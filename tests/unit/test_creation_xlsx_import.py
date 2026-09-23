"""创建 XLSX 导入的整批拒绝测试：包级危险特征、技术元数据与受控规模（PLAN-DM-036 Task 2）。

覆盖 brief Step 4 的拒绝类用例：公式单元格、包内外部链接与宏、不可读载荷、被
篡改的隐藏技术元数据（标准身份与列映射）、未知/重复/缺失表头、计划之外的单元格
与行、可见表集合被改动、行/列数超限，以及危险目标路径（工作簿层与领域函数两层）。
所有用例都要求整批拒绝（``value`` 为 None）并给出稳定的工作表/行/列定位。
"""

from creation_xlsx_fixtures import (
    DEFAULT_SHEETSET_PATH,
    diagnostic,
    fill_template,
    group_row,
    meta_cell,
    meta_label_cell,
    valid_group_workbook,
    with_extra_package_part,
)

from dst_manager.application.creation_import import parse_creation_workbook
from dst_manager.domain.creation import (
    MAX_TARGET_PATH_LENGTH,
    validate_creation_target_path,
)
from dst_manager.infrastructure.creation_xlsx import (
    MAX_SHEET_COLUMNS,
    MAX_SHEET_ROWS,
    META_SHEET,
    SHEET_SHEET,
    SHEETSET_SHEET,
)

# ---- 公式、外部链接与不可读输入 ------------------------------------------


def test_formula_cell_is_rejected_with_cell_location(standard, options) -> None:
    data = fill_template(
        standard,
        options,
        sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
        rows=(group_row(),),
        mutate=lambda workbook: setattr(
            workbook[SHEET_SHEET].cell(row=2, column=2), "value", "=1+1"
        ),
    )
    result = parse_creation_workbook(data, standard, options)
    assert result.value is None
    found = diagnostic(result, "CREATION_XLSX_FORMULA_FORBIDDEN")
    assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 2, "B")


def test_external_link_and_macro_parts_are_rejected(standard, options) -> None:
    valid = valid_group_workbook(path=DEFAULT_SHEETSET_PATH, count=1)
    linked = parse_creation_workbook(
        with_extra_package_part(valid, "xl/externalLinks/externalLink1.xml"), standard, options
    )
    assert linked.value is None
    assert diagnostic(linked, "CREATION_XLSX_EXTERNAL_LINK_FORBIDDEN").code
    macro = parse_creation_workbook(
        with_extra_package_part(valid, "xl/vbaProject.bin"), standard, options
    )
    assert macro.value is None
    assert diagnostic(macro, "CREATION_XLSX_MACRO_FORBIDDEN").code


def test_unreadable_payload_is_rejected(standard, options) -> None:
    result = parse_creation_workbook("不是工作簿".encode(), standard, options)
    assert result.value is None
    assert diagnostic(result, "CREATION_XLSX_UNREADABLE").code


# ---- 隐藏元数据篡改与标准身份 --------------------------------------------


def test_tampered_standard_identity_in_metadata_is_rejected(standard, options) -> None:
    data = fill_template(
        standard,
        options,
        sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
        rows=(group_row(),),
        mutate=lambda workbook: setattr(
            meta_cell(workbook, "standard", "standard_version"), "value", "9.9.9"
        ),
    )
    result = parse_creation_workbook(data, standard, options)
    assert result.value is None
    assert diagnostic(result, "CREATION_XLSX_STANDARD_MISMATCH").sheet == META_SHEET


def test_tampered_property_column_mapping_is_rejected(standard, options) -> None:
    def tamper(property_id: str):
        return lambda workbook: setattr(
            meta_label_cell(workbook, "property_column", "分部"), "value", property_id
        )

    for property_id in ("prop-label", "prop-unknown"):
        data = fill_template(
            standard,
            options,
            sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
            rows=(group_row(),),
            mutate=tamper(property_id),
        )
        result = parse_creation_workbook(data, standard, options)
        assert result.value is None
        found = diagnostic(result, "CREATION_XLSX_METADATA_INVALID")
        assert found.sheet == META_SHEET


# ---- 表头与受控规模 ------------------------------------------------------


def test_header_duplicate_missing_and_unknown_are_rejected(standard, options) -> None:
    def data_with(mutate) -> bytes:
        return fill_template(
            standard,
            options,
            sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
            rows=(group_row(),),
            mutate=mutate,
        )

    duplicated = parse_creation_workbook(
        data_with(
            lambda workbook: setattr(workbook[SHEET_SHEET].cell(row=1, column=2), "value", "图名")
        ),
        standard,
        options,
    )
    assert duplicated.value is None
    assert (diagnostic(duplicated, "CREATION_XLSX_HEADER_DUPLICATE").column) == "B"

    missing = parse_creation_workbook(
        data_with(
            lambda workbook: setattr(workbook[SHEET_SHEET].cell(row=1, column=2), "value", None)
        ),
        standard,
        options,
    )
    assert missing.value is None
    found = diagnostic(missing, "CREATION_XLSX_HEADER_MISSING")
    assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 1, "B")

    unknown = parse_creation_workbook(
        data_with(
            lambda workbook: setattr(workbook[SHEET_SHEET].cell(row=1, column=8), "value", "多余列")
        ),
        standard,
        options,
    )
    assert unknown.value is None
    found = diagnostic(unknown, "CREATION_XLSX_HEADER_UNKNOWN")
    assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 1, "H")


def test_unexpected_content_outside_plan_is_rejected(standard, options) -> None:
    sheet_extra = parse_creation_workbook(
        fill_template(
            standard,
            options,
            sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
            rows=(group_row(),),
            mutate=lambda workbook: setattr(
                workbook[SHEET_SHEET].cell(row=2, column=8), "value", "越界内容"
            ),
        ),
        standard,
        options,
    )
    assert sheet_extra.value is None
    found = diagnostic(sheet_extra, "CREATION_XLSX_CELL_UNEXPECTED")
    assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 2, "H")

    sheetset_extra = parse_creation_workbook(
        fill_template(
            standard,
            options,
            sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
            rows=(group_row(),),
            mutate=lambda workbook: setattr(
                workbook[SHEETSET_SHEET].cell(row=7, column=1), "value", "多余行"
            ),
        ),
        standard,
        options,
    )
    assert sheetset_extra.value is None
    found = diagnostic(sheetset_extra, "CREATION_XLSX_CELL_UNEXPECTED")
    assert (found.sheet, found.row, found.column) == (SHEETSET_SHEET, 7, "A")


def test_visible_sheet_set_is_enforced_on_import(standard, options) -> None:
    def data_with(mutate) -> bytes:
        return fill_template(
            standard,
            options,
            sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
            rows=(group_row(),),
            mutate=mutate,
        )

    extra = parse_creation_workbook(
        data_with(lambda workbook: workbook.create_sheet("Sheet3")), standard, options
    )
    assert extra.value is None
    assert diagnostic(extra, "CREATION_XLSX_SHEET_INVALID").sheet == "Sheet3"

    removed = parse_creation_workbook(
        data_with(lambda workbook: workbook.remove(workbook[SHEET_SHEET])), standard, options
    )
    assert removed.value is None
    assert diagnostic(removed, "CREATION_XLSX_SHEET_INVALID").sheet == SHEET_SHEET

    metadata_visible = parse_creation_workbook(
        data_with(lambda workbook: setattr(workbook[META_SHEET], "sheet_state", "visible")),
        standard,
        options,
    )
    assert metadata_visible.value is None
    assert diagnostic(metadata_visible, "CREATION_XLSX_METADATA_INVALID").sheet == META_SHEET


def test_oversized_workbook_is_rejected(standard, options) -> None:
    rows = parse_creation_workbook(
        fill_template(
            standard,
            options,
            sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
            rows=(group_row(),),
            mutate=lambda workbook: setattr(
                workbook[SHEET_SHEET].cell(row=MAX_SHEET_ROWS + 1, column=1), "value", "超限"
            ),
        ),
        standard,
        options,
    )
    assert rows.value is None
    found = diagnostic(rows, "CREATION_XLSX_SCALE_EXCEEDED")
    assert (found.sheet, found.row) == (SHEET_SHEET, MAX_SHEET_ROWS + 1)

    columns = parse_creation_workbook(
        fill_template(
            standard,
            options,
            sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
            rows=(group_row(),),
            mutate=lambda workbook: setattr(
                workbook[SHEET_SHEET].cell(row=1, column=MAX_SHEET_COLUMNS + 1), "value", "越界"
            ),
        ),
        standard,
        options,
    )
    assert columns.value is None
    found = diagnostic(columns, "CREATION_XLSX_SCALE_EXCEEDED")
    assert found.sheet == SHEET_SHEET
    assert found.column is not None


# ---- 目标路径安全（工作簿层与领域函数） ----------------------------------


def test_unsafe_target_path_is_rejected(standard, options) -> None:
    cases = {
        r"Projects\道路工程": "CREATION_TARGET_PATH_NOT_ABSOLUTE",
        r"C:道路工程": "CREATION_TARGET_PATH_DRIVE_INVALID",
        r"C:\Projects\道路<工程": "CREATION_TARGET_PATH_CHARACTER_INVALID",
        r"C:\Projects\con": "CREATION_TARGET_PATH_RESERVED_DEVICE",
        r"C:\Projects\道路工程.": "CREATION_TARGET_PATH_TRAILING_CHARACTER",
        r"C:\Projects\..\其他": "CREATION_TARGET_PATH_SEGMENT_INVALID",
        "C:\\Projects\\道路工程\\": "CREATION_TARGET_PATH_SEGMENT_INVALID",
        "": "CREATION_TARGET_PATH_EMPTY",
    }
    for path, code in cases.items():
        data = fill_template(
            standard,
            options,
            sheetset={"项目保存路径": path},
            rows=(group_row(),),
        )
        result = parse_creation_workbook(data, standard, options)
        assert result.value is None, path
        found = diagnostic(result, code)
        assert (found.sheet, found.row, found.column) == (SHEETSET_SHEET, 2, "B")


def test_validate_creation_target_path_accepts_absolute_windows_paths() -> None:
    assert validate_creation_target_path(r"C:\Projects\道路工程") == ()
    assert validate_creation_target_path("D:/Projects/项目") == ()
    assert validate_creation_target_path(r"C:\Projects\新建项目 2") == ()


def test_validate_creation_target_path_rejects_unsafe_values() -> None:
    cases = {
        "": "CREATION_TARGET_PATH_EMPTY",
        "   ": "CREATION_TARGET_PATH_EMPTY",
        r"Projects\道路工程": "CREATION_TARGET_PATH_NOT_ABSOLUTE",
        r"\\server\share\项目": "CREATION_TARGET_PATH_NOT_ABSOLUTE",
        r"C:道路工程": "CREATION_TARGET_PATH_DRIVE_INVALID",
        r"C:\Projects\道路|工程": "CREATION_TARGET_PATH_CHARACTER_INVALID",
        r"C:\Projects\道路工程 ": "CREATION_TARGET_PATH_TRAILING_CHARACTER",
        r"C:\Projects\nul": "CREATION_TARGET_PATH_RESERVED_DEVICE",
        r"C:\Projects\.": "CREATION_TARGET_PATH_SEGMENT_INVALID",
        "C:\\Projects\\道路工程\\": "CREATION_TARGET_PATH_SEGMENT_INVALID",
        r"C:\\Projects": "CREATION_TARGET_PATH_SEGMENT_INVALID",
    }
    for path, code in cases.items():
        codes = [item.code for item in validate_creation_target_path(path)]
        assert code in codes, (path, codes)
        assert all(item.sheet == "" and item.row is None for item in validate_creation_target_path(path))

    too_long = "C:\\Projects\\" + "道" * MAX_TARGET_PATH_LENGTH
    assert "CREATION_TARGET_PATH_TOO_LONG" in [
        item.code for item in validate_creation_target_path(too_long)
    ]
