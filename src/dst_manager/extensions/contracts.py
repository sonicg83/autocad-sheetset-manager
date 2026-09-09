"""内置扩展宿主契约（PLAN-DM-020 Task 1 / ARCH-DM-006 §4、§5）。

这里只存放跨模块共享的稳定值对象与协议；清单 YAML 的严格校验在
:mod:`dst_manager.extensions.manifest`，生命周期状态机在
:mod:`dst_manager.extensions.registry`。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

HOST_CONTRACT = 1

#: 首期唯一允许的候选成果 MIME；由宿主映射到固定保存对话框与验证器，
#: 不能由前端或扩展提交任意过滤器、后缀或 MIME 类型。
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True, slots=True)
class UiContribution:
    contribution_id: str
    kind: Literal["workspace_page"]
    route_key: str


class Extension(Protocol):
    """内置扩展必须提供的最小生命周期接口。"""

    def start(self) -> None: ...
    def stop(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ExtensionActionManifest:
    action_id: str
    output_kind: Literal["xlsx"] | None
    media_type: str | None


@dataclass(frozen=True, slots=True)
class ExtensionManifest:
    extension_id: str
    version: str
    host_contract: int
    enabled_by_default: bool
    name_key: str
    description_key: str
    required_capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    ui_contributions: tuple[UiContribution, ...]
    actions: tuple[ExtensionActionManifest, ...]
    settings_schema: int


@dataclass(frozen=True, slots=True)
class BuiltinExtensionEntry:
    """固定索引条目：直接引用随包清单资源与已审核工厂函数。"""

    manifest_resource: str
    factory: Callable[[], Extension]


@dataclass(frozen=True, slots=True)
class ExtensionDescriptor:
    manifest: ExtensionManifest
    status: Literal[
        "DISCOVERED",
        "DISABLED",
        "STARTING",
        "AVAILABLE",
        "WAITING_DEPENDENCY",
        "INCOMPATIBLE",
        "FAILED",
        "STOPPING",
        "STOPPED",
    ]
    error_code: str | None


@dataclass(frozen=True, slots=True)
class ExtensionInvocation:
    invocation_id: str
    extension: Extension
    manifest: ExtensionManifest
