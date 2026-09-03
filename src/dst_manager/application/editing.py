"""受控编辑域（v0.3.2 Task 0 自 service.py 拆分）。

`EditingOperations` 以 mixin 组合进 `DstManagerService`：承载结构命令的
预览（`preview_changes`）与受控发布（`execute_changes`），以及布局来源
基准捕获、CAD 执行估算与命令归一化等编辑域专属辅助。workspace 门禁
（`_check_revision`/`_gate_writable`）与事务辅助保留在编排入口与共享
模块，经 `self` 访问。
"""

import uuid
from pathlib import Path
from typing import Any

from dst_manager.application.errors import ApplicationError
from dst_manager.application.summaries import (
    attach_expected_file_hashes,
    build_semantic_diff,
    operation_digest,
    parallel_makespan,
)
from dst_manager.domain.models import JobStatus, Severity, SuffixOptions, Workspace
from dst_manager.domain.planning import (
    PlanningError,
    build_structural_plan,
    derived_document_from_plan,
)
from dst_manager.infrastructure.acsm_xml import (
    AcsmDocument,
    AcsmValidationError,
    load_acsm,
)
from dst_manager.infrastructure.filesystem.locking import WindowsWriteLocks
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
)
from dst_manager.infrastructure.persistence.database import WorkspaceBusyError


class EditingOperations:
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
        self._gate_writable(workspace.document)
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
            structural |= command_type in {"update_subset_title", "delete_sheet", "delete_subset", "insert_sheet", "insert_subset"}
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
            diagnostics.extend(self._collect_structural_source_baselines(workspace, execution_intent))
            if not diagnostics:
                try:
                    attach_expected_file_hashes(workspace, execution_intent)
                    execution_intent["estimate"] = self._estimate_cad_execution(
                        cad_version,
                        execution_intent,
                    )
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
                preview_dom = load_acsm(self.codec.decode_file(workspace.dst_path)).clone()
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
        semantic_diff = build_semantic_diff(workspace, normalized_commands, execution_intent)
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
        target_baselines = {str(workspace.dst_path): base_revision_id}
        source_baselines: list[dict[str, Any]] = []
        if execution_intent is not None:
            target_baselines.update(execution_intent.get("expected_file_hashes", {}))
            source_baselines = execution_intent.get("source_baselines", [])
        preview_digest = operation_digest(
            operation_type="change_set",
            workspace_id=workspace_id,
            base_revision_id=base_revision_id,
            normalized_input={"commands": normalized_commands},
            semantic_diff=semantic_diff,
            target_baselines=target_baselines,
            cad_version=cad_version,
            source_baselines=source_baselines,
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
        if preview_digest != plan["preview_digest"]:
            raise ApplicationError("REPREVIEW_REQUIRED", "变更预览已变化或尚未确认，请重新预览并确认", 409)
        normalized_commands = self._normalize_commands(commands)
        job_id = str(uuid.uuid4())
        try:
            self.database.create_job(job_id, workspace_id, "change_set", JobStatus.VALIDATED, {"base_revision_id": base_revision_id, "plan": plan, "commands": normalized_commands}, cad_version)
        except WorkspaceBusyError as exc:
            raise ApplicationError("WORKSPACE_WRITE_BUSY", str(exc), 409) from exc
        if plan["requires_cad"]:
            capability = self.capabilities()[cad_version]
            execution_groups = (plan.get("execution_intent") or {}).get("groups", [])
            if capability["available"] or not execution_groups:
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
                    expected_baseline = self._capture_baseline(workspace.dst_path)
                except OSError as exc:
                    raise PublishBaselineError("捕获 DST 执行基准时文件发生变化") from exc
                if expected_baseline is None or expected_baseline.sha256 != base_revision_id:
                    raise PublishBaselineError("DST 已偏离提交预览基准")
                self.database.update_job(job_id, JobStatus.STAGING, 20)
                self._safe_operation_event(workspace.root, job_id, "STAGING", job_type="metadata")
                acsm = load_acsm(self.codec.decode_file(workspace.dst_path))
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
                load_acsm(self.codec.decode_file(staging))
                self.database.update_job(job_id, JobStatus.PREPARED, 70)
                if self._capture_baseline(workspace.dst_path) != expected_baseline:
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

    def _collect_structural_source_baselines(
        self,
        workspace: Workspace,
        execution_intent: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """在预览中捕获全部布局来源的轻量基准，不调用 CAD。"""
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

        baselines = []
        for item in sorted(sources.values(), key=lambda source: str(source["path"]).casefold()):
            path = item["path"]
            try:
                baseline = self._capture_baseline(path)
            except OSError as exc:
                return [diagnostic("LAYOUT_SOURCE_UNREADABLE", f"布局来源无法读取：{exc}")]
            if baseline is None:
                return [diagnostic("LAYOUT_SOURCE_NOT_FOUND", f"布局来源不存在：{path}")]
            baselines.append(
                {
                    "path": str(path),
                    "sha256": baseline.sha256,
                    "identity": list(baseline.identity),
                    "source_types": sorted(item["types"]),
                    "requested_layouts": sorted(item["requested_layouts"], key=str.casefold),
                },
            )
        execution_intent["source_baselines"] = baselines
        execution_intent["cad_validation_deferred"] = True
        return []

    def _estimate_cad_execution(
        self,
        cad_version: str,
        execution_intent: dict[str, Any],
    ) -> dict[str, Any]:
        """按已确认计划估算 Core Console 数量、并发度和墙钟耗时范围。"""
        fallback = {
            "2016": {"rename_only": (15_000, 45_000), "rebuild": (60_000, 180_000)},
            "2020": {"rename_only": (10_000, 30_000), "rebuild": (45_000, 120_000)},
        }
        groups = list(execution_intent.get("groups", []))
        concurrency = min(self.settings.cad_max_parallel, len(groups)) if groups else 0
        sources: list[dict[str, Any]] = []
        ranges: dict[str, tuple[int, int]] = {}
        for operation in sorted({str(group["cad_operation"]) for group in groups}):
            samples = self.database.cad_duration_history(cad_version, operation)
            if len(samples) >= 3:
                ranges[operation] = (min(samples), max(samples))
                source = "history"
            else:
                ranges[operation] = fallback[cad_version].get(operation, (60_000, 180_000))
                source = "fallback-v1"
            sources.append(
                {
                    "cad_operation": operation,
                    "sample_count": len(samples),
                    "source": source,
                },
            )
        lower_durations = [ranges[str(group["cad_operation"])][0] for group in groups]
        upper_durations = [ranges[str(group["cad_operation"])][1] for group in groups]
        lower_total = parallel_makespan(lower_durations, concurrency)
        upper_total = parallel_makespan(upper_durations, concurrency)
        return {
            "schema_version": 1,
            "estimated": True,
            "core_console_count": len(groups),
            "concurrency": concurrency,
            "duration_ms": {"lower": lower_total, "upper": upper_total},
            "sources": sources,
        }

    @staticmethod
    def _normalize_commands(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {
            "update_sheet_set",
            "update_subset_title",
            "update_sheet_properties",
            "delete_sheet",
            "insert_sheet",
            "insert_subset",
            "delete_subset",
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
        structural_types = {"update_subset", "delete_sheet", "delete_subset", "insert_sheet", "insert_subset"}
        for command in commands:
            if command["type"] in {"add_custom_property", "delete_custom_property"}:
                document.apply_property_definition_commands([command])
            elif not structural or command["type"] not in structural_types:
                document.apply_metadata_commands([command])
