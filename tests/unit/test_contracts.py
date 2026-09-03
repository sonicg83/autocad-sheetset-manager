"""接口契约测试：布局来源（SPEC-DM-008 F-02）。

`LayoutSource` 在 `type=existing_snapshot` 时允许空 file/layout（由
`derive_document_structure` 解析回填）；`template_layout` 仍要求两字段必填，
缺失时报 `LAYOUT_SOURCE_INVALID`（沿用既有错误码与文案）。
"""

import pytest
from pydantic import ValidationError

from dst_manager.interfaces.contracts import InsertSubsetCommand, LayoutSource


def test_layout_source_existing_snapshot_accepts_explicit_empty_file_and_layout():
    source = LayoutSource(type="existing_snapshot", file="", layout="")

    assert source.file == ""
    assert source.layout == ""


def test_layout_source_existing_snapshot_omits_file_and_layout_by_default():
    source = LayoutSource(type="existing_snapshot")

    assert source.type == "existing_snapshot"
    assert source.file == ""
    assert source.layout == ""


def test_layout_source_existing_snapshot_still_accepts_explicit_source():
    source = LayoutSource(type="existing_snapshot", file="C:/工程/A.dwg", layout="001 平面")

    assert source.file == "C:/工程/A.dwg"
    assert source.layout == "001 平面"


def test_layout_source_template_layout_rejects_empty_file():
    with pytest.raises(ValidationError, match="LAYOUT_SOURCE_INVALID"):
        LayoutSource(type="template_layout", file="", layout="A3")


def test_layout_source_template_layout_rejects_empty_layout():
    with pytest.raises(ValidationError, match="LAYOUT_SOURCE_INVALID"):
        LayoutSource(type="template_layout", file="C:/模板/标准.dwt", layout="")


def test_layout_source_template_layout_requires_both_fields():
    LayoutSource(type="template_layout", file="C:/模板/标准.dwt", layout="A3")


def _insert_subset_command(**overrides: object) -> dict:
    payload = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "燃气管道平面图",
        "initial_sheet_count": 1,
        "source": {"type": "template_layout", "file": "C:/模板/标准.dwt", "layout": "A3"},
        "base_template_file": "C:/模板/图纸模板.dwg",
    }
    payload.update(overrides)
    return payload


def test_insert_subset_requires_base_template_file():
    command = _insert_subset_command()
    command.pop("base_template_file")

    with pytest.raises(ValidationError):
        InsertSubsetCommand(**command)


def test_insert_subset_rejects_relative_base_template_file():
    command = _insert_subset_command(base_template_file="模板/图纸模板.dwg")

    with pytest.raises(ValidationError):
        InsertSubsetCommand(**command)


@pytest.mark.parametrize("extension", [".txt", ".bak", ""])
def test_insert_subset_rejects_invalid_base_template_extension(extension: str):
    command = _insert_subset_command(base_template_file=f"C:/模板/图纸模板{extension}")

    with pytest.raises(ValidationError, match="INSERT_SUBSET_BASE_TEMPLATE_INVALID"):
        InsertSubsetCommand(**command)


@pytest.mark.parametrize("extension", [".dwg", ".dwt", ".DWG", ".Dwt"])
def test_insert_subset_accepts_dwg_and_dwt_base_template(extension: str):
    command = InsertSubsetCommand(**_insert_subset_command(base_template_file=f"C:/模板/图纸模板{extension}"))

    assert command.base_template_file == f"C:/模板/图纸模板{extension}"
