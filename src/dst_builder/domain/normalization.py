"""规范化 JSON、确定性哈希与 §4 派生值（纯函数，标准库 only，SPEC-DB-001 §4/§5）。

规范化 JSON：UTF-8、键名排序、无多余空白、数组保序、``ensure_ascii=False``。
时间、绝对项目路径与运行机器信息不得进入哈希输入（由调用方保证载荷形状）。
"""

from __future__ import annotations

import hashlib
import json
import uuid

__all__ = [
    "canonical_json",
    "dwg_name",
    "layout_name",
    "plan_id_from_sha256",
    "revision_id_from_sha256",
    "sha256_hex",
    "sheet_number",
    "task_id_from_revision_sha256",
]

_REVISION_NAMESPACE_PREFIX = "dst-builder:revision:"
_PLAN_NAMESPACE_PREFIX = "dst-builder:plan:"
_TASK_NAMESPACE_PREFIX = "dst-builder:task:"

MAX_NUMBERING_START = 999999
MAX_NUMBERING_WIDTH = 6


def canonical_json(payload: object) -> str:
    """键名排序、紧凑分隔符、保留非 ASCII 字面量的规范化 JSON。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def revision_id_from_sha256(sha256: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{_REVISION_NAMESPACE_PREFIX}{sha256}"))


def plan_id_from_sha256(sha256: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{_PLAN_NAMESPACE_PREFIX}{sha256}"))


def task_id_from_revision_sha256(revision_sha256: str, task_kind: str) -> str:
    """任务/对象 ID 由计划哈希（同修订确定性）与对象语义路径 UUIDv5 派生。"""
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL, f"{_TASK_NAMESPACE_PREFIX}{revision_sha256}:{task_kind}"
        )
    )


def sheet_number(prefix: str, start: int, width: int) -> str:
    """``prefix + zero_pad(start, width)``；起始序号位数超过 ``width`` 即图号溢出。"""
    digits = str(start)
    if len(digits) > width:
        raise ValueError(f"起始序号 {start} 的位数超过位数 {width}")
    return f"{prefix}{digits.zfill(width)}"


def layout_name(number: str, title: str) -> str:
    """``sheet_number + ' ' + title``。"""
    return f"{number} {title}"


def dwg_name(name: str) -> str:
    """``layout_name + '.dwg'``。"""
    return f"{name}.dwg"
