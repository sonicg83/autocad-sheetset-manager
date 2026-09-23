"""创建草稿、XLSX 与权威预览的应用编排（PLAN-DM-036 Task 4）。

`CreationOperations` 以 mixin 组合进 `DstManagerService`：标准候选、XLSX 模板
导出与全量导入、以及权威预览。它只做编排与稳定错误转译，不解析 XLSX（解析在
:mod:`dst_manager.application.creation_import`）、不执行编号或 DWG 命名（在领域
层 :mod:`dst_manager.domain.creation_planning`）、不做文件操作（除草稿 JSON）。

关键语义：

- 标准候选只列已发布且**依赖与受控资产都可用**的标准（见
  :mod:`dst_manager.application.creation_assets`），不可用的候选带原因；
- 完整最终路径（上级目录 + 目录名、或 XLSX 的完整路径）只经同一 ``target_path``
  字段流转，不从任何自定义属性推断；
- 目标只能是尚不存在的新目录或已存在的空目录；预览与执行都必须重查目标状态，
  非空/同名文件以 ``CREATION_TARGET_NOT_EMPTY`` 阻断；
- XLSX 导入是全量覆盖且原子的：先整批解析校验，最后一次性保存；解析失败时
  草稿 JSON 与修订号零变化，陈旧修订由保存门禁以 ``CREATION_DRAFT_CONFLICT``
  拒绝，绝不写入半新半旧状态；
- 预览重新加载标准、当前设置、草稿与目标状态，验证资产文件与图幅声明并计算
  内容哈希；``preview_digest`` 绑定标准文档、草稿修订、有效设置、资产哈希、
  目标状态与领域计划内容，任一项变化都必须产生不同摘要；
- 预览全过程不启动 CAD、不写文件（除草稿自身的读取）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from dst_manager.application.creation_assets import (
    CreationAssetSnapshot,
    CreationStandardCandidate,
    creation_asset_options,
    creation_standard_candidates,
    resolve_creation_assets,
    standard_document_digest,
)
from dst_manager.application.creation_import import (
    build_creation_template,
    parse_creation_workbook,
)
from dst_manager.application.errors import ApplicationError
from dst_manager.domain.creation import (
    CreationDiagnostic,
    CreationDraft,
    CreationGroupInput,
    validate_creation_target_path,
)
from dst_manager.domain.creation_plan_models import (
    CreationPlan,
    CreationPlanDiagnostic,
    GroupPlan,
)
from dst_manager.domain.creation_planning import create_creation_plan
from dst_manager.domain.keywords import normalize_keywords
from dst_manager.domain.models import SuffixOptions
from dst_manager.domain.standard_models import DrawingStandard, NumberingPolicy
from dst_manager.infrastructure.creation_drafts import CreationDraftStore
from dst_manager.infrastructure.standards.package import MAX_ENTRY_SIZE

__all__ = [
    "MAX_CREATION_XLSX_BYTES",
    "CreationImportOutcome",
    "CreationOperations",
    "CreationTemplateFile",
    "creation_preview_digest",
]

#: 单个导入工作簿的字节上限：与标准包单条目上限同一口径，避免异常输入占满内存。
MAX_CREATION_XLSX_BYTES = MAX_ENTRY_SIZE


def _creation_error(code: str, detail: str, status_code: int = 422) -> ApplicationError:
    """应用层新造的稳定错误：消息统一以「错误码: 详情」呈现。

    状态码在 raise 点显式给出（不另立一份码→状态映射），避免与草稿功能域的
    同名码状态漂移。
    """
    return ApplicationError(code, f"{code}: {detail}", status_code)


@dataclass(frozen=True, slots=True)
class CreationTemplateFile:
    """一次 XLSX 模板导出：受控字节与建议文件名（文件名只含标准身份）。"""

    filename: str
    data: bytes


@dataclass(frozen=True, slots=True)
class CreationImportOutcome:
    """一次 XLSX 导入的结果：成功时为保存后的草稿，被拒时为可定位诊断。"""

    draft: CreationDraft | None = None
    diagnostics: tuple[CreationDiagnostic, ...] = ()


class CreationOperations:
    """经 `self` 访问 standard_store/creation_drafts/设置入口的创建功能域。"""

    standard_store: object  # 由 DstManagerService.__init__ 注入 StandardStore
    creation_drafts: CreationDraftStore  # 由 DstManagerService.__init__ 注入

    # ---- 标准候选 --------------------------------------------------------

    def list_creation_standards(
        self, manifests: Mapping[str, object] | None = None
    ) -> list[dict[str, object]]:
        """创建可用的标准候选；不可用的候选同样返回，并说明原因。"""
        return [
            _candidate_payload(candidate)
            for candidate in creation_standard_candidates(
                self.standard_store, manifests or {}
            )
        ]

    # ---- XLSX 模板与全量导入 ---------------------------------------------

    def creation_xlsx_template(self, draft_id: str) -> CreationTemplateFile:
        """按草稿固定的标准版本导出模板；标签与导入校验共用同一份资产候选。"""
        draft = self._load_creation_draft(draft_id)
        standard = self._require_published_standard(
            (draft.standard_id, draft.standard_version)
        )
        return CreationTemplateFile(
            filename=f"creation-template-{standard.standard_id}-{standard.version}.xlsx",
            data=build_creation_template(standard, creation_asset_options(standard)),
        )

    def import_creation_xlsx(
        self, draft_id: str, data: bytes, *, expected_revision: int | None = None
    ) -> CreationImportOutcome:
        """全量覆盖导入：整批解析校验后才一次性保存，失败不留任何改动。

        ``expected_revision`` 给出时由保存门禁按乐观修订校验（陈旧即 409
        ``CREATION_DRAFT_CONFLICT``）；未给出时以读取到的当前修订保存，读取与
        保存之间的并发修改同样由仓储的修订检查拒绝。
        """
        draft = self._load_creation_draft(draft_id)
        standard = self._require_published_standard(
            (draft.standard_id, draft.standard_version)
        )
        if len(data) > MAX_CREATION_XLSX_BYTES:
            return CreationImportOutcome(
                diagnostics=(
                    CreationDiagnostic(
                        "CREATION_XLSX_SCALE_EXCEEDED",
                        f"工作簿大小 {len(data)} 超过受控上限 {MAX_CREATION_XLSX_BYTES} 字节",
                    ),
                )
            )
        result = parse_creation_workbook(
            data, standard, creation_asset_options(standard)
        )
        if result.value is None:
            return CreationImportOutcome(diagnostics=result.diagnostics)
        value = result.value
        saved = self.save_creation_draft(
            draft_id,
            expected_revision=(
                draft.revision if expected_revision is None else expected_revision
            ),
            value=replace(
                draft,
                target_path=value.target_path,
                sheetset_values=dict(value.sheetset_values),
                groups=value.groups,
            ),
        )
        return CreationImportOutcome(draft=saved)

    # ---- 权威预览 --------------------------------------------------------

    def preview(self, draft_id: str) -> dict[str, object]:
        """权威预览：重新加载标准、设置、草稿与目标状态，返回按组表格与摘要。

        只读：不启动 CAD、不写文件、不改变草稿修订。
        """
        return self._creation_preview(draft_id)[2]

    def _creation_preview(
        self, draft_id: str
    ) -> tuple[CreationDraft, CreationPlan, dict[str, object]]:
        """重算一次权威预览，同时返回草稿与计划：预览、执行与 Worker 侧复核共用。

        三者必须来自同一次重算（标准文档、设置、资产、目标状态都在同一次快照里），
        否则摘要与计划可能对应不同现场。
        """
        draft = self._load_creation_draft(draft_id)
        standard = self._require_published_standard(
            (draft.standard_id, draft.standard_version)
        )
        settings = self._live_settings()
        suffix_options = SuffixOptions(
            settings.enable_add_number_suffix,
            settings.number_suffix_type,
            normalize_keywords(settings.unnumbered_subset_keywords),
        )
        target_state = self._require_creation_target(draft.target_path)
        assets = resolve_creation_assets(self.standard_store, standard)
        plan = create_creation_plan(draft, standard, suffix_options)
        diagnostics = _preview_diagnostics(draft, assets, plan)
        payload: dict[str, object] = {
            "draft_id": draft.id,
            "revision": draft.revision,
            "standard_id": standard.standard_id,
            "standard_version": standard.version,
            "standard_name": standard.name,
            "target_path": draft.target_path,
            "sheetset_values": dict(plan.sheetset_values),
            "group_count": len(plan.groups),
            "sheet_count": sum(group.sheet_count for group in plan.groups),
            "dwg_count": len(plan.groups),
            "numbering": {
                "sequence_field": standard.numbering.sequence_field,
                "digits": standard.numbering.digits,
                "start": standard.numbering.start,
            },
            "suffix": {
                "enabled": suffix_options.enabled,
                "suffix_type": suffix_options.suffix_type,
                "unnumbered_keywords": list(suffix_options.unnumbered_keywords),
            },
            "diagnostics": [_diagnostic_payload(item) for item in diagnostics],
            "groups": [_group_payload(group) for group in plan.groups],
            "executable": not any(item.is_error for item in diagnostics),
            "preview_digest": creation_preview_digest(
                draft=draft,
                plan=plan,
                standard_digest=self._standard_document_digest(standard),
                assets_digest=assets.digest,
                suffix_options=suffix_options,
                numbering=standard.numbering,
                target_state=target_state,
                diagnostics=diagnostics,
            ),
        }
        return draft, plan, payload

    # ---- 草稿输入保存 ----------------------------------------------------

    def update_creation_draft(
        self,
        draft_id: str,
        *,
        expected_revision: int,
        step: str,
        target_path: str,
        sheetset_values: Mapping[str, str],
        groups: Sequence[CreationGroupInput],
    ) -> CreationDraft:
        """按乐观修订保存草稿输入；草稿身份与固定标准只由已存草稿决定。

        完整最终路径（上级目录 + 目录名，或 XLSX 的完整路径）只写入这一个
        ``target_path`` 字段，不从任何自定义属性推断。
        """
        stored = self._load_creation_draft(draft_id)
        return self.save_creation_draft(
            draft_id,
            expected_revision=expected_revision,
            value=replace(
                stored,
                step=step,
                target_path=target_path,
                sheetset_values=dict(sheetset_values),
                groups=tuple(groups),
            ),
        )

    # ---- 内部辅助 --------------------------------------------------------

    def _require_creation_target(self, target_path: str) -> str:
        """目标状态门禁：只能是尚不存在的新目录或已存在的空目录。

        路径形状非法时不做文件系统判定（由领域诊断定位到字段），返回 ``invalid``。
        """
        if validate_creation_target_path(target_path):
            return "invalid"
        path = Path(target_path)
        if not path.exists():
            return "missing"
        if path.is_dir() and not any(path.iterdir()):
            return "empty-directory"
        raise _creation_error(
            "CREATION_TARGET_NOT_EMPTY",
            f"目标 {target_path!r} 不能作为新项目目录（已存在同名文件或目录非空）",
        )

    def _standard_document_digest(self, standard: DrawingStandard) -> str:
        """已发布标准文档内容哈希；标准在读取后消失时仍按缺失稳定拒绝。"""
        document = self.standard_store.get_document(standard.standard_id, standard.version)
        if document is None:
            raise _creation_error(
                "CREATION_STANDARD_MISSING",
                f"标准 {standard.standard_id}@{standard.version} 未发布或已不可用",
                404,
            )
        return standard_document_digest(document)


def creation_preview_digest(
    *,
    draft: CreationDraft,
    plan: CreationPlan,
    standard_digest: str,
    assets_digest: str,
    suffix_options: SuffixOptions,
    numbering: NumberingPolicy,
    target_state: str,
    diagnostics: Sequence[CreationPlanDiagnostic],
) -> str:
    """预览摘要：绑定标准文档、草稿修订、有效设置、资产哈希、目标状态与计划内容。

    有效设置包含编号策略（位数/起点/序号字段）与标题后缀、不编号关键字；
    目标状态区分「尚不存在」与「已存在空目录」，两者都不阻断但摘要不同。
    """
    payload = {
        "draft": {
            "id": draft.id,
            "revision": draft.revision,
            "target_path": draft.target_path,
        },
        "standard": standard_digest,
        "assets": assets_digest,
        "numbering": {
            "sequence_field": numbering.sequence_field,
            "digits": numbering.digits,
            "start": numbering.start,
        },
        "suffix": {
            "enabled": suffix_options.enabled,
            "suffix_type": suffix_options.suffix_type,
            "unnumbered_keywords": list(suffix_options.unnumbered_keywords),
        },
        "target": {"path": plan.target_path, "state": target_state},
        "plan": plan.digest,
        "diagnostics": [
            [item.code, item.group_id, item.property_id, item.severity]
            for item in diagnostics
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _preview_diagnostics(
    draft: CreationDraft, assets: CreationAssetSnapshot, plan: CreationPlan
) -> list[CreationPlanDiagnostic]:
    """预览门禁：计划器不判定的两项（空图纸组、资产文件可用性）在此显式阻断。"""
    diagnostics: list[CreationPlanDiagnostic] = []
    if not draft.groups:
        diagnostics.append(
            CreationPlanDiagnostic(
                code="CREATION_GROUPS_EMPTY",
                message="草稿还没有图纸组：至少需要一个图纸组才能创建图纸集",
            )
        )
    diagnostics.extend(
        CreationPlanDiagnostic(
            code="CREATION_ASSET_FILE_MISSING",
            message=(
                f"标准资产 {item.asset_id!r} 声明的文件 {item.path!r} 不存在或路径非法，"
                "模板不可用"
            ),
        )
        for item in assets.missing_files
    )
    diagnostics.extend(plan.diagnostics)
    return diagnostics


def _candidate_payload(candidate: CreationStandardCandidate) -> dict[str, object]:
    return {
        "standard_id": candidate.standard_id,
        "version": candidate.version,
        "name": candidate.name,
        "supported_cad_versions": list(candidate.supported_cad_versions),
        "available": candidate.available,
        "reasons": list(candidate.reasons),
        "asset_options": [
            {
                "asset_id": option.asset_id,
                "kind": option.kind,
                "label": option.label,
                "layouts": list(option.layouts),
            }
            for option in candidate.asset_options
        ],
    }


def _diagnostic_payload(diagnostic: CreationPlanDiagnostic) -> dict[str, object]:
    return {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "severity": diagnostic.severity,
        "group_id": diagnostic.group_id,
        "property_id": diagnostic.property_id,
    }


def _group_payload(group: GroupPlan) -> dict[str, object]:
    return {
        "group_id": group.group_id,
        "created_order": group.created_order,
        "title": group.title,
        "number_range": group.number_range,
        "title_range": group.title_range,
        "base_template": group.base_template,
        "layout_template": group.layout_template,
        "paper_layout": group.paper_layout,
        "dwg_name": group.dwg_name,
        "target_path": group.target_path,
        "sheet_count": group.sheet_count,
        "sheets": [
            {
                "number": sheet.number,
                "title": sheet.title,
                "layout_name": sheet.layout_name,
                "values": dict(sheet.values),
            }
            for sheet in group.sheets
        ],
        "property_cells": {
            property_id: {
                "property_id": cell.property_id,
                "first_value": cell.first_value,
                "sheets": [
                    {"number": row.number, "value": row.value} for row in cell.sheets
                ],
            }
            for property_id, cell in group.property_cells.items()
        },
    }
