"""草稿（Draft）功能域：工作区草稿的读取、保存与删除（v0.3.2 Task 0 自 service.py 拆分）。

`DraftOperations` 以 mixin 组合进 `DstManagerService`，通过 `self` 访问
入口持有的 database/drafts 等依赖，公共方法签名与行为保持不变。
"""

from typing import Any

from dst_manager.application.errors import ApplicationError
from dst_manager.domain.models import Workspace
from dst_manager.infrastructure.drafts import DraftConflictError


class DraftOperations:
    def get_draft(self, workspace_id: str) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        loaded = self.drafts.load(workspace_id)
        return self._draft_envelope(workspace, loaded)

    def save_draft(
        self,
        workspace_id: str,
        draft: dict[str, Any],
        expected_version: int,
    ) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        try:
            saved = self.drafts.save(
                workspace_id,
                draft,
                expected_version=expected_version,
            )
        except DraftConflictError as exc:
            raise ApplicationError("DRAFT_CONFLICT", str(exc), 409) from exc
        return self._draft_envelope(workspace, {"draft": saved, "corrupted": False})

    def delete_draft(self, workspace_id: str, expected_version: int) -> dict[str, bool]:
        self.get_workspace(workspace_id)
        try:
            deleted = self.drafts.delete(workspace_id, expected_version=expected_version)
        except DraftConflictError as exc:
            raise ApplicationError("DRAFT_CONFLICT", str(exc), 409) from exc
        return {"deleted": deleted}

    @staticmethod
    def _draft_envelope(workspace: Workspace, loaded: dict[str, Any]) -> dict[str, Any]:
        draft = loaded["draft"]
        reasons: list[str] = []
        if draft is not None:
            if draft.get("base_revision_id") != workspace.revision_id:
                reasons.append("BASE_REVISION_CHANGED")
            current_repair_status = (
                workspace.document.repair_report.status
                if workspace.document.repair_report is not None
                else "VALID"
            )
            if draft.get("repair_status") != current_repair_status:
                reasons.append("REPAIR_STATUS_CHANGED")
        return {
            "draft": draft,
            "corrupted": bool(loaded["corrupted"]),
            "stale": bool(reasons),
            "stale_reasons": reasons,
        }
