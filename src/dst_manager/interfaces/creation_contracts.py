"""创建草稿、XLSX 与权威预览 API 契约（PLAN-DM-036 Task 4）。

只承载请求/响应 Pydantic 模型：草稿输入形状、标准候选、预览按组表格与逐张
属性明细、导入拒绝体。可输入字段判定、资产解析、编号与 DWG 命名派生全部在
应用层与领域层完成，本模块不做任何规则判定；``step`` 白名单直接复用领域常量，
不复制第二份阶段枚举。
"""

from pydantic import Field, field_validator

from dst_manager.domain.creation import CREATION_STEPS
from dst_manager.interfaces.contracts import ContractModel
from dst_manager.interfaces.error_contracts import ParamValue

__all__ = [
    "CreationAssetOptionModel",
    "CreationDraftCreateRequest",
    "CreationDraftResponse",
    "CreationDraftSaveRequest",
    "CreationGroupModel",
    "CreationImportDiagnosticModel",
    "CreationImportRejectedResponse",
    "CreationNumberingModel",
    "CreationPreviewDiagnosticModel",
    "CreationPreviewGroupModel",
    "CreationPreviewPropertyCellModel",
    "CreationPreviewPropertyRowModel",
    "CreationPreviewResponse",
    "CreationPreviewSheetModel",
    "CreationStandardCandidateModel",
    "CreationSuffixModel",
]


class CreationAssetOptionModel(ContractModel):
    """标准包内的一个受控模板资产候选（``label`` 同类内唯一）。"""

    asset_id: str
    kind: str
    label: str
    layouts: list[str] = Field(default_factory=list)


class CreationStandardCandidateModel(ContractModel):
    """创建标准候选；不可用时 ``reasons`` 说明为什么不能选。"""

    standard_id: str
    version: str
    name: str
    supported_cad_versions: list[str] = Field(default_factory=list)
    available: bool
    reasons: list[str] = Field(default_factory=list)
    asset_options: list[CreationAssetOptionModel] = Field(default_factory=list)


class CreationGroupModel(ContractModel):
    """一个图纸组的输入/存储形状；``sheet_values`` 只含可输入普通 sheet 属性。"""

    group_id: str
    created_order: int = Field(ge=0)
    title: str
    count: int = Field(ge=0)
    base_asset_id: str
    layout_asset_id: str
    paper_layout: str
    sheet_values: dict[str, str] = Field(default_factory=dict)


class CreationDraftCreateRequest(ContractModel):
    """按已发布标准身份建草稿；版本在这里固定，此后不可改写。"""

    standard_id: str
    version: str


class CreationDraftSaveRequest(ContractModel):
    """草稿输入全量保存；``expected_revision`` 为乐观修订门禁。"""

    expected_revision: int = Field(ge=1)
    step: str
    target_path: str
    sheetset_values: dict[str, str] = Field(default_factory=dict)
    groups: list[CreationGroupModel] = Field(default_factory=list)

    @field_validator("step")
    @classmethod
    def validate_step(cls, value: str) -> str:
        if value not in CREATION_STEPS:
            raise ValueError(
                f"CREATION_DRAFT_INVALID: 草稿阶段 {value!r} 不在 {list(CREATION_STEPS)} 内"
            )
        return value


class CreationDraftResponse(ContractModel):
    """草稿当前状态；``revision`` 每次保存递增并使旧预览失效。"""

    id: str
    standard_id: str
    standard_version: str
    revision: int
    step: str
    target_path: str
    sheetset_values: dict[str, str] = Field(default_factory=dict)
    groups: list[CreationGroupModel] = Field(default_factory=list)


class CreationPreviewDiagnosticModel(ContractModel):
    """一条创建预览诊断：稳定错误码 + 可定位的图纸组/属性。"""

    code: str
    message: str
    severity: str
    group_id: str = ""
    property_id: str = ""


class CreationPreviewPropertyRowModel(ContractModel):
    """逐张属性明细的一行：图号 + 该张实际值。"""

    number: str
    value: str


class CreationPreviewPropertyCellModel(ContractModel):
    """一个属性的按组投影：首张实际值 + 完整逐张明细（供「…」模态）。"""

    property_id: str
    first_value: str
    sheets: list[CreationPreviewPropertyRowModel] = Field(default_factory=list)


class CreationPreviewSheetModel(ContractModel):
    """一张展开后的图纸：最终图号/标题/布局名与该张全部属性值。"""

    number: str
    title: str
    layout_name: str
    values: dict[str, str] = Field(default_factory=dict)


class CreationPreviewGroupModel(ContractModel):
    """预览主表一行（一个图纸组一个主 DWG）。"""

    group_id: str
    created_order: int
    title: str
    number_range: str
    title_range: str
    base_template: str
    layout_template: str
    paper_layout: str
    dwg_name: str
    target_path: str
    sheet_count: int
    sheets: list[CreationPreviewSheetModel] = Field(default_factory=list)
    property_cells: dict[str, CreationPreviewPropertyCellModel] = Field(default_factory=dict)


class CreationNumberingModel(ContractModel):
    """当前标准的编号策略摘要。"""

    sequence_field: str
    digits: int
    start: int


class CreationSuffixModel(ContractModel):
    """当前有效设置里的标题后缀与不编号关键字。"""

    enabled: bool
    suffix_type: int
    unnumbered_keywords: list[str] = Field(default_factory=list)


class CreationPreviewResponse(ContractModel):
    """权威预览：按组表格数据、逐张属性明细、定位诊断与 ``preview_digest``。"""

    draft_id: str
    revision: int
    standard_id: str
    standard_version: str
    standard_name: str
    target_path: str
    sheetset_values: dict[str, str] = Field(default_factory=dict)
    group_count: int
    sheet_count: int
    dwg_count: int
    numbering: CreationNumberingModel
    suffix: CreationSuffixModel
    diagnostics: list[CreationPreviewDiagnosticModel] = Field(default_factory=list)
    groups: list[CreationPreviewGroupModel] = Field(default_factory=list)
    executable: bool
    preview_digest: str


class CreationImportDiagnosticModel(ContractModel):
    """一条导入诊断：稳定错误码 + 工作表/行/列定位。"""

    code: str
    message: str
    sheet: str = ""
    row: int | None = None
    column: str | None = None


class CreationImportRejectedResponse(ContractModel):
    """导入被拒（422）响应体：统一错误负载 + 可定位的逐条诊断。

    草稿 JSON 与修订号在拒绝时零变化，调用方可直接修正工作簿后重试。
    """

    code: str
    message_key: str | None = None
    params: dict[str, ParamValue] = Field(default_factory=dict)
    message: str
    diagnostics: list[CreationImportDiagnosticModel] = Field(default_factory=list)
