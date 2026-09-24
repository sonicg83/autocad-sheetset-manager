"""图纸标准身份纯函数（PLAN-DM-041 Task 3）。

本模块只放无副作用、无文件系统依赖的纯函数，供本机发布与标准包导入共用同一
名称比较口径。名称唯一性的门禁本身在仓储层（需要枚举官方与用户库），这里只
定义「什么算同一个名称」。
"""

from __future__ import annotations

import unicodedata

__all__ = ["normalize_standard_name"]


def normalize_standard_name(name: str) -> str:
    """已发布标准显示名称的比较口径（SPEC-DM-019 §3.2）。

    依次执行 Unicode NFKC 归一、去除首尾空白、连续空白归一为单个空格，
    最后用 ``str.casefold()`` 做大小写折叠。

    必须使用 ``casefold()`` 而不是 ``lower()``：德语 ``ẞ``、土耳其 ``İ``
    等字符在两者下结果不一致，会造成「看起来同名却放行」或「不同名却冲突」。
    """
    if not isinstance(name, str):
        raise TypeError(f"标准名称必须是字符串：{name!r}")
    return " ".join(unicodedata.normalize("NFKC", name).split()).casefold()
