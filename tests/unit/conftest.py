"""tests/unit 共享夹具：创建 XLSX 模板与导入用例的标准与资产候选。

夹具数据与辅助函数见 :mod:`creation_xlsx_fixtures`（同目录模块）；这里只把它
包装成 pytest 夹具，供「模板生成」「元数据与安全」「行解析」三个测试模块共用。
"""

import pytest
from creation_xlsx_fixtures import (
    ASSET_OPTIONS,
    STANDARD,
    STANDARD_WITH_COUNT_PROPERTY,
)

from dst_manager.domain.creation import CreationAssetOption
from dst_manager.domain.standards import DrawingStandard


@pytest.fixture
def standard() -> DrawingStandard:
    return STANDARD


@pytest.fixture
def options() -> tuple[CreationAssetOption, ...]:
    return ASSET_OPTIONS


@pytest.fixture
def standard_with_sheet_property_named_count() -> DrawingStandard:
    return STANDARD_WITH_COUNT_PROPERTY
