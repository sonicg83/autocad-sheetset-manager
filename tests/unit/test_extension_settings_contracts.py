# 扩展设置值对象与 Provider 契约单元测试（PLAN-DM-025 Task 1 / ARCH-DM-006 §8、§11）
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from typing import get_type_hints

import pytest

from dst_manager.extensions.contracts import BuiltinExtensionEntry
from dst_manager.extensions.settings import (
    ExtensionSettingsProvider,
    ExtensionSettingsSnapshot,
    SettingsContribution,
    SettingsFieldDefinition,
    freeze_json,
    settings_digest,
)

DIGEST_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")


class _StubExtension:
    def start(self) -> None: ...

    def stop(self) -> None: ...


class _StubProvider:
    """最小 Provider 替身：只验证契约成员可被结构化实现，不含业务语义。"""

    extension_id = "test.a"
    schema_version = 2
    field_definitions = (
        SettingsFieldDefinition(
            key="max_rows",
            label_key="extensions.test.fields.maxRows",
            description_key=None,
            order=0,
        ),
    )

    def default_value(self) -> dict[str, object]:
        return {"max_rows": 10}

    def migrate(
        self, stored_schema_version: int, value: dict[str, object]
    ) -> dict[str, object]:
        return value

    def validate_and_normalize(self, value: dict[str, object]) -> dict[str, object]:
        return value

    def resolve(self, value: dict[str, object]) -> dict[str, object]:
        return {**self.default_value(), **value}


# --------------------------------------------------------------- 冻结 JSON


def test_freeze_json_is_recursive_and_read_only() -> None:
    frozen = freeze_json(
        {
            "flag": True,
            "limit": 10,
            "ratio": 1.5,
            "note": None,
            "name": "草图",
            "sections": [{"title": "A", "tags": ["x", "y"]}],
        }
    )

    assert isinstance(frozen, Mapping)
    sections = frozen["sections"]
    assert isinstance(sections, tuple)
    section = sections[0]
    assert isinstance(section, Mapping)
    assert section["title"] == "A"
    assert section["tags"] == ("x", "y")
    assert isinstance(section["tags"], tuple)
    assert frozen["limit"] == 10
    assert frozen["ratio"] == 1.5
    assert frozen["flag"] is True
    assert frozen["note"] is None

    with pytest.raises(TypeError):
        frozen["limit"] = 5  # type: ignore[index]
    with pytest.raises(TypeError):
        section["title"] = "B"  # type: ignore[index]


def test_freeze_json_does_not_alias_source_dict() -> None:
    source: dict[str, object] = {"sections": [{"tags": ["x"]}]}
    frozen = freeze_json(source)

    source["limit"] = 10
    nested = source["sections"]
    assert isinstance(nested, list)
    nested.append({"tags": ["z"]})
    first = nested[0]
    assert isinstance(first, dict)
    first["tags"].append("y")

    assert frozen == {"sections": ({"tags": ("x",)},)}
    assert dict(frozen["sections"][0]) == {"tags": ("x",)}


def test_freeze_json_keeps_scalars_hashable_inside_tuples() -> None:
    frozen = freeze_json(["a", 1, 1.5, True, None])
    assert isinstance(frozen, tuple)
    assert hash(frozen) == hash(("a", 1, 1.5, True, None))


# ------------------------------------------------------------------ 摘要


def test_settings_digest_is_canonical_and_scoped_to_extension_identity() -> None:
    value = {"b": [1, 2], "a": {"y": None, "x": "草图"}}
    digest = settings_digest("test.a", 2, value)

    assert DIGEST_PATTERN.match(digest) is not None
    # 键序与 list/tuple 容器差异不改变规范 JSON
    assert digest == settings_digest("test.a", 2, {"a": {"x": "草图", "y": None}, "b": (1, 2)})
    assert digest == settings_digest("test.a", 2, freeze_json(value))
    # 相同取值不得跨扩展或跨 Schema 复用摘要
    assert digest != settings_digest("test.b", 2, value)
    assert digest != settings_digest("test.a", 3, value)


def test_settings_digest_matches_canonical_json_sha256() -> None:
    value = {"b": [1, 2], "a": {"y": None, "x": "草图"}}
    canonical = json.dumps(
        {"extension_id": "test.a", "schema_version": 2, "value": value},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert settings_digest("test.a", 2, value) == hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def test_settings_digest_is_stable_across_processes() -> None:
    script = (
        "import json\n"
        "from dst_manager.extensions.settings import settings_digest\n"
        "value = json.loads('{\"b\": [1, 2], \"a\": {\"y\": null, \"x\": \"\u8349\u56fe\"}}')\n"
        "print(settings_digest('test.a', 2, value))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == settings_digest(
        "test.a", 2, {"b": (1, 2), "a": {"y": None, "x": "草图"}}
    )


# -------------------------------------------------- 快照与 Provider 契约


def test_snapshot_is_frozen_with_declared_field_order() -> None:
    snapshot = ExtensionSettingsSnapshot(
        extension_id="test.a",
        schema_version=2,
        revision=3,
        value=freeze_json({"max_rows": 10}),
        digest="0" * 64,
    )

    assert [field.name for field in dataclasses.fields(snapshot)] == [
        "extension_id",
        "schema_version",
        "revision",
        "value",
        "digest",
    ]
    assert snapshot.value["max_rows"] == 10
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.revision = 4  # type: ignore[misc]


def test_provider_protocol_declares_settings_semantics() -> None:
    annotations = get_type_hints(ExtensionSettingsProvider)
    assert annotations["extension_id"] is str
    assert annotations["schema_version"] is int
    assert annotations["field_definitions"] == tuple[SettingsFieldDefinition, ...]
    for member in ("default_value", "migrate", "validate_and_normalize", "resolve"):
        assert callable(getattr(ExtensionSettingsProvider, member))


def test_provider_shaped_object_can_be_used_through_protocol() -> None:
    provider: ExtensionSettingsProvider = _StubProvider()

    assert provider.extension_id == "test.a"
    assert provider.schema_version == 2
    assert provider.field_definitions[0].key == "max_rows"
    assert provider.migrate(1, {"max_rows": 5}) == {"max_rows": 5}
    assert provider.validate_and_normalize({"max_rows": 5}) == {"max_rows": 5}
    assert provider.resolve({}) == {"max_rows": 10}
    assert provider.resolve({"max_rows": 5}) == {"max_rows": 5}


# ---------------------------------------------------- 呈现声明与索引条目


def test_generated_contribution_carries_ordered_field_definitions() -> None:
    contribution = SettingsContribution(
        presentation="generated",
        fields=(
            SettingsFieldDefinition(
                key="max_rows",
                label_key="extensions.test.fields.maxRows",
                description_key="extensions.test.fields.maxRows.description",
                order=0,
            ),
        ),
    )

    assert contribution.presentation == "generated"
    assert contribution.route_key is None
    field = contribution.fields[0]
    assert (field.key, field.label_key, field.description_key, field.order) == (
        "max_rows",
        "extensions.test.fields.maxRows",
        "extensions.test.fields.maxRows.description",
        0,
    )


def test_custom_contribution_carries_route_key_without_fields() -> None:
    contribution = SettingsContribution(
        presentation="custom", route_key="sheet-catalog-settings"
    )

    assert contribution.presentation == "custom"
    assert contribution.route_key == "sheet-catalog-settings"
    assert contribution.fields == ()


def test_builtin_entry_settings_provider_defaults_to_none() -> None:
    entry = BuiltinExtensionEntry(
        manifest_resource="dst_manager/extensions/builtin/test/manifest.yaml",
        factory=_StubExtension,
    )
    assert entry.settings_provider is None

    provider = _StubProvider()
    assert (
        BuiltinExtensionEntry(
            manifest_resource=entry.manifest_resource,
            factory=_StubExtension,
            settings_provider=provider,
        ).settings_provider
        is provider
    )
