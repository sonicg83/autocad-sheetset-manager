import csv
import hashlib
import io
import json
import re
import shutil
import socket
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dst_manager.application.cad_job import CadJobRunner
from dst_manager.config import Settings
from dst_manager.domain.editing import (
    parse_property_csv_result,
    property_definitions_from_document,
)
from dst_manager.domain.models import (
    JobStatus,
    Severity,
    SuffixOptions,
    Workspace,
)
from dst_manager.domain.planning import (
    PlanningError,
    build_structural_plan,
    derived_document_from_plan,
)
from dst_manager.infrastructure.acsm_xml import AcsmDocument, AcsmValidationError
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    CoreConsoleExecutor,
    ScriptRenderer,
    parse_handles,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.locking import (
    FileLockError,
    WindowsResultGuards,
    WindowsWriteLocks,
)
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
    RecoverablePublisher,
    capture_file_baseline,
    file_sha256,
)
from dst_manager.infrastructure.filesystem.workspace import write_workspace_metadata
from dst_manager.infrastructure.operation_log import append_operation_event
from dst_manager.infrastructure.persistence import Database
from dst_manager.infrastructure.persistence.database import WorkspaceBusyError


class ApplicationError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class DstManagerService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.database = Database(self.settings.database_url)
        self.codec = DstCodec()
        self.publisher = RecoverablePublisher()
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
        acsm = AcsmDocument(self.codec.decode_file(dst_path))
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

    def preview_custom_property_import(
        self,
        workspace_id: str,
        base_revision_id: str,
        csv_data: bytes,
    ) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        parsed = parse_property_csv_result(csv_data)
        existing = {
            item.name.casefold(): item
            for item in property_definitions_from_document(workspace.document)
        }
        changes: list[dict[str, Any]] = []
        commands: list[dict[str, Any]] = []
        diagnostics = [
            {
                "code": item.code,
                "severity": "error",
                "message": item.message,
                "line": item.line,
            }
            for item in parsed.diagnostics
        ]
        for record in parsed.records:
            line = record.line
            definition = record.definition
            previous = existing.get(definition.name.casefold())
            action = "add"
            if previous is not None and previous.type != definition.type:
                action = "conflict"
                diagnostics.append(
                    {
                        "code": "CUSTOM_PROPERTY_TYPE_CONFLICT",
                        "severity": "error",
                        "message": f"自定义属性类型冲突：{definition.name}",
                        "line": line,
                    },
                )
            elif previous is not None and previous.name != definition.name:
                action = "conflict"
                diagnostics.append(
                    {
                        "code": "CUSTOM_PROPERTY_NAME_DUPLICATE",
                        "severity": "error",
                        "message": f"自定义属性名称大小写冲突：{definition.name}",
                        "line": line,
                    },
                )
            elif previous is not None:
                action = "skip"
            else:
                command = {
                    "type": "add_custom_property",
                    "property_type": definition.type,
                    "name": definition.name,
                    "default_value": definition.default_value,
                }
                commands.append(command)
                existing[definition.name.casefold()] = definition
            changes.append(
                {
                    "line": line,
                    "action": action,
                    "type": definition.type,
                    "name": definition.name,
                    "default_value": definition.default_value,
                    "affected_sheet_count": len(workspace.document.sheets) if definition.type == "sheet" else 0,
                },
            )
        main_preview = self.preview_changes(workspace_id, base_revision_id, commands)
        diagnostics.extend(main_preview["diagnostics"])
        return {
            **main_preview,
            "changes": changes,
            "commands": commands,
            "diagnostics": diagnostics,
            "executable": not any(item["severity"] == "error" for item in diagnostics),
        }

    def import_custom_properties(
        self,
        workspace_id: str,
        base_revision_id: str,
        csv_data: bytes,
    ) -> dict[str, Any]:
        preview = self.preview_custom_property_import(workspace_id, base_revision_id, csv_data)
        if not preview["executable"]:
            raise ApplicationError("PLAN_INVALID", "属性 CSV 导入计划包含阻断诊断")
        if not preview["commands"]:
            return {
                "id": None,
                "workspace_id": workspace_id,
                "status": "SUCCEEDED",
                "revision_id": base_revision_id,
                "no_op": True,
            }
        return self.execute_changes(workspace_id, base_revision_id, preview["commands"])

    def export_custom_properties_csv(self, workspace_id: str) -> bytes:
        workspace = self.get_workspace(workspace_id)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(["type", "name", "default_value"])
        for definition in property_definitions_from_document(workspace.document):
            writer.writerow([definition.type, definition.name, definition.default_value])
        return stream.getvalue().encode("utf-8")

    def preview_changes(
        self,
        workspace_id: str,
        base_revision_id: str,
        commands: list[dict[str, Any]],
        cad_version: str = "2020",
    ) -> dict[str, Any]:
        if cad_version not in {"2016", "2020"}:
            raise ApplicationError("CAD_VERSION_INVALID", f"不支持的AutoCAD版本：{cad_version}", 422)
        normalized_commands = self._normalize_commands(commands)
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        sheet_ids = {sheet.acsm_id for sheet in workspace.document.sheets}
        diagnostics = []
        changes = []
        structural = False
        for index, (command, normalized_command) in enumerate(zip(commands, normalized_commands, strict=True)):
            command_type = command["type"]
            sheet_id = command.get("sheet_id")
            if command_type in {"update_sheet_properties", "delete_sheet"} and sheet_id not in sheet_ids:
                diagnostics.append({"code": "SHEET_NOT_FOUND", "severity": "error", "message": f"找不到图纸：{sheet_id}", "index": index})
            if command_type in {"insert_sheet", "insert_subset"} and not command.get("source"):
                diagnostics.append({"code": "LAYOUT_SOURCE_REQUIRED", "severity": "error", "message": "新增图纸必须明确布局来源", "index": index})
            structural |= command_type in {"update_subset_title", "delete_sheet", "insert_sheet", "insert_subset"}
            changes.append(
                {
                    "index": index,
                    "type": normalized_command["type"],
                    "object_id": sheet_id,
                    "after": normalized_command,
                },
            )
        property_commands = [
            command
            for command in normalized_commands
            if command["type"] in {"add_custom_property", "delete_custom_property"}
        ]
        if structural and property_commands:
            diagnostics.append(
                {
                    "code": "COMMAND_COMBINATION_UNSUPPORTED",
                    "severity": "error",
                    "message": "属性定义与 CAD 结构命令必须分别预览和执行",
                },
            )
        execution_intent = None
        if structural and not diagnostics:
            try:
                execution_intent = build_structural_plan(
                    workspace,
                    [command for command in normalized_commands if command not in property_commands],
                    SuffixOptions(
                        self.settings.enable_add_number_suffix,
                        self.settings.number_suffix_type,
                    ),
                )
            except PlanningError as exc:
                diagnostics.append({"code": exc.code, "severity": "error", "message": str(exc)})
        if execution_intent is not None and not diagnostics:
            diagnostics.extend(self._inspect_structural_sources(workspace, execution_intent, cad_version))
            if not diagnostics:
                try:
                    self._attach_expected_file_hashes(workspace, execution_intent)
                except OSError as exc:
                    diagnostics.append(
                        {
                            "code": "LAYOUT_SOURCE_UNREADABLE",
                            "severity": "error",
                            "message": f"布局来源无法读取：{exc}",
                        },
                    )
        if not diagnostics:
            try:
                preview_dom = AcsmDocument(self.codec.decode_file(workspace.dst_path)).clone()
                if structural:
                    preview_dom.apply_derived_document(derived_document_from_plan(execution_intent))
                self._apply_nonstructural_commands(preview_dom, normalized_commands, structural)
                planned_sheet_ids = {
                    layout["sheet_id"]
                    for group in execution_intent["groups"]
                    for layout in group["layouts"]
                } if execution_intent else set()
                for issue in preview_dom.validate():
                    if issue.object_id in planned_sheet_ids and issue.code in {"LAYOUT_FIELD_MISSING", "LAYOUT_HANDLE_PLACEHOLDER"}:
                        continue
                    if issue.severity == Severity.ERROR:
                        diagnostics.append({"code": issue.code, "severity": "error", "message": issue.message, "object_id": issue.object_id})
            except AcsmValidationError as exc:
                code, _, detail = str(exc).partition(":")
                messages = {
                    "CUSTOM_PROPERTY_FLAGS_MISSING": "自定义属性缺少 Flags，无法确定属性作用域。",
                    "CUSTOM_PROPERTY_FLAGS_INVALID": "自定义属性的 Flags 无效，无法确定属性作用域。",
                    "CUSTOM_PROPERTY_SCOPE_MISMATCH": "自定义属性作用域与当前编辑对象不一致。",
                    "CUSTOM_PROPERTY_DUPLICATED": "同一作用域中存在重复的同名自定义属性。",
                    "CUSTOM_PROPERTY_VALUE_DUPLICATED": "自定义属性存在多个 Value，无法安全选择写入目标。",
                    "CUSTOM_PROPERTY_NOT_FOUND": "找不到要更新的自定义属性定义。",
                    "CUSTOM_PROPERTY_NAME_DUPLICATE": "自定义属性名称已存在。",
                    "CUSTOM_PROPERTY_TYPE_CONFLICT": "自定义属性名称属于另一作用域。",
                    "CUSTOM_PROPERTY_NAME_EMPTY": "自定义属性名称不能为空。",
                    "CUSTOM_PROPERTY_NAME_INVALID": "自定义属性名称无效。",
                    "CUSTOM_PROPERTY_TYPE_INVALID": "自定义属性类型无效。",
                    "CUSTOM_PROPERTY_VALUE_INVALID": "自定义属性值包含 XML 1.0 禁止字符。",
                    "XML_TEXT_INVALID": "文本包含 XML 1.0 禁止字符。",
                }
                diagnostics.append({"code": code, "severity": "error", "message": messages.get(code, "AcSm 结构不支持当前修改。"), "property_name": detail.strip() or None})
        affected = {str(workspace.dst_path)}
        if execution_intent:
            affected.update(group["target_file"] for group in execution_intent["groups"])
            affected.update(group["source_target_file"] for group in execution_intent["groups"] if group["source_target_file"] is not None)
            affected.update(item["target_file"] for item in execution_intent["deleted_subsets"])
        semantic_diff = self._build_semantic_diff(workspace, normalized_commands, execution_intent)
        property_counts = {
            (item["action"], item["type"], item["name"]): item["affected_sheet_count"]
            for item in semantic_diff["properties"]
        }
        for change in changes:
            command = change["after"]
            if command["type"] in {"add_custom_property", "delete_custom_property"}:
                action = "add" if command["type"] == "add_custom_property" else "delete"
                change["affected_sheet_count"] = property_counts.get(
                    (action, command.get("property_type"), command.get("name")),
                    0,
                )
        preview_digest = self._preview_digest(
            base_revision_id,
            cad_version,
            normalized_commands,
            execution_intent,
            semantic_diff,
        )
        return {
            "workspace_id": workspace_id,
            "base_revision_id": base_revision_id,
            "cad_version": cad_version,
            "requires_cad": structural,
            "affected_files": sorted(affected),
            "execution_intent": execution_intent,
            "semantic_diff": semantic_diff,
            "preview_digest": preview_digest,
            "changes": changes,
            "diagnostics": diagnostics,
            "executable": not any(item["severity"] == "error" for item in diagnostics),
        }

    def execute_changes(
        self,
        workspace_id: str,
        base_revision_id: str,
        commands: list[dict[str, Any]],
        cad_version: str = "2020",
        preview_digest: str | None = None,
    ) -> dict[str, Any]:
        plan = self.preview_changes(workspace_id, base_revision_id, commands, cad_version)
        if not plan["executable"]:
            raise ApplicationError("PLAN_INVALID", "执行计划包含阻断诊断")
        if plan["requires_cad"] and preview_digest != plan["preview_digest"]:
            raise ApplicationError("REPREVIEW_REQUIRED", "结构变更预览已变化或尚未确认，请重新预览并确认", 409)
        normalized_commands = self._normalize_commands(commands)
        job_id = str(uuid.uuid4())
        try:
            self.database.create_job(job_id, workspace_id, "change_set", JobStatus.VALIDATED, {"base_revision_id": base_revision_id, "plan": plan, "commands": normalized_commands}, cad_version)
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc
        if plan["requires_cad"]:
            capability = self.capabilities()[cad_version]
            if capability["available"]:
                self.database.update_job(job_id, JobStatus.QUEUED, 0)
            else:
                self.database.update_job(job_id, JobStatus.FAILED, 0, "CAD_CAPABILITY_UNAVAILABLE")
            return self.database.get_job(job_id) or {}
        workspace = self.get_workspace(workspace_id)
        operation_id = job_id
        published = False
        commit_state: dict[str, Any] = {"result_hash": None, "error": None}
        try:
            with WindowsWriteLocks([workspace.dst_path]):
                try:
                    expected_baseline = capture_file_baseline(workspace.dst_path)
                except OSError as exc:
                    raise PublishBaselineError("捕获 DST 执行基准时文件发生变化") from exc
                if expected_baseline is None or expected_baseline.sha256 != base_revision_id:
                    raise PublishBaselineError("DST 已偏离提交预览基准")
                self.database.update_job(job_id, JobStatus.STAGING, 20)
                self._safe_operation_event(workspace.root, job_id, "STAGING", job_type="metadata")
                acsm = AcsmDocument(self.codec.decode_file(workspace.dst_path))
                try:
                    self._apply_nonstructural_commands(acsm, normalized_commands, structural=False)
                except AcsmValidationError as exc:
                    code = str(exc).split(":", 1)[0]
                    raise ApplicationError(code, str(exc)) from exc
                issues = acsm.validate()
                if any(issue.severity == Severity.ERROR for issue in issues):
                    raise ApplicationError("XML_VALIDATION_FAILED", "DST XML 校验失败")
                job_dir = workspace.root / ".dst-manager" / "jobs" / operation_id
                staging = job_dir / "staging" / workspace.dst_path.name
                staging.parent.mkdir(parents=True, exist_ok=True)
                self.codec.encode_file(acsm.to_bytes(), staging)
                AcsmDocument(self.codec.decode_file(staging))
                self.database.update_job(job_id, JobStatus.PREPARED, 70)
                if capture_file_baseline(workspace.dst_path) != expected_baseline:
                    raise PublishBaselineError("DST 在发布前已偏离提交基准")
                self.database.update_job(job_id, JobStatus.PUBLISHING, 90)
                self._safe_operation_event(workspace.root, job_id, "PUBLISHING", file_count=1)

                def finalize_metadata(revision_dir: Path, journal: dict[str, Any]) -> None:
                    try:
                        result_hash = self._committed_result_hash(journal, workspace.dst_path)
                        commit_state["result_hash"] = result_hash
                        self.database.finalize_committed_job(
                            f"change-{operation_id}",
                            workspace_id,
                            operation_id,
                            expected_baseline.sha256,
                            result_hash,
                            revision_dir,
                            current_revision=result_hash,
                        )
                    except Exception as exc:  # noqa: BLE001 - 回调不得让 COMMITTED 进入回滚分支
                        commit_state["error"] = exc
                        try:
                            current = self.database.get_job(job_id) or {}
                            if current.get("status") != JobStatus.SUCCEEDED:
                                self.database.finalize_job_terminal(
                                    job_id,
                                    JobStatus.NEEDS_REVIEW,
                                    "COMMITTED_FINALIZE_FAILED",
                                    str(exc),
                                )
                        except Exception:  # noqa: BLE001, S110 - 启动恢复仍会依据 COMMITTED 日志隔离
                            pass

                self.publisher.publish(
                    operation_id,
                    workspace.root,
                    {workspace.dst_path: staging},
                    expected_baselines={workspace.dst_path: expected_baseline},
                    on_committed=finalize_metadata,
                )
                published = True
        except PublishRolledBackError as exc:
            self.database.finalize_job_terminal(job_id, JobStatus.ROLLED_BACK, exc.code, str(exc))
            return self.database.get_job(job_id) or {}
        except PublishRecoveryError as exc:
            self.database.finalize_job_terminal(job_id, JobStatus.NEEDS_REVIEW, exc.code, str(exc))
            return self.database.get_job(job_id) or {}
        except Exception as exc:  # noqa: BLE001 - 同步写入边界必须持久化终态并释放写锁
            current = self.database.get_job(job_id) or {}
            if current.get("status") == JobStatus.SUCCEEDED:
                return current
            status = JobStatus.NEEDS_REVIEW if published else JobStatus.FAILED
            code = "COMMITTED_FINALIZE_FAILED" if published else getattr(exc, "code", type(exc).__name__.upper())
            self.database.finalize_job_terminal(job_id, status, code, str(exc))
            return self.database.get_job(job_id) or {}
        if commit_state["error"] is not None:
            return self.database.get_job(job_id) or {}
        result_hash = commit_state["result_hash"]
        if not isinstance(result_hash, str):
            self.database.finalize_job_terminal(
                job_id,
                JobStatus.NEEDS_REVIEW,
                "COMMITTED_FINALIZE_MISSING",
            )
            return self.database.get_job(job_id) or {}
        self._write_workspace_metadata_after_commit(workspace, result_hash, cad_version, job_id)
        self._safe_operation_event(workspace.root, job_id, "SUCCEEDED", revision_id=f"change-{operation_id}")
        return self.database.get_job(job_id) or {}

    def run_next_job(self) -> dict[str, Any] | None:
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
            "TEMPLATE_CHANGED": "模板已变化，请重新预览后提交。",
            "CAD_TIMEOUT": "检查 CAD 日志、图纸复杂度和超时设置后重试。",
            "STAGING_DISK_SPACE_INSUFFICIENT": "释放工作区磁盘空间后重试。",
            "HANDLE_LAYOUT_MISMATCH": "检查模板布局名和 Worker 插件版本。",
            "PUBLISH_JOURNAL_REVIEW_REQUIRED": "先核对发布日志并完成恢复，禁止直接重跑。",
        }
        job["suggestion"] = suggestions.get(job["error_code"], "查看逐 DWG 日志和错误详情后决定是否重试。" if job["error_code"] else None)
        return job

    def preview_revision_restore(self, workspace_id: str, revision_id: str) -> dict[str, Any]:
        workspace_row = self.database.get_workspace(workspace_id)
        if workspace_row is None:
            raise ApplicationError("WORKSPACE_NOT_FOUND", "工作区不存在", 404)
        workspace_root = Path(workspace_row.root)
        dst_path = Path(workspace_row.dst_path)
        revision = self.database.get_revision(revision_id)
        if revision is None or revision["workspace_id"] != workspace_id:
            raise ApplicationError("REVISION_NOT_FOUND", "修订不存在", 404)
        manifest_path = Path(revision["revision_dir"]) / "manifest.json"
        if not manifest_path.is_file():
            raise ApplicationError("REVISION_MANIFEST_MISSING", "修订清单缺失", 409)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = []
        conflicts = []
        for entry in manifest["files"]:
            target = Path(entry["target"])
            current_hash = file_sha256(target) if target.exists() else None
            expected_hash = entry.get("result_hash")
            backup_hash = None
            backup_identity = None
            source_conflict = False
            if entry.get("backup"):
                try:
                    backup_baseline = capture_file_baseline(Path(entry["backup"]))
                except (OSError, PublishBaselineError):
                    backup_baseline = None
                if backup_baseline is not None:
                    backup_hash = backup_baseline.sha256
                    backup_identity = list(backup_baseline.identity)
                source_conflict = (
                    backup_hash != entry.get("before_hash")
                    or backup_identity != entry.get("before_identity")
                )
            conflict = current_hash != expected_hash or source_conflict
            action = "replace" if entry.get("backup") else "delete"
            item = {
                "path": str(target.relative_to(workspace_root)),
                "action": action,
                "current_hash": current_hash,
                "expected_hash": expected_hash,
                "restore_hash": entry.get("before_hash"),
                "backup_hash": backup_hash,
                "backup_identity": backup_identity,
                "source_conflict": source_conflict,
                "conflict": conflict,
            }
            files.append(item)
            if conflict:
                conflicts.append(item["path"])
        return {"workspace_id": workspace_id, "revision_id": revision_id, "base_revision_id": file_sha256(dst_path), "files": files, "conflicts": conflicts, "executable": not conflicts}

    def restore_revision(self, workspace_id: str, revision_id: str, base_revision_id: str) -> dict[str, Any]:
        preview = self.preview_revision_restore(workspace_id, revision_id)
        if preview["base_revision_id"] != base_revision_id or not preview["executable"]:
            raise ApplicationError("REVISION_RESTORE_CONFLICT", "当前文件已变化，请重新预览恢复", 409)
        workspace = self.get_workspace(workspace_id)
        revision = self.database.get_revision(revision_id)
        manifest = json.loads((Path(revision["revision_dir"]) / "manifest.json").read_text(encoding="utf-8"))
        job_id = str(uuid.uuid4())
        try:
            self.database.create_job(job_id, workspace_id, "revision_restore", JobStatus.STAGING, {"base_revision_id": base_revision_id, "source_revision_id": revision_id})
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc
        staging_dir = workspace.root / ".dst-manager" / "jobs" / job_id / "staging"
        published = False
        commit_state: dict[str, Any] = {"result_hash": None, "error": None}
        try:
            targets = [Path(entry["target"]).resolve() for entry in manifest["files"]]
            backup_paths = [Path(entry["backup"]).resolve() for entry in manifest["files"] if entry.get("backup")]
            preview_hashes = {
                (workspace.root / item["path"]).resolve(): item["current_hash"]
                for item in preview["files"]
            }
            with WindowsResultGuards(backup_paths), WindowsWriteLocks([target for target in targets if target.exists()]):
                try:
                    expected_baselines = {
                        target: capture_file_baseline(target)
                        for target in targets
                    }
                except OSError as exc:
                    raise ApplicationError("REVISION_RESTORE_CONFLICT", "捕获恢复基准时文件发生变化", 409) from exc
                if {
                    target: baseline.sha256 if baseline is not None else None
                    for target, baseline in expected_baselines.items()
                } != preview_hashes:
                    raise ApplicationError("REVISION_RESTORE_CONFLICT", "恢复目标已偏离预览", 409)
                source_baselines = {}
                for entry, item in zip(manifest["files"], preview["files"], strict=True):
                    if not entry.get("backup"):
                        continue
                    source = Path(entry["backup"]).resolve()
                    baseline = capture_file_baseline(source)
                    if (
                        baseline is None
                        or baseline.sha256 != item["backup_hash"]
                        or list(baseline.identity) != item["backup_identity"]
                    ):
                        raise ApplicationError("REVISION_RESTORE_SOURCE_CHANGED", "永久恢复源已偏离预览", 409)
                    source_baselines[source] = baseline
                staging_dir.mkdir(parents=True, exist_ok=True)
                staged: dict[Path, Path | None] = {}
                for index, entry in enumerate(manifest["files"]):
                    target = Path(entry["target"]).resolve()
                    if entry.get("backup"):
                        source = Path(entry["backup"])
                        staged_copy = staging_dir / f"{index:03d}-{target.name}"
                        shutil.copy2(source, staged_copy)
                        if (
                            file_sha256(staged_copy) != entry["before_hash"]
                            or capture_file_baseline(source.resolve()) != source_baselines[source.resolve()]
                        ):
                            raise ApplicationError("REVISION_RESTORE_SOURCE_CHANGED", "永久恢复源在复制期间变化", 409)
                        staged[target] = staged_copy
                    else:
                        staged[target] = None
                self.database.update_job(job_id, JobStatus.PREPARED, 70)
                workspace_baseline = expected_baselines.get(workspace.dst_path.resolve())
                if workspace_baseline is None:
                    raise ApplicationError("REVISION_RESTORE_CONFLICT", "当前 DST 缺失", 409)
                before_hash = workspace_baseline.sha256
                self.database.update_job(job_id, JobStatus.PUBLISHING, 90)

                def finalize_restore(revision_dir: Path, journal: dict[str, Any]) -> None:
                    try:
                        result_hash = self._committed_result_hash(journal, workspace.dst_path)
                        commit_state["result_hash"] = result_hash
                        self.database.finalize_committed_job(
                            f"restore-{job_id}",
                            workspace_id,
                            job_id,
                            before_hash,
                            result_hash,
                            revision_dir,
                            current_revision=result_hash,
                        )
                    except Exception as exc:  # noqa: BLE001 - 回调不得让 COMMITTED 进入回滚分支
                        commit_state["error"] = exc
                        try:
                            current = self.database.get_job(job_id) or {}
                            if current.get("status") != JobStatus.SUCCEEDED:
                                self.database.finalize_job_terminal(
                                    job_id,
                                    JobStatus.NEEDS_REVIEW,
                                    "COMMITTED_FINALIZE_FAILED",
                                    str(exc),
                                )
                        except Exception:  # noqa: BLE001, S110 - 启动恢复仍会依据 COMMITTED 日志隔离
                            pass

                self.publisher.publish(
                    job_id,
                    workspace.root,
                    staged,
                    expected_baselines=expected_baselines,
                    on_committed=finalize_restore,
                )
                published = True
                record_id = f"restore-{job_id}"
        except PublishRolledBackError as exc:
            self.database.finalize_job_terminal(job_id, JobStatus.ROLLED_BACK, exc.code, str(exc))
            return self.database.get_job(job_id) or {}
        except PublishRecoveryError as exc:
            self.database.finalize_job_terminal(job_id, JobStatus.NEEDS_REVIEW, exc.code, str(exc))
            return self.database.get_job(job_id) or {}
        except Exception as exc:  # noqa: BLE001 - 恢复边界必须释放普通写锁
            current = self.database.get_job(job_id) or {}
            if current.get("status") != JobStatus.SUCCEEDED:
                status = JobStatus.NEEDS_REVIEW if published else JobStatus.FAILED
                code = "COMMITTED_FINALIZE_FAILED" if published else getattr(
                    exc,
                    "code",
                    "REVISION_RESTORE_STAGING_FAILED",
                )
                self.database.finalize_job_terminal(job_id, status, code, str(exc))
            return self.database.get_job(job_id) or {}
        if commit_state["error"] is not None:
            return self.database.get_job(job_id) or {}
        result_hash = commit_state["result_hash"]
        if not isinstance(result_hash, str):
            self.database.finalize_job_terminal(job_id, JobStatus.NEEDS_REVIEW, "COMMITTED_FINALIZE_MISSING")
            return self.database.get_job(job_id) or {}
        workspace_row = self.database.get_workspace(workspace_id)
        self._write_workspace_metadata_after_commit(
            workspace,
            result_hash,
            workspace_row.default_cad_version if workspace_row else "2020",
            job_id,
        )
        self._safe_operation_event(
            workspace.root,
            job_id,
            "REVISION_RESTORED",
            source_revision_id=revision_id,
            revision_id=record_id,
        )
        return self.database.get_job(job_id) or {}

    def preview_xml(
        self,
        workspace_id: str,
        base_revision_id: str,
        xml: bytes,
        destination: Path | None = None,
    ) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        imported = AcsmDocument(xml).project(workspace.root)
        before_sheets = {sheet.acsm_id: sheet for sheet in workspace.document.sheets}
        after_sheets = {sheet.acsm_id: sheet for sheet in imported.sheets}
        changes: list[dict[str, Any]] = []
        for sheet_id in sorted(before_sheets.keys() - after_sheets.keys()):
            changes.append({"type": "sheet_removed", "sheet_id": sheet_id, "before": {"number": before_sheets[sheet_id].number, "title": before_sheets[sheet_id].title}})
        for sheet_id in sorted(after_sheets.keys() - before_sheets.keys()):
            changes.append({"type": "sheet_added", "sheet_id": sheet_id, "after": {"number": after_sheets[sheet_id].number, "title": after_sheets[sheet_id].title}})
        for sheet_id in sorted(before_sheets.keys() & after_sheets.keys()):
            before, after = before_sheets[sheet_id], after_sheets[sheet_id]
            fields = {}
            for name in ("number", "title", "custom_properties"):
                if getattr(before, name) != getattr(after, name):
                    fields[name] = {"before": getattr(before, name), "after": getattr(after, name)}
            if (before.layout.file_name, before.layout.layout_name, before.layout.handle) != (after.layout.file_name, after.layout.layout_name, after.layout.handle):
                fields["layout"] = {"before": asdict(before.layout), "after": asdict(after.layout)}
            if fields:
                changes.append({"type": "sheet_changed", "sheet_id": sheet_id, "fields": fields})
        destination_revision_id = None
        if destination is not None:
            destination = destination.expanduser().resolve()
            if workspace.root != destination.parent and workspace.root not in destination.parents:
                raise ApplicationError("DESTINATION_OUTSIDE_WORKSPACE", "导出位置必须在工作区内")
            destination_revision_id = file_sha256(destination) if destination.is_file() else "MISSING"
        return {
            "sheet_count_before": len(workspace.document.sheets),
            "sheet_count_after": len(imported.sheets),
            "subset_count_before": len(workspace.document.subsets),
            "subset_count_after": len(imported.subsets),
            "changes": changes,
            "diagnostics": [asdict(issue) for issue in imported.diagnostics],
            "destination_revision_id": destination_revision_id,
        }

    def export_xml_to_dst(
        self,
        workspace_id: str,
        base_revision_id: str,
        xml: bytes,
        destination: Path,
        destination_revision_id: str | None = None,
    ) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        document = AcsmDocument(xml)
        errors = [issue for issue in document.validate() if issue.severity == Severity.ERROR]
        if errors:
            raise ApplicationError("XML_VALIDATION_FAILED", f"XML存在{len(errors)}个阻断问题")
        destination = destination.expanduser().resolve()
        if workspace.root != destination.parent and workspace.root not in destination.parents:
            raise ApplicationError("DESTINATION_OUTSIDE_WORKSPACE", "导出位置必须在工作区内")
        is_main = destination == workspace.dst_path
        if not is_main and destination_revision_id is None:
            raise ApplicationError("DESTINATION_BASELINE_REQUIRED", "非主 DST 导出必须先预览目标基准", 409)
        frozen_destination_revision = base_revision_id if is_main else destination_revision_id
        job_id = str(uuid.uuid4())
        try:
            self.database.create_job(
                job_id,
                workspace_id,
                "xml_export",
                JobStatus.STAGING,
                {
                    "base_revision_id": base_revision_id,
                    "destination": str(destination),
                    "destination_revision_id": frozen_destination_revision,
                },
            )
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc
        job_dir = workspace.root / ".dst-manager" / "jobs" / job_id
        input_path, staged = job_dir / "input" / "imported.xml", job_dir / "staging" / destination.name
        published = False
        commit_state: dict[str, Any] = {"result_hash": None, "revision_dir": None, "error": None}
        try:
            with WindowsWriteLocks([destination] if destination.exists() else []):
                expected_baseline = capture_file_baseline(destination)
                actual_destination_revision = expected_baseline.sha256 if expected_baseline is not None else "MISSING"
                if actual_destination_revision != frozen_destination_revision:
                    raise PublishBaselineError("XML 导出目标已偏离预览基准")
                before_hash = expected_baseline.sha256 if expected_baseline is not None else base_revision_id
                input_path.parent.mkdir(parents=True, exist_ok=True)
                staged.parent.mkdir(parents=True, exist_ok=True)
                input_path.write_bytes(xml)
                self._safe_operation_event(workspace.root, job_id, "STAGING", job_type="xml_export")
                self.codec.encode_file(document.to_bytes(), staged)
                roundtrip = AcsmDocument(self.codec.decode_file(staged))
                if roundtrip.semantic_bytes() != document.semantic_bytes():
                    raise ValueError("DST_ROUNDTRIP_MISMATCH")
                self.database.update_job(job_id, JobStatus.PREPARED, 70)
                self.database.update_job(job_id, JobStatus.PUBLISHING, 90)
                self._safe_operation_event(workspace.root, job_id, "PUBLISHING", file_count=1)

                def finalize_xml(revision_dir: Path, journal: dict[str, Any]) -> None:
                    try:
                        result_hash = self._committed_result_hash(journal, destination)
                        commit_state["result_hash"] = result_hash
                        commit_state["revision_dir"] = revision_dir
                        self.database.finalize_committed_job(
                            f"xml-{job_id}",
                            workspace_id,
                            job_id,
                            before_hash,
                            result_hash,
                            revision_dir,
                            update_current=is_main,
                            current_revision=result_hash if is_main else None,
                        )
                    except Exception as exc:  # noqa: BLE001 - 回调不得让 COMMITTED 进入回滚分支
                        commit_state["error"] = exc
                        try:
                            current = self.database.get_job(job_id) or {}
                            if current.get("status") != JobStatus.SUCCEEDED:
                                self.database.finalize_job_terminal(
                                    job_id,
                                    JobStatus.NEEDS_REVIEW,
                                    "COMMITTED_FINALIZE_FAILED",
                                    str(exc),
                                )
                        except Exception:  # noqa: BLE001, S110 - 启动恢复仍会依据 COMMITTED 日志隔离
                            pass

                self.publisher.publish(
                    job_id,
                    workspace.root,
                    {destination: staged},
                    expected_baselines={destination: expected_baseline},
                    on_committed=finalize_xml,
                )
                published = True
        except PublishRolledBackError:
            self.database.finalize_job_terminal(job_id, JobStatus.ROLLED_BACK, "PUBLISH_ROLLED_BACK")
            return self.database.get_job(job_id) or {}
        except PublishRecoveryError as exc:
            self.database.finalize_job_terminal(job_id, JobStatus.NEEDS_REVIEW, exc.code, str(exc))
            return self.database.get_job(job_id) or {}
        except Exception as exc:  # noqa: BLE001 - XML 发布边界必须持久化终态并释放锁
            current = self.database.get_job(job_id) or {}
            if current.get("status") != JobStatus.SUCCEEDED:
                status = JobStatus.NEEDS_REVIEW if published else JobStatus.FAILED
                code = "COMMITTED_FINALIZE_FAILED" if published else getattr(exc, "code", type(exc).__name__.upper())
                self.database.finalize_job_terminal(job_id, status, code, str(exc))
            return self.database.get_job(job_id) or {}
        if commit_state["error"] is not None:
            return self.database.get_job(job_id) or {}
        result_hash = commit_state["result_hash"]
        revision_dir = commit_state["revision_dir"]
        revision_id = f"xml-{job_id}"
        if not isinstance(result_hash, str) or not isinstance(revision_dir, Path):
            self.database.finalize_job_terminal(job_id, JobStatus.NEEDS_REVIEW, "COMMITTED_FINALIZE_MISSING")
            return self.database.get_job(job_id) or {}
        revision_input = revision_dir / "input"
        try:
            revision_input.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, revision_input / "imported.xml")
        except OSError as exc:
            self._safe_operation_event(workspace.root, job_id, "POST_COMMIT_ARCHIVE_FAILED", error=repr(exc))
        if is_main:
            self._write_workspace_metadata_after_commit(workspace, result_hash, "2020", job_id)
        self._safe_operation_event(workspace.root, job_id, "SUCCEEDED", revision_id=revision_id)
        try:
            shutil.copytree(job_dir / "logs", revision_dir / "logs", dirs_exist_ok=True)
        except OSError:
            pass
        return self.database.get_job(job_id) or {}

    def capabilities(self) -> dict[str, dict[str, Any]]:
        capabilities = {version: self._capability(version) for version in ("2016", "2020")}
        return {version: {"version": version, "available": item.available, "console": str(item.console) if item.console else None, "plugin": str(item.plugin) if item.plugin else None} for version, item in capabilities.items()}

    def inspect_template(self, template: Path, cad_version: str) -> dict[str, Any]:
        template = template.expanduser().resolve()
        if template.suffix.lower() not in {".dwg", ".dwt"} or not template.is_file():
            raise ApplicationError("TEMPLATE_NOT_FOUND", f"模板不存在：{template}", 404)
        capability = self._capability(cad_version)
        if not capability.available:
            raise ApplicationError("CAD_CAPABILITY_UNAVAILABLE", f"AutoCAD {cad_version}未配置")
        source_hash = file_sha256(template)
        with tempfile.TemporaryDirectory(prefix="dst-manager-template-") as temp:
            temp_dir = Path(temp)
            drawing = temp_dir / (template.stem + ".dwg")
            import shutil
            shutil.copy2(template, drawing)
            script = temp_dir / "inspect.scr"
            script.write_text(ScriptRenderer().render_handles(capability.plugin), encoding="mbcs")
            CoreConsoleExecutor().run(capability, drawing, script, self.settings.cad_timeout_seconds)
            handles = parse_handles(drawing.with_suffix(".dst-handles.txt").read_text(encoding="utf-8"))
        if file_sha256(template) != source_hash:
            raise ApplicationError("TEMPLATE_CHANGED", "模板在检查期间发生变化")
        return {"path": str(template), "sha256": source_hash, "cad_version": cad_version, "layouts": [{"name": name, "handle": handle} for name, handle in handles.items()]}

    def _capability(self, version: str) -> CadCapability:
        if version == "2016":
            return CadCapability(version, self.settings.autocad_2016_console, self.settings.autocad_2016_plugin)
        if version == "2020":
            return CadCapability(version, self.settings.autocad_2020_console, self.settings.autocad_2020_plugin)
        raise ApplicationError("CAD_VERSION_INVALID", f"不支持的AutoCAD版本：{version}")

    def _check_revision(self, workspace: Workspace, base_revision_id: str) -> None:
        if workspace.revision_id != base_revision_id:
            raise ApplicationError("REVISION_CONFLICT", "基准修订已变化，请重新预览", 409)

    def _inspect_structural_sources(
        self,
        workspace: Workspace,
        execution_intent: dict[str, Any],
        cad_version: str,
    ) -> list[dict[str, Any]]:
        """在任务入队前解析、检查并固化全部布局来源证据。"""
        def diagnostic(code: str, message: str) -> dict[str, Any]:
            return {"code": code, "severity": "error", "message": message}

        row = self.database.get_workspace(workspace.id)
        allowed_roots = [workspace.root.resolve()]
        if row is not None and row.root_override:
            allowed_roots.append(Path(row.root_override).expanduser().resolve())
        sources: dict[str, dict[str, Any]] = {}

        def register(raw_path: str, source_type: str, requested_layout: str | None = None) -> Path:
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = workspace.root / candidate
            resolved = candidate.resolve()
            key = str(resolved).casefold()
            item = sources.setdefault(
                key,
                {"path": resolved, "types": set(), "requested_layouts": set()},
            )
            item["types"].add(source_type)
            if requested_layout:
                item["requested_layouts"].add(requested_layout)
            return resolved

        try:
            for group in execution_intent.get("groups", []):
                snapshot_type = "template_layout" if group.get("operation") == "create" else "existing_snapshot"
                snapshot = register(group["source_snapshot"], snapshot_type)
                group["source_snapshot"] = str(snapshot)
                for layout in group.get("layouts", []):
                    source = register(layout["source_file"], layout["source_type"], layout["source_layout"])
                    layout["source_file"] = str(source)
        except (OSError, RuntimeError, ValueError) as exc:
            return [diagnostic("LAYOUT_SOURCE_OUTSIDE_WORKSPACE", f"布局来源路径无效：{exc}")]

        for item in sorted(sources.values(), key=lambda source: str(source["path"]).casefold()):
            path = item["path"]
            if (
                "existing_snapshot" in item["types"]
                and not any(path == root or path.is_relative_to(root) for root in allowed_roots)
            ):
                return [diagnostic("LAYOUT_SOURCE_OUTSIDE_WORKSPACE", f"布局来源越出工作区：{path}")]
            allowed_extensions = {".dwg", ".dwt"}
            if "existing_snapshot" in item["types"]:
                allowed_extensions = {".dwg"}
            if path.suffix.lower() not in allowed_extensions:
                return [diagnostic("LAYOUT_SOURCE_EXTENSION_INVALID", f"布局来源扩展名无效：{path}")]
            if not path.is_file():
                return [diagnostic("LAYOUT_SOURCE_NOT_FOUND", f"布局来源不存在：{path}")]
            try:
                with path.open("rb") as stream:
                    stream.read(1)
            except OSError:
                return [diagnostic("LAYOUT_SOURCE_UNREADABLE", f"布局来源不可读：{path}")]

        ordered_sources = sorted(sources.values(), key=lambda source: str(source["path"]).casefold())
        snapshots: dict[Path, tuple[Path, Any]] = {}
        try:
            with tempfile.TemporaryDirectory(prefix="dst-manager-preview-") as temporary_directory:
                snapshot_root = Path(temporary_directory)
                with WindowsWriteLocks([item["path"] for item in ordered_sources]):
                    for index, item in enumerate(ordered_sources):
                        path = item["path"]
                        baseline = capture_file_baseline(path)
                        if baseline is None:
                            return [diagnostic("LAYOUT_SOURCE_NOT_FOUND", f"布局来源不存在：{path}")]
                        snapshot = snapshot_root / f"{index:03d}-{path.name}"
                        shutil.copy2(path, snapshot)
                        if file_sha256(snapshot) != baseline.sha256 or capture_file_baseline(path) != baseline:
                            snapshot.unlink(missing_ok=True)
                            return [diagnostic("BASE_FILE_CHANGED", f"布局来源在快照期间发生变化：{path}")]
                        snapshots[path] = (snapshot, baseline)

                inspections: list[dict[str, Any]] = []
                for item in ordered_sources:
                    path = item["path"]
                    snapshot, baseline = snapshots[path]
                    try:
                        inspected = self.inspect_template(snapshot, cad_version)
                    except ApplicationError as exc:
                        if exc.code == "CAD_CAPABILITY_UNAVAILABLE":
                            return [diagnostic(exc.code, str(exc))]
                        return [diagnostic("LAYOUT_SOURCE_INSPECTION_FAILED", f"布局来源检查失败：{path}；{exc}")]
                    except Exception as exc:  # noqa: BLE001 - CAD 检查边界统一转换为阻断诊断
                        return [diagnostic("LAYOUT_SOURCE_INSPECTION_FAILED", f"布局来源检查失败：{path}；{exc}")]
                    raw_layouts = inspected.get("layouts") if isinstance(inspected, dict) else None
                    if not isinstance(raw_layouts, list):
                        return [diagnostic("LAYOUT_SOURCE_INSPECTION_FAILED", f"布局来源检查结果无效：{path}")]
                    layout_names = [
                        str(layout["name"] if isinstance(layout, dict) else layout)
                        for layout in raw_layouts
                    ]
                    requested = sorted(item["requested_layouts"], key=str.casefold)
                    for requested_name in requested:
                        matches = [name for name in layout_names if name.casefold() == requested_name.casefold()]
                        if not matches:
                            return [diagnostic("SOURCE_LAYOUT_NOT_FOUND", f"来源布局不存在：{path} / {requested_name}")]
                        if len(matches) > 1:
                            return [diagnostic("SOURCE_LAYOUT_AMBIGUOUS", f"来源布局大小写歧义：{path} / {requested_name}")]
                    inspected_path = Path(str(inspected.get("path", snapshot))).resolve()
                    if (
                        inspected_path != snapshot.resolve()
                        or inspected.get("cad_version") != cad_version
                        or inspected.get("sha256") != baseline.sha256
                    ):
                        return [diagnostic("LAYOUT_SOURCE_INSPECTION_FAILED", f"布局来源检查证据不匹配：{path}")]
                    inspections.append(
                        {
                            "path": str(path),
                            "sha256": baseline.sha256,
                            "identity": list(baseline.identity),
                            "cad_version": cad_version,
                            "layouts": sorted(layout_names, key=str.casefold),
                            "requested_layouts": requested,
                        },
                    )
        except FileLockError as exc:
            return [diagnostic("BLOCKED_FILE_LOCK", f"布局来源被占用：{exc}")]
        except OSError as exc:
            return [diagnostic("LAYOUT_SOURCE_UNREADABLE", f"布局来源无法读取：{exc}")]
        execution_intent["source_inspections"] = inspections
        return []

    @classmethod
    def _build_semantic_diff(
        cls,
        workspace: Workspace,
        commands: list[dict[str, Any]],
        execution_intent: dict[str, Any] | None,
    ) -> dict[str, Any]:
        before = cls._summarize_current_structure(workspace)
        after = (
            cls._summarize_derived_structure(execution_intent["derived_document"])
            if execution_intent is not None
            else before
        )
        return {
            "structure": {"before": before, "after": after},
            "properties": cls._summarize_property_changes(workspace, commands),
            "dwgs": cls._summarize_dwg_changes(workspace, execution_intent),
        }

    @classmethod
    def _summarize_current_structure(cls, workspace: Workspace) -> list[dict[str, Any]]:
        result = []
        for subset_position, subset in enumerate(sorted(workspace.document.subsets, key=lambda item: item.order), 1):
            sheets = []
            for sheet_position, sheet in enumerate(subset.sheets, 1):
                drawing = sheet.layout.resolved_path or sheet.layout.file_name
                sheets.append(cls._sheet_summary(sheet_position, sheet.acsm_id, sheet.number, sheet.title, str(drawing or ""), sheet.layout.layout_name))
            number_range = ""
            if sheets:
                number_range = sheets[0]["number"] if len(sheets) == 1 else f"{sheets[0]['number']}-{sheets[-1]['number']}"
            title = subset.name
            if number_range and subset.name.startswith(f"{number_range} "):
                title = subset.name[len(number_range) + 1:]
            result.append(
                {
                    "position": subset_position,
                    "id": subset.acsm_id,
                    "title": title,
                    "number_range": number_range,
                    "display_name": subset.name,
                    "dwg_file": sheets[0]["dwg_file"] if sheets else "",
                    "sheets": sheets,
                },
            )
        return result

    @classmethod
    def _summarize_derived_structure(cls, document: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for subset_position, subset in enumerate(document.get("subsets", []), 1):
            drawing = str(subset.get("target_file", ""))
            sheets = [
                cls._sheet_summary(
                    sheet_position,
                    sheet["acsm_id"],
                    sheet["number"],
                    sheet["title"],
                    drawing,
                    sheet["layout"]["layout_name"],
                )
                for sheet_position, sheet in enumerate(subset.get("sheets", []), 1)
            ]
            result.append(
                {
                    "position": subset_position,
                    "id": subset["acsm_id"],
                    "title": subset["title"],
                    "number_range": subset["number_range"],
                    "display_name": subset["display_name"],
                    "dwg_file": drawing,
                    "sheets": sheets,
                },
            )
        return result

    @staticmethod
    def _sheet_summary(position: int, sheet_id: str, number: str, title: str, drawing: str, layout: str) -> dict[str, Any]:
        suffix_match = re.search(r"\s+\(([^()]*)\)$", title)
        return {
            "position": position,
            "id": sheet_id,
            "number": number,
            "title": title,
            "suffix": suffix_match.group(1) if suffix_match else "",
            "dwg_file": drawing,
            "layout_name": layout,
        }

    @staticmethod
    def _summarize_property_changes(workspace: Workspace, commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            definitions = {
                (definition.type, definition.name.casefold()): definition
                for definition in property_definitions_from_document(workspace.document)
            }
        except AcsmValidationError:
            definitions = {}
        sheet_by_id = {sheet.acsm_id: sheet for sheet in workspace.document.sheets}
        result = []
        for command in commands:
            command_type = command["type"]
            if command_type in {"add_custom_property", "delete_custom_property"}:
                property_type = command["property_type"]
                name = command["name"]
                previous = definitions.get((property_type, name.casefold()))
                after = None
                if command_type == "add_custom_property":
                    after = {
                        "type": property_type,
                        "name": name,
                        "default_value": command.get("default_value", ""),
                    }
                result.append(
                    {
                        "action": "add" if command_type == "add_custom_property" else "delete",
                        "type": property_type,
                        "name": name,
                        "before": asdict(previous) if previous is not None else None,
                        "after": after,
                        "affected_sheet_count": len(workspace.document.sheets) if property_type == "sheet" else 0,
                    },
                )
            elif command_type == "update_sheet":
                sheet = sheet_by_id.get(command.get("sheet_id"))
                for name, value in command.get("custom_properties", {}).items():
                    result.append(
                        {
                            "action": "update",
                            "type": "sheet",
                            "name": name,
                            "before": sheet.custom_properties.get(name) if sheet else None,
                            "after": value,
                            "affected_sheet_count": 1 if sheet else 0,
                        },
                    )
            elif command_type == "update_sheet_set":
                for name, value in command.get("custom_properties", {}).items():
                    result.append(
                        {
                            "action": "update",
                            "type": "sheetset",
                            "name": name,
                            "before": workspace.document.custom_properties.get(name),
                            "after": value,
                            "affected_sheet_count": 0,
                        },
                    )
        return result

    @classmethod
    def _summarize_dwg_changes(cls, workspace: Workspace, execution_intent: dict[str, Any] | None) -> list[dict[str, Any]]:
        if execution_intent is None:
            return []
        before_by_id = {item["id"]: item for item in cls._summarize_current_structure(workspace)}
        after_by_id = {item["id"]: item for item in cls._summarize_derived_structure(execution_intent["derived_document"])}
        result = []
        for group in execution_intent.get("groups", []):
            subset_id = group["subset_id"]
            before = before_by_id.get(subset_id)
            after = after_by_id.get(subset_id)
            result.append(
                {
                    "action": group["operation"],
                    "subset_id": subset_id,
                    "before": None if before is None else {"file": before["dwg_file"], "layouts": [sheet["layout_name"] for sheet in before["sheets"]]},
                    "after": None if after is None else {"file": after["dwg_file"], "layouts": [sheet["layout_name"] for sheet in after["sheets"]]},
                },
            )
        for deleted in execution_intent.get("deleted_subsets", []):
            subset_id = deleted["subset_id"]
            before = before_by_id.get(subset_id)
            result.append(
                {
                    "action": "delete",
                    "subset_id": subset_id,
                    "before": {"file": deleted["target_file"], "layouts": [sheet["layout_name"] for sheet in before["sheets"]]} if before else {"file": deleted["target_file"], "layouts": []},
                    "after": None,
                },
            )
        return result

    @staticmethod
    def _preview_digest(
        base_revision_id: str,
        cad_version: str,
        commands: list[dict[str, Any]],
        execution_intent: dict[str, Any] | None,
        semantic_diff: dict[str, Any],
    ) -> str:
        payload = {
            "base_revision_id": base_revision_id,
            "cad_version": cad_version,
            "commands": commands,
            "execution_intent": execution_intent,
            "semantic_diff": semantic_diff,
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _attach_expected_file_hashes(workspace: Workspace, execution_intent: dict[str, Any]) -> None:
        paths = {
            workspace.dst_path.resolve(),
            *(Path(path).resolve() for path in execution_intent.get("path_graph", {}).get("old_sources", [])),
            *(Path(path).resolve() for path in execution_intent.get("path_graph", {}).get("final_targets", [])),
        }
        for group in execution_intent.get("groups", []):
            paths.add(Path(group["source_snapshot"]).resolve())
            paths.update(Path(layout["source_file"]).resolve() for layout in group.get("layouts", []))
        inspected_sources = {
            Path(inspection["path"]).resolve(): inspection
            for inspection in execution_intent.get("source_inspections", [])
        }
        expected = {
            str(path): (
                inspected_sources[path]["sha256"]
                if path in inspected_sources
                else file_sha256(path) if path.is_file() else None
            )
            for path in sorted(paths, key=lambda item: str(item).casefold())
        }
        execution_intent["expected_file_hashes"] = expected
        execution_intent["expected_file_identities"] = {
            str(path): inspected_sources[path]["identity"]
            for path in sorted(inspected_sources, key=lambda item: str(item).casefold())
        }

    def _require_committed_operation(self, workspace_root: Path, operation_id: str) -> dict[str, Any]:
        journal = self.publisher.read_committed_operation(workspace_root, operation_id)
        if journal is None:
            raise PublishRecoveryError(f"COMMITTED_JOURNAL_MISSING: {operation_id}")
        return journal

    @staticmethod
    def _committed_result_hash(journal: dict[str, Any], target: Path) -> str:
        target_key = str(target.resolve()).casefold()
        for entry in journal["files"]:
            if str(Path(entry["target"]).resolve()).casefold() == target_key:
                result_hash = entry.get("result_hash")
                if isinstance(result_hash, str):
                    return result_hash
                break
        raise PublishRecoveryError(f"COMMITTED_RESULT_MISSING: {target}")

    def _recover_committed_job(self, workspace_root: Path, journal: dict[str, Any]) -> None:
        operation_id = journal["operation_id"]
        job = self.database.get_job(operation_id)
        if job is None or job["status"] == JobStatus.SUCCEEDED:
            return
        try:
            if journal.get("identity_version") != 1:
                raise PublishRecoveryError("COMMITTED_IDENTITY_VERSION_UNSUPPORTED")
            existing_results = [
                Path(entry["target"])
                for entry in journal["files"]
                if entry.get("result_hash") is not None
            ]
            missing_results = [
                Path(entry["target"])
                for entry in journal["files"]
                if entry.get("result_hash") is None
            ]
            with WindowsResultGuards(existing_results, missing_results) as result_guard:
                self._validate_recovered_committed_results(journal, result_guard)
                workspace = self.database.get_workspace(job["workspace_id"])
                if workspace is None:
                    raise PublishRecoveryError("COMMITTED_WORKSPACE_MISSING")
                payload = job["payload"]
                target = Path(payload["destination"]) if job["type"] == "xml_export" else Path(workspace.dst_path)
                result_hash = self._committed_result_hash(journal, target)
                entry = next(
                    item
                    for item in journal["files"]
                    if str(Path(item["target"]).resolve()).casefold() == str(target.resolve()).casefold()
                )
                before_hash = entry.get("before_hash") or payload["base_revision_id"]
                update_current = job["type"] != "xml_export" or target.resolve() == Path(workspace.dst_path).resolve()
                if job["type"] == "revision_restore":
                    revision_id = f"restore-{operation_id}"
                elif job["type"] == "xml_export":
                    revision_id = f"xml-{operation_id}"
                else:
                    revision_id = f"change-{operation_id}"
                revision_dir = workspace_root / ".dst-manager" / "revisions" / operation_id
                self.database.finalize_committed_job(
                    revision_id,
                    job["workspace_id"],
                    operation_id,
                    before_hash,
                    result_hash,
                    revision_dir,
                    update_current=update_current,
                    current_revision=result_hash if update_current else None,
                )
        except Exception as exc:  # noqa: BLE001 - 无法证明 COMMITTED 一致性时必须隔离
            self.database.finalize_job_terminal(
                operation_id,
                JobStatus.NEEDS_REVIEW,
                "COMMITTED_RECOVERY_UNPROVEN",
                str(exc),
            )

    def _quarantine_unproven_publish_jobs(self, workspace_root: Path, error: PublishRecoveryError) -> None:
        """发布清单不可证明时，只按受控任务目录隔离，绝不读取它来完成事务。"""
        jobs_root = workspace_root.resolve() / ".dst-manager" / "jobs"
        if not jobs_root.is_dir():
            return
        error_code = str(error) or error.code
        for journal_path in jobs_root.glob("*/publish-journal.json"):
            operation_id = journal_path.parent.name
            if not operation_id or journal_path.parent.parent != jobs_root:
                continue
            job = self.database.get_job(operation_id)
            if job is None or job["status"] == JobStatus.SUCCEEDED:
                continue
            try:
                self.database.finalize_job_terminal(
                    operation_id,
                    JobStatus.NEEDS_REVIEW,
                    error_code,
                    str(error),
                )
            except KeyError:
                continue

    @staticmethod
    def _validate_recovered_committed_results(
        journal: dict[str, Any],
        result_guard: WindowsResultGuards,
    ) -> None:
        for entry in journal["files"]:
            target = Path(entry["target"])
            result_hash = entry.get("result_hash")
            if result_hash is None:
                if not result_guard.protects_missing(target):
                    raise PublishRecoveryError(f"COMMITTED_RESULT_CHANGED: {target}")
                continue
            baseline = capture_file_baseline(target)
            expected_identity = entry.get("result_identity")
            if (
                baseline is None
                or baseline.sha256 != result_hash
                or expected_identity is None
                or tuple(expected_identity) != baseline.identity
            ):
                raise PublishRecoveryError(f"COMMITTED_RESULT_CHANGED: {target}")

    @staticmethod
    def _safe_operation_event(root: Path, operation_id: str, event: str, **details: Any) -> None:
        try:
            append_operation_event(root, operation_id, event, **details)
        except Exception:  # noqa: BLE001, S110 - 提交后诊断失败不得改变已提交状态
            pass

    @staticmethod
    def _write_workspace_metadata_after_commit(
        workspace: Workspace,
        revision_id: str,
        cad_version: str,
        operation_id: str,
    ) -> None:
        try:
            write_workspace_metadata(
                workspace.root,
                workspace.id,
                workspace.dst_path,
                revision_id,
                cad_version,
            )
        except Exception as exc:  # noqa: BLE001 - DB 已闭环，元数据仅作为可重试诊断
            DstManagerService._safe_operation_event(
                workspace.root,
                operation_id,
                "POST_COMMIT_METADATA_FAILED",
                error=repr(exc),
            )

    @staticmethod
    def _normalize_commands(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {
            "update_sheet_set",
            "update_subset_title",
            "update_sheet_properties",
            "delete_sheet",
            "insert_sheet",
            "insert_subset",
            "add_custom_property",
            "delete_custom_property",
        }
        invalid = [command.get("type") for command in commands if command.get("type") not in allowed]
        if invalid:
            raise ApplicationError("COMMAND_UNSUPPORTED", f"不支持的命令：{invalid}")
        normalized: list[dict[str, Any]] = []
        for command in commands:
            item = dict(command)
            if item["type"] == "update_subset_title":
                item["type"] = "update_subset"
            elif item["type"] == "update_sheet_properties":
                if {"number", "title"} & item.keys():
                    raise ApplicationError("COMMAND_UNSUPPORTED", "不支持直接更新图号或图纸标题")
                item["type"] = "update_sheet"
            normalized.append(item)
        return normalized

    @staticmethod
    def _apply_nonstructural_commands(
        document: AcsmDocument,
        commands: list[dict[str, Any]],
        structural: bool,
    ) -> None:
        structural_types = {"update_subset", "delete_sheet", "insert_sheet", "insert_subset"}
        for command in commands:
            if command["type"] in {"add_custom_property", "delete_custom_property"}:
                document.apply_property_definition_commands([command])
            elif not structural or command["type"] not in structural_types:
                document.apply_metadata_commands([command])

    @staticmethod
    def _issue(code: str, severity: str, message: str):
        from dst_manager.domain.models import ValidationIssue
        return ValidationIssue(code, Severity(severity), message)

    @staticmethod
    def _write_workspace_file(workspace: Workspace) -> None:
        write_workspace_metadata(workspace.root, workspace.id, workspace.dst_path, workspace.revision_id, "2020")
