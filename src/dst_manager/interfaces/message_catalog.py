"""已知 API/CAD/Shell 错误目录（PLAN-DM-021 Task 9 / ARCH-DM-005 §6.2 / I18N-11）。

接口层唯一事实源：把现有异常的稳定 ``code`` 适配为
``{code, message_key, params, message}`` 统一负载。约束：

- 只登记现状已会进入桌面界面的 code（application.ApplicationError、
  AcsmValidationError、设置 409/422 外层 code、ShellBridge ``{ok:false}``）；
  不发明新业务错误码，DST 诊断与任务状态不在此列（按功能域渐进迁移）。
- ``message_key`` 是前端文案键（``web/src/i18n/locales/*/errors.ts`` 与本表
  一一对应，占位符与 ``param_schema`` 严格对称，由
  ``tests/unit/test_message_catalog.py`` 交叉守护）。
- ``params`` 只允许结构化插值参数（str/int/bool/list[str] 白名单，拒绝本地化
  label 或完整句子）；结构化参数从异常详情中提取——详情只取稳定值
  （路径/标识/名称/编号），句子型详情不提取。
- 不把翻译资源或 locale 传入 application/domain；本模块不依赖任何语言环境，
  日志继续记录稳定 code 与原始诊断（兼容 ``message`` 原样保留）。
"""

from dataclasses import dataclass, field

from dst_manager.interfaces.extension_contracts import EXTENSION_MESSAGE_KEYS
from dst_manager.settings.errors import ParamValue

__all__ = ["CATALOG", "ErrorCatalogEntry", "error_payload", "known_codes", "shell_error"]

_PARAM_TYPES = (str, int, bool, list)


@dataclass(frozen=True)
class ErrorCatalogEntry:
    """单个稳定 code 的文案键与参数 schema。

    ``param_schema``：参数名 -> 允许类型（白名单，拒绝任意对象/句子）。
    ``detail_param``：从异常详情提取的参数名（详情规则见 :func:`_detail_from_message`）。
    """

    message_key: str
    param_schema: dict[str, type] = field(default_factory=dict)
    detail_param: str | None = None


def _E(message_key: str, param_schema: dict[str, type] | None = None, detail_param: str | None = None) -> ErrorCatalogEntry:
    return ErrorCatalogEntry(message_key=message_key, param_schema=param_schema or {}, detail_param=detail_param)


# 注意：shell 组 code 由 :func:`shell_error` 消费，其余由 API 统一 handler 消费。
CATALOG: dict[str, ErrorCatalogEntry] = {
    # ---- 工作区（application.ApplicationError） ----
    "WORKSPACE_NOT_FOUND": _E("errors.workspace.notFound"),
    "WORKSPACE_WRITE_BUSY": _E("errors.workspace.writeBusy"),
    "DST_NOT_FOUND": _E("errors.workspace.dstNotFound", {"dst_path": str}, "dst_path"),
    # ---- 修订 ----
    "REVISION_CONFLICT": _E("errors.revision.conflict"),
    "REVISION_NOT_FOUND": _E("errors.revision.notFound"),
    "REVISION_MANIFEST_MISSING": _E("errors.revision.manifestMissing"),
    "REVISION_RESTORE_CONFLICT": _E("errors.revision.restoreConflict"),
    "REVISION_RESTORE_SOURCE_CHANGED": _E("errors.revision.restoreSourceChanged"),
    # ---- 草稿 ----
    "DRAFT_CONFLICT": _E("errors.draft.conflict"),
    # ---- 标准驱动创建（PLAN-DM-036 Task 4；草稿/标准/目标/导入四个入口的稳定码） ----
    # 参数只携带可数诊断条数，导入的逐条定位（工作表/行/列）随 422 响应体的
    # ``diagnostics`` 返回，不进 params。
    "CREATION_DRAFT_NOT_FOUND": _E("errors.creation.draftNotFound"),
    "CREATION_DRAFT_INVALID": _E("errors.creation.draftInvalid"),
    "CREATION_DRAFT_CONFLICT": _E("errors.creation.draftConflict"),
    "CREATION_DRAFT_CORRUPT": _E("errors.creation.draftCorrupt"),
    "CREATION_STANDARD_MISSING": _E("errors.creation.standardMissing"),
    "CREATION_TARGET_NOT_EMPTY": _E("errors.creation.targetNotEmpty"),
    "CREATION_IMPORT_INVALID": _E("errors.creation.importInvalid", {"count": int}),
    # 执行入口（`POST /{id}/execute`）的预览漂移：摘要不符即 409，必须重新预览。
    "CREATION_PREVIEW_STALE": _E("errors.creation.previewStale"),
    # 创建暂存与发布事务码（PLAN-DM-036 Task 5/6；逐条核对 raise 点：创建计划门禁、
    # 作业身份、资产定位、布局/Handle 回填、DST 往返、CAD 能力与发布事务）。这些码
    # 既可能是 HTTP 错误，也可能是创建任务的 error_code，界面用同一套 errors.creation
    # 文案呈现，因此同批登记。
    "CREATION_PLAN_INVALID": _E("errors.creation.planInvalid"),
    "CREATION_JOB_ID_INVALID": _E("errors.creation.jobIdInvalid"),
    "CREATION_ATTEMPT_INVALID": _E("errors.creation.attemptInvalid"),
    "CREATION_ASSET_PATH_INVALID": _E("errors.creation.assetPathInvalid"),
    "CREATION_ASSET_FILE_MISSING": _E("errors.creation.assetFileMissing"),
    "CREATION_LAYOUT_TEMPLATE_MISMATCH": _E("errors.creation.layoutTemplateMismatch"),
    "CREATION_LAYOUT_SET_MISMATCH": _E("errors.creation.layoutSetMismatch"),
    "CREATION_LAYOUT_READ_FAILED": _E("errors.creation.layoutReadFailed"),
    "CREATION_LAYOUT_REFERENCE_INVALID": _E("errors.creation.layoutReferenceInvalid"),
    "CREATION_HANDLE_INVALID": _E("errors.creation.handleInvalid"),
    "CREATION_HANDLE_PLACEHOLDER": _E("errors.creation.handlePlaceholder"),
    "CREATION_HANDLE_DUPLICATE": _E("errors.creation.handleDuplicate"),
    "CREATION_HANDLE_SET_MISMATCH": _E("errors.creation.handleSetMismatch"),
    "CREATION_ROUNDTRIP_MISMATCH": _E("errors.creation.roundtripMismatch"),
    "CREATION_DST_INVALID": _E("errors.creation.dstInvalid"),
    "CREATION_SKELETON_INVALID": _E("errors.creation.skeletonInvalid"),
    "CREATION_SKELETON_UNREADABLE": _E("errors.creation.skeletonUnreadable"),
    "CREATION_CAD_UNAVAILABLE": _E("errors.creation.cadUnavailable"),
    "CREATION_CAD_FAILED": _E("errors.creation.cadFailed"),
    "CREATION_PUBLISH_INVALID": _E("errors.creation.publishInvalid"),
    "CREATION_PUBLISH_FAILED": _E("errors.creation.publishFailed"),
    "CREATION_PUBLISH_CONFLICT": _E("errors.creation.publishConflict"),
    "CREATION_PUBLISH_REVIEW_REQUIRED": _E("errors.creation.publishReviewRequired"),
    # ---- 任务 ----
    "JOB_NOT_FOUND": _E("errors.job.notFound"),
    "JOB_NOT_RETRYABLE": _E("errors.job.notRetryable"),
    # ---- 预览与执行计划 ----
    "PLAN_INVALID": _E("errors.plan.invalid"),
    "REPREVIEW_REQUIRED": _E("errors.plan.repreviewRequired"),
    # ---- 修复 ----
    "REPAIR_BLOCKED": _E("errors.repair.blocked"),
    "REPAIR_NOT_REQUIRED": _E("errors.repair.notRequired"),
    "REPAIR_CONFIRMATION_REQUIRED": _E("errors.repair.confirmationRequired"),
    "REPAIR_UNRECOVERABLE": _E("errors.repair.unrecoverable"),
    # ---- XML 导出 ----
    "XML_VALIDATION_FAILED": _E("errors.xml.validationFailed"),
    "DESTINATION_BASELINE_REQUIRED": _E("errors.export.baselineRequired"),
    "DESTINATION_OUTSIDE_WORKSPACE": _E("errors.export.outsideWorkspace"),
    # ---- CAD 环境 ----
    "CAD_VERSION_INVALID": _E("errors.cad.versionInvalid", {"cad_version": str}, "cad_version"),
    "CAD_CAPABILITY_UNAVAILABLE": _E("errors.cad.capabilityUnavailable"),
    "LAYOUT_READ_FAILED": _E("errors.layout.readFailed"),
    "LAYOUT_SOURCE_NOT_FOUND": _E("errors.layout.sourceNotFound"),
    "LAYOUT_SOURCE_TYPE_INVALID": _E("errors.layout.sourceTypeInvalid"),
    "LAYOUT_SOURCE_INVALID": _E("errors.dwg.layoutSourceInvalid"),
    # ---- 命令 ----
    "COMMAND_UNSUPPORTED": _E("errors.command.unsupported", {"command": str}, "command"),
    "COMMAND_REQUIRES_CAD": _E("errors.command.requiresCad", {"command": str}, "command"),
    # ---- 设置中心（PUT /api/settings 外层 code；逐字段 422 见 settings/errors.py） ----
    "SETTINGS_CONFLICT": _E("errors.settings.conflict"),
    "SETTINGS_SCHEMA_BLOCKED": _E("errors.settings.schemaBlocked"),
    "SETTINGS_SCHEMA_OLDER": _E("errors.settings.schemaOlder"),
    "SETTINGS_VALIDATION_FAILED": _E("errors.settings.validationFailed"),
    # ---- ShellBridge（interfaces/shell.py，{ok:false} 结果） ----
    "SHELL_WORKSPACE_UNAVAILABLE": _E("errors.shell.workspaceUnavailable"),
    "SHELL_OPEN_FAILED": _E("errors.shell.openFailed"),
    "SHELL_DIRECTORY_NOT_FOUND": _E("errors.shell.directoryNotFound"),
    "SHELL_EXTERNAL_URL_REJECTED": _E("errors.shell.externalUrlRejected"),
    "SHEET_PREFERENCES_IO": _E("errors.shell.preferencesIo"),
    "SHEET_PREFERENCES_INVALID": _E("errors.shell.preferencesInvalid"),
    # 导出成果"打开所在文件夹"（PLAN-DM-020 Task 11B；artifactNotFound 复用
    # 扩展域既有键，目录缺失用专用键区分图纸集目录语义）
    "EXTENSION_ARTIFACT_NOT_FOUND": _E("errors.extension.artifactNotFound"),
    "SHELL_ARTIFACT_DIRECTORY_NOT_FOUND": _E("errors.shell.artifactDirectoryNotFound"),
    # ---- ShellBridge 扩展平台码（PLAN-DM-024 Task 2 / MEMO-DM-031 F3） ----
    # 三个 Shell 侧扩展错误此前只带中文 message、缺 message_key，en-US 用户看到
    # 原始中文串。复用 extension_contracts.EXTENSION_MESSAGE_KEYS 的既有键：Shell
    # 与 API 的同名平台码共用同一前端文案，不新建第二套文案键（无循环导入：
    # extension_contracts -> contracts.py 不依赖本模块）。
    "EXTENSION_NOT_FOUND": _E(EXTENSION_MESSAGE_KEYS["EXTENSION_NOT_FOUND"]),
    "EXTENSION_ACTION_NOT_FOUND": _E(EXTENSION_MESSAGE_KEYS["EXTENSION_ACTION_NOT_FOUND"]),
    "EXTENSION_CAPABILITY_UNAVAILABLE": _E(EXTENSION_MESSAGE_KEYS["EXTENSION_CAPABILITY_UNAVAILABLE"]),
    # ---- 扩展平台设置码（PLAN-DM-025 Task 3/4 / ARCH-DM-006 §8.1、§11、§12） ----
    # 已存设置 Schema 高于当前版本：GET 为 200 只读视图，PUT 以同一稳定 code
    # 与 HTTP 409 拒绝（extension_api 直接返回统一错误负载）；此处登记使该码
    # 进入 UI 可见错误名录并复用扩展域既有文案键。参数只携带扩展 ID 与两个
    # Schema 版本号，不登记占位符。
    "EXTENSION_SETTINGS_SCHEMA_NEWER": _E(
        EXTENSION_MESSAGE_KEYS["EXTENSION_SETTINGS_SCHEMA_NEWER"]
    ),
    # 预览后应用级扩展设置变化：动作执行以同一稳定 code 与 HTTP 409 拒绝
    # （必须重新预览）。
    # 登记本身也是防 500 的硬要求：不登记就会让 extension_api 按码索引文案键
    # 抛 KeyError（与 R9 同类缺陷），参数同样只携带标识与修订号、无占位符。
    "EXTENSION_SETTINGS_CHANGED": _E(
        EXTENSION_MESSAGE_KEYS["EXTENSION_SETTINGS_CHANGED"]
    ),
    # ---- CAD/Acsm 结构校验（AcsmValidationError，422 handler） ----
    "SHEET_NOT_FOUND": _E("errors.sheet.notFound", {"object_id": str}, "object_id"),
    "ACSMSHEET_NOT_FOUND": _E("errors.sheet.nodeNotFound", {"object_id": str}, "object_id"),
    "ACSMSHEET_DUPLICATED": _E("errors.sheet.nodeDuplicated", {"object_id": str}, "object_id"),
    "SHEET_TITLE_EMPTY": _E("errors.sheet.titleEmpty"),
    "SHEET_LAYOUT_COUNT": _E("errors.sheet.layoutCount", {"object_id": str}, "object_id"),
    "SHEET_POSITION_INVALID": _E("errors.sheet.positionInvalid", {"position": str}, "position"),
    "SHEET_INSERT_COUNT_INVALID": _E("errors.sheet.insertCountInvalid", {"value": str}, "value"),
    "SUBSET_NOT_FOUND": _E("errors.subset.notFound", {"subset_id": str}, "subset_id"),
    "ACSMSUBSET_NOT_FOUND": _E("errors.subset.nodeNotFound", {"object_id": str}, "object_id"),
    "ACSMSUBSET_DUPLICATED": _E("errors.subset.nodeDuplicated", {"object_id": str}, "object_id"),
    "SUBSET_POSITION_INVALID": _E("errors.subset.positionInvalid", {"position": str}, "position"),
    "EMPTY_SUBSET": _E("errors.subset.empty"),
    "SHEET_SET_INVALID": _E("errors.sheetSet.invalid"),
    "SHEET_SET_MISSING": _E("errors.sheetSet.missing"),
    "CUSTOM_PROPERTY_NOT_FOUND": _E("errors.property.notFound", {"name": str}, "name"),
    "CUSTOM_PROPERTY_DUPLICATED": _E("errors.property.duplicated", {"name": str}, "name"),
    "CUSTOM_PROPERTY_VALUE_DUPLICATED": _E("errors.property.valueDuplicated", {"name": str}, "name"),
    "CUSTOM_PROPERTY_BAG_DUPLICATED": _E("errors.property.bagDuplicated", {"owner_id": str}, "owner_id"),
    "CUSTOM_PROPERTY_FLAGS_MISSING": _E("errors.property.flagsMissing", {"name": str}, "name"),
    "CUSTOM_PROPERTY_FLAGS_INVALID": _E("errors.property.flagsInvalid", {"name": str}, "name"),
    "CUSTOM_PROPERTY_TYPE_INVALID": _E("errors.property.typeInvalid", {"type": str}, "type"),
    "CUSTOM_PROPERTY_TYPE_CONFLICT": _E("errors.property.typeConflict", {"name": str}, "name"),
    "CUSTOM_PROPERTY_NAME_DUPLICATE": _E("errors.property.nameDuplicate", {"name": str}, "name"),
    "CUSTOM_PROPERTY_NAME_EMPTY": _E("errors.property.nameEmpty"),
    "CUSTOM_PROPERTY_NAME_INVALID": _E("errors.property.nameInvalid"),
    "CUSTOM_PROPERTY_VALUE_INVALID": _E("errors.property.valueInvalid"),
    "CUSTOM_PROPERTY_SCOPE_MISMATCH": _E("errors.property.scopeMismatch", {"name": str}, "name"),
    "DUPLICATE_ACSM_ID": _E("errors.dwg.duplicateAcsmId", {"acsm_id": str}, "acsm_id"),
    "DWG_OUTSIDE_WORKSPACE": _E("errors.dwg.outsideWorkspace", {"path": str}, "path"),
    "UNKNOWN_REFERENCE_BLOCKED": _E("errors.dwg.unknownReferenceBlocked", {"object_id": str}, "object_id"),
    "CONTROLLED_PROPERTY_INVALID": _E("errors.xml.controlledPropertyInvalid", {"name": str}, "name"),
    "CONTROLLED_CHILD_RECONCILIATION_FAILED": _E("errors.xml.childReconciliationFailed"),
    "XML_INVALID": _E("errors.xml.invalid"),
    "XML_ROOT_INVALID": _E("errors.xml.rootInvalid"),
    "XML_TEXT_INVALID": _E("errors.xml.textInvalid"),
}


def known_codes() -> frozenset[str]:
    """全部已登记的稳定 code（测试用于锁定枚举清单）。"""
    return frozenset(CATALOG)


def _detail_from_message(message: str) -> str | None:
    """从异常文本中提取稳定详情值。

    两种既有形态：应用层中文消息 ``……：<稳定值>``（取最后一个全角冒号之后）；
    CAD 码 ``CODE: <稳定值>``（取首个 ``": "`` 之后）。取不到或为空返回 None；
    句子型详情（如 XML_ROOT_INVALID 的中文说明）不登记 detail_param，天然不提取。
    """
    if "：" in message:
        detail = message.rsplit("：", 1)[1].strip()
    elif ": " in message:
        detail = message.split(": ", 1)[1].strip()
    else:
        return None
    return detail or None


def _sanitize_params(entry: ErrorCatalogEntry, params: dict[str, ParamValue] | None) -> dict[str, ParamValue]:
    """显式 params 必须完全落在 schema 与类型白名单内（含路径/标识等用户数据原样）。"""
    if not params:
        return {}
    for name, value in params.items():
        if name not in entry.param_schema:
            raise ValueError(f"{entry.message_key}: 未登记的参数 {name!r}")
        if not isinstance(value, entry.param_schema[name]) or not isinstance(value, _PARAM_TYPES):
            raise TypeError(f"{entry.message_key}: 参数 {name!r} 类型越界，禁止携带句子/对象")
    return dict(params)


def error_payload(
    code: str,
    message: str,
    params: dict[str, ParamValue] | None = None,
) -> dict[str, object]:
    """统一错误负载（API 4xx/422/409 JSONResponse content）。

    已知 code：补 ``message_key`` 与 schema 内参数（显式 params 优先，其次从
    详情提取）；``message`` 原样保留为兼容文本与原始诊断。未知 code：不携带
    ``message_key``，原始文本仅作诊断详情由前端按未知错误呈现。
    """
    entry = CATALOG.get(code)
    if entry is None:
        return {"code": code, "params": {}, "message": message}
    merged = _sanitize_params(entry, params)
    if entry.detail_param is not None and entry.detail_param not in merged:
        detail = _detail_from_message(message)
        if detail is not None:
            merged[entry.detail_param] = detail
    return {"code": code, "message_key": entry.message_key, "params": merged, "message": message}


def shell_error(
    code: str,
    message: str,
    params: dict[str, ParamValue] | None = None,
) -> dict[str, object]:
    """ShellBridge ``{ok:false}`` 统一结构：保留 ``code``/``message``，补 ``message_key``/``params``。"""
    payload = error_payload(code, message, params)
    if payload.get("message_key") is None:
        return {"ok": False, "code": code, "params": {}, "message": message}
    return {"ok": False, **payload}
