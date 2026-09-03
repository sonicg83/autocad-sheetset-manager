"""修复域（v0.3.2 Task 0 自 service.py 拆分）。

`RepairOperations` 以 mixin 组合进 `DstManagerService`：预览可审计修复
摘要（`preview_repair`）并把内存修复作为独立修订沿受控发布事务写回
（`execute_repair`）。基准捕获经共享门禁 `self._capture_baseline` 转发。
"""

import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dst_manager.application.errors import ApplicationError
from dst_manager.application.summaries import operation_digest
from dst_manager.domain.models import JobStatus, Severity
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.acsm_xml.document import repair_digest
from dst_manager.infrastructure.filesystem.locking import WindowsWriteLocks
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
)
from dst_manager.infrastructure.persistence.database import WorkspaceBusyError


class RepairOperations:
    def preview_repair(self, workspace_id: str, base_revision_id: str) -> dict[str, Any]:
        """固定 base revision 并生成修复摘要与可审计报告；执行只信任服务端重解码结果。"""
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        acsm = load_acsm(self.codec.decode_file(workspace.dst_path))
        report = acsm.repair_report
        if report.status == "VALID":
            return {
                "workspace_id": workspace_id,
                "base_revision_id": base_revision_id,
                "status": "VALID",
                "actions": [],
                "blocking_issues": [],
                "preview_digest": None,
                "executable": False,
            }
        # 摘要只对可确认的 REPAIRED 状态有意义：INVALID_* 不可执行，不返回摘要，
        # 避免客户端混淆“不可执行的阻断”与“待确认的修复”。
        actions = [self._repair_action_dict(action) for action in report.actions]
        blocking_issues = [asdict(issue) for issue in report.blocking_issues]
        digest = (
            operation_digest(
                operation_type="repair_publish",
                workspace_id=workspace_id,
                base_revision_id=base_revision_id,
                normalized_input={"repair_digest": repair_digest(acsm.root, base_revision_id)},
                semantic_diff={
                    "action_codes": [action["code"] for action in actions],
                    "blocking_issue_codes": [issue["code"] for issue in blocking_issues],
                },
                target_baselines={str(workspace.dst_path): base_revision_id},
            )
            if report.status == "REPAIRED"
            else None
        )
        return {
            "workspace_id": workspace_id,
            "base_revision_id": base_revision_id,
            "status": report.status,
            "actions": actions,
            "blocking_issues": blocking_issues,
            "preview_digest": digest,
            "executable": report.status == "REPAIRED",
        }

    def execute_repair(self, workspace_id: str, base_revision_id: str, preview_digest: str | None) -> dict[str, Any]:
        """把可审计的内存修复作为独立修订，沿现有受控发布事务写回正式 DST。

        执行时从正式 DST 重新解码、修复、严格校验并复核预览摘要；不允许通过
        普通业务 commands 或客户端 XML 绕过确认。发布沿用锁、永久 before 快照、
        暂存、校验、发布日志与失败回滚/启动恢复流程。
        """
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        job_id = str(uuid.uuid4())
        try:
            self.database.create_job(
                job_id,
                workspace_id,
                "repair_revision",
                JobStatus.VALIDATED,
                {"base_revision_id": base_revision_id, "kind": "repair"},
            )
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc
        operation_id = job_id
        published = False
        commit_state: dict[str, Any] = {"result_hash": None, "error": None}
        try:
            with WindowsWriteLocks([workspace.dst_path]):
                expected_baseline = self._capture_baseline(workspace.dst_path)
                if expected_baseline is None or expected_baseline.sha256 != base_revision_id:
                    raise PublishBaselineError("DST 已偏离修复预览基准")
                acsm = load_acsm(self.codec.decode_file(workspace.dst_path))
                report = acsm.repair_report
                if report.status == "VALID":
                    raise ApplicationError("REPAIR_NOT_REQUIRED", "当前 DST 无待确认修复")
                if report.status != "REPAIRED":
                    raise ApplicationError("REPAIR_BLOCKED", "修复后仍存在阻断问题，禁止发布")
                expected_digest = operation_digest(
                    operation_type="repair_publish",
                    workspace_id=workspace_id,
                    base_revision_id=base_revision_id,
                    normalized_input={"repair_digest": repair_digest(acsm.root, base_revision_id)},
                    semantic_diff={
                        "action_codes": [action.code for action in report.actions],
                        "blocking_issue_codes": [issue.code for issue in report.blocking_issues],
                    },
                    target_baselines={str(workspace.dst_path): base_revision_id},
                )
                if preview_digest != expected_digest:
                    raise ApplicationError("REPREVIEW_REQUIRED", "修复预览已变化，请重新预览并确认", 409)
                issues = acsm.validate()
                if any(issue.severity == Severity.ERROR for issue in issues):
                    raise ApplicationError("XML_VALIDATION_FAILED", "修复后 DST XML 校验失败")
                self.database.update_job(job_id, JobStatus.STAGING, 20)
                self._safe_operation_event(workspace.root, job_id, "STAGING", job_type="repair")
                job_dir = workspace.root / ".dst-manager" / "jobs" / operation_id
                staging = job_dir / "staging" / workspace.dst_path.name
                staging.parent.mkdir(parents=True, exist_ok=True)
                self.codec.encode_file(acsm.to_bytes(), staging)
                roundtrip = load_acsm(self.codec.decode_file(staging))
                if roundtrip.semantic_bytes() != acsm.semantic_bytes():
                    raise ValueError("DST_ROUNDTRIP_MISMATCH")
                self.database.update_job(job_id, JobStatus.PREPARED, 70)
                if self._capture_baseline(workspace.dst_path) != expected_baseline:
                    raise PublishBaselineError("DST 在发布前已偏离修复基准")
                self.database.update_job(job_id, JobStatus.PUBLISHING, 90)
                self._safe_operation_event(workspace.root, job_id, "PUBLISHING", file_count=1)

                def finalize_repair(revision_dir: Path, journal: dict[str, Any]) -> None:
                    try:
                        result_hash = self._committed_result_hash(journal, workspace.dst_path)
                        commit_state["result_hash"] = result_hash
                        self.database.finalize_committed_job(
                            f"repair-{operation_id}",
                            workspace_id,
                            operation_id,
                            expected_baseline.sha256,
                            result_hash,
                            revision_dir,
                            current_revision=result_hash,
                        )
                    except Exception as exc:  # noqa: BLE001 - 回调不得让 COMMITTED 进入回滚分支
                        commit_state["error"] = exc
                        try:
                            current = self.database.get_job(job_id) or {}
                            if current.get("status") != JobStatus.SUCCEEDED:
                                self.database.finalize_job_terminal(
                                    job_id,
                                    JobStatus.NEEDS_REVIEW,
                                    "COMMITTED_FINALIZE_FAILED",
                                    str(exc),
                                )
                        except Exception:  # noqa: BLE001, S110 - 启动恢复仍会依据 COMMITTED 日志隔离
                            pass

                self.publisher.publish(
                    operation_id,
                    workspace.root,
                    {workspace.dst_path: staging},
                    expected_baselines={workspace.dst_path: expected_baseline},
                    on_committed=finalize_repair,
                )
                published = True
        except PublishRolledBackError as exc:
            self.database.finalize_job_terminal(job_id, JobStatus.ROLLED_BACK, exc.code, str(exc))
            return self.database.get_job(job_id) or {}
        except PublishRecoveryError as exc:
            self.database.finalize_job_terminal(job_id, JobStatus.NEEDS_REVIEW, exc.code, str(exc))
            return self.database.get_job(job_id) or {}
        except Exception as exc:  # noqa: BLE001 - 同步写入边界必须持久化终态并释放写锁
            current = self.database.get_job(job_id) or {}
            if current.get("status") == JobStatus.SUCCEEDED:
                return current
            status = JobStatus.NEEDS_REVIEW if published else JobStatus.FAILED
            code = "COMMITTED_FINALIZE_FAILED" if published else getattr(exc, "code", type(exc).__name__.upper())
            self.database.finalize_job_terminal(job_id, status, code, str(exc))
            return self.database.get_job(job_id) or {}
        if commit_state["error"] is not None:
            return self.database.get_job(job_id) or {}
        result_hash = commit_state["result_hash"]
        if not isinstance(result_hash, str):
            self.database.finalize_job_terminal(
                job_id,
                JobStatus.NEEDS_REVIEW,
                "COMMITTED_FINALIZE_MISSING",
            )
            return self.database.get_job(job_id) or {}
        self._write_workspace_metadata_after_commit(workspace, result_hash, "2020", job_id)
        self._safe_operation_event(workspace.root, job_id, "SUCCEEDED", revision_id=f"repair-{operation_id}")
        return self.database.get_job(job_id) or {}

    @staticmethod
    def _repair_action_dict(action) -> dict[str, Any]:
        return {
            "code": action.code,
            "node_path": action.node_path,
            "object_id": action.object_id,
            "confidence": action.confidence,
            "before": action.before,
            "after": action.after,
            "message": action.message,
        }
