import pytest
from pydantic import ValidationError

from dst_manager.config import Settings


def test_suffix_settings_use_spec_defaults(monkeypatch):
    monkeypatch.delenv("EnableAddNumberSuffix", raising=False)
    monkeypatch.delenv("NumberSuffixType", raising=False)
    settings = Settings(_env_file=None)
    assert settings.enable_add_number_suffix is True
    assert settings.number_suffix_type == 1


def test_suffix_settings_reject_invalid_values(monkeypatch):
    monkeypatch.setenv("NumberSuffixType", "3")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["1", "2"])
def test_suffix_settings_accept_digit_strings(monkeypatch, value: str):
    """.env 与环境变量里的值恒为字符串：数字序号选项必须像布尔选项一样
    接受 "1"/"2" 字符串，否则 setup.bat 生成的 .env 会让 Settings 崩溃。"""
    monkeypatch.setenv("NumberSuffixType", value)
    settings = Settings(_env_file=None)
    assert settings.number_suffix_type == int(value)


@pytest.mark.parametrize("value", ["1", "0", "yes", "on"])
def test_suffix_settings_reject_loose_boolean_strings(monkeypatch, value: str):
    monkeypatch.setenv("EnableAddNumberSuffix", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_alias_fields_accept_field_name_kwargs():
    """设置中心以 registry 字段名（snake_case）构造覆盖项：validation_alias 只服务
    .env/环境变量通道，populate_by_name 必须让字段名入口同时可用。"""
    settings = Settings(_env_file=None, enable_add_number_suffix=False, number_suffix_type=2)
    assert settings.enable_add_number_suffix is False
    assert settings.number_suffix_type == 2


def test_cad_paths_resolve_relative_to_absolute(monkeypatch, tmp_path):
    """accoreconsole 子进程内 NETLOAD 按自身工作目录解析相对 DLL 路径，Python 侧 is_file
    （相对项目根）会通过但加载失败：Settings 必须把 CAD 路径统一规范化为绝对路径。"""
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        _env_file=None,
        autocad_2020_plugin="plugins/autocad2020/DstManager.AutoCAD.dll",
        autocad_2016_console=r"Program Files\Autodesk\AutoCAD 2016\accoreconsole.exe",
    )
    assert settings.autocad_2020_plugin == (tmp_path / "plugins/autocad2020/DstManager.AutoCAD.dll").resolve()
    assert settings.autocad_2016_console == (tmp_path / r"Program Files\Autodesk\AutoCAD 2016\accoreconsole.exe").resolve()


def test_cad_paths_none_untouched():
    settings = Settings(_env_file=None)
    assert settings.autocad_2016_console is None
    assert settings.autocad_2020_plugin is None


def test_frozen_plugin_defaults_point_to_bundled_dlls(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "dst-manager.exe"))
    settings = Settings(_env_file=None)
    assert settings.autocad_2016_plugin == (tmp_path / "autocad2016" / "DstManager.AutoCAD.dll").resolve()
    assert settings.autocad_2020_plugin == (tmp_path / "autocad2020" / "DstManager.AutoCAD.dll").resolve()
    # Core Console 永不猜测，frozen 态同样保持 None
    assert settings.autocad_2016_console is None
    assert settings.autocad_2020_console is None


def test_frozen_data_dir_defaults_to_localappdata(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "dst-manager.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    settings = Settings(_env_file=None)
    assert settings.data_dir == (tmp_path / "AppData" / "dst-manager" / "data").resolve()


def test_frozen_explicit_config_overrides_defaults(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "dst-manager.exe"))
    plugin = tmp_path / "custom" / "my.dll"
    settings = Settings(_env_file=None, autocad_2020_plugin=str(plugin))
    assert settings.autocad_2020_plugin == plugin.resolve()
