"""连续编号、标题压缩与不编号判定的共享纯原语（PLAN-DM-036 Task 3）。

编辑域（:mod:`dst_manager.domain.editing`）与创建计划域
（:mod:`dst_manager.domain.creation_planning`）必须使用同一套编号、标题与不编号
规则，否则「不编号组不占号」「图号范围单值/首末值」会在两条路径上漂移。本模块
只做纯计算：不依赖 DOM、文件系统、标准包或 AutoCAD 进程。

关键语义：

- 图号范围：组内全部图号相同时退化为单值（如 ``00``），否则取首末值（如 ``01-03``）；
- 编号种子：起点与位数取首个纯数字图号；不编号组的 0 填充图号必须由调用方先
  排除，否则会把起点拉成 0，使全部组都从 0 起编；
- 不编号判定：可编辑标题命中任一关键字即不编号（复用
  :func:`dst_manager.domain.keywords.title_matches_keywords`）；
- 标题压缩：组内多张带尾序号标题压缩为 ``基础标题 (首)-(末)``，结构异常时回退
  基础标题，供预览的「图纸」列与 DWG 命名共用。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from dst_manager.domain.keywords import title_matches_keywords

__all__ = [
    "SheetNumberingError",
    "compress_group_title",
    "format_number_range",
    "is_unnumbered_title",
    "number_seed",
]

#: 空组/空子集不能派生图号范围或命名（与编辑域 ``EMPTY_SUBSET`` 同一稳定错误码）。
EMPTY_SUBSET = "EMPTY_SUBSET"


class SheetNumberingError(ValueError):
    """编号原语的领域错误；``code`` 与 ``message`` 供调用方映射成本层错误类型。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def format_number_range(numbers: Sequence[str]) -> str:
    """图号范围：全部图号相同时为单值（不写成 ``00-00``），否则为首末值。

    空序列无法形成范围（组必须至少包含一张图纸），抛
    :class:`SheetNumberingError`（``EMPTY_SUBSET``）。
    """
    if not numbers:
        raise SheetNumberingError(EMPTY_SUBSET, "子集必须至少包含一张图纸")
    if numbers[0] == numbers[-1]:
        return numbers[0]
    return f"{numbers[0]}-{numbers[-1]}"


def number_seed(numbers: Iterable[str], fallback_numbers: Iterable[str] = ()) -> tuple[int, int]:
    """编号起点与位数：首个纯数字图号决定 ``(起点, 位数)``。

    ``numbers`` 必须只含**有编号**组的图号（不编号组的 0 填充图号先由调用方排除，
    否则会把起点拉成 0）。全部候选都不是纯数字时，改用 ``fallback_numbers`` 的
    位数并把起点定为 1——使「符合项目编号位数」不因关键字命中而丢失；两者都无
    数字图号时回退 ``(1, 1)``。
    """
    for value in numbers:
        if value.isdigit():
            return int(value), len(value)
    for value in fallback_numbers:
        if value.isdigit():
            return 1, len(value)
    return 1, 1


def is_unnumbered_title(title: str, keywords: Iterable[str]) -> bool:
    """可编辑标题是否命中不编号关键字（casefold 后字面子串匹配，多关键字 OR）。"""
    return title_matches_keywords(title, keywords)


def compress_group_title(base_title: str, sheet_titles: Sequence[str]) -> str:
    """把组内多张带后缀图纸的标题压缩为单个带区间后缀的标题。

    例如三张 `图纸目录 (一)`/`图纸目录 (二)`/`图纸目录 (三)` 压缩为
    `图纸目录 (一)-(三)`，供派生 DWG 文件名与预览的「图纸」列使用。组内仅一张时
    沿用基础标题（向后兼容）；任一张标题结构不符合 `基础标题 (后缀)` 时防御性
    回退为基础标题，保持与旧行为一致。
    """
    if len(sheet_titles) < 2:
        return base_title  # 组内仅一张时沿用基础标题（SPEC-DM-008 §3.2 向后兼容）
    prefix = f"{base_title} ("
    suffixes: list[str] = []
    for title in sheet_titles:
        if title.startswith(prefix) and title.endswith(")"):
            suffixes.append(title[len(prefix):-1])
        else:
            return base_title  # 结构异常时防御性回退为基础标题
    # 区间压缩：只保留首末两张图纸的序号（如 (一)-(六)），与图纸标题后缀语义对齐
    return f"{prefix}{suffixes[0]})-({suffixes[-1]})"
