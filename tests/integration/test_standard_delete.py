"""标准删除影响预览与关联创建草稿事务回归。"""

from __future__ import annotations

import concurrent.futures
import copy
import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from creation_xlsx_fixtures import STANDARD_DOCUMENT
from fastapi.testclient import TestClient

from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.interfaces.api import create_app

FIRST_ID = "00000000-0000-4000-8000-000000000046"
SECOND_ID = "00000000-0000-4000-8000-000000000047"
OFFICIAL_ID = "00000000-0000-4000-8000-000000000048"


def _document(standard_id: str, *, published: bool = False) -> dict[str, object]:
    document = copy.deepcopy(STANDARD_DOCUMENT)
    document.update(
        standard_id=standard_id,
        published_at=1_800_000_000_123 if published else None,
        assets=[],
    )
    return document


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path / "data")))


def _service(client: TestClient) -> DstManagerService:
    return client.app.state.service


def _publish(client: TestClient, standard_id: str) -> None:
    document = _document(standard_id)
    document["name"] = f"测试标准 {standard_id[-4:]}"
    service = _service(client)
    draft = service.create_standard_draft(document, f"std-{standard_id[-4:]}")
    service.publish_standard(str(draft["draft_id"]))


def _creation_draft(client: TestClient, standard_id: str) -> str:
    return _service(client).create_creation_draft(standard_id).id


def test_preview_and_delete_remove_only_target_package_and_drafts(
    client: TestClient, tmp_path: Path
) -> None:
    _publish(client, FIRST_ID)
    _publish(client, SECOND_ID)
    service = _service(client)
    first_drafts = {_creation_draft(client, FIRST_ID) for _ in range(2)}
    other_draft = _creation_draft(client, SECOND_ID)
    snapshot = tmp_path / "project" / ".dst-manager" / "standards" / FIRST_ID / "snapshot.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("project snapshot", encoding="utf-8")

    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact")
    assert impact.status_code == 200
    preview = impact.json()
    assert preview["standard_id"] == FIRST_ID
    assert preview["affected_count"] == 2
    assert isinstance(preview["impact_token"], str)

    deleted = client.post(
        f"/api/standards/{FIRST_ID}/delete",
        json={"impact_token": preview["impact_token"]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_count"] == 2
    assert service.standard_store.get(FIRST_ID) is None
    assert service.standard_store.get(SECOND_ID) is not None
    assert service.creation_drafts.list_by_standard(FIRST_ID) == ()
    assert service.creation_drafts.load(other_draft).standard_id == SECOND_ID
    assert all(not (service.creation_drafts.root / item).exists() for item in first_drafts)
    assert snapshot.read_text(encoding="utf-8") == "project snapshot"


def test_zero_draft_preview_can_be_cancelled_without_changes(client: TestClient) -> None:
    _publish(client, FIRST_ID)
    service = _service(client)
    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact").json()
    assert impact["affected_count"] == 0
    assert service.standard_store.get(FIRST_ID) is not None
    assert client.get(f"/api/standards/{FIRST_ID}/delete-impact").status_code == 200
    assert service.standard_store.get(FIRST_ID) is not None


def test_zero_draft_delete_removes_package_and_returns_zero(client: TestClient) -> None:
    _publish(client, FIRST_ID)
    service = _service(client)
    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact").json()

    deleted = client.post(
        f"/api/standards/{FIRST_ID}/delete",
        json={"impact_token": impact["impact_token"]},
    )

    assert deleted.status_code == 200
    assert deleted.json()["deleted_count"] == 0
    assert service.standard_store.get(FIRST_ID) is None


def test_missing_standard_preview_and_repeated_confirmation_are_stable(
    client: TestClient,
) -> None:
    missing = client.get(f"/api/standards/{FIRST_ID}/delete-impact")
    assert missing.status_code == 404
    assert missing.json()["code"] == "STANDARD_ID_NOT_FOUND"

    _publish(client, FIRST_ID)
    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact").json()
    body = {"impact_token": impact["impact_token"]}
    first = client.post(f"/api/standards/{FIRST_ID}/delete", json=body)
    repeated = client.post(f"/api/standards/{FIRST_ID}/delete", json=body)

    assert first.status_code == 200
    assert repeated.status_code == 404
    assert repeated.json()["code"] == "STANDARD_ID_NOT_FOUND"


def test_official_standard_delete_routes_are_rejected_without_clearing_drafts(
    client: TestClient,
) -> None:
    service = _service(client)
    official = service.standard_store.official_root / OFFICIAL_ID
    official.mkdir(parents=True)
    (official / "document.json").write_text(
        json.dumps(_document(OFFICIAL_ID, published=True)), encoding="utf-8"
    )
    draft_id = _creation_draft(client, OFFICIAL_ID)

    impact = client.get(f"/api/standards/{OFFICIAL_ID}/delete-impact")
    assert impact.status_code == 403
    assert impact.json()["code"] == "STANDARD_DELETE_FORBIDDEN"
    deleted = client.post(
        f"/api/standards/{OFFICIAL_ID}/delete", json={"impact_token": "anything"}
    )
    assert deleted.status_code == 403
    assert deleted.json()["code"] == "STANDARD_DELETE_FORBIDDEN"
    assert (official / "document.json").is_file()
    assert service.creation_drafts.load(draft_id).standard_id == OFFICIAL_ID


def test_new_associated_draft_invalidates_preview_token(client: TestClient) -> None:
    _publish(client, FIRST_ID)
    service = _service(client)
    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact").json()
    _creation_draft(client, FIRST_ID)

    deleted = client.post(
        f"/api/standards/{FIRST_ID}/delete",
        json={"impact_token": impact["impact_token"]},
    )
    assert deleted.status_code == 409
    assert deleted.json()["code"] == "STANDARD_DELETE_IMPACT_CHANGED"
    assert service.standard_store.get(FIRST_ID) is not None
    assert service.creation_drafts.list_by_standard(FIRST_ID)


def test_active_creation_job_blocks_standard_delete(client: TestClient) -> None:
    _publish(client, FIRST_ID)
    service = _service(client)
    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact").json()
    service.database.create_job(
        "active-standard-delete-test",
        None,
        "creation",
        "QUEUED",
        {"standard": {"standard_id": FIRST_ID}},
    )

    deleted = client.post(
        f"/api/standards/{FIRST_ID}/delete",
        json={"impact_token": impact["impact_token"]},
    )
    assert deleted.status_code == 409
    assert deleted.json()["code"] == "STANDARD_DELETE_JOB_ACTIVE"
    assert service.standard_store.get(FIRST_ID) is not None


def test_delete_waits_for_in_flight_creation_draft_save(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(client, FIRST_ID)
    service = _service(client)
    draft = service.create_creation_draft(FIRST_ID)
    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact").json()
    entered_save = threading.Event()
    allow_save = threading.Event()
    entered_delete = threading.Event()
    original_save = service.creation_drafts.save
    original_delete = service.delete_standard

    def blocking_save(*args, **kwargs):
        entered_save.set()
        if not allow_save.wait(timeout=5):
            raise TimeoutError("test did not release the save")
        return original_save(*args, **kwargs)

    def tracked_delete(standard_id: str, impact_token: str):
        entered_delete.set()
        return original_delete(standard_id, impact_token)

    monkeypatch.setattr(service.creation_drafts, "save", blocking_save)
    monkeypatch.setattr(service, "delete_standard", tracked_delete)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        save = executor.submit(
            service.save_creation_draft,
            draft.id,
            expected_revision=draft.revision,
            value=replace(draft, step=draft.step),
        )
        assert entered_save.wait(timeout=5)
        delete = executor.submit(
            service.delete_standard, FIRST_ID, impact["impact_token"]
        )
        assert entered_delete.wait(timeout=5)
        assert not delete.done()
        allow_save.set()
        save.result(timeout=5)
        result = delete.result(timeout=5)

    assert result["deleted_count"] == 1
    assert service.standard_store.get(FIRST_ID) is None
    assert service.creation_drafts.list_by_standard(FIRST_ID) == ()


@pytest.mark.parametrize("failed_move", [1, 2, 3])
def test_each_directory_move_failure_rolls_back_whole_delete(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, failed_move: int
) -> None:
    _publish(client, FIRST_ID)
    service = _service(client)
    draft_ids = {_creation_draft(client, FIRST_ID) for _ in range(2)}
    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact").json()
    transaction = service.standard_delete_transaction
    original_move = transaction._move
    calls = 0

    def failing_move(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == failed_move:
            raise OSError("injected directory move failure")
        original_move(source, destination)

    monkeypatch.setattr(transaction, "_move", failing_move)
    deleted = client.post(
        f"/api/standards/{FIRST_ID}/delete",
        json={"impact_token": impact["impact_token"]},
    )
    assert deleted.status_code == 500
    assert service.standard_store.get(FIRST_ID) is not None
    assert service.creation_drafts.list_by_standard(FIRST_ID) == tuple(sorted(draft_ids))


def test_restart_recovers_uncommitted_delete_after_directory_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    client = TestClient(create_app(settings))
    _publish(client, FIRST_ID)
    draft_id = _creation_draft(client, FIRST_ID)
    transaction = service.standard_delete_transaction
    original_move = transaction._move

    def crash_after_move(source: Path, destination: Path) -> None:
        original_move(source, destination)
        raise KeyboardInterrupt("simulated process interruption")

    monkeypatch.setattr(transaction, "_move", crash_after_move)
    with pytest.raises(KeyboardInterrupt):
        transaction.delete(FIRST_ID, (draft_id,))

    recovered = DstManagerService(settings)
    assert recovered.standard_store.get(FIRST_ID) is not None
    assert recovered.creation_drafts.load(draft_id).standard_id == FIRST_ID


def test_restart_finishes_cleanup_after_committed_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    client = TestClient(create_app(settings))
    _publish(client, FIRST_ID)
    draft_id = _creation_draft(client, FIRST_ID)
    impact = client.get(f"/api/standards/{FIRST_ID}/delete-impact").json()
    transaction = service.standard_delete_transaction

    def crash_during_cleanup(transaction_dir: Path) -> None:
        raise KeyboardInterrupt("simulated process interruption")

    monkeypatch.setattr(transaction, "_cleanup", crash_during_cleanup)
    with pytest.raises(KeyboardInterrupt):
        transaction.delete(FIRST_ID, (draft_id,))

    recovered = DstManagerService(settings)
    assert recovered.standard_store.get(FIRST_ID) is None
    assert recovered.creation_drafts.list_by_standard(FIRST_ID) == ()
    assert impact["affected_count"] == 1
