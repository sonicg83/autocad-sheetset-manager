"""统一扩展管理 API（PLAN-DM-020 Task 3/6 / ARCH-DM-006 §8）。

:func:`register_extension_routes` 只做装配、扩展状态/动作声明校验和请求模型
校验；预览通道（Task 6）分派给扩展的真实预览实现，执行通道仍属 Task 9，
在动作已声明且扩展可用时返回 ``EXTENSION_CAPABILITY_UNAVAILABLE``，绝不编造
执行结果。预览请求模板快照经 :class:`ExtensionPreviewRequest` 契约校验，成功
响应为 :class:`SheetCatalogPreviewResponse`；工作区偏好按 ARCH-DM-006 §8.2
best-effort 更新——保存失败降级为响应内的非阻断 warning，不升级为动作失败。
所有错误都走 :class:`ExtensionErrorResponse` 统一结构
（code/message_key/params/message），``message_key`` 由 :data:`EXTENSION_MESSAGE_KEYS`
按平台码稳定映射。

路由直接注册到宿主 ``FastAPI`` 实例（与既有 api.py 逐条声明的形态一致），
不引入 ``APIRouter.include_router``，保证 ``app.routes`` 仍全部是具体路由对象。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dst_manager.application.extensions.runtime import (
    ExtensionPlatformError,
    ExtensionRuntime,
    capability_platform_error,
)
from dst_manager.extensions.builtin.sheet_catalog.preview import (
    SheetCatalogDiagnostic,
    SheetCatalogPreview,
    SheetCatalogPreviewRequest,
    preference_save_failed_warning,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import (
    TEMPLATE_SCHEMA_VERSION,
    SheetCatalogTemplate,
    TemplateColumn,
)
from dst_manager.extensions.capabilities import CapabilityError
from dst_manager.interfaces.extension_contracts import (
    EXTENSION_MESSAGE_KEYS,
    ArtifactResponseModel,
    ExtensionActionModel,
    ExtensionActionRequest,
    ExtensionErrorResponse,
    ExtensionPreferencePutRequest,
    ExtensionPreviewRequest,
    ExtensionSettingsPutRequest,
    ExtensionStatePatchRequest,
    ExtensionSummaryModel,
    ExtensionUiContributionModel,
    SheetCatalogColumnModel,
    SheetCatalogDiagnosticModel,
    SheetCatalogFieldCatalogModel,
    SheetCatalogFieldDefinitionModel,
    SheetCatalogPreviewResponse,
    SheetCatalogTemplateModel,
    VersionedValueModel,
)

logger = logging.getLogger(__name__)

#: 扩展端点的错误响应契约（404/409/422/503 统一负载）。
_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": ExtensionErrorResponse} for status in (404, 409, 422, 503)
}


def _runtime(request: Request) -> ExtensionRuntime:
    runtime = getattr(request.app.state, "extension_runtime", None)
    if runtime is None:  # pragma: no cover - create_app 恒装配，防御装配遗漏
        raise RuntimeError("扩展运行时未装配")
    return runtime


def _error_response(exc: ExtensionPlatformError) -> JSONResponse:
    payload = {
        "code": exc.code,
        "message_key": exc.key_override or EXTENSION_MESSAGE_KEYS[exc.code],
        "params": dict(exc.params),
        "message": str(exc),
    }
    # 出口自检：任何平台错误都必须满足统一错误契约（四字段齐全）。
    ExtensionErrorResponse.model_validate(payload)
    return JSONResponse(status_code=exc.status_code, content=payload)


def _versioned(versioned) -> VersionedValueModel:
    return VersionedValueModel(
        schema_version=versioned.schema_version,
        revision=versioned.revision,
        value=dict(versioned.value),
    )


def _summary(view) -> ExtensionSummaryModel:
    manifest = view.manifest
    return ExtensionSummaryModel(
        extension_id=view.extension_id,
        version=view.version,
        name_key=manifest.name_key,
        description_key=manifest.description_key,
        status=view.status,  # type: ignore[arg-type]
        enabled=view.enabled,
        error_code=view.error_code,
        actions=[
            ExtensionActionModel(
                action_id=action.action_id,
                output_kind=action.output_kind,
                media_type=action.media_type,
            )
            for action in manifest.actions
        ],
        ui_contributions=[
            ExtensionUiContributionModel(
                contribution_id=contribution.contribution_id,
                kind=contribution.kind,
                route_key=contribution.route_key,
            )
            for contribution in manifest.ui_contributions
        ],
    )


def _dispatch_preview(
    request: Request, extension_id: str, action_id: str, body: ExtensionPreviewRequest
):
    """预览分派：可用性/声明校验 → 能力上下文 → 扩展真实预览 → 偏好 best-effort。"""
    runtime = _runtime(request)
    sheet_request = _preview_request(body)
    try:
        with runtime.invoke_action(extension_id, action_id) as invocation:
            extension = invocation.extension
            if not hasattr(extension, "preview"):
                raise ExtensionPlatformError(
                    "EXTENSION_CAPABILITY_UNAVAILABLE",
                    f"宿主尚未接入该扩展的预览通道：{extension_id}/{action_id}",
                    status_code=503,
                    params={"extension_id": extension_id, "action_id": action_id},
                )
            with runtime.extension_context(
                extension_id, body.workspace_id, body.base_revision_id
            ) as context:
                result = extension.preview(context, sheet_request)
    except (ExtensionPlatformError, CapabilityError) as exc:
        return _error_response(
            capability_platform_error(exc) if isinstance(exc, CapabilityError) else exc
        )
    warnings = list(result.warnings)
    preference_warning = _save_last_template_preference(
        runtime, extension_id, body.workspace_id, result.normalized_template
    )
    if preference_warning is not None:
        warnings.append(preference_warning)
    return _preview_response(result, warnings)


def _preview_request(body: ExtensionPreviewRequest) -> SheetCatalogPreviewRequest:
    """契约模型 → 预览请求值对象（模板快照原样传递，规范化属预览阶段）。"""
    return SheetCatalogPreviewRequest(
        workspace_id=body.workspace_id,
        base_revision_id=body.base_revision_id,
        template=SheetCatalogTemplate(
            template_id=body.template.template_id,
            name=body.template.name,
            schema_version=TEMPLATE_SCHEMA_VERSION,
            columns=tuple(
                TemplateColumn(
                    column_id=column.column_id,
                    header=column.header,
                    expression=column.expression,
                )
                for column in body.template.columns
            ),
        ),
    )


def _save_last_template_preference(runtime, extension_id: str, workspace_id: str, template):
    """best-effort 更新"上次选中的已保存模板"偏好（ARCH-DM-006 §8.2）。

    未保存草稿不进入工作区偏好；保存失败只记录稳定诊断日志（仅含标识，
    不含属性值）并降级为响应内的非阻断 warning，绝不升级为动作失败。
    """
    if template.template_id is None:
        return None
    template_id = str(template.template_id)
    try:
        runtime.put_preference(
            extension_id,
            workspace_id,
            runtime.settings_schema(extension_id),
            {"template_id": template_id},
        )
    except Exception:  # noqa: BLE001 - best-effort 降级：任何偏好失败都不得升级为动作失败
        logger.warning(
            "EXTENSION_PREFERENCE_SAVE_FAILED extension_id=%s workspace_id=%s template_id=%s",
            extension_id,
            workspace_id,
            template_id,
        )
        return preference_save_failed_warning(template_id)
    return None


def _diagnostic_model(diagnostic: SheetCatalogDiagnostic) -> SheetCatalogDiagnosticModel:
    return SheetCatalogDiagnosticModel(
        code=diagnostic.code,
        message_key=diagnostic.message_key,
        params=dict(diagnostic.params),
        column_id=str(diagnostic.column_id) if diagnostic.column_id is not None else None,
        source_position=diagnostic.source_position,
    )


def _template_model(template: SheetCatalogTemplate) -> SheetCatalogTemplateModel:
    return SheetCatalogTemplateModel(
        template_id=str(template.template_id) if template.template_id is not None else None,
        name=template.name,
        schema_version=template.schema_version,
        columns=[
            SheetCatalogColumnModel(
                column_id=str(column.column_id) if column.column_id is not None else None,
                header=column.header,
                expression=column.expression,
            )
            for column in template.columns
        ],
    )


def _field_catalog_model(field_catalog) -> SheetCatalogFieldCatalogModel:
    return SheetCatalogFieldCatalogModel(
        sheetset=[
            SheetCatalogFieldDefinitionModel(
                scope=field.scope, canonical_name=field.canonical_name, builtin=field.builtin
            )
            for field in field_catalog.sheetset
        ],
        sheet=[
            SheetCatalogFieldDefinitionModel(
                scope=field.scope, canonical_name=field.canonical_name, builtin=field.builtin
            )
            for field in field_catalog.sheet
        ],
    )


def _preview_response(
    result: SheetCatalogPreview, warnings: list[SheetCatalogDiagnostic]
) -> SheetCatalogPreviewResponse:
    return SheetCatalogPreviewResponse(
        normalized_template=_template_model(result.normalized_template),
        field_catalog=_field_catalog_model(result.field_catalog),
        errors=[_diagnostic_model(diagnostic) for diagnostic in result.errors],
        warnings=[_diagnostic_model(diagnostic) for diagnostic in warnings],
        rows=[list(row) for row in result.rows],
        total_rows=result.total_rows,
        preview_digest=result.preview_digest,
        executable=result.executable,
    )


def _dispatch_action(request: Request, extension_id: str, action_id: str) -> JSONResponse:
    """执行分派：校验扩展可用与动作声明；执行通道属 Task 9，不编造结果。"""
    runtime = _runtime(request)
    try:
        with runtime.invoke_action(extension_id, action_id):
            raise ExtensionPlatformError(
                "EXTENSION_CAPABILITY_UNAVAILABLE",
                f"宿主动作执行通道尚未接入：{extension_id}/{action_id}",
                status_code=503,
                params={"extension_id": extension_id, "action_id": action_id},
            )
    except ExtensionPlatformError as exc:
        return _error_response(exc)


def register_extension_routes(app: FastAPI) -> None:
    """把统一扩展管理端点注册到宿主应用（PLAN-DM-020 Task 3）。"""

    @app.get(
        "/api/extensions",
        response_model=list[ExtensionSummaryModel],
        response_model_exclude_unset=True,
        tags=["extensions"],
    )
    def list_extensions(request: Request):
        runtime = _runtime(request)
        return [_summary(view) for view in runtime.list_extensions()]

    @app.patch(
        "/api/extensions/{extension_id}/state",
        response_model=ExtensionSummaryModel,
        response_model_exclude_unset=True,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def patch_extension_state(
        extension_id: str, body: ExtensionStatePatchRequest, request: Request
    ):
        runtime = _runtime(request)
        try:
            return _summary(runtime.set_enabled(extension_id, body.enabled))
        except ExtensionPlatformError as exc:
            return _error_response(exc)

    @app.get(
        "/api/extensions/{extension_id}/settings",
        response_model=VersionedValueModel,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def get_extension_settings(extension_id: str, request: Request):
        runtime = _runtime(request)
        try:
            return _versioned(runtime.get_settings(extension_id))
        except ExtensionPlatformError as exc:
            return _error_response(exc)

    @app.put(
        "/api/extensions/{extension_id}/settings",
        response_model=VersionedValueModel,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def put_extension_settings(
        extension_id: str, body: ExtensionSettingsPutRequest, request: Request
    ):
        runtime = _runtime(request)
        try:
            return _versioned(
                runtime.put_settings(
                    extension_id, body.schema_version, body.value, body.expected_revision
                )
            )
        except ExtensionPlatformError as exc:
            return _error_response(exc)

    @app.get(
        "/api/extensions/{extension_id}/workspaces/{workspace_id}/preferences",
        response_model=VersionedValueModel,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def get_extension_preference(extension_id: str, workspace_id: str, request: Request):
        runtime = _runtime(request)
        try:
            return _versioned(runtime.get_preference(extension_id, workspace_id))
        except ExtensionPlatformError as exc:
            return _error_response(exc)

    @app.put(
        "/api/extensions/{extension_id}/workspaces/{workspace_id}/preferences",
        response_model=VersionedValueModel,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def put_extension_preference(
        extension_id: str,
        workspace_id: str,
        body: ExtensionPreferencePutRequest,
        request: Request,
    ):
        runtime = _runtime(request)
        try:
            return _versioned(
                runtime.put_preference(
                    extension_id, workspace_id, body.schema_version, body.value
                )
            )
        except ExtensionPlatformError as exc:
            return _error_response(exc)

    @app.post(
        "/api/extensions/{extension_id}/actions/{action_id}/preview",
        response_model=SheetCatalogPreviewResponse,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def preview_extension_action(
        extension_id: str, action_id: str, body: ExtensionPreviewRequest, request: Request
    ):
        return _dispatch_preview(request, extension_id, action_id, body)

    @app.post(
        "/api/extensions/{extension_id}/actions/{action_id}/execute",
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def execute_extension_action(
        extension_id: str, action_id: str, body: ExtensionActionRequest, request: Request
    ):
        return _dispatch_action(request, extension_id, action_id)

    @app.get(
        "/api/artifacts/{artifact_id}",
        response_model=ArtifactResponseModel,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def get_artifact(artifact_id: str, request: Request):
        runtime = _runtime(request)
        try:
            record = runtime.get_artifact(artifact_id)
            return ArtifactResponseModel(
                artifact_id=record.artifact_id,
                extension_id=record.extension_id,
                extension_version=record.extension_version,
                workspace_id=record.workspace_id,
                source_revision_id=record.source_revision_id,
                kind=record.kind,
                media_type=record.media_type,
                management_relation=record.management_relation,
                output_path=record.output_path,
                file_name=record.file_name,
                size_bytes=record.size_bytes,
                sha256=record.sha256,
                created_at=record.created_at,
            )
        except ExtensionPlatformError as exc:
            return _error_response(exc)
