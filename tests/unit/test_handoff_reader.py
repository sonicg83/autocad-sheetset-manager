"""Manager 交接读取器验证（SPEC-DB-001 §9/§10，PLAN-DB-001 Task 10）。

读取器是纯只读验证：对 Builder 发布的成果包（真实 DST/DWG/XLSX 字节）按
§10 六步顺序验证，任何失败都抛 :class:`HandoffPackageError` 且绝不写盘。
成果包由 tests/handoff_package_factory.py 用真实 Builder 工厂合成。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path, PureWindowsPath

import pytest
from handoff_package_factory import (
    BUILD_ID,
    DWG_CONTENT,
    entry_by_path,
    make_builder_package,
    manifest_entries,
    reseal_package,
)

from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.dst_codec import DstCodec as ManagerDstCodec
from dst_manager.infrastructure.handoff.reader import (
    HandoffPackageError,
    read_handoff_package,
)
from dst_platform.acsm.codec import DstCodec as PlatformDstCodec

# ---------------------------------------------------------------------------
# 成功路径
# ---------------------------------------------------------------------------


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "example-package"
    make_builder_package(root)
    return root


def test_valid_package_is_read_with_projection(package: Path) -> None:
    handoff = json.loads((package / "metadata" / "handoff.json").read_text(encoding="utf-8"))
    manifest_sha256 = hashlib.sha256((package / "metadata" / "manifest.json").read_bytes()).hexdigest()

    result = read_handoff_package(package / "metadata" / "handoff.json")

    assert result.root == package
    assert result.package_id == handoff["package_id"]
    assert result.package_id == str(
        uuid.uuid5(uuid.NAMESPACE_URL, "dst-builder:package:" + manifest_sha256)
    )
    assert result.build_id == BUILD_ID
    assert result.plan_id
    assert result.manifest_sha256 == manifest_sha256
    assert result.dst_relative == "drawings/sheetset.dst"
    assert result.dst_path == package / "drawings" / "sheetset.dst"
    assert result.dst_sha256 == hashlib.sha256(
        (package / "drawings" / "sheetset.dst").read_bytes()
    ).hexdigest()
    assert [entry["path"] for entry in result.entries] == sorted(
        entry["path"] for entry in result.entries
    )
    # Manager 只读投影：唯一图纸的 DWG 解析到包内 drawings/ 且与登记一致
    assert len(result.document.sheets) == 1
    resolved = result.document.sheets[0].layout.resolved_path
    assert resolved is not None
    assert resolved == (package / entry_by_path(package, "drawings/A-001 首层平面图.dwg")["path"]).resolve()


def test_relative_handoff_path_is_rejected(package: Path) -> None:
    with pytest.raises(HandoffPackageError):
        read_handoff_package(Path("metadata") / "handoff.json")


def test_missing_handoff_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(HandoffPackageError):
        read_handoff_package(tmp_path / "nowhere" / "metadata" / "handoff.json")


def test_handoff_outside_metadata_layout_is_rejected(package: Path) -> None:
    misplaced = package / "handoff.json"
    misplaced.write_bytes((package / "metadata" / "handoff.json").read_bytes())

    with pytest.raises(HandoffPackageError):
        read_handoff_package(misplaced)


def test_unexpected_top_level_directory_is_rejected(package: Path) -> None:
    (package / "assets").mkdir()

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


# ---------------------------------------------------------------------------
# Schema 与完整性
# ---------------------------------------------------------------------------


def test_unknown_handoff_schema_is_rejected(package: Path) -> None:
    handoff_path = package / "metadata" / "handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["schema"] = "dst-builder.handoff/v2"
    handoff_path.write_bytes(json.dumps(handoff, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    with pytest.raises(HandoffPackageError, match="Schema"):
        read_handoff_package(handoff_path)


def test_manifest_hash_drift_is_rejected(package: Path) -> None:
    # 漂移 manifest 登记的文件内容，但不重算 handoff 的 manifest_sha256
    target = package / entry_by_path(package, "metadata/validation-report.json")["path"]
    target.write_bytes(target.read_bytes() + b"drift")

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_wrong_manifest_hash_in_handoff_is_rejected(package: Path) -> None:
    handoff_path = package / "metadata" / "handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["manifest_sha256"] = "0" * 64
    handoff_path.write_bytes(json.dumps(handoff, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    with pytest.raises(HandoffPackageError):
        read_handoff_package(handoff_path)


def test_missing_registered_file_is_rejected(package: Path) -> None:
    (package / entry_by_path(package, "drawings/图纸目录.xlsx")["path"]).unlink()

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_registered_file_size_drift_is_rejected(package: Path) -> None:
    entry = entry_by_path(package, "metadata/project-revision.json")
    reseal_package(
        package,
        patch=lambda item: item | {"size": item["size"] + 1}
        if item["path"] == entry["path"]
        else item,
    )

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_registered_file_hash_drift_is_rejected(package: Path) -> None:
    entry = entry_by_path(package, "metadata/project-revision.json")
    target = package / entry["path"]
    target.write_bytes(target.read_bytes()[:-1] + b"~")
    reseal_package(
        package,
        patch=lambda item: item | {"sha256": "f" * 64}
        if item["path"] == entry["path"]
        else item,
    )

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_unregistered_extra_file_is_rejected(package: Path) -> None:
    (package / "drawings" / "extra.txt").write_bytes(b"sneaky")

    with pytest.raises(HandoffPackageError, match="未登记"):
        read_handoff_package(package / "metadata" / "handoff.json")


# ---------------------------------------------------------------------------
# 路径逃逸
# ---------------------------------------------------------------------------


def _replace_entry(package: Path, relative: str, replacement: dict) -> None:
    entries = manifest_entries(package)
    index = next(position for position, item in enumerate(entries) if item["path"] == relative)
    entries[index] = replacement
    reseal_package(package, entries=entries)


def test_absolute_manifest_entry_is_rejected(package: Path) -> None:
    _replace_entry(
        package,
        "metadata/project-revision.json",
        {"path": "C:/evil/project-revision.json", "role": "metadata", "size": 1, "sha256": "a" * 64},
    )

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_dotdot_manifest_entry_is_rejected(package: Path) -> None:
    _replace_entry(
        package,
        "metadata/project-revision.json",
        {"path": "metadata/../outside.json", "role": "metadata", "size": 1, "sha256": "a" * 64},
    )

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_symlink_escape_is_rejected(package: Path) -> None:
    outside = package.parent / "outside.dwg"
    outside.write_bytes(DWG_CONTENT)
    dwg_relative = entry_by_path(package, "drawings/A-001 首层平面图.dwg")["path"]
    (package / dwg_relative).unlink()
    try:
        os.symlink(outside, package / dwg_relative)
    except OSError:  # pragma: no cover - 无符号链接特权的环境
        pytest.skip("当前环境不允许创建符号链接")

    with pytest.raises(HandoffPackageError, match="符号链接"):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_case_collision_between_entries_is_rejected(package: Path) -> None:
    entries = manifest_entries(package)
    original = entries[0]
    colliding = dict(original)
    colliding["path"] = original["path"].replace(
        original["path"].split("/")[-1], original["path"].split("/")[-1].swapcase()
    )
    reseal_package(package, entries=[*entries, colliding])

    with pytest.raises(HandoffPackageError, match="大小写"):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_case_mismatch_against_disk_is_rejected(package: Path) -> None:
    entry = entry_by_path(package, "metadata/project-revision.json")
    entries = manifest_entries(package)
    for item in entries:
        if item["path"] == entry["path"]:
            item["path"] = "metadata/Project-Revision.json"
    reseal_package(package, entries=entries)

    with pytest.raises(HandoffPackageError, match="大小写"):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_purewindows_drive_style_entry_is_rejected(package: Path) -> None:
    assert PureWindowsPath("metadata/x.json").drive == ""
    entry = entry_by_path(package, "metadata/project-revision.json")
    entries = manifest_entries(package)
    for item in entries:
        if item["path"] == entry["path"]:
            item["path"] = "metadata\\..\\..\\evil.json"
    reseal_package(package, entries=entries)

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


# ---------------------------------------------------------------------------
# DST 只读投影一致性
# ---------------------------------------------------------------------------


def _rewrite_dst_reference(package: Path, new_relative: str) -> None:
    dst = package / "drawings" / "sheetset.dst"
    document = AcsmDocument(ManagerDstCodec().decode_file(dst))
    layout = document.root.xpath("//*[local-name()='AcSmAcDbLayoutReference']")[0]
    for prop_name in ("FileName", "Relative_FileName"):
        layout.xpath(f"./*[local-name()='AcSmProp' and @propname='{prop_name}']")[0].text = (
            new_relative
        )
    PlatformDstCodec().encode_file(document.to_bytes(), dst)


def test_dst_reference_outside_drawings_is_rejected(package: Path) -> None:
    outside = package.parent / "escaped.dwg"
    outside.write_bytes(DWG_CONTENT)
    # DST 引用相对 drawings/ 解析：../../ 越出成果包根
    _rewrite_dst_reference(package, "../../escaped.dwg")
    reseal_package(package)
    assert outside.is_file()

    with pytest.raises(HandoffPackageError, match="drawings"):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_dst_reference_to_unregistered_file_is_rejected(package: Path) -> None:
    (package / "drawings" / "ghost.dwg").write_bytes(DWG_CONTENT)
    _rewrite_dst_reference(package, "./ghost.dwg")
    reseal_package(package)  # ghost.dwg 保持未登记 → census 拒绝

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")


def test_corrupted_dst_is_rejected(package: Path) -> None:
    dst = package / "drawings" / "sheetset.dst"
    dst.write_bytes(dst.read_bytes()[:-16] + b"\x00" * 16)
    reseal_package(package)

    with pytest.raises(HandoffPackageError):
        read_handoff_package(package / "metadata" / "handoff.json")
