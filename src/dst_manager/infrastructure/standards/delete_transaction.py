"""标准包与关联创建草稿的可恢复删除事务。"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from dst_manager.domain.standard_identity import parse_standard_id
from dst_manager.infrastructure.filesystem.atomic import atomic_write_text

_DRAFT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
_MANIFEST_NAME = "manifest.json"
_COMMITTED_NAME = "COMMITTED"


class StandardDeleteTransaction:
    """用同数据根内的目录重命名实现崩溃可恢复的批量删除。"""

    def __init__(
        self,
        *,
        root: Path,
        published_root: Path,
        creation_draft_root: Path,
    ) -> None:
        self.root = Path(root).resolve()
        self.published_root = Path(published_root).resolve()
        self.creation_draft_root = Path(creation_draft_root).resolve()

    def delete(self, standard_id: str, draft_ids: tuple[str, ...]) -> int:
        canonical_id = parse_standard_id(standard_id)
        normalized_draft_ids = self._validate_draft_ids(draft_ids)
        transaction_dir = self.root / uuid.uuid4().hex
        entries = self._entries(canonical_id, normalized_draft_ids, transaction_dir)
        for source, _ in entries:
            if source.is_symlink() or not source.is_dir():
                raise FileNotFoundError(f"删除目标目录不存在或不是普通目录：{source.name}")

        transaction_dir.mkdir(parents=True, exist_ok=False)
        manifest = {
            "schema_version": 1,
            "standard_id": canonical_id,
            "draft_ids": list(normalized_draft_ids),
        }
        atomic_write_text(
            transaction_dir / _MANIFEST_NAME,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        )

        try:
            for source, staged in entries:
                self._move(source, staged)
            atomic_write_text(transaction_dir / _COMMITTED_NAME, "committed\n")
        except Exception:
            if (transaction_dir / _COMMITTED_NAME).exists():
                self._cleanup_after_commit(transaction_dir)
                return len(normalized_draft_ids)
            self._rollback(entries)
            self._cleanup(transaction_dir)
            raise

        self._cleanup_after_commit(transaction_dir)
        return len(normalized_draft_ids)

    def recover(self) -> None:
        """按提交标记恢复未提交事务，或清理已提交事务的暂存目录。"""
        if not self.root.is_dir():
            return
        for transaction_dir in sorted(self.root.iterdir()):
            if (
                not _TRANSACTION_ID.fullmatch(transaction_dir.name)
                or transaction_dir.is_symlink()
                or not transaction_dir.is_dir()
            ):
                continue
            manifest_path = transaction_dir / _MANIFEST_NAME
            if not manifest_path.is_file():
                # 清单在任何目录移动之前持久化；未完成清单写入时没有数据被移动。
                staged_root = transaction_dir / "staged"
                if staged_root.is_dir() and any(staged_root.iterdir()):
                    raise RuntimeError(
                        f"标准删除事务缺少清单但暂存区非空：{transaction_dir.name}"
                    )
                self._cleanup(transaction_dir)
                continue
            manifest = self._read_manifest(manifest_path)
            entries = self._entries(manifest["standard_id"], manifest["draft_ids"], transaction_dir)
            if (transaction_dir / _COMMITTED_NAME).is_file():
                self._cleanup_after_commit(transaction_dir)
            else:
                self._rollback(entries)
                self._cleanup(transaction_dir)

    def _entries(
        self,
        standard_id: str,
        draft_ids: tuple[str, ...],
        transaction_dir: Path,
    ) -> list[tuple[Path, Path]]:
        staged_root = transaction_dir / "staged"
        entries = [
            (self.published_root / standard_id, staged_root / "standard")
        ]
        entries.extend(
            (
                self.creation_draft_root / draft_id,
                staged_root / "drafts" / f"{index:04d}",
            )
            for index, draft_id in enumerate(draft_ids)
        )
        return entries

    @staticmethod
    def _validate_draft_ids(draft_ids: tuple[str, ...]) -> tuple[str, ...]:
        if any(not isinstance(item, str) or not _DRAFT_ID.fullmatch(item) for item in draft_ids):
            raise ValueError("创建草稿 ID 非法")
        normalized = tuple(sorted(set(draft_ids)))
        if len(normalized) != len(draft_ids):
            raise ValueError("创建草稿 ID 重复")
        return normalized

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(value, dict)
                or type(value.get("schema_version")) is not int
                or value["schema_version"] != 1
            ):
                raise ValueError("事务清单版本无效")
            standard_id = parse_standard_id(value.get("standard_id"))
            raw_draft_ids = value.get("draft_ids")
            if not isinstance(raw_draft_ids, list) or any(
                not isinstance(item, str) for item in raw_draft_ids
            ):
                raise ValueError("事务清单草稿 ID 列表无效")
            draft_ids = StandardDeleteTransaction._validate_draft_ids(tuple(raw_draft_ids))
            if set(value) != {"schema_version", "standard_id", "draft_ids"}:
                raise ValueError("事务清单字段无效")
            return {"standard_id": standard_id, "draft_ids": draft_ids}
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RuntimeError(f"标准删除事务清单损坏：{path.parent.name}") from exc

    def _rollback(self, entries: list[tuple[Path, Path]]) -> None:
        for source, staged in reversed(entries):
            if not staged.exists():
                continue
            if source.exists() or source.is_symlink():
                raise RuntimeError(f"标准删除事务回滚目标已被占用：{source.name}")
            self._move(staged, source)

    def _move(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)

    def _cleanup_after_commit(self, transaction_dir: Path) -> None:
        try:
            self._cleanup(transaction_dir)
        except OSError:
            # 提交标记已经持久化；下次启动会继续清理，不应把已完成删除报告成失败。
            return

    @staticmethod
    def _cleanup(transaction_dir: Path) -> None:
        if transaction_dir.exists():
            shutil.rmtree(transaction_dir)
