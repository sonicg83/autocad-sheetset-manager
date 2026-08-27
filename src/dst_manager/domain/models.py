from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class JobStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    STAGING = "STAGING"
    CAD_RUNNING = "CAD_RUNNING"
    VERIFYING = "VERIFYING"
    PREPARED = "PREPARED"
    PUBLISHING = "PUBLISHING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED_FILE_LOCK = "BLOCKED_FILE_LOCK"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(slots=True)
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    object_id: str | None = None
    location: str | None = None


RepairStatus = Literal[
    "VALID",
    "REPAIRED",
    "INVALID_REPAIR_REQUIRED",
    "INVALID_UNRECOVERABLE",
]

RepairConfidence = Literal["deterministic", "inferred"]


@dataclass(frozen=True, slots=True)
class RepairAction:
    """一次可审计的内存修复动作。

    记录节点路径、对象 ID、修复前后属性差异、置信度、错误码和中文说明。
    属性值与修复器都不写文件，只描述可复现的 DOM 修复。
    """

    code: str
    node_path: str
    object_id: str | None
    confidence: RepairConfidence
    before: dict[str, str | None]
    after: dict[str, str | None]
    message: str


@dataclass(frozen=True, slots=True)
class RepairReport:
    """可修复加载的诊断结果。

    - `VALID`：无需修复，无阻断问题；
    - `REPAIRED`：已应用确定性/推断修复且修复后通过校验，等待用户确认持久化；
    - `INVALID_REPAIR_REQUIRED`：存在需用户补充信息或决策的阻断问题
      （缺业务值、布局缺失/冲突、属性作用域冲突等），不自动覆盖原值；
    - `INVALID_UNRECOVERABLE`：存在结构性不可恢复问题
      （重复/格式非法 ID、XML 语法/根节点错误、非空错误固定值等），禁止发布。
    """

    status: RepairStatus
    actions: tuple[RepairAction, ...] = ()
    blocking_issues: tuple[ValidationIssue, ...] = ()


@dataclass(slots=True)
class LayoutReference:
    file_name: str
    relative_file_name: str
    layout_name: str
    handle: str
    resolved_path: Path | None = None
    resolution_source: str | None = None


@dataclass(slots=True)
class Sheet:
    acsm_id: str
    number: str
    title: str
    layout: LayoutReference
    custom_properties: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Subset:
    acsm_id: str
    name: str
    order: int
    sheets: list[Sheet] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CustomPropertyDefinition:
    type: Literal["sheetset", "sheet"]
    name: str
    default_value: str


@dataclass(frozen=True, slots=True)
class SuffixOptions:
    enabled: bool
    suffix_type: Literal[1, 2]


@dataclass(frozen=True, slots=True)
class PropertyDefinitionDiff:
    added: list[CustomPropertyDefinition] = field(default_factory=list)
    skipped: list[CustomPropertyDefinition] = field(default_factory=list)


@dataclass(slots=True)
class DerivedSubset:
    acsm_id: str
    title: str
    number_range: str
    display_name: str
    sheets: list[Sheet]
    source_target_file: str = ""
    target_file: str = ""


@dataclass(slots=True)
class DerivedDocument:
    subsets: list[DerivedSubset]
    affected_subset_ids: list[str]
    property_diff: PropertyDefinitionDiff = field(default_factory=PropertyDefinitionDiff)
    layout_sources: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(slots=True)
class SheetSetDocument:
    database_id: str
    name: str
    subsets: list[Subset]
    custom_properties: dict[str, str] = field(default_factory=dict)
    diagnostics: list[ValidationIssue] = field(default_factory=list)
    sheet_property_definitions: list[str] = field(default_factory=list)
    repair_report: RepairReport | None = None

    @property
    def sheets(self) -> list[Sheet]:
        return [sheet for subset in self.subsets for sheet in subset.sheets]


@dataclass(slots=True)
class Workspace:
    id: str
    root: Path
    dst_path: Path
    revision_id: str
    document: SheetSetDocument
    unreferenced_dwgs: list[Path] = field(default_factory=list)
