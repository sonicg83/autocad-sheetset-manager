"""XLSX 创建输入的结构导入编排与诊断汇总（PLAN-DM-036 Task 2 / SPEC-DM-018 §5.2）。

``parse_creation_workbook`` 是全量导入的唯一入口：按**固定标准身份 + 隐藏技术
元数据**解析可见列，任何诊断都整批拒绝（``value`` 为 None），不产生部分结果，
也不接触草稿文件。校验顺序固定为：工作表结构 → 隐藏元数据 → 可见表头 →
``SheetSet`` 输入 → ``Sheet`` 组行，前面的阶段失败就不再读取后面的值；各阶段
实现按职责分在 :mod:`dst_manager.application.creation_import_metadata`（阶段一
与阶段二）与 :mod:`dst_manager.application.creation_import_rows`（阶段三到阶段五）。

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

from dst_manager.application.creation_import_metadata import CreationMetadataStages
from dst_manager.application.creation_import_rows import CreationRowStages
from dst_manager.domain.creation import (
    CreationAssetOption,
    CreationDiagnostic,
    CreationImportResult,
    CreationImportValue,
)
from dst_manager.domain.standard_models import DrawingStandard
from dst_manager.infrastructure.creation_xlsx import (
    CreationSheetGrid,
    CreationTemplatePlan,
    CreationWorkbookView,
    CreationXlsxReadError,
    build_creation_template,
    creation_template_plan,
    read_creation_workbook,
)

__all__ = [
    "build_creation_template",
    "parse_creation_workbook",
]


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


class _WorkbookParser(CreationMetadataStages, CreationRowStages):
    """一次导入解析：按固定阶段校验并汇总诊断，任一诊断即整批拒绝。

    本类只放阶段编排与共享状态访问（诊断收集、网格读取、资产候选查找）；
    阶段实现见 :class:`~dst_manager.application.creation_import_metadata.CreationMetadataStages`
    与 :class:`~dst_manager.application.creation_import_rows.CreationRowStages`。
    """

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

    def _option(self, asset_id: str) -> CreationAssetOption | None:
        """按稳定 ``asset_id`` 在当前资产候选中定位；已失效候选返回 None。"""
        for option in self.asset_options:
            if option.asset_id == asset_id:
                return option
        return None
