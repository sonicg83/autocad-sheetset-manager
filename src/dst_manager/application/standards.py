"""图纸标准应用编排（PLAN-DM-035 Task 4）。

`StandardOperations` 以 mixin 组合进 `DstManagerService`：承载标准库访问、
工作区标准绑定的解析与项目快照恢复。`DstManagerService` 只负责组合，
本模块不触碰规则求值（领域层）与包/库持久化（基础设施层）。
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dst_manager.application.errors import ApplicationError
from dst_manager.domain.models import Severity, ValidationIssue, Workspace
from dst_manager.domain.standards import (
    STANDARD_ID_PATTERN,
    STANDARD_VERSION_PATTERN,
    DrawingStandard,
)

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

        from dst_manager.domain.standards import parse_standard_document

        return parse_standard_document(
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
