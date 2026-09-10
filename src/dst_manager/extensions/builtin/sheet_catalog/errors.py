"""图纸目录错误词汇表（PLAN-DM-020 Task 5 / SPEC-DM-012 §11）。

七个目录错误码的封闭词汇：稳定 ``code``、稳定 ``message_key``、结构化参数
白名单与用户结果语义。错误工厂只接受词汇表中登记的 code 与参数（键与类型
双重白名单，拒绝任意对象、本地化 label 或完整句子进入 ``params``）。
``VALUE_MISSING`` 是允许执行的 warning（``blocking=False``），其余六个码
均为阻断语义。本模块不读取翻译资源，不做本地化。
"""

from __future__ import annotations

from typing import Literal

from dst_manager.settings.errors import ParamValue

__all__ = [
    "SHEET_CATALOG_BLOCKING",
    "SHEET_CATALOG_MESSAGE_KEYS",
    "SHEET_CATALOG_PARAM_SCHEMAS",
    "SHEET_CATALOG_USER_RESULTS",
    "SheetCatalogError",
    "SheetCatalogErrorCode",
    "sheet_catalog_error",
]


SheetCatalogErrorCode = Literal[
    "SHEET_CATALOG_EXPRESSION_INVALID",
    "SHEET_CATALOG_FIELD_UNDEFINED",
    "SHEET_CATALOG_VALUE_MISSING",
    "SHEET_CATALOG_COLUMN_DUPLICATE",
    "SHEET_CATALOG_TEMPLATE_LIMIT",
    "SHEET_CATALOG_TEMPLATE_CONFLICT",
    "SHEET_CATALOG_XLSX_INVALID",
]

#: 稳定文案键（ARCH-DM-005 §6.2 ``errors.<域>.<camelCase>`` 形态，与既有
#: ``message_catalog.py``/``EXTENSION_MESSAGE_KEYS`` 的键风格一致）。
SHEET_CATALOG_MESSAGE_KEYS: dict[str, str] = {
    "SHEET_CATALOG_EXPRESSION_INVALID": "errors.sheetCatalog.expressionInvalid",
    "SHEET_CATALOG_FIELD_UNDEFINED": "errors.sheetCatalog.fieldUndefined",
    "SHEET_CATALOG_VALUE_MISSING": "errors.sheetCatalog.valueMissing",
    "SHEET_CATALOG_COLUMN_DUPLICATE": "errors.sheetCatalog.columnDuplicate",
    "SHEET_CATALOG_TEMPLATE_LIMIT": "errors.sheetCatalog.templateLimit",
    "SHEET_CATALOG_TEMPLATE_CONFLICT": "errors.sheetCatalog.templateConflict",
    "SHEET_CATALOG_XLSX_INVALID": "errors.sheetCatalog.xlsxInvalid",
}

#: 每个 code 允许的结构化参数白名单（键 -> 类型）。
SHEET_CATALOG_PARAM_SCHEMAS: dict[str, dict[str, type]] = {
    "SHEET_CATALOG_EXPRESSION_INVALID": {"source_start": int, "column_header": str},
    "SHEET_CATALOG_FIELD_UNDEFINED": {"scope": str, "name": str},
    "SHEET_CATALOG_VALUE_MISSING": {"scope": str, "name": str, "sheet_count": int},
    "SHEET_CATALOG_COLUMN_DUPLICATE": {"header": str},
    "SHEET_CATALOG_TEMPLATE_LIMIT": {"kind": str, "limit": int, "actual": int},
    "SHEET_CATALOG_TEMPLATE_CONFLICT": {
        "expected_revision": int,
        "current_revision": int,
    },
    "SHEET_CATALOG_XLSX_INVALID": {"check": str},
}

#: SPEC-DM-012 §11 固定的用户结果（诊断展示语义，不作为界面文案源）。
SHEET_CATALOG_USER_RESULTS: dict[str, str] = {
    "SHEET_CATALOG_EXPRESSION_INVALID": "定位到具体列和字符位置，禁止预览与导出",
    "SHEET_CATALOG_FIELD_UNDEFINED": "显示缺少的作用域和属性名，禁止导出",
    "SHEET_CATALOG_VALUE_MISSING": "显示字段和受影响行数，允许导出",
    "SHEET_CATALOG_COLUMN_DUPLICATE": "定位重复列名，禁止保存、预览和导出",
    "SHEET_CATALOG_TEMPLATE_LIMIT": "显示具体限制，不截断数据",
    "SHEET_CATALOG_TEMPLATE_CONFLICT": "保留本地编辑，刷新模板修订后允许另存或重试",
    "SHEET_CATALOG_XLSX_INVALID": "不保存候选文件，不登记成功 Artifact",
}

#: 阻断语义：``VALUE_MISSING`` 是允许执行的 warning，其余均为阻断。
SHEET_CATALOG_BLOCKING: dict[str, bool] = {
    "SHEET_CATALOG_EXPRESSION_INVALID": True,
    "SHEET_CATALOG_FIELD_UNDEFINED": True,
    "SHEET_CATALOG_VALUE_MISSING": False,
    "SHEET_CATALOG_COLUMN_DUPLICATE": True,
    "SHEET_CATALOG_TEMPLATE_LIMIT": True,
    "SHEET_CATALOG_TEMPLATE_CONFLICT": True,
    "SHEET_CATALOG_XLSX_INVALID": True,
}

#: 迁移窗口兼容中文文本（与 ``message_catalog.py`` 同期语义，不按语言选择）。
_DEFAULT_MESSAGES: dict[str, str] = {
    "SHEET_CATALOG_EXPRESSION_INVALID": "表达式语法无效（位置 {source_start}）",
    "SHEET_CATALOG_FIELD_UNDEFINED": "表达式引用了未定义的字段：[{scope}] {name}",
    "SHEET_CATALOG_VALUE_MISSING": "字段值为空：[{scope}] {name}（涉及 {sheet_count} 张图纸）",
    "SHEET_CATALOG_COLUMN_DUPLICATE": "名称重复：{header}",
    "SHEET_CATALOG_TEMPLATE_LIMIT": "超出模板限制 {kind}：{actual}/{limit}",
    "SHEET_CATALOG_TEMPLATE_CONFLICT": "模板已被其他保存更新（本地 r{current_revision}/服务端 r{expected_revision}）",
    "SHEET_CATALOG_XLSX_INVALID": "候选文件校验未通过：{check}",
}


class SheetCatalogError(Exception):
    """图纸目录结构化错误：``code``/``message_key``/``params`` 全部稳定。

    不用 ``@dataclass``：异常基类需要解释器写入 ``__traceback__`` 等属性，
    frozen/slots 组合会破坏 ``raise``/``except`` 匹配。
    """

    def __init__(
        self,
        code: str,
        message_key: str,
        params: dict[str, ParamValue],
        message: str,
        blocking: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message_key = message_key
        self.params = params
        self.message = message
        self.blocking = blocking


class _SafeParams(dict):
    """缺参时占位为空串：工厂允许白名单的子集（分阶段补齐上下文参数）。"""

    def __missing__(self, key: str) -> str:
        return ""


def _format_message(code: str, params: dict[str, ParamValue]) -> str:
    return _DEFAULT_MESSAGES[code].format_map(_SafeParams(params))


def sheet_catalog_error(
    code: SheetCatalogErrorCode | str,
    params: dict[str, ParamValue] | None = None,
    message: str | None = None,
) -> SheetCatalogError:
    """错误工厂：只接受词汇表登记的 code 与参数白名单内的结构化参数。"""
    schema = SHEET_CATALOG_PARAM_SCHEMAS.get(code)
    if schema is None:
        raise ValueError(f"SHEET_CATALOG_ERROR_CODE_INVALID: {code!r}")
    checked: dict[str, ParamValue] = dict(params or {})
    for key, value in checked.items():
        expected = schema.get(key)
        if expected is None:
            raise ValueError(
                f"SHEET_CATALOG_ERROR_PARAM_INVALID: {code} 不接受参数 {key!r}"
            )
        if expected is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"SHEET_CATALOG_ERROR_PARAM_TYPE_INVALID: {code}.{key} 需要 int"
                )
        elif expected is str:
            if not isinstance(value, str):
                raise ValueError(
                    f"SHEET_CATALOG_ERROR_PARAM_TYPE_INVALID: {code}.{key} 需要 str"
                )
        else:  # 防御：词汇表中出现新的参数类型时显式失败。
            raise ValueError(
                f"SHEET_CATALOG_ERROR_PARAM_SCHEMA_INVALID: {code}.{key}"
            )
    return SheetCatalogError(
        code=code,
        message_key=SHEET_CATALOG_MESSAGE_KEYS[code],
        params=checked,
        message=message or _format_message(code, checked),
        blocking=SHEET_CATALOG_BLOCKING[code],
    )
