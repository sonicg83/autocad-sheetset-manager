"""图纸目录受限表达式：解析、绑定与求值（PLAN-DM-020 Task 5 / SPEC-DM-012 §5）。

语法（SPEC-DM-012 §5.1）::

    expression      := (literal | field_reference | escaped_brace)*
    field_reference := "{" scope ("." identifier | "[" json_string "]") "}"
    scope           := "sheetset" | "sheet"
    escaped_brace   := "{{" | "}}"

实现是手写有限状态扫描器加受限 JSON 字符串解码：不引入通用模板引擎、
不支持函数/条件/运算/过滤器，任何输入只会产出结构化 token 或结构化错误，
绝不执行代码。``FieldToken.quoted`` 记录方括号 JSON 形式，绑定阶段据此
落实保留名裁决：点号形式的固有字段优先，与固有字段同名的自定义保留属性
只能经方括号形式寻址（SPEC-DM-012 §4.1/§4.2）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from dst_manager.extensions.builtin.sheet_catalog.errors import sheet_catalog_error
from dst_manager.extensions.snapshots import SHEET_BUILTIN_FIELDS

if TYPE_CHECKING:
    from dst_manager.extensions.snapshots import (
        FieldCatalog,
        SheetSnapshot,
        SnapshotPropertyScope,
    )

__all__ = [
    "BoundExpression",
    "BoundFieldToken",
    "ExpressionToken",
    "FieldToken",
    "LiteralToken",
    "bind_expression",
    "evaluate_expression",
    "field_reference",
    "parse_expression",
]


@dataclass(frozen=True, slots=True)
class LiteralToken:
    value: str


@dataclass(frozen=True, slots=True)
class FieldToken:
    scope: Literal["sheetset", "sheet"]
    name: str
    source_start: int
    #: 是否以 ``["..."]`` JSON 字符串形式书写（决定绑定阶段的保留名裁决）。
    quoted: bool = False


ExpressionToken = LiteralToken | FieldToken


@dataclass(frozen=True, slots=True)
class BoundFieldToken:
    scope: Literal["sheetset", "sheet"]
    canonical_name: str
    builtin: bool


@dataclass(frozen=True, slots=True)
class BoundExpression:
    tokens: tuple[LiteralToken | BoundFieldToken, ...]


_SCOPES = ("sheetset", "sheet")
_BUILTIN_CASEFOLD = frozenset(name.casefold() for name in SHEET_BUILTIN_FIELDS)
#: 点号形式只接受可作为单一标识符读取的名称；其余字符必须走方括号形式。
_DOT_NAME_FORBIDDEN = frozenset(' \t\r\n.[]{}"\'(),;:=\\')
_JSON_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _invalid(source_start: int, *, column_header: str | None = None):
    return sheet_catalog_error(
        "SHEET_CATALOG_EXPRESSION_INVALID",
        {"source_start": source_start, **({"column_header": column_header} if column_header else {})},
    )


def parse_expression(source: str) -> tuple[ExpressionToken, ...]:
    """把表达式源文本扫描为受限 token 序列；语法错误带 0-based 字符位置。"""
    tokens: list[ExpressionToken] = []
    literal: list[str] = []
    index = 0
    length = len(source)
    if length == 0:
        raise _invalid(0)

    def flush() -> None:
        if literal:
            tokens.append(LiteralToken("".join(literal)))
            literal.clear()

    while index < length:
        char = source[index]
        if char == "{":
            if index + 1 < length and source[index + 1] == "{":
                literal.append("{")
                index += 2
                continue
            flush()
            token, index = _parse_field(source, index)
            tokens.append(token)
        elif char == "}":
            if index + 1 < length and source[index + 1] == "}":
                literal.append("}")
                index += 2
                continue
            raise _invalid(index)
        else:
            literal.append(char)
            index += 1
    flush()
    return tuple(tokens)


def _parse_field(source: str, start: int) -> tuple[FieldToken, int]:
    """扫描 ``{`` 起始的字段引用，返回 token 与引用结束后的下一位置。"""
    index = start + 1
    scope_start = index
    while index < len(source) and source[index] not in ".[{":
        index += 1
    if index >= len(source) or source[index] == "{":
        raise _invalid(start)
    scope = source[scope_start:index]
    if scope not in _SCOPES:
        raise _invalid(start)
    if source[index] == "[":
        # 方括号形式在内部已消费到 `}` 之后的位置，直接返回。
        name, index = _parse_quoted_name(source, index + 1, start)
        return FieldToken(scope, name, start, quoted=True), index
    if source[index] == ".":
        name, index = _parse_dot_name(source, index + 1)
        quoted = False
    else:  # "}": 引用缺少名称部分。
        raise _invalid(start)
    if index >= len(source) or source[index] != "}":
        raise _invalid(start)
    return FieldToken(scope, name, start, quoted=quoted), index + 1


def _parse_dot_name(source: str, start: int) -> tuple[str, int]:
    index = start
    length = len(source)
    while index < length and source[index] != "}":
        if source[index] in _DOT_NAME_FORBIDDEN:
            raise _invalid(index)
        index += 1
    name = source[start:index]
    if not name:
        raise _invalid(start)
    return name, index


def _parse_quoted_name(source: str, start: int, field_start: int) -> tuple[str, int]:
    """扫描 ``["..."]``：手写状态机校验，转义按 JSON 字符串规则解码。"""
    index = start
    length = len(source)
    if index >= length or source[index] != '"':
        raise _invalid(index)
    index += 1
    chars: list[str] = []
    while True:
        if index >= length:
            raise _invalid(field_start)
        char = source[index]
        if char == '"':
            index += 1
            break
        if char == "\\":
            index, decoded = _parse_escape(source, index)
            chars.append(decoded)
            continue
        if ord(char) < 0x20:
            raise _invalid(index)
        chars.append(char)
        index += 1
    if index + 1 >= length or source[index] != "]" or source[index + 1] != "}":
        raise _invalid(index)
    return "".join(chars), index + 2


def _parse_escape(source: str, backslash: int) -> tuple[int, str]:
    index = backslash + 1
    if index >= len(source):
        raise _invalid(backslash)
    marker = source[index]
    if marker in _JSON_ESCAPES:
        return index + 1, _JSON_ESCAPES[marker]
    if marker == "u":
        digits = source[index + 1 : index + 5]
        if len(digits) == 4 and all(digit in _HEX_DIGITS for digit in digits):
            return index + 5, chr(int(digits, 16))
    raise _invalid(backslash)


# ---------------------------------------------------------------------------
# 绑定：大小写不敏感匹配规范名称，保留名按书写形式裁决
# ---------------------------------------------------------------------------


def _bind_field(token: FieldToken, fields: FieldCatalog) -> BoundFieldToken:
    scope_defs: tuple = getattr(fields, token.scope)
    matches = [
        definition
        for definition in scope_defs
        if definition.canonical_name.casefold() == token.name.casefold()
    ]
    if not matches:
        raise sheet_catalog_error(
            "SHEET_CATALOG_FIELD_UNDEFINED",
            {"scope": token.scope, "name": token.name},
        )
    # 方括号形式显式寻址自定义属性（保留名冲突时的唯一入口）；
    # 点号形式固有字段优先。同侧无匹配时回落到另一侧。
    preferred_builtin = not token.quoted
    ordered = sorted(
        matches, key=lambda definition: definition.builtin != preferred_builtin
    )
    chosen = ordered[0]
    return BoundFieldToken(token.scope, chosen.canonical_name, chosen.builtin)


def bind_expression(
    tokens: tuple[ExpressionToken, ...], fields: FieldCatalog
) -> BoundExpression:
    """把字段引用绑定到当前字段目录的规范作用域与规范名称。"""
    bound: list[LiteralToken | BoundFieldToken] = []
    for token in tokens:
        if isinstance(token, LiteralToken):
            bound.append(token)
        else:
            bound.append(_bind_field(token, fields))
    return BoundExpression(tuple(bound))


# ---------------------------------------------------------------------------
# 求值：缺定义已在绑定阶段阻断；缺值求值为空串，字面量原样保留
# ---------------------------------------------------------------------------


def _lookup(properties: tuple, canonical_name: str) -> str:
    for prop in properties:
        if prop.canonical_name == canonical_name:
            return prop.value
    return ""


def evaluate_expression(
    expression: BoundExpression,
    sheetset: SnapshotPropertyScope,
    sheet: SheetSnapshot,
) -> str:
    """对单张图纸求值；缺失的属性值按空字符串处理，分隔符等字面量保留。"""
    parts: list[str] = []
    for token in expression.tokens:
        if isinstance(token, LiteralToken):
            parts.append(token.value)
        elif token.scope == "sheetset":
            parts.append(_lookup(sheetset.custom_properties, token.canonical_name))
        elif token.builtin:
            parts.append(getattr(sheet, token.canonical_name, ""))
        else:
            parts.append(_lookup(sheet.custom_properties, token.canonical_name))
    return "".join(parts)


# ---------------------------------------------------------------------------
# 字段浏览器：按规范名称自动插入正确语法（SPEC-DM-012 §4.2）
# ---------------------------------------------------------------------------


def field_reference(scope: str, canonical_name: str) -> str:
    """生成指向规范名称的规范引用语法：点号或方括号 JSON 字符串。"""
    needs_quoted = (
        not canonical_name
        or any(char in _DOT_NAME_FORBIDDEN for char in canonical_name)
        or (
            scope == "sheet"
            and canonical_name.casefold() in _BUILTIN_CASEFOLD
            and canonical_name not in SHEET_BUILTIN_FIELDS
        )
    )
    if needs_quoted:
        return f'{{{scope}[{json.dumps(canonical_name, ensure_ascii=False)}]}}'
    return f"{{{scope}.{canonical_name}}}"
