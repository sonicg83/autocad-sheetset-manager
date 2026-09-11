"""图纸目录模板校验与扩展设置语义（PLAN-DM-020 Task 5 / SPEC-DM-012 §5.3/§6）。

内置默认模板来自代码常量（不写数据库、不可改名或删除，用户编辑后只能另存
为新模板）；``load_templates`` 合并代码常量与 settings JSON，坏条目逐条隔离
并输出稳定诊断，未知高 schema 保留原 JSON 不加载为可编辑状态。
``save_templates`` 做乐观并发核对（冲突时本地编辑原样保留，刷新服务端模板
修订后可另存为或按新修订重试）、封闭限制值校验、用户模板 UUID 唯一与
模板名 casefold 唯一性检查；
删除用户模板是纯函数，只动模板设置，不触碰历史 Artifact。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from dst_manager.extensions.builtin.sheet_catalog.errors import (
    SheetCatalogError,
    sheet_catalog_error,
)
from dst_manager.extensions.builtin.sheet_catalog.expressions import (
    ExpressionToken,
    parse_expression,
)

if TYPE_CHECKING:
    from dst_manager.infrastructure.persistence.extensions import VersionedJson

__all__ = [
    "DEFAULT_TEMPLATE",
    "MAX_COLUMNS",
    "MAX_EXPRESSION_CHARS",
    "MAX_HEADER_CHARS",
    "MAX_NAME_CHARS",
    "MAX_USER_TEMPLATES",
    "SheetCatalogTemplate",
    "TemplateCollection",
    "TemplateColumn",
    "ValidatedTemplate",
    "delete_template",
    "load_templates",
    "save_templates",
    "validate_template",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TemplateColumn:
    column_id: uuid.UUID
    header: str
    expression: str


@dataclass(frozen=True, slots=True)
class SheetCatalogTemplate:
    template_id: uuid.UUID | None
    name: str
    schema_version: Literal[1]
    columns: tuple[TemplateColumn, ...]


@dataclass(frozen=True, slots=True)
class TemplateCollection:
    revision: int
    builtin: SheetCatalogTemplate
    user_templates: tuple[SheetCatalogTemplate, ...]
    #: ``load_templates`` 检测到未知高 schema 时置 True：服务端原 JSON 已
    #: 保留且高于当前可解析格式，``save_templates`` 必须拒绝以免 v1 负载
    #: 静默覆盖原 JSON（Ruling-9）。带默认值，向后兼容既有构造。
    unknown_schema_preserved: bool = field(default=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class ValidatedTemplate:
    template: SheetCatalogTemplate
    parsed_columns: tuple[tuple[ExpressionToken, ...], ...]


#: SPEC-DM-012 §5.3 首版限制值（超限明确提示，不截断不静默丢弃）。
MAX_USER_TEMPLATES = 100
MAX_COLUMNS = 50
MAX_NAME_CHARS = 80
MAX_HEADER_CHARS = 100
MAX_EXPRESSION_CHARS = 1024

TEMPLATE_SCHEMA_VERSION: Literal[1] = 1

#: SPEC-DM-012 §6.2 内置默认模板：随扩展版本交付的代码常量。
_BUILTIN_TEMPLATE_NAME = "默认图纸目录（内置）"
_BUILTIN_COLUMNS = (
    ("图号", "{sheet.number}"),
    ("图名", "{sheet.title}"),
    ("文件名", "{sheet.file_name}"),
)
_COLUMN_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "dst-manager.sheet-catalog")


def _stable_uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(_COLUMN_NAMESPACE, name)


DEFAULT_TEMPLATE = SheetCatalogTemplate(
    template_id=None,
    name=_BUILTIN_TEMPLATE_NAME,
    schema_version=1,
    columns=tuple(
        TemplateColumn(
            column_id=_stable_uuid(f"builtin-column:{header}:{expression}"),
            header=header,
            expression=expression,
        )
        for header, expression in _BUILTIN_COLUMNS
    ),
)


# ---------------------------------------------------------------------------
# 校验：限制值、casefold 唯一、逐列解析
# ---------------------------------------------------------------------------


def _limit(kind: str, limit: int, actual: int) -> SheetCatalogError:
    return sheet_catalog_error(
        "SHEET_CATALOG_TEMPLATE_LIMIT", {"kind": kind, "limit": limit, "actual": actual}
    )


def validate_template(template: SheetCatalogTemplate) -> ValidatedTemplate:
    """校验单个模板的结构、限制值与表达式语法；不要求兼容当前字段目录。"""
    if len(template.name) < 1:
        raise _limit("template_name", 1, len(template.name))
    if len(template.name) > MAX_NAME_CHARS:
        raise _limit("template_name", MAX_NAME_CHARS, len(template.name))
    if len(template.columns) < 1:
        raise _limit("columns", 1, len(template.columns))
    if len(template.columns) > MAX_COLUMNS:
        raise _limit("columns", MAX_COLUMNS, len(template.columns))
    seen: dict[str, str] = {}
    parsed: list[tuple[ExpressionToken, ...]] = []
    for column in template.columns:
        if len(column.header) < 1:
            raise _limit("column_header", 1, len(column.header))
        if len(column.header) > MAX_HEADER_CHARS:
            raise _limit("column_header", MAX_HEADER_CHARS, len(column.header))
        folded = column.header.casefold()
        if folded in seen:
            raise sheet_catalog_error(
                "SHEET_CATALOG_COLUMN_DUPLICATE", {"header": column.header}
            )
        seen[folded] = column.header
        if len(column.expression) > MAX_EXPRESSION_CHARS:
            raise _limit("expression", MAX_EXPRESSION_CHARS, len(column.expression))
        try:
            parsed.append(parse_expression(column.expression))
        except SheetCatalogError as error:
            raise sheet_catalog_error(
                "SHEET_CATALOG_EXPRESSION_INVALID",
                {"source_start": error.params["source_start"], "column_header": column.header},
            ) from error
    return ValidatedTemplate(template, tuple(parsed))


# ---------------------------------------------------------------------------
# settings JSON 序列化与严格回读
# ---------------------------------------------------------------------------


def _column_to_json(column: TemplateColumn) -> dict[str, object]:
    return {
        "column_id": str(column.column_id),
        "header": column.header,
        "expression": column.expression,
    }


def _template_to_json(template: SheetCatalogTemplate) -> dict[str, object]:
    return {
        "template_id": str(template.template_id),
        "name": template.name,
        "schema_version": template.schema_version,
        "columns": [_column_to_json(column) for column in template.columns],
    }


def _template_from_json(entry: object) -> SheetCatalogTemplate:
    """严格回读单个模板 JSON；结构/类型不符抛 ``TypeError``/``ValueError``。"""
    if not isinstance(entry, dict):
        raise TypeError("template entry must be a JSON object")
    template_id = uuid.UUID(str(entry["template_id"]))
    name = entry["name"]
    columns_raw = entry["columns"]
    if entry["schema_version"] != TEMPLATE_SCHEMA_VERSION:
        raise ValueError("unsupported template schema_version")
    if not isinstance(name, str) or not isinstance(columns_raw, list):
        raise TypeError("template name/columns must be str/list")
    for column in columns_raw:
        if (
            not isinstance(column, dict)
            or not isinstance(column.get("header"), str)
            or not isinstance(column.get("expression"), str)
        ):
            raise TypeError("template columns must carry str header/expression")
    columns = tuple(
        TemplateColumn(
            column_id=uuid.UUID(str(column["column_id"])),
            header=column["header"],
            expression=column["expression"],
        )
        for column in columns_raw
    )
    return SheetCatalogTemplate(template_id, name, TEMPLATE_SCHEMA_VERSION, columns)


# ---------------------------------------------------------------------------
# 保存 / 加载 / 删除
# ---------------------------------------------------------------------------


def save_templates(
    collection: TemplateCollection, expected_revision: int
) -> dict[str, object]:
    """校验并序列化用户模板；``expected_revision`` 与集合修订不一致即冲突。

    冲突时本地编辑（传入的 collection）原样保留：调用方刷新服务端模板修订
    后可按新修订重试或另存为新模板。内置默认模板不可替换。
    """
    if collection.unknown_schema_preserved:
        # 服务端模板设置 schema 高于当前版本：按 v1 负载保存会静默销毁
        # 原始 JSON。冲突语义（SPEC-DM-012 §11）保留本地编辑，等待升级。
        raise sheet_catalog_error(
            "SHEET_CATALOG_TEMPLATE_CONFLICT",
            {},
            message=(
                "服务端模板设置 schema 高于当前版本，原 JSON 已保留，"
                "请升级程序后再保存或另存为新模板"
            ),
        )
    if collection.revision != expected_revision:
        raise sheet_catalog_error(
            "SHEET_CATALOG_TEMPLATE_CONFLICT",
            {
                "expected_revision": expected_revision,
                "current_revision": collection.revision,
            },
        )
    if collection.builtin != DEFAULT_TEMPLATE:
        raise ValueError(
            "SHEET_CATALOG_BUILTIN_IMMUTABLE: 内置默认模板不可修改或删除"
        )
    if len(collection.user_templates) > MAX_USER_TEMPLATES:
        raise _limit(
            "user_templates", MAX_USER_TEMPLATES, len(collection.user_templates)
        )
    seen_names: dict[str, str] = {_BUILTIN_TEMPLATE_NAME.casefold(): _BUILTIN_TEMPLATE_NAME}
    # PLAN-DM-024 Task 3 / MEMO-DM-031 F5：``template_id`` 是用户模板身份权威，
    # 重复 UUID 必须在序列化前拒绝——否则 ``delete_template`` 按 ID 过滤会一次
    # 带走两条名字不同但同 ID 的模板。
    seen_ids: set[uuid.UUID] = set()
    for template in collection.user_templates:
        if template.template_id is None:
            raise ValueError(
                "SHEET_CATALOG_TEMPLATE_ID_REQUIRED: 保存前必须分配模板 UUID"
            )
        if template.template_id in seen_ids:
            raise ValueError(
                "SHEET_CATALOG_TEMPLATE_ID_DUPLICATE: "
                f"重复的用户模板 UUID（{template.template_id}）"
            )
        seen_ids.add(template.template_id)
        validate_template(template)
        folded = template.name.casefold()
        if folded in seen_names:
            raise sheet_catalog_error(
                "SHEET_CATALOG_COLUMN_DUPLICATE", {"header": template.name}
            )
        seen_names[folded] = template.name
    return {
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "user_templates": [
            _template_to_json(template) for template in collection.user_templates
        ],
    }


def _log_skip(reason: str) -> None:
    # 稳定诊断：只含稳定标识与原因码，不含模板名等用户数据。
    logger.warning("SHEET_CATALOG_TEMPLATES_SKIPPED: %s", reason)


def load_templates(settings: VersionedJson | None) -> TemplateCollection:
    """合并代码常量内置模板与 settings JSON；坏条目隔离，不阻止宿主启动。"""
    if settings is None:
        return TemplateCollection(0, DEFAULT_TEMPLATE, ())
    if settings.schema_version != TEMPLATE_SCHEMA_VERSION:
        # 未知高 schema：原 JSON 原样保留（只读不重写），输出稳定诊断，
        # 不加载为可编辑状态。
        logger.warning(
            "SHEET_CATALOG_SETTINGS_SCHEMA_UNSUPPORTED: schema_version=%s",
            settings.schema_version,
        )
        return TemplateCollection(
            settings.revision, DEFAULT_TEMPLATE, (), unknown_schema_preserved=True
        )
    entries = settings.value.get("user_templates")
    if not isinstance(entries, list):
        _log_skip("user_templates_not_a_list")
        return TemplateCollection(settings.revision, DEFAULT_TEMPLATE, ())
    templates: list[SheetCatalogTemplate] = []
    # 与内置默认模板同名的用户模板不加载：否则之后的任何一次保存都会因
    # 名字冲突被拒，卡死全部模板保存（save 路径把内置名预置进 seen_names）。
    seen_names: set[str] = {_BUILTIN_TEMPLATE_NAME.casefold()}
    for entry in entries:
        if len(templates) >= MAX_USER_TEMPLATES:
            _log_skip("user_templates_over_limit")
            break
        try:
            validated = validate_template(_template_from_json(entry))
        except (KeyError, TypeError, ValueError, SheetCatalogError):
            _log_skip("template_entry_invalid")
            continue
        template = validated.template
        folded = template.name.casefold()
        if folded in seen_names:
            _log_skip("template_name_duplicate")
            continue
        seen_names.add(folded)
        templates.append(template)
    return TemplateCollection(settings.revision, DEFAULT_TEMPLATE, tuple(templates))


def delete_template(
    collection: TemplateCollection, template_id: uuid.UUID
) -> TemplateCollection:
    """删除当前用户模板；内置默认模板原样保留，选择层据此回退默认模板。"""
    remaining = tuple(
        template
        for template in collection.user_templates
        if template.template_id != template_id
    )
    if len(remaining) == len(collection.user_templates):
        raise ValueError(
            f"SHEET_CATALOG_TEMPLATE_NOT_FOUND: {template_id}"
        )
    return TemplateCollection(collection.revision, collection.builtin, remaining)
