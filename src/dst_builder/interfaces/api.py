"""DST Builder Web API（SPEC-DB-001 §11）：独立 FastAPI 应用工厂。

接口层只负责输入输出、状态码和依赖装配；业务规则在领域层，用例编排在
应用层。服务只监听 127.0.0.1（由 CLI ``dst-builder serve`` 保证）。
"""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from dst_builder.application.projects import (
    BuilderProjectService,
    DraftConflictError,
    DraftPatch,
    ProjectCreation,
    ProjectExistsError,
    ProjectNotInitializedError,
    ProjectServiceError,
    ProjectState,
)
from dst_builder.domain.models import (
    DraftProjectV1,
    NumberingInput,
    ProjectInput,
    SheetInput,
    TemplateInput,
)
from dst_builder.interfaces.responses import (
    REQUEST_INVALID,
    ErrorPayloadModel,
    error_payload,
)
from dst_builder.interfaces.schemas import (
    DraftFieldsModel,
    DraftPatchRequest,
    ProjectCreateRequest,
    ProjectModel,
    ProjectStateResponse,
)

__all__ = ["create_builder_app"]

_STATUS_BY_ERROR = {
    ProjectExistsError: 409,
    ProjectNotInitializedError: 404,
    DraftConflictError: 409,
}


def _builder_version() -> str:
    try:
        return package_version("autocad-sheetset")
    except PackageNotFoundError:  # pragma: no cover - 未安装环境
        return "0.0.0.dev0"


def _service_from_factory(request: Request) -> BuilderProjectService:
    root = request.app.state.project_root
    if root is None:
        raise ProjectNotInitializedError("未绑定项目根目录")
    return BuilderProjectService(root)


def _service_for_create(request: Request, body: ProjectCreateRequest) -> BuilderProjectService:
    """创建项目是唯一写入入口：工厂未绑定根目录时接受请求体中的 project_root。"""
    root = request.app.state.project_root
    if root is None:
        if not body.project_root:
            raise ProjectNotInitializedError("请求必须提供 project_root", field="project_root")
        return BuilderProjectService(body.project_root)
    return BuilderProjectService(root)


def _to_domain_draft(model: DraftFieldsModel) -> DraftProjectV1:
    return DraftProjectV1(
        project=ProjectInput(
            name=model.project.name,
            stage=model.project.stage,
            discipline=model.project.discipline,
            output_path=model.project.output_path,
        ),
        numbering=NumberingInput(
            prefix=model.numbering.prefix,
            start=model.numbering.start,
            width=model.numbering.width,
        ),
        cad_version=model.cad_version,
        sheets=tuple(SheetInput(title=sheet.title) for sheet in model.sheets),
        template=TemplateInput(
            base_asset_id=model.template.base_asset_id,
            layout_asset_id=model.template.layout_asset_id,
            source_layout=model.template.source_layout,
        ),
        schema_version=model.schema_version,
    )


def _state_response(state: ProjectState) -> ProjectStateResponse:
    return ProjectStateResponse(
        project=ProjectModel(
            id=state.project.id,
            name=state.project.name,
            stage=state.project.stage,
            discipline=state.project.discipline,
            output_path=state.project.output_path,
            created_at=state.project.created_at,
            updated_at=state.project.updated_at,
        ),
        draft=DraftFieldsModel.model_validate(json.loads(state.draft.payload_json)),
        wizard_step=state.draft.wizard_step,
        focused_field=state.draft.focused_field,
        updated_at=state.draft.updated_at,
        diagnostics=[
            {
                "code": diagnostic.code,
                "severity": diagnostic.severity.value,
                "message": diagnostic.message,
                "field": diagnostic.field,
            }
            for diagnostic in state.diagnostics
        ],
    )


def _error_response(status: int, payload: ErrorPayloadModel) -> JSONResponse:
    return JSONResponse(status_code=status, content=payload.model_dump())


def create_builder_app(project_root: Path | None = None) -> FastAPI:
    """Builder 独立应用工厂；``project_root`` 为项目根目录（可缺省）。"""
    app = FastAPI(
        title="DST Builder",
        version=_builder_version(),
        description="DST Builder 最小生成闭环 API（SPEC-DB-001 §11）",
    )
    app.state.project_root = project_root

    @app.exception_handler(ProjectServiceError)
    async def _handle_project_service_error(_: Request, exc: ProjectServiceError) -> JSONResponse:
        status = _STATUS_BY_ERROR.get(type(exc), 400)
        return _error_response(
            status,
            error_payload(
                exc.code,
                exc.message,
                recovery_action=exc.recovery_action,
                field=exc.field,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        return _error_response(
            422,
            error_payload(
                REQUEST_INVALID,
                str(first.get("msg", "请求体结构不符合契约")),
                recovery_action="修正请求体后重试",
                field=location or None,
                details={"errors": errors[:5]},
            ),
        )

    @app.post("/api/projects", status_code=201, response_model=ProjectStateResponse)
    def create_project(body: ProjectCreateRequest, request: Request) -> ProjectStateResponse:
        """创建项目库（project.dstb）、初始草稿与 assets/、builds/ 目录。"""
        service = _service_for_create(request, body)
        state = service.create_project(
            ProjectCreation(
                name=body.name,
                stage=body.stage,
                discipline=body.discipline,
                output_path=body.output_path,
            )
        )
        return _state_response(state)

    @app.get("/api/projects/current", response_model=ProjectStateResponse)
    def get_current_project(request: Request) -> ProjectStateResponse:
        """读取项目、当前草稿、引导步骤、聚焦字段与诊断（只读，无副作用）。"""
        service = _service_from_factory(request)
        return _state_response(service.load_current())

    @app.patch("/api/projects/current/draft", response_model=ProjectStateResponse)
    def patch_current_draft(body: DraftPatchRequest, request: Request) -> ProjectStateResponse:
        """带 base_updated_at 乐观并发保存草稿；返回字段级诊断。"""
        service = _service_from_factory(request)
        state = service.save_draft(
            DraftPatch(
                draft=_to_domain_draft(body.draft),
                base_updated_at=body.base_updated_at,
                wizard_step=body.wizard_step,
                focused_field=body.focused_field,
            )
        )
        return _state_response(state)

    return app
