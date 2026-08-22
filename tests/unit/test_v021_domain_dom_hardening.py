from pathlib import Path

import pytest
from lxml import etree

from dst_manager.domain.editing import (
    EditingError,
    derive_document_structure,
    derive_group_titles,
    format_sheet_title,
    property_definitions_from_document,
)
from dst_manager.domain.models import (
    DerivedDocument,
    DerivedSubset,
    LayoutReference,
    Sheet,
    SheetSetDocument,
    Subset,
    SuffixOptions,
    Workspace,
)
from dst_manager.domain.planning import PlanningError, build_structural_plan
from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.acsm_xml.document import AcsmValidationError
from dst_manager.infrastructure.dst_codec import DstCodec


def _sheet(sheet_id: str, number: str, title: str, drawing: str = "A.dwg") -> Sheet:
    return Sheet(
        sheet_id,
        number,
        title,
        LayoutReference(drawing, f".\\{Path(drawing).name}", f"{number} {title}", "AB"),
    )


def _insert_sheet_command(subset_id: str, count: int = 1) -> dict:
    return {
        "type": "insert_sheet",
        "target_subset_id": subset_id,
        "ordinal": 1,
        "placement": "after",
        "count": count,
        "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
    }


def _insert_subset_command(count: int = 1) -> dict:
    return {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "燃气管道平面图",
        "initial_sheet_count": count,
        "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
    }


def _committed_document(source: SheetSetDocument, derived: DerivedDocument) -> SheetSetDocument:
    subsets = [
        Subset(item.acsm_id, item.display_name, order, list(item.sheets))
        for order, item in enumerate(derived.subsets)
    ]
    return SheetSetDocument(source.database_id, source.name, subsets)


def test_insert_sheet_ids_are_stable_per_document_and_change_after_commit():
    document = SheetSetDocument(
        "g10000000-0000-0000-0000-000000000001",
        "图纸集",
        [Subset("g20000000-0000-0000-0000-000000000001", "1 平面", 0, [_sheet("g30000000-0000-0000-0000-000000000001", "001", "平面")])],
    )
    command = _insert_sheet_command(document.subsets[0].acsm_id, count=2)

    first = derive_document_structure(document, [command], SuffixOptions(True, 2))
    repeated = derive_document_structure(document, [command], SuffixOptions(True, 2))
    first_ids = [sheet.acsm_id for sheet in first.subsets[0].sheets[1:]]
    repeated_ids = [sheet.acsm_id for sheet in repeated.subsets[0].sheets[1:]]

    assert first_ids == repeated_ids
    assert len(first_ids) == len(set(first_ids)) == 2

    committed = _committed_document(document, first)
    after_commit = derive_document_structure(
        committed,
        [_insert_sheet_command(committed.subsets[0].acsm_id, count=2)],
        SuffixOptions(True, 2),
    )
    after_commit_ids = [sheet.acsm_id for sheet in after_commit.subsets[0].sheets[1:3]]
    assert set(after_commit_ids).isdisjoint(first_ids)


def test_insert_subset_ids_are_stable_per_document_and_change_after_commit():
    document = SheetSetDocument("g10000000-0000-0000-0000-000000000002", "图纸集", [])
    command = _insert_subset_command(count=2)

    first = derive_document_structure(document, [command], SuffixOptions(True, 2))
    repeated = derive_document_structure(document, [command], SuffixOptions(True, 2))
    first_ids = [first.subsets[0].acsm_id, *(sheet.acsm_id for sheet in first.subsets[0].sheets)]
    repeated_ids = [repeated.subsets[0].acsm_id, *(sheet.acsm_id for sheet in repeated.subsets[0].sheets)]

    assert first_ids == repeated_ids
    assert len(first_ids) == len(set(first_ids)) == 3

    committed = _committed_document(document, first)
    after_commit = derive_document_structure(committed, [command], SuffixOptions(True, 2))
    new_subset = after_commit.subsets[1]
    after_commit_ids = [new_subset.acsm_id, *(sheet.acsm_id for sheet in new_subset.sheets)]
    assert set(after_commit_ids).isdisjoint(first_ids)


def test_plan_rejects_duplicate_subset_and_sheet_ids_before_filesystem_planning(tmp_path):
    drawing = tmp_path / "A.dwg"
    drawing.write_bytes(b"dwg")
    duplicated_id = "g40000000-0000-0000-0000-000000000001"
    sheet = _sheet(duplicated_id, "001", "平面", str(drawing))
    sheet.layout.resolved_path = drawing.resolve()
    workspace = Workspace(
        "workspace",
        tmp_path,
        tmp_path / "test.dst",
        "revision",
        SheetSetDocument("database", "图纸集", [Subset(duplicated_id, "1 平面", 0, [sheet])]),
    )

    with pytest.raises(PlanningError) as exc_info:
        build_structural_plan(workspace, [], SuffixOptions(True, 2))

    assert exc_info.value.code == "DUPLICATE_ACSM_ID"


def test_plan_treats_acsm_guid_case_variants_as_the_same_id(tmp_path):
    drawing = tmp_path / "A.dwg"
    drawing.write_bytes(b"dwg")
    subset_id = "gABCDEF00-0000-0000-0000-000000000001"
    sheet = _sheet(subset_id.lower(), "001", "平面", str(drawing))
    sheet.layout.resolved_path = drawing.resolve()
    workspace = Workspace(
        "workspace",
        tmp_path,
        tmp_path / "test.dst",
        "revision",
        SheetSetDocument("database", "图纸集", [Subset(subset_id, "1 平面", 0, [sheet])]),
    )

    with pytest.raises(PlanningError) as exc_info:
        build_structural_plan(workspace, [], SuffixOptions(True, 2))

    assert exc_info.value.code == "DUPLICATE_ACSM_ID"


def test_preferred_acsm_id_collision_is_stable_and_transactional(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    before = document.semantic_bytes()
    derived = DerivedDocument(
        [
            DerivedSubset(
                sheet_id,
                "新子集",
                "002",
                "002 新子集",
                [
                    _sheet(
                        "g40000000-0000-0000-0000-000000000002",
                        "002",
                        "新子集",
                        str(dst.parent / "A.dwg"),
                    ),
                ],
            ),
        ],
        [sheet_id],
    )

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_derived_document(derived)

    assert exc_info.value.code == "DUPLICATE_ACSM_ID"
    assert document.semantic_bytes() == before


def test_structural_command_batch_rolls_back_slot_changes_when_later_command_fails(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset_id = document.root.xpath("//*[local-name()='AcSmSubset']")[0].get("ID")
    before = document.semantic_bytes()

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_structural_commands(
            [
                _insert_sheet_command(subset_id),
                _insert_sheet_command("gFFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF"),
            ],
            "revision",
        )

    assert exc_info.value.code == "ACSMSUBSET_NOT_FOUND"
    assert document.semantic_bytes() == before


def _clone_with_fresh_ids(node: etree._Element, start: int) -> etree._Element:
    clone = etree.fromstring(etree.tostring(node))
    identified = [clone, *clone.xpath(".//*[@ID]")]
    for offset, item in enumerate((item for item in identified if item.get("ID")), start=start):
        item.set("ID", f"gA0000000-0000-0000-0000-{offset:012X}")
    return clone


def _marker(name: str) -> etree._Element:
    node = etree.Element("UnknownSlot", {"marker": name, "keep": "yes"})
    node.text = f"text-{name}"
    node.tail = f"tail-{name}"
    return node


def _marker_payloads(parent: etree._Element) -> dict[str, tuple[dict[str, str], str | None, str | None]]:
    return {
        node.get("marker", ""): (dict(node.attrib), node.text, node.tail)
        for node in parent.xpath("./*[local-name()='UnknownSlot']")
    }


def _controlled_sequence(parent: etree._Element, local_name: str) -> list[str]:
    return [
        child.get("marker") if etree.QName(child).localname == "UnknownSlot" else child.get("ID")
        for child in parent
        if etree.QName(child).localname in {"UnknownSlot", local_name}
    ]


def test_sheet_reconciliation_preserves_unknown_slots_for_reorder_insert_and_delete(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]
    first_node = subset.xpath("./*[local-name()='AcSmSheet']")[0]
    second_node = _clone_with_fresh_ids(first_node, 100)
    first_node.addprevious(_marker("head"))
    first_node.addnext(_marker("middle"))
    first_node.getnext().addnext(second_node)
    second_node.addnext(_marker("tail"))
    original_payloads = _marker_payloads(subset)
    projected = document.project(dst.parent)
    first_sheet, second_sheet = projected.subsets[0].sheets
    unchanged = DerivedDocument(
        [
            DerivedSubset(
                projected.subsets[0].acsm_id,
                "分组",
                "001-002",
                projected.subsets[0].name,
                [first_sheet, second_sheet],
            ),
        ],
        [],
    )
    before_noop = document.semantic_bytes()

    document.apply_derived_document(unchanged)

    assert document.semantic_bytes() == before_noop
    inserted = _sheet(
        "g50000000-0000-0000-0000-000000000001",
        "003",
        "新增",
        str(dst.parent / "A.dwg"),
    )
    derived = DerivedDocument(
        [
            DerivedSubset(
                projected.subsets[0].acsm_id,
                "分组",
                "002-003",
                "002-003 分组",
                [second_sheet, inserted],
            ),
        ],
        [projected.subsets[0].acsm_id],
    )

    document.apply_derived_document(derived)

    result_subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]
    assert _controlled_sequence(result_subset, "AcSmSheet") == [
        "head",
        second_sheet.acsm_id,
        "middle",
        inserted.acsm_id,
        "tail",
    ]
    assert _marker_payloads(result_subset) == original_payloads
    assert first_sheet.acsm_id not in document.semantic_bytes().decode()


def test_subset_reconciliation_preserves_unknown_slots_for_reorder_insert_and_delete(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    sheet_set = document.root.xpath("//*[local-name()='AcSmSheetSet']")[0]
    first_node = sheet_set.xpath("./*[local-name()='AcSmSubset']")[0]
    second_node = _clone_with_fresh_ids(first_node, 200)
    first_node.addprevious(_marker("head"))
    first_node.addnext(_marker("middle"))
    first_node.getnext().addnext(second_node)
    second_node.addnext(_marker("tail"))
    original_payloads = _marker_payloads(sheet_set)
    projected = document.project(dst.parent)
    first_subset, second_subset = projected.subsets
    inserted_sheet = _sheet(
        "g60000000-0000-0000-0000-000000000001",
        "003",
        "新增子集",
        str(dst.parent / "A.dwg"),
    )
    inserted_subset = DerivedSubset(
        "g60000000-0000-0000-0000-000000000002",
        "新增子集",
        "003",
        "003 新增子集",
        [inserted_sheet],
    )
    derived = DerivedDocument(
        [
            DerivedSubset(
                second_subset.acsm_id,
                "分组",
                "002",
                "002 分组",
                second_subset.sheets,
            ),
            inserted_subset,
        ],
        [second_subset.acsm_id, inserted_subset.acsm_id],
    )

    document.apply_derived_document(derived)

    result_sheet_set = document.root.xpath("//*[local-name()='AcSmSheetSet']")[0]
    assert _controlled_sequence(result_sheet_set, "AcSmSubset") == [
        "head",
        second_subset.acsm_id,
        "middle",
        inserted_subset.acsm_id,
        "tail",
    ]
    assert _marker_payloads(result_sheet_set) == original_payloads
    assert first_subset.acsm_id not in document.semantic_bytes().decode()


@pytest.mark.parametrize(
    ("ordinal", "expected"),
    [
        (1, "一"),
        (10, "十"),
        (11, "十一"),
        (20, "二十"),
        (99, "九十九"),
        (100, "一零零"),
        (101, "一零一"),
        (110, "一一零"),
        (999, "九九九"),
    ],
)
def test_legacy_transdigit_is_exact_through_999(ordinal, expected):
    assert format_sheet_title("标题", ordinal, True, 1) == f"标题 ({expected})"


def test_legacy_transdigit_rejects_1000_in_same_title_group():
    with pytest.raises(EditingError) as exc_info:
        derive_group_titles([("1-1000", "标题", 1000)], True, 1)

    assert exc_info.value.code == "SHEET_TITLE_ORDINAL_OUT_OF_RANGE"


def _sheet_set_property_nodes(document: AcsmDocument, name: str) -> list[etree._Element]:
    return document.root.xpath(
        "//*[local-name()='AcSmSheetSet']"
        "/*[local-name()='AcSmCustomPropertyBag']"
        "/*[local-name()='AcSmCustomPropertyValue' and @propname=$name]",
        name=name,
    )


def _scope(node: etree._Element) -> str:
    return node.xpath("./*[local-name()='AcSmProp' and @propname='Flags']")[0].text


def test_sheet_definition_anchor_survives_empty_set_reopen_and_first_sheet_creation(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    sheet_set = document.root.xpath("//*[local-name()='AcSmSheetSet']")[0]
    for subset in sheet_set.xpath("./*[local-name()='AcSmSubset']"):
        sheet_set.remove(subset)

    document.apply_property_definition_commands(
        [{"type": "add_custom_property", "property_type": "sheet", "name": "用途", "default_value": "燃气"}],
    )

    anchors = [node for node in _sheet_set_property_nodes(document, "用途") if _scope(node) == "2"]
    assert len(anchors) == 1
    assert not anchors[0].xpath("./*[local-name()='AcSmProp' and @propname='Value']")
    reopened = AcsmDocument(document.to_bytes())
    projected_empty = reopened.project(dst.parent)
    assert projected_empty.sheet_property_definitions == ["用途"]
    assert property_definitions_from_document(projected_empty)[-1].default_value == ""

    reopened.apply_structural_commands([_insert_subset_command()], "revision-2")

    projected = AcsmDocument(reopened.to_bytes()).project(dst.parent)
    assert projected.sheet_property_definitions == ["用途"]
    assert projected.sheets[0].custom_properties == {"用途": ""}


def test_sheet_definition_anchor_keeps_empty_default_while_existing_sheets_receive_import_default(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    document.apply_property_definition_commands(
        [{"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"}],
    )

    anchors = [node for node in _sheet_set_property_nodes(document, "专业") if _scope(node) == "2"]
    assert len(anchors) == 1
    assert not anchors[0].xpath("./*[local-name()='AcSmProp' and @propname='Value']")
    projected = AcsmDocument(document.to_bytes()).project(dst.parent)
    assert projected.sheet_property_definitions == ["专业", "比例"]
    assert projected.sheets[0].custom_properties["专业"] == "燃气"
    definitions = property_definitions_from_document(projected)
    assert next(item.default_value for item in definitions if item.name == "专业") == ""


def test_delete_sheet_definition_removes_sheetset_anchor_and_sheet_values(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    document.apply_property_definition_commands(
        [{"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"}],
    )

    document.apply_property_definition_commands(
        [{"type": "delete_custom_property", "property_type": "sheet", "name": "专业"}],
    )

    assert _sheet_set_property_nodes(document, "专业") == []
    assert all("专业" not in sheet.custom_properties for sheet in document.project(dst.parent).sheets)


def test_legacy_sheet_values_without_anchor_remain_discoverable(tiny_workspace):
    dst, _ = tiny_workspace
    projected = AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)

    assert projected.sheet_property_definitions == ["比例"]
    assert property_definitions_from_document(projected)[-1].name == "比例"
    assert property_definitions_from_document(projected)[-1].default_value == ""


@pytest.mark.parametrize("value", ["制表\t换行\n回车\r", "补充字符😀"])
def test_dom_accepts_xml_10_text(value, tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    document.apply_metadata_commands([{"type": "update_sheet_set", "name": value}])

    document.to_bytes()


@pytest.mark.parametrize("value", ["\x00", "\x08", "\x0b", "\ud800", "\ufffe", "\uffff"])
def test_set_prop_rejects_forbidden_xml_text_as_stable_acsm_error(value, tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_metadata_commands([{"type": "update_sheet_set", "name": value}])

    assert exc_info.value.code == "XML_TEXT_INVALID"


def test_custom_property_text_rejects_surrogate_as_stable_acsm_error(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_metadata_commands(
            [{"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "\ud800"}}],
        )

    assert exc_info.value.code == "XML_TEXT_INVALID"


def test_sheetset_property_text_rejects_noncharacter_as_stable_acsm_error(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_metadata_commands(
            [{"type": "update_sheet_set", "custom_properties": {"项目号": "\uffff"}}],
        )

    assert exc_info.value.code == "XML_TEXT_INVALID"


def test_property_name_rejects_noncharacter_as_stable_acsm_error(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_property_definition_commands(
            [{"type": "add_custom_property", "property_type": "sheet", "name": "\ufffe", "default_value": ""}],
        )

    assert exc_info.value.code == "CUSTOM_PROPERTY_NAME_INVALID"


def test_derived_subset_text_fails_transactionally(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    projected = document.project(dst.parent)
    subset = projected.subsets[0]
    before = document.semantic_bytes()
    derived = DerivedDocument(
        [DerivedSubset(subset.acsm_id, "非法\uffff", "001", "001 非法\uffff", subset.sheets)],
        [subset.acsm_id],
    )

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_derived_document(derived)

    assert exc_info.value.code == "XML_TEXT_INVALID"
    assert document.semantic_bytes() == before


def test_derived_existing_property_text_fails_transactionally(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    projected = document.project(dst.parent)
    subset = projected.subsets[0]
    subset.sheets[0].custom_properties["比例"] = "\ud800"
    before = document.semantic_bytes()
    derived = DerivedDocument(
        [DerivedSubset(subset.acsm_id, "分组", "001", subset.name, subset.sheets)],
        [subset.acsm_id],
    )

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_derived_document(derived)

    assert exc_info.value.code == "XML_TEXT_INVALID"
    assert document.semantic_bytes() == before
