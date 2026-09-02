"""pywebview 桌面壳轻量单测：桥可导入、未绑定窗口报错、绑定后对话框返回路径。"""

import pytest

from dst_manager.interfaces.shell import ShellBridge


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
