"""创建暂存工作单元：隔离 attempt 中的候选成果（PLAN-DM-036 Task 5）。

覆盖 brief Step 1 的两个逐字用例（每组一个主 DWG、Handle 总数 = 总张数），以及
本任务的核心安全不变量：

- 候选物全部落在 Manager 应用数据目录下的独立 attempt 暂存目录，**不写目标项目
  目录**，暂存区之外不留任何文件；
- 布局模板的真实布局集合必须包含标准声明的图幅，DWG 实际布局集合必须与计划逐项
  一致，否则整个任务失败；
- 非法/占位/重复 Handle 一律拒绝；
- 任何一步失败只留隔离 attempt 日志，不产出半成品候选。

测试不启动 AutoCAD：`LayoutCreationWorker` 注入模拟 Core Console 的替身执行器，
真实跑通「渲染固定 SCR → 写脚本 → 解析 sidecar → 回读布局与 Handle」的代码路径。
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from dst_manager.application.creation_job import (
    CREATION_JOBS_DIR_NAME,
    CreationJobError,
    CreationJobRunner,
)
from dst_manager.domain.creation import CreationDraft, CreationGroupInput
from dst_manager.domain.creation_plan_models import (
    CreationPlan,
    CreationPlanDiagnostic,
)
from dst_manager.domain.creation_planning import create_creation_plan
from dst_manager.domain.models import SuffixOptions
from dst_manager.domain.standards import parse_published_standard_document
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.acsm_xml.creation import (
    CREATION_DST_NAME,
    STANDARD_IDENTITY_PROPERTY,
    STANDARD_OPTIONS_PROPERTY,
)
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    LayoutCreationWorker,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.publisher import file_sha256
from dst_platform.autocad.process import CoreConsoleResult

#: 夹具标准与 Task 2/4 同一份：两个 sheetset 普通属性、一个 sheetset 派生映射、
#: 一个 sheet 普通文本、一个 sheet 普通枚举、一个 sheet 派生组合，两个模板资产。
STANDARD_DOCUMENT: dict[str, object] = {
    "schema_version": 1,
    "standard_id": "szmedi.gas",
    "version": "2.1.0",
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
            "property_id": "prop-major",
            "name": "专业",
            "scope": "sheetset",
            "kind": "enum",
            "required": True,
            "default_value": "燃气",
            "enum_items": [
                {"item_id": "enum-gas", "value": "燃气"},
                {"item_id": "enum-oil", "value": "燃油"},
            ],
        },
        {
            "property_id": "prop-code",
            "name": "专业代码",
            "scope": "sheetset",
            "kind": "mapping",
            "source_property_id": "prop-major",
            "mapping": [
                {"item_id": "enum-gas", "value": "RQ"},
                {"item_id": "enum-oil", "value": "RY"},
            ],
            "confirmed_source_items": [["enum-gas", "燃气"], ["enum-oil", "燃油"]],
        },
        {
            "property_id": "prop-stage",
            "name": "设计阶段",
            "scope": "sheet",
            "kind": "text",
            "default_value": "施工图",
        },
        {
            "property_id": "prop-part",
            "name": "分部",
            "scope": "sheet",
            "kind": "enum",
            "enum_items": [
                {"item_id": "enum-part-a", "value": "A 段"},
                {"item_id": "enum-part-b", "value": "B 段"},
            ],
        },
        {
            "property_id": "prop-label",
            "name": "图签",
            "scope": "sheet",
            "kind": "composition",
            "segments": [
                {"property_id": "prop-code"},
                {"literal": "-"},
                {"system_field": "sheet.number"},
            ],
        },
    ],
    "dwg_naming": {
        "segments": [
            {"property_id": "prop-code"},
            {"literal": "-"},
            {"system_field": "subset.scope"},
            {"literal": " "},
            {"system_field": "subset.name"},
        ]
    },
    "assets": [
        {
            "asset_id": "base-a1",
            "kind": "base-template",
            "files": [{"path": "templates/a1.dwt", "role": ""}],
        },
        {
            "asset_id": "layout-a1",
            "kind": "layout-template",
            "files": [{"path": "templates/a1-layout.dwt", "role": "A1"}],
        },
    ],
    "numbering": {"sequence_field": "subset.sequence", "digits": 2},
}

STANDARD = parse_published_standard_document(STANDARD_DOCUMENT)
TARGET_PATH = r"C:\Projects\新建项目"
STANDARD_IDENTITY = "szmedi.gas@2.1.0"
#: 布局模板真实布局集合：包含标准声明的图幅 A1（另有 A0 与 Model）。
TEMPLATE_LAYOUTS = ("A1", "A0", "Model")
#: 每个主 DWG 的布局集合：与计划逐项一致。
GROUP_LAYOUTS = {
    "RQ-01-02 平面图.dwg": ("01 平面图", "02 平面图"),
    "RQ-03 剖面图.dwg": ("03 剖面图",),
}
EXPECTED_SHEET_PROPERTIES = [
    {"设计阶段": "施工图", "分部": "A 段", "图签": "RQ-01"},
    {"设计阶段": "施工图", "分部": "A 段", "图签": "RQ-02"},
    {"设计阶段": "施工图", "分部": "B 段", "图签": "RQ-03"},
]


class FakeCadExecutor:
    """模拟 Core Console 插件：按图纸写出布局清单/Handle sidecar，不启动 AutoCAD。

    与真实插件同一套 sidecar 协议（`.dst-layout-names.json` 与 `.dst-handles.txt`），
    因此被测试的是真实的脚本渲染、执行调用与结果解析路径。
    """

    def __init__(
        self,
        layouts_for: Callable[[Path], Sequence[str]],
        handles: Mapping[str, str] | None = None,
    ) -> None:
        self.layouts_for = layouts_for
        self.handles = dict(handles or {})
        self.calls: list[Path] = []

    def run(
        self, capability: CadCapability, drawing: Path, script: Path, timeout: int
    ) -> CoreConsoleResult:
        self.calls.append(drawing)
        layouts = list(self.layouts_for(drawing))
        handles = {
            name: self.handles.get(name) or f"{0x100 + index:X}"
            for index, name in enumerate(layouts)
        }
        drawing.with_suffix(".dst-layout-names.json").write_text(
            json.dumps({"version": 1, "layouts": layouts}, ensure_ascii=False),
            encoding="utf-8",
        )
        drawing.with_suffix(".dst-handles.txt").write_text(
            "\n".join(sorted(f"{name}={handle}" for name, handle in handles.items()))
            + "\n",
            encoding="utf-8",
        )
        return CoreConsoleResult([str(script)], 0, "", "", 1, None)


def _layouts_for(drawing: Path) -> Sequence[str]:
    """模板副本（attempt 的 input 目录）返回模板布局；主 DWG 返回该组计划布局。"""
    if drawing.parent.name == "input":
        return TEMPLATE_LAYOUTS
    return GROUP_LAYOUTS[drawing.name]


def _draft() -> CreationDraft:
    return CreationDraft(
        id="draft-1",
        standard_id="szmedi.gas",
        standard_version="2.1.0",
        revision=1,
        step="review",
        target_path=TARGET_PATH,
        sheetset_values={"prop-name": "示例工程", "prop-major": "燃气"},
        groups=(
            CreationGroupInput(
                group_id="group-1",
                created_order=1,
                title="平面图",
                count=2,
                base_asset_id="base-a1",
                layout_asset_id="layout-a1",
                paper_layout="A1",
                sheet_values={"prop-stage": "施工图", "prop-part": "A 段"},
            ),
            CreationGroupInput(
                group_id="group-2",
                created_order=2,
                title="剖面图",
                count=1,
                base_asset_id="base-a1",
                layout_asset_id="layout-a1",
                paper_layout="A1",
                sheet_values={"prop-stage": "施工图", "prop-part": "B 段"},
            ),
        ),
    )


@pytest.fixture
def plan() -> CreationPlan:
    result = create_creation_plan(_draft(), STANDARD, SuffixOptions(False, 1, ()))
    assert result.diagnostics == ()
    return result


@pytest.fixture
def capability(tmp_path: Path) -> CadCapability:
    """能力可用（Core Console 与插件文件存在）：进程执行由替身接管。"""
    directory = tmp_path / "cad"
    directory.mkdir()
    console = directory / "accoreconsole.exe"
    plugin = directory / "DstManager.AutoCAD.dll"
    console.write_bytes(b"fake-console")
    plugin.write_bytes(b"fake-plugin")
    return CadCapability("2020", console, plugin)


@pytest.fixture
def package_root(tmp_path: Path) -> Path:
    """标准包根：基础模板与布局模板按声明路径真实存在。"""
    root = tmp_path / "package"
    templates = root / "templates"
    templates.mkdir(parents=True)
    (templates / "a1.dwt").write_bytes(b"base-template")
    (templates / "a1-layout.dwt").write_bytes(b"layout-template")
    return root


@pytest.fixture
def executor() -> FakeCadExecutor:
    return FakeCadExecutor(_layouts_for)


@pytest.fixture
def runner(
    tmp_path: Path,
    package_root: Path,
    capability: CadCapability,
    executor: FakeCadExecutor,
) -> CreationJobRunner:
    return CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
    )


def _attempt_dir(tmp_path: Path, job_id: str = "job-1", attempt: int = 1) -> Path:
    return (
        tmp_path
        / "data"
        / CREATION_JOBS_DIR_NAME
        / job_id
        / f"attempt-{attempt:03d}"
    )


def _stray_files(tmp_path: Path) -> list[Path]:
    """暂存数据目录、标准包与 CAD 能力目录之外的文件（必须为空）。"""
    allowed = (tmp_path / "data", tmp_path / "package", tmp_path / "cad")
    return [
        path
        for path in tmp_path.rglob("*")
        if path.is_file() and not any(path.is_relative_to(root) for root in allowed)
    ]


def test_staged_candidate_has_one_dwg_per_group_and_all_layout_handles(
    runner, plan
) -> None:
    candidate = runner.stage("job-1", 1, plan)
    assert len(candidate.dwgs) == len(plan.groups)
    assert len(candidate.handles) == sum(group.sheet_count for group in plan.groups)


def test_candidate_stays_inside_the_isolated_attempt_directory(
    runner, plan, tmp_path
) -> None:
    candidate = runner.stage("job-1", 1, plan)
    attempt_dir = _attempt_dir(tmp_path)
    assert candidate.attempt_dir == attempt_dir
    assert candidate.dst_name == CREATION_DST_NAME
    assert candidate.dst_path == attempt_dir / "staging" / "final-dst" / CREATION_DST_NAME
    assert candidate.dst_path.is_file()
    assert [item.staged_path for item in candidate.dwgs] == [
        attempt_dir / "staging" / f"group-{index:03d}" / group.dwg_name
        for index, group in enumerate(plan.groups)
    ]
    assert all(item.staged_path.is_file() for item in candidate.dwgs)
    assert [item.file_name for item in candidate.dwgs] == [
        group.dwg_name for group in plan.groups
    ]
    assert candidate.target_path == TARGET_PATH
    # 目标项目目录绝不被创建或写入，暂存区之外不留任何文件
    assert not Path(TARGET_PATH).exists()
    assert _stray_files(tmp_path) == []


def test_staged_dst_roundtrip_matches_plan_and_records_report(
    runner, plan, tmp_path
) -> None:
    candidate = runner.stage("job-1", 1, plan)
    document = load_acsm(DstCodec().decode_file(candidate.dst_path))
    assert document.repair_report.status == "VALID"
    assert document.validate() == []
    projected = document.project(Path(plan.target_path))
    assert projected.name == Path(plan.target_path).name
    assert [subset.name for subset in projected.subsets] == [
        group.title for group in plan.groups
    ]
    sheets = projected.sheets
    assert [(sheet.number, sheet.title) for sheet in sheets] == [
        (sheet.number, sheet.title)
        for group in plan.groups
        for sheet in group.sheets
    ]
    assert [sheet.layout.layout_name for sheet in sheets] == [
        sheet.layout_name for group in plan.groups for sheet in group.sheets
    ]
    assert [sheet.layout.file_name for sheet in sheets] == [
        group.target_path for group in plan.groups for _ in group.sheets
    ]
    assert [sheet.layout.relative_file_name for sheet in sheets] == [
        ".\\" + group.dwg_name for group in plan.groups for _ in group.sheets
    ]
    assert [sheet.layout.handle for sheet in sheets] == list(candidate.handles.values())
    assert [sheet.custom_properties for sheet in sheets] == EXPECTED_SHEET_PROPERTIES
    assert projected.custom_properties[STANDARD_IDENTITY_PROPERTY] == STANDARD_IDENTITY
    assert projected.custom_properties[STANDARD_OPTIONS_PROPERTY] == (
        '{"numbering":{"digits":2,"sequence_field":"subset.sequence","start":1},'
        '"suffix":{"enabled":false,"suffix_type":1,"unnumbered_keywords":[]},"version":1}'
    )
    # 最终布局/Handle 清单
    assert set(candidate.layouts.values()) == {
        sheet.layout_name for group in plan.groups for sheet in group.sheets
    }
    assert set(candidate.handles) == {sheet.acsm_id for sheet in sheets}
    # Handle 唯一性按单个主 DWG 判定（不同 DWG 允许出现相同数值）
    for subset in projected.subsets:
        group_handles = [sheet.layout.handle for sheet in subset.sheets]
        assert len(set(group_handles)) == len(group_handles)
    # 校验报告
    assert candidate.report.repair_status == "VALID"
    assert candidate.report.semantic_issue_codes == ()
    assert candidate.report.dwg_count == len(plan.groups)
    assert candidate.report.sheet_count == len(sheets)
    assert candidate.report.encoded_sha256 == file_sha256(candidate.dst_path)


def test_retry_uses_a_new_attempt_directory(runner, plan, tmp_path) -> None:
    first = runner.stage("job-1", 1, plan)
    second = runner.stage("job-1", 2, plan)
    assert first.attempt_dir != second.attempt_dir
    assert first.dst_path.is_file() and second.dst_path.is_file()
    assert second.attempt_dir == _attempt_dir(tmp_path, attempt=2)


def test_layout_template_without_declared_paper_layout_fails_whole_task(
    tmp_path, package_root, capability, plan
) -> None:
    executor = FakeCadExecutor(
        lambda drawing: ("A0", "Model")
        if drawing.parent.name == "input"
        else GROUP_LAYOUTS[drawing.name]
    )
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
    )
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage("job-1", 1, plan)
    assert excinfo.value.code == "CREATION_LAYOUT_TEMPLATE_MISMATCH"
    attempt_dir = _attempt_dir(tmp_path)
    assert not (attempt_dir / "staging" / "final-dst").exists()
    assert "CREATION_LAYOUT_TEMPLATE_MISMATCH" in (
        attempt_dir / "logs" / "creation.log"
    ).read_text(encoding="utf-8")
    assert not Path(TARGET_PATH).exists()
    assert _stray_files(tmp_path) == []


def test_dwg_layout_set_mismatch_is_rejected(
    tmp_path, package_root, capability, plan
) -> None:
    executor = FakeCadExecutor(
        lambda drawing: TEMPLATE_LAYOUTS
        if drawing.parent.name == "input"
        else ("01 平面图",)
    )
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
    )
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage("job-1", 1, plan)
    assert excinfo.value.code == "CREATION_LAYOUT_SET_MISMATCH"
    assert not (_attempt_dir(tmp_path) / "staging" / "final-dst").exists()
    assert not Path(TARGET_PATH).exists()


@pytest.mark.parametrize(
    ("case", "handles", "expected_code"),
    [
        ("zero", {"01 平面图": "0"}, "CREATION_HANDLE_INVALID"),
        ("duplicate", {"01 平面图": "1", "02 平面图": "1"}, "CREATION_HANDLE_INVALID"),
        ("not-hex", {"01 平面图": "ZZ"}, "CREATION_HANDLE_INVALID"),
        ("placeholder", {"01 平面图": "FFFFFFFFFFFFFFFF"}, "CREATION_HANDLE_PLACEHOLDER"),
    ],
)
def test_illegal_handles_are_rejected(
    tmp_path, package_root, capability, plan, case, handles, expected_code
) -> None:
    executor = FakeCadExecutor(_layouts_for, handles=handles)
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
    )
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage("job-1", 1, plan)
    assert excinfo.value.code == expected_code
    assert not (_attempt_dir(tmp_path) / "staging" / "final-dst").exists()
    assert not Path(TARGET_PATH).exists()


def test_cad_failure_leaves_only_the_isolated_attempt_log(
    tmp_path, package_root, capability, plan
) -> None:
    class FailingExecutor:
        def run(self, capability, drawing, script, timeout):
            raise RuntimeError("CAD_CAPABILITY_UNAVAILABLE: 2020")

    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=FailingExecutor()),
        timeout=60,
    )
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage("job-1", 1, plan)
    assert excinfo.value.code == "CREATION_CAD_UNAVAILABLE"
    attempt_dir = _attempt_dir(tmp_path)
    assert "CREATION_CAD_UNAVAILABLE" in (attempt_dir / "logs" / "creation.log").read_text(
        encoding="utf-8"
    )
    assert not (attempt_dir / "staging" / "final-dst").exists()
    assert not Path(TARGET_PATH).exists()
    assert _stray_files(tmp_path) == []


def test_missing_asset_file_fails_before_any_cad_call(
    tmp_path, capability, executor, plan
) -> None:
    empty_root = tmp_path / "empty-package"
    empty_root.mkdir()
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=empty_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
    )
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage("job-1", 1, plan)
    assert excinfo.value.code == "CREATION_ASSET_FILE_MISSING"
    assert executor.calls == []


def test_plan_with_diagnostics_is_rejected_without_touching_disk(
    runner, plan, tmp_path
) -> None:
    broken = replace(
        plan,
        diagnostics=(
            CreationPlanDiagnostic("CREATION_REQUIRED_VALUE_MISSING", "缺必填值"),
        ),
    )
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage("job-1", 1, broken)
    assert excinfo.value.code == "CREATION_PLAN_INVALID"
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("job_id", ["../escape", "", "a/b", "a" * 65, "作业"])
def test_unsafe_job_id_is_rejected_without_touching_disk(
    runner, plan, tmp_path, job_id
) -> None:
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage(job_id, 1, plan)
    assert excinfo.value.code == "CREATION_JOB_ID_INVALID"
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("attempt", [0, -1])
def test_illegal_attempt_is_rejected_without_touching_disk(
    runner, plan, tmp_path, attempt
) -> None:
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage("job-1", attempt, plan)
    assert excinfo.value.code == "CREATION_ATTEMPT_INVALID"
    assert not (tmp_path / "data").exists()
