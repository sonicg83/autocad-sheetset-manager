"""图纸标准身份纯函数（PLAN-DM-046 Task 1）。

本模块只放无副作用、无文件系统依赖的纯函数，供本机发布与标准包导入共用同一
名称比较口径。名称唯一性的门禁本身在仓储层（需要枚举官方与用户库），这里只
定义「什么算同一个名称」。
"""

from __future__ import annotations

import re
import unicodedata
import uuid

__all__ = ["new_standard_id", "normalize_standard_name", "parse_standard_id"]

_STANDARD_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def new_standard_id() -> str:
    """生成规范小写形式的 UUIDv4 标准身份。"""
    return str(uuid.uuid4())


def parse_standard_id(value: object) -> str:
    """验证 UUID 文本并规范化为小写带连字符形式。

    UUID 十六进制字符允许大小写不同；缺少连字符、额外分隔符及非法值拒绝。
    """
    if not isinstance(value, str) or not _STANDARD_ID_PATTERN.fullmatch(value):
        raise ValueError("标准 ID 必须是带连字符的 UUID")
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise ValueError("标准 ID 必须是有效 UUID") from exc


def normalize_standard_name(name: str) -> str:
    """标准名称唯一性比较口径（SPEC-DM-020 §3）。

    依次执行 Unicode NFKC 归一、去除首尾空白、连续空白归一为单个空格，
    最后用 ``str.casefold()`` 做大小写折叠。

    必须使用 ``casefold()`` 而不是 ``lower()``：德语 ``ẞ``、土耳其 ``İ``
    等字符在两者下结果不一致，会造成「看起来同名却放行」或「不同名却冲突」。
    """
    if not isinstance(name, str):
        raise TypeError(f"标准名称必须是字符串：{name!r}")
    return " ".join(unicodedata.normalize("NFKC", name).split()).casefold()
