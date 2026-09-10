"""统一扩展管理 API（PLAN-DM-020 Task 3 / ARCH-DM-006 §8）。

:func:`register_extension_routes` 只做装配、扩展状态/动作声明校验和请求模型
校验；预览/执行的业务实现分别由 Task 6/9 接入 :class:`ExtensionRuntime`，本
任务在动作已声明且扩展可用时也返回 ``EXTENSION_CAPABILITY_UNAVAILABLE``，
绝不编造预览或执行结果。所有错误都走 :class:`ExtensionErrorResponse` 统一
结构（code/message_key/params/message），``message_key`` 由
:data:`EXTENSION_MESSAGE_KEYS` 按平台码稳定映射。

路由直接注册到宿主 ``FastAPI`` 实例（与既有 api.py 逐条声明的形态一致），
不引入 ``APIRouter.include_router``，保证 ``app.routes`` 仍全部是具体路由对象。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dst_manager.application.extensions.runtime import (
    ExtensionPlatformError,
    ExtensionRuntime,
)
from dst_manager.interfaces.extension_contracts import (
    EXTENSION_MESSAGE_KEYS,
    ArtifactResponseModel,
    ExtensionActionModel,
    ExtensionActionRequest,
    ExtensionErrorResponse,
    ExtensionPreferencePutRequest,
    ExtensionSettingsPutRequest,
    ExtensionStatePatchRequest,
    ExtensionSummaryModel,
    ExtensionUiContributionModel,
    VersionedValueModel,
)

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


def _dispatch_action(request: Request, extension_id: str, action_id: str) -> JSONResponse:
    """统一动作分派：校验扩展可用与动作声明；执行通道 Task 6/9 接入。"""
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
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def preview_extension_action(
        extension_id: str, action_id: str, body: ExtensionActionRequest, request: Request
    ):
        return _dispatch_action(request, extension_id, action_id)

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
