"""图纸标准 Schema v1 领域模型与解析测试（PLAN-DM-038 Task 1）。"""

import pytest

from dst_manager.domain.standards import (
    DrawingStandard,
    StandardReference,
    StandardSchemaError,
    loads_standard_document,
    parse_published_standard_document,
    parse_standard_draft_document,
)


def valid_standard_document() -> dict[str, object]:
    """一份最小合法标准文档，供各测试裁剪复用。"""
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
                "required": True,
                "default_value": "",
                "enum_items": [{"item_id": "enum-gas", "value": "燃气"}],
                "description": "专业大类",
            },
            {
                "property_id": "prop-code",
                "name": "专业代码",
                "previous_names": ["专业编号"],
                "scope": "sheetset",
                "kind": "mapping",
                "required": False,
                "default_value": "",
                "source_property_id": "prop-major",
                "mapping": [{"item_id": "enum-gas", "value": "RQ"}],
                "confirmed_source_items": [["enum-gas", "燃气"]],
                "description": "",
            },
            {
                "property_id": "prop-part",
                "name": "分部",
                "previous_names": [],
                "scope": "sheet",
                "kind": "enum",
                "required": False,
                "default_value": "",
                "enum_items": [{"item_id": "enum-part-a", "value": "A 段"}],
                "description": "",
            },
            {
                "property_id": "prop-label",
                "name": "图签",
                "previous_names": [],
                "scope": "sheet",
                "kind": "composition",
                "required": False,
                "default_value": "",
                "segments": [
                    {"property_id": "prop-code"},
                    {"literal": "-"},
                    {"system_field": "sheet.number"},
                ],
                "description": "",
            },
        ],
        "dwg_naming": {
            "segments": [
                {"property_id": "prop-code"},
                {"literal": "-"},
                {"system_field": "subset.scope"},
                {"literal": " "},
                {"system_field": "subset.name"},
            ]
        },
        "assets": [
            {
                "asset_id": "base",
                "kind": "base-template",
                "files": [{"path": "templates/base.dwt", "role": ""}],
            },
            {
                "asset_id": "layouts",
                "kind": "layout-template",
                "files": [{"path": "templates/A2.dwg", "role": "A2"}],
            },
        ],
        "numbering": {"sequence_field": "subset.sequence", "digits": 2},
        "dependencies": [
            {
                "extension_id": "builtin.sheet-catalog",
                "capability_id": "numbering",
                "min_version": "1.2.0",
            }
        ],
    }


def _append(document: dict[str, object], prop: dict[str, object]) -> None:
    properties = document["properties"]
    assert isinstance(properties, list)
    properties.append(prop)


def _text_property(property_id: str, name: str, *, scope: str = "sheet") -> dict[str, object]:
    """一条最小普通文本属性，供裁剪用例追加。"""
    return {
        "property_id": property_id,
        "name": name,
        "previous_names": [],
        "scope": scope,
        "kind": "text",
    }


def _composition_property(
    property_id: str, name: str, segments: list[dict[str, object]], *, scope: str = "sheet"
) -> dict[str, object]:
    """一条最小组合属性，供字段范围用例追加。"""
    return {
        "property_id": property_id,
        "name": name,
        "previous_names": [],
        "scope": scope,
        "kind": "composition",
        "segments": segments,
    }


def _mapping_property(
    property_id: str, name: str, source_property_id: str, *, scope: str = "sheet"
) -> dict[str, object]:
    """一条最小映射属性（单行目标 RQ），供映射源约束用例追加。"""
    return {
        "property_id": property_id,
        "name": name,
        "previous_names": [],
        "scope": scope,
        "kind": "mapping",
        "source_property_id": source_property_id,
        "mapping": [{"item_id": "enum-gas", "value": "RQ"}],
    }


def test_schema_v1_uses_stable_property_and_enum_ids() -> None:
    standard = parse_published_standard_document(valid_standard_document())
    major = standard.property_by_id("prop-major")
    assert major.kind == "enum"
    assert [(item.item_id, item.value) for item in major.enum_items] == [("enum-gas", "燃气")]
    assert standard.dwg_naming.segments[-1].system_field == "subset.name"


def test_property_names_are_globally_unique_across_scopes_and_history() -> None:
    document = valid_standard_document()
    _append(document, _text_property("prop-sheet", " 专业 "))
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_NAME_DUPLICATE"):
        parse_published_standard_document(document)


def test_parse_standard_round_trip_is_stable() -> None:
    standard = parse_published_standard_document(valid_standard_document())
    assert isinstance(standard, DrawingStandard)
    assert standard.standard_id == "szmedi.gas"
    assert standard.version == "2.1.0"
    assert standard.supported_cad_versions == ("2016", "2020")
    assert [prop.property_id for prop in standard.properties] == [
        "prop-major",
        "prop-code",
        "prop-part",
        "prop-label",
    ]
    assert standard.property_by_id("prop-code").previous_names == ("专业编号",)
    assert standard.property_by_id("prop-code").mapping[0].value == "RQ"
    assert standard.numbering.sequence_field == "subset.sequence"
    assert standard.numbering.digits == 2
    assert standard.dependencies[0].extension_id == "builtin.sheet-catalog"
    assert standard.assets[1].kind == "layout-template"
    # 再次解析同一文档得到等价结果（冻结对象可比较）。
    assert parse_published_standard_document(valid_standard_document()) == standard


def test_property_lookup_by_scope_and_normalized_name() -> None:
    standard = parse_published_standard_document(valid_standard_document())
    assert standard.property_by_name("sheetset", "  专业 ") is not None
    assert standard.property_by_name("sheet", "专业") is None
    assert standard.find_property("prop-missing") is None
    with pytest.raises(KeyError):
        standard.property_by_id("prop-missing")


def test_property_names_conflict_with_previous_names() -> None:
    document = valid_standard_document()
    _append(document, _text_property("prop-renamed", "专业编号"))
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_NAME_DUPLICATE"):
        parse_published_standard_document(document)


def test_property_name_conflict_ignores_case() -> None:
    document = valid_standard_document()
    _append(document, _text_property("prop-upper", "PROP-X"))
    _append(document, _text_property("prop-lower", "prop-x", scope="sheetset"))
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_NAME_DUPLICATE"):
        parse_published_standard_document(document)


@pytest.mark.parametrize(
    "reserved",
    ["sheet.number", "subset.sequence", "DSTManager.Standard", "DSTManager.Anything"],
)
def test_published_parse_rejects_reserved_property_names(reserved: str) -> None:
    document = valid_standard_document()
    _append(document, _text_property("prop-reserved", reserved, scope="sheetset"))
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_NAME_RESERVED"):
        parse_published_standard_document(document)


def test_references_to_enumerates_mapping_composition_and_naming_tokens() -> None:
    standard = parse_published_standard_document(valid_standard_document())
    assert standard.references_to("prop-major") == (
        StandardReference(kind="mapping", owner_id="prop-code"),
    )
    assert standard.references_to("prop-code") == (
        StandardReference(kind="composition", owner_id="prop-label", segment_index=0),
        StandardReference(kind="dwg-naming", owner_id="", segment_index=0),
    )
    assert standard.references_to("prop-label") == ()


def test_composition_cannot_reference_composition() -> None:
    document = valid_standard_document()
    _append(
        document,
        _composition_property("prop-stacked", "叠加图签", [{"property_id": "prop-label"}]),
    )
    with pytest.raises(StandardSchemaError, match="STANDARD_SEGMENT_SCOPE_INVALID"):
        parse_published_standard_document(document)


def test_sheetset_composition_rejects_sheet_property_and_sheet_system_field() -> None:
    document = valid_standard_document()
    _append(
        document,
        _composition_property(
            "prop-set-compose", "图纸集图签", [{"system_field": "sheet.number"}], scope="sheetset"
        ),
    )
    with pytest.raises(StandardSchemaError, match="STANDARD_SEGMENT_SCOPE_INVALID"):
        parse_published_standard_document(document)

    other = valid_standard_document()
    _append(
        other,
        _composition_property(
            "prop-set-compose", "图纸集图签", [{"property_id": "prop-label"}], scope="sheetset"
        ),
    )
    with pytest.raises(StandardSchemaError, match="STANDARD_SEGMENT_SCOPE_INVALID"):
        parse_published_standard_document(other)


def test_published_parse_rejects_mapping_without_source() -> None:
    """映射属性必须有源：草稿可保存，发布必须阻断（不能静默变成一个永不求值的属性）。"""
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    del properties[1]["source_property_id"]
    with pytest.raises(StandardSchemaError, match="STANDARD_MAPPING_SOURCE_INVALID"):
        parse_published_standard_document(document)
    # 草稿门禁仍然放行：用户可以保存还没选源的映射属性
    assert parse_standard_draft_document(document).property_by_id("prop-code").source_property_id is None


def test_published_parse_rejects_whitespace_only_property_name() -> None:
    """只有空白字符的属性名按空名处理：否则两个 `" "` 属性可以同时发布。"""
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    properties[0]["name"] = "   "
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_NAME_INVALID"):
        parse_published_standard_document(document)


def test_mapping_source_must_be_ordinary_enum() -> None:
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    properties[1]["source_property_id"] = "prop-label"
    with pytest.raises(StandardSchemaError, match="STANDARD_MAPPING_SOURCE_INVALID"):
        parse_published_standard_document(document)


def test_sheetset_mapping_rejects_sheet_enum_source() -> None:
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    properties[1]["source_property_id"] = "prop-part"
    with pytest.raises(StandardSchemaError, match="STANDARD_MAPPING_SCOPE_INVALID"):
        parse_published_standard_document(document)


def test_sheet_mapping_may_use_sheetset_enum_source() -> None:
    document = valid_standard_document()
    _append(document, _mapping_property("prop-part-code", "分部代码", "prop-major"))
    standard = parse_published_standard_document(document)
    assert standard.property_by_id("prop-part-code").source_property_id == "prop-major"


def test_dwg_naming_rejects_sheet_property_and_sheet_system_field() -> None:
    document = valid_standard_document()
    document["dwg_naming"] = {"segments": [{"property_id": "prop-label"}]}
    with pytest.raises(StandardSchemaError, match="STANDARD_NAMING_FIELD_SCOPE_INVALID"):
        parse_published_standard_document(document)

    other = valid_standard_document()
    other["dwg_naming"] = {"segments": [{"system_field": "sheet.title"}]}
    with pytest.raises(StandardSchemaError, match="STANDARD_NAMING_FIELD_SCOPE_INVALID"):
        parse_published_standard_document(other)


def test_dwg_naming_accepts_all_sheetset_property_kinds() -> None:
    document = valid_standard_document()
    _append(
        document,
        _composition_property(
            "prop-set-compose", "图纸集图签", [{"property_id": "prop-code"}], scope="sheetset"
        ),
    )
    document["dwg_naming"] = {
        "segments": [
            {"property_id": "prop-set-compose"},
            {"system_field": "subset.sequence", "format": "02"},
        ]
    }
    standard = parse_published_standard_document(document)
    assert standard.dwg_naming.segments[1].format == "02"


def test_published_parse_rejects_unregistered_pad_format() -> None:
    document = valid_standard_document()
    document["dwg_naming"] = {
        "segments": [{"system_field": "subset.sequence", "format": "99"}]
    }
    with pytest.raises(StandardSchemaError, match="STANDARD_SEGMENT_FORMAT_INVALID"):
        parse_published_standard_document(document)


def test_published_parse_rejects_pad_format_on_non_sequence_token() -> None:
    document = valid_standard_document()
    document["dwg_naming"] = {"segments": [{"property_id": "prop-code", "format": "02"}]}
    with pytest.raises(StandardSchemaError, match="STANDARD_SEGMENT_FORMAT_INVALID"):
        parse_published_standard_document(document)


def test_published_parse_rejects_enum_default_outside_enum_items() -> None:
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    properties[0]["default_value"] = "给水"
    with pytest.raises(StandardSchemaError, match="STANDARD_ENUM_DEFAULT_INVALID"):
        parse_published_standard_document(document)


def test_published_parse_rejects_duplicate_property_ids() -> None:
    document = valid_standard_document()
    _append(document, _text_property("prop-major", "另一个专业"))
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_ID_DUPLICATE"):
        parse_published_standard_document(document)


def test_published_parse_rejects_duplicate_enum_item_ids() -> None:
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    properties[0]["enum_items"] = [
        {"item_id": "enum-gas", "value": "燃气"},
        {"item_id": "enum-gas", "value": "给水"},
    ]
    with pytest.raises(StandardSchemaError, match="STANDARD_ENUM_ITEM_ID_DUPLICATE"):
        parse_published_standard_document(document)


def test_draft_parse_tolerates_incomplete_names_targets_and_segments() -> None:
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    properties[0]["name"] = ""
    properties[1]["mapping"] = [{"item_id": "enum-gas", "value": ""}]
    document["dwg_naming"] = {"segments": []}
    draft = parse_standard_draft_document(document)
    assert draft.property_by_id("prop-major").name == ""
    assert draft.property_by_id("prop-code").mapping[0].value == ""
    assert draft.dwg_naming.segments == ()


def test_draft_parse_still_requires_stable_ids_and_references() -> None:
    document = valid_standard_document()
    document["dwg_naming"] = {"segments": [{"property_id": "prop-missing"}]}
    with pytest.raises(StandardSchemaError, match="STANDARD_SEGMENT_REFERENCE_UNKNOWN"):
        parse_standard_draft_document(document)

    other = valid_standard_document()
    properties = other["properties"]
    assert isinstance(properties, list)
    properties[1]["source_property_id"] = "prop-missing"
    with pytest.raises(StandardSchemaError, match="STANDARD_MAPPING_SOURCE_INVALID"):
        parse_standard_draft_document(other)


def test_published_parse_rejects_empty_property_name_and_missing_naming() -> None:
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    properties[0]["name"] = ""
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_NAME_INVALID"):
        parse_published_standard_document(document)

    other = valid_standard_document()
    del other["dwg_naming"]
    with pytest.raises(StandardSchemaError, match="STANDARD_DWG_NAMING_MISSING"):
        parse_published_standard_document(other)


def test_parse_standard_rejects_unknown_scope_and_kind() -> None:
    document = valid_standard_document()
    properties = document["properties"]
    assert isinstance(properties, list)
    properties[0]["scope"] = "project"
    with pytest.raises(StandardSchemaError, match="STANDARD_SCOPE_INVALID"):
        parse_standard_draft_document(document)

    other = valid_standard_document()
    properties = other["properties"]
    assert isinstance(properties, list)
    properties[0]["kind"] = "formula"
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_KIND_INVALID"):
        parse_standard_draft_document(other)


def test_parse_standard_rejects_segment_without_content() -> None:
    document = valid_standard_document()
    document["dwg_naming"] = {"segments": [{"format": "02"}]}
    with pytest.raises(StandardSchemaError, match="STANDARD_SEGMENT_INVALID"):
        parse_standard_draft_document(document)


def test_parse_standard_rejects_unknown_system_field() -> None:
    document = valid_standard_document()
    document["dwg_naming"] = {"segments": [{"system_field": "subset.unknown"}]}
    with pytest.raises(StandardSchemaError, match="STANDARD_SEGMENT_REFERENCE_UNKNOWN"):
        parse_standard_draft_document(document)


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"standard_id": "a.b", "version": "1.0.0"}, "STANDARD_SCHEMA_VERSION_UNSUPPORTED"),
        (
            {"schema_version": 2, "standard_id": "a.b", "version": "1.0.0"},
            "STANDARD_SCHEMA_VERSION_UNSUPPORTED",
        ),
        ({"schema_version": 1, "version": "1.0.0"}, "STANDARD_ID_INVALID"),
        (
            {"schema_version": 1, "standard_id": "a.b", "version": "1.0"},
            "STANDARD_VERSION_INVALID",
        ),
        ({"schema_version": 1, "standard_id": "a.b"}, "STANDARD_VERSION_INVALID"),
        (
            {"schema_version": 1, "standard_id": "a.b", "version": "1.0.0"},
            "STANDARD_NAME_INVALID",
        ),
    ],
)
def test_parse_standard_rejects_invalid_top_level(
    document: dict[str, object], code: str
) -> None:
    with pytest.raises(StandardSchemaError, match=code):
        parse_standard_draft_document(document)


def test_parse_standard_rejects_duplicate_asset_ids() -> None:
    document = valid_standard_document()
    document["assets"] = [
        {"asset_id": "base", "kind": "base-template"},
        {"asset_id": "base", "kind": "layout-template"},
    ]
    with pytest.raises(StandardSchemaError, match="STANDARD_ASSET_DUPLICATE"):
        parse_standard_draft_document(document)


def test_loads_standard_document_rejects_duplicate_json_keys() -> None:
    text = (
        '{"schema_version": 1, "standard_id": "a.b", "standard_id": "a.c", '
        '"version": "1.0.0", "name": "n", "supported_cad_versions": ["2016"], '
        '"dwg_naming": {"segments": [{"literal": "x"}]}, '
        '"numbering": {"sequence_field": "subset.sequence", "digits": 2}}'
    )
    with pytest.raises(StandardSchemaError, match="STANDARD_FIELD_DUPLICATE"):
        loads_standard_document(text)


def test_loads_standard_document_rejects_broken_json() -> None:
    with pytest.raises(StandardSchemaError, match="STANDARD_JSON_INVALID"):
        loads_standard_document("{not json")
