"""内置最小 DST 骨架的实例化契约（PLAN-DM-036 Task 5）。

唯一受版本控制的权威骨架是 `acsm_xml/assets/minimal_sheetset.xml`：静态结构、
无示例业务值，实例化时只用 DOM 写入动态值，**不做字符串替换**。本模块固定：

- 每次实例化生成新的数据库指纹与全部根/子对象 AcSm ID；
- `AcSmSheetSet.Name` 取最终项目目录名，项目路径写入 `NewSheetLocation`；
- 普通与派生文本属性按**属性名**写入（SPEC-DM-017 §3.2），并写保留属性
  `DSTManager.Standard` / `DSTManager.StandardOptions`；
- 布局引用先写受控占位 Handle，由暂存 Worker 回填；占位/零值/非法/重复
  Handle 一律拒绝，绝不靠 `"0"` 伪装通过 `validate()`。

夹具标准来自 `creation_xlsx_fixtures.STANDARD`（两个 sheetset 普通属性、一个
sheetset 派生映射、一个 sheet 普通文本、一个 sheet 普通枚举、一个 sheet 派生
组合），因此断言同时覆盖「普通属性按名写入」与「派生结果按名写入」。
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from creation_xlsx_fixtures import STANDARD

from dst_manager.domain.creation import CreationDraft, CreationGroupInput
from dst_manager.domain.creation_plan_models import CreationPlan
from dst_manager.domain.creation_planning import create_creation_plan
from dst_manager.domain.models import SuffixOptions
from dst_manager.infrastructure.acsm_xml import load_acsm
from dst_manager.infrastructure.acsm_xml.creation import (
    CREATION_DST_NAME,
    PLACEHOLDER_LAYOUT_HANDLE,
    SKELETON_PATH,
    STANDARD_IDENTITY_PROPERTY,
    STANDARD_OPTIONS_PROPERTY,
    apply_layout_handles,
    build_minimal_acsm,
    is_placeholder_handle,
    pending_layout_handles,
    standard_options_value,
)
from dst_manager.infrastructure.dst_codec import DstCodec

TARGET_PATH = r"C:\Projects\新建项目"
STANDARD_IDENTITY = "szmedi.gas@2.1.0"
#: 逐张 sheet 属性期望值：`prop-stage`/`prop-part` 是普通输入，`prop-label`
#: 是「专业代码-图号」派生组合。
EXPECTED_SHEET_PROPERTIES = [
    {"设计阶段": ["施工图"], "分部": ["A 段"], "图签": ["RQ-01"]},
    {"设计阶段": ["施工图"], "分部": ["A 段"], "图签": ["RQ-02"]},
    {"设计阶段": ["施工图"], "分部": ["B 段"], "图签": ["RQ-03"]},
]


def _draft() -> CreationDraft:
    """两个图纸组（2 张 + 1 张）：同组共用输入，组内逐张图号不同。"""
    return CreationDraft(
        id="draft-1",
        standard_id="szmedi.gas",
        standard_version="2.1.0",
        revision=1,
        step="review",
        target_path=TARGET_PATH,
        sheetset_values={"prop-name": "示例工程", "prop-major": "燃气"},
        groups=(
            CreationGroupInput(
                group_id="group-1",
                created_order=1,
                title="平面图",
                count=2,
                base_asset_id="base-a1",
                layout_asset_id="layout-a1",
                paper_layout="A1",
                sheet_values={"prop-stage": "施工图", "prop-part": "A 段"},
            ),
            CreationGroupInput(
                group_id="group-2",
                created_order=2,
                title="剖面图",
                count=1,
                base_asset_id="base-a1",
                layout_asset_id="layout-a1",
                paper_layout="A1",
                sheet_values={"prop-stage": "施工图", "prop-part": "B 段"},
            ),
        ),
    )


@pytest.fixture
def plan() -> CreationPlan:
    """无阻断诊断的创建计划（标题后缀关闭，不编号关键字为空）。"""
    result = create_creation_plan(_draft(), STANDARD, SuffixOptions(False, 1, ()))
    assert result.diagnostics == ()
    return result


def _property_texts(document, propname: str) -> list[str]:
    """图纸集属性袋里某个属性的 Value 文本（无 Value 节点即未写值）。"""
    return document.root.xpath(
        "//*[local-name()='AcSmSheetSet']/*[local-name()='AcSmCustomPropertyBag']"
        "/*[local-name()='AcSmCustomPropertyValue' and @propname=$propname]"
        "/*[local-name()='AcSmProp' and @propname='Value']/text()",
        propname=propname,
    )


def _sheet_property_texts(document) -> list[dict[str, list[str]]]:
    return [
        {
            value.get("propname"): value.xpath(
                "./*[local-name()='AcSmProp' and @propname='Value']/text()"
            )
            for value in sheet.xpath(
                "./*[local-name()='AcSmCustomPropertyBag']"
                "/*[local-name()='AcSmCustomPropertyValue']"
            )
        }
        for sheet in document.root.xpath("//*[local-name()='AcSmSheet']")
    ]


def test_minimal_acsm_has_fresh_ids_and_no_legacy_placeholders(plan) -> None:
    first = build_minimal_acsm(plan)
    second = build_minimal_acsm(plan)
    assert first.repair_report.status == "VALID"
    assert first.validate() == []
    assert set(first.root.xpath("//@ID")).isdisjoint(set(second.root.xpath("//@ID")))
    assert b"SheetSet Name" not in first.to_bytes()
    assert "工程路径" not in first.to_bytes().decode("utf-8")
    assert first.root.xpath("//*[local-name()='AcSmSheetSet']/*[local-name()='AcSmProp' and @propname='Name']/text()") == [
        Path(plan.target_path).name
    ]


def test_minimal_acsm_fingerprint_is_fresh_per_instantiation(plan) -> None:
    """数据库指纹每次实例化都不同：同一计划重复创建不得复用同一指纹。"""
    fingerprints = [
        document.root.xpath(
            "*[local-name()='AcSmProp' and @propname='DbFingerPrint']/text()"
        )
        for document in (build_minimal_acsm(plan), build_minimal_acsm(plan))
    ]
    assert all(len(value) == 1 and value[0] for value in fingerprints)
    assert fingerprints[0] != fingerprints[1]


def test_minimal_acsm_writes_project_path_and_layout_references(plan) -> None:
    """项目路径写入 NewSheetLocation；布局引用先写受控占位并指向最终目标 DWG。"""
    document = build_minimal_acsm(plan)
    assert document.root.xpath(
        "//*[local-name()='AcSmSheetSet']/*[local-name()='AcSmFileReference'"
        " and @propname='NewSheetLocation']"
        "/*[local-name()='AcSmProp' and @propname='FileName']/text()"
    ) == [TARGET_PATH]
    references = document.root.xpath(
        "//*[local-name()='AcSmAcDbLayoutReference' and @propname='Layout']"
    )
    assert len(references) == sum(group.sheet_count for group in plan.groups)
    expected = [
        (group.target_path, ".\\" + group.dwg_name, sheet.layout_name, PLACEHOLDER_LAYOUT_HANDLE)
        for group in plan.groups
        for sheet in group.sheets
    ]
    actual = [
        (
            reference.xpath("./*[local-name()='AcSmProp' and @propname='FileName']/text()")[0],
            reference.xpath("./*[local-name()='AcSmProp' and @propname='Relative_FileName']/text()")[0],
            reference.xpath("./*[local-name()='AcSmProp' and @propname='Name']/text()")[0],
            reference.xpath("./*[local-name()='AcSmProp' and @propname='AcDbHandle']/text()")[0],
        )
        for reference in references
    ]
    assert actual == expected
    assert all(is_placeholder_handle(item[3]) for item in actual)
    assert PLACEHOLDER_LAYOUT_HANDLE != "0"


def test_minimal_acsm_writes_subsets_sheets_and_numbers(plan) -> None:
    document = build_minimal_acsm(plan)
    subsets = document.root.xpath("//*[local-name()='AcSmSubset']")
    assert [
        subset.xpath("./*[local-name()='AcSmProp' and @propname='Name']/text()")[0]
        for subset in subsets
    ] == [group.title for group in plan.groups]
    assert [
        (
            sheet.xpath("./*[local-name()='AcSmProp' and @propname='Number']/text()")[0],
            sheet.xpath("./*[local-name()='AcSmProp' and @propname='Title']/text()")[0],
        )
        for subset in subsets
        for sheet in subset.xpath("./*[local-name()='AcSmSheet']")
    ] == [
        (sheet.number, sheet.title) for group in plan.groups for sheet in group.sheets
    ]


def test_minimal_acsm_writes_properties_by_name(plan) -> None:
    """普通与派生属性都按标准属性名写入；值分别取 sheetset 与逐张求值结果。"""
    document = build_minimal_acsm(plan)
    assert _property_texts(document, "工程名称") == ["示例工程"]
    assert _property_texts(document, "专业") == ["燃气"]
    assert _property_texts(document, "专业代码") == ["RQ"]
    # sheet 作用域属性在图纸集属性袋里只有定义（Flags=2，无 Value）
    assert _property_texts(document, "设计阶段") == []
    assert _property_texts(document, "图签") == []
    assert _sheet_property_texts(document) == EXPECTED_SHEET_PROPERTIES


def test_minimal_acsm_writes_standard_identity_and_effective_options(plan) -> None:
    """保留属性逐字钉住：标准身份与有效编号配置（Task 7 与 DST 读取方依赖）。"""
    document = build_minimal_acsm(plan)
    assert _property_texts(document, STANDARD_IDENTITY_PROPERTY) == [STANDARD_IDENTITY]
    options = _property_texts(document, STANDARD_OPTIONS_PROPERTY)
    assert options == [
        (
            '{"numbering":{"digits":2,"sequence_field":"subset.sequence","start":1},'
            '"suffix":{"enabled":false,"suffix_type":1,"unnumbered_keywords":[]},"version":1}'
        )
    ]
    assert options[0] == standard_options_value(plan.settings)
    assert json.loads(options[0]) == {
        "version": 1,
        "numbering": {"sequence_field": "subset.sequence", "digits": 2, "start": 1},
        "suffix": {"enabled": False, "suffix_type": 1, "unnumbered_keywords": []},
    }


def test_minimal_acsm_keeps_protocol_structure_from_real_databases(plan) -> None:
    """骨架保留真实 AcSm 数据库的协议节点；legacy 的拼写异常节点不作为必需。"""
    document = build_minimal_acsm(plan)
    assert document.root.xpath("//*[local-name()='AcSmPublishOptions']")
    assert document.root.xpath(
        "//*[local-name()='AcSmViewCategories']/*[local-name()='AcSmViewCategory']"
    )
    assert document.root.xpath("//*[local-name()='AcSmProjectPointLocations']")
    assert document.root.xpath("//*[local-name()='AcSmSheetSelSets']")
    assert not document.root.xpath("//*[local-name()='AcSmSimpleFileReferece']")
    assert document.root.xpath(
        "*[local-name()='AcSmProp' and @propname='DbVersion']/text()"
    ) == ["1.1"]


def test_skeleton_asset_is_static_and_carries_no_instance_identity() -> None:
    """骨架文件本身静态、无业务示例值、无内置 AcSm ID（ID 只由实例化生成）。"""
    text = SKELETON_PATH.read_text(encoding="utf-8")
    assert "SheetSet Name" not in text
    assert "工程路径" not in text
    assert 'ID="' not in text
    assert "<AcSmDatabase" in text


def test_instantiated_dst_keeps_no_skeleton_comments(plan) -> None:
    """骨架的说明注释不进入成果：产出的 DST 与真实 DST 一样只有数据节点。"""
    assert b"<!--" not in build_minimal_acsm(plan).to_bytes()


def test_pending_layout_handles_are_explicit_not_zero(plan) -> None:
    """未回填的中间态可显式识别：占位值非 0、可枚举，且回填前不得视为完成。"""
    document = build_minimal_acsm(plan)
    pending = pending_layout_handles(document)
    assert len(pending) == sum(group.sheet_count for group in plan.groups)
    assert "0" not in pending.values()
    assert all(is_placeholder_handle(value) for value in pending.values())


def test_apply_layout_handles_accepts_complete_real_handles(plan) -> None:
    document = build_minimal_acsm(plan)
    sheet_ids = document.root.xpath("//*[local-name()='AcSmSheet']/@ID")
    handles = {sheet_id: f"{0x100 + index:X}" for index, sheet_id in enumerate(sheet_ids)}
    apply_layout_handles(document, handles)
    assert pending_layout_handles(document) == {}
    assert document.validate() == []
    assert document.root.xpath(
        "//*[local-name()='AcSmAcDbLayoutReference' and @propname='Layout']"
        "/*[local-name()='AcSmProp' and @propname='AcDbHandle']/text()"
    ) == list(handles.values())


@pytest.mark.parametrize(
    ("case", "handles_factory"),
    [
        ("zero", lambda ids: {ids[0]: "0", ids[1]: "1", ids[2]: "2"}),
        ("not-hex", lambda ids: {ids[0]: "ZZ", ids[1]: "1", ids[2]: "2"}),
        ("placeholder", lambda ids: {ids[0]: PLACEHOLDER_LAYOUT_HANDLE, ids[1]: "1", ids[2]: "2"}),
        ("missing-sheet", lambda ids: {ids[0]: "1", ids[1]: "2"}),
        (
            "unknown-sheet",
            lambda ids: {
                ids[0]: "1",
                ids[1]: "2",
                ids[2]: "3",
                "g00000000-0000-0000-0000-000000000000": "4",
            },
        ),
        ("duplicate-in-drawing", lambda ids: {ids[0]: "1", ids[1]: "1", ids[2]: "2"}),
    ],
)
def test_apply_layout_handles_rejects_illegal_handles(plan, case, handles_factory) -> None:
    """零值、非十六进制、占位、覆盖不全、越界与同 DWG 内重复都必须拒绝。"""
    document = build_minimal_acsm(plan)
    sheet_ids = document.root.xpath("//*[local-name()='AcSmSheet']/@ID")
    with pytest.raises(ValueError) as excinfo:
        apply_layout_handles(document, handles_factory(sheet_ids))
    assert getattr(excinfo.value, "code", "").startswith("CREATION_HANDLE")
    assert pending_layout_handles(document) != {}


def test_minimal_acsm_rejects_text_that_cannot_be_written_to_xml(plan) -> None:
    """用户文本（自定义属性值）必须先过 XML 1.0 字符门禁，不能把原始异常漏出去。"""
    sheet = plan.groups[0].sheets[0]
    broken = replace(
        plan,
        groups=(
            replace(
                plan.groups[0],
                sheets=(replace(sheet, values={**sheet.values, "prop-stage": "施工\x01图"}),),
            ),
            *plan.groups[1:],
        ),
    )
    with pytest.raises(ValueError) as excinfo:
        build_minimal_acsm(broken)
    assert getattr(excinfo.value, "code", "") == "XML_TEXT_INVALID"


def test_minimal_acsm_survives_dst_codec_roundtrip(plan) -> None:
    """受控 DOM → DST 编码 → 解码 → 加载：修复状态与语义校验都必须仍然通过。"""
    codec = DstCodec()
    document = build_minimal_acsm(plan)
    roundtrip = load_acsm(codec.decode_bytes(codec.encode_bytes(document.to_bytes())))
    assert roundtrip.repair_report.status == "VALID"
    assert roundtrip.validate() == []


def test_creation_dst_name_is_the_project_database_file() -> None:
    """候选 DST 文件名是发布器要用的唯一常量（Task 6 不得再写字面量）。"""
    assert CREATION_DST_NAME == "图纸集数据文件.dst"
