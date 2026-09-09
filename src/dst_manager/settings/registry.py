"""设置中心展示元数据注册表（PLAN-DM-019 设置中心任务 2；PLAN-DM-021 Task 1 key 化）。

注册表只保存界面展示所需的静态元数据：稳定显示键（``label_key``/
``category_key``/``file_filter_key``）、控件类型、稳定文件种类与迁移期兼容
中文文本（``label``/``category``/``file_filter``，阶段三验收后删除）。翻译
正文只存在于前端语言资源，本模块不按语言生成文本。数值范围与枚举值从
:mod:`dst_manager.config` 的 ``Settings`` 字段注解派生（Pydantic 保持权威），
本模块对 ``store``/``resolver`` 无依赖。

``REGISTRY`` 的顺序即设置 API 的稳定排序；``ui_locale``（界面/语言）居首，
设置对话框按首次出现分组（SPEC-DM-013 §3.2）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args, get_origin

import annotated_types

from dst_manager.config import Settings

# 文件过滤器兼容中文文案（pywebview 对话框括号格式约束见 shell.ts 既有注释）
EXE_FILTER = "可执行程序 (*.exe)"
DLL_FILTER = ".NET 程序集 (*.dll)"


@dataclass(frozen=True)
class SettingsItemMeta:
    """单个设置项的展示元数据。"""

    key: str  # 与 Settings 字段同名，同时是 422 逐字段错误的外层稳定 key
    label_key: str  # 前端文案键，如 settings.items.uiLocale
    category_key: str  # 前端文案键，如 settings.categories.interface
    label: str  # 兼容：中文显示名（阶段三删除）
    category: str  # 兼容：中文分类（阶段三删除）
    control: Literal["path", "bool", "int", "enum"]
    nullable: bool = False  # 仅 path：允许清空（写入 null）
    file_filter: str | None = None  # 兼容：仅 path，中文过滤器文本（阶段三删除）
    file_filter_key: str | None = None  # 仅 path：过滤器显示名文案键
    file_kind: Literal["exe", "dll"] | None = None  # 仅 path：固定扩展名种类


REGISTRY: tuple[SettingsItemMeta, ...] = (
    SettingsItemMeta(
        key="ui_locale",
        label_key="settings.items.uiLocale",
        category_key="settings.categories.interface",
        label="语言",
        category="界面",
        control="enum",
    ),
    SettingsItemMeta(
        key="autocad_2016_console",
        label_key="settings.items.autocad2016Console",
        category_key="settings.categories.autocad2016",
        label="Core Console",
        category="AutoCAD 2016",
        control="path",
        nullable=True,
        file_filter=EXE_FILTER,
        file_filter_key="settings.fileFilters.executable",
        file_kind="exe",
    ),
    SettingsItemMeta(
        key="autocad_2016_plugin",
        label_key="settings.items.autocad2016Plugin",
        category_key="settings.categories.autocad2016",
        label="Worker 插件",
        category="AutoCAD 2016",
        control="path",
        nullable=True,
        file_filter=DLL_FILTER,
        file_filter_key="settings.fileFilters.dotnetAssembly",
        file_kind="dll",
    ),
    SettingsItemMeta(
        key="autocad_2020_console",
        label_key="settings.items.autocad2020Console",
        category_key="settings.categories.autocad2020",
        label="Core Console",
        category="AutoCAD 2020",
        control="path",
        nullable=True,
        file_filter=EXE_FILTER,
        file_filter_key="settings.fileFilters.executable",
        file_kind="exe",
    ),
    SettingsItemMeta(
        key="autocad_2020_plugin",
        label_key="settings.items.autocad2020Plugin",
        category_key="settings.categories.autocad2020",
        label="Worker 插件",
        category="AutoCAD 2020",
        control="path",
        nullable=True,
        file_filter=DLL_FILTER,
        file_filter_key="settings.fileFilters.dotnetAssembly",
        file_kind="dll",
    ),
    SettingsItemMeta(
        key="cad_timeout_seconds",
        label_key="settings.items.cadTimeout",
        category_key="settings.categories.execution",
        label="CAD 超时（秒）",
        category="任务执行",
        control="int",
    ),
    SettingsItemMeta(
        key="cad_max_parallel",
        label_key="settings.items.cadMaxParallel",
        category_key="settings.categories.execution",
        label="最大并行任务数",
        category="任务执行",
        control="int",
    ),
    SettingsItemMeta(
        key="worker_lease_seconds",
        label_key="settings.items.workerLease",
        category_key="settings.categories.execution",
        label="Worker 租约（秒）",
        category="任务执行",
        control="int",
    ),
    SettingsItemMeta(
        key="enable_add_number_suffix",
        label_key="settings.items.addNumberSuffix",
        category_key="settings.categories.numbering",
        label="图纸编号追加后缀",
        category="编号规则",
        control="bool",
    ),
    SettingsItemMeta(
        key="number_suffix_type",
        label_key="settings.items.numberSuffixType",
        category_key="settings.categories.numbering",
        label="后缀类型",
        category="编号规则",
        control="enum",
    ),
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


# 枚举选项元数据：稳定选项键 + 迁移期兼容中文文本。
# number_suffix_type 按领域真实语义（1 → 中文数字后缀，2 → 阿拉伯数字后缀，
# 见 domain/editing.py format_sheet_title）；ui_locale 选项名保留自称形式
#（SPEC-DM-013 §5.1），"跟随系统"的当前解析结果由前端展示
_ENUM_META: dict[str, dict[object, tuple[str, str]]] = {
    "ui_locale": {
        "system": ("settings.locale.system", "跟随系统"),
        "zh-CN": ("settings.locale.zhCN", "简体中文"),
        "en-US": ("settings.locale.enUS", "English"),
    },
    "number_suffix_type": {
        1: ("settings.enumOptions.suffixChinese", "中文序号（一、二、三…）"),
        2: ("settings.enumOptions.suffixArabic", "数字序号（1、2、3…）"),
    },
}


def enum_options(key: str) -> list[dict]:
    """从 ``Literal`` 注解派生枚举选项（值支持 int | str，如 ui_locale）。"""
    annotation = Settings.model_fields[key].annotation
    if get_origin(annotation) is not Literal:
        raise ValueError(f"字段 {key} 注解不是 Literal，无法派生枚举选项")
    meta = _ENUM_META[key]
    return [
        {"value": value, "text_key": meta[value][0], "text": meta[value][1]}
        for value in get_args(annotation)
    ]
