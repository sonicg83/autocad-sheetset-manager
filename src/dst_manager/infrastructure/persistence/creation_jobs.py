"""创建任务针对标准库生命周期的窄查询。"""

from __future__ import annotations

import json

from sqlalchemy import select

from dst_manager.domain.standard_identity import parse_standard_id
from dst_manager.infrastructure.persistence.database import (
    TERMINAL_JOB_STATUSES,
    Database,
    JobRow,
)


def list_active_creation_jobs_for_standard(
    database: Database, standard_id: str
) -> tuple[str, ...]:
    """查询仍可能使用指定标准的创建任务，包含 QUEUED 状态。"""
    canonical_id = parse_standard_id(standard_id)
    with database.sessions() as session:
        rows = session.scalars(
            select(JobRow).where(
                JobRow.job_type == "creation",
                JobRow.status.not_in(TERMINAL_JOB_STATUSES),
            ),
        ).all()
        active_ids: list[str] = []
        for row in rows:
            try:
                payload = json.loads(row.payload_json)
                identity = payload.get("standard", {}).get("standard_id")
                if parse_standard_id(identity) == canonical_id:
                    active_ids.append(row.id)
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return tuple(sorted(active_ids))
