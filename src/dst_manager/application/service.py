import re
import shutil
import socket
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from dst_manager.application.cad_job import CadJobRunner
from dst_manager.application.drafts import DraftOperations
from dst_manager.application.editing import EditingOperations
from dst_manager.application.errors import ApplicationError
from dst_manager.application.property_import import PropertyImportOperations
from dst_manager.application.recovery import TransactionRecoveryOperations
from dst_manager.application.repair import RepairOperations
from dst_manager.application.revisions import RevisionRestoreOperations
from dst_manager.application.xml_io import XmlExportOperations
from dst_manager.config import Settings
from dst_manager.domain.models import (
    JobStatus,
    Severity,
    SheetSetDocument,
    Workspace,
)
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    CoreConsoleExecutor,
    ScriptRenderer,
    parse_layout_names,
)
from dst_manager.infrastructure.drafts import DraftStore
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.publisher import (
    PublishRecoveryError,
    RecoverablePublisher,
    capture_file_baseline,
    file_sha256,
)
from dst_manager.infrastructure.filesystem.workspace import write_workspace_metadata
from dst_manager.infrastructure.persistence import Database
from dst_manager.infrastructure.persistence.database import WorkspaceBusyError


class DstManagerService(
    DraftOperations,
    PropertyImportOperations,
    EditingOperations,
    RevisionRestoreOperations,
    XmlExportOperations,
    RepairOperations,
    TransactionRecoveryOperations,
):
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.database = Database(self.settings.database_url)
        self.codec = DstCodec()
        self.publisher = RecoverablePublisher()
        self.drafts = DraftStore(self.settings.draft_dir)
        for root in self.database.list_workspace_roots():
            try:
                rolled_back = self.publisher.recover(root)
            except PublishRecoveryError as exc:
                self._quarantine_unproven_publish_jobs(root, exc)
                continue
            for operation_id in rolled_back:
                try:
                    self.database.update_job(operation_id, JobStatus.ROLLED_BACK, 0, "STARTUP_RECOVERY")
                except KeyError:
                    pass
            for journal in self.publisher.list_committed_operations(root):
                self._recover_committed_job(root, journal)
        self.database.recover_stale_jobs(self.settings.worker_lease_seconds)

    def open_workspace(self, dst_path: Path, root_override: Path | None = None) -> Workspace:
        dst_path = dst_path.expanduser().resolve()
        if dst_path.suffix.lower() != ".dst" or not dst_path.is_file():
            raise ApplicationError("DST_NOT_FOUND", f"DST文件不存在：{dst_path}", 404)
        root = dst_path.parent
        try:
            self.publisher.recover(root)
        except PublishRecoveryError as exc:
            raise ApplicationError("PUBLISH_RECOVERY_FAILED", "工作区存在无法自动恢复的发布事务", 409) from exc
        revision = file_sha256(dst_path)
        workspace_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(dst_path).casefold()))
        acsm = load_acsm(self.codec.decode_file(dst_path))
        document = acsm.project(root, root_override)
        referenced = {sheet.layout.resolved_path for sheet in document.sheets if sheet.layout.resolved_path}
        unreferenced = sorted((path.resolve() for path in root.glob("*.dwg") if path.resolve() not in referenced), key=str)
        if unreferenced:
            document.diagnostics.append(self._issue("UNREFERENCED_DWG", "info", f"发现{len(unreferenced)}个未引用DWG"))
        workspace = Workspace(workspace_id, root, dst_path, revision, document, unreferenced)
        self.database.upsert_workspace(workspace_id, root, dst_path, revision, root_override)
        return workspace

    def get_workspace(self, workspace_id: str) -> Workspace:
        row = self.database.get_workspace(workspace_id)
        if row is None:
            raise ApplicationError("WORKSPACE_NOT_FOUND", "工作区不存在", 404)
        return self.open_workspace(Path(row.dst_path), Path(row.root_override) if row.root_override else None)

    def run_next_job(self) -> dict[str, Any] | None:
        self.database.recover_stale_jobs(self.settings.worker_lease_seconds)
        worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        job = self.database.claim_next_job(worker_id)
        if job is None:
            return None
        workspace = self.get_workspace(job["workspace_id"])
        capability = self._capability(job["cad_version"] or "2020")
        runner = CadJobRunner(
            self.database,
            self.codec,
            self.publisher,
            self.settings.cad_timeout_seconds,
            self.settings.cad_max_parallel,
            heartbeat_interval=min(30.0, self.settings.worker_lease_seconds / 3),
        )
        return runner.run(job, workspace, capability)

    def retry_job(self, job_id: str) -> dict[str, Any]:
        try:
            return self.database.retry_job(job_id)
        except KeyError as exc:
            raise ApplicationError("JOB_NOT_FOUND", "任务不存在", 404) from exc
        except ValueError as exc:
            raise ApplicationError("JOB_NOT_RETRYABLE", "当前任务状态不允许重试", 409) from exc
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc

    def get_job_details(self, job_id: str) -> dict[str, Any]:
        job = self.database.get_job(job_id)
        if job is None:
            raise ApplicationError("JOB_NOT_FOUND", "任务不存在", 404)
        row = self.database.get_workspace(job["workspace_id"])
        root = Path(row.root) if row else None
        files = []
        for item in job["files"]:
            public = dict(item)
            log_value = public.get("log_path")
            if log_value and Path(log_value).is_file():
                text = Path(log_value).read_text(encoding="utf-8", errors="replace")[-4000:]
                text = re.sub(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+", r"\1=<REDACTED>", text)
                if root:
                    text = text.replace(str(root), "<WORKSPACE>")
                text = text.replace(str(Path.home()), "<USER_HOME>")
                public["log_summary"] = text
            for key in ("target_path", "source_path", "log_path"):
                value = public.get(key)
                if value and root:
                    try:
                        public[key] = str(Path(value).resolve().relative_to(root.resolve()))
                    except ValueError:
                        public[key] = Path(value).name
            files.append(public)
        job["files"] = files
        job["summary"] = {
            "total": len(files),
            "succeeded": sum(item["status"] == "SUCCEEDED" for item in files),
            "failed": sum(item["status"] == "FAILED" for item in files),
            "duration_ms": sum(item.get("duration_ms") or 0 for item in files),
        }
        suggestions = {
            "CAD_CAPABILITY_UNAVAILABLE": "配置匹配版本的 Core Console 和 Worker 插件后重试。",
            "BLOCKED_FILE_LOCK": "关闭占用目标 DST/DWG 的程序后重试。",
            "CAD_TIMEOUT": "检查 CAD 日志、图纸复杂度和超时设置后重试。",
            "STAGING_DISK_SPACE_INSUFFICIENT": "释放工作区磁盘空间后重试。",
            "HANDLE_LAYOUT_MISMATCH": "检查模板布局名和 Worker 插件版本。",
            "PUBLISH_JOURNAL_REVIEW_REQUIRED": "先核对发布日志并完成恢复，禁止直接重跑。",
        }
        job["suggestion"] = suggestions.get(job["error_code"], "查看逐 DWG 日志和错误详情后决定是否重试。" if job["error_code"] else None)
        return job

    def capabilities(self) -> dict[str, dict[str, Any]]:
        capabilities = {version: self._capability(version) for version in ("2016", "2020")}
        return {version: {"version": version, "available": item.available, "console": str(item.console) if item.console else None, "plugin": str(item.plugin) if item.plugin else None} for version, item in capabilities.items()}

    def get_layout_names(self, file_path: Path, cad_version: str) -> dict:
        """读取 DWG/DWT 布局名，命中全局缓存直接返回，否则在临时副本上运行只读枚举。

        对用户路径复用 open_workspace（service.py:94 起）的同一校验模式：
        expanduser().resolve() + 扩展名 + is_file，保持入口校验逻辑一致。
        """
        resolved = file_path.expanduser().resolve()
        if resolved.suffix.casefold() not in {".dwg", ".dwt"}:
            raise ApplicationError("LAYOUT_SOURCE_TYPE_INVALID", "来源文件必须是 .dwg 或 .dwt", 422)
        if not resolved.is_file():
            raise ApplicationError("LAYOUT_SOURCE_NOT_FOUND", "来源文件不存在", 404)
        digest = file_sha256(resolved)
        cached = self.database.get_layout_names(digest)
        if cached is not None:
            return {"layouts": cached, "cached": True, "file_hash": digest}
        capability = self._capability(cad_version)
        if not capability.available:
            # 未配置是环境问题，不得混入"文件被占用"的执行失败提示
            raise ApplicationError(
                "CAD_CAPABILITY_UNAVAILABLE",
                f"AutoCAD {cad_version} 未配置：缺少 Core Console 或 Worker 插件路径，"
                "请检查 .env 配置或运行 dst-manager doctor",
                503,
            )
        renderer, executor = ScriptRenderer(), CoreConsoleExecutor()
        with tempfile.TemporaryDirectory(prefix="dst-layouts-") as tmp:
            work_dir = Path(tmp)
            # .dwt 同样复制为 source.dwg（同格式），避免 /i 按模板新建图形；
            # 在临时副本上运行，原文件不产生锁/临时文件，sidecar 落在 temp 内。
            shutil.copy2(resolved, work_dir / "source.dwg")
            script = renderer.render_layout_names(capability, work_dir)
            try:
                executor.run(capability, work_dir / "source.dwg", script, self.settings.cad_timeout_seconds)
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                raise ApplicationError("LAYOUT_READ_FAILED", "读取布局失败：DWG 可能正被 AutoCAD 占用或 CAD 环境不可用", 502) from exc
            sidecar = work_dir / "source.dst-layout-names.json"
            if not sidecar.is_file():
                raise ApplicationError("LAYOUT_READ_FAILED", "布局枚举未产出结果，请确认 Core Console 与插件配置", 502)
            layouts = parse_layout_names(sidecar)
        self.database.save_layout_names(digest, str(resolved), layouts)
        return {"layouts": layouts, "cached": False, "file_hash": digest}

    def _capability(self, version: str) -> CadCapability:
        if version == "2016":
            return CadCapability(version, self.settings.autocad_2016_console, self.settings.autocad_2016_plugin)
        if version == "2020":
            return CadCapability(version, self.settings.autocad_2020_console, self.settings.autocad_2020_plugin)
        raise ApplicationError("CAD_VERSION_INVALID", f"不支持的AutoCAD版本：{version}")

    def _check_revision(self, workspace: Workspace, base_revision_id: str) -> None:
        if workspace.revision_id != base_revision_id:
            raise ApplicationError("REVISION_CONFLICT", "基准修订已变化，请重新预览", 409)

    @staticmethod
    def _capture_baseline(path: Path):
        """共享基准捕获门禁：功能域模块经 self 引用，测试可整包替换。"""
        return capture_file_baseline(path)

    @staticmethod
    def _gate_writable(document: SheetSetDocument) -> None:
        """写入门禁：只有 VALID 工作区才能创建/执行写任务。

        `REPAIRED` 必须先完成独立修复修订；两个 INVALID 状态只能读和显示诊断。
        """
        report = getattr(document, "repair_report", None)
        status = report.status if report is not None else None
        if status is None or status == "VALID":
            return
        if status == "REPAIRED":
            raise ApplicationError(
                "REPAIR_CONFIRMATION_REQUIRED",
                "检测到可修复的 DST 元数据缺失，必须先在修复预览中确认并发布独立修复修订",
                409,
            )
        if status == "INVALID_REPAIR_REQUIRED":
            raise ApplicationError(
                "REPAIR_BLOCKED",
                "DST 存在需补充信息或决策的阻断问题，只能查看诊断，禁止写入",
                409,
            )
        raise ApplicationError(
            "REPAIR_UNRECOVERABLE",
            "DST 存在不可恢复问题，禁止写入",
            409,
        )

    def _issue(self, code: str, severity: str, message: str):
        from dst_manager.domain.models import ValidationIssue
        return ValidationIssue(code, Severity(severity), message)

    @staticmethod
    def _write_workspace_file(workspace: Workspace) -> None:
        write_workspace_metadata(workspace.root, workspace.id, workspace.dst_path, workspace.revision_id, "2020")
