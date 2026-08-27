"""DST XML 内存修复器与可审计 RepairReport 测试。

失败样本 `sheetset-fail.xml` 只从 `docs/shared/research/...` 复制到 pytest
临时目录后使用，绝不修改样本原件。
"""
from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from dst_manager.infrastructure.acsm_xml.contract import validate_contract
from dst_manager.infrastructure.acsm_xml.repair import AcsmRepairer

GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "shared"
    / "research"
    / "project1-dst-xml"
    / "project1_sheetset.xml"
)
FAIL = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "shared"
    / "research"
    / "project1-dst-xml"
    / "sheetset-fail.xml"
)

_ID_FORMAT = re.compile(r"^g[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")

# 一张结构完整（含 bag/layout/Number/Title/SheetViews）的最小图纸
TEMPLATE = (
    '<AcSmDatabase ID="g00000000-0000-0000-0000-200000000001" clsid="x">'
    '<AcSmProp propname="DbVersion" vt="8">1.1</AcSmProp>'
    '<AcSmSheetSet ID="g00000000-0000-0000-0000-200000000002" '
    'clsid="gB20534F2-0978-418C-8D14-2E6928A077ED" propname="SheetSet" vt="13">'
    '<AcSmSubset ID="g00000000-0000-0000-0000-200000000003" '
    'clsid="g076D548F-B0F5-4FE1-B35D-7F7B73B8D322">'
    '<AcSmSheet ID="g00000000-0000-0000-0000-200000000004" '
    'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065">'
    '<AcSmCustomPropertyBag ID="g00000000-0000-0000-0000-200000000005" '
    'clsid="g4D103908-8C86-4D95-BBF4-68B9A7B00731" propname="CustomPropertyBag" vt="13">'
    '<AcSmCustomPropertyValue ID="g00000000-0000-0000-0000-200000000006" '
    'clsid="g8D22A2A4-1777-4D78-84CC-69EF741FE954" propname="图幅" vt="13">'
    '<AcSmProp propname="Flags" vt="3">2</AcSmProp>'
    '</AcSmCustomPropertyValue>'
    '</AcSmCustomPropertyBag>'
    '<AcSmAcDbLayoutReference ID="g00000000-0000-0000-0000-200000000007" '
    'clsid="g94910E94-4FCA-427C-B6ED-2EC9E1C900C7" propname="Layout" vt="13">'
    '<AcSmProp propname="AcDbHandle" vt="8">AB</AcSmProp>'
    '<AcSmProp propname="FileName" vt="8">C:\\x.dwg</AcSmProp>'
    '<AcSmProp propname="Name" vt="8">001</AcSmProp>'
    '<AcSmProp propname="Relative_FileName" vt="8">.\\x.dwg</AcSmProp>'
    '</AcSmAcDbLayoutReference>'
    '<AcSmProp propname="Number" vt="8">001</AcSmProp>'
    '<AcSmSheetViews ID="g00000000-0000-0000-0000-200000000008" '
    'clsid="gF40F931B-64BC-4B90-9FC8-A11A77D6815B" propname="SheetViews" vt="13"/>'
    '<AcSmProp propname="Title" vt="8">T</AcSmProp>'
    '</AcSmSheet>'
    '</AcSmSubset>'
    '</AcSmSheetSet>'
    '</AcSmDatabase>'
)


def _repair(xml_bytes: bytes):
    root = etree.fromstring(xml_bytes)
    repaired, report = AcsmRepairer().repair(root)
    return root, repaired, report


def _codes(report) -> set[str]:
    return {action.code for action in report.actions}


# ---------------------------------------------------------------- 黄金 no-op

def test_golden_returns_valid_with_no_actions():
    root = etree.fromstring(GOLDEN.read_bytes())
    repaired, report = AcsmRepairer().repair(root)
    assert report.status == "VALID"
    assert report.actions == ()
    assert report.blocking_issues == ()
    # 序列化保持一致，原始 root 未被修改
    assert etree.tostring(repaired) == etree.tostring(root)


def test_repair_never_mutates_input_root():
    xml = GOLDEN.read_bytes()
    root = etree.fromstring(xml)
    before = etree.tostring(root)
    AcsmRepairer().repair(root)
    assert etree.tostring(root) == before


# ---------------------------------------------------------------- 失败样本修复

def test_fail_samples_repair_in_memory(tmp_path):
    dst = tmp_path / "sheetset-fail.xml"
    dst.write_bytes(FAIL.read_bytes())
    root = etree.fromstring(dst.read_bytes())
    repaired, report = AcsmRepairer().repair(root)

    assert report.status == "REPAIRED"
    assert report.blocking_issues == ()
    codes = _codes(report)
    # 覆盖缺失的 clsid、固定属性和 vt
    assert "REPAIR_ATTR_MISSING" in codes
    assert "PROP_VT_MISSING" in codes
    # 11 张缺 clsid 的 sheet 与 11 张缺 SheetViews 的 sheet 均被修复
    assert sum(1 for a in report.actions if a.code == "REPAIR_SHEET_VIEWS_MISSING") >= 11

    # 每个生成 ID 都符合 g+UUID 格式且全局唯一
    generated = {a.after["ID"] for a in report.actions if a.code in {"REPAIR_ID_MISSING", "REPAIR_SHEET_VIEWS_MISSING"}}
    generated = {value for value in generated if value}
    for value in generated:
        assert _ID_FORMAT.fullmatch(value)
    seen: set[str] = set()
    for node in repaired.iter():
        object_id = node.get("ID")
        if object_id:
            key = object_id.casefold()
            assert key not in seen, f"修复后仍存在重复 ID：{object_id}"
            seen.add(key)

    # 修复后满足 contract 校验
    assert validate_contract(repaired) == []
    # 每张图纸都补齐了 AcSmSheetViews
    for sheet in repaired.xpath("//*[local-name()='AcSmSheet']"):
        views = [c for c in sheet if etree.QName(c).localname == "AcSmSheetViews"]
        assert len(views) == 1


def test_fail_source_file_untouched(tmp_path):
    dst = tmp_path / "sheetset-fail.xml"
    dst.write_bytes(FAIL.read_bytes())
    before_bytes = dst.read_bytes()
    root = etree.fromstring(dst.read_bytes())
    AcsmRepairer().repair(root)
    assert dst.read_bytes() == before_bytes


# ---------------------------------------------------------------- 负例阻断

def _parse_single_sheet(sheet_fragment: str) -> bytes:
    return TEMPLATE.replace(
        (
            '<AcSmSheet ID="g00000000-0000-0000-0000-200000000004" '
            'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065">'
        ),
        sheet_fragment,
        1,
    ).encode()


def test_duplicate_id_is_unrecoverable():
    xml = (
        b'<AcSmDatabase ID="g00000000-0000-0000-0000-200000000001" clsid="x">'
        b'<AcSmSheetSet ID="g00000000-0000-0000-0000-200000000002" '
        b'clsid="gB20534F2-0978-418C-8D14-2E6928A077ED" propname="SheetSet" vt="13">'
        b'<AcSmSubset ID="g00000000-0000-0000-0000-200000000003" '
        b'clsid="g076D548F-B0F5-4FE1-B35D-7F7B73B8D322">'
        b'<AcSmSheet ID="g00000000-0000-0000-0000-200000000004" '
        b'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"/>'
        b'</AcSmSubset><AcSmSubset ID="g00000000-0000-0000-0000-200000000009" '
        b'clsid="g076D548F-B0F5-4FE1-B35D-7F7B73B8D322">'
        b'<AcSmSheet ID="g00000000-0000-0000-0000-200000000004" '
        b'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"/>'
        b'</AcSmSubset></AcSmSheetSet></AcSmDatabase>'
    )
    _, _, report = _repair(xml)
    assert report.status == "INVALID_UNRECOVERABLE"
    assert any(issue.code == "DUPLICATE_ACSM_ID" for issue in report.blocking_issues)


def test_nonempty_wrong_clsid_not_overwritten():
    xml = TEMPLATE.replace(
        'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"',
        'clsid="g16A07941-BC15-4D48-A880-9D5A211D5BAD"',
        1,
    ).encode()
    root, repaired, report = _repair(xml)
    assert report.status == "INVALID_REPAIR_REQUIRED"
    sheet = repaired.xpath("//*[local-name()='AcSmSheet']")[0]
    # 非空错误 clsid 不得被静默覆盖
    assert sheet.get("clsid") == "g16A07941-BC15-4D48-A880-9D5A211D5BAD"
    assert root is not None

def test_missing_business_value_is_blocked():
    # 移除 Title 业务值
    xml = TEMPLATE.replace('<AcSmProp propname="Title" vt="8">T</AcSmProp>', "", 1).encode()
    _, _, report = _repair(xml)
    assert report.status == "INVALID_REPAIR_REQUIRED"
    assert any(issue.code == "SHEET_FIELD_MISSING" for issue in report.blocking_issues)


def test_missing_layout_is_blocked():
    xml = TEMPLATE.replace(
        (
            '<AcSmAcDbLayoutReference ID="g00000000-0000-0000-0000-200000000007" '
            'clsid="g94910E94-4FCA-427C-B6ED-2EC9E1C900C7" propname="Layout" vt="13">'
            '<AcSmProp propname="AcDbHandle" vt="8">AB</AcSmProp>'
            '<AcSmProp propname="FileName" vt="8">C:\\x.dwg</AcSmProp>'
            '<AcSmProp propname="Name" vt="8">001</AcSmProp>'
            '<AcSmProp propname="Relative_FileName" vt="8">.\\x.dwg</AcSmProp>'
            '</AcSmAcDbLayoutReference>'
        ),
        "",
        1,
    ).encode()
    _, _, report = _repair(xml)
    assert report.status == "INVALID_REPAIR_REQUIRED"
    assert any(issue.code == "SHEET_LAYOUT_COUNT" for issue in report.blocking_issues)


def test_multiple_layouts_are_blocked():
    first = (
        '<AcSmAcDbLayoutReference ID="g00000000-0000-0000-0000-200000000007" '
        'clsid="g94910E94-4FCA-427C-B6ED-2EC9E1C900C7" propname="Layout" vt="13">'
        '<AcSmProp propname="AcDbHandle" vt="8">AB</AcSmProp>'
        '<AcSmProp propname="FileName" vt="8">C:\\x.dwg</AcSmProp>'
        '<AcSmProp propname="Name" vt="8">001</AcSmProp>'
        '<AcSmProp propname="Relative_FileName" vt="8">.\\x.dwg</AcSmProp>'
        '</AcSmAcDbLayoutReference>'
    )
    second = first.replace(
        'ID="g00000000-0000-0000-0000-200000000007"',
        'ID="g00000000-0000-0000-0000-20000000000A"',
        1,
    )
    xml = TEMPLATE.replace(first, first + second, 1).encode()
    _, _, report = _repair(xml)
    assert report.status == "INVALID_REPAIR_REQUIRED"
    assert any(issue.code == "SHEET_LAYOUT_COUNT" for issue in report.blocking_issues)


def test_property_scope_conflict_is_blocked():
    # Flags 缺失/非法 -> 属性作用域无法判定
    xml = TEMPLATE.replace('<AcSmProp propname="Flags" vt="3">2</AcSmProp>', '<AcSmProp propname="Flags" vt="3">9</AcSmProp>', 1).encode()
    _, _, report = _repair(xml)
    assert report.status == "INVALID_REPAIR_REQUIRED"
    assert any(issue.code == "CUSTOM_PROPERTY_FLAGS_INVALID" for issue in report.blocking_issues)
