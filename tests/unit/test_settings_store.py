# tests/unit/test_settings_store.py
import json
from pathlib import Path

import pytest

from dst_manager.settings.store import (
    SCHEMA_VERSION,
    SettingsSchemaNewer,
    SettingsSchemaOlder,
    UserSettingsStore,
)


def test_missing_file_returns_defaults(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    assert store.load() == ({}, 0, ["SETTINGS_FILE_MISSING"])


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    revision = store.save_overrides({"cad_timeout_seconds": 900}, previous_revision=0)
    assert revision == 1
    values, loaded_revision, diagnostics = store.load()
    assert values == {"cad_timeout_seconds": 900}
    assert loaded_revision == 1 and diagnostics == []


def test_written_file_contains_schema_and_revision(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save_overrides({}, previous_revision=5)
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data == {"schema_version": SCHEMA_VERSION, "config_revision": 6, "values": {}}


def test_corrupt_file_backed_up_and_reset(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{截断的 JSON", encoding="utf-8")
    store = UserSettingsStore(path)
    values, revision, diagnostics = store.load()
    assert values == {} and revision == 0
    assert diagnostics == ["SETTINGS_FILE_CORRUPT"]
    assert not path.exists()  # 原文件已重命名为备份
    backups = list(tmp_path.glob("settings.json.corrupt-*"))
    assert len(backups) == 1 and "截断" in backups[0].read_text(encoding="utf-8")


def test_unknown_newer_schema_left_untouched(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    original = json.dumps({"schema_version": SCHEMA_VERSION + 1, "config_revision": 3, "values": {"x": 1}, "future_field": True})
    path.write_text(original, encoding="utf-8")
    with pytest.raises(SettingsSchemaNewer):
        UserSettingsStore(path).load()
    assert path.read_text(encoding="utf-8") == original  # 字节不变


def test_older_schema_raises(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION - 1, "config_revision": 1, "values": {}}), encoding="utf-8")
    with pytest.raises(SettingsSchemaOlder):
        UserSettingsStore(path).load()


def test_no_temp_files_left_behind(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save_overrides({"a": 1}, previous_revision=0)
    assert list(tmp_path.iterdir()) == [tmp_path / "settings.json"]
