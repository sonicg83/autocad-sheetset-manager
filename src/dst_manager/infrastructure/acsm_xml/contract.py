"""版本化 AcSm contract registry 与结构契约校验。

本模块是 `DST -> XML DOM -> DST` 受控链路的契约权威来源：
- 维护已知 AcSm 对象的必需属性、固定属性值与 AcSmProp 的 `vt` 类型表；
- 维护已知对象类型的父级包含关系（用于层级校验）；
- 提供 `validate_contract`（宽容扫描）与 `validate_schema`（严格后置 XSD 边界）。

分层职责约定：
- **contract 校验器**：检查必需属性缺失、固定属性值错配、AcSmProp `vt`
  错配以及已知对象父级包含关系（层级）错误；对未知元素/属性/顺序/tail
  一律忽略，绝不报错，从而满足“未知内容必须保留”的安全约束。
- **XSD 校验器（schema）**：负责修复后的结构边界，声明已知对象类型并允许
  未知元素与未知属性扩展；由于 lxml/libxml2 不支持 XSD 1.1 `assert` 与
  `xs:all + xs:any` 的组合，XSD 内不再强制“必需子节点必须出现”，该不变量
  交给契约/语义校验器完成，避免对顺序与扩展节点产生误报。
- **语义校验器**：见 `document.AcsmDocument.validate()`，负责每张 Sheet 的
  布局唯一性、Number/Title 存在性、Handle 合法性、ID 全局唯一等业务不变量。

本文件不读取文件系统，不依赖 AutoCAD/DST codec，只做纯 DOM 契约判断。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from lxml import etree

from dst_manager.domain.models import Severity, ValidationIssue

CONTRACT_VERSION = "acsm-1.1"

# 稳定的 Project1 DbVersion=1.1 clsid（来自黄金样本，均为全局唯一类别标识）
CLSID_SHEETSET = "gB20534F2-0978-418C-8D14-2E6928A077ED"
CLSID_SUBSET = "g076D548F-B0F5-4FE1-B35D-7F7B73B8D322"
CLSID_SHEET = "g16A07941-BC15-4D48-A880-9D5A211D5065"
CLSID_PROPERTY_BAG = "g4D103908-8C86-4D95-BBF4-68B9A7B00731"
CLSID_PROPERTY_VALUE = "g8D22A2A4-1777-4D78-84CC-69EF741FE954"
CLSID_LAYOUT_REFERENCE = "g94910E94-4FCA-427C-B6ED-2EC9E1C900C7"
CLSID_SHEET_VIEWS = "gF40F931B-64BC-4B90-9FC8-A11A77D6815B"

_VT_OBJECT = "13"  # 对象节点的持久化类型标记
_VT_TEXT = "8"  # 普通文本属性
_VT_INT = "3"  # Flags 等整数标记
_VT_BOOL = "2"  # PromptForDwt / PublishOptions 等布尔标记


@dataclass(frozen=True, slots=True)
class ObjectContract:
    """已知 AcSm 对象的结构契约。

    - `required_attributes`：该节点类型必须存在的属性名集合。
    - `fixed_attributes`：只要该属性存在就必须等于此值的映射
      （clsid 全部固定；propname/vt 仅在整类恒定时列在此处）。
    """

    local_name: str
    required_attributes: frozenset[str]
    fixed_attributes: Mapping[str, str] = field(default_factory=dict)


_OBJECT_CONTRACTS: dict[str, ObjectContract] = {
    "AcSmSheetSet": ObjectContract(
        "AcSmSheetSet",
        frozenset({"ID", "clsid", "propname", "vt"}),
        {"clsid": CLSID_SHEETSET, "propname": "SheetSet", "vt": _VT_OBJECT},
    ),
    "AcSmSubset": ObjectContract(
        "AcSmSubset",
        frozenset({"ID", "clsid"}),
        {"clsid": CLSID_SUBSET},
    ),
    "AcSmSheet": ObjectContract(
        "AcSmSheet",
        frozenset({"ID", "clsid"}),
        {"clsid": CLSID_SHEET},
    ),
    "AcSmCustomPropertyBag": ObjectContract(
        "AcSmCustomPropertyBag",
        frozenset({"ID", "clsid", "propname", "vt"}),
        {"clsid": CLSID_PROPERTY_BAG, "propname": "CustomPropertyBag", "vt": _VT_OBJECT},
    ),
    "AcSmCustomPropertyValue": ObjectContract(
        "AcSmCustomPropertyValue",
        frozenset({"ID", "clsid", "propname", "vt"}),
        {"clsid": CLSID_PROPERTY_VALUE, "vt": _VT_OBJECT},
    ),
    "AcSmAcDbLayoutReference": ObjectContract(
        "AcSmAcDbLayoutReference",
        frozenset({"ID", "clsid", "propname", "vt"}),
        {"clsid": CLSID_LAYOUT_REFERENCE, "vt": _VT_OBJECT},
    ),
    "AcSmSheetViews": ObjectContract(
        "AcSmSheetViews",
        frozenset({"ID", "clsid", "propname", "vt"}),
        {"clsid": CLSID_SHEET_VIEWS, "propname": "SheetViews", "vt": _VT_OBJECT},
    ),
}

# 已知 AcSmProp 的 (所有者节点, propname) -> vt 类型表。
# 仅固化黄金样本中稳定、可证明的类型；未收录的 propname 不做类型断言。
_PROP_VT: dict[tuple[str, str], str] = {
    ("AcSmDatabase", "DbFingerPrint"): _VT_TEXT,
    ("AcSmDatabase", "DbVersion"): _VT_TEXT,
    ("AcSmDatabase", "FileRevision"): _VT_INT,
    ("AcSmSheetSet", "Desc"): _VT_TEXT,
    ("AcSmSheetSet", "Name"): _VT_TEXT,
    ("AcSmSheetSet", "PromptForDwt"): _VT_BOOL,
    ("AcSmSubset", "Desc"): _VT_TEXT,
    ("AcSmSubset", "Name"): _VT_TEXT,
    ("AcSmSubset", "PromptForDwt"): _VT_BOOL,
    ("AcSmSheet", "Number"): _VT_TEXT,
    ("AcSmSheet", "Title"): _VT_TEXT,
    ("AcSmCustomPropertyValue", "Flags"): _VT_INT,
    ("AcSmCustomPropertyValue", "Value"): _VT_TEXT,
    ("AcSmAcDbLayoutReference", "AcDbHandle"): _VT_TEXT,
    ("AcSmAcDbLayoutReference", "FileName"): _VT_TEXT,
    ("AcSmAcDbLayoutReference", "Name"): _VT_TEXT,
    ("AcSmAcDbLayoutReference", "Relative_FileName"): _VT_TEXT,
    ("AcSmFileReference", "FileName"): _VT_TEXT,
    ("AcSmFileReference", "Relative_FileName"): _VT_TEXT,
    ("AcSmPublishOptions", "DwfType"): _VT_BOOL,
    ("AcSmPublishOptions", "PromptForName"): _VT_BOOL,
}

# 已知对象类型的父级包含关系（层级校验）。未收录的父子组合表示“未知，
# 不校验”，从而保留扩展节点。
_PARENT_ALLOWED: dict[str, frozenset[str]] = {
    "AcSmSheetSet": frozenset({"AcSmDatabase"}),
    "AcSmSubset": frozenset({"AcSmSheetSet"}),
    "AcSmSheet": frozenset({"AcSmSubset"}),
    "AcSmCustomPropertyBag": frozenset({"AcSmSheet", "AcSmSheetSet"}),
    "AcSmCustomPropertyValue": frozenset({"AcSmCustomPropertyBag"}),
    "AcSmAcDbLayoutReference": frozenset({"AcSmSheet", "AcSmSheetSet"}),
    "AcSmSheetViews": frozenset({"AcSmSheet"}),
}


def object_contract(local_name: str) -> ObjectContract | None:
    """按本地名返回已知对象契约；未知类型返回 None（宽容）。"""
    return _OBJECT_CONTRACTS.get(local_name)


def expected_prop_vt(owner_local_name: str, propname: str) -> str | None:
    """返回已知 AcSmProp 在指定所有者下的期望 vt；未知返回 None。"""
    return _PROP_VT.get((owner_local_name, propname))


def _local_name(node: etree._Element) -> str:
    return etree.QName(node).localname


def validate_contract(root: etree._Element) -> list[ValidationIssue]:
    """宽松契约扫描：报告必需属性缺失、固定值错配、AcSmProp vt 错配与
    已知对象父级包含关系错误；未知元素/属性/顺序/tail 一律忽略。"""
    issues: list[ValidationIssue] = []
    for node in root.iter():
        local = _local_name(node)
        contract = _OBJECT_CONTRACTS.get(local)
        if contract is not None:
            object_id = node.get("ID") or node.get("propname") or local
            for attribute in sorted(contract.required_attributes):
                if attribute not in node.attrib:
                    issues.append(
                        ValidationIssue(
                            "CONTRACT_ATTRIBUTE_MISSING",
                            Severity.ERROR,
                            f"{local} 缺少必需属性 {attribute}",
                            object_id,
                            _node_location(node),
                        ),
                    )
            for attribute, expected in contract.fixed_attributes.items():
                actual = node.get(attribute)
                if actual is not None and actual != expected:
                    issues.append(
                        ValidationIssue(
                            "CONTRACT_ATTRIBUTE_VALUE",
                            Severity.ERROR,
                            f"{local} 的 {attribute} 应为 {expected}，实际为 {actual}",
                            object_id,
                            _node_location(node),
                        ),
                    )
            if local in _PARENT_ALLOWED:
                parent = node.getparent()
                parent_local = _local_name(parent) if parent is not None else None
                if parent_local not in _PARENT_ALLOWED[local]:
                    issues.append(
                        ValidationIssue(
                            "CONTRACT_PARENT_INVALID",
                            Severity.ERROR,
                            f"{local} 不能出现在 {parent_local or '根'} 之下",
                            object_id,
                            _node_location(node),
                        ),
                    )
        elif local == "AcSmProp":
            _validate_prop_vt(node, issues)
    return issues


def _validate_prop_vt(node: etree._Element, issues: list[ValidationIssue]) -> None:
    propname = node.get("propname")
    if propname is None:
        return
    parent = node.getparent()
    owner = _local_name(parent) if parent is not None else ""
    expected = _PROP_VT.get((owner, propname))
    if expected is None:
        return  # 未知属性名或所有者：宽容，交给语义/修复器处理
    actual = node.get("vt")
    if actual is None:
        issues.append(
            ValidationIssue(
                "PROP_VT_MISSING",
                Severity.ERROR,
                f"AcSmProp {propname} 缺少 vt（应为 {expected}）",
                None,
                _node_location(node),
            ),
        )
    elif actual != expected:
        issues.append(
            ValidationIssue(
                "PROP_VT_MISMATCH",
                Severity.ERROR,
                f"AcSmProp {propname} 的 vt 应为 {expected}，实际为 {actual}",
                None,
                _node_location(node),
            ),
        )


def _node_location(node: etree._Element) -> str | None:
    try:
        if node.sourceline is None:
            return None
        return f"line {node.sourceline}"
    except AttributeError:
        return None


@lru_cache(maxsize=1)
def _load_schema() -> etree.XMLSchema:
    """加载随包分发的严格后置 XSD；解析失败视为开发缺陷并抛出。"""
    schema_path = Path(__file__).resolve().parent / "schema" / "acsm-v1.xsd"
    schema_doc = etree.parse(str(schema_path))
    return etree.XMLSchema(schema_doc)


def validate_schema(root: etree._Element, version: str = CONTRACT_VERSION) -> list[ValidationIssue]:
    """严格后置 XSD 边界校验。校验的是修复后的结构；未知元素/属性通过
    `processContents=lax` 与 anyAttribute 保留，不被报错。"""
    schema = _load_schema()
    if schema.validate(root):
        return []
    error = schema.error_log.last_error
    message = error.message if error is not None else "schema 校验失败"
    location = f"{error.line}:{error.column}" if error is not None else None
    return [
        ValidationIssue(
            "XSD_INVALID",
            Severity.ERROR,
            f"AcSm XML 不满足 {version} 结构边界：{message}",
            root.get("ID"),
            location,
        ),
    ]
