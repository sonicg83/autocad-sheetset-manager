"""Builder AcSm factory 确定性构造（PLAN-DB-001 Task 8，SPEC-DB-001 §8）。

覆盖：同一计划 + CAD 结果两次构造 XML 字节一致；对象 ID（SheetSet/Subset/
Sheet/LayoutReference）由计划哈希 + 语义路径 UUIDv5 派生且不同计划必然不同；
必需节点结构、命名与 Handle；Codec 编码往返。factory 从零构造，不读模板 DST。
"""

from __future__ import annotations

import re

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
from dst_builder.infrastructure.acsm.factory import (
    DST_DB_VERSION,
    build_dst_bytes,
    build_dst_xml,
    dst_object_id,
)
from dst_builder.infrastructure.autocad.request import (
    CAD_DRAWING_RESULT_SCHEMA,
    CadDrawingResultV1,
)
from dst_platform.acsm.codec import DstCodec


def _make_plan(title: str = "首层平面图") -> object:
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


def _prop(node: etree._Element, name: str) -> str | None:
    for child in node:
        if etree.QName(child).localname == "AcSmProp" and child.get("propname") == name:
            return (child.text or "").strip()
    return None


def _collect_ids(xml: bytes) -> dict[str, str]:
    """按语义角色收集对象 ID（database/sheetset/subset/sheet/layout-reference）。"""
    root = etree.fromstring(xml)
    sheetset = _children(root, "AcSmSheetSet")[0]
    subset = _children(sheetset, "AcSmSubset")[0]
    sheet = _children(subset, "AcSmSheet")[0]
    layout = _children(sheet, "AcSmAcDbLayoutReference")[0]
    return {
        "database": root.get("ID"),
        "sheetset": sheetset.get("ID"),
        "subset": subset.get("ID"),
        "sheet": sheet.get("ID"),
        "layout-reference": layout.get("ID"),
    }


_ID_PATTERN = re.compile(r"g[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}")


def test_same_plan_and_cad_result_produce_identical_xml_bytes() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    assert build_dst_xml(plan, result) == build_dst_xml(plan, result)


def test_object_ids_are_uuid5_derived_from_plan_hash() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    ids = _collect_ids(build_dst_xml(plan, result))
    assert ids == {
        "database": dst_object_id(plan.plan_sha256, "database"),
        "sheetset": dst_object_id(plan.plan_sha256, "sheetset"),
        "subset": dst_object_id(plan.plan_sha256, "subset"),
        "sheet": dst_object_id(plan.plan_sha256, "sheet"),
        "layout-reference": dst_object_id(plan.plan_sha256, "layout-reference"),
    }
    assert all(_ID_PATTERN.fullmatch(oid) for oid in ids.values())


def test_different_plan_changes_object_ids() -> None:
    plan_a = _make_plan()
    plan_b = _make_plan(title="二层平面图")
    ids_a = _collect_ids(build_dst_xml(plan_a, _make_cad_result(plan_a)))
    ids_b = _collect_ids(build_dst_xml(plan_b, _make_cad_result(plan_b)))
    assert set(ids_a) == set(ids_b)
    assert all(ids_a[key] != ids_b[key] for key in ids_a)


def test_required_structure_names_and_handle() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    root = etree.fromstring(build_dst_xml(plan, result))
    assert etree.QName(root).localname == "AcSmDatabase"
    assert _prop(root, "DbVersion") == DST_DB_VERSION

    sheetsets = _children(root, "AcSmSheetSet")
    assert len(sheetsets) == 1
    sheetset = sheetsets[0]
    assert _prop(sheetset, "Name") == plan.sheetset_task.sheetset_name

    subsets = _children(sheetset, "AcSmSubset")
    assert len(subsets) == 1
    assert _prop(subsets[0], "Name") == plan.sheetset_task.subset_name

    sheets = _children(subsets[0], "AcSmSheet")
    assert len(sheets) == 1
    sheet = sheets[0]
    assert _prop(sheet, "Number") == plan.sheetset_task.sheet_number
    assert _prop(sheet, "Title") == plan.sheetset_task.sheet_title

    layouts = _children(sheet, "AcSmAcDbLayoutReference")
    assert len(layouts) == 1
    layout = layouts[0]
    # 布局名来自计划，Handle 来自插件返回的实际 DWG 结果
    assert _prop(layout, "Name") == plan.sheetset_task.layout_name
    assert _prop(layout, "AcDbHandle") == result.layout_handle
    # DST 与 DWG 同目录：引用只保存裸 dwg_name
    assert _prop(layout, "FileName") == plan.sheetset_task.dwg_path
    assert _prop(layout, "Relative_FileName") == f".\\{plan.sheetset_task.dwg_path}"


def test_encoded_dst_roundtrips_to_factory_xml() -> None:
    plan = _make_plan()
    result = _make_cad_result(plan)
    encoded = build_dst_bytes(plan, result)
    assert encoded != build_dst_xml(plan, result)  # byte-translate 必须真实发生
    decoded = DstCodec().decode_bytes(encoded)
    assert decoded == build_dst_xml(plan, result)
