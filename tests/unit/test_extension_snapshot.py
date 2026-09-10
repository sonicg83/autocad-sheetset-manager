"""PLAN-DM-020 Task 4：裁剪的冻结工作区快照与 Capability Broker。

覆盖：属性定义/值合并与 casefold() 规范化、两作用域、跨 Windows/Posix
分隔符 basename、顺序、冻结不可变与可序列化、无路径泄漏；能力上下文的
清单声明 ∩ 宿主 allowlist 校验、修订绑定与 close() 后失效。
"""

import json
from dataclasses import FrozenInstanceError, asdict

import pytest

from dst_manager.domain.models import (
    LayoutReference,
    Sheet,
    SheetSetDocument,
    Subset,
)
from dst_manager.extensions.capabilities import (
    WORKSPACE_SNAPSHOT_CAPABILITY,
    CapabilityBroker,
    CapabilityError,
)
from dst_manager.extensions.manifest import load_manifest
from dst_manager.extensions.snapshots import (
    SnapshotProperty,
    build_field_catalog,
    build_workspace_snapshot,
)
from dst_manager.infrastructure.extension_workspace import (
    DecodedWorkspace,
    ExtensionWorkspaceReadError,
)

SHEET_CATALOG_ID = "dst-manager.sheet-catalog"
SHEET_CATALOG_MANIFEST = "dst_manager/extensions/builtin/sheet_catalog/manifest.yaml"


# ---------------------------------------------------------------------------
# 快照构造：属性合并、规范化、basename、两作用域、顺序
# ---------------------------------------------------------------------------


def make_document() -> SheetSetDocument:
    """构造覆盖全部裁剪场景的最小文档（不依赖 DST 文件）。"""
    first = Sheet(
        "sheet-1",
        "001",
        "平面",
        LayoutReference(r"C:\工程\A.dwg", r".\A.dwg", "001 平面", "AB"),
        {"比例": "1:100", "professional": "水"},
    )
    second = Sheet(
        "sheet-2",
        "002",
        "剖面",
        LayoutReference("folder/A.dwg", "folder/A.dwg", "002 剖面", "CD"),
        {"专项": "结构"},
    )
    return SheetSetDocument(
        database_id="db-1",
        name="测试集",
        subsets=[
            Subset("subset-1", "01-02 分组", 0, [first]),
            Subset("subset-2", "空分组", 1, [second]),
        ],
        custom_properties={"项目号": "P-000", "阶段": ""},
        sheet_property_definitions=["PROFESSIONAL", "备注"],
    )


def make_source(document: SheetSetDocument) -> DecodedWorkspace:
    return DecodedWorkspace(workspace_id="ws-1", revision_id="rev-1", document=document)


def test_snapshot_merges_definitions_and_normalizes_canonical_names():
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1",
        revision_id="rev-1",
        document=make_document(),
    )

    # 图纸集作用域：声明即定义（含空值"阶段"），按 casefold 排序
    assert snapshot.sheetset.custom_property_definitions == ("阶段", "项目号")
    assert snapshot.sheetset.custom_properties == (
        SnapshotProperty("阶段", ""),
        SnapshotProperty("项目号", "P-000"),
    )
    # 图纸作用域：声明与实际投影并集，大小写重复绑定到规范名称
    # （"professional" 与声明的 "PROFESSIONAL" 同 key，保留声明侧拼写）
    assert snapshot.sheets[0].custom_property_definitions == (
        "PROFESSIONAL",
        "专项",
        "备注",
        "比例",
    )


def test_snapshot_carries_declared_without_value_and_actual_without_declaration():
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1",
        revision_id="rev-1",
        document=make_document(),
    )

    # 声明但无值："备注" 只出现在定义，不出现在任何图纸属性值
    for sheet in snapshot.sheets:
        assert all(
            prop.canonical_name != "备注" for prop in sheet.custom_properties
        )
    # 实际但未声明："专项" 同时进入定义与值
    assert "专项" in snapshot.sheets[1].custom_property_definitions
    assert SnapshotProperty("专项", "结构") in snapshot.sheets[1].custom_properties


def test_snapshot_binds_sheet_values_to_canonical_names_in_order():
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1",
        revision_id="rev-1",
        document=make_document(),
    )

    assert snapshot.sheets[0].custom_properties == (
        SnapshotProperty("PROFESSIONAL", "水"),
        SnapshotProperty("比例", "1:100"),
    )


def test_snapshot_flattens_sheets_in_subset_then_sheet_order():
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1",
        revision_id="rev-1",
        document=make_document(),
    )

    assert [sheet.sheet_id for sheet in snapshot.sheets] == ["sheet-1", "sheet-2"]
    assert snapshot.sheets[0].number == "001"
    assert snapshot.sheets[0].title == "平面"


def test_snapshot_trims_basename_across_windows_and_posix_separators():
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1",
        revision_id="rev-1",
        document=make_document(),
    )

    assert [sheet.file_name for sheet in snapshot.sheets] == ["A.dwg", "A.dwg"]


def test_snapshot_is_frozen_and_serializable_without_any_paths():
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1",
        revision_id="rev-1",
        document=make_document(),
    )

    with pytest.raises(FrozenInstanceError):
        snapshot.revision_id = "rev-2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snapshot.sheets[0].file_name = "escaped.dwg"  # type: ignore[misc]

    payload = json.dumps(asdict(snapshot), ensure_ascii=False)
    assert payload  # 全部字段可 JSON 序列化
    for leaked in ("root", "dst_path", "resolved_path", "relative"):
        assert leaked not in asdict(snapshot)
    # Windows 与 Posix 目录信息均被裁剪
    for leaked in ("C:\\工程", "folder/", "\\\\"):
        assert leaked not in payload


def test_field_catalog_marks_builtin_fields_and_custom_definitions():
    snapshot = build_workspace_snapshot(
        workspace_id="ws-1",
        revision_id="rev-1",
        document=make_document(),
    )

    catalog = build_field_catalog(snapshot)

    assert [field.canonical_name for field in catalog.sheet] == [
        "number",
        "title",
        "file_name",
        "PROFESSIONAL",
        "专项",
        "备注",
        "比例",
    ]
    assert [field.builtin for field in catalog.sheet][:3] == [True, True, True]
    assert all(not field.builtin for field in catalog.sheet[3:])
    assert [field.scope for field in catalog.sheetset] == ["sheetset"] * 2
    assert [field.canonical_name for field in catalog.sheetset] == ["阶段", "项目号"]


# ---------------------------------------------------------------------------
# Capability Broker：清单声明 ∩ 宿主 allowlist、修订绑定、close() 失效
# ---------------------------------------------------------------------------


class StubReader:
    """只读 reader 替身：记录 workspace_id 并返回预置投影。"""

    def __init__(self, source: DecodedWorkspace) -> None:
        self.source = source
        self.requested: list[str] = []

    def load(self, workspace_id: str) -> DecodedWorkspace:
        self.requested.append(workspace_id)
        if workspace_id != self.source.workspace_id:
            raise ExtensionWorkspaceReadError(
                "EXTENSION_NOT_FOUND",
                f"工作区未登记：{workspace_id}",
                params={"workspace_id": workspace_id},
            )
        return self.source


def make_broker(source=None, **kwargs) -> tuple[CapabilityBroker, StubReader]:
    reader = StubReader(source or make_source(make_document()))
    kwargs.setdefault(
        "allowed_capabilities", frozenset({WORKSPACE_SNAPSHOT_CAPABILITY})
    )
    broker = CapabilityBroker(
        {SHEET_CATALOG_ID: load_manifest(SHEET_CATALOG_MANIFEST)},
        reader,
        **kwargs,
    )
    return broker, reader


def test_context_serves_declared_capability_and_binds_identity():
    broker, reader = make_broker()

    context = broker.context(SHEET_CATALOG_ID, "ws-1", "rev-1")
    snapshot = context.workspace_snapshot()

    assert reader.requested == ["ws-1"]
    assert context.extension_id == SHEET_CATALOG_ID
    assert context.invocation_id
    assert snapshot.workspace_id == "ws-1"
    assert snapshot.revision_id == "rev-1"
    assert [sheet.file_name for sheet in snapshot.sheets] == ["A.dwg", "A.dwg"]


def test_context_fails_after_close():
    broker, _ = make_broker()
    context = broker.context(SHEET_CATALOG_ID, "ws-1", "rev-1")
    assert context.workspace_snapshot() is not None

    context.close()

    with pytest.raises(CapabilityError) as exc_info:
        context.workspace_snapshot()
    assert exc_info.value.code == "EXTENSION_CAPABILITY_UNAVAILABLE"


def test_undeclared_capability_is_rejected():
    manifest = load_manifest(SHEET_CATALOG_MANIFEST)
    # 真实清单确实声明了快照能力；同构清单去掉声明后必须被拒绝
    assert WORKSPACE_SNAPSHOT_CAPABILITY in manifest.required_capabilities
    stripped = type(manifest)(
        extension_id=manifest.extension_id,
        version=manifest.version,
        host_contract=manifest.host_contract,
        enabled_by_default=manifest.enabled_by_default,
        name_key=manifest.name_key,
        description_key=manifest.description_key,
        required_capabilities=(),
        permissions=manifest.permissions,
        ui_contributions=manifest.ui_contributions,
        actions=manifest.actions,
        settings_schema=manifest.settings_schema,
    )
    broker = CapabilityBroker(
        {SHEET_CATALOG_ID: stripped},
        StubReader(make_source(make_document())),
        allowed_capabilities=frozenset({WORKSPACE_SNAPSHOT_CAPABILITY}),
    )

    with pytest.raises(CapabilityError) as exc_info:
        broker.context(SHEET_CATALOG_ID, "ws-1", "rev-1")
    assert exc_info.value.code == "EXTENSION_CAPABILITY_UNAVAILABLE"
    assert exc_info.value.params == {
        "extension_id": SHEET_CATALOG_ID,
        "capability": WORKSPACE_SNAPSHOT_CAPABILITY,
    }


def test_capability_outside_host_vocabulary_is_rejected():
    broker, _ = make_broker()

    with pytest.raises(CapabilityError) as exc_info:
        broker.context(
            SHEET_CATALOG_ID,
            "ws-1",
            "rev-1",
            capability="workspace.snapshot.write.v9",
        )
    assert exc_info.value.code == "EXTENSION_CAPABILITY_UNKNOWN"


def test_capability_outside_host_allowlist_is_rejected():
    broker, _ = make_broker(allowed_capabilities=frozenset())

    with pytest.raises(CapabilityError) as exc_info:
        broker.context(SHEET_CATALOG_ID, "ws-1", "rev-1")
    assert exc_info.value.code == "EXTENSION_CAPABILITY_UNAVAILABLE"


def test_unknown_extension_is_rejected():
    broker, _ = make_broker()

    with pytest.raises(CapabilityError) as exc_info:
        broker.context("dst-manager.unknown", "ws-1", "rev-1")
    assert exc_info.value.code == "EXTENSION_NOT_FOUND"


def test_revision_mismatch_requires_repreview():
    source = make_source(make_document())
    stale = DecodedWorkspace(
        workspace_id=source.workspace_id,
        revision_id="rev-2",
        document=source.document,
    )
    broker, _ = make_broker(stale)

    context = broker.context(SHEET_CATALOG_ID, "ws-1", "rev-1")
    with pytest.raises(CapabilityError) as exc_info:
        context.workspace_snapshot()
    assert exc_info.value.code == "REPREVIEW_REQUIRED"
    assert exc_info.value.params["workspace_id"] == "ws-1"


def test_reader_failures_are_mapped_to_structured_capability_errors():
    broker, _ = make_broker()

    context = broker.context(SHEET_CATALOG_ID, "ws-other", "rev-1")
    with pytest.raises(CapabilityError) as exc_info:
        context.workspace_snapshot()
    assert exc_info.value.code == "EXTENSION_NOT_FOUND"
    assert exc_info.value.params == {"workspace_id": "ws-other"}
