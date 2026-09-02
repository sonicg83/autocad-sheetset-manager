from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dst_manager.domain.text_validation import (
    normalize_derived_name,
    normalize_property_name,
    validate_absolute_source_file,
    validate_custom_properties,
    validate_sheet_set_name,
    validate_xml_text,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LayoutSource(ContractModel):
    type: Literal["existing_snapshot", "template_layout"]
    file: str = Field(min_length=1)
    layout: str = Field(min_length=1)

    @field_validator("file")
    @classmethod
    def validate_absolute_file(cls, value: str) -> str:
        return validate_absolute_source_file(value)

    @field_validator("layout")
    @classmethod
    def validate_layout_name(cls, value: str) -> str:
        return normalize_derived_name(value, "布局名称")


class UpdateSheetSetCommand(ContractModel):
    type: Literal["update_sheet_set"]
    name: str | None = None
    custom_properties: dict[str, str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return validate_sheet_set_name(value) if value is not None else None

    @field_validator("custom_properties")
    @classmethod
    def validate_properties(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return validate_custom_properties(value) if value is not None else None


class UpdateSubsetTitleCommand(ContractModel):
    type: Literal["update_subset_title"]
    subset_id: str = Field(min_length=1)
    title: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return normalize_derived_name(value, "子集标题")


class UpdateSheetPropertiesCommand(ContractModel):
    type: Literal["update_sheet_properties"]
    sheet_id: str = Field(min_length=1)
    custom_properties: dict[str, str]

    @field_validator("custom_properties")
    @classmethod
    def validate_properties(cls, value: dict[str, str]) -> dict[str, str]:
        return validate_custom_properties(value)


class DeleteSheetCommand(ContractModel):
    type: Literal["delete_sheet"]
    sheet_id: str = Field(min_length=1)


class InsertSheetCommand(ContractModel):
    type: Literal["insert_sheet"]
    target_subset_id: str = Field(min_length=1)
    ordinal: int | None = Field(default=None, ge=1)
    placement: Literal["before", "after"] = "after"
    count: int = Field(default=1, ge=1)
    source: LayoutSource


class InsertSubsetCommand(ContractModel):
    type: Literal["insert_subset"]
    ordinal: int | None = Field(default=None, ge=1)
    placement: Literal["before", "after"] = "after"
    title: str = Field(min_length=1)
    initial_sheet_count: int = Field(default=1, ge=1)
    source: LayoutSource

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return normalize_derived_name(value, "子集标题")


class AddCustomPropertyCommand(ContractModel):
    type: Literal["add_custom_property"]
    property_type: Literal["sheetset", "sheet"]
    name: str = Field(min_length=1)
    default_value: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_property_name(value)

    @field_validator("default_value")
    @classmethod
    def validate_default_value(cls, value: str) -> str:
        return validate_xml_text(value)


class DeleteCustomPropertyCommand(ContractModel):
    type: Literal["delete_custom_property"]
    property_type: Literal["sheetset", "sheet"]
    name: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_property_name(value)


class DeleteSubsetCommand(ContractModel):
    type: Literal["delete_subset"]
    subset_id: str = Field(min_length=1)
    confirm_delete_all_sheets: Literal[True]
    confirm_delete_main_dwg: Literal[True]


ChangeCommand = Annotated[
    UpdateSheetSetCommand
    | UpdateSubsetTitleCommand
    | UpdateSheetPropertiesCommand
    | DeleteSheetCommand
    | InsertSheetCommand
    | InsertSubsetCommand
    | AddCustomPropertyCommand
    | DeleteCustomPropertyCommand
    | DeleteSubsetCommand,
    Field(discriminator="type"),
]


class ChangePreviewRequest(ContractModel):
    base_revision_id: str = Field(min_length=1)
    commands: list[ChangeCommand] = Field(default_factory=list)
    cad_version: Literal["2016", "2020"] = "2020"

    def command_payloads(self) -> list[dict[str, object]]:
        return [command.model_dump(mode="json", exclude_none=True) for command in self.commands]


class ChangeExecuteRequest(ChangePreviewRequest):
    preview_digest: str = Field(min_length=1)


class PropertyCsvPreviewRequest(ContractModel):
    base_revision_id: str = Field(min_length=1)
    csv: str


class PropertyCsvExecuteRequest(PropertyCsvPreviewRequest):
    preview_digest: str = Field(min_length=1)


class XmlPreviewRequest(ContractModel):
    base_revision_id: str = Field(min_length=1)
    xml: str
    destination: Path | None = None


class XmlExecuteRequest(XmlPreviewRequest):
    destination: Path
    destination_revision_id: str | None = None
    preview_digest: str = Field(min_length=1)


class RepairPreviewRequest(ContractModel):
    base_revision_id: str = Field(min_length=1)


class RepairExecuteRequest(RepairPreviewRequest):
    preview_digest: str = Field(min_length=1)


class RestoreRevisionExecuteRequest(ContractModel):
    base_revision_id: str = Field(min_length=1)
    preview_digest: str = Field(min_length=1)


RepairStatus = Literal[
    "VALID",
    "REPAIRED",
    "INVALID_REPAIR_REQUIRED",
    "INVALID_UNRECOVERABLE",
]


class DraftAction(ContractModel):
    id: str = Field(min_length=1)
    kind: Literal["command_batch"]
    label: str = Field(min_length=1)
    commands: list[ChangeCommand] = Field(min_length=1)


class DraftPutRequest(ContractModel):
    schema_version: Literal[1] = 1
    base_revision_id: str = Field(min_length=1)
    repair_status: RepairStatus
    expected_version: int = Field(ge=0)
    cursor: int = Field(ge=0)
    actions: list[DraftAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_cursor(self):
        if self.cursor > len(self.actions):
            raise ValueError("cursor 不得超过动作数量")
        return self


class DraftDeleteRequest(ContractModel):
    expected_version: int = Field(ge=0)


class LayoutNamesRequest(ContractModel):
    file_path: Path
    cad_version: Literal["2016", "2020"] = "2020"
