import json
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from dst_manager.config import Settings
from dst_manager.infrastructure.acsm_xml import AcsmDocument
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.publisher import file_sha256
from dst_manager.interfaces.api import create_app


def _add_second_sheet_with_different_scale(dst):
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]
    first = subset.xpath("./*[local-name()='AcSmSheet']")[0]
    second = deepcopy(first)
    for index, node in enumerate([second, *second.xpath(".//*[@ID]")], start=20):
        node.set("ID", f"g00000000-0000-0000-0000-{index:012X}")
    second.xpath("./*[local-name()='AcSmProp' and @propname='Number']")[0].text = "002"
    second.xpath("./*[local-name()='AcSmProp' and @propname='Title']")[0].text = "剖面"
    second.xpath(
        "./*[local-name()='AcSmAcDbLayoutReference']/*[local-name()='AcSmProp' and @propname='Name']",
    )[0].text = "002 剖面"
    second.xpath(
        "./*[local-name()='AcSmCustomPropertyBag']/*[local-name()='AcSmCustomPropertyValue' and @propname='比例']/*[local-name()='AcSmProp' and @propname='Value']",
    )[0].text = "1:500"
    subset.append(second)
    DstCodec().encode_file(document.to_bytes(), dst)


def _reverse_sheet_order(dst):
    document = AcsmDocument(DstCodec().decode_file(dst))
    subset = document.root.xpath("//*[local-name()='AcSmSubset']")[0]
    sheets = subset.xpath("./*[local-name()='AcSmSheet']")
    subset.remove(sheets[1])
    subset.insert(subset.index(sheets[0]), sheets[1])
    DstCodec().encode_file(document.to_bytes(), dst)


def test_read_only_open_does_not_create_workspace_metadata(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    before = {
        path: (path.stat().st_mtime_ns, path.read_bytes())
        for path in dst.parent.iterdir()
        if path.is_file()
    }
    data_dir = tmp_path / "application-data"
    client = TestClient(create_app(Settings(data_dir=data_dir)))
    response = client.post("/api/workspaces/open", json={"dst_path": str(dst)})
    assert response.status_code == 200
    assert not (tmp_path / ".dst-manager").exists()
    assert {
        path: (path.stat().st_mtime_ns, path.read_bytes())
        for path in dst.parent.iterdir()
        if path.is_file()
    } == before


def test_health_returns_current_run_id(tmp_path, monkeypatch):
    monkeypatch.setenv("DST_MANAGER_RUN_ID", "run-test-123")
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))

    assert client.get("/api/health").json() == {"status": "ok", "run_id": "run-test-123"}


def test_open_preview_execute(tmp_path,tiny_workspace):
    dst,sheet_id=tiny_workspace; client=TestClient(create_app(Settings(data_dir=tmp_path/"data"))); opened=client.post("/api/workspaces/open",json={"dst_path":str(dst)}).json(); assert opened["sheet_set"]["sheet_count"]==1
    payload={"base_revision_id":opened["revision_id"],"commands":[{"type":"update_sheet_properties","sheet_id":sheet_id,"custom_properties":{"比例":"1:200"}}]}; assert client.post(f"/api/workspaces/{opened['id']}/changes/preview",json=payload).json()["requires_cad"] is False
    job=client.post(f"/api/workspaces/{opened['id']}/changes/execute",json=payload).json(); assert job["status"]=="SUCCEEDED"; assert (dst.parent/".dst-manager"/"revisions"/job["id"]/"before"/dst.name).is_file()
def test_revision_conflict(tmp_path,tiny_workspace):
    dst,_=tiny_workspace; client=TestClient(create_app(Settings(data_dir=tmp_path/"data"))); opened=client.post("/api/workspaces/open",json={"dst_path":str(dst)}).json(); response=client.post(f"/api/workspaces/{opened['id']}/changes/preview",json={"base_revision_id":"stale","commands":[]}); assert response.status_code==409 and response.json()["code"]=="REVISION_CONFLICT"

def test_sheet_set_name_is_metadata_only(tmp_path,tiny_workspace):
    dst,_=tiny_workspace; client=TestClient(create_app(Settings(data_dir=tmp_path/"data"))); opened=client.post("/api/workspaces/open",json={"dst_path":str(dst)}).json(); payload={"base_revision_id":opened["revision_id"],"commands":[{"type":"update_sheet_set","name":"新图纸集"}]}
    assert client.post(f"/api/workspaces/{opened['id']}/changes/preview",json=payload).json()["requires_cad"] is False
    assert client.post(f"/api/workspaces/{opened['id']}/changes/execute",json=payload).json()["status"]=="SUCCEEDED"


def test_metadata_illegal_xml_text_is_blocked_without_side_effects(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    before = dst.read_bytes()
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {
        "base_revision_id": opened["revision_id"],
        "commands": [{"type": "update_sheet_set", "name": "非法\u0001名称"}],
    }

    preview = client.post(f"/api/workspaces/{opened['id']}/changes/preview", json=payload)
    execute = client.post(f"/api/workspaces/{opened['id']}/changes/execute", json=payload)

    assert preview.status_code == 200
    assert preview.json()["executable"] is False
    assert preview.json()["diagnostics"][0]["code"] == "XML_TEXT_INVALID"
    assert execute.status_code == 400
    assert execute.json()["code"] == "PLAN_INVALID"
    assert dst.read_bytes() == before
    with app.state.service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM document_revisions").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0


def test_empty_sheetset_sheet_property_round_trip_reports_zero_affected(tmp_path):
    xml = (
        b'<AcSmDatabase ID="g00000000-0000-0000-0000-000000000001">'
        b'<AcSmProp propname="DbVersion">1.1</AcSmProp>'
        b'<AcSmSheetSet ID="g00000000-0000-0000-0000-000000000002">'
        b'<AcSmProp propname="Name">Empty</AcSmProp>'
        b'</AcSmSheetSet></AcSmDatabase>'
    )
    dst = tmp_path / "empty.dst"
    DstCodec().encode_file(xml, dst)
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {
        "base_revision_id": opened["revision_id"],
        "commands": [{"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"}],
    }

    preview = client.post(f"/api/workspaces/{opened['id']}/changes/preview", json=payload).json()
    executed = client.post(f"/api/workspaces/{opened['id']}/changes/execute", json=payload).json()
    reopened = client.get(f"/api/workspaces/{opened['id']}").json()
    exported = client.get(f"/api/workspaces/{opened['id']}/custom-properties/export").text

    assert [item["code"] for item in preview["diagnostics"]] == []
    assert preview["executable"] is True
    assert preview["changes"][0]["affected_sheet_count"] == 0
    assert preview["semantic_diff"]["properties"][0]["affected_sheet_count"] == 0
    assert executed["status"] == "SUCCEEDED"
    assert {item["name"] for item in reopened["sheet_set"]["property_definitions"]} == {"专业"}
    assert "sheet,专业," in exported


def test_structural_preview_and_execute_defer_cad_validation(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app)
    app.state.service.inspect_template = Mock(side_effect=AssertionError("预览不得调用 CAD"))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {
        "base_revision_id": opened["revision_id"],
        "cad_version": "2016",
        "commands": [{
            "type": "insert_subset",
            "ordinal": 1,
            "placement": "after",
            "title": "新建子集",
            "initial_sheet_count": 1,
            "source": {"type": "template_layout", "file": str(dst.parent / "A.dwg"), "layout": "001 平面"},
        }],
    }

    preview = client.post(f"/api/workspaces/{opened['id']}/changes/preview", json=payload).json()
    unconfirmed = client.post(f"/api/workspaces/{opened['id']}/changes/execute", json=payload)
    executed = client.post(
        f"/api/workspaces/{opened['id']}/changes/execute",
        json={**payload, "preview_digest": preview["preview_digest"]},
    ).json()
    invalid = client.post(
        f"/api/workspaces/{opened['id']}/changes/preview",
        json={**payload, "cad_version": "2018"},
    )

    assert preview["executable"] is True
    assert preview["cad_version"] == "2016"
    assert preview["execution_intent"]["cad_validation_deferred"] is True
    assert preview["execution_intent"]["source_baselines"][0]["sha256"] == file_sha256(dst.parent / "A.dwg")
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["code"] == "REPREVIEW_REQUIRED"
    assert executed["payload"]["plan"]["cad_version"] == "2016"
    assert executed["payload"]["plan"]["execution_intent"]["source_baselines"] == preview["execution_intent"]["source_baselines"]
    app.state.service.inspect_template.assert_not_called()
    assert invalid.status_code == 422


def test_get_job_files_returns_cad_operation_and_timing_directly(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    started = datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC)
    finished = datetime(2026, 8, 26, 1, 2, 4, tzinfo=UTC)
    app.state.service.database.create_job(
        "job-files-contract",
        opened["id"],
        "change_set",
        "QUEUED",
        {"plan": {"requires_cad": True}},
        "2020",
    )
    app.state.service.database.upsert_job_file(
        "job-files-contract",
        dst.parent / "001 第一册.dwg",
        cad_operation="rename_only",
        status="SUCCEEDED",
        started_at=started,
        finished_at=finished,
    )

    response = client.get("/api/jobs/job-files-contract")

    assert response.status_code == 200
    assert response.json()["files"][0] == response.json()["files"][0] | {
        "cad_operation": "rename_only",
        "started_at": started.replace(tzinfo=None).isoformat(),
        "finished_at": finished.replace(tzinfo=None).isoformat(),
    }


def test_retry_then_pre_cad_failure_does_not_expose_previous_file_terminal_state(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    database = app.state.service.database
    database.create_job(
        "job-retry-files",
        opened["id"],
        "change_set",
        "QUEUED",
        {"plan": {"requires_cad": True}},
        "2020",
    )
    database.upsert_job_file(
        "job-retry-files",
        dst.parent / "001 第一册.dwg",
        source_path=str(dst.parent / "old.dwg"),
        cad_operation="rebuild",
        status="SUCCEEDED",
        progress=100,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=100,
        error_code="OLD_ERROR",
        error_detail="old detail",
    )
    database.update_job("job-retry-files", "FAILED", 0, "CAD_FAILED")

    retry = client.post("/api/jobs/job-retry-files/retry")
    database.update_job("job-retry-files", "FAILED", 0, "PRE_CAD_FAILURE")
    details = client.get("/api/jobs/job-retry-files")

    assert retry.status_code == 200
    assert details.status_code == 200
    item = details.json()["files"][0]
    assert item["cad_operation"] == "rebuild"
    assert item["source_path"] == "old.dwg"
    assert item == item | {
        "status": "PENDING",
        "progress": 0,
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "error_code": None,
        "error_detail": None,
    }


def test_preview_blocks_invalid_custom_property_before_job_creation(tmp_path, tiny_workspace):
    dst, sheet_id = tiny_workspace
    xml = DstCodec().decode_file(dst).replace(b'<AcSmProp propname="Flags" vt="3">2</AcSmProp>', b'<AcSmProp propname="Flags" vt="3">9</AcSmProp>', 1)
    DstCodec().encode_file(xml, dst)
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {"base_revision_id": opened["revision_id"], "commands": [{"type": "update_sheet_properties", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}]}

    preview = client.post(f"/api/workspaces/{opened['id']}/changes/preview", json=payload).json()

    assert preview["executable"] is False
    assert preview["diagnostics"][0]["code"] == "CUSTOM_PROPERTY_FLAGS_INVALID"
    execution = client.post(f"/api/workspaces/{opened['id']}/changes/execute", json=payload)
    assert execution.status_code == 400
    assert execution.json() == {"code": "PLAN_INVALID", "message": "执行计划包含阻断诊断"}
    assert "traceback" not in execution.text.lower()
    with app.state.service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0


def test_full_form_empty_roundtrip_is_semantic_noop(tmp_path, tiny_workspace):
    dst, sheet_id = tiny_workspace
    xml = DstCodec().decode_file(dst).replace(b'<AcSmProp propname="Value" vt="8">1:100</AcSmProp>', b"", 1)
    DstCodec().encode_file(xml, dst)
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {"base_revision_id": opened["revision_id"], "commands": [{"type": "update_sheet_properties", "sheet_id": sheet_id, "custom_properties": {"比例": ""}}]}

    preview = client.post(f"/api/workspaces/{opened['id']}/changes/preview", json=payload).json()

    assert preview["executable"] is True
    assert preview["requires_cad"] is False

def test_xml_preview_and_export_are_revisioned(tmp_path,tiny_workspace):
    dst,_=tiny_workspace; client=TestClient(create_app(Settings(data_dir=tmp_path/"data"))); opened=client.post("/api/workspaces/open",json={"dst_path":str(dst)}).json(); xml=DstCodec().decode_file(dst).decode().replace("平面</AcSmProp>","导入标题</AcSmProp>")
    destination=tmp_path/"export.dst"; payload={"base_revision_id":opened["revision_id"],"xml":xml,"destination":str(destination)}
    preview=client.post(f"/api/workspaces/{opened['id']}/xml/import/preview",json=payload).json(); assert any(item["type"]=="sheet_changed" for item in preview["changes"])
    payload["destination_revision_id"]=preview["destination_revision_id"]; job=client.post(f"/api/workspaces/{opened['id']}/xml/export-dst",json=payload).json(); assert job["status"]=="SUCCEEDED" and destination.is_file()
    assert (tmp_path/".dst-manager"/"revisions"/job["id"]).is_dir()


def test_xml_export_requires_destination_baseline_from_preview(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    destination = tmp_path / "frozen-export.dst"
    xml = DstCodec().decode_file(dst).decode()
    payload = {
        "base_revision_id": opened["revision_id"],
        "xml": xml,
        "destination": str(destination),
    }

    preview = client.post(
        f"/api/workspaces/{opened['id']}/xml/import/preview",
        json=payload,
    ).json()
    assert preview["destination_revision_id"] == "MISSING"

    missing_baseline = client.post(
        f"/api/workspaces/{opened['id']}/xml/export-dst",
        json=payload,
    )
    assert missing_baseline.status_code == 409
    assert missing_baseline.json()["code"] == "DESTINATION_BASELINE_REQUIRED"

    payload["destination_revision_id"] = preview["destination_revision_id"]
    exported = client.post(
        f"/api/workspaces/{opened['id']}/xml/export-dst",
        json=payload,
    )
    assert exported.status_code == 200
    assert exported.json()["status"] == "SUCCEEDED"
    assert destination.is_file()


def test_revision_restore_creates_new_revision_and_keeps_history(tmp_path, tiny_workspace):
    dst, sheet_id = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {"base_revision_id": opened["revision_id"], "commands": [{"type": "update_sheet_properties", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}]}
    changed = client.post(f"/api/workspaces/{opened['id']}/changes/execute", json=payload).json()
    assert changed["status"] == "SUCCEEDED"
    revision = client.get("/api/revisions", params={"workspace_id": opened["id"]}).json()[0]
    current = client.get(f"/api/workspaces/{opened['id']}").json()
    preview = client.get(f"/api/workspaces/{opened['id']}/revisions/{revision['id']}/restore-preview").json()
    assert preview["executable"] is True
    assert preview["files"] == [preview["files"][0] | {"path": dst.name, "action": "replace", "conflict": False}]
    restored = client.post(
        f"/api/workspaces/{opened['id']}/revisions/{revision['id']}/restore",
        json={"base_revision_id": current["revision_id"]},
    ).json()
    assert restored["status"] == "SUCCEEDED"
    reopened = client.get(f"/api/workspaces/{opened['id']}").json()
    assert reopened["sheet_set"]["subsets"][0]["sheets"][0]["custom_properties"]["比例"] == "1:100"
    revisions = client.get("/api/revisions", params={"workspace_id": opened["id"]}).json()
    assert len(revisions) == 2
    restore_revision = next(item for item in revisions if item["id"].startswith("restore-"))
    reverse_preview = client.get(f"/api/workspaces/{opened['id']}/revisions/{restore_revision['id']}/restore-preview").json()
    assert reverse_preview["executable"] is True
    reversed_job = client.post(
        f"/api/workspaces/{opened['id']}/revisions/{restore_revision['id']}/restore",
        json={"base_revision_id": reopened["revision_id"]},
    ).json()
    assert reversed_job["status"] == "SUCCEEDED"
    changed_again = client.get(f"/api/workspaces/{opened['id']}").json()
    assert changed_again["sheet_set"]["subsets"][0]["sheets"][0]["custom_properties"]["比例"] == "1:200"


def test_revision_restore_rejects_changed_current_file(tmp_path, tiny_workspace):
    dst, sheet_id = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {"base_revision_id": opened["revision_id"], "commands": [{"type": "update_sheet_properties", "sheet_id": sheet_id, "custom_properties": {"比例": "1:200"}}]}
    client.post(f"/api/workspaces/{opened['id']}/changes/execute", json=payload)
    revision = client.get("/api/revisions", params={"workspace_id": opened["id"]}).json()[0]
    dst.write_bytes(dst.read_bytes() + b"external-change")
    preview = client.get(f"/api/workspaces/{opened['id']}/revisions/{revision['id']}/restore-preview").json()
    assert preview["executable"] is False
    assert preview["conflicts"] == [dst.name]


def test_property_csv_template_workspace_fields_and_export_are_exact(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))

    template = client.get("/api/custom-properties/template")
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    exported = client.get(f"/api/workspaces/{opened['id']}/custom-properties/export")

    assert template.status_code == 200
    assert template.headers["content-type"].startswith("text/csv; charset=utf-8")
    assert template.content == b"type,name,default_value\r\n"
    assert opened["sheet_set"]["property_definitions"] == [
        {"type": "sheetset", "name": "项目号", "default_value": "P-000"},
        {"type": "sheet", "name": "比例", "default_value": ""},
    ]
    assert opened["sheet_set"]["subsets"][0] | {"sheets": []} == {
        "id": opened["sheet_set"]["subsets"][0]["id"],
        "name": "分组",
        "title": "分组",
        "number_range": "001",
        "display_name": "001 分组",
        "order": 0,
        "sheets": [],
    }
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv; charset=utf-8")
    assert exported.content == (
        "type,name,default_value\r\n"
        "sheetset,项目号,P-000\r\n"
        "sheet,比例,\r\n"
    ).encode()


def test_sheet_property_definition_default_is_stable_across_values_and_sheet_order(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    _add_second_sheet_with_different_scale(dst)
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))

    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    exported_before = client.get(f"/api/workspaces/{opened['id']}/custom-properties/export").content

    assert opened["sheet_set"]["property_definitions"] == [
        {"type": "sheetset", "name": "项目号", "default_value": "P-000"},
        {"type": "sheet", "name": "比例", "default_value": ""},
    ]
    assert exported_before == (
        "type,name,default_value\r\n"
        "sheetset,项目号,P-000\r\n"
        "sheet,比例,\r\n"
    ).encode()

    _reverse_sheet_order(dst)
    reopened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    exported_after = client.get(f"/api/workspaces/{reopened['id']}/custom-properties/export").content

    assert reopened["sheet_set"]["property_definitions"] == opened["sheet_set"]["property_definitions"]
    assert exported_after == exported_before


def test_property_csv_default_initializes_every_existing_sheet(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    _add_second_sheet_with_different_scale(dst)
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()

    result = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import",
        json={
            "base_revision_id": opened["revision_id"],
            "csv": "type,name,default_value\nsheet,专业,燃气\n",
        },
    )

    assert result.status_code == 200
    assert result.json()["status"] == "SUCCEEDED"
    reopened = client.get(f"/api/workspaces/{opened['id']}").json()
    sheets = reopened["sheet_set"]["subsets"][0]["sheets"]
    assert [sheet["custom_properties"]["专业"] for sheet in sheets] == ["燃气", "燃气"]
    assert {item["name"]: item["default_value"] for item in reopened["sheet_set"]["property_definitions"]}[
        "专业"
    ] == ""


def test_property_csv_import_preview_executes_domain_commands_and_skips_repeat(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    csv_text = "type,name,default_value\nsheet,专业,燃气\nsheetset,项目阶段,施工图\n"
    payload = {"base_revision_id": opened["revision_id"], "csv": csv_text}

    preview = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import/preview",
        json=payload,
    ).json()

    assert preview["executable"] is True
    assert preview["requires_cad"] is False
    assert [change["action"] for change in preview["changes"]] == ["add", "add"]
    assert preview["commands"] == [
        {"type": "add_custom_property", "property_type": "sheet", "name": "专业", "default_value": "燃气"},
        {"type": "add_custom_property", "property_type": "sheetset", "name": "项目阶段", "default_value": "施工图"},
    ]

    job = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import",
        json=payload,
    ).json()
    assert job["status"] == "SUCCEEDED"
    assert (dst.parent / ".dst-manager" / "revisions" / job["id"] / "before" / dst.name).is_file()
    reopened = client.get(f"/api/workspaces/{opened['id']}").json()
    assert reopened["revision_id"] != opened["revision_id"]
    assert reopened["sheet_set"]["custom_properties"]["项目阶段"] == "施工图"
    assert reopened["sheet_set"]["subsets"][0]["sheets"][0]["custom_properties"]["专业"] == "燃气"

    repeated = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import/preview",
        json={"base_revision_id": reopened["revision_id"], "csv": csv_text},
    ).json()
    assert repeated["executable"] is True
    assert repeated["commands"] == []
    assert [change["action"] for change in repeated["changes"]] == ["skip", "skip"]


def test_property_csv_repeated_import_is_stable_noop_without_job_revision_or_lock(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app, raise_server_exceptions=False)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    csv_text = "type,name,default_value\nsheet,专业,燃气\n"
    first = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import",
        json={"base_revision_id": opened["revision_id"], "csv": csv_text},
    ).json()
    current = client.get(f"/api/workspaces/{opened['id']}").json()
    before_file = (dst.stat().st_mtime_ns, dst.read_bytes())
    with app.state.service.database.engine.connect() as connection:
        before_counts = (
            connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one(),
            connection.exec_driver_sql("SELECT COUNT(*) FROM document_revisions").scalar_one(),
        )

    assert first["status"] == "SUCCEEDED"
    expected = {
        "id": None,
        "workspace_id": opened["id"],
        "status": "SUCCEEDED",
        "revision_id": current["revision_id"],
        "no_op": True,
    }
    for _ in range(2):
        response = client.post(
            f"/api/workspaces/{opened['id']}/custom-properties/import",
            json={"base_revision_id": current["revision_id"], "csv": csv_text},
        )
        assert response.status_code == 200
        assert response.json() == expected

    with app.state.service.database.engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one(),
            connection.exec_driver_sql("SELECT COUNT(*) FROM document_revisions").scalar_one(),
        ) == before_counts
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0
    assert (dst.stat().st_mtime_ns, dst.read_bytes()) == before_file

    next_write = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import",
        json={
            "base_revision_id": current["revision_id"],
            "csv": "type,name,default_value\nsheetset,项目阶段,施工图\n",
        },
    )
    assert next_write.status_code == 200
    assert next_write.json()["status"] == "SUCCEEDED"


def test_delete_custom_property_uses_revisioned_dst_publish(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {
        "base_revision_id": opened["revision_id"],
        "commands": [
            {
                "type": "delete_custom_property",
                "property_type": "sheet",
                "name": "比例",
            }
        ],
    }

    preview = client.post(
        f"/api/workspaces/{opened['id']}/changes/preview",
        json=payload,
    ).json()
    job = client.post(
        f"/api/workspaces/{opened['id']}/changes/execute",
        json=payload,
    ).json()

    assert preview["executable"] is True
    assert preview["requires_cad"] is False
    assert job["status"] == "SUCCEEDED"
    assert (dst.parent / ".dst-manager" / "revisions" / job["id"] / "before" / dst.name).is_file()
    reopened = client.get(f"/api/workspaces/{opened['id']}").json()
    assert {item["name"] for item in reopened["sheet_set"]["property_definitions"]} == {"项目号"}
    assert reopened["sheet_set"]["subsets"][0]["sheets"][0]["custom_properties"] == {}


@pytest.mark.parametrize(
    ("csv_text", "code", "line"),
    [
        ("name,type,default_value\n比例,sheet,1:100\n", "CUSTOM_PROPERTY_CSV_HEADER_INVALID", 1),
        ("type,name,default_value\nsheet,比例\n", "CUSTOM_PROPERTY_CSV_COLUMNS_INVALID", 2),
        ("type,name,default_value\nsubset,编号,1\n", "CUSTOM_PROPERTY_TYPE_INVALID", 2),
        ("type,name,default_value\nsheet,,1\n", "CUSTOM_PROPERTY_NAME_EMPTY", 2),
        ("type,name,default_value\nsheet,go,1\nsheet,Go,2\n", "CUSTOM_PROPERTY_NAME_DUPLICATE", 3),
        ("type,name,default_value\nsheet,go,1\nsheetset,GO,2\n", "CUSTOM_PROPERTY_TYPE_CONFLICT", 3),
        ("type,name,default_value\nsheetset,比例,1\n", "CUSTOM_PROPERTY_TYPE_CONFLICT", 2),
    ],
)
def test_property_csv_preview_returns_blocking_line_diagnostics(tmp_path, tiny_workspace, csv_text, code, line):
    dst, _ = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()

    preview = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import/preview",
        json={"base_revision_id": opened["revision_id"], "csv": csv_text},
    )

    assert preview.status_code == 200
    assert preview.json()["executable"] is False
    assert preview.json()["diagnostics"][0]["code"] == code
    assert preview.json()["diagnostics"][0]["line"] == line


def test_property_csv_preview_preserves_physical_line_after_blank_record(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()

    preview = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import/preview",
        json={
            "base_revision_id": opened["revision_id"],
            "csv": "type,name,default_value\n\nsheet,专业,燃气\n",
        },
    ).json()

    assert preview["changes"][0]["line"] == 3


def test_property_csv_rejects_invalid_xml_value_at_logical_record_start_without_writing(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app, raise_server_exceptions=False)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {
        "base_revision_id": opened["revision_id"],
        "csv": (
            'type,name,default_value\r\n'
            'sheet,说明,"第一行\r\n第二行"\r\n'
            'sheet,专业,"燃\x00气"\r\n'
        ),
    }
    before = (dst.stat().st_mtime_ns, dst.read_bytes())

    preview = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import/preview",
        json=payload,
    )

    assert preview.status_code == 200
    assert preview.json()["executable"] is False
    assert preview.json()["diagnostics"] == [
        {
            "code": "CUSTOM_PROPERTY_VALUE_INVALID",
            "severity": "error",
            "message": "自定义属性值包含 XML 1.0 禁止字符",
            "line": 4,
        },
    ]
    execution = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import",
        json=payload,
    )
    assert execution.status_code == 400
    assert execution.json()["code"] == "PLAN_INVALID"
    with app.state.service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM document_revisions").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0
    assert (dst.stat().st_mtime_ns, dst.read_bytes()) == before


def test_direct_property_definition_command_rejects_invalid_xml_value_without_writing(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app, raise_server_exceptions=False)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {
        "base_revision_id": opened["revision_id"],
        "commands": [
            {
                "type": "add_custom_property",
                "property_type": "sheet",
                "name": "专业",
                "default_value": "燃\x00气",
            },
        ],
    }
    before = (dst.stat().st_mtime_ns, dst.read_bytes())

    preview = client.post(
        f"/api/workspaces/{opened['id']}/changes/preview",
        json=payload,
    )

    assert preview.status_code == 200
    assert preview.json()["executable"] is False
    assert [item["code"] for item in preview.json()["diagnostics"]] == ["CUSTOM_PROPERTY_VALUE_INVALID"]
    execution = client.post(
        f"/api/workspaces/{opened['id']}/changes/execute",
        json=payload,
    )
    assert execution.status_code == 400
    assert execution.json()["code"] == "PLAN_INVALID"
    with app.state.service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM document_revisions").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0
    assert (dst.stat().st_mtime_ns, dst.read_bytes()) == before


def test_property_csv_preview_merges_main_dom_diagnostics_and_blocks_execution(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    xml = DstCodec().decode_file(dst).replace(
        b'<AcSmProp propname="Flags" vt="3">2</AcSmProp>',
        b'<AcSmProp propname="Flags" vt="3">9</AcSmProp>',
        1,
    )
    DstCodec().encode_file(xml, dst)
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app, raise_server_exceptions=False)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {
        "base_revision_id": opened["revision_id"],
        "csv": "type,name,default_value\nsheet,专业,燃气\n",
    }
    before = (dst.stat().st_mtime_ns, dst.read_bytes())

    preview = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import/preview",
        json=payload,
    )

    assert preview.status_code == 200
    assert preview.json()["executable"] is False
    assert preview.json()["requires_cad"] is False
    assert preview.json()["affected_files"] == [str(dst)]
    assert preview.json()["changes"] == [
        {
            "line": 2,
            "action": "add",
            "type": "sheet",
            "name": "专业",
            "default_value": "燃气",
            "affected_sheet_count": 1,
        }
    ]
    assert [item["code"] for item in preview.json()["diagnostics"]] == ["CUSTOM_PROPERTY_FLAGS_INVALID"]

    execution = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import",
        json=payload,
    )
    assert execution.status_code == 400
    assert execution.json()["code"] == "PLAN_INVALID"
    with app.state.service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM document_revisions").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM workspace_write_locks").scalar_one() == 0
    assert (dst.stat().st_mtime_ns, dst.read_bytes()) == before


def test_property_csv_api_reports_unpaired_surrogate_as_stable_encoding_diagnostic(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    app = create_app(Settings(data_dir=tmp_path / "data"))
    client = TestClient(app, raise_server_exceptions=False)
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    payload = {
        "base_revision_id": opened["revision_id"],
        "csv": "type,name,default_value\nsheet,\ud800,x\n",
    }

    preview = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import/preview",
        content=json.dumps(payload, ensure_ascii=True).encode(),
        headers={"content-type": "application/json"},
    )

    assert preview.status_code == 200
    assert preview.json()["executable"] is False
    assert preview.json()["diagnostics"] == [
        {
            "code": "CUSTOM_PROPERTY_CSV_ENCODING_INVALID",
            "severity": "error",
            "message": "CSV 必须使用 UTF-8 编码",
            "line": None,
        }
    ]
    execution = client.post(
        f"/api/workspaces/{opened['id']}/custom-properties/import",
        content=json.dumps(payload, ensure_ascii=True).encode(),
        headers={"content-type": "application/json"},
    )
    assert execution.status_code == 400
    assert execution.json()["code"] == "PLAN_INVALID"
    with app.state.service.database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0


def test_property_csv_writes_require_current_base_revision(tmp_path, tiny_workspace):
    dst, _ = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    path = f"/api/workspaces/{opened['id']}/custom-properties/import"

    missing = client.post(path, json={"csv": "type,name,default_value\n"})
    stale = client.post(
        path,
        json={"base_revision_id": "stale", "csv": "type,name,default_value\nsheet,专业,燃气\n"},
    )

    assert missing.status_code == 422
    assert stale.status_code == 409
    assert stale.json()["code"] == "REVISION_CONFLICT"


@pytest.mark.parametrize(
    "command",
    [
        {"type": "move_sheet", "sheet_id": "sheet"},
        {"type": "reorder_sheet", "sheet_id": "sheet"},
        {"type": "renumber_sheets", "subset_id": "subset"},
        {"type": "update_sheet", "sheet_id": "sheet", "number": "999"},
        {"type": "update_sheet", "sheet_id": "sheet", "title": "手工标题"},
        {"type": "update_sheet", "sheet_id": "sheet", "custom_properties": {"比例": "1:500"}},
    ],
)
def test_legacy_commands_are_immediately_unsupported_without_partial_commit(tmp_path, tiny_workspace, command):
    dst, _ = tiny_workspace
    before = dst.read_bytes()
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()

    response = client.post(
        f"/api/workspaces/{opened['id']}/changes/preview",
        json={
            "base_revision_id": opened["revision_id"],
            "commands": [
                {"type": "update_sheet_set", "name": "不得提交"},
                command,
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "COMMAND_UNSUPPORTED"
    assert dst.read_bytes() == before


@pytest.mark.parametrize(
    ("command", "code"),
    [
        (
            {
                "type": "insert_sheet",
                "target_subset_id": "subset-id",
                "ordinal": 0,
                "source": {"type": "existing_snapshot", "file": "drawing", "layout": "001 平面"},
            },
            "SHEET_POSITION_INVALID",
        ),
        (
            {
                "type": "insert_subset",
                "ordinal": 2,
                "title": "新子集",
                "source": {"type": "template_layout", "file": "drawing", "layout": "001 平面"},
            },
            "SUBSET_POSITION_INVALID",
        ),
    ],
)
def test_controlled_insert_commands_report_ordinal_boundaries(tmp_path, tiny_workspace, command, code):
    dst, _ = tiny_workspace
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    opened = client.post("/api/workspaces/open", json={"dst_path": str(dst)}).json()
    subset_id = opened["sheet_set"]["subsets"][0]["id"]
    command = {
        **command,
        "target_subset_id": subset_id if command["type"] == "insert_sheet" else command.get("target_subset_id"),
        "source": {**command["source"], "file": str(dst.parent / "A.dwg")},
    }

    preview = client.post(
        f"/api/workspaces/{opened['id']}/changes/preview",
        json={"base_revision_id": opened["revision_id"], "commands": [command]},
    ).json()

    assert preview["executable"] is False
    assert preview["diagnostics"][0]["code"] == code
