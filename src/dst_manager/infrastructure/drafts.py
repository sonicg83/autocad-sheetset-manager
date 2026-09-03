import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dst_manager.domain.text_validation import (
    normalize_derived_name,
    normalize_property_name,
    validate_absolute_source_file,
    validate_custom_properties,
    validate_sheet_set_name,
    validate_xml_text,
)

_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_REPAIR_STATUSES = {
    "VALID",
    "REPAIRED",
    "INVALID_REPAIR_REQUIRED",
    "INVALID_UNRECOVERABLE",
}
_COMMAND_KEYS: dict[str, tuple[set[str], set[str]]] = {
    "update_sheet_set": ({"type"}, {"name", "custom_properties"}),
    "update_subset_title": ({"type", "subset_id", "title"}, set()),
    "update_sheet_properties": ({"type", "sheet_id", "custom_properties"}, set()),
    "delete_sheet": ({"type", "sheet_id"}, set()),
    "insert_sheet": (
        {"type", "target_subset_id", "placement", "count", "source"},
        {"ordinal"},
    ),
    "insert_subset": (
        {"type", "placement", "title", "initial_sheet_count", "source"},
        {"ordinal", "base_template_file"},
    ),
    "add_custom_property": (
        {"type", "property_type", "name", "default_value"},
        set(),
    ),
    "delete_custom_property": ({"type", "property_type", "name"}, set()),
    "delete_subset": (
        {"type", "subset_id", "confirm_delete_all_sheets", "confirm_delete_main_dwg"},
        set(),
    ),
}


class DraftConflictError(RuntimeError):
    pass


class DraftStore:
    def __init__(self, root: Path):
        if not root.is_absolute():
            raise ValueError("DRAFT_DIR_NOT_ABSOLUTE")
        self.root = root.resolve()

    def load(self, workspace_id: str) -> dict[str, Any]:
        path = self._path(workspace_id)
        if not path.is_file():
            return {"draft": None, "corrupted": False}
        with self._write_lock(workspace_id):
            return self._load_unlocked(workspace_id)

    def _load_unlocked(self, workspace_id: str) -> dict[str, Any]:
        path = self._path(workspace_id)
        if not path.is_file():
            return {"draft": None, "corrupted": False}
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(draft, dict) or draft.get("workspace_id") != workspace_id:
                raise ValueError("DRAFT_CONTENT_INVALID")
            _validate_draft_document(draft)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            quarantine = self.root / (
                f"{workspace_id}.corrupt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}.json"
            )
            os.replace(path, quarantine)
            return {"draft": None, "corrupted": True}
        return {"draft": draft, "corrupted": False}

    def save(
        self,
        workspace_id: str,
        draft: dict[str, Any],
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        path = self._path(workspace_id)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._write_lock(workspace_id):
            loaded = self._load_unlocked(workspace_id)["draft"]
            current_version = int(loaded.get("version", 0)) if loaded else 0
            if current_version != expected_version:
                raise DraftConflictError(
                    f"DRAFT_VERSION_CONFLICT: expected={expected_version}, current={current_version}",
                )
            saved = dict(draft)
            saved["workspace_id"] = workspace_id
            saved["version"] = current_version + 1
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    newline="\n",
                    dir=self.root,
                    prefix=f".{workspace_id}-",
                    suffix=".tmp",
                    delete=False,
                ) as stream:
                    temporary_path = Path(stream.name)
                    json.dump(saved, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, path)
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
        return saved

    def delete(self, workspace_id: str, *, expected_version: int) -> bool:
        path = self._path(workspace_id)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._write_lock(workspace_id):
            loaded = self._load_unlocked(workspace_id)["draft"]
            current_version = int(loaded.get("version", 0)) if loaded else 0
            if current_version != expected_version:
                raise DraftConflictError(
                    f"DRAFT_VERSION_CONFLICT: expected={expected_version}, current={current_version}",
                )
            if not path.is_file():
                return False
            path.unlink()
            return True

    @contextmanager
    def _write_lock(self, workspace_id: str):
        lock_path = self.root / f".{workspace_id}.lock"
        deadline = time.monotonic() + 2.0
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        while True:
            try:
                self._lock_descriptor(descriptor)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    os.close(descriptor)
                    raise DraftConflictError("DRAFT_WRITE_LOCKED") from exc
                time.sleep(0.01)
        try:
            yield
        finally:
            self._unlock_descriptor(descriptor)
            os.close(descriptor)

    @staticmethod
    def _lock_descriptor(descriptor: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_descriptor(descriptor: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)

    def _path(self, workspace_id: str) -> Path:
        if not _WORKSPACE_ID.fullmatch(workspace_id):
            raise ValueError("DRAFT_WORKSPACE_ID_INVALID")
        return self.root / f"{workspace_id}.json"


def _is_integer(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _require_keys(
    value: dict[str, Any],
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    if not required <= value.keys() or value.keys() - required - optional:
        raise ValueError("DRAFT_CONTENT_INVALID")


def _require_text(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("DRAFT_CONTENT_INVALID")


def _require_string_map(value: object) -> None:
    if not isinstance(value, dict) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()):
        raise ValueError("DRAFT_CONTENT_INVALID")


def _validate_source(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("DRAFT_CONTENT_INVALID")  # noqa: TRY004 - 文件内容损坏统一归类
    _require_keys(value, {"type", "file", "layout"})
    if value["type"] not in {"existing_snapshot", "template_layout"}:
        raise ValueError("DRAFT_CONTENT_INVALID")
    if not isinstance(value["file"], str) or not isinstance(value["layout"], str):
        raise ValueError("DRAFT_CONTENT_INVALID")  # noqa: TRY004 - 文件内容损坏统一归类
    # existing_snapshot 来源允许空 file/layout（前端以 {type, file:"", layout:""} 提交，SPEC-DM-008 F-02）
    if value["type"] == "template_layout":
        _require_text(value["file"])
        _require_text(value["layout"])
    if value["file"]:
        validate_absolute_source_file(value["file"])
    if value["layout"]:
        normalize_derived_name(value["layout"], "布局名称")


def _validate_command(command: object) -> None:
    if not isinstance(command, dict) or not isinstance(command.get("type"), str):
        raise ValueError("DRAFT_CONTENT_INVALID")  # noqa: TRY004 - 文件内容损坏统一归类
    command_type = command["type"]
    keys = _COMMAND_KEYS.get(command_type)
    if keys is None:
        raise ValueError("DRAFT_CONTENT_INVALID")
    _require_keys(command, *keys)
    for key in {"subset_id", "target_subset_id", "sheet_id", "title", "name"} & command.keys():
        _require_text(command[key])
    if "custom_properties" in command and command["custom_properties"] is not None:
        _require_string_map(command["custom_properties"])
        validate_custom_properties(command["custom_properties"])
    if command_type == "update_sheet_set" and command.get("name") is not None:
        validate_sheet_set_name(command["name"])
    if command_type in {"update_subset_title", "insert_subset"}:
        normalize_derived_name(command["title"], "子集标题")
    if command_type == "insert_subset" and "base_template_file" in command:
        # 基础模板文件与契约同步（SPEC-DM-008 F-04）：存在则校验非空绝对路径；
        # 缺字段视为 v0.3.1 前旧草稿，可加载、预览期由 INSERT_SUBSET_BASE_TEMPLATE_INVALID 明确拒绝
        _require_text(command["base_template_file"])
        validate_absolute_source_file(command["base_template_file"])
    if command_type in {"add_custom_property", "delete_custom_property"} and command["property_type"] not in {"sheetset", "sheet"}:
        raise ValueError("DRAFT_CONTENT_INVALID")
    if command_type in {"add_custom_property", "delete_custom_property"}:
        normalize_property_name(command["name"])
    if command_type == "add_custom_property" and not isinstance(command["default_value"], str):
        raise ValueError("DRAFT_CONTENT_INVALID")
    if command_type == "add_custom_property":
        validate_xml_text(command["default_value"])
    if command_type in {"insert_sheet", "insert_subset"}:
        if command["placement"] not in {"before", "after"}:
            raise ValueError("DRAFT_CONTENT_INVALID")
        count_key = "count" if command_type == "insert_sheet" else "initial_sheet_count"
        if not _is_integer(command[count_key], minimum=1):
            raise ValueError("DRAFT_CONTENT_INVALID")
        if command.get("ordinal") is not None and not _is_integer(command["ordinal"], minimum=1):
            raise ValueError("DRAFT_CONTENT_INVALID")
        _validate_source(command["source"])
    if command_type == "delete_subset" and (
        command["confirm_delete_all_sheets"] is not True
        or command["confirm_delete_main_dwg"] is not True
    ):
        raise ValueError("DRAFT_CONTENT_INVALID")


def _validate_draft_document(draft: dict[str, Any]) -> None:
    _require_keys(
        draft,
        {
            "schema_version",
            "workspace_id",
            "base_revision_id",
            "repair_status",
            "version",
            "cursor",
            "actions",
        },
    )
    if draft["schema_version"] != 1 or draft["repair_status"] not in _REPAIR_STATUSES:
        raise ValueError("DRAFT_CONTENT_INVALID")
    _require_text(draft["workspace_id"])
    _require_text(draft["base_revision_id"])
    if not _is_integer(draft["version"]) or not _is_integer(draft["cursor"]):
        raise ValueError("DRAFT_CONTENT_INVALID")
    actions = draft["actions"]
    if not isinstance(actions, list) or draft["cursor"] > len(actions):
        raise ValueError("DRAFT_CONTENT_INVALID")
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("DRAFT_CONTENT_INVALID")  # noqa: TRY004 - 文件内容损坏统一归类
        _require_keys(action, {"id", "kind", "label", "commands"})
        _require_text(action["id"])
        _require_text(action["label"])
        if action["kind"] != "command_batch" or not isinstance(action["commands"], list) or not action["commands"]:
            raise ValueError("DRAFT_CONTENT_INVALID")
        for command in action["commands"]:
            _validate_command(command)
