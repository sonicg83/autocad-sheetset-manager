"""Worker 配置热更新与任务级快照（PLAN-DM-019 任务 6，ARCH-DM-004 §2.4）。

覆盖要点：
- 认领时把 worker_lease_seconds 冻结进 jobs.lease_seconds 行快照；
- recover_stale_jobs 按行快照判定过期，调用方全局默认只兜底空值；
- 认领事件 detail 记录 cfg=r<config_revision>，可追溯任务实际配置；
- run_next_job 认领前 refresh_if_changed，任务级 timeout/parallel/lease/
  capability 全部取认领时快照——新任务新配置、已认领任务保持旧值。
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from dst_manager.application import service as service_module
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.persistence.database import Database
from dst_manager.settings.runtime import RuntimeSettings
from dst_manager.settings.store import UserSettingsStore


def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    return database


def _enqueue(database: Database, job_id: str) -> None:
    database.create_job(job_id, "w", "change_set", "QUEUED", {"plan": {"requires_cad": True}})


def _backdate_heartbeat(database: Database, job_id: str, seconds: int) -> None:
    stale = (datetime.now(UTC) - timedelta(seconds=seconds)).replace(tzinfo=None)
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE jobs SET heartbeat_at=? WHERE id=?",
            (stale, job_id),
        )


def _row_lease_seconds(database: Database, job_id: str) -> int | None:
    with database.engine.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT lease_seconds FROM jobs WHERE id=?", (job_id,)
        ).scalar_one()


def test_lease_snapshot_written_on_claim_and_used_by_recovery(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _enqueue(database, "job")
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save_overrides({"worker_lease_seconds": 60}, previous_revision=0)
    runtime = RuntimeSettings(store)

    claimed = database.claim_next_job(
        "worker-a", lease_seconds=runtime.current().settings.worker_lease_seconds
    )

    assert claimed is not None and claimed["id"] == "job"
    # 认领时冻结行快照
    assert _row_lease_seconds(database, "job") == 60
    # 行 lease=60、心跳 100 秒前：全局默认 120 会放过，按行快照必须回收
    _backdate_heartbeat(database, "job", seconds=100)
    recovered = database.recover_stale_jobs(lease_seconds=120)
    assert any(item["id"] == "job" for item in recovered)


def test_old_lease_row_not_reaped_after_global_lease_decreased(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _enqueue(database, "job")
    claimed = database.claim_next_job("worker-a", lease_seconds=120)
    assert claimed is not None
    _backdate_heartbeat(database, "job", seconds=100)

    # 行 lease=120、心跳 100 秒前：调用方全局 lease 已调小为 30，也不得误回收
    assert database.recover_stale_jobs(lease_seconds=30) == []


def test_claim_event_detail_records_config_revision(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _enqueue(database, "job-1")

    with_runtime = database.claim_next_job("worker-a", config_revision=7)
    assert with_runtime is not None
    assert with_runtime["timeline"][-1]["detail"] == "worker=worker-a cfg=r7"

    database.update_job(
        "job-1", "FAILED", 0, "TEST",
        worker_id=with_runtime["worker_id"], attempt=with_runtime["attempt"],
    )
    _enqueue(database, "job-2")
    without_runtime = database.claim_next_job("worker-b")
    assert without_runtime is not None
    # 无运行时快照的调用方保持既有 detail 格式，零行为变化
    assert without_runtime["timeline"][-1]["detail"] == "worker=worker-b"


class _RecordingRunner:
    """替身 CadJobRunner：只捕获认领时冻结的构造参数并落终态。"""

    instances: ClassVar[list["_RecordingRunner"]] = []

    def __init__(self, database, codec, publisher, timeout, max_parallel=4, heartbeat_interval=30.0):
        self.database = database
        self.timeout = timeout
        self.max_parallel = max_parallel
        self.heartbeat_interval = heartbeat_interval
        _RecordingRunner.instances.append(self)

    def run(self, job, workspace, capability) -> dict:
        return self.database.get_job(job["id"]) or {}


def test_run_next_job_uses_claim_time_snapshot_per_task(tmp_path: Path, monkeypatch) -> None:
    store = UserSettingsStore(tmp_path / "settings.json")
    store.save_overrides({"cad_timeout_seconds": 777, "worker_lease_seconds": 33}, previous_revision=0)
    runtime = RuntimeSettings(store)
    monkeypatch.setattr(service_module, "CadJobRunner", _RecordingRunner)
    _RecordingRunner.instances = []

    service = DstManagerService(Settings(data_dir=tmp_path / "data"), runtime_settings=runtime)
    service.database.upsert_workspace("w", tmp_path, tmp_path / "a.dst", "r")
    _enqueue(service.database, "job-1")
    service.get_workspace = lambda workspace_id: object()

    result = service.run_next_job()
    assert result is not None and result["id"] == "job-1"
    first = _RecordingRunner.instances[-1]
    assert first.timeout == 777
    assert first.heartbeat_interval == 11.0  # min(30, 33/3)
    assert _row_lease_seconds(service.database, "job-1") == 33
    assert service.database.get_job("job-1")["timeline"][-1]["detail"].endswith("cfg=r1")

    # 任务 1 已认领后修改配置：任务 2 必须用新配置（新任务新配置）
    claimed = service.database.get_job("job-1")
    service.database.update_job(
        "job-1", "FAILED", 0, "TEST",
        worker_id=claimed["worker_id"], attempt=claimed["attempt"],
    )
    store.save_overrides({"cad_timeout_seconds": 1234, "worker_lease_seconds": 90}, previous_revision=1)
    _enqueue(service.database, "job-2")

    result = service.run_next_job()
    assert result is not None and result["id"] == "job-2"
    second = _RecordingRunner.instances[-1]
    assert second.timeout == 1234
    assert second.heartbeat_interval == 30.0  # min(30, 90/3)
    assert _row_lease_seconds(service.database, "job-2") == 90
    assert service.database.get_job("job-2")["timeline"][-1]["detail"].endswith("cfg=r2")
