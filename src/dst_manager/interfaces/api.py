import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from dst_manager.application.service import ApplicationError, DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.acsm_xml.document import AcsmValidationError
from dst_manager.interfaces.contracts import (
    ChangeExecuteRequest,
    ChangePreviewRequest,
    ContractModel,
    DraftDeleteRequest,
    DraftPutRequest,
    LayoutNamesRequest,
    PropertyCsvExecuteRequest,
    PropertyCsvPreviewRequest,
    RepairExecuteRequest,
    RepairPreviewRequest,
    RestoreRevisionExecuteRequest,
    XmlExecuteRequest,
    XmlPreviewRequest,
)
from dst_manager.interfaces.responses import (
    CadCapabilitiesResponse,
    ChangePreviewResponse,
    DraftDeleteResponse,
    DraftEnvelopeResponse,
    HealthResponse,
    JobResponse,
    LayoutNamesResponse,
    RepairPreviewResponse,
    RestorePreviewResponse,
    RevisionResponse,
    WorkspaceResponse,
    XmlPreviewResponse,
)
from dst_manager.interfaces.serialization import workspace_json


class OpenRequest(ContractModel):
    dst_path: Path
    root_override: Path | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="DST Manager", version="0.3.0")
    service = DstManagerService(settings)
    app.state.service = service

    @app.exception_handler(ApplicationError)
    async def application_error(_, exc: ApplicationError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": str(exc)})

    @app.exception_handler(AcsmValidationError)
    async def acsm_validation_error(_, exc: AcsmValidationError):
        from fastapi.responses import JSONResponse
        code, _, detail = str(exc).partition(":")
        return JSONResponse(status_code=422, content={"code": code, "message": detail.strip() or "AcSm 结构校验失败"})

    @app.get("/api/health", response_model=HealthResponse, response_model_exclude_unset=True)
    def health():
        return {"status": "ok", "run_id": os.environ.get("DST_MANAGER_RUN_ID")}

    @app.get("/api/custom-properties/template")
    def custom_property_template():
        return Response(
            content=b"type,name,default_value\r\n",
            media_type="text/csv; charset=utf-8",
        )

    @app.post("/api/workspaces/open", response_model=WorkspaceResponse, response_model_exclude_unset=True)
    def open_workspace(request: OpenRequest):
        return workspace_json(service.open_workspace(request.dst_path, request.root_override))

    @app.get(
        "/api/workspaces/{workspace_id}",
        response_model=WorkspaceResponse,
        response_model_exclude_unset=True,
    )
    def get_workspace(workspace_id: str):
        return workspace_json(service.get_workspace(workspace_id))

    @app.get(
        "/api/workspaces/{workspace_id}/draft",
        response_model=DraftEnvelopeResponse,
        response_model_exclude_unset=True,
    )
    def get_draft(workspace_id: str):
        return service.get_draft(workspace_id)

    @app.put(
        "/api/workspaces/{workspace_id}/draft",
        response_model=DraftEnvelopeResponse,
        response_model_exclude_unset=True,
    )
    def put_draft(workspace_id: str, request: DraftPutRequest):
        payload = request.model_dump(
            mode="json",
            exclude={"expected_version"},
            exclude_none=True,
        )
        return service.save_draft(workspace_id, payload, request.expected_version)

    @app.delete(
        "/api/workspaces/{workspace_id}/draft",
        response_model=DraftDeleteResponse,
        response_model_exclude_unset=True,
    )
    def delete_draft(workspace_id: str, request: DraftDeleteRequest):
        return service.delete_draft(workspace_id, request.expected_version)

    @app.post(
        "/api/workspaces/{workspace_id}/custom-properties/import/preview",
        response_model=ChangePreviewResponse,
        response_model_exclude_unset=True,
    )
    def preview_custom_property_import(workspace_id: str, request: PropertyCsvPreviewRequest):
        return service.preview_custom_property_import(
            workspace_id,
            request.base_revision_id,
            request.csv.encode("utf-8", errors="surrogatepass"),
        )

    @app.post(
        "/api/workspaces/{workspace_id}/custom-properties/import",
        response_model=JobResponse,
        response_model_exclude_unset=True,
    )
    def import_custom_properties(workspace_id: str, request: PropertyCsvExecuteRequest):
        return service.import_custom_properties(
            workspace_id,
            request.base_revision_id,
            request.csv.encode("utf-8", errors="surrogatepass"),
            request.preview_digest,
        )

    @app.get("/api/workspaces/{workspace_id}/custom-properties/export")
    def export_custom_properties(workspace_id: str):
        return Response(
            content=service.export_custom_properties_csv(workspace_id),
            media_type="text/csv; charset=utf-8",
        )

    @app.post(
        "/api/workspaces/{workspace_id}/changes/preview",
        response_model=ChangePreviewResponse,
        response_model_exclude_unset=True,
    )
    def preview(workspace_id: str, request: ChangePreviewRequest):
        return service.preview_changes(
            workspace_id,
            request.base_revision_id,
            request.command_payloads(),
            request.cad_version,
        )

    @app.post(
        "/api/workspaces/{workspace_id}/changes/execute",
        response_model=JobResponse,
        response_model_exclude_unset=True,
    )
    def execute(workspace_id: str, request: ChangeExecuteRequest):
        return service.execute_changes(
            workspace_id,
            request.base_revision_id,
            request.command_payloads(),
            request.cad_version,
            request.preview_digest,
        )

    @app.post(
        "/api/workspaces/{workspace_id}/xml/import/preview",
        response_model=XmlPreviewResponse,
        response_model_exclude_unset=True,
    )
    def preview_xml(workspace_id: str, request: XmlPreviewRequest):
        return service.preview_xml(
            workspace_id,
            request.base_revision_id,
            request.xml.encode("utf-8"),
            request.destination,
        )

    @app.post(
        "/api/workspaces/{workspace_id}/xml/export-dst",
        response_model=JobResponse,
        response_model_exclude_unset=True,
    )
    def export_dst(workspace_id: str, request: XmlExecuteRequest):
        return service.export_xml_to_dst(
            workspace_id,
            request.base_revision_id,
            request.xml.encode("utf-8"),
            request.destination,
            request.destination_revision_id,
            request.preview_digest,
        )

    @app.get("/api/jobs/{job_id}", response_model=JobResponse, response_model_exclude_unset=True)
    def job(job_id: str):
        return service.get_job_details(job_id)

    @app.post("/api/jobs/{job_id}/retry", response_model=JobResponse, response_model_exclude_unset=True)
    def retry_job(job_id: str):
        return service.retry_job(job_id)

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        async def events():
            previous = None
            while True:
                try:
                    result = service.get_job_details(job_id)
                except ApplicationError:
                    yield "event: error\ndata: {\"code\":\"JOB_NOT_FOUND\"}\n\n"
                    return
                current = json.dumps(result, ensure_ascii=False)
                if current != previous:
                    yield f"data: {current}\n\n"
                    previous = current
                if result["status"] in {"SUCCEEDED", "FAILED", "ROLLED_BACK", "BLOCKED_FILE_LOCK"}:
                    return
                await asyncio.sleep(0.5)
        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/revisions", response_model=list[RevisionResponse], response_model_exclude_unset=True)
    def revisions(workspace_id: str | None = None):
        return service.database.list_revisions(workspace_id)

    @app.get(
        "/api/workspaces/{workspace_id}/revisions/{revision_id}/restore-preview",
        response_model=RestorePreviewResponse,
        response_model_exclude_unset=True,
    )
    def restore_preview(workspace_id: str, revision_id: str):
        return service.preview_revision_restore(workspace_id, revision_id)

    @app.post(
        "/api/workspaces/{workspace_id}/revisions/{revision_id}/restore",
        response_model=JobResponse,
        response_model_exclude_unset=True,
    )
    def restore_revision(workspace_id: str, revision_id: str, request: RestoreRevisionExecuteRequest):
        return service.restore_revision(
            workspace_id,
            revision_id,
            request.base_revision_id,
            request.preview_digest,
        )

    @app.post(
        "/api/workspaces/{workspace_id}/repairs/preview",
        response_model=RepairPreviewResponse,
        response_model_exclude_unset=True,
    )
    def repair_preview(workspace_id: str, request: RepairPreviewRequest):
        return service.preview_repair(workspace_id, request.base_revision_id)

    @app.post(
        "/api/workspaces/{workspace_id}/repairs/execute",
        response_model=JobResponse,
        response_model_exclude_unset=True,
    )
    def repair_execute(workspace_id: str, request: RepairExecuteRequest):
        return service.execute_repair(workspace_id, request.base_revision_id, request.preview_digest)

    @app.get(
        "/api/system/cad-capabilities",
        response_model=CadCapabilitiesResponse,
        response_model_exclude_unset=True,
    )
    def capabilities():
        return service.capabilities()

    @app.post(
        "/api/layout-names",
        response_model=LayoutNamesResponse,
        response_model_exclude_unset=True,
    )
    def read_layout_names(request: LayoutNamesRequest):
        return service.get_layout_names(request.file_path, request.cad_version)

    web_dist = Path(__file__).parents[3] / "web" / "dist"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


app = create_app()
