"""统一 DST 加载入口的一致性测试（PLAN-DM-009 Task 4）。

所有工作区、预览、XML 与 CAD 暂存入口必须共用 `load_acsm` loader，禁止直接
构造 `AcsmDocument` 绕过修复与门禁；同一份 DST 在各入口观察到相同的
`RepairReport` 语义，读取不改变文件、不产生发布目录。
"""
from __future__ import annotations

from pathlib import Path

import pytest

import dst_manager.application.cad_job as cad_job_module
import dst_manager.application.service as service_module
from dst_manager.application.service import ApplicationError, DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.dst_codec import DstCodec

FAIL_SRC = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "shared"
    / "research"
    / "project1-dst-xml"
    / "sheetset-fail.xml"
)
GOLDEN_SRC = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "shared"
    / "research"
    / "project1-dst-xml"
    / "project1_sheetset.xml"
)


def _service(tmp_path: Path) -> DstManagerService:
    return DstManagerService(Settings(data_dir=tmp_path / "data"))


def _dst_from_xml(tmp_path: Path, xml: bytes, name: str = "project.dst") -> Path:
    dst = tmp_path / name
    DstCodec().encode_file(xml, dst)
    return dst


def test_application_modules_share_the_single_loader():
    """service 与 CAD job 都引用基础设施的统一 loader，不存在旁路构造。"""
    from dst_manager.infrastructure.acsm_xml.document import load_acsm as infra_loader

    assert service_module.load_acsm is infra_loader
    assert cad_job_module.load_acsm is infra_loader
    assert callable(load_acsm)


def test_loader_deterministic_across_entries(tmp_path: Path):
    """同一份失败样本在各入口观察到相同的 RepairReport 语义。

    注：修复会按设计为缺失 ID 的节点生成随机 UUID，因此逐字段比较只针对
    status/blocking/动作计数与动作码集合，不比较随机 ID 值。
    """
    service = _service(tmp_path)
    dst = _dst_from_xml(tmp_path, FAIL_SRC.read_bytes())

    opened = service.open_workspace(dst)
    assert opened.document.repair_report.status == "REPAIRED"
    assert opened.document.repair_report.blocking_issues == ()

    reopened = service.get_workspace(opened.id)
    assert reopened.document.repair_report.status == "REPAIRED"
    assert {a.code for a in reopened.document.repair_report.actions} == {a.code for a in opened.document.repair_report.actions}

    # 直接 loader 与工作区入口一致
    direct = load_acsm(DstCodec().decode_file(dst))
    assert direct.repair_report.status == reopened.document.repair_report.status
    assert len(direct.repair_report.actions) == len(reopened.document.repair_report.actions)


def test_golden_workspace_valid_and_bypasses_gate(tmp_path: Path):
    service = _service(tmp_path)
    dst = _dst_from_xml(tmp_path, GOLDEN_SRC.read_bytes(), "golden.dst")
    workspace = service.open_workspace(dst)
    assert workspace.document.repair_report.status == "VALID"
    # VALID 工作区不触发修复门禁（环境性诊断如 DWG 路径缺失与修复无关）
    preview = service.preview_changes(workspace.id, workspace.revision_id, [])
    assert all(
        item["code"] not in {"REPAIR_CONFIRMATION_REQUIRED", "REPAIR_BLOCKED", "REPAIR_UNRECOVERABLE"}
        for item in preview["diagnostics"]
    )


def test_fail_workspace_writes_are_gated(tmp_path: Path):
    service = _service(tmp_path)
    dst = _dst_from_xml(tmp_path, FAIL_SRC.read_bytes())
    workspace = service.open_workspace(dst)
    assert workspace.document.repair_report.status == "REPAIRED"

    with pytest.raises(ApplicationError) as exc_info:
        service.preview_changes(workspace.id, workspace.revision_id, [])
    assert exc_info.value.code == "REPAIR_CONFIRMATION_REQUIRED"

    with pytest.raises(ApplicationError) as exc_info:
        service.preview_xml(workspace.id, workspace.revision_id, GOLDEN_SRC.read_bytes())
    assert exc_info.value.code == "REPAIR_CONFIRMATION_REQUIRED"

    with pytest.raises(ApplicationError) as exc_info:
        service.export_xml_to_dst(
            workspace.id,
            workspace.revision_id,
            GOLDEN_SRC.read_bytes(),
            tmp_path / "out.dst",
            "MISSING",
        )
    assert exc_info.value.code == "REPAIR_CONFIRMATION_REQUIRED"


def test_read_only_open_creates_nothing_inside_project(tmp_path: Path):
    """只读打开不创建 `.dst-manager/`，不改变 DST 字节与时间戳。"""
    project = tmp_path / "project"
    project.mkdir()
    dst = project / "set.dst"
    dst.write_bytes(FAIL_SRC.read_bytes())
    DstCodec().encode_file(dst.read_bytes(), dst)
    before_bytes = dst.read_bytes()
    before_mtime = dst.stat().st_mtime

    service = _service(tmp_path)
    workspace = service.open_workspace(dst)
    assert not (project / ".dst-manager").exists()
    assert workspace.document.repair_report.status == "REPAIRED"
    assert dst.read_bytes() == before_bytes
    assert dst.stat().st_mtime == before_mtime


def test_repair_preview_reports_actions_and_blocks_unconfirmed_execute(tmp_path: Path):
    service = _service(tmp_path)
    dst = _dst_from_xml(tmp_path, FAIL_SRC.read_bytes())
    workspace = service.open_workspace(dst)

    preview = service.preview_repair(workspace.id, workspace.revision_id)
    assert preview["status"] == "REPAIRED"
    assert preview["actions"]
    assert preview["executable"] is True
    assert preview["preview_digest"]

    # 未确认（无 digest）不能执行修复：任务以 REPREVIEW_REQUIRED 进入 FAILED
    job = service.execute_repair(workspace.id, workspace.revision_id, None)
    assert job["status"] == "FAILED"
    assert job.get("error_code") == "REPREVIEW_REQUIRED"