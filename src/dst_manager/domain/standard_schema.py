"""图纸标准 Schema v3 结构解析（PLAN-DM-046 Task 1）。

本模块只负责**结构**：文档格式版本、稳定 ID、JSON 类型、片段形状与引用对象
存在性。草稿与发布共用同一结构解析，区别在版本字段与 ``dwg_naming``：

- 草稿必须带 ``published_at: null``；
- 发布必须带非负 UTC Unix 毫秒整数 ``published_at``；
- 两种文档都拒绝旧标准发布 ``version`` 字段。

依赖能力版本使用 :func:`parse_dependency_version`（三段数字字符串）；它与
标准身份和文档格式版本无关。

语义门禁见 :mod:`dst_manager.domain.standard_semantics`；两阶段入口在
:mod:`dst_manager.domain.standards` 门面组合。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from dst_manager.domain.standard_cascade import parse_cascade_options
from dst_manager.domain.standard_errors import (
    StandardSchemaError,  # noqa: F401
)
from dst_manager.domain.standard_errors import (
    standard_error as _error,
)
from dst_manager.domain.standard_identity import parse_standard_id
from dst_manager.domain.standard_models import (
    ASSET_KINDS,
    PROPERTY_KINDS,
    PROPERTY_SCOPES,
    SYSTEM_FIELDS,
    DraftDrawingStandard,
    DrawingStandard,
    DwgNamingTemplate,
    NumberingPolicy,
    StandardAsset,
    StandardDependency,
    StandardEnumItem,
    StandardMappingRow,
    StandardProperty,
    StandardSegment,
)
from dst_manager.domain.standard_versioning import (
    DEPENDENCY_VERSION_PATTERN,  # noqa: F401
    parse_dependency_version,
)

#: 支持的文档格式版本。
SUPPORTED_SCHEMA_VERSIONS = (3, 4)

def _require_str(data: Mapping[str, Any], key: str, code: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise _error(code, f"字段 {key!r} 必须是非空字符串")
    return value


def _text(raw: Mapping[str, Any], key: str, code: str) -> str:
    """取字符串字段；缺失时为空串，类型非法时报错（草稿允许空内容）。"""
    value = raw.get(key, "")
    if not isinstance(value, str):
        raise _error(code, f"字段 {key!r} 必须是字符串")
    return value


def _sequence(raw: Mapping[str, Any], key: str, code: str) -> list[Any]:
    value = raw.get(key, ())
    if not isinstance(value, (list, tuple)):
        raise _error(code, f"字段 {key!r} 必须是列表")
    return list(value)


def _str_tuple(raw: Mapping[str, Any], key: str, code: str) -> tuple[str, ...]:
    items = _sequence(raw, key, code)
    if any(not isinstance(item, str) for item in items):
        raise _error(code, f"字段 {key!r} 必须是字符串列表")
    return tuple(items)


def parse_published_at(value: object) -> int:
    """验证非负 UTC Unix 毫秒整数，显式排除布尔值、小数与字符串。"""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _error(
            "STANDARD_PUBLISHED_AT_INVALID",
            "published_at 必须是非负 UTC Unix 毫秒整数",
        )
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error("STANDARD_FIELD_DUPLICATE", f"重复字段 {key!r}")
        result[key] = value
    return result


# ---- 片段 ----------------------------------------------------------------


def _parse_segment(raw: Any, owner: str, index: int) -> StandardSegment:
    """解析令牌片段：字段、系统字段与固定文本三者必须互斥且存在其一。"""
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_SEGMENT_INVALID", f"{owner} 片段 #{index} 不是对象")
    present = [
        key
        for key in ("property_id", "system_field", "literal")
        if raw.get(key) is not None
    ]
    if len(present) != 1:
        raise _error(
            "STANDARD_SEGMENT_INVALID",
            f"{owner} 片段 #{index} 必须且只能包含字段、系统字段或固定文本之一",
        )
    key = present[0]
    value = raw[key]
    if not isinstance(value, str):
        raise _error("STANDARD_SEGMENT_INVALID", f"{owner} 片段 #{index} 的 {key!r} 必须是字符串")
    if key != "literal" and not value:
        raise _error("STANDARD_SEGMENT_INVALID", f"{owner} 片段 #{index} 的 {key!r} 不能为空")
    format_code = raw.get("format")
    if format_code is not None and not isinstance(format_code, str):
        raise _error(
            "STANDARD_SEGMENT_FORMAT_INVALID", f"{owner} 片段 #{index} 的格式码必须是字符串"
        )
    return StandardSegment(
        property_id=value if key == "property_id" else None,
        system_field=value if key == "system_field" else None,
        literal=value if key == "literal" else None,
        format=format_code,
    )


# ---- 属性 ----------------------------------------------------------------


def _parse_enum_item(raw: Any, property_id: str, index: int) -> StandardEnumItem:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_ENUM_ITEM_INVALID", f"属性 {property_id!r} 枚举项 #{index} 不是对象")
    item_id = _require_str(raw, "item_id", "STANDARD_ENUM_ITEM_ID_INVALID")
    return StandardEnumItem(item_id=item_id, value=_text(raw, "value", "STANDARD_ENUM_ITEM_INVALID"))


def _parse_mapping_row(raw: Any, property_id: str, index: int) -> StandardMappingRow:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_MAPPING_ROW_INVALID", f"属性 {property_id!r} 映射行 #{index} 不是对象")
    item_id = _require_str(raw, "item_id", "STANDARD_MAPPING_ROW_INVALID")
    return StandardMappingRow(
        item_id=item_id, value=_text(raw, "value", "STANDARD_MAPPING_ROW_INVALID")
    )


def _parse_confirmed_items(raw: Any, property_id: str) -> tuple[tuple[str, str], ...]:
    """解析映射确认快照：``[枚举项 ID, 当时显示值]`` 的有序列表。"""
    if not isinstance(raw, (list, tuple)):
        raise _error(
            "STANDARD_MAPPING_ROW_INVALID",
            f"属性 {property_id!r} 的 confirmed_source_items 必须是列表",
        )
    confirmed: list[tuple[str, str]] = []
    for index, item in enumerate(raw):
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
            or not item[0]
        ):
            raise _error(
                "STANDARD_MAPPING_ROW_INVALID",
                f"属性 {property_id!r} 的 confirmed_source_items #{index} 必须是 [枚举项 ID, 值]",
            )
        confirmed.append((item[0], item[1]))
    return tuple(confirmed)


def _parse_property(raw: Any, index: int, schema_version: int) -> StandardProperty:
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_PROPERTY_INVALID", f"属性 #{index} 不是对象")
    property_id = _require_str(raw, "property_id", "STANDARD_PROPERTY_ID_INVALID")
    scope = raw.get("scope")
    if scope not in PROPERTY_SCOPES:
        raise _error("STANDARD_SCOPE_INVALID", f"属性 {property_id!r} 作用域 {scope!r} 未知")
    kind = raw.get("kind")
    if schema_version == 3 and (kind == "cascade" or "cascade_options" in raw):
        raise _error(
            "STANDARD_CASCADE_SCHEMA_UNSUPPORTED",
            "级联属性仅支持 schema_version 4",
        )
    if kind not in PROPERTY_KINDS:
        raise _error(
            "STANDARD_PROPERTY_KIND_INVALID", f"属性 {property_id!r} 类型 {kind!r} 未知"
        )
    if kind != "cascade" and "cascade_options" in raw:
        raise _error(
            "STANDARD_CASCADE_OPTIONS_INVALID",
            f"非级联属性 {property_id!r} 不得包含 cascade_options",
        )
    required = raw.get("required", False)
    if not isinstance(required, bool):
        raise _error("STANDARD_PROPERTY_INVALID", f"属性 {property_id!r} required 必须是布尔值")
    source_property_id = raw.get("source_property_id")
    if source_property_id is not None and (
        not isinstance(source_property_id, str) or not source_property_id
    ):
        source_code = (
            "STANDARD_CASCADE_SOURCE_INVALID"
            if kind == "cascade"
            else "STANDARD_MAPPING_SOURCE_INVALID"
        )
        raise _error(source_code, f"属性 {property_id!r} 的源 ID 非法")
    return StandardProperty(
        property_id=property_id,
        name=_text(raw, "name", "STANDARD_PROPERTY_INVALID"),
        previous_names=_str_tuple(raw, "previous_names", "STANDARD_PROPERTY_INVALID"),
        scope=str(scope),
        kind=str(kind),
        required=required,
        default_value=_text(raw, "default_value", "STANDARD_PROPERTY_INVALID"),
        enum_items=tuple(
            _parse_enum_item(item, property_id, position)
            for position, item in enumerate(
                _sequence(raw, "enum_items", "STANDARD_ENUM_ITEM_INVALID")
            )
        ),
        cascade_options=(
            parse_cascade_options(raw.get("cascade_options", ()), property_id)
            if kind == "cascade"
            else ()
        ),
        source_property_id=source_property_id,
        mapping=tuple(
            _parse_mapping_row(item, property_id, position)
            for position, item in enumerate(
                _sequence(raw, "mapping", "STANDARD_MAPPING_ROW_INVALID")
            )
        ),
        confirmed_source_items=_parse_confirmed_items(
            raw.get("confirmed_source_items", ()), property_id
        ),
        segments=tuple(
            _parse_segment(item, f"属性 {property_id!r}", position)
            for position, item in enumerate(_sequence(raw, "segments", "STANDARD_SEGMENT_INVALID"))
        ),
        description=_text(raw, "description", "STANDARD_PROPERTY_INVALID"),
    )


# ---- 资产、编号与依赖 ----------------------------------------------------


def _parse_asset(raw: Any, index: int) -> StandardAsset:
    """解析单文件资产（PLAN-DM-042）：``file`` 必填，``paper_layouts`` 去重保序。

    旧多文件 ``files``/``role`` 形状没有 ``file`` 字段，在此以稳定码拒绝，
    不做自动转换（旧标准包须重新导入）。
    """
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_ASSET_INVALID", f"资产 #{index} 不是对象")
    asset_id = _require_str(raw, "asset_id", "STANDARD_ASSET_INVALID")
    kind = raw.get("kind")
    if kind not in ASSET_KINDS:
        raise _error("STANDARD_ASSET_KIND_INVALID", f"资产 {asset_id!r} 种类 {kind!r} 未知")
    file_path = _require_str(raw, "file", "STANDARD_ASSET_INVALID")
    paper_layouts: list[str] = []
    for item in _sequence(raw, "paper_layouts", "STANDARD_ASSET_INVALID"):
        if not isinstance(item, str):
            raise _error(
                "STANDARD_ASSET_INVALID",
                f"资产 {asset_id!r} 的 paper_layouts 必须是字符串列表",
            )
        name = item.strip()
        if name and name not in paper_layouts:
            paper_layouts.append(name)
    return StandardAsset(
        asset_id=asset_id,
        kind=str(kind),
        file=file_path,
        paper_layouts=tuple(paper_layouts),
    )


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
        min_version=parse_dependency_version(
            _require_str(raw, "min_version", "STANDARD_VERSION_INVALID")
        ),
    )


# ---- 引用对象存在性 ------------------------------------------------------


def resolve_segment_property(
    standard: DrawingStandard, segment: StandardSegment, owner: str, index: int
) -> StandardProperty | None:
    """解析片段引用的属性：系统字段返回 None，未知引用报稳定错误。

    结构层只保证被引用对象存在；作用域与类型越权由语义层判定。
    """
    if segment.system_field is not None:
        if segment.system_field not in SYSTEM_FIELDS:
            raise _error(
                "STANDARD_SEGMENT_REFERENCE_UNKNOWN",
                f"{owner} 片段 #{index} 引用未知系统字段 {segment.system_field!r}",
            )
        return None
    if segment.property_id is not None:
        referenced = standard.find_property(segment.property_id)
        if referenced is None:
            raise _error(
                "STANDARD_SEGMENT_REFERENCE_UNKNOWN",
                f"{owner} 片段 #{index} 引用未知属性 {segment.property_id!r}",
            )
        return referenced
    return None


def _validate_references(standard: DrawingStandard) -> None:
    for prop in standard.properties:
        if (
            prop.kind != "cascade"
            and prop.source_property_id is not None
            and standard.find_property(prop.source_property_id) is None
        ):
            raise _error(
                "STANDARD_MAPPING_SOURCE_INVALID",
                f"属性 {prop.property_id!r} 的映射源 {prop.source_property_id!r} 不存在",
            )
        for index, segment in enumerate(prop.segments):
            resolve_segment_property(standard, segment, f"属性 {prop.property_id!r}", index)
    for index, segment in enumerate(standard.dwg_naming.segments):
        resolve_segment_property(standard, segment, "DWG 命名模板", index)


# ---- 入口 ----------------------------------------------------------------


def _parse_common_structure(data: Mapping[str, object], *, published: bool) -> dict[str, object]:
    """解析草稿与发布共有的结构字段；返回构造实体所需的 kwargs。

    旧 ``version`` 与 ``release_notes`` 均不得进入 v3 文档。
    """
    if not isinstance(data, Mapping):
        raise _error("STANDARD_JSON_INVALID", "标准文档根必须是对象")
    schema_version = data.get("schema_version")
    if type(schema_version) is not int or schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise _error(
            "STANDARD_SCHEMA_VERSION_UNSUPPORTED",
            f"schema_version {schema_version!r} 不受支持",
        )
    if "version" in data:
        raise _error(
            "STANDARD_VERSION_INVALID",
            "v3 标准文档不得携带旧 version 字段",
        )
    if "release_notes" in data:
        raise _error(
            "STANDARD_RELEASE_NOTES_DEPRECATED",
            "v3 标准文档使用 description，不得携带 release_notes",
        )
    if "published_at" not in data:
        raise _error("STANDARD_PUBLISHED_AT_INVALID", "标准文档必须包含 published_at")
    raw_published_at = data["published_at"]
    if published:
        published_at: int | None = parse_published_at(raw_published_at)
    else:
        if raw_published_at is not None:
            raise _error("STANDARD_PUBLISHED_AT_INVALID", "草稿 published_at 必须为 null")
        published_at = None
    raw_standard_id = _require_str(data, "standard_id", "STANDARD_ID_INVALID")
    try:
        standard_id = parse_standard_id(raw_standard_id)
    except ValueError as exc:
        raise _error("STANDARD_ID_INVALID", f"标准 ID {raw_standard_id!r} 必须是带连字符的 UUID") from exc
    if published:
        name = _require_str(data, "name", "STANDARD_NAME_INVALID")
    else:
        if "name" not in data:
            raise _error("STANDARD_NAME_INVALID", "字段 'name' 必须是字符串")
        name = _text(data, "name", "STANDARD_NAME_INVALID")
    description = _text(data, "description", "STANDARD_DESCRIPTION_INVALID")
    cad_versions = _sequence(data, "supported_cad_versions", "STANDARD_CAD_VERSIONS_INVALID")
    if not cad_versions or any(not isinstance(item, str) or not item for item in cad_versions):
        raise _error(
            "STANDARD_CAD_VERSIONS_INVALID", "supported_cad_versions 必须是非空字符串列表"
        )

    properties = tuple(
        _parse_property(item, index, int(schema_version))
        for index, item in enumerate(_sequence(data, "properties", "STANDARD_PROPERTY_INVALID"))
    )
    property_ids = [prop.property_id for prop in properties]
    if len(property_ids) != len(set(property_ids)):
        raise _error("STANDARD_PROPERTY_ID_DUPLICATE", f"重复属性 ID：{property_ids}")
    for prop in properties:
        item_ids = [item.item_id for item in prop.enum_items]
        if len(item_ids) != len(set(item_ids)):
            raise _error(
                "STANDARD_ENUM_ITEM_ID_DUPLICATE",
                f"属性 {prop.property_id!r} 存在重复枚举项 ID：{item_ids}",
            )

    assets = tuple(
        _parse_asset(item, index)
        for index, item in enumerate(_sequence(data, "assets", "STANDARD_ASSET_INVALID"))
    )
    asset_ids = [asset.asset_id for asset in assets]
    if len(asset_ids) != len(set(asset_ids)):
        raise _error("STANDARD_ASSET_DUPLICATE", f"重复资产 ID：{asset_ids}")

    return {
        "schema_version": int(schema_version),
        "standard_id": standard_id,
        "published_at": published_at,
        "name": name,
        "description": description,
        "supported_cad_versions": tuple(str(item) for item in cad_versions),
        "properties": properties,
        "dwg_naming": _parse_dwg_naming(data.get("dwg_naming"), published=published),
        "assets": assets,
        "numbering": _parse_numbering(data.get("numbering", {})),
        "dependencies": tuple(
            _parse_dependency(item, index)
            for index, item in enumerate(
                _sequence(data, "dependencies", "STANDARD_DEPENDENCY_INVALID")
            )
        ),
    }


def parse_standard_draft_structure(data: Mapping[str, object]) -> DraftDrawingStandard:
    """把草稿文档映射解析为 :class:`DraftDrawingStandard`（仅结构校验）。"""
    draft = DraftDrawingStandard(**_parse_common_structure(data, published=False))
    _validate_references(draft)
    return draft


def parse_published_standard_structure(data: Mapping[str, object]) -> DrawingStandard:
    """把发布文档映射解析为 :class:`DrawingStandard`（仅结构校验）。

    拒绝未知文档格式版本、重复字段、非法 UUID/发布时间、未知作用域/类型、
    重复属性 ID、重复枚举项 ID、重复资产 ID 与未知引用；任何失败都抛出
    以稳定错误码开头的 :class:`StandardSchemaError`。
    """
    common = _parse_common_structure(data, published=True)
    standard = DrawingStandard(**common)
    _validate_references(standard)
    return standard


def _parse_dwg_naming(raw: Any, *, published: bool) -> DwgNamingTemplate:
    if raw is None:
        if published:
            raise _error("STANDARD_DWG_NAMING_MISSING", "标准缺少 dwg_naming 模板")
        return DwgNamingTemplate()
    if not isinstance(raw, Mapping):
        raise _error("STANDARD_DWG_NAMING_INVALID", "dwg_naming 不是对象")
    segments = tuple(
        _parse_segment(item, "DWG 命名模板", index)
        for index, item in enumerate(_sequence(raw, "segments", "STANDARD_SEGMENT_INVALID"))
    )
    if published and not segments:
        raise _error("STANDARD_DWG_NAMING_MISSING", "标准缺少 dwg_naming 模板片段")
    return DwgNamingTemplate(segments=segments)


def loads_standard_json(text: str | bytes) -> Mapping[str, Any]:
    """从 JSON 文本读取对象；重复字段与语法错误返回稳定错误码。"""
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise _error("STANDARD_JSON_INVALID", f"JSON 语法错误：{exc.msg}") from exc
    if not isinstance(data, Mapping):
        raise _error("STANDARD_JSON_INVALID", "标准文档根必须是对象")
    return data
