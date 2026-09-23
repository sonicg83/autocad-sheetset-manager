"""XLSX 导入的包级安全与隐藏技术元数据阶段（PLAN-DM-036 Task 2 / SPEC-DM-018 §5.2）。

阶段一判定工作表结构与包级危险特征（宏、外部链接、非文本单元格、受控规模），
阶段二判定隐藏技术表 ``_CreationMeta``：表头与记录协议、模板版本、精确标准身份、
列/``SheetSet`` 行映射与资产映射都必须与当前标准的规范计划一致。

两个阶段都以 mixin 组合进
:class:`dst_manager.application.creation_import._WorkbookParser`，经 ``self`` 访问
它的 ``view``/``standard``/``plan``/``diagnostics``/``workbook_assets`` 状态与
``_add``/``_grid``/``_option`` 辅助；诊断只追加不抛出，由入口统一整批拒绝。
"""

from __future__ import annotations

from dst_manager.domain.creation import CreationDiagnostic
from dst_manager.domain.standard_models import (
    ASSET_KINDS,
    DrawingStandard,
    normalize_property_name,
)
from dst_manager.infrastructure.creation_xlsx import (
    CREATION_TEMPLATE_VERSION,
    HIDDEN_SHEET_NAMES,
    MAX_SHEET_COLUMNS,
    MAX_SHEET_ROWS,
    META_FIRST_RECORD_ROW,
    META_HEADER,
    META_RECORDS,
    META_SHEET,
    VISIBLE_SHEET_NAMES,
    CreationTemplatePlan,
    CreationWorkbookView,
    column_letter,
    creation_metadata_records,
)

__all__ = ["CreationMetadataStages"]

#: 隐藏技术表里需要与模板计划逐字比对的两组记录。
_COLUMN_RECORDS = ("fixed_column", "property_column")
_SHEETSET_RECORDS = ("sheetset_target_path", "sheetset_property")


class CreationMetadataStages:
    """阶段一（工作表结构与包级危险特征）与阶段二（隐藏技术元数据）。"""

    view: CreationWorkbookView  # 由 _WorkbookParser.__init__ 提供
    standard: DrawingStandard
    plan: CreationTemplatePlan
    diagnostics: list[CreationDiagnostic]
    #: 工作簿自带的资产标签映射：``(kind, label) → asset_id``。
    workbook_assets: dict[tuple[str, str], str]

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
