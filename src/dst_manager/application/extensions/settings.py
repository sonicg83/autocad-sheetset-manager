"""扩展设置编排服务（PLAN-DM-025 Task 2 / ARCH-DM-006 §8.1、§11）。

:class:`ExtensionSettingsService` 是 Provider 与持久层之间的唯一编排点：

- 按 ``extension_id`` 查找固定索引登记的 Provider，并核对 Manifest/Provider
  的 ID、Schema 与字段覆盖；登记缺失、重复或不一致只让该扩展的设置不可用
  （稳定 503 + 诊断 reason），不阻止宿主启动（§8.1）；
- 读取：从未保存返回 Provider 默认零值 + ``revision = 0``；较旧 Schema 先在
  内存逐级迁移并校验，不落库；未知高版本保留原始 JSON 并返回只读视图，
  PUT 以 ``EXTENSION_SETTINGS_SCHEMA_NEWER``/409 拒绝覆盖；
- 保存：Provider 校验与规范化 → ``ExtensionStore`` 条件更新（乐观并发，
  竞争写入 409），Provider 业务错误原样上抛；
- 呈现：``field_specs()`` 只读返回 ``generated`` 的 Provider 字段元数据，
  供接口层与清单的排序/i18n key 合并（§8.2），不读取 Store；
- 快照：把有效值递归冻结，并以 ``extension_id`` + ``settings_schema`` + 有效值
  计算稳定摘要，供动作调用绑定（§11）。

Provider 只在调用点被问语义问题，不接触 Store、数据库或文件系统；所有非契约
异常都被转换为 :class:`ExtensionSettingsError`，日志只记录稳定标识与异常文本，
绝不记录完整设置值。失败只禁用该扩展的设置与动作，不影响宿主启动。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, cast

from dst_manager.extensions.settings import (
    ExtensionSettingsProvider,
    ExtensionSettingsSnapshot,
    FrozenJson,
    SettingsFieldSpec,
    freeze_json,
    settings_digest,
)
from dst_manager.infrastructure.persistence.extensions import (
    SettingsRevisionConflictError,
)

if TYPE_CHECKING:
    from dst_manager.extensions.contracts import ExtensionManifest
    from dst_manager.infrastructure.persistence.extensions import (
        ExtensionStore,
        VersionedJson,
    )

__all__ = [
    "EXTENSION_SETTINGS_PROVIDER_DUPLICATE",
    "EXTENSION_SETTINGS_PROVIDER_FIELD_UNKNOWN",
    "EXTENSION_SETTINGS_PROVIDER_ID_MISMATCH",
    "EXTENSION_SETTINGS_PROVIDER_MISSING",
    "EXTENSION_SETTINGS_PROVIDER_SCHEMA_MISMATCH",
    "ExtensionSettingsError",
    "ExtensionSettingsService",
    "ExtensionSettingsView",
    "settings_provider_error",
]

logger = logging.getLogger(__name__)

#: Manifest/Provider 配对诊断码（ARCH-DM-006 §8.1）。诊断只携带稳定码，
#: 由接口层映射为 ``EXTENSION_CAPABILITY_UNAVAILABLE``/503 的 ``params.reason``。
EXTENSION_SETTINGS_PROVIDER_MISSING = "EXTENSION_SETTINGS_PROVIDER_MISSING"
EXTENSION_SETTINGS_PROVIDER_DUPLICATE = "EXTENSION_SETTINGS_PROVIDER_DUPLICATE"
EXTENSION_SETTINGS_PROVIDER_ID_MISMATCH = "EXTENSION_SETTINGS_PROVIDER_ID_MISMATCH"
EXTENSION_SETTINGS_PROVIDER_SCHEMA_MISMATCH = "EXTENSION_SETTINGS_PROVIDER_SCHEMA_MISMATCH"
EXTENSION_SETTINGS_PROVIDER_FIELD_UNKNOWN = "EXTENSION_SETTINGS_PROVIDER_FIELD_UNKNOWN"

#: 已存设置高于当前扩展支持版本（ARCH-DM-006 §8.1/§12）。
EXTENSION_SETTINGS_SCHEMA_NEWER = "EXTENSION_SETTINGS_SCHEMA_NEWER"

#: 设置无效（Schema 或数据）：负载校验、迁移、解析失败与修订冲突共用稳定码。
EXTENSION_SETTINGS_INVALID = "EXTENSION_SETTINGS_INVALID"

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class ExtensionSettingsView:
    """设置读取/保存结果：持久值 + 解析后的有效值 + 只读诊断。

    ``value`` 是规范化的持久值（未知高版本时是原 JSON 原样）；``effective_value``
    是 Provider 解析后的有效配置（含代码默认值）。``read_only`` 为 True 时
    只允许展示，PUT 一律以 ``EXTENSION_SETTINGS_SCHEMA_NEWER`` 拒绝。
    """

    extension_id: str
    schema_version: int
    revision: int
    value: dict[str, object]
    effective_value: dict[str, object]
    read_only: bool = False
    diagnostic_code: str | None = None


class ExtensionSettingsError(RuntimeError):
    """设置链路的结构化错误：Provider 业务码与宿主编排错误共用同一形状。

    ``code`` 为稳定错误码（Provider 业务码或宿主设置码），``status_code`` 为
    接口层 HTTP 状态，``params`` 只携带稳定值，``key_override`` 允许 Provider
    自带文案键（如目录域 ``errors.sheetCatalog.*``）。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        params: dict[str, str | int] | None = None,
        key_override: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.params = dict(params) if params else {}
        self.key_override = key_override


def settings_provider_error(
    manifest: ExtensionManifest, provider: ExtensionSettingsProvider
) -> str | None:
    """Manifest 与 Provider 的配对校验；返回稳定诊断码，``None`` 表示可解释。

    清单只声明呈现（顺序与 i18n key），Provider 唯一定义类型、默认值与约束，
    因此 ``generated`` 清单字段必须由 Provider 的字段元数据逐个解释（§8.2）。
    """
    if provider.extension_id != manifest.extension_id:
        return EXTENSION_SETTINGS_PROVIDER_ID_MISMATCH
    if provider.schema_version != manifest.settings_schema:
        return EXTENSION_SETTINGS_PROVIDER_SCHEMA_MISMATCH
    contribution = manifest.settings_contribution
    if contribution is None:
        return None
    declared = {field.key for field in contribution.fields}
    known = {field.key for field in provider.field_definitions}
    if declared - known:
        return EXTENSION_SETTINGS_PROVIDER_FIELD_UNKNOWN
    return None


class ExtensionSettingsService:
    """Provider 登记、设置读取/保存与不可变快照的编排服务。"""

    def __init__(
        self,
        store: ExtensionStore,
        providers: Iterable[ExtensionSettingsProvider] = (),
    ) -> None:
        self._store = store
        self._providers: dict[str, ExtensionSettingsProvider] = {}
        self._diagnostics: dict[str, str] = {}
        self.bind_providers(providers)

    # ------------------------------------------------------------------ 登记

    def bind_providers(self, providers: Iterable[ExtensionSettingsProvider]) -> None:
        """登记固定索引的 Provider；重复登记只隔离该扩展的设置（§8.1）。

        以 Provider 声明的 ``extension_id`` 为登记键；同一实例重复登记（宿主
        重启后重新 ``start()``）是幂等的，不同实例争夺同一 ID 则整条 ID 不可用。
        """
        for provider in providers:
            extension_id = getattr(provider, "extension_id", None)
            if not isinstance(extension_id, str) or not extension_id:
                logger.warning(
                    "EXTENSION_SETTINGS_PROVIDER_INVALID provider=%s",
                    type(provider).__name__,
                )
                continue
            if extension_id in self._diagnostics:
                continue  # 已判定重复登记：保持不可用，不再接受后续实例
            if self._providers.get(extension_id) is provider:
                continue
            if extension_id in self._providers:
                del self._providers[extension_id]
                self._diagnostics[extension_id] = EXTENSION_SETTINGS_PROVIDER_DUPLICATE
                logger.warning(
                    "EXTENSION_SETTINGS_PROVIDER_DUPLICATE extension_id=%s", extension_id
                )
                continue
            self._providers[extension_id] = provider

    # ------------------------------------------------------------------ 读取

    def get(self, manifest: ExtensionManifest) -> ExtensionSettingsView:
        """读取设置视图：零值 / 内存迁移 / 有效值解析 / 未知高版本只读保护。"""
        return self._view_or_read_only(manifest, self._provider_or_none(manifest))

    # ------------------------------------------------------------------ 呈现

    def field_specs(self, manifest: ExtensionManifest) -> tuple[SettingsFieldSpec, ...]:
        """该扩展可生成字段的 Provider 元数据（只读，不访问 Store）。

        ``generated`` 呈现的字段项由接口层把这里的控件类型、默认值与约束与
        清单的排序和 i18n key 合并（ARCH-DM-006 §8.2）；``custom`` 呈现或未
        声明设置的扩展没有可持续生成的字段，返回空元组。Provider 登记或配对
        异常与读取一致，上抛同一稳定诊断，由调用方映射为契约化错误。

        ``generated`` 声明必然伴随已登记且配对一致的 Provider：字段覆盖由
        :func:`settings_provider_error` 在 :meth:`_provider_or_none` 里唯一放行，
        因此这里不保留“Provider 缺席就返回空字段”的静默降级（§8.1 要求诊断，
        而空元组会让接口层默默渲染出一份缺字段的部分结果）。
        """
        contribution = manifest.settings_contribution
        if contribution is None or contribution.presentation != "generated":
            return ()
        provider = self._provider_or_none(manifest)
        assert provider is not None, "generated 声明必须经 settings_provider_error 放行"
        return tuple(provider.field_definitions)

    # ------------------------------------------------------------------ 保存

    def put(
        self,
        manifest: ExtensionManifest,
        schema_version: int,
        value: dict[str, object],
        expected_revision: int,
    ) -> ExtensionSettingsView:
        """校验并保存设置：Schema 核对 → Provider 规范化 → 乐观并发写入。"""
        provider = self._provider_or_none(manifest)
        current_schema = self._current_schema(manifest, provider)
        if schema_version != current_schema:
            raise ExtensionSettingsError(
                EXTENSION_SETTINGS_INVALID,
                f"设置 schema 版本不匹配：声明 {current_schema}，提交 {schema_version}",
                status_code=422,
                params={"settings_schema": current_schema, "submitted": schema_version},
            )
        stored = self._store.get_settings(manifest.extension_id)
        if stored is not None and stored.schema_version > current_schema:
            raise self._schema_newer(
                manifest.extension_id, stored.schema_version, current_schema
            )
        if provider is None:
            normalized = dict(value)
        else:
            normalized = self._provider_call(
                manifest.extension_id,
                EXTENSION_SETTINGS_INVALID,
                lambda: provider.validate_and_normalize(dict(value)),
            )
        try:
            saved = self._store.put_settings(
                manifest.extension_id, current_schema, normalized, expected_revision
            )
        except SettingsRevisionConflictError as exc:
            current = self._store.get_settings(manifest.extension_id)
            raise ExtensionSettingsError(
                EXTENSION_SETTINGS_INVALID,
                str(exc),
                status_code=409,
                params={
                    "expected_revision": expected_revision,
                    "current_revision": current.revision if current is not None else 0,
                },
            ) from exc
        if provider is None:
            return ExtensionSettingsView(
                extension_id=manifest.extension_id,
                schema_version=saved.schema_version,
                revision=saved.revision,
                value=dict(saved.value),
                effective_value=dict(saved.value),
            )
        return self._view(manifest, provider, saved.value, revision=saved.revision)

    # ------------------------------------------------------------------ 快照

    def snapshot(self, manifest: ExtensionManifest) -> ExtensionSettingsSnapshot:
        """一次动作调用的不可变设置快照：冻结有效值 + 稳定摘要（§11）。

        未知高版本无法解析，必须 fail-closed 拒绝动作调用，绝不按当前语义去
        执行一份来自更高版本的配置。
        """
        provider = self._provider_or_none(manifest)
        view = self._view_or_read_only(manifest, provider)
        if view.read_only:
            raise self._schema_newer(
                manifest.extension_id,
                view.schema_version,
                self._current_schema(manifest, provider),
            )
        effective = view.effective_value
        return ExtensionSettingsSnapshot(
            extension_id=manifest.extension_id,
            schema_version=view.schema_version,
            revision=view.revision,
            value=cast("Mapping[str, FrozenJson]", freeze_json(effective)),
            digest=settings_digest(
                manifest.extension_id, view.schema_version, effective
            ),
        )

    # ------------------------------------------------------------------ 内部

    def _provider_or_none(
        self, manifest: ExtensionManifest
    ) -> ExtensionSettingsProvider | None:
        """解析该扩展的 Provider；登记异常与配对不一致只隔离自身设置。

        未登记 Provider 且清单未声明设置时返回 ``None``：该扩展走通用 JSON
        存储路径（无默认值、迁移与校验语义），保持既有行为不变。
        """
        extension_id = manifest.extension_id
        diagnostic = self._diagnostics.get(extension_id)
        if diagnostic is not None:
            raise self._unavailable(extension_id, diagnostic)
        provider = self._providers.get(extension_id)
        if provider is None:
            if manifest.settings_contribution is not None:
                raise self._unavailable(
                    extension_id, EXTENSION_SETTINGS_PROVIDER_MISSING
                )
            return None
        diagnostic = settings_provider_error(manifest, provider)
        if diagnostic is not None:
            logger.warning(
                "EXTENSION_SETTINGS_PROVIDER_INVALID extension_id=%s reason=%s",
                extension_id,
                diagnostic,
            )
            raise self._unavailable(extension_id, diagnostic)
        return provider

    def _view_or_read_only(
        self,
        manifest: ExtensionManifest,
        provider: ExtensionSettingsProvider | None,
    ) -> ExtensionSettingsView:
        stored = self._store.get_settings(manifest.extension_id)
        if provider is None:
            return self._generic_view(manifest, stored)
        if stored is not None and stored.schema_version > provider.schema_version:
            return self._read_only_view(manifest, stored)
        revision = stored.revision if stored is not None else 0
        return self._view(
            manifest,
            provider,
            self._current_value(manifest, provider, stored),
            revision=revision,
        )

    def _current_value(
        self,
        manifest: ExtensionManifest,
        provider: ExtensionSettingsProvider,
        stored: VersionedJson | None,
    ) -> dict[str, object]:
        """当前持久值的规范形态：旧 Schema 先在内存逐级迁移再校验。"""
        if stored is None:
            return dict(provider.default_value())
        if stored.schema_version < provider.schema_version:
            stored_schema_version = stored.schema_version
            migrated = self._provider_call(
                manifest.extension_id,
                "EXTENSION_SETTINGS_MIGRATION_FAILED",
                lambda: provider.migrate(stored_schema_version, dict(stored.value)),
            )
            return self._normalize(manifest, provider, migrated)
        return self._normalize(manifest, provider, stored.value)

    def _normalize(
        self,
        manifest: ExtensionManifest,
        provider: ExtensionSettingsProvider,
        value: dict[str, object],
    ) -> dict[str, object]:
        return self._provider_call(
            manifest.extension_id,
            EXTENSION_SETTINGS_INVALID,
            lambda: provider.validate_and_normalize(dict(value)),
        )

    def _view(
        self,
        manifest: ExtensionManifest,
        provider: ExtensionSettingsProvider,
        value: dict[str, object],
        *,
        revision: int,
    ) -> ExtensionSettingsView:
        effective = self._provider_call(
            manifest.extension_id,
            EXTENSION_SETTINGS_INVALID,
            lambda: provider.resolve(dict(value)),
        )
        return ExtensionSettingsView(
            extension_id=manifest.extension_id,
            schema_version=provider.schema_version,
            revision=revision,
            value=dict(value),
            effective_value=effective,
        )

    def _generic_view(
        self, manifest: ExtensionManifest, stored: VersionedJson | None
    ) -> ExtensionSettingsView:
        """无 Provider 的扩展：原样读写版本化 JSON（无默认值与迁移语义）。"""
        if stored is not None and stored.schema_version > manifest.settings_schema:
            return self._read_only_view(manifest, stored)
        if stored is None:
            return ExtensionSettingsView(
                extension_id=manifest.extension_id,
                schema_version=manifest.settings_schema,
                revision=0,
                value={},
                effective_value={},
            )
        return ExtensionSettingsView(
            extension_id=manifest.extension_id,
            schema_version=stored.schema_version,
            revision=stored.revision,
            value=dict(stored.value),
            effective_value=dict(stored.value),
        )

    def _read_only_view(
        self, manifest: ExtensionManifest, stored: VersionedJson
    ) -> ExtensionSettingsView:
        logger.warning(
            "EXTENSION_SETTINGS_SCHEMA_NEWER extension_id=%s settings_schema=%s",
            manifest.extension_id,
            stored.schema_version,
        )
        return ExtensionSettingsView(
            extension_id=manifest.extension_id,
            schema_version=stored.schema_version,
            revision=stored.revision,
            value=dict(stored.value),
            effective_value=dict(stored.value),
            read_only=True,
            diagnostic_code=EXTENSION_SETTINGS_SCHEMA_NEWER,
        )

    def _provider_call(
        self, extension_id: str, diagnostic: str, call: Callable[[], _T]
    ) -> _T:
        """调用 Provider：契约错误原样上抛，其余异常转换为稳定设置错误。

        任何 Provider 失败都只禁用该扩展的设置与动作（ARCH-DM-006 §8.1），
        绝不逃逸为宿主 500；诊断日志只含扩展 ID、稳定码与异常文本，不含设置值。
        """
        try:
            return call()
        except ExtensionSettingsError:
            raise
        except Exception as exc:
            logger.warning(
                "%s extension_id=%s error=%s", diagnostic, extension_id, exc
            )
            raise self._invalid(extension_id, str(exc)) from exc

    @staticmethod
    def _current_schema(
        manifest: ExtensionManifest, provider: ExtensionSettingsProvider | None
    ) -> int:
        return (
            provider.schema_version if provider is not None else manifest.settings_schema
        )

    @staticmethod
    def _invalid(extension_id: str, message: str | None = None) -> ExtensionSettingsError:
        """设置无效：稳定码 + 结构化标识，``message`` 保留原始诊断供排障。"""
        return ExtensionSettingsError(
            EXTENSION_SETTINGS_INVALID,
            message or f"扩展设置无效：{extension_id}",
            status_code=422,
            params={"extension_id": extension_id},
        )

    @staticmethod
    def _schema_newer(
        extension_id: str, settings_schema: int, current_schema: int
    ) -> ExtensionSettingsError:
        return ExtensionSettingsError(
            EXTENSION_SETTINGS_SCHEMA_NEWER,
            f"已存设置 schema {settings_schema} 高于当前支持版本 {current_schema}，"
            "原 JSON 已保留且只读",
            status_code=409,
            params={
                "extension_id": extension_id,
                "settings_schema": settings_schema,
                "current_schema": current_schema,
            },
        )

    @staticmethod
    def _unavailable(extension_id: str, reason: str) -> ExtensionSettingsError:
        return ExtensionSettingsError(
            "EXTENSION_CAPABILITY_UNAVAILABLE",
            f"扩展设置不可用：{extension_id}（{reason}）",
            status_code=503,
            params={"extension_id": extension_id, "reason": reason},
        )
