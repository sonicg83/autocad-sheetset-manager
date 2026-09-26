"""标准资产路径解析与文件集合校验（PLAN-DM-040 Task 2）。

标准文档只保存包内相对路径；资产文件必须落在受控根目录内、真实存在，
并与包清单一一对应。发布、导入与导出共用本模块的三重门禁：

- 路径合法：非空、非绝对/UNC、无空段与 ``.``/``..`` 分量、解析后仍在根内
  （符号链接不得指向受控目录之外）；
- 文件存在：声明的每个文件都落在受控根目录里；
- 清单一致：包内条目与清单声明双向相等，不夹带未声明的载荷。

失败复用既有 ``STANDARD_ASSET_PATH_INVALID``、``STANDARD_ASSET_FILE_MISSING``
与 ``STANDARD_PACKAGE_INVALID`` 稳定码，不新增错误码。
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path, PureWindowsPath

from dst_manager.domain.standards import DrawingStandard

PATH_INVALID = "STANDARD_ASSET_PATH_INVALID"
FILE_MISSING = "STANDARD_ASSET_FILE_MISSING"
PACKAGE_INCONSISTENT = "STANDARD_PACKAGE_INVALID"


class StandardAssetError(Exception):
    """资产门禁失败；消息以稳定错误码开头，由调用方转成各自层次的错误类型。"""


def _error(code: str, detail: str) -> StandardAssetError:
    return StandardAssetError(f"{code}: {detail}")


def normalize_asset_path(relative: str) -> str:
    """校验并归一化包内资产相对路径；任何逃逸形态都不接受。

    先按分量校验再拼接，绝不对含 ``..`` 的输入做「先归一化再检查」，否则
    ``assets/../A2.dwg`` 会被洗成合法路径（F15）。
    """
    if not isinstance(relative, str) or not relative:
        raise _error(PATH_INVALID, "资产文件路径不得为空")
    if relative.startswith(("/", "\\")) or PureWindowsPath(relative).drive:
        raise _error(
            PATH_INVALID, f"资产文件路径 {relative!r} 不得为绝对路径或 UNC 路径"
        )
    parts = relative.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise _error(PATH_INVALID, f"资产文件路径 {relative!r} 含空段或相对分量")
    return "/".join(parts)


def resolve_asset_file(root: Path, relative: str) -> Path:
    """把资产相对路径解析到受控根目录内；解析结果不得越出根目录。"""
    base = Path(root).resolve()
    resolved = (base / normalize_asset_path(relative)).resolve()
    if resolved != base and base not in resolved.parents:
        raise _error(
            PATH_INVALID, f"资产文件路径 {relative!r} 解析后落在受控目录之外"
        )
    return resolved


def declared_asset_paths(standard: DrawingStandard) -> tuple[str, ...]:
    """清单声明的规范化资产相对路径；只校验路径合法性，不检查文件存在。"""
    paths: list[str] = []
    for asset in standard.assets:
        path = normalize_asset_path(asset.file)
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def resolve_asset_files(
    standard: DrawingStandard, root: Path
) -> tuple[tuple[str, Path], ...]:
    """校验全部声明资产并返回 ``(包内相对路径, 实际文件路径)`` 对。"""
    resolved: list[tuple[str, Path]] = []
    for asset in standard.assets:
        target = resolve_asset_file(root, asset.file)
        if not target.is_file():
            raise _error(
                FILE_MISSING,
                f"资产 {asset.asset_id!r} 声明的文件 {asset.file!r} 不在受控目录中",
            )
        resolved.append((normalize_asset_path(asset.file), target))
    return tuple(resolved)


def validate_asset_files(standard: DrawingStandard, root: Path) -> None:
    """发布/导出门禁：声明的资产文件必须真实存在于受控根目录内。"""
    resolve_asset_files(standard, root)


def validate_package_asset_files(
    standard: DrawingStandard, entries: Collection[str]
) -> None:
    """导入门禁：包内条目与清单声明必须双向一致。"""
    declared = declared_asset_paths(standard)
    present = {str(entry).replace("\\", "/") for entry in entries}
    for path in declared:
        if path not in present:
            raise _error(FILE_MISSING, f"标准包清单声明的 {path!r} 不在包内条目中")
    for entry in sorted(present - set(declared)):
        raise _error(PACKAGE_INCONSISTENT, f"标准包含未在清单中声明的条目 {entry!r}")
