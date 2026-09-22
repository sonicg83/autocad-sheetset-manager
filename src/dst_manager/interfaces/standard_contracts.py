"""标准管理 API 契约（PLAN-DM-035 Task 6）。

只承载请求/响应的 Pydantic 模型；标准文档本身是自由 dict，Schema 校验由
领域解析器在应用层完成（错误以 ``STANDARD_*`` 稳定码返回 422）。
"""

from pydantic import Field

from dst_manager.interfaces.contracts import ContractModel


class StandardSummaryModel(ContractModel):
    source: str
    status: str
    standard_id: str
    version: str
    name: str
    draft_id: str | None = None


class StandardDocumentRequest(ContractModel):
    document: dict[str, object]


class StandardDraftRequest(ContractModel):
    draft_id: str | None = None
    document: dict[str, object]


class StandardDraftResponse(ContractModel):
    draft_id: str
    document: dict[str, object]


class ImportedStandardDraftResponse(StandardDraftResponse):
    """DST 导入草稿；两个恒空列表证明不复制子集/图纸/外部引用。"""

    subsets: list[str] = Field(default_factory=list)
    external_paths: list[str] = Field(default_factory=list)


class StandardPublishResponse(ContractModel):
    standard_id: str
    version: str
    name: str


class StandardPathRequest(ContractModel):
    path: str


class StandardDstImportRequest(ContractModel):
    dst_path: str


class StandardDependencyModel(ContractModel):
    extension_id: str
    capability_id: str
    min_version: str


class StandardDetailResponse(ContractModel):
    standard_id: str
    version: str
    name: str
    supported_cad_versions: list[str]
    dependencies: list[StandardDependencyModel]


class StandardAssetInspectRequest(ContractModel):
    cad_version: str


class StandardDiagnosticModel(ContractModel):
    code: str
    severity: str
    message: str


class AssetInspectionResponse(ContractModel):
    asset_id: str
    kind: str
    layouts: list[str]
    diagnostics: list[StandardDiagnosticModel]
