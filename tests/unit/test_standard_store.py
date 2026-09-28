"""UUID 标准库、发布事务与资产边界测试（PLAN-DM-046 Task 2）。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from pathlib import Path

import pytest
from creation_xlsx_fixtures import STANDARD_DOCUMENT

from dst_manager.domain.standards import parse_published_standard_document
from dst_manager.infrastructure.creation_drafts import CreationDraftStore
from dst_manager.infrastructure.standards.delete_transaction import (
    StandardDeleteTransaction,
)
from dst_manager.infrastructure.standards.store import (
    StandardStore,
    StandardStoreError,
)

OFFICIAL_ID = "123e4567-e89b-42d3-a456-426614174100"
FIRST_ID = "123e4567-e89b-42d3-a456-426614174101"
SECOND_ID = "123e4567-e89b-42d3-a456-426614174102"
THIRD_ID = "123e4567-e89b-42d3-a456-426614174103"
PUBLISHED_AT = 1_800_000_000_123


def standard_document(
    standard_id: str = FIRST_ID,
    *,
    name: str = "用户给排水标准",
    description: str = "测试标准说明",
    mapping_target: str = "GS",
    published: bool = False,
) -> dict[str, object]:
    document = copy.deepcopy(STANDARD_DOCUMENT)
    document.update(
        standard_id=standard_id,
        published_at=PUBLISHED_AT if published else None,
        description=description,
        name=name,
        assets=[],
    )
    for prop in document["properties"]:
        if isinstance(prop, dict) and prop.get("kind") == "mapping":
            for row in prop.get("mapping", []):
                if isinstance(row, dict):
                    row["value"] = mapping_target
    return document


def write_published(root: Path, document: dict[str, object]) -> Path:
    standard = parse_published_standard_document(document)
    target = root / standard.standard_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "document.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )
    return target


@pytest.fixture
def store(tmp_path: Path) -> StandardStore:
    standards_root = tmp_path / "standards"
    official_root = standards_root / "official"
    user_root = standards_root / "user"
    write_published(
        official_root,
        standard_document(
            OFFICIAL_ID,
            name="官方燃气标准",
            description="官方标准说明",
            published=True,
        ),
    )
    return StandardStore(official_root=official_root, user_root=user_root)


def create_draft(
    store: StandardStore,
    document: dict[str, object],
    *,
    draft_id: str,
) -> None:
    draft = copy.deepcopy(document)
    draft["published_at"] = None
    store.create_draft(draft, draft_id=draft_id)


def asset_document(*paths: str) -> dict[str, object]:
    document = standard_document()
    document["assets"] = [
        {
            "asset_id": f"template-{index}",
            "kind": "base-template",
            "file": path,
        }
        for index, path in enumerate(paths)
    ]
    return document


def write_draft_asset(store: StandardStore, draft_id: str, relative: str, data: bytes) -> Path:
    target = store.drafts_root / draft_id / Path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def test_list_is_flat_and_summaries_include_description_and_published_at(
    store: StandardStore,
) -> None:
    create_draft(
        store,
        standard_document(FIRST_ID, description="草稿说明"),
        draft_id="draft-one",
    )

    entries = store.list()
    official = next(item for item in entries if item.standard_id == OFFICIAL_ID)
    draft = next(item for item in entries if item.draft_id == "draft-one")

    assert len([item for item in entries if item.status == "published"]) == 1
    assert official.description == "官方标准说明"
    assert official.published_at == PUBLISHED_AT
    assert draft.description == "草稿说明"
    assert draft.published_at is None
    assert not hasattr(official, "version")


def test_creation_draft_lookup_skips_corrupt_data_without_quarantining_it(
    tmp_path: Path,
) -> None:
    drafts = CreationDraftStore(tmp_path / "creation-drafts")
    matching = drafts.create(FIRST_ID, {})
    other = drafts.create(SECOND_ID, {})
    corrupt = drafts.root / "broken-draft"
    corrupt.mkdir(parents=True)
    corrupt_document = corrupt / "draft.json"
    corrupt_document.write_text("{broken", encoding="utf-8")

    assert drafts.list_by_standard(FIRST_ID) == (matching.id,)
    assert corrupt_document.read_text(encoding="utf-8") == "{broken"
    assert {path.name for path in drafts.root.iterdir()} == {
        matching.id,
        other.id,
        "broken-draft",
    }


def test_delete_transaction_targets_user_root_and_preserves_official_package(
    store: StandardStore, tmp_path: Path
) -> None:
    official_document = store.official_root / OFFICIAL_ID / "document.json"
    before = official_document.read_bytes()
    transaction = StandardDeleteTransaction(
        root=tmp_path / "tmp" / "standard-delete-transactions",
        published_root=store.published_root,
        creation_draft_root=tmp_path / "creation-drafts",
    )

    with pytest.raises(FileNotFoundError):
        transaction.delete(OFFICIAL_ID, ())

    assert official_document.read_bytes() == before


def test_get_and_create_normalize_uuid_case(store: StandardStore) -> None:
    upper_id = FIRST_ID.upper()
    create_draft(
        store,
        standard_document(upper_id),
        draft_id="draft-upper",
    )
    draft = store.get_draft("draft-upper")

    assert draft is not None
    assert draft.document["standard_id"] == FIRST_ID
    assert store.get(OFFICIAL_ID.upper()).standard_id == OFFICIAL_ID


def test_identity_gate_checks_ids_and_nonempty_names_in_all_libraries(
    store: StandardStore,
) -> None:
    with pytest.raises(StandardStoreError, match="STANDARD_ID_EXISTS"):
        store.check_available_identity(OFFICIAL_ID, "另一个名称")
    with pytest.raises(StandardStoreError, match="STANDARD_NAME_CONFLICT"):
        store.check_available_identity(SECOND_ID, "官方燃气标准")

    create_draft(
        store,
        standard_document(FIRST_ID, name="给排水标准 A"),
        draft_id="draft-a",
    )
    with pytest.raises(StandardStoreError, match="STANDARD_NAME_CONFLICT"):
        store.check_available_identity(SECOND_ID, "  给排水标准  A ")


@pytest.mark.parametrize(
    ("published_name", "conflicting_name"),
    [
        ("标准A", "标准Ａ"),
        ("标准 A", " 标准  A "),
        ("标准ABC", "标准abc"),
        ("ẞ标准", "ß标准"),
    ],
)
def test_publish_rejects_normalized_name_conflict(
    store: StandardStore,
    published_name: str,
    conflicting_name: str,
) -> None:
    create_draft(
        store,
        standard_document(FIRST_ID, name=published_name),
        draft_id="draft-a",
    )
    store.publish("draft-a", published_at=PUBLISHED_AT)
    conflicting_draft = store.drafts_root / "draft-b"
    conflicting_draft.mkdir(parents=True)
    (conflicting_draft / "document.json").write_text(
        json.dumps(
            standard_document(SECOND_ID, name=conflicting_name), ensure_ascii=False
        ),
        encoding="utf-8",
    )

    with pytest.raises(StandardStoreError, match="STANDARD_NAME_CONFLICT"):
        store.publish("draft-b", published_at=PUBLISHED_AT + 1)
    assert not (store.published_root / SECOND_ID).exists()


def test_empty_name_draft_is_allowed_and_does_not_reserve_identity(
    store: StandardStore,
) -> None:
    create_draft(
        store,
        standard_document(FIRST_ID, name=""),
        draft_id="draft-empty",
    )
    store.check_available_identity(SECOND_ID, "可用名称")
    with pytest.raises(StandardStoreError, match="STANDARD_ID_EXISTS"):
        store.check_available_identity(FIRST_ID, "另一个名称")


def test_publish_uses_timestamp_and_uuid_directory(
    store: StandardStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dst_manager.infrastructure.standards.store as store_module

    monkeypatch.setattr(store_module.time, "time_ns", lambda: PUBLISHED_AT * 1_000_000)
    create_draft(
        store,
        standard_document(FIRST_ID, description="发布后保留"),
        draft_id="draft-one",
    )

    published = store.publish("draft-one")

    assert published.root == store.published_root / FIRST_ID
    assert published.published_at == PUBLISHED_AT
    assert published.description == "发布后保留"
    assert not hasattr(published, "version")
    assert (published.root / "document.json").is_file()
    assert store.get(FIRST_ID).published_at == PUBLISHED_AT


def test_same_source_copies_publish_as_independent_standards(
    store: StandardStore,
) -> None:
    create_draft(
        store,
        standard_document(FIRST_ID, name="给排水 A"),
        draft_id="draft-a",
    )
    create_draft(
        store,
        standard_document(SECOND_ID, name="给排水 B"),
        draft_id="draft-b",
    )

    first = store.publish("draft-a", published_at=PUBLISHED_AT)
    second = store.publish("draft-b", published_at=PUBLISHED_AT + 1)

    assert first.standard_id != second.standard_id
    assert first.root != second.root
    assert store.get(FIRST_ID) is not None
    assert store.get(SECOND_ID) is not None


def test_concurrent_publication_keeps_distinct_uuids(store: StandardStore) -> None:
    create_draft(
        store,
        standard_document(FIRST_ID, name="并发标准 A"),
        draft_id="draft-a",
    )
    create_draft(
        store,
        standard_document(SECOND_ID, name="并发标准 B"),
        draft_id="draft-b",
    )
    barrier = threading.Barrier(2)
    results: list[str] = []
    errors: list[BaseException] = []

    def publish(draft_id: str, timestamp: int) -> None:
        try:
            barrier.wait(timeout=10)
            results.append(store.publish(draft_id, published_at=timestamp).standard_id)
        except BaseException as exc:  # noqa: BLE001 - 汇总线程异常后统一断言
            errors.append(exc)

    threads = [
        threading.Thread(target=publish, args=("draft-a", PUBLISHED_AT)),
        threading.Thread(target=publish, args=("draft-b", PUBLISHED_AT + 1)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert sorted(results) == sorted((FIRST_ID, SECOND_ID))


def test_publish_failure_restores_draft_and_assets(
    store: StandardStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = asset_document("assets/A2.dwg")
    create_draft(store, document, draft_id="draft-asset")
    write_draft_asset(store, "draft-asset", "assets/A2.dwg", b"a2")
    source_dir = store.drafts_root / "draft-asset"
    before = (source_dir / "document.json").read_bytes()
    real_replace = os.replace

    def fail_final_move(source, target):
        if Path(source) == source_dir:
            raise OSError(13, "injected publish failure")
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_final_move)
    with pytest.raises(StandardStoreError, match="STANDARD_PUBLISH_FAILED"):
        store.publish("draft-asset", published_at=PUBLISHED_AT)

    assert (source_dir / "document.json").read_bytes() == before
    assert (source_dir / "assets" / "A2.dwg").read_bytes() == b"a2"
    assert not (store.published_root / FIRST_ID).exists()


def test_publish_rejects_incomplete_document_without_moving_draft(
    store: StandardStore,
) -> None:
    create_draft(
        store,
        standard_document(mapping_target=""),
        draft_id="draft-incomplete",
    )

    with pytest.raises(StandardStoreError, match="STANDARD_MAPPING_TARGET_EMPTY"):
        store.publish("draft-incomplete", published_at=PUBLISHED_AT)
    assert (store.drafts_root / "draft-incomplete" / "document.json").is_file()


def test_library_lock_timeout_reports_stable_code(
    store: StandardStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dst_manager.infrastructure.standards.store as store_module
    from dst_manager.infrastructure.filesystem.locking import (
        WorkspaceTransactionBusyError,
    )

    class BusyLock:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            raise WorkspaceTransactionBusyError(32, "busy")

        def __exit__(self, *args) -> bool:
            return False

    create_draft(
        store,
        standard_document(FIRST_ID),
        draft_id="draft-one",
    )
    monkeypatch.setattr(store_module, "WorkspaceTransactionLock", BusyLock)
    with pytest.raises(StandardStoreError, match="STANDARD_LIBRARY_BUSY"):
        store.publish("draft-one", published_at=PUBLISHED_AT)


@pytest.mark.parametrize(
    "draft_id",
    ["../outside", "..\\outside", "C:\\outside", ".", "..", "a/b", "a\\b", "", "CON", "draft-1."],
)
def test_illegal_draft_id_cannot_escape_storage_root(
    store: StandardStore, draft_id: str
) -> None:
    with pytest.raises(StandardStoreError, match="STANDARD_DRAFT_ID_INVALID"):
        store.create_draft(standard_document(FIRST_ID), draft_id=draft_id)


@pytest.mark.parametrize(
    "asset_path",
    [
        "C:\\outside\\secret.dwg",
        "\\\\server\\share\\secret.dwg",
        "../outside.dwg",
        "assets/../../outside.dwg",
        "assets\\..\\outside.dwg",
    ],
)
def test_publish_rejects_illegal_asset_path(
    store: StandardStore, asset_path: str
) -> None:
    create_draft(store, asset_document(asset_path), draft_id="draft-asset")
    with pytest.raises(StandardStoreError, match="STANDARD_ASSET_PATH_INVALID"):
        store.publish("draft-asset", published_at=PUBLISHED_AT)


def test_publish_rejects_missing_asset_and_accepts_files(store: StandardStore) -> None:
    create_draft(
        store,
        asset_document("assets/missing.dwg"),
        draft_id="draft-missing",
    )
    with pytest.raises(StandardStoreError, match="STANDARD_ASSET_FILE_MISSING"):
        store.publish("draft-missing", published_at=PUBLISHED_AT)

    document = asset_document("assets/A2.dwg", "assets/模板/标题栏.dwg")
    document["standard_id"] = SECOND_ID
    document["name"] = "标题栏标准"
    create_draft(store, document, draft_id="draft-valid")
    write_draft_asset(store, "draft-valid", "assets/A2.dwg", b"a2")
    write_draft_asset(store, "draft-valid", "assets/模板/标题栏.dwg", b"title")
    published = store.publish("draft-valid", published_at=PUBLISHED_AT + 1)

    assert (published.root / "assets" / "A2.dwg").is_file()
    assert (published.root / "assets" / "模板" / "标题栏.dwg").is_file()


def test_publish_rejects_asset_symlink_outside_root(store: StandardStore) -> None:
    create_draft(
        store,
        asset_document("assets/linked.dwg"),
        draft_id="draft-asset",
    )
    outside = store.drafts_root.parent / "outside.dwg"
    outside.write_bytes(b"outside-dwg")
    link = store.drafts_root / "draft-asset" / "assets" / "linked.dwg"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")

    with pytest.raises(StandardStoreError, match="STANDARD_ASSET_PATH_INVALID"):
        store.publish("draft-asset", published_at=PUBLISHED_AT)
    assert outside.read_bytes() == b"outside-dwg"


def test_save_prunes_only_unreferenced_managed_asset_copies(
    store: StandardStore,
) -> None:
    document = asset_document("assets/managed-keep.dwg")
    create_draft(store, document, draft_id="draft-asset")
    write_draft_asset(store, "draft-asset", "assets/managed-keep.dwg", b"keep")
    write_draft_asset(store, "draft-asset", "assets/managed-orphan.dwg", b"orphan")
    write_draft_asset(store, "draft-asset", "assets/A2.dwg", b"hand-placed")

    store.save_draft("draft-asset", document)

    assets = store.drafts_root / "draft-asset" / "assets"
    assert (assets / "managed-keep.dwg").is_file()
    assert not (assets / "managed-orphan.dwg").exists()
    assert (assets / "A2.dwg").read_bytes() == b"hand-placed"


def test_corrupt_published_document_is_reported_on_get(store: StandardStore) -> None:
    path = write_published(
        store.official_root,
        standard_document(THIRD_ID, name="损坏样例", published=True),
    )
    (path / "document.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(StandardStoreError, match="STANDARD_JSON_INVALID"):
        store.get(THIRD_ID)


def test_unsupported_published_schema_is_skipped_in_list_and_rejected_by_get(
    store: StandardStore,
) -> None:
    document = standard_document(THIRD_ID, name="旧格式")
    document["schema_version"] = 2
    path = store.official_root / THIRD_ID
    path.mkdir(parents=True)
    (path / "document.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )

    assert THIRD_ID not in {item.standard_id for item in store.list()}
    with pytest.raises(StandardStoreError, match="STANDARD_SCHEMA_VERSION_UNSUPPORTED"):
        store.get(THIRD_ID)


def test_outside_files_remain_untouched_when_draft_id_is_invalid(
    store: StandardStore,
) -> None:
    outside = store.drafts_root.parent / "outside"
    outside.mkdir(parents=True)
    secret = outside / "document.json"
    secret.write_text('{"private": true}', encoding="utf-8")
    before = hashlib.sha256(secret.read_bytes()).hexdigest()

    with pytest.raises(StandardStoreError, match="STANDARD_DRAFT_ID_INVALID"):
        store.create_draft(standard_document(FIRST_ID), draft_id="../outside")

    assert hashlib.sha256(secret.read_bytes()).hexdigest() == before
    assert sorted(path.name for path in store.drafts_root.parent.iterdir()) == [
        "outside"
    ]
