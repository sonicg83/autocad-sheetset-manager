"""旧标准格式不再迁移或进入当前标准库。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from dst_manager.infrastructure.standards.store import StandardStore


def _legacy_document(*, schema_version: int = 2) -> dict[str, object]:
    from creation_xlsx_fixtures import STANDARD_DOCUMENT

    document = copy.deepcopy(STANDARD_DOCUMENT)
    document.update(
        {
            "schema_version": schema_version,
            "standard_id": "legacy.water",
            "version": 2,
            "release_notes": "旧版说明",
            "assets": [],
        }
    )
    document.pop("published_at", None)
    document.pop("description", None)
    return document


def test_legacy_published_packages_are_ignored_without_migration(
    tmp_path: Path,
) -> None:
    user_root = tmp_path / "standards" / "user"
    published_root = user_root / "published"
    first_dir = published_root / "legacy.water" / "2"
    second_dir = published_root / "legacy.water" / "5"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    first_document = first_dir / "document.json"
    second_document = second_dir / "document.json"
    first_document.write_text(json.dumps(_legacy_document()), encoding="utf-8")
    second_document.write_text(json.dumps(_legacy_document()), encoding="utf-8")
    original_bytes = (first_document.read_bytes(), second_document.read_bytes())

    store = StandardStore(
        official_root=tmp_path / "standards" / "official", user_root=user_root
    )

    assert store.list() == []
    assert (first_document.read_bytes(), second_document.read_bytes()) == original_bytes
    assert sorted(path.name for path in published_root.iterdir()) == ["legacy.water"]
    assert not (tmp_path / "backups").exists()


def test_legacy_drafts_are_ignored_without_migration(tmp_path: Path) -> None:
    user_root = tmp_path / "standards" / "user"
    draft_dir = user_root / "drafts" / "draft-legacy"
    draft_dir.mkdir(parents=True)
    document_path = draft_dir / "document.json"
    document_path.write_text(json.dumps(_legacy_document(schema_version=1)), encoding="utf-8")
    original_bytes = document_path.read_bytes()

    store = StandardStore(
        official_root=tmp_path / "standards" / "official", user_root=user_root
    )

    assert store.list() == []
    assert store.get_draft("draft-legacy") is None
    assert document_path.read_bytes() == original_bytes
    assert not (tmp_path / "backups").exists()


def test_unknown_publication_time_is_not_treated_as_a_current_standard(
    tmp_path: Path,
) -> None:
    from creation_xlsx_fixtures import STANDARD_DOCUMENT

    user_root = tmp_path / "standards" / "user"
    standard_id = "00000000-0000-4000-8000-000000000046"
    package_dir = user_root / "published" / standard_id
    package_dir.mkdir(parents=True)
    document = copy.deepcopy(STANDARD_DOCUMENT)
    document["standard_id"] = standard_id
    document["published_at"] = None
    (package_dir / "document.json").write_text(
        json.dumps(document), encoding="utf-8"
    )

    store = StandardStore(
        official_root=tmp_path / "standards" / "official", user_root=user_root
    )

    assert store.list() == []
