"""CAD 能力探测测试（SPEC-DB-001 §2/§7 / PLAN-DB-001 Task 4）。

只接受“显式配置且版本匹配”的 accoreconsole.exe 与对应 Builder 插件 DLL；
任何 acad.exe 或任意 DLL 都不可用；探测是纯配置/文件系统检查，绝不启动进程。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dst_builder.infrastructure.autocad.capabilities import (
    CAD_CONSOLE_NOT_CONFIGURED,
    CAD_CONSOLE_NOT_CORE_CONSOLE,
    CAD_CONSOLE_NOT_FOUND,
    CAD_PLUGIN_NOT_BUILDER,
    CAD_PLUGIN_NOT_CONFIGURED,
    CAD_PLUGIN_NOT_FOUND,
    CAD_VERSION_UNSUPPORTED,
    SUPPORTED_CAD_VERSIONS,
    CadConfiguration,
    evaluate_cad_capability,
    load_cad_configuration,
)
from dst_builder.interfaces.api import create_builder_app

PROJECT_BODY = {
    "name": "示例工程",
    "stage": "施工图",
    "discipline": "建筑",
    "output_path": "D:/deliveries/example-package",
}


def _write_console(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    console = directory / "accoreconsole.exe"
    console.write_bytes(b"MZ fake core console")
    return console


def _write_plugin(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    plugin = directory / "DstBuilder.AutoCAD.dll"
    plugin.write_bytes(b"MZ fake builder plugin")
    return plugin


# ---------------------------------------------------------------------------
# evaluate_cad_capability
# ---------------------------------------------------------------------------


def test_unconfigured_tools_are_unavailable() -> None:
    status = evaluate_cad_capability("2020", console=None, plugin=None)

    assert status.cad_version == "2020"
    assert status.available is False
    assert status.unavailable_reason == CAD_CONSOLE_NOT_CONFIGURED
    assert status.console_path is None
    assert status.plugin_path is None


def test_missing_console_file_is_unavailable(tmp_path: Path) -> None:
    missing = tmp_path / "cad2016" / "accoreconsole.exe"
    plugin = _write_plugin(tmp_path / "plugin")

    status = evaluate_cad_capability("2016", console=missing, plugin=plugin)

    assert status.available is False
    assert status.unavailable_reason == CAD_CONSOLE_NOT_FOUND


def test_acad_exe_is_not_accepted_as_core_console(tmp_path: Path) -> None:
    """配置指向 acad.exe（而非 accoreconsole.exe）时不可用。"""
    directory = tmp_path / "acad"
    directory.mkdir()
    acad = directory / "acad.exe"
    acad.write_bytes(b"MZ full AutoCAD")
    plugin = _write_plugin(tmp_path / "plugin")

    status = evaluate_cad_capability("2020", console=acad, plugin=plugin)

    assert status.available is False
    assert status.unavailable_reason == CAD_CONSOLE_NOT_CORE_CONSOLE


def test_missing_plugin_file_is_unavailable(tmp_path: Path) -> None:
    console = _write_console(tmp_path / "cad2020")
    missing = tmp_path / "plugin" / "DstBuilder.AutoCAD.dll"

    status = evaluate_cad_capability("2020", console=console, plugin=missing)

    assert status.available is False
    assert status.unavailable_reason == CAD_PLUGIN_NOT_FOUND


def test_unconfigured_plugin_is_unavailable(tmp_path: Path) -> None:
    console = _write_console(tmp_path / "cad2020")

    status = evaluate_cad_capability("2020", console=console, plugin=None)

    assert status.available is False
    assert status.unavailable_reason == CAD_PLUGIN_NOT_CONFIGURED


def test_foreign_plugin_dll_is_rejected(tmp_path: Path) -> None:
    """Manager 插件 DLL 不是 Builder 插件，不得视为可用。"""
    console = _write_console(tmp_path / "cad2020")
    foreign_directory = tmp_path / "plugin"
    foreign_directory.mkdir()
    foreign = foreign_directory / "DstManager.AutoCAD.dll"
    foreign.write_bytes(b"MZ manager plugin")

    status = evaluate_cad_capability("2020", console=console, plugin=foreign)

    assert status.available is False
    assert status.unavailable_reason == CAD_PLUGIN_NOT_BUILDER


def test_non_dll_plugin_is_rejected(tmp_path: Path) -> None:
    console = _write_console(tmp_path / "cad2020")
    wrong_kind_directory = tmp_path / "plugin"
    wrong_kind_directory.mkdir()
    wrong_kind = wrong_kind_directory / "DstBuilder.AutoCAD.exe"
    wrong_kind.write_bytes(b"MZ not a dll")

    status = evaluate_cad_capability("2020", console=console, plugin=wrong_kind)

    assert status.available is False
    assert status.unavailable_reason == CAD_PLUGIN_NOT_BUILDER


@pytest.mark.parametrize("cad_version", SUPPORTED_CAD_VERSIONS)
def test_fully_configured_versions_are_available(tmp_path: Path, cad_version: str) -> None:
    console = _write_console(tmp_path / f"cad{cad_version}")
    plugin = _write_plugin(tmp_path / f"plugin{cad_version}")

    status = evaluate_cad_capability(cad_version, console=console, plugin=plugin)

    assert status.available is True
    assert status.unavailable_reason is None
    assert status.console_path == str(console)
    assert status.plugin_path == str(plugin)


def test_unsupported_cad_version_is_rejected(tmp_path: Path) -> None:
    console = _write_console(tmp_path / "cad2019")
    plugin = _write_plugin(tmp_path / "plugin2019")

    status = evaluate_cad_capability("2019", console=console, plugin=plugin)

    assert status.available is False
    assert status.unavailable_reason == CAD_VERSION_UNSUPPORTED


def test_probe_never_launches_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """探测是纯文件系统/配置检查：任何进程启动企图都视为缺陷。"""

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("能力探测不得启动进程")

    monkeypatch.setattr("subprocess.Popen", forbidden)
    console = _write_console(tmp_path / "cad2020")
    plugin = _write_plugin(tmp_path / "plugin2020")

    status = evaluate_cad_capability("2020", console=console, plugin=plugin)

    assert status.available is True


# ---------------------------------------------------------------------------
# 配置加载（沿用 Manager 的显式路径模式，不注册表/PATH 猜测）
# ---------------------------------------------------------------------------


def test_load_cad_configuration_reads_explicit_environment(tmp_path: Path) -> None:
    console_2016 = _write_console(tmp_path / "cad2016")
    plugin_2016 = _write_plugin(tmp_path / "plugin2016")
    console_2020 = _write_console(tmp_path / "cad2020")
    plugin_2020 = _write_plugin(tmp_path / "plugin2020")
    environ: Mapping[str, str] = {
        "DST_BUILDER_AUTOCAD_2016_CONSOLE": str(console_2016),
        "DST_BUILDER_AUTOCAD_2016_PLUGIN": str(plugin_2016),
        "DST_BUILDER_AUTOCAD_2020_CONSOLE": str(console_2020),
        "DST_BUILDER_AUTOCAD_2020_PLUGIN": str(plugin_2020),
    }

    configuration = load_cad_configuration(environ)

    assert configuration.console_2016 == console_2016
    assert configuration.plugin_2016 == plugin_2016
    assert configuration.console_2020 == console_2020
    assert configuration.plugin_2020 == plugin_2020


def test_load_cad_configuration_defaults_to_unconfigured_in_development() -> None:
    configuration = load_cad_configuration({})

    assert configuration.console_2016 is None
    assert configuration.plugin_2016 is None
    assert configuration.console_2020 is None
    assert configuration.plugin_2020 is None


# ---------------------------------------------------------------------------
# GET /api/cadabilities（只读 capability 响应）
# ---------------------------------------------------------------------------


def test_get_cadabilities_reports_unconfigured_versions(tmp_path: Path) -> None:
    client = TestClient(create_builder_app(project_root=tmp_path / "project"))

    response = client.get("/api/cadabilities")

    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    assert [item["cad_version"] for item in capabilities] == ["2016", "2020"]
    assert all(item["available"] is False for item in capabilities)
    assert all(
        item["unavailable_reason"] == CAD_CONSOLE_NOT_CONFIGURED for item in capabilities
    )


def test_get_cadabilities_reports_configured_version(tmp_path: Path) -> None:
    console = _write_console(tmp_path / "cad2020")
    plugin = _write_plugin(tmp_path / "plugin2020")
    configuration = CadConfiguration(console_2020=console, plugin_2020=plugin)
    client = TestClient(
        create_builder_app(project_root=tmp_path / "project", cad_configuration=configuration)
    )

    response = client.get("/api/cadabilities")

    assert response.status_code == 200
    by_version = {item["cad_version"]: item for item in response.json()["capabilities"]}
    assert by_version["2020"]["available"] is True
    assert by_version["2020"]["unavailable_reason"] is None
    assert by_version["2016"]["available"] is False
