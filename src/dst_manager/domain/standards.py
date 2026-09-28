"""图纸标准领域门面（PLAN-DM-046 Task 1）。

Schema v3 数据类型见 :mod:`dst_manager.domain.standard_models`（草稿为
``DraftDrawingStandard``、发布为 ``DrawingStandard``），结构解析见
:mod:`dst_manager.domain.standard_schema`，发布语义门禁见
:mod:`dst_manager.domain.standard_semantics`，派生求值见
:mod:`dst_manager.domain.standard_rules`，DWG 命名见
:mod:`dst_manager.domain.standard_naming`。

两阶段解析入口在本模块组合：草稿的发布时间必须为空；发布在结构门禁之上追加完整
语义校验。服务端注入发布时间：``materialize_published_document`` 在草稿副本上
写入 UTC Unix 毫秒时间戳，``materialize_published_standard`` 再走完整
发布解析。本模块只做公共导入门面，保持既有导入路径稳定。

``schema_version`` 仍标识 JSON 文档格式；依赖能力版本
（``dependencies[*].min_version``）仍保留三段字符串，与标准身份无关。
"""

from __future__ import annotations

from collections.abc import Mapping

from dst_manager.domain.standard_identity import (
    new_standard_id,
    parse_standard_id,
)
from dst_manager.domain.standard_models import (
    ASSET_KINDS,
    DERIVED_PROPERTY_KINDS,
    ORDINARY_PROPERTY_KINDS,
    PROPERTY_KINDS,
    PROPERTY_SCOPES,
    REFERENCE_KINDS,
    RESERVED_PROPERTY_NAME_PREFIX,
    RESERVED_PROPERTY_NAMES,
    SHEET_SYSTEM_FIELDS,
    SUBSET_SYSTEM_FIELDS,
    SYSTEM_FIELDS,
    DraftDrawingStandard,
    DrawingStandard,
    DwgNamingTemplate,
    NumberingPolicy,
    StandardAsset,
    StandardDependency,
    StandardDiagnostic,
    StandardEnumItem,
    StandardMappingRow,
    StandardProperty,
    StandardReference,
    StandardSegment,
    normalize_property_name,
)
from dst_manager.domain.standard_schema import (
    DEPENDENCY_VERSION_PATTERN,
    MAX_STANDARD_VERSION,
    STANDARD_ID_PATTERN,
    STANDARD_VERSION_SEGMENT_PATTERN,
    SUPPORTED_SCHEMA_VERSIONS,
    StandardSchemaError,
    loads_standard_json,
    parse_dependency_version,
    parse_published_at,
    parse_published_standard_structure,
    parse_standard_draft_structure,
    parse_standard_version,
    parse_standard_version_segment,
)
from dst_manager.domain.standard_semantics import (
    MAX_PAD_WIDTH,
    PAD_FORMAT_PATTERN,
    validate_published_semantics,
)

__all__ = [
    "ASSET_KINDS",
    "DEPENDENCY_VERSION_PATTERN",
    "DERIVED_PROPERTY_KINDS",
    "MAX_PAD_WIDTH",
    "MAX_STANDARD_VERSION",
    "ORDINARY_PROPERTY_KINDS",
    "PAD_FORMAT_PATTERN",
    "PROPERTY_KINDS",
    "PROPERTY_SCOPES",
    "REFERENCE_KINDS",
    "RESERVED_PROPERTY_NAMES",
    "RESERVED_PROPERTY_NAME_PREFIX",
    "SHEET_SYSTEM_FIELDS",
    "STANDARD_ID_PATTERN",
    "STANDARD_VERSION_SEGMENT_PATTERN",
    "SUBSET_SYSTEM_FIELDS",
    "SUPPORTED_SCHEMA_VERSIONS",
    "SYSTEM_FIELDS",
    "DraftDrawingStandard",
    "DrawingStandard",
    "DwgNamingTemplate",
    "NumberingPolicy",
    "StandardAsset",
    "StandardDependency",
    "StandardDiagnostic",
    "StandardEnumItem",
    "StandardMappingRow",
    "StandardProperty",
    "StandardReference",
    "StandardSchemaError",
    "StandardSegment",
    "loads_standard_document",
    "loads_standard_draft_document",
    "materialize_published_document",
    "materialize_published_standard",
    "new_standard_id",
    "normalize_property_name",
    "parse_dependency_version",
    "parse_published_at",
    "parse_published_standard_document",
    "parse_standard_draft_document",
    "parse_standard_id",
    "parse_standard_version",
    "parse_standard_version_segment",
]


def parse_standard_draft_document(data: Mapping[str, object]) -> DraftDrawingStandard:
    """解析草稿文档：结构合法、语义允许未完成，且发布时间必须为空。"""
    return parse_standard_draft_structure(data)


def parse_published_standard_document(data: Mapping[str, object]) -> DrawingStandard:
    """解析已发布文档：结构合法之上追加完整发布语义门禁。"""
    standard = parse_published_standard_structure(data)
    validate_published_semantics(standard)
    return standard


def materialize_published_document(
    document: Mapping[str, object], published_at: int
) -> dict[str, object]:
    """在草稿文档副本上注入经校验的 UTC Unix 毫秒发布时间。

    只写入 ``published_at``，不改动原始草稿或其余字段。
    """
    data = dict(document)
    data["published_at"] = parse_published_at(published_at)
    return data


def materialize_published_standard(
    draft_document: Mapping[str, object], published_at: int
) -> DrawingStandard:
    """由草稿文档与发布时间构造并完整校验发布候选。"""
    return parse_published_standard_document(
        materialize_published_document(draft_document, published_at)
    )


def loads_standard_document(text: str | bytes) -> DrawingStandard:
    """从 JSON 文本解析已发布标准；重复字段与语法错误返回稳定错误码。"""
    return parse_published_standard_document(loads_standard_json(text))


def loads_standard_draft_document(text: str | bytes) -> DraftDrawingStandard:
    """从 JSON 文本解析草稿标准；重复字段与语法错误返回稳定错误码。"""
    return parse_standard_draft_document(loads_standard_json(text))
