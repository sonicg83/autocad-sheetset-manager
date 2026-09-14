"""启动恢复与已提交清单枚举（自 publisher.py 拆分；锁获取、回滚与校验逻辑逐字保留）。

以 publisher 为首参的鸭子类型调用 publisher 实例方法（``publisher._rollback`` 等），
本模块不得反向 import publisher，保持依赖单向 publisher → publish_recovery。
"""

import json
import os
import shutil
from pathlib import Path

from dst_manager.infrastructure.filesystem.locking import WorkspaceTransactionLock
from dst_manager.infrastructure.filesystem.publish_errors import PublishRecoveryError
from dst_manager.infrastructure.filesystem.publish_journal import (
    archive_journal,
    immutable_transaction_projection,
    write_journal,
)
from dst_manager.infrastructure.filesystem.publish_primitives import file_sha256


def _parse_attempt_dir_name(name: str) -> int:
    raw_attempt = name.removeprefix("attempt-")
    try:
        attempt = int(raw_attempt)
    except ValueError as error:
        raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH") from error
    if attempt < 1 or name != f"attempt-{attempt:03d}":
        raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
    return attempt


def _iter_journal_records(
    jobs: Path,
    workspace_root: Path,
) -> list[tuple[Path, str, int | None, Path]]:
    """按新旧两种布局枚举发布日志并严格校验 attempt 目录名。返回
    ``(journal_path, job_id, attempt, revision_dir)``。

    嵌套布局 ``jobs/<job_id>/attempt-NNN/`` 与旧平铺布局 ``jobs/<job_id>/`` 并存：
    升级后旧工作区仍必须能被启动恢复与清单枚举读取，因此两套 glob 都要扫。
    """
    records: list[tuple[Path, str, int | None, Path]] = []
    revisions = workspace_root / ".dst-manager" / "revisions"
    for path in jobs.glob("*/attempt-*/publish-journal.json"):
        job_id = path.parent.parent.name
        attempt_dir_name = path.parent.name
        attempt = _parse_attempt_dir_name(attempt_dir_name)
        records.append((path, job_id, attempt, revisions / job_id / attempt_dir_name))
    for path in jobs.glob("*/publish-journal.json"):
        records.append((path, path.parent.name, None, revisions / path.parent.name))
    return records


def _rollback_legacy_attempted(publisher, journal_path: Path, journal: dict) -> None:
    journal["status"] = "ROLLING_BACK"
    write_journal(journal_path, journal)
    for entry in reversed(journal["files"]):
        if entry.get("conflict_preserved") or not (entry.get("replaced") or entry.get("attempted")):
            continue
        target = Path(entry["target"])
        before_hash = entry.get("before_hash")
        if before_hash is None:
            if target.exists() and file_sha256(target) == entry.get("staged_hash"):
                target.unlink()
            continue
        if target.exists() and file_sha256(target) == before_hash:
            continue
        backup = _legacy_rollback_source(entry, before_hash)
        restore_temp = target.with_name(f".{target.name}.{journal['operation_id']}.restore")
        shutil.copy2(backup, restore_temp)
        os.replace(restore_temp, target)
    journal["status"] = "ROLLED_BACK"
    write_journal(journal_path, journal)


def _legacy_rollback_source(entry: dict, before_hash: str) -> Path:
    for raw_path in (entry.get("replace_backup"), entry.get("backup")):
        if raw_path and (path := Path(raw_path)).exists() and file_sha256(path) == before_hash:
            return path
    raise PublishRecoveryError(f"PUBLISH_BACKUP_CORRUPTED: {entry['target']}")


def recover(publisher, workspace_root: Path) -> list[str]:
    workspace_root = workspace_root.resolve()
    jobs = workspace_root / ".dst-manager" / "jobs"
    if not jobs.exists():
        return []
    lock_path = workspace_root / ".dst-manager" / "publish-transaction.lock"
    with WorkspaceTransactionLock(lock_path):
        return _recover_locked(publisher, workspace_root)


def _recover_locked(publisher, workspace_root: Path) -> list[str]:
    recovered: list[str] = []
    jobs = workspace_root / ".dst-manager" / "jobs"
    if not jobs.exists():
        return recovered
    for path, job_id, attempt, revision_dir in _iter_journal_records(jobs, workspace_root):
        journal = json.loads(path.read_text(encoding="utf-8"))
        status = journal["status"]
        if status in {"ROLLED_BACK", "ABORTED_BASELINE_CHANGED"}:
            continue
        # 嵌套布局额外校验 attempt 目录名与 journal 字段一致；该校验必须
        # 覆盖所有未终结状态（含 PREPARED/PUBLISHING/ROLLING_BACK），
        # 因此放在状态分发之前。
        if attempt is not None:
            journal_attempt = journal.get("attempt")
            if type(journal_attempt) is not int or journal_attempt != attempt:
                raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
        if status == "COMMITTED":
            if "identity_version" in journal and journal["identity_version"] != 1:
                journal["cleanup_error_code"] = "PUBLISH_IDENTITY_VERSION_UNSUPPORTED"
                journal["cleanup_error_detail"] = repr(journal["identity_version"])
                write_journal(path, journal)
                raise PublishRecoveryError(
                    f"PUBLISH_IDENTITY_VERSION_UNSUPPORTED: {journal['identity_version']!r}",
                )
            if journal.get("operation_id") != job_id:
                raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
            manifest_path = revision_dir / "manifest.json"
            try:
                archived_journal = json.loads(manifest_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                archived_journal = None
            except (OSError, json.JSONDecodeError) as manifest_error:
                raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH") from manifest_error
            if archived_journal is not None and immutable_transaction_projection(
                workspace_root,
                archived_journal,
            ) != immutable_transaction_projection(workspace_root, journal):
                raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
            try:
                if journal.get("cleanup_status") == "PENDING":
                    publisher._finish_committed_cleanup(path, journal, revision_dir)
                elif archived_journal is None:
                    archive_journal(revision_dir, path, journal)
                else:
                    synchronized_manifest = dict(archived_journal)
                    for field in publisher.CLEANUP_FIELDS:
                        synchronized_manifest.pop(field, None)
                        if field in journal:
                            synchronized_manifest[field] = journal[field]
                    if synchronized_manifest != archived_journal:
                        archive_journal(revision_dir, path, synchronized_manifest)
            except Exception as recovery_error:
                journal["cleanup_error_code"] = "PUBLISH_ARCHIVE_FAILED"
                journal["cleanup_error_detail"] = str(recovery_error)
                try:
                    write_journal(path, journal)
                except Exception:  # noqa: BLE001, S110 - 保留原始归档恢复故障
                    pass
                raise PublishRecoveryError(str(recovery_error)) from recovery_error
            continue
        if "identity_version" in journal and journal["identity_version"] != 1:
            journal["status"] = "ROLLBACK_FAILED"
            journal["recovery_error_code"] = "PUBLISH_IDENTITY_VERSION_UNSUPPORTED"
            write_journal(path, journal)
            raise PublishRecoveryError(
                f"PUBLISH_IDENTITY_VERSION_UNSUPPORTED: {journal['identity_version']!r}",
            )
        if journal.get("identity_version") == 1:
            try:
                publisher._rollback(path, journal, journal["files"])
            except Exception as recovery_error:
                journal["status"] = "ROLLBACK_FAILED"
                write_journal(path, journal)
                raise PublishRecoveryError(str(recovery_error)) from recovery_error
            recovered.append(journal["operation_id"])
            continue
        if any("attempted" in entry for entry in journal["files"]):
            try:
                _rollback_legacy_attempted(publisher, path, journal)
            except Exception as recovery_error:
                journal["status"] = "ROLLBACK_FAILED"
                write_journal(path, journal)
                raise PublishRecoveryError(str(recovery_error)) from recovery_error
            recovered.append(journal["operation_id"])
            continue
        for entry in reversed(journal["files"]):
            if entry.get("replaced"):
                target = Path(entry["target"])
                if entry.get("backup") is None:
                    target.unlink(missing_ok=True)
                elif Path(entry["backup"]).exists():
                    backup = Path(entry["backup"])
                    restore_temp = target.with_name(f".{target.name}.{journal['operation_id']}.restore")
                    shutil.copy2(backup, restore_temp)
                    os.replace(restore_temp, target)
        journal["status"] = "ROLLED_BACK"
        write_journal(path, journal)
        recovered.append(journal["operation_id"])
    return recovered


def list_committed_operations(publisher, workspace_root: Path) -> list[dict]:
    """只读枚举仍可用于数据库闭环的 COMMITTED 发布清单。"""
    workspace_root = workspace_root.resolve()
    revisions = workspace_root / ".dst-manager" / "revisions"
    if not revisions.exists():
        return []
    lock_path = workspace_root / ".dst-manager" / "publish-transaction.lock"
    with WorkspaceTransactionLock(lock_path):
        return _list_committed_operations_locked(workspace_root)


def _list_committed_operations_locked(workspace_root: Path) -> list[dict]:
    revisions = workspace_root / ".dst-manager" / "revisions"
    # 新旧两种布局并存：嵌套 ``revisions/<job_id>/attempt-NNN/`` 与旧平铺
    # ``revisions/<job_id>/``。候选 manifest 按路径携带预期身份，身份不一致
    # 的清单不得用于数据库闭环。
    candidates: list[tuple[Path, str, int | None]] = []
    for path in revisions.glob("*/attempt-*/manifest.json"):
        candidates.append((path, path.parent.parent.name, _parse_attempt_dir_name(path.parent.name)))
    candidates.extend((path, path.parent.name, None) for path in revisions.glob("*/manifest.json"))
    committed: dict[str, dict] = {}
    for path, expected_job_id, expected_attempt in candidates:
        try:
            journal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        operation_id = journal.get("operation_id")
        if expected_attempt is None:
            identity_matches = True
        else:
            journal_attempt = journal.get("attempt")
            identity_matches = type(journal_attempt) is int and journal_attempt == expected_attempt
        if (
            journal.get("status") != "COMMITTED"
            or not isinstance(operation_id, str)
            or operation_id != expected_job_id
            or not identity_matches
            or not isinstance(journal.get("files"), list)
        ):
            continue
        committed.setdefault(operation_id, journal)
    return [committed[key] for key in sorted(committed)]


def read_committed_operation(publisher, workspace_root: Path, operation_id: str) -> dict | None:
    return next(
        (
            journal
            for journal in list_committed_operations(publisher, workspace_root)
            if journal["operation_id"] == operation_id
        ),
        None,
    )
