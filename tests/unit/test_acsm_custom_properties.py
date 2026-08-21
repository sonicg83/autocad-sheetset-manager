from pathlib import Path

import pytest
from lxml import etree

from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.acsm_xml.document import AcsmValidationError
from dst_manager.infrastructure.dst_codec import DstCodec


def _sheet_property(document: AcsmDocument, sheet_id: str, name: str = "比例"):
    matches = document.root.xpath(
        "//*[@ID=$sheet_id and local-name()='AcSmSheet']"
        "/*[local-name()='AcSmCustomPropertyBag']"
        "/*[local-name()='AcSmCustomPropertyValue' and @propname=$name]",
        sheet_id=sheet_id,
        name=name,
    )
    assert len(matches) == 1
    return matches[0]


def _props(node, name: str):
    return [child for child in node if etree.QName(child).localname == "AcSmProp" and child.get("propname") == name]


def test_missing_value_and_submitted_empty_is_dom_noop(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    node = _sheet_property(document, sheet_id)
    node.remove(_props(node, "Value")[0])
    before = document.semantic_bytes()

    document.apply_metadata_commands([{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": ""}}])

    assert document.semantic_bytes() == before
    assert not _props(node, "Value")
    assert _props(node, "Flags")[0].text == "2"


def test_explicit_empty_value_and_submitted_empty_is_dom_noop(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    node = _sheet_property(document, sheet_id)
    _props(node, "Value")[0].text = ""
    before = document.semantic_bytes()

    document.apply_metadata_commands([{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": ""}}])

    assert document.semantic_bytes() == before


def test_clearing_nonempty_value_removes_value_and_preserves_flags(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    node = _sheet_property(document, sheet_id)

    document.apply_metadata_commands([{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": ""}}])

    assert not _props(node, "Value")
    assert len(_props(node, "Flags")) == 1
    assert _props(node, "Flags")[0].text == "2"


def test_nonempty_value_is_created_after_flags_with_verified_shape(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    node = _sheet_property(document, sheet_id)
    node.remove(_props(node, "Value")[0])

    document.apply_metadata_commands([{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "1:500"}}])

    children = [child for child in node if etree.QName(child).localname == "AcSmProp"]
    assert [(child.get("propname"), child.get("vt"), child.text) for child in children] == [
        ("Flags", "3", "2"),
        ("Value", "8", "1:500"),
    ]


def test_sheet_command_rejects_sheetset_scope(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    flags = _props(_sheet_property(document, sheet_id), "Flags")[0]
    flags.text = "1"

    with pytest.raises(AcsmValidationError, match="CUSTOM_PROPERTY_SCOPE_MISMATCH"):
        document.apply_metadata_commands([{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}])


@pytest.mark.parametrize("flags", [None, "", "3"])
def test_missing_or_invalid_flags_is_rejected(tiny_workspace, flags):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    node = _sheet_property(document, sheet_id)
    flag_node = _props(node, "Flags")[0]
    if flags is None:
        node.remove(flag_node)
        expected = "CUSTOM_PROPERTY_FLAGS_MISSING"
    else:
        flag_node.text = flags
        expected = "CUSTOM_PROPERTY_FLAGS_INVALID"

    with pytest.raises(AcsmValidationError, match=expected):
        document.apply_metadata_commands([{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}])


def test_duplicate_flags_and_values_are_rejected(tiny_workspace):
    dst, sheet_id = tiny_workspace
    for duplicated_name, expected in (("Flags", "CUSTOM_PROPERTY_FLAGS_INVALID"), ("Value", "CUSTOM_PROPERTY_VALUE_DUPLICATED")):
        document = AcsmDocument(DstCodec().decode_file(dst))
        node = _sheet_property(document, sheet_id)
        node.append(etree.fromstring(etree.tostring(_props(node, duplicated_name)[0])))
        with pytest.raises(AcsmValidationError, match=expected):
            document.apply_metadata_commands([{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}])


def test_duplicate_name_in_same_scope_is_rejected(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    node = _sheet_property(document, sheet_id)
    duplicate = etree.fromstring(etree.tostring(node))
    duplicate.set("ID", "g33333333-3333-3333-3333-333333333333")
    node.addnext(duplicate)

    with pytest.raises(AcsmValidationError, match="CUSTOM_PROPERTY_DUPLICATED"):
        document.apply_metadata_commands([{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}])


def test_projection_filters_sheetset_and_sheet_scopes(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    sheet_set = document.root.xpath("//*[local-name()='AcSmSheetSet']")[0]
    bag = sheet_set.xpath("./*[local-name()='AcSmCustomPropertyBag']")[0]
    sheet_definition = etree.fromstring(
        b'<AcSmCustomPropertyValue ID="g11111111-1111-1111-1111-111111111111" propname="SheetOnly">'
        b'<AcSmProp propname="Flags" vt="3">2</AcSmProp><AcSmProp propname="Value" vt="8">x</AcSmProp>'
        b"</AcSmCustomPropertyValue>"
    )
    bag.append(sheet_definition)

    projected = document.project(Path(dst).parent)

    assert projected.custom_properties == {"项目号": "P-000"}
    assert "SheetOnly" not in projected.custom_properties


def test_same_name_different_scopes_do_not_overwrite_each_other(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    sheet_set = document.root.xpath("//*[local-name()='AcSmSheetSet']")[0]
    bag = sheet_set.xpath("./*[local-name()='AcSmCustomPropertyBag']")[0]
    sheet_definition = etree.fromstring(
        b'<AcSmCustomPropertyValue ID="g44444444-4444-4444-4444-444444444444" propname="\xe9\xa1\xb9\xe7\x9b\xae\xe5\x8f\xb7">'
        b'<AcSmProp propname="Flags" vt="3">2</AcSmProp><AcSmProp propname="Value" vt="8">sheet</AcSmProp>'
        b"</AcSmCustomPropertyValue>"
    )
    bag.append(sheet_definition)

    document.apply_metadata_commands([{"type": "update_sheet_set", "custom_properties": {"项目号": "P-002"}}])

    scoped = {}
    for node in bag:
        if node.get("propname") != "项目号":
            continue
        flags = _props(node, "Flags")[0].text
        scoped[flags] = _props(node, "Value")[0].text
    assert scoped == {"1": "P-002", "2": "sheet"}


def test_insert_factory_initializes_sheet_scope_definitions_only(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]
    template = subset.xpath("./*[local-name()='AcSmSheet']")[0]
    bag = template.xpath("./*[local-name()='AcSmCustomPropertyBag']")[0]
    inherited = etree.fromstring(
        b'<AcSmCustomPropertyValue ID="g22222222-2222-2222-2222-222222222222" propname="Inherited">'
        b'<AcSmProp propname="Flags" vt="3">1</AcSmProp><AcSmProp propname="Value" vt="8">keep</AcSmProp>'
        b"</AcSmCustomPropertyValue>"
    )
    bag.append(inherited)

    document.apply_structural_commands(
        [
            {
                "type": "insert_sheet",
                "target_subset_id": subset.get("ID"),
                "position": 1,
                "number": "002",
                "title": "新增",
                "custom_properties": {},
                "source": {"type": "template_layout", "file": r"C:\模板\标准.dwt", "layout": "A3"},
            },
        ],
        "revision",
    )

    inserted = subset.xpath("./*[local-name()='AcSmSheet']")[1]
    properties = {node.get("propname"): node for node in inserted.xpath("./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue']")}
    assert not _props(properties["比例"], "Value")
    assert "Inherited" not in properties


def test_add_sheet_definition_sets_default_on_every_sheet(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    document.apply_property_definition_commands(
        [{"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"}],
    )

    projected = AcsmDocument(document.to_bytes()).project(dst.parent)
    assert [sheet.custom_properties["专业"] for sheet in projected.sheets] == ["燃气"]
    node = _sheet_property(document, projected.sheets[0].acsm_id, "专业")
    assert [(prop.get("propname"), prop.get("vt"), prop.text) for prop in _props(node, "Flags") + _props(node, "Value")] == [
        ("Flags", "3", "2"),
        ("Value", "8", "燃气"),
    ]


def test_empty_sheet_definition_uses_missing_value_semantics(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    document.apply_property_definition_commands(
        [{"type": "add_custom_property", "property_type": "sheet", "name": "用途", "default_value": ""}],
    )

    projected = AcsmDocument(document.to_bytes()).project(dst.parent)
    assert projected.sheets[0].custom_properties["用途"] == ""
    node = _sheet_property(document, projected.sheets[0].acsm_id, "用途")
    assert [(prop.get("propname"), prop.get("vt"), prop.text) for prop in _props(node, "Flags")] == [("Flags", "3", "2")]
    assert not _props(node, "Value")


def test_delete_sheet_definition_removes_values_from_all_sheets(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    document.apply_property_definition_commands(
        [{"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"}],
    )

    document.apply_property_definition_commands(
        [{"type": "delete_custom_property", "property_type": "sheet", "name": "专业"}],
    )

    projected = AcsmDocument(document.to_bytes()).project(dst.parent)
    assert all("专业" not in sheet.custom_properties for sheet in projected.sheets)
    assert not document.root.xpath(
        "//*[local-name()='AcSmSheet']"
        "/*[local-name()='AcSmCustomPropertyBag']"
        "/*[local-name()='AcSmCustomPropertyValue' and @propname='专业']",
    )


def test_delete_sheetset_definition_only_affects_sheetset_scope(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    document.apply_property_definition_commands(
        [{"type": "delete_custom_property", "property_type": "sheetset", "name": "项目号"}],
    )

    projected = AcsmDocument(document.to_bytes()).project(dst.parent)
    assert "项目号" not in projected.custom_properties
    assert projected.sheets[0].custom_properties == {"比例": "1:100"}


def test_add_definition_rejects_casefold_duplicate(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_property_definition_commands(
            [{"type": "add_custom_property", "property_type": "sheet", "name": " 比例 ", "default_value": ""}],
        )

    assert exc_info.value.code == "CUSTOM_PROPERTY_NAME_DUPLICATE"


def test_property_definition_preserves_unknown_bag_children_and_roundtrips(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    sheet = document.root.xpath("//*[local-name()='AcSmSheet']")[0]
    bag = sheet.xpath("./*[local-name()='AcSmCustomPropertyBag']")[0]
    marker = etree.Element("UnknownPropertyPayload", {"keep": "yes"})
    marker.text = "原始文本"
    bag.insert(0, marker)

    document.apply_property_definition_commands(
        [{"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"}],
    )

    roundtrip = AcsmDocument(document.to_bytes())
    roundtrip_bag = roundtrip.root.xpath(
        "//*[local-name()='AcSmSheet']/*[local-name()='AcSmCustomPropertyBag']",
    )[0]
    assert [(etree.QName(child).localname, child.get("keep"), child.text) for child in roundtrip_bag[:2]] == [
        ("UnknownPropertyPayload", "yes", "原始文本"),
        ("AcSmCustomPropertyValue", None, None),
    ]
