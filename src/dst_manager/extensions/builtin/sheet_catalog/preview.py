"""图纸目录预览构建、兼容性诊断与确定性摘要（PLAN-DM-020 Task 6 / SPEC-DM-012 §8.1、PLAN-DM-025 Task 4）。

预览是纯函数投影：输入冻结 :class:`~dst_manager.extensions.snapshots.WorkspaceSnapshot`
与模板，输出规范化模板、字段目录、阻断错误、非阻断警告、前 20 行求值结果、
总图纸数、``preview_digest`` 与 ``executable``。

规则（SPEC §8.1/§11）：

- 模板限制、表达式语法与字段定义全部通过才 ``executable=True``；任何阻断
  错误都不产出半截行数据（``rows=()``），不截断、不静默丢弃；
- 缺值（``SHEET_CATALOG_VALUE_MISSING``）是允许执行的 warning：按字段聚合
  受影响图纸数，**诊断与日志绝不记录属性值**；
- **输出图纸过滤先于求值与缺值统计**（SPEC-DM-012 §6.4 / Task 4）：被排除的
  图纸不进入 ``rows``、不计缺值 warning；``total_rows`` 是过滤后的实际输出
  行数，``filtered_rows`` 是被排除数。匹配语义只来自
  :func:`~dst_manager.extensions.builtin.sheet_catalog.settings.title_matches_exclusion`
  （与 Provider 规范化后的关键词同源），预览与导出不会各算一份；
- ``preview_digest`` 覆盖 workspace、修订、模板 schema、按序列的规范列
  （ID/表头/规范化 token）、扩展标识（Ruling-4：必须含 ``extension_id``）、
  扩展版本、动作 ID，以及设置 Schema/修订/摘要（§11：每次调用绑定不可变
  设置快照）；canonical JSON 固定键 + 紧凑分隔符后取 SHA-256，相同输入摘要
  逐字节稳定。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from dst_manager.extensions.builtin.sheet_catalog.errors import (
    SheetCatalogError,
    SheetCatalogErrorCode,
    sheet_catalog_error,
)
from dst_manager.extensions.builtin.sheet_catalog.expressions import (
    BoundExpression,
    BoundFieldToken,
    LiteralToken,
    bind_expression,
    evaluate_expression,
)
from dst_manager.extensions.builtin.sheet_catalog.settings import (
    title_matches_exclusion,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import (
    SheetCatalogTemplate,
    TemplateColumn,
    validate_template,
)
from dst_manager.extensions.snapshots import (
    FieldCatalog,
    SnapshotPropertyScope,
    WorkspaceSnapshot,
    build_field_catalog,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dst_manager.extensions.snapshots import SheetSnapshot

__all__ = [
    "DIGEST_KEY",
    "PREFERENCE_SAVE_FAILED_CODE",
    "PREVIEW_ROW_LIMIT",
    "DigestColumn",
    "PreviewDiagnosticCode",
    "SheetCatalogDiagnostic",
    "SheetCatalogPreview",
    "SheetCatalogPreviewRequest",
    "build_preview",
    "preference_save_failed_warning",
    "preview_digest",
    "projected_sheets",
]

#: 普通页面预览最多回传 20 行；总图纸数始终全量统计。
PREVIEW_ROW_LIMIT = 20

#: Ruling-4：摘要输入必须包含扩展 ID；工厂按此常量传入。
DIGEST_KEY = "extension_id"

#: 宿主偏好保存失败的稳定诊断码（ARCH-DM-006 §8.2 best-effort：可诊断、
#: 不阻断当前预览）。不属于 SPEC §11 目录错误词汇，属宿主平台诊断。
PREFERENCE_SAVE_FAILED_CODE = "EXTENSION_PREFERENCE_SAVE_FAILED"

#: 偏好失败 warning 的稳定文案键（Task 10 前端 extensions 域承接）。
_PREFERENCE_SAVE_FAILED_KEY = "errors.extension.preferenceSaveFailed"

PreviewDiagnosticCode = SheetCatalogErrorCode | Literal[
    "EXTENSION_PREFERENCE_SAVE_FAILED"
]


@dataclass(frozen=True, slots=True)
class SheetCatalogPreviewRequest:
    workspace_id: str
    base_revision_id: str
    template: SheetCatalogTemplate


@dataclass(frozen=True, slots=True)
class DigestColumn:
    """摘要输入的规范化列投影：列 ID、表头与规范化 token 序列。

    token 形态：``("literal", 文本)`` 或
    ``("field", scope, canonical_name, "builtin"|"custom")``；字段带数字格式码
    时后接 ``("format", "0" * width)``，使宽度变化同样改变摘要（SPEC §5.2）。
    """

    column_id: str
    header: str
    tokens: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class SheetCatalogDiagnostic:
    """预览诊断：稳定 code/message_key/params，定位到列与字符位置。"""

    code: PreviewDiagnosticCode
    message_key: str
    params: dict[str, str | int]
    column_id: UUID | None
    source_position: int | None

    @classmethod
    def from_error(
        cls, error: SheetCatalogError, *, column_id: UUID | None = None
    ) -> SheetCatalogDiagnostic:
        """把 ``SheetCatalogError`` 转成预览诊断（params 只保留 str/int）。"""
        params = {
            key: value for key, value in error.params.items() if isinstance(value, (str, int))
        }
        source = params.get("source_start")
        return cls(
            code=error.code,  # type: ignore[arg-type]
            message_key=error.message_key,
            params=params,
            column_id=column_id,
            source_position=source if isinstance(source, int) else None,
        )


@dataclass(frozen=True, slots=True)
class SheetCatalogPreview:
    """预览投影（行/计数/诊断/摘要）与绑定的设置快照修订。

    ``rows`` 只包含通过输出图纸过滤的图纸（最多 ``PREVIEW_ROW_LIMIT`` 条）；
    ``total_rows`` 是过滤后的实际输出行数（也是候选 XLSX 的数据行数），
    ``filtered_rows`` 是被排除图纸数，二者之和等于快照中的图纸总数。
    """

    normalized_template: SheetCatalogTemplate
    field_catalog: FieldCatalog
    errors: tuple[SheetCatalogDiagnostic, ...]
    warnings: tuple[SheetCatalogDiagnostic, ...]
    rows: tuple[tuple[str, ...], ...]
    total_rows: int
    filtered_rows: int
    settings_revision: int
    preview_digest: str
    executable: bool


def projected_sheets(
    snapshot: WorkspaceSnapshot, excluded_title_keywords: Sequence[str]
) -> tuple[SheetSnapshot, ...]:
    """输出图纸过滤投影：按图名排除命中关键词的图纸（Casefold 字面 OR 匹配）。

    预览构建与候选导出的行投影都经本函数，保证“预览计数”与“导出内容”同源
    （ARCH-DM-006 §11 风险节：过滤必须先于求值且两路径复用同一纯函数）。
    """
    if not excluded_title_keywords:
        return snapshot.sheets
    return tuple(
        sheet
        for sheet in snapshot.sheets
        if not title_matches_exclusion(sheet.title, excluded_title_keywords)
    )


def preference_save_failed_warning(template_id: str) -> SheetCatalogDiagnostic:
    """宿主工作区偏好保存失败的非阻断 warning（可诊断、不升级为动作失败）。"""
    return SheetCatalogDiagnostic(
        code=PREFERENCE_SAVE_FAILED_CODE,
        message_key=_PREFERENCE_SAVE_FAILED_KEY,
        params={"template_id": template_id},
        column_id=None,
        source_position=None,
    )


# ---------------------------------------------------------------------------
# 摘要：canonical JSON（固定键 + 紧凑分隔符）后 SHA-256
# ---------------------------------------------------------------------------


def _digest_payload(
    workspace_id: str,
    revision_id: str,
    template_schema: int,
    normalized_columns: Sequence[DigestColumn],
    extension_version: str,
    action_id: str,
    extension_id: str,
    settings_schema_version: int,
    settings_revision: int,
    settings_digest: str,
) -> dict[str, object]:
    return {
        "action_id": action_id,
        "columns": [
            {
                "column_id": column.column_id,
                "header": column.header,
                "tokens": [list(token) for token in column.tokens],
            }
            for column in normalized_columns
        ],
        DIGEST_KEY: extension_id,
        "extension_version": extension_version,
        "revision_id": revision_id,
        "schema_version": template_schema,
        # 设置绑定（§11）：Schema 版本、乐观并发修订与规范值摘要三者都参与，
        # 任何一项变化都必须使旧预览摘要失效。
        "settings_digest": settings_digest,
        "settings_revision": settings_revision,
        "settings_schema_version": settings_schema_version,
        "workspace_id": workspace_id,
    }


def preview_digest(
    workspace_id: str,
    revision_id: str,
    template_schema: int,
    normalized_columns: Sequence[DigestColumn],
    extension_version: str,
    action_id: str,
    *,
    extension_id: str,
    settings_schema_version: int,
    settings_revision: int,
    settings_digest: str,
) -> str:
    """确定性预览摘要：对全部绑定输入的 canonical JSON 取 SHA-256。"""
    payload = _digest_payload(
        workspace_id,
        revision_id,
        template_schema,
        normalized_columns,
        extension_version,
        action_id,
        extension_id,
        settings_schema_version,
        settings_revision,
        settings_digest,
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _digest_token(token: LiteralToken | BoundFieldToken) -> tuple[str, ...]:
    if isinstance(token, LiteralToken):
        return ("literal", token.value)
    base = (
        "field",
        token.scope,
        token.canonical_name,
        "builtin" if token.builtin else "custom",
    )
    if token.format_width is None:
        return base
    return (*base, "format", "0" * token.format_width)


def _digest_columns(
    columns: tuple[TemplateColumn, ...],
    expressions: Sequence[BoundExpression | None],
) -> tuple[DigestColumn, ...]:
    """规范化列投影：已绑定列用规范化 token，未绑定列退化为表达式源标记。"""
    digest: list[DigestColumn] = []
    for column, expression in zip(columns, expressions):
        tokens = (
            tuple(_digest_token(token) for token in expression.tokens)
            if expression is not None
            else (("source", column.expression),)
        )
        digest.append(DigestColumn(str(column.column_id), column.header, tokens))
    return tuple(digest)


# ---------------------------------------------------------------------------
# 预览构建：校验 → 逐列绑定 → 一次性遍历图纸求值与缺值统计
# ---------------------------------------------------------------------------


def _raw_value(
    token: BoundFieldToken,
    sheetset: SnapshotPropertyScope,
    sheet: SheetSnapshot,
) -> str:
    """取字段原始值用于缺值判定；不进入任何诊断或日志。"""
    if token.scope == "sheetset":
        properties = sheetset.custom_properties
    elif token.builtin:
        return getattr(sheet, token.canonical_name, "")
    else:
        properties = sheet.custom_properties
    for prop in properties:
        if prop.canonical_name == token.canonical_name:
            return prop.value
    return ""


def _column_for_header(
    template: SheetCatalogTemplate, header: object
) -> UUID | None:
    """按错误参数里的 column_header 回定位列（校验期表头唯一，可安全匹配）。"""
    if not isinstance(header, str):
        return None
    for column in template.columns:
        if column.header == header:
            return column.column_id
    return None


def build_preview(
    snapshot: WorkspaceSnapshot,
    template: SheetCatalogTemplate,
    *,
    extension_id: str,
    extension_version: str,
    action_id: str,
    settings_schema_version: int,
    settings_revision: int,
    settings_digest: str,
    excluded_title_keywords: Sequence[str] = (),
) -> SheetCatalogPreview:
    """对冻结快照构建图纸目录预览（纯函数，不触碰 DST/数据库/文件系统）。

    ``excluded_title_keywords`` 与设置三要素都来自调用方注入的同一冻结设置
    快照（宿主运行时在创建上下文前取得）：预览不自行读 Store，也不缓存设置。
    """
    errors: list[SheetCatalogDiagnostic] = []
    field_catalog = build_field_catalog(snapshot)
    # 过滤先于求值与缺值统计：被排除图纸不产生行、也不参与缺值计数
    sheets = projected_sheets(snapshot, excluded_title_keywords)

    validated = None
    try:
        validated = validate_template(template)
    except SheetCatalogError as error:
        # 校验期错误（重复列/超限/语法）：语法错误已带 column_header，可回定位列；
        # 重复列发生在解析之前，列定位保持 None。
        column_id = _column_for_header(template, error.params.get("column_header"))
        errors.append(SheetCatalogDiagnostic.from_error(error, column_id=column_id))

    expressions: list[BoundExpression | None] = []
    if validated is not None:
        for column, tokens in zip(validated.template.columns, validated.parsed_columns):
            try:
                expressions.append(bind_expression(tokens, field_catalog))
            except SheetCatalogError as error:
                # 缺定义等绑定阻断：定位到列，不产出半截行。
                errors.append(SheetCatalogDiagnostic.from_error(error, column_id=column.column_id))
                expressions = [None] * len(validated.template.columns)
                break
    else:
        expressions = [None] * len(template.columns)

    rows: list[tuple[str, ...]] = []
    missing_counts: dict[tuple[str, str], int] = {}
    if validated is not None and all(expression is not None for expression in expressions):
        for sheet in sheets:
            row: list[str] = []
            # 逐图纸有序去重：同一字段在同一张图纸只计一次缺值。
            sheet_missing: list[tuple[str, str]] = []
            for expression in expressions:
                assert expression is not None
                row.append(evaluate_expression(expression, snapshot.sheetset, sheet))
                for token in expression.tokens:
                    if isinstance(token, BoundFieldToken):
                        key = (token.scope, token.canonical_name)
                        if (
                            key not in sheet_missing
                            and _raw_value(token, snapshot.sheetset, sheet) == ""
                        ):
                            sheet_missing.append(key)
            for key in sheet_missing:
                missing_counts[key] = missing_counts.get(key, 0) + 1
            if len(rows) < PREVIEW_ROW_LIMIT:
                rows.append(tuple(row))

    warnings = tuple(
        SheetCatalogDiagnostic.from_error(
            sheet_catalog_error(
                "SHEET_CATALOG_VALUE_MISSING",
                {"scope": scope, "name": name, "sheet_count": count},
            )
        )
        for (scope, name), count in missing_counts.items()
    )

    digest = preview_digest(
        snapshot.workspace_id,
        snapshot.revision_id,
        template.schema_version,
        _digest_columns(
            validated.template.columns if validated is not None else template.columns,
            expressions,
        ),
        extension_version,
        action_id,
        extension_id=extension_id,
        settings_schema_version=settings_schema_version,
        settings_revision=settings_revision,
        settings_digest=settings_digest,
    )
    return SheetCatalogPreview(
        normalized_template=template,
        field_catalog=field_catalog,
        errors=tuple(errors),
        warnings=warnings,
        rows=tuple(rows),
        total_rows=len(sheets),
        filtered_rows=len(snapshot.sheets) - len(sheets),
        settings_revision=settings_revision,
        preview_digest=digest,
        executable=not errors,
    )
