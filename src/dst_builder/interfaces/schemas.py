"""Builder HTTP 契约模型（Pydantic）：请求/响应载荷，不承载领域规则。

字段级业务校验一律由领域层 ``validate_draft`` 完成；此处只固化 JSON 形态
（字段名、类型、schema_version 字面量、未知字段拒绝）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AssetInspectRequest",
    "AssetInspectionResponse",
    "AssetIntakeRequest",
    "AssetModel",
    "CadCapabilitiesResponse",
    "CadCapabilityModel",
    "DiagnosticModel",
    "DraftFieldsModel",
    "DraftPatchRequest",
    "NumberingFieldsModel",
    "ProjectCreateRequest",
    "ProjectFieldsModel",
    "ProjectModel",
    "ProjectStateResponse",
    "SheetFieldsModel",
    "TemplateFieldsModel",
]


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreateRequest(_ContractModel):
    """POST /api/projects 请求。``project_root`` 仅在应用工厂未绑定根目录时必填。"""

    project_root: str | None = None
    name: str
    stage: str
    discipline: str
    output_path: str


class ProjectFieldsModel(_ContractModel):
    name: str
    stage: str
    discipline: str
    output_path: str


class NumberingFieldsModel(_ContractModel):
    prefix: str
    start: int
    width: int


class SheetFieldsModel(_ContractModel):
    title: str


class TemplateFieldsModel(_ContractModel):
    base_asset_id: str
    layout_asset_id: str
    source_layout: str


class DraftFieldsModel(_ContractModel):
    """§4 DraftProjectV1 JSON 形态（PATCH 载荷的解析与校验目标）。"""

    schema_version: Literal[1] = 1
    project: ProjectFieldsModel
    numbering: NumberingFieldsModel
    cad_version: str
    sheets: list[SheetFieldsModel]
    template: TemplateFieldsModel


class DraftPatchRequest(_ContractModel):
    """PATCH /api/projects/current/draft 请求：base_updated_at 乐观并发。"""

    base_updated_at: str
    draft: DraftFieldsModel
    wizard_step: int = Field(ge=1, le=7)
    focused_field: str | None = None


class ProjectModel(_ContractModel):
    id: str
    name: str
    stage: str
    discipline: str
    output_path: str
    created_at: str
    updated_at: str


class DiagnosticModel(_ContractModel):
    code: str
    severity: str
    message: str
    field: str | None = None


class ProjectStateResponse(_ContractModel):
    """GET /api/projects/current 与 PATCH /api/projects/current/draft 响应。"""

    project: ProjectModel
    draft: DraftFieldsModel
    wizard_step: int
    focused_field: str | None
    updated_at: str
    diagnostics: list[DiagnosticModel]


class AssetIntakeRequest(_ContractModel):
    """POST /api/assets 请求：纳入一个本机源文件（ Builder 为本地应用，
    源文件经路径引用而非 HTTP 上传，避免 2 GiB 文件流经接口层）。"""

    role: Literal["base", "layout"]
    source_path: str


class AssetModel(_ContractModel):
    """纳入结果：内容寻址相对路径与固定哈希（§3 assets 表投影）。"""

    id: str
    role: str
    relative_path: str
    sha256: str
    size: int
    source_name: str


class AssetInspectRequest(_ContractModel):
    """POST /api/assets/{id}/inspect 请求：指定匹配版本的 CAD。"""

    cad_version: Literal["2016", "2020"]


class AssetInspectionResponse(_ContractModel):
    """布局 inspection 结果；端口未接线时端点返回 501 错误负载。"""

    asset_id: str
    cad_version: str
    layouts: list[str]


class CadCapabilityModel(_ContractModel):
    """单个 CAD 版本的只读能力探测结果。"""

    cad_version: str
    available: bool
    console_path: str | None = None
    plugin_path: str | None = None
    unavailable_reason: str | None = None


class CadCapabilitiesResponse(_ContractModel):
    """GET /api/cadabilities 响应：两个受支持版本的探测结果。"""

    capabilities: list[CadCapabilityModel]
