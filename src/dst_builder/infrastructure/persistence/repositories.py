"""Builder 项目库仓储：Protocol 端口 + SQLite 适配器。

适配器只做行与记录的映射，不开事务、不 commit——事务边界由 application
service 通过 ``Database.sessions.begin()`` 控制。时间戳一律 RFC3339 UTC 字符串。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from dst_builder.infrastructure.persistence.database import (
    BuildAttemptRow,
    BuildEventRow,
    BuildRunRow,
    DraftRow,
    GenerationPlanRow,
    ProjectRevisionRow,
    ProjectRow,
)

__all__ = [
    "BuildAttemptRecord",
    "BuildEventRecord",
    "BuildRepository",
    "BuildRunRecord",
    "DraftRecord",
    "PlanRecord",
    "ProjectRecord",
    "ProjectRepository",
    "ProjectRowExistsError",
    "RevisionRecord",
    "RevisionRepository",
    "SqliteBuildRepository",
    "SqliteProjectRepository",
    "SqliteRevisionRepository",
]


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: str
    name: str
    stage: str
    discipline: str
    output_path: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class DraftRecord:
    project_id: str
    payload_json: str
    wizard_step: int
    focused_field: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    id: str
    canonical_json: str
    sha256: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PlanRecord:
    id: str
    revision_id: str
    canonical_json: str
    sha256: str
    confirmed_at: str | None


@dataclass(frozen=True, slots=True)
class BuildRunRecord:
    id: str
    plan_id: str
    status: str
    published_path: str | None
    created_at: str
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class BuildAttemptRecord:
    build_id: str
    attempt: int
    status: str
    progress: int
    error_code: str | None
    error_detail: str | None


@dataclass(frozen=True, slots=True)
class BuildEventRecord:
    id: int
    build_id: str
    attempt: int
    sequence: int
    event_json: str
    created_at: str


class ProjectRowExistsError(RuntimeError):
    """违反 §3「单库恰好一条 projects 记录」。"""


class ProjectRepository(Protocol):
    """项目聚合（projects + drafts）的持久化端口。"""

    def insert_project(self, record: ProjectRecord) -> None: ...

    def load_project(self) -> ProjectRecord | None: ...

    def insert_draft(self, record: DraftRecord) -> None: ...

    def load_draft(self, project_id: str) -> DraftRecord | None: ...

    def update_draft(
        self,
        project_id: str,
        *,
        expected_updated_at: str,
        payload_json: str,
        wizard_step: int,
        focused_field: str | None,
        updated_at: str,
    ) -> bool: ...


class RevisionRepository(Protocol):
    """不可变修订与生成计划的持久化端口（内容不可更新）。"""

    def insert_revision(self, record: RevisionRecord) -> None: ...

    def load_revision(self, revision_id: str) -> RevisionRecord | None: ...

    def insert_plan(self, record: PlanRecord) -> None: ...

    def load_plan(self, plan_id: str) -> PlanRecord | None: ...


class BuildRepository(Protocol):
    """构建运行、attempt 与事件的持久化端口（历史不覆盖）。"""

    def insert_build_run(self, record: BuildRunRecord) -> None: ...

    def load_build_run(self, build_id: str) -> BuildRunRecord | None: ...

    def insert_attempt(self, record: BuildAttemptRecord) -> None: ...

    def list_attempts(self, build_id: str) -> tuple[BuildAttemptRecord, ...]: ...

    def append_event(self, record: BuildEventRecord) -> None: ...

    def list_events(self, build_id: str, attempt: int) -> tuple[BuildEventRecord, ...]: ...


class SqliteProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_project(self, record: ProjectRecord) -> None:
        existing = self._session.get(ProjectRow, record.id)
        if existing is not None or self.load_project() is not None:
            raise ProjectRowExistsError("项目库已包含 projects 记录")
        self._session.add(
            ProjectRow(
                id=record.id,
                name=record.name,
                stage=record.stage,
                discipline=record.discipline,
                output_path=record.output_path,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )
        # 父行先落库：无 relationship 时 UOW 不保证跨 mapper 的插入顺序；
        # flush 只在调用方事务内发送 SQL，不提交事务。
        self._session.flush()

    def load_project(self) -> ProjectRecord | None:
        row = self._session.scalars(select(ProjectRow)).first()
        if row is None:
            return None
        return ProjectRecord(
            id=row.id,
            name=row.name,
            stage=row.stage,
            discipline=row.discipline,
            output_path=row.output_path,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def insert_draft(self, record: DraftRecord) -> None:
        self._session.add(
            DraftRow(
                project_id=record.project_id,
                payload_json=record.payload_json,
                wizard_step=record.wizard_step,
                focused_field=record.focused_field,
                updated_at=record.updated_at,
            )
        )

    def load_draft(self, project_id: str) -> DraftRecord | None:
        row = self._session.get(DraftRow, project_id)
        if row is None:
            return None
        return DraftRecord(
            project_id=row.project_id,
            payload_json=row.payload_json,
            wizard_step=row.wizard_step,
            focused_field=row.focused_field,
            updated_at=row.updated_at,
        )

    def update_draft(
        self,
        project_id: str,
        *,
        expected_updated_at: str,
        payload_json: str,
        wizard_step: int,
        focused_field: str | None,
        updated_at: str,
    ) -> bool:
        """乐观并发保存：``expected_updated_at`` 不匹配当前值时不写入。"""
        row = self._session.get(DraftRow, project_id)
        if row is None or row.updated_at != expected_updated_at:
            return False
        row.payload_json = payload_json
        row.wizard_step = wizard_step
        row.focused_field = focused_field
        row.updated_at = updated_at
        return True


class SqliteRevisionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_revision(self, record: RevisionRecord) -> None:
        self._session.add(
            ProjectRevisionRow(
                id=record.id,
                canonical_json=record.canonical_json,
                sha256=record.sha256,
                created_at=record.created_at,
            )
        )
        # 修订先于引用它的计划落库（同 insert_project 的说明）。
        self._session.flush()

    def load_revision(self, revision_id: str) -> RevisionRecord | None:
        row = self._session.get(ProjectRevisionRow, revision_id)
        if row is None:
            return None
        return RevisionRecord(
            id=row.id,
            canonical_json=row.canonical_json,
            sha256=row.sha256,
            created_at=row.created_at,
        )

    def insert_plan(self, record: PlanRecord) -> None:
        self._session.add(
            GenerationPlanRow(
                id=record.id,
                revision_id=record.revision_id,
                canonical_json=record.canonical_json,
                sha256=record.sha256,
                confirmed_at=record.confirmed_at,
            )
        )
        # 修订/计划按引用顺序落库（同 insert_project 的说明）。
        self._session.flush()

    def load_plan(self, plan_id: str) -> PlanRecord | None:
        row = self._session.get(GenerationPlanRow, plan_id)
        if row is None:
            return None
        return PlanRecord(
            id=row.id,
            revision_id=row.revision_id,
            canonical_json=row.canonical_json,
            sha256=row.sha256,
            confirmed_at=row.confirmed_at,
        )


class SqliteBuildRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_build_run(self, record: BuildRunRecord) -> None:
        self._session.add(
            BuildRunRow(
                id=record.id,
                plan_id=record.plan_id,
                status=record.status,
                published_path=record.published_path,
                created_at=record.created_at,
                finished_at=record.finished_at,
            )
        )
        self._session.flush()

    def load_build_run(self, build_id: str) -> BuildRunRecord | None:
        row = self._session.get(BuildRunRow, build_id)
        if row is None:
            return None
        return BuildRunRecord(
            id=row.id,
            plan_id=row.plan_id,
            status=row.status,
            published_path=row.published_path,
            created_at=row.created_at,
            finished_at=row.finished_at,
        )

    def insert_attempt(self, record: BuildAttemptRecord) -> None:
        self._session.add(
            BuildAttemptRow(
                build_id=record.build_id,
                attempt=record.attempt,
                status=record.status,
                progress=record.progress,
                error_code=record.error_code,
                error_detail=record.error_detail,
            )
        )

    def list_attempts(self, build_id: str) -> tuple[BuildAttemptRecord, ...]:
        rows = self._session.scalars(
            select(BuildAttemptRow)
            .where(BuildAttemptRow.build_id == build_id)
            .order_by(BuildAttemptRow.attempt)
        ).all()
        return tuple(
            BuildAttemptRecord(
                build_id=row.build_id,
                attempt=row.attempt,
                status=row.status,
                progress=row.progress,
                error_code=row.error_code,
                error_detail=row.error_detail,
            )
            for row in rows
        )

    def append_event(self, record: BuildEventRecord) -> None:
        self._session.add(
            BuildEventRow(
                id=record.id,
                build_id=record.build_id,
                attempt=record.attempt,
                sequence=record.sequence,
                event_json=record.event_json,
                created_at=record.created_at,
            )
        )

    def list_events(self, build_id: str, attempt: int) -> tuple[BuildEventRecord, ...]:
        rows = self._session.scalars(
            select(BuildEventRow)
            .where(BuildEventRow.build_id == build_id, BuildEventRow.attempt == attempt)
            .order_by(BuildEventRow.sequence)
        ).all()
        return tuple(
            BuildEventRecord(
                id=row.id,
                build_id=row.build_id,
                attempt=row.attempt,
                sequence=row.sequence,
                event_json=row.event_json,
                created_at=row.created_at,
            )
            for row in rows
        )
