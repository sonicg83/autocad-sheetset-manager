"""扩展平台运行时编排（PLAN-DM-020 Task 3 / ARCH-DM-006 §5、§7、§12）。

:class:`ExtensionRuntime` 把 :class:`~dst_manager.extensions.registry.ExtensionRegistry`
（生命周期状态机）与 :class:`~dst_manager.infrastructure.persistence.extensions.ExtensionStore`
（四张持久化表）组合为宿主运行时：

- 启动顺序由装配方（``create_app``）保证：现有 ``DstManagerService`` 完成数据库
  迁移与发布恢复之后才调用 :meth:`start`（内部先 ``registry.discover()``，再按
  持久化启停意图对账）；
- 用户启停意图持久化在 ``extension_states``；``WAITING_DEPENDENCY``/
  ``INCOMPATIBLE``/``FAILED`` 等"天然不可用"状态与用户停用在该表上可区分；
- 对接口层统一抛 :class:`ExtensionPlatformError`（ARCH §12 平台错误码 +
  HTTP 状态 + 结构化 params），注册表的具体诊断码不外溢到 API。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from dst_manager.extensions.builtin.index import BUILTIN_EXTENSION_INDEX
from dst_manager.extensions.capabilities import (
    CapabilityBroker,
    CapabilityError,
    ExtensionContext,
)
from dst_manager.extensions.contracts import (
    BuiltinExtensionEntry,
    ExtensionDescriptor,
    ExtensionInvocation,
    ExtensionManifest,
)
from dst_manager.extensions.registry import ExtensionRegistry, ExtensionRegistryError
from dst_manager.infrastructure.extension_workspace import ExtensionWorkspaceReader
from dst_manager.infrastructure.persistence.extensions import (
    ArtifactRecord,
    ExtensionStateRecord,
    ExtensionStore,
    SettingsRevisionConflictError,
    VersionedJson,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ExtensionPlatformError",
    "ExtensionRuntime",
    "ExtensionStatusView",
    "capability_platform_error",
    "default_runtime",
]

#: 清单不可读时注册表用资源串占位（Task 1 披露）；占位记录不落库、不可启用。
_PLACEHOLDER_ERROR = "EXTENSION_MANIFEST_INVALID"


class ExtensionPlatformError(RuntimeError):
    """API 层统一平台错误：``code`` 为 ARCH-DM-006 §12 平台错误码。

    ``key_override`` 允许同码不同语境（如 Artifact 404）在接口层覆盖稳定
    文案键；缺省由接口层按码映射。应用层不持有任何文案目录。
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


@dataclass(frozen=True, slots=True)
class ExtensionStatusView:
    """列表/启停响应视图：描述符状态 + 持久化的用户启停意图。"""

    extension_id: str
    version: str
    name_key: str
    description_key: str
    status: str
    enabled: bool
    error_code: str | None
    manifest: ExtensionManifest


def default_runtime(sessions) -> ExtensionRuntime:
    """宿主默认装配：注册表 + 扩展仓储 + 只读工作区快照 reader。"""
    return ExtensionRuntime(
        ExtensionRegistry(),
        ExtensionStore(sessions),
        reader=ExtensionWorkspaceReader(sessions),
    )


def capability_platform_error(exc: CapabilityError) -> ExtensionPlatformError:
    """能力/上下文拒绝 → 契约化平台错误（ARCH-DM-006 §12 状态映射）。"""
    return ExtensionPlatformError(
        exc.code,
        str(exc),
        status_code=_ERROR_STATUS.get(exc.code, 503),
        params=dict(exc.params),
    )


class ExtensionRuntime:
    """组合 registry/store 的扩展运行时（线程安全由注册表保证）。"""

    def __init__(
        self,
        registry: ExtensionRegistry,
        store: ExtensionStore,
        *,
        reader: ExtensionWorkspaceReader | None = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._reader = reader

    # ------------------------------------------------------------------ 启动

    def start(
        self, entries: Sequence[BuiltinExtensionEntry] = BUILTIN_EXTENSION_INDEX
    ) -> None:
        """发现固定索引条目并按持久化意图对账；单扩展失败只留下稳定诊断。"""
        self._registry.discover(entries)
        self._reconcile_persisted_states()

    def _reconcile_persisted_states(self) -> None:
        now = datetime.now(UTC)
        for descriptor in self._registry.list():
            try:
                self._reconcile_one(descriptor, now)
            except Exception:
                logger.warning(
                    "EXTENSION_STATE_RECONCILE_FAILED extension_id=%s",
                    descriptor.manifest.extension_id,
                    exc_info=True,
                )

    def _reconcile_one(self, descriptor: ExtensionDescriptor, now: datetime) -> None:
        extension_id = descriptor.manifest.extension_id
        if descriptor.error_code == _PLACEHOLDER_ERROR:
            return  # 清单不可读的占位记录：不落库、不可启用
        state = self._store.get_state(extension_id)
        if state is None:
            # 首次发现：按清单默认意图落库（DISABLED 之外都视为启用中）。
            self._persist(extension_id, descriptor.status != "DISABLED", descriptor, now)
            return
        if not state.enabled and descriptor.status != "DISABLED":
            # 用户已停用：把本次重启中重新拉起的实例重新停掉（排空 + stop）。
            descriptor = self._registry.set_enabled(extension_id, False)
        elif state.enabled and descriptor.status in {"DISABLED", "STOPPED", "DISCOVERED"}:
            # 用户意图为启用但本次未拉起：重新启用；不兼容/缺能力被注册表拒绝时
            # 保持持久化停用并记录稳定诊断，绝不伪装成已启用。
            try:
                descriptor = self._registry.set_enabled(extension_id, True)
            except ExtensionRegistryError as exc:
                logger.warning(
                    "EXTENSION_RESTART_ENABLE_FAILED extension_id=%s code=%s",
                    extension_id,
                    exc.code,
                )
                self._persist(extension_id, False, descriptor, now)
                return
        self._persist(extension_id, state.enabled, descriptor, now)

    def _persist(
        self,
        extension_id: str,
        enabled: bool,
        descriptor: ExtensionDescriptor,
        now: datetime,
    ) -> None:
        self._store.put_state(
            ExtensionStateRecord(
                extension_id=extension_id,
                enabled=enabled,
                last_loaded_version=descriptor.manifest.version,
                last_error_code=descriptor.error_code,
                updated_at=now,
            )
        )

    # ------------------------------------------------------------------ 查询

    def list_extensions(self) -> list[ExtensionStatusView]:
        views: list[ExtensionStatusView] = []
        for descriptor in self._registry.list():
            extension_id = descriptor.manifest.extension_id
            if descriptor.error_code == _PLACEHOLDER_ERROR:
                enabled = False
            else:
                state = self._store.get_state(extension_id)
                enabled = (
                    state.enabled if state is not None else descriptor.status != "DISABLED"
                )
            views.append(self._view(descriptor, enabled))
        return views

    # ------------------------------------------------------------------ 启停

    def set_enabled(self, extension_id: str, enabled: bool) -> ExtensionStatusView:
        descriptor = self._descriptor_or_404(extension_id)
        if enabled and descriptor.error_code == _PLACEHOLDER_ERROR:
            # 清单不可读的占位条目没有可用工厂：显式契约化拒绝，
            # 绝不让注册表断言/异常逃逸成非契约 500。
            raise ExtensionPlatformError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                f"清单不可读的扩展不能启用：{extension_id}",
                status_code=503,
                params={"extension_id": extension_id},
            )
        try:
            descriptor = self._registry.set_enabled(extension_id, enabled)
        except ExtensionRegistryError as exc:
            raise self._with_identity(
                self._platform_error(exc.code, str(exc)), extension_id=extension_id
            ) from exc
        if descriptor.error_code != _PLACEHOLDER_ERROR:
            try:
                self._persist(extension_id, enabled, descriptor, datetime.now(UTC))
            except Exception:
                logger.warning(
                    "EXTENSION_STATE_PERSIST_FAILED extension_id=%s", extension_id,
                    exc_info=True,
                )
        return self._view(descriptor, enabled)

    # ------------------------------------------------------------------ 设置与偏好

    def get_settings(self, extension_id: str) -> VersionedJson:
        manifest = self._manifest(extension_id)
        versioned = self._store.get_settings(extension_id)
        if versioned is None:
            # 从未保存：返回清单 schema 的零值默认，而不是 404。
            return VersionedJson(
                schema_version=manifest.settings_schema, revision=0, value={}
            )
        return versioned

    def put_settings(
        self,
        extension_id: str,
        schema_version: int,
        value: dict[str, object],
        expected_revision: int,
    ) -> VersionedJson:
        manifest = self._manifest(extension_id)
        if schema_version != manifest.settings_schema:
            raise ExtensionPlatformError(
                "EXTENSION_SETTINGS_INVALID",
                f"设置 schema 版本不匹配：声明 {manifest.settings_schema}，提交 {schema_version}",
                status_code=422,
                params={"settings_schema": manifest.settings_schema, "submitted": schema_version},
            )
        try:
            return self._store.put_settings(
                extension_id, schema_version, value, expected_revision
            )
        except SettingsRevisionConflictError as exc:
            current = self._store.get_settings(extension_id)
            raise ExtensionPlatformError(
                "EXTENSION_SETTINGS_INVALID",
                str(exc),
                status_code=409,
                params={
                    "expected_revision": expected_revision,
                    "current_revision": current.revision if current else 0,
                },
            ) from exc

    def get_preference(self, extension_id: str, workspace_id: str) -> VersionedJson:
        manifest = self._manifest(extension_id)
        versioned = self._store.get_preference(workspace_id, extension_id)
        if versioned is None:
            return VersionedJson(
                schema_version=manifest.settings_schema, revision=0, value={}
            )
        return versioned

    def put_preference(
        self,
        extension_id: str,
        workspace_id: str,
        schema_version: int,
        value: dict[str, object],
    ) -> VersionedJson:
        manifest = self._manifest(extension_id)
        if schema_version != manifest.settings_schema:
            raise ExtensionPlatformError(
                "EXTENSION_SETTINGS_INVALID",
                f"偏好 schema 版本不匹配：声明 {manifest.settings_schema}，提交 {schema_version}",
                status_code=422,
                params={"settings_schema": manifest.settings_schema, "submitted": schema_version},
            )
        return self._store.put_preference(workspace_id, extension_id, schema_version, value)

    # ------------------------------------------------------------------ 动作与 Artifact

    @contextmanager
    def invoke_action(
        self, extension_id: str, action_id: str
    ) -> Iterator[ExtensionInvocation]:
        """校验扩展可调用且动作已声明，并给出调用上下文（活动计数排空语义由注册表保证）。"""
        self._manifest(extension_id)  # 未知扩展先于注册表给出稳定 404
        try:
            with self._registry.invoke(extension_id, action_id) as invocation:
                yield invocation
        except ExtensionRegistryError as exc:
            raise self._with_identity(
                self._platform_error(exc.code, str(exc)),
                extension_id=extension_id,
                action_id=action_id,
            ) from exc

    @contextmanager
    def extension_context(
        self, extension_id: str, workspace_id: str, required_revision_id: str
    ) -> Iterator[ExtensionContext]:
        """经 CapabilityBroker 发放短生命周期扩展上下文，退出即关闭。

        修订漂移（``REPREVIEW_REQUIRED``）与工作区不可读由上下文在
        ``workspace_snapshot()`` 时拒绝；能力拒绝统一经
        :func:`capability_platform_error` 映射为契约化平台错误。
        """
        manifests = {
            descriptor.manifest.extension_id: descriptor.manifest
            for descriptor in self._registry.list()
        }
        if self._reader is None:
            # 测试/定制装配未提供只读 reader：显式契约化拒绝，绝不 AttributeError → 500。
            raise ExtensionPlatformError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                f"宿主未装配工作区快照读取通道：{extension_id}",
                status_code=503,
                params={"extension_id": extension_id, "workspace_id": workspace_id},
            )
        broker = CapabilityBroker(manifests, self._reader)
        try:
            context = broker.context(extension_id, workspace_id, required_revision_id)
        except CapabilityError as exc:
            raise capability_platform_error(exc) from exc
        try:
            yield context
        finally:
            context.close()

    def settings_schema(self, extension_id: str) -> int:
        """清单声明的设置/偏好 schema 版本（偏好保存用）。"""
        return self._manifest(extension_id).settings_schema

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        record = self._store.get_artifact(artifact_id)
        if record is None:
            raise ExtensionPlatformError(
                "EXTENSION_NOT_FOUND",
                f"Artifact 不存在：{artifact_id}",
                status_code=404,
                params={"artifact_id": artifact_id},
                key_override="errors.extension.artifactNotFound",
            )
        return record

    # ------------------------------------------------------------------ 内部

    def _manifest(self, extension_id: str) -> ExtensionManifest:
        return self._descriptor_or_404(extension_id).manifest

    def _descriptor_or_404(self, extension_id: str) -> ExtensionDescriptor:
        for descriptor in self._registry.list():
            if descriptor.manifest.extension_id == extension_id:
                return descriptor
        raise ExtensionPlatformError(
            "EXTENSION_NOT_FOUND",
            f"扩展未登记：{extension_id}",
            status_code=404,
            params={"extension_id": extension_id},
        )

    @staticmethod
    def _platform_error(code: str, message: str) -> ExtensionPlatformError:
        """注册表平台码 → 契约化错误；未映射的诊断码兜底为"扩展当前不可用"。

        注册表可能抛出的稳定码都已映射；任何未知/新增诊断码都不得变成
        KeyError → 500，统一按 503 ``EXTENSION_CAPABILITY_UNAVAILABLE`` 返回
        契约化错误体，原始诊断保留在 ``message`` 供排障。
        """
        status = _ERROR_STATUS.get(code)
        if status is None:
            return ExtensionPlatformError(
                "EXTENSION_CAPABILITY_UNAVAILABLE", message, status_code=503
            )
        return ExtensionPlatformError(code, message, status_code=status)

    @staticmethod
    def _with_identity(
        error: ExtensionPlatformError, **identity: str
    ) -> ExtensionPlatformError:
        """注册表异常只带文本详情：把请求标识补齐为结构化 params。"""
        for name, value in identity.items():
            error.params.setdefault(name, value)
        return error

    @staticmethod
    def _view(descriptor: ExtensionDescriptor, enabled: bool) -> ExtensionStatusView:
        manifest = descriptor.manifest
        return ExtensionStatusView(
            extension_id=manifest.extension_id,
            version=manifest.version,
            name_key=manifest.name_key,
            description_key=manifest.description_key,
            status=descriptor.status,
            enabled=enabled,
            error_code=descriptor.error_code,
            manifest=manifest,
        )


#: 平台错误码默认 HTTP 状态（ARCH-DM-006 §12；能力不可用按环境问题归 503）。
#: 未登记的注册表诊断码由 :meth:`ExtensionRuntime._platform_error` 兜底为 503。
#: ``REPREVIEW_REQUIRED`` 仅来自能力上下文的修订漂移核对（409 语义：请刷新）。
_ERROR_STATUS: dict[str, int] = {
    "EXTENSION_NOT_FOUND": 404,
    "EXTENSION_DISABLED": 409,
    "EXTENSION_INCOMPATIBLE": 409,
    "EXTENSION_CAPABILITY_UNAVAILABLE": 503,
    "EXTENSION_ACTION_NOT_FOUND": 404,
    "REPREVIEW_REQUIRED": 409,
}
