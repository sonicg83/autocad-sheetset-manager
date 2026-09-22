"""图纸标准封闭规则编译与求值测试（PLAN-DM-035 Task 2）。"""

import pytest

from dst_manager.domain.standard_rules import (
    StandardRuleError,
    compile_standard_rules,
    evaluate_fields,
)
from dst_manager.domain.standards import parse_standard_document


def standard_with_gas_mapping() -> object:
    """专业名称 -> 专业代码一对一映射 + DWG 命名组合的最小标准。"""
    return parse_standard_document(
        {
            "schema_version": 1,
            "standard_id": "szmedi.gas",
            "version": "2.1.0",
            "name": "市政燃气施工图",
            "supported_cad_versions": ["2016", "2020"],
            "properties": [
                {"name": "专业名称", "scope": "sheetset", "required": True},
                {"name": "专业代码", "scope": "sheetset", "enum_values": ["RQ", "JZ"]},
            ],
            "rules": [
                {
                    "rule_id": "map-specialty",
                    "kind": "mapping",
                    "target": "sheetset.专业代码",
                    "source": "sheetset.专业名称",
                    "table": [["燃气", "RQ"], ["建筑", "JZ"]],
                },
                {
                    "rule_id": "compose-dwg-name",
                    "kind": "compose",
                    "target": "derived.dwg_name",
                    "segments": [
                        {"field": "sheetset.专业代码"},
                        {"field": "subset.sequence", "format": "02"},
                        {"literal": " 平面图01-05"},
                    ],
                },
            ],
            "assets": [],
            "numbering": {"sequence_field": "subset.sequence", "digits": 2},
        }
    )


def standard_with_cycle(*chain: str) -> object:
    """构造 chain 上相邻字段互为映射源/目标的循环标准。"""
    fields = [f"sheetset.{name}" for name in chain]
    rules = [
        {
            "rule_id": f"map-{index}",
            "kind": "mapping",
            "target": fields[index + 1],
            "source": fields[index],
            "table": [["x", "y"]],
        }
        for index in range(len(fields) - 1)
    ]
    return parse_standard_document(
        {
            "schema_version": 1,
            "standard_id": "cycle.test",
            "version": "1.0.0",
            "name": "循环测试",
            "supported_cad_versions": ["2020"],
            "properties": [{"name": field.split(".", 1)[1], "scope": "sheetset"} for field in fields],
            "rules": rules,
            "assets": [],
            "numbering": {"sequence_field": "subset.sequence", "digits": 2},
        }
    )


def test_mapping_then_compose_uses_derived_value() -> None:
    compiled = compile_standard_rules(standard_with_gas_mapping())
    result = evaluate_fields(compiled, {"sheetset.专业名称": "燃气"}, {"subset.sequence": 3})
    assert result.values["sheetset.专业代码"] == "RQ"
    assert result.values["derived.dwg_name"] == "RQ03 平面图01-05"


def test_compile_rejects_indirect_cycle() -> None:
    with pytest.raises(StandardRuleError, match="STANDARD_RULE_CYCLE"):
        compile_standard_rules(standard_with_cycle("a", "b", "a"))


def test_compile_rejects_unknown_field_reference() -> None:
    standard = parse_standard_document(
        {
            "schema_version": 1,
            "standard_id": "unknown.ref",
            "version": "1.0.0",
            "name": "未知引用",
            "supported_cad_versions": ["2020"],
            "properties": [{"name": "备注", "scope": "sheetset"}],
            "rules": [
                {
                    "rule_id": "r1",
                    "kind": "mapping",
                    "target": "sheetset.专业代码",
                    "source": "sheetset.不存在的字段",
                    "table": [["x", "y"]],
                }
            ],
            "assets": [],
            "numbering": {"sequence_field": "subset.sequence", "digits": 2},
        }
    )
    with pytest.raises(StandardRuleError, match="STANDARD_RULE_FIELD_UNKNOWN"):
        compile_standard_rules(standard)


def test_compile_rejects_invalid_format_code() -> None:
    standard = parse_standard_document(
        {
            "schema_version": 1,
            "standard_id": "bad.format",
            "version": "1.0.0",
            "name": "非法格式码",
            "supported_cad_versions": ["2020"],
            "properties": [{"name": "序号", "scope": "sheetset"}],
            "rules": [
                {
                    "rule_id": "r1",
                    "kind": "compose",
                    "target": "derived.name",
                    "segments": [{"field": "sheetset.序号", "format": "0N"}],
                }
            ],
            "assets": [],
            "numbering": {"sequence_field": "subset.sequence", "digits": 2},
        }
    )
    with pytest.raises(StandardRuleError, match="STANDARD_RULE_FORMAT_INVALID"):
        compile_standard_rules(standard)


def test_compile_rejects_duplicate_targets() -> None:
    standard = parse_standard_document(
        {
            "schema_version": 1,
            "standard_id": "dup.target",
            "version": "1.0.0",
            "name": "重复目标",
            "supported_cad_versions": ["2020"],
            "properties": [{"name": "专业名称", "scope": "sheetset"}],
            "rules": [
                {
                    "rule_id": "r1",
                    "kind": "mapping",
                    "target": "sheetset.专业代码",
                    "source": "sheetset.专业名称",
                    "table": [["x", "y"]],
                },
                {
                    "rule_id": "r2",
                    "kind": "mapping",
                    "target": "sheetset.专业代码",
                    "source": "sheetset.专业名称",
                    "table": [["x", "z"]],
                },
            ],
            "assets": [],
            "numbering": {"sequence_field": "subset.sequence", "digits": 2},
        }
    )
    with pytest.raises(StandardRuleError, match="STANDARD_RULE_TARGET_DUPLICATE"):
        compile_standard_rules(standard)


def test_evaluate_reports_uncovered_mapping_source() -> None:
    compiled = compile_standard_rules(standard_with_gas_mapping())
    result = evaluate_fields(compiled, {"sheetset.专业名称": "给排水"}, {"subset.sequence": 3})
    assert "sheetset.专业代码" not in result.values
    assert result.diagnostics[0].code == "STANDARD_MAPPING_SOURCE_UNCOVERED"
    assert result.diagnostics[0].field == "sheetset.专业名称"


def test_evaluate_reports_missing_compose_source_without_deriving() -> None:
    compiled = compile_standard_rules(standard_with_gas_mapping())
    result = evaluate_fields(compiled, {"sheetset.专业名称": ""}, {"subset.sequence": 3})
    assert "derived.dwg_name" not in result.values
    codes = [diagnostic.code for diagnostic in result.diagnostics]
    assert "STANDARD_RULE_SOURCE_MISSING" in codes


def test_evaluate_reports_invalid_format_value() -> None:
    standard = parse_standard_document(
        {
            "schema_version": 1,
            "standard_id": "bad.value",
            "version": "1.0.0",
            "name": "非数字序号",
            "supported_cad_versions": ["2020"],
            "properties": [{"name": "序号", "scope": "sheetset"}],
            "rules": [
                {
                    "rule_id": "r1",
                    "kind": "compose",
                    "target": "derived.name",
                    "segments": [{"field": "sheetset.序号", "format": "02"}],
                }
            ],
            "assets": [],
            "numbering": {"sequence_field": "subset.sequence", "digits": 2},
        }
    )
    compiled = compile_standard_rules(standard)
    result = evaluate_fields(compiled, {"sheetset.序号": "三"}, {})
    assert "derived.name" not in result.values
    assert result.diagnostics[0].code == "STANDARD_RULE_FORMAT_INVALID"


def test_evaluate_required_and_enum_rules() -> None:
    standard = parse_standard_document(
        {
            "schema_version": 1,
            "standard_id": "constraints",
            "version": "1.0.0",
            "name": "约束",
            "supported_cad_versions": ["2020"],
            "properties": [
                {"name": "专业名称", "scope": "sheetset", "required": True},
                {"name": "图幅", "scope": "sheetset"},
            ],
            "rules": [
                {
                    "rule_id": "r1",
                    "kind": "enum",
                    "target": "sheetset.图幅",
                    "allowed": ["A2", "A3"],
                },
                {
                    "rule_id": "r2",
                    "kind": "fixed",
                    "target": "sheetset.固定前缀",
                    "value": "SZ",
                },
            ],
            "assets": [],
            "numbering": {"sequence_field": "subset.sequence", "digits": 2},
        }
    )
    compiled = compile_standard_rules(standard)
    result = evaluate_fields(compiled, {"sheetset.图幅": "A1"}, {})
    codes = [diagnostic.code for diagnostic in result.diagnostics]
    assert "STANDARD_RULE_REQUIRED_MISSING" in codes
    assert "STANDARD_RULE_ENUM_VIOLATION" in codes
    assert result.values["sheetset.固定前缀"] == "SZ"
