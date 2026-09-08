"""设置快照解析与来源追踪（PLAN-DM-019 设置中心任务 3）。

合并优先级 默认 < env < 文件覆盖，产物 :class:`SettingsSnapshot` 供 API 与
Worker 共用。来源判定采用双层构造：先无 kwargs 构造 ``Settings()`` 记录
env 基线，再对有覆盖的 key 用 ``Settings(**overrides)`` 构造最终实例——
``source`` 只看"key 是否在文件覆盖集中 + env 基线是否偏离默认值"，
绝不从合并后的终值反推（覆盖值恰好等于 env 值时仍是 ``"file"``）。

- 文件覆盖值经 kwargs 注入 ``Settings(...)``，由 pydantic 完成校验与
  路径规范化（相对路径解析为绝对路径，兼容现状）；
- 空字符串/纯空白路径在传入 kwargs 前置为 None，绝不解析为 cwd；
- 手编文件值类型非法（pydantic 拒绝，如 int 字段塞字符串）→ 忽略全部
  文件覆盖、按默认+env 构造 ``Settings``，诊断附 ``SETTINGS_FILE_CORRUPT``
  与中文说明——绝不让进程启动/任务认领因设置文件崩溃；
- ``SettingsSchemaNewer``（schema 过新）→ 忽略全部文件覆盖、用纯
  env/默认构造 ``Settings``，``schema_blocked=True`` 只读，
  ``config_revision`` 仍取文件值（store.load 抛异常前已校验其为 int）。

不缓存——每次 ``load_snapshot()`` 重读文件（Worker 每任务调用，成本可忽略）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from pydantic import ValidationError

from dst_manager.config import Settings

from .registry import REGISTRY
from .store import SettingsSchemaNewer, UserSettingsStore


@dataclass(frozen=True)
class FieldSource:
    """单个设置项的来源信息。"""

    source: str  # "default" | "env" | "file"
    has_file_override: bool


@dataclass(frozen=True)
class SettingsSnapshot:
    """一次解析得到的只读快照。"""

    settings: Settings
    sources: dict[str, FieldSource]  # 仅 REGISTRY 中的 9 个 key
    diagnostics: list[str]
    config_revision: int
    schema_blocked: bool  # True = Schema 过新，只读


def _field_default(key: str) -> object:
    """取 ``Settings`` 字段的默认值（default_factory 展开后的实际值）。"""
    return Settings.model_fields[key].get_default(call_default_factory=True)


class SettingsResolver:
    """把设置文件覆盖与 env/默认合并成带来源标注的快照。"""

    def __init__(self, store: UserSettingsStore) -> None:
        self._store = store
        # key → 控件类型；path 类字段用"env 变量存在"判定来源，其余比较基线值
        self._controls = {meta.key: meta.control for meta in REGISTRY}

    def load_snapshot(self) -> SettingsSnapshot:
        """重读设置文件并解析快照（含 schema 过新时的只读降级）。"""
        try:
            overrides_raw, revision, diagnostics = self._store.load()
            schema_blocked = False
        except SettingsSchemaNewer:
            # schema 过新：文件字节不动，忽略全部覆盖，修订号仍取文件值
            overrides_raw, revision, diagnostics = {}, self._read_file_revision(), []
            schema_blocked = True
        overrides = self._normalize_overrides(overrides_raw)
        try:
            settings = Settings(**overrides)
        except ValidationError:
            # 手编文件值类型非法：忽略全部文件覆盖降级运行，修订号仍取文件值
            return self._degraded_snapshot(revision, diagnostics)
        return SettingsSnapshot(
            settings=settings,
            sources=self._build_sources(overrides),
            diagnostics=diagnostics,
            config_revision=revision,
            schema_blocked=schema_blocked,
        )

    def _degraded_snapshot(self, revision: int, diagnostics: list[str]) -> SettingsSnapshot:
        """值类型非法时的降级快照：纯默认+env，无文件覆盖，携带诊断。"""
        return SettingsSnapshot(
            settings=Settings(),
            sources=self._build_sources({}),
            diagnostics=[
                *diagnostics,
                "SETTINGS_FILE_CORRUPT",
                "设置文件中存在类型非法的值，已忽略全部文件覆盖，按默认值与环境变量运行",
            ],
            config_revision=revision,
            schema_blocked=False,
        )

    def _read_file_revision(self) -> int:
        """schema 过新时直接读文件的 config_revision（load 前置校验保证为 int）。"""
        try:
            data = json.loads(self._store.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        revision = data.get("config_revision") if isinstance(data, dict) else None
        if isinstance(revision, int) and not isinstance(revision, bool):
            return revision
        return 0

    def _normalize_overrides(self, overrides_raw: dict[str, object]) -> dict[str, object]:
        """过滤出 REGISTRY 内的 key，并把空字符串/纯空白路径规整为 None。"""
        overrides: dict[str, object] = {}
        for key, value in overrides_raw.items():
            control = self._controls.get(key)
            if control is None:
                continue  # 非 REGISTRY 键不注入，避免 pydantic 拒绝未知字段
            if control == "path" and isinstance(value, str) and not value.strip():
                value = None
            overrides[key] = value
        return overrides

    def _build_sources(self, overrides: dict[str, object]) -> dict[str, FieldSource]:
        """逐 key 判定来源；env 基线取自无 kwargs 构造的 ``Settings()``。"""
        env_settings = Settings()
        sources: dict[str, FieldSource] = {}
        for key, control in self._controls.items():
            has_override = key in overrides
            if has_override:
                source = "file"
            elif control == "path":
                # path 类"env 存在即 env"：环境变量显式存在，或 env 基线偏离默认值
                #（覆盖 .env 文件通道——其值不进 os.environ，只能从基线偏差识别）
                env_var_present = os.environ.get(f"DST_MANAGER_{key.upper()}") is not None
                baseline_differs = getattr(env_settings, key) != _field_default(key)
                source = "env" if env_var_present or baseline_differs else "default"
            elif getattr(env_settings, key) != _field_default(key):
                source = "env"
            else:
                source = "default"
            sources[key] = FieldSource(source, has_override)
        return sources
