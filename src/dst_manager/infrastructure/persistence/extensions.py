"""内置扩展持久化仓储（PLAN-DM-020 Task 2 / ARCH-DM-006 §7）。

四张表只服务扩展自身的状态、设置、工作区偏好与 Artifact 元数据；
授权（save grant）不在此持久化。:class:`ExtensionStore` 接收宿主现有的
session factory，不把 SQLAlchemy Session 暴露给扩展层。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

__all__ = [
    "ArtifactRecord",
    "ExtensionStateRecord",
    "ExtensionStore",
    "SettingsRevisionConflictError",
    "VersionedJson",
]


class ExtensionStateRow(Base):
    __tablename__ = "extension_states"
    extension_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
    last_loaded_version: Mapped[str | None] = mapped_column(String(32))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExtensionSettingRow(Base):
    __tablename__ = "extension_settings"
    extension_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    value_json: Mapped[dict[str, object]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkspaceExtensionPreferenceRow(Base):
    __tablename__ = "workspace_extension_preferences"
    workspace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extension_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    value_json: Mapped[dict[str, object]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    extension_id: Mapped[str] = mapped_column(String(120))
    extension_version: Mapped[str] = mapped_column(String(32))
    workspace_id: Mapped[str] = mapped_column(String(36))
    source_revision_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40))
    media_type: Mapped[str] = mapped_column(String(120))
    management_relation: Mapped[str] = mapped_column(String(16))
    output_path: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True, slots=True)
class VersionedJson:
    schema_version: int
    revision: int
    value: dict[str, object]


@dataclass(frozen=True, slots=True)
class ExtensionStateRecord:
    extension_id: str
    enabled: bool
    last_loaded_version: str | None
    last_error_code: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    extension_id: str
    extension_version: str
    workspace_id: str
    source_revision_id: str
    kind: str
    media_type: str
    management_relation: Literal["external"]
    output_path: str
    file_name: str
    size_bytes: int
    sha256: str
    created_at: datetime


class SettingsRevisionConflictError(RuntimeError):
    """设置乐观并发控制失败：expected_revision 与当前行修订不一致。"""


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ExtensionStore:
    """扩展状态、设置、偏好与 Artifact 元数据的仓储外观。"""

    def __init__(self, sessions) -> None:
        self._sessions = sessions

    # -- extension_states ---------------------------------------------------

    def get_state(self, extension_id: str) -> ExtensionStateRecord | None:
        with self._sessions() as session:
            row = session.get(ExtensionStateRow, extension_id)
            if row is None:
                return None
            return ExtensionStateRecord(
                extension_id=row.extension_id,
                enabled=row.enabled,
                last_loaded_version=row.last_loaded_version,
                last_error_code=row.last_error_code,
                updated_at=_as_utc(row.updated_at),
            )

    def put_state(self, record: ExtensionStateRecord) -> None:
        with self._sessions.begin() as session:
            row = session.get(ExtensionStateRow, record.extension_id)
            if row is None:
                session.add(
                    ExtensionStateRow(
                        extension_id=record.extension_id,
                        enabled=record.enabled,
                        last_loaded_version=record.last_loaded_version,
                        last_error_code=record.last_error_code,
                        updated_at=_as_utc(record.updated_at),
                    )
                )
            else:
                row.enabled = record.enabled
                row.last_loaded_version = record.last_loaded_version
                row.last_error_code = record.last_error_code
                row.updated_at = _as_utc(record.updated_at)

    # -- extension_settings -------------------------------------------------

    def get_settings(self, extension_id: str) -> VersionedJson | None:
        with self._sessions() as session:
            row = session.get(ExtensionSettingRow, extension_id)
            if row is None:
                return None
            return VersionedJson(
                schema_version=row.schema_version,
                revision=row.revision,
                value=dict(row.value_json),
            )

    def put_settings(
        self,
        extension_id: str,
        schema_version: int,
        value: dict[str, object],
        expected_revision: int,
    ) -> VersionedJson:
        """乐观并发写入：条件 UPDATE 以行数判定冲突，读-改-写不做窗口竞争。"""
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            updated = session.execute(
                update(ExtensionSettingRow)
                .where(
                    ExtensionSettingRow.extension_id == extension_id,
                    ExtensionSettingRow.revision == expected_revision,
                )
                .values(
                    schema_version=schema_version,
                    revision=expected_revision + 1,
                    value_json=value,
                    updated_at=now,
                )
            )
            if updated.rowcount == 1:
                return VersionedJson(
                    schema_version=schema_version,
                    revision=expected_revision + 1,
                    value=dict(value),
                )
            if expected_revision != 0:
                raise SettingsRevisionConflictError(
                    f"EXTENSION_SETTINGS_REVISION_CONFLICT: "
                    f"expected=r{expected_revision}"
                )
            # 首次写入：行不存在；并发抢先插入由主键约束判为冲突。
            session.add(
                ExtensionSettingRow(
                    extension_id=extension_id,
                    schema_version=schema_version,
                    revision=1,
                    value_json=value,
                    updated_at=now,
                )
            )
            try:
                session.flush()
            except IntegrityError as exc:
                raise SettingsRevisionConflictError(
                    "EXTENSION_SETTINGS_REVISION_CONFLICT: 首次写入被并发抢先"
                ) from exc
            return VersionedJson(
                schema_version=schema_version,
                revision=1,
                value=dict(value),
            )

    # -- workspace_extension_preferences ------------------------------------

    def get_preference(self, workspace_id: str, extension_id: str) -> VersionedJson | None:
        with self._sessions() as session:
            row = session.get(
                WorkspaceExtensionPreferenceRow,
                (workspace_id, extension_id),
            )
            if row is None:
                return None
            return VersionedJson(
                schema_version=row.schema_version,
                revision=row.revision,
                value=dict(row.value_json),
            )

    def put_preference(
        self,
        workspace_id: str,
        extension_id: str,
        schema_version: int,
        value: dict[str, object],
    ) -> VersionedJson:
        with self._sessions.begin() as session:
            row = session.get(
                WorkspaceExtensionPreferenceRow,
                (workspace_id, extension_id),
            )
            now = datetime.now(UTC)
            revision = row.revision + 1 if row is not None else 1
            if row is None:
                session.add(
                    WorkspaceExtensionPreferenceRow(
                        workspace_id=workspace_id,
                        extension_id=extension_id,
                        schema_version=schema_version,
                        revision=revision,
                        value_json=value,
                        updated_at=now,
                    )
                )
            else:
                row.schema_version = schema_version
                row.revision = revision
                row.value_json = value
                row.updated_at = now
            return VersionedJson(
                schema_version=schema_version,
                revision=revision,
                value=dict(value),
            )

    # -- artifacts -----------------------------------------------------------

    def create_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        if not (
            record.extension_id
            and record.extension_version
            and record.workspace_id
            and record.source_revision_id
        ):
            raise ValueError(
                "EXTENSION_ARTIFACT_SOURCE_INVALID: artifact 必填来源字段缺失"
            )
        if record.management_relation != "external":
            raise ValueError(
                f"EXTENSION_ARTIFACT_RELATION_INVALID: {record.management_relation!r}"
            )
        with self._sessions.begin() as session:
            session.add(
                ArtifactRow(
                    artifact_id=record.artifact_id,
                    extension_id=record.extension_id,
                    extension_version=record.extension_version,
                    workspace_id=record.workspace_id,
                    source_revision_id=record.source_revision_id,
                    kind=record.kind,
                    media_type=record.media_type,
                    management_relation=record.management_relation,
                    output_path=record.output_path,
                    file_name=record.file_name,
                    size_bytes=record.size_bytes,
                    sha256=record.sha256,
                    created_at=_as_utc(record.created_at),
                )
            )
        return record

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        with self._sessions() as session:
            row = session.get(ArtifactRow, artifact_id)
            if row is None:
                return None
            return ArtifactRecord(
                artifact_id=row.artifact_id,
                extension_id=row.extension_id,
                extension_version=row.extension_version,
                workspace_id=row.workspace_id,
                source_revision_id=row.source_revision_id,
                kind=row.kind,
                media_type=row.media_type,
                management_relation="external",
                output_path=row.output_path,
                file_name=row.file_name,
                size_bytes=row.size_bytes,
                sha256=row.sha256,
                created_at=_as_utc(row.created_at),
            )
