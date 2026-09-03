"""发布事务与启动恢复辅助（v0.3.2 Task 0 自 service.py 拆分）。

`TransactionRecoveryOperations` 以 mixin 组合进 `DstManagerService`：
承载 COMMITTED 清单校验、启动恢复闭环、不可证明发布隔离、提交后
操作事件与工作区元数据写入等共享事务辅助，供入口与各功能域模块
经 `self` 引用。
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dst_manager.domain.models import JobStatus, Workspace
from dst_manager.infrastructure.filesystem.locking import WindowsResultGuards
from dst_manager.infrastructure.filesystem.publisher import (
    PublishRecoveryError,
    capture_file_baseline,
)
from dst_manager.infrastructure.filesystem.workspace import write_workspace_metadata
from dst_manager.infrastructure.operation_log import append_operation_event


class TransactionRecoveryOperations:
    def _require_committed_operation(self, workspace_root: Path, operation_id: str) -> dict[str, Any]:
        journal = self.publisher.read_committed_operation(workspace_root, operation_id)
        if journal is None:
            raise PublishRecoveryError(f"COMMITTED_JOURNAL_MISSING: {operation_id}")
        return journal

    @staticmethod
    def _committed_result_hash(journal: dict[str, Any], target: Path) -> str:
        target_key = str(target.resolve()).casefold()
        for entry in journal["files"]:
            if str(Path(entry["target"]).resolve()).casefold() == target_key:
                result_hash = entry.get("result_hash")
                if isinstance(result_hash, str):
                    return result_hash
                break
        raise PublishRecoveryError(f"COMMITTED_RESULT_MISSING: {target}")

    def _recover_committed_job(self, workspace_root: Path, journal: dict[str, Any]) -> None:
        operation_id = journal["operation_id"]
        job = self.database.get_job(operation_id)
        if job is None or job["status"] == JobStatus.SUCCEEDED:
            return
        # 过期的 PUBLISHING 任务已被回收并明确隔离；其 COMMITTED 清单不能
        # 再被启动恢复自动闭环，避免失权的旧 Worker 把任务恢复为成功。
        if (
            job["status"] == JobStatus.NEEDS_REVIEW
            and job.get("error_code") == "PUBLISH_JOURNAL_REVIEW_REQUIRED"
        ):
            return
        heartbeat_at = job.get("heartbeat_at")
        if heartbeat_at:
            try:
                heartbeat = datetime.fromisoformat(heartbeat_at)
            except ValueError:
                return
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=UTC)
            if heartbeat < datetime.now(UTC) - timedelta(seconds=self.settings.worker_lease_seconds):
                return
        try:
            if journal.get("identity_version") != 1:
                raise PublishRecoveryError("COMMITTED_IDENTITY_VERSION_UNSUPPORTED")
            existing_results = [
                Path(entry["target"])
                for entry in journal["files"]
                if entry.get("result_hash") is not None
            ]
            missing_results = [
                Path(entry["target"])
                for entry in journal["files"]
                if entry.get("result_hash") is None
            ]
            with WindowsResultGuards(existing_results, missing_results) as result_guard:
                self._validate_recovered_committed_results(journal, result_guard)
                workspace = self.database.get_workspace(job["workspace_id"])
                if workspace is None:
                    raise PublishRecoveryError("COMMITTED_WORKSPACE_MISSING")
                payload = job["payload"]
                target = Path(payload["destination"]) if job["type"] == "xml_export" else Path(workspace.dst_path)
                result_hash = self._committed_result_hash(journal, target)
                entry = next(
                    item
                    for item in journal["files"]
                    if str(Path(item["target"]).resolve()).casefold() == str(target.resolve()).casefold()
                )
                before_hash = entry.get("before_hash") or payload["base_revision_id"]
                update_current = job["type"] != "xml_export" or target.resolve() == Path(workspace.dst_path).resolve()
                if job["type"] == "revision_restore":
                    revision_id = f"restore-{operation_id}"
                elif job["type"] == "xml_export":
                    revision_id = f"xml-{operation_id}"
                else:
                    revision_id = f"change-{operation_id}"
                revision_dir = workspace_root / ".dst-manager" / "revisions" / operation_id
                self.database.finalize_committed_job(
                    revision_id,
                    job["workspace_id"],
                    operation_id,
                    before_hash,
                    result_hash,
                    revision_dir,
                    update_current=update_current,
                    current_revision=result_hash if update_current else None,
                )
        except Exception as exc:  # noqa: BLE001 - 无法证明 COMMITTED 一致性时必须隔离
            self.database.finalize_job_terminal(
                operation_id,
                JobStatus.NEEDS_REVIEW,
                "COMMITTED_RECOVERY_UNPROVEN",
                str(exc),
            )

    def _quarantine_unproven_publish_jobs(self, workspace_root: Path, error: PublishRecoveryError) -> None:
        """发布清单不可证明时，只按受控任务目录隔离，绝不读取它来完成事务。"""
        jobs_root = workspace_root.resolve() / ".dst-manager" / "jobs"
        if not jobs_root.is_dir():
            return
        error_code = str(error) or error.code
        for journal_path in jobs_root.glob("*/publish-journal.json"):
            operation_id = journal_path.parent.name
            if not operation_id or journal_path.parent.parent != jobs_root:
                continue
            job = self.database.get_job(operation_id)
            if job is None or job["status"] == JobStatus.SUCCEEDED:
                continue
            try:
                self.database.finalize_job_terminal(
                    operation_id,
                    JobStatus.NEEDS_REVIEW,
                    error_code,
                    str(error),
                )
            except KeyError:
                continue

    @staticmethod
    def _validate_recovered_committed_results(
        journal: dict[str, Any],
        result_guard: WindowsResultGuards,
    ) -> None:
        for entry in journal["files"]:
            target = Path(entry["target"])
            result_hash = entry.get("result_hash")
            if result_hash is None:
                if not result_guard.protects_missing(target):
                    raise PublishRecoveryError(f"COMMITTED_RESULT_CHANGED: {target}")
                continue
            baseline = capture_file_baseline(target)
            expected_identity = entry.get("result_identity")
            if (
                baseline is None
                or baseline.sha256 != result_hash
                or expected_identity is None
                or tuple(expected_identity) != baseline.identity
            ):
                raise PublishRecoveryError(f"COMMITTED_RESULT_CHANGED: {target}")

    @staticmethod
    def _safe_operation_event(root: Path, operation_id: str, event: str, **details: Any) -> None:
        try:
            append_operation_event(root, operation_id, event, **details)
        except Exception:  # noqa: BLE001, S110 - 提交后诊断失败不得改变已提交状态
            pass

    @staticmethod
    def _write_workspace_metadata_after_commit(
        workspace: Workspace,
        revision_id: str,
        cad_version: str,
        operation_id: str,
    ) -> None:
        try:
            write_workspace_metadata(
                workspace.root,
                workspace.id,
                workspace.dst_path,
                revision_id,
                cad_version,
            )
        except Exception as exc:  # noqa: BLE001 - DB 已闭环，元数据仅作为可重试诊断
            TransactionRecoveryOperations._safe_operation_event(
                workspace.root,
                operation_id,
                "POST_COMMIT_METADATA_FAILED",
                error=repr(exc),
            )
