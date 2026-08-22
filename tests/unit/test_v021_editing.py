from pathlib import Path

import pytest

from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.domain.editing import (
    EditingError,
    SuffixOptions,
    derive_document_structure,
    derive_group_titles,
    format_sheet_title,
    normalize_property_name,
    parse_property_csv,
    parse_property_csv_result,
    validate_property_definitions,
)
from dst_manager.domain.models import (
    CustomPropertyDefinition,
    LayoutReference,
    Sheet,
    SheetSetDocument,
    Subset,
    Workspace,
)
from dst_manager.domain.planning import build_structural_plan


def _sheet(acsm_id: str, number: str, title: str, file_name: str = "C:/工程/GP-0004-0005 燃气管道平面图.dwg") -> Sheet:
    return Sheet(
        acsm_id,
        number,
        title,
        LayoutReference(file_name, f".\\{Path(file_name).name}", f"{number} {title}", "AB", Path(file_name)),
        {"比例": "1:100"},
    )


def _workspace(document: SheetSetDocument) -> Workspace:
    return Workspace("workspace", Path("C:/工程"), Path("C:/工程/图纸集.dst"), "revision", document)


def test_same_title_subsets_receive_continuous_chinese_suffixes():
    titles = derive_group_titles(
        [("4-10", "燃气管道平面图", 7), ("11-20", "燃气管道平面图", 10)],
        enabled=True,
        suffix_type=1,
    )
    assert titles[0][0] == "燃气管道平面图 (一)"
    assert titles[1][0] == "燃气管道平面图 (八)"


def test_group_title_suffix_modes_and_numeric_range_sorting():
    groups = [("11-12", "燃气管道平面图", 2), ("4-5", "燃气管道平面图", 2)]

    assert derive_group_titles(groups, enabled=True, suffix_type=2) == [
        ["燃气管道平面图 (3)", "燃气管道平面图 (4)"],
        ["燃气管道平面图 (1)", "燃气管道平面图 (2)"],
    ]
    assert derive_group_titles(groups, enabled=False, suffix_type=1) == [
        ["燃气管道平面图", "燃气管道平面图"],
        ["燃气管道平面图", "燃气管道平面图"],
    ]
    assert derive_group_titles([("7", "节点详图", 1)], enabled=True, suffix_type=1) == [["节点详图"]]


def test_same_title_group_uses_first_trimmed_spelling_for_all_members():
    titles = derive_group_titles(
        [("10", " plan ", 1), ("2", "Plan", 1)],
        enabled=True,
        suffix_type=2,
    )

    assert titles == [["Plan (2)"], ["Plan (1)"]]


@pytest.mark.parametrize(
    ("base_title", "ordinal", "enabled", "suffix_type", "expected"),
    [
        ("燃气管道平面图", 12, True, 1, "燃气管道平面图 (十二)"),
        ("燃气管道平面图", 12, True, 2, "燃气管道平面图 (12)"),
        ("燃气管道平面图", None, True, 1, "燃气管道平面图"),
        ("燃气管道平面图", 12, False, 1, "燃气管道平面图"),
    ],
)
def test_format_sheet_title_uses_configured_suffix(base_title, ordinal, enabled, suffix_type, expected):
    assert format_sheet_title(base_title, ordinal, enabled, suffix_type) == expected


@pytest.mark.parametrize(
    ("base_title", "ordinal", "enabled", "suffix_type", "code"),
    [
        (" ", 1, True, 1, "SHEET_TITLE_EMPTY"),
        ("标题", 1, True, 3, "NUMBER_SUFFIX_TYPE_INVALID"),
        ("标题", 0, True, 1, "SHEET_TITLE_ORDINAL_INVALID"),
    ],
)
def test_format_sheet_title_rejects_invalid_arguments(base_title, ordinal, enabled, suffix_type, code):
    with pytest.raises(EditingError) as exc_info:
        format_sheet_title(base_title, ordinal, enabled, suffix_type)
    assert exc_info.value.code == code


def test_normalize_property_name_rejects_autocad_case_collision():
    assert normalize_property_name(" Go ") == "Go"
    with pytest.raises(EditingError, match="CUSTOM_PROPERTY_NAME_DUPLICATE"):
        validate_property_definitions([("sheet", "go", ""), ("sheet", "Go", "")])


def test_property_csv_accepts_utf8_bom_and_exact_three_columns():
    definitions = parse_property_csv("\ufefftype,name,default_value\nsheetset, 项目号 ,P-001\nsheet,比例,\n".encode("utf-8"))

    assert definitions == [
        CustomPropertyDefinition("sheetset", "项目号", "P-001"),
        CustomPropertyDefinition("sheet", "比例", ""),
    ]


def test_property_csv_result_preserves_logical_record_start_lines_across_blank_rows():
    result = parse_property_csv_result(
        "type,name,default_value\r\n\r\nsheet,专业,燃气\r\nsheetset,阶段,施工图\r\n".encode(),
    )

    assert result.diagnostics == []
    assert [(record.line, record.definition.name) for record in result.records] == [
        (3, "专业"),
        (4, "阶段"),
    ]


@pytest.mark.parametrize(
    ("data", "code", "line"),
    [
        (
            b'type,name,default_value\r\nsheet,"line\r\nbreak",x\r\n',
            "CUSTOM_PROPERTY_NAME_INVALID",
            2,
        ),
        (
            "type,name,default_value\n\nsheet,比例\n".encode(),
            "CUSTOM_PROPERTY_CSV_COLUMNS_INVALID",
            3,
        ),
        (
            "type,name,default_value\nsheet,专业,燃气\n\nsheet,专业,给排水\n".encode(),
            "CUSTOM_PROPERTY_NAME_DUPLICATE",
            4,
        ),
    ],
)
def test_property_csv_result_diagnostics_use_record_start_line(data, code, line):
    result = parse_property_csv_result(data)

    assert [(diagnostic.code, diagnostic.line) for diagnostic in result.diagnostics] == [(code, line)]


@pytest.mark.parametrize("value", ["制表符\t换行\n回车\r", "补充字符😀"])
def test_property_definition_allows_xml_10_text_characters(value):
    assert validate_property_definitions([("sheet", "说明", value)]) == [
        CustomPropertyDefinition("sheet", "说明", value),
    ]


@pytest.mark.parametrize("value", ["燃\x00气", "\x08", "\x0b", "\x1f", "\ud800", "\ufffe", "\uffff"])
def test_property_definition_rejects_xml_10_forbidden_characters(value):
    with pytest.raises(EditingError) as exc_info:
        validate_property_definitions([("sheet", "专业", value)])

    assert exc_info.value.code == "CUSTOM_PROPERTY_VALUE_INVALID"


@pytest.mark.parametrize(
    ("data", "code"),
    [
        ("type,name,default_value,extra\nsheet,比例,1:100,x\n".encode(), "CUSTOM_PROPERTY_CSV_COLUMNS_INVALID"),
        ("type;name;default_value\nsheet;比例;1:100\n".encode(), "CUSTOM_PROPERTY_CSV_HEADER_INVALID"),
        (b"type,name,default_value\nsheet,,1:100\n", "CUSTOM_PROPERTY_NAME_EMPTY"),
        ("type,name,default_value\nsubset,编号,1\n".encode(), "CUSTOM_PROPERTY_TYPE_INVALID"),
        (b"type,name,default_value\nsheet,\xb1\xe0\xba\xc5,1\n", "CUSTOM_PROPERTY_CSV_ENCODING_INVALID"),
        (b'type,name,default_value\nsheet,"line\nbreak",x\n', "CUSTOM_PROPERTY_NAME_INVALID"),
        (b"type,name,default_value\nsheet,bad\x00name,x\n", "CUSTOM_PROPERTY_NAME_INVALID"),
    ],
)
def test_property_csv_rejects_invalid_encoding_shape_and_required_values(data, code):
    with pytest.raises(EditingError) as exc_info:
        parse_property_csv(data)
    assert exc_info.value.code == code


def test_service_property_csv_preview_reports_invalid_utf8_without_writing(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    before = (dst.stat().st_mtime_ns, dst.read_bytes())

    preview = service.preview_custom_property_import(
        workspace.id,
        workspace.revision_id,
        b"type,name,default_value\nsheet,\xb1\xe0\xba\xc5,1\n",
    )

    assert preview["executable"] is False
    assert preview["diagnostics"] == [
        {
            "code": "CUSTOM_PROPERTY_CSV_ENCODING_INVALID",
            "severity": "error",
            "message": "CSV 必须使用 UTF-8 编码",
            "line": None,
        }
    ]
    assert (dst.stat().st_mtime_ns, dst.read_bytes()) == before


def test_normalize_property_name_rejects_control_characters():
    with pytest.raises(EditingError) as exc_info:
        normalize_property_name("编号\r")
    assert exc_info.value.code == "CUSTOM_PROPERTY_NAME_INVALID"


def test_property_definition_diff_skips_same_type_and_blocks_different_type():
    document = SheetSetDocument(
        "db",
        "图纸集",
        [Subset("subset-1", "4-5 燃气管道平面图", 1, [_sheet("sheet-1", "0004", "燃气管道平面图")])],
        {"项目号": "P-000"},
    )

    derived = derive_document_structure(
        document,
        [{"type": "import_custom_properties", "definitions": [("sheet", "比例", ""), ("sheet", "用途", "燃气")]}],
        SuffixOptions(True, 1),
    )

    assert derived.property_diff.skipped == [CustomPropertyDefinition("sheet", "比例", "")]
    assert derived.property_diff.added == [CustomPropertyDefinition("sheet", "用途", "燃气")]
    assert derived.subsets[0].sheets[0].custom_properties["用途"] == "燃气"

    with pytest.raises(EditingError) as exc_info:
        derive_document_structure(
            document,
            [{"type": "import_custom_properties", "definitions": [("sheetset", "比例", "")]}],
            SuffixOptions(True, 1),
        )
    assert exc_info.value.code == "CUSTOM_PROPERTY_TYPE_CONFLICT"


def test_imported_sheet_property_default_applies_to_inserted_sheets_in_same_batch():
    document = SheetSetDocument(
        "db",
        "图纸集",
        [Subset("subset-1", "4 燃气管道平面图", 1, [_sheet("sheet-1", "0004", "燃气管道平面图")])],
    )

    derived = derive_document_structure(
        document,
        [
            {"type": "import_custom_properties", "definitions": [("sheet", "用途", "燃气")]},
            {
                "type": "insert_sheet",
                "target_subset_id": "subset-1",
                "ordinal": 1,
                "placement": "after",
                "count": 1,
                "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
            },
        ],
        SuffixOptions(True, 1),
    )

    assert [sheet.custom_properties["用途"] for sheet in derived.subsets[0].sheets] == ["燃气", "燃气"]


def test_imported_sheet_property_default_applies_to_inserted_subset_sheets_in_same_batch():
    document = SheetSetDocument("db", "图纸集", [])

    derived = derive_document_structure(
        document,
        [
            {"type": "import_custom_properties", "definitions": [("sheet", "用途", "燃气")]},
            {
                "type": "insert_subset",
                "ordinal": 1,
                "title": "燃气管道平面图",
                "initial_sheet_count": 2,
                "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
            },
        ],
        SuffixOptions(True, 1),
    )

    assert [sheet.custom_properties["用途"] for sheet in derived.subsets[0].sheets] == ["燃气", "燃气"]


def test_first_subset_ordinal_one_creates_numbered_initial_sheets():
    document = SheetSetDocument("db", "图纸集", [])

    derived = derive_document_structure(
        document,
        [
            {
                "type": "insert_subset",
                "ordinal": 1,
                "title": "燃气管道平面图",
                "initial_sheet_count": 2,
                "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
            }
        ],
        SuffixOptions(True, 1),
    )

    assert [subset.number_range for subset in derived.subsets] == ["1-2"]
    assert [sheet.number for sheet in derived.subsets[0].sheets] == ["1", "2"]
    assert [sheet.title for sheet in derived.subsets[0].sheets] == ["燃气管道平面图 (一)", "燃气管道平面图 (二)"]


def test_batch_insert_uses_ordinal_as_position_and_preserves_existing_number_width():
    document = SheetSetDocument(
        "db",
        "图纸集",
        [
            Subset(
                "subset-1",
                "4-5 燃气管道平面图",
                1,
                [_sheet("sheet-1", "0004", "燃气管道平面图"), _sheet("sheet-2", "0005", "燃气管道平面图")],
            )
        ],
    )

    derived = derive_document_structure(
        document,
        [
            {
                "type": "insert_sheet",
                "target_subset_id": "subset-1",
                "ordinal": 1,
                "placement": "after",
                "count": 2,
                "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
            }
        ],
        SuffixOptions(True, 2),
    )

    subset = derived.subsets[0]
    assert subset.number_range == "0004-0007"
    assert [sheet.acsm_id for sheet in subset.sheets[:1] + subset.sheets[-1:]] == ["sheet-1", "sheet-2"]
    assert all(sheet.acsm_id.startswith("g") for sheet in subset.sheets[1:3])
    assert len({sheet.acsm_id for sheet in subset.sheets}) == 4
    assert [sheet.number for sheet in subset.sheets] == ["0004", "0005", "0006", "0007"]
    assert [sheet.title for sheet in subset.sheets] == [
        "燃气管道平面图 (1)",
        "燃气管道平面图 (2)",
        "燃气管道平面图 (3)",
        "燃气管道平面图 (4)",
    ]


def test_empty_subset_is_rejected_before_deriving_titles():
    document = SheetSetDocument("db", "图纸集", [Subset("subset-1", "空子集", 1, [])])

    with pytest.raises(EditingError) as exc_info:
        derive_document_structure(document, [], SuffixOptions(True, 1))
    assert exc_info.value.code == "EMPTY_SUBSET"


def test_delete_sheet_rederives_numbers_and_titles_without_manual_editing():
    document = SheetSetDocument(
        "db",
        "图纸集",
        [
            Subset(
                "subset-1",
                "4-6 燃气管道平面图",
                1,
                [
                    _sheet("sheet-1", "0004", "燃气管道平面图"),
                    _sheet("sheet-2", "0005", "燃气管道平面图"),
                    _sheet("sheet-3", "0006", "燃气管道平面图"),
                ],
            )
        ],
    )

    derived = derive_document_structure(
        document,
        [{"type": "delete_sheet", "sheet_id": "sheet-2"}],
        SuffixOptions(True, 2),
    )

    subset = derived.subsets[0]
    assert derived.affected_subset_ids == ["subset-1"]
    assert [sheet.acsm_id for sheet in subset.sheets] == ["sheet-1", "sheet-3"]
    assert [sheet.number for sheet in subset.sheets] == ["0004", "0005"]
    assert [sheet.title for sheet in subset.sheets] == ["燃气管道平面图 (1)", "燃气管道平面图 (2)"]


def test_delete_sheet_rejects_empty_subset_and_legacy_moves_remain_unsupported():
    document = SheetSetDocument(
        "db",
        "图纸集",
        [Subset("subset-1", "4 燃气管道平面图", 1, [_sheet("sheet-1", "0004", "燃气管道平面图")])],
    )

    with pytest.raises(EditingError) as exc_info:
        derive_document_structure(document, [{"type": "delete_sheet", "sheet_id": "sheet-1"}], SuffixOptions(True, 1))
    assert exc_info.value.code == "EMPTY_SUBSET"

    with pytest.raises(EditingError) as exc_info:
        derive_document_structure(document, [{"type": "move_sheet", "sheet_id": "sheet-1"}], SuffixOptions(True, 1))
    assert exc_info.value.code == "COMMAND_UNSUPPORTED"


def test_build_structural_plan_consumes_derived_document_without_filesystem_source_checks():
    document = SheetSetDocument(
        "db",
        "图纸集",
        [Subset("subset-1", "4-5 燃气管道平面图", 1, [_sheet("sheet-1", "0004", "燃气管道平面图")])],
    )

    plan = build_structural_plan(
        _workspace(document),
        [
            {
                "type": "insert_sheet",
                "target_subset_id": "subset-1",
                "ordinal": 1,
                "placement": "after",
                "count": 1,
                "source": {"type": "template_layout", "file": "C:/尚未创建/模板.dwt", "layout": "A3"},
            }
        ],
        SuffixOptions(True, 2),
    )

    assert plan["affected_subset_ids"] == ["subset-1"]
    assert plan["groups"][0]["subset_name"] == "0004-0005 燃气管道平面图"
    assert [layout["number"] for layout in plan["groups"][0]["layouts"]] == ["0004", "0005"]
    assert [layout["title"] for layout in plan["groups"][0]["layouts"]] == ["燃气管道平面图 (1)", "燃气管道平面图 (2)"]
