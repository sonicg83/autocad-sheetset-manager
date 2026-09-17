"""Manager 显式交接 API 集成测试（SPEC-DB-001 §10/§11，PLAN-DB-001 Task 10）。

覆盖：交接成功（handoff_initial 修订与证据目录）、重复幂等、package_id
冲突、逐场景验证失败的零写入、普通 /api/workspaces/open 不推断 handoff，
以及 Builder 一键交接适配器（Manager 可用 / 不可用 / 构建未发布）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from handoff_package_factory import (
    BUILD_ID,
    DWG_CONTENT,
    entry_by_path,
    make_builder_package,
    reseal_package,
)

from dst_builder.infrastructure.autocad.capabilities import CadConfiguration
from dst_builder.infrastructure.autocad.drawing import CoreConsoleDrawingBuilder
from dst_builder.infrastructure.filesystem.package import (
    verify_package as builder_verify_package,
)
from dst_builder.interfaces.api import create_builder_app
from dst_manager.config import Settings
from dst_manager.infrastructure.persistence.database import Database
from dst_manager.interfaces.api import create_app

# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


class ManagerEnv:
    def __init__(self, tmp_path: Path) -> None:
        self.settings = Settings(data_dir=tmp_path / "manager-data")
        self.client = TestClient(create_app(self.settings))
        self.database = Database(self.settings.database_url)

    def open_handoff(self, package_root: Path):
        return self.client.post(
            "/api/handoffs/open",
            json={"handoff_path": str(package_root / "metadata" / "handoff.json")},
        )

    def counts(self) -> dict[str, int]:
        with sqlite3.connect(self.database.engine.url.database) as connection:
            return {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("workspaces", "handoff_sources", "document_revisions")
            }


@pytest.fixture
def manager(tmp_path: Path) -> ManagerEnv:
    return ManagerEnv(tmp_path)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "example-package"
    make_builder_package(root)
    return root


def _package_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".dst-manager" not in path.parts
    }


def _canonical_json(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


# ---------------------------------------------------------------------------
# 交接成功与幂等
# ---------------------------------------------------------------------------


def test_handoff_open_creates_workspace_and_handoff_initial_revision(manager, package) -> None:
    dst_path = package / "drawings" / "sheetset.dst"
    dst_sha256 = hashlib.sha256(dst_path.read_bytes()).hexdigest()

    response = manager.open_handoff(package)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["idempotent"] is False
    assert payload["kind"] == "handoff_initial"
    assert payload["package_id"]
    assert payload["build_id"] == BUILD_ID
    assert payload["dst_path"] == str(dst_path)
    assert payload["dst_sha256"] == dst_sha256
    assert payload["root"] == str(package)

    # 数据库证据：工作区 + handoff 来源 + 初始修订
    assert manager.counts() == {"workspaces": 1, "handoff_sources": 1, "document_revisions": 1}
    revisions = manager.client.get(
        "/api/revisions", params={"workspace_id": payload["workspace_id"]}
    ).json()
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision["kind"] == "handoff_initial"
    assert revision["before_hash"] == dst_sha256
    assert revision["result_hash"] == dst_sha256
    assert revision["id"] == payload["revision_id"]
    assert revision["source_json"]["schema"] == "dst-manager.handoff-source/v1"
    assert revision["source_json"]["package_id"] == payload["package_id"]
    assert revision["source_json"]["manifest_sha256"] == payload["manifest_sha256"]
    assert revision["source_json"]["build_id"] == BUILD_ID

    # 修订目录：可验证 manifest + 完整 drawings/ 基线 + Builder metadata 副本
    revision_dir = Path(revision["revision_dir"])
    manifest = json.loads((revision_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "handoff_initial"
    assert manifest["handoff"]["package_id"] == payload["package_id"]
    entries = {
        Path(entry["target"]).relative_to(package).as_posix(): entry
        for entry in manifest["files"]
    }
    assert set(entries) == {
        path for path in _package_files(package) if path.startswith("drawings/")
    }
    for relative, entry in entries.items():
        backup = Path(entry["backup"])
        assert backup.is_file()
        assert entry["target"] == str(package / relative)
        assert entry["before_hash"] == entry["result_hash"]
        assert entry["result_hash"] == hashlib.sha256(backup.read_bytes()).hexdigest()
        assert hashlib.sha256((package / relative).read_bytes()).hexdigest() == entry["result_hash"]
    assert {Path(path).name for path in entries} == {
        path.name for path in (revision_dir / "drawings").iterdir()
    }
    assert {
        "manifest.json",
        "handoff.json",
        "project-revision.json",
        "generation-plan.json",
        "validation-report.json",
    } == {path.name for path in (revision_dir / "metadata").iterdir()}

    # 现有工作区/修订/恢复逻辑仍然工作（工作区当前修订 = DST 内容哈希）
    reopened = manager.client.get(f"/api/workspaces/{payload['workspace_id']}")
    assert reopened.status_code == 200
    assert reopened.json()["revision_id"] == payload["dst_sha256"]
    preview = manager.client.get(
        f"/api/workspaces/{payload['workspace_id']}/revisions/{payload['revision_id']}/restore-preview"
    ).json()
    assert preview["executable"] is True
    assert {item["path"].replace("\\", "/") for item in preview["files"]} == set(entries)


def test_repeated_handoff_is_idempotent(manager, package) -> None:
    first = manager.open_handoff(package)
    assert first.status_code == 200
    snapshot = manager.counts()

    second = manager.open_handoff(package)

    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["idempotent"] is True
    assert payload["workspace_id"] == first.json()["workspace_id"]
    assert payload["revision_id"] == first.json()["revision_id"]
    assert manager.counts() == snapshot
    operation_root = Path(first.json()["revision_dir"]).parent
    assert [item.name for item in operation_root.iterdir()] == ["attempt-001"]


def test_same_package_id_with_different_hash_is_conflict(manager, package, tmp_path) -> None:
    first = manager.open_handoff(package)
    assert first.status_code == 200
    original_package_id = first.json()["package_id"]

    # 伪造：改动内容、重算 manifest 哈希，但保留原 package_id（§10 冲突场景）
    forged = tmp_path / "forged-package"
    shutil.copytree(package, forged, ignore=shutil.ignore_patterns(".dst-manager"))
    target = forged / entry_by_path(forged, "metadata/validation-report.json")["path"]
    target.write_bytes(target.read_bytes() + b"tampered")
    reseal_package(forged)
    handoff_path = forged / "metadata" / "handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["package_id"] = original_package_id
    handoff_path.write_bytes(_canonical_json(handoff))

    response = manager.open_handoff(forged)

    assert response.status_code == 409
    assert response.json()["code"] == "HANDOFF_ID_CONFLICT"
    assert manager.counts() == {"workspaces": 1, "handoff_sources": 1, "document_revisions": 1}
    assert not (forged / ".dst-manager").exists()


# ---------------------------------------------------------------------------
# 验证失败零写入
# ---------------------------------------------------------------------------


def _tamper_package(scenario: str, root: Path) -> None:
    if scenario == "unknown_schema":
        handoff_path = root / "metadata" / "handoff.json"
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff["schema"] = "dst-builder.handoff/v2"
        handoff_path.write_bytes(_canonical_json(handoff))
    elif scenario == "manifest_drift":
        target = root / entry_by_path(root, "metadata/validation-report.json")["path"]
        target.write_bytes(target.read_bytes() + b"drift")
    elif scenario == "missing_file":
        (root / entry_by_path(root, "drawings/图纸目录.xlsx")["path"]).unlink()
    elif scenario == "path_escape":
        entries = json.loads((root / "metadata" / "manifest.json").read_text(encoding="utf-8"))[
            "files"
        ]
        for item in entries:
            if item["path"] == "metadata/project-revision.json":
                item["path"] = "metadata/../outside.json"
        reseal_package(root, entries=entries)
    elif scenario == "case_collision":
        entries = json.loads((root / "metadata" / "manifest.json").read_text(encoding="utf-8"))[
            "files"
        ]
        colliding = dict(entries[0])
        colliding["path"] = entries[0]["path"].swapcase()
        reseal_package(root, entries=[*entries, colliding])
    elif scenario == "dst_reference_outside":
        outside = root.parent / f"escaped-{uuid.uuid4().hex[:8]}.dwg"
        outside.write_bytes(DWG_CONTENT)
        _rewrite_dst_reference(root, "../" + outside.name)
        reseal_package(root)
    else:  # pragma: no cover - 参数化守卫
        raise AssertionError(scenario)


def _rewrite_dst_reference(package: Path, new_relative: str) -> None:
    from dst_manager.infrastructure.acsm_xml import AcsmDocument
    from dst_manager.infrastructure.dst_codec import DstCodec as ManagerDstCodec
    from dst_platform.acsm.codec import DstCodec as PlatformDstCodec

    dst = package / "drawings" / "sheetset.dst"
    document = AcsmDocument(ManagerDstCodec().decode_file(dst))
    layout = document.root.xpath("//*[local-name()='AcSmAcDbLayoutReference']")[0]
    for prop_name in ("FileName", "Relative_FileName"):
        layout.xpath(f"./*[local-name()='AcSmProp' and @propname='{prop_name}']")[0].text = (
            new_relative
        )
    PlatformDstCodec().encode_file(document.to_bytes(), dst)


@pytest.mark.parametrize(
    "scenario",
    [
        "unknown_schema",
        "manifest_drift",
        "missing_file",
        "path_escape",
        "case_collision",
        "dst_reference_outside",
    ],
)
def test_failed_validation_writes_nothing(manager, tmp_path, scenario) -> None:
    root = tmp_path / f"pkg-{scenario}"
    make_builder_package(root)
    _tamper_package(scenario, root)
    before = manager.counts()
    assert before == {"workspaces": 0, "handoff_sources": 0, "document_revisions": 0}

    response = manager.open_handoff(root)

    assert 400 <= response.status_code < 500, response.text
    assert response.json()["code"] == "HANDOFF_INVALID"
    assert manager.counts() == before
    assert not (root / ".dst-manager").exists()


def test_normal_workspace_open_does_not_infer_handoff(manager, package) -> None:
    dst = package / "drawings" / "sheetset.dst"

    response = manager.client.post("/api/workspaces/open", json={"dst_path": str(dst)})

    assert response.status_code == 200
    assert response.json()["root"] == str(dst.parent)
    assert manager.counts() == {"workspaces": 1, "handoff_sources": 0, "document_revisions": 0}
    assert not (package / ".dst-manager").exists()


# ---------------------------------------------------------------------------
# Builder 一键交接适配器（§11 POST /api/builds/{id}/handoff）
# ---------------------------------------------------------------------------


def _write_cad_result(request) -> None:
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
    request.drawing.write_bytes(b"fake built dwg bytes (integration)")


def _run_build(tmp_path: Path, *, work_name: str = "loop", fail_cad: bool = False) -> tuple[TestClient, str, Path]:
    work = tmp_path / work_name
    work.mkdir(parents=True, exist_ok=True)
    cad = work / "cad"
    cad.mkdir(exist_ok=True)
    console = cad / "accoreconsole.exe"
    console.write_bytes(b"MZ fake console")
    plugin = cad / "DstBuilder.AutoCAD.dll"
    plugin.write_bytes(b"MZ fake plugin")

    def execute(request) -> None:
        if fail_cad:
            raise RuntimeError("CAD 执行失败")
        _write_cad_result(request)

    project_root = work / "project"
    drawing_builder = CoreConsoleDrawingBuilder(
        project_root,
        CadConfiguration(console_2020=console, plugin_2020=plugin),
        executor=_FakeConsoleExecutor(execute),
    )
    client = TestClient(create_builder_app(project_root, drawing_builder=drawing_builder))

    response = client.post(
        "/api/projects",
        json={
            "project_root": str(project_root),
            "name": "示例工程",
            "stage": "施工图",
            "discipline": "建筑",
            "output_path": str(work / "example-package"),
        },
    )
    assert response.status_code == 201, response.text
    base_updated_at = response.json()["updated_at"]
    base_source = work / "base.dwg"
    base_source.write_bytes(b"fake base dwg bytes")
    layout_source = work / "layout.dwt"
    layout_source.write_bytes(b"fake layout bytes")
    base_asset = client.post(
        "/api/assets", json={"role": "base", "source_path": str(base_source)}
    ).json()
    layout_asset = client.post(
        "/api/assets", json={"role": "layout", "source_path": str(layout_source)}
    ).json()
    state = client.get("/api/projects/current").json()
    draft = state["draft"]
    draft["project"]["output_path"] = str(work / "example-package")
    draft["sheets"] = [{"title": "首层平面图"}]
    draft["template"]["source_layout"] = "A1"
    draft["template"]["base_asset_id"] = base_asset["id"]
    draft["template"]["layout_asset_id"] = layout_asset["id"]
    patch = client.patch(
        "/api/projects/current/draft",
        json={"base_updated_at": base_updated_at, "draft": draft, "wizard_step": 4},
    )
    assert patch.status_code == 200, patch.text
    plan_id = client.post("/api/plans").json()["plan_id"]
    confirmed = client.post(f"/api/plans/{plan_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    started = client.post("/api/builds", json={"plan_id": plan_id})
    assert started.status_code == 202, started.text
    build_id = started.json()["build_id"]
    deadline = time.monotonic() + 10.0
    payload: dict = {}
    while time.monotonic() < deadline:
        payload = client.get(f"/api/builds/{build_id}").json()
        if payload["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.02)
    expected = "FAILED" if fail_cad else "SUCCEEDED"
    assert payload["status"] == expected, payload
    return client, build_id, Path(payload["published_path"]) if payload.get("published_path") else work / "example-package"


class _FakeConsoleExecutor:
    def __init__(self, behavior) -> None:
        self.behavior = behavior

    def run(self, request) -> None:
        self.behavior(request)


def test_builder_handoff_endpoint_calls_manager_adapter(manager, tmp_path) -> None:
    builder_client, build_id, published = _run_build(tmp_path)
    assert builder_verify_package(published) == ()
    forwarded: dict = {}

    def transport(url: str, payload: dict):
        forwarded["url"] = url
        forwarded["payload"] = payload
        package_root = Path(payload["handoff_path"]).parent.parent
        response = manager.open_handoff(package_root)
        return response.status_code, response.json()

    builder_client.app.state.handoff_transport = transport
    response = builder_client.post(f"/api/builds/{build_id}/handoff")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["workspace_id"]
    assert payload["kind"] == "handoff_initial"
    assert forwarded["payload"] == {"handoff_path": str(published / "metadata" / "handoff.json")}
    assert forwarded["url"].endswith("/api/handoffs/open")
    assert manager.counts()["handoff_sources"] == 1


def test_builder_handoff_preserves_package_when_manager_unavailable(tmp_path) -> None:
    builder_client, build_id, published = _run_build(tmp_path)
    snapshot = {path: path.read_bytes() for path in published.rglob("*") if path.is_file()}

    def unreachable(url: str, payload: dict):
        raise OSError("连接被拒绝")

    builder_client.app.state.handoff_transport = unreachable
    response = builder_client.post(f"/api/builds/{build_id}/handoff")

    assert response.status_code == 502
    payload = response.json()
    assert payload["code"] == "HANDOFF_UNAVAILABLE"
    assert "保留" in payload["recovery_action"]
    assert {path: path.read_bytes() for path in published.rglob("*") if path.is_file()} == snapshot


def test_builder_handoff_rejects_build_without_published_package(tmp_path) -> None:
    builder_client, _build_id, _published = _run_build(tmp_path, fail_cad=True)

    response = builder_client.post(f"/api/builds/{uuid.uuid4()}/handoff")

    assert response.status_code == 404
    assert response.json()["code"] == "BUILD_NOT_FOUND"


def test_builder_handoff_rejects_failed_build(tmp_path) -> None:
    builder_client, build_id, _published = _run_build(tmp_path, fail_cad=True)

    response = builder_client.post(f"/api/builds/{build_id}/handoff")

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "HANDOFF_INVALID"
    assert payload["recovery_action"]
