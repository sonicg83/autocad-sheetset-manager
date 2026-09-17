"""Builder 项目库独立迁移链集成测试（SPEC-DB-001 §3 / PLAN-DB-001 Task 3）。

从空目录升级后断言八张表、唯一约束、迁移修订号与 Manager 表隔离。
Builder 使用独立 Alembic 配置（builder_alembic.ini + builder_migrations/），
不得复用或污染 Manager 的 migrations/。
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[3]

# SPEC-DB-001 §3 首版（Schema 1）八张表。
BUILDER_TABLES = {
    "projects",
    "drafts",
    "assets",
    "project_revisions",
    "generation_plans",
    "build_runs",
    "build_attempts",
    "build_events",
}

# Manager 应用数据库迁移链（migrations/0001..0006）建立的全部表；不得出现在 Builder 库。
MANAGER_TABLES = {
    "workspaces",
    "document_revisions",
    "change_sets",
    "jobs",
    "job_files",
    "job_events",
    "diagnostics",
    "templates",
    "application_settings",
    "workspace_write_locks",
    "layout_name_cache",
    "extension_states",
    "extension_settings",
    "workspace_extension_preferences",
    "artifacts",
}

# 迁移 0001 修订号固定为 0001_db001_initial（Task 3 裁决）。
LATEST_SCHEMA_REVISION = "0001_db001_initial"

EXPECTED_COLUMNS = {
    "projects": {
        "id",
        "name",
        "stage",
        "discipline",
        "output_path",
        "created_at",
        "updated_at",
    },
    "drafts": {"project_id", "payload_json", "wizard_step", "focused_field", "updated_at"},
    "assets": {"id", "role", "relative_path", "sha256", "size", "source_name"},
    "project_revisions": {"id", "canonical_json", "sha256", "created_at"},
    "generation_plans": {"id", "revision_id", "canonical_json", "sha256", "confirmed_at"},
    "build_runs": {
        "id",
        "plan_id",
        "status",
        "published_path",
        "created_at",
        "finished_at",
    },
    "build_attempts": {
        "build_id",
        "attempt",
        "status",
        "progress",
        "error_code",
        "error_detail",
    },
    "build_events": {
        "id",
        "build_id",
        "attempt",
        "sequence",
        "event_json",
        "created_at",
    },
}

# SPEC §3 唯一约束：(role, sha256)、修订 sha256 唯一、(build_id, attempt, sequence) 唯一。
EXPECTED_UNIQUE_CONSTRAINTS = {
    "assets": {frozenset({"role", "sha256"})},
    "project_revisions": {frozenset({"sha256"})},
    "build_events": {frozenset({"build_id", "attempt", "sequence"})},
}


def _upgrade_from_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """对任务专用临时空目录执行 builder 迁移链全新升级，返回 project.dstb 路径。"""
    monkeypatch.delenv("DST_BUILDER_DATABASE_URL", raising=False)
    db_path = tmp_path / "project.dstb"
    assert not db_path.exists()
    config = Config(str(REPO_ROOT / "builder_alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "builder_migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "head")
    return db_path


def test_upgrade_from_empty_directory_creates_spec_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """从空目录升级后：八张表齐全、Manager 表不出现、迁移修订号正确。"""
    db_path = _upgrade_from_empty(tmp_path, monkeypatch)

    assert db_path.is_file()
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert BUILDER_TABLES <= tables, f"缺少表：{sorted(BUILDER_TABLES - tables)}"
        assert not tables & MANAGER_TABLES, (
            f"出现 Manager 表：{sorted(tables & MANAGER_TABLES)}"
        )
        with engine.connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()
    assert version == LATEST_SCHEMA_REVISION


def test_upgraded_tables_carry_spec_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """每张表的字段集合与 SPEC-DB-001 §3 一致。"""
    db_path = _upgrade_from_empty(tmp_path, monkeypatch)
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        inspector = inspect(engine)
        for table_name, expected_columns in EXPECTED_COLUMNS.items():
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            assert actual == expected_columns, (
                f"{table_name} 字段不符：缺少 {sorted(expected_columns - actual)}，"
                f"多出 {sorted(actual - expected_columns)}"
            )
    finally:
        engine.dispose()


def test_upgraded_tables_carry_spec_unique_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """assets(role, sha256)、project_revisions(sha256)、build_events(build_id, attempt, sequence) 唯一。"""
    db_path = _upgrade_from_empty(tmp_path, monkeypatch)
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        inspector = inspect(engine)
        for table_name, expected in EXPECTED_UNIQUE_CONSTRAINTS.items():
            actual = {
                frozenset(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(table_name)
            }
            assert expected <= actual, (
                f"{table_name} 缺少唯一约束：{sorted(expected - actual)}"
            )
        pk = inspector.get_pk_constraint("build_attempts")
        assert set(pk["constrained_columns"]) == {"build_id", "attempt"}
    finally:
        engine.dispose()


def test_projects_table_rejects_second_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§3「单库恰好一条 projects 记录」在数据库层强制：第二条插入必须失败。"""
    db_path = _upgrade_from_empty(tmp_path, monkeypatch)
    engine = create_engine(f"sqlite:///{db_path}")
    from sqlalchemy.exc import IntegrityError

    insert = text(
        "INSERT INTO projects (id, name, stage, discipline, output_path, created_at, updated_at)"
        " VALUES (:id, :name, :stage, :discipline, :output_path, :created_at, :updated_at)"
    )
    row = {
        "name": "示例工程",
        "stage": "施工图",
        "discipline": "建筑",
        "output_path": "D:/deliveries/example-package",
        "created_at": "2026-09-17T00:00:00+00:00",
        "updated_at": "2026-09-17T00:00:00+00:00",
    }
    try:
        with engine.begin() as connection:
            connection.execute(insert, {"id": "11111111-1111-4111-8111-111111111111", **row})
        with (
            pytest.raises(IntegrityError),
            engine.begin() as connection,
        ):
            connection.execute(
                insert, {"id": "22222222-2222-4222-8222-222222222222", **row}
            )
    finally:
        engine.dispose()
