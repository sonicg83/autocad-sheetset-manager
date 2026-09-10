"""一次性保存授权存储（PLAN-DM-020 Task 8 / ARCH-DM-006 §9.1、§11）。

桌面壳的原生"另存为"确认后，宿主在此创建随机、一次性、短时有效的
``save_grant_id``，并绑定扩展/动作/工作区身份、规范化目标 ``.xlsx`` 路径与
选择时目标的存在性、文件身份（device/inode/size/mtime_ns）和 SHA-256 基线。

规则：

- 授权只保存在进程内（Task 2 已确认授权不落库），宿主重启即全部失效；
- 消费是原子的：同一授权只有一个消费者成功，其余一律 ``SAVE_GRANT_INVALID``
  （任何消费尝试——无论身份是否匹配——都会烧毁授权，防伪造探测）；
- 消费时重新计算目标基线并与选择时基线比对，任何漂移（创建/修改/删除）
  或基线不可读（锁定/权限/竞态）按 ``EXPORT_DESTINATION_CHANGED`` 拒绝，
  绝不把旧决策用于新目标；基线读取不裸抛 OSError（fail-closed）。
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


#: 目标不存在：除 ``existed`` 外全为 None（授权创建与消费复核共用）。
_ABSENT = TargetBaseline(
    existed=False, device=None, inode=None, size_bytes=None, modified_ns=None,
    sha256=None,
)

#: 目标存在但基线不可读（stat/open 之间的删除竞态、Excel/AV 独占锁定、
#: 权限变化——Windows 上是常态）：身份无法确认，由调用方决定归类
#: （Artifact 可用性 → CHANGED；授权消费 → EXPORT_DESTINATION_CHANGED），
#: 绝不把读失败裸抛为非契约 500。
_UNREADABLE = TargetBaseline(
    existed=True, device=None, inode=None, size_bytes=None, modified_ns=None,
    sha256=None,
)


def capture_baseline(target: Path) -> TargetBaseline:
    """记录目标当前的存在性、文件身份与 SHA-256（授权创建与发布复核共用）。

    不裸抛 OSError：``FileNotFoundError`` 返回不存在基线；其他 OS 级读失败
    返回"目标存在但基线不可读"（``_UNREADABLE``，``existed=True`` 且身份
    字段全 None），语义由调用方归类——可用性派生按 CHANGED、授权消费按
    EXPORT_DESTINATION_CHANGED，均为 fail-closed 且契约化。
    """
    try:
        stat = target.stat()
    except FileNotFoundError:
        return _ABSENT
    except OSError:
        # stat 失败（如父目录权限）：存在性本身无法确认，同样按不可读处理，
        # 调用方 fail-closed 拒绝，绝不逃逸 500。
        return _UNREADABLE
    try:
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(_HASH_CHUNK), b""):
                digest.update(chunk)
    except OSError:
        # 文件在 stat 与 open 之间被删除/锁定/权限变化：身份无法确认。
        return _UNREADABLE
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
        baseline = capture_baseline(grant.target)
        if baseline.existed and baseline.sha256 is None:
            # 目标存在但基线不可读（锁定/权限/竞态）：身份无法确认，fail-closed
            # 归类为 EXPORT_DESTINATION_CHANGED（授权已随消费烧毁——这正是
            # execute 通道 OSError 兜底注释声称"不会发生在消费后"的例外来源，
            # 此处显式包装为 SaveGrantError，保证不逃逸为非契约 500）。
            raise SaveGrantError(
                "EXPORT_DESTINATION_CHANGED",
                "保存目标当前不可读（可能被其他程序占用或权限不足），无法确认其未变化",
            )
        if baseline != grant.baseline:
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
