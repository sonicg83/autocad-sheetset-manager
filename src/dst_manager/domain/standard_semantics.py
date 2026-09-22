"""图纸标准发布语义门禁（PLAN-DM-038 Task 1）。

结构解析（:mod:`dst_manager.domain.standard_schema`）之后，已发布文档还要
通过本模块的完整语义校验：

- 属性当前名称与历史名称全局唯一，且不使用保留名称；
- 枚举项非空、不重复，枚举默认值必须属于枚举列表；
- 映射源只能是普通枚举属性，且作用域不得越权；
- 组合属性不能引用组合属性，字段作用域与系统字段受作用域约束；
- DWG 命名模板只允许 ``subset.*`` 系统字段与全部 sheetset 属性；
- 补零格式只允许用于 ``subset.sequence``，宽度 1–12。

映射目标为空、映射源被重复占用、枚举变化后的待确认状态不在这里判定，
它们是发布诊断（``standard_rules.publish_diagnostics``）的职责。
"""

from __future__ import annotations

import re

from dst_manager.domain.standard_models import (
    RESERVED_PROPERTY_NAME_PREFIX,
    RESERVED_PROPERTY_NAMES,
    SHEET_SYSTEM_FIELDS,
    SUBSET_SYSTEM_FIELDS,
    DrawingStandard,
    StandardProperty,
    StandardSegment,
    normalize_property_name,
)
from dst_manager.domain.standard_schema import (
    StandardSchemaError,
    resolve_segment_property,
)

# 宿主登记的数字补零格式：如 "02" 表示补零到两位宽。
PAD_FORMAT_PATTERN = re.compile(r"^\d{1,2}$")
MAX_PAD_WIDTH = 12

_RESERVED_NORMALIZED = frozenset(
    normalize_property_name(name) for name in RESERVED_PROPERTY_NAMES
)


def _error(code: str, detail: str) -> StandardSchemaError:
    return StandardSchemaError(f"{code}: {detail}")


def _is_reserved_name(normalized: str) -> bool:
    return normalized in _RESERVED_NORMALIZED or normalized.startswith(
        RESERVED_PROPERTY_NAME_PREFIX
    )


def validate_pad_format(segment: StandardSegment, owner: str, index: int) -> None:
    """补零格式只允许出现在 ``subset.sequence`` 令牌上，宽度 1–12。"""
    code = segment.format
    if code is None:
        return
    if segment.system_field != "subset.sequence":
        raise _error(
            "STANDARD_SEGMENT_FORMAT_INVALID",
            f"{owner} 片段 #{index} 的补零格式只能用于 subset.sequence",
        )
    if not PAD_FORMAT_PATTERN.fullmatch(code) or not 1 <= int(code) <= MAX_PAD_WIDTH:
        raise _error(
            "STANDARD_SEGMENT_FORMAT_INVALID",
            f"{owner} 片段 #{index} 的格式码 {code!r} 不是登记的数字补零格式",
        )


def validate_property_names(standard: DrawingStandard) -> None:
    """当前名称与历史名称共同参与全局唯一与保留名称检查。"""
    claimed: dict[str, str] = {}
    for prop in standard.properties:
        if not prop.name:
            raise _error("STANDARD_PROPERTY_NAME_INVALID", f"属性 {prop.property_id!r} 名称不能为空")
        for value in (prop.name, *prop.previous_names):
            normalized = normalize_property_name(value)
            if not normalized:
                continue
            if _is_reserved_name(normalized):
                raise _error(
                    "STANDARD_PROPERTY_NAME_RESERVED",
                    f"属性 {prop.property_id!r} 使用保留名称 {value!r}",
                )
            owner = claimed.get(normalized)
            if owner is not None and owner != prop.property_id:
                raise _error(
                    "STANDARD_PROPERTY_NAME_DUPLICATE",
                    f"名称 {value!r} 在属性 {owner!r} 与 {prop.property_id!r} 之间冲突",
                )
            claimed[normalized] = prop.property_id


def validate_enum_properties(standard: DrawingStandard) -> None:
    """枚举项不得为空或重复；非空默认值必须属于枚举列表。"""
    for prop in standard.properties:
        if prop.kind != "enum":
            continue
        values: list[str] = []
        for item in prop.enum_items:
            if not item.value:
                raise _error(
                    "STANDARD_ENUM_ITEM_INVALID",
                    f"枚举属性 {prop.property_id!r} 存在空枚举值",
                )
            if item.value in values:
                raise _error(
                    "STANDARD_ENUM_ITEM_DUPLICATE",
                    f"枚举属性 {prop.property_id!r} 存在重复枚举值 {item.value!r}",
                )
            values.append(item.value)
        if prop.default_value and prop.default_value not in values:
            raise _error(
                "STANDARD_ENUM_DEFAULT_INVALID",
                f"枚举属性 {prop.property_id!r} 的默认值 {prop.default_value!r} 不在枚举列表内",
            )


def validate_mapping_sources(standard: DrawingStandard) -> None:
    """映射源必须是普通枚举属性，且作用域不得越权。"""
    for prop in standard.properties:
        if prop.source_property_id is None:
            continue
        source = standard.find_property(prop.source_property_id)
        if source is None:  # 结构层已拒绝，此处保持防御
            raise _error(
                "STANDARD_MAPPING_SOURCE_INVALID",
                f"属性 {prop.property_id!r} 的映射源 {prop.source_property_id!r} 不存在",
            )
        if source.kind != "enum":
            raise _error(
                "STANDARD_MAPPING_SOURCE_INVALID",
                f"映射属性 {prop.property_id!r} 的源 {source.property_id!r} 不是普通枚举属性",
            )
        if prop.scope == "sheetset" and source.scope != "sheetset":
            raise _error(
                "STANDARD_MAPPING_SCOPE_INVALID",
                f"图纸集映射属性 {prop.property_id!r} 越权引用 {source.scope} 枚举属性 {source.property_id!r}",
            )


def validate_composition_segments(standard: DrawingStandard) -> None:
    """组合字段越权、组合引用组合与非法补零格式在此阻断。"""
    for prop in standard.properties:
        if prop.kind != "composition":
            continue
        for index in range(len(prop.segments)):
            _validate_composition_segment(standard, prop, index)


def _validate_composition_segment(
    standard: DrawingStandard, prop: StandardProperty, index: int
) -> None:
    segment = prop.segments[index]
    owner = f"属性 {prop.property_id!r}"
    referenced = resolve_segment_property(standard, segment, owner, index)
    validate_pad_format(segment, owner, index)
    if segment.literal is not None:
        return
    if segment.system_field is not None:
        if prop.scope == "sheetset" or segment.system_field not in SHEET_SYSTEM_FIELDS:
            raise _error(
                "STANDARD_SEGMENT_SCOPE_INVALID",
                f"组合属性 {prop.property_id!r} 越权引用系统字段 {segment.system_field!r}",
            )
        return
    assert referenced is not None
    if referenced.kind == "composition":
        raise _error(
            "STANDARD_SEGMENT_SCOPE_INVALID",
            f"组合属性 {prop.property_id!r} 不能引用组合属性 {referenced.property_id!r}",
        )
    if prop.scope == "sheetset" and referenced.scope != "sheetset":
        raise _error(
            "STANDARD_SEGMENT_SCOPE_INVALID",
            f"图纸集组合属性 {prop.property_id!r} 越权引用 {referenced.scope} 属性 {referenced.property_id!r}",
        )


def validate_naming_segments(standard: DrawingStandard) -> None:
    """DWG 命名只允许 ``subset.*`` 系统字段与 sheetset 属性。"""
    for index in range(len(standard.dwg_naming.segments)):
        segment = standard.dwg_naming.segments[index]
        owner = "DWG 命名模板"
        referenced = resolve_segment_property(standard, segment, owner, index)
        validate_pad_format(segment, owner, index)
        if segment.literal is not None:
            continue
        if segment.system_field is not None:
            if segment.system_field not in SUBSET_SYSTEM_FIELDS:
                raise _error(
                    "STANDARD_NAMING_FIELD_SCOPE_INVALID",
                    f"DWG 命名模板越权引用系统字段 {segment.system_field!r}",
                )
            continue
        assert referenced is not None
        if referenced.scope != "sheetset":
            raise _error(
                "STANDARD_NAMING_FIELD_SCOPE_INVALID",
                f"DWG 命名模板越权引用 {referenced.scope} 属性 {referenced.property_id!r}",
            )


def validate_published_semantics(standard: DrawingStandard) -> None:
    """按固定顺序执行全部发布语义门禁；首个失败抛出稳定错误码。"""
    validate_property_names(standard)
    validate_enum_properties(standard)
    validate_mapping_sources(standard)
    validate_composition_segments(standard)
    validate_naming_segments(standard)
