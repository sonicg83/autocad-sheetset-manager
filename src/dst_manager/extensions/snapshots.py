"""裁剪的冻结工作区快照（PLAN-DM-020 Task 4 / ARCH-DM-006 §6.2）。

``workspace.snapshot.read.v1`` 的负载：冻结、可序列化的最小投影。属性
定义/值合并与大小写规范化**复用** :func:`property_definitions_from_document`
（不复制规则）；图纸文件名跨 Windows/Posix 分隔符裁 basename。快照绝不
包含 ``root``/``dst_path``/``resolved_path``/``Relative_FileName`` 或任何
绝对路径，也不携带可变领域对象——扩展拿到的只有本模块的冻结值对象。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from dst_manager.domain.editing import property_definitions_from_document

if TYPE_CHECKING:
    from dst_manager.domain.models import SheetSetDocument

__all__ = [
    "FieldCatalog",
    "FieldDefinition",
    "SheetSnapshot",
    "SnapshotProperty",
    "SnapshotPropertyScope",
    "WorkspaceSnapshot",
    "build_field_catalog",
    "build_workspace_snapshot",
]


@dataclass(frozen=True, slots=True)
class SnapshotProperty:
    canonical_name: str
    value: str


@dataclass(frozen=True, slots=True)
class SnapshotPropertyScope:
    custom_property_definitions: tuple[str, ...]
    custom_properties: tuple[SnapshotProperty, ...]


@dataclass(frozen=True, slots=True)
class SheetSnapshot:
    sheet_id: str
    number: str
    title: str
    file_name: str
    custom_property_definitions: tuple[str, ...]
    custom_properties: tuple[SnapshotProperty, ...]


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    scope: Literal["sheetset", "sheet"]
    canonical_name: str
    builtin: bool


@dataclass(frozen=True, slots=True)
class FieldCatalog:
    sheetset: tuple[FieldDefinition, ...]
    sheet: tuple[FieldDefinition, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    workspace_id: str
    revision_id: str
    sheetset: SnapshotPropertyScope
    sheets: tuple[SheetSnapshot, ...]


#: SPEC-DM-012 §4.1 的三个稳定固有字段（sheet 作用域，保留标识）。
SHEET_BUILTIN_FIELDS: tuple[str, ...] = ("number", "title", "file_name")


def _basename(value: str) -> str:
    """跨 Windows/Posix 分隔符裁 basename：两种共同语义下都只留末段。"""
    return value.replace("\\", "/").rpartition("/")[2]


def _sorted_properties(
    properties: dict[str, str], canonical: dict[str, str]
) -> tuple[SnapshotProperty, ...]:
    return tuple(
        SnapshotProperty(canonical[name.casefold()], value)
        for name, value in sorted(
            properties.items(), key=lambda item: (item[0].casefold(), item[0])
        )
    )


def build_workspace_snapshot(
    *, workspace_id: str, revision_id: str, document: SheetSetDocument
) -> WorkspaceSnapshot:
    """把当前 DST 投影裁剪为冻结、可序列化的最小快照（纯函数，零副作用）。"""
    definitions = property_definitions_from_document(document)
    # 作用域各自的 casefold 规范映射：跨作用域同名（casefold 相撞）属性
    # 不得互相覆盖，否则预览阶段按另一侧规范名查值会误报缺值。
    canonical_by_scope: dict[str, dict[str, str]] = {"sheetset": {}, "sheet": {}}
    for definition in definitions:
        canonical_by_scope[definition.type][definition.name.casefold()] = definition.name
    sheetset_scope = SnapshotPropertyScope(
        custom_property_definitions=tuple(
            definition.name for definition in definitions if definition.type == "sheetset"
        ),
        custom_properties=_sorted_properties(
            document.custom_properties, canonical_by_scope["sheetset"]
        ),
    )
    sheet_definitions = tuple(
        definition.name for definition in definitions if definition.type == "sheet"
    )
    # 子集顺序、图纸顺序展平（与领域文档的既有遍历顺序一致）。
    sheets = tuple(
        SheetSnapshot(
            sheet_id=sheet.acsm_id,
            number=sheet.number,
            title=sheet.title,
            file_name=_basename(sheet.layout.file_name),
            custom_property_definitions=sheet_definitions,
            custom_properties=_sorted_properties(
                sheet.custom_properties, canonical_by_scope["sheet"]
            ),
        )
        for sheet in document.sheets
    )
    return WorkspaceSnapshot(
        workspace_id=workspace_id,
        revision_id=revision_id,
        sheetset=sheetset_scope,
        sheets=sheets,
    )


def build_field_catalog(snapshot: WorkspaceSnapshot) -> FieldCatalog:
    """从快照推导字段目录：固有字段置 ``builtin``，自定义属性为普通字段。"""
    sheetset = tuple(
        FieldDefinition("sheetset", name, False)
        for name in snapshot.sheetset.custom_property_definitions
    )
    sheet_definitions = (
        snapshot.sheets[0].custom_property_definitions if snapshot.sheets else ()
    )
    sheet = tuple(
        FieldDefinition("sheet", name, True) for name in SHEET_BUILTIN_FIELDS
    ) + tuple(FieldDefinition("sheet", name, False) for name in sheet_definitions)
    return FieldCatalog(sheetset=sheetset, sheet=sheet)
