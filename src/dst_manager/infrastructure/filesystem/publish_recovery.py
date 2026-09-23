"""启动恢复与已提交清单枚举（自 publisher.py 拆分；锁获取、回滚与校验逻辑逐字保留）。

以 publisher 为首参的鸭子类型调用 publisher 实例方法（``publisher._rollback`` 等），
本模块不得反向 import publisher，保持依赖单向 publisher → publish_recovery。
PLAN-DM-036 Task 6 的创建发布恢复同属本模块：创建事务没有工作区 ``.dst-manager/``
命名空间，日志落在 Manager 应用数据目录的隔离 attempt 里，因此按
``creation-jobs/<job_id>/attempt-NNN/publish-journal.json`` 独立枚举，回滚同样走
鸭子类型调用 ``publisher._rollback_creation``，不复制回滚实现。
"""

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dst_manager.infrastructure.filesystem.locking import (
    WorkspaceTransactionBusyError,
    WorkspaceTransactionLock,
)
from dst_manager.infrastructure.filesystem.publish_errors import PublishRecoveryError
from dst_manager.infrastructure.filesystem.publish_journal import (
    archive_journal,
    immutable_transaction_projection,
    write_journal,
    write_journal_best_effort,
)
from dst_manager.infrastructure.filesystem.publish_primitives import file_sha256

#: 创建发布日志文件名（与 project_publisher 写入侧同一字面量；本模块只读枚举）。
CREATION_PUBLISH_JOURNAL_NAME = "publish-journal.json"
#: 创建发布日志中不表示「仍需处理」的终态。
CREATION_PUBLISH_SETTLED_STATUSES = frozenset({"ROLLED_BACK", "ABORTED_BASELINE_CHANGED"})


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


@dataclass(frozen=True, slots=True)
class CreationPublishOutcome:
    """一次创建发布启动恢复的结论：任务身份、现场结论与（提交时的）成果投影。"""

    job_id: str
    attempt: int
    conclusion: str
    detail: str = ""
    published: dict[str, Any] | None = None


def creation_published_payload(journal: dict[str, Any]) -> dict[str, Any]:
    """已提交创建发布的成果投影。

    任务闭环（``jobs.payload.published``）与 Task 7 的工作区登记消费同一形状；
    发布路径与启动恢复都从这里取，避免两处各写一份字段集合。
    """
    target = Path(journal["target"]["path"])
    files = []
    for entry in journal["files"]:
        path = Path(entry["target"])
        files.append(
            {
                "name": entry["name"],
                "role": entry["role"],
                "group_id": entry["group_id"],
                "sha256": entry["result_hash"],
                "size": path.stat().st_size if path.is_file() else 0,
            }
        )
    dst_name = next(entry["name"] for entry in journal["files"] if entry["role"] == "dst")
    return {
        "target_dir": str(target),
        "dst_path": str(target / dst_name),
        "dst_name": dst_name,
        "target_state": journal["target"]["state"],
        "attempt": journal["attempt"],
        "journal_path": journal["journal_path"],
        "revision_dir": journal["revision_dir"],
        "files": files,
    }


def _creation_recovery_lock(journal: dict[str, Any]) -> WorkspaceTransactionLock:
    """创建发布的目标级事务锁：与发布路径同一把锁，恢复绝不与进行中的发布并发。

    锁路径不可用（缺失/非字符串）时抛 ``PublishRecoveryError``：两个调用方都只处置
    这一条日志（回滚分支落 ``NEEDS_REVIEW``，已提交分支跳过），绝不因此终止整批恢复。
    取锁本身的环境故障不在本函数内处置，由调用方按 ``OSError`` 收口：锁被占用是
    ``WorkspaceTransactionBusyError``；锁路径指向已存在目录是无权限打开（``FileLockError``）；
    锁路径父级是普通文件是 ``mkdir`` 的 ``FileExistsError``（普通 ``OSError``，不是
    ``FileLockError``，所以调用方按 ``OSError`` 收口才完整）。构造本身只做
    ``Path.resolve()``，对含 NUL/非法字符/超长/父级回溯的路径均不抛（实测）。
    """
    lock_path = journal.get("lock_path")
    if not isinstance(lock_path, str) or not lock_path:
        raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
    return WorkspaceTransactionLock(Path(lock_path))


def _read_creation_journal(journal_path: Path) -> dict[str, Any] | None:
    """读取创建发布日志；不可读取、非 JSON 或不是 JSON 对象时返回 ``None``。

    日志被截断或手工改写是既有代码明确预期的输入（``_list_committed_operations_locked``
    对不可解析的清单同样只 ``continue``）：返回 ``None`` 表示跳过该日志、现场与日志
    原样保留。一条损坏日志既不阻断服务启动，也不阻断其它任务的恢复。

    ``UnicodeDecodeError`` 必须显式列出：它是 ``ValueError`` 子类，不是
    ``JSONDecodeError`` 子类，而「手工按 ANSI/GBK 保存含中文的日志」或二进制垃圾
    覆写都会让 ``read_text(encoding="utf-8")`` 直接抛出它。``RecursionError`` 同样
    必须显式列出：``json.loads`` 对病态深嵌套 JSON（深度超过解释器递归上限）抛它，
    它是 ``RuntimeError`` 子类，不在上面任何一个类型里。
    """
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    return journal if isinstance(journal, dict) else None


def _committed_creation_payload(journal: dict[str, Any]) -> dict[str, Any] | None:
    """已提交日志的成果投影；结构不可信（缺键/类型错误）时返回 ``None``。

    只有 ``revision_dir`` 与成果投影所需的键（``target.path``/``files`` 及逐条目字段）
    都齐全，才允许按这份日志闭环任务并补齐证据归档。
    """
    if not isinstance(journal.get("revision_dir"), str):
        return None
    try:
        return creation_published_payload(journal)
    except (KeyError, TypeError, StopIteration, OSError):
        return None


def recover_creation_publishes(publisher, creation_jobs_root: Path) -> list[CreationPublishOutcome]:
    """按持久日志幂等处理中断的创建发布（``PREPARED``/``PUBLISHING``/回滚中断）。

    - 已提交（``COMMITTED``）：只补齐证据归档，绝不再次生成或覆盖成果文件；
    - 未提交：调用 ``publisher._rollback_creation`` 按身份回滚，结论为 ``ROLLED_BACK``
      或（出现外部内容/身份不匹配时）``NEEDS_REVIEW``；
    - 每份日志都在**目标级发布事务锁**下处理（与发布路径同一把锁）：锁被占用说明
      同一目标上仍有进行中的发布或恢复，此时不介入现场（回滚分支与已提交分支都
      跳过该条日志）；锁路径不可用（内容被改写成目录/非法路径，或权限不足）在已提交
      分支同样只跳过该条日志，在回滚分支落单条 ``NEEDS_REVIEW``；
    - 日志身份与路径不一致（作业 ID / attempt 被改写）属于不可信现场，直接以
      ``PUBLISH_MANIFEST_IMMUTABLE_MISMATCH`` 终止恢复，不做任何猜测性清理；
    - **损坏日志**（截断/非 JSON/不是 JSON 对象/非法 UTF-8 字节/病态深嵌套 JSON/
      ``status`` 不是字符串）
      与结构不可信的已提交日志一律跳过，不阻断启动，也不阻断其它任务的恢复；这类
      任务由既有 ``recover_stale_jobs`` 落 ``PUBLISH_JOURNAL_REVIEW_REQUIRED``，
      等待人工核对。
    """
    root = Path(creation_jobs_root)
    if not root.exists():
        return []
    outcomes: list[CreationPublishOutcome] = []
    for journal_path in sorted(root.glob(f"*/attempt-*/{CREATION_PUBLISH_JOURNAL_NAME}")):
        job_id = journal_path.parent.parent.name
        attempt = _parse_attempt_dir_name(journal_path.parent.name)
        journal = _read_creation_journal(journal_path)
        if journal is None:
            continue
        if journal.get("operation_id") != job_id or journal.get("attempt") != attempt:
            raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
        status = journal.get("status")
        if not isinstance(status, str):
            # ``status`` 是 JSON 数组/对象/缺失：不可信日志，跳过（入 ``frozenset`` 或
            # 比对状态字面量都无意义），绝不因此终止整批恢复。
            continue
        if status in CREATION_PUBLISH_SETTLED_STATUSES:
            continue
        if status == "COMMITTED":
            published = _committed_creation_payload(journal)
            if published is None:
                # 已提交日志结构不可信：既不闭环成功，也不清理或覆盖任何成果文件。
                continue
            try:
                with _creation_recovery_lock(journal):
                    publisher._finish_committed_cleanup(
                        journal_path, journal, Path(journal["revision_dir"])
                    )
            except PublishRecoveryError:
                # 锁路径不可用（缺失/非字符串）同样是结构不可信：只跳过这一条，
                # 不按身份不可证明处置，绝不因此隔离同批其它任务。
                continue
            except WorkspaceTransactionBusyError:
                # 同一目标上仍有进程持有发布事务锁（正在发布或正在恢复）：不介入现场，
                # 与回滚分支同一处置，让任务按租约恢复规则处理。
                continue
            except OSError:
                # 取锁或提交后归档的环境故障：锁路径指向已存在目录/父级是普通文件/
                # 无权限（``FileLockError`` 与 ``mkdir`` 的 ``FileExistsError`` 都是
                # ``OSError``），或归档时被占用/磁盘不可写。只跳过这一条日志并保留
                # 现场，绝不终止整批恢复，也绝不据此改动已提交成果。
                continue
            outcomes.append(
                CreationPublishOutcome(job_id, attempt, "COMMITTED", published=published)
            )
            continue
        try:
            with _creation_recovery_lock(journal):
                publisher._rollback_creation(journal_path, journal)
        except WorkspaceTransactionBusyError:
            # 同一目标上仍有进程持有发布事务锁（正在发布或正在恢复）：不介入现场，
            # 让任务按租约恢复规则处理，绝不同时操作同一目标。
            continue
        except Exception as recovery_error:  # noqa: BLE001 - 恢复故障必须显式隔离为人工核对
            journal["status"] = "ROLLBACK_FAILED"
            write_journal_best_effort(journal_path, journal)
            outcomes.append(
                CreationPublishOutcome(job_id, attempt, "NEEDS_REVIEW", str(recovery_error))
            )
            continue
        if journal["status"] == "ROLLED_BACK":
            outcomes.append(CreationPublishOutcome(job_id, attempt, "ROLLED_BACK"))
        else:
            outcomes.append(
                CreationPublishOutcome(
                    job_id, attempt, "NEEDS_REVIEW", journal.get("review_detail", "")
                )
            )
    return outcomes
