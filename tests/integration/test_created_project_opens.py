"""创建成果接管为普通工作区：登记、初始修订与重新打开（PLAN-DM-036 Task 7）。

覆盖 brief Step 1 的两个逐字用例，以及本任务的核心安全不变量：

- 只在项目文件完整发布之后登记普通工作区、项目内标准快照、有效编号配置与初始
  修订；对外成功响应（任务终态 + ``workspace_id``/``revision_id``/``dst_path``）
  必须在文件、SQLite 与修订清单一致且工作区能重新打开之后才产生；
- 登记失败保留已发布文件、发布日志与修订证据，任务落 ``NEEDS_REVIEW`` 而不是
  ``SUCCEEDED``；启动恢复按持久日志幂等补登记，绝不重新生成或覆盖 DWG；
- 标准库中的版本被删除后，工作区语义仍由项目内快照恢复（不因库缺失拒绝打开）。

测试不启动 AutoCAD：创建执行链的 CAD 能力由模拟 Core Console 的替身执行器接管
（与 ``test_creation_job.py`` 同一套 sidecar 协议），其余全部走真实服务路径
（``execute_creation`` → ``run_next_job`` → 隔离暂存 → 发布 → 登记）。夹具只用
``tmp_path``，不依赖用户本地数据库或上次运行残留。
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dst_manager.application.creation_job import CreationJobRunner
from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.domain.creation import CreationDraft, CreationGroupInput
from dst_manager.domain.creation_plan_models import CreationPlan
from dst_manager.domain.standards import parse_published_standard_document
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    LayoutCreationWorker,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.project_publish_types import PublishedProject
from dst_manager.infrastructure.filesystem.publisher import file_sha256
from dst_manager.interfaces.api import create_app
from dst_platform.autocad.process import CoreConsoleResult

#: 夹具标准：一个 sheetset 文本、一个 sheetset 枚举、一个 sheet 文本，一个基础模板
#: 与一个布局模板（声明图幅 A1），DWG 命名只用受控片段与系统字段。
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
            "asset_id": "base-a1",
            "kind": "base-template",
            "files": [{"path": "templates/base.dwt", "role": ""}],
        },
        {
            "asset_id": "layout-a1",
            "kind": "layout-template",
            "files": [{"path": "templates/layout.dwt", "role": "A1"}],
        },
    ],
    "numbering": {"sequence_field": "subset.sequence", "digits": 2},
}

#: 标准包内的受控资产（发布时随草稿目录一起落到 published 下）。
ASSET_FILES: dict[str, bytes] = {
    "templates/base.dwt": b"base-template",
    "templates/layout.dwt": b"layout-template",
}
#: 布局模板的真实布局集合：包含标准声明的图幅 A1。
TEMPLATE_LAYOUTS = ("A1", "A2", "A3", "Model")

STANDARD_IDENTITY = "szmedi.gas@2.1.0"
CREATION_JOB_ID = "job-1"
#: 项目内标准快照目录（brief Step 1 断言的精确位置）。
STANDARD_SNAPSHOT = ".dst-manager/standards/szmedi.gas/2.1.0"


class FakeCadExecutor:
    """模拟 Core Console 插件：按图纸写出布局清单/Handle sidecar，不启动 AutoCAD。

    与真实插件同一套 sidecar 协议（``.dst-layout-names.json`` 与
    ``.dst-handles.txt``），因此被测试的是真实的脚本渲染、执行调用与结果解析路径。
    """

    def __init__(self, group_layouts: Mapping[str, Sequence[str]]) -> None:
        self.group_layouts = dict(group_layouts)
        self.calls: list[Path] = []

    def run(
        self, capability: CadCapability, drawing: Path, script: Path, timeout: int
    ) -> CoreConsoleResult:
        self.calls.append(drawing)
        layouts = (
            list(TEMPLATE_LAYOUTS)
            if drawing.parent.name == "input"
            else list(self.group_layouts[drawing.name])
        )
        handles = {name: f"{0x100 + index:X}" for index, name in enumerate(layouts)}
        drawing.with_suffix(".dst-layout-names.json").write_text(
            json.dumps({"version": 1, "layouts": layouts}, ensure_ascii=False),
            encoding="utf-8",
        )
        drawing.with_suffix(".dst-handles.txt").write_text(
            "\n".join(f"{name}={handle}" for name, handle in handles.items()) + "\n",
            encoding="utf-8",
        )
        return CoreConsoleResult([str(script)], 0, "", "", 1, None)


class RegistrationFaultInjector:
    """登记阶段故障注入：在「发布成功 → 工作区登记」之间制造确定性失败。

    与发布事务的故障注入同一意图（``ProjectPublishFaultInjector``）：只在测试中
    安装，生产路径不注入。故障发生在登记第一步（打开已发布项目）之前，因此已发布
    成果、发布日志与修订证据全部保持完整，登记失败现场可被启动恢复补登记。
    """

    def __init__(self) -> None:
        self.armed = False

    def fail_before_workspace_registration(self) -> None:
        """武装故障：下一次登记在打开已发布项目之前失败。"""
        self.armed = True

    def heal(self) -> None:
        """撤除故障：登记恢复可用（用于验证幂等补登记）。"""
        self.armed = False


@dataclass(frozen=True, slots=True)
class CreationSite:
    """一次创建的现场：草稿身份、权威预览摘要、计划与替身 CAD 执行器。"""

    draft_id: str
    preview_digest: str
    plan: CreationPlan
    executor: FakeCadExecutor


@dataclass(frozen=True, slots=True)
class CompletedCreation:
    """已完成创建的任务身份：成功响应必须齐备的三个字段。"""

    job: dict[str, Any]
    workspace_id: str
    revision_id: str
    dst_path: str


@pytest.fixture
def service(tmp_path: Path) -> DstManagerService:
    """真实服务：标准已发布，数据目录与数据库全部落在 ``tmp_path``。"""
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    _publish_standard(service)
    return service


@pytest.fixture
def site(service: DstManagerService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CreationSite:
    """创建现场：草稿 + 预览摘要 + 计划 + 替身 CAD（接管服务执行链的 CAD 能力）。"""
    creation = _creation_site(service, tmp_path, target=tmp_path / "projects" / "新建项目")
    capability = _fake_capability(tmp_path)
    monkeypatch.setattr(
        "dst_manager.application.creation_execution.LayoutCreationWorker",
        lambda _capability: LayoutCreationWorker(capability, executor=creation.executor),
    )
    return creation


@pytest.fixture
def completed_creation(service: DstManagerService, site: CreationSite) -> CompletedCreation:
    """走完整创建链：入队 → 领取执行 → 隔离暂存 → 发布 → 登记。"""
    queued = service.execute_creation(site.draft_id, site.preview_digest)
    assert queued["status"] == "QUEUED" and queued["workspace_id"] is None

    result = service.run_next_job()

    assert result is not None and result["id"] == queued["id"]
    assert result["status"] == "SUCCEEDED", result["error_detail"]
    assert result["workspace_id"] is not None
    return CompletedCreation(
        job=result,
        workspace_id=result["workspace_id"],
        revision_id=result["payload"]["workspace"]["revision_id"],
        dst_path=result["payload"]["published"]["dst_path"],
    )


@pytest.fixture
def published_candidate(
    service: DstManagerService, site: CreationSite, tmp_path: Path
) -> PublishedProject:
    """已完整发布但尚未登记的候选成果：任务停在 ``PUBLISHING``，成果文件已落盘。"""
    runner = CreationJobRunner(
        data_dir=service.settings.data_dir,
        asset_root=_package_root(service),
        worker=LayoutCreationWorker(_fake_capability(tmp_path), executor=site.executor),
        timeout=60,
    )
    candidate = runner.stage(CREATION_JOB_ID, 1, site.plan)
    service.database.create_job(
        CREATION_JOB_ID,
        None,
        "creation",
        "PUBLISHING",
        {
            "creation_draft_id": site.draft_id,
            "preview_digest": site.preview_digest,
            "target_path": site.plan.target_path,
        },
        "2020",
        creation_draft_id=site.draft_id,
    )
    return service.project_publisher.publish_new_project(
        candidate, Path(site.plan.target_path), CREATION_JOB_ID, 1
    )


@pytest.fixture
def fault_injector(monkeypatch: pytest.MonkeyPatch) -> RegistrationFaultInjector:
    """登记阶段故障注入夹具：把登记第一步替换成可武装的故障。"""
    import dst_manager.application.creation_registration as registration_module

    injector = RegistrationFaultInjector()
    original = registration_module.CreationRegistrationOperations._register_published_workspace

    def guarded(self, published):
        if injector.armed:
            raise OSError("注入登记故障：工作区登记前失败")
        return original(self, published)

    monkeypatch.setattr(
        registration_module.CreationRegistrationOperations,
        "_register_published_workspace",
        guarded,
    )
    return injector


def test_created_project_opens_as_normal_workspace(service, completed_creation) -> None:
    workspace = service.get_workspace(completed_creation.workspace_id)
    assert workspace.document.custom_properties["DSTManager.Standard"] == "szmedi.gas@2.1.0"
    assert workspace.revision_id == completed_creation.revision_id
    assert (workspace.root / ".dst-manager/standards/szmedi.gas/2.1.0").is_dir()


def test_registration_failure_is_recoverable_not_successful(service, published_candidate, fault_injector) -> None:
    fault_injector.fail_before_workspace_registration()
    result = service.finish_creation(published_candidate)
    assert result.status == "NEEDS_REVIEW"
    assert result.workspace_id is None


# ---- 成功响应与登记产物 -----------------------------------------------------


def test_success_response_carries_workspace_revision_and_dst_path(
    service: DstManagerService, completed_creation: CompletedCreation
) -> None:
    job = completed_creation.job
    dst_path = Path(completed_creation.dst_path)

    assert job["status"] == "SUCCEEDED" and job["progress"] == 100
    assert job["workspace_id"] == completed_creation.workspace_id
    assert job["payload"]["workspace"] == {
        "id": completed_creation.workspace_id,
        "revision_id": completed_creation.revision_id,
        "dst_path": str(dst_path),
    }
    # 修订 ID 就是已发布 DST 的内容哈希（与工作区 current_revision 同一口径）
    assert completed_creation.revision_id == file_sha256(dst_path)
    assert dst_path.is_file() and dst_path.name == "图纸集数据文件.dst"
    # 登记行与任务行指向同一个工作区
    row = service.database.get_workspace(completed_creation.workspace_id)
    assert row is not None
    assert Path(row.dst_path).resolve() == dst_path.resolve()
    assert Path(row.root).resolve() == dst_path.parent.resolve()
    assert row.current_revision == completed_creation.revision_id


def test_initial_revision_matches_published_dst_and_records_effective_numbering(
    service: DstManagerService, completed_creation: CompletedCreation
) -> None:
    revisions = service.database.list_revisions(completed_creation.workspace_id)

    assert [item["id"] for item in revisions] == [completed_creation.revision_id]
    revision = revisions[0]
    assert revision["kind"] == "creation"
    assert revision["operation_id"] == completed_creation.job["id"]
    # 初始修订没有前序 DST：before_hash 记为空串，result_hash 与修订 ID 同值
    assert revision["before_hash"] == ""
    assert revision["result_hash"] == completed_creation.revision_id
    # 修订清单复用发布事务归档的同一份 manifest.json，不另立格式
    revision_dir = Path(revision["revision_dir"])
    assert revision_dir == Path(completed_creation.job["payload"]["published"]["revision_dir"])
    assert (revision_dir / "manifest.json").is_file()
    # 有效编号配置随初始修订留档（与 DST 保留属性同一份值）
    document = service.get_workspace(completed_creation.workspace_id).document
    options = json.loads(document.custom_properties["DSTManager.StandardOptions"])
    assert revision["source_json"] == {
        "schema": "dst-manager.creation-source/v1",
        "job_id": completed_creation.job["id"],
        "attempt": 1,
        "standard": STANDARD_IDENTITY,
        "numbering_options": options,
    }
    assert options["numbering"] == {
        "digits": 2,
        "sequence_field": "subset.sequence",
        "start": 1,
    }


def test_initial_creation_revision_is_not_a_restore_point(
    service: DstManagerService, completed_creation: CompletedCreation
) -> None:
    """创建初始修订不是恢复点：预览与执行都以稳定码 409 拒绝，成果零改动。

    创建修订的 ``revision_dir`` 是发布事务归档目录，其 manifest 条目没有永久
    before 快照（``project_publisher`` 只写 ``result_hash``）；若把它当恢复来源，
    既有恢复流程会按「无 backup 即删除」把它解释成删除全部已发布成果，并让项目
    DST 与主 DWG 被移出项目目录。因此预览与执行两条路径都必须拒绝。
    """
    workspace = service.get_workspace(completed_creation.workspace_id)
    dst_path = Path(completed_creation.dst_path)
    before_dst = file_sha256(dst_path)
    before_drawings = _drawing_hashes(workspace.root)
    assert before_drawings, "夹具必须真的产出主 DWG，否则零改动断言没有意义"

    with pytest.raises(ApplicationError) as preview_error:
        service.preview_revision_restore(
            completed_creation.workspace_id, completed_creation.revision_id
        )
    assert (preview_error.value.code, preview_error.value.status_code) == (
        "REVISION_NOT_RESTORABLE",
        409,
    )

    # 执行入口（可被直接调用，不经过界面）同样拒绝，不得进入删除分支
    with pytest.raises(ApplicationError) as restore_error:
        service.restore_revision(
            completed_creation.workspace_id,
            completed_creation.revision_id,
            base_revision_id=before_dst,
        )
    assert (restore_error.value.code, restore_error.value.status_code) == (
        "REVISION_NOT_RESTORABLE",
        409,
    )

    # 界面可达面（`/api/revisions` 逐条渲染恢复按钮）返回 409 + 稳定码
    client = TestClient(create_app(service.settings))
    response = client.get(
        f"/api/workspaces/{completed_creation.workspace_id}"
        f"/revisions/{completed_creation.revision_id}/restore-preview"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REVISION_NOT_RESTORABLE"

    # 项目 DST 与全部主 DWG 零改动，且没有恢复任务、没有残留写锁、修订历史不增长
    assert file_sha256(dst_path) == before_dst and dst_path.is_file()
    assert _drawing_hashes(workspace.root) == before_drawings
    assert len(service.database.list_revisions(completed_creation.workspace_id)) == 1
    with service.database.engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM jobs WHERE job_type = 'revision_restore'"
            ).scalar_one()
            == 0
        )
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM workspace_write_locks"
            ).scalar_one()
            == 0
        )


def test_created_project_references_the_published_drawings_and_handles(
    service: DstManagerService, completed_creation: CompletedCreation, site: CreationSite
) -> None:
    workspace = service.get_workspace(completed_creation.workspace_id)
    sheets = workspace.document.sheets

    assert len(sheets) == sum(group.sheet_count for group in site.plan.groups)
    assert [Path(sheet.layout.resolved_path).name for sheet in sheets] == [
        group.dwg_name for group in site.plan.groups for _ in group.sheets
    ]
    # 每组主 DWG 真实落盘，且 DST 里的 Handle 与布局名与计划一致
    for group in site.plan.groups:
        drawing = workspace.root / group.dwg_name
        assert drawing.is_file()
        group_sheets = [
            sheet
            for sheet in sheets
            if Path(sheet.layout.resolved_path).name == group.dwg_name
        ]
        assert [sheet.layout.layout_name for sheet in group_sheets] == [
            sheet_plan.layout_name for sheet_plan in group.sheets
        ]
        handles = [sheet.layout.handle for sheet in group_sheets]
        assert all(handles) and len(set(handles)) == len(handles)
    assert (workspace.root / STANDARD_SNAPSHOT / "document.json").is_file()


def test_created_project_keeps_standard_semantics_after_library_version_is_deleted(
    service: DstManagerService, completed_creation: CompletedCreation
) -> None:
    """标准库里的版本被删除后，语义仍由项目内快照恢复，不拒绝打开。"""
    shutil.rmtree(service.standard_store.published_root / "szmedi.gas")

    resolution = service.resolve_workspace_standard(completed_creation.workspace_id)

    assert resolution.status == "resolved"
    assert resolution.source == "project-snapshot"
    assert resolution.standard_id == "szmedi.gas" and resolution.version == "2.1.0"
    reopened = service.get_workspace(completed_creation.workspace_id)
    assert reopened.revision_id == completed_creation.revision_id
    assert not [item for item in reopened.document.diagnostics if item.severity.value == "error"]


def test_registration_succeeds_when_the_library_version_is_already_gone(
    service: DstManagerService, published_candidate: PublishedProject
) -> None:
    """发布与登记之间库中版本消失：登记仍成功，工作区照常打开（标准能力降级）。"""
    shutil.rmtree(service.standard_store.published_root / "szmedi.gas")

    result = service.finish_creation(published_candidate)

    assert result.status == "SUCCEEDED"
    workspace = service.get_workspace(result.workspace_id)
    assert workspace.document.custom_properties["DSTManager.Standard"] == STANDARD_IDENTITY
    assert not (workspace.root / STANDARD_SNAPSHOT).exists()
    assert [item.code for item in workspace.document.diagnostics] == ["STANDARD_MISSING"]


# ---- 登记失败与幂等补登记 ---------------------------------------------------


def _drawing_hashes(root: Path) -> dict[str, str]:
    """项目目录里主 DWG 的（名字 → 内容哈希）。"""
    return {
        path.name: file_sha256(path)
        for path in sorted(root.glob("*.dwg"))
    }


def _published_files(target: Path) -> dict[str, str]:
    """目标目录里已发布成果文件的（名字 → 内容哈希）。"""
    return {
        path.name: file_sha256(path)
        for path in sorted(target.iterdir())
        if path.is_file()
    }


def test_registration_failure_keeps_published_files_and_resumes_idempotently(
    service: DstManagerService,
    published_candidate: PublishedProject,
    fault_injector: RegistrationFaultInjector,
) -> None:
    target = Path(published_candidate.target_dir)
    fault_injector.fail_before_workspace_registration()

    failed = service.finish_creation(published_candidate)

    assert failed.status == "NEEDS_REVIEW"
    assert failed.workspace_id is None and failed.revision_id is None
    assert failed.error_code == "CREATION_REGISTRATION_FAILED"
    # 已发布成果、发布日志与修订证据全部保留，任务不是普通成功
    assert _published_files(target) == {
        item.name: item.sha256 for item in published_candidate.files
    }
    assert published_candidate.journal_path.is_file()
    assert (published_candidate.revision_dir / "manifest.json").is_file()
    job = service.database.get_job(published_candidate.job_id)
    assert job["status"] == "NEEDS_REVIEW" and job["workspace_id"] is None
    assert service.database.list_workspace_roots() == []

    # 启动恢复按持久日志幂等补登记：绝不重新生成或覆盖 DWG
    fault_injector.heal()
    before = _published_files(target)
    restarted = DstManagerService(service.settings)

    resumed = restarted.database.get_job(published_candidate.job_id)
    assert resumed["status"] == "SUCCEEDED" and resumed["progress"] == 100
    assert resumed["workspace_id"] is not None
    assert resumed["payload"]["workspace"]["revision_id"] == file_sha256(
        published_candidate.dst_path
    )
    assert _published_files(target) == before
    workspace = restarted.get_workspace(resumed["workspace_id"])
    assert workspace.revision_id == resumed["payload"]["workspace"]["revision_id"]
    assert (workspace.root / STANDARD_SNAPSHOT).is_dir()

    # 再重启一次：已登记完成的任务不被重复登记
    again = DstManagerService(service.settings)
    assert again.database.get_job(published_candidate.job_id)["status"] == "SUCCEEDED"
    assert _published_files(target) == before
    assert len(again.database.list_revisions(resumed["workspace_id"])) == 1


def test_registration_failure_after_workspace_row_is_resumed_consistently(
    service: DstManagerService,
    published_candidate: PublishedProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登记中途失败（工作区行已写入、初始修订未记）：补登记后现场仍自洽。"""
    import dst_manager.application.creation_registration as registration_module

    operations = registration_module.CreationRegistrationOperations
    original = operations._record_initial_revision

    def broken(self, published, workspace):
        raise OSError("注入登记故障：初始修订写入失败")

    monkeypatch.setattr(operations, "_record_initial_revision", broken)

    failed = service.finish_creation(published_candidate)

    assert failed.status == "NEEDS_REVIEW" and failed.workspace_id is None
    assert service.database.get_job(published_candidate.job_id)["status"] == "NEEDS_REVIEW"
    # 可恢复中间态：工作区行已写入，补登记必须复用同一身份而不是新建第二份
    assert len(service.database.list_workspace_roots()) == 1

    monkeypatch.setattr(operations, "_record_initial_revision", original)
    resumed = service.resume_creation_registration(
        published_candidate.job_id, published_candidate.to_payload()
    )

    assert resumed.status == "SUCCEEDED" and resumed.workspace_id
    assert len(service.database.list_workspace_roots()) == 1
    assert len(service.database.list_revisions(resumed.workspace_id)) == 1
    assert service.get_workspace(resumed.workspace_id).revision_id == resumed.revision_id


def test_registration_is_idempotent_for_an_already_published_project(
    service: DstManagerService, published_candidate: PublishedProject
) -> None:
    first = service.finish_creation(published_candidate)
    second = service.finish_creation(published_candidate)

    assert first.status == second.status == "SUCCEEDED"
    assert (first.workspace_id, first.revision_id) == (second.workspace_id, second.revision_id)
    assert len(service.database.list_revisions(first.workspace_id)) == 1
    assert len(service.database.list_workspace_roots()) == 1
    assert service.get_workspace(first.workspace_id).revision_id == first.revision_id


def test_registration_refuses_to_report_success_without_the_revision_manifest(
    service: DstManagerService, published_candidate: PublishedProject
) -> None:
    """修订清单缺失（成果不完整）：登记失败而不是普通成功，成果文件原样保留。"""
    shutil.rmtree(published_candidate.revision_dir)

    result = service.finish_creation(published_candidate)

    assert result.status == "NEEDS_REVIEW"
    assert result.workspace_id is None
    assert result.error_code == "CREATION_REGISTRATION_FAILED"
    assert service.database.get_job(published_candidate.job_id)["status"] == "NEEDS_REVIEW"
    assert _published_files(Path(published_candidate.target_dir)) == {
        item.name: item.sha256 for item in published_candidate.files
    }


# ---- 夹具辅助 ---------------------------------------------------------------


def _publish_standard(service: DstManagerService) -> None:
    """发布夹具标准：资产文件先写入草稿目录，发布后随目录一起落到 published 下。"""
    draft = service.create_standard_draft(STANDARD_DOCUMENT, "draft-gas")
    draft_root = (
        service.settings.data_dir
        / "standards"
        / "user"
        / "drafts"
        / str(draft["draft_id"])
    )
    for relative, content in ASSET_FILES.items():
        target = draft_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    published = service.publish_standard(str(draft["draft_id"]))
    assert published["standard_id"] == "szmedi.gas" and published["version"] == "2.1.0"


def _package_root(service: DstManagerService) -> Path:
    return service.standard_store.published_root / "szmedi.gas" / "2.1.0"


def _fake_capability(tmp_path: Path) -> CadCapability:
    """能力可用（Core Console 与插件文件存在）：进程执行由替身接管。"""
    directory = tmp_path / "cad"
    directory.mkdir(exist_ok=True)
    console = directory / "accoreconsole.exe"
    plugin = directory / "DstManager.AutoCAD.dll"
    console.write_bytes(b"fake-console")
    plugin.write_bytes(b"fake-plugin")
    return CadCapability("2020", console, plugin)


def _draft_value(draft: CreationDraft, target: Path) -> CreationDraft:
    """两个图纸组（2 张 + 1 张）、图幅 A1、可输入普通属性全部给出值。"""
    return replace(
        draft,
        target_path=str(target),
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
                sheet_values={"prop-stage": "施工图"},
            ),
            CreationGroupInput(
                group_id="group-2",
                created_order=2,
                title="剖面图",
                count=1,
                base_asset_id="base-a1",
                layout_asset_id="layout-a1",
                paper_layout="A1",
                sheet_values={"prop-stage": "施工图"},
            ),
        ),
    )


def _creation_site(service: DstManagerService, tmp_path: Path, *, target: Path) -> CreationSite:
    """建一份可执行草稿并算出权威预览摘要与计划（与执行入口同一份重算口径）。"""
    draft = service.create_creation_draft(("szmedi.gas", "2.1.0"))
    saved = service.save_creation_draft(
        draft.id,
        expected_revision=draft.revision,
        value=_draft_value(draft, target),
    )
    preview = service.preview(saved.id)
    assert preview["executable"] is True, preview["diagnostics"]
    plan = service.reload_creation_plan(saved.id, str(preview["preview_digest"]))
    executor = FakeCadExecutor(
        {
            group.dwg_name: tuple(sheet.layout_name for sheet in group.sheets)
            for group in plan.groups
        }
    )
    return CreationSite(
        draft_id=saved.id,
        preview_digest=str(preview["preview_digest"]),
        plan=plan,
        executor=executor,
    )


def _standard_document_is_publishable() -> None:
    """夹具标准必须能通过发布门禁（否则夹具失效，测试失败点会被误导）。"""
    standard = parse_published_standard_document(STANDARD_DOCUMENT)
    assert standard.standard_id == "szmedi.gas"


def test_fixture_standard_is_publishable() -> None:
    _standard_document_is_publishable()


def test_fixture_dst_roundtrip_is_readable(completed_creation: CompletedCreation) -> None:
    """登记后的 DST 仍是可解码、可校验的普通工作区来源。"""
    document = load_acsm(DstCodec().decode_file(Path(completed_creation.dst_path)))
    assert document.repair_report.status == "VALID"
    assert document.validate() == []
