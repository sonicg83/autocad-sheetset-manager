from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from dst_manager.interfaces.contracts import ChangeCommand, RepairStatus


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HealthResponse(ResponseModel):
    status: Literal["ok"]
    run_id: str | None = None


class DiagnosticResponse(ResponseModel):
    code: str
    severity: str
    message: str
    object_id: str | None = None
    location: str | None = None
    line: int | None = None
    index: int | None = None
    property_name: str | None = None


class RepairActionResponse(ResponseModel):
    code: str
    node_path: str
    object_id: str | None = None
    confidence: Literal["deterministic", "inferred"]
    before: dict[str, str | None]
    after: dict[str, str | None]
    message: str


class DstValidationResponse(ResponseModel):
    status: Literal[
        "VALID",
        "REPAIRED",
        "INVALID_REPAIR_REQUIRED",
        "INVALID_UNRECOVERABLE",
    ]
    actions: list[RepairActionResponse] = Field(default_factory=list)
    blocking_issues: list[DiagnosticResponse] = Field(default_factory=list)


class PropertyDefinitionResponse(ResponseModel):
    type: Literal["sheetset", "sheet"]
    name: str
    default_value: str


class LayoutResponse(ResponseModel):
    file_name: str
    relative_file_name: str
    layout_name: str
    handle: str
    resolved_path: str | None = None
    resolution_source: str | None = None


class SheetResponse(ResponseModel):
    id: str
    number: str
    title: str
    custom_properties: dict[str, str]
    layout: LayoutResponse


class SubsetResponse(ResponseModel):
    id: str
    name: str
    title: str
    number_range: str
    display_name: str
    order: int
    sheets: list[SheetResponse]


class SheetSetResponse(ResponseModel):
    database_id: str
    name: str
    custom_properties: dict[str, str]
    property_definitions: list[PropertyDefinitionResponse]
    sheet_count: int
    subset_count: int
    subsets: list[SubsetResponse]


class WorkspaceResponse(ResponseModel):
    id: str
    root: str
    dst_path: str
    revision_id: str
    sheet_set: SheetSetResponse
    diagnostics: list[DiagnosticResponse]
    dst_validation: DstValidationResponse
    unreferenced_dwgs: list[str]


class PlannedLayoutResponse(ResponseModel):
    sheet_id: str
    number: str
    title: str
    custom_properties: dict[str, str]
    source_type: Literal["existing_snapshot", "template_layout"]
    source_file: str
    source_layout: str
    target_layout: str
    original_layout: str | None = None


class CadGroupResponse(ResponseModel):
    subset_id: str
    subset_name: str
    operation: Literal["create", "rebuild"]
    cad_operation: Literal["rename_only", "rebuild"]
    source_target_file: str | None
    source_snapshot: str
    target_file: str
    layouts: list[PlannedLayoutResponse]
    expected_baseline: None = None
    target_reuses_source: bool


class CardinalityFrontierResponse(ResponseModel):
    index: int
    subset_id: str | None


class SubsetOperationResponse(ResponseModel):
    subset_id: str
    cad_operation: Literal["none", "rename_only", "rebuild"]
    target_file: str
    in_cardinality_scope: bool


class DeletedSubsetResponse(ResponseModel):
    subset_id: str
    target_file: str


class PathTransitionResponse(ResponseModel):
    subset_id: str
    operation: Literal["create", "rebuild"]
    source: str | None
    target: str


class PathGraphResponse(ResponseModel):
    old_sources: list[str]
    final_targets: list[str]
    reused_targets: list[str]
    delete_targets: list[str]
    transitions: list[PathTransitionResponse]


class DerivedLayoutResponse(ResponseModel):
    file_name: str
    relative_file_name: str
    layout_name: str
    handle: str
    resolved_path: str | None = None
    resolution_source: str | None = None


class DerivedSheetResponse(ResponseModel):
    acsm_id: str
    number: str
    title: str
    custom_properties: dict[str, str]
    layout: DerivedLayoutResponse


class DerivedSubsetResponse(ResponseModel):
    acsm_id: str
    title: str
    number_range: str
    display_name: str
    source_target_file: str
    target_file: str
    sheets: list[DerivedSheetResponse]


class PropertyDefinitionDiffResponse(ResponseModel):
    added: list[PropertyDefinitionResponse]
    skipped: list[PropertyDefinitionResponse]


class DerivedDocumentResponse(ResponseModel):
    subsets: list[DerivedSubsetResponse]
    affected_subset_ids: list[str]
    property_diff: PropertyDefinitionDiffResponse
    layout_sources: dict[str, dict[str, str]]


class SourceBaselineResponse(ResponseModel):
    path: str
    sha256: str
    identity: list[int]
    source_types: list[Literal["existing_snapshot", "template_layout"]]
    requested_layouts: list[str]


class EstimateDurationResponse(ResponseModel):
    lower: int
    upper: int


class EstimateSourceResponse(ResponseModel):
    cad_operation: Literal["rename_only", "rebuild"]
    sample_count: int
    source: Literal["history", "fallback-v1"]


class ExecutionEstimateResponse(ResponseModel):
    schema_version: Literal[1]
    estimated: Literal[True]
    core_console_count: int
    concurrency: int
    duration_ms: EstimateDurationResponse
    sources: list[EstimateSourceResponse]


class ExecutionIntentResponse(ResponseModel):
    groups: list[CadGroupResponse]
    cardinality_frontier: CardinalityFrontierResponse | None
    subset_operations: list[SubsetOperationResponse]
    deleted_subsets: list[DeletedSubsetResponse]
    path_graph: PathGraphResponse
    affected_subset_ids: list[str]
    derived_document: DerivedDocumentResponse
    source_baselines: list[SourceBaselineResponse] = Field(default_factory=list)
    cad_validation_deferred: bool = False
    expected_file_hashes: dict[str, str | None] = Field(default_factory=dict)
    estimate: ExecutionEstimateResponse | None = None


class StructureSheetResponse(ResponseModel):
    position: int
    id: str
    number: str
    title: str
    suffix: str
    dwg_file: str
    layout_name: str


class StructureSubsetResponse(ResponseModel):
    position: int
    id: str
    title: str
    number_range: str
    display_name: str
    dwg_file: str
    sheets: list[StructureSheetResponse]


class StructureDiffResponse(ResponseModel):
    before: list[StructureSubsetResponse]
    after: list[StructureSubsetResponse]


class SheetSetFieldDiffResponse(ResponseModel):
    field: Literal["name"]
    before: str
    after: str


class PropertyDiffResponse(ResponseModel):
    action: Literal["add", "delete", "update"]
    type: Literal["sheetset", "sheet"]
    name: str
    before: str | PropertyDefinitionResponse | None
    after: str | PropertyDefinitionResponse | None
    affected_sheet_count: int


class DwgLayoutSnapshotResponse(ResponseModel):
    file: str
    layouts: list[str]


class DwgDiffResponse(ResponseModel):
    action: Literal["create", "rebuild", "delete"]
    subset_id: str
    before: DwgLayoutSnapshotResponse | None
    after: DwgLayoutSnapshotResponse | None


class SemanticDiffResponse(ResponseModel):
    sheet_set: list[SheetSetFieldDiffResponse]
    structure: StructureDiffResponse
    properties: list[PropertyDiffResponse]
    dwgs: list[DwgDiffResponse]


class NormalizedUpdateSubsetCommand(ResponseModel):
    type: Literal["update_subset"]
    subset_id: str
    title: str


class NormalizedUpdateSheetCommand(ResponseModel):
    type: Literal["update_sheet"]
    sheet_id: str
    custom_properties: dict[str, str]


class CommandChangeResponse(ResponseModel):
    index: int
    type: Literal[
        "update_sheet_set",
        "update_subset",
        "update_sheet",
        "delete_sheet",
        "insert_sheet",
        "insert_subset",
        "add_custom_property",
        "delete_custom_property",
        "delete_subset",
    ]
    object_id: str | None = None
    after: ChangeCommand | NormalizedUpdateSubsetCommand | NormalizedUpdateSheetCommand
    affected_sheet_count: int | None = None


class PropertyCsvChangeResponse(ResponseModel):
    line: int
    action: Literal["add", "skip", "conflict"]
    type: Literal["sheetset", "sheet"]
    name: str
    default_value: str
    affected_sheet_count: int


class ChangePreviewResponse(ResponseModel):
    workspace_id: str
    base_revision_id: str
    cad_version: Literal["2016", "2020"]
    requires_cad: bool
    affected_files: list[str]
    execution_intent: ExecutionIntentResponse | None = None
    semantic_diff: SemanticDiffResponse
    preview_digest: str
    changes: list[CommandChangeResponse | PropertyCsvChangeResponse]
    commands: list[ChangeCommand] | None = None
    diagnostics: list[DiagnosticResponse]
    executable: bool


class JobFileResponse(ResponseModel):
    target_path: str
    source_path: str | None = None
    cad_operation: str | None = None
    status: str
    progress: int
    duration_ms: int | None = None
    peak_memory_bytes: int | None = None
    staging_bytes: int | None = None
    log_path: str | None = None
    log_summary: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    before_hash: str | None = None
    result_hash: str | None = None
    role: str | None = None


class JobSummaryResponse(ResponseModel):
    total: int
    succeeded: int
    failed: int
    duration_ms: int


class JobResponse(ResponseModel):
    id: str | None
    workspace_id: str
    status: str
    progress: int | None = None
    type: str | None = None
    cad_version: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    worker_id: str | None = None
    attempt: int | None = None
    started_at: str | None = None
    heartbeat_at: str | None = None
    finished_at: str | None = None
    payload: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    files: list[JobFileResponse] = Field(default_factory=list)
    summary: JobSummaryResponse | None = None
    suggestion: str | None = None
    revision_id: str | None = None
    no_op: bool | None = None


class RevisionResponse(ResponseModel):
    id: str
    workspace_id: str
    operation_id: str
    before_hash: str
    result_hash: str
    revision_dir: str
    created_at: str


class RevisionListResponse(RootModel[list[RevisionResponse]]):
    pass


class RestoreFileResponse(ResponseModel):
    path: str
    action: Literal["replace", "delete"]
    current_hash: str | None = None
    expected_hash: str | None = None
    restore_hash: str | None = None
    backup_hash: str | None = None
    backup_identity: list[int] | None = None
    source_conflict: bool
    conflict: bool


class RestorePreviewResponse(ResponseModel):
    workspace_id: str
    revision_id: str
    base_revision_id: str
    files: list[RestoreFileResponse]
    conflicts: list[str]
    executable: bool
    preview_digest: str


class XmlPreviewResponse(ResponseModel):
    workspace_id: str
    base_revision_id: str
    sheet_count_before: int
    sheet_count_after: int
    subset_count_before: int
    subset_count_after: int
    changes: list[dict[str, Any]]
    diagnostics: list[DiagnosticResponse]
    destination_revision_id: str | None = None
    preview_digest: str
    executable: bool


class RepairPreviewResponse(ResponseModel):
    workspace_id: str
    base_revision_id: str
    status: Literal[
        "VALID",
        "REPAIRED",
        "INVALID_REPAIR_REQUIRED",
        "INVALID_UNRECOVERABLE",
    ]
    actions: list[RepairActionResponse]
    blocking_issues: list[DiagnosticResponse]
    preview_digest: str | None = None
    executable: bool


class CadCapabilityResponse(ResponseModel):
    version: str
    available: bool
    console: str | None = None
    plugin: str | None = None


class CadCapabilitiesResponse(RootModel[dict[str, CadCapabilityResponse]]):
    pass


class TemplateLayoutResponse(ResponseModel):
    name: str
    handle: str


class TemplateInspectResponse(ResponseModel):
    path: str
    sha256: str
    cad_version: str
    layouts: list[TemplateLayoutResponse]


class DraftActionResponse(ResponseModel):
    id: str
    kind: Literal["command_batch"]
    label: str
    commands: list[ChangeCommand]


class DraftDocumentResponse(ResponseModel):
    schema_version: Literal[1]
    workspace_id: str
    base_revision_id: str
    repair_status: RepairStatus
    version: int
    cursor: int
    actions: list[DraftActionResponse]


class DraftEnvelopeResponse(ResponseModel):
    draft: DraftDocumentResponse | None
    corrupted: bool
    stale: bool
    stale_reasons: list[str]


class DraftDeleteResponse(ResponseModel):
    deleted: bool


class LayoutNamesResponse(ResponseModel):
    layouts: list[str]
    cached: bool
    file_hash: str
