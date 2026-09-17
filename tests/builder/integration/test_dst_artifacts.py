"""DST 与图纸目录成果全链路（PLAN-DB-001 Task 8，SPEC-DB-001 §8）。

计划 + CAD 结果 → factory 构造 DST → Codec 编码 → 解码验证（Schema + 语义
投影）→ 图纸目录 XLSX → 验证报告聚合；不一致路径以 DST_VALIDATION_FAILED 阻断。
"""

from __future__ import annotations

import pytest
from lxml import etree

from dst_builder.application.validation import (
    VALIDATION_REPORT_SCHEMA,
    build_validation_report,
)
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
)
from dst_builder.infrastructure.autocad.request import (
    CAD_DRAWING_RESULT_SCHEMA,
    CadDrawingResultV1,
)
from dst_builder.infrastructure.catalog.xlsx import build_sheet_catalog_xlsx
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


def _make_catalog(plan) -> bytes:
    task = plan.sheetset_task
    return build_sheet_catalog_xlsx(
        number=task.sheet_number,
        title=task.sheet_title,
        dwg=task.dwg_path,
        layout=task.layout_name,
    )


def _children(node: etree._Element, local: str) -> list[etree._Element]:
    return [child for child in node if etree.QName(child).localname == local]


def _dst_with_wrong_handle(plan, result) -> bytes:
    """插件返回 Handle 与 DST 内写入 Handle 不一致的情形。"""
    drifted = CadDrawingResultV1(
        schema=CAD_DRAWING_RESULT_SCHEMA,
        request_id="req-001",
        layout_name=result.layout_name,
        layout_handle="FFE",
        database_version=result.database_version,
        layouts=result.layouts,
        diagnostics=(),
        dwg_size=result.dwg_size,
        dwg_sha256=result.dwg_sha256,
        cad_version=result.cad_version,
    )
    return build_dst_bytes(plan, drifted)


def test_full_chain_produces_validated_dst_and_report() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    dst = build_dst_bytes(plan, result)
    catalog = _make_catalog(plan)

    ensure_dst_valid(dst, plan, result)  # Schema + 语义投影全通过

    report = build_validation_report(
        plan=plan, cad_result=result, dst_bytes=dst, catalog_bytes=catalog
    )
    assert report.schema == VALIDATION_REPORT_SCHEMA == "dst-builder.validation-report/v1"
    assert report.plan_id == plan.plan_id
    assert report.revision_id == plan.revision_id
    assert not report.blocking
    assert {check.name for check in report.checks} == {
        "input",
        "dwg",
        "dst",
        "sheet-catalog",
        "reference-boundary",
    }
    versions = dict(report.validator_versions)
    assert versions["acsm-contract"] == "acsm-1.1"
    assert all(
        isinstance(issue, ValidationIssue) and isinstance(issue.severity, Severity)
        for check in report.checks
        for issue in check.issues
    )


def test_full_chain_is_deterministic() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    assert build_dst_bytes(plan, result) == build_dst_bytes(plan, result)
    assert _make_catalog(plan) == _make_catalog(plan)


def test_handle_drift_blocks_dst_and_report() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    wrong = _dst_with_wrong_handle(plan, result)

    with pytest.raises(DstValidationError) as excinfo:
        ensure_dst_valid(wrong, plan, result)
    assert excinfo.value.code == DST_VALIDATION_FAILED

    report = build_validation_report(
        plan=plan, cad_result=result, dst_bytes=wrong, catalog_bytes=_make_catalog(plan)
    )
    assert report.blocking
    dst_check = next(check for check in report.checks if check.name == "dst")
    assert any(issue.severity is Severity.ERROR for issue in dst_check.issues)


def test_tampered_dst_bytes_fail_validation() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    root = etree.fromstring(DstCodec().decode_bytes(build_dst_bytes(plan, result)))
    subset = _children(_children(root, "AcSmSheetSet")[0], "AcSmSubset")[0]
    for child in subset:
        if child.get("propname") == "Name":
            child.text = "结构"
    tampered = DstCodec().encode_bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8"))

    report = build_validation_report(
        plan=plan, cad_result=result, dst_bytes=tampered, catalog_bytes=_make_catalog(plan)
    )
    assert report.blocking
