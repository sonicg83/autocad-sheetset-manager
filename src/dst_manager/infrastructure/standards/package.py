"""`.dststandard` 标准包安全读取（PLAN-DM-035 Task 3）。

标准包是 zip 容器：`manifest.json` 保存标准文档，其余条目为模板资产。
读取阶段即拒绝路径逃逸（``..``、绝对路径、重复规范化路径）、可执行扩展名、
超大条目与非法 Schema，不解压任何未通过校验的条目。
"""

import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dst_manager.domain.standards import (
    DrawingStandard,
    StandardSchemaError,
    loads_standard_document,
)

MANIFEST_NAME = "manifest.json"
# 单条目与整包大小上限：标准模板远小于该量级，超限视为异常输入。
MAX_ENTRY_SIZE = 64 * 1024 * 1024
MAX_PACKAGE_SIZE = 256 * 1024 * 1024

# 标准包不得包含 Python、DLL、SCR、Shell、AutoLISP 或其他可执行内容。
FORBIDDEN_EXTENSIONS = frozenset(
    {
        ".py", ".pyc", ".pyo", ".pyd", ".dll", ".exe", ".scr", ".lsp", ".fas",
        ".vlx", ".bat", ".cmd", ".ps1", ".com", ".sh", ".vbs", ".js", ".msi",
    }
)


class StandardPackageError(Exception):
    """标准包读取失败；消息以稳定错误码开头。"""


@dataclass(frozen=True, slots=True)
class PackageEntry:
    """包内一条已验证条目；``path`` 为规范化 POSIX 相对路径。"""

    path: str
    size: int


@dataclass(frozen=True, slots=True)
class LoadedStandardPackage:
    """读取通过校验的标准包；文件本体仍在包内，由导入方按条目复制。"""

    standard: DrawingStandard
    entries: tuple[PackageEntry, ...]
    source_path: Path


def _error(code: str, detail: str) -> StandardPackageError:
    return StandardPackageError(f"{code}: {detail}")


def _normalize_entry_name(name: str) -> str | None:
    """规范化 zip 条目名；目录条目返回 None，非法路径抛错。"""
    if name.endswith("/"):
        return None
    if not name or name.startswith(("/", "\\")):
        raise _error("STANDARD_PACKAGE_PATH_INVALID", f"条目 {name!r} 不是合法相对路径")
    if ":" in name.split("/", 1)[0]:
        raise _error("STANDARD_PACKAGE_PATH_INVALID", f"条目 {name!r} 疑似绝对路径")
    normalized = posixpath.normpath(name.replace("\\", "/"))
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise _error("STANDARD_PACKAGE_PATH_INVALID", f"条目 {name!r} 包含逃逸分量")
    return normalized


class StandardPackageReader:
    """读取并校验 `.dststandard` 包；不写入、不执行包内任何内容。"""

    def read(self, path: Path) -> LoadedStandardPackage:
        source = Path(path)
        try:
            archive = zipfile.ZipFile(source)
        except (OSError, zipfile.BadZipFile) as exc:
            raise _error("STANDARD_PACKAGE_INVALID", f"无法打开标准包：{exc}") from exc
        with archive:
            normalized_names: set[str] = set()
            entries: list[PackageEntry] = []
            manifest_text: str | None = None
            total_size = 0
            for info in archive.infolist():
                normalized = _normalize_entry_name(info.filename)
                if normalized is None:
                    continue
                if normalized in normalized_names:
                    raise _error(
                        "STANDARD_PACKAGE_PATH_INVALID",
                        f"重复规范化路径 {normalized!r}",
                    )
                normalized_names.add(normalized)
                suffix = PurePosixPath(normalized).suffix.lower()
                if suffix in FORBIDDEN_EXTENSIONS:
                    raise _error(
                        "STANDARD_PACKAGE_EXTENSION_FORBIDDEN",
                        f"条目 {normalized!r} 使用禁止的可执行扩展名 {suffix!r}",
                    )
                if info.file_size > MAX_ENTRY_SIZE:
                    raise _error(
                        "STANDARD_PACKAGE_TOO_LARGE",
                        f"条目 {normalized!r} 超过单文件大小上限",
                    )
                total_size += info.file_size
                if total_size > MAX_PACKAGE_SIZE:
                    raise _error(
                        "STANDARD_PACKAGE_TOO_LARGE", "包总大小超过上限"
                    )
                if normalized == MANIFEST_NAME:
                    try:
                        manifest_text = archive.read(info).decode("utf-8")
                    except (OSError, UnicodeDecodeError) as exc:
                        raise _error(
                            "STANDARD_PACKAGE_MANIFEST_INVALID",
                            f"manifest 读取失败：{exc}",
                        ) from exc
                else:
                    entries.append(PackageEntry(path=normalized, size=info.file_size))
        if manifest_text is None:
            raise _error("STANDARD_PACKAGE_MANIFEST_MISSING", "包内缺少 manifest.json")
        try:
            standard = loads_standard_document(manifest_text)
        except StandardSchemaError as exc:
            raise _error("STANDARD_PACKAGE_MANIFEST_INVALID", str(exc)) from exc
        return LoadedStandardPackage(
            standard=standard, entries=tuple(entries), source_path=source
        )
