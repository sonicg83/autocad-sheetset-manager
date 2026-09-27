---
id: PLAN-DM-044
title: 语义化 grid 伪表格对齐契约收口实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-27
updated: 2026-09-27
related:
  - ARCH-DM-007
  - SPEC-DM-006
  - SPEC-DM-017
  - SPEC-DM-018
  - SPEC-DM-023
  - PLAN-DM-029
  - PLAN-DM-043
---

# 语义化 grid 伪表格对齐契约收口实施计划

> **执行约定：** 实施者逐任务使用 `superpowers:executing-plans` 或经用户选定的同等流程，按 RED → 最小实现 → GREEN → 复核执行；复选框只在实际完成并登记验证后勾选。本文是待执行计划，不代表任何组件已完成语义标记或样式整改。

**目标：** 把 4 个用户可见、以 CSS grid 模拟表格的组件（`EnumValuesDialog.vue`、`MappingPropertyDialog.vue`、`DerivedPropertyEditor.vue`、`ColumnEditor.vue`）纳入 [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.4 的单元格对齐契约：先补齐显式表格语义与稳定锚点，再新增一组 `grid-table-*` 静态规则要求其表头/数据行取明确行高档、令牌化单档 padding 与显式对齐，并由 Playwright 断言真实几何；同时补齐 `check:ui` 的「语义化表格必须有契约规则」守卫，堵住 PLAN-DM-043 删除 `legacy.css` 兜底后暴露的「新增表格静默回退」缺口。

**架构：** 沿用 PLAN-DM-043 建成的两层验证：静态层扩展现有 CSS 规则/声明解析与例外棘轮（新增 `grid-table-*` 规则与 `table-without-cell-contract` 守卫），计算样式层由 Playwright 在同一断言处钉令牌名与计算绝对值。不引入新表格框架、不重写 DOM 结构、不新增 44px 令牌。

**技术栈：** Windows 11、Vue 3、TypeScript、Vite、Node.js 内置 `node:test`、Vitest、Playwright、CSS 自定义属性；Python 仅运行既有 Ruff/pytest 回归。

**规范依据（本轮需增量修订的正文，见 Task 1）：** 用户可见口径以 [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.4 为唯一权威；实现与门禁边界见 [ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §4.3/§9.1/§9.3。现有两处正文只以 `th/td` 表述表格，需以**增量条款**（不静默改写既有条目）补入「语义化 grid 表格」口径，否则本计划的静态规则会与已接受规范正文矛盾。派生属性表还须遵守 [SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md) 的编辑器 Demo 与分级响应式（1050px/780px 隐藏说明列与源摘要列），目录列编辑器须遵守 SPEC-DM-023 系列既有列轨道约定。

**与 PLAN-DM-043 的关系：** PLAN-DM-043 收口的是真实 `<table>` 组件（11 组件 / 18 张表），本计划收口 **grid 伪表格**，两者不重叠、不互相取代。PLAN-DM-043 已删除 `legacy.css` 的 `:where(#app) th,:where(#app) td` 兜底，本计划的 grid 表格**从未**依赖该规则（其几何全部来自组件自身 scoped 样式），因此本计划不重新引入任何全局兜底。

**双重表头取消裁决（2026-09-27 用户确认，方案 C「列头即标签」）：** 本计划**取消** grid 表行内在单元格上重复渲染的字段标签（`EnumValuesDialog` 每行的「枚举值」、`MappingPropertyDialog` 每行的「目标值」、`DerivedPropertyEditor` 每行的「属性名/作用域/说明」、`ColumnEditor` 每行的「输出列名 N/表达式 N」），由**列头**承担该列的可访问名称：行内控件不再传 `label`，改以 `aria-labelledby` 关联同列 `role="columnheader"`（或列头元素）的 `id`。本计划范围内**四张**表全部取「列头即标签」路径（`DerivedPropertyEditor` 与 `ColumnEditor` 均由 2026-09-27 用户追加裁决纳入；`ColumnEditor` 因列头文字与行内旧名不同，另按「列头文字 + 行号补足」裁决处理，见 Task 4）。这与既有"仅视觉隐藏"路径（`OrdinaryPropertyEditor` / `GroupsStep` 的 `:deep(.ui-input__label){display:none}`）**并存但不互斥**：本计划不改动那两处正在使用中的表格。该裁决同时要求扩展 `visible-input-label` 门禁的第四种合法形态（见全局约束与 Task 2），否则移除 `label` 属性会立即让 `check:ui` 失败。

**范围裁决（2026-09-27 用户确认）：** ① 路线取「**语义标记 + 门禁扩展**」——保留现有 grid 实现，给伪表格补显式表格语义，`check:ui` 新增 grid 表规则，同步增量修订规范正文；不采用「改造为真实 `<table>`」（DOM 重写会牵动 aria、键盘模型、粘性表头、响应式隐藏列与既有 e2e，回归面最大），也不采用「只做视觉整改 + 断言」（无法阻止新增伪表格静默回退）。② 覆盖 **4 张全收**：枚举值弹窗、映射属性弹窗、派生属性表、目录列编辑器。③ 「语义化表格必须声明契约规则」的守卫**一并纳入**本计划（原载体为 [2026-09-26-new-table-guard-and-cell-gate-boundary.md](../../todos/dst-manager/2026-09-26-new-table-guard-and-cell-gate-boundary.md) 第 1 项），实施时把该项标记为「由 PLAN-DM-044 承接」，其第 2–5 项仍留待办。

## 前置条件

- SPEC-DM-006 §6.4 与 ARCH-DM-007 §4.3/§9 的现行修订（含 PLAN-DM-043 的 2026-09-26 增补）是实施基准；实施前先通读两处正文与 PLAN-DM-043 的 Task 1–5 执行记录，确认口径后再写 RED。
- 实施前确认 `web/` 依赖可用，并用裸检查器（`node scripts/check-ui-contracts.mjs`）取得 `ui-contract-exceptions.json` 的现存条目数基线（当前 10 条例外 + 1 条动态变量），作为棘轮对照；不得凭源码推断存量违规数。
- Task 2 的迁移基线必须**一次量取全部 4 个组件**的表头行/数据行的现状计算值（行高、padding、`align-items`、列轨道模板），作为 Task 3–6 的 RED 依据与最终命中证据。
- 本计划为前端视觉、语义与静态门禁调整，不需要真实 AutoCAD 作为实施前置条件；最终桌面缩放复验需要 Windows WebView2，缺失时记录证据缺口并**保持 `active`**（[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §12），不得据此宣布验收通过。

## 全局约束

- 任务开始前检查 `rtk git status --short`，保留用户已有改动；只暂存本任务文件。每次实际代码修改同步更新根 `changelog.md`，提交信息用简体中文动词短语。
- **不改** HTTP/SSE、后端校验、字段含义、props/emits、i18n key、焦点管理与键盘模型；**不改** `ColumnEditor.vue` 与 `DerivedPropertyEditor.vue` 的响应式断点行为（1050px 隐藏说明列、780px 隐藏源摘要列、≤720px 隐藏表头等既有约定必须保持）。
- **不改** 已清退的例外表语义：既有的 `unicode-structure-icon`（`ColumnEditor.vue` 的 ↑/↓/✕、`GroupsStep.vue`、`RevisionHistoryPanel.vue` 的 `→`、`SheetToolbar.vue` 的 ✕）与 `visible-input-label` 条目不得因本计划改写或删除；本计划只新增自身到期条件的条目。
- grid 伪表格的普通行基础档取与同类真实表一致的 `44px`（消费既有 `--sheet-table-row-height`）；若某张 grid 表实测内容高度超过 44px（`DerivedPropertyEditor` 的 `.derived-row` 为 `align-items:start` 且含错误行，`ColumnEditor` 的表达式格为 2 行 textarea），则取「**≥44px 且消费该档**」，不断言恰好 44px，也不压到 44px 以下。普通 `padding` 统一取 `var(--space-2)`（8px）单档；`EnumValuesDialog`/`MappingPropertyDialog` 允许改用 `var(--space-1)`（4px），但同一张表内必须单档且令牌化，且必须在 Task 2 基线量取后按实测决定，不得两种混用。
- 表头行与同表普通数据行**同档同 padding**；表头对齐方向与其列数据一致（文本列左、可比较数值列右 + `tabular-nums`、纯图标操作列可右/居中）；grid 表**没有** `vertical-align`，对应的垂直对齐约束改由行轨道对齐表达：行的 `align-items` 必须显式声明（`center` 为默认；仅多行长文本格允许 `start`），禁止依赖浏览器默认 `stretch`。
- 语义标记形态（本轮裁决）：3 张**模态/伪表体**组件用 ARIA 语义 —— 表头容器 `role="row"` 且其列标题项 `role="columnheader"`，数据行容器 `role="row"`，行内各列项 `role="cell"`；`DerivedPropertyEditor.vue` 的 `.derived-list` 已带 `data-testid="derived-table"`，按**同一形态**补语义。`ColumnEditor.vue` 的 `.columns-head`/`.column-row` 已有列轨道对齐 e2e，本轮**不新增 ARIA 角色**（避免与基准 Demo 可访问名比较产生歧义），只复用既有 `data-testid` 锚点，由 Task 6 单独裁决其门禁命中方式。
- **列头可访问名契约（方案 C，本计划强制）：** 行内控件承担的是「该单元格取值」，其可访问名称必须来自同列列头，不得来自单元格内重复渲染的标签。落地要求：① 每个列头元素必须有稳定且唯一的 `id`（本轮在模板内显式声明，便于断言与 `aria-labelledby` 引用；`ColumnEditor` 的列头不需要新增 `role`，但 `id` 必须加）；② 行内 `UiInput` **不再传 `label`**，改为 `:aria-labelledby="<该列列头的id>"`（`UiInput` 的 `$attrs` 会落到真实 `<input>`，见 [UiInput.vue](file:///c:/Users/sonic/autocad-sheetset/web/src/components/ui/UiInput.vue#L41-L45)）；③ 行内不得再出现「可见或隐藏的第二个同义标签」——本轮**不使用** `:deep(.ui-input__label){display:none}`，也不保留 `label` 属性，凡四张表行内出现 `.ui-input__label` 即判失败；④ 无可见文字或仅装饰的列头（如纯图标操作列）**不参与** 可访问名，仍由行内 `aria-label` 承担，不得强行为其造文字用于 `aria-labelledby`；⑤ 当列头文字不足以区分同行多个控件（`ColumnEditor` 的「列名」对多行同义）时，按「列头文字 + 行号补足」处理：`aria-labelledby` 指向列头，另以 `aria-describedby` 或行内既有说明元素补足序号，使读屏不出现 N 行同报同一名称；⑥ 实施时须同步核对 e2e 的 `getByTestId`/`getByLabel` 定位是否受影响——**定位以 `data-testid` 为主，避免依赖可见文案**。
- **列头 `aria-hidden` 与 `aria-labelledby` 的共存规则（`DerivedPropertyEditor` 专用裁决）：** 该表列头当前为 `aria-hidden="true"`（列标题仅视觉呈现，可访问名由行内 `aria-label` 承担）。本轮取方案 C 后，列头必须同时是「可见文字」与「可访问名来源」，因此：① 移除列头容器的 `aria-hidden="true"`，但**保留**每个列项自身的 `id` 与 `role="columnheader"`；② 行内 `UiInput` 的 `aria-label` 与 `label` 一并移除，改由 `aria-labelledby` 指向同列列头；③ 行内非输入格（`.source-summary`、`.scope-locked`、`UiButton`/`UiIconButton`）不参与 `aria-labelledby`，其可访问名保持现状；④ `.derived-head` 的 `:nth-child(5)`/`:nth-child(3)` 响应式隐藏（1050px/780px）**只隐藏视觉**，被隐藏列的列头 `id` 必须仍在 DOM 中（`display:none` 元素仍可被 `aria-labelledby` 引用），不得连带删除 `id` 或改用条件渲染。若实测发现 `aria-hidden` 移除会让读屏重复播报列标题（与基准 Demo 对照不符），按 Task 3 Step 3 的最小必要集合裁决：优先保留 `role="columnheader"` 与 `id`、仅对**空列**（纯操作列）恢复 `aria-hidden`，并在执行记录中登记实际采用集合。
- **门禁口径扩展（`visible-input-label` 第四种合法形态）：** 现有三条合法形态为「自带非空 `label`」「位于 `FormField` 默认插槽」「存在有可见文字的外部 `<label for=X>` 且 `id` 一致」（见 [check-ui-contracts.mjs](file:///c:/Users/sonic/autocad-sheetset/web/scripts/check-ui-contracts.mjs#L482-L528)）。本轮新增第四条：「控件的 `aria-labelledby` 指向同组件模板内**已有可见文字**的列头元素的 `id`」。判定须同时满足三项：① 指向元素存在（`id` 文本与 `aria-labelledby` 文本相等）；② 该元素有可见文字（复用 `hasVisibleText`）；③ 该元素是**列头元素**——判定条件为「声明 `role="columnheader"`」**或**「位于声明表格语义（`role="row"`/`role="table"`）的容器内且是 `.columns-head` 类列头行」二者之一，以覆盖 `ColumnEditor` 不新增 `role` 的例外（见全局约束的语义标记形态裁决）。**不得放宽既有三条的严格度**，也不得把该形态扩成"任意 `aria-labelledby` 即可"。
- 每个实现任务先写能因目标缺陷失败的测试，再做最小改动并复跑。静态门禁新增或规则变更须运行变异用例；现存偏差按 `ui-contract-exceptions.json` 的指纹棘轮登记与逐项清退，不以全局白名单掩盖新表格。
- **本轮新增静态规则不得放宽既有两条规则**（`table-cell-vertical-align` 要求所有 `th/td` 规则显式声明该属性，`table-cell-padding` 要求普通格单档令牌化）——该字面口径有 SPEC-DM-006 §6.4 与 ARCH-DM-007 §4.3 正文支持。

## 文件与责任边界

| 责任 | 主要文件 | 验收位置 |
| --- | --- | --- |
| 规范正文本轮增量修订 | `docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md`（§6.4）、`docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md`（§4.3、§9.1、§9.3） | 文档走查 + 后续任务的规则命名一致性 |
| 静态规则与守卫 | `web/scripts/ui-contracts/grid-table-cells.mjs`（新增）、`table-without-cell-contract.mjs`（新增，或并入前一模块）、`types.mjs`、`check-ui-contracts.mjs`（含 `visible-input-label` 第四形态）、`ui-contract-exceptions.json` | `web/scripts/check-ui-contracts.test.mjs` |
| 迁移基线与计数 | 同上 + `.planning/plans/dst-manager/PLAN-DM-044-grid-pseudo-table-alignment.md` 执行记录 | 检查器 CLI 输出 |
| 标准平台三张伪表格 | `web/src/components/standards/EnumValuesDialog.vue`、`MappingPropertyDialog.vue`、`DerivedPropertyEditor.vue` | `web/tests/e2e/standards-editor.spec.ts`、`standards-visual-evidence.spec.ts` |
| 目录列编辑器 | `web/src/components/sheet-catalog/ColumnEditor.vue` | `web/tests/e2e/sheet-catalog.spec.ts`、`sheet-catalog-visual-evidence.spec.ts` |
| 守卫与全量验证 | 上述全部 + `changelog.md` | `test:contracts`、`check:ui`、`build`、`test:e2e` |

`CompositionPropertyDialog.vue`、`GroupBatchDialog.vue`、`XlsxImportDialog.vue`、`PropertyValuePanel.vue` 展开卡、`PropertyValueCompareDialog.vue`、`TemplateAssetsEditor.vue` 的 `.file-row`、`GeneratedExtensionSettingsForm.vue` 的 `.ef-row` 均**不在本计划范围**：它们是表单、列表或卡片，没有「表头 + 列」语义（已按源码逐一核实）。若执行时发现未列出的「表头行 + 重复数据行」grid 结构，按同一契约纳入本计划并更新清单。

## Review Focus

1. **双重表头已取消（方案 C）**：`EnumValuesDialog`、`MappingPropertyDialog`、`DerivedPropertyEditor`、`ColumnEditor` 的行内 `UiInput` 均不再渲染第二条同义标签，其可访问名称来自同列列头 `id` 经 `aria-labelledby` 关联；`check:ui` 对这四张表新增断言「行内不得出现 `.ui-input__label`」。`OrdinaryPropertyEditor`/`GroupsStep` 的"仅视觉隐藏"路径并存，本轮不动。
2. `DerivedPropertyEditor.vue` 的 1050px/780px 隐藏列、`ColumnEditor.vue` 的 ≤720px 隐藏表头行为不被破坏；被隐藏列的表头项与数据项仍保持同一 grid 轨道定义；列头隐藏时其 `aria-labelledby` 目标仍须存在于 DOM（`display:none` 元素仍可被 `aria-labelledby` 引用），不得连带删除 `id`。`.derived-head` 原有 `aria-hidden="true"` 已按方案 C 移除，须确认读屏不出现列标题重复播报。
3. 语义标记不产生重复的表格语义或新增不必要的 Tab 停靠点：ARIA 角色标注不改变键盘模型，`role="row"` 容器内的输入控件仍可正常聚焦与 Tab 遍历。
4. 新增守卫 `table-without-cell-contract` 的存量命中数为 **0**（4 张 grid 表在 Task 3–6 完成后都有规则，18 张真实表在 PLAN-DM-043 后都有规则）；若实测不为 0，必须先在本计划列明清退任务与到期条件，不得直接登记例外放行。
5. 变异证据齐全：`grid-table-*`、守卫与 `visible-input-label` 第四形态都要有 CLI 级变异注入（第四形态至少覆盖「`aria-labelledby` 指向不存在元素」「指向元素无可见文字」「指向元素缺 `role="columnheader"`」三种反向用例），且 `check-ui-contracts.test.mjs` 的分类数/注入数/规则集合三处计数同步更新（当前为 20 分类 / 22 注入 / 16 规则）。
6. `ui-contract-exceptions.json` 不残留本计划到期项，且既有 10 条例外的指纹未被无意改写。

## 任务

### Task 1：规范正文本轮增量修订

**Files:** `docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md`（§6.4）、`docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md`（§4.3、§9.1、§9.3）。

**Interfaces:** 在 SPEC-DM-006 §6.4「单元格对齐契约」下新增一条**独立子条目**（例如「语义化 grid 表格」），不修改既有 `th/td` 条目文字；在 ARCH-DM-007 §4.3 补对应实现边界、§9.1 补静态门禁条目、§9.3 补计算样式断言要求。新规则名与字段名在本文档确定后不得在实施中改写。

- [ ] 在 SPEC-DM-006 §6.4 增补：以 `role="row"`/`role="columnheader"`/`role="cell"` 或等效语义标注的 grid 表格，与 `<table>` 表格适用同一对齐契约（水平对齐方向、表头跟随列数据、基础行高档、单档令牌化 padding、行内控件垂直中点 ±1px）；差异点是垂直对齐由行轨道 `align-items` 承载而非 `vertical-align`。注明该条目为 2026-09-27 增补及来源（PLAN-DM-044）。
- [ ] 在 SPEC-DM-006 §6.4 增补**列头即可访问名**条款：语义化表格的行内输入控件，其可访问名称由同列列头承担（`aria-labelledby` 指向 `role="columnheader"` 的 `id`），同一字段**不得**在列头与单元格内各渲染一次标签（"双重表头"）；既有以视觉隐藏单元格内标签的表格不因此条款回退，但新增语义化表格一律取列头路径。注明该条款来自 2026-09-27 用户裁决（方案 C）。
- [ ] 在 ARCH-DM-007 §4.3 增补实现边界：grid 表格的行容器必须显式声明 `align-items`（`center` 默认、多行长文本格 `start`），且必须显式声明行高档与令牌化 padding；`role="columnheader"` 必须带稳定 `id` 供 `aria-labelledby` 引用；§9.1 增补 `grid-table-*`、`table-without-cell-contract` 与 `visible-input-label` 第四形态三条门禁的口径（含「守卫只判定模板事实与已声明规则，不猜测计算几何」）；§9.3 增补 grid 表的计算样式断言要求（列轨道对齐、行高、padding、行内控件中点差 ≤1px、行内不出现 `.ui-input__label`）。
- [ ] 复核修订后与 PLAN-DM-043 的既有条款不冲突，并在计划「修订记录」登记本次规范修订；提交信息：`增补语义化 grid 表格对齐规范`。

### Task 2：建立 grid 表格静态规则与迁移基线

**Files:** 新建 `web/scripts/ui-contracts/grid-table-cells.mjs`、`web/scripts/ui-contracts/table-without-cell-contract.mjs`；修改 `web/scripts/ui-contracts/types.mjs`、`web/scripts/check-ui-contracts.mjs`、`web/scripts/check-ui-contracts.test.mjs`、`web/scripts/ui-contract-exceptions.json`。

**接口：** `collectGridTableCellViolations({files, emitFor})` 接收检查器已读取的文件列表（相对路径、源码、SFC 分段），复用 `css-vars.mjs` 的 `parseRules`/`parseDeclarations` 产出既有 `Violation` 结构；规则名固定为 `grid-table-row-height`、`grid-table-padding`、`grid-table-align`（三条，最终命名以 Task 1 文档为准）、守卫规则名固定为 `table-without-cell-contract`。守卫复用 `vue-source.mjs` 的 `findTags` / `findTags("div"|"section")` + `hasAttribute` 检测表格语义。`visible-input-label` 在 `check-ui-contracts.mjs` 的组件化输入分支新增第四条合法形态（`aria-labelledby` → 可见 `role="columnheader"`），**不新增规则名**，因此规则集合计数不变、只增分类与注入计数。

**结构配对的落地形式（与 PLAN-DM-043 同口径）：** grid 表的「结构性零 padding」等跨组件条件不进 `ui-contract-exceptions.json`（该文件条目被 `REQUIRED_EXCEPTION_FIELDS` 固定），仍在模块内以常量表表达（形如 `{file, rowSelector, tableSelector, requiredToken}` 的精确条目）。

- [ ] **Step 1（RED）**：在临时 Vue/CSS 夹具写用例：语义化 grid 表的行容器缺 `align-items`、行容器使用裸非零 padding、同表表头行与数据行两档 padding、行容器未声明行高档、模板含表格语义却无任何对应样式规则（守卫命中）均失败；`visible-input-label` 第四形态的**五条反向用例**——`aria-labelledby` 指向不存在元素、指向元素无可见文字、指向元素非列头（既非 `role="columnheader"` 也不在 `role="row"`/`.columns-head` 列头行内）、控件同时传 `label` 与 `aria-labelledby` 造成双重标签、指向元素为纯图标操作列头（无可访问名）——也须失败，正向用例（指向可见列头 `id`，含带 `role` 与不带 `role` 的 `.columns-head` 两种形态）通过；4 个真实组件的现状（未加语义标记）下守卫不误报、规则不产生虚假命中。运行 `rtk npm --prefix web run test:contracts`，确认目标用例 RED。
- [ ] **Step 2（GREEN）**：实现 `grid-table-cells.mjs`（三条规则 + 模块内配对常量）与 `table-without-cell-contract.mjs`（守卫），接入 `types.mjs` 的 `RULE` 与 `check-ui-contracts.mjs` 的扫描链（新增第几遍扫描按文件现有编号顺延）；在组件化输入分支实现 `visible-input-label` 第四形态，判定条件严格取「指向元素存在 + 该元素有可见文字 + 该元素是列头」三项同时成立（列头判定含 `role="columnheader"` 与 `role="row"`/`.columns-head` 两条路径）。注意：规则只看**已声明的**行/选择器规则，真实几何由浏览器测试覆盖；守卫只看模板事实。
- [ ] **Step 3（棘轮与基线）**：先量取并登记 4 个组件的现状（表头/数据行计算行高、padding、`align-items`、`grid-template-columns`、是否落在 44px 档），把存量违规按「文件 + 稳定语义」登记到 `ui-contract-exceptions.json`，每条写明迁移任务与到期条件；守卫的存量命中数必须实测为 0（不为 0 则在此列出清退任务，不得登记例外放行）。注入每种规则的变异夹具，并入 `check-ui-contracts.test.mjs` 的 CLI 级变异清单并同步分类数/注入数/规则集合三处计数。
- [ ] **Step 4（验证/提交）**：运行 `rtk npm --prefix web run test:contracts` 与 `rtk npm --prefix web run check:ui`；只提交本任务文件及本次 `changelog.md` 记录，提交信息：`建立网格伪表格静态门禁`。

### Task 3：标准平台三张伪表格的语义标记与几何收口

**Files:** `web/src/components/standards/EnumValuesDialog.vue`、`web/src/components/standards/MappingPropertyDialog.vue`、`web/src/components/standards/DerivedPropertyEditor.vue`、`web/tests/e2e/standards-editor.spec.ts`、`web/tests/e2e/standards-visual-evidence.spec.ts`、`web/scripts/ui-contract-exceptions.json`。

**Interfaces:** 三组件的表头容器/数据行容器补 `role="row"`、列标题项补 `role="columnheader"`、行内列项补 `role="cell"`；在 scoped 样式里显式声明行高档（`height:var(--sheet-table-row-height)`）、单档令牌化 `padding`、行容器 `align-items`。**三张表全部按方案 C 取消双重表头**：每个 `role="columnheader"` 显式声明稳定 `id`（形如 `enum-col-value`、`mapping-col-target`、`derived-col-name`/`derived-col-scope`/`derived-col-kind`/`derived-col-description`），行内 `UiInput` 移除 `label`（`DerivedPropertyEditor` 连同其 `aria-label` 一并移除）并改为 `:aria-labelledby="<对应列头 id>"`。`DerivedPropertyEditor` 额外要求：移除 `.derived-head` 的 `aria-hidden="true"`（保留各列 `id`/`role`）、删除 `.derived-row :deep(.ui-input__label){display:none}` 与 `:deep(.ui-input){gap:0}` 这两条为"隐藏标签"存在的规则、纯操作列不参与 `aria-labelledby`、1050px/780px 被隐藏列的列头 `id` 仍留在 DOM。其响应式隐藏列行为与 `align-items:start` 取舍必须先量取再改。

- [ ] **Step 1（RED）**：在 `standards-editor.spec.ts` 断言三张表的表头行与普通数据行（a）计算高度 ≥44px 且消费 44px 档（同一断言处钉令牌名与绝对值 `44px`）、（b）行容器计算 `align-items` 为显式声明值、（c）普通格/行 padding 为令牌化单档、（d）同一行内输入框、图标按钮与序号的中点差 ≤1px。**同时新增双重表头取消的断言**：（e）三张表内 `.ui-input__label` 元素计数为 0；（f）行内每个 `UiInput` 的可访问名称等于对应列头文字（`getByLabel("<列头文字>")` 命中该行控件，同一列每行命中且仅命中一次）。**并改写既有断言**：`standards-editor.spec.ts` 现第 168–170 行「`derived-table` 内 `label` 计数 > 0 且首项隐藏」是"仅视觉隐藏"口径的断言，方案 C 下必须改为「`derived-table` 内 `label` 计数为 0、行内控件 `getByLabel("属性名")` 仍命中」；`ordinary-table` 的同类断言（第 160–165 行）保持不动。先跑一次并记录"当前 `getByLabel('枚举值')` 命中 = 行数×2、`derived-table` label 计数 = 行数×1"作为 RED 证据，再改代码。运行目标 e2e 确认 RED。
- [ ] **Step 2（GREEN）**：补语义标记与 scoped 样式；按方案 C 移除三张表行内 `UiInput` 的 `label` 并接 `aria-labelledby`；`.enum-head,.enum-row` 与 `.mapping-head,.mapping-row` 共用同一 `grid-template-columns` 的定义不得拆分成两套轨道；派生属性表移除 `aria-hidden` 与两条"隐藏标签"规则后，必须复跑 `standards-editor.spec.ts` 的 900×768 用例（第 173–193 行）确认隐藏说明列仍隐藏**整个网格项**、行内子项数与列数一致（原 `:deep(.ui-input){gap:0}` 被删后 `.ui-input` 的 `gap` 变化可能影响行高，需一并量取）。改动后必须复跑 `check:ui`，确认新形态被 `visible-input-label` 第四形态正确放行（若报违规，说明 Task 2 的第四形态实现或 `id` 拼写不一致，先修门禁/拼写而不是回退 `label`）。
- [ ] **Step 3（验证/提交）**：运行两份目标 e2e、`rtk npm --prefix web run check:ui` 与生产构建；核对 900×768 与 1440×900 下无页面级横溢、模态内横向滚动行为不变；核对全仓无 `getByLabel('枚举值')`/`getByLabel('目标值')`/`getByLabel('属性名')`（派生表内）依赖可见文案的既有断言被打破（如有，改为 `data-testid` 定位并说明）；跑一次 axe 扫描确认列头不再 `aria-hidden` 后无新增 Critical/Serious 问题与重复播报；按全局约束的「列头 `aria-hidden` 与 `aria-labelledby` 共存规则」记录实际采用的语义集合；清退对应例外，提交信息：`收口标准平台网格表格对齐并取消双重表头`。

### Task 4：目录列编辑器的几何与轨道对齐收口

**Files:** `web/src/components/sheet-catalog/ColumnEditor.vue`、`web/tests/e2e/sheet-catalog.spec.ts`、`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`、`web/scripts/ui-contract-exceptions.json`。

**Interfaces:** 本轮**不新增 ARIA 角色**（理由见全局约束），只复用既有 `data-testid` 与 `.columns-head`/`.column-row` 选择器；按 Task 6 裁决结果决定该表是进入门禁范围还是登记为有到期条件的例外。若进入范围，则显式声明行高档、单档令牌化 padding 与行容器 `align-items`，并保持 ≤720px 隐藏表头、≤某断点单列化的既有响应式行为。

**双重表头改造（方案 C 扩围，2026-09-27 用户裁决）：** 该表与枚举值/映射属性/派生属性同属"列头 + 行内重复标签"形态（列头「列名」「表达式」，行内 `UiInput` 的 `label` 为「输出列名 N」「表达式 N」）。改造要求：① 删除行内 `UiInput` 的可见标签——**不再传 `label`**，因此为该表 `:deep(...)` 或组件内的"隐藏标签"样式无需新增，但需核查 `ColumnEditor.vue` 是否已有同类隐藏规则并一并清理；② 行内可访问名取「**列头文字 + 行号补足**」（用户裁决）：即以 `aria-labelledby` 指向同列列头 `id`（列头文字保持「列名」/「表达式」），并以 `aria-describedby` 或行内既有说明元素补足行号，使读屏得到「列名，第 1 列」而非五行同报「列名」；③ 列头 `.columns-head` 的列项显式声明稳定 `id`（形如 `catalog-col-header`/`catalog-col-expression`），行内 `UiInput`/textarea 的 `aria-labelledby` 指向对应列头；④ 列头在 ≤720px 被隐藏时其 `id` 必须仍在 DOM（`display:none` 元素仍可被引用），不得连带删除或改为条件渲染。

- [ ] **Step 1（RED）**：在 `sheet-catalog.spec.ts` 断言 `.columns-head` 与 `.column-row` 共用同一 `grid-template-columns`（既有 e2e 已覆盖列轨道一致，此处补行高/`align-items`/padding 断言），断言表头列名与行内数据项在各自轨道内的对齐方向一致；**并新增双重表头取消断言**：（a）`.column-row` 内 `.ui-input__label` 元素计数为 0；（b）行内控件的可访问名来自列头（`getByLabel("列名")` 或按其裁决后的最终名称命中，且行号补足信息存在）；（c）列头 `id` 在 ≤720px 表头隐藏时仍存在于 DOM。**并记录既有定位现状**：全仓 `getByLabel("输出列名 1")` / `getByLabel(/^输出列名 \d+$/)` / `getByLabel("Column header 1")` 的命中数与断言原文（`sheet-catalog.spec.ts` 有 20+ 处，含第 339 行的批量断言），作为 RED 证据与改写清单。运行目标 e2e 确认 RED。
- [ ] **Step 2（GREEN）**：在 scoped 样式补显式行高档与令牌化 padding、行容器 `align-items`；按方案 C 移除行内可见标签并接 `aria-labelledby` + 行号补足；不改 `.columns-head` 五列轨道定义、不改表达式格 textarea 行数、不改列操作轨宽度（112px）、不改 `columnHeader` i18n 文案语义（若需调整可访问名文案，同步更新中英文值与断言）。
- [ ] **Step 3（验证/提交）**：逐一核对 Step 1 记录的 20+ 处 `getByLabel` 定位，按裁决后的最终可访问名改写或改为 `data-testid` 定位并说明理由；运行两份目标 e2e 与 `check:ui`、生产构建；确认 ≤720px 响应式表头隐藏、单列化与 112px 操作轨行为未回归；清退对应例外；提交信息：`收口目录列编辑器网格表格对齐并取消双重表头`。

### Task 5：语义化表格守卫与存量覆盖确认

**Files:** `web/scripts/ui-contracts/table-without-cell-contract.mjs`、`web/scripts/check-ui-contracts.mjs`、`web/scripts/check-ui-contracts.test.mjs`、`web/scripts/ui-contract-exceptions.json`、[`.planning/todos/dst-manager/2026-09-26-new-table-guard-and-cell-gate-boundary.md`](../../todos/dst-manager/2026-09-26-new-table-guard-and-cell-gate-boundary.md)。

- [ ] **Step 1（RED）**：为守卫补 CLI 级变异用例：新增含 `<table>` 或表格语义却没有任何对应样式规则的临时组件 → `check:ui` 退出 1；补齐规则后退出 0。同时复用待办中的**探针 B（新表无规则）**与**探针 A（class-only 绕过）**确认两者在守卫实施后的真实结果，并把实测结论写入本计划执行记录。
- [ ] **Step 2（GREEN）**：实现守卫并接入扫描链；确认 4 张 grid 表 + 18 张真实表的存量命中数为 0。
- [ ] **Step 3（待办交接）**：在待办的「待处理」第 1 项标注「由 PLAN-DM-044 承接（守卫已实现），本项关闭」，其余第 2–5 项保持待办状态并注明仍未被任何计划承接；提交信息：`补齐语义化表格规则守卫`。

### Task 6：目录列编辑器门禁口径裁决与全量验证

**Files:** 按 Task 4 结论落到 `web/scripts/ui-contracts/grid-table-cells.mjs`（模块内配对/范围常量）或 `ui-contract-exceptions.json`，以及 `web/tests/e2e/sheet-catalog*.spec.ts`、`changelog.md`。

- [ ] **Step 1（裁决）**：按 Task 2 实测基线裁决 `ColumnEditor.vue` 是否进入 `grid-table-*` 门禁范围：若其 `align-items`/padding/行高可无损落档则纳入；若纳入会导致既有响应式列隐藏或 112px 操作轨回归，则**登记为有到期条件的例外**（到期条件写「下一次目录页视觉 Spec 修订」），并在计划与提交说明中写明理由与证据，不得静默不覆盖。
- [ ] **Step 2（全量验证）**：运行 `rtk npm --prefix web run test:contracts`、`test:unit`、`build`、`test:e2e`，以及 `rtk uv run ruff check .` 与受影响的 pytest（若无 Python 改动，记录无相关用例）；确认 `check:ui` 退出 0 且例外清单无本计划到期项、既有 10 条例外指纹未变。
- [ ] **Step 3（缺口登记）**：补 100/125/150/200% Windows WebView2 的代表性模态/编辑页人工复验；环境缺失时按 ARCH-DM-007 §12 **保持 `active`** 并明记缺口，不声称通过；提交信息：`完成网格伪表格对齐契约收口`。

## 风险与处置

- **规范与实现的一致性风险**：`grid-table-*` 规则如果先于规范修订落地，就会出现「门禁比规范严」的矛盾。处置：Task 1 必须先于 Task 2，且规则名以 Task 1 定稿为准。
- **语义标记的可访问性风险**：给 grid 容器加 `role="row"`/`role="cell"` 可能与既有 axe 扫描、基准 Demo 可访问名比较或 `[role="dialog"]` 计数断言冲突（`ExtensionSettingsHost.vue` 已有同类注释）。处置：Task 3 实施时先跑目标 e2e 与 axe 断言，出现冲突时优先只保留 `role="row"`/`role="columnheader"`/`role="cell"` 中的最小必要集合，并在执行记录中登记实际采用集合。
- **取消双重表头带来的定位回归风险（方案 C 特有）**：移除行内 `label` 会同时移除 `label[for]` 与 `id` 的关联路径，若既有 e2e 以 `getByLabel("枚举值")` 之类可见文案定位行内输入，会变成"命中列头 + 多行控件"的歧义定位而失败。处置：Task 3 Step 1 先记录现状命中数量作为 RED 证据，Step 3 逐一核对并改为 `data-testid` 定位；**不得为了保住旧定位而回退方案 C**（`data-testid` 本就已存在，改造成本低于保留双重标签的可访问性代价）。
- **门禁第四形态被放水风险**：`visible-input-label` 新增的 `aria-labelledby` 形态若实现为"有 `aria-labelledby` 即通过"，会让任意无可见标签的控件蒙混过关。处置：Task 2 Step 1 必须同时写正向与五条反向用例，Task 3 / Task 4 的 Step 3 复核 `check:ui` 在移除 `label` 后**不是**因为门禁被放宽才通过；Task 5 的变异清单须包含第四形态的反向注入。
- **`ColumnEditor` 双重表头改造的既有定位风险（方案 C 扩围特有）**：`sheet-catalog.spec.ts` 有 **20+ 处** `getByLabel("输出列名 N")` / `getByLabel(/^输出列名 \d+$/)` / `getByLabel("Column header 1")` 定位（含第 339 行的批量断言），且行内旧名（「输出列名 1」）与列头文字（「列名」）**不同名**。取「列头文字 + 行号补足」后，可访问名将从「输出列名 1」变为「列名 + 第 N 列」类组合，这些定位**大概率失配**。处置：Task 4 Step 1 必须先记录这 20+ 处的命中数与原文清单作为 RED 证据，Step 3 逐条核对——优先改为已存在的 `data-testid` 定位；若某处必须依赖可访问名，则按最终名称改写并同步中英文（`Column header N` 对应英文路径）。**不得为保住旧定位而回退方案 C**；同时不得改动 `columnHeader` i18n 的语义（其仍是用户可见的列名占位文案，仅可见性由「标签」改为「列头 + 行号补足」）。
- **`ColumnEditor` 无 ARIA 角色与门禁第四形态的适配**：该表按全局约束**不新增** `role="columnheader"`，若门禁第四形态只认 `role="columnheader"`，改造后 `check:ui` 会误报。处置：Task 2 Step 2 的列头判定必须实现两条路径（`role="columnheader"` 或 `role="row"`/`.columns-head` 列头行内），并在 Step 1 写清「不带 `role` 的 `.columns-head` 正向用例」，防止扩围后门禁把 `ColumnEditor` 判红。
- **`DerivedPropertyEditor` 改造的既有断言冲突（方案 C 扩围特有）**：该表当前的可访问性口径是「列头 `aria-hidden` + 行内 `aria-label`/隐藏 `label`」，且 `standards-editor.spec.ts` 第 168–170 行**直接断言**了"`derived-table` 内 `label` 计数 > 0 且首项隐藏"、第 291–292 与 718–719 行以 `getByLabel("属性名")`/`getByLabel("作用域")` 定位行内控件。改为方案 C 后：① 前一条断言必须改写为「count 为 0」；② 后两条定位依赖可访问名不变——`aria-labelledby` 指向的列头文字与现 `aria-label` 文字一致（「属性名」「作用域」「类型」「说明」）时仍可命中。已核实门禁边界（[check-ui-contracts.mjs](file:///c:/Users/sonic/autocad-sheetset/web/scripts/check-ui-contracts.mjs#L449-L528)）：`visible-input-label` 只扫裸 `<input>` 与 `UiInput`/`UiSelect` 调用点，**不扫裸 `<select>`**——作用域列的 `<select class="cell-select" aria-label="作用域">` 因此不受第四形态约束，本轮**保留其 `aria-label` 即可**，但该列若同时存在列头文字，须人工确认不构成视觉双重表头（`select` 无 `label` 元素，不存在 `.ui-input__label` 重复问题）。处置：Step 1 必须先跑一次现状并记录两条定位的实际命中数与断言原文，Step 3 逐条核对改写，**不得为保住旧断言而放弃扩围**。
- **`DerivedPropertyEditor` 的 `aria-hidden` 移除风险**：列头去掉 `aria-hidden` 后，读屏会在进入每行前播报列标题，可能与基准 Demo 的对照结论不一致或造成重复播报（行内控件已通过 `aria-labelledby` 引用同一文字）。处置：Task 3 Step 3 跑 axe 并做一次读屏人工走查（环境缺失时登记缺口），若确认重复播报，按全局约束的最小必要集合裁决——保留 `role="columnheader"`/`id`，仅对纯操作列恢复 `aria-hidden`，并在执行记录登记实际集合。
- **`DerivedPropertyEditor` 的高度不确定性**：`.derived-row` 为 `align-items:start` 且含 `.row-issue` 错误行与 2 行 textarea，无法断言恰好 44px。处置：统一采用「≥44px 且消费该档」，并单独断言错误行不裁切、隐藏列在 1050px/780px 断点行为不变；删除 `:deep(.ui-input){gap:0}` 后须重新量取行高，不得沿用改造前的基线值。
- **`ColumnEditor.vue` 的既有 Bases**：其 ↑/↓/✕ 三个 Unicode 图标例外与 112px 操作轨是 PLAN-DM-023 A1 的已批准裁决，本计划不得借对齐收口之名改写；Task 4/6 只改行几何与对齐，不动操作轨与图标形态。
- **守卫的误报风险**：`table-without-cell-contract` 若把 `<table>` 与「表格语义」混在一个判定里，可能对只做语义标注、样式全在父级的组件误报。处置：守卫判定限定「组件模板含 `<table>` 或表格语义，且该组件（含父级全局样式表）没有任何对应行列规则」，先以裸检查器确认全仓命中为 0 再并入变异清单。
- **内容驱动高度与滚动**：`EnumValuesDialog` 与 `MappingPropertyDialog` 的正文滚动、`DerivedPropertyEditor` 的分级响应式可能改变可见列数与行高。处置：保持既有滚动与隐藏行为，长文本、错误态与缩放逐档检查，不把截图差异直接当作业务回归。

## 验证命令

- 静态规则和变异：`rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run check:ui`。
- 前端回归与构建：各任务列明的 `rtk npm --prefix web run test:e2e -- tests/e2e/<目标文件>.spec.ts`；最终运行 `rtk npm --prefix web run test:unit`、`rtk npm --prefix web run build`、`rtk npm --prefix web run test:e2e`。
- 仓库检查：`rtk uv run ruff check .`、`rtk git diff --check`；若实施中修改 Python，再运行相关 pytest，且不以 Ruff 代替测试。

## 完成标准与实际验证

- [ ] Task 1 的规范增量修订已落地（含「列头即可访问名 / 禁止双重表头」条款），规则名与 ARCH-DM-007 §9.1 门禁条目一致。
- [ ] 4 张 grid 表的语义标记、行高档、单档令牌化 padding 与行轨道对齐逐个有 Playwright 计算样式证据；`ColumnEditor.vue` 的纳入或例外裁决有明确理由与证据。
- [ ] **双重表头已取消**：`EnumValuesDialog`、`MappingPropertyDialog`、`DerivedPropertyEditor`、`ColumnEditor` 行内 `.ui-input__label` 元素计数均为 0，行内控件可访问名称来自同列列头；`ColumnEditor` 的「列头文字 + 行号补足」使读屏不出现 N 行同报同一名称；`OrdinaryPropertyEditor` 与 `GroupsStep` 的"仅视觉隐藏"路径未回退；`standards-editor.spec.ts` 中原「派生表 label 计数 > 0 且隐藏」的断言与 `sheet-catalog.spec.ts` 中 20+ 处 `getByLabel("输出列名 N")` 定位均已按新口径核对改写并通过。
- [ ] `grid-table-*`、`table-without-cell-contract` 规则与 `visible-input-label` 第四形态（含三条反向变体）、守卫与 CLI 级变异测试通过；全量 `test:contracts`、`test:unit`、`build`、`test:e2e` 与 `check:ui` 通过；例外清单只含 PLAN-DM-029/023 遗留项与（如裁决需要）本计划的新增到期项，无过期条目。
- [ ] 待办 `2026-09-26-new-table-guard-and-cell-gate-boundary.md` 第 1 项已标注由本计划承接并关闭，第 2–5 项状态已更新。
- [ ] 真实 Windows WebView2 100/125/150/200% 复验通过后才把状态改为 `completed`（[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §12）；桌面复验缺失时保持 `active` 并把缺口写入下表，不得以自动化证据代替真实缩放结论；实施期间保持 `active`，未开始前保持 `proposed`。

| 日期 | Task | RED 证据 | GREEN 与回归命令/结果 | 仍待验证 |
| --- | --- | --- | --- | --- |
| 待填 | | | | |

## 修订记录

- 2026-09-27 首版（proposed）：依据用户对「grid 伪表格是否属于表格对齐契约」的核查结论起草。范围裁决为语义标记 + 门禁扩展、4 张伪表格全收、守卫一并纳入；明确与 PLAN-DM-043（真实 `<table>`，11 组件 / 18 张表）互不重叠，并把 `ColumnEditor.vue` 的门禁口径裁决单列为 Task 6，避免在范围上做出无证据的承诺。
- 2026-09-27 修订（方案 C，用户裁决）：明确**取消双重表头**——`EnumValuesDialog` 与 `MappingPropertyDialog` 行内不再渲染重复字段标签，可访问名称改由同列 `role="columnheader"` 经 `aria-labelledby` 承担；相应扩展 `visible-input-label` 门禁第四种合法形态（严格三条件，含三条反向变异用例），并在 Task 1 增列规范条款、Task 2 增列门禁实现、Task 3 增列 RED/GREEN 断言与定位回归核对、Review Focus/完成标准/风险新增对应条目。原「保留 label、仅视觉隐藏」的处置仅保留给既有表格；`DerivedPropertyEditor.vue`（列头 `aria-hidden`）本轮不随方案 C 改造，差异已在风险中登记。
- 2026-09-27 修订二（方案 C 扩围，用户追加裁决）：把 `DerivedPropertyEditor.vue` **纳入**方案 C 改造范围，三张 grid 表口径统一。相应新增「列头 `aria-hidden` 与 `aria-labelledby` 共存规则」（移除列头 `aria-hidden`、保留 `id`/`role`、删除两条"隐藏标签"规则、被隐藏列的 `id` 仍在 DOM、空操作列可不参与可访问名），Task 3 的 Interfaces/Step 1/Step 2/Step 3 全部改写（含把 `standards-editor.spec.ts` 第 168–170 行「`label` 计数 > 0 且隐藏」的既有断言按新口径改写、复跑 900×768 网格项隐藏用例、axe 与读屏走查），风险条替换为「既有断言冲突」「`aria-hidden` 移除」「删 `gap:0` 后重新量取行高」三项。原「派生表不改造」的说明与对应完成标准条目已删除。
- 2026-09-27 修订三（方案 C 二次扩围，用户追加裁决）：把 `ColumnEditor.vue`（图纸目录插件的输出列编辑器）**纳入**双重表头改造——截图确认其列头「列名」/「表达式」与行内「输出列名 N」/「表达式 N」构成双重表头，而 Task 4 原稿只安排了几何与轨道对齐，属计划缺口。按用户裁决取「**列头文字 + 行号补足**」（`aria-labelledby` 指向列头，另以 `aria-describedby` 补行号，避免 N 行同报「列名」），并把改造落到 Task 4 的 Interfaces 与三个 Step（含记录并核对 `sheet-catalog.spec.ts` 20+ 处 `getByLabel("输出列名 N")` 定位、≤720px 表头隐藏时列头 `id` 仍留在 DOM）。同时修正门禁第四形态的判定条件：由「必须 `role="columnheader"`」放宽为「`role="columnheader"` 或位于 `role="row"`/`.columns-head` 列头行内」两条路径之一，以适配 `ColumnEditor` 不新增 ARIA 角色的既有裁决，并把反向用例从三条扩到五条。范围由三张表扩为**四张**，相应更新范围裁决、Review Focus、完成标准与两条新增风险。
