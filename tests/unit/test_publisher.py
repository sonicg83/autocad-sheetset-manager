import json
import os
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem.locking import WindowsWriteLocks
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    PublishRolledBackError,
    RecoverablePublisher,
    file_sha256,
)


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_publish_failure_rolls_back_every_replaced_file(tmp_path: Path, fail_at: int):
    targets = {}
    for index in range(3):
        target = tmp_path / f"target-{index}.txt"
        source = tmp_path / f"staged-{index}.txt"
        target.write_text(f"before-{index}")
        source.write_text(f"after-{index}")
        targets[target] = source
    calls = 0

    def replace(source: Path, target: Path):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise OSError("注入发布故障")
        os.replace(source, target)

    with pytest.raises(PublishRolledBackError, match="注入发布故障"):
        RecoverablePublisher(replace).publish("fault", tmp_path, targets)
    assert [path.read_text() for path in targets] == ["before-0", "before-1", "before-2"]
    journal = json.loads((tmp_path / ".dst-manager/jobs/fault/publish-journal.json").read_text(encoding="utf-8"))
    assert journal["status"] == "ROLLED_BACK"
    assert all((tmp_path / ".dst-manager/revisions/fault/before" / path.name).is_file() for path in targets)


def test_deleted_file_is_restored_when_later_publish_fails(tmp_path: Path):
    deleted, replaced, staged = tmp_path / "delete.txt", tmp_path / "replace.txt", tmp_path / "staged.txt"
    deleted.write_text("keep-delete"); replaced.write_text("keep-replace"); staged.write_text("new")
    def fail(*_): raise OSError("fail")
    # 删除项先执行，第二项替换失败。
    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(fail).publish("delete-fault", tmp_path, {deleted: None, replaced: staged})
    assert deleted.read_text() == "keep-delete" and replaced.read_text() == "keep-replace"


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_mixed_create_replace_delete_publish_failure_restores_batch(
    tmp_path: Path,
    monkeypatch,
    fail_at: int,
):
    created = tmp_path / "created.dwg"
    replaced = tmp_path / "replaced.dwg"
    deleted = tmp_path / "deleted.dwg"
    staged_created = tmp_path / "staged-created.dwg"
    staged_replaced = tmp_path / "staged-replaced.dwg"
    replaced.write_bytes(b"old-replaced")
    deleted.write_bytes(b"old-deleted")
    staged_created.write_bytes(b"new-created")
    staged_replaced.write_bytes(b"new-replaced")
    replace_calls = 0

    def replace(source: Path, target: Path):
        nonlocal replace_calls
        replace_calls += 1
        if fail_at in {1, 2} and replace_calls == fail_at:
            raise OSError(f"注入第 {fail_at} 项发布故障")
        os.replace(source, target)

    publisher = RecoverablePublisher(replace)
    original_move = publisher._move_no_replace

    def move(source: Path, target: Path):
        if fail_at == 3 and source == deleted:
            raise OSError("注入第 3 项发布故障")
        original_move(source, target)

    monkeypatch.setattr(publisher, "_move_no_replace", move)

    with pytest.raises(PublishRolledBackError, match=f"注入第 {fail_at} 项发布故障"):
        publisher.publish(
            f"mixed-{fail_at}",
            tmp_path,
            {created: staged_created, replaced: staged_replaced, deleted: None},
        )

    assert not created.exists()
    assert replaced.read_bytes() == b"old-replaced"
    assert deleted.read_bytes() == b"old-deleted"
    journal = json.loads(
        (tmp_path / ".dst-manager" / "jobs" / f"mixed-{fail_at}" / "publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "ROLLED_BACK"


@pytest.mark.parametrize("status", ["PREPARED", "PUBLISHING", "ROLLING_BACK"])
def test_startup_recovery_closes_unfinished_journal(tmp_path: Path, status: str):
    operation="crash"; target=tmp_path/"target.txt"; target.write_text("after")
    backup=tmp_path/".dst-manager"/"revisions"/operation/"before"/target.name; backup.parent.mkdir(parents=True); backup.write_text("before")
    journal_path=tmp_path/".dst-manager"/"jobs"/operation/"publish-journal.json"; journal_path.parent.mkdir(parents=True)
    journal={"operation_id":operation,"status":status,"files":[{"target":str(target),"backup":str(backup),"staged":None,"replaced":status!="PREPARED"}]}; journal_path.write_text(json.dumps(journal),encoding="utf-8")
    assert RecoverablePublisher().recover(tmp_path)==[operation]
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"]=="ROLLED_BACK"
    assert target.read_text()==("after" if status=="PREPARED" else "before")


def test_startup_recovery_restores_target_moved_by_attempted_replace(tmp_path: Path):
    operation = "attempted-crash"
    target = tmp_path / "attempted-target.dwg"
    staged = tmp_path / "attempted-staged.dwg"
    staged.write_bytes(b"published")
    before = tmp_path / ".dst-manager/revisions" / operation / "before" / target.name
    before.parent.mkdir(parents=True)
    before.write_bytes(b"baseline")
    replace_backup = tmp_path / f".{target.name}.{operation}.replaced"
    replace_backup.write_bytes(b"baseline")
    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal = {
        "operation_id": operation,
        "status": "PUBLISHING",
        "files": [
            {
                "target": str(target),
                "staged": str(staged),
                "backup": str(before),
                "replace_backup": str(replace_backup),
                "before_hash": file_sha256(before),
                "staged_hash": file_sha256(staged),
                "attempted": True,
                "replaced": False,
                "conflict_preserved": False,
            },
        ],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    assert RecoverablePublisher().recover(tmp_path) == [operation]

    assert target.read_bytes() == b"baseline"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"


def test_windows_lock_blocks_writers_but_allows_readers(tmp_path: Path):
    target=tmp_path/"locked.txt"; target.write_text("data")
    with WindowsWriteLocks([target]):
        assert target.read_text()=="data"
        with pytest.raises(PermissionError): target.write_text("changed")
    target.write_text("changed"); assert target.read_text()=="changed"


def test_publish_can_atomically_replace_target_while_write_lock_is_held(tmp_path: Path):
    target = tmp_path / "locked-publish.dwg"
    staged = tmp_path / "staged-locked-publish.dwg"
    target.write_bytes(b"old")
    staged.write_bytes(b"new")
    expected = file_sha256(target)

    with WindowsWriteLocks([target]):
        RecoverablePublisher().publish(
            "locked-publish",
            tmp_path,
            {target: staged},
            expected_baselines={target: expected},
        )

    assert target.read_bytes() == b"new"


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_locked_mixed_publish_failure_restores_whole_batch(tmp_path: Path, monkeypatch, fail_at: int):
    created = tmp_path / "created-locked.dwg"
    replaced = tmp_path / "replaced-locked.dwg"
    deleted = tmp_path / "deleted-locked.dwg"
    staged_created = tmp_path / "staged-created-locked.dwg"
    staged_replaced = tmp_path / "staged-replaced-locked.dwg"
    replaced.write_bytes(b"old-replaced")
    deleted.write_bytes(b"old-deleted")
    staged_created.write_bytes(b"new-created")
    staged_replaced.write_bytes(b"new-replaced")
    publisher = RecoverablePublisher()
    original_move = publisher._move_no_replace
    original_replace = publisher._replace_existing
    publish_calls = 0

    def next_call() -> None:
        nonlocal publish_calls
        publish_calls += 1
        if publish_calls == fail_at:
            raise OSError(f"注入第 {fail_at} 项锁内发布故障")

    def replace(source: Path, target: Path, backup: Path):
        next_call()
        original_replace(source, target, backup)

    def move(source: Path, target: Path):
        next_call()
        original_move(source, target)

    monkeypatch.setattr(publisher, "_replace_existing", replace)
    monkeypatch.setattr(publisher, "_move_no_replace", move)
    expected = {
        created: None,
        replaced: file_sha256(replaced),
        deleted: file_sha256(deleted),
    }

    with WindowsWriteLocks([replaced, deleted]), pytest.raises(PublishRolledBackError):
        publisher.publish(
            f"locked-mixed-{fail_at}",
            tmp_path,
            {created: staged_created, replaced: staged_replaced, deleted: None},
            expected_baselines=expected,
        )

    assert not created.exists()
    assert replaced.read_bytes() == b"old-replaced"
    assert deleted.read_bytes() == b"old-deleted"


def test_publish_rechecks_existing_target_before_first_replace(tmp_path: Path, monkeypatch):
    target = tmp_path / "existing.dwg"
    staged = tmp_path / "staged-existing.dwg"
    target.write_bytes(b"old")
    staged.write_bytes(b"new")
    expected = file_sha256(target)
    publisher = RecoverablePublisher()
    original_write_journal = publisher._write_journal

    def mutate_after_publishing(path: Path, journal: dict):
        original_write_journal(path, journal)
        if journal["status"] == "PUBLISHING":
            target.write_bytes(b"external")

    monkeypatch.setattr(publisher, "_write_journal", mutate_after_publishing)

    with pytest.raises(PublishBaselineError) as exc:
        publisher.publish(
            "race-existing",
            tmp_path,
            {target: staged},
            expected_baselines={target: expected},
        )

    assert exc.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"external"


def test_publish_rechecks_absent_create_target_before_first_replace(tmp_path: Path, monkeypatch):
    target = tmp_path / "new.dwg"
    staged = tmp_path / "staged-new.dwg"
    staged.write_bytes(b"new")
    publisher = RecoverablePublisher()
    original_write_journal = publisher._write_journal

    def create_after_publishing(path: Path, journal: dict):
        original_write_journal(path, journal)
        if journal["status"] == "PUBLISHING":
            target.write_bytes(b"external")

    monkeypatch.setattr(publisher, "_write_journal", create_after_publishing)

    with pytest.raises(PublishBaselineError) as exc:
        publisher.publish(
            "race-create",
            tmp_path,
            {target: staged},
            expected_baselines={target: None},
        )

    assert exc.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"external"


def test_create_commit_atomically_rejects_target_appearing_after_last_check(tmp_path: Path, monkeypatch):
    target = tmp_path / "atomic-create.dwg"
    staged = tmp_path / "staged-atomic-create.dwg"
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()

    def appear_then_commit(source: Path, destination: Path):
        destination.write_bytes(b"external")
        os.rename(source, destination)

    monkeypatch.setattr(publisher, "_move_no_replace", appear_then_commit, raising=False)

    with pytest.raises(PublishBaselineError) as exc_info:
        publisher.publish(
            "atomic-create-race",
            tmp_path,
            {target: staged},
            expected_baselines={target: None},
        )

    assert exc_info.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"external"


def test_existing_commit_restores_external_version_swapped_after_last_check(tmp_path: Path, monkeypatch):
    target = tmp_path / "atomic-existing.dwg"
    staged = tmp_path / "staged-atomic-existing.dwg"
    external = tmp_path / "external-atomic-existing.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    external.write_bytes(b"external")
    publisher = RecoverablePublisher()
    original_replace = publisher._replace_existing
    calls = 0

    def swap_then_replace(source: Path, destination: Path, backup: Path):
        nonlocal calls
        calls += 1
        if calls == 1:
            os.replace(external, destination)
        original_replace(source, destination, backup)

    monkeypatch.setattr(publisher, "_replace_existing", swap_then_replace, raising=False)

    with pytest.raises(PublishBaselineError) as exc_info:
        publisher.publish(
            "atomic-existing-race",
            tmp_path,
            {target: staged},
            expected_baselines={target: file_sha256(target)},
        )

    assert exc_info.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"external"
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/atomic-existing-race/publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "ROLLED_BACK"


def test_replace_api_partial_failure_restores_attempted_target_and_error_chain(tmp_path: Path, monkeypatch):
    target = tmp_path / "partial-existing.dwg"
    staged = tmp_path / "staged-partial-existing.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()

    def fail_after_moving_target(_source: Path, destination: Path, backup: Path):
        os.replace(destination, backup)
        raise OSError("ReplaceFileW 1177 注入故障")

    monkeypatch.setattr(publisher, "_replace_existing", fail_after_moving_target, raising=False)

    with pytest.raises(PublishRolledBackError) as exc_info:
        publisher.publish(
            "partial-replace",
            tmp_path,
            {target: staged},
            expected_baselines={target: file_sha256(target)},
        )

    assert target.read_bytes() == b"baseline"
    assert isinstance(exc_info.value.__cause__, OSError)
    assert "1177" in str(exc_info.value.__cause__)
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/partial-replace/publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "ROLLED_BACK"
    assert journal["files"][0]["attempted"] is True
