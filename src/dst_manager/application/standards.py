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
    STANDARD_VERSION_PATTERN,
    DrawingStandard,
    StandardDiagnostic,
    parse_published_standard_document,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

from dst_manager.domain.standards import StandardSchemaError
from dst_manager.infrastructure.standards.store import StandardStoreError

#: 标准库稳定错误码 → HTTP 状态；未登记码一律 422。
_STORE_STATUS = {
    "STANDARD_VERSION_EXISTS": 409,
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
    version: str = ""
    standard: DrawingStandard | None = None
    source: str = ""
    diagnostics: tuple[ValidationIssue, ...] = ()


def parse_standard_identity(identity: str) -> tuple[str, str]:
    """解析 ``standard_id@version`` 身份；非法输入抛 422。"""
    standard_id, separator, version = identity.partition(IDENTITY_SEPARATOR)
    if (
        not separator
        or not STANDARD_ID_PATTERN.fullmatch(standard_id)
        or not STANDARD_VERSION_PATTERN.fullmatch(version)
    ):
        raise ApplicationError(
            "STANDARD_IDENTITY_INVALID", f"标准身份 {identity!r} 非法，应为 standard_id@version", 422
        )
    return standard_id, version


def snapshot_directory(root: Path, standard_id: str, version: str) -> Path:
    return Path(root) / ".dst-manager" / "standards" / standard_id / version


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
        self, standard_id: str, version: str
    ) -> tuple[DrawingStandard, str] | None:
        store = self.standard_store
        for root, source in (
            (store.published_root, "user-library"),
            (store.official_root, "official-library"),
        ):
            document = Path(root) / standard_id / version / "document.json"
            if document.is_file():
                return self._load_snapshot(document.parent), source
        return None

    def _restore_snapshot(
        self, workspace: Workspace, standard_id: str, version: str
    ) -> tuple[DrawingStandard, str] | None:
        store = self.standard_store
        for root, source in (
            (store.published_root, "user-library"),
            (store.official_root, "official-library"),
        ):
            source_dir = Path(root) / standard_id / version
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
        try:
            draft = self.standard_store.save_draft(draft_id, document)
        except (StandardStoreError, StandardSchemaError) as exc:
            raise _store_error(exc) from exc
        return {"draft_id": draft.draft_id, "document": draft.document}

    def save_standard_by_identity(
        self, standard_id: str, version: str, document: Mapping[str, object]
    ) -> dict[str, object]:
        """按身份保存用户草稿；已发布身份一律不可原地修改。"""
        if self.standard_store.get(standard_id, version) is not None:
            raise ApplicationError(
                "STANDARD_VERSION_IMMUTABLE",
                f"标准 {standard_id}@{version} 已发布，不可修改",
                409,
            )
        if document.get("standard_id") != standard_id or document.get("version") != version:
            raise ApplicationError(
                "STANDARD_IDENTITY_MISMATCH",
                f"文档身份 {document.get('standard_id')!r}@{document.get('version')!r} 与路径 {standard_id!r}@{version!r} 不一致",
                422,
            )
        draft_id = self._draft_id_with_identity(standard_id, version)
        if draft_id is None:
            raise ApplicationError("STANDARD_DRAFT_NOT_FOUND", f"身份 {standard_id}@{version} 无对应草稿", 404)
        return self.save_standard_draft(draft_id, document)

    def get_standard(self, standard_id: str, version: str) -> dict[str, object]:
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
        """发布草稿；完整发布门禁在目录移动前生效。

        声明的受信扩展依赖缺失时以 409 稳定拒绝；warning 随成功响应返回，
        不阻断发布。
        """
        draft = self.standard_store.get_draft(draft_id)
        if draft is None:
            raise ApplicationError("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在", 404)
        standard = parse_published_standard_document(draft.document)
        diagnostics = self._publish_gate(standard)
        if manifests is not None:
            self._require_dependencies(standard.dependencies, manifests)
        try:
            published = self.standard_store.publish(draft_id)
        except StandardStoreError as exc:
            raise _store_error(exc) from exc
        return {
            "standard_id": published.standard_id,
            "version": published.version,
            "name": published.name,
            "diagnostics": [_publish_diagnostic(item) for item in diagnostics],
        }

    def import_standard_package(self, path: Path) -> dict[str, object]:
        """导入标准包；包内文档同样要过完整发布门禁，失败不落库。"""
        try:
            loaded = self.standard_store.read_package(Path(path))
        except StandardStoreError as exc:
            raise _store_error(exc) from exc
        diagnostics = self._publish_gate(loaded.standard)
        try:
            published = self.standard_store.import_package(Path(path), loaded)
        except StandardStoreError as exc:
            raise _store_error(exc) from exc
        return {
            "standard_id": published.standard_id,
            "version": published.version,
            "name": published.name,
            "diagnostics": [_publish_diagnostic(item) for item in diagnostics],
        }

    def _publish_gate(
        self, standard: DrawingStandard
    ) -> tuple[StandardDiagnostic, ...]:
        """派生属性与 DWG 命名的发布诊断；首个 error 转稳定 422。"""
        diagnostics = publish_diagnostics(standard) + publish_naming_diagnostics(standard)
        first_error = next((item for item in diagnostics if item.is_error), None)
        if first_error is not None:
            raise ApplicationError(first_error.code, first_error.message, 422)
        return diagnostics

    def export_standard_package(self, standard_id: str, version: str, dest_dir: Path) -> Path:
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

    def _draft_id_with_identity(self, standard_id: str, version: str) -> str | None:
        # 草稿摘要的 version 恒为空串（身份在草稿文档内），必须逐份解析匹配。
        for summary in self.standard_store.list():
            if summary.status != "draft":
                continue
            draft = self.standard_store.get_draft(summary.draft_id or "")
            if (
                draft is not None
                and draft.document.get("standard_id") == standard_id
                and draft.document.get("version") == version
            ):
                return draft.draft_id
        return None


def _store_error(exc: Exception) -> ApplicationError:
    """标准库/Schema 错误码（消息前缀）转 HTTP 稳定错误；未登记码一律 422。"""
    code = str(exc).split(":", 1)[0]
    return ApplicationError(code, str(exc), _STORE_STATUS.get(code, 422))


def _publish_diagnostic(diagnostic: StandardDiagnostic) -> dict[str, object]:
    """发布检查诊断模型：错误码 + 严重级 + 可定位信息。"""
    return {
        "code": diagnostic.code,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "property_id": diagnostic.property_id,
        "segment_index": diagnostic.segment_index,
    }
