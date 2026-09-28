"""官方/用户图纸标准库（PLAN-DM-046 Task 2）。

布局::

    official_root/<uuid>/document.json                 # 只读
    user_root/published/<uuid>/document.json           # 已发布用户标准
    user_root/drafts/<draft_id>/document.json          # 用户草稿
    user_root/.standards.lock                          # 发布/导入互斥锁文件

标准包按 UUID 平铺；重复身份与规范化名称冲突在库锁内稳定拒绝。
目录迁移使用同盘原子 rename，已发布内容不被原地修改。

草稿写入只过**结构**门禁（``parse_standard_draft_document``），草稿发布时间为空；
读取已发布内容与发布草稿时过**完整发布**门禁
（``parse_published_standard_document``）。首次发现旧用户草稿时，先备份整棵标准库，
再在库锁内执行原子、可重入的 schema v3 迁移。
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dst_manager.domain.standard_identity import (
    normalize_standard_name,
    parse_standard_id,
)
from dst_manager.domain.standard_naming import publish_naming_diagnostics
from dst_manager.domain.standard_rules import publish_diagnostics
from dst_manager.domain.standards import (
    SUPPORTED_SCHEMA_VERSIONS,
    DrawingStandard,
    StandardSchemaError,
    materialize_published_document,
    parse_published_at,
    parse_published_standard_document,
    parse_standard_draft_document,
)
from dst_manager.infrastructure.filesystem.atomic import atomic_write_text
from dst_manager.infrastructure.filesystem.locking import (
    FileLockError,
    WorkspaceTransactionLock,
)
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    resolve_asset_file,
    resolve_asset_files,
    validate_asset_files,
    validate_package_asset_files,
)
from dst_manager.infrastructure.standards.identity_index import (
    IdentityEntry,
    IdentityIndex,
)
from dst_manager.infrastructure.standards.migration import (
    StandardMigrationError,
    has_legacy_drafts,
    migrate_legacy_drafts,
)
from dst_manager.infrastructure.standards.package import (
    MANIFEST_NAME,
    LoadedStandardPackage,
    StandardPackageError,
    StandardPackageReader,
)

DOCUMENT_NAME = "document.json"

#: 标准库写入门禁文件名（位于用户库根）：发布与导入共用同一互斥。
LIBRARY_LOCK_NAME = ".standards.lock"
#: 取得互斥锁的等待上限（秒）；持锁窗口只覆盖读最高版到原子提交。
LIBRARY_LOCK_TIMEOUT_SECONDS = 30.0

#: 进程内按用户库根注册的互斥：确保同进程内多个 Store 实例也互斥。
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

#: 单段路径名长度上限：标准库目录名来自客户端输入，超长一律拒绝。
MAX_SEGMENT_LENGTH = 128
#: 受控资产副本文件名前缀；清理只针对带该前缀且未被文档引用的副本。
MANAGED_ASSET_PREFIX = "managed-"
#: 单个本机模板来源的大小上限（与标准包单条目上限一致）。
MAX_ASSET_SOURCE_SIZE = 64 * 1024 * 1024
#: 允许复制进草稿的模板扩展名。
ALLOWED_ASSET_SUFFIXES = frozenset({".dwg", ".dwt"})
#: 受控副本名分配重试次数；uuid4 碰撞概率可忽略，仅作确定性防护。
_ASSET_NAME_ATTEMPTS = 5
_COPY_CHUNK_SIZE = 1024 * 1024
#: Windows 保留设备名（带任意扩展名时同样保留）。
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
#: 路径段种类 → 稳定错误码；草稿段与身份段各有自己的码。
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


class StandardStore:
    """官方（只读）与用户标准库的组合仓储。"""

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
        self._reader = StandardPackageReader()
        try:
            if has_legacy_drafts(self._drafts_root):
                with self._exclusive():
                    if has_legacy_drafts(self._drafts_root):
                        migrate_legacy_drafts(
                            standards_root=self._standards_root,
                            official_root=self._official_root,
                            published_root=self._published_root,
                            drafts_root=self._drafts_root,
                            identity_entries=self._identity_entries(),
                        )
        except StandardMigrationError as exc:
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
    def _exclusive(self):
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

    # ---- 路径段边界 ------------------------------------------------------

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

    # ---- 身份与名称占用 --------------------------------------------------

    def published_name_owners(self) -> dict[str, str]:
        """规范化非空名称 → 已发布标准 ID，用于保留旧调用门面。"""
        owners: dict[str, str] = {}
        for summary in self.list():
            if summary.status != "published":
                continue
            normalized = normalize_standard_name(summary.name)
            if normalized:
                owners.setdefault(normalized, summary.standard_id)
        return owners

    def check_published_name(self, standard_id: str, name: str) -> None:
        """兼容入口：检查官方与用户已发布标准中的名称冲突。"""
        owner = self.published_name_owners().get(normalize_standard_name(name))
        if owner is not None and owner != standard_id:
            raise _error(
                "STANDARD_NAME_CONFLICT",
                f"标准名称 {name!r} 已由已发布标准 {owner!r} 占用",
            )

    def _identity_index(self) -> IdentityIndex:
        return IdentityIndex(
            IdentityEntry(
                standard_id=summary.standard_id,
                name=summary.name,
                source=summary.source,
                status=summary.status,
                draft_id=summary.draft_id,
            )
            for summary in self.list()
        )

    def _identity_entries(self) -> list[IdentityEntry]:
        return [
            IdentityEntry(
                standard_id=summary.standard_id,
                name=summary.name,
                source=summary.source,
                status=summary.status,
                draft_id=summary.draft_id,
            )
            for summary in self.list()
        ]

    def check_available_identity(
        self,
        standard_id: str,
        name: str,
        *,
        exclude_draft_id: str | None = None,
    ) -> None:
        """拒绝库内重复 UUID 或重复的非空规范化名称。"""
        try:
            canonical_id = parse_standard_id(standard_id)
        except ValueError as exc:
            raise _error("STANDARD_ID_INVALID", "标准 ID 必须是带连字符的 UUID") from exc
        if not isinstance(name, str):
            raise _error("STANDARD_NAME_INVALID", "标准名称必须是字符串")
        index = self._identity_index()
        id_owner = index.find_id(canonical_id, exclude_draft_id=exclude_draft_id)
        if id_owner is not None:
            raise _error(
                "STANDARD_ID_EXISTS",
                f"标准 ID 已被名称 {id_owner.name!r} 占用",
            )
        name_owner = index.find_name(name, exclude_draft_id=exclude_draft_id)
        if name_owner is not None:
            raise _error(
                "STANDARD_NAME_CONFLICT",
                f"标准名称 {name!r} 已由标准 {name_owner.standard_id!r} 占用",
            )

    # ---- 查询 ------------------------------------------------------------

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
            try:
                canonical_id = _safe_segment(standard_dir.name, "id")
            except StandardStoreError:
                # 目录名非法的历史条目只跳过，不阻断其余标准。
                continue
            if canonical_id != standard_dir.name:
                continue
            document = self._read_document(standard_dir)
            schema_version = document.get("schema_version")
            if type(schema_version) is not int or schema_version != SUPPORTED_SCHEMA_VERSIONS[0]:
                continue
            try:
                document_id = parse_standard_id(document.get("standard_id"))
            except ValueError:
                continue
            if document_id != canonical_id:
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
                standard = parse_published_standard_document(self._read_supported(document))
                if standard.standard_id != _safe_segment(standard_id, "id"):
                    raise _error("STANDARD_ID_INVALID", "文档标准 ID 与存储目录不一致")
                return standard
        return None

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

    def get_draft(self, draft_id: str) -> StandardDraft | None:
        document = self._draft_dir(draft_id) / DOCUMENT_NAME
        if not document.is_file():
            return None
        data = json.loads(document.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return StandardDraft(draft_id=draft_id, document=data)

    def _iter_drafts(self) -> list[StandardDraft]:
        drafts = []
        if not self._drafts_root.is_dir():
            return drafts
        for directory in sorted(self._drafts_root.iterdir()):
            if not directory.is_dir():
                continue
            try:
                draft = self.get_draft(directory.name)
            except StandardStoreError:
                # 目录名非法的历史草稿只跳过，不删除也不阻断其余条目。
                continue
            if draft is not None:
                drafts.append(draft)
        return drafts

    # ---- 草稿 ------------------------------------------------------------

    def create_draft(
        self, document: Mapping[str, object], draft_id: str | None = None
    ) -> StandardDraft:
        """保存一份草稿文档；只要求结构合法，允许语义未完成内容。"""
        standard = parse_standard_draft_document(document)  # 提前拒绝结构非法的草稿
        normalized_document = dict(document)
        normalized_document["standard_id"] = standard.standard_id
        # 显式空串不是「未指定」：仍按非法草稿段拒绝。
        if draft_id is None:
            draft_id = f"draft-{uuid.uuid4().hex[:12]}"
        target = self._draft_dir(draft_id)
        with self._exclusive():
            self.check_available_identity(standard.standard_id, standard.name)
            if target.exists():
                raise _error("STANDARD_DRAFT_EXISTS", f"草稿 {draft_id!r} 已存在")
            target.mkdir(parents=True)
            try:
                self._write_document(target, normalized_document)
            except BaseException:
                shutil.rmtree(target, ignore_errors=True)
                raise
        return StandardDraft(draft_id=draft_id, document=normalized_document)

    def save_draft(self, draft_id: str, document: Mapping[str, object]) -> StandardDraft:
        standard = parse_standard_draft_document(document)
        normalized_document = dict(document)
        normalized_document["standard_id"] = standard.standard_id
        target = self._draft_dir(draft_id)
        with self._exclusive():
            if not (target / DOCUMENT_NAME).is_file():
                raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
            self.check_available_identity(
                standard.standard_id,
                standard.name,
                exclude_draft_id=draft_id,
            )
            self._write_document(target, normalized_document)
            # 保存成功后清理本次编辑未引用的受控副本（手工放置的资产不受影响）。
            self._prune_managed_assets(target, standard)
        return StandardDraft(draft_id=draft_id, document=normalized_document)

    def delete_draft(self, draft_id: str) -> None:
        target = self._draft_dir(draft_id)
        if not target.is_dir():
            raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
        shutil.rmtree(target)

    def _write_document(self, directory: Path, document: Mapping[str, object]) -> None:
        atomic_write_text(
            directory / DOCUMENT_NAME,
            json.dumps(document, ensure_ascii=False, indent=2),
        )

    # ---- 受控资产副本 ----------------------------------------------------

    def copy_draft_asset(self, draft_id: str, source_path: Path) -> str:
        """把本机 DWG/DWT 受控复制进草稿，返回包内相对路径。

        来源只作一次性读取：不写回来源、不把绝对路径写进草稿。副本先写草稿内
        随机临时文件，校验完成后原子改名；任何失败都不留半文件、不覆盖已有副本。
        """
        draft_dir = self._draft_dir(draft_id)
        if not (draft_dir / DOCUMENT_NAME).is_file():
            raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
        source = Path(source_path)
        if not source.is_absolute() or not source.is_file():
            raise _error(
                "STANDARD_ASSET_SOURCE_NOT_FOUND",
                f"本机模板来源 {str(source_path)!r} 不存在或不是文件",
            )
        suffix = source.suffix.casefold()
        if suffix not in ALLOWED_ASSET_SUFFIXES:
            raise _error(
                "STANDARD_ASSET_SOURCE_INVALID",
                f"本机模板来源 {source.name!r} 必须是 .dwg 或 .dwt 文件",
            )
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise _error(
                "STANDARD_ASSET_SOURCE_NOT_FOUND", f"无法读取本机模板来源：{exc}"
            ) from exc
        if size > MAX_ASSET_SOURCE_SIZE:
            raise _error(
                "STANDARD_ASSET_SOURCE_INVALID",
                f"本机模板来源 {source.name!r} 超过 {MAX_ASSET_SOURCE_SIZE} 字节上限",
            )
        assets_dir = draft_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        final = self._free_asset_target(assets_dir, suffix)
        temp = assets_dir / f".{uuid.uuid4().hex}.copying"
        try:
            with source.open("rb") as reader, temp.open("wb") as writer:
                shutil.copyfileobj(reader, writer, length=_COPY_CHUNK_SIZE)
                writer.flush()
                os.fsync(writer.fileno())
            if temp.stat().st_size != size:
                raise _error(
                    "STANDARD_ASSET_COPY_FAILED", "复制结果大小与来源不一致，已放弃"
                )
            os.replace(temp, final)
        except OSError as exc:
            raise _error("STANDARD_ASSET_COPY_FAILED", f"复制本机模板失败：{exc}") from exc
        finally:
            temp.unlink(missing_ok=True)
        return f"assets/{final.name}"

    @staticmethod
    def _free_asset_target(assets_dir: Path, suffix: str) -> Path:
        """分配一个尚未占用的受控副本名；碰撞一律重试，不覆盖已有文件。"""
        for _ in range(_ASSET_NAME_ATTEMPTS):
            candidate = assets_dir / f"{MANAGED_ASSET_PREFIX}{uuid.uuid4().hex}{suffix}"
            if not candidate.exists():
                return candidate
        raise _error(
            "STANDARD_ASSET_COPY_FAILED",
            f"草稿资产目录 {assets_dir} 中无法分配唯一的受控副本名",
        )

    def _prune_managed_assets(
        self, draft_dir: Path, standard: DrawingStandard
    ) -> None:
        """清理未被文档引用且带受控前缀的副本；其他文件一律不碰。"""
        assets_dir = draft_dir / "assets"
        if not assets_dir.is_dir():
            return
        referenced: set[Path] = set()
        for asset in standard.assets:
            try:
                referenced.add(resolve_asset_file(draft_dir, asset.file))
            except StandardAssetError:
                continue  # 非法声明不参与引用集合，也不阻断清理
        for candidate in sorted(assets_dir.iterdir()):
            if not candidate.is_file() or not candidate.name.startswith(
                MANAGED_ASSET_PREFIX
            ):
                continue
            if candidate.resolve() in referenced:
                continue
            try:
                candidate.unlink()
            except OSError:
                # 清理是尽力而为：删除失败只留下无害的孤儿副本（导出白名单已排除）。
                continue

    # ---- 发布与导入导出 --------------------------------------------------

    def publish(
        self, draft_id: str, *, published_at: int | None = None
    ) -> PublishedStandard:
        """写入发布时间并在标准库锁内原子发布 UUID 包。"""
        with self._exclusive():
            draft = self.get_draft(draft_id)
            if draft is None:
                raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
            draft_dir = self._draft_dir(draft_id)
            try:
                draft_standard = parse_standard_draft_document(draft.document)
            except StandardSchemaError as exc:
                raise StandardStoreError(str(exc)) from exc
            standard_id = draft_standard.standard_id
            timestamp = (
                time.time_ns() // 1_000_000
                if published_at is None
                else parse_published_at(published_at)
            )
            document = dict(draft.document)
            document["standard_id"] = standard_id
            document = materialize_published_document(document, timestamp)
            standard = _published_or_store_error(document)
            try:
                # 发布前最终门禁：声明的模板资产必须真实落在草稿受控目录内。
                validate_asset_files(standard, draft_dir)
            except StandardAssetError as exc:
                raise _asset_gate_error(exc) from exc
            self.check_available_identity(
                standard_id,
                standard.name,
                exclude_draft_id=draft_id,
            )
            target = self._assert_identity_free(standard_id)
            # 发布成功后草稿目录整体移动：先清理本次编辑未引用的受控副本。
            self._prune_managed_assets(draft_dir, standard)
            self._published_root.mkdir(parents=True, exist_ok=True)
            original = (draft_dir / DOCUMENT_NAME).read_bytes()
            try:
                self._write_document(draft_dir, document)
                os.replace(draft_dir, target)
            except OSError as exc:
                self._restore_draft_document(draft_dir, original)
                if isinstance(exc, FileExistsError):
                    raise _error(
                        "STANDARD_ID_EXISTS", f"标准 ID {standard_id!r} 已存在"
                    ) from exc
                raise _error(
                    "STANDARD_PUBLISH_FAILED",
                    f"发布标准 {standard_id!r} 失败：{exc}",
                ) from exc
            return PublishedStandard(
                standard_id=standard_id,
                published_at=standard.published_at,
                name=standard.name,
                description=standard.description,
                root=target,
            )

    @staticmethod
    def _restore_draft_document(draft_dir: Path, original: bytes) -> None:
        """把草稿文档恢复为发布前的空发布时间形态。

        尽力而为：恢复失败时草稿目录可能保留已写入的 ``published_at`` 字段，
        需人工介入；绝不能因此删除草稿内容。
        """
        try:
            (draft_dir / DOCUMENT_NAME).write_bytes(original)
        except OSError:
            return

    def read_package(self, path: Path) -> LoadedStandardPackage:
        """读取并校验标准包（不落库），供应用层发布门禁先行判定。

        保留读取器的稳定错误码前缀（如 ``STANDARD_SCHEMA_VERSION_UNSUPPORTED``
        与 ``STANDARD_PACKAGE_PATH_INVALID``），不统一改写为 ``STANDARD_PACKAGE_INVALID``。
        """
        try:
            return self._reader.read(Path(path))
        except StandardPackageError as exc:
            raise _error(str(exc).split(":", 1)[0], str(exc)) from exc

    def import_package(
        self, path: Path, loaded: LoadedStandardPackage | None = None
    ) -> PublishedStandard:
        """导入标准包；包内文档必须通过完整发布门禁与名称唯一门禁，失败不落库。

        读包与建目录都在标准库锁内完成，并在锁内重新核对身份与名称，
        使预检后的库状态变化不会造成静默覆盖。
        """
        with self._exclusive():
            loaded = loaded if loaded is not None else self.read_package(path)
            standard = loaded.standard
            gate = _publish_gate_error(standard)
            if gate is not None:
                raise gate
            try:
                # 导入门禁在建任何目录之前：清单与包内条目必须双向一致。
                validate_package_asset_files(
                    standard, [entry.path for entry in loaded.entries]
                )
            except StandardAssetError as exc:
                raise _asset_gate_error(exc) from exc
            self.check_available_identity(standard.standard_id, standard.name)
            target = self._assert_identity_free(standard.standard_id)
            # 包先写入发布根内的随机暂存目录，再原子改名为 UUID 目录。
            self._published_root.mkdir(parents=True, exist_ok=True)
            staging = self._published_root / f".import-{uuid.uuid4().hex}"
            staging.mkdir(parents=True)
            try:
                self._extract_package(loaded, staging)
                try:
                    os.replace(staging, target)
                except OSError as exc:
                    raise _error(
                        "STANDARD_ID_EXISTS",
                        f"标准 ID {standard.standard_id!r} 已存在",
                    ) from exc
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            return PublishedStandard(
                standard_id=standard.standard_id,
                published_at=standard.published_at,
                name=standard.name,
                description=standard.description,
                root=target,
            )

    def _extract_package(self, loaded, staging: Path) -> None:
        """把已校验条目逐个复制到暂存目录；路径在读取阶段已验证。"""
        import zipfile

        with zipfile.ZipFile(loaded.source_path) as archive:
            names = {info.filename.replace("\\", "/") for info in archive.infolist()}
            archive.extract(MANIFEST_NAME, path=staging)
            for entry in loaded.entries:
                candidates = [name for name in names if _norm(name) == entry.path]
                if not candidates:
                    raise _error(
                        "STANDARD_PACKAGE_INVALID", f"包内缺少声明条目 {entry.path!r}"
                    )
                source = archive.open(candidates[0])
                destination = staging / entry.path
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source, destination.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
        os.replace(staging / MANIFEST_NAME, staging / DOCUMENT_NAME)

    def _assert_identity_free(self, standard_id: str) -> Path:
        target = self._published_dir(self._published_root, standard_id)
        if target.exists() or self._published_dir(self._official_root, standard_id).exists():
            raise _error(
                "STANDARD_ID_EXISTS", f"标准 ID {standard_id!r} 已存在"
            )
        return target

    def export_package(
        self,
        standard_id: str,
        dest_dir: Path | int | str,
        legacy_dest_dir: Path | None = None,
    ) -> Path:
        import zipfile

        candidates = [
            self._published_dir(root, standard_id)
            for root in (self._published_root, self._official_root)
        ]
        for source in candidates:
            if source.is_dir():
                break
        else:
            raise _error(
                "STANDARD_ID_NOT_FOUND", f"标准 {standard_id!r} 不存在"
            )
        standard = _published_or_store_error(self._read_supported(source / DOCUMENT_NAME))
        try:
            # 只导出文档声明且校验通过的资产；草稿临时文件一律不进口袋。
            assets = resolve_asset_files(standard, source)
        except StandardAssetError as exc:
            raise _asset_gate_error(exc) from exc
        # 第三个参数仅在旧应用门面尚未迁移时接收并忽略旧发布版本。
        dest = Path(legacy_dest_dir if legacy_dest_dir is not None else dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        package = dest / f"{standard.standard_id}.dststandard"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(source / DOCUMENT_NAME, arcname=MANIFEST_NAME)
            # 两个资产可以声明同一路径：包内条目必须去重，否则阅读器以重复路径拒绝自家导出包。
            written: set[str] = set()
            for arcname, file in assets:
                if arcname in written:
                    continue
                written.add(arcname)
                archive.write(file, arcname=arcname)
        return package


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
