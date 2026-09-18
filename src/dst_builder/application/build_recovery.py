"""启动恢复（SPEC-DB-001 §6，PLAN-DB-001 Task 9）。

应用启动时把遗留在 QUEUED～VERIFYING 的 attempt 标为
``FAILED/BUILD_INTERRUPTED``（保留现场，不续跑半完成 CAD 命令）；``PUBLISHING``
遗留按 attempt 内发布证据裁决：

* 暂存存在且目标不存在 → 清理暂存并标记失败；
* 目标存在且通过 ``verify_target`` 校验 → 收敛为 SUCCEEDED；
* 其余歧义现场 → ``PUBLISH_RECOVERY_REQUIRED``，阻止自动删除。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from dst_builder.domain.build_state import BuildStatus
from dst_builder.domain.normalization import canonical_json
from dst_builder.infrastructure.filesystem.attempts import (
    PublishEvidenceError,
    attempt_dir_for,
    read_publish_evidence,
)
from dst_builder.infrastructure.filesystem.package import verify_target
from dst_builder.infrastructure.persistence.database import Database, utc_now_iso
from dst_builder.infrastructure.persistence.repositories import (
    BuildAttemptRecord,
    BuildEventRecord,
    SqliteBuildRepository,
)

__all__ = [
    "BUILD_INTERRUPTED",
    "PUBLISH_RECOVERY_REQUIRED",
    "RecoveryOutcome",
    "recover_pending_builds",
]

BUILD_INTERRUPTED = "BUILD_INTERRUPTED"
PUBLISH_RECOVERY_REQUIRED = "PUBLISH_RECOVERY_REQUIRED"

# 中断即失败的非 PUBLISHING 管线状态（QUEUED 视为从未开始执行）。
_INTERRUPTED_STATUSES = frozenset(
    {
        BuildStatus.QUEUED,
        BuildStatus.PREPARING,
        BuildStatus.BUILDING_DWG,
        BuildStatus.BUILDING_DST,
        BuildStatus.VERIFYING,
    }
)

_TERMINAL_STATUSES = frozenset(
    {BuildStatus.SUCCEEDED, BuildStatus.CANCELLED, BuildStatus.FAILED}
)


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    build_id: str
    attempt: int
    error_code: str | None
    note: str


@dataclass(frozen=True, slots=True)
class _RecoveryDecision:
    """事务外现场裁决结果：写回事务只消费该决定，绝不执行文件 I/O。"""

    error_code: str | None  # None = 收敛 SUCCEEDED；否则 FAILED + 该码
    error_detail: str  # 落库 error_detail（FAILED 分支）
    note: str  # RecoveryOutcome.note
    artifact_path: str | None = None  # 仅收敛 SUCCEEDED 时携带


def recover_pending_builds(
    project_root: Path, database: Database
) -> list[RecoveryOutcome]:
    """把所有非终止 build/attempt 恢复到确定终止状态；返回恢复结果。

    事务边界（终审 Important ②）：先用单个短事务读出待恢复项，随后在
    **事务外**执行文件现场裁决（读发布证据、verify_target 校验现场、
    清理暂存），最后每项用独立短事务写回结果——耗时文件 I/O 不再持有数据库写锁。
    四分支裁决语义与逐项文件操作顺序保持不变。
    """
    outcomes: list[RecoveryOutcome] = []
    root = Path(project_root)
    with database.sessions.begin() as session:
        repository = SqliteBuildRepository(session)
        pending: list[BuildAttemptRecord] = [
            repository.list_attempts(run.id)[-1]
            for run in repository.list_non_terminal_runs()
        ]
    for attempt in pending:
        decision = _adjudicate_attempt(root, attempt)
        if decision is None:
            continue
        with database.sessions.begin() as session:
            outcome = _apply_decision(
                SqliteBuildRepository(session), attempt.build_id, attempt, decision
            )
        outcomes.append(outcome)
    return outcomes


def _adjudicate_attempt(
    project_root: Path, attempt: BuildAttemptRecord
) -> _RecoveryDecision | None:
    """纯裁决：只读 attempt 记录与文件现场，不写库。"""
    status = BuildStatus(attempt.status)
    if status in _TERMINAL_STATUSES:
        return None
    if status in _INTERRUPTED_STATUSES:
        # PREPARING～VERIFYING 中断：保留现场，不续跑半完成 CAD 命令。
        return _RecoveryDecision(
            error_code=BUILD_INTERRUPTED,
            error_detail="构建被中断（启动恢复）",
            note=f"{status.value} 中断，现场已保留",
        )
    if status is BuildStatus.PUBLISHING:
        return _adjudicate_publishing(project_root, attempt)
    return None


def _adjudicate_publishing(
    project_root: Path, attempt: BuildAttemptRecord
) -> _RecoveryDecision:
    attempt_dir = attempt_dir_for(project_root, attempt.build_id, attempt.attempt)
    try:
        evidence = read_publish_evidence(attempt_dir)
    except PublishEvidenceError as error:
        # 歧义现场：无法裁决目标/暂存状态，阻止自动删除。
        return _RecoveryDecision(
            error_code=PUBLISH_RECOVERY_REQUIRED,
            error_detail=f"发布证据不可用：{error}",
            note=f"发布证据不可用：{error}",
        )

    target = evidence.target
    staging = evidence.staging
    staging_exists = staging.exists()
    target_exists = target.exists()

    if staging_exists and not target_exists:
        # 未改名：清理暂存并标记失败（attempt 现场保留）。
        shutil.rmtree(staging, ignore_errors=True)
        return _RecoveryDecision(
            error_code=BUILD_INTERRUPTED,
            error_detail="PUBLISHING 未改名：暂存已清理",
            note="PUBLISHING 未改名：暂存已清理，目标未创建",
        )

    if target_exists and not staging_exists:
        problems = verify_target(target, evidence.expected_paths)
        if not problems:
            # 已完整改名但状态未落库：收敛为成功。
            return _RecoveryDecision(
                error_code=None,
                error_detail="",
                note="PUBLISHING 已改名且成果完整：收敛为 SUCCEEDED",
                artifact_path=str(target),
            )
        return _RecoveryDecision(
            error_code=PUBLISH_RECOVERY_REQUIRED,
            error_detail=f"目标存在但不完整：{'；'.join(problems)}",
            note=f"目标存在但不完整：{'；'.join(problems)}",
        )

    # 目标与暂存并存（成功改名后暂存不应存在）等无法裁决的状态：歧义现场。
    return _RecoveryDecision(
        error_code=PUBLISH_RECOVERY_REQUIRED,
        error_detail="PUBLISHING 现场歧义，不自动删除",
        note="PUBLISHING 现场歧义，不自动删除",
    )


def _apply_decision(
    repository: SqliteBuildRepository,
    build_id: str,
    attempt: BuildAttemptRecord,
    decision: _RecoveryDecision,
) -> RecoveryOutcome:
    """把裁决结果写回（调用方独立短事务内）：仅数据库操作。"""
    if decision.error_code is None:
        _converge_succeeded(repository, build_id, attempt, decision.artifact_path or "")
    else:
        _fail_attempt(repository, build_id, attempt, decision.error_code, decision.error_detail)
    return RecoveryOutcome(
        build_id=build_id,
        attempt=attempt.attempt,
        error_code=decision.error_code,
        note=decision.note,
    )


def _fail_attempt(
    repository: SqliteBuildRepository,
    build_id: str,
    attempt: BuildAttemptRecord,
    error_code: str,
    detail: str,
) -> None:
    """恢复失败收敛：attempt/run 迁移 FAILED 并追加事件（调用方事务内）。"""
    now = utc_now_iso()
    repository.update_attempt(
        build_id,
        attempt.attempt,
        status=BuildStatus.FAILED.value,
        progress=attempt.progress,
        error_code=error_code,
        error_detail=detail,
    )
    repository.update_build_run(
        build_id,
        status=BuildStatus.FAILED.value,
        finished_at=now,
    )
    repository.append_event(
        _recovery_event(
            repository,
            build_id,
            attempt.attempt,
            BuildStatus.FAILED,
            progress=attempt.progress,
            error_code=error_code,
            created_at=now,
        )
    )


def _converge_succeeded(
    repository: SqliteBuildRepository,
    build_id: str,
    attempt: BuildAttemptRecord,
    published_path: str,
) -> None:
    """已完整改名：收敛为 SUCCEEDED（published_path 落库）。"""
    now = utc_now_iso()
    repository.update_attempt(
        build_id,
        attempt.attempt,
        status=BuildStatus.SUCCEEDED.value,
        progress=100,
        error_code=None,
        error_detail=None,
    )
    repository.update_build_run(
        build_id,
        status=BuildStatus.SUCCEEDED.value,
        published_path=published_path,
        finished_at=now,
    )
    repository.append_event(
        _recovery_event(
            repository,
            build_id,
            attempt.attempt,
            BuildStatus.SUCCEEDED,
            progress=100,
            artifact_path=published_path,
            created_at=now,
        )
    )


def _recovery_event(
    repository: SqliteBuildRepository,
    build_id: str,
    attempt: int,
    status: BuildStatus,
    *,
    progress: int,
    error_code: str | None = None,
    artifact_path: str | None = None,
    created_at: str,
) -> BuildEventRecord:
    events = repository.list_events(build_id, attempt)
    sequence = events[-1].sequence + 1 if events else 1
    payload = {
        "schema_version": 1,
        "sequence": sequence,
        "status": status.value,
        "progress": progress,
        "message_key": f"build.status.{status.value.lower()}",
        "artifact_path": artifact_path,
        "error_code": error_code,
        "created_at": created_at,
    }
    return BuildEventRecord(
        id=0,
        build_id=build_id,
        attempt=attempt,
        sequence=sequence,
        event_json=canonical_json(payload),
        created_at=created_at,
    )
