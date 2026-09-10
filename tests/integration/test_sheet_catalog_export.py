"""图纸目录导出执行动作与 Artifact 登记集成测试（PLAN-DM-020 Task 9 / SPEC-DM-012 §8.2、§9、§10）。

覆盖：预览后执行成功并回读 XLSX/Artifact、未保存模板可执行、修订/模板/扩展
版本/动作摘要变化 ``REPREVIEW_REQUIRED``、无效/漂移/复用授权拒绝、候选失败不
登记、成功响应无后台字段、Artifact 三态可用性、桥与 API runtime 共享同一
``SaveGrantStore``，以及整条预览→执行链路的只读不变量。
"""

import hashlib
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import text

import dst_manager.extensions.builtin.sheet_catalog.extension as extension_module
import dst_manager.extensions.registry as registry_module
from dst_manager.application.extensions.runtime import ExtensionRuntime
from dst_manager.config import Settings
from dst_manager.extensions.builtin.sheet_catalog.templates import DEFAULT_TEMPLATE
from dst_manager.extensions.registry import ExtensionRegistry
from dst_manager.extensions.save_grants import SaveGrantStore
from dst_manager.infrastructure.extension_workspace import ExtensionWorkspaceReader
from dst_manager.infrastructure.persistence.database import Database
from dst_manager.infrastructure.persistence.extensions import ExtensionStore
from dst_manager.interfaces.api import create_app
from dst_manager.interfaces.shell import ShellBridge

SHEET_CATALOG_ID = "dst-manager.sheet-catalog"
ACTION_ID = "export-xlsx"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def make_client(tmp_path, save_grants=None, **kwargs) -> TestClient:
    return TestClient(
        create_app(
            Settings(data_dir=tmp_path / "data"), save_grants=save_grants, **kwargs
        )
    )


def grant_store(client: TestClient) -> SaveGrantStore:
    """API runtime 持有的授权存储（桌面装配注入同一实例）。"""
    return client.app.state.extension_runtime.save_grants


def candidate_files(client: TestClient) -> list[Path]:
    """应用临时候选目录的残留文件（成功/失败后都必须为空）。"""
    root = Path(client.app.state.extension_runtime.proposal_root)
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []


def template_payload(template=DEFAULT_TEMPLATE, template_id=None) -> dict:
    return {
        "template_id": str(template_id) if template_id else None,
        "name": template.name,
        "schema_version": template.schema_version,
        "columns": [
            {
                "column_id": str(column.column_id),
                "header": column.header,
                "expression": column.expression,
            }
            for column in template.columns
        ],
    }


def draft_template() -> dict:
    """未保存草稿模板：自定义表头与表达式（template_id=null）。"""
    return {
        "template_id": None,
        "name": "未保存草稿",
        "schema_version": 1,
        "columns": [
            {
                "column_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "export:number")),
                "header": "编号",
                "expression": "{sheet.number}",
            }
        ],
    }


def open_workspace(client: TestClient, tiny_workspace) -> dict:
    opened = client.post("/api/workspaces/open", json={"dst_path": str(tiny_workspace[0])})
    assert opened.status_code == 200
    return opened.json()


def preview_action(client: TestClient, workspace: dict, template=None) -> dict:
    body = template if template is not None else template_payload()
    resp = client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/{ACTION_ID}/preview",
        json={
            "workspace_id": workspace["id"],
            "base_revision_id": workspace["revision_id"],
            "template": body,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def create_grant(store: SaveGrantStore, workspace: dict, target: Path):
    return store.create(SHEET_CATALOG_ID, ACTION_ID, workspace["id"], target)


def execute_action(client: TestClient, workspace: dict, preview_body: dict, grant_id: str, template=None):
    body = template if template is not None else template_payload()
    return client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/{ACTION_ID}/execute",
        json={
            "workspace_id": workspace["id"],
            "base_revision_id": workspace["revision_id"],
            "template": body,
            "preview_digest": preview_body["preview_digest"],
            "save_grant_id": grant_id,
        },
    )


def assert_error_contract(body: dict) -> None:
    assert set(body) == {"code", "message_key", "params", "message"}
    assert body["code"] and body["message_key"] and body["message"]
    assert isinstance(body["params"], dict)


# ---------------------------------------------------------------------------
# 预览后执行成功：XLSX 回读、Artifact 登记与查询
# ---------------------------------------------------------------------------


def test_preview_then_execute_roundtrip_registers_artifact(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    target = tmp_path / "exports"
    target.mkdir()
    grant = create_grant(grant_store(client), workspace, target / "图纸目录.xlsx")
    preview_body = preview_action(client, workspace)

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 成功响应只含 SPEC §8.2 四字段：不含 sha256/source_revision/extension_version
    assert set(body) == {"artifact_id", "file_name", "output_path", "warnings"}
    assert body["file_name"] == "图纸目录.xlsx"
    assert Path(body["output_path"]).is_file()
    assert body["warnings"] == []

    # openpyxl 回读真实落盘文件（SPEC §9）
    workbook = load_workbook(body["output_path"])
    assert workbook.sheetnames == ["图纸目录"]
    worksheet = workbook["图纸目录"]
    assert [cell.value for cell in worksheet[1]] == ["图号", "图名", "文件名"]
    assert [[cell.value for cell in row] for row in worksheet.iter_rows(min_row=2)] == [
        ["001", "平面", "A.dwg"]
    ]
    assert worksheet.freeze_panes == "A2"
    assert worksheet.auto_filter.ref is not None
    workbook.close()

    # Artifact 查询含后台字段与可用性派生
    artifact = client.get(f"/api/artifacts/{body['artifact_id']}")
    assert artifact.status_code == 200
    record = artifact.json()
    assert record["extension_id"] == SHEET_CATALOG_ID
    assert record["extension_version"] == "0.1.0"
    assert record["workspace_id"] == workspace["id"]
    assert record["source_revision_id"] == workspace["revision_id"]
    assert record["kind"] == "sheet-catalog"
    assert record["media_type"] == XLSX_MEDIA_TYPE
    assert record["management_relation"] == "external"
    assert record["file_name"] == "图纸目录.xlsx"
    assert record["availability"] == "AVAILABLE"
    saved = Path(body["output_path"])
    assert record["size_bytes"] == saved.stat().st_size
    assert record["sha256"] == hashlib.sha256(saved.read_bytes()).hexdigest()

    # 应用临时候选目录清空（SPEC §10）
    assert candidate_files(client) == []


def test_unsaved_draft_template_executes_without_server_state(tmp_path, tiny_workspace):
    """模板来自请求快照：未保存草稿（template_id=null）也能执行。"""
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "草稿.xlsx")
    template = draft_template()
    preview_body = preview_action(client, workspace, template)

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id, template)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    workbook = load_workbook(body["output_path"])
    worksheet = workbook["图纸目录"]
    assert [cell.value for cell in worksheet[1]] == ["编号"]
    assert worksheet["A2"].value == "001"
    workbook.close()
    assert candidate_files(client) == []


# ---------------------------------------------------------------------------
# REPREVIEW_REQUIRED：修订 / 模板 / 扩展版本 / 动作摘要变化
# ---------------------------------------------------------------------------


def test_revision_change_requires_repreview_and_keeps_grant(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)
    stale = dict(workspace)
    stale["revision_id"] = "f" * 64

    resp = execute_action(client, stale, preview_body, grant.save_grant_id)

    assert resp.status_code == 409
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "REPREVIEW_REQUIRED"
    assert body["message_key"] == "errors.extension.repreviewRequired"
    # 授权未被烧毁：刷新预览后可用同一授权重试（保留编辑语义）
    assert grant_store(client).active_count() == 1
    retry = execute_action(client, workspace, preview_body, grant.save_grant_id)
    assert retry.status_code == 200


def test_template_change_requires_repreview(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)
    changed = draft_template()  # 与预览所用模板不同列

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id, changed)

    assert resp.status_code == 409
    assert resp.json()["code"] == "REPREVIEW_REQUIRED"


def test_extension_version_change_requires_repreview(tmp_path, tiny_workspace, monkeypatch):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)
    monkeypatch.setattr(extension_module, "EXTENSION_VERSION", "9.9.9")

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 409
    assert resp.json()["code"] == "REPREVIEW_REQUIRED"


def test_action_summary_change_requires_repreview(tmp_path, tiny_workspace, monkeypatch):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)
    monkeypatch.setattr(extension_module, "PREVIEW_ACTION_ID", "export-xlsx-v2")

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 409
    assert resp.json()["code"] == "REPREVIEW_REQUIRED"


def test_capability_unavailable_returns_503_and_keeps_grant(tmp_path, tiny_workspace, monkeypatch):
    # 能力不可发放（WAITING_DEPENDENCY）：执行不得编造结果；预览先于执行不可用
    monkeypatch.setattr(registry_module, "AVAILABLE_CAPABILITIES", frozenset())
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")

    resp = execute_action(client, workspace, {"preview_digest": "0" * 64}, grant.save_grant_id)

    assert resp.status_code == 503
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert grant_store(client).active_count() == 1


def test_disabled_extension_rejects_execute(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)
    assert client.patch(
        f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": False}
    ).status_code == 200

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 409
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_DISABLED"


# ---------------------------------------------------------------------------
# 保存授权：无效 / 漂移 / 复用
# ---------------------------------------------------------------------------


def test_unknown_grant_rejected_with_save_grant_invalid(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    preview_body = preview_action(client, workspace)

    resp = execute_action(client, workspace, preview_body, "no-such-grant")

    assert resp.status_code == 409
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "SAVE_GRANT_INVALID"
    assert body["message_key"] == "errors.extension.saveGrantInvalid"


def test_mismatched_workspace_grant_rejected(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = SaveGrantStore().create(SHEET_CATALOG_ID, ACTION_ID, "ws-other", exports / "out.xlsx")
    preview_body = preview_action(client, workspace)

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 409
    assert resp.json()["code"] == "SAVE_GRANT_INVALID"


def test_drifted_destination_rejected_with_export_destination_changed(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)
    (exports / "out.xlsx").write_bytes(b"created after grant")

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 409
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXPORT_DESTINATION_CHANGED"
    assert body["message_key"] == "errors.extension.exportDestinationChanged"
    assert not candidate_files(client)


def test_grant_cannot_be_reused_after_successful_execute(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)
    assert execute_action(client, workspace, preview_body, grant.save_grant_id).status_code == 200

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 409
    assert resp.json()["code"] == "SAVE_GRANT_INVALID"


# ---------------------------------------------------------------------------
# 候选失败：不登记 Artifact、不留半文件
# ---------------------------------------------------------------------------


def test_invalid_candidate_fails_without_artifact(tmp_path, tiny_workspace, monkeypatch):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)

    def broken_write_candidate(path, headers, rows):
        path.write_bytes(b"not an xlsx")
        from dst_manager.extensions.builtin.sheet_catalog.workbook import (
            WorkbookSummary,
        )

        return WorkbookSummary(worksheet_name="图纸目录", headers=tuple(headers), data_rows=len(rows))

    monkeypatch.setattr(extension_module, "write_candidate", broken_write_candidate)

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 503
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "ARTIFACT_WRITE_FAILED"
    assert body["message_key"] == "errors.extension.artifactWriteFailed"
    # 目标未被写入、无半文件残留、无 Artifact 登记
    assert not (exports / "out.xlsx").exists()
    assert list(exports.iterdir()) == []
    assert candidate_files(client) == []
    with client.app.state.service.database.sessions() as session:
        assert session.execute(text("SELECT COUNT(*) FROM artifacts")).scalar_one() == 0


def test_replace_failure_keeps_old_target_without_artifact(tmp_path, tiny_workspace, monkeypatch):
    """批次三检查点：os.replace 失败 → 旧目标字节保持、零半文件、零 Artifact。"""
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    target = exports / "out.xlsx"
    target.write_bytes(b"old user file")
    grant = create_grant(grant_store(client), workspace, target)
    preview_body = preview_action(client, workspace)

    def broken_replace(src, dst):
        raise OSError("replace locked")

    monkeypatch.setattr("dst_manager.extensions.artifacts.os.replace", broken_replace)

    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)

    assert resp.status_code == 503
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "ARTIFACT_WRITE_FAILED"
    # 旧目标字节保持、目标目录无半文件残留、无 Artifact 登记
    assert target.read_bytes() == b"old user file"
    assert list(exports.iterdir()) == [target]
    assert candidate_files(client) == []
    with client.app.state.service.database.sessions() as session:
        assert session.execute(text("SELECT COUNT(*) FROM artifacts")).scalar_one() == 0


def test_execute_without_grant_channel_returns_contract_503(tmp_path, tiny_workspace):
    """授权通道未装配（如最小测试装配）时契约化拒绝，绝不 AttributeError。"""
    settings = Settings(data_dir=tmp_path / "data")
    settings.data_dir.mkdir(parents=True)
    database = Database(settings.database_url)
    runtime = ExtensionRuntime(
        ExtensionRegistry(),
        ExtensionStore(database.sessions),
        reader=ExtensionWorkspaceReader(database.sessions),
    )
    client = TestClient(create_app(settings, extension_runtime=runtime))
    workspace = open_workspace(client, tiny_workspace)
    preview_body = preview_action(client, workspace)

    resp = execute_action(client, workspace, preview_body, "any-grant")

    assert resp.status_code == 503
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Artifact 三态可用性派生
# ---------------------------------------------------------------------------


def test_artifact_availability_tracks_filesystem_state(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    preview_body = preview_action(client, workspace)
    executed = execute_action(client, workspace, preview_body, grant.save_grant_id)
    artifact_id = executed.json()["artifact_id"]
    output = Path(executed.json()["output_path"])

    # 文件被删除 → MISSING（历史记录不伪装成当前可用）
    output.unlink()
    assert client.get(f"/api/artifacts/{artifact_id}").json()["availability"] == "MISSING"

    # 文件被替换为不同内容 → CHANGED
    output.write_bytes(b"different content")
    assert client.get(f"/api/artifacts/{artifact_id}").json()["availability"] == "CHANGED"


# ---------------------------------------------------------------------------
# 桌面共同装配：桥与 API runtime 共享同一个 SaveGrantStore
# ---------------------------------------------------------------------------


class _FakeWindow:
    def __init__(self, result):
        self._result = result

    def create_file_dialog(self, *args, **kwargs):
        return self._result


class _FakeContext:
    """可信上下文替身：只暴露桥消费的最小面。"""

    def __init__(self, workspace_id: str, dst_path: Path):
        self._workspace_id = workspace_id
        self.dst_path = dst_path
        self.root = dst_path.parent

    @property
    def current(self):
        return self

    @property
    def workspace_id(self) -> str:
        return self._workspace_id


def test_bridge_created_grant_is_consumable_by_api_execute(tmp_path, tiny_workspace):
    """run_desktop 共同装配的行为钉子：桥创建的授权必须能被 API 执行消费。"""
    store = SaveGrantStore()
    client = make_client(tmp_path, save_grants=store)
    assert client.app.state.extension_runtime.save_grants is store
    workspace = open_workspace(client, tiny_workspace)
    exports = tmp_path / "exports"
    exports.mkdir()
    bridge = ShellBridge(
        context=_FakeContext(workspace["id"], tiny_workspace[0]),
        registry=client.app.state.extension_runtime.registry,
        save_grants=store,
    )
    bridge.bind(_FakeWindow(str(exports / "桥选.xlsx")))

    result = bridge.request_extension_save(SHEET_CATALOG_ID, ACTION_ID, workspace["id"])

    assert result["ok"] is True
    grant_id = result["value"]["save_grant_id"]
    preview_body = preview_action(client, workspace)
    resp = execute_action(client, workspace, preview_body, grant_id)
    assert resp.status_code == 200, resp.text
    assert Path(resp.json()["output_path"]).name == "桥选.xlsx"


# ---------------------------------------------------------------------------
# 只读不变量：预览→执行前后工程与数据库零写入
# ---------------------------------------------------------------------------


def test_preview_and_execute_leave_project_and_database_read_only(tmp_path, tiny_workspace):
    client = make_client(tmp_path, save_grants=SaveGrantStore())
    workspace = open_workspace(client, tiny_workspace)
    dst_path = tiny_workspace[0]
    dwg_path = dst_path.parent / "A.dwg"
    project_root = dst_path.parent
    data_dir = tmp_path / "data"
    exports = tmp_path / "exports"
    exports.mkdir()

    def project_tree():
        # 测试布局折衷：应用数据目录与用户选择的保存目标都位于工程目录内，
        # 二者都不属于工程内容，排除后只对工程文件树做不变量比对。
        return {
            str(p.relative_to(project_root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in project_root.rglob("*")
            if p.is_file() and data_dir not in p.parents and exports not in p.parents
        }

    def db_counts():
        with client.app.state.service.database.sessions() as session:
            return {
                table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in ("jobs", "document_revisions", "workspace_write_locks")
            }

    before_tree = project_tree()
    before_counts = db_counts()
    before_bytes = {p: p.read_bytes() for p in (dst_path, dwg_path)}
    before_mtime = {p: p.stat().st_mtime_ns for p in (dst_path, dwg_path)}

    preview_body = preview_action(client, workspace)
    assert preview_body["executable"] is True
    grant = create_grant(grant_store(client), workspace, exports / "out.xlsx")
    resp = execute_action(client, workspace, preview_body, grant.save_grant_id)
    assert resp.status_code == 200

    assert project_tree() == before_tree
    assert db_counts() == before_counts
    for path in (dst_path, dwg_path):
        assert path.read_bytes() == before_bytes[path]
        assert path.stat().st_mtime_ns == before_mtime[path]
    assert candidate_files(client) == []
