import asyncio
import json
import logging
import os
import tomllib
from collections.abc import Callable, Sequence
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from dst_manager.application.extensions.runtime import ExtensionRuntime, default_runtime
from dst_manager.application.service import ApplicationError, DstManagerService
from dst_manager.config import Settings
from dst_manager.extensions.builtin.index import BUILTIN_EXTENSION_INDEX
from dst_manager.extensions.save_grants import SaveGrantStore
from dst_manager.infrastructure.acsm_xml.document import AcsmValidationError
from dst_manager.interfaces import extension_api
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
from dst_manager.interfaces.message_catalog import error_payload
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
from dst_manager.interfaces.settings_contracts import (
    AboutResponse,
    EnumOptionModel,
    LicenseInfo,
    SettingsItemModel,
    SettingsPutRequest,
    SettingsResponse,
)
from dst_manager.settings.registry import REGISTRY, enum_options, min_max
from dst_manager.settings.resolver import FieldSource, SettingsSnapshot
from dst_manager.settings.runtime import (
    RuntimeSettings,
    SettingsConflict,
    SettingsValidationError,
)
from dst_manager.settings.store import (
    SCHEMA_VERSION,
    SettingsSchemaNewer,
    SettingsSchemaOlder,
)

from ..runtime import resource_dir

logger = logging.getLogger(__name__)


class OpenRequest(ContractModel):
    dst_path: Path
    root_override: Path | None = None


_APP_NAME = "DST Manager"
_HOMEPAGE = "https://github.com/sonicg83/autocad-sheetset"


def _app_version() -> str:
    """应用版本：分发元数据优先，缺失时回退读 pyproject.toml。

    frozen 态 pyproject.toml 不保证随包分发，全部来源不可得时容错返回
    "版本未知" 字符串，绝不让 /api/about 因版本探测崩溃。
    """
    try:
        # 发行名以 pyproject.toml [project].name 为准（autocad-sheetset），
        # 而非 CLI/包目录名 dst-manager——后者永远查不到，主路径才是活代码
        return package_version("autocad-sheetset")
    except PackageNotFoundError:
        pass
    try:
        with (resource_dir() / "pyproject.toml").open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "版本未知"


def _license_text() -> str:
    """LICENSE 全文：开发态读仓库根，frozen 态读 resource_dir()/LICENSE（任务 7 打包）。"""
    try:
        return (resource_dir() / "LICENSE").read_text(encoding="utf-8")
    except OSError:
        return ""


def _settings_items(snapshot: SettingsSnapshot) -> list[SettingsItemModel]:
    """快照按 REGISTRY 稳定顺序转响应模型；值经控件类型规整（Path → str|None）。"""
    items: list[SettingsItemModel] = []
    for meta in REGISTRY:
        raw = getattr(snapshot.settings, meta.key)
        value: bool | int | str | None
        if meta.control == "path":
            value = str(raw) if raw is not None else None
        else:
            value = raw
        # default 取 Settings 字段默认值（与 resolver._field_default 同规则），
        # 不随 env/文件覆盖漂移——快照 settings 在降级分支才是纯默认构造
        raw_default = Settings.model_fields[meta.key].get_default(call_default_factory=True)
        if meta.control == "path":
            default: bool | int | str | None = (
                str(raw_default) if raw_default is not None else None
            )
        else:
            default = raw_default
        source = snapshot.sources[meta.key]
        item = SettingsItemModel(
            key=meta.key,
            label_key=meta.label_key,
            category_key=meta.category_key,
            control=meta.control,
            value=value,
            default=default,
            source=source.source,  # type: ignore[arg-type]
            has_file_override=source.has_file_override,
        )
        if meta.control == "path":
            item.nullable = meta.nullable
            item.file_filter_key = meta.file_filter_key
            item.file_kind = meta.file_kind
        elif meta.control == "enum":
            item.options = [
                EnumOptionModel(**option) for option in enum_options(meta.key)
            ]
        else:  # int 控件：无 ge/le 约束的字段（cad_timeout_seconds）不设范围
            try:
                item.min, item.max = min_max(meta.key)
            except ValueError:
                pass
        items.append(item)
    return items


def _settings_response(snapshot: SettingsSnapshot) -> SettingsResponse:
    return SettingsResponse(
        schema_version=SCHEMA_VERSION,
        config_revision=snapshot.config_revision,
        items=_settings_items(snapshot),
        diagnostics=snapshot.diagnostics,
        schema_blocked=snapshot.schema_blocked,
    )


def _schema_older_snapshot() -> SettingsSnapshot:
    """schema 过旧的只读降级快照：忽略文件覆盖，按默认值与环境变量展示。

    resolver 对 SettingsSchemaNewer 已内置降级；Older 本期无迁移器，由本端点
    处置——原则是旧 Schema 文件绝不能经本程序写回（PUT 一律 409）。
    """
    return SettingsSnapshot(
        settings=Settings(),
        sources={meta.key: FieldSource("default", False) for meta in REGISTRY},
        diagnostics=[
            "SETTINGS_SCHEMA_OLDER",
            "设置文件 schema 版本低于当前程序，已忽略文件覆盖并按默认值与环境变量只读展示",
        ],
        config_revision=0,
        schema_blocked=True,
    )


def create_app(
    settings: Settings | None = None,
    on_workspace_opened: Callable[[object], None] | None = None,
    runtime_settings: RuntimeSettings | None = None,
    extension_runtime: ExtensionRuntime | None = None,
    extension_index: Sequence | None = None,
    save_grants: SaveGrantStore | None = None,
) -> FastAPI:
    """构建 FastAPI 应用。

    ``on_workspace_opened`` 是仅 Python 内部可选回调（默认 None，不改任何 HTTP
    契约）：工作区打开成功后被以服务端 Workspace 调用一次，供桌面壳登记可信
    当前上下文（PLAN-DM-015 任务 2）。

    ``runtime_settings`` 是进程内设置快照持有者（PLAN-DM-019 任务 4）：由
    ``run_desktop`` 构造一次同时供 API 与桌面服务共用；为 None 时（开发态
    serve / 既有测试）不注册设置与关于端点，契约零变化。

    ``extension_runtime``/``extension_index`` 是扩展平台注入点（PLAN-DM-020
    任务 3）：严格在 ``DstManagerService`` 完成数据库迁移与发布恢复之后才创建/
    接收运行时并调用 ``discover()``；单扩展发现失败由注册表隔离，不影响
    ``/api/health`` 与核心工作区 API。

    ``save_grants`` 是扩展执行通道注入点（PLAN-DM-020 任务 9）：桌面壳把与
    ``ShellBridge`` **同一个** :class:`SaveGrantStore` 传入，桥创建的一次性
    保存授权才能被 API 执行消费；缺省时默认装配新建独立实例。
    """
    app = FastAPI(title="DST Manager", version="0.3.0")
    service = DstManagerService(settings)
    app.state.service = service

    if extension_runtime is None:
        extension_runtime = default_runtime(
            service.database.sessions,
            # 未注入时默认装配新建独立实例：默认装配下执行通道可用，
            # 桌面壳的共享实例经参数传入（PLAN-DM-020 任务 9）。
            save_grants=save_grants if save_grants is not None else SaveGrantStore(),
            proposal_root=(service.settings.data_dir) / "tmp" / "extension-candidates",
        )
    app.state.extension_runtime = extension_runtime
    try:
        extension_runtime.start(extension_index or BUILTIN_EXTENSION_INDEX)
    except Exception:
        logger.warning("EXTENSION_BOOTSTRAP_FAILED", exc_info=True)
    extension_api.register_extension_routes(app)

    @app.exception_handler(ApplicationError)
    async def application_error(_, exc: ApplicationError):
        # PLAN-DM-021 Task 9：统一错误结构 {code, message_key, params, message}；
        # message 保留原始诊断（兼容文本 + 排障），message_key 由接口层目录提供
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, str(exc), params=exc.params),
        )

    @app.exception_handler(AcsmValidationError)
    async def acsm_validation_error(_, exc: AcsmValidationError):
        return JSONResponse(status_code=422, content=error_payload(exc.code, str(exc)))

    @app.get("/api/health", response_model=HealthResponse, response_model_exclude_unset=True)
    def health():
        return {"status": "ok", "run_id": os.environ.get("DST_MANAGER_RUN_ID")}

    @app.get("/api/custom-properties/template")
    def custom_property_template():
        return Response(
            content=b"type,name,default_value\r\n",
            media_type="text/csv; charset=utf-8",
            # 桌面壳（WebView2）按该头命名落盘文件；URL 末段无扩展名，不能省略
            headers={"Content-Disposition": 'attachment; filename="custom-properties-template.csv"'},
        )

    @app.post("/api/workspaces/open", response_model=WorkspaceResponse, response_model_exclude_unset=True)
    def open_workspace(request: OpenRequest):
        workspace = service.open_workspace(request.dst_path, request.root_override)
        if on_workspace_opened is not None:
            on_workspace_opened(workspace)
        return workspace_json(workspace)

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
            headers={"Content-Disposition": 'attachment; filename="custom-properties-export.csv"'},
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

    if runtime_settings is not None:
        # 设置中心与关于端点（PLAN-DM-019 任务 5）：仅注入 RuntimeSettings 时注册。
        @app.get("/api/settings", response_model=SettingsResponse)
        def get_settings():
            try:
                # 先按文件指纹刷新缓存：外部手编/其他窗口保存后 GET 不读陈旧快照；
                # 文件被替换为旧 schema 时刷新本身即抛 SettingsSchemaOlder
                runtime_settings.refresh_if_changed()
                snapshot = runtime_settings.current()
            except SettingsSchemaOlder:
                snapshot = _schema_older_snapshot()
            return _settings_response(snapshot)

        @app.put("/api/settings", response_model=SettingsResponse)
        def put_settings(request: SettingsPutRequest):
            try:
                # 与 GET 一致先按文件指纹刷新：进程启动后直接 PUT 时，
                # 只读守卫不得建立在陈旧快照（schema_blocked=False）之上
                runtime_settings.refresh_if_changed()
                snapshot = runtime_settings.current()
                if snapshot.schema_blocked:
                    return JSONResponse(
                        status_code=409,
                        content=error_payload(
                            "SETTINGS_SCHEMA_BLOCKED",
                            "设置文件 schema 版本与当前程序不兼容，已进入只读模式，不能保存",
                        ),
                    )
                snapshot = runtime_settings.apply_changes(
                    request.set, request.unset, request.expected_revision
                )
            except SettingsSchemaNewer:
                # 刷新与 apply_changes 落盘之间文件被替换为新 Schema 的竞态：拒绝写回
                return JSONResponse(
                    status_code=409,
                    content=error_payload(
                        "SETTINGS_SCHEMA_BLOCKED",
                        "设置文件 schema 版本与当前程序不兼容，已进入只读模式，不能保存",
                    ),
                )
            except SettingsSchemaOlder:
                # current() 未触发的竞态（读后文件被替换为旧 schema）同样拒绝写回
                return JSONResponse(
                    status_code=409,
                    content=error_payload(
                        "SETTINGS_SCHEMA_OLDER",
                        "设置文件 schema 版本低于当前程序，已进入只读模式，不能保存",
                    ),
                )
            except SettingsConflict as exc:
                return JSONResponse(status_code=409, content=error_payload("SETTINGS_CONFLICT", str(exc)))
            except SettingsValidationError as exc:
                # 逐字段 422（ARCH-DM-005 §6.2）：外层 key 为稳定设置 key，
                # 错误对象含 code/message_key/params 与兼容 message
                return JSONResponse(
                    status_code=422,
                    content={
                        "code": "SETTINGS_VALIDATION_FAILED",
                        "errors": {
                            key: error.model_dump() for key, error in exc.errors.items()
                        },
                    },
                )
            return _settings_response(snapshot)

        @app.get("/api/about", response_model=AboutResponse)
        def about():
            return AboutResponse(
                app_name=_APP_NAME,
                version=_app_version(),
                license=LicenseInfo(spdx="MIT", text=_license_text()),
                homepage=_HOMEPAGE,
                feedback_url=f"{_HOMEPAGE}/issues",
            )

    web_dist = resource_dir() / "web" / "dist"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


app = create_app()
