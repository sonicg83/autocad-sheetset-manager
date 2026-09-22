"""从现有 DST 导入标准草稿（PLAN-DM-035 Task 5）：只提取属性定义与最小安全结构。

覆盖：导入不复制子集、图纸、工程路径或引用（``subsets``/``external_paths``
恒为空）、两级属性定义进入草稿文档、非法/非 DST 来源稳定拒绝且不留任何
草稿半成品。
"""

from pathlib import Path

import pytest

from dst_manager.application.errors import ApplicationError
from dst_manager.application.service import DstManagerService
from dst_manager.config import Settings
from dst_manager.domain.standards import parse_standard_document


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


def test_dst_import_persists_valid_draft(service, imported_draft) -> None:
    stored = service.standard_store.get_draft(imported_draft.draft_id)
    assert stored is not None
    standard = parse_standard_document(stored.document)
    assert standard.name == "测试集"
    assert standard.standard_id == imported_draft.document["standard_id"]


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
