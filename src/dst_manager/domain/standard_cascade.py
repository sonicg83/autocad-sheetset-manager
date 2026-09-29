"""级联属性配置与输入值校验。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dst_manager.domain.standard_errors import StandardSchemaError
from dst_manager.domain.standard_models import (
    PROPERTY_SCOPES,
    DrawingStandard,
    StandardCascadeRow,
    StandardDiagnostic,
)


def _error(code: str, detail: str) -> StandardSchemaError:
    return StandardSchemaError(f"{code}: {detail}")


def parse_cascade_options(raw: Any, property_id: str) -> tuple[StandardCascadeRow, ...]:
    """解析 v4 候选行形状；完整性由发布门禁检查，草稿可暂存缺行。"""
    if not isinstance(raw, (list, tuple)):
        raise _error(
            "STANDARD_CASCADE_OPTIONS_INVALID",
            f"级联属性 {property_id!r} 的 cascade_options 必须是列表",
        )
    rows: list[StandardCascadeRow] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise _error(
                "STANDARD_CASCADE_OPTIONS_INVALID",
                f"级联属性 {property_id!r} 的候选行 #{index} 不是对象",
            )
        source_item_id = item.get("source_item_id")
        values = item.get("values", ())
        if not isinstance(source_item_id, str) or not source_item_id:
            raise _error(
                "STANDARD_CASCADE_OPTIONS_INVALID",
                f"级联属性 {property_id!r} 的候选行 #{index} 缺少来源枚举项 ID",
            )
        if not isinstance(values, (list, tuple)) or any(
            not isinstance(value, str) for value in values
        ):
            raise _error(
                "STANDARD_CASCADE_OPTIONS_INVALID",
                f"级联属性 {property_id!r} 的候选行 #{index} 的 values 必须是字符串列表",
            )
        rows.append(
            StandardCascadeRow(source_item_id=source_item_id, values=tuple(values))
        )
    return tuple(rows)


def validate_cascade_definition(
    standard: DrawingStandard,
) -> tuple[StandardDiagnostic, ...]:
    """校验级联来源与候选行是否完整对应当前普通枚举。"""
    diagnostics: list[StandardDiagnostic] = []
    for prop in standard.properties:
        if prop.kind != "cascade":
            continue
        source = (
            standard.find_property(prop.source_property_id)
            if prop.source_property_id is not None
            else None
        )
        if (
            source is None
            or source.kind != "enum"
            or source.scope != prop.scope
            or not source.enum_items
        ):
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_CASCADE_SOURCE_INVALID",
                    message=(
                        f"级联属性 {prop.name or prop.property_id!r} 必须引用同作用域且含枚举项的普通枚举属性"
                    ),
                    property_id=prop.property_id,
                )
            )
            continue

        expected_ids = tuple(item.item_id for item in source.enum_items)
        option_ids = tuple(row.source_item_id for row in prop.cascade_options)
        options_invalid = (
            bool(prop.default_value)
            or option_ids != expected_ids
            or len(option_ids) != len(set(option_ids))
        )
        for row in prop.cascade_options:
            normalized_values = [value.strip().casefold() for value in row.values]
            if (
                not row.values
                or any(not value.strip() for value in row.values)
                or len(normalized_values) != len(set(normalized_values))
            ):
                options_invalid = True
                break
        if options_invalid:
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_CASCADE_OPTIONS_INVALID",
                    message=(
                        f"级联属性 {prop.name or prop.property_id!r} 的候选行须逐项对应上级枚举，"
                        "且每行必须包含非空、不重复的候选值"
                    ),
                    property_id=prop.property_id,
                )
            )
    return tuple(diagnostics)


def validate_cascade_values(
    standard: DrawingStandard, scope: str, values: Mapping[str, str]
) -> tuple[StandardDiagnostic, ...]:
    """按作用域和当前对象的上级枚举值校验级联输入，不推断非法上级的候选。"""
    if scope not in PROPERTY_SCOPES:
        return (
            StandardDiagnostic(
                code="STANDARD_CASCADE_VALUE_INVALID",
                message=f"级联值作用域 {scope!r} 未知",
            ),
        )

    diagnostics: list[StandardDiagnostic] = []
    for prop in standard.properties:
        if prop.kind != "cascade" or prop.scope != scope:
            continue
        source = (
            standard.find_property(prop.source_property_id)
            if prop.source_property_id is not None
            else None
        )
        if source is None or source.kind != "enum" or source.scope != scope:
            continue

        source_value = values.get(source.property_id, "")
        if source_value and source_value not in {
            item.value for item in source.enum_items
        }:
            continue

        child_value = values.get(prop.property_id, "")
        if source_value == "":
            allowed_values: tuple[str, ...] = ()
        else:
            source_item = next(
                (item for item in source.enum_items if item.value == source_value),
                None,
            )
            row = next(
                (
                    option
                    for option in prop.cascade_options
                    if source_item is not None
                    and option.source_item_id == source_item.item_id
                ),
                None,
            )
            allowed_values = row.values if row is not None else ()

        if child_value and child_value not in allowed_values:
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_CASCADE_VALUE_INVALID",
                    message=(
                        f"级联属性 {prop.name or prop.property_id!r} 的值与当前上级枚举值不匹配"
                    ),
                    property_id=prop.property_id,
                )
            )
    return tuple(diagnostics)
