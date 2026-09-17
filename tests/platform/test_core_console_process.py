"""Core Console 进程原语平台所有权测试（PLAN-DB-001 Task 6，产品无关）。

所有权：``dst_platform.autocad.process``（进程执行自
``dst_manager.infrastructure.autocad.worker`` 迁入；``sanitize_log_text`` 自
``dst_manager.infrastructure.logging_text`` 迁入）。共享接口固定为
``CoreConsoleExecutor.run(CoreConsoleRequest) -> CoreConsoleResult``。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import dst_platform.autocad.process as process_module
from dst_platform.autocad.process import (
    CoreConsoleExecutor,
    CoreConsoleRequest,
    CoreConsoleResult,
    decode_console_output,
    sanitize_log_text,
)


class _FakeProcess:
    def __init__(self, *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"", times_out: bool = False):
        self.killed = False
        self._returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._times_out = times_out

    def communicate(self, timeout=None):
        if self._times_out and not self.killed:
            raise subprocess.TimeoutExpired(cmd=["fake"], timeout=timeout, output=self._stdout, stderr=self._stderr)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True

    @property
    def returncode(self) -> int:
        return self._returncode


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch):
    """替换 Popen，记录启动参数并返回可编程的假进程。"""
    calls: list[tuple[list[str], dict]] = []

    def install(process: _FakeProcess):
        def fake_popen(args, **kwargs):
            calls.append((args, kwargs))
            return process

        monkeypatch.setattr(process_module.subprocess, "Popen", fake_popen)
        return calls

    return install


def test_sanitize_log_text_escapes_control_characters() -> None:
    assert sanitize_log_text("中文\x00错误\x1b[31m\t正常\n") == "中文\\x00错误\\x1b[31m\t正常\n"
    assert sanitize_log_text("del\x7f") == "del\\x7f"


def test_decode_console_output_detects_utf16_and_mbcs() -> None:
    assert decode_console_output("中文输出".encode("utf-16")) == "中文输出"
    assert decode_console_output("plain ascii".encode("mbcs")) == "plain ascii"


def test_run_builds_core_console_arguments_and_decodes_output(fake_run) -> None:
    console = Path("C:/fake/accoreconsole.exe")
    drawing = Path("C:/work/样张.dwg")
    script = Path("C:/work/task.scr")
    process = _FakeProcess(stdout="中文输出".encode("utf-16"), stderr=b"warn")
    calls = fake_run(process)

    request = CoreConsoleRequest(console=console, drawing=drawing, script=script, timeout=60)
    result = CoreConsoleExecutor().run(request)

    args, kwargs = calls[0]
    assert args == [str(console), "/i", str(drawing), "/s", str(script), "/l", "zh-CN"]
    assert kwargs["shell"] is False
    assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert isinstance(result, CoreConsoleResult)
    assert result.args == args
    assert result.returncode == 0
    assert result.stdout == "中文输出"
    assert result.stderr == "warn"
    assert result.duration_ms >= 0
    assert result.peak_memory_bytes is None  # 假进程无真实句柄：查询失败不致命


def test_run_raises_called_process_error_with_decoded_output(fake_run) -> None:
    process = _FakeProcess(returncode=7, stdout="布局输出".encode("utf-16"), stderr=b"cad error")
    fake_run(process)

    request = CoreConsoleRequest(console=Path("c.exe"), drawing=Path("a.dwg"), script=Path("a.scr"), timeout=30)
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        CoreConsoleExecutor().run(request)

    assert excinfo.value.returncode == 7
    assert excinfo.value.stdout == "布局输出"
    assert excinfo.value.stderr == "cad error"


def test_run_kills_process_and_reraises_on_timeout(fake_run) -> None:
    process = _FakeProcess(times_out=True, stdout=b"partial")
    fake_run(process)

    request = CoreConsoleRequest(console=Path("c.exe"), drawing=Path("a.dwg"), script=Path("a.scr"), timeout=5)
    with pytest.raises(subprocess.TimeoutExpired):
        CoreConsoleExecutor().run(request)

    assert process.killed


def test_run_supports_explicit_locale_override(fake_run) -> None:
    calls = fake_run(_FakeProcess())

    request = CoreConsoleRequest(console=Path("c.exe"), drawing=Path("a.dwg"), script=Path("a.scr"), timeout=10, locale="en-US")
    CoreConsoleExecutor().run(request)

    assert calls[0][0][-1] == "en-US"
