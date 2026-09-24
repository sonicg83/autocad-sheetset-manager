"""官方/用户图纸标准库（PLAN-DM-035 Task 3；PLAN-DM-041 Task 2）。

布局::

    official_root/<standard_id>/<n>/document.json      # 只读
    user_root/published/<standard_id>/<n>/             # 已发布用户标准
    user_root/drafts/<draft_id>/document.json          # 用户草稿

``<n>`` 是规范十进制正整数版本目录名；同一 ``standard_id + <n>`` 的重复发布、
导入碰撞与官方身份冲突一律以 ``STANDARD_VERSION_EXISTS`` 稳定拒绝。
目录迁移使用同盘原子 rename，已发布内容不被原地修改。

草稿写入只过**结构**门禁（``parse_standard_draft_document``），草稿不携带版本；
读取已发布内容与发布草稿时过**完整发布**门禁
（``parse_published_standard_document``）。残留 ``schema_version: 1`` 目录在
``list()`` 中跳过，读取时以 ``STANDARD_SCHEMA_VERSION_UNSUPPORTED`` 拒绝。
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dst_manager.domain.standard_naming import publish_naming_diagnostics
from dst_manager.domain.standard_rules import publish_diagnostics
from dst_manager.domain.standards import (
    STANDARD_ID_PATTERN,
    STANDARD_VERSION_SEGMENT_PATTERN,
    SUPPORTED_SCHEMA_VERSIONS,
    DrawingStandard,
    StandardSchemaError,
    parse_published_standard_document,
    parse_standard_draft_document,
    parse_standard_version,
    parse_standard_version_segment,
)
from dst_manager.infrastructure.filesystem.atomic import atomic_write_text
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    resolve_asset_file,
    resolve_asset_files,
    validate_package_asset_files,
)
from dst_manager.infrastructure.standards.package import (
    MANIFEST_NAME,
    LoadedStandardPackage,
    StandardPackageError,
    StandardPackageReader,
)

DOCUMENT_NAME = "document.json"

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
    "version": "STANDARD_VERSION_INVALID",
}
_SEGMENT_LABELS = {"draft": "草稿 ID", "id": "标准 ID", "version": "标准版本"}


class StandardStoreError(Exception):
    """标准库操作失败；消息以稳定错误码开头。"""


@dataclass(frozen=True, slots=True)
class StandardSummary:
    """标准库列表条目；草稿的 ``version`` 为 ``None``，已发布为整数。"""

    source: Literal["official", "user"]
    status: Literal["published", "draft"]
    standard_id: str
    version: int | None
    name: str
    draft_id: str | None = None


@dataclass(frozen=True, slots=True)
class StandardDraft:
    draft_id: str
    document: dict[str, object]


@dataclass(frozen=True, slots=True)
class PublishedStandard:
    standard_id: str
    version: int
    name: str
    root: Path


def _error(code: str, detail: str) -> StandardStoreError:
    return StandardStoreError(f"{code}: {detail}")


def _identity_collision(standard_id: str, version: int | str) -> StandardStoreError:
    return _error("STANDARD_VERSION_EXISTS", f"标准 {standard_id}@{version} 已存在")


def _version_segment(version: int | str) -> str:
    """把版本解释为目录段文本：整数与规范十进制字符串都接受，其他一律拒绝。"""
    try:
        if isinstance(version, bool):
            raise _error("STANDARD_VERSION_INVALID", f"标准版本 {version!r} 必须是正整数")
        if isinstance(version, int):
            return str(parse_standard_version(version))
        return str(parse_standard_version_segment(version))
    except StandardSchemaError as exc:
        # 仓储层错误码保持与领域层一致，便于接口层统一映射到 422。
        raise StandardStoreError(str(exc)) from exc


def _asset_gate_error(exc: StandardAssetError) -> StandardStoreError:
    """资产门禁错误保留稳定码前缀，统一以仓储错误类型向上传递。"""
    return StandardStoreError(str(exc))


def _safe_segment(value: str, kind: str) -> str:
    """校验单个路径段；``kind`` 为 ``draft``/``id``/``version``，决定稳定错误码。

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
    if kind == "id" and not STANDARD_ID_PATTERN.fullmatch(value):
        raise _error(code, f"标准 ID {value!r} 不符合 {STANDARD_ID_PATTERN.pattern}")
    if kind == "version" and not STANDARD_VERSION_SEGMENT_PATTERN.fullmatch(value):
        raise _error(
            code,
            f"标准版本段 {value!r} 不符合 {STANDARD_VERSION_SEGMENT_PATTERN.pattern}",
        )
    return value


class StandardStore:
    """官方（只读）与用户标准库的组合仓储。"""

    def __init__(self, *, official_root: Path, user_root: Path) -> None:
        # 目录根统一解析为真实路径：路径段边界校验与文件操作共用同一基准。
        self._official_root = Path(official_root).resolve()
        self._user_root = Path(user_root).resolve()
        self._published_root = self._user_root / "published"
        self._drafts_root = self._user_root / "drafts"
        self._reader = StandardPackageReader()

    @property
    def official_root(self) -> Path:
        return self._official_root

    @property
    def published_root(self) -> Path:
        return self._published_root

    @property
    def drafts_root(self) -> Path:
        return self._drafts_root

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

    def _published_dir(self, root: Path, standard_id: str, version: int | str) -> Path:
        """某个发布根下的 ``standard_id/<n>`` 目录；身份段非法即稳定拒绝。"""
        base = Path(root).resolve()
        target = (
            base
            / _safe_segment(standard_id, "id")
            / _safe_segment(_version_segment(version), "version")
        )
        if target.resolve().parent.parent != base:
            raise _error(
                "STANDARD_VERSION_NOT_FOUND",
                f"标准 {standard_id}@{version} 不在发布根的单层目录中",
            )
        return target

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
                    version=None,
                    name=str(document.get("name", "")),
                    draft_id=draft.draft_id,
                )
            )
        return summaries

    def _scan_published(self, root: Path, source: str) -> list[StandardSummary]:
        summaries = []
        if not root.is_dir():
            return summaries
        for standard_dir in sorted(root.iterdir()):
            if not standard_dir.is_dir():
                continue
            try:
                _safe_segment(standard_dir.name, "id")
            except StandardStoreError:
                # 目录名非法的历史条目只跳过，不阻断其余标准（与草稿扫描同口径）
                continue
            for version_dir in sorted(standard_dir.iterdir()):
                if not version_dir.is_dir():
                    continue
                try:
                    _safe_segment(version_dir.name, "version")
                except StandardStoreError:
                    continue
                document = self._read_document(version_dir)
                if document.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
                    # 残留 schema_version:1（或损坏）目录只跳过，不阻断列表，也不自动迁移。
                    continue
                summaries.append(
                    StandardSummary(
                        source=source,  # type: ignore[arg-type]
                        status="published",
                        standard_id=standard_dir.name,
                        version=int(version_dir.name),
                        name=str(document.get("name", "")),
                    )
                )
        return summaries

    def _read_document(self, directory: Path) -> dict[str, object]:
        """读取已发布文档：不可信文件（截断/非 UTF-8）一律当作空文档，不参与列表。"""
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
        """读取已发布文档并核对文档格式版本；残留 v1 以稳定码拒绝。"""
        data = json.loads(document.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise _error("STANDARD_JSON_INVALID", f"{document} 根不是对象")
        if data.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            raise _error(
                "STANDARD_SCHEMA_VERSION_UNSUPPORTED",
                f"schema_version {data.get('schema_version')!r} 不受支持（需要 "
                f"{'/'.join(str(item) for item in SUPPORTED_SCHEMA_VERSIONS)}）",
            )
        return data

    def get(self, standard_id: str, version: int | str) -> DrawingStandard | None:
        for root in (self._published_root, self._official_root):
            document = self._published_dir(root, standard_id, version) / DOCUMENT_NAME
            if document.is_file():
                return parse_published_standard_document(self._read_supported(document))
        return None

    def get_document(self, standard_id: str, version: int | str) -> dict[str, object] | None:
        """读取已发布标准的原始文档字典（派生草稿等场景需要完整内容）。"""
        for root in (self._published_root, self._official_root):
            document = self._published_dir(root, standard_id, version) / DOCUMENT_NAME
            if document.is_file():
                data = self._read_supported(document)
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
        parse_standard_draft_document(document)  # 提前拒绝结构非法的草稿
        # 显式空串不是「未指定」：仍按非法草稿段拒绝。
        if draft_id is None:
            draft_id = f"draft-{uuid.uuid4().hex[:12]}"
        target = self._draft_dir(draft_id)
        if target.exists():
            raise _error("STANDARD_DRAFT_EXISTS", f"草稿 {draft_id!r} 已存在")
        target.mkdir(parents=True)
        try:
            self._write_document(target, document)
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return StandardDraft(draft_id=draft_id, document=dict(document))

    def save_draft(self, draft_id: str, document: Mapping[str, object]) -> StandardDraft:
        standard = parse_standard_draft_document(document)
        target = self._draft_dir(draft_id)
        if not (target / DOCUMENT_NAME).is_file():
            raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
        self._write_document(target, document)
        # 保存成功后清理本次编辑未引用的受控副本（手工放置的资产不受影响）。
        self._prune_managed_assets(target, standard)
        return StandardDraft(draft_id=draft_id, document=dict(document))

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
            for file in asset.files:
                try:
                    referenced.add(resolve_asset_file(draft_dir, file.path))
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

    def publish(self, draft_id: str) -> PublishedStandard:
        """发布草稿（PLAN-DM-041 Task 2 → Task 3 显式过渡态）。

        草稿不再携带版本，服务端版本分配（官方/用户库同 ID 取 ``max+1``）由
        Task 3 在仓储锁内实现。在它落地前，本入口以稳定 422
        ``STANDARD_VERSION_UNASSIGNED`` 拒绝，**不写任何目录**，避免任何调用方
        在未分配版本的情况下移动草稿目录。
        """
        draft = self.get_draft(draft_id)
        if draft is None:
            raise _error("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在")
        raise _error(
            "STANDARD_VERSION_UNASSIGNED",
            f"草稿 {draft_id!r} 尚未分配发布版本：服务端版本分配尚未接线",
        )

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
        """导入标准包；包内文档必须通过完整发布门禁，失败不落库。"""
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
        target = self._assert_identity_free(standard.standard_id, standard.version)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = self._published_root / f".import-{uuid.uuid4().hex}"
        staging.mkdir(parents=True)
        try:
            self._extract_package(loaded, staging)
            try:
                os.replace(staging, target)
            except OSError as exc:
                raise _identity_collision(standard.standard_id, standard.version) from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return PublishedStandard(
            standard_id=standard.standard_id,
            version=standard.version,
            name=standard.name,
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

    def _assert_identity_free(self, standard_id: str, version: int | str) -> Path:
        target = self._published_dir(self._published_root, standard_id, version)
        if target.exists() or self._published_dir(
            self._official_root, standard_id, version
        ).exists():
            raise _error(
                "STANDARD_VERSION_EXISTS", f"标准 {standard_id}@{version} 已存在"
            )
        return target

    def export_package(self, standard_id: str, version: int | str, dest_dir: Path) -> Path:
        import zipfile

        candidates = [
            self._published_dir(root, standard_id, version)
            for root in (self._published_root, self._official_root)
        ]
        for source in candidates:
            if source.is_dir():
                break
        else:
            raise _error(
                "STANDARD_VERSION_NOT_FOUND", f"标准 {standard_id}@{version} 不存在"
            )
        standard = _published_or_store_error(self._read_supported(source / DOCUMENT_NAME))
        try:
            # 只导出文档声明且校验通过的资产；草稿临时文件一律不进口袋。
            assets = resolve_asset_files(standard, source)
        except StandardAssetError as exc:
            raise _asset_gate_error(exc) from exc
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        # 文件名带 ``v`` 前缀，包内 manifest 的 version 仍是裸整数。
        package = dest / f"{standard_id}-v{standard.version}.dststandard"
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