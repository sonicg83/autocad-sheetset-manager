"""真实 AutoCAD 下的创建闭环验收（PLAN-DM-036 Task 7）。

覆盖每组主 DWG、全部布局/Handle、DST 引用与「官方图纸集管理器可打开性」中可在
Core Console 内机器验证的部分：

- 逐版本（2016/2020）走真实创建链（``execute_creation`` → ``run_next_job``）：
  真实 Core Console + 匹配版本的 Worker 插件生成主 DWG，随后发布并登记为普通工作区；
- 逐组主 DWG：真实回读布局集合与 Handle，必须与计划、与 DST 里记录的布局引用和
  Handle 逐项一致（同一份 ``DstGetLayoutHandles`` 输出既是布局集合也是 Handle 依据）；
- DST 引用：每张图纸的绝对/相对 DWG 引用必须解析到本次生成的主 DWG，且 AcSm
  契约/XSD/语义校验通过（``validate() == []``、修复状态 ``VALID``）。

**官方图纸集管理器（SSM）图形界面打开性无法在 Core Console 内自动化**：Worker 插件
没有打开 DST 的 AcSm 命令，也没有可脚本化的 SSM 入口，因此这一步是人工验收项——
用 AutoCAD 打开生成目录里的 ``图纸集数据文件.dst``，确认子集/图纸/布局与本文档
断言一致。本测试不把该人工步骤记为已通过。

必须显式启用（``DST_MANAGER_RUN_AUTOCAD=1``），并要求本机存在对应版本的 Core
Console、匹配版本的插件与私有样本；缺任何一项按原因跳过，绝不把系统验收标为通过。
私有样本只读：模板 DWG 一律复制到临时目录后使用，原样本的内容哈希在测试前后必须
完全一致。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.domain.creation import CreationDraft, CreationGroupInput
from dst_manager.domain.models import Workspace
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    CoreConsoleExecutor,
    ScriptRenderer,
    parse_handles,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.publisher import file_sha256

_ROOT = Path(__file__).parents[2]
_SAMPLE_TEMPLATES = _ROOT / "sample" / "template"
#: 真实模板：基础模板（含默认布局）与布局模板（真实布局 A1/A2/A3/A3NS）。
_BASE_TEMPLATE = _SAMPLE_TEMPLATES / "基础模板.dwg"
_LAYOUT_TEMPLATE = _SAMPLE_TEMPLATES / "市政项目模板-通用.dwg"
#: 标准声明的图幅：必须是布局模板真实布局之一。
_PAPER_LAYOUT = "A1"
_STANDARD_IDENTITY = "szmedi.gas@2.1.0"

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("DST_MANAGER_RUN_AUTOCAD") != "1",
        reason="需要显式启用真实AutoCAD测试",
    ),
    pytest.mark.skipif(
        not (_BASE_TEMPLATE.is_file() and _LAYOUT_TEMPLATE.is_file()),
        reason="公开仓库不分发真实工程模板样本",
    ),
]

STANDARD_DOCUMENT: dict[str, object] = {
    "schema_version": 2,
    "standard_id": "szmedi.gas",
    "version": 1,
    "name": "市政燃气施工图",
    "supported_cad_versions": ["2016", "2020"],
    "properties": [
        {
            "property_id": "prop-name",
            "name": "工程名称",
            "scope": "sheetset",
            "kind": "text",
            "required": True,
            "default_value": "默认工程",
        },
        {
            "property_id": "prop-stage",
            "name": "设计阶段",
            "scope": "sheet",
            "kind": "text",
            "default_value": "施工图",
        },
    ],
    "dwg_naming": {
        "segments": [
            {"literal": "GP-"},
            {"system_field": "subset.sequence"},
            {"literal": " "},
            {"system_field": "subset.name"},
        ]
    },
    "assets": [
        {
            "asset_id": "base-real",
            "kind": "base-template",
            "file": "templates/base.dwg",
        },
        {
            "asset_id": "layout-real",
            "kind": "layout-template",
            "file": "templates/layout.dwg",
            "paper_layouts": [_PAPER_LAYOUT],
        },
    ],
    "numbering": {"sequence_field": "subset.sequence", "digits": 2},
}


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_created_project_matches_plan_and_is_readable_by_cad(
    version: str, tmp_path: Path
) -> None:
    capability = _capability(version)
    settings = Settings(
        data_dir=tmp_path / "data",
        cad_version=version,  # type: ignore[arg-type]
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=_ROOT / "plugins" / "autocad2016" / "DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=_ROOT / "plugins" / "autocad2020" / "DstManager.AutoCAD.dll",
        cad_timeout_seconds=600,
    )
    sample_hashes = _sample_hashes()
    service = DstManagerService(settings)
    _publish_standard(service)

    target = tmp_path / "projects" / "新建项目"
    draft_id, preview_digest = _prepare_draft(service, target)
    queued = service.execute_creation(draft_id, preview_digest)
    result = service.run_next_job()

    assert result is not None and result["id"] == queued["id"]
    assert result["status"] == "SUCCEEDED", result["error_detail"]
    assert result["workspace_id"] and result["payload"]["workspace"]["revision_id"]
    dst_path = Path(result["payload"]["published"]["dst_path"])
    assert dst_path == target / "图纸集数据文件.dst" and dst_path.is_file()

    # 重新打开：登记产物（标准绑定、快照、初始修订）齐备且与任务一致
    workspace = service.get_workspace(result["workspace_id"])
    assert workspace.document.custom_properties["DSTManager.Standard"] == _STANDARD_IDENTITY
    assert workspace.revision_id == result["payload"]["workspace"]["revision_id"]
    assert workspace.revision_id == file_sha256(dst_path)
    assert (workspace.root / ".dst-manager/standards/szmedi.gas/2.1.0/document.json").is_file()
    assert not [
        item for item in workspace.document.diagnostics if item.severity.value == "error"
    ]

    # DST 引用与 AcSm 校验：每张图纸都解析到本次生成的主 DWG
    document = load_acsm(DstCodec().decode_file(dst_path))
    assert document.repair_report.status == "VALID"
    assert document.validate() == []
    expected = _expected_layouts_and_handles(workspace)
    assert len(expected) == 2, "夹具必须覆盖两个图纸组"
    for name, layouts in expected.items():
        drawing = workspace.root / name
        assert drawing.is_file(), f"主 DWG 未落盘：{name}"
        assert layouts, f"主 DWG {name} 没有任何布局引用"

    # 真实回读：布局集合与 Handle 必须与 DST 记录逐项一致
    check_dir = tmp_path / "cad-readback"
    check_dir.mkdir()
    for name, layouts in expected.items():
        copy = check_dir / name
        shutil.copy2(workspace.root / name, copy)
        actual = _read_layout_handles(capability, copy, check_dir, settings.cad_timeout_seconds)
        assert {key: value.upper() for key, value in actual.items()} == {
            key: value.upper() for key, value in layouts.items()
        }, f"{version} {name} 的真实布局/Handle 与 DST 不一致"

    # 私有样本只读：原样本内容哈希在测试前后完全一致
    assert _sample_hashes() == sample_hashes


def _capability(version: str) -> CadCapability:
    capability = CadCapability(
        version,
        Path(f"C:/Program Files/Autodesk/AutoCAD {version}/accoreconsole.exe"),
        _ROOT / "plugins" / f"autocad{version}" / "DstManager.AutoCAD.dll",
    )
    if not capability.available:
        pytest.skip(f"缺少 AutoCAD {version} Core Console 或匹配版本 Worker 插件")
    return capability


def _sample_hashes() -> dict[str, str]:
    return {
        path.name: file_sha256(path)
        for path in (_BASE_TEMPLATE, _LAYOUT_TEMPLATE)
        if path.is_file()
    }


def _publish_standard(service: DstManagerService) -> None:
    """发布夹具标准：真实模板先复制进草稿目录，发布后随目录落到 published 下。"""
    draft = service.create_standard_draft(STANDARD_DOCUMENT, "draft-real")
    draft_root = (
        service.settings.data_dir / "standards" / "user" / "drafts" / str(draft["draft_id"])
    )
    for relative, source in (
        ("templates/base.dwg", _BASE_TEMPLATE),
        ("templates/layout.dwg", _LAYOUT_TEMPLATE),
    ):
        target = draft_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    published = service.publish_standard(str(draft["draft_id"]))
    assert published["standard_id"] == "szmedi.gas"


def _prepare_draft(service: DstManagerService, target: Path) -> tuple[str, str]:
    draft = service.create_creation_draft(("szmedi.gas", "2.1.0"))
    saved = service.save_creation_draft(
        draft.id,
        expected_revision=draft.revision,
        value=_draft_value(draft, target),
    )
    preview = service.preview(saved.id)
    assert preview["executable"] is True, preview["diagnostics"]
    return saved.id, str(preview["preview_digest"])


def _draft_value(draft: CreationDraft, target: Path) -> CreationDraft:
    """两个图纸组（2 张 + 1 张），全部使用真实模板与真实图幅 A1。"""
    groups = (
        CreationGroupInput(
            group_id="group-1",
            created_order=1,
            title="平面图",
            count=2,
            base_asset_id="base-real",
            layout_asset_id="layout-real",
            paper_layout=_PAPER_LAYOUT,
            sheet_values={"prop-stage": "施工图"},
        ),
        CreationGroupInput(
            group_id="group-2",
            created_order=2,
            title="剖面图",
            count=1,
            base_asset_id="base-real",
            layout_asset_id="layout-real",
            paper_layout=_PAPER_LAYOUT,
            sheet_values={"prop-stage": "施工图"},
        ),
    )
    return replace(
        draft,
        target_path=str(target),
        sheetset_values={"prop-name": "真实系统验收工程"},
        groups=groups,
    )


def _expected_layouts_and_handles(workspace: Workspace) -> dict[str, dict[str, str]]:
    """已登记 DST 里逐组主 DWG 的布局 → Handle（真实回读的比对基准）。"""
    expected: dict[str, dict[str, str]] = {}
    for sheet in workspace.document.sheets:
        name = Path(sheet.layout.resolved_path).name
        expected.setdefault(name, {})[sheet.layout.layout_name] = sheet.layout.handle
    return expected


def _read_layout_handles(
    capability: CadCapability, drawing: Path, work_dir: Path, timeout: int
) -> dict[str, str]:
    """真实回读一个 DWG 的全部布局与 Handle（``DstGetLayoutHandles`` 固定命令）。"""
    script = work_dir / f"handles-{drawing.stem}.scr"
    script.write_text(ScriptRenderer().render_handles(capability.plugin), encoding="mbcs")
    completed = CoreConsoleExecutor().run(capability, drawing, script, timeout)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return parse_handles(drawing.with_suffix(".dst-handles.txt").read_text(encoding="utf-8"))
