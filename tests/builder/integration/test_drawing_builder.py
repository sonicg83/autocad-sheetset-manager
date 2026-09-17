"""DrawingBuilder 编排测试（SPEC-DB-001 §7）：fake executor 完整验证。

不启动真实 accoreconsole：fake executor 替换
``dst_platform.autocad.process.CoreConsoleExecutor.run``，断言参数数组输入、
SCR/请求 JSON 落盘、结果解析门禁与失败语义（超时/进程失败/缺结果/版本
不匹配/布局集合不匹配/Handle 非法/阻断诊断）。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from dst_builder.domain.models import AssetRole, AssetSnapshot, DrawingTask
from dst_builder.infrastructure.autocad.capabilities import CadConfiguration
from dst_builder.infrastructure.autocad.drawing import (
    BUILD_INTERRUPTED,
    CAD_EXECUTION_FAILED,
    CAD_VERSION_UNAVAILABLE,
    CadDrawingError,
    CoreConsoleDrawingBuilder,
)
from dst_builder.infrastructure.autocad.request import (
    CAD_DRAWING_REQUEST_SCHEMA,
    CAD_DRAWING_RESULT_SCHEMA,
    CAD_INSPECT_REQUEST_SCHEMA,
    CAD_INSPECT_RESULT_SCHEMA,
    AttemptPaths,
)
from dst_platform.autocad.process import (
    CoreConsoleExecutor,
    CoreConsoleRequest,
    CoreConsoleResult,
)

BASE_SHA = "a" * 64
LAYOUT_SHA = "b" * 64
BASE_CONTENT = b"base dwg working copy bytes"
BUILT_CONTENT = b"built dwg bytes"
TARGET_LAYOUT = "001 平面"


class FakeExecutor:
    """按注入行为模拟 accoreconsole：记录 CoreConsoleRequest 并产出副作用。"""

    def __init__(
        self, behavior: Callable[[CoreConsoleRequest, FakeExecutor], None] | None = None
    ) -> None:
        self.requests: list[CoreConsoleRequest] = []
        self._behavior = behavior

    def run(self, request: CoreConsoleRequest):
        self.requests.append(request)
        if self._behavior is not None:
            self._behavior(request, self)
        return CoreConsoleResult(
            args=[str(request.console)], returncode=0, stdout="", stderr="", duration_ms=1, peak_memory_bytes=None
        )


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    base_dir = root / "assets" / "base"
    layout_dir = root / "assets" / "layout"
    base_dir.mkdir(parents=True, exist_ok=True)
    layout_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / f"base-{BASE_SHA}.dwg").write_bytes(BASE_CONTENT)
    (layout_dir / f"layout-{LAYOUT_SHA}.dwg").write_bytes(b"layout asset bytes")
    return root


def make_configuration(tmp_path: Path) -> CadConfiguration:
    cad = tmp_path / "cad"
    cad.mkdir(exist_ok=True)
    console = cad / "accoreconsole.exe"
    console.write_bytes(b"MZ fake console")
    plugin = cad / "DstBuilder.AutoCAD.dll"
    plugin.write_bytes(b"MZ fake plugin")
    cad_2016 = cad / "2016"
    cad_2016.mkdir(exist_ok=True)
    console_2016 = cad_2016 / "accoreconsole.exe"
    console_2016.write_bytes(b"MZ fake console 2016")
    plugin_2016 = cad_2016 / "DstBuilder.AutoCAD.dll"
    plugin_2016.write_bytes(b"MZ fake plugin 2016")
    return CadConfiguration(
        console_2020=console,
        plugin_2020=plugin,
        console_2016=console_2016,
        plugin_2016=plugin_2016,
    )


def make_task() -> DrawingTask:
    return DrawingTask(
        task_id="task-1",
        base_asset=AssetSnapshot(
            role=AssetRole.BASE,
            relative_path=f"assets/base/base-{BASE_SHA}.dwg",
            sha256=BASE_SHA,
            size=len(BASE_CONTENT),
        ),
        layout_asset=AssetSnapshot(
            role=AssetRole.LAYOUT,
            relative_path=f"assets/layout/layout-{LAYOUT_SHA}.dwg",
            sha256=LAYOUT_SHA,
            size=18,
        ),
        source_layout="平面",
        target_layout=TARGET_LAYOUT,
        target_dwg_path=f"drawings/{TARGET_LAYOUT}.dwg",
    )


def make_builder(tmp_path: Path, executor: FakeExecutor) -> tuple[CoreConsoleDrawingBuilder, Path, AttemptPaths, CadConfiguration]:
    root = make_project(tmp_path)
    configuration = make_configuration(tmp_path)
    builder = CoreConsoleDrawingBuilder(root, configuration, executor=executor)
    attempt = AttemptPaths.create(tmp_path / "attempt")
    attempt.attempt_dir.mkdir(parents=True, exist_ok=True)
    return builder, root, attempt, configuration


def write_result(request: CoreConsoleRequest, attempt: AttemptPaths, payload: dict) -> None:
    """模拟插件行为：校验工作副本、读取请求 JSON、产出工作 DWG、写出结果 JSON。"""
    # 插件打开前，工作副本必须是基础资产的完整副本。
    assert attempt.working_dwg.read_bytes() == BASE_CONTENT
    drawing_request = json.loads(attempt.request_json.read_text(encoding="utf-8"))
    assert drawing_request["schema"] == CAD_DRAWING_REQUEST_SCHEMA
    payload.setdefault("schema", CAD_DRAWING_RESULT_SCHEMA)
    payload.setdefault("request_id", drawing_request["request_id"])
    payload.setdefault("layout_name", drawing_request["target_layout"])
    payload.setdefault("layout_handle", "2F")
    payload.setdefault("database_version", "AC1027")
    payload.setdefault("layouts", [drawing_request["target_layout"]])
    payload.setdefault("diagnostics", [])
    attempt.result_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    attempt.working_dwg.write_bytes(BUILT_CONTENT)


def write_saved_result(request: CoreConsoleRequest, attempt: AttemptPaths, payload: dict) -> None:
    """模拟 Core Console 插件行为：文档原路径不可覆盖，保存落到固定派生名。

    真实 AutoCAD Core Console 拒绝 ``Database.SaveAs`` 覆盖文档自身已打开的
    ``working.dwg``（eInvalidInput），插件实际保存到 ``working.saved.dwg``；
    进程退出后由 build() 收敛回标准工作副本路径。
    """
    write_result(request, attempt, payload)
    attempt.working_dwg.with_suffix(".saved.dwg").write_bytes(BUILT_CONTENT)
    attempt.working_dwg.write_bytes(BASE_CONTENT)


# ---------------------------------------------------------------------------
# build：happy path 与编排断言
# ---------------------------------------------------------------------------


def test_build_happy_path_publishes_dwg_with_sha256(tmp_path: Path) -> None:
    executor = FakeExecutor(
        lambda request, fake: write_result(request, attempt, {}),
    )
    builder, root, attempt, configuration = make_builder(tmp_path, executor)

    result = builder.build(make_task(), attempt, cad_version="2020")

    # 参数数组输入：console/drawing/script 来自显式配置与 attempt 契约路径。
    assert len(executor.requests) == 1
    sent = executor.requests[0]
    assert sent.console == configuration.console_2020
    assert sent.drawing == attempt.working_dwg
    assert sent.script == attempt.script

    # 请求 JSON：结构化数据全部在 JSON，SCR 不携带用户文本。
    payload = json.loads(attempt.request_json.read_text(encoding="utf-8"))
    assert payload["schema"] == CAD_DRAWING_REQUEST_SCHEMA
    assert payload["layout_asset"] == f"assets/layout/layout-{LAYOUT_SHA}.dwg"
    assert payload["source_layout"] == "平面"
    assert payload["target_layout"] == TARGET_LAYOUT
    assert payload["result_json"] == str(attempt.result_json)

    # 工作副本经插件处理后保存为成果内容；项目资产本身未被改动。
    assert attempt.working_dwg.read_bytes() == BUILT_CONTENT
    assert (root / f"assets/base/base-{BASE_SHA}.dwg").read_bytes() == BASE_CONTENT

    # 成果发布：目标 DWG 落在项目内计划路径，Python 计算大小与 SHA-256。
    final = root / "drawings" / f"{TARGET_LAYOUT}.dwg"
    assert final.read_bytes() == BUILT_CONTENT
    assert result.layout_name == TARGET_LAYOUT
    assert result.layout_handle == "2F"
    assert result.layouts == (TARGET_LAYOUT,)
    assert result.dwg_size == len(BUILT_CONTENT)
    assert result.dwg_sha256 == hashlib.sha256(BUILT_CONTENT).hexdigest()


def test_build_converges_core_console_saved_file_back_to_working_dwg(tmp_path: Path) -> None:
    executor = FakeExecutor(
        lambda request, fake: write_saved_result(request, attempt, {}),
    )
    builder, root, attempt, _configuration = make_builder(tmp_path, executor)

    result = builder.build(make_task(), attempt, cad_version="2020")

    # 插件保存的 ``working.saved.dwg`` 被收敛回 ``working.dwg`` 后再发布；
    # attempt 目录不残留派生保存文件。
    final = root / "drawings" / f"{TARGET_LAYOUT}.dwg"
    assert final.read_bytes() == BUILT_CONTENT
    assert attempt.working_dwg.read_bytes() == BUILT_CONTENT
    assert not attempt.working_dwg.with_suffix(".saved.dwg").exists()
    assert result.dwg_sha256 == hashlib.sha256(BUILT_CONTENT).hexdigest()
    # attempt 版本证据：结果留痕实际使用的 CAD 版本（Task 9 接线点）。
    assert result.cad_version == "2020"


def test_build_script_file_matches_fixed_renderer(tmp_path: Path) -> None:
    from dst_builder.infrastructure.autocad.script import render_worker_scr

    executor = FakeExecutor(lambda request, fake: write_result(request, attempt, {}))
    builder, _, attempt, configuration = make_builder(tmp_path, executor)

    builder.build(make_task(), attempt, cad_version="2020")

    expected = render_worker_scr(
        str(configuration.plugin_2020), str(attempt.request_json)
    )
    assert attempt.script.read_text(encoding="mbcs") == expected


def test_build_without_executor_uses_platform_core_console(tmp_path: Path) -> None:
    """默认执行器必须是 dst_platform 共享 CoreConsoleExecutor（Task 6 原语）。"""
    root = make_project(tmp_path)
    configuration = make_configuration(tmp_path)
    builder = CoreConsoleDrawingBuilder(root, configuration)

    assert isinstance(builder._executor, CoreConsoleExecutor)


# ---------------------------------------------------------------------------
# build：失败语义
# ---------------------------------------------------------------------------


def test_build_timeout_is_blocked_as_interrupted(tmp_path: Path) -> None:
    def timeout(request: CoreConsoleRequest, fake: FakeExecutor) -> None:
        raise subprocess.TimeoutExpired(cmd=["accoreconsole"], timeout=5)

    builder, _, attempt, _ = make_builder(tmp_path, FakeExecutor(timeout))

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == BUILD_INTERRUPTED


def test_build_process_failure_is_blocked(tmp_path: Path) -> None:
    def failure(request: CoreConsoleRequest, fake: FakeExecutor) -> None:
        raise subprocess.CalledProcessError(returncode=3, cmd=["accoreconsole"])

    builder, _, attempt, _ = make_builder(tmp_path, FakeExecutor(failure))

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == CAD_EXECUTION_FAILED


def test_build_missing_result_json_is_blocked(tmp_path: Path) -> None:
    builder, _, attempt, _ = make_builder(tmp_path, FakeExecutor())

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == CAD_EXECUTION_FAILED


def test_build_result_version_mismatch_is_blocked(tmp_path: Path) -> None:
    executor = FakeExecutor(
        lambda request, fake: write_result(
            request, attempt, {"schema": "dst-builder.cad-drawing-result/v2"}
        )
    )
    builder, _, attempt, _ = make_builder(tmp_path, executor)

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == CAD_EXECUTION_FAILED


def test_build_request_id_mismatch_is_blocked(tmp_path: Path) -> None:
    executor = FakeExecutor(
        lambda request, fake: write_result(
            request, attempt, {"request_id": "00000000-0000-0000-0000-000000000000"}
        )
    )
    builder, _, attempt, _ = make_builder(tmp_path, executor)

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == CAD_EXECUTION_FAILED


def test_build_layout_set_mismatch_is_blocked(tmp_path: Path) -> None:
    for layouts in (["Model", TARGET_LAYOUT], ["别的布局"], [TARGET_LAYOUT, "多余的"]):
        executor = FakeExecutor()
        builder, _, attempt, _ = make_builder(tmp_path, executor)
        executor._behavior = lambda request, fake, a=attempt, ls=layouts: write_result(
            request, a, {"layouts": ls}
        )

        with pytest.raises(CadDrawingError) as excinfo:
            builder.build(make_task(), attempt, cad_version="2020")
        assert excinfo.value.code == CAD_EXECUTION_FAILED


def test_build_invalid_handle_is_blocked(tmp_path: Path) -> None:
    executor = FakeExecutor(
        lambda request, fake: write_result(request, attempt, {"layout_handle": "XYZ"})
    )
    builder, _, attempt, _ = make_builder(tmp_path, executor)

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == CAD_EXECUTION_FAILED


def test_build_blocking_diagnostic_is_blocked(tmp_path: Path) -> None:
    executor = FakeExecutor(
        lambda request, fake: write_result(
            request,
            attempt,
            {"diagnostics": [{"code": "D1", "severity": "blocking", "message": "阻断"}]},
        )
    )
    builder, _, attempt, _ = make_builder(tmp_path, executor)

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == CAD_EXECUTION_FAILED


def test_build_uses_requested_version_without_cross_version_fallback(tmp_path: Path) -> None:
    """计划版本=2016 而 2020 也可用时，仍严格使用 2016（SPEC §2/§5/§7）。"""
    executor = FakeExecutor(lambda request, fake: write_result(request, attempt, {}))
    builder, _, attempt, configuration = make_builder(tmp_path, executor)

    builder.build(make_task(), attempt, cad_version="2016")

    assert executor.requests[0].console == configuration.console_2016


def test_build_unavailable_requested_version_is_blocked_without_fallback(tmp_path: Path) -> None:
    """请求的 2016 未配置而 2020 可用：以 CAD_VERSION_UNAVAILABLE 阻断，不回退。"""
    root = make_project(tmp_path)
    configuration = make_configuration(tmp_path)
    configuration = CadConfiguration(
        console_2020=configuration.console_2020, plugin_2020=configuration.plugin_2020
    )
    executor = FakeExecutor()
    builder = CoreConsoleDrawingBuilder(root, configuration, executor=executor)
    attempt = AttemptPaths.create(tmp_path / "attempt")
    attempt.attempt_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2016")
    assert excinfo.value.code == CAD_VERSION_UNAVAILABLE
    assert executor.requests == []


def test_build_rejects_unsupported_version(tmp_path: Path) -> None:
    executor = FakeExecutor()
    builder, _, attempt, _ = make_builder(tmp_path, executor)

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2024")
    assert excinfo.value.code == CAD_VERSION_UNAVAILABLE
    assert executor.requests == []


# ---------------------------------------------------------------------------
# inspect_layouts
# ---------------------------------------------------------------------------


def test_inspect_layouts_reads_structured_result(tmp_path: Path) -> None:
    def inspect(request: CoreConsoleRequest, fake: FakeExecutor) -> None:
        # 打开的是资产私有副本，而非项目资产原件。
        assert request.drawing != fake_asset_original
        assert request.drawing.read_bytes() == b"layout asset bytes"
        # inspect 请求 JSON 也是结构化契约。
        payload = json.loads(
            request.drawing.with_name("cad-inspect-request.json").read_text(encoding="utf-8")
        )
        assert payload["schema"] == CAD_INSPECT_REQUEST_SCHEMA
        result = {
            "schema": CAD_INSPECT_RESULT_SCHEMA,
            "request_id": payload["request_id"],
            "layouts": ["A1", "A2"],
        }
        request.drawing.with_name("cad-inspect-result.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )

    builder, root, _, _ = make_builder(tmp_path, FakeExecutor(inspect))
    fake_asset_original = root / f"assets/layout/layout-{LAYOUT_SHA}.dwg"
    asset = AssetSnapshot(
        role=AssetRole.LAYOUT,
        relative_path=f"assets/layout/layout-{LAYOUT_SHA}.dwg",
        sha256=LAYOUT_SHA,
        size=18,
    )

    assert builder.inspect_layouts(asset, "2020") == ("A1", "A2")
    # 项目资产原件未被修改。
    assert fake_asset_original.read_bytes() == b"layout asset bytes"


@pytest.mark.parametrize("cad_version", ["2020", "2016"])
def test_unavailable_capability_is_blocked(tmp_path: Path, cad_version: str) -> None:
    root = make_project(tmp_path)
    builder = CoreConsoleDrawingBuilder(root, CadConfiguration(), executor=FakeExecutor())
    asset = AssetSnapshot(
        role=AssetRole.LAYOUT,
        relative_path=f"assets/layout/layout-{LAYOUT_SHA}.dwg",
        sha256=LAYOUT_SHA,
        size=18,
    )

    with pytest.raises(CadDrawingError) as excinfo:
        builder.inspect_layouts(asset, cad_version)
    assert excinfo.value.code == CAD_VERSION_UNAVAILABLE

    attempt = AttemptPaths.create(tmp_path / "attempt")
    attempt.attempt_dir.mkdir(parents=True)
    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == CAD_VERSION_UNAVAILABLE


def test_unsupported_version_is_blocked(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    builder = CoreConsoleDrawingBuilder(
        root, make_configuration(tmp_path), executor=FakeExecutor()
    )
    asset = AssetSnapshot(
        role=AssetRole.LAYOUT,
        relative_path=f"assets/layout/layout-{LAYOUT_SHA}.dwg",
        sha256=LAYOUT_SHA,
        size=18,
    )

    with pytest.raises(CadDrawingError) as excinfo:
        builder.inspect_layouts(asset, "2024")
    assert excinfo.value.code == CAD_VERSION_UNAVAILABLE


def test_missing_base_asset_is_blocked_before_process_start(tmp_path: Path) -> None:
    executor = FakeExecutor()
    builder, root, attempt, _ = make_builder(tmp_path, executor)
    (root / f"assets/base/base-{BASE_SHA}.dwg").unlink()

    with pytest.raises(CadDrawingError) as excinfo:
        builder.build(make_task(), attempt, cad_version="2020")
    assert excinfo.value.code == CAD_EXECUTION_FAILED
    assert executor.requests == []
