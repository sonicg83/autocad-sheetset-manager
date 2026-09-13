"""图纸目录内置扩展：生命周期、预览与执行动作（PLAN-DM-020 Task 1/6/9 / PLAN-DM-025 Task 4）。

预览动作只从 :class:`~dst_manager.extensions.capabilities.ExtensionContext`
获取冻结工作区快照（SPEC-DM-012 §12 只读边界：不触碰 reader、DST、数据库
或文件系统），把请求模板交给 :mod:`.preview` 构建规范化预览、兼容性诊断与
确定性摘要。受限表达式与模板（Task 5）、候选 XLSX 导出（Task 7～9）分别
在各自模块落地。首期不注册后台计时器、外部进程或网络连接。

设置绑定（PLAN-DM-025 Task 4 / ARCH-DM-006 §11）：预览与执行都从同一
``ExtensionContext.settings`` 冻结快照读取规范化的“输出图纸过滤”关键词，
并调用 Provider 的同一 :func:`title_matches_exclusion` 做图名排除；扩展不读
Store、不缓存设置，也不二次解释用户输入。

执行通道（Task 9 / SPEC §8.2）：

- :meth:`SheetCatalogExtension.repreview` 由宿主运行时在执行前调用，对当前
  快照重建预览供摘要复核（修订/模板/扩展身份/设置漂移 → ``REPREVIEW_REQUIRED``
  或 ``EXTENSION_SETTINGS_CHANGED``）；
- :meth:`SheetCatalogExtension.execute` 只组装"上下文快照 → 候选文件"：把
  过滤后的目录行写成宿主分配的 :class:`ArtifactProposalDirectory` 内唯一候选
  XLSX 并返回 :class:`CandidateArtifact`（扩展不见目标路径、不消费授权、不
  登记）；宿主回读校验、消费授权、原子保存与 Artifact 登记都在宿主侧完成。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dst_manager.extensions.builtin.sheet_catalog.expressions import (
    bind_expression,
    evaluate_expression,
)
from dst_manager.extensions.builtin.sheet_catalog.preview import (
    SheetCatalogDiagnostic,
    SheetCatalogPreview,
    SheetCatalogPreviewRequest,
    build_preview,
    projected_sheets,
)
from dst_manager.extensions.builtin.sheet_catalog.settings import (
    EXCLUDED_TITLE_KEYWORDS_FIELD,
    normalize_excluded_title_keywords,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import (
    SheetCatalogTemplate,
    validate_template,
)
from dst_manager.extensions.builtin.sheet_catalog.workbook import write_candidate
from dst_manager.extensions.capabilities import ExtensionContext
from dst_manager.extensions.contracts import XLSX_MEDIA_TYPE, Extension
from dst_manager.extensions.settings import ExtensionSettingsSnapshot
from dst_manager.extensions.snapshots import (
    SheetSnapshot,
    WorkspaceSnapshot,
    build_field_catalog,
)

#: 与随包 manifest.yaml 保持一致（由单元测试钉住，防止漂移）。
EXTENSION_ID = "dst-manager.sheet-catalog"
EXTENSION_VERSION = "0.1.0"
PREVIEW_ACTION_ID = "export-xlsx"

#: 宿主候选目录内的固定候选文件名（目录本身按次唯一，由宿主分配与清理）。
CANDIDATE_FILE_NAME = "sheet-catalog-candidate.xlsx"


@dataclass(frozen=True, slots=True)
class SheetCatalogExecuteRequest:
    """执行请求（SPEC-DM-012 §8.2）：重复提交模板快照、预览摘要与设置修订。

    ``settings_revision`` 是预览响应回传、前端原样重复提交的乐观并发绑定值；
    宿主在执行前用它核对已应用的设置是否仍是预览时那一份（§11）。
    """

    workspace_id: str
    base_revision_id: str
    template: SheetCatalogTemplate
    preview_digest: str
    save_grant_id: str
    settings_revision: int


@dataclass(frozen=True, slots=True)
class SheetCatalogExecuteResponse:
    """执行成功响应：Artifact ID/文件名/用户选择的保存路径/非阻断警告。

    刻意不含 sha256/source_revision/extension_version——后台字段只经
    Artifact 查询接口（``GET /api/artifacts/{id}``）披露。
    """

    artifact_id: str
    file_name: str
    output_path: str
    warnings: tuple[SheetCatalogDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class ArtifactProposalDirectory:
    """宿主按次分配的候选目录；``root`` 只指向应用临时目录。"""

    root: Path


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    """扩展产出候选的宿主侧交接物：路径 + 宿主回读校验所需的形状。"""

    path: Path
    media_type: str
    expected_headers: tuple[str, ...]
    expected_rows: int


class SheetCatalogExtension:
    """首期无后台资源；start/stop 只标记生命周期边界。"""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def preview(
        self, context: ExtensionContext, request: SheetCatalogPreviewRequest
    ) -> SheetCatalogPreview:
        """对上下文冻结快照与冻结设置构建图纸目录预览（漂移由上下文拒绝）。"""
        snapshot = context.workspace_snapshot()
        settings = context.settings
        return build_preview(
            snapshot,
            request.template,
            extension_id=EXTENSION_ID,
            extension_version=EXTENSION_VERSION,
            action_id=PREVIEW_ACTION_ID,
            excluded_title_keywords=_excluded_title_keywords(settings),
            settings_schema_version=settings.schema_version,
            settings_revision=settings.revision,
            settings_digest=settings.digest,
        )

    def repreview(
        self, context: ExtensionContext, request: SheetCatalogExecuteRequest
    ) -> SheetCatalogPreview:
        """宿主执行前的摘要复核入口：对当前快照重建同一预览投影。"""
        return self.preview(
            context,
            SheetCatalogPreviewRequest(
                workspace_id=request.workspace_id,
                base_revision_id=request.base_revision_id,
                template=request.template,
            ),
        )

    def execute(
        self,
        context: ExtensionContext,
        request: SheetCatalogExecuteRequest,
        proposal_directory: ArtifactProposalDirectory,
    ) -> CandidateArtifact:
        """把过滤后的目录行写成候选 XLSX；保存/登记由宿主完成（SPEC §8.2）。

        摘要复核已在宿主侧通过：此处模板必然可解析、字段必然可绑定；缺值
        仍按空字符串求值（允许导出的 warning 语义与预览一致）。过滤词与预览
        取自同一 ``context.settings`` 快照，行投影与预览计数因此同源。
        """
        snapshot = context.workspace_snapshot()
        sheets = projected_sheets(snapshot, _excluded_title_keywords(context.settings))
        headers, rows = _catalog_rows(snapshot, request.template, sheets)
        candidate_path = proposal_directory.root / CANDIDATE_FILE_NAME
        summary = write_candidate(candidate_path, headers, rows)
        return CandidateArtifact(
            path=candidate_path,
            media_type=XLSX_MEDIA_TYPE,
            expected_headers=summary.headers,
            expected_rows=summary.data_rows,
        )


def _excluded_title_keywords(settings: ExtensionSettingsSnapshot) -> tuple[str, ...]:
    """从冻结设置快照取得规范化的“输出图纸过滤”关键词。

    快照的有效值由 Provider 的 ``resolve()`` 生成（已是规范数组），此处仍走
    同一 :func:`normalize_excluded_title_keywords` 纯函数：预览与执行不各自
    解释用户输入，缺失该字段（无用户显式过滤词）等价于不过滤。
    """
    return normalize_excluded_title_keywords(
        settings.value.get(EXCLUDED_TITLE_KEYWORDS_FIELD)
    )


def _catalog_rows(
    snapshot: WorkspaceSnapshot,
    template: SheetCatalogTemplate,
    sheets: Sequence[SheetSnapshot],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """求值给定图纸行（预览只回 20 行；导出必须全量，求值语义与预览一致）。

    ``sheets`` 是已经过输出图纸过滤的投影（与预览同一 ``projected_sheets``），
    因此候选 XLSX 的数据行数等于预览的 ``total_rows``。
    """
    field_catalog = build_field_catalog(snapshot)
    validated = validate_template(template)
    expressions = [
        bind_expression(tokens, field_catalog) for tokens in validated.parsed_columns
    ]
    rows = tuple(
        tuple(
            evaluate_expression(expression, snapshot.sheetset, sheet)
            for expression in expressions
        )
        for sheet in sheets
    )
    headers = tuple(column.header for column in validated.template.columns)
    return headers, rows


def create_sheet_catalog_extension() -> Extension:
    """固定索引引用的工厂函数。"""
    return SheetCatalogExtension()
