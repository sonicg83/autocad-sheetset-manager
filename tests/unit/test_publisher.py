import ctypes
import json
import os
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem.locking import WindowsWriteLocks
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
    RecoverablePublisher,
    capture_file_baseline,
    file_sha256,
)


def _identity(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_dev, stat.st_ino]


class _SimulatedProcessCrash(BaseException):
    pass


def test_caller_identity_baseline_allows_unchanged_target(tmp_path: Path):
    target = tmp_path / "caller-baseline.dwg"
    staged = tmp_path / "staged-caller-baseline.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    expected = capture_file_baseline(target)

    RecoverablePublisher().publish(
        "caller-baseline-unchanged",
        tmp_path,
        {target: staged},
        expected_baselines={target: expected},
    )

    assert target.read_bytes() == b"published"


def test_caller_identity_baseline_rejects_same_bytes_replacement_before_publish(tmp_path: Path):
    target = tmp_path / "caller-race.dwg"
    staged = tmp_path / "staged-caller-race.dwg"
    external = tmp_path / "external-caller-race.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    external.write_bytes(b"baseline")
    expected = capture_file_baseline(target)
    external_identity = _identity(external)
    os.replace(external, target)

    with pytest.raises(PublishBaselineError) as exc_info:
        RecoverablePublisher().publish(
            "caller-identity-race",
            tmp_path,
            {target: staged},
            expected_baselines={target: expected},
        )

    assert exc_info.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"baseline"
    assert _identity(target) == external_identity


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
    expected = capture_file_baseline(target)

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
        replaced: capture_file_baseline(replaced),
        deleted: capture_file_baseline(deleted),
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
    expected = capture_file_baseline(target)
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
            expected_baselines={target: capture_file_baseline(target)},
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
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert target.read_bytes() == b"baseline"
    assert isinstance(exc_info.value.__cause__, OSError)
    assert "1177" in str(exc_info.value.__cause__)
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/partial-replace/publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "ROLLED_BACK"
    assert journal["files"][0]["attempted"] is True


def test_existing_commit_rejects_same_bytes_external_identity(tmp_path: Path, monkeypatch):
    target = tmp_path / "same-bytes-existing.dwg"
    staged = tmp_path / "staged-same-bytes-existing.dwg"
    external = tmp_path / "external-same-bytes-existing.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    external.write_bytes(b"baseline")
    external_identity = _identity(external)
    publisher = RecoverablePublisher()
    original_replace = publisher._replace_existing
    calls = 0

    def swap_same_bytes_then_replace(source: Path, destination: Path, backup: Path):
        nonlocal calls
        calls += 1
        if calls == 1:
            os.replace(external, destination)
        original_replace(source, destination, backup)

    monkeypatch.setattr(publisher, "_replace_existing", swap_same_bytes_then_replace, raising=False)

    with pytest.raises(PublishBaselineError) as exc_info:
        publisher.publish(
            "same-bytes-existing-race",
            tmp_path,
            {target: staged},
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert exc_info.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"baseline"
    assert _identity(target) == external_identity


def test_committed_cleanup_preserves_same_bytes_external_backup_as_pending(tmp_path: Path, monkeypatch):
    target = tmp_path / "cleanup-existing.dwg"
    staged = tmp_path / "staged-cleanup-existing.dwg"
    external = tmp_path / "external-cleanup-backup.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    external.write_bytes(b"baseline")
    external_identity = _identity(external)
    publisher = RecoverablePublisher()
    original_cleanup = publisher._cleanup_replace_backups

    def swap_backup_before_cleanup(entries: list[dict]):
        replace_backup = Path(entries[0]["replace_backup"])
        os.replace(external, replace_backup)
        original_cleanup(entries)

    monkeypatch.setattr(publisher, "_cleanup_replace_backups", swap_backup_before_cleanup)

    publisher.publish(
        "same-bytes-cleanup-race",
        tmp_path,
        {target: staged},
        expected_baselines={target: capture_file_baseline(target)},
    )

    replace_backup = target.with_name(f".{target.name}.same-bytes-cleanup-race.replaced")
    assert target.read_bytes() == b"published"
    assert replace_backup.read_bytes() == b"baseline"
    assert _identity(replace_backup) == external_identity
    journal_path = tmp_path / ".dst-manager/jobs/same-bytes-cleanup-race/publish-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "COMMITTED"
    assert journal["cleanup_status"] == "PENDING"
    assert journal["cleanup_error_code"] == "PUBLISH_CLEANUP_FAILED"

    assert RecoverablePublisher().recover(tmp_path) == []
    assert target.read_bytes() == b"published"
    assert _identity(replace_backup) == external_identity
    assert json.loads(journal_path.read_text(encoding="utf-8"))["cleanup_status"] == "PENDING"


def test_existing_result_identity_recheck_preserves_late_external_target(tmp_path: Path, monkeypatch):
    target = tmp_path / "late-result-existing.dwg"
    staged = tmp_path / "staged-late-result-existing.dwg"
    external = tmp_path / "external-late-result-existing.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    external.write_bytes(b"published")
    external_identity = _identity(external)
    publisher = RecoverablePublisher()
    original_commit = publisher._commit_existing

    def swap_after_commit_check(entry: dict, publish_temp: Path, operation_id: str):
        original_commit(entry, publish_temp, operation_id)
        os.replace(external, Path(entry["target"]))

    monkeypatch.setattr(publisher, "_commit_existing", swap_after_commit_check)

    with pytest.raises(PublishBaselineError):
        publisher.publish(
            "late-result-existing-race",
            tmp_path,
            {target: staged},
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert target.read_bytes() == b"published"
    assert _identity(target) == external_identity


def test_delete_result_identity_recheck_preserves_late_external_target(tmp_path: Path, monkeypatch):
    target = tmp_path / "late-result-delete.dwg"
    external = tmp_path / "external-late-result-delete.dwg"
    target.write_bytes(b"baseline")
    external.write_bytes(b"external")
    external_identity = _identity(external)
    publisher = RecoverablePublisher()
    original_commit = publisher._commit_delete

    def recreate_after_commit_check(entry: dict):
        original_commit(entry)
        os.replace(external, Path(entry["target"]))

    monkeypatch.setattr(publisher, "_commit_delete", recreate_after_commit_check)

    with pytest.raises(PublishBaselineError):
        publisher.publish(
            "late-result-delete-race",
            tmp_path,
            {target: None},
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert target.read_bytes() == b"external"
    assert _identity(target) == external_identity


def test_startup_recovery_rejects_same_bytes_external_target_identity(tmp_path: Path):
    operation = "same-bytes-recovery-race"
    target = tmp_path / "recovery-existing.dwg"
    target.write_bytes(b"published")
    publish_identity = _identity(target)
    staged = tmp_path / "staged-recovery-existing.dwg"
    staged.write_bytes(b"published")
    before = tmp_path / ".dst-manager/revisions" / operation / "before" / target.name
    before.parent.mkdir(parents=True)
    before.write_bytes(b"baseline")
    replace_backup = tmp_path / f".{target.name}.{operation}.replaced"
    replace_backup.write_bytes(b"baseline")
    baseline_identity = _identity(replace_backup)
    external = tmp_path / "external-recovery-existing.dwg"
    external.write_bytes(b"baseline")
    external_identity = _identity(external)
    os.replace(external, target)
    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal = {
        "identity_version": 1,
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
                "baseline_identity": baseline_identity,
                "before_identity": _identity(before),
                "expected_backup_identity": baseline_identity,
                "publish_identity": publish_identity,
                "result_identity": publish_identity,
                "attempted": True,
                "replaced": True,
                "conflict_preserved": False,
            },
        ],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(PublishRecoveryError):
        RecoverablePublisher().recover(tmp_path)

    assert target.read_bytes() == b"baseline"
    assert _identity(target) == external_identity
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLBACK_FAILED"


def test_startup_recovery_does_not_rebuild_externally_deleted_target(tmp_path: Path):
    operation = "deleted-recovery-race"
    target = tmp_path / "deleted-recovery-existing.dwg"
    target.write_bytes(b"published")
    publish_identity = _identity(target)
    staged = tmp_path / "staged-deleted-recovery-existing.dwg"
    staged.write_bytes(b"published")
    before = tmp_path / ".dst-manager/revisions" / operation / "before" / target.name
    before.parent.mkdir(parents=True)
    before.write_bytes(b"baseline")
    replace_backup = tmp_path / f".{target.name}.{operation}.replaced"
    replace_backup.write_bytes(b"baseline")
    baseline_identity = _identity(replace_backup)
    target.unlink()
    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal = {
        "identity_version": 1,
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
                "baseline_identity": baseline_identity,
                "before_identity": _identity(before),
                "expected_backup_identity": baseline_identity,
                "publish_identity": publish_identity,
                "result_identity": publish_identity,
                "attempted": True,
                "replaced": True,
                "conflict_preserved": False,
            },
        ],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(PublishRecoveryError):
        RecoverablePublisher().recover(tmp_path)

    assert not target.exists()
    assert replace_backup.read_bytes() == b"baseline"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLBACK_FAILED"


def test_startup_recovery_preserves_same_bytes_external_replacement_backup(tmp_path: Path):
    operation = "same-bytes-backup-recovery-race"
    target = tmp_path / "backup-recovery-existing.dwg"
    target.write_bytes(b"published")
    publish_identity = _identity(target)
    staged = tmp_path / "staged-backup-recovery-existing.dwg"
    staged.write_bytes(b"published")
    before = tmp_path / ".dst-manager/revisions" / operation / "before" / target.name
    before.parent.mkdir(parents=True)
    before.write_bytes(b"baseline")
    replace_backup = tmp_path / f".{target.name}.{operation}.replaced"
    replace_backup.write_bytes(b"baseline")
    baseline_identity = _identity(replace_backup)
    external = tmp_path / "external-backup-recovery-existing.dwg"
    external.write_bytes(b"baseline")
    external_identity = _identity(external)
    os.replace(external, replace_backup)
    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal = {
        "identity_version": 1,
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
                "baseline_identity": baseline_identity,
                "before_identity": _identity(before),
                "expected_backup_identity": baseline_identity,
                "publish_identity": publish_identity,
                "result_identity": publish_identity,
                "attempted": True,
                "replaced": True,
                "conflict_preserved": False,
            },
        ],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(PublishRecoveryError):
        RecoverablePublisher().recover(tmp_path)

    assert target.read_bytes() == b"published"
    assert _identity(target) == publish_identity
    assert replace_backup.read_bytes() == b"baseline"
    assert _identity(replace_backup) == external_identity
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLBACK_FAILED"


def test_partial_replace_with_staged_result_at_target_restores_original_identity(tmp_path: Path, monkeypatch):
    target = tmp_path / "partial-result-existing.dwg"
    staged = tmp_path / "staged-partial-result-existing.dwg"
    target.write_bytes(b"same-content")
    staged.write_bytes(b"same-content")
    baseline_identity = _identity(target)
    published_identity: list[int] | None = None
    publisher = RecoverablePublisher()
    original_replace = publisher._replace_existing
    calls = 0

    def fail_after_installing_staged(source: Path, destination: Path, backup: Path):
        nonlocal calls, published_identity
        calls += 1
        if calls > 1:
            original_replace(source, destination, backup)
            return
        os.replace(destination, backup)
        os.replace(source, destination)
        published_identity = _identity(destination)
        raise OSError("ReplaceFileW 1176 注入故障")

    monkeypatch.setattr(publisher, "_replace_existing", fail_after_installing_staged, raising=False)

    with pytest.raises(PublishRolledBackError) as exc_info:
        publisher.publish(
            "partial-staged-result",
            tmp_path,
            {target: staged},
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert published_identity is not None
    assert published_identity != baseline_identity
    assert _identity(target) == baseline_identity
    assert isinstance(exc_info.value.__cause__, OSError)
    assert "1176" in str(exc_info.value.__cause__)


def test_startup_recovery_restores_partial_replace_when_publish_source_still_exists(
    tmp_path: Path,
    monkeypatch,
):
    operation = "crash-with-publish-source"
    target = tmp_path / "partial-crash.dwg"
    staged = tmp_path / "staged-partial-crash.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    baseline_identity = _identity(target)
    expected = capture_file_baseline(target)
    publisher = RecoverablePublisher()

    def crash_after_moving_baseline(_source: Path, destination: Path, backup: Path):
        os.replace(destination, backup)
        raise _SimulatedProcessCrash

    monkeypatch.setattr(publisher, "_replace_existing", crash_after_moving_baseline)

    with pytest.raises(_SimulatedProcessCrash):
        publisher.publish(
            operation,
            tmp_path,
            {target: staged},
            expected_baselines={target: expected},
        )

    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    publish_source = Path(journal["files"][0]["publish_source"])
    assert publish_source.is_file()
    assert _identity(publish_source) == journal["files"][0]["publish_identity"]

    assert RecoverablePublisher().recover(tmp_path) == [operation]
    assert target.read_bytes() == b"baseline"
    assert _identity(target) == baseline_identity
    assert not Path(journal["files"][0]["replace_backup"]).exists()
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"


def test_startup_recovery_does_not_restore_after_publish_source_moved_and_target_deleted(
    tmp_path: Path,
    monkeypatch,
):
    operation = "crash-after-source-moved"
    target = tmp_path / "successful-crash.dwg"
    staged = tmp_path / "staged-successful-crash.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    expected = capture_file_baseline(target)
    publisher = RecoverablePublisher()

    def crash_after_api_success(source: Path, destination: Path, backup: Path):
        os.replace(destination, backup)
        os.replace(source, destination)
        destination.unlink()
        raise _SimulatedProcessCrash

    monkeypatch.setattr(publisher, "_replace_existing", crash_after_api_success)

    with pytest.raises(_SimulatedProcessCrash):
        publisher.publish(
            operation,
            tmp_path,
            {target: staged},
            expected_baselines={target: expected},
        )

    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    publish_source = Path(journal["files"][0]["publish_source"])
    replace_backup = Path(journal["files"][0]["replace_backup"])
    assert not publish_source.exists()

    with pytest.raises(PublishRecoveryError):
        RecoverablePublisher().recover(tmp_path)

    assert not target.exists()
    assert replace_backup.read_bytes() == b"baseline"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLBACK_FAILED"


def test_startup_recovery_rejects_unknown_identity_version_without_legacy_fallback(tmp_path: Path):
    operation = "unknown-identity-version"
    target = tmp_path / "unknown-version.dwg"
    before = tmp_path / ".dst-manager/revisions" / operation / "before" / target.name
    before.parent.mkdir(parents=True)
    before.write_bytes(b"baseline")
    target.write_bytes(b"published")
    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal = {
        "identity_version": 2,
        "operation_id": operation,
        "status": "PUBLISHING",
        "files": [
            {
                "target": str(target),
                "staged": None,
                "backup": str(before),
                "before_hash": file_sha256(before),
                "attempted": True,
                "replaced": True,
            },
        ],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(PublishRecoveryError, match="PUBLISH_IDENTITY_VERSION_UNSUPPORTED"):
        RecoverablePublisher().recover(tmp_path)

    assert target.read_bytes() == b"published"
    persisted = json.loads(journal_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "ROLLBACK_FAILED"
    assert persisted["recovery_error_code"] == "PUBLISH_IDENTITY_VERSION_UNSUPPORTED"


def test_crash_before_committed_journal_recovers_batch_with_original_identities(
    tmp_path: Path,
    monkeypatch,
):
    operation = "crash-before-committed"
    targets: dict[Path, Path] = {}
    baseline_identities: dict[Path, list[int]] = {}
    expected = {}
    for index in range(2):
        target = tmp_path / f"commit-boundary-{index}.dwg"
        staged = tmp_path / f"staged-commit-boundary-{index}.dwg"
        target.write_bytes(f"baseline-{index}".encode())
        staged.write_bytes(f"published-{index}".encode())
        targets[target] = staged
        baseline_identities[target] = _identity(target)
        expected[target] = capture_file_baseline(target)
    publisher = RecoverablePublisher()
    original_write_journal = publisher._write_journal

    def crash_before_commit(path: Path, journal: dict):
        if journal["status"] == "COMMITTED":
            raise _SimulatedProcessCrash
        original_write_journal(path, journal)

    monkeypatch.setattr(publisher, "_write_journal", crash_before_commit)

    with pytest.raises(_SimulatedProcessCrash):
        publisher.publish(
            operation,
            tmp_path,
            targets,
            expected_baselines=expected,
        )

    assert RecoverablePublisher().recover(tmp_path) == [operation]
    for index, target in enumerate(targets):
        assert target.read_bytes() == f"baseline-{index}".encode()
        assert _identity(target) == baseline_identities[target]
        assert not target.with_name(f".{target.name}.{operation}.replaced").exists()


def test_committed_cleanup_failure_keeps_results_and_retries_on_startup(
    tmp_path: Path,
    monkeypatch,
):
    operation = "committed-cleanup-failure"
    target = tmp_path / "cleanup-failure.dwg"
    staged = tmp_path / "staged-cleanup-failure.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()

    def fail_cleanup(_entries: list[dict]):
        raise OSError("注入 cleanup 故障")

    monkeypatch.setattr(publisher, "_cleanup_replace_backups", fail_cleanup)

    publisher.publish(
        operation,
        tmp_path,
        {target: staged},
        expected_baselines={target: capture_file_baseline(target)},
    )

    committed_identity = _identity(target)
    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    replace_backup = Path(journal["files"][0]["replace_backup"])
    assert target.read_bytes() == b"published"
    assert journal["status"] == "COMMITTED"
    assert journal["cleanup_status"] == "PENDING"
    assert journal["cleanup_error_code"] == "PUBLISH_CLEANUP_FAILED"
    assert replace_backup.is_file()

    assert RecoverablePublisher().recover(tmp_path) == []
    assert target.read_bytes() == b"published"
    assert _identity(target) == committed_identity
    assert not replace_backup.exists()
    cleaned = json.loads(journal_path.read_text(encoding="utf-8"))
    assert cleaned["status"] == "COMMITTED"
    assert cleaned["cleanup_status"] == "COMPLETE"


def test_startup_resumes_cleanup_after_crash_following_committed_journal(
    tmp_path: Path,
    monkeypatch,
):
    operation = "crash-after-committed"
    target = tmp_path / "cleanup-crash.dwg"
    staged = tmp_path / "staged-cleanup-crash.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()

    def crash_during_cleanup(_entries: list[dict]):
        raise _SimulatedProcessCrash

    monkeypatch.setattr(publisher, "_cleanup_replace_backups", crash_during_cleanup)

    with pytest.raises(_SimulatedProcessCrash):
        publisher.publish(
            operation,
            tmp_path,
            {target: staged},
            expected_baselines={target: capture_file_baseline(target)},
        )

    journal_path = tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "COMMITTED"


    committed_identity = _identity(target)

    assert RecoverablePublisher().recover(tmp_path) == []
    assert target.read_bytes() == b"published"
    assert _identity(target) == committed_identity
    assert json.loads(journal_path.read_text(encoding="utf-8"))["cleanup_status"] == "COMPLETE"


def test_committed_operation_can_be_read_from_active_journal_when_manifest_is_missing(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    target = root / "a.dst"
    staged = root / "staged.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"after")
    publisher = RecoverablePublisher()

    revision_dir = publisher.publish("job-committed", root, {target: staged})
    (revision_dir / "manifest.json").unlink()

    committed = publisher.list_committed_operations(root)

    assert len(committed) == 1
    assert committed[0]["operation_id"] == "job-committed"
    assert committed[0]["status"] == "COMMITTED"
    assert committed[0]["files"][0]["before_hash"] == file_sha256(revision_dir / "before" / "a.dst")
    assert committed[0]["files"][0]["result_hash"] == file_sha256(target)


def test_winerror32_rollback_preserves_original_identity_or_reports_failure(
    tmp_path: Path,
    monkeypatch,
):
    operation = "rollback-winerror32"
    target = tmp_path / "rollback-winerror32.dwg"
    staged = tmp_path / "staged-rollback-winerror32.dwg"
    target.write_bytes(b"baseline")
    staged.write_bytes(b"published")
    baseline_identity = _identity(target)
    publisher = RecoverablePublisher()
    original_replace = publisher._replace_existing
    calls = 0

    def fail_first_rollback_replace(source: Path, destination: Path, backup: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ctypes.WinError(32)
        original_replace(source, destination, backup)

    def fail_after_commit(_entry: dict):
        raise OSError("注入结果复核故障")

    monkeypatch.setattr(publisher, "_replace_existing", fail_first_rollback_replace)
    monkeypatch.setattr(publisher, "_capture_result", fail_after_commit)

    with pytest.raises((PublishRolledBackError, PublishRecoveryError)):
        publisher.publish(
            operation,
            tmp_path,
            {target: staged},
            expected_baselines={target: capture_file_baseline(target)},
        )

    journal = json.loads(
        (tmp_path / ".dst-manager/jobs" / operation / "publish-journal.json").read_text(encoding="utf-8"),
    )
    replace_backup = Path(journal["files"][0]["replace_backup"])
    if journal["status"] == "ROLLED_BACK":
        assert _identity(target) == baseline_identity
        assert not replace_backup.exists()
    else:
        assert journal["status"] == "ROLLBACK_FAILED"
        assert replace_backup.is_file()
        assert _identity(replace_backup) == baseline_identity
