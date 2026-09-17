"""构建事件序列化与 SSE 重放工具（SPEC-DB-001 §6，PLAN-DB-001 Task 9）。

事件载荷（``BuildEventV1`` 语义）与状态迁移在同一事务内写入（由编排层调用
本模块构造记录）；SSE 流按 ``(attempt, sequence)`` 二元组定位续传位置，
``Last-Event-ID`` 形如 ``"<attempt>:<sequence>"``。
"""

from __future__ import annotations

from dst_builder.domain.build_state import BuildStatus
from dst_builder.domain.normalization import canonical_json
from dst_builder.infrastructure.persistence.repositories import BuildEventRecord

__all__ = [
    "SSE_POLL_SECONDS",
    "STAGE_PROGRESS",
    "TERMINAL_STATUSES",
    "event_record",
    "format_sse",
    "next_sequence",
    "parse_position",
]

# 终止状态（§6 迁移表的汇点）
TERMINAL_STATUSES = frozenset(
    {BuildStatus.SUCCEEDED, BuildStatus.CANCELLED, BuildStatus.FAILED}
)

# 阶段 → 事件进度（0～100，单调不减）
STAGE_PROGRESS: dict[BuildStatus, int] = {
    BuildStatus.QUEUED: 2,
    BuildStatus.PREPARING: 10,
    BuildStatus.BUILDING_DWG: 30,
    BuildStatus.BUILDING_DST: 55,
    BuildStatus.VERIFYING: 75,
    BuildStatus.PUBLISHING: 92,
    BuildStatus.SUCCEEDED: 100,
}

SSE_POLL_SECONDS = 0.1


def next_sequence(events: tuple[BuildEventRecord, ...]) -> int:
    """该 attempt 的下一个事件序号（sequence 从 1 起单调递增）。"""
    return events[-1].sequence + 1 if events else 1


def event_record(
    build_id: str,
    attempt: int,
    status: BuildStatus,
    *,
    sequence: int,
    progress: int | None = None,
    error_code: str | None = None,
    artifact_path: str | None = None,
    created_at: str,
) -> BuildEventRecord:
    """构造事件仓储记录；JSON 载荷为规范化字节序（键名排序）。"""
    resolved_progress = (
        STAGE_PROGRESS.get(status, 0) if progress is None else progress
    )
    payload = {
        "schema_version": 1,
        "sequence": sequence,
        "status": status.value,
        "progress": resolved_progress,
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


def format_sse(event: BuildEventRecord) -> str:
    """SSE 帧：``id`` 携带 ``(attempt, sequence)`` 位置，``data`` 为持久化载荷。"""
    return (
        f"id: {event.attempt}:{event.sequence}\n"
        f"event: build\n"
        f"data: {event.event_json}\n\n"
    )


def parse_position(last_event_id: str | None) -> tuple[int, int]:
    """``Last-Event-ID`` → ``(attempt, sequence)``；缺省或非法即从头重放。"""
    if not last_event_id:
        return (0, 0)
    try:
        attempt_text, _, sequence_text = last_event_id.partition(":")
        return (int(attempt_text), int(sequence_text))
    except ValueError:
        return (0, 0)
