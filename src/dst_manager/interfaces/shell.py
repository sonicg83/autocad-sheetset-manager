"""桌面壳：pywebview（WebView2）承载本地 Web 界面。壳为 v0.3.1 唯一交付入口。"""

import json
import threading
import time

import uvicorn
import webview

from ..config import Settings
from .api import create_app


class ShellBridge:
    """暴露给 window.pywebview.api 的最小原生能力面（SPEC-DM-007 §3.2）。

    拖拽文件路径（v0.3.1 Task 8 spike 结论）：pywebview >=5 的 EdgeChromium/WebView2
    后端原生支持——`webview.dom` 的 drop 事件经 WebView2 `postMessageWithAdditionalObjects`
    携带真实 `CoreWebView2File`，pywebview 将其绝对路径注入事件字典的
    `pywebviewFullPath` 字段。本桥在 document 上注册 drop 监听（prevent_default，
    避免拖拽触发默认导航），命中后经 `window.evaluate_js` 把路径转交前端注册的
    全局回调（callback_id 为前端传入的全局函数名）。
    """

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._drop_callback_id: str | None = None
        self._drop_listener_registered = False

    def bind(self, window: webview.Window) -> None:
        self._window = window

    def select_file(self, file_types: list[str]) -> str | None:
        if self._window is None:
            raise RuntimeError("文件对话框窗口尚未就绪")
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
        )
        return result[0] if result else None

    def on_files_dropped(self, callback_id: str) -> None:
        """注册拖拽文件路径回调。

        callback_id 是前端暴露的全局 JS 函数名；此后每次真实 OS 拖拽把文件落入
        窗口时，本桥以该文件的绝对路径调用 `window[callback_id](path)`。桥不拦截
        扩展名，仅转发路径；扩展名校验由前端复用 selectAndOpenDst 的校验。
        """
        if self._window is None:
            raise RuntimeError("拖拽回调注册时窗口尚未就绪")
        self._drop_callback_id = callback_id
        self._register_drop_listener()

    def _register_drop_listener(self) -> None:
        if self._drop_listener_registered:
            return
        from webview.dom import DOMEventHandler

        def _on_drop(event: dict) -> None:
            files = event.get("dataTransfer", {}).get("files", [])
            for file in files:
                path = file.get("pywebviewFullPath")
                if path:
                    self._notify_dropped_path(path)

        self._window.dom.document.on(
            "drop", DOMEventHandler(_on_drop, prevent_default=True, stop_propagation=True)
        )
        self._drop_listener_registered = True

    def _notify_dropped_path(self, path: str) -> None:
        if self._window is None or not self._drop_callback_id:
            return
        self._window.evaluate_js(
            f"window[{json.dumps(self._drop_callback_id)}] && "
            f"window[{json.dumps(self._drop_callback_id)}]({json.dumps(path)})"
        )


def run_desktop(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=0, log_level="warning")
    )
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
