"""项目内相对路径边界纯函数测试（SPEC-DB-001 §3/§12 / PLAN-DB-001 Task 4）。

覆盖：POSIX/Windows 绝对路径、盘符、``..`` 与非规范段、反斜杠、符号链接与
junction 逃逸、大小写碰撞（Windows casefold）。符号链接与 junction 用例在
无权限环境下如实跳过（Windows 创建符号链接需要管理员或开发者模式）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path, PurePosixPath

import pytest

from dst_builder.domain.paths import (
    ProjectPathError,
    casefold_collisions,
    normalize_relative_path,
    resolve_within_project,
)

# ---------------------------------------------------------------------------
# 规范化：接受的形态
# ---------------------------------------------------------------------------


def test_accepts_normalized_posix_relative_path(tmp_path: Path) -> None:
    relative = "assets/base/3f6b5a246a8e.dwg"

    assert normalize_relative_path(relative) == PurePosixPath(relative)
    resolved = resolve_within_project(tmp_path, relative)
    assert resolved == tmp_path / "assets" / "base" / "3f6b5a246a8e.dwg"


def test_accepts_path_with_existing_directories(tmp_path: Path) -> None:
    (tmp_path / "assets" / "layout").mkdir(parents=True)

    resolved = resolve_within_project(tmp_path, "assets/layout/abc.dwt")

    assert resolved == tmp_path / "assets" / "layout" / "abc.dwt"


# ---------------------------------------------------------------------------
# 规范化：拒绝的形态
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidate",
    [
        "/etc/passwd",
        "//server/share/evil.dwg",
    ],
)
def test_rejects_posix_absolute_paths(candidate: str) -> None:
    with pytest.raises(ProjectPathError):
        normalize_relative_path(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "C:\\evil.dwg",
        "C:/evil.dwg",
        "C:evil.dwg",
    ],
)
def test_rejects_windows_absolute_and_drive_relative_paths(candidate: str) -> None:
    with pytest.raises(ProjectPathError):
        normalize_relative_path(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "../evil.dwg",
        "assets/../../evil.dwg",
        "assets/../base/x.dwg",
    ],
)
def test_rejects_parent_traversal(candidate: str) -> None:
    with pytest.raises(ProjectPathError):
        normalize_relative_path(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "assets\\base\\x.dwg",
        "..\\evil.dwg",
    ],
)
def test_rejects_backslash_separators(candidate: str) -> None:
    with pytest.raises(ProjectPathError):
        normalize_relative_path(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "./x.dwg",
        "assets//x.dwg",
        "assets/",
        " ",
        "",
    ],
)
def test_rejects_non_canonical_segments(candidate: str) -> None:
    with pytest.raises(ProjectPathError):
        normalize_relative_path(candidate)


# ---------------------------------------------------------------------------
# 解析 containment：符号链接 / junction 逃逸
# ---------------------------------------------------------------------------


def _symlink_supported(tmp_path: Path) -> bool:
    try:
        target = tmp_path / "symlink-probe-target"
        target.mkdir()
        link = tmp_path / "symlink-probe"
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    return True


@pytest.fixture()
def require_symlink(tmp_path: Path):
    if not _symlink_supported(tmp_path):
        pytest.skip("当前环境无法创建符号链接（Windows 需要管理员或开发者模式）")
    return tmp_path


def test_rejects_directory_symlink_escape(require_symlink: Path) -> None:
    tmp_path = require_symlink
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "project"
    (root / "assets").mkdir(parents=True)
    os.symlink(outside, root / "link", target_is_directory=True)

    with pytest.raises(ProjectPathError):
        resolve_within_project(root, "link/x.dwg")


def test_rejects_file_symlink_escape(require_symlink: Path) -> None:
    tmp_path = require_symlink
    outside_file = tmp_path / "outside.dwg"
    outside_file.write_bytes(b"outside")
    root = tmp_path / "project"
    (root / "assets" / "base").mkdir(parents=True)
    os.symlink(outside_file, root / "assets" / "base" / "escape.dwg")

    with pytest.raises(ProjectPathError):
        resolve_within_project(root, "assets/base/escape.dwg")


def _create_junction(link: Path, target: Path) -> bool:
    """junction 创建不需要特权；无法创建时如实跳过。"""
    try:
        import _winapi
    except ImportError:
        return False
    try:
        _winapi.CreateJunction(str(target), str(link))
    except OSError:
        return False
    return True


@pytest.mark.skipif(sys.platform != "win32", reason="junction 仅存在于 Windows")
def test_rejects_junction_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "project"
    (root / "assets").mkdir(parents=True)
    if not _create_junction(root / "link", outside):
        pytest.skip("当前环境无法创建 junction")

    with pytest.raises(ProjectPathError):
        resolve_within_project(root, "link/x.dwg")


# ---------------------------------------------------------------------------
# 大小写碰撞（Windows casefold）
# ---------------------------------------------------------------------------


def test_casefold_collisions_finds_case_variants() -> None:
    assert casefold_collisions(["ABC.DWG", "readme.txt"], "abc.dwg") == ("ABC.DWG",)
    assert casefold_collisions(["abc.DWG"], "ABC.dwg") == ("abc.DWG",)


def test_casefold_collisions_ignores_exact_match_and_unrelated() -> None:
    assert casefold_collisions(["abc.dwg"], "abc.dwg") == ()
    assert casefold_collisions(["ABC.DWGX"], "abc.dwg") == ()
    assert casefold_collisions([], "abc.dwg") == ()
