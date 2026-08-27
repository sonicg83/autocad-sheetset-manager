"""DST XML 内存修复器与可审计 RepairReport。

`AcsmRepairer` 在**深拷贝的 DOM** 上事务式执行确定性/推断修复，绝不修改
传入的原始 root，也不写任何文件。修复顺序：

1. 建立全局 ID 索引并检测重复/格式非法 ID；
2. 为缺少 ID 的已知对象生成唯一 ID；
3. 按 `contract.py` 的固定属性表补齐缺失的 `clsid`/`propname`/`vt`；
4. 按属性类型表补齐 `AcSmProp` 缺失的 `vt`；
5. 在黄金样本位置为缺 `AcSmSheetViews` 的图纸补齐该容器；
6. 汇总每张图纸的布局/Number/Title/属性作用域不变量，形成阻断诊断。

状态汇总（见 `domain.models.RepairReport`）：
- 结构性不可恢复（重复/非法 ID、根节点错误）→ `INVALID_UNRECOVERABLE`；
- 其他阻断（缺业务值、布局冲突、错误非空固定值、属性作用域冲突）→
  `INVALID_REPAIR_REQUIRED`，均**不覆盖原值**；
- 修复生效且无阻断 → `REPAIRED`；无修复且无阻断 → `VALID`。
"""
from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Iterable

from lxml import etree

from dst_manager.domain.models import (
    RepairAction,
    RepairReport,
    Severity,
    ValidationIssue,
)
from dst_manager.infrastructure.acsm_xml.contract import (
    CLSID_SHEET_VIEWS,
    expected_prop_vt,
    object_contract,
)

_ID_RE = re.compile(r"^g[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")
_UNRECOVERABLE_CODES = {"DUPLICATE_ACSM_ID", "INVALID_ACSM_ID", "XML_ROOT_INVALID"}
_VT_OBJECT = "13"


def _local_name(node: etree._Element) -> str:
    return etree.QName(node).localname


def _node_path(node: etree._Element) -> str:
    parts: list[str] = []
    current = node
    while current is not None:
        local = _local_name(current)
        parent = current.getparent()
        if parent is None:
            parts.append(local)
            break
        siblings = [c for c in parent if _local_name(c) == local]
        try:
            index = siblings.index(current)
        except ValueError:
            index = 0
        object_id = current.get("ID")
        suffix = f'[@ID="{object_id}"]' if object_id else f"[{index}]"
        parts.append(local + suffix)
        current = parent
    return "/" + "/".join(reversed(parts))


def _prop_text(node: etree._Element, name: str) -> str:
    for child in node:
        if _local_name(child) == "AcSmProp" and child.get("propname") == name:
            return (child.text or "").strip()
    return ""


class AcsmRepairer:
    """在深拷贝副本上执行可审计的 AcSm 结构修复。"""

    def repair(self, root: etree._Element) -> tuple[etree._Element, RepairReport]:
        if _local_name(root) != "AcSmDatabase":
            report = RepairReport(
                "INVALID_UNRECOVERABLE",
                (),
                (
                    ValidationIssue(
                        "XML_ROOT_INVALID",
                        Severity.ERROR,
                        "根节点必须为AcSmDatabase",
                    ),
                ),
            )
            return copy.deepcopy(root), report

        working = copy.deepcopy(root)
        actions: list[RepairAction] = []
        blocking: list[ValidationIssue] = []

        # 1) 全局 ID 索引与重复/格式校验
        seen_ids: set[str] = set()
        id_by_key: dict[str, str] = {}
        for node in working.iter():
            object_id = node.get("ID")
            if not object_id:
                continue
            key = object_id.casefold()
            if key in id_by_key:
                blocking.append(ValidationIssue("DUPLICATE_ACSM_ID", Severity.ERROR, "AcSm ID重复", object_id))
            else:
                id_by_key[key] = object_id
            if not _ID_RE.fullmatch(object_id):
                blocking.append(ValidationIssue("INVALID_ACSM_ID", Severity.ERROR, "AcSm ID格式无效", object_id))
            seen_ids.add(key)

        # 2) 为缺失 ID 的已知对象生成唯一 ID
        for node in list(working.iter()):
            if object_contract(_local_name(node)) is not None and not node.get("ID"):
                new_id = self._new_unique_id(seen_ids)
                node.set("ID", new_id)
                actions.append(
                    RepairAction(
                        "REPAIR_ID_MISSING",
                        _node_path(node),
                        new_id,
                        "deterministic",
                        {"ID": None},
                        {"ID": new_id},
                        "为已知对象生成唯一 AcSm ID",
                    ),
                )

        # 3) 补齐已知对象的固定属性（缺则补；非空错误值不覆盖并阻断）
        for node in list(working.iter()):
            local = _local_name(node)
            contract = object_contract(local)
            if contract is None:
                continue
            for attribute in ("ID", "clsid", "propname", "vt"):
                expected = contract.fixed_attributes.get(attribute)
                if expected is None:
                    continue
                current = node.get(attribute)
                if current is None:
                    node.set(attribute, expected)
                    actions.append(
                        RepairAction(
                            "REPAIR_ATTR_MISSING",
                            _node_path(node),
                            node.get("ID"),
                            "deterministic",
                            {attribute: None},
                            {attribute: expected},
                            f"补齐 {local} 的 {attribute}",
                        ),
                    )
                elif current != expected:
                    blocking.append(
                        ValidationIssue(
                            "CONTRACT_ATTRIBUTE_VALUE",
                            Severity.ERROR,
                            f"{local} 的 {attribute} 应为 {expected}，实际为 {current}",
                            node.get("ID"),
                        ),
                    )
            # 布局引用的 propname 按父级上下文动态确定
            if local == "AcSmAcDbLayoutReference" and node.get("propname") is None:
                parent = node.getparent()
                parent_local = _local_name(parent) if parent is not None else ""
                propname = "Layout" if parent_local == "AcSmSheet" else ("DefDwtLayout" if parent_local == "AcSmSheetSet" else None)
                if propname:
                    node.set("propname", propname)
                    actions.append(
                        RepairAction(
                            "REPAIR_ATTR_MISSING",
                            _node_path(node),
                            node.get("ID"),
                            "deterministic",
                            {"propname": None},
                            {"propname": propname},
                            "补齐布局引用的 propname",
                        ),
                    )

        # 4) 补齐 AcSmProp 缺失的 vt（非空错误 vt 不覆盖并阻断）
        for node in list(working.iter()):
            if _local_name(node) != "AcSmProp":
                continue
            propname = node.get("propname")
            parent = node.getparent()
            owner = _local_name(parent) if parent is not None else ""
            expected = expected_prop_vt(owner, propname)
            if expected is None:
                continue
            current = node.get("vt")
            if current is None:
                node.set("vt", expected)
                actions.append(
                    RepairAction(
                        "PROP_VT_MISSING",
                        _node_path(node),
                        node.get("ID"),
                        "deterministic",
                        {"vt": None},
                        {"vt": expected},
                        f"补齐 AcSmProp {propname} 的 vt",
                    ),
                )
            elif current != expected:
                blocking.append(
                    ValidationIssue(
                        "PROP_VT_MISMATCH",
                        Severity.ERROR,
                        f"AcSmProp {propname} 的 vt 应为 {expected}，实际为 {current}",
                        node.get("ID"),
                    ),
                )

        # 5) 为缺 AcSmSheetViews 的图纸补齐该容器（黄金样本位置：Title 之前）
        for sheet in list(working.xpath("//*[local-name()='AcSmSheet']")):
            if any(_local_name(child) == "AcSmSheetViews" for child in sheet):
                continue
            new_id = self._new_unique_id(seen_ids)
            views_node = etree.Element(
                "AcSmSheetViews",
                {"clsid": CLSID_SHEET_VIEWS, "ID": new_id, "propname": "SheetViews", "vt": _VT_OBJECT},
            )
            title = next(
                (
                    child
                    for child in sheet
                    if _local_name(child) == "AcSmProp" and child.get("propname") == "Title"
                ),
                None,
            )
            if title is not None:
                title.addprevious(views_node)
            else:
                sheet.append(views_node)
            actions.append(
                RepairAction(
                    "REPAIR_SHEET_VIEWS_MISSING",
                    _node_path(sheet) + "/AcSmSheetViews",
                    new_id,
                    "deterministic",
                    {},
                    {"clsid": CLSID_SHEET_VIEWS, "ID": new_id, "propname": "SheetViews", "vt": _VT_OBJECT},
                    "为图纸补齐 AcSmSheetViews 容器",
                ),
            )

        # 6) 每张图纸的语义不变量 -> 阻断诊断
        for sheet in working.xpath("//*[local-name()='AcSmSheet']"):
            sheet_id = sheet.get("ID")
            layouts = [child for child in sheet if _local_name(child) == "AcSmAcDbLayoutReference"]
            if len(layouts) != 1:
                blocking.append(
                    ValidationIssue("SHEET_LAYOUT_COUNT", Severity.ERROR, "图纸必须恰好有一个布局引用", sheet_id),
                )
            else:
                for field in ("AcDbHandle", "FileName", "Name", "Relative_FileName"):
                    if not _prop_text(layouts[0], field):
                        blocking.append(
                            ValidationIssue("LAYOUT_FIELD_MISSING", Severity.ERROR, f"布局缺少{field}", sheet_id, layouts[0].get("ID")),
                        )
            if not _prop_text(sheet, "Number") or not _prop_text(sheet, "Title"):
                blocking.append(
                    ValidationIssue("SHEET_FIELD_MISSING", Severity.ERROR, "图纸缺少Number或Title", sheet_id),
                )
            blocking.extend(self._property_scope_issues(sheet, sheet_id))

        status = self._classify(blocking, actions)
        return working, RepairReport(status, tuple(actions), tuple(blocking))

    def _property_scope_issues(self, owner: etree._Element, owner_id: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        seen: set[tuple[str, str]] = set()
        for value in owner.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']"):
            name = value.get("propname", "")
            flags = _prop_text(value, "Flags")
            if flags not in {"1", "2"}:
                issues.append(
                    ValidationIssue("CUSTOM_PROPERTY_FLAGS_INVALID", Severity.ERROR, f"自定义属性“{name}”的 Flags 无效", owner_id),
                )
                continue
            key = (flags, name)
            if key in seen:
                issues.append(ValidationIssue("CUSTOM_PROPERTY_DUPLICATED", Severity.ERROR, f"自定义属性“{name}”重复", owner_id))
            seen.add(key)
        return issues

    @staticmethod
    def _new_unique_id(seen: set[str]) -> str:
        while True:
            value = "g" + str(uuid.uuid4()).upper()
            if value not in seen:
                seen.add(value)
                return value

    @staticmethod
    def _classify(blocking: Iterable[ValidationIssue], actions: list[RepairAction]) -> str:
        blocking_list = list(blocking)
        if any(issue.code in _UNRECOVERABLE_CODES for issue in blocking_list):
            return "INVALID_UNRECOVERABLE"
        if blocking_list:
            return "INVALID_REPAIR_REQUIRED"
        if actions:
            return "REPAIRED"
        return "VALID"
