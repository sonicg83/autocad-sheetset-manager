"""资产纳入 API 集成测试（SPEC-DB-001 §3/§4/§11 / PLAN-DB-001 Task 4）。

覆盖：内容寻址落盘与入库、同内容去重幂等、扩展名与 2 GiB 上限门禁、
复制中源文件变化（ASSET_HASH_MISMATCH）、文件/数据库提交失败不留假记录
（文件无记录、记录无文件都算失败）、大小写碰撞拒绝，以及布局 inspection
端口未接线时的固定语义（501 + CAD_VERSION_UNAVAILABLE）。
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from dst_builder.application.assets import (
    ASSET_FILE_TOO_LARGE,
    ASSET_HASH_MISMATCH,
    ASSET_NOT_FOUND,
    ASSET_OUTSIDE_PROJECT,
    ASSET_SOURCE_MISSING,
    ASSET_TYPE_REJECTED,
    CAD_VERSION_UNAVAILABLE,
    AssetFileTooLargeError,
    AssetHashMismatchError,
    AssetIntake,
    BuilderAssetService,
)
from dst_builder.domain.models import AssetRole
from dst_builder.infrastructure.assets.store import (
    MAX_ASSET_BYTES,
    SqliteAssetRepository,
)
from dst_builder.infrastructure.persistence.database import AssetRow, Database
from dst_builder.interfaces.api import create_builder_app

CONTENT = b"DST-BUILDER fake dwg content\n"
PROJECT_BODY = {
    "name": "示例工程",
    "stage": "施工图",
    "discipline": "建筑",
    "output_path": "D:/deliveries/example-package",
}


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    return tmp_path / "project"


@pytest.fixture()
def client(project_root: Path) -> TestClient:
    return TestClient(create_builder_app(project_root=project_root))


@pytest.fixture()
def initialized(client: TestClient) -> None:
    response = client.post("/api/projects", json=PROJECT_BODY)
    assert response.status_code == 201, response.text


def _write_source(tmp_path: Path, name: str, content: bytes) -> Path:
    """源文件位于项目外（tmp_path/sources），项目根在 tmp_path/project。"""
    source = tmp_path / "sources" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    return source


def _intake(client: TestClient, source: Path, role: str = "base") -> dict[str, Any]:
    response = client.post("/api/assets", json={"role": role, "source_path": str(source)})
    assert response.status_code == 201, response.text
    return response.json()


def _asset_count(project_root: Path) -> int:
    database = Database(project_root / "project.dstb")
    with database.sessions.begin() as session:
        return int(session.scalars(select(func.count()).select_from(AssetRow)).one())


def _temp_residue(project_root: Path) -> list[Path]:
    return list((project_root / "assets").rglob("incoming-*"))


# ---------------------------------------------------------------------------
# 正常纳入：内容寻址落盘 + 入库
# ---------------------------------------------------------------------------


def test_intake_base_asset_places_content_addressed_file_and_record(
    project_root: Path, client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "首层平面.dwg", CONTENT)
    expected_sha = hashlib.sha256(CONTENT).hexdigest()

    payload = _intake(client, source, role="base")

    assert payload["role"] == "base"
    assert payload["sha256"] == expected_sha
    assert payload["size"] == len(CONTENT)
    assert payload["relative_path"] == f"assets/base/{expected_sha}.dwg"
    assert payload["source_name"] == "首层平面.dwg"
    uuid.UUID(payload["id"])  # id 是合法 UUID

    final = project_root / "assets" / "base" / f"{expected_sha}.dwg"
    assert final.is_file()
    assert final.read_bytes() == CONTENT
    assert _temp_residue(project_root) == []

    with Database(project_root / "project.dstb").sessions.begin() as session:
        record = SqliteAssetRepository(session).load(payload["id"])
    assert record is not None
    assert record.relative_path == payload["relative_path"]
    assert record.source_name == "首层平面.dwg"


def test_intake_layout_asset_accepts_dwt(
    project_root: Path, client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "A1 图框.dwt", CONTENT)
    expected_sha = hashlib.sha256(CONTENT).hexdigest()

    payload = _intake(client, source, role="layout")

    assert payload["role"] == "layout"
    assert payload["relative_path"] == f"assets/layout/{expected_sha}.dwt"
    assert (project_root / "assets" / "layout" / f"{expected_sha}.dwt").is_file()


def test_intake_accepts_uppercase_extension(
    client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "PLAN.DWG", CONTENT)
    expected_sha = hashlib.sha256(CONTENT).hexdigest()

    payload = _intake(client, source, role="base")

    # 存储名统一小写扩展名（内容寻址名规范化）。
    assert payload["relative_path"] == f"assets/base/{expected_sha}.dwg"


def test_intake_source_name_never_participates_in_path(
    client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "危险 名称!! 演示.dwg", CONTENT)
    expected_sha = hashlib.sha256(CONTENT).hexdigest()

    payload = _intake(client, source, role="base")

    assert payload["source_name"] == "危险 名称!! 演示.dwg"
    assert payload["relative_path"] == f"assets/base/{expected_sha}.dwg"


# ---------------------------------------------------------------------------
# 去重幂等
# ---------------------------------------------------------------------------


def test_intake_same_content_same_role_is_idempotent(
    project_root: Path, client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "base.dwg", CONTENT)

    first = _intake(client, source, role="base")
    second = _intake(client, source, role="base")

    assert second == first
    assert _asset_count(project_root) == 1
    assert len(list((project_root / "assets" / "base").glob("*.dwg"))) == 1


def test_intake_same_content_different_role_creates_separate_assets(
    project_root: Path, client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "both.dwg", CONTENT)

    base = _intake(client, source, role="base")
    layout = _intake(client, source, role="layout")

    assert base["id"] != layout["id"]
    assert base["relative_path"] != layout["relative_path"]
    assert _asset_count(project_root) == 2


def test_intake_replaces_missing_file_when_record_exists(
    project_root: Path, client: TestClient, initialized: None, tmp_path: Path
) -> None:
    """去重命中但项目内文件缺失：重新落盘自愈，不留“记录无文件”假状态。"""
    source = _write_source(tmp_path, "base.dwg", CONTENT)
    service = BuilderAssetService(project_root)
    record = service.intake(AssetIntake(role=AssetRole.BASE, source_path=source))
    final = project_root / record.relative_path
    final.unlink()
    assert not final.exists()

    healed = service.intake(AssetIntake(role=AssetRole.BASE, source_path=source))

    assert healed.id == record.id
    assert final.is_file()
    assert final.read_bytes() == CONTENT


# ---------------------------------------------------------------------------
# §4 门禁：扩展名与 2 GiB 上限
# ---------------------------------------------------------------------------


def test_intake_rejects_wrong_extension_for_role(
    client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "frame.dwt", CONTENT)

    response = client.post("/api/assets", json={"role": "base", "source_path": str(source)})

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == ASSET_TYPE_REJECTED
    assert payload["recovery_action"]


def test_intake_rejects_non_cad_extension(
    client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "notes.txt", CONTENT)

    response = client.post("/api/assets", json={"role": "layout", "source_path": str(source)})

    assert response.status_code == 422
    assert response.json()["code"] == ASSET_TYPE_REJECTED


def test_intake_rejects_unknown_role(
    client: TestClient, initialized: None, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, "base.dwg", CONTENT)

    response = client.post("/api/assets", json={"role": "template", "source_path": str(source)})

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"


def test_intake_missing_source_file_returns_404(
    client: TestClient, initialized: None, tmp_path: Path
) -> None:
    missing = tmp_path / "sources" / "missing.dwg"

    response = client.post("/api/assets", json={"role": "base", "source_path": str(missing)})

    assert response.status_code == 404
    assert response.json()["code"] == ASSET_SOURCE_MISSING


def test_intake_before_project_initialization_returns_404(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    client = TestClient(create_builder_app(project_root=root))
    source = _write_source(tmp_path, "base.dwg", CONTENT)

    response = client.post("/api/assets", json={"role": "base", "source_path": str(source)})

    assert response.status_code == 404
    assert response.json()["code"] == "PROJECT_PATH_INVALID"
    assert not (root / "assets").exists()


def test_intake_enforces_size_limit(
    project_root: Path, client: TestClient, initialized: None, tmp_path: Path
) -> None:
    """≤ 上限接受、> 上限拒绝；默认上限为 2 GiB（无法在测试中真实构造）。"""
    service = BuilderAssetService(project_root, max_bytes=8)
    small = _write_source(tmp_path, "small.dwg", b"12345678")
    big = _write_source(tmp_path, "big.dwg", b"123456789")

    record = service.intake(AssetIntake(role=AssetRole.BASE, source_path=small))
    assert record.size == 8

    with pytest.raises(AssetFileTooLargeError) as excinfo:
        service.intake(AssetIntake(role=AssetRole.BASE, source_path=big))
    assert excinfo.value.code == ASSET_FILE_TOO_LARGE
    assert _asset_count(project_root) == 1  # 只有 small 入库

    assert MAX_ASSET_BYTES == 2 * 1024**3


# ---------------------------------------------------------------------------
# 复制前后一致性：源文件变化 → ASSET_HASH_MISMATCH
# ---------------------------------------------------------------------------


def test_intake_detects_source_mutation_during_copy(
    project_root: Path,
    client: TestClient,
    initialized: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path, "base.dwg", CONTENT)

    def tampered_copy(source_path: Path, target_path: Path) -> int:
        target_path.write_bytes(b"tampered during copy")
        return len(b"tampered during copy")

    monkeypatch.setattr("dst_builder.application.assets.stream_copy", tampered_copy)
    service = BuilderAssetService(project_root)

    with pytest.raises(AssetHashMismatchError) as excinfo:
        service.intake(AssetIntake(role=AssetRole.BASE, source_path=source))

    assert excinfo.value.code == ASSET_HASH_MISMATCH
    assert _asset_count(project_root) == 0
    assert list((project_root / "assets" / "base").glob("*.dwg")) == []
    assert _temp_residue(project_root) == []


# ---------------------------------------------------------------------------
# 提交原子性：文件/数据库任一失败都不留假记录
# ---------------------------------------------------------------------------


def test_intake_file_placement_failure_leaves_no_record(
    project_root: Path,
    client: TestClient,
    initialized: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path, "base.dwg", CONTENT)

    def broken_replace(source_path: Path, target_path: Path) -> None:
        raise OSError("模拟原子改名失败")

    monkeypatch.setattr("dst_builder.infrastructure.assets.store.atomic_replace", broken_replace)
    service = BuilderAssetService(project_root)

    with pytest.raises(OSError):
        service.intake(AssetIntake(role=AssetRole.BASE, source_path=source))

    assert _asset_count(project_root) == 0
    assert list((project_root / "assets" / "base").glob("*.dwg")) == []
    assert _temp_residue(project_root) == []


def test_intake_database_failure_leaves_no_file(
    project_root: Path,
    client: TestClient,
    initialized: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path, "base.dwg", CONTENT)
    expected_sha = hashlib.sha256(CONTENT).hexdigest()

    def broken_insert(self: object, record: object) -> None:
        raise RuntimeError("模拟数据库提交失败")

    monkeypatch.setattr(SqliteAssetRepository, "insert", broken_insert)
    service = BuilderAssetService(project_root)

    with pytest.raises(RuntimeError):
        service.intake(AssetIntake(role=AssetRole.BASE, source_path=source))

    assert _asset_count(project_root) == 0
    assert not (project_root / "assets" / "base" / f"{expected_sha}.dwg").exists()
    assert _temp_residue(project_root) == []


# ---------------------------------------------------------------------------
# 路径边界：大小写碰撞
# ---------------------------------------------------------------------------


def test_intake_rejects_case_colliding_existing_file(
    project_root: Path, client: TestClient, initialized: None, tmp_path: Path
) -> None:
    expected_sha = hashlib.sha256(CONTENT).hexdigest()
    role_dir = project_root / "assets" / "base"
    role_dir.mkdir(parents=True, exist_ok=True)
    colliding = role_dir / f"{expected_sha.upper()}.DWG"
    colliding.write_bytes(b"pre-existing placeholder")
    source = _write_source(tmp_path, "base.dwg", CONTENT)

    response = client.post("/api/assets", json={"role": "base", "source_path": str(source)})

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == ASSET_OUTSIDE_PROJECT
    assert payload["recovery_action"]
    # 既有碰撞文件保持原样，未发生任何改名覆盖。
    assert colliding.read_bytes() == b"pre-existing placeholder"


# ---------------------------------------------------------------------------
# 布局 inspection 端口（Task 7 接真实执行器）
# ---------------------------------------------------------------------------


class _StubInspector:
    """端口签名验证桩：Task 7 以真实 CAD 执行器实现同一协议。"""

    def list_layouts(self, asset: object, cad_version: str) -> tuple[str, ...]:
        assert cad_version == "2020"
        return ("A1", "A2")


def test_inspect_unknown_asset_returns_404(client: TestClient, initialized: None) -> None:
    response = client.post(f"/api/assets/{uuid.uuid4()}/inspect", json={"cad_version": "2020"})

    assert response.status_code == 404
    assert response.json()["code"] == ASSET_NOT_FOUND


def test_inspect_without_wired_port_returns_501(
    client: TestClient, initialized: None, tmp_path: Path
) -> None:
    """端口未接线时固定返回 501 + CAD_VERSION_UNAVAILABLE（本任务裁决）。"""
    source = _write_source(tmp_path, "base.dwg", CONTENT)
    asset = _intake(client, source, role="base")

    response = client.post(f"/api/assets/{asset['id']}/inspect", json={"cad_version": "2020"})

    assert response.status_code == 501
    payload = response.json()
    assert payload["code"] == CAD_VERSION_UNAVAILABLE
    assert payload["recovery_action"]


def test_inspect_with_wired_port_returns_layouts(
    project_root: Path, tmp_path: Path
) -> None:
    client = TestClient(
        create_builder_app(project_root=project_root, layout_inspector=_StubInspector())
    )
    assert client.post("/api/projects", json=PROJECT_BODY).status_code == 201
    source = _write_source(tmp_path, "base.dwg", CONTENT)
    asset = _intake(client, source, role="base")

    response = client.post(f"/api/assets/{asset['id']}/inspect", json={"cad_version": "2020"})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "asset_id": asset["id"],
        "cad_version": "2020",
        "layouts": ["A1", "A2"],
    }
