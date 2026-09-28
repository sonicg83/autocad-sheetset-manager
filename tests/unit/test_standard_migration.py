"""旧用户标准草稿迁移与备份测试（PLAN-DM-046 Task 2）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dst_manager.infrastructure.standards.store import StandardStore, StandardStoreError

BACKUP_NAME = "PLAN-DM-046-pre-migration-2026-09-28"


def legacy_document(
    *,
    schema_version: int = 1,
    description: object = None,
    release_notes: object = "旧版说明原文",
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": schema_version,
        "standard_id": "old.water",
        "version": 4,
        "name": "旧版给排水标准",
        "supported_cad_versions": ["2020"],
        "properties": [],
        "dwg_naming": {"segments": [{"literal": "图纸"}]},
        "assets": [],
        "numbering": {"sequence_field": "subset.sequence", "digits": 2},
    }
    if description is not None:
        document["description"] = description
    if release_notes is not None:
        document["release_notes"] = release_notes
    return document


def legacy_store(tmp_path: Path, document: dict[str, object]):
    standards_root = tmp_path / "standards"
    official_root = standards_root / "official"
    user_root = standards_root / "user"
    draft_dir = user_root / "drafts" / "draft-legacy"
    draft_dir.mkdir(parents=True)
    source = draft_dir / "document.json"
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return official_root, user_root, source


@pytest.mark.parametrize("schema_version", [1, 2])
def test_initialization_backups_and_migrates_legacy_draft_idempotently(
    tmp_path: Path, schema_version: int
) -> None:
    original = legacy_document(schema_version=schema_version)
    official_root, user_root, source = legacy_store(tmp_path, original)
    original_bytes = source.read_bytes()

    store = StandardStore(official_root=official_root, user_root=user_root)
    migrated = store.get_draft("draft-legacy")

    assert migrated is not None
    assert migrated.document["schema_version"] == 3
    assert migrated.document["published_at"] is None
    assert migrated.document["description"] == "旧版说明原文"
    assert "release_notes" not in migrated.document
    assert "version" not in migrated.document
    standard_id = str(migrated.document["standard_id"])
    assert len(standard_id) == 36
    assert standard_id[14] == "4"

    backup_dir = tmp_path / "backups" / BACKUP_NAME
    assert (backup_dir / "standards" / "user" / "drafts" / "draft-legacy" / "document.json").read_bytes() == original_bytes
    report = json.loads((backup_dir / "migration-report.json").read_text(encoding="utf-8"))
    assert report["migrated_count"] == 1
    assert report["description_conflict_count"] == 0
    assert set(report) <= {"format", "migrated_count", "description_conflict_count", "result"}

    reopened = StandardStore(
        official_root=tmp_path / "standards" / "official",
        user_root=tmp_path / "standards" / "user",
    )
    reloaded = reopened.get_draft("draft-legacy")
    assert reloaded is not None
    assert reloaded.document["standard_id"] == standard_id


def test_description_wins_and_conflict_report_contains_no_private_text(
    tmp_path: Path,
) -> None:
    document = legacy_document(
        description="明确描述",
        release_notes="不应进入迁移报告的旧文字",
    )
    official_root, user_root, _ = legacy_store(tmp_path, document)
    store = StandardStore(official_root=official_root, user_root=user_root)

    migrated = store.get_draft("draft-legacy")
    assert migrated is not None
    assert migrated.document["description"] == "明确描述"
    report_text = (
        tmp_path
        / "backups"
        / BACKUP_NAME
        / "migration-report.json"
    ).read_text(encoding="utf-8")
    assert "description_conflict_count\": 1" in report_text
    assert "明确描述" not in report_text
    assert "不应进入迁移报告的旧文字" not in report_text


def test_migration_write_failure_keeps_original_draft_and_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dst_manager.infrastructure.standards import migration

    document = legacy_document()
    official_root, user_root, source = legacy_store(tmp_path, document)
    original_bytes = source.read_bytes()

    real_write = migration.atomic_write_text

    def fail_write(*args, **kwargs):
        if Path(args[0]).name == "document.json":
            raise OSError("injected migration write failure")
        return real_write(*args, **kwargs)

    monkeypatch.setattr(migration, "atomic_write_text", fail_write)

    with pytest.raises(StandardStoreError, match="STANDARD_MIGRATION_FAILED"):
        StandardStore(
            official_root=official_root,
            user_root=user_root,
        )

    assert source.read_bytes() == original_bytes
    backup_file = (
        tmp_path
        / "backups"
        / BACKUP_NAME
        / "standards"
        / "user"
        / "drafts"
        / "draft-legacy"
        / "document.json"
    )
    assert backup_file.read_bytes() == original_bytes


def test_partial_migration_can_resume_without_reassigning_completed_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dst_manager.infrastructure.standards import migration

    official_root, user_root, first_source = legacy_store(tmp_path, legacy_document())
    second_dir = user_root / "drafts" / "draft-two"
    second_dir.mkdir()
    second_source = second_dir / "document.json"
    second_source.write_text(
        json.dumps(legacy_document(), ensure_ascii=False), encoding="utf-8"
    )
    second_document = json.loads(second_source.read_text(encoding="utf-8"))
    second_document["standard_id"] = "old.water.two"
    second_document["name"] = "另一旧草稿"
    second_source.write_text(
        json.dumps(second_document, ensure_ascii=False), encoding="utf-8"
    )
    real_write = migration.atomic_write_text

    def fail_second_document(path, content, **kwargs):
        if Path(path).parent.name == "draft-two":
            raise OSError("injected second draft failure")
        return real_write(path, content, **kwargs)

    with monkeypatch.context() as patch_context:
        patch_context.setattr(migration, "atomic_write_text", fail_second_document)
        with pytest.raises(StandardStoreError, match="STANDARD_MIGRATION_FAILED"):
            StandardStore(official_root=official_root, user_root=user_root)

    first_after_partial = json.loads(first_source.read_text(encoding="utf-8"))
    assert first_after_partial["schema_version"] == 3
    first_id = first_after_partial["standard_id"]
    assert json.loads(second_source.read_text(encoding="utf-8"))["schema_version"] == 1

    reopened = StandardStore(official_root=official_root, user_root=user_root)
    resumed_first = reopened.get_draft("draft-legacy")
    resumed_second = reopened.get_draft("draft-two")
    assert resumed_first is not None and resumed_second is not None
    assert resumed_first.document["standard_id"] == first_id
    assert resumed_second.document["schema_version"] == 3


def test_existing_complete_backup_is_verified_before_migration(
    tmp_path: Path,
) -> None:
    import shutil

    official_root, user_root, source = legacy_store(tmp_path, legacy_document())
    standards_root = tmp_path / "standards"
    backup_dir = tmp_path / "backups" / BACKUP_NAME
    shutil.copytree(standards_root, backup_dir / "standards")
    original_bytes = source.read_bytes()

    store = StandardStore(official_root=official_root, user_root=user_root)

    migrated = store.get_draft("draft-legacy")
    assert migrated is not None and migrated.document["schema_version"] == 3
    assert (
        backup_dir
        / "standards"
        / "user"
        / "drafts"
        / "draft-legacy"
        / "document.json"
    ).read_bytes() == original_bytes
    manifest = json.loads((backup_dir / "sha256-manifest.json").read_text(encoding="utf-8"))
    assert manifest["file_count"] == len(manifest["files"]) == 1


def test_incomplete_backup_blocks_migration_without_changing_source(
    tmp_path: Path,
) -> None:
    official_root, user_root, source = legacy_store(tmp_path, legacy_document())
    original_bytes = source.read_bytes()
    backup_file = (
        tmp_path
        / "backups"
        / BACKUP_NAME
        / "standards"
        / "user"
        / "drafts"
        / "draft-legacy"
        / "document.json"
    )
    backup_file.parent.mkdir(parents=True)
    backup_file.write_text("incomplete", encoding="utf-8")

    with pytest.raises(StandardStoreError, match="STANDARD_BACKUP_INVALID"):
        StandardStore(
            official_root=official_root,
            user_root=user_root,
        )

    assert source.read_bytes() == original_bytes
