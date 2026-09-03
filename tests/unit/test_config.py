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


@pytest.mark.parametrize("value", ["1", "0", "yes", "on"])
def test_suffix_settings_reject_loose_boolean_strings(monkeypatch, value: str):
    monkeypatch.setenv("EnableAddNumberSuffix", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


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
