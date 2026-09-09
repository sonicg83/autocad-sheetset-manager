"""设置中心展示元数据注册表（PLAN-DM-019 设置中心任务 2；PLAN-DM-021 Task 1 key 化）。

注册表只保存界面展示所需的静态元数据：稳定显示键（``label_key``/
``category_key``/``file_filter_key``）、控件类型与稳定文件种类。翻译正文只存在
于前端语言资源，本模块不按语言生成文本；迁移期兼容中文字段
（``label``/``category``/``file_filter``/``text``）已随阶段三（PLAN-DM-021
Task 10 / I18N-17）删除。数值范围与枚举值从 :mod:`dst_manager.config` 的
``Settings`` 字段注解派生（Pydantic 保持权威），本模块对 ``store``/``resolver``
无依赖。

``REGISTRY`` 的顺序即设置 API 的稳定排序；``ui_locale``（界面/语言）居首，
设置对话框按首次出现分组（SPEC-DM-013 §3.2）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args, get_origin

import annotated_types

from dst_manager.config import Settings


@dataclass(frozen=True)
class SettingsItemMeta:
    """单个设置项的展示元数据。"""

    key: str  # 与 Settings 字段同名，同时是 422 逐字段错误的外层稳定 key
    label_key: str  # 前端文案键，如 settings.items.uiLocale
    category_key: str  # 前端文案键，如 settings.categories.interface
    control: Literal["path", "bool", "int", "enum"]
    nullable: bool = False  # 仅 path：允许清空（写入 null）
    file_filter_key: str | None = None  # 仅 path：过滤器显示名文案键
    file_kind: Literal["exe", "dll"] | None = None  # 仅 path：固定扩展名种类


REGISTRY: tuple[SettingsItemMeta, ...] = (
    SettingsItemMeta(
        key="ui_locale",
        label_key="settings.items.uiLocale",
        category_key="settings.categories.interface",
        control="enum",
    ),
    SettingsItemMeta(
        key="autocad_2016_console",
        label_key="settings.items.autocad2016Console",
        category_key="settings.categories.autocad2016",
        control="path",
        nullable=True,
        file_filter_key="settings.fileFilters.executable",
        file_kind="exe",
    ),
    SettingsItemMeta(
        key="autocad_2016_plugin",
        label_key="settings.items.autocad2016Plugin",
        category_key="settings.categories.autocad2016",
        control="path",
        nullable=True,
        file_filter_key="settings.fileFilters.dotnetAssembly",
        file_kind="dll",
    ),
    SettingsItemMeta(
        key="autocad_2020_console",
        label_key="settings.items.autocad2020Console",
        category_key="settings.categories.autocad2020",
        control="path",
        nullable=True,
        file_filter_key="settings.fileFilters.executable",
        file_kind="exe",
    ),
    SettingsItemMeta(
        key="autocad_2020_plugin",
        label_key="settings.items.autocad2020Plugin",
        category_key="settings.categories.autocad2020",
        control="path",
        nullable=True,
        file_filter_key="settings.fileFilters.dotnetAssembly",
        file_kind="dll",
    ),
    SettingsItemMeta(
        key="cad_timeout_seconds",
        label_key="settings.items.cadTimeout",
        category_key="settings.categories.execution",
        control="int",
    ),
    SettingsItemMeta(
        key="cad_max_parallel",
        label_key="settings.items.cadMaxParallel",
        category_key="settings.categories.execution",
        control="int",
    ),
    SettingsItemMeta(
        key="worker_lease_seconds",
        label_key="settings.items.workerLease",
        category_key="settings.categories.execution",
        control="int",
    ),
    SettingsItemMeta(
        key="enable_add_number_suffix",
        label_key="settings.items.addNumberSuffix",
        category_key="settings.categories.numbering",
        control="bool",
    ),
    SettingsItemMeta(
        key="number_suffix_type",
        label_key="settings.items.numberSuffixType",
        category_key="settings.categories.numbering",
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


# 枚举选项的稳定选项键。number_suffix_type 按领域真实语义（1 → 中文数字后缀，
# 2 → 阿拉伯数字后缀，见 domain/editing.py format_sheet_title）；ui_locale 选项
# 名保留自称形式（SPEC-DM-013 §5.1），"跟随系统"的当前解析结果由前端展示
_ENUM_KEYS: dict[str, dict[object, str]] = {
    "ui_locale": {
        "system": "settings.locale.system",
        "zh-CN": "settings.locale.zhCN",
        "en-US": "settings.locale.enUS",
    },
    "number_suffix_type": {
        1: "settings.enumOptions.suffixChinese",
        2: "settings.enumOptions.suffixArabic",
    },
}


def enum_options(key: str) -> list[dict]:
    """从 ``Literal`` 注解派生枚举选项（值支持 int | str，如 ui_locale）。"""
    annotation = Settings.model_fields[key].annotation
    if get_origin(annotation) is not Literal:
        raise ValueError(f"字段 {key} 注解不是 Literal，无法派生枚举选项")
    meta = _ENUM_KEYS[key]
    return [{"value": value, "text_key": meta[value]} for value in get_args(annotation)]
