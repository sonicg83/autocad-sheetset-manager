"""扩展平台统一管理 API 集成测试（PLAN-DM-020 Task 3/6 / ARCH-DM-006 §8、§12）。

覆盖：列表/启停/重启持久化、未知扩展、禁用动作、错误清单与工厂失败隔离、
设置 ``expected_revision`` 冲突、偏好不存在默认值、Artifact 404、平台错误码
的稳定 ``message_key`` 与结构化 ``params``、OpenAPI 端点与错误契约、启动顺序
（数据库迁移完成 → 发布恢复完成 → ``registry.discover()``），以及 Task 6 的
真实数据预览动作（行/字段目录/摘要/错误警告契约、修订不匹配、偏好 best-effort
降级），以及 Task 11B（SC-06）的模板设置 PUT 服务端强制矩阵（save_templates
分派：casefold 重名/100 上限/内置不可变/高 schema 保留/合法回读与通用路径隔离），
以及 PLAN-DM-025 Task 2 的通用设置编排（Schema v2 升级、
Provider 全权校验、过滤关键词规范回读与字段级超限错误、未知高版本只读保留），
以及 PLAN-DM-025 Task 3 的设置呈现与只读诊断契约（摘要 ``settings_contribution``、
``generated`` 字段项由 Provider 元数据与 Manifest 呈现合并、``custom`` 空字段项、
``effective_value``/``read_only``/``diagnostic_code``，以及更高 Schema 的
HTTP 409 ``EXTENSION_SETTINGS_SCHEMA_NEWER``），以及修复轮 1 的 R9 复核（
声明设置却无法由 Provider 解释时的 503 诊断与无部分结果、Provider 重绑定
时字段规格访问器与 ``get_settings`` 同形的错误映射），以及 PLAN-DM-025
Task 4 的设置快照绑定（预览回传 ``settings_revision``/``filtered_rows``、
输出图纸过滤经服务端规范化关键词作用于预览行与计数）。
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import dst_manager.application.service as service_module
import dst_manager.extensions.registry as registry_module
from dst_manager.application.extensions.runtime import ExtensionRuntime
from dst_manager.config import Settings
from dst_manager.extensions.builtin.index import (
    BUILTIN_EXTENSION_INDEX,
    BuiltinExtensionEntry,
)
from dst_manager.extensions.builtin.sheet_catalog.settings import (
    MAX_EXCLUDED_TITLE_KEYWORD_CHARS,
    MAX_EXCLUDED_TITLE_KEYWORDS,
    SHEET_CATALOG_SETTINGS_PROVIDER,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import DEFAULT_TEMPLATE
from dst_manager.extensions.registry import ExtensionRegistry
from dst_manager.extensions.settings import SettingsFieldSpec
from dst_manager.infrastructure.extension_workspace import ExtensionWorkspaceReader
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
    "EXTENSION_SETTINGS_SCHEMA_NEWER",
    "EXTENSION_ACTION_NOT_FOUND",
    "SAVE_GRANT_INVALID",
    "EXPORT_DESTINATION_CHANGED",
    "REPREVIEW_REQUIRED",
    "ARTIFACT_WRITE_FAILED",
)

#: 列表摘要 error_code 的封闭诊断码词汇（Ruling-7；错误响应用平台码，摘要暴露诊断码）。
DIAGNOSTIC_CODES = frozenset(
    {
        "EXTENSION_MANIFEST_INVALID",
        "EXTENSION_HOST_CONTRACT_MISMATCH",
        "EXTENSION_CAPABILITY_UNKNOWN",
        "EXTENSION_CAPABILITY_UNAVAILABLE",
        "EXTENSION_START_FAILED",
        "EXTENSION_STOP_FAILED",
    }
)


def make_client(tmp_path, **kwargs) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path / "data"), **kwargs))


def make_runtime(tmp_path, entries) -> ExtensionRuntime:
    """测试注入用运行时：独立 sqlite 库承载扩展状态/设置/偏好/Artifact。"""
    database = Database(f"sqlite:///{(tmp_path / 'extension-tests.db').as_posix()}")
    sessions = database.sessions
    return ExtensionRuntime(
        ExtensionRegistry(),
        ExtensionStore(sessions),
        reader=ExtensionWorkspaceReader(sessions),
    )


def template_payload(template=DEFAULT_TEMPLATE, template_id=None) -> dict:
    """把模板对象投影为预览请求负载（SPEC-DM-012 §8.1 的模板快照形态）。"""
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


def open_workspace(client: TestClient, tiny_workspace) -> dict:
    opened = client.post("/api/workspaces/open", json={"dst_path": str(tiny_workspace[0])})
    assert opened.status_code == 200
    return opened.json()


def post_preview(client: TestClient, workspace: dict, template=None, template_id="unset", **overrides):
    if isinstance(template, dict):
        template_dict = template
    else:
        template_dict = template_payload(template) if template is not None else template_payload()
    if template_id != "unset":
        template_dict["template_id"] = str(template_id) if template_id else None
    payload = {
        "workspace_id": workspace["id"],
        "base_revision_id": workspace["revision_id"],
        "template": template_dict,
    }
    payload.update(overrides)
    return client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/preview", json=payload
    )


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
    # Task 6 已接线 CapabilityBroker：快照能力真实可发放，状态为 AVAILABLE
    assert item["status"] == "AVAILABLE"
    assert item["error_code"] is None
    # 摘要 error_code 为 None（可用）或封闭诊断码词汇（Ruling-7），禁止原始异常文本
    assert all(
        entry["error_code"] is None or entry["error_code"] in DIAGNOSTIC_CODES
        for entry in items
    )
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
    # 摘要只声明设置呈现方式：图纸目录使用宿主编译期白名单里的专属组件
    assert item["settings_contribution"] == {
        "presentation": "custom",
        "route_key": "sheet-catalog-settings",
    }


def test_patch_state_persists_across_restart(tmp_path):
    client = make_client(tmp_path)

    patched = client.patch(f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": False})

    assert patched.status_code == 200
    body = patched.json()
    assert body["extension_id"] == SHEET_CATALOG_ID
    assert body["enabled"] is False
    # 用户停用真实排空并停止扩展实例：状态机进入 STOPPED（能力已接线）
    assert body["status"] == "STOPPED"
    assert body["error_code"] is None

    restarted = make_client(tmp_path)
    assert restarted.get("/api/extensions").json()[0]["enabled"] is False


def test_enable_after_user_disable_returns_extension_to_available(tmp_path):
    client = make_client(tmp_path)
    assert client.patch(
        f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": False}
    ).status_code == 200

    resp = client.patch(f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["status"] == "AVAILABLE"
    assert body["error_code"] is None


def test_enable_rejected_while_capability_missing_keeps_persisted_intent(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    assert client.patch(
        f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": False}
    ).status_code == 200
    # 快照能力重新不可发放（环境退化）：启用必须被拒绝而非伪装成功
    monkeypatch.setattr(registry_module, "AVAILABLE_CAPABILITIES", frozenset())

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
            "/api/extensions/no-such/actions/export-xlsx/preview",
            json={
                "workspace_id": "ws-1",
                "base_revision_id": "0" * 64,
                "template": template_payload(),
            },
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
            output_path=str(tmp_path / "missing" / "图纸目录.xlsx"),
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
    # 输出文件不存在：历史记录不伪装成当前可用（Task 9 可用性派生）
    assert body["availability"] == "MISSING"


def test_artifact_availability_reports_changed_not_500_when_target_unreadable(
    tmp_path, monkeypatch
):
    """fix round 3：目标文件在 stat 与 open 之间被锁定/权限变化（Windows 上
    Excel/AV 占用是常态）时，``GET /api/artifacts/{id}`` 必须按契约返回
    CHANGED 可用性，绝不逃逸为非契约 500。"""
    from pathlib import Path

    output_path = tmp_path / "图纸目录.xlsx"
    content = b"catalog-bytes"
    output_path.write_bytes(content)

    client = make_client(tmp_path)
    store = ExtensionStore(client.app.state.service.database.sessions)
    store.create_artifact(
        ArtifactRecord(
            artifact_id="artifact-locked",
            extension_id=SHEET_CATALOG_ID,
            extension_version="0.1.0",
            workspace_id="ws-1",
            source_revision_id="rev-1",
            kind="sheet-catalog",
            media_type=XLSX_MEDIA_TYPE,
            management_relation="external",
            output_path=str(output_path),
            file_name="图纸目录.xlsx",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            created_at=datetime(2026, 9, 10, 8, 0, 0, tzinfo=UTC),
        )
    )

    real_open = Path.open

    def locked_open(self, *args, **kwargs):
        if self == output_path:
            raise PermissionError(13, "被其他程序占用")
        return real_open(self, *args, **kwargs)

    # 健全性前置：文件可读时按登记身份判为 AVAILABLE
    assert client.get("/api/artifacts/artifact-locked").json()["availability"] == "AVAILABLE"

    monkeypatch.setattr(Path, "open", locked_open)

    resp = client.get("/api/artifacts/artifact-locked")

    assert resp.status_code == 200
    # 文件在但身份无法确认：与"内容可能已被改动"同样不可信，归为 CHANGED
    assert resp.json()["availability"] == "CHANGED"


# ---------------------------------------------------------------------------
# 设置与偏好
# ---------------------------------------------------------------------------


def catalog_template_json(name, columns=(("图号", "{sheet.number}"),), template_id=None) -> dict:
    """模板设置负载中的单个用户模板 JSON（与前端 settingsPayload 同形态）。"""
    base = template_id or uuid.uuid5(uuid.NAMESPACE_URL, f"settings:{name}")
    return {
        "template_id": str(base),
        "name": name,
        "schema_version": 1,
        "columns": [
            {
                "column_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"settings:{name}:{header}")),
                "header": header,
                "expression": expression,
            }
            for header, expression in columns
        ],
    }


def assert_settings_versioned(
    body: dict, schema_version: int, revision: int, value: dict
) -> None:
    """设置响应既有的版本化三字段（Task 3 追加的呈现/诊断字段由专项用例覆盖）。"""
    assert {key: body[key] for key in ("schema_version", "revision", "value")} == {
        "schema_version": schema_version,
        "revision": revision,
        "value": value,
    }


def put_settings(client: TestClient, templates, expected_revision=0, keywords=None):
    """按前端保存负载形态 PUT 图纸目录扩展设置（Schema v2 完整快照）。

    模板与过滤关键词同属一份设置修订：省略 ``keywords`` 即不写入显式覆盖。
    """
    value: dict[str, object] = {"schema_version": 2, "user_templates": list(templates)}
    if keywords is not None:
        value["excluded_title_keywords"] = keywords
    return client.put(
        f"/api/extensions/{SHEET_CATALOG_ID}/settings",
        json={"schema_version": 2, "expected_revision": expected_revision, "value": value},
    )


def test_settings_put_validates_templates_and_roundtrips(tmp_path):
    """Task 11B（SC-06 服务端接线）：图纸目录设置 PUT 分派 save_templates
    强制全部模板规则；合法保存返回新修订且 GET 规范回读一致。"""
    client = make_client(tmp_path)
    url = f"/api/extensions/{SHEET_CATALOG_ID}/settings"

    default = client.get(url)
    assert default.status_code == 200
    # 从未保存：返回当前 Schema 的零值（内置模板是代码常量，不在 value 中）
    assert_settings_versioned(default.json(), 2, 0, {})

    template = catalog_template_json("市政标准目录")
    saved = put_settings(client, [template])
    assert saved.status_code == 200
    assert_settings_versioned(
        saved.json(), 2, 1, {"schema_version": 2, "user_templates": [template]}
    )
    # 保存结果可回读：GET 返回同一规范负载（内置默认模板是代码常量，不在 value 中）
    assert client.get(url).json() == saved.json()

    # 未知 schema 仍由设置契约先行拒绝（422），不进入 Provider 校验
    mismatch = client.put(url, json={"schema_version": 1, "value": {}, "expected_revision": 1})
    assert mismatch.status_code == 422
    body = mismatch.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    assert body["params"] == {"settings_schema": 2, "submitted": 1}


def test_settings_put_stale_revision_returns_settings_conflict(tmp_path):
    """ARCH-DM-006 §8.1：PUT 没带 ``expected_revision`` 的并发写入返回 409。

    并发由 ExtensionStore 条件更新判定，错误沿用框架设置错误契约；前端
    ``useSheetCatalog`` 对 ``SHEET_CATALOG_TEMPLATE_CONFLICT`` 与本 409 同样
    保留本地编辑。
    """
    client = make_client(tmp_path)
    url = f"/api/extensions/{SHEET_CATALOG_ID}/settings"
    assert put_settings(client, [catalog_template_json("市政标准目录")]).status_code == 200

    stale = put_settings(client, [], expected_revision=0)

    assert stale.status_code == 409
    body = stale.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    assert body["message_key"] == "errors.extension.settingsInvalid"
    assert body["params"] == {"expected_revision": 0, "current_revision": 1}
    # 冲突时旧值未被覆盖
    assert client.get(url).json()["revision"] == 1


def test_settings_put_normalizes_filter_keywords_and_roundtrips(tmp_path):
    """SPEC-DM-012 §6.4：PUT 原始文本，GET 返回规范化数组；空文本清除覆盖。

    PLAN-DM-025 Task 3：规范化结果同时体现在持久值（``value``）与 Provider
    解析后的有效值（``effective_value``）上，custom 呈现不生成 ``items``。
    """
    client = make_client(tmp_path)
    url = f"/api/extensions/{SHEET_CATALOG_ID}/settings"

    saved = put_settings(client, [catalog_template_json("市政标准目录")], keywords="草图， TEMP,,作废,temp")
    assert saved.status_code == 200
    assert_settings_versioned(
        saved.json(),
        2,
        1,
        {
            "schema_version": 2,
            "user_templates": [catalog_template_json("市政标准目录")],
            "excluded_title_keywords": ["草图", "TEMP", "作废"],
        },
    )
    assert saved.json()["items"] == []
    assert saved.json()["effective_value"]["excluded_title_keywords"] == [
        "草图",
        "TEMP",
        "作废",
    ]
    # 保存结果可回读：GET 返回同一完整契约（含有效值与字段项）
    assert client.get(url).json() == saved.json()
    cleared = put_settings(client, [catalog_template_json("市政标准目录")], expected_revision=1, keywords="  ,, ")
    assert cleared.status_code == 200
    assert cleared.json()["value"] == {
        "schema_version": 2,
        "user_templates": [catalog_template_json("市政标准目录")],
    }
    # 空文本清除显式覆盖：有效值仍返回空数组（默认值不是用户配置）
    assert cleared.json()["effective_value"]["excluded_title_keywords"] == []


def test_settings_put_rejects_filter_keyword_count_over_limit(tmp_path):
    client = make_client(tmp_path)
    too_many = ",".join(
        f"k{index:02d}" for index in range(MAX_EXCLUDED_TITLE_KEYWORDS + 1)
    )

    rejected = put_settings(client, [], keywords=too_many)

    assert rejected.status_code == 422
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    assert body["params"] == {
        "field": "excluded_title_keywords",
        "kind": "count",
        "limit": MAX_EXCLUDED_TITLE_KEYWORDS,
        "actual": MAX_EXCLUDED_TITLE_KEYWORDS + 1,
    }
    # 超限明确拒绝、不截断：未写入任何设置行
    assert client.get(f"/api/extensions/{SHEET_CATALOG_ID}/settings").json()["value"] == {}


def test_settings_put_rejects_filter_keyword_length_over_limit(tmp_path):
    client = make_client(tmp_path)
    too_long = "x" * (MAX_EXCLUDED_TITLE_KEYWORD_CHARS + 1)

    rejected = put_settings(client, [], keywords=too_long)

    assert rejected.status_code == 422
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    assert body["params"] == {
        "field": "excluded_title_keywords",
        "kind": "length",
        "limit": MAX_EXCLUDED_TITLE_KEYWORD_CHARS,
        "actual": MAX_EXCLUDED_TITLE_KEYWORD_CHARS + 1,
    }
    assert client.get(f"/api/extensions/{SHEET_CATALOG_ID}/settings").json()["value"] == {}


@pytest.mark.parametrize(
    ("existing", "incoming"),
    [
        pytest.param(["市政标准目录"], "市政标准目录", id="用户模板名重复"),
        pytest.param([], "默认图纸目录（内置）", id="与内置默认模板同名"),
        pytest.param(["Catalog"], "catalog", id="casefold 重复"),
    ],
)
def test_settings_put_rejects_duplicate_template_names_casefold(tmp_path, existing, incoming):
    client = make_client(tmp_path)
    url = f"/api/extensions/{SHEET_CATALOG_ID}/settings"
    assert put_settings(client, [catalog_template_json(name) for name in existing]).status_code == 200

    rejected = put_settings(
        client,
        # 冲突名用独立 UUID：catalog_template_json 按 name 派生 template_id，
        # 同名条目会先撞 UUID 唯一检查；本用例钉住的是名称唯一性。
        [*[catalog_template_json(name) for name in existing],
         catalog_template_json(incoming, template_id=uuid.uuid4())],
        expected_revision=1,
    )

    assert rejected.status_code == 409
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "SHEET_CATALOG_COLUMN_DUPLICATE"
    assert body["message_key"] == "errors.sheetCatalog.columnDuplicate"
    assert body["params"] == {"header": incoming}
    # 原设置不变：不存在半保存状态
    assert client.get(url).json()["value"]["user_templates"] == [
        catalog_template_json(name) for name in existing
    ]


def test_settings_put_rejects_more_than_100_user_templates(tmp_path):
    client = make_client(tmp_path)
    templates = [catalog_template_json(f"模板{i:03d}") for i in range(101)]

    rejected = put_settings(client, templates)

    assert rejected.status_code == 422
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "SHEET_CATALOG_TEMPLATE_LIMIT"
    assert body["message_key"] == "errors.sheetCatalog.templateLimit"
    assert body["params"] == {"kind": "user_templates", "limit": 100, "actual": 101}
    assert client.get(f"/api/extensions/{SHEET_CATALOG_ID}/settings").json()["value"] == {}


def test_settings_put_rejects_builtin_mutations(tmp_path):
    """内置默认模板是服务端代码常量：同名影子模板与内置形态（无 UUID）条目均拒绝。"""
    client = make_client(tmp_path)

    shadow = put_settings(client, [catalog_template_json("默认图纸目录（内置）")])
    assert shadow.status_code == 409
    body = shadow.json()
    assert_error_contract(body)
    assert body["code"] == "SHEET_CATALOG_COLUMN_DUPLICATE"
    assert body["params"] == {"header": "默认图纸目录（内置）"}

    builtin_shaped = dict(catalog_template_json("市政标准目录"), template_id=None)
    rejected = put_settings(client, [builtin_shaped])
    assert rejected.status_code == 422
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    assert "SHEET_CATALOG_TEMPLATE_ID_REQUIRED" in body["message"]
    # 内置默认模板始终由代码常量提供：GET value 不含任何内置形态条目
    assert client.get(f"/api/extensions/{SHEET_CATALOG_ID}/settings").json()["value"] == {}


def test_settings_put_rejects_duplicate_template_ids(tmp_path):
    """PLAN-DM-024 Task 3 / MEMO-DM-031 F5：直接 PUT 设置端点提交重复
    ``template_id`` 必须失败，持久化 revision/value 均不变；错误体保持现有
    扩展设置无效契约（EXTENSION_SETTINGS_INVALID，不扩张目录业务错误码）。"""
    client = make_client(tmp_path)
    url = f"/api/extensions/{SHEET_CATALOG_ID}/settings"
    template = catalog_template_json("市政标准目录")
    assert put_settings(client, [template]).status_code == 200

    duplicate_id = dict(catalog_template_json("建筑专业目录"), template_id=template["template_id"])
    rejected = put_settings(client, [template, duplicate_id], expected_revision=1)

    assert rejected.status_code == 422
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    # 稳定诊断前缀（与 TEMPLATE_ID_REQUIRED 同通道），不是新的目录业务错误码
    assert "SHEET_CATALOG_TEMPLATE_ID_DUPLICATE" in body["message"]
    # 拒绝后持久化原样：revision 与 value 都不变，不存在半保存状态
    assert_settings_versioned(
        client.get(url).json(),
        2,
        1,
        {"schema_version": 2, "user_templates": [template]},
    )


def test_settings_schema_newer_get_is_read_only_and_put_rejected_with_409(tmp_path):
    """ARCH-DM-006 §8.1/§12：已存设置 Schema 高于当前版本时只读保留且拒绝覆盖。

    Ruling R9：Task 2 曾把本用例降级为 Runtime 层断言，导致 HTTP 层的
    ``_error_response`` 文案键缺口（缺 ``EXTENSION_SETTINGS_SCHEMA_NEWER`` →
    ``KeyError`` → 500）逃过测试。本用例重新钉住 HTTP 契约：GET 为 200 只读
    视图（``read_only`` + 稳定 ``diagnostic_code``），PUT 以同一稳定 ``code``
    与 409 拒绝，且原 JSON 逐键保留。
    """
    client = make_client(tmp_path)
    store = ExtensionStore(client.app.state.service.database.sessions)
    raw_value = {"user_templates": [{"unknown": "future-shape"}], "future_field": 1}
    store.put_settings(SHEET_CATALOG_ID, 3, raw_value, 0)
    url = f"/api/extensions/{SHEET_CATALOG_ID}/settings"

    read = client.get(url)

    assert read.status_code == 200
    payload = read.json()
    # GET 返回原 JSON 的只读视图：Schema 与内容逐键一致
    assert_settings_versioned(payload, 3, 1, raw_value)
    assert payload["read_only"] is True
    assert payload["diagnostic_code"] == "EXTENSION_SETTINGS_SCHEMA_NEWER"
    # custom 呈现不生成字段项，也不得把未知高版本渲染成当前语义
    assert payload["items"] == []

    rejected = client.put(
        url,
        json={
            "schema_version": 2,
            "expected_revision": 1,
            "value": {"schema_version": 2, "user_templates": []},
        },
    )

    assert rejected.status_code == 409
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_SCHEMA_NEWER"
    assert body["message_key"] == "errors.extension.schemaNewer"
    assert body["params"] == {
        "extension_id": SHEET_CATALOG_ID,
        "settings_schema": 3,
        "current_schema": 2,
    }
    # 原 JSON 原样保留（schema 3、内容逐键一致，未被 v2 负载覆盖）
    assert client.get(url).json() == payload


def test_generated_settings_read_only_view_still_exposes_current_field_items(tmp_path):
    """未知高版本的 GET 仍返回当前程序可生成的字段项：``items`` 与 ``read_only``
    正交——前者描述当前可渲染字段集，后者只说明持久值来自更高版本、禁止覆盖。"""
    client = generated_settings_client(tmp_path)
    raw_value = {"max_rows": 999, "future_field": True}
    client.app.state.extension_runtime.store.put_settings(
        GENERATED_SETTINGS_ID, 2, raw_value, 0
    )
    url = f"/api/extensions/{GENERATED_SETTINGS_ID}/settings"

    read = client.get(url)

    assert read.status_code == 200
    payload = read.json()
    assert_settings_versioned(payload, 2, 1, raw_value)
    assert payload["read_only"] is True
    assert payload["diagnostic_code"] == "EXTENSION_SETTINGS_SCHEMA_NEWER"
    assert [item["key"] for item in payload["items"]] == [
        "notify",
        "title",
        "mode",
        "max_rows",
        "ratio",
    ]

    rejected = client.put(
        url,
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "value": {"max_rows": 5, "notify": False},
        },
    )

    assert rejected.status_code == 409
    assert rejected.json()["code"] == "EXTENSION_SETTINGS_SCHEMA_NEWER"
    assert client.get(url).json() == payload


def test_custom_settings_presentation_returns_empty_items_and_resolved_value(tmp_path):
    """custom 呈现由宿主编译期白名单里的专属组件承载：``items`` 恒为空数组，
    有效值仍由 Provider 解析（内置模板来自代码常量，不进持久值）。"""
    client = make_client(tmp_path)
    url = f"/api/extensions/{SHEET_CATALOG_ID}/settings"

    payload = client.get(url).json()

    assert payload["items"] == []
    assert payload["read_only"] is False
    assert payload["diagnostic_code"] is None
    assert payload["value"] == {}
    assert payload["effective_value"]["builtin_template"]["name"] == DEFAULT_TEMPLATE.name
    assert payload["effective_value"]["user_templates"] == []
    assert payload["effective_value"]["excluded_title_keywords"] == []


def test_settings_put_dispatches_to_registered_provider_on_schema_v2(tmp_path):
    """fix round 1 fail-closed 钉子：登记了 Provider 就必须经 Provider 全权校验。

    模拟未来 sheet-catalog ``settings_schema`` 升级到 2：PUT 仍必须强制模板规则
    （此处用 casefold 重名触发拒绝），绝不静默退回通用 JSON 存储路径让重名/超限
    重新失去服务端强制。
    """
    manifest = tmp_path / "catalog-v2.yaml"
    manifest.write_text(
        f"""
extension_id: {SHEET_CATALOG_ID}
version: 0.2.0
extension_type: builtin
host_contract: 1
enabled_by_default: false
name_key: extensions.sheetCatalog.name
description_key: extensions.sheetCatalog.description
required_capabilities: []
permissions: []
ui_contributions: []
actions: []
settings_schema: 2
""".strip()
        + "\n",
        encoding="utf-8",
    )
    entries = (
        BuiltinExtensionEntry(
            manifest_resource=str(manifest),
            factory=_boom,
            settings_provider=SHEET_CATALOG_SETTINGS_PROVIDER,
        ),
    )
    client = make_client(
        tmp_path, extension_runtime=make_runtime(tmp_path, entries), extension_index=entries
    )

    rejected = client.put(
        f"/api/extensions/{SHEET_CATALOG_ID}/settings",
        json={
            "schema_version": 2,
            "expected_revision": 0,
            "value": {
                "schema_version": 2,
                "user_templates": [
                    catalog_template_json("Catalog"),
                    catalog_template_json("catalog"),
                ],
            },
        },
    )

    assert rejected.status_code == 409
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "SHEET_CATALOG_COLUMN_DUPLICATE"
    assert body["message_key"] == "errors.sheetCatalog.columnDuplicate"
    # 拒绝即未落库：通用路径不会接受任何负载
    assert client.get(f"/api/extensions/{SHEET_CATALOG_ID}/settings").json()["value"] == {}


def test_settings_put_other_extensions_keep_generic_json_path(tmp_path):
    """无 sheet-catalog 契约的扩展（未来）不受模板分派影响：value 原样存储回读。

    未声明设置的扩展同时锁定呈现与字段项：摘要 ``settings_contribution`` 为
    ``None``（设置中心不显示“配置”），设置响应 ``items`` 恒为空数组。
    """
    manifest = tmp_path / "plain-settings.yaml"
    manifest.write_text(
        """
extension_id: test.plain-settings
version: 0.1.0
extension_type: builtin
host_contract: 1
enabled_by_default: false
name_key: extensions.test.name
description_key: extensions.test.description
required_capabilities: []
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

    saved = client.put(
        "/api/extensions/test.plain-settings/settings",
        json={
            "schema_version": 1,
            "value": {"columns": ["{{sheet.number}}"]},
            "expected_revision": 0,
        },
    )

    assert saved.status_code == 200
    assert_settings_versioned(saved.json(), 1, 1, {"columns": ["{{sheet.number}}"]})
    # 无 Provider 的通用路径：有效值即持久值，且没有可生成字段
    assert saved.json()["effective_value"] == {"columns": ["{{sheet.number}}"]}
    assert saved.json()["items"] == []
    listed = client.get("/api/extensions").json()
    assert listed[0]["settings_contribution"] is None
    assert client.get("/api/extensions/test.plain-settings/settings").json()["items"] == []


# ---------------------------------------------------------------------------
# Task 3：设置呈现（settings_contribution / items）与只读诊断契约
# ---------------------------------------------------------------------------

#: generated 呈现的测试内载体（MEMO-DM-033 M1 / Ruling R5）：临时清单 + 假
#: Provider，经既有 ``extension_index``/``ExtensionRuntime`` 注入；生产固定
#: 索引只登记 custom 呈现的图纸目录，不为测试新增虚构扩展。
GENERATED_SETTINGS_ID = "test.generated-settings"

GENERATED_SETTINGS_MANIFEST = """
extension_id: test.generated-settings
version: 0.1.0
extension_type: builtin
host_contract: 1
enabled_by_default: false
name_key: extensions.testGenerated.name
description_key: extensions.testGenerated.description
required_capabilities: []
permissions: []
ui_contributions: []
actions: []
settings_schema: 1
settings_contribution:
  presentation: generated
  fields:
    - key: ratio
      label_key: extensions.testGenerated.ratio
      order: 30
    - key: mode
      label_key: extensions.testGenerated.mode
      description_key: extensions.testGenerated.modeDescription
      order: 15
    - key: max_rows
      label_key: extensions.testGenerated.maxRows
      description_key: extensions.testGenerated.maxRowsDescription
      order: 20
    - key: title
      label_key: extensions.testGenerated.title
      description_key: extensions.testGenerated.titleDescription
      order: 10
    - key: notify
      label_key: extensions.testGenerated.notify
      order: 10
"""


class _GeneratedSettingsProvider:
    """generated 假 Provider：五个字段覆盖控件词表、默认值与全部约束位。

    控件词表按 R8 逐项出现：``integer``（上下界）、``number``（上下界）、
    ``string``（``nullable`` + ``max_length``）、``boolean``、``enum``
    （非空 ``options``）。只强制 ``max_rows`` 范围与 ``notify`` 类型（Provider
    是校验权威）；其余字段在该假 Provider 里只作为元数据映射的载体。
    解析时补齐代码默认值，用于区分持久值 ``value`` 与有效值 ``effective_value``。
    """

    extension_id = GENERATED_SETTINGS_ID
    schema_version = 1
    field_definitions = (
        SettingsFieldSpec(
            key="max_rows", control="integer", default=10, min_value=1, max_value=100
        ),
        SettingsFieldSpec(key="notify", control="boolean", default=False),
        SettingsFieldSpec(
            key="title", control="string", default="", nullable=True, max_length=20
        ),
        SettingsFieldSpec(
            key="mode",
            control="enum",
            default="fast",
            options=("fast", "thorough"),
        ),
        SettingsFieldSpec(
            key="ratio", control="number", default=1.5, min_value=0.1, max_value=10.0
        ),
    )

    def default_value(self) -> dict[str, object]:
        return dict(GENERATED_SETTINGS_DEFAULTS)

    def migrate(
        self, stored_schema_version: int, value: dict[str, object]
    ) -> dict[str, object]:
        raise AssertionError("generated 假 Provider 是首版 Schema，没有迁移路径")

    def validate_and_normalize(self, value: dict[str, object]) -> dict[str, object]:
        rows = value.get("max_rows")
        if isinstance(rows, bool) or not isinstance(rows, int):
            raise TypeError("EXTENSION_SETTINGS_TEST_INVALID: max_rows 必须是整数")
        if not 1 <= rows <= 100:
            raise ValueError("EXTENSION_SETTINGS_TEST_INVALID: max_rows 必须在 1..100")
        notify = value.get("notify")
        if not isinstance(notify, bool):
            raise TypeError("EXTENSION_SETTINGS_TEST_INVALID: notify 必须是布尔值")
        return {"max_rows": rows, "notify": notify}

    def resolve(self, value: dict[str, object]) -> dict[str, object]:
        return {**self.default_value(), **value}


GENERATED_SETTINGS_PROVIDER = _GeneratedSettingsProvider()

#: 假 Provider 的代码默认零值：GET 未保存时 ``value`` 与 ``effective_value`` 都是它。
GENERATED_SETTINGS_DEFAULTS = {
    "max_rows": 10,
    "notify": False,
    "title": "",
    "mode": "fast",
    "ratio": 1.5,
}


def generated_settings_entries(
    tmp_path, provider=GENERATED_SETTINGS_PROVIDER
) -> tuple[BuiltinExtensionEntry, ...]:
    """测试内 generated 扩展的固定索引条目（临时清单 + 指定 Provider）。

    ``provider=None`` 得到“声明了设置却没有 Provider”的条目（§8.1 诊断载体）。
    """
    manifest = tmp_path / "generated-settings.yaml"
    manifest.write_text(GENERATED_SETTINGS_MANIFEST, encoding="utf-8")
    return (
        BuiltinExtensionEntry(
            manifest_resource=str(manifest),
            factory=_boom,
            settings_provider=provider,
        ),
    )


def generated_settings_client(tmp_path, provider=GENERATED_SETTINGS_PROVIDER) -> TestClient:
    """注入测试内 generated 扩展的客户端（清单 + 假 Provider + 临时运行时）。"""
    entries = generated_settings_entries(tmp_path, provider)
    return make_client(
        tmp_path,
        extension_runtime=make_runtime(tmp_path, entries),
        extension_index=entries,
    )


def test_generated_settings_items_merge_provider_specs_with_manifest_presentation(tmp_path):
    """ARCH-DM-006 §8.2：字段项由 Provider 的类型/默认值/约束与 Manifest 的
    label/description/order 合并，按 ``order, key`` 排序；控件词表原样输出。"""
    client = generated_settings_client(tmp_path)
    url = f"/api/extensions/{GENERATED_SETTINGS_ID}/settings"

    response = client.get(url)

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["revision"] == 0
    # 从未保存：value 是 Provider 默认零值，effective_value 是解析后的有效配置
    assert payload["value"] == GENERATED_SETTINGS_DEFAULTS
    assert payload["effective_value"] == GENERATED_SETTINGS_DEFAULTS
    assert payload["read_only"] is False
    assert payload["diagnostic_code"] is None
    # 清单声明顺序是 ratio/mode/max_rows/title/notify：结果必须按 (order, key) 重排
    # （notify 与 title 同为 10 时按 key，mode 15 插在中间，max_rows 20、ratio 30）
    assert payload["items"] == [
        {
            "key": "notify",
            "label_key": "extensions.testGenerated.notify",
            "description_key": None,
            "order": 10,
            "control": "boolean",
            "default": False,
            "nullable": False,
            "min_value": None,
            "max_value": None,
            "options": [],
            "max_length": None,
        },
        {
            "key": "title",
            "label_key": "extensions.testGenerated.title",
            "description_key": "extensions.testGenerated.titleDescription",
            "order": 10,
            "control": "string",
            "default": "",
            "nullable": True,
            "min_value": None,
            "max_value": None,
            "options": [],
            "max_length": 20,
        },
        {
            "key": "mode",
            "label_key": "extensions.testGenerated.mode",
            "description_key": "extensions.testGenerated.modeDescription",
            "order": 15,
            "control": "enum",
            "default": "fast",
            "nullable": False,
            "min_value": None,
            "max_value": None,
            "options": ["fast", "thorough"],
            "max_length": None,
        },
        {
            "key": "max_rows",
            "label_key": "extensions.testGenerated.maxRows",
            "description_key": "extensions.testGenerated.maxRowsDescription",
            "order": 20,
            "control": "integer",
            "default": 10,
            "nullable": False,
            "min_value": 1,
            "max_value": 100,
            "options": [],
            "max_length": None,
        },
        {
            "key": "ratio",
            "label_key": "extensions.testGenerated.ratio",
            "description_key": None,
            "order": 30,
            "control": "number",
            "default": 1.5,
            "nullable": False,
            "min_value": 0.1,
            "max_value": 10.0,
            "options": [],
            "max_length": None,
        },
    ]
    # 摘要声明呈现方式；generated 不携带 route_key（专属组件只用于 custom）
    listed = client.get("/api/extensions").json()
    assert listed[0]["settings_contribution"] == {
        "presentation": "generated",
        "route_key": None,
    }


class _UnexplainableFieldProvider(_GeneratedSettingsProvider):
    """配对不一致的假 Provider：清单声明了 ``title`` 却给不出它的字段元数据。

    ARCH-DM-006 §8.1 的“字段元数据无法由 Provider 解释”只能产生稳定诊断，
    不得让宿主渲染一份缺字段的 ``items`` 部分结果。
    """

    field_definitions = tuple(
        spec
        for spec in _GeneratedSettingsProvider.field_definitions
        if spec.key != "title"
    )


@pytest.mark.parametrize(
    ("provider", "reason"),
    [
        (None, "EXTENSION_SETTINGS_PROVIDER_MISSING"),
        (_UnexplainableFieldProvider(), "EXTENSION_SETTINGS_PROVIDER_FIELD_UNKNOWN"),
    ],
    ids=["missing-provider", "unexplainable-field"],
)
def test_generated_settings_without_explainable_provider_returns_diagnostic(
    tmp_path, provider, reason
):
    """ARCH-DM-006 §8.1：声明设置但缺少 Provider（或清单字段无法由 Provider 解释）
    时，只使该扩展设置不可用并产生诊断：GET 与 PUT 都必须以 503 + 稳定
    ``params.reason`` 返回，不得静默渲染一份缺字段的 ``items`` 部分结果。
    """
    client = generated_settings_client(tmp_path, provider)
    url = f"/api/extensions/{GENERATED_SETTINGS_ID}/settings"

    read = client.get(url)

    assert read.status_code == 503
    body = read.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert body["message_key"] == "errors.extension.capabilityUnavailable"
    assert body["params"] == {"extension_id": GENERATED_SETTINGS_ID, "reason": reason}
    # 无任何 items：诊断之外的字段列表（部分结果）绝不出现在错误体里
    assert "items" not in body

    rejected = client.put(
        url,
        json={"schema_version": 1, "expected_revision": 0, "value": {"max_rows": 5}},
    )

    assert rejected.status_code == 503
    assert rejected.json() == body


def test_generated_settings_maps_rebind_diagnostic_instead_of_unhandled_500(
    tmp_path, monkeypatch
):
    """R9 复核：Provider 在“读取设置视图”与“取字段规格”之间失效时仍必须是契约化 503。

    真实触发点是 :meth:`ExtensionRuntime.start` 重跑 ``bind_providers``（FastAPI
    在线程池里同步执行端点，两次调用之间可插入重绑定）；这里在端点内部模拟该
    交错，钉住 ``settings_field_specs`` 与 ``get_settings`` 的错误映射同形，
    不泄漏 :class:`ExtensionSettingsError` 为未处理异常（HTTP 500）。
    """
    client = generated_settings_client(tmp_path)
    runtime = client.app.state.extension_runtime
    url = f"/api/extensions/{GENERATED_SETTINGS_ID}/settings"
    assert client.get(url).status_code == 200  # 基线：Provider 登记有效

    original_get_settings = runtime.get_settings

    def get_settings_then_rebind(extension_id: str):
        view = original_get_settings(extension_id)
        # 重启式重绑定：同 ID 的第二份 Provider 实例触发重复登记诊断（§8.1）
        runtime.start(generated_settings_entries(tmp_path, _GeneratedSettingsProvider()))
        return view

    monkeypatch.setattr(runtime, "get_settings", get_settings_then_rebind)

    response = client.get(url)

    assert response.status_code == 503
    body = response.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert body["params"] == {
        "extension_id": GENERATED_SETTINGS_ID,
        "reason": "EXTENSION_SETTINGS_PROVIDER_DUPLICATE",
    }
    # 呈现访问器只读清单、不经设置服务：登记失效后仍是总函数（无诊断、无异常）
    contribution = runtime.settings_contribution(GENERATED_SETTINGS_ID)
    assert contribution is not None and contribution.presentation == "generated"


def test_generated_settings_put_roundtrips_and_keeps_effective_defaults(tmp_path):
    """generated 扩展的每次保存/读取都返回同一呈现契约：值仍分持久值与有效值。"""
    client = generated_settings_client(tmp_path)
    url = f"/api/extensions/{GENERATED_SETTINGS_ID}/settings"

    saved = client.put(
        url,
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "value": {"max_rows": 5, "notify": True},
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["revision"] == 1
    # value 只存用户显式配置；effective_value 由 Provider 补齐代码默认值
    assert payload["value"] == {"max_rows": 5, "notify": True}
    assert payload["effective_value"] == {
        **GENERATED_SETTINGS_DEFAULTS,
        "max_rows": 5,
        "notify": True,
    }
    assert payload["read_only"] is False and payload["diagnostic_code"] is None
    assert [item["key"] for item in payload["items"]] == [
        "notify",
        "title",
        "mode",
        "max_rows",
        "ratio",
    ]
    assert client.get(url).json() == payload


def test_generated_settings_put_invalid_field_returns_422_and_keeps_value(tmp_path):
    """非法字段值必须由 Provider 拒绝（422），不落库、不截断。"""
    client = generated_settings_client(tmp_path)
    url = f"/api/extensions/{GENERATED_SETTINGS_ID}/settings"

    rejected = client.put(
        url,
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "value": {"max_rows": 101, "notify": False},
        },
    )

    assert rejected.status_code == 422
    body = rejected.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_SETTINGS_INVALID"
    assert body["message_key"] == "errors.extension.settingsInvalid"
    assert body["params"] == {"extension_id": GENERATED_SETTINGS_ID}
    assert "EXTENSION_SETTINGS_TEST_INVALID" in body["message"]
    assert client.get(url).json()["revision"] == 0


def test_generated_settings_put_stale_revision_returns_409(tmp_path):
    """ARCH-DM-006 §8.1：PUT 未携带当前 ``expected_revision`` 时竞争写入 409。"""
    client = generated_settings_client(tmp_path)
    url = f"/api/extensions/{GENERATED_SETTINGS_ID}/settings"
    body = {"schema_version": 1, "expected_revision": 0, "value": {"max_rows": 5, "notify": False}}
    assert client.put(url, json=body).status_code == 200

    stale = client.put(
        url,
        json={"schema_version": 1, "expected_revision": 0, "value": {"max_rows": 7, "notify": False}},
    )

    assert stale.status_code == 409
    payload = stale.json()
    assert_error_contract(payload)
    assert payload["code"] == "EXTENSION_SETTINGS_INVALID"
    assert payload["params"] == {"expected_revision": 0, "current_revision": 1}
    assert client.get(url).json()["value"] == {"max_rows": 5, "notify": False}


def test_preferences_default_and_workspace_isolation(tmp_path):
    client = make_client(tmp_path)
    first = f"/api/extensions/{SHEET_CATALOG_ID}/workspaces/ws-1/preferences"
    second = f"/api/extensions/{SHEET_CATALOG_ID}/workspaces/ws-2/preferences"

    # 偏好不存在时返回清单 schema 的零值默认，而不是 404
    assert client.get(first).json() == {"schema_version": 2, "revision": 0, "value": {}}

    put = client.put(first, json={"schema_version": 2, "value": {"template_id": "t-1"}})
    assert put.status_code == 200
    assert put.json() == {"schema_version": 2, "revision": 1, "value": {"template_id": "t-1"}}
    assert client.get(first).json()["value"] == {"template_id": "t-1"}
    assert client.get(second).json()["value"] == {}


# ---------------------------------------------------------------------------
# 动作分派：扩展状态与动作声明
# ---------------------------------------------------------------------------


def test_action_endpoints_validate_availability_and_declared_action(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/extensions").json()[0]["status"] == "AVAILABLE"

    unknown_action = client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/no-such-action/preview",
        json={
            "workspace_id": "ws-1",
            "base_revision_id": "0" * 64,
            "template": template_payload(),
        },
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
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/preview",
        json={
            "workspace_id": "ws-1",
            "base_revision_id": "0" * 64,
            "template": template_payload(),
        },
    )
    assert disabled.status_code == 409
    body = disabled.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_DISABLED"
    assert body["message_key"] == "errors.extension.disabled"
    assert body["params"] == {"extension_id": SHEET_CATALOG_ID, "action_id": "export-xlsx"}

    # 重新启用后预览与执行走真实分派（未登记工作区 → 稳定 404）
    assert client.patch(
        f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": True}
    ).status_code == 200
    preview = client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/preview",
        json={
            "workspace_id": "no-such-workspace",
            "base_revision_id": "0" * 64,
            "template": template_payload(),
        },
    )
    assert preview.status_code == 404
    assert preview.json()["code"] == "EXTENSION_NOT_FOUND"

    execute = client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/execute",
        json={
            "workspace_id": "no-such-workspace",
            "base_revision_id": "0" * 64,
            "template": template_payload(),
            "preview_digest": "0" * 64,
            "save_grant_id": "grant-1",
            # PLAN-DM-025 Task 4：执行必须重复提交预览时绑定的设置修订
            "settings_revision": 0,
        },
    )
    assert execute.status_code == 404
    body = execute.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_NOT_FOUND"
    assert body["params"]["workspace_id"] == "no-such-workspace"

    # 缺失必填字段的执行负载由契约校验直接拒绝（422），不进入分派
    assert client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/execute", json={}
    ).status_code == 422


def test_action_endpoint_reports_unavailable_extension(tmp_path, monkeypatch):
    # 快照能力不可发放（WAITING_DEPENDENCY）：预览不得编造结果，返回稳定 503
    monkeypatch.setattr(registry_module, "AVAILABLE_CAPABILITIES", frozenset())
    client = make_client(tmp_path)
    assert client.get("/api/extensions").json()[0]["status"] == "WAITING_DEPENDENCY"

    resp = client.post(
        f"/api/extensions/{SHEET_CATALOG_ID}/actions/export-xlsx/preview",
        json={
            "workspace_id": "ws-1",
            "base_revision_id": "0" * 64,
            "template": template_payload(),
        },
    )

    assert resp.status_code == 503
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert body["message_key"] == "errors.extension.capabilityUnavailable"
    assert body["params"] == {"extension_id": SHEET_CATALOG_ID, "action_id": "export-xlsx"}


# ---------------------------------------------------------------------------
# Task 6：真实数据预览动作（SPEC-DM-012 §8.1）
# ---------------------------------------------------------------------------


def test_preview_action_returns_real_rows_field_catalog_and_digest(tmp_path, tiny_workspace):
    client = make_client(tmp_path)
    workspace = open_workspace(client, tiny_workspace)

    resp = post_preview(client, workspace)

    assert resp.status_code == 200
    body = resp.json()
    # 规范化模板快照原样回传
    assert body["normalized_template"]["template_id"] is None
    assert body["normalized_template"]["name"] == DEFAULT_TEMPLATE.name
    assert [column["header"] for column in body["normalized_template"]["columns"]] == [
        "图号",
        "图名",
        "文件名",
    ]
    assert body["normalized_template"]["columns"][0]["expression"] == "{sheet.number}"
    # 字段目录按作用域分组，固有字段置 builtin
    sheetset_names = [field["canonical_name"] for field in body["field_catalog"]["sheetset"]]
    sheet_fields = {field["canonical_name"]: field["builtin"] for field in body["field_catalog"]["sheet"]}
    assert sheetset_names == ["项目号"]
    assert sheet_fields == {"number": True, "title": True, "file_name": True, "比例": False}
    # 真实行（basename 裁剪）、总数、digest、可执行
    assert body["rows"] == [["001", "平面", "A.dwg"]]
    assert body["total_rows"] == 1
    assert body["errors"] == []
    assert body["warnings"] == []
    assert body["executable"] is True
    assert len(body["preview_digest"]) == 64

    again = post_preview(client, workspace).json()
    assert again["preview_digest"] == body["preview_digest"]


def test_preview_action_reports_revision_mismatch_and_unknown_workspace(tmp_path, tiny_workspace):
    client = make_client(tmp_path)
    workspace = open_workspace(client, tiny_workspace)

    mismatch = post_preview(client, workspace, base_revision_id="f" * 64)
    assert mismatch.status_code == 409
    body = mismatch.json()
    assert_error_contract(body)
    assert body["code"] == "REPREVIEW_REQUIRED"
    assert body["message_key"] == "errors.extension.repreviewRequired"
    # 请求要求的基准修订 vs 工作区当前修订（SPEC §11：保留编辑，刷新后重试）
    assert body["params"]["required_revision_id"] == "f" * 64
    assert body["params"]["current_revision_id"] == workspace["revision_id"]

    missing = post_preview(client, {"id": "no-such-workspace", "revision_id": "0" * 64})
    assert missing.status_code == 404
    body = missing.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_NOT_FOUND"
    assert body["params"]["workspace_id"] == "no-such-workspace"


def test_preview_action_blocks_undefined_field_with_structured_error(tmp_path, tiny_workspace):
    client = make_client(tmp_path)
    workspace = open_workspace(client, tiny_workspace)
    template = template_payload()
    template["columns"] = [
        {
            "column_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "preview:bad")),
            "header": "图号",
            "expression": "{sheet.不存在}",
        }
    ]

    resp = post_preview(client, workspace, template)

    assert resp.status_code == 200
    body = resp.json()
    assert body["executable"] is False
    assert body["rows"] == []
    assert len(body["errors"]) == 1
    error = body["errors"][0]
    assert error["code"] == "SHEET_CATALOG_FIELD_UNDEFINED"
    assert error["message_key"] == "errors.sheetCatalog.fieldUndefined"
    assert error["params"] == {"scope": "sheet", "name": "不存在"}
    assert error["column_id"] == str(uuid.uuid5(uuid.NAMESPACE_URL, "preview:bad"))


def test_preview_projects_filter_settings_and_reports_settings_revision(tmp_path, tiny_workspace):
    """预览从同一冻结设置快照取过滤词，并回传绑定的设置修订与过滤计数。"""
    client = make_client(tmp_path)
    workspace = open_workspace(client, tiny_workspace)  # 单张图纸：001/平面

    baseline = post_preview(client, workspace).json()
    assert baseline["executable"] is True
    assert (baseline["total_rows"], baseline["filtered_rows"]) == (1, 0)
    assert baseline["rows"] == [["001", "平面", "A.dwg"]]
    # 从未保存过设置：revision = 0（Provider 默认零值），预览仍携带绑定值
    assert baseline["settings_revision"] == 0

    saved = client.put(
        f"/api/extensions/{SHEET_CATALOG_ID}/settings",
        json={
            "schema_version": 2,
            "expected_revision": 0,
            "value": {"excluded_title_keywords": " 平面，PLAN "},
        },
    )
    assert saved.status_code == 200, saved.text
    # 服务端规范化（半/全角逗号、trim、去重）后的持久值即预览使用的过滤词
    assert saved.json()["value"]["excluded_title_keywords"] == ["平面", "PLAN"]
    revision = saved.json()["revision"]

    filtered = post_preview(client, workspace).json()

    assert filtered["settings_revision"] == revision
    assert filtered["executable"] is True
    assert filtered["errors"] == []
    assert filtered["rows"] == []
    assert (filtered["total_rows"], filtered["filtered_rows"]) == (0, 1)
    # 设置修订变化后旧预览摘要失效（不得用新设置执行旧预览）
    assert filtered["preview_digest"] != baseline["preview_digest"]


def test_preview_saves_last_template_preference_and_skips_drafts(tmp_path, tiny_workspace):
    client = make_client(tmp_path)
    workspace = open_workspace(client, tiny_workspace)
    preference_url = (
        f"/api/extensions/{SHEET_CATALOG_ID}/workspaces/{workspace['id']}/preferences"
    )

    saved_id = uuid.uuid5(uuid.NAMESPACE_URL, "preview:saved-template")
    post_preview(client, workspace, template_id=saved_id)
    assert client.get(preference_url).json()["value"] == {"template_id": str(saved_id)}

    # 未保存草稿（template_id=null）不进入工作区偏好（ARCH-DM-006 §8.2）
    post_preview(client, workspace)
    assert client.get(preference_url).json()["value"] == {"template_id": str(saved_id)}


def test_preview_preference_save_failure_degrades_to_non_blocking_warning(
    tmp_path, tiny_workspace, monkeypatch
):
    def _broken_put_preference(self, *args, **kwargs):
        raise RuntimeError("偏好库不可用")

    monkeypatch.setattr(ExtensionStore, "put_preference", _broken_put_preference)
    client = make_client(tmp_path)
    workspace = open_workspace(client, tiny_workspace)
    saved_id = uuid.uuid5(uuid.NAMESPACE_URL, "preview:saved-template")

    resp = post_preview(client, workspace, template_id=saved_id)

    # 偏好保存失败不得升级为动作失败：预览照常成功并返回可诊断的非阻断 warning
    assert resp.status_code == 200
    body = resp.json()
    assert body["executable"] is True
    assert body["rows"] == [["001", "平面", "A.dwg"]]
    assert len(body["warnings"]) == 1
    warning = body["warnings"][0]
    assert warning["code"] == "EXTENSION_PREFERENCE_SAVE_FAILED"
    assert warning["message_key"] == "errors.extension.preferenceSaveFailed"
    assert warning["params"] == {"template_id": str(saved_id)}
    assert warning["column_id"] is None and warning["source_position"] is None


# ---------------------------------------------------------------------------
# 错误清单与工厂失败的故障隔离
# ---------------------------------------------------------------------------


def _boom() -> None:
    raise RuntimeError("工厂故障")


def test_broken_manifest_and_factory_isolation_keeps_core_api_available(tmp_path, monkeypatch):
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

    rendered = client.get("/api/extensions").text
    # Ruling-7：占位条目的 extension_id 不得把服务端绝对路径暴露给客户端
    assert str(bad) not in rendered and str(tmp_path) not in rendered
    listed = {item["extension_id"]: item for item in json.loads(rendered)}
    assert listed["builtin.invalid-bad-manifest"]["status"] == "FAILED"
    assert listed["builtin.invalid-bad-manifest"]["error_code"] == "EXTENSION_MANIFEST_INVALID"
    assert listed[SHEET_CATALOG_ID]["status"] == "FAILED"
    assert listed[SHEET_CATALOG_ID]["error_code"] == "EXTENSION_START_FAILED"
    assert all(item["error_code"] in DIAGNOSTIC_CODES for item in listed.values())


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
# 启停不产生非契约 500（fix round 1 / Finding 1）
# ---------------------------------------------------------------------------


def test_enable_factory_failed_extension_stays_contract_compliant(tmp_path, monkeypatch):
    """对工厂失败的扩展启用：注册表重试仍失败并保持 FAILED，响应契约合规、绝不 500。"""
    entries = (
        BuiltinExtensionEntry(
            manifest_resource="dst_manager/extensions/builtin/sheet_catalog/manifest.yaml",
            factory=_boom,
        ),
    )
    client = make_client(
        tmp_path, extension_runtime=make_runtime(tmp_path, entries), extension_index=entries
    )
    assert client.get("/api/extensions").json()[0]["status"] == "FAILED"

    resp = client.patch(f"/api/extensions/{SHEET_CATALOG_ID}/state", json={"enabled": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["error_code"] == "EXTENSION_START_FAILED"
    assert body["error_code"] in DIAGNOSTIC_CODES


def test_enable_placeholder_extension_returns_contract_error(tmp_path):
    """对清单不可读的占位条目启用：契约化 503，而不是注册表断言逃逸成 500。"""
    bad = tmp_path / "bad-manifest.yaml"
    bad.write_text("extension_id: [未闭合", encoding="utf-8")
    entries = (BuiltinExtensionEntry(manifest_resource=str(bad), factory=_boom),)
    client = make_client(
        tmp_path, extension_runtime=make_runtime(tmp_path, entries), extension_index=entries
    )

    resp = client.patch("/api/extensions/builtin.invalid-bad-manifest/state", json={"enabled": True})

    assert resp.status_code == 503
    body = resp.json()
    assert_error_contract(body)
    assert body["code"] == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert body["message_key"] == "errors.extension.capabilityUnavailable"
    assert body["params"] == {"extension_id": "builtin.invalid-bad-manifest"}


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
