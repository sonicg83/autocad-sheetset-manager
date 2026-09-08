"""设置中心展示元数据注册表（PLAN-DM-019 设置中心任务 2）。

注册表只保存界面展示所需的静态元数据（标签、分类、控件类型、文件过滤器），
不持有任何取值；数值范围与枚举选项从 :mod:`dst_manager.config` 的
``Settings`` 字段注解派生（Pydantic 保持权威），本模块对 ``store``/``resolver``
无依赖。

``REGISTRY`` 的顺序即设置 API 的稳定排序，供后续 resolver/runtime 直接消费。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args, get_origin

import annotated_types

from dst_manager.config import Settings

# 文件过滤器文案（pywebview 对话框括号格式约束见 shell.ts 既有注释）
EXE_FILTER = "可执行程序 (*.exe)"
DLL_FILTER = ".NET 程序集 (*.dll)"


@dataclass(frozen=True)
class SettingsItemMeta:
    """单个设置项的展示元数据。"""

    key: str  # 与 Settings 字段同名
    label: str  # 中文显示名
    category: str  # "AutoCAD 2016" | "AutoCAD 2020" | "任务执行" | "编号规则"
    control: str  # "path" | "bool" | "int" | "enum"
    nullable: bool = False  # 仅 path：允许清空（写入 null）
    file_filter: str | None = None  # 仅 path：文件选择过滤器


REGISTRY: tuple[SettingsItemMeta, ...] = (
    SettingsItemMeta("autocad_2016_console", "Core Console", "AutoCAD 2016", "path", True, EXE_FILTER),
    SettingsItemMeta("autocad_2016_plugin", "Worker 插件", "AutoCAD 2016", "path", True, DLL_FILTER),
    SettingsItemMeta("autocad_2020_console", "Core Console", "AutoCAD 2020", "path", True, EXE_FILTER),
    SettingsItemMeta("autocad_2020_plugin", "Worker 插件", "AutoCAD 2020", "path", True, DLL_FILTER),
    SettingsItemMeta("cad_timeout_seconds", "CAD 超时（秒）", "任务执行", "int"),
    SettingsItemMeta("cad_max_parallel", "最大并行任务数", "任务执行", "int"),
    SettingsItemMeta("worker_lease_seconds", "Worker 租约（秒）", "任务执行", "int"),
    SettingsItemMeta("enable_add_number_suffix", "图纸编号追加后缀", "编号规则", "bool"),
    SettingsItemMeta("number_suffix_type", "后缀类型", "编号规则", "enum"),
)


def min_max(key: str) -> tuple[int, int]:
    """从 ``Settings`` 字段注解的 ge/le 约束派生数值范围。"""
    ge: int | None = None
    le: int | None = None
    for constraint in Settings.model_fields[key].metadata:
        if isinstance(constraint, annotated_types.Ge):
            ge = constraint.ge
        elif isinstance(constraint, annotated_types.Le):
            le = constraint.le
    if ge is None or le is None:
        raise ValueError(f"字段 {key} 缺少 ge/le 约束，无法派生数值范围")
    return (ge, le)


# 枚举选项文案（按领域真实语义：suffix_type=1 → 中文数字后缀，2 → 阿拉伯数字后缀，
# 见 domain/editing.py format_sheet_title）
_ENUM_TEXTS: dict[str, dict[int, str]] = {
    "number_suffix_type": {
        1: "中文序号（一、二、三…）",
        2: "数字序号（1、2、3…）",
    },
}


def enum_options(key: str) -> list[dict]:
    """从 ``Literal`` 注解派生枚举选项（如 number_suffix_type → 中文/数字序号）。"""
    annotation = Settings.model_fields[key].annotation
    if get_origin(annotation) is not Literal:
        raise ValueError(f"字段 {key} 注解不是 Literal，无法派生枚举选项")
    texts = _ENUM_TEXTS[key]
    return [{"value": value, "text": texts[value]} for value in get_args(annotation)]
