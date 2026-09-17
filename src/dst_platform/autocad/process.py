"""Core Console 进程原语：请求/结果数据类、进程执行器与日志文本净化。

所有权（PLAN-DB-001 Task 6）：
- 进程执行自 ``dst_manager.infrastructure.autocad.worker`` 的
  ``CoreConsoleExecutor``/``CoreConsoleResult`` 迁入，共享接口固定为
  ``run(CoreConsoleRequest) -> CoreConsoleResult``；
- ``sanitize_log_text`` 自 ``dst_manager.infrastructure.logging_text`` 迁入
  （``decode_console_output`` 依赖它做日志安全净化，必须随进程原语同层）。

行为约束：进程启动参数、``CREATE_NO_WINDOW``、超时取消（kill 后回收输出）、
输出解码（UTF-16 BOM / UTF-16-LE 探测 / mbcs 兜底）与错误码均保持原样。
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CoreConsoleExecutor",
    "CoreConsoleRequest",
    "CoreConsoleResult",
    "decode_console_output",
    "sanitize_log_text",
]

_ALLOWED_LOG_CONTROLS = {"\t", "\n", "\r"}


def sanitize_log_text(value: str) -> str:
    """把日志规范为可安全写入 UTF-8 文本文件的内容。"""
    output: list[str] = []
    for character in value:
        codepoint = ord(character)
        if codepoint < 32 and character not in _ALLOWED_LOG_CONTROLS:
            output.append(f"\\x{codepoint:02x}")
        elif codepoint == 127:
            output.append("\\x7f")
        else:
            output.append(character)
    return "".join(output)


def decode_console_output(data: bytes) -> str:
    """按 Core Console 的实际输出编码解码，再转换为安全日志文本。"""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return sanitize_log_text(data.decode("utf-16", errors="replace"))
    sample = data[:200]
    odd_nuls = sample[1::2].count(0)
    if odd_nuls >= 2 and odd_nuls >= len(sample[1::2]) // 4:
        return sanitize_log_text(data.decode("utf-16-le", errors="replace"))
    return sanitize_log_text(data.decode("mbcs", errors="replace"))


@dataclass(slots=True, frozen=True)
class CoreConsoleRequest:
    """一次 Core Console 调用的不可变输入。"""

    console: Path
    drawing: Path
    script: Path
    timeout: int
    locale: str = "zh-CN"


@dataclass(slots=True)
class CoreConsoleResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    peak_memory_bytes: int | None


class CoreConsoleExecutor:
    def run(self, request: CoreConsoleRequest) -> CoreConsoleResult:
        args = [str(request.console), "/i", str(request.drawing), "/s", str(request.script), "/l", request.locale]
        started = time.perf_counter()
        # accoreconsole 是控制台程序，从 GUI 进程启动会弹出终端窗口；
        # CREATE_NO_WINDOW 抑制该窗口（stdout/stderr 仍照常经管道回收）。
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            stdout, stderr = process.communicate(timeout=request.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(args, request.timeout, stdout, stderr)
        duration_ms = int((time.perf_counter() - started) * 1000)
        peak_memory = self._peak_memory(process)

        completed = CoreConsoleResult(args, process.returncode, decode_console_output(stdout), decode_console_output(stderr), duration_ms, peak_memory)
        if completed.returncode:
            raise subprocess.CalledProcessError(completed.returncode, args, completed.stdout, completed.stderr)
        return completed

    @staticmethod
    def _peak_memory(process: subprocess.Popen) -> int | None:
        """Windows 进程句柄保留的 PeakWorkingSetSize；查询失败不影响 CAD 结果。"""
        try:
            import ctypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            if ctypes.windll.psapi.GetProcessMemoryInfo(int(process._handle), ctypes.byref(counters), counters.cb):
                return int(counters.PeakWorkingSetSize)
        except (AttributeError, OSError, ValueError):
            pass
        return None
