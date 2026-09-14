"""原子文件写入与「瞬时占用」有界重试。

为什么需要这一层：Windows 上「新建临时文件 → ``os.replace``」会在新文件刚落盘的瞬间
被安全软件 / EDR 的文件过滤驱动持有，rename 返回 ``ERROR_ACCESS_DENIED``(5)、
``ERROR_SHARING_VIOLATION``(32) 或 ``ERROR_LOCK_VIOLATION``(33)。这类拒绝窗口通常只有
毫秒级，但发布日志（``publish-journal.json``）是单次发布里重写最频繁的文件，任何一次
被拒绝都会让发布器按通用失败路径回滚整批并报 ``PUBLISH_ROLLED_BACK``。

因此这里对整条「写临时文件 + 原子替换」链路做有界指数退避重试：把外部过滤驱动的瞬时
占用与真实写盘失败区分开。重试预算耗尽时仍抛出**原始** ``OSError``（含 errno/winerror），
既有异常语义与上层回滚契约不变；退出前必须清理本轮被拒绝的临时文件，且清理失败不得
覆盖原始错误。
"""

import errno
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path

# 重试预算：5 次尝试、退避 20/40/80/160 ms（累计约 0.3 s），足以覆盖实测毫秒级占用窗口，
# 又不会让真正的写盘失败长时间阻塞持锁中的发布。
DEFAULT_ATTEMPTS = 5
DEFAULT_BASE_DELAY_SECONDS = 0.02
MAX_DELAY_SECONDS = 0.2

# Win32：ERROR_ACCESS_DENIED / ERROR_SHARING_VIOLATION / ERROR_LOCK_VIOLATION。
RETRIABLE_WINDOWS_ERRORS = frozenset({5, 32, 33})
# POSIX 等价物：权限被拒、资源忙、文本文件忙。
RETRIABLE_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EBUSY, errno.ETXTBSY})


def is_transient_contention(error: BaseException) -> bool:
    """判断异常是否属于「文件被短暂占用」这类可重试故障。"""
    if not isinstance(error, OSError):
        return False
    winerror = getattr(error, "winerror", None)
    if winerror is not None:
        return winerror in RETRIABLE_WINDOWS_ERRORS
    return error.errno in RETRIABLE_ERRNOS


def _remove_quietly(path: Path) -> None:
    """清理临时文件；文件仍被外部占用时不得让清理异常覆盖原始写入故障。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def retry_transient_contention(
    operation: Callable[[], None],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """按有界指数退避重试文件操作；不可重试或预算耗尽时原样抛出。"""
    if attempts < 1:
        raise ValueError("attempts 必须大于等于 1")
    delay = base_delay
    for attempt in range(1, attempts + 1):
        try:
            operation()
            return
        except OSError as error:
            if attempt >= attempts or not is_transient_contention(error):
                raise
            sleep(delay)
            delay = min(delay * 2, MAX_DELAY_SECONDS)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """把 ``text`` 原子写入 ``path``，瞬时占用按有界指数退避重试。

    每轮都使用新的唯一临时文件名：被过滤驱动持有的旧临时名不会拖住下一轮替换。
    """

    def write_once() -> None:
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_text(text, encoding=encoding)
            os.replace(temp, path)
        except OSError:
            _remove_quietly(temp)
            raise

    retry_transient_contention(write_once, attempts=attempts, base_delay=base_delay, sleep=sleep)
