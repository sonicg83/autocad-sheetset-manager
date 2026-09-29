"""标准依赖能力版本解析。"""

from __future__ import annotations

import re

from dst_manager.domain.standard_errors import standard_error as _error

# 依赖能力版本仍保留三段语义化字符串。
DEPENDENCY_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def parse_dependency_version(value: object) -> str:
    """依赖能力版本：保留三段语义化字符串。"""
    if not isinstance(value, str) or not DEPENDENCY_VERSION_PATTERN.fullmatch(value):
        raise _error("STANDARD_VERSION_INVALID", f"依赖版本 {value!r} 不是三段数字版本")
    return value
