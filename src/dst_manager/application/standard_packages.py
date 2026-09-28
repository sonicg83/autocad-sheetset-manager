"""标准包导入预检、改名确认与导出编排。"""

from __future__ import annotations

import uuid
from pathlib import Path

from dst_manager.application.errors import ApplicationError
from dst_manager.application.standard_common import (
    publish_diagnostic_payload,
    store_error,
)
from dst_manager.domain.standard_identity import normalize_standard_name
from dst_manager.domain.standard_naming import publish_naming_diagnostics
from dst_manager.domain.standard_rules import publish_diagnostics
from dst_manager.domain.standards import StandardDiagnostic
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    validate_package_asset_files,
)
from dst_manager.infrastructure.standards.import_previews import (
    ImportPreviewError,
    ImportPreviewStore,
)
from dst_manager.infrastructure.standards.package import (
    StandardPackageError,
    copy_package_with_name,
)
from dst_manager.infrastructure.standards.store import StandardStoreError

_IMPORT_PREVIEW_STATUS = {
    "STANDARD_IMPORT_PREVIEW_NOT_FOUND": 404,
    "STANDARD_IMPORT_PREVIEW_EXPIRED": 410,
}


def _import_preview_error(exc: ImportPreviewError) -> ApplicationError:
    code = str(exc).split(":", 1)[0]
    return ApplicationError(code, str(exc), _IMPORT_PREVIEW_STATUS.get(code, 422))


class StandardPackageOperations:
    """负责标准包预检、确认导入与导出，不承载草稿生命周期。"""

    standard_store: object
    import_previews: ImportPreviewStore

    def preview_standard_import(self, path: Path) -> dict[str, object]:
        """复制到限时快照、校验并返回预检凭证；不写标准库。"""
        previews = self.import_previews
        try:
            snapshot = previews.snapshot_source(Path(path))
        except ImportPreviewError as exc:
            raise _import_preview_error(exc) from exc
        try:
            loaded = self.standard_store.read_package(snapshot)
        except StandardStoreError as exc:
            previews.discard_snapshot(snapshot)
            raise store_error(exc) from exc
        standard = loaded.standard
        diagnostics, can_import, id_exists, name_conflict, existing_name = (
            self._import_preview_diagnostics(loaded)
        )
        record = None
        if id_exists or any(
            item.is_error
            and item.code not in {"STANDARD_ID_EXISTS", "STANDARD_NAME_CONFLICT"}
            for item in diagnostics
        ):
            previews.discard_snapshot(snapshot)
        else:
            try:
                record = previews.register(
                    snapshot,
                    {
                        "standard_id": standard.standard_id,
                        "name": standard.name,
                        "description": standard.description,
                        "published_at": standard.published_at,
                        "name_conflict": name_conflict,
                        "existing_name": existing_name,
                        "supported_cad_versions": list(standard.supported_cad_versions),
                    },
                )
            except BaseException:
                previews.discard_snapshot(snapshot)
                raise
        return {
            "preview_id": record.preview_id if record is not None else None,
            "expires_at": previews.expires_at_iso(record) if record is not None else None,
            "standard_id": standard.standard_id,
            "name": standard.name,
            "description": standard.description,
            "published_at": standard.published_at,
            "name_conflict": name_conflict,
            "existing_name": existing_name,
            "supported_cad_versions": list(standard.supported_cad_versions),
            "diagnostics": [publish_diagnostic_payload(item) for item in diagnostics],
            "can_import": can_import,
        }

    def confirm_standard_import(
        self, preview_id: str, *, name: str | None = None
    ) -> dict[str, object]:
        """只消费预检快照；改名时验证并导入单独生成的包副本。"""
        previews = self.import_previews
        with previews.confirmation_lock:
            try:
                record = previews.require(preview_id)
            except ImportPreviewError as exc:
                raise _import_preview_error(exc) from exc
            if record.consumed is not None:
                return dict(record.consumed)
            import_path = record.snapshot_path
            renamed_copy: Path | None = None
            if name is not None:
                renamed_copy = previews.root / f"rename-{uuid.uuid4().hex}.dststandard"
                try:
                    import_path = copy_package_with_name(
                        record.snapshot_path, renamed_copy, name
                    )
                except StandardPackageError as exc:
                    raise store_error(exc) from exc
            try:
                # 仓储在库锁内重新完整读取改名后的包，并复核 ID 与名称。
                published = self.standard_store.import_package(import_path)
            except (StandardPackageError, StandardStoreError) as exc:
                raise store_error(exc) from exc
            finally:
                if renamed_copy is not None:
                    renamed_copy.unlink(missing_ok=True)
            result = {
                "standard_id": published.standard_id,
                "published_at": published.published_at,
                "name": published.name,
                "description": published.description,
                "diagnostics": [
                    publish_diagnostic_payload(item)
                    for item in self._published_diagnostics(published)
                ],
            }
            return previews.remember_result(preview_id, result)

    def cancel_standard_import(self, preview_id: str) -> None:
        """取消预检：删除快照并废弃凭证。"""
        self.import_previews.cancel(preview_id)

    def _import_preview_diagnostics(
        self, loaded
    ) -> tuple[tuple[StandardDiagnostic, ...], bool, bool, bool, str | None]:
        """运行发布、资产、ID 与规范化名称门禁。"""
        standard = loaded.standard
        diagnostics: list[StandardDiagnostic] = list(
            publish_diagnostics(standard) + publish_naming_diagnostics(standard)
        )
        try:
            validate_package_asset_files(
                standard, [entry.path for entry in loaded.entries]
            )
        except StandardAssetError as exc:
            diagnostics.append(
                StandardDiagnostic(code=str(exc).split(":", 1)[0], message=str(exc))
            )
        summaries = self.standard_store.list()
        id_owner = next(
            (item for item in summaries if item.standard_id == standard.standard_id), None
        )
        id_exists = id_owner is not None or self.standard_store.has_published_identity(
            standard.standard_id
        )
        if id_exists:
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_ID_EXISTS",
                    message=(
                        f"标准 ID {standard.standard_id!r} 已存在"
                        if id_owner is None
                        else f"标准 ID {standard.standard_id!r} 已由标准 {id_owner.name!r} 占用"
                    ),
                )
            )
            return tuple(diagnostics), False, True, False, (
                id_owner.name if id_owner is not None else None
            )

        normalized_name = normalize_standard_name(standard.name)
        name_owner = next(
            (
                item
                for item in summaries
                if normalize_standard_name(item.name) == normalized_name
                and normalized_name
            ),
            None,
        )
        name_conflict = name_owner is not None
        if name_owner is not None:
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_NAME_CONFLICT",
                    message=(
                        f"标准名称 {standard.name!r} 已由标准 "
                        f"{name_owner.standard_id!r} 占用"
                    ),
                )
            )
        has_validation_error = any(
            item.is_error and item.code != "STANDARD_NAME_CONFLICT"
            for item in diagnostics
        )
        can_import = not has_validation_error and not name_conflict
        return tuple(diagnostics), can_import, False, name_conflict, (
            name_owner.name if name_owner is not None else None
        )

    def export_standard_package(self, standard_id: str, dest_dir: Path) -> Path:
        try:
            return self.standard_store.export_package(standard_id, Path(dest_dir))
        except StandardStoreError as exc:
            raise store_error(exc) from exc
