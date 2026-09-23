"""创建 XLSX 组行解析测试：合法往返与行级校验（PLAN-DM-036 Task 2）。

覆盖 brief Step 1 的路径/张数往返用例与 Step 4 的行级用例：合法工作簿按行序
往返成图纸组（一行一组，张数不展开为逐张输入）、与界面输入同形、粘贴绕过的非法
枚举值整批拒绝，以及失效资产、图幅与布局模板不匹配、重复图名、非法张数的定位诊断。
"""

from creation_xlsx_fixtures import (
    DEFAULT_SHEETSET_PATH,
    diagnostic,
    fill_template,
    group_row,
    valid_group_workbook,
    workbook_with_invalid_enum,
)

from dst_manager.application.creation_import import parse_creation_workbook
from dst_manager.infrastructure.creation_xlsx import SHEET_SHEET

# ---- 粘贴绕过与合法往返 --------------------------------------------------


def test_pasted_invalid_enum_rejects_entire_workbook(standard, options) -> None:
    result = parse_creation_workbook(workbook_with_invalid_enum(), standard, options)
    assert result.value is None
    assert (result.diagnostics[0].sheet, result.diagnostics[0].row) == ("Sheet", 2)


def test_xlsx_final_path_and_group_count_round_trip(standard, options) -> None:
    result = parse_creation_workbook(valid_group_workbook(path=r"C:\Projects\道路工程", count=3), standard, options)
    assert result.value.target_path == r"C:\Projects\道路工程"
    assert len(result.value.groups) == 1
    assert result.value.groups[0].count == 3


def test_valid_workbook_round_trips_groups_in_row_order(standard, options) -> None:
    data = fill_template(
        standard,
        options,
        sheetset={"项目保存路径": r"C:\Projects\道路工程"},
        rows=(
            group_row(图名="平面图", 张数=3),
            {},
            group_row(图名="剖面图", 设计阶段=""),
        ),
    )
    result = parse_creation_workbook(data, standard, options)
    assert result.diagnostics == ()
    value = result.value
    assert value.target_path == r"C:\Projects\道路工程"
    assert value.sheetset_values == {"prop-name": "默认工程", "prop-major": "燃气"}
    assert [group.title for group in value.groups] == ["平面图", "剖面图"]
    assert [group.count for group in value.groups] == [3, 1]
    assert [group.created_order for group in value.groups] == [1, 2]
    assert len({group.group_id for group in value.groups}) == 2
    # 一行一组：张数不展开为逐张输入，普通 sheet 属性每个键都存在。
    assert value.groups[0].sheet_values == {"prop-stage": "施工图", "prop-part": "A 段"}
    assert value.groups[1].sheet_values == {"prop-stage": "", "prop-part": "A 段"}


def test_imported_value_matches_ui_input_shape(standard, options) -> None:
    result = parse_creation_workbook(
        valid_group_workbook(path=r"C:\Projects\道路工程", count=3), standard, options
    )
    value = result.value
    group = value.groups[0]
    assert value.target_path == r"C:\Projects\道路工程"
    assert value.sheetset_values == {"prop-name": "默认工程", "prop-major": "燃气"}
    assert (group.title, group.count) == ("平面图", 3)
    assert (group.base_asset_id, group.layout_asset_id, group.paper_layout) == (
        "base-a1",
        "layout-a1",
        "A1",
    )
    assert group.sheet_values == {"prop-stage": "施工图", "prop-part": "A 段"}


# ---- 资产、图幅与行输入校验 ----------------------------------------------


def test_stale_asset_option_is_rejected(standard, options) -> None:
    data = valid_group_workbook(path=DEFAULT_SHEETSET_PATH, count=1)
    result = parse_creation_workbook(data, standard, options[1:])
    assert result.value is None
    found = diagnostic(result, "CREATION_XLSX_ASSET_INVALID")
    assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 2, "C")


def test_layout_template_and_paper_layout_mismatch_is_rejected(standard, options) -> None:
    wrong_layout = fill_template(
        standard,
        options,
        sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
        rows=(group_row(图幅="A0"),),
    )
    result = parse_creation_workbook(wrong_layout, standard, options)
    assert result.value is None
    found = diagnostic(result, "CREATION_XLSX_PAPER_LAYOUT_INVALID")
    assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 2, "E")

    swapped = fill_template(
        standard,
        options,
        sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
        rows=(group_row(基础模板="a1-layout.dwt"),),
    )
    result = parse_creation_workbook(swapped, standard, options)
    assert result.value is None
    found = diagnostic(result, "CREATION_XLSX_ASSET_INVALID")
    assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 2, "C")


def test_duplicate_group_title_is_rejected(standard, options) -> None:
    data = fill_template(
        standard,
        options,
        sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
        rows=(group_row(图名="平面图"), group_row(图名=" 平面图 ")),
    )
    result = parse_creation_workbook(data, standard, options)
    assert result.value is None
    found = diagnostic(result, "CREATION_XLSX_TITLE_DUPLICATE")
    assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 3, "A")


def test_invalid_group_count_is_rejected(standard, options) -> None:
    for count in ("0", "-1", "3.5", "三", ""):
        data = fill_template(
            standard,
            options,
            sheetset={"项目保存路径": DEFAULT_SHEETSET_PATH},
            rows=(group_row(张数=count),),
        )
        result = parse_creation_workbook(data, standard, options)
        assert result.value is None, count
        found = diagnostic(result, "CREATION_XLSX_COUNT_INVALID")
        assert (found.sheet, found.row, found.column) == (SHEET_SHEET, 2, "B")
