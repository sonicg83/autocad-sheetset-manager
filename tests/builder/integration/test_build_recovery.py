"""启动恢复集成测试（SPEC-DB-001 §6 / PLAN-DB-001 Task 9）。

覆盖：PREPARING～VERIFYING 中断保留现场并标记 FAILED/BUILD_INTERRUPTED、
QUEUED 遗留、PUBLISHING 未改名（清理暂存标记失败）、已完整改名（收敛
SUCCEEDED）、歧义现场（PUBLISH_RECOVERY_REQUIRED，不自动删除），以及
应用启动时的自动恢复。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dst_builder.application.build_recovery import (
    BUILD_INTERRUPTED,
    PUBLISH_RECOVERY_REQUIRED,
    recover_pending_builds,
)
from dst_builder.infrastructure.filesystem import package as package_module
from dst_builder.infrastructure.persistence.database import Database
from dst_builder.infrastructure.persistence.repositories import (
    BuildAttemptRecord,
    BuildEventRecord,
    BuildRunRecord,
    SqliteBuildRepository,
    SqliteProjectRepository,
)
from dst_builder.interfaces.api import create_builder_app

NOW = "2026-09-17T00:00:00+00:00"


@pytest.fixture
def recovery(tmp_path: Path):
    """已初始化的项目库 + 一条已确认计划，用于直接构造 build 行与现场。"""
    project_root = tmp_path / "project"
    client = TestClient(create_builder_app(project_root))
    response = client.post(
        "/api/projects",
        json={
            "project_root": str(project_root),
            "name": "示例工程",
            "stage": "施工图",
            "discipline": "建筑",
            "output_path": str(tmp_path / "example-package"),
        },
    )
    assert response.status_code == 201

    base_source = tmp_path / "base.dwg"
    base_source.write_bytes(b"fake base dwg")
    layout_source = tmp_path / "layout.dwt"
    layout_source.write_bytes(b"fake layout")
    base_asset = client.post(
        "/api/assets", json={"role": "base", "source_path": str(base_source)}
    ).json()
    layout_asset = client.post(
        "/api/assets", json={"role": "layout", "source_path": str(layout_source)}
    ).json()


    state = client.get("/api/projects/current").json()
    draft = state["draft"]
    draft["project"]["output_path"] = str(tmp_path / "example-package")
    draft["numbering"] = {"prefix": "A-", "start": 1, "width": 3}
    draft["sheets"] = [{"title": "首层平面图"}]
    draft["template"]["base_asset_id"] = base_asset["id"]
    draft["template"]["layout_asset_id"] = layout_asset["id"]
    draft["template"]["source_layout"] = "A1"
    patched = client.patch(
        "/api/projects/current/draft",
        json={"base_updated_at": state["updated_at"], "draft": draft, "wizard_step": 4},
    )
    assert patched.status_code == 200, patched.text
    plan_id = client.post("/api/plans").json()["plan_id"]
    confirmed = client.post(f"/api/plans/{plan_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text

    database = Database(project_root / "project.dstb")
    database.check_schema()
    with database.sessions.begin() as session:
        project = SqliteProjectRepository(session).load_project()
    assert project is not None

    def add_build(status: str, attempt_status: str, *, attempt: int = 1, error_code: str | None = None):
        build_id = str(uuid.uuid4())
        with database.sessions.begin() as session:
            repo = SqliteBuildRepository(session)
            repo.insert_build_run(
                BuildRunRecord(
                    id=build_id, plan_id=plan_id, status=status,
                    published_path=None, created_at=NOW, finished_at=None,
                )
            )
            repo.insert_attempt(
                BuildAttemptRecord(
                    build_id=build_id, attempt=attempt, status=attempt_status,
                    progress=50, error_code=error_code, error_detail=None,
                )
            )
            repo.append_event(
                BuildEventRecord(
                    id=0, build_id=build_id, attempt=attempt, sequence=1,
                    event_json=json.dumps({"sequence": 1, "status": attempt_status}),
                    created_at=NOW,
                )
            )
        return build_id

    return Simple(
        tmp_path=tmp_path, project_root=project_root, database=database,
        output_target=tmp_path / "example-package", add_build=add_build,
        build_dir=project_root / "builds", plan_id=plan_id,
    )


class Simple:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def _seed_attempt_dirs(recovery, build_id: str, attempt: int = 1) -> Path:
    """创建保留现场的 attempt 目录结构（input/work/logs/metadata/candidate）。"""
    attempt_dir = recovery.build_dir / build_id / f"attempt-{attempt:03d}"
    for name in ("input", "work", "logs", "metadata", "candidate"):
        (attempt_dir / name).mkdir(parents=True, exist_ok=True)
    (attempt_dir / "work" / "working.dwg").write_bytes(b"leftover work copy")
    return attempt_dir


def _seed_publish_evidence(attempt_dir: Path, target: Path, staging: Path) -> None:
    (attempt_dir / "metadata" / "publish-target.json").write_text(
        json.dumps(
            {"target": str(target), "staging": str(staging), "recorded_at": NOW}
        ),
        encoding="utf-8",
    )


def _write_valid_package(target: Path) -> None:
    """在 target 写一个可通过 manifest 校验的完整成果包。"""
    from dst_builder.infrastructure.filesystem.publisher import publish_candidate

    plan = _minimal_package_files()
    publish_candidate(plan, target, staging=target.parent / f".staging-{uuid.uuid4().hex[:8]}")


def _minimal_package_files() -> dict[str, bytes]:
    files = {
        "drawings/sheetset.dst": b"dst",
        "drawings/A-001 平面.dwg": b"dwg",
        "drawings/图纸目录.xlsx": b"xlsx",
        "metadata/project-revision.json": b"rev",
        "metadata/generation-plan.json": b"plan",
        "metadata/validation-report.json": b"report",
    }
    manifest_bytes = package_module.build_manifest_bytes(
        files, {path: "role" for path in files}
    )
    files[package_module.MANIFEST_FILE] = manifest_bytes
    return files


# ---------------------------------------------------------------------------
# PREPARING～VERIFYING 中断
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["QUEUED", "PREPARING", "BUILDING_DWG", "BUILDING_DST", "VERIFYING"])
def test_interrupted_attempts_fail_with_build_interrupted(recovery, status: str) -> None:
    build_id = recovery.add_build(status, status)
    attempt_dir = _seed_attempt_dirs(recovery, build_id)

    outcomes = recover_pending_builds(recovery.project_root, recovery.database)

    assert outcomes, "至少恢复一个 build"
    with recovery.database.sessions.begin() as session:
        repo = SqliteBuildRepository(session)
        run = repo.load_build_run(build_id)
        attempts = repo.list_attempts(build_id)
    assert run is not None and run.status == "FAILED" and run.finished_at
    assert attempts[-1].status == "FAILED"
    assert attempts[-1].error_code == BUILD_INTERRUPTED
    # 保留现场：attempt 目录与内容不被清理
    assert (attempt_dir / "work" / "working.dwg").is_file()


def test_recovery_finds_retry_attempt_of_stale_run(recovery) -> None:
    """Important 回归：重试 attempt 的 run 状态已复位，恢复不得漏掉 attempt 2。"""
    build_id = str(uuid.uuid4())
    with recovery.database.sessions.begin() as session:
        repo = SqliteBuildRepository(session)
        # run 复位为 QUEUED（start_build 创建 attempt 2 时的形态），
        # attempt 1 已 FAILED，attempt 2 卡在 PUBLISHING 且残留暂存。
        repo.insert_build_run(
            BuildRunRecord(
                id=build_id, plan_id=recovery.plan_id, status="QUEUED",
                published_path=None, created_at=NOW, finished_at=None,
            )
        )
        repo.insert_attempt(
            BuildAttemptRecord(
                build_id=build_id, attempt=1, status="FAILED",
                progress=30, error_code="CAD_EXECUTION_FAILED", error_detail=None,
            )
        )
        repo.insert_attempt(
            BuildAttemptRecord(
                build_id=build_id, attempt=2, status="PUBLISHING",
                progress=92, error_code=None, error_detail=None,
            )
        )
    attempt_dir = _seed_attempt_dirs(recovery, build_id, attempt=2)
    staging = recovery.output_target.parent / f".dstb-staging-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True)
    (staging / "drawings").mkdir()
    (staging / "drawings" / "sheetset.dst").write_bytes(b"partial")
    _seed_publish_evidence(attempt_dir, recovery.output_target, staging)

    outcomes = recover_pending_builds(recovery.project_root, recovery.database)

    assert [outcome.attempt for outcome in outcomes] == [2]
    assert outcomes[0].error_code == BUILD_INTERRUPTED
    assert not staging.exists(), "attempt 2 的暂存目录必须被清理"
    assert not recovery.output_target.exists()
    with recovery.database.sessions.begin() as session:
        repo = SqliteBuildRepository(session)
        attempts = repo.list_attempts(build_id)
    assert [item.status for item in attempts] == ["FAILED", "FAILED"]
    assert attempts[-1].error_code == BUILD_INTERRUPTED


# ---------------------------------------------------------------------------
# PUBLISHING 恢复分支
# ---------------------------------------------------------------------------


def test_publishing_with_staging_and_no_target_cleans_staging_and_fails(recovery) -> None:
    build_id = recovery.add_build("PUBLISHING", "PUBLISHING")
    attempt_dir = _seed_attempt_dirs(recovery, build_id)
    staging = recovery.output_target.parent / f".dstb-staging-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True)
    (staging / "drawings").mkdir()
    (staging / "drawings" / "sheetset.dst").write_bytes(b"partial")
    _seed_publish_evidence(attempt_dir, recovery.output_target, staging)

    recover_pending_builds(recovery.project_root, recovery.database)

    assert not staging.exists(), "暂存目录必须被清理"
    assert not recovery.output_target.exists()
    with recovery.database.sessions.begin() as session:
        run = SqliteBuildRepository(session).load_build_run(build_id)
        attempts = SqliteBuildRepository(session).list_attempts(build_id)
    assert run.status == "FAILED"
    assert attempts[-1].error_code == BUILD_INTERRUPTED


def test_publishing_with_complete_target_converges_to_succeeded(recovery) -> None:
    build_id = recovery.add_build("PUBLISHING", "PUBLISHING")
    attempt_dir = _seed_attempt_dirs(recovery, build_id)
    _write_valid_package(recovery.output_target)
    _seed_publish_evidence(attempt_dir, recovery.output_target, recovery.output_target.parent / ".gone-staging")

    recover_pending_builds(recovery.project_root, recovery.database)

    with recovery.database.sessions.begin() as session:
        run = SqliteBuildRepository(session).load_build_run(build_id)
        attempts = SqliteBuildRepository(session).list_attempts(build_id)
    assert run.status == "SUCCEEDED"
    assert run.published_path == str(recovery.output_target)
    assert attempts[-1].status == "SUCCEEDED"
    assert recovery.output_target.is_dir(), "成果不得被删除"


def test_publishing_with_tampered_target_requires_manual_recovery(recovery) -> None:
    build_id = recovery.add_build("PUBLISHING", "PUBLISHING")
    attempt_dir = _seed_attempt_dirs(recovery, build_id)
    _write_valid_package(recovery.output_target)
    (recovery.output_target / "drawings" / "sheetset.dst").write_bytes(b"tampered")
    _seed_publish_evidence(attempt_dir, recovery.output_target, recovery.output_target.parent / ".gone-staging")

    recover_pending_builds(recovery.project_root, recovery.database)

    with recovery.database.sessions.begin() as session:
        run = SqliteBuildRepository(session).load_build_run(build_id)
        attempts = SqliteBuildRepository(session).list_attempts(build_id)
    assert run.status == "FAILED"
    assert attempts[-1].error_code == PUBLISH_RECOVERY_REQUIRED
    # 歧义现场不被自动删除
    assert recovery.output_target.is_dir()


def test_publishing_with_both_staging_and_target_requires_manual_recovery(recovery) -> None:
    build_id = recovery.add_build("PUBLISHING", "PUBLISHING")
    attempt_dir = _seed_attempt_dirs(recovery, build_id)
    staging = recovery.output_target.parent / f".dstb-staging-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True)
    _write_valid_package(recovery.output_target)
    _seed_publish_evidence(attempt_dir, recovery.output_target, staging)

    recover_pending_builds(recovery.project_root, recovery.database)

    with recovery.database.sessions.begin() as session:
        run = SqliteBuildRepository(session).load_build_run(build_id)
        attempts = SqliteBuildRepository(session).list_attempts(build_id)
    assert attempts[-1].error_code == PUBLISH_RECOVERY_REQUIRED
    assert run.status == "FAILED"
    # 现场保留
    assert staging.exists() and recovery.output_target.is_dir()


def test_publishing_without_evidence_requires_manual_recovery(recovery) -> None:
    build_id = recovery.add_build("PUBLISHING", "PUBLISHING")
    _seed_attempt_dirs(recovery, build_id)

    recover_pending_builds(recovery.project_root, recovery.database)

    with recovery.database.sessions.begin() as session:
        attempts = SqliteBuildRepository(session).list_attempts(build_id)
    assert attempts[-1].error_code == PUBLISH_RECOVERY_REQUIRED


def test_publishing_file_io_runs_outside_database_transaction(
    recovery, monkeypatch: pytest.MonkeyPatch
) -> None:
    """终审 Important ② 回归：verify_package 等文件 I/O 不得在数据库事务内执行。

    用事务计数代理包裹 sessions.begin()，在 verify_package 被调用的瞬间
    断言活跃事务数为 0（重构前恢复循环全程持有事务）。
    """
    from dst_builder.application import build_recovery as recovery_module

    build_id = recovery.add_build("PUBLISHING", "PUBLISHING")
    attempt_dir = _seed_attempt_dirs(recovery, build_id)
    _write_valid_package(recovery.output_target)
    _seed_publish_evidence(
        attempt_dir, recovery.output_target, recovery.output_target.parent / ".gone-staging"
    )

    counter = {"live": 0}
    real_sessions = recovery.database.sessions

    class _TrackedTransaction:
        def __init__(self, real) -> None:
            self._real = real

        def __enter__(self):
            counter["live"] += 1
            return self._real.__enter__()

        def __exit__(self, *exc_info):
            counter["live"] -= 1
            return self._real.__exit__(*exc_info)

    class _TrackedSessions:
        def begin(self):
            return _TrackedTransaction(real_sessions.begin())

    monkeypatch.setattr(recovery.database, "sessions", _TrackedSessions())

    observed: dict[str, int] = {}
    original_verify = recovery_module.verify_package

    def spy_verify(target):
        observed["live_during_verify"] = counter["live"]
        return original_verify(target)

    monkeypatch.setattr(recovery_module, "verify_package", spy_verify)

    outcomes = recovery_module.recover_pending_builds(
        recovery.project_root, recovery.database
    )

    assert [outcome.error_code for outcome in outcomes] == [None]
    assert observed["live_during_verify"] == 0, (
        "verify_package 在数据库事务内执行（耗时哈希持锁）"
    )


def test_recovery_appends_event_to_attempt_history(recovery) -> None:
    build_id = recovery.add_build("BUILDING_DWG", "BUILDING_DWG")
    _seed_attempt_dirs(recovery, build_id)

    recover_pending_builds(recovery.project_root, recovery.database)

    with recovery.database.sessions.begin() as session:
        events = SqliteBuildRepository(session).list_events(build_id, 1)
    assert [event.sequence for event in events] == [1, 2]
    assert json.loads(events[-1].event_json)["status"] == "FAILED"


# ---------------------------------------------------------------------------
# 应用启动自动恢复
# ---------------------------------------------------------------------------


def test_app_startup_runs_recovery(recovery) -> None:
    build_id = recovery.add_build("PREPARING", "PREPARING")
    _seed_attempt_dirs(recovery, build_id)

    with TestClient(create_builder_app(recovery.project_root)) as client:
        response = client.get("/api/projects/current")
        assert response.status_code == 200

    with recovery.database.sessions.begin() as session:
        run = SqliteBuildRepository(session).load_build_run(build_id)
    assert run.status == "FAILED"


def test_recovery_of_healthy_project_changes_nothing(recovery) -> None:
    outcomes = recover_pending_builds(recovery.project_root, recovery.database)
    assert outcomes == []
