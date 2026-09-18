"""正式成果装配与完整性校验（SPEC-DB-001 §9，RFC-INT-002）。

成果目标目录直接包含 ``sheetset.dst``、构建后的 DWG 与 ``图纸目录.xlsx``；
不再生成 ``drawings/`` 包装层与 ``metadata/``，因此不存在清单、哈希链与
来源元数据。:func:`verify_target` 只断言预期产物集合存在、可读、非空——
目标目录就是用户的图纸集工作目录，允许用户在其中放入其他文件。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from dst_builder.domain.models import GenerationPlanV1
from dst_builder.domain.planning import SHEET_CATALOG_PATH, SHEETSET_PATH

__all__ = [
    "assemble_package_files",
    "verify_target",
]


def assemble_package_files(
    *,
    plan: GenerationPlanV1,
    dst_bytes: bytes,
    dwg_bytes: bytes,
    catalog_bytes: bytes,
) -> dict[str, bytes]:
    """装配全部正式文件，键为成果目标目录内的相对路径。"""
    return {
        SHEETSET_PATH: dst_bytes,
        plan.drawing_task.target_dwg_path: dwg_bytes,
        SHEET_CATALOG_PATH: catalog_bytes,
    }


def verify_target(root: Path, expected_paths: Iterable[str]) -> tuple[str, ...]:
    """校验目标目录至少包含预期产物集合；返回问题列表（空元组 = 通过）。

    ``expected_paths`` 由调用方显式给出：发布时来自候选文件映射，启动恢复
    时来自发布证据的 ``expected_paths``。空集合视为发布证据缺失并判为问题，
    避免「没有预期产物即视为完整」的静默放行。不比对内容哈希，也不约束目录
    内的其他文件。
    """
    root = Path(root)
    paths = tuple(expected_paths)
    if not paths:
        return ("发布证据缺少预期产物清单",)
    problems: list[str] = []
    for relative in paths:
        candidate = root / relative
        if not candidate.is_file():
            problems.append(f"预期产物缺失：{relative}")
            continue
        try:
            size = candidate.stat().st_size
        except OSError as error:
            problems.append(f"预期产物不可读：{relative}（{error}）")
            continue
        if size == 0:
            problems.append(f"预期产物为空：{relative}")
    return tuple(problems)
