"""发布事务日志读写（自 publisher.py 拆分；原子写入与错误包装逐字保留）。"""

import json
import shutil
from pathlib import Path

from dst_manager.infrastructure.filesystem import atomic
from dst_manager.infrastructure.filesystem.publish_errors import (
    PublishJournalWriteError,
    PublishRecoveryError,
)


def write_journal(path: Path, journal: dict) -> None:
    try:
        atomic.atomic_write_text(path, json.dumps(journal, ensure_ascii=False, indent=2))
    except OSError as error:
        hint = (
            f"（已按瞬时占用退避重试 {atomic.DEFAULT_ATTEMPTS} 次仍被拒绝，通常是安全软件或同步工具持有该文件）"
            if atomic.is_transient_contention(error)
            else ""
        )
        raise PublishJournalWriteError(f"发布日志写入失败{hint}：{error}") from error


def write_journal_best_effort(path: Path, journal: dict) -> None:
    """回滚前的日志记录：日志不可写时不得阻止正式文件的回填。

    日志只是诊断记录，磁盘上正式文件的一致性优先级更高。这里只吞掉写入类故障，
    其他编程错误继续向上抛出。
    """
    try:
        write_journal(path, journal)
    except OSError:
        pass


def archive_journal(revision_dir: Path, journal_path: Path, journal: dict) -> None:
    manifest_path = revision_dir / "manifest.json"
    # manifest 是数据库 finalize 的可见性闸门，因此必须最后原子发布；任何前置归档
    # 失败都只能留下不可枚举的临时文件或 journal 副本。两处写入都对外部文件过滤
    # 驱动的瞬时占用做有界重试：归档失败会在下次启动被升级为发布恢复故障。
    atomic.retry_transient_contention(
        lambda: shutil.copy2(journal_path, revision_dir / "publish-journal.json"),
    )
    atomic.atomic_write_text(manifest_path, json.dumps(journal, ensure_ascii=False, indent=2))


def immutable_transaction_projection(workspace_root: Path, journal: dict) -> dict:
    operation_id = journal.get("operation_id")
    files = journal.get("files")
    if (
        not isinstance(operation_id, str)
        or journal.get("status") != "COMMITTED"
        or not isinstance(files, list)
        or any(not isinstance(entry, dict) for entry in files)
    ):
        raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
    root = workspace_root.resolve()
    for entry in files:
        target_raw = entry.get("target")
        if not isinstance(target_raw, str):
            raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
        target = Path(target_raw).resolve()
        if root != target and root not in target.parents:
            raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
    return {
        "identity_version": journal.get("identity_version"),
        "operation_id": operation_id,
        "root": str(root).casefold(),
        "status": journal["status"],
        # COMMITTED 后 files 的完整审计向量均不可变，包括目标、staged/backup、
        # before/result hash 与 identity、Win32 source 及 API 状态。
        "files": files,
    }
