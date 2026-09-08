"""用户配置文件原子存取（PLAN-DM-019 设置中心任务 1）。

设置文件为单个 JSON 文档（``schema_version``/``config_revision``/``values``），
``values`` 是默认值之上的用户覆盖字典。读取语义：

- 文件缺失 → 返回空覆盖与诊断码 ``SETTINGS_FILE_MISSING``，不创建任何文件；
- 内容损坏（JSON 解析失败 / 顶层或 ``values`` 非对象 / 字段类型非法）→
  原文件重命名为 ``<名称>.corrupt-<时间戳>`` 备份后按缺失处理，
  诊断码 ``SETTINGS_FILE_CORRUPT``；
- ``schema_version`` 大于本程序支持的版本 → 抛 ``SettingsSchemaNewer``，
  原文件字节不动（未来版本写回会丢字段，禁止静默降级）；
- ``schema_version`` 小于本程序版本 → 抛 ``SettingsSchemaOlder``
  （本期无迁移器，由调用方决定处置）。

写入经同目录临时文件 + ``os.replace`` 原子替换，成功后清场不残留临时文件；
``config_revision`` 每次保存自增一次，供后续并发检测使用。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

SCHEMA_VERSION = 1


class SettingsFileMissing(Exception):
    """设置文件缺失（诊断码 SETTINGS_FILE_MISSING）。"""


class SettingsFileCorrupt(Exception):
    """设置文件损坏，已备份为 backup_path（诊断码 SETTINGS_FILE_CORRUPT）。"""

    def __init__(self, backup_path: Path) -> None:
        super().__init__(f"设置文件损坏，已备份至：{backup_path}")
        self.backup_path = backup_path


class SettingsSchemaNewer(Exception):
    """设置文件 schema 版本高于本程序支持版本，文件保持原样。"""


class SettingsSchemaOlder(Exception):
    """设置文件 schema 版本低于本程序支持版本（本期无迁移器）。"""


def _backup_corrupt_file(path: Path) -> Path:
    """将损坏文件重命名为 <名称>.corrupt-<时间戳>，冲突时追加 -1 序号。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    seq = 0
    while backup.exists():
        seq += 1
        backup = path.with_name(f"{path.name}.corrupt-{stamp}-{seq}")
    path.replace(backup)
    return backup


class UserSettingsStore:
    """单个用户设置 JSON 文件的原子存取。"""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> tuple[dict[str, object], int, list[str]]:
        """返回 (values 覆盖字典, config_revision, 诊断码列表)。"""
        if not self._path.is_file():
            return {}, 0, ["SETTINGS_FILE_MISSING"]
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._reset_corrupt()
        if not isinstance(data, dict):
            return self._reset_corrupt()
        schema_version = data.get("schema_version")
        revision = data.get("config_revision")
        values = data.get("values")
        if (
            not isinstance(schema_version, int)
            or isinstance(schema_version, bool)
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or not isinstance(values, dict)
        ):
            return self._reset_corrupt()
        if schema_version > SCHEMA_VERSION:
            raise SettingsSchemaNewer(
                f"设置文件 schema_version={schema_version} 高于支持的 {SCHEMA_VERSION}"
            )
        if schema_version < SCHEMA_VERSION:
            raise SettingsSchemaOlder(
                f"设置文件 schema_version={schema_version} 低于支持的 {SCHEMA_VERSION}"
            )
        return values, revision, []

    def _reset_corrupt(self) -> tuple[dict[str, object], int, list[str]]:
        """备份损坏文件并按缺失处理（诊断码 SETTINGS_FILE_CORRUPT）。"""
        _backup_corrupt_file(self._path)
        return {}, 0, ["SETTINGS_FILE_CORRUPT"]

    def save_overrides(self, values: dict[str, object], previous_revision: int) -> int:
        """原子写入覆盖字典；config_revision = previous_revision + 1，返回新修订号。"""
        new_revision = previous_revision + 1
        payload = json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "config_revision": new_revision,
                "values": values,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 同目录临时文件，保证 os.replace 原子性；异常时清理，不残留临时文件
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp", delete=False
            ) as handle:
                tmp_path = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self._path)
            tmp_path = None
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        return new_revision
