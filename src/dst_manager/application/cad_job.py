import json
import re
import shutil
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dst_manager.domain.models import JobStatus, Severity, Workspace
from dst_manager.domain.planning import (
    PlanningError,
    derived_document_from_plan,
    metadata_commands_for_derived_document,
)
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    CoreConsoleExecutor,
    ScriptRenderer,
    parse_handles,
    parse_rename_result,
    rename_result_path,
    write_rename_request,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.locking import (
    FileLockError,
    WindowsWriteLocks,
)
from dst_manager.infrastructure.filesystem.publisher import (
    ExpectedFileBaseline,
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
    RecoverablePublisher,
    capture_file_baseline,
    file_sha256,
)
from dst_manager.infrastructure.filesystem.workspace import write_workspace_metadata
from dst_manager.infrastructure.logging_text import sanitize_log_text
from dst_manager.infrastructure.operation_log import append_operation_event
from dst_manager.infrastructure.persistence import Database


@dataclass(frozen=True, slots=True)
class CadWorkUnit:
    index: int
    group: dict[str, Any]
    source_snapshot: Path
    staging_dir: Path
    scripts_dir: Path
    logs_dir: Path
    timeout: int


@dataclass(frozen=True, slots=True)
class CadWorkResult:
    index: int
    target: Path
    source_target: Path | None
    staged: Path
    bindings: dict[str, dict[str, str]]
    duration_ms: int
    log_path: Path
    peak_memory_bytes: int | None
    staging_bytes: int


# 兼容既有调用方；新代码统一使用 CAD 工作单元名称。
RebuildWorkUnit = CadWorkUnit
RebuildResult = CadWorkResult


class CadJobRunner:
    def __init__(
        self,
        database: Database,
        codec: DstCodec,
        publisher: RecoverablePublisher,
        timeout: int,
        max_parallel: int = 4,
        heartbeat_interval: float = 30.0,
    ):
        self.database, self.codec, self.publisher, self.timeout = database, codec, publisher, timeout
        if not 1 <= max_parallel <= 10:
            raise ValueError("CAD_MAX_PARALLEL_OUT_OF_RANGE")
        if heartbeat_interval <= 0:
            raise ValueError("CAD_HEARTBEAT_INTERVAL_INVALID")
        self.max_parallel = max_parallel
        self.heartbeat_interval = heartbeat_interval
        self.renderer, self.executor = ScriptRenderer(), CoreConsoleExecutor()
        self._active_owner: tuple[str, str, int] | None = None

    def _update_owned_job(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
        status: str,
        progress: int,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> bool:
        return bool(
            self.database.update_job(
                job_id,
                status,
                progress,
                error_code,
                error_detail,
                worker_id=worker_id,
                attempt=attempt,
            ),
        )

    def _require_owned_update(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
        status: str,
        progress: int,
    ) -> None:
        if not self._update_owned_job(job_id, worker_id, attempt, status, progress):
            raise PlanningError("CAD_JOB_LEASE_LOST", "CAD Worker 已失去任务租约")

    def run(self, job: dict[str, Any], workspace: Workspace, capability: CadCapability) -> dict[str, Any]:
        job_id = job["id"]
        payload = job["payload"]
        worker_id = job.get("worker_id") or "local-worker"
        attempt = job.get("attempt", 1)
        append_operation_event(workspace.root, job_id, "WORKER_CLAIMED", cad_version=capability.version)
        if workspace.revision_id != payload["base_revision_id"]:
            self._update_owned_job(job_id, worker_id, attempt, JobStatus.FAILED, 0, "REVISION_CONFLICT")
            return self.database.get_job(job_id) or {}
        if not capability.available:
            self._update_owned_job(job_id, worker_id, attempt, JobStatus.FAILED, 0, "CAD_CAPABILITY_UNAVAILABLE")
            return self.database.get_job(job_id) or {}
        try:
            plan = payload.get("plan", {}).get("execution_intent")
            if not isinstance(plan, dict):
                raise PlanningError("EXECUTION_PLAN_MISSING", "CAD 任务缺少已确认的执行计划")
            if not isinstance(plan.get("expected_file_hashes"), dict):
                raise PlanningError("EXECUTION_BASELINE_MISSING", "CAD 任务缺少预览内容基准")
            self._validate_source_baselines(plan)
            return self._execute(job_id, worker_id, attempt, workspace, capability, payload["commands"], plan)
        except FileLockError as exc:
            append_operation_event(workspace.root, job_id, "BLOCKED_FILE_LOCK")
            self._update_owned_job(job_id, worker_id, attempt, JobStatus.BLOCKED_FILE_LOCK, 0, "BLOCKED_FILE_LOCK", str(exc))
        except PublishRolledBackError as exc:
            append_operation_event(workspace.root, job_id, "PUBLISH_ROLLED_BACK")
            self._update_owned_job(job_id, worker_id, attempt, JobStatus.ROLLED_BACK, 0, "PUBLISH_ROLLED_BACK", str(exc))
        except PublishRecoveryError as exc:
            append_operation_event(workspace.root, job_id, "PUBLISH_RECOVERY_FAILED")
            self.database.finalize_job_terminal(
                job_id,
                JobStatus.NEEDS_REVIEW,
                "PUBLISH_RECOVERY_FAILED",
                str(exc),
                worker_id=worker_id,
                attempt=attempt,
            )
        except subprocess.TimeoutExpired as exc:
            append_operation_event(workspace.root, job_id, "CAD_TIMEOUT")
            self._update_owned_job(job_id, worker_id, attempt, JobStatus.FAILED, 0, "CAD_TIMEOUT", str(exc))
        except subprocess.CalledProcessError as exc:
            append_operation_event(workspace.root, job_id, "CAD_PROCESS_FAILED", returncode=exc.returncode)
            self._write_failure_log(workspace, job_id, attempt, exc.stdout or "", exc.stderr or "")
            self._update_owned_job(job_id, worker_id, attempt, JobStatus.FAILED, 0, "CAD_PROCESS_FAILED", str(exc))
        except Exception as exc:  # noqa: BLE001 - Worker边界必须把任意故障持久化为终态
            append_operation_event(workspace.root, job_id, "FAILED", error=repr(exc))
            self._write_failure_log(workspace, job_id, attempt, "", repr(exc))
            current = self.database.get_job(job_id) or {}
            if current.get("status") != JobStatus.SUCCEEDED:
                self._update_owned_job(
                    job_id,
                    worker_id,
                    attempt,
                    JobStatus.FAILED,
                    0,
                    getattr(exc, "code", type(exc).__name__.upper()),
                    str(exc),
                )
        return self.database.get_job(job_id) or {}

    def _execute(self, job_id: str, worker_id: str, attempt: int, workspace: Workspace, capability: CadCapability, commands: list[dict], plan: dict[str, Any]) -> dict[str, Any]:
        commit_state: dict[str, Any] = {"result_hash": None, "revision_dir": None, "error": None}
        job_dir = workspace.root / ".dst-manager" / "jobs" / job_id
        attempt_dir = job_dir / f"attempt-{attempt:03d}"
        staging_dir, scripts_dir, logs_dir = attempt_dir / "staging", attempt_dir / "scripts", attempt_dir / "logs"
        for directory in (staging_dir, scripts_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        plan_dir = workspace.root / ".dst-manager" / "revisions" / job_id / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "change-set.json").write_text(json.dumps({"base_revision_id": workspace.revision_id, "commands": commands}, ensure_ascii=False, indent=2), encoding="utf-8")
        input_dir = attempt_dir / "input" / "sources"
        input_dir.mkdir(parents=True, exist_ok=True)
        unique_sources: set[Path] = set()
        for group in plan["groups"]:
            base_source = Path(group["source_snapshot"]).resolve()
            self._require_source_file(
                base_source,
                "TEMPLATE_NOT_FOUND" if group["operation"] == "create" else "SOURCE_TARGET_NOT_FOUND",
            )
            unique_sources.add(base_source)
            for layout in group["layouts"]:
                source = Path(layout["source_file"]).resolve()
                self._require_source_file(
                    source,
                    "TEMPLATE_NOT_FOUND" if layout["source_type"] == "template_layout" else "LAYOUT_SOURCE_NOT_FOUND",
                )
                unique_sources.add(source)
        path_graph = plan.get("path_graph")
        if not isinstance(path_graph, dict):
            raise PlanningError("EXECUTION_PATH_GRAPH_INVALID", "CAD 任务缺少完整的DWG路径图")
        publication_targets = {
            workspace.dst_path.resolve(),
            *(Path(path).resolve() for path in path_graph.get("old_sources", [])),
            *(Path(path).resolve() for path in path_graph.get("final_targets", [])),
        }
        required_space = sum(path.stat().st_size for path in unique_sources) + 2 * sum(
            path.stat().st_size for path in publication_targets if path.exists()
        )
        if shutil.disk_usage(workspace.root).free < required_space:
            raise OSError("STAGING_DISK_SPACE_INSUFFICIENT")
        lock_targets = [path for path in publication_targets | unique_sources if path.exists()]
        with WindowsWriteLocks(lock_targets):
            try:
                captured_baselines = {
                    path: capture_file_baseline(path)
                    for path in publication_targets | unique_sources
                }
            except (OSError, PublishBaselineError) as exc:
                raise PlanningError("BASE_FILE_CHANGED", "捕获执行基准时文件发生变化") from exc
            self._validate_expected_hashes(plan, captured_baselines, workspace)
            expected_publish_baselines = {
                path: captured_baselines[path]
                for path in publication_targets
            }
            baseline_hashes = {
                path: baseline.sha256 if baseline is not None else None
                for path, baseline in expected_publish_baselines.items()
            }
            self._validate_create_targets(plan, baseline_hashes)
            source_baselines: dict[Path, ExpectedFileBaseline] = {}
            for source in unique_sources:
                baseline = captured_baselines[source]
                if baseline is None:
                    raise PlanningError("BASE_FILE_CHANGED", f"源文件在基准捕获时已消失：{source}")
                source_baselines[source] = baseline
            source_snapshots: dict[Path, Path] = {}
            for index, source in enumerate(sorted(unique_sources, key=lambda path: str(path).casefold())):
                source_baseline = source_baselines[source]
                snapshot = input_dir / f"{source_baseline.sha256[:16]}-{index:03d}-{source.name}"
                self._copy_verified_snapshot(source, snapshot, source_baseline)
                source_snapshots[source] = snapshot
            for group in plan["groups"]:
                for layout in group["layouts"]:
                    source = Path(layout["source_file"]).resolve()
                    layout["source_file"] = str(source_snapshots[source])
                group["source_snapshot"] = str(source_snapshots[Path(group["source_snapshot"]).resolve()])
            (plan_dir / "execution-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._require_owned_update(job_id, worker_id, attempt, JobStatus.CAD_RUNNING, 15)
            units = [CadWorkUnit(index, group, Path(group["source_snapshot"]), staging_dir, scripts_dir, logs_dir, self.timeout) for index, group in enumerate(plan["groups"])]
            self._active_owner = (job_id, worker_id, attempt)
            try:
                results = self._run_groups(job_id, worker_id, workspace, capability, units, attempt=attempt)
            finally:
                self._active_owner = None
            staged_files, bindings = self._collect_staged_files(results, plan)
            self._require_owned_update(job_id, worker_id, attempt, JobStatus.VERIFYING, 70)
            staged_dst = self._write_staged_dst(workspace, plan, bindings, staging_dir, commands)
            staged_files[workspace.dst_path.resolve()] = staged_dst
            self._require_owned_update(job_id, worker_id, attempt, JobStatus.PREPARED, 80)
            for path, expected_baseline in expected_publish_baselines.items():
                if capture_file_baseline(path) != expected_baseline:
                    raise PlanningError("BASE_FILE_CHANGED", f"发布基准已变化：{path}")
            before_hash = baseline_hashes[workspace.dst_path.resolve()]
            staged_baselines = {
                path.resolve(): expected_publish_baselines[path.resolve()]
                for path in staged_files
            }
            self._require_owned_update(job_id, worker_id, attempt, JobStatus.PUBLISHING, 90)
            append_operation_event(workspace.root, job_id, "PUBLISHING", file_count=len(staged_files))

            def ensure_publish_ownership() -> None:
                if not self.database.heartbeat(job_id, worker_id, attempt=attempt):
                    raise PlanningError("CAD_JOB_LEASE_LOST", "CAD Worker 已失去任务租约")

            def finalize_cad(revision_dir: Path, journal: dict[str, Any]) -> None:
                try:
                    result_hash = self._committed_result_hash(journal, workspace.dst_path)
                    commit_state["result_hash"] = result_hash
                    commit_state["revision_dir"] = revision_dir
                    finalized = self.database.finalize_committed_job(
                        f"change-{job_id}",
                        workspace.id,
                        job_id,
                        before_hash,
                        result_hash,
                        revision_dir,
                        current_revision=result_hash,
                        worker_id=worker_id,
                        attempt=attempt,
                    )
                    if not finalized:
                        raise PlanningError("CAD_JOB_LEASE_LOST", "CAD Worker 已失去任务租约")
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
                                worker_id=worker_id,
                                attempt=attempt,
                            )
                    except Exception:  # noqa: BLE001, S110 - 启动恢复仍会依据 COMMITTED 日志隔离
                        pass

            self.publisher.publish(
                job_id,
                workspace.root,
                staged_files,
                expected_baselines=staged_baselines,
                before_commit=ensure_publish_ownership,
                on_committed=finalize_cad,
            )
            if commit_state["error"] is not None:
                return self.database.get_job(job_id) or {}
        result_hash = commit_state["result_hash"]
        revision_dir = commit_state["revision_dir"]
        if not isinstance(result_hash, str) or not isinstance(revision_dir, Path):
            self.database.finalize_job_terminal(
                job_id,
                JobStatus.NEEDS_REVIEW,
                "COMMITTED_FINALIZE_MISSING",
                worker_id=worker_id,
                attempt=attempt,
            )
            return self.database.get_job(job_id) or {}
        self._safe_post_commit_copy(logs_dir, revision_dir / "logs")
        self._safe_post_commit_copy(scripts_dir, revision_dir / "scripts")
        self._safe_post_commit_copy(input_dir.parent, revision_dir / "input")
        try:
            write_workspace_metadata(workspace.root, workspace.id, workspace.dst_path, result_hash, capability.version)
        except Exception as exc:  # noqa: BLE001 - DB 已闭环，元数据失败只能记录诊断
            self._safe_post_commit_event(workspace.root, job_id, "POST_COMMIT_METADATA_FAILED", error=repr(exc))
        self._safe_post_commit_event(workspace.root, job_id, "SUCCEEDED", revision_id=f"change-{job_id}")
        return self.database.get_job(job_id) or {}

    @staticmethod
    def _validate_expected_hashes(
        plan: dict[str, Any],
        captured: dict[Path, ExpectedFileBaseline | None],
        workspace: Workspace,
    ) -> None:
        raw_expected = plan.get("expected_file_hashes")
        if raw_expected is None:
            return
        expected = {Path(path).resolve(): digest for path, digest in raw_expected.items()}
        if expected.keys() != captured.keys():
            raise PlanningError("EXECUTION_BASELINE_TARGET_MISMATCH", "执行文件集合已偏离预览")
        if expected.get(workspace.dst_path.resolve()) != workspace.revision_id:
            raise PlanningError("BASE_FILE_CHANGED", "DST 执行基准与任务修订不一致")
        expected_identities = {
            Path(path).resolve(): tuple(identity)
            for path, identity in plan.get("expected_file_identities", {}).items()
        }
        for path, baseline in captured.items():
            actual = baseline.sha256 if baseline is not None else None
            if actual != expected[path]:
                raise PlanningError("BASE_FILE_CHANGED", f"文件内容已偏离预览基准：{path}")
            if path in expected_identities and (baseline is None or baseline.identity != expected_identities[path]):
                raise PlanningError("BASE_FILE_CHANGED", f"文件身份已偏离预览基准：{path}")

    @staticmethod
    def _validate_source_baselines(plan: dict[str, Any]) -> None:
        if plan.get("cad_validation_deferred") is not True:
            raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", "CAD 任务缺少已延期的布局校验标记")
        raw_baselines = plan.get("source_baselines")
        if not isinstance(raw_baselines, list):
            raise PlanningError("EXECUTION_SOURCE_BASELINE_MISSING", "CAD 任务缺少布局来源基准")
        sources: dict[Path, dict[str, set[str]]] = {}

        def register(path: Path, source_type: str, requested_layout: str | None = None) -> None:
            item = sources.setdefault(path, {"source_types": set(), "requested_layouts": set()})
            item["source_types"].add(source_type)
            if requested_layout is not None:
                item["requested_layouts"].add(requested_layout)

        for group in plan.get("groups", []):
            snapshot = Path(group["source_snapshot"]).resolve()
            register(snapshot, "template_layout" if group.get("operation") == "create" else "existing_snapshot")
            for layout in group.get("layouts", []):
                source = Path(layout["source_file"]).resolve()
                source_type = layout.get("source_type")
                if not isinstance(source_type, str):
                    raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", "布局来源基准缺少来源类型")
                register(source, source_type, str(layout["source_layout"]))
        baselines: dict[Path, dict[str, Any]] = {}
        for item in raw_baselines:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", "布局来源基准格式无效")
            path = Path(item["path"]).resolve()
            if path in baselines:
                raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", f"布局来源基准重复：{path}")
            baselines[path] = item
        if baselines.keys() != sources.keys():
            raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", "布局来源基准未完整覆盖执行计划")
        raw_expected_hashes = plan.get("expected_file_hashes")
        raw_expected_identities = plan.get("expected_file_identities")
        if not isinstance(raw_expected_hashes, dict):
            raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", "布局来源基准缺少期望文件证据")
        if raw_expected_identities is None:
            raw_expected_identities = {}
        elif not isinstance(raw_expected_identities, dict):
            raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", "布局来源基准缺少期望文件证据")
        if sources and not raw_expected_identities:
            raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", "布局来源基准缺少期望文件证据")
        expected_hashes = {
            Path(path).resolve(): digest
            for path, digest in raw_expected_hashes.items()
        }
        expected_identities = {
            Path(path).resolve(): identity
            for path, identity in raw_expected_identities.items()
        }
        for path, source in sources.items():
            item = baselines[path]
            source_types = item.get("source_types")
            recorded_requested = item.get("requested_layouts")
            if (
                not isinstance(source_types, list)
                or not isinstance(recorded_requested, list)
                or not all(isinstance(source_type, str) for source_type in source_types)
                or not all(isinstance(layout, str) for layout in recorded_requested)
                or path not in expected_hashes
                or not isinstance(expected_hashes[path], str)
                or item.get("sha256") != expected_hashes[path]
                or not isinstance(item.get("identity"), list)
                or path not in expected_identities
                or not isinstance(expected_identities[path], list)
                or item["identity"] != expected_identities[path]
                or set(source_types) != source["source_types"]
                or {str(name).casefold() for name in recorded_requested}
                != {name.casefold() for name in source["requested_layouts"]}
            ):
                raise PlanningError("EXECUTION_SOURCE_BASELINE_MISMATCH", f"布局来源基准与计划不一致：{path}")

    @staticmethod
    def _committed_result_hash(journal: dict[str, Any], target: Path) -> str:
        target_key = str(target.resolve()).casefold()
        for entry in journal["files"]:
            if str(Path(entry["target"]).resolve()).casefold() == target_key:
                value = entry.get("result_hash")
                if isinstance(value, str):
                    return value
        raise PublishRecoveryError(f"COMMITTED_RESULT_MISSING: {target}")

    @staticmethod
    def _safe_post_commit_copy(source: Path, destination: Path) -> None:
        try:
            shutil.copytree(source, destination, dirs_exist_ok=True)
        except Exception:  # noqa: BLE001, S110 - 提交后归档失败不得改变已提交状态
            pass

    @staticmethod
    def _safe_post_commit_event(root: Path, job_id: str, event: str, **details: Any) -> None:
        try:
            append_operation_event(root, job_id, event, **details)
        except Exception:  # noqa: BLE001, S110 - 提交后日志失败不得改变已提交状态
            pass

    @staticmethod
    def _copy_verified_snapshot(
        source: Path,
        snapshot: Path,
        expected_baseline: ExpectedFileBaseline,
    ) -> None:
        if capture_file_baseline(source) != expected_baseline:
            raise PlanningError("BASE_FILE_CHANGED", f"源文件在快照前已变化：{source}")
        shutil.copy2(source, snapshot)
        if (
            file_sha256(snapshot) != expected_baseline.sha256
            or capture_file_baseline(source) != expected_baseline
        ):
            snapshot.unlink(missing_ok=True)
            raise PlanningError("BASE_FILE_CHANGED", f"源文件与快照基准不一致：{source}")

    @staticmethod
    def _validate_create_targets(plan: dict[str, Any], baselines: dict[Path, str | None]) -> None:
        old_sources = {
            str(Path(path).resolve()).casefold()
            for path in plan["path_graph"].get("old_sources", [])
        }
        for group in plan["groups"]:
            if group["operation"] != "create":
                continue
            if group.get("expected_baseline", "missing") is not None:
                raise PlanningError("EXECUTION_PLAN_INVALID", "create 计划必须声明空目标基准")
            target = Path(group["target_file"]).resolve()
            if baselines[target] is None:
                continue
            explicitly_reused = group.get("target_reuses_source") is True and str(target).casefold() in old_sources
            if not explicitly_reused:
                raise PlanningError("CREATE_TARGET_EXISTS", f"新建DWG目标已存在：{target}")

    @staticmethod
    def _collect_staged_files(
        results: list[CadWorkResult],
        plan: dict[str, Any],
    ) -> tuple[dict[Path, Path | None], dict[str, dict[str, str]]]:
        expected_targets = {
            str(Path(group["target_file"]).resolve()).casefold(): Path(group["target_file"]).resolve()
            for group in plan["groups"]
        }
        staged_by_key: dict[str, Path] = {}
        bindings: dict[str, dict[str, str]] = {}
        for result in sorted(results, key=lambda item: item.index):
            key = str(result.target.resolve()).casefold()
            if key in staged_by_key:
                raise PlanningError("DUPLICATE_STAGED_TARGET", f"多个CAD结果指向同一最终DWG：{result.target}")
            if key not in expected_targets:
                raise PlanningError("CAD_RESULT_TARGET_MISMATCH", f"CAD结果包含计划外目标：{result.target}")
            staged_by_key[key] = result.staged
            bindings.update(result.bindings)
        if staged_by_key.keys() != expected_targets.keys():
            raise PlanningError("CAD_RESULT_TARGET_MISMATCH", "CAD结果未与最终计划目标一一对应")
        staged_files: dict[Path, Path | None] = {
            expected_targets[key]: staged
            for key, staged in staged_by_key.items()
        }
        final_keys = {
            str(Path(path).resolve()).casefold()
            for path in plan["path_graph"].get("final_targets", [])
        }
        for path in plan["path_graph"].get("delete_targets", []):
            target = Path(path).resolve()
            if str(target).casefold() not in final_keys:
                staged_files[target] = None
        return staged_files, bindings

    def _run_groups(
        self,
        job_id: str,
        worker_id: str,
        workspace: Workspace,
        capability: CadCapability,
        units: list[CadWorkUnit],
        *,
        attempt: int = 1,
    ) -> list[CadWorkResult]:
        if not units:
            return []
        results: list[CadWorkResult] = []
        next_index = 0
        failures: dict[int, BaseException] = {}
        lease_lost = False
        futures: dict[Future[CadWorkResult], CadWorkUnit] = {}
        next_heartbeat = time.monotonic() + self.heartbeat_interval
        with ThreadPoolExecutor(max_workers=self.max_parallel, thread_name_prefix="dst-cad") as pool:
            while next_index < len(units) and len(futures) < self.max_parallel:
                unit = units[next_index]
                futures[pool.submit(self._execute_group, job_id, workspace, capability, unit)] = unit
                next_index += 1
            while futures:
                wait_timeout = max(0.0, next_heartbeat - time.monotonic())
                done, _ = wait(futures, timeout=wait_timeout, return_when=FIRST_COMPLETED)
                if time.monotonic() >= next_heartbeat:
                    if not self.database.heartbeat(job_id, worker_id, attempt=attempt):
                        lease_lost = True
                        failures.setdefault(-1, PlanningError("CAD_JOB_LEASE_LOST", "CAD Worker 已失去任务租约"))
                    next_heartbeat = time.monotonic() + self.heartbeat_interval
                for future in sorted(done, key=lambda item: futures[item].index):
                    unit = futures.pop(future)
                    try:
                        results.append(future.result())
                    except BaseException as exc:  # noqa: BLE001 - 等待已启动 CAD 安全退出后统一抛出
                        failures.setdefault(unit.index, exc)
                    completed = len(results)
                    if not lease_lost and not failures:
                        try:
                            self._require_owned_update(
                                job_id,
                                worker_id,
                                attempt,
                                JobStatus.CAD_RUNNING,
                                15 + int(50 * completed / len(units)),
                            )
                        except PlanningError as exc:
                            lease_lost = True
                            failures.setdefault(-1, exc)
                if not failures:
                    while next_index < len(units) and len(futures) < self.max_parallel:
                        following = units[next_index]
                        futures[pool.submit(self._execute_group, job_id, workspace, capability, following)] = following
                        next_index += 1
        if failures:
            raise min(failures.items(), key=lambda item: item[0])[1]
        return sorted(results, key=lambda result: result.index)

    def _execute_group(self, job_id: str, workspace: Workspace, capability: CadCapability, unit: CadWorkUnit) -> CadWorkResult:
        operation = unit.group.get("cad_operation")
        owner = self._active_owner
        owner_values = {} if owner is None else {"worker_id": owner[1], "attempt": owner[2]}
        if operation == "rename_only":
            return self._rename_group(job_id, workspace, capability, unit, **owner_values)
        if operation == "rebuild":
            return self._rebuild_group(job_id, workspace, capability, unit, **owner_values)
        raise PlanningError("CAD_OPERATION_INVALID", f"CAD 工作单元操作无效：{operation}")

    def _rename_group(self, job_id: str, workspace: Workspace, capability: CadCapability, unit: CadWorkUnit, *, worker_id: str | None = None, attempt: int | None = None) -> CadWorkResult:
        group_index, group = unit.index, unit.group
        source_target = Path(group["source_target_file"]) if group["source_target_file"] is not None else None
        target = Path(group["target_file"])
        started = time.perf_counter()
        started_at = datetime.now(UTC)
        rename_script = unit.scripts_dir / f"rename-{group_index:03d}.scr"
        log_path = unit.logs_dir / f"group-{group_index:03d}.log"
        if self.database.upsert_job_file(
            job_id,
            target,
            source_path=str(source_target) if source_target is not None else None,
            cad_operation="rename_only",
            status="RUNNING",
            progress=5,
            started_at=started_at,
            log_path=str(log_path),
            before_hash=None,
            worker_id=worker_id,
            attempt=attempt,
        ) is False:
            raise PlanningError("CAD_JOB_LEASE_LOST", "CAD Worker 已失去任务租约")
        output = ""
        phase = "校验并批量改名布局"
        before_hash: str | None = None
        try:
            group_dir = unit.staging_dir / f"group-{group_index:03d}"
            group_dir.mkdir(parents=True, exist_ok=True)
            staged = group_dir / target.name
            shutil.copy2(unit.source_snapshot, staged)
            before_hash = file_sha256(source_target) if source_target is not None else None
            result_path = rename_result_path(staged)
            result_path.unlink(missing_ok=True)
            write_rename_request(staged, group["layouts"])
            rename_script.write_text(self.renderer.render_rename(capability.plugin), encoding="mbcs")
            completed = self.executor.run(capability, staged, rename_script, unit.timeout)
            output += self._format_console_output(phase, completed.stdout, completed.stderr)
            log_path.write_text(sanitize_log_text(output), encoding="utf-8")
            expected = {layout["target_layout"] for layout in group["layouts"]}
            renamed_count = parse_rename_result(result_path.read_text(encoding="utf-8"), expected)
            expected_renamed_count = sum(
                layout["original_layout"] != layout["target_layout"] for layout in group["layouts"]
            )
            if renamed_count != expected_renamed_count:
                raise ValueError("LAYOUT_RENAME_RESULT_INVALID")
            duration_ms = int((time.perf_counter() - started) * 1000)
            staging_bytes = staged.stat().st_size
            if self.database.upsert_job_file(
                job_id,
                target,
                cad_operation="rename_only",
                status="SUCCEEDED",
                progress=100,
                duration_ms=duration_ms,
                peak_memory_bytes=completed.peak_memory_bytes,
                staging_bytes=staging_bytes,
                finished_at=datetime.now(UTC),
                before_hash=before_hash,
                result_hash=file_sha256(staged),
                worker_id=worker_id,
                attempt=attempt,
            ) is False:
                raise PlanningError("CAD_JOB_LEASE_LOST", "CAD Worker 已失去任务租约")
            return CadWorkResult(group_index, target, source_target, staged, {}, duration_ms, log_path, completed.peak_memory_bytes, staging_bytes)
        except Exception as exc:
            if isinstance(exc, subprocess.CalledProcessError):
                stdout = exc.stdout if exc.stdout is not None else exc.output
                output += self._format_console_output(phase, stdout, exc.stderr, exc.returncode)
            duration_ms = int((time.perf_counter() - started) * 1000)
            log_path.write_text(sanitize_log_text(output + "\n" + repr(exc)), encoding="utf-8")
            self.database.upsert_job_file(
                job_id,
                target,
                cad_operation="rename_only",
                status="FAILED",
                progress=0,
                duration_ms=duration_ms,
                finished_at=datetime.now(UTC),
                before_hash=before_hash,
                error_code=getattr(exc, "code", type(exc).__name__.upper()),
                error_detail=str(exc),
                worker_id=worker_id,
                attempt=attempt,
            )
            raise

    def _rebuild_group(self, job_id: str, workspace: Workspace, capability: CadCapability, unit: CadWorkUnit, *, worker_id: str | None = None, attempt: int | None = None) -> CadWorkResult:
        group_index, group = unit.index, unit.group
        source_target = Path(group["source_target_file"]) if group["source_target_file"] is not None else None
        target = Path(group["target_file"])
        started = time.perf_counter()
        started_at = datetime.now(UTC)
        rebuild_script = unit.scripts_dir / f"rebuild-{group_index:03d}.scr"
        log_path = unit.logs_dir / f"group-{group_index:03d}.log"
        if self.database.upsert_job_file(
            job_id,
            target,
            source_path=str(source_target) if source_target is not None else None,
            cad_operation="rebuild",
            status="RUNNING",
            progress=5,
            started_at=started_at,
            log_path=str(log_path),
            before_hash=None,
            worker_id=worker_id,
            attempt=attempt,
        ) is False:
            raise PlanningError("CAD_JOB_LEASE_LOST", "CAD Worker 已失去任务租约")
        output = ""
        phase = "重建布局并读取布局 Handle"
        before_hash: str | None = None
        try:
            group_dir = unit.staging_dir / f"group-{group_index:03d}"
            group_dir.mkdir(parents=True, exist_ok=True)
            staged = group_dir / target.name
            shutil.copy2(unit.source_snapshot, staged)
            before_hash = file_sha256(source_target) if source_target is not None else None
            rebuild_script.write_text(self.renderer.render_rebuild(capability.plugin, group["layouts"]), encoding="mbcs")
            completed = self.executor.run(capability, staged, rebuild_script, unit.timeout)
            peak_memory = completed.peak_memory_bytes
            output += self._format_console_output(phase, completed.stdout, completed.stderr)
            log_path.write_text(sanitize_log_text(output), encoding="utf-8")
            handles = parse_handles(staged.with_suffix(".dst-handles.txt").read_text(encoding="utf-8"))
            expected = {layout["target_layout"] for layout in group["layouts"]}
            if set(handles) != expected:
                raise ValueError(f"HANDLE_LAYOUT_MISMATCH: expected={sorted(expected)!r}, actual={sorted(handles)!r}")
            if any(handle == "0" for handle in handles.values()):
                raise ValueError("HANDLE_OUTPUT_INVALID")
            bindings = {layout["sheet_id"]: {"file": str(target), "layout": layout["target_layout"], "handle": handles[layout["target_layout"]]} for layout in group["layouts"]}
            duration_ms = int((time.perf_counter() - started) * 1000)
            staging_bytes = staged.stat().st_size
            if self.database.upsert_job_file(job_id, target, cad_operation="rebuild", status="SUCCEEDED", progress=100, duration_ms=duration_ms, peak_memory_bytes=peak_memory, staging_bytes=staging_bytes, finished_at=datetime.now(UTC), before_hash=before_hash, result_hash=file_sha256(staged), worker_id=worker_id, attempt=attempt) is False:
                raise PlanningError("CAD_JOB_LEASE_LOST", "CAD Worker 已失去任务租约")
            return CadWorkResult(group_index, target, source_target, staged, bindings, duration_ms, log_path, peak_memory, staging_bytes)
        except Exception as exc:
            if isinstance(exc, subprocess.CalledProcessError):
                stdout = exc.stdout if exc.stdout is not None else exc.output
                output += self._format_console_output(phase, stdout, exc.stderr, exc.returncode)
            duration_ms = int((time.perf_counter() - started) * 1000)
            log_path.write_text(sanitize_log_text(output + "\n" + repr(exc)), encoding="utf-8")
            self.database.upsert_job_file(job_id, target, cad_operation="rebuild", status="FAILED", progress=0, duration_ms=duration_ms, finished_at=datetime.now(UTC), before_hash=before_hash, error_code=getattr(exc, "code", type(exc).__name__.upper()), error_detail=str(exc), worker_id=worker_id, attempt=attempt)
            raise

    def _write_staged_dst(
        self,
        workspace: Workspace,
        plan: dict[str, Any],
        bindings: dict[str, dict[str, str]],
        staging_dir: Path,
        commands: list[dict[str, Any]] | None = None,
    ) -> Path:
        references: dict[str, dict[str, str]] = {}
        rebuild_expected: dict[str, dict[str, str]] = {}
        for group in plan["groups"]:
            operation = group.get("cad_operation")
            if operation not in {"rename_only", "rebuild"}:
                raise PlanningError("CAD_OPERATION_INVALID", f"CAD 工作单元操作无效：{operation}")
            for layout in group["layouts"]:
                sheet_id = layout["sheet_id"]
                if sheet_id in references:
                    raise PlanningError("HANDLE_LAYOUT_MISMATCH", "最终计划包含重复图纸")
                reference = {
                    "file": str(Path(group["target_file"]).resolve()),
                    "layout": layout["target_layout"],
                }
                references[sheet_id] = reference
                if operation == "rebuild":
                    rebuild_expected[sheet_id] = reference
        if len(references) != sum(len(group["layouts"]) for group in plan["groups"]):
            raise PlanningError("HANDLE_LAYOUT_MISMATCH", "最终计划包含重复图纸")
        if set(bindings) != set(rebuild_expected):
            raise PlanningError("HANDLE_LAYOUT_MISMATCH", "Handle 回读结果与需要重建的最终图纸不一一对应")
        normalized_bindings: dict[str, dict[str, str]] = {}
        for sheet_id, expected_binding in rebuild_expected.items():
            binding = bindings[sheet_id]
            handle = str(binding.get("handle", "")).upper()
            try:
                handle_value = int(handle, 16)
            except ValueError as exc:
                raise PlanningError("HANDLE_OUTPUT_INVALID", f"Handle 格式无效：{sheet_id}") from exc
            if handle_value == 0:
                raise PlanningError("HANDLE_OUTPUT_INVALID", f"Handle 不得为 0：{sheet_id}")
            actual_file = str(Path(binding.get("file", "")).resolve())
            if actual_file.casefold() != expected_binding["file"].casefold() or binding.get("layout") != expected_binding["layout"]:
                raise PlanningError("HANDLE_LAYOUT_MISMATCH", f"Handle 回读绑定偏离最终计划：{sheet_id}")
            normalized_bindings[sheet_id] = {
                "file": expected_binding["file"],
                "layout": expected_binding["layout"],
                "handle": handle,
            }

        acsm = load_acsm(self.codec.decode_file(workspace.dst_path))
        acsm.apply_derived_document(derived_document_from_plan(plan))
        metadata_commands = metadata_commands_for_derived_document(commands or [])
        if metadata_commands:
            acsm.apply_metadata_commands(metadata_commands)
        acsm.apply_layout_references(references, workspace.root)
        acsm.apply_layout_bindings(normalized_bindings, workspace.root)
        handle_owners: set[tuple[str, int]] = set()
        for sheet in acsm.project(workspace.root).sheets:
            handle = sheet.layout.handle
            if not handle or not re.fullmatch(r"[0-9A-Fa-f]+", handle) or int(handle, 16) == 0:
                raise PlanningError("HANDLE_OUTPUT_INVALID", f"最终图纸 Handle 无效：{sheet.acsm_id}")
            drawing = (sheet.layout.resolved_path or Path(sheet.layout.file_name)).resolve()
            owner = (str(drawing).casefold(), int(handle, 16))
            if owner in handle_owners:
                raise PlanningError(
                    "HANDLE_DUPLICATE",
                    f"同一 DWG 包含数值重复的 Handle：{drawing}，{handle}",
                )
            handle_owners.add(owner)
        issues = acsm.validate()
        if any(issue.severity == Severity.ERROR for issue in issues):
            raise ValueError("XML_VALIDATION_FAILED")
        final_dir = staging_dir / "final-dst"
        final_dir.mkdir(parents=True, exist_ok=True)
        staged_dst = final_dir / workspace.dst_path.name
        self.codec.encode_file(acsm.to_bytes(), staged_dst)
        roundtrip = load_acsm(self.codec.decode_file(staged_dst))
        if roundtrip.semantic_bytes() != acsm.semantic_bytes():
            raise ValueError("DST_ROUNDTRIP_MISMATCH")
        return staged_dst

    @staticmethod
    def _require_source_file(path: Path, code: str) -> None:
        if not path.is_file():
            raise PlanningError(code, f"CAD 来源文件不存在：{path}")

    @staticmethod
    def _format_console_output(phase: str, stdout: str | bytes | None, stderr: str | bytes | None, returncode: int = 0) -> str:
        """将每次 Core Console 调用的两个输出流完整归档，并标记所属阶段。"""
        def text(value: str | bytes | None) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode("mbcs", errors="replace")
            return value

        return (
            f"\n===== Core Console：{phase}（退出码 {returncode}）stdout =====\n{text(stdout)}"
            f"\n===== Core Console：{phase}（退出码 {returncode}）stderr =====\n{text(stderr)}\n"
        )

    @staticmethod
    def _write_failure_log(workspace: Workspace, job_id: str, attempt: int, stdout: str, stderr: str) -> None:
        path = workspace.root / ".dst-manager" / "jobs" / job_id / f"attempt-{attempt:03d}" / "logs" / "failure.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sanitize_log_text(stdout + "\n" + stderr), encoding="utf-8")
