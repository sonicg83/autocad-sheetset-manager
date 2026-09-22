"""随包清单加载与严格校验（PLAN-DM-020 Task 1 / ARCH-DM-006 §4.2、§4.3）。

清单是数据文件，不是代码入口：Pydantic 模型 ``extra="forbid"``，禁止出现
``module``/``class_name``/``script``/``command``/``entry_point`` 等可执行入口
字段；固定索引（:mod:`dst_manager.extensions.builtin.index`）直接引用工厂
函数，绝不从 YAML 导入模块。任何校验失败都归一为 :class:`ManifestError`，
由注册表逐条隔离为该扩展的 ``FAILED`` 稳定诊断。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from dst_manager.extensions.contracts import (
    XLSX_MEDIA_TYPE,
    ExtensionActionManifest,
    ExtensionManifest,
    ExtensionProvidedCapability,
    UiContribution,
)
from dst_manager.extensions.settings import (
    SettingsContribution,
    SettingsFieldDefinition,
)

_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


class ManifestError(ValueError):
    """清单缺失、字段无效或声明越界；``code`` 固定为稳定诊断码。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "EXTENSION_MANIFEST_INVALID"


class _UiContributionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contribution_id: str = Field(min_length=1)
    kind: Literal["workspace_page"]
    route_key: str = Field(min_length=1)


class _ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1)
    output_kind: Literal["xlsx"] | None = None
    media_type: str | None = None

    @model_validator(mode="after")
    def _check_output_declaration(self) -> _ActionModel:
        if self.output_kind == "xlsx":
            if self.media_type != XLSX_MEDIA_TYPE:
                raise ValueError(
                    f"output_kind=xlsx 的动作必须声明固定 MIME {XLSX_MEDIA_TYPE}"
                )
        elif self.media_type is not None:
            raise ValueError("未声明 output_kind 的动作不能携带 media_type")
        return self


class _SettingsFieldModel(BaseModel):
    """``generated`` 字段声明：只描述呈现，不重复类型、默认值或业务约束。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    label_key: str = Field(min_length=1)
    #: 可缺省，但一旦声明就必须是稳定的非空 i18n key（与其他 ``*_key`` 同口径）。
    description_key: str | None = Field(default=None, min_length=1)
    order: int


class _SettingsContributionModel(BaseModel):
    """设置呈现声明（ARCH-DM-006 §4.2）：两类呈现不得混用负载。"""

    model_config = ConfigDict(extra="forbid")

    presentation: Literal["generated", "custom"]
    route_key: str | None = None
    fields: tuple[_SettingsFieldModel, ...] = ()

    @model_validator(mode="after")
    def _check_presentation_payload(self) -> _SettingsContributionModel:
        if self.presentation == "generated":
            if self.route_key is not None:
                raise ValueError("generated 呈现不能携带 route_key")
            if not self.fields:
                raise ValueError("generated 呈现必须声明非空 fields")
            keys = [field.key for field in self.fields]
            if len(keys) != len(set(keys)):
                raise ValueError("settings_contribution 字段 key 必须唯一")
        else:
            if not self.route_key:
                raise ValueError("custom 呈现必须声明 route_key")
            if self.fields:
                raise ValueError("custom 呈现不能携带 fields")
        return self


class _ProvidedCapabilityModel(BaseModel):
    """受信能力供给声明：能力 ID 与三段数字版本（PLAN-DM-035 Task 6）。"""

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=1)
    version: str

    @field_validator("version")
    @classmethod
    def _check_semver(cls, value: str) -> str:
        if _SEMVER_PATTERN.match(value) is None:
            raise ValueError(f"供给能力版本 {value!r} 不是合法 SemVer（MAJOR.MINOR.PATCH）")
        return value


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extension_id: str = Field(min_length=1)
    version: str
    extension_type: Literal["builtin"]
    host_contract: int
    enabled_by_default: bool
    name_key: str = Field(min_length=1)
    description_key: str = Field(min_length=1)
    required_capabilities: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    ui_contributions: tuple[_UiContributionModel, ...] = ()
    actions: tuple[_ActionModel, ...] = ()
    settings_schema: int
    settings_contribution: _SettingsContributionModel | None = None
    provided_capabilities: tuple[_ProvidedCapabilityModel, ...] = ()

    @field_validator("version")
    @classmethod
    def _check_semver(cls, value: str) -> str:
        if _SEMVER_PATTERN.match(value) is None:
            raise ValueError(f"版本 {value!r} 不是合法 SemVer（MAJOR.MINOR.PATCH）")
        return value

    @model_validator(mode="after")
    def _check_unique_action_ids(self) -> _ManifestModel:
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("动作 ID 必须唯一")
        return self


def _to_settings_contribution(
    model: _SettingsContributionModel | None,
) -> SettingsContribution | None:
    if model is None:
        return None
    return SettingsContribution(
        presentation=model.presentation,
        route_key=model.route_key,
        fields=tuple(
            SettingsFieldDefinition(
                key=field.key,
                label_key=field.label_key,
                description_key=field.description_key,
                order=field.order,
            )
            for field in model.fields
        ),
    )


def parse_manifest(data: Mapping[str, object]) -> ExtensionManifest:
    """把已解析的清单映射严格校验为冻结契约；失败统一抛 :class:`ManifestError`。"""
    try:
        model = _ManifestModel.model_validate(dict(data))
    except ValidationError as exc:
        raise ManifestError(f"清单校验失败：{exc}") from exc
    return ExtensionManifest(
        extension_id=model.extension_id,
        version=model.version,
        host_contract=model.host_contract,
        enabled_by_default=model.enabled_by_default,
        name_key=model.name_key,
        description_key=model.description_key,
        required_capabilities=model.required_capabilities,
        permissions=model.permissions,
        ui_contributions=tuple(
            UiContribution(
                contribution_id=contribution.contribution_id,
                kind=contribution.kind,
                route_key=contribution.route_key,
            )
            for contribution in model.ui_contributions
        ),
        actions=tuple(
            ExtensionActionManifest(
                action_id=action.action_id,
                output_kind=action.output_kind,
                media_type=action.media_type,
            )
            for action in model.actions
        ),
        settings_schema=model.settings_schema,
        settings_contribution=_to_settings_contribution(model.settings_contribution),
        provided_capabilities=tuple(
            ExtensionProvidedCapability(
                capability_id=capability.capability_id,
                version=capability.version,
            )
            for capability in model.provided_capabilities
        ),
    )


def load_manifest(resource: str) -> ExtensionManifest:
    """加载随包清单资源；``resource`` 也可以是测试用的绝对清单文件路径。"""
    path = Path(resource)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        package, _, filename = resource.rpartition("/")
        if not package:
            raise ManifestError(f"清单资源无效：{resource}")
        try:
            text = (
                (resources.files(package.replace("/", ".")) / filename)
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise ManifestError(f"清单资源不存在：{resource}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"清单不是合法 YAML：{resource}") from exc
    if not isinstance(data, Mapping):
        raise ManifestError(f"清单必须是键值映射：{resource}")
    return parse_manifest(data)
