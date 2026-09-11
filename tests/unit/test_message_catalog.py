"""PLAN-DM-021 Task 9：已知 API/CAD/Shell 错误目录（message_catalog）结构化单测。

覆盖 ARCH-DM-005 §6.2 / I18N-11：
- 目录枚举全部已知 API/CAD/Shell 稳定 code，每个 code 有唯一 ``message_key``、
  参数 schema（名称 + 白名单类型）；
- 中英文资源（``web/src/i18n/locales/{zh-CN,en-US}/errors.ts``）覆盖全部键，
  且翻译占位符与参数 schema 对称；
- 统一负载 ``{code, message_key, params, message}``：``params`` 只允许结构化
  插值参数（拒绝本地化 label / 完整句子 / 非白名单类型），未知 code 不携带 key；
- Shell 桥错误同样返回稳定结构；
- 目录仅存在于接口层：application/domain 不导入目录、不引入翻译资源。
"""

import re
from pathlib import Path

import pytest

from dst_manager.interfaces.error_contracts import ErrorPayloadModel
from dst_manager.interfaces.message_catalog import (
    CATALOG,
    error_payload,
    known_codes,
    shell_error,
)

_REPO = Path(__file__).parents[2]
_LOCALES = _REPO / "web" / "src" / "i18n" / "locales"

# ---- 已知错误码清单（枚举自现状代码，逐一核对 raise 点） ----

# application.ApplicationError（API 统一 handler）
APPLICATION_CODES = {
    "CAD_CAPABILITY_UNAVAILABLE",
    "CAD_VERSION_INVALID",
    "COMMAND_UNSUPPORTED",
    "DESTINATION_BASELINE_REQUIRED",
    "DESTINATION_OUTSIDE_WORKSPACE",
    "DRAFT_CONFLICT",
    "DST_NOT_FOUND",
    "JOB_NOT_FOUND",
    "JOB_NOT_RETRYABLE",
    "LAYOUT_READ_FAILED",
    "LAYOUT_SOURCE_NOT_FOUND",
    "LAYOUT_SOURCE_TYPE_INVALID",
    "PLAN_INVALID",
    "REPAIR_BLOCKED",
    "REPAIR_CONFIRMATION_REQUIRED",
    "REPAIR_NOT_REQUIRED",
    "REPAIR_UNRECOVERABLE",
    "REPREVIEW_REQUIRED",
    "REVISION_CONFLICT",
    "REVISION_MANIFEST_MISSING",
    "REVISION_NOT_FOUND",
    "REVISION_RESTORE_CONFLICT",
    "REVISION_RESTORE_SOURCE_CHANGED",
    "WORKSPACE_NOT_FOUND",
    "WORKSPACE_WRITE_BUSY",
    "XML_VALIDATION_FAILED",
}

# infrastructure.acsm_xml AcsmValidationError（CAD 422 handler；含动态族具体值）
CAD_CODES = {
    "ACSMSHEET_DUPLICATED",
    "ACSMSHEET_NOT_FOUND",
    "ACSMSUBSET_DUPLICATED",
    "ACSMSUBSET_NOT_FOUND",
    "COMMAND_REQUIRES_CAD",
    "CONTROLLED_CHILD_RECONCILIATION_FAILED",
    "CONTROLLED_PROPERTY_INVALID",
    "CUSTOM_PROPERTY_BAG_DUPLICATED",
    "CUSTOM_PROPERTY_DUPLICATED",
    "CUSTOM_PROPERTY_FLAGS_INVALID",
    "CUSTOM_PROPERTY_FLAGS_MISSING",
    "CUSTOM_PROPERTY_NAME_DUPLICATE",
    "CUSTOM_PROPERTY_NAME_EMPTY",
    "CUSTOM_PROPERTY_NAME_INVALID",
    "CUSTOM_PROPERTY_NOT_FOUND",
    "CUSTOM_PROPERTY_SCOPE_MISMATCH",
    "CUSTOM_PROPERTY_TYPE_CONFLICT",
    "CUSTOM_PROPERTY_TYPE_INVALID",
    "CUSTOM_PROPERTY_VALUE_DUPLICATED",
    "CUSTOM_PROPERTY_VALUE_INVALID",
    "DUPLICATE_ACSM_ID",
    "DWG_OUTSIDE_WORKSPACE",
    "EMPTY_SUBSET",
    "LAYOUT_SOURCE_INVALID",
    "SHEET_INSERT_COUNT_INVALID",
    "SHEET_LAYOUT_COUNT",
    "SHEET_NOT_FOUND",
    "SHEET_POSITION_INVALID",
    "SHEET_SET_INVALID",
    "SHEET_SET_MISSING",
    "SHEET_TITLE_EMPTY",
    "SUBSET_NOT_FOUND",
    "SUBSET_POSITION_INVALID",
    "UNKNOWN_REFERENCE_BLOCKED",
    "XML_INVALID",
    "XML_ROOT_INVALID",
    "XML_TEXT_INVALID",
}

# 设置中心 409/422 外层 code（PUT /api/settings）
SETTINGS_CODES = {
    "SETTINGS_CONFLICT",
    "SETTINGS_SCHEMA_BLOCKED",
    "SETTINGS_SCHEMA_OLDER",
    "SETTINGS_VALIDATION_FAILED",
}

# ShellBridge {ok: false} 结果（interfaces/shell.py；三个扩展平台码为
# PLAN-DM-024 Task 2 / MEMO-DM-031 F3 新登记）
SHELL_CODES = {
    "EXTENSION_ACTION_NOT_FOUND",
    "EXTENSION_ARTIFACT_NOT_FOUND",
    "EXTENSION_CAPABILITY_UNAVAILABLE",
    "EXTENSION_NOT_FOUND",
    "SHELL_ARTIFACT_DIRECTORY_NOT_FOUND",
    "SHELL_DIRECTORY_NOT_FOUND",
    "SHELL_EXTERNAL_URL_REJECTED",
    "SHELL_OPEN_FAILED",
    "SHELL_WORKSPACE_UNAVAILABLE",
    "SHEET_PREFERENCES_INVALID",
    "SHEET_PREFERENCES_IO",
}

ALL_KNOWN_CODES = APPLICATION_CODES | CAD_CODES | SETTINGS_CODES | SHELL_CODES


def test_catalog_covers_every_known_api_cad_shell_code():
    """枚举的已知 code 必须全部登记；目录不得遗漏、不得收录清单之外的 code。"""
    assert known_codes() == ALL_KNOWN_CODES


def test_message_keys_are_unique_and_namespaced():
    keys = [entry.message_key for entry in CATALOG.values()]
    assert len(keys) == len(set(keys)), "message_key 必须全局唯一"
    assert all(key.startswith("errors.") for key in keys)


def test_param_schema_only_allows_structured_param_types():
    """参数 schema 只允许结构化白名单类型；detail 参数必须登记在 schema 内。"""
    allowed = (str, int, bool, list)
    for code, entry in CATALOG.items():
        for name, value_type in entry.param_schema.items():
            assert value_type in allowed, f"{code}: 参数 {name} 类型越界"
        if entry.detail_param is not None:
            assert entry.detail_param in entry.param_schema, f"{code}: detail 参数未登记"


# ---- 中英文资源交叉校验 ----


def _parse_errors_ts(locale: str) -> dict[str, str]:
    """解析 errors.ts 为 ``组.键 -> 文本`` 平面映射（文件由本任务生成，格式规整）。"""
    texts: dict[str, str] = {}
    group = ""
    pattern = re.compile(r'^\s{2}([A-Za-z_][A-Za-z0-9_]*):\s*\{\s*$|^\s{4}([A-Za-z_][A-Za-z0-9_]*):\s*"((?:[^"\\]|\\.)*)",\s*$')
    for line in (_LOCALES / locale / "errors.ts").read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        if match.group(1):
            group = match.group(1)
        else:
            assert group, f"{locale}/errors.ts 组外出现叶子键：{line}"
            texts[f"{group}.{match.group(2)}"] = match.group(3)
    return texts


def test_zh_and_en_resources_cover_all_catalog_keys():
    zh = _parse_errors_ts("zh-CN")
    en = _parse_errors_ts("en-US")
    expected = {entry.message_key.removeprefix("errors.") for entry in CATALOG.values()}
    assert expected <= set(zh), f"zh-CN 缺键：{sorted(expected - set(zh))}"
    assert expected <= set(en), f"en-US 缺键：{sorted(expected - set(en))}"


@pytest.mark.parametrize("locale", ["zh-CN", "en-US"])
def test_translation_placeholders_match_param_schema(locale):
    """翻译占位符与参数 schema 严格对称：不多（缺参数渲染空）、不少（参数无落点）。"""
    texts = _parse_errors_ts(locale)
    for code, entry in CATALOG.items():
        text = texts[entry.message_key.removeprefix("errors.")]
        placeholders = set(re.findall(r"\{(\w+)\}", text))
        assert placeholders == set(entry.param_schema), (
            f"{locale} {code}: 占位符 {sorted(placeholders)} 与参数 schema {sorted(entry.param_schema)} 不一致"
        )


# ---- 统一负载 ----


def test_error_payload_known_code_returns_unified_shape():
    payload = error_payload("WORKSPACE_NOT_FOUND", "工作区不存在")
    assert payload["code"] == "WORKSPACE_NOT_FOUND"
    assert payload["message_key"] == "errors.workspace.notFound"
    assert payload["params"] == {}
    assert payload["message"] == "工作区不存在"
    ErrorPayloadModel.model_validate(payload)  # 契约模型校验


def test_error_payload_unknown_code_omits_message_key():
    payload = error_payload("SOME_FUTURE_CODE", "原始诊断")
    assert payload == {"code": "SOME_FUTURE_CODE", "params": {}, "message": "原始诊断"}
    ErrorPayloadModel.model_validate(payload)


def test_error_payload_extracts_stable_suffix_detail_param():
    """应用层中文消息尾部全角冒号后的稳定值提取为参数（DST 路径为用户数据，原样保留）。"""
    payload = error_payload("DST_NOT_FOUND", "DST文件不存在：C:\\work\\样例.dst")
    assert payload["message_key"] == "errors.workspace.dstNotFound"
    assert payload["params"] == {"dst_path": "C:\\work\\样例.dst"}


def test_error_payload_extracts_acsm_prefix_detail_param():
    """CAD 码 ``CODE: 值`` 前缀详情提取为参数。"""
    payload = error_payload("SHEET_NOT_FOUND", "SHEET_NOT_FOUND: sheet-1")
    assert payload["message_key"] == "errors.sheet.notFound"
    assert payload["params"] == {"object_id": "sheet-1"}


def test_error_payload_cad_detail_without_declared_param_stays_in_message():
    """详情为本地化句子（XML_ROOT_INVALID）时不提取参数，原始文本只留在兼容 message。"""
    payload = error_payload("XML_ROOT_INVALID", "XML_ROOT_INVALID: 根节点必须为AcSmDatabase")
    assert payload["params"] == {}
    assert "根节点必须为AcSmDatabase" in payload["message"]


def test_error_payload_rejects_params_outside_schema_or_type_whitelist():
    """显式 params 越界（未登记键 / 非白名单类型 / 不可结构化的句子对象）立即报错，
    不静默丢弃——避免把本地化 label 或完整句子带进 params。"""
    with pytest.raises(ValueError):
        error_payload("SHEET_NOT_FOUND", "SHEET_NOT_FOUND: sheet-1", params={"extra": "x"})
    with pytest.raises((ValueError, TypeError)):
        error_payload("SHEET_NOT_FOUND", "SHEET_NOT_FOUND: sheet-1", params={"object_id": ["sheet-1"]})
    with pytest.raises((ValueError, TypeError)):
        error_payload("SHEET_NOT_FOUND", "x", params={"object_id": {"sentence": "完整句子"}})


def test_error_payload_explicit_params_override_detail_extraction():
    payload = error_payload("CAD_VERSION_INVALID", "不支持的AutoCAD版本：2016", params={"cad_version": "2020"})
    assert payload["params"] == {"cad_version": "2020"}


# ---- Shell 桥错误结构 ----


def test_shell_error_returns_stable_structure():
    result = shell_error("SHELL_OPEN_FAILED", "系统找不到指定的路径")
    assert result["ok"] is False
    assert result["code"] == "SHELL_OPEN_FAILED"
    assert result["message_key"] == "errors.shell.openFailed"
    assert result["params"] == {}
    assert result["message"] == "系统找不到指定的路径"


def test_shell_error_unknown_code_falls_back_without_key():
    result = shell_error("SHELL_FUTURE_CODE", "原始诊断")
    assert result["ok"] is False
    assert "message_key" not in result
    assert result["message"] == "原始诊断"


# ---- Shell 扩展错误复用 extension 域既有文案键（PLAN-DM-024 Task 2 / MEMO-DM-031 F3） ----


@pytest.mark.parametrize(
    "code",
    ["EXTENSION_NOT_FOUND", "EXTENSION_ACTION_NOT_FOUND", "EXTENSION_CAPABILITY_UNAVAILABLE"],
)
def test_shell_extension_codes_reuse_extension_message_keys(code):
    """三个 Shell 扩展 code 必须登记为 UI 可见错误（进 CATALOG），且复用
    extension_contracts.EXTENSION_MESSAGE_KEYS 的既有键，不新建第二套文案键。"""
    from dst_manager.interfaces.extension_contracts import EXTENSION_MESSAGE_KEYS

    assert code in known_codes()
    assert code in EXTENSION_MESSAGE_KEYS
    assert CATALOG[code].message_key == EXTENSION_MESSAGE_KEYS[code]


# ---- 分层约束 ----


def test_catalog_is_interface_layer_only():
    """目录只在接口层：application/domain 不导入 catalog，也不引入翻译/locale 概念。"""
    for layer in ("application", "domain"):
        for source in (_REPO / "src" / "dst_manager" / layer).rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "message_catalog" not in text, f"{source} 不得依赖错误目录"
            assert "message_key" not in text, f"{source} 不得承载文案键"
    catalog_source = (_REPO / "src" / "dst_manager" / "interfaces" / "message_catalog.py").read_text(encoding="utf-8")
    for token in ("ui_locale", "gettext", "setlocale", "getdefaultlocale"):
        assert token not in catalog_source, "catalog 不按语言环境选择文本"
