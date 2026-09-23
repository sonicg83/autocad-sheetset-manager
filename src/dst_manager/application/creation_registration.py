"""创建成果登记：把已发布的新项目接管为普通工作区与初始修订（PLAN-DM-036 Task 7）。

`CreationRegistrationOperations` 以 mixin 组合进 `DstManagerService`（与
:mod:`dst_manager.application.creation_execution` 同层拆分：登记属于独立职责，
入口类只做装配）。它只编排既有原语，不复制任何领域规则：

- 只在项目文件**完整发布**之后登记：已发布 DST 与发布事务归档的修订清单
  （``revision_dir/manifest.json``）必须齐全，否则登记失败；
- 普通工作区登记复用 ``open_workspace``（同一套工作区 ID 推导、修订哈希与
  ``workspaces`` 行写入），标准绑定复用 ``resolve_workspace_standard``（项目内快照
  由既有恢复路径物化），初始修订复用 ``Database.add_revision`` 与发布事务已归档的
  清单格式，不另立第二套修订清单；
- 对外成功响应（``workspace_id``/``revision_id``/``dst_path``）只在文件、SQLite、
  修订清单一致**且工作区能重新打开**之后产生：重新打开用 ``get_workspace``
  复核已登记行、DST 内容哈希与元数据是否自洽；
- 登记失败保留已发布文件、发布日志与修订证据，任务落 ``NEEDS_REVIEW``（绝不落
  ``SUCCEEDED``），并由启动恢复按持久成果投影**幂等补登记**；补登记只写数据库与
  项目内快照/元数据，绝不重新生成或覆盖任何成果文件；
- 标准库中版本缺失不阻断登记：工作区仍可打开，绑定语义由 DST 内的标准身份与
  项目内快照承载，缺失只降级为标准能力诊断（``STANDARD_MISSING``）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from dst_manager.application.creation_candidate import CreationJobError
from dst_manager.application.standards import (
    RESERVED_BINDING_PROPERTY,
    RESERVED_OPTIONS_PROPERTY,
)
from dst_manager.domain.models import JobStatus, Workspace
from dst_manager.infrastructure.filesystem.project_publish_types import PublishedProject
from dst_manager.infrastructure.filesystem.workspace import write_workspace_metadata
from dst_manager.infrastructure.logging_text import sanitize_log_text

__all__ = [
    "CREATION_REGISTRATION_FAILED",
    "CreationRegistrar",
    "CreationRegistration",
    "CreationRegistrationOperations",
    "PublishedCreation",
]

#: 登记失败的稳定错误码：任务落 ``NEEDS_REVIEW``，界面按该码给出人工核对提示。
CREATION_REGISTRATION_FAILED = "CREATION_REGISTRATION_FAILED"
#: 初始修订的来源摘要 schema（版本化 JSON；与标准导入来源摘要同一形态）。
_CREATION_SOURCE_SCHEMA = "dst-manager.creation-source/v1"


class CreationRegistrar(Protocol):
    """发布成功后的登记回调（由应用层入口实现；创建运行器只按协议调用）。"""

    def finish_creation(
        self,
        published: PublishedProject,
        *,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> CreationRegistration: ...


@dataclass(frozen=True, slots=True)
class PublishedCreation:
    """一次已发布创建成果的登记输入。

    两种来源共用同一形状：发布事务返回的 :class:`PublishedProject`（Worker 路径）
    与任务持久化的成果投影 ``jobs.payload.published``（启动恢复路径）。后者是
    「续办身份」——恢复只消费它，绝不回到暂存区重新生成成果。
    """

    job_id: str
    attempt: int
    target_dir: Path
    dst_path: Path
    revision_dir: Path
    payload: dict[str, Any]

    @classmethod
    def from_project(cls, published: PublishedProject) -> PublishedCreation:
        return cls(
            job_id=published.job_id,
            attempt=published.attempt,
            target_dir=published.target_dir,
            dst_path=published.dst_path,
            revision_dir=published.revision_dir,
            payload=published.to_payload(),
        )

    @classmethod
    def from_payload(cls, job_id: str, payload: Mapping[str, Any]) -> PublishedCreation:
        """按持久成果投影重建登记输入；结构不可信即稳定拒绝，绝不猜测路径。"""
        target_dir = payload.get("target_dir")
        dst_path = payload.get("dst_path")
        revision_dir = payload.get("revision_dir")
        attempt = payload.get("attempt")
        if (
            not isinstance(target_dir, str)
            or not target_dir
            or not isinstance(dst_path, str)
            or not isinstance(revision_dir, str)
            or not revision_dir
            or type(attempt) is not int
            or attempt < 1
        ):
            raise CreationJobError(
                CREATION_REGISTRATION_FAILED, "创建成果投影缺少可用的目标/成果/修订路径"
            )
        resolved_target = Path(target_dir)
        resolved_dst = Path(dst_path)
        if not resolved_target.is_absolute() or resolved_dst.parent != resolved_target:
            raise CreationJobError(
                CREATION_REGISTRATION_FAILED,
                f"创建成果投影的 DST 路径 {dst_path!r} 不在目标目录 {target_dir!r} 内",
            )
        return cls(
            job_id=job_id,
            attempt=attempt,
            target_dir=resolved_target,
            dst_path=resolved_dst,
            revision_dir=Path(revision_dir),
            payload=dict(payload),
        )


@dataclass(frozen=True, slots=True)
class CreationRegistration:
    """一次创建成果登记的结论：任务身份、登记产物与失败诊断。

    成功时 ``workspace_id``/``revision_id``/``dst_path`` 三者齐备（对外成功响应的
    必需字段）；登记失败时 ``workspace_id``/``revision_id`` 为空，``dst_path`` 仍
    给出已发布成果的位置（人工核对与续办身份），``status`` 为 ``NEEDS_REVIEW``。
    """

    job_id: str
    status: str
    workspace_id: str | None
    revision_id: str | None
    dst_path: str | None
    error_code: str | None = None
    error_detail: str | None = None


class CreationRegistrationOperations:
    """经 `self` 访问 database/standard_store 的创建登记功能域。"""

    def finish_creation(
        self,
        published: PublishedProject,
        *,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> CreationRegistration:
        """发布成功后登记普通工作区与初始修订；失败落 ``NEEDS_REVIEW``。

        ``worker_id``/``attempt`` 给出时按任务租约围栏写入终态（Worker 路径），
        租约已丢失则只读回现场、绝不覆盖新主人的状态。
        """
        return self._register_published_creation(
            PublishedCreation.from_project(published), worker_id=worker_id, attempt=attempt
        )

    def resume_creation_registration(
        self, job_id: str, payload: Mapping[str, Any]
    ) -> CreationRegistration:
        """启动恢复的幂等补登记：只消费持久成果投影，绝不重新生成或覆盖成果。"""
        try:
            published = PublishedCreation.from_payload(job_id, payload)
        except CreationJobError as exc:
            return self._isolate_registration_failure(job_id, None, exc)
        return self._register_published_creation(published)

    # ---- 登记主流程 ------------------------------------------------------

    def _register_published_creation(
        self,
        published: PublishedCreation,
        *,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> CreationRegistration:
        try:
            workspace_id, revision_id = self._register_published_workspace(published)
        except Exception as exc:  # noqa: BLE001 - 登记边界必须把任意故障落成可核对终态
            return self._isolate_registration_failure(
                published.job_id, published.dst_path, exc, worker_id=worker_id, attempt=attempt
            )
        return self._close_registered_creation(
            published, workspace_id, revision_id, worker_id=worker_id, attempt=attempt
        )

    def _register_published_workspace(self, published: PublishedCreation) -> tuple[str, str]:
        """登记普通工作区与初始修订，返回 ``(workspace_id, revision_id)``。"""
        self._require_published_artifacts(published)
        # 打开即登记：工作区 ID、修订哈希与 workspaces 行都走既有 open_workspace 口径。
        workspace = self.open_workspace(
            published.dst_path, workspace_root=published.target_dir
        )
        # 标准绑定只读解析：项目内快照由既有恢复路径物化；库中版本缺失只降级为诊断，
        # 不阻断登记（工作区仍可打开，语义由 DST 内的标准身份与快照承载）。
        self.resolve_workspace_standard(workspace.id)
        write_workspace_metadata(
            workspace.root,
            workspace.id,
            workspace.dst_path,
            workspace.revision_id,
            self._job_cad_version(published.job_id),
        )
        self._record_initial_revision(published, workspace)
        self._require_reopenable(workspace)
        return workspace.id, workspace.revision_id

    def _close_registered_creation(
        self,
        published: PublishedCreation,
        workspace_id: str,
        revision_id: str,
        *,
        worker_id: str | None,
        attempt: int | None,
    ) -> CreationRegistration:
        """登记完成之后才闭环任务：成功响应在此之后产生。"""
        applied = self.database.finalize_creation_job(
            published.job_id,
            published.payload,
            workspace_id=workspace_id,
            revision_id=revision_id,
            worker_id=worker_id,
            attempt=attempt,
        )
        if not applied:
            # 租约已丢失：登记产物留在磁盘，任务状态由新主人决定，这里只读回现场。
            return self._registration_of(published.job_id, str(published.dst_path))
        return CreationRegistration(
            job_id=published.job_id,
            status=JobStatus.SUCCEEDED,
            workspace_id=workspace_id,
            revision_id=revision_id,
            dst_path=str(published.dst_path),
        )

    # ---- 登记步骤 --------------------------------------------------------

    @staticmethod
    def _require_published_artifacts(published: PublishedCreation) -> None:
        """成果文件与修订清单必须齐全：缺任何一项都不算「完整发布」。"""
        if not published.dst_path.is_file():
            raise CreationJobError(
                CREATION_REGISTRATION_FAILED, f"已发布 DST 不存在：{published.dst_path}"
            )
        manifest = published.revision_dir / "manifest.json"
        if not manifest.is_file():
            raise CreationJobError(
                CREATION_REGISTRATION_FAILED, f"修订清单缺失：{manifest}"
            )

    def _record_initial_revision(
        self, published: PublishedCreation, workspace: Workspace
    ) -> None:
        """记初始修订：修订 ID 与已发布 DST 的内容哈希同值（与 current_revision 同口径）。

        初始修订没有前序 DST，``before_hash`` 记为空串（列非空）；修订清单复用发布
        事务归档的 ``manifest.json``。幂等：同 ID 同身份已存在即跳过，身份不一致以
        ``CREATION_REGISTRATION_FAILED`` 拒绝（绝不覆盖既有修订记录）。
        """
        revision_id = workspace.revision_id
        revision_dir = str(published.revision_dir)
        existing = self.database.get_revision(revision_id)
        if existing is not None:
            actual = (
                existing["workspace_id"],
                existing["operation_id"],
                existing["result_hash"],
                existing["revision_dir"],
            )
            if actual != (workspace.id, published.job_id, revision_id, revision_dir):
                raise CreationJobError(
                    CREATION_REGISTRATION_FAILED,
                    f"修订 {revision_id} 已存在且身份不一致，禁止覆盖既有修订",
                )
            return
        self.database.add_revision(
            revision_id,
            workspace.id,
            published.job_id,
            "",
            revision_id,
            published.revision_dir,
            current_revision=revision_id,
            kind="creation",
            source_json=_creation_source_json(published, workspace),
        )

    def _require_reopenable(self, workspace: Workspace) -> None:
        """重新打开已登记工作区：SQLite 行、DST 内容与元数据必须自洽。"""
        reopened = self.get_workspace(workspace.id)
        if (
            reopened.revision_id != workspace.revision_id
            or reopened.dst_path.resolve() != workspace.dst_path.resolve()
            or reopened.root.resolve() != workspace.root.resolve()
        ):
            raise CreationJobError(
                CREATION_REGISTRATION_FAILED,
                f"重新打开工作区 {workspace.id} 后修订或路径与登记不一致",
            )

    def _job_cad_version(self, job_id: str) -> str:
        job = self.database.get_job(job_id)
        version = (job or {}).get("cad_version")
        return version if isinstance(version, str) and version else "2020"

    # ---- 失败隔离 --------------------------------------------------------

    def _isolate_registration_failure(
        self,
        job_id: str,
        dst_path: Path | None,
        exc: BaseException,
        *,
        worker_id: str | None = None,
        attempt: int | None = None,
    ) -> CreationRegistration:
        """把登记失败隔离为 ``NEEDS_REVIEW``：保留现场与续办身份，绝不报普通成功。"""
        code = getattr(exc, "code", "") or CREATION_REGISTRATION_FAILED
        detail = sanitize_log_text(str(exc))
        if self.database.get_job(job_id) is not None:
            self.database.finalize_job_terminal(
                job_id,
                JobStatus.NEEDS_REVIEW,
                code,
                detail,
                worker_id=worker_id,
                attempt=attempt,
            )
        return CreationRegistration(
            job_id=job_id,
            status=JobStatus.NEEDS_REVIEW,
            workspace_id=None,
            revision_id=None,
            dst_path=str(dst_path) if dst_path is not None else None,
            error_code=code,
            error_detail=detail,
        )

    def _registration_of(self, job_id: str, dst_path: str) -> CreationRegistration:
        """按数据库现状回报（租约丢失时不写入，只反映新主人的状态）。"""
        job = self.database.get_job(job_id) or {}
        registration = job.get("payload", {}).get("workspace") or {}
        return CreationRegistration(
            job_id=job_id,
            status=job.get("status", JobStatus.NEEDS_REVIEW),
            workspace_id=job.get("workspace_id"),
            revision_id=registration.get("revision_id"),
            dst_path=registration.get("dst_path") or dst_path,
            error_code=job.get("error_code"),
            error_detail=job.get("error_detail"),
        )


def _creation_source_json(published: PublishedCreation, workspace: Workspace) -> str:
    """初始修订的来源摘要：固定标准身份与本次生效的编号配置。"""
    properties = workspace.document.custom_properties
    return json.dumps(
        {
            "schema": _CREATION_SOURCE_SCHEMA,
            "job_id": published.job_id,
            "attempt": published.attempt,
            "standard": properties.get(RESERVED_BINDING_PROPERTY, ""),
            "numbering_options": _numbering_options(properties),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _numbering_options(properties: Mapping[str, str]) -> dict[str, Any] | None:
    """DST 保留属性里的有效编号配置；缺失或不可解析时记 ``None``（不猜测值）。"""
    raw = properties.get(RESERVED_OPTIONS_PROPERTY, "")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None
