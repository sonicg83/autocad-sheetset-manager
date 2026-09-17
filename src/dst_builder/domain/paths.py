"""项目内相对路径边界（SPEC-DB-001 §3/§12）：路径合法性判定与解析 containment。

全部为无副作用的判定函数；``resolve_within_project`` 只读文件系统以解析
符号链接/junction（不创建、不修改任何路径）。``models`` 只保存 POSIX 相对
路径；绝对路径、``..``、反斜杠分隔符、盘符、非规范段与本函数族产生的越界
判定一律以 ``ProjectPathError``（§11 ``ASSET_OUTSIDE_PROJECT``）拒绝。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath

__all__ = [
    "ASSET_OUTSIDE_PROJECT",
    "ProjectPathError",
    "casefold_collisions",
    "normalize_relative_path",
    "resolve_within_project",
]

ASSET_OUTSIDE_PROJECT = "ASSET_OUTSIDE_PROJECT"


class ProjectPathError(ValueError):
    """项目内相对路径越界（绝对路径、``..``、符号链接逃逸、大小写碰撞等）。"""

    code = ASSET_OUTSIDE_PROJECT


def normalize_relative_path(candidate: str) -> PurePosixPath:
    """把候选路径校验为规范的 POSIX 相对路径并返回。

    拒绝：空串与首尾空白、反斜杠分隔符、POSIX/Windows 绝对路径、盘符
    （含盘符相对形态 ``C:foo``）、``..`` / ``.`` / 空段。Windows 文件系统
    大小写不敏感由 ``casefold_collisions`` 单独处理。
    """
    if not candidate or candidate.strip() != candidate:
        raise ProjectPathError(f"路径不能为空或含首尾空白：{candidate!r}")
    if "\\" in candidate:
        raise ProjectPathError(f"路径必须使用 POSIX 分隔符：{candidate!r}")
    if PurePosixPath(candidate).is_absolute():
        raise ProjectPathError(f"拒绝绝对路径：{candidate!r}")
    windows = PureWindowsPath(candidate)
    if windows.is_absolute() or windows.drive:
        raise ProjectPathError(f"拒绝 Windows 绝对或盘符路径：{candidate!r}")
    if any(part in ("", ".", "..") for part in candidate.split("/")):
        raise ProjectPathError(f"路径段不得为空、'.' 或 '..'：{candidate!r}")
    return PurePosixPath(candidate)


def resolve_within_project(root: Path, candidate: str) -> Path:
    """校验候选相对路径解析后仍位于项目根内，返回项目根下的字面路径。

    已存在前缀（含符号链接/junction）按真实解析参与 containment 检查；
    尚不存在的尾段按字面拼接。``root`` 先 ``resolve()``，保证根路径自身的
    符号链接成分不参与判定。
    """
    relative = normalize_relative_path(candidate)
    root_resolved = Path(root).resolve()
    literal = root_resolved.joinpath(*relative.parts)
    resolved = literal.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise ProjectPathError(f"路径解析后越出项目根：{candidate!r}") from None
    return literal


def casefold_collisions(existing: Iterable[str], candidate: str) -> tuple[str, ...]:
    """返回与 ``candidate`` 仅大小写不同的既有名称（Windows casefold 碰撞）。

    Windows 文件系统大小写不敏感：仅大小写不同的名称不能共存，内容寻址名
    落盘前必须排除这类碰撞。与 ``candidate`` 完全同名的既有项不算碰撞。
    """
    folded = candidate.casefold()
    return tuple(name for name in existing if name != candidate and name.casefold() == folded)
