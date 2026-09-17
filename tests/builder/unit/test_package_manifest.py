"""manifest / handoff 生成单元测试（SPEC-DB-001 §9 / PLAN-DB-001 Task 9）。

覆盖：manifest 排序与内容、handoff 的 package_id 派生与互斥性、
成果包根目录约定（只有 drawings/ 与 metadata/，无空 assets 目录）、
确定性（固定 created_at 后字节级一致）与 verify_package 完整性校验。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from dst_builder.domain.models import (
    DRAFT_SCHEMA_VERSION,
    MANIFEST_SCHEMA,
    AssetRole,
    AssetSnapshot,
    GenerationPlanV1,
    NumberingInput,
    ProjectRevisionV1,
    RevisionProject,
    SheetInput,
    TemplateInput,
)
from dst_builder.domain.planning import create_plan
from dst_builder.infrastructure.filesystem.package import (
    HANDOFF_FILE,
    MANIFEST_FILE,
    assemble_package_files,
    manifest_sha256_of,
    verify_package,
)

REVISION_SHA = "a" * 64


def _make_revision() -> ProjectRevisionV1:
    return ProjectRevisionV1(
        schema_version=DRAFT_SCHEMA_VERSION,
        ruleset_version=1,
        project=RevisionProject(name="示例工程", stage="施工图", discipline="建筑"),
        numbering=NumberingInput(prefix="A-", start=1, width=3),
        cad_version="2020",
        sheets=(SheetInput(title="首层平面图"),),
        template=TemplateInput(
            base_asset_id="3f6b5a24-6a8e-4c2a-9c8f-0f5d7a1b2c31",
            layout_asset_id="8c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
            source_layout="A1",
        ),
        assets=(
            AssetSnapshot(role=AssetRole.BASE, relative_path="assets/base/x.dwg", sha256="a" * 64, size=10),
            AssetSnapshot(role=AssetRole.LAYOUT, relative_path="assets/layout/y.dwg", sha256="b" * 64, size=20),
        ),
        revision_sha256=REVISION_SHA,
        revision_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"dst-builder:revision:{REVISION_SHA}")),
    )


def _make_plan() -> GenerationPlanV1:
    return create_plan(_make_revision())


def _make_files(**overrides) -> dict[str, bytes]:
    """组装一套候选包字节（固定 created_at 保证确定性）。"""
    plan = _make_plan()
    kwargs = {
        "plan": plan,
        "revision_json": '{"schema_version":1}',
        "plan_json": '{"schema_version":1,"plan":true}',
        "report_json": '{"schema":"dst-builder.validation-report/v1"}',
        "dst_bytes": b"dst-bytes",
        "dwg_bytes": b"dwg-bytes",
        "catalog_bytes": b"xlsx-bytes",
        "build_id": "11111111-1111-1111-1111-111111111111",
        "builder_version": "0.3.5",
        "created_at": "2026-09-17T00:00:00+00:00",
    }
    kwargs.update(overrides)
    return assemble_package_files(**kwargs)


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------


def test_manifest_entries_sorted_with_correct_size_and_sha256() -> None:
    files = _make_files()
    manifest = json.loads(files[MANIFEST_FILE])
    assert manifest["schema"] == MANIFEST_SCHEMA == "dst-builder.manifest/v1"

    entries = manifest["files"]
    paths = [entry["path"] for entry in entries]
    assert paths == sorted(paths)
    for entry in entries:
        content = files[entry["path"]]
        assert entry["size"] == len(content)
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        assert set(entry) == {"path", "role", "size", "sha256"}


def test_manifest_excludes_itself_and_handoff() -> None:
    files = _make_files()
    manifest = json.loads(files[MANIFEST_FILE])
    paths = {entry["path"] for entry in manifest["files"]}
    assert MANIFEST_FILE not in paths
    assert HANDOFF_FILE not in paths
    # 全部七个正式文件中除 manifest/handoff 外都在 manifest 中
    assert paths == {
        "drawings/sheetset.dst",
        "drawings/A-001 首层平面图.dwg",
        "drawings/图纸目录.xlsx",
        "metadata/project-revision.json",
        "metadata/generation-plan.json",
        "metadata/validation-report.json",
    }


def test_manifest_roles_match_plan_expected_artifacts() -> None:
    plan = _make_plan()
    files = _make_files(plan=plan)
    manifest = json.loads(files[MANIFEST_FILE])
    roles = {entry["path"]: entry["role"] for entry in manifest["files"]}
    for artifact in plan.expected_artifacts:
        if artifact.path in (MANIFEST_FILE, HANDOFF_FILE):
            continue
        assert roles[artifact.path] == artifact.role


def test_manifest_sha_matches_file_bytes() -> None:
    files = _make_files()
    assert manifest_sha256_of(files) == hashlib.sha256(files[MANIFEST_FILE]).hexdigest()


# ---------------------------------------------------------------------------
# handoff
# ---------------------------------------------------------------------------


def test_handoff_package_id_is_derived_from_manifest_sha256() -> None:
    files = _make_files()
    manifest_sha256 = manifest_sha256_of(files)
    handoff = json.loads(files[HANDOFF_FILE])
    expected_package_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"dst-builder:package:{manifest_sha256}")
    )
    assert handoff["schema"] == "dst-builder.handoff/v1"
    assert handoff["package_id"] == expected_package_id
    assert handoff["build_id"] == "11111111-1111-1111-1111-111111111111"
    assert handoff["plan_id"]
    assert handoff["manifest_path"] == "metadata/manifest.json"
    assert handoff["manifest_sha256"] == manifest_sha256
    assert handoff["dst_path"] == "drawings/sheetset.dst"
    assert handoff["created_at"] == "2026-09-17T00:00:00+00:00"
    assert handoff["builder_version"] == "0.3.5"


def test_assembled_files_live_only_under_drawings_and_metadata() -> None:
    files = _make_files()
    for path in files:
        assert path.startswith(("drawings/", "metadata/"))
    # 七个正式文件 + manifest 本身 = 8
    assert len(files) == 8


def test_assembled_files_are_deterministic_with_fixed_created_at() -> None:
    assert _make_files() == _make_files()


# ---------------------------------------------------------------------------
# verify_package
# ---------------------------------------------------------------------------


def test_verify_package_accepts_complete_package(tmp_path: Path) -> None:
    files = _make_files()
    for path, content in files.items():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    assert verify_package(tmp_path) == ()


def test_verify_package_detects_tampered_file(tmp_path: Path) -> None:
    files = _make_files()
    for path, content in files.items():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (tmp_path / "drawings/sheetset.dst").write_bytes(b"tampered")

    problems = verify_package(tmp_path)
    assert problems
    assert any("sheetset.dst" in problem for problem in problems)


def test_verify_package_detects_missing_file(tmp_path: Path) -> None:
    files = _make_files()
    for path, content in files.items():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (tmp_path / "metadata/generation-plan.json").unlink()

    problems = verify_package(tmp_path)
    assert any("generation-plan.json" in problem for problem in problems)
