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
from dst_manager.infrastructure.acsm_xml.document import repair_digest
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


def test_repair_digest_stable_across_independent_repairs(tmp_path: Path):
    """两次独立解码-修复产生不同随机 ID，但掩码摘要一致；摘要绑定基准修订。

    固化 `repair_digest` 的掩码不变量：预览与执行各自重解码修复时，随机生成的
    ID 值不得影响摘要；同时摘要必须随 base revision 变化（防止跨修订复用）。
    """
    xml = FAIL_SRC.read_bytes()
    first = load_acsm(xml)
    second = load_acsm(xml)
    ids_first = {node.get("ID") for node in first.root.iter() if node.get("ID")}
    ids_second = {node.get("ID") for node in second.root.iter() if node.get("ID")}
    # 两次修复的随机生成 ID 几乎必然不同：测试真正在验证掩码而不是常量
    assert ids_first != ids_second
    assert repair_digest(first.root, "rev-1") == repair_digest(second.root, "rev-1")
    assert repair_digest(first.root, "rev-1") != repair_digest(first.root, "rev-2")


def test_hierarchy_violation_workspace_opens_as_invalid(tmp_path: Path):
    """父级包含关系错误经统一 loader 观察到 INVALID_REPAIR_REQUIRED，
    写入门禁返回 REPAIR_BLOCKED；不得伪装成 REPAIRED 确认死胡同。"""
    xml = (
        b'<AcSmDatabase ID="g00000000-0000-0000-0000-400000000001" '
        b'clsid="g2162C6B6-0CE4-40E8-912B-46F59DFDF826">'
        b'<AcSmProp propname="DbVersion" vt="8">1.1</AcSmProp>'
        b'<AcSmSheetSet ID="g00000000-0000-0000-0000-400000000002" '
        b'clsid="gB20534F2-0978-418C-8D14-2E6928A077ED" propname="SheetSet" vt="13">'
        b'<AcSmProp propname="Name" vt="8">S</AcSmProp>'
        b'</AcSmSheetSet>'
        b'<AcSmSheet ID="g00000000-0000-0000-0000-400000000003" '
        b'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065">'
        b'<AcSmAcDbLayoutReference ID="g00000000-0000-0000-0000-400000000004" '
        b'clsid="g94910E94-4FCA-427C-B6ED-2EC9E1C900C7" propname="Layout" vt="13">'
        b'<AcSmProp propname="AcDbHandle" vt="8">AB</AcSmProp>'
        b'<AcSmProp propname="FileName" vt="8">C:\\x.dwg</AcSmProp>'
        b'<AcSmProp propname="Name" vt="8">001</AcSmProp>'
        b'<AcSmProp propname="Relative_FileName" vt="8">.\\x.dwg</AcSmProp>'
        b'</AcSmAcDbLayoutReference>'
        b'<AcSmProp propname="Number" vt="8">001</AcSmProp>'
        b'<AcSmSheetViews ID="g00000000-0000-0000-0000-400000000005" '
        b'clsid="gF40F931B-64BC-4B90-9FC8-A11A77D6815B" propname="SheetViews" vt="13"/>'
        b'<AcSmProp propname="Title" vt="8">T</AcSmProp>'
        b'</AcSmSheet>'
        b'</AcSmDatabase>'
    )
    service = _service(tmp_path)
    dst = _dst_from_xml(tmp_path, xml, "hierarchy.dst")
    workspace = service.open_workspace(dst)
    assert workspace.document.repair_report.status == "INVALID_REPAIR_REQUIRED"
    assert any(
        issue.code == "CONTRACT_PARENT_INVALID"
        for issue in workspace.document.repair_report.blocking_issues
    )
    with pytest.raises(ApplicationError) as exc_info:
        service.preview_changes(workspace.id, workspace.revision_id, [])
    assert exc_info.value.code == "REPAIR_BLOCKED"