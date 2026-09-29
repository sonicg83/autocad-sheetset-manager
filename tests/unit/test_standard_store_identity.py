"""无版本标准库 UUID 存储契约测试（PLAN-DM-046 Task 2）。"""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

import pytest
from creation_xlsx_fixtures import STANDARD_DOCUMENT

from dst_manager.domain.standards import parse_published_standard_document
from dst_manager.infrastructure.standards.store import (
    StandardStore,
    StandardStoreError,
)

FIRST_ID = "123e4567-e89b-42d3-a456-426614174000"
SECOND_ID = "123e4567-e89b-42d3-a456-426614174001"
THIRD_ID = "123e4567-e89b-42d3-a456-426614174002"
FOURTH_ID = "123e4567-e89b-42d3-a456-426614174003"
PUBLISHED_AT = 1_800_000_000_123


def standard_document(
    standard_id: str = FIRST_ID,
    *,
    name: str = "用户给排水标准",
    description: str = "标准说明",
) -> dict[str, object]:
    document = copy.deepcopy(STANDARD_DOCUMENT)
    document.update(
        standard_id=standard_id,
        published_at=None,
        name=name,
        description=description,
        assets=[],
    )
    return document


def write_published(root: Path, document: dict[str, object]) -> Path:
    standard = parse_published_standard_document(document)
    target = root / standard.standard_id
    target.mkdir(parents=True)
    (target / "document.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )
    return target


@pytest.fixture
def store(tmp_path: Path) -> StandardStore:
    official_root = tmp_path / "standards" / "official"
    user_root = tmp_path / "standards" / "user"
    official_root.mkdir(parents=True)
    write_published(
        official_root,
        {
            **standard_document(THIRD_ID, name="官方标准", description="官方说明"),
            "published_at": PUBLISHED_AT,
        },
    )
    return StandardStore(official_root=official_root, user_root=user_root)


def create_draft(
    store: StandardStore,
    standard_id: str,
    *,
    name: str,
    description: str,
    draft_id: str,
) -> None:
    store.create_draft(
        standard_document(standard_id, name=name, description=description),
        draft_id=draft_id,
    )


def test_publish_uses_uuid_directory_timestamp_and_flat_summary(
    store: StandardStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dst_manager.infrastructure.standards.package_io as package_module

    monkeypatch.setattr(package_module.time, "time_ns", lambda: PUBLISHED_AT * 1_000_000)
    create_draft(
        store,
        FIRST_ID,
        name="用户给排水标准",
        description="保留到发布后的说明",
        draft_id="draft-first",
    )

    published = store.publish("draft-first")

    assert published.standard_id == FIRST_ID
    assert published.root == store.published_root / FIRST_ID
    assert not hasattr(published, "version")
    assert (published.root / "document.json").is_file()
    assert not (published.root.parent / "1").exists()
    summary = next(item for item in store.list() if item.standard_id == FIRST_ID)
    assert summary.description == "保留到发布后的说明"
    assert summary.published_at == PUBLISHED_AT
    assert not hasattr(summary, "version")
    assert store.get(FIRST_ID).published_at == PUBLISHED_AT


def test_copying_same_source_produces_independent_standard_ids(store: StandardStore) -> None:
    create_draft(
        store,
        FIRST_ID,
        name="给排水 A",
        description="",
        draft_id="draft-a",
    )
    create_draft(
        store,
        SECOND_ID,
        name="给排水 B",
        description="",
        draft_id="draft-b",
    )

    first = store.publish("draft-a", published_at=PUBLISHED_AT)
    second = store.publish("draft-b", published_at=PUBLISHED_AT + 1)

    assert first.standard_id != second.standard_id
    assert first.root != second.root
    assert store.get(FIRST_ID) is not None
    assert store.get(SECOND_ID) is not None


@pytest.mark.parametrize(
    ("standard_id", "name", "code"),
    [
        (THIRD_ID, "另一个名称", "STANDARD_ID_EXISTS"),
        (SECOND_ID, "官方标准", "STANDARD_NAME_CONFLICT"),
    ],
)
def test_identity_gate_includes_official_library(
    store: StandardStore,
    standard_id: str,
    name: str,
    code: str,
) -> None:
    with pytest.raises(StandardStoreError, match=code):
        store.check_available_identity(standard_id, name)


def test_identity_gate_includes_nonempty_drafts_but_allows_empty_names(
    store: StandardStore,
) -> None:
    create_draft(
        store,
        FIRST_ID,
        name="给排水标准 A",
        description="",
        draft_id="draft-a",
    )
    with pytest.raises(StandardStoreError, match="STANDARD_NAME_CONFLICT"):
        store.check_available_identity(SECOND_ID, "  给排水标准  A ")


def test_empty_name_draft_does_not_reserve_a_name(store: StandardStore) -> None:
    store.create_draft(
        standard_document(SECOND_ID, name="", description=""), draft_id="draft-empty"
    )

    store.check_available_identity(FOURTH_ID, "可用名称")


def test_concurrent_publications_keep_distinct_ids_and_flat_packages(
    store: StandardStore,
) -> None:
    create_draft(
        store,
        FIRST_ID,
        name="并发标准 A",
        description="",
        draft_id="draft-a",
    )
    create_draft(
        store,
        SECOND_ID,
        name="并发标准 B",
        description="",
        draft_id="draft-b",
    )
    barrier = threading.Barrier(2)
    results: list[str] = []
    errors: list[BaseException] = []

    def publish(draft_id: str, published_at: int) -> None:
        try:
            barrier.wait(timeout=10)
            results.append(
                store.publish(draft_id, published_at=published_at).standard_id
            )
        except BaseException as exc:  # noqa: BLE001 - 线程结束后统一断言
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
    assert all((store.published_root / standard_id / "document.json").is_file() for standard_id in results)
