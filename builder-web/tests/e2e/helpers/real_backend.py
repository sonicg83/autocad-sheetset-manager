# Builder 真实后端 e2e 入口（PLAN-DB-001 Task 9 controller 裁决）。
#
# 用途：Playwright webServer 拉起真实 Builder FastAPI 应用（真实项目库、真实
# 编排/发布链路），仅 CAD 执行器替换为进程内 fake（不依赖 AutoCAD 安装）。
# 启动方式（playwright.config.ts）：
#   uv run --project .. python tests/e2e/helpers/real_backend.py
# 监听 127.0.0.1:8101；前端 vite 代理经 DST_BUILDER_API_TARGET 指向本端口。
"""Real-backend e2e entry: real Builder API with an in-process fake CAD executor."""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import uvicorn

# `uv run --project ..` 已提供项目 venv；此处兜底支持直接 `python` 调用。
_REPO_SRC = Path(__file__).resolve().parents[4] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from dst_builder.domain.models import AssetSnapshot
from dst_builder.infrastructure.autocad.capabilities import CadConfiguration
from dst_builder.infrastructure.autocad.request import (
    CAD_DRAWING_RESULT_SCHEMA,
    CadDrawingResultV1,
)
from dst_builder.interfaces.api import create_builder_app

BUILT_CONTENT = b"fake built dwg bytes (e2e)"
LAYOUT_HANDLE = "2F"
FAKE_LAYOUTS = ("Model", "A1", "A2")

_CAD_DIR = Path(tempfile.mkdtemp(prefix="dstb-e2e-cad-"))

# 确定性项目根：spec 用同一相对路径计算（tests/e2e → builder-web/.e2e/project）。
_E2E_WORK = Path(__file__).resolve().parents[3] / ".e2e"
PROJECT_ROOT = _E2E_WORK / "project"


def _prepare_project_root() -> None:
    """每次启动重建空项目根（工厂绑定它，资产端点依赖 app.state.project_root）。"""
    shutil.rmtree(_E2E_WORK, ignore_errors=True)
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)


def _make_cad_configuration() -> CadConfiguration:
    """伪造能力探测所需文件（真实探测只检查文件存在）。"""
    console = _CAD_DIR / "accoreconsole.exe"
    console.write_bytes(b"MZ fake console")
    plugin = _CAD_DIR / "DstBuilder.AutoCAD.dll"
    plugin.write_bytes(b"MZ fake plugin")
    return CadConfiguration(console_2020=console, plugin_2020=plugin)


class FakeDrawingBuilder:
    """进程内 fake：布局探测返回固定列表；DWG 生成写出自洽结果。"""

    def inspect_layouts(self, asset: AssetSnapshot, cad_version: str) -> tuple[str, ...]:
        return FAKE_LAYOUTS

    def build(self, task, attempt, *, cad_version: str) -> CadDrawingResultV1:
        # attempt 目录为 <root>/builds/<build-id>/attempt-NNN/work（work 内平铺）。
        project_root = attempt.attempt_dir.parents[3]
        built = project_root / task.target_dwg_path
        built.parent.mkdir(parents=True, exist_ok=True)
        built.write_bytes(BUILT_CONTENT)
        return CadDrawingResultV1(
            schema=CAD_DRAWING_RESULT_SCHEMA,
            request_id="e2e-fake-request-id",
            layout_name=task.target_layout,
            layout_handle=LAYOUT_HANDLE,
            database_version="AC1027",
            layouts=(task.target_layout,),
            diagnostics=(),
            dwg_size=len(BUILT_CONTENT),
            dwg_sha256=hashlib.sha256(BUILT_CONTENT).hexdigest(),
            cad_version=cad_version,
        )


def main() -> None:
    _prepare_project_root()
    builder = FakeDrawingBuilder()
    app = create_builder_app(
        PROJECT_ROOT,
        cad_configuration=_make_cad_configuration(),
        layout_inspector=builder,
        drawing_builder=builder,
    )
    uvicorn.run(app, host="127.0.0.1", port=8101, log_level="warning")


if __name__ == "__main__":
    main()
