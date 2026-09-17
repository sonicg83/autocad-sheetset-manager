"""构建 attempt 目录契约与现场证据（SPEC-DB-001 §3，PLAN-DB-001 Task 9）。

``builds/<build-id>/attempt-NNN/`` 是可审计运行证据：固定五个子目录
``input/work/logs/metadata/candidate``；启动恢复依据其中的
``metadata/publish-target.json`` 发布证据裁决 PUBLISHING 遗留现场。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from dst_builder.infrastructure.persistence.database import utc_now_iso

__all__ = [
    "PUBLISH_EVIDENCE_FILE",
    "AttemptDirectory",
    "PublishEvidence",
    "PublishEvidenceError",
    "attempt_dir_for",
    "create_attempt_dirs",
    "read_publish_evidence",
    "write_cad_evidence",
    "write_publish_evidence",
]

ATTEMPT_SUBDIRS = ("input", "work", "logs", "metadata", "candidate")
PUBLISH_EVIDENCE_FILE = "publish-target.json"
CAD_EVIDENCE_FILE = "cad-result.json"


class PublishEvidenceError(ValueError):
    """发布证据缺失或不可解析（PUBLISHING 遗留现场裁决为歧义）。"""


@dataclass(frozen=True, slots=True)
class AttemptDirectory:
    """一次 attempt 的工作目录：根与五个固定子目录。"""

    root: Path
    input_dir: Path
    work: Path
    logs: Path
    metadata: Path
    candidate: Path


@dataclass(frozen=True, slots=True)
class PublishEvidence:
    """发布证据：PUBLISHING 阶段的目标与暂存绝对路径（仅存 attempt 内）。"""

    target: Path
    staging: Path
    recorded_at: str


def attempt_dir_for(project_root: Path, build_id: str, attempt: int) -> Path:
    return Path(project_root) / "builds" / build_id / f"attempt-{attempt:03d}"


def create_attempt_dirs(project_root: Path, build_id: str, attempt: int) -> AttemptDirectory:
    """创建 attempt 的五个固定子目录（已存在时幂等）。"""
    root = attempt_dir_for(project_root, build_id, attempt)
    paths = {name: root / name for name in ATTEMPT_SUBDIRS}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return AttemptDirectory(
        root=root,
        input_dir=paths["input"],
        work=paths["work"],
        logs=paths["logs"],
        metadata=paths["metadata"],
        candidate=paths["candidate"],
    )


def write_publish_evidence(
    attempt_metadata_dir: Path, *, target: Path, staging: Path
) -> None:
    """在 PUBLISHING 进入点写发布证据（改名前落盘，供启动恢复裁决）。"""
    payload = {
        "target": str(target),
        "staging": str(staging),
        "recorded_at": utc_now_iso(),
    }
    attempt_metadata_dir.mkdir(parents=True, exist_ok=True)
    (attempt_metadata_dir / PUBLISH_EVIDENCE_FILE).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def read_publish_evidence(attempt_dir: Path) -> PublishEvidence:
    """读取发布证据；缺失或不可解析即 :class:`PublishEvidenceError`（歧义现场）。"""
    path = Path(attempt_dir) / "metadata" / PUBLISH_EVIDENCE_FILE
    if not path.is_file():
        raise PublishEvidenceError(f"发布证据缺失：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        target = Path(payload["target"])
        staging = Path(payload["staging"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise PublishEvidenceError(f"发布证据不可解析：{error}") from error
    if not payload.get("recorded_at"):
        raise PublishEvidenceError("发布证据缺少 recorded_at")
    return PublishEvidence(
        target=target, staging=staging, recorded_at=payload["recorded_at"]
    )


def write_cad_evidence(attempt_metadata_dir: Path, payload: dict) -> None:
    """写入 CAD 结果证据（布局 Handle、实际 CAD 版本、DWG 大小与哈希）。"""
    attempt_metadata_dir.mkdir(parents=True, exist_ok=True)
    (attempt_metadata_dir / CAD_EVIDENCE_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def unique_staging_name(target: Path) -> str:
    """目标父目录内的唯一暂存目录名（隐藏式前缀 + 随机后缀）。"""
    return f".dstb-staging-{uuid.uuid4().hex[:12]}"
