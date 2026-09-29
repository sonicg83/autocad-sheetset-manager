"""旧版本发布包的一对一 UUID 兼容迁移。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dst_manager.domain.legacy_standard_compat import (
    parse_legacy_published_standard_document,
)
from dst_manager.domain.standard_identity import new_standard_id, parse_standard_id
from dst_manager.domain.standard_semantics import validate_published_semantics
from dst_manager.domain.standards import (
    StandardSchemaError,
    parse_standard_draft_document,
)
from dst_manager.infrastructure.filesystem.atomic import atomic_write_text
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    validate_asset_files,
)
from dst_manager.infrastructure.standards.identity_index import (
    IdentityEntry,
    IdentityIndex,
)
from dst_manager.infrastructure.standards.migration_backup import (
    file_manifest,
)

MAPPING_NAME = "legacy-published-uuid-map.json"


class LegacyPublishedMigrationError(Exception):
    """旧发布包无法安全映射；消息以稳定迁移错误码开头。"""


@dataclass(frozen=True, slots=True)
class _LegacyPackage:
    source_dir: Path
    source_document: dict[str, object]


@dataclass(frozen=True, slots=True)
class PreparedLegacyPackage:
    source_dir: Path
    standard_id: str
    source_sha256: str
    document: dict[str, object]


def has_pending_legacy_published(
    published_root: Path, mapping_path: Path
) -> bool:
    """只读判断是否有尚未生成兼容副本的旧发布版本。"""
    packages = _discover_legacy_packages(published_root)
    if not packages:
        return False
    try:
        mapping = _read_mapping(mapping_path)
    except LegacyPublishedMigrationError:
        return True
    entries = mapping["entries"]
    for package in packages:
        key = _source_key(package.source_dir.relative_to(published_root))
        entry = entries.get(key)
        if not isinstance(entry, dict):
            return True
        try:
            standard_id = parse_standard_id(entry.get("standard_id"))
            source_sha256 = _directory_sha256(package.source_dir)
        except (TypeError, ValueError, OSError):
            return True
        target_document = Path(published_root) / standard_id / "document.json"
        if entry.get("source_sha256") != source_sha256 or not target_document.is_file():
            return True
        try:
            target_value = json.loads(target_document.read_text(encoding="utf-8"))
            expected_value, _ = _versionless_document(
                package.source_dir, package.source_document, standard_id
            )
            source_manifest = file_manifest(package.source_dir)
            target_manifest = file_manifest(target_document.parent)
        except (OSError, ValueError, LegacyPublishedMigrationError):
            return True
        source_manifest.pop("document.json", None)
        target_manifest.pop("document.json", None)
        if target_value != expected_value or source_manifest != target_manifest:
            return True
    return False


def prepare_legacy_published(
    *,
    standards_root: Path,
    published_root: Path,
    backup_manifest: dict[str, str],
    backup_parent: Path,
    identity_entries: Iterable[IdentityEntry],
) -> tuple[list[PreparedLegacyPackage], dict[str, object], int, list[IdentityEntry]]:
    """校验历史发布包、分配稳定 UUID，并校验备份与名称唯一性。"""
    packages = _discover_legacy_packages(published_root)
    mapping_path = Path(backup_parent) / MAPPING_NAME
    mapping = _read_mapping(mapping_path)
    entries = dict(mapping["entries"])
    index = IdentityIndex(identity_entries)
    prepared: list[PreparedLegacyPackage] = []
    migrated_identities: list[IdentityEntry] = []
    conflict_count = 0

    for package in packages:
        try:
            relative_source = package.source_dir.relative_to(standards_root).as_posix()
            source_files = file_manifest(package.source_dir)
        except (OSError, ValueError) as exc:
            raise LegacyPublishedMigrationError(
                "STANDARD_MIGRATION_FAILED: 旧发布包目录无法核验"
            ) from exc
        if not source_files:
            raise LegacyPublishedMigrationError(
                "STANDARD_MIGRATION_FAILED: 旧发布包目录为空"
            )
        for relative_path, digest in source_files.items():
            backup_path = f"{relative_source}/{relative_path}"
            if backup_manifest.get(backup_path) != digest:
                raise LegacyPublishedMigrationError(
                    "STANDARD_BACKUP_INVALID: 旧发布包与迁移备份不一致"
                )

        source_sha256 = _directory_sha256(package.source_dir)
        key = _source_key(package.source_dir.relative_to(published_root))
        entry = entries.get(key)
        if entry is None:
            standard_id = new_standard_id()
            entries[key] = {
                "standard_id": standard_id,
                "source_sha256": source_sha256,
            }
        elif (
            not isinstance(entry, dict)
            or entry.get("source_sha256") != source_sha256
        ):
            raise LegacyPublishedMigrationError(
                "STANDARD_MIGRATION_CONFLICT: 已映射的旧发布包内容发生变化"
            )
        else:
            try:
                standard_id = parse_standard_id(entry.get("standard_id"))
            except (TypeError, ValueError) as exc:
                raise LegacyPublishedMigrationError(
                    "STANDARD_BACKUP_INVALID: 旧发布包 UUID 映射无效"
                ) from exc

        migrated, description_conflict = _versionless_document(
            package.source_dir, package.source_document, standard_id
        )
        conflict_count += int(description_conflict)
        try:
            standard = parse_standard_draft_document(migrated)
            validate_published_semantics(standard)
            validate_asset_files(standard, package.source_dir)
        except (StandardSchemaError, StandardAssetError) as exc:
            raise LegacyPublishedMigrationError(
                f"STANDARD_MIGRATION_FAILED: 旧发布包无法通过当前发布校验：{exc}"
            ) from exc

        id_owner = index.find_id(standard_id)
        if id_owner is not None and (
            id_owner.name != standard.name
            or id_owner.source != "user"
            or id_owner.status != "published"
        ):
            raise LegacyPublishedMigrationError(
                "STANDARD_MIGRATION_CONFLICT: UUID 映射与现有标准冲突"
            )
        name_owner = index.find_name(standard.name)
        if name_owner is not None and name_owner.standard_id != standard_id:
            raise LegacyPublishedMigrationError(
                "STANDARD_MIGRATION_CONFLICT: 旧发布标准名称与现有标准冲突"
            )
        identity = IdentityEntry(
            standard_id=standard_id,
            name=standard.name,
            source="user",
            status="published",
        )
        if id_owner is None:
            index.add(identity)
        migrated_identities.append(identity)
        prepared.append(
            PreparedLegacyPackage(
                source_dir=package.source_dir,
                standard_id=standard_id,
                source_sha256=source_sha256,
                document=migrated,
            )
        )

    return prepared, {"format": 1, "entries": entries}, conflict_count, migrated_identities


def save_legacy_mapping(path: Path, mapping: dict[str, object]) -> None:
    atomic_write_text(path, json.dumps(mapping, ensure_ascii=False, indent=2))


def install_legacy_published_copies(
    prepared: Iterable[PreparedLegacyPackage], published_root: Path
) -> None:
    """以同盘暂存与原子改名生成副本，绝不写入旧发布包目录。"""
    published_root = Path(published_root)
    published_root.mkdir(parents=True, exist_ok=True)
    for package in prepared:
        target = published_root / package.standard_id
        if target.exists():
            _verify_existing_copy(package, target)
            continue
        staging = published_root / f".legacy-migration-{uuid.uuid4().hex}"
        try:
            shutil.copytree(package.source_dir, staging)
            atomic_write_text(
                staging / "document.json",
                json.dumps(package.document, ensure_ascii=False, indent=2),
            )
            os.replace(staging, target)
        except OSError as exc:
            raise LegacyPublishedMigrationError(
                "STANDARD_MIGRATION_FAILED: 旧发布包兼容副本写入失败"
            ) from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def migrated_standard_ids(mapping_path: Path) -> frozenset[str]:
    """读取已分配的兼容 UUID；映射文件损坏时拒绝继续服务。"""
    mapping = _read_mapping(mapping_path)
    identifiers = set()
    for entry in mapping["entries"].values():
        if not isinstance(entry, dict):
            raise LegacyPublishedMigrationError(
                "STANDARD_BACKUP_INVALID: 旧发布包 UUID 映射无效"
            )
        try:
            identifiers.add(parse_standard_id(entry.get("standard_id")))
        except (TypeError, ValueError) as exc:
            raise LegacyPublishedMigrationError(
                "STANDARD_BACKUP_INVALID: 旧发布包 UUID 映射无效"
            ) from exc
    return frozenset(identifiers)


def _discover_legacy_packages(root: Path) -> list[_LegacyPackage]:
    packages: list[_LegacyPackage] = []
    root = Path(root)
    if not root.is_dir():
        return packages
    for identity_dir in sorted(root.iterdir()):
        if identity_dir.is_symlink():
            continue
        if not identity_dir.is_dir() or (identity_dir / "document.json").is_file():
            continue
        for version_dir in sorted(identity_dir.iterdir()):
            if version_dir.is_symlink() or not version_dir.is_dir():
                continue
            document_path = version_dir / "document.json"
            if not document_path.is_file():
                continue
            try:
                document = json.loads(document_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise LegacyPublishedMigrationError(
                    "STANDARD_MIGRATION_FAILED: 旧发布包文档无法读取"
                ) from exc
            if not isinstance(document, dict):
                raise LegacyPublishedMigrationError(
                    "STANDARD_MIGRATION_FAILED: 旧发布包文档根必须是对象"
                )
            packages.append(_LegacyPackage(version_dir, document))
    return packages


def _versionless_document(
    source_dir: Path, document: dict[str, object], standard_id: str
) -> tuple[dict[str, object], bool]:
    try:
        legacy_id = source_dir.parent.name
        legacy_version = int(source_dir.name)
        parse_legacy_published_standard_document(
            document, standard_id=legacy_id, version=legacy_version
        )
    except (TypeError, ValueError, StandardSchemaError) as exc:
        raise LegacyPublishedMigrationError(
            "STANDARD_MIGRATION_FAILED: 旧发布包身份或结构无效"
        ) from exc

    description = document.get("description")
    release_notes = document.get("release_notes")
    if description is not None and not isinstance(description, str):
        raise LegacyPublishedMigrationError(
            "STANDARD_MIGRATION_FAILED: 旧标准描述不是文本"
        )
    if release_notes is not None and not isinstance(release_notes, str):
        raise LegacyPublishedMigrationError(
            "STANDARD_MIGRATION_FAILED: 旧版本说明不是文本"
        )
    conflict = (
        isinstance(description, str)
        and isinstance(release_notes, str)
        and description != release_notes
    )
    migrated = dict(document)
    migrated["schema_version"] = 3
    migrated["standard_id"] = standard_id
    migrated["published_at"] = None
    migrated["description"] = (
        description if isinstance(description, str) else release_notes or ""
    )
    migrated.pop("version", None)
    migrated.pop("release_notes", None)
    return migrated, conflict


def _read_mapping(path: Path) -> dict[str, object]:
    if not Path(path).exists():
        return {"format": 1, "entries": {}}
    try:
        mapping = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LegacyPublishedMigrationError(
            "STANDARD_BACKUP_INVALID: 旧发布包 UUID 映射无法读取"
        ) from exc
    entries = mapping.get("entries") if isinstance(mapping, dict) else None
    if (
        not isinstance(mapping, dict)
        or mapping.get("format") != 1
        or not isinstance(entries, dict)
    ):
        raise LegacyPublishedMigrationError(
            "STANDARD_BACKUP_INVALID: 旧发布包 UUID 映射格式无效"
        )
    mapped_ids: set[str] = set()
    for entry in entries.values():
        if not isinstance(entry, dict):
            raise LegacyPublishedMigrationError(
                "STANDARD_BACKUP_INVALID: 旧发布包 UUID 映射格式无效"
            )
        try:
            standard_id = parse_standard_id(entry.get("standard_id"))
        except (TypeError, ValueError) as exc:
            raise LegacyPublishedMigrationError(
                "STANDARD_BACKUP_INVALID: 旧发布包 UUID 映射无效"
            ) from exc
        if standard_id in mapped_ids:
            raise LegacyPublishedMigrationError(
                "STANDARD_BACKUP_INVALID: 多个旧发布包映射到同一 UUID"
            )
        mapped_ids.add(standard_id)
    return mapping


def _source_key(relative_source: Path) -> str:
    return hashlib.sha256(relative_source.as_posix().encode("utf-8")).hexdigest()


def _directory_sha256(source_dir: Path) -> str:
    manifest = file_manifest(source_dir)
    content = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _verify_existing_copy(
    package: PreparedLegacyPackage, target: Path
) -> None:
    if target.is_symlink() or not target.is_dir():
        raise LegacyPublishedMigrationError(
            "STANDARD_MIGRATION_CONFLICT: UUID 兼容副本路径已被占用"
        )
    try:
        current = json.loads((target / "document.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LegacyPublishedMigrationError(
            "STANDARD_MIGRATION_CONFLICT: UUID 兼容副本无法读取"
        ) from exc
    if current != package.document:
        raise LegacyPublishedMigrationError(
            "STANDARD_MIGRATION_CONFLICT: UUID 兼容副本与旧发布包映射不一致"
        )
    source_manifest = file_manifest(package.source_dir)
    target_manifest = file_manifest(target)
    source_manifest.pop("document.json", None)
    target_manifest.pop("document.json", None)
    if source_manifest != target_manifest:
        raise LegacyPublishedMigrationError(
            "STANDARD_MIGRATION_CONFLICT: UUID 兼容副本资源与旧发布包不一致"
        )
