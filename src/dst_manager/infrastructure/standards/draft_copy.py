"""已发布标准的草稿内容准备与受控模板复制。"""

from __future__ import annotations

import copy
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from dst_manager.domain.standards import parse_published_standard_document
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    resolve_asset_file,
    resolve_asset_files,
)
from dst_manager.infrastructure.standards.store_common import (
    ALLOWED_ASSET_SUFFIXES,
    DOCUMENT_NAME,
    MAX_ASSET_SOURCE_SIZE,
    _asset_gate_error,
    _error,
)

if TYPE_CHECKING:
    from dst_manager.infrastructure.standards.store import StandardStore


def prepare_published_copy(
    store: StandardStore, source_standard_id: str, standard_id: str, name: str,
) -> tuple[dict[str, object], tuple[tuple[str, Path, int], ...]]:
    """在调用方持有生命周期锁时读取源标准，只接受请求中的新身份与名称。"""
    document = store.get_document(source_standard_id)
    if document is None:
        raise _error("STANDARD_ID_NOT_FOUND", f"标准 {source_standard_id!r} 不存在")
    standard = parse_published_standard_document(document)
    for root in (store.published_root, store.official_root):
        source = store._published_dir(root, standard.standard_id)
        if (source / DOCUMENT_NAME).is_file():
            break
    else:
        raise _error("STANDARD_ID_NOT_FOUND", f"标准 {source_standard_id!r} 不存在")
    try:
        sources = resolve_asset_files(standard, source)
    except StandardAssetError as exc:
        raise _asset_gate_error(exc) from exc
    files: dict[str, tuple[str, Path, int]] = {}
    for relative, file in sources:
        if relative in files:
            continue  # 同一路径被多个资产声明时只复制一次。
        if Path(relative).suffix.casefold() not in ALLOWED_ASSET_SUFFIXES:
            raise _error("STANDARD_ASSET_SOURCE_INVALID", "模板文件必须是 .dwg 或 .dwt")
        try:
            size = file.stat().st_size
        except OSError as exc:
            raise _error("STANDARD_ASSET_COPY_FAILED", f"读取源模板失败：{exc}") from exc
        if size > MAX_ASSET_SOURCE_SIZE:
            raise _error("STANDARD_ASSET_SOURCE_INVALID", "模板文件超过受控复制大小上限")
        files[relative] = (relative, file, size)
    result = copy.deepcopy(document)
    result.update(standard_id=standard_id, name=name, published_at=None)
    return result, tuple(files.values())


def copy_published_assets(target: Path, files: tuple[tuple[str, Path, int], ...]) -> None:
    """只写新建草稿的声明文件；失败由创建流程撤销整份草稿。"""
    for relative, source, expected_size in files:
        try:
            destination = resolve_asset_file(target, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            with destination.open("rb+") as copied:
                os.fsync(copied.fileno())
            if destination.stat().st_size != expected_size:
                raise _error("STANDARD_ASSET_COPY_FAILED", "模板复制结果大小与来源不一致")
        except StandardAssetError as exc:
            raise _asset_gate_error(exc) from exc
        except OSError as exc:
            raise _error("STANDARD_ASSET_COPY_FAILED", f"复制源标准模板失败：{exc}") from exc
