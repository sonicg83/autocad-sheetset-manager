"""创建草稿、XLSX 与权威预览路由（PLAN-DM-036 Task 4）。

:func:`register_creation_routes` 把 ``/api/creation-drafts`` 系列端点直接注册到
宿主 ``FastAPI``（与 standard_api/extension_api 同形态，不引入 ``APIRouter``）。
路由只做请求/响应转换、状态码与错误映射：草稿结构门禁、XLSX 解析、资产解析与
编号/命名派生全部在应用层与领域层完成。

``/{draft_id}/execute`` 只接受草稿 ID 与 `preview_digest`：执行前重新加载标准、
草稿、目标与设置/资产快照并重算摘要（漂移 409 `CREATION_PREVIEW_STALE`），入队
创建任务；目标目录不写任何文件（成果只能由 Worker 发布）。标准候选路由必须先于
``/{draft_id}`` 注册，避免 ``standards`` 段被身份路由吞掉。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from dst_manager.domain.creation import (
    CreationDiagnostic,
    CreationDraft,
    CreationGroupInput,
)
from dst_manager.interfaces.creation_contracts import (
    CreationDraftCreateRequest,
    CreationDraftResponse,
    CreationDraftSaveRequest,
    CreationExecuteRequest,
    CreationGroupModel,
    CreationImportRejectedResponse,
    CreationPreviewResponse,
    CreationStandardCandidateModel,
)
from dst_manager.interfaces.message_catalog import error_payload
from dst_manager.interfaces.responses import JobResponse

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

#: XLSX 工作簿 MIME：桌面壳与浏览器都按该类型落盘。
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def register_creation_routes(app: FastAPI) -> None:
    """把创建路由注册到宿主应用。"""

    def service(request: Request):
        return request.app.state.service

    @app.get(
        "/api/creation-drafts/standards",
        response_model=list[CreationStandardCandidateModel],
        response_model_exclude_unset=True,
    )
    def list_creation_standards(request: Request):
        return service(request).list_creation_standards(manifests=_manifests(request.app))

    @app.post(
        "/api/creation-drafts",
        response_model=CreationDraftResponse,
        response_model_exclude_unset=True,
    )
    def create_creation_draft(request: Request, body: CreationDraftCreateRequest):
        return _draft_payload(
            service(request).create_creation_draft((body.standard_id, body.version))
        )

    @app.get(
        "/api/creation-drafts/{draft_id}",
        response_model=CreationDraftResponse,
        response_model_exclude_unset=True,
    )
    def get_creation_draft(request: Request, draft_id: str):
        return _draft_payload(service(request).get_creation_draft(draft_id))

    @app.put(
        "/api/creation-drafts/{draft_id}",
        response_model=CreationDraftResponse,
        response_model_exclude_unset=True,
    )
    def save_creation_draft(request: Request, draft_id: str, body: CreationDraftSaveRequest):
        return _draft_payload(
            service(request).update_creation_draft(
                draft_id,
                expected_revision=body.expected_revision,
                step=body.step,
                target_path=body.target_path,
                sheetset_values=body.sheetset_values,
                groups=tuple(_group_input(item) for item in body.groups),
            )
        )

    @app.delete("/api/creation-drafts/{draft_id}")
    def delete_creation_draft(request: Request, draft_id: str):
        service(request).delete_creation_draft(draft_id)
        return {"status": "deleted"}

    @app.get("/api/creation-drafts/{draft_id}/xlsx-template")
    def export_creation_xlsx_template(request: Request, draft_id: str):
        template = service(request).creation_xlsx_template(draft_id)
        return Response(
            content=template.data,
            media_type=XLSX_MEDIA_TYPE,
            headers={
                "Content-Disposition": f'attachment; filename="{template.filename}"'
            },
        )

    @app.post(
        "/api/creation-drafts/{draft_id}/xlsx-import",
        response_model=CreationDraftResponse,
        response_model_exclude_unset=True,
        responses={
            422: {
                "model": CreationImportRejectedResponse,
                "description": "导入被整批拒绝：草稿 JSON 与修订号保持不变",
            }
        },
    )
    async def import_creation_xlsx(
        request: Request,
        draft_id: str,
        file: Annotated[UploadFile, File()],
        expected_revision: int | None = None,
    ):
        outcome = service(request).import_creation_xlsx(
            draft_id, await file.read(), expected_revision=expected_revision
        )
        if outcome.draft is None:
            return JSONResponse(
                status_code=422,
                content=_import_rejected_payload(outcome.diagnostics),
            )
        return _draft_payload(outcome.draft)

    @app.post(
        "/api/creation-drafts/{draft_id}/preview",
        response_model=CreationPreviewResponse,
        response_model_exclude_unset=True,
    )
    def preview_creation_draft(request: Request, draft_id: str):
        return service(request).preview(draft_id)

    @app.post(
        "/api/creation-drafts/{draft_id}/execute",
        response_model=JobResponse,
        response_model_exclude_unset=True,
    )
    def execute_creation_draft(request: Request, draft_id: str, body: CreationExecuteRequest):
        return service(request).execute_creation(draft_id, body.preview_digest)


def _manifests(app: FastAPI) -> Mapping[str, object]:
    """注册表清单按扩展 ID 索引，供标准候选校验受信依赖（与标准发布门禁同口径）。"""
    registry = app.state.extension_runtime.registry
    return {item.manifest.extension_id: item.manifest for item in registry.list()}


def _draft_payload(draft: CreationDraft) -> dict[str, object]:
    """草稿值 → 响应字典（字段与仓储文档一一对应，不含 schema_version）。"""
    return {
        "id": draft.id,
        "standard_id": draft.standard_id,
        "standard_version": draft.standard_version,
        "revision": draft.revision,
        "step": draft.step,
        "target_path": draft.target_path,
        "sheetset_values": dict(draft.sheetset_values),
        "groups": [
            {
                "group_id": group.group_id,
                "created_order": group.created_order,
                "title": group.title,
                "count": group.count,
                "base_asset_id": group.base_asset_id,
                "layout_asset_id": group.layout_asset_id,
                "paper_layout": group.paper_layout,
                "sheet_values": dict(group.sheet_values),
            }
            for group in draft.groups
        ],
    }


def _group_input(item: CreationGroupModel) -> CreationGroupInput:
    """契约模型 → 图纸组输入值；形状由契约保证，语义由应用层与仓储判定。"""
    return CreationGroupInput(
        group_id=item.group_id,
        created_order=item.created_order,
        title=item.title,
        count=item.count,
        base_asset_id=item.base_asset_id,
        layout_asset_id=item.layout_asset_id,
        paper_layout=item.paper_layout,
        sheet_values=dict(item.sheet_values),
    )


def _import_rejected_payload(diagnostics: Sequence[CreationDiagnostic]) -> dict[str, object]:
    """导入拒绝体：统一错误负载（含文案键）+ 可定位诊断。"""
    payload = error_payload(
        "CREATION_IMPORT_INVALID",
        "导入被整批拒绝：" + "；".join(f"{item.code} {item.message}" for item in diagnostics),
        params={"count": len(diagnostics)},
    )
    payload["diagnostics"] = [
        {
            "code": item.code,
            "message": item.message,
            "sheet": item.sheet,
            "row": item.row,
            "column": item.column,
        }
        for item in diagnostics
    ]
    return payload
