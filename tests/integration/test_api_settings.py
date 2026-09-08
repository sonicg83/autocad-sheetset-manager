"""设置中心与关于 API 端点集成测试（PLAN-DM-019 设置中心任务 5）。

夹具沿用作坊既有 API 集成测试模式（TestClient 直构 create_app）：
- ``client``：不注入 RuntimeSettings（开发态 serve / 既有测试），设置端点不注册；
- ``client_with_runtime``：``DST_MANAGER_SETTINGS_PATH`` 指向 tmp_path 的
  ``UserSettingsStore`` 构造 ``RuntimeSettings`` 注入 ``create_app``。
"""

import json

import pytest
from fastapi.testclient import TestClient

from dst_manager.interfaces.api import create_app
from dst_manager.settings.runtime import RuntimeSettings, default_store


@pytest.fixture
def client():
    """无 RuntimeSettings 装配：既有契约零变化。"""
    return TestClient(create_app())


@pytest.fixture
def client_with_runtime(tmp_path, monkeypatch):
    """注入 RuntimeSettings（store 落在 tmp_path，经环境变量隔离）。"""
    monkeypatch.setenv("DST_MANAGER_SETTINGS_PATH", str(tmp_path / "settings.json"))
    runtime = RuntimeSettings(default_store())
    return TestClient(create_app(runtime_settings=runtime))


def _write_settings_file(tmp_path, schema_version, revision=3, values=None):
    """手写一个指定 schema_version 的设置文件，供 schema 降级用例使用。"""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "config_revision": revision,
                "values": values or {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path.read_bytes()


def test_get_settings_returns_items_with_metadata(client_with_runtime) -> None:
    body = client_with_runtime.get("/api/settings").json()
    assert body["schema_version"] == 1 and body["config_revision"] == 0
    keys = [item["key"] for item in body["items"]]
    assert keys[0] == "autocad_2016_console" and len(keys) == 9  # REGISTRY 顺序稳定
    item = body["items"][4]
    assert item["label"] and item["category"] and item["source"] in ("default", "env", "file")


def test_put_partial_update_does_not_freeze_env_values(client_with_runtime, monkeypatch) -> None:
    monkeypatch.setenv("DST_MANAGER_CAD_TIMEOUT_SECONDS", "777")
    rev = client_with_runtime.get("/api/settings").json()["config_revision"]
    resp = client_with_runtime.put(
        "/api/settings",
        json={"expected_revision": rev, "set": {"cad_max_parallel": 8}, "unset": []},
    )
    assert resp.status_code == 200
    items = {i["key"]: i for i in resp.json()["items"]}
    assert items["cad_max_parallel"]["has_file_override"] is True
    assert items["cad_timeout_seconds"]["source"] == "env"  # 未被固化


def test_put_stale_revision_returns_409(client_with_runtime) -> None:
    resp = client_with_runtime.put(
        "/api/settings", json={"expected_revision": 99, "set": {}, "unset": []}
    )
    assert resp.status_code == 409


def test_put_field_errors_return_422_with_errors_map(client_with_runtime) -> None:
    rev = client_with_runtime.get("/api/settings").json()["config_revision"]
    resp = client_with_runtime.put(
        "/api/settings",
        json={"expected_revision": rev, "set": {"cad_max_parallel": 99}, "unset": []},
    )
    assert resp.status_code == 422 and "cad_max_parallel" in resp.json()["errors"]


def test_about_returns_version_and_mit_license(client_with_runtime) -> None:
    body = client_with_runtime.get("/api/about").json()
    assert body["license"]["spdx"] == "MIT"
    assert "MIT License" in body["license"]["text"]
    assert body["version"] and body["app_name"]


def test_endpoints_absent_without_runtime(client) -> None:
    """开发态/既有测试的 create_app() 不注册设置端点，契约零变化。"""
    assert client.get("/api/settings").status_code == 404


def test_get_settings_schema_older_degrades_to_readonly(client_with_runtime, tmp_path) -> None:
    """schema 过旧：GET 200 + 只读降级 + SETTINGS_SCHEMA_OLDER 诊断。"""
    _write_settings_file(tmp_path, schema_version=0, revision=3)
    body = client_with_runtime.get("/api/settings").json()
    assert body["schema_blocked"] is True
    assert "SETTINGS_SCHEMA_OLDER" in body["diagnostics"]
    assert all(item["has_file_override"] is False for item in body["items"])


def test_put_rejected_when_schema_older_and_file_untouched(client_with_runtime, tmp_path) -> None:
    """schema 过旧：PUT 409，且旧 Schema 文件字节绝不被写回。"""
    original = _write_settings_file(tmp_path, schema_version=0, revision=3)
    resp = client_with_runtime.put(
        "/api/settings",
        json={"expected_revision": 3, "set": {"cad_max_parallel": 8}, "unset": []},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "SETTINGS_SCHEMA_OLDER"
    assert (tmp_path / "settings.json").read_bytes() == original


def test_put_rejected_when_schema_newer_blocks_writes(client_with_runtime, tmp_path) -> None:
    """schema 过新：GET 只读降级（resolver 快照），PUT 409 拒绝写回。"""
    _write_settings_file(tmp_path, schema_version=2, revision=5)
    body = client_with_runtime.get("/api/settings").json()
    assert body["schema_blocked"] is True and body["config_revision"] == 5
    resp = client_with_runtime.put(
        "/api/settings",
        json={"expected_revision": 5, "set": {"cad_max_parallel": 8}, "unset": []},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "SETTINGS_SCHEMA_BLOCKED"


def test_get_refreshes_after_external_file_change(client_with_runtime, tmp_path) -> None:
    """外部改文件（手编/其他窗口保存）后 GET 反映新修订号与覆盖，不读陈旧缓存。"""
    assert client_with_runtime.get("/api/settings").json()["config_revision"] == 0
    _write_settings_file(
        tmp_path, schema_version=1, revision=5, values={"cad_max_parallel": 3}
    )
    body = client_with_runtime.get("/api/settings").json()
    assert body["config_revision"] == 5
    items = {item["key"]: item for item in body["items"]}
    assert items["cad_max_parallel"]["has_file_override"] is True
    assert items["cad_max_parallel"]["value"] == 3
