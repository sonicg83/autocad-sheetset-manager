import json
from pathlib import Path

import pytest

from dst_manager.settings.resolver import SettingsResolver
from dst_manager.settings.store import UserSettingsStore


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch, tmp_path):
    # Settings 的 env_file=".env" 按 cwd 解析：开发机常存在真实 .env（gitignored），
    # 切到 tmp_path 保证"env 未设置"的断言不受本机 .env 污染
    monkeypatch.chdir(tmp_path)


def _resolver(tmp_path: Path, values: object, version: int = 1) -> SettingsResolver:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": version, "config_revision": 4, "values": values}), encoding="utf-8")
    return SettingsResolver(UserSettingsStore(path))


def test_file_only_stores_overrides_and_merges_over_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    snap = _resolver(tmp_path, {"cad_timeout_seconds": 900}).load_snapshot()
    assert snap.settings.cad_timeout_seconds == 900          # file > env
    src = snap.sources["cad_timeout_seconds"]
    assert (src.source, src.has_file_override) == ("file", True)


def test_source_is_env_when_no_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    snap = _resolver(tmp_path, {}).load_snapshot()
    assert snap.settings.cad_timeout_seconds == 777
    assert snap.sources["cad_timeout_seconds"].source == "env"


def test_source_is_file_even_when_value_equals_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    snap = _resolver(tmp_path, {"cad_timeout_seconds": 777}).load_snapshot()
    assert snap.sources["cad_timeout_seconds"].source == "file"  # 不从终值反推


def test_empty_string_path_normalizes_to_none(tmp_path) -> None:
    snap = _resolver(tmp_path, {"autocad_2016_console": "   "}).load_snapshot()
    assert snap.settings.autocad_2016_console is None        # 绝不解析为 cwd


def test_relative_path_still_resolves_absolute(tmp_path) -> None:
    snap = _resolver(tmp_path, {"autocad_2016_console": "console/accoreconsole.exe"}).load_snapshot()
    assert snap.settings.autocad_2016_console.is_absolute()  # 兼容现状


def test_newer_schema_blocks_but_falls_back(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    snap = _resolver(tmp_path, {"cad_timeout_seconds": 900}, version=99).load_snapshot()
    assert snap.schema_blocked and snap.config_revision == 4
    assert snap.settings.cad_timeout_seconds == 777          # 覆盖值被忽略


def test_env_unset_paths_stay_none_in_dev(tmp_path) -> None:
    snap = _resolver(tmp_path, {}).load_snapshot()
    assert snap.settings.autocad_2016_console is None        # 开发态默认 None
