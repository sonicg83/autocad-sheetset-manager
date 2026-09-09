# 设置中心展示元数据注册表单元测试
from dataclasses import fields

from dst_manager.config import Settings
from dst_manager.settings.registry import (
    REGISTRY,
    SettingsItemMeta,
    enum_options,
    min_max,
)


def test_registry_covers_every_ui_field_of_settings() -> None:
    # 新增 ui_locale 后不再用固定数量断言：覆盖面由 Settings 字段派生
    ui_fields = {m.key for m in REGISTRY}
    assert ui_fields == set(Settings.model_fields) - {"data_dir", "draft_dir"}


def test_ui_locale_is_first_item_in_interface_category() -> None:
    # "界面"分组置于设置中心首位，语言为该分组首项（SPEC-DM-013 §3.2）
    first = REGISTRY[0]
    assert first.key == "ui_locale"
    assert first.label_key == "settings.items.uiLocale"
    assert first.category_key == "settings.categories.interface"
    assert first.control == "enum"


def test_no_legacy_localized_fields_remain() -> None:
    # 阶段三（PLAN-DM-021 Task 10 / I18N-17）：迁移期兼容中文字段
    # label/category/file_filter 已删除，注册表只保留稳定显示键
    legacy = {"label", "category", "file_filter"}
    field_names = {f.name for f in fields(SettingsItemMeta)}
    assert legacy.isdisjoint(field_names)
    for meta in REGISTRY:
        assert not hasattr(meta, "label") and not hasattr(meta, "category"), meta.key


def test_every_item_declares_stable_display_keys() -> None:
    # 所有项只靠稳定 key 描述：label_key/category_key 必填，path 项附 file_filter_key
    # 与白名单内的 file_kind，前端不得再从中文 file_filter 推导行为
    for meta in REGISTRY:
        assert meta.label_key.startswith("settings.items."), meta.key
        assert meta.category_key.startswith("settings.categories."), meta.key
        if meta.control == "path":
            assert meta.nullable, meta.key
            assert meta.file_filter_key, meta.key
            assert meta.file_kind in ("exe", "dll"), meta.key
        else:
            assert meta.file_filter_key is None and meta.file_kind is None, meta.key


def test_derived_constraints_match_settings_schema() -> None:
    assert min_max("cad_max_parallel") == (1, 10)
    assert min_max("worker_lease_seconds") == (30, 3600)


def test_number_suffix_enum_options_carry_stable_keys() -> None:
    options = enum_options("number_suffix_type")
    assert [o["value"] for o in options] == [1, 2]
    # 稳定选项键；语义与 domain/editing.py 的后缀定义一致；中文正文只在前端语言资源
    assert [o["text_key"] for o in options] == [
        "settings.enumOptions.suffixChinese",
        "settings.enumOptions.suffixArabic",
    ]
    assert all("text" not in o for o in options)  # 兼容中文 text 已随阶段三删除


def test_ui_locale_enum_options_are_string_values_with_keys() -> None:
    # 枚举值从 int 扩展为 int | str，承载 ui_locale 的字符串枚举值
    options = enum_options("ui_locale")
    assert [o["value"] for o in options] == ["system", "zh-CN", "en-US"]
    assert [o["text_key"] for o in options] == [
        "settings.locale.system",
        "settings.locale.zhCN",
        "settings.locale.enUS",
    ]
    assert all("text" not in o for o in options)  # 兼容中文 text 已随阶段三删除
