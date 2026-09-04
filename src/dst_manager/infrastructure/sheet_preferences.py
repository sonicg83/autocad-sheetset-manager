"""图纸集级列偏好应用目录 JSON 原子存储（PLAN-DM-015 任务 2）。

配置按图纸集记忆在应用数据目录（``data_dir/ui-preferences/sheets/``），不写入
DST 或工程目录。文件路径由 workspace_id 的 SHA-256 摘要派生——workspace_id 只
参与摘要，绝不作为路径组成部分，防止路径注入/越界写入。写入经同目录临时文件
+ ``os.replace`` 原子替换，进程内锁串行化写入防止并发损坏，失败保留旧文件；
``load`` 只读不创建任何目录。

校验结构对应任务 1 建立的 ``ColumnPreferences`` TS 类型
（schemaVersion=1；file/layout/subsetAll/subsetSingle 布尔；properties 为
``sheet:`` 前缀到布尔的映射），未知 schema、字段缺失/类型错误、非法属性键与
属性数量超限一律拒绝（``SHEET_PREFERENCES_INVALID``）；文件系统错误映射为
``SHEET_PREFERENCES_IO``。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

PREFERENCES_SCHEMA_VERSION = 1
MAX_PROPERTIES = 500  # 属性开关数量上限，防止病态偏好文件拖垮界面

_BOOL_FIELDS = ("file", "layout", "subsetAll", "subsetSingle")


class SheetPreferencesError(Exception):
    """偏好读写失败（壳桥映射为 SHEET_PREFERENCES_IO）。"""


class InvalidSheetPreferencesError(SheetPreferencesError):
    """偏好结构校验失败（壳桥映射为 SHEET_PREFERENCES_INVALID）。"""


def _workspace_digest(workspace_id: str) -> str:
    return hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()


def _validate(preferences: object) -> dict[str, Any]:
    if not isinstance(preferences, dict):
        raise InvalidSheetPreferencesError("列偏好必须是 JSON 对象")
    if preferences.get("schemaVersion") != PREFERENCES_SCHEMA_VERSION:
        raise InvalidSheetPreferencesError(
            f"未知的列偏好 schemaVersion：{preferences.get('schemaVersion')!r}"
        )
    for key in _BOOL_FIELDS:
        if not isinstance(preferences.get(key), bool):
            raise InvalidSheetPreferencesError(f"字段 {key} 必须是布尔值")
    properties = preferences.get("properties")
    if not isinstance(properties, dict):
        raise InvalidSheetPreferencesError("字段 properties 必须是对象")
    if len(properties) > MAX_PROPERTIES:
        raise InvalidSheetPreferencesError(f"属性开关数量超过上限 {MAX_PROPERTIES}")
    for key, value in properties.items():
        if not isinstance(key, str) or not key.startswith("sheet:"):
            raise InvalidSheetPreferencesError(f"非法属性键：{key!r}")
        if not isinstance(value, bool):
            raise InvalidSheetPreferencesError(f"属性 {key} 的开关值必须是布尔值")
    return preferences


class SheetPreferences:
    """图纸集列偏好的原子 JSON 存取；线程安全、失败保留旧文件。"""

    def __init__(self, data_dir: Path) -> None:
        self._sheets_dir = Path(data_dir) / "ui-preferences" / "sheets"
        self._lock = threading.Lock()

    def load(self, workspace_id: str) -> dict[str, Any] | None:
        """读取该工作区偏好；无存储返回 None。只读操作，绝不创建目录。"""
        path = self._sheets_dir / f"{_workspace_digest(workspace_id)}.json"
        if not path.is_file():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SheetPreferencesError(f"读取列偏好失败：{exc}") from exc
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise InvalidSheetPreferencesError(f"列偏好文件损坏：{exc}") from exc
        return _validate(data)

    def save(self, workspace_id: str, preferences: dict[str, Any]) -> None:
        """校验并原子写入该工作区偏好；校验失败不创建目录，写入失败保留旧文件。"""
        validated = _validate(preferences)
        path = self._sheets_dir / f"{_workspace_digest(workspace_id)}.json"
        payload = json.dumps(validated, ensure_ascii=False, indent=2).encode("utf-8")
        with self._lock:
            try:
                self._sheets_dir.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".json.tmp")  # 同目录临时文件，保证 os.replace 原子性
                with tmp.open("wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
            except OSError as exc:
                try:
                    (path.with_suffix(".json.tmp")).unlink(missing_ok=True)
                except OSError:
                    pass
                raise SheetPreferencesError(f"写入列偏好失败：{exc}") from exc
