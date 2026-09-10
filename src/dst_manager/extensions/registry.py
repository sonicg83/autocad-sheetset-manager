"""内置扩展生命周期注册表（PLAN-DM-020 Task 1 / ARCH-DM-006 §5、§11）。

职责：发现固定索引条目、按清单分类兼容性、启停扩展并维护活动同步调用
计数。规则：

- 逐条捕获发现/启动/停止失败，只把对应扩展置为 ``FAILED`` 等不可用状态，
  绝不影响其他扩展或宿主启动（故障隔离）；
- 已知但当前不可用的必需能力 → ``WAITING_DEPENDENCY``；未知能力或
  ``host_contract`` 不匹配 → ``INCOMPATIBLE``；
- 停用先置 ``draining`` 拒绝新调用，再等待已进入的同步调用排空，最后调用
  ``stop()``；清理失败进入 ``FAILED``，不伪装成已停止；
- 首期扩展不得注册后台计时器、外部进程或网络连接；生命周期只跟踪页面
  贡献、动作处理器和活动调用计数（后台资源注册被拒绝）。
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from dst_manager.extensions.contracts import (
    HOST_CONTRACT,
    BuiltinExtensionEntry,
    Extension,
    ExtensionDescriptor,
    ExtensionInvocation,
    ExtensionManifest,
)
from dst_manager.extensions.manifest import load_manifest

logger = logging.getLogger(__name__)

def _placeholder_id(resource: str) -> str:
    """清单不可读条目的稳定占位 ID：只保留资源名末段并清洗为安全字符。

    前缀 ``builtin.invalid-`` 保证不与真实扩展 ID 冲突；同名坏清单保留先
    发现者（与重复扩展 ID 的策略一致）。
    """
    name = re.split(r"[/\\]", resource)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")
    return f"builtin.invalid-{slug or 'unknown'}"


_ExtensionStatus = Literal[
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

#: 宿主已认识的能力词汇表（ARCH-DM-006 §6）。
KNOWN_CAPABILITIES: frozenset[str] = frozenset({"workspace.snapshot.read.v1"})

#: 当前真正可发放的能力（Task 6 已接入 CapabilityBroker + 只读 workspace
#: reader，``workspace.snapshot.read.v1`` 由宿主真实提供）。
AVAILABLE_CAPABILITIES: frozenset[str] = frozenset({"workspace.snapshot.read.v1"})


class ExtensionRegistryError(RuntimeError):
    """注册表拒绝请求；``code`` 与 ARCH-DM-006 §12 平台错误码对齐。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class _Record:
    manifest: ExtensionManifest
    factory: Callable[[], Extension] | None
    enabled: bool
    status: _ExtensionStatus
    error_code: str | None
    extension: Extension | None = None
    active_calls: int = 0
    draining: bool = False


class ExtensionRegistry:
    """内置扩展的发现、启停与同步调用生命周期（线程安全）。"""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._records: dict[str, _Record] = {}

    # ------------------------------------------------------------------ 发现

    def discover(self, entries: Sequence[BuiltinExtensionEntry]) -> None:
        """逐条发现内置扩展；单条失败只生成该条目的稳定诊断。"""
        for entry in entries:
            try:
                manifest = load_manifest(entry.manifest_resource)
            except Exception as exc:  # noqa: BLE001 - 故障隔离：任何清单失败都不得外溢
                logger.warning(
                    "EXTENSION_MANIFEST_INVALID resource=%s error=%s",
                    entry.manifest_resource,
                    exc,
                )
                self._record_placeholder(entry.manifest_resource)
                continue
            with self._condition:
                if manifest.extension_id in self._records:
                    # 重复 ID：保留先发现者，后到者只留下稳定诊断。
                    logger.warning(
                        "EXTENSION_ID_DUPLICATED extension_id=%s resource=%s",
                        manifest.extension_id,
                        entry.manifest_resource,
                    )
                    continue
                status, error_code = self._classify(manifest)
                record = _Record(
                    manifest=manifest,
                    factory=entry.factory,
                    enabled=manifest.enabled_by_default,
                    status=status or "DISCOVERED",
                    error_code=error_code,
                )
                self._records[manifest.extension_id] = record
                if error_code is None:
                    if record.enabled:
                        self._start_locked(record)
                    else:
                        record.status = "DISABLED"

    # ------------------------------------------------------------------ 查询

    def list(self) -> tuple[ExtensionDescriptor, ...]:
        with self._condition:
            return tuple(self._descriptor(record) for record in self._records.values())

    # ------------------------------------------------------------------ 启停

    def set_enabled(self, extension_id: str, enabled: bool) -> ExtensionDescriptor:
        with self._condition:
            record = self._records.get(extension_id)
            if record is None:
                raise ExtensionRegistryError(
                    "EXTENSION_NOT_FOUND", f"扩展未登记：{extension_id}"
                )
            if record.draining:
                raise ExtensionRegistryError(
                    "EXTENSION_DISABLED", f"扩展正在停用：{extension_id}"
                )
        if enabled:
            return self._enable(record)
        return self._disable(record)

    def _enable(self, record: _Record) -> ExtensionDescriptor:
        with self._condition:
            if record.status == "AVAILABLE" and record.extension is not None:
                # 重复启用幂等：不重复创建实例。
                return self._descriptor(record)
            record.enabled = True
            status, error_code = self._classify(record.manifest)
            record.status, record.error_code = status or record.status, error_code
            if error_code is not None:
                # ARCH §5：启用前先校验宿主契约与必需能力；不通过则拒绝启用。
                # 抛出 §12 平台错误码；描述符保留更具体的稳定诊断。
                raise ExtensionRegistryError(
                    self._unavailable_code(record.status, False),
                    f"扩展无法启用：{record.manifest.extension_id}（{error_code}）",
                )
            self._start_locked(record)
            return self._descriptor(record)

    def _disable(self, record: _Record) -> ExtensionDescriptor:
        with self._condition:
            record.enabled = False
            # 1) 先拒绝新调用：invoke 在 draining 时立即失败。
            record.draining = True
            # 2) 再等待已进入的同步调用结束（wait_for 期间释放锁）。
            self._condition.wait_for(lambda: record.active_calls == 0)
            was_running = record.extension is not None
            record.draining = False
            if was_running:
                record.status = "STOPPING"
                extension, record.extension = record.extension, None
            else:
                extension = None
        if extension is None:
            return self._descriptor(record)
        # 3) 锁外释放生命周期资源；清理失败进入 FAILED。
        try:
            extension.stop()
        except Exception as exc:  # noqa: BLE001 - 停用失败必须可见而非伪装成功
            with self._condition:
                record.status = "FAILED"
                record.error_code = "EXTENSION_STOP_FAILED"
            logger.warning(
                "EXTENSION_STOP_FAILED extension_id=%s error=%s",
                record.manifest.extension_id,
                exc,
            )
        else:
            with self._condition:
                record.status = "STOPPED"
                record.error_code = None
        return self._descriptor(record)

    # ------------------------------------------------------------------ 调用

    @contextmanager
    def invoke(
        self, extension_id: str, action_id: str
    ) -> Iterator[ExtensionInvocation]:
        with self._condition:
            record = self._records.get(extension_id)
            if record is None:
                raise ExtensionRegistryError(
                    "EXTENSION_NOT_FOUND", f"扩展未登记：{extension_id}"
                )
            if record.draining or record.status != "AVAILABLE":
                raise ExtensionRegistryError(
                    self._unavailable_code(record.status, record.draining),
                    f"扩展当前不可调用：{extension_id}（{record.status}）",
                )
            if all(action.action_id != action_id for action in record.manifest.actions):
                raise ExtensionRegistryError(
                    "EXTENSION_ACTION_NOT_FOUND",
                    f"扩展 {extension_id} 未声明动作：{action_id}",
                )
            extension = record.extension
            assert extension is not None  # AVAILABLE 状态下实例必然存在
            record.active_calls += 1
        try:
            yield ExtensionInvocation(
                invocation_id=uuid.uuid4().hex,
                extension=extension,
                manifest=record.manifest,
            )
        finally:
            with self._condition:
                record.active_calls -= 1
                self._condition.notify_all()

    # ------------------------------------------------------------------ 内部

    @staticmethod
    def _classify(
        manifest: ExtensionManifest,
    ) -> tuple[_ExtensionStatus | None, str | None]:
        if manifest.host_contract != HOST_CONTRACT:
            return ("INCOMPATIBLE", "EXTENSION_HOST_CONTRACT_MISMATCH")
        unknown = [
            capability
            for capability in manifest.required_capabilities
            if capability not in KNOWN_CAPABILITIES
        ]
        if unknown:
            return ("INCOMPATIBLE", "EXTENSION_CAPABILITY_UNKNOWN")
        missing = [
            capability
            for capability in manifest.required_capabilities
            if capability not in AVAILABLE_CAPABILITIES
        ]
        if missing:
            return ("WAITING_DEPENDENCY", "EXTENSION_CAPABILITY_UNAVAILABLE")
        return (None, None)

    def _start_locked(self, record: _Record) -> None:
        """校验通过后创建实例并启动；调用方必须持有 ``_condition``。"""
        assert record.factory is not None
        record.status = "STARTING"
        record.error_code = None
        try:
            extension = record.factory()
            extension.start()
        except Exception as exc:  # noqa: BLE001 - 工厂失败只影响该扩展
            record.extension = None
            record.status = "FAILED"
            record.error_code = "EXTENSION_START_FAILED"
            logger.warning(
                "EXTENSION_START_FAILED extension_id=%s error=%s",
                record.manifest.extension_id,
                exc,
            )
            return
        record.extension = extension
        record.status = "AVAILABLE"

    def _record_placeholder(self, resource: str) -> None:
        """清单不可读时的占位清单：仅承载稳定诊断，不可启用、不可调用。

        占位 ID 用不含文件系统路径的稳定标识（:func:`_placeholder_id`，Ruling-7）：
        该 ID 会原样进入 ``GET /api/extensions`` 摘要，绝不把服务端绝对路径
        暴露给客户端；原始资源串只留在服务端日志里。
        """
        placeholder_id = _placeholder_id(resource)
        with self._condition:
            if placeholder_id in self._records:
                # 重复占位 ID（如同名坏清单）：与业务扩展一致，保留先发现者。
                logger.warning(
                    "EXTENSION_ID_DUPLICATED extension_id=%s resource=%s",
                    placeholder_id,
                    resource,
                )
                return
            self._records[placeholder_id] = _Record(
                manifest=ExtensionManifest(
                    extension_id=placeholder_id,
                    version="0.0.0",
                    host_contract=HOST_CONTRACT,
                    enabled_by_default=False,
                    name_key="",
                    description_key="",
                    required_capabilities=(),
                    permissions=(),
                    ui_contributions=(),
                    actions=(),
                    settings_schema=0,
                ),
                factory=None,
                enabled=False,
                status="FAILED",
                error_code="EXTENSION_MANIFEST_INVALID",
            )

    @staticmethod
    def _unavailable_code(status: _ExtensionStatus, draining: bool) -> str:
        if draining or status in {"DISABLED", "STOPPING", "STOPPED", "STARTING", "DISCOVERED"}:
            return "EXTENSION_DISABLED"
        if status == "INCOMPATIBLE":
            return "EXTENSION_INCOMPATIBLE"
        # WAITING_DEPENDENCY 与 FAILED 都归入“能力当前不可用”族。
        return "EXTENSION_CAPABILITY_UNAVAILABLE"

    def _descriptor(self, record: _Record) -> ExtensionDescriptor:
        return ExtensionDescriptor(
            manifest=record.manifest,
            status=record.status,
            error_code=record.error_code,
        )
