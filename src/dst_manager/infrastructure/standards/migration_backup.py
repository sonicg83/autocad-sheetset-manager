"""标准库迁移前备份及 SHA-256 清单。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from dst_manager.infrastructure.filesystem.atomic import atomic_write_text

LIBRARY_LOCK_NAME = ".standards.lock"
_MANIFEST_NAME = "sha256-manifest.json"
_HASH_CHUNK_SIZE = 1024 * 1024


def ensure_verified_backup(source_root: Path, backup_parent: Path) -> dict[str, str]:
    """创建或校验标准库整树备份，拒绝覆盖损坏备份。"""
    source_root = Path(source_root)
    backup_parent = Path(backup_parent)
    backup_tree = backup_parent / "standards"
    manifest_path = backup_parent / _MANIFEST_NAME
    try:
        source_manifest = file_manifest(source_root)
        data_root = backup_parent.parent.parent
        backups_root = backup_parent.parent
        if (
            data_root.is_symlink()
            or backups_root.is_symlink()
            or backup_parent.is_symlink()
        ):
            raise ValueError("备份路径不能包含符号链接")
        if manifest_path.is_symlink() or backup_tree.is_symlink():
            raise ValueError("备份文件不能是符号链接")
        if backup_tree.exists():
            if not backup_parent.is_dir() or not backup_tree.is_dir():
                raise ValueError("备份 standards 不是普通目录")
            backup_manifest = file_manifest(backup_tree)
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
            write_manifest(manifest_path, backup_manifest)
            return backup_manifest
        if backup_parent.exists() or manifest_path.exists():
            raise ValueError("已有备份不完整，拒绝覆盖")

        backup_parent.mkdir(parents=True, exist_ok=True)
        staging = backup_parent / f".standards-copy-{uuid.uuid4().hex}"

        def ignore_lock(_directory: str, names: list[str]) -> set[str]:
            return {name for name in names if name == LIBRARY_LOCK_NAME}

        try:
            shutil.copytree(source_root, staging, ignore=ignore_lock)
            staged_manifest = file_manifest(staging)
            if staged_manifest != source_manifest:
                raise ValueError("标准库备份的文件数或 SHA-256 与源目录不一致")
            os.replace(staging, backup_tree)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        write_manifest(manifest_path, staged_manifest)
        return staged_manifest
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"STANDARD_BACKUP_INVALID: 迁移前标准库备份校验失败：{exc}") from exc


def file_manifest(root: Path) -> dict[str, str]:
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path, files: dict[str, str]) -> None:
    payload = {"format": 1, "file_count": len(files), "files": files}
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
