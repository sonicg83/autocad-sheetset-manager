"""CadDrawingRequestV1 / CadDrawingResultV1 契约与 attempt 路径边界（SPEC-DB-001 §7）。

只承载纯数据契约、路径校验与 payload 序列化；进程执行编排在 ``drawing``，
SCR 渲染在 ``script``。所有路径约束在构造（``create`` / ``AttemptPaths``）时
完成：项目内相对路径复用 ``domain.paths.resolve_within_project``，attempt
目录内绝对路径用 ``ensure_within_directory`` 做同样的解析后 containment 检查，
任一越界以 :class:`CadDrawingRequestError`（链上原 ``ProjectPathError``）拒绝。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dst_builder.domain.models import Diagnostic, DiagnosticSeverity, DrawingTask
from dst_builder.domain.paths import ProjectPathError, resolve_within_project
from dst_platform.contracts.naming import validate_windows_file_name

__all__ = [
    "CAD_DRAWING_REQUEST_SCHEMA",
    "CAD_DRAWING_RESULT_SCHEMA",
    "CAD_INSPECT_REQUEST_SCHEMA",
    "CAD_INSPECT_RESULT_SCHEMA",
    "AttemptPaths",
    "CadDrawingRequestError",
    "CadDrawingRequestV1",
    "CadDrawingResultV1",
    "CadInspectRequestV1",
    "CadInspectResultV1",
    "CadVersion",
    "ensure_within_directory",
]

# §7 版本化契约：进入插件的请求与插件写出的结果都带 Schema，未知即阻断。
CAD_DRAWING_REQUEST_SCHEMA = "dst-builder.cad-drawing-request/v1"
CAD_DRAWING_RESULT_SCHEMA = "dst-builder.cad-drawing-result/v1"
CAD_INSPECT_REQUEST_SCHEMA = "dst-builder.cad-inspect-request/v1"
CAD_INSPECT_RESULT_SCHEMA = "dst-builder.cad-inspect-result/v1"

CadVersion = Literal["2016", "2020"]

_HANDLE_DIGITS = frozenset("0123456789abcdefABCDEF")
_DIAGNOSTIC_SEVERITIES = frozenset(item.value for item in DiagnosticSeverity)


class CadDrawingRequestError(ValueError):
    """CAD 请求/结果契约或路径边界违规（§7：进入插件前阻断）。"""


def ensure_within_directory(root: Path, candidate: Path) -> Path:
    """校验绝对路径解析后仍位于 root 内（attempt 目录版 containment）。"""
    try:
        root_resolved = Path(root).resolve()
        resolved = Path(candidate).resolve()
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        raise CadDrawingRequestError(f"路径解析后越出目录：{candidate}") from None
    return Path(candidate)


def _validated_layout_name(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise CadDrawingRequestError(f"{field} 不能为空或含首尾空白")
    try:
        validate_windows_file_name(value)
    except ValueError as error:
        raise CadDrawingRequestError(f"{field} 不合法：{error}") from error
    return value


@dataclass(frozen=True, slots=True)
class AttemptPaths:
    """一次构建 attempt 的工作目录契约：attempt 目录内的四个固定文件。

    直接构造时逐一路径校验必须位于 ``attempt_dir`` 内；常规入口是
    ``create(attempt_dir)``（按固定文件名派生）。
    """

    attempt_dir: Path
    working_dwg: Path
    request_json: Path
    result_json: Path
    script: Path

    @classmethod
    def create(cls, attempt_dir: str | Path) -> AttemptPaths:
        directory = Path(attempt_dir)
        return cls(
            attempt_dir=directory,
            working_dwg=directory / "working.dwg",
            request_json=directory / "cad-drawing-request.json",
            result_json=directory / "cad-drawing-result.json",
            script=directory / "cad-drawing.scr",
        )

    def __post_init__(self) -> None:
        for field in ("working_dwg", "request_json", "result_json", "script"):
            ensure_within_directory(self.attempt_dir, getattr(self, field))


@dataclass(frozen=True, slots=True)
class CadDrawingRequestV1:
    """§7 单 DWG 生成请求：进入插件前的全部路径都经过边界校验。"""

    schema: str
    request_id: str
    base_dwg: Path  # 基础 DWG 工作副本（attempt 目录内绝对路径）
    layout_asset: str  # 布局资产项目内 POSIX 相对路径（规范字段）
    layout_asset_path: Path  # 同一资产的本机绝对路径（Python 校验后派生）
    source_layout: str
    target_layout: str
    result_json: Path  # 结果 JSON（attempt 目录内绝对路径）

    @classmethod
    def create(
        cls,
        *,
        task: DrawingTask,
        attempt: AttemptPaths,
        project_root: Path,
        request_id: str | None = None,
    ) -> CadDrawingRequestV1:
        project_root = Path(project_root)

        def resolve_asset(relative_path: str) -> Path:
            try:
                return resolve_within_project(project_root, relative_path)
            except ProjectPathError as error:
                raise CadDrawingRequestError(str(error)) from error

        resolve_asset(task.base_asset.relative_path)
        layout_asset_path = resolve_asset(task.layout_asset.relative_path)
        resolve_asset(task.target_dwg_path)

        _validated_layout_name(task.source_layout, field="source_layout")
        _validated_layout_name(task.target_layout, field="target_layout")
        if task.source_layout.casefold() == "model":
            raise CadDrawingRequestError("source_layout 不得为保留布局名 Model")
        if task.target_layout.casefold() == "model":
            raise CadDrawingRequestError("target_layout 不得为保留布局名 Model")
        if task.source_layout == task.target_layout:
            raise CadDrawingRequestError("source_layout 与 target_layout 不得同名")

        return cls(
            schema=CAD_DRAWING_REQUEST_SCHEMA,
            request_id=request_id or uuid.uuid4().hex,
            base_dwg=attempt.working_dwg,
            layout_asset=task.layout_asset.relative_path,
            layout_asset_path=layout_asset_path,
            source_layout=task.source_layout,
            target_layout=task.target_layout,
            result_json=attempt.result_json,
        )

    def to_payload(self) -> dict:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "base_dwg": str(self.base_dwg),
            "layout_asset": self.layout_asset,
            "layout_asset_path": str(self.layout_asset_path),
            "source_layout": self.source_layout,
            "target_layout": self.target_layout,
            "result_json": str(self.result_json),
        }

    @classmethod
    def from_payload(cls, payload: object) -> CadDrawingRequestV1:
        fields = _strict_fields(
            payload,
            CAD_DRAWING_REQUEST_SCHEMA,
            ("schema", "request_id", "base_dwg", "layout_asset", "layout_asset_path", "source_layout", "target_layout", "result_json"),
        )
        for key in ("request_id", "layout_asset", "source_layout", "target_layout"):
            if not isinstance(fields[key], str) or not fields[key]:
                raise CadDrawingRequestError(f"请求字段 {key} 必须为非空字符串")
        for key in ("base_dwg", "layout_asset_path", "result_json"):
            if not isinstance(fields[key], str) or not fields[key]:
                raise CadDrawingRequestError(f"请求字段 {key} 必须为非空路径")
        return cls(
            schema=fields["schema"],
            request_id=fields["request_id"],
            base_dwg=Path(fields["base_dwg"]),
            layout_asset=fields["layout_asset"],
            layout_asset_path=Path(fields["layout_asset_path"]),
            source_layout=fields["source_layout"],
            target_layout=fields["target_layout"],
            result_json=Path(fields["result_json"]),
        )


@dataclass(frozen=True, slots=True)
class CadDrawingResultV1:
    """§7 单 DWG 生成结果：插件写出前七项，DWG 大小与 SHA-256 由 Python 计算。"""

    schema: str
    request_id: str
    layout_name: str
    layout_handle: str
    database_version: str
    layouts: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]
    dwg_size: int | None = None
    dwg_sha256: str | None = None

    @classmethod
    def from_payload(cls, payload: object) -> CadDrawingResultV1:
        fields = _strict_fields(
            payload,
            CAD_DRAWING_RESULT_SCHEMA,
            ("schema", "request_id", "layout_name", "layout_handle", "database_version", "layouts", "diagnostics"),
        )
        for key in ("request_id", "layout_name", "layout_handle", "database_version"):
            if not isinstance(fields[key], str) or not fields[key]:
                raise CadDrawingRequestError(f"结果字段 {key} 必须为非空字符串")
        if not set(fields["layout_handle"]) <= _HANDLE_DIGITS:
            raise CadDrawingRequestError(f"布局 Handle 非法：{fields['layout_handle']!r}")
        layouts = fields["layouts"]
        if not isinstance(layouts, list) or not all(isinstance(name, str) and name for name in layouts):
            raise CadDrawingRequestError("结果 layouts 必须为非空字符串列表")
        return cls(
            schema=fields["schema"],
            request_id=fields["request_id"],
            layout_name=fields["layout_name"],
            layout_handle=fields["layout_handle"].upper(),
            database_version=fields["database_version"],
            layouts=tuple(layouts),
            diagnostics=_parse_diagnostics(fields["diagnostics"]),
        )


@dataclass(frozen=True, slots=True)
class CadInspectRequestV1:
    """布局 inspection 请求：唯一命令 ``DSTBUILDER_CREATE_DRAWING`` 的读取模式。"""

    schema: str
    request_id: str
    result_json: Path

    @classmethod
    def create(cls, *, result_json: Path, request_id: str | None = None) -> CadInspectRequestV1:
        return cls(
            schema=CAD_INSPECT_REQUEST_SCHEMA,
            request_id=request_id or uuid.uuid4().hex,
            result_json=Path(result_json),
        )

    def to_payload(self) -> dict:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "result_json": str(self.result_json),
        }

    @classmethod
    def from_payload(cls, payload: object) -> CadInspectRequestV1:
        fields = _strict_fields(
            payload, CAD_INSPECT_REQUEST_SCHEMA, ("schema", "request_id", "result_json")
        )
        if not isinstance(fields["request_id"], str) or not fields["request_id"]:
            raise CadDrawingRequestError("请求字段 request_id 必须为非空字符串")
        if not isinstance(fields["result_json"], str) or not fields["result_json"]:
            raise CadDrawingRequestError("请求字段 result_json 必须为非空路径")
        return cls(
            schema=fields["schema"],
            request_id=fields["request_id"],
            result_json=Path(fields["result_json"]),
        )


@dataclass(frozen=True, slots=True)
class CadInspectResultV1:
    schema: str
    request_id: str
    layouts: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: object) -> CadInspectResultV1:
        fields = _strict_fields(
            payload, CAD_INSPECT_RESULT_SCHEMA, ("schema", "request_id", "layouts")
        )
        if not isinstance(fields["request_id"], str) or not fields["request_id"]:
            raise CadDrawingRequestError("结果字段 request_id 必须为非空字符串")
        layouts = fields["layouts"]
        if not isinstance(layouts, list) or not all(isinstance(name, str) and name for name in layouts):
            raise CadDrawingRequestError("结果 layouts 必须为非空字符串列表")
        return cls(schema=fields["schema"], request_id=fields["request_id"], layouts=tuple(layouts))


def _strict_fields(payload: object, schema: str, keys: tuple[str, ...]) -> dict:
    """payload 必须是指定 Schema 的扁平对象且字段集合精确匹配。"""
    if not isinstance(payload, dict):
        raise CadDrawingRequestError("契约 payload 必须为 JSON 对象")
    if set(payload) != set(keys):
        raise CadDrawingRequestError(f"契约字段集合不匹配：{sorted(payload)}")
    if payload["schema"] != schema:
        raise CadDrawingRequestError(f"未知契约 Schema：{payload['schema']!r}")
    return payload


def _parse_diagnostics(raw: object) -> tuple[Diagnostic, ...]:
    if not isinstance(raw, list):
        raise CadDrawingRequestError("结果 diagnostics 必须为列表")
    parsed: list[Diagnostic] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"code", "severity", "message"}:
            raise CadDrawingRequestError(f"诊断项字段集合不匹配：{item!r}")
        if not isinstance(item["code"], str) or not isinstance(item["message"], str):
            raise CadDrawingRequestError("诊断 code/message 必须为字符串")
        if item["severity"] not in _DIAGNOSTIC_SEVERITIES:
            raise CadDrawingRequestError(f"未知诊断级别：{item['severity']!r}")
        parsed.append(
            Diagnostic(
                code=item["code"],
                severity=DiagnosticSeverity(item["severity"]),
                message=item["message"],
            )
        )
    return tuple(parsed)
