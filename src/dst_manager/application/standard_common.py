"""标准应用层共享的错误映射与诊断序列化。"""

from dst_manager.application.errors import ApplicationError
from dst_manager.domain.standards import StandardDiagnostic

_STORE_STATUS = {
    "STANDARD_ID_EXISTS": 409,
    "STANDARD_NAME_CONFLICT": 409,
    "STANDARD_ID_NOT_FOUND": 404,
    "STANDARD_VERSION_EXISTS": 409,
    "STANDARD_VERSION_LIMIT_REACHED": 409,
    "STANDARD_DRAFT_EXISTS": 409,
    "STANDARD_VERSION_NOT_FOUND": 404,
    "STANDARD_DRAFT_NOT_FOUND": 404,
}


def store_error(exc: Exception) -> ApplicationError:
    """标准库/Schema 错误码（消息前缀）转 HTTP 稳定错误。"""
    code = str(exc).split(":", 1)[0]
    return ApplicationError(code, str(exc), _STORE_STATUS.get(code, 422))


def publish_diagnostic_payload(diagnostic: StandardDiagnostic) -> dict[str, object]:
    """发布检查诊断模型：错误码、严重级与可定位信息。"""
    return {
        "code": diagnostic.code,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "property_id": diagnostic.property_id,
        "segment_index": diagnostic.segment_index,
    }
