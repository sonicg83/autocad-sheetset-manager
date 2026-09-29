"""标准删除影响计算与事务编排。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dst_manager.application.errors import ApplicationError
from dst_manager.domain.standard_identity import parse_standard_id
from dst_manager.infrastructure.persistence.creation_jobs import (
    list_active_creation_jobs_for_standard,
)
from dst_manager.infrastructure.standards.delete_transaction import (
    StandardDeleteTransaction,
)
from dst_manager.infrastructure.standards.store import StandardStore, StandardStoreError


class StandardDeletionOperations:
    """通过标准库生命周期锁协调包、创建草稿和运行任务。"""

    standard_store: StandardStore
    creation_drafts: Any
    database: Any
    standard_delete_transaction: StandardDeleteTransaction

    def standard_delete_impact(self, standard_id: str) -> dict[str, object]:
        canonical_id = self._canonical_id(standard_id)
        with self.standard_store.lifecycle_lock():
            self._require_user_standard(canonical_id)
            draft_ids = self.creation_drafts.list_by_standard(canonical_id)
            return {
                "standard_id": canonical_id,
                "affected_count": len(draft_ids),
                "impact_token": self._impact_token(canonical_id, draft_ids),
            }

    def delete_standard(self, standard_id: str, impact_token: str) -> dict[str, object]:
        canonical_id = self._canonical_id(standard_id)
        with self.standard_store.lifecycle_lock():
            self._require_user_standard(canonical_id)
            draft_ids = self.creation_drafts.list_by_standard(canonical_id)
            if impact_token != self._impact_token(canonical_id, draft_ids):
                raise ApplicationError(
                    "STANDARD_DELETE_IMPACT_CHANGED",
                    "标准删除影响已变化，请重新预览",
                    409,
                )
            active_jobs = list_active_creation_jobs_for_standard(self.database, canonical_id)
            if active_jobs:
                raise ApplicationError(
                    "STANDARD_DELETE_JOB_ACTIVE",
                    "仍有创建任务正在使用此标准",
                    409,
                )
            try:
                deleted_count = self.standard_delete_transaction.delete(canonical_id, draft_ids)
            except Exception as exc:
                raise ApplicationError(
                    "STANDARD_DELETE_FAILED",
                    "标准删除事务失败；启动恢复会继续处理未完成的事务",
                    500,
                ) from exc
            return {"standard_id": canonical_id, "deleted_count": deleted_count}

    def _require_user_standard(self, standard_id: str) -> None:
        official_document = Path(self.standard_store.official_root) / standard_id / "document.json"
        if official_document.is_file():
            raise ApplicationError(
                "STANDARD_DELETE_FORBIDDEN", "官方标准不可删除", 403
            )
        user_document = Path(self.standard_store.published_root) / standard_id / "document.json"
        if not user_document.is_file():
            raise ApplicationError(
                "STANDARD_ID_NOT_FOUND", f"用户标准 {standard_id!r} 不存在", 404
            )
        if self.standard_store.is_legacy_published(standard_id):
            raise ApplicationError(
                "STANDARD_LEGACY_READ_ONLY",
                "旧版标准仅供查看与历史兼容，不能删除",
                409,
            )
        try:
            if self.standard_store.get(standard_id) is None:
                raise ApplicationError(
                    "STANDARD_ID_NOT_FOUND", f"用户标准 {standard_id!r} 不存在", 404
                )
        except StandardStoreError as exc:
            code = str(exc).split(":", 1)[0]
            raise ApplicationError(code, str(exc), 422) from exc

    @staticmethod
    def _canonical_id(standard_id: str) -> str:
        try:
            return parse_standard_id(standard_id)
        except (TypeError, ValueError) as exc:
            raise ApplicationError(
                "STANDARD_ID_INVALID", f"标准 ID {standard_id!r} 非法", 422
            ) from exc

    @staticmethod
    def _impact_token(standard_id: str, draft_ids: tuple[str, ...]) -> str:
        payload = json.dumps(
            {"standard_id": standard_id, "draft_ids": sorted(draft_ids)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
