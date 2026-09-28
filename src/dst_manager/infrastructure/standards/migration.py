"""用户标准库旧草稿备份与 schema v3 迁移。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Iterable
from pathlib import Path

from dst_manager.domain.standard_identity import new_standard_id
from dst_manager.domain.standards import (
    StandardSchemaError,
    parse_standard_draft_document,
)
from dst_manager.infrastructure.filesystem.atomic import atomic_write_text
from dst_manager.infrastructure.standards.identity_index import (
    IdentityEntry,
    IdentityIndex,
)

BACKUP_NAME = "PLAN-DM-046-pre-migration-2026-09-28"
LIBRARY_LOCK_NAME = ".standards.lock"
_MANIFEST_NAME = "sha256-manifest.json"
_REPORT_NAME = "migration-report.json"
_MIGRATABLE_SCHEMA_VERSIONS = frozenset({1, 2})
_HASH_CHUNK_SIZE = 1024 * 1024


class StandardMigrationError(Exception):
    """标准库迁移失败；消息包含稳定错误码。"""


def has_legacy_drafts(drafts_root: Path) -> bool:
    """只读探测是否有可迁移的 schema v1/v2 草稿。"""
    return bool(_legacy_drafts(Path(drafts_root)))


def migrate_legacy_drafts(
    *,
    standards_root: Path,
    official_root: Path,
    published_root: Path,
    drafts_root: Path,
    identity_entries: Iterable[IdentityEntry],
) -> tuple[int, int]:
    """先校验整库备份，再验证并逐文件原子迁移旧用户草稿。

    返回本次迁移的草稿数和描述冲突数。调用方负责在标准库互斥锁内执行。
    """
    standards_root = Path(standards_root).resolve()
    legacy = _legacy_drafts(Path(drafts_root))
    if not legacy:
        return 0, 0
    _reject_legacy_published(official_root, published_root)

    data_root = standards_root.parent if standards_root.name == "standards" else standards_root
    backup_parent = data_root / "backups" / BACKUP_NAME
    backup_tree = backup_parent / "standards"
    backup_manifest = _ensure_verified_backup(
        standards_root, backup_parent, backup_tree
    )
    for _draft_id, document_path, _document in legacy:
        relative_path = document_path.relative_to(standards_root).as_posix()
        if backup_manifest.get(relative_path) != _sha256_file(document_path):
            raise StandardMigrationError(
                "STANDARD_BACKUP_INVALID: 待迁移草稿与经校验备份不一致"
            )

    index = IdentityIndex(identity_entries)
    prepared: list[tuple[Path, dict[str, object]]] = []
    conflict_count = 0
    for draft_id, document_path, document in legacy:
        raw_description = document.get("description")
        raw_release_notes = document.get("release_notes")
        description = raw_description if isinstance(raw_description, str) else None
        release_notes = raw_release_notes if isinstance(raw_release_notes, str) else None
        if description is not None and release_notes is not None and description != release_notes:
            conflict_count += 1
        if description is None:
            description = release_notes or ""

        migrated = dict(document)
        migrated["schema_version"] = 3
        migrated["standard_id"] = new_standard_id()
        migrated["published_at"] = None
        migrated["description"] = description
        migrated.pop("version", None)
        migrated.pop("release_notes", None)
        try:
            standard = parse_standard_draft_document(migrated)
        except StandardSchemaError as exc:
            raise StandardMigrationError(
                f"STANDARD_MIGRATION_FAILED: 草稿文档结构无法升级：{exc}"
            ) from exc
        if index.find_id(standard.standard_id) is not None:
            raise StandardMigrationError(
                "STANDARD_MIGRATION_FAILED: UUID 冲突，请重新运行迁移"
            )
        owner = index.find_name(standard.name, exclude_draft_id=draft_id)
        if owner is not None:
            raise StandardMigrationError(
                "STANDARD_MIGRATION_CONFLICT: 旧草稿与现有非空标准名称重复"
            )
        index.add(
            IdentityEntry(
                standard_id=standard.standard_id,
                name=standard.name,
                source="user",
                status="draft",
                draft_id=draft_id,
            )
        )
        prepared.append((document_path, migrated))

    report_path = backup_parent / _REPORT_NAME
    previous_report = _read_aggregate_report(report_path)
    report = {
        "format": 1,
        "migrated_count": max(
            len(prepared), _nonnegative_count(previous_report.get("migrated_count"))
        ),
        "description_conflict_count": max(
            conflict_count,
            _nonnegative_count(previous_report.get("description_conflict_count")),
        ),
        "result": "prepared",
    }
    _write_report(report_path, report)
    for document_path, document in prepared:
        try:
            atomic_write_text(
                document_path,
                json.dumps(document, ensure_ascii=False, indent=2),
            )
        except OSError as exc:
            raise StandardMigrationError(
                f"STANDARD_MIGRATION_FAILED: 草稿原子写入失败：{exc}"
            ) from exc
    report["result"] = "completed"
    _write_report(report_path, report)
    return len(prepared), conflict_count


def _legacy_drafts(drafts_root: Path) -> list[tuple[str, Path, dict[str, object]]]:
    drafts: list[tuple[str, Path, dict[str, object]]] = []
    if not drafts_root.is_dir():
        return drafts
    try:
        directories = sorted(drafts_root.iterdir())
    except OSError as exc:
        raise StandardMigrationError(
            f"STANDARD_MIGRATION_FAILED: 无法扫描草稿库：{exc}"
        ) from exc
    for directory in directories:
        if directory.is_symlink():
            raise StandardMigrationError(
                "STANDARD_MIGRATION_FAILED: 草稿目录含符号链接"
            )
        if not directory.is_dir():
            continue
        document_path = directory / "document.json"
        if not document_path.is_file():
            continue
        try:
            document = json.loads(document_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StandardMigrationError(
                f"STANDARD_MIGRATION_FAILED: 草稿文档无法读取：{exc}"
            ) from exc
        if not isinstance(document, dict):
            raise StandardMigrationError(
                "STANDARD_MIGRATION_FAILED: 草稿文档根必须是对象"
            )
        schema_version = document.get("schema_version")
        if type(schema_version) is int and schema_version in _MIGRATABLE_SCHEMA_VERSIONS:
            drafts.append((directory.name, document_path, document))
    return drafts


def _reject_legacy_published(*roots: Path) -> None:
    """发现旧版 ID/版本嵌套包时停止，不触碰任何旧发布物。"""
    for root in roots:
        if not root.is_dir():
            continue
        for identity_dir in root.iterdir():
            if identity_dir.is_symlink() or not identity_dir.is_dir():
                continue
            if any(
                child.is_dir() and (child / "document.json").is_file()
                for child in identity_dir.iterdir()
            ):
                raise StandardMigrationError(
                    "STANDARD_MIGRATION_REQUIRED: 检测到旧版已发布标准，草稿迁移已停止"
                )


def _ensure_verified_backup(
    source_root: Path, backup_parent: Path, backup_tree: Path
) -> dict[str, str]:
    manifest_path = backup_parent / _MANIFEST_NAME
    try:
        source_manifest = _file_manifest(source_root)
        data_root = backup_parent.parent.parent
        backups_root = backup_parent.parent
        if data_root.is_symlink() or backups_root.is_symlink() or backup_parent.is_symlink():
            raise ValueError("备份路径不能包含符号链接")
        if manifest_path.is_symlink() or backup_tree.is_symlink():
            raise ValueError("备份文件不能是符号链接")
        if backup_tree.exists():
            if not backup_parent.is_dir() or not backup_tree.is_dir():
                raise ValueError("备份 standards 不是普通目录")
            backup_manifest = _file_manifest(backup_tree)
            if manifest_path.is_file():
                expected = json.loads(manifest_path.read_text(encoding="utf-8"))
                expected_files = expected.get("files") if isinstance(expected, dict) else None
                if (
                    not isinstance(expected, dict)
                    or expected.get("format") != 1
                    or expected.get("file_count") != len(expected_files or {})
                    or expected_files != backup_manifest
                ):
                    raise ValueError("已有备份与校验清单不一致")
            elif source_manifest != backup_manifest:
                raise ValueError("已有备份与当前标准库不一致")
            _write_manifest(manifest_path, backup_manifest)
            return backup_manifest
        if backup_parent.exists() or manifest_path.exists():
            raise ValueError("已有备份不完整，拒绝覆盖")

        backup_parent.mkdir(parents=True, exist_ok=True)
        staging = backup_parent / f".standards-copy-{uuid.uuid4().hex}"

        def ignore_lock(_directory: str, names: list[str]) -> set[str]:
            return {name for name in names if name == LIBRARY_LOCK_NAME}

        try:
            shutil.copytree(source_root, staging, ignore=ignore_lock)
            staged_manifest = _file_manifest(staging)
            if staged_manifest != source_manifest:
                raise ValueError("标准库备份的文件数或 SHA-256 与源目录不一致")
            os.replace(staging, backup_tree)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        _write_manifest(manifest_path, staged_manifest)
        return staged_manifest
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise StandardMigrationError(
            f"STANDARD_BACKUP_INVALID: 迁移前标准库备份校验失败：{exc}"
        ) from exc


def _file_manifest(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for directory, names, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in names:
            if (base / name).is_symlink():
                raise ValueError("标准库树含符号链接目录")
        for name in filenames:
            path = base / name
            if path.name == LIBRARY_LOCK_NAME:
                continue
            if path.is_symlink():
                raise ValueError("标准库树含符号链接文件")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
                    digest.update(chunk)
            files[path.relative_to(root).as_posix()] = digest.hexdigest()
    return dict(sorted(files.items()))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_aggregate_report(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(report, dict) or report.get("format") != 1:
        return {}
    return report


def _nonnegative_count(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _write_manifest(path: Path, files: dict[str, str]) -> None:
    payload = {"format": 1, "file_count": len(files), "files": files}
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _write_report(path: Path, report: dict[str, object]) -> None:
    try:
        atomic_write_text(path, json.dumps(report, ensure_ascii=False, indent=2))
    except OSError as exc:
        raise StandardMigrationError(
            f"STANDARD_MIGRATION_FAILED: 本地迁移报告无法写入：{exc}"
        ) from exc
