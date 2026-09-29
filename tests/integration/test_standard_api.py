"""标准管理 API 契约（PLAN-DM-035 Task 6 / PLAN-DM-038 Task 4）。

覆盖：已发布版本 PUT 稳定 409 ``STANDARD_VERSION_IMMUTABLE``、草稿全生命周期、
草稿可保存语义未完成内容但发布被门禁拒绝、发布 warning 随响应返回、受信扩展
依赖缺失时发布以 409 ``STANDARD_DEPENDENCY_MISSING`` 拒绝、包导入与导出、
资产检查诊断透传。路由只做请求/响应转换，业务在应用层。
"""

import concurrent.futures
import copy
import io
import json
import os
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from yaml import safe_dump

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.extensions.builtin.index import BuiltinExtensionEntry
from dst_manager.infrastructure.standards.store import StandardStoreError
from dst_manager.interfaces.api import create_app

DRAFT_DOCUMENT = {
    "schema_version": 3,
    "standard_id": "123e4567-e89b-42d3-a456-426614174101",
    "published_at": None,
    "description": "标准描述原文",
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

STANDARD_ID = "123e4567-e89b-42d3-a456-426614174101"
SECOND_STANDARD_ID = "123e4567-e89b-42d3-a456-426614174102"
THIRD_STANDARD_ID = "123e4567-e89b-42d3-a456-426614174103"


def published_document(
    standard_id: str,
    *,
    name: str = "市政燃气施工图",
    description: str = "标准描述原文",
    published_at: int = 1_800_000_000_123,
) -> dict:
    document = copy.deepcopy(DRAFT_DOCUMENT)
    document.update(
        standard_id=standard_id,
        name=name,
        description=description,
        published_at=published_at,
    )
    return document

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
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source"] == "user"
    assert entry["status"] == "published"
    assert entry["standard_id"] == STANDARD_ID
    assert entry["name"] == "市政燃气施工图"
    assert entry["description"] == "标准描述原文"
    assert isinstance(entry["published_at"], int)
    assert "version" not in entry


def test_published_standard_cannot_be_updated(published_standard: TestClient) -> None:
    """已发布标准不可原地修改：身份路由不再提供写入入口，文档零变更。"""
    before = published_standard.get(f"/api/standards/{STANDARD_ID}").json()["document"]
    identity_write = published_standard.put(
        f"/api/standards/{STANDARD_ID}", json={"name": "changed"}
    )
    assert identity_write.status_code == 405
    missing_draft = published_standard.put(
        "/api/standards/drafts/absent", json={"document": {"name": "changed"}}
    )
    assert missing_draft.status_code == 404
    after = published_standard.get(f"/api/standards/{STANDARD_ID}").json()["document"]
    assert after == before


def test_draft_lifecycle_roundtrip(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")

    detail = client.get("/api/standards/drafts/draft-gas")
    assert detail.status_code == 200
    assert detail.json()["document"]["standard_id"] == STANDARD_ID

    saved = client.put(
        "/api/standards/drafts/draft-gas",
        json={"document": dict(DRAFT_DOCUMENT, name="修订名")},
    )
    assert saved.status_code == 200, saved.text
    assert client.get("/api/standards/drafts/draft-gas").json()["document"]["name"] == "修订名"

    assert client.delete("/api/standards/drafts/draft-gas").status_code == 200
    assert client.get("/api/standards/drafts/draft-gas").status_code == 404
    assert (
        client.put(
            "/api/standards/drafts/draft-gas", json={"document": DRAFT_DOCUMENT}
        ).status_code
        == 404
    )


def test_saving_v3_draft_explicitly_upgrades_response_and_disk_to_v4(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-v3")
    document_path = (
        client.app.state.service.standard_store.drafts_root
        / "draft-v3"
        / "document.json"
    )
    original_bytes = document_path.read_bytes()
    original_mtime_ns = document_path.stat().st_mtime_ns

    opened = client.get("/api/standards/drafts/draft-v3")
    assert opened.status_code == 200
    assert opened.json()["document"]["schema_version"] == 3
    assert document_path.read_bytes() == original_bytes
    assert document_path.stat().st_mtime_ns == original_mtime_ns

    edited = copy.deepcopy(DRAFT_DOCUMENT)
    edited["name"] = "显式保存后升级"
    saved = client.put(
        "/api/standards/drafts/draft-v3", json={"document": edited}
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["document"]["schema_version"] == 4
    assert json.loads(document_path.read_text(encoding="utf-8"))["schema_version"] == 4


def test_saving_v3_draft_with_cascade_fields_is_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-v3")
    edited = copy.deepcopy(DRAFT_DOCUMENT)
    edited["properties"].append(
        {
            "property_id": "prop-zone",
            "name": "片区",
            "scope": "sheetset",
            "kind": "cascade",
            "source_property_id": "prop-major",
            "cascade_options": [
                {"source_item_id": "enum-gas", "values": ["北区"]}
            ],
        }
    )

    response = client.put(
        "/api/standards/drafts/draft-v3", json={"document": edited}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_CASCADE_SCHEMA_UNSUPPORTED"


def test_v4_cascade_survives_draft_publish_export_preflight_and_import(
    tmp_path: Path,
) -> None:
    document = copy.deepcopy(DRAFT_DOCUMENT)
    document["schema_version"] = 4
    document["properties"].append(
        {
            "property_id": "prop-zone",
            "name": "片区",
            "scope": "sheetset",
            "kind": "cascade",
            "source_property_id": "prop-major",
            "cascade_options": [
                {"source_item_id": "enum-gas", "values": ["北区", "南区"]}
            ],
        }
    )
    client = make_client(tmp_path)
    make_draft(client, document, "draft-v4")

    saved = client.put(
        "/api/standards/drafts/draft-v4", json={"document": document}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["document"]["properties"][-1]["cascade_options"] == [
        {"source_item_id": "enum-gas", "values": ["北区", "南区"]}
    ]
    published = client.post("/api/standards/drafts/draft-v4/publish")
    assert published.status_code == 200, published.text

    details = client.get(f"/api/standards/{STANDARD_ID}")
    assert details.status_code == 200
    assert details.json()["document"]["schema_version"] == 4
    package = tmp_path / "cascade.dststandard"
    package.write_bytes(
        client.get(f"/api/standards/{STANDARD_ID}/export").content
    )
    with zipfile.ZipFile(package) as archive:
        exported_document = json.loads(archive.read("manifest.json"))
    expected_options = exported_document["properties"][-1]["cascade_options"]
    assert expected_options == [
        {"source_item_id": "enum-gas", "values": ["北区", "南区"]}
    ]

    other = make_client(tmp_path / "other")
    preview = other.post(
        "/api/standards/import-previews", json={"path": str(package)}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is True
    imported = other.post(
        "/api/standards/import", json={"preview_id": preview.json()["preview_id"]}
    )
    assert imported.status_code == 200, imported.text
    imported_document = other.get(f"/api/standards/{STANDARD_ID}").json()["document"]
    assert imported_document["schema_version"] == 4
    assert imported_document["properties"][-1]["cascade_options"] == expected_options


def test_published_detail_includes_dependencies(published_standard: TestClient) -> None:
    detail = published_standard.get(f"/api/standards/{STANDARD_ID}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["standard_id"] == STANDARD_ID
    assert body["description"] == "标准描述原文"
    assert isinstance(body["published_at"], int)
    assert "version" not in body
    assert body["dependencies"] == []
    assert published_standard.get("/api/standards/absent/1").status_code == 404


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
    body = response.json()
    assert body["standard_id"] == STANDARD_ID
    assert body["name"] == "市政燃气施工图"
    assert body["description"] == "标准描述原文"
    assert isinstance(body["published_at"], int)
    assert body["diagnostics"] == []


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
    exported = published_standard.get(f"/api/standards/{STANDARD_ID}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    package = tmp_path / "copy.dststandard"
    package.write_bytes(exported.content)
    with zipfile.ZipFile(package) as archive:
        assert json.loads(archive.read("manifest.json"))["schema_version"] == 3

    other = make_client(tmp_path / "second")
    preview = other.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_import"] is True
    assert body["standard_id"] == STANDARD_ID
    assert body["description"] == "标准描述原文"
    assert "version" not in body
    # 预检只复制快照与诊断，不写标准库。
    assert other.get("/api/standards").json() == []

    imported = other.post(
        "/api/standards/import", json={"preview_id": body["preview_id"]}
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["standard_id"] == STANDARD_ID
    assert imported.json()["published_at"] == body["published_at"]
    assert "version" not in imported.json()
    imported_detail = other.get(f"/api/standards/{STANDARD_ID}").json()["document"]
    assert imported_detail["schema_version"] == 3

    # 同一凭证重复确认返回原成功结果，不二次写入。
    repeated = other.post(
        "/api/standards/import", json={"preview_id": body["preview_id"]}
    )
    assert repeated.status_code == 200
    assert repeated.json() == imported.json()
    assert len(other.get("/api/standards").json()) == 1

    # 再预检同一身份：预检以 can_import=false 阻断，确认阶段以 409 拒绝。
    blocked = other.post("/api/standards/import-previews", json={"path": str(package)})
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["can_import"] is False
    assert [item["code"] for item in blocked.json()["diagnostics"]] == [
        "STANDARD_ID_EXISTS"
    ]
    assert blocked.json()["preview_id"] is None
    refreshed = other.post("/api/standards/import-previews", json={"path": str(package)})
    assert refreshed.status_code == 200
    assert other.get("/api/standards").json()[0]["standard_id"] == STANDARD_ID


def test_import_http_rejects_path_body(tmp_path: Path) -> None:
    """服务端不接受绕过预检的路径导入（SPEC-DM-019 §4.1）。"""
    client = make_client(tmp_path)
    package = write_api_package(
        tmp_path / "copy.dststandard",
        {**asset_document("assets/A2.dwg"), "version": 1},
        {"assets/A2.dwg": b"a2"},
    )
    response = client.post("/api/standards/import", json={"path": str(package)})
    assert response.status_code == 422


def test_import_preview_rejects_existing_uuid_without_writing(
    published_standard: TestClient, tmp_path
) -> None:
    """ID 唯一，不再把同一 UUID 的多个整数版本归集为一个标准。"""
    package = write_api_package(
        tmp_path / "copy.dststandard", published_document(STANDARD_ID)
    )
    before = published_standard.get("/api/standards").json()

    preview = published_standard.post(
        "/api/standards/import-previews", json={"path": str(package)}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_import"] is False
    assert body["preview_id"] is None
    assert body["existing_name"] == "市政燃气施工图"
    assert [item["code"] for item in body["diagnostics"]] == ["STANDARD_ID_EXISTS"]
    assert published_standard.get("/api/standards").json() == before


def test_import_preview_reports_name_conflict(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    other = write_api_package(
        tmp_path / "other.dststandard",
        {
            **asset_document("assets/A2.dwg"),
            "standard_id": SECOND_STANDARD_ID,
            "version": 1,
            "name": "市政燃气施工图",
        },
        {"assets/A2.dwg": b"a2"},
    )
    assert client.post("/api/standards/import", json={"path": str(other)}).status_code == 422
    preview = client.post("/api/standards/import-previews", json={"path": str(other)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is True
    confirmed = client.post(
        "/api/standards/import", json={"preview_id": preview.json()["preview_id"]}
    )
    assert confirmed.status_code == 200, confirmed.text

    # 建立第二个同名但不同 ID 的包：预检必须阻断。
    same_name = write_api_package(
        tmp_path / "same-name.dststandard",
        {
            **asset_document("assets/A2.dwg"),
            "standard_id": THIRD_STANDARD_ID,
            "version": 1,
            "name": "  市政燃气施工图  ",
        },
        {"assets/A2.dwg": b"a2"},
    )
    blocked = client.post("/api/standards/import-previews", json={"path": str(same_name)})
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["can_import"] is False
    assert blocked.json()["preview_id"]
    assert blocked.json()["name_conflict"] is True
    assert blocked.json()["existing_name"] == "市政燃气施工图"
    assert [item["code"] for item in blocked.json()["diagnostics"]] == [
        "STANDARD_NAME_CONFLICT"
    ]


def test_import_preview_conflict_after_preview_returns_409(tmp_path: Path) -> None:
    """确认前库状态变化（新增同 UUID）必须在库锁内复核并以 409 拒绝。"""
    client = make_client(tmp_path)
    package = write_api_package(
        tmp_path / "copy.dststandard",
        {**asset_document("assets/A2.dwg"), "version": 1},
        {"assets/A2.dwg": b"a2"},
    )
    preview = client.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.json()["can_import"] is True

    # 预检后由并发写入先占用同一 UUID，再确认：必须 409。
    same_identity = write_api_package(
        tmp_path / "same.dststandard",
        {**asset_document("assets/A2.dwg"), "version": 1},
        {"assets/A2.dwg": b"a2"},
    )
    client.app.state.service.standard_store.import_package(same_identity)

    confirmed = client.post(
        "/api/standards/import", json={"preview_id": preview.json()["preview_id"]}
    )
    assert confirmed.status_code == 409, confirmed.text
    assert confirmed.json()["code"] == "STANDARD_ID_EXISTS"


def test_import_confirms_from_snapshot_after_source_changes(tmp_path: Path) -> None:
    """预检后源文件被替换或删除：确认只消费快照字节。"""
    client = make_client(tmp_path)
    package = write_api_package(
        tmp_path / "copy.dststandard",
        {**asset_document("assets/A2.dwg"), "version": 1},
        {"assets/A2.dwg": b"a2"},
    )
    original = package.read_bytes()
    preview = client.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.json()["can_import"] is True

    package.write_bytes(b"replaced-after-preview")
    confirmed = client.post(
        "/api/standards/import", json={"preview_id": preview.json()["preview_id"]}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["name"] == asset_document("assets/A2.dwg")["name"]
    assert original != package.read_bytes()

    # 另一种情况：预检后源被删，仍可从快照确认。
    second = write_api_package(
        tmp_path / "second.dststandard",
        {
            **asset_document("assets/A2.dwg"),
            "standard_id": THIRD_STANDARD_ID,
            "name": "第二标准",
            "version": 1,
        },
        {"assets/A2.dwg": b"a2"},
    )
    second_preview = client.post(
        "/api/standards/import-previews", json={"path": str(second)}
    )
    second.unlink()
    assert (
        client.post(
            "/api/standards/import",
            json={"preview_id": second_preview.json()["preview_id"]},
        ).status_code
        == 200
    )


def test_import_preview_rejects_corrupt_asset_crc(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    package = write_api_package(
        tmp_path / "corrupt.dststandard",
        {**asset_document("assets/A2.dwg"), "version": 1},
        {"assets/A2.dwg": b"ABCDE"},
    )
    package.write_bytes(package.read_bytes().replace(b"ABCDE", b"ABXDE", 1))

    response = client.post("/api/standards/import-previews", json={"path": str(package)})

    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_PACKAGE_INVALID"
    assert client.app.state.service.import_previews.snapshot_files() == ()


def test_import_preview_conflict_does_not_keep_unusable_snapshot(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    package = write_api_package(
        tmp_path / "duplicate.dststandard",
        {**asset_document("assets/A2.dwg"), "version": 1},
        {"assets/A2.dwg": b"ABCDE"},
    )
    first = client.post("/api/standards/import-previews", json={"path": str(package)})
    assert first.status_code == 200
    confirmed = client.post(
        "/api/standards/import", json={"preview_id": first.json()["preview_id"]}
    )
    assert confirmed.status_code == 200
    before = client.app.state.service.import_previews.snapshot_files()

    blocked = client.post("/api/standards/import-previews", json={"path": str(package)})

    assert blocked.status_code == 200
    assert blocked.json()["can_import"] is False
    assert blocked.json()["preview_id"] is None
    assert blocked.json()["diagnostics"][0]["code"] == "STANDARD_ID_EXISTS"
    assert client.app.state.service.import_previews.snapshot_files() == before


def test_concurrent_confirmation_of_same_preview_returns_same_result(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    package = write_api_package(
        tmp_path / "concurrent.dststandard",
        {**asset_document("assets/A2.dwg"), "version": 1},
        {"assets/A2.dwg": b"ABCDE"},
    )
    service = client.app.state.service
    preview = service.preview_standard_import(package)
    original_import = service.standard_store.import_package
    entered = threading.Event()
    release = threading.Event()

    def delayed_import(path):
        entered.set()
        assert release.wait(timeout=5)
        return original_import(path)

    service.standard_store.import_package = delayed_import
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.confirm_standard_import, preview["preview_id"])
        assert entered.wait(timeout=5)
        second = pool.submit(service.confirm_standard_import, preview["preview_id"])
        time.sleep(0.1)
        release.set()
        results = [first.result(timeout=5), second.result(timeout=5)]

    assert results[0] == results[1]


def test_import_preview_unknown_forged_and_cancelled_credentials(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert (
        client.post("/api/standards/import", json={"preview_id": "forged"}).status_code
        == 404
    )
    assert (
        client.delete("/api/standards/import-previews/forged").status_code == 200
    )

    package = write_api_package(
        tmp_path / "copy.dststandard",
        {**asset_document("assets/A2.dwg"), "version": 1},
        {"assets/A2.dwg": b"a2"},
    )
    preview = client.post("/api/standards/import-previews", json={"path": str(package)})
    preview_id = preview.json()["preview_id"]
    assert client.delete(f"/api/standards/import-previews/{preview_id}").status_code == 200
    cancelled = client.post("/api/standards/import", json={"preview_id": preview_id})
    assert cancelled.status_code == 404
    assert cancelled.json()["code"] == "STANDARD_IMPORT_PREVIEW_NOT_FOUND"
    # 取消后快照已清理，标准库零新增。
    assert client.get("/api/standards").json() == []


def test_import_preview_rejects_bad_sources(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    missing = tmp_path / "absent.dststandard"
    response = client.post("/api/standards/import-previews", json={"path": str(missing)})
    # SPEC-DM-019 §4.3：源不存在属于"包或路径问题"，返回 422（不是 404）
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_IMPORT_SOURCE_NOT_FOUND"

    wrong_suffix = tmp_path / "package.zip"
    wrong_suffix.write_bytes(b"zip")
    response = client.post(
        "/api/standards/import-previews", json={"path": str(wrong_suffix)}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_IMPORT_SOURCE_INVALID"

    broken = tmp_path / "broken.dststandard"
    broken.write_bytes(b"not-a-zip")
    response = client.post("/api/standards/import-previews", json={"path": str(broken)})
    assert response.status_code == 422
    assert response.json()["code"].startswith("STANDARD_PACKAGE")

    monkeypatch.setattr(
        "dst_manager.infrastructure.standards.import_previews.MAX_PACKAGE_SOURCE_BYTES",
        8,
    )
    oversized = tmp_path / "oversized.dststandard"
    oversized.write_bytes(b"x" * 16)
    response = client.post(
        "/api/standards/import-previews", json={"path": str(oversized)}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_IMPORT_SOURCE_TOO_LARGE"
    assert not list((tmp_path / "data" / "tmp").glob("**/*.dststandard"))


def test_versioned_standard_routes_are_removed(tmp_path: Path) -> None:
    """已发布标准通过 UUID 定位，不再接受 ID/整数版本二级路由。"""
    client = make_client(tmp_path)
    assert client.get(f"/api/standards/{STANDARD_ID}/1").status_code == 404
    assert client.get(f"/api/standards/{STANDARD_ID}/1/export").status_code == 404


def test_import_preview_tolerates_unreadable_existing_entry(tmp_path: Path) -> None:
    """同身份已有条目不可读（残留 v1 或损坏）：预检仍 200，按身份冲突阻断而不是 500。"""
    client = make_client(tmp_path)
    official = tmp_path / "data" / "standards" / "official" / STANDARD_ID
    official.mkdir(parents=True)
    (official / "document.json").write_text("{not json", encoding="utf-8")
    package = write_api_package(
        tmp_path / "copy.dststandard", {**DRAFT_DOCUMENT, "version": 1}
    )

    preview = client.post("/api/standards/import-previews", json={"path": str(package)})

    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is False
    assert [item["code"] for item in preview.json()["diagnostics"]] == [
        "STANDARD_ID_EXISTS"
    ]


def test_import_preview_reports_asset_gate_without_writing(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    # 包内文档必须携带合法发布时间与完整资产。
    document = {**asset_document("assets/A2.dwg"), "version": 1}
    package = write_api_package(tmp_path / "missing.dststandard", document)
    preview = client.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is False
    assert [item["code"] for item in preview.json()["diagnostics"]] == [
        "STANDARD_ASSET_FILE_MISSING"
    ]
    assert client.get("/api/standards").json() == []

    # 直接确认同一包（绕过前端）仍以 422 拒绝且不落库。
    bypass = client.post("/api/standards/import", json={"preview_id": "forged"})
    assert bypass.status_code == 404
    assert client.get("/api/standards").json() == []


def test_missing_export_target_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    absent_id = "123e4567-e89b-42d3-a456-426614174199"
    assert client.get(f"/api/standards/{absent_id}/export").status_code == 404


# ---- 草稿级保存路由（PLAN-DM-040 Task 7，F11） ---------------------------


def test_draft_save_route_roundtrip(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")

    response = client.put(
        "/api/standards/drafts/draft-gas",
        json={"document": dict(DRAFT_DOCUMENT, name="修订名")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["draft_id"] == "draft-gas"
    assert response.json()["document"]["name"] == "修订名"
    stored = client.get("/api/standards/drafts/draft-gas").json()
    assert stored["document"]["name"] == "修订名"


def test_draft_save_route_missing_draft_returns_404(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.put(
        "/api/standards/drafts/absent", json={"document": DRAFT_DOCUMENT}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "STANDARD_DRAFT_NOT_FOUND"


def test_draft_save_route_rejects_carried_version(tmp_path: Path) -> None:
    """草稿不得携带正式版本：携带时以稳定 422 拒绝，且不静默改写已存草稿。"""
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")

    response = client.put(
        "/api/standards/drafts/draft-gas",
        json={"document": dict(DRAFT_DOCUMENT, version=9)},
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "STANDARD_VERSION_INVALID"
    assert "version" not in client.get("/api/standards/drafts/draft-gas").json()["document"]


def test_draft_save_route_rejects_invalid_structure(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")
    response = client.put(
        "/api/standards/drafts/draft-gas", json={"document": {"schema_version": 99}}
    )
    assert response.status_code == 422
    assert response.json()["code"].startswith("STANDARD_")


def test_draft_save_route_rejects_illegal_draft_id(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.put(
        "/api/standards/drafts/%2E%2E", json={"document": DRAFT_DOCUMENT}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_DRAFT_ID_INVALID"


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
                    "file": "assets/A2.dwg",
                    "paper_layouts": ["A2"],
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
    assert body["diagnostics"][0]["code"] == "STANDARD_PAPER_LAYOUT_MISSING"
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


# ---- 身份段路径边界（PLAN-DM-040 Task 1，F17） ----------------------------

SECRET_NAME = "根外秘密标准"


def write_library_escape_fixture(tmp_path: Path) -> Path:
    """在标准库根上两级预置合法 document.json 与 assets/secret.dwg。

    ``<data>/standards/user/published/../..`` 正好落在 ``<data>/standards``。
    """
    standards_root = tmp_path / "data" / "standards"
    (standards_root / "assets").mkdir(parents=True, exist_ok=True)
    (standards_root / "document.json").write_text(
        json.dumps(copy.deepcopy(DRAFT_DOCUMENT) | {"name": SECRET_NAME}, ensure_ascii=False),
        encoding="utf-8",
    )
    (standards_root / "assets" / "secret.dwg").write_bytes(b"secret-dwg")
    return standards_root


def test_identity_route_rejects_percent_encoded_parent_segments(tmp_path: Path) -> None:
    write_library_escape_fixture(tmp_path)
    client = make_client(tmp_path)

    detail = client.get("/api/standards/%2E%2E")
    assert detail.status_code in (404, 422), detail.text
    assert SECRET_NAME not in detail.text

    exported = client.get("/api/standards/%2E%2E/export")
    assert exported.status_code in (404, 422), exported.text
    assert exported.headers.get("content-type") != "application/zip"
    assert b"secret-dwg" not in exported.content

ILLEGAL_IDENTITIES = ("..", "C:", "", "not-a-uuid", "123e4567e89b42d3a456426614174101")


@pytest.mark.parametrize("standard_id", ILLEGAL_IDENTITIES)
def test_store_identity_entries_reject_illegal_segments(
    tmp_path: Path, standard_id: str
) -> None:
    write_library_escape_fixture(tmp_path)
    store = DstManagerService(Settings(data_dir=tmp_path / "data")).standard_store

    with pytest.raises(StandardStoreError) as fetched:
        store.get(standard_id)
    assert str(fetched.value).split(":", 1)[0] == "STANDARD_ID_INVALID"

    with pytest.raises(StandardStoreError) as document_exc:
        store.get_document(standard_id)
    assert str(document_exc.value).split(":", 1)[0] == "STANDARD_ID_INVALID"

    with pytest.raises(StandardStoreError) as exported:
        store.export_package(standard_id, tmp_path / "out")
    assert str(exported.value).split(":", 1)[0] == "STANDARD_ID_INVALID"
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob("*.dststandard"))


def test_identity_codes_name_the_offending_segment(tmp_path: Path) -> None:
    write_library_escape_fixture(tmp_path)
    store = DstManagerService(Settings(data_dir=tmp_path / "data")).standard_store
    with pytest.raises(StandardStoreError, match="STANDARD_ID_INVALID"):
        store.get("..")
    with pytest.raises(StandardStoreError, match="STANDARD_ID_INVALID"):
        store.get("szmedi.gas")


# ---- 资产硬门禁 HTTP 入口（PLAN-DM-040 Task 2，F02） ----------------------


def asset_document(*paths: str) -> dict:
    document = copy.deepcopy(DRAFT_DOCUMENT)
    document["assets"] = [
        {
            "asset_id": "templates",
            "kind": "base-template",
            "file": paths[0],
        }
    ]
    return document


def write_api_package(path: Path, document: dict, entries: dict[str, bytes] | None = None) -> Path:
    package_document = copy.deepcopy(document)
    if package_document.get("schema_version") == 3:
        package_document.pop("version", None)
        if package_document.get("published_at") is None:
            package_document["published_at"] = 1_800_000_000_123
        package_document.setdefault("description", "标准描述原文")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(package_document, ensure_ascii=False))
        for name, data in (entries or {}).items():
            archive.writestr(name, data)
    return path


def test_publish_rejects_draft_with_missing_asset(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, asset_document("assets/missing.dwg"), "draft-asset")

    response = client.post("/api/standards/drafts/draft-asset/publish")
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "STANDARD_ASSET_FILE_MISSING"
    assert client.get("/api/standards/drafts/draft-asset").status_code == 200
    assert [
        item
        for item in client.get("/api/standards").json()
        if item["status"] == "published"
    ] == []


def test_publish_rejects_draft_with_absolute_asset_path(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, asset_document("C:\\outside\\secret.dwg"), "draft-asset")

    response = client.post("/api/standards/drafts/draft-asset/publish")
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "STANDARD_ASSET_PATH_INVALID"
    assert client.get("/api/standards/drafts/draft-asset").status_code == 200


def test_export_includes_only_declared_assets(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, asset_document("assets/A2.dwg"), "draft-asset")
    assets = tmp_path / "data" / "standards" / "user" / "drafts" / "draft-asset" / "assets"
    assets.mkdir(parents=True)
    (assets / "A2.dwg").write_bytes(b"a2")
    (assets / "tmp-unreferenced.dwg").write_bytes(b"tmp")
    assert client.post("/api/standards/drafts/draft-asset/publish").status_code == 200

    exported = client.get(f"/api/standards/{STANDARD_ID}/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert sorted(archive.namelist()) == ["assets/A2.dwg", "manifest.json"]


# ---- 本机模板受控复制 HTTP 入口（PLAN-DM-040 Task 3，F01） -----------------


def test_copy_asset_file_endpoint_returns_controlled_copy(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")
    source = tmp_path / "OneDrive - 项目" / "A2 模板.dwg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"dwg-bytes")
    before = source.stat().st_mtime_ns

    response = client.post(
        "/api/standards/drafts/draft-gas/asset-files", json={"source_path": str(source)}
    )

    assert response.status_code == 200, response.text
    copied = response.json()["path"]
    assert copied.startswith("assets/managed-") and copied.endswith(".dwg")
    target = (
        tmp_path / "data" / "standards" / "user" / "drafts" / "draft-gas" / copied
    )
    assert target.read_bytes() == b"dwg-bytes"
    assert source.stat().st_mtime_ns == before
    # 本机绝对路径不得写进草稿文档
    document = client.get("/api/standards/drafts/draft-gas").json()["document"]
    assert str(source) not in json.dumps(document, ensure_ascii=False)


def test_copy_asset_file_endpoint_rejects_missing_source(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")
    response = client.post(
        "/api/standards/drafts/draft-gas/asset-files",
        json={"source_path": str(tmp_path / "nope.dwg")},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "STANDARD_ASSET_SOURCE_NOT_FOUND"


def test_copy_asset_file_endpoint_rejects_illegal_draft_id(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    source = tmp_path / "A2.dwg"
    source.write_bytes(b"dwg")
    response = client.post(
        "/api/standards/drafts/%2E%2E/asset-files", json={"source_path": str(source)}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "STANDARD_DRAFT_ID_INVALID"


def test_copied_asset_closes_loop_through_publish_and_export(    tmp_path: Path, monkeypatch
) -> None:
    """复制 → 声明 → 保存 → 检查 → 发布 → 导出 的完整闭环。"""
    monkeypatch.setattr(
        DstManagerService,
        "get_layout_names",
        lambda self, file_path, cad_version: {
            "layouts": ["Model", "A2"],
            "cached": False,
            "file_hash": "0" * 64,
        },
    )
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")
    source = tmp_path / "A2 模板.dwg"
    source.write_bytes(b"dwg-bytes")
    copied = client.post(
        "/api/standards/drafts/draft-gas/asset-files", json={"source_path": str(source)}
    ).json()["path"]

    document = copy.deepcopy(DRAFT_DOCUMENT)
    document["assets"] = [
        {
            "asset_id": "layouts",
            "kind": "layout-template",
            "file": copied,
            "paper_layouts": ["A2"],
        }
    ]
    assert (
        client.put(
            "/api/standards/drafts/draft-gas", json={"document": document}
        ).status_code
        == 200
    )
    inspected = client.post(
        "/api/standards/drafts/draft-gas/assets/layouts/inspect", json={"cad_version": "2020"}
    )
    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["diagnostics"] == []
    assert client.post("/api/standards/drafts/draft-gas/publish").status_code == 200

    exported = client.get(f"/api/standards/{STANDARD_ID}/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert sorted(archive.namelist()) == sorted(["manifest.json", copied])
        assert archive.read(copied) == b"dwg-bytes"


def test_legal_identity_entries_keep_working(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")
    assert client.post("/api/standards/drafts/draft-gas/publish").status_code == 200
    detail = client.get(f"/api/standards/{STANDARD_ID}")
    assert detail.status_code == 200
    assert detail.json()["document"]["name"] == "市政燃气施工图"
    exported = client.get(f"/api/standards/{STANDARD_ID}/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert "manifest.json" in archive.namelist()


# ---- UUID 标准包两步导入的端到端闭环（PLAN-DM-046 Task 3） ---------------


def test_standard_package_full_loop_from_draft_asset_to_import_roundtrip(
    tmp_path: Path,
) -> None:
    """发布、导出、预检、确认与再次导出沿用 UUID、发布时间和标准描述。"""
    publisher = make_client(tmp_path / "publisher")
    template = tmp_path / "A2 模板.dwg"
    template.write_bytes(b"dwg-bytes")
    make_draft(publisher, DRAFT_DOCUMENT, "draft-gas")
    copied = publisher.post(
        "/api/standards/drafts/draft-gas/asset-files", json={"source_path": str(template)}
    ).json()["path"]
    document = {**DRAFT_DOCUMENT, "assets": [
        {"asset_id": "templates", "kind": "base-template", "file": copied}
    ]}
    assert (
        publisher.put(
            "/api/standards/drafts/draft-gas", json={"document": document}
        ).status_code
        == 200
    )

    published = publisher.post("/api/standards/drafts/draft-gas/publish")
    assert published.status_code == 200, published.text
    published_at = published.json()["published_at"]
    assert published.json()["standard_id"] == STANDARD_ID
    assert publisher.get(f"/api/standards/{STANDARD_ID}").status_code == 200

    exported = publisher.get(f"/api/standards/{STANDARD_ID}/export")
    assert exported.status_code == 200
    package = tmp_path / f"{STANDARD_ID}.dststandard"
    package.write_bytes(exported.content)
    with zipfile.ZipFile(package) as archive:
        assert sorted(archive.namelist()) == [copied, "manifest.json"]
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["schema_version"] == 4
    assert manifest["standard_id"] == STANDARD_ID
    assert manifest["published_at"] == published_at
    assert manifest["description"] == "标准描述原文"
    assert "version" not in manifest
    assert "release_notes" not in manifest

    # 另一数据根：预检 → 确认导入
    consumer = make_client(tmp_path / "consumer")
    preview = consumer.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is True
    assert preview.json()["name_conflict"] is False
    assert preview.json()["existing_name"] is None
    confirmed = consumer.post(
        "/api/standards/import", json={"preview_id": preview.json()["preview_id"]}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["published_at"] == published_at
    assert confirmed.json()["description"] == "标准描述原文"

    entries = consumer.get("/api/standards").json()
    assert len(entries) == 1
    assert entries[0]["standard_id"] == STANDARD_ID
    assert entries[0]["published_at"] == published_at
    assert "version" not in entries[0]
    re_exported = consumer.get(f"/api/standards/{STANDARD_ID}/export")
    assert re_exported.status_code == 200

    duplicate = consumer.post(
        "/api/standards/import-previews", json={"path": str(package)}
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["can_import"] is False
    assert [item["code"] for item in duplicate.json()["diagnostics"]] == [
        "STANDARD_ID_EXISTS"
    ]


def test_publish_failure_keeps_draft_and_does_not_reserve_identity(
    tmp_path: Path, monkeypatch
) -> None:
    """发布失败回滚：草稿与受控资产保留，不预留空版本目录。"""
    client = make_client(tmp_path)
    template = tmp_path / "A2 模板.dwg"
    template.write_bytes(b"dwg-bytes")
    make_draft(client, DRAFT_DOCUMENT, "draft-gas")
    copied = client.post(
        "/api/standards/drafts/draft-gas/asset-files", json={"source_path": str(template)}
    ).json()["path"]
    document = {**DRAFT_DOCUMENT, "assets": [
        {"asset_id": "templates", "kind": "base-template", "file": copied}
    ]}
    client.put("/api/standards/drafts/draft-gas", json={"document": document})

    real_replace = os.replace

    def failing_replace(source, target):
        raise OSError(13, "injected publish failure")

    monkeypatch.setattr(os, "replace", failing_replace)
    try:
        failed = client.post("/api/standards/drafts/draft-gas/publish")
    finally:
        monkeypatch.setattr(os, "replace", real_replace)

    assert failed.status_code == 422, failed.text
    assert failed.json()["code"] == "STANDARD_PUBLISH_FAILED"
    # 草稿仍可按草稿门禁读回（无 version），受控资产仍在，标准库无条目
    stored = client.get("/api/standards/drafts/draft-gas").json()["document"]
    assert "version" not in stored
    # 列表只剩这份草稿：失败不创建已发布 UUID 目录。
    entries = client.get("/api/standards").json()
    assert [(item["status"], item["published_at"]) for item in entries] == [
        ("draft", None)
    ]
    assert "version" not in entries[0]
    assert not (
        tmp_path
        / "data"
        / "standards"
        / "user"
        / "published"
        / STANDARD_ID
    ).exists()
    assert (
        tmp_path / "data" / "standards" / "user" / "drafts" / "draft-gas" / copied
    ).read_bytes() == b"dwg-bytes"


# ---- 确认阶段的门禁复核与凭证时效（PLAN-DM-041 固定复核延后项） -----------


def test_import_confirm_rejects_name_conflict_added_after_preview(tmp_path: Path) -> None:
    """预检后、确认前新增不同 ID 的同名标准：确认必须在仓储锁内复核并以 409 拒绝。

    「单实例」只排除第二个进程，不排除第二个请求：预检返回可导入之后，同一进程内的
    另一个发布请求完全可以先占用同一名称，因此这条复核不可省。
    """
    client = make_client(tmp_path)
    package = write_api_package(
        tmp_path / "copy.dststandard", published_document(SECOND_STANDARD_ID)
    )
    preview = client.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is True

    # 预检之后用另一个 ID 占住同一名称。
    other_draft = copy.deepcopy(DRAFT_DOCUMENT)
    other_draft["standard_id"] = THIRD_STANDARD_ID
    make_draft(client, other_draft, "draft-other")
    published = client.post("/api/standards/drafts/draft-other/publish")
    assert published.status_code == 200, published.text

    confirmed = client.post(
        "/api/standards/import", json={"preview_id": preview.json()["preview_id"]}
    )
    assert confirmed.status_code == 409, confirmed.text
    assert confirmed.json()["code"] == "STANDARD_NAME_CONFLICT"
    # 被拒绝的导入不落库
    assert [item["standard_id"] for item in client.get("/api/standards").json()] == [
        THIRD_STANDARD_ID
    ]


def test_import_confirm_rejects_expired_credential_with_410(tmp_path: Path) -> None:
    """凭证过期后确认返回 410（不是 404/422），且过期即清理快照。"""
    client = make_client(tmp_path)
    service = client.app.state.service
    service.import_previews.ttl_seconds = 0
    package = write_api_package(
        tmp_path / "copy.dststandard", {**DRAFT_DOCUMENT, "version": 1}
    )
    preview = client.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.status_code == 200, preview.text
    preview_id = preview.json()["preview_id"]
    assert preview_id is not None

    confirmed = client.post("/api/standards/import", json={"preview_id": preview_id})

    assert confirmed.status_code == 410, confirmed.text
    assert confirmed.json()["code"] == "STANDARD_IMPORT_PREVIEW_EXPIRED"
    assert client.get("/api/standards").json() == []
    assert list(service.import_previews.snapshot_files()) == []


def test_task3_import_preview_blocks_same_uuid_before_name_conflict(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-existing")
    published = client.post("/api/standards/drafts/draft-existing/publish")
    assert published.status_code == 200, published.text

    package = write_api_package(
        tmp_path / "same-id.dststandard",
        published_document(
            STANDARD_ID,
            name="包内改名",
            description="另一份描述",
            published_at=1_800_000_000_999,
        ),
    )
    preview = client.post("/api/standards/import-previews", json={"path": str(package)})

    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_import"] is False
    assert body["preview_id"] is None
    assert body["name_conflict"] is False
    assert body["existing_name"] == "市政燃气施工图"
    assert [item["code"] for item in body["diagnostics"]] == ["STANDARD_ID_EXISTS"]


def test_task3_name_conflict_keeps_preview_and_imports_a_renamed_copy(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path)
    make_draft(client, DRAFT_DOCUMENT, "draft-existing")
    assert client.post("/api/standards/drafts/draft-existing/publish").status_code == 200
    package = write_api_package(
        tmp_path / "same-name.dststandard",
        published_document(
            SECOND_STANDARD_ID,
            description="从原包保留的描述",
            published_at=1_800_000_000_555,
        ),
    )
    original_bytes = package.read_bytes()

    preview = client.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_import"] is False
    assert body["preview_id"]
    assert body["name_conflict"] is True
    assert body["existing_name"] == "市政燃气施工图"
    assert body["description"] == "从原包保留的描述"
    assert body["published_at"] == 1_800_000_000_555

    blocked = client.post(
        "/api/standards/import", json={"preview_id": body["preview_id"]}
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "STANDARD_NAME_CONFLICT"

    imported = client.post(
        "/api/standards/import",
        json={"preview_id": body["preview_id"], "name": "燃气施工图（改名）"},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["standard_id"] == SECOND_STANDARD_ID
    assert imported.json()["name"] == "燃气施工图（改名）"
    assert imported.json()["published_at"] == 1_800_000_000_555
    detail = client.get(f"/api/standards/{SECOND_STANDARD_ID}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["description"] == "从原包保留的描述"
    assert package.read_bytes() == original_bytes


def test_task3_export_import_roundtrip_preserves_description_without_release_notes(
    tmp_path: Path,
) -> None:
    publisher = make_client(tmp_path / "publisher")
    document = copy.deepcopy(DRAFT_DOCUMENT)
    document["description"] = "可导出的标准描述"
    make_draft(publisher, document, "draft-export")
    published = publisher.post("/api/standards/drafts/draft-export/publish")
    assert published.status_code == 200, published.text
    published_at = published.json()["published_at"]

    exported = publisher.get(f"/api/standards/{STANDARD_ID}/export")
    assert exported.status_code == 200, exported.text
    assert f"{STANDARD_ID}.dststandard" in exported.headers["content-disposition"]
    package = tmp_path / "roundtrip.dststandard"
    package.write_bytes(exported.content)

    consumer = make_client(tmp_path / "consumer")
    preview = consumer.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["description"] == "可导出的标准描述"
    imported = consumer.post(
        "/api/standards/import", json={"preview_id": preview.json()["preview_id"]}
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["published_at"] == published_at
    detail = consumer.get(f"/api/standards/{STANDARD_ID}")
    assert detail.json()["description"] == "可导出的标准描述"

    re_exported = consumer.get(f"/api/standards/{STANDARD_ID}/export")
    with zipfile.ZipFile(io.BytesIO(re_exported.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["description"] == "可导出的标准描述"
    assert "release_notes" not in manifest
    assert manifest["published_at"] == published_at


def test_task3_import_confirm_rechecks_name_occupied_after_preview(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    package = write_api_package(
        tmp_path / "import.dststandard",
        published_document(SECOND_STANDARD_ID, name="预检时可用"),
    )
    preview = client.post("/api/standards/import-previews", json={"path": str(package)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is True

    make_draft(client, published_document(STANDARD_ID, name="预检时可用", published_at=None), "draft-race")
    assert client.post("/api/standards/drafts/draft-race/publish").status_code == 200
    confirmed = client.post(
        "/api/standards/import",
        json={"preview_id": preview.json()["preview_id"]},
    )
    assert confirmed.status_code == 409
    assert confirmed.json()["code"] == "STANDARD_NAME_CONFLICT"
