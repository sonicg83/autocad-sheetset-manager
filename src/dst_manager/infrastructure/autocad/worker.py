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
    "LayoutCreationError",
    "LayoutCreationOutcome",
    "LayoutCreationRequest",
    "LayoutCreationWorker",
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


@dataclass(frozen=True, slots=True)
class LayoutCreationRequest:
    """一个图纸组的固定布局创建请求：模板图幅 → 组内每张 Sheet 的计划布局。

    只由受控创建流程构造；字段在构造时按 ``encode_scr_argument`` 同一套不安全
    字符判定校验，脚本内容由 :meth:`ScriptRenderer.render_create_layouts` 固定
    渲染——调用方无法拼接自由 SCR，也无法把用户文本直接拼进命令行。
    """

    layout_template: Path
    paper_layout: str
    target_layouts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.paper_layout or not self.target_layouts:
            raise ValueError("LAYOUT_CREATION_REQUEST_INVALID")
        keys = [name.casefold() for name in self.target_layouts]
        if len(keys) != len(set(keys)):
            raise ValueError("LAYOUT_CREATION_REQUEST_INVALID")
        try:
            for value in (
                str(self.layout_template),
                self.paper_layout,
                *self.target_layouts,
            ):
                encode_scr_argument(value)
        except ValueError:
            raise ValueError("LAYOUT_CREATION_REQUEST_INVALID") from None


@dataclass(frozen=True, slots=True)
class LayoutCreationOutcome:
    """一次固定布局创建的回读结果：完整布局名与非零唯一 Handle。"""

    layouts: tuple[str, ...]
    handles: dict[str, str]


class LayoutCreationError(ValueError):
    """固定布局创建的请求/回读失败；``code`` 为稳定错误码。"""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


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

    def render_create_layouts(
        self, capability: "CadCapability", request: LayoutCreationRequest
    ) -> str:
        """固定布局创建脚本：删旧布局 → 逐张导入模板图幅并改名 → 回读 Handle。

        与 ``render_rebuild`` 同一套已验证的 ``-LAYOUT`` 步骤（导入后立即改名，
        避免同一模板布局名重复），但不接受调用方提供的自由参数：模板路径、图幅
        与目标布局名都来自已校验的 :class:`LayoutCreationRequest`。
        """
        lines = [
            "FILEDIA",
            "0",
            "SECURELOAD",
            "0",
            "CMDECHO",
            "0",
            "_.NETLOAD",
            encode_scr_argument(str(capability.plugin)),
            "DstDeleteLayouts",
        ]
        temporary_names: list[str] = []
        for index in range(len(request.target_layouts)):
            temporary_name = f"DST_CREATE_{index:04d}"
            temporary_names.append(temporary_name)
            lines.extend(
                [
                    "_.-LAYOUT",
                    "_Template",
                    encode_scr_argument(str(request.layout_template)),
                    encode_scr_argument(request.paper_layout),
                ]
            )
            lines.extend(
                [
                    "_.-LAYOUT",
                    "_Rename",
                    encode_scr_argument(request.paper_layout),
                    temporary_name,
                ]
            )
        for temporary_name, target_layout in zip(
            temporary_names, request.target_layouts, strict=True
        ):
            lines.extend(
                ["_.-LAYOUT", "_Rename", temporary_name, encode_scr_argument(target_layout)]
            )
        lines.extend(
            [
                "_.-LAYOUT",
                "_Set",
                encode_scr_argument(request.target_layouts[0]),
                "DstDeleteDefaultLayout",
                "DstGetLayoutHandles",
                "CMDECHO",
                "1",
                "FILEDIA",
                "1",
                "_.QSAVE",
                "_.QUIT",
            ]
        )
        return "\n".join(lines) + "\n"


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


class LayoutCreationWorker:
    """固定请求的布局创建工作单元：脚本渲染、Core Console 执行与结果回读。

    只接受 :class:`LayoutCreationRequest`（无自由 SCR 拼接），只读写调用方给定的
    图纸副本与 sidecar；renderer/executor 可注入替身，因此非 CAD 环境下的测试
    不会启动 AutoCAD。
    """

    def __init__(
        self,
        capability: CadCapability,
        *,
        renderer: ScriptRenderer | None = None,
        executor: CoreConsoleExecutor | None = None,
    ) -> None:
        self.capability = capability
        self.renderer = renderer if renderer is not None else ScriptRenderer()
        self.executor = executor if executor is not None else CoreConsoleExecutor()

    def layout_names(self, drawing: Path, work_dir: Path, timeout: int) -> tuple[str, ...]:
        """固定只读枚举：在给定副本上读取完整布局名（不含 ``Model``）。"""
        script = self.renderer.render_layout_names(self.capability, work_dir)
        self.executor.run(self.capability, drawing, script, timeout)
        try:
            return tuple(parse_layout_names(drawing.with_suffix(".dst-layout-names.json")))
        except RuntimeError as exc:
            raise LayoutCreationError(getattr(exc, "code", "LAYOUT_READ_FAILED"), str(exc)) from exc

    def create_layouts(
        self,
        drawing: Path,
        request: LayoutCreationRequest,
        script_path: Path,
        timeout: int,
    ) -> LayoutCreationOutcome:
        """固定请求：导入模板图幅、为组内每张 Sheet 建计划布局并回读 Handle。"""
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(
            self.renderer.render_create_layouts(self.capability, request), encoding="mbcs"
        )
        self.executor.run(self.capability, drawing, script_path, timeout)
        try:
            text = drawing.with_suffix(".dst-handles.txt").read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise LayoutCreationError("LAYOUT_READ_FAILED", str(exc)) from exc
        try:
            handles = parse_handles(text)
        except ValueError as exc:
            raise LayoutCreationError("HANDLE_OUTPUT_INVALID", str(exc)) from exc
        if any(int(handle, 16) == 0 for handle in handles.values()):
            raise LayoutCreationError("HANDLE_OUTPUT_INVALID", "布局 Handle 不得为 0")
        return LayoutCreationOutcome(tuple(handles), handles)
