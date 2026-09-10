"""PLAN-DM-020 Task 5：图纸目录受限表达式（解析/绑定/求值）与错误词汇。

覆盖：字面量与 ``{{``/``}}`` 转义、点号与 JSON 字符串字段、中文、空表达式、
未闭合/多余内容/非法转义/未知作用域/嵌套引用、函数与代码 payload 拒绝、
0-based 字符位置；固有字段优先与保留名方括号寻址、大小写绑定规范名、
缺定义结构化报错、缺值求值为空且分隔符保留；实现源码不含通用执行器。
"""

from pathlib import Path

import pytest

from dst_manager.extensions.builtin.sheet_catalog.errors import (
    SHEET_CATALOG_BLOCKING,
    SHEET_CATALOG_MESSAGE_KEYS,
    SHEET_CATALOG_PARAM_SCHEMAS,
    SHEET_CATALOG_USER_RESULTS,
    SheetCatalogError,
    sheet_catalog_error,
)
from dst_manager.extensions.builtin.sheet_catalog.expressions import (
    BoundExpression,
    BoundFieldToken,
    FieldToken,
    LiteralToken,
    bind_expression,
    evaluate_expression,
    field_reference,
    parse_expression,
)
from dst_manager.extensions.snapshots import (
    FieldCatalog,
    FieldDefinition,
    SheetSnapshot,
    SnapshotProperty,
    SnapshotPropertyScope,
)

# ---------------------------------------------------------------------------
# 夹具：字段目录与快照（手工构造，覆盖固有字段 + 两侧自定义属性）
# ---------------------------------------------------------------------------


def make_catalog() -> FieldCatalog:
    return FieldCatalog(
        sheetset=(
            FieldDefinition("sheetset", "项目名称", False),
            FieldDefinition("sheetset", "阶段", False),
        ),
        sheet=(
            FieldDefinition("sheet", "number", True),
            FieldDefinition("sheet", "title", True),
            FieldDefinition("sheet", "file_name", True),
            FieldDefinition("sheet", "专业代码", False),
            # 与固有字段同名的自定义保留属性（casefold 冲突）。
            FieldDefinition("sheet", "Number", False),
        ),
    )


def make_sheetset_scope() -> SnapshotPropertyScope:
    return SnapshotPropertyScope(
        custom_property_definitions=("项目名称", "阶段"),
        custom_properties=(
            SnapshotProperty("项目名称", "市政工程"),
            SnapshotProperty("阶段", ""),
        ),
    )


def make_sheet() -> SheetSnapshot:
    return SheetSnapshot(
        sheet_id="sheet-1",
        number="002",
        title="平面布置图",
        file_name="002 平面.dwg",
        custom_property_definitions=("专业代码", "Number"),
        custom_properties=(
            SnapshotProperty("专业代码", "水"),
            SnapshotProperty("Number", "自定义图号"),
        ),
    )


# ---------------------------------------------------------------------------
# 解析：字面量、转义、点号与 JSON 字符串字段、中文
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("A-001 图纸", (LiteralToken("A-001 图纸"),), id="纯字面量"),
        pytest.param("{{}}", (LiteralToken("{}"),), id="成对转义花括号"),
        pytest.param("{{{sheet.number}}}", (
            LiteralToken("{"),
            FieldToken("sheet", "number", 2, quoted=False),
            LiteralToken("}"),
        ), id="转义与字段混排"),
        pytest.param("{sheet.number}", (FieldToken("sheet", "number", 0, quoted=False),), id="点号固有字段"),
        pytest.param("{sheetset.项目名称}", (FieldToken("sheetset", "项目名称", 0, quoted=False),), id="点号中文字段"),
        pytest.param(
            '{sheetset["项目 名称"]}',
            (FieldToken("sheetset", "项目 名称", 0, quoted=True),),
            id="JSON 字符串字段含空格",
        ),
        pytest.param(
            '{sheet["专业.代码"]}',
            (FieldToken("sheet", "专业.代码", 0, quoted=True),),
            id="JSON 字符串字段含点号",
        ),
        pytest.param(
            '{sheet["A\\"B"]}',
            (FieldToken("sheet", 'A"B', 0, quoted=True),),
            id="JSON 字符串转义引号",
        ),
        pytest.param(
            '{sheet["\\u4e13\\u4e1a"]}',
            (FieldToken("sheet", "专业", 0, quoted=True),),
            id="JSON 字符串 Unicode 转义",
        ),
        pytest.param(
            "{sheet.专业代码}-{sheet.number}",
            (
                FieldToken("sheet", "专业代码", 0, quoted=False),
                LiteralToken("-"),
                FieldToken("sheet", "number", 13, quoted=False),
            ),
            id="多字段与分隔符",
        ),
    ],
)
def test_parse_expression_accepts_restricted_grammar(source, expected):
    assert parse_expression(source) == expected


# ---------------------------------------------------------------------------
# 解析：语法错误与 0-based 字符位置
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "source_start"),
    [
        pytest.param("", 0, id="空表达式"),
        pytest.param("{sheet.number", 0, id="未闭合引用"),
        pytest.param("{", 0, id="孤立花括号"),
        pytest.param("abc}", 3, id="多余右花括号"),
        pytest.param("{foo.bar}", 0, id="未知作用域"),
        pytest.param("{sheetx.y}", 0, id="未知作用域变体"),
        pytest.param("{sheet.{x}}", 7, id="嵌套引用"),
        pytest.param("{sheet}", 0, id="缺少名称分隔符"),
        pytest.param("{sheet.}", 7, id="点号后空名称"),
        pytest.param("{sheet.number}x}", 15, id="引用后多余内容"),
        pytest.param("{sheet['a']}", 7, id="JSON 形式必须双引号"),
        pytest.param('{sheet["a" ]}', 10, id="右括号前多余内容"),
        pytest.param("{sheet.number()}", 13, id="函数调用负载"),
        pytest.param("{sheet.a=b}", 8, id="赋值负载"),
        pytest.param("{__import__('os')}", 0, id="Python payload 拒绝"),
    ],
)
def test_parse_expression_rejects_with_zero_based_position(source, source_start):
    with pytest.raises(SheetCatalogError) as excinfo:
        parse_expression(source)
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_EXPRESSION_INVALID"
    assert error.blocking is True
    assert error.params["source_start"] == source_start


def test_parse_expression_rejects_invalid_json_escape_at_backslash_position():
    source = '{sheet["a\\qb"]}'
    with pytest.raises(SheetCatalogError) as excinfo:
        parse_expression(source)
    assert excinfo.value.code == "SHEET_CATALOG_EXPRESSION_INVALID"
    assert excinfo.value.params["source_start"] == source.index("\\")


@pytest.mark.parametrize(
    "source",
    ["{{ 7*7 }}", "{{ x | filter }} {{ x }}"],
)
def test_parse_expression_keeps_curly_payloads_as_literal_text(source):
    """模板引擎式/运算式负载不执行：全部退化为字面量，不做任何运算。"""
    tokens = parse_expression(source)
    assert all(isinstance(token, LiteralToken) for token in tokens)


# ---------------------------------------------------------------------------
# 绑定：固有字段优先、保留名方括号寻址、大小写规范名、缺定义
# ---------------------------------------------------------------------------


def test_bind_expression_prefers_builtin_over_same_name_custom_property():
    bound = bind_expression(parse_expression("{sheet.number}"), make_catalog())
    assert bound == BoundExpression((
        BoundFieldToken(scope="sheet", canonical_name="number", builtin=True),
    ))


def test_bind_expression_reaches_reserved_custom_property_only_via_bracket_form():
    bound = bind_expression(parse_expression('{sheet["Number"]}'), make_catalog())
    assert bound == BoundExpression((
        BoundFieldToken(scope="sheet", canonical_name="Number", builtin=False),
    ))


def test_bind_expression_matches_case_insensitively_to_canonical_name():
    catalog = FieldCatalog(
        sheetset=(FieldDefinition("sheetset", "ProjectName", False),),
        sheet=(FieldDefinition("sheet", "PROFESSIONAL", False),),
    )
    bound = bind_expression(parse_expression("{sheet.professional}"), catalog)
    assert bound.tokens[0] == BoundFieldToken("sheet", "PROFESSIONAL", False)
    sheetset_bound = bind_expression(
        parse_expression('{sheetset["projectname"]}'), catalog
    )
    assert sheetset_bound.tokens[0] == BoundFieldToken("sheetset", "ProjectName", False)


@pytest.mark.parametrize(
    "source",
    ["{sheet.备注}", '{sheet["备注"]}', "{sheetset.不存在的属性}"],
)
def test_bind_expression_raises_structured_undefined_field(source):
    with pytest.raises(SheetCatalogError) as excinfo:
        bind_expression(parse_expression(source), make_catalog())
    error = excinfo.value
    assert error.code == "SHEET_CATALOG_FIELD_UNDEFINED"
    assert error.blocking is True
    assert error.message_key == "errors.sheetCatalog.fieldUndefined"
    assert set(error.params) == {"scope", "name"}


def test_bind_expression_keeps_literals_and_binds_each_field():
    bound = bind_expression(
        parse_expression("{sheetset.项目名称}/{sheet.专业代码}-{sheet.number}"), make_catalog()
    )
    assert bound.tokens == (
        BoundFieldToken("sheetset", "项目名称", False),
        LiteralToken("/"),
        BoundFieldToken("sheet", "专业代码", False),
        LiteralToken("-"),
        BoundFieldToken("sheet", "number", True),
    )


# ---------------------------------------------------------------------------
# 求值：缺值为空且分隔符保留、转义输出、固有字段原样
# ---------------------------------------------------------------------------


def test_evaluate_expression_joins_tokens_with_values():
    bound = bind_expression(
        parse_expression("{sheetset.项目名称}-{sheet.专业代码}-{sheet.number}"), make_catalog()
    )
    assert (
        evaluate_expression(bound, make_sheetset_scope(), make_sheet())
        == "市政工程-水-002"
    )


def test_evaluate_expression_missing_value_is_empty_but_separators_kept():
    bound = bind_expression(parse_expression("{sheet.专业代码}-{sheet.number}"), make_catalog())
    sheet = SheetSnapshot(
        sheet_id="sheet-1",
        number="002",
        title="平面布置图",
        file_name="002 平面.dwg",
        custom_property_definitions=("专业代码",),
        custom_properties=(),
    )
    assert evaluate_expression(bound, make_sheetset_scope(), sheet) == "-002"


def test_evaluate_expression_defined_but_empty_value_yields_empty_string():
    bound = bind_expression(parse_expression("{sheetset.阶段}!{sheet.number}"), make_catalog())
    assert evaluate_expression(bound, make_sheetset_scope(), make_sheet()) == "!002"


def test_evaluate_expression_builtin_fields_and_escaped_braces():
    bound = bind_expression(parse_expression("{{{sheet.number}}} {sheet.title}"), make_catalog())
    assert evaluate_expression(bound, make_sheetset_scope(), make_sheet()) == "{002} 平面布置图"


def test_evaluate_expression_sheetset_scope_repeats_on_every_row():
    bound = bind_expression(parse_expression("{sheetset.项目名称}/{sheet.number}"), make_catalog())
    second = SheetSnapshot(
        sheet_id="sheet-2",
        number="003",
        title="剖面图",
        file_name="003 剖面.dwg",
        custom_property_definitions=(),
        custom_properties=(),
    )
    assert (
        evaluate_expression(bound, make_sheetset_scope(), make_sheet()) == "市政工程/002"
    )
    assert evaluate_expression(bound, make_sheetset_scope(), second) == "市政工程/003"


# ---------------------------------------------------------------------------
# field_reference：字段浏览器按规范名称插入正确语法
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scope", "name", "expected"),
    [
        pytest.param("sheet", "number", "{sheet.number}", id="固有字段点号"),
        pytest.param("sheet", "title", "{sheet.title}", id="固有字段点号二"),
        pytest.param("sheet", "专业代码", "{sheet.专业代码}", id="普通中文属性点号"),
        pytest.param("sheetset", "项目名称", "{sheetset.项目名称}", id="图纸集属性点号"),
        pytest.param("sheetset", "项目 名称", '{sheetset["项目 名称"]}', id="含空格方括号"),
        pytest.param("sheet", "专业.代码", '{sheet["专业.代码"]}', id="含点号方括号"),
        pytest.param("sheet", "Number", '{sheet["Number"]}', id="保留名冲突方括号"),
        pytest.param("sheet", 'A"B', '{sheet["A\\"B"]}', id="含引号方括号转义"),
    ],
)
def test_field_reference_emits_correct_syntax(scope, name, expected):
    assert field_reference(scope, name) == expected


# ---------------------------------------------------------------------------
# 错误词汇表：7 个目录码的 message_key、参数白名单与用户结果
# ---------------------------------------------------------------------------

EXPECTED_VOCABULARY = {
    "SHEET_CATALOG_EXPRESSION_INVALID": {
        "message_key": "errors.sheetCatalog.expressionInvalid",
        "params": {"source_start": int, "column_header": str},
        "result": "定位到具体列和字符位置，禁止预览与导出",
        "blocking": True,
    },
    "SHEET_CATALOG_FIELD_UNDEFINED": {
        "message_key": "errors.sheetCatalog.fieldUndefined",
        "params": {"scope": str, "name": str},
        "result": "显示缺少的作用域和属性名，禁止导出",
        "blocking": True,
    },
    "SHEET_CATALOG_VALUE_MISSING": {
        "message_key": "errors.sheetCatalog.valueMissing",
        "params": {"scope": str, "name": str, "sheet_count": int},
        "result": "显示字段和受影响行数，允许导出",
        "blocking": False,
    },
    "SHEET_CATALOG_COLUMN_DUPLICATE": {
        "message_key": "errors.sheetCatalog.columnDuplicate",
        "params": {"header": str},
        "result": "定位重复列名，禁止保存、预览和导出",
        "blocking": True,
    },
    "SHEET_CATALOG_TEMPLATE_LIMIT": {
        "message_key": "errors.sheetCatalog.templateLimit",
        "params": {"kind": str, "limit": int, "actual": int},
        "result": "显示具体限制，不截断数据",
        "blocking": True,
    },
    "SHEET_CATALOG_TEMPLATE_CONFLICT": {
        "message_key": "errors.sheetCatalog.templateConflict",
        "params": {"expected_revision": int, "current_revision": int},
        "result": "保留本地编辑，刷新模板修订后允许另存或重试",
        "blocking": True,
    },
    "SHEET_CATALOG_XLSX_INVALID": {
        "message_key": "errors.sheetCatalog.xlsxInvalid",
        "params": {"check": str},
        "result": "不保存候选文件，不登记成功 Artifact",
        "blocking": True,
    },
}


def test_error_vocabulary_covers_exactly_seven_catalog_codes():
    assert set(SHEET_CATALOG_MESSAGE_KEYS) == set(EXPECTED_VOCABULARY)
    assert set(SHEET_CATALOG_PARAM_SCHEMAS) == set(EXPECTED_VOCABULARY)
    assert set(SHEET_CATALOG_USER_RESULTS) == set(EXPECTED_VOCABULARY)
    assert set(SHEET_CATALOG_BLOCKING) == set(EXPECTED_VOCABULARY)


@pytest.mark.parametrize("code", sorted(EXPECTED_VOCABULARY))
def test_error_vocabulary_pins_message_key_params_and_user_result(code):
    expected = EXPECTED_VOCABULARY[code]
    assert SHEET_CATALOG_MESSAGE_KEYS[code] == expected["message_key"]
    assert SHEET_CATALOG_PARAM_SCHEMAS[code] == expected["params"]
    assert SHEET_CATALOG_USER_RESULTS[code] == expected["result"]
    assert SHEET_CATALOG_BLOCKING[code] is expected["blocking"]

    params = {
        name: ("x" if kind is str else 1) for name, kind in expected["params"].items()
    }
    error = sheet_catalog_error(code, params)
    assert error.code == code
    assert error.message_key == expected["message_key"]
    assert error.params == params
    assert error.blocking is expected["blocking"]
    assert error.message


def test_value_missing_is_an_executable_warning_not_a_blocker():
    error = sheet_catalog_error(
        "SHEET_CATALOG_VALUE_MISSING", {"scope": "sheet", "name": "专业代码", "sheet_count": 3}
    )
    assert error.blocking is False


def test_error_factory_rejects_params_outside_vocabulary():
    with pytest.raises(ValueError):
        sheet_catalog_error("SHEET_CATALOG_COLUMN_DUPLICATE", {"unexpected": "x"})
    with pytest.raises(ValueError):
        sheet_catalog_error("SHEET_CATALOG_NOT_IN_VOCABULARY")
    with pytest.raises(ValueError):
        sheet_catalog_error("SHEET_CATALOG_TEMPLATE_LIMIT", {"kind": "columns", "limit": "50"})
    with pytest.raises(ValueError):
        sheet_catalog_error("SHEET_CATALOG_TEMPLATE_LIMIT", {"kind": "columns", "limit": 50, "actual": "3"})


# ---------------------------------------------------------------------------
# 安全红线：实现源码不含通用执行器
# ---------------------------------------------------------------------------


def test_implementation_source_contains_no_universal_executors():
    package = Path(__file__).parents[2] / "src/dst_manager/extensions/builtin/sheet_catalog"
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(package.glob("*.py"))
    )
    lowered = sources.lower()
    assert "eval(" not in lowered
    assert "exec(" not in lowered
    assert "jinja" not in lowered
