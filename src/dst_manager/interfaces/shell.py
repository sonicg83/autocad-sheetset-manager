"""桌面壳：pywebview（WebView2）承载本地 Web 界面。壳为 v0.3.1 唯一交付入口。"""

import threading
import time

import uvicorn
import webview

from ..config import Settings
from .api import create_app


class ShellBridge:
    """暴露给 window.pywebview.api 的最小原生能力面（SPEC-DM-007 §3.2）。"""

    def __init__(self) -> None:
        self._window: webview.Window | None = None

    def bind(self, window: webview.Window) -> None:
        self._window = window

    def select_file(self, file_types: list[str]) -> str | None:
        if self._window is None:
            raise RuntimeError("文件对话框窗口尚未就绪")
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
        )
        return result[0] if result else None


def run_desktop(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    bridge = ShellBridge()
    window = webview.create_window("DST Manager", f"http://127.0.0.1:{port}/", js_api=bridge, width=1280, height=800)
    bridge.bind(window)
    try:
        webview.start()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
