# 设置中心展示元数据注册表单元测试
from dst_manager.config import Settings
from dst_manager.settings.registry import REGISTRY, enum_options, min_max


def test_registry_covers_exactly_the_nine_ui_fields() -> None:
    ui_fields = {m.key for m in REGISTRY}
    assert ui_fields == {
        "autocad_2016_console", "autocad_2016_plugin",
        "autocad_2020_console", "autocad_2020_plugin",
        "cad_timeout_seconds", "cad_max_parallel", "worker_lease_seconds",
        "enable_add_number_suffix", "number_suffix_type",
    }
    excluded = {"data_dir", "draft_dir"}
    assert not (ui_fields & excluded)


def test_every_key_exists_on_settings() -> None:
    settings = Settings()
    for meta in REGISTRY:
        assert hasattr(settings, meta.key)


def test_derived_constraints_match_settings_schema() -> None:
    assert min_max("cad_max_parallel") == (1, 10)
    assert min_max("worker_lease_seconds") == (30, 3600)
    options = enum_options("number_suffix_type")
    assert [o["value"] for o in options] == [1, 2]
    # 文案与 domain/editing.py 的后缀语义一致：1=中文数字、2=阿拉伯数字
    assert [o["text"] for o in options] == ["中文序号（一、二、三…）", "数字序号（1、2、3…）"]


def test_path_fields_declare_nullable_and_filters() -> None:
    for meta in REGISTRY:
        if meta.control == "path":
            assert meta.nullable and meta.file_filter is not None
    console = next(m for m in REGISTRY if m.key == "autocad_2016_console")
    assert "*.exe" in console.file_filter
    plugin = next(m for m in REGISTRY if m.key == "autocad_2016_plugin")
    assert "*.dll" in plugin.file_filter
