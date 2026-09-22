"""标准管理 API 契约（PLAN-DM-035 Task 6 / PLAN-DM-038 Task 4）。

覆盖：已发布版本 PUT 稳定 409 ``STANDARD_VERSION_IMMUTABLE``、草稿全生命周期、
草稿可保存语义未完成内容但发布被门禁拒绝、发布 warning 随响应返回、受信扩展
依赖缺失时发布以 409 ``STANDARD_DEPENDENCY_MISSING`` 拒绝、包导入与导出、
资产检查诊断透传。路由只做请求/响应转换，业务在应用层。
"""

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from yaml import safe_dump

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.extensions.builtin.index import BuiltinExtensionEntry
from dst_manager.interfaces.api import create_app

DRAFT_DOCUMENT = {
    "schema_version": 1,
    "standard_id": "szmedi.gas",
    "version": "0.1.0",
    "name": "市政燃气施工图",
    "supported_cad_versions": ["2016", "2020"],
    "properties": [
        {
            "property_id": "prop-major",
            "name": "专业",
            "scope": "sheetset",
            "kind": "enum",
            "required": True,
            "enum_items": [{"item_id": "enum-gas", "value": "燃气"}],
        },
        {
            "property_id": "prop-code",
            "name": "专业代码",
            "scope": "sheetset",
            "kind": "mapping",
            "source_property_id": "prop-major",
            "mapping": [{"item_id": "enum-gas", "value": "RQ"}],
            "confirmed_source_items": [["enum-gas", "燃气"]],
        },
    ],
    "dwg_naming": {
        "segments": [
            {"system_field": "subset.scope"},
            {"literal": " "},
            {"system_field": "subset.name"},
        ]
    },
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


def incomplete_mapping_document() -> dict:
    """有效夹具的派生副本：映射目标留空，草稿可保存但不可发布。"""
    document = copy.deepcopy(DRAFT_DOCUMENT)
    document["properties"][1]["mapping"][0]["value"] = ""
    return document


@pytest.fixture
def service(tmp_path: Path) -> DstManagerService:
    return DstManagerService(Settings(data_dir=tmp_path / "data"))


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
        "diagnostics": [],
    }


def test_incomplete_mapping_draft_saves_but_does_not_publish(service) -> None:
    saved = service.create_standard_draft(incomplete_mapping_document())
    with pytest.raises(ApplicationError) as exc:
        service.publish_standard(saved["draft_id"])
    assert exc.value.code == "STANDARD_MAPPING_TARGET_EMPTY"
    assert service.get_standard_draft(saved["draft_id"])


def test_publish_rejects_draft_with_semantic_schema_error(tmp_path: Path) -> None:
    """草稿门禁放行、发布门禁拒绝的语义错误必须以稳定 422 返回，而不是 500。"""
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")), raise_server_exceptions=False)
    document = copy.deepcopy(DRAFT_DOCUMENT)
    document["properties"][0]["name"] = ""
    make_draft(client, document, "draft-noname")
    response = client.post("/api/standards/drafts/draft-noname/publish")
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_PROPERTY_NAME_INVALID"
    assert client.get("/api/standards/drafts/draft-noname").status_code == 200


def test_incomplete_mapping_draft_http_publish_returns_422(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, incomplete_mapping_document(), "draft-incomplete")
    response = client.post("/api/standards/drafts/draft-incomplete/publish")
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_MAPPING_TARGET_EMPTY"
    # 草稿目录未被移动，也没有产生已发布标准。
    assert client.get("/api/standards/drafts/draft-incomplete").status_code == 200
    assert [
        item for item in client.get("/api/standards").json() if item["status"] == "published"
    ] == []


def test_publish_returns_mapping_confirmation_warning(tmp_path: Path) -> None:
    document = copy.deepcopy(DRAFT_DOCUMENT)
    # 枚举改名：enum_item_id 不变，映射目标保留，但进入待确认 warning。
    document["properties"][0]["enum_items"][0]["value"] = "城镇燃气"
    client = make_client(tmp_path)
    make_draft(client, document, "draft-renamed")
    response = client.post("/api/standards/drafts/draft-renamed/publish")
    assert response.status_code == 200, response.text
    assert response.json()["diagnostics"] == [
        {
            "code": "STANDARD_MAPPING_CONFIRMATION_REQUIRED",
            "severity": "warning",
            "message": "映射属性 'prop-code' 的源枚举列表已变化，请确认映射",
            "property_id": "prop-code",
            "segment_index": None,
        }
    ]


def test_publish_rejects_legacy_rules_document(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    legacy = copy.deepcopy(DRAFT_DOCUMENT)
    legacy["properties"] = [{"name": "专业名称", "scope": "sheetset"}]
    legacy["rules"] = [
        {"rule_id": "r1", "kind": "required", "target": "sheetset.专业名称"}
    ]
    response = client.post(
        "/api/standards/drafts", json={"draft_id": "legacy", "document": legacy}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_PROPERTY_ID_INVALID"


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
    assert body["document"]["dwg_naming"] == {
        "segments": [
            {"system_field": "subset.scope"},
            {"literal": " "},
            {"system_field": "subset.name"},
        ]
    }
    assert body["document"]["properties"] and {
        (item["name"], item["scope"]) for item in body["document"]["properties"]
    } == {("比例", "sheet"), ("项目号", "sheetset")}
    assert all(item["kind"] == "text" for item in body["document"]["properties"])
    assert all(
        item["property_id"] and item["previous_names"] == []
        for item in body["document"]["properties"]
    )


def test_dst_import_endpoint_rejects_invalid_source(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    broken = tmp_path / "broken.dst"
    broken.write_bytes(b"not a dst")
    response = client.post("/api/standards/drafts/from-dst", json={"dst_path": str(broken)})
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_DST_IMPORT_INVALID"
