"""标准库仓储的公共数据类型、路径校验和发布门禁。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dst_manager.domain.standard_identity import parse_standard_id
from dst_manager.domain.standard_naming import publish_naming_diagnostics
from dst_manager.domain.standard_rules import publish_diagnostics
from dst_manager.domain.standards import (
    DrawingStandard,
    StandardSchemaError,
    parse_published_standard_document,
)
from dst_manager.infrastructure.standards.asset_paths import StandardAssetError

LIBRARY_LOCK_NAME = ".standards.lock"
LIBRARY_LOCK_TIMEOUT_SECONDS = 30.0

DOCUMENT_NAME = "document.json"

MAX_SEGMENT_LENGTH = 128

MANAGED_ASSET_PREFIX = "managed-"

MAX_ASSET_SOURCE_SIZE = 64 * 1024 * 1024

ALLOWED_ASSET_SUFFIXES = frozenset({".dwg", ".dwt"})

_ASSET_NAME_ATTEMPTS = 5

_COPY_CHUNK_SIZE = 1024 * 1024

WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)

_SEGMENT_ERROR_CODES = {
    "draft": "STANDARD_DRAFT_ID_INVALID",
    "id": "STANDARD_ID_INVALID",
}

_SEGMENT_LABELS = {"draft": "草稿 ID", "id": "标准 ID"}

class StandardStoreError(Exception):
    """标准库操作失败；消息以稳定错误码开头。"""

@dataclass(frozen=True, slots=True)
class StandardSummary:
    """标准库列表条目；草稿的 ``published_at`` 为空。"""

    source: Literal["official", "user"]
    status: Literal["published", "draft"]
    standard_id: str
    name: str
    description: str
    published_at: int | None
    draft_id: str | None = None

@dataclass(frozen=True, slots=True)
class StandardDraft:
    draft_id: str
    document: dict[str, object]

@dataclass(frozen=True, slots=True)
class PublishedStandard:
    standard_id: str
    published_at: int
    name: str
    description: str
    root: Path

def _error(code: str, detail: str) -> StandardStoreError:
    return StandardStoreError(f"{code}: {detail}")

def _asset_gate_error(exc: StandardAssetError) -> StandardStoreError:
    """资产门禁错误保留稳定码前缀，统一以仓储错误类型向上传递。"""
    return StandardStoreError(str(exc))

def _safe_segment(value: str, kind: str) -> str:
    """校验单个路径段；``kind`` 为 ``draft``/``id``，决定稳定错误码。

    标准库目录名只有一层，任何分隔符、相对分量、盘符、首尾空白、尾随点、
    Windows 保留设备名、控制字符与超长输入都不允许进入文件系统。
    """
    code = _SEGMENT_ERROR_CODES[kind]
    label = _SEGMENT_LABELS[kind]
    if not isinstance(value, str) or not value:
        raise _error(code, f"{label}不能为空")
    if len(value) > MAX_SEGMENT_LENGTH:
        raise _error(code, f"{label}超过 {MAX_SEGMENT_LENGTH} 个字符")
    if value != value.strip():
        raise _error(code, f"{label} {value!r} 含首尾空白")
    if value in (".", ".."):
        raise _error(code, f"{label} {value!r} 是相对路径分量")
    if "/" in value or "\\" in value or ":" in value:
        raise _error(code, f"{label} {value!r} 含路径分隔符或盘符")
    if value.endswith("."):
        raise _error(code, f"{label} {value!r} 以点结尾")
    if any(ord(char) < 32 for char in value):
        raise _error(code, f"{label} {value!r} 含控制字符")
    if value.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        raise _error(code, f"{label} {value!r} 是 Windows 保留设备名")
    if kind == "id":
        try:
            return parse_standard_id(value)
        except ValueError as exc:
            raise _error(code, f"标准 ID {value!r} 不是带连字符的 UUID") from exc
    return value

def _published_or_store_error(document: Mapping[str, object]) -> DrawingStandard:
    """发布路径的完整门禁：Schema 解析 + 派生/命名发布诊断。"""
    try:
        standard = parse_published_standard_document(document)
    except StandardSchemaError as exc:
        raise StandardStoreError(str(exc)) from exc
    gate = _publish_gate_error(standard)
    if gate is not None:
        raise gate
    return standard

def _publish_gate_error(standard: DrawingStandard) -> StandardStoreError | None:
    """首个发布阻断错误；warning 不阻断。仓储层保留一份防线，不得绕过。"""
    for diagnostic in (
        *publish_diagnostics(standard),
        *publish_naming_diagnostics(standard),
    ):
        if diagnostic.is_error:
            return StandardStoreError(f"{diagnostic.code}: {diagnostic.message}")
    return None

def _norm(name: str) -> str:
    import posixpath

    return posixpath.normpath(name.replace("\\", "/"))
