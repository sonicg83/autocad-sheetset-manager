
from concurrent.futures import ThreadPoolExecutor

import pytest

from dst_manager.config import Settings
from dst_manager.infrastructure.drafts import DraftConflictError, DraftStore


def _draft(version: int = 0) -> dict:
    return {
        "schema_version": 1,
        "workspace_id": "workspace-1",
        "base_revision_id": "revision-1",
        "repair_status": "VALID",
        "version": version,
        "cursor": 1,
        "actions": [
            {
                "id": "action-1",
                "kind": "command_batch",
                "label": "批量更新专业",
                "commands": [
                    {
                        "type": "update_sheet_properties",
                        "sheet_id": "sheet-1",
                        "custom_properties": {"专业": "燃气"},
                    },
                ],
            },
        ],
    }


def test_default_draft_directory_is_absolute_and_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.chdir(tmp_path)

    settings = Settings(data_dir=tmp_path / "data")

    assert settings.draft_dir == (tmp_path / "local-app-data" / "dst-manager" / "drafts").resolve()
    assert settings.draft_dir.is_absolute()


def test_draft_store_uses_atomic_versioned_writes_and_detects_conflicts(tmp_path):
    store = DraftStore(tmp_path / "drafts")

    saved = store.save("workspace-1", _draft(), expected_version=0)
    loaded = store.load("workspace-1")

    assert saved["version"] == 1
    assert loaded == {"draft": saved, "corrupted": False}
    with pytest.raises(DraftConflictError):
        store.save("workspace-1", _draft(), expected_version=0)


def test_concurrent_draft_writes_never_silently_overwrite_newer_version(tmp_path):
    store = DraftStore(tmp_path / "drafts")

    def save_once():
        try:
            return store.save("workspace-1", _draft(), expected_version=0)["version"]
        except DraftConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save_once(), range(2)))

    assert sorted(results, key=str) == [1, "conflict"]
    assert store.load("workspace-1")["draft"]["version"] == 1


def test_corrupt_draft_is_quarantined_without_overwriting_it(tmp_path):
    draft_dir = tmp_path / "drafts"
    draft_dir.mkdir()
    source = draft_dir / "workspace-1.json"
    source.write_text("{broken", encoding="utf-8")
    store = DraftStore(draft_dir)

    result = store.load("workspace-1")

    assert result == {"draft": None, "corrupted": True}
    assert not source.exists()
    quarantined = list(draft_dir.glob("workspace-1.corrupt-*.json"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{broken"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda draft: draft.update(schema_version=2),
        lambda draft: draft.update(version=-1),
        lambda draft: draft.update(cursor=2),
        lambda draft: draft["actions"][0]["commands"][0].update(type="unknown"),
        lambda draft: draft["actions"][0]["commands"][0].update(unexpected=True),
        lambda draft: draft["actions"][0]["commands"].__setitem__(
            0,
            {"type": "update_sheet_set", "name": ""},
        ),
        lambda draft: draft["actions"][0]["commands"].__setitem__(
            0,
            {
                "type": "insert_sheet",
                "target_subset_id": "subset-1",
                "placement": "after",
                "count": 1,
                "source": {"type": "template_layout", "file": "relative.dwt", "layout": "A1"},
            },
        ),
        lambda draft: draft["actions"][0]["commands"].__setitem__(
            0,
            {
                "type": "insert_subset",
                "placement": "after",
                "title": "危险/标题",
                "initial_sheet_count": 1,
                "source": {"type": "template_layout", "file": "C:\\template.dwt", "layout": "A1"},
                "base_template_file": "C:\\template.dwt",
            },
        ),
        lambda draft: draft["actions"][0]["commands"].__setitem__(
            0,
            {
                "type": "add_custom_property",
                "property_type": "sheet",
                "name": "专业",
                "default_value": "非法\u0001值",
            },
        ),
    ],
)
def test_semantically_corrupt_draft_is_quarantined(tmp_path, mutation):
    draft_dir = tmp_path / "drafts"
    draft_dir.mkdir()
    source = draft_dir / "workspace-1.json"
    draft = _draft(version=1)
    mutation(draft)
    source.write_text(__import__("json").dumps(draft), encoding="utf-8")

    result = DraftStore(draft_dir).load("workspace-1")

    assert result == {"draft": None, "corrupted": True}
    assert not source.exists()
    assert len(list(draft_dir.glob("workspace-1.corrupt-*.json"))) == 1


def test_concurrent_corrupt_draft_loads_create_one_quarantine(tmp_path):
    draft_dir = tmp_path / "drafts"
    draft_dir.mkdir()
    source = draft_dir / "workspace-1.json"
    invalid = _draft(version=1)
    invalid["cursor"] = 2
    source.write_text(__import__("json").dumps(invalid), encoding="utf-8")
    store = DraftStore(draft_dir)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.load("workspace-1"), range(2)))

    assert sum(result["corrupted"] for result in results) == 1
    assert all(result["draft"] is None for result in results)
    assert len(list(draft_dir.glob("workspace-1.corrupt-*.json"))) == 1


def test_draft_store_rejects_workspace_path_traversal(tmp_path):
    store = DraftStore(tmp_path / "drafts")

    with pytest.raises(ValueError, match="DRAFT_WORKSPACE_ID_INVALID"):
        store.load("../outside")

    assert not (tmp_path / "outside.json").exists()


def _insert_subset_draft_command(
    *,
    base_template_file: str = "C:\\图纸基底.dwg",
    source: dict | None = None,
) -> dict:
    return {
        "type": "insert_subset",
        "placement": "after",
        "title": "新分册",
        "initial_sheet_count": 2,
        "source": source or {"type": "template_layout", "file": "C:\\template.dwt", "layout": "A1模板"},
        "base_template_file": base_template_file,
    }


def _insert_sheet_draft_command(*, source: dict) -> dict:
    return {
        "type": "insert_sheet",
        "target_subset_id": "subset-1",
        "ordinal": 1,
        "placement": "after",
        "count": 1,
        "source": source,
    }


def _write_and_load(tmp_path, draft: dict) -> dict:
    import json

    draft_dir = tmp_path / "drafts"
    draft_dir.mkdir()
    source = draft_dir / "workspace-1.json"
    source.write_text(json.dumps(draft), encoding="utf-8")
    return DraftStore(draft_dir).load("workspace-1")


def test_draft_with_insert_subset_base_template_file_loads_clean(tmp_path):
    """SPEC-DM-008 F-04：含必填 base_template_file 的 insert_subset 命令不再被形状校验器误判损坏。"""
    draft = _draft(version=1)
    draft["actions"][0]["commands"] = [_insert_subset_draft_command()]

    result = _write_and_load(tmp_path, draft)

    assert result == {"draft": draft, "corrupted": False}


def test_draft_existing_snapshot_source_allows_empty_file_and_layout(tmp_path):
    """SPEC-DM-008 F-02：existing_snapshot 来源允许空 file/layout，template_layout 仍要求非空。"""
    draft = _draft(version=1)
    draft["actions"][0]["commands"] = [
        _insert_sheet_draft_command(source={"type": "existing_snapshot", "file": "", "layout": ""}),
    ]

    result = _write_and_load(tmp_path, draft)

    assert result["corrupted"] is False
    assert result["draft"]["actions"][0]["commands"][0]["source"] == {
        "type": "existing_snapshot",
        "file": "",
        "layout": "",
    }


def test_draft_existing_snapshot_source_still_validates_nonempty_path(tmp_path):
    """existing_snapshot 非空 file 仍走绝对路径校验（越界防御保留）。"""
    draft = _draft(version=1)
    draft["actions"][0]["commands"] = [
        _insert_sheet_draft_command(source={"type": "existing_snapshot", "file": "relative.dwg", "layout": ""}),
    ]

    result = _write_and_load(tmp_path, draft)

    assert result == {"draft": None, "corrupted": True}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda command: command.pop("base_template_file"),
        lambda command: command.update(base_template_file="relative.dwg"),
    ],
)
def test_draft_insert_subset_missing_or_invalid_base_template_is_quarantined(tmp_path, mutation):
    draft = _draft(version=1)
    command = _insert_subset_draft_command()
    mutation(command)
    draft["actions"][0]["commands"] = [command]

    result = _write_and_load(tmp_path, draft)

    assert result == {"draft": None, "corrupted": True}


def test_draft_template_layout_source_rejects_empty_file(tmp_path):
    draft = _draft(version=1)
    draft["actions"][0]["commands"] = [
        _insert_sheet_draft_command(source={"type": "template_layout", "file": "", "layout": "A1"}),
    ]

    result = _write_and_load(tmp_path, draft)

    assert result == {"draft": None, "corrupted": True}
