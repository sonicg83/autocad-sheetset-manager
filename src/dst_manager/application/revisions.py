"""修订恢复域（v0.3.2 Task 0 自 service.py 拆分）。

`RevisionRestoreOperations` 以 mixin 组合进 `DstManagerService`：预览
恢复清单（`preview_revision_restore`）与沿受控发布事务写回
（`restore_revision`）。基准捕获经入口共享门禁 `self._capture_baseline`
转发，保持测试对 service 模块 monkeypatch 契约不变。
"""

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dst_manager.application.errors import ApplicationError
from dst_manager.application.summaries import operation_digest
from dst_manager.domain.models import JobStatus
from dst_manager.infrastructure.filesystem.locking import (
    WindowsResultGuards,
    WindowsWriteLocks,
)
from dst_manager.infrastructure.filesystem.publisher import (
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
    file_sha256,
)
from dst_manager.infrastructure.persistence.database import WorkspaceBusyError


class RevisionRestoreOperations:
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
                    backup_baseline = self._capture_baseline(Path(entry["backup"]))
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
        base_revision_id = file_sha256(dst_path)
        preview_digest = operation_digest(
            operation_type="revision_restore",
            workspace_id=workspace_id,
            base_revision_id=base_revision_id,
            normalized_input={"source_revision_id": revision_id},
            semantic_diff={"files": files, "conflicts": conflicts},
            target_baselines={item["path"]: item["current_hash"] for item in files},
        )
        return {
            "workspace_id": workspace_id,
            "revision_id": revision_id,
            "base_revision_id": base_revision_id,
            "files": files,
            "conflicts": conflicts,
            "executable": not conflicts,
            "preview_digest": preview_digest,
        }

    def restore_revision(
        self,
        workspace_id: str,
        revision_id: str,
        base_revision_id: str,
        preview_digest: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_revision_restore(workspace_id, revision_id)
        if preview_digest != preview["preview_digest"]:
            raise ApplicationError("REPREVIEW_REQUIRED", "修订恢复预览已变化或尚未确认，请重新预览并确认", 409)
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
                        target: self._capture_baseline(target)
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
                    baseline = self._capture_baseline(source)
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
                            or self._capture_baseline(source.resolve()) != source_baselines[source.resolve()]
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
