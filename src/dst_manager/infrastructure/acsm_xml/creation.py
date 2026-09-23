"""内置最小 DST 骨架的受控实例化（PLAN-DM-036 Task 5）。

唯一受版本控制的权威骨架是 ``assets/minimal_sheetset.xml``：静态结构、无示例
业务值、无 AcSm ID。全部动态值（数据库指纹、根/子对象 ID、图纸集名称、项目
路径、属性定义与值、子集/Sheet/布局引用）都由本模块用 DOM 写入，**禁止字符串
替换 XML**。骨架里的单个 ``AcSmSubset``/``AcSmSheet`` 是节点原型（节点名、
clsid 与子节点顺序的权威来源）：实例化时按计划克隆，原型本身不进入最终 DST。

结构与类别标识按实测的真实 AcSm 数据库核定（``sample/project1``、``sample/project2``
的 ``图纸集数据文件.dst``，均为 AutoCAD/图纸集管理器真实产物）：只保留协议所需
的 ``clsid``/``vt``/节点名与顺序，不复制示例名称、路径或实例 GUID，也不执行
legacy PowerShell。legacy 清单里的 ``AcSmSimpleFileReferece`` 未出现在任何真实
DST 中，因此不作为协议必需节点。

布局引用先写受控占位 Handle（:data:`PLACEHOLDER_LAYOUT_HANDLE`）：语义校验器
拒绝 ``"0"``，所以「CAD 回写前」的中间态用一个**显式可识别**的占位值表示，绝不
用 ``"0"`` 伪装成通过校验；候选 DST 必须经 :func:`apply_layout_handles` 回填真实
Handle 后才允许流出，:func:`is_placeholder_handle` 与 :func:`pending_layout_handles`
是「尚未回填」的唯一判定口径。
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from pathlib import Path

from lxml import etree

from dst_manager.domain.creation import SHEET_SCOPE, SHEETSET_SCOPE
from dst_manager.domain.creation_plan_models import (
    CreationPlan,
    CreationSettings,
    GroupPlan,
    SheetPlan,
)
from dst_manager.domain.editing import EditingError, validate_xml_text
from dst_manager.infrastructure.acsm_xml.contract import CLSID_PROPERTY_VALUE
from dst_manager.infrastructure.acsm_xml.document import AcsmDocument, load_acsm

__all__ = [
    "CREATION_DST_NAME",
    "PLACEHOLDER_LAYOUT_HANDLE",
    "SKELETON_PATH",
    "STANDARD_IDENTITY_PROPERTY",
    "STANDARD_OPTIONS_PROPERTY",
    "CreationAcsmError",
    "apply_layout_handles",
    "build_minimal_acsm",
    "is_placeholder_handle",
    "pending_layout_handles",
    "standard_options_value",
]

#: 唯一受版本控制的权威骨架；实例化只读它，绝不改写。
SKELETON_PATH = Path(__file__).resolve().parent / "assets" / "minimal_sheetset.xml"

#: 新项目图纸集数据文件名（legacy ``$dstname`` 与真实工程 ``sample/project1|2`` 同一口径）。
#: Task 6 发布器按 :attr:`CreationCandidate.dst_name` 使用，不得再写字面量。
CREATION_DST_NAME = "图纸集数据文件.dst"

#: CAD 回写前的受控占位 Handle：16 位全 F。真实 DWG 的布局对象句柄远低于该值，
#: 因此占位不可能与真实回读值相撞；语义校验器拒绝 ``"0"``，占位必须显式可识别。
PLACEHOLDER_LAYOUT_HANDLE = "FFFFFFFFFFFFFFFF"

#: 标准身份与有效编号配置的保留属性名（AcSm 自定义属性名，作用域固定为图纸集）。
STANDARD_IDENTITY_PROPERTY = "DSTManager.Standard"
STANDARD_OPTIONS_PROPERTY = "DSTManager.StandardOptions"

_HANDLE_PATTERN = re.compile(r"^[0-9A-Fa-f]+$")
_VT_OBJECT = "13"  # 对象节点的持久化类型标记（与 contract 同一口径）
_VT_TEXT = "8"  # 普通文本属性
_VT_INT = "3"  # Flags 等整数标记
_SHEETSET_FLAGS = "1"
_SHEET_FLAGS = "2"


class CreationAcsmError(ValueError):
    """内置骨架实例化/回填失败；``code`` 为稳定错误码，消息以该码开头。"""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def standard_options_value(settings: CreationSettings) -> str:
    """有效编号配置的受控 JSON 文本（键序固定、``version`` 显式为 1）。

    这是 ``DSTManager.StandardOptions`` 的唯一权威形态：只转移 DST/DWG、未附带
    ``.dst-manager`` 时，读取方靠它恢复实际生效的编号位数/起点与标题后缀设置。
    """
    payload = {
        "version": 1,
        "numbering": {
            "sequence_field": settings.numbering.sequence_field,
            "digits": settings.numbering.digits,
            "start": settings.numbering.start,
        },
        "suffix": {
            "enabled": settings.suffix_options.enabled,
            "suffix_type": settings.suffix_options.suffix_type,
            "unnumbered_keywords": list(settings.suffix_options.unnumbered_keywords),
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_placeholder_handle(value: object) -> bool:
    """是否为 CAD 回写前的受控占位 Handle（唯一判定口径，大小写与首尾空白不敏感）。"""
    return isinstance(value, str) and value.strip().upper() == PLACEHOLDER_LAYOUT_HANDLE


def pending_layout_handles(document: AcsmDocument) -> dict[str, str]:
    """仍是占位值的图纸：``AcSmSheet ID → 占位值``；非空即代表尚未回填真实 Handle。"""
    return {
        sheet.get("ID", ""): _prop(_layout_reference(sheet), "AcDbHandle")
        for sheet in _sheets(document.root)
        if is_placeholder_handle(_prop(_layout_reference(sheet), "AcDbHandle"))
    }


def build_minimal_acsm(plan: CreationPlan) -> AcsmDocument:
    """按创建计划实例化内置骨架，返回已通过契约/XSD/语义校验的 ``AcsmDocument``。

    每次调用生成新的数据库指纹与全部对象 ID；``AcSmSheetSet.Name`` 取最终项目
    目录名，项目路径写入 ``NewSheetLocation``，普通与派生属性按**属性名**写入
    （SPEC-DM-017 §3.2），并写保留属性 ``DSTManager.Standard`` 与
    ``DSTManager.StandardOptions``。布局引用一律先写受控占位 Handle。
    """
    root = _skeleton_root()
    sheet_set = _single_child(root, "AcSmSheetSet")
    _write_database(root)
    _write_sheet_set(sheet_set, plan)
    _write_sheet_set_properties(sheet_set, plan)
    _append_subsets(sheet_set, plan)
    _assign_ids(root)
    document = load_acsm(etree.tostring(root, xml_declaration=True, encoding="UTF-8"))
    _require_valid(document)
    return document


def apply_layout_handles(document: AcsmDocument, handles: Mapping[str, str]) -> None:
    """把暂存 Worker 回读的真实 Handle 写回骨架 DOM。

    覆盖必须与文档中的图纸一一对应；占位值、``"0"``、非十六进制与同一 DWG 内
    数值重复一律拒绝（与发布链的 ``HANDLE_OUTPUT_INVALID``/``HANDLE_DUPLICATE``
    同口径）。回填后复核一遍，保证候选 DST 里不再残留占位。
    """
    sheets = _sheets(document.root)
    sheet_ids = [sheet.get("ID", "") for sheet in sheets]
    if len(handles) != len(sheet_ids) or set(handles) != set(sheet_ids):
        raise CreationAcsmError(
            "CREATION_HANDLE_SET_MISMATCH",
            f"Handle 覆盖与图纸不一一对应：图纸 {len(sheet_ids)} 张，Handle {len(handles)} 个",
        )
    owners: set[tuple[str, int]] = set()
    for sheet in sheets:
        value = _require_handle(handles[sheet.get("ID", "")])
        layout = _layout_reference(sheet)
        owner = (_prop(layout, "FileName").casefold(), value)
        if owner in owners:
            raise CreationAcsmError(
                "CREATION_HANDLE_DUPLICATE",
                f"同一 DWG 内布局 Handle 重复：{_prop(layout, 'FileName')}，{handles[sheet.get('ID', '')]}",
            )
        owners.add(owner)
        _set_prop(layout, "AcDbHandle", handles[sheet.get("ID", "")].upper())
    for sheet in sheets:
        _require_handle(_prop(_layout_reference(sheet), "AcDbHandle"))


# ---- 骨架实例化 -------------------------------------------------------------


def _skeleton_root() -> etree._Element:
    """读取并解析骨架：去缩进空白与注释，保证产出的 DST 与真实 DST 同样紧凑。

    只校验骨架形状（根节点、对象节点都带 clsid、不内置 AcSm ID）；ID 在最终
    树上一次性生成，因此克隆出的每个节点都拿到新 ID。
    """
    parser = etree.XMLParser(
        remove_blank_text=True,
        remove_comments=True,
        resolve_entities=False,
        no_network=True,
    )
    try:
        root = etree.fromstring(SKELETON_PATH.read_bytes(), parser)
    except (OSError, etree.XMLSyntaxError) as exc:
        raise CreationAcsmError("CREATION_SKELETON_UNREADABLE", f"内置骨架不可读：{exc}") from exc
    if etree.QName(root).localname != "AcSmDatabase":
        raise CreationAcsmError("CREATION_SKELETON_INVALID", "内置骨架根节点必须为AcSmDatabase")
    for node in root.iter():
        local = etree.QName(node).localname
        if node.get("clsid") is None:
            if local != "AcSmProp":
                raise CreationAcsmError(
                    "CREATION_SKELETON_INVALID", f"骨架节点 {local} 缺少 clsid"
                )
            continue
        if node.get("ID") is not None:
            raise CreationAcsmError(
                "CREATION_SKELETON_INVALID", f"骨架不得内置 AcSm ID：{local}"
            )
    return root


def _assign_ids(root: etree._Element) -> None:
    """给最终树上每个 AcSm 对象生成新 ID（骨架不内置 ID，也不复用原型 ID）。"""
    for node in root.iter():
        if node.get("clsid") is not None:
            node.set("ID", "g" + str(uuid.uuid4()).upper())


def _write_database(root: etree._Element) -> None:
    """数据库指纹每次实例化都重新生成；版本与文件修订保持骨架的固定值。"""
    _set_prop(root, "DbFingerPrint", "g" + str(uuid.uuid4()).upper())


def _write_sheet_set(sheet_set: etree._Element, plan: CreationPlan) -> None:
    """图纸集名称取最终项目目录名；项目路径写入新建图纸位置引用。"""
    if not plan.target_path:
        raise CreationAcsmError("CREATION_PLAN_INVALID", "计划缺少最终项目路径")
    _set_prop(sheet_set, "Name", Path(plan.target_path).name)
    _set_prop(sheet_set, "Desc", "")
    location = _single_child(sheet_set, "AcSmFileReference")
    _set_prop(location, "FileName", plan.target_path)
    _set_prop(location, "Relative_FileName", ".")


def _write_sheet_set_properties(sheet_set: etree._Element, plan: CreationPlan) -> None:
    """图纸集属性袋：全部属性定义（按作用域给 Flags）+ 值 + 两项保留属性。

    ``sheet`` 作用域属性在图纸集属性袋里只写定义（无 Value），逐张值写在各
    图纸自己的属性袋里——与真实 DST 及受控编辑的既有语义一致。
    """
    bag = _single_child(sheet_set, "AcSmCustomPropertyBag")
    for prop in plan.settings.properties:
        sheetset_scope = prop.scope == SHEETSET_SCOPE
        bag.append(
            _property_value(
                prop.name,
                _SHEETSET_FLAGS if sheetset_scope else _SHEET_FLAGS,
                plan.sheetset_values.get(prop.property_id, "") if sheetset_scope else "",
            )
        )
    bag.append(
        _property_value(
            STANDARD_IDENTITY_PROPERTY, _SHEETSET_FLAGS, plan.settings.standard_identity
        )
    )
    bag.append(
        _property_value(
            STANDARD_OPTIONS_PROPERTY,
            _SHEETSET_FLAGS,
            standard_options_value(plan.settings),
        )
    )


def _append_subsets(sheet_set: etree._Element, plan: CreationPlan) -> None:
    """按计划克隆节点原型：一组一个子集、一张图纸一个 Sheet 与一个布局引用。"""
    prototypes = _children(sheet_set, "AcSmSubset")
    if len(prototypes) != 1:
        raise CreationAcsmError(
            "CREATION_SKELETON_INVALID", "骨架必须恰好包含一个子集原型"
        )
    prototype_subset = prototypes[0]
    prototype_sheets = _children(prototype_subset, "AcSmSheet")
    if len(prototype_sheets) != 1:
        raise CreationAcsmError(
            "CREATION_SKELETON_INVALID", "骨架必须恰好包含一个图纸原型"
        )
    prototype_sheet = prototype_sheets[0]
    for group in plan.groups:
        if not group.dwg_name or not group.target_path or not group.sheets:
            raise CreationAcsmError(
                "CREATION_PLAN_INVALID", f"图纸组 {group.group_id!r} 缺少可执行的命名结果"
            )
        subset = _clone(prototype_subset)
        _set_prop(subset, "Name", group.title)
        for sheet in _children(subset, "AcSmSheet"):
            subset.remove(sheet)
        for sheet_plan in group.sheets:
            subset.append(_sheet_node(prototype_sheet, group, sheet_plan, plan))
        prototype_subset.addprevious(subset)
    sheet_set.remove(prototype_subset)


def _sheet_node(
    prototype: etree._Element, group: GroupPlan, sheet_plan: SheetPlan, plan: CreationPlan
) -> etree._Element:
    """一张图纸：图号/标题 + 布局引用（占位 Handle 指向最终目标 DWG）+ 逐张属性。"""
    sheet = _clone(prototype)
    _set_prop(sheet, "Number", sheet_plan.number)
    _set_prop(sheet, "Title", sheet_plan.title)
    layout = _layout_reference(sheet)
    _set_prop(layout, "AcDbHandle", PLACEHOLDER_LAYOUT_HANDLE)
    _set_prop(layout, "Name", sheet_plan.layout_name)
    _set_prop(layout, "FileName", group.target_path)
    _set_prop(layout, "Relative_FileName", ".\\" + group.dwg_name)
    bag = _single_child(sheet, "AcSmCustomPropertyBag")
    for prop in plan.settings.properties:
        if prop.scope != SHEET_SCOPE:
            continue
        bag.append(
            _property_value(
                prop.name, _SHEET_FLAGS, sheet_plan.values.get(prop.property_id, "")
            )
        )
    return sheet


def _clone(prototype: etree._Element) -> etree._Element:
    """克隆节点原型：序列化往返保持节点名、属性与子节点顺序，不带原型 tail。"""
    return etree.fromstring(etree.tostring(prototype, with_tail=False))


def _property_value(propname: str, flags: str, value: str) -> etree._Element:
    """一个自定义属性定义：``Flags`` 决定作用域，空值不写 ``Value`` 节点。"""
    node = etree.Element(
        "AcSmCustomPropertyValue",
        {
            "clsid": CLSID_PROPERTY_VALUE,
            "ID": "g" + str(uuid.uuid4()).upper(),
            "propname": _xml_text(propname),
            "vt": _VT_OBJECT,
        },
    )
    node.append(_new_prop("Flags", flags, _VT_INT))
    if value:
        node.append(_new_prop("Value", value, _VT_TEXT))
    return node


def _new_prop(propname: str, text: str, vt: str) -> etree._Element:
    node = etree.Element("AcSmProp", {"propname": propname, "vt": vt})
    node.text = _xml_text(text)
    return node


def _xml_text(value: object) -> str:
    """写入 DST 的文本必须可编码为 XML 1.0 文本（复用编辑域同一判定与错误码）。"""
    try:
        return validate_xml_text(value)
    except EditingError as exc:
        raise CreationAcsmError(exc.code, "文本包含 XML 1.0 禁止字符") from exc


# ---- DOM 读写与校验辅助 -----------------------------------------------------


def _children(node: etree._Element, local_name: str) -> list[etree._Element]:
    return [child for child in node if etree.QName(child).localname == local_name]


def _single_child(node: etree._Element, local_name: str) -> etree._Element:
    found = _children(node, local_name)
    if len(found) != 1:
        raise CreationAcsmError(
            "CREATION_SKELETON_INVALID",
            f"{etree.QName(node).localname} 必须恰好包含一个 {local_name}",
        )
    return found[0]


def _prop(node: etree._Element, propname: str) -> str:
    for child in _children(node, "AcSmProp"):
        if child.get("propname") == propname:
            return child.text or ""
    return ""


def _set_prop(node: etree._Element, propname: str, value: str) -> None:
    found = [child for child in _children(node, "AcSmProp") if child.get("propname") == propname]
    if len(found) != 1:
        raise CreationAcsmError(
            "CREATION_SKELETON_INVALID",
            f"{etree.QName(node).localname} 的 {propname} 属性节点不唯一",
        )
    found[0].text = _xml_text(value)


def _sheets(root: etree._Element) -> list[etree._Element]:
    return root.xpath("//*[local-name()='AcSmSheet']")


def _layout_reference(sheet: etree._Element) -> etree._Element:
    return _single_child(sheet, "AcSmAcDbLayoutReference")


def _require_handle(handle: object) -> int:
    """校验一个回读 Handle：必须是合法十六进制、非占位、非零，返回数值。"""
    if not isinstance(handle, str) or not _HANDLE_PATTERN.fullmatch(handle):
        raise CreationAcsmError("CREATION_HANDLE_INVALID", f"布局 Handle 无效：{handle!r}")
    if is_placeholder_handle(handle):
        raise CreationAcsmError(
            "CREATION_HANDLE_PLACEHOLDER", "布局 Handle 仍为 CAD 回写前的受控占位值"
        )
    value = int(handle, 16)
    if value == 0:
        raise CreationAcsmError("CREATION_HANDLE_INVALID", "布局 Handle 不得为 0")
    return value


def _require_valid(document: AcsmDocument) -> None:
    """骨架实例化后必须同时通过修复状态与语义/契约/XSD 校验。"""
    if document.repair_report.status != "VALID":
        raise CreationAcsmError(
            "CREATION_SKELETON_INVALID",
            "内置骨架未被校验器接受：" + document.repair_report.status,
        )
    issues = document.validate()
    if issues:
        raise CreationAcsmError(
            "CREATION_SKELETON_INVALID",
            "内置骨架存在诊断：" + ", ".join(sorted({issue.code for issue in issues})),
        )
