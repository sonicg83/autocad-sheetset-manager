"""设置层结构化字段校验错误模型（PLAN-DM-021 Task 1 评审裁决）。

下沉到 settings 层的原因：``settings/runtime.py`` 产出 :class:`FieldErrorModel`
结构化错误，但 settings 层不得依赖 interfaces 层（否则 application 会经
settings 传递性依赖 interfaces）。模型约束与 ``interfaces/contracts.py`` 的
``ContractModel`` 一致（pydantic ``BaseModel`` + ``extra="forbid"``）；
``interfaces/settings_contracts.py`` 原样重导出，外部导入面
``from dst_manager.interfaces.settings_contracts import FieldErrorModel``
保持可用。本模块不按语言选择文本（ARCH-DM-005 §6.2）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["FieldErrorModel", "ParamValue"]

# params 白名单：只允许结构化插值参数（min/max/allowed_values 等），
# 禁止携带本地化 label 或完整句子
ParamValue = str | int | bool | list[str]


class FieldErrorModel(BaseModel):
    """设置逐字段校验错误对象（ARCH-DM-005 §6.2）。

    ``code`` 为稳定错误码，``message_key`` 为前端文案键，``params`` 只携带
    结构化插值参数（str/int/bool/list[str] 白名单，禁止本地化 label 或完整
    句子）；``message`` 是迁移期兼容中文文本，仅服务旧调用方。
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    message_key: str
    params: dict[str, ParamValue] = Field(default_factory=dict)
    message: str
