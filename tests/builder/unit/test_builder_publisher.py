"""发布器单元测试（SPEC-DB-001 §9 / PLAN-DB-001 Task 9）。

覆盖：暂存目录唯一且位于目标父目录、目标预存在拒绝且不修改、
改名失败清理暂存且目标不存在、父目录缺失拒绝发布。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import dst_builder.infrastructure.filesystem.publisher as publisher_module
from dst_builder.infrastructure.filesystem.publisher import (
    PackagePublishError,
    PackageTargetExistsError,
    publish_candidate,
)

_DST = b"dst"
_FILES = {
    "sheetset.dst": _DST,
    "A-001 平面.dwg": b"dwg",
    "图纸目录.xlsx": b"xlsx",
}
FILES = _FILES


def _publish(tmp_path: Path, target: Path) -> Path:
    return publish_candidate(FILES, target, staging=tmp_path / ".staging")


def test_publish_places_complete_package_at_target(tmp_path: Path) -> None:
    target = tmp_path / "deliveries" / "example-package"
    target.parent.mkdir(parents=True)

    published = _publish(tmp_path, target)

    assert published == target
    assert {path.read_bytes() for path in target.iterdir()} == set(_FILES.values())
    # 正式成果直接落在目标目录，无包装子目录、无空 assets 目录。
    assert sorted(item.name for item in target.iterdir()) == [
        "A-001 平面.dwg",
        "sheetset.dst",
        "图纸目录.xlsx",
    ]
    # 唯一暂存目录已消失。
    assert not (tmp_path / ".staging").exists()
    assert [item.name for item in target.parent.iterdir()] == [target.name]


def test_publish_rejects_existing_target_without_modifying_it(tmp_path: Path) -> None:
    target = tmp_path / "example-package"
    target.mkdir()
    (target / "user-file.txt").write_bytes(b"user data")

    with pytest.raises(PackageTargetExistsError):
        _publish(tmp_path, target)

    # 目标未被修改，也未留下暂存目录。
    assert (target / "user-file.txt").read_bytes() == b"user data"
    assert sorted(item.name for item in target.iterdir()) == ["user-file.txt"]


def test_publish_cleans_staging_when_rename_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "example-package"
    staging = tmp_path / ".staging"

    def broken_replace(source: Path, destination: Path) -> None:
        assert source == staging
        raise OSError("跨卷/占用")

    monkeypatch.setattr(publisher_module.os, "replace", broken_replace)

    with pytest.raises(PackagePublishError):
        _publish(tmp_path, target)

    assert not staging.exists()
    assert not target.exists()


def test_publish_requires_existing_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "missing-parent" / "example-package"

    with pytest.raises(PackagePublishError):
        _publish(tmp_path, target)

    assert not target.exists()
    assert not (tmp_path / ".staging").exists()
