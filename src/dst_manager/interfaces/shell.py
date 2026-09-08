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
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
import webview

from ..application.shell_context import ShellContext
from ..config import Settings
from ..infrastructure.explorer import Explorer, ExplorerError
from ..infrastructure.sheet_preferences import (
    InvalidSheetPreferencesError,
    SheetPreferences,
    SheetPreferencesError,
)
from ..runtime import is_frozen
from ..settings.runtime import RuntimeSettings, default_store
from .api import create_app

# SC-11 外链白名单（SPEC-DM-011 §4 / ARCH-DM-004 §4.2）：硬编码登记，不做任意放宽。
# 仅允许项目主页/反馈所在的 github.com 域、sonicg83 账号路径下的 https 地址；
# 运行值来自 GET /api/about 的后端登记常量（api.py _HOMEPAGE），前端不传任意字符串。
_EXTERNAL_URL_SCHEME = "https"
_EXTERNAL_URL_HOST = "github.com"
_EXTERNAL_URL_PATH_PREFIX = "/sonicg83"


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

    def __init__(
        self,
        context: ShellContext | None = None,
        preferences: SheetPreferences | None = None,
        explorer: Explorer | None = None,
    ) -> None:
        """上下文与偏好仓库由 run_desktop 注入；缺省时仅文件选择/拖拽桥可用。"""
        self._context = context
        self._preferences = preferences
        self._explorer = explorer if explorer is not None else Explorer()
        self._window: webview.Window | None = None
        self._drop_callback_id: str | None = None
        self._drop_listener_registered = False

    def bind(self, window: webview.Window) -> None:
        self._window = window

    # ---- PLAN-DM-015 任务 2：可信上下文与偏好桥（新增方法不进业务 OpenAPI） ----
    # 四个方法均校验 workspace_id 等于当前有效上下文；路径只从上下文取得。
    # 返回可序列化字典：{ok:true;value} 或 {ok:false;code;message}。

    def _context_error(self, workspace_id: str) -> dict | None:
        context = self._context.current if self._context is not None else None
        if context is None or context.workspace_id != workspace_id:
            return {
                "ok": False,
                "code": "SHELL_WORKSPACE_UNAVAILABLE",
                "message": "当前没有匹配的已打开工作区，请重新打开图纸集",
            }
        return None

    def open_workspace_folder(self, workspace_id: str) -> dict:
        """在资源管理器中打开当前 DST 所在目录并尽量选中 DST；目录缺失明确提示。"""
        error = self._context_error(workspace_id)
        if error is not None:
            return error
        context = self._context.current
        if context.dst_path.is_file():
            try:
                self._explorer.open_folder_and_select(context.dst_path)
            except ExplorerError as exc:
                return {"ok": False, "code": "SHELL_OPEN_FAILED", "message": str(exc)}
            return {"ok": True, "value": None}
        if context.root.is_dir():
            try:
                self._explorer.open_folder(context.root)
            except ExplorerError as exc:
                return {"ok": False, "code": "SHELL_OPEN_FAILED", "message": str(exc)}
            return {"ok": True, "value": None}
        return {
            "ok": False,
            "code": "SHELL_DIRECTORY_NOT_FOUND",
            "message": "图纸集目录不存在，可能已被移动或删除",
        }

    def load_sheet_columns(self, workspace_id: str) -> dict:
        """读取当前工作区的图纸页列偏好；无存储返回 value=None。"""
        error = self._context_error(workspace_id)
        if error is not None:
            return error
        if self._preferences is None:
            return {"ok": False, "code": "SHEET_PREFERENCES_IO", "message": "偏好存储未就绪"}
        try:
            data = self._preferences.load(workspace_id)
        except InvalidSheetPreferencesError as exc:
            return {"ok": False, "code": "SHEET_PREFERENCES_INVALID", "message": str(exc)}
        except SheetPreferencesError as exc:
            return {"ok": False, "code": "SHEET_PREFERENCES_IO", "message": str(exc)}
        return {"ok": True, "value": data}

    def save_sheet_columns(self, workspace_id: str, preferences: dict) -> dict:
        """校验并保存当前工作区的图纸页列偏好到应用数据目录。"""
        error = self._context_error(workspace_id)
        if error is not None:
            return error
        if self._preferences is None:
            return {"ok": False, "code": "SHEET_PREFERENCES_IO", "message": "偏好存储未就绪"}
        try:
            self._preferences.save(workspace_id, preferences)
        except InvalidSheetPreferencesError as exc:
            return {"ok": False, "code": "SHEET_PREFERENCES_INVALID", "message": str(exc)}
        except SheetPreferencesError as exc:
            return {"ok": False, "code": "SHEET_PREFERENCES_IO", "message": str(exc)}
        return {"ok": True, "value": None}

    def clear_workspace_context(self, workspace_id: str) -> dict:
        """关闭成功后清除可信上下文；ID 不匹配或本无上下文返回不可用（前端 best-effort）。"""
        if self._context is None:
            return {"ok": True, "value": None}
        if not self._context.clear(workspace_id):
            return {
                "ok": False,
                "code": "SHELL_WORKSPACE_UNAVAILABLE",
                "message": "当前没有匹配的已打开工作区上下文",
            }
        return {"ok": True, "value": None}

    def open_external(self, url: str) -> dict:
        """经系统默认浏览器打开登记的 https 外链（SPEC-DM-011 SC-11），不经 WebView 导航。

        只接受代码内白名单（github.com 域、/sonicg83 路径前缀）的 https 地址；
        返回模式与 open_workspace_folder 等桥方法一致：{ok:true;value} / {ok:false;code;message}。
        本方法不触碰 webview 窗口，无需窗口就绪守卫；打开失败对齐 open_workspace_folder
        回 SHELL_OPEN_FAILED。
        """
        if not isinstance(url, str):
            return {
                "ok": False,
                "code": "SHELL_EXTERNAL_URL_REJECTED",
                "message": "仅允许打开登记的 https 链接",
            }
        try:
            parts = urlsplit(url)
        except ValueError:
            return {
                "ok": False,
                "code": "SHELL_EXTERNAL_URL_REJECTED",
                "message": "仅允许打开登记的 https 链接",
            }
        path = parts.path or ""
        if (
            parts.scheme != _EXTERNAL_URL_SCHEME
            or parts.netloc != _EXTERNAL_URL_HOST
            or not (path == _EXTERNAL_URL_PATH_PREFIX or path.startswith(f"{_EXTERNAL_URL_PATH_PREFIX}/"))
        ):
            return {
                "ok": False,
                "code": "SHELL_EXTERNAL_URL_REJECTED",
                "message": "仅允许打开登记的 https 链接",
            }
        try:
            webbrowser.open(url)
        except OSError as exc:
            return {"ok": False, "code": "SHELL_OPEN_FAILED", "message": str(exc)}
        return {"ok": True, "value": None}

    def select_file(self, file_types: list[str]) -> str | None:
        if self._window is None:
            raise RuntimeError("文件对话框窗口尚未就绪")
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
        )
        return result[0] if result else None

    def select_folder(self) -> str | None:
        """弹出原生文件夹选择对话框；取消或未选中返回 None（模式与 select_file 一致）。"""
        if self._window is None:
            raise RuntimeError("文件夹对话框窗口尚未就绪")
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
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

    开发态经 `python -m` 进入 `cli worker`；frozen 态 sys.executable 是 exe 自身，
    复用其 `worker` 子命令（entry.py 无参数时默认 desktop，见 packaging/entry.py）。
    `cwd` 与 `--project-root` 都取当前工作目录：`cli worker` 校验二者一致，
    且 `Settings.data_dir` 相对路径按 cwd 解析——与壳内 API 同 cwd，保证
    Worker 与 API 操作同一个 SQLite 任务队列。frozen 态 console=False，子进程
    无终端：Worker 认领日志由 entry.py 在子进程内重定向到
    %LOCALAPPDATA%/dst-manager/logs/worker.log（从控制台手工运行则保持可见）。
    """
    if is_frozen():
        args = [sys.executable, "worker", "--project-root", str(project_root)]
    else:
        args = [sys.executable, "-m", "dst_manager.interfaces.cli", "worker", "--project-root", str(project_root)]
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.Popen(
        args,
        cwd=str(project_root),
        env=env,
    )


def _report_early_exit(process: subprocess.Popen) -> None:
    """Worker 启动后短暂观察；立即退出（配置错误等）时给出警告。

    console=False 下警告经 entry.py 的 stdio 重定向落入 dst-manager.log；
    从控制台运行时仍直接可见。
    """
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


def enable_native_downloads() -> None:
    """放行页面内下载（属性 CSV 模板/导出）。

    pywebview 5 默认 ``ALLOW_DOWNLOADS = False``：WebView2 会静默吞掉 ``<a download>`` 点击，
    表现为页面无任何反应；落盘文件名由后端 Content-Disposition 提供。
    """
    webview.settings["ALLOW_DOWNLOADS"] = True


def run_desktop(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    # 单实例守卫（PLAN-DM-018）：双实例会同时操作同一工作区的 .dst-manager 锁、发布
    # journal 与任务队列互相踩踏；第二个实例弹窗报错，用户确认后唤起既有窗口再退出。
    # Worker 由壳拉起、天然同实例，serve/doctor 等开发入口不参与守卫。
    from ..infrastructure.single_instance import (
        APP_WINDOW_TITLE,
        acquire_instance_mutex,
        notify_already_running_and_raise,
        release_instance_mutex,
    )

    guard = acquire_instance_mutex()
    if guard is None:
        notify_already_running_and_raise()
        return
    try:
        enable_native_downloads()
        # 可信上下文登记 + 列偏好仓库：create_app 打开成功后登记当前工作区，桥只消费登记结果
        context = ShellContext()
        preferences = SheetPreferences(settings.data_dir)
        # 设置快照持有者装配一次（PLAN-DM-019 任务 5）：API 与桌面服务共用同一实例，
        # 避免双实例缓存读到不同步的 config_revision（桌面服务消费在任务 6 接线）。
        runtime_settings = RuntimeSettings(default_store())
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(
                    settings,
                    on_workspace_opened=context.set_workspace,
                    runtime_settings=runtime_settings,
                ),
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
        bridge = ShellBridge(context=context, preferences=preferences)
        window = webview.create_window(
            APP_WINDOW_TITLE, f"http://127.0.0.1:{port}/", js_api=bridge, width=1280, height=800
        )
        bridge.bind(window)
        worker = _spawn_worker(Path.cwd())
        threading.Thread(target=_report_early_exit, args=(worker,), daemon=True).start()
        try:
            webview.start()
        finally:
            _shutdown_worker(worker)
            server.should_exit = True
            thread.join(timeout=5)
    finally:
        release_instance_mutex(guard)
