"""Builder AcSm DOM 工厂（SPEC-DB-001 §8）：从计划与 CAD 结果从零构造 DST。

不读取模板 DST，不调用 Manager document/editing 层，不做旧 DLL 回退；二进制
编码复用 :class:`dst_platform.acsm.codec.DstCodec`。对象 ID（数据库、指纹、
SheetSet/Subset/Sheet/LayoutReference/SheetViews）由计划哈希 + 对象语义路径
UUIDv5 派生：同一计划与 CAD 结果两次构造的 XML 字节一致，不同计划的对象 ID
必然不同，绝不使用随机值。
"""

from __future__ import annotations

import uuid

from lxml import etree

from dst_builder.domain.models import GenerationPlanV1
from dst_builder.infrastructure.autocad.request import CadDrawingResultV1
from dst_platform.acsm.codec import DstCodec
from dst_platform.acsm.contract import (
    CLSID_LAYOUT_REFERENCE,
    CLSID_SHEET,
    CLSID_SHEET_VIEWS,
    CLSID_SHEETSET,
    CLSID_SUBSET,
    validate_contract,
    validate_schema,
)
from dst_platform.contracts.diagnostics import Severity

__all__ = [
    "DST_DATABASE_CLSID",
    "DST_DB_VERSION",
    "DST_FILE_REVISION",
    "build_dst_bytes",
    "build_dst_xml",
    "dst_object_id",
]

# 稳定的 AcSmDatabase clsid（来自黄金样本，全局唯一类别标识）
DST_DATABASE_CLSID = "g2162C6B6-0CE4-40E8-912B-46F59DFDF826"
DST_DB_VERSION = "1.1"
DST_FILE_REVISION = "1"

_OBJECT_NAMESPACE_PREFIX = "dst-builder:dst-object:"


def dst_object_id(plan_sha256: str, semantic_path: str) -> str:
    """``g + UUIDv5(计划哈希:语义路径)`` 的十六进制大写形式（AcSm ID 约定）。"""
    name = f"{_OBJECT_NAMESPACE_PREFIX}{plan_sha256}:{semantic_path}"
    return "g" + str(uuid.uuid5(uuid.NAMESPACE_URL, name)).upper()


def _prop(name: str, value: str, *, vt: str = "8") -> etree._Element:
    node = etree.Element("AcSmProp", propname=name, vt=vt)
    node.text = value
    return node


def build_dst_xml(plan: GenerationPlanV1, cad_result: CadDrawingResultV1) -> bytes:
    """从零构造 AcSm DOM 并序列化为 XML 字节（纯函数，无 I/O）。

    首期固定形状：一个 SheetSet（名 = 工程名称）、一个 Subset（名 = 专业）、
    一个 Sheet（编号/标题）、一个 LayoutReference（布局名来自计划，Handle
    来自插件返回的实际 DWG 结果）。DST 与 DWG 同目录，引用只保存裸
    ``dwg_name``（``Relative_FileName`` 加 Windows 同目录前缀 ``.\\``）。
    """
    task = plan.sheetset_task
    sha256 = plan.plan_sha256

    root = etree.Element(
        "AcSmDatabase",
        ID=dst_object_id(sha256, "database"),
        clsid=DST_DATABASE_CLSID,
    )
    root.append(_prop("DbFingerPrint", dst_object_id(sha256, "database-fingerprint")))
    root.append(_prop("DbVersion", DST_DB_VERSION))
    root.append(_prop("FileRevision", DST_FILE_REVISION, vt="3"))

    sheetset = etree.SubElement(
        root,
        "AcSmSheetSet",
        ID=dst_object_id(sha256, "sheetset"),
        clsid=CLSID_SHEETSET,
        propname="SheetSet",
        vt="13",
    )
    sheetset.append(_prop("Name", task.sheetset_name))

    subset = etree.SubElement(
        sheetset,
        "AcSmSubset",
        ID=dst_object_id(sha256, "subset"),
        clsid=CLSID_SUBSET,
    )
    subset.append(_prop("Name", task.subset_name))

    sheet = etree.SubElement(
        subset,
        "AcSmSheet",
        ID=dst_object_id(sha256, "sheet"),
        clsid=CLSID_SHEET,
    )

    layout = etree.SubElement(
        sheet,
        "AcSmAcDbLayoutReference",
        ID=dst_object_id(sha256, "layout-reference"),
        clsid=CLSID_LAYOUT_REFERENCE,
        propname="Layout",
        vt="13",
    )
    layout.append(_prop("AcDbHandle", cad_result.layout_handle))
    layout.append(_prop("FileName", task.dwg_path))
    layout.append(_prop("Name", task.layout_name))
    layout.append(_prop("Relative_FileName", f".\\{task.dwg_path}"))

    sheet.append(_prop("Number", task.sheet_number))
    etree.SubElement(
        sheet,
        "AcSmSheetViews",
        ID=dst_object_id(sha256, "sheet-views"),
        clsid=CLSID_SHEET_VIEWS,
        propname="SheetViews",
        vt="13",
    )
    sheet.append(_prop("Title", task.sheet_title))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def build_dst_bytes(plan: GenerationPlanV1, cad_result: CadDrawingResultV1) -> bytes:
    """构造 XML，经共享结构校验后编码为 DST 二进制字节。

    编码前补一次共享结构校验（``validate_contract`` + ``validate_schema``，
    Task 8 遗留顺手补齐）：结构畸形不让它进入二进制编码路径。语义投影
    （与计划/CAD 结果的一致性）仍由编码后的解码验证承担（Task 9 编排层调用
    ``ensure_dst_valid``），本函数不做语义校验，避免重复投影开销。
    """
    xml = build_dst_xml(plan, cad_result)
    root = etree.fromstring(xml)
    issues = (*validate_contract(root), *validate_schema(root))
    errors = [issue for issue in issues if issue.severity is Severity.ERROR]
    if errors:
        raise ValueError(
            "DST 结构校验失败："
            + "；".join(f"{issue.code}: {issue.message}" for issue in errors)
        )
    return DstCodec().encode_bytes(xml)
