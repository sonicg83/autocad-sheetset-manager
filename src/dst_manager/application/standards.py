"""图纸标准应用编排（PLAN-DM-035 Task 4/6，PLAN-DM-038 Task 4）。

`StandardOperations` 以 mixin 组合进 `DstManagerService`：承载标准库访问、
工作区标准绑定的解析与项目快照恢复，以及面向 API 的草稿/发布/导入/导出
事务转译（标准库错误码 → HTTP 稳定错误）。`DstManagerService` 只负责组合，
本模块不触碰派生求值（领域层）与包/库持久化（基础设施层）。

草稿保存只过结构门禁；**发布与导入**在目录移动前汇总完整发布门禁：
Schema 发布解析 + 派生属性发布诊断 + DWG 命名发布诊断，首个 error 转 422，
warning 随成功响应返回。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from dst_manager.application.errors import ApplicationError
from dst_manager.domain.models import Severity, ValidationIssue, Workspace
from dst_manager.domain.standard_naming import publish_naming_diagnostics
from dst_manager.domain.standard_rules import publish_diagnostics
from dst_manager.domain.standards import (
    STANDARD_ID_PATTERN,
    DrawingStandard,
    StandardDiagnostic,
    parse_published_standard_document,
    parse_standard_draft_document,
    parse_standard_version_segment,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

from dst_manager.domain.standards import StandardSchemaError
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    validate_package_asset_files,
)
from dst_manager.infrastructure.standards.import_previews import ImportPreviewError
from dst_manager.infrastructure.standards.store import StandardStoreError

#: 标准库稳定错误码 → HTTP 状态；未登记码一律 422。
_STORE_STATUS = {
    "STANDARD_VERSION_EXISTS": 409,
    "STANDARD_NAME_CONFLICT": 409,
    "STANDARD_VERSION_LIMIT_REACHED": 409,
    "STANDARD_DRAFT_EXISTS": 409,
    "STANDARD_VERSION_NOT_FOUND": 404,
    "STANDARD_DRAFT_NOT_FOUND": 404,
}

RESERVED_BINDING_PROPERTY = "DSTManager.Standard"
RESERVED_OPTIONS_PROPERTY = "DSTManager.StandardOptions"
RESERVED_PROPERTIES = (RESERVED_BINDING_PROPERTY, RESERVED_OPTIONS_PROPERTY)

IDENTITY_SEPARATOR = "@"


@dataclass(frozen=True, slots=True)
class StandardResolution:
    """工作区标准绑定解析结果。

    - ``unbound``：图纸集未绑定标准；
    - ``resolved``：已定位标准文档，``source`` 为 ``project-snapshot``/
      ``user-library``/``official-library``；
    - ``missing``：绑定的标准身份在三层库中均不存在，仅降级标准能力。
    """

    status: Literal["unbound", "resolved", "missing"]
    standard_id: str = ""
    version: int = 0
    standard: DrawingStandard | None = None
    source: str = ""
    diagnostics: tuple[ValidationIssue, ...] = ()


def parse_standard_identity(identity: str) -> tuple[str, int]:
    """解析 ``standard_id@<n>`` 绑定身份；非法输入抛 422。

    版本必须是规范十进制正整数（与目录段、路由段同一口径）：``@0``、``@01``、
    ``@1.0.0``、``@../`` 一律拒绝。
    """
    standard_id, separator, version = identity.partition(IDENTITY_SEPARATOR)
    if not separator or not STANDARD_ID_PATTERN.fullmatch(standard_id):
        raise ApplicationError(
            "STANDARD_IDENTITY_INVALID",
            f"标准身份 {identity!r} 非法，应为 standard_id@<正整数版本>",
            422,
        )
    try:
        parsed = parse_standard_version_segment(version)
    except Exception as exc:  # StandardSchemaError：稳定码已在消息前缀
        raise ApplicationError("STANDARD_IDENTITY_INVALID", str(exc), 422) from exc
    return standard_id, parsed


def snapshot_directory(root: Path, standard_id: str, version: int | str) -> Path:
    return Path(root) / ".dst-manager" / "standards" / standard_id / str(version)


class StandardOperations:
    """经 `self` 访问 database/settings 等入口依赖的标准功能域。"""

    standard_store: object  # 由 DstManagerService.__init__ 注入 StandardStore

    # ---- 标准库透传 ------------------------------------------------------

    def list_standards(self) -> list[dict[str, object]]:
        return [
            {
                "source": item.source,
                "status": item.status,
                "standard_id": item.standard_id,
                "version": item.version,
                "name": item.name,
                "draft_id": item.draft_id,
            }
            for item in self.standard_store.list()
        ]

    # ---- 绑定解析与快照恢复 ----------------------------------------------

    def resolve_workspace_standard(self, workspace_id: str) -> StandardResolution:
        """解析工作区标准绑定；快照缺失时按 ID/版本从标准库恢复。"""
        workspace = self.get_workspace(workspace_id)
        resolution = self._resolve_binding(workspace)
        if resolution.status != "resolved" or resolution.source == "project-snapshot":
            return resolution
        restored = self._restore_snapshot(workspace, resolution.standard_id, resolution.version)
        if restored is None:
            return StandardResolution(
                status="missing",
                standard_id=resolution.standard_id,
                version=resolution.version,
                diagnostics=(
                    ValidationIssue(
                        "STANDARD_MISSING",
                        Severity("warning"),
                        f"标准 {resolution.standard_id}@{resolution.version} 在标准库中不存在",
                    ),
                ),
            )
        standard, source = restored
        return StandardResolution(
            status="resolved",
            standard_id=resolution.standard_id,
            version=resolution.version,
            standard=standard,
            source=source,
        )

    def peek_workspace_standard(self, workspace: Workspace) -> StandardResolution:
        """只读解析（不恢复快照）：open_workspace 挂载与降级诊断用。"""
        return self._resolve_binding(workspace)

    def _resolve_binding(self, workspace: Workspace) -> StandardResolution:
        identity = workspace.document.custom_properties.get(
            RESERVED_BINDING_PROPERTY, ""
        ).strip()
        if not identity:
            return StandardResolution(status="unbound")
        try:
            standard_id, version = parse_standard_identity(identity)
        except ApplicationError as exc:
            return StandardResolution(
                status="missing",
                diagnostics=(
                    ValidationIssue("STANDARD_MISSING", Severity("error"), str(exc)),
                ),
            )
        snapshot = snapshot_directory(workspace.root, standard_id, version)
        if (snapshot / "document.json").is_file():
            return StandardResolution(
                status="resolved",
                standard_id=standard_id,
                version=version,
                standard=self._load_snapshot(snapshot),
                source="project-snapshot",
            )
        restored = self._locate_in_library(standard_id, version)
        if restored is not None:
            standard, source = restored
            return StandardResolution(
                status="resolved",
                standard_id=standard_id,
                version=version,
                standard=standard,
                source=source,
            )
        return StandardResolution(
            status="missing",
            standard_id=standard_id,
            version=version,
            diagnostics=(
                ValidationIssue(
                    "STANDARD_MISSING",
                    Severity("warning"),
                    f"标准 {standard_id}@{version} 不在官方/用户标准库中，标准能力已降级",
                ),
            ),
        )

    def _locate_in_library(
        self, standard_id: str, version: int
    ) -> tuple[DrawingStandard, str] | None:
        store = self.standard_store
        for root, source in (
            (store.published_root, "user-library"),
            (store.official_root, "official-library"),
        ):
            document = Path(root) / standard_id / str(version) / "document.json"
            if document.is_file():
                return self._load_snapshot(document.parent), source
        return None

    def _restore_snapshot(
        self, workspace: Workspace, standard_id: str, version: int
    ) -> tuple[DrawingStandard, str] | None:
        store = self.standard_store
        for root, source in (
            (store.published_root, "user-library"),
            (store.official_root, "official-library"),
        ):
            source_dir = Path(root) / standard_id / str(version)
            if not (source_dir / "document.json").is_file():
                continue
            snapshot = snapshot_directory(workspace.root, standard_id, version)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, snapshot)
            return self._load_snapshot(snapshot), source
        return None

    @staticmethod
    def _load_snapshot(directory: Path) -> DrawingStandard:
        import json

        from dst_manager.domain.standards import parse_published_standard_document

        return parse_published_standard_document(
            json.loads((directory / "document.json").read_text(encoding="utf-8"))
        )

    # ---- 绑定写入 --------------------------------------------------------

    def bind_workspace_standard(
        self, workspace_id: str, identity: str, base_revision_id: str
    ) -> dict[str, object]:
        """通过专用命令把标准身份写入图纸集保留属性。"""
        standard_id, version = parse_standard_identity(identity)
        commands = [{"type": "bind_standard", "standard": identity}]
        plan = self.preview_changes(workspace_id, base_revision_id, commands)
        if not plan["executable"]:
            raise ApplicationError("PLAN_INVALID", "执行计划包含阻断诊断")
        job = self.execute_changes(
            workspace_id,
            base_revision_id,
            commands,
            preview_digest=plan["preview_digest"],
        )
        return {
            "status": "bound",
            "standard_id": standard_id,
            "version": version,
            "job_id": job.get("id"),
        }

    # ---- 草稿/发布/导入导出 API 编排（Task 6） ----------------------------

    def create_standard_draft(
        self, document: Mapping[str, object], draft_id: str | None = None
    ) -> dict[str, object]:
        try:
            draft = self.standard_store.create_draft(document, draft_id)
        except (StandardStoreError, StandardSchemaError) as exc:
            raise _store_error(exc) from exc
        return {"draft_id": draft.draft_id, "document": draft.document}

    def get_standard_draft(self, draft_id: str) -> dict[str, object]:
        draft = self.standard_store.get_draft(draft_id)
        if draft is None:
            raise ApplicationError("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在", 404)
        return {"draft_id": draft.draft_id, "document": draft.document}

    def delete_standard_draft(self, draft_id: str) -> None:
        try:
            self.standard_store.delete_draft(draft_id)
        except StandardStoreError as exc:
            raise _store_error(exc) from exc

    def save_standard_draft(self, draft_id: str, document: Mapping[str, object]) -> dict[str, object]:
        """保存草稿：文档身份（标准 ID）必须等于草稿已存身份（F11）。

        身份不一致时以稳定 422 ``STANDARD_IDENTITY_MISMATCH`` 拒绝，不静默改写文档；
        结构与语义未完成内容仍按草稿门禁处理；草稿不携带正式版本（携带即 422）。
        """
        try:
            existing = self.standard_store.get_draft(draft_id)
        except StandardStoreError as exc:
            raise _store_error(exc) from exc
        if existing is None:
            raise ApplicationError(
                "STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在", 404
            )
        try:
            parse_standard_draft_document(document)  # 结构门禁先于身份核对
        except StandardSchemaError as exc:
            raise _store_error(exc) from exc
        _require_identity_match(existing.document, document)
        try:
            draft = self.standard_store.save_draft(draft_id, document)
        except (StandardStoreError, StandardSchemaError) as exc:
            raise _store_error(exc) from exc
        return {"draft_id": draft.draft_id, "document": draft.document}

    def get_standard(self, standard_id: str, version: int | str) -> dict[str, object]:
        standard = self.standard_store.get(standard_id, version)
        if standard is None:
            raise ApplicationError(
                "STANDARD_VERSION_NOT_FOUND", f"标准 {standard_id}@{version} 不存在", 404
            )
        document = self.standard_store.get_document(standard_id, version)
        return {
            "standard_id": standard.standard_id,
            "version": standard.version,
            "name": standard.name,
            "supported_cad_versions": list(standard.supported_cad_versions),
            "dependencies": [
                {
                    "extension_id": item.extension_id,
                    "capability_id": item.capability_id,
                    "min_version": item.min_version,
                }
                for item in standard.dependencies
            ],
            "document": document or {},
        }

    def publish_standard(
        self, draft_id: str, manifests: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """发布草稿：服务端分配整数版本，仓储锁内完整校验后原子提交。

        先过草稿结构门禁与受信扩展依赖门禁（缺失时 409），再由仓储分配
        ``max(官方, 用户) + 1`` 并跑完整发布门禁与名称唯一门禁；warning 随成功
        响应返回，不阻断发布。
        """
        draft = self.standard_store.get_draft(draft_id)
        if draft is None:
            raise ApplicationError("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在", 404)
        try:
            draft_standard = parse_standard_draft_document(draft.document)
        except StandardSchemaError as exc:
            # 草稿门禁允许的语义未完成内容在发布时必须以稳定 422 返回（不能冒泡成 500）
            raise _store_error(exc) from exc
        if manifests is not None:
            self._require_dependencies(draft_standard.dependencies, manifests)
        try:
            published = self.standard_store.publish(draft_id)
        except StandardStoreError as exc:
            raise _store_error(exc) from exc
        diagnostics = self._published_diagnostics(published)
        return {
            "standard_id": published.standard_id,
            "version": published.version,
            "name": published.name,
            "diagnostics": [_publish_diagnostic(item) for item in diagnostics],
        }

    def _published_diagnostics(self, published) -> tuple[StandardDiagnostic, ...]:
        """发布成功后的诊断：由仓储已校验的发布文档确定性重算。"""
        document = self.standard_store.get_document(
            published.standard_id, published.version
        )
        if document is None:
            return ()
        try:
            standard = parse_published_standard_document(document)
        except StandardSchemaError:
            return ()
        return publish_diagnostics(standard) + publish_naming_diagnostics(standard)

    def preview_standard_import(self, path: Path) -> dict[str, object]:
        """两步导入第一节：复制到限时快照、校验并返回预检凭证；**不写标准库**。

        身份/名称冲突以 ``can_import=False`` 与稳定诊断呈现（HTTP 200）；包或路径
        非法以 422 拒绝。校验失败时删除刚建立的快照，不在快照根留垃圾。
        """
        previews = self.import_previews
        try:
            snapshot = previews.snapshot_source(Path(path))
        except ImportPreviewError as exc:
            raise _import_preview_error(exc) from exc
        try:
            loaded = self.standard_store.read_package(snapshot)
        except StandardStoreError as exc:
            previews.discard_snapshot(snapshot)
            raise _store_error(exc) from exc
        standard = loaded.standard
        diagnostics, can_import = self._import_preview_diagnostics(loaded)
        try:
            record = previews.register(
                snapshot,
                {
                    "standard_id": standard.standard_id,
                    "version": standard.version,
                    "name": standard.name,
                    "supported_cad_versions": list(standard.supported_cad_versions),
                },
            )
        except BaseException:
            previews.discard_snapshot(snapshot)
            raise
        return {
            "preview_id": record.preview_id if can_import else None,
            "expires_at": previews.expires_at_iso(record) if can_import else None,
            "standard_id": standard.standard_id,
            "version": standard.version,
            "name": standard.name,
            "supported_cad_versions": list(standard.supported_cad_versions),
            "existing_versions": [
                {"source": item.source, "version": item.version}
                for item in self.standard_store.list()
                if item.status == "published" and item.standard_id == standard.standard_id
            ],
            "diagnostics": [_publish_diagnostic(item) for item in diagnostics],
            "can_import": can_import,
        }

    def confirm_standard_import(self, preview_id: str) -> dict[str, object]:
        """两步导入第二节：只消费预检快照，在仓储写入锁下复核后导入。

        同一凭证重复确认返回原成功结果（不二次写入）；确认前库状态变化（新增
        同身份或同名）由仓储锁内的复核以 409 拒绝。
        """
        previews = self.import_previews
        try:
            record = previews.require(preview_id)
        except ImportPreviewError as exc:
            raise _import_preview_error(exc) from exc
        if record.consumed is not None:
            return dict(record.consumed)
        try:
            published = self.standard_store.import_package(record.snapshot_path)
        except StandardStoreError as exc:
            raise _store_error(exc) from exc
        result = {
            "standard_id": published.standard_id,
            "version": published.version,
            "name": published.name,
            "diagnostics": [
                _publish_diagnostic(item)
                for item in self._published_diagnostics(published)
            ],
        }
        return previews.remember_result(preview_id, result)

    def cancel_standard_import(self, preview_id: str) -> None:
        """取消预检：删除快照并废弃凭证；之后确认一律要求重新预检。"""
        self.import_previews.cancel(preview_id)

    def _import_preview_diagnostics(
        self, loaded
    ) -> tuple[tuple[StandardDiagnostic, ...], bool]:
        """预检诊断与可否导入：错误阻断，warning 不阻断（与发布门禁同口径）。"""
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
        try:
            existing = self.standard_store.get(standard.standard_id, standard.version)
        except (StandardStoreError, StandardSchemaError) as exc:
            # 同身份的既有条目存在但不可读（残留 v1 或语义非法）：按身份已占用处理，
            # 不冒泡成 500（SPEC-DM-019 §4.3：身份冲突一律 200 + 诊断）。
            existing = exc
        if existing is not None:
            diagnostics.append(
                StandardDiagnostic(
                    code="STANDARD_VERSION_EXISTS",
                    message=f"标准 {standard.standard_id}@{standard.version} 已存在",
                )
            )
        try:
            self.standard_store.check_published_name(standard.standard_id, standard.name)
        except StandardStoreError as exc:
            diagnostics.append(
                StandardDiagnostic(code=str(exc).split(":", 1)[0], message=str(exc))
            )
        return tuple(diagnostics), not any(item.is_error for item in diagnostics)

    def export_standard_package(
        self, standard_id: str, version: int | str, dest_dir: Path
    ) -> Path:
        try:
            return self.standard_store.export_package(standard_id, version, Path(dest_dir))
        except StandardStoreError as exc:
            raise _store_error(exc) from exc

    def _require_dependencies(
        self, dependencies: tuple, manifests: Mapping[str, object]
    ) -> None:
        from dst_manager.extensions.capabilities import standard_dependency_gaps

        gaps = standard_dependency_gaps(dependencies, manifests)
        if not gaps:
            return
        detail = "；".join(
            f"{gap.extension_id}/{gap.capability_id}（{gap.reason}）" for gap in gaps
        )
        raise ApplicationError(
            "STANDARD_DEPENDENCY_MISSING",
            f"标准声明的受信扩展能力缺失：{detail}",
            409,
        )


def _require_identity_match(
    expected: Mapping[str, object], document: Mapping[str, object]
) -> None:
    """文档身份必须等于预期身份（草稿已存身份或路径身份）；两个保存入口共用。"""
    expected_id = expected.get("standard_id")
    expected_version = expected.get("version")
    if document.get("standard_id") != expected_id or document.get("version") != expected_version:
        raise ApplicationError(
            "STANDARD_IDENTITY_MISMATCH",
            f"文档身份 {document.get('standard_id')!r}@{document.get('version')!r} 与预期身份 {expected_id!r}@{expected_version!r} 不一致",
            422,
        )


def _store_error(exc: Exception) -> ApplicationError:
    """标准库/Schema 错误码（消息前缀）转 HTTP 稳定错误；未登记码一律 422。"""
    code = str(exc).split(":", 1)[0]
    return ApplicationError(code, str(exc), _STORE_STATUS.get(code, 422))


#: 预检错误码 → HTTP 状态；其余（含包、资产、路径与源不可读）一律 422。
#: SPEC-DM-019 §4.3：“包损坏、路径非法、**源不存在**、扩展名不符、超限等包或路径
#: 问题返回 HTTP 422”；只有凭证类错误才用 404/410。
_IMPORT_PREVIEW_STATUS = {
    "STANDARD_IMPORT_PREVIEW_NOT_FOUND": 404,
    "STANDARD_IMPORT_PREVIEW_EXPIRED": 410,
}


def _import_preview_error(exc: ImportPreviewError) -> ApplicationError:
    code = str(exc).split(":", 1)[0]
    return ApplicationError(code, str(exc), _IMPORT_PREVIEW_STATUS.get(code, 422))


def _publish_diagnostic(diagnostic: StandardDiagnostic) -> dict[str, object]:
    """发布检查诊断模型：错误码 + 严重级 + 可定位信息。"""
    return {
        "code": diagnostic.code,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "property_id": diagnostic.property_id,
        "segment_index": diagnostic.segment_index,
    }
