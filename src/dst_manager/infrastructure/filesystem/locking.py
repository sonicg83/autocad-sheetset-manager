import ctypes
import errno
import os
import time
from pathlib import Path


class FileLockError(OSError):
    code = "BLOCKED_FILE_LOCK"


class WorkspaceTransactionBusyError(FileLockError):
    code = "PUBLISH_TRANSACTION_BUSY"


class WorkspaceTransactionLock:
    """跨进程串行化同一工作区的发布、恢复和已提交清单读取。"""

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_ALWAYS = 4
    FILE_ATTRIBUTE_NORMAL = 0x80
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    BUSY_WINDOWS_ERRORS = frozenset({32, 33})

    def __init__(self, path: Path, *, timeout_seconds: float = 0):
        self.path = path.resolve()
        self.timeout_seconds = timeout_seconds
        self.handle: int | None = None
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                if os.name == "nt":
                    self._acquire_windows()
                else:
                    self._acquire_posix()
                return self
            except WorkspaceTransactionBusyError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))

    def _acquire_windows(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        create_file.restype = ctypes.c_void_p
        ctypes.set_last_error(0)
        handle = create_file(
            str(self.path),
            self.GENERIC_READ | self.GENERIC_WRITE,
            0,
            None,
            self.OPEN_ALWAYS,
            self.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == self.INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            if error in self.BUSY_WINDOWS_ERRORS:
                raise WorkspaceTransactionBusyError(error, f"工作区发布事务正在执行：{self.path}")
            raise FileLockError(error, f"无法取得工作区发布事务锁：{self.path}")
        self.handle = handle

    def _acquire_posix(self) -> None:
        import fcntl

        self.stream = self.path.open("a+b")
        try:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            self.stream = None
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise WorkspaceTransactionBusyError(exc.errno, f"工作区发布事务正在执行：{self.path}") from exc
            raise FileLockError(exc.errno, f"无法取得工作区发布事务锁：{self.path}") from exc

    def __exit__(self, *_):
        if os.name == "nt" and self.handle is not None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [ctypes.c_void_p]
            close_handle.restype = ctypes.c_int
            close_handle(self.handle)
            self.handle = None
        elif self.stream is not None:
            import fcntl

            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()
            self.stream = None


class WindowsWriteLocks:
    """允许读取和删除，但拒绝其他进程取得写访问；发布时可原子替换。"""

    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self, paths: list[Path]):
        self.paths = sorted({path.resolve() for path in paths}, key=lambda item: str(item).casefold())
        self.handles: list[int] = []

    def __enter__(self):
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = ctypes.c_void_p
        for path in self.paths:
            handle = kernel32.CreateFileW(str(path), self.GENERIC_READ, self.FILE_SHARE_READ | self.FILE_SHARE_DELETE, None, self.OPEN_EXISTING, self.FILE_ATTRIBUTE_NORMAL, None)
            if handle == self.INVALID_HANDLE_VALUE:
                error = ctypes.get_last_error()
                self.__exit__(None, None, None)
                raise FileLockError(error, f"文件被占用，无法取得写阻断锁：{path}")
            self.handles.append(handle)
        return self

    def __exit__(self, *_):
        kernel32 = ctypes.windll.kernel32
        while self.handles:
            kernel32.CloseHandle(self.handles.pop())


class WindowsResultGuards:
    """在提交闭环窗口内保护既有结果，并用 delete-pending 占位保护删除结果。"""

    GENERIC_READ = 0x80000000
    DELETE = 0x00010000
    FILE_SHARE_READ = 0x00000001
    CREATE_NEW = 1
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self, existing_paths: list[Path], missing_paths: list[Path] | None = None):
        self.existing_paths = sorted(
            {path.resolve() for path in existing_paths},
            key=lambda item: str(item).casefold(),
        )
        self.missing_paths = sorted(
            {path.resolve() for path in (missing_paths or [])},
            key=lambda item: str(item).casefold(),
        )
        self.handles: list[int] = []
        self.placeholders: set[Path] = set()

    def __enter__(self):
        if os.name != "nt":
            raise FileLockError(
                "PUBLISH_RESULT_GUARD_UNSUPPORTED: 正式发布结果守卫仅支持 Windows",
            )
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = ctypes.c_void_p
        try:
            for path in self.existing_paths:
                self._open_handle(
                    kernel32,
                    path,
                    self.GENERIC_READ,
                    self.FILE_ATTRIBUTE_NORMAL,
                )
            for path in self.missing_paths:
                handle = self._open_handle(
                    kernel32,
                    path,
                    self.GENERIC_READ | self.DELETE,
                    self.FILE_ATTRIBUTE_NORMAL,
                    creation_disposition=self.CREATE_NEW,
                )
                self.placeholders.add(path)
                self._mark_delete_pending(kernel32, handle, path)
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def _open_handle(
        self,
        kernel32,
        path: Path,
        access: int,
        flags: int,
        *,
        creation_disposition: int | None = None,
    ) -> int:
        handle = kernel32.CreateFileW(
            str(path),
            access,
            self.FILE_SHARE_READ,
            None,
            creation_disposition or self.OPEN_EXISTING,
            flags,
            None,
        )
        if handle == self.INVALID_HANDLE_VALUE:
            raise FileLockError(ctypes.get_last_error(), f"无法保护已提交结果：{path}")
        self.handles.append(handle)
        return handle

    @staticmethod
    def _mark_delete_pending(kernel32, handle: int, path: Path) -> None:
        set_file_information = kernel32.SetFileInformationByHandle
        set_file_information.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        set_file_information.restype = ctypes.c_int
        delete_file = ctypes.c_ubyte(1)
        if not set_file_information(handle, 4, ctypes.byref(delete_file), ctypes.sizeof(delete_file)):
            raise FileLockError(ctypes.get_last_error(), f"无法保护删除结果名称：{path}")

    def protects_missing(self, path: Path) -> bool:
        return path.resolve() in self.placeholders

    def __exit__(self, *_):
        if os.name == "nt":
            kernel32 = ctypes.windll.kernel32
            while self.handles:
                kernel32.CloseHandle(self.handles.pop())
            # delete-pending 文件在最后一个句柄关闭时已由内核删除并释放名称；此后绝不能
            # 再按路径 unlink，否则可能删除恰好复用该名称的外部文件。
            self.placeholders.clear()
        else:
            self.placeholders.clear()
