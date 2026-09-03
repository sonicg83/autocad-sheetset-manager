"""PLAN-DM-011 Task 3：布局名读取服务的单元测试。

覆盖：假 executor 写 sidecar 后的两次调用（第二次 cached=True 且 layouts 一致）、
原 DWG 未被修改、.dwt 同样复制为 source.dwg 副本路径、executor 失败转换为
LAYOUT_READ_FAILED(502)，以及 Task 1 遗留的 Database.get_layout_names/
save_layout_names 行为（roundtrip / upsert / 缺失 -> None）。
"""

import json
from pathlib import Path

import pytest

from dst_manager.application.service import ApplicationError, DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.autocad.worker import CoreConsoleResult
from dst_manager.infrastructure.filesystem.publisher import file_sha256
from dst_manager.infrastructure.persistence import Database


def _available_settings(tmp_path: Path) -> Settings:
    """构造 capability 可用的 Settings（dummy console/plugin 文件，仅满足 is_file 检查）。"""
    console = tmp_path / "accoreconsole.exe"
    console.write_bytes(b"console")
    plugin = tmp_path / "DstManager.AutoCAD.dll"
    plugin.write_bytes(b"plugin")
    return Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=console,
        autocad_2016_plugin=plugin,
        autocad_2020_console=console,
        autocad_2020_plugin=plugin,
    )


def _fake_run(payload: dict, captured: list) -> callable:
    def run(capability, drawing: Path, script: Path, timeout: int) -> CoreConsoleResult:
        captured.append(drawing)
        drawing.with_suffix(".dst-layout-names.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return CoreConsoleResult(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=0,
            peak_memory_bytes=None,
        )

    return run


def test_get_layout_names_writes_sidecar_then_hits_cache_and_keeps_dwg_untouched(tmp_path, monkeypatch):
    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"fake dwg bytes")
    before = source.read_bytes()
    captured: list[Path] = []
    monkeypatch.setattr(
        "dst_manager.application.service.CoreConsoleExecutor.run",
        staticmethod(_fake_run({"version": 1, "layouts": ["001 平面", "002 立面"]}, captured)),
    )
    service = DstManagerService(_available_settings(tmp_path))
    expected_hash = file_sha256(source)

    first = service.get_layout_names(source, "2020")
    second = service.get_layout_names(source, "2020")

    assert first == {"layouts": ["001 平面", "002 立面"], "cached": False, "file_hash": expected_hash}
    assert second == {"layouts": ["001 平面", "002 立面"], "cached": True, "file_hash": expected_hash}
    assert len(captured) == 1, "缓存命中不得再次调用 Core Console"
    assert captured[0].name == "source.dwg"
    assert source.read_bytes() == before, "原 DWG 不得被修改"


def test_get_layout_names_dwt_also_copied_to_source_dwg(tmp_path, monkeypatch):
    template = tmp_path / "template.dwt"
    template.write_bytes(b"fake template bytes")
    before = template.read_bytes()
    captured: list[Path] = []
    monkeypatch.setattr(
        "dst_manager.application.service.CoreConsoleExecutor.run",
        staticmethod(_fake_run({"version": 1, "layouts": ["A3", "A4"]}, captured)),
    )
    service = DstManagerService(_available_settings(tmp_path))

    result = service.get_layout_names(template, "2016")

    assert result["cached"] is False
    assert result["layouts"] == ["A3", "A4"]
    assert len(captured) == 1
    assert captured[0].name == "source.dwg", ".dwt 也必须复制为 source.dwg 副本运行"
    assert template.read_bytes() == before


def test_get_layout_names_unconfigured_capability_raises_clear_error(tmp_path):
    """CAD 能力未配置（缺 console/plugin）时必须在调用 Core Console 前给出可操作的明确错误，
    不得误报为"DWG 可能正被 AutoCAD 占用"（能力未配置是环境问题，与执行失败提示分开）。"""
    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"fake dwg bytes")

    # 显式传 None 覆盖 env_file=".env"：测试不得依赖宿主机 CAD 配置
    service = DstManagerService(
        Settings(
            data_dir=tmp_path / "data",
            autocad_2016_console=None,
            autocad_2016_plugin=None,
            autocad_2020_console=None,
            autocad_2020_plugin=None,
        )
    )

    with pytest.raises(ApplicationError) as excinfo:
        service.get_layout_names(source, "2020")

    assert excinfo.value.code == "CAD_CAPABILITY_UNAVAILABLE"


def test_get_layout_names_converts_executor_failure_to_502(tmp_path, monkeypatch):
    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"fake dwg bytes")

    def failing_run(capability, drawing: Path, script: Path, timeout: int):
        raise RuntimeError("accoreconsole 退出码 1")  # capability 已可用，纯执行失败

    monkeypatch.setattr(
        "dst_manager.application.service.CoreConsoleExecutor.run",
        staticmethod(failing_run),
    )
    service = DstManagerService(_available_settings(tmp_path))

    with pytest.raises(ApplicationError) as excinfo:
        service.get_layout_names(source, "2020")

    assert excinfo.value.code == "LAYOUT_READ_FAILED"
    assert excinfo.value.status_code == 502


def test_get_layout_names_no_sidecar_after_success_raises_502(tmp_path, monkeypatch):
    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"fake dwg bytes")

    def success_without_sidecar(capability, drawing: Path, script: Path, timeout: int) -> CoreConsoleResult:
        return CoreConsoleResult(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=0,
            peak_memory_bytes=None,
        )

    monkeypatch.setattr(
        "dst_manager.application.service.CoreConsoleExecutor.run",
        staticmethod(success_without_sidecar),
    )
    service = DstManagerService(_available_settings(tmp_path))

    with pytest.raises(ApplicationError) as excinfo:
        service.get_layout_names(source, "2020")

    assert excinfo.value.code == "LAYOUT_READ_FAILED"
    assert excinfo.value.status_code == 502


def test_layout_name_cache_database_roundtrip_upsert_and_missing(tmp_path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")

    assert database.get_layout_names("missing-hash") is None

    database.save_layout_names("h1", str(tmp_path / "a.dwg"), ["001", "002"])
    assert database.get_layout_names("h1") == ["001", "002"]

    database.save_layout_names("h1", str(tmp_path / "b.dwg"), ["003"])
    assert database.get_layout_names("h1") == ["003"]
    assert database.get_layout_names("h2") is None
