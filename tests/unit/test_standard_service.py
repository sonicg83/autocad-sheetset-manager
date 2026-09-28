"""标准应用服务：草稿/发布编排、绑定解析与项目快照恢复（PLAN-DM-035 Task 4）。"""

import json
import shutil
from pathlib import Path

import pytest

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.infrastructure.acsm_xml import AcsmDocument, AcsmValidationError
from dst_manager.infrastructure.dst_codec import DstCodec


def draft_document(document: dict) -> dict:
    """返回 schema v3 草稿文档。"""
    result = dict(document)
    result["published_at"] = None
    result.pop("version", None)
    return result


GAS_DOCUMENT = {
    "schema_version": 3,
    "standard_id": "00000000-0000-4000-8000-000000000046",
    "published_at": 1_700_000_000_000,
    "description": "",
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
    store.create_draft(
        draft_document(GAS_DOCUMENT),
        draft_id="draft-gas",
    )
    store.publish("draft-gas")
    return store


def bind_standard_file(dst_path: Path, identity: str) -> None:
    """在 DST 文件上直接写入标准绑定保留属性（测试夹具辅助）。"""
    document = AcsmDocument(DstCodec().decode_file(dst_path))
    if "@" in identity:
        # 仅此分支模拟旧版 DST 中已经存在的只读绑定。
        document._ensure_reserved_property_definitions()
        sheet_set = document.root.xpath("//*[local-name()='AcSmSheetSet']")[0]
        document._set_custom_properties(
            sheet_set,
            {"DSTManager.Standard": identity},
            expected_scope="1",
            allow_reserved=True,
        )
    else:
        document.apply_metadata_commands([{"type": "bind_standard", "standard": identity}])
    DstCodec().encode_file(document.to_bytes(), dst_path)


def test_resolve_restores_project_snapshot_from_user_library(
    service: DstManagerService, workspace, standard_store
) -> None:
    bind_standard_file(workspace.dst_path, "00000000-0000-4000-8000-000000000046")
    resolution = service.resolve_workspace_standard(workspace.id)
    assert resolution.status == "resolved"
    assert resolution.source == "user-library"
    assert (workspace.root / ".dst-manager/standards/00000000-0000-4000-8000-000000000046").is_dir()
    # 再次解析直接命中项目快照，不再回源。
    again = service.resolve_workspace_standard(workspace.id)
    assert again.source == "project-snapshot"

    # 用户库包移除后，已创建工程仍从自己的 UUID 快照只读打开。
    shutil.rmtree(standard_store.published_root / "00000000-0000-4000-8000-000000000046")
    opened = service.open_workspace(workspace.dst_path)
    assert opened.standard.status == "resolved"
    assert opened.standard.source == "project-snapshot"


def test_legacy_versioned_binding_reads_snapshot_without_writes(
    service: DstManagerService, workspace
) -> None:
    standard_id = "legacy.gas"
    bind_standard_file(workspace.dst_path, f"{standard_id}@1")
    snapshot = workspace.root / ".dst-manager" / "standards" / standard_id / "1"
    snapshot.mkdir(parents=True)
    legacy_document = dict(GAS_DOCUMENT)
    legacy_document.update({"schema_version": 2, "standard_id": standard_id, "version": 1})
    legacy_document.pop("published_at")
    legacy_document.pop("description")
    legacy_document["release_notes"] = "旧版说明"
    (snapshot / "document.json").write_text(
        json.dumps(legacy_document, ensure_ascii=False), encoding="utf-8"
    )
    snapshot_bytes = (snapshot / "document.json").read_bytes()
    snapshot_mtime = (snapshot / "document.json").stat().st_mtime_ns
    dst_bytes = workspace.dst_path.read_bytes()
    dst_mtime = workspace.dst_path.stat().st_mtime_ns
    dwg_path = workspace.root / "legacy-unmodified.dwg"
    dwg_path.write_bytes(b"legacy DWG fixture")
    dwg_bytes = dwg_path.read_bytes()
    dwg_mtime = dwg_path.stat().st_mtime_ns

    opened = service.open_workspace(workspace.dst_path)

    assert opened.standard.status == "resolved"
    assert opened.standard.source == "project-snapshot"
    assert opened.standard.standard_id == standard_id
    assert opened.standard.standard is not None
    assert opened.standard.standard.version == 1
    assert opened.standard.standard.description == "旧版说明"
    assert opened.standard.standard.published_at is None
    assert (snapshot / "document.json").read_bytes() == snapshot_bytes
    assert (snapshot / "document.json").stat().st_mtime_ns == snapshot_mtime
    assert workspace.dst_path.read_bytes() == dst_bytes
    assert workspace.dst_path.stat().st_mtime_ns == dst_mtime
    assert dwg_path.read_bytes() == dwg_bytes
    assert dwg_path.stat().st_mtime_ns == dwg_mtime


def test_missing_standard_does_not_block_workspace_open(
    service: DstManagerService, workspace
) -> None:
    bind_standard_file(workspace.dst_path, "missing@1")
    original_bytes = workspace.dst_path.read_bytes()
    original_mtime = workspace.dst_path.stat().st_mtime_ns
    opened = service.open_workspace(workspace.dst_path)
    assert opened.standard.status == "missing"
    assert opened.standard.standard_id == "missing"
    assert any(item.code == "STANDARD_MISSING" for item in opened.document.diagnostics)
    # 打开动作本身不创建项目快照。
    assert not (opened.root / ".dst-manager/standards/missing/1").exists()
    assert workspace.dst_path.read_bytes() == original_bytes
    assert workspace.dst_path.stat().st_mtime_ns == original_mtime


def test_unbound_workspace_resolves_to_unbound(
    service: DstManagerService, workspace
) -> None:
    resolution = service.resolve_workspace_standard(workspace.id)
    assert resolution.status == "unbound"


def test_bind_workspace_standard_writes_reserved_property(
    service: DstManagerService, workspace
) -> None:
    result = service.bind_workspace_standard(
        workspace.id, "00000000-0000-4000-8000-000000000046", workspace.revision_id
    )
    assert result["status"] == "bound"
    reopened = service.open_workspace(workspace.dst_path)
    assert reopened.document.custom_properties["DSTManager.Standard"] == "00000000-0000-4000-8000-000000000046"
    assert reopened.standard.standard_id == "00000000-0000-4000-8000-000000000046"


@pytest.mark.parametrize(
    "identity",
    [
        "not-an-identity",
        "00000000-0000-4000-8000-000000000046@0",
        "00000000-0000-4000-8000-000000000046@01",
        "00000000-0000-4000-8000-000000000046@1.0.0",
        "00000000-0000-4000-8000-000000000046@../..",
        "00000000-0000-4000-8000-000000000046@-1",
        "00000000-0000-4000-8000-000000000046@",
        "00000000-0000-4000-8000-000000000046@1 ",
        "../@1",
    ],
)
def test_bind_workspace_standard_rejects_invalid_identity(
    service: DstManagerService, workspace, identity: str
) -> None:
    with pytest.raises(ApplicationError) as exc_info:
        service.bind_workspace_standard(workspace.id, identity, workspace.revision_id)
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
    document.apply_metadata_commands([{"type": "bind_standard", "standard": "00000000-0000-4000-8000-000000000046"}])
    projected = document.project(dst.parent)
    assert projected.custom_properties["DSTManager.Standard"] == "00000000-0000-4000-8000-000000000046"


# ---- 草稿级保存与身份核对（PLAN-DM-040 Task 7，F11） ----------------------


def test_save_draft_accepts_matching_identity(service: DstManagerService) -> None:
    service.create_standard_draft(draft_document(GAS_DOCUMENT), draft_id="draft-gas")
    saved = service.save_standard_draft(
        "draft-gas", dict(draft_document(GAS_DOCUMENT), name="修订名")
    )
    assert saved["draft_id"] == "draft-gas"
    assert saved["document"]["name"] == "修订名"
    assert service.get_standard_draft("draft-gas")["document"]["name"] == "修订名"


@pytest.mark.parametrize("standard_id", ["00000000-0000-4000-8000-000000000050", "00000000-0000-4000-8000-000000000051"])
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
    assert stored["standard_id"] == "00000000-0000-4000-8000-000000000046"
    assert "version" not in stored


def test_save_draft_rejects_carried_version(service: DstManagerService) -> None:
    """草稿不得携带正式版本：携带时以稳定 422 拒绝，不改写已存草稿。"""
    service.create_standard_draft(draft_document(GAS_DOCUMENT), draft_id="draft-gas")
    with pytest.raises(ApplicationError) as exc_info:
        service.save_standard_draft("draft-gas", dict(GAS_DOCUMENT, version=9))
    assert exc_info.value.code == "STANDARD_VERSION_INVALID"
    assert "version" not in service.get_standard_draft("draft-gas")["document"]
