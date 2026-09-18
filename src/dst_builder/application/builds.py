"""构建/attempt 编排（SPEC-DB-001 §5/§6/§9/§11，PLAN-DB-001 Task 9）。

:class:`BuildCoordinator` 是唯一编排者：

* 每次状态迁移与事件写入**同一数据库事务**（``build_attempts``/``build_events``
  与 ``build_runs`` 一起提交）；
* 阻塞 CAD 调用在**线程执行器**中运行（后台线程 + 独立数据库会话），
  绝不阻塞 SSE/HTTP event loop；
* 状态迁移一律经领域层 ``build_state.transition`` 封闭迁移表；
* 发布经 ``infrastructure.filesystem.publisher`` 原子改名，``PUBLISHING``
  不响应取消；
* 计划冻结（§5）：启动构建前用当前草稿重新计算确定性计划，与请求的
  ``plan_id`` 不一致即 ``PLAN_STALE``；已启动构建使用创建时快照的计划与
  发布目标，不受后续草稿影响。

错误族与结果视图见 ``build_contracts``；事件载荷与 SSE 重放工具见
``build_events``。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from dst_builder.application.assets import AssetNotFoundError
from dst_builder.application.build_contracts import (
    BUILD_FAILED,
    AttemptView,
    BuildAlreadyRunningError,
    BuildNotFoundError,
    BuildServiceError,
    BuildStatusView,
    BuildTargetExistsError,
    BuildTargetInvalidError,
    CancelNotAcceptedError,
    PlanBlockedError,
    PlanConfirmation,
    PlanNotConfirmedError,
    PlanNotFoundError,
    PlanPreview,
    PlanStaleError,
)
from dst_builder.application.build_events import (
    SSE_POLL_SECONDS,
    STAGE_PROGRESS,
    TERMINAL_STATUSES,
    event_record,
    format_sse,
    next_sequence,
    parse_position,
)
from dst_builder.application.handoff_adapter import (
    default_handoff_transport,
    manager_base_url_from_environ,
)
from dst_builder.application.projects import (
    ProjectNotInitializedError,
    draft_from_payload,
)
from dst_builder.application.validation import build_validation_report
from dst_builder.domain.build_state import (
    BuildStatus,
    IllegalTransitionError,
    transition,
)
from dst_builder.domain.models import (
    AssetSnapshot,
    GenerationPlanV1,
    ProjectRevisionV1,
)
from dst_builder.domain.normalization import canonical_json
from dst_builder.domain.planning import commit_revision, create_plan, validate_draft
from dst_builder.infrastructure.acsm.factory import build_dst_bytes
from dst_builder.infrastructure.acsm.projection import (
    DstValidationError,
    ensure_dst_valid,
)
from dst_builder.infrastructure.assets.store import SqliteAssetRepository
from dst_builder.infrastructure.autocad.request import AttemptPaths
from dst_builder.infrastructure.catalog.xlsx import build_sheet_catalog_xlsx
from dst_builder.infrastructure.filesystem.attempts import (
    create_attempt_dirs,
    unique_staging_name,
    write_cad_evidence,
    write_publish_evidence,
)
from dst_builder.infrastructure.filesystem.package import assemble_package_files
from dst_builder.infrastructure.filesystem.publisher import publish_candidate
from dst_builder.infrastructure.persistence.database import Database, utc_now_iso
from dst_builder.infrastructure.persistence.repositories import (
    BuildAttemptRecord,
    BuildEventRecord,
    BuildRunRecord,
    PlanRecord,
    RevisionRecord,
    SqliteBuildRepository,
    SqliteProjectRepository,
    SqliteRevisionRepository,
)

__all__ = [
    "BUILD_FAILED",
    "AttemptView",
    "BuildAlreadyRunningError",
    "BuildCoordinator",
    "BuildNotFoundError",
    "BuildServiceError",
    "BuildStatusView",
    "BuildTargetExistsError",
    "BuildTargetInvalidError",
    "CancelNotAcceptedError",
    "HandoffNotPublishedError",
    "HandoffPackageMissingError",
    "HandoffRejectedError",
    "HandoffUnavailableError",
    "PlanBlockedError",
    "PlanConfirmation",
    "PlanNotConfirmedError",
    "PlanNotFoundError",
    "PlanPreview",
    "PlanStaleError",
]


class _BuildCancelled(Exception):
    """取消检查点命中的内部信号（转换为 CANCELLED 迁移）。"""


class HandoffNotPublishedError(BuildServiceError):
    """构建尚未成功发布，成果包不存在（HANDOFF_INVALID）。"""

    code = "HANDOFF_INVALID"
    status_code = 409

    @property
    def recovery_action(self) -> str:
        return "先完成构建并到达 SUCCEEDED 状态，再发起交接"


class HandoffPackageMissingError(BuildServiceError):
    """已发布成果包缺少 metadata/handoff.json（HANDOFF_INVALID）。"""

    code = "HANDOFF_INVALID"
    status_code = 409

    @property
    def recovery_action(self) -> str:
        return "已发布成果包保留不变；确认 metadata/handoff.json 存在后重试"


class HandoffUnavailableError(BuildServiceError):
    """本机 Manager 不可达（HANDOFF_UNAVAILABLE）：已发布包保留并给出恢复动作。"""

    code = "HANDOFF_UNAVAILABLE"
    status_code = 502

    @property
    def recovery_action(self) -> str:
        return (
            "已发布成果包保留不变：启动 DST Manager 后重试，"
            f"或直接在 Manager 中打开 {self.message}"
        )


class HandoffRejectedError(BuildServiceError):
    """Manager 验证拒绝交接：透传 Manager 的稳定错误码。"""

    status_code = 422

    def __init__(
        self, code: str, status_code: int, message: str, *, field: str | None = None
    ) -> None:
        super().__init__(message, field=field)
        self.code = code
        self.status_code = status_code

    @property
    def recovery_action(self) -> str:
        return "已发布成果包保留不变；按错误信息修正后重试"


def _built_dwg_relative(build_id: str, attempt: int) -> str:
    """DWG 工作成果落在 attempt 内（项目根不残留正式成果副本）。"""
    return f"builds/{build_id}/attempt-{attempt:03d}/work/built.dwg"


def _plan_preview(plan: GenerationPlanV1) -> dict:
    task = plan.sheetset_task
    return {
        "sheet_number": task.sheet_number,
        "layout_name": task.layout_name,
        "dwg_name": task.dwg_path,
        "artifact_path": plan.drawing_task.target_dwg_path,
        "dst_path": task.dst_path,
        "sheetset_name": task.sheetset_name,
        "subset_name": task.subset_name,
        "cad_version": plan.cad_version,
    }


def _revision_record(revision: ProjectRevisionV1) -> RevisionRecord:
    from dst_builder.domain.planning import revision_payload

    return RevisionRecord(
        id=revision.revision_id,
        canonical_json=canonical_json(revision_payload(revision, revision.assets)),
        sha256=revision.revision_sha256,
        created_at=utc_now_iso(),
    )


def _plan_record(plan: GenerationPlanV1, revision: ProjectRevisionV1) -> PlanRecord:
    from dst_builder.domain.planning import plan_payload

    return PlanRecord(
        id=plan.plan_id,
        revision_id=plan.revision_id,
        canonical_json=canonical_json(plan_payload(revision)),
        sha256=plan.plan_sha256,
        confirmed_at=None,
    )


class BuildCoordinator:
    """计划提交/确认与 build/attempt 生命周期编排。"""

    def __init__(
        self,
        project_root: Path,
        *,
        drawing_builder: object,
        database: Database | None = None,
        max_workers: int = 1,
    ) -> None:
        self._project_root = Path(project_root)
        self._drawing_builder = drawing_builder
        self._database = database
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        # 取消标志按 (build_id, attempt) 键控：标志只作用于发起取消时的那个
        # attempt，绝不泄漏到同 build 的后续重试 attempt（§6 递增重试路径）。
        self._cancel_flags: dict[tuple[str, int], threading.Event] = {}

    # -- 计划（§5）----------------------------------------------------------

    def submit_plan(self) -> PlanPreview:
        draft, assets, target = self._load_frozen_inputs()
        revision = commit_revision(draft, assets)
        plan = create_plan(revision)
        diagnostics = validate_draft(draft, output_exists=target.exists())
        with self._require_database().sessions.begin() as session:
            repository = SqliteRevisionRepository(session)
            if repository.load_revision(revision.revision_id) is None:
                repository.insert_revision(_revision_record(revision))
            if repository.load_plan(plan.plan_id) is None:
                repository.insert_plan(_plan_record(plan, revision))
        return PlanPreview(
            plan_id=plan.plan_id,
            revision_id=revision.revision_id,
            revision_sha256=revision.revision_sha256,
            plan_sha256=plan.plan_sha256,
            diagnostics=diagnostics,
            preview=_plan_preview(plan),
        )

    def confirm_plan(self, plan_id: str) -> PlanConfirmation:
        draft, assets, target = self._load_frozen_inputs()
        revision = commit_revision(draft, assets)
        now = utc_now_iso()
        with self._require_database().sessions.begin() as session:
            repository = SqliteRevisionRepository(session)
            plan_record = repository.load_plan(plan_id)
            if plan_record is None:
                raise PlanNotFoundError(f"计划不存在：{plan_id}")
            if json.loads(plan_record.canonical_json)["revision_id"] != revision.revision_id:
                raise PlanStaleError("草稿已变化，当前计划对应旧修订")
            blocking = [
                diagnostic
                for diagnostic in validate_draft(draft, output_exists=target.exists())
                if diagnostic.severity.value == "blocking"
            ]
            if blocking:
                raise PlanBlockedError(blocking[0])
            repository.set_plan_confirmed(plan_id, now)
        return PlanConfirmation(
            plan_id=plan_id, revision_id=revision.revision_id, confirmed_at=now
        )

    # -- 构建（§6/§9）-------------------------------------------------------

    def start_build(self, plan_id: str) -> BuildStatusView:
        draft, assets, target = self._load_frozen_inputs()
        revision = commit_revision(draft, assets)
        plan = create_plan(revision)
        with self._require_database().sessions.begin() as session:
            revision_repository = SqliteRevisionRepository(session)
            plan_record = revision_repository.load_plan(plan_id)
            if plan_record is None:
                raise PlanNotFoundError(f"计划不存在：{plan_id}")
            if plan.plan_id != plan_id:
                raise PlanStaleError("草稿已变化，请求的计划对应旧修订")
            if plan_record.confirmed_at is None:
                raise PlanNotConfirmedError(f"计划尚未确认：{plan_id}")
            revision_record = revision_repository.load_revision(plan.revision_id)
            if revision_record is None:
                raise PlanNotFoundError(f"计划修订缺失：{plan.revision_id}")

        if target.exists():
            raise BuildTargetExistsError(f"成果目标已存在：{target}")
        if not target.parent.is_dir():
            raise BuildTargetInvalidError(f"成果目录父目录不存在：{target.parent}")

        now = utc_now_iso()
        with self._require_database().sessions.begin() as session:
            repository = SqliteBuildRepository(session)
            existing = repository.latest_build_for_plan(plan_id)
            if existing is None:
                build_id = str(uuid.uuid4())
                attempt = 1
                repository.insert_build_run(
                    BuildRunRecord(
                        id=build_id,
                        plan_id=plan_id,
                        status=BuildStatus.QUEUED.value,
                        published_path=None,
                        created_at=now,
                        finished_at=None,
                    )
                )
            else:
                build_id = existing.id
                latest = repository.list_attempts(build_id)[-1]
                if BuildStatus(latest.status) not in TERMINAL_STATUSES:
                    raise BuildAlreadyRunningError(
                        f"构建仍有未终止 attempt：{build_id}#{latest.attempt}"
                    )
                attempt = latest.attempt + 1
                # 重试 attempt：run 状态从未终止的 FAILED/CANCELLED 复位为
                # QUEUED（finished_at 清空）。否则 (a) 重试的取消被终态 run
                # 误拒、(b) SSE 按过期终态提前收流、(c) 崩溃恢复漏掉非终态
                # attempt（含残留暂存）。
                repository.reset_run_for_new_attempt(
                    build_id, status=BuildStatus.QUEUED.value
                )
            repository.insert_attempt(
                BuildAttemptRecord(
                    build_id=build_id,
                    attempt=attempt,
                    status=BuildStatus.QUEUED.value,
                    progress=STAGE_PROGRESS[BuildStatus.QUEUED],
                    error_code=None,
                    error_detail=None,
                )
            )
            repository.append_event(
                event_record(build_id, attempt, BuildStatus.QUEUED, sequence=1, created_at=now)
            )
        # 快照计划与发布目标传入后台线程（§5：构建使用创建时快照）。
        self._executor.submit(self._run_build, build_id, attempt, plan, target)
        return self.get_build(build_id)

    def cancel_build(self, build_id: str) -> BuildStatusView:
        with self._require_database().sessions.begin() as session:
            repository = SqliteBuildRepository(session)
            run = repository.load_build_run(build_id)
            if run is None:
                raise BuildNotFoundError(f"构建不存在：{build_id}")
            latest = repository.list_attempts(build_id)[-1]
        if (
            BuildStatus(run.status) in TERMINAL_STATUSES
            or BuildStatus(latest.status) in TERMINAL_STATUSES
            or BuildStatus(latest.status) is BuildStatus.PUBLISHING
        ):
            raise CancelNotAcceptedError(f"构建状态 {latest.status} 不响应取消（§6）")
        self._cancel_flags.setdefault(
            (build_id, latest.attempt), threading.Event()
        ).set()
        return self.get_build(build_id)

    def get_build(self, build_id: str) -> BuildStatusView:
        with self._require_database().sessions.begin() as session:
            repository = SqliteBuildRepository(session)
            run = repository.load_build_run(build_id)
            if run is None:
                raise BuildNotFoundError(f"构建不存在：{build_id}")
            attempts = repository.list_attempts(build_id)
        latest = attempts[-1]
        return BuildStatusView(
            build_id=run.id,
            plan_id=run.plan_id,
            attempt=latest.attempt,
            status=latest.status,
            progress=latest.progress,
            error_code=latest.error_code,
            error_detail=latest.error_detail,
            published_path=run.published_path,
            created_at=run.created_at,
            finished_at=run.finished_at,
            attempts=tuple(
                AttemptView(
                    attempt=item.attempt,
                    status=item.status,
                    progress=item.progress,
                    error_code=item.error_code,
                )
                for item in attempts
            ),
        )

    # -- 交接（§10/§11）-----------------------------------------------------

    def handoff_to_manager(
        self,
        build_id: str,
        *,
        manager_base_url: str | None = None,
        transport: object | None = None,
    ) -> dict:
        """“一键交接”：显式调用本机 Manager 的 POST /api/handoffs/open。

        只对 SUCCEEDED 且已发布的构建发起；Manager 不可用时已发布成果包
        原样保留并抛 HANDOFF_UNAVAILABLE（带可执行恢复动作）。
        ``transport`` 是测试注入点（``(url, payload) -> (status, json)``）。
        """
        with self._require_database().sessions.begin() as session:
            run = SqliteBuildRepository(session).load_build_run(build_id)
        if run is None:
            raise BuildNotFoundError(f"构建不存在：{build_id}")
        if run.status != BuildStatus.SUCCEEDED.value or not run.published_path:
            raise HandoffNotPublishedError(f"构建尚未成功发布，无法交接：{build_id}")
        package = Path(run.published_path)
        handoff_path = package / "metadata" / "handoff.json"
        if not handoff_path.is_file():
            raise HandoffPackageMissingError(f"成果包缺少 metadata/handoff.json：{package}")

        base = (manager_base_url or manager_base_url_from_environ()).rstrip("/")
        post = transport if transport is not None else default_handoff_transport
        try:
            status, payload = post(f"{base}/api/handoffs/open", {"handoff_path": str(handoff_path)})
        except OSError as error:
            raise HandoffUnavailableError(str(handoff_path)) from error
        if status >= 400:
            code = payload.get("code") if isinstance(payload, dict) else None
            message = payload.get("message") if isinstance(payload, dict) else None
            raise HandoffRejectedError(
                code if isinstance(code, str) and code else "HANDOFF_INVALID",
                status if 400 <= status < 600 else 502,
                message if isinstance(message, str) and message else f"Manager 拒绝交接（HTTP {status}）",
            )
        if not isinstance(payload, dict):
            raise HandoffRejectedError("HANDOFF_INVALID", 502, "Manager 交接响应不是 JSON 对象")
        return payload

    # -- SSE（§6）-----------------------------------------------------------

    def ensure_build_exists(self, build_id: str) -> None:
        if self._load_build_run(build_id) is None:
            raise BuildNotFoundError(f"构建不存在：{build_id}")

    def stream_events(self, build_id: str, last_event_id: str | None) -> Iterator[str]:
        """SSE 事件流：按 (attempt, sequence) 重放 Last-Event-ID 之后的事件。

        断线不影响构建：流只读数据库，重连以 ``Last-Event-ID`` 续传。
        """

        def generator() -> Iterator[str]:
            position = parse_position(last_event_id)
            while True:
                run, events = self._load_run_and_events(build_id)
                if run is None:
                    return
                fresh = [
                    event
                    for event in events
                    if (event.attempt, event.sequence) > position
                ]
                for event in fresh:
                    position = (event.attempt, event.sequence)
                    yield format_sse(event)
                if BuildStatus(run.status) in TERMINAL_STATUSES and not fresh:
                    return
                time.sleep(SSE_POLL_SECONDS)

        return generator()

    # -- 后台流水线 ----------------------------------------------------------

    def _run_build(
        self,
        build_id: str,
        attempt: int,
        plan: GenerationPlanV1,
        target: Path,
    ) -> None:
        try:
            self._checkpoint(build_id, attempt)
            self._commit_transition(build_id, attempt, BuildStatus.PREPARING)
            dirs = create_attempt_dirs(self._project_root, build_id, attempt)

            self._checkpoint(build_id, attempt)
            self._commit_transition(build_id, attempt, BuildStatus.BUILDING_DWG)
            dwg_task = replace(
                plan.drawing_task,
                target_dwg_path=_built_dwg_relative(build_id, attempt),
            )
            cad_result = self._drawing_builder.build(
                dwg_task,
                AttemptPaths.create(dirs.work),
                cad_version=plan.cad_version,
            )
            # CAD 版本证据接线点：Task 7 修复后结果携带实际使用的版本。
            write_cad_evidence(
                dirs.metadata,
                {
                    "cad_version": cad_result.cad_version,
                    "layout_name": cad_result.layout_name,
                    "layout_handle": cad_result.layout_handle,
                    "dwg_size": cad_result.dwg_size,
                    "dwg_sha256": cad_result.dwg_sha256,
                },
            )

            self._checkpoint(build_id, attempt)
            self._commit_transition(build_id, attempt, BuildStatus.BUILDING_DST)
            dst_bytes = build_dst_bytes(plan, cad_result)
            catalog_bytes = build_sheet_catalog_xlsx(
                number=plan.sheetset_task.sheet_number,
                title=plan.sheetset_task.sheet_title,
                dwg=plan.sheetset_task.dwg_path,
                layout=plan.sheetset_task.layout_name,
            )

            self._checkpoint(build_id, attempt)
            self._commit_transition(build_id, attempt, BuildStatus.VERIFYING)
            ensure_dst_valid(dst_bytes, plan, cad_result)
            report = build_validation_report(
                plan=plan,
                cad_result=cad_result,
                dst_bytes=dst_bytes,
                catalog_bytes=catalog_bytes,
            )
            if report.blocking:
                raise DstValidationError(report.issues)
            candidate = assemble_package_files(
                plan=plan,
                dst_bytes=dst_bytes,
                dwg_bytes=(self._project_root / _built_dwg_relative(build_id, attempt)).read_bytes(),
                catalog_bytes=catalog_bytes,
            )
            for relative, content in candidate.items():
                destination = dirs.candidate / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)

            # PUBLISHING：最后取消检查点之后不再响应取消（§6）。
            self._checkpoint(build_id, attempt)
            self._commit_transition(build_id, attempt, BuildStatus.PUBLISHING)
            staging = target.parent / unique_staging_name(target)
            write_publish_evidence(
                dirs.metadata, target=target, staging=staging, expected_paths=tuple(candidate)
            )
            published = publish_candidate(candidate, target, staging=staging)
            self._commit_transition(
                build_id, attempt, BuildStatus.SUCCEEDED, artifact_path=str(published)
            )
        except _BuildCancelled:
            self._commit_transition(build_id, attempt, BuildStatus.CANCELLED)
        except BaseException as error:  # noqa: BLE001 - 任何异常都以 FAILED 终止 attempt
            self._fail(build_id, attempt, error)

    def _checkpoint(self, build_id: str, attempt: int) -> None:
        flag = self._cancel_flags.get((build_id, attempt))
        if flag is not None and flag.is_set():
            raise _BuildCancelled(build_id)

    def _fail(self, build_id: str, attempt: int, error: BaseException) -> None:
        code = getattr(error, "code", None)
        if not isinstance(code, str):
            code = BUILD_FAILED
        try:
            self._commit_transition(
                build_id,
                attempt,
                BuildStatus.FAILED,
                error_code=code,
                error_detail=str(error),
            )
        except (IllegalTransitionError, ValueError):
            # attempt 已终止（例如与恢复并发）；保留先到者，不覆盖历史。
            pass

    # -- 状态迁移与事件（同一事务，§6）----------------------------------------

    def _commit_transition(
        self,
        build_id: str,
        attempt: int,
        target: BuildStatus,
        *,
        error_code: str | None = None,
        error_detail: str | None = None,
        artifact_path: str | None = None,
    ) -> None:
        with self._require_database().sessions.begin() as session:
            repository = SqliteBuildRepository(session)
            attempts = repository.list_attempts(build_id)
            current = next(
                (item for item in attempts if item.attempt == attempt), None
            )
            if current is None:
                raise ValueError(f"构建 attempt 不存在：{build_id}#{attempt}")
            next_status = transition(BuildStatus(current.status), target)
            progress = STAGE_PROGRESS.get(target, current.progress)
            repository.update_attempt(
                build_id,
                attempt,
                status=next_status.value,
                progress=progress,
                error_code=error_code,
                error_detail=error_detail,
            )
            repository.append_event(
                event_record(
                    build_id,
                    attempt,
                    target,
                    sequence=next_sequence(repository.list_events(build_id, attempt)),
                    progress=progress,
                    error_code=error_code,
                    artifact_path=artifact_path,
                    created_at=utc_now_iso(),
                )
            )
            if target in TERMINAL_STATUSES:
                repository.update_build_run(
                    build_id,
                    status=target.value,
                    published_path=(
                        artifact_path if target is BuildStatus.SUCCEEDED else None
                    ),
                    finished_at=utc_now_iso(),
                )
                # 终态迁移即清除该 (build_id, attempt) 的取消标志（终审
                # Important ③）：CANCELLED/SUCCEEDED/FAILED 之后标志不可能
                # 再被检查点消费，留驻只会累积陈旧 Event。
                self._cancel_flags.pop((build_id, attempt), None)

    # -- 内部 ---------------------------------------------------------------

    def close(self) -> None:
        """关闭后台构建线程执行器（应用 lifespan shutdown 钩子调用，终审 Important ③）。"""
        self._executor.shutdown(wait=False)

    def _require_database(self) -> Database:
        if self._database is None:
            db_path = self._project_root / "project.dstb"
            if not db_path.is_file():
                raise ProjectNotInitializedError("项目库尚未创建")
            self._database = Database(db_path)
        return self._database

    def _load_frozen_inputs(self) -> tuple[object, tuple[AssetSnapshot, ...], Path]:
        """当前草稿 + 草稿引用的项目内资产快照 + 发布目标（§5 冻结输入）。"""
        with self._require_database().sessions.begin() as session:
            projects = SqliteProjectRepository(session)
            project = projects.load_project()
            if project is None:
                raise ProjectNotInitializedError("项目库缺少 projects 记录")
            draft_record = projects.load_draft(project.id)
            if draft_record is None:
                raise ProjectNotInitializedError("项目库缺少当前草稿记录")
            draft = draft_from_payload(json.loads(draft_record.payload_json))
            assets = SqliteAssetRepository(session)
            base = assets.load(draft.template.base_asset_id)
            layout = assets.load(draft.template.layout_asset_id)
        if base is None or layout is None:
            raise AssetNotFoundError("草稿引用的模板资产不存在，请重新纳入资产")
        snapshots = (
            AssetSnapshot(
                role=base.role,
                relative_path=base.relative_path,
                sha256=base.sha256,
                size=base.size,
            ),
            AssetSnapshot(
                role=layout.role,
                relative_path=layout.relative_path,
                sha256=layout.sha256,
                size=layout.size,
            ),
        )
        return draft, snapshots, Path(project.output_path)

    def _load_build_run(self, build_id: str) -> BuildRunRecord | None:
        with self._require_database().sessions.begin() as session:
            return SqliteBuildRepository(session).load_build_run(build_id)

    def _load_run_and_events(
        self, build_id: str
    ) -> tuple[BuildRunRecord | None, tuple[BuildEventRecord, ...]]:
        with self._require_database().sessions.begin() as session:
            repository = SqliteBuildRepository(session)
            run = repository.load_build_run(build_id)
            events = (
                repository.list_events_for_build(build_id) if run is not None else ()
            )
            return run, events
