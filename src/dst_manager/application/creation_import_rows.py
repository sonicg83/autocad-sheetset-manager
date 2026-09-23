"""XLSX 导入的可见表头、``SheetSet`` 输入与 ``Sheet`` 组行阶段（PLAN-DM-036 Task 2 / SPEC-DM-018 §5.2）。

阶段三判定两张可见表的表头与计划之外的单元格，阶段四读取 ``SheetSet`` 输入
（含完整最终路径的安全校验与枚举校验），阶段五按行读取图纸组：行序即组序，
一行一组，「张数」只作为组的 ``count``，绝不展开为逐张输入；全空行跳过（用户
清行视为删除），部分填写行按缺值报错。资产一律先按技术表的 ``asset_id`` 定位，
再核对当前候选标签，不做标签→ID 猜测；图幅必须是所选布局模板实际包含的布局名。

三个阶段都以 mixin 组合进
:class:`dst_manager.application.creation_import._WorkbookParser`，经 ``self`` 访问
它的 ``view``/``standard``/``plan``/``diagnostics``/``workbook_assets`` 状态与
``_add``/``_cell``/``_grid``/``_option`` 辅助；诊断只追加不抛出，由入口统一整批拒绝。
"""

from __future__ import annotations

import re
from dataclasses import replace

from dst_manager.domain.creation import (
    SHEET_SCOPE,
    CreationAssetOption,
    CreationDiagnostic,
    CreationGroupInput,
    ordinary_properties,
    validate_creation_target_path,
)
from dst_manager.domain.standard_models import (
    DrawingStandard,
    StandardProperty,
    normalize_property_name,
)
from dst_manager.infrastructure.creation_xlsx import (
    MAX_GROUP_COUNT,
    SHEET_SHEET,
    SHEETSET_HEADERS,
    SHEETSET_SHEET,
    VISIBLE_SHEET_NAMES,
    CreationColumnSpec,
    CreationTemplatePlan,
    column_letter,
)

__all__ = ["CreationRowStages"]

#: 资产映射键：固定列协议键 → 资产种类。
_ASSET_COLUMNS: tuple[tuple[str, str], ...] = (
    ("base_template", "base-template"),
    ("layout_template", "layout-template"),
)
#: 张数：只接受十进制正整数文本。
_COUNT_PATTERN = re.compile(r"^[1-9][0-9]*$")


class CreationRowStages:
    """阶段三（可见表头）、阶段四（``SheetSet`` 输入）与阶段五（``Sheet`` 组行）。"""

    standard: DrawingStandard  # 由 _WorkbookParser.__init__ 提供
    plan: CreationTemplatePlan
    diagnostics: list[CreationDiagnostic]
    asset_options: tuple[CreationAssetOption, ...]

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
