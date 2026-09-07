"""桌面壳单实例守卫（Windows）：命名互斥量 + 前台唤起。

背景：桌面壳（pywebview/WebView2）是 DST Manager 唯一交付入口（SPEC-DM-007），
同一会话只允许一个壳进程。两个实例并行会同时操作同一工作区的资源
（`.dst-manager` 锁、发布 journal、SQLite 任务队列），真实日志中的
`PUBLISH_RECOVERY_FAILED`、`WinError 32 文件被占用` 即属此类踩踏。
本模块在进程层兜底（PLAN-DM-018）：第二个实例启动时弹窗报错，用户确认后
把已启动实例的窗口还原并置前，然后退出。CAD Worker 是壳的子进程、天然同
实例，不受限；`serve`/`doctor` 等开发入口不参与守卫。

实现：仅标准库 + ctypes 直调 Win32（项目不引入 pywin32）。
- 命名互斥量（CreateMutexW）：内核对象，进程退出（含崩溃）自动释放、
  不会遗留陈旧锁；`Local\\` 前缀限定会话内可见，无需管理员权限。
- 前台唤起由"后启动"进程执行：它刚被 Shell 激活、持有前台权限，才能
  可靠调用 SetForegroundWindow（Windows 前台锁规则）；最小化窗口先经
  ShowWindow(SW_RESTORE) 还原。
- 非 Windows 平台守卫直接放行（桌面壳本就只面向 Windows 11），保证
  Linux CI 可运行，平台条件为模块级开关、单测可注入。
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import time
from pathlib import Path

# 平台开关：Windows 才参与守卫；单测可 monkeypatch 模拟非 Windows。
WINDOWS = os.name == "nt"

# 桌面壳主窗口标题；与 shell.create_window 的 title 参数保持同一权威来源。
APP_WINDOW_TITLE = "DST Manager"

# 非 Windows 平台的放行标记（恒为"唯一实例"）；与内核句柄（int）区分。
_NO_GUARD_REQUIRED = object()

# Win32 常量（ctypes 直调，避免 magic number）。
_ERROR_ALREADY_EXISTS = 183
_SYNCHRONIZE = 0x00100000
_SW_RESTORE = 9  # 还原窗口（解除最小化）
_MB_ICONWARNING = 0x00000030
_MB_OK = 0x00000000
_MB_SETFOREGROUND = 0x00010000
_MB_TOPMOST = 0x00040000


def instance_app_dir(base: Path | None = None) -> Path:
    """单实例标识基准目录：`%LOCALAPPDATA%/dst-manager`（与日志/数据同根）。

    用户维度隔离：不同 Windows 用户之间互不阻断；`base` 仅供测试注入。
    """
    if base is not None:
        return base
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "dst-manager"


def mutex_name(key_base: Path | None = None) -> str:
    """会话级命名互斥量名：按用户维度确定性派生，同一用户进程间稳定可撞。"""
    digest = hashlib.sha1(
        str(instance_app_dir(key_base)).lower().encode("utf-8", "surrogatepass")
    ).hexdigest()[:12]
    return f"Local\\dst-manager-{digest}"


def acquire_instance_mutex(key_base: Path | None = None):
    """尝试成为唯一实例。返回守卫（int 内核句柄或放行标记）或 None（已有实例）。

    先 OpenMutexW 探测、再 CreateMutexW 建立，两道检查消除句柄复用歧义：
    探测失败后由本进程创建成功才可声明"唯一"；创建时返回
    ERROR_ALREADY_EXISTS 说明另有进程抢先，同样按"非唯一"处理。
    """
    if not WINDOWS:
        return _NO_GUARD_REQUIRED
    name = mutex_name(key_base)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    kernel32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    existing = kernel32.OpenMutexW(_SYNCHRONIZE, False, name)
    if existing:
        kernel32.CloseHandle(ctypes.c_void_p(existing))
        return None
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return handle


def release_instance_mutex(guard) -> None:
    """释放守卫句柄。平台放行标记与无效句柄一律无事发生；进程退出也会由内核回收。"""
    if guard is _NO_GUARD_REQUIRED or not isinstance(guard, int) or guard <= 0:
        return
    if not WINDOWS:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle(ctypes.c_void_p(guard))


def find_app_window(title: str = APP_WINDOW_TITLE, attempts: int = 8, delay: float = 0.15):
    """按标题寻找已启动实例的主窗口 HWND；找不到返回 None。

    已有实例可能仍在启动（窗口尚未创建），做短重试避免双击瞬间漏判；
    窗口标题缺失（异常改名）时找不到也不抛错，唤起步骤静默跳过。
    """
    if not WINDOWS:
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    for _ in range(attempts):
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            return hwnd
        time.sleep(delay)
    return None


def restore_and_foreground(hwnd: int) -> bool:
    """把既有窗口还原（若最小化）并置前；前台锁拦截时退化为任务栏闪烁。返回是否置前。"""
    if not WINDOWS:
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_int
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_int
    user32.FlashWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.FlashWindow.restype = ctypes.c_int
    user32.ShowWindow(hwnd, _SW_RESTORE)
    if user32.SetForegroundWindow(hwnd):
        return True
    user32.FlashWindow(hwnd, True)  # 前台锁拦截（罕见）时至少闪烁任务栏提示用户
    return False


def notify_already_running_and_raise(title: str = APP_WINDOW_TITLE) -> None:
    """第二个实例被拒的完整收尾：告警弹窗 → 用户确认后唤起既有窗口。

    顺序按用户裁决（弹窗→确认→切换）：置顶警告框让用户先看清报错；
    点击确定后由本进程（持前台权限）把已有实例窗口还原并置前。
    无窗口可唤起（首个实例仍在启动/异常）时仅报错退出，不抛异常。
    """
    print(
        "DST Manager 已在运行：第二个实例被拒绝，将切换到已打开的窗口。",
        file=sys.stderr,
    )
    if WINDOWS:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.MessageBoxW.restype = ctypes.c_int
        user32.MessageBoxW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint32,
        ]
        user32.MessageBoxW(
            None,
            "DST Manager 已在运行，无法启动第二个实例。\n\n"
            "点击“确定”后将切换到已打开的窗口。",
            f"{title} - 已在运行",
            _MB_TOPMOST | _MB_SETFOREGROUND | _MB_ICONWARNING | _MB_OK,
        )
    hwnd = find_app_window(title)
    if hwnd:
        restore_and_foreground(hwnd)