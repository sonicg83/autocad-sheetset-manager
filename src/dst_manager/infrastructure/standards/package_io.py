"""标准发布、包预检导入和导出。"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

from dst_manager.domain.standards import (
    StandardSchemaError,
    materialize_published_document,
    parse_published_at,
    parse_standard_draft_document,
)
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    resolve_asset_files,
    validate_asset_files,
    validate_package_asset_files,
)
from dst_manager.infrastructure.standards.package import (
    MANIFEST_NAME,
    LoadedStandardPackage,
    StandardPackageError,
)
from dst_manager.infrastructure.standards.store_common import (
    DOCUMENT_NAME,
    PublishedStandard,
    StandardStoreError,
    _asset_gate_error,
    _error,
    _norm,
    _publish_gate_error,
    _published_or_store_error,
)


class StandardPackageIO:
    """StandardPackageIO 的标准库操作组合。"""

    def publish(
        self, draft_id: str, *, published_at: int | None = None
    ) -> PublishedStandard:
        """写入发布时间并在标准库锁内原子发布 UUID 包。"""
        with self.lifecycle_lock():
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
        with self.lifecycle_lock():
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

        if self.is_legacy_published(standard_id):
            raise _error(
                "STANDARD_LEGACY_READ_ONLY",
                "旧版标准仅供查看与历史兼容，不能导出为新版本标准包",
            )
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
