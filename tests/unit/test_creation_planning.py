"""标准驱动创建计划与创建求值缺键门禁测试（PLAN-DM-036 Task 3）。

夹具标准在 Task 2 的 ``creation_xlsx_fixtures.STANDARD_DOCUMENT`` 基础上追加一个
必填普通 sheet 属性 ``prop-required``：本模块的 ``draft`` 夹具含 3 张图纸且该值被
**明确清空**，用于固定「必填非空只在创建实际值门禁判断」这一契约。

本模块的 ``options`` 夹具返回 ``SuffixOptions``（覆盖 ``tests/unit/conftest.py`` 中
同名的资产候选夹具），与 ``create_creation_plan`` 的 ``suffix_options`` 参数同名口径
一致：数字位数/起点来自标准，标题后缀与不编号关键字来自设置。
"""

import copy
from dataclasses import replace
from pathlib import Path

import pytest
from creation_xlsx_fixtures import STANDARD_DOCUMENT

from dst_manager.domain.creation import (
    SHEET_SCOPE,
    SHEETSET_SCOPE,
    CreationDraft,
    CreationGroupInput,
    ordinary_property_defaults,
)
from dst_manager.domain.creation_planning import create_creation_plan
from dst_manager.domain.models import SuffixOptions
from dst_manager.domain.standard_rules import (
    CompiledProperties,
    compile_standard_properties,
    evaluate_standard_properties,
)
from dst_manager.domain.standards import (
    DrawingStandard,
    DwgNamingTemplate,
    StandardSegment,
    parse_published_standard_document,
)

REQUIRED_SHEET_PROPERTY = "prop-required"
REQUIRED_SHEET_VALUE = "RF-001"
TARGET_PATH = r"C:\Projects\新建项目"


def _plan_document() -> dict[str, object]:
    """Task 2 夹具标准 + 一个必填普通 sheet 属性（无默认值，必须由用户填写）。"""
    document = copy.deepcopy(STANDARD_DOCUMENT)
    properties = _properties(document)
    properties.append(
        {
            "property_id": REQUIRED_SHEET_PROPERTY,
            "name": "编审批号",
            "scope": "sheet",
            "kind": "text",
            "required": True,
            "default_value": "",
        }
    )
    return document


def _properties(document: dict[str, object]) -> list[dict[str, object]]:
    properties = document["properties"]
    assert isinstance(properties, list)
    return properties


#: 夹具标准：普通 sheetset（文本/枚举）、派生 sheetset（映射）、普通 sheet（文本/枚举/必填）、
#: 派生 sheet（组合）、标准级 DWG 命名模板与两个资产声明。
STANDARD = parse_published_standard_document(_plan_document())


def standard_with_digits(digits: int) -> DrawingStandard:
    """只改编号位数的标准变体（起点仍为 ``numbering.start``）。"""
    return replace(STANDARD, numbering=replace(STANDARD.numbering, digits=digits))


def standard_with_sheet_number_composition() -> DrawingStandard:
    """``prop-label`` 改为「平面图-{sheet.number}」：逐张取值必须不同。"""
    document = _plan_document()
    for prop in _properties(document):
        if prop["property_id"] == "prop-label":
            prop["segments"] = [
                {"literal": "平面图"},
                {"literal": "-"},
                {"system_field": "sheet.number"},
            ]
    return parse_published_standard_document(document)


def standard_with_literal_naming(body: str) -> DrawingStandard:
    """DWG 命名模板只含固定文本：不同组必然得到同名文件，用于碰撞用例。"""
    return replace(
        STANDARD,
        dwg_naming=DwgNamingTemplate(segments=(StandardSegment(literal=body),)),
    )


def options_with_keyword(keyword: str) -> SuffixOptions:
    return SuffixOptions(True, 1, (keyword,))


def _sheetset_values(**overrides: str) -> dict[str, str]:
    values = ordinary_property_defaults(STANDARD, SHEETSET_SCOPE)
    values.update(overrides)
    return values


def _group(
    group_id: str,
    title: str,
    count: int,
    *,
    created_order: int = 1,
    required: str = REQUIRED_SHEET_VALUE,
    base_asset_id: str = "base-a1",
    layout_asset_id: str = "layout-a1",
    paper_layout: str = "A1",
) -> CreationGroupInput:
    """一个完整输入的图纸组：``sheet_values`` 覆盖全部可输入普通 sheet 属性。"""
    values = ordinary_property_defaults(STANDARD, SHEET_SCOPE)
    values[REQUIRED_SHEET_PROPERTY] = required
    return CreationGroupInput(
        group_id=group_id,
        created_order=created_order,
        title=title,
        count=count,
        base_asset_id=base_asset_id,
        layout_asset_id=layout_asset_id,
        paper_layout=paper_layout,
        sheet_values=values,
    )


def _draft(
    groups: list[CreationGroupInput],
    *,
    sheetset_values: dict[str, str] | None = None,
    target_path: str = TARGET_PATH,
    revision: int = 3,
) -> CreationDraft:
    return CreationDraft(
        id="draft-1",
        standard_id=STANDARD.standard_id,
        standard_version=STANDARD.version,
        revision=revision,
        step="review",
        target_path=target_path,
        sheetset_values=_sheetset_values() if sheetset_values is None else sheetset_values,
        groups=tuple(groups),
    )


def draft_with_cover_and_groups(counts: tuple[int, ...]) -> CreationDraft:
    """首个组图名命中「封面」关键字，其后两组按给定张数排列。"""
    titles = ("封面", "平面图", "剖面图")
    return _draft(
        [
            _group(f"group-{index + 1}", title, count, created_order=index + 1)
            for index, (title, count) in enumerate(zip(titles, counts))
        ]
    )


def draft_with_sheet_number_composition() -> CreationDraft:
    """一个含 2 张图纸的图纸组：``prop-label`` 逐张取到不同图号。"""
    return _draft([_group("group-1", "平面图", 2)])


def diagnostic_codes(plan) -> list[str]:
    """去重且保持首次出现顺序的稳定错误码序列。"""
    seen: list[str] = []
    for diagnostic in plan.diagnostics:
        if diagnostic.code not in seen:
            seen.append(diagnostic.code)
    return seen


@pytest.fixture
def standard() -> DrawingStandard:
    return STANDARD


@pytest.fixture
def options() -> SuffixOptions:
    return SuffixOptions(True, 1)


@pytest.fixture
def draft() -> CreationDraft:
    """夹具含 3 张且 ``prop-required`` 被明确清空。"""
    return _draft([_group("group-1", "平面图", 3, required="")])


@pytest.fixture
def compiled(standard: DrawingStandard) -> CompiledProperties:
    return compile_standard_properties(standard)


# ---- F2：漏传普通属性键不得被当作空值 ---------------------------------------


def test_mapping_missing_key_does_not_become_empty_result(compiled) -> None:
    missing = evaluate_standard_properties(compiled, {}, {})
    assert "prop-code" not in missing.values
    assert "STANDARD_DERIVED_UPSTREAM_INVALID" in [item.code for item in missing.diagnostics]
    explicit_empty = evaluate_standard_properties(compiled, {"prop-major": ""}, {})
    assert explicit_empty.values["prop-code"] == ""


# ---- 创建输入门禁 -----------------------------------------------------------


def test_required_sheet_value_blocks_every_expanded_sheet(draft, standard, options) -> None:
    plan = create_creation_plan(draft, standard, options)  # 夹具含 3 张且 prop-required 被明确清空
    assert plan.has_errors
    assert [(item.group_id, item.property_id) for item in plan.diagnostics if item.code == "CREATION_REQUIRED_VALUE_MISSING"] == [
        (draft.groups[0].group_id, "prop-required")
    ]


def test_missing_sheetset_key_and_missing_group_key_are_diagnostics() -> None:
    draft = _draft(
        [
            CreationGroupInput(
                group_id="group-1",
                created_order=1,
                title="平面图",
                count=1,
                base_asset_id="base-a1",
                layout_asset_id="layout-a1",
                paper_layout="A1",
                sheet_values={"prop-stage": "施工图"},
            )
        ],
        sheetset_values={"prop-name": "示例工程"},
    )

    plan = create_creation_plan(draft, STANDARD, SuffixOptions(True, 1))

    assert plan.has_errors
    assert [(item.property_id, item.group_id) for item in plan.diagnostics if item.code == "CREATION_SHEETSET_VALUE_MISSING"] == [
        ("prop-major", "")
    ]
    assert sorted(
        item.property_id
        for item in plan.diagnostics
        if item.code == "CREATION_GROUP_VALUE_MISSING"
    ) == ["prop-part", "prop-required"]


def test_optional_empty_value_is_not_a_missing_key() -> None:
    """可选普通属性显式空串合法：``prop-part`` 空值不报错，只有必填清空才阻断。"""
    plan = create_creation_plan(
        _draft([_group("group-1", "平面图", 1)]), STANDARD, SuffixOptions(True, 1)
    )

    assert plan.diagnostics == ()
    assert plan.has_errors is False
    assert plan.groups[0].sheets[0].values["prop-part"] == ""


def test_invalid_enum_and_invalid_count_and_empty_title_are_diagnostics() -> None:
    draft = _draft(
        [
            _group("group-1", "  ", 0, created_order=1),
        ],
        sheetset_values=_sheetset_values(**{"prop-major": "未知专业"}),
    )

    plan = create_creation_plan(draft, STANDARD, SuffixOptions(True, 1))

    assert plan.has_errors
    assert diagnostic_codes(plan) == [
        "CREATION_GROUP_TITLE_EMPTY",
        "CREATION_GROUP_COUNT_INVALID",
        "STANDARD_ENUM_VALUE_INVALID",
        "STANDARD_DERIVED_UPSTREAM_INVALID",
    ]


def test_invalid_target_path_blocks_plan_without_group_absolute_paths() -> None:
    """非法目标路径阻断计划，且不产出可疑的逐组绝对路径。"""
    draft = _draft([_group("group-1", "平面图", 1)], target_path="C:项目")

    plan = create_creation_plan(draft, STANDARD, SuffixOptions(True, 1))

    assert plan.has_errors
    assert [item.code for item in plan.diagnostics] == ["CREATION_TARGET_PATH_DRIVE_INVALID"]
    assert plan.target_path == "C:项目"
    assert plan.groups[0].target_path == ""


def test_duplicate_group_title_ignores_case_and_surrounding_spaces() -> None:
    draft = _draft(
        [
            _group("group-1", "平面图", 1, created_order=1),
            _group("group-2", " 平面图 ", 1, created_order=2),
        ]
    )

    plan = create_creation_plan(draft, STANDARD, SuffixOptions(True, 1))

    assert plan.has_errors
    assert [item.group_id for item in plan.diagnostics if item.code == "CREATION_GROUP_TITLE_DUPLICATE"] == [
        "group-2"
    ]


def test_invalid_asset_and_paper_layout_are_diagnostics() -> None:
    draft = _draft(
        [
            _group("group-1", "平面图", 1, created_order=1, base_asset_id="base-missing"),
            _group("group-2", "剖面图", 1, created_order=2, paper_layout="A0"),
        ]
    )

    plan = create_creation_plan(draft, STANDARD, SuffixOptions(True, 1))

    assert plan.has_errors
    assert diagnostic_codes(plan) == [
        "CREATION_ASSET_INVALID",
        "CREATION_PAPER_LAYOUT_INVALID",
    ]
    assert plan.groups[0].base_template == ""
    assert plan.groups[1].layout_template == ""


# ---- 编号、标题与按组预览投影 -----------------------------------------------


def test_unnumbered_group_is_zero_and_does_not_advance_numbering() -> None:
    plan = create_creation_plan(draft_with_cover_and_groups((2, 3, 2)), standard_with_digits(2), options_with_keyword("封面"))
    assert [group.number_range for group in plan.groups] == ["00", "01-03", "04-05"]
    assert [sheet.number for sheet in plan.groups[0].sheets] == ["00", "00"]


def test_group_preview_keeps_first_value_and_full_sheet_detail(options) -> None:
    plan = create_creation_plan(draft_with_sheet_number_composition(), standard_with_sheet_number_composition(), options)
    assert plan.groups[0].property_cells["prop-label"].first_value == "平面图-01"
    assert [row.value for row in plan.groups[0].property_cells["prop-label"].sheets] == ["平面图-01", "平面图-02"]


def test_numbering_uses_standard_digits_and_start() -> None:
    plan = create_creation_plan(
        draft_with_cover_and_groups((2, 3, 2)),
        replace(
            standard_with_digits(3),
            numbering=replace(standard_with_digits(3).numbering, start=5),
        ),
        options_with_keyword("封面"),
    )

    assert [group.number_range for group in plan.groups] == ["000", "005-007", "008-009"]


def test_sheet_titles_and_layout_names_follow_suffix_options() -> None:
    plan = create_creation_plan(
        _draft([_group("group-1", "平面图", 2)]), STANDARD, SuffixOptions(True, 1)
    )

    group = plan.groups[0]
    assert group.title_range == "平面图 (一)-(二)"
    assert [sheet.title for sheet in group.sheets] == ["平面图 (一)", "平面图 (二)"]
    assert [sheet.layout_name for sheet in group.sheets] == ["01 平面图 (一)", "02 平面图 (二)"]


def test_unnumbered_group_without_suffix_blocks_duplicate_layout_names() -> None:
    """SPEC-DM-018 §6.2：不编号组且关闭尾序号导致同名布局时预览直接阻断。"""
    plan = create_creation_plan(
        draft_with_cover_and_groups((2, 1, 1)), STANDARD, SuffixOptions(False, 1, ("封面",))
    )

    assert plan.has_errors
    assert [item.group_id for item in plan.diagnostics if item.code == "DUPLICATE_LAYOUT_NAME"] == [
        "group-1"
    ]


def test_dwg_name_collision_is_case_insensitive_and_blocks_the_plan() -> None:
    draft = _draft(
        [
            _group("group-1", "Cover", 1, created_order=1),
            _group("group-2", "COVER", 1, created_order=2),
        ]
    )

    plan = create_creation_plan(draft, standard_with_literal_naming("Cover"), SuffixOptions(True, 1))

    assert plan.has_errors
    assert [item.group_id for item in plan.diagnostics if item.code == "DWG_TARGET_COLLISION"] == [
        "group-1",
        "group-2",
    ]
    assert [group.dwg_name for group in plan.groups] == ["", ""]


def test_dwg_name_failure_never_yields_a_partial_file_name() -> None:
    """``sheetset`` 派生失败时不得产出半成品文件名（此处枚举非法阻断映射）。"""
    draft = _draft(
        [_group("group-1", "平面图", 1)],
        sheetset_values=_sheetset_values(**{"prop-major": "未知专业"}),
    )

    plan = create_creation_plan(draft, STANDARD, SuffixOptions(True, 1))

    assert plan.has_errors
    assert plan.groups[0].dwg_name == ""
    assert plan.groups[0].target_path == ""
    assert diagnostic_codes(plan) == [
        "STANDARD_ENUM_VALUE_INVALID",
        "STANDARD_DERIVED_UPSTREAM_INVALID",
        "DWG_NAMING_SOURCE_MISSING",
    ]


# ---- 计划形状与确定性摘要 ---------------------------------------------------


def test_valid_plan_exposes_targets_templates_and_two_level_values() -> None:
    draft = _draft([_group("group-1", "平面图", 2)])
    plan = create_creation_plan(draft, STANDARD, SuffixOptions(True, 1))

    assert plan.diagnostics == ()
    assert plan.target_path == TARGET_PATH
    assert plan.sheetset_values == {
        "prop-name": "默认工程",
        "prop-major": "燃气",
        "prop-code": "RQ",
    }

    group = plan.groups[0]
    assert group.group_id == "group-1"
    assert group.number_range == "01-02"
    assert group.dwg_name == "RQ-01-02 平面图.dwg"
    assert Path(group.target_path) == Path(TARGET_PATH) / group.dwg_name
    assert group.base_template == "templates/a1.dwt"
    assert group.layout_template == "templates/a1-layout.dwt"
    assert group.paper_layout == "A1"
    assert group.sheet_count == 2
    assert group.sheets[0].values["prop-label"] == "RQ-01"
    assert group.sheets[1].values["prop-label"] == "RQ-02"
    assert group.property_cells["prop-required"].first_value == REQUIRED_SHEET_VALUE


def test_digest_is_stable_and_covers_revision_numbering_and_outputs() -> None:
    draft = _draft([_group("group-1", "平面图", 2)])
    plan = create_creation_plan(draft, STANDARD, SuffixOptions(True, 1))

    assert plan.digest == create_creation_plan(draft, STANDARD, SuffixOptions(True, 1)).digest
    assert plan.digest != create_creation_plan(
        replace(draft, revision=draft.revision + 1), STANDARD, SuffixOptions(True, 1)
    ).digest
    assert plan.digest != create_creation_plan(
        draft, standard_with_digits(3), SuffixOptions(True, 1)
    ).digest
    assert plan.digest != create_creation_plan(
        draft, STANDARD, SuffixOptions(True, 2)
    ).digest
    assert plan.digest != create_creation_plan(
        draft, STANDARD, SuffixOptions(True, 1, ("封面",))
    ).digest
