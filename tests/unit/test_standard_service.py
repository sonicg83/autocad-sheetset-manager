"""标准应用服务：草稿/发布编排、绑定解析与项目快照恢复（PLAN-DM-035 Task 4）。"""

from pathlib import Path

import pytest

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.acsm_xml import AcsmDocument, AcsmValidationError
from dst_manager.infrastructure.dst_codec import DstCodec

def draft_document(document: dict) -> dict:
    """草稿不携带正式版本（PLAN-DM-041）：去 version 的文档副本。"""
    return {key: value for key, value in document.items() if key != "version"}


GAS_DOCUMENT = {
    "schema_version": 2,
    "standard_id": "szmedi.gas",
    "version": 1,
    "name": "市政燃气施工图",
    "supported_cad_versions": ["2016", "2020"],
    "properties": [
        {
            "property_id": "prop-major",
            "name": "专业",
            "scope": "sheetset",
            "kind": "enum",
            "required": True,
            "enum_items": [{"item_id": "enum-gas", "value": "燃气"}],
        }
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


@pytest.fixture
def service(tmp_path: Path) -> DstManagerService:
    return DstManagerService(Settings(data_dir=tmp_path / "data"))


@pytest.fixture
def workspace(service: DstManagerService, tiny_workspace):
    dst, _sheet_id = tiny_workspace
    return service.open_workspace(dst)


@pytest.fixture
def standard_store(service: DstManagerService):
    store = service.standard_store
    # 草稿不携带版本（PLAN-DM-041 Task 2）：发布版本文档去掉 version 后入库为草稿。
    store.create_draft(
        {key: value for key, value in GAS_DOCUMENT.items() if key != "version"},
        draft_id="draft-gas",
    )
    store.publish("draft-gas")
    return store


def bind_standard_file(dst_path: Path, identity: str) -> None:
    """在 DST 文件上直接写入标准绑定保留属性（测试夹具辅助）。"""
    document = AcsmDocument(DstCodec().decode_file(dst_path))
    document.apply_metadata_commands([{"type": "bind_standard", "standard": identity}])
    DstCodec().encode_file(document.to_bytes(), dst_path)


def test_resolve_restores_project_snapshot_from_user_library(
    service: DstManagerService, workspace, standard_store
) -> None:
    bind_standard_file(workspace.dst_path, "szmedi.gas@1")
    resolution = service.resolve_workspace_standard(workspace.id)
    assert resolution.status == "resolved"
    assert resolution.source == "user-library"
    assert (workspace.root / ".dst-manager/standards/szmedi.gas/1").is_dir()
    # 再次解析直接命中项目快照，不再回源。
    again = service.resolve_workspace_standard(workspace.id)
    assert again.source == "project-snapshot"


def test_missing_standard_does_not_block_workspace_open(
    service: DstManagerService, workspace
) -> None:
    bind_standard_file(workspace.dst_path, "missing@1")
    opened = service.open_workspace(workspace.dst_path)
    assert opened.standard.status == "missing"
    assert opened.standard.standard_id == "missing"
    assert any(item.code == "STANDARD_MISSING" for item in opened.document.diagnostics)
    # 打开动作本身不创建项目快照。
    assert not (opened.root / ".dst-manager/standards/missing/1").exists()


def test_unbound_workspace_resolves_to_unbound(
    service: DstManagerService, workspace
) -> None:
    resolution = service.resolve_workspace_standard(workspace.id)
    assert resolution.status == "unbound"


def test_bind_workspace_standard_writes_reserved_property(
    service: DstManagerService, workspace
) -> None:
    result = service.bind_workspace_standard(
        workspace.id, "szmedi.gas@1", workspace.revision_id
    )
    assert result["status"] == "bound"
    reopened = service.open_workspace(workspace.dst_path)
    assert reopened.document.custom_properties["DSTManager.Standard"] == "szmedi.gas@1"
    assert reopened.standard.standard_id == "szmedi.gas"
    assert reopened.standard.version == "1"


def test_bind_workspace_standard_rejects_invalid_identity(
    service: DstManagerService, workspace
) -> None:
    with pytest.raises(ApplicationError) as exc_info:
        service.bind_workspace_standard(workspace.id, "not-an-identity", workspace.revision_id)
    assert exc_info.value.code == "STANDARD_IDENTITY_INVALID"


def test_update_sheet_set_rejects_reserved_property(
    service: DstManagerService, workspace
) -> None:
    with pytest.raises(ApplicationError) as exc_info:
        service.preview_changes(
            workspace.id,
            workspace.revision_id,
            [{"type": "update_sheet_set", "custom_properties": {"DSTManager.Standard": "evil@1.0.0"}}],
        )
    assert exc_info.value.code == "STANDARD_PROPERTY_RESERVED"


def test_delete_property_definition_rejects_reserved_name(
    service: DstManagerService, workspace
) -> None:
    with pytest.raises(ApplicationError) as exc_info:
        service.preview_changes(
            workspace.id,
            workspace.revision_id,
            [{"type": "delete_custom_property", "property_type": "sheetset", "name": "DSTManager.StandardOptions"}],
        )
    assert exc_info.value.code == "STANDARD_PROPERTY_RESERVED"


def test_dom_update_sheet_set_rejects_reserved_property(tiny_workspace) -> None:
    dst, _sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    with pytest.raises(AcsmValidationError, match="STANDARD_PROPERTY_RESERVED"):
        document.apply_metadata_commands(
            [{"type": "update_sheet_set", "custom_properties": {"DSTManager.Standard": "x@1.0.0"}}]
        )


def test_dom_bind_standard_command_writes_reserved_property(tiny_workspace) -> None:
    dst, _sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    document.apply_metadata_commands([{"type": "bind_standard", "standard": "szmedi.gas@2.1.0"}])
    projected = document.project(dst.parent)
    assert projected.custom_properties["DSTManager.Standard"] == "szmedi.gas@2.1.0"


# ---- 草稿级保存与身份核对（PLAN-DM-040 Task 7，F11） ----------------------


def test_save_draft_accepts_matching_identity(service: DstManagerService) -> None:
    service.create_standard_draft(draft_document(GAS_DOCUMENT), draft_id="draft-gas")
    saved = service.save_standard_draft(
        "draft-gas", dict(draft_document(GAS_DOCUMENT), name="修订名")
    )
    assert saved["draft_id"] == "draft-gas"
    assert saved["document"]["name"] == "修订名"
    assert service.get_standard_draft("draft-gas")["document"]["name"] == "修订名"


@pytest.mark.parametrize("standard_id", ["szmedi.water", "szmedi.other"])
def test_save_draft_rejects_identity_mismatch(
    service: DstManagerService, standard_id: str
) -> None:
    service.create_standard_draft(draft_document(GAS_DOCUMENT), draft_id="draft-gas")
    changed = dict(draft_document(GAS_DOCUMENT), standard_id=standard_id)
    with pytest.raises(ApplicationError) as exc_info:
        service.save_standard_draft("draft-gas", changed)
    assert exc_info.value.code == "STANDARD_IDENTITY_MISMATCH"
    # 不静默改写：草稿保持原身份与原内容
    stored = service.get_standard_draft("draft-gas")["document"]
    assert stored["standard_id"] == "szmedi.gas"
    assert "version" not in stored


def test_save_draft_rejects_carried_version(service: DstManagerService) -> None:
    """草稿不得携带正式版本：携带时以稳定 422 拒绝，不改写已存草稿。"""
    service.create_standard_draft(draft_document(GAS_DOCUMENT), draft_id="draft-gas")
    with pytest.raises(ApplicationError) as exc_info:
        service.save_standard_draft("draft-gas", dict(GAS_DOCUMENT, version=9))
    assert exc_info.value.code == "STANDARD_VERSION_INVALID"
    assert "version" not in service.get_standard_draft("draft-gas")["document"]
