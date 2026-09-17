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
    CadCapabilitiesResponse,
    CadCapabilityModel,
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
) -> FastAPI:
    """Builder 独立应用工厂；``project_root`` 为项目根目录（可缺省）。

    ``layout_inspector`` 是 §11 布局 inspection 端口（Task 7 注入真实执行器）；
    ``cad_configuration`` 缺省时从显式环境变量加载（不猜测 AutoCAD）。
    """
    app = FastAPI(
        title="DST Builder",
        version=_builder_version(),
        description="DST Builder 最小生成闭环 API（SPEC-DB-001 §11）",
    )
    app.state.project_root = project_root
    app.state.cad_configuration = (
        cad_configuration if cad_configuration is not None else load_cad_configuration()
    )
    app.state.layout_inspector = layout_inspector

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

    @app.post("/api/assets/{asset_id}/inspect", response_model=AssetInspectionResponse)
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

    return app
