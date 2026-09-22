"""图纸标准领域模型与严格解析器（PLAN-DM-035 Task 1）。

标准是纯数据文档：身份仅为 ``standard_id + version``，已发布版本不可变。
本模块只定义冻结领域对象与 ``parse_standard_document`` 解析器；
规则编译与求值见 ``standard_rules``，包与库的持久化见基础设施层。
标准不含任何可执行代码，解析失败一律返回稳定错误码。
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SUPPORTED_SCHEMA_VERSIONS = (1,)

# 标准 ID：小写域式标识（如 ``szmedi.gas``），大小写差异一律视为非法输入，
# 保证同一身份的重复发布/导入碰撞可被稳定拒绝。
STANDARD_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z0-9-]+)*$")
# 标准版本：三段数字版本（如 ``2.1.0``）。
STANDARD_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# 首版规则种类：必填、枚举、固定值、一对一映射、字段组合、编号与受控命名。
RULE_KINDS = ("required", "enum", "fixed", "mapping", "compose", "numbering", "naming")

# 字段作用域；``subset`` 只预留 Schema，不进入首版编辑表单与强制校验。
FIELD_SCOPES = ("sheetset", "sheet", "subset", "derived")
RESERVED_FIELD_SCOPES = ("subset",)

# 资产种类：基础模板与布局模板。
ASSET_KINDS = ("base-template", "layout-template")


class StandardSchemaError(Exception):
    """标准文档解析失败；消息以稳定错误码开头，如 ``STANDARD_ID_INVALID``。"""


@dataclass(frozen=True, slots=True)
class StandardProperty:
    """标准属性定义。``enum_values`` 非空时表示受控枚举。"""

    name: str
    scope: str
    required: bool = False
    default_value: str = ""
    enum_values: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True, slots=True)
class StandardSegment:
    """字段组合（compose/naming）的一个片段：字段令牌、固定文本或受控序号。"""

    field: str | None = None
    literal: str | None = None
    format: str | None = None


@dataclass(frozen=True, slots=True)
class StandardRule:
    """一条封闭规则。语义按 ``kind`` 解释，非法组合由解析器拒绝。"""

    rule_id: str
    kind: str
    target: str
    source: str | None = None
    value: str | None = None
    allowed: tuple[str, ...] = ()
    segments: tuple[StandardSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class StandardAssetFile:
    """包内相对路径及其角色（如图幅枚举值）。"""

    path: str
    role: str = ""


@dataclass(frozen=True, slots=True)
class StandardAsset:
    """标准模板资产声明；文件本体由标准包层校验与复制。"""

    asset_id: str
    kind: str
    files: tuple[StandardAssetFile, ...] = ()


@dataclass(frozen=True, slots=True)
class NumberingPolicy:
    """编号策略：受控序号字段、补零位数与起始值。"""

    sequence_field: str
    digits: int
    start: int = 1


@dataclass(frozen=True, slots=True)
class StandardDependency:
    """受信扩展依赖；缺少声明能力时标准能力降级。"""

    extension_id: str
    capability_id: str
    min_version: str


@dataclass(frozen=True, slots=True)
class DrawingStandard:
    """不可变的图纸标准文档。"""

    schema_version: int
    standard_id: str
    version: str
    name: str
    supported_cad_versions: tuple[str, ...]
    properties: tuple[StandardProperty, ...]
    rules: tuple[StandardRule, ...]
    assets: tuple[StandardAsset, ...]
    numbering: NumberingPolicy
    dependencies: tuple[StandardDependency, ...] = ()


def _error(code: str, detail: str) -> StandardSchemaError:
    return StandardSchemaError(f"{code}: {detail}")


def _require_str(data: Mapping[str, Any], key: str, code: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise _error(code, f"字段 {key!r} 必须是非空字符串")
    return value


def _parse_version(value: str) -> str:
    if not STANDARD_VERSION_PATTERN.fullmatch(value):
        raise _error("STANDARD_VERSION_INVALID", f"版本 {value!r} 不是三段数字版本")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error("STANDARD_FIELD_DUPLICATE", f"重复字段 {key!r}")
        result[key] = value
    return result


def _parse_property(raw: Any, index: int) -> StandardProperty:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_PROPERTY_INVALID", f"属性 #{index} 不是对象")
    name = _require_str(raw, "name", "STANDARD_PROPERTY_INVALID")
    scope = raw.get("scope")
    if scope not in FIELD_SCOPES:
        raise _error("STANDARD_SCOPE_INVALID", f"属性 {name!r} 作用域 {scope!r} 未知")
    enum_values = raw.get("enum_values", ())
    if not isinstance(enum_values, (list, tuple)) or any(
        not isinstance(item, str) for item in enum_values
    ):
        raise _error("STANDARD_PROPERTY_INVALID", f"属性 {name!r} enum_values 必须是字符串列表")
    return StandardProperty(
        name=name,
        scope=str(scope),
        required=bool(raw.get("required", False)),
        default_value=str(raw.get("default_value", "")),
        enum_values=tuple(enum_values),
        description=str(raw.get("description", "")),
    )


def _parse_segment(raw: Any, rule_id: str) -> StandardSegment:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_RULE_INVALID", f"规则 {rule_id!r} 片段不是对象")
    keys = {"field", "literal", "format"} & set(raw)
    if not keys:
        raise _error("STANDARD_RULE_INVALID", f"规则 {rule_id!r} 片段缺少内容")
    field = raw.get("field")
    literal = raw.get("literal")
    if field is not None and literal is not None:
        raise _error("STANDARD_RULE_INVALID", f"规则 {rule_id!r} 片段不能同时含字段与固定文本")
    if field is not None:
        if not isinstance(field, str) or not field:
            raise _error("STANDARD_RULE_INVALID", f"规则 {rule_id!r} 片段字段非法")
        return StandardSegment(field=field)
    if not isinstance(literal, str):
        raise _error("STANDARD_RULE_INVALID", f"规则 {rule_id!r} 片段固定文本非法")
    return StandardSegment(literal=literal, format=raw.get("format"))


def _parse_rule(raw: Any, index: int) -> StandardRule:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_RULE_INVALID", f"规则 #{index} 不是对象")
    rule_id = _require_str(raw, "rule_id", "STANDARD_RULE_INVALID")
    kind = raw.get("kind")
    if kind not in RULE_KINDS:
        raise _error("STANDARD_RULE_KIND_INVALID", f"规则 {rule_id!r} 种类 {kind!r} 未知")
    target = _require_str(raw, "target", "STANDARD_FIELD_INVALID")
    _validate_field_reference(target, rule_id)
    source = raw.get("source")
    if kind == "mapping":
        if not isinstance(source, str) or not source:
            raise _error("STANDARD_RULE_INVALID", f"映射规则 {rule_id!r} 缺少 source")
        _validate_field_reference(source, rule_id)
    allowed = raw.get("allowed", ())
    if not isinstance(allowed, (list, tuple)) or any(not isinstance(item, str) for item in allowed):
        raise _error("STANDARD_RULE_INVALID", f"规则 {rule_id!r} allowed 必须是字符串列表")
    segments = tuple(_parse_segment(item, rule_id) for item in raw.get("segments", ()))
    return StandardRule(
        rule_id=rule_id,
        kind=str(kind),
        target=target,
        source=source if isinstance(source, str) else None,
        value=raw.get("value") if isinstance(raw.get("value"), str) else None,
        allowed=tuple(allowed),
        segments=segments,
    )


def _validate_field_reference(field: str, rule_id: str) -> None:
    scope, _, _ = field.partition(".")
    if scope not in FIELD_SCOPES or not field.partition(".")[2]:
        raise _error("STANDARD_FIELD_INVALID", f"规则 {rule_id!r} 字段引用 {field!r} 非法")


def _parse_asset(raw: Any, index: int) -> StandardAsset:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_ASSET_INVALID", f"资产 #{index} 不是对象")
    asset_id = _require_str(raw, "asset_id", "STANDARD_ASSET_INVALID")
    kind = raw.get("kind")
    if kind not in ASSET_KINDS:
        raise _error("STANDARD_ASSET_KIND_INVALID", f"资产 {asset_id!r} 种类 {kind!r} 未知")
    files: list[StandardAssetFile] = []
    for item in raw.get("files", ()):
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str) or not item["path"]:
            raise _error("STANDARD_ASSET_INVALID", f"资产 {asset_id!r} 文件条目非法")
        files.append(
            StandardAssetFile(path=item["path"], role=str(item.get("role", "")))
        )
    return StandardAsset(asset_id=asset_id, kind=str(kind), files=tuple(files))


def _parse_numbering(raw: Any) -> NumberingPolicy:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_NUMBERING_INVALID", "numbering 不是对象")
    sequence_field = _require_str(raw, "sequence_field", "STANDARD_FIELD_INVALID")
    digits = raw.get("digits")
    if not isinstance(digits, int) or isinstance(digits, bool) or digits <= 0:
        raise _error("STANDARD_NUMBERING_INVALID", "numbering.digits 必须是正整数")
    start = raw.get("start", 1)
    if not isinstance(start, int) or isinstance(start, bool) or start < 0:
        raise _error("STANDARD_NUMBERING_INVALID", "numbering.start 必须是非负整数")
    return NumberingPolicy(sequence_field=sequence_field, digits=digits, start=start)


def _parse_dependency(raw: Any, index: int) -> StandardDependency:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_DEPENDENCY_INVALID", f"依赖 #{index} 不是对象")
    return StandardDependency(
        extension_id=_require_str(raw, "extension_id", "STANDARD_DEPENDENCY_INVALID"),
        capability_id=_require_str(raw, "capability_id", "STANDARD_DEPENDENCY_INVALID"),
        min_version=_parse_version(_require_str(raw, "min_version", "STANDARD_VERSION_INVALID")),
    )


def parse_standard_document(data: Mapping[str, object]) -> DrawingStandard:
    """把标准文档映射解析为冻结的 :class:`DrawingStandard`。

    拒绝未知 Schema 版本、重复字段、非法 ID/版本、未知作用域/规则种类
    和重复资产 ID；任何失败都抛出以稳定错误码开头的
    :class:`StandardSchemaError`。
    """
    schema_version = data.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise _error(
            "STANDARD_SCHEMA_VERSION_UNSUPPORTED",
            f"schema_version {schema_version!r} 不受支持",
        )
    standard_id = _require_str(data, "standard_id", "STANDARD_ID_INVALID")
    if not STANDARD_ID_PATTERN.fullmatch(standard_id):
        raise _error("STANDARD_ID_INVALID", f"标准 ID {standard_id!r} 非法（须为小写域式标识）")
    version = _parse_version(_require_str(data, "version", "STANDARD_VERSION_INVALID"))
    name = _require_str(data, "name", "STANDARD_NAME_INVALID")
    cad_versions = data.get("supported_cad_versions")
    if (
        not isinstance(cad_versions, (list, tuple))
        or not cad_versions
        or any(not isinstance(item, str) or not item for item in cad_versions)
    ):
        raise _error(
            "STANDARD_CAD_VERSIONS_INVALID", "supported_cad_versions 必须是非空字符串列表"
        )
    properties = tuple(
        _parse_property(item, index) for index, item in enumerate(data.get("properties", ()))
    )
    rules = tuple(_parse_rule(item, index) for index, item in enumerate(data.get("rules", ())))
    assets_raw = data.get("assets", ())
    assets = tuple(_parse_asset(item, index) for index, item in enumerate(assets_raw))
    asset_ids = [asset.asset_id for asset in assets]
    if len(asset_ids) != len(set(asset_ids)):
        raise _error("STANDARD_ASSET_DUPLICATE", f"重复资产 ID：{asset_ids}")
    rule_ids = [rule.rule_id for rule in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise _error("STANDARD_RULE_DUPLICATE", f"重复规则 ID：{rule_ids}")
    return DrawingStandard(
        schema_version=int(schema_version),
        standard_id=standard_id,
        version=version,
        name=name,
        supported_cad_versions=tuple(cad_versions),
        properties=properties,
        rules=rules,
        assets=assets,
        numbering=_parse_numbering(data.get("numbering", {})),
        dependencies=tuple(
            _parse_dependency(item, index)
            for index, item in enumerate(data.get("dependencies", ()))
        ),
    )


def loads_standard_document(text: str | bytes) -> DrawingStandard:
    """从 JSON 文本解析标准；重复字段与语法错误返回稳定错误码。"""
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise _error("STANDARD_JSON_INVALID", f"JSON 语法错误：{exc.msg}") from exc
    if not isinstance(data, Mapping):
        raise _error("STANDARD_JSON_INVALID", "标准文档根必须是对象")
    return parse_standard_document(data)
