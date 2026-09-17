"""DST Builder 桌面壳单测（PLAN-DB-001 Task 11）。

覆盖：独立应用 ID/进程标题、%LOCALAPPDATA%/dst-builder 数据目录、单实例锁
（含与 DST Manager 的共存互不抢占）、动态回环端口、frozen/源码双路径资源发现
与无窗 stdio 重定向。壳窗口本身（pywebview/WebView2）不做真实 GUI 冒烟，
只对编排单元断言。
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pytest

from dst_builder.interfaces.desktop import (
    APP_DATA_DIR_NAME,
    APP_ID,
    APP_TITLE,
    acquire_instance_mutex,
    app_data_dir,
    is_frozen,
    log_dir,
    mutex_name,
    redirect_frozen_stdio,
    release_instance_mutex,
    resource_dir,
)
from dst_builder.interfaces.shell import create_shell_app, start_local_server

# ---------------------------------------------------------------------------
# 应用身份：与 DST Manager 共存的前提是全部身份要素互异
# ---------------------------------------------------------------------------


def test_builder_app_identity_is_independent():
    assert APP_ID == "dst-builder"
    assert APP_TITLE == "DST Builder"


@pytest.mark.parametrize(
    ("manager_module", "manager_attr"),
    [
        ("dst_manager.infrastructure.single_instance", "APP_WINDOW_TITLE"),
    ],
)
def test_builder_identity_differs_from_manager(manager_module, manager_attr):
    import importlib

    manager_value = getattr(importlib.import_module(manager_module), manager_attr)
    assert APP_TITLE != manager_value


def test_builder_data_dir_uses_localappdata_dst_builder(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"D:\user-appdata")
    assert app_data_dir() == Path(r"D:\user-appdata") / "dst-builder"
    assert APP_DATA_DIR_NAME == "dst-builder"


def test_builder_log_dir_lives_under_app_data_dir(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"D:\user-appdata")
    assert log_dir() == Path(r"D:\user-appdata") / "dst-builder" / "logs"


def test_builder_and_manager_data_dirs_are_disjoint(monkeypatch):
    from dst_manager.infrastructure.single_instance import instance_app_dir

    monkeypatch.setenv("LOCALAPPDATA", r"D:\user-appdata")
    assert app_data_dir() != instance_app_dir()
    assert APP_DATA_DIR_NAME != "dst-manager"


# ---------------------------------------------------------------------------
# 单实例锁：命名互斥量派生与双产品共存
# ---------------------------------------------------------------------------


def test_mutex_name_is_deterministic_user_scoped_and_prefixed():
    first = mutex_name(Path(r"D:\appdata-a"))
    again = mutex_name(Path(r"D:\appdata-a"))
    other = mutex_name(Path(r"D:\appdata-b"))
    assert first == again
    assert first != other
    assert first.startswith("Local\\dst-builder-")


def test_mutex_name_differs_from_manager_for_same_base():
    from dst_manager.infrastructure.single_instance import (
        mutex_name as manager_mutex_name,
    )

    base = Path(r"D:\appdata-a")
    assert mutex_name(base) != manager_mutex_name(base)


def test_default_mutex_names_differ(monkeypatch):
    from dst_manager.infrastructure.single_instance import (
        mutex_name as manager_mutex_name,
    )

    monkeypatch.setenv("LOCALAPPDATA", r"D:\user-appdata")
    assert mutex_name() != manager_mutex_name()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 命名互斥量内核对象")
def test_builder_lock_blocks_second_builder_but_never_manager(tmp_path):
    """双产品共存核心证据：Builder 持锁时 Manager 互斥量仍可立即获取。"""
    from dst_manager.infrastructure.single_instance import (
        acquire_instance_mutex as manager_acquire,
    )
    from dst_manager.infrastructure.single_instance import (
        release_instance_mutex as manager_release,
    )

    builder_guard = acquire_instance_mutex(tmp_path)
    assert builder_guard is not None
    try:
        # 第二个 Builder 实例被拒
        assert acquire_instance_mutex(tmp_path) is None
        # Manager 不受 Builder 锁影响：同一基准目录下两边互斥量名不同
        manager_guard = manager_acquire(tmp_path)
        assert manager_guard is not None
        manager_release(manager_guard)
    finally:
        release_instance_mutex(builder_guard)
    # 释放后 Builder 可重新成为唯一实例
    re_guard = acquire_instance_mutex(tmp_path)
    assert re_guard is not None
    release_instance_mutex(re_guard)


@pytest.mark.skipif(sys.platform == "win32", reason="仅非 Windows 平台放行路径")
def test_non_windows_platform_allows_startup(monkeypatch):
    monkeypatch.setattr(desktop_module(), "WINDOWS", False)
    guard = acquire_instance_mutex(Path(r"D:\appdata-a"))
    assert guard is not None
    release_instance_mutex(guard)


def desktop_module():
    from dst_builder.interfaces import desktop

    return desktop


# ---------------------------------------------------------------------------
# 资源发现：源码树 / PyInstaller frozen 双路径
# ---------------------------------------------------------------------------


def test_is_frozen_false_in_development():
    assert is_frozen() is False


def test_resource_dir_development_points_to_repo_root():
    root = resource_dir()
    assert (root / "builder_alembic.ini").is_file()
    assert (root / "builder_migrations" / "versions").is_dir()
    assert (root / "builder-web").is_dir()


def test_resource_dir_frozen_uses_meipass(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_dir() == tmp_path


def test_builder_source_has_no_stray_file_resource_resolution():
    """dst_builder 源码不得用 Path(__file__) 定位打包资源，统一走 resource_dir。

    唯一例外是 dst_builder/runtime.py 自身的 _DEV_ROOT（仓库根定位，无打包资源）。
    """
    import re

    package_dir = Path(resource_dir()) / "src" / "dst_builder"
    pattern = re.compile(r"Path\(__file__\)")
    hits = [
        py.relative_to(package_dir).as_posix()
        for py in package_dir.rglob("*.py")
        if pattern.search(py.read_text(encoding="utf-8"))
    ]
    assert hits == ["runtime.py"], (
        f"dst_builder 内通过 Path(__file__) 定位资源的文件：{hits}；"
        "frozen 态会断链，请改走 dst_builder.runtime.resource_dir"
    )


# ---------------------------------------------------------------------------
# 无窗 stdio 重定向（console=False 双击启动的日志通道）
# ---------------------------------------------------------------------------


def test_redirect_frozen_stdio_is_noop_in_development():
    assert redirect_frozen_stdio("desktop") is False


def test_redirect_frozen_stdio_writes_log_file_in_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    class _NullWriter:
        def write(self, *_args):
            return None

        def fileno(self):  # 模拟 PyInstaller windowed 态无 fileno
            raise OSError

    monkeypatch.setattr(sys, "stdout", _NullWriter())
    monkeypatch.setattr(sys, "stderr", _NullWriter())
    assert redirect_frozen_stdio("desktop") is True
    assert (tmp_path / "dst-builder" / "logs" / "dst-builder.log").is_file()


def test_redirect_frozen_stdio_keeps_console_output(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # 真实控制台流可用时不重定向（从控制台手工运行时输出保持可见）
    assert redirect_frozen_stdio("desktop") is False


def test_redirect_frozen_stdio_rejects_unknown_command():
    assert redirect_frozen_stdio("worker") is False


# ---------------------------------------------------------------------------
# 壳编排：动态回环端口 + 前端静态挂载
# ---------------------------------------------------------------------------


def test_start_local_server_binds_dynamic_loopback_port():
    handle = start_local_server(create_shell_app(None))
    try:
        assert handle.base_url.startswith("http://127.0.0.1:")
        port = int(handle.base_url.rsplit(":", 1)[1])
        assert port > 0, "壳必须使用动态端口（port=0），不得写死端口"
    finally:
        handle.shutdown()


def test_start_local_server_answers_api_on_dynamic_port():
    handle = start_local_server(create_shell_app(None))
    try:
        with urllib.request.urlopen(f"{handle.base_url}/openapi.json", timeout=5) as response:
            assert response.status == 200
    finally:
        handle.shutdown()


def test_shell_app_serves_frontend_at_root():
    from fastapi.testclient import TestClient

    dist_index = resource_dir() / "builder-web" / "dist" / "index.html"
    if not dist_index.is_file():
        pytest.skip("builder-web/dist 未构建：先运行 npm --prefix builder-web run build")
    with TestClient(create_shell_app(None)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # API 文档路由必须优先于根挂载的静态资源
        assert client.get("/openapi.json").status_code == 200


def test_shell_app_without_frontend_dist_still_boots_api(tmp_path):
    """dist 缺失时壳应用仍可构建（API 可用），只是静态资源降级为 404。"""
    from fastapi.testclient import TestClient

    app = create_shell_app(None, dist_dir=tmp_path / "missing-dist")
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/").status_code == 404
