"""标准包导入预检的限时快照与凭证（PLAN-DM-041 Task 5）。

两步导入的第一步：把用户选定的 `.dststandard` 复制到应用数据目录下的限时快照
根，再由上层用既有安全读取器与资产门禁校验，并把结果与一个随机、不可猜测的
凭证关联起来。确认导入只消费快照字节，不再读原路径。

边界（SPEC-DM-019 §4.2）：

- 快照根固定为 ``<data_dir>/tmp/standard-import-previews``，不进入任何工程目录；
- 来源扩展名白名单只有 ``.dststandard``；压缩源文件不超过 256 MiB；
- 复制流式写入随机临时文件，完成后原子定稿；中断不留半成品；
- 凭证默认 15 分钟有效，过期、取消或**进程重启**后失效（凭证只存在于内存中）；
- 过期与取消的快照立即清理，不在快照根无限累积。
"""

from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ALLOWED_PACKAGE_SUFFIXES",
    "MAX_PACKAGE_SOURCE_BYTES",
    "PREVIEW_TTL_SECONDS",
    "ImportPreviewError",
    "ImportPreviewRecord",
    "ImportPreviewStore",
]

#: 凭证有效期（秒）。
PREVIEW_TTL_SECONDS = 15 * 60
#: 单个压缩来源文件的字节上限。
MAX_PACKAGE_SOURCE_BYTES = 256 * 1024 * 1024
#: 允许导入的来源扩展名白名单。
ALLOWED_PACKAGE_SUFFIXES = frozenset({".dststandard"})
#: 流式复制块大小。
_COPY_CHUNK_SIZE = 1024 * 1024


class ImportPreviewError(Exception):
    """预检失败；消息以稳定错误码开头，如 ``STANDARD_IMPORT_SOURCE_INVALID``。"""


def _error(code: str, detail: str) -> ImportPreviewError:
    return ImportPreviewError(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class ImportPreviewRecord:
    """一条预检凭证记录；``consumed`` 保存成功确认的短期幂等回执。"""

    preview_id: str
    snapshot_path: Path
    expires_at: float
    payload: dict[str, object]
    consumed: dict[str, object] | None = None
    extras: dict[str, object] = field(default_factory=dict)

    def is_expired(self, now: float) -> bool:
        """是否已过期；``now`` 由持有者传入，使测试可注入时钟。"""
        return now >= self.expires_at


class ImportPreviewStore:
    """限时快照根与内存凭证表。

    ``clock`` 可注入，便于测试过期行为而不真的等待；凭证表只存在于进程内，
    因此重启后所有凭证自动失效（上层表现为 404）。
    """

    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: float = PREVIEW_TTL_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self.root = Path(root)
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._records: dict[str, ImportPreviewRecord] = {}
        self._lock = threading.Lock()

    # ---- 快照 ------------------------------------------------------------

    def snapshot_source(self, source_path: Path) -> Path:
        """校验来源并流式复制到快照根；返回快照文件路径。

        来源只作一次性读取：不写回来源、不把来源路径写进任何持久化结构。
        """
        source = Path(source_path)
        if source.suffix.casefold() not in ALLOWED_PACKAGE_SUFFIXES:
            raise _error(
                "STANDARD_IMPORT_SOURCE_INVALID",
                f"来源 {source.name!r} 必须是 .dststandard 文件",
            )
        if not source.is_absolute() or not source.is_file():
            raise _error(
                "STANDARD_IMPORT_SOURCE_NOT_FOUND",
                f"来源 {str(source_path)!r} 不存在或不是文件",
            )
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise _error(
                "STANDARD_IMPORT_SOURCE_NOT_FOUND", f"无法读取来源：{exc}"
            ) from exc
        if size > MAX_PACKAGE_SOURCE_BYTES:
            raise _error(
                "STANDARD_IMPORT_SOURCE_TOO_LARGE",
                f"来源 {source.name!r} 超过 {MAX_PACKAGE_SOURCE_BYTES} 字节上限",
            )
        self.root.mkdir(parents=True, exist_ok=True)
        final = self.root / f"{uuid.uuid4().hex}{source.suffix.casefold()}"
        temp = self.root / f".{uuid.uuid4().hex}.copying"
        try:
            with source.open("rb") as reader, temp.open("wb") as writer:
                shutil.copyfileobj(reader, writer, length=_COPY_CHUNK_SIZE)
                writer.flush()
                os.fsync(writer.fileno())
            if temp.stat().st_size != size:
                raise _error(
                    "STANDARD_IMPORT_COPY_FAILED",
                    "快照大小与来源不一致，已放弃复制",
                )
            os.replace(temp, final)
        except OSError as exc:
            raise _error("STANDARD_IMPORT_COPY_FAILED", f"复制来源失败：{exc}") from exc
        finally:
            temp.unlink(missing_ok=True)
        return final

    def expires_at_iso(self, record: ImportPreviewRecord) -> str:
        """把单调时钟的到期时刻换算为 UTC ISO-8601 字符串（供前端展示与刷新）。"""
        from datetime import UTC, datetime, timedelta

        remaining = max(0.0, record.expires_at - self._clock())
        return (datetime.now(UTC) + timedelta(seconds=remaining)).isoformat()

    # ---- 凭证 ------------------------------------------------------------

    def register(self, snapshot_path: Path, payload: dict[str, object]) -> ImportPreviewRecord:
        """登记一条凭证；返回含 ``preview_id`` 与到期时刻的记录。"""
        self.cleanup()
        preview_id = uuid.uuid4().hex
        record = ImportPreviewRecord(
            preview_id=preview_id,
            snapshot_path=Path(snapshot_path),
            expires_at=self._clock() + self.ttl_seconds,
            payload=dict(payload),
        )
        with self._lock:
            self._records[preview_id] = record
        return record

    def require(self, preview_id: str) -> ImportPreviewRecord:
        """取凭证；未知/伪造/重启后失效与过期分别以稳定码拒绝。"""
        with self._lock:
            record = self._records.get(preview_id)
        if record is None:
            raise _error(
                "STANDARD_IMPORT_PREVIEW_NOT_FOUND",
                f"导入预检凭证 {preview_id!r} 不存在或已失效，请重新预检",
            )
        if record.is_expired(self._clock()):
            self.cancel(preview_id)
            raise _error(
                "STANDARD_IMPORT_PREVIEW_EXPIRED",
                f"导入预检凭证 {preview_id!r} 已过期，请重新预检",
            )
        return record

    def remember_result(
        self, preview_id: str, result: dict[str, object]
    ) -> dict[str, object]:
        """记录成功确认的幂等回执；同一凭证重复确认返回同一结果。"""
        with self._lock:
            record = self._records.get(preview_id)
            if record is None:
                return result
            self._records[preview_id] = ImportPreviewRecord(
                preview_id=record.preview_id,
                snapshot_path=record.snapshot_path,
                expires_at=record.expires_at,
                payload=record.payload,
                consumed=dict(result),
                extras=dict(record.extras),
            )
        return result

    def cancel(self, preview_id: str) -> None:
        """取消凭证并删除快照；未知凭证不报错（幂等取消）。"""
        with self._lock:
            record = self._records.pop(preview_id, None)
        if record is not None:
            _remove_quietly(record.snapshot_path)

    def discard_snapshot(self, snapshot_path: Path) -> None:
        """删除尚未登记凭证的快照（校验失败回滚）：不猜测目录，只删传入路径。"""
        _remove_quietly(snapshot_path)

    def cleanup(self) -> None:
        """清理过期凭证与它们的快照；返回不表示任何业务结果。"""
        now = self._clock()
        with self._lock:
            expired = [
                preview_id
                for preview_id, record in self._records.items()
                if now >= record.expires_at
            ]
            records = [self._records.pop(preview_id) for preview_id in expired]
        for record in records:
            _remove_quietly(record.snapshot_path)

    def snapshot_files(self) -> tuple[Path, ...]:
        """当前快照根下的文件（测试与运维用；不含正在复制的临时文件前缀）。"""
        if not self.root.is_dir():
            return ()
        return tuple(
            path
            for path in sorted(self.root.iterdir())
            if path.is_file() and not path.name.startswith(".")
        )


def _remove_quietly(path: Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        return
