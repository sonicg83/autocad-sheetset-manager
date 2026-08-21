import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from dst_manager.application.cad_job import CadJobRunner, RebuildWorkUnit
from dst_manager.domain.editing import SuffixOptions, derive_document_structure
from dst_manager.domain.models import (
    CustomPropertyDefinition,
    DerivedDocument,
    DerivedSubset,
    LayoutReference,
    PropertyDefinitionDiff,
    Sheet,
    SheetSetDocument,
    Subset,
    Workspace,
)
from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.acsm_xml.document import AcsmValidationError
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    decode_console_output,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.dst_codec.codec import _DECODE, _ENCODE
from dst_manager.infrastructure.logging_text import (
    sanitize_log_text,
    validate_log_bytes,
)
from dst_manager.interfaces.cli import _worker_summary
from dst_manager.interfaces.cli import app as cli_app


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
    assert "Core Console：重建布局（退出码 7）stdout" in log
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


def _insert_subset_command(initial_sheet_count: int = 1) -> dict:
    return {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "燃气管道平面图",
        "initial_sheet_count": initial_sheet_count,
        "source": {"type": "template_layout", "file": r"C:\模板\标准.dwt", "layout": "A3"},
    }


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
