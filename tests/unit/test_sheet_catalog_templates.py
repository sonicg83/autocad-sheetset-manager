"""PLAN-DM-020 Task 5：图纸目录模板校验、加载/保存/删除与扩展设置语义。

覆盖：内置默认模板三列不可改删、用户模板与列 UUID 往返稳定、全部限制值
（100 个用户模板、1～50 列、模板名 1～80、列名 1～100、表达式 ≤1024）、
列名与模板名 casefold 唯一、保存只要求语法有效不要求兼容当前图纸集、
乐观并发冲突保留本地编辑、删除回退内置默认模板、未知高 schema 保留
原 JSON 并输出稳定诊断。
"""

import logging
import uuid
from dataclasses import replace

import pytest

from dst_manager.extensions.builtin.sheet_catalog.errors import (
    SheetCatalogError,
    sheet_catalog_error,
)
from dst_manager.extensions.builtin.sheet_catalog.expressions import (
    FieldToken,
    LiteralToken,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import (
    DEFAULT_TEMPLATE,
    MAX_COLUMNS,
    MAX_EXPRESSION_CHARS,
    MAX_HEADER_CHARS,
    MAX_NAME_CHARS,
    MAX_USER_TEMPLATES,
    SheetCatalogTemplate,
    TemplateCollection,
    TemplateColumn,
    delete_template,
    load_templates,
    save_templates,
    validate_template,
)
from dst_manager.infrastructure.persistence.extensions import VersionedJson

TEMPLATES_LOGGER = logging.getLogger(
    "dst_manager.extensions.builtin.sheet_catalog.templates"
)


@pytest.fixture(autouse=True)
def _enable_templates_logger():
    """Alembic ``fileConfig``（disable_existing_loggers=True）会禁用先于迁移
    导入的模块 logger；本文件断言稳定诊断输出，逐用例强制恢复。"""
    was_disabled = TEMPLATES_LOGGER.disabled
    TEMPLATES_LOGGER.disabled = False
    yield
    TEMPLATES_LOGGER.disabled = was_disabled


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


def make_column(header: str, expression: str) -> TemplateColumn:
    return TemplateColumn(
        column_id=uuid.uuid5(uuid.NAMESPACE_URL, f"column:{header}"),
        header=header,
        expression=expression,
    )


def make_template(
    name: str = "市政标准目录",
    columns: tuple[TemplateColumn, ...] | None = None,
    template_id: uuid.UUID | None = None,
) -> SheetCatalogTemplate:
    return SheetCatalogTemplate(
        template_id=template_id
        if template_id is not None
        else uuid.uuid5(uuid.NAMESPACE_URL, f"template:{name}"),
        name=name,
        schema_version=1,
        columns=columns
        if columns is not None
        else (
            make_column("图号", "{sheet.number}"),
            make_column("专业", "{sheet.专业代码}"),
        ),
    )


def make_collection(
    user_templates: tuple[SheetCatalogTemplate, ...] = (),
    revision: int = 3,
) -> TemplateCollection:
    return TemplateCollection(
        revision=revision, builtin=DEFAULT_TEMPLATE, user_templates=user_templates
    )


# ---------------------------------------------------------------------------
# 内置默认模板：代码常量、三列固定、UUID 稳定、不落库
# ---------------------------------------------------------------------------


def test_default_template_pins_three_builtin_columns():
    assert DEFAULT_TEMPLATE.name == "默认图纸目录（内置）"
    assert DEFAULT_TEMPLATE.schema_version == 1
    assert DEFAULT_TEMPLATE.template_id is None
    assert [(c.header, c.expression) for c in DEFAULT_TEMPLATE.columns] == [
        ("图号", "{sheet.number}"),
        ("图名", "{sheet.title}"),
        ("文件名", "{sheet.file_name}"),
    ]


def test_default_template_column_ids_are_stable_constants():
    again = TemplateCollection(revision=0, builtin=DEFAULT_TEMPLATE, user_templates=())
    assert again.builtin.columns == DEFAULT_TEMPLATE.columns
    assert len({c.column_id for c in DEFAULT_TEMPLATE.columns}) == 3
    assert validate_template(DEFAULT_TEMPLATE).template is DEFAULT_TEMPLATE


# ---------------------------------------------------------------------------
# validate_template：限制值与 casefold 唯一
# ---------------------------------------------------------------------------


def test_validate_template_returns_parsed_columns_per_column():
    template = make_template(
        columns=(
            make_column("图号", "{sheet.number}"),
            make_column("专业", '{sheet["专业.代码"]}-{sheet.number}'),
        )
    )
    validated = validate_template(template)
    assert validated.template is template
    assert validated.parsed_columns == (
        (FieldToken("sheet", "number", 0, quoted=False),),
        (
            FieldToken("sheet", "专业.代码", 0, quoted=True),
            LiteralToken("-"),
            FieldToken("sheet", "number", 17, quoted=False),
        ),
    )


@pytest.mark.parametrize(
    ("template", "kind", "limit", "actual"),
    [
        pytest.param(
            make_template(name=""), "template_name", 1, 0, id="模板名下限"
        ),
        pytest.param(
            make_template(name="甲" * (MAX_NAME_CHARS + 1)),
            "template_name",
            MAX_NAME_CHARS,
            MAX_NAME_CHARS + 1,
            id="模板名 81 字符超限",
        ),
        pytest.param(
            make_template(columns=()), "columns", 1, 0, id="0 列低于下限"
        ),
        pytest.param(
            make_template(
                columns=tuple(
                    make_column(f"列{i}", "{sheet.number}") for i in range(MAX_COLUMNS + 1)
                )
            ),
            "columns",
            MAX_COLUMNS,
            MAX_COLUMNS + 1,
            id="51 列超限",
        ),
        pytest.param(
            make_template(columns=(make_column("", "{sheet.number}"),)),
            "column_header",
            1,
            0,
            id="列名下限",
        ),
        pytest.param(
            make_template(
                columns=(make_column("甲" * (MAX_HEADER_CHARS + 1), "{sheet.number}"),)
            ),
            "column_header",
            MAX_HEADER_CHARS,
            MAX_HEADER_CHARS + 1,
            id="列名 101 字符超限",
        ),
        pytest.param(
            make_template(
                columns=(make_column("图号", "甲" * (MAX_EXPRESSION_CHARS + 1)),)
            ),
            "expression",
            MAX_EXPRESSION_CHARS,
            MAX_EXPRESSION_CHARS + 1,
            id="表达式 1025 字符超限",
        ),
    ],
)
def test_validate_template_enforces_limits(template, kind, limit, actual):
    with pytest.raises(SheetCatalogError) as excinfo:
        validate_template(template)
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_TEMPLATE_LIMIT"
    assert error.params == {"kind": kind, "limit": limit, "actual": actual}


def test_validate_template_accepts_expression_at_limit_boundary():
    template = make_template(
        columns=(make_column("图号", "甲" * MAX_EXPRESSION_CHARS),)
    )
    validated = validate_template(template)
    assert len(validated.parsed_columns) == 1


def test_validate_template_rejects_casefold_duplicate_headers():
    template = make_template(
        columns=(
            make_column("Abc", "{sheet.number}"),
            make_column("ABC", "{sheet.title}"),
        )
    )
    with pytest.raises(SheetCatalogError) as excinfo:
        validate_template(template)
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_COLUMN_DUPLICATE"
    assert error.params == {"header": "ABC"}


def test_validate_template_wraps_parse_error_with_column_header():
    template = make_template(columns=(make_column("图号", "{sheet.number"),))
    with pytest.raises(SheetCatalogError) as excinfo:
        validate_template(template)
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_EXPRESSION_INVALID"
    assert error.params["column_header"] == "图号"
    assert error.params["source_start"] == 0


def test_validate_template_does_not_require_current_field_catalog_compatibility():
    """保存只要求语法/结构有效；字段目录兼容性属于预览阶段（SPEC-DM-012 §6.3）。"""
    template = make_template(columns=(make_column("备注", "{sheet.尚未存在的属性}"),))
    validated = validate_template(template)
    assert validated.parsed_columns == (
        (FieldToken("sheet", "尚未存在的属性", 0, quoted=False),),
    )


# ---------------------------------------------------------------------------
# save_templates：乐观并发、内置不可变、模板数与模板名唯一、UUID 序列化
# ---------------------------------------------------------------------------


def test_save_templates_serializes_user_templates_with_stable_uuids():
    template = make_template()
    payload = save_templates(make_collection((template,)), expected_revision=3)
    assert payload["schema_version"] == 1
    assert payload["user_templates"] == [
        {
            "template_id": str(template.template_id),
            "name": template.name,
            "schema_version": 1,
            "columns": [
                {
                    "column_id": str(column.column_id),
                    "header": column.header,
                    "expression": column.expression,
                }
                for column in template.columns
            ],
        }
    ]


def test_load_templates_round_trips_save_payload_with_stable_uuids():
    template = make_template()
    payload = save_templates(make_collection((template,)), expected_revision=3)
    settings = VersionedJson(schema_version=1, revision=7, value=payload)
    collection = load_templates(settings)
    assert collection.revision == 7
    assert collection.builtin is DEFAULT_TEMPLATE
    assert collection.user_templates == (template,)


def test_save_templates_rejects_revision_conflict_and_keeps_local_edits():
    template = make_template()
    collection = make_collection((template,), revision=3)
    with pytest.raises(SheetCatalogError) as excinfo:
        save_templates(collection, expected_revision=4)
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_TEMPLATE_CONFLICT"
    assert error.params == {"expected_revision": 4, "current_revision": 3}
    # 冲突后本地编辑原样保留：按服务端修订刷新后可重试。
    assert collection.user_templates == (template,)
    refreshed = replace(collection, revision=4)
    assert save_templates(refreshed, expected_revision=4)["user_templates"][0][
        "name"
    ] == template.name


def test_save_templates_rejects_mutated_builtin_template():
    mutated_builtin = replace(
        DEFAULT_TEMPLATE, columns=(make_column("改动", "{sheet.number}"),)
    )
    collection = TemplateCollection(
        revision=1, builtin=mutated_builtin, user_templates=()
    )
    with pytest.raises(ValueError, match="SHEET_CATALOG_BUILTIN_IMMUTABLE"):
        save_templates(collection, expected_revision=1)

def test_save_templates_rejects_more_than_100_user_templates():
    templates = tuple(
        make_template(name=f"模板{i:03d}") for i in range(MAX_USER_TEMPLATES + 1)
    )
    with pytest.raises(SheetCatalogError) as excinfo:
        save_templates(make_collection(templates), expected_revision=3)
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_TEMPLATE_LIMIT"
    assert error.params == {
        "kind": "user_templates",
        "limit": MAX_USER_TEMPLATES,
        "actual": MAX_USER_TEMPLATES + 1,
    }


def test_save_templates_accepts_exactly_100_user_templates():
    templates = tuple(
        make_template(name=f"模板{i:03d}") for i in range(MAX_USER_TEMPLATES)
    )
    payload = save_templates(make_collection(templates), expected_revision=3)
    assert len(payload["user_templates"]) == MAX_USER_TEMPLATES


@pytest.mark.parametrize(
    ("existing", "incoming"),
    [
        pytest.param(
            (make_template(name="市政标准目录"),),
            "市政标准目录",
            id="用户模板名重复",
        ),
        pytest.param((), "默认图纸目录（内置）", id="与内置模板名冲突"),
        pytest.param((make_template(name="ABC"),), "abc", id="casefold 重复"),
    ],
)
def test_save_templates_rejects_casefold_duplicate_template_names(
    existing, incoming
):
    collection = make_collection((*existing, make_template(name=incoming)))
    with pytest.raises(SheetCatalogError) as excinfo:
        save_templates(collection, expected_revision=collection.revision)
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_COLUMN_DUPLICATE"
    assert error.params == {"header": incoming}


def test_save_templates_requires_saved_template_ids():
    # 未命名草稿（template_id=None）必须先分配 UUID 才能保存。
    draft = SheetCatalogTemplate(
        template_id=None,
        name="未命名草稿",
        schema_version=1,
        columns=(make_column("图号", "{sheet.number}"),),
    )
    with pytest.raises(ValueError, match="SHEET_CATALOG_TEMPLATE_ID_REQUIRED"):
        save_templates(make_collection((draft,)), expected_revision=3)


# ---------------------------------------------------------------------------
# load_templates：默认合并、坏条目隔离诊断、未知高 schema 保留原 JSON
# ---------------------------------------------------------------------------


def test_load_templates_without_settings_returns_default_collection():
    collection = load_templates(None)
    assert collection.revision == 0
    assert collection.builtin is DEFAULT_TEMPLATE
    assert collection.user_templates == ()


def test_load_templates_skips_invalid_entry_with_stable_diagnostic(caplog):
    good = make_template()
    payload = save_templates(make_collection((good,)), expected_revision=3)
    broken = dict(payload["user_templates"][0])
    broken["name"] = ""
    payload = dict(payload, user_templates=[broken, payload["user_templates"][0]])
    with caplog.at_level(logging.WARNING, logger="dst_manager.extensions.builtin.sheet_catalog.templates"):
        collection = load_templates(VersionedJson(schema_version=1, revision=2, value=payload))
    assert collection.user_templates == (good,)
    assert "SHEET_CATALOG_TEMPLATES_SKIPPED" in caplog.text
    assert good.name not in caplog.text


def test_load_templates_preserves_unknown_high_schema_json_with_diagnostic(caplog):
    raw_value = {"user_templates": [{"unknown": "future-shape"}], "future_field": 1}
    settings = VersionedJson(schema_version=2, revision=5, value=raw_value)
    with caplog.at_level(logging.WARNING, logger="dst_manager.extensions.builtin.sheet_catalog.templates"):
        collection = load_templates(settings)
    # 未知高 schema 不加载为可编辑状态，但原 JSON 原样保留（不重写、不变更）。
    assert collection.revision == 5
    assert collection.builtin is DEFAULT_TEMPLATE
    assert collection.user_templates == ()
    assert settings.value == raw_value
    assert settings.schema_version == 2
    assert "SHEET_CATALOG_SETTINGS_SCHEMA_UNSUPPORTED" in caplog.text
    # Ruling-9：高 schema 集合必须带保留标记，堵住"按服务端修订原样覆盖 v2
    # JSON"的数据丢失通路。
    assert collection.unknown_schema_preserved is True


def test_save_templates_rejects_collection_loaded_from_unknown_high_schema(caplog):
    """高 schema 载入的集合即使 revision 与服务端一致也不得保存为 v1 负载。"""
    raw_value = {"user_templates": [{"unknown": "future-shape"}], "future_field": 1}
    settings = VersionedJson(schema_version=2, revision=5, value=raw_value)
    with caplog.at_level(logging.WARNING, logger="dst_manager.extensions.builtin.sheet_catalog.templates"):
        collection = load_templates(settings)
    with pytest.raises(SheetCatalogError) as excinfo:
        save_templates(collection, expected_revision=settings.revision)
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_TEMPLATE_CONFLICT"
    assert "schema" in error.message
    # 本地无编辑可丢、服务端原 JSON 依旧原样保留。
    assert settings.value == raw_value


def test_template_collection_defaults_to_savable_unknown_schema_flag():
    collection = make_collection((make_template(),))
    assert collection.unknown_schema_preserved is False
    payload = save_templates(collection, expected_revision=collection.revision)
    assert payload["schema_version"] == 1


def test_load_templates_skips_user_template_named_like_builtin(caplog):
    """与内置默认模板同名的用户模板不得加载，否则会卡死之后的全部保存。"""
    good = make_template(name="其他目录")
    good_json = save_templates(make_collection((good,)), expected_revision=3)[
        "user_templates"
    ][0]
    # 手改 settings JSON 注入与内置默认模板同名的用户模板（损坏数据形态）。
    builtin_named_json = dict(
        good_json,
        template_id=str(uuid.uuid4()),
        name=DEFAULT_TEMPLATE.name,
    )
    payload = {
        "schema_version": 1,
        "user_templates": [builtin_named_json, good_json],
    }
    with caplog.at_level(logging.WARNING, logger="dst_manager.extensions.builtin.sheet_catalog.templates"):
        collection = load_templates(
            VersionedJson(schema_version=1, revision=4, value=payload)
        )
    # 与内置名冲突的条目被跳过，其余正常加载。
    assert collection.user_templates == (good,)
    assert "SHEET_CATALOG_TEMPLATES_SKIPPED" in caplog.text
    # 跳过后保存恢复正常，不再被同名条目卡死。
    saved = save_templates(collection, expected_revision=4)
    assert saved["user_templates"] == [good_json]


def test_load_templates_ignores_non_list_user_templates_with_diagnostic(caplog):
    with caplog.at_level(logging.WARNING, logger="dst_manager.extensions.builtin.sheet_catalog.templates"):
        collection = load_templates(
            VersionedJson(schema_version=1, revision=1, value={"user_templates": "broken"})
        )
    assert collection.builtin is DEFAULT_TEMPLATE
    assert collection.user_templates == ()
    assert "SHEET_CATALOG_TEMPLATES_SKIPPED" in caplog.text


# ---------------------------------------------------------------------------
# delete_template：只删除当前用户模板，回退内置默认，不影响历史 Artifact
# ---------------------------------------------------------------------------


def test_delete_template_removes_only_target_user_template():
    first = make_template(name="市政标准目录")
    second = make_template(name="建筑专业目录")
    collection = make_collection((first, second))
    remaining = delete_template(collection, first.template_id)
    assert remaining.user_templates == (second,)
    # 删除当前用户模板后，选择回退内置默认模板：内置模板原样保留可选。
    assert remaining.builtin is DEFAULT_TEMPLATE
    assert remaining.revision == collection.revision
    # 删除只动模板设置：纯函数，不触碰原集合与任何 Artifact 仓储。
    assert collection.user_templates == (first, second)


def test_delete_template_rejects_unknown_or_builtin_identity():
    collection = make_collection((make_template(),))
    with pytest.raises(ValueError, match="SHEET_CATALOG_TEMPLATE_NOT_FOUND"):
        delete_template(collection, uuid.uuid4())
    with pytest.raises(ValueError, match="SHEET_CATALOG_TEMPLATE_NOT_FOUND"):
        delete_template(collection, DEFAULT_TEMPLATE.template_id)


def test_sheet_catalog_error_is_exception_with_migration_message():
    error = sheet_catalog_error("SHEET_CATALOG_FIELD_UNDEFINED", {"scope": "sheet", "name": "备注"})
    assert isinstance(error, Exception)
    assert "备注" in error.message
    with pytest.raises(SheetCatalogError):
        raise error
