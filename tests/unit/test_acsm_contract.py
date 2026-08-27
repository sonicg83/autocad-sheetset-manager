"""AcSm contract registry 与标准 XSD 的结构契约测试。

黄金样本来自 `docs/shared/research/project1-dst-xml/project1_sheetset.xml`，
只读使用；失败样本 `sheetset-fail.xml` 仅供上层可修复加载测试复用。
"""
from __future__ import annotations

from pathlib import Path

from lxml import etree

from dst_manager.infrastructure.acsm_xml.contract import (
    CLSID_LAYOUT_REFERENCE,
    CLSID_PROPERTY_BAG,
    CLSID_PROPERTY_VALUE,
    CLSID_SHEET,
    CLSID_SHEET_VIEWS,
    CLSID_SHEETSET,
    CLSID_SUBSET,
    CONTRACT_VERSION,
    expected_prop_vt,
    object_contract,
    validate_contract,
    validate_schema,
)

GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "shared"
    / "research"
    / "project1-dst-xml"
    / "project1_sheetset.xml"
)

_DB_ID = "g00000000-0000-0000-0000-100000000001"


def _base_xml() -> bytes:
    return (
        f'<AcSmDatabase ID="{_DB_ID}" clsid="g2162C6B6-0CE4-40E8-912B-46F59DFDF826">'
        '<AcSmProp propname="DbVersion" vt="8">1.1</AcSmProp>'
        '<AcSmSheetSet ID="g00000000-0000-0000-0000-100000000002" '
        'clsid="gB20534F2-0978-418C-8D14-2E6928A077ED" propname="SheetSet" vt="13">'
        '<AcSmSubset ID="g00000000-0000-0000-0000-100000000003" '
        'clsid="g076D548F-B0F5-4FE1-B35D-7F7B73B8D322">'
        '<AcSmSheet ID="g00000000-0000-0000-0000-100000000004" '
        'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065">'
        '<AcSmProp propname="Number" vt="8">001</AcSmProp>'
        '</AcSmSheet>'
        '</AcSmSubset>'
        '</AcSmSheetSet>'
        '</AcSmDatabase>'
    ).encode()


def _parse(xml: bytes) -> etree._Element:
    return etree.fromstring(xml)


def _codes(issues) -> set[str]:
    return {issue.code for issue in issues}


# ---------------------------------------------------------------- 黄金样本

def test_golden_sheetset_passes_contract_and_schema():
    """Project1 黄金样本经 contract 与 XSD 校验无错误。"""
    root = _parse(GOLDEN.read_bytes())
    assert validate_contract(root) == []
    assert validate_schema(root) == []


def test_golden_sheets_require_id_and_fixed_clsid_only():
    """黄金 AcSmSheet 根节点只用 ID + 固定 clsid，不要求 propname/vt。"""
    root = _parse(GOLDEN.read_bytes())
    for sheet in root.xpath("//*[local-name()='AcSmSheet']"):
        assert "ID" in sheet.attrib
        assert sheet.get("clsid") == CLSID_SHEET
        assert "propname" not in sheet.attrib
        assert "vt" not in sheet.attrib


# ---------------------------------------------------------------- 固定 ID 表

def test_fixed_id_table_covers_seven_object_types():
    sheet_set = object_contract("AcSmSheetSet")
    assert sheet_set.required_attributes == frozenset({"ID", "clsid", "propname", "vt"})
    assert sheet_set.fixed_attributes == {"clsid": CLSID_SHEETSET, "propname": "SheetSet", "vt": "13"}

    subset = object_contract("AcSmSubset")
    assert subset.required_attributes == frozenset({"ID", "clsid"})
    assert subset.fixed_attributes == {"clsid": CLSID_SUBSET}

    sheet = object_contract("AcSmSheet")
    assert sheet.required_attributes == frozenset({"ID", "clsid"})
    assert sheet.fixed_attributes == {"clsid": CLSID_SHEET}

    bag = object_contract("AcSmCustomPropertyBag")
    assert bag.required_attributes == frozenset({"ID", "clsid", "propname", "vt"})
    assert bag.fixed_attributes == {"clsid": CLSID_PROPERTY_BAG, "propname": "CustomPropertyBag", "vt": "13"}

    value = object_contract("AcSmCustomPropertyValue")
    assert value.required_attributes == frozenset({"ID", "clsid", "propname", "vt"})
    assert value.fixed_attributes == {"clsid": CLSID_PROPERTY_VALUE, "vt": "13"}

    layout = object_contract("AcSmAcDbLayoutReference")
    assert layout.required_attributes == frozenset({"ID", "clsid", "propname", "vt"})
    assert layout.fixed_attributes == {"clsid": CLSID_LAYOUT_REFERENCE, "vt": "13"}

    views = object_contract("AcSmSheetViews")
    assert views.required_attributes == frozenset({"ID", "clsid", "propname", "vt"})
    assert views.fixed_attributes == {"clsid": CLSID_SHEET_VIEWS, "propname": "SheetViews", "vt": "13"}

    assert object_contract("AcSmProp") is None
    assert object_contract("AcSmFileReference") is None
    assert CONTRACT_VERSION == "acsm-1.1"


# ---------------------------------------------------------------- 属性类型表

def test_property_vt_table_distinguishes_types():
    # 文本（8）
    assert expected_prop_vt("AcSmSheet", "Number") == "8"
    assert expected_prop_vt("AcSmSheet", "Title") == "8"
    assert expected_prop_vt("AcSmCustomPropertyValue", "Value") == "8"
    assert expected_prop_vt("AcSmAcDbLayoutReference", "AcDbHandle") == "8"
    assert expected_prop_vt("AcSmAcDbLayoutReference", "FileName") == "8"
    assert expected_prop_vt("AcSmAcDbLayoutReference", "Name") == "8"
    assert expected_prop_vt("AcSmAcDbLayoutReference", "Relative_FileName") == "8"
    # 整数（3）
    assert expected_prop_vt("AcSmCustomPropertyValue", "Flags") == "3"
    assert expected_prop_vt("AcSmDatabase", "FileRevision") == "3"
    # 布尔（2）：非文本样本，禁止默认成 8
    assert expected_prop_vt("AcSmSheetSet", "PromptForDwt") == "2"
    assert expected_prop_vt("AcSmPublishOptions", "DwfType") == "2"


def test_property_vt_table_does_not_default_everything_to_text():
    assert expected_prop_vt("AcSmCustomPropertyValue", "Flags") != "8"
    assert expected_prop_vt("AcSmDatabase", "FileRevision") != "8"
    assert expected_prop_vt("AcSmSheetSet", "PromptForDwt") != "8"
    # 未知属性名宽容返回 None
    assert expected_prop_vt("AcSmSheet", "未知字段") is None


# ---------------------------------------------------------------- 宽容与负例

def test_unknown_element_attribute_order_tail_are_ignored():
    xml = _base_xml().replace(
        b'<AcSmProp propname="Number" vt="8">001</AcSmProp>',
        (
            b'<AcSmProp propname="Number" vt="8">001</AcSmProp>'
            b'<UnknownObject extra="keep" />tail'
            b'<AcSmSheetViews ID="g00000000-0000-0000-0000-100000000005" '
            b'clsid="gF40F931B-64BC-4B90-9FC8-A11A77D6815B" '
            b'propname="SheetViews" vt="13" />'
        ),
        1,
    )
    root = _parse(xml)
    assert validate_contract(root) == []
    assert validate_schema(root) == []


def test_contract_reports_missing_id():
    xml = _base_xml().replace(
        b'ID="g00000000-0000-0000-0000-100000000004" clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"',
        b'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"',
        1,
    )
    root = _parse(xml)
    assert "CONTRACT_ATTRIBUTE_MISSING" in _codes(validate_contract(root))


def test_contract_reports_wrong_fixed_attribute():
    xml = _base_xml().replace(b'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"', b'clsid="g00000000-0000-0000-0000-999999999999"', 1)
    root = _parse(xml)
    assert "CONTRACT_ATTRIBUTE_VALUE" in _codes(validate_contract(root))


def test_contract_reports_wrong_vt():
    xml = _base_xml().replace(b'<AcSmProp propname="Number" vt="8">001</AcSmProp>', b'<AcSmProp propname="Number" vt="7">001</AcSmProp>', 1)
    root = _parse(xml)
    assert "PROP_VT_MISMATCH" in _codes(validate_contract(root))


def test_contract_reports_missing_vt():
    xml = _base_xml().replace(b'<AcSmProp propname="Number" vt="8">001</AcSmProp>', b'<AcSmProp propname="Number">001</AcSmProp>', 1)
    root = _parse(xml)
    assert "PROP_VT_MISSING" in _codes(validate_contract(root))


def test_contract_reports_wrong_hierarchy():
    # AcSmSubset 直属 AcSmDatabase 节点（父级应为 AcSmSheetSet）
    xml = (
        f'<AcSmDatabase ID="{_DB_ID}" clsid="x">'
        '<AcSmSubset ID="g00000000-0000-0000-0000-100000000006" clsid="g076D548F-B0F5-4FE1-B35D-7F7B73B8D322"/>'
        '</AcSmDatabase>'
    ).encode()
    root = _parse(xml)
    assert "CONTRACT_PARENT_INVALID" in _codes(validate_contract(root))


def test_schema_rejects_wrong_root():
    xml = _base_xml().replace(b'<AcSmDatabase', b'<Foo', 1).replace(b'</AcSmDatabase>', b'</Foo>', 1)
    root = _parse(xml)
    assert "XSD_INVALID" in _codes(validate_schema(root))
