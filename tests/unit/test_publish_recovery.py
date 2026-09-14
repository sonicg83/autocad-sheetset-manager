import json
import os
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem import publisher as publisher_module
from dst_manager.infrastructure.filesystem.locking import WorkspaceTransactionBusyError
from dst_manager.infrastructure.filesystem.publisher import (
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


def test_recovery_rejects_a_publish_holding_the_workspace_transaction_lock(tmp_path: Path, monkeypatch):
    target = tmp_path / "active.dst"
    staged = tmp_path / "staged-active.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"after")
    publisher = RecoverablePublisher()
    original_write = publisher_module.write_journal
    recovery_was_blocked = False
    injected = False

    def recover_while_publishing(path: Path, journal: dict):
        nonlocal injected, recovery_was_blocked
        original_write(path, journal)
        if journal.get("status") == "PUBLISHING" and not injected:
            injected = True
            with pytest.raises(WorkspaceTransactionBusyError):
                RecoverablePublisher().recover(tmp_path)
            recovery_was_blocked = True

    monkeypatch.setattr(publisher_module, "write_journal", recover_while_publishing)

    publisher.publish("active-job", tmp_path, {target: staged}, attempt=1)

    assert recovery_was_blocked is True
    assert target.read_bytes() == b"after"
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/active-job/attempt-001/publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "COMMITTED"


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
        attempt=1,
        expected_baselines={target: capture_file_baseline(target)},
    )

    replace_backup = target.with_name(f".{target.name}.same-bytes-cleanup-race~001.replaced")
    assert target.read_bytes() == b"published"
    assert replace_backup.read_bytes() == b"baseline"
    assert _identity(replace_backup) == external_identity
    journal_path = tmp_path / ".dst-manager/jobs/same-bytes-cleanup-race/attempt-001/publish-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "COMMITTED"
    assert journal["cleanup_status"] == "PENDING"
    assert journal["cleanup_error_code"] == "PUBLISH_CLEANUP_FAILED"

    assert RecoverablePublisher().recover(tmp_path) == []
    assert target.read_bytes() == b"published"
    assert _identity(replace_backup) == external_identity
    assert json.loads(journal_path.read_text(encoding="utf-8"))["cleanup_status"] == "PENDING"


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

    monkeypatch.setattr(publisher_module, "replace_existing", crash_after_moving_baseline)

    with pytest.raises(_SimulatedProcessCrash):
        publisher.publish(
            operation,
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: expected},
        )

    journal_path = tmp_path / ".dst-manager/jobs" / operation / "attempt-001" / "publish-journal.json"
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

    monkeypatch.setattr(publisher_module, "replace_existing", crash_after_api_success)

    with pytest.raises(_SimulatedProcessCrash):
        publisher.publish(
            operation,
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: expected},
        )

    journal_path = tmp_path / ".dst-manager/jobs" / operation / "attempt-001" / "publish-journal.json"
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
    original_write_journal = publisher_module.write_journal

    def crash_before_commit(path: Path, journal: dict):
        if journal["status"] == "COMMITTED":
            raise _SimulatedProcessCrash
        original_write_journal(path, journal)

    monkeypatch.setattr(publisher_module, "write_journal", crash_before_commit)

    with pytest.raises(_SimulatedProcessCrash):
        publisher.publish(
            operation,
            tmp_path,
            targets,
            attempt=1,
            expected_baselines=expected,
        )

    assert RecoverablePublisher().recover(tmp_path) == [operation]
    for index, target in enumerate(targets):
        assert target.read_bytes() == f"baseline-{index}".encode()
        assert _identity(target) == baseline_identities[target]
        assert not target.with_name(f".{target.name}.{operation}~001.replaced").exists()


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
        attempt=1,
        expected_baselines={target: capture_file_baseline(target)},
    )

    committed_identity = _identity(target)
    journal_path = tmp_path / ".dst-manager/jobs" / operation / "attempt-001" / "publish-journal.json"
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
            attempt=1,
            expected_baselines={target: capture_file_baseline(target)},
        )

    journal_path = tmp_path / ".dst-manager/jobs" / operation / "attempt-001" / "publish-journal.json"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "COMMITTED"


    committed_identity = _identity(target)

    assert RecoverablePublisher().recover(tmp_path) == []
    assert target.read_bytes() == b"published"
    assert _identity(target) == committed_identity
    assert json.loads(journal_path.read_text(encoding="utf-8"))["cleanup_status"] == "COMPLETE"


def test_committed_operation_is_not_visible_without_manifest(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    target = root / "a.dst"
    staged = root / "staged.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"after")
    publisher = RecoverablePublisher()

    revision_dir = publisher.publish("job-committed", root, {target: staged}, attempt=1)
    (revision_dir / "manifest.json").unlink()

    assert publisher.list_committed_operations(root) == []


def test_archive_failure_does_not_invoke_committed_callback_or_expose_operation(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "archive-failure.dst"
    staged = tmp_path / "staged-archive-failure.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()
    callback_results: list[str] = []

    def fail_archive(*_args):
        raise OSError("注入 manifest 归档失败")

    monkeypatch.setattr(publisher_module, "archive_journal", fail_archive)

    publisher.publish(
        "archive-failure",
        tmp_path,
        {target: staged},
        attempt=1,
        on_committed=lambda _revision_dir, _journal: callback_results.append("called"),
    )

    assert callback_results == []
    assert publisher.list_committed_operations(tmp_path) == []
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/archive-failure/attempt-001/publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "COMMITTED"
    assert journal["cleanup_error_code"] == "PUBLISH_ARCHIVE_FAILED"


def test_committed_callback_runs_after_publish_cleanup_attempt(tmp_path: Path):
    target = tmp_path / "callback-order.dst"
    staged = tmp_path / "staged-callback-order.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"after")
    observed: dict[str, object] = {}

    def observe_cleanup(_revision_dir: Path, journal: dict):
        observed["cleanup_status"] = journal["cleanup_status"]
        observed["replace_backup_exists"] = Path(journal["files"][0]["replace_backup"]).exists()

    RecoverablePublisher().publish(
        "callback-order",
        tmp_path,
        {target: staged},
        attempt=1,
        on_committed=observe_cleanup,
    )

    assert observed == {
        "cleanup_status": "COMPLETE",
        "replace_backup_exists": False,
    }


def test_archive_copy_failure_does_not_leave_visible_manifest(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "archive-copy-failure.dst"
    staged = tmp_path / "staged-archive-copy-failure.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"published")
    original_copy = publisher_module.shutil.copy2

    def fail_publish_journal_copy(source, destination, *args, **kwargs):
        if Path(destination).name == "publish-journal.json":
            raise OSError("注入归档 journal 复制失败")
        return original_copy(source, destination, *args, **kwargs)

    monkeypatch.setattr(publisher_module.shutil, "copy2", fail_publish_journal_copy)

    RecoverablePublisher().publish(
        "archive-copy-failure",
        tmp_path,
        {target: staged},
        attempt=1,
    )

    revision_dir = tmp_path / ".dst-manager/revisions/archive-copy-failure/attempt-001"
    assert not (revision_dir / "manifest.json").exists()


def test_startup_refreshes_pending_manifest_after_second_archive_failure(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "cleanup-archive-retry.dst"
    staged = tmp_path / "staged-cleanup-archive-retry.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()
    original_archive = publisher_module.archive_journal
    archive_calls = 0

    def fail_second_archive(*args):
        nonlocal archive_calls
        archive_calls += 1
        if archive_calls == 2:
            raise OSError("注入 cleanup 完成后的归档失败")
        return original_archive(*args)

    monkeypatch.setattr(publisher_module, "archive_journal", fail_second_archive)
    publisher.publish("cleanup-archive-retry", tmp_path, {target: staged}, attempt=1)
    journal_path = tmp_path / ".dst-manager/jobs/cleanup-archive-retry/attempt-001/publish-journal.json"
    manifest_path = tmp_path / ".dst-manager/revisions/cleanup-archive-retry/attempt-001/manifest.json"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["cleanup_status"] == "COMPLETE"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["cleanup_status"] == "PENDING"

    publisher.recover(tmp_path)

    assert json.loads(manifest_path.read_text(encoding="utf-8")) == json.loads(
        journal_path.read_text(encoding="utf-8"),
    )


def test_startup_refreshes_manifest_when_content_differs_from_committed_journal(tmp_path: Path):
    target = tmp_path / "manifest-content-refresh.dst"
    staged = tmp_path / "staged-manifest-content-refresh.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()
    publisher.publish("manifest-content-refresh", tmp_path, {target: staged}, attempt=1)
    journal_path = tmp_path / ".dst-manager/jobs/manifest-content-refresh/attempt-001/publish-journal.json"
    manifest_path = tmp_path / ".dst-manager/revisions/manifest-content-refresh/attempt-001/manifest.json"
    stale_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stale_manifest["cleanup_error_detail"] = "stale-manifest"
    manifest_path.write_text(json.dumps(stale_manifest), encoding="utf-8")

    publisher.recover(tmp_path)

    assert json.loads(manifest_path.read_text(encoding="utf-8")) == json.loads(
        journal_path.read_text(encoding="utf-8"),
    )


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("result_hash", "0" * 64),
        ("result_identity", [999, 999]),
    ],
)
def test_startup_rejects_main_journal_file_identity_projection_tampering(
    tmp_path: Path,
    field: str,
    tampered_value,
):
    target = tmp_path / f"immutable-{field}.dst"
    staged = tmp_path / f"staged-immutable-{field}.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()
    operation_id = f"immutable-{field}"
    publisher.publish(operation_id, tmp_path, {target: staged}, attempt=1)
    journal_path = tmp_path / ".dst-manager/jobs" / operation_id / "attempt-001" / "publish-journal.json"
    manifest_path = tmp_path / ".dst-manager/revisions" / operation_id / "attempt-001" / "manifest.json"
    safe_manifest = manifest_path.read_bytes()
    tampered = json.loads(journal_path.read_text(encoding="utf-8"))
    tampered["files"][0][field] = tampered_value
    journal_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(PublishRecoveryError, match="PUBLISH_MANIFEST_IMMUTABLE_MISMATCH"):
        publisher.recover(tmp_path)

    assert manifest_path.read_bytes() == safe_manifest


def test_startup_rejects_main_journal_operation_id_tampering(tmp_path: Path):
    target = tmp_path / "immutable-operation.dst"
    staged = tmp_path / "staged-immutable-operation.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()
    operation_id = "immutable-operation"
    publisher.publish(operation_id, tmp_path, {target: staged}, attempt=1)
    journal_path = tmp_path / ".dst-manager/jobs" / operation_id / "attempt-001" / "publish-journal.json"
    manifest_path = tmp_path / ".dst-manager/revisions" / operation_id / "attempt-001" / "manifest.json"
    safe_manifest = manifest_path.read_bytes()
    tampered = json.loads(journal_path.read_text(encoding="utf-8"))
    tampered["operation_id"] = "tampered-operation"
    journal_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(PublishRecoveryError, match="PUBLISH_MANIFEST_IMMUTABLE_MISMATCH"):
        publisher.recover(tmp_path)

    assert manifest_path.read_bytes() == safe_manifest


@pytest.mark.parametrize("status", ["PREPARED", "PUBLISHING", "ROLLING_BACK"])
def test_startup_recovery_reads_nested_attempt_journal(tmp_path: Path, status: str):
    """嵌套 attempt 布局下的未完成日志在启动恢复时按嵌套路径回滚。"""
    operation = "nested-crash"
    target = tmp_path / "target.txt"
    target.write_text("after")
    backup = tmp_path / ".dst-manager" / "revisions" / operation / "attempt-001" / "before" / target.name
    backup.parent.mkdir(parents=True)
    backup.write_text("before")
    journal_path = tmp_path / ".dst-manager" / "jobs" / operation / "attempt-001" / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal = {
        "operation_id": operation,
        "attempt": 1,
        "status": status,
        "files": [{"target": str(target), "backup": str(backup), "staged": None, "replaced": status != "PREPARED"}],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    assert RecoverablePublisher().recover(tmp_path) == [operation]
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"
    assert target.read_text() == ("after" if status == "PREPARED" else "before")


@pytest.mark.parametrize(
    ("attempt_dir_name", "journal_attempt"),
    [("attempt-foo", 1), ("attempt-000", 0), ("attempt-01", 1), ("attempt-001", 2)],
)
def test_startup_recovery_rejects_noncanonical_or_mismatched_attempt_identity(
    tmp_path: Path,
    attempt_dir_name: str,
    journal_attempt: int,
):
    operation = "bad-attempt-identity"
    journal_path = tmp_path / ".dst-manager" / "jobs" / operation / attempt_dir_name / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal_path.write_text(
        json.dumps({"operation_id": operation, "attempt": journal_attempt, "status": "PREPARED", "files": []}),
        encoding="utf-8",
    )
    with pytest.raises(PublishRecoveryError, match="PUBLISH_MANIFEST_IMMUTABLE_MISMATCH"):
        RecoverablePublisher().recover(tmp_path)

def test_retry_preserves_rolled_back_previous_attempt_evidence(tmp_path: Path):
    """attempt-002 成功后，attempt-001 的回滚日志与 before 快照仍永久存在。"""
    job_id = "preserve-rolled-back"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")

    def replace(source: Path, target_path: Path):
        raise OSError("注入首次发布故障")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=1)
    first_journal = tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-001" / "publish-journal.json"
    first_before = tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-001" / "before" / target.name
    journal_bytes = first_journal.read_bytes()
    before_bytes = first_before.read_bytes()

    revision_dir = RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert revision_dir.name == "attempt-002"
    assert first_journal.read_bytes() == journal_bytes
    assert first_before.read_bytes() == before_bytes


@pytest.mark.parametrize("status", ["ABORTED_BASELINE_CHANGED", "ROLLBACK_FAILED"])
def test_new_attempt_never_deletes_previous_terminal_or_unproven_evidence(tmp_path: Path, status: str):
    """旧 attempt 无论已安全终结还是需要人工复核，都不由发布路径自动删除。"""
    job_id = f"preserve-{status.lower()}"
    jobs_attempt = tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-001"
    revisions_attempt = tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-001"
    jobs_attempt.mkdir(parents=True)
    revisions_attempt.mkdir(parents=True)
    journal = {"operation_id": job_id, "attempt": 1, "status": status, "files": []}
    (jobs_attempt / "publish-journal.json").write_text(json.dumps(journal), encoding="utf-8")
    evidence = revisions_attempt / "evidence.bin"
    evidence.write_bytes(b"keep")
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")

    RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert (jobs_attempt / "publish-journal.json").is_file()
    assert evidence.read_bytes() == b"keep"


def test_legacy_flat_committed_manifest_is_listed_after_upgrade(tmp_path: Path):
    """旧布局 COMMITTED 清单在升级后仍可被 list/read_committed_operation 枚举。"""
    operation = "legacy-committed"
    revisions = tmp_path / ".dst-manager" / "revisions" / operation
    revisions.mkdir(parents=True)
    manifest = {
        "identity_version": 1,
        "operation_id": operation,
        "status": "COMMITTED",
        "files": [{"target": str(tmp_path / "target.txt")}],
    }
    (revisions / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    publisher = RecoverablePublisher()
    listed = publisher.list_committed_operations(tmp_path)
    assert [journal["operation_id"] for journal in listed] == [operation]
    assert publisher.read_committed_operation(tmp_path, operation) == manifest


def test_legacy_flat_publishing_journal_recovers_before_new_publish(tmp_path: Path):
    """旧平铺 PUBLISHING 残留先被恢复并永久保留，随后新 attempt 正常发布。"""
    operation = "legacy-publishing"
    target = tmp_path / "target.txt"
    target.write_text("after")
    backup = tmp_path / ".dst-manager" / "revisions" / operation / "before" / target.name
    backup.parent.mkdir(parents=True)
    backup.write_text("before")
    legacy_journal = tmp_path / ".dst-manager" / "jobs" / operation / "publish-journal.json"
    legacy_journal.parent.mkdir(parents=True)
    legacy_journal.write_text(
        json.dumps({
            "operation_id": operation,
            "status": "PUBLISHING",
            "files": [{"target": str(target), "backup": str(backup), "staged": None, "replaced": True}],
        }),
        encoding="utf-8",
    )
    publisher = RecoverablePublisher()
    assert publisher.recover(tmp_path) == [operation]
    assert target.read_text() == "before"

    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    revision_dir = publisher.publish(operation, tmp_path, {target: staged}, attempt=1)
    assert revision_dir == tmp_path / ".dst-manager" / "revisions" / operation / "attempt-001"
    assert target.read_text() == "after"
    # 旧布局证据同样永久保留；新 attempt 不复用也不覆盖它。
    assert legacy_journal.is_file()
    assert json.loads(legacy_journal.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"
    assert backup.read_text() == "before"
