# 不编号子集编号规则单元测试（SPEC-DM-014）
#
# 规则要点：
#   * 子集可编辑标题命中关键字 → 该子集全部图纸图号固定为 0 填充（位数继承项目编号位数）；
#   * 不编号子集不消耗全局序号，新建它或在其内增删图纸都不改变其他子集图号；
#   * 图号范围退化为单值（000），DWG 文件名前缀沿用「前缀 + 图号范围 + 标题」既有规则。
from pathlib import Path

import pytest

from dst_manager.domain.editing import SuffixOptions, derive_document_structure
from dst_manager.domain.models import (
    LayoutReference,
    Sheet,
    SheetSetDocument,
    Subset,
)


def _sheet(sheet_id: str, number: str, title: str) -> Sheet:
    file_name = f"RQ-{number} {title}.dwg" if number else ""
    layout_name = f"{number} {title}".strip()
    return Sheet(sheet_id, number, title, LayoutReference(file_name, "", layout_name, ""))


def _document(subsets: list[Subset]) -> SheetSetDocument:
    return SheetSetDocument("db", "图纸集", subsets)


def _numbers(derived) -> list[list[str]]:
    return [[sheet.number for sheet in subset.sheets] for subset in derived.subsets]


def _insert_subset(title: str, position: int, count: int) -> dict[str, object]:
    return {
        "type": "insert_subset",
        "position": position,
        "title": title,
        "initial_sheet_count": count,
        "base_template_file": "C:/模板/图纸基底.dwg",
        "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
    }


def _delete_subset(subset_id: str) -> dict[str, object]:
    return {
        "type": "delete_subset",
        "subset_id": subset_id,
        "confirm_delete_all_sheets": True,
        "confirm_delete_main_dwg": True,
    }


def test_new_unnumbered_subset_uses_zero_padding_width_and_keeps_other_numbers() -> None:
    document = _document(
        [
            Subset("subset-a", "1-2 图纸目录", 1, [_sheet("a1", "001", "图纸目录"), _sheet("a2", "002", "图纸目录")]),
            Subset("subset-c", "3 平面图", 2, [_sheet("c1", "003", "平面图")]),
        ]
    )

    derived = derive_document_structure(
        document,
        [_insert_subset("封面", 0, 2)],
        SuffixOptions(True, 1, ("封面",)),
    )

    assert _numbers(derived) == [["000", "000"], ["001", "002"], ["003"]]
    assert [subset.number_range for subset in derived.subsets] == ["000", "001-002", "003"]
    assert [subset.display_name for subset in derived.subsets] == ["000 封面", "001-002 图纸目录", "003 平面图"]


def test_unnumbered_subset_number_range_is_single_value_not_range() -> None:
    document = _document(
        [
            Subset("subset-a", "1 图纸目录", 1, [_sheet("a1", "001", "图纸目录")]),
            Subset("subset-b", "2-3 封面", 2, [_sheet("b1", "002", "封面"), _sheet("b2", "003", "封面")]),
        ]
    )

    derived = derive_document_structure(document, [], SuffixOptions(True, 1, ("封面",)))

    assert derived.subsets[1].number_range == "000"
    assert derived.subsets[1].display_name == "000 封面"


def test_unnumbered_subset_zero_padding_follows_project_number_width() -> None:
    document = _document(
        [
            Subset("subset-a", "0001 图纸目录", 1, [_sheet("a1", "0001", "图纸目录")]),
            Subset("subset-b", "0002 封面", 2, [_sheet("b1", "0002", "封面")]),
        ]
    )

    derived = derive_document_structure(document, [], SuffixOptions(True, 1, ("封面",)))

    assert _numbers(derived) == [["0001"], ["0000"]]
    assert derived.subsets[1].number_range == "0000"


def test_unnumbered_subset_at_project_start_does_not_drag_number_seed_to_zero() -> None:
    # 排首位的不编号子集不得把起点拉成 0（否则全部子集都从 000 起编）
    document = _document(
        [
            Subset("subset-u", "1 封面", 1, [_sheet("u1", "001", "封面")]),
            Subset("subset-a", "2-3 图纸目录", 2, [_sheet("a1", "002", "图纸目录"), _sheet("a2", "003", "图纸目录")]),
        ]
    )

    derived = derive_document_structure(document, [], SuffixOptions(True, 1, ("封面",)))

    assert _numbers(derived) == [["000"], ["002", "003"]]
    assert [subset.number_range for subset in derived.subsets] == ["000", "002-003"]


@pytest.mark.parametrize(
    ("cover_number", "first_number"),
    [("00", "01"), ("000", "001"), ("0000", "0001")],
)
def test_deleting_applied_unnumbered_subset_does_not_drag_number_seed_to_zero(
    cover_number: str,
    first_number: str,
) -> None:
    # 用户报告（2026-09-14）：删除已应用的不编号封面后，紧随其后的图纸目录被重编为 0 起（00 图纸目录）。
    # 原因：编号种子读的是**命令前**文档，而排除集合按**命令后**子集列表计算，被删除的封面
    # 已不在集合里，它的 0 填充图号就成了种子（起点 0）。命令前文档的排除集合也必须按
    # 命令前标题计算（SPEC-DM-014 §行为 3、§行为 5）。
    document = _document(
        [
            Subset("subset-u", f"{cover_number} 封面", 1, [_sheet("u1", cover_number, "封面")]),
            Subset("subset-a", f"{first_number} 图纸目录", 2, [_sheet("a1", first_number, "图纸目录")]),
        ]
    )

    derived = derive_document_structure(
        document,
        [_delete_subset("subset-u")],
        SuffixOptions(True, 1, ("封面",)),
    )

    assert _numbers(derived) == [[first_number]]
    assert derived.subsets[0].display_name == f"{first_number} 图纸目录"


def test_deleting_unnumbered_subset_keeps_following_numbers_without_zero_padding() -> None:
    # 关键字刚开启、封面仍是既有编号（尚未应用 0 填充）时删除它：后续子集也不得前移
    # （删除不消耗序号、也不释放号段给后续子集，SPEC-DM-014 §行为 5）
    document = _document(
        [
            Subset("subset-u", "1 封面", 1, [_sheet("u1", "001", "封面")]),
            Subset("subset-a", "2 说明", 2, [_sheet("a1", "002", "说明")]),
        ]
    )

    derived = derive_document_structure(
        document,
        [_delete_subset("subset-u")],
        SuffixOptions(True, 1, ("封面",)),
    )

    assert _numbers(derived) == [["002"]]
    assert derived.subsets[0].display_name == "002 说明"


def test_number_seed_falls_back_to_one_digit_when_project_has_no_numbered_sheet() -> None:
    # 项目内只有不编号子集时无编号种子：回退 1 位宽，图号为单个 0
    document = _document(
        [Subset("subset-u", "封面", 1, [_sheet("u1", "", "封面")])]
    )

    derived = derive_document_structure(document, [], SuffixOptions(True, 1, ("封面",)))

    assert _numbers(derived) == [["0"]]
    assert derived.subsets[0].number_range == "0"


def test_all_unnumbered_project_keeps_existing_number_width() -> None:
    # 全部子集都不编号时，位数仍取文档既有图号位数（不因关键字命中退化成 1 位）
    document = _document(
        [
            Subset("subset-u", "1 封面", 1, [_sheet("u1", "001", "封面")]),
            Subset("subset-v", "2 图纸目录", 2, [_sheet("v1", "002", "图纸目录")]),
        ]
    )

    derived = derive_document_structure(document, [], SuffixOptions(True, 1, ("封面", "目录")))

    assert _numbers(derived) == [["000"], ["000"]]


def test_enabling_keyword_releases_number_band_and_shifts_following_subsets() -> None:
    # 动态判定：既有子集改名/新增关键字命中后释放号段，后续子集整体前移（预览可见）
    document = _document(
        [
            Subset("subset-a", "1 说明", 1, [_sheet("a1", "001", "说明")]),
            Subset("subset-u", "2 封面", 2, [_sheet("u1", "002", "封面")]),
            Subset("subset-b", "3 平面图", 3, [_sheet("b1", "003", "平面图")]),
        ]
    )

    before = derive_document_structure(document, [], SuffixOptions(True, 1))
    after = derive_document_structure(document, [], SuffixOptions(True, 1, ("封面",)))

    assert _numbers(before) == [["001"], ["002"], ["003"]]
    assert _numbers(after) == [["001"], ["000"], ["002"]]


def test_changing_subset_title_into_keyword_hit_marks_it_unnumbered() -> None:
    # 动态判定同样适用于 update_subset 改名：标题命中关键字即整子集转为不编号
    document = _document(
        [
            Subset("subset-a", "1 说明", 1, [_sheet("a1", "001", "说明")]),
            Subset("subset-b", "2 平面图", 2, [_sheet("b1", "002", "平面图")]),
        ]
    )

    derived = derive_document_structure(
        document,
        [{"type": "update_subset", "subset_id": "subset-b", "title": "封面"}],
        SuffixOptions(True, 1, ("封面",)),
    )

    assert _numbers(derived) == [["001"], ["000"]]
    assert derived.subsets[1].display_name == "000 封面"


def test_inserting_sheets_into_unnumbered_subset_keeps_other_subsets_numbers() -> None:
    document = _document(
        [
            Subset("subset-a", "1 说明", 1, [_sheet("a1", "001", "说明")]),
            Subset("subset-u", "2 封面", 2, [_sheet("u1", "002", "封面")]),
            Subset("subset-b", "3-4 平面图", 3, [_sheet("b1", "003", "平面图"), _sheet("b2", "004", "平面图")]),
        ]
    )
    options = SuffixOptions(True, 1, ("封面",))
    baseline = _numbers(derive_document_structure(document, [], options))

    derived = derive_document_structure(
        document,
        [
            {
                "type": "insert_sheet",
                "target_subset_id": "subset-u",
                "position": 1,
                "count": 2,
                "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
            }
        ],
        options,
    )

    assert baseline == [["001"], ["000"], ["002", "003"]]
    assert _numbers(derived) == [["001"], ["000", "000", "000"], ["002", "003"]]


def test_deleting_sheet_inside_unnumbered_subset_keeps_other_subsets_numbers() -> None:
    document = _document(
        [
            Subset("subset-a", "1 说明", 1, [_sheet("a1", "001", "说明")]),
            Subset("subset-u", "2-3 封面", 2, [_sheet("u1", "002", "封面"), _sheet("u2", "003", "封面")]),
            Subset("subset-b", "4 平面图", 3, [_sheet("b1", "004", "平面图")]),
        ]
    )
    options = SuffixOptions(True, 1, ("封面",))

    derived = derive_document_structure(
        document,
        [{"type": "delete_sheet", "sheet_id": "u2"}],
        options,
    )

    assert _numbers(derived) == [["001"], ["000"], ["002"]]


def test_new_unnumbered_subset_does_not_consume_number_band() -> None:
    document = _document(
        [
            Subset("subset-a", "1-2 图纸目录", 1, [_sheet("a1", "001", "图纸目录"), _sheet("a2", "002", "图纸目录")]),
            Subset("subset-c", "3 平面图", 2, [_sheet("c1", "003", "平面图")]),
        ]
    )

    derived = derive_document_structure(
        document,
        [_insert_subset("封面", 1, 1)],
        SuffixOptions(True, 1, ("封面",)),
    )

    assert _numbers(derived) == [["001", "002"], ["000"], ["003"]]


def test_unnumbered_subset_keeps_global_title_suffix_rules() -> None:
    document = _document(
        [
            Subset("subset-u", "1 封面", 1, [_sheet("u1", "001", "封面")]),
            Subset("subset-a", "2-3 图纸目录", 2, [_sheet("a1", "002", "图纸目录"), _sheet("a2", "003", "图纸目录")]),
        ]
    )

    derived = derive_document_structure(
        document,
        [_insert_subset("封面", 1, 1)],
        SuffixOptions(True, 2, ("封面",)),
    )

    assert [sheet.title for sheet in derived.subsets[0].sheets] == ["封面 (1)"]
    assert [sheet.layout.layout_name for sheet in derived.subsets[0].sheets] == ["000 封面 (1)"]
    assert [sheet.title for sheet in derived.subsets[1].sheets] == ["封面 (2)"]
    assert [sheet.layout.layout_name for sheet in derived.subsets[1].sheets] == ["000 封面 (2)"]


def test_unnumbered_subset_target_file_name_uses_prefix_and_zero_range() -> None:
    document = _document(
        [
            Subset("subset-a", "1-2 图纸目录", 1, [_sheet("a1", "001", "图纸目录"), _sheet("a2", "002", "图纸目录")]),
        ]
    )

    derived = derive_document_structure(
        document,
        [_insert_subset("封面", 0, 2)],
        SuffixOptions(True, 1, ("封面",)),
    )

    assert Path(derived.subsets[0].target_file).name == "RQ-000 封面 (一)-(二).dwg"
    assert Path(derived.subsets[1].target_file).name == "RQ-001-002 图纸目录 (一)-(二).dwg"


def test_keyword_matching_is_case_insensitive_and_multi_keyword_or() -> None:
    document = _document(
        [
            Subset("subset-a", "1 说明", 1, [_sheet("a1", "001", "说明")]),
            Subset("subset-u", "2 Cover Sheet", 2, [_sheet("u1", "002", "Cover Sheet")]),
            Subset("subset-v", "3 图纸目录", 3, [_sheet("v1", "003", "图纸目录")]),
        ]
    )

    derived = derive_document_structure(document, [], SuffixOptions(True, 1, ("cover", "目录")))

    assert _numbers(derived) == [["001"], ["000"], ["000"]]


def test_empty_keyword_list_keeps_legacy_numbering() -> None:
    document = _document(
        [
            Subset("subset-a", "1 说明", 1, [_sheet("a1", "001", "说明")]),
            Subset("subset-u", "2 封面", 2, [_sheet("u1", "002", "封面")]),
        ]
    )

    derived = derive_document_structure(document, [], SuffixOptions(True, 1))

    assert _numbers(derived) == [["001"], ["002"]]
    assert [subset.display_name for subset in derived.subsets] == ["001 说明", "002 封面"]


def test_two_unnumbered_subsets_share_zero_number_and_display_name() -> None:
    # 两个同标题不编号子集会得到相同显示名与同号段；目标 DWG 重名由发布前校验拦下
    document = _document(
        [
            Subset("subset-a", "1 说明", 1, [_sheet("a1", "001", "说明")]),
            Subset("subset-u1", "2 封面", 2, [_sheet("u1", "002", "封面")]),
            Subset("subset-u2", "3 封面", 3, [_sheet("u2", "003", "封面")]),
        ]
    )

    derived = derive_document_structure(document, [], SuffixOptions(True, 1, ("封面",)))

    assert _numbers(derived) == [["001"], ["000"], ["000"]]
    assert [subset.display_name for subset in derived.subsets] == ["001 说明", "000 封面", "000 封面"]


# ---- 设置 → 计划接线（application 层，SPEC-DM-014 §4）----


def test_service_preview_passes_normalized_settings_keywords_into_plan(tmp_path, tiny_workspace) -> None:
    # 端到端接线：设置文本 → normalize_keywords → SuffixOptions → 计划图号全 000
    from dst_manager.application.service import DstManagerService
    from dst_manager.config import Settings

    dst, _ = tiny_workspace
    service = DstManagerService(
        Settings(data_dir=tmp_path / "data", unnumbered_subset_keywords=" 封面， 目录,封面 ")
    )
    workspace = service.open_workspace(dst)
    subset_id = workspace.document.subsets[0].acsm_id

    preview = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_subset_title", "subset_id": subset_id, "title": "封面"}],
    )

    group = preview["execution_intent"]["groups"][0]
    # 半/全角逗号、trim、去重均已在领域层完成；图号位数继承文档既有 001 的 3 位
    assert group["subset_name"] == "000 封面"
    assert [layout["number"] for layout in group["layouts"]] == ["000"]
    assert Path(group["target_file"]).name.endswith("000 封面.dwg")


def test_service_preview_keeps_legacy_numbering_without_keywords(tmp_path, tiny_workspace) -> None:
    from dst_manager.application.service import DstManagerService
    from dst_manager.config import Settings

    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    subset_id = workspace.document.subsets[0].acsm_id

    preview = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_subset_title", "subset_id": subset_id, "title": "封面"}],
    )

    group = preview["execution_intent"]["groups"][0]
    assert group["subset_name"] == "001 封面"
    assert [layout["number"] for layout in group["layouts"]] == ["001"]
