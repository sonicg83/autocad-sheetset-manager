"""XML 导入导出域（v0.3.2 Task 0 自 service.py 拆分）。

`XmlExportOperations` 以 mixin 组合进 `DstManagerService`：预览 XML 与
当前图纸集的结构差异（`preview_xml`），并沿受控发布事务把 XML 写回
主 DST 或工作区内目标文件（`export_xml_to_dst`）。
"""

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dst_manager.application.errors import ApplicationError
from dst_manager.application.summaries import operation_digest
from dst_manager.domain.models import JobStatus, Severity
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.filesystem.locking import WindowsWriteLocks
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
    file_sha256,
)
from dst_manager.infrastructure.persistence.database import WorkspaceBusyError


class XmlExportOperations:
    def preview_xml(
        self,
        workspace_id: str,
        base_revision_id: str,
        xml: bytes,
        destination: Path | None = None,
    ) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        self._gate_writable(workspace.document)
        imported = load_acsm(xml).project(workspace.root)
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
        changes = json.loads(json.dumps(changes, ensure_ascii=False, default=str))
        diagnostics = [asdict(issue) for issue in imported.diagnostics]
        executable = not any(issue.severity == Severity.ERROR for issue in imported.diagnostics)
        normalized_destination = str(destination) if destination is not None else None
        semantic_diff = {
            "sheet_count_before": len(workspace.document.sheets),
            "sheet_count_after": len(imported.sheets),
            "subset_count_before": len(workspace.document.subsets),
            "subset_count_after": len(imported.subsets),
            "changes": changes,
            "diagnostics": diagnostics,
        }
        preview_digest = operation_digest(
            operation_type="xml_export",
            workspace_id=workspace_id,
            base_revision_id=base_revision_id,
            normalized_input={
                "xml_sha256": hashlib.sha256(xml).hexdigest(),
                "destination": normalized_destination,
            },
            semantic_diff=semantic_diff,
            target_baselines={
                str(workspace.dst_path): base_revision_id,
                **(
                    {normalized_destination: destination_revision_id}
                    if normalized_destination is not None
                    else {}
                ),
            },
        )
        return {
            "workspace_id": workspace_id,
            "base_revision_id": base_revision_id,
            "sheet_count_before": len(workspace.document.sheets),
            "sheet_count_after": len(imported.sheets),
            "subset_count_before": len(workspace.document.subsets),
            "subset_count_after": len(imported.subsets),
            "changes": changes,
            "diagnostics": diagnostics,
            "destination_revision_id": destination_revision_id,
            "preview_digest": preview_digest,
            "executable": executable,
        }

    def export_xml_to_dst(
        self,
        workspace_id: str,
        base_revision_id: str,
        xml: bytes,
        destination: Path,
        destination_revision_id: str | None = None,
        preview_digest: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_xml(workspace_id, base_revision_id, xml, destination)
        if preview_digest != preview["preview_digest"]:
            raise ApplicationError("REPREVIEW_REQUIRED", "XML 导出预览已变化或尚未确认，请重新预览并确认", 409)
        workspace = self.get_workspace(workspace_id)
        self._check_revision(workspace, base_revision_id)
        self._gate_writable(workspace.document)
        document = load_acsm(xml)
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
                expected_baseline = self._capture_baseline(destination)
                actual_destination_revision = expected_baseline.sha256 if expected_baseline is not None else "MISSING"
                if actual_destination_revision != frozen_destination_revision:
                    raise PublishBaselineError("XML 导出目标已偏离预览基准")
                before_hash = expected_baseline.sha256 if expected_baseline is not None else base_revision_id
                input_path.parent.mkdir(parents=True, exist_ok=True)
                staged.parent.mkdir(parents=True, exist_ok=True)
                input_path.write_bytes(xml)
                self._safe_operation_event(workspace.root, job_id, "STAGING", job_type="xml_export")
                self.codec.encode_file(document.to_bytes(), staged)
                roundtrip = load_acsm(self.codec.decode_file(staged))
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
