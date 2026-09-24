"""标准管理路由（PLAN-DM-035 Task 6）。

:func:`register_standard_routes` 把 ``/api/standards`` 系列端点直接注册到宿主
``FastAPI``（与 extension_api 同形态，不引入 ``APIRouter``）。路由只做请求/
响应转换与错误码映射：标准 Schema 校验、发布门禁、包安全与导入导出全部在
应用层/基础设施层完成。受信扩展依赖在发布时按当前注册表清单校验。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from dst_manager.infrastructure.standards.store import StandardStoreError
from dst_manager.interfaces.message_catalog import error_payload
from dst_manager.interfaces.standard_contracts import (
    AssetInspectionResponse,
    ImportedStandardDraftResponse,
    StandardAssetCopyRequest,
    StandardAssetCopyResponse,
    StandardAssetInspectRequest,
    StandardDetailResponse,
    StandardDiagnosticModel,
    StandardDraftRequest,
    StandardDraftResponse,
    StandardDstImportRequest,
    StandardPathRequest,
    StandardPublishResponse,
    StandardSummaryModel,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dst_manager.domain.models import ValidationIssue


def register_standard_routes(app: FastAPI) -> None:
    """把标准路由注册到宿主应用；草稿路由先于身份路由注册避免吞段。"""

    @app.exception_handler(StandardStoreError)
    async def standard_store_error(_: Request, exc: StandardStoreError):
        # 标准库错误消息以稳定码为前缀；未登记码按 422 处理
        code = str(exc).split(":", 1)[0]
        status = {"STANDARD_VERSION_EXISTS": 409, "STANDARD_DRAFT_EXISTS": 409}.get(
            code, 404 if code.endswith("_NOT_FOUND") else 422
        )
        return JSONResponse(status_code=status, content=error_payload(code, str(exc)))

    def service(request: Request):
        return request.app.state.service

    @app.get(
        "/api/standards",
        response_model=list[StandardSummaryModel],
        response_model_exclude_unset=True,
    )
    def list_standards(request: Request):
        return service(request).list_standards()

    # ---- 草稿（先注册，防止被身份路由吞掉 "drafts" 段） ------------------

    @app.post(
        "/api/standards/drafts",
        response_model=StandardDraftResponse,
        response_model_exclude_unset=True,
    )
    def create_standard_draft(request: Request, body: StandardDraftRequest):
        return service(request).create_standard_draft(body.document, body.draft_id)

    @app.post(
        "/api/standards/drafts/from-dst",
        response_model=ImportedStandardDraftResponse,
        response_model_exclude_unset=True,
    )
    def create_draft_from_dst(request: Request, body: StandardDstImportRequest):
        return service(request).create_draft_from_dst(Path(body.dst_path))

    @app.get(
        "/api/standards/drafts/{draft_id}",
        response_model=StandardDraftResponse,
        response_model_exclude_unset=True,
    )
    def get_standard_draft(request: Request, draft_id: str):
        return service(request).get_standard_draft(draft_id)

    @app.delete("/api/standards/drafts/{draft_id}")
    def delete_standard_draft(request: Request, draft_id: str):
        service(request).delete_standard_draft(draft_id)
        return {"status": "deleted"}

    @app.post(
        "/api/standards/drafts/{draft_id}/publish",
        response_model=StandardPublishResponse,
        response_model_exclude_unset=True,
    )
    def publish_standard(request: Request, draft_id: str):
        return service(request).publish_standard(
            draft_id, manifests=_manifests(request.app)
        )

    @app.post(
        "/api/standards/drafts/{draft_id}/assets/{asset_id}/inspect",
        response_model=AssetInspectionResponse,
        response_model_exclude_unset=True,
    )
    def inspect_standard_asset(
        request: Request, draft_id: str, asset_id: str, body: StandardAssetInspectRequest
    ):
        inspection = service(request).inspect_standard_asset(
            draft_id, asset_id, body.cad_version
        )
        return {
            "asset_id": inspection.asset_id,
            "kind": inspection.kind,
            "layouts": list(inspection.layouts),
            "diagnostics": [_diagnostic(issue) for issue in inspection.diagnostics],
        }

    @app.post(
        "/api/standards/drafts/{draft_id}/asset-files",
        response_model=StandardAssetCopyResponse,
        response_model_exclude_unset=True,
    )
    def copy_standard_draft_asset_file(
        request: Request, draft_id: str, body: StandardAssetCopyRequest
    ):
        return service(request).copy_draft_asset_file(draft_id, Path(body.source_path))

    # ---- 导入导出 --------------------------------------------------------

    @app.post(
        "/api/standards/import",
        response_model=StandardPublishResponse,
        response_model_exclude_unset=True,
    )
    def import_standard(request: Request, body: StandardPathRequest):
        return service(request).import_standard_package(Path(body.path))

    @app.get("/api/standards/{standard_id}/{version}/export")
    def export_standard(request: Request, standard_id: str, version: str):
        package = service(request).export_standard_package(
            standard_id,
            version,
            service(request).settings.data_dir / "tmp" / "standard-exports",
        )
        return FileResponse(package, media_type="application/zip", filename=package.name)

    # ---- 身份路由 --------------------------------------------------------

    @app.get(
        "/api/standards/{standard_id}/{version}",
        response_model=StandardDetailResponse,
        response_model_exclude_unset=True,
    )
    def get_standard(request: Request, standard_id: str, version: str):
        return service(request).get_standard(standard_id, version)

    @app.put(
        "/api/standards/{standard_id}/{version}",
        response_model=StandardDraftResponse,
        response_model_exclude_unset=True,
    )
    def put_standard(
        request: Request, standard_id: str, version: str, body: dict[str, object]
    ):
        # 请求体即标准文档本身；已发布身份在应用层最先以 409 拒绝。
        return service(request).save_standard_by_identity(standard_id, version, body)


def _manifests(app: FastAPI) -> Mapping[str, object]:
    """注册表清单按扩展 ID 索引，供发布门禁校验受信依赖。"""
    registry = app.state.extension_runtime.registry
    return {item.manifest.extension_id: item.manifest for item in registry.list()}


def _diagnostic(issue: ValidationIssue) -> StandardDiagnosticModel:
    return StandardDiagnosticModel(
        code=issue.code,
        severity=str(issue.severity.value),
        message=issue.message,
    )
