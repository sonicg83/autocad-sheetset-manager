"""AcSm 语义投影校验（PLAN-DB-001 Task 8，SPEC-DB-001 §8）。

解码后的 DOM 与计划期望形状比较：SheetSet/Subset/Sheet/LayoutReference 必需
节点、命名、对象 ID 派生、相对 DWG 路径（裸 dwg_name）与布局 Handle；任何
不一致都是 ERROR 诊断，``ensure_dst_valid`` 统一以 DST_VALIDATION_FAILED 阻断。
"""

from __future__ import annotations

import pytest
from lxml import etree

from dst_builder.domain.models import (
    AssetRole,
    AssetSnapshot,
    DraftProjectV1,
    NumberingInput,
    ProjectInput,
    SheetInput,
    TemplateInput,
)
from dst_builder.domain.planning import commit_revision, create_plan
from dst_builder.infrastructure.acsm.factory import build_dst_bytes
from dst_builder.infrastructure.acsm.projection import (
    DST_VALIDATION_FAILED,
    DstValidationError,
    ensure_dst_valid,
    validate_dst_bytes,
)
from dst_builder.infrastructure.autocad.request import (
    CAD_DRAWING_RESULT_SCHEMA,
    CadDrawingResultV1,
)
from dst_platform.acsm.codec import DstCodec
from dst_platform.contracts.diagnostics import Severity, ValidationIssue


def _make_plan(title: str = "首层平面图"):
    draft = DraftProjectV1(
        project=ProjectInput(
            name="示例工程",
            stage="施工图",
            discipline="建筑",
            output_path="D:/deliveries/example-package",
        ),
        numbering=NumberingInput(prefix="A-", start=1, width=3),
        cad_version="2020",
        sheets=(SheetInput(title=title),),
        template=TemplateInput(
            base_asset_id="3f6b5a24-6a8e-4c2a-9c8f-0f5d7a1b2c31",
            layout_asset_id="8c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
            source_layout="A1",
        ),
    )
    assets = (
        AssetSnapshot(
            role=AssetRole.BASE, relative_path=f"assets/base/{'a' * 64}.dwg", sha256="a" * 64, size=2048
        ),
        AssetSnapshot(
            role=AssetRole.LAYOUT,
            relative_path=f"assets/layout/{'b' * 64}.dwt",
            sha256="b" * 64,
            size=4096,
        ),
    )
    return create_plan(commit_revision(draft, assets))


def _make_cad_result(plan) -> CadDrawingResultV1:
    task = plan.sheetset_task
    return CadDrawingResultV1(
        schema=CAD_DRAWING_RESULT_SCHEMA,
        request_id="req-001",
        layout_name=task.layout_name,
        layout_handle="43D",
        database_version="AC1032",
        layouts=(task.layout_name,),
        diagnostics=(),
        dwg_size=1024,
        dwg_sha256="c" * 64,
        cad_version=plan.cad_version,
    )


def _children(node: etree._Element, local: str) -> list[etree._Element]:
    return [child for child in node if etree.QName(child).localname == local]


def _tamper(data: bytes, mutate) -> bytes:
    """解码 → 修改 DOM → 重新编码为 DST 字节。"""
    root = etree.fromstring(DstCodec().decode_bytes(data))
    mutate(root)
    return DstCodec().encode_bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8"))


def _codes(issues) -> set[str]:
    return {issue.code for issue in issues}


def test_valid_dst_passes_full_validation() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    issues = validate_dst_bytes(build_dst_bytes(plan, result), plan, result)
    assert issues == ()


def test_validation_issue_types_are_shared_platform_types() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    issues = validate_dst_bytes(build_dst_bytes(plan, result), plan, result)
    assert all(isinstance(issue, ValidationIssue) for issue in issues)
    assert all(isinstance(issue.severity, Severity) for issue in issues)


def test_tampered_sheetset_name_reported() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    data = build_dst_bytes(plan, result)

    def mutate(root: etree._Element) -> None:
        sheetset = _children(root, "AcSmSheetSet")[0]
        for child in sheetset:
            if child.get("propname") == "Name":
                child.text = "另一个工程"

    issues = validate_dst_bytes(_tamper(data, mutate), plan, result)
    assert "SHEETSET_NAME_MISMATCH" in _codes(issues)
    assert all(issue.severity is Severity.ERROR for issue in issues)


def test_tampered_layout_handle_reported() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    data = build_dst_bytes(plan, result)

    def mutate(root: etree._Element) -> None:
        sheet = _children(_children(_children(root, "AcSmSheetSet")[0], "AcSmSubset")[0], "AcSmSheet")[0]
        layout = _children(sheet, "AcSmAcDbLayoutReference")[0]
        for child in layout:
            if child.get("propname") == "AcDbHandle":
                child.text = "FFE"

    issues = validate_dst_bytes(_tamper(data, mutate), plan, result)
    assert "LAYOUT_HANDLE_MISMATCH" in _codes(issues)


def test_missing_sheet_reported() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    data = build_dst_bytes(plan, result)

    def mutate(root: etree._Element) -> None:
        subset = _children(_children(root, "AcSmSheetSet")[0], "AcSmSubset")[0]
        for sheet in _children(subset, "AcSmSheet"):
            subset.remove(sheet)

    issues = validate_dst_bytes(_tamper(data, mutate), plan, result)
    assert "SHEET_COUNT" in _codes(issues)


def test_duplicate_object_ids_reported() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    data = build_dst_bytes(plan, result)

    def mutate(root: etree._Element) -> None:
        sheetset = _children(root, "AcSmSheetSet")[0]
        subset = _children(sheetset, "AcSmSubset")[0]
        subset.set("ID", sheetset.get("ID"))

    issues = validate_dst_bytes(_tamper(data, mutate), plan, result)
    assert "DUPLICATE_ACSM_ID" in _codes(issues)


def test_wrong_derived_object_id_reported() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    data = build_dst_bytes(plan, result)

    def mutate(root: etree._Element) -> None:
        sheetset = _children(root, "AcSmSheetSet")[0]
        sheetset.set("ID", "g00000000-0000-0000-0000-000000000001")

    issues = validate_dst_bytes(_tamper(data, mutate), plan, result)
    assert "OBJECT_ID_MISMATCH" in _codes(issues)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("FileName", "drawings/A-001 首层平面图.dwg"),
        ("Relative_FileName", "..\\A-001 首层平面图.dwg"),
        ("Relative_FileName", ".\\drawings\\A-001 首层平面图.dwg"),
    ],
    ids=["prefix-drawings", "parent-escape", "nested-drawings"],
)
def test_dwg_reference_not_bare_dwg_name_reported(field: str, value: str) -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    data = build_dst_bytes(plan, result)

    def mutate(root: etree._Element) -> None:
        sheet = _children(_children(_children(root, "AcSmSheetSet")[0], "AcSmSubset")[0], "AcSmSheet")[0]
        layout = _children(sheet, "AcSmAcDbLayoutReference")[0]
        for child in layout:
            if child.get("propname") == field:
                child.text = value

    issues = validate_dst_bytes(_tamper(data, mutate), plan, result)
    assert "DWG_REFERENCE_INVALID" in _codes(issues)


def test_cad_result_layout_mismatch_reported() -> None:
    plan = _make_plan()
    drifted = CadDrawingResultV1(
        schema=CAD_DRAWING_RESULT_SCHEMA,
        request_id="req-001",
        layout_name="另一个布局",
        layout_handle="43D",
        database_version="AC1032",
        layouts=("另一个布局",),
        diagnostics=(),
        dwg_size=1024,
        dwg_sha256="c" * 64,
        cad_version=plan.cad_version,
    )
    issues = validate_dst_bytes(build_dst_bytes(plan, drifted), plan, drifted)
    assert "CAD_LAYOUT_MISMATCH" in _codes(issues)


def test_corrupt_dst_bytes_reported_not_raised() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    issues = validate_dst_bytes(b"\xff\xff\xff-not-a-dst", plan, result)
    assert "DST_DECODE_INVALID" in _codes(issues)
    assert all(issue.severity is Severity.ERROR for issue in issues)


def test_ensure_dst_valid_raises_dst_validation_failed() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    data = build_dst_bytes(plan, result)

    def mutate(root: etree._Element) -> None:
        sheetset = _children(root, "AcSmSheetSet")[0]
        for child in sheetset:
            if child.get("propname") == "Name":
                child.text = "另一个工程"

    ensure_dst_valid(data, plan, result)  # 不抛
    with pytest.raises(DstValidationError) as excinfo:
        ensure_dst_valid(_tamper(data, mutate), plan, result)
    assert excinfo.value.code == DST_VALIDATION_FAILED == "DST_VALIDATION_FAILED"
    assert excinfo.value.issues
    assert all(issue.severity is Severity.ERROR for issue in excinfo.value.issues)
