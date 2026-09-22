"""从现有 DST 导入标准草稿（PLAN-DM-035 Task 5 / PLAN-DM-038 Task 4）。

覆盖：导入不复制子集、图纸、工程路径或引用（``subsets``/``external_paths``
恒为空）、两级属性定义以稳定 ID 与 ``kind="text"`` 进入草稿文档、必填默认
``dwg_naming`` 写入且不推测现有 DWG 前缀、同名跨作用域按全局唯一规则拒绝、
非法/非 DST 来源稳定拒绝且不留任何草稿半成品。
"""

from pathlib import Path

import pytest
from lxml import etree

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.domain.standards import parse_standard_draft_document
from dst_manager.infrastructure.acsm_xml import AcsmDocument, AcsmValidationError
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.standards.dst_import import (
    _extract_property_definitions,
)

DEFAULT_NAMING_SEGMENTS = [
    {"system_field": "subset.scope"},
    {"literal": " "},
    {"system_field": "subset.name"},
]


@pytest.fixture
def service(tmp_path: Path) -> DstManagerService:
    return DstManagerService(Settings(data_dir=tmp_path / "data"))


@pytest.fixture
def imported_draft(service: DstManagerService, tiny_workspace):
    dst, _sheet_id = tiny_workspace
    return service.create_draft_from_dst(dst)


def properties_of(document: dict) -> set[tuple[str, str]]:
    return {(item["name"], item["scope"]) for item in document["properties"]}


def test_dst_import_excludes_project_structure(imported_draft) -> None:
    assert imported_draft.subsets == ()
    assert imported_draft.external_paths == ()


def test_dst_import_extracts_property_definitions(imported_draft) -> None:
    assert properties_of(imported_draft.document) == {
        ("比例", "sheet"),
        ("项目号", "sheetset"),
    }
    assert "rules" not in imported_draft.document
    assert all(item["kind"] == "text" for item in imported_draft.document["properties"])
    assert all(item["previous_names"] == [] for item in imported_draft.document["properties"])
    assert all(item["property_id"] for item in imported_draft.document["properties"])


def test_dst_import_writes_default_dwg_naming(imported_draft) -> None:
    assert imported_draft.document["dwg_naming"] == {"segments": DEFAULT_NAMING_SEGMENTS}


def test_dst_import_ids_are_stable_across_imports(service, tiny_workspace) -> None:
    dst, _sheet_id = tiny_workspace
    first = service.create_draft_from_dst(dst)
    second = service.create_draft_from_dst(dst)
    ids = lambda document: {
        item["name"]: item["property_id"] for item in document["properties"]
    }
    assert ids(first.document) == ids(second.document)


def test_dst_import_persists_valid_draft(service, imported_draft) -> None:
    stored = service.standard_store.get_draft(imported_draft.draft_id)
    assert stored is not None
    standard = parse_standard_draft_document(stored.document)
    assert standard.name == "测试集"
    assert standard.standard_id == imported_draft.document["standard_id"]


def test_dom_rejects_same_name_across_scopes(tiny_workspace) -> None:
    """AcSm DOM 层已拒绝同名跨作用域定义（兼容 AutoCAD 官方行为）。"""
    dst, _sheet_id = tiny_workspace
    document = AcsmDocument(DstCodec().decode_file(dst))
    with pytest.raises(AcsmValidationError, match="CUSTOM_PROPERTY_TYPE_CONFLICT"):
        document.apply_property_definition_commands(
            [
                {
                    "type": "add_custom_property",
                    "property_type": "sheetset",
                    "name": "比例",
                    "default_value": "1:100",
                }
            ]
        )


def test_extract_rejects_same_name_across_scopes() -> None:
    """第三方 DST 绕过 DOM 时，提取层仍按全局唯一规则拒绝并给出诊断。"""
    root = etree.fromstring(
        "<Root>"
        '<AcSmCustomPropertyValue propname="比例">'
        '<AcSmProp propname="Flags">2</AcSmProp></AcSmCustomPropertyValue>'
        '<AcSmCustomPropertyValue propname=" 比例 ">'
        '<AcSmProp propname="Flags">1</AcSmProp></AcSmCustomPropertyValue>'
        "</Root>"
    )
    with pytest.raises(ValueError, match="DST_PROPERTY_NAME_CONFLICT"):
        _extract_property_definitions(root)


def test_extract_dedupes_repeated_same_scope_instances() -> None:
    """同一属性在多个 AcSm 节点上重复出现时只产出一条定义。"""
    root = etree.fromstring(
        "<Root>"
        '<AcSmCustomPropertyValue propname="比例">'
        '<AcSmProp propname="Flags">2</AcSmProp></AcSmCustomPropertyValue>'
        '<AcSmCustomPropertyValue propname="比例">'
        '<AcSmProp propname="Flags">2</AcSmProp></AcSmCustomPropertyValue>'
        "</Root>"
    )
    definitions = _extract_property_definitions(root)
    assert [(item["name"], item["scope"], item["kind"]) for item in definitions] == [
        ("比例", "sheet", "text")
    ]


def test_invalid_dst_returns_stable_error_and_leaves_no_draft(
    service, tmp_path
) -> None:
    source = tmp_path / "broken.dst"
    source.write_bytes(b"not a dst file at all")
    with pytest.raises(ApplicationError) as exc_info:
        service.create_draft_from_dst(source)
    assert exc_info.value.code == "STANDARD_DST_IMPORT_INVALID"
    assert service.standard_store.list() == []


def test_missing_dst_source_rejected(service, tmp_path) -> None:
    with pytest.raises(ApplicationError) as exc_info:
        service.create_draft_from_dst(tmp_path / "absent.dst")
    assert exc_info.value.code == "STANDARD_DST_IMPORT_SOURCE_NOT_FOUND"


def test_non_dst_source_rejected(service, tmp_path) -> None:
    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"fake")
    with pytest.raises(ApplicationError) as exc_info:
        service.create_draft_from_dst(source)
    assert exc_info.value.code == "STANDARD_DST_IMPORT_SOURCE_INVALID"
