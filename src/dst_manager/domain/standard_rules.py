"""图纸标准封闭规则编译与求值（PLAN-DM-035 Task 2）。

规则是标准文档中的纯数据；本模块把标准编译为拓扑有序的规则计划，
再在宿主提供的字段值与上下文上求值。全程不执行 ``eval``、模板脚本
或动态导入——片段只能是字段令牌、固定文本或受控序号，格式码只允许
宿主登记的数字补零形式。
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from dst_manager.domain.standards import (
    DrawingStandard,
    StandardRule,
    StandardSegment,
)

__all__ = ["CompiledStandard", "EvaluationResult", "StandardRuleError", "compile_standard_rules", "evaluate_fields"]

# 宿主登记的数字补零格式：如 "02" 表示补零到两位宽。
PAD_FORMAT_PATTERN = re.compile(r"^\d{1,2}$")
MAX_PAD_WIDTH = 12


class StandardRuleError(Exception):
    """规则编译失败；消息以稳定错误码开头，如 ``STANDARD_RULE_CYCLE``。"""


@dataclass(frozen=True, slots=True)
class RuleDiagnostic:
    """一次求值诊断；``field``/``rule_id`` 定位到具体规则与字段。"""

    code: str
    message: str
    field: str | None = None
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledStandard:
    """拓扑有序的规则计划；``order`` 保证依赖先于依赖者。"""

    standard: DrawingStandard
    order: tuple[StandardRule, ...]
    known_fields: frozenset[str] = field(default_factory=frozenset)
    tables: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """求值结果：``values`` 为派生字段，``diagnostics`` 记录确定性失败。"""

    values: dict[str, str]
    diagnostics: tuple[RuleDiagnostic, ...] = ()


def _error(code: str, detail: str) -> StandardRuleError:
    return StandardRuleError(f"{code}: {detail}")


def _rule_sources(rule: StandardRule) -> tuple[str, ...]:
    if rule.kind == "mapping":
        return (rule.source,) if rule.source else ()
    if rule.kind in ("compose", "naming"):
        return tuple(
            segment.field for segment in rule.segments if segment.field is not None
        )
    return ()


def _compile_error(code: str, rule_id: str, detail: str) -> StandardRuleError:
    return _error(code, f"规则 {rule_id!r}: {detail}")


def compile_standard_rules(standard: DrawingStandard) -> CompiledStandard:
    """把标准规则编译为拓扑有序计划。

    未知引用、重复目标、非法格式码与间接循环在编译期确定失败，
    抛出以稳定错误码开头的 :class:`StandardRuleError`。
    """
    known_fields = {
        f"{prop.scope}.{prop.name}" for prop in standard.properties
    } | {standard.numbering.sequence_field}
    targets: dict[str, str] = {}
    for rule in standard.rules:
        if rule.target in targets:
            raise _compile_error(
                "STANDARD_RULE_TARGET_DUPLICATE", rule.rule_id,
                f"目标字段 {rule.target!r} 已被规则 {targets[rule.target]!r} 占用",
            )
        targets[rule.target] = rule.rule_id
    known_fields |= set(targets)
    for rule in standard.rules:
        _validate_rule(rule, known_fields)
    order = _topological_order(standard.rules)
    tables = {
        rule.target: dict(rule.table) for rule in standard.rules if rule.kind == "mapping"
    }
    return CompiledStandard(
        standard=standard,
        order=tuple(order),
        known_fields=frozenset(known_fields),
        tables=tables,
    )


def _validate_rule(rule: StandardRule, known_fields: set[str]) -> None:
    for segment in rule.segments:
        if segment.format is not None:
            if not PAD_FORMAT_PATTERN.fullmatch(segment.format) or (
                int(segment.format) < 1 or int(segment.format) > MAX_PAD_WIDTH
            ):
                raise _compile_error(
                    "STANDARD_RULE_FORMAT_INVALID", rule.rule_id,
                    f"格式码 {segment.format!r} 不是登记的数字补零格式",
                )
            if segment.literal is not None:
                raise _compile_error(
                    "STANDARD_RULE_FORMAT_INVALID", rule.rule_id,
                    "固定文本片段不允许格式码",
                )
    for source in _rule_sources(rule):
        if source not in known_fields:
            raise _compile_error(
                "STANDARD_RULE_FIELD_UNKNOWN", rule.rule_id, f"未知引用 {source!r}"
            )


def _topological_order(rules: list[StandardRule]) -> list[StandardRule]:
    by_id = {rule.rule_id: rule for rule in rules}
    produced = {rule.target: rule.rule_id for rule in rules}
    dependents: dict[str, list[str]] = {rule.rule_id: [] for rule in rules}
    indegree: dict[str, int] = {rule.rule_id: 0 for rule in rules}
    for rule in rules:
        for source in _rule_sources(rule):
            producer = produced.get(source)
            if producer is not None and producer != rule.rule_id:
                dependents[producer].append(rule.rule_id)
                indegree[rule.rule_id] += 1
    ready = [rule.rule_id for rule in rules if indegree[rule.rule_id] == 0]
    ordered: list[StandardRule] = []
    while ready:
        rule_id = ready.pop(0)
        ordered.append(by_id[rule_id])
        for dependent in dependents[rule_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    if len(ordered) != len(rules):
        raise _error("STANDARD_RULE_CYCLE", "规则依赖存在循环引用")
    return ordered


def evaluate_fields(
    compiled: CompiledStandard,
    values: Mapping[str, str],
    context: Mapping[str, str] | None = None,
) -> EvaluationResult:
    """按拓扑顺序求值派生字段。

    ``values`` 是宿主提供的已填字段，优先于 ``context``；
    缺失可选值、映射未覆盖与非法格式值返回稳定诊断，不中断其余规则。
    """
    merged: dict[str, str] = dict(context or {})
    merged.update(values)
    results: dict[str, str] = {}
    diagnostics: list[RuleDiagnostic] = []

    def lookup(field_name: str) -> str | None:
        if field_name in results:
            return results[field_name]
        return merged.get(field_name)

    explicit_required = {
        rule.target for rule in compiled.order if rule.kind == "required"
    }
    for prop in compiled.standard.properties:
        if not prop.required:
            continue
        field_name = f"{prop.scope}.{prop.name}"
        if field_name in explicit_required:
            continue  # 已由显式 required 规则覆盖，避免重复诊断
        value = lookup(field_name)
        if value is None or value == "":
            diagnostics.append(RuleDiagnostic(
                code="STANDARD_RULE_REQUIRED_MISSING",
                field=field_name,
                message=f"必填字段 {field_name} 未提供值",
            ))

    for rule in compiled.order:
        if rule.kind == "mapping":
            _evaluate_mapping(rule, lookup, results, diagnostics)
        elif rule.kind in ("compose", "naming"):
            _evaluate_compose(rule, lookup, results, diagnostics)
        elif rule.kind == "fixed":
            results[rule.target] = rule.value or ""
        elif rule.kind == "required":
            value = lookup(rule.target)
            if value is None or value == "":
                diagnostics.append(RuleDiagnostic(
                    code="STANDARD_RULE_REQUIRED_MISSING",
                    field=rule.target,
                    rule_id=rule.rule_id,
                    message=f"必填字段 {rule.target} 未提供值",
                ))
        elif rule.kind == "enum":
            value = lookup(rule.target)
            if value is not None and value not in rule.allowed:
                diagnostics.append(RuleDiagnostic(
                    code="STANDARD_RULE_ENUM_VIOLATION",
                    field=rule.target,
                    rule_id=rule.rule_id,
                    message=f"值 {value!r} 不在允许集合内",
                ))
    return EvaluationResult(values=results, diagnostics=tuple(diagnostics))


def _evaluate_mapping(
    rule: StandardRule,
    lookup,
    results: dict[str, str],
    diagnostics: list[RuleDiagnostic],
) -> None:
    source_value = lookup(rule.source or "")
    if source_value is None or source_value == "":
        diagnostics.append(RuleDiagnostic(
            code="STANDARD_RULE_SOURCE_MISSING",
            field=rule.source,
            rule_id=rule.rule_id,
            message=f"映射源字段 {rule.source} 缺少值",
        ))
        return
    table = dict(rule.table)
    if source_value not in table:
        diagnostics.append(RuleDiagnostic(
            code="STANDARD_MAPPING_SOURCE_UNCOVERED",
            field=rule.source,
            rule_id=rule.rule_id,
            message=f"源值 {source_value!r} 未被映射表覆盖",
        ))
        return
    results[rule.target] = table[source_value]


def _evaluate_compose(
    rule: StandardRule,
    lookup,
    results: dict[str, str],
    diagnostics: list[RuleDiagnostic],
) -> None:
    parts: list[str] = []
    for segment in rule.segments:
        rendered = _render_segment(rule, segment, lookup, diagnostics)
        if rendered is None:
            return  # 缺失必需来源：整条组合确定性失败
        parts.append(rendered)
    results[rule.target] = "".join(parts)


def _render_segment(
    rule: StandardRule,
    segment: StandardSegment,
    lookup,
    diagnostics: list[RuleDiagnostic],
) -> str | None:
    if segment.literal is not None:
        return segment.literal
    assert segment.field is not None
    value = lookup(segment.field)
    if value is None or value == "":
        diagnostics.append(RuleDiagnostic(
            code="STANDARD_RULE_SOURCE_MISSING",
            field=segment.field,
            rule_id=rule.rule_id,
            message=f"组合片段字段 {segment.field} 缺少值",
        ))
        return None
    if segment.format is None:
        return value
    try:
        number = int(value)
    except ValueError:
        diagnostics.append(RuleDiagnostic(
            code="STANDARD_RULE_FORMAT_INVALID",
            field=segment.field,
            rule_id=rule.rule_id,
            message=f"字段 {segment.field} 的值 {value!r} 不是整数，无法补零",
        ))
        return None
    return str(number).zfill(int(segment.format))
