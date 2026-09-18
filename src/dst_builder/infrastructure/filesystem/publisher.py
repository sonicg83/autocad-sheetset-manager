"""原子发布器（SPEC-DB-001 §9，PLAN-DB-001 Task 9）。

候选包在 attempt 内完成后复制到目标父目录的唯一暂存目录 → 重新校验 →
同卷 ``os.replace(staging, target)``。首期禁止替换既有目标：目标预存在即
``PACKAGE_TARGET_EXISTS`` 且不修改它；改名失败清理暂存并保证目标不存在。
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from dst_builder.infrastructure.filesystem.package import verify_target

__all__ = [
    "PACKAGE_TARGET_EXISTS",
    "PUBLISH_FAILED",
    "PackagePublishError",
    "PackageTargetExistsError",
    "publish_candidate",
]

PACKAGE_TARGET_EXISTS = "PACKAGE_TARGET_EXISTS"
PUBLISH_FAILED = "PUBLISH_FAILED"


class PackageTargetExistsError(Exception):
    """正式目标已存在；首期不覆盖或合并既有目录。"""

    code = PACKAGE_TARGET_EXISTS


class PackagePublishError(Exception):
    """暂存/改名阶段失败（父目录缺失、不可写、改名异常）；目标不被创建。"""

    code = PUBLISH_FAILED


def _copy_tree(files: Mapping[str, bytes], root: Path) -> None:
    for relative, content in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def publish_candidate(
    files: Mapping[str, bytes], target: Path, *, staging: Path
) -> Path:
    """把候选文件经暂存目录原子发布到 ``target``，返回发布路径。

    前置：``target`` 与 ``staging`` 均不存在，``target.parent`` 已存在。
    任一步失败都不修改既有文件系统状态（暂存被清理）。
    """
    target = Path(target)
    staging = Path(staging)
    if target.exists():
        raise PackageTargetExistsError(f"成果目标已存在：{target}")
    if staging.exists():
        raise PackagePublishError(f"暂存目录已存在：{staging}")
    parent = target.parent
    if not parent.is_dir():
        raise PackagePublishError(f"目标父目录不存在：{parent}")
    if not os.access(parent, os.W_OK):
        raise PackagePublishError(f"目标父目录不可写：{parent}")

    try:
        _copy_tree(files, staging)
        problems = verify_target(staging, tuple(files))
        if problems:
            raise PackagePublishError(
                f"暂存包校验失败：{'；'.join(problems)}"
            )
        os.replace(staging, target)
    except PackageTargetExistsError:
        raise
    except PackagePublishError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise PackagePublishError(f"发布改名失败：{error}") from error

    problems = verify_target(target, tuple(files))
    if problems:
        # 改名成功但事后校验失败：不回滚（目标已是完整可见状态，失败由校验
        # 之外的因素导致），交由启动恢复按 PUBLISH_RECOVERY_REQUIRED 裁决。
        raise PackagePublishError(f"发布后校验失败：{'；'.join(problems)}")
    return target
