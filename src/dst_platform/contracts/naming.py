"""Windows 文件名危险字符与保留设备名校验（纯函数，无 I/O，标准库 only）。

SPEC-DB-001 §4：``layout_name`` 与 ``dwg_name`` 不得包含 ``<>:"/\\|?*`` 或控制字符，
不得以句点/空格结尾，去除扩展名并忽略大小写后不得等于保留设备名，规范化后的
文件基名最长 180 个字符；所有字符串保存前去除首尾空白。

Manager 侧既有等价规则（``dst_manager.domain.text_validation`` 的
``_UNSAFE_DERIVED_NAME``）额外禁止 ``;`` 与 ``=``。本模块取两者并集，保证
「Manager 拒绝的名称本函数必拒绝」，Manager 成为第二个消费方（PLAN-DB-001
Task 6）时切换到本实现语义只紧不松。Builder 不得 import ``dst_manager.*``。
"""

from __future__ import annotations

__all__ = [
    "MAX_WINDOWS_BASE_NAME_CHARS",
    "WINDOWS_RESERVED_DEVICE_NAMES",
    "WINDOWS_UNSAFE_FILENAME_CHARS",
    "contains_unsafe_filename_char",
    "ends_with_dot_or_space",
    "validate_windows_file_name",
]

MAX_WINDOWS_BASE_NAME_CHARS = 180

# SPEC §4 禁止字符与 Manager 既有字符集的并集（后者额外禁止 ';' 与 '='）。
WINDOWS_UNSAFE_FILENAME_CHARS = frozenset('<>:"/\\|?*;=')

WINDOWS_RESERVED_DEVICE_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)

# 大小写不敏感判定视图（供与 casefold 后的基名比较）。
_RESERVED_DEVICE_NAMES_CASEFOLDED = frozenset(
    name.casefold() for name in WINDOWS_RESERVED_DEVICE_NAMES
)


def _is_control_char(character: str) -> bool:
    return ord(character) < 0x20 or ord(character) == 0x7F


def contains_unsafe_filename_char(value: str) -> bool:
    """是否包含 Windows 文件名非法字符、路径分隔符或控制字符。"""
    return any(
        character in WINDOWS_UNSAFE_FILENAME_CHARS or _is_control_char(character)
        for character in value
    )


def ends_with_dot_or_space(value: str) -> bool:
    """规范化后的名称是否以句点或空格结尾。"""
    return value.endswith((".", " "))


def validate_windows_file_name(name: str, *, max_stem_chars: int = MAX_WINDOWS_BASE_NAME_CHARS) -> str:
    """校验 Windows 文件名并返回去除首尾空白后的规范化名称。

    ``name`` 允许携带扩展名：保留设备名与长度上限按去除最后一个扩展名后的
    基名（stem）判定，忽略大小写。违反任一规则抛出 :class:`ValueError`。
    """
    normalized = name.strip()
    if not normalized:
        raise ValueError("文件名不能为空")
    if contains_unsafe_filename_char(normalized):
        raise ValueError(f"文件名包含非法字符：{normalized!r}")
    if ends_with_dot_or_space(normalized):
        raise ValueError(f"文件名不得以句点或空格结尾：{normalized!r}")
    stem = _stem_of(normalized)
    if stem.casefold() in _RESERVED_DEVICE_NAMES_CASEFOLDED:
        raise ValueError(f"文件名不得使用 Windows 保留设备名：{stem!r}")
    if len(stem) > max_stem_chars:
        raise ValueError(f"文件基名超过 {max_stem_chars} 个字符：{len(stem)}")
    return normalized


def _stem_of(name: str) -> str:
    dot_index = name.rfind(".")
    return name[:dot_index] if dot_index > 0 else name
