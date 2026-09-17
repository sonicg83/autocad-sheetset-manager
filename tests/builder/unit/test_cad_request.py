"""CadDrawingRequestV1 / CadDrawingResultV1 结构化契约测试（SPEC-DB-001 §7）。

覆盖：request/result Schema 严格性（未知 Schema、未知字段拒绝）、项目内路径
约束（``resolve_within_project`` 复用）、attempt 目录内路径约束（attempt 目录
逃逸拒绝）、布局名门禁（``Model`` 保留名、危险字符、源目标同名）。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from dst_builder.domain.models import AssetRole, AssetSnapshot, DrawingTask
from dst_builder.infrastructure.autocad.request import (
    CAD_DRAWING_REQUEST_SCHEMA,
    CAD_DRAWING_RESULT_SCHEMA,
    CAD_INSPECT_REQUEST_SCHEMA,
    CAD_INSPECT_RESULT_SCHEMA,
    AttemptPaths,
    CadDrawingRequestError,
    CadDrawingRequestV1,
    CadDrawingResultV1,
    CadInspectRequestV1,
    CadInspectResultV1,
)

BASE_SHA = "a" * 64
LAYOUT_SHA = "b" * 64
BASE_CONTENT = b"base dwg bytes"
LAYOUT_CONTENT = b"layout asset bytes"


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    base_dir = root / "assets" / "base"
    layout_dir = root / "assets" / "layout"
    base_dir.mkdir(parents=True, exist_ok=True)
    layout_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / f"base-{BASE_SHA}.dwg").write_bytes(BASE_CONTENT)
    (layout_dir / f"layout-{LAYOUT_SHA}.dwg").write_bytes(LAYOUT_CONTENT)
    return root


def make_task(
    *,
    source_layout: str = "平面",
    target_layout: str = "001 平面",
    target_dwg_path: str = "drawings/001 平面.dwg",
    layout_asset_path: str = f"assets/layout/layout-{LAYOUT_SHA}.dwg",
    base_asset_path: str = f"assets/base/base-{BASE_SHA}.dwg",
) -> DrawingTask:
    return DrawingTask(
        task_id="task-1",
        base_asset=AssetSnapshot(
            role=AssetRole.BASE, relative_path=base_asset_path, sha256=BASE_SHA, size=len(BASE_CONTENT)
        ),
        layout_asset=AssetSnapshot(
            role=AssetRole.LAYOUT,
            relative_path=layout_asset_path,
            sha256=LAYOUT_SHA,
            size=len(LAYOUT_CONTENT),
        ),
        source_layout=source_layout,
        target_layout=target_layout,
        target_dwg_path=target_dwg_path,
    )


def make_request(tmp_path: Path, **task_kwargs: str) -> tuple[CadDrawingRequestV1, Path, AttemptPaths]:
    root = make_project(tmp_path)
    attempt = AttemptPaths.create(tmp_path / "attempt")
    request = CadDrawingRequestV1.create(
        task=make_task(**task_kwargs), attempt=attempt, project_root=root
    )
    return request, root, attempt


# ---------------------------------------------------------------------------
# AttemptPaths：attempt 目录内路径约束
# ---------------------------------------------------------------------------


def test_attempt_paths_derive_fixed_names(tmp_path: Path) -> None:
    attempt = AttemptPaths.create(tmp_path / "attempt")

    assert attempt.attempt_dir == tmp_path / "attempt"
    assert attempt.working_dwg.parent == attempt.attempt_dir
    assert attempt.request_json.parent == attempt.attempt_dir
    assert attempt.result_json.parent == attempt.attempt_dir
    assert attempt.script.parent == attempt.attempt_dir
    assert attempt.working_dwg.suffix == ".dwg"
    assert attempt.request_json.suffix == ".json"
    assert attempt.result_json.suffix == ".json"
    assert attempt.script.suffix == ".scr"


def test_attempt_paths_reject_escape_from_attempt_dir(tmp_path: Path) -> None:
    """四个 attempt 内路径任一逃逸 attempt 目录都拒绝（§7 路径约束）。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    attempt_dir = tmp_path / "attempt"

    with pytest.raises(CadDrawingRequestError):
        AttemptPaths(
            attempt_dir=attempt_dir,
            working_dwg=outside / "working.dwg",
            request_json=attempt_dir / "cad-drawing-request.json",
            result_json=attempt_dir / "cad-drawing-result.json",
            script=attempt_dir / "cad-drawing.scr",
        )

    with pytest.raises(CadDrawingRequestError):
        AttemptPaths(
            attempt_dir=attempt_dir,
            working_dwg=attempt_dir / "working.dwg",
            request_json=tmp_path / "elsewhere" / "request.json",
            result_json=attempt_dir / "cad-drawing-result.json",
            script=attempt_dir / "cad-drawing.scr",
        )


# ---------------------------------------------------------------------------
# CadDrawingRequestV1.create：项目内路径约束与布局名门禁
# ---------------------------------------------------------------------------


def test_request_create_happy_path(tmp_path: Path) -> None:
    request, _, attempt = make_request(tmp_path)

    assert request.schema == CAD_DRAWING_REQUEST_SCHEMA
    uuid.UUID(request.request_id)  # 合法 UUIDv4
    assert request.base_dwg == attempt.working_dwg
    assert request.result_json == attempt.result_json
    assert request.layout_asset == f"assets/layout/layout-{LAYOUT_SHA}.dwg"
    assert request.source_layout == "平面"
    assert request.target_layout == "001 平面"


def test_request_create_rejects_layout_asset_outside_project(tmp_path: Path) -> None:
    with pytest.raises(CadDrawingRequestError):
        make_request(tmp_path, layout_asset_path="../outside.dwg")


def test_request_create_rejects_absolute_layout_asset(tmp_path: Path) -> None:
    with pytest.raises(CadDrawingRequestError):
        make_request(tmp_path, layout_asset_path="C:/evil/asset.dwg")


def test_request_create_rejects_target_dwg_outside_project(tmp_path: Path) -> None:
    with pytest.raises(CadDrawingRequestError):
        make_request(tmp_path, target_dwg_path="drawings/../../evil.dwg")


def test_request_create_rejects_base_asset_outside_project(tmp_path: Path) -> None:
    with pytest.raises(CadDrawingRequestError):
        make_request(tmp_path, base_asset_path="../../evil.dwg")


@pytest.mark.parametrize("name", ["Model", "model", "MODEL"])
def test_request_create_rejects_model_as_target(tmp_path: Path, name: str) -> None:
    with pytest.raises(CadDrawingRequestError):
        make_request(tmp_path, target_layout=name)


@pytest.mark.parametrize("name", ["Model", "model"])
def test_request_create_rejects_model_as_source(tmp_path: Path, name: str) -> None:
    with pytest.raises(CadDrawingRequestError):
        make_request(tmp_path, source_layout=name)


def test_request_create_rejects_unsafe_layout_names(tmp_path: Path) -> None:
    for name in ("平面\n_.QUIT", '引"号', "斜杠/名", "  ", ""):
        with pytest.raises(CadDrawingRequestError):
            make_request(tmp_path, target_layout=name)


def test_request_create_rejects_source_equals_target(tmp_path: Path) -> None:
    with pytest.raises(CadDrawingRequestError):
        make_request(tmp_path, source_layout="同名", target_layout="同名")


def test_request_payload_roundtrip(tmp_path: Path) -> None:
    request, _, _ = make_request(tmp_path)

    payload = request.to_payload()
    assert set(payload) == {
        "schema",
        "request_id",
        "base_dwg",
        "layout_asset",
        "layout_asset_path",
        "source_layout",
        "target_layout",
        "result_json",
    }
    assert CadDrawingRequestV1.from_payload(payload) == request


def test_request_from_payload_rejects_unknown_schema(tmp_path: Path) -> None:
    request, _, _ = make_request(tmp_path)
    payload = request.to_payload()
    payload["schema"] = "dst-builder.cad-drawing-request/v2"

    with pytest.raises(CadDrawingRequestError):
        CadDrawingRequestV1.from_payload(payload)


def test_request_from_payload_rejects_unknown_fields(tmp_path: Path) -> None:
    request, _, _ = make_request(tmp_path)
    payload = request.to_payload()
    payload["extra"] = "injected"

    with pytest.raises(CadDrawingRequestError):
        CadDrawingRequestV1.from_payload(payload)


def test_request_from_payload_rejects_missing_fields(tmp_path: Path) -> None:
    request, _, _ = make_request(tmp_path)
    payload = request.to_payload()
    del payload["target_layout"]

    with pytest.raises(CadDrawingRequestError):
        CadDrawingRequestV1.from_payload(payload)


# ---------------------------------------------------------------------------
# CadDrawingResultV1.from_payload：结果 Schema 与 Handle 门禁
# ---------------------------------------------------------------------------


def make_result_payload(**overrides: object) -> dict:
    payload: dict[str, object] = {
        "schema": CAD_DRAWING_RESULT_SCHEMA,
        "request_id": str(uuid.uuid4()),
        "layout_name": "001 平面",
        "layout_handle": "2F",
        "database_version": "AC1027",
        "layouts": ["001 平面"],
        "diagnostics": [],
    }
    payload.update(overrides)
    return payload


def test_result_from_payload_happy_path() -> None:
    payload = make_result_payload(
        diagnostics=[{"code": "D1", "severity": "info", "message": "提示"}]
    )
    result = CadDrawingResultV1.from_payload(payload)

    assert result.schema == CAD_DRAWING_RESULT_SCHEMA
    assert result.layout_handle == "2F"
    assert result.layouts == ("001 平面",)
    assert result.diagnostics[0].code == "D1"
    assert result.dwg_size is None
    assert result.dwg_sha256 is None


def test_result_from_payload_accepts_lowercase_handle() -> None:
    result = CadDrawingResultV1.from_payload(make_result_payload(layout_handle="abc"))

    assert result.layout_handle == "ABC"


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema": "dst-builder.cad-drawing-result/v2"},
        {"schema": 1},
        {"layout_handle": ""},
        {"layout_handle": "GG12"},
        {"layout_handle": "2F 3A"},
        {"layouts": "001 平面"},
        {"layouts": ["001 平面", 7]},
        {"diagnostics": [{"code": "D", "severity": "fatal", "message": "m"}]},
        {"extra": 1},
    ],
)
def test_result_from_payload_rejects_invalid_payloads(overrides: dict) -> None:
    with pytest.raises(CadDrawingRequestError):
        CadDrawingResultV1.from_payload(make_result_payload(**overrides))


def test_result_from_payload_rejects_missing_field() -> None:
    payload = make_result_payload()
    del payload["database_version"]

    with pytest.raises(CadDrawingRequestError):
        CadDrawingResultV1.from_payload(payload)


# ---------------------------------------------------------------------------
# inspect 请求/结果契约
# ---------------------------------------------------------------------------


def test_inspect_request_roundtrip(tmp_path: Path) -> None:
    request = CadInspectRequestV1.create(result_json=tmp_path / "inspect-result.json")

    assert request.schema == CAD_INSPECT_REQUEST_SCHEMA
    payload = request.to_payload()
    assert set(payload) == {"schema", "request_id", "result_json"}
    assert CadInspectRequestV1.from_payload(payload) == request


def test_inspect_request_rejects_unknown_schema(tmp_path: Path) -> None:
    request = CadInspectRequestV1.create(result_json=tmp_path / "inspect-result.json")
    payload = request.to_payload()
    payload["schema"] = "other/v1"

    with pytest.raises(CadDrawingRequestError):
        CadInspectRequestV1.from_payload(payload)


def test_inspect_result_from_payload() -> None:
    result = CadInspectResultV1.from_payload(
        {
            "schema": CAD_INSPECT_RESULT_SCHEMA,
            "request_id": str(uuid.uuid4()),
            "layouts": ["A1", "A2"],
        }
    )

    assert result.layouts == ("A1", "A2")


@pytest.mark.parametrize(
    "payload",
    [
        {"schema": "other/v1", "request_id": str(uuid.uuid4()), "layouts": []},
        {"schema": CAD_INSPECT_RESULT_SCHEMA, "request_id": str(uuid.uuid4()), "layouts": "A1"},
        {"schema": CAD_INSPECT_RESULT_SCHEMA, "request_id": str(uuid.uuid4()), "layouts": [1]},
        {"schema": CAD_INSPECT_RESULT_SCHEMA, "request_id": str(uuid.uuid4())},
    ],
)
def test_inspect_result_rejects_invalid_payloads(payload: dict) -> None:
    with pytest.raises(CadDrawingRequestError):
        CadInspectResultV1.from_payload(payload)
