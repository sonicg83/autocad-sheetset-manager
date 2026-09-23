"""图纸标准派生属性编译、求值与发布诊断测试（PLAN-DM-038 Task 2）。

``codes()`` 返回**去重且保持首次出现顺序**的稳定错误码序列；每个被阻断的
派生属性各自携带 ``property_id`` 归属的 ``STANDARD_DERIVED_UPSTREAM_INVALID``，
逐属性归属由 ``test_blocked_derived_properties_are_attributed`` 单独固定。
"""

from collections.abc import Iterable

from dst_manager.domain.standard_rules import (
    compile_standard_properties,
    evaluate_standard_properties,
    publish_diagnostics,
)
from dst_manager.domain.standards import (
    StandardDiagnostic,
    parse_published_standard_document,
)


def standard_document(
    *, enum_value: str = "燃气", confirmed_value: str | None = "燃气"
) -> dict[str, object]:
    """Task 1 新 Schema 的完整最小文档：枚举源 + 映射 + 组合 + DWG 命名。"""
    return {
        "schema_version": 1,
        "standard_id": "szmedi.gas",
        "version": "2.1.0",
        "name": "市政燃气施工图",
        "supported_cad_versions": ["2016", "2020"],
        "properties": [
            {
                "property_id": "prop-major",
                "name": "专业",
                "previous_names": [],
                "scope": "sheetset",
                "kind": "enum",
                "required": False,
                "default_value": "",
                "enum_items": [{"item_id": "enum-gas", "value": enum_value}],
                "description": "",
            },
            {
                "property_id": "prop-code",
                "name": "专业代码",
                "previous_names": [],
                "scope": "sheetset",
                "kind": "mapping",
                "required": False,
                "default_value": "",
                "source_property_id": "prop-major",
                "mapping": [{"item_id": "enum-gas", "value": "RQ"}],
                "confirmed_source_items": (
                    [] if confirmed_value is None else [["enum-gas", confirmed_value]]
                ),
                "description": "",
            },
            {
                "property_id": "prop-label",
                "name": "图签",
                "previous_names": [],
                "scope": "sheetset",
                "kind": "composition",
                "required": False,
                "default_value": "",
                "segments": [
                    {"property_id": "prop-code"},
                    {"literal": "-"},
                    {"property_id": "prop-major"},
                ],
                "description": "",
            },
        ],
        "dwg_naming": {"segments": [{"property_id": "prop-code"}]},
        "assets": [],
        "numbering": {"sequence_field": "subset.sequence", "digits": 2},
    }


def _properties(document: dict[str, object]) -> list[dict[str, object]]:
    properties = document["properties"]
    assert isinstance(properties, list)
    return properties


def codes(diagnostics: Iterable[StandardDiagnostic]) -> list[str]:
    """去重且保持首次出现顺序的稳定错误码序列。"""
    seen: list[str] = []
    for diagnostic in diagnostics:
        if diagnostic.code not in seen:
            seen.append(diagnostic.code)
    return seen


def _compiled(document: dict[str, object]):
    return compile_standard_properties(parse_published_standard_document(document))


def test_enum_rename_keeps_mapping_and_requires_confirmation() -> None:
    standard = parse_published_standard_document(
        standard_document(enum_value="城镇燃气", confirmed_value="燃气")
    )
    result = evaluate_standard_properties(
        compile_standard_properties(standard), {"prop-major": "城镇燃气"}, {}
    )
    assert result.values["prop-code"] == "RQ"
    assert "STANDARD_MAPPING_CONFIRMATION_REQUIRED" in codes(publish_diagnostics(standard))


def test_empty_optional_mapping_source_is_empty_but_invalid_source_blocks_composition() -> None:
    compiled = compile_standard_properties(parse_published_standard_document(standard_document()))
    assert evaluate_standard_properties(compiled, {"prop-major": ""}, {}).values["prop-code"] == ""
    invalid = evaluate_standard_properties(compiled, {"prop-major": "未知"}, {})
    assert "prop-label" not in invalid.values
    assert codes(invalid.diagnostics) == [
        "STANDARD_ENUM_VALUE_INVALID",
        "STANDARD_DERIVED_UPSTREAM_INVALID",
    ]


def test_blocked_derived_properties_are_attributed() -> None:
    compiled = compile_standard_properties(parse_published_standard_document(standard_document()))
    invalid = evaluate_standard_properties(compiled, {"prop-major": "未知"}, {})
    blocked = [
        diagnostic.property_id
        for diagnostic in invalid.diagnostics
        if diagnostic.code == "STANDARD_DERIVED_UPSTREAM_INVALID"
    ]
    assert blocked == ["prop-code", "prop-label"]
    assert invalid.diagnostics[0].property_id == "prop-major"


def test_confirmed_snapshot_matches_current_enum_list_is_silent() -> None:
    standard = parse_published_standard_document(standard_document())
    assert codes(publish_diagnostics(standard)) == []


def test_two_mappings_sharing_a_source_are_rejected() -> None:
    document = standard_document()
    _properties(document).append(
        {
            "property_id": "prop-code-2",
            "name": "专业代码二",
            "previous_names": [],
            "scope": "sheet",
            "kind": "mapping",
            "source_property_id": "prop-major",
            "mapping": [{"item_id": "enum-gas", "value": "RQ2"}],
        }
    )
    standard = parse_published_standard_document(document)
    assert "STANDARD_MAPPING_SOURCE_DUPLICATE" in codes(publish_diagnostics(standard))


def test_empty_mapping_target_blocks_publish_but_repeated_targets_are_legal() -> None:
    document = standard_document()
    _properties(document)[0]["enum_items"] = [
        {"item_id": "enum-gas", "value": "燃气"},
        {"item_id": "enum-water", "value": "给水"},
    ]
    _properties(document)[1]["mapping"] = [
        {"item_id": "enum-gas", "value": "RQ"},
        {"item_id": "enum-water", "value": ""},
    ]
    empty = publish_diagnostics(parse_published_standard_document(document))
    assert "STANDARD_MAPPING_TARGET_EMPTY" in codes(empty)

    repeated = standard_document()
    _properties(repeated)[0]["enum_items"] = [
        {"item_id": "enum-gas", "value": "燃气"},
        {"item_id": "enum-water", "value": "给水"},
    ]
    _properties(repeated)[1]["mapping"] = [
        {"item_id": "enum-gas", "value": "RQ"},
        {"item_id": "enum-water", "value": "RQ"},
    ]
    _properties(repeated)[1]["confirmed_source_items"] = [
        ["enum-gas", "燃气"],
        ["enum-water", "给水"],
    ]
    assert codes(publish_diagnostics(parse_published_standard_document(repeated))) == []


def test_mapping_rows_follow_source_enum_add_delete_and_reorder() -> None:
    added = standard_document()
    _properties(added)[0]["enum_items"] = [
        {"item_id": "enum-gas", "value": "燃气"},
        {"item_id": "enum-water", "value": "给水"},
    ]
    mapping = _compiled(added).mappings[0]
    assert [(row.item_id, row.value) for row in mapping.rows] == [
        ("enum-gas", "RQ"),
        ("enum-water", ""),
    ]
    assert mapping.confirmation_required is True

    deleted = standard_document()
    _properties(deleted)[0]["enum_items"] = [
        {"item_id": "enum-gas", "value": "燃气"},
        {"item_id": "enum-water", "value": "给水"},
    ]
    _properties(deleted)[1]["mapping"] = [
        {"item_id": "enum-gas", "value": "RQ"},
        {"item_id": "enum-water", "value": "GS"},
    ]
    _properties(deleted)[1]["confirmed_source_items"] = [
        ["enum-gas", "燃气"],
        ["enum-water", "给水"],
    ]
    _properties(deleted)[0]["enum_items"] = [{"item_id": "enum-gas", "value": "燃气"}]
    _properties(deleted)[1]["mapping"] = [{"item_id": "enum-gas", "value": "RQ"}]
    _properties(deleted)[1]["confirmed_source_items"] = [["enum-gas", "燃气"]]
    assert [
        (row.item_id, row.value) for row in _compiled(deleted).mappings[0].rows
    ] == [("enum-gas", "RQ")]

    reordered = standard_document()
    _properties(reordered)[0]["enum_items"] = [
        {"item_id": "enum-water", "value": "给水"},
        {"item_id": "enum-gas", "value": "燃气"},
    ]
    _properties(reordered)[1]["mapping"] = [
        {"item_id": "enum-gas", "value": "RQ"},
        {"item_id": "enum-water", "value": "GS"},
    ]
    mapping = _compiled(reordered).mappings[0]
    assert [(row.item_id, row.value) for row in mapping.rows] == [
        ("enum-water", "GS"),
        ("enum-gas", "RQ"),
    ]
    assert mapping.confirmation_required is True


def test_composition_renders_literals_tokens_and_sheet_system_fields() -> None:
    document = standard_document()
    _properties(document).append(
        {
            "property_id": "prop-sheet-label",
            "name": "图纸图签",
            "previous_names": [],
            "scope": "sheet",
            "kind": "composition",
            "segments": [
                {"system_field": "sheet.number"},
                {"literal": " "},
                {"property_id": "prop-code"},
                {"literal": " "},
                {"system_field": "sheet.title"},
            ],
        }
    )
    compiled = _compiled(document)
    result = evaluate_standard_properties(
        compiled,
        {"prop-major": "燃气"},
        {"sheet.number": "001", "sheet.title": "平面图"},
    )
    assert result.values["prop-sheet-label"] == "001 RQ 平面图"
    assert result.diagnostics == ()


def test_missing_system_value_marks_composition_uncomputable() -> None:
    document = standard_document()
    _properties(document).append(
        {
            "property_id": "prop-sheet-label",
            "name": "图纸图签",
            "previous_names": [],
            "scope": "sheet",
            "kind": "composition",
            "segments": [{"system_field": "sheet.number"}],
        }
    )
    compiled = _compiled(document)
    result = evaluate_standard_properties(compiled, {"prop-major": "燃气"}, {})
    assert "prop-sheet-label" not in result.values
    assert codes(result.diagnostics) == ["STANDARD_SYSTEM_VALUE_MISSING"]


def test_stale_derived_values_are_never_reused_on_failure() -> None:
    compiled = compile_standard_properties(parse_published_standard_document(standard_document()))
    result = evaluate_standard_properties(
        compiled, {"prop-major": "未知", "prop-code": "旧代码", "prop-label": "旧图签"}, {}
    )
    assert "prop-code" not in result.values
    assert "prop-label" not in result.values


def test_missing_ordinary_key_is_not_treated_as_empty_value() -> None:
    """漏传普通属性键不得按空值求值：缺键即上游无法计算，且不写派生结果。"""
    compiled = compile_standard_properties(parse_published_standard_document(standard_document()))
    complete = evaluate_standard_properties(compiled, {"prop-major": "燃气"}, {})
    assert complete.values["prop-label"] == "RQ-燃气"

    incomplete = evaluate_standard_properties(compiled, {}, {})
    assert "prop-code" not in incomplete.values
    assert "prop-label" not in incomplete.values
    assert [
        diagnostic.property_id
        for diagnostic in incomplete.diagnostics
        if diagnostic.code == "STANDARD_DERIVED_UPSTREAM_INVALID"
    ] == ["prop-code", "prop-label"]


def test_missing_composition_token_key_blocks_the_composition() -> None:
    """组合令牌引用的普通属性缺键时整条组合无法计算，不按空串拼接。"""
    document = standard_document()
    _properties(document).append(
        {
            "property_id": "prop-note",
            "name": "备注",
            "previous_names": [],
            "scope": "sheetset",
            "kind": "text",
            "default_value": "",
        }
    )
    _properties(document).append(
        {
            "property_id": "prop-extra-label",
            "name": "附加图签",
            "previous_names": [],
            "scope": "sheetset",
            "kind": "composition",
            "segments": [
                {"property_id": "prop-major"},
                {"literal": "/"},
                {"property_id": "prop-note"},
            ],
        }
    )
    compiled = compile_standard_properties(parse_published_standard_document(document))
    assert evaluate_standard_properties(
        compiled, {"prop-major": "燃气", "prop-note": "A"}, {}
    ).values["prop-extra-label"] == "燃气/A"

    incomplete = evaluate_standard_properties(compiled, {"prop-major": "燃气"}, {})
    assert "prop-extra-label" not in incomplete.values
    assert [
        diagnostic.property_id
        for diagnostic in incomplete.diagnostics
        if diagnostic.code == "STANDARD_DERIVED_UPSTREAM_INVALID"
    ] == ["prop-extra-label"]


def test_unrelated_ordinary_values_pass_through_unchanged() -> None:
    compiled = compile_standard_properties(parse_published_standard_document(standard_document()))
    result = evaluate_standard_properties(
        compiled, {"prop-major": "燃气", "prop-extra": "原值"}, {}
    )
    assert result.values["prop-extra"] == "原值"
    assert result.values["prop-major"] == "燃气"
    assert result.values["prop-code"] == "RQ"
