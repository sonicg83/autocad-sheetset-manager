"""资源管理器命令行构造单测（顶部栏「打开所在文件夹」回归钉子）。

真实 explorer **自行解析原始命令行**（不走 CRT/CommandLineToArgvW 那套引号规则）：
``/select,<path>`` 必须整体保留、只给路径部分加引号。Python 的
``subprocess.list2cmdline`` 见到含空格的路径时会把**整个** ``/select,<path>`` 参数
用双引号包住（``"/select,C:\\a b\\f.dst"``），explorer 会把它当成一个普通路径
解析失败，随后回退打开用户的「文档」目录。

本机实测（Shell.Application 枚举窗口位置）：

- ``explorer "/select,C:\\...\\project3 - 2\\图纸集数据文件.dst"`` → ``file:///C:/Users/sonic/Documents``
- ``explorer /select,"C:\\...\\project3 - 2\\图纸集数据文件.dst"`` → 正确目录并选中文件

fake Popen 只记录参数、绝不弹出窗口；断言针对"explorer 最终收到的命令行"，
即字符串参数原样、列表参数经 ``list2cmdline`` 还原后的结果。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dst_manager.infrastructure import explorer as explorer_module
from dst_manager.infrastructure.explorer import (
    Explorer,
    ExplorerError,
    ExplorerUnsupportedError,
)


class _RecordingPopen:
    """替换 subprocess.Popen：只记录参数，不启动任何进程。"""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, args, **kwargs):
        # 对齐 Popen 调用签名；只记录、不启动进程
        self.calls.append(args)


def _effective_command_line(args: object) -> str:
    """还原 explorer 实际收到的命令行：字符串原样，列表按 Windows 规则拼装。"""
    if isinstance(args, str):
        return args
    return subprocess.list2cmdline(list(args))  # type: ignore[arg-type]


@pytest.fixture()
def recording_popen(monkeypatch: pytest.MonkeyPatch) -> _RecordingPopen:
    popen = _RecordingPopen()
    monkeypatch.setattr(explorer_module.subprocess, "Popen", popen)
    return popen


def test_select_command_line_keeps_switch_outside_quotes_for_path_with_spaces(
    recording_popen: _RecordingPopen,
):
    """含空格路径：只有路径加引号，/select 开关留在引号外（否则 explorer 打开「文档」）。"""
    dst = Path(r"C:\工程 甲\图纸集数据文件.dst")
    Explorer().open_folder_and_select(dst)
    assert recording_popen.calls == [f'explorer /select,"{dst}"']


def test_select_command_line_is_quoted_for_path_without_spaces(
    recording_popen: _RecordingPopen,
):
    """无空格路径走同一条命令行构造路径（不因是否含空格分叉）。"""
    dst = Path(r"C:\工程\图纸集数据文件.dst")
    Explorer().open_folder_and_select(dst)
    assert recording_popen.calls == [f'explorer /select,"{dst}"']


def test_select_command_line_rejects_embedded_double_quote(recording_popen: _RecordingPopen):
    """路径含双引号时无法在命令行中安全表达：拒绝且不启动 explorer。"""
    with pytest.raises(ExplorerError):
        Explorer().open_folder_and_select(Path('C:\\工程\\图纸集"异常.dst'))
    assert recording_popen.calls == []


def test_select_command_line_preserves_cjk_and_tricky_characters(recording_popen: _RecordingPopen):
    """中文、逗号、&、#、括号等合法路径字符原样保留，不被转义或被 shell 解释。"""
    dst = Path(r"C:\工程 甲,乙 & 丙 #1 (终)\图纸 集, v2.dst")
    Explorer().open_folder_and_select(dst)
    assert recording_popen.calls == [f'explorer /select,"{dst}"']


def test_select_reports_unsupported_on_non_windows(monkeypatch: pytest.MonkeyPatch):
    """非 Windows 平台直接拒绝，不拼任何命令行。"""
    monkeypatch.setattr(explorer_module.sys, "platform", "linux")
    with pytest.raises(ExplorerUnsupportedError):
        Explorer().open_folder_and_select(Path("/工程 甲/图纸集.dst"))
