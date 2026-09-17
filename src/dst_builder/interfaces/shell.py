"""DST Builder 桌面壳：pywebview（WebView2）承载本地 Web 界面（Task 11）。

壳进程负责：应用工厂装配（含 builder-web/dist 静态挂载）→ 进程内 uvicorn
（127.0.0.1 动态端口，AGENTS.md 只允许监听回环）→ pywebview 窗口；窗口关闭
时回收 uvicorn。借鉴 Manager 已验证的壳模式，但独立实现产品入口与资源发现，
不从 Manager shell import。

与 ``dst-builder serve`` 的关系：serve 是显式绑定项目根的开发/自动化入口
（固定默认端口）；桌面壳是最终用户交付入口，前端创建向导自带项目根输入，
壳本身不绑定项目根（``create_builder_app(project_root=None)`` 为受支持的
未初始化形态）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import uvicorn
import webview
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..runtime import APP_TITLE, resource_dir
from .api import create_builder_app
from .desktop import (
    acquire_instance_mutex,
    notify_already_running_and_raise,
    release_instance_mutex,
)

__all__ = ["LocalServerHandle", "create_shell_app", "run_desktop", "start_local_server"]

# WebView2 窗口默认尺寸（与 Manager 壳一致的可用工作区）
_WINDOW_WIDTH = 1280
_WINDOW_HEIGHT = 800


def _frontend_dist(dist_dir: Path | None = None) -> Path:
    """builder-web/dist 定位：显式参数 > frozen/源码双路径资源基准目录。"""
    if dist_dir is not None:
        return dist_dir
    return resource_dir() / "builder-web" / "dist"


def create_shell_app(project_root: Path | None = None, dist_dir: Path | None = None) -> FastAPI:
    """壳专用应用工厂：Builder API + 根路径静态前端。

    静态挂载在 API 路由注册之后（Starlette 按注册顺序匹配，``/api/*`` 优先）；
    dist 缺失时跳过挂载，壳仍提供完整 API（前端缺失是打包前置条件错误，
    不应在运行期崩溃整个进程）。
    """
    app = create_builder_app(project_root=project_root)
    frontend = _frontend_dist(dist_dir)
    if (frontend / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="builder-web")
    return app


@dataclass
class LocalServerHandle:
    """运行中的壳内 uvicorn 句柄；shutdown 由壳窗口关闭路径调用。"""

    server: uvicorn.Server
    thread: threading.Thread
    base_url: str

    def shutdown(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def start_local_server(app: FastAPI) -> LocalServerHandle:
    """在 127.0.0.1 的动态端口（port=0）上启动进程内 uvicorn。

    动态端口：壳与 ``dst-builder serve``（默认 8100）、Manager 壳/serve
    并存时绝不抢占固定端口；实际端口从已绑定 socket 读取。
    """
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    return LocalServerHandle(server=server, thread=thread, base_url=f"http://127.0.0.1:{port}")


def run_desktop(project_root: Path | None = None) -> None:
    """桌面壳主入口（packaging/builder_entry.py 无参数启动即进入此处）。

    单实例守卫：第二个实例弹窗提示后退出（守卫语义见 desktop 模块说明）。
    """
    guard = acquire_instance_mutex()
    if guard is None:
        notify_already_running_and_raise()
        return
    try:
        app = create_shell_app(project_root)
        handle = start_local_server(app)
        webview.create_window(
            APP_TITLE, handle.base_url, width=_WINDOW_WIDTH, height=_WINDOW_HEIGHT
        )
        try:
            webview.start()
        finally:
            handle.shutdown()
    finally:
        release_instance_mutex(guard)
