"""双工作表创建模板的协议：常量、值类型、规范计划与隐藏技术表记录。

模板形状只有两张**可见**表：``SheetSet``（A 列属性名、B 列输入值，另含固定
「项目保存路径」行）与 ``Sheet``（第一行固定表头 + 每行一个图纸组）。隐藏技术表
``_CreationMeta`` 保存模板版本、精确标准身份、各可见列的稳定 ``property_id``/协议
键与资产 ``asset_id``；隐藏表 ``_CreationLists`` 只放 Data Validation 候选值，因此
候选值可以含逗号而不必转义。可见表不出现派生属性列、内部 ID 或任何公式。

``creation_template_plan`` 给出模板的**规范形状**，生成端
（:mod:`dst_manager.infrastructure.creation_xlsx_template`）与解析端
（:mod:`dst_manager.application.creation_import`）共用同一份计划，避免协议漂移；
``creation_metadata_records`` 给出隐藏技术表的规范记录序列。``CreationWorkbookView``
是回读快照（:mod:`dst_manager.infrastructure.creation_xlsx_read`）与解析端之间的
接口，本模块只定义形状，不做任何协议判定。
"""

from __future__ import annotations

from dataclasses import dataclass

from openpyxl.utils import get_column_letter

from dst_manager.domain.creation import (
    SHEET_SCOPE,
    SHEETSET_SCOPE,
    CreationAssetOption,
    ordinary_properties,
)
from dst_manager.domain.standard_models import (
    DrawingStandard,
    normalize_property_name,
)

__all__ = [
    "CREATION_TEMPLATE_VERSION",
    "FIXED_SHEET_COLUMNS",
    "HIDDEN_SHEET_NAMES",
    "LIST_SHEET",
    "MAX_GROUP_COUNT",
    "MAX_SHEET_COLUMNS",
    "MAX_SHEET_ROWS",
    "META_FIRST_RECORD_ROW",
    "META_HEADER",
    "META_RECORDS",
    "META_SHEET",
    "SHEETSET_HEADERS",
    "SHEETSET_SHEET",
    "SHEET_SHEET",
    "TARGET_PATH_LABEL",
    "VALIDATION_ROW_LIMIT",
    "VISIBLE_SHEET_NAMES",
    "CreationAssetEntry",
    "CreationColumnSpec",
    "CreationSheetGrid",
    "CreationSheetSetRow",
    "CreationTemplatePlan",
    "CreationWorkbookView",
    "CreationXlsxReadError",
    "column_letter",
    "creation_metadata_records",
    "creation_template_plan",
]

#: 模板格式版本：隐藏技术表记录它，结构变化时必须递增。
CREATION_TEMPLATE_VERSION = 1

#: 两张可见工作表；顺序即生成顺序（``SheetSet`` 在前）。
SHEETSET_SHEET = "SheetSet"
SHEET_SHEET = "Sheet"
VISIBLE_SHEET_NAMES: tuple[str, str] = (SHEETSET_SHEET, SHEET_SHEET)
#: 隐藏技术表：元数据与 Data Validation 候选值。
META_SHEET = "_CreationMeta"
LIST_SHEET = "_CreationLists"
HIDDEN_SHEET_NAMES: tuple[str, str] = (META_SHEET, LIST_SHEET)

#: ``SheetSet`` 表：A 列属性名、B 列输入值；第 2 行固定为完整最终路径。
SHEETSET_HEADERS: tuple[str, str] = ("属性名", "输入值")
TARGET_PATH_LABEL = "项目保存路径"
#: ``Sheet`` 表的固定列（顺序即列序）：协议键 → 可见表头。
FIXED_SHEET_COLUMNS: tuple[tuple[str, str], ...] = (
    ("title", "图名"),
    ("count", "张数"),
    ("base_template", "基础模板"),
    ("layout_template", "布局模板"),
    ("paper_layout", "图幅"),
)
#: 动态列与固定表头重名时追加的可读限定语，保证可见表头唯一。
PROPERTY_HEADER_QUALIFIER = "（标准属性）"

#: 隐藏技术表的记录列与首条记录行。
META_HEADER: tuple[str, str, str, str] = ("record", "key", "value", "label")
META_FIRST_RECORD_ROW = 2
#: 隐藏技术表的记录类型。
META_RECORDS: frozenset[str] = frozenset(
    {
        "version",
        "standard",
        "fixed_column",
        "property_column",
        "sheetset_target_path",
        "sheetset_property",
        "asset",
    }
)

#: 受控规模：单个工作表的行号/列号上限，超出即整批拒绝。
MAX_SHEET_ROWS = 2000
MAX_SHEET_COLUMNS = 128
#: 单个图纸组的张数上限，避免异常工作簿触发放大。
MAX_GROUP_COUNT = 9999
#: Data Validation 覆盖的行上限（覆盖用户可能填写的范围）。
VALIDATION_ROW_LIMIT = 500

#: 包内禁止出现的部件标记：宏与外部链接。
FORBIDDEN_PART_MARKERS = ("vbaproject", "externallink")


class CreationXlsxReadError(Exception):
    """工作簿字节无法读成 XLSX（非压缩包、包损坏或 openpyxl 打开失败）。"""


@dataclass(frozen=True, slots=True)
class CreationColumnSpec:
    """``Sheet`` 表的一列：列号、唯一可见表头与稳定映射键。

    ``key`` 对固定列是协议键（``title``/``count``/…），对动态列是标准属性
    ``property_id``；解析只按 ``key`` 定位，不按表头文案猜测身份。
    """

    index: int
    header: str
    key: str
    is_fixed: bool

    @property
    def column(self) -> str:
        return column_letter(self.index)


@dataclass(frozen=True, slots=True)
class CreationSheetSetRow:
    """``SheetSet`` 表的一行：行号、可见属性名与目标 ``property_id``。

    ``property_id`` 为 None 表示固定的「项目保存路径」行（完整最终路径不是
    标准属性）。
    """

    row: int
    label: str
    property_id: str | None = None

    @property
    def is_target_path(self) -> bool:
        return self.property_id is None


@dataclass(frozen=True, slots=True)
class CreationAssetEntry:
    """隐藏技术表里的一个资产标签映射：同类内唯一的用户标签 → 稳定 ``asset_id``。"""

    kind: str
    label: str
    asset_id: str


@dataclass(frozen=True, slots=True)
class CreationTemplatePlan:
    """模板的规范形状：列计划、``SheetSet`` 行计划与资产标签映射。"""

    columns: tuple[CreationColumnSpec, ...]
    sheetset_rows: tuple[CreationSheetSetRow, ...]
    assets: tuple[CreationAssetEntry, ...]
    #: 生成计划时的当前资产候选；「图幅」候选名从中去重提取。
    asset_options: tuple[CreationAssetOption, ...] = ()

    def column(self, key: str) -> CreationColumnSpec | None:
        for spec in self.columns:
            if spec.key == key:
                return spec
        return None

    def sheetset_row(self, property_id: str) -> CreationSheetSetRow | None:
        for row in self.sheetset_rows:
            if row.property_id == property_id:
                return row
        return None

    def asset_labels(self, kind: str) -> tuple[str, ...]:
        return tuple(entry.label for entry in self.assets if entry.kind == kind)

    def layout_names(self) -> tuple[str, ...]:
        """全部布局模板候选的布局名（去重后保持出现顺序），供「图幅」候选用。"""
        names: list[str] = []
        for option in self.asset_options:
            if option.kind != "layout-template":
                continue
            for name in option.layouts:
                if name not in names:
                    names.append(name)
        return tuple(names)


@dataclass(frozen=True, slots=True)
class CreationSheetGrid:
    """一个工作表的只读快照：行 × 列文本网格（空单元格为空串）。

    ``rows`` 为空表示该工作表超出受控规模、未展开；此时调用方按 ``row_count``
    与 ``column_count`` 拒绝。
    """

    name: str
    state: str
    row_count: int
    column_count: int
    rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class CreationWorkbookView:
    """工作簿只读视图：工作表网格、公式单元格、不可解释单元格与包内危险部件。"""

    sheets: tuple[CreationSheetGrid, ...]
    formulas: tuple[tuple[str, int, str], ...] = ()
    invalid_cells: tuple[tuple[str, int, str], ...] = ()
    external_links: bool = False
    forbidden_parts: tuple[str, ...] = ()

    def sheet(self, name: str) -> CreationSheetGrid | None:
        for grid in self.sheets:
            if grid.name == name:
                return grid
        return None


def column_letter(index: int) -> str:
    """1 起始列号 → 列字母；诊断统一使用列字母。"""
    return get_column_letter(index)


def creation_template_plan(
    standard: DrawingStandard, asset_options: tuple[CreationAssetOption, ...]
) -> CreationTemplatePlan:
    """按标准与当前资产候选算出模板的规范形状。

    固定列在前、动态列按标准文档顺序在后；动态列表头与已用表头冲突时追加
    可读限定语，保证可见表头唯一。
    """
    columns: list[CreationColumnSpec] = []
    used: set[str] = set()
    for key, header in FIXED_SHEET_COLUMNS:
        used.add(normalize_property_name(header))
        columns.append(
            CreationColumnSpec(index=len(columns) + 1, header=header, key=key, is_fixed=True)
        )
    for prop in ordinary_properties(standard, SHEET_SCOPE):
        header = _unique_header(prop.name, used)
        used.add(normalize_property_name(header))
        columns.append(
            CreationColumnSpec(
                index=len(columns) + 1, header=header, key=prop.property_id, is_fixed=False
            )
        )

    sheetset_rows: list[CreationSheetSetRow] = [CreationSheetSetRow(row=2, label=TARGET_PATH_LABEL)]
    for prop in ordinary_properties(standard, SHEETSET_SCOPE):
        sheetset_rows.append(
            CreationSheetSetRow(
                row=len(sheetset_rows) + 2, label=prop.name, property_id=prop.property_id
            )
        )

    return CreationTemplatePlan(
        columns=tuple(columns),
        sheetset_rows=tuple(sheetset_rows),
        assets=tuple(
            CreationAssetEntry(kind=option.kind, label=option.label, asset_id=option.asset_id)
            for option in asset_options
        ),
        asset_options=tuple(asset_options),
    )


def _unique_header(name: str, used: set[str]) -> str:
    """动态列表头去重：与固定表头或其他属性名冲突时追加可读限定语。"""
    candidate = name
    index = 0
    while normalize_property_name(candidate) in used:
        index += 1
        qualifier = PROPERTY_HEADER_QUALIFIER if index == 1 else f"（标准属性 {index}）"
        candidate = f"{name}{qualifier}"
    return candidate


def creation_metadata_records(
    standard: DrawingStandard, plan: CreationTemplatePlan
) -> tuple[tuple[str, str, str, str], ...]:
    """隐藏技术表的规范记录序列（模板版本、标准身份、列/行映射与资产映射）。"""
    records: list[tuple[str, str, str, str]] = [
        ("version", "template_version", str(CREATION_TEMPLATE_VERSION), ""),
        ("standard", "standard_id", standard.standard_id, ""),
        ("standard", "standard_version", str(standard.version), ""),
    ]
    for spec in plan.columns:
        record = "fixed_column" if spec.is_fixed else "property_column"
        records.append((record, spec.column, spec.key, spec.header))
    for row in plan.sheetset_rows:
        if row.is_target_path:
            records.append(("sheetset_target_path", str(row.row), "", row.label))
        else:
            assert row.property_id is not None
            records.append(("sheetset_property", str(row.row), row.property_id, row.label))
    for entry in plan.assets:
        records.append(("asset", entry.kind, entry.asset_id, entry.label))
    return tuple(records)
