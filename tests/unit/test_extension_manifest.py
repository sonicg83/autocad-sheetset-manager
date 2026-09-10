# 内置扩展清单契约单元测试（PLAN-DM-020 Task 1 / ARCH-DM-006 §4）
from importlib import resources

import pytest
import yaml

from dst_manager.extensions.builtin.index import BUILTIN_EXTENSION_INDEX
from dst_manager.extensions.builtin.sheet_catalog.extension import (
    create_sheet_catalog_extension,
)
from dst_manager.extensions.contracts import (
    XLSX_MEDIA_TYPE,
    ExtensionManifest,
)
from dst_manager.extensions.manifest import ManifestError, load_manifest, parse_manifest

BUILTIN_MANIFEST_RESOURCE = "dst_manager/extensions/builtin/sheet_catalog/manifest.yaml"

FORBIDDEN_EXECUTION_FIELDS = ("module", "class_name", "script", "command", "entry_point")


def valid_manifest_data(**overrides):
    """构造一份最小合法清单；overrides 仅供负向用例修改单个字段。"""
    data = {
        "extension_id": "test.a",
        "version": "0.1.0",
        "extension_type": "builtin",
        "host_contract": 1,
        "enabled_by_default": True,
        "name_key": "extensions.test.name",
        "description_key": "extensions.test.description",
        "required_capabilities": [],
        "permissions": [],
        "ui_contributions": [],
        "actions": [
            {"action_id": "noop", "output_kind": None, "media_type": None},
        ],
        "settings_schema": 1,
    }
    data.update(overrides)
    return data


def test_builtin_sheet_catalog_manifest_loads_with_expected_contract() -> None:
    manifest = load_manifest(BUILTIN_MANIFEST_RESOURCE)
    assert isinstance(manifest, ExtensionManifest)
    assert manifest.extension_id == "dst-manager.sheet-catalog"
    assert manifest.version == "0.1.0"
    assert manifest.host_contract == 1
    assert manifest.enabled_by_default is True
    assert manifest.name_key == "extensions.sheetCatalog.name"
    assert manifest.description_key == "extensions.sheetCatalog.description"
    assert manifest.required_capabilities == ("workspace.snapshot.read.v1",)
    assert manifest.permissions == ("workspace.snapshot.read", "artifact.output.propose")
    assert [(c.contribution_id, c.kind, c.route_key) for c in manifest.ui_contributions] == [
        ("workspace-page", "workspace_page", "sheet-catalog")
    ]
    assert [(a.action_id, a.output_kind, a.media_type) for a in manifest.actions] == [
        ("export-xlsx", "xlsx", XLSX_MEDIA_TYPE)
    ]
    assert manifest.settings_schema == 1


def test_fixed_index_references_factory_directly_and_yaml_has_no_execution_fields() -> None:
    # EP-01：固定代码白名单直接引用工厂函数；清单不得携带可执行入口字段
    assert len(BUILTIN_EXTENSION_INDEX) == 1
    entry = BUILTIN_EXTENSION_INDEX[0]
    assert entry.manifest_resource == BUILTIN_MANIFEST_RESOURCE
    assert entry.factory is create_sheet_catalog_extension

    text = (
        resources.files("dst_manager.extensions.builtin.sheet_catalog")
        / "manifest.yaml"
    ).read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    assert set(FORBIDDEN_EXECUTION_FIELDS).isdisjoint(raw)


def test_parse_manifest_maps_declared_fields_into_frozen_contract() -> None:
    manifest = parse_manifest(valid_manifest_data())
    assert manifest.extension_id == "test.a"
    assert manifest.required_capabilities == ()
    assert manifest.ui_contributions == ()
    assert isinstance(manifest.actions, tuple)
    assert manifest.actions[0].action_id == "noop"


@pytest.mark.parametrize("missing", ["name_key", "description_key"])
def test_display_keys_are_required(missing: str) -> None:
    data = valid_manifest_data()
    del data[missing]
    with pytest.raises(ManifestError):
        parse_manifest(data)


@pytest.mark.parametrize("empty", ["name_key", "description_key"])
def test_display_keys_must_not_be_blank(empty: str) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(valid_manifest_data(**{empty: ""}))


def test_action_ids_must_be_unique() -> None:
    data = valid_manifest_data(
        actions=[
            {"action_id": "dup", "output_kind": None, "media_type": None},
            {"action_id": "dup", "output_kind": None, "media_type": None},
        ]
    )
    with pytest.raises(ManifestError):
        parse_manifest(data)


def test_xlsx_action_requires_fixed_mime() -> None:
    wrong_mime = valid_manifest_data(
        actions=[{"action_id": "export", "output_kind": "xlsx", "media_type": "text/csv"}]
    )
    with pytest.raises(ManifestError):
        parse_manifest(wrong_mime)

    missing_mime = valid_manifest_data(
        actions=[{"action_id": "export", "output_kind": "xlsx", "media_type": None}]
    )
    with pytest.raises(ManifestError):
        parse_manifest(missing_mime)

    fixed = valid_manifest_data(
        actions=[{"action_id": "export", "output_kind": "xlsx", "media_type": XLSX_MEDIA_TYPE}]
    )
    assert parse_manifest(fixed).actions[0].media_type == XLSX_MEDIA_TYPE


def test_media_type_requires_declared_output_kind() -> None:
    data = valid_manifest_data(
        actions=[{"action_id": "odd", "output_kind": None, "media_type": XLSX_MEDIA_TYPE}]
    )
    with pytest.raises(ManifestError):
        parse_manifest(data)


def test_unknown_output_kind_rejected() -> None:
    data = valid_manifest_data(
        actions=[{"action_id": "export", "output_kind": "pdf", "media_type": "application/pdf"}]
    )
    with pytest.raises(ManifestError):
        parse_manifest(data)


def test_missing_required_field_rejected() -> None:
    data = valid_manifest_data()
    del data["version"]
    with pytest.raises(ManifestError):
        parse_manifest(data)


def test_unknown_field_rejected() -> None:
    with pytest.raises(ManifestError):
        parse_manifest(valid_manifest_data(unknown_field="x"))


@pytest.mark.parametrize("field", FORBIDDEN_EXECUTION_FIELDS)
def test_execution_entry_fields_rejected(field: str) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(valid_manifest_data(**{field: "os.system"}))


@pytest.mark.parametrize("version", ["1.0", "v1.0.0", "0.1.0.0", "alpha", "", "01.2.3"])
def test_invalid_semver_rejected(version: str) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(valid_manifest_data(version=version))


def test_non_builtin_extension_type_rejected() -> None:
    with pytest.raises(ManifestError):
        parse_manifest(valid_manifest_data(extension_type="user"))


def test_missing_resource_raises_manifest_error() -> None:
    with pytest.raises(ManifestError):
        load_manifest("dst_manager/extensions/builtin/does_not_exist.yaml")
