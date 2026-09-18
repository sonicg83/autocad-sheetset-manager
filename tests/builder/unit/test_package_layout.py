"""正式成果布局与完整性校验（RFC-INT-002 / SPEC-DB-001 §9）。

成果目标目录直接包含三件套，不再有 ``drawings/`` 包装层与 ``metadata/``；
``verify_target`` 只断言预期产物存在、可读、非空，不比对内容哈希，也不
约束目录内的其他文件——目标目录就是用户的图纸集工作目录。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from dst_builder.domain.models import (
    DRAFT_SCHEMA_VERSION,
    AssetRole,
    AssetSnapshot,
    GenerationPlanV1,
    NumberingInput,
    ProjectRevisionV1,
    RevisionProject,
    SheetInput,
    TemplateInput,
)
from dst_builder.domain.planning import SHEET_CATALOG_PATH, SHEETSET_PATH, create_plan
from dst_builder.infrastructure.filesystem.package import (
    assemble_package_files,
    verify_target,
)

REVISION_SHA = "a" * 64
DWG_PATH = "A-001 首层平面图.dwg"
DST_BYTES = b"dst-bytes"
DWG_BYTES = b"dwg-bytes"
CATALOG_BYTES = b"xlsx-bytes"


def _make_plan() -> GenerationPlanV1:
    revision = ProjectRevisionV1(
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
    return create_plan(revision)


def _make_files(**overrides) -> dict[str, bytes]:
    kwargs = {
        "plan": _make_plan(),
        "dst_bytes": DST_BYTES,
        "dwg_bytes": DWG_BYTES,
        "catalog_bytes": CATALOG_BYTES,
    }
    kwargs.update(overrides)
    return assemble_package_files(**kwargs)


def _write(root: Path, files: dict[str, bytes]) -> None:
    for path, content in files.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def test_assembled_files_sit_directly_in_target_root() -> None:
    files = _make_files()
    assert set(files) == {"sheetset.dst", DWG_PATH, "图纸目录.xlsx"}
    assert all("/" not in path for path in files)


def test_assembled_bytes_are_bound_to_their_paths() -> None:
    """键与值必须成对：把 catalog 装到 sheetset 键下这类错装必须被抓住。"""
    files = _make_files()
    assert files[SHEETSET_PATH] == DST_BYTES
    assert files[DWG_PATH] == DWG_BYTES
    assert files[SHEET_CATALOG_PATH] == CATALOG_BYTES


def test_plan_expected_artifacts_match_assembled_files() -> None:
    plan = _make_plan()
    files = _make_files(plan=plan)
    assert {artifact.path for artifact in plan.expected_artifacts} == set(files)
    assert {artifact.path: artifact.role for artifact in plan.expected_artifacts} == {
        "sheetset.dst": "dst",
        DWG_PATH: "dwg",
        "图纸目录.xlsx": "sheet-catalog",
    }


def test_assembled_files_are_deterministic() -> None:
    assert _make_files() == _make_files()


def test_verify_target_accepts_complete_target(tmp_path: Path) -> None:
    files = _make_files()
    _write(tmp_path, files)
    assert verify_target(tmp_path, tuple(files)) == ()


def test_verify_target_ignores_unexpected_files(tmp_path: Path) -> None:
    """目标目录就是用户的工作目录：额外文件与子目录不得导致校验失败。"""
    files = _make_files()
    _write(tmp_path, files)
    (tmp_path / "notes.txt").write_text("用户备注", encoding="utf-8")
    (tmp_path / "backup").mkdir()
    (tmp_path / "backup" / "sheetset.bak").write_bytes(b"bak")
    assert verify_target(tmp_path, tuple(files)) == ()


def test_verify_target_does_not_detect_content_change(tmp_path: Path) -> None:
    """改为集合校验后不再比对内容哈希——这是 RFC-INT-002 的有意取舍。"""
    files = _make_files()
    _write(tmp_path, files)
    (tmp_path / "sheetset.dst").write_bytes(b"edited-by-user")
    assert verify_target(tmp_path, tuple(files)) == ()


def test_verify_target_detects_missing_file(tmp_path: Path) -> None:
    files = _make_files()
    _write(tmp_path, files)
    (tmp_path / "图纸目录.xlsx").unlink()
    problems = verify_target(tmp_path, tuple(files))
    assert any("图纸目录.xlsx" in problem for problem in problems)


def test_verify_target_detects_empty_file(tmp_path: Path) -> None:
    files = _make_files()
    _write(tmp_path, files)
    (tmp_path / "sheetset.dst").write_bytes(b"")
    problems = verify_target(tmp_path, tuple(files))
    assert any("sheetset.dst" in problem for problem in problems)


def test_verify_target_rejects_empty_expected_set(tmp_path: Path) -> None:
    """空预期集合是发布证据缺失，不得静默放行。"""
    files = _make_files()
    _write(tmp_path, files)
    assert verify_target(tmp_path, ()) == ("发布证据缺少预期产物清单",)
