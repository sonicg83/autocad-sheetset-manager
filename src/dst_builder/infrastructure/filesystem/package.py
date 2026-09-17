"""正式成果包装配与完整性校验（SPEC-DB-001 §9，PLAN-DB-001 Task 9）。

manifest 使用 ``dst-builder.manifest/v1``，列出除自身和 ``handoff.json`` 外
的全部正式文件，每项含 ``path``/``role``/``size``/``sha256``，按路径字典序
排列；``handoff.json`` 使用 ``dst-builder.handoff/v1``，
``package_id = uuid5(NAMESPACE_URL, "dst-builder:package:" + manifest_sha256)``，
且不进入 manifest（避免自引用）。全部 JSON 为规范化字节（键名排序、紧凑、
``ensure_ascii=False``），固定输入（含 ``created_at``）字节级确定。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dst_builder.domain.models import (
    HANDOFF_SCHEMA,
    MANIFEST_SCHEMA,
    GenerationPlanV1,
)
from dst_builder.domain.normalization import (
    canonical_json,
    package_id_from_manifest_sha256,
)
from dst_builder.domain.planning import SHEETSET_PATH

__all__ = [
    "HANDOFF_FILE",
    "MANIFEST_FILE",
    "ManifestEntry",
    "assemble_package_files",
    "build_handoff_bytes",
    "build_manifest_bytes",
    "manifest_sha256_of",
    "package_id_for",
    "verify_package",
]

MANIFEST_FILE = "metadata/manifest.json"
HANDOFF_FILE = "metadata/handoff.json"
_DST_PATH = SHEETSET_PATH

_COPY_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    role: str
    size: int
    sha256: str


def manifest_sha256_of(files: Mapping[str, bytes]) -> str:
    return hashlib.sha256(files[MANIFEST_FILE]).hexdigest()


def package_id_for(manifest_sha256: str) -> str:
    return package_id_from_manifest_sha256(manifest_sha256)


def build_manifest_bytes(
    files: Mapping[str, bytes], roles: Mapping[str, str]
) -> bytes:
    """manifest 规范化字节：除自身与 handoff 外的全部正式文件，按路径字典序。"""
    entries = [
        {
            "path": path,
            "role": roles[path],
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, content in sorted(files.items())
        if path not in (MANIFEST_FILE, HANDOFF_FILE)
    ]
    return canonical_json({"schema": MANIFEST_SCHEMA, "files": entries}).encode("utf-8")


def build_handoff_bytes(
    *,
    manifest_sha256: str,
    build_id: str,
    plan_id: str,
    builder_version: str,
    created_at: str,
) -> bytes:
    """§9 handoff 规范化字节（不进入 manifest）。"""
    payload = {
        "schema": HANDOFF_SCHEMA,
        "package_id": package_id_for(manifest_sha256),
        "build_id": build_id,
        "plan_id": plan_id,
        "manifest_path": "metadata/manifest.json",
        "manifest_sha256": manifest_sha256,
        "dst_path": _DST_PATH,
        "created_at": created_at,
        "builder_version": builder_version,
    }
    return canonical_json(payload).encode("utf-8")


def assemble_package_files(
    *,
    plan: GenerationPlanV1,
    revision_json: str,
    plan_json: str,
    report_json: str,
    dst_bytes: bytes,
    dwg_bytes: bytes,
    catalog_bytes: bytes,
    build_id: str,
    builder_version: str,
    created_at: str,
) -> dict[str, bytes]:
    """装配全部正式文件（含 manifest 与 handoff），路径均为成果包内相对路径。"""
    roles = {artifact.path: artifact.role for artifact in plan.expected_artifacts}
    drawing_path = plan.drawing_task.target_dwg_path
    files: dict[str, bytes] = {
        _DST_PATH: dst_bytes,
        drawing_path: dwg_bytes,
        "drawings/图纸目录.xlsx": catalog_bytes,
        "metadata/project-revision.json": revision_json.encode("utf-8"),
        "metadata/generation-plan.json": plan_json.encode("utf-8"),
        "metadata/validation-report.json": report_json.encode("utf-8"),
    }
    files[MANIFEST_FILE] = build_manifest_bytes(files, roles)
    files[HANDOFF_FILE] = build_handoff_bytes(
        manifest_sha256=manifest_sha256_of(files),
        build_id=build_id,
        plan_id=plan.plan_id,
        builder_version=builder_version,
        created_at=created_at,
    )
    return files


def verify_package(root: Path) -> tuple[str, ...]:
    """校验成果包完整性：根目录约定、manifest 登记文件的大小与 SHA-256。

    返回问题列表（空元组 = 完整）；只读，不修改任何文件。
    """
    root = Path(root)
    problems: list[str] = []
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.is_file():
        return (f"manifest 缺失：{MANIFEST_FILE}",)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return (f"manifest 读取失败：{error}",)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        problems.append(f"manifest Schema 不符：{manifest.get('schema')!r}")
        return tuple(problems)

    top_level = sorted(item.name for item in root.iterdir())
    if top_level != ["drawings", "metadata"]:
        problems.append(f"成果根目录约定被破坏：{top_level}")

    for entry in manifest.get("files", []):
        path = entry["path"]
        if path in (MANIFEST_FILE, HANDOFF_FILE):
            problems.append(f"manifest 不得登记 {path}")
            continue
        if not path.startswith(("drawings/", "metadata/")):
            problems.append(f"登记路径越出成果包约定：{path}")
            continue
        candidate = root / path
        if not candidate.is_file():
            problems.append(f"登记文件缺失：{path}")
            continue
        size = candidate.stat().st_size
        if size != entry["size"]:
            problems.append(f"文件大小不符：{path}（{size} != {entry['size']}）")
            continue
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_COPY_CHUNK), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != entry["sha256"]:
            problems.append(f"文件 SHA-256 不符：{path}")
    return tuple(problems)
