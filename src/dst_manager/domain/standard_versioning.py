"""旧标准发布版本兼容解析与依赖能力版本解析。"""

from __future__ import annotations

import re

from dst_manager.domain.standard_errors import standard_error as _error

# 标准发布版本上限（32 位有符号整数上界）。仅供旧绑定兼容。
MAX_STANDARD_VERSION = 2147483647

# 旧工程 ``standard_id@version`` 的 ID 形式，仅作只读兼容解析。
LEGACY_STANDARD_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z0-9-]+)*$")
STANDARD_ID_PATTERN = LEGACY_STANDARD_ID_PATTERN

# 旧工程绑定版本的规范十进制正整数形式（无前导零）。
STANDARD_VERSION_SEGMENT_PATTERN = re.compile(r"^[1-9]\d*$")

# 依赖能力版本仍保留三段语义化字符串。
DEPENDENCY_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def parse_standard_version(value: object) -> int:
    """旧标准发布版本 JSON 字段口径：``1..MAX_STANDARD_VERSION`` 的整数。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error("STANDARD_VERSION_INVALID", f"标准版本 {value!r} 必须是 JSON 整数")
    if not 1 <= value <= MAX_STANDARD_VERSION:
        raise _error(
            "STANDARD_VERSION_INVALID",
            f"标准版本 {value!r} 超出 1..{MAX_STANDARD_VERSION} 范围",
        )
    return value


def parse_standard_version_segment(value: object) -> int:
    """解析旧工程绑定中的规范十进制版本段。"""
    if not isinstance(value, str) or not STANDARD_VERSION_SEGMENT_PATTERN.fullmatch(value):
        raise _error(
            "STANDARD_VERSION_INVALID",
            f"标准版本段 {value!r} 必须是规范十进制正整数（无前导零）",
        )
    if len(value) > len(str(MAX_STANDARD_VERSION)):
        raise _error(
            "STANDARD_VERSION_INVALID",
            f"标准版本段超过 {MAX_STANDARD_VERSION} 的位数上限",
        )
    return parse_standard_version(int(value))


def parse_dependency_version(value: object) -> str:
    """依赖能力版本：保留三段语义化字符串。"""
    if not isinstance(value, str) or not DEPENDENCY_VERSION_PATTERN.fullmatch(value):
        raise _error("STANDARD_VERSION_INVALID", f"依赖版本 {value!r} 不是三段数字版本")
    return value
