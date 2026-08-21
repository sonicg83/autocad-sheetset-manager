import ctypes
import hashlib
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PublishRolledBackError(RuntimeError):
    code = "PUBLISH_ROLLED_BACK"


class PublishRecoveryError(RuntimeError):
    code = "PUBLISH_RECOVERY_FAILED"


class PublishBaselineError(RuntimeError):
    code = "PUBLISH_BASE_CHANGED"


class RecoverablePublisher:
    """以before快照和同步日志提供多文件可恢复发布。"""

    def __init__(self, replace_file: Callable[[Path, Path], None] | None = None):
        self._replace_file = replace_file

    @staticmethod
    def _move_no_replace(source: Path, target: Path) -> None:
        if os.name != "nt":
            os.link(source, target)
            source.unlink()
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move_file = kernel32.MoveFileW
        move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        move_file.restype = ctypes.c_int
        ctypes.set_last_error(0)
        if not move_file(str(source), str(target)):
            raise ctypes.WinError(ctypes.get_last_error())

    @staticmethod
    def _replace_existing(source: Path, target: Path, backup: Path) -> None:
        if backup.exists():
            raise FileExistsError(f"PUBLISH_REPLACE_BACKUP_EXISTS: {backup}")
        if os.name != "nt":
            os.replace(target, backup)
            try:
                os.replace(source, target)
            except Exception:
                os.replace(backup, target)
                raise
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        replace_file = kernel32.ReplaceFileW
        replace_file.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        replace_file.restype = ctypes.c_int
        ctypes.set_last_error(0)
        if not replace_file(str(target), str(source), str(backup), 0x2, None, None):
            raise ctypes.WinError(ctypes.get_last_error())

    def publish(
        self,
        operation_id: str,
        workspace_root: Path,
        staged: dict[Path, Path | None],
        *,
        expected_baselines: dict[Path, str | None] | None = None,
    ) -> Path:
        workspace_root = workspace_root.resolve()
        staged = {target.resolve(): staged_file for target, staged_file in staged.items()}
        if expected_baselines is None:
            baselines = {
                target: file_sha256(target) if target.exists() else None
                for target in staged
            }
        else:
            baselines = {target.resolve(): expected for target, expected in expected_baselines.items()}
            if baselines.keys() != staged.keys():
                raise ValueError("PUBLISH_BASELINE_TARGET_MISMATCH")
        self._verify_baselines(baselines)
        manager_dir = workspace_root / ".dst-manager"
        revision_dir = manager_dir / "revisions" / operation_id
        before_dir = revision_dir / "before"
        journal_path = manager_dir / "jobs" / operation_id / "publish-journal.json"
        before_dir.mkdir(parents=True, exist_ok=False)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        for target, staged_file in staged.items():
            if workspace_root not in target.parents:
                raise ValueError(f"PUBLISH_OUTSIDE_WORKSPACE: {target}")
            target_existed = target.exists()
            baseline_identity = self._file_identity(target) if target_existed else None
            backup = before_dir / target.relative_to(workspace_root)
            if target_existed:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                if (
                    file_sha256(backup) != baselines[target]
                    or file_sha256(target) != baselines[target]
                    or self._file_identity(target) != baseline_identity
                ):
                    raise PublishBaselineError(f"发布前快照与预期基准不一致：{target}")
            elif staged_file is None:
                raise FileNotFoundError(f"DELETE_TARGET_NOT_FOUND: {target}")
            replace_backup = target.with_name(f".{target.name}.{operation_id}.replaced")
            if replace_backup.exists():
                raise FileExistsError(f"PUBLISH_REPLACE_BACKUP_EXISTS: {replace_backup}")
            entries.append(
                {
                    "target": str(target),
                    "staged": str(staged_file) if staged_file else None,
                    "backup": str(backup) if target_existed else None,
                    "replace_backup": str(replace_backup),
                    "before_hash": baselines[target],
                    "staged_hash": file_sha256(staged_file) if staged_file else None,
                    "baseline_identity": baseline_identity,
                    "before_identity": self._file_identity(backup) if target_existed else None,
                    "staged_identity": self._file_identity(staged_file) if staged_file else None,
                    "expected_backup_identity": baseline_identity,
                    "publish_identity": None,
                    "replace_backup_identity": None,
                    "attempted": False,
                    "replaced": False,
                    "api_failed": False,
                    "conflict_preserved": False,
                },
            )
        journal = {
            "identity_version": 1,
            "operation_id": operation_id,
            "status": "PREPARED",
            "files": entries,
        }
        self._write_journal(journal_path, journal)
        try:
            journal["status"] = "PUBLISHING"
            self._write_journal(journal_path, journal)
            self._verify_baselines(baselines)
            for entry in entries:
                target = Path(entry["target"])
                self._verify_entry_baseline(entry)
                if entry["staged"] is None:
                    entry["attempted"] = True
                    self._write_journal(journal_path, journal)
                    self._commit_delete(entry)
                else:
                    staged_file = Path(entry["staged"])
                    publish_temp = target.with_name(f".{target.name}.{operation_id}.tmp")
                    shutil.copy2(staged_file, publish_temp)
                    if file_sha256(publish_temp) != entry["staged_hash"]:
                        raise PublishBaselineError(f"发布暂存文件已偏离计划内容：{staged_file}")
                    entry["publish_identity"] = self._file_identity(publish_temp)
                    entry["attempted"] = True
                    self._write_journal(journal_path, journal)
                    if entry["before_hash"] is None:
                        self._commit_create(entry, publish_temp)
                    else:
                        self._commit_existing(entry, publish_temp, operation_id)
                self._capture_result(entry)
                entry["replaced"] = True
                self._write_journal(journal_path, journal)
            self._cleanup_replace_backups(entries)
            journal["status"] = "COMMITTED"
            self._write_journal(journal_path, journal)
            (revision_dir / "manifest.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
            shutil.copy2(journal_path, revision_dir / "publish-journal.json")
            return revision_dir
        except PublishBaselineError as publish_error:
            self._write_journal(journal_path, journal)
            if any(entry["replaced"] or entry["attempted"] for entry in entries):
                try:
                    self._rollback(journal_path, journal, entries)
                except Exception as recovery_error:  # noqa: BLE001 - 基准冲突后的恢复故障必须显式终止
                    journal["status"] = "ROLLBACK_FAILED"
                    self._write_journal(journal_path, journal)
                    raise PublishRecoveryError(str(recovery_error)) from publish_error
            else:
                journal["status"] = "ABORTED_BASELINE_CHANGED"
                self._write_journal(journal_path, journal)
            raise
        except Exception as publish_error:
            for entry in entries:
                if entry.get("attempted") and not entry.get("replaced") and not entry.get("conflict_preserved"):
                    entry["api_failed"] = True
            self._write_journal(journal_path, journal)
            try:
                self._rollback(journal_path, journal, entries)
            except Exception as recovery_error:  # noqa: BLE001 - 任何恢复故障都必须进入可再次恢复状态
                journal["status"] = "ROLLBACK_FAILED"
                self._write_journal(journal_path, journal)
                raise PublishRecoveryError(str(recovery_error)) from publish_error
            raise PublishRolledBackError(str(publish_error)) from publish_error

    def _commit_create(self, entry: dict, publish_temp: Path) -> None:
        target = Path(entry["target"])
        try:
            if self._replace_file is None:
                self._move_no_replace(publish_temp, target)
            else:
                self._replace_file(publish_temp, target)
        except OSError as exc:
            if target.exists():
                entry["conflict_preserved"] = True
                raise PublishBaselineError(f"新建目标在原子提交前已出现：{target}") from exc
            raise
        if (
            not target.exists()
            or self._file_identity(target) != entry["publish_identity"]
            or file_sha256(target) != entry["staged_hash"]
        ):
            entry["conflict_preserved"] = True
            raise PublishBaselineError(f"新建目标提交后被外部版本替换：{target}")

    def _commit_existing(self, entry: dict, publish_temp: Path, operation_id: str) -> None:
        target = Path(entry["target"])
        if self._replace_file is not None:
            self._replace_file(publish_temp, target)
            return
        replace_backup = Path(entry["replace_backup"])
        self._replace_existing(publish_temp, target, replace_backup)
        captured_identity = self._file_identity(replace_backup)
        entry["replace_backup_identity"] = captured_identity
        captured_hash = file_sha256(replace_backup)
        if (
            captured_hash != entry["before_hash"]
            or captured_identity != entry["expected_backup_identity"]
        ):
            self._restore_captured_external(entry, operation_id, captured_identity)
            entry["conflict_preserved"] = True
            raise PublishBaselineError(f"正式替换捕获到基准后的外部版本：{target}")
        if (
            not target.exists()
            or file_sha256(target) != entry["staged_hash"]
            or self._file_identity(target) != entry["publish_identity"]
        ):
            entry["conflict_preserved"] = True
            raise PublishBaselineError(f"正式替换后目标被外部版本再次改动：{target}")

    def _commit_delete(self, entry: dict) -> None:
        target = Path(entry["target"])
        replace_backup = Path(entry["replace_backup"])
        self._move_no_replace(target, replace_backup)
        captured_identity = self._file_identity(replace_backup)
        entry["replace_backup_identity"] = captured_identity
        if (
            file_sha256(replace_backup) != entry["before_hash"]
            or captured_identity != entry["expected_backup_identity"]
        ):
            try:
                self._move_no_replace(replace_backup, target)
            except OSError as recovery_error:
                entry["conflict_preserved"] = True
                raise PublishRecoveryError(f"外部版本已保存在 {replace_backup}：{target}") from recovery_error
            entry["conflict_preserved"] = True
            raise PublishBaselineError(f"正式删除捕获到基准后的外部版本：{target}")
        if target.exists():
            entry["conflict_preserved"] = True
            raise PublishBaselineError(f"正式删除后目标被外部版本再次创建：{target}")

    def _restore_captured_external(
        self,
        entry: dict,
        operation_id: str,
        captured_identity: list[int],
    ) -> None:
        target = Path(entry["target"])
        captured_external = Path(entry["replace_backup"])
        if (
            not target.exists()
            or file_sha256(target) != entry["staged_hash"]
            or self._file_identity(target) != entry["publish_identity"]
        ):
            raise PublishRecoveryError(f"外部版本已保存在 {captured_external}，目标又发生变化：{target}")
        displaced_publish = target.with_name(f".{target.name}.{operation_id}.conflict-published")
        self._replace_existing(captured_external, target, displaced_publish)
        if (
            not target.exists()
            or self._file_identity(target) != captured_identity
            or self._file_identity(displaced_publish) != entry["publish_identity"]
        ):
            raise PublishRecoveryError(f"恢复外部版本时目标再次变化：{target}")
        self._unlink_owned(displaced_publish, entry["publish_identity"], recovery=True)

    def _verify_entry_baseline(self, entry: dict) -> None:
        target = Path(entry["target"])
        before_hash = entry["before_hash"]
        if before_hash is None:
            if target.exists():
                raise PublishBaselineError(f"发布目标已偏离预期基准：{target}")
            return
        if (
            not target.exists()
            or file_sha256(target) != before_hash
            or self._file_identity(target) != entry["baseline_identity"]
        ):
            raise PublishBaselineError(f"发布目标已偏离预期基准：{target}")

    def _capture_result(self, entry: dict) -> None:
        target = Path(entry["target"])
        if entry["staged"] is None:
            if target.exists():
                entry["conflict_preserved"] = True
                raise PublishBaselineError(f"正式删除结果复核时目标被外部版本创建：{target}")
            entry["result_hash"] = None
            entry["result_identity"] = None
            return
        if (
            not target.exists()
            or file_sha256(target) != entry["staged_hash"]
            or self._file_identity(target) != entry["publish_identity"]
        ):
            entry["conflict_preserved"] = True
            raise PublishBaselineError(f"正式发布结果复核时目标身份已变化：{target}")
        entry["result_hash"] = entry["staged_hash"]
        entry["result_identity"] = entry["publish_identity"]

    @staticmethod
    def _verify_baselines(baselines: dict[Path, str | None]) -> None:
        for target, expected in baselines.items():
            actual = file_sha256(target) if target.exists() else None
            if actual != expected:
                raise PublishBaselineError(f"发布目标已偏离预期基准：{target}")

    def _rollback(self, journal_path: Path, journal: dict, entries: list[dict]) -> None:
        journal["status"] = "ROLLING_BACK"
        self._write_journal(journal_path, journal)
        for entry in reversed(entries):
            if entry.get("conflict_preserved"):
                continue
            if entry.get("replaced") or entry.get("attempted"):
                self._restore_entry(entry, journal["operation_id"])
        journal["status"] = "ROLLED_BACK"
        self._write_journal(journal_path, journal)

    def _restore_entry(self, entry: dict, operation_id: str) -> None:
        target = Path(entry["target"])
        before_hash = entry.get("before_hash")
        if before_hash is None:
            if not target.exists():
                return
            current_identity = self._file_identity(target)
            if current_identity not in self._published_identities(entry):
                raise PublishRecoveryError(f"回滚时新建目标已被外部版本替换：{target}")
            self._unlink_owned(target, current_identity, recovery=True)
            return

        baseline_identity = entry.get("baseline_identity")
        if baseline_identity is None:
            raise PublishRecoveryError(f"PUBLISH_IDENTITY_MISSING: {target}")
        replacement_backup = self._checked_replacement_backup(entry, before_hash)
        if not target.exists():
            is_delete = entry.get("staged") is None
            if replacement_backup is None or (not is_delete and not entry.get("api_failed")):
                raise PublishRecoveryError(f"回滚时既有目标缺失且无法证明属于本批：{target}")
            self._move_no_replace(replacement_backup, target)
            if self._file_identity(target) != baseline_identity:
                raise PublishRecoveryError(f"回滚时原始目标身份不一致：{target}")
            return

        current_identity = self._file_identity(target)
        if current_identity == baseline_identity:
            return
        if current_identity not in self._published_identities(entry):
            raise PublishRecoveryError(f"回滚时既有目标已被外部版本替换：{target}")
        backup = replacement_backup or self._checked_before_snapshot(entry, before_hash)
        source = backup
        restored_exact_identity = replacement_backup is not None
        if replacement_backup is None:
            restore_temp = target.with_name(f".{target.name}.{operation_id}.restore")
            shutil.copy2(backup, restore_temp)
            source = restore_temp
        displaced = target.with_name(f".{target.name}.{operation_id}.rollback-displaced")
        try:
            self._replace_existing(source, target, displaced)
        except OSError:
            if (
                replacement_backup is None
                or displaced.exists()
                or not target.exists()
                or self._file_identity(target) != current_identity
                or self._file_identity(replacement_backup) != baseline_identity
            ):
                raise
            restore_temp = target.with_name(f".{target.name}.{operation_id}.restore")
            shutil.copy2(replacement_backup, restore_temp)
            self._replace_existing(restore_temp, target, displaced)
            restored_exact_identity = False
        if self._file_identity(displaced) != current_identity:
            raise PublishRecoveryError(f"回滚原子替换期间目标再次变化：{target}")
        if restored_exact_identity and self._file_identity(target) != baseline_identity:
            raise PublishRecoveryError(f"回滚后原始目标身份不一致：{target}")
        if file_sha256(target) != before_hash:
            raise PublishRecoveryError(f"回滚后原始目标内容不一致：{target}")
        self._unlink_owned(displaced, current_identity, recovery=True)

    def _checked_replacement_backup(self, entry: dict, before_hash: str) -> Path | None:
        raw_path = entry.get("replace_backup")
        if not raw_path or not (path := Path(raw_path)).exists():
            return None
        expected_identity = entry.get("replace_backup_identity") or entry.get("expected_backup_identity")
        if expected_identity is None:
            raise PublishRecoveryError(f"PUBLISH_BACKUP_IDENTITY_MISSING: {entry['target']}")
        if self._file_identity(path) != expected_identity or file_sha256(path) != before_hash:
            raise PublishRecoveryError(f"PUBLISH_REPLACEMENT_BACKUP_CHANGED: {entry['target']}")
        return path

    def _checked_before_snapshot(self, entry: dict, before_hash: str) -> Path:
        raw_path = entry.get("backup")
        expected_identity = entry.get("before_identity")
        if not raw_path or expected_identity is None:
            raise PublishRecoveryError(f"PUBLISH_BACKUP_IDENTITY_MISSING: {entry['target']}")
        path = Path(raw_path)
        if (
            not path.exists()
            or self._file_identity(path) != expected_identity
            or file_sha256(path) != before_hash
        ):
            raise PublishRecoveryError(f"PUBLISH_BACKUP_CORRUPTED: {entry['target']}")
        return path

    @staticmethod
    def _published_identities(entry: dict) -> list[list[int]]:
        return [
            identity
            for identity in (entry.get("publish_identity"), entry.get("result_identity"))
            if identity is not None
        ]

    @staticmethod
    def _file_identity(path: Path) -> list[int]:
        stat = path.stat()
        return [stat.st_dev, stat.st_ino]

    def _cleanup_replace_backups(self, entries: list[dict]) -> None:
        for entry in entries:
            replace_backup = Path(entry["replace_backup"])
            if not replace_backup.exists():
                continue
            expected_identity = entry.get("replace_backup_identity") or entry.get("expected_backup_identity")
            if expected_identity is None or self._file_identity(replace_backup) != expected_identity:
                raise PublishBaselineError(f"清理替换备份时文件身份已变化：{replace_backup}")
            self._unlink_owned(replace_backup, expected_identity, recovery=False)

    def _unlink_owned(self, path: Path, expected_identity: list[int], *, recovery: bool) -> None:
        error_type = PublishRecoveryError if recovery else PublishBaselineError
        if os.name != "nt":
            if self._file_identity(path) != expected_identity:
                raise error_type(f"删除前文件身份已变化：{path}")
            path.unlink()
            return

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        create_file.restype = ctypes.c_void_p
        set_file_information = kernel32.SetFileInformationByHandle
        set_file_information.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        set_file_information.restype = ctypes.c_int
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int
        ctypes.set_last_error(0)
        handle = create_file(
            str(path),
            0x00010000 | 0x00000080,
            0x00000001 | 0x00000002,
            None,
            3,
            0x80,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            raise error_type(f"无法取得待删除文件的身份锁：{path}") from ctypes.WinError(ctypes.get_last_error())
        try:
            if self._file_identity(path) != expected_identity:
                raise error_type(f"删除前文件身份已变化：{path}")
            delete_file = ctypes.c_ubyte(1)
            ctypes.set_last_error(0)
            if not set_file_information(handle, 4, ctypes.byref(delete_file), ctypes.sizeof(delete_file)):
                raise error_type(f"无法按身份删除本批文件：{path}") from ctypes.WinError(ctypes.get_last_error())
        finally:
            close_handle(handle)

    @staticmethod
    def _write_journal(path: Path, journal: dict) -> None:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)

    def _rollback_legacy_attempted(self, journal_path: Path, journal: dict) -> None:
        journal["status"] = "ROLLING_BACK"
        self._write_journal(journal_path, journal)
        for entry in reversed(journal["files"]):
            if entry.get("conflict_preserved") or not (entry.get("replaced") or entry.get("attempted")):
                continue
            target = Path(entry["target"])
            before_hash = entry.get("before_hash")
            if before_hash is None:
                if target.exists() and file_sha256(target) == entry.get("staged_hash"):
                    target.unlink()
                continue
            if target.exists() and file_sha256(target) == before_hash:
                continue
            backup = self._legacy_rollback_source(entry, before_hash)
            restore_temp = target.with_name(f".{target.name}.{journal['operation_id']}.restore")
            shutil.copy2(backup, restore_temp)
            os.replace(restore_temp, target)
        journal["status"] = "ROLLED_BACK"
        self._write_journal(journal_path, journal)

    @staticmethod
    def _legacy_rollback_source(entry: dict, before_hash: str) -> Path:
        for raw_path in (entry.get("replace_backup"), entry.get("backup")):
            if raw_path and (path := Path(raw_path)).exists() and file_sha256(path) == before_hash:
                return path
        raise PublishRecoveryError(f"PUBLISH_BACKUP_CORRUPTED: {entry['target']}")

    def recover(self, workspace_root: Path) -> list[str]:
        recovered: list[str] = []
        jobs = workspace_root / ".dst-manager" / "jobs"
        if not jobs.exists():
            return recovered
        for path in jobs.glob("*/publish-journal.json"):
            journal = json.loads(path.read_text(encoding="utf-8"))
            if journal["status"] in {"COMMITTED", "ROLLED_BACK", "ABORTED_BASELINE_CHANGED"}:
                continue
            if journal.get("identity_version") == 1:
                try:
                    self._rollback(path, journal, journal["files"])
                except Exception as recovery_error:
                    journal["status"] = "ROLLBACK_FAILED"
                    self._write_journal(path, journal)
                    raise PublishRecoveryError(str(recovery_error)) from recovery_error
                recovered.append(journal["operation_id"])
                continue
            if any("attempted" in entry for entry in journal["files"]):
                try:
                    self._rollback_legacy_attempted(path, journal)
                except Exception as recovery_error:
                    journal["status"] = "ROLLBACK_FAILED"
                    self._write_journal(path, journal)
                    raise PublishRecoveryError(str(recovery_error)) from recovery_error
                recovered.append(journal["operation_id"])
                continue
            for entry in reversed(journal["files"]):
                if entry.get("replaced"):
                    target = Path(entry["target"])
                    if entry.get("backup") is None:
                        target.unlink(missing_ok=True)
                    elif Path(entry["backup"]).exists():
                        backup = Path(entry["backup"])
                        restore_temp = target.with_name(f".{target.name}.{journal['operation_id']}.restore")
                        shutil.copy2(backup, restore_temp)
                        os.replace(restore_temp, target)
            journal["status"] = "ROLLED_BACK"
            self._write_journal(path, journal)
            recovered.append(journal["operation_id"])
        return recovered
