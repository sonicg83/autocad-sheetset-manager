import hashlib
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.acsm_xml.document import AcsmValidationError
from dst_manager.infrastructure.autocad.worker import (
    CadCapability,
    CoreConsoleExecutor,
    ScriptRenderer,
    parse_handles,
    parse_rename_result,
    rename_request_path,
    rename_result_path,
)
from dst_manager.infrastructure.dst_codec import DstCodec

_SAMPLE_PROJECT = Path(__file__).parents[2] / "sample" / "project1"
pytestmark = [
    pytest.mark.skipif(os.environ.get("DST_MANAGER_RUN_AUTOCAD") != "1", reason="需要显式启用真实AutoCAD测试"),
    pytest.mark.skipif(not _SAMPLE_PROJECT.is_dir(), reason="公开仓库不分发真实工程样本"),
]


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_plugin_loads_and_reads_layout_handles(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    capability = CadCapability(
        version,
        Path(f"C:/Program Files/Autodesk/AutoCAD {version}/accoreconsole.exe"),
        root / "plugins" / f"autocad{version}" / "DstManager.AutoCAD.dll",
    )
    assert capability.available
    source = root / "sample" / "project1" / "GP-0000 封面.dwg"
    drawing = tmp_path / source.name
    shutil.copy2(source, drawing)
    script = tmp_path / "handles.scr"
    script.write_text(ScriptRenderer().render_handles(capability.plugin), encoding="mbcs")
    completed = CoreConsoleExecutor().run(capability, drawing, script, 120)
    handle_file = drawing.with_suffix(".dst-handles.txt")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert parse_handles(handle_file.read_text(encoding="utf-8"))


def _rename_capability(version: str) -> CadCapability:
    root = Path(__file__).parents[2]
    capability = CadCapability(
        version,
        Path(f"C:/Program Files/Autodesk/AutoCAD {version}/accoreconsole.exe"),
        root / "plugins" / f"autocad{version}" / "DstManager.AutoCAD.dll",
    )
    if not capability.available:
        pytest.skip(f"缺少 AutoCAD {version} Core Console 或匹配插件")
    return capability


def _copy_rename_drawing(tmp_path: Path, minimum_layouts: int) -> Path:
    source_document = AcsmDocument(DstCodec().decode_file(_SAMPLE_PROJECT / "图纸集数据文件.dst")).project(_SAMPLE_PROJECT)
    groups: dict[Path, list[str]] = {}
    for sheet in source_document.sheets:
        groups.setdefault(sheet.layout.resolved_path, []).append(sheet.layout.layout_name)
    source = next(
        (
            path
            for path, names in sorted(groups.items(), key=lambda item: str(item[0]))
            if len(names) >= minimum_layouts
        ),
        None,
    )
    if source is None:
        pytest.skip(f"私有样本中不存在至少含 {minimum_layouts} 个业务布局的 DWG")
    drawing = tmp_path / source.name
    shutil.copy2(source, drawing)
    return drawing


def _read_handles(capability: CadCapability, drawing: Path, script: Path) -> dict[str, str]:
    script.write_text(ScriptRenderer().render_handles(capability.plugin), encoding="mbcs")
    CoreConsoleExecutor().run(capability, drawing, script, 120)
    return parse_handles(drawing.with_suffix(".dst-handles.txt").read_text(encoding="utf-8"))


def _add_case_probe_layout(capability: CadCapability, drawing: Path, script: Path) -> str:
    name = "DST_CASE_PROBE_AUTOMATED_RENAME"
    script.write_text(
        f"FILEDIA\n0\nCMDECHO\n0\n_.-LAYOUT\n_New\n{name}\n_.QSAVE\n_.QUIT\n",
        encoding="mbcs",
    )
    CoreConsoleExecutor().run(capability, drawing, script, 120)
    return name


@pytest.mark.parametrize(("mapping", "changed_count"), [("exchange", 2), ("cycle", 3), ("case", 1)])
@pytest.mark.parametrize("version", ["2016", "2020"])
def test_rename_layouts_preserves_handle_mapping_for_exchange_cycle_and_case_only_changes(
    version: str,
    mapping: str,
    changed_count: int,
    tmp_path: Path,
):
    capability = _rename_capability(version)
    drawing = _copy_rename_drawing(tmp_path, changed_count)
    before_handles = _read_handles(capability, drawing, tmp_path / "before-handles.scr")
    if mapping == "case":
        case_name = _add_case_probe_layout(capability, drawing, tmp_path / "add-case-probe.scr")
        before_handles = _read_handles(capability, drawing, tmp_path / "case-before-handles.scr")
        assert case_name in before_handles
    original_names = sorted(before_handles)
    rows = [{"old_name": name, "new_name": name} for name in original_names]
    if mapping == "exchange":
        rows[0]["new_name"], rows[1]["new_name"] = original_names[1], original_names[0]
    elif mapping == "cycle":
        rows[0]["new_name"], rows[1]["new_name"], rows[2]["new_name"] = (
            original_names[1],
            original_names[2],
            original_names[0],
        )
    else:
        rows[original_names.index(case_name)]["new_name"] = case_name.lower()
    expected_handles = {row["new_name"]: before_handles[row["old_name"]] for row in rows}
    request = rename_request_path(drawing)
    request.write_text(json.dumps({"version": 1, "layouts": rows}, ensure_ascii=False), encoding="utf-8")
    rename_script = tmp_path / "rename.scr"
    rename_script.write_text(ScriptRenderer().render_rename(capability.plugin, request), encoding="mbcs")

    completed = CoreConsoleExecutor().run(capability, drawing, rename_script, 120)

    after_handles = _read_handles(capability, drawing, tmp_path / "after-handles.scr")
    result_path = rename_result_path(drawing)
    assert completed.returncode == 0
    assert after_handles == expected_handles
    assert parse_rename_result(result_path.read_text(encoding="utf-8"), set(expected_handles)) == changed_count


@pytest.mark.parametrize("request_kind", ["missing", "duplicate", "extra"])
@pytest.mark.parametrize("version", ["2016", "2020"])
def test_rename_layouts_rejects_invalid_complete_layout_sets(version: str, request_kind: str, tmp_path: Path):
    capability = _rename_capability(version)
    drawing = _copy_rename_drawing(tmp_path, 2)
    before_handles = _read_handles(capability, drawing, tmp_path / "before-handles.scr")
    original_names = sorted(before_handles)
    rows = [{"old_name": name, "new_name": name} for name in original_names]
    if request_kind == "missing":
        rows.pop()
    elif request_kind == "duplicate":
        rows[1]["new_name"] = original_names[0]
    else:
        rows.append({"old_name": "意外额外布局", "new_name": "意外额外布局"})
    request = rename_request_path(drawing)
    request.write_text(json.dumps({"version": 1, "layouts": rows}, ensure_ascii=False), encoding="utf-8")
    rename_script = tmp_path / "rename-invalid.scr"
    rename_script.write_text(ScriptRenderer().render_rename(capability.plugin, request), encoding="mbcs")

    failed = False
    try:
        CoreConsoleExecutor().run(capability, drawing, rename_script, 120)
    except subprocess.CalledProcessError:
        failed = True

    assert failed or not rename_result_path(drawing).exists()
    assert _read_handles(capability, drawing, tmp_path / "after-handles.scr") == before_handles


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_structural_subset_title_change_rebuilds_dwg_and_dst(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample" / "project1"
    shutil.copy2(source_project / "图纸集数据文件.dst", tmp_path / "图纸集数据文件.dst")
    shutil.copy2(source_project / "GP-0000 封面.dwg", tmp_path / "GP-0000 封面.dwg")
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=120,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / "图纸集数据文件.dst")
    subset = workspace.document.subsets[0]
    job = service.execute_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_subset", "subset_id": subset.acsm_id, "title": "封面测试"}],
        version,
    )
    assert job["status"] == "QUEUED"
    result = service.run_next_job()
    assert result and result["status"] == "SUCCEEDED", result
    assert len(result["files"]) == 1
    assert result["files"][0]["duration_ms"] > 0
    assert result["files"][0]["peak_memory_bytes"] > 0
    assert result["files"][0]["staging_bytes"] > 0
    reopened = service.open_workspace(tmp_path / "图纸集数据文件.dst")
    changed = reopened.document.subsets[0].sheets[0]
    assert changed.title == "封面测试"
    assert changed.layout.layout_name == "0000 封面测试"
    assert changed.layout.handle
    assert (tmp_path / ".dst-manager" / "revisions" / result["id"] / "before" / "图纸集数据文件.dst").is_file()


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_missing_custom_value_update_and_supported_insert_complete_before_publish(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    dst_name = "图纸集数据文件.dst"
    drawing_name = "GP-0000 封面.dwg"
    shutil.copy2(source_project / dst_name, tmp_path / dst_name)
    shutil.copy2(source_project / drawing_name, tmp_path / drawing_name)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / dst_name)
    subset = workspace.document.subsets[0]
    existing = subset.sheets[0]
    assert existing.custom_properties["备注"] == ""
    commands = [
        {"type": "update_sheet_set", "custom_properties": {"版本": "B"}},
        {
            "type": "update_sheet",
            "sheet_id": existing.acsm_id,
            "custom_properties": {"备注": "", "出图比例": "1:500", "设计人": existing.custom_properties["设计人"]},
        },
        {
            "type": "insert_sheet",
            "target_subset_id": subset.acsm_id,
            "position": 1,
            "source": {"type": "template_layout", "file": str(existing.layout.resolved_path), "layout": existing.layout.layout_name},
        },
    ]
    preview = service.preview_changes(workspace.id, workspace.revision_id, commands, version)
    assert preview["executable"] is True, preview
    job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
    assert job["status"] == "QUEUED", job

    result = service.run_next_job()

    assert result and result["status"] == "SUCCEEDED", result
    reopened = service.open_workspace(tmp_path / dst_name)
    final_subset = reopened.document.subsets[0]
    assert reopened.document.custom_properties["版本"] == "B"
    assert [sheet.title for sheet in final_subset.sheets] == ["封面 (一)", "封面 (二)"]
    assert all(sheet.custom_properties["备注"] == "" for sheet in final_subset.sheets)
    updated = next(sheet for sheet in final_subset.sheets if sheet.acsm_id == existing.acsm_id)
    assert updated.custom_properties["出图比例"] == "1:500"
    xml = AcsmDocument(DstCodec().decode_file(tmp_path / dst_name))
    sheetset_remark_values = xml.root.xpath(
        "//*[local-name()='AcSmSheetSet']/*[local-name()='AcSmCustomPropertyBag']"
        "/*[local-name()='AcSmCustomPropertyValue' and @propname='备注']"
        "/*[local-name()='AcSmProp' and @propname='Value']"
    )
    assert sheetset_remark_values == []
    for sheet in final_subset.sheets:
        value_nodes = xml.root.xpath(
            "//*[@ID=$sheet_id and local-name()='AcSmSheet']"
            "/*[local-name()='AcSmCustomPropertyBag']"
            "/*[local-name()='AcSmCustomPropertyValue' and @propname='备注']"
            "/*[local-name()='AcSmProp' and @propname='Value']",
            sheet_id=sheet.acsm_id,
        )
        assert value_nodes == []


@pytest.mark.parametrize("version", ["2016", "2020"])
@pytest.mark.parametrize(("parallel", "expected_peak"), [(1, 1), (4, 4), (10, 5)])
def test_five_dwg_groups_run_with_bounded_parallelism(
    version: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parallel: int,
    expected_peak: int,
):
    active = 0
    maximum = 0
    lock = threading.Lock()
    original_run = CoreConsoleExecutor.run

    def measure_console_peak(self, *args, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        try:
            return original_run(self, *args, **kwargs)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(CoreConsoleExecutor, "run", measure_console_peak)
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    dst_name = "图纸集数据文件.dst"
    shutil.copy2(source_project / dst_name, tmp_path / dst_name)
    source_document = AcsmDocument(DstCodec().decode_file(source_project / dst_name)).project(source_project)
    sheets = [subset.sheets[0] for subset in source_document.subsets[:5]]
    for drawing in {sheet.layout.resolved_path for sheet in sheets}:
        shutil.copy2(drawing, tmp_path / drawing.name)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
        cad_max_parallel=parallel,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / dst_name)
    commands = [
        {"type": "update_subset", "subset_id": subset.acsm_id, "title": f"{subset.name}-并行"}
        for subset in workspace.document.subsets[:5]
    ]
    job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
    assert job["status"] == "QUEUED"
    result = service.run_next_job()
    assert result and result["status"] == "SUCCEEDED", result
    assert len(result["files"]) == 5
    assert all(item["status"] == "SUCCEEDED" for item in result["files"])
    assert all(item["duration_ms"] > 0 and item["peak_memory_bytes"] > 0 for item in result["files"])
    assert maximum == expected_peak
    reopened = service.open_workspace(tmp_path / dst_name)
    assert all("-并行" in subset.sheets[0].title for subset in reopened.document.subsets[:5])


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_insert_and_delete_rebuilds_supported_subset(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    shutil.copy2(source_project / "图纸集数据文件.dst", tmp_path / "图纸集数据文件.dst")
    for name in ("GP-0001-0005 图纸目录(一)-(五).dwg", "GP-0006-0007 主要设备及材料表(一)-(二).dwg"):
        shutil.copy2(source_project / name, tmp_path / name)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / "图纸集数据文件.dst")
    source_subset = workspace.document.subsets[2]
    deleted_id = source_subset.sheets[2].acsm_id
    template = source_subset.sheets[1]
    commands = [
        {"type": "delete_sheet", "sheet_id": deleted_id},
        {
            "type": "insert_sheet",
            "target_subset_id": source_subset.acsm_id,
            "position": 1,
            "count": 1,
            "source": {
                "type": "template_layout",
                "file": str(template.layout.resolved_path),
                "layout": template.layout.layout_name,
            },
        },
    ]
    job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
    assert job["status"] == "QUEUED", job
    result = service.run_next_job()
    assert result and result["status"] == "SUCCEEDED", result
    reopened = service.open_workspace(tmp_path / "图纸集数据文件.dst")
    final_source = reopened.document.subsets[2]
    assert deleted_id not in {sheet.acsm_id for sheet in reopened.document.sheets}
    assert len(final_source.sheets) == len(source_subset.sheets)
    assert len({sheet.layout.handle for sheet in final_source.sheets}) == len(final_source.sheets)


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_delete_last_sheet_removes_subset_and_dwg(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]; source_project = root / "sample/project1"
    shutil.copy2(source_project / "图纸集数据文件.dst", tmp_path / "图纸集数据文件.dst")
    drawing = tmp_path / "GP-0000 封面.dwg"; shutil.copy2(source_project / drawing.name, drawing)
    settings=Settings(data_dir=tmp_path/"data",autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),autocad_2016_plugin=root/"plugins/autocad2016/DstManager.AutoCAD.dll",autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),autocad_2020_plugin=root/"plugins/autocad2020/DstManager.AutoCAD.dll",cad_timeout_seconds=120)
    service=DstManagerService(settings); workspace=service.open_workspace(tmp_path/"图纸集数据文件.dst"); subset=workspace.document.subsets[0]; sheet_id=subset.sheets[0].acsm_id
    job=service.execute_changes(workspace.id,workspace.revision_id,[{"type":"delete_sheet","sheet_id":sheet_id,"delete_empty_subset":True}],version); assert job["status"]=="QUEUED"
    result=service.run_next_job(); assert result and result["status"]=="SUCCEEDED",result
    reopened=service.open_workspace(tmp_path/"图纸集数据文件.dst"); assert subset.acsm_id not in {item.acsm_id for item in reopened.document.subsets}; assert not drawing.exists()
    assert (tmp_path/".dst-manager"/"revisions"/result["id"]/"before"/drawing.name).is_file()


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_largest_25_layout_group_rebuilds_in_order(version: str, tmp_path: Path):
    root=Path(__file__).parents[2]; source_project=root/"sample/project1"; shutil.copy2(source_project/"图纸集数据文件.dst",tmp_path/"图纸集数据文件.dst")
    drawing_name="GP-0038-0062 龙岗段入廊给水、再生水平面图(十六)-(四十).dwg"; shutil.copy2(source_project/drawing_name,tmp_path/drawing_name)
    settings=Settings(data_dir=tmp_path/"data",autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),autocad_2016_plugin=root/"plugins/autocad2016/DstManager.AutoCAD.dll",autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),autocad_2020_plugin=root/"plugins/autocad2020/DstManager.AutoCAD.dll",cad_timeout_seconds=900)
    service=DstManagerService(settings); workspace=service.open_workspace(tmp_path/"图纸集数据文件.dst"); subset=workspace.document.subsets[14]; assert len(subset.sheets)==25
    job=service.execute_changes(workspace.id,workspace.revision_id,[{"type":"renumber_sheets","subset_id":subset.acsm_id,"start":38,"width":4}],version); assert job["status"]=="QUEUED"
    result=service.run_next_job(); assert result and result["status"]=="SUCCEEDED",result
    rebuilt=service.open_workspace(tmp_path/"图纸集数据文件.dst").document.subsets[14].sheets; assert len(rebuilt)==25; assert [sheet.number for sheet in rebuilt]==[str(value).zfill(4) for value in range(38,63)]; assert len({sheet.layout.handle for sheet in rebuilt})==25


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_parallel_one_and_two_produce_equivalent_results(version: str, tmp_path: Path):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    source_document = AcsmDocument(DstCodec().decode_file(source_project / "图纸集数据文件.dst")).project(source_project)
    source_sheets = [subset.sheets[0] for subset in source_document.subsets[:2]]
    outcomes = []
    for parallel in (1, 2):
        project = tmp_path / f"parallel-{parallel}"
        project.mkdir()
        shutil.copy2(source_project / "图纸集数据文件.dst", project / "图纸集数据文件.dst")
        for drawing in {sheet.layout.resolved_path for sheet in source_sheets}:
            shutil.copy2(drawing, project / drawing.name)
        settings = Settings(
            data_dir=project / "data",
            autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
            autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
            autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
            autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
            cad_timeout_seconds=180,
            cad_max_parallel=parallel,
        )
        service = DstManagerService(settings)
        workspace = service.open_workspace(project / "图纸集数据文件.dst")
        commands = [
            {"type": "update_subset", "subset_id": subset.acsm_id, "title": f"{subset.name}-等价"}
            for subset in workspace.document.subsets[:2]
        ]
        job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
        assert job["status"] == "QUEUED"
        result = service.run_next_job()
        assert result and result["status"] == "SUCCEEDED", result
        reopened = service.open_workspace(project / "图纸集数据文件.dst")
        outcomes.append(
            [
                (sheet.acsm_id, sheet.number, sheet.title, sheet.layout.layout_name)
                for subset in reopened.document.subsets[:2]
                for sheet in subset.sheets
            ]
        )
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_injected_second_dwg_failure_never_publishes_partial_files(version: str, tmp_path: Path, monkeypatch):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    dst_name = "图纸集数据文件.dst"
    shutil.copy2(source_project / dst_name, tmp_path / dst_name)
    source_document = AcsmDocument(DstCodec().decode_file(source_project / dst_name)).project(source_project)
    source_sheets = [subset.sheets[0] for subset in source_document.subsets[:2]]
    for drawing in {sheet.layout.resolved_path for sheet in source_sheets}:
        shutil.copy2(drawing, tmp_path / drawing.name)
    formal_files = [tmp_path / dst_name, *(tmp_path / sheet.layout.resolved_path.name for sheet in source_sheets)]
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in formal_files}
    original_run = CoreConsoleExecutor.run
    calls = 0

    failed_script = None

    def fail_second_console_call(self, capability, drawing, script, timeout):
        nonlocal calls, failed_script
        calls += 1
        if calls == 2:
            failed_script = Path(script).name
            raise subprocess.CalledProcessError(1, [str(capability.console)], "", "INJECTED_DWG_FAILURE")
        return original_run(self, capability, drawing, script, timeout)

    monkeypatch.setattr(CoreConsoleExecutor, "run", fail_second_console_call)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
        cad_max_parallel=1,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(tmp_path / dst_name)
    commands = [
        {"type": "update_subset", "subset_id": subset.acsm_id, "title": f"{subset.name}-失败注入"}
        for subset in workspace.document.subsets[:2]
    ]
    job = service.execute_changes(workspace.id, workspace.revision_id, commands, version)
    assert job["status"] == "QUEUED"

    result = service.run_next_job()

    assert result and result["status"] == "FAILED"
    assert result["error_code"] == "CAD_PROCESS_FAILED"
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in formal_files}
    assert after == before
    assert {path.name for path in tmp_path.glob("*.dwg")} == {path.name for path in formal_files if path.suffix.lower() == ".dwg"}
    assert not (tmp_path / ".dst-manager" / "revisions" / result["id"] / "manifest.json").exists()
    assert failed_script == "rebuild-001.scr"


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_cad_success_then_dom_failure_keeps_formal_hashes(version: str, tmp_path: Path, monkeypatch):
    root = Path(__file__).parents[2]
    source_project = root / "sample/project1"
    dst = tmp_path / "图纸集数据文件.dst"
    drawing = tmp_path / "GP-0000 封面.dwg"
    shutil.copy2(source_project / dst.name, dst)
    shutil.copy2(source_project / drawing.name, drawing)
    settings = Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=180,
    )
    service = DstManagerService(settings)
    workspace = service.open_workspace(dst)
    subset = workspace.document.subsets[0]
    job = service.execute_changes(
        workspace.id,
        workspace.revision_id,
        [{"type": "update_subset", "subset_id": subset.acsm_id, "title": "DOM 失败注入"}],
        version,
    )
    assert job["status"] == "QUEUED"
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dst, drawing)}

    def fail_dom(*_args, **_kwargs):
        raise AcsmValidationError("CUSTOM_PROPERTY_VALUE_DUPLICATED: 注入")

    monkeypatch.setattr(AcsmDocument, "apply_derived_document", fail_dom)
    result = service.run_next_job()

    assert result and result["status"] == "FAILED"
    assert result["error_code"] == "CUSTOM_PROPERTY_VALUE_DUPLICATED"
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dst, drawing)}
    assert after == before
    assert not (tmp_path / ".dst-manager" / "revisions" / result["id"] / "manifest.json").exists()


def _copy_single_subset_project(tmp_path: Path) -> tuple[Path, Path, str]:
    codec = DstCodec()
    source_dst = _SAMPLE_PROJECT / "图纸集数据文件.dst"
    document = AcsmDocument(codec.decode_file(source_dst))
    sheet_set = document.root.xpath("//*[local-name()='AcSmSheetSet']")[0]
    subsets = sheet_set.xpath("./*[local-name()='AcSmSubset']")
    for subset in subsets[1:]:
        sheet_set.remove(subset)
    dst = tmp_path / source_dst.name
    codec.encode_file(document.to_bytes(), dst)
    projected = document.project(_SAMPLE_PROJECT)
    source_sheet = projected.subsets[0].sheets[0]
    drawing = tmp_path / source_sheet.layout.resolved_path.name
    shutil.copy2(source_sheet.layout.resolved_path, drawing)
    return dst, drawing, source_sheet.layout.layout_name


def _system_settings(tmp_path: Path) -> Settings:
    root = Path(__file__).parents[2]
    return Settings(
        data_dir=tmp_path / "data",
        autocad_2016_console=Path("C:/Program Files/Autodesk/AutoCAD 2016/accoreconsole.exe"),
        autocad_2016_plugin=root / "plugins/autocad2016/DstManager.AutoCAD.dll",
        autocad_2020_console=Path("C:/Program Files/Autodesk/AutoCAD 2020/accoreconsole.exe"),
        autocad_2020_plugin=root / "plugins/autocad2020/DstManager.AutoCAD.dll",
        cad_timeout_seconds=240,
        cad_max_parallel=1,
    )


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_insert_subset_creates_independent_dwg_with_batch_layouts(version: str, tmp_path: Path):
    dst, template, template_layout = _copy_single_subset_project(tmp_path)
    service = DstManagerService(_system_settings(tmp_path))
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "独立DWG验证",
        "initial_sheet_count": 3,
        "source": {"type": "template_layout", "file": str(template), "layout": template_layout},
    }
    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], version)
    created_group = next(group for group in preview["execution_intent"]["groups"] if group["operation"] == "create")
    assert created_group["source_target_file"] is None
    assert len(created_group["layouts"]) == 3

    job = service.execute_changes(workspace.id, workspace.revision_id, [command], version)
    result = service.run_next_job()

    assert job["status"] == "QUEUED"
    assert result and result["status"] == "SUCCEEDED", result
    reopened = service.open_workspace(dst)
    created = next(subset for subset in reopened.document.subsets if "独立DWG验证" in subset.name)
    assert len(created.sheets) == 3
    assert len({sheet.layout.resolved_path for sheet in created.sheets}) == 1
    created_dwg = created.sheets[0].layout.resolved_path
    assert created_dwg and created_dwg.is_file() and created_dwg != template
    assert [sheet.layout.layout_name for sheet in created.sheets] == [
        layout["target_layout"] for layout in created_group["layouts"]
    ]
    assert len({sheet.layout.handle for sheet in created.sheets}) == 3
    assert all(sheet.layout.handle != "0" for sheet in created.sheets)


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_batch_insert_rebuilds_layouts_in_final_order(version: str, tmp_path: Path):
    dst, template, template_layout = _copy_single_subset_project(tmp_path)
    service = DstManagerService(_system_settings(tmp_path))
    workspace = service.open_workspace(dst)
    subset = workspace.document.subsets[0]
    command = {
        "type": "insert_sheet",
        "target_subset_id": subset.acsm_id,
        "ordinal": 1,
        "placement": "after",
        "count": 3,
        "source": {"type": "template_layout", "file": str(template), "layout": template_layout},
    }
    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], version)
    group = preview["execution_intent"]["groups"][0]
    assert group["operation"] == "rebuild"
    assert len(group["layouts"]) == 4

    job = service.execute_changes(workspace.id, workspace.revision_id, [command], version)
    result = service.run_next_job()

    assert job["status"] == "QUEUED"
    assert result and result["status"] == "SUCCEEDED", result
    rebuilt = service.open_workspace(dst).document.subsets[0].sheets
    assert [sheet.layout.layout_name for sheet in rebuilt] == [layout["target_layout"] for layout in group["layouts"]]
    assert len({sheet.layout.handle for sheet in rebuilt}) == 4
    assert all(sheet.layout.handle != "0" for sheet in rebuilt)


@pytest.mark.parametrize("version", ["2016", "2020"])
def test_missing_template_layout_is_blocked_during_preview(version: str, tmp_path: Path):
    dst, drawing, _ = _copy_single_subset_project(tmp_path)
    service = DstManagerService(_system_settings(tmp_path))
    workspace = service.open_workspace(dst)
    subset = workspace.document.subsets[0]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dst, drawing)}
    command = {
        "type": "insert_sheet",
        "target_subset_id": subset.acsm_id,
        "ordinal": 1,
        "placement": "after",
        "count": 1,
        "source": {"type": "template_layout", "file": str(drawing), "layout": "不存在的模板布局"},
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], version)

    assert preview["executable"] is False
    assert preview["diagnostics"][0]["code"] == "SOURCE_LAYOUT_NOT_FOUND"
    with service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dst, drawing)} == before
    assert not (tmp_path / ".dst-manager").exists()
