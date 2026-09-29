"""标准库仓储门面所依赖的路径、生命周期锁与读取实现。"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

from dst_manager.domain.legacy_standard_compat import (
    parse_migrated_published_standard_document,
)
from dst_manager.domain.standard_identity import parse_standard_id
from dst_manager.domain.standards import (
    SUPPORTED_SCHEMA_VERSIONS,
    DrawingStandard,
    parse_published_standard_document,
)
from dst_manager.infrastructure.filesystem.locking import (
    FileLockError,
    WorkspaceTransactionLock,
)
from dst_manager.infrastructure.standards.legacy_published_migration import (
    LegacyPublishedMigrationError,
    migrated_standard_ids,
)
from dst_manager.infrastructure.standards.migration import (
    BACKUP_NAME,
    StandardMigrationError,
    has_legacy_drafts,
    has_legacy_published,
    migrate_legacy_standards,
)
from dst_manager.infrastructure.standards.package import StandardPackageReader
from dst_manager.infrastructure.standards.store_common import (
    DOCUMENT_NAME,
    LIBRARY_LOCK_NAME,
    LIBRARY_LOCK_TIMEOUT_SECONDS,
    StandardStoreError,
    StandardSummary,
    _error,
    _safe_segment,
)

_process_locks_guard = threading.Lock()
_process_locks: dict[str, threading.Lock] = {}


def _process_lock(root: Path) -> threading.Lock:
    key = str(root)
    with _process_locks_guard:
        lock = _process_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _process_locks[key] = lock
        return lock


class StandardStoreCore:
    """StandardStoreCore 的标准库操作组合。"""

    def __init__(self, *, official_root: Path, user_root: Path) -> None:
        # 目录根统一解析为真实路径：路径段边界校验与文件操作共用同一基准。
        self._official_root = Path(official_root).resolve()
        self._user_root = Path(user_root).resolve()
        try:
            self._standards_root = Path(
                os.path.commonpath((self._official_root, self._user_root))
            ).resolve()
        except ValueError as exc:
            raise _error("STANDARD_LIBRARY_PATH_INVALID", "官方库与用户库必须位于同一标准库树") from exc
        self._published_root = self._user_root / "published"
        self._drafts_root = self._user_root / "drafts"
        backup_parent = self._standards_root.parent / "backups" / BACKUP_NAME
        self._reader = StandardPackageReader()
        try:
            if has_legacy_drafts(self._drafts_root) or has_legacy_published(
                self._published_root, backup_parent
            ):
                with self.lifecycle_lock():
                    if has_legacy_drafts(self._drafts_root) or has_legacy_published(
                        self._published_root, backup_parent
                    ):
                        migrate_legacy_standards(
                            standards_root=self._standards_root,
                            official_root=self._official_root,
                            published_root=self._published_root,
                            drafts_root=self._drafts_root,
                            identity_entries=self._identity_entries(),
                        )
            self._legacy_published_ids = migrated_standard_ids(
                backup_parent / "legacy-published-uuid-map.json"
            )
        except (StandardMigrationError, LegacyPublishedMigrationError) as exc:
            raise StandardStoreError(str(exc)) from exc

    @property
    def official_root(self) -> Path:
        return self._official_root

    @property
    def published_root(self) -> Path:
        return self._published_root

    @property
    def drafts_root(self) -> Path:
        return self._drafts_root

    @contextmanager
    def lifecycle_lock(self):
        """标准库写入门禁：**进程内互斥（必需）+ 跨进程文件锁（纵深防御）**。

        两层职责不同，不得因为「产品是单实例」而删掉任何一层：

        - **进程内必需**：接口层的标准端点都是同步 ``def``，FastAPI 把它们放到
          threadpool 执行，uvicorn 在同一个进程内可以真正并行处理多个请求。两次
          ``publish`` 或一次 ``publish`` 与一次导入确认完全可能交错，所以「读最高版
          → 分配版本 → 原子提交」必须在本层串行化（PLAN-DM-018 的单实例守卫只排除
          第二个**进程**，不排除第二个**请求**）。
        - **跨进程为纵深防御**：`WorkspaceTransactionLock` 额外覆盖「两个进程写同一
          个标准库根」。按 PLAN-DM-018 的裁决，桌面壳为唯一交付入口且单实例，所以
          这条路径不在承诺范围内；但 ``serve``（开发/排障/e2e 夹具）与桌面壳并存、
          或把 ``data_dir`` 指向共享/漫游位置时，``Local\\`` 互斥量按用户与会话隔离而
          **挡不住**这种情况，文件锁是低成本的第二道防线。
          若未来把 ``serve`` 升为受支持的并行入口，或允许共享/漫游 ``data_dir``，
          则本层从「纵深防御」升为「必须」，需补真实双进程并发证据。

        取锁超时以稳定码 ``STANDARD_LIBRARY_BUSY`` 拒绝（可重试的冲突），
        不让 ``FileLockError`` 冒泡成 500。
        """
        try:
            with _process_lock(self._user_root), WorkspaceTransactionLock(
                self._user_root / LIBRARY_LOCK_NAME,
                timeout_seconds=LIBRARY_LOCK_TIMEOUT_SECONDS,
            ):
                yield
        except FileLockError as exc:
            raise _error(
                "STANDARD_LIBRARY_BUSY",
                f"标准库正在被其他操作占用，请稍后重试：{exc}",
            ) from exc

    def _draft_dir(self, draft_id: str) -> Path:
        """草稿根下的单层草稿目录；非法段或越界符号链接一律拒绝。"""
        segment = _safe_segment(draft_id, "draft")
        target = self._drafts_root / segment
        if target.resolve().parent != self._drafts_root:
            raise _error(
                "STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不是草稿根下的单层目录"
            )
        return target

    def _published_dir(self, root: Path, standard_id: str) -> Path:
        """某个发布根下的 UUID 单层目录；身份段非法即稳定拒绝。"""
        base = Path(root).resolve()
        target = base / _safe_segment(standard_id, "id")
        if target.resolve().parent != base:
            raise _error(
                "STANDARD_ID_NOT_FOUND",
                f"标准 {standard_id!r} 不在发布根的单层目录中",
            )
        return target

    def list(self) -> list[StandardSummary]:
        summaries: list[StandardSummary] = []
        summaries.extend(self._scan_published(self._official_root, "official"))
        summaries.extend(self._scan_published(self._published_root, "user"))
        for draft in self._iter_drafts():
            document = draft.document
            summaries.append(
                StandardSummary(
                    source="user",
                    status="draft",
                    standard_id=str(document.get("standard_id", "")),
                    name=str(document.get("name", "")),
                    description=(
                        document.get("description", "")
                        if isinstance(document.get("description", ""), str)
                        else ""
                    ),
                    published_at=None,
                    draft_id=draft.draft_id,
                )
            )
        return summaries

    def _scan_published(self, root: Path, source: str) -> list[StandardSummary]:
        summaries = []
        if not root.is_dir():
            return summaries
        for standard_dir in sorted(root.iterdir()):
            if standard_dir.is_symlink() or not standard_dir.is_dir():
                continue
            if not (standard_dir / DOCUMENT_NAME).is_file() and any(
                child.is_dir() and (child / DOCUMENT_NAME).is_file()
                for child in standard_dir.iterdir()
            ):
                # 旧 ID/版本容器只由迁移兼容层读取，不能作为 UUID 标准出现在列表。
                continue
            try:
                canonical_id = _safe_segment(standard_dir.name, "id")
            except StandardStoreError:
                # 目录名非法的历史条目只跳过，不阻断其余标准。
                continue
            if canonical_id != standard_dir.name:
                continue
            document = self._read_document(standard_dir)
            schema_version = document.get("schema_version")
            if schema_version is not None and (
                type(schema_version) is not int
                or schema_version != SUPPORTED_SCHEMA_VERSIONS[0]
            ):
                continue
            raw_published_at = document.get("published_at")
            published_at = (
                raw_published_at
                if isinstance(raw_published_at, int)
                and not isinstance(raw_published_at, bool)
                and raw_published_at >= 0
                else None
            )
            raw_description = document.get("description", "")
            summaries.append(
                StandardSummary(
                    source=source,  # type: ignore[arg-type]
                    status="published",
                    standard_id=canonical_id,
                    name=str(document.get("name", "")),
                    description=raw_description if isinstance(raw_description, str) else "",
                    published_at=published_at,
                )
            )
        return summaries

    def _read_document(self, directory: Path) -> dict[str, object]:
        """读取已发布文档；不可信文件（截断/非 UTF-8）当作空文档。

        空文档仍会进入列表（名称为空）以便上层把它报为不可用候选，而不是让
        一个损坏的标准静默消失；明确写有不受支持 ``schema_version`` 的目录才跳过。
        """
        try:
            data = json.loads(
                (directory / DOCUMENT_NAME).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            # ValueError 同时覆盖 JSONDecodeError 与 UnicodeDecodeError
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _read_supported(document: Path) -> dict[str, object]:
        """读取已发布文档并核对文档格式版本；残留 v1 与损坏文件均以稳定码拒绝。

        损坏（截断/非 UTF-8）也归为 ``STANDARD_JSON_INVALID``：列表用容错读取把它
        当空文档上报为不可用候选，详情与导出不得因此冒泡成 500。
        """
        try:
            data = json.loads(document.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # ValueError 同时覆盖 JSONDecodeError 与 UnicodeDecodeError
            raise _error("STANDARD_JSON_INVALID", f"{document} 无法读取：{exc}") from exc
        if not isinstance(data, dict):
            raise _error("STANDARD_JSON_INVALID", f"{document} 根不是对象")
        schema_version = data.get("schema_version")
        if type(schema_version) is not int or schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise _error(
                "STANDARD_SCHEMA_VERSION_UNSUPPORTED",
                f"schema_version {data.get('schema_version')!r} 不受支持（需要 "
                f"{'/'.join(str(item) for item in SUPPORTED_SCHEMA_VERSIONS)}）",
            )
        return data

    def get(
        self, standard_id: str, version: int | str | None = None
    ) -> DrawingStandard | None:
        for root in (self._published_root, self._official_root):
            document = self._published_dir(root, standard_id) / DOCUMENT_NAME
            if document.is_file():
                data = self._read_supported(document)
                standard = (
                    parse_migrated_published_standard_document(
                        data, standard_id=standard_id
                    )
                    if root == self._published_root
                    and standard_id in self._legacy_published_ids
                    else parse_published_standard_document(data)
                )
                if standard.standard_id != _safe_segment(standard_id, "id"):
                    raise _error("STANDARD_ID_INVALID", "文档标准 ID 与存储目录不一致")
                return standard
        return None

    def has_published_identity(self, standard_id: str) -> bool:
        """即使发布目录中的文档损坏，也报告该 UUID 已被占用。"""
        try:
            canonical_id = parse_standard_id(standard_id)
        except ValueError as exc:
            raise _error("STANDARD_ID_INVALID", "标准 ID 必须是带连字符的 UUID") from exc
        return any(
            (directory := self._published_dir(root, canonical_id)).exists()
            or directory.is_symlink()
            for root in (self._published_root, self._official_root)
        )

    def is_legacy_published(self, standard_id: str) -> bool:
        """迁移兼容标准只读，不能导出、删除或用于新工程绑定。"""
        return standard_id in self._legacy_published_ids

    def get_document(
        self, standard_id: str, version: int | str | None = None
    ) -> dict[str, object] | None:
        """读取已发布标准的原始文档字典（派生草稿等场景需要完整内容）。"""
        for root in (self._published_root, self._official_root):
            document = self._published_dir(root, standard_id) / DOCUMENT_NAME
            if document.is_file():
                data = self._read_supported(document)
                try:
                    document_id = parse_standard_id(data.get("standard_id"))
                except ValueError as exc:
                    raise _error(
                        "STANDARD_ID_INVALID", "文档标准 ID 与存储目录不一致"
                    ) from exc
                if document_id != _safe_segment(standard_id, "id"):
                    raise _error("STANDARD_ID_INVALID", "文档标准 ID 与存储目录不一致")
                return data if isinstance(data, dict) else None
        return None
