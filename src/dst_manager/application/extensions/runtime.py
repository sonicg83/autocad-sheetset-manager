"""扩展平台运行时编排（PLAN-DM-020 Task 3/9 / ARCH-DM-006 §5、§7、§11、§12）。

:class:`ExtensionRuntime` 把 :class:`~dst_manager.extensions.registry.ExtensionRegistry`
（生命周期状态机）与 :class:`~dst_manager.infrastructure.persistence.extensions.ExtensionStore`
（四张持久化表）组合为宿主运行时：

- 启动顺序由装配方（``create_app``）保证：现有 ``DstManagerService`` 完成数据库
  迁移与发布恢复之后才调用 :meth:`start`（内部先 ``registry.discover()``，再按
  持久化启停意图对账）；
- 用户启停意图持久化在 ``extension_states``；``WAITING_DEPENDENCY``/
  ``INCOMPATIBLE``/``FAILED`` 等"天然不可用"状态与用户停用在该表上可区分；
- 执行通道（Task 9 / §11）：编排摘要复核 → 候选目录分配 → 扩展写候选 → 一次性
  授权消费 → 宿主回读 + 原子保存 + Artifact 登记 → ``finally`` 清理候选；
  授权存储与候选根由装配方注入（桌面壳与桥共享同一 :class:`SaveGrantStore`）；
- 对接口层统一抛 :class:`ExtensionPlatformError`（ARCH §12 平台错误码 +
  HTTP 状态 + 结构化 params），注册表的具体诊断码不外溢到 API。
"""

from __future__ import annotations

import logging
import shutil
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from dst_manager.extensions.artifacts import (
    ArtifactExporter,
    ArtifactExportError,
    ArtifactMetadata,
)
from dst_manager.extensions.builtin.index import BUILTIN_EXTENSION_INDEX
from dst_manager.extensions.builtin.sheet_catalog.errors import (
    SHEET_CATALOG_MESSAGE_KEYS,
    SheetCatalogError,
)
from dst_manager.extensions.builtin.sheet_catalog.extension import (
    ArtifactProposalDirectory,
    SheetCatalogExecuteRequest,
    SheetCatalogExecuteResponse,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import (
    _template_from_json,
    load_templates,
    save_templates,
)
from dst_manager.extensions.builtin.sheet_catalog.workbook import validate_candidate
from dst_manager.extensions.capabilities import (
    CapabilityBroker,
    CapabilityError,
    ExtensionContext,
)
from dst_manager.extensions.contracts import (
    XLSX_MEDIA_TYPE,
    BuiltinExtensionEntry,
    ExtensionDescriptor,
    ExtensionInvocation,
    ExtensionManifest,
)
from dst_manager.extensions.registry import ExtensionRegistry, ExtensionRegistryError
from dst_manager.extensions.save_grants import (
    SaveGrantError,
    SaveGrantStore,
    capture_baseline,
)
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

#: 模板校验分派的内置扩展（Task 11B / Ruling-11）：该扩展的设置 PUT 语义由
#: :func:`save_templates` 全权解释（SC-06 服务端强制）；其余扩展（未来）保持
#: 通用 JSON 存储路径，不受模板规则影响。
_TEMPLATE_SETTINGS_EXTENSION_ID = "dst-manager.sheet-catalog"


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


def default_runtime(
    sessions,
    *,
    save_grants: SaveGrantStore | None = None,
    proposal_root: Path | None = None,
) -> ExtensionRuntime:
    """宿主默认装配：注册表 + 扩展仓储 + 只读工作区快照 reader。

    ``save_grants``/``proposal_root`` 是执行通道装配点（Task 9）：桌面壳经
    ``create_app`` 注入与 :class:`~dst_manager.interfaces.shell.ShellBridge`
    **同一个** :class:`SaveGrantStore`，桥创建的授权才能被 API 执行消费。
    """
    return ExtensionRuntime(
        ExtensionRegistry(),
        ExtensionStore(sessions),
        reader=ExtensionWorkspaceReader(sessions),
        save_grants=save_grants,
        proposal_root=proposal_root,
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
        save_grants: SaveGrantStore | None = None,
        proposal_root: Path | None = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._reader = reader
        self._save_grants = save_grants
        self._proposal_root = proposal_root

    @property
    def registry(self) -> ExtensionRegistry:
        """注册表（桌面壳桥只读消费：动作声明校验）。"""
        return self._registry

    @property
    def save_grants(self) -> SaveGrantStore | None:
        """一次性保存授权存储；未装配时执行通道契约化拒绝。"""
        return self._save_grants

    @property
    def store(self) -> ExtensionStore:
        """扩展仓储（桌面壳桥只读消费：Task 11B 导出成果定位）。"""
        return self._store

    @property
    def proposal_root(self) -> Path | None:
        """候选临时目录的宿主根（应用数据目录内；按次在其下建唯一子目录）。"""
        return self._proposal_root

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
        if extension_id == _TEMPLATE_SETTINGS_EXTENSION_ID:
            # SC-06 服务端接线（Task 11B / fix round 1）：分派只按扩展身份，不
            # 耦合字面 schema 版本——否则 settings_schema 升级后 v2 PUT 会静默
            # 退回通用 JSON 路径（fail-open，重名/超限重新失去强制）。非 v1 负载
            # 在分派内天然 fail-closed：模板条目按 v1 严格解析、服务端高 schema
            # 行经 unknown_schema_preserved 走 Ruling-9 冲突拒绝。
            value = self._save_catalog_templates(extension_id, value, expected_revision)
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

    def _save_catalog_templates(
        self,
        extension_id: str,
        value: dict[str, object],
        expected_revision: int,
    ) -> dict[str, object]:
        """图纸目录设置 PUT → 模板校验（Task 5 ``save_templates`` 全权解释）。

        服务端权威：casefold 重名、100 上限、内置不可变（同名影子模板）、
        修订冲突（expected/current）与未知高 schema 拒绝（Ruling-9：原 JSON
        保留）全部由 ``save_templates`` 强制；结构性坏负载（缺 UUID/缺列等）
        按设置无效契约化 422。成功返回可持久化的规范序列化负载。
        """
        current = self._store.get_settings(extension_id)
        collection = load_templates(current)  # 服务端修订 + 未知高 schema 标记
        try:
            entries = value.get("user_templates")
            if not isinstance(entries, list):
                raise TypeError(
                    "SHEET_CATALOG_TEMPLATES_INVALID: user_templates 必须是模板数组"
                )
            incoming = []
            for entry in entries:
                if isinstance(entry, dict) and entry.get("template_id") is None:
                    raise ValueError(
                        "SHEET_CATALOG_TEMPLATE_ID_REQUIRED: 保存前必须分配模板 UUID"
                    )
                incoming.append(_template_from_json(entry))
            collection = replace(collection, user_templates=tuple(incoming))
            return save_templates(collection, expected_revision)
        except SheetCatalogError as exc:
            raise ExtensionPlatformError(
                exc.code,
                str(exc),
                status_code=_SHEET_CATALOG_ERROR_STATUS.get(exc.code, 503),
                params=dict(exc.params),
                key_override=SHEET_CATALOG_MESSAGE_KEYS[exc.code],
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtensionPlatformError(
                "EXTENSION_SETTINGS_INVALID",
                str(exc),
                status_code=422,
                params={"extension_id": extension_id},
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

    # ------------------------------------------------------------------ 执行

    def execute_action(
        self,
        extension_id: str,
        action_id: str,
        request: SheetCatalogExecuteRequest,
    ) -> SheetCatalogExecuteResponse:
        """执行扩展动作（Task 9 / ARCH-DM-006 §11、SPEC-DM-012 §8.2）。

        宿主编排：可用性与动作声明（注册表）→ 摘要复核（对当前快照重建预览，
        修订/模板/扩展身份漂移 → ``REPREVIEW_REQUIRED``）→ 分配应用临时目录内
        唯一候选目录 → 扩展只写候选 → 消费一次性授权 → 宿主回读校验 + 原子
        保存 + 登记 Artifact → ``finally`` 清理候选目录（SPEC §10）。
        扩展全程不见目标路径；导出不取得工作区写锁、不创建修订或 CAD 任务。
        """
        if self._save_grants is None:
            raise ExtensionPlatformError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                f"保存授权通道未装配：{extension_id}/{action_id}",
                status_code=503,
                params={"extension_id": extension_id, "action_id": action_id},
            )
        if self._proposal_root is None:
            raise ExtensionPlatformError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                f"宿主未分配候选临时目录：{extension_id}/{action_id}",
                status_code=503,
                params={"extension_id": extension_id, "action_id": action_id},
            )
        try:
            with self.invoke_action(extension_id, action_id) as invocation:
                extension = invocation.extension
                repview = getattr(extension, "repreview", None)
                if repview is None or not hasattr(extension, "execute"):
                    raise ExtensionPlatformError(
                        "EXTENSION_CAPABILITY_UNAVAILABLE",
                        f"宿主尚未接入该扩展的执行通道：{extension_id}/{action_id}",
                        status_code=503,
                        params={"extension_id": extension_id, "action_id": action_id},
                    )
                with self.extension_context(
                    extension_id, request.workspace_id, request.base_revision_id
                ) as context:
                    repreview = self._verify_repreview(
                        repview, context, request
                    )
                    candidate_dir = self._proposal_root / uuid.uuid4().hex
                    try:
                        # mkdir 也纳入清理范围：创建本身可能半途失败留残目录。
                        candidate_dir.mkdir(parents=True)
                        record = self._run_candidate_to_artifact(
                            invocation,
                            extension,
                            context,
                            request,
                            action_id,
                            candidate_dir,
                        )
                    finally:
                        shutil.rmtree(candidate_dir, ignore_errors=True)
        except CapabilityError as exc:
            raise capability_platform_error(exc) from exc
        except (SaveGrantError, ArtifactExportError) as exc:
            raise ExtensionPlatformError(
                exc.code,
                str(exc),
                status_code=_ERROR_STATUS.get(exc.code, 503),
                params={
                    "extension_id": extension_id,
                    "action_id": action_id,
                    "workspace_id": request.workspace_id,
                },
            ) from exc
        except SheetCatalogError as exc:
            # 候选生成失败（模板/表达式/工作簿）按 ARTIFACT_WRITE_FAILED 契约化，
            # 不登记 Artifact（摘要复核已放行的模板不应走到这里，防御性兜底）。
            raise ExtensionPlatformError(
                "ARTIFACT_WRITE_FAILED",
                str(exc),
                status_code=_ERROR_STATUS["ARTIFACT_WRITE_FAILED"],
                params={
                    "extension_id": extension_id,
                    "action_id": action_id,
                    "workspace_id": request.workspace_id,
                },
            ) from exc
        except OSError as exc:
            # 候选目录创建/候选写入的 OS 级失败（磁盘满/AV 锁定/权限）同样按
            # ARTIFACT_WRITE_FAILED 契约化，绝不逃逸为非契约 500。此失败只会
            # 发生在授权消费之前（ArtifactExporter 已把发布期 OS 错误包装为
            # ArtifactExportError），授权未被烧毁，重试不要求重新"另存为"。
            raise ExtensionPlatformError(
                "ARTIFACT_WRITE_FAILED",
                str(exc),
                status_code=_ERROR_STATUS["ARTIFACT_WRITE_FAILED"],
                params={
                    "extension_id": extension_id,
                    "action_id": action_id,
                    "workspace_id": request.workspace_id,
                },
            ) from exc
        return SheetCatalogExecuteResponse(
            artifact_id=record.artifact_id,
            file_name=record.file_name,
            output_path=record.output_path,
            warnings=repreview.warnings,
        )

    @staticmethod
    def _verify_repreview(
        repview, context: ExtensionContext, request: SheetCatalogExecuteRequest
    ):
        """摘要复核：可执行且摘要逐字节一致才放行；否则 REPREVIEW_REQUIRED。"""
        repreview = repview(context, request)
        if (
            not repreview.executable
            or repreview.preview_digest != request.preview_digest
        ):
            raise ExtensionPlatformError(
                "REPREVIEW_REQUIRED",
                "预览摘要与当前快照不一致，请刷新预览后重试",
                status_code=_ERROR_STATUS["REPREVIEW_REQUIRED"],
                params={
                    "workspace_id": request.workspace_id,
                    "base_revision_id": request.base_revision_id,
                },
            )
        return repreview

    def _run_candidate_to_artifact(
        self,
        invocation: ExtensionInvocation,
        extension,
        context: ExtensionContext,
        request: SheetCatalogExecuteRequest,
        action_id: str,
        candidate_dir: Path,
    ) -> ArtifactRecord:
        """扩展写候选 → 消费授权 → 宿主回读 + 原子保存 + 登记。"""
        candidate = extension.execute(
            context, request, ArtifactProposalDirectory(root=candidate_dir)
        )
        grant = self._save_grants.consume(
            request.save_grant_id,
            invocation.manifest.extension_id,
            action_id,
            request.workspace_id,
        )
        exporter = ArtifactExporter(
            self._store,
            invocation_id=invocation.invocation_id,
            candidate_validator=lambda path: validate_candidate(
                path, candidate.expected_headers, candidate.expected_rows
            ),
        )
        return exporter.publish(
            grant,
            candidate.path,
            ArtifactMetadata(
                extension_id=invocation.manifest.extension_id,
                extension_version=invocation.manifest.version,
                workspace_id=request.workspace_id,
                source_revision_id=request.base_revision_id,
                kind="sheet-catalog",
                media_type=XLSX_MEDIA_TYPE,
            ),
        )

    def artifact_availability(self, record: ArtifactRecord) -> str:
        """按当前文件系统状态派生 Artifact 可用性（历史记录不伪装成可用）。

        ``AVAILABLE``：文件存在且 SHA-256 与登记一致；``MISSING``：文件已
        删除；``CHANGED``：文件存在但内容被移动/修改（SPEC-DM-012 §10）。
        """
        baseline = capture_baseline(Path(record.output_path))
        if not baseline.existed:
            return _ARTIFACT_MISSING
        if (
            baseline.sha256 == record.sha256
            and baseline.size_bytes == record.size_bytes
        ):
            return _ARTIFACT_AVAILABLE
        return _ARTIFACT_CHANGED

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


#: Artifact 可用性派生词表（SPEC-DM-012 §10；只反映当前文件系统状态）。
_ARTIFACT_AVAILABLE = "AVAILABLE"
_ARTIFACT_MISSING = "MISSING"
_ARTIFACT_CHANGED = "CHANGED"

#: 平台错误码默认 HTTP 状态（ARCH-DM-006 §12；能力不可用按环境问题归 503）。
#: 未登记的注册表诊断码由 :meth:`ExtensionRuntime._platform_error` 兜底为 503。
#: ``REPREVIEW_REQUIRED``：来源修订或模板摘要已变化（409 语义：请刷新）。
#: ``SAVE_GRANT_INVALID``/``EXPORT_DESTINATION_CHANGED``：授权状态冲突（409）。
#: ``ARTIFACT_WRITE_FAILED``：候选/保存/登记失败，宿主环境问题（503）。
_ERROR_STATUS: dict[str, int] = {
    "EXTENSION_NOT_FOUND": 404,
    "EXTENSION_DISABLED": 409,
    "EXTENSION_INCOMPATIBLE": 409,
    "EXTENSION_CAPABILITY_UNAVAILABLE": 503,
    "EXTENSION_ACTION_NOT_FOUND": 404,
    "REPREVIEW_REQUIRED": 409,
    "SAVE_GRANT_INVALID": 409,
    "EXPORT_DESTINATION_CHANGED": 409,
    "ARTIFACT_WRITE_FAILED": 503,
}

#: SheetCatalogError 目录码默认 HTTP 状态（沿用 ARCH-DM-006 §12 映射风格：
#: 并发/状态冲突 409，负载校验 422，宿主环境失败 503）。模板保存路径只会
#: 产生其中一部分；词汇保持封闭，未登记的新码兜底 503（对齐 _platform_error）。
_SHEET_CATALOG_ERROR_STATUS: dict[str, int] = {
    "SHEET_CATALOG_TEMPLATE_CONFLICT": 409,
    "SHEET_CATALOG_COLUMN_DUPLICATE": 409,
    "SHEET_CATALOG_TEMPLATE_LIMIT": 422,
    "SHEET_CATALOG_EXPRESSION_INVALID": 422,
    "SHEET_CATALOG_FIELD_UNDEFINED": 422,
    "SHEET_CATALOG_VALUE_MISSING": 422,
    "SHEET_CATALOG_XLSX_INVALID": 503,
}
