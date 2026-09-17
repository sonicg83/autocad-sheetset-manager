"""Task 9 build/attempt 编排集成测试共享夹具（PLAN-DB-001）。

提供：真实项目库（临时目录）+ 注入 fake DrawingBuilder 的 TestClient，
以及「创建项目 → 纳入资产 → 保存合法草稿 → 提交计划 → 确认计划」的最小前置。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from dst_builder.infrastructure.autocad.request import (
    CAD_DRAWING_RESULT_SCHEMA,
    AttemptPaths,
    CadDrawingResultV1,
)
from dst_builder.interfaces.api import create_builder_app

BASE_CONTENT = b"fake base dwg bytes"
BUILT_CONTENT = b"fake built dwg bytes"
LAYOUT_HANDLE = "2F"

OUTPUT_PATH_NAME = "example-package"

VALID_DRAFT = {
    "schema_version": 1,
    "project": {
        "name": "示例工程",
        "stage": "施工图",
        "discipline": "建筑",
        "output_path": "",  # 由夹具按临时目录填充
    },
    "numbering": {"prefix": "A-", "start": 1, "width": 3},
    "cad_version": "2020",
    "sheets": [{"title": "首层平面图"}],
    "template": {
        "base_asset_id": "",
        "layout_asset_id": "",
        "source_layout": "A1",
    },
}


class FakeDrawingBuilder:
    """§7 生成端口 fake：写 built.dwg 并返回自洽的 CadDrawingResultV1。

    ``behavior`` 可注入异常（如 CadDrawingError）模拟 CAD 阶段失败；
    ``gate`` 可注入回调在执行前后阻塞（用于取消/PUBLISHING 竞态测试）。
    """

    def __init__(
        self,
        project_root: Path,
        *,
        content: bytes = BUILT_CONTENT,
        behavior: Callable[[str, Path], None] | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.content = content
        self.behavior = behavior
        self.calls: list[tuple[str, AttemptPaths]] = []

    def build(self, task, attempt: AttemptPaths, *, cad_version: str) -> CadDrawingResultV1:
        self.calls.append((cad_version, attempt))
        if self.behavior is not None:
            self.behavior(cad_version, attempt.attempt_dir)
        built = self.project_root / task.target_dwg_path
        built.parent.mkdir(parents=True, exist_ok=True)
        built.write_bytes(self.content)
        return CadDrawingResultV1(
            schema=CAD_DRAWING_RESULT_SCHEMA,
            request_id="fake-request-id",
            layout_name=task.target_layout,
            layout_handle=LAYOUT_HANDLE,
            database_version="AC1027",
            layouts=(task.target_layout,),
            diagnostics=(),
            dwg_size=len(self.content),
            dwg_sha256=hashlib.sha256(self.content).hexdigest(),
            cad_version=cad_version,
        )


@dataclass
class BuildEnv:
    client: TestClient
    project_root: Path
    fake_builder: FakeDrawingBuilder
    base_updated_at: str = ""
    plan_id: str | None = None
    extra: dict = field(default_factory=dict)
    draft: dict = field(default_factory=lambda: json.loads(json.dumps(VALID_DRAFT)))

    def patch_draft(self, **overrides) -> None:
        draft = self.draft
        draft["project"]["output_path"] = str(self.project_root.parent / OUTPUT_PATH_NAME)
        for dotted, value in overrides.items():
            container = draft
            parts = dotted.split(".")
            for part in parts[:-1]:
                container = container[int(part)] if part.isdigit() else container[part]
            last = parts[-1]
            if last.isdigit():
                container[int(last)] = value
            else:
                container[last] = value
        response = self.client.patch(
            "/api/projects/current/draft",
            json={"base_updated_at": self.base_updated_at, "draft": draft, "wizard_step": 4},
        )
        assert response.status_code == 200, response.text
        self.base_updated_at = response.json()["updated_at"]
        self.draft = response.json()["draft"]

    def submit_plan(self) -> dict:
        response = self.client.post("/api/plans")
        assert response.status_code == 201, response.text
        self.plan_id = response.json()["plan_id"]
        return response.json()

    def confirm_plan(self, plan_id: str | None = None) -> dict:
        response = self.client.post(f"/api/plans/{plan_id or self.plan_id}/confirm")
        assert response.status_code == 200, response.text
        return response.json()

    @property
    def target(self) -> Path:
        return self.project_root.parent / OUTPUT_PATH_NAME

    def wait_terminal(self, build_id: str, timeout: float = 10.0) -> dict:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/builds/{build_id}")
            assert response.status_code == 200, response.text
            payload = response.json()
            if payload["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                return payload
            time.sleep(0.02)
        raise AssertionError(f"构建未在 {timeout}s 内到达终止状态：{payload['status']}")


def _write_asset_sources(tmp_path: Path) -> tuple[Path, Path]:
    sources = tmp_path / "sources"
    sources.mkdir(exist_ok=True)
    base = sources / "base.dwg"
    layout = sources / "layout.dwt"
    base.write_bytes(BASE_CONTENT)
    layout.write_bytes(b"fake layout template bytes")
    return base, layout


@pytest.fixture
def env(tmp_path: Path) -> BuildEnv:
    project_root = tmp_path / "project"
    fake_builder = FakeDrawingBuilder(project_root)
    client = TestClient(create_builder_app(project_root, drawing_builder=fake_builder))
    response = client.post(
        "/api/projects",
        json={
            "project_root": str(project_root),
            "name": "示例工程",
            "stage": "施工图",
            "discipline": "建筑",
            "output_path": str(tmp_path / OUTPUT_PATH_NAME),
        },
    )
    assert response.status_code == 201, response.text
    state = SimpleNamespace(**response.json())
    base_updated_at = state.updated_at

    base_source, layout_source = _write_asset_sources(tmp_path)
    base_asset = client.post(
        "/api/assets", json={"role": "base", "source_path": str(base_source)}
    ).json()
    layout_asset = client.post(
        "/api/assets", json={"role": "layout", "source_path": str(layout_source)}
    ).json()

    environment = BuildEnv(client=client, project_root=project_root, fake_builder=fake_builder)
    environment.base_updated_at = base_updated_at
    environment.patch_draft(
        **{
            "template.base_asset_id": base_asset["id"],
            "template.layout_asset_id": layout_asset["id"],
        }
    )
    return environment
