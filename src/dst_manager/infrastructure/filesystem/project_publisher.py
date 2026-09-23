"""新图纸集项目的可恢复发布事务（PLAN-DM-036 Task 6）。

与既有 :class:`~dst_manager.infrastructure.filesystem.publisher.RecoverablePublisher`
的差别只有一处语义：本发布器**创建**一个尚不存在（或已存在但为空）的新项目目录，
因此没有 before 快照，也没有工作区 ``.dst-manager/`` 命名空间——发布日志、修订证据
与锁全部落在 Manager 应用数据目录的隔离 attempt 命名空间
（``<data_dir>/creation-jobs/<job_id>/attempt-<NNN>/``）里，目标项目目录只承载最终
成果文件。

关键不变量：

- **只按显式候选清单发布**：清单来自 ``CreationCandidate``（DST + 每组主 DWG），
  绝不扫描 attempt 暂存目录。Task 5 复核发现候选 DST 先写盘后校验，暂存区里可能
  残留校验失败的候选形文件，按目录扫描会把它们误当成果发布；
- 目标在发布前必须是「不存在」或「已存在且为空」，并记录在日志里（含已存在空目录
  的身份）；首次创建目录后只操作本次占有的精确路径，不使用宽泛递归删除；
- 失败只回滚本次已创建且**身份匹配**的文件，随后精确恢复「目录不存在」或「目录
  存在且为空」；空目录不误删、外来内容不误删，残余外部内容一律升级为
  ``NEEDS_REVIEW`` 并保留日志；
- 进程在 ``PREPARED``/``PUBLISHING`` 中断时保留持久日志现场，由
  :func:`dst_manager.infrastructure.filesystem.publish_recovery.recover_creation_publishes`
  幂等处理；重试永远使用新 attempt 目录，旧日志与证据保留。

文件写入、哈希、身份与原子换名复用既有发布原语（``publish_primitives``），日志
读写与归档复用 ``publish_journal``（同一 JSON 形态与原子写入），跨进程串行化复用
``WorkspaceTransactionLock``，不另立第二套实现；对外值类型、稳定错误与故障注入点
在 :mod:`dst_manager.infrastructure.filesystem.project_publish_types`（容量契约）。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dst_manager.infrastructure.filesystem import publish_recovery
from dst_manager.infrastructure.filesystem.locking import WorkspaceTransactionLock
from dst_manager.infrastructure.filesystem.project_publish_types import (
    ProjectPublishError,
    ProjectPublishFaultInjector,
    PublishedFile,
    PublishedProject,
)
from dst_manager.infrastructure.filesystem.publish_journal import (
    archive_journal,
    write_journal,
    write_journal_best_effort,
)
from dst_manager.infrastructure.filesystem.publish_primitives import (
    file_identity,
    file_sha256,
    move_no_replace,
)
from dst_manager.infrastructure.filesystem.publish_recovery import (
    CREATION_PUBLISH_JOURNAL_NAME,
    CreationPublishOutcome,
)

if TYPE_CHECKING:
    from dst_manager.application.creation_candidate import CreationCandidate

__all__ = [
    "CREATION_PUBLISH_JOURNAL_NAME",
    "CREATION_PUBLISH_LOCK_DIR_NAME",
    "CREATION_PUBLISH_REVISION_DIR_NAME",
    "CREATION_PUBLISH_ROLLBACK_DIR_NAME",
    "ProjectPublisher",
]

#: 提交后的修订证据目录（清单归档处）。
CREATION_PUBLISH_REVISION_DIR_NAME = "revision"
#: 回滚隔离目录：本批文件按身份换名到这里再删除，绝不就地按名字删。
CREATION_PUBLISH_ROLLBACK_DIR_NAME = "rollback"
#: 目标级串行化锁目录（Manager 应用数据目录内，不污染新项目目录）。
CREATION_PUBLISH_LOCK_DIR_NAME = "locks"

#: 目标原状态：尚不存在 / 已存在且为空。非空目标在发布前就被拒绝。
_TARGET_MISSING = "missing"
_TARGET_EMPTY = "empty-directory"


class ProjectPublisher:
    """新项目发布器：目标占有、持久日志、逐文件提交与按身份回滚。"""

    def __init__(self, *, fault_injector: ProjectPublishFaultInjector | None = None) -> None:
        self.fault_injector = fault_injector

    def publish_new_project(
        self, candidate: CreationCandidate, target: Path, job_id: str, attempt: int
    ) -> PublishedProject:
        """把候选清单发布到新项目目录；失败按现场结论回滚或升级为 ``NEEDS_REVIEW``。"""
        if type(attempt) is not int or attempt < 1:
            raise ValueError("PUBLISH_ATTEMPT_INVALID")
        target = Path(target)
        attempt_dir = Path(candidate.attempt_dir)
        entries = _candidate_entries(candidate, target, job_id, attempt)
        # 目标级锁：同一目标的发布与启动恢复互斥（锁路径记入日志，恢复侧按日志取锁）。
        lock_path = _target_lock_path(attempt_dir, target)
        with WorkspaceTransactionLock(lock_path, timeout_seconds=30):
            return self._publish_locked(target, job_id, attempt, entries, attempt_dir)

    def recover_creation_publishes(
        self, creation_jobs_root: Path
    ) -> list[CreationPublishOutcome]:
        """启动恢复：按持久日志幂等处理中断的创建发布。"""
        return publish_recovery.recover_creation_publishes(self, creation_jobs_root)

    # ---- 发布主流程 ------------------------------------------------------

    def _publish_locked(
        self,
        target: Path,
        job_id: str,
        attempt: int,
        entries: list[dict[str, Any]],
        attempt_dir: Path,
    ) -> PublishedProject:
        journal_path = attempt_dir / CREATION_PUBLISH_JOURNAL_NAME
        revision_dir = attempt_dir / CREATION_PUBLISH_REVISION_DIR_NAME
        if journal_path.exists() or revision_dir.exists():
            # 同一次尝试的命名空间不可复用：重试必须落在新 attempt 目录上。
            raise ProjectPublishError(
                "CREATION_PUBLISH_CONFLICT",
                f"同一次尝试的发布命名空间已存在，禁止复用：{attempt_dir.name}",
                "NEEDS_REVIEW",
            )
        target_state, target_identity = _require_publishable_target(target)
        lock_path = _target_lock_path(attempt_dir, target)
        journal: dict[str, Any] = {
            "identity_version": 1,
            "kind": "creation",
            "operation_id": job_id,
            "attempt": attempt,
            "status": "PREPARED",
            "journal_path": str(journal_path),
            "lock_path": str(lock_path),
            "attempt_dir": str(attempt_dir),
            "revision_dir": str(revision_dir),
            "rollback_dir": str(attempt_dir / CREATION_PUBLISH_ROLLBACK_DIR_NAME),
            "target": {
                "path": str(target),
                "state": target_state,
                "identity": target_identity,
            },
            "created_directories": [],
            "files": entries,
            "cleanup_status": "PENDING",
        }
        write_journal(journal_path, journal)
        self._inject_stage("PREPARED")
        try:
            journal["created_directories"] = _create_directories(_missing_ancestors(target))
            journal["status"] = "PUBLISHING"
            write_journal(journal_path, journal)
            self._inject_stage("PUBLISHING")
            operation_uid = f"{job_id}~{attempt:03d}"
            for entry in entries:
                _commit_entry(entry, operation_uid, journal_path, journal)
                self._inject_after_commit(Path(entry["target"]))
            journal["status"] = "COMMITTED"
            write_journal(journal_path, journal)
        except Exception as exc:
            code = getattr(exc, "code", "CREATION_PUBLISH_FAILED")
            try:
                self._rollback_creation(journal_path, journal)
            except Exception as rollback_error:  # noqa: BLE001 - 回滚故障必须显式隔离
                journal["status"] = "ROLLBACK_FAILED"
                write_journal_best_effort(journal_path, journal)
                raise ProjectPublishError(
                    "CREATION_PUBLISH_REVIEW_REQUIRED",
                    f"{code}: {exc}（回滚失败：{rollback_error}）",
                    "NEEDS_REVIEW",
                ) from exc
            if journal["status"] == "NEEDS_REVIEW":
                raise ProjectPublishError(
                    "CREATION_PUBLISH_REVIEW_REQUIRED", f"{code}: {exc}", "NEEDS_REVIEW"
                ) from exc
            raise ProjectPublishError(code, str(exc), "ROLLED_BACK") from exc
        except BaseException:
            # 真实进程终止不执行回滚：保留现场，由启动恢复按持久日志处理。
            raise
        try:
            self._finish_committed_cleanup(journal_path, journal, revision_dir)
        except Exception:  # noqa: BLE001, S110 - 提交后归档诊断失败不得触发文件回滚
            pass
        return _published_project(journal, target, journal_path, revision_dir)

    def _finish_committed_cleanup(
        self, journal_path: Path, journal: dict[str, Any], revision_dir: Path
    ) -> bool:
        """COMMITTED 之后归档证据；归档失败只登记诊断，绝不触发文件回滚。"""
        try:
            revision_dir.mkdir(parents=True, exist_ok=True)
            archive_journal(revision_dir, journal_path, journal)
        except Exception as cleanup_error:  # noqa: BLE001 - 提交后清理失败不得改变已提交状态
            journal["cleanup_status"] = "PENDING"
            journal["cleanup_error_code"] = "PUBLISH_ARCHIVE_FAILED"
            journal["cleanup_error_detail"] = str(cleanup_error)
            try:
                write_journal(journal_path, journal)
            except Exception:  # noqa: BLE001, S110 - COMMITTED 主记录已先持久化
                pass
            return False
        journal["cleanup_status"] = "COMPLETE"
        journal.pop("cleanup_error_code", None)
        journal.pop("cleanup_error_detail", None)
        write_journal(journal_path, journal)
        archive_journal(revision_dir, journal_path, journal)
        return True

    # ---- 回滚（发布失败与启动恢复共用同一实现） --------------------------

    def _rollback_creation(self, journal_path: Path, journal: dict[str, Any]) -> None:
        """只回滚本次已创建且身份匹配的文件，再恢复发布前的精确原状态。"""
        journal["status"] = "ROLLING_BACK"
        write_journal_best_effort(journal_path, journal)
        rollback_dir = Path(journal["rollback_dir"])
        for entry in reversed(journal["files"]):
            _rollback_entry(entry, rollback_dir)
        if _residual_entries(Path(journal["target"]["path"])):
            # 目标出现不属于本次清单的内容：停止自动清理、保留日志并标记人工核对。
            journal["status"] = "NEEDS_REVIEW"
            journal["review_detail"] = "目标目录存在不属于本次发布清单的内容，已停止自动清理"
            write_journal(journal_path, journal)
            return
        _remove_created_directories(journal)
        journal["status"] = "ROLLED_BACK"
        write_journal(journal_path, journal)

    # ---- 故障注入 --------------------------------------------------------

    def _inject_stage(self, stage: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector.at_stage(stage)

    def _inject_after_commit(self, target: Path) -> None:
        if self.fault_injector is not None:
            self.fault_injector.after_commit(target)


def _candidate_entries(
    candidate: CreationCandidate, target: Path, job_id: str, attempt: int
) -> list[dict[str, Any]]:
    """把候选展开成显式发布清单；身份、路径形状与暂存哈希都在此门禁。"""
    attempt_dir = Path(candidate.attempt_dir)
    if candidate.job_id != job_id or candidate.attempt != attempt:
        raise ProjectPublishError(
            "CREATION_PUBLISH_INVALID",
            f"候选身份（{candidate.job_id}/{candidate.attempt}）与任务（{job_id}/{attempt}）不一致",
        )
    if attempt_dir.name != f"attempt-{attempt:03d}":
        raise ProjectPublishError(
            "CREATION_PUBLISH_INVALID", f"候选暂存目录名与 attempt 不一致：{attempt_dir.name}"
        )
    items: list[tuple[str, str, Path, str]] = [
        ("dst", "", Path(candidate.dst_path), candidate.dst_name),
    ]
    items.extend(
        ("dwg", drawing.group_id, Path(drawing.staged_path), drawing.file_name)
        for drawing in candidate.dwgs
    )
    entries: list[dict[str, Any]] = []
    names: set[str] = set()
    for role, group_id, staged, name in items:
        _require_plain_name(name)
        if name.casefold() in names:
            raise ProjectPublishError(
                "CREATION_PUBLISH_INVALID", f"候选清单包含重复的目标文件名：{name}"
            )
        names.add(name.casefold())
        if attempt_dir.resolve() not in staged.resolve().parents:
            raise ProjectPublishError(
                "CREATION_PUBLISH_INVALID", f"候选暂存文件不在隔离 attempt 内：{staged}"
            )
        if not staged.is_file():
            raise ProjectPublishError(
                "CREATION_PUBLISH_INVALID", f"候选暂存文件不存在：{staged}"
            )
        entries.append(
            {
                "name": name,
                "role": role,
                "group_id": group_id,
                "staged": str(staged),
                "staged_hash": file_sha256(staged),
                "staged_identity": file_identity(staged),
                "target": str(target / name),
                "attempted": False,
                "publish_temp": None,
                "publish_identity": None,
                "committed": False,
                "result_hash": None,
                "result_identity": None,
            }
        )
    return entries


def _require_plain_name(name: str) -> None:
    """目标文件名必须是单个普通名字：不含分隔符、不是 ``.``/``..``。"""
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ProjectPublishError(
            "CREATION_PUBLISH_INVALID", f"候选目标文件名非法：{name!r}"
        )


def _require_publishable_target(target: Path) -> tuple[str, list[int] | None]:
    """目标只能是尚不存在的新目录或已存在的空目录；已存在空目录记录身份。"""
    if not target.exists():
        return _TARGET_MISSING, None
    if not target.is_dir() or any(target.iterdir()):
        raise ProjectPublishError(
            "CREATION_TARGET_NOT_EMPTY",
            f"目标 {str(target)!r} 不能作为新项目目录（已存在同名文件或目录非空）",
        )
    return _TARGET_EMPTY, file_identity(target)


def _missing_ancestors(target: Path) -> list[Path]:
    """目标路径上尚不存在的目录链（最深优先），供创建与精确回滚登记。"""
    missing: list[Path] = []
    current = target
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    return missing


def _create_directories(missing: list[Path]) -> list[dict[str, Any]]:
    """按浅到深创建缺失目录并记录身份；只创建本次占有的精确路径。"""
    created: list[dict[str, Any]] = []
    for path in reversed(missing):
        path.mkdir()
        created.append({"path": str(path), "identity": file_identity(path)})
    return created


def _remove_created_directories(journal: dict[str, Any]) -> None:
    """按深到浅移除本次创建的目录；``rmdir`` 非空即失败，绝不递归删除。"""
    for item in reversed(journal["created_directories"]):
        path = Path(item["path"])
        if not path.exists():
            continue
        if file_identity(path) != item["identity"]:
            raise ProjectPublishError(
                "CREATION_PUBLISH_REVIEW_REQUIRED", f"待清理目录身份已变化：{path}", "NEEDS_REVIEW"
            )
        try:
            path.rmdir()
        except OSError as exc:
            raise ProjectPublishError(
                "CREATION_PUBLISH_REVIEW_REQUIRED", f"目标目录不空，已保留现场：{path}", "NEEDS_REVIEW"
            ) from exc


def _commit_entry(
    entry: dict[str, Any], operation_uid: str, journal_path: Path, journal: dict[str, Any]
) -> None:
    """提交一个文件：暂存副本 → 原子换名 → 身份复核；日志先于换名落盘。"""
    target = Path(entry["target"])
    staged = Path(entry["staged"])
    temp = target.with_name(f".{target.name}.{operation_uid}.tmp")
    if temp.exists():
        raise ProjectPublishError(
            "CREATION_PUBLISH_CONFLICT", f"目标目录内已存在同名发布临时文件：{temp}", "NEEDS_REVIEW"
        )
    shutil.copy2(staged, temp)
    if file_sha256(temp) != entry["staged_hash"]:
        raise ProjectPublishError(
            "CREATION_PUBLISH_FAILED", f"发布副本已偏离候选哈希：{staged}", "ABORTED"
        )
    entry["attempted"] = True
    entry["publish_temp"] = str(temp)
    entry["publish_identity"] = file_identity(temp)
    write_journal(journal_path, journal)
    move_no_replace(temp, target)
    if (
        not target.exists()
        or file_identity(target) != entry["publish_identity"]
        or file_sha256(target) != entry["staged_hash"]
    ):
        raise ProjectPublishError(
            "CREATION_PUBLISH_REVIEW_REQUIRED", f"目标文件提交后身份或内容已变化：{target}", "NEEDS_REVIEW"
        )
    entry["committed"] = True
    entry["result_hash"] = entry["staged_hash"]
    entry["result_identity"] = entry["publish_identity"]
    write_journal(journal_path, journal)


def _rollback_entry(entry: dict[str, Any], rollback_dir: Path) -> None:
    """回滚一个条目：只处理本次占有且身份匹配的文件，身份不符即留给人工核对。"""
    target = Path(entry["target"])
    owned = [value for value in (entry.get("publish_identity"), entry.get("result_identity")) if value]
    if target.exists():
        identity = file_identity(target)
        if identity in owned:
            _quarantine(target, rollback_dir, identity)
        else:
            entry["rollback_conflict"] = True
    raw_temp = entry.get("publish_temp")
    if raw_temp and (temp := Path(raw_temp)).exists():
        if file_identity(temp) == entry.get("publish_identity"):
            _quarantine(temp, rollback_dir, entry["publish_identity"])
        else:
            entry["rollback_conflict"] = True


def _quarantine(path: Path, rollback_dir: Path, expected_identity: list[int]) -> None:
    """按身份把本批文件换名到回滚隔离目录再删除，绝不就地按名字删除。"""
    rollback_dir.mkdir(parents=True, exist_ok=True)
    displaced = rollback_dir / f"{file_sha256(path)[:16]}-{path.name}"
    if displaced.exists():
        raise ProjectPublishError(
            "CREATION_PUBLISH_REVIEW_REQUIRED", f"回滚隔离文件已存在：{displaced}", "NEEDS_REVIEW"
        )
    move_no_replace(path, displaced)
    if file_identity(displaced) != expected_identity:
        raise ProjectPublishError(
            "CREATION_PUBLISH_REVIEW_REQUIRED", f"回滚换名期间文件身份已变化：{displaced}", "NEEDS_REVIEW"
        )
    displaced.unlink()


def _residual_entries(target: Path) -> list[Path]:
    """回滚后目标目录内的残余内容（发布前为空，因此残余必为外部内容）。"""
    if not target.exists() or not target.is_dir():
        return []
    return sorted(target.iterdir(), key=lambda item: item.name.casefold())


def _target_lock_path(attempt_dir: Path, target: Path) -> Path:
    """目标级锁路径：锁放在 Manager 应用数据目录，不污染新项目目录。"""
    return (
        attempt_dir.parent.parent
        / CREATION_PUBLISH_LOCK_DIR_NAME
        / f"target-{_target_key(target)}.lock"
    )


def _target_key(target: Path) -> str:
    """目标级锁名：目标路径的稳定摘要（不把路径本身拼进文件名）。"""
    return hashlib.sha256(str(target).casefold().encode("utf-8")).hexdigest()[:16]


def _published_project(
    journal: dict[str, Any], target: Path, journal_path: Path, revision_dir: Path
) -> PublishedProject:
    """把已提交日志投影成成果值：字段与启动恢复侧同一实现，不复制字段集合。"""
    payload = publish_recovery.creation_published_payload(journal)
    return PublishedProject(
        job_id=journal["operation_id"],
        attempt=journal["attempt"],
        target_dir=target,
        dst_path=Path(payload["dst_path"]),
        target_state=payload["target_state"],
        files=tuple(
            PublishedFile(
                name=item["name"],
                role=item["role"],
                group_id=item["group_id"],
                target=target / item["name"],
                sha256=item["sha256"],
                size=item["size"],
            )
            for item in payload["files"]
        ),
        journal_path=journal_path,
        revision_dir=revision_dir,
        journal=journal,
    )
