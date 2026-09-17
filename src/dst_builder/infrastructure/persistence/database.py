"""Builder 项目库（project.dstb，SQLite）的 ORM 模型、引擎与迁移入口。

``project.dstb`` 是 Builder 项目的唯一事实源（SPEC-DB-001 §3）：单库恰好一条
``projects`` 记录，数据库文件本体即项目库。时间戳一律以 RFC3339 UTC 字符串
（``sa.Text``）存储，保证 ``base_updated_at`` 乐观并发比较逐字稳定。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    BigInteger,
    Engine,
    ForeignKey,
    String,
    Text,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool

__all__ = [
    "BUILDER_TABLES",
    "LATEST_SCHEMA_REVISION",
    "PROJECT_DATABASE_NAME",
    "AssetRow",
    "Base",
    "BuildAttemptRow",
    "BuildEventRow",
    "BuildRunRow",
    "Database",
    "DatabaseSchemaError",
    "DraftRow",
    "GenerationPlanRow",
    "ProjectRevisionRow",
    "ProjectRow",
    "create_project_database",
    "project_database_path",
    "utc_now_iso",
]

LATEST_SCHEMA_REVISION = "0001_db001_initial"
PROJECT_DATABASE_NAME = "project.dstb"

BUILDER_TABLES = frozenset(
    {
        "projects",
        "drafts",
        "assets",
        "project_revisions",
        "generation_plans",
        "build_runs",
        "build_attempts",
        "build_events",
    }
)

_REPO_ROOT = Path(__file__).resolve().parents[4]


def utc_now_iso() -> str:
    """RFC3339 UTC 时间戳（保存/比较的唯一时间形态）。"""
    return datetime.now(UTC).isoformat()


def project_database_path(project_root: Path) -> Path:
    return project_root / PROJECT_DATABASE_NAME


class DatabaseSchemaError(RuntimeError):
    """项目库缺失、版本不匹配或表结构不可识别。"""


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    """§3 ``projects``：单库恰好一条（由 0001 迁移中的单例唯一索引强制）。"""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    discipline: Mapped[str] = mapped_column(Text, nullable=False)
    output_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DraftRow(Base):
    """§3 ``drafts``：当前草稿载荷、引导步骤与聚焦字段。"""

    __tablename__ = "drafts"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), primary_key=True
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    wizard_step: Mapped[int] = mapped_column(nullable=False)
    focused_field: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class AssetRow(Base):
    """§3 ``assets``：项目内内容寻址资产（(role, sha256) 唯一）。"""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)


class ProjectRevisionRow(Base):
    """§3 ``project_revisions``：不可变修订（内容不可更新，sha256 唯一）。"""

    __tablename__ = "project_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class GenerationPlanRow(Base):
    """§3 ``generation_plans``：引用固定修订的生成计划（内容不可更新）。"""

    __tablename__ = "generation_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_revisions.id"), nullable=False
    )
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class BuildRunRow(Base):
    """§3 ``build_runs``：一次构建运行，引用一个计划。"""

    __tablename__ = "build_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("generation_plans.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    published_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class BuildAttemptRow(Base):
    """§3 ``build_attempts``：(build_id, attempt) 唯一，历史不覆盖。"""

    __tablename__ = "build_attempts"

    build_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("build_runs.id"), primary_key=True
    )
    attempt: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress: Mapped[int] = mapped_column(nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class BuildEventRow(Base):
    """§3 ``build_events``：(build_id, attempt, sequence) 唯一。"""

    __tablename__ = "build_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    build_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("build_runs.id"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    event_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


def _alembic_config(db_path: Path) -> Config:
    config = Config(str(_REPO_ROOT / "builder_alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "builder_migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def create_project_database(db_path: Path) -> None:
    """从空文件创建 Schema 1 项目库（只承诺全新创建，不迁移历史库）。"""
    if db_path.exists():
        raise DatabaseSchemaError(f"项目库已存在：{db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(db_path), "head")


class Database:
    """项目库引擎与会话工厂；事务边界由调用方（application service）控制。"""

    def __init__(self, db_path: Path) -> None:
        if not db_path.is_file():
            raise DatabaseSchemaError(f"项目库不存在：{db_path}")
        self.db_path = db_path
        # NullPool：读路径不留驻连接，保证只读打开不遗留 -wal/-shm 文件。
        self.engine: Engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def check_schema(self) -> None:
        """校验迁移修订号与八张表齐全；不匹配即拒绝服务。"""
        with self.engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            missing = BUILDER_TABLES - tables
            if missing:
                raise DatabaseSchemaError(f"项目库缺少表：{sorted(missing)}")
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        if version != LATEST_SCHEMA_REVISION:
            raise DatabaseSchemaError(
                f"项目库 Schema 版本不兼容：当前={version}，需要={LATEST_SCHEMA_REVISION}"
            )
