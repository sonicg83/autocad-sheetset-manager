"""一次性保存授权存储（PLAN-DM-020 Task 8 / ARCH-DM-006 §9.1、§11）。

桌面壳的原生"另存为"确认后，宿主在此创建随机、一次性、短时有效的
``save_grant_id``，并绑定扩展/动作/工作区身份、规范化目标 ``.xlsx`` 路径与
选择时目标的存在性、文件身份（device/inode/size/mtime_ns）和 SHA-256 基线。

规则：

- 授权只保存在进程内（Task 2 已确认授权不落库），宿主重启即全部失效；
- 消费是原子的：同一授权只有一个消费者成功，其余一律 ``SAVE_GRANT_INVALID``
  （任何消费尝试——无论身份是否匹配——都会烧毁授权，防伪造探测）；
- 消费时重新计算目标基线并与选择时基线比对，任何漂移（创建/修改/删除）按
  ``EXPORT_DESTINATION_CHANGED`` 拒绝，绝不把旧决策用于新目标。
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

__all__ = [
    "ConsumedSaveGrant",
    "SaveGrantError",
    "SaveGrantReceipt",
    "SaveGrantStore",
    "TargetBaseline",
    "capture_baseline",
]

_HASH_CHUNK = 1 << 20


class SaveGrantError(RuntimeError):
    """授权拒绝；``code`` 与 ARCH-DM-006 §12 平台错误码对齐。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TargetBaseline:
    """选择保存目标时的文件基线；目标不存在时除 ``existed`` 外全为 None。"""

    existed: bool
    device: int | None
    inode: int | None
    size_bytes: int | None
    modified_ns: int | None
    sha256: str | None


@dataclass(frozen=True, slots=True)
class SaveGrantReceipt:
    save_grant_id: str
    file_name: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ConsumedSaveGrant:
    save_grant_id: str
    extension_id: str
    action_id: str
    workspace_id: str
    target: Path
    baseline: TargetBaseline


@dataclass(frozen=True, slots=True)
class _Grant:
    save_grant_id: str
    extension_id: str
    action_id: str
    workspace_id: str
    target: Path
    baseline: TargetBaseline
    expires_at: datetime


def capture_baseline(target: Path) -> TargetBaseline:
    """记录目标当前的存在性、文件身份与 SHA-256（授权创建与发布复核共用）。"""
    try:
        stat = target.stat()
    except FileNotFoundError:
        return TargetBaseline(
            existed=False, device=None, inode=None, size_bytes=None,
            modified_ns=None, sha256=None,
        )
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return TargetBaseline(
        existed=True,
        device=stat.st_dev,
        inode=stat.st_ino,  # Windows/NTFS 可用；不假设恒非零
        size_bytes=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


class SaveGrantStore:
    """进程内一次性保存授权存储（线程安全；创建/消费均持锁）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._grants: dict[str, _Grant] = {}

    def active_count(self) -> int:
        """当前有效授权数量（诊断用；取消不创建、消费即销毁）。"""
        with self._lock:
            return len(self._grants)

    def create(
        self,
        extension_id: str,
        action_id: str,
        workspace_id: str,
        target: Path,
        ttl_seconds: int = 300,
    ) -> SaveGrantReceipt:
        """为用户确认的目标创建一次性授权；目标强制规范 ``.xlsx`` 后缀。"""
        normalized = Path(target)
        if normalized.suffix.lower() != ".xlsx":
            normalized = normalized.with_name(normalized.name + ".xlsx")
        normalized = normalized.resolve()  # 规范路径：消除 .. 与符号链接
        grant = _Grant(
            save_grant_id=uuid.uuid4().hex,
            extension_id=extension_id,
            action_id=action_id,
            workspace_id=workspace_id,
            target=normalized,
            baseline=capture_baseline(normalized),
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        with self._lock:
            self._grants[grant.save_grant_id] = grant
        return SaveGrantReceipt(
            save_grant_id=grant.save_grant_id,
            file_name=normalized.name,
            expires_at=grant.expires_at,
        )

    def consume(
        self, save_grant_id: str, extension_id: str, action_id: str, workspace_id: str
    ) -> ConsumedSaveGrant:
        """原子消费授权；身份不匹配/过期/漂移一律拒绝且授权即被烧毁。"""
        with self._lock:
            grant = self._grants.pop(save_grant_id, None)
        if grant is None:
            raise SaveGrantError(
                "SAVE_GRANT_INVALID", "保存授权不存在、已被使用或已被取消"
            )
        if datetime.now(UTC) >= grant.expires_at:
            raise SaveGrantError("SAVE_GRANT_INVALID", "保存授权已过期")
        if (
            grant.extension_id != extension_id
            or grant.action_id != action_id
            or grant.workspace_id != workspace_id
        ):
            raise SaveGrantError(
                "SAVE_GRANT_INVALID", "保存授权与请求的扩展/动作/工作区不匹配"
            )
        if capture_baseline(grant.target) != grant.baseline:
            raise SaveGrantError(
                "EXPORT_DESTINATION_CHANGED", "保存目标在选择后发生了变化"
            )
        return ConsumedSaveGrant(
            save_grant_id=grant.save_grant_id,
            extension_id=grant.extension_id,
            action_id=grant.action_id,
            workspace_id=grant.workspace_id,
            target=grant.target,
            baseline=grant.baseline,
        )
