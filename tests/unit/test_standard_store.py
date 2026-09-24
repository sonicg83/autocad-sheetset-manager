"""官方/用户标准库仓储测试（PLAN-DM-035 Task 3 / PLAN-DM-038 Task 4）。"""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from dst_manager.domain.standards import StandardSchemaError
from dst_manager.infrastructure.standards.package import StandardPackageReader
from dst_manager.infrastructure.standards.store import (
    StandardStore,
    StandardStoreError,
)


def standard_document(
    *,
    standard_id: str = "user.water",
    version: str = "3.0.0",
    name: str = "用户给排水标准",
    mapping_target: str = "GS",
) -> dict[str, object]:
    """Schema v1 最小文档：枚举源 + 映射 + 默认 DWG 命名。"""
    return {
        "schema_version": 1,
        "standard_id": standard_id,
        "version": version,
        "name": name,
        "supported_cad_versions": ["2020"],
        "properties": [
            {
                "property_id": "prop-major",
                "name": "专业",
                "scope": "sheetset",
                "kind": "enum",
                "enum_items": [{"item_id": "enum-water", "value": "给水"}],
            },
            {
                "property_id": "prop-code",
                "name": "专业代码",
                "scope": "sheetset",
                "kind": "mapping",
                "source_property_id": "prop-major",
                "mapping": [{"item_id": "enum-water", "value": mapping_target}],
                "confirmed_source_items": [["enum-water", "给水"]],
            },
        ],
        "dwg_naming": {
            "segments": [
                {"system_field": "subset.scope"},
                {"literal": " "},
                {"system_field": "subset.name"},
            ]
        },
        "assets": [],
        "numbering": {"sequence_field": "subset.sequence", "digits": 2},
    }


OFFICIAL_DOCUMENT = standard_document(
    standard_id="official.gas", version="1.0.0", name="官方燃气标准"
)
USER_DOCUMENT = standard_document()

LEGACY_DOCUMENT = {
    "schema_version": 1,
    "standard_id": "legacy.rules",
    "version": "1.0.0",
    "name": "旧通用规则标准",
    "supported_cad_versions": ["2020"],
    "properties": [{"name": "专业名称", "scope": "sheetset", "required": True}],
    "rules": [{"rule_id": "r1", "kind": "required", "target": "sheetset.专业名称"}],
    "assets": [],
    "numbering": {"sequence_field": "subset.sequence", "digits": 2},
}


def write_official(root: Path, document: dict) -> None:
    target = root / document["standard_id"] / document["version"]
    target.mkdir(parents=True)
    (target / "document.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )


@pytest.fixture
def store(tmp_path: Path) -> StandardStore:
    official_root = tmp_path / "official"
    official_root.mkdir()
    write_official(official_root, OFFICIAL_DOCUMENT)
    return StandardStore(official_root=official_root, user_root=tmp_path / "user")


def create_draft(store: StandardStore, document: dict, draft_id: str | None = None):
    return store.create_draft(document, draft_id=draft_id)


def test_publish_rejects_existing_identity(store: StandardStore) -> None:
    create_draft(store, USER_DOCUMENT, draft_id="draft-1")
    create_draft(store, USER_DOCUMENT, draft_id="draft-2")
    store.publish("draft-1")
    with pytest.raises(StandardStoreError, match="STANDARD_VERSION_EXISTS"):
        store.publish("draft-2")


def test_publish_rejects_official_identity_collision(store: StandardStore) -> None:
    create_draft(store, OFFICIAL_DOCUMENT, draft_id="draft-1")
    with pytest.raises(StandardStoreError, match="STANDARD_VERSION_EXISTS"):
        store.publish("draft-1")


def test_publish_writes_immutable_version_directory(store: StandardStore) -> None:
    create_draft(store, USER_DOCUMENT, draft_id="draft-1")
    published = store.publish("draft-1")
    assert (published.root / "document.json").is_file()
    assert published.standard_id == "user.water"
    assert published.version == "3.0.0"


def test_store_round_trips_after_reopen(store: StandardStore, tmp_path: Path) -> None:
    create_draft(store, USER_DOCUMENT, draft_id="draft-1")
    store.publish("draft-1")
    reopened = StandardStore(
        official_root=tmp_path / "official", user_root=tmp_path / "user"
    )
    standard = reopened.get("user.water", "3.0.0")
    assert standard is not None
    assert standard.name == "用户给排水标准"


def test_list_covers_official_and_user(store: StandardStore) -> None:
    create_draft(store, USER_DOCUMENT, draft_id="draft-1")
    store.publish("draft-1")
    entries = {(entry.source, entry.status, entry.standard_id, entry.version) for entry in store.list()}
    assert ("official", "published", "official.gas", "1.0.0") in entries
    assert ("user", "published", "user.water", "3.0.0") in entries


def test_get_missing_identity_returns_none(store: StandardStore) -> None:
    assert store.get("missing.standard", "9.9.9") is None


def test_legacy_document_rejected_by_draft_gate(store: StandardStore) -> None:
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_ID_INVALID"):
        create_draft(store, LEGACY_DOCUMENT, draft_id="draft-legacy")


def test_legacy_draft_document_is_rejected_not_guessed(store: StandardStore) -> None:
    legacy_dir = store.drafts_root / "draft-legacy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "document.json").write_text(
        json.dumps(LEGACY_DOCUMENT, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(StandardStoreError, match="STANDARD_PROPERTY_ID_INVALID"):
        store.publish("draft-legacy")
    assert (legacy_dir / "document.json").is_file()


def test_draft_saves_semantically_incomplete_mapping(store: StandardStore) -> None:
    draft = create_draft(store, standard_document(mapping_target=""), draft_id="draft-1")
    assert draft.document["standard_id"] == "user.water"
    assert store.get_draft("draft-1") is not None


def test_publish_rejects_incomplete_draft_without_moving_directory(
    store: StandardStore,
) -> None:
    create_draft(store, standard_document(mapping_target=""), draft_id="draft-1")
    with pytest.raises(StandardStoreError, match="STANDARD_MAPPING_TARGET_EMPTY"):
        store.publish("draft-1")
    assert (store.drafts_root / "draft-1" / "document.json").is_file()
    assert store.get("user.water", "3.0.0") is None


def test_import_package_collides_with_existing(store: StandardStore, tmp_path: Path) -> None:
    create_draft(store, USER_DOCUMENT, draft_id="draft-1")
    store.publish("draft-1")
    package = tmp_path / "user-water.dststandard"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(USER_DOCUMENT, ensure_ascii=False))
    with pytest.raises(StandardStoreError, match="STANDARD_VERSION_EXISTS"):
        store.import_package(package)


def test_import_package_rejects_incomplete_document(
    store: StandardStore, tmp_path: Path
) -> None:
    package = tmp_path / "incomplete.dststandard"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(standard_document(mapping_target=""), ensure_ascii=False),
        )
    with pytest.raises(StandardStoreError, match="STANDARD_MAPPING_TARGET_EMPTY"):
        store.import_package(package)
    assert store.get("user.water", "3.0.0") is None


def test_import_export_round_trip(store: StandardStore, tmp_path: Path) -> None:
    create_draft(store, USER_DOCUMENT, draft_id="draft-1")
    store.publish("draft-1")
    exported = store.export_package("user.water", "3.0.0", tmp_path / "out")
    assert exported.suffix == ".dststandard"
    loaded = StandardPackageReader().read(exported)
    assert loaded.standard.standard_id == "user.water"
    assert loaded.standard.name == "用户给排水标准"
    # 已发布版本不可变，同库重复导入必须拒绝；导入到全新用户库验证往返。
    fresh = StandardStore(official_root=tmp_path / "official-2", user_root=tmp_path / "user-2")
    fresh.import_package(exported)
    assert fresh.get("user.water", "3.0.0") is not None


def test_round_trip_preserves_stable_ids_and_tokens(store: StandardStore, tmp_path: Path) -> None:
    document = standard_document()
    create_draft(store, document, draft_id="draft-1")
    store.publish("draft-1")
    exported = store.export_package("user.water", "3.0.0", tmp_path / "out")
    fresh = StandardStore(official_root=tmp_path / "official-2", user_root=tmp_path / "user-2")
    fresh.import_package(exported)
    restored = fresh.get_document("user.water", "3.0.0")
    assert restored == document


def test_draft_save_and_get(store: StandardStore) -> None:
    draft = create_draft(store, USER_DOCUMENT, draft_id="draft-1")
    assert draft.draft_id == "draft-1"
    loaded = store.get_draft("draft-1")
    assert loaded is not None
    assert loaded.document["standard_id"] == "user.water"


def test_publish_missing_draft_fails(store: StandardStore) -> None:
    with pytest.raises(StandardStoreError, match="STANDARD_DRAFT_NOT_FOUND"):
        store.publish("nope")


def test_get_rejects_legacy_rules_document(store: StandardStore, tmp_path: Path) -> None:
    official_root = tmp_path / "official"
    write_official(official_root, LEGACY_DOCUMENT)
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_ID_INVALID"):
        store.get("legacy.rules", "1.0.0")


# ---- 草稿段边界（PLAN-DM-040 Task 1，F04） -------------------------------

ILLEGAL_DRAFT_IDS = (
    "../outside",
    "..\\outside",
    "C:\\outside",
    ".",
    "..",
    "a/b",
    "a\\b",
    "",
    "CON",
    "LPT1",
    "CON.dwg",
    "draft-1.",
    "draft-1 ",
)

DRAFT_OPERATIONS = ("create_draft", "get_draft", "save_draft", "delete_draft", "publish")


def _call_draft_operation(store: StandardStore, operation: str, draft_id: str) -> None:
    if operation == "create_draft":
        store.create_draft(USER_DOCUMENT, draft_id=draft_id)
    elif operation == "get_draft":
        store.get_draft(draft_id)
    elif operation == "save_draft":
        store.save_draft(draft_id, USER_DOCUMENT)
    elif operation == "delete_draft":
        store.delete_draft(draft_id)
    else:
        store.publish(draft_id)


@pytest.mark.parametrize("draft_id", ILLEGAL_DRAFT_IDS)
@pytest.mark.parametrize("operation", DRAFT_OPERATIONS)
def test_illegal_draft_id_rejected_by_every_entry(
    store: StandardStore, draft_id: str, operation: str
) -> None:
    with pytest.raises(StandardStoreError, match="STANDARD_DRAFT_ID_INVALID"):
        _call_draft_operation(store, operation, draft_id)


def test_illegal_draft_id_leaves_files_outside_root_untouched(
    store: StandardStore,
) -> None:
    outside = store.drafts_root.parent / "outside"
    outside.mkdir(parents=True)
    secret = outside / "document.json"
    secret.write_text("{\"secret\": true}", encoding="utf-8")
    before_hash = hashlib.sha256(secret.read_bytes()).hexdigest()
    before_listing = sorted(path.name for path in store.drafts_root.parent.iterdir())

    for draft_id in ILLEGAL_DRAFT_IDS:
        for operation in DRAFT_OPERATIONS:
            with pytest.raises(StandardStoreError, match="STANDARD_DRAFT_ID_INVALID"):
                _call_draft_operation(store, operation, draft_id)

    assert hashlib.sha256(secret.read_bytes()).hexdigest() == before_hash
    assert sorted(path.name for path in store.drafts_root.parent.iterdir()) == before_listing


@pytest.mark.parametrize("draft_id", ["draft-1", "legacy", "draft-gas"])
def test_legal_draft_ids_still_round_trip(store: StandardStore, draft_id: str) -> None:
    create_draft(store, USER_DOCUMENT, draft_id=draft_id)
    assert store.get_draft(draft_id) is not None
    assert store.save_draft(draft_id, USER_DOCUMENT).draft_id == draft_id
    published = store.publish(draft_id)
    assert (published.standard_id, published.version) == ("user.water", "3.0.0")
    assert not (store.drafts_root / draft_id).exists()


def test_list_skips_illegal_historical_draft_directories(store: StandardStore) -> None:
    create_draft(store, USER_DOCUMENT, draft_id="draft-ok")
    for name in ("d" * 200, " draft-legacy"):
        legacy = store.drafts_root / name
        legacy.mkdir(parents=True)
        (legacy / "document.json").write_text(
            json.dumps(USER_DOCUMENT, ensure_ascii=False), encoding="utf-8"
        )

    draft_ids = [entry.draft_id for entry in store.list() if entry.status == "draft"]
    assert draft_ids == ["draft-ok"]
    # 非法历史目录只被跳过，不被删除
    assert (store.drafts_root / ("d" * 200) / "document.json").is_file()
    assert (store.drafts_root / " draft-legacy" / "document.json").is_file()
