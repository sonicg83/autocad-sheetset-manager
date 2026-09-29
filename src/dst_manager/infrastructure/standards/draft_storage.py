"""标准草稿与受控模板资产读写。"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Mapping
from pathlib import Path

from dst_manager.domain.standards import (
    DrawingStandard,
    StandardSchemaError,
    parse_standard_draft_document,
)
from dst_manager.infrastructure.filesystem.atomic import atomic_write_text
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    resolve_asset_file,
)
from dst_manager.infrastructure.standards.store_common import (
    _ASSET_NAME_ATTEMPTS,
    _COPY_CHUNK_SIZE,
    ALLOWED_ASSET_SUFFIXES,
    DOCUMENT_NAME,
    MANAGED_ASSET_PREFIX,
    MAX_ASSET_SOURCE_SIZE,
    StandardDraft,
    StandardStoreError,
    _error,
)


class StandardDraftStorage:
    """StandardDraftStorage 的标准库操作组合。"""

    def get_draft(self, draft_id: str) -> StandardDraft | None:
        document = self._draft_dir(draft_id) / DOCUMENT_NAME
        if not document.is_file():
            return None
        data = json.loads(document.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        if data.get("schema_version") != 3:
            return None
        try:
            parse_standard_draft_document(data)
        except StandardSchemaError:
            return None
        return StandardDraft(draft_id=draft_id, document=data)

    def _iter_drafts(self) -> list[StandardDraft]:
        drafts = []
        if not self._drafts_root.is_dir():
            return drafts
        for directory in sorted(self._drafts_root.iterdir()):
            if not directory.is_dir():
                continue
            try:
                draft = self.get_draft(directory.name)
            except StandardStoreError:
                # 目录名非法的草稿只跳过，不删除也不阻断其余条目。
                continue
            if draft is not None:
                drafts.append(draft)
        return drafts

    def create_draft(
        self, document: Mapping[str, object], draft_id: str | None = None
    ) -> StandardDraft:
        """保存一份草稿文档；只要求结构合法，允许语义未完成内容。"""
        standard = parse_standard_draft_document(document)  # 提前拒绝结构非法的草稿
        normalized_document = dict(document)
        normalized_document["standard_id"] = standard.standard_id
        # 显式空串不是「未指定」：仍按非法草稿段拒绝。
        if draft_id is None:
            draft_id = f"draft-{uuid.uuid4().hex[:12]}"
        target = self._draft_dir(draft_id)
        with self.lifecycle_lock():
            self.check_available_identity(standard.standard_id, standard.name)
            if target.exists():
                raise _error("STANDARD_DRAFT_EXISTS", f"草稿 {draft_id!r} 已存在")
            target.mkdir(parents=True)
            try:
                self._write_document(target, normalized_document)
            except BaseException:
                shutil.rmtree(target, ignore_errors=True)
                raise
        return StandardDraft(draft_id=draft_id, document=normalized_document)

    def save_draft(self, draft_id: str, document: Mapping[str, object]) -> StandardDraft:
        standard = parse_standard_draft_document(document)
        normalized_document = dict(document)
        normalized_document["standard_id"] = standard.standard_id
        target = self._draft_dir(draft_id)
        with self.lifecycle_lock():
            if not (target / DOCUMENT_NAME).is_file():
                raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
            self.check_available_identity(
                standard.standard_id,
                standard.name,
                exclude_draft_id=draft_id,
            )
            self._write_document(target, normalized_document)
            # 保存成功后清理本次编辑未引用的受控副本（手工放置的资产不受影响）。
            self._prune_managed_assets(target, standard)
        return StandardDraft(draft_id=draft_id, document=normalized_document)

    def delete_draft(self, draft_id: str) -> None:
        target = self._draft_dir(draft_id)
        if not target.is_dir():
            raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
        shutil.rmtree(target)

    def _write_document(self, directory: Path, document: Mapping[str, object]) -> None:
        atomic_write_text(
            directory / DOCUMENT_NAME,
            json.dumps(document, ensure_ascii=False, indent=2),
        )

    def copy_draft_asset(self, draft_id: str, source_path: Path) -> str:
        """把本机 DWG/DWT 受控复制进草稿，返回包内相对路径。

        来源只作一次性读取：不写回来源、不把绝对路径写进草稿。副本先写草稿内
        随机临时文件，校验完成后原子改名；任何失败都不留半文件、不覆盖已有副本。
        """
        draft_dir = self._draft_dir(draft_id)
        if not (draft_dir / DOCUMENT_NAME).is_file():
            raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
        source = Path(source_path)
        if not source.is_absolute() or not source.is_file():
            raise _error(
                "STANDARD_ASSET_SOURCE_NOT_FOUND",
                f"本机模板来源 {str(source_path)!r} 不存在或不是文件",
            )
        suffix = source.suffix.casefold()
        if suffix not in ALLOWED_ASSET_SUFFIXES:
            raise _error(
                "STANDARD_ASSET_SOURCE_INVALID",
                f"本机模板来源 {source.name!r} 必须是 .dwg 或 .dwt 文件",
            )
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise _error(
                "STANDARD_ASSET_SOURCE_NOT_FOUND", f"无法读取本机模板来源：{exc}"
            ) from exc
        if size > MAX_ASSET_SOURCE_SIZE:
            raise _error(
                "STANDARD_ASSET_SOURCE_INVALID",
                f"本机模板来源 {source.name!r} 超过 {MAX_ASSET_SOURCE_SIZE} 字节上限",
            )
        assets_dir = draft_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        final = self._free_asset_target(assets_dir, suffix)
        temp = assets_dir / f".{uuid.uuid4().hex}.copying"
        try:
            with source.open("rb") as reader, temp.open("wb") as writer:
                shutil.copyfileobj(reader, writer, length=_COPY_CHUNK_SIZE)
                writer.flush()
                os.fsync(writer.fileno())
            if temp.stat().st_size != size:
                raise _error(
                    "STANDARD_ASSET_COPY_FAILED", "复制结果大小与来源不一致，已放弃"
                )
            os.replace(temp, final)
        except OSError as exc:
            raise _error("STANDARD_ASSET_COPY_FAILED", f"复制本机模板失败：{exc}") from exc
        finally:
            temp.unlink(missing_ok=True)
        return f"assets/{final.name}"

    @staticmethod
    def _free_asset_target(assets_dir: Path, suffix: str) -> Path:
        """分配一个尚未占用的受控副本名；碰撞一律重试，不覆盖已有文件。"""
        for _ in range(_ASSET_NAME_ATTEMPTS):
            candidate = assets_dir / f"{MANAGED_ASSET_PREFIX}{uuid.uuid4().hex}{suffix}"
            if not candidate.exists():
                return candidate
        raise _error(
            "STANDARD_ASSET_COPY_FAILED",
            f"草稿资产目录 {assets_dir} 中无法分配唯一的受控副本名",
        )

    def _prune_managed_assets(
        self, draft_dir: Path, standard: DrawingStandard
    ) -> None:
        """清理未被文档引用且带受控前缀的副本；其他文件一律不碰。"""
        assets_dir = draft_dir / "assets"
        if not assets_dir.is_dir():
            return
        referenced: set[Path] = set()
        for asset in standard.assets:
            try:
                referenced.add(resolve_asset_file(draft_dir, asset.file))
            except StandardAssetError:
                continue  # 非法声明不参与引用集合，也不阻断清理
        for candidate in sorted(assets_dir.iterdir()):
            if not candidate.is_file() or not candidate.name.startswith(
                MANAGED_ASSET_PREFIX
            ):
                continue
            if candidate.resolve() in referenced:
                continue
            try:
                candidate.unlink()
            except OSError:
                # 清理是尽力而为：删除失败只留下无害的孤儿副本（导出白名单已排除）。
                continue
