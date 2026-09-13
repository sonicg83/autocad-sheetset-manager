"""不编号图纸关键字：解析、规范化与子集标题匹配（纯函数，无 I/O）。

语义与图纸目录扩展的「输出图纸过滤」一致（ARCH-DM-001 领域层约束：本模块
只依赖标准库，不触达 FastAPI / SQLAlchemy / 文件系统 / AutoCAD 进程）：

* 半角逗号与全角逗号都是分隔符；
* 逐项 trim、忽略空项、按 ``casefold()`` 去重并保留首次出现的原文与顺序；
* 匹配为 casefold 后的**字面子串**匹配，多关键字之间是 OR；
* 数量与单项长度上限只在设置保存事务里强制（拒绝保存、绝不截断）。

用途见 SPEC-DM-014：子集可编辑标题命中任关键字时，该子集判为「不编号子集」，
其全部图纸图号固定为 0 填充（如 ``000``），且不消耗全局序号。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

__all__ = [
    "MAX_UNNUMBERED_KEYWORDS",
    "MAX_UNNUMBERED_KEYWORD_CHARS",
    "KeywordLimitError",
    "format_keywords",
    "normalize_keywords",
    "parse_keywords",
    "title_matches_keywords",
]

_KEYWORD_SEPARATORS = re.compile("[,，]")

# 上限与图纸目录扩展的输出图纸过滤保持一致（50 项 / 单项 100 字符）
MAX_UNNUMBERED_KEYWORDS = 50
MAX_UNNUMBERED_KEYWORD_CHARS = 100


class KeywordLimitError(ValueError):
    """关键字数量或单项长度超限（保存事务据此产出 422 逐字段错误）。"""

    def __init__(self, kind: Literal["count", "length"], limit: int, actual: int) -> None:
        super().__init__(f"不编号关键字{'数量' if kind == 'count' else '长度'}超限：{actual} > {limit}")
        self.code = "KEYWORD_LIMIT"
        self.kind = kind
        self.limit = limit
        self.actual = actual


def normalize_keywords(value: object) -> tuple[str, ...]:
    """把设置取值规整为关键字元组。

    接受字符串（半角/全角逗号分隔）或字符串序列；``None`` 与空串视作空清单。
    参数类型非法时抛 :class:`TypeError`，由调用方决定降级或报错。
    """
    if value is None:
        return ()
    if isinstance(value, str):
        items: tuple[object, ...] = tuple(_KEYWORD_SEPARATORS.split(value))
    elif isinstance(value, (list, tuple)):
        items = tuple(value)
    else:
        raise TypeError(f"不编号关键字必须是字符串或字符串序列：{type(value).__name__}")
    keywords: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise TypeError("不编号关键字每一项都必须是字符串")
        keyword = item.strip()
        if not keyword:
            continue
        folded = keyword.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        keywords.append(keyword)
    return tuple(keywords)


def format_keywords(keywords: Iterable[str]) -> str:
    """把关键字序列格式化为持久形态（半角逗号分隔，不含空白）。"""
    return ",".join(keywords)


def parse_keywords(value: object) -> tuple[str, ...]:
    """规范化并强制数量/单项长度上限，供设置保存事务调用。"""
    keywords = normalize_keywords(value)
    if len(keywords) > MAX_UNNUMBERED_KEYWORDS:
        raise KeywordLimitError("count", MAX_UNNUMBERED_KEYWORDS, len(keywords))
    for keyword in keywords:
        if len(keyword) > MAX_UNNUMBERED_KEYWORD_CHARS:
            raise KeywordLimitError("length", MAX_UNNUMBERED_KEYWORD_CHARS, len(keyword))
    return keywords


def title_matches_keywords(title: str, keywords: Iterable[str]) -> bool:
    """子集标题是否命中任一关键字（casefold 后字面子串匹配，多关键字 OR）。"""
    folded = title.casefold()
    return any(keyword.casefold() in folded for keyword in keywords)
