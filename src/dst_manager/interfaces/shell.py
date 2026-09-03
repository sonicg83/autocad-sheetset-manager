"""桌面壳：pywebview（WebView2）承载本地 Web 界面。壳为 v0.3.1 唯一交付入口。

壳进程负责完整的进程族生命周期：进程内 uvicorn（临时端口）+ 同机 CAD Worker
子进程（发布/布局重建等队列型 CAD 操作依赖 Worker 认领 SQLite 任务，见
`cli worker`）。窗口关闭时一并回收两者。
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
import webview

from ..config import Settings
from .api import create_app


class ShellBridge:
    """暴露给 window.pywebview.api 的最小原生能力面（SPEC-DM-007 §3.2）。

    拖拽文件路径（v0.3.1 Task 8 spike 结论）：pywebview >=5 的 EdgeChromium/WebView2
    后端原生支持——`webview.dom` 的 drop 事件经 WebView2 `postMessageWithAdditionalObjects`
    携带真实 `CoreWebView2File`，pywebview 将其绝对路径注入事件字典的
    `pywebviewFullPath` 字段。本桥在 document 上注册 dragenter/dragover/drop 监听
    （dragenter/dragover prevent_default 放行拖放，避免 WebView2 走默认导航/下载），
    drop 命中后经 `window.evaluate_js` 把路径转交前端注册的
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

        def _on_drag(event: dict) -> None:
            pass  # 仅需 preventDefault 使页面成为合法放置目标；无业务逻辑

        def _on_drop(event: dict) -> None:
            files = event.get("dataTransfer", {}).get("files", [])
            for file in files:
                path = file.get("pywebviewFullPath")
                if path:
                    self._notify_dropped_path(path)

        document = self._window.dom.document
        # 对齐 pywebview 官方 drag & drop 示例（MDN：drop 只在 dragover 被 cancel 后派发）：
        # 缺 dragenter/dragover 的 preventDefault 时，WebView2 走默认行为（导航/下载被拖文件），
        # drop 事件不会到达页面。dragover 高频触发，debounce 抑制桥面空转。
        document.on(
            "dragenter", DOMEventHandler(_on_drag, prevent_default=True, stop_propagation=True)
        )
        document.on(
            "dragover",
            DOMEventHandler(_on_drag, prevent_default=True, stop_propagation=True, debounce=500),
        )
        document.on(
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


def _spawn_worker(project_root: Path) -> subprocess.Popen:
    """拉起同机 CAD Worker 子进程（对齐 start.ps1 的托管方式）。

    `cwd` 与 `--project-root` 都取当前工作目录：`cli worker` 校验二者一致，
    且 `Settings.data_dir` 相对路径按 cwd 解析——与壳内 API 同 cwd，保证
    Worker 与 API 操作同一个 SQLite 任务队列。输出继承父进程终端，便于
    观察 Worker 认领日志。
    """
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.Popen(
        [sys.executable, "-m", "dst_manager.interfaces.cli", "worker", "--project-root", str(project_root)],
        cwd=str(project_root),
        env=env,
    )


def _report_early_exit(process: subprocess.Popen) -> None:
    """Worker 启动后短暂观察；立即退出（配置错误等）时给出可见警告。"""
    for _ in range(4):
        if process.poll() is not None:
            print(
                f"警告：CAD Worker 子进程已提前退出（退出码 {process.returncode}），"
                "队列型 CAD 任务将无人认领；请检查 `dst-manager doctor` 配置。",
                file=sys.stderr,
            )
            return
        time.sleep(0.5)


def _shutdown_worker(process: subprocess.Popen | None) -> None:
    """回收 Worker 子进程；terminate 不退出则升级 kill（与 start.ps1 Stop 的强杀语义一致）。"""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


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
    worker = _spawn_worker(Path.cwd())
    threading.Thread(target=_report_early_exit, args=(worker,), daemon=True).start()
    try:
        webview.start()
    finally:
        _shutdown_worker(worker)
        server.should_exit = True
        thread.join(timeout=5)
