"""Builder HTTP 契约模型（Pydantic）：请求/响应载荷，不承载领域规则。

字段级业务校验一律由领域层 ``validate_draft`` 完成；此处只固化 JSON 形态
（字段名、类型、schema_version 字面量、未知字段拒绝）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
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
