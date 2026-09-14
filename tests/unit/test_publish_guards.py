import ctypes
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dst_manager.infrastructure.filesystem import locking as locking_module
from dst_manager.infrastructure.filesystem import publisher as publisher_module
from dst_manager.infrastructure.filesystem.locking import (
    FileLockError,
    WindowsResultGuards,
    WindowsWriteLocks,
)
from dst_manager.infrastructure.filesystem.publisher import (
    PublishOperationConflictError,
    PublishRecoveryError,
    RecoverablePublisher,
    capture_file_baseline,
)


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
            attempt=1,
            expected_baselines={target: expected},
        )

    assert target.read_bytes() == b"new"


@pytest.mark.skipif(os.name != "nt", reason="验证 Windows ReplaceFile/rename 共享删除竞态")
def test_result_guard_blocks_replace_between_final_verification_and_committed_journal(tmp_path: Path, monkeypatch):
    target = tmp_path / "guarded.dst"
    staged = tmp_path / "staged.dst"
    replacement = tmp_path / "external.dst"
    target.write_bytes(b"before")
    staged.write_bytes(b"published")
    publisher = RecoverablePublisher()
    original_write = publisher_module.write_journal
    replacement_blocked = False
    injected = False

    def inject_replace_before_committed(path: Path, journal: dict):
        nonlocal injected, replacement_blocked
        if journal.get("status") == "COMMITTED" and not injected:
            injected = True
            replacement.write_bytes(b"external")
            try:
                os.replace(replacement, target)
            except PermissionError:
                replacement_blocked = True
        original_write(path, journal)

    monkeypatch.setattr(publisher_module, "write_journal", inject_replace_before_committed)

    publisher.publish("guarded-operation", tmp_path, {target: staged}, attempt=1)

    assert replacement_blocked is True
    assert target.read_bytes() == b"published"
    journal = json.loads(
        (tmp_path / ".dst-manager/jobs/guarded-operation/attempt-001/publish-journal.json").read_text(encoding="utf-8"),
    )
    assert journal["status"] == "COMMITTED"


@pytest.mark.skipif(os.name != "nt", reason="验证 Windows 删除结果父目录守卫")
def test_result_guard_blocks_recreation_of_deleted_target_during_committed_callback(tmp_path: Path):
    target = tmp_path / "deleted.dst"
    target.write_bytes(b"before")
    publisher = RecoverablePublisher()
    recreation_blocked = False

    def recreate_deleted(_revision_dir: Path, _journal: dict):
        nonlocal recreation_blocked
        try:
            target.write_bytes(b"external-recreated")
        except PermissionError:
            recreation_blocked = True

    publisher.publish(
        "delete-guarded-operation",
        tmp_path,
        {target: None},
        attempt=1,
        on_committed=recreate_deleted,
    )

    assert recreation_blocked is True
    assert not target.exists()


@pytest.mark.skipif(os.name != "nt", reason="验证 Windows 新建结果的替换竞态")
def test_result_guard_blocks_replacement_of_new_target_during_committed_callback(tmp_path: Path):
    target = tmp_path / "created.dst"
    staged = tmp_path / "staged-created.dst"
    replacement = tmp_path / "external-created.dst"
    staged.write_bytes(b"published")
    replacement_blocked = False

    def replace_created(_revision_dir: Path, _journal: dict):
        nonlocal replacement_blocked
        replacement.write_bytes(b"external")
        try:
            os.replace(replacement, target)
        except PermissionError:
            replacement_blocked = True

    RecoverablePublisher().publish(
        "create-guarded-operation",
        tmp_path,
        {target: staged},
        attempt=1,
        on_committed=replace_created,
    )

    assert replacement_blocked is True
    assert target.read_bytes() == b"published"


@pytest.mark.skipif(os.name != "nt", reason="验证 Windows delete-pending 关闭后的名称复用")
def test_windows_result_guard_does_not_unlink_external_file_created_after_close(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "deleted-then-recreated.dst"
    target.write_bytes(b"before")
    target.unlink()
    kernel32 = ctypes.windll.kernel32
    original_close = kernel32.CloseHandle
    external_created = False

    def close_then_recreate(handle):
        nonlocal external_created
        result = original_close(handle)
        if not external_created:
            target.write_bytes(b"external-after-close")
            external_created = True
        return result

    monkeypatch.setattr(kernel32, "CloseHandle", close_then_recreate)

    with WindowsResultGuards([], [target]):
        pass

    assert target.read_bytes() == b"external-after-close"


def test_non_windows_result_guard_fails_closed_without_touching_paths(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "fallback-unsupported.dst"
    replacement = tmp_path / "fallback-untouched.dst"
    replacement.write_bytes(b"external")
    monkeypatch.setattr(
        locking_module,
        "os",
        SimpleNamespace(name="posix", fstat=os.fstat),
    )

    with (
        pytest.raises(FileLockError, match="PUBLISH_RESULT_GUARD_UNSUPPORTED"),
        WindowsResultGuards([], [target]),
    ):
        pass

    assert not target.exists()
    assert replacement.read_bytes() == b"external"


def test_non_windows_result_guard_never_reaches_replace_tombstone_probe(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "fallback-tombstone-probe.dst"
    replacement = tmp_path / "fallback-tombstone-external.dst"
    replacement.write_bytes(b"external-tombstone")
    monkeypatch.setattr(
        locking_module,
        "os",
        SimpleNamespace(name="posix", fstat=os.fstat),
    )
    guard = WindowsResultGuards([], [target])
    original_stat = Path.stat

    def stat_then_replace(path: Path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if "guard-tombstone" in path.name:
            replacement.replace(path)
        return result

    monkeypatch.setattr(Path, "stat", stat_then_replace)

    with pytest.raises(FileLockError, match="PUBLISH_RESULT_GUARD_UNSUPPORTED"), guard:
        pass

    assert not target.exists()
    assert replacement.read_bytes() == b"external-tombstone"


def test_same_attempt_revision_dir_conflict_is_refused(tmp_path: Path):
    """同号 attempt 的修订目录已存在（重复提交防护）时拒绝且不触碰任何文件。"""
    job_id = "conflict-job"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    revision_dir = tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-001"
    revision_dir.mkdir(parents=True)
    (revision_dir / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PublishOperationConflictError):
        RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "before"
    assert not (tmp_path / ".dst-manager" / "jobs" / job_id).exists()


def test_bare_attempt_revision_dir_conflict_is_refused(tmp_path: Path):
    """revision_dir 已存在但尚无 manifest 与 journal（如 before 快照复制期间崩溃）同样拒绝发布。"""
    job_id = "bare-revision-dir-job"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    revision_dir = tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-001"
    (revision_dir / "before").mkdir(parents=True)
    with pytest.raises(PublishOperationConflictError) as exc_info:
        RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert exc_info.value.code == "PUBLISH_OPERATION_CONFLICT"
    assert target.read_text() == "before"
    assert not (tmp_path / ".dst-manager" / "jobs" / job_id).exists()
    assert not (revision_dir / "manifest.json").exists()
    assert not (revision_dir / "publish-journal.json").exists()


def test_same_attempt_job_namespace_conflict_is_refused(tmp_path: Path):
    """仅 jobs attempt 目录存在也属于未恢复现场，禁止覆盖 journal。"""
    job_id = "job-journal-conflict"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    journal_path = tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-001" / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    original = b'{"operation_id":"job-journal-conflict","attempt":1,"status":"PUBLISHING","files":[]}'
    journal_path.write_bytes(original)
    with pytest.raises(PublishOperationConflictError):
        RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "before"
    assert journal_path.read_bytes() == original
    assert not (tmp_path / ".dst-manager" / "revisions" / job_id).exists()


@pytest.mark.parametrize("attempt", [0, -1, True, 1.5, "1"])
def test_invalid_attempt_is_rejected_without_creating_manager_files(tmp_path: Path, attempt):
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    with pytest.raises((TypeError, ValueError), match="PUBLISH_ATTEMPT_INVALID"):
        RecoverablePublisher().publish(job_id="invalid-attempt", workspace_root=tmp_path, staged={target: staged}, attempt=attempt)
    assert target.read_text() == "before"
    assert not (tmp_path / ".dst-manager").exists()


@pytest.mark.parametrize(
    ("committed_dir", "retry_attempt"),
    [("attempt-001", 2), (".", 1)],
    ids=["nested-attempt", "legacy-flat"],
)
def test_reusing_committed_operation_is_refused_without_touching_files(
    tmp_path: Path,
    committed_dir: str,
    retry_attempt: int,
):
    """已提交清单存在时禁止再次发布且必须零改动：嵌套布局经真实提交，旧平铺布局由 fixture 构造。"""
    job_id = "job-committed-once"
    target, staged, later = tmp_path / "target.dwg", tmp_path / "staged.dwg", tmp_path / "later.dwg"
    target.write_bytes(b"before")
    staged.write_bytes(b"after")
    later.write_bytes(b"later")
    publisher = RecoverablePublisher()
    revision_dir = tmp_path / ".dst-manager" / "revisions" / job_id / committed_dir
    journal_path = tmp_path / ".dst-manager" / "jobs" / job_id / committed_dir / "publish-journal.json"
    if committed_dir == ".":
        # 旧平铺布局无法由新写入侧产出，只能手工构造提交清单；内容损坏也必须被尊重
        revision_dir.mkdir(parents=True)
        (revision_dir / "manifest.json").write_text("{}", encoding="utf-8")
    else:
        publisher.publish(job_id, tmp_path, {target: staged}, attempt=1)
        assert target.read_bytes() == b"after"
    manifest_bytes = (revision_dir / "manifest.json").read_bytes()
    journal_bytes = journal_path.read_bytes() if journal_path.exists() else None

    with pytest.raises(PublishOperationConflictError) as exc_info:
        publisher.publish(job_id, tmp_path, {target: later}, attempt=retry_attempt)

    assert exc_info.value.code == "PUBLISH_OPERATION_CONFLICT"
    assert isinstance(exc_info.value, PublishRecoveryError)
    assert "提交清单" in str(exc_info.value)
    assert target.read_bytes() == (b"after" if journal_bytes is not None else b"before")
    assert (revision_dir / "manifest.json").read_bytes() == manifest_bytes
    if journal_bytes is not None:
        assert journal_path.read_bytes() == journal_bytes
    assert not (tmp_path / ".dst-manager" / "revisions" / job_id / f"attempt-{retry_attempt:03d}").exists()
    assert not (tmp_path / ".dst-manager" / "jobs" / job_id / f"attempt-{retry_attempt:03d}").exists()
