"""图纸标准领域门面（PLAN-DM-038 Task 1；PLAN-DM-041 Task 2）。

Schema v2 数据类型见 :mod:`dst_manager.domain.standard_models`（草稿为
``DraftDrawingStandard``、发布为 ``DrawingStandard``），结构解析见
:mod:`dst_manager.domain.standard_schema`，发布语义门禁见
:mod:`dst_manager.domain.standard_semantics`，派生求值见
:mod:`dst_manager.domain.standard_rules`，DWG 命名见
:mod:`dst_manager.domain.standard_naming`。

两阶段解析入口在本模块组合：草稿只过结构门禁且**不携带版本**；发布在其之上
追加完整语义校验。正式版本由发布时分配：``materialize_published_document``
在草稿文档副本上写入整数版本，``materialize_published_standard`` 再走完整
发布解析。本模块只做公共导入门面，保持既有导入路径稳定。

文档格式版本（``schema_version``）与标准发布版本（``version``）是两个概念；
依赖能力版本（``dependencies[*].min_version``）保留三段字符串，三个解析器
互不共用。
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
    "normalize_property_name",
    "parse_dependency_version",
    "parse_published_standard_document",
    "parse_standard_draft_document",
    "parse_standard_version",
    "parse_standard_version_segment",
]


def parse_standard_draft_document(data: Mapping[str, object]) -> DraftDrawingStandard:
    """解析草稿文档：结构必须合法、语义允许未完成、不得携带 ``version``。"""
    return parse_standard_draft_structure(data)


def parse_published_standard_document(data: Mapping[str, object]) -> DrawingStandard:
    """解析已发布文档：结构合法之上追加完整发布语义门禁。"""
    standard = parse_published_standard_structure(data)
    validate_published_semantics(standard)
    return standard


def materialize_published_document(
    document: Mapping[str, object], version: int
) -> dict[str, object]:
    """在草稿文档**副本**上写入已校验的整数版本；不改动原始文档。

    只覆盖 ``version`` 一个字段，其余键（含实现未识别的扩展键）与顺序保留。
    """
    data = dict(document)
    data.pop("version", None)
    # 先校验再写入：非法版本不会进入待写文档。
    data["version"] = parse_standard_version(version)
    return data


def materialize_published_standard(
    draft_document: Mapping[str, object], version: int
) -> DrawingStandard:
    """由草稿文档与分配到的整数版本构造并完整校验发布候选。"""
    return parse_published_standard_document(
        materialize_published_document(draft_document, version)
    )


def loads_standard_document(text: str | bytes) -> DrawingStandard:
    """从 JSON 文本解析已发布标准；重复字段与语法错误返回稳定错误码。"""
    return parse_published_standard_document(loads_standard_json(text))


def loads_standard_draft_document(text: str | bytes) -> DraftDrawingStandard:
    """从 JSON 文本解析草稿标准；重复字段与语法错误返回稳定错误码。"""
    return parse_standard_draft_document(loads_standard_json(text))
