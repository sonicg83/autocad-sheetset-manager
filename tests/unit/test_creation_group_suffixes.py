"""创建与编辑共用同名组后缀，DWG 名称保留实际图纸标题的序号。"""

from dataclasses import replace

import pytest
from creation_xlsx_fixtures import STANDARD_DOCUMENT

from dst_manager.domain.creation import (
    CreationDraft,
    CreationGroupInput,
    ordinary_property_defaults,
)
from dst_manager.domain.creation_planning import create_creation_plan
from dst_manager.domain.models import SuffixOptions
from dst_manager.domain.sheet_numbering import compress_group_title
from dst_manager.domain.standards import (
    DwgNamingTemplate,
    StandardSegment,
    parse_published_standard_document,
)


def _plan(counts, options, *, titles=None, template=None):
    standard = parse_published_standard_document(STANDARD_DOCUMENT)
    if template is not None:
        standard = replace(standard, dwg_naming=template)
    draft = CreationDraft(
        id="draft-suffix",
        standard_id=standard.standard_id,
        revision=1,
        step="review",
        target_path=r"C:\Projects\新建项目",
        sheetset_values=ordinary_property_defaults(standard, "sheetset"),
        groups=tuple(
            CreationGroupInput(
                group_id=f"group-{index + 1}",
                created_order=index + 1,
                title=titles[index] if titles else "平面图",
                count=count,
                base_asset_id="base-a1",
                layout_asset_id="layout-a1",
                paper_layout="A1",
                sheet_values=ordinary_property_defaults(standard, "sheet"),
            )
            for index, count in enumerate(counts)
        ),
    )
    return create_creation_plan(draft, standard, options)


@pytest.mark.parametrize(
    ("suffix_type", "ranges", "sheet_titles"),
    [
        (1, ["平面图 (一)-(二)", "平面图 (三)-(五)"],
         ["平面图 (一)", "平面图 (二)", "平面图 (三)", "平面图 (四)", "平面图 (五)"]),
        (2, ["平面图 (1)-(2)", "平面图 (3)-(5)"],
         ["平面图 (1)", "平面图 (2)", "平面图 (3)", "平面图 (4)", "平面图 (5)"]),
    ],
)
def test_same_title_groups_share_suffixes_and_keep_standard_filename_template(
    suffix_type, ranges, sheet_titles
):
    plan = _plan((2, 3), SuffixOptions(True, suffix_type))

    assert plan.diagnostics == ()
    assert [sheet.title for group in plan.groups for sheet in group.sheets] == sheet_titles
    assert [group.title_range for group in plan.groups] == ranges
    assert [group.dwg_name for group in plan.groups] == [
        f"RQ-01-02 {ranges[0]}.dwg", f"RQ-03-05 {ranges[1]}.dwg"
    ]


def test_single_sheet_same_title_groups_keep_their_actual_suffix_in_filenames():
    plan = _plan((1, 1), SuffixOptions(True, 1))

    assert plan.diagnostics == ()
    assert [group.title_range for group in plan.groups] == ["平面图 (一)", "平面图 (二)"]
    assert [group.dwg_name for group in plan.groups] == [
        "RQ-01 平面图 (一).dwg", "RQ-02 平面图 (二).dwg"
    ]


def test_title_only_template_uses_suffix_ranges_to_distinguish_same_title_dwgs():
    template = DwgNamingTemplate(segments=(StandardSegment(system_field="subset.name"),))
    plan = _plan((2, 3), SuffixOptions(True, 1), template=template)

    assert plan.diagnostics == ()
    assert [group.dwg_name for group in plan.groups] == [
        "平面图 (一)-(二).dwg", "平面图 (三)-(五).dwg"
    ]


def test_disabled_suffix_still_blocks_actual_filename_collisions():
    template = DwgNamingTemplate(segments=(StandardSegment(system_field="subset.name"),))
    plan = _plan((2, 3), SuffixOptions(False, 1), template=template)

    assert [item.code for item in plan.diagnostics] == ["DWG_TARGET_COLLISION"] * 2
    assert [group.dwg_name for group in plan.groups] == ["", ""]
    assert {sheet.title for group in plan.groups for sheet in group.sheets} == {"平面图"}


def test_disabled_suffix_allows_same_titles_when_template_distinguishes_files():
    plan = _plan((2, 3), SuffixOptions(False, 1))

    assert plan.diagnostics == ()
    assert [group.dwg_name for group in plan.groups] == [
        "RQ-01-02 平面图.dwg", "RQ-03-05 平面图.dwg"
    ]


def test_case_insensitive_titles_use_the_same_canonical_spelling_for_filename_ranges():
    plan = _plan((2, 1), SuffixOptions(True, 2), titles=[" Plan ", "PLAN"])

    assert plan.diagnostics == ()
    assert [group.dwg_name for group in plan.groups] == [
        "RQ-01-02 Plan (1)-(2).dwg", "RQ-03 Plan (3).dwg"
    ]


def test_interleaved_groups_only_advance_suffixes_for_the_same_title():
    plan = _plan((2, 1, 3), SuffixOptions(True, 1), titles=["平面图", "剖面图", "平面图"])

    assert plan.diagnostics == ()
    assert [group.dwg_name for group in plan.groups] == [
        "RQ-01-02 平面图 (一)-(二).dwg", "RQ-03 剖面图.dwg", "RQ-04-06 平面图 (三)-(五).dwg"
    ]


def test_reordering_same_title_groups_recalculates_the_suffix_ranges():
    plan = _plan((3, 2), SuffixOptions(True, 1))

    assert plan.diagnostics == ()
    assert [group.dwg_name for group in plan.groups] == [
        "RQ-01-03 平面图 (一)-(三).dwg", "RQ-04-05 平面图 (四)-(五).dwg"
    ]


@pytest.mark.parametrize("title", ["平面图", "平面图 (一)", "平面图 (3)"])
def test_single_sheet_title_compression_preserves_actual_title(title):
    assert compress_group_title("平面图", [title]) == title


@pytest.mark.parametrize(
    "titles",
    [
        ["剖面图 (一)"],
        ["剖面图"],
        ["平面图 (一"],
        [""],
        ["剖面图 (一)", "剖面图 (二)"],
        ["平面图 (一)", "剖面图 (二)"],
    ],
)
def test_title_compression_falls_back_for_unrelated_or_malformed_titles(titles):
    assert compress_group_title("平面图", titles) == "平面图"


def test_single_sheet_compression_accepts_canonical_case_insensitive_base():
    assert compress_group_title(" PLAN ", ["Plan (3)"]) == "Plan (3)"
