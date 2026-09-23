"""创建执行编排：权威预览复核、任务入队与运行（PLAN-DM-036 Task 6）。

`CreationExecutionOperations` 以 mixin 组合进 `DstManagerService`（与
:mod:`dst_manager.application.creation` 同层拆分：执行编排属于独立职责，且创建
预览模块已接近容量软上限，不再追加新方法）。它只做编排，不复制任何领域规则：

- 执行入口只接收草稿 ID 与 ``preview_digest``，入队前**重新加载**标准、草稿、
  目标与设置/资产快照并重算摘要；漂移以 409 ``CREATION_PREVIEW_STALE`` 拒绝，
  客户端永远不能提供目标路径、组表、命名结果等派生输出；
- 创建任务在普通工作区尚不存在时就已持久化（``workspace_id`` 为 NULL、
  ``creation_draft_id`` 指向草稿），状态、进度、时间线与失败诊断因此照常记录；
- Worker 侧执行前再次重算摘要并重建计划，再交给
  :class:`~dst_manager.application.creation_job.CreationJobRunner` 隔离暂存与
  可恢复发布；发布成功后由登记功能域（:mod:`dst_manager.application.creation_registration`）
  接管为普通工作区与初始修订，本模块只装配登记回调；
- 启动恢复按持久日志幂等处理中断的创建发布，只闭环任务状态，不重发成果。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

# 创建功能域统一的稳定错误构造（消息以「错误码: 详情」呈现）；同层共享同一实现，
# 不另立第二套消息格式。
from dst_manager.application.creation import _creation_error
from dst_manager.application.creation_assets import standard_package_root
from dst_manager.application.creation_job import (
    CREATION_JOBS_DIR_NAME,
    CreationJobRunner,
)
from dst_manager.application.errors import ApplicationError
from dst_manager.application.standards import parse_standard_identity
from dst_manager.domain.creation_plan_models import CreationPlan
from dst_manager.domain.models import JobStatus
from dst_manager.infrastructure.autocad.worker import LayoutCreationWorker
from dst_manager.infrastructure.filesystem.project_publisher import ProjectPublisher
from dst_manager.infrastructure.filesystem.publish_errors import PublishRecoveryError
from dst_manager.infrastructure.filesystem.publish_recovery import (
    CreationPublishOutcome,
)
from dst_manager.infrastructure.persistence.database import TERMINAL_JOB_STATUSES

__all__ = ["CreationExecutionOperations"]


class CreationExecutionOperations:
    """经 `self` 访问 database/project_publisher/standard_store 的创建执行功能域。"""

    #: 由 DstManagerService.__init__ 注入（与普通工作区发布器相互独立）。
    project_publisher: ProjectPublisher

    def execute_creation(self, draft_id: str, preview_digest: str) -> dict[str, Any]:
        """复核权威预览后把创建任务入队；不写目标目录、不启动 CAD。"""
        draft, plan, preview = self._creation_preview(draft_id)
        if preview["preview_digest"] != preview_digest:
            raise _creation_error(
                "CREATION_PREVIEW_STALE",
                "创建预览已变化或尚未确认，请重新预览后再执行",
                409,
            )
        if not preview["executable"]:
            raise _creation_error(
                "CREATION_PLAN_INVALID",
                "创建计划存在阻断诊断："
                + ", ".join(sorted({str(item["code"]) for item in preview["diagnostics"]})),
            )
        settings = self._live_settings()
        job_id = str(uuid.uuid4())
        self.database.create_job(
            job_id,
            None,
            "creation",
            JobStatus.QUEUED,
            {
                "creation_draft_id": draft.id,
                "creation_revision": draft.revision,
                "standard": {
                    "standard_id": draft.standard_id,
                    "version": draft.standard_version,
                },
                "preview_digest": preview_digest,
                "target_path": plan.target_path,
                "plan_digest": plan.digest,
            },
            settings.cad_version,
            creation_draft_id=draft.id,
        )
        return self.database.get_job(job_id) or {}

    def reload_creation_plan(self, draft_id: str, preview_digest: str) -> CreationPlan:
        """Worker 侧执行前重算权威预览：任何漂移都以 ``CREATION_PREVIEW_STALE`` 拒绝。"""
        _draft, plan, preview = self._creation_preview(draft_id)
        if preview["preview_digest"] != preview_digest:
            raise _creation_error(
                "CREATION_PREVIEW_STALE",
                "创建预览已变化，禁止按旧摘要执行；请重新预览后再执行",
                409,
            )
        return plan

    def run_creation_job(self, job: dict[str, Any]) -> dict[str, Any]:
        """运行一个已领取的创建任务：重算预览 → 隔离暂存 → 可恢复发布。"""
        payload = job["payload"]
        worker_id = job.get("worker_id")
        attempt = job.get("attempt")
        try:
            plan = self.reload_creation_plan(
                payload["creation_draft_id"], payload["preview_digest"]
            )
            asset_root = self._creation_asset_root(plan)
        except ApplicationError as exc:
            self.database.finalize_job_terminal(
                job["id"],
                JobStatus.FAILED,
                exc.code,
                str(exc),
                worker_id=worker_id,
                attempt=attempt,
            )
            return self.database.get_job(job["id"]) or {}
        snapshot = self._live_settings()
        runner = CreationJobRunner(
            data_dir=self.settings.data_dir,
            asset_root=asset_root,
            worker=LayoutCreationWorker(
                self._capability(job["cad_version"] or snapshot.cad_version, snapshot)
            ),
            timeout=snapshot.cad_timeout_seconds,
            database=self.database,
            publisher=self.project_publisher,
            # 发布成功后的登记回调：任务只在登记完成（或登记失败被隔离）后落终态。
            registration=self,
        )
        return runner.run(job["id"], attempt, plan)

    def _creation_asset_root(self, plan: CreationPlan) -> Path:
        """计划固定的标准身份 → 标准包根；不可读取即稳定拒绝，不降级到其它版本。"""
        standard_id, version = parse_standard_identity(plan.settings.standard_identity)
        root = standard_package_root(self.standard_store, standard_id, version)
        if root is None:
            raise _creation_error(
                "CREATION_STANDARD_MISSING",
                f"标准 {plan.settings.standard_identity} 已不可读取，请重新选择标准",
                404,
            )
        return root

    # ---- 启动恢复 --------------------------------------------------------

    def recover_interrupted_creation_jobs(self) -> list[dict[str, Any]]:
        """启动恢复：按持久日志幂等处理中断的创建发布，并闭环对应任务。

        已提交：幂等补登记（工作区/初始修订），绝不重发或覆盖成果；已回滚：任务落
        ``ROLLED_BACK``；出现外部内容/身份不匹配：任务落 ``NEEDS_REVIEW``，
        日志与现场原样保留。日志身份不可信时只按受控目录层级隔离任务，
        不读取日志内容决定数据库主键。
        """
        root = self.settings.data_dir / CREATION_JOBS_DIR_NAME
        try:
            outcomes = self.project_publisher.recover_creation_publishes(root)
        except PublishRecoveryError as exc:
            self._quarantine_unproven_creation_jobs(root, exc)
            return []
        conclusions: list[dict[str, Any]] = []
        for outcome in outcomes:
            job = self.database.get_job(outcome.job_id)
            if job is None:
                continue
            if outcome.conclusion == "COMMITTED":
                self._resume_committed_creation(outcome)
                conclusions.append({"id": outcome.job_id, "conclusion": "COMMITTED"})
                continue
            if job["status"] in TERMINAL_JOB_STATUSES:
                continue
            if outcome.conclusion == "ROLLED_BACK":
                self.database.finalize_job_terminal(
                    outcome.job_id, JobStatus.ROLLED_BACK, "STARTUP_RECOVERY", outcome.detail
                )
                conclusions.append({"id": outcome.job_id, "conclusion": "ROLLED_BACK"})
                continue
            self.database.finalize_job_terminal(
                outcome.job_id,
                JobStatus.NEEDS_REVIEW,
                "CREATION_PUBLISH_REVIEW_REQUIRED",
                outcome.detail,
            )
            conclusions.append({"id": outcome.job_id, "conclusion": "NEEDS_REVIEW"})
        return conclusions

    def _resume_committed_creation(self, outcome: CreationPublishOutcome) -> None:
        """已提交发布的补登记：已登记完成则跳过，否则按持久投影幂等补登记。"""
        job = self.database.get_job(outcome.job_id) or {}
        if job.get("status") == JobStatus.SUCCEEDED and job.get("workspace_id"):
            return
        if outcome.published is None:
            return
        self.resume_creation_registration(outcome.job_id, outcome.published)

    def _quarantine_unproven_creation_jobs(self, root: Path, error: PublishRecoveryError) -> None:
        """创建发布日志不可证明时，只按受控目录层级隔离任务，不猜测性清理任何文件。"""
        if not root.is_dir():
            return
        error_code = str(error) or error.code
        for journal_path in root.glob("*/attempt-*/publish-journal.json"):
            job_id = journal_path.parent.parent.name
            job = self.database.get_job(job_id)
            if job is None or job["status"] in TERMINAL_JOB_STATUSES:
                continue
            self.database.finalize_job_terminal(
                job_id, JobStatus.NEEDS_REVIEW, error_code, "创建发布日志身份不可证明"
            )
