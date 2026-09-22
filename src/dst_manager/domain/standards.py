"""图纸标准领域门面（PLAN-DM-038 Task 1）。

Schema v1 数据类型见 :mod:`dst_manager.domain.standard_models`，结构解析见
:mod:`dst_manager.domain.standard_schema`，发布语义门禁见
:mod:`dst_manager.domain.standard_semantics`，派生求值见
:mod:`dst_manager.domain.standard_rules`，DWG 命名见
:mod:`dst_manager.domain.standard_naming`。

两阶段解析入口在本模块组合：草稿只过结构门禁，发布在其之上追加完整语义
校验。本模块只做公共导入门面，保持既有导入路径稳定；不再包含旧通用规则
模型（``StandardRule``/顶层 ``rules``），Schema v1 已直接替换且不提供兼容层。
"""

from __future__ import annotations

from collections.abc import Mapping

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
    DrawingStandard,
    DwgNamingTemplate,
    NumberingPolicy,
    StandardAsset,
    StandardAssetFile,
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
    STANDARD_ID_PATTERN,
    STANDARD_VERSION_PATTERN,
    SUPPORTED_SCHEMA_VERSIONS,
    StandardSchemaError,
    loads_standard_json,
    parse_standard_structure,
)
from dst_manager.domain.standard_semantics import (
    MAX_PAD_WIDTH,
    PAD_FORMAT_PATTERN,
    validate_published_semantics,
)

__all__ = [
    "ASSET_KINDS",
    "DERIVED_PROPERTY_KINDS",
    "MAX_PAD_WIDTH",
    "ORDINARY_PROPERTY_KINDS",
    "PAD_FORMAT_PATTERN",
    "PROPERTY_KINDS",
    "PROPERTY_SCOPES",
    "REFERENCE_KINDS",
    "RESERVED_PROPERTY_NAMES",
    "RESERVED_PROPERTY_NAME_PREFIX",
    "SHEET_SYSTEM_FIELDS",
    "STANDARD_ID_PATTERN",
    "STANDARD_VERSION_PATTERN",
    "SUBSET_SYSTEM_FIELDS",
    "SUPPORTED_SCHEMA_VERSIONS",
    "SYSTEM_FIELDS",
    "DrawingStandard",
    "DwgNamingTemplate",
    "NumberingPolicy",
    "StandardAsset",
    "StandardAssetFile",
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
    "normalize_property_name",
    "parse_published_standard_document",
    "parse_standard_draft_document",
]


def parse_standard_draft_document(data: Mapping[str, object]) -> DrawingStandard:
    """解析草稿文档：结构必须合法，语义允许未完成。"""
    return parse_standard_structure(data, published=False)


def parse_published_standard_document(data: Mapping[str, object]) -> DrawingStandard:
    """解析已发布文档：结构合法之上追加完整发布语义门禁。"""
    standard = parse_standard_structure(data, published=True)
    validate_published_semantics(standard)
    return standard


def loads_standard_document(text: str | bytes) -> DrawingStandard:
    """从 JSON 文本解析已发布标准；重复字段与语法错误返回稳定错误码。"""
    return parse_published_standard_document(loads_standard_json(text))


def loads_standard_draft_document(text: str | bytes) -> DrawingStandard:
    """从 JSON 文本解析草稿标准；重复字段与语法错误返回稳定错误码。"""
    return parse_standard_draft_document(loads_standard_json(text))
