"""DST Builder 桌面壳的应用身份、单实例守卫与 frozen stdio 重定向。

独立于 DST Manager 的对应实现（``dst_manager.infrastructure.single_instance`` /
``dst_manager.runtime``）：不 import Manager 任何模块，应用 ID、互斥量名、
数据目录与窗口标题全部落在 ``dst-builder`` 命名空间，保证两个产品可在同一
机器、同一用户会话下并行运行互不抢占（PLAN-DB-001 Task 11）。

单实例守卫动机：两个 Builder 壳实例会绑定同一项目目录并同时操作同一
``project.dstb``（SQLite 任务队列、发布事务）互相踩踏。仅标准库 + ctypes
直调 Win32（项目不引入 pywin32）：

- 命名互斥量（CreateMutexW）：内核对象，进程退出（含崩溃）自动释放；
  ``Local\\`` 前缀限定会话内可见，无需管理员权限。
- 非 Windows 平台守卫直接放行（桌面壳本就只面向 Windows 11），保证
  Linux CI 可运行；平台条件为模块级开关、单测可注入。
"""

from __future__ import annotations

import ctypes
import hashlib
import sys
from pathlib import Path

# 平台开关：Windows 才参与守卫；单测可 monkeypatch 模拟非 Windows。
WINDOWS = sys.platform == "win32"

# 非 Windows 平台的放行标记（恒为"唯一实例"）；与内核句柄（int）区分。
_NO_GUARD_REQUIRED = object()

# Win32 常量（ctypes 直调，避免 magic number）。
_ERROR_ALREADY_EXISTS = 183
_SYNCHRONIZE = 0x00100000
_MB_ICONWARNING = 0x00000030
_MB_OK = 0x00000000
_MB_SETFOREGROUND = 0x00010000
_MB_TOPMOST = 0x00040000

__all__ = [
    "APP_DATA_DIR_NAME",
    "APP_ID",
    "APP_TITLE",
    "acquire_instance_mutex",
    "app_data_dir",
    "is_frozen",
    "log_dir",
    "mutex_name",
    "notify_already_running_and_raise",
    "redirect_frozen_stdio",
    "release_instance_mutex",
    "resource_dir",
]

# 资源与身份解析统一走 dst_builder.runtime（frozen 双路径的唯一权威）。
from ..runtime import (
    APP_DATA_DIR_NAME,
    APP_ID,
    APP_TITLE,
    app_data_dir,
    is_frozen,
    log_dir,
    redirect_frozen_stdio,
    resource_dir,
)


def mutex_name(key_base: Path | None = None) -> str:
    """会话级命名互斥量名：按用户维度确定性派生，同一用户进程间稳定可撞。

    ``Local\\dst-builder-`` 前缀与 Manager 的 ``Local\\dst-manager-`` 天然互异，
    同一基准目录下两产品的互斥量名也绝不相同。
    """
    digest = hashlib.sha1(
        str(app_data_dir(key_base)).lower().encode("utf-8", "surrogatepass")
    ).hexdigest()[:12]
    return f"Local\\dst-builder-{digest}"


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


def notify_already_running_and_raise(title: str = APP_TITLE) -> None:
    """第二个实例被拒的收尾：告警弹窗提示用户切回已打开的窗口。

    Builder 壳窗口由 WebView2 托管、标题固定为 APP_TITLE，用户据此切换；
    无窗口可唤起（首个实例仍在启动/异常）时仅报错退出，不抛异常。
    """
    print(
        "DST Builder 已在运行：第二个实例被拒绝，请切换到已打开的窗口。",
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
            "DST Builder 已在运行，无法启动第二个实例。\n\n请切换到已打开的窗口。",
            f"{title} - 已在运行",
            _MB_TOPMOST | _MB_SETFOREGROUND | _MB_ICONWARNING | _MB_OK,
        )
