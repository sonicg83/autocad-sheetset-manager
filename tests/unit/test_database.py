import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dst_manager.infrastructure.persistence.database import (
    Database,
    InvalidJobTransitionError,
    WorkspaceBusyError,
)


def test_published_migrations_are_immutable():
    expected = {
        "0001_initial.py": "d19d09f9984eaa7bfe93932fb9971583f5c08bc28bed0c26a79b8f54af9df4f1",
        "0002_v02_job_reliability.py": "f318c1c9c0de34f23d6d41fe3677ebb38a51f2d528a3449ada4f6ff81f7a122c",
    }
    migration_root = Path("migrations/versions")
    actual = {
        name: hashlib.sha256((migration_root / name).read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest()
        for name in expected
    }
    assert actual == expected, "已发布 migration 不可原地修改；schema 变化必须新增 revision"


def test_workspace_allows_only_one_active_write_job(tmp_path: Path):
    database=Database(f"sqlite:///{(tmp_path/'db.sqlite').as_posix()}"); root=tmp_path/"project"; root.mkdir(); dst=root/"a.dst"; dst.write_bytes(b"x"); database.upsert_workspace("w",root,dst,"rev")
    database.create_job("job-1","w","change_set","QUEUED",{})
    with pytest.raises(WorkspaceBusyError): database.create_job("job-2","w","change_set","QUEUED",{})
    database.update_job("job-1","FAILED",0,"TEST")
    database.create_job("job-2","w","change_set","QUEUED",{})


def test_illegal_job_status_transition_is_rejected(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job("job", "w", "change_set", "QUEUED", {})
    with pytest.raises(InvalidJobTransitionError):
        database.update_job("job", "SUCCEEDED", 100)


def test_claim_is_atomic_and_records_lease(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job(
        "job-1",
        "w",
        "change_set",
        "QUEUED",
        {"plan": {"requires_cad": True}},
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(database.claim_next_job, ("worker-a", "worker-b")))
    claimed = [item for item in results if item]
    assert len(claimed) == 1
    assert claimed[0]["attempt"] == 1
    assert claimed[0]["worker_id"] in {"worker-a", "worker-b"}
    assert claimed[0]["heartbeat_at"]


def test_claim_allows_only_one_active_cad_job_across_workspaces(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    for index in (1, 2):
        workspace_id = f"w-{index}"
        database.upsert_workspace(workspace_id, tmp_path / workspace_id, tmp_path / f"{workspace_id}.dst", "r")
        database.create_job(
            f"job-{index}",
            workspace_id,
            "change_set",
            "QUEUED",
            {"plan": {"requires_cad": True}},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(database.claim_next_job, ("worker-a", "worker-b")))

    claimed = [item for item in results if item is not None]
    assert len(claimed) == 1
    first = claimed[0]
    queued_id = "job-2" if first["id"] == "job-1" else "job-1"
    assert database.get_job(queued_id)["status"] == "QUEUED"

    assert database.update_job(
        first["id"],
        "FAILED",
        0,
        "TEST_COMPLETE",
        worker_id=first["worker_id"],
        attempt=first["attempt"],
    ) is True
    second = database.claim_next_job("worker-c")
    assert second is not None and second["id"] == queued_id


def test_stale_safe_stage_requeues_and_publish_requires_review(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    old = datetime.now(UTC) - timedelta(minutes=10)
    for index, status in enumerate(("CAD_RUNNING", "PUBLISHING"), 1):
        workspace = f"w-{index}"
        database.upsert_workspace(workspace, tmp_path, tmp_path / f"{index}.dst", "r")
        database.create_job(
            f"job-{index}",
            workspace,
            "change_set",
            status,
            {"plan": {"requires_cad": True}},
        )
        with database.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE jobs SET heartbeat_at=? WHERE id=?", (old.replace(tzinfo=None), f"job-{index}"))
    conclusions = {item["id"]: item["conclusion"] for item in database.recover_stale_jobs(30)}
    assert conclusions == {"job-1": "REQUEUED_SAFE_STAGE", "job-2": "PUBLISH_JOURNAL_REVIEW_REQUIRED"}
    assert database.get_job("job-1")["status"] == "QUEUED"
    assert database.get_job("job-2")["status"] == "NEEDS_REVIEW"
    with pytest.raises(ValueError, match="JOB_NOT_RETRYABLE"):
        database.retry_job("job-2")


def test_stale_recovery_prevents_old_attempt_from_updating_new_owner(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job(
        "job",
        "w",
        "change_set",
        "QUEUED",
        {"plan": {"requires_cad": True}},
    )
    old = database.claim_next_job("old-worker")
    assert old is not None and old["attempt"] == 1
    stale_at = datetime.now(UTC) - timedelta(minutes=10)
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE jobs SET heartbeat_at=? WHERE id='job'",
            (stale_at.replace(tzinfo=None),),
        )
    assert database.recover_stale_jobs(30) == [{"id": "job", "conclusion": "REQUEUED_SAFE_STAGE"}]
    current = database.claim_next_job("new-worker")
    assert current is not None and current["attempt"] == 2

    assert database.heartbeat("job", "old-worker", attempt=1) is False
    assert database.update_job(
        "job",
        "FAILED",
        0,
        "OLD_WORKER_FAILURE",
        worker_id="old-worker",
        attempt=1,
    ) is False
    after_old_update = database.get_job("job")
    assert after_old_update is not None
    assert after_old_update["status"] == "STAGING"
    assert after_old_update["worker_id"] == "new-worker"
    assert after_old_update["attempt"] == 2


def test_finalize_committed_job_is_atomic_and_idempotent(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    root = tmp_path / "project"
    root.mkdir()
    dst = root / "a.dst"
    dst.write_bytes(b"result")
    database.upsert_workspace("w", root, dst, "before")
    database.create_job("job", "w", "change_set", "PUBLISHING", {"base_revision_id": "before"})

    for _ in range(2):
        database.finalize_committed_job(
            "result",
            "w",
            "job",
            "before",
            "result",
            root / ".dst-manager" / "revisions" / "job",
        )

    job = database.get_job("job")
    workspace = database.get_workspace("w")
    assert job is not None and job["status"] == "SUCCEEDED"
    assert sum(item["status"] == "SUCCEEDED" for item in job["timeline"]) == 1
    assert workspace is not None and workspace.current_revision == "result"
    assert [item["id"] for item in database.list_revisions("w")] == ["result"]
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_finalize_committed_job_rejects_lost_owner_before_writing_revision(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    root = tmp_path / "project"
    root.mkdir()
    dst = root / "a.dst"
    dst.write_bytes(b"result")
    database.upsert_workspace("w", root, dst, "before")
    database.create_job("job", "w", "change_set", "PUBLISHING", {"plan": {"requires_cad": True}})
    claimed = database.claim_next_job("worker")
    assert claimed is None

    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE jobs SET status='PUBLISHING', worker_id='worker', attempt=3 WHERE id='job'",
        )

    assert database.finalize_committed_job(
        "result",
        "w",
        "job",
        "before",
        "result",
        root / ".dst-manager" / "revisions" / "job",
        worker_id="old-worker",
        attempt=2,
    ) is False
    assert database.get_job("job")["status"] == "PUBLISHING"
    assert database.list_revisions("w") == []


def test_job_file_update_rejects_lost_owner(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job("job", "w", "change_set", "QUEUED", {"plan": {"requires_cad": True}})
    claimed = database.claim_next_job("new-worker")
    assert claimed is not None and claimed["attempt"] == 1
    target = tmp_path / "target.dwg"

    assert database.upsert_job_file(
        "job",
        target,
        worker_id="old-worker",
        attempt=0,
        status="SUCCEEDED",
        result_hash="old-result",
    ) is False
    assert database.get_job("job")["files"] == []


def test_finalize_committed_job_closes_crash_after_revision_insert_before_success(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    root = tmp_path / "project"
    root.mkdir()
    dst = root / "a.dst"
    dst.write_bytes(b"result")
    revision_dir = root / ".dst-manager" / "revisions" / "job"
    database.upsert_workspace("w", root, dst, "before")
    database.create_job("job", "w", "change_set", "PUBLISHING", {"base_revision_id": "before"})
    database.add_revision("result", "w", "job", "before", "result", revision_dir, update_current=False)

    database.finalize_committed_job("result", "w", "job", "before", "result", revision_dir)

    assert database.get_job("job")["status"] == "SUCCEEDED"
    assert database.get_workspace("w").current_revision == "result"
    assert len(database.list_revisions("w")) == 1
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_stale_revision_restore_is_never_requeued_as_cad_job_and_releases_lock(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job("restore", "w", "revision_restore", "STAGING", {"base_revision_id": "r"})
    old = datetime.now(UTC) - timedelta(minutes=10)
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE jobs SET heartbeat_at=? WHERE id='restore'",
            (old.replace(tzinfo=None),),
        )

    conclusions = database.recover_stale_jobs(30)

    assert conclusions == [{"id": "restore", "conclusion": "STATE_REVIEW_REQUIRED"}]
    assert database.get_job("restore")["status"] == "NEEDS_REVIEW"
    assert database.claim_next_job("cad-worker") is None
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_historical_queued_non_cad_jobs_are_quarantined_and_never_claimed(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job(
        "restore",
        "w",
        "revision_restore",
        "QUEUED",
        {"base_revision_id": "r"},
    )

    conclusions = database.recover_stale_jobs(30)

    assert conclusions == [{"id": "restore", "conclusion": "NON_CAD_QUEUE_QUARANTINED"}]
    assert database.claim_next_job("cad-worker") is None
    assert database.get_job("restore")["status"] == "NEEDS_REVIEW"
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_claim_next_job_rejects_queued_non_cad_change_set_even_without_startup_recovery(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    database.create_job(
        "metadata",
        "w",
        "change_set",
        "QUEUED",
        {"plan": {"requires_cad": False}},
    )

    assert database.claim_next_job("cad-worker") is None
    assert database.get_job("metadata")["status"] == "NEEDS_REVIEW"
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_existing_mvp_database_is_upgraded_by_alembic(tmp_path: Path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
        CREATE TABLE workspaces (id VARCHAR(36) PRIMARY KEY, root TEXT NOT NULL, dst_path TEXT NOT NULL, root_override TEXT, current_revision VARCHAR(64) NOT NULL, default_cad_version VARCHAR(4) NOT NULL, version INTEGER NOT NULL);
        CREATE TABLE document_revisions (id VARCHAR(64) PRIMARY KEY, workspace_id VARCHAR(36) NOT NULL, operation_id VARCHAR(36) NOT NULL, before_hash VARCHAR(64) NOT NULL, result_hash VARCHAR(64) NOT NULL, revision_dir TEXT NOT NULL, created_at DATETIME NOT NULL);
        CREATE TABLE change_sets (id VARCHAR(36) PRIMARY KEY, workspace_id VARCHAR(36) NOT NULL, base_revision VARCHAR(64) NOT NULL, commands_json TEXT NOT NULL, status VARCHAR(32) NOT NULL, validation_summary TEXT NOT NULL);
        CREATE TABLE jobs (id VARCHAR(36) PRIMARY KEY, workspace_id VARCHAR(36) NOT NULL, job_type VARCHAR(40) NOT NULL, cad_version VARCHAR(4), status VARCHAR(32) NOT NULL, progress INTEGER NOT NULL, payload_json TEXT NOT NULL, error_code VARCHAR(80), created_at DATETIME NOT NULL);
        CREATE TABLE job_files (id INTEGER PRIMARY KEY, job_id VARCHAR(36) NOT NULL, source_path TEXT, target_path TEXT NOT NULL, before_hash VARCHAR(64), result_hash VARCHAR(64), role VARCHAR(32) NOT NULL, result VARCHAR(32));
        CREATE TABLE diagnostics (id INTEGER PRIMARY KEY, job_id VARCHAR(36), workspace_id VARCHAR(36) NOT NULL, severity VARCHAR(16) NOT NULL, code VARCHAR(80) NOT NULL, object_id VARCHAR(64), location TEXT, message TEXT NOT NULL);
        CREATE TABLE templates (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, sha256 VARCHAR(64) NOT NULL, layouts_json TEXT NOT NULL, cad_version VARCHAR(4) NOT NULL);
        CREATE TABLE application_settings (key VARCHAR(100) PRIMARY KEY, value_json TEXT NOT NULL);
        CREATE TABLE workspace_write_locks (workspace_id VARCHAR(36) PRIMARY KEY, job_id VARCHAR(36) UNIQUE NOT NULL);
        """)
    database = Database(f"sqlite:///{path.as_posix()}")
    with database.engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(jobs)")}
        job_file_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(job_files)")}
        revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    assert {"worker_id", "attempt", "heartbeat_at", "finished_at"} <= columns
    assert {"cad_operation", "started_at", "finished_at"} <= job_file_columns
    assert revision == "0004_dm007_layout_name_cache"


def test_job_file_cad_operation_and_timing_are_returned_without_transformation(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("workspace", tmp_path, tmp_path / "set.dst", "revision")
    database.create_job("job", "workspace", "change_set", "QUEUED", {"plan": {"requires_cad": True}})
    target = tmp_path / "001 第一册.dwg"
    started = datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC)
    finished = datetime(2026, 8, 26, 1, 2, 4, tzinfo=UTC)

    database.upsert_job_file(
        "job",
        target,
        cad_operation="rename_only",
        started_at=started,
        finished_at=finished,
    )

    item = database.get_job("job")["files"][0]
    assert item["cad_operation"] == "rename_only"
    assert item["started_at"] == started.replace(tzinfo=None).isoformat()
    assert item["finished_at"] == finished.replace(tzinfo=None).isoformat()


def test_cad_duration_history_is_scoped_by_version_operation_and_success(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("workspace", tmp_path, tmp_path / "set.dst", "revision")
    samples = [12_000, 18_000, 24_000]
    for index, duration in enumerate(samples):
        job_id = f"job-{index}"
        database.create_job(
            job_id,
            "workspace",
            "change_set",
            "QUEUED",
            {"plan": {"requires_cad": True}},
            cad_version="2020",
        )
        database.upsert_job_file(
            job_id,
            tmp_path / f"{index}.dwg",
            cad_operation="rename_only",
            status="SUCCEEDED",
            duration_ms=duration,
        )
        database.update_job(job_id, "FAILED", 0, "TEST_COMPLETE")
    database.create_job(
        "ignored",
        "workspace",
        "change_set",
        "QUEUED",
        {"plan": {"requires_cad": True}},
        cad_version="2016",
    )
    database.upsert_job_file(
        "ignored",
        tmp_path / "ignored.dwg",
        cad_operation="rename_only",
        status="SUCCEEDED",
        duration_ms=99_000,
    )

    assert database.cad_duration_history("2020", "rename_only") == samples


def test_running_job_file_retry_clears_previous_terminal_state(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("workspace", tmp_path, tmp_path / "set.dst", "revision")
    database.create_job("job", "workspace", "change_set", "QUEUED", {"plan": {"requires_cad": True}})
    target = tmp_path / "001 第一册.dwg"
    database.upsert_job_file(
        "job",
        target,
        cad_operation="rename_only",
        status="FAILED",
        duration_ms=12,
        peak_memory_bytes=34,
        staging_bytes=56,
        result_hash="before",
        error_code="CAD_FAILED",
        error_detail="previous failure",
        finished_at=datetime.now(UTC),
    )

    database.upsert_job_file("job", target, cad_operation="rename_only", status="RUNNING", started_at=datetime.now(UTC))

    running = database.get_job("job")["files"][0]
    assert running["duration_ms"] is None
    assert running["peak_memory_bytes"] is None
    assert running["staging_bytes"] is None
    assert running["result_hash"] is None
    assert running["error_code"] is None
    assert running["error_detail"] is None
    assert running["finished_at"] is None

    database.upsert_job_file("job", target, status="SUCCEEDED", result_hash="after", finished_at=datetime.now(UTC))

    succeeded = database.get_job("job")["files"][0]
    assert succeeded["result_hash"] == "after"
    assert succeeded["error_code"] is None
    assert succeeded["error_detail"] is None


def test_retry_job_resets_all_job_file_attempt_state_atomically(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("workspace", tmp_path, tmp_path / "set.dst", "revision")
    database.create_job("job", "workspace", "change_set", "QUEUED", {"plan": {"requires_cad": True}})
    source = tmp_path / "source.dwg"
    target = tmp_path / "target.dwg"
    database.upsert_job_file(
        "job",
        target,
        source_path=str(source),
        cad_operation="rename_only",
        role="DWG",
        status="SUCCEEDED",
        progress=100,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=12,
        peak_memory_bytes=34,
        staging_bytes=56,
        log_path=str(tmp_path / "old.log"),
        before_hash="before",
        result_hash="after",
        result="WRITTEN",
        error_code="OLD_ERROR",
        error_detail="old detail",
    )
    database.update_job("job", "FAILED", 0, "CAD_FAILED")

    retried = database.retry_job("job")

    assert retried["status"] == "QUEUED"
    item = retried["files"][0]
    assert item["target_path"] == str(target)
    assert item["source_path"] == str(source)
    assert item["cad_operation"] == "rename_only"
    assert item["role"] == "DWG"
    assert item == item | {
        "status": "PENDING",
        "progress": 0,
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "peak_memory_bytes": None,
        "staging_bytes": None,
        "log_path": None,
        "before_hash": None,
        "result_hash": None,
        "error_code": None,
        "error_detail": None,
    }


def test_outdated_schema_is_rejected_when_migration_is_disabled(tmp_path: Path):
    path = tmp_path / "db.sqlite"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE alembic_version SET version_num='0001_initial'")
    with pytest.raises(RuntimeError, match="DATABASE_SCHEMA_INCOMPATIBLE.*alembic upgrade head"):
        Database(f"sqlite:///{path.as_posix()}", migrate=False)


@pytest.mark.parametrize(
    ("damage_sql", "missing"),
    [
        ("DROP TABLE job_events", "缺少表=job_events"),
        ("ALTER TABLE jobs DROP COLUMN error_detail", "缺少列=jobs.error_detail"),
    ],
)
def test_latest_revision_with_physical_schema_drift_is_rejected(tmp_path: Path, damage_sql: str, missing: str):
    path = tmp_path / "drift.sqlite"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute(damage_sql)

    with pytest.raises(RuntimeError, match=f"DATABASE_SCHEMA_DRIFT.*{missing}"):
        Database(f"sqlite:///{path.as_posix()}", migrate=False)


def test_fresh_upgrade_includes_layout_name_cache(tmp_path: Path):
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    with database.engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='layout_name_cache'"
        ).fetchall()
    assert rows, "layout_name_cache 表应存在"
