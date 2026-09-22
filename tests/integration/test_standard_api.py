"""标准管理 API 契约（PLAN-DM-035 Task 6）：列表/草稿/发布/导入/导出/资产检查。

覆盖：已发布版本 PUT 稳定 409 ``STANDARD_VERSION_IMMUTABLE``、草稿全生命周期、
受信扩展依赖缺失时发布以 409 ``STANDARD_DEPENDENCY_MISSING`` 拒绝、包导入与
导出、资产检查诊断透传。路由只做请求/响应转换，业务在应用层。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from yaml import safe_dump

from dst_manager.config import Settings
from dst_manager.extensions.builtin.index import BuiltinExtensionEntry
from dst_manager.interfaces.api import create_app

DRAFT_DOCUMENT = {
    "schema_version": 1,
    "standard_id": "szmedi.gas",
    "version": "0.1.0",
    "name": "市政燃气施工图",
    "supported_cad_versions": ["2016", "2020"],
    "properties": [{"name": "专业名称", "scope": "sheetset", "required": True}],
    "rules": [],
    "assets": [],
    "numbering": {"sequence_field": "subset.sequence", "digits": 2},
}

DEPENDENT_DOCUMENT = {
    **DRAFT_DOCUMENT,
    "dependencies": [
        {
            "extension_id": "test.trusted",
            "capability_id": "layout.template.v1",
            "min_version": "1.0.0",
        },
    ],
}


class _NoopExtension:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def make_client(tmp_path: Path, manifest: dict | None = None) -> TestClient:
    kwargs: dict[str, object] = {}
    if manifest is not None:
        manifest_path = tmp_path / "trusted-extension.yaml"
        manifest_path.write_text(safe_dump(manifest), encoding="utf-8")
        kwargs["extension_index"] = [
            BuiltinExtensionEntry(manifest_resource=str(manifest_path), factory=_NoopExtension)
        ]
    return TestClient(create_app(Settings(data_dir=tmp_path / "data"), **kwargs))


def make_draft(client: TestClient, document: dict, draft_id: str) -> None:
    response = client.post(
        "/api/standards/drafts", json={"draft_id": draft_id, "document": document}
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def published_standard(tmp_path: Path) -> TestClient:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")
    response = client.post("/api/standards/drafts/draft-gas/publish")
    assert response.status_code == 200, response.text
    return client


def test_standards_list_returns_published(published_standard: TestClient) -> None:
    entries = published_standard.get("/api/standards").json()
    assert entries == [
        {
            "source": "user",
            "status": "published",
            "standard_id": "szmedi.gas",
            "version": "0.1.0",
            "name": "市政燃气施工图",
            "draft_id": None,
        },
    ]


def test_published_standard_cannot_be_updated(published_standard: TestClient) -> None:
    response = published_standard.put(
        "/api/standards/szmedi.gas/0.1.0", json={"name": "changed"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STANDARD_VERSION_IMMUTABLE"


def test_draft_lifecycle_roundtrip(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")

    detail = client.get("/api/standards/drafts/draft-gas")
    assert detail.status_code == 200
    assert detail.json()["document"]["standard_id"] == "szmedi.gas"

    saved = client.put("/api/standards/szmedi.gas/0.1.0", json=dict(DRAFT_DOCUMENT, name="修订名"))
    assert saved.status_code == 200
    assert client.get("/api/standards/drafts/draft-gas").json()["document"]["name"] == "修订名"

    assert client.delete("/api/standards/drafts/draft-gas").status_code == 200
    assert client.get("/api/standards/drafts/draft-gas").status_code == 404
    assert client.put("/api/standards/szmedi.gas/0.1.0", json=DRAFT_DOCUMENT).status_code == 404


def test_published_detail_includes_dependencies(published_standard: TestClient) -> None:
    detail = published_standard.get("/api/standards/szmedi.gas/0.1.0")
    assert detail.status_code == 200
    body = detail.json()
    assert body["standard_id"] == "szmedi.gas"
    assert body["dependencies"] == []
    assert published_standard.get("/api/standards/absent/1.0.0").status_code == 404


def test_publish_missing_trusted_dependency_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DEPENDENT_DOCUMENT, "draft-dep")
    response = client.post("/api/standards/drafts/draft-dep/publish")
    assert response.status_code == 409
    assert response.json()["code"] == "STANDARD_DEPENDENCY_MISSING"


def test_publish_satisfied_trusted_dependency(tmp_path: Path) -> None:
    manifest = {
        "extension_id": "test.trusted",
        "version": "1.2.0",
        "extension_type": "builtin",
        "host_contract": 1,
        "enabled_by_default": True,
        "name_key": "extensions.trusted.name",
        "description_key": "extensions.trusted.description",
        "required_capabilities": [],
        "provided_capabilities": [
            {"capability_id": "layout.template.v1", "version": "1.0.0"},
        ],
        "actions": [],
        "settings_schema": 1,
    }
    client = make_client(tmp_path, manifest)
    make_draft(client, DEPENDENT_DOCUMENT, "draft-dep")
    response = client.post("/api/standards/drafts/draft-dep/publish")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "standard_id": "szmedi.gas",
        "version": "0.1.0",
        "name": "市政燃气施工图",
    }


def test_invalid_draft_document_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/standards/drafts",
        json={"draft_id": "bad", "document": {"schema_version": 99}},
    )
    assert response.status_code == 422
    assert response.json()["code"].startswith("STANDARD_")


def test_export_and_import_package_roundtrip(published_standard: TestClient, tmp_path) -> None:
    exported = published_standard.get("/api/standards/szmedi.gas/0.1.0/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    package = tmp_path / "copy.dststandard"
    package.write_bytes(exported.content)

    other = make_client(tmp_path / "second")
    imported = other.post("/api/standards/import", json={"path": str(package)})
    assert imported.status_code == 200
    assert imported.json()["standard_id"] == "szmedi.gas"

    collision = other.post("/api/standards/import", json={"path": str(package)})
    assert collision.status_code == 409
    assert collision.json()["code"] == "STANDARD_VERSION_EXISTS"


def test_missing_export_target_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/api/standards/absent/1.0.0/export").status_code == 404


def test_asset_inspection_endpoint(tmp_path: Path, monkeypatch) -> None:
    from dst_manager.application.service import DstManagerService

    def fake_layout_names(self, file_path, cad_version):
        return {"layouts": ["Model", "A2 "], "cached": False, "file_hash": "0" * 64}

    monkeypatch.setattr(DstManagerService, "get_layout_names", fake_layout_names)
    client = make_client(tmp_path)
    make_draft(
        client,
        {
            **DRAFT_DOCUMENT,
            "assets": [
                {
                    "asset_id": "layouts",
                    "kind": "layout-template",
                    "files": [{"path": "assets/A2.dwg", "role": "A2"}],
                },
            ],
        },
        "draft-layouts",
    )
    assets = tmp_path / "data" / "standards" / "user" / "drafts" / "draft-layouts" / "assets"
    assets.mkdir(parents=True)
    (assets / "A2.dwg").write_bytes(b"fake dwg")

    response = client.post(
        "/api/standards/drafts/draft-layouts/assets/layouts/inspect",
        json={"cad_version": "2020"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "layouts"
    assert body["kind"] == "layout-template"
    assert body["diagnostics"][0]["code"] == "STANDARD_LAYOUT_NAME_MISMATCH"
    assert body["diagnostics"][0]["severity"] == "error"


def test_dst_import_endpoint(tmp_path: Path, tiny_workspace) -> None:
    client = make_client(tmp_path)
    dst, _sheet_id = tiny_workspace
    response = client.post("/api/standards/drafts/from-dst", json={"dst_path": str(dst)})
    assert response.status_code == 200
    body = response.json()
    assert body["subsets"] == []
    assert body["external_paths"] == []
    assert body["document"]["properties"] and {
        (item["name"], item["scope"]) for item in body["document"]["properties"]
    } == {("比例", "sheet"), ("项目号", "sheetset")}


def test_dst_import_endpoint_rejects_invalid_source(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    broken = tmp_path / "broken.dst"
    broken.write_bytes(b"not a dst")
    response = client.post("/api/standards/drafts/from-dst", json={"dst_path": str(broken)})
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_DST_IMPORT_INVALID"
