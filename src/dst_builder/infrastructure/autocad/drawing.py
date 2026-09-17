"""DrawingBuilder：单 DWG 生成与布局 inspection 编排（SPEC-DB-001 §7）。

进程执行一律经 ``dst_platform.autocad.process.CoreConsoleExecutor``（参数数组
启动匹配版本 ``accoreconsole.exe``、``shell=False``、超时 kill 后回收输出）；
测试以 fake executor 替换 ``run`` 即可完整验证编排。失败语义：超时/取消 →
``BUILD_INTERRUPTED``；进程失败、结果缺失、Schema/版本不匹配、请求 ID 不匹配、
布局集合不匹配、Handle 非法、阻断诊断 → ``CAD_EXECUTION_FAILED``；能力未配置
或版本不受支持 → ``CAD_VERSION_UNAVAILABLE``。均以阻断错误结束 attempt。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from dst_builder.domain.models import AssetSnapshot, DiagnosticSeverity, DrawingTask
from dst_builder.domain.paths import resolve_within_project
from dst_builder.infrastructure.autocad.capabilities import (
    SUPPORTED_CAD_VERSIONS,
    CadConfiguration,
    evaluate_cad_capability,
)
from dst_builder.infrastructure.autocad.request import (
    AttemptPaths,
    CadDrawingRequestError,
    CadDrawingRequestV1,
    CadDrawingResultV1,
    CadInspectRequestV1,
    CadInspectResultV1,
    CadVersion,
)
from dst_builder.infrastructure.autocad.script import render_worker_scr
from dst_platform.autocad.process import CoreConsoleExecutor, CoreConsoleRequest

__all__ = [
    "BUILD_INTERRUPTED",
    "CAD_EXECUTION_FAILED",
    "CAD_VERSION_UNAVAILABLE",
    "DEFAULT_TIMEOUT_SECONDS",
    "CadDrawingError",
    "CoreConsoleDrawingBuilder",
    "DrawingBuilder",
]

CAD_EXECUTION_FAILED = "CAD_EXECUTION_FAILED"
BUILD_INTERRUPTED = "BUILD_INTERRUPTED"
CAD_VERSION_UNAVAILABLE = "CAD_VERSION_UNAVAILABLE"
DEFAULT_TIMEOUT_SECONDS = 600


class CadDrawingError(Exception):
    """§7 阻断错误：固定 §11 code + 用户信息。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DrawingBuilder(Protocol):
    """§7 生成端口：真实实现为 :class:`CoreConsoleDrawingBuilder`。"""

    def inspect_layouts(self, asset: AssetSnapshot, cad_version: CadVersion) -> tuple[str, ...]: ...

    def build(self, task: DrawingTask, attempt: AttemptPaths) -> CadDrawingResultV1: ...


class CoreConsoleDrawingBuilder:
    """经共享 Core Console 原语执行 Builder 插件的唯一实现。"""

    def __init__(
        self,
        project_root: str | Path,
        configuration: CadConfiguration,
        *,
        executor: CoreConsoleExecutor | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._project_root = Path(project_root)
        self._configuration = configuration
        self._executor = executor if executor is not None else CoreConsoleExecutor()
        self._timeout = timeout

    # -- 端口 ----------------------------------------------------------------

    def inspect_layouts(self, asset: AssetSnapshot, cad_version: CadVersion) -> tuple[str, ...]:
        """用匹配版本 CAD 读取布局资产的可用布局（资产在私有副本上打开）。"""
        console, plugin = self._capability(cad_version)
        with tempfile.TemporaryDirectory(prefix="dstb-inspect-") as temp:
            work = Path(temp)
            drawing = work / f"layout-asset{Path(asset.relative_path).suffix.lower()}"
            shutil.copyfile(self._resolve_asset(asset.relative_path), drawing)
            request = CadInspectRequestV1.create(result_json=work / "cad-inspect-result.json")
            self._write_request(work / "cad-inspect-request.json", request.to_payload())
            script = work / "cad-inspect.scr"
            self._write_script(script, plugin, work / "cad-inspect-request.json")
            self._run(console, drawing, script)
            payload = self._read_result_json(request.result_json)
            try:
                result = CadInspectResultV1.from_payload(payload)
            except CadDrawingRequestError as error:
                raise self._execution_failed(f"inspection 结果无效：{error}") from error
            if result.request_id != request.request_id:
                raise self._execution_failed("inspection 结果 request ID 不匹配")
            return result.layouts

    def build(self, task: DrawingTask, attempt: AttemptPaths) -> CadDrawingResultV1:
        """执行单 DWG 生成：工作副本 → 插件导入布局 → 发布 → 计算大小与哈希。"""
        try:
            request = CadDrawingRequestV1.create(
                task=task, attempt=attempt, project_root=self._project_root
            )
        except CadDrawingRequestError as error:
            raise CadDrawingError(CAD_EXECUTION_FAILED, str(error)) from error

        console, plugin = self._capability_for_build()
        source = self._resolve_asset(task.base_asset.relative_path)
        if not source.is_file():
            raise CadDrawingError(CAD_EXECUTION_FAILED, f"基础资产不存在：{source}")
        shutil.copyfile(source, attempt.working_dwg)
        self._write_request(attempt.request_json, request.to_payload())
        self._write_script(attempt.script, plugin, attempt.request_json)

        self._run(console, attempt.working_dwg, attempt.script)

        payload = self._read_result_json(attempt.result_json)
        try:
            result = CadDrawingResultV1.from_payload(payload)
        except CadDrawingRequestError as error:
            raise self._execution_failed(f"结果 JSON 无效：{error}") from error
        if result.request_id != request.request_id:
            raise self._execution_failed("结果 request ID 与请求不匹配")
        if result.layout_name != task.target_layout:
            raise self._execution_failed(
                f"结果布局名不匹配：期望 {task.target_layout!r}，实际 {result.layout_name!r}"
            )
        if set(result.layouts) != {task.target_layout}:
            raise self._execution_failed(f"最终布局集合不匹配：{list(result.layouts)}")
        if any(item.severity is DiagnosticSeverity.BLOCKING for item in result.diagnostics):
            raise self._execution_failed("结果携带阻断诊断")

        final = self._resolve_asset(task.target_dwg_path)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(attempt.working_dwg, final)
        return replace(result, dwg_size=final.stat().st_size, dwg_sha256=_file_sha256(final))

    # -- 内部 ----------------------------------------------------------------

    def _capability(self, cad_version: str) -> tuple[Path, Path]:
        if cad_version not in SUPPORTED_CAD_VERSIONS:
            raise CadDrawingError(CAD_VERSION_UNAVAILABLE, f"不支持的 CAD 版本：{cad_version}")
        console = self._console_for(cad_version)
        plugin = self._plugin_for(cad_version)
        status = evaluate_cad_capability(cad_version, console=console, plugin=plugin)
        if not status.available:
            raise CadDrawingError(
                CAD_VERSION_UNAVAILABLE,
                f"AutoCAD {cad_version} 不可用：{status.unavailable_reason}",
            )
        return console, plugin

    def _console_for(self, cad_version: str) -> Path | None:
        return {
            "2016": self._configuration.console_2016,
            "2020": self._configuration.console_2020,
        }.get(cad_version)

    def _plugin_for(self, cad_version: str) -> Path | None:
        return {
            "2016": self._configuration.plugin_2016,
            "2020": self._configuration.plugin_2020,
        }.get(cad_version)

    def _capability_for_build(self) -> tuple[Path, Path]:
        """build 的版本选择：优先 2020，其次 2016（两个版本插件行为一致）。

        2016/2020 双版本产物由插件构建脚本分别产出；全部不可用时以
        ``CAD_VERSION_UNAVAILABLE`` 阻断。
        """
        errors: list[str] = []
        for cad_version in ("2020", "2016"):
            try:
                return self._capability(cad_version)
            except CadDrawingError as error:
                errors.append(f"{cad_version}: {error.message}")
        raise CadDrawingError(CAD_VERSION_UNAVAILABLE, "；".join(errors))

    def _resolve_asset(self, relative_path: str) -> Path:
        try:
            return resolve_within_project(self._project_root, relative_path)
        except Exception as error:  # ProjectPathError（含越界/非法形态）
            raise self._execution_failed(f"资产路径越界：{error}") from error

    def _run(self, console: Path, drawing: Path, script: Path) -> None:
        try:
            self._executor.run(
                CoreConsoleRequest(console=console, drawing=drawing, script=script, timeout=self._timeout)
            )
        except subprocess.TimeoutExpired as error:
            raise CadDrawingError(BUILD_INTERRUPTED, f"CAD 执行超时（{self._timeout}s），attempt 已阻断") from error
        except subprocess.CalledProcessError as error:
            raise self._execution_failed(f"CAD 进程执行失败：退出码 {error.returncode}") from error

    @staticmethod
    def _write_request(path: Path, payload: dict) -> None:
        """请求 JSON 原子写出（临时文件 + os.replace），插件读到即完整内容。"""
        temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _write_script(path: Path, plugin: Path, request_json: Path) -> None:
        try:
            text = render_worker_scr(str(plugin), str(request_json))
        except ValueError as error:
            raise CadDrawingError(CAD_EXECUTION_FAILED, f"SCR 渲染被拒绝：{error}") from error
        path.write_text(text, encoding="mbcs")

    @staticmethod
    def _read_result_json(path: Path) -> dict:
        if not path.is_file():
            raise CadDrawingError(CAD_EXECUTION_FAILED, f"结果 JSON 缺失：{path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CadDrawingError(CAD_EXECUTION_FAILED, f"结果 JSON 读取失败：{error}") from error
        if not isinstance(payload, dict):
            raise CadDrawingError(CAD_EXECUTION_FAILED, "结果 JSON 必须为对象")
        return payload

    @staticmethod
    def _execution_failed(message: str) -> CadDrawingError:
        return CadDrawingError(CAD_EXECUTION_FAILED, message)


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
