"""已发布标准复制为独立草稿的 HTTP 契约。"""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from dst_manager.config import Settings
from dst_manager.interfaces.api import create_app

SOURCE_ID = "123e4567-e89b-42d3-a456-426614174101"
TARGET_ID = "123e4567-e89b-42d3-a456-426614174102"


@pytest.fixture
def source(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    store = client.app.state.service.standard_store
    document = {
        "schema_version": 4, "standard_id": SOURCE_ID, "name": "原标准",
        "description": "模板说明", "published_at": 1_800_000_000_123,
        "supported_cad_versions": ["2020"], "properties": [],
        "dwg_naming": {"segments": [{"system_field": "subset.name"}]},
        "numbering": {"sequence_field": "subset.sequence", "digits": 3},
        "assets": [{"asset_id": "layout", "kind": "layout-template", "file": "assets/布局.dwg", "paper_layouts": ["A2"]}],
    }
    root = store.published_root / SOURCE_ID
    (root / "assets").mkdir(parents=True)
    (root / "document.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    file = root / "assets" / "布局.dwg"
    file.write_bytes(b"dwg-template")
    request = copy.deepcopy(document)
    request.update(standard_id=TARGET_ID, name="复制草稿", published_at=None)
    body = {"draft_id": "copied", "source_standard_id": SOURCE_ID, "document": request}
    return client, store, file, body


def test_copy_request_creates_files_and_does_not_persist_source_identity(source):
    client, store, file, body = source
    response = client.post("/api/standards/drafts", json=body)
    assert response.status_code == 200, response.text
    document = response.json()["document"]
    assert document["standard_id"] == TARGET_ID
    assert document["published_at"] is None
    assert document["assets"] == body["document"]["assets"]
    assert "source_standard_id" not in document
    copied = store.drafts_root / "copied" / "assets" / "布局.dwg"
    assert copied.read_bytes() == file.read_bytes()
    assert not copied.samefile(file)
    assert client.get("/api/standards/drafts/copied").json()["document"] == document


@pytest.mark.parametrize("failure,code,status", [
    ("missing-standard", "STANDARD_ID_NOT_FOUND", 404),
    ("invalid-id", "STANDARD_ID_INVALID", 422),
    ("missing-file", "STANDARD_ASSET_FILE_MISSING", 422),
    ("copy-error", "STANDARD_ASSET_COPY_FAILED", 422),
])
def test_copy_failures_return_stable_codes_and_leave_no_draft(source, monkeypatch, failure, code, status):
    client, store, file, body = source
    if failure == "missing-standard":
        body["source_standard_id"] = TARGET_ID
    elif failure == "invalid-id":
        body["source_standard_id"] = "../outside"
    elif failure == "missing-file":
        file.unlink()
    else:
        def fail_copy(*args, **kwargs):
            raise OSError("模拟模板读取失败")
        monkeypatch.setattr("shutil.copyfile", fail_copy)
    response = client.post("/api/standards/drafts", json=body)
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert not (store.drafts_root / "copied").exists()
