"""按图纸组保存的可恢复创建草稿：领域类型与原子 JSON 持久化（PLAN-DM-036 Task 1）。

覆盖：标准身份固定、乐观修订冲突、显式空串与遗漏键的区别、每次组变更递增修订、
损坏 JSON 隔离、标准版本缺失、草稿不保存可执行预览、拒绝派生/越权/重复身份输入。
"""

import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.domain.creation import CreationGroupInput

# 最小可发布标准：两个普通 sheetset 属性（文本带默认值、枚举无默认值）、一个派生
# 映射属性（不得进入草稿输入）与一个普通 sheet 属性。
STANDARD_DOCUMENT = {
    "schema_version": 2,
    "standard_id": "szmedi.gas",
    "version": 1,
    "name": "市政燃气施工图",
    "supported_cad_versions": ["2016", "2020"],
    "properties": [
        {
            "property_id": "prop-name",
            "name": "工程名称",
            "scope": "sheetset",
            "kind": "text",
            "required": True,
            "default_value": "默认工程",
        },
        {
            "property_id": "prop-major",
            "name": "专业",
            "scope": "sheetset",
            "kind": "enum",
            "required": True,
            "enum_items": [{"item_id": "enum-gas", "value": "燃气"}],
        },
        {
            "property_id": "prop-code",
            "name": "专业代码",
            "scope": "sheetset",
            "kind": "mapping",
            "source_property_id": "prop-major",
            "mapping": [{"item_id": "enum-gas", "value": "RQ"}],
            "confirmed_source_items": [["enum-gas", "燃气"]],
        },
        {
            "property_id": "prop-stage",
            "name": "设计阶段",
            "scope": "sheet",
            "kind": "text",
            "default_value": "施工图",
        },
    ],
    "dwg_naming": {
        "segments": [
            {"system_field": "subset.scope"},
            {"literal": " "},
            {"system_field": "subset.name"},
        ]
    },
    "assets": [],
    "numbering": {"sequence_field": "subset.sequence", "digits": 2},
}

DRAFT_DOCUMENT_KEYS = {
    "schema_version",
    "id",
    "standard_id",
    "standard_version",
    "revision",
    "step",
    "target_path",
    "sheetset_values",
    "groups",
}
GROUP_DOCUMENT_KEYS = {
    "group_id",
    "created_order",
    "title",
    "count",
    "base_asset_id",
    "layout_asset_id",
    "paper_layout",
    "sheet_values",
}


@dataclass(frozen=True, slots=True)
class PublishedStandardFixture:
    """已发布标准夹具：稳定身份 + 原始文档。"""

    identity: tuple[str, str]
    document: dict[str, object]


@pytest.fixture
def service(tmp_path: Path) -> DstManagerService:
    return DstManagerService(Settings(data_dir=tmp_path / "data"))


@pytest.fixture
def published_standard(service: DstManagerService) -> PublishedStandardFixture:
    store = service.standard_store
    # 草稿不携带版本（PLAN-DM-041 Task 2）。
    store.create_draft(
        {key: value for key, value in STANDARD_DOCUMENT.items() if key != "version"},
        draft_id="draft-gas",
    )
    published = store.publish("draft-gas")
    return PublishedStandardFixture(
        identity=(published.standard_id, published.version),
        document=STANDARD_DOCUMENT,
    )


@pytest.fixture
def draft(service: DstManagerService, published_standard: PublishedStandardFixture):
    return service.create_creation_draft(published_standard.identity)


def draft_document_path(service: DstManagerService, draft_id: str) -> Path:
    """草稿根布局契约：``<data_dir>/creation-drafts/<uuid>/draft.json``。"""
    return service.settings.data_dir / "creation-drafts" / draft_id / "draft.json"


def group(group_id: str, created_order: int, **overrides: object) -> CreationGroupInput:
    values: dict[str, object] = {
        "title": f"图名{created_order}",
        "count": 1,
        "base_asset_id": "base-a1",
        "layout_asset_id": "layout-a1",
        "paper_layout": "A1",
        "sheet_values": {},
    }
    values.update(overrides)
    return CreationGroupInput(group_id=group_id, created_order=created_order, **values)  # type: ignore[arg-type]


# ---- Step 1：标准固定与崩溃恢复 ------------------------------------------


def test_creation_draft_pins_published_standard(tmp_path, service, published_standard) -> None:
    draft = service.create_creation_draft(published_standard.identity)
    restored = service.get_creation_draft(draft.id)
    assert (restored.standard_id, restored.standard_version) == published_standard.identity
    assert restored.revision == 1
    assert restored.target_path == ""
    assert restored.groups == ()


def test_save_uses_optimistic_revision(service, draft) -> None:
    service.save_creation_draft(draft.id, expected_revision=1, value=draft)
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_CONFLICT"):
        service.save_creation_draft(draft.id, expected_revision=1, value=draft)


def test_explicitly_cleared_value_survives_restore(service, draft) -> None:
    value = replace(draft, sheetset_values={**draft.sheetset_values, "prop-name": ""})
    saved = service.save_creation_draft(draft.id, expected_revision=1, value=value)
    assert service.get_creation_draft(draft.id).sheetset_values["prop-name"] == ""
    assert saved.revision == 2


# ---- Step 4：初值只应用一次、空串与遗漏键、修订递增 ----------------------


def test_creation_applies_ordinary_defaults_once(service, draft) -> None:
    # 初建只对普通属性应用一次默认值；派生属性不进入输入。
    assert draft.sheetset_values == {"prop-name": "默认工程", "prop-major": ""}
    # 标准已在建草稿前选定，初建即停在第二阶段（SPEC-DM-018 §2.2）。
    assert draft.step == "project"
    cleared = replace(draft, sheetset_values={**draft.sheetset_values, "prop-major": ""})
    saved = service.save_creation_draft(draft.id, expected_revision=1, value=cleared)
    assert service.get_creation_draft(saved.id).sheetset_values == {
        "prop-name": "默认工程",
        "prop-major": "",
    }


def test_missing_key_and_explicit_empty_string_stay_distinct(service, draft) -> None:
    explicit = group("group-1", 1, sheet_values={"prop-stage": ""})
    omitted = group("group-2", 2, sheet_values={})
    value = replace(draft, groups=(explicit, omitted))
    saved = service.save_creation_draft(draft.id, expected_revision=1, value=value)
    restored = service.get_creation_draft(saved.id)
    assert restored.groups[0].sheet_values == {"prop-stage": ""}
    assert restored.groups[1].sheet_values == {}


def test_every_group_change_increments_revision(service, draft) -> None:
    first = group("group-1", 1, sheet_values={"prop-stage": "施工图"})
    second = group("group-2", 2, title="剖面图", count=3)

    value = service.save_creation_draft(draft.id, expected_revision=1, value=replace(draft, groups=(first,)))
    assert value.revision == 2  # 新增组
    value = service.save_creation_draft(
        draft.id, expected_revision=value.revision, value=replace(value, groups=(first, second))
    )
    assert value.revision == 3  # 新增组
    value = service.save_creation_draft(
        draft.id, expected_revision=value.revision, value=replace(value, groups=(second, first))
    )
    assert value.revision == 4  # 排序
    reordered = service.get_creation_draft(draft.id)
    assert [item.group_id for item in reordered.groups] == ["group-2", "group-1"]
    # 重排只改数组顺序，created_order 保持创建时的单调值。
    assert [item.created_order for item in reordered.groups] == [2, 1]
    value = service.save_creation_draft(
        draft.id,
        expected_revision=value.revision,
        value=replace(value, groups=(replace(second, title="剖面图（改）"), first)),
    )
    assert value.revision == 5  # 字段修改
    value = service.save_creation_draft(
        draft.id, expected_revision=value.revision, value=replace(value, groups=(replace(second, title="剖面图（改）"),))
    )
    assert value.revision == 6  # 删除组


def test_restored_draft_carries_no_preview_state(service, draft) -> None:
    value = replace(draft, step="groups", target_path="C:/projects/新建项目")
    saved = service.save_creation_draft(draft.id, expected_revision=1, value=value)
    document = json.loads(draft_document_path(service, draft.id).read_text(encoding="utf-8"))
    assert set(document) == DRAFT_DOCUMENT_KEYS
    assert document["schema_version"] == 1
    assert document["revision"] == 2
    assert document["step"] == "groups"
    assert document["target_path"] == "C:/projects/新建项目"
    restored = service.get_creation_draft(saved.id)
    assert restored.revision == 2
    assert not hasattr(restored, "preview")


def test_creation_draft_survives_service_restart(tmp_path, service, draft) -> None:
    saved = service.save_creation_draft(
        draft.id, expected_revision=1, value=replace(draft, groups=(group("group-1", 1),))
    )
    restarted = DstManagerService(Settings(data_dir=tmp_path / "data"))
    restored = restarted.get_creation_draft(saved.id)
    assert restored == saved
    assert restored.groups[0].group_id == "group-1"


# ---- Step 4：损坏隔离、标准缺失与输入拒绝 --------------------------------


def test_corrupt_draft_json_is_quarantined(service, draft) -> None:
    path = draft_document_path(service, draft.id)
    path.write_text("{ 不是 JSON", encoding="utf-8")
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_CORRUPT"):
        service.get_creation_draft(draft.id)
    assert not path.exists()
    quarantined = sorted(path.parent.parent.glob(f"{draft.id}.corrupt-*.json"))
    assert len(quarantined) == 1
    assert "不是 JSON" in quarantined[0].read_text(encoding="utf-8")
    # 隔离后草稿不再可用，重复读取按缺失处理；「重新开始」仍能清掉残留目录。
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_NOT_FOUND"):
        service.get_creation_draft(draft.id)
    service.delete_creation_draft(draft.id)
    assert not path.parent.exists()


def test_draft_document_with_unknown_field_is_quarantined(service, draft) -> None:
    path = draft_document_path(service, draft.id)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["preview"] = {"digest": "stale"}
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_CORRUPT"):
        service.get_creation_draft(draft.id)


def test_missing_published_standard_version_reports_standard_missing(
    service, published_standard
) -> None:
    draft = service.create_creation_draft(published_standard.identity)
    standard_id, version = published_standard.identity
    shutil.rmtree(service.standard_store.published_root / standard_id / version)
    with pytest.raises(ApplicationError, match="CREATION_STANDARD_MISSING"):
        service.get_creation_draft(draft.id)
    with pytest.raises(ApplicationError, match="CREATION_STANDARD_MISSING"):
        service.save_creation_draft(draft.id, expected_revision=1, value=draft)


def test_standard_draft_is_not_usable_for_creation(service) -> None:
    service.standard_store.create_draft(
        {key: value for key, value in STANDARD_DOCUMENT.items() if key != "version"},
        draft_id="draft-gas",
    )
    with pytest.raises(ApplicationError, match="CREATION_STANDARD_MISSING"):
        service.create_creation_draft(("szmedi.gas", "2.1.0"))
    with pytest.raises(ApplicationError, match="CREATION_STANDARD_MISSING"):
        service.create_creation_draft(("szmedi.gas", "9.9.9"))


def test_save_rejects_derived_and_out_of_scope_values(service, draft) -> None:
    derived = replace(draft, sheetset_values={**draft.sheetset_values, "prop-code": "RQ"})
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_INVALID"):
        service.save_creation_draft(draft.id, expected_revision=1, value=derived)
    wrong_scope = replace(draft, groups=(group("group-1", 1, sheet_values={"prop-name": "越权"}),))
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_INVALID"):
        service.save_creation_draft(draft.id, expected_revision=1, value=wrong_scope)
    unknown = replace(draft, groups=(group("group-1", 1, sheet_values={"prop-unknown": ""}),))
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_INVALID"):
        service.save_creation_draft(draft.id, expected_revision=1, value=unknown)
    # 拒绝不改变磁盘内容与修订号。
    assert service.get_creation_draft(draft.id) == draft


def test_save_rejects_duplicate_group_identity(service, draft) -> None:
    duplicated_id = replace(draft, groups=(group("group-1", 1), group("group-1", 2)))
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_INVALID"):
        service.save_creation_draft(draft.id, expected_revision=1, value=duplicated_id)
    duplicated_order = replace(draft, groups=(group("group-1", 1), group("group-2", 1)))
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_INVALID"):
        service.save_creation_draft(draft.id, expected_revision=1, value=duplicated_order)


def test_save_rejects_pinned_standard_change(service, draft) -> None:
    changed = replace(draft, standard_version="9.9.9")
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_INVALID"):
        service.save_creation_draft(draft.id, expected_revision=1, value=changed)
    renamed = replace(draft, id="other-draft")
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_INVALID"):
        service.save_creation_draft(draft.id, expected_revision=1, value=renamed)


def test_save_rejects_unknown_step(service, draft) -> None:
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_INVALID"):
        service.save_creation_draft(draft.id, expected_revision=1, value=replace(draft, step="export"))


def test_delete_creation_draft_removes_storage(service, draft) -> None:
    directory = draft_document_path(service, draft.id).parent
    assert directory.is_dir()
    service.delete_creation_draft(draft.id)
    assert not directory.exists()
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_NOT_FOUND"):
        service.get_creation_draft(draft.id)
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_NOT_FOUND"):
        service.delete_creation_draft(draft.id)
