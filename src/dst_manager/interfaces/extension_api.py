"""统一扩展管理 API（PLAN-DM-020 Task 3/6 / ARCH-DM-006 §8）。

:func:`register_extension_routes` 只做装配、扩展状态/动作声明校验和请求模型
校验；预览通道（Task 6）与执行通道（Task 9）都分派给扩展的真实实现——执行
由 :class:`ExtensionRuntime.execute_action` 编排摘要复核、候选生成、授权消费、
原子保存与 Artifact 登记。预览请求模板快照经 :class:`ExtensionPreviewRequest`
契约校验，成功响应为 :class:`SheetCatalogPreviewResponse`；执行请求经
:class:`ExtensionExecuteRequest` 契约校验，成功响应为
:class:`SheetCatalogExecuteResponseModel`（不含 sha256/来源修订/扩展版本，
后台字段只经 Artifact 查询披露，查询响应含 ``AVAILABLE/MISSING/CHANGED``
可用性派生）；工作区偏好按 ARCH-DM-006 §8.2 best-effort 更新——保存失败
降级为响应内的非阻断 warning，不升级为动作失败。扩展设置的 GET/PUT 统一返回
:class:`ExtensionSettingsResponseModel`（持久值 + 有效值 + 只读诊断 +
``generated`` 字段项）；字段项在接口层把 Provider 的控件类型/默认值/约束与
清单的 label/description/order 合并，按 ``order, key`` 排序（§8.2）。
所有错误都走
:class:`ExtensionErrorResponse` 统一结构
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
from dst_manager.application.extensions.settings import ExtensionSettingsView
from dst_manager.extensions.builtin.sheet_catalog.extension import (
    SheetCatalogExecuteRequest,
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
from dst_manager.extensions.contracts import ExtensionManifest
from dst_manager.extensions.settings import SettingsContribution, SettingsFieldSpec
from dst_manager.interfaces.extension_contracts import (
    EXTENSION_MESSAGE_KEYS,
    ArtifactResponseModel,
    ExtensionActionModel,
    ExtensionErrorResponse,
    ExtensionExecuteRequest,
    ExtensionPreferencePutRequest,
    ExtensionPreviewRequest,
    ExtensionSettingsContributionModel,
    ExtensionSettingsItemModel,
    ExtensionSettingsPutRequest,
    ExtensionSettingsResponseModel,
    ExtensionStatePatchRequest,
    ExtensionSummaryModel,
    ExtensionTemplateRequest,
    ExtensionUiContributionModel,
    SheetCatalogColumnModel,
    SheetCatalogDiagnosticModel,
    SheetCatalogExecuteResponseModel,
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


def _settings_contribution(
    manifest: ExtensionManifest,
) -> ExtensionSettingsContributionModel | None:
    """清单的设置呈现声明 → 摘要契约；未声明设置时为 ``None``。"""
    contribution = manifest.settings_contribution
    if contribution is None:
        return None
    return ExtensionSettingsContributionModel(
        presentation=contribution.presentation,
        route_key=contribution.route_key,
    )


def _settings_items(
    contribution: SettingsContribution | None,
    field_specs: tuple[SettingsFieldSpec, ...],
) -> list[ExtensionSettingsItemModel]:
    """``generated`` 字段项：Provider 语义 ⊕ Manifest 呈现，按 ``order, key`` 排序。

    清单只声明可发现性（key/顺序/i18n key），控件类型、默认值与约束只由
    Provider 定义（ARCH-DM-006 §8.2）。配对校验（``settings_provider_error``）
    是清单字段可解释性的唯一放行点：声明了 ``generated`` 而字段无法被 Provider
    解释时，读取早已给出稳定诊断，永远不会走到这里；因此本函数不做“解释不了
    就跳过”的静默过滤——那正是 §8.1 禁止的部分结果。Provider 自报但清单未
    声明的字段不进入呈现。``custom`` 与未声明设置的扩展返回空列表。
    """
    if contribution is None or contribution.presentation != "generated":
        return []
    specs = {spec.key: spec for spec in field_specs}
    items: list[ExtensionSettingsItemModel] = []
    for field in contribution.fields:
        # 契约破坏（清单字段无 Provider 元数据）直接 KeyError 失败报错，绝不静默省略
        spec = specs[field.key]
        items.append(
            ExtensionSettingsItemModel(
                key=field.key,
                label_key=field.label_key,
                description_key=field.description_key,
                order=field.order,
                control=spec.control,
                default=spec.default,
                nullable=spec.nullable,
                min_value=spec.min_value,
                max_value=spec.max_value,
                options=list(spec.options),
                max_length=spec.max_length,
            )
        )
    return sorted(items, key=lambda item: (item.order, item.key))


def _settings_response(
    runtime: ExtensionRuntime, extension_id: str, view: ExtensionSettingsView
) -> ExtensionSettingsResponseModel:
    """设置视图 → 响应契约：保留版本化三字段，追加有效值/只读诊断/字段项。"""
    contribution = runtime.settings_contribution(extension_id)
    return ExtensionSettingsResponseModel(
        schema_version=view.schema_version,
        revision=view.revision,
        value=dict(view.value),
        effective_value=dict(view.effective_value),
        read_only=view.read_only,
        diagnostic_code=view.diagnostic_code,
        items=_settings_items(contribution, runtime.settings_field_specs(extension_id)),
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
        settings_contribution=_settings_contribution(manifest),
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


def _template_snapshot(body_template: ExtensionTemplateRequest) -> SheetCatalogTemplate:
    """契约模板快照 → 扩展模板值对象（原样传递，规范化属预览阶段）。"""
    return SheetCatalogTemplate(
        template_id=body_template.template_id,
        name=body_template.name,
        schema_version=TEMPLATE_SCHEMA_VERSION,
        columns=tuple(
            TemplateColumn(
                column_id=column.column_id,
                header=column.header,
                expression=column.expression,
            )
            for column in body_template.columns
        ),
    )


def _preview_request(body: ExtensionPreviewRequest) -> SheetCatalogPreviewRequest:
    """契约模型 → 预览请求值对象（模板快照原样传递，规范化属预览阶段）。"""
    return SheetCatalogPreviewRequest(
        workspace_id=body.workspace_id,
        base_revision_id=body.base_revision_id,
        template=_template_snapshot(body.template),
    )


def _execute_request(body: ExtensionExecuteRequest) -> SheetCatalogExecuteRequest:
    """契约模型 → 执行请求值对象（模板快照与摘要原样传递，复核属宿主运行时）。"""
    return SheetCatalogExecuteRequest(
        workspace_id=body.workspace_id,
        base_revision_id=body.base_revision_id,
        template=_template_snapshot(body.template),
        preview_digest=body.preview_digest,
        save_grant_id=body.save_grant_id,
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


def _dispatch_execute(
    request: Request,
    extension_id: str,
    action_id: str,
    body: ExtensionExecuteRequest,
):
    """执行分派：契约校验后交宿主运行时编排（摘要复核→候选→授权→保存→登记）。"""
    runtime = _runtime(request)
    try:
        result = runtime.execute_action(extension_id, action_id, _execute_request(body))
    except ExtensionPlatformError as exc:
        return _error_response(exc)
    return SheetCatalogExecuteResponseModel(
        artifact_id=result.artifact_id,
        file_name=result.file_name,
        output_path=result.output_path,
        warnings=[_diagnostic_model(warning) for warning in result.warnings],
    )


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
        response_model=ExtensionSettingsResponseModel,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def get_extension_settings(extension_id: str, request: Request):
        runtime = _runtime(request)
        try:
            view = runtime.get_settings(extension_id)
            return _settings_response(runtime, extension_id, view)
        except ExtensionPlatformError as exc:
            return _error_response(exc)

    @app.put(
        "/api/extensions/{extension_id}/settings",
        response_model=ExtensionSettingsResponseModel,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def put_extension_settings(
        extension_id: str, body: ExtensionSettingsPutRequest, request: Request
    ):
        runtime = _runtime(request)
        try:
            view = runtime.put_settings(
                extension_id, body.schema_version, body.value, body.expected_revision
            )
            return _settings_response(runtime, extension_id, view)
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
        response_model=SheetCatalogExecuteResponseModel,
        responses=_ERROR_RESPONSES,
        tags=["extensions"],
    )
    def execute_extension_action(
        extension_id: str, action_id: str, body: ExtensionExecuteRequest, request: Request
    ):
        return _dispatch_execute(request, extension_id, action_id, body)

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
                availability=runtime.artifact_availability(record),
            )
        except ExtensionPlatformError as exc:
            return _error_response(exc)
