"""从现有 DST 提取最小标准草稿结构（PLAN-DM-035 Task 5）。

导入只提取图纸集/图纸两级自定义属性定义与图纸集名称，构成可继续编辑的
最小安全草稿；不复制子集、图纸、布局引用、工程路径或任何外部依赖。
``ImportedStandardDraft`` 的 ``subsets``/``external_paths`` 恒为空元组，
以类型声明固化"不复制工程结构"这一边界。
"""

from dataclasses import dataclass

from dst_manager.infrastructure.acsm_xml.document import (
    _custom_property_scope,
    _prop,
)
from dst_manager.infrastructure.acsm_xml.document import (
    load_acsm as load_acsm_document,
)
from dst_manager.infrastructure.standards.store import StandardDraft

DEFAULT_IMPORTED_ID = "imported.draft"
DEFAULT_IMPORTED_VERSION = "0.1.0"
DEFAULT_CAD_VERSIONS = ["2020"]
DEFAULT_NUMBERING = {"sequence_field": "subset.sequence", "digits": 2}

# 属性定义 Flags：1=图纸集级，2=图纸级（与 AcSmDocument 契约一致）。
_SCOPE_BY_FLAG = {"1": "sheetset", "2": "sheet"}


@dataclass(frozen=True, slots=True)
class ImportedStandardDraft(StandardDraft):
    """DST 导入草稿；两个恒空字段证明未复制子集与外部引用。"""

    subsets: tuple[str, ...] = ()
    external_paths: tuple[str, ...] = ()


def extract_standard_document(xml: bytes) -> dict[str, object]:
    """解析 DST XML 并生成最小标准草稿文档；非法 DST 抛稳定错误码。"""
    document = load_acsm_document(xml)
    status = document.repair_report.status
    if status not in {"VALID", "REPAIRED"}:
        raise ValueError(f"DST_IMPORT_REPAIR_BLOCKED: {status}")
    root = document.root
    sheet_sets = root.xpath("//*[local-name()='AcSmSheetSet']")
    if len(sheet_sets) != 1:
        raise ValueError("DST_SHEET_SET_MISSING")
    return {
        "schema_version": 1,
        "standard_id": DEFAULT_IMPORTED_ID,
        "version": DEFAULT_IMPORTED_VERSION,
        "name": _require_sheet_set_name(sheet_sets[0]),
        "supported_cad_versions": list(DEFAULT_CAD_VERSIONS),
        "properties": _extract_property_definitions(root),
        "rules": [],
        "assets": [],
        "numbering": dict(DEFAULT_NUMBERING),
    }


def _require_sheet_set_name(sheet_set) -> str:
    name = _prop(sheet_set, "Name")
    if not name:
        raise ValueError("DST_SHEET_SET_NAME_MISSING")
    return name


def _extract_property_definitions(root) -> list[dict[str, object]]:
    properties: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for node in root.xpath("//*[local-name()='AcSmCustomPropertyValue']"):
        name = node.get("propname", "")
        if not name:
            continue
        scope = _SCOPE_BY_FLAG.get(_custom_property_scope(node))
        if scope is None:
            continue
        key = (scope, name.casefold())
        if key in seen:
            continue
        seen.add(key)
        properties.append({"name": name, "scope": scope, "required": False})
    return properties
