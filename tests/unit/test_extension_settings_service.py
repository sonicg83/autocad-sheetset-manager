"""PLAN-DM-025 Task 2：扩展设置编排服务（Provider 配对、迁移、并发与快照）。

用 :class:`FakeStore`（只实现设置读取与条件写入）与 :class:`FakeProvider`
覆盖 ARCH-DM-006 §8.1 的编排语义：默认零值、旧 Schema 内存迁移不落库、迁移
失败隔离、未知高版本只读保留、合法/非法保存、修订冲突、Manifest/Provider
的 ID/Schema/字段覆盖不一致与重复登记。图纸目录 Provider 见
``test_sheet_catalog_settings.py``。
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from dst_manager.application.extensions.settings import (
    EXTENSION_SETTINGS_PROVIDER_DUPLICATE,
    EXTENSION_SETTINGS_PROVIDER_FIELD_UNKNOWN,
    EXTENSION_SETTINGS_PROVIDER_ID_MISMATCH,
    EXTENSION_SETTINGS_PROVIDER_MISSING,
    EXTENSION_SETTINGS_PROVIDER_SCHEMA_MISMATCH,
    ExtensionSettingsError,
    ExtensionSettingsService,
    ExtensionSettingsView,
    settings_provider_error,
)
from dst_manager.extensions.contracts import ExtensionManifest
from dst_manager.extensions.settings import (
    ExtensionSettingsSnapshot,
    SettingsContribution,
    SettingsFieldDefinition,
    SettingsFieldSpec,
    settings_digest,
)
from dst_manager.infrastructure.persistence.extensions import (
    SettingsRevisionConflictError,
    VersionedJson,
)

EXTENSION_ID = "test.provider"


# ---------------------------------------------------------------------------
# 替身
# ---------------------------------------------------------------------------


class FakeStore:
    """``ExtensionStore`` 的设置部分替身：版本化 JSON + 条件更新。"""

    def __init__(self, current: VersionedJson | None = None) -> None:
        self.current = current
        self.put_calls: list[tuple[str, int, dict[str, object], int]] = []
        self.conflict = False

    def get_settings(self, extension_id: str) -> VersionedJson | None:
        return self.current

    def put_settings(
        self,
        extension_id: str,
        schema_version: int,
        value: dict[str, object],
        expected_revision: int,
    ) -> VersionedJson:
        if self.conflict:
            raise SettingsRevisionConflictError(
                "EXTENSION_SETTINGS_REVISION_CONFLICT: 替身强制冲突"
            )
        self.put_calls.append((extension_id, schema_version, dict(value), expected_revision))
        self.current = VersionedJson(schema_version, expected_revision + 1, dict(value))
        return self.current


class FakeProvider:
    """单字段（``max_rows``）替身 Provider：零值、迁移、校验、解析全部可观察。"""

    extension_id = EXTENSION_ID
    schema_version = 2
    field_definitions = (
        SettingsFieldSpec(key="max_rows", control="integer", default=10, min_value=1),
    )

    def __init__(
        self,
        *,
        extension_id: str | None = None,
        schema_version: int | None = None,
    ) -> None:
        if extension_id is not None:
            self.extension_id = extension_id
        if schema_version is not None:
            self.schema_version = schema_version
        self.migrate_calls: list[tuple[int, dict[str, object]]] = []
        self.validate_calls: list[dict[str, object]] = []
        self.resolve_calls: list[dict[str, object]] = []
        self.migrate_error: Exception | None = None
        self.validate_error: Exception | None = None

    def default_value(self) -> dict[str, object]:
        return {"max_rows": 10}

    def migrate(
        self, stored_schema_version: int, value: dict[str, object]
    ) -> dict[str, object]:
        self.migrate_calls.append((stored_schema_version, dict(value)))
        if self.migrate_error is not None:
            raise self.migrate_error
        return {"max_rows": value["limit"]}

    def validate_and_normalize(self, value: dict[str, object]) -> dict[str, object]:
        self.validate_calls.append(dict(value))
        if self.validate_error is not None:
            raise self.validate_error
        rows = value.get("max_rows")
        if isinstance(rows, bool) or not isinstance(rows, int):
            raise TypeError("EXTENSION_SETTINGS_TEST_INVALID: max_rows 必须是整数")
        return {"max_rows": rows}

    def resolve(self, value: dict[str, object]) -> dict[str, object]:
        self.resolve_calls.append(dict(value))
        return {
            "max_rows": value.get("max_rows", 10),
            "tags": ["default", "resolved"],
        }


def manifest(
    *,
    extension_id: str = EXTENSION_ID,
    settings_schema: int = 2,
    with_settings: bool = True,
    fields: tuple[SettingsFieldDefinition, ...] = (),
) -> ExtensionManifest:
    """测试清单：默认声明 ``generated`` 设置，字段默认为 ``max_rows``。"""
    contribution = None
    if with_settings:
        contribution = SettingsContribution(
            presentation="generated",
            fields=fields
            or (
                SettingsFieldDefinition(
                    key="max_rows",
                    label_key="settings.test.maxRows",
                    description_key=None,
                    order=0,
                ),
            ),
        )
    return ExtensionManifest(
        extension_id=extension_id,
        version="0.1.0",
        host_contract=1,
        enabled_by_default=True,
        name_key="extensions.test.name",
        description_key="extensions.test.description",
        required_capabilities=(),
        permissions=(),
        ui_contributions=(),
        actions=(),
        settings_schema=settings_schema,
        settings_contribution=contribution,
    )


def service(
    store: FakeStore, providers: list[FakeProvider] | tuple[FakeProvider, ...] = ()
) -> ExtensionSettingsService:
    return ExtensionSettingsService(store, providers)


# ---------------------------------------------------------------------------
# 读取：零值、规范化、旧 Schema 迁移、未知高版本只读保留
# ---------------------------------------------------------------------------


def test_never_saved_extension_returns_provider_zero_value_at_revision_zero():
    store = FakeStore()
    provider = FakeProvider()

    view = service(store, [provider]).get(manifest())

    assert view == ExtensionSettingsView(
        extension_id=EXTENSION_ID,
        schema_version=2,
        revision=0,
        value={"max_rows": 10},
        effective_value={"max_rows": 10, "tags": ["default", "resolved"]},
        read_only=False,
        diagnostic_code=None,
    )
    # 从未保存不得落库，也不得触发迁移
    assert store.put_calls == []
    assert provider.migrate_calls == []


def test_stored_value_is_normalized_on_read():
    store = FakeStore(VersionedJson(2, 3, {"max_rows": 20, "unknown": "drop"}))
    provider = FakeProvider()

    view = service(store, [provider]).get(manifest())

    assert view.value == {"max_rows": 20}
    assert view.revision == 3
    assert view.effective_value == {"max_rows": 20, "tags": ["default", "resolved"]}
    assert store.put_calls == []


def test_invalid_stored_value_disables_settings_with_stable_error():
    store = FakeStore(VersionedJson(2, 3, {"max_rows": "many"}))

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [FakeProvider()]).get(manifest())

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_INVALID"
    assert error.status_code == 422
    assert error.params == {"extension_id": EXTENSION_ID}


def test_older_schema_is_migrated_without_writing_store():
    store = FakeStore(VersionedJson(1, 4, {"limit": 10}))

    view = service(store, [FakeProvider()]).get(manifest())

    assert view.value == {"max_rows": 10}
    assert view.revision == 4
    assert view.schema_version == 2
    assert store.put_calls == []


def test_migration_failure_is_reported_without_writing_store():
    store = FakeStore(VersionedJson(1, 4, {"limit": 10}))
    provider = FakeProvider()
    provider.migrate_error = ValueError("EXTENSION_SETTINGS_MIGRATE_BROKEN")

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [provider]).get(manifest())

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_INVALID"
    assert error.status_code == 422
    assert store.put_calls == []


def test_newer_schema_is_read_only_and_preserved():
    raw = {"future": {"keep": [1, 2]}}
    store = FakeStore(VersionedJson(3, 8, raw))

    view = service(store, [FakeProvider()]).get(manifest())

    assert view.read_only is True
    assert view.value == raw
    assert view.effective_value == raw
    assert view.schema_version == 3
    assert view.revision == 8
    assert view.diagnostic_code == "EXTENSION_SETTINGS_SCHEMA_NEWER"
    assert store.put_calls == []


def test_newer_schema_put_is_rejected_and_keeps_original_json():
    raw = {"future": "keep"}
    store = FakeStore(VersionedJson(3, 8, raw))
    provider = FakeProvider()

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [provider]).put(
            manifest(), 2, {"max_rows": 10}, expected_revision=8
        )

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_SCHEMA_NEWER"
    assert error.status_code == 409
    assert error.params == {
        "extension_id": EXTENSION_ID,
        "settings_schema": 3,
        "current_schema": 2,
    }
    assert store.put_calls == []
    assert store.current == VersionedJson(3, 8, raw)


def test_newer_schema_snapshot_is_rejected_fail_closed():
    store = FakeStore(VersionedJson(3, 8, {"future": "keep"}))

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [FakeProvider()]).snapshot(manifest())

    assert excinfo.value.code == "EXTENSION_SETTINGS_SCHEMA_NEWER"
    assert excinfo.value.status_code == 409


# ---------------------------------------------------------------------------
# 保存：规范化、非法负载、Provider 业务错误与修订冲突
# ---------------------------------------------------------------------------


def test_put_normalizes_and_persists_with_provider_schema():
    store = FakeStore()
    provider = FakeProvider()

    view = service(store, [provider]).put(
        manifest(), 2, {"max_rows": 42, "unknown": "drop"}, expected_revision=0
    )

    assert store.put_calls == [(EXTENSION_ID, 2, {"max_rows": 42}, 0)]
    assert view == ExtensionSettingsView(
        extension_id=EXTENSION_ID,
        schema_version=2,
        revision=1,
        value={"max_rows": 42},
        effective_value={"max_rows": 42, "tags": ["default", "resolved"]},
        read_only=False,
        diagnostic_code=None,
    )


def test_put_rejects_submitted_schema_mismatch():
    store = FakeStore()

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [FakeProvider()]).put(manifest(), 1, {"max_rows": 10}, 0)

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_INVALID"
    assert error.status_code == 422
    assert error.params == {"settings_schema": 2, "submitted": 1}
    assert store.put_calls == []


def test_put_rejects_invalid_value_without_writing():
    store = FakeStore()

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [FakeProvider()]).put(manifest(), 2, {"max_rows": "many"}, 0)

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_INVALID"
    assert error.status_code == 422
    assert error.params == {"extension_id": EXTENSION_ID}
    assert store.put_calls == []


def test_put_propagates_provider_settings_error_verbatim():
    store = FakeStore()
    provider = FakeProvider()
    provider.validate_error = ExtensionSettingsError(
        "SHEET_CATALOG_TEMPLATE_LIMIT",
        "超出模板限制",
        status_code=422,
        params={"kind": "user_templates", "limit": 100, "actual": 101},
        key_override="errors.sheetCatalog.templateLimit",
    )

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [provider]).put(manifest(), 2, {"max_rows": 1}, 0)

    error = excinfo.value
    assert error.code == "SHEET_CATALOG_TEMPLATE_LIMIT"
    assert error.status_code == 422
    assert error.params == {"kind": "user_templates", "limit": 100, "actual": 101}
    assert error.key_override == "errors.sheetCatalog.templateLimit"
    assert store.put_calls == []


def test_put_revision_conflict_reports_expected_and_current_revision():
    store = FakeStore(VersionedJson(2, 4, {"max_rows": 10}))
    store.conflict = True

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [FakeProvider()]).put(manifest(), 2, {"max_rows": 20}, 1)

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_INVALID"
    assert error.status_code == 409
    assert error.params == {"expected_revision": 1, "current_revision": 4}
    assert store.put_calls == []


# ---------------------------------------------------------------------------
# Manifest / Provider 配对与登记
# ---------------------------------------------------------------------------


def test_settings_provider_error_pins_id_schema_and_field_coverage():
    provider = FakeProvider()

    assert settings_provider_error(manifest(), provider) is None
    assert (
        settings_provider_error(manifest(extension_id="other"), provider)
        == EXTENSION_SETTINGS_PROVIDER_ID_MISMATCH
    )
    assert (
        settings_provider_error(manifest(settings_schema=3), provider)
        == EXTENSION_SETTINGS_PROVIDER_SCHEMA_MISMATCH
    )
    assert (
        settings_provider_error(
            manifest(
                fields=(
                    SettingsFieldDefinition(
                        key="max_rows", label_key="l", description_key=None, order=0
                    ),
                    SettingsFieldDefinition(
                        key="cad_version", label_key="l", description_key=None, order=1
                    ),
                )
            ),
            provider,
        )
        == EXTENSION_SETTINGS_PROVIDER_FIELD_UNKNOWN
    )


def test_provider_schema_mismatch_isolates_settings():
    store = FakeStore()
    provider = FakeProvider(schema_version=3)

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [provider]).get(manifest())

    error = excinfo.value
    assert error.code == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert error.status_code == 503
    assert error.params == {
        "extension_id": EXTENSION_ID,
        "reason": EXTENSION_SETTINGS_PROVIDER_SCHEMA_MISMATCH,
    }
    assert store.put_calls == []


def test_duplicate_provider_registration_isolates_settings():
    store = FakeStore()

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store, [FakeProvider(), FakeProvider()]).get(manifest())

    error = excinfo.value
    assert error.code == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert error.status_code == 503
    assert error.params == {
        "extension_id": EXTENSION_ID,
        "reason": EXTENSION_SETTINGS_PROVIDER_DUPLICATE,
    }


def test_rebinding_same_provider_is_idempotent():
    store = FakeStore()
    provider = FakeProvider()
    settings = service(store, [provider])

    settings.bind_providers([provider])  # 重复 start() 不得自判为重复登记

    assert settings.get(manifest()).value == {"max_rows": 10}


def test_missing_provider_for_declared_settings_isolates_settings():
    store = FakeStore()

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store).get(manifest())

    error = excinfo.value
    assert error.code == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert error.status_code == 503
    assert error.params == {
        "extension_id": EXTENSION_ID,
        "reason": EXTENSION_SETTINGS_PROVIDER_MISSING,
    }


def test_extension_without_settings_keeps_generic_json_path():
    store = FakeStore()
    settings = service(store)

    assert settings.get(manifest(with_settings=False)).value == {}
    assert settings.get(manifest(with_settings=False)).revision == 0

    saved = settings.put(
        manifest(with_settings=False), 2, {"columns": ["a"]}, expected_revision=0
    )
    assert store.put_calls == [(EXTENSION_ID, 2, {"columns": ["a"]}, 0)]
    assert saved.value == {"columns": ["a"]}
    assert saved.effective_value == {"columns": ["a"]}


def test_generic_path_rejects_revision_conflict_with_stable_error():
    store = FakeStore(VersionedJson(2, 2, {"columns": ["a"]}))
    store.conflict = True

    with pytest.raises(ExtensionSettingsError) as excinfo:
        service(store).put(manifest(with_settings=False), 2, {"columns": ["b"]}, 1)

    assert excinfo.value.code == "EXTENSION_SETTINGS_INVALID"
    assert excinfo.value.status_code == 409
    assert excinfo.value.params == {"expected_revision": 1, "current_revision": 2}


# ---------------------------------------------------------------------------
# 快照：冻结有效值并绑定摘要
# ---------------------------------------------------------------------------


def test_snapshot_freezes_effective_value_and_binds_digest():
    store = FakeStore(VersionedJson(2, 5, {"max_rows": 20}))
    settings = service(store, [FakeProvider()])

    view = settings.get(manifest())
    snapshot = settings.snapshot(manifest())

    assert isinstance(snapshot, ExtensionSettingsSnapshot)
    assert snapshot.extension_id == EXTENSION_ID
    assert snapshot.schema_version == 2
    assert snapshot.revision == 5
    assert isinstance(snapshot.value, Mapping)
    assert snapshot.value["tags"] == ("default", "resolved")
    assert snapshot.digest == settings_digest(
        EXTENSION_ID, 2, {"max_rows": 20, "tags": ["default", "resolved"]}
    )
    # 冻结结果不与调用方共享可变容器
    view.effective_value["tags"].append("mutated")
    assert snapshot.value["tags"] == ("default", "resolved")


def test_snapshot_digest_changes_with_normalized_value():
    store = FakeStore()
    settings = service(store, [FakeProvider()])

    first = settings.snapshot(manifest())
    settings.put(manifest(), 2, {"max_rows": 20}, expected_revision=0)
    second = settings.snapshot(manifest())

    assert first.revision == 0
    assert first.digest != second.digest
    assert second.revision == 1
