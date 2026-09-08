"""设置中心与关于接口的请求/响应契约（PLAN-DM-019 设置中心任务 5）。

独立成文件的原因：``responses.py`` 已触及 500 行软上限，设置相关模型按计划
授权落在此处。请求模型沿用 ``ContractModel``（extra=forbid）严格校验。
"""

from typing import Literal

from pydantic import Field

from dst_manager.interfaces.contracts import ContractModel


class SettingsPutRequest(ContractModel):
    """PUT /api/settings 请求体：期望修订号 + 增改/清空集合。"""

    expected_revision: int
    set: dict[str, object] = Field(default_factory=dict)
    unset: list[str] = Field(default_factory=list)


class LicenseInfo(ContractModel):
    """许可证信息（spdx 标识 + 全文）。"""

    spdx: str
    text: str


class AboutResponse(ContractModel):
    """GET /api/about 响应：应用名、版本、许可证、主页与反馈入口。"""

    app_name: str
    version: str
    license: LicenseInfo
    homepage: str
    feedback_url: str


class EnumOptionModel(ContractModel):
    """枚举控件的单个选项。"""

    value: int
    text: str


class SettingsItemModel(ContractModel):
    """单个设置项：展示元数据 + 当前值 + 来源标注。

    ``nullable``/``file_filter`` 仅 path 控件返回；``options`` 仅 enum 控件；
    ``min``/``max`` 仅带 ge/le 约束的 int 控件。
    """

    key: str
    label: str
    category: str
    control: str
    value: bool | int | str | None
    source: Literal["default", "env", "file"]
    has_file_override: bool
    nullable: bool | None = None
    file_filter: str | None = None
    options: list[EnumOptionModel] | None = None
    min: int | None = None
    max: int | None = None


class SettingsResponse(ContractModel):
    """GET/PUT /api/settings 响应：快照 + 逐项来源。

    ``schema_blocked`` 为 True 时前端进入只读降级（schema 过新/过旧）。
    """

    schema_version: Literal[1]
    config_revision: int
    items: list[SettingsItemModel]
    diagnostics: list[str]
    schema_blocked: bool
