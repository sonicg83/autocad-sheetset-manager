"""扩展设置值对象与 Provider 契约（PLAN-DM-025 Task 1 / ARCH-DM-006 §8、§11）。

这里只定义宿主与扩展共享的稳定语义：冻结设置值、规范内容摘要、不可变设置快照
与 :class:`ExtensionSettingsProvider` 协议。默认值、字段类型与约束、校验、迁移
与解析的唯一权威是 Provider（其字段元数据即 :class:`SettingsFieldSpec`）；持久层
只按 ``extension_id`` 保存用户显式配置，不保存解析后的默认值。

清单里的设置声明（:class:`SettingsContribution` 及其 :class:`SettingsFieldDefinition`）
只描述可发现性、顺序与 i18n key，不重复类型、默认值或业务约束；宿主在调用点把
Provider 的字段元数据与清单的呈现合并（ARCH-DM-006 §8.2）。摘要仅以 SHA-256
十六进制串外泄，日志、错误与任务记录不得写入完整设置值。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

#: 冻结后的 JSON 取值：Mapping 只读、数组转 tuple、标量原样。
type FrozenJson = (
    Mapping[str, FrozenJson] | tuple[FrozenJson, ...] | str | int | float | bool | None
)


@dataclass(frozen=True, slots=True)
class SettingsFieldDefinition:
    """``generated`` 呈现的字段元数据；宿主据此合并 i18n 文案与顺序。

    只含呈现信息：类型、默认值与约束由 Provider 的字段定义解释，不在清单重复。
    """

    key: str
    label_key: str
    description_key: str | None
    order: int


#: 设置字段的控件类型；与设置中心的 ``SettingsItemModel.control`` 同一词表。
type SettingsFieldControl = Literal["boolean", "int", "number", "string", "enum"]


@dataclass(frozen=True, slots=True)
class SettingsFieldSpec:
    """Provider 一侧的字段元数据：控件类型、默认值与约束（ARCH-DM-006 §4.2、§8.2）。

    清单不重复这些语义，因此宿主解释字段时只认 Provider 的声明：把 ``default``
    作为默认值来源，按 ``nullable``/``min_value``/``max_value``/``options``/
    ``max_length`` 渲染与校验，再叠加清单 :class:`SettingsFieldDefinition` 的
    顺序与 i18n key。Provider 无法解释清单里的字段时只隔离该扩展设置并产生诊断
    （§8.1），不阻止宿主启动。
    """

    key: str
    control: SettingsFieldControl
    default: object
    nullable: bool = False
    min_value: int | float | None = None
    max_value: int | float | None = None
    options: tuple[str, ...] = ()
    max_length: int | None = None


@dataclass(frozen=True, slots=True)
class SettingsContribution:
    """清单的设置呈现声明（ARCH-DM-006 §4.2）。

    ``generated`` 由宿主按 ``fields`` 生成表单；``custom`` 由宿主编译期白名单里的
    专属组件按 ``route_key`` 呈现。合法组合由 :mod:`dst_manager.extensions.manifest`
    严格校验，本值对象只承载已校验结果。
    """

    presentation: Literal["generated", "custom"]
    route_key: str | None = None
    fields: tuple[SettingsFieldDefinition, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtensionSettingsSnapshot:
    """一次动作调用冻结的有效设置（ARCH-DM-006 §11）。

    ``value`` 是 Provider 解析后的有效配置（含代码默认值），``revision`` 与
    ``digest`` 随预览绑定；同一调用全程复用该快照，用户保存只影响后续调用。
    """

    extension_id: str
    schema_version: int
    revision: int
    value: Mapping[str, FrozenJson]
    digest: str


class ExtensionSettingsProvider(Protocol):
    """扩展设置语义的唯一权威：默认值、迁移、校验规范化与解析。

    Provider 不依赖基础设施：宿主把持久值与调用点交给它，它只返回纯 JSON 结构。
    """

    extension_id: str
    schema_version: int
    field_definitions: tuple[SettingsFieldSpec, ...]

    def default_value(self) -> dict[str, object]: ...

    def migrate(
        self, stored_schema_version: int, value: dict[str, object]
    ) -> dict[str, object]: ...

    def validate_and_normalize(self, value: dict[str, object]) -> dict[str, object]: ...

    def resolve(self, value: dict[str, object]) -> dict[str, object]: ...


def freeze_json(value: object) -> FrozenJson:
    """递归冻结 JSON 取值：Mapping → 只读 Mapping，list/tuple → tuple，标量原样。

    冻结结果不与入参共享可变容器，调用方之后修改原 dict/list 不会改变已冻结值。
    只读 Mapping（``MappingProxyType``）本身不可哈希，需要哈希时取其中的 tuple
    与标量；数组转 tuple 后，纯标量数组可直接作为键或放进集合。

    非 JSON 取值（``set``、日期、任意对象等）在此处直接抛 :class:`TypeError`，
    失败点即冻结本身，而不是推迟到 :func:`settings_digest` 的序列化。
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(
        f"设置值必须是 JSON 取值（Mapping/list/tuple/str/int/float/bool/null），"
        f"收到 {type(value).__name__}"
    )


def _plain_json(value: FrozenJson) -> object:
    """把冻结结构还原为 JSON 可序列化结构（只用于规范序列化，不对外暴露）。"""
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def settings_digest(
    extension_id: str, schema_version: int, value: Mapping[str, object]
) -> str:
    """计算设置摘要：冻结值的规范 JSON（键排序、紧凑分隔符、保留非 ASCII）的 SHA-256。

    摘要绑定 ``extension_id`` 与 ``schema_version``，因此取值相同的不同扩展或不同
    Schema 版本绝不共享摘要。全程使用 sha256 与显式规范序列化，不依赖 ``hash()``
    或 ``id()``，跨进程与跨启动稳定。
    """
    payload = json.dumps(
        {
            "extension_id": extension_id,
            "schema_version": schema_version,
            "value": _plain_json(freeze_json(value)),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
