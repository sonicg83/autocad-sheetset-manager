"""标准驱动创建的输入值类型与稳定身份（PLAN-DM-036 Task 1/2）。

本模块只放冻结值类型与纯函数：创建草稿、按序图纸组输入、标准资产候选、
XLSX 导入结果与完整最终路径的安全校验。草稿只保存**用户输入**与稳定身份，
不保存派生求值结果、DWG 命名结果、任意模板文件路径或逐张 Sheet 输入；标准
默认值只在初建时应用一次，恢复与保存不得回填用户主动清空的值
（SPEC-DM-018 §3.1、§4.1）。

``created_order`` 是组的创建序（单调递增），数组顺序才是最终组序：重排只改
数组顺序，不改变 ``created_order``；「复制最近创建的组」取它最大的组。

领域层不依赖 FastAPI、SQLAlchemy、文件系统或 AutoCAD 进程；持久化见
:mod:`dst_manager.infrastructure.creation_drafts`，草稿编排见
:mod:`dst_manager.application.creation_drafts`，XLSX 编排见
:mod:`dst_manager.application.creation_import`。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from dst_manager.domain.standard_models import DrawingStandard, StandardProperty
from dst_manager.domain.standard_naming import (
    MAX_FILENAME_LENGTH,
    segment_safety_violations,
)

#: 创建向导四阶段（SPEC-DM-018 §2）：选择标准 → 项目信息 → 图纸组 → 检查并创建。
#: 草稿只记录当前阶段，不在此做阶段门禁求值。
CREATION_STEPS: tuple[str, ...] = ("standard", "project", "groups", "review")
#: 新建草稿时标准已固定，直接进入第二阶段（SPEC-DM-018 §2.2）。
CREATION_INITIAL_STEP = "project"

#: 草稿输入的两个作用域：图纸集级与图纸组级（组内全部 Sheet 共用同一份输入）。
SHEETSET_SCOPE = "sheetset"
SHEET_SCOPE = "sheet"

#: 完整最终项目路径的长度上限：与 DWG 文件名同口径，为目录名与后续文件名预留空间。
MAX_TARGET_PATH_LENGTH = MAX_FILENAME_LENGTH
#: 路径分隔符（Windows 两种写法都接受，但不允许出现空片段）。
_TARGET_PATH_SEPARATORS = re.compile(r"[\\/]")
#: 盘符绝对路径前缀：如 ``C:\`` 或 ``C:/``。
_TARGET_PATH_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
#: 只写出盘符而缺少分隔符的写法（如 ``C:foo``），属于盘符相对路径。
_TARGET_PATH_BARE_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True, slots=True)
class CreationAssetOption:
    """标准包内的一个可用模板资产候选。

    ``asset_id`` 是标准包内稳定 ID（不是任意模板路径）；``label`` 是面向用户
    的同类内唯一显示名，由构造方（资产解析器）保证唯一，草稿存储不做去重；
    ``layouts`` 是该布局模板内可用布局名。``kind`` 只对应标准包两种资产类型。
    """

    asset_id: str
    kind: str
    label: str
    layouts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CreationGroupInput:
    """一个图纸组的输入；同组全部 Sheet 继承本组输入（SPEC-DM-018 §4.1）。"""

    group_id: str
    created_order: int
    title: str
    count: int
    base_asset_id: str
    layout_asset_id: str
    paper_layout: str
    #: 只含可输入普通 sheet 属性：``property_id → str``；显式空串与遗漏键不同义。
    sheet_values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CreationDraft:
    """可恢复的创建草稿：固定标准身份 + 输入 + 当前阶段。

    ``revision`` 是乐观修订号，每次保存递增；``target_path`` 是完整最终项目
    路径（上级目录与目录名在界面侧合成，不从属性推断）。草稿不含预览结果。
    """

    id: str
    standard_id: str
    standard_version: str
    revision: int
    step: str
    target_path: str
    #: 只含可输入普通 sheetset 属性：``property_id → str``。
    sheetset_values: dict[str, str] = field(default_factory=dict)
    #: 组序由数组顺序决定；``group_id`` 只用于稳定定位。
    groups: tuple[CreationGroupInput, ...] = ()


@dataclass(frozen=True, slots=True)
class CreationDiagnostic:
    """一条创建输入诊断：稳定错误码 + 可定位的工作表/行/列。

    ``sheet`` 为空串表示该诊断不针对具体工作表（如包级外部链接、路径形状）；
    ``column`` 用列字母（如 ``"B"``），与模板表头保持一致口径。任何诊断
    存在即代表整批拒绝，调用方不得使用半新半旧的值。
    """

    code: str
    message: str
    sheet: str = ""
    row: int | None = None
    column: str | None = None


@dataclass(frozen=True, slots=True)
class CreationImportValue:
    """一次 XLSX 导入解析出的创建输入。

    只含完整最终路径、可输入普通 sheetset 值与按行序排列的图纸组；草稿身份、
    修订与阶段由应用层在一次性保存时补，不在这里出现。
    """

    target_path: str
    #: 只含可输入普通 sheetset 属性：``property_id → str``（空单元格为显式空串）。
    sheetset_values: dict[str, str]
    groups: tuple[CreationGroupInput, ...] = ()


@dataclass(frozen=True, slots=True)
class CreationImportResult:
    """XLSX 导入解析结果：``value`` 为 None 表示整批被拒，不产生部分结果。"""

    value: CreationImportValue | None = None
    diagnostics: tuple[CreationDiagnostic, ...] = ()


def ordinary_properties(standard: DrawingStandard, scope: str) -> tuple[StandardProperty, ...]:
    """某作用域内全部可输入普通属性（按标准文档顺序）。

    派生属性不是输入项，既不产生初值，也不接受输入；图纸集与图纸组输入、
    XLSX 模板列都按本函数判定「可输入字段」。
    """
    return tuple(
        prop for prop in standard.properties if prop.scope == scope and not prop.is_derived
    )


def ordinary_property_defaults(standard: DrawingStandard, scope: str) -> dict[str, str]:
    """某作用域内全部可输入普通属性的初值：``property_id → 标准默认值``。

    只用于初建那一次（含「首个图纸组」）；派生属性不产生输入项。
    """
    return {prop.property_id: prop.default_value for prop in ordinary_properties(standard, scope)}


def unknown_value_property_ids(
    standard: DrawingStandard, scope: str, values: Mapping[str, str]
) -> tuple[str, ...]:
    """``values`` 中不属于该作用域可输入普通属性的键（保持出现顺序）。

    用于拒绝来自请求的派生字段、跨作用域字段与未知字段。
    """
    known = {prop.property_id for prop in ordinary_properties(standard, scope)}
    return tuple(key for key in values if key not in known)


def validate_creation_target_path(value: str) -> tuple[CreationDiagnostic, ...]:
    """校验完整最终项目路径（Windows 本地盘符绝对路径）。

    只判定形状与安全性，不检查目标是否存在、是否为空目录（存在性属于预览与
    执行时的检查）。非法字符、保留设备名与文件名长度上限复用 DWG 命名的既有
    常量，不另立一套规则。返回的诊断不带工作表定位，由调用方按需补上单元格。
    """
    if not value.strip():
        return (_path_diagnostic("CREATION_TARGET_PATH_EMPTY", "项目保存路径不能为空"),)
    if _TARGET_PATH_DRIVE.match(value) is None:
        if _TARGET_PATH_BARE_DRIVE.match(value) is not None:
            return (
                _path_diagnostic(
                    "CREATION_TARGET_PATH_DRIVE_INVALID",
                    f"路径 {value!r} 只写出盘符而缺少分隔符",
                ),
            )
        return (
            _path_diagnostic(
                "CREATION_TARGET_PATH_NOT_ABSOLUTE",
                f"路径 {value!r} 不是盘符绝对路径（如 C:\\Projects\\项目名）",
            ),
        )

    diagnostics: list[CreationDiagnostic] = []
    if len(value) > MAX_TARGET_PATH_LENGTH:
        diagnostics.append(
            _path_diagnostic(
                "CREATION_TARGET_PATH_TOO_LONG",
                f"路径长度 {len(value)} 超过上限 {MAX_TARGET_PATH_LENGTH}",
            )
        )
    segments = _TARGET_PATH_SEPARATORS.split(value[3:])
    for segment in segments:
        diagnostics.extend(_path_segment_diagnostics(segment))
    if len(segments[-1]) > MAX_FILENAME_LENGTH:
        diagnostics.append(
            _path_diagnostic(
                "CREATION_TARGET_PATH_TOO_LONG",
                f"项目目录名长度 {len(segments[-1])} 超过上限 {MAX_FILENAME_LENGTH}",
            )
        )
    return tuple(diagnostics)


def _path_segment_diagnostics(segment: str) -> list[CreationDiagnostic]:
    """单个路径片段的安全判定；空片段、``.``/``..`` 与尾随字符都要阻断。

    非法字符、尾随空格或句点、保留设备名复用 :func:`segment_safety_violations`
    （与 DWG 命名主体同一份规则），与命名侧的区别是这里收集全部违规。
    """
    if not segment.strip() or segment in (".", ".."):
        return [
            _path_diagnostic(
                "CREATION_TARGET_PATH_SEGMENT_INVALID",
                f"路径片段 {segment!r} 为空、是相对片段或目录分隔符重复",
            )
        ]
    return [
        _path_segment_diagnostic(kind, segment)
        for kind in segment_safety_violations(segment)
    ]


def _path_segment_diagnostic(kind: str, segment: str) -> CreationDiagnostic:
    """片段安全违规种类 → 项目路径错误码与文案。"""
    codes = {
        "character": "CREATION_TARGET_PATH_CHARACTER_INVALID",
        "trailing": "CREATION_TARGET_PATH_TRAILING_CHARACTER",
        "reserved": "CREATION_TARGET_PATH_RESERVED_DEVICE",
    }
    messages = {
        "character": f"路径片段 {segment!r} 含控制字符或 Windows 非法字符",
        "trailing": f"路径片段 {segment!r} 不得以空格或句点结尾",
        "reserved": f"路径片段 {segment!r} 是 Windows 保留设备名",
    }
    return _path_diagnostic(codes[kind], messages[kind])


def _path_diagnostic(code: str, message: str) -> CreationDiagnostic:
    return CreationDiagnostic(code=code, message=message)
