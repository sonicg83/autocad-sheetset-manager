"""标准驱动创建计划编译（PLAN-DM-036 Task 3）。

把「草稿输入 + 已发布标准 + 创建时有效编号设置」编译成不可变 ``CreationPlan``：
逐组图号/标题/布局名/DWG 文件名、逐张普通与派生属性、按组预览投影、稳定诊断与
确定性内容摘要。计划器**不读文件系统、不启动 CAD、不查标准包文件**：资产只按标准
声明的 ``asset_id`` 与图幅角色解析出**包内相对路径**，文件本体、目标目录状态与
标准包身份由应用层（Task 4/6）另行绑定。

同层模块划分（容量契约：单文件约 500 行）：

- :mod:`dst_manager.domain.creation_plan_models`：计划对外形状与确定性摘要；
- :mod:`dst_manager.domain.creation_plan_inputs`：输入门禁与标准资产解析；
- 本模块：入口 ``create_creation_plan``、编号/标题/布局派生、逐张求值与诊断去重。

计划同时冻结执行链（内置 DST 骨架实例化）所需的 ``settings``：标准身份、属性定义
（``property_id`` 与 AcSm 属性名/作用域）与有效编号/后缀选项——执行链只拿到计划，
无法从逐张输出反推这三项。

关键语义：

- ``draft.sheetset_values`` 与每组 ``sheet_values`` 必须是完整 ``property_id``
  字典：缺键报创建输入诊断，绝不在求值时临时补空串，也绝不从旧派生值回填；
- 漏传普通属性键在派生求值中同样报 ``STANDARD_DERIVED_UPSTREAM_INVALID`` 并阻断
  下游，显式空串仍按「可选源为空」处理（求值语义见 ``standard_rules``）；
- 图号位数与起点取 ``standard.numbering``，标题后缀与不编号关键字取
  ``suffix_options``；不编号组全组图号为补零 ``0`` 且不占号，后续组继续顺延；
- 每组一个主 DWG：``sheetset`` 派生结果用于全局 DWG 命名，任一失败或目标重名都
  使计划阻断，且不产出半成品文件名；
- 任何阻断错误都让 ``has_errors`` 为真，调用方不得使用该计划执行创建。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from dst_manager.domain.creation import (
    SHEET_SCOPE,
    SHEETSET_SCOPE,
    CreationDraft,
    CreationGroupInput,
    ordinary_properties,
)
from dst_manager.domain.creation_plan_inputs import (
    duplicate_title_diagnostics,
    group_diagnostics,
    input_diagnostics,
    resolve_base_template,
    resolve_layout_template,
    target_path_diagnostics,
)
from dst_manager.domain.creation_plan_models import (
    CreationPlan,
    CreationPlanDiagnostic,
    CreationProperty,
    CreationSettings,
    GroupPlan,
    PropertyCell,
    PropertyCellRow,
    SheetPlan,
    plan_digest,
    target_file_path,
)
from dst_manager.domain.editing import EditingError, derive_group_titles
from dst_manager.domain.models import SuffixOptions
from dst_manager.domain.planning import PlanningError, derive_layout_name
from dst_manager.domain.sheet_numbering import (
    compress_group_title,
    format_number_range,
    is_unnumbered_title,
)
from dst_manager.domain.standard_models import DrawingStandard
from dst_manager.domain.standard_naming import (
    SubsetNamingContext,
    validate_dwg_filenames,
)
from dst_manager.domain.standard_rules import (
    CompiledProperties,
    compile_standard_properties,
    evaluate_standard_properties,
)

__all__ = [
    "CreationPlan",
    "CreationPlanDiagnostic",
    "CreationProperty",
    "CreationSettings",
    "GroupPlan",
    "PropertyCell",
    "PropertyCellRow",
    "SheetPlan",
    "create_creation_plan",
]


def create_creation_plan(
    draft: CreationDraft,
    standard: DrawingStandard,
    suffix_options: SuffixOptions,
) -> CreationPlan:
    """把草稿与标准编译成创建计划；不读文件系统、不启动 CAD、不查标准包文件。"""
    compiled = compile_standard_properties(standard)
    sheetset_ordinary = ordinary_properties(standard, SHEETSET_SCOPE)
    sheet_ordinary = ordinary_properties(standard, SHEET_SCOPE)
    path_diagnostics = target_path_diagnostics(draft.target_path)
    diagnostics: list[CreationPlanDiagnostic] = [
        *path_diagnostics,
        *input_diagnostics(
            sheetset_ordinary,
            draft.sheetset_values,
            "",
            "CREATION_SHEETSET_VALUE_MISSING",
        ),
    ]

    group_inputs = list(draft.groups)
    titles = [group.title.strip() for group in group_inputs]
    base_templates: list[str] = []
    layout_templates: list[str] = []
    for index, group in enumerate(group_inputs):
        base_template, base_diagnostics = resolve_base_template(standard, group)
        layout_template, layout_diagnostics = resolve_layout_template(standard, group)
        base_templates.append(base_template)
        layout_templates.append(layout_template)
        diagnostics.extend(group_diagnostics(group, titles[index]))
        diagnostics.extend(
            input_diagnostics(
                sheet_ordinary,
                group.sheet_values,
                group.group_id,
                "CREATION_GROUP_VALUE_MISSING",
            )
        )
        diagnostics.extend(base_diagnostics)
        diagnostics.extend(layout_diagnostics)
    diagnostics.extend(duplicate_title_diagnostics(group_inputs, titles))

    # 输入形状门禁先于派生求值：先报「输入不完整/非法」，再报「求值失败」。
    diagnostics = _dedupe(diagnostics)
    sheetset_result, evaluation = _evaluate(
        compiled, draft.sheetset_values, {}, SHEETSET_SCOPE, ""
    )
    sheetset_values = _scope_values(standard, SHEETSET_SCOPE, sheetset_result)

    digits = standard.numbering.digits
    current = standard.numbering.start
    numbers: list[list[str]] = []
    for index, group in enumerate(group_inputs):
        count = max(group.count, 0)
        if is_unnumbered_title(titles[index], suffix_options.unnumbered_keywords):
            numbers.append(["0" * digits] * count)  # 不编号组全组图号为补零 0 且不占号
            continue
        numbers.append([str(current + offset).zfill(digits) for offset in range(count)])
        current += count
    number_ranges = [format_number_range(items) if items else "" for items in numbers]

    sheet_titles, title_diagnostics = _sheet_titles(
        [
            (number_ranges[index], titles[index], group.count)
            for index, group in enumerate(group_inputs)
        ],
        suffix_options,
    )
    evaluation.extend(title_diagnostics)
    sheets_by_group: list[tuple[SheetPlan, ...]] = []
    for index, group in enumerate(group_inputs):
        sheets: list[SheetPlan] = []
        for number, title in zip(numbers[index], sheet_titles[index]):
            values, sheet_diagnostics = _evaluate(
                compiled,
                {**draft.sheetset_values, **group.sheet_values},
                {"sheet.number": number, "sheet.title": title},
                SHEET_SCOPE,
                group.group_id,
            )
            layout_name, layout_diagnostics = _layout_name(
                number, title, group.group_id
            )
            evaluation.extend(sheet_diagnostics)
            evaluation.extend(layout_diagnostics)
            sheets.append(
                SheetPlan(
                    number=number,
                    title=title,
                    layout_name=layout_name,
                    values=_scope_values(standard, SHEET_SCOPE, values),
                )
            )
        evaluation.extend(_duplicate_layout_diagnostics(sheets, group.group_id))
        sheets_by_group.append(tuple(sheets))

    dwg_names, naming_diagnostics = _dwg_names(
        standard,
        sheetset_values,
        group_inputs,
        titles,
        number_ranges,
    )
    evaluation.extend(naming_diagnostics)
    diagnostics = _dedupe([*diagnostics, *evaluation])

    target_path = "" if path_diagnostics else draft.target_path
    groups = tuple(
        _group_plan(
            standard,
            group_inputs[index],
            titles[index],
            number_ranges[index],
            base_templates[index],
            layout_templates[index],
            dwg_names[index],
            target_path,
            sheets_by_group[index],
        )
        for index in range(len(group_inputs))
    )
    return CreationPlan(
        target_path=draft.target_path,
        settings=_creation_settings(standard, suffix_options),
        sheetset_values=sheetset_values,
        groups=groups,
        diagnostics=tuple(diagnostics),
        digest=plan_digest(
            draft, standard, suffix_options, sheetset_values, groups, diagnostics
        ),
    )


def _creation_settings(
    standard: DrawingStandard, suffix_options: SuffixOptions
) -> CreationSettings:
    """冻结执行链需要的标准身份、属性定义与有效编号/后缀选项。

    执行链（Task 5 的内置骨架实例化）只能拿到计划，因此标准身份（写
    ``DSTManager.Standard``）、AcSm 属性名与作用域（SPEC-DM-017 §3.2：DST 按
    属性名匹配，不按 ``property_id``）与有效编号配置（写
    ``DSTManager.StandardOptions``）必须随计划冻结。
    """
    return CreationSettings(
        standard_identity=f"{standard.standard_id}@{standard.version}",
        properties=tuple(
            CreationProperty(prop.property_id, prop.name, prop.scope)
            for prop in standard.properties
        ),
        numbering=standard.numbering,
        suffix_options=suffix_options,
    )


# ---- 标题、布局与命名 -------------------------------------------------------


def _sheet_titles(
    entries: Sequence[tuple[str, str, int]], suffix_options: SuffixOptions
) -> tuple[list[list[str]], list[CreationPlanDiagnostic]]:
    """复用编辑域标题派生；组结构非法或后缀超限时退化为组图名（计划已阻断）。"""
    if all(title and count >= 1 for _, title, count in entries):
        try:
            titles = derive_group_titles(
                list(entries), suffix_options.enabled, suffix_options.suffix_type
            )
            return titles, []
        except EditingError as exc:
            return (
                [[title] * max(count, 0) for _, title, count in entries],
                [
                    CreationPlanDiagnostic(
                        code=exc.code, message=f"图纸标题后缀派生失败：{exc}"
                    )
                ],
            )
    return [[title] * max(count, 0) for _, title, count in entries], []


def _layout_name(
    number: str, title: str, group_id: str
) -> tuple[str, list[CreationPlanDiagnostic]]:
    """复用受控编辑的布局名派生与校验（``LAYOUT_NAME_INVALID``）。"""
    try:
        return derive_layout_name(number, title), []
    except PlanningError as exc:
        return "", [
            CreationPlanDiagnostic(code=exc.code, message=str(exc), group_id=group_id)
        ]


def _duplicate_layout_diagnostics(
    sheets: Sequence[SheetPlan], group_id: str
) -> list[CreationPlanDiagnostic]:
    """一个主 DWG 内布局名不得重复（大小写不敏感），与受控编辑同一稳定错误码。"""
    diagnostics: list[CreationPlanDiagnostic] = []
    names: set[str] = set()
    for sheet in sheets:
        if not sheet.layout_name:
            continue
        key = sheet.layout_name.casefold()
        if key in names:
            diagnostics.append(
                CreationPlanDiagnostic(
                    code="DUPLICATE_LAYOUT_NAME",
                    message=f"目标DWG内布局名重复：{sheet.layout_name}",
                    group_id=group_id,
                )
            )
        names.add(key)
    return diagnostics


def _dwg_names(
    standard: DrawingStandard,
    sheetset_values: Mapping[str, str],
    group_inputs: Sequence[CreationGroupInput],
    titles: Sequence[str],
    number_ranges: Sequence[str],
) -> tuple[list[str], list[CreationPlanDiagnostic]]:
    """全局 DWG 命名：``sheetset`` 派生结果 + 组号段/图名，失败或重名即阻断。"""
    namable = [
        index
        for index, group in enumerate(group_inputs)
        if titles[index] and group.count >= 1
    ]
    contexts = [
        SubsetNamingContext(number_ranges[index], titles[index], index + 1)
        for index in namable
    ]
    names = [""] * len(group_inputs)
    if not contexts:
        return names, []
    results = validate_dwg_filenames(standard, sheetset_values, contexts)
    diagnostics: list[CreationPlanDiagnostic] = []
    for position, index in enumerate(namable):
        result = results[position]
        diagnostics.extend(
            CreationPlanDiagnostic(
                code=diagnostic.code,
                message=diagnostic.message,
                group_id=group_inputs[index].group_id,
                property_id=diagnostic.property_id or "",
                severity=diagnostic.severity,
            )
            for diagnostic in result.diagnostics
        )
        if result.ok:
            names[index] = result.filename
    return names, diagnostics


# ---- 逐组投影、求值与通用辅助 -----------------------------------------------


def _group_plan(
    standard: DrawingStandard,
    group: CreationGroupInput,
    title: str,
    number_range: str,
    base_template: str,
    layout_template: str,
    dwg_name: str,
    target_path: str,
    sheets: tuple[SheetPlan, ...],
) -> GroupPlan:
    return GroupPlan(
        group_id=group.group_id,
        created_order=group.created_order,
        title=title,
        number_range=number_range,
        title_range=compress_group_title(title, [sheet.title for sheet in sheets]),
        base_template=base_template,
        layout_template=layout_template,
        paper_layout=group.paper_layout.strip(),
        dwg_name=dwg_name,
        target_path=target_file_path(target_path, dwg_name),
        sheets=sheets,
        property_cells=_property_cells(standard, sheets),
    )


def _property_cells(
    standard: DrawingStandard, sheets: Sequence[SheetPlan]
) -> dict[str, PropertyCell]:
    """每个 ``sheet`` 属性（普通 + 派生）一组一个单元格：首张实际值 + 完整明细。"""
    cells: dict[str, PropertyCell] = {}
    for prop in standard.properties:
        if prop.scope != SHEET_SCOPE:
            continue
        rows = tuple(
            PropertyCellRow(number=sheet.number, value=sheet.values.get(prop.property_id, ""))
            for sheet in sheets
        )
        cells[prop.property_id] = PropertyCell(
            property_id=prop.property_id,
            first_value=rows[0].value if rows else "",
            sheets=rows,
        )
    return cells


def _evaluate(
    compiled: CompiledProperties,
    values: Mapping[str, str],
    system_values: Mapping[str, str],
    scope: str,
    group_id: str,
) -> tuple[dict[str, str], list[CreationPlanDiagnostic]]:
    """按作用域求值派生属性；另一作用域的失败在它自己的作用域内报告。"""
    result = evaluate_standard_properties(compiled, values, system_values)
    diagnostics: list[CreationPlanDiagnostic] = []
    for diagnostic in result.diagnostics:
        prop = (
            None
            if diagnostic.property_id is None
            else compiled.standard.find_property(diagnostic.property_id)
        )
        if prop is None or prop.scope != scope:
            continue
        diagnostics.append(
            CreationPlanDiagnostic(
                code=diagnostic.code,
                message=diagnostic.message,
                group_id=group_id,
                property_id=diagnostic.property_id or "",
                severity=diagnostic.severity,
            )
        )
    return result.values, diagnostics


def _scope_values(
    standard: DrawingStandard, scope: str, values: Mapping[str, str]
) -> dict[str, str]:
    """某作用域内的属性值（按标准文档顺序），派生失败时该键缺失（不补空串）。"""
    return {
        prop.property_id: values[prop.property_id]
        for prop in standard.properties
        if prop.scope == scope and prop.property_id in values
    }


def _dedupe(
    diagnostics: Sequence[CreationPlanDiagnostic],
) -> list[CreationPlanDiagnostic]:
    """同一 (错误码, 图纸组, 属性) 只保留首次出现：组输入由组内全部图纸共用。"""
    seen: set[tuple[str, str, str]] = set()
    result: list[CreationPlanDiagnostic] = []
    for diagnostic in diagnostics:
        key = (diagnostic.code, diagnostic.group_id, diagnostic.property_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(diagnostic)
    return result
