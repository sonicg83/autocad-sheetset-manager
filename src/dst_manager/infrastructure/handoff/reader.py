"""成果包交接验证与只读投影（SPEC-DB-001 §10，PLAN-DB-001 Task 10）。

:func:`read_handoff_package` 对 Builder 发布的 ``metadata/handoff.json`` 按
§10 六步顺序的验证部分做**纯只读**校验（步骤 1-3）：同根内路径、支持的
Schema、manifest 哈希、逐文件大小与 SHA-256、Manager 只读投影打开 DST 并
确认引用只落在 ``drawings/`` 内且与登记一致。任何失败都抛
:class:`HandoffPackageError`，绝不写盘——写库与修订证据由应用层在验证
全部通过后进行（零写入原则）。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from dst_manager.domain.models import SheetSetDocument
from dst_manager.infrastructure.acsm_xml import AcsmValidationError, load_acsm
from dst_manager.infrastructure.dst_codec import DstCodec

__all__ = [
    "DRAWINGS_DIR",
    "HANDOFF_FILE_RELATIVE",
    "MANIFEST_FILE_RELATIVE",
    "HandoffPackage",
    "HandoffPackageError",
    "read_handoff_package",
]

HANDOFF_SCHEMA = "dst-builder.handoff/v1"
MANIFEST_SCHEMA = "dst-builder.manifest/v1"
DRAWINGS_DIR = "drawings"
METADATA_DIR = "metadata"
MANIFEST_FILE_RELATIVE = "metadata/manifest.json"
HANDOFF_FILE_RELATIVE = "metadata/handoff.json"

_HEX_DIGITS = set("0123456789abcdef")
_CHUNK = 1024 * 1024


class HandoffPackageError(Exception):
    """交接验证失败（应用层统一转换为 HANDOFF_INVALID）。"""


@dataclass(frozen=True, slots=True)
class HandoffPackage:
    """验证通过的成果包事实（只读投影结果随附）。"""

    root: Path
    handoff_path: Path
    package_id: str
    build_id: str
    plan_id: str
    manifest_sha256: str
    dst_relative: str
    dst_path: Path
    dst_sha256: str
    builder_version: str
    created_at: str
    entries: tuple[dict, ...]
    document: SheetSetDocument

    @property
    def drawing_entries(self) -> tuple[dict, ...]:
        return tuple(entry for entry in self.entries if entry["path"].startswith(f"{DRAWINGS_DIR}/"))

    @property
    def metadata_entries(self) -> tuple[dict, ...]:
        return tuple(entry for entry in self.entries if entry["path"].startswith(f"{METADATA_DIR}/"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX_DIGITS


def _invalid(message: str) -> HandoffPackageError:
    return HandoffPackageError(message)


def _relative_parts(value: object, *, field: str) -> list[str]:
    """包内相对路径解析：拒绝绝对路径、``..``、空段与反斜杠以外形式。"""
    if not isinstance(value, str) or not value or value != value.strip():
        raise _invalid(f"{field} 不是合法的包内相对路径：{value!r}")
    normalized = value.replace("\\", "/")
    pure = PureWindowsPath(normalized)
    if pure.is_absolute() or pure.drive or pure.root or normalized.startswith("/"):
        raise _invalid(f"{field} 是绝对路径，拒绝越出成果包根：{value!r}")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise _invalid(f"{field} 含空段或 ..，拒绝越出成果包根：{value!r}")
    return parts


def _walk_exact(root: Path, parts: list[str], *, field: str) -> Path:
    """按精确大小写逐段走目录：缺失、大小写不符与符号链接都拒绝。"""
    current = root
    for part in parts:
        if current.is_symlink():
            raise _invalid(f"{field} 路径含符号链接，拒绝逃逸成果包根")
        if not current.is_dir():
            raise _invalid(f"{field} 的父目录缺失：{part}")
        existing = {entry.name: entry for entry in current.iterdir()}
        entry = existing.get(part)
        if entry is None:
            folded = {name.casefold(): name for name in existing}
            if part.casefold() in folded:
                raise _invalid(
                    f"{field} 与盘上名称大小写不符：{part!r} != {folded[part.casefold()]!r}"
                )
            raise _invalid(f"{field} 指向的文件缺失：{part}")
        current = entry
    if current.is_symlink():
        raise _invalid(f"{field} 路径含符号链接，拒绝逃逸成果包根")
    root_real = Path(os.path.realpath(root))
    target_real = Path(os.path.realpath(current))
    if target_real != root_real and root_real not in target_real.parents:
        raise _invalid(f"{field} 解析后越出成果包根")
    return current


def _require_file(root: Path, parts: list[str], *, field: str) -> Path:
    path = _walk_exact(root, parts, field=field)
    if not path.is_file():
        raise _invalid(f"{field} 不是文件")
    return path


def _register_casefold(seen: dict[str, str], relative: str, *, field: str) -> None:
    key = relative.casefold()
    if key in seen:
        raise _invalid(
            f"{field} 存在大小写碰撞：{seen[key]!r} 与 {relative!r} 仅大小写不同"
        )
    seen[key] = relative


def _require_uuid(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise _invalid(f"{field} 缺失或不是字符串")
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise _invalid(f"{field} 不是合法 UUID：{value!r}") from error
    return str(parsed)


def read_handoff_package(handoff_path: Path) -> HandoffPackage:
    """按 §10 顺序验证成果包并返回包事实；失败抛 HandoffPackageError。"""
    handoff_path = Path(handoff_path)
    if not handoff_path.is_absolute():
        raise _invalid("handoff_path 必须是绝对路径")
    try:
        resolved_handoff = handoff_path.resolve()
    except OSError as error:
        raise _invalid(f"handoff.json 路径无法解析：{error}") from error
    if not resolved_handoff.is_file():
        raise _invalid(f"handoff.json 不存在：{resolved_handoff}")
    if resolved_handoff.name != "handoff.json" or resolved_handoff.parent.name != METADATA_DIR:
        raise _invalid("handoff.json 必须位于成果包的 metadata/ 目录内")
    root = resolved_handoff.parent.parent

    # 步骤 1 前置：正式成果包根只能包含 drawings/ 与 metadata/；
    # .dst-manager/ 是 Manager 接管后自身的证据目录，允许存在。
    try:
        top_level = sorted(entry.name for entry in root.iterdir())
    except OSError as error:
        raise _invalid(f"成果包根目录不可读：{error}") from error
    if top_level not in ([DRAWINGS_DIR, METADATA_DIR], [".dst-manager", DRAWINGS_DIR, METADATA_DIR]):
        raise _invalid(f"成果包根目录约定被破坏：{top_level}")

    # handoff.json 解析与 Schema
    handoff_bytes = resolved_handoff.read_bytes()
    try:
        handoff = json.loads(handoff_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise _invalid(f"handoff.json 读取失败：{error}") from error
    if not isinstance(handoff, dict):
        raise _invalid("handoff.json 必须是 JSON 对象")
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise _invalid(f"不支持的 handoff Schema：{handoff.get('schema')!r}")
    package_id = _require_uuid(handoff.get("package_id"), field="package_id")
    build_id = _require_uuid(handoff.get("build_id"), field="build_id")
    plan_id = _require_uuid(handoff.get("plan_id"), field="plan_id")
    if handoff.get("manifest_path") != MANIFEST_FILE_RELATIVE:
        raise _invalid(f"manifest_path 必须是 {MANIFEST_FILE_RELATIVE}")
    if not _is_sha256(handoff.get("manifest_sha256")):
        raise _invalid("manifest_sha256 缺失或不是 64 位十六进制")
    for field in ("created_at", "builder_version"):
        value = handoff.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _invalid(f"{field} 缺失或为空")
    dst_parts = _relative_parts(handoff.get("dst_path"), field="dst_path")
    if dst_parts[0] != DRAWINGS_DIR:
        raise _invalid(f"dst_path 必须位于 {DRAWINGS_DIR}/ 内：{handoff.get('dst_path')!r}")
    dst_relative = "/".join(dst_parts)

    seen_paths: dict[str, str] = {}
    _register_casefold(seen_paths, HANDOFF_FILE_RELATIVE, field="成果包文件")
    _register_casefold(seen_paths, MANIFEST_FILE_RELATIVE, field="成果包文件")
    _require_file(root, [METADATA_DIR, "handoff.json"], field="handoff.json")
    manifest_path = _require_file(root, [METADATA_DIR, "manifest.json"], field="manifest.json")

    # 步骤 2：manifest 哈希 → 每文件大小与 SHA-256
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        raise _invalid(f"manifest.json 读取失败：{error}") from error
    if _sha256_bytes(manifest_bytes) != handoff["manifest_sha256"]:
        raise _invalid("manifest.json 哈希与 handoff.json 登记不符")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise _invalid(f"manifest.json 读取失败：{error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise _invalid(f"不支持的 manifest Schema：{manifest.get('schema')!r}")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise _invalid("manifest.files 缺失或为空")
    paths: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise _invalid("manifest.files 条目必须是对象")
        parts = _relative_parts(entry.get("path"), field="manifest 登记路径")
        relative = "/".join(parts)
        if parts[0] not in (DRAWINGS_DIR, METADATA_DIR):
            raise _invalid(f"manifest 登记路径越出成果包约定：{relative}")
        if relative in (MANIFEST_FILE_RELATIVE, HANDOFF_FILE_RELATIVE):
            raise _invalid(f"manifest 不得登记 {relative}")
        _register_casefold(seen_paths, relative, field="manifest 登记路径")
        size = entry.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise _invalid(f"manifest 登记的 size 非法：{relative}")
        if not _is_sha256(entry.get("sha256")):
            raise _invalid(f"manifest 登记的 sha256 非法：{relative}")
        if not isinstance(entry.get("role"), str) or not entry["role"]:
            raise _invalid(f"manifest 登记的 role 非法：{relative}")
        paths.append(relative)
    if paths != sorted(paths):
        raise _invalid("manifest.files 未按路径字典序排列")
    if len(set(paths)) != len(paths):
        raise _invalid("manifest.files 存在重复登记")
    verified: list[dict] = []
    for entry in entries:
        candidate = _require_file(root, entry["path"].replace("\\", "/").split("/"), field="manifest 登记文件")
        if candidate.stat().st_size != entry["size"]:
            raise _invalid(f"manifest 登记文件大小不符：{entry['path']}")
        if _sha256_file(candidate) != entry["sha256"]:
            raise _invalid(f"manifest 登记文件 SHA-256 不符：{entry['path']}")
        verified.append(dict(entry))

    # 成果包内不得存在未登记文件（manifest 列出除自身与 handoff 外全部正式文件）
    registered = set(paths) | {MANIFEST_FILE_RELATIVE, HANDOFF_FILE_RELATIVE}
    actual: set[str] = set()
    for directory in (DRAWINGS_DIR, METADATA_DIR):
        for path in (root / directory).rglob("*"):
            if path.is_file():
                actual.add(path.relative_to(root).as_posix())
    unregistered = sorted(actual - registered)
    if unregistered:
        raise _invalid(f"成果包存在未登记文件：{unregistered[0]}")

    # 说明：package_id 与 manifest 哈希的派生关系（§9）不在此校验——§10 要求
    # 「相同 package_id + 不同 manifest 哈希」能够通过验证并落入
    # HANDOFF_ID_CONFLICT，冲突裁决由应用层的来源记录比较完成。

    # 步骤 3：Manager 只读投影打开 DST，引用只落 drawings/ 内且与登记一致
    dst_entry = next((item for item in verified if item["path"] == dst_relative), None)
    if dst_entry is None:
        raise _invalid(f"dst_path 未登记于 manifest：{dst_relative}")
    dst_path = _require_file(root, dst_parts, field="DST")
    dst_sha256 = _sha256_file(dst_path)
    if dst_sha256 != dst_entry["sha256"]:
        raise _invalid("DST 哈希与 manifest 登记不符")
    try:
        document = load_acsm(DstCodec().decode_file(dst_path)).project(dst_path.parent)
    except (AcsmValidationError, OSError, ValueError) as error:
        raise _invalid(f"DST 只读投影失败：{error}") from error
    report = document.repair_report
    if report is not None and report.status not in ("VALID", "REPAIRED"):
        raise _invalid(f"DST 结构校验未通过：{report.status}")
    registered_real = {Path(os.path.realpath(root / item["path"])) for item in verified}
    drawings_real = Path(os.path.realpath(root / DRAWINGS_DIR))
    for sheet in document.sheets:
        resolved = sheet.layout.resolved_path
        if resolved is None:
            raise _invalid(f"DST 布局引用无法解析：{sheet.number}")
        resolved_real = Path(os.path.realpath(resolved))
        if resolved_real != drawings_real and drawings_real not in resolved_real.parents:
            raise _invalid(f"DST 引用越出 {DRAWINGS_DIR}/：{sheet.layout.relative_file_name!r}")
        if resolved_real not in registered_real:
            raise _invalid(f"DST 引用与 manifest 登记不一致：{sheet.layout.relative_file_name!r}")

    return HandoffPackage(
        root=root,
        handoff_path=resolved_handoff,
        package_id=package_id,
        build_id=build_id,
        plan_id=plan_id,
        manifest_sha256=handoff["manifest_sha256"],
        dst_relative=dst_relative,
        dst_path=dst_path,
        dst_sha256=dst_sha256,
        builder_version=handoff["builder_version"],
        created_at=handoff["created_at"],
        entries=tuple(verified),
        document=document,
    )
