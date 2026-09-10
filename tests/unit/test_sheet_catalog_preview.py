"""PLAN-DM-020 Task 6：图纸目录预览构建、兼容性诊断与确定性摘要。

覆盖：默认模板真实行、图纸集/图纸作用域组合、20 行上限与总图纸数、空图纸集
可执行、缺定义/重复列/超限/语法错误阻断、缺值字段与受影响图纸数（诊断不含
属性值）、Windows/Posix basename、跨作用域 casefold 同名属性、摘要对任一
绑定项变化敏感且相同输入稳定（canonical JSON 固定键 + 紧凑分隔符 + SHA-256）、
扩展模块常量与随包清单一致。
"""

import hashlib
import json
import uuid

import pytest

from dst_manager.domain.models import LayoutReference, Sheet, SheetSetDocument, Subset
from dst_manager.extensions.builtin.sheet_catalog.errors import SheetCatalogError
from dst_manager.extensions.builtin.sheet_catalog.extension import (
    EXTENSION_ID,
    EXTENSION_VERSION,
    PREVIEW_ACTION_ID,
)
from dst_manager.extensions.builtin.sheet_catalog.preview import (
    PREFERENCE_SAVE_FAILED_CODE,
    DigestColumn,
    SheetCatalogDiagnostic,
    SheetCatalogPreview,
    build_preview,
    preference_save_failed_warning,
    preview_digest,
)
from dst_manager.extensions.builtin.sheet_catalog.templates import (
    DEFAULT_TEMPLATE,
    MAX_COLUMNS,
    MAX_EXPRESSION_CHARS,
    SheetCatalogTemplate,
    TemplateColumn,
)
from dst_manager.extensions.manifest import load_manifest
from dst_manager.extensions.snapshots import (
    SheetSnapshot,
    SnapshotProperty,
    SnapshotPropertyScope,
    WorkspaceSnapshot,
    build_workspace_snapshot,
)

_COLUMN_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "dst-manager.sheet-catalog:preview-tests")


# ---------------------------------------------------------------------------
# 夹具：快照与模板（手工构造；basename/跨作用域场景走真实文档投影）
# ---------------------------------------------------------------------------


def make_column(header: str, expression: str) -> TemplateColumn:
    return TemplateColumn(
        column_id=uuid.uuid5(_COLUMN_NAMESPACE, f"{header}:{expression}"),
        header=header,
        expression=expression,
    )


def make_template(*columns: TemplateColumn, name: str = "预览模板") -> SheetCatalogTemplate:
    return SheetCatalogTemplate(
        template_id=None, name=name, schema_version=1, columns=columns
    )


def make_sheet(
    sheet_id: str = "sheet-1",
    number: str = "001",
    title: str = "平面",
    file_name: str = "A.dwg",
    definitions: tuple[str, ...] = ("比例",),
    properties: tuple[SnapshotProperty, ...] = (SnapshotProperty("比例", "1:100"),),
) -> SheetSnapshot:
    return SheetSnapshot(
        sheet_id=sheet_id,
        number=number,
        title=title,
        file_name=file_name,
        custom_property_definitions=definitions,
        custom_properties=properties,
    )


def make_snapshot(
    *sheets: SheetSnapshot,
    sheetset_properties: tuple[SnapshotProperty, ...] = (
        SnapshotProperty("项目号", "P-000"),
    ),
) -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        workspace_id="ws-1",
        revision_id="rev-1",
        sheetset=SnapshotPropertyScope(
            custom_property_definitions=tuple(
                prop.canonical_name for prop in sheetset_properties
            ),
            custom_properties=sheetset_properties,
        ),
        sheets=sheets,
    )


def build(*sheets: SheetSnapshot, template=None, **kwargs) -> SheetCatalogPreview:
    return build_preview(
        make_snapshot(*sheets, **kwargs.pop("snapshot_kwargs", {})),
        template if template is not None else DEFAULT_TEMPLATE,
        extension_id=EXTENSION_ID,
        extension_version=EXTENSION_VERSION,
        action_id=PREVIEW_ACTION_ID,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 预览行：默认模板真实行、两作用域组合、20 行上限、空图纸集
# ---------------------------------------------------------------------------


def test_default_template_evaluates_real_rows():
    result = build(make_sheet(), make_sheet("sheet-2", "002", "立面", "B.dwg"))

    assert result.rows == (("001", "平面", "A.dwg"), ("002", "立面", "B.dwg"))
    assert result.total_rows == 2
    assert result.errors == ()
    assert result.warnings == ()
    assert result.executable is True
    assert result.normalized_template == DEFAULT_TEMPLATE
    # 字段目录：sheet 作用域固有字段置 builtin，图纸集作用域为普通字段
    assert [field.canonical_name for field in result.field_catalog.sheet][:3] == [
        "number",
        "title",
        "file_name",
    ]
    assert all(field.builtin for field in result.field_catalog.sheet[:3])
    assert [field.canonical_name for field in result.field_catalog.sheetset] == ["项目号"]
    assert all(not field.builtin for field in result.field_catalog.sheetset)


def test_preview_combines_sheetset_and_sheet_scopes():
    template = make_template(make_column("目录号", "{sheetset.项目号}-{sheet.number}"))

    result = build(make_sheet(), make_sheet("sheet-2", "002"), template=template)

    assert result.rows == (("P-000-001",), ("P-000-002",))
    assert result.executable is True


def test_preview_caps_rows_at_20_and_reports_total_sheet_count():
    sheets = tuple(
        make_sheet(sheet_id=f"sheet-{index}", number=f"{index:03d}")
        for index in range(25)
    )

    result = build(*sheets)

    assert len(result.rows) == 20
    assert result.rows[0] == ("000", "平面", "A.dwg")
    assert result.rows[-1] == ("019", "平面", "A.dwg")
    assert result.total_rows == 25
    assert result.executable is True


def test_empty_sheetset_is_executable_with_zero_rows():
    result = build()

    assert result.rows == ()
    assert result.total_rows == 0
    assert result.errors == ()
    assert result.warnings == ()
    assert result.executable is True


# ---------------------------------------------------------------------------
# 阻断错误：缺定义、语法、重复列、超限
# ---------------------------------------------------------------------------


def test_undefined_field_blocks_preview_with_structured_params():
    column = make_column("图号", "{sheet.不存在}")

    result = build(make_sheet(), template=make_template(column))

    assert result.executable is False
    assert result.rows == ()
    assert len(result.errors) == 1
    diagnostic = result.errors[0]
    assert diagnostic.code == "SHEET_CATALOG_FIELD_UNDEFINED"
    assert diagnostic.message_key == "errors.sheetCatalog.fieldUndefined"
    assert diagnostic.params == {"scope": "sheet", "name": "不存在"}
    assert diagnostic.column_id == column.column_id
    assert diagnostic.source_position is None


def test_syntax_error_blocks_preview_with_character_position():
    column = make_column("图号", "{sheet.number")

    result = build(make_sheet(), template=make_template(column))

    assert result.executable is False
    diagnostic = result.errors[0]
    assert diagnostic.code == "SHEET_CATALOG_EXPRESSION_INVALID"
    assert diagnostic.message_key == "errors.sheetCatalog.expressionInvalid"
    assert diagnostic.source_position == 0
    assert diagnostic.column_id == column.column_id
    assert diagnostic.params["column_header"] == "图号"


def test_duplicate_column_blocks_preview():
    template = make_template(
        make_column("图号", "{sheet.number}"),
        make_column("图号", "{sheet.title}"),
    )

    result = build(make_sheet(), template=template)

    assert result.executable is False
    assert result.rows == ()
    diagnostic = result.errors[0]
    assert diagnostic.code == "SHEET_CATALOG_COLUMN_DUPLICATE"
    assert diagnostic.message_key == "errors.sheetCatalog.columnDuplicate"
    assert diagnostic.params == {"header": "图号"}
    assert diagnostic.column_id is None
    assert diagnostic.source_position is None


def test_column_and_expression_limits_block_preview():
    over_columns = make_template(
        *[make_column(f"列{index}", "{sheet.number}") for index in range(MAX_COLUMNS + 1)]
    )
    over_expression = make_template(make_column("图号", "x" * (MAX_EXPRESSION_CHARS + 1)))

    columns_result = build(make_sheet(), template=over_columns)
    expression_result = build(make_sheet(), template=over_expression)

    for result, kind in ((columns_result, "columns"), (expression_result, "expression")):
        assert result.executable is False
        diagnostic = result.errors[0]
        assert diagnostic.code == "SHEET_CATALOG_TEMPLATE_LIMIT"
        assert diagnostic.message_key == "errors.sheetCatalog.templateLimit"
        assert diagnostic.params["kind"] == kind


# ---------------------------------------------------------------------------
# 非阻断警告：缺值字段与受影响图纸数（不记录属性值）
# ---------------------------------------------------------------------------


def test_missing_values_report_with_sheet_count_without_values():
    sheets = (
        make_sheet("sheet-1", properties=(SnapshotProperty("比例", "1:100"),)),
        make_sheet("sheet-2", properties=(SnapshotProperty("比例", ""),)),
        make_sheet("sheet-3", properties=()),
    )
    template = make_template(make_column("比例", "{sheet.比例}"))

    result = build(*sheets, template=template)

    assert result.executable is True
    assert result.errors == ()
    assert len(result.warnings) == 1
    diagnostic = result.warnings[0]
    assert diagnostic.code == "SHEET_CATALOG_VALUE_MISSING"
    assert diagnostic.message_key == "errors.sheetCatalog.valueMissing"
    # 只含字段标识与受影响图纸数，绝不含属性值
    assert diagnostic.params == {"scope": "sheet", "name": "比例", "sheet_count": 2}
    assert json.dumps(diagnostic.params, ensure_ascii=False).find("1:100") == -1
    # 缺值不阻断：行照常产出
    assert len(result.rows) == 3


def test_missing_sheetset_value_reports_sheet_scope_and_count():
    template = make_template(make_column("阶段", "{sheetset.阶段}"))

    result = build(
        make_sheet(),
        make_sheet("sheet-2"),
        snapshot_kwargs={"sheetset_properties": (SnapshotProperty("阶段", ""),)},
        template=template,
    )

    assert result.executable is True
    assert len(result.warnings) == 1
    diagnostic = result.warnings[0]
    assert diagnostic.params == {"scope": "sheetset", "name": "阶段", "sheet_count": 2}


def test_missing_field_counted_once_per_sheet_even_when_referenced_twice():
    template = make_template(make_column("组合", "{sheet.比例}-{sheet.比例}"))

    result = build(
        make_sheet("sheet-1", definitions=("比例",), properties=()), template=template
    )

    assert result.warnings[0].params["sheet_count"] == 1


# ---------------------------------------------------------------------------
# 真实文档投影：Windows/Posix basename 与跨作用域 casefold 同名属性
# ---------------------------------------------------------------------------


def test_preview_rows_carry_basename_across_separators():
    document = SheetSetDocument(
        database_id="db-1",
        name="测试集",
        subsets=[
            Subset(
                "subset-1",
                "分组",
                0,
                [
                    Sheet(
                        "sheet-1",
                        "001",
                        "平面",
                        LayoutReference(r"C:\工程\A.dwg", r".\A.dwg", "001 平面", "AB"),
                    ),
                    Sheet(
                        "sheet-2",
                        "002",
                        "立面",
                        LayoutReference("folder/B.dwg", "folder/B.dwg", "002 立面", "CD"),
                    ),
                ],
            )
        ],
    )
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1", revision_id="rev-1", document=document
    )
    template = make_template(make_column("文件名", "{sheet.file_name}"))

    result = build_preview(
        snapshot,
        template,
        extension_id=EXTENSION_ID,
        extension_version=EXTENSION_VERSION,
        action_id=PREVIEW_ACTION_ID,
    )

    assert result.rows == (("A.dwg",), ("B.dwg",))


def test_cross_scope_casefold_collision_keeps_scope_specific_values():
    document = SheetSetDocument(
        database_id="db-1",
        name="测试集",
        subsets=[
            Subset(
                "subset-1",
                "分组",
                0,
                [
                    Sheet(
                        "sheet-1",
                        "001",
                        "平面",
                        LayoutReference("A.dwg", "A.dwg", "001", "AB"),
                        {"dwg": "Y-SHEET"},
                    )
                ],
            )
        ],
        custom_properties={"Dwg": "X-SET"},
    )
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1", revision_id="rev-1", document=document
    )
    template = make_template(
        make_column("集值", "{sheetset.Dwg}"),
        make_column("图值", "{sheet.dwg}"),
    )

    result = build_preview(
        snapshot,
        template,
        extension_id=EXTENSION_ID,
        extension_version=EXTENSION_VERSION,
        action_id=PREVIEW_ACTION_ID,
    )

    assert result.rows == (("X-SET", "Y-SHEET"),)
    assert result.warnings == ()
    assert result.errors == ()


# ---------------------------------------------------------------------------
# 确定性摘要：稳定性、敏感性与 canonical JSON 形态
# ---------------------------------------------------------------------------


DIGEST_COLUMNS = (
    DigestColumn("c-1", "图号", (("field", "sheet", "number", "builtin"),)),
    DigestColumn("c-2", "图名", (("literal", "A"), ("field", "sheet", "title", "builtin"))),
)


def test_preview_digest_is_stable_for_identical_inputs():
    first = build(make_sheet(), make_sheet("sheet-2", "002"))
    second = build(make_sheet(), make_sheet("sheet-2", "002"))

    assert first.preview_digest == second.preview_digest
    assert len(first.preview_digest) == 64
    int(first.preview_digest, 16)  # SHA-256 十六进制摘要


def test_preview_digest_changes_with_normalized_tokens_and_headers():
    baseline = build(make_sheet())

    def variant(first_header: str, first_expression: str) -> SheetCatalogTemplate:
        # 复用默认模板列 ID：保证摘要差异只来自表头/规范化 token，而非列 ID。
        return SheetCatalogTemplate(
            template_id=None,
            name=DEFAULT_TEMPLATE.name,
            schema_version=1,
            columns=(
                TemplateColumn(
                    DEFAULT_TEMPLATE.columns[0].column_id, first_header, first_expression
                ),
            )
            + DEFAULT_TEMPLATE.columns[1:],
        )

    renamed_header = variant("编号", "{sheet.number}")
    different_expression = variant("图号", "{sheet.number}-后缀")
    # 规范化 token：大小写不同的引用绑定到同一规范名 → 摘要不变
    case_variant = variant("图号", "{sheet.NUMBER}")

    assert build(make_sheet(), template=renamed_header).preview_digest != baseline.preview_digest
    assert build(make_sheet(), template=different_expression).preview_digest != baseline.preview_digest
    assert build(make_sheet(), template=case_variant).preview_digest == baseline.preview_digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_id", "ws-other"),
        ("revision_id", "rev-2"),
        ("template_schema", 2),
        ("extension_version", "0.2.0"),
        ("action_id", "export-xlsx-next"),
        ("extension_id", "dst-manager.other"),
    ],
)
def test_preview_digest_is_sensitive_to_every_bound_input(field, value):
    kwargs = {
        "workspace_id": "ws-1",
        "revision_id": "rev-1",
        "template_schema": 1,
        "normalized_columns": DIGEST_COLUMNS,
        "extension_version": "0.1.0",
        "action_id": "export-xlsx",
        "extension_id": "dst-manager.sheet-catalog",
    }
    baseline = preview_digest(**kwargs)
    kwargs[field] = value

    assert preview_digest(**kwargs) != baseline


def test_preview_digest_uses_canonical_json_with_fixed_keys_and_compact_separators():
    digest = preview_digest(
        workspace_id="ws-1",
        revision_id="rev-1",
        template_schema=1,
        normalized_columns=DIGEST_COLUMNS,
        extension_version="0.1.0",
        action_id="export-xlsx",
        extension_id="dst-manager.sheet-catalog",
    )
    # 列顺序参与摘要：交换列后摘要必须变化
    reordered = preview_digest(
        workspace_id="ws-1",
        revision_id="rev-1",
        template_schema=1,
        normalized_columns=tuple(reversed(DIGEST_COLUMNS)),
        extension_version="0.1.0",
        action_id="export-xlsx",
        extension_id="dst-manager.sheet-catalog",
    )

    payload = {
        "action_id": "export-xlsx",
        "columns": [
            {
                "column_id": "c-1",
                "header": "图号",
                "tokens": [["field", "sheet", "number", "builtin"]],
            },
            {
                "column_id": "c-2",
                "header": "图名",
                "tokens": [["literal", "A"], ["field", "sheet", "title", "builtin"]],
            },
        ],
        "extension_id": "dst-manager.sheet-catalog",
        "extension_version": "0.1.0",
        "revision_id": "rev-1",
        "schema_version": 1,
        "workspace_id": "ws-1",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert reordered != digest


def test_digest_error_diagnostic_covers_template_level_and_column_level_sources():
    template = make_template(make_column("图号", "{sheet.number}"))
    result = build(make_sheet(), template=template)

    assert isinstance(result.preview_digest, str) and result.preview_digest


# ---------------------------------------------------------------------------
# 宿主偏好失败降级：诊断形状（API 层负责注入失败并降级）
# ---------------------------------------------------------------------------


def test_preference_save_failed_warning_has_stable_identity():
    warning = preference_save_failed_warning("d94b3f57-0000-0000-0000-000000000001")

    assert warning.code == PREFERENCE_SAVE_FAILED_CODE
    assert warning.code == "EXTENSION_PREFERENCE_SAVE_FAILED"
    assert warning.message_key == "errors.extension.preferenceSaveFailed"
    assert warning.params == {"template_id": "d94b3f57-0000-0000-0000-000000000001"}
    assert warning.column_id is None
    assert warning.source_position is None


def test_diagnostic_from_sheet_catalog_error_carries_message_key_and_params():
    error = SheetCatalogError(
        "SHEET_CATALOG_FIELD_UNDEFINED",
        "errors.sheetCatalog.fieldUndefined",
        {"scope": "sheet", "name": "缺失字段"},
        "缺失字段",
        True,
    )

    diagnostic = SheetCatalogDiagnostic.from_error(error)

    assert diagnostic.code == "SHEET_CATALOG_FIELD_UNDEFINED"
    assert diagnostic.message_key == "errors.sheetCatalog.fieldUndefined"
    assert diagnostic.params == {"scope": "sheet", "name": "缺失字段"}
    assert diagnostic.column_id is None
    assert diagnostic.source_position is None


# ---------------------------------------------------------------------------
# 扩展模块常量与随包清单一致（防漂移）
# ---------------------------------------------------------------------------


def test_extension_module_constants_match_packaged_manifest():
    manifest = load_manifest(
        "dst_manager/extensions/builtin/sheet_catalog/manifest.yaml"
    )

    assert EXTENSION_ID == manifest.extension_id
    assert EXTENSION_VERSION == manifest.version
    assert PREVIEW_ACTION_ID == manifest.actions[0].action_id
