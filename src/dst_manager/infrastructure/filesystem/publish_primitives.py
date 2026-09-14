"""发布事务文件原语（自 publisher.py 拆分；哈希、基线、替换与身份识别）。"""

import ctypes
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from dst_manager.infrastructure.filesystem.publish_errors import PublishBaselineError


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ExpectedFileBaseline:
    """调用方在发布前确认的不可变文件内容与身份基准。"""

    sha256: str
    identity: tuple[int, int]


def capture_file_baseline(path: Path) -> ExpectedFileBaseline | None:
    """同时捕获文件哈希和身份；不存在的路径以 ``None`` 表示。"""
    if not path.exists():
        return None
    before = path.stat()
    digest = file_sha256(path)
    try:
        after = path.stat()
    except FileNotFoundError as exc:
        raise PublishBaselineError(f"捕获发布基准时目标已变化：{path}") from exc
    before_identity = (before.st_dev, before.st_ino)
    after_identity = (after.st_dev, after.st_ino)
    if after_identity != before_identity:
        raise PublishBaselineError(f"捕获发布基准时目标已变化：{path}")
    return ExpectedFileBaseline(digest, before_identity)


def move_no_replace(source: Path, target: Path) -> None:
    if os.name != "nt":
        os.link(source, target)
        source.unlink()
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file = kernel32.MoveFileW
    move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    move_file.restype = ctypes.c_int
    ctypes.set_last_error(0)
    if not move_file(str(source), str(target)):
        raise ctypes.WinError(ctypes.get_last_error())


def replace_existing(source: Path, target: Path, backup: Path) -> None:
    if backup.exists():
        raise FileExistsError(f"PUBLISH_REPLACE_BACKUP_EXISTS: {backup}")
    if os.name != "nt":
        os.replace(target, backup)
        try:
            os.replace(source, target)
        except Exception:
            os.replace(backup, target)
            raise
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    replace_file = kernel32.ReplaceFileW
    replace_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    replace_file.restype = ctypes.c_int
    ctypes.set_last_error(0)
    if not replace_file(str(target), str(source), str(backup), 0x2, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def before_snapshot_path(before_dir: Path, workspace_root: Path, target: Path) -> Path:
    return before_dir / target.relative_to(workspace_root)


def replacement_backup_path(target: Path, operation_id: str) -> Path:
    return target.with_name(f".{target.name}.{operation_id}.replaced")


def file_identity(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_dev, stat.st_ino]
