"""创建草稿应用编排（PLAN-DM-036 Task 1）。

`CreationDraftOperations` 以 mixin 组合进 `DstManagerService`：固定已发布标准的
身份、按作用域校验用户输入、把仓储的结构/修订错误转译为稳定 HTTP 错误码。
标准解析走 `StandardStore`（只读已发布内容），因此标准草稿不可用于创建；草稿
固定的版本在库中消失时以 `CREATION_STANDARD_MISSING` 稳定拒绝，不静默降级。

本模块不运行派生求值、编号或 DWG 命名（属于预览/执行域），也不解析 XLSX。
"""

from __future__ import annotations

from dst_manager.application.errors import ApplicationError
from dst_manager.domain.creation import (
    SHEET_SCOPE,
    SHEETSET_SCOPE,
    CreationDraft,
    ordinary_property_defaults,
    unknown_value_property_ids,
)
from dst_manager.domain.standards import DrawingStandard
from dst_manager.infrastructure.creation_drafts import (
    CreationDraftStore,
    CreationDraftStoreError,
)

#: 创建草稿稳定错误码 → HTTP 状态。
_CREATION_STATUS = {
    "CREATION_DRAFT_CONFLICT": 409,
    "CREATION_DRAFT_CORRUPT": 409,
    "CREATION_DRAFT_INVALID": 422,
    "CREATION_DRAFT_NOT_FOUND": 404,
    "CREATION_STANDARD_MISSING": 404,
}


def _creation_error(code: str, detail: str) -> ApplicationError:
    """应用层新造的稳定错误：消息统一以「错误码: 详情」呈现。"""
    return ApplicationError(code, f"{code}: {detail}", _CREATION_STATUS.get(code, 422))


def _store_error(exc: CreationDraftStoreError) -> ApplicationError:
    """仓储错误码 → HTTP 稳定错误；仓储消息已以错误码开头，原样透出。"""
    return ApplicationError(exc.code, str(exc), _CREATION_STATUS.get(exc.code, 422))


class CreationDraftOperations:
    """经 `self` 访问 standard_store/creation_drafts 的创建草稿功能域。"""

    standard_store: object  # 由 DstManagerService.__init__ 注入 StandardStore
    creation_drafts: CreationDraftStore  # 由 DstManagerService.__init__ 注入

    # ---- 草稿生命周期 ----------------------------------------------------

    def create_creation_draft(self, identity: tuple[str, int]) -> CreationDraft:
        """固定一个已发布标准版本并建立修订 1 的空草稿。

        初建时对每个普通 sheetset 属性应用一次标准默认值；``target_path`` 与
        图纸组留空，由后续保存逐步补全。
        """
        standard = self._require_published_standard(identity[0], identity[1])
        try:
            return self.creation_drafts.create(
                standard.standard_id,
                standard.version,
                ordinary_property_defaults(standard, SHEETSET_SCOPE),
            )
        except CreationDraftStoreError as exc:
            raise _store_error(exc) from exc

    def get_creation_draft(self, draft_id: str) -> CreationDraft:
        """恢复草稿；固定标准版本不可解析时稳定拒绝。"""
        draft = self._load_creation_draft(draft_id)
        self._require_published_standard(draft.standard_id, draft.standard_version)
        return draft

    def save_creation_draft(
        self, draft_id: str, *, expected_revision: int, value: CreationDraft
    ) -> CreationDraft:
        """按乐观修订保存草稿；任何输入变更都递增修订并使旧预览失效。

        草稿只保存可输入普通属性；派生字段、跨作用域字段、未知字段、重复组
        身份、改写固定标准或草稿 ID 的请求一律以 `CREATION_DRAFT_INVALID` 拒绝，
        且不改变磁盘内容与修订号。
        """
        stored = self._load_creation_draft(draft_id)
        standard = self._require_published_standard(
            stored.standard_id, stored.standard_version
        )
        self._reject_non_input_values(standard, value)
        try:
            return self.creation_drafts.save(
                draft_id, value, expected_revision=expected_revision
            )
        except CreationDraftStoreError as exc:
            raise _store_error(exc) from exc

    def delete_creation_draft(self, draft_id: str) -> None:
        """放弃草稿（「重新开始」）；草稿不存在时稳定报缺失。"""
        try:
            self.creation_drafts.delete(draft_id)
        except CreationDraftStoreError as exc:
            raise _store_error(exc) from exc

    # ---- 内部辅助 --------------------------------------------------------

    def _load_creation_draft(self, draft_id: str) -> CreationDraft:
        try:
            return self.creation_drafts.load(draft_id)
        except CreationDraftStoreError as exc:
            raise _store_error(exc) from exc

    def _require_published_standard(self, standard_id: str, version: int) -> DrawingStandard:
        standard = self.standard_store.get(standard_id, version)
        if standard is None:
            raise _creation_error(
                "CREATION_STANDARD_MISSING",
                f"标准 {standard_id}@{version} 未发布或已不可用，请重新选择标准后创建",
            )
        return standard

    @staticmethod
    def _reject_non_input_values(standard: DrawingStandard, value: CreationDraft) -> None:
        """拒绝非「可输入普通属性」的值键：派生结果与逐张输入不得进入草稿。"""
        unknown = unknown_value_property_ids(standard, SHEETSET_SCOPE, value.sheetset_values)
        if unknown:
            raise _creation_error(
                "CREATION_DRAFT_INVALID",
                f"图纸集输入包含非可输入普通属性 {list(unknown)}",
            )
        for group in value.groups:
            unknown = unknown_value_property_ids(standard, SHEET_SCOPE, group.sheet_values)
            if unknown:
                raise _creation_error(
                    "CREATION_DRAFT_INVALID",
                    f"图纸组 {group.group_id!r} 输入包含非可输入普通属性 {list(unknown)}",
                )
