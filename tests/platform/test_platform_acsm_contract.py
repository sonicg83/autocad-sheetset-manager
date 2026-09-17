"""AcSm 契约校验平台所有权测试（PLAN-DB-001 Task 6，产品无关）。

所有权：``dst_platform.acsm.contract``（自 ``dst_manager.infrastructure.acsm_xml.contract``
迁入），XSD 随包资源迁至 ``dst_platform/acsm/schema/acsm-v1.xsd``。Manager 原路径
仅薄 re-export，行为由 tests/unit/test_acsm_contract.py 既有回归守护。
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from dst_platform.acsm.contract import (
    CONTRACT_VERSION,
    expected_prop_vt,
    object_contract,
    validate_contract,
    validate_schema,
)
from dst_platform.contracts.diagnostics import Severity, ValidationIssue

GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "shared"
    / "research"
    / "project1-dst-xml"
    / "project1_sheetset.xml"
)

_DB_ID = "g00000000-0000-0000-0000-100000000001"


def _base_xml() -> bytes:
    return (
        f'<AcSmDatabase ID="{_DB_ID}" clsid="g2162C6B6-0CE4-40E8-912B-46F59DFDF826">'
        '<AcSmProp propname="DbVersion" vt="8">1.1</AcSmProp>'
        '<AcSmSheetSet ID="g00000000-0000-0000-0000-100000000002" '
        'clsid="gB20534F2-0978-418C-8D14-2E6928A077ED" propname="SheetSet" vt="13">'
        '<AcSmSubset ID="g00000000-0000-0000-0000-100000000003" '
        'clsid="g076D548F-B0F5-4FE1-B35D-7F7B73B8D322">'
        '<AcSmSheet ID="g00000000-0000-0000-0000-100000000004" '
        'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065">'
        '<AcSmProp propname="Number" vt="8">001</AcSmProp>'
        "</AcSmSheet>"
        "</AcSmSubset>"
        "</AcSmSheetSet>"
        "</AcSmDatabase>"
    ).encode()


def _parse(xml: bytes) -> etree._Element:
    return etree.fromstring(xml)


def test_diagnostic_models_are_shared_not_copied() -> None:
    """Manager domain 与平台诊断模型必须是同一类型对象（避免两套诊断模型）。"""
    from dst_manager.domain import models as manager_models

    assert manager_models.Severity is Severity
    assert manager_models.ValidationIssue is ValidationIssue


def test_golden_sheetset_passes_contract_and_schema() -> None:
    root = _parse(GOLDEN.read_bytes())
    assert validate_contract(root) == ()
    assert validate_schema(root) == ()


def test_validate_contract_returns_immutable_sequence() -> None:
    root = _parse(_base_xml())
    assert isinstance(validate_contract(root), tuple)
    assert isinstance(validate_schema(root), tuple)


def test_contract_reports_missing_required_attribute() -> None:
    xml = _base_xml().replace(
        b'ID="g00000000-0000-0000-0000-100000000004" clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"',
        b'clsid="g16A07941-BC15-4D48-A880-9D5A211D5065"',
        1,
    )
    codes = {issue.code for issue in validate_contract(_parse(xml))}
    assert "CONTRACT_ATTRIBUTE_MISSING" in codes
    assert all(issue.severity is Severity.ERROR for issue in validate_contract(_parse(xml)))


def test_prop_vt_mismatch_reported() -> None:
    xml = _base_xml().replace(
        b'<AcSmProp propname="Number" vt="8">001</AcSmProp>',
        b'<AcSmProp propname="Number" vt="7">001</AcSmProp>',
        1,
    )
    codes = {issue.code for issue in validate_contract(_parse(xml))}
    assert "PROP_VT_MISMATCH" in codes


def test_unknown_elements_are_tolerated() -> None:
    xml = _base_xml().replace(b"</AcSmDatabase>", b'<Unknown keep="yes"/>tail</AcSmDatabase>', 1)
    assert validate_contract(_parse(xml)) == ()


def test_schema_rejects_wrong_root_with_xsd_invalid_code() -> None:
    xml = _base_xml().replace(b"<AcSmDatabase", b"<Foo", 1).replace(b"</AcSmDatabase>", b"</Foo>", 1)
    issues = validate_schema(_parse(xml))
    assert [issue.code for issue in issues] == ["XSD_INVALID"]


def test_contract_version_is_acsm_1_1() -> None:
    assert CONTRACT_VERSION == "acsm-1.1"


def test_registry_lookups_tolerate_unknown_types() -> None:
    assert object_contract("AcSmProp") is None
    assert expected_prop_vt("AcSmSheet", "未知字段") is None


def test_validation_issue_defaults() -> None:
    issue = ValidationIssue("CODE", Severity.WARNING, "消息")
    assert issue.object_id is None
    assert issue.location is None
