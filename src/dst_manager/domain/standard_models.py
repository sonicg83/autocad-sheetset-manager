"""图纸标准 Schema v1 领域模型（PLAN-DM-038 Task 1）。

本模块只放冻结数据类型：枚举项、映射行、令牌片段、属性、DWG 命名模板、
资产、编号、依赖、诊断与标准文档本体。解析与校验见 ``standard_schema``，
派生求值见 ``standard_rules``，DWG 命名见 ``standard_naming``。

领域层不依赖 FastAPI、Vue、文件系统或 AutoCAD；标准是纯数据文档，
内部 ID（``property_id``/``enum_item_id``）不写入或替代 AcSm GUID。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PropertyScope = Literal["sheetset", "sheet"]
PropertyKind = Literal["text", "enum", "mapping", "composition"]
DiagnosticSeverity = Literal["error", "warning"]

#: 属性作用域：只有图纸集与 Sheet 两级。
PROPERTY_SCOPES: tuple[str, ...] = ("sheetset", "sheet")
#: 普通属性种类：普通属性只含文本与枚举。
ORDINARY_PROPERTY_KINDS: tuple[str, ...] = ("text", "enum")
#: 派生属性种类：派生属性只含映射与组合。
DERIVED_PROPERTY_KINDS: tuple[str, ...] = ("mapping", "composition")
PROPERTY_KINDS: tuple[str, ...] = ORDINARY_PROPERTY_KINDS + DERIVED_PROPERTY_KINDS

#: 子集系统字段：只对标准级 DWG 命名模板开放。
SUBSET_SYSTEM_FIELDS: tuple[str, ...] = (
    "subset.scope",
    "subset.name",
    "subset.sequence",
)
#: Sheet 系统字段：只对 sheet 作用域组合属性开放；不含 ``sheet.name`` 与布局名。
SHEET_SYSTEM_FIELDS: tuple[str, ...] = ("sheet.number", "sheet.title")
SYSTEM_FIELDS: tuple[str, ...] = SUBSET_SYSTEM_FIELDS + SHEET_SYSTEM_FIELDS

#: 保留属性名（比较时忽略大小写）；``DSTManager.*`` 前缀整体保留。
RESERVED_PROPERTY_NAMES: tuple[str, ...] = SYSTEM_FIELDS + (
    "DSTManager.Standard",
    "DSTManager.StandardOptions",
)
RESERVED_PROPERTY_NAME_PREFIX = "dstmanager."

#: 资产种类：基础模板与布局模板。
ASSET_KINDS: tuple[str, ...] = ("base-template", "layout-template")

#: 引用种类：映射源、组合令牌与 DWG 命名令牌。
REFERENCE_KINDS: tuple[str, ...] = ("mapping", "composition", "dwg-naming")


def normalize_property_name(name: str) -> str:
    """属性名比较口径：忽略首尾空格与大小写（SPEC-DM-017 §3.2）。"""
    return name.strip().casefold()


@dataclass(frozen=True, slots=True)
class StandardEnumItem:
    """枚举项；``item_id`` 稳定，改名不改变映射行身份。"""

    item_id: str
    value: str


@dataclass(frozen=True, slots=True)
class StandardMappingRow:
    """映射行：以源枚举项 ID 为身份，``value`` 为目标值（可暂时为空）。"""

    item_id: str
    value: str


@dataclass(frozen=True, slots=True)
class StandardSegment:
    """令牌片段：字段令牌、系统字段令牌或固定文本，三者互斥。"""

    property_id: str | None = None
    system_field: str | None = None
    literal: str | None = None
    format: str | None = None

    @property
    def is_token(self) -> bool:
        return self.property_id is not None or self.system_field is not None


@dataclass(frozen=True, slots=True)
class StandardProperty:
    """标准属性定义；普通与派生属性共用一个全局命名空间。"""

    property_id: str
    name: str
    previous_names: tuple[str, ...]
    scope: str
    kind: str
    required: bool = False
    default_value: str = ""
    enum_items: tuple[StandardEnumItem, ...] = ()
    source_property_id: str | None = None
    mapping: tuple[StandardMappingRow, ...] = ()
    confirmed_source_items: tuple[tuple[str, str], ...] = ()
    segments: tuple[StandardSegment, ...] = ()
    description: str = ""

    @property
    def is_derived(self) -> bool:
        return self.kind in DERIVED_PROPERTY_KINDS

    def enum_item(self, item_id: str) -> StandardEnumItem | None:
        for item in self.enum_items:
            if item.item_id == item_id:
                return item
        return None

    def mapping_row(self, item_id: str) -> StandardMappingRow | None:
        for row in self.mapping:
            if row.item_id == item_id:
                return row
        return None


@dataclass(frozen=True, slots=True)
class DwgNamingTemplate:
    """标准级唯一 DWG 命名模板；只生成文件名主体，扩展名由系统追加。"""

    segments: tuple[StandardSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class StandardReference:
    """一处属性引用；``owner_id`` 为引用方属性 ID，DWG 命名为空串。"""

    kind: str
    owner_id: str
    segment_index: int | None = None


@dataclass(frozen=True, slots=True)
class StandardDiagnostic:
    """标准诊断；``code`` 为稳定错误码，供前后端共用同一码表。"""

    code: str
    message: str
    severity: str = "error"
    property_id: str | None = None
    segment_index: int | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


@dataclass(frozen=True, slots=True)
class StandardAssetFile:
    """包内相对路径及其角色（如图幅枚举值）。"""

    path: str
    role: str = ""


@dataclass(frozen=True, slots=True)
class StandardAsset:
    """标准模板资产声明；文件本体由标准包层校验与复制。"""

    asset_id: str
    kind: str
    files: tuple[StandardAssetFile, ...] = ()


@dataclass(frozen=True, slots=True)
class NumberingPolicy:
    """编号策略：受控序号字段、补零位数与起始值。"""

    sequence_field: str
    digits: int
    start: int = 1


@dataclass(frozen=True, slots=True)
class StandardDependency:
    """受信扩展依赖；缺少声明能力时标准能力降级。"""

    extension_id: str
    capability_id: str
    min_version: str


@dataclass(frozen=True, slots=True)
class DrawingStandard:
    """不可变的图纸标准文档（Schema v1）。"""

    schema_version: int
    standard_id: str
    version: str
    name: str
    supported_cad_versions: tuple[str, ...]
    properties: tuple[StandardProperty, ...]
    dwg_naming: DwgNamingTemplate
    assets: tuple[StandardAsset, ...]
    numbering: NumberingPolicy
    dependencies: tuple[StandardDependency, ...] = ()

    def find_property(self, property_id: str) -> StandardProperty | None:
        for prop in self.properties:
            if prop.property_id == property_id:
                return prop
        return None

    def property_by_id(self, property_id: str) -> StandardProperty:
        """按稳定 ID 取属性；缺失时抛 ``KeyError``。"""
        prop = self.find_property(property_id)
        if prop is None:
            raise KeyError(property_id)
        return prop

    def property_by_name(self, scope: str, name: str) -> StandardProperty | None:
        """按作用域 + 规范化当前名称取属性（不含历史名称迁移）。"""
        target = normalize_property_name(name)
        for prop in self.properties:
            if prop.scope == scope and normalize_property_name(prop.name) == target:
                return prop
        return None

    def references_to(self, property_id: str) -> tuple[StandardReference, ...]:
        """枚举对该属性的全部引用：映射源、组合令牌与 DWG 命名令牌。

        删除保护与发布诊断共用本方法；顺序为属性文档顺序 + DWG 命名片段顺序。
        """
        references: list[StandardReference] = []
        for prop in self.properties:
            if prop.kind == "mapping" and prop.source_property_id == property_id:
                references.append(
                    StandardReference(kind="mapping", owner_id=prop.property_id)
                )
            if prop.kind == "composition":
                for index, segment in enumerate(prop.segments):
                    if segment.property_id == property_id:
                        references.append(
                            StandardReference(
                                kind="composition",
                                owner_id=prop.property_id,
                                segment_index=index,
                            )
                        )
        for index, segment in enumerate(self.dwg_naming.segments):
            if segment.property_id == property_id:
                references.append(
                    StandardReference(kind="dwg-naming", owner_id="", segment_index=index)
                )
        return tuple(references)
