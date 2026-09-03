"""pywebview 桌面壳轻量单测：桥可导入、未绑定窗口报错、绑定后对话框返回路径、拖拽回调注册与转发、Worker 子进程管理。"""

import subprocess
import sys
from pathlib import Path

import pytest

from dst_manager.interfaces.shell import (
    ShellBridge,
    _report_early_exit,
    _shutdown_worker,
    _spawn_worker,
)


class _FakeDom:
    """模拟 window（含 window.dom.document）：捕获事件监听器与 evaluate_js 调用。"""

    def __init__(self):
        self.handlers: dict[str, object] = {}  # 事件名 -> DOMEventHandler
        self.handler = None  # drop 监听器的底层 callable（对齐老用例）
        self.evaluated: list[str] = []
        self.on_calls = 0

    @property
    def dom(self):
        return self

    @property
    def document(self):
        return self

    def on(self, event: str, handler) -> None:
        # 对齐 pywebview Element.on：存的是底层 callable（DOMEventHandler.callback）
        self.on_calls += 1
        self.handlers[event] = handler
        if event == "drop":
            self.handler = handler.callback

    def evaluate_js(self, code: str) -> None:
        self.evaluated.append(code)


def test_shell_bridge_select_file_requires_window():
    bridge = ShellBridge()
    with pytest.raises(RuntimeError):
        bridge.select_file(["DST 文件|*.dst"])  # 未绑定窗口时给出明确错误而非 AttributeError


def test_shell_bridge_select_file_returns_first_path():
    class _FakeWindow:
        def __init__(self, result):
            self._result = result
            self.calls = []

        def create_file_dialog(self, dialog_type, allow_multiple=False, file_types=None):
            self.calls.append((dialog_type, allow_multiple, file_types))
            return self._result

    fake = _FakeWindow(["C:\\work\\out.dst"])
    bridge = ShellBridge()
    bridge.bind(fake)
    assert bridge.select_file(["DST 文件|*.dst"]) == "C:\\work\\out.dst"
    assert fake.calls[0][0] == 10  # webview.OPEN_DIALOG
    assert fake.calls[0][1] is False
    assert fake.calls[0][2] == ["DST 文件|*.dst"]


def test_shell_bridge_select_file_returns_none_when_cancelled():
    class _FakeWindow:
        def create_file_dialog(self, dialog_type, allow_multiple=False, file_types=None):
            return None

    bridge = ShellBridge()
    bridge.bind(_FakeWindow())
    assert bridge.select_file(["DST 文件|*.dst"]) is None


def test_shell_bridge_on_files_dropped_requires_window():
    bridge = ShellBridge()
    with pytest.raises(RuntimeError):
        bridge.on_files_dropped("__acceptDstPath")  # 未绑定窗口时给出明确错误


def test_shell_bridge_on_files_dropped_registers_drop_listener_once():
    dom = _FakeDom()
    bridge = ShellBridge()
    bridge.bind(dom)
    bridge.on_files_dropped("__acceptDstPath")
    bridge.on_files_dropped("__acceptDstPath")  # 幂等：不重复注册监听器
    assert dom.on_calls == 3  # drop + dragenter + dragover，重复注册不再翻倍
    assert dom.handler is not None
    assert dom.evaluated == []


def test_shell_bridge_registers_dragenter_and_dragover_to_allow_drop():
    """MDN/pywebview 官方示例：必须对 dragenter/dragover preventDefault，页面才是合法放置目标；
    否则 WebView2 走默认行为（导航/下载该文件），drop 事件根本不会派发到页面。"""
    dom = _FakeDom()
    bridge = ShellBridge()
    bridge.bind(dom)
    bridge.on_files_dropped("__acceptDstPath")
    for event in ("dragenter", "dragover"):
        handler = dom.handlers.get(event)
        assert handler is not None, f"缺少 {event} 监听器"
        assert handler.prevent_default and handler.stop_propagation


def test_shell_bridge_dropped_path_forwards_to_frontend_callback():
    dom = _FakeDom()
    bridge = ShellBridge()
    bridge.bind(dom)
    bridge.on_files_dropped("__acceptDstPath")
    dom.handler({"dataTransfer": {"files": [{"pywebviewFullPath": "C:\\work\\out.dst"}]}})
    assert len(dom.evaluated) == 1
    code = dom.evaluated[0]
    assert '"__acceptDstPath"' in code
    assert '"C:\\\\work\\\\out.dst"' in code or "C:\\\\work\\\\out.dst" in code


def test_shell_bridge_dropped_event_without_full_path_is_ignored():
    dom = _FakeDom()
    bridge = ShellBridge()
    bridge.bind(dom)
    bridge.on_files_dropped("__acceptDstPath")
    dom.handler({"dataTransfer": {"files": [{"name": "out.dst"}]}})  # 无 pywebviewFullPath
    assert dom.evaluated == []


class _FakePopen:
    """模拟 subprocess.Popen：记录构造参数与回收调用序列。"""

    def __init__(self, args, cwd=None, env=None, alive=True):
        self.args = args
        self.cwd = cwd
        self.env = env
        self.alive = alive
        self.returncode = None if alive else 3
        self.calls: list[str] = []

    def poll(self):
        return None if self.alive else self.returncode

    def terminate(self):
        self.calls.append("terminate")
        self.alive = False
        self.returncode = 0

    def kill(self):
        self.calls.append("kill")
        self.alive = False
        self.returncode = 1

    def wait(self, timeout=None):
        self.calls.append(f"wait({timeout})")
        return self.returncode


def test_spawn_worker_targets_cli_worker_with_matching_project_root(monkeypatch):
    captured = {}

    def fake_popen(args, cwd=None, env=None):
        captured["args"], captured["cwd"], captured["env"] = args, cwd, env
        return _FakePopen(args, cwd=cwd, env=env)

    monkeypatch.setattr("dst_manager.interfaces.shell.subprocess.Popen", fake_popen)
    project_root = Path.cwd()
    _spawn_worker(project_root)
    # cwd 与 --project-root 一致（cli worker 校验），且指向同一任务队列
    assert captured["cwd"] == str(project_root)
    assert captured["args"][:3] == [sys.executable, "-m", "dst_manager.interfaces.cli"]
    assert captured["args"][3:5] == ["worker", "--project-root"]
    assert captured["args"][5] == str(project_root)
    assert captured["env"].get("PYTHONUTF8") == "1"


def test_report_early_exit_warns_when_worker_dies_immediately(capsys):
    dead = _FakePopen([], alive=False)
    dead.returncode = 3
    _report_early_exit(dead)  # 首轮 poll 即命中，不引入测试等待
    err = capsys.readouterr().err
    assert "CAD Worker 子进程已提前退出" in err
    assert "退出码 3" in err


def test_report_early_exit_silent_while_alive(monkeypatch, capsys):
    process = _FakePopen([], alive=True)
    sleeps = []

    monkeypatch.setattr("dst_manager.interfaces.shell.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(process, "poll", lambda: None)
    _report_early_exit(process)
    assert len(sleeps) == 4  # 观察 2 秒后静默放行
    assert capsys.readouterr().err == ""


def test_shutdown_worker_terminates_gracefully():
    process = _FakePopen([], alive=True)
    _shutdown_worker(process)
    assert process.calls == ["terminate", "wait(5)"]


def test_shutdown_worker_escapes_to_kill_on_timeout():
    process = _FakePopen([], alive=True)
    original_wait = process.wait

    def stubborn_wait(timeout=None):
        if process.calls.count("terminate") == 1 and "wait(5)" not in process.calls:
            process.calls.append(f"wait({timeout})")
            raise subprocess.TimeoutExpired(process.args, timeout)
        return original_wait(timeout)

    process.wait = stubborn_wait
    _shutdown_worker(process)
    assert process.calls[:3] == ["terminate", "wait(5)", "kill"]


def test_shutdown_worker_ignores_already_exited():
    process = _FakePopen([], alive=False)
    _shutdown_worker(process)
    _shutdown_worker(None)  # 不抛错
    assert process.calls == []

def test_frontend_file_filters_match_pywebview_parse_format():
    """壳桥 select_file 直通 create_file_dialog：前端过滤器字符串必须通过 pywebview
    parse_file_type 校验（描述仅允许字母/数字/下划线/空格，不得含 / 等符号），否则真实壳
    在对话框弹出前抛 ValueError；假桥 e2e 不经过该校验，需本契约测试守护。"""
    import re

    from webview.util import parse_file_type

    source = (Path(__file__).parents[2] / "web" / "src" / "api" / "shell.ts").read_text(encoding="utf-8")
    filters = re.findall(r'"([^"]+\(\*[^"]+\))"', source)
    assert filters, "未在 web/src/api/shell.ts 中找到文件过滤器定义"
    for file_filter in filters:
        parse_file_type(file_filter)  # 抛 ValueError 即失败
