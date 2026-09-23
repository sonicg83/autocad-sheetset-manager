"""创建计划的冻结值类型与确定性内容摘要（PLAN-DM-036 Task 3）。

本模块只放计划对外形状（下游任务与前端按这些名字消费）与摘要计算：`CreationPlan`
不读文件系统、不启动 CAD、不查标准包文件。计划编译见
:mod:`dst_manager.domain.creation_planning`，输入门禁与资产解析见
:mod:`dst_manager.domain.creation_plan_inputs`。

摘要 ``digest`` 必须确定性覆盖标准身份、草稿身份与修订、有效编号配置（位数/起点/
标题后缀/不编号关键字）与全部派生输出（含逐张属性与文件名）：同样输入必得同样摘要。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PureWindowsPath

from dst_manager.domain.creation import CreationDraft
from dst_manager.domain.models import SuffixOptions
from dst_manager.domain.standard_models import DrawingStandard

__all__ = [
    "CreationPlan",
    "CreationPlanDiagnostic",
    "GroupPlan",
    "PropertyCell",
    "PropertyCellRow",
    "SheetPlan",
    "plan_digest",
    "target_file_path",
]


@dataclass(frozen=True, slots=True)
class CreationPlanDiagnostic:
    """一条创建计划诊断：稳定错误码 + 可定位的图纸组/属性。

    ``group_id`` 为空串表示该诊断不针对具体图纸组（如目标路径形状、``sheetset``
    输入）；``property_id`` 为空串表示该诊断不针对具体属性（如组图名、DWG 重名）。
    """

    code: str
    message: str
    group_id: str = ""
    property_id: str = ""
    severity: str = "error"

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


@dataclass(frozen=True, slots=True)
class PropertyCellRow:
    """按组预览里一行图纸的属性明细：图号 + 该张实际值。"""

    number: str
    value: str


@dataclass(frozen=True, slots=True)
class PropertyCell:
    """一个属性的按组预览投影：首张实际值 + 完整逐张明细（供「…」模态）。"""

    property_id: str
    first_value: str
    sheets: tuple[PropertyCellRow, ...]


@dataclass(frozen=True, slots=True)
class SheetPlan:
    """一张展开后的图纸：最终图号/标题/布局名与该张的完整普通 + 派生属性值。"""

    number: str
    title: str
    layout_name: str
    values: dict[str, str]


@dataclass(frozen=True, slots=True)
class GroupPlan:
    """一个图纸组的最终结果：一组一个主 DWG，组内每张图纸一个布局。

    ``dwg_name`` 是标准 DWG 命名模板对该组真实数据求值后的**文件名**，
    ``target_path`` 是它在最终项目目录下的**完整绝对路径**；命名失败或目标重名时
    两者都为空串。``base_template``/``layout_template`` 是标准包内相对路径，
    ``paper_layout`` 是所选布局资产声明的图幅。
    """

    group_id: str
    created_order: int
    title: str
    number_range: str
    title_range: str
    base_template: str
    layout_template: str
    paper_layout: str
    dwg_name: str
    target_path: str
    sheets: tuple[SheetPlan, ...]
    property_cells: dict[str, PropertyCell]

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)


@dataclass(frozen=True, slots=True)
class CreationPlan:
    """创建计划的确定性编译结果；``has_errors`` 为真时计划不可执行。"""

    target_path: str
    sheetset_values: dict[str, str]
    groups: tuple[GroupPlan, ...]
    diagnostics: tuple[CreationPlanDiagnostic, ...]
    digest: str

    @property
    def has_errors(self) -> bool:
        return any(diagnostic.is_error for diagnostic in self.diagnostics)


def target_file_path(target_path: str, dwg_name: str) -> str:
    """主 DWG 的完整绝对路径；目标路径或文件名为空时返回空串。"""
    if not target_path or not dwg_name:
        return ""
    return str(PureWindowsPath(target_path) / dwg_name)


def plan_digest(
    draft: CreationDraft,
    standard: DrawingStandard,
    suffix_options: SuffixOptions,
    sheetset_values: Mapping[str, str],
    groups: Sequence[GroupPlan],
    diagnostics: Sequence[CreationPlanDiagnostic],
) -> str:
    """确定性内容摘要：稳定序列化（排序键 + 固定分隔符），不使用 ``hash()``/集合顺序。"""
    payload = {
        "standard": {"id": standard.standard_id, "version": standard.version},
        "draft": {"id": draft.id, "revision": draft.revision, "target_path": draft.target_path},
        "numbering": {
            "sequence_field": standard.numbering.sequence_field,
            "digits": standard.numbering.digits,
            "start": standard.numbering.start,
        },
        "suffix": {
            "enabled": suffix_options.enabled,
            "suffix_type": suffix_options.suffix_type,
            "unnumbered_keywords": list(suffix_options.unnumbered_keywords),
        },
        "sheetset_values": dict(sheetset_values),
        "groups": [
            {
                "group_id": group.group_id,
                "created_order": group.created_order,
                "title": group.title,
                "number_range": group.number_range,
                "title_range": group.title_range,
                "base_template": group.base_template,
                "layout_template": group.layout_template,
                "paper_layout": group.paper_layout,
                "dwg_name": group.dwg_name,
                "target_path": group.target_path,
                "sheets": [
                    {
                        "number": sheet.number,
                        "title": sheet.title,
                        "layout_name": sheet.layout_name,
                        "values": dict(sheet.values),
                    }
                    for sheet in group.sheets
                ],
            }
            for group in groups
        ],
        "diagnostics": [
            {
                "code": diagnostic.code,
                "group_id": diagnostic.group_id,
                "property_id": diagnostic.property_id,
            }
            for diagnostic in diagnostics
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
