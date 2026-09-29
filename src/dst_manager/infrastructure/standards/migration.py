"""用户标准库旧草稿与旧发布包备份、兼容迁移。"""

from __future__ import annotations

import json
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
from dst_manager.infrastructure.standards.legacy_published_migration import (
    LegacyPublishedMigrationError,
    has_pending_legacy_published,
    install_legacy_published_copies,
    prepare_legacy_published,
    save_legacy_mapping,
)
from dst_manager.infrastructure.standards.migration_backup import (
    ensure_verified_backup,
    sha256_file,
)

BACKUP_NAME = "PLAN-DM-046-pre-migration-2026-09-28"
_REPORT_NAME = "migration-report.json"
_MIGRATABLE_SCHEMA_VERSIONS = frozenset({1, 2})


class StandardMigrationError(Exception):
    """标准库迁移失败；消息包含稳定错误码。"""


def has_legacy_drafts(drafts_root: Path) -> bool:
    """只读探测是否有可迁移的 schema v1/v2 草稿。"""
    return bool(_legacy_drafts(Path(drafts_root)))


def has_legacy_published(published_root: Path, backup_parent: Path) -> bool:
    """只读探测是否存在尚未映射的旧版发布包。"""
    return has_pending_legacy_published(
        Path(published_root), Path(backup_parent) / "legacy-published-uuid-map.json"
    )


def migrate_legacy_standards(
    *,
    standards_root: Path,
    official_root: Path,
    published_root: Path,
    drafts_root: Path,
    identity_entries: Iterable[IdentityEntry],
) -> tuple[int, int, int]:
    """先校验整库备份，再迁移旧草稿并为每个旧发布包生成 UUID 副本。

    旧发布目录与工程快照均只读；兼容副本发布时间未知。调用方负责持锁。
    """
    standards_root = Path(standards_root).resolve()
    drafts_root = Path(drafts_root)
    published_root = Path(published_root)
    legacy_drafts = _legacy_drafts(drafts_root)
    backup_parent = standards_root.parent / "backups" / BACKUP_NAME
    has_pending_published = has_legacy_published(published_root, backup_parent)
    if not legacy_drafts and not has_pending_published:
        return 0, 0, 0
    _reject_legacy_published(official_root)
    try:
        backup_manifest = ensure_verified_backup(standards_root, backup_parent)
    except ValueError as exc:
        raise StandardMigrationError(str(exc)) from exc
    for _draft_id, document_path, _document in legacy_drafts:
        relative_path = document_path.relative_to(standards_root).as_posix()
        if backup_manifest.get(relative_path) != sha256_file(document_path):
            raise StandardMigrationError(
                "STANDARD_BACKUP_INVALID: 待迁移草稿与经校验备份不一致"
            )

    try:
        prepared_published, mapping, package_conflicts, published_identities = (
            prepare_legacy_published(
                standards_root=standards_root,
                published_root=published_root,
                backup_manifest=backup_manifest,
                backup_parent=backup_parent,
                identity_entries=identity_entries,
            )
        )
    except LegacyPublishedMigrationError as exc:
        raise StandardMigrationError(str(exc)) from exc

    index = IdentityIndex(identity_entries)
    for identity in published_identities:
        if index.find_id(identity.standard_id) is None:
            index.add(identity)
    prepared_drafts: list[tuple[Path, dict[str, object]]] = []
    conflict_count = 0
    for draft_id, document_path, document in legacy_drafts:
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
        prepared_drafts.append((document_path, migrated))

    report_path = backup_parent / _REPORT_NAME
    previous_report = _read_aggregate_report(report_path)
    previous_draft_count = _nonnegative_count(
        previous_report.get("draft_migrated_count", previous_report.get("migrated_count"))
    )
    previous_published_count = _nonnegative_count(
        previous_report.get("published_migrated_count")
    )
    draft_count = max(len(prepared_drafts), previous_draft_count)
    published_count = max(len(prepared_published), previous_published_count)
    report = {
        "format": 1,
        "migrated_count": draft_count + published_count,
        "draft_migrated_count": draft_count,
        "published_migrated_count": published_count,
        "description_conflict_count": max(
            conflict_count + package_conflicts,
            _nonnegative_count(previous_report.get("description_conflict_count")),
        ),
        "result": "prepared",
    }
    try:
        save_legacy_mapping(backup_parent / "legacy-published-uuid-map.json", mapping)
    except OSError as exc:
        raise StandardMigrationError(
            "STANDARD_MIGRATION_FAILED: 旧发布包 UUID 映射无法保存"
        ) from exc
    _write_report(report_path, report)
    try:
        install_legacy_published_copies(prepared_published, published_root)
    except LegacyPublishedMigrationError as exc:
        raise StandardMigrationError(str(exc)) from exc
    for document_path, document in prepared_drafts:
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
    return len(prepared_published), len(prepared_drafts), package_conflicts + conflict_count


def migrate_legacy_drafts(
    *,
    standards_root: Path,
    official_root: Path,
    published_root: Path,
    drafts_root: Path,
    identity_entries: Iterable[IdentityEntry],
) -> tuple[int, int]:
    """兼容旧调用门面；同时执行当前标准库迁移并返回草稿数与冲突数。"""
    _published_count, draft_count, conflict_count = migrate_legacy_standards(
        standards_root=standards_root,
        official_root=official_root,
        published_root=published_root,
        drafts_root=drafts_root,
        identity_entries=identity_entries,
    )
    return draft_count, conflict_count


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


def _write_report(path: Path, report: dict[str, object]) -> None:
    try:
        atomic_write_text(path, json.dumps(report, ensure_ascii=False, indent=2))
    except OSError as exc:
        raise StandardMigrationError(
            f"STANDARD_MIGRATION_FAILED: 本地迁移报告无法写入：{exc}"
        ) from exc
