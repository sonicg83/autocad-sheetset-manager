"""资产文件存储与 SQLite 仓储适配器（SPEC-DB-001 §3 ``assets/`` 与 ``assets`` 表）。

内容寻址布局为 ``assets/<role>/<sha256>.<ext>``。文件落盘采用“项目内临时
文件 + ``os.replace`` 原子改名”，临时文件与最终文件同目录，保证改名在同一
卷内完成。本模块只提供 IO 原语与行映射，不做校验决策、不开事务——纳入
流程的编排与校验在 application 层（事务边界同样在 application 层）。
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from dst_builder.domain.models import AssetRole
from dst_builder.domain.paths import (
    ProjectPathError,
    casefold_collisions,
    resolve_within_project,
)
from dst_builder.infrastructure.persistence.database import AssetRow

__all__ = [
    "MAX_ASSET_BYTES",
    "AssetRecord",
    "AssetRepository",
    "SqliteAssetRepository",
    "asset_relative_path",
    "atomic_replace",
    "file_sha256",
    "make_temp_file",
    "place_file_atomically",
    "stream_copy",
]

# §4：单文件不超过 2 GiB（2 * 1024**3 字节，不含）。
MAX_ASSET_BYTES = 2 * 1024**3

ASSET_DIRECTORY_BY_ROLE: dict[AssetRole, str] = {
    AssetRole.BASE: "base",
    AssetRole.LAYOUT: "layout",
}

_COPY_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class AssetRecord:
    """``assets`` 表一行的不可变投影（relative_path 为 POSIX 相对路径）。"""

    id: str
    role: AssetRole
    relative_path: str
    sha256: str
    size: int
    source_name: str


class AssetRepository(Protocol):
    """``assets`` 表的持久化端口；事务由 application 层控制。"""

    def find_by_role_and_sha256(self, role: AssetRole, sha256: str) -> AssetRecord | None: ...

    def insert(self, record: AssetRecord) -> None: ...

    def load(self, asset_id: str) -> AssetRecord | None: ...


def file_sha256(path: Path) -> tuple[int, str]:
    """流式计算文件的 ``(size, sha256)``。"""
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        while chunk := handle.read(_COPY_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def stream_copy(source: Path, target: Path) -> int:
    """把源文件流式复制为目标文件，返回复制字节数。

    application 层在复制前后分别校验哈希；测试可通过替换本函数模拟
    “复制中源文件变化”。
    """
    size = 0
    with Path(source).open("rb") as src, Path(target).open("wb") as dst:
        while chunk := src.read(_COPY_CHUNK):
            dst.write(chunk)
            size += len(chunk)
    return size


def asset_relative_path(role: AssetRole, sha256: str, suffix: str) -> str:
    """§3 内容寻址相对路径 ``assets/<role>/<sha256>.<ext>``（POSIX、小写扩展名）。"""
    directory = ASSET_DIRECTORY_BY_ROLE[role]
    return f"assets/{directory}/{sha256}{suffix.lower()}"


def make_temp_file(project_root: Path, role: AssetRole) -> Path:
    """在项目内 ``assets/<role>/`` 创建唯一临时文件（保证与最终文件同卷）。"""
    directory = Path(project_root) / "assets" / ASSET_DIRECTORY_BY_ROLE[role]
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"incoming-{uuid.uuid4().hex}.tmp"


def atomic_replace(source: Path, target: Path) -> None:
    """同卷原子改名；测试可通过替换本函数模拟改名失败。"""
    os.replace(source, target)


def place_file_atomically(project_root: Path, relative_path: str, temp: Path) -> Path:
    """以内容寻址名原子落盘：先做项目内边界与大小写碰撞校验，再 ``os.replace``。"""
    final = resolve_within_project(project_root, relative_path)
    directory = final.parent
    directory.mkdir(parents=True, exist_ok=True)
    collisions = casefold_collisions((item.name for item in directory.iterdir()), final.name)
    if collisions:
        raise ProjectPathError(
            f"存在仅大小写不同的既有文件，拒绝落盘：{collisions[0]!r}"
        )
    atomic_replace(temp, final)
    return final


class SqliteAssetRepository:
    """``assets`` 表适配器：只做行映射，唯一约束兜底由 §3 迁移保证。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_role_and_sha256(self, role: AssetRole, sha256: str) -> AssetRecord | None:
        row = self._session.scalars(
            select(AssetRow).where(AssetRow.role == role.value, AssetRow.sha256 == sha256)
        ).first()
        return _to_record(row) if row is not None else None

    def insert(self, record: AssetRecord) -> None:
        self._session.add(
            AssetRow(
                id=record.id,
                role=record.role.value,
                relative_path=record.relative_path,
                sha256=record.sha256,
                size=record.size,
                source_name=record.source_name,
            )
        )
        # flush 让 (role, sha256) 唯一约束在调用方事务内提前暴露。
        self._session.flush()

    def load(self, asset_id: str) -> AssetRecord | None:
        row = self._session.get(AssetRow, asset_id)
        return _to_record(row) if row is not None else None


def _to_record(row: AssetRow) -> AssetRecord:
    return AssetRecord(
        id=row.id,
        role=AssetRole(row.role),
        relative_path=row.relative_path,
        sha256=row.sha256,
        size=row.size,
        source_name=row.source_name,
    )
