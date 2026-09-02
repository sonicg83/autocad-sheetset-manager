"""pywebview 桌面壳轻量单测：桥可导入、未绑定窗口报错、绑定后对话框返回路径、拖拽回调注册与转发。"""

import pytest

from dst_manager.interfaces.shell import ShellBridge


class _FakeDom:
    """模拟 window（含 window.dom.document）：捕获 drop 监听器与 evaluate_js 调用。"""

    def __init__(self):
        self.handler = None
        self.evaluated: list[str] = []

    @property
    def dom(self):
        return self

    @property
    def document(self):
        return self

    def on(self, event: str, handler) -> None:
        # 对齐 pywebview Element.on：存的是底层 callable（DOMEventHandler.callback）
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
    assert dom.handler is not None
    assert dom.evaluated == []


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
