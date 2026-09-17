"""AcSm 语义投影（SPEC-DB-001 §8）：解码后 DOM 与计划期望形状的比较。

必需节点（一个 SheetSet/Subset/Sheet/LayoutReference）、命名、对象 ID 的
UUIDv5 派生、相对 DWG 路径（裸 ``dwg_name``，DST 与 DWG 同目录）与布局
Handle 必须与计划及插件返回的实际 DWG 结果一致；任何不一致都是 ERROR 级
共享诊断（:class:`dst_platform.contracts.diagnostics.ValidationIssue`），
``ensure_dst_valid`` 统一以 ``DST_VALIDATION_FAILED`` 阻断发布。
"""

from __future__ import annotations

import re

from lxml import etree

from dst_builder.domain.models import GenerationPlanV1
from dst_builder.infrastructure.acsm.factory import (
    DST_DATABASE_CLSID,
    DST_DB_VERSION,
    dst_object_id,
)
from dst_builder.infrastructure.autocad.request import CadDrawingResultV1
from dst_platform.acsm.codec import CodecError, DstCodec
from dst_platform.acsm.contract import validate_contract, validate_schema
from dst_platform.contracts.diagnostics import Severity, ValidationIssue

__all__ = [
    "DST_VALIDATION_FAILED",
    "DstValidationError",
    "ensure_dst_valid",
    "project_dst_plan",
    "validate_dst_bytes",
]

DST_VALIDATION_FAILED = "DST_VALIDATION_FAILED"

_HANDLE_PATTERN = re.compile(r"^[0-9A-Fa-f]+$")


class DstValidationError(Exception):
    """§8/§11 阻断错误：DST 编码/Schema/语义校验失败，code 固定。"""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = tuple(issues)
        self.code = DST_VALIDATION_FAILED
        super().__init__(
            f"DST 验证失败（{self.code}）：{len(self.issues)} 个诊断"
        )


def _local(node: etree._Element) -> str:
    return etree.QName(node).localname


def _children(node: etree._Element, local: str) -> list[etree._Element]:
    return [child for child in node if _local(child) == local]


def _prop(node: etree._Element, name: str) -> str | None:
    for child in node:
        if _local(child) == "AcSmProp" and child.get("propname") == name:
            return (child.text or "").strip()
    return None


def _issue(code: str, message: str, object_id: str | None = None) -> ValidationIssue:
    return ValidationIssue(code, Severity.ERROR, message, object_id)


def _bare_dwg_reference(value: str | None) -> str | None:
    """把布局引用值规范化为同目录裸文件名；含目录成分时返回 None。"""
    if not value:
        return None
    normalized = value.replace("\\", "/").removeprefix("./")
    if "/" in normalized or normalized.startswith(".."):
        return None
    return normalized


def project_dst_plan(
    root: etree._Element,
    plan: GenerationPlanV1,
    cad_result: CadDrawingResultV1,
) -> tuple[ValidationIssue, ...]:
    """比较解码后 DOM 与计划期望形状；返回全部 ERROR 级不一致诊断。"""
    task = plan.sheetset_task
    sha256 = plan.plan_sha256
    issues: list[ValidationIssue] = []

    if _local(root) != "AcSmDatabase":
        return (_issue("DST_ROOT_INVALID", f"DST 根必须是 AcSmDatabase，实际为 {_local(root)}"),)
    if _prop(root, "DbVersion") != DST_DB_VERSION:
        issues.append(_issue("DATABASE_VERSION_MISMATCH", f"AcSm 数据库版本应为 {DST_DB_VERSION}"))
    if root.get("clsid") != DST_DATABASE_CLSID:
        issues.append(_issue("DATABASE_CLSID_MISMATCH", "AcSmDatabase clsid 不符合稳定共享包约定"))

    sheetsets = _children(root, "AcSmSheetSet")
    if len(sheetsets) != 1:
        issues.append(_issue("SHEETSET_COUNT", f"必须恰好有一个 AcSmSheetSet，实际 {len(sheetsets)} 个"))
        return tuple(issues)
    sheetset = sheetsets[0]
    if _prop(sheetset, "Name") != task.sheetset_name:
        issues.append(
            _issue("SHEETSET_NAME_MISMATCH", f"图纸集名应为 {task.sheetset_name!r}", sheetset.get("ID"))
        )
    _check_object_id(issues, sheetset, sha256, "sheetset", "图纸集")

    subsets = _children(sheetset, "AcSmSubset")
    if len(subsets) != 1:
        issues.append(_issue("SUBSET_COUNT", f"必须恰好有一个 AcSmSubset，实际 {len(subsets)} 个"))
        return tuple(issues)
    subset = subsets[0]
    if _prop(subset, "Name") != task.subset_name:
        issues.append(_issue("SUBSET_NAME_MISMATCH", f"分组名应为 {task.subset_name!r}", subset.get("ID")))
    _check_object_id(issues, subset, sha256, "subset", "分组")

    sheets = _children(subset, "AcSmSheet")
    if len(sheets) != 1:
        issues.append(_issue("SHEET_COUNT", f"必须恰好有一个 AcSmSheet，实际 {len(sheets)} 个"))
        return tuple(issues)
    sheet = sheets[0]
    if _prop(sheet, "Number") != task.sheet_number:
        issues.append(_issue("SHEET_NUMBER_MISMATCH", f"图号应为 {task.sheet_number!r}", sheet.get("ID")))
    if _prop(sheet, "Title") != task.sheet_title:
        issues.append(_issue("SHEET_TITLE_MISMATCH", f"图名应为 {task.sheet_title!r}", sheet.get("ID")))
    _check_object_id(issues, sheet, sha256, "sheet", "图纸")

    layouts = _children(sheet, "AcSmAcDbLayoutReference")
    if len(layouts) != 1:
        issues.append(
            _issue("SHEET_LAYOUT_COUNT", f"图纸必须恰好有一个布局引用，实际 {len(layouts)} 个", sheet.get("ID"))
        )
        return tuple(issues)
    layout = layouts[0]
    _check_object_id(issues, layout, sha256, "layout-reference", "布局引用")
    if _prop(layout, "Name") != task.layout_name:
        issues.append(_issue("LAYOUT_NAME_MISMATCH", f"布局名应为 {task.layout_name!r}", layout.get("ID")))

    handle = _prop(layout, "AcDbHandle")
    if not handle or handle == "0" or not _HANDLE_PATTERN.fullmatch(handle):
        issues.append(_issue("LAYOUT_HANDLE_INVALID", f"布局 Handle 非法：{handle!r}", layout.get("ID")))
    elif handle != cad_result.layout_handle:
        issues.append(
            _issue(
                "LAYOUT_HANDLE_MISMATCH",
                f"布局 Handle 应为插件返回的 {cad_result.layout_handle!r}，实际 {handle!r}",
                layout.get("ID"),
            )
        )

    expected_dwg = task.dwg_path
    for field, code in (("FileName", "DWG_REFERENCE_INVALID"), ("Relative_FileName", "DWG_REFERENCE_INVALID")):
        if _bare_dwg_reference(_prop(layout, field)) != expected_dwg:
            issues.append(
                _issue(code, f"布局 {field} 必须只引用同目录 {expected_dwg!r}", layout.get("ID"))
            )

    if cad_result.layout_name != plan.drawing_task.target_layout or cad_result.layout_name != task.layout_name:
        issues.append(
            _issue("CAD_LAYOUT_MISMATCH", f"插件布局名 {cad_result.layout_name!r} 与计划不一致", layout.get("ID"))
        )

    issues.extend(_duplicate_id_issues(root))
    return tuple(issues)


def _check_object_id(
    issues: list[ValidationIssue],
    node: etree._Element,
    plan_sha256: str,
    semantic_path: str,
    label: str,
) -> None:
    expected = dst_object_id(plan_sha256, semantic_path)
    if node.get("ID") != expected:
        issues.append(
            _issue("OBJECT_ID_MISMATCH", f"{label}对象 ID 应为计划派生的 {expected}", node.get("ID"))
        )


def _duplicate_id_issues(root: etree._Element) -> tuple[ValidationIssue, ...]:
    seen: set[str] = set()
    issues: list[ValidationIssue] = []
    for node in root.iter():
        object_id = node.get("ID")
        if not object_id:
            continue
        key = object_id.casefold()
        if key in seen:
            issues.append(_issue("DUPLICATE_ACSM_ID", f"AcSm ID 重复：{object_id}", object_id))
        seen.add(key)
    return tuple(issues)


def validate_dst_bytes(
    data: bytes,
    plan: GenerationPlanV1,
    cad_result: CadDrawingResultV1,
) -> tuple[ValidationIssue, ...]:
    """DST 二进制 → 共享 Codec 解码 → 契约/XSD Schema → 语义投影全链校验。"""
    try:
        xml = DstCodec().decode_bytes(data)
    except CodecError as error:
        return (_issue("DST_DECODE_INVALID", str(error)),)
    root = etree.fromstring(xml)
    return (
        *validate_contract(root),
        *validate_schema(root),
        *project_dst_plan(root, plan, cad_result),
    )


def ensure_dst_valid(
    data: bytes,
    plan: GenerationPlanV1,
    cad_result: CadDrawingResultV1,
) -> None:
    """任何校验 ERROR 都以 :class:`DstValidationError`（DST_VALIDATION_FAILED）阻断。"""
    issues = validate_dst_bytes(data, plan, cad_result)
    if any(issue.severity is Severity.ERROR for issue in issues):
        raise DstValidationError(issues)
