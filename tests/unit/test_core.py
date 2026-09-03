import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from lxml import etree
from typer.testing import CliRunner

import dst_manager.application.cad_job as cad_job_module
import dst_manager.application.service as service_module
from dst_manager.application.cad_job import CadJobRunner, RebuildResult, RebuildWorkUnit
from dst_manager.application.service import ApplicationError, DstManagerService
from dst_manager.config import Settings
from dst_manager.domain.editing import (
    EditingError,
    SuffixOptions,
    derive_document_structure,
)
from dst_manager.domain.models import (
    CustomPropertyDefinition,
    DerivedDocument,
    DerivedSubset,
    JobStatus,
    LayoutReference,
    PropertyDefinitionDiff,
    Sheet,
    SheetSetDocument,
    Subset,
    Workspace,
)
from dst_manager.domain.planning import (
    PlanningError,
    build_structural_plan,
    derive_subset_and_dwg_name,
)
from dst_manager.infrastructure.acsm_xml import AcsmDocument, load_acsm
from dst_manager.infrastructure.acsm_xml.document import AcsmValidationError
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    decode_console_output,
    rename_result_path,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.dst_codec.codec import _DECODE, _ENCODE
from dst_manager.infrastructure.filesystem.publisher import (
    ExpectedFileBaseline,
    PublishBaselineError,
    PublishRecoveryError,
    PublishRolledBackError,
    RecoverablePublisher,
    capture_file_baseline,
    file_sha256,
)
from dst_manager.infrastructure.logging_text import (
    sanitize_log_text,
    validate_log_bytes,
)
from dst_manager.interfaces.cli import _worker_summary
from dst_manager.interfaces.cli import app as cli_app


def _execute_confirmed(service, workspace_id, base_revision_id, commands, cad_version="2020"):
    preview = service.preview_changes(workspace_id, base_revision_id, commands, cad_version)
    return service.execute_changes(
        workspace_id,
        base_revision_id,
        commands,
        cad_version,
        preview_digest=preview["preview_digest"],
    )


def _restore_confirmed(service, workspace_id, revision_id, base_revision_id):
    preview = service.preview_revision_restore(workspace_id, revision_id)
    return service.restore_revision(
        workspace_id,
        revision_id,
        base_revision_id,
        preview_digest=preview["preview_digest"],
    )


def test_mapping_all_bytes(): assert bytes(range(256)).translate(_ENCODE).translate(_DECODE)==bytes(range(256))


def test_log_text_is_strict_utf8_without_disallowed_controls(tmp_path):
    text = sanitize_log_text("中文\x00错误\x1b[31m\t正常\n")
    encoded = text.encode("utf-8")
    validate_log_bytes(encoded)
    assert b"\x00" not in encoded
    assert "\\x00" in text and "\\x1b" in text
    log_path = tmp_path / "中文工程" / "运行错误.log"
    log_path.parent.mkdir()
    log_path.write_text(text, encoding="utf-8")
    validate_log_bytes(log_path.read_bytes())


def test_windows_console_output_is_decoded_before_utf8_logging():
    text = "中文错误\x00"
    decoded_mbcs = decode_console_output(text.encode("mbcs"))
    decoded_utf16 = decode_console_output(text.encode("utf-16"))
    assert decoded_mbcs == decoded_utf16 == "中文错误\\x00"
    validate_log_bytes(decoded_mbcs.encode("utf-8"))


def test_failed_core_console_output_is_archived_in_per_dwg_log(tmp_path):
    source = tmp_path / "来源.dwg"
    source.write_bytes(b"source")
    staging = tmp_path / "staging"
    scripts = tmp_path / "scripts"
    logs = tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    unit = RebuildWorkUnit(
        index=0,
        group={
            "source_target_file": str(source),
            "target_file": str(tmp_path / "目标.dwg"),
            "layouts": [{"source_file": str(source), "source_layout": "布局1", "target_layout": "001 平面"}],
        },
        source_snapshot=source,
        staging_dir=staging,
        scripts_dir=scripts,
        logs_dir=logs,
        timeout=30,
    )
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    runner.executor = Mock()
    runner.executor.run.side_effect = subprocess.CalledProcessError(7, ["accoreconsole.exe"], "布局输出", "CAD 错误输出")
    workspace = Workspace("workspace", tmp_path, tmp_path / "test.dst", "revision", SheetSetDocument("db", "图纸集", []))

    with pytest.raises(subprocess.CalledProcessError):
        runner._rebuild_group("job-1", workspace, CadCapability("2020", None, tmp_path / "plugin.dll"), unit)

    log = (logs / "group-000.log").read_text(encoding="utf-8")
    assert "Core Console：重建布局并读取布局 Handle（退出码 7）stdout" in log
    assert "布局输出" in log and "CAD 错误输出" in log


def test_worker_stdout_summary_excludes_payload_and_paths():
    result = {
        "id": "job-1",
        "status": "FAILED",
        "attempt": 2,
        "error_code": "CAD_TIMEOUT",
        "payload": {"commands": [{"secret": "不要输出"}]},
        "files": [
            {"status": "SUCCEEDED", "target_path": r"C:\\客户\\A.dwg"},
            {"status": "FAILED", "target_path": r"C:\\客户\\B.dwg"},
        ],
    }

    summary = _worker_summary(result, 123)

    assert summary == {
        "job_id": "job-1",
        "status": "FAILED",
        "attempt": 2,
        "dwg_succeeded": 1,
        "dwg_failed": 1,
        "duration_ms": 123,
        "error_code": "CAD_TIMEOUT",
    }
    assert "payload" not in summary and "files" not in summary


@pytest.mark.parametrize(("status", "error_code"), [("SUCCEEDED", None), ("FAILED", "CAD_TIMEOUT")])
def test_worker_cli_writes_only_one_line_summary(monkeypatch, status, error_code):
    result = {
        "id": "job-1",
        "status": status,
        "attempt": 1,
        "error_code": error_code,
        "payload": {"commands": [{"secret": "不要输出"}]},
        "files": [{"status": status, "target_path": r"C:\\客户\\A.dwg"}],
    }

    class FakeService:
        def __init__(self):
            self.calls = 0

        def run_next_job(self):
            self.calls += 1
            return result if self.calls == 1 else None

    monkeypatch.setattr("dst_manager.interfaces.cli.DstManagerService", FakeService)
    completed = CliRunner().invoke(cli_app, ["worker", "--once"])

    assert completed.exit_code == 0
    lines = completed.stdout.strip().splitlines()
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["job_id"] == "job-1" and summary["status"] == status
    assert "payload" not in completed.stdout and "commands" not in completed.stdout and "客户" not in completed.stdout
def test_golden_counts_and_relocation():
    dst=Path("sample/project1/图纸集数据文件.dst")
    if not dst.is_file(): pytest.skip("公开仓库不分发黄金工程样本")
    doc=AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    manifest=json.loads(Path("tests/golden/project1_manifest.json").read_text(encoding="utf-8")); files=[{"name":path.name,"size":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(dst.parent.iterdir()) if path.is_file() and path.suffix.lower() in {".dst",".dwg"}]; digest=hashlib.sha256(json.dumps(files,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode()).hexdigest()
    assert len(files)==manifest["file_count"] and sum(item["size"] for item in files)==manifest["total_size"] and digest==manifest["files_digest"]
    assert (len(doc.sheets),len(doc.subsets))==(manifest["sheet_count"],manifest["subset_count"]); assert all(x.layout.resolved_path for x in doc.sheets)


def test_real_project_read_only_structure_profiles():
    """从真实黄金工程固定小型、约 300 图纸和大布局组的只读结构基线。"""
    dst = Path("sample/project1/图纸集数据文件.dst")
    if not dst.is_file():
        pytest.skip("公开仓库不分发黄金工程样本")
    before = {path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) for path in dst.parent.glob("*") if path.is_file()}
    doc = AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    profiles = {
        "small": len(doc.subsets[0].sheets),
        "around_300": len(doc.sheets),
        "large_layout_group": max(len(subset.sheets) for subset in doc.subsets),
    }
    assert profiles == {"small": 1, "around_300": 298, "large_layout_group": 25}
    after = {path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) for path in dst.parent.glob("*") if path.is_file()}
    assert after == before
    assert not (dst.parent / ".dst-manager").exists()
def test_unknown_preserved(tiny_workspace):
    dst,sheet_id=tiny_workspace; doc=AcsmDocument(DstCodec().decode_file(dst)); doc.apply_metadata_commands([{"type":"update_sheet","sheet_id":sheet_id,"title":"修改后","custom_properties":{"比例":"1:200"}}]); roundtrip=AcsmDocument(doc.to_bytes()); sheet=roundtrip.root.xpath("//*[@ID=$sheet_id and local-name()='AcSmSheet']", sheet_id=sheet_id)[0]; unknown=sheet.xpath("./*[local-name()='Unknown']")[0]; assert unknown.get("keep")=="yes"; assert roundtrip.project(dst.parent).sheets[0].title=="修改后"

def test_sheet_set_and_sheet_custom_properties_roundtrip(tiny_workspace):
    dst,sheet_id=tiny_workspace
    doc=AcsmDocument(DstCodec().decode_file(dst))
    doc.apply_metadata_commands([
        {"type":"update_sheet_set","name":"新图纸集","custom_properties":{"项目号":"P-001"}},
        {"type":"update_sheet","sheet_id":sheet_id,"custom_properties":{"比例":"1:200"}},
    ])
    projected=AcsmDocument(doc.to_bytes()).project(dst.parent)
    assert projected.name=="新图纸集"
    assert projected.custom_properties=={"项目号":"P-001"}
    assert projected.sheets[0].custom_properties=={"比例":"1:200"}

def test_v021_naming_policy_derives_range_and_sheet_titles():
    sheets = [
        Sheet("1", "0001", "图纸目录(一)", LayoutReference("", "", "", "")),
        Sheet("2", "0005", "图纸目录(五)", LayoutReference("", "", "", "")),
    ]
    document = SheetSetDocument("db", "图纸集", [Subset("subset", "1-5 图纸目录", 1, sheets)])

    derived = derive_document_structure(document, [], SuffixOptions(True, 1))

    assert derived.subsets[0].display_name == "0001-0002 图纸目录"
    assert [sheet.title for sheet in derived.subsets[0].sheets] == ["图纸目录 (一)", "图纸目录 (二)"]


def test_derived_target_file_name_compresses_title_suffixes(tmp_path: Path):
    sheets = [
        Sheet("1", "01", "图纸目录", LayoutReference(str(tmp_path / "RQ-01 图纸目录.dwg"), "", "01 图纸目录", "")),
        Sheet("2", "02", "图纸目录", LayoutReference(str(tmp_path / "RQ-01 图纸目录.dwg"), "", "02 图纸目录", "")),
    ]
    document = SheetSetDocument("db", "图纸集", [Subset("subset", "01-02 图纸目录", 1, sheets)])

    derived = derive_document_structure(document, [], SuffixOptions(True, 1))

    assert [sheet.title for sheet in derived.subsets[0].sheets] == ["图纸目录 (一)", "图纸目录 (二)"]
    assert Path(derived.subsets[0].target_file).name == "RQ-01-02 图纸目录 (一)-(二).dwg"


def test_derived_target_file_name_compresses_arabic_suffixes(tmp_path: Path):
    sheets = [
        Sheet("1", "01", "图纸目录", LayoutReference(str(tmp_path / "RQ-01 图纸目录.dwg"), "", "01 图纸目录", "")),
        Sheet("2", "02", "图纸目录", LayoutReference(str(tmp_path / "RQ-01 图纸目录.dwg"), "", "02 图纸目录", "")),
    ]
    document = SheetSetDocument("db", "图纸集", [Subset("subset", "01-02 图纸目录", 1, sheets)])

    derived = derive_document_structure(document, [], SuffixOptions(True, 2))

    assert Path(derived.subsets[0].target_file).name == "RQ-01-02 图纸目录 (1)-(2).dwg"


def test_derived_target_file_name_keeps_base_title_without_suffix(tmp_path: Path):
    sheets = [
        Sheet("1", "01", "图纸目录", LayoutReference(str(tmp_path / "RQ-01 图纸目录.dwg"), "", "01 图纸目录", "")),
    ]
    document = SheetSetDocument("db", "图纸集", [Subset("subset", "01 图纸目录", 1, sheets)])

    derived = derive_document_structure(document, [], SuffixOptions(True, 1))

    assert derived.subsets[0].sheets[0].title == "图纸目录"
    assert Path(derived.subsets[0].target_file).name == "RQ-01 图纸目录.dwg"


def _insert_subset_command(initial_sheet_count: int = 1) -> dict:
    return {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "燃气管道平面图",
        "initial_sheet_count": initial_sheet_count,
        "source": {"type": "template_layout", "file": r"C:\模板\标准.dwt", "layout": "A3"},
        "base_template_file": r"C:\模板\图纸模板.dwg",
    }


def test_derive_insert_subset_carries_base_template_file(tmp_path: Path):
    base_template = tmp_path / "图纸基底.dwg"
    document = SheetSetDocument("db", "图纸集", [])
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "燃气管道平面图",
        "initial_sheet_count": 2,
        "base_template_file": str(base_template),
        "source": {"type": "template_layout", "file": str(tmp_path / "布局模板.dwt"), "layout": "A3"},
    }

    derived = derive_document_structure(document, [command], SuffixOptions(True, 1))

    new_subset_id = derived.subsets[-1].acsm_id
    assert derived.subset_base_templates[new_subset_id] == str(base_template)
    assert new_subset_id in derived.affected_subset_ids


def test_derive_insert_subset_rejects_missing_base_template_file(tmp_path: Path):
    document = SheetSetDocument("db", "图纸集", [])
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "燃气管道平面图",
        "initial_sheet_count": 1,
        "source": {"type": "template_layout", "file": str(tmp_path / "布局模板.dwt"), "layout": "A3"},
    }

    with pytest.raises(EditingError) as exc_info:
        derive_document_structure(document, [command], SuffixOptions(True, 1))

    assert exc_info.value.code == "INSERT_SUBSET_BASE_TEMPLATE_INVALID"


def test_derive_insert_subset_rejects_invalid_base_template_extension(tmp_path: Path):
    document = SheetSetDocument("db", "图纸集", [])
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "燃气管道平面图",
        "initial_sheet_count": 1,
        "base_template_file": str(tmp_path / "基底.txt"),
        "source": {"type": "template_layout", "file": str(tmp_path / "布局模板.dwt"), "layout": "A3"},
    }

    with pytest.raises(EditingError) as exc_info:
        derive_document_structure(document, [command], SuffixOptions(True, 1))

    assert exc_info.value.code == "INSERT_SUBSET_BASE_TEMPLATE_INVALID"


def test_insert_subset_creates_nonempty_controlled_nodes(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))

    document.apply_structural_commands([_insert_subset_command()], "revision")

    projected = AcsmDocument(document.to_bytes()).project(dst.parent)
    assert len(projected.subsets[-1].sheets) == 1
    assert projected.subsets[-1].name == "燃气管道平面图"
    assert projected.subsets[-1].sheets[0].layout.layout_name == "A3"


def test_insert_subset_rejects_empty_without_half_node(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    before = document.semantic_bytes()

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_structural_commands([_insert_subset_command(0)], "revision")

    assert exc_info.value.code == "EMPTY_SUBSET"
    assert document.semantic_bytes() == before


def test_insert_sheet_batch_creates_unique_controlled_nodes(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]

    document.apply_structural_commands(
        [
            {
                "type": "insert_sheet",
                "target_subset_id": subset.get("ID"),
                "ordinal": 1,
                "placement": "after",
                "count": 3,
                "source": {"type": "template_layout", "file": r"C:\模板\标准.dwt", "layout": "A3"},
            },
        ],
        "revision",
    )

    sheets = subset.xpath("./*[local-name()='AcSmSheet']")
    ids = [node.get("ID") for node in sheets]
    all_ids = [node.get("ID") for node in document.root.xpath(".//*[@ID] | self::node()[@ID]")]
    assert len(sheets) == 4
    assert len(ids) == len(set(ids))
    assert len(all_ids) == len(set(all_ids))
    projected_sheets = AcsmDocument(document.to_bytes()).project(dst.parent).subsets[0].sheets
    assert [sheet.layout.layout_name for sheet in projected_sheets[1:]] == ["A3", "A3", "A3"]
    assert [sheet.layout.handle for sheet in projected_sheets] == ["AB", "0", "0", "0"]


def test_final_validate_rejects_inserted_sheet_placeholder_handle_until_binding(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]

    document.apply_structural_commands(
        [
            {
                "type": "insert_sheet",
                "target_subset_id": subset.get("ID"),
                "position": 1,
                "number": "002",
                "title": "新增",
                "source": {"type": "template_layout", "file": r"C:\模板\标准.dwt", "layout": "A3"},
            },
        ],
        "revision",
    )

    inserted_id = subset.xpath("./*[local-name()='AcSmSheet']")[1].get("ID")
    placeholder_issues = [issue for issue in document.validate() if issue.code == "LAYOUT_HANDLE_PLACEHOLDER"]
    assert [issue.object_id for issue in placeholder_issues] == [inserted_id]

    document.apply_layout_bindings(
        {inserted_id: {"file": str(dst.parent / "A.dwg"), "layout": "002 新增", "handle": "CD"}},
        dst.parent,
    )

    final_errors = {issue.code for issue in document.validate() if issue.severity == "error"}
    assert "LAYOUT_HANDLE_PLACEHOLDER" not in final_errors
    assert "LAYOUT_HANDLE_INVALID" not in final_errors


def test_layout_references_use_windows_relative_path_and_reject_outside_workspace(tiny_workspace, tmp_path: Path):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    target = dst.parent / "A.dwg"

    document.apply_layout_references(
        {sheet_id: {"file": str(target), "layout": "001 平面"}},
        dst.parent,
    )

    layout = document.project(dst.parent).sheets[0].layout
    assert layout.relative_file_name == ".\\A.dwg"
    with pytest.raises(AcsmValidationError, match="DWG_OUTSIDE_WORKSPACE"):
        document.apply_layout_references(
            {sheet_id: {"file": str(tmp_path.parent / "outside.dwg"), "layout": "001 平面"}},
            dst.parent,
        )


def test_first_subset_uses_minimal_factory_when_no_subset_template(tiny_workspace):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    sheet_set = document.root.xpath("//*[local-name()='AcSmSheetSet']")[0]
    for subset in sheet_set.xpath("./*[local-name()='AcSmSubset']"):
        sheet_set.remove(subset)

    document.apply_structural_commands([_insert_subset_command(2)], "revision")

    subset = sheet_set.xpath("./*[local-name()='AcSmSubset']")[0]
    sheets = subset.xpath("./*[local-name()='AcSmSheet']")
    assert len(sheets) == 2
    assert [child.get("propname") for child in subset if child.tag.endswith("AcSmProp")] == ["Name"]
    assert all(sheet.xpath("./*[local-name()='AcSmCustomPropertyBag']") for sheet in sheets)
    assert all(sheet.xpath("./*[local-name()='AcSmAcDbLayoutReference']") for sheet in sheets)
    assert all(sheet.xpath("./*[local-name()='AcSmProp' and @propname='Number']") for sheet in sheets)
    assert all(sheet.xpath("./*[local-name()='AcSmProp' and @propname='Title']") for sheet in sheets)


@pytest.mark.parametrize(
    "command",
    [
        {"type": "move_sheet", "sheet_id": "sheet-1", "target_subset_id": "subset-1"},
        {"type": "reorder_sheet", "sheet_id": "sheet-1", "position": 0},
        {"type": "update_sheet", "sheet_id": "sheet-1", "title": "手工标题"},
    ],
)
def test_legacy_structural_commands_are_rejected(tiny_workspace, command):
    dst, sheet_id = tiny_workspace
    command = dict(command)
    command["sheet_id"] = sheet_id
    document = AcsmDocument(DstCodec().decode_file(dst))

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_structural_commands([command], "revision")

    assert exc_info.value.code == "COMMAND_UNSUPPORTED"


def test_apply_derived_document_writes_final_structure_without_deriving_business_rules(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    existing_layout = LayoutReference(r"C:\old\A.dwg", r".\A.dwg", "应被派生布局覆盖", "AB")
    derived = DerivedDocument(
        [
            DerivedSubset(
                "g99999999-9999-9999-9999-999999999999",
                "燃气管道平面图",
                "001-002",
                "001-002 燃气管道平面图",
                [
                    Sheet(
                        sheet_id,
                        "777",
                        "来自派生的标题",
                        existing_layout,
                        {"比例": "1:500", "专业": "燃气"},
                    ),
                    Sheet(
                        "g88888888-8888-8888-8888-888888888888",
                        "778",
                        "来自派生的新图纸",
                        LayoutReference(r"C:\模板\标准.dwt", r".\标准.dwt", "778 来自派生的新图纸", ""),
                        {"专业": "燃气"},
                    ),
                ],
            )
        ],
        ["g99999999-9999-9999-9999-999999999999"],
        PropertyDefinitionDiff([CustomPropertyDefinition("sheet", "专业", "燃气")]),
    )

    document.apply_derived_document(derived)

    roundtrip = AcsmDocument(document.to_bytes())
    projected = roundtrip.project(dst.parent)
    assert [subset.name for subset in projected.subsets] == ["001-002 燃气管道平面图"]
    assert [sheet.number for sheet in projected.sheets] == ["777", "778"]
    assert [sheet.title for sheet in projected.sheets] == ["来自派生的标题", "来自派生的新图纸"]
    assert [sheet.custom_properties["专业"] for sheet in projected.sheets] == ["燃气", "燃气"]
    assert projected.sheets[0].custom_properties["比例"] == "1:500"
    original_sheet = roundtrip.root.xpath("//*[@ID=$sheet_id and local-name()='AcSmSheet']", sheet_id=sheet_id)[0]
    assert original_sheet.xpath("./*[local-name()='Unknown']")[0].get("keep") == "yes"


def test_apply_derived_document_failure_leaves_original_dom_unchanged(tiny_workspace):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]
    sheet = document.root.xpath("//*[@ID=$sheet_id and local-name()='AcSmSheet']", sheet_id=sheet_id)[0]
    sheet.remove(sheet.xpath("./*[local-name()='AcSmAcDbLayoutReference']")[0])
    before = document.semantic_bytes()
    derived = DerivedDocument(
        [
            DerivedSubset(
                subset.get("ID"),
                "新标题",
                "999",
                "999 新标题",
                [
                    Sheet(
                        sheet_id,
                        "999",
                        "失败前不应留下",
                        LayoutReference(r"C:\old\A.dwg", r".\A.dwg", "999 失败前不应留下", "AB"),
                        {"比例": "1:500"},
                    ),
                ],
            ),
        ],
        [subset.get("ID")],
        PropertyDefinitionDiff([CustomPropertyDefinition("sheet", "专业", "燃气")]),
    )

    with pytest.raises(AcsmValidationError) as exc_info:
        document.apply_derived_document(derived)

    assert exc_info.value.code == "SHEET_LAYOUT_COUNT"
    assert document.semantic_bytes() == before


def _planning_sheet(sheet_id: str, number: str, title: str, drawing: Path, handle: str) -> Sheet:
    return Sheet(
        sheet_id,
        number,
        title,
        LayoutReference(
            str(drawing),
            f".\\{drawing.name}",
            f"{number} {title}",
            handle,
            drawing.resolve(),
            "relative",
        ),
    )


def _planning_workspace(tmp_path: Path, subsets: list[Subset]) -> Workspace:
    dst = tmp_path / "图纸集.dst"
    dst.write_bytes(b"dst")
    return Workspace(
        "workspace",
        tmp_path,
        dst,
        "revision",
        SheetSetDocument("database", "图纸集", subsets),
    )


def _chained_rename_workspace(
    tmp_path: Path,
    count: int = 2,
    handles: list[str] | None = None,
) -> tuple[Workspace, list[Path]]:
    drawings = [tmp_path / f"{index:03d} 共享.dwg" for index in range(1, count + 1)]
    for index, drawing in enumerate(drawings, start=1):
        drawing.write_bytes(f"old-{index}".encode())
    ids = [f"g00000000-0000-0000-0001-{index:012X}" for index in range(1, 3 + 3 * count)]
    subsets = []
    for index, drawing in enumerate(drawings, start=1):
        offset = (index - 1) * 3
        handle = handles[index - 1] if handles is not None else f"A{index}"
        subsets.append(
            f'''<AcSmSubset ID="{ids[offset + 2]}"><AcSmProp propname="Name">00{index} 共享</AcSmProp>'''
            f'''<AcSmSheet ID="{ids[offset + 3]}"><AcSmCustomPropertyBag ID="{ids[offset + 4]}"/>'''
            f'''<AcSmAcDbLayoutReference><AcSmProp propname="AcDbHandle">{handle}</AcSmProp>'''
            f'''<AcSmProp propname="FileName">{drawing}</AcSmProp>'''
            f'''<AcSmProp propname="Name">00{index} 共享 ({index})</AcSmProp>'''
            f'''<AcSmProp propname="Relative_FileName">.\\{drawing.name}</AcSmProp></AcSmAcDbLayoutReference>'''
            f'''<AcSmProp propname="Number">00{index}</AcSmProp><AcSmProp propname="Title">共享 ({index})</AcSmProp>'''
            "</AcSmSheet></AcSmSubset>",
        )
    xml = (
        f'''<AcSmDatabase ID="{ids[0]}"><AcSmProp propname="DbVersion">1.1</AcSmProp>'''
        f'''<AcSmSheetSet ID="{ids[1]}"><AcSmProp propname="Name">连锁改名</AcSmProp>'''
        + "".join(subsets)
        + "</AcSmSheetSet></AcSmDatabase>"
    ).encode()
    # 通过统一 loader 对齐新契约（固定 clsid/propname/vt + AcSmSheetViews），保持 VALID
    xml = load_acsm(xml).to_bytes()
    dst = tmp_path / "连锁改名.dst"
    codec = DstCodec()
    codec.encode_file(xml, dst)
    document = AcsmDocument(codec.decode_file(dst)).project(tmp_path)
    return Workspace("workspace-chain", tmp_path, dst, file_sha256(dst), document), drawings


def test_subset_title_only_renames_target_without_touching_following_subset(tmp_path: Path):
    first = tmp_path / "001 第一册.dwg"
    second = tmp_path / "002 第二册.dwg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    workspace = _planning_workspace(
        tmp_path,
        [
            Subset("subset-1", "001 第一册", 0, [_planning_sheet("sheet-1", "001", "第一册", first, "A1")]),
            Subset("subset-2", "002 第二册", 1, [_planning_sheet("sheet-2", "002", "第二册", second, "A2")]),
        ],
    )

    plan = build_structural_plan(
        workspace,
        [{"type": "update_subset", "subset_id": "subset-1", "title": "第一分册"}],
        SuffixOptions(True, 1),
    )

    assert [(item["subset_id"], item["cad_operation"]) for item in plan["subset_operations"]] == [
        ("subset-1", "rename_only"),
        ("subset-2", "none"),
    ]
    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]] == [
        ("subset-1", "rename_only"),
    ]


def test_sheet_count_change_rebuilds_frontier_and_renames_following_subset(tmp_path: Path):
    first = tmp_path / "001 第一册.dwg"
    second = tmp_path / "002 第二册.dwg"
    template = tmp_path / "模板.dwt"
    for path in (first, second, template):
        path.write_bytes(path.name.encode("utf-8"))
    workspace = _planning_workspace(
        tmp_path,
        [
            Subset("subset-1", "001 第一册", 0, [_planning_sheet("sheet-1", "001", "第一册", first, "A1")]),
            Subset("subset-2", "002 第二册", 1, [_planning_sheet("sheet-2", "002", "第二册", second, "A2")]),
        ],
    )

    plan = build_structural_plan(
        workspace,
        [{
            "type": "insert_sheet",
            "target_subset_id": "subset-1",
            "ordinal": 1,
            "placement": "after",
            "count": 1,
            "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
        }],
        SuffixOptions(True, 1),
    )

    assert plan["cardinality_frontier"] == {"index": 0, "subset_id": "subset-1"}
    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]] == [
        ("subset-1", "rebuild"),
        ("subset-2", "rename_only"),
    ]
    assert plan["groups"][1]["layouts"][0]["original_layout"] == "002 第二册"


def _derived_subset_for_plan(subset: Subset, sheets: list[Sheet] | None = None) -> DerivedSubset:
    source_target = str((subset.sheets[0].layout.resolved_path or Path(subset.sheets[0].layout.file_name)).resolve())
    sheets = sheets if sheets is not None else subset.sheets
    return DerivedSubset(
        subset.acsm_id,
        subset.name,
        f"{sheets[0].number}-{sheets[-1].number}" if len(sheets) > 1 else sheets[0].number,
        subset.name,
        sheets,
        source_target,
        source_target,
    )


def _existing_sources(subsets: list[Subset]) -> dict[str, dict[str, str]]:
    return {
        sheet.acsm_id: {
            "type": "existing_snapshot",
            "file": str((sheet.layout.resolved_path or Path(sheet.layout.file_name)).resolve()),
            "layout": sheet.layout.layout_name,
        }
        for subset in subsets
        for sheet in subset.sheets
    }


@pytest.mark.parametrize(
    ("removed_subset_id", "expected_frontier", "expected_groups"),
    [
        ("subset-2", {"index": 1, "subset_id": "subset-3"}, [("subset-3", "rename_only")]),
        ("subset-3", {"index": 2, "subset_id": None}, []),
    ],
)
def test_cardinality_frontier_propagates_after_subset_deletion(
    tmp_path: Path,
    monkeypatch,
    removed_subset_id: str,
    expected_frontier: dict[str, int | str | None],
    expected_groups: list[tuple[str, str]],
):
    subsets = []
    for index, title in enumerate(("第一册", "第二册", "第三册"), start=1):
        drawing = tmp_path / f"{index:03d} {title}.dwg"
        drawing.write_bytes(title.encode("utf-8"))
        subsets.append(
            Subset(
                f"subset-{index}",
                f"{index:03d} {title}",
                index - 1,
                [_planning_sheet(f"sheet-{index}", f"{index:03d}", title, drawing, f"A{index}")],
            ),
        )
    workspace = _planning_workspace(tmp_path, subsets)
    final_subsets = [_derived_subset_for_plan(subset) for subset in subsets if subset.acsm_id != removed_subset_id]
    derived = DerivedDocument(final_subsets, [], layout_sources=_existing_sources(subsets))
    monkeypatch.setattr("dst_manager.domain.planning.derive_document_structure", lambda *_args: derived)

    plan = build_structural_plan(workspace, [], SuffixOptions(True, 1))

    assert plan["cardinality_frontier"] == expected_frontier
    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]] == expected_groups
    assert [item["subset_id"] for item in plan["subset_operations"]] == [subset.acsm_id for subset in final_subsets]


def test_inserted_subset_rebuilds_and_renames_following_subset(tmp_path: Path):
    first = tmp_path / "001 第一册.dwg"
    second = tmp_path / "002 第二册.dwg"
    template = tmp_path / "模板.dwt"
    for path in (first, second, template):
        path.write_bytes(path.name.encode("utf-8"))
    workspace = _planning_workspace(
        tmp_path,
        [
            Subset("subset-1", "001 第一册", 0, [_planning_sheet("sheet-1", "001", "第一册", first, "A1")]),
            Subset("subset-2", "002 第二册", 1, [_planning_sheet("sheet-2", "002", "第二册", second, "A2")]),
        ],
    )

    plan = build_structural_plan(
        workspace,
        [{
            "type": "insert_subset",
            "ordinal": 1,
            "placement": "after",
            "title": "新增册",
            "initial_sheet_count": 1,
            "base_template_file": str(template),
            "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
        }],
        SuffixOptions(True, 1),
    )

    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]][-2:] == [
        (plan["groups"][-2]["subset_id"], "rebuild"),
        ("subset-2", "rename_only"),
    ]


def test_mismatched_stable_sheet_order_requires_rebuild(tmp_path: Path, monkeypatch):
    drawing = tmp_path / "001-002 第一册.dwg"
    drawing.write_bytes(b"drawing")
    original = Subset(
        "subset-1",
        "001-002 第一册",
        0,
        [
            _planning_sheet("sheet-1", "001", "第一册", drawing, "A1"),
            _planning_sheet("sheet-2", "002", "第一册", drawing, "A2"),
        ],
    )
    workspace = _planning_workspace(tmp_path, [original])
    derived = DerivedDocument(
        [_derived_subset_for_plan(original, list(reversed(original.sheets)))],
        [],
        layout_sources=_existing_sources([original]),
    )
    monkeypatch.setattr("dst_manager.domain.planning.derive_document_structure", lambda *_args: derived)

    plan = build_structural_plan(workspace, [], SuffixOptions(True, 1))

    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]] == [("subset-1", "rebuild")]


@pytest.mark.parametrize("handle", ["-1", "+1", "0x1", " A1"])
def test_noncanonical_nonzero_handle_requires_rebuild(tmp_path: Path, handle: str):
    drawing = tmp_path / "001 第一册.dwg"
    drawing.write_bytes(b"drawing")
    workspace = _planning_workspace(
        tmp_path,
        [Subset("subset-1", "001 第一册", 0, [_planning_sheet("sheet-1", "001", "第一册", drawing, handle)])],
    )

    plan = build_structural_plan(
        workspace,
        [{"type": "update_subset", "subset_id": "subset-1", "title": "第一分册"}],
        SuffixOptions(True, 1),
    )

    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]] == [("subset-1", "rebuild")]


@pytest.mark.parametrize(("first_handle", "second_handle"), [("A", "A"), ("A", "0A")])
def test_duplicate_numeric_handles_in_one_drawing_require_rebuild(
    tmp_path: Path,
    first_handle: str,
    second_handle: str,
):
    drawing = tmp_path / "001-002 第一册.dwg"
    drawing.write_bytes(b"drawing")
    workspace = _planning_workspace(
        tmp_path,
        [
            Subset(
                "subset-1",
                "001-002 第一册",
                0,
                [
                    _planning_sheet("sheet-1", "001", "第一册 (1)", drawing, first_handle),
                    _planning_sheet("sheet-2", "002", "第一册 (2)", drawing, second_handle),
                ],
            ),
        ],
    )

    plan = build_structural_plan(
        workspace,
        [{"type": "update_subset", "subset_id": "subset-1", "title": "改名后的第一册"}],
        SuffixOptions(True, 1),
    )

    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]] == [
        ("subset-1", "rebuild"),
    ]


def test_same_numeric_handle_in_different_drawings_can_rename(tmp_path: Path):
    first = tmp_path / "001 第一册.dwg"
    second = tmp_path / "002 第二册.dwg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    workspace = _planning_workspace(
        tmp_path,
        [
            Subset("subset-1", "001 第一册", 0, [_planning_sheet("sheet-1", "001", "第一册", first, "A")]),
            Subset("subset-2", "002 第二册", 1, [_planning_sheet("sheet-2", "002", "第二册", second, "0A")]),
        ],
    )

    plan = build_structural_plan(
        workspace,
        [
            {"type": "update_subset", "subset_id": "subset-1", "title": "第一分册"},
            {"type": "update_subset", "subset_id": "subset-2", "title": "第二分册"},
        ],
        SuffixOptions(True, 1),
    )

    assert [group["cad_operation"] for group in plan["groups"]] == ["rename_only", "rename_only"]


def test_insert_subset_plan_creates_one_new_dwg_without_deleting_existing(tmp_path: Path):
    existing = tmp_path / "GP-0001 目录.dwg"
    existing.write_bytes(b"existing")
    template = tmp_path / "模板" / "标准.dwt"
    template.parent.mkdir()
    template.write_bytes(b"template")
    workspace = _planning_workspace(
        tmp_path,
        [Subset("subset-1", "0001 目录", 0, [_planning_sheet("sheet-1", "0001", "目录", existing, "A1")])],
    )
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "燃气管道平面图",
        "initial_sheet_count": 2,
        "base_template_file": str(template),
        "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
    }

    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 1))

    assert len(plan["groups"]) == 1
    group = plan["groups"][0]
    assert group["operation"] == "create"
    assert group["expected_baseline"] is None
    assert group["source_target_file"] is None
    assert Path(group["source_snapshot"]) == template
    assert Path(group["target_file"]).parent == tmp_path
    assert Path(group["target_file"]).name.endswith(".dwg")
    assert plan["deleted_subsets"] == []


def test_batch_insert_plan_rebuilds_existing_dwg_in_final_layout_order(tmp_path: Path):
    drawing = tmp_path / "GP-0004-0005 燃气管道平面图.dwg"
    drawing.write_bytes(b"existing")
    template = tmp_path / "标准.dwt"
    template.write_bytes(b"template")
    workspace = _planning_workspace(
        tmp_path,
        [
            Subset(
                "subset-1",
                "0004-0005 燃气管道平面图",
                0,
                [
                    _planning_sheet("sheet-1", "0004", "燃气管道平面图 (1)", drawing, "A1"),
                    _planning_sheet("sheet-2", "0005", "燃气管道平面图 (2)", drawing, "A2"),
                ],
            ),
        ],
    )

    plan = build_structural_plan(
        workspace,
        [
            {
                "type": "insert_sheet",
                "target_subset_id": "subset-1",
                "ordinal": 1,
                "placement": "after",
                "count": 2,
                "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
            },
        ],
        SuffixOptions(True, 2),
    )

    group = plan["groups"][0]
    assert group["operation"] == "rebuild"
    assert Path(group["source_target_file"]) == drawing
    assert Path(group["source_snapshot"]) == drawing
    assert [layout["number"] for layout in group["layouts"]] == ["0004", "0005", "0006", "0007"]
    assert [layout["target_layout"] for layout in group["layouts"]] == [
        "0004 燃气管道平面图 (1)",
        "0005 燃气管道平面图 (2)",
        "0006 燃气管道平面图 (3)",
        "0007 燃气管道平面图 (4)",
    ]


def test_inserted_subset_replans_collateral_number_ranges_and_suffixes(tmp_path: Path):
    first = tmp_path / "GP-0001 燃气管道平面图.dwg"
    second = tmp_path / "GP-0002 燃气管道平面图.dwg"
    template = tmp_path / "标准.dwt"
    for path in (first, second, template):
        path.write_bytes(path.name.encode("utf-8"))
    workspace = _planning_workspace(
        tmp_path,
        [
            Subset("subset-1", "0001 燃气管道平面图", 0, [_planning_sheet("sheet-1", "0001", "燃气管道平面图 (1)", first, "A1")]),
            Subset("subset-2", "0002 燃气管道平面图", 1, [_planning_sheet("sheet-2", "0002", "燃气管道平面图 (2)", second, "A2")]),
        ],
    )

    plan = build_structural_plan(
        workspace,
        [
            {
                "type": "insert_subset",
                "ordinal": 1,
                "placement": "after",
                "title": "燃气管道平面图",
                "initial_sheet_count": 2,
                "base_template_file": str(template),
                "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
            },
        ],
        SuffixOptions(True, 2),
    )

    by_subset = {group["subset_id"]: group for group in plan["groups"]}
    created = next(group for group in plan["groups"] if group["operation"] == "create")
    assert [layout["number"] for layout in created["layouts"]] == ["0002", "0003"]
    assert [layout["title"] for layout in created["layouts"]] == ["燃气管道平面图 (2)", "燃气管道平面图 (3)"]
    assert by_subset["subset-2"]["operation"] == "rebuild"
    assert [layout["number"] for layout in by_subset["subset-2"]["layouts"]] == ["0004"]
    assert [layout["title"] for layout in by_subset["subset-2"]["layouts"]] == ["燃气管道平面图 (4)"]
    assert set(plan["path_graph"]["old_sources"]) == {str(first.resolve()), str(second.resolve())}
    assert len(plan["path_graph"]["final_targets"]) == 3


def test_first_subset_plan_uses_template_as_create_snapshot(tmp_path: Path):
    template = tmp_path / "标准.dwt"
    template.write_bytes(b"template")
    workspace = _planning_workspace(tmp_path, [])

    plan = build_structural_plan(
        workspace,
        [
            {
                "type": "insert_subset",
                "ordinal": 1,
                "title": "首个子集",
                "initial_sheet_count": 1,
                "base_template_file": str(template),
                "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
            },
        ],
        SuffixOptions(True, 1),
    )

    assert plan["groups"][0]["operation"] == "create"
    assert plan["groups"][0]["source_target_file"] is None
    assert Path(plan["groups"][0]["source_snapshot"]) == template
    assert json.loads(json.dumps(plan, ensure_ascii=False))["groups"][0]["operation"] == "create"


def test_insert_subset_plan_snapshot_uses_base_template_not_layout_template(tmp_path: Path):
    base_template = tmp_path / "图纸基底.dwg"
    layout_template = tmp_path / "布局模板.dwt"
    base_template.write_bytes(b"base")
    layout_template.write_bytes(b"layout-template")
    workspace = _planning_workspace(tmp_path, [])
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 1,
        "base_template_file": str(base_template),
        "source": {"type": "template_layout", "file": str(layout_template), "layout": "A3"},
    }

    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 1))

    group = plan["groups"][0]
    assert group["operation"] == "create"
    assert Path(group["source_snapshot"]) == base_template
    assert group["layouts"][0]["source_file"] == str(layout_template)


def test_structural_plan_rejects_layout_collision_after_one_derivation(tmp_path: Path, monkeypatch):
    drawing = tmp_path / "A.dwg"
    drawing.write_bytes(b"drawing")
    workspace = _planning_workspace(
        tmp_path,
        [Subset("subset-1", "001-002 分组", 0, [_planning_sheet("sheet-1", "001", "分组", drawing, "A1")])],
    )
    calls = 0
    duplicate_layout = LayoutReference(str(drawing), ".\\A.dwg", "重复布局", "A1", drawing)
    derived = DerivedDocument(
        [
            DerivedSubset(
                "subset-1",
                "分组",
                "001-002",
                "001-002 分组",
                [
                    Sheet("sheet-1", "001", "分组", duplicate_layout),
                    Sheet("sheet-2", "002", "分组", duplicate_layout),
                ],
                str(drawing),
                str(drawing),
            ),
        ],
        ["subset-1"],
        layout_sources={
            "sheet-1": {"type": "existing_snapshot", "file": str(drawing), "layout": "001 分组"},
            "sheet-2": {"type": "existing_snapshot", "file": str(drawing), "layout": "001 分组"},
        },
    )

    def derive_once(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return derived

    monkeypatch.setattr("dst_manager.domain.planning.derive_document_structure", derive_once)

    with pytest.raises(PlanningError) as exc_info:
        build_structural_plan(workspace, [], SuffixOptions(True, 1))

    assert exc_info.value.code == "DUPLICATE_LAYOUT_NAME"
    assert calls == 1


def test_worker_uses_persisted_execution_plan_without_rederiving(tmp_path: Path, monkeypatch):
    console = tmp_path / "accoreconsole.exe"
    plugin = tmp_path / "plugin.dll"
    console.write_bytes(b"console")
    plugin.write_bytes(b"plugin")
    workspace = _planning_workspace(tmp_path, [])
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    persisted_plan = {
        "groups": [],
        "deleted_subsets": [],
        "derived_document": {},
        "expected_file_hashes": {},
        "source_baselines": [],
        "cad_validation_deferred": True,
    }
    runner._execute = Mock(return_value={"status": "SUCCEEDED"})
    monkeypatch.setattr(
        "dst_manager.domain.planning.derive_document_structure",
        Mock(side_effect=AssertionError("Worker 不得重新派生计划")),
    )
    job = {
        "id": "job-1",
        "payload": {
            "base_revision_id": "revision",
            "commands": [],
            "plan": {"execution_intent": persisted_plan},
        },
    }

    capability = CadCapability("2020", console, plugin)
    result = runner.run(job, workspace, capability)

    assert result == {"status": "SUCCEEDED"}
    runner._execute.assert_called_once_with("job-1", "local-worker", 1, workspace, capability, [], persisted_plan)


@pytest.mark.parametrize("cad_validation_deferred", [None, False], ids=["missing", "false"])
def test_worker_rejects_persisted_plan_without_deferred_cad_validation(tmp_path: Path, cad_validation_deferred: bool | None):
    console = tmp_path / "accoreconsole.exe"
    plugin = tmp_path / "plugin.dll"
    console.write_bytes(b"console")
    plugin.write_bytes(b"plugin")
    workspace = _planning_workspace(tmp_path, [])
    database = Mock()
    database.get_job.return_value = {"status": "FAILED", "error_code": "EXECUTION_SOURCE_BASELINE_MISMATCH"}
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    runner._execute = Mock(return_value={"status": "SUCCEEDED"})
    plan = {
        "groups": [],
        "expected_file_hashes": {},
        "source_baselines": [],
    }
    if cad_validation_deferred is not None:
        plan["cad_validation_deferred"] = cad_validation_deferred
    job = {
        "id": "job-1",
        "payload": {
            "base_revision_id": "revision",
            "commands": [],
            "plan": {"execution_intent": plan},
        },
    }

    runner.run(job, workspace, CadCapability("2020", console, plugin))

    runner._execute.assert_not_called()
    assert any(
        call.args[3] == "EXECUTION_SOURCE_BASELINE_MISMATCH"
        for call in database.update_job.call_args_list
        if len(call.args) >= 4
    )


def test_missing_source_baseline_is_rejected_before_cad_staging(tmp_path: Path):
    console = tmp_path / "accoreconsole.exe"
    plugin = tmp_path / "plugin.dll"
    console.write_bytes(b"console")
    plugin.write_bytes(b"plugin")
    workspace = _planning_workspace(tmp_path, [])
    missing = tmp_path / "missing.dwt"
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "title": "首个子集",
        "initial_sheet_count": 1,
        "base_template_file": str(missing),
        "source": {"type": "template_layout", "file": str(missing), "layout": "A3"},
    }
    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 1))
    plan["expected_file_hashes"] = {str(missing.resolve()): None}
    plan["cad_validation_deferred"] = True
    database = Mock()
    database.get_job.return_value = {"status": "FAILED", "error_code": "TEMPLATE_NOT_FOUND"}
    runner = CadJobRunner(database, DstCodec(), Mock(), 30)
    job = {
        "id": "job-1",
        "payload": {
            "base_revision_id": "revision",
            "commands": [command],
            "plan": {"execution_intent": plan},
        },
    }

    runner.run(job, workspace, CadCapability("2020", console, plugin))

    assert any(
        call.args[3] == "EXECUTION_SOURCE_BASELINE_MISSING"
        for call in database.update_job.call_args_list
        if len(call.args) >= 4
    )


@pytest.mark.parametrize("template_is_target", [False, True])
def test_create_target_collision_is_blocked_before_cad(tmp_path: Path, template_is_target: bool):
    workspace = _planning_workspace(tmp_path, [])
    target = tmp_path / "1 新建.dwg"
    template = target if template_is_target else tmp_path / "模板.dwt"
    template.write_bytes(b"template" if template_is_target else b"template-source")
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "title": "新建",
        "initial_sheet_count": 1,
        "base_template_file": str(template),
        "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
    }
    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 1))
    if not template_is_target:
        target.write_bytes(b"unrelated")
    database = Mock()
    runner = CadJobRunner(database, DstCodec(), Mock(), 30)
    runner._run_groups = Mock(side_effect=AssertionError("目标碰撞时不得启动 CAD"))

    with pytest.raises(PlanningError) as exc_info:
        runner._execute(
            "job-collision",
            "worker",
            1,
            workspace,
            CadCapability("2020", None, tmp_path / "plugin.dll"),
            [command],
            plan,
        )

    assert exc_info.value.code == "CREATE_TARGET_EXISTS"
    runner._run_groups.assert_not_called()
    assert target.read_bytes() == (b"template" if template_is_target else b"unrelated")


def test_snapshot_copy_rejects_change_after_baseline(tmp_path: Path):
    source = tmp_path / "source.dwg"
    snapshot = tmp_path / "snapshot.dwg"
    source.write_bytes(b"baseline")
    expected = capture_file_baseline(source)
    source.write_bytes(b"external")

    with pytest.raises(PlanningError) as exc_info:
        CadJobRunner._copy_verified_snapshot(source, snapshot, expected)

    assert exc_info.value.code == "BASE_FILE_CHANGED"
    assert not snapshot.exists()


def test_snapshot_copy_accepts_unchanged_identity_baseline(tmp_path: Path):
    source = tmp_path / "unchanged-source.dwg"
    snapshot = tmp_path / "unchanged-snapshot.dwg"
    source.write_bytes(b"baseline")
    expected = capture_file_baseline(source)
    assert expected is not None

    CadJobRunner._copy_verified_snapshot(source, snapshot, expected)

    assert snapshot.read_bytes() == b"baseline"


def test_cad_execution_rejects_captured_hash_that_differs_from_preview(tmp_path: Path):
    planned = _planning_workspace(tmp_path, [])
    workspace = Workspace(
        planned.id,
        planned.root,
        planned.dst_path,
        file_sha256(planned.dst_path),
        planned.document,
    )
    source = tmp_path / "source.dwg"
    source.write_bytes(b"external")
    captured = {
        workspace.dst_path.resolve(): capture_file_baseline(workspace.dst_path),
        source.resolve(): capture_file_baseline(source),
    }
    plan = {
        "expected_file_hashes": {
            str(workspace.dst_path.resolve()): workspace.revision_id,
            str(source.resolve()): hashlib.sha256(b"preview").hexdigest(),
        },
    }

    with pytest.raises(PlanningError) as exc_info:
        CadJobRunner._validate_expected_hashes(plan, captured, workspace)

    assert exc_info.value.code == "BASE_FILE_CHANGED"


def test_cad_execution_rejects_source_identity_that_differs_from_preview(tmp_path: Path):
    planned = _planning_workspace(tmp_path, [])
    workspace = Workspace(
        planned.id,
        planned.root,
        planned.dst_path,
        file_sha256(planned.dst_path),
        planned.document,
    )
    source = tmp_path / "source.dwg"
    source.write_bytes(b"preview")
    captured = {
        workspace.dst_path.resolve(): capture_file_baseline(workspace.dst_path),
        source.resolve(): capture_file_baseline(source),
    }
    plan = {
        "expected_file_hashes": {
            str(workspace.dst_path.resolve()): workspace.revision_id,
            str(source.resolve()): file_sha256(source),
        },
        "expected_file_identities": {str(source.resolve()): [0, 0, 0]},
    }

    with pytest.raises(PlanningError) as exc_info:
        CadJobRunner._validate_expected_hashes(plan, captured, workspace)

    assert exc_info.value.code == "BASE_FILE_CHANGED"


def test_startup_immutable_manifest_failure_quarantines_job_without_finalizing_manifest(tmp_path: Path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    dst = root / "set.dst"
    dst.write_bytes(b"dst")
    settings = Settings(data_dir=tmp_path / "data")
    settings.data_dir.mkdir()
    database = service_module.Database(settings.database_url)
    database.upsert_workspace("workspace", root, dst, file_sha256(dst))
    database.create_job(
        "operation",
        "workspace",
        "change_set",
        JobStatus.PUBLISHING,
        {"base_revision_id": file_sha256(dst)},
    )
    journal = root / ".dst-manager" / "jobs" / "operation" / "publish-journal.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        RecoverablePublisher,
        "recover",
        lambda *_: (_ for _ in ()).throw(PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")),
    )
    monkeypatch.setattr(
        RecoverablePublisher,
        "list_committed_operations",
        lambda *_: (_ for _ in ()).throw(AssertionError("不应基于不可信 manifest 完结任务")),
    )

    restarted = DstManagerService(settings)

    job = restarted.database.get_job("operation")
    assert job is not None
    assert job["status"] == JobStatus.NEEDS_REVIEW
    assert job["error_code"] == "PUBLISH_MANIFEST_IMMUTABLE_MISMATCH"
    restarted.database.create_job("next-operation", "workspace", "change_set", JobStatus.VALIDATED, {})


def test_duplicate_staged_results_for_final_target_are_rejected(tmp_path: Path):
    target = tmp_path / "same.dwg"
    first = tmp_path / "first.dwg"
    second = tmp_path / "second.dwg"
    result_arguments = ({}, 1, tmp_path / "log", None, 1)
    results = [
        RebuildResult(0, target, None, first, *result_arguments),
        RebuildResult(1, target, None, second, *result_arguments),
    ]
    plan = {
        "groups": [{"target_file": str(target)}, {"target_file": str(target)}],
        "path_graph": {"delete_targets": []},
    }

    with pytest.raises(PlanningError) as exc_info:
        CadJobRunner._collect_staged_files(results, plan)

    assert exc_info.value.code == "DUPLICATE_STAGED_TARGET"


def test_structural_preview_is_fast_and_defers_cad_validation(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    service.get_layout_names = Mock(side_effect=AssertionError("预览不得调用 CAD"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 1,
        "base_template_file": str(tmp_path / "A.dwg"),
        "source": {"type": "template_layout", "file": str(tmp_path / "A.dwg"), "layout": "001 平面"},
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], "2016")

    assert preview["executable"] is True
    assert preview["execution_intent"]["cad_validation_deferred"] is True
    assert preview["execution_intent"]["source_baselines"][0]["sha256"] == file_sha256(tmp_path / "A.dwg")
    assert "source_inspections" not in preview["execution_intent"]
    assert not (tmp_path / ".dst-manager").exists()
    service.get_layout_names.assert_not_called()


def test_open_workspace_reports_unreferenced_dwg_without_crashing(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    (tmp_path / "孤儿.dwg").write_bytes(b"fake-unreferenced")
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    codes = {item.code for item in workspace.document.diagnostics}
    assert "UNREFERENCED_DWG" in codes


def test_service_persists_insert_subset_baselines_for_worker(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 2,
        "base_template_file": str(tmp_path / "A.dwg"),
        "source": {"type": "template_layout", "file": str(tmp_path / "A.dwg"), "layout": "001 平面"},
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], "2016")
    job = service.execute_changes(
        workspace.id,
        workspace.revision_id,
        [command],
        "2016",
        preview_digest=preview["preview_digest"],
    )

    assert preview["executable"] is True, preview["diagnostics"]
    assert any(group["operation"] == "create" for group in preview["execution_intent"]["groups"])
    assert preview["execution_intent"]["source_baselines"] == [
        {
            "path": str((tmp_path / "A.dwg").resolve()),
            "sha256": file_sha256(tmp_path / "A.dwg"),
            "identity": list(capture_file_baseline(tmp_path / "A.dwg").identity),
            "source_types": ["existing_snapshot", "template_layout"],
            "requested_layouts": ["001 平面"],
        },
    ]
    assert job["payload"]["plan"]["execution_intent"] == preview["execution_intent"]


def test_structural_preview_binds_dst_sources_and_create_targets_to_content_hashes(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 1,
        "base_template_file": str(tmp_path / "A.dwg"),
        "source": {"type": "template_layout", "file": str(tmp_path / "A.dwg"), "layout": "001 平面"},
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command])
    intent = preview["execution_intent"]
    expected = intent["expected_file_hashes"]

    assert expected[str(dst.resolve())] == workspace.revision_id
    assert expected[str((tmp_path / "A.dwg").resolve())] == file_sha256(tmp_path / "A.dwg")
    create_target = next(group["target_file"] for group in intent["groups"] if group["operation"] == "create")
    assert expected[str(Path(create_target).resolve())] is None


def test_structural_preview_estimates_core_console_count_concurrency_and_historical_duration(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data", cad_max_parallel=3))
    service.database.cad_duration_history = Mock(return_value=[10_000, 20_000, 30_000])
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_sheet",
        "target_subset_id": workspace.document.subsets[0].acsm_id,
        "ordinal": 1,
        "placement": "after",
        "count": 1,
        "source": {"type": "existing_snapshot", "file": str(tmp_path / "A.dwg"), "layout": "001 平面"},
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], "2020")
    estimate = preview["execution_intent"]["estimate"]

    assert estimate == {
        "schema_version": 1,
        "estimated": True,
        "core_console_count": 1,
        "concurrency": 1,
        "duration_ms": {"lower": 10_000, "upper": 30_000},
        "sources": [{"cad_operation": "rebuild", "sample_count": 3, "source": "history"}],
    }


def test_structural_preview_resolves_existing_snapshot_from_target_subset(tiny_workspace, tmp_path: Path):
    """existing_snapshot 空来源在预览规划期解析为目标子集首图登记，下游零改动。"""
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)

    preview = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{
            "type": "insert_sheet",
            "target_subset_id": workspace.document.subsets[0].acsm_id,
            "ordinal": 1,
            "placement": "after",
            "count": 1,
            "source": {"type": "existing_snapshot"},
        }],
    )

    assert preview["executable"] is True, preview["diagnostics"]
    group = preview["execution_intent"]["groups"][0]
    resolved = group["layouts"][1]
    assert resolved["source_type"] == "existing_snapshot"
    assert resolved["source_file"] == str((tmp_path / "A.dwg").resolve())
    assert resolved["source_layout"] == "001 平面"
    # 解析出的 DWG 进入既有来源基准（SHA-256）链路
    assert str((tmp_path / "A.dwg").resolve()) in {
        item["path"] for item in preview["execution_intent"]["source_baselines"]
    }


def test_cad_estimate_never_places_a_long_task_below_its_own_duration(tmp_path: Path):
    service = DstManagerService(Settings(data_dir=tmp_path / "data", cad_max_parallel=4))
    service.database.cad_duration_history = Mock(return_value=[])
    intent = {
        "groups": [
            {"cad_operation": "rebuild"},
            {"cad_operation": "rename_only"},
            {"cad_operation": "rename_only"},
            {"cad_operation": "rename_only"},
        ],
    }

    estimate = service._estimate_cad_execution("2020", intent)

    assert estimate["duration_ms"] == {"lower": 45_000, "upper": 120_000}


def test_cad_estimate_simulates_worker_plan_order_instead_of_optimized_order(tmp_path: Path):
    service = DstManagerService(Settings(data_dir=tmp_path / "data", cad_max_parallel=2))
    service.database.cad_duration_history = Mock(return_value=[])
    intent = {
        "groups": [
            {"cad_operation": "rename_only"},
            {"cad_operation": "rename_only"},
            {"cad_operation": "rebuild"},
        ],
    }

    estimate = service._estimate_cad_execution("2020", intent)

    assert estimate["duration_ms"] == {"lower": 55_000, "upper": 150_000}


def test_structural_execute_requires_confirmed_preview_digest(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 1,
        "base_template_file": str(tmp_path / "A.dwg"),
        "source": {"type": "template_layout", "file": str(tmp_path / "A.dwg"), "layout": "001 平面"},
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], "2016")
    create_job = Mock(wraps=service.database.create_job)
    service.database.create_job = create_job

    assert preview["preview_digest"]
    with pytest.raises(ApplicationError) as exc_info:
        service.execute_changes(
            workspace.id,
            workspace.revision_id,
            [command],
            "2016",
            preview_digest="different-preview",
        )

    assert exc_info.value.code == "REPREVIEW_REQUIRED"
    create_job.assert_not_called()


def test_structural_execute_requires_repreview_after_source_baseline_changes(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    source = tmp_path / "A.dwg"
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 1,
        "base_template_file": str(source),
        "source": {"type": "template_layout", "file": str(source), "layout": "001 平面"},
    }
    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], "2016")
    source.write_bytes(b"changed-after-preview")

    with pytest.raises(ApplicationError) as exc_info:
        service.execute_changes(
            workspace.id,
            workspace.revision_id,
            [command],
            "2016",
            preview_digest=preview["preview_digest"],
        )

    assert exc_info.value.code == "REPREVIEW_REQUIRED"


def test_structural_preview_allows_legal_absolute_template_outside_workspace(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    outside = tmp_path.parent / "outside-template.dwt"
    outside.write_bytes(b"template")
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)

    preview = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{
            "type": "insert_subset",
            "ordinal": 1,
            "placement": "after",
            "title": "新建子集",
            "initial_sheet_count": 1,
            "base_template_file": str(outside),
            "source": {"type": "template_layout", "file": str(outside), "layout": "A3"},
        }],
    )

    assert preview["executable"] is True
    assert preview["execution_intent"]["source_baselines"][0]["path"] == str(outside.resolve())


def test_normalized_sheet_property_update_has_semantic_before_after(tiny_workspace, tmp_path: Path):
    dst, sheet_id = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)

    preview = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_properties", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}],
    )

    assert preview["changes"][0]["type"] == "update_sheet"
    assert preview["semantic_diff"]["properties"] == [{
        "action": "update",
        "type": "sheet",
        "name": "比例",
        "before": "1:100",
        "after": "1:200",
        "affected_sheet_count": 1,
    }]


def test_sheet_set_name_update_has_human_readable_before_after(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)

    preview = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "新图纸集名称"}],
    )

    assert preview["semantic_diff"]["sheet_set"] == [
        {
            "field": "name",
            "before": workspace.document.name,
            "after": "新图纸集名称",
        },
    ]


def test_derived_dwg_name_removes_stale_number_range_without_misreading_parenthetical_title(tmp_path: Path):
    existing = tmp_path / "001-002 设备 (一期).dwg"
    sheets = [
        Sheet("sheet-1", "003", "设备 (一期)", LayoutReference("", "", "", "")),
        Sheet("sheet-2", "004", "设备 (一期)", LayoutReference("", "", "", "")),
    ]

    subset_name, derived_path = derive_subset_and_dwg_name(existing, sheets)

    assert subset_name == "3-4 设备 (一期)"
    assert derived_path.name == "003-004 设备 (一期).dwg"


def test_structural_preview_blocks_outside_source_without_invoking_cad(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    outside = tmp_path.parent / "outside-source.dwg"
    outside.write_bytes(b"template")
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    service.get_layout_names = Mock(side_effect=AssertionError("预览不得调用 CAD"))
    workspace = service.open_workspace(dst)

    preview = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{
            "type": "insert_sheet",
            "target_subset_id": workspace.document.subsets[0].acsm_id,
            "ordinal": 1,
            "placement": "after",
            "count": 1,
            "source": {"type": "existing_snapshot", "file": str(outside), "layout": "A3"},
        }],
    )

    assert preview["executable"] is False
    assert preview["diagnostics"][0]["code"] == "LAYOUT_SOURCE_OUTSIDE_WORKSPACE"
    service.get_layout_names.assert_not_called()


def test_structural_preview_defers_layout_existence_to_cad_worker(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 1,
        "base_template_file": str(tmp_path / "A.dwg"),
        "source": {"type": "template_layout", "file": str(tmp_path / "A.dwg"), "layout": "A3"},
    }
    preview = service.preview_changes(workspace.id, workspace.revision_id, [command])

    assert preview["executable"] is True
    assert "A3" in preview["execution_intent"]["source_baselines"][0]["requested_layouts"]


def test_preview_semantic_diff_contains_complete_structure_properties_and_dwgs(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    structural = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{
            "type": "insert_subset",
            "ordinal": 1,
            "placement": "after",
            "title": "新建子集",
            "initial_sheet_count": 1,
            "base_template_file": str(tmp_path / "A.dwg"),
            "source": {"type": "template_layout", "file": str(tmp_path / "A.dwg"), "layout": "001 平面"},
        }],
    )
    properties = service.preview_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"}],
    )

    assert [item["position"] for item in structural["semantic_diff"]["structure"]["before"]] == [1]
    assert [item["position"] for item in structural["semantic_diff"]["structure"]["after"]] == [1, 2]
    assert structural["semantic_diff"]["structure"]["after"][1]["sheets"][0].keys() >= {
        "position", "id", "number", "title", "suffix", "dwg_file", "layout_name",
    }
    assert structural["semantic_diff"]["dwgs"][0].keys() >= {"action", "before", "after"}
    assert properties["semantic_diff"]["properties"][0]["affected_sheet_count"] == 1
    assert properties["changes"][0]["affected_sheet_count"] == 1


def test_cad_runner_rejects_missing_or_mismatched_source_baselines(tmp_path: Path):
    source = tmp_path / "A.dwg"
    source.write_bytes(b"source")
    baseline = capture_file_baseline(source)
    assert baseline is not None
    plan = {
        "cad_validation_deferred": True,
        "groups": [{
            "operation": "create",
            "source_snapshot": str(source),
            "layouts": [{"source_file": str(source), "source_layout": "A3", "source_type": "template_layout"}],
        }],
        "expected_file_hashes": {str(source.resolve()): file_sha256(source)},
        "expected_file_identities": {str(source.resolve()): list(baseline.identity)},
    }

    with pytest.raises(PlanningError) as missing:
        CadJobRunner._validate_source_baselines(plan)
    plan["source_baselines"] = [{
        "path": str(source.resolve()),
        "sha256": file_sha256(source),
        "identity": list(baseline.identity),
        "source_types": ["template_layout"],
        "requested_layouts": ["A3"],
    }]
    CadJobRunner._validate_source_baselines(plan)
    plan["source_baselines"][0]["identity"] = ["unexpected"]
    with pytest.raises(PlanningError) as mismatch:
        CadJobRunner._validate_source_baselines(plan)
    plan["source_baselines"][0].pop("identity")
    plan.pop("expected_file_identities")
    with pytest.raises(PlanningError) as malformed:
        CadJobRunner._validate_source_baselines(plan)

    assert missing.value.code == "EXECUTION_SOURCE_BASELINE_MISSING"
    assert mismatch.value.code == "EXECUTION_SOURCE_BASELINE_MISMATCH"
    assert malformed.value.code == "EXECUTION_SOURCE_BASELINE_MISMATCH"


def test_metadata_service_passes_identity_baseline_to_publisher(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    delegate = RecoverablePublisher()
    calls = 0

    class IdentityCheckingPublisher:
        def recover(self, *args, **kwargs):
            return delegate.recover(*args, **kwargs)

        def publish(self, *args, expected_baselines=None, **kwargs):
            nonlocal calls
            calls += 1
            assert expected_baselines is not None
            assert all(
                baseline is None or isinstance(baseline, ExpectedFileBaseline)
                for baseline in expected_baselines.values()
            )
            return delegate.publish(
                *args,
                expected_baselines=expected_baselines,
                **kwargs,
            )

        def read_committed_operation(self, *args, **kwargs):
            return delegate.read_committed_operation(*args, **kwargs)

    service.publisher = IdentityCheckingPublisher()

    result = _execute_confirmed(
        service,
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "身份基准"}],
    )

    assert result["status"] == "SUCCEEDED"
    assert calls == 1


def test_worker_poll_rechecks_stale_jobs_after_initialization(tmp_path: Path):
    service = object.__new__(DstManagerService)
    service.settings = SimpleNamespace(worker_lease_seconds=120)
    service.database = Mock()
    service.database.claim_next_job.return_value = None

    assert service.run_next_job() is None

    service.database.recover_stale_jobs.assert_called_once_with(120)


def test_committed_journal_review_quarantine_is_not_auto_finalized(tmp_path: Path):
    service = object.__new__(DstManagerService)
    service.database = Mock()
    service.database.get_job.return_value = {
        "status": JobStatus.NEEDS_REVIEW,
        "error_code": "PUBLISH_JOURNAL_REVIEW_REQUIRED",
    }

    service._recover_committed_job(
        tmp_path,
        {"operation_id": "job-1", "status": "COMMITTED", "files": []},
    )

    service.database.finalize_committed_job.assert_not_called()
    service.database.finalize_job_terminal.assert_not_called()


def test_stale_publishing_job_with_committed_journal_is_not_auto_finalized(tmp_path: Path):
    service = object.__new__(DstManagerService)
    service.database = Mock()
    service.settings = SimpleNamespace(worker_lease_seconds=120)
    service.database.get_job.return_value = {
        "status": JobStatus.PUBLISHING,
        "heartbeat_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    }

    service._recover_committed_job(
        tmp_path,
        {"operation_id": "job-1", "status": "COMMITTED", "files": []},
    )

    service.database.finalize_committed_job.assert_not_called()
    service.database.finalize_job_terminal.assert_not_called()


def test_repeating_same_content_creates_distinct_operation_revisions(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    command = [{"type": "update_sheet_set", "name": "相同内容"}]

    first = _execute_confirmed(service, workspace.id, workspace.revision_id, command)
    repeated_base = file_sha256(dst)
    second = _execute_confirmed(service, workspace.id, repeated_base, command)

    assert first["status"] == second["status"] == "SUCCEEDED"
    revisions = service.database.list_revisions(workspace.id)
    assert len(revisions) == 2
    assert revisions[0]["id"] != revisions[1]["id"]
    assert revisions[0]["result_hash"] == revisions[1]["result_hash"] == file_sha256(dst)


def test_returning_to_old_content_keeps_distinct_revision_history(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    original_hash = workspace.revision_id
    first = _execute_confirmed(
        service,
        workspace.id,
        original_hash,
        [{"type": "update_sheet_set", "name": "临时名称"}],
    )

    second = _execute_confirmed(
        service,
        workspace.id,
        file_sha256(dst),
        [{"type": "update_sheet_set", "name": "测试集"}],
    )

    assert first["status"] == second["status"] == "SUCCEEDED"
    revisions = service.database.list_revisions(workspace.id)
    assert len(revisions) == 2
    assert len({item["id"] for item in revisions}) == 2
    assert revisions[0]["result_hash"] == file_sha256(dst)


def test_metadata_execution_rejects_atomic_replacement_before_locked_baseline(
    tiny_workspace,
    tmp_path: Path,
    monkeypatch,
):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    before = dst.read_bytes()
    original_capture = service_module.capture_file_baseline
    injected = False

    def replace_then_capture(path: Path):
        nonlocal injected
        if not injected and path.resolve() == dst.resolve():
            replacement = dst.with_suffix(".external")
            replacement.write_bytes(b"external-version")
            replacement.replace(dst)
            injected = True
        return original_capture(path)

    commands = [{"type": "update_sheet_set", "name": "不得覆盖外部版本"}]
    preview = service.preview_changes(workspace.id, workspace.revision_id, commands)
    monkeypatch.setattr(service_module, "capture_file_baseline", replace_then_capture)

    result = service.execute_changes(
        workspace.id,
        workspace.revision_id,
        commands,
        preview_digest=preview["preview_digest"],
    )

    assert result["status"] == "FAILED"
    assert result["error_code"] in {"REVISION_CONFLICT", "PUBLISH_BASE_CHANGED"}
    assert dst.read_bytes() in {before, b"external-version"}
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_restore_rejects_atomic_replacement_after_preview_before_locked_baseline(
    tiny_workspace,
    tmp_path: Path,
    monkeypatch,
):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    _execute_confirmed(
        service,
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "已发布版本"}],
    )
    revision_id = service.database.list_revisions(workspace.id)[0]["id"]
    current_revision = file_sha256(dst)
    before = dst.read_bytes()
    restore_preview = service.preview_revision_restore(workspace.id, revision_id)
    original_capture = service_module.capture_file_baseline
    injected = False

    def replace_then_capture(path: Path):
        nonlocal injected
        if not injected and path.resolve() == dst.resolve():
            replacement = dst.with_suffix(".external")
            replacement.write_bytes(b"external-after-preview")
            replacement.replace(dst)
            injected = True
        return original_capture(path)

    monkeypatch.setattr(service_module, "capture_file_baseline", replace_then_capture)

    result = service.restore_revision(
        workspace.id,
        revision_id,
        current_revision,
        preview_digest=restore_preview["preview_digest"],
    )

    assert result["status"] == "FAILED"
    assert result["error_code"] in {"REVISION_RESTORE_CONFLICT", "PUBLISH_BASE_CHANGED"}
    assert dst.read_bytes() in {before, b"external-after-preview"}
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_startup_finalizes_committed_publish_exactly_once_after_repeated_restart(
    tiny_workspace,
    tmp_path: Path,
):
    dst, _ = tiny_workspace
    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    workspace = service.open_workspace(dst)
    operation_id = "committed-before-db-finalize"
    service.database.create_job(
        operation_id,
        workspace.id,
        "change_set",
        JobStatus.PUBLISHING,
        {"base_revision_id": workspace.revision_id, "plan": {"requires_cad": False}},
    )
    staged = tmp_path / "committed.dst"
    staged.write_bytes(b"committed-result")
    service.publisher.publish(
        operation_id,
        workspace.root,
        {workspace.dst_path: staged},
        expected_baselines={workspace.dst_path: capture_file_baseline(workspace.dst_path)},
    )
    result_hash = file_sha256(workspace.dst_path)

    first_restart = DstManagerService(settings)
    second_restart = DstManagerService(settings)

    assert first_restart.database.get_job(operation_id)["status"] == "SUCCEEDED"
    assert second_restart.database.get_job(operation_id)["status"] == "SUCCEEDED"
    revisions = second_restart.database.list_revisions(workspace.id)
    recovered = [item for item in revisions if item["id"] == f"change-{operation_id}"]
    assert len(recovered) == 1
    assert recovered[0]["result_hash"] == result_hash
    with second_restart.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_startup_quarantines_committed_publish_when_result_changed(
    tiny_workspace,
    tmp_path: Path,
):
    dst, _ = tiny_workspace
    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    workspace = service.open_workspace(dst)
    operation_id = "committed-result-changed"
    service.database.create_job(
        operation_id,
        workspace.id,
        "change_set",
        JobStatus.PUBLISHING,
        {"base_revision_id": workspace.revision_id, "plan": {"requires_cad": False}},
    )
    staged = tmp_path / "committed-changed.dst"
    staged.write_bytes(b"committed-result")
    service.publisher.publish(
        operation_id,
        workspace.root,
        {workspace.dst_path: staged},
        expected_baselines={workspace.dst_path: capture_file_baseline(workspace.dst_path)},
    )
    replacement = tmp_path / "external-after-committed.dst"
    replacement.write_bytes(b"external-after-committed")
    replacement.replace(workspace.dst_path)

    restarted = DstManagerService(settings)

    recovered_job = restarted.database.get_job(operation_id)
    assert recovered_job["status"] == "NEEDS_REVIEW"
    assert recovered_job["error_code"] == "COMMITTED_RECOVERY_UNPROVEN"
    assert "COMMITTED_RESULT_CHANGED" in recovered_job["error_detail"]
    assert restarted.database.list_revisions(workspace.id) == []
    with restarted.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_restore_finalize_failure_enters_needs_review_without_live_lock(
    tiny_workspace,
    tmp_path: Path,
    monkeypatch,
):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    _execute_confirmed(
        service,
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "待恢复版本"}],
    )
    revision_id = service.database.list_revisions(workspace.id)[0]["id"]
    base_revision_id = file_sha256(dst)

    def fail_finalize(*_args, **_kwargs):
        raise OSError("注入数据库 finalize 故障")

    monkeypatch.setattr(service.database, "finalize_committed_job", fail_finalize)

    result = _restore_confirmed(service, workspace.id, revision_id, base_revision_id)

    assert result["status"] == "NEEDS_REVIEW"
    assert result["error_code"] == "COMMITTED_FINALIZE_FAILED"
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_restore_staging_copy_failure_becomes_failed_and_releases_lock(
    tiny_workspace,
    tmp_path: Path,
    monkeypatch,
):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    _execute_confirmed(
        service,
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "待复制恢复"}],
    )
    revision_id = service.database.list_revisions(workspace.id)[0]["id"]
    base_revision_id = file_sha256(dst)
    monkeypatch.setattr(service_module.shutil, "copy2", Mock(side_effect=OSError("注入 copy 故障")))

    result = _restore_confirmed(service, workspace.id, revision_id, base_revision_id)

    assert result["status"] == "FAILED"
    assert result["error_code"] == "REVISION_RESTORE_STAGING_FAILED"
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (PublishBaselineError("注入 publisher baseline 故障"), "FAILED"),
        (PublishRecoveryError("注入 publisher recovery 故障"), "NEEDS_REVIEW"),
    ],
)
def test_restore_publisher_failures_use_safe_terminal_status(
    tiny_workspace,
    tmp_path: Path,
    monkeypatch,
    failure: Exception,
    expected_status: str,
):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    _execute_confirmed(
        service,
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "待发布恢复"}],
    )
    revision_id = service.database.list_revisions(workspace.id)[0]["id"]
    base_revision_id = file_sha256(dst)
    monkeypatch.setattr(service.publisher, "publish", Mock(side_effect=failure))

    result = _restore_confirmed(service, workspace.id, revision_id, base_revision_id)

    assert result["status"] == expected_status
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_restore_rejects_permanent_backup_replacement_before_copy(
    tiny_workspace,
    tmp_path: Path,
    monkeypatch,
):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    _execute_confirmed(
        service,
        workspace.id,
        workspace.revision_id,
        [{"type": "update_sheet_set", "name": "建立永久快照"}],
    )
    revision = service.database.list_revisions(workspace.id)[0]
    manifest = json.loads((Path(revision["revision_dir"]) / "manifest.json").read_text(encoding="utf-8"))
    backup = Path(next(item for item in manifest["files"] if Path(item["target"]) == dst)["backup"])
    backup_before = backup.read_bytes()
    base_revision_id = file_sha256(dst)
    restore_preview = service.preview_revision_restore(workspace.id, revision["id"])
    original_copy = service_module.shutil.copy2
    injected = False

    def replace_backup_before_copy(source: Path, target: Path, *args, **kwargs):
        nonlocal injected
        if not injected and Path(source).resolve() == backup.resolve():
            replacement = backup.with_suffix(".external")
            replacement.write_bytes(b"corrupt-backup")
            replacement.replace(backup)
            injected = True
        return original_copy(source, target, *args, **kwargs)

    monkeypatch.setattr(service_module.shutil, "copy2", replace_backup_before_copy)

    result = service.restore_revision(
        workspace.id,
        revision["id"],
        base_revision_id,
        preview_digest=restore_preview["preview_digest"],
    )

    assert result["status"] == "FAILED"
    assert result["error_code"] in {"REVISION_RESTORE_SOURCE_CHANGED", "REVISION_RESTORE_STAGING_FAILED"}
    assert dst.read_bytes() != b"corrupt-backup"
    assert backup.read_bytes() in {backup_before, b"corrupt-backup"}
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_update_sheet_title_with_custom_properties_is_rejected_without_partial_commit(tiny_workspace, tmp_path: Path):
    dst, sheet_id = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    before = dst.read_bytes()
    command = {
        "type": "update_sheet",
        "sheet_id": sheet_id,
        "title": "不支持的标题",
        "custom_properties": {"比例": "1:500"},
    }

    with pytest.raises(ApplicationError) as exc_info:
        service.preview_changes(workspace.id, workspace.revision_id, [command])
    assert exc_info.value.code == "COMMAND_UNSUPPORTED"
    with pytest.raises(ApplicationError) as exc_info:
        service.execute_changes(workspace.id, workspace.revision_id, [command])
    assert exc_info.value.code == "COMMAND_UNSUPPORTED"
    assert dst.read_bytes() == before
    reopened = service.open_workspace(dst)
    assert reopened.document.sheets[0].custom_properties["比例"] == "1:100"


class _SuccessfulCadExecutor:
    def __init__(self, handle_text: str):
        self.handle_text = handle_text
        self.calls = 0
        self.scripts: list[Path] = []

    def run(self, _capability, drawing, script, _timeout):
        self.calls += 1
        self.scripts.append(script)
        drawing.with_suffix(".dst-handles.txt").write_text(self.handle_text, encoding="utf-8")
        return SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)


class _RenameSuccessfulCadExecutor:
    def __init__(self, final_layouts: list[str], renamed_count: int | None = None):
        self.final_layouts = final_layouts
        self.renamed_count = len(final_layouts) if renamed_count is None else renamed_count
        self.calls = 0
        self.scripts: list[Path] = []
        self.result_existed_at_start: bool | None = None

    def run(self, _capability, drawing, script, _timeout):
        self.calls += 1
        self.scripts.append(script)
        self.result_existed_at_start = rename_result_path(drawing).exists()
        rename_result_path(drawing).write_text(
            json.dumps(
                {
                    "version": 1,
                    "renamed_count": self.renamed_count,
                    "final_layouts": self.final_layouts,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)


def test_rename_group_uses_one_console_call_and_returns_no_bindings(tmp_path: Path):
    source = tmp_path / "001 第一册.dwg"
    source.write_bytes(b"source")
    staging, scripts, logs = tmp_path / "staging", tmp_path / "scripts", tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    group = {
        "subset_id": "subset-1",
        "subset_name": "002 第一册",
        "operation": "rebuild",
        "cad_operation": "rename_only",
        "source_target_file": str(source),
        "target_file": str(tmp_path / "002 第一册.dwg"),
        "layouts": [{"sheet_id": "sheet-1", "original_layout": "001 第一册", "target_layout": "002 第一册"}],
    }
    unit = RebuildWorkUnit(0, group, source, staging, scripts, logs, 30)
    runner = CadJobRunner(Mock(), Mock(), Mock(), 30)
    executor = _RenameSuccessfulCadExecutor(["002 第一册"])
    runner.executor = executor

    result = runner._execute_group(
        "job-1",
        _planning_workspace(tmp_path, []),
        CadCapability("2020", None, tmp_path / "plugin.dll"),
        unit,
    )

    assert executor.calls == 1
    assert [script.name for script in executor.scripts] == ["rename-000.scr"]
    assert result.bindings == {}
    assert rename_result_path(result.staged).is_file()
    assert not result.staged.with_suffix(".dst-handles.txt").exists()


def test_rename_group_deletes_stale_result_before_starting_console(tmp_path: Path):
    source = tmp_path / "001 第一册.dwg"
    source.write_bytes(b"source")
    staging, scripts, logs = tmp_path / "staging", tmp_path / "scripts", tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    group = {
        "cad_operation": "rename_only",
        "source_target_file": str(source),
        "target_file": str(tmp_path / "002 第一册.dwg"),
        "layouts": [{"original_layout": "001 第一册", "target_layout": "002 第一册"}],
    }
    unit = RebuildWorkUnit(0, group, source, staging, scripts, logs, 30)
    stale_result = rename_result_path(staging / "group-000" / "002 第一册.dwg")
    stale_result.parent.mkdir()
    stale_result.write_text('{"version":1,"renamed_count":1,"final_layouts":["002 第一册"]}', encoding="utf-8")
    runner = CadJobRunner(Mock(), Mock(), Mock(), 30)
    executor = _RenameSuccessfulCadExecutor(["002 第一册"])
    runner.executor = executor

    runner._execute_group("job-1", _planning_workspace(tmp_path, []), CadCapability("2020", None, tmp_path / "plugin.dll"), unit)

    assert executor.result_existed_at_start is False


def test_rename_group_records_failure_without_starting_console_when_stale_result_cannot_be_deleted(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "001 第一册.dwg"
    source.write_bytes(b"source")
    staging, scripts, logs = tmp_path / "staging", tmp_path / "scripts", tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    group = {
        "cad_operation": "rename_only",
        "source_target_file": str(source),
        "target_file": str(tmp_path / "002 第一册.dwg"),
        "layouts": [{"original_layout": "001 第一册", "target_layout": "002 第一册"}],
    }
    unit = RebuildWorkUnit(0, group, source, staging, scripts, logs, 30)
    stale_result = rename_result_path(staging / "group-000" / "002 第一册.dwg")
    stale_result.parent.mkdir()
    stale_result.write_text('{"version":1,"renamed_count":1,"final_layouts":["002 第一册"]}', encoding="utf-8")
    original_unlink = Path.unlink

    def reject_result_delete(path: Path, *args, **kwargs):
        if path == stale_result:
            raise PermissionError("INJECTED_RESULT_DELETE_FAILURE")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", reject_result_delete)
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    runner.executor = Mock()
    runner.executor.run.return_value = SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)

    with pytest.raises(PermissionError, match="INJECTED_RESULT_DELETE_FAILURE"):
        runner._execute_group("job-1", _planning_workspace(tmp_path, []), CadCapability("2020", None, tmp_path / "plugin.dll"), unit)

    runner.executor.run.assert_not_called()
    assert database.upsert_job_file.call_args_list[-1].kwargs["status"] == "FAILED"
    assert stale_result.is_file()


def test_rename_group_rejects_mismatched_renamed_count(tmp_path: Path):
    source = tmp_path / "001 第一册.dwg"
    source.write_bytes(b"source")
    staging, scripts, logs = tmp_path / "staging", tmp_path / "scripts", tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    group = {
        "cad_operation": "rename_only",
        "source_target_file": str(source),
        "target_file": str(tmp_path / "002 第一册.dwg"),
        "layouts": [{"original_layout": "001 第一册", "target_layout": "002 第一册"}],
    }
    unit = RebuildWorkUnit(0, group, source, staging, scripts, logs, 30)
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    runner.executor = _RenameSuccessfulCadExecutor(["002 第一册"], renamed_count=0)

    with pytest.raises(ValueError, match="LAYOUT_RENAME_RESULT_INVALID"):
        runner._execute_group("job-1", _planning_workspace(tmp_path, []), CadCapability("2020", None, tmp_path / "plugin.dll"), unit)

    assert database.upsert_job_file.call_args_list[-1].kwargs["status"] == "FAILED"


def test_rename_group_records_finished_failure_when_request_is_invalid(tmp_path: Path):
    source = tmp_path / "source.dwg"
    source.write_bytes(b"source")
    staging, scripts, logs = tmp_path / "staging", tmp_path / "scripts", tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    unit = RebuildWorkUnit(
        0,
        {
            "cad_operation": "rename_only",
            "source_target_file": str(source),
            "target_file": str(tmp_path / "target.dwg"),
            "layouts": [{}],
        },
        source,
        staging,
        scripts,
        logs,
        30,
    )
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30)

    with pytest.raises(ValueError, match="LAYOUT_RENAME_REQUEST_INVALID"):
        runner._execute_group("job-1", _planning_workspace(tmp_path, []), CadCapability("2020", None, tmp_path / "plugin.dll"), unit)

    assert database.upsert_job_file.call_args_list[-1].kwargs["status"] == "FAILED"
    assert database.upsert_job_file.call_args_list[-1].kwargs["finished_at"] is not None
    assert database.upsert_job_file.call_args_list[-1].kwargs["duration_ms"] is not None


@pytest.mark.parametrize("cad_operation", ["rename_only", "rebuild"])
def test_group_setup_failure_records_terminal_file_state(tmp_path: Path, monkeypatch, cad_operation: str):
    source = tmp_path / "source.dwg"
    source.write_bytes(b"source")
    staging, scripts, logs = tmp_path / "staging", tmp_path / "scripts", tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    unit = RebuildWorkUnit(
        0,
        {
            "cad_operation": cad_operation,
            "source_target_file": str(source),
            "target_file": str(tmp_path / "target.dwg"),
            "layouts": [],
        },
        source,
        staging,
        scripts,
        logs,
        30,
    )
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    monkeypatch.setattr(cad_job_module.shutil, "copy2", Mock(side_effect=OSError("INJECTED_COPY_FAILURE")))

    with pytest.raises(OSError, match="INJECTED_COPY_FAILURE"):
        runner._execute_group("job-1", _planning_workspace(tmp_path, []), CadCapability("2020", None, tmp_path / "plugin.dll"), unit)

    assert [call.kwargs["status"] for call in database.upsert_job_file.call_args_list] == ["RUNNING", "FAILED"]
    assert database.upsert_job_file.call_args_list[-1].kwargs["cad_operation"] == cad_operation
    assert database.upsert_job_file.call_args_list[-1].kwargs["finished_at"] is not None


def test_rename_only_final_dst_preserves_existing_handle(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    workspace = Workspace("workspace", dst.parent, dst, "revision", document)
    plan = build_structural_plan(
        workspace,
        [{"type": "update_subset", "subset_id": document.subsets[0].acsm_id, "title": "改名后的子集"}],
        SuffixOptions(True, 1),
    )
    assert plan["groups"][0]["cad_operation"] == "rename_only"

    staged = CadJobRunner(Mock(), DstCodec(), Mock(), 30)._write_staged_dst(workspace, plan, {}, tmp_path)

    final_sheet = AcsmDocument(DstCodec().decode_file(staged)).project(dst.parent).sheets[0]
    assert final_sheet.layout.handle == "AB"
    assert final_sheet.layout.file_name == str(Path(plan["groups"][0]["target_file"]).resolve())
    assert final_sheet.layout.layout_name == plan["groups"][0]["layouts"][0]["target_layout"]


def test_final_dst_rejects_numeric_duplicate_handles_in_same_drawing(tmp_path: Path):
    drawing = tmp_path / "001-002 第一册.dwg"
    drawing.write_bytes(b"drawing")
    ids = [f"g00000000-0000-0000-0001-{index:012X}" for index in range(1, 8)]
    xml = (
        f'<AcSmDatabase ID="{ids[0]}"><AcSmProp propname="DbVersion">1.1</AcSmProp>'
        f'<AcSmSheetSet ID="{ids[1]}"><AcSmProp propname="Name">重复 Handle</AcSmProp>'
        f'<AcSmSubset ID="{ids[2]}"><AcSmProp propname="Name">001-002 第一册</AcSmProp>'
        f'<AcSmSheet ID="{ids[3]}"><AcSmCustomPropertyBag ID="{ids[4]}"/>'
        f'<AcSmAcDbLayoutReference><AcSmProp propname="AcDbHandle">A</AcSmProp>'
        f'<AcSmProp propname="FileName">{drawing}</AcSmProp><AcSmProp propname="Name">001 第一册 (1)</AcSmProp>'
        f'<AcSmProp propname="Relative_FileName">.\\{drawing.name}</AcSmProp></AcSmAcDbLayoutReference>'
        '<AcSmProp propname="Number">001</AcSmProp><AcSmProp propname="Title">第一册 (1)</AcSmProp></AcSmSheet>'
        f'<AcSmSheet ID="{ids[5]}"><AcSmCustomPropertyBag ID="{ids[6]}"/>'
        f'<AcSmAcDbLayoutReference><AcSmProp propname="AcDbHandle">0A</AcSmProp>'
        f'<AcSmProp propname="FileName">{drawing}</AcSmProp><AcSmProp propname="Name">002 第一册 (2)</AcSmProp>'
        f'<AcSmProp propname="Relative_FileName">.\\{drawing.name}</AcSmProp></AcSmAcDbLayoutReference>'
        '<AcSmProp propname="Number">002</AcSmProp><AcSmProp propname="Title">第一册 (2)</AcSmProp></AcSmSheet>'
        '</AcSmSubset></AcSmSheetSet></AcSmDatabase>'
    ).encode()
    # 通过统一 loader 对齐新契约，保持 VALID（允许 Handle 校验逻辑独立验证）
    xml = load_acsm(xml).to_bytes()
    dst = tmp_path / "重复Handle.dst"
    codec = DstCodec()
    codec.encode_file(xml, dst)
    document = AcsmDocument(codec.decode_file(dst)).project(tmp_path)
    workspace = Workspace("workspace", tmp_path, dst, file_sha256(dst), document)
    plan = build_structural_plan(
        workspace,
        [{"type": "update_subset", "subset_id": document.subsets[0].acsm_id, "title": "改名后的第一册"}],
        SuffixOptions(True, 1),
    )
    # 模拟旧版本已确认的 rename_only 计划，发布边界仍必须独立阻断重复 Handle。
    plan["groups"][0]["cad_operation"] = "rename_only"

    with pytest.raises(PlanningError) as exc_info:
        CadJobRunner(Mock(), codec, Mock(), 30)._write_staged_dst(workspace, plan, {}, tmp_path)

    assert exc_info.value.code == "HANDLE_DUPLICATE"


def test_final_dst_allows_same_numeric_handle_in_different_drawings(tmp_path: Path):
    workspace, _ = _chained_rename_workspace(tmp_path, handles=["A", "0A"])
    commands = [
        {
            "type": "update_subset",
            "subset_id": subset.acsm_id,
            "title": f"改名后的第{index}册",
        }
        for index, subset in enumerate(workspace.document.subsets, start=1)
    ]
    plan = build_structural_plan(workspace, commands, SuffixOptions(True, 1))

    staged = CadJobRunner(Mock(), DstCodec(), Mock(), 30)._write_staged_dst(
        workspace,
        plan,
        {},
        tmp_path,
        commands,
    )

    handles = [
        sheet.layout.handle
        for sheet in AcsmDocument(DstCodec().decode_file(staged)).project(tmp_path).sheets
    ]
    assert handles == ["A", "0A"]


def test_execute_group_rejects_missing_or_unknown_cad_operation(tmp_path: Path):
    source = tmp_path / "source.dwg"
    source.write_bytes(b"source")
    staging, scripts, logs = tmp_path / "staging", tmp_path / "scripts", tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    runner = CadJobRunner(Mock(), Mock(), Mock(), 30)
    for operation in (None, "unsupported"):
        unit = RebuildWorkUnit(
            0,
            {"cad_operation": operation, "source_target_file": str(source), "target_file": str(source), "layouts": []},
            source,
            staging,
            scripts,
            logs,
            30,
        )
        with pytest.raises(PlanningError) as exc_info:
            runner._execute_group("job-1", _planning_workspace(tmp_path, []), CadCapability("2020", None, tmp_path / "plugin.dll"), unit)
        assert exc_info.value.code == "CAD_OPERATION_INVALID"


class _PerDrawingCadExecutor:
    def __init__(self, layouts_by_target: dict[str, list[str]]):
        self.layouts_by_target = layouts_by_target
        self.next_handle = 16
        self.scripts: list[Path] = []

    def run(self, _capability, drawing, script, _timeout):
        self.scripts.append(script)
        if script.name.startswith("rename-"):
            rename_result_path(drawing).write_text(
                json.dumps(
                    {
                        "version": 1,
                        "renamed_count": len(self.layouts_by_target[drawing.name]),
                        "final_layouts": self.layouts_by_target[drawing.name],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)
        lines = []
        for layout in self.layouts_by_target[drawing.name]:
            lines.append(f"{layout}={self.next_handle:X}")
            self.next_handle += 1
        drawing.with_suffix(".dst-handles.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)


class _SecondRebuildFailureExecutor:
    def __init__(self):
        self.calls = 0
        self.failed_script: str | None = None
        self.scripts: list[Path] = []

    def run(self, _capability, drawing, script, _timeout):
        self.calls += 1
        self.scripts.append(script)
        if self.calls == 2:
            self.failed_script = script.name
            raise subprocess.CalledProcessError(1, ["accoreconsole.exe"], "布局输出", "INJECTED_DWG_FAILURE")
        drawing.with_suffix(".dst-handles.txt").write_text("001 第1组=10\n", encoding="utf-8")
        return SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)


class _RenameFailureAfterRebuildExecutor:
    def __init__(self, layouts_by_target: dict[str, list[str]]):
        self.layouts_by_target = layouts_by_target
        self.scripts: list[Path] = []

    def run(self, _capability, drawing, script, _timeout):
        self.scripts.append(script)
        if script.name.startswith("rename-"):
            raise subprocess.CalledProcessError(1, ["accoreconsole.exe"], "", "INJECTED_RENAME_FAILURE")
        drawing.with_suffix(".dst-handles.txt").write_text(
            "\n".join(f"{layout}={index + 16:X}" for index, layout in enumerate(self.layouts_by_target[drawing.name])) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)


class _ParallelRenameFailureExecutor:
    def __init__(self, layouts_by_target: dict[str, list[str]]):
        self.layouts_by_target = layouts_by_target
        self.rebuild_started = Event()
        self.rename_started = Event()
        self.release_rebuild = Event()
        self.scripts: list[Path] = []

    def run(self, _capability, drawing, script, _timeout):
        self.scripts.append(script)
        if script.name.startswith("rebuild-"):
            self.rebuild_started.set()
            assert self.rename_started.wait(2)
            assert self.release_rebuild.wait(2)
            drawing.with_suffix(".dst-handles.txt").write_text(
                "\n".join(f"{layout}={index + 16:X}" for index, layout in enumerate(self.layouts_by_target[drawing.name])) + "\n",
                encoding="utf-8",
            )
            return SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)
        self.rename_started.set()
        assert self.rebuild_started.wait(2)
        self.release_rebuild.set()
        raise subprocess.CalledProcessError(1, ["accoreconsole.exe"], "", "INJECTED_PARALLEL_RENAME_FAILURE")


def test_parallel_mixed_cad_failure_never_publishes_staged_results(tmp_path: Path):
    workspace, old_drawings = _chained_rename_workspace(tmp_path)
    template = tmp_path / "模板.dwt"
    template.write_bytes(b"template")
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "before",
        "title": "新增",
        "initial_sheet_count": 1,
        "base_template_file": str(template),
        "source": {"type": "template_layout", "file": str(template), "layout": "模板布局"},
    }
    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 2))
    layouts_by_target = {
        Path(group["target_file"]).name: [layout["target_layout"] for layout in group["layouts"]]
        for group in plan["groups"]
        if group["cad_operation"] == "rebuild"
    }
    publisher = Mock()
    runner = CadJobRunner(Mock(), DstCodec(), publisher, 30, max_parallel=2)
    executor = _ParallelRenameFailureExecutor(layouts_by_target)
    runner.executor = executor
    plugin = tmp_path / "plugin.dll"
    plugin.write_bytes(b"plugin")
    before = {path: path.read_bytes() for path in [workspace.dst_path, *old_drawings]}

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        runner._execute("job-parallel", "worker", 1, workspace, CadCapability("2020", None, plugin), [command], plan)

    assert exc_info.value.stderr == "INJECTED_PARALLEL_RENAME_FAILURE"
    assert executor.rebuild_started.is_set() and executor.rename_started.is_set()
    publisher.publish.assert_not_called()
    assert {path: path.read_bytes() for path in before} == before


def test_lost_job_lease_never_publishes_staged_results(tmp_path: Path):
    workspace, drawings = _chained_rename_workspace(tmp_path, count=1)
    command = {
        "type": "update_subset",
        "subset_id": workspace.document.subsets[0].acsm_id,
        "title": "改名后的共享册",
    }
    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 1))
    database = Mock()
    database.update_job.return_value = True
    database.heartbeat.return_value = False
    publisher = Mock()
    runner = CadJobRunner(
        database,
        DstCodec(),
        publisher,
        30,
        max_parallel=1,
        heartbeat_interval=0.01,
    )

    def execute(_job, _workspace, _capability, unit):
        time.sleep(0.05)
        target = Path(unit.group["target_file"])
        return RebuildResult(unit.index, target, target, target, {}, 50, tmp_path / "x.log", 1, 1)

    runner._execute_group = execute
    plugin = tmp_path / "plugin.dll"
    plugin.write_bytes(b"plugin")
    before = {path: path.read_bytes() for path in [workspace.dst_path, *drawings]}

    with pytest.raises(PlanningError) as exc_info:
        runner._execute(
            "job-lost-lease",
            "old-worker",
            1,
            workspace,
            CadCapability("2020", None, plugin),
            [command],
            plan,
        )

    assert exc_info.value.code == "CAD_JOB_LEASE_LOST"
    publisher.publish.assert_not_called()
    assert {path: path.read_bytes() for path in before} == before


def test_service_derives_heartbeat_interval_from_worker_lease(tmp_path: Path, monkeypatch):
    service = object.__new__(DstManagerService)
    service.database = Mock()
    service.database.claim_next_job.return_value = {
        "id": "job",
        "workspace_id": "workspace",
        "cad_version": "2020",
    }
    service.settings = Settings(data_dir=tmp_path / "data", worker_lease_seconds=60)
    service.codec = Mock()
    service.publisher = Mock()
    service.get_workspace = Mock(return_value=object())
    service._capability = Mock(return_value=object())
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, *_args, **kwargs):
            captured.update(kwargs)

        def run(self, *_args):
            return {"status": "FAILED"}

    monkeypatch.setattr(service_module, "CadJobRunner", FakeRunner)

    service.run_next_job()

    assert captured["heartbeat_interval"] == 20


def test_mixed_cad_failure_does_not_publish_staged_results(tmp_path: Path):
    workspace, old_drawings = _chained_rename_workspace(tmp_path)
    template = tmp_path / "模板.dwt"
    template.write_bytes(b"template")
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "before",
        "title": "新增",
        "initial_sheet_count": 1,
        "base_template_file": str(template),
        "source": {"type": "template_layout", "file": str(template), "layout": "模板布局"},
    }
    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 2))
    assert {group["cad_operation"] for group in plan["groups"]} == {"rename_only", "rebuild"}
    layouts_by_target = {
        Path(group["target_file"]).name: [layout["target_layout"] for layout in group["layouts"]]
        for group in plan["groups"]
        if group["cad_operation"] == "rebuild"
    }
    publisher = Mock()
    runner = CadJobRunner(Mock(), DstCodec(), publisher, 30, max_parallel=1)
    executor = _RenameFailureAfterRebuildExecutor(layouts_by_target)
    runner.executor = executor
    plugin = tmp_path / "plugin.dll"
    plugin.write_bytes(b"plugin")
    before = {path: path.read_bytes() for path in [workspace.dst_path, *old_drawings]}

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        runner._execute("job-mixed", "worker", 1, workspace, CadCapability("2020", None, plugin), [command], plan)

    assert exc_info.value.stderr == "INJECTED_RENAME_FAILURE"
    assert any(script.name.startswith("rebuild-") for script in executor.scripts)
    assert any(script.name.startswith("rename-") for script in executor.scripts)
    publisher.publish.assert_not_called()
    assert {path: path.read_bytes() for path in before} == before


def test_second_group_failure_is_attributable_to_the_single_rebuild_script(tmp_path: Path):
    source = tmp_path / "来源.dwg"
    source.write_bytes(b"source")
    staging = tmp_path / "staging"
    scripts = tmp_path / "scripts"
    logs = tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    units = [
        RebuildWorkUnit(
            index,
                {
                    "cad_operation": "rebuild",
                    "source_target_file": str(source),
                "target_file": str(tmp_path / f"目标-{index}.dwg"),
                "layouts": [{"sheet_id": f"sheet-{index}", "source_file": str(source), "source_layout": "来源", "target_layout": f"00{index + 1} 第{index + 1}组"}],
            },
            source,
            staging,
            scripts,
            logs,
            30,
        )
        for index in range(2)
    ]
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30, max_parallel=1)
    executor = _SecondRebuildFailureExecutor()
    runner.executor = executor

    with pytest.raises(subprocess.CalledProcessError):
        runner._run_groups(
            "job-1",
            "worker",
            _planning_workspace(tmp_path, []),
            CadCapability("2020", None, tmp_path / "plugin.dll"),
            units,
        )

    assert executor.failed_script == "rebuild-001.scr"
    assert [script.name for script in executor.scripts] == ["rebuild-000.scr", "rebuild-001.scr"]
    assert not list(scripts.glob("handles-*.scr"))
    log = (logs / "group-001.log").read_text(encoding="utf-8")
    assert "Core Console：重建布局并读取布局 Handle（退出码 1）stdout" in log
    assert "布局输出" in log and "INJECTED_DWG_FAILURE" in log and "CalledProcessError" in log
    assert any(
        call.args[1] == tmp_path / "目标-1.dwg" and call.kwargs["status"] == "FAILED"
        for call in database.upsert_job_file.call_args_list
    )


def test_core_console_failure_is_classified_as_cad_process_failed(tmp_path: Path):
    console = tmp_path / "accoreconsole.exe"
    plugin = tmp_path / "plugin.dll"
    console.write_bytes(b"console")
    plugin.write_bytes(b"plugin")
    workspace = _planning_workspace(tmp_path, [])
    database = Mock()
    database.get_job.return_value = {"status": "FAILED", "error_code": "CAD_PROCESS_FAILED"}
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    runner._execute = Mock(
        side_effect=subprocess.CalledProcessError(1, [str(console)], "布局输出", "INJECTED_DWG_FAILURE")
    )
    job = {
        "id": "job-1",
        "payload": {
            "base_revision_id": "revision",
            "commands": [],
            "plan": {"execution_intent": {"groups": [], "expected_file_hashes": {}, "source_baselines": [], "cad_validation_deferred": True}},
        },
    }

    result = runner.run(job, workspace, CadCapability("2020", console, plugin))

    assert result["error_code"] == "CAD_PROCESS_FAILED"
    assert any(
        call.args[3] == "CAD_PROCESS_FAILED"
        for call in database.update_job.call_args_list
        if len(call.args) >= 4
    )
    failure_log = tmp_path / ".dst-manager" / "jobs" / "job-1" / "attempt-001" / "logs" / "failure.log"
    assert "INJECTED_DWG_FAILURE" in failure_log.read_text(encoding="utf-8")


def test_create_group_uses_template_snapshot_without_source_target(tmp_path: Path):
    template = tmp_path / "标准.dwt"
    template.write_bytes(b"template-base")
    staging = tmp_path / "staging"
    scripts = tmp_path / "scripts"
    logs = tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    target = tmp_path / "001 新建子集.dwg"
    unit = RebuildWorkUnit(
        0,
        {
            "operation": "create",
            "source_target_file": None,
            "target_file": str(target),
            "layouts": [
                {
                    "sheet_id": "sheet-new",
                    "source_file": str(template),
                    "source_layout": "A3",
                    "target_layout": "001 新建子集",
                },
            ],
        },
        template,
        staging,
        scripts,
        logs,
        30,
    )
    database = Mock()
    runner = CadJobRunner(database, Mock(), Mock(), 30)
    executor = _SuccessfulCadExecutor("001 新建子集=AB\n")
    runner.executor = executor
    workspace = _planning_workspace(tmp_path, [])

    result = runner._rebuild_group("job-1", workspace, CadCapability("2020", None, tmp_path / "plugin.dll"), unit)

    assert result.source_target is None
    assert result.target == target
    assert result.staged.read_bytes() == b"template-base"
    assert result.bindings == {"sheet-new": {"file": str(target), "layout": "001 新建子集", "handle": "AB"}}
    assert executor.calls == 1
    assert [script.name for script in executor.scripts] == ["rebuild-000.scr"]
    assert not (scripts / "handles-000.scr").exists()
    assert database.upsert_job_file.call_args_list[0].kwargs["before_hash"] is None


def test_missing_template_layout_cad_failure_never_returns_binding(tmp_path: Path):
    template = tmp_path / "标准.dwt"
    template.write_bytes(b"template-base")
    staging = tmp_path / "staging"
    scripts = tmp_path / "scripts"
    logs = tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    target = tmp_path / "001 新建子集.dwg"
    unit = RebuildWorkUnit(
        0,
        {
            "operation": "create",
            "source_target_file": None,
            "target_file": str(target),
            "layouts": [
                {
                    "sheet_id": "sheet-new",
                    "source_file": str(template),
                    "source_layout": "不存在的模板布局",
                    "target_layout": "001 新建子集",
                },
            ],
        },
        template,
        staging,
        scripts,
        logs,
        30,
    )
    runner = CadJobRunner(Mock(), Mock(), Mock(), 30)
    runner.executor = Mock()
    runner.executor.run.side_effect = subprocess.CalledProcessError(
        1,
        ["accoreconsole.exe"],
        "",
        "找不到模板布局",
    )

    with pytest.raises(subprocess.CalledProcessError):
        runner._rebuild_group(
            "job-1",
            _planning_workspace(tmp_path, []),
            CadCapability("2020", None, tmp_path / "plugin.dll"),
            unit,
        )

    assert not target.exists()
    assert "找不到模板布局" in (logs / "group-000.log").read_text(encoding="utf-8")


def test_create_group_full_flow_publishes_new_dwg_without_deleting_existing(tiny_workspace):
    dst, sheet_id = tiny_workspace
    codec = DstCodec()
    acsm = AcsmDocument(codec.decode_file(dst))
    existing = dst.parent / "001 平面.dwg"
    (dst.parent / "A.dwg").replace(existing)
    acsm.apply_metadata_commands(
        [{"type": "update_subset", "subset_id": acsm.project(dst.parent).subsets[0].acsm_id, "name": "001 平面"}],
    )
    acsm.apply_layout_bindings(
        {sheet_id: {"file": str(existing), "layout": "001 平面", "handle": "AB"}},
        dst.parent,
    )
    codec.encode_file(acsm.to_bytes(), dst)
    document = AcsmDocument(codec.decode_file(dst)).project(dst.parent)
    workspace = Workspace("workspace", dst.parent, dst, file_sha256(dst), document)
    existing_hash = file_sha256(existing)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 2,
        "base_template_file": str(existing),
        "source": {"type": "template_layout", "file": str(existing), "layout": "001 平面"},
    }
    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 2))
    assert [group["operation"] for group in plan["groups"]] == ["create"]
    group = plan["groups"][0]
    handle_text = "\n".join(
        f"{layout['target_layout']}={index + 16:X}"
        for index, layout in enumerate(group["layouts"])
    ) + "\n"
    database = Mock()
    database.get_job.return_value = {"id": "job-create", "status": "SUCCEEDED"}
    publisher = RecoverablePublisher()
    published_baselines = None
    published_before_commit = None
    original_publish = publisher.publish

    def capture_publish_baselines(*args, **kwargs):
        nonlocal published_baselines, published_before_commit
        published_baselines = kwargs["expected_baselines"]
        published_before_commit = kwargs["before_commit"]
        return original_publish(*args, **kwargs)

    publisher.publish = capture_publish_baselines
    runner = CadJobRunner(database, codec, publisher, 30, max_parallel=1)
    executor = _SuccessfulCadExecutor(handle_text)
    runner.executor = executor
    plugin = dst.parent / "plugin.dll"
    plugin.write_bytes(b"plugin")

    result = runner._execute(
        "job-create",
        "worker",
        1,
        workspace,
        CadCapability("2020", None, plugin),
        [command],
        plan,
    )

    target = Path(group["target_file"])
    assert result["status"] == "SUCCEEDED"
    assert target.is_file()
    assert file_sha256(existing) == existing_hash
    reopened = AcsmDocument(codec.decode_file(dst)).project(dst.parent)
    created = next(subset for subset in reopened.subsets if "新建子集" in subset.name)
    assert len(created.sheets) == 2
    assert {sheet.layout.resolved_path for sheet in created.sheets} == {target}
    assert all(sheet.layout.handle != "0" for sheet in created.sheets)
    assert executor.calls == 1
    assert [script.name for script in executor.scripts] == ["rebuild-000.scr"]
    assert published_baselines is not None
    assert callable(published_before_commit)
    assert all(
        baseline is None or isinstance(baseline, ExpectedFileBaseline)
        for baseline in published_baselines.values()
    )
    assert all(
        call.kwargs["worker_id"] == "worker" and call.kwargs["attempt"] == 1
        for call in database.upsert_job_file.call_args_list
    )
    assert database.finalize_committed_job.call_args.kwargs["worker_id"] == "worker"
    assert database.finalize_committed_job.call_args.kwargs["attempt"] == 1
    assert (dst.parent / ".dst-manager" / "revisions" / "job-create" / "manifest.json").is_file()


def test_front_insert_publishes_complete_chained_dwg_renames(tmp_path: Path):
    workspace, old_drawings = _chained_rename_workspace(tmp_path)
    template = tmp_path / "模板.dwt"
    template.write_bytes(b"template")
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "before",
        "title": "共享",
        "initial_sheet_count": 1,
        "base_template_file": str(template),
        "source": {"type": "template_layout", "file": str(template), "layout": "模板布局"},
    }
    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 2))
    assert [group["operation"] for group in plan["groups"]] == ["create", "rebuild", "rebuild"]
    targets = [Path(group["target_file"]) for group in plan["groups"]]
    assert targets[:2] == old_drawings
    layouts_by_target = {
        Path(group["target_file"]).name: [layout["target_layout"] for layout in group["layouts"]]
        for group in plan["groups"]
    }
    database = Mock()
    database.get_job.return_value = {"id": "job-chain", "status": "SUCCEEDED"}
    runner = CadJobRunner(database, DstCodec(), RecoverablePublisher(), 30, max_parallel=1)
    executor = _PerDrawingCadExecutor(layouts_by_target)
    runner.executor = executor
    plugin = tmp_path / "plugin.dll"
    plugin.write_bytes(b"plugin")

    result = runner._execute(
        "job-chain",
        "worker",
        1,
        workspace,
        CadCapability("2020", None, plugin),
        [command],
        plan,
    )

    assert result["status"] == "SUCCEEDED"
    assert [target.read_bytes() for target in targets] == [b"template", b"old-1", b"old-2"]
    reopened = AcsmDocument(DstCodec().decode_file(workspace.dst_path)).project(tmp_path)
    assert [sheet.layout.resolved_path for sheet in reopened.sheets] == targets
    assert all(sheet.layout.handle != "0" for sheet in reopened.sheets)
    assert [script.name for script in executor.scripts] == [
        f"{'rename' if group['cad_operation'] == 'rename_only' else 'rebuild'}-{index:03d}.scr"
        for index, group in enumerate(plan["groups"])
    ]


def test_middle_insert_publishes_overlapping_source_and_target_paths(tmp_path: Path):
    workspace, old_drawings = _chained_rename_workspace(tmp_path, count=3)
    template = tmp_path / "中部模板.dwt"
    template.write_bytes(b"middle-template")
    command = {
        "type": "insert_subset",
        "ordinal": 2,
        "placement": "before",
        "title": "共享",
        "initial_sheet_count": 1,
        "base_template_file": str(template),
        "source": {"type": "template_layout", "file": str(template), "layout": "模板布局"},
    }
    plan = build_structural_plan(workspace, [command], SuffixOptions(True, 2))
    changed_targets = [Path(group["target_file"]) for group in plan["groups"]]
    assert changed_targets == [old_drawings[1], old_drawings[2], tmp_path / "004 共享.dwg"]
    layouts_by_target = {
        Path(group["target_file"]).name: [layout["target_layout"] for layout in group["layouts"]]
        for group in plan["groups"]
    }
    database = Mock()
    database.get_job.return_value = {"id": "job-middle-chain", "status": "SUCCEEDED"}
    runner = CadJobRunner(database, DstCodec(), RecoverablePublisher(), 30, max_parallel=1)
    executor = _PerDrawingCadExecutor(layouts_by_target)
    runner.executor = executor
    plugin = tmp_path / "plugin.dll"
    plugin.write_bytes(b"plugin")

    result = runner._execute(
        "job-middle-chain",
        "worker",
        1,
        workspace,
        CadCapability("2020", None, plugin),
        [command],
        plan,
    )

    final_drawings = [*old_drawings, tmp_path / "004 共享.dwg"]
    assert result["status"] == "SUCCEEDED"
    assert [path.read_bytes() for path in final_drawings] == [
        b"old-1",
        b"middle-template",
        b"old-2",
        b"old-3",
    ]
    reopened = AcsmDocument(DstCodec().decode_file(workspace.dst_path)).project(tmp_path)
    assert [sheet.layout.resolved_path for sheet in reopened.sheets] == final_drawings
    assert all(sheet.layout.handle != "0" for sheet in reopened.sheets)
    assert [script.name for script in executor.scripts] == [
        f"{'rename' if group['cad_operation'] == 'rename_only' else 'rebuild'}-{index:03d}.scr"
        for index, group in enumerate(plan["groups"])
    ]


def test_zero_handle_is_rejected_before_binding(tmp_path: Path):
    source = tmp_path / "来源.dwg"
    source.write_bytes(b"source")
    staging = tmp_path / "staging"
    scripts = tmp_path / "scripts"
    logs = tmp_path / "logs"
    for directory in (staging, scripts, logs):
        directory.mkdir()
    unit = RebuildWorkUnit(
        0,
        {
            "operation": "rebuild",
            "source_target_file": str(source),
            "target_file": str(source),
            "layouts": [
                {
                    "sheet_id": "sheet-1",
                    "source_file": str(source),
                    "source_layout": "旧布局",
                    "target_layout": "001 新布局",
                },
            ],
        },
        source,
        staging,
        scripts,
        logs,
        30,
    )
    runner = CadJobRunner(Mock(), Mock(), Mock(), 30)
    executor = _SuccessfulCadExecutor("001 新布局=0\n")
    runner.executor = executor

    with pytest.raises(ValueError, match="HANDLE_OUTPUT_INVALID"):
        runner._rebuild_group(
            "job-1",
            _planning_workspace(tmp_path, []),
            CadCapability("2020", None, tmp_path / "plugin.dll"),
            unit,
        )

    assert executor.calls == 1
    assert [script.name for script in executor.scripts] == ["rebuild-000.scr"]


def test_final_dst_applies_derived_structure_then_real_bindings(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    workspace = Workspace("workspace", dst.parent, dst, "revision", document)
    template = dst.parent / "A.dwg"
    plan = build_structural_plan(
        workspace,
        [
            {
                "type": "insert_sheet",
                "target_subset_id": document.subsets[0].acsm_id,
                "ordinal": 1,
                "placement": "after",
                "count": 1,
                "source": {"type": "template_layout", "file": str(template), "layout": "001 平面"},
            },
        ],
        SuffixOptions(True, 2),
    )
    group = plan["groups"][0]
    bindings = {
        layout["sheet_id"]: {
            "file": group["target_file"],
            "layout": layout["target_layout"],
            "handle": f"C{index + 1}",
        }
        for index, layout in enumerate(group["layouts"])
    }
    runner = CadJobRunner(Mock(), DstCodec(), Mock(), 30)

    staged = runner._write_staged_dst(workspace, plan, bindings, tmp_path)

    final = AcsmDocument(DstCodec().decode_file(staged))
    projected = final.project(dst.parent)
    assert [sheet.number for sheet in projected.sheets] == ["001", "002"]
    assert [sheet.title for sheet in projected.sheets] == ["分组 (1)", "分组 (2)"]
    assert [sheet.layout.handle for sheet in projected.sheets] == ["C1", "C2"]
    assert {issue.code for issue in final.validate() if issue.severity == "error"} == set()


def test_final_dst_keeps_metadata_updates_from_structural_batch(tiny_workspace, tmp_path: Path):
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    workspace = Workspace("workspace", dst.parent, dst, "revision", document)
    commands = [
        {"type": "update_sheet_set", "custom_properties": {"项目号": "P-999"}},
        {"type": "update_sheet", "sheet_id": sheet_id, "custom_properties": {"比例": "1:500"}},
        {
            "type": "insert_sheet",
            "target_subset_id": document.subsets[0].acsm_id,
            "ordinal": 1,
            "placement": "after",
            "count": 1,
            "source": {"type": "template_layout", "file": str(dst.parent / "A.dwg"), "layout": "001 平面"},
        },
    ]
    plan = build_structural_plan(workspace, commands, SuffixOptions(True, 2))
    group = plan["groups"][0]
    bindings = {
        layout["sheet_id"]: {
            "file": group["target_file"],
            "layout": layout["target_layout"],
            "handle": f"D{index + 1}",
        }
        for index, layout in enumerate(group["layouts"])
    }
    runner = CadJobRunner(Mock(), DstCodec(), Mock(), 30)

    staged = runner._write_staged_dst(workspace, plan, bindings, tmp_path, commands)

    projected = AcsmDocument(DstCodec().decode_file(staged)).project(dst.parent)
    assert projected.custom_properties["项目号"] == "P-999"
    assert projected.sheets[0].custom_properties["比例"] == "1:500"


@pytest.mark.parametrize(
    "bindings",
    [
        {"unexpected": {"file": "A.dwg", "layout": "001 平面", "handle": "AB"}},
        {"sheet-1": {"file": "A.dwg", "layout": "001 平面", "handle": "0"}},
    ],
)
def test_final_dst_rejects_non_bijective_or_zero_handle_bindings(tiny_workspace, tmp_path: Path, bindings):
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst)).project(dst.parent)
    workspace = Workspace("workspace", dst.parent, dst, "revision", document)
    plan = build_structural_plan(
        workspace,
        [{"type": "update_subset", "subset_id": document.subsets[0].acsm_id, "title": "新标题"}],
        SuffixOptions(True, 1),
    )
    runner = CadJobRunner(Mock(), DstCodec(), Mock(), 30)

    with pytest.raises(PlanningError) as exc_info:
        runner._write_staged_dst(workspace, plan, bindings, tmp_path)

    assert exc_info.value.code in {"HANDLE_LAYOUT_MISMATCH", "HANDLE_OUTPUT_INVALID"}


# ---------------------------------------------------------------- PLAN-DM-009 Task 3：契约工厂与可修复加载

def test_new_sheet_factory_matches_golden_contract(tiny_workspace):
    """`_make_sheet_node` 生成的新 Sheet 必须含完整 bag/layout/sheet views/Number/Title
    子树，且每类固定对象属性与每个已知 AcSmProp 的 vt 与黄金样本一致。"""
    dst, _ = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    sheet = document._make_sheet_node(
        "g99999999-9999-9999-9999-999999999001",
        "001",
        "新图标题",
        r"C:\test\new.dwg",
        r".\new.dwg",
        "001 新图布局",
        "0",
    )
    assert dict(sheet.attrib) == {
        "ID": "g99999999-9999-9999-9999-999999999001",
        "clsid": "g16A07941-BC15-4D48-A880-9D5A211D5065",
    }
    children = {etree.QName(child).localname: child for child in sheet}
    bag = children["AcSmCustomPropertyBag"]
    assert dict(bag.attrib) == {
        "ID": bag.get("ID"),
        "clsid": "g4D103908-8C86-4D95-BBF4-68B9A7B00731",
        "propname": "CustomPropertyBag",
        "vt": "13",
    }
    values = [child for child in bag if etree.QName(child).localname == "AcSmCustomPropertyValue"]
    for value in values:
        assert value.get("clsid") == "g8D22A2A4-1777-4D78-84CC-69EF741FE954"
        assert value.get("vt") == "13"
        flags = [c for c in value if c.get("propname") == "Flags"]
        assert flags and flags[0].get("vt") == "3"
    layout = children["AcSmAcDbLayoutReference"]
    assert dict(layout.attrib) == {
        "ID": layout.get("ID"),
        "clsid": "g94910E94-4FCA-427C-B6ED-2EC9E1C900C7",
        "propname": "Layout",
        "vt": "13",
    }
    for field in ("AcDbHandle", "FileName", "Name", "Relative_FileName"):
        prop = next(c for c in layout if c.get("propname") == field)
        assert prop.get("vt") == "8"
    props_by_name = {child.get("propname"): child for child in sheet if etree.QName(child).localname == "AcSmProp"}
    assert props_by_name["Number"].get("vt") == "8"
    assert props_by_name["Title"].get("vt") == "8"
    views = children["AcSmSheetViews"]
    assert dict(views.attrib) == {
        "ID": views.get("ID"),
        "clsid": "gF40F931B-64BC-4B90-9FC8-A11A77D6815B",
        "propname": "SheetViews",
        "vt": "13",
    }


def test_insert_sheet_and_subset_produce_complete_sheetviews(tiny_workspace):
    """insert_sheet / insert_subset 生成的新 Sheet 在 DOM 中均含 AcSmSheetViews，
    并保留原有兄弟节点、未知节点和节点顺序。"""
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]
    document.apply_structural_commands(
        [
            {
                "type": "insert_sheet",
                "target_subset_id": subset.get("ID"),
                "count": 1,
                "number": "099",
                "title": "插入的新图",
                "source": {"type": "existing_snapshot", "file": r"C:\x.dwg", "layout": "099"},
                "position": len([c for c in subset if etree.QName(c).localname == "AcSmSheet"]),
            },
            {
                "type": "insert_subset",
                "initial_sheet_count": 2,
                "title": "新子集",
                "source": {"type": "existing_snapshot", "file": r"C:\x.dwg", "layout": "099"},
            },
        ],
        "base",
    )
    sheets = document.root.xpath("//*[local-name()='AcSmSheet']")
    assert len(sheets) == 4
    for sheet in sheets:
        child_names = [etree.QName(child).localname for child in sheet]
        assert "AcSmSheetViews" in child_names
        views = [c for c in sheet if etree.QName(c).localname == "AcSmSheetViews"]
        assert views[0].get("propname") == "SheetViews"
        assert views[0].get("vt") == "13"
    # 原有 sheet 的 Unknown 节点保留，且原有节点相对顺序不变
    original = document.root.xpath("//*[@ID=$sheet_id and local-name()='AcSmSheet']", sheet_id=sheet_id)[0]
    unknown = original.xpath("./*[local-name()='Unknown']")[0]
    assert unknown.get("keep") == "yes"
    original_order = ["AcSmCustomPropertyBag", "AcSmAcDbLayoutReference", "AcSmProp", "AcSmProp", "Unknown"]
    tags_in_document = [etree.QName(child).localname for child in original]
    preserved = [tag for tag in tags_in_document if tag in {"AcSmCustomPropertyBag", "AcSmAcDbLayoutReference", "AcSmProp", "Unknown"}]
    assert preserved == original_order
    # round-trip 后结构一致；新图纸的 Handle 占位是 CAD 前合法状态，无结构/契约问题
    roundtrip = AcsmDocument(document.to_bytes())
    assert len(roundtrip.root.xpath("//*[local-name()='AcSmSheet']")) == 4
    issue_codes = {issue.code for issue in roundtrip.validate()}
    assert issue_codes <= {"LAYOUT_HANDLE_PLACEHOLDER"}


def test_apply_derived_document_new_sheet_has_sheetviews(tiny_workspace):
    """apply_derived_document 派生出的新图纸也具备完整固定对象属性和 AcSmSheetViews。"""
    dst, sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]
    derived = DerivedDocument(
        [
            DerivedSubset(
                subset.get("ID"),
                "分组",
                "001-002",
                "001-002 分组",
                [
                    Sheet(
                        sheet_id,
                        "001",
                        "原始图纸",
                        LayoutReference(r"C:\old\A.dwg", r".\A.dwg", "001 平面", "AB"),
                    ),
                    Sheet(
                        "g99999999-9999-9999-9999-999999999003",
                        "002",
                        "派生图纸A",
                        LayoutReference(r"C:\test\A.dwg", r".\A.dwg", "002 派生图纸A", "0"),
                    ),
                ],
            )
        ],
        [subset.get("ID")],
    )
    document.apply_derived_document(derived)
    roundtrip = AcsmDocument(document.to_bytes())
    sheets = roundtrip.root.xpath("//*[local-name()='AcSmSheet']")
    assert len(sheets) == 2
    new_sheet = roundtrip.root.xpath(
        "//*[@ID='g99999999-9999-9999-9999-999999999003' and local-name()='AcSmSheet']"
    )[0]
    views = [c for c in new_sheet if etree.QName(c).localname == "AcSmSheetViews"]
    assert len(views) == 1
    assert views[0].get("clsid") == "gF40F931B-64BC-4B90-9FC8-A11A77D6815B"
    # 原有 sheet 的 Unknown 节点仍在
    original = roundtrip.root.xpath("//*[@ID=$sheet_id and local-name()='AcSmSheet']", sheet_id=sheet_id)[0]
    assert original.xpath("./*[local-name()='Unknown']")[0].get("keep") == "yes"


def test_fail_sample_load_repairs_in_memory_and_roundtrips(tmp_path: Path):
    """失败样本加载后投影可见所有可推断 Sheet，validate() 只保留不可修复问题；
    原始 `sheetset-fail.xml` 字节和 mtime 不变。"""
    source = Path(__file__).resolve().parents[2] / "docs" / "shared" / "research" / "project1-dst-xml" / "sheetset-fail.xml"
    fail_copy = tmp_path / "sheetset-fail.xml"
    fail_copy.write_bytes(source.read_bytes())
    before_bytes = fail_copy.read_bytes()
    before_mtime = fail_copy.stat().st_mtime

    document = AcsmDocument(fail_copy.read_bytes())
    assert document.repair_report.status == "REPAIRED"
    assert document.repair_report.actions
    proj = document.project(tmp_path)
    assert len(proj.sheets) == 24
    assert [issue.code for issue in document.validate()] == []

    assert fail_copy.read_bytes() == before_bytes
    assert fail_copy.stat().st_mtime == before_mtime


# ---------------------------------------------------------------- PLAN-DM-009 Task 5：修复事务与 CAD 边界

FAIL_SRC = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "shared"
    / "research"
    / "project1-dst-xml"
    / "sheetset-fail.xml"
)


def _fail_dst(tmp_path: Path) -> Path:
    dst = tmp_path / "repair-project.dst"
    DstCodec().encode_file(FAIL_SRC.read_bytes(), dst)
    return dst


def _repair_preview_digest(service, workspace) -> str:
    preview = service.preview_repair(workspace.id, workspace.revision_id)
    assert preview["status"] == "REPAIRED"
    return preview["preview_digest"]


def test_delete_subset_preview_removes_complete_subtree_and_main_dwg(tiny_workspace, tmp_path: Path):
    dst, sheet_id = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    subset = workspace.document.subsets[0]
    command = {
        "type": "delete_subset",
        "subset_id": subset.acsm_id,
        "confirm_delete_all_sheets": True,
        "confirm_delete_main_dwg": True,
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command])

    assert preview["executable"] is True, preview["diagnostics"]
    assert preview["execution_intent"]["derived_document"]["subsets"] == []
    assert preview["execution_intent"]["deleted_subsets"] == [
        {"subset_id": subset.acsm_id, "target_file": str((tmp_path / "A.dwg").resolve())},
    ]
    assert preview["execution_intent"]["path_graph"]["delete_targets"] == [
        str((tmp_path / "A.dwg").resolve()),
    ]
    before = preview["semantic_diff"]["structure"]["before"][0]
    assert [item["id"] for item in before["sheets"]] == [sheet_id]
    assert preview["semantic_diff"]["structure"]["after"] == []
    assert preview["semantic_diff"]["dwgs"][0]["action"] == "delete"


def test_delete_subset_preview_blocks_external_xml_reference_to_owned_id(tiny_workspace, tmp_path: Path):
    dst, sheet_id = tiny_workspace
    codec = DstCodec()
    xml = codec.decode_file(dst)
    xml = xml.replace(b"</AcSmSheetSet>", f'<UnknownReference ref="{sheet_id}"/></AcSmSheetSet>'.encode())
    codec.encode_file(xml, dst)
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "delete_subset",
        "subset_id": workspace.document.subsets[0].acsm_id,
        "confirm_delete_all_sheets": True,
        "confirm_delete_main_dwg": True,
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command])

    assert preview["executable"] is False
    assert any(item["code"] == "UNKNOWN_REFERENCE_BLOCKED" for item in preview["diagnostics"])


def test_delete_subset_publishes_dst_and_main_dwg_delete_without_core_console(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    main_dwg = tmp_path / "A.dwg"
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "delete_subset",
        "subset_id": workspace.document.subsets[0].acsm_id,
        "confirm_delete_all_sheets": True,
        "confirm_delete_main_dwg": True,
    }
    preview = service.preview_changes(workspace.id, workspace.revision_id, [command])

    queued = service.execute_changes(
        workspace.id,
        workspace.revision_id,
        [command],
        preview_digest=preview["preview_digest"],
    )
    completed = service.run_next_job()

    assert queued["status"] == "QUEUED"
    assert completed["status"] == "SUCCEEDED"
    assert not main_dwg.exists()
    reopened = service.get_workspace(workspace.id)
    assert reopened.document.subsets == []
    manifest = Path(completed["payload"]["plan"]["execution_intent"]["path_graph"]["delete_targets"][0])
    assert manifest == main_dwg.resolve()
    revision = service.database.list_revisions(workspace.id)[0]
    assert (Path(revision["revision_dir"]) / "before" / "A.dwg").is_file()


def test_delete_subset_blocks_when_surviving_sheet_references_same_main_dwg(tmp_path: Path):
    shared = tmp_path / "001 立面.dwg"
    shared.write_bytes(b"dwg")
    first_sheet = Sheet("sheet-1", "001", "平面", LayoutReference(str(shared), ".\\001 立面.dwg", "001 平面", "A", shared))
    second_sheet = Sheet("sheet-2", "002", "立面", LayoutReference(str(shared), ".\\001 立面.dwg", "002 立面", "B", shared))
    document = SheetSetDocument(
        "database",
        "测试集",
        [Subset("subset-1", "1 平面", 0, [first_sheet]), Subset("subset-2", "2 立面", 1, [second_sheet])],
    )
    workspace = Workspace("workspace", tmp_path, tmp_path / "test.dst", "revision", document)

    with pytest.raises(PlanningError) as exc_info:
        build_structural_plan(
            workspace,
            [{
                "type": "delete_subset",
                "subset_id": "subset-1",
                "confirm_delete_all_sheets": True,
                "confirm_delete_main_dwg": True,
            }],
        )

    assert exc_info.value.code == "DWG_DELETE_STILL_REFERENCED"


def test_delete_subset_preview_blocks_main_dwg_outside_workspace(tmp_path: Path):
    outside = tmp_path.parent / "outside-delete-target.dwg"
    outside.write_bytes(b"dwg")
    sheet = Sheet("sheet-1", "001", "平面", LayoutReference(str(outside), str(outside), "001 平面", "A", outside))
    document = SheetSetDocument("database", "测试集", [Subset("subset-1", "1 平面", 0, [sheet])])
    workspace = Workspace("workspace", tmp_path, tmp_path / "test.dst", "revision", document)

    with pytest.raises(PlanningError) as exc_info:
        build_structural_plan(
            workspace,
            [{
                "type": "delete_subset",
                "subset_id": "subset-1",
                "confirm_delete_all_sheets": True,
                "confirm_delete_main_dwg": True,
            }],
        )

    assert exc_info.value.code == "DWG_DELETE_OUTSIDE_WORKSPACE"


def test_delete_subset_preview_blocks_multiple_main_dwgs(tmp_path: Path):
    first = tmp_path / "A.dwg"
    second = tmp_path / "B.dwg"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    sheets = [
        Sheet("sheet-1", "001", "平面", LayoutReference(str(first), str(first), "001 平面", "A", first)),
        Sheet("sheet-2", "002", "立面", LayoutReference(str(second), str(second), "002 立面", "B", second)),
    ]
    document = SheetSetDocument("database", "测试集", [Subset("subset-1", "1-2", 0, sheets)])
    workspace = Workspace("workspace", tmp_path, tmp_path / "test.dst", "revision", document)

    with pytest.raises(PlanningError) as exc_info:
        build_structural_plan(
            workspace,
            [{
                "type": "delete_subset",
                "subset_id": "subset-1",
                "confirm_delete_all_sheets": True,
                "confirm_delete_main_dwg": True,
            }],
        )

    assert exc_info.value.code == "SUBSET_MULTIPLE_MAIN_DWGS"


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (PublishRolledBackError("INJECTED_REPAIR_ROLLBACK"), "ROLLED_BACK"),
        (PublishRecoveryError("INJECTED_REPAIR_RECOVERY"), "NEEDS_REVIEW"),
        (RuntimeError("INJECTED_REPAIR_FAILURE"), "FAILED"),
    ],
)
def test_repair_publish_failures_use_safe_terminal_and_keep_official_dst(
    tmp_path: Path,
    monkeypatch,
    failure: Exception,
    expected_status: str,
):
    """修复发布中途异常时，正式 DST 保持发布前字节，任务进入安全终态并释放写锁。"""
    dst = _fail_dst(tmp_path)
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    base_hash = file_sha256(dst)
    base_bytes = dst.read_bytes()
    digest = _repair_preview_digest(service, workspace)
    monkeypatch.setattr(service.publisher, "publish", Mock(side_effect=failure))

    job = service.execute_repair(workspace.id, workspace.revision_id, digest)

    assert job["status"] == expected_status
    assert dst.read_bytes() == base_bytes
    assert file_sha256(dst) == base_hash
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_repair_staging_encode_failure_is_traceable_and_keeps_file(tmp_path: Path, monkeypatch):
    """暂存编码失败：任务 FAILED、正式 DST 不变，且无修订 manifest 落盘。"""
    dst = _fail_dst(tmp_path)
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    base_hash = file_sha256(dst)
    base_bytes = dst.read_bytes()
    digest = _repair_preview_digest(service, workspace)

    def fail_encode(data: bytes, target):
        raise OSError("INJECTED_ENCODE_FAILURE")

    monkeypatch.setattr(service.codec, "encode_file", Mock(side_effect=fail_encode))
    job = service.execute_repair(workspace.id, workspace.revision_id, digest)

    assert job["status"] == "FAILED"
    assert job.get("error_code") == "OSERROR"
    assert dst.read_bytes() == base_bytes
    assert file_sha256(dst) == base_hash
    revisions = service.database.list_revisions(workspace.id)
    assert not any(item["id"].startswith("repair-") for item in revisions)


def test_repair_startup_recovery_restores_official_dst(tmp_path: Path, tiny_workspace):
    """修复发布在 PUBLISHING 阶段中断后重启，正式 DST 恢复为发布前字节且任务 ROLLED_BACK。"""
    dst, _ = tiny_workspace
    settings = Settings(data_dir=tmp_path / "data")
    service = DstManagerService(settings)
    workspace = service.open_workspace(dst)
    operation_id = "repair-crash"
    service.database.create_job(
        operation_id,
        workspace.id,
        "repair_revision",
        JobStatus.PUBLISHING,
        {"base_revision_id": workspace.revision_id, "kind": "repair"},
    )
    before_bytes = DstCodec().decode_file(dst)
    backup = tmp_path / ".dst-manager" / "revisions" / operation_id / "before" / dst.name
    backup.parent.mkdir(parents=True)
    backup.write_bytes(before_bytes)
    staged = tmp_path / ".dst-manager" / "jobs" / operation_id / "staging" / dst.name
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"repair-staged")
    journal_path = tmp_path / ".dst-manager" / "jobs" / operation_id / "publish-journal.json"
    journal = {
        "operation_id": operation_id,
        "status": "PUBLISHING",
        "files": [
            {
                "target": str(dst),
                "backup": str(backup),
                "staged": None,
                "replaced": True,
            },
        ],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    dst.write_bytes(b"repair-staged")  # 模拟已替换

    restarted = DstManagerService(settings)

    assert dst.read_bytes() == before_bytes
    assert restarted.database.get_job(operation_id)["status"] == "ROLLED_BACK"


def test_cad_staging_rejects_non_valid_dst(tmp_path: Path):
    """CAD 暂存加载要求 VALID：修复/阻断状态的 DST 不得交给 AutoCAD Worker。"""
    dst = _fail_dst(tmp_path)
    document = load_acsm(DstCodec().decode_file(dst)).project(tmp_path)
    workspace = Workspace("workspace", tmp_path, dst, "revision", document)
    runner = CadJobRunner(Mock(), DstCodec(), Mock(), 30)

    # 门禁在计划内容使用前触发，因此最小 plan 即可验证
    with pytest.raises(PlanningError) as exc_info:
        runner._write_staged_dst(workspace, {"groups": []}, {}, tmp_path)

    assert exc_info.value.code == "DST_REPAIR_GATE_BLOCKED"


def _replicate_relative_dwgs(dst: Path) -> None:
    """按失败样本 Relative_FileName 在 DST 目录补齐同名 DWG，保证规划路径落在工作区内。"""
    document = load_acsm(DstCodec().decode_file(dst))
    for item in document.root.iter():
        if etree.QName(item).localname == "AcSmProp" and item.get("propname") == "Relative_FileName":
            relative = (item.text or "").strip().replace("\\", "/").removeprefix("./")
            if not relative:
                continue
            target = (dst.parent / relative).resolve()
            if dst.parent.resolve() not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fake-dwg")


def test_cad_staging_accepts_valid_dst_after_repair(tmp_path: Path):
    """修复发布成功后，CAD 暂存加载恢复为 VALID 并可生成最终 DST。"""
    dst = _fail_dst(tmp_path)
    _replicate_relative_dwgs(dst)
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    workspace = service.open_workspace(dst)
    digest = _repair_preview_digest(service, workspace)
    job = service.execute_repair(workspace.id, workspace.revision_id, digest)
    assert job["status"] == "SUCCEEDED"

    reloaded = service.get_workspace(workspace.id)
    assert reloaded.document.repair_report.status == "VALID"
    # 门禁直接可过
    CadJobRunner(Mock(), DstCodec(), Mock(), 30)._require_valid_staging(
        load_acsm(DstCodec().decode_file(dst)),
    )
    plan = build_structural_plan(reloaded, [], SuffixOptions(True, 1))
    runner = CadJobRunner(Mock(), DstCodec(), Mock(), 30)

    staged = runner._write_staged_dst(reloaded, plan, {}, tmp_path)

    final = load_acsm(DstCodec().decode_file(staged))
    assert final.repair_report.status == "VALID"
    assert len(final.project(tmp_path).sheets) == 24
