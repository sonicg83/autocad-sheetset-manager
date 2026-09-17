"""AcSm 契约校验兼容导出（PLAN-DB-001 Task 6：实现所有权已迁至 dst_platform.acsm.contract）。

本模块只做薄 re-export；唯一实现与随包 XSD（dst_platform/acsm/schema/acsm-v1.xsd）
见 ``dst_platform/acsm/contract.py``。
"""

from dst_platform.acsm.contract import (
    CLSID_LAYOUT_REFERENCE,
    CLSID_PROPERTY_BAG,
    CLSID_PROPERTY_VALUE,
    CLSID_SHEET,
    CLSID_SHEET_VIEWS,
    CLSID_SHEETSET,
    CLSID_SUBSET,
    CONTRACT_VERSION,
    ObjectContract,
    expected_prop_vt,
    object_contract,
    validate_contract,
    validate_schema,
)

__all__ = [
    "CLSID_LAYOUT_REFERENCE",
    "CLSID_PROPERTY_BAG",
    "CLSID_PROPERTY_VALUE",
    "CLSID_SHEET",
    "CLSID_SHEETSET",
    "CLSID_SHEET_VIEWS",
    "CLSID_SUBSET",
    "CONTRACT_VERSION",
    "ObjectContract",
    "expected_prop_vt",
    "object_contract",
    "validate_contract",
    "validate_schema",
]
