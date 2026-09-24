"""从现有 DST 提取最小标准草稿结构（PLAN-DM-035 Task 5 / PLAN-DM-038 Task 4）。

导入只提取图纸集/图纸两级自定义属性定义与图纸集名称，构成可继续编辑的
最小安全草稿；不复制子集、图纸、布局引用、工程路径或任何外部依赖。
``ImportedStandardDraft`` 的 ``subsets``/``external_paths`` 恒为空元组，
以类型声明固化"不复制工程结构"这一边界。

Schema v1 起每个提取属性都带稳定 ``property_id``、``kind="text"`` 与空历史
名称；同名属性按全局唯一规则拒绝（不同作用域也不允许同名）。文档写入必填
的默认 ``dwg_naming``：``subset.scope + " " + subset.name``，不读取也不
推测现有 DWG 文件名前缀。
"""

import hashlib
from dataclasses import dataclass

from dst_manager.domain.standard_models import normalize_property_name
from dst_manager.infrastructure.acsm_xml.document import (
    _custom_property_scope,
    _prop,
)
from dst_manager.infrastructure.acsm_xml.document import (
    load_acsm as load_acsm_document,
)
from dst_manager.infrastructure.standards.store import StandardDraft

DEFAULT_IMPORTED_ID = "imported.draft"
DEFAULT_CAD_VERSIONS = ["2020"]
DEFAULT_NUMBERING = {"sequence_field": "subset.sequence", "digits": 2}
#: 默认 DWG 命名模板：只使用子集范围与名称，不携带隐式前缀。
DEFAULT_DWG_NAMING_SEGMENTS = (
    {"system_field": "subset.scope"},
    {"literal": " "},
    {"system_field": "subset.name"},
)


def _default_dwg_naming() -> dict[str, object]:
    return {"segments": [dict(segment) for segment in DEFAULT_DWG_NAMING_SEGMENTS]}

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
        "schema_version": 2,
        "standard_id": DEFAULT_IMPORTED_ID,
        "name": _require_sheet_set_name(sheet_sets[0]),
        "supported_cad_versions": list(DEFAULT_CAD_VERSIONS),
        "properties": _extract_property_definitions(root),
        "dwg_naming": _default_dwg_naming(),
        "assets": [],
        "numbering": dict(DEFAULT_NUMBERING),
    }


def _require_sheet_set_name(sheet_set) -> str:
    name = _prop(sheet_set, "Name")
    if not name:
        raise ValueError("DST_SHEET_SET_NAME_MISSING")
    return name


def _extract_property_definitions(root) -> list[dict[str, object]]:
    """提取文本型自定义属性定义；同名跨作用域按全局唯一规则拒绝。"""
    properties: list[dict[str, object]] = []
    seen: dict[str, str] = {}
    for node in root.xpath("//*[local-name()='AcSmCustomPropertyValue']"):
        name = node.get("propname", "")
        if not name:
            continue
        scope = _SCOPE_BY_FLAG.get(_custom_property_scope(node))
        if scope is None:
            continue
        normalized = normalize_property_name(name)
        if not normalized:
            continue
        owner = seen.get(normalized)
        if owner is not None:
            if owner == scope:
                continue  # 同一属性定义在多个 AcSm 节点上重复出现
            raise ValueError(
                f"DST_PROPERTY_NAME_CONFLICT: 属性名 {name!r} 在 {owner} 与 {scope} 作用域重复，"
                "标准属性名必须全局唯一"
            )
        seen[normalized] = scope
        properties.append(
            {
                "property_id": _imported_property_id(normalized),
                "name": name,
                "previous_names": [],
                "scope": scope,
                "kind": "text",
                "required": False,
            }
        )
    return properties


def _imported_property_id(normalized_name: str) -> str:
    """由规范化名称派生的稳定属性 ID；同一 DST 重复导入得到同一 ID。"""
    digest = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()
    return f"prop-{digest[:12]}"
