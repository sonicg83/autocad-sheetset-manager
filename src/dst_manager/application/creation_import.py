"""XLSX 创建输入的结构导入编排与诊断汇总（PLAN-DM-036 Task 2 / SPEC-DM-018 §5.2）。

``parse_creation_workbook`` 是全量导入的唯一入口：按**固定标准身份 + 隐藏技术
元数据**解析可见列，任何诊断都整批拒绝（``value`` 为 None），不产生部分结果，
也不接触草稿文件。校验顺序固定为：工作表结构 → 隐藏元数据 → 可见表头 →
``SheetSet`` 输入 → ``Sheet`` 组行，前面的阶段失败就不再读取后面的值。

不可信输入的处理口径：

- 单元格 Data Validation 不作信任边界，粘贴绕过与手工输入走同一套独立校验；
- 公式单元格、宏与外部链接、非文本单元格、未知/重复/缺失表头一律拒绝；
- 隐藏技术表被篡改（标准身份、列映射、``SheetSet`` 行映射、资产映射）一律拒绝；
- 资产一律按技术表的 ``asset_id`` 定位，再核对当前候选标签，不做标签→ID 猜测；
- ``Sheet`` 行序即组序，一行一组；「张数」不展开为逐张属性输入；
- 模板生成入口 ``build_creation_template`` 在基础设施层实现，此处一并再导出，
  使调用方一次导入即可拿到「导出模板 + 导入模板」这一对接口。
"""

from __future__ import annotations

import re
from dataclasses import replace

from dst_manager.domain.creation import (
    SHEET_SCOPE,
    CreationAssetOption,
    CreationDiagnostic,
    CreationGroupInput,
    CreationImportResult,
    CreationImportValue,
    ordinary_properties,
    validate_creation_target_path,
)
from dst_manager.domain.standard_models import (
    ASSET_KINDS,
    DrawingStandard,
    StandardProperty,
    normalize_property_name,
)
from dst_manager.infrastructure.creation_xlsx import (
    CREATION_TEMPLATE_VERSION,
    HIDDEN_SHEET_NAMES,
    MAX_GROUP_COUNT,
    MAX_SHEET_COLUMNS,
    MAX_SHEET_ROWS,
    META_FIRST_RECORD_ROW,
    META_HEADER,
    META_RECORDS,
    META_SHEET,
    SHEET_SHEET,
    SHEETSET_HEADERS,
    SHEETSET_SHEET,
    VISIBLE_SHEET_NAMES,
    CreationColumnSpec,
    CreationSheetGrid,
    CreationTemplatePlan,
    CreationWorkbookView,
    CreationXlsxReadError,
    build_creation_template,
    column_letter,
    creation_metadata_records,
    creation_template_plan,
    read_creation_workbook,
)

__all__ = [
    "build_creation_template",
    "parse_creation_workbook",
]

#: 资产映射键：固定列协议键 → 资产种类。
_ASSET_COLUMNS: tuple[tuple[str, str], ...] = (
    ("base_template", "base-template"),
    ("layout_template", "layout-template"),
)
#: 张数：只接受十进制正整数文本。
_COUNT_PATTERN = re.compile(r"^[1-9][0-9]*$")

#: 隐藏技术表里需要与模板计划逐字比对的两组记录。
_COLUMN_RECORDS = ("fixed_column", "property_column")
_SHEETSET_RECORDS = ("sheetset_target_path", "sheetset_property")


def parse_creation_workbook(
    data: bytes,
    standard: DrawingStandard,
    asset_options: tuple[CreationAssetOption, ...],
) -> CreationImportResult:
    """解析 XLSX 创建输入：合法时返回完整输入值，任何诊断都整批拒绝。"""
    try:
        view = read_creation_workbook(data)
    except CreationXlsxReadError as exc:
        return CreationImportResult(
            diagnostics=(
                CreationDiagnostic("CREATION_XLSX_UNREADABLE", f"工作簿无法读取：{exc}"),
            )
        )
    return _WorkbookParser(view, standard, asset_options).parse()


class _WorkbookParser:
    """一次导入解析：按固定阶段校验并汇总诊断，任一诊断即整批拒绝。"""

    def __init__(
        self,
        view: CreationWorkbookView,
        standard: DrawingStandard,
        asset_options: tuple[CreationAssetOption, ...],
    ) -> None:
        self.view = view
        self.standard = standard
        self.asset_options = asset_options
        self.plan: CreationTemplatePlan = creation_template_plan(standard, asset_options)
        self.diagnostics: list[CreationDiagnostic] = []
        #: 工作簿自带的资产标签映射：``(kind, label) → asset_id``。
        self.workbook_assets: dict[tuple[str, str], str] = {}

    # ---- 阶段编排 --------------------------------------------------------

    def parse(self) -> CreationImportResult:
        """按阶段推进；任一阶段产生诊断即整批拒绝，不再读取后续值。"""
        for stage in (self._check_structure, self._check_metadata, self._check_headers):
            stage()
            if self.diagnostics:
                return self._reject()
        target_path, sheetset_values = self._read_sheetset()
        if self.diagnostics:
            return self._reject()
        groups = self._read_groups()
        if self.diagnostics:
            return self._reject()
        return CreationImportResult(
            value=CreationImportValue(
                target_path=target_path, sheetset_values=sheetset_values, groups=groups
            )
        )

    def _reject(self) -> CreationImportResult:
        return CreationImportResult(value=None, diagnostics=tuple(self.diagnostics))

    def _add(
        self, code: str, message: str, sheet: str = "", row: int | None = None, column: str | None = None
    ) -> None:
        self.diagnostics.append(
            CreationDiagnostic(code=code, message=message, sheet=sheet, row=row, column=column)
        )

    def _grid(self, name: str) -> CreationSheetGrid:
        grid = self.view.sheet(name)
        assert grid is not None  # 结构阶段已确认工作表存在
        return grid

    def _cell(self, name: str, row: int, column: int) -> str:
        """按行列取单元格文本；越界或空单元格给空串。"""
        grid = self._grid(name)
        if not 1 <= row <= len(grid.rows) or not 1 <= column <= len(grid.rows[row - 1]):
            return ""
        return grid.rows[row - 1][column - 1]

    # ---- 阶段一：工作表结构与包级危险特征 --------------------------------

    def _check_structure(self) -> None:
        for marker in self.view.forbidden_parts:
            if marker == "vbaproject":
                self._add("CREATION_XLSX_MACRO_FORBIDDEN", "工作簿包内含宏部件，导入不执行宏")
            else:
                self._add(
                    "CREATION_XLSX_EXTERNAL_LINK_FORBIDDEN", "工作簿包内含外部链接部件，导入不读取外部数据"
                )
        if self.view.external_links:
            self._add("CREATION_XLSX_EXTERNAL_LINK_FORBIDDEN", "工作簿含外部链接，导入不读取外部数据")

        known = set(VISIBLE_SHEET_NAMES) | set(HIDDEN_SHEET_NAMES)
        for grid in self.view.sheets:
            if grid.name not in known:
                self._add(
                    "CREATION_XLSX_SHEET_INVALID",
                    f"未知工作表 {grid.name!r}，模板只允许 {list(VISIBLE_SHEET_NAMES)} 与隐藏技术表",
                    sheet=grid.name,
                )
            elif grid.name in VISIBLE_SHEET_NAMES and grid.state != "visible":
                self._add(
                    "CREATION_XLSX_SHEET_INVALID",
                    f"工作表 {grid.name!r} 必须可见",
                    sheet=grid.name,
                )
            elif grid.name in HIDDEN_SHEET_NAMES and grid.state == "visible":
                self._add(
                    "CREATION_XLSX_METADATA_INVALID",
                    f"技术表 {grid.name!r} 不得可见",
                    sheet=grid.name,
                )
        for name in VISIBLE_SHEET_NAMES:
            if self.view.sheet(name) is None:
                self._add("CREATION_XLSX_SHEET_INVALID", f"缺少可见工作表 {name!r}", sheet=name)
        if self.view.sheet(META_SHEET) is None:
            self._add(
                "CREATION_XLSX_METADATA_INVALID",
                f"缺少隐藏技术表 {META_SHEET!r}，无法按稳定身份解析",
                sheet=META_SHEET,
            )
        if self.diagnostics:
            return

        for grid in self.view.sheets:
            if grid.row_count > MAX_SHEET_ROWS:
                self._add(
                    "CREATION_XLSX_SCALE_EXCEEDED",
                    f"工作表 {grid.name!r} 行数 {grid.row_count} 超过受控上限 {MAX_SHEET_ROWS}",
                    sheet=grid.name,
                    row=MAX_SHEET_ROWS + 1,
                )
            if grid.column_count > MAX_SHEET_COLUMNS:
                self._add(
                    "CREATION_XLSX_SCALE_EXCEEDED",
                    f"工作表 {grid.name!r} 列数 {grid.column_count} 超过受控上限 {MAX_SHEET_COLUMNS}",
                    sheet=grid.name,
                    column=column_letter(MAX_SHEET_COLUMNS + 1),
                )
        for sheet, row, column in self.view.formulas:
            self._add(
                "CREATION_XLSX_FORMULA_FORBIDDEN",
                f"单元格 {column}{row} 是公式，导入不执行公式",
                sheet=sheet,
                row=row,
                column=column,
            )
        for sheet, row, column in self.view.invalid_cells:
            self._add(
                "CREATION_XLSX_CELL_TYPE_INVALID",
                f"单元格 {column}{row} 不是可解释的文本或数字",
                sheet=sheet,
                row=row,
                column=column,
            )

    # ---- 阶段二：隐藏技术元数据 ------------------------------------------

    def _check_metadata(self) -> None:
        records = self._read_metadata_records()
        if self.diagnostics:
            return
        self._check_metadata_identity(records)
        if self.diagnostics:
            return
        expected = creation_metadata_records(self.standard, self.plan)
        self._compare_records(
            [item for item in records if item[0][0] in _COLUMN_RECORDS],
            [item for item in expected if item[0] in _COLUMN_RECORDS],
            "列映射",
        )
        self._compare_records(
            [item for item in records if item[0][0] in _SHEETSET_RECORDS],
            [item for item in expected if item[0] in _SHEETSET_RECORDS],
            "SheetSet 行映射",
        )
        self._check_metadata_assets(records)

    def _read_metadata_records(self) -> list[tuple[tuple[str, str, str, str], int]]:
        """读隐藏技术表：表头、记录类型与单元格形状都必须符合协议。"""
        grid = self._grid(META_SHEET)
        if not grid.rows:
            self._add("CREATION_XLSX_METADATA_INVALID", "隐藏技术表为空", sheet=META_SHEET)
            return []
        header = tuple(cell.strip() for cell in grid.rows[0][: len(META_HEADER)])
        if header != META_HEADER:
            self._add(
                "CREATION_XLSX_METADATA_INVALID",
                f"隐藏技术表表头应为 {list(META_HEADER)}，实际为 {list(header)}",
                sheet=META_SHEET,
                row=1,
                column="A",
            )
            return []
        records: list[tuple[tuple[str, str, str, str], int]] = []
        for offset, cells in enumerate(grid.rows, start=1):
            self._check_meta_extra_columns(cells, offset)
            if offset == 1 or all(cell.strip() == "" for cell in cells):
                continue
            record = tuple(cell.strip() for cell in cells[: len(META_HEADER)])
            if record[0] not in META_RECORDS:
                self._add(
                    "CREATION_XLSX_METADATA_INVALID",
                    f"未知记录类型 {record[0]!r}",
                    sheet=META_SHEET,
                    row=offset,
                    column="A",
                )
                continue
            records.append((record, offset))
        if self.diagnostics:
            return []
        return records

    def _check_meta_extra_columns(self, cells: tuple[str, ...], row: int) -> None:
        """隐藏技术表只使用四列记录协议，多出的列不得有内容。"""
        for index in range(len(META_HEADER), len(cells)):
            if cells[index].strip():
                self._add(
                    "CREATION_XLSX_METADATA_INVALID",
                    f"隐藏技术表 {column_letter(index + 1)} 列不属于记录协议",
                    sheet=META_SHEET,
                    row=row,
                    column=column_letter(index + 1),
                )

    def _check_metadata_identity(self, records: list[tuple[tuple[str, str, str, str], int]]) -> None:
        """模板版本与精确标准身份必须与当前固定标准一致。"""
        checks = (
            (
                "version",
                "template_version",
                str(CREATION_TEMPLATE_VERSION),
                "CREATION_XLSX_TEMPLATE_VERSION_UNSUPPORTED",
            ),
            ("standard", "standard_id", self.standard.standard_id, "CREATION_XLSX_STANDARD_MISMATCH"),
            ("standard", "standard_version", self.standard.version, "CREATION_XLSX_STANDARD_MISMATCH"),
        )
        for record_type, key, expected, code in checks:
            found = [
                (record, row)
                for record, row in records
                if record[0] == record_type and record[1] == key
            ]
            if not found:
                self._add(
                    code,
                    f"隐藏技术表缺少记录 {key!r}，期望值 {expected!r}",
                    sheet=META_SHEET,
                )
                continue
            record, row = found[0]
            if record[2] != expected:
                self._add(
                    code,
                    f"{key} 记录 {record[2]!r} 与当前标准期望值 {expected!r} 不一致",
                    sheet=META_SHEET,
                    row=row,
                    column="C",
                )

    def _compare_records(
        self,
        actual: list[tuple[tuple[str, str, str, str], int]],
        expected: list[tuple[str, str, str, str]],
        label: str,
    ) -> None:
        """隐藏技术表的列/行映射必须与当前标准的模板计划逐字一致。"""
        if len(actual) != len(expected):
            row = (
                actual[len(expected)][1]
                if len(actual) > len(expected)
                else META_FIRST_RECORD_ROW + len(actual)
            )
            self._add(
                "CREATION_XLSX_METADATA_INVALID",
                f"{label}记录数 {len(actual)} 与模板计划 {len(expected)} 不一致",
                sheet=META_SHEET,
                row=row,
                column="A",
            )
            return
        for (record, row), want in zip(actual, expected):
            if record == want:
                continue
            index = next(position for position in range(len(want)) if record[position] != want[position])
            self._add(
                "CREATION_XLSX_METADATA_INVALID",
                f"{label}记录 {list(record)} 与模板计划 {list(want)} 不一致",
                sheet=META_SHEET,
                row=row,
                column=column_letter(index + 1),
            )
            return

    def _check_metadata_assets(self, records: list[tuple[tuple[str, str, str, str], int]]) -> None:
        """资产映射只做结构与一致性判定；可用性在组行按 ``asset_id`` 核对。"""
        seen: set[tuple[str, str]] = set()
        for record, row in records:
            if record[0] != "asset":
                continue
            kind, asset_id, label = record[1], record[2], record[3]
            if kind not in ASSET_KINDS or not asset_id or not label:
                self._add(
                    "CREATION_XLSX_METADATA_INVALID",
                    f"资产记录 {list(record)} 非法",
                    sheet=META_SHEET,
                    row=row,
                    column="B",
                )
                continue
            key = (kind, normalize_property_name(label))
            if key in seen:
                self._add(
                    "CREATION_XLSX_METADATA_INVALID",
                    f"资产标签 {label!r} 在 {kind} 内重复",
                    sheet=META_SHEET,
                    row=row,
                    column="D",
                )
                continue
            seen.add(key)
            self.workbook_assets[(kind, label)] = asset_id
            option = self._option(asset_id)
            if option is None:
                continue  # 已失效候选由组行按位置报错，不在这里制造噪声
            if option.kind != kind or option.label != label:
                self._add(
                    "CREATION_XLSX_METADATA_INVALID",
                    f"资产映射 {kind}/{label!r} 与当前候选 {asset_id!r}（{option.label!r}）不一致",
                    sheet=META_SHEET,
                    row=row,
                    column="C",
                )

    # ---- 阶段三：可见表头 -------------------------------------------------

    def _check_headers(self) -> None:
        self._check_sheetset_headers()
        self._check_sheet_headers()
        self._check_unexpected_content()

    def _check_sheetset_headers(self) -> None:
        for index, header in enumerate(SHEETSET_HEADERS, start=1):
            value = self._cell(SHEETSET_SHEET, 1, index).strip()
            if not value:
                self._add(
                    "CREATION_XLSX_HEADER_MISSING",
                    f"缺少 {SHEETSET_SHEET} 表头 {header!r}",
                    sheet=SHEETSET_SHEET,
                    row=1,
                    column=column_letter(index),
                )
            elif value != header:
                self._add(
                    "CREATION_XLSX_HEADER_MISMATCH",
                    f"{SHEETSET_SHEET} 表头 {value!r} 与模板 {header!r} 不一致",
                    sheet=SHEETSET_SHEET,
                    row=1,
                    column=column_letter(index),
                )
        for row_spec in self.plan.sheetset_rows:
            value = self._cell(SHEETSET_SHEET, row_spec.row, 1).strip()
            if not value:
                self._add(
                    "CREATION_XLSX_HEADER_MISSING",
                    f"缺少 {SHEETSET_SHEET} 行标签 {row_spec.label!r}",
                    sheet=SHEETSET_SHEET,
                    row=row_spec.row,
                    column="A",
                )
            elif value != row_spec.label:
                self._add(
                    "CREATION_XLSX_HEADER_MISMATCH",
                    f"{SHEETSET_SHEET} 行标签 {value!r} 与模板 {row_spec.label!r} 不一致",
                    sheet=SHEETSET_SHEET,
                    row=row_spec.row,
                    column="A",
                )

    def _check_sheet_headers(self) -> None:
        grid = self._grid(SHEET_SHEET)
        actual = [
            self._cell(SHEET_SHEET, 1, index).strip() for index in range(1, grid.column_count + 1)
        ]
        positions: dict[str, list[int]] = {}
        for index, value in enumerate(actual, start=1):
            if value:
                positions.setdefault(normalize_property_name(value), []).append(index)
        for indexes in positions.values():
            for index in indexes[1:]:
                self._add(
                    "CREATION_XLSX_HEADER_DUPLICATE",
                    f"表头 {actual[index - 1]!r} 重复出现",
                    sheet=SHEET_SHEET,
                    row=1,
                    column=column_letter(index),
                )
        for spec in self.plan.columns:
            value = actual[spec.index - 1] if spec.index <= len(actual) else ""
            if not value:
                self._add(
                    "CREATION_XLSX_HEADER_MISSING",
                    f"缺少表头 {spec.header!r}",
                    sheet=SHEET_SHEET,
                    row=1,
                    column=spec.column,
                )
            elif value != spec.header:
                self._add(
                    "CREATION_XLSX_HEADER_MISMATCH",
                    f"表头 {value!r} 与模板 {spec.header!r} 不一致",
                    sheet=SHEET_SHEET,
                    row=1,
                    column=spec.column,
                )

    def _check_unexpected_content(self) -> None:
        """计划之外的内容一律拒绝：额外列、额外 ``SheetSet`` 行都不许静默忽略。"""
        for name in VISIBLE_SHEET_NAMES:
            grid = self._grid(name)
            last_column = len(self.plan.columns) if name == SHEET_SHEET else 2
            for row in range(1, len(grid.rows) + 1):
                for column in range(last_column + 1, grid.column_count + 1):
                    if not grid.rows[row - 1][column - 1].strip():
                        continue
                    self._add(
                        "CREATION_XLSX_HEADER_UNKNOWN" if row == 1 else "CREATION_XLSX_CELL_UNEXPECTED",
                        f"单元格 {column_letter(column)}{row} 超出模板计划",
                        sheet=name,
                        row=row,
                        column=column_letter(column),
                    )
            if name != SHEETSET_SHEET:
                continue
            last_row = max(row_spec.row for row_spec in self.plan.sheetset_rows)
            for row in range(last_row + 1, len(grid.rows) + 1):
                for column in range(1, grid.column_count + 1):
                    if not grid.rows[row - 1][column - 1].strip():
                        continue
                    self._add(
                        "CREATION_XLSX_CELL_UNEXPECTED",
                        f"单元格 {column_letter(column)}{row} 超出模板计划",
                        sheet=name,
                        row=row,
                        column=column_letter(column),
                    )

    # ---- 阶段四：SheetSet 输入 -------------------------------------------

    def _read_sheetset(self) -> tuple[str, dict[str, str]]:
        target_path = ""
        values: dict[str, str] = {}
        for row_spec in self.plan.sheetset_rows:
            text = self._cell(SHEETSET_SHEET, row_spec.row, 2)
            if row_spec.is_target_path:
                target_path = text
                for found in validate_creation_target_path(text):
                    self.diagnostics.append(
                        replace(found, sheet=SHEETSET_SHEET, row=row_spec.row, column="B")
                    )
                continue
            assert row_spec.property_id is not None
            values[row_spec.property_id] = text
            self._check_enum_value(
                self.standard.property_by_id(row_spec.property_id), text, SHEETSET_SHEET, row_spec.row, "B"
            )
        return target_path, values

    def _check_enum_value(
        self, prop: StandardProperty, text: str, sheet: str, row: int, column: str
    ) -> None:
        """枚举值必须属于当前枚举列表；空值留给预览阶段的必填门禁。"""
        if prop.kind != "enum" or not text:
            return
        allowed = {item.value for item in prop.enum_items}
        if text not in allowed:
            self._add(
                "CREATION_XLSX_ENUM_VALUE_INVALID",
                f"属性 {prop.name!r} 的值 {text!r} 不在枚举列表 {sorted(allowed)} 内",
                sheet=sheet,
                row=row,
                column=column,
            )

    # ---- 阶段五：Sheet 组行 ----------------------------------------------

    def _read_groups(self) -> tuple[CreationGroupInput, ...]:
        grid = self._grid(SHEET_SHEET)
        title_spec = self._require_column("title")
        count_spec = self._require_column("count")
        sheet_properties = ordinary_properties(self.standard, SHEET_SCOPE)
        groups: list[CreationGroupInput] = []
        titles: dict[str, int] = {}
        for row in range(2, len(grid.rows) + 1):
            if not any(cell.strip() for cell in grid.rows[row - 1]):
                continue
            title = self._cell(SHEET_SHEET, row, title_spec.index)
            self._check_title(title, row, title_spec, titles)
            count = self._read_count(row, count_spec)
            assets = {
                kind: self._resolve_asset(kind, self._require_column(key), row)
                for key, kind in _ASSET_COLUMNS
            }
            paper_layout = self._resolve_paper_layout(assets["layout-template"], row)
            sheet_values: dict[str, str] = {}
            for prop in sheet_properties:
                spec = self._require_column(prop.property_id)
                text = self._cell(SHEET_SHEET, row, spec.index)
                sheet_values[prop.property_id] = text
                self._check_enum_value(prop, text, SHEET_SHEET, row, spec.column)
            groups.append(
                CreationGroupInput(
                    group_id=f"xlsx-{row}",
                    created_order=len(groups) + 1,
                    title=title,
                    count=count if count is not None else 0,
                    base_asset_id=assets["base-template"] or "",
                    layout_asset_id=assets["layout-template"] or "",
                    paper_layout=paper_layout or "",
                    sheet_values=sheet_values,
                )
            )  # 已有诊断时整组会被丢弃；仍按同一形状构造，保证组序与行序一致
        return tuple(groups)

    def _require_column(self, key: str) -> CreationColumnSpec:
        spec = self.plan.column(key)
        assert spec is not None  # 计划由标准与固定列生成，键必然存在
        return spec

    def _check_title(
        self, title: str, row: int, spec: CreationColumnSpec, titles: dict[str, int]
    ) -> None:
        if not title.strip():
            self._add(
                "CREATION_XLSX_TITLE_INVALID",
                "图名不能为空",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return
        key = normalize_property_name(title)
        if key in titles:
            self._add(
                "CREATION_XLSX_TITLE_DUPLICATE",
                f"图名 {title!r} 与第 {titles[key]} 行重复（去首尾空格、大小写不敏感）",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return
        titles[key] = row

    def _read_count(self, row: int, spec: CreationColumnSpec) -> int | None:
        text = self._cell(SHEET_SHEET, row, spec.index).strip()
        if not _COUNT_PATTERN.fullmatch(text) or int(text) > MAX_GROUP_COUNT:
            self._add(
                "CREATION_XLSX_COUNT_INVALID",
                f"张数 {text!r} 不是 1..{MAX_GROUP_COUNT} 的整数",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return None
        return int(text)

    def _resolve_asset(self, kind: str, spec: CreationColumnSpec, row: int) -> str | None:
        """按技术表的 ``asset_id`` 定位资产，再核对当前候选标签是否一致。"""
        label = self._cell(SHEET_SHEET, row, spec.index).strip()
        if not label:
            self._add(
                "CREATION_XLSX_ASSET_INVALID",
                f"{spec.header}不能为空",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return None
        asset_id = self.workbook_assets.get((kind, label))
        if asset_id is None:
            self._add(
                "CREATION_XLSX_ASSET_INVALID",
                f"{spec.header} {label!r} 不在模板的资产映射内",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return None
        option = self._option(asset_id)
        if option is None or option.kind != kind:
            self._add(
                "CREATION_XLSX_ASSET_INVALID",
                f"{spec.header} {label!r} 对应的资产 {asset_id!r} 已不可用",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return None
        if option.label != label:
            self._add(
                "CREATION_XLSX_ASSET_INVALID",
                f"{spec.header} {label!r} 与资产 {asset_id!r} 的当前标签 {option.label!r} 不一致",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return None
        return asset_id

    def _resolve_paper_layout(self, layout_asset_id: str | None, row: int) -> str | None:
        """图幅必须是所选布局模板实际包含的布局名。"""
        spec = self._require_column("paper_layout")
        paper_layout = self._cell(SHEET_SHEET, row, spec.index).strip()
        if layout_asset_id is None:
            return paper_layout or None
        option = self._option(layout_asset_id)
        if option is None:
            return paper_layout or None
        if not paper_layout:
            self._add(
                "CREATION_XLSX_PAPER_LAYOUT_INVALID",
                f"{spec.header}不能为空",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return None
        if paper_layout not in option.layouts:
            self._add(
                "CREATION_XLSX_PAPER_LAYOUT_INVALID",
                f"{spec.header} {paper_layout!r} 不在布局模板 {option.label!r} 的布局 {list(option.layouts)} 内",
                sheet=SHEET_SHEET,
                row=row,
                column=spec.column,
            )
            return None
        return paper_layout

    def _option(self, asset_id: str) -> CreationAssetOption | None:
        for option in self.asset_options:
            if option.asset_id == asset_id:
                return option
        return None
