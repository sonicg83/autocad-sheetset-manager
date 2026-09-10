"""统一扩展管理 API 的请求/响应/错误 Pydantic 契约（PLAN-DM-020 Task 3）。

与 ARCH-DM-005 之后的既有结构化错误契约一致：``message`` 是迁移窗口兼容
文本，用户呈现一律走稳定 ``message_key`` + 结构化 ``params``（只携带稳定值：
标识/编号/修订号，禁止本地化 label 或完整句子）。扩展域的 ``message_key``
（:data:`EXTENSION_MESSAGE_KEYS`）由 Task 10 的前端 ``extensions`` 域文案承接，
本模块只锁定稳定键名。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from dst_manager.interfaces.contracts import ContractModel

__all__ = [
    "EXTENSION_MESSAGE_KEYS",
    "ArtifactResponseModel",
    "ExtensionActionModel",
    "ExtensionActionRequest",
    "ExtensionDiagnosticCode",
    "ExtensionErrorResponse",
    "ExtensionLifecycleStatus",
    "ExtensionPlatformErrorCode",
    "ExtensionPreferencePutRequest",
    "ExtensionSettingsPutRequest",
    "ExtensionStatePatchRequest",
    "ExtensionSummaryModel",
    "ExtensionUiContributionModel",
    "VersionedValueModel",
]

ExtensionPlatformErrorCode = Literal[
    "EXTENSION_NOT_FOUND",
    "EXTENSION_DISABLED",
    "EXTENSION_INCOMPATIBLE",
    "EXTENSION_CAPABILITY_UNAVAILABLE",
    "EXTENSION_SETTINGS_INVALID",
    "EXTENSION_ACTION_NOT_FOUND",
    "SAVE_GRANT_INVALID",
    "EXPORT_DESTINATION_CHANGED",
    "REPREVIEW_REQUIRED",
    "ARTIFACT_WRITE_FAILED",
]

#: 生命周期状态字面量（与 extensions.contracts.ExtensionDescriptor 一致）。
ExtensionLifecycleStatus = Literal[
    "DISCOVERED",
    "DISABLED",
    "STARTING",
    "AVAILABLE",
    "WAITING_DEPENDENCY",
    "INCOMPATIBLE",
    "FAILED",
    "STOPPING",
    "STOPPED",
]

#: 列表摘要 ``error_code`` 的封闭诊断码词汇（Ruling-7：ARCH §4.3 诊断面只暴露
#: 稳定诊断码，禁止原始异常文本或含路径/敏感值的字符串；错误响应仍用 §12 平台码）。
ExtensionDiagnosticCode = Literal[
    "EXTENSION_MANIFEST_INVALID",
    "EXTENSION_HOST_CONTRACT_MISMATCH",
    "EXTENSION_CAPABILITY_UNKNOWN",
    "EXTENSION_CAPABILITY_UNAVAILABLE",
    "EXTENSION_START_FAILED",
    "EXTENSION_STOP_FAILED",
]

#: 平台错误码 -> 稳定文案键（Task 10 前端 extensions 域逐一对应）。
EXTENSION_MESSAGE_KEYS: dict[str, str] = {
    "EXTENSION_NOT_FOUND": "errors.extension.notFound",
    "EXTENSION_DISABLED": "errors.extension.disabled",
    "EXTENSION_INCOMPATIBLE": "errors.extension.incompatible",
    "EXTENSION_CAPABILITY_UNAVAILABLE": "errors.extension.capabilityUnavailable",
    "EXTENSION_SETTINGS_INVALID": "errors.extension.settingsInvalid",
    "EXTENSION_ACTION_NOT_FOUND": "errors.extension.actionNotFound",
    "SAVE_GRANT_INVALID": "errors.extension.saveGrantInvalid",
    "EXPORT_DESTINATION_CHANGED": "errors.extension.exportDestinationChanged",
    "REPREVIEW_REQUIRED": "errors.extension.repreviewRequired",
    "ARTIFACT_WRITE_FAILED": "errors.extension.artifactWriteFailed",
}


class ExtensionErrorResponse(ContractModel):
    """扩展平台统一错误负载（ARCH-DM-006 §12 平台码）。"""

    code: ExtensionPlatformErrorCode | str
    message_key: str
    params: dict[str, str | int]
    message: str


class ExtensionActionModel(ContractModel):
    action_id: str
    output_kind: Literal["xlsx"] | None = None
    media_type: str | None = None


class ExtensionUiContributionModel(ContractModel):
    contribution_id: str
    kind: str
    route_key: str


class ExtensionSummaryModel(ContractModel):
    extension_id: str
    version: str
    name_key: str
    description_key: str
    status: ExtensionLifecycleStatus
    enabled: bool
    error_code: ExtensionDiagnosticCode | None = None
    actions: list[ExtensionActionModel] = Field(default_factory=list)
    ui_contributions: list[ExtensionUiContributionModel] = Field(default_factory=list)


class ExtensionStatePatchRequest(ContractModel):
    enabled: bool


class VersionedValueModel(ContractModel):
    """设置/偏好统一版本化负载：``revision`` 为扩展自身乐观并发修订。"""

    schema_version: int
    revision: int
    value: dict[str, object]


class ExtensionSettingsPutRequest(ContractModel):
    schema_version: int
    value: dict[str, object]
    expected_revision: int


class ExtensionPreferencePutRequest(ContractModel):
    schema_version: int
    value: dict[str, object]


class ExtensionActionRequest(ContractModel):
    """动作请求占位契约（Task 3 只校验状态与声明；具体请求模型由 Task 6/9 接管）。"""

    payload: dict[str, object] = Field(default_factory=dict)


class ArtifactResponseModel(ContractModel):
    """Artifact 元数据响应：不含任何扩展内部状态或二进制内容。"""

    artifact_id: str
    extension_id: str
    extension_version: str
    workspace_id: str
    source_revision_id: str
    kind: str
    media_type: str
    management_relation: str
    output_path: str
    file_name: str
    size_bytes: int
    sha256: str
    created_at: datetime
