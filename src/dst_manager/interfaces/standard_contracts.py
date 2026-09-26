"""标准管理 API 契约（PLAN-DM-035 Task 6）。

只承载请求/响应的 Pydantic 模型；标准文档本身是自由 dict，Schema 校验由
领域解析器在应用层完成（错误以 ``STANDARD_*`` 稳定码返回 422）。
"""

from pydantic import Field

from dst_manager.interfaces.contracts import ContractModel


class StandardDiagnosticModel(ContractModel):
    code: str
    severity: str
    message: str
    #: 诊断定位：属性 ID 与令牌片段序号，供发布检查跳转并聚焦。
    property_id: str | None = None
    segment_index: int | None = None


class StandardSummaryModel(ContractModel):
    source: str
    status: str
    standard_id: str
    #: 草稿为 ``None``，已发布为服务端分配的整数版本（PLAN-DM-041 Task 2）。
    version: int | None = None
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
    version: int
    name: str
    #: 发布检查诊断：成功发布时只可能包含 warning（error 已转 422）。
    diagnostics: list[StandardDiagnosticModel] = Field(default_factory=list)


class StandardPathRequest(ContractModel):
    """本机路径请求（标准包导入预检与 DST 导入共用）。"""

    path: str


class StandardImportPreviewRequest(ContractModel):
    """导入预检：只接受本机 ``.dststandard`` 路径；服务端复制到限时快照。"""

    path: str


class StandardImportConfirmRequest(ContractModel):
    """确认导入：只接受预检凭证，不再接受路径（SPEC-DM-019 §4.1）。"""

    preview_id: str


class StandardExistingVersionModel(ContractModel):
    """同 ID 在官方/用户库中已有的整数发布版本。"""

    source: str
    version: int


class StandardImportPreviewResponse(ContractModel):
    """预检结果：候选身份、已有版本、诊断与可否导入。

    身份/名称冲突时 ``can_import`` 为 ``false`` 且 ``preview_id``/``expires_at`` 为空；
    包或路径非法则直接 422。
    """

    preview_id: str | None = None
    expires_at: str | None = None
    standard_id: str
    version: int
    name: str
    supported_cad_versions: list[str] = Field(default_factory=list)
    existing_versions: list[StandardExistingVersionModel] = Field(default_factory=list)
    diagnostics: list[StandardDiagnosticModel] = Field(default_factory=list)
    can_import: bool


class StandardDstImportRequest(ContractModel):
    dst_path: str


class StandardDependencyModel(ContractModel):
    extension_id: str
    capability_id: str
    min_version: str


class StandardDetailResponse(ContractModel):
    standard_id: str
    version: int
    name: str
    supported_cad_versions: list[str]
    dependencies: list[StandardDependencyModel]
    #: 完整标准文档（派生草稿等场景需要）；与身份字段冗余但保持契约自洽。
    document: dict[str, object]


class StandardAssetInspectRequest(ContractModel):
    cad_version: str


class StandardAssetCopyRequest(ContractModel):
    """本机模板来源：用户显式选择或本地开发态显式输入的绝对路径。

    ``cad_version`` 非空时，复制成功后服务端读取受控副本布局（PLAN-DM-042）。
    """

    source_path: str
    cad_version: str = ""


class StandardAssetCopyResponse(ContractModel):
    """受控副本的包内相对路径与（按需读取的）布局清单。

    ``layouts_error`` 是布局读取失败的稳定码（如 ``STANDARD_LAYOUT_READ_FAILED``），
    不影响复制结果；未请求读取时为 ``None``。
    """

    path: str
    layouts: list[str] = Field(default_factory=list)
    layouts_error: str | None = None


class AssetInspectionResponse(ContractModel):
    asset_id: str
    kind: str
    layouts: list[str]
    diagnostics: list[StandardDiagnosticModel]
