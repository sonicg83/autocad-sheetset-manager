"""统一错误响应负载（SPEC-DB-001 §11）：code / message / field / recovery_action / details。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = ["REQUEST_INVALID", "ErrorPayloadModel", "error_payload"]

REQUEST_INVALID = "REQUEST_INVALID"


class ErrorPayloadModel(BaseModel):
    """所有非 2xx 响应的统一负载；``code`` 只使用 §11 固定错误码。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    field: str | None = None
    recovery_action: str
    details: dict[str, Any] | None = None


def error_payload(
    code: str,
    message: str,
    *,
    recovery_action: str,
    field: str | None = None,
    details: dict[str, Any] | None = None,
) -> ErrorPayloadModel:
    return ErrorPayloadModel(
        code=code,
        message=message,
        field=field,
        recovery_action=recovery_action,
        details=details,
    )
