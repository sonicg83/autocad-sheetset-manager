"""图纸标准派生属性编译、求值与发布诊断（PLAN-DM-038 Task 2）。

派生关系内嵌在属性里，求值顺序固定为：

    普通属性 → 映射属性 → 组合属性

映射以 ``enum_item_id`` 关联行——源枚举改名后保留原映射结果；组合令牌只
解析 ``property_id``、``sheet.number`` 与 ``sheet.title``。全程不执行
``eval``、模板脚本或动态导入：片段只能是字段令牌、系统字段令牌或固定文本。

关键语义：

- 可选源为空时映射结果为空字符串，不报错；
- 调用方**漏传**普通属性键与显式空串不同义：漏传即上游无法计算，该派生属性进入
  阻断集合且不写入派生键（显式空串仍按「可选源为空」处理）；
- 非空源值不属于枚举、映射行缺目标或上游失败时，下游组合标记为无法计算，
  不读取调用方传入的旧派生值，也不写入部分结果；
- 枚举列表增删改后映射进入待确认状态，发布检查给出 warning；
- 映射源被两个映射共用、映射目标为空是发布阻断错误。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from dst_manager.domain.standard_models import (
    DrawingStandard,
    StandardDiagnostic,
    StandardMappingRow,
    StandardProperty,
)

__all__ = [
    "CompiledMapping",
    "CompiledProperties",
    "EvaluationResult",
    "compile_standard_properties",
    "evaluate_standard_properties",
    "publish_diagnostics",
]

#: 固定求值顺序：普通属性 → 映射属性 → 组合属性。
DERIVED_ORDER = ("mapping", "composition")


@dataclass(frozen=True, slots=True)
class CompiledMapping:
    """一个映射属性的固定行集合；行跟随源枚举列表的顺序与身份。"""

    property_id: str
    source_property_id: str
    rows: tuple[StandardMappingRow, ...]
    source_items: tuple[tuple[str, str], ...]
    confirmed_source_items: tuple[tuple[str, str], ...] = ()

    @property
    def confirmation_required(self) -> bool:
        """源枚举列表与用户确认时的快照不一致时进入待确认状态。"""
        return self.source_items != self.confirmed_source_items

    def row_for_item(self, item_id: str) -> StandardMappingRow | None:
        for row in self.rows:
            if row.item_id == item_id:
                return row
        return None

    def item_id_for_value(self, value: str) -> str | None:
        for item_id, item_value in self.source_items:
            if item_value == value:
                return item_id
        return None


@dataclass(frozen=True, slots=True)
class CompiledProperties:
    """派生计划：映射与组合属性，以及各枚举属性的当前显示值。"""

    standard: DrawingStandard
    mappings: tuple[CompiledMapping, ...] = ()
    compositions: tuple[StandardProperty, ...] = ()
    enum_values: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def mapping_by_id(self, property_id: str) -> CompiledMapping | None:
        for mapping in self.mappings:
            if mapping.property_id == property_id:
                return mapping
        return None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """求值结果：``values`` 为按 ``property_id`` 键控的全量值，含派生结果。"""

    values: dict[str, str]
    diagnostics: tuple[StandardDiagnostic, ...] = ()


def compile_standard_properties(standard: DrawingStandard) -> CompiledProperties:
    """把标准编译为固定拓扑的派生计划。

    映射行集合由**源枚举列表**决定（顺序与 ``enum_item_id`` 都跟随枚举项），
    存储的映射表只提供各 ``enum_item_id`` 的目标值；枚举项缺少对应行时视为
    空目标，由发布诊断阻断。
    """
    enum_values: dict[str, tuple[str, ...]] = {}
    for prop in standard.properties:
        if prop.kind == "enum":
            enum_values[prop.property_id] = tuple(item.value for item in prop.enum_items)

    mappings: list[CompiledMapping] = []
    for prop in standard.properties:
        if prop.kind != "mapping" or prop.source_property_id is None:
            continue
        source = standard.find_property(prop.source_property_id)
        if source is None or source.kind != "enum":
            continue  # 结构层已拒绝；此处保持防御，不产出不可用映射
        rows: list[StandardMappingRow] = []
        for item in source.enum_items:
            stored = prop.mapping_row(item.item_id)
            rows.append(
                StandardMappingRow(
                    item_id=item.item_id, value=stored.value if stored is not None else ""
                )
            )
        mappings.append(
            CompiledMapping(
                property_id=prop.property_id,
                source_property_id=source.property_id,
                rows=tuple(rows),
                source_items=tuple(
                    (item.item_id, item.value) for item in source.enum_items
                ),
                confirmed_source_items=prop.confirmed_source_items,
            )
        )
    return CompiledProperties(
        standard=standard,
        mappings=tuple(mappings),
        compositions=tuple(
            prop for prop in standard.properties if prop.kind == "composition"
        ),
        enum_values=enum_values,
    )


def evaluate_standard_properties(
    compiled: CompiledProperties,
    values: Mapping[str, str],
    system_values: Mapping[str, str],
) -> EvaluationResult:
    """按固定拓扑求值派生属性。

    ``values`` 以 ``property_id`` 为键提供普通属性值，``system_values`` 提供
    ``sheet.number``/``sheet.title`` 等系统字段。调用方传入的派生属性旧值
    一律丢弃，只使用本次计算出的结果。

    普通属性必须提供键（可以为空串）：**漏传键**代表「宿主没有提供该输入」，
    与「合法的空值」不同义——映射源或组合令牌缺键时该派生属性报
    ``STANDARD_DERIVED_UPSTREAM_INVALID``、进入阻断集合，并且不写入派生键。
    """
    derived_ids = {mapping.property_id for mapping in compiled.mappings} | {
        prop.property_id for prop in compiled.compositions
    }
    result: dict[str, str] = {
        key: value for key, value in values.items() if key not in derived_ids
    }
    diagnostics: list[StandardDiagnostic] = []
    blocked: set[str] = set()

    for prop in compiled.standard.properties:
        if prop.kind != "enum":
            continue
        value = result.get(prop.property_id, "")
        if value and value not in compiled.enum_values.get(prop.property_id, ()):
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_ENUM_VALUE_INVALID",
                    message=f"属性 {prop.name or prop.property_id} 的值 {value!r} 不在枚举列表内",
                    property_id=prop.property_id,
                )
            )
            blocked.add(prop.property_id)

    for mapping in compiled.mappings:
        if mapping.source_property_id in blocked:
            blocked.add(mapping.property_id)
            diagnostics.append(
                _upstream_diagnostic(
                    mapping.property_id,
                    f"映射源 {mapping.source_property_id!r} 无法提供合法值",
                )
            )
            continue
        if mapping.source_property_id not in result:
            blocked.add(mapping.property_id)
            diagnostics.append(
                _upstream_diagnostic(
                    mapping.property_id,
                    f"映射源 {mapping.source_property_id!r} 未提供值",
                )
            )
            continue
        source_value = result[mapping.source_property_id]
        if source_value == "":
            result[mapping.property_id] = ""
            continue
        item_id = mapping.item_id_for_value(source_value)
        row = mapping.row_for_item(item_id) if item_id is not None else None
        if row is None or not row.value:
            blocked.add(mapping.property_id)
            diagnostics.append(
                _upstream_diagnostic(
                    mapping.property_id,
                    f"源值 {source_value!r} 未被映射表覆盖",
                )
            )
            continue
        result[mapping.property_id] = row.value

    for prop in compiled.compositions:
        _evaluate_composition(compiled, prop, result, system_values, blocked, diagnostics)
    return EvaluationResult(values=result, diagnostics=tuple(diagnostics))


def _upstream_diagnostic(property_id: str, detail: str) -> StandardDiagnostic:
    return StandardDiagnostic(
        code="STANDARD_DERIVED_UPSTREAM_INVALID",
        message=f"派生属性 {property_id!r} 无法计算：{detail}",
        property_id=property_id,
    )


def _evaluate_composition(
    compiled: CompiledProperties,
    prop: StandardProperty,
    result: dict[str, str],
    system_values: Mapping[str, str],
    blocked: set[str],
    diagnostics: list[StandardDiagnostic],
) -> None:
    """组合令牌：字段可选（显式空串按空字符串拼接），系统字段必需，上游失败即整条失败。

    字段令牌引用的普通属性**缺键**时同样属于上游失败：不按空串拼接，也不写结果。
    """
    parts: list[str] = []
    for index, segment in enumerate(prop.segments):
        if segment.literal is not None:
            parts.append(segment.literal)
            continue
        if segment.system_field is not None:
            value = system_values.get(segment.system_field, "")
            if value == "":
                diagnostics.append(
                    StandardDiagnostic(
                        code="STANDARD_SYSTEM_VALUE_MISSING",
                        message=f"组合属性 {prop.property_id!r} 缺少必需系统值 {segment.system_field!r}",
                        property_id=prop.property_id,
                        segment_index=index,
                    )
                )
                blocked.add(prop.property_id)
                return
            parts.append(value)
            continue
        referenced = segment.property_id
        assert referenced is not None
        if referenced in blocked:
            diagnostics.append(
                _upstream_diagnostic(prop.property_id, f"上游属性 {referenced!r} 无法计算")
            )
            blocked.add(prop.property_id)
            return
        if referenced not in result:
            diagnostics.append(
                _upstream_diagnostic(prop.property_id, f"上游属性 {referenced!r} 未提供值")
            )
            blocked.add(prop.property_id)
            return
        parts.append(result[referenced])
    result[prop.property_id] = "".join(parts)


def publish_diagnostics(standard: DrawingStandard) -> tuple[StandardDiagnostic, ...]:
    """发布前的派生属性静态门禁：源唯一、目标非空、确认状态。

    不依赖运行期值，因此不需要具体项目数据即可判定。组合字段越权与引用
    未知字段已在 Schema 发布解析中阻断，不在这里重复。
    """
    compiled = compile_standard_properties(standard)
    diagnostics: list[StandardDiagnostic] = []
    claimed: dict[str, str] = {}
    for mapping in compiled.mappings:
        owner = claimed.get(mapping.source_property_id)
        if owner is not None and owner != mapping.property_id:
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_MAPPING_SOURCE_DUPLICATE",
                    message=(
                        f"映射属性 {mapping.property_id!r} 与 {owner!r} "
                        f"共用源属性 {mapping.source_property_id!r}"
                    ),
                    property_id=mapping.property_id,
                )
            )
        else:
            claimed[mapping.source_property_id] = mapping.property_id
        for row in mapping.rows:
            if not row.value:
                diagnostics.append(
                    StandardDiagnostic(
                        code="STANDARD_MAPPING_TARGET_EMPTY",
                        message=(
                            f"映射属性 {mapping.property_id!r} 的枚举项 {row.item_id!r} 缺少目标值"
                        ),
                        property_id=mapping.property_id,
                    )
                )
        if mapping.confirmation_required:
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_MAPPING_CONFIRMATION_REQUIRED",
                    severity="warning",
                    message=f"映射属性 {mapping.property_id!r} 的源枚举列表已变化，请确认映射",
                    property_id=mapping.property_id,
                )
            )
    return tuple(diagnostics)
