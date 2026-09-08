"""进程内设置快照持有者与保存事务（PLAN-DM-019 设置中心任务 4）。

职责（API 与同进程的 desktop/Worker 服务共用）：

- 缓存最近一次解析的 :class:`SettingsSnapshot`：``current()`` 返回缓存（首次
  调用加载）；``refresh_if_changed()`` 按文件 ``(st_mtime_ns, st_size)`` 指纹
  判断是否重解析，供 Worker 每任务前低成本调用；
- ``apply_changes()`` 在 ``threading.RLock`` 内完成"读基准 → 校验 → 合并 →
  落盘 → 换快照"全流程：``expected_revision`` 与文件当前修订号不符抛
  :class:`SettingsConflict`（零副作用，API 层转 409）；校验失败抛
  :class:`SettingsValidationError`（文件与内存均不动，API 层转 422）；
- 校验分层：registry 约束（int 范围、bool/enum 取值、path 非法字符）先行，
  再以 ``Settings(**merged_overrides)`` 构造兜底，pydantic 异常转逐字段中文
  错误；文件遗留的非法值在保存时随合并清理（自愈），不影响本次合法提交。

``default_store()`` 返回用户默认设置存储：``DST_MANAGER_SETTINGS_PATH`` 环境
变量存在时用作 settings.json 完整路径（测试/e2e 隔离机制）；否则落
``%LOCALAPPDATA%\\dst-manager\\settings.json``（``LOCALAPPDATA`` 缺失回退
``~/AppData/Local``，与 ``config._default_data_dir`` 同规则，不导入其私有函数）。
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from pydantic import ValidationError

from dst_manager.config import Settings

from .registry import REGISTRY, SettingsItemMeta, enum_options, min_max
from .resolver import SettingsResolver, SettingsSnapshot
from .store import UserSettingsStore

# Windows 文件名非法字符（盘符冒号与 \ / 分隔符为合法路径成分，不在其列）
_ILLEGAL_PATH_CHARS = '<>"|?*'


class SettingsConflict(Exception):
    """expected_revision 与文件当前修订号不符（零副作用，API 层转 409）。"""


class SettingsValidationError(Exception):
    """设置值未通过校验（API 层转 422）。

    ``errors``：key → 中文消息，逐字段回显到设置界面。
    """

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("；".join(f"{key}: {message}" for key, message in errors.items()))
        self.errors = errors


def default_store() -> UserSettingsStore:
    """用户默认设置存储（见模块 docstring 的路径规则）。"""
    override = os.environ.get("DST_MANAGER_SETTINGS_PATH")
    if override:
        return UserSettingsStore(Path(override))
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return UserSettingsStore(base / "dst-manager" / "settings.json")


def _validate_value(meta: SettingsItemMeta, value: object) -> str | None:
    """按 registry 控件类型校验单个取值；通过返回 None，否则返回中文消息。"""
    label = meta.label
    if meta.control == "path":
        if value is None:
            return None  # 显式置空与"清空覆盖"等价
        if not isinstance(value, str):
            return f"{label} 必须为文件路径"
        if any(char in _ILLEGAL_PATH_CHARS or ord(char) < 0x20 for char in value):
            return f"{label} 含有路径非法字符"
        return None
    if meta.control == "bool":
        return None if isinstance(value, bool) else f"{label} 仅接受 true 或 false"
    if meta.control == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"{label} 必须为整数"
        try:
            low, high = min_max(meta.key)
        except ValueError:
            return None  # 字段无 ge/le 约束（如 cad_timeout_seconds），不设范围
        if not low <= value <= high:
            return f"{label} 必须介于 {low} 和 {high} 之间"
        return None
    # enum
    options = {option["value"] for option in enum_options(meta.key)}
    if value in options:
        return None
    return f"{label} 取值必须为 {'/'.join(str(option) for option in sorted(options))}"


class RuntimeSettings:
    """进程内快照持有者 + 保存事务。"""

    def __init__(self, store: UserSettingsStore) -> None:
        self._store = store
        self._resolver = SettingsResolver(store)
        self._lock = threading.RLock()
        self._snapshot: SettingsSnapshot | None = None
        self._fingerprint: tuple[int, int] | None = None  # (st_mtime_ns, st_size)

    def current(self) -> SettingsSnapshot:
        """返回缓存快照；首次调用加载。"""
        with self._lock:
            if self._snapshot is None:
                self._reload_locked()
            return self._snapshot

    def refresh_if_changed(self) -> bool:
        """文件指纹变化才重解析；返回是否发生重载（Worker 每任务前调用）。"""
        with self._lock:
            fingerprint = self._file_fingerprint()
            if self._snapshot is None or fingerprint != self._fingerprint:
                self._reload_locked()
                return True
            return False

    def apply_changes(
        self,
        set_values: dict[str, object],
        unset: list[str],
        expected_revision: int,
    ) -> SettingsSnapshot:
        """锁内全流程保存事务：读基准 → 校验 → 合并 → 落盘 → 换快照。

        校验失败抛 :class:`SettingsValidationError`（文件与内存均不动）；
        ``expected_revision`` 不符抛 :class:`SettingsConflict`（无任何副作用）。
        """
        with self._lock:
            overrides_raw, revision, _diagnostics = self._store.load()
            if revision != expected_revision:
                raise SettingsConflict(
                    f"配置已被其他窗口修改（当前修订号 {revision}，期望 {expected_revision}），请刷新后重试"
                )
            fresh = self._validated_set(set_values, unset)
            merged = self._filter_registry(overrides_raw)
            merged.update(fresh)
            for key in unset:
                merged.pop(key, None)
            merged = self._ensure_constructible(merged, set(fresh))
            self._store.save_overrides(merged, revision)
            self._snapshot = self._resolver.load_snapshot()
            self._fingerprint = self._file_fingerprint()
            return self._snapshot

    # ---- 内部实现（调用方须持有 self._lock）----

    def _reload_locked(self) -> None:
        self._snapshot = self._resolver.load_snapshot()
        self._fingerprint = self._file_fingerprint()

    def _file_fingerprint(self) -> tuple[int, int] | None:
        try:
            stat = self._store.path.stat()
        except OSError:
            return None  # 文件缺失按"无指纹"参与比较
        return (stat.st_mtime_ns, stat.st_size)

    def _validated_set(self, set_values: dict[str, object], unset: list[str]) -> dict[str, object]:
        """registry 约束校验 + 空串路径规整为 None；失败抛 SettingsValidationError。"""
        known = {meta.key: meta for meta in REGISTRY}
        errors: dict[str, str] = {}
        for key in unset:
            if key not in known:
                errors[key] = f"未知的设置项：{key}"
        fresh: dict[str, object] = {}
        for key, value in set_values.items():
            meta = known.get(key)
            if meta is None:
                errors[key] = f"未知的设置项：{key}"
                continue
            if meta.control == "path" and isinstance(value, str) and not value.strip():
                fresh[key] = None  # 空串/纯空白 = 清空覆盖，写 null
                continue
            message = _validate_value(meta, value)
            if message is not None:
                errors[key] = message
                continue
            fresh[key] = value
        if errors:
            raise SettingsValidationError(errors)
        return fresh

    @staticmethod
    def _filter_registry(overrides_raw: dict[str, object]) -> dict[str, object]:
        """文件遗留覆盖规整：未知键忽略，空串/纯空白路径规整为 None。"""
        known = {meta.key: meta for meta in REGISTRY}
        merged: dict[str, object] = {}
        for key, value in overrides_raw.items():
            meta = known.get(key)
            if meta is None:
                continue  # 手编文件中的未知键不注入，避免 pydantic 拒绝
            if meta.control == "path" and isinstance(value, str) and not value.strip():
                value = None
            merged[key] = value
        return merged

    @staticmethod
    def _ensure_constructible(merged: dict[str, object], fresh_keys: set[str]) -> dict[str, object]:
        """``Settings(**merged)`` 构造兜底。

        文件遗留值类型非法时剔除后重试（随本次保存自愈）；本次提交的取值
        仍非法则把 pydantic 异常转成逐字段中文 ``SettingsValidationError``。
        """
        try:
            Settings(**merged)
            return merged
        except ValidationError as exc:
            bad = {str(err["loc"][0]) for err in exc.errors() if err["loc"]}
            for key in bad - fresh_keys:
                merged.pop(key, None)
            try:
                Settings(**merged)
            except ValidationError as retry_exc:
                raise SettingsValidationError(_errors_to_chinese(retry_exc)) from retry_exc
            return merged


def _errors_to_chinese(exc: ValidationError) -> dict[str, str]:
    """pydantic 错误转 key → 中文消息（registry 约束之外的兜底分支）。"""
    errors: dict[str, str] = {}
    for err in exc.errors():
        key = str(err["loc"][0]) if err["loc"] else "settings"
        errors[key] = "取值类型或格式不合法，请检查后重试"
    return errors
