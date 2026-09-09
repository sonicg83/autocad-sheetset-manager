"""统一用户可见错误负载契约（PLAN-DM-021 Task 9 / ARCH-DM-005 §6.2 / I18N-11）。

``responses.py`` 已达容量软上限（AGENTS.md 代码组织契约），错误契约按计划
授权独立成模块。``message`` 仅是迁移窗口兼容文本；已知错误的用户呈现一律走
``message_key`` + ``params``，未知错误的原始文本只作诊断详情。
"""

from pydantic import BaseModel, ConfigDict, Field

from dst_manager.settings.errors import ParamValue

__all__ = ["ErrorPayloadModel", "ParamValue"]


class ErrorPayloadModel(BaseModel):
    """API/Shell 已知错误统一负载：``code`` 稳定、``message_key`` 稳定、
    ``params`` 只携带结构化插值参数（禁止本地化 label 或完整句子）、
    ``message`` 为迁移期兼容文本。未知 code 不携带 ``message_key``。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    message_key: str | None = None
    params: dict[str, ParamValue] = Field(default_factory=dict)
    message: str
