"""真实 AutoCAD 单 DWG 生成系统测试（SPEC-DB-001 §7）。

环境门禁：

* 仅当 ``DST_BUILDER_RUN_AUTOCAD=1`` 时运行，否则跳过；
* 需要显式配置 ``DST_BUILDER_AUTOCAD_<版本>_CONSOLE`` / ``..._PLUGIN``
  （``load_cad_configuration``）且探测可用；
* 需要样本 DWG：``DST_BUILDER_AUTOCAD_SAMPLE_DWG``（私有小样图路径），
  测试只操作 ``tmp_path`` 内的私有样本副本，绝不改动样本原件。

可选环境变量：``DST_BUILDER_AUTOCAD_VERSION``（默认 2020）、
``DST_BUILDER_AUTOCAD_SAMPLE_LAYOUT``（默认 Layout1）。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from dst_builder.domain.models import AssetRole, AssetSnapshot
from dst_builder.domain.planning import layout_name, sheet_number
from dst_builder.infrastructure.autocad.capabilities import (
    evaluate_cad_capability,
    load_cad_configuration,
)
from dst_builder.infrastructure.autocad.drawing import CoreConsoleDrawingBuilder
from dst_builder.infrastructure.autocad.request import AttemptPaths

pytest.importorskip("dst_builder")


def _require_environment() -> tuple[str, Path, str]:
    if os.environ.get("DST_BUILDER_RUN_AUTOCAD") != "1":
        pytest.skip("需要 DST_BUILDER_RUN_AUTOCAD=1 显式启用真实 AutoCAD 测试")

    cad_version = os.environ.get("DST_BUILDER_AUTOCAD_VERSION", "2020")
    configuration = load_cad_configuration()
    if cad_version == "2016":
        console, plugin = configuration.console_2016, configuration.plugin_2016
    else:
        console, plugin = configuration.console_2020, configuration.plugin_2020
    status = evaluate_cad_capability(cad_version, console=console, plugin=plugin)
    if not status.available:
        pytest.skip(f"本机未配置可用的 AutoCAD {cad_version}：{status.unavailable_reason}")

    sample = os.environ.get("DST_BUILDER_AUTOCAD_SAMPLE_DWG")
    if not sample or not Path(sample).is_file():
        pytest.skip("需要 DST_BUILDER_AUTOCAD_SAMPLE_DWG 指向私有小样图 DWG")
    source_layout = os.environ.get("DST_BUILDER_AUTOCAD_SAMPLE_LAYOUT", "Layout1")
    return cad_version, Path(sample), source_layout


def test_real_autocad_minimal_drawing(tmp_path: Path) -> None:
    _, sample, source_layout = _require_environment()

    # 私有样本副本：样本原件绝不进入生成流程。
    root = tmp_path / "project"
    asset_dir = root / "assets" / "base"
    asset_dir.mkdir(parents=True)
    private_copy = asset_dir / "sample.dwg"
    shutil.copyfile(sample, private_copy)
    size, sha256 = private_copy.stat().st_size, _sha256(private_copy)
    asset = AssetSnapshot(
        role=AssetRole.BASE, relative_path="assets/base/sample.dwg", sha256=sha256, size=size
    )

    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    attempt = AttemptPaths.create(attempt_dir)

    target_layout = layout_name(sheet_number("建", 1, 3), "系统图")
    builder = CoreConsoleDrawingBuilder(root, load_cad_configuration())

    from dst_builder.domain.models import DrawingTask

    task = DrawingTask(
        task_id="system-test",
        base_asset=asset,
        layout_asset=asset,
        source_layout=source_layout,
        target_layout=target_layout,
        target_dwg_path=f"drawings/{target_layout}.dwg",
    )

    result = builder.build(task, attempt)

    final = root / "drawings" / f"{target_layout}.dwg"
    assert final.is_file()
    assert result.layout_name == target_layout
    assert result.layouts == (target_layout,)
    assert result.layout_handle
    assert result.dwg_size == final.stat().st_size
    assert result.dwg_sha256 == _sha256(final)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
