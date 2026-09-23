"""标准驱动创建的输入值类型与稳定身份（PLAN-DM-036 Task 1）。

本模块只放冻结值类型与纯函数：创建草稿、按序图纸组输入与标准资产候选。
草稿只保存**用户输入**与稳定身份，不保存派生求值结果、DWG 命名结果、任意
模板文件路径或逐张 Sheet 输入；标准默认值只在初建时应用一次，恢复与保存
不得回填用户主动清空的值（SPEC-DM-018 §3.1、§4.1）。

``created_order`` 是组的创建序（单调递增），数组顺序才是最终组序：重排只改
数组顺序，不改变 ``created_order``；「复制最近创建的组」取它最大的组。

领域层不依赖 FastAPI、SQLAlchemy、文件系统或 AutoCAD 进程；持久化见
:mod:`dst_manager.infrastructure.creation_drafts`，编排见
:mod:`dst_manager.application.creation_drafts`。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from dst_manager.domain.standard_models import DrawingStandard

#: 创建向导四阶段（SPEC-DM-018 §2）：选择标准 → 项目信息 → 图纸组 → 检查并创建。
#: 草稿只记录当前阶段，不在此做阶段门禁求值。
CREATION_STEPS: tuple[str, ...] = ("standard", "project", "groups", "review")
#: 新建草稿时标准已固定，直接进入第二阶段（SPEC-DM-018 §2.2）。
CREATION_INITIAL_STEP = "project"

#: 草稿输入的两个作用域：图纸集级与图纸组级（组内全部 Sheet 共用同一份输入）。
SHEETSET_SCOPE = "sheetset"
SHEET_SCOPE = "sheet"


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


def ordinary_property_defaults(standard: DrawingStandard, scope: str) -> dict[str, str]:
    """某作用域内全部可输入普通属性的初值：``property_id → 标准默认值``。

    只用于初建那一次（含「首个图纸组」）；派生属性不产生输入项。
    """
    return {
        prop.property_id: prop.default_value
        for prop in standard.properties
        if prop.scope == scope and not prop.is_derived
    }


def unknown_value_property_ids(
    standard: DrawingStandard, scope: str, values: Mapping[str, str]
) -> tuple[str, ...]:
    """``values`` 中不属于该作用域可输入普通属性的键（保持出现顺序）。

    用于拒绝来自请求的派生字段、跨作用域字段与未知字段。
    """
    known = {
        prop.property_id
        for prop in standard.properties
        if prop.scope == scope and not prop.is_derived
    }
    return tuple(key for key in values if key not in known)
