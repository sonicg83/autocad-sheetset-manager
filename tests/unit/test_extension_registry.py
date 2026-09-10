# 内置扩展生命周期注册表单元测试（PLAN-DM-020 Task 1 / ARCH-DM-006 §5）
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from dst_manager.extensions.builtin.index import BUILTIN_EXTENSION_INDEX
from dst_manager.extensions.contracts import BuiltinExtensionEntry, Extension
from dst_manager.extensions.manifest import XLSX_MEDIA_TYPE
from dst_manager.extensions.registry import ExtensionRegistry, ExtensionRegistryError

XLSX_ACTION = {
    "action_id": "export-xlsx",
    "output_kind": "xlsx",
    "media_type": XLSX_MEDIA_TYPE,
}


class RecordingExtension:
    """测试替身：记录启停次数；可注入停止失败。"""

    def __init__(self, stop_error: Exception | None = None) -> None:
        self.started = 0
        self.stopped = 0
        self._stop_error = stop_error

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1
        if self._stop_error is not None:
            raise self._stop_error


def write_manifest(path: Path, **overrides) -> str:
    data = {
        "extension_id": "test.a",
        "version": "0.1.0",
        "extension_type": "builtin",
        "host_contract": 1,
        "enabled_by_default": True,
        "name_key": "extensions.test.name",
        "description_key": "extensions.test.description",
        "required_capabilities": [],
        "permissions": [],
        "ui_contributions": [],
        "actions": [],
        "settings_schema": 1,
    }
    data.update(overrides)
    path.mkdir(parents=True, exist_ok=True)
    manifest = path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(manifest)


def entry(manifest_resource: str, factory: Callable[[], Extension]) -> BuiltinExtensionEntry:
    return BuiltinExtensionEntry(manifest_resource=manifest_resource, factory=factory)


def test_real_builtin_index_discovers_as_available() -> None:
    # Task 6 已接线能力 broker：快照能力真实可发放，内置扩展发现即可用
    registry = ExtensionRegistry()
    registry.discover(BUILTIN_EXTENSION_INDEX)
    descriptors = registry.list()
    assert [d.manifest.extension_id for d in descriptors] == ["dst-manager.sheet-catalog"]
    assert descriptors[0].manifest.version == "0.1.0"
    assert descriptors[0].status == "AVAILABLE"
    assert descriptors[0].error_code is None
    with registry.invoke("dst-manager.sheet-catalog", "export-xlsx") as invocation:
        assert invocation.manifest.extension_id == "dst-manager.sheet-catalog"


def test_enabled_by_default_starts_and_serves_declared_actions(tmp_path: Path) -> None:
    resource = write_manifest(tmp_path, actions=[XLSX_ACTION])
    extension = RecordingExtension()
    registry = ExtensionRegistry()
    registry.discover([entry(resource, lambda: extension)])

    (descriptor,) = registry.list()
    assert descriptor.status == "AVAILABLE"
    assert descriptor.error_code is None
    assert extension.started == 1

    with registry.invoke("test.a", "export-xlsx") as invocation:
        assert invocation.extension is extension
        assert invocation.manifest.extension_id == "test.a"
        assert invocation.invocation_id

    with pytest.raises(ExtensionRegistryError) as excinfo, registry.invoke("test.a", "undeclared"):
        pass
    assert excinfo.value.code == "EXTENSION_ACTION_NOT_FOUND"


def test_disabled_by_default_stays_disabled_until_enabled(tmp_path: Path) -> None:
    resource = write_manifest(tmp_path, enabled_by_default=False, actions=[XLSX_ACTION])
    extension = RecordingExtension()
    registry = ExtensionRegistry()
    registry.discover([entry(resource, lambda: extension)])

    (descriptor,) = registry.list()
    assert descriptor.status == "DISABLED"
    with pytest.raises(ExtensionRegistryError) as excinfo, registry.invoke("test.a", "export-xlsx"):
        pass
    assert excinfo.value.code == "EXTENSION_DISABLED"

    enabled = registry.set_enabled("test.a", True)
    assert enabled.status == "AVAILABLE"
    with registry.invoke("test.a", "export-xlsx"):
        pass

    disabled = registry.set_enabled("test.a", False)
    assert disabled.status == "STOPPED"
    assert extension.stopped == 1
    with pytest.raises(ExtensionRegistryError) as excinfo, registry.invoke("test.a", "export-xlsx"):
        pass
    assert excinfo.value.code == "EXTENSION_DISABLED"

    # STOPPED → STARTING：停用后可再次启用
    assert registry.set_enabled("test.a", True).status == "AVAILABLE"


def test_unknown_extension_reports_not_found() -> None:
    registry = ExtensionRegistry()
    with pytest.raises(ExtensionRegistryError) as excinfo, registry.invoke("missing", "noop"):
        pass
    assert excinfo.value.code == "EXTENSION_NOT_FOUND"
    with pytest.raises(ExtensionRegistryError) as excinfo:
        registry.set_enabled("missing", True)
    assert excinfo.value.code == "EXTENSION_NOT_FOUND"


def test_host_contract_mismatch_is_incompatible(tmp_path: Path) -> None:
    resource = write_manifest(tmp_path, host_contract=2)
    registry = ExtensionRegistry()
    registry.discover([entry(resource, RecordingExtension)])
    (descriptor,) = registry.list()
    assert descriptor.status == "INCOMPATIBLE"
    assert descriptor.error_code == "EXTENSION_HOST_CONTRACT_MISMATCH"
    with pytest.raises(ExtensionRegistryError) as excinfo:
        registry.set_enabled("test.a", True)
    assert excinfo.value.code == "EXTENSION_INCOMPATIBLE"


def test_unknown_capability_is_incompatible(tmp_path: Path) -> None:
    resource = write_manifest(tmp_path, required_capabilities=["made.up.capability"])
    registry = ExtensionRegistry()
    registry.discover([entry(resource, RecordingExtension)])
    (descriptor,) = registry.list()
    assert descriptor.status == "INCOMPATIBLE"
    assert descriptor.error_code == "EXTENSION_CAPABILITY_UNKNOWN"


def test_factory_failure_is_isolated_and_marks_extension_failed(tmp_path: Path) -> None:
    broken = write_manifest(tmp_path / "broken", extension_id="test.broken")

    def failing_factory() -> Extension:
        raise RuntimeError("工厂启动失败")

    healthy = write_manifest(tmp_path / "healthy", extension_id="test.healthy")
    healthy_extension = RecordingExtension()
    registry = ExtensionRegistry()
    registry.discover(
        [
            entry(broken, failing_factory),
            entry(healthy, lambda: healthy_extension),
        ]
    )

    by_id = {d.manifest.extension_id: d for d in registry.list()}
    assert by_id["test.broken"].status == "FAILED"
    assert by_id["test.broken"].error_code == "EXTENSION_START_FAILED"
    assert by_id["test.healthy"].status == "AVAILABLE"


def test_manifest_load_failure_is_isolated(tmp_path: Path) -> None:
    healthy = write_manifest(tmp_path / "healthy", extension_id="test.healthy")
    healthy_extension = RecordingExtension()
    registry = ExtensionRegistry()
    registry.discover(
        [
            entry(str(tmp_path / "missing" / "manifest.yaml"), RecordingExtension),
            entry(healthy, lambda: healthy_extension),
        ]
    )

    statuses = {d.manifest.extension_id: d.status for d in registry.list()}
    # Ruling-7（PLAN-DM-020 Task 3 fix round 1）：占位 ID 不得携带服务端路径，
    # 改为不含路径的稳定标识 builtin.invalid-<资源名 slug>。
    assert statuses["builtin.invalid-manifest"] == "FAILED"
    assert statuses["test.healthy"] == "AVAILABLE"


def test_duplicate_extension_id_keeps_first_discovered(tmp_path: Path) -> None:
    first = write_manifest(tmp_path / "first", extension_id="test.dup")
    second = write_manifest(tmp_path / "second", extension_id="test.dup")
    first_extension = RecordingExtension()
    registry = ExtensionRegistry()
    registry.discover(
        [
            entry(first, lambda: first_extension),
            entry(second, RecordingExtension),
        ]
    )
    assert [d.manifest.extension_id for d in registry.list()] == ["test.dup"]
    assert registry.list()[0].status == "AVAILABLE"


def test_disable_rejects_new_calls_then_drains_active_call(tmp_path: Path) -> None:
    resource = write_manifest(tmp_path, actions=[XLSX_ACTION])
    extension = RecordingExtension()
    registry = ExtensionRegistry()
    registry.discover([entry(resource, lambda: extension)])

    entered = threading.Event()
    release = threading.Event()
    worker_done = threading.Event()

    def worker() -> None:
        try:
            with registry.invoke("test.a", "export-xlsx"):
                entered.set()
                release.wait(timeout=5)
        finally:
            worker_done.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=5)

    results: list[object] = []

    def disabler() -> None:
        results.append(registry.set_enabled("test.a", False))

    disabler_thread = threading.Thread(target=disabler)
    disabler_thread.start()

    # 停用先行生效：活动调用排空之前，新调用一律被拒绝
    deadline = time.monotonic() + 5
    rejected = False
    while time.monotonic() < deadline:
        try:
            with registry.invoke("test.a", "export-xlsx"):
                pass
        except ExtensionRegistryError as exc:
            assert exc.code == "EXTENSION_DISABLED"
            rejected = True
            break
        time.sleep(0.01)
    assert rejected, "停用未先拒绝新调用"

    # 排空阶段：活动同步调用尚未结束，停用未返回
    assert disabler_thread.is_alive(), "排空未等待已进入的同步调用"

    release.set()
    thread.join(timeout=5)
    disabler_thread.join(timeout=5)
    assert worker_done.is_set()

    descriptor = registry.list()[0]
    assert descriptor.status == "STOPPED"
    assert extension.stopped == 1


def test_stop_failure_enters_failed(tmp_path: Path) -> None:
    resource = write_manifest(tmp_path, actions=[XLSX_ACTION])
    extension = RecordingExtension(stop_error=RuntimeError("清理失败"))
    registry = ExtensionRegistry()
    registry.discover([entry(resource, lambda: extension)])

    descriptor = registry.set_enabled("test.a", False)
    assert descriptor.status == "FAILED"
    assert descriptor.error_code == "EXTENSION_STOP_FAILED"

    with pytest.raises(ExtensionRegistryError), registry.invoke("test.a", "export-xlsx"):
        pass
