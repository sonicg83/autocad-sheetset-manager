"""图纸集列偏好应用目录 JSON 原子存储单测（PLAN-DM-015 任务 2）。

验证：两个工作区 ID 隔离、同一 ID 重开恢复、坏 JSON/未知 schema/字段与
数量限制被拒绝、数据目录不可写时报 IO 错、只读 load 不创建目录、写入
不触碰工程目录、失败保留旧文件且无残留临时文件。workspace_id 只参与
SHA-256 摘要，绝不作为路径组成部分。
"""

import hashlib
import json

import pytest

from dst_manager.infrastructure.sheet_preferences import (
    MAX_PROPERTIES,
    InvalidSheetPreferencesError,
    SheetPreferences,
    SheetPreferencesError,
)


def _preferences(**overrides):
    data = {
        "schemaVersion": 1,
        "file": True,
        "layout": False,
        "subsetAll": True,
        "subsetSingle": False,
        "properties": {"sheet:比例": True, "sheet:图幅": False},
    }
    data.update(overrides)
    return data


def _sheets_dir(tmp_path):
    return tmp_path / "app-data" / "ui-preferences" / "sheets"


def test_preferences_read_does_not_create_directory(tmp_path):
    from dst_manager.infrastructure.sheet_preferences import SheetPreferences

    store = SheetPreferences(tmp_path / "app-data")
    assert store.load("workspace-1") is None
    assert not (tmp_path / "app-data").exists()


def test_preferences_two_workspaces_are_isolated(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    store.save("workspace-1", _preferences(file=True, layout=False))
    store.save("workspace-2", _preferences(file=False, layout=True))
    assert store.load("workspace-1")["layout"] is False
    assert store.load("workspace-1")["file"] is True
    assert store.load("workspace-2")["layout"] is True
    assert store.load("workspace-2")["file"] is False


def test_preferences_same_workspace_roundtrips_across_instances(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    store.save("workspace-1", _preferences(properties={"sheet:比例": True}))
    # 新实例（模拟应用重开）仍能恢复同一工作区偏好
    again = SheetPreferences(tmp_path / "app-data")
    assert again.load("workspace-1") == _preferences(properties={"sheet:比例": True})


def test_preferences_missing_preferences_returns_none(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    store.save("workspace-1", _preferences())
    assert store.load("workspace-2") is None


def test_preferences_bad_json_raises_invalid(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    store.save("workspace-1", _preferences())
    target = next(_sheets_dir(tmp_path).glob("*.json"))
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(InvalidSheetPreferencesError):
        store.load("workspace-1")


def test_preferences_unknown_schema_is_rejected(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    with pytest.raises(InvalidSheetPreferencesError):
        store.save("workspace-1", _preferences(schemaVersion=2))


def test_preferences_missing_field_is_rejected(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    bad = _preferences()
    del bad["layout"]
    with pytest.raises(InvalidSheetPreferencesError):
        store.save("workspace-1", bad)


def test_preferences_non_boolean_field_is_rejected(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    with pytest.raises(InvalidSheetPreferencesError):
        store.save("workspace-1", _preferences(file="yes"))


def test_preferences_property_key_must_be_sheet_prefixed(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    with pytest.raises(InvalidSheetPreferencesError):
        store.save("workspace-1", _preferences(properties={"比例": True}))


def test_preferences_property_value_must_be_boolean(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    with pytest.raises(InvalidSheetPreferencesError):
        store.save("workspace-1", _preferences(properties={"sheet:比例": "1:100"}))


def test_preferences_properties_count_limit_is_enforced(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    too_many = {f"sheet:p{i}": True for i in range(MAX_PROPERTIES + 1)}
    with pytest.raises(InvalidSheetPreferencesError):
        store.save("workspace-1", _preferences(properties=too_many))


def test_preferences_save_io_error_when_data_dir_blocked(tmp_path):
    (tmp_path / "app-data" / "ui-preferences").mkdir(parents=True)
    # sheets 被文件占位 → mkdir(parents=True) 抛 FileExistsError（OSError 子类）→ IO 错
    (tmp_path / "app-data" / "ui-preferences" / "sheets").write_text("occupied", encoding="utf-8")
    store = SheetPreferences(tmp_path / "app-data")
    with pytest.raises(SheetPreferencesError):
        store.save("workspace-1", _preferences())


def test_preferences_save_failure_keeps_previous_file(tmp_path, monkeypatch):
    store = SheetPreferences(tmp_path / "app-data")
    store.save("workspace-1", _preferences(file=True))
    target = next(_sheets_dir(tmp_path).glob("*.json"))
    before = target.read_text(encoding="utf-8")

    def boom(src, dst):
        raise OSError("模拟磁盘故障")

    monkeypatch.setattr("dst_manager.infrastructure.sheet_preferences.os.replace", boom)
    with pytest.raises(SheetPreferencesError):
        store.save("workspace-1", _preferences(file=False))
    assert target.read_text(encoding="utf-8") == before


def test_preferences_atomic_write_leaves_no_temp_file(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    store.save("workspace-1", _preferences())
    assert list(_sheets_dir(tmp_path).glob("*.tmp")) == []


def test_preferences_save_does_not_touch_project_directory(tmp_path):
    project = tmp_path / "工程"
    project.mkdir()
    dst = project / "图纸集.dst"
    dst.write_bytes(b"fake")
    before_mtime = dst.stat().st_mtime_ns
    store = SheetPreferences(tmp_path / "app-data")
    store.save("workspace-1", _preferences())
    assert dst.read_bytes() == b"fake"
    assert dst.stat().st_mtime_ns == before_mtime
    assert not (project / ".dst-manager").exists()


def test_preferences_workspace_id_is_hashed_not_a_path_part(tmp_path):
    """workspace_id 只参与 SHA-256 摘要，绝不进入路径（防止路径注入/越界写入）。"""
    store = SheetPreferences(tmp_path / "app-data")
    evil = "../../outside"
    store.save(evil, _preferences())
    names = [path.name for path in _sheets_dir(tmp_path).glob("*.json")]
    assert names == [hashlib.sha256(evil.encode("utf-8")).hexdigest() + ".json"]
    assert not (tmp_path / "outside").exists()


def test_preferences_load_returns_stored_json(tmp_path):
    store = SheetPreferences(tmp_path / "app-data")
    store.save("workspace-1", _preferences())
    target = next(_sheets_dir(tmp_path).glob("*.json"))
    assert json.loads(target.read_text(encoding="utf-8")) == _preferences()
