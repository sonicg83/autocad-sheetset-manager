"""标准级 DWG 命名模板渲染、文件名安全与碰撞预检测试（PLAN-DM-038 Task 3）。"""

from dataclasses import replace

import pytest

from dst_manager.domain.creation import validate_creation_target_path
from dst_manager.domain.standard_naming import (
    SubsetNamingContext,
    publish_naming_diagnostics,
    render_dwg_filename,
    segment_safety_violations,
    validate_dwg_filenames,
)
from dst_manager.domain.standards import (
    DrawingStandard,
    DwgNamingTemplate,
    StandardSegment,
    parse_published_standard_document,
)

DEFAULT_SEGMENTS: tuple[dict[str, object], ...] = (
    {"property_id": "prop-code"},
    {"literal": "-"},
    {"system_field": "subset.scope"},
    {"literal": " "},
    {"system_field": "subset.name"},
)


def _standard(segments: tuple[dict[str, object], ...]) -> DrawingStandard:
    """带 sheetset 映射属性 prop-code 与 sheet 属性 prop-sheet 的最小已发布标准。"""
    document: dict[str, object] = {
        "schema_version": 2,
        "standard_id": "szmedi.gas",
        "version": 1,
        "name": "市政燃气施工图",
        "supported_cad_versions": ["2016", "2020"],
        "properties": [
            {
                "property_id": "prop-major",
                "name": "专业",
                "previous_names": [],
                "scope": "sheetset",
                "kind": "enum",
                "enum_items": [{"item_id": "enum-gas", "value": "燃气"}],
            },
            {
                "property_id": "prop-code",
                "name": "专业代码",
                "previous_names": [],
                "scope": "sheetset",
                "kind": "mapping",
                "source_property_id": "prop-major",
                "mapping": [{"item_id": "enum-gas", "value": "RQ"}],
                "confirmed_source_items": [["enum-gas", "燃气"]],
            },
            {
                "property_id": "prop-sheet",
                "name": "图号",
                "previous_names": [],
                "scope": "sheet",
                "kind": "text",
            },
        ],
        "dwg_naming": {"segments": list(segments)},
        "assets": [],
        "numbering": {"sequence_field": "subset.sequence", "digits": 2},
    }
    return parse_published_standard_document(document)


def naming_standard(*segments: dict[str, object]) -> DrawingStandard:
    """最小已发布标准；默认模板为 ``{prop-code}-{subset.scope} {subset.name}``。"""
    return _standard(tuple(segments) if segments else DEFAULT_SEGMENTS)


def literal_standard(value: str) -> DrawingStandard:
    """命名模板仅含该固定文本。"""
    return _standard(({"literal": value},))


def test_renders_explicit_prefix_scope_and_name() -> None:
    result = render_dwg_filename(
        naming_standard(), {"prop-code": "RQ"}, SubsetNamingContext("007-011", "迁改平面图", 1)
    )
    assert result.filename == "RQ-007-011 迁改平面图.dwg"


@pytest.mark.parametrize("name", ["CON", "bad.", "a/b", "..", "x" * 237])
def test_rejects_unsafe_windows_filename(name: str) -> None:
    result = render_dwg_filename(
        literal_standard(name), {}, SubsetNamingContext("001", "示例", 1)
    )
    assert result.diagnostics


@pytest.mark.parametrize("name", ["CON", "bad.", "a/b", "..", "x" * 237])
def test_unsafe_names_report_distinct_codes(name: str) -> None:
    result = render_dwg_filename(
        literal_standard(name), {}, SubsetNamingContext("001", "示例", 1)
    )
    assert result.ok is False
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity == "error"


@pytest.mark.parametrize(
    ("text", "violations"),
    [
        ("平面图", ()),
        ("", ()),
        ("a/b", ("character",)),
        ("bad.", ("trailing",)),
        ("CON", ("reserved",)),
        # 保留设备名只看首个句点之前的部分；尾随句点另行判定。
        ("con.", ("trailing", "reserved")),
        ("a|b ", ("character", "trailing")),
    ],
)
def test_segment_safety_violations_report_kinds_in_fixed_order(
    text: str, violations: tuple[str, ...]
) -> None:
    assert segment_safety_violations(text) == violations


def test_naming_and_target_path_share_the_segment_safety_rule() -> None:
    """同一份片段安全规则分别映射到 DWG 命名与项目路径错误码。"""
    body = "平面图."
    assert segment_safety_violations(body) == ("trailing",)
    assert [
        item.code
        for item in render_dwg_filename(
            literal_standard(body), {}, SubsetNamingContext("001", "示例", 1)
        ).diagnostics
    ] == ["DWG_NAME_TRAILING_CHARACTER"]
    assert [
        item.code for item in validate_creation_target_path(f"C:\\Projects\\{body}")
    ] == ["CREATION_TARGET_PATH_TRAILING_CHARACTER"]


def test_default_template_renders_scope_and_name_without_prefix() -> None:
    standard = naming_standard(
        {"system_field": "subset.scope"}, {"literal": " "}, {"system_field": "subset.name"}
    )
    result = render_dwg_filename(standard, {}, SubsetNamingContext("001-003", "封面", 3))
    assert result.filename == "001-003 封面.dwg"
    assert result.ok is True


def test_subset_sequence_uses_controlled_padding() -> None:
    padded = naming_standard({"system_field": "subset.sequence", "format": "02"})
    assert render_dwg_filename(
        padded, {}, SubsetNamingContext("001", "封面", 3)
    ).filename == "03.dwg"
    plain = naming_standard({"system_field": "subset.sequence"})
    assert render_dwg_filename(
        plain, {}, SubsetNamingContext("001", "封面", 3)
    ).filename == "3.dwg"


def test_extension_is_appended_exactly_once() -> None:
    result = render_dwg_filename(
        naming_standard(), {"prop-code": "RQ"}, SubsetNamingContext("001", "封面", 1)
    )
    assert result.filename.endswith(".dwg")
    assert result.filename.count(".dwg") == 1


def test_body_carrying_the_extension_is_rejected() -> None:
    result = render_dwg_filename(
        literal_standard("图签.dwg"), {}, SubsetNamingContext("001", "封面", 1)
    )
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "DWG_NAME_EXTENSION_FORBIDDEN"
    ]


def test_length_limit_counts_the_appended_extension() -> None:
    assert render_dwg_filename(
        literal_standard("x" * 236), {}, SubsetNamingContext("001", "封面", 1)
    ).ok is True
    assert [d.code for d in render_dwg_filename(
        literal_standard("x" * 237), {}, SubsetNamingContext("001", "封面", 1)
    ).diagnostics] == ["DWG_NAME_TOO_LONG"]


def test_sheet_property_token_is_rejected_at_render_time() -> None:
    standard = replace(
        naming_standard(),
        dwg_naming=DwgNamingTemplate(segments=(StandardSegment(property_id="prop-sheet"),)),
    )
    result = render_dwg_filename(
        standard, {"prop-sheet": "A-001"}, SubsetNamingContext("001", "封面", 1)
    )
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "STANDARD_NAMING_FIELD_SCOPE_INVALID"
    ]


def test_missing_sheetset_value_makes_the_result_unusable() -> None:
    result = render_dwg_filename(
        naming_standard(), {}, SubsetNamingContext("001", "封面", 1)
    )
    assert result.ok is False
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "DWG_NAMING_SOURCE_MISSING"
    ]


def test_missing_subset_system_value_is_reported() -> None:
    standard = naming_standard({"system_field": "subset.scope"}, {"system_field": "subset.name"})
    result = render_dwg_filename(standard, {}, SubsetNamingContext("", "封面", 1))
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "STANDARD_SYSTEM_VALUE_MISSING"
    ]


def test_publish_warns_when_uniqueness_fields_are_both_absent() -> None:
    warning = publish_naming_diagnostics(literal_standard("封面"))
    assert [(item.code, item.severity) for item in warning] == [
        ("DWG_NAMING_UNIQUENESS_UNPROVEN", "warning")
    ]
    assert publish_naming_diagnostics(naming_standard()) == ()
    assert publish_naming_diagnostics(
        naming_standard({"system_field": "subset.sequence"})
    ) == ()


def test_validate_reports_case_insensitive_collisions() -> None:
    standard = naming_standard({"system_field": "subset.name"})
    results = validate_dwg_filenames(
        standard,
        {},
        [SubsetNamingContext("001", "ABC", 1), SubsetNamingContext("002", "abc", 2)],
    )
    assert [result.filename for result in results] == ["ABC.dwg", "abc.dwg"]
    assert [
        diagnostic.code for result in results for diagnostic in result.diagnostics
    ] == ["DWG_TARGET_COLLISION", "DWG_TARGET_COLLISION"]


def test_validate_keeps_distinct_targets_collision_free() -> None:
    results = validate_dwg_filenames(
        naming_standard(),
        {"prop-code": "RQ"},
        [SubsetNamingContext("001", "封面", 1), SubsetNamingContext("002", "平面图", 2)],
    )
    assert [result.filename for result in results] == [
        "RQ-001 封面.dwg",
        "RQ-002 平面图.dwg",
    ]
    assert all(result.ok for result in results)


def test_validate_does_not_collide_on_unusable_results() -> None:
    results = validate_dwg_filenames(
        naming_standard(),
        {},
        [SubsetNamingContext("001", "封面", 1), SubsetNamingContext("002", "平面图", 2)],
    )
    assert all(result.ok is False for result in results)
    assert [diagnostic.code for result in results for diagnostic in result.diagnostics] == [
        "DWG_NAMING_SOURCE_MISSING",
        "DWG_NAMING_SOURCE_MISSING",
    ]
