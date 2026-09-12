"""PLAN-DM-025 Task 2：图纸目录设置 Provider 与过滤纯函数（SPEC-DM-012 §6.4）。

覆盖 Schema 1→2 迁移、过滤关键词规范化（两种逗号、trim、casefold 去重、
首见原文顺序）、50/51 项与 100/101 字符边界、图名大小写不敏感字面 OR 匹配、
有效值合并代码内置模板，以及 Provider 把目录错误码映射为设置错误的契约。
"""

from __future__ import annotations

import uuid

import pytest

from dst_manager.application.extensions.settings import (
    ExtensionSettingsError,
    ExtensionSettingsService,
)
from dst_manager.extensions.builtin.sheet_catalog import settings as catalog_settings
from dst_manager.extensions.builtin.sheet_catalog.settings import (
    MAX_EXCLUDED_TITLE_KEYWORD_CHARS,
    MAX_EXCLUDED_TITLE_KEYWORDS,
    SHEET_CATALOG_SETTINGS_PROVIDER,
    SheetCatalogSettingsProvider,
    normalize_excluded_title_keywords,
    title_matches_exclusion,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import DEFAULT_TEMPLATE
from dst_manager.extensions.manifest import load_manifest
from dst_manager.infrastructure.persistence.extensions import VersionedJson

SHEET_CATALOG_ID = "dst-manager.sheet-catalog"
MANIFEST_RESOURCE = "dst_manager/extensions/builtin/sheet_catalog/manifest.yaml"


class RecordingStore:
    """``ExtensionStore`` 设置部分替身：记录写入以断言"不主动落库"。"""

    def __init__(self, current: VersionedJson | None = None) -> None:
        self.current = current
        self.put_calls: list[tuple[str, int, dict[str, object], int]] = []

    def get_settings(self, extension_id: str) -> VersionedJson | None:
        return self.current

    def put_settings(
        self,
        extension_id: str,
        schema_version: int,
        value: dict[str, object],
        expected_revision: int,
    ) -> VersionedJson:
        self.put_calls.append((extension_id, schema_version, dict(value), expected_revision))
        self.current = VersionedJson(schema_version, expected_revision + 1, dict(value))
        return self.current


def catalog_manifest():
    """真实随包清单：Service 层用例据此核对 Manifest 与 Provider 的配对。"""
    return load_manifest(MANIFEST_RESOURCE)


def service(store: RecordingStore) -> ExtensionSettingsService:
    return ExtensionSettingsService(store, [SHEET_CATALOG_SETTINGS_PROVIDER])


def template_json(name: str = "市政标准目录") -> dict[str, object]:
    """v1/v2 设置负载中的单个用户模板 JSON（SPEC-DM-012 §6.1）。"""
    return {
        "template_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"catalog-settings:{name}")),
        "name": name,
        "schema_version": 1,
        "columns": [
            {
                "column_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"catalog-settings:{name}:number")),
                "header": "图号",
                "expression": "{sheet.number}",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Provider 身份与字段元数据
# ---------------------------------------------------------------------------


def test_provider_identity_and_schema_are_pinned_to_the_manifest():
    provider = SheetCatalogSettingsProvider()

    assert provider.extension_id == SHEET_CATALOG_ID
    assert provider.schema_version == 2
    assert catalog_manifest().extension_id == SHEET_CATALOG_ID
    # SPEC-DM-012 §6.4：目录设置 Schema 从 1 升为 2
    assert catalog_manifest().settings_schema == provider.schema_version


def test_provider_declares_no_generated_fields():
    """目录设置由编译期白名单的 custom 组件呈现，宿主不生成表单字段。"""
    assert catalog_manifest().settings_contribution.presentation == "custom"
    assert SHEET_CATALOG_SETTINGS_PROVIDER.field_definitions == ()


def test_provider_default_value_is_empty_explicit_configuration():
    assert SHEET_CATALOG_SETTINGS_PROVIDER.default_value() == {}


# ---------------------------------------------------------------------------
# 过滤关键词规范化
# ---------------------------------------------------------------------------


def test_normalize_splits_both_commas_trims_and_dedupes_casefold():
    keywords = normalize_excluded_title_keywords("草图， TEMP,,作废,temp")

    assert keywords == ("草图", "TEMP", "作废")


def test_normalize_accepts_empty_and_absent_input():
    assert normalize_excluded_title_keywords("") == ()
    assert normalize_excluded_title_keywords("   ") == ()
    assert normalize_excluded_title_keywords(None) == ()
    assert normalize_excluded_title_keywords([]) == ()


def test_normalize_accepts_persisted_array_and_keeps_first_spelling():
    keywords = normalize_excluded_title_keywords(["作废", " 作废 ", "TEMP", "temp"])

    assert keywords == ("作废", "TEMP")


def test_normalize_uses_unicode_casefold_not_lower():
    # "straße".casefold() == "strasse"；lower() 不会合并这两种拼写
    keywords = normalize_excluded_title_keywords(["STRASSE", "straße"])

    assert keywords == ("STRASSE",)


@pytest.mark.parametrize("value", [5, {"keyword": "作废"}, ["作废", 5], ["作废", None]])
def test_normalize_rejects_non_string_shapes(value):
    with pytest.raises(TypeError, match="excluded_title_keywords"):
        normalize_excluded_title_keywords(value)


# ---------------------------------------------------------------------------
# 图名排除匹配
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("TEMP-平面图", True),
        ("平面图（作废）", True),
        ("平面图", False),
        ("", False),
        ("草图", False),
    ],
)
def test_title_matches_exclusion_is_case_insensitive_or_substring(title, expected):
    keywords = normalize_excluded_title_keywords("作废, temp")

    assert title_matches_exclusion(title, keywords) is expected


def test_title_matches_exclusion_without_keywords_filters_nothing():
    assert title_matches_exclusion("作废图", ()) is False


def test_title_matches_exclusion_has_no_wildcard_or_regex_semantics():
    assert title_matches_exclusion("草图", ("草.",)) is False
    assert title_matches_exclusion("草图", ("草*",)) is False
    assert title_matches_exclusion("草图", ("草",)) is True


# ---------------------------------------------------------------------------
# 关键词限制值：50/51 项、100/101 字符
# ---------------------------------------------------------------------------


def test_keyword_limits_accept_exact_boundaries():
    fifty = ",".join(f"k{index:02d}" for index in range(MAX_EXCLUDED_TITLE_KEYWORDS))
    longest = "x" * MAX_EXCLUDED_TITLE_KEYWORD_CHARS

    by_count = SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(
        {"user_templates": [], "excluded_title_keywords": fifty}
    )
    by_length = SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(
        {"user_templates": [], "excluded_title_keywords": longest}
    )

    assert len(by_count["excluded_title_keywords"]) == MAX_EXCLUDED_TITLE_KEYWORDS
    assert by_length["excluded_title_keywords"] == [longest]


def test_keyword_count_over_limit_is_rejected_with_field_error():
    too_many = ",".join(f"k{index:02d}" for index in range(MAX_EXCLUDED_TITLE_KEYWORDS + 1))

    with pytest.raises(ExtensionSettingsError) as excinfo:
        SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(
            {"user_templates": [], "excluded_title_keywords": too_many}
        )

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_INVALID"
    assert error.status_code == 422
    assert error.params == {
        "field": "excluded_title_keywords",
        "kind": "count",
        "limit": MAX_EXCLUDED_TITLE_KEYWORDS,
        "actual": MAX_EXCLUDED_TITLE_KEYWORDS + 1,
    }


def test_keyword_length_over_limit_is_rejected_without_truncating():
    too_long = "x" * (MAX_EXCLUDED_TITLE_KEYWORD_CHARS + 1)

    with pytest.raises(ExtensionSettingsError) as excinfo:
        SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(
            {"user_templates": [], "excluded_title_keywords": too_long}
        )

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_INVALID"
    assert error.status_code == 422
    assert error.params == {
        "field": "excluded_title_keywords",
        "kind": "length",
        "limit": MAX_EXCLUDED_TITLE_KEYWORD_CHARS,
        "actual": MAX_EXCLUDED_TITLE_KEYWORD_CHARS + 1,
    }


# ---------------------------------------------------------------------------
# Provider 校验与规范化（Schema v2 负载）
# ---------------------------------------------------------------------------


def test_validate_normalizes_templates_and_drops_empty_keyword_override():
    payload = SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(
        {"schema_version": 1, "user_templates": [template_json()], "excluded_title_keywords": ""}
    )

    assert payload == {"schema_version": 2, "user_templates": [template_json()]}


def test_validate_persists_keywords_as_normalized_array():
    payload = SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(
        {"user_templates": [], "excluded_title_keywords": "草图，TEMP,作废"}
    )

    assert payload == {
        "schema_version": 2,
        "user_templates": [],
        "excluded_title_keywords": ["草图", "TEMP", "作废"],
    }


def test_validate_is_idempotent_on_its_own_output():
    first = SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(
        {"user_templates": [template_json()], "excluded_title_keywords": " 作废 , TEMP "}
    )

    assert SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(first) == first


@pytest.mark.parametrize(
    ("value", "code", "status"),
    [
        ({"user_templates": "broken"}, "EXTENSION_SETTINGS_INVALID", 422),
        (
            {"user_templates": [dict(template_json(), template_id=None)]},
            "EXTENSION_SETTINGS_INVALID",
            422,
        ),
        (
            {"user_templates": [template_json("Catalog"), template_json("catalog")]},
            "SHEET_CATALOG_COLUMN_DUPLICATE",
            409,
        ),
        (
            {"user_templates": [dict(template_json(), name="默认图纸目录（内置）")]},
            "SHEET_CATALOG_COLUMN_DUPLICATE",
            409,
        ),
        (
            {
                "user_templates": [
                    template_json(f"模板{index:03d}") for index in range(101)
                ]
            },
            "SHEET_CATALOG_TEMPLATE_LIMIT",
            422,
        ),
        ({"user_templates": [dict(template_json(), columns=[])]}, "SHEET_CATALOG_TEMPLATE_LIMIT", 422),
    ],
)
def test_validate_maps_catalog_errors_to_settings_errors(value, code, status):
    with pytest.raises(ExtensionSettingsError) as excinfo:
        SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(value)

    error = excinfo.value
    assert error.code == code
    assert error.status_code == status
    if code == "SHEET_CATALOG_COLUMN_DUPLICATE":
        assert error.key_override == "errors.sheetCatalog.columnDuplicate"
    assert error.params


def test_validate_reports_missing_template_uuid_with_stable_diagnostic():
    with pytest.raises(ExtensionSettingsError) as excinfo:
        SHEET_CATALOG_SETTINGS_PROVIDER.validate_and_normalize(
            {"user_templates": [dict(template_json(), template_id=None)]}
        )

    error = excinfo.value
    assert error.code == "EXTENSION_SETTINGS_INVALID"
    assert "SHEET_CATALOG_TEMPLATE_ID_REQUIRED" in str(error)


# ---------------------------------------------------------------------------
# 迁移与解析
# ---------------------------------------------------------------------------


def test_migrate_v1_keeps_templates_and_does_not_add_keyword_override():
    templates = [template_json()]

    migrated = SHEET_CATALOG_SETTINGS_PROVIDER.migrate(
        1, {"schema_version": 1, "user_templates": templates}
    )

    assert migrated == {"schema_version": 2, "user_templates": templates}
    assert "excluded_title_keywords" not in migrated


def test_migrate_rejects_unknown_older_schema():
    with pytest.raises(ExtensionSettingsError) as excinfo:
        SHEET_CATALOG_SETTINGS_PROVIDER.migrate(0, {})

    assert excinfo.value.code == "EXTENSION_SETTINGS_INVALID"
    assert excinfo.value.status_code == 422


def test_resolve_merges_builtin_template_and_empty_keywords():
    effective = SHEET_CATALOG_SETTINGS_PROVIDER.resolve({})

    assert effective["builtin_template"]["template_id"] is None
    assert effective["builtin_template"]["name"] == DEFAULT_TEMPLATE.name
    assert effective["builtin_template"]["columns"][0]["header"] == "图号"
    assert effective["user_templates"] == []
    assert effective["excluded_title_keywords"] == []


def test_resolve_returns_normalized_keywords_and_user_templates():
    effective = SHEET_CATALOG_SETTINGS_PROVIDER.resolve(
        {
            "user_templates": [template_json()],
            "excluded_title_keywords": ["作废", "作废 ", "TEMP"],
        }
    )

    assert effective["user_templates"] == [template_json()]
    assert effective["excluded_title_keywords"] == ["作废", "TEMP"]


# ---------------------------------------------------------------------------
# 服务编排：v1 存量读取、保存写回与只读保护
# ---------------------------------------------------------------------------


def test_real_v1_settings_are_migrated_in_memory_without_writing_store():
    templates = [template_json()]
    store = RecordingStore(
        VersionedJson(1, 4, {"schema_version": 1, "user_templates": templates})
    )

    view = service(store).get(catalog_manifest())

    assert view.value == {"schema_version": 2, "user_templates": templates}
    assert view.revision == 4
    assert view.schema_version == 2
    assert view.effective_value["user_templates"] == templates
    assert view.effective_value["excluded_title_keywords"] == []
    assert store.put_calls == []


def test_put_accepts_raw_keyword_text_and_returns_normalized_array():
    store = RecordingStore()

    saved = service(store).put(
        catalog_manifest(),
        2,
        {"user_templates": [template_json()], "excluded_title_keywords": "草图， TEMP,,作废,temp"},
        expected_revision=0,
    )

    assert store.put_calls == [
        (
            SHEET_CATALOG_ID,
            2,
            {
                "schema_version": 2,
                "user_templates": [template_json()],
                "excluded_title_keywords": ["草图", "TEMP", "作废"],
            },
            0,
        )
    ]
    assert saved.value == store.put_calls[0][2]
    assert saved.effective_value["excluded_title_keywords"] == ["草图", "TEMP", "作废"]


def test_put_with_empty_keyword_text_clears_the_explicit_override():
    store = RecordingStore()

    saved = service(store).put(
        catalog_manifest(),
        2,
        {"user_templates": [], "excluded_title_keywords": "  ,, "},
        expected_revision=0,
    )

    assert saved.value == {"schema_version": 2, "user_templates": []}
    assert saved.effective_value["excluded_title_keywords"] == []


def test_snapshot_digest_tracks_excluded_title_keywords():
    store = RecordingStore()
    settings = service(store)

    before = settings.snapshot(catalog_manifest())
    settings.put(
        catalog_manifest(),
        2,
        {"user_templates": [], "excluded_title_keywords": "作废"},
        expected_revision=0,
    )
    after = settings.snapshot(catalog_manifest())

    assert before.digest != after.digest
    assert after.value["excluded_title_keywords"] == ("作废",)
    assert after.value["builtin_template"]["name"] == DEFAULT_TEMPLATE.name


def test_unknown_newer_schema_is_preserved_and_rejected_on_put():
    raw = {"schema_version": 3, "future_field": {"keep": True}}
    store = RecordingStore(VersionedJson(3, 2, raw))
    settings = service(store)

    view = settings.get(catalog_manifest())
    assert view.read_only is True
    assert view.value == raw

    with pytest.raises(ExtensionSettingsError) as excinfo:
        settings.put(catalog_manifest(), 2, {"user_templates": []}, expected_revision=2)

    assert excinfo.value.code == "EXTENSION_SETTINGS_SCHEMA_NEWER"
    assert excinfo.value.status_code == 409
    assert store.put_calls == []
    assert store.current == VersionedJson(3, 2, raw)


def test_provider_module_exposes_the_shared_provider_instance():
    assert isinstance(SHEET_CATALOG_SETTINGS_PROVIDER, SheetCatalogSettingsProvider)
    assert catalog_settings.SHEET_CATALOG_SETTINGS_PROVIDER is SHEET_CATALOG_SETTINGS_PROVIDER
