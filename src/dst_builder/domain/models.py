"""DST Builder 领域模型（SPEC-DB-001 V1 契约，冻结 dataclass + StrEnum）。

只承载纯数据与固定契约常量；校验与派生逻辑在 ``planning`` / ``normalization`` /
``build_state``。模型中的资产路径一律是项目内 POSIX 相对路径；``output_path``
等本机绝对位置只出现在草稿输入与 application/infrastructure 边界，不进入
修订与计划的规范化载荷（由 ``BuildRun`` 单独快照）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dst_builder.domain.build_state import BuildStatus

__all__ = [
    "DRAFT_SCHEMA_VERSION",
    "HANDOFF_SCHEMA",
    "MANIFEST_SCHEMA",
    "RULESET_VERSION",
    "VALIDATION_REPORT_SCHEMA",
    "WORKER_COMMAND_NAME",
    "AssetRole",
    "AssetSnapshot",
    "BuildEventV1",
    "Diagnostic",
    "DiagnosticSeverity",
    "DraftProjectV1",
    "DrawingTask",
    "ExpectedArtifact",
    "GenerationPlanV1",
    "NumberingInput",
    "ProjectInput",
    "ProjectRevisionV1",
    "RevisionProject",
    "SheetInput",
    "SheetsetTask",
    "TemplateInput",
]

DRAFT_SCHEMA_VERSION = 1
RULESET_VERSION = 1
WORKER_COMMAND_NAME = "DSTBUILDER_CREATE_DRAWING"

# SPEC-DB-001 §9 固定 Schema 名与固定引用路径（manifest/handoff 最终字节在 Task 9 生成）。
MANIFEST_SCHEMA = "dst-builder.manifest/v1"
VALIDATION_REPORT_SCHEMA = "dst-builder.validation-report/v1"
HANDOFF_SCHEMA = "dst-builder.handoff/v1"

# 诊断码只使用 §11 固定错误码；§4 字段级违规统一归入 DRAFT_FIELD_INVALID，
# 由 ``field`` 属性区分具体字段（PATCH 草稿返回字段诊断时按字段聚焦）。
PROJECT_PATH_INVALID = "PROJECT_PATH_INVALID"
PACKAGE_TARGET_EXISTS = "PACKAGE_TARGET_EXISTS"
PLAN_STALE = "PLAN_STALE"
DRAFT_FIELD_INVALID = "DRAFT_FIELD_INVALID"


class DiagnosticSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: DiagnosticSeverity
    message: str
    field: str | None = None


class AssetRole(StrEnum):
    BASE = "base"
    LAYOUT = "layout"


@dataclass(frozen=True, slots=True)
class AssetSnapshot:
    """项目内资产的内容寻址快照（路径为项目内 POSIX 相对路径）。"""

    role: AssetRole
    relative_path: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class ProjectInput:
    name: str
    stage: str
    discipline: str
    output_path: str


@dataclass(frozen=True, slots=True)
class NumberingInput:
    prefix: str
    start: int
    width: int


@dataclass(frozen=True, slots=True)
class SheetInput:
    title: str


@dataclass(frozen=True, slots=True)
class TemplateInput:
    base_asset_id: str
    layout_asset_id: str
    source_layout: str


@dataclass(frozen=True, slots=True)
class DraftProjectV1:
    """内部草稿：允许携带未完成/非法字段（草稿防抖保存），由 ``validate_draft`` 评估。"""

    project: ProjectInput
    numbering: NumberingInput
    cad_version: str
    sheets: tuple[SheetInput, ...]
    template: TemplateInput
    schema_version: int = DRAFT_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class RevisionProject:
    """修订内的工程字段：刻意不含 ``output_path``（不入哈希，由 BuildRun 单独快照）。"""

    name: str
    stage: str
    discipline: str


@dataclass(frozen=True, slots=True)
class ProjectRevisionV1:
    schema_version: int
    ruleset_version: int
    project: RevisionProject
    numbering: NumberingInput
    cad_version: str
    sheets: tuple[SheetInput, ...]
    template: TemplateInput
    assets: tuple[AssetSnapshot, ...]
    revision_sha256: str
    revision_id: str


@dataclass(frozen=True, slots=True)
class ExpectedArtifact:
    """正式成果中的预期文件（成果包内 POSIX 相对路径）。"""

    path: str
    role: str
    required: bool


@dataclass(frozen=True, slots=True)
class DrawingTask:
    task_id: str
    base_asset: AssetSnapshot
    layout_asset: AssetSnapshot
    source_layout: str
    target_layout: str
    target_dwg_path: str


@dataclass(frozen=True, slots=True)
class SheetsetTask:
    dst_path: str
    sheetset_name: str
    subset_name: str
    sheet_number: str
    sheet_title: str
    dwg_path: str  # DST 内的 DWG 引用只保存 dwg_name（同目录）
    layout_name: str


@dataclass(frozen=True, slots=True)
class GenerationPlanV1:
    schema_version: int
    ruleset_version: int
    revision_id: str
    revision_sha256: str
    cad_version: str
    worker_command: str
    drawing_task: DrawingTask
    sheetset_task: SheetsetTask
    expected_artifacts: tuple[ExpectedArtifact, ...]
    diagnostics: tuple[Diagnostic, ...]
    plan_sha256: str
    plan_id: str


@dataclass(frozen=True, slots=True)
class BuildEventV1:
    """构建事件：``sequence`` 单调递增，``progress`` 限定 0～100。"""

    schema_version: int
    sequence: int
    status: BuildStatus
    progress: int
    message_key: str
    artifact_path: str | None = None
    error_code: str | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("构建事件 sequence 必须从 1 开始单调递增")
        if not 0 <= self.progress <= 100:
            raise ValueError("构建事件 progress 必须在 0～100 之间")
