"""双工作表创建模板的公共入口：模板生成与工作簿回读（PLAN-DM-036 Task 2 / SPEC-DM-018 §5）。

本模块只做再导出，实现按职责分在三个同层模块：模板协议（常量、值类型、规范
计划与隐藏技术表记录）见 :mod:`dst_manager.infrastructure.creation_xlsx_protocol`，
模板生成见 :mod:`dst_manager.infrastructure.creation_xlsx_template`，工作簿回读
见 :mod:`dst_manager.infrastructure.creation_xlsx_read`。调用方（含解析端
:mod:`dst_manager.application.creation_import`）只需从本模块取入口，不必关心
内部拆分。
"""

from __future__ import annotations

from dst_manager.infrastructure.creation_xlsx_protocol import (
    CREATION_TEMPLATE_VERSION,
    FIXED_SHEET_COLUMNS,
    FORBIDDEN_PART_MARKERS,
    HIDDEN_SHEET_NAMES,
    LIST_SHEET,
    MAX_GROUP_COUNT,
    MAX_SHEET_COLUMNS,
    MAX_SHEET_ROWS,
    META_FIRST_RECORD_ROW,
    META_HEADER,
    META_RECORDS,
    META_SHEET,
    PROPERTY_HEADER_QUALIFIER,
    SHEET_SHEET,
    SHEETSET_HEADERS,
    SHEETSET_SHEET,
    TARGET_PATH_LABEL,
    VALIDATION_ROW_LIMIT,
    VISIBLE_SHEET_NAMES,
    CreationAssetEntry,
    CreationColumnSpec,
    CreationSheetGrid,
    CreationSheetSetRow,
    CreationTemplatePlan,
    CreationWorkbookView,
    CreationXlsxReadError,
    column_letter,
    creation_metadata_records,
    creation_template_plan,
)
from dst_manager.infrastructure.creation_xlsx_read import read_creation_workbook
from dst_manager.infrastructure.creation_xlsx_template import build_creation_template

__all__ = [
    "CREATION_TEMPLATE_VERSION",
    "FIXED_SHEET_COLUMNS",
    "FORBIDDEN_PART_MARKERS",
    "HIDDEN_SHEET_NAMES",
    "LIST_SHEET",
    "MAX_GROUP_COUNT",
    "MAX_SHEET_COLUMNS",
    "MAX_SHEET_ROWS",
    "META_FIRST_RECORD_ROW",
    "META_HEADER",
    "META_RECORDS",
    "META_SHEET",
    "PROPERTY_HEADER_QUALIFIER",
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
    "build_creation_template",
    "column_letter",
    "creation_metadata_records",
    "creation_template_plan",
    "read_creation_workbook",
]
