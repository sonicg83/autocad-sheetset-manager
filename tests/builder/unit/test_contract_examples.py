"""SPEC-DB-001 契约示例固化为测试夹具（PLAN-DB-001 Task 2）。

把 §4 草稿示例、§9 正式成果目录结构、§6 BuildEventV1 字段固化为契约夹具：
实现漂移破坏示例形状时先在这里变红。示例中的 ``<uuid>`` 占位替换为固定 UUID
字面量，其余字段与规范逐字一致。
"""

from dst_builder.domain.models import (
    AssetRole,
    AssetSnapshot,
    BuildStatus,
    DraftProjectV1,
    NumberingInput,
    ProjectInput,
    SheetInput,
    TemplateInput,
)
from dst_builder.domain.normalization import (
    dwg_name,
    layout_name,
    sheet_number,
)
from dst_builder.domain.planning import commit_revision, create_plan, validate_draft

# SPEC §4 草稿输入契约示例（output_path 为本机发布位置，不入修订/计划哈希）。
SPEC_DRAFT_EXAMPLE = {
    "schema_version": 1,
    "project": {
        "name": "示例工程",
        "stage": "施工图",
        "discipline": "建筑",
        "output_path": "D:/deliveries/example-package",
    },
    "numbering": {"prefix": "A-", "start": 1, "width": 3},
    "cad_version": "2020",
    "sheets": [{"title": "首层平面图"}],
    "template": {
        "base_asset_id": "3f6b5a24-6a8e-4c2a-9c8f-0f5d7a1b2c31",
        "layout_asset_id": "8c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
        "source_layout": "A1",
    },
}

SPEC_ASSETS_EXAMPLE = (
    AssetSnapshot(
        role=AssetRole.BASE,
        relative_path="assets/base/1111111111111111111111111111111111111111111111111111111111111111.dwg",
        sha256="1" * 64,
        size=1024,
    ),
    AssetSnapshot(
        role=AssetRole.LAYOUT,
        relative_path="assets/layout/2222222222222222222222222222222222222222222222222222222222222222.dwt",
        sha256="2" * 64,
        size=2048,
    ),
)


def draft_from_spec_example() -> DraftProjectV1:
    project = SPEC_DRAFT_EXAMPLE["project"]
    numbering = SPEC_DRAFT_EXAMPLE["numbering"]
    template = SPEC_DRAFT_EXAMPLE["template"]
    return DraftProjectV1(
        project=ProjectInput(
            name=project["name"],
            stage=project["stage"],
            discipline=project["discipline"],
            output_path=project["output_path"],
        ),
        numbering=NumberingInput(
            prefix=numbering["prefix"], start=numbering["start"], width=numbering["width"]
        ),
        cad_version=SPEC_DRAFT_EXAMPLE["cad_version"],
        sheets=tuple(SheetInput(title=sheet["title"]) for sheet in SPEC_DRAFT_EXAMPLE["sheets"]),
        template=TemplateInput(
            base_asset_id=template["base_asset_id"],
            layout_asset_id=template["layout_asset_id"],
            source_layout=template["source_layout"],
        ),
        schema_version=SPEC_DRAFT_EXAMPLE["schema_version"],
    )


def test_spec_draft_example_validates_clean() -> None:
    draft = draft_from_spec_example()
    assert draft.schema_version == 1
    assert validate_draft(draft, output_exists=False) == ()


def test_spec_draft_example_derived_values() -> None:
    """§4 派生值公式逐项对照。"""
    number = sheet_number("A-", 1, 3)
    assert number == "A-001"
    assert layout_name(number, "首层平面图") == "A-001 首层平面图"
    assert dwg_name("A-001 首层平面图") == "A-001 首层平面图.dwg"


def test_expected_artifacts_match_assembled_files() -> None:
    """§9：正式成果目标目录直接包含三件套，预期产物与装配键集逐项一致。"""
    revision = commit_revision(draft_from_spec_example(), SPEC_ASSETS_EXAMPLE)
    plan = create_plan(revision)

    assert {artifact.path for artifact in plan.expected_artifacts} == {
        "sheetset.dst",
        "A-001 首层平面图.dwg",
        "图纸目录.xlsx",
    }


def test_build_event_v1_contract_fields() -> None:
    """§6 BuildEventV1：schema_version、单调 sequence、status、progress、message_key、
    可选 artifact_path/error_code/created_at。"""
    from dst_builder.domain.models import BuildEventV1

    event = BuildEventV1(
        schema_version=1,
        sequence=7,
        status=BuildStatus.VERIFYING,
        progress=80,
        message_key="build.verifying",
    )
    assert event.error_code is None
    assert event.artifact_path is None
    assert event.created_at is None
