# 设置中心展示元数据注册表单元测试
from dst_manager.config import Settings
from dst_manager.settings.registry import REGISTRY, enum_options, min_max


def test_registry_covers_every_ui_field_of_settings() -> None:
    # 新增 ui_locale 后不再用固定数量断言：覆盖面由 Settings 字段派生
    ui_fields = {m.key for m in REGISTRY}
    assert ui_fields == set(Settings.model_fields) - {"data_dir", "draft_dir"}


def test_ui_locale_is_first_item_in_interface_category() -> None:
    # "界面"分组置于设置中心首位，语言为该分组首项（SPEC-DM-013 §3.2）
    first = REGISTRY[0]
    assert first.key == "ui_locale"
    assert (first.label, first.category) == ("语言", "界面")  # 兼容中文文本
    assert first.label_key == "settings.items.uiLocale"
    assert first.category_key == "settings.categories.interface"
    assert first.control == "enum"


def test_every_item_declares_stable_display_keys() -> None:
    # 所有项只靠稳定 key 描述：label_key/category_key 必填，path 项附 file_filter_key
    # 与白名单内的 file_kind，前端不得再从中文 file_filter 推导行为
    for meta in REGISTRY:
        assert meta.label_key.startswith("settings.items."), meta.key
        assert meta.category_key.startswith("settings.categories."), meta.key
        if meta.control == "path":
            assert meta.nullable, meta.key
            assert meta.file_filter, meta.key  # 兼容中文过滤器文本
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
    # 稳定选项键 + 中文兼容文本；语义与 domain/editing.py 的后缀定义一致
    assert [o["text_key"] for o in options] == [
        "settings.enumOptions.suffixChinese",
        "settings.enumOptions.suffixArabic",
    ]
    assert [o["text"] for o in options] == ["中文序号（一、二、三…）", "数字序号（1、2、3…）"]


def test_ui_locale_enum_options_are_string_values_with_keys() -> None:
    # 枚举值从 int 扩展为 int | str，承载 ui_locale 的字符串枚举值
    options = enum_options("ui_locale")
    assert [o["value"] for o in options] == ["system", "zh-CN", "en-US"]
    assert [o["text_key"] for o in options] == [
        "settings.locale.system",
        "settings.locale.zhCN",
        "settings.locale.enUS",
    ]
    assert all(o["text"] for o in options)  # 兼容中文文本："跟随系统"/"简体中文"/"English"
