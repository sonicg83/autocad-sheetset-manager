import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem import atomic as atomic_module
from dst_manager.infrastructure.filesystem import publisher as publisher_module
from dst_manager.infrastructure.filesystem.publisher import (
    PublishJournalWriteError,
    PublishRecoveryError,
    RecoverablePublisher,
)


def _deny_journal_replacement(monkeypatch, *, denied_budget: int):
    """模拟安全软件/EDR：发布日志的原子替换返回 WinError 5，预算用完后恢复正常。"""
    original_replace = publisher_module.os.replace
    denied = 0

    def replace(source, destination):
        nonlocal denied
        if Path(destination).name == "publish-journal.json" and denied < denied_budget:
            denied += 1
            error = PermissionError(13, "拒绝访问")
            error.winerror = 5  # type: ignore[attr-defined]
            raise error
        return original_replace(source, destination)

    monkeypatch.setattr(publisher_module.os, "replace", replace)
    return lambda: denied


def test_concurrent_journal_writes_use_independent_temporary_files(tmp_path: Path, monkeypatch):
    journal_path = tmp_path / "publish-journal.json"
    barrier = threading.Barrier(2)
    replace_lock = threading.Lock()
    original_replace = publisher_module.os.replace
    replace_sources: list[Path] = []

    def synchronize_before_replace(source, destination):
        replace_sources.append(Path(source))
        barrier.wait(timeout=5)
        with replace_lock:
            return original_replace(source, destination)

    monkeypatch.setattr(publisher_module.os, "replace", synchronize_before_replace)
    journals = [
        {"operation_id": "first", "status": "PUBLISHING", "files": []},
        {"operation_id": "second", "status": "PUBLISHING", "files": []},
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(publisher_module.write_journal, journal_path, item) for item in journals]
        for future in futures:
            future.result()

    written = json.loads(journal_path.read_text(encoding="utf-8"))
    assert written in journals
    assert len(set(replace_sources)) == 2
    assert list(tmp_path.glob("*.tmp")) == []


def test_transient_journal_denial_is_retried_without_rolling_back(tmp_path: Path, monkeypatch):
    """2026-09-14 现场回归：日志被瞬时拒绝不得让整批发布回滚。"""
    targets = {}
    for index in range(3):
        target = tmp_path / f"target-{index}.txt"
        source = tmp_path / f"staged-{index}.txt"
        target.write_text(f"before-{index}")
        source.write_text(f"after-{index}")
        targets[target] = source
    denial_count = _deny_journal_replacement(monkeypatch, denied_budget=2)

    RecoverablePublisher().publish("transient-journal-denial", tmp_path, targets, attempt=1)

    assert denial_count() == 2
    assert [path.read_text() for path in targets] == ["after-0", "after-1", "after-2"]
    job_dir = tmp_path / ".dst-manager/jobs/transient-journal-denial/attempt-001"
    journal = json.loads((job_dir / "publish-journal.json").read_text(encoding="utf-8"))
    assert journal["status"] == "COMMITTED"
    assert list(job_dir.glob("*.tmp")) == []


def test_persistent_journal_denial_fails_before_touching_files(tmp_path: Path, monkeypatch):
    """重试预算耗尽时必须给出可读原因，且不得留下半发布状态或临时文件。"""
    target, staged = tmp_path / "target.txt", tmp_path / "staged.txt"
    target.write_text("before")
    staged.write_text("after")
    denial_count = _deny_journal_replacement(monkeypatch, denied_budget=1000)

    with pytest.raises(PublishJournalWriteError) as exc_info:
        RecoverablePublisher().publish("journal-denied", tmp_path, {target: staged}, attempt=1)

    assert "发布日志写入失败" in str(exc_info.value)
    assert "拒绝访问" in str(exc_info.value)
    assert PublishJournalWriteError.code == "PUBLISH_JOURNAL_WRITE_FAILED"
    # 首条日志（PREPARED）就写不进去，说明尚未触碰任何正式文件
    assert denial_count() == atomic_module.DEFAULT_ATTEMPTS
    assert target.read_text() == "before"
    job_dir = tmp_path / ".dst-manager/jobs/journal-denied/attempt-001"
    assert not (job_dir / "publish-journal.json").exists()
    assert list(job_dir.glob("*.tmp")) == []


def test_journal_denial_after_first_replacement_still_restores_files(tmp_path: Path, monkeypatch):
    """日志中途不可写时，已替换的正式文件仍必须被回填（磁盘一致性优先于日志记录）。"""
    replaced, staged, untouched, untouched_staged = (
        tmp_path / "replaced.txt",
        tmp_path / "staged-replaced.txt",
        tmp_path / "untouched.txt",
        tmp_path / "staged-untouched.txt",
    )
    replaced.write_text("before-replaced")
    untouched.write_text("before-untouched")
    staged.write_text("after-replaced")
    untouched_staged.write_text("after-untouched")
    original_replace = publisher_module.os.replace
    journal_writes = 0

    def replace(source, destination):
        nonlocal journal_writes
        if Path(destination).name == "publish-journal.json":
            journal_writes += 1
            # 前三条（PREPARED/PUBLISHING/首项 STARTED）成功，之后持续被拒绝。
            if journal_writes > 3:
                error = PermissionError(13, "拒绝访问")
                error.winerror = 5  # type: ignore[attr-defined]
                raise error
        return original_replace(source, destination)

    monkeypatch.setattr(publisher_module.os, "replace", replace)

    with pytest.raises(PublishRecoveryError):
        RecoverablePublisher().publish(
            "journal-denied-midway",
            tmp_path,
            {replaced: staged, untouched: untouched_staged},
            attempt=1,
        )

    assert replaced.read_text() == "before-replaced"
    assert untouched.read_text() == "before-untouched"
    job_dir = tmp_path / ".dst-manager/jobs/journal-denied-midway/attempt-001"
    # 日志保留最后一次成功写入的状态，供启动恢复与人工核对
    journal = json.loads((job_dir / "publish-journal.json").read_text(encoding="utf-8"))
    assert journal["status"] == "PUBLISHING"
    assert journal["files"][0]["api_state"] == "STARTED"
    assert list(job_dir.glob("*.tmp")) == []
