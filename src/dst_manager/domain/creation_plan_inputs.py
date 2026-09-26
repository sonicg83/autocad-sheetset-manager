"""创建输入门禁与标准资产解析（PLAN-DM-036 Task 3）。

把「草稿输入是否完整、合法」与「标准声明的资产/图幅是否可用」判定成稳定诊断：
路径形状复用 :func:`dst_manager.domain.creation.validate_creation_target_path`，
资产只按标准声明的 ``asset_id`` 与图幅角色解析出**包内相对路径**——本模块不读
文件系统、不查标准包文件，文件本体与目标目录状态由应用层（Task 4/6）另行绑定。

关键语义：

- ``sheetset`` 与每组 ``sheet`` 输入必须是完整 ``property_id`` 字典：漏传键报
  ``CREATION_SHEETSET_VALUE_MISSING``/``CREATION_GROUP_VALUE_MISSING``，
  与显式空串不可混同；
- ``required`` 非空只在创建实际值门禁判断（标准可以没有必填属性默认值）；
- 资产必须存在且种类相符，图幅必须是布局模板资产勾选的启用图幅（PLAN-DM-042），
  不是自由文本；
- 组图名重复按「去首尾空格 + 大小写不敏感」判定。

每个函数只返回诊断与解析结果，不抛出、不修改入参；去重与顺序由调用方
（:mod:`dst_manager.domain.creation_planning`）统一维护。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from dst_manager.domain.creation import (
    CreationGroupInput,
    validate_creation_target_path,
)
from dst_manager.domain.creation_plan_models import CreationPlanDiagnostic
from dst_manager.domain.standard_models import (
    DrawingStandard,
    StandardAsset,
    StandardProperty,
)

__all__ = [
    "BASE_TEMPLATE_KIND",
    "LAYOUT_TEMPLATE_KIND",
    "duplicate_title_diagnostics",
    "group_diagnostics",
    "input_diagnostics",
    "resolve_base_template",
    "resolve_layout_template",
    "target_path_diagnostics",
]

#: 资产种类：基础模板与布局模板（与 ``standard_models.ASSET_KINDS`` 同口径）。
BASE_TEMPLATE_KIND = "base-template"
LAYOUT_TEMPLATE_KIND = "layout-template"


def target_path_diagnostics(target_path: str) -> list[CreationPlanDiagnostic]:
    """项目路径形状与安全校验；非法路径阻断计划，调用方不再产出逐组绝对路径。"""
    return [
        CreationPlanDiagnostic(code=diagnostic.code, message=diagnostic.message)
        for diagnostic in validate_creation_target_path(target_path)
    ]


def input_diagnostics(
    properties: Sequence[StandardProperty],
    values: Mapping[str, str],
    group_id: str,
    missing_code: str,
) -> list[CreationPlanDiagnostic]:
    """完整性（缺键）与必填非空门禁：缺键与显式空串不可混同。"""
    diagnostics: list[CreationPlanDiagnostic] = []
    for prop in properties:
        name = prop.name or prop.property_id
        if prop.property_id not in values:
            diagnostics.append(
                CreationPlanDiagnostic(
                    code=missing_code,
                    message=f"缺少普通属性 {name!r} 的值（漏传键与显式空串不可混同）",
                    group_id=group_id,
                    property_id=prop.property_id,
                )
            )
        if prop.required and not values.get(prop.property_id, "").strip():
            diagnostics.append(
                CreationPlanDiagnostic(
                    code="CREATION_REQUIRED_VALUE_MISSING",
                    message=f"必填属性 {name!r} 不能为空",
                    group_id=group_id,
                    property_id=prop.property_id,
                )
            )
    return diagnostics


def group_diagnostics(
    group: CreationGroupInput, title: str
) -> list[CreationPlanDiagnostic]:
    """组图名与张数的结构门禁（``title`` 为去首尾空格后的组图名）。"""
    diagnostics: list[CreationPlanDiagnostic] = []
    if not title:
        diagnostics.append(
            CreationPlanDiagnostic(
                code="CREATION_GROUP_TITLE_EMPTY",
                message=f"图纸组 {group.group_id!r} 的图名不能为空",
                group_id=group.group_id,
            )
        )
    if group.count < 1:
        diagnostics.append(
            CreationPlanDiagnostic(
                code="CREATION_GROUP_COUNT_INVALID",
                message=f"图纸组 {group.group_id!r} 的张数必须为正整数",
                group_id=group.group_id,
            )
        )
    return diagnostics


def duplicate_title_diagnostics(
    group_inputs: Sequence[CreationGroupInput], titles: Sequence[str]
) -> list[CreationPlanDiagnostic]:
    """组图名重复：去首尾空格 + 大小写不敏感（空图名已单独阻断）。"""
    diagnostics: list[CreationPlanDiagnostic] = []
    owners: dict[str, str] = {}
    for index, group in enumerate(group_inputs):
        if not titles[index]:
            continue
        key = titles[index].casefold()
        owner = owners.get(key)
        if owner is not None:
            diagnostics.append(
                CreationPlanDiagnostic(
                    code="CREATION_GROUP_TITLE_DUPLICATE",
                    message=(
                        f"图纸组图名 {titles[index]!r} 与组 {owner!r} 重复"
                        "（忽略大小写与首尾空格）"
                    ),
                    group_id=group.group_id,
                )
            )
            continue
        owners[key] = group.group_id
    return diagnostics


def resolve_base_template(
    standard: DrawingStandard, group: CreationGroupInput
) -> tuple[str, list[CreationPlanDiagnostic]]:
    """基础模板资产的包内相对路径；资产缺失或种类不符时阻断该组。"""
    asset = _find_asset(standard, group.base_asset_id)
    if asset is None or asset.kind != BASE_TEMPLATE_KIND or not asset.file:
        return "", [
            CreationPlanDiagnostic(
                code="CREATION_ASSET_INVALID",
                message=(
                    f"图纸组 {group.group_id!r} 的基础模板资产 {group.base_asset_id!r} "
                    "不存在或不是基础模板"
                ),
                group_id=group.group_id,
            )
        ]
    return asset.file, []


def resolve_layout_template(
    standard: DrawingStandard, group: CreationGroupInput
) -> tuple[str, list[CreationPlanDiagnostic]]:
    """解析布局模板资产；图幅必须是该资产勾选的启用图幅，不是自由文本。"""
    asset = _find_asset(standard, group.layout_asset_id)
    if asset is None or asset.kind != LAYOUT_TEMPLATE_KIND or not asset.file:
        return "", [
            CreationPlanDiagnostic(
                code="CREATION_ASSET_INVALID",
                message=(
                    f"图纸组 {group.group_id!r} 的布局模板资产 {group.layout_asset_id!r} "
                    "不存在或不是布局模板"
                ),
                group_id=group.group_id,
            )
        ]
    paper_layout = group.paper_layout.strip()
    if paper_layout and paper_layout in asset.paper_layouts:
        return asset.file, []
    return "", [
        CreationPlanDiagnostic(
            code="CREATION_PAPER_LAYOUT_INVALID",
            message=(
                f"图纸组 {group.group_id!r} 的图幅 {group.paper_layout!r} 不在布局模板资产"
                f" {group.layout_asset_id!r} 声明的图幅内"
            ),
            group_id=group.group_id,
        )
    ]


def _find_asset(standard: DrawingStandard, asset_id: str) -> StandardAsset | None:
    return next((asset for asset in standard.assets if asset.asset_id == asset_id), None)
