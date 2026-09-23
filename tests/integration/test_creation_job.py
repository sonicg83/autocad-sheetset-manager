"""创建暂存工作单元：隔离 attempt 中的候选成果（PLAN-DM-036 Task 5）。

覆盖 brief Step 1 的两个逐字用例（每组一个主 DWG、Handle 总数 = 总张数），以及
本任务的核心安全不变量：

- 候选物全部落在 Manager 应用数据目录下的独立 attempt 暂存目录，**不写目标项目
  目录**，暂存区之外不留任何文件；
- 布局模板的真实布局集合必须包含标准声明的图幅，DWG 实际布局集合必须与计划逐项
  一致，否则整个任务失败；
- 非法/占位/重复 Handle 一律拒绝；
- 任何一步失败只留隔离 attempt 日志，不产出半成品候选。

Task 6 追加：`CreationJobRunner.run` 把候选**可恢复地发布**到新项目目录，并在普通
工作区尚不存在时仍能记录任务状态/进度/时间线与失败诊断；发布失败按现场结论回滚为
`ROLLED_BACK` 或隔离为 `NEEDS_REVIEW`；重试严格使用新 attempt 目录。

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
from dst_manager.infrastructure.filesystem.project_publish_types import (
    ProjectPublishError,
)
from dst_manager.infrastructure.filesystem.project_publisher import ProjectPublisher
from dst_manager.infrastructure.filesystem.publisher import file_sha256
from dst_manager.infrastructure.persistence.database import Database
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


class FailingCadExecutor:
    """模拟 CAD 能力不可用：任何执行都失败，用于验证失败路径与重试。"""

    def run(self, capability, drawing, script, timeout):
        raise RuntimeError("CAD_CAPABILITY_UNAVAILABLE: 2020")


class FailAfterFirstCommit:
    """发布事务故障注入：第 1 个文件提交后失败（触发按身份回滚）。"""

    def at_stage(self, stage: str) -> None:
        return None

    def after_commit(self, target: Path) -> None:
        raise ProjectPublishError("CREATION_PUBLISH_FAILED", "注入提交失败")


class ExternalContentAfterFirstCommit:
    """发布事务故障注入：提交第 1 个文件后写入外部内容并失败（回滚必须停手）。"""

    def __init__(self) -> None:
        self._fired = False

    def at_stage(self, stage: str) -> None:
        return None

    def after_commit(self, target: Path) -> None:
        if self._fired:
            return
        self._fired = True
        (target.parent / "外部.dwg").write_bytes(b"external")
        raise ProjectPublishError("CREATION_PUBLISH_FAILED", "注入提交失败")


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
def tmp_plan(tmp_path: Path) -> CreationPlan:
    """目标落在 tmp_path 内的计划：Task 6 的发布测试必须真实写盘且不依赖本机路径。"""
    draft = replace(_draft(), target_path=str(tmp_path / "projects" / "新建项目"))
    result = create_creation_plan(draft, STANDARD, SuffixOptions(False, 1, ()))
    assert result.diagnostics == ()
    return result


@pytest.fixture
def database(tmp_path: Path) -> Database:
    # 库文件落在 Manager 应用数据目录内：测试同时断言「暂存区之外零文件」。
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Database(f"sqlite:///{(data_dir / 'dst-manager.db').as_posix()}")


@pytest.fixture
def publisher() -> ProjectPublisher:
    return ProjectPublisher()


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
    database: Database,
    publisher: ProjectPublisher,
) -> CreationJobRunner:
    return CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
        database=database,
        publisher=publisher,
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
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=FailingCadExecutor()),
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
    assert not (tmp_path / "data" / CREATION_JOBS_DIR_NAME).exists()


@pytest.mark.parametrize("job_id", ["../escape", "", "a/b", "a" * 65, "作业"])
def test_unsafe_job_id_is_rejected_without_touching_disk(
    runner, plan, tmp_path, job_id
) -> None:
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage(job_id, 1, plan)
    assert excinfo.value.code == "CREATION_JOB_ID_INVALID"
    assert not (tmp_path / "data" / CREATION_JOBS_DIR_NAME).exists()


@pytest.mark.parametrize("attempt", [0, -1])
def test_illegal_attempt_is_rejected_without_touching_disk(
    runner, plan, tmp_path, attempt
) -> None:
    with pytest.raises(CreationJobError) as excinfo:
        runner.stage("job-1", attempt, plan)
    assert excinfo.value.code == "CREATION_ATTEMPT_INVALID"
    assert not (tmp_path / "data" / CREATION_JOBS_DIR_NAME).exists()


# ---- Task 6：创建任务状态、可恢复发布与重试 ---------------------------------


CREATION_DRAFT_ID = "draft-1"
PREVIEW_DIGEST = "digest-1"


def _create_creation_job(
    database: Database,
    plan: CreationPlan,
    *,
    job_id: str = "job-1",
    draft_id: str = CREATION_DRAFT_ID,
    digest: str = PREVIEW_DIGEST,
) -> None:
    """建一个创建任务：没有普通工作区，只有草稿身份与预览摘要。"""
    database.create_job(
        job_id,
        None,
        "creation",
        "QUEUED",
        {
            "creation_draft_id": draft_id,
            "preview_digest": digest,
            "target_path": plan.target_path,
        },
        cad_version="2020",
        creation_draft_id=draft_id,
    )


def _claim(database: Database, *, job_id: str = "job-1", worker: str = "worker-1") -> dict:
    job = database.claim_next_job(worker)
    assert job is not None and job["id"] == job_id
    return job


def _published_names(target: Path) -> list[str]:
    return sorted(item.name for item in target.iterdir())


def test_run_publishes_the_candidate_and_closes_the_job_without_workspace(
    tmp_path, runner, database, tmp_plan
) -> None:
    _create_creation_job(database, tmp_plan)
    job = _claim(database)

    result = runner.run(job["id"], job["attempt"], tmp_plan)

    target = Path(tmp_plan.target_path)
    assert result["status"] == "SUCCEEDED"
    assert result["progress"] == 100
    assert result["workspace_id"] is None
    assert result["creation_draft_id"] == CREATION_DRAFT_ID
    assert result["error_code"] is None
    assert [item["status"] for item in result["timeline"]] == [
        "QUEUED",
        "STAGING",
        "CAD_RUNNING",
        "VERIFYING",
        "PREPARED",
        "PUBLISHING",
        "SUCCEEDED",
    ]
    assert _published_names(target) == sorted(
        [CREATION_DST_NAME, *(group.dwg_name for group in tmp_plan.groups)]
    )
    published = result["payload"]["published"]
    assert published["target_dir"] == str(target)
    assert published["dst_path"] == str(target / CREATION_DST_NAME)
    assert published["target_state"] == "missing"
    assert [item["role"] for item in published["files"]] == ["dst", "dwg", "dwg"]
    assert all(len(item["sha256"]) == 64 for item in published["files"])
    # 发布日志与修订证据落在 Manager 应用数据目录的 attempt 命名空间
    assert Path(published["journal_path"]) == _attempt_dir(tmp_path) / "publish-journal.json"
    assert Path(published["revision_dir"]) == _attempt_dir(tmp_path) / "revision"


def test_run_records_failure_diagnostics_without_workspace(
    tmp_path, database, package_root, capability, tmp_plan
) -> None:
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=FailingCadExecutor()),
        timeout=60,
        database=database,
        publisher=ProjectPublisher(),
    )
    _create_creation_job(database, tmp_plan)
    job = _claim(database)

    result = runner.run(job["id"], job["attempt"], tmp_plan)

    assert result["status"] == "FAILED"
    assert result["workspace_id"] is None
    assert result["error_code"] == "CREATION_CAD_UNAVAILABLE"
    assert "CAD_CAPABILITY_UNAVAILABLE" in result["error_detail"]
    assert not Path(tmp_plan.target_path).exists()
    assert "CREATION_CAD_UNAVAILABLE" in (
        _attempt_dir(tmp_path) / "logs" / "creation.log"
    ).read_text(encoding="utf-8")


def test_retry_after_failure_uses_a_new_attempt_directory(
    tmp_path, database, package_root, capability, executor, tmp_plan
) -> None:
    failing = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=FailingCadExecutor()),
        timeout=60,
        database=database,
        publisher=ProjectPublisher(),
    )
    _create_creation_job(database, tmp_plan)
    first = _claim(database)
    failed = failing.run(first["id"], first["attempt"], tmp_plan)
    assert failed["status"] == "FAILED" and failed["attempt"] == 1

    assert database.retry_job("job-1")["status"] == "QUEUED"
    retried = _claim(database, worker="worker-2")
    assert retried["attempt"] == 2

    working = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
        database=database,
        publisher=ProjectPublisher(),
    )
    result = working.run(retried["id"], retried["attempt"], tmp_plan)

    assert result["status"] == "SUCCEEDED" and result["attempt"] == 2
    assert (_attempt_dir(tmp_path, attempt=1) / "logs" / "creation.log").is_file()
    assert (_attempt_dir(tmp_path, attempt=2) / "revision" / "manifest.json").is_file()


def test_publish_failure_rolls_back_and_marks_the_job_rolled_back(
    tmp_path, database, package_root, capability, executor, tmp_plan
) -> None:
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
        database=database,
        publisher=ProjectPublisher(fault_injector=FailAfterFirstCommit()),
    )
    _create_creation_job(database, tmp_plan)
    job = _claim(database)

    result = runner.run(job["id"], job["attempt"], tmp_plan)

    assert result["status"] == "ROLLED_BACK"
    assert result["error_code"] == "CREATION_PUBLISH_FAILED"
    assert not Path(tmp_plan.target_path).exists()
    assert [item["status"] for item in result["timeline"]][-1] == "ROLLED_BACK"


def test_external_content_during_rollback_marks_the_job_needs_review(
    tmp_path, database, package_root, capability, executor, tmp_plan
) -> None:
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
        database=database,
        publisher=ProjectPublisher(
            fault_injector=ExternalContentAfterFirstCommit()
        ),
    )
    _create_creation_job(database, tmp_plan)
    job = _claim(database)

    result = runner.run(job["id"], job["attempt"], tmp_plan)

    target = Path(tmp_plan.target_path)
    assert result["status"] == "NEEDS_REVIEW"
    assert result["error_code"] == "CREATION_PUBLISH_REVIEW_REQUIRED"
    assert _published_names(target) == ["外部.dwg"]
    assert (target / "外部.dwg").read_bytes() == b"external"
    # 现场与日志保留：人工核对依据不被自动清理
    assert (_attempt_dir(tmp_path) / "publish-journal.json").is_file()


def test_run_requires_a_task_database_and_publisher(tmp_path, package_root, capability, executor, tmp_plan) -> None:
    runner = CreationJobRunner(
        data_dir=tmp_path / "data",
        asset_root=package_root,
        worker=LayoutCreationWorker(capability, executor=executor),
        timeout=60,
    )

    with pytest.raises(CreationJobError) as excinfo:
        runner.run("job-1", 1, tmp_plan)

    assert excinfo.value.code == "CREATION_JOB_NOT_RUNNABLE"
    assert not Path(tmp_plan.target_path).exists()


class ProcessInterrupted(BaseException):
    """模拟进程在发布中途被终止（不触发回滚，只留持久日志现场）。"""


class InterruptAtPublishing:
    """在写入 PUBLISHING 日志后终止进程。"""

    def at_stage(self, stage: str) -> None:
        if stage == "PUBLISHING":
            raise ProcessInterrupted("注入进程中断：PUBLISHING")

    def after_commit(self, target: Path) -> None:
        return None


def _interrupted_creation_job(tmp_path, runner, tmp_plan, job_id: str = "job-1"):
    """在 PUBLISHING 中断一次创建发布，并返回服务重启前的持久化身份。"""
    from dst_manager.application.service import DstManagerService
    from dst_manager.config import Settings

    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    candidate = runner.stage(job_id, 1, tmp_plan)
    target = Path(tmp_plan.target_path)
    interrupted = ProjectPublisher(fault_injector=InterruptAtPublishing())
    with pytest.raises(ProcessInterrupted):
        interrupted.publish_new_project(candidate, target, job_id, 1)
    service.database.create_job(
        job_id,
        None,
        "creation",
        "PUBLISHING",
        {"creation_draft_id": CREATION_DRAFT_ID, "preview_digest": PREVIEW_DIGEST},
        cad_version="2020",
        creation_draft_id=CREATION_DRAFT_ID,
    )
    with service.database.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE jobs SET worker_id='worker-1', attempt=1 WHERE id=?", (job_id,)
        )
    return settings, target


def test_startup_recovery_rolls_back_interrupted_creation_publish(
    tmp_path, runner, tmp_plan
) -> None:
    """进程中断（PUBLISHING）后重启：目标恢复原状态，任务落可核对终态。"""
    from dst_manager.application.service import DstManagerService

    settings, target = _interrupted_creation_job(tmp_path, runner, tmp_plan)
    assert target.is_dir() and list(target.iterdir()) == []

    restarted = DstManagerService(settings)

    job = restarted.database.get_job("job-1")
    assert job["status"] == "ROLLED_BACK"
    assert job["error_code"] == "STARTUP_RECOVERY"
    assert job["workspace_id"] is None
    assert not target.exists()
    # 日志与现场保留，供人工核对
    assert (_attempt_dir(tmp_path) / "publish-journal.json").is_file()


def test_startup_recovery_marks_needs_review_when_external_content_appeared(
    tmp_path, runner, tmp_plan
) -> None:
    """中断后目标出现外部内容：停止自动清理、保留日志并标记 NEEDS_REVIEW。"""
    from dst_manager.application.service import DstManagerService

    settings, target = _interrupted_creation_job(tmp_path, runner, tmp_plan)
    external = target / "外部.dwg"
    external.write_bytes(b"external")

    restarted = DstManagerService(settings)

    job = restarted.database.get_job("job-1")
    assert job["status"] == "NEEDS_REVIEW"
    assert job["error_code"] == "CREATION_PUBLISH_REVIEW_REQUIRED"
    assert external.read_bytes() == b"external"
    assert _published_names(target) == ["外部.dwg"]


def test_startup_recovery_closes_committed_creation_publish(
    tmp_path, runner, tmp_plan
) -> None:
    """已提交但未闭环的创建发布：启动恢复幂等补齐成功状态，绝不重发成果。"""
    from dst_manager.application.service import DstManagerService
    from dst_manager.config import Settings

    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    candidate = runner.stage("job-1", 1, tmp_plan)
    target = Path(tmp_plan.target_path)
    published = ProjectPublisher().publish_new_project(candidate, target, "job-1", 1)
    service.database.create_job(
        "job-1",
        None,
        "creation",
        "PUBLISHING",
        {"creation_draft_id": CREATION_DRAFT_ID},
        cad_version="2020",
        creation_draft_id=CREATION_DRAFT_ID,
    )

    restarted = DstManagerService(settings)

    job = restarted.database.get_job("job-1")
    assert job["status"] == "SUCCEEDED"
    assert job["progress"] == 100
    assert job["workspace_id"] is None
    assert job["payload"]["published"]["target_dir"] == str(target)
    assert _published_names(target) == sorted(
        [CREATION_DST_NAME, *(group.dwg_name for group in tmp_plan.groups)]
    )
    assert published.revision_dir.is_dir()


def test_startup_recovery_quarantines_unprovable_creation_journal(
    tmp_path, runner, tmp_plan
) -> None:
    """日志身份被改写：只按受控目录层级隔离任务，不做任何猜测性清理。"""
    import json as json_module

    from dst_manager.application.service import DstManagerService

    settings, target = _interrupted_creation_job(tmp_path, runner, tmp_plan)
    journal_path = _attempt_dir(tmp_path) / "publish-journal.json"
    journal = json_module.loads(journal_path.read_text(encoding="utf-8"))
    journal["attempt"] = 9
    journal_path.write_text(
        json_module.dumps(journal, ensure_ascii=False), encoding="utf-8"
    )

    restarted = DstManagerService(settings)

    job = restarted.database.get_job("job-1")
    assert job["status"] == "NEEDS_REVIEW"
    assert job["error_code"] == "PUBLISH_MANIFEST_IMMUTABLE_MISMATCH"
    assert target.is_dir() and list(target.iterdir()) == []
    assert journal_path.is_file()
