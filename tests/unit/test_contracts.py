"""接口契约测试：布局来源（SPEC-DM-008 F-02）。

`LayoutSource` 在 `type=existing_snapshot` 时允许空 file/layout（由
`derive_document_structure` 解析回填）；`template_layout` 仍要求两字段必填，
缺失时报 `LAYOUT_SOURCE_INVALID`（沿用既有错误码与文案）。
"""

import pytest
from pydantic import ValidationError

from dst_manager.interfaces.contracts import LayoutSource


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
