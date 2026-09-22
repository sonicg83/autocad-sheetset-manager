"""图纸标准领域模型与 Schema 解析测试（PLAN-DM-035 Task 1）。"""

import pytest

from dst_manager.domain.standards import (
    DrawingStandard,
    StandardSchemaError,
    loads_standard_document,
    parse_standard_document,
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
            {"name": "专业名称", "scope": "sheetset", "required": True},
            {
                "name": "专业代码",
                "scope": "sheetset",
                "enum_values": ["RQ", "JZ", "GPS"],
            },
        ],
        "rules": [
            {
                "rule_id": "derive-dwg-name",
                "kind": "compose",
                "target": "derived.dwg_name",
                "segments": [
                    {"field": "sheetset.专业代码"},
                    {"field": "subset.sequence", "format": "02"},
                    {"literal": " 平面图"},
                ],
            },
            {
                "rule_id": "map-specialty-code",
                "kind": "mapping",
                "target": "sheetset.专业代码",
                "source": "sheetset.专业名称",
            },
        ],
        "assets": [
            {
                "asset_id": "base",
                "kind": "base-template",
                "files": [{"path": "templates/base.dwt", "role": ""}],
            },
            {
                "asset_id": "layouts",
                "kind": "layout-template",
                "files": [
                    {"path": "templates/A2.dwg", "role": "A2"},
                    {"path": "templates/A3.dwg", "role": "A3"},
                ],
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


def test_parse_standard_requires_stable_identity() -> None:
    with pytest.raises(StandardSchemaError, match="STANDARD_ID_INVALID"):
        parse_standard_document({"schema_version": 1, "standard_id": "", "version": "1.0.0"})


def test_parse_standard_round_trip_is_stable() -> None:
    standard = parse_standard_document(valid_standard_document())
    assert isinstance(standard, DrawingStandard)
    assert standard.standard_id == "szmedi.gas"
    assert standard.version == "2.1.0"
    assert standard.supported_cad_versions == ("2016", "2020")
    assert [prop.name for prop in standard.properties] == ["专业名称", "专业代码"]
    assert [rule.rule_id for rule in standard.rules] == [
        "derive-dwg-name",
        "map-specialty-code",
    ]
    assert [asset.asset_id for asset in standard.assets] == ["base", "layouts"]
    assert standard.numbering.sequence_field == "subset.sequence"
    assert standard.numbering.digits == 2
    assert standard.dependencies[0].extension_id == "builtin.sheet-catalog"
    # 再次解析同一文档得到等价结果（冻结对象可比较）。
    assert parse_standard_document(valid_standard_document()) == standard


def test_parse_standard_rejects_uppercase_identity() -> None:
    document = valid_standard_document()
    document["standard_id"] = "SzMedi.Gas"
    with pytest.raises(StandardSchemaError, match="STANDARD_ID_INVALID"):
        parse_standard_document(document)


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"standard_id": "a.b", "version": "1.0.0"}, "STANDARD_SCHEMA_VERSION_UNSUPPORTED"),
        ({"schema_version": 2, "standard_id": "a.b", "version": "1.0.0"}, "STANDARD_SCHEMA_VERSION_UNSUPPORTED"),
        ({"schema_version": 1, "version": "1.0.0"}, "STANDARD_ID_INVALID"),
        ({"schema_version": 1, "standard_id": "a.b", "version": "1.0"}, "STANDARD_VERSION_INVALID"),
        ({"schema_version": 1, "standard_id": "a.b"}, "STANDARD_VERSION_INVALID"),
        ({"schema_version": 1, "standard_id": "a.b", "version": "1.0.0"}, "STANDARD_NAME_INVALID"),
    ],
)
def test_parse_standard_rejects_invalid_top_level(document: dict[str, object], code: str) -> None:
    with pytest.raises(StandardSchemaError, match=code):
        parse_standard_document(document)


def test_parse_standard_rejects_missing_name() -> None:
    document = valid_standard_document()
    document["name"] = ""
    with pytest.raises(StandardSchemaError, match="STANDARD_NAME_INVALID"):
        parse_standard_document(document)


def test_parse_standard_rejects_unknown_scope() -> None:
    document = valid_standard_document()
    document["properties"] = [{"name": "专业名称", "scope": "project"}]
    with pytest.raises(StandardSchemaError, match="STANDARD_SCOPE_INVALID"):
        parse_standard_document(document)


def test_parse_standard_rejects_duplicate_asset_ids() -> None:
    document = valid_standard_document()
    document["assets"] = [
        {"asset_id": "base", "kind": "base-template"},
        {"asset_id": "base", "kind": "layout-template"},
    ]
    with pytest.raises(StandardSchemaError, match="STANDARD_ASSET_DUPLICATE"):
        parse_standard_document(document)


def test_parse_standard_rejects_unknown_rule_kind() -> None:
    document = valid_standard_document()
    document["rules"] = [
        {"rule_id": "r1", "kind": "formula", "target": "sheetset.专业代码"}
    ]
    with pytest.raises(StandardSchemaError, match="STANDARD_RULE_KIND_INVALID"):
        parse_standard_document(document)


def test_parse_standard_rejects_duplicate_rule_ids() -> None:
    document = valid_standard_document()
    document["rules"] = [
        {"rule_id": "r1", "kind": "fixed", "target": "sheetset.专业代码", "value": "RQ"},
        {"rule_id": "r1", "kind": "fixed", "target": "sheetset.备注", "value": ""},
    ]
    with pytest.raises(StandardSchemaError, match="STANDARD_RULE_DUPLICATE"):
        parse_standard_document(document)


def test_parse_standard_rejects_invalid_field_reference() -> None:
    document = valid_standard_document()
    document["rules"] = [
        {"rule_id": "r1", "kind": "required", "target": "专业代码"}
    ]
    with pytest.raises(StandardSchemaError, match="STANDARD_FIELD_INVALID"):
        parse_standard_document(document)


def test_loads_standard_document_rejects_duplicate_json_keys() -> None:
    text = '{"schema_version": 1, "standard_id": "a.b", "standard_id": "a.c", "version": "1.0.0", "name": "n", "supported_cad_versions": ["2016"], "numbering": {"sequence_field": "subset.sequence", "digits": 2}}'
    with pytest.raises(StandardSchemaError, match="STANDARD_FIELD_DUPLICATE"):
        loads_standard_document(text)


def test_loads_standard_document_rejects_broken_json() -> None:
    with pytest.raises(StandardSchemaError, match="STANDARD_JSON_INVALID"):
        loads_standard_document("{not json")
