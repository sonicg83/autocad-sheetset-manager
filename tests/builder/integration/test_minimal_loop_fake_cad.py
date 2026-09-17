"""最小生成闭环 fake CAD 全链路测试（SPEC-DB-001 §6/§9 / PLAN-DB-001 Task 9）。

真实 DrawingBuilder（CoreConsoleDrawingBuilder + fake executor）驱动的完整
纵向闭环：阶段故障注入（PREPARING/BUILDING_DWG/BUILDING_DST/VERIFYING/
PUBLISHING）、发布原子性（最终改名前正式目标不存在、改名后只存在完整成果）、
attempt CAD 版本证据与计划冻结。
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest
from conftest import BASE_CONTENT, BUILT_CONTENT
from fastapi.testclient import TestClient

import dst_builder.application.builds as builds_module
import dst_builder.infrastructure.filesystem.publisher as publisher_module
from dst_builder.infrastructure.acsm.projection import (
    DST_VALIDATION_FAILED,
    DstValidationError,
)
from dst_builder.infrastructure.autocad.capabilities import CadConfiguration
from dst_builder.infrastructure.autocad.drawing import (
    CAD_EXECUTION_FAILED,
    CoreConsoleDrawingBuilder,
)
from dst_builder.interfaces.api import create_builder_app
from dst_platform.autocad.process import CoreConsoleRequest

# ---------------------------------------------------------------------------
# 夹具：真实 DrawingBuilder + fake Core Console executor
# ---------------------------------------------------------------------------


class FakeExecutor:
    """模拟 accoreconsole：产出结果 JSON 与构建后的 DWG 工作副本。"""

    def __init__(self) -> None:
        self.requests: list[CoreConsoleRequest] = []
        self.behavior = None

    def run(self, request: CoreConsoleRequest):
        self.requests.append(request)
        if self.behavior is not None:
            self.behavior(request)


def _write_cad_result(request: CoreConsoleRequest) -> None:
    """模拟插件：校验请求 JSON、写出结果 JSON、保存构建后的 DWG。"""
    payload = json.loads(
        request.drawing.with_name("cad-drawing-request.json").read_text(encoding="utf-8")
    )
    result = {
        "schema": "dst-builder.cad-drawing-result/v1",
        "request_id": payload["request_id"],
        "layout_name": payload["target_layout"],
        "layout_handle": "2F",
        "database_version": "AC1027",
        "layouts": [payload["target_layout"]],
        "diagnostics": [],
    }
    request.drawing.with_name("cad-drawing-result.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
    request.drawing.write_bytes(BUILT_CONTENT)


class LoopEnv:
    def __init__(self, client, project_root, target, executor):
        self.client = client
        self.project_root = project_root
        self.target = target
        self.executor = executor
        self.plan_id: str | None = None

    def start_build(self) -> str:
        started = self.client.post("/api/builds", json={"plan_id": self.plan_id})
        assert started.status_code == 202, started.text
        return started.json()["build_id"]

    def wait_terminal(self, build_id: str, timeout: float = 10.0) -> dict:
        deadline = time.monotonic() + timeout
        payload: dict = {}
        while time.monotonic() < deadline:
            payload = self.client.get(f"/api/builds/{build_id}").json()
            if payload["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                return payload
            time.sleep(0.02)
        raise AssertionError(f"构建未终止：{payload}")

    def run_confirmed_plan(self) -> tuple[str, dict]:
        self.plan_id = self.client.post("/api/plans").json()["plan_id"]
        confirm = self.client.post(f"/api/plans/{self.plan_id}/confirm")
        assert confirm.status_code == 200, confirm.text
        build_id = self.start_build()
        return build_id, self.wait_terminal(build_id)


@pytest.fixture
def loop_env(tmp_path: Path) -> LoopEnv:
    cad = tmp_path / "cad"
    cad.mkdir(exist_ok=True)
    console = cad / "accoreconsole.exe"
    console.write_bytes(b"MZ fake console")
    plugin = cad / "DstBuilder.AutoCAD.dll"
    plugin.write_bytes(b"MZ fake plugin")
    configuration = CadConfiguration(console_2020=console, plugin_2020=plugin)

    project_root = tmp_path / "project"
    executor = FakeExecutor()
    executor.behavior = _write_cad_result
    builder = CoreConsoleDrawingBuilder(project_root, configuration, executor=executor)

    client = TestClient(create_builder_app(project_root, drawing_builder=builder))
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
    assert response.status_code == 201, response.text
    base_updated_at = response.json()["updated_at"]

    base_source = tmp_path / "base.dwg"
    base_source.write_bytes(BASE_CONTENT)
    layout_source = tmp_path / "layout.dwt"
    layout_source.write_bytes(b"fake layout bytes")
    base_asset = client.post(
        "/api/assets", json={"role": "base", "source_path": str(base_source)}
    ).json()
    layout_asset = client.post(
        "/api/assets", json={"role": "layout", "source_path": str(layout_source)}
    ).json()

    from conftest import VALID_DRAFT

    draft = json.loads(json.dumps(VALID_DRAFT))
    draft["project"]["output_path"] = str(tmp_path / "example-package")
    draft["template"]["base_asset_id"] = base_asset["id"]
    draft["template"]["layout_asset_id"] = layout_asset["id"]
    patch = client.patch(
        "/api/projects/current/draft",
        json={"base_updated_at": base_updated_at, "draft": draft, "wizard_step": 4},
    )
    assert patch.status_code == 200, patch.text

    return LoopEnv(
        client=client,
        project_root=project_root,
        target=tmp_path / "example-package",
        executor=executor,
    )


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_minimal_loop_publishes_complete_package_with_fake_cad(loop_env) -> None:
    env = loop_env
    build_id, final = env.run_confirmed_plan()

    assert final["status"] == "SUCCEEDED"
    assert final["published_path"] == str(env.target)

    from dst_builder.infrastructure.filesystem.package import verify_package

    assert verify_package(env.target) == ()
    built_dwg = next((env.target / "drawings").glob("*.dwg"))
    assert built_dwg.read_bytes() == BUILT_CONTENT
    # 项目根不残留正式 drawings/（成果只进成果包）
    assert not (env.project_root / "drawings").exists()
    # attempt 证据保留：请求 JSON 与 CAD 版本证据
    attempt_dirs = list((env.project_root / "builds" / build_id).iterdir())
    assert len(attempt_dirs) == 1
    cad_evidence = attempt_dirs[0] / "metadata" / "cad-result.json"
    assert cad_evidence.is_file()
    evidence = json.loads(cad_evidence.read_text(encoding="utf-8"))
    assert evidence["cad_version"] == "2020"
    assert evidence["layout_handle"] == "2F"


# ---------------------------------------------------------------------------
# 阶段故障注入
# ---------------------------------------------------------------------------


def test_failure_in_preparing_leaves_no_target(
    loop_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = loop_env

    def broken_prepare(*args, **kwargs):
        raise OSError("无法创建 attempt 目录")

    monkeypatch.setattr(builds_module, "create_attempt_dirs", broken_prepare)
    _build_id, final = env.run_confirmed_plan()

    assert final["status"] == "FAILED"
    assert not env.target.exists()


def test_failure_in_building_dwg_blocks_attempt(loop_env) -> None:
    env = loop_env

    def failing(request: CoreConsoleRequest) -> None:
        raise subprocess.CalledProcessError(returncode=3, cmd=["accoreconsole"])

    env.executor.behavior = failing
    _build_id, final = env.run_confirmed_plan()

    assert final["status"] == "FAILED"
    assert final["error_code"] == CAD_EXECUTION_FAILED
    assert not env.target.exists()


def test_failure_in_building_dst_blocks_attempt(
    loop_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = loop_env

    def broken_dst(*args, **kwargs):
        raise ValueError("DST 构造失败")

    monkeypatch.setattr(builds_module, "build_dst_bytes", broken_dst)
    _build_id, final = env.run_confirmed_plan()

    assert final["status"] == "FAILED"
    assert not env.target.exists()


def test_failure_in_verifying_blocks_attempt_with_dst_code(
    loop_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = loop_env

    def broken_verify(*args, **kwargs):
        raise DstValidationError(())

    monkeypatch.setattr(builds_module, "ensure_dst_valid", broken_verify)
    _build_id, final = env.run_confirmed_plan()

    assert final["status"] == "FAILED"
    assert final["error_code"] == DST_VALIDATION_FAILED
    assert not env.target.exists()


def test_failure_in_publishing_cleans_staging_and_leaves_no_target(
    loop_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = loop_env

    def broken_replace(source: Path, destination: Path) -> None:
        raise OSError("改名失败")

    monkeypatch.setattr(publisher_module.os, "replace", broken_replace)
    _build_id, final = env.run_confirmed_plan()

    assert final["status"] == "FAILED"
    assert not env.target.exists()
    # 暂存目录被清理：目标父目录无 .dstb-staging 残留
    assert not any(
        item.name.startswith(".dstb-staging") for item in env.target.parent.iterdir()
    )


# ---------------------------------------------------------------------------
# 计划冻结
# ---------------------------------------------------------------------------


def test_confirmed_plan_is_frozen_against_draft_drift(loop_env) -> None:
    env = loop_env
    plan_id = env.client.post("/api/plans").json()["plan_id"]
    assert env.client.post(f"/api/plans/{plan_id}/confirm").status_code == 200

    # 确认后修改草稿：构建必须拒绝（已确认计划对应旧修订）
    state = env.client.get("/api/projects/current").json()
    draft = state["draft"]
    draft["sheets"][0]["title"] = "二层平面图"
    patch = env.client.patch(
        "/api/projects/current/draft",
        json={"base_updated_at": state["updated_at"], "draft": draft, "wizard_step": 5},
    )
    assert patch.status_code == 200

    response = env.client.post("/api/builds", json={"plan_id": plan_id})
    assert response.status_code == 409
    assert response.json()["code"] == "PLAN_STALE"
    assert not env.target.exists()
