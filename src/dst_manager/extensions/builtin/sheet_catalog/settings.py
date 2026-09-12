"""图纸目录扩展设置 Provider（PLAN-DM-025 Task 2 / SPEC-DM-012 §6.4、§8）。

Provider 是目录设置语义的唯一权威（ARCH-DM-006 §8.1）：默认零值、Schema
1→2 迁移、保存前校验与规范化、把持久值解析为有效配置。设置 ``value_json``
只保存用户模板和用户显式过滤词；内置默认模板来自随包代码常量，不写数据库。

v1 → v2 只保留既有 ``user_templates``，缺失的 ``excluded_title_keywords``
不写回显式覆盖（默认值不因迁移成为用户配置）；规范化结果为空时该字段从持久值
移除，有效值仍返回空数组。过滤关键词规范化与图名排除是纯函数，预览与执行
（PLAN-DM-025 Task 4）共用同一份语义：对图名与关键词分别 ``casefold()`` 后做
字面子串匹配，关键词之间为 OR，不支持通配符、正则或转义逗号。

Provider 不依赖基础设施：它只接收/返回纯 JSON 结构，由
:class:`~dst_manager.application.extensions.settings.ExtensionSettingsService`
读取持久值并编排迁移与并发。
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from dst_manager.application.extensions.settings import ExtensionSettingsError
from dst_manager.extensions.builtin.sheet_catalog.errors import (
    SHEET_CATALOG_MESSAGE_KEYS,
    SheetCatalogError,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import (
    CATALOG_SETTINGS_SCHEMA_VERSION,
    DEFAULT_TEMPLATE,
    TemplateCollection,
    parse_user_templates,
    save_templates,
    template_to_json,
)
from dst_manager.extensions.settings import SettingsFieldSpec

__all__ = [
    "EXCLUDED_TITLE_KEYWORDS_FIELD",
    "MAX_EXCLUDED_TITLE_KEYWORDS",
    "MAX_EXCLUDED_TITLE_KEYWORD_CHARS",
    "SHEET_CATALOG_SETTINGS_PROVIDER",
    "SheetCatalogSettingsProvider",
    "normalize_excluded_title_keywords",
    "title_matches_exclusion",
]

#: SPEC-DM-012 §6.4：最多 50 项、单项最多 100 字符；超限拒绝保存、绝不截断。
MAX_EXCLUDED_TITLE_KEYWORDS = 50
MAX_EXCLUDED_TITLE_KEYWORD_CHARS = 100

#: 过滤关键词字段名：文本错误与 API 字段定位共用同一拼写。
EXCLUDED_TITLE_KEYWORDS_FIELD = "excluded_title_keywords"

#: SPEC-DM-012 §6.4：输入同时接受半角逗号与全角逗号。
_KEYWORD_SEPARATORS = re.compile("[,，]")

#: 目录错误码 → HTTP 状态（沿用既有映射口径：状态冲突 409、负载校验 422、
#: 宿主环境失败 503）；Provider 业务码自身即稳定错误码，只补状态与文案键。
_CATALOG_ERROR_STATUS: dict[str, int] = {
    "SHEET_CATALOG_TEMPLATE_CONFLICT": 409,
    "SHEET_CATALOG_COLUMN_DUPLICATE": 409,
    "SHEET_CATALOG_TEMPLATE_LIMIT": 422,
    "SHEET_CATALOG_EXPRESSION_INVALID": 422,
    "SHEET_CATALOG_FIELD_UNDEFINED": 422,
    "SHEET_CATALOG_VALUE_MISSING": 422,
    "SHEET_CATALOG_XLSX_INVALID": 503,
}


def normalize_excluded_title_keywords(value: object) -> tuple[str, ...]:
    """规范化过滤关键词：两种逗号拆分 → trim → 忽略空项 → casefold 去重。

    保留第一次出现的原文与顺序（``草图， TEMP,,作废,temp`` → 草图和 TEMP 与
    作废），故持久值是用户可见的拼写而不是折叠后的形态。文本形态按逗号拆分；
    数组形态是已规范化的持久形态，逐项去空与去重后不再二次拆分。``None``
    与空文本等价于不过滤。无法解释的形态抛 ``TypeError``，由设置服务契约化。
    """
    if value is None:
        return ()
    if isinstance(value, str):
        items: Sequence[object] = _KEYWORD_SEPARATORS.split(value)
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        raise TypeError(
            "SHEET_CATALOG_EXCLUDED_TITLE_KEYWORDS_INVALID: "
            f"{EXCLUDED_TITLE_KEYWORDS_FIELD} 必须是文本或字符串数组"
        )
    keywords: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise TypeError(
                "SHEET_CATALOG_EXCLUDED_TITLE_KEYWORDS_INVALID: "
                f"{EXCLUDED_TITLE_KEYWORDS_FIELD} 的每一项都必须是字符串"
            )
        keyword = item.strip()
        if not keyword:
            continue
        folded = keyword.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        keywords.append(keyword)
    return tuple(keywords)


def title_matches_exclusion(title: str, keywords: Sequence[str]) -> bool:
    """图名是否命中任一过滤关键词：``casefold()`` 后字面子串匹配，关键词为 OR。

    匹配对象是固有字段 ``SheetSnapshot.title``（界面与目录中的“图名”）。不做
    通配符、正则、转义或表达式求值：``草*`` 只按字面匹配 ``草*``。
    """
    if not keywords:
        return False
    folded = title.casefold()
    return any(keyword.casefold() in folded for keyword in keywords)


def _keyword_limit_error(kind: str, limit: int, actual: int) -> ExtensionSettingsError:
    """字段级设置无效错误：定位到 ``excluded_title_keywords``，不截断输入。"""
    return ExtensionSettingsError(
        "EXTENSION_SETTINGS_INVALID",
        f"超出输出图纸过滤限制 {kind}：{actual}/{limit}",
        status_code=422,
        params={
            "field": EXCLUDED_TITLE_KEYWORDS_FIELD,
            "kind": kind,
            "limit": limit,
            "actual": actual,
        },
    )


def _validated_excluded_title_keywords(value: object) -> tuple[str, ...]:
    """规范化并强制关键词限制值（50 项 / 单项 100 字符）。"""
    keywords = normalize_excluded_title_keywords(value)
    if len(keywords) > MAX_EXCLUDED_TITLE_KEYWORDS:
        raise _keyword_limit_error("count", MAX_EXCLUDED_TITLE_KEYWORDS, len(keywords))
    for keyword in keywords:
        if len(keyword) > MAX_EXCLUDED_TITLE_KEYWORD_CHARS:
            raise _keyword_limit_error(
                "length", MAX_EXCLUDED_TITLE_KEYWORD_CHARS, len(keyword)
            )
    return keywords


def _settings_error(error: SheetCatalogError) -> ExtensionSettingsError:
    """目录错误码 → 设置错误契约：保留稳定 code/params 与目录域文案键。"""
    return ExtensionSettingsError(
        error.code,
        str(error),
        status_code=_CATALOG_ERROR_STATUS.get(error.code, 503),
        params=dict(error.params),
        key_override=SHEET_CATALOG_MESSAGE_KEYS[error.code],
    )


class SheetCatalogSettingsProvider:
    """图纸目录设置语义：Schema v2、目录模板校验与过滤关键词规范化。

    ``field_definitions`` 为空：目录设置由 Manifest 声明的 ``custom`` 专属
    组件呈现，宿主不生成表单字段，因此没有 Provider 侧的可生成字段元数据；
    过滤关键词的默认值与约束仍由本 Provider 的 ``validate_and_normalize``
    强制（默认持久零值 ``{}`` 即“无用户模板、无显式过滤词”）。
    """

    extension_id = "dst-manager.sheet-catalog"
    schema_version = CATALOG_SETTINGS_SCHEMA_VERSION
    field_definitions: tuple[SettingsFieldSpec, ...] = ()

    # ---------------------------------------------------------------- 零值

    def default_value(self) -> dict[str, object]:
        """默认持久零值：内置模板来自代码常量，用户模板与过滤词均为空。"""
        return {}

    # ---------------------------------------------------------------- 迁移

    def migrate(
        self, stored_schema_version: int, value: dict[str, object]
    ) -> dict[str, object]:
        """v1 → v2：保留既有 ``user_templates``，不写入过滤词显式覆盖。"""
        if stored_schema_version == 1:
            return {
                "schema_version": CATALOG_SETTINGS_SCHEMA_VERSION,
                "user_templates": value.get("user_templates"),
            }
        raise ExtensionSettingsError(
            "EXTENSION_SETTINGS_INVALID",
            f"无法迁移的设置 schema 版本：{stored_schema_version}",
            status_code=422,
            params={
                "extension_id": self.extension_id,
                "settings_schema": stored_schema_version,
            },
        )

    # ---------------------------------------------------------------- 校验

    def validate_and_normalize(self, value: dict[str, object]) -> dict[str, object]:
        """校验并规范化客户端负载，返回可持久化的规范形态。

        模板限制值、名称/UUID 唯一与内置不可变由 ``save_templates`` 强制；
        过滤关键词超限定位到 ``excluded_title_keywords``，绝不截断。规范化后
        关键词为空则从持久值移除该字段（有效值仍返回空数组）。

        结构/类型不合约负载（缺 UUID、条目不是对象等）与目录域错误都转为
        :class:`ExtensionSettingsError`：调用方（设置服务与 API）只看到一个
        稳定错误契约，稳定诊断前缀保留在 ``message`` 里。
        """
        try:
            keywords = _validated_excluded_title_keywords(
                value.get(EXCLUDED_TITLE_KEYWORDS_FIELD)
            )
            templates = parse_user_templates(value.get("user_templates"))
            collection = TemplateCollection(
                revision=0, builtin=DEFAULT_TEMPLATE, user_templates=templates
            )
            payload = save_templates(collection)
        except SheetCatalogError as exc:
            raise _settings_error(exc) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtensionSettingsError(
                "EXTENSION_SETTINGS_INVALID",
                str(exc),
                status_code=422,
                params={"extension_id": self.extension_id},
            ) from exc
        if keywords:
            payload[EXCLUDED_TITLE_KEYWORDS_FIELD] = list(keywords)
        return payload

    # ---------------------------------------------------------------- 解析

    def resolve(self, value: dict[str, object]) -> dict[str, object]:
        """把规范持久值解析为有效配置：代码内置模板 + 用户模板 + 过滤词。"""
        templates = parse_user_templates(value.get("user_templates"))
        keywords = normalize_excluded_title_keywords(
            value.get(EXCLUDED_TITLE_KEYWORDS_FIELD)
        )
        return {
            "builtin_template": template_to_json(DEFAULT_TEMPLATE),
            "user_templates": [template_to_json(template) for template in templates],
            EXCLUDED_TITLE_KEYWORDS_FIELD: list(keywords),
        }


#: 固定索引引用的单例：宿主绝不从清单或配置动态构造 Provider。
SHEET_CATALOG_SETTINGS_PROVIDER = SheetCatalogSettingsProvider()
