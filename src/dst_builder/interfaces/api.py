"""DST Builder Web API（SPEC-DB-001 §11）：独立 FastAPI 应用工厂。

接口层只负责输入输出、状态码和依赖装配；业务规则在领域层，用例编排在
应用层。服务只监听 127.0.0.1（由 CLI ``dst-builder serve`` 保证）。
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from dst_builder.application.assets import (
    AssetFileTooLargeError,
    AssetHashMismatchError,
    AssetIntake,
    AssetNotFoundError,
    AssetOutsideProjectError,
    AssetServiceError,
    AssetSourceMissingError,
    AssetTypeRejectedError,
    BuilderAssetService,
    CadInspectionUnavailableError,
)
from dst_builder.application.build_recovery import recover_pending_builds
from dst_builder.application.builds import BuildCoordinator, BuildServiceError
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
    AssetRole,
    DraftProjectV1,
    NumberingInput,
    ProjectInput,
    SheetInput,
    TemplateInput,
)
from dst_builder.infrastructure.autocad.capabilities import (
    SUPPORTED_CAD_VERSIONS,
    CadCapabilityStatus,
    CadConfiguration,
    evaluate_cad_capability,
    load_cad_configuration,
)
from dst_builder.infrastructure.autocad.drawing import CoreConsoleDrawingBuilder
from dst_builder.infrastructure.persistence.database import Database
from dst_builder.interfaces.responses import (
    REQUEST_INVALID,
    ErrorPayloadModel,
    error_payload,
)
from dst_builder.interfaces.schemas import (
    AssetInspectionResponse,
    AssetInspectRequest,
    AssetIntakeRequest,
    AssetModel,
    BuildStartRequest,
    BuildStatusResponse,
    CadCapabilitiesResponse,
    CadCapabilityModel,
    DraftFieldsModel,
    DraftPatchRequest,
    HandoffResponse,
    PlanConfirmationResponse,
    PlanSubmitResponse,
    ProjectCreateRequest,
    ProjectModel,
    ProjectStateResponse,
)

__all__ = ["create_builder_app"]

_STATUS_BY_ERROR = {
    ProjectExistsError: 409,
    ProjectNotInitializedError: 404,
    DraftConflictError: 409,
    # 资产纳入（§11）：422 = 请求可修正（类型/大小门禁），404 = 引用不存在，
    # 409 = 源文件在复制过程中变化（重试可恢复），501 = inspection 端口未接线。
    AssetTypeRejectedError: 422,
    AssetFileTooLargeError: 422,
    AssetSourceMissingError: 404,
    AssetNotFoundError: 404,
    AssetHashMismatchError: 409,
    AssetOutsideProjectError: 400,
    CadInspectionUnavailableError: 501,
}


@asynccontextmanager
async def _builder_lifespan(app: FastAPI):
    """应用启动钩子：绑定项目根时执行 §6 启动恢复。"""
    root = app.state.project_root
    if root is not None and (Path(root) / "project.dstb").is_file():
        database = Database(Path(root) / "project.dstb")
        try:
            recover_pending_builds(Path(root), database)
        finally:
            database.engine.dispose()
    yield


def _build_service_from_factory(request: Request) -> BuildCoordinator:
    """构建编排者：按需绑定项目库与 DrawingBuilder（工厂可注入 fake/真实执行器）。"""
    root = request.app.state.project_root
    if root is None:
        raise ProjectNotInitializedError("未绑定项目根目录")
    coordinator: BuildCoordinator | None = getattr(request.app.state, "build_coordinator", None)
    if coordinator is None:
        drawing_builder = request.app.state.drawing_builder
        if drawing_builder is None:
            drawing_builder = CoreConsoleDrawingBuilder(
                root, request.app.state.cad_configuration
            )
        coordinator = BuildCoordinator(root, drawing_builder=drawing_builder)
        request.app.state.build_coordinator = coordinator
    return coordinator


def _build_status_response(view) -> BuildStatusResponse:
    return BuildStatusResponse(
        build_id=view.build_id,
        plan_id=view.plan_id,
        attempt=view.attempt,
        status=view.status,
        progress=view.progress,
        error_code=view.error_code,
        error_detail=view.error_detail,
        published_path=view.published_path,
        created_at=view.created_at,
        finished_at=view.finished_at,
        attempts=[
            {"attempt": item.attempt, "status": item.status, "progress": item.progress, "error_code": item.error_code}
            for item in view.attempts
        ],
    )


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


def _asset_service_from_factory(request: Request) -> BuilderAssetService:
    root = request.app.state.project_root
    if root is None:
        raise ProjectNotInitializedError("未绑定项目根目录")
    return BuilderAssetService(root)


def _cad_tool_paths(
    configuration: CadConfiguration, cad_version: str
) -> tuple[Path | None, Path | None]:
    by_version = {
        "2016": (configuration.console_2016, configuration.plugin_2016),
        "2020": (configuration.console_2020, configuration.plugin_2020),
    }
    return by_version[cad_version]


def _capability_model(status: CadCapabilityStatus) -> CadCapabilityModel:
    return CadCapabilityModel(
        cad_version=status.cad_version,
        available=status.available,
        console_path=status.console_path,
        plugin_path=status.plugin_path,
        unavailable_reason=status.unavailable_reason,
    )


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


def create_builder_app(
    project_root: Path | None = None,
    *,
    cad_configuration: CadConfiguration | None = None,
    layout_inspector: object | None = None,
    drawing_builder: object | None = None,
    manager_base_url: str | None = None,
    handoff_transport: object | None = None,
) -> FastAPI:
    """Builder 独立应用工厂；``project_root`` 为项目根目录（可缺省）。

    ``layout_inspector`` / ``drawing_builder`` 是 §7 CAD 端口（测试注入 fake，
    缺省时构建编排按需构造真实 :class:`CoreConsoleDrawingBuilder`）；
    ``cad_configuration`` 缺省时从显式环境变量加载（不猜测 AutoCAD）。

    ``manager_base_url`` / ``handoff_transport`` 是 §10 交接适配器注入点：
    缺省时分别回退环境变量 ``DST_BUILDER_MANAGER_URL`` / 默认传输与
    ``http://127.0.0.1:8000``（Task 10）。
    """
    app = FastAPI(
        title="DST Builder",
        version=_builder_version(),
        description="DST Builder 最小生成闭环 API（SPEC-DB-001 §11）",
        lifespan=_builder_lifespan,
    )
    app.state.project_root = project_root
    app.state.cad_configuration = (
        cad_configuration if cad_configuration is not None else load_cad_configuration()
    )
    app.state.layout_inspector = layout_inspector
    app.state.drawing_builder = drawing_builder
    app.state.build_coordinator = None
    app.state.manager_base_url = manager_base_url
    app.state.handoff_transport = handoff_transport

    @app.exception_handler(ProjectServiceError)
    @app.exception_handler(AssetServiceError)
    async def _handle_service_error(
        _: Request, exc: ProjectServiceError | AssetServiceError
    ) -> JSONResponse:
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

    @app.exception_handler(BuildServiceError)
    async def _handle_build_error(_: Request, exc: BuildServiceError) -> JSONResponse:
        return _error_response(
            exc.status_code,
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

    @app.post("/api/assets", status_code=201, response_model=AssetModel)
    def create_asset(body: AssetIntakeRequest, request: Request) -> AssetModel:
        """纳入并哈希一个模板资产（§11）：复制 → 校验 → 内容寻址落盘 → 入库。"""
        service = _asset_service_from_factory(request)
        record = service.intake(
            AssetIntake(role=AssetRole(body.role), source_path=Path(body.source_path))
        )
        return AssetModel(
            id=record.id,
            role=record.role.value,
            relative_path=record.relative_path,
            sha256=record.sha256,
            size=record.size,
            source_name=record.source_name,
        )

    @app.post(
        "/api/assets/{asset_id}/inspect",
        response_model=AssetInspectionResponse,
        responses={
            501: {
                "description": "布局 inspection 端口未接线或匹配版本 CAD 不可用"
                "（CAD_VERSION_UNAVAILABLE）",
                "model": ErrorPayloadModel,
            }
        },
    )
    def inspect_asset(
        asset_id: str, body: AssetInspectRequest, request: Request
    ) -> AssetInspectionResponse:
        """用匹配版本 CAD 读取可用布局（§11）；端口未接线时返回 501。

        PLAN-DB-001 Task 4 裁决：本任务只定义 LayoutInspection 端口，
        端口未接线固定 501 + CAD_VERSION_UNAVAILABLE；真实 CAD 布局读取
        由 Task 7 接线，本端点绝不伪造布局列表。
        """
        service = _asset_service_from_factory(request)
        layouts = service.inspect_layouts(
            asset_id, body.cad_version, request.app.state.layout_inspector
        )
        return AssetInspectionResponse(
            asset_id=asset_id, cad_version=body.cad_version, layouts=list(layouts)
        )

    @app.get("/api/cadabilities", response_model=CadCapabilitiesResponse)
    def get_cadabilities(request: Request) -> CadCapabilitiesResponse:
        """只读 capability 响应：两个受支持版本的探测结果（不启动进程）。"""
        configuration: CadConfiguration = request.app.state.cad_configuration
        capabilities = []
        for cad_version in SUPPORTED_CAD_VERSIONS:
            console, plugin = _cad_tool_paths(configuration, cad_version)
            capabilities.append(
                _capability_model(
                    evaluate_cad_capability(cad_version, console=console, plugin=plugin)
                )
            )
        return CadCapabilitiesResponse(capabilities=capabilities)

    # -- 计划与构建（§5/§6/§11，Task 9）------------------------------------

    @app.post("/api/plans", status_code=201, response_model=PlanSubmitResponse)
    def submit_plan(request: Request) -> PlanSubmitResponse:
        """提交修订并产生预览计划（§5）：确定性 ID，不自动确认。"""
        preview = _build_service_from_factory(request).submit_plan()
        return PlanSubmitResponse(
            plan_id=preview.plan_id,
            revision_id=preview.revision_id,
            revision_sha256=preview.revision_sha256,
            plan_sha256=preview.plan_sha256,
            diagnostics=[
                {
                    "code": diagnostic.code,
                    "severity": diagnostic.severity.value,
                    "message": diagnostic.message,
                    "field": diagnostic.field,
                }
                for diagnostic in preview.diagnostics
            ],
            preview=preview.preview,
        )

    @app.post(
        "/api/plans/{plan_id}/confirm",
        response_model=PlanConfirmationResponse,
        responses={
            404: {"model": ErrorPayloadModel, "description": "计划不存在"},
            409: {"model": ErrorPayloadModel, "description": "PLAN_STALE"},
            422: {"model": ErrorPayloadModel, "description": "存在阻断诊断"},
        },
    )
    def confirm_plan(plan_id: str, request: Request) -> PlanConfirmationResponse:
        """用户显式确认计划（绝不自动确认）；确认后构建输入冻结。"""
        confirmation = _build_service_from_factory(request).confirm_plan(plan_id)
        return PlanConfirmationResponse(
            plan_id=confirmation.plan_id,
            revision_id=confirmation.revision_id,
            confirmed_at=confirmation.confirmed_at,
        )

    @app.post(
        "/api/builds",
        status_code=202,
        response_model=BuildStatusResponse,
        responses={
            404: {"model": ErrorPayloadModel, "description": "计划不存在"},
            409: {
                "model": ErrorPayloadModel,
                "description": "PLAN_STALE / PACKAGE_TARGET_EXISTS / BUILD_ALREADY_RUNNING",
            },
            422: {"model": ErrorPayloadModel, "description": "PLAN_NOT_CONFIRMED"},
        },
    )
    def start_build(body: BuildStartRequest, request: Request) -> BuildStatusResponse:
        """基于已确认计划创建 build/attempt 并在线程执行器中启动构建。"""
        view = _build_service_from_factory(request).start_build(body.plan_id)
        return _build_status_response(view)

    @app.post(
        "/api/builds/{build_id}/cancel",
        status_code=202,
        response_model=BuildStatusResponse,
        responses={
            404: {"model": ErrorPayloadModel, "description": "构建不存在"},
            409: {
                "model": ErrorPayloadModel,
                "description": "PUBLISHING 或终止状态不响应取消（CANCEL_NOT_ACCEPTED）",
            },
        },
    )
    def cancel_build(build_id: str, request: Request) -> BuildStatusResponse:
        """请求安全取消（§6）：检查点处迁移 CANCELLED；PUBLISHING 拒绝。"""
        view = _build_service_from_factory(request).cancel_build(build_id)
        return _build_status_response(view)

    @app.get(
        "/api/builds/{build_id}",
        response_model=BuildStatusResponse,
        responses={404: {"model": ErrorPayloadModel, "description": "构建不存在"}},
    )
    def get_build(build_id: str, request: Request) -> BuildStatusResponse:
        """读取状态、诊断和成果（§11）。"""
        view = _build_service_from_factory(request).get_build(build_id)
        return _build_status_response(view)

    @app.post(
        "/api/builds/{build_id}/handoff",
        response_model=HandoffResponse,
        responses={
            404: {"model": ErrorPayloadModel, "description": "构建不存在"},
            409: {
                "model": ErrorPayloadModel,
                "description": "构建未成功发布（HANDOFF_INVALID）或包冲突（HANDOFF_ID_CONFLICT）",
            },
            422: {"model": ErrorPayloadModel, "description": "Manager 验证拒绝（HANDOFF_INVALID）"},
            502: {"model": ErrorPayloadModel, "description": "本机 Manager 不可用（HANDOFF_UNAVAILABLE）"},
        },
    )
    def handoff_build(build_id: str, request: Request) -> HandoffResponse:
        """调用本机 Manager 交接适配器（§10/§11）：已发布成果包原样保留。"""
        coordinator = _build_service_from_factory(request)
        result = coordinator.handoff_to_manager(
            build_id,
            manager_base_url=request.app.state.manager_base_url,
            transport=request.app.state.handoff_transport,
        )
        return HandoffResponse(**result)

    @app.get(
        "/api/builds/{build_id}/events",
        responses={
            404: {"model": ErrorPayloadModel, "description": "构建不存在"},
            200: {"description": "SSE 事件流（id: attempt:sequence）"},
        },
    )
    def stream_build_events(build_id: str, request: Request) -> StreamingResponse:
        """SSE 事件流与重放（§6）：Last-Event-ID 之后的事件按序重放。"""
        service = _build_service_from_factory(request)
        service.ensure_build_exists(build_id)
        last_event_id = request.headers.get("last-event-id")
        return StreamingResponse(
            service.stream_events(build_id, last_event_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return app
