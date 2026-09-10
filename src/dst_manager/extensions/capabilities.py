"""Capability Broker 与最小 ExtensionContext（PLAN-DM-020 Task 4 / ARCH-DM-006 §6.1）。

扩展只能通过短生命周期 :class:`ExtensionContext` 请求**清单已声明 ∩ 宿主
allowlist** 的能力；每次上下文绑定 ``extension_id``、``workspace_id``、
``required_revision_id`` 与 invocation ID，``close()`` 后立即失效。

上下文不暴露 ``DstManagerService``、SQLAlchemy Session、可变
``Workspace``/``SheetSetDocument``、发布器、任务队列、ShellBridge、工作区
根路径或 DST/DWG 绝对路径——唯一出口是 :meth:`ExtensionContext.workspace_snapshot`
返回的冻结快照。本任务只交付 broker 本体；接入 ``ExtensionRuntime``/
``discover`` 对账属 Task 6，宿主可用性（``AVAILABLE_CAPABILITIES``）缺省
沿用注册表模块的同一份 allowlist。

错误 ``code`` 只取自既有封闭词汇（``ExtensionDiagnosticCode`` 六值诊断码与
ARCH-DM-006 §12 平台码），不新增诊断码。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from dst_manager.extensions import registry as registry_module
from dst_manager.extensions.snapshots import (
    WorkspaceSnapshot,
    build_workspace_snapshot,
)
from dst_manager.infrastructure.extension_workspace import (
    ExtensionWorkspaceReadError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dst_manager.extensions.contracts import ExtensionManifest
    from dst_manager.infrastructure.extension_workspace import DecodedWorkspace

__all__ = [
    "WORKSPACE_SNAPSHOT_CAPABILITY",
    "CapabilityBroker",
    "CapabilityError",
    "ExtensionContext",
]

#: 首期唯一可发放的读取能力（真实清单 required_capabilities 之一）。
WORKSPACE_SNAPSHOT_CAPABILITY = "workspace.snapshot.read.v1"


class CapabilityError(RuntimeError):
    """能力/上下文拒绝；``code`` 取自既有平台码或诊断码封闭词汇。"""

    def __init__(
        self, code: str, message: str, *, params: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.params = dict(params) if params else {}


class ExtensionContext:
    """一次调用的最小能力上下文：``close()`` 后所有请求失败。"""

    def __init__(
        self,
        extension_id: str,
        workspace_id: str,
        required_revision_id: str,
        capability: str,
        reader: object,
    ) -> None:
        self._extension_id = extension_id
        self._workspace_id = workspace_id
        self._required_revision_id = required_revision_id
        self._capability = capability
        self._reader = reader
        self._invocation_id = uuid.uuid4().hex
        self._closed = False

    @property
    def extension_id(self) -> str:
        return self._extension_id

    @property
    def invocation_id(self) -> str:
        return self._invocation_id

    def workspace_snapshot(self) -> WorkspaceSnapshot:
        if self._closed:
            raise CapabilityError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                "扩展上下文已关闭，能力不再可用",
                params={
                    "extension_id": self._extension_id,
                    "workspace_id": self._workspace_id,
                },
            )
        decoded = self._decode()
        if decoded.revision_id != self._required_revision_id:
            raise CapabilityError(
                "REPREVIEW_REQUIRED",
                f"工作区修订已变化：要求 {self._required_revision_id}，"
                f"当前 {decoded.revision_id}",
                params={
                    "workspace_id": decoded.workspace_id,
                    "required_revision_id": self._required_revision_id,
                    "current_revision_id": decoded.revision_id,
                },
            )
        return build_workspace_snapshot(
            workspace_id=decoded.workspace_id,
            revision_id=decoded.revision_id,
            document=decoded.document,
        )

    def close(self) -> None:
        self._closed = True

    def _decode(self) -> DecodedWorkspace:
        try:
            return self._reader.load(self._workspace_id)  # type: ignore[attr-defined]
        except ExtensionWorkspaceReadError as exc:
            raise CapabilityError(exc.code, str(exc), params=exc.params) from exc


class CapabilityBroker:
    """按"清单声明 ∩ 宿主 allowlist"发放短生命周期扩展上下文。"""

    def __init__(
        self,
        manifests: Mapping[str, ExtensionManifest],
        reader: object,
        *,
        allowed_capabilities: frozenset[str] | None = None,
    ) -> None:
        self._manifests = dict(manifests)
        self._reader = reader
        self._allowed_capabilities = allowed_capabilities

    def context(
        self,
        extension_id: str,
        workspace_id: str,
        required_revision_id: str,
        *,
        capability: str = WORKSPACE_SNAPSHOT_CAPABILITY,
    ) -> ExtensionContext:
        params = {"extension_id": extension_id, "capability": capability}
        manifest = self._manifests.get(extension_id)
        if manifest is None:
            raise CapabilityError(
                "EXTENSION_NOT_FOUND",
                f"扩展未登记：{extension_id}",
                params={"extension_id": extension_id},
            )
        if capability not in registry_module.KNOWN_CAPABILITIES:
            raise CapabilityError(
                "EXTENSION_CAPABILITY_UNKNOWN",
                f"宿主不认识的能力：{capability}",
                params=params,
            )
        allowed = (
            self._allowed_capabilities
            if self._allowed_capabilities is not None
            else registry_module.AVAILABLE_CAPABILITIES
        )
        if capability not in allowed:
            raise CapabilityError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                f"能力当前不可发放：{capability}",
                params=params,
            )
        if all(declared != capability for declared in manifest.required_capabilities):
            raise CapabilityError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                f"扩展未声明能力：{capability}",
                params=params,
            )
        return ExtensionContext(
            extension_id,
            workspace_id,
            required_revision_id,
            capability,
            self._reader,
        )
