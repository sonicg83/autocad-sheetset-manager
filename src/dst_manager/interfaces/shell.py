"""桌面壳：pywebview（WebView2）承载本地 Web 界面。壳为 v0.3.1 唯一交付入口。

壳进程负责完整的进程族生命周期：进程内 uvicorn（临时端口）+ 同机 CAD Worker
子进程（发布/布局重建等队列型 CAD 操作依赖 Worker 认领 SQLite 任务，见
`cli worker`）。窗口关闭时一并回收两者。
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import uvicorn
import webview

from ..application.shell_context import ShellContext
from ..config import Settings
from ..extensions.contracts import XLSX_MEDIA_TYPE
from ..extensions.registry import ExtensionRegistry
from ..extensions.save_grants import SaveGrantStore
from ..infrastructure.explorer import Explorer, ExplorerError
from ..infrastructure.persistence.extensions import ExtensionStore
from ..infrastructure.sheet_preferences import (
    InvalidSheetPreferencesError,
    SheetPreferences,
    SheetPreferencesError,
)
from ..runtime import is_frozen
from ..settings.runtime import RuntimeSettings, default_store
from .api import create_app
from .message_catalog import shell_error

# SC-11 外链白名单（SPEC-DM-011 §4 / ARCH-DM-004 §4.2）：硬编码登记，不做任意放宽。
# 仅允许项目主页/反馈所在的 github.com 域、sonicg83 账号路径下的 https 地址；
# 运行值来自 GET /api/about 的后端登记常量（api.py _HOMEPAGE），前端不传任意字符串。
_EXTERNAL_URL_SCHEME = "https"
_EXTERNAL_URL_HOST = "github.com"
_EXTERNAL_URL_PATH_PREFIX = "/sonicg83"

# ---- PLAN-DM-021 Task 4：原生文件对话框固定文件种类（安全红线） ----
# 扩展名白名单只由 file_kind 在此固定拼接：前端（含被伪造的本地化描述）无法传入
# 任意 file_types 过滤器字符串，描述含 (*.bat) 也不能扩大白名单。未知 kind 拒绝；
# 文件夹选择不经 file_kind，走独立的 select_folder（FOLDER_DIALOG 无过滤器概念）。
FileKind = Literal["dst", "template", "exe", "dll"]
_FILE_KIND_PATTERNS: dict[str, str] = {
    "dst": "*.dst",
    "template": "*.dwg;*.dwt",
    "exe": "*.exe",
    "dll": "*.dll",
}

# ---- PLAN-DM-020 Task 8：扩展成果原生"另存为"（SAVE_DIALOG + 一次性授权） ----
# 只允许 registry 中 output_kind=xlsx 且 MIME 匹配的动作；建议名由宿主从当前
# 可信工作区快照严格生成（不接受前端建议名），过滤器固定 XLSX。
_SAVE_DIALOG_DESCRIPTION = "XLSX 工作簿"
_SAVE_DIALOG_PATTERN = "*.xlsx"
_NAME_SUFFIX = "-图纸目录.xlsx"
_NAME_FALLBACK_STEM = "图纸集"
_MAX_STEM_LENGTH = 100
_NAME_INVALID_PATTERN = r'[<>:"/\\|?*\x00-\x1f\x7f]'


def _suggested_catalog_name(dst_path: Path) -> str:
    """从可信工作区 DST 生成图纸目录建议文件名（SPEC-DM-012 §9）。

    Windows 非法文件名字符（``<>:"/\\|?*``）与控制字符逐个替换为下划线，
    剥离首尾空白与点，图纸集名称部分限制长度；清洗后为空回退稳定默认名。
    """
    stem = re.sub(_NAME_INVALID_PATTERN, "_", dst_path.stem)
    stem = stem.strip(" .") or _NAME_FALLBACK_STEM
    return f"{stem[:_MAX_STEM_LENGTH]}{_NAME_SUFFIX}"


def _sanitize_description(description: str) -> str:
    """把本地化描述净化为 pywebview parse_file_type 允许的 ``[\\w ]+`` 文本。

    描述只进对话框显示：剥掉括号/点/分号/星号等模式字符（保留字母、数字、
    下标、CJK 与空格），伪造 ``危险 (*.bat)`` 退化为纯文本 ``危险 bat``，
    既不能扩大白名单，也不会在对话框弹出前抛 ValueError。
    """
    return " ".join(re.sub(r"[^\w ]", " ", description).split())


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
        registry: ExtensionRegistry | None = None,
        save_grants: SaveGrantStore | None = None,
        extension_store: ExtensionStore | None = None,
    ) -> None:
        """上下文与偏好仓库由 run_desktop 注入；缺省时仅文件选择/拖拽桥可用。

        ``registry``/``save_grants`` 由桌面装配注入（Task 9 与 API runtime 共享
        同一个 SaveGrantStore）；缺省时 request_extension_save 契约化拒绝。
        ``extension_store``（Task 11B）由桌面装配注入与 API 同一个扩展仓储；
        缺省时 open_artifact_folder 契约化拒绝。
        """
        self._context = context
        self._preferences = preferences
        self._explorer = explorer if explorer is not None else Explorer()
        self._registry = registry
        self._save_grants = save_grants
        self._extension_store = extension_store
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
            return shell_error(
                "SHELL_WORKSPACE_UNAVAILABLE", "当前没有匹配的已打开工作区，请重新打开图纸集"
            )
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
                return shell_error("SHELL_OPEN_FAILED", str(exc))
            return {"ok": True, "value": None}
        if context.root.is_dir():
            try:
                self._explorer.open_folder(context.root)
            except ExplorerError as exc:
                return shell_error("SHELL_OPEN_FAILED", str(exc))
            return {"ok": True, "value": None}
        return shell_error(
            "SHELL_DIRECTORY_NOT_FOUND", "图纸集目录不存在，可能已被移动或删除"
        )

    def load_sheet_columns(self, workspace_id: str) -> dict:
        """读取当前工作区的图纸页列偏好；无存储返回 value=None。"""
        error = self._context_error(workspace_id)
        if error is not None:
            return error
        if self._preferences is None:
            return shell_error("SHEET_PREFERENCES_IO", "偏好存储未就绪")
        try:
            data = self._preferences.load(workspace_id)
        except InvalidSheetPreferencesError as exc:
            return shell_error("SHEET_PREFERENCES_INVALID", str(exc))
        except SheetPreferencesError as exc:
            return shell_error("SHEET_PREFERENCES_IO", str(exc))
        return {"ok": True, "value": data}

    def save_sheet_columns(self, workspace_id: str, preferences: dict) -> dict:
        """校验并保存当前工作区的图纸页列偏好到应用数据目录。"""
        error = self._context_error(workspace_id)
        if error is not None:
            return error
        if self._preferences is None:
            return shell_error("SHEET_PREFERENCES_IO", "偏好存储未就绪")
        try:
            self._preferences.save(workspace_id, preferences)
        except InvalidSheetPreferencesError as exc:
            return shell_error("SHEET_PREFERENCES_INVALID", str(exc))
        except SheetPreferencesError as exc:
            return shell_error("SHEET_PREFERENCES_IO", str(exc))
        return {"ok": True, "value": None}

    def clear_workspace_context(self, workspace_id: str) -> dict:
        """关闭成功后清除可信上下文；ID 不匹配或本无上下文返回不可用（前端 best-effort）。"""
        if self._context is None:
            return {"ok": True, "value": None}
        if not self._context.clear(workspace_id):
            return shell_error(
                "SHELL_WORKSPACE_UNAVAILABLE", "当前没有匹配的已打开工作区上下文"
            )
        return {"ok": True, "value": None}

    def open_external(self, url: str) -> dict:
        """经系统默认浏览器打开登记的 https 外链（SPEC-DM-011 SC-11），不经 WebView 导航。

        只接受代码内白名单（github.com 域、/sonicg83 路径前缀）的 https 地址；
        返回模式与 open_workspace_folder 等桥方法一致：{ok:true;value} / {ok:false;code;message}。
        本方法不触碰 webview 窗口，无需窗口就绪守卫；打开失败对齐 open_workspace_folder
        回 SHELL_OPEN_FAILED。
        """
        if not isinstance(url, str):
            return shell_error("SHELL_EXTERNAL_URL_REJECTED", "仅允许打开登记的 https 链接")
        try:
            parts = urlsplit(url)
        except ValueError:
            return shell_error("SHELL_EXTERNAL_URL_REJECTED", "仅允许打开登记的 https 链接")
        path = parts.path or ""
        if (
            parts.scheme != _EXTERNAL_URL_SCHEME
            or parts.netloc != _EXTERNAL_URL_HOST
            or not (path == _EXTERNAL_URL_PATH_PREFIX or path.startswith(f"{_EXTERNAL_URL_PATH_PREFIX}/"))
        ):
            return shell_error("SHELL_EXTERNAL_URL_REJECTED", "仅允许打开登记的 https 链接")
        try:
            webbrowser.open(url)
        except OSError as exc:
            return shell_error("SHELL_OPEN_FAILED", str(exc))
        return {"ok": True, "value": None}

    def request_extension_save(self, extension_id: str, action_id: str, workspace_id: str) -> dict:
        """扩展成果原生"另存为"（PLAN-DM-020 Task 8 / ARCH-DM-006 §9.1）。

        只允许 registry 中 ``output_kind == "xlsx"`` 且 MIME 匹配的动作；桥不
        接受前端建议名——建议文件名由宿主从当前可信工作区快照严格生成（
        :func:`_suggested_catalog_name`），对话框固定 XLSX 过滤器。用户确认后
        经共享的 :class:`SaveGrantStore` 创建一次性授权，返回
        ``{ok:true;value:{save_grant_id,file_name,expires_at}}``——**不含目标
        绝对路径**；用户取消返回 ``{ok:true;value:null}`` 且不创建授权。
        """
        error = self._context_error(workspace_id)
        if error is not None:
            return error
        if self._save_grants is None or self._registry is None:
            return shell_error("EXTENSION_CAPABILITY_UNAVAILABLE", "保存授权通道未装配")
        descriptor = next(
            (
                item
                for item in self._registry.list()
                if item.manifest.extension_id == extension_id
            ),
            None,
        )
        if descriptor is None:
            return shell_error("EXTENSION_NOT_FOUND", f"扩展未登记：{extension_id}")
        action = next(
            (
                item
                for item in descriptor.manifest.actions
                if item.action_id == action_id
            ),
            None,
        )
        if action is None:
            return shell_error(
                "EXTENSION_ACTION_NOT_FOUND",
                f"扩展 {extension_id} 未声明动作：{action_id}",
            )
        if action.output_kind != "xlsx" or action.media_type != XLSX_MEDIA_TYPE:
            return shell_error(
                "EXTENSION_CAPABILITY_UNAVAILABLE", "该动作不支持 XLSX 保存"
            )
        if self._window is None:
            raise RuntimeError("保存对话框窗口尚未就绪")
        context = self._context.current
        assert context is not None  # _context_error 通过后当前上下文必然存在
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=_suggested_catalog_name(context.dst_path),
            file_types=[f"{_SAVE_DIALOG_DESCRIPTION} ({_SAVE_DIALOG_PATTERN})"],
        )
        if not result:
            # 用户取消：立即结束，不生成授权、不登记 Artifact。
            return {"ok": True, "value": None}
        try:
            receipt = self._save_grants.create(
                extension_id, action_id, workspace_id, Path(result)
            )
        except OSError:
            return shell_error("EXTENSION_CAPABILITY_UNAVAILABLE", "无法读取所选保存目标")
        return {
            "ok": True,
            "value": {
                "save_grant_id": receipt.save_grant_id,
                "file_name": receipt.file_name,
                "expires_at": receipt.expires_at.isoformat(),
            },
        }

    def open_artifact_folder(self, extension_id: str, artifact_id: str) -> dict:
        """在资源管理器中打开扩展导出成果所在目录并尽量选中文件（SPEC-DM-012 §10）。

        前端只传扩展与 Artifact 标识，**路径权威在宿主**：经扩展仓储校验
        Artifact 存在且 ``extension_id`` 匹配后才打开其登记 ``output_path`` 的
        所在目录（文件仍在则选中文件）。Artifact 不存在/身份不匹配/目录已被
        移动删除均返回结构化失败；除资源管理器外不执行任何命令，不打开任何
        未登记路径。
        """
        if self._extension_store is None:
            return shell_error("EXTENSION_CAPABILITY_UNAVAILABLE", "扩展成果存储未装配")
        record = (
            self._extension_store.get_artifact(artifact_id)
            if isinstance(artifact_id, str)
            else None
        )
        if record is None:
            return shell_error("EXTENSION_ARTIFACT_NOT_FOUND", "导出成果不存在或已被移动")
        if record.extension_id != extension_id:
            return shell_error("EXTENSION_ARTIFACT_NOT_FOUND", "导出成果不属于该扩展")
        output = Path(record.output_path)
        folder = output.parent
        if not folder.is_dir():
            return shell_error(
                "SHELL_ARTIFACT_DIRECTORY_NOT_FOUND",
                "导出成果所在目录不存在，可能已被移动或删除",
            )
        try:
            if output.is_file():
                self._explorer.open_folder_and_select(output)
            else:
                self._explorer.open_folder(folder)
        except ExplorerError as exc:
            return shell_error("SHELL_OPEN_FAILED", str(exc))
        return {"ok": True, "value": None}

    def select_file(self, file_kind: FileKind, localized_description: str) -> str | None:
        """弹出原生文件选择对话框（PLAN-DM-021 Task 4：file_kind + 本地化描述）。

        扩展名白名单只由 ``file_kind`` 按 :data:`_FILE_KIND_PATTERNS` 固定拼接；
        ``localized_description`` 仅作对话框显示并经净化，无法扩大白名单。
        未知 kind 抛 ValueError（不弹对话框）；取消或未选中返回 None；无窗口报
        明确错误。文件夹选择不经本方法，走 :meth:`select_folder`。
        """
        if self._window is None:
            raise RuntimeError("文件对话框窗口尚未就绪")
        patterns = _FILE_KIND_PATTERNS.get(file_kind) if isinstance(file_kind, str) else None
        if patterns is None:
            raise ValueError(f"未知的文件种类：{file_kind!r}")
        description = (
            _sanitize_description(localized_description)
            if isinstance(localized_description, str)
            else ""
        )
        if not description:
            description = "文件"  # 空描述仍须满足 parse_file_type 的 [\w ]+ 前缀
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=[f"{description} ({patterns})"],
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
        # 一次性保存授权存储装配一次（PLAN-DM-020 任务 9）：同一个实例注入 API
        # extension runtime 与 ShellBridge——桥"另存为"创建的授权必须能被 API
        # 执行消费，两处各建实例会让所有导出都报 SAVE_GRANT_INVALID。
        save_grants = SaveGrantStore()
        app = create_app(
            settings,
            on_workspace_opened=context.set_workspace,
            runtime_settings=runtime_settings,
            save_grants=save_grants,
        )
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
        bridge = ShellBridge(
            context=context,
            preferences=preferences,
            registry=app.state.extension_runtime.registry,
            save_grants=save_grants,
            # Task 11B：与 API 同一个扩展仓储——"打开所在文件夹"按登记的
            # Artifact output_path 定位，前端不传任何路径。
            extension_store=app.state.extension_runtime.store,
        )
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
