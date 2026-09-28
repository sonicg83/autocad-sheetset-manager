"""标准领域结构错误的共享定义。"""


class StandardSchemaError(Exception):
    """标准文档解析失败；消息以稳定错误码开头，如 ``STANDARD_ID_INVALID``。"""


def standard_error(code: str, detail: str) -> StandardSchemaError:
    """创建携带稳定错误码的标准结构错误。"""
    return StandardSchemaError(f"{code}: {detail}")
