"""扩展平台统一管理 API 集成测试（PLAN-DM-020 Task 3 / ARCH-DM-006 §8、§12）。

覆盖：列表/启停/重启持久化、未知扩展、禁用动作、错误清单与工厂失败隔离、
设置 ``expected_revision`` 冲突、偏好不存在默认值、Artifact 404、平台错误码
的稳定 ``message_key`` 与结构化 ``params``、OpenAPI 端点与错误契约，以及
启动顺序（数据库迁移完成 → 发布恢复完成 → ``registry.discover()``）。
"""

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

import dst_manager.application.service as service_module
import dst_manager.extensions.registry as registry_module
from dst_manager.application.extensions.runtime import ExtensionRuntime
from dst_manager.config import Settings
from dst_manager.extensions.builtin.index import (
    BUILTIN_EXTENSION_INDEX,
    BuiltinExtensionEntry,
)
from dst_manager.extensions.registry import ExtensionRegistry
from dst_manager.infrastructure.persistence.database import Database
from dst_manager.infrastructure.persistence.extensions import (
    ArtifactRecord,
    ExtensionStore,
)
from dst_manager.interfaces.api import create_app

SHEET_CATALOG_ID = "dst-manager.sheet-catalog"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: ARCH-DM-006 §12 全部平台错误码；OpenAPI 错误契约必须逐一登记。
PLATFORM_ERROR_CODES = (
    "EXTENSION_NOT_FOUND",
    "EXTENSION_DISABLED",
    "EXTENSION_INCOMPATIBLE",
    "EXTENSION_CAPABILITY_UNAVAILABLE",
    "EXTENSION_SETTINGS_INVALID",
    "EXTENSION_ACTION_NOT_FOUND",
    "SAVE_GRANT_INVALID",
    "EXPORT_DESTINATION_CHANGED",
    "REPREVIEW_REQUIRED",
    "ARTIFACT_WRITE_FAILED",
)


def make_client(tmp_path, **kwargs) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path / "data"), **kwargs))


def make_runtime(tmp_path, entries) -> ExtensionRuntime:
    """测试注入用运行时：独立 sqlite 库承载扩展状态/设置/偏好/Artifact。"""
    database = Database(f"sqlite:///{(tmp_path / 'extension-tests.db').as_posix()}")
    return ExtensionRuntime(ExtensionRegistry(), ExtensionStore(database.sessions))


def assert_error_contract(body: dict) -> None:
    """统一错误契约：code/message_key/params/message 四字段齐全且稳定。"""
    assert set(body) == {"code", "message_key", "params", "message"}
    assert body["code"] and body["message_key"] and body["message"]
    assert isinstance(body["params"], dict)


# ---------------------------------------------------------------------------
# 列表 / 启停 / 重启持久化
# ---------------------------------------------------------------------------


def test_list_extensions_reports_real_sheet_catalog_state(tmp_path):
    client = make_client(tmp_path)

    body = client.get("/api/extensions")

    assert body.status_code == 200
    items = body.json()
    assert [item["extension_id"] for item in items] == [SHEET_CATALOG_ID]
    item = items[0]
    # 能力中心（Task 4）未落地：必须如实呈现 WAITING_DEPENDENCY，不得谎报 AVAILABLE
    assert item["status"] == "WAITING_DEPENDENCY"
    assert item["error_code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert item["enabled"] is True
    assert item["version"] == "0.1.0"
    assert item["name_key"] == "extensions.sheetCatalog.name"
    assert item["description_key"] == "extensions.sheetCatalog.description"
    assert item["actions"] == [
        {"action_id": "export-xlsx", "output_kind": "xlsx", "media_type": XLSX_MEDIA_TYPE}
    ]
    assert item["ui_contributions"] == [
        {
            "contribution_id": "workspace-page",
            "kind": "workspace_page",
            "route_key": "sheet-catalog",
        }
    ]


def test_patch_state_persists_across_restart(tmp_path):
    client = make_client(tmp_path)

    patched = client.patch(f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": False})

    assert patched.status_code == 200
    body = patched.json()
    assert body["extension_id"] == SHEET_CATALOG_ID
    assert body["enabled"] is False
    # 用户停用不改变"天然不可用"的状态机事实：状态保持 WAITING_DEPENDENCY
    assert body["status"] == "WAITING_DEPENDENCY"

    restarted = make_client(tmp_path)
    assert restarted.get("/api/extensions").json()[0]["enabled"] is False


def test_enable_rejected_while_capability_missing_keeps_persisted_intent(tmp_path):
    client = make_client(tmp_path)
    assert client.patch(
        f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": False}
    ).status_code == 200

    resp = client.patch(f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": True})

    assert resp.status_code == 503
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert body["message_key"] == "errors.extension.capabilityUnavailable"
    assert body["params"] == {"extension_id": SHEET_CATALOG_ID}
    # 失败的启用不得翻转持久化的用户停用意图
    assert client.get("/api/extensions").json()[0]["enabled"] is False


# ---------------------------------------------------------------------------
# 未知扩展 / Artifact 404
# ---------------------------------------------------------------------------


def test_unknown_extension_and_artifact_return_structured_404(tmp_path):
    client = make_client(tmp_path)

    responses = {
        "state": client.patch("/api/extensions/no-such/state", json={"enabled": True}),
        "settings": client.get("/api/extensions/no-such/settings"),
        "preference": client.get("/api/extensions/no-such/workspaces/ws-1/preferences"),
        "preview": client.post(
            "/api/extensions/no-such/actions/export-xlsx/preview", json={}
        ),
        "artifact": client.get("/api/artifacts/no-such-artifact"),
    }

    for resp in responses.values():
        assert resp.status_code == 404
        body = resp.json()
        assert_error_contract(body)
        assert body["code"] == "EXTENSION_NOT_FOUND"
    assert responses["state"].json()["params"] == {"extension_id": "no-such"}
    assert responses["settings"].json()["params"] == {"extension_id": "no-such"}
    assert responses["preview"].json()["params"] == {"extension_id": "no-such"}
    assert responses["artifact"].json()["params"] == {"artifact_id": "no-such-artifact"}


def test_artifact_lookup_returns_seeded_metadata(tmp_path):
    client = make_client(tmp_path)
    store = ExtensionStore(client.app.state.service.database.sessions)
    store.create_artifact(
        ArtifactRecord(
            artifact_id="artifact-1",
            extension_id=SHEET_CATALOG_ID,
            extension_version="0.1.0",
            workspace_id="ws-1",
            source_revision_id="rev-1",
            kind="sheet-catalog",
            media_type=XLSX_MEDIA_TYPE,
            management_relation="external",
            output_path="C:/out/图纸目录.xlsx",
            file_name="图纸目录.xlsx",
            size_bytes=2048,
            sha256="a" * 64,
            created_at=datetime(2026, 9, 10, 8, 0, 0, tzinfo=UTC),
        )
    )

    resp = client.get("/api/artifacts/artifact-1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["artifact_id"] == "artifact-1"
    assert body["extension_id"] == SHEET_CATALOG_ID
    assert body["workspace_id"] == "ws-1"
    assert body["source_revision_id"] == "rev-1"
    assert body["kind"] == "sheet-catalog"
    assert body["media_type"] == XLSX_MEDIA_TYPE
    assert body["management_relation"] == "external"
    assert body["file_name"] == "图纸目录.xlsx"


# ---------------------------------------------------------------------------
# 设置与偏好
# ---------------------------------------------------------------------------


def test_settings_roundtrip_revision_conflict_and_schema_guard(tmp_path):
    client = make_client(tmp_path)
    url = f"/api/extensions/{SHEET_CATALOG_ID}/settings"

    default = client.get(url)
    assert default.status_code == 200
    assert default.json() == {"schema_version": 1, "revision": 0, "value": {}}

    saved = client.put(
        url,
        json={
            "schema_version": 1,
            "value": {"columns": ["{{sheet.number}}"]},
            "expected_revision": 0,
        },
    )
    assert saved.status_code == 200
    assert saved.json() == {
        "schema_version": 1,
        "revision": 1,
        "value": {"columns": ["{{sheet.number}}"]},
    }

    conflict = client.put(
        url, json={"schema_version": 1, "value": {}, "expected_revision": 0}
    )
    assert conflict.status_code == 409
    body = conflict.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    assert body["message_key"] == "errors.extension.settingsInvalid"
    assert body["params"] == {"expected_revision": 0, "current_revision": 1}
    # 冲突时旧值未被覆盖
    assert client.get(url).json()["value"] == {"columns": ["{{sheet.number}}"]}

    schema_mismatch = client.put(
        url, json={"schema_version": 2, "value": {}, "expected_revision": 1}
    )
    assert schema_mismatch.status_code == 422
    body = schema_mismatch.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    assert body["params"] == {"settings_schema": 1, "submitted": 2}


def test_preferences_default_and_workspace_isolation(tmp_path):
    client = make_client(tmp_path)
    first = f"/api/extensions/{SHEET_CATALOG_ID}/workspaces/ws-1/preferences"
    second = f"/api/extensions/{SHEET_CATALOG_ID}/workspaces/ws-2/preferences"

    # 偏好不存在时返回清单 schema 的零值默认，而不是 404
    assert client.get(first).json() == {"schema_version": 1, "revision": 0, "value": {}}

    put = client.put(first, json={"schema_version": 1, "value": {"template_id": "t-1"}})
    assert put.status_code == 200
    assert put.json() == {"schema_version": 1, "revision": 1, "value": {"template_id": "t-1"}}
    assert client.get(first).json()["value"] == {"template_id": "t-1"}
    assert client.get(second).json()["value"] == {}


# ---------------------------------------------------------------------------
# 动作分派：扩展状态与动作声明
# ---------------------------------------------------------------------------


def test_action_endpoints_validate_availability_and_declared_action(tmp_path, monkeypatch):
    monkeypatch.setattr(
        registry_module, "AVAILABLE_CAPABILITIES", frozenset({"workspace.snapshot.read.v1"})
    )
    client = make_client(tmp_path)
    assert client.get("/api/extensions").json()[0]["status"] == "AVAILABLE"

    unknown_action = client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/no-such-action/preview", json={}
    )
    assert unknown_action.status_code == 404
    body = unknown_action.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_ACTION_NOT_FOUND"
    assert body["message_key"] == "errors.extension.actionNotFound"
    assert body["params"] == {"extension_id": SHEET_CATALOG_ID, "action_id": "no-such-action"}

    assert client.patch(
        f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": False}
    ).status_code == 200
    disabled = client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/preview", json={}
    )
    assert disabled.status_code == 409
    body = disabled.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_DISABLED"
    assert body["message_key"] == "errors.extension.disabled"
    assert body["params"] == {"extension_id": SHEET_CATALOG_ID, "action_id": "export-xlsx"}

    # 重新启用后动作已声明，但宿主动作执行通道未接入（Task 6/9）：不得编造预览/执行结果
    assert client.patch(
        f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": True}
    ).status_code == 200
    for suffix in ("preview", "execute"):
        resp = client.post(
            f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/{suffix}", json={}
        )
        assert resp.status_code == 503
        body = resp.json()
        assert_error_contract(body)
        assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"


def test_action_endpoint_reports_unavailable_extension_without_capability_broker(tmp_path):
    client = make_client(tmp_path)

    resp = client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/preview", json={}
    )

    assert resp.status_code == 503
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert body["message_key"] == "errors.extension.capabilityUnavailable"
    assert body["params"] == {"extension_id": SHEET_CATALOG_ID, "action_id": "export-xlsx"}


# ---------------------------------------------------------------------------
# 错误清单与工厂失败的故障隔离
# ---------------------------------------------------------------------------


def _boom() -> None:
    raise RuntimeError("工厂故障")


def test_broken_manifest_and_factory_isolation_keeps_core_api_available(tmp_path, monkeypatch):
    monkeypatch.setattr(
        registry_module, "AVAILABLE_CAPABILITIES", frozenset({"workspace.snapshot.read.v1"})
    )
    bad = tmp_path / "bad-manifest.yaml"
    bad.write_text("extension_id: [未闭合", encoding="utf-8")
    entries = (
        BuiltinExtensionEntry(manifest_resource=str(bad), factory=_boom),
        BuiltinExtensionEntry(
            manifest_resource="dst_manager/extensions/builtin/sheet_catalog/manifest.yaml",
            factory=_boom,
        ),
    )
    client = make_client(
        tmp_path, extension_runtime=make_runtime(tmp_path, entries), extension_index=entries
    )

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/revisions").status_code == 200

    listed = {item["extension_id"]: item for item in client.get("/api/extensions").json()}
    assert listed[str(bad)]["status"] == "FAILED"
    assert listed[str(bad)]["error_code"] == "EXTENSION_MANIFEST_INVALID"
    assert listed[SHEET_CATALOG_ID]["status"] == "FAILED"
    assert listed[SHEET_CATALOG_ID]["error_code"] == "EXTENSION_START_FAILED"


# ---------------------------------------------------------------------------
# 不兼容扩展
# ---------------------------------------------------------------------------


def test_incompatible_extension_enable_rejected_with_platform_code(tmp_path):
    manifest = tmp_path / "broken-capability.yaml"
    manifest.write_text(
        """
extension_id: test.broken-capability
version: 0.1.0
extension_type: builtin
host_contract: 1
enabled_by_default: false
name_key: extensions.test.name
description_key: extensions.test.description
required_capabilities:
  - workspace.snapshot.write.v9
permissions: []
ui_contributions: []
actions: []
settings_schema: 1
""".strip()
        + "\n",
        encoding="utf-8",
    )
    entries = (BuiltinExtensionEntry(manifest_resource=str(manifest), factory=_boom),)
    client = make_client(
        tmp_path, extension_runtime=make_runtime(tmp_path, entries), extension_index=entries
    )

    listed = client.get("/api/extensions").json()
    assert [item["extension_id"] for item in listed] == ["test.broken-capability"]
    assert listed[0]["status"] == "INCOMPATIBLE"
    assert listed[0]["error_code"] == "EXTENSION_CAPABILITY_UNKNOWN"

    resp = client.patch("/api/extensions/test.broken-capability/state", json={"enabled": True})

    assert resp.status_code == 409
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_INCOMPATIBLE"
    assert body["message_key"] == "errors.extension.incompatible"
    assert body["params"] == {"extension_id": "test.broken-capability"}


# ---------------------------------------------------------------------------
# OpenAPI 契约
# ---------------------------------------------------------------------------


def test_openapi_lists_all_extension_endpoints_and_platform_error_codes(tmp_path):
    client = make_client(tmp_path)

    schema = client.app.openapi()

    paths = schema["paths"]
    expected = {
        "/api/extensions": {"get"},
        "/api/extensions/{extension_id}/state": {"patch"},
        "/api/extensions/{extension_id}/settings": {"get", "put"},
        "/api/extensions/{extension_id}/workspaces/{workspace_id}/preferences": {"get", "put"},
        "/api/extensions/{extension_id}/actions/{action_id}/preview": {"post"},
        "/api/extensions/{extension_id}/actions/{action_id}/execute": {"post"},
        "/api/artifacts/{artifact_id}": {"get"},
    }
    for path, methods in expected.items():
        assert methods <= set(paths[path]), path
    error_schema = schema["components"]["schemas"]["ExtensionErrorResponse"]
    assert set(error_schema["required"]) == {"code", "message_key", "params", "message"}
    rendered = json.dumps(error_schema, ensure_ascii=False)
    for code in PLATFORM_ERROR_CODES:
        assert code in rendered, code


# ---------------------------------------------------------------------------
# 启动顺序：数据库迁移完成 → 发布恢复完成 → registry.discover()
# ---------------------------------------------------------------------------


def test_startup_order_is_migration_then_publish_recovery_then_discover(
    tmp_path, tiny_workspace, monkeypatch
):
    # 先让服务库登记 workspace root：重启后发布恢复才真实执行
    first = make_client(tmp_path)
    opened = first.post("/api/workspaces/open", json={"dst_path": str(tiny_workspace[0])})
    assert opened.status_code == 200
    first.app.state.service.database.engine.dispose()

    events: list[str] = []

    class RecordingDatabase(service_module.Database):
        def __init__(self, url, **kwargs):
            super().__init__(url, **kwargs)
            events.append("database-migrated")

    class RecordingPublisher(service_module.RecoverablePublisher):
        def recover(self, root):
            events.append("publish-recovered")
            return super().recover(root)

    monkeypatch.setattr(service_module, "Database", RecordingDatabase)
    monkeypatch.setattr(service_module, "RecoverablePublisher", RecordingPublisher)

    class RecordingRuntime(ExtensionRuntime):
        def start(self, entries=BUILTIN_EXTENSION_INDEX):
            events.append("registry-discovered")
            super().start(entries)

    settings = Settings(data_dir=tmp_path / "data")
    runtime = RecordingRuntime(
        ExtensionRegistry(),
        ExtensionStore(Database(settings.database_url).sessions),
    )
    client = make_client(tmp_path, extension_runtime=runtime)

    assert client.get("/api/extensions").json()[0]["enabled"] is True
    assert events == ["database-migrated", "publish-recovered", "registry-discovered"]
