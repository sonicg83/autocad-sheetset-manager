"""AutoCAD Core Console Worker：SCR 渲染、sidecar 协议与能力描述。

进程执行原语（``CoreConsoleExecutor``/``CoreConsoleRequest``/``CoreConsoleResult``、
日志解码 ``decode_console_output`` 与 ``sanitize_log_text``）所有权已迁至
``dst_platform.autocad.process``（PLAN-DB-001 Task 6）；本模块的
``CoreConsoleExecutor`` 是 Manager 兼容适配器，保留既有
``run(capability, drawing, script, timeout)`` 签名并委托共享执行器。
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from dst_platform.autocad.process import (
    CoreConsoleExecutor as _PlatformCoreConsoleExecutor,
)
from dst_platform.autocad.process import (
    CoreConsoleRequest,
    CoreConsoleResult,
    decode_console_output,
)

__all__ = [
    "CadCapability",
    "CoreConsoleExecutor",
    "CoreConsoleRequest",
    "CoreConsoleResult",
    "ScriptRenderer",
    "decode_console_output",
    "encode_scr_argument",
    "parse_handles",
    "parse_layout_names",
    "parse_rename_result",
    "rename_request_path",
    "rename_result_path",
    "write_rename_request",
]

_UNSAFE = re.compile(r"[\r\n\x00-\x1f\"]")


def encode_scr_argument(value: str) -> str:
    if not value or _UNSAFE.search(value):
        raise ValueError("SCR_ARGUMENT_UNSAFE")
    return f'"{value}"' if " " in value else value


def rename_request_path(drawing: Path) -> Path:
    return drawing.with_suffix(".dst-layout-rename-request.json")


def rename_result_path(drawing: Path) -> Path:
    return drawing.with_suffix(".dst-layout-rename-result.json")


def write_rename_request(drawing: Path, layouts: list[dict[str, str]]) -> Path:
    try:
        rows = [
            {"old_name": item["original_layout"], "new_name": item["target_layout"]}
            for item in layouts
        ]
    except (KeyError, TypeError):
        raise ValueError("LAYOUT_RENAME_REQUEST_INVALID") from None

    if (
        not rows
        or any(
            not isinstance(item["old_name"], str)
            or not isinstance(item["new_name"], str)
            or not item["old_name"]
            or not item["new_name"]
            for item in rows
        )
    ):
        raise ValueError("LAYOUT_RENAME_REQUEST_INVALID")

    old_keys = [item["old_name"].casefold() for item in rows]
    new_keys = [item["new_name"].casefold() for item in rows]
    if len(old_keys) != len(set(old_keys)) or len(new_keys) != len(set(new_keys)):
        raise ValueError("LAYOUT_RENAME_REQUEST_INVALID")

    path = rename_request_path(drawing)
    path.write_text(json.dumps({"version": 1, "layouts": rows}, ensure_ascii=False), encoding="utf-8")
    return path


def parse_rename_result(text: str, expected_layouts: set[str]) -> int:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("LAYOUT_RENAME_RESULT_INVALID") from None

    if not isinstance(payload, dict) or set(payload) != {"version", "renamed_count", "final_layouts"}:
        raise ValueError("LAYOUT_RENAME_RESULT_INVALID")
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise ValueError("LAYOUT_RENAME_RESULT_INVALID")

    renamed_count = payload["renamed_count"]
    if type(renamed_count) is not int or renamed_count < 0:
        raise ValueError("LAYOUT_RENAME_RESULT_INVALID")

    final_layouts = payload["final_layouts"]
    if not isinstance(final_layouts, list) or not all(isinstance(name, str) and name for name in final_layouts):
        raise ValueError("LAYOUT_RENAME_RESULT_INVALID")
    layout_keys = [name.casefold() for name in final_layouts]
    if len(layout_keys) != len(set(layout_keys)) or set(final_layouts) != expected_layouts:
        raise ValueError("LAYOUT_RENAME_RESULT_INVALID")
    return renamed_count


class ScriptRenderer:
    def render_rename(self, plugin: Path) -> str:
        lines = [
            "FILEDIA",
            "0",
            "SECURELOAD",
            "0",
            "CMDECHO",
            "0",
            "_.NETLOAD",
            encode_scr_argument(str(plugin)),
            "DstRenameLayouts",
            "CMDECHO",
            "1",
            "FILEDIA",
            "1",
            "SECURELOAD",
            "1",
            "_.QSAVE",
            "_.QUIT",
        ]
        return "\n".join(lines) + "\n"

    def render_rebuild(self, plugin: Path, layouts: list[dict[str, str]]) -> str:
        lines = ["FILEDIA", "0", "SECURELOAD", "0", "CMDECHO", "0", "_.NETLOAD", encode_scr_argument(str(plugin)), "DstDeleteLayouts"]
        temporary_names = []
        for index, layout in enumerate(layouts):
            temporary_name = f"DST_TMP_{index:04d}"
            temporary_names.append(temporary_name)
            lines.extend(["_.-LAYOUT", "_Template", encode_scr_argument(layout["source_file"]), encode_scr_argument(layout["source_layout"])])
            lines.extend(["_.-LAYOUT", "_Rename", encode_scr_argument(layout["source_layout"]), temporary_name])
        for temporary_name, layout in zip(temporary_names, layouts, strict=True):
            lines.extend(["_.-LAYOUT", "_Rename", temporary_name, encode_scr_argument(layout["target_layout"])])
        if layouts:
            lines.extend(["_.-LAYOUT", "_Set", encode_scr_argument(layouts[0]["target_layout"])])
        lines.append("DstDeleteDefaultLayout")
        lines.append("DstGetLayoutHandles")
        lines.extend(["CMDECHO", "1", "FILEDIA", "1", "_.QSAVE", "_.QUIT"])
        return "\n".join(lines) + "\n"

    def render_handles(self, plugin: Path) -> str:
        return "\n".join(["FILEDIA", "0", "SECURELOAD", "0", "CMDECHO", "0", "_.NETLOAD", encode_scr_argument(str(plugin)), "DstGetLayoutHandles", "_.QSAVE", "_.QUIT"]) + "\n"

    def render_layout_names(self, capability: "CadCapability", work_dir: Path) -> Path:
        script = work_dir / "layout-names.scr"
        lines = [
            "FILEDIA 0",
            "SECURELOAD 0",
            f"_.NETLOAD {encode_scr_argument(str(capability.plugin))}",
            "DstGetLayoutNames",
        ]
        script.write_text("\n".join(lines) + "\n", encoding="mbcs")
        return script


def parse_handles(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        name, handle = (part.strip() for part in line.split("=", 1))
        if not name or not re.fullmatch(r"[0-9A-Fa-f]+", handle) or name in result or handle.upper() in {value.upper() for value in result.values()}:
            raise ValueError("HANDLE_OUTPUT_INVALID")
        result[name] = handle.upper()
    if not result:
        raise ValueError("HANDLE_OUTPUT_EMPTY")
    return result


def parse_layout_names(path: Path) -> list[str]:
    from dst_manager.application.service import ApplicationError

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ApplicationError("LAYOUT_READ_FAILED", f"布局清单读取失败：{path}") from None
    if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload.get("version") != 1:
        raise ApplicationError("LAYOUT_READ_FAILED", f"不支持的布局清单版本：{path}")
    layouts = payload.get("layouts")
    if not isinstance(layouts, list) or not all(isinstance(name, str) and name for name in layouts):
        raise ApplicationError("LAYOUT_READ_FAILED", f"布局清单内容无效：{path}")
    return list(layouts)


@dataclass(slots=True)
class CadCapability:
    version: str
    console: Path | None
    plugin: Path | None

    @property
    def available(self) -> bool:
        return bool(self.console and self.console.is_file() and self.plugin and self.plugin.is_file())


class CoreConsoleExecutor:
    """Manager 兼容适配器：能力检查与错误码保持原样，进程执行委托共享实现。"""

    def __init__(self) -> None:
        self._executor = _PlatformCoreConsoleExecutor()

    def run(self, capability: CadCapability, drawing: Path, script: Path, timeout: int) -> CoreConsoleResult:
        if not capability.available:
            raise RuntimeError(f"CAD_CAPABILITY_UNAVAILABLE: {capability.version}")
        return self._executor.run(
            CoreConsoleRequest(console=capability.console, drawing=drawing, script=script, timeout=timeout)
        )
