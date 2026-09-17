"""草稿校验、不可变修订与确定性计划（PLAN-DB-001 Task 2，SPEC-DB-001 §4/§5/§11）。

覆盖：

* ``validate_draft`` 参数化字段规则：长度、控制字符、非法字符、图号溢出、
  恰好一张图纸、输出目录已存在、派生危险名称；
* 诊断码只使用 §11 固定码（PROJECT_PATH_INVALID / PACKAGE_TARGET_EXISTS /
  PLAN_STALE）加单一草稿字段码 DRAFT_FIELD_INVALID（``field`` 区分字段）；
* ``commit_revision``：output_path 不入哈希、空白差异不影响哈希、资产排序无关、
  业务字段或资产字节变化必然改变修订 ID；
* ``create_plan``：确定性 ID、expected_artifacts 固定清单；
* ``check_plan_stale``：修订变化使确认失效，仅改 output_path 不失效。
"""

import dataclasses

import pytest

from dst_builder.domain.models import (
    AssetRole,
    AssetSnapshot,
    DiagnosticSeverity,
    DraftProjectV1,
    NumberingInput,
    ProjectInput,
    SheetInput,
    TemplateInput,
)
from dst_builder.domain.normalization import (
    dwg_name,
    layout_name,
    revision_id_from_sha256,
    sheet_number,
    task_id_from_revision_sha256,
)
from dst_builder.domain.planning import (
    PACKAGE_TARGET_EXISTS,
    PLAN_STALE,
    PROJECT_PATH_INVALID,
    check_plan_stale,
    commit_revision,
    create_plan,
    revision_payload,
    validate_draft,
)

BASE_DRAFT = DraftProjectV1(
    project=ProjectInput(
        name="示例工程",
        stage="施工图",
        discipline="建筑",
        output_path="D:/deliveries/example-package",
    ),
    numbering=NumberingInput(prefix="A-", start=1, width=3),
    cad_version="2020",
    sheets=(SheetInput(title="首层平面图"),),
    template=TemplateInput(
        base_asset_id="3f6b5a24-6a8e-4c2a-9c8f-0f5d7a1b2c31",
        layout_asset_id="8c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
        source_layout="A1",
    ),
)

BASE_ASSETS = (
    AssetSnapshot(
        role=AssetRole.BASE,
        relative_path="assets/base/"
        + "a" * 64
        + ".dwg",
        sha256="a" * 64,
        size=2048,
    ),
    AssetSnapshot(
        role=AssetRole.LAYOUT,
        relative_path="assets/layout/"
        + "b" * 64
        + ".dwt",
        sha256="b" * 64,
        size=4096,
    ),
)


def draft_with(**overrides: object) -> DraftProjectV1:
    return dataclasses.replace(BASE_DRAFT, **overrides)


def codes(diagnostics: tuple) -> set[str]:
    return {diagnostic.code for diagnostic in diagnostics}


def fields_of(diagnostics: tuple, code: str) -> set[str]:
    return {diagnostic.field for diagnostic in diagnostics if diagnostic.code == code}


# ---------------------------------------------------------------------------
# validate_draft：合法与边界
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"project": dataclasses.replace(BASE_DRAFT.project, name="工" * 100)},
        {"numbering": NumberingInput(prefix="前" * 20, start=0, width=1)},
        {"numbering": NumberingInput(prefix="A-", start=999999, width=6)},
        {"cad_version": "2016"},
        {"sheets": (SheetInput(title="图" * 100),)},  # 图名恰好 100 字符
        {
            "project": dataclasses.replace(
                BASE_DRAFT.project, output_path=r"D:\deliveries\example-package"
            )
        },
    ],
    ids=[
        "规范样例",
        "工程名恰好100字符",
        "前缀恰好20字符且序号下界",
        "序号上界6位",
        "cad版本2016",
        "图名恰好100字符",
        "Windows反斜杠绝对路径",
    ],
)
def test_valid_and_boundary_drafts_pass(overrides: dict) -> None:
    draft = draft_with(**overrides)
    assert validate_draft(draft, output_exists=False) == ()


def test_output_target_existing_is_rejected() -> None:
    """确认计划时成果目标目录不得存在（§5）。"""
    diagnostics = validate_draft(BASE_DRAFT, output_exists=True)
    assert codes(diagnostics) == {PACKAGE_TARGET_EXISTS}
    assert fields_of(diagnostics, PACKAGE_TARGET_EXISTS) == {"project.output_path"}
    assert all(item.severity is DiagnosticSeverity.BLOCKING for item in diagnostics)


# ---------------------------------------------------------------------------
# validate_draft：字段规则参数化
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected_field"),
    [
        ({"project": dataclasses.replace(BASE_DRAFT.project, name="")}, "project.name"),
        (
            {"project": dataclasses.replace(BASE_DRAFT.project, name="工" * 101)},
            "project.name",
        ),
        (
            {"project": dataclasses.replace(BASE_DRAFT.project, name="示例\n工程")},
            "project.name",
        ),
        (
            {"project": dataclasses.replace(BASE_DRAFT.project, stage="")},
            "project.stage",
        ),
        (
            {"project": dataclasses.replace(BASE_DRAFT.project, stage="阶" * 101)},
            "project.stage",
        ),
        (
            {"project": dataclasses.replace(BASE_DRAFT.project, discipline="")},
            "project.discipline",
        ),
        (
            {"project": dataclasses.replace(BASE_DRAFT.project, discipline="专" * 101)},
            "project.discipline",
        ),
        (
            {"numbering": NumberingInput(prefix="前" * 21, start=1, width=3)},
            "numbering.prefix",
        ),
        (
            {"numbering": NumberingInput(prefix="A?", start=1, width=3)},
            "numbering.prefix",
        ),
        (
            {"numbering": NumberingInput(prefix="A\\", start=1, width=3)},
            "numbering.prefix",
        ),
        (
            {"numbering": NumberingInput(prefix="A/", start=1, width=3)},
            "numbering.prefix",
        ),
        (
            {"numbering": NumberingInput(prefix="A.", start=1, width=3)},
            "numbering.prefix",
        ),
        (
            {"numbering": NumberingInput(prefix="A-", start=-1, width=3)},
            "numbering.start",
        ),
        (
            {"numbering": NumberingInput(prefix="A-", start=1000000, width=6)},
            "numbering.start",
        ),
        (
            {"numbering": NumberingInput(prefix="A-", start=1000, width=3)},
            "numbering.start",
        ),
        (
            {"numbering": NumberingInput(prefix="A-", start=1, width=0)},
            "numbering.width",
        ),
        (
            {"numbering": NumberingInput(prefix="A-", start=1, width=7)},
            "numbering.width",
        ),
        ({"cad_version": "2018"}, "cad_version"),
        ({"cad_version": ""}, "cad_version"),
        ({"sheets": ()}, "sheets"),
        (
            {"sheets": (SheetInput(title="首层平面图"), SheetInput(title="二层平面图"))},
            "sheets",
        ),
        ({"sheets": (SheetInput(title=""),)}, "sheets[0].title"),
        ({"sheets": (SheetInput(title="图" * 101),)}, "sheets[0].title"),
        ({"sheets": (SheetInput(title="首层\x07平面图"),)}, "sheets[0].title"),
        (
            {
                "template": dataclasses.replace(
                    BASE_DRAFT.template, base_asset_id="nope"
                )
            },
            "template.base_asset_id",
        ),
        (
            {
                "template": dataclasses.replace(
                    BASE_DRAFT.template, layout_asset_id=""
                )
            },
            "template.layout_asset_id",
        ),
        (
            {
                "template": dataclasses.replace(
                    BASE_DRAFT.template, source_layout="Model"
                )
            },
            "template.source_layout",
        ),
        (
            {
                "template": dataclasses.replace(
                    BASE_DRAFT.template, source_layout=""
                )
            },
            "template.source_layout",
        ),
        (
            {
                "project": dataclasses.replace(
                    BASE_DRAFT.project, output_path="deliveries/example-package"
                )
            },
            "project.output_path",
        ),
        (
            {
                "project": dataclasses.replace(
                    BASE_DRAFT.project, output_path="D:relative"
                )
            },
            "project.output_path",
        ),
    ],
)
def test_invalid_field_rules_yield_blocking_diagnostics(
    overrides: dict, expected_field: str
) -> None:
    diagnostics = validate_draft(draft_with(**overrides), output_exists=False)
    assert diagnostics, "字段违规必须产生阻断诊断"
    assert codes(diagnostics) <= {"DRAFT_FIELD_INVALID", PROJECT_PATH_INVALID}
    assert expected_field in fields_of(diagnostics, "DRAFT_FIELD_INVALID") | fields_of(
        diagnostics, PROJECT_PATH_INVALID
    )


def test_derived_dangerous_layout_name_yields_title_diagnostic() -> None:
    """图名带入危险字符使派生 layout_name/dwg_name 违反 §4 危险名称规则。"""
    draft = draft_with(sheets=(SheetInput(title="首层?平面图"),))
    diagnostics = validate_draft(draft, output_exists=False)
    assert "sheets[0].title" in fields_of(diagnostics, "DRAFT_FIELD_INVALID")


def test_derived_name_length_limit_unreachable_via_single_sheet_fields() -> None:
    """§4 基名 180 上限在字段上限内不可达（前缀 20 + 序号 6 + 图名 100 = 127），
    该上限由共享命名函数直接参数化覆盖（test_naming.py）。"""
    draft = draft_with(
        numbering=NumberingInput(prefix="前" * 20, start=999999, width=6),
        sheets=(SheetInput(title="图" * 100),),
    )
    assert validate_draft(draft, output_exists=False) == ()


def test_absolute_output_path_forms_accepted() -> None:
    for output_path in ("D:/deliveries/pkg", r"D:\deliveries\pkg", "//server/share/pkg"):
        draft = draft_with(
            project=dataclasses.replace(BASE_DRAFT.project, output_path=output_path)
        )
        assert validate_draft(draft, output_exists=False) == ()


# ---------------------------------------------------------------------------
# commit_revision：不可变修订与确定性哈希
# ---------------------------------------------------------------------------


def test_revision_id_matches_spec_derivation_and_is_deterministic() -> None:
    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    assert revision.revision_id == revision_id_from_sha256(revision.revision_sha256)
    assert commit_revision(BASE_DRAFT, BASE_ASSETS) == revision


def test_output_path_does_not_enter_revision_hash() -> None:
    """只改变 output_path 不产生新修订（§5），且修订载荷不保存 output_path。"""
    moved = draft_with(
        project=dataclasses.replace(
            BASE_DRAFT.project, output_path="E:/other-place/package"
        )
    )
    left = commit_revision(BASE_DRAFT, BASE_ASSETS)
    right = commit_revision(moved, BASE_ASSETS)
    assert left.revision_sha256 == right.revision_sha256
    assert left.revision_id == right.revision_id
    assert "output_path" not in revision_payload(BASE_DRAFT, BASE_ASSETS)


def test_business_field_change_changes_revision_id() -> None:
    renamed = draft_with(sheets=(SheetInput(title="二层平面图"),))
    assert commit_revision(renamed, BASE_ASSETS).revision_id != (
        commit_revision(BASE_DRAFT, BASE_ASSETS).revision_id
    )


def test_asset_hash_change_changes_revision_id() -> None:
    changed_assets = (
        AssetSnapshot(
            role=AssetRole.BASE,
            relative_path=BASE_ASSETS[0].relative_path,
            sha256="c" * 64,
            size=2048,
        ),
        BASE_ASSETS[1],
    )
    assert commit_revision(BASE_DRAFT, changed_assets).revision_id != (
        commit_revision(BASE_DRAFT, BASE_ASSETS).revision_id
    )


def test_asset_size_change_changes_revision_id() -> None:
    changed_assets = (
        AssetSnapshot(
            role=AssetRole.BASE,
            relative_path=BASE_ASSETS[0].relative_path,
            sha256=BASE_ASSETS[0].sha256,
            size=9999,
        ),
        BASE_ASSETS[1],
    )
    assert commit_revision(BASE_DRAFT, changed_assets).revision_id != (
        commit_revision(BASE_DRAFT, BASE_ASSETS).revision_id
    )


def test_asset_order_does_not_change_revision_id() -> None:
    reordered = commit_revision(BASE_DRAFT, tuple(reversed(BASE_ASSETS)))
    assert reordered == commit_revision(BASE_DRAFT, BASE_ASSETS)


def test_whitespace_only_difference_does_not_change_revision_id() -> None:
    """保存前去除首尾空白：仅空白差异的草稿得到同一修订。"""
    padded = draft_with(
        project=dataclasses.replace(BASE_DRAFT.project, name="  示例工程  "),
        sheets=(SheetInput(title="\t首层平面图 "),),
    )
    assert commit_revision(padded, BASE_ASSETS) == commit_revision(BASE_DRAFT, BASE_ASSETS)


def test_revision_assets_are_posix_relative_paths_with_role_and_hash() -> None:
    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    by_role = {asset.role: asset for asset in revision.assets}
    assert set(by_role) == {AssetRole.BASE, AssetRole.LAYOUT}
    assert all("\\" not in asset.relative_path for asset in revision.assets)
    assert all(len(asset.sha256) == 64 for asset in revision.assets)


# ---------------------------------------------------------------------------
# create_plan：确定性计划
# ---------------------------------------------------------------------------


def test_plan_id_matches_spec_derivation_and_is_deterministic() -> None:
    from dst_builder.domain.normalization import plan_id_from_sha256

    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    plan = create_plan(revision)
    assert plan.plan_id == plan_id_from_sha256(plan.plan_sha256)
    assert plan.revision_id == revision.revision_id
    assert plan.revision_sha256 == revision.revision_sha256
    assert create_plan(revision) == plan


def test_revision_change_changes_plan_id() -> None:
    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    changed = commit_revision(
        draft_with(sheets=(SheetInput(title="二层平面图"),)), BASE_ASSETS
    )
    assert create_plan(revision).plan_id != create_plan(changed).plan_id


def test_expected_artifacts_list_full_deliverable_set() -> None:
    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    plan = create_plan(revision)
    paths = [artifact.path for artifact in plan.expected_artifacts]
    assert paths == sorted(paths)
    assert set(paths) == {
        "drawings/sheetset.dst",
        "drawings/A-001 首层平面图.dwg",
        "drawings/图纸目录.xlsx",
        "metadata/project-revision.json",
        "metadata/generation-plan.json",
        "metadata/validation-report.json",
        "metadata/handoff.json",
    }
    assert all(artifact.required for artifact in plan.expected_artifacts)


def test_plan_tasks_follow_spec_derived_values() -> None:
    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    plan = create_plan(revision)
    number = sheet_number("A-", 1, 3)
    expected_layout = layout_name(number, "首层平面图")
    expected_dwg = dwg_name(expected_layout)

    assert plan.worker_command == "DSTBUILDER_CREATE_DRAWING"
    assert plan.drawing_task.task_id == task_id_from_revision_sha256(
        revision.revision_sha256, "drawing"
    )
    assert plan.drawing_task.base_asset.role is AssetRole.BASE
    assert plan.drawing_task.layout_asset.role is AssetRole.LAYOUT
    assert plan.drawing_task.source_layout == "A1"
    assert plan.drawing_task.target_layout == expected_layout
    assert plan.drawing_task.target_dwg_path == f"drawings/{expected_dwg}"

    assert plan.sheetset_task.dst_path == "drawings/sheetset.dst"
    assert plan.sheetset_task.sheetset_name == "示例工程"
    assert plan.sheetset_task.subset_name == "建筑"
    assert plan.sheetset_task.sheet_number == number
    assert plan.sheetset_task.sheet_title == "首层平面图"
    assert plan.sheetset_task.dwg_path == expected_dwg
    assert plan.sheetset_task.layout_name == expected_layout


# ---------------------------------------------------------------------------
# check_plan_stale：修订漂移使确认失效（§5/§11 PLAN_STALE）
# ---------------------------------------------------------------------------


def test_matching_revision_is_not_stale() -> None:
    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    assert check_plan_stale(create_plan(revision), revision) == ()


def test_changed_business_field_makes_plan_stale() -> None:
    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    plan = create_plan(revision)
    drifted = commit_revision(
        draft_with(sheets=(SheetInput(title="二层平面图"),)), BASE_ASSETS
    )
    diagnostics = check_plan_stale(plan, drifted)
    assert codes(diagnostics) == {PLAN_STALE}
    assert all(item.severity is DiagnosticSeverity.BLOCKING for item in diagnostics)


def test_output_path_only_change_does_not_make_plan_stale() -> None:
    revision = commit_revision(BASE_DRAFT, BASE_ASSETS)
    plan = create_plan(revision)
    moved = commit_revision(
        draft_with(
            project=dataclasses.replace(
                BASE_DRAFT.project, output_path="E:/other-place/package"
            )
        ),
        BASE_ASSETS,
    )
    assert check_plan_stale(plan, moved) == ()
