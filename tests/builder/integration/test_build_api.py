"""构建 API 集成测试（SPEC-DB-001 §6/§11 / PLAN-DB-001 Task 9）。

覆盖：计划提交/确认与 PLAN_STALE、构建启动门禁（PLAN_NOT_CONFIRMED /
PACKAGE_TARGET_EXISTS）、fake CAD 全状态序列与事件（序号单调、Last-Event-ID
重放）、安全取消（PUBLISHING 拒绝）与新 attempt 递增。
"""

from __future__ import annotations

import json
import threading
import time

from dst_builder.infrastructure.filesystem.package import (
    HANDOFF_FILE,
    MANIFEST_FILE,
    verify_package,
)

# ---------------------------------------------------------------------------
# 计划提交与确认
# ---------------------------------------------------------------------------


def test_submit_plan_returns_deterministic_preview(env) -> None:
    first = env.submit_plan()
    second = env.client.post("/api/plans").json()

    assert first["plan_id"] == second["plan_id"]
    assert first["revision_id"] == second["revision_id"]
    preview = first["preview"]
    assert preview["sheet_number"] == "A-001"
    assert preview["layout_name"] == "A-001 首层平面图"
    assert preview["artifact_path"] == "drawings/A-001 首层平面图.dwg"
    assert first["diagnostics"] == []


def test_confirm_unknown_plan_returns_404(env) -> None:
    response = env.client.post("/api/plans/00000000-0000-0000-0000-000000000000/confirm")
    assert response.status_code == 404
    assert response.json()["code"] == "PLAN_NOT_FOUND"


def test_confirm_rejects_draft_drift_with_plan_stale(env) -> None:
    env.submit_plan()
    env.patch_draft(**{"sheets.0.title": "二层平面图"})

    response = env.client.post(f"/api/plans/{env.plan_id}/confirm")
    assert response.status_code == 409
    assert response.json()["code"] == "PLAN_STALE"


def test_resubmitted_plan_after_drift_is_confirmable(env) -> None:
    env.submit_plan()
    env.patch_draft(**{"sheets.0.title": "二层平面图"})
    plan = env.submit_plan()
    confirmed = env.confirm_plan(plan["plan_id"])
    assert confirmed["confirmed_at"]


# ---------------------------------------------------------------------------
# 构建启动门禁
# ---------------------------------------------------------------------------


def test_start_build_requires_confirmed_plan(env) -> None:
    plan = env.submit_plan()
    response = env.client.post("/api/builds", json={"plan_id": plan["plan_id"]})
    assert response.status_code == 422
    assert response.json()["code"] == "PLAN_NOT_CONFIRMED"


def test_start_build_rejects_existing_target_without_touching_it(env) -> None:
    env.submit_plan()
    env.confirm_plan()
    env.target.mkdir(parents=True)
    (env.target / "keep.txt").write_bytes(b"user data")

    response = env.client.post("/api/builds", json={"plan_id": env.plan_id})
    assert response.status_code == 409
    assert response.json()["code"] == "PACKAGE_TARGET_EXISTS"
    assert [item.name for item in env.target.iterdir()] == ["keep.txt"]


def test_start_build_unknown_plan_returns_404(env) -> None:
    response = env.client.post("/api/builds", json={"plan_id": "missing"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# fake CAD 完整闭环：状态序列、事件、SSE
# ---------------------------------------------------------------------------


def test_full_build_reaches_succeeded_and_publishes_package(env) -> None:
    env.submit_plan()
    env.confirm_plan()
    started = env.client.post("/api/builds", json={"plan_id": env.plan_id})
    assert started.status_code == 202, started.text
    build_id = started.json()["build_id"]
    # 启动响应在线程执行器已开跑后返回：状态必须是非终止阶段。
    assert started.json()["status"] not in {"SUCCEEDED", "FAILED", "CANCELLED"}

    final = env.wait_terminal(build_id)
    assert final["status"] == "SUCCEEDED"
    assert final["published_path"] == str(env.target)

    assert env.target.is_dir()
    assert verify_package(env.target) == ()
    assert (env.target / MANIFEST_FILE).is_file()
    assert (env.target / HANDOFF_FILE).is_file()
    # 正式根只有两项
    assert sorted(item.name for item in env.target.iterdir()) == ["drawings", "metadata"]


def test_event_sequences_are_monotonic_and_replayable(env) -> None:
    env.submit_plan()
    env.confirm_plan()
    build_id = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()["build_id"]
    env.wait_terminal(build_id)

    response = env.client.get(f"/api/builds/{build_id}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)

    sequences = [event["sequence"] for event in events]
    assert sequences == sorted(sequences)
    assert sequences[0] == 1
    statuses = [event["status"] for event in events]
    assert statuses[0] == "QUEUED"
    assert statuses[-1] == "SUCCEEDED"
    for expected in ("PREPARING", "BUILDING_DWG", "BUILDING_DST", "VERIFYING", "PUBLISHING"):
        assert expected in statuses

    # Last-Event-ID 重放：跳过前 3 个事件后，首条即第 4 个
    last_id = f"1:{sequences[2]}"
    replay = env.client.get(
        f"/api/builds/{build_id}/events", headers={"Last-Event-ID": last_id}
    )
    replayed = _parse_sse(replay.text)
    assert [event["sequence"] for event in replayed] == sequences[3:]


def test_sse_streams_live_events_before_terminal(env) -> None:
    """构建进行中连接 SSE：能收到非终止阶段事件（断线不影响构建）。"""
    env.submit_plan()
    env.confirm_plan()
    release = threading.Event()
    entered = threading.Event()
    original = env.fake_builder.behavior

    def gate(_cad_version: str, _attempt_dir) -> None:
        entered.set()
        assert release.wait(timeout=10)

    env.fake_builder.behavior = gate
    build_id = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()["build_id"]
    assert entered.wait(timeout=5), "fake CAD 未进入 BUILDING_DWG"

    response = env.client.get(f"/api/builds/{build_id}/events")
    events = _parse_sse(response.text)
    statuses = [event["status"] for event in events]
    assert "BUILDING_DWG" in statuses

    release.set()
    env.wait_terminal(build_id)
    env.fake_builder.behavior = original


# ---------------------------------------------------------------------------
# 取消语义
# ---------------------------------------------------------------------------


def test_cancel_during_building_dwg_transitions_to_cancelled(env) -> None:
    env.submit_plan()
    env.confirm_plan()
    release = threading.Event()
    entered = threading.Event()

    def gate(_cad_version: str, _attempt_dir) -> None:
        entered.set()
        assert release.wait(timeout=10)

    env.fake_builder.behavior = gate
    build_id = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()["build_id"]
    assert entered.wait(timeout=5)

    response = env.client.post(f"/api/builds/{build_id}/cancel")
    assert response.status_code == 202, response.text
    release.set()

    final = env.wait_terminal(build_id)
    assert final["status"] == "CANCELLED"
    # 取消后正式目标不存在
    assert not env.target.exists()


def test_cancel_during_publishing_is_rejected_and_build_succeeds(env) -> None:
    env.submit_plan()
    env.confirm_plan()

    entered = threading.Event()
    release = threading.Event()

    import dst_builder.infrastructure.filesystem.publisher as publisher_module

    original_replace = publisher_module.os.replace

    def gated_replace(source, destination):
        entered.set()
        assert release.wait(timeout=10)
        return original_replace(source, destination)

    publisher_module.os.replace = gated_replace  # type: ignore[assignment]
    try:
        build_id = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()[
            "build_id"
        ]
        assert entered.wait(timeout=5)
        # 等 GET 状态也反映 PUBLISHING（事件与状态同事务，先于暂存改名）
        deadline = time.monotonic() + 5
        status = None
        while time.monotonic() < deadline:
            status = env.client.get(f"/api/builds/{build_id}").json()["status"]
            if status == "PUBLISHING":
                break
            time.sleep(0.02)
        assert status == "PUBLISHING"

        response = env.client.post(f"/api/builds/{build_id}/cancel")
        assert response.status_code == 409
        assert response.json()["code"] == "CANCEL_NOT_ACCEPTED"
    finally:
        release.set()
        publisher_module.os.replace = original_replace  # type: ignore[assignment]

    final = env.wait_terminal(build_id)
    assert final["status"] == "SUCCEEDED"


# ---------------------------------------------------------------------------
# 新 attempt 递增与并发启动门禁
# ---------------------------------------------------------------------------


def test_new_attempt_increments_after_failed_attempt(env) -> None:
    from dst_builder.infrastructure.autocad.drawing import (
        CAD_EXECUTION_FAILED,
        CadDrawingError,
    )

    env.submit_plan()
    env.confirm_plan()
    env.fake_builder.behavior = lambda _v, _d: (_ for _ in ()).throw(
        CadDrawingError(CAD_EXECUTION_FAILED, "注入失败")
    )
    first = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()
    final = env.wait_terminal(first["build_id"])
    assert final["status"] == "FAILED"

    # 修复后基于同一计划重试：attempt 递增。
    env.fake_builder.behavior = None
    second = env.client.post("/api/builds", json={"plan_id": env.plan_id})
    assert second.status_code == 202, second.text
    payload = second.json()
    assert payload["attempt"] == first["attempt"] + 1
    assert payload["build_id"] == first["build_id"]

    final = env.wait_terminal(payload["build_id"])
    assert final["status"] == "SUCCEEDED"
    attempts = {item["attempt"]: item["status"] for item in final["attempts"]}
    assert attempts[1] == "FAILED"
    assert attempts[2] == "SUCCEEDED"
    # 历史不覆盖：两个 attempt 记录都在
    assert len(final["attempts"]) == 2


def test_restart_after_success_is_rejected_because_target_exists(env) -> None:
    """成功后目标已存在：首期不覆盖，不再发起新 attempt。"""
    env.submit_plan()
    env.confirm_plan()
    first = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()
    env.wait_terminal(first["build_id"])

    response = env.client.post("/api/builds", json={"plan_id": env.plan_id})
    assert response.status_code == 409
    assert response.json()["code"] == "PACKAGE_TARGET_EXISTS"


def test_concurrent_start_while_running_is_rejected(env) -> None:
    env.submit_plan()
    env.confirm_plan()
    release = threading.Event()

    def gate(_cad_version: str, _attempt_dir) -> None:
        assert release.wait(timeout=10)

    env.fake_builder.behavior = gate
    first = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()
    assert env.client.get(f"/api/builds/{first['build_id']}").status_code == 200

    response = env.client.post("/api/builds", json={"plan_id": env.plan_id})
    assert response.status_code == 409
    assert response.json()["code"] == "BUILD_ALREADY_RUNNING"

    release.set()
    env.wait_terminal(first["build_id"])


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        data_lines = [
            line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: ")
        ]
        if data_lines:
            events.append(json.loads("".join(data_lines)))
    return events
