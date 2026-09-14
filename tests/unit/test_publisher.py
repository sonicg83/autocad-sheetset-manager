import ctypes
import json
import os
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem import publisher as publisher_module
from dst_manager.infrastructure.filesystem.locking import WindowsWriteLocks
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
    RecoverablePublisher,
    capture_file_baseline,
)


def _identity(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_dev, stat.st_ino]


def test_publish_fence_aborts_before_replacing_formal_file(tmp_path: Path):
    target = tmp_path / "fenced-target.dwg"
    staged = tmp_path / "fenced-staged.dwg"
    target.write_bytes(b"before")
    staged.write_bytes(b"after")

    def reject_publish() -> None:
        raise PublishBaselineError("PUBLISH_FENCE_LOST")

    with pytest.raises(PublishBaselineError, match="PUBLISH_FENCE_LOST"):
        RecoverablePublisher().publish(
            "fenced-publish",
            tmp_path,
            {target: staged},
            attempt=1,
            before_commit=reject_publish,
        )

    assert target.read_bytes() == b"before"
    assert not (tmp_path / ".dst-manager" / "revisions" / "fenced-publish" / "attempt-001" / "manifest.json").exists()


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
        RecoverablePublisher(replace).publish("fault", tmp_path, targets, attempt=1)
    assert [path.read_text() for path in targets] == ["before-0", "before-1", "before-2"]
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/fault/attempt-001/publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "ROLLED_BACK"
    assert all((tmp_path / ".dst-manager/revisions/fault/attempt-001/before" / path.name).is_file() for path in targets)


def test_deleted_file_is_restored_when_later_publish_fails(tmp_path: Path):
    deleted, replaced, staged = tmp_path / "delete.txt", tmp_path / "replace.txt", tmp_path / "staged.txt"
    deleted.write_text("keep-delete"); replaced.write_text("keep-replace"); staged.write_text("new")
    def fail(*_): raise OSError("fail")
    # 删除项先执行，第二项替换失败。
    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(fail).publish("delete-fault", tmp_path, {deleted: None, replaced: staged}, attempt=1)
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
    original_move = publisher_module.move_no_replace

    def move(source: Path, target: Path):
        if fail_at == 3 and source == deleted:
            raise OSError("注入第 3 项发布故障")
        original_move(source, target)

    monkeypatch.setattr(publisher_module, "move_no_replace", move)

    with pytest.raises(PublishRolledBackError, match=f"注入第 {fail_at} 项发布故障"):
        publisher.publish(
            f"mixed-{fail_at}",
            tmp_path,
            {created: staged_created, replaced: staged_replaced, deleted: None},
            attempt=1,
        )

    assert not created.exists()
    assert replaced.read_bytes() == b"old-replaced"
    assert deleted.read_bytes() == b"old-deleted"
    journal = json.loads(
        (tmp_path / ".dst-manager" / "jobs" / f"mixed-{fail_at}" / "attempt-001" / "publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "ROLLED_BACK"


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
    original_move = publisher_module.move_no_replace
    original_replace = publisher_module.replace_existing
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

    monkeypatch.setattr(publisher_module, "replace_existing", replace)
    monkeypatch.setattr(publisher_module, "move_no_replace", move)
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
            attempt=1,
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
    original_write_journal = publisher_module.write_journal

    def mutate_after_publishing(path: Path, journal: dict):
        original_write_journal(path, journal)
        if journal["status"] == "PUBLISHING":
            target.write_bytes(b"external")

    monkeypatch.setattr(publisher_module, "write_journal", mutate_after_publishing)

    with pytest.raises(PublishBaselineError) as exc:
        publisher.publish(
            "race-existing",
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: expected},
        )

    assert exc.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"external"


def test_publish_rechecks_absent_create_target_before_first_replace(tmp_path: Path, monkeypatch):
    target = tmp_path / "new.dwg"
    staged = tmp_path / "staged-new.dwg"
    staged.write_bytes(b"new")
    publisher = RecoverablePublisher()
    original_write_journal = publisher_module.write_journal

    def create_after_publishing(path: Path, journal: dict):
        original_write_journal(path, journal)
        if journal["status"] == "PUBLISHING":
            target.write_bytes(b"external")

    monkeypatch.setattr(publisher_module, "write_journal", create_after_publishing)

    with pytest.raises(PublishBaselineError) as exc:
        publisher.publish(
            "race-create",
            tmp_path,
            {target: staged},
            attempt=1,
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

    monkeypatch.setattr(publisher_module, "move_no_replace", appear_then_commit, raising=False)

    with pytest.raises(PublishBaselineError) as exc_info:
        publisher.publish(
            "atomic-create-race",
            tmp_path,
            {target: staged},
            attempt=1,
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
    original_replace = publisher_module.replace_existing
    calls = 0

    def swap_then_replace(source: Path, destination: Path, backup: Path):
        nonlocal calls
        calls += 1
        if calls == 1:
            os.replace(external, destination)
        original_replace(source, destination, backup)

    monkeypatch.setattr(publisher_module, "replace_existing", swap_then_replace, raising=False)

    with pytest.raises(PublishBaselineError) as exc_info:
        publisher.publish(
            "atomic-existing-race",
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert exc_info.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"external"
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/atomic-existing-race/attempt-001/publish-journal.json").read_text(encoding="utf-8"),
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

    monkeypatch.setattr(publisher_module, "replace_existing", fail_after_moving_target, raising=False)

    with pytest.raises(PublishRolledBackError) as exc_info:
        publisher.publish(
            "partial-replace",
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert target.read_bytes() == b"baseline"
    assert isinstance(exc_info.value.__cause__, OSError)
    assert "1177" in str(exc_info.value.__cause__)
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/partial-replace/attempt-001/publish-journal.json").read_text(encoding="utf-8"),
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
    original_replace = publisher_module.replace_existing
    calls = 0

    def swap_same_bytes_then_replace(source: Path, destination: Path, backup: Path):
        nonlocal calls
        calls += 1
        if calls == 1:
            os.replace(external, destination)
        original_replace(source, destination, backup)

    monkeypatch.setattr(publisher_module, "replace_existing", swap_same_bytes_then_replace, raising=False)

    with pytest.raises(PublishBaselineError) as exc_info:
        publisher.publish(
            "same-bytes-existing-race",
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert exc_info.value.code == "PUBLISH_BASE_CHANGED"
    assert target.read_bytes() == b"baseline"
    assert _identity(target) == external_identity


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
            attempt=1,
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
            attempt=1,
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert target.read_bytes() == b"external"
    assert _identity(target) == external_identity


def test_partial_replace_with_staged_result_at_target_restores_original_identity(tmp_path: Path, monkeypatch):
    target = tmp_path / "partial-result-existing.dwg"
    staged = tmp_path / "staged-partial-result-existing.dwg"
    target.write_bytes(b"same-content")
    staged.write_bytes(b"same-content")
    baseline_identity = _identity(target)
    published_identity: list[int] | None = None
    publisher = RecoverablePublisher()
    original_replace = publisher_module.replace_existing
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

    monkeypatch.setattr(publisher_module, "replace_existing", fail_after_installing_staged, raising=False)

    with pytest.raises(PublishRolledBackError) as exc_info:
        publisher.publish(
            "partial-staged-result",
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: capture_file_baseline(target)},
        )

    assert published_identity is not None
    assert published_identity != baseline_identity
    assert _identity(target) == baseline_identity
    assert isinstance(exc_info.value.__cause__, OSError)
    assert "1176" in str(exc_info.value.__cause__)


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
    original_replace = publisher_module.replace_existing
    calls = 0

    def fail_first_rollback_replace(source: Path, destination: Path, backup: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ctypes.WinError(32)
        original_replace(source, destination, backup)

    def fail_after_commit(_entry: dict):
        raise OSError("注入结果复核故障")

    monkeypatch.setattr(publisher_module, "replace_existing", fail_first_rollback_replace)
    monkeypatch.setattr(publisher, "_capture_result", fail_after_commit)

    with pytest.raises((PublishRolledBackError, PublishRecoveryError)):
        publisher.publish(
            operation,
            tmp_path,
            {target: staged},
            attempt=1,
            expected_baselines={target: capture_file_baseline(target)},
        )

    journal = json.loads(
        (tmp_path / ".dst-manager/jobs" / operation / "attempt-001" / "publish-journal.json").read_text(encoding="utf-8"),
    )
    replace_backup = Path(journal["files"][0]["replace_backup"])
    if journal["status"] == "ROLLED_BACK":
        assert _identity(target) == baseline_identity
        assert not replace_backup.exists()
    else:
        assert journal["status"] == "ROLLBACK_FAILED"
        assert replace_backup.is_file()
        assert _identity(replace_backup) == baseline_identity


def test_retry_publishes_into_new_attempt_directory(tmp_path: Path):
    """重试写入 attempt-002 新目录并正常提交，不依赖上一次尝试的任何产物。"""
    job_id = "retry-jobs"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    publisher = RecoverablePublisher()

    def replace(source: Path, target_path: Path):
        raise OSError("注入首次发布故障")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "before"

    revision_dir = publisher.publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert revision_dir == tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-002"
    assert target.read_text() == "after"
    second_journal = json.loads(
        (tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-002" / "publish-journal.json").read_text(encoding="utf-8"),
    )
    assert second_journal["status"] == "COMMITTED"
    assert second_journal["operation_id"] == job_id
    assert second_journal["attempt"] == 2


def test_second_attempt_rollback_still_restores_formal_files(tmp_path: Path):
    """连续两次发布均失败时，attempt-002 仍独立恢复到本次发布前内容。"""
    job_id = "second-rollback"
    target = tmp_path / "target.txt"
    staged = tmp_path / "staged.txt"
    target.write_text("v0")
    staged.write_text("v1")

    def replace(source: Path, target_path: Path):
        raise OSError("注入发布故障")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "v0"
    staged.write_text("v2")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert target.read_text() == "v0"
    for attempt in (1, 2):
        journal_path = tmp_path / ".dst-manager" / "jobs" / job_id / f"attempt-{attempt:03d}" / "publish-journal.json"
        assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"
