"""PLAN-DM-020 Task 2：扩展状态、设置、偏好与 Artifact 持久化。"""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from dst_manager.infrastructure.persistence.database import Database
from dst_manager.infrastructure.persistence.extensions import (
    ArtifactRecord,
    ExtensionStateRecord,
    ExtensionStore,
    SettingsRevisionConflictError,
    VersionedJson,
)
from dst_manager.runtime import resource_dir

NEW_EXTENSION_TABLES = {
    "extension_states",
    "extension_settings",
    "workspace_extension_preferences",
    "artifacts",
}
LATEST_REVISION = "0006_dm020_extension_platform"


def make_database(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")


def make_store(database: Database) -> ExtensionStore:
    return ExtensionStore(database.sessions)


def artifact_record(**overrides) -> ArtifactRecord:
    values = {
        "artifact_id": "artifact-1",
        "extension_id": "dst-manager.sheet-catalog",
        "extension_version": "0.1.0",
        "workspace_id": "workspace-1",
        "source_revision_id": "rev-1",
        "kind": "xlsx",
        "media_type": (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        "management_relation": "external",
        "output_path": "C:/out/图纸目录.xlsx",
        "file_name": "图纸目录.xlsx",
        "size_bytes": 2048,
        "sha256": "a" * 64,
        "created_at": datetime(2026, 9, 10, 8, 0, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return ArtifactRecord(**values)


# ---------------------------------------------------------------------------
# extension_states
# ---------------------------------------------------------------------------


def test_state_round_trip_and_upsert_keeps_single_row(tmp_path: Path):
    database = make_database(tmp_path)
    store = make_store(database)
    first = ExtensionStateRecord(
        extension_id="dst-manager.sheet-catalog",
        enabled=True,
        last_loaded_version="0.1.0",
        last_error_code=None,
        updated_at=datetime(2026, 9, 10, 8, 0, 0, tzinfo=UTC),
    )

    store.put_state(first)

    assert store.get_state("dst-manager.sheet-catalog") == first

    second = ExtensionStateRecord(
        extension_id="dst-manager.sheet-catalog",
        enabled=False,
        last_loaded_version="0.1.0",
        last_error_code="EXTENSION_START_FAILED",
        updated_at=datetime(2026, 9, 10, 9, 0, 0, tzinfo=UTC),
    )
    store.put_state(second)

    assert store.get_state("dst-manager.sheet-catalog") == second
    assert store.get_state("unknown") is None
    with database.engine.connect() as connection:
        count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM extension_states"
        ).scalar_one()
    assert count == 1


# ---------------------------------------------------------------------------
# extension_settings
# ---------------------------------------------------------------------------


def test_settings_json_round_trip(tmp_path: Path):
    database = make_database(tmp_path)
    store = make_store(database)
    value = {
        "templates": [{"path": "C:/t.xlsx", "layouts": ["封面", "正文"]}],
        "include_empty_sheets": False,
    }

    created = store.put_settings(
        "dst-manager.sheet-catalog",
        schema_version=1,
        value=value,
        expected_revision=0,
    )

    assert created == VersionedJson(schema_version=1, revision=1, value=value)
    assert store.get_settings("dst-manager.sheet-catalog") == created
    first_updated_at = read_updated_at(database, "extension_settings")
    assert first_updated_at is not None

    updated = store.put_settings(
        "dst-manager.sheet-catalog",
        schema_version=1,
        value={"templates": []},
        expected_revision=1,
    )
    assert updated.revision == 2
    assert store.get_settings("dst-manager.sheet-catalog") == updated
    assert read_updated_at(database, "extension_settings") >= first_updated_at


def read_updated_at(database: Database, table: str) -> str | None:
    with database.engine.connect() as connection:
        row = connection.exec_driver_sql(
            f"SELECT updated_at FROM {table}"
        ).fetchone()
    return None if row is None else row[0]


def test_concurrent_settings_writers_exactly_one_wins(tmp_path: Path):
    """两个写者从同一 expected_revision 竞争：条件更新保证恰一个成功。"""
    database = make_database(tmp_path)
    store = make_store(database)
    store.put_settings("ext-a", 1, {"v": "old"}, expected_revision=0)

    start = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def attempt(name: str, new_value: str) -> None:
        start.wait()
        try:
            result = store.put_settings("ext-a", 1, {"v": new_value}, expected_revision=1)
            outcomes[name] = result.value
        except SettingsRevisionConflictError:
            outcomes[name] = "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, "a", "first"), pool.submit(attempt, "b", "second")]
        for future in futures:
            future.result()

    winners = [value for value in outcomes.values() if value != "conflict"]
    assert len(winners) == 1
    final = store.get_settings("ext-a")
    assert final is not None
    assert final.revision == 2
    assert final.value == winners[0]


def test_settings_revision_conflict_rejects_and_keeps_old_value(tmp_path: Path):
    store = make_store(make_database(tmp_path))
    old_value = {"templates": ["keep"]}
    store.put_settings("ext-a", 1, old_value, expected_revision=0)

    with pytest.raises(SettingsRevisionConflictError):
        store.put_settings("ext-a", 1, {"templates": ["clobber"]}, expected_revision=0)

    current = store.get_settings("ext-a")
    assert current is not None
    assert current.revision == 1
    assert current.value == old_value


def test_settings_are_scoped_per_extension(tmp_path: Path):
    store = make_store(make_database(tmp_path))
    store.put_settings("ext-a", 1, {"owner": "a"}, expected_revision=0)
    store.put_settings("ext-b", 2, {"owner": "b"}, expected_revision=0)

    assert store.get_settings("ext-a").value == {"owner": "a"}
    assert store.get_settings("ext-a").schema_version == 1
    assert store.get_settings("ext-b").value == {"owner": "b"}
    assert store.get_settings("ext-b").schema_version == 2
    assert store.get_settings("unknown") is None


# ---------------------------------------------------------------------------
# workspace_extension_preferences
# ---------------------------------------------------------------------------


def test_preferences_are_isolated_by_workspace_and_extension(tmp_path: Path):
    store = make_store(make_database(tmp_path))

    w1_ext1 = store.put_preference("workspace-1", "ext-a", 1, {"sort": "number"})
    w1_ext2 = store.put_preference("workspace-1", "ext-b", 1, {"sort": "name"})
    w2_ext1 = store.put_preference("workspace-2", "ext-a", 1, {"sort": "path"})

    assert store.get_preference("workspace-1", "ext-a") == w1_ext1
    assert store.get_preference("workspace-1", "ext-b") == w1_ext2
    assert store.get_preference("workspace-2", "ext-a") == w2_ext1
    assert store.get_preference("workspace-2", "ext-b") is None


def test_preference_upsert_keeps_single_row_and_bumps_revision(tmp_path: Path):
    database = make_database(tmp_path)
    store = make_store(database)
    store.put_preference("workspace-1", "ext-a", 1, {"sort": "number"})
    updated = store.put_preference("workspace-1", "ext-a", 1, {"sort": "name"})

    assert updated.revision == 2
    assert updated.value == {"sort": "name"}
    assert store.get_preference("workspace-1", "ext-a") == updated
    with database.engine.connect() as connection:
        count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM workspace_extension_preferences"
        ).scalar_one()
    assert count == 1
    assert read_updated_at(database, "workspace_extension_preferences") is not None


# ---------------------------------------------------------------------------
# artifacts
# ---------------------------------------------------------------------------


def test_artifact_round_trip(tmp_path: Path):
    store = make_store(make_database(tmp_path))
    record = artifact_record()

    stored = store.create_artifact(record)

    assert stored == record
    assert store.get_artifact("artifact-1") == record
    assert store.get_artifact("missing") is None


@pytest.mark.parametrize(
    "field",
    ["extension_id", "extension_version", "workspace_id", "source_revision_id"],
)
def test_artifact_requires_source_fields(tmp_path: Path, field: str):
    database = make_database(tmp_path)
    store = make_store(database)
    record = artifact_record(**{field: ""})

    with pytest.raises(ValueError, match="EXTENSION_ARTIFACT_SOURCE_INVALID"):
        store.create_artifact(record)

    assert store.get_artifact("artifact-1") is None
    with database.engine.connect() as connection:
        count = connection.exec_driver_sql("SELECT COUNT(*) FROM artifacts").scalar_one()
    assert count == 0


@pytest.mark.parametrize("relation", ["inline", "", "EXTERNAL"])
def test_artifact_management_relation_only_allows_external(tmp_path: Path, relation: str):
    database = make_database(tmp_path)
    store = make_store(database)

    with pytest.raises(ValueError, match="EXTENSION_ARTIFACT_RELATION_INVALID"):
        store.create_artifact(artifact_record(management_relation=relation))

    with database.engine.connect() as connection:
        count = connection.exec_driver_sql("SELECT COUNT(*) FROM artifacts").scalar_one()
    assert count == 0


def test_duplicate_artifact_id_is_rejected(tmp_path: Path):
    store = make_store(make_database(tmp_path))
    store.create_artifact(artifact_record())

    with pytest.raises(IntegrityError):
        store.create_artifact(artifact_record(output_path="C:/other.xlsx"))


def test_deleting_extension_settings_does_not_delete_artifacts(tmp_path: Path):
    """模板存于 extension_settings 的 JSON；删除后历史 Artifact 必须保留。"""
    database = make_database(tmp_path)
    store = ExtensionStore(database.sessions)
    store.put_settings(
        "dst-manager.sheet-catalog",
        1,
        {"templates": [{"path": "C:/t.xlsx"}]},
        expected_revision=0,
    )
    store.create_artifact(artifact_record())

    with database.engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM extension_settings")

    assert store.get_settings("dst-manager.sheet-catalog") is None
    assert store.get_artifact("artifact-1") is not None
    with database.engine.connect() as connection:
        count = connection.exec_driver_sql("SELECT COUNT(*) FROM artifacts").scalar_one()
        foreign_keys = connection.exec_driver_sql(
            "PRAGMA foreign_key_list(artifacts)"
        ).fetchall()
    assert count == 1
    assert foreign_keys == [], "artifacts 不得外键级联到设置/状态表"


# ---------------------------------------------------------------------------
# schema / migration
# ---------------------------------------------------------------------------


def test_extension_tables_declare_expected_primary_keys(tmp_path: Path):
    database = make_database(tmp_path)
    with database.engine.connect() as connection:
        primary_keys = {}
        for table in NEW_EXTENSION_TABLES:
            rows = connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            primary_keys[table] = [
                row[1] for row in rows if row[5]
            ]
    assert primary_keys == {
        "extension_states": ["extension_id"],
        "extension_settings": ["extension_id"],
        "workspace_extension_preferences": ["workspace_id", "extension_id"],
        "artifacts": ["artifact_id"],
    }


def test_empty_database_upgrades_to_extension_platform(tmp_path: Path):
    database = make_database(tmp_path)
    with database.engine.connect() as connection:
        revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        tables = {row[0] for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert revision == LATEST_REVISION
    assert NEW_EXTENSION_TABLES <= tables


def test_database_at_0005_upgrades_to_extension_platform(tmp_path: Path):
    path = tmp_path / "existing.sqlite"
    url = f"sqlite:///{path.as_posix()}"

    def alembic_config() -> Config:
        config = Config(str(resource_dir() / "alembic.ini"))
        config.set_main_option("script_location", str(resource_dir() / "migrations"))
        config.set_main_option("sqlalchemy.url", url)
        return config

    command.upgrade(alembic_config(), "0005_dm019_job_lease_seconds")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, root, dst_path, current_revision,"
            " default_cad_version, version) VALUES"
            " ('w', 'C:/root', 'C:/root/a.dst', 'rev', '2020', 1)"
        )

    command.upgrade(alembic_config(), "head")

    with sqlite3.connect(path) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        remaining = connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
    assert revision == LATEST_REVISION
    assert NEW_EXTENSION_TABLES <= tables
    assert remaining == 1
