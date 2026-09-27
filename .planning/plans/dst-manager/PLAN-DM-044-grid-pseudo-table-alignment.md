---
id: PLAN-DM-044
title: 语义化 grid 伪表格对齐契约收口实施计划
status: active
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

**目标：** 把 4 个用户可见、以 CSS grid 模拟表格的组件（`EnumValuesDialog.vue`、`MappingPropertyDialog.vue`、`DerivedPropertyEditor.vue`、`ColumnEditor.vue`）纳入 [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.4 的单元格对齐契约：四张表都具备完整的 `table → row → columnheader/cell` 语义与实例级稳定锚点，再新增一组 `grid-table-*` 静态规则要求其表头/数据行取明确行高档、令牌化单档 padding 与显式对齐，并由 Playwright 断言真实几何；同时补齐按每张表根节点核对的 `check:ui` 守卫，堵住在已有组件中新增无规则表格也能静默回退的缺口。

**架构：** 沿用 PLAN-DM-043 建成的两层验证：静态层扩展现有 CSS 规则/声明解析与例外棘轮（新增 `grid-table-*` 规则与逐表 `table-without-cell-contract` 守卫），计算样式层由 Playwright 在同一断言处钉令牌名与计算绝对值。语义采用 `role="table"` 而非需要新增方向键导航的 `role="grid"`；枚举与映射弹窗为表头及数据行增加最小包裹容器，其他表复用现有容器。不引入新表格框架、不新增 44px 令牌。

**技术栈：** Windows 11、Vue 3、TypeScript、Vite、Node.js 内置 `node:test`、Vitest、Playwright、CSS 自定义属性；Python 仅运行既有 Ruff/pytest 回归。

**规范依据（本轮需增量修订的正文，见 Task 1）：** 用户可见口径以 [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.4 为唯一权威；实现与门禁边界见 [ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §4.3/§9.1/§9.3。现有两处正文只以 `th/td` 表述表格，需以**增量条款**（不静默改写既有条目）补入「语义化 grid 表格」口径，否则本计划的静态规则会与已接受规范正文矛盾。派生属性表还须遵守 [SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md) 的编辑器 Demo 与分级响应式（1050px/780px 隐藏说明列与源摘要列），目录列编辑器须遵守 SPEC-DM-023 系列既有列轨道约定。

**与 PLAN-DM-043 的关系：** PLAN-DM-043 收口的是真实 `<table>` 组件（11 组件 / 18 张表），本计划收口 **grid 伪表格**，两者不重叠、不互相取代。PLAN-DM-043 已删除 `legacy.css` 的 `:where(#app) th,:where(#app) td` 兜底，本计划的 grid 表格**从未**依赖该规则（其几何全部来自组件自身 scoped 样式），因此本计划不重新引入任何全局兜底。

**双重表头取消裁决（2026-09-27 用户确认，方案 C「列头即标签」）：** 本计划取消四张 grid 表在**列头可见时**于每个单元格重复渲染的字段标签（枚举值、目标值、派生属性字段、目录列名与表达式）。行内控件不再传 `label`，以 `aria-labelledby` 关联同列 `role="columnheader"` 的实例级 `id`；`ColumnEditor` 还把行号纳入名称。≤720px 该表隐藏列头时，为视觉用户显示仅该断点可见、从辅助技术树隐藏的行内列名，保证同一时刻不出现双重可见标签。四张表仍统一取列头作为可访问名来源；既有 `OrdinaryPropertyEditor` / `GroupsStep` 的「仅视觉隐藏」路径不改。移除 `label` 后需扩展 `visible-input-label` 门禁第四形态，见 Task 2。

**范围裁决（2026-09-27 用户确认）：** ① 路线取「**语义标记 + 门禁扩展**」——保留现有 grid 实现，给伪表格补显式表格语义，`check:ui` 新增 grid 表规则，同步增量修订规范正文；不采用「改造为真实 `<table>`」（DOM 重写会牵动 aria、键盘模型、粘性表头、响应式隐藏列与既有 e2e，回归面最大），也不采用「只做视觉整改 + 断言」（无法阻止新增伪表格静默回退）。② 覆盖 **4 张全收**：枚举值弹窗、映射属性弹窗、派生属性表、目录列编辑器。③ 「语义化表格必须声明契约规则」的守卫**一并纳入**本计划（原载体为 [2026-09-26-new-table-guard-and-cell-gate-boundary.md](../../todos/dst-manager/2026-09-26-new-table-guard-and-cell-gate-boundary.md) 第 1 项），实施时把该项标记为「由 PLAN-DM-044 承接」，其第 2–5 项仍留待办。

## 前置条件

- SPEC-DM-006 §6.4 与 ARCH-DM-007 §4.3/§9 的现行修订（含 PLAN-DM-043 的 2026-09-26 增补）是实施基准；实施前先通读两处正文与 PLAN-DM-043 的 Task 1–5 执行记录，确认口径后再写 RED。
- 实施前确认 `web/` 依赖可用，并用裸检查器（`node scripts/check-ui-contracts.mjs`）取得 `ui-contract-exceptions.json` 的现存条目数基线（当前 10 条例外 + 1 条动态变量），作为棘轮对照；不得凭源码推断存量违规数。
- Task 2 的迁移基线必须**一次量取全部 4 个组件**的表头行/数据行的现状计算值（行高、padding、`align-items`、列轨道模板），作为 Task 3–6 的 RED 依据与最终命中证据。
- 本计划为前端视觉、语义与静态门禁调整，不需要真实 AutoCAD 作为实施前置条件；最终桌面缩放复验需要 Windows WebView2，缺失时记录证据缺口并**保持 `active`**（[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §12），不得据此宣布验收通过。

## 全局约束

- 任务开始前检查 `rtk git status --short`，保留用户已有改动；只暂存本任务文件。每次实际代码修改同步更新根 `changelog.md`，提交信息用简体中文动词短语。
- **不改** HTTP/SSE、后端校验、字段含义、props/emits、i18n key、焦点管理与键盘模型；**不改** `ColumnEditor.vue` 与 `DerivedPropertyEditor.vue` 的响应式断点行为（1050px 隐藏说明列、780px 隐藏源摘要列、≤720px 隐藏表头等既有约定必须保持）。≤720px 隐藏表头时，`ColumnEditor.vue` 必须为每个可编辑字段显示仅在该断点可见的行内列名；这不是桌面态重复标签。
- **不改** 已清退的例外表语义：既有的 `unicode-structure-icon`（`ColumnEditor.vue` 的 ↑/↓/✕、`GroupsStep.vue`、`RevisionHistoryPanel.vue` 的 `→`、`SheetToolbar.vue` 的 ✕）与 `visible-input-label` 条目不得因本计划改写或删除；本计划只新增自身到期条件的条目。
- grid 伪表格的普通行基础档取与同类真实表一致的 `44px`（消费既有 `--sheet-table-row-height`）；若某张 grid 表实测内容高度超过 44px（`DerivedPropertyEditor` 的 `.derived-row` 为 `align-items:start` 且含错误行，`ColumnEditor` 的表达式格为 2 行 textarea），则取「**≥44px 且消费该档**」，不断言恰好 44px，也不压到 44px 以下。普通 `padding` 统一取 `var(--space-2)`（8px）单档；`EnumValuesDialog`/`MappingPropertyDialog` 允许改用 `var(--space-1)`（4px），但同一张表内必须单档且令牌化，且必须在 Task 2 基线量取后按实测决定，不得两种混用。
- 表头行与同表普通数据行**同档同 padding**；表头对齐方向与其列数据一致（文本列左、可比较数值列右 + `tabular-nums`、纯图标操作列可右/居中）；grid 表**没有** `vertical-align`，对应的垂直对齐约束改由行轨道对齐表达：行的 `align-items` 必须显式声明（`center` 为默认；仅多行长文本格允许 `start`），禁止依赖浏览器默认 `stretch`。
- 语义标记形态（本轮审查修正）：四张表统一取 `role="table"` 根容器、`role="row"` 表头与数据行、`role="columnheader"` 列头项、`role="cell"` 数据项；纯操作列也保留结构角色，但其按钮仍以自身 `aria-label` 命名。`DerivedPropertyEditor.vue` 的 `.derived-list` 可直接作表根；`ColumnEditor.vue` 的 `.columns` 作表根，`.column-list` 取 `role="rowgroup"` 以覆盖现有 `ol/li`；枚举与映射弹窗只为表头及重复行增加专用表根，说明、源选择和新增按钮留在表根外。**不使用 `role="grid"`**，保持既有 Tab 遍历；不得通过删减必要角色来压过 axe 报错。此前“`ColumnEditor` 不新增 ARIA 角色”裁决与“四张语义化表全收”冲突，本次以完整语义树修正，实施时用基准 Demo、axe 与读屏实测确认。
- **列头可访问名契约（方案 C，本计划强制）：** 行内控件的可访问名称来自同列列头；`ColumnEditor` 的名称还包含行号。① 每个表实例使用 `nextInstanceId()` 生成唯一前缀，再生成同一实例的列头 `id`；列头采用 `:id="nameHeaderId"`、控件采用 `:aria-labelledby="nameHeaderId"` 这类**同一绑定表达式**，不得写固定页面级 `id`。② 行内 `UiInput` 不再传 `label`，`UiInput` 的 `$attrs` 透传到真实 `<input>`；裸 `<textarea>` 同理引用列头。③ 四张表行内均不得出现 `.ui-input__label`；纯操作列不参与输入可访问名。④ `ColumnEditor` 的每行序号文本有实例内唯一 `id`，列名与表达式控件的 `aria-labelledby` 按顺序同时引用列头 `id` 和该行序号 `id`，使计算出的**名称**分别包含“列名/表达式 + 第 N 列”；`aria-describedby` 只用于补充描述或错误信息，不能代替名称中的行号。⑤ ≤720px 行内另显示与列头同文案的纯视觉标签，桌面态隐藏；该标签 `aria-hidden="true"`，表头在窄屏虽 `display:none` 但仍保留在 DOM 并由 `aria-labelledby` 引用。⑥ `ColumnEditor.vue` 当前没有可复用的 `data-testid`，Task 4 必须先新增实例内稳定的行/控件锚点，再迁移旧 `getByLabel` 定位。
- **列头 `aria-hidden` 与 `aria-labelledby` 的共存规则（`DerivedPropertyEditor` 专用裁决）：** 该表列头当前为 `aria-hidden="true"`（列标题仅视觉呈现，可访问名由行内 `aria-label` 承担）。本轮取方案 C 后，列头必须同时是「可见文字」与「可访问名来源」，因此：① 移除列头容器的 `aria-hidden="true"`，但**保留**每个列项自身的 `id` 与 `role="columnheader"`；② 行内 `UiInput` 的 `aria-label` 与 `label` 一并移除，改由 `aria-labelledby` 指向同列列头；③ 行内非输入格（`.source-summary`、`.scope-locked`、`UiButton`/`UiIconButton`）不参与 `aria-labelledby`，其可访问名保持现状；④ `.derived-head` 的 `:nth-child(5)`/`:nth-child(3)` 响应式隐藏（1050px/780px）**只隐藏视觉**，被隐藏列的列头 `id` 必须仍在 DOM 中（`display:none` 元素仍可被 `aria-labelledby` 引用），不得连带删除 `id` 或改用条件渲染。若实测发现 `aria-hidden` 移除会让读屏重复播报列标题（与基准 Demo 对照不符），按 Task 3 Step 3 的最小必要集合裁决：优先保留 `role="columnheader"` 与 `id`、仅对**空列**（纯操作列）恢复 `aria-hidden`，并在执行记录中登记实际采用集合。
- **门禁口径扩展（`visible-input-label` 第四种合法形态）：** 现有三条合法形态不放宽（见 `check-ui-contracts.mjs` 的组件化输入分支）。第四形态要求控件的 `aria-labelledby` 至少引用同组件模板内、位于 `role="table"`/`role="row"` 语义树中的 `role="columnheader"`：列头必须存在并有可见文字（复用 `hasVisibleText`）；可附加同一行的序号 `id`，但该序号不得替代列头。静态配对接受字面量属性（`id="x"`/`aria-labelledby="x"`）、同一绑定表达式（`:id="nameHeaderId"`/`:aria-labelledby="nameHeaderId"`），以及 `ColumnEditor` 的明确组合形态（列头 `:id="headerColumnId"`、行序号 `:id="rowOrderId(row.column.columnId)"`、控件 `:aria-labelledby="[headerColumnId, rowOrderId(row.column.columnId)].join(' ')"`）；不得把其他任意表达式视作匹配。补断言列头被 `aria-hidden` 时不能作为可访问表头。
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

1. **四张完整语义表**：每张都能由 `getByRole("table")` 找到，表内 `row`、`columnheader`、`cell` 的父子关系正确；枚举、映射、派生表头移除旧 `aria-hidden`；不引入 `role="grid"` 所需的方向键模型，也不改变输入控件的 Tab 顺序。
2. **方案 C 与窄屏可见性**：四张表行内 `.ui-input__label` 均为 0；`ColumnEditor` 在桌面态只显示列头，≤720px 表头隐藏后每个输入与表达式框旁显示列名，两个断点下均无同时可见的同义标签。其计算可访问名称包含列头文字和行号；序号不能仅落在 `aria-describedby`。
3. **实例级引用**：目录页与设置面板同时挂载 `ColumnEditor` 时列头 `id` 不重复，`aria-labelledby` 始终指向本实例；1050px/780px/720px 隐藏列头后引用目标仍在 DOM。`DerivedPropertyEditor` 的既有分级隐藏行为不变。
4. **逐表守卫**：新增第二张无规则表到已含合规表的组件仍使 `check:ui` 退出 1；补齐该表的稳定根锚点与专属规则后才退出 0。最终逐个核对 4 张 grid 表 + 18 张真实表，守卫存量命中数为 0，不能只按组件汇总。
5. **变异证据**：`grid-table-*`、逐表守卫与 `visible-input-label` 第四形态均有 CLI 级正反例，覆盖不存在/无文字/非列头/隐藏列头/重复标签及缺行号引用；跨实例错误引用由 Task 4 的双挂载 Playwright 用例覆盖。`check-ui-contracts.test.mjs` 的分类、注入、规则集合计数按实测同步更新。
6. `ui-contract-exceptions.json` 不残留本计划到期项，且既有 10 条例外的指纹未被无意改写；`ColumnEditor` 必须纳入门禁，不以视觉 Spec 后续修订为例外到期条件。

## 任务

### Task 1：规范正文本轮增量修订

**Files:** `docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md`（§6.4）、`docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md`（§4.3、§9.1、§9.3）。

**Interfaces:** 在 SPEC-DM-006 §6.4「单元格对齐契约」下新增一条**独立子条目**（例如「语义化 grid 表格」），不修改既有 `th/td` 条目文字；在 ARCH-DM-007 §4.3 补对应实现边界、§9.1 补静态门禁条目、§9.3 补计算样式断言要求。新规则名与字段名在本文档确定后不得在实施中改写。

- [x] 在 SPEC-DM-006 §6.4 增补：CSS grid 模拟的语义化表格须组成 `role="table" → role="row" → role="columnheader"/"cell"` 完整树，与 `<table>` 适用同一对齐契约；保持现有 Tab 模型，故不取交互式 `role="grid"`。垂直对齐由行轨道 `align-items` 承载；行高、padding 与行内控件中点沿用本节档位。注明 2026-09-27 增补及 PLAN-DM-044 来源。
- [x] 在 SPEC-DM-006 §6.4 增补方案 C：桌面态行内输入以同列列头命名，不重复显示字段标签；列头隐藏的响应式档位须就地显示字段名，且与列头视觉互斥；同名多行输入的行号须进入**可访问名称**，`aria-describedby` 仅补描述；实例级列头 `id` 不得重复。既有以视觉隐藏单元格内标签的表格不因此回退。
- [x] 在 ARCH-DM-007 §4.3 增补完整角色树、实例级 `id`、响应式可见标签及行容器 `align-items`/行高/padding 边界；§9.1 规定 `grid-table-*`、**逐表** `table-without-cell-contract` 和严格的 `visible-input-label` 第四形态；§9.3 增补列轨道、几何、可见标签互斥、计算可访问名、两个同时挂载的实例及 axe 扫描断言。
- [x] 复核修订后与 PLAN-DM-043 的既有条款不冲突，并在计划「修订记录」登记本次规范修订；提交信息：`增补语义化 grid 表格对齐规范`。

### Task 2：建立 grid 表格静态规则与迁移基线

**Files:** 新建 `web/scripts/ui-contracts/grid-table-cells.mjs`、`web/scripts/ui-contracts/table-without-cell-contract.mjs`；修改 `web/scripts/ui-contracts/types.mjs`、`web/scripts/check-ui-contracts.mjs`、`web/scripts/check-ui-contracts.test.mjs`、`web/scripts/ui-contract-exceptions.json`；按逐表盘点结果仅在确无稳定根锚点的既有真实表组件中补锚点，并在执行记录逐一列出文件。

**接口：** `collectGridTableCellViolations({files, emitFor})` 接收检查器已读取的文件列表（相对路径、源码、SFC 分段），复用 `css-vars.mjs` 的 `parseRules`/`parseDeclarations` 产出既有 `Violation` 结构；规则名固定为 `grid-table-row-height`、`grid-table-padding`、`grid-table-align`。`collectTableWithoutCellContractViolations({files, emitFor})` 按**表根**扫描 `<table>` 与 `role="table"`：每个根必须有同文件唯一的字面量 `data-ui-table-contract` 值，模块内 `TABLE_CONTRACTS` 以 `{file, marker, headerSelector, rowSelector, cssFile}` 逐表登记，并核对对应 CSS 选择器确有**行高、padding、垂直对齐**声明（真实表为 `vertical-align`，grid 表为 `align-items`）；空规则不算契约。缺 marker、重复 marker、未登记 marker、登记项无实际表根或缺声明均失败；额外扫描并拒绝不在 `role="table"`/`rowgroup` 内的孤立 `row`。同一文件已有合规表的规则不能替新表通过。守卫名固定为 `table-without-cell-contract`，不猜测计算几何。`visible-input-label` 在组件化输入分支新增第四合法形态：解析 `aria-labelledby` 的列头引用，校验完整角色树与可见文字；`ColumnEditor` 额外校验行号引用。第四形态本身不新增规则名，规则集合总数仍须把新三条 `grid-table-*` 与守卫计算进去。

**结构配对的落地形式（与 PLAN-DM-043 同口径）：** `TABLE_CONTRACTS` 的 `headerSelector`/`rowSelector` 指向实际承载几何声明的规则：真实表可为 `th/td`，grid 表为表头/数据行；允许多张表有意共用同一规则，但每张根仍单独登记 marker。grid 表的「结构性零 padding」等跨组件条件不进 `ui-contract-exceptions.json`（该文件条目被 `REQUIRED_EXCEPTION_FIELDS` 固定），仍在模块内以 `{file, rowSelector, tableSelector, requiredToken}` 精确配对。

- [x] **Step 1（RED）**：用临时 Vue/CSS 夹具覆盖缺 `align-items`、裸/多档 padding、表头/数据行 padding 不同与缺行高；守卫覆盖缺/重复/动态/未登记 marker、无实际根、CSS 选择器缺失/空规则、已合规组件内第二张无规则表、孤立 `role="row"`，并记录 class-only 边界；第四形态覆盖列头不存在/无文字/非 `columnheader`/`aria-hidden`/图标无文字、重复 `label`、缺同行序号引用与三种正例。首次运行 `test:contracts` 127 项中 12 项预期失败，证明新增路径为 RED。
- [x] **Step 2（GREEN）**：新增 `grid-table-cells.mjs` 三条规则与 `table-without-cell-contract.mjs` 逐表守卫，在 `types.mjs` 和 `check-ui-contracts.mjs` 接入；第四形态检查同一 `role="table"` 内可见列头、完整 `row` 关系、字面量/同绑定表达式，以及 `ColumnEditor` 明确列头 + 同行序号组合。扫描器只看**已声明**的选择器，不推算浏览器几何；class-only 伪表边界由探针记录。
- [x] **Step 3（棘轮与基线）**：Playwright 先量取 4 个 grid 组件；18 张真实表逐表加唯一字面量 marker 并写入 `TABLE_CONTRACTS`。四张 grid marker/配对预登记到 `GRID_TABLE_CONTRACTS`，待 Task 3/4 真实语义表根落地时加入 `TABLE_CONTRACTS` 并启用逐根守卫。真实表几何和守卫基线均为 0，无需改动 `ui-contract-exceptions.json`；原有例外/动态变量仍是 10/1，保持指纹不变。将三条 `grid-table-*`、逐表守卫和第四形态负例并入 CLI 变异组，变异数由 22 调整为 27，分类数由 20 调整为 25。
- [x] **Step 4（验证/提交）**：`rtk npm run test:contracts` 133/133 通过，含 27 条 CLI 变异；`rtk npm run check:ui` exit 0。只提交 Task 2 文件与本次 `changelog.md` 记录，提交信息：`建立网格伪表格静态门禁`。

##### Task 2 几何迁移基线

以下数据由未修改样式的 Playwright Chromium 夹具实测，视口 1280×720；列轨道为 `getComputedStyle().gridTemplateColumns`，padding 顺序为上/右/下/左。

| 组件 | 表头：行高 / padding / `align-items` / 轨道 | 数据行：行高 / padding / `align-items` / 轨道 |
| --- | --- | --- |
| `EnumValuesDialog.vue` | 19.5px / `0 0 0 0` / `center` / `140px 646px 44px` | 61.5px / `0 0 0 0` / `center` / `140px 646px 44px` |
| `MappingPropertyDialog.vue` | 19.5px / `0 0 0 0` / `end` / `339px 339px` | 61.5px / `0 0 0 0` / `end` / `339px 339px` |
| `DerivedPropertyEditor.vue` | 19.5px / `0 0 0 0` / `start` / `191.031px 80.625px 208.406px 107.516px 208.422px 26px 26px` | 38px / `0 0 0 0` / `start` / `179.094px 80.625px 195.375px 107.516px 195.375px 54px 36.0156px` |
| `ColumnEditor.vue` | 34px / `8px 12px 8px 12px` / `normal` / `34px 158.828px 461.156px 92px 112px` | 80.5px / `9px 12px 9px 12px` / `start` / `34px 158.828px 461.156px 92px 112px` |

### Task 3：标准平台三张伪表格的语义标记与几何收口

**Files:** `web/src/components/standards/EnumValuesDialog.vue`、`web/src/components/standards/MappingPropertyDialog.vue`、`web/src/components/standards/DerivedPropertyEditor.vue`、`web/tests/e2e/standards-editor.spec.ts`、`web/tests/e2e/standards-visual-evidence.spec.ts`、`web/scripts/ui-contract-exceptions.json`。

**Interfaces:** 枚举、映射表为表头与重复行增加最小 `role="table"` 包裹容器，派生表复用 `.derived-list` 作表根；三表根分别加同文件唯一的 `data-ui-table-contract` marker 并登记到 Task 2 的 `TABLE_CONTRACTS`。三表行容器补 `role="row"`、列头补 `role="columnheader"`、数据网格项补 `role="cell"`。`UiInput` 是 `inheritAttrs:false`，**不能**直接把 `role="cell"` 传给 `UiInput`（那会落在内部 `<input>`）；须在网格项外包元素上加 `role="cell"`，并复核列轨道和响应式 `:nth-child` 选择器。对每表实例用 `nextInstanceId()` 生成列头 ID，列头与输入共享同一绑定变量；三张表头均移除现有 `aria-hidden="true"`，纯操作列仍由按钮自身命名。scoped 样式显式声明 `height` 或可容纳内容增高的 `min-height:var(--sheet-table-row-height)`、单档令牌化 `padding` 与行容器 `align-items`。行内 `UiInput` 移除 `label`（派生表同时移除重复 `aria-label`）并接 `aria-labelledby`；派生表删除 `.ui-input__label` 隐藏规则与专为该标签存在的 `gap:0`，1050px/780px 隐藏列及 `align-items:start` 必须先量取再改，错误说明格按实际列跨度标注。

- [x] **Step 1（RED）**：在 `standards-editor.spec.ts` 对三张表逐一断言 `getByRole("table")` 内的表头/数据行/列头/单元格数量及父子关系、列头不在 `aria-hidden` 子树、Tab 顺序不变；同一断言量取普通行高度 ≥44px 且消费 44px 档、显式 `align-items`、单档令牌化 padding、行内控件中点差 ≤1px。新增 `.ui-input__label` 计数 0 与控件可访问名称等于对应列头文字的断言；把既有 `derived-table` 的「隐藏 label >0」断言改为 `label=0`，`ordinary-table` 同类断言保持不动。RED 实测：派生表仍有 4 个 label，枚举弹窗尚无登记表根；两条新断言失败。
- [x] **Step 2（GREEN）**：按 Interfaces 补表根、行/格角色、外包网格项、实例级列头 ID、`aria-labelledby` 与 scoped 样式；`.enum-head,.enum-row` 和 `.mapping-head,.mapping-row` 各自继续共用同一轨道声明。复跑 900×768 派生表用例，确认说明列隐藏的是整个网格项且行内项数匹配；删除 `gap:0` 后重测行高。新增 780×768 源摘要与说明列整格隐藏断言。`check:ui` 与几何验证通过，无需新增例外。
- [x] **Step 3（验证/提交）**：两份目标 e2e、`check:ui`、`test:contracts` 与生产构建均通过；900×768、780×768、1440×900 检查无横溢且响应式列隐藏符合预期；既有 `getByLabel` 定位通过。检查器未安装 `axe-core`/`@axe-core/playwright`，当前会话未运行 Narrator/NVDA，故 axe 与人工读屏列为未验证；不删减语义角色。三表无计划到期例外，例外清单保持不变。提交信息：`收口标准平台网格表格对齐并取消双重表头`。

### Task 4：目录列编辑器的几何与轨道对齐收口

**Files:** `web/src/components/sheet-catalog/ColumnEditor.vue`、`web/tests/e2e/sheet-catalog.spec.ts`、`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`、`web/scripts/ui-contracts/table-without-cell-contract.mjs` 的逐表配对表、`web/scripts/ui-contract-exceptions.json`。

**Interfaces:** `.columns` 补 `role="table"` 与同文件唯一的 `data-ui-table-contract="catalog-columns"`，并加入 Task 2 的 `TABLE_CONTRACTS`；`.columns-head` 补 `role="row"`、五个列项补 `role="columnheader"`，`.column-list` 补 `role="rowgroup"`、各 `.column-row` 补 `role="row"`、直接网格项或外包元素补 `role="cell"`；不要把 `role="cell"` 透传给 `UiInput` 内部 `<input>`。为原本**没有** `data-testid` 的行、列名输入、表达式框新增 `catalog-row-${columnId}`、`catalog-header-${columnId}`、`catalog-expression-${columnId}` 锚点，e2e 在对应编辑器区域内定位。该表确定进入 `grid-table-*` 与逐表守卫范围；显式声明 44px 基础行高档、单档令牌化 padding 与行 `align-items`，保持五列轨道、112px 操作轨、≤720px 表头隐藏与单列化。

**双重表头改造（方案 C 扩围，2026-09-27 用户裁决）：** 桌面态移除 `UiInput` 的 `label`，输入和 textarea 的可访问名由同表实例的列头文字与行号组成。使用 `nextInstanceId("catalog-table")` 生成表实例前缀，列头 `:id="headerColumnId"`/`:id="expressionColumnId"`，行序号项以实例前缀 + `columnId` 生成唯一 `:id="rowOrderId(row.column.columnId)"`；两个控件分别以 `:aria-labelledby="[headerColumnId, rowOrderId(row.column.columnId)].join(' ')"` 和表达式列头对应表达式引用同实例列头与行序号，名称例如「列名 1」「表达式 1」，而非只有列名。Task 2 静态门禁只识别该明确的组合形态并核对两端绑定，实际值由双实例 Playwright 断言。可用 `aria-describedby` 关联错误信息，但不能靠它提供名称中的行号。≤720px 仍隐藏 `.columns-head`，但列头 `id` 保持在 DOM；在每行列名输入和表达式框旁新增仅该断点显示的可见列名，复用现有 `columnsHeadHeader`/`columnsHeadExpression` 中英文文案并始终 `aria-hidden="true"`，桌面态隐藏。不得重新传 `label`，`.ui-input__label` 保持为 0。

- [x] **Step 1（RED）**：先在 `sheet-catalog.spec.ts` 增加完整 `table → row/rowgroup → columnheader/cell` 语义树、同一轨道及计算行高/`align-items`/padding、无重复 label、名称含列头和行号、720px 两侧与双挂载引用断言；组件尚未修改时三项新语义用例失败。盘点到两个目标 spec 合计 79 处编号字段 `getByLabel`，`ColumnEditor.vue` 原本没有行/控件锚点。
- [x] **Step 2（GREEN）**：按 Interfaces 增加角色、单元格包装元素、三个 `data-testid`、实例级 ID、列头 + 行号双引用与 720px 可见列名；补 44px 行高档、单档令牌 padding 和 `align-items`。保持五列轨道、两行 textarea 与 112px 操作轨，保留 `columnHeader` 原 i18n 键和文案。
- [x] **Step 3（验证/提交）**：79 处旧编号标签定位全部迁移，残留 0；`test:contracts` 133/133、`check:ui`、`check:i18n`、生产构建通过；三个语义用例聚焦运行 36/36，两个目标 spec 全量 135/135。核对窄屏字段名、隐藏表头引用、双实例 ID、本表引用、Tab 顺序、轨道与 112px 操作区；无新增例外。提交信息：`收口目录列编辑器网格表格对齐并取消双重表头`。

### Task 5：逐表守卫与存量覆盖确认

**Files:** `web/scripts/ui-contracts/table-without-cell-contract.mjs`、`web/scripts/check-ui-contracts.mjs`、`web/scripts/check-ui-contracts.test.mjs`、`web/scripts/ui-contract-exceptions.json`、[`.planning/todos/dst-manager/2026-09-26-new-table-guard-and-cell-gate-boundary.md`](../../todos/dst-manager/2026-09-26-new-table-guard-and-cell-gate-boundary.md)。

- [x] **Step 1（复核变异）**：复跑待办探针 A（`<table>` 含 class-only 单元格 padding）与 B（有 `<table>`、无 `th/td` 样式）均由 CLI 以 `table-without-cell-contract` 退出 1；同组件第二张无 marker 表 CLI 退出 1，补唯一 marker、向 `TABLE_CONTRACTS`/`GRID_TABLE_CONTRACTS` 登记专属根与行配对、添加对应 CSS 规则后退出 0。无表格语义的 class-only 伪表退出 0，记录为静态边界，不宣称守卫覆盖所有视觉伪表。
- [x] **Step 2（覆盖盘点）**：`TABLE_CONTRACTS` 为 22 项且键唯一，其中 18 张真实表、4 张 grid 表；四张 grid 与 `GRID_TABLE_CONTRACTS` 配对完整。`test:contracts` 覆盖精确根、CSS 选择器、重复/未登记 marker 与同组件第二张表；`check:ui` exit 0，逐表守卫与四表几何规则无未豁免命中。复用 Task 2 守卫，不重复实现或接入扫描链。
- [x] **Step 3（待办交接）**：待办第 1 项标注「由 PLAN-DM-044 承接（守卫已实现），本项关闭」；第 2–5 项保留待办并注明尚未被任何计划承接。提交信息：`补齐语义化表格规则守卫`。

### Task 6：目录列编辑器门禁复核与全量验证

**Files:** `web/scripts/ui-contracts/grid-table-cells.mjs`、`web/scripts/ui-contracts/table-without-cell-contract.mjs` 的精确配对表、`web/tests/e2e/sheet-catalog*.spec.ts`、`changelog.md`；仅修复复核发现的本计划缺口。

- [x] **Step 1（复核）**：确认 `ColumnEditor.vue` 已纳入 `grid-table-*` 与逐表守卫；扩展 E2E 几何断言实测 721px 桌面布局与 720px 窄屏布局，表头/数据行均满足行高下限、单档 token padding、`align-items: start`；桌面五轨一致且操作轨为 112px，窄屏两轨一致。未新增例外。
- [x] **Step 2（全量验证）**：`test:contracts` 133/133、`check:ui`、`check:i18n`（1620 keys / 11 domains）、`test:unit` 339/339、`build`、`ruff check .` 全部通过；最终全量 Playwright E2E 701/701 通过。`TABLE_CONTRACTS` 22 张逐表覆盖，例外清单仍为既有 10 条、1 条动态变量且无 PLAN-DM-044 项；目标 E2E 旧标签定位已迁移，样式基线等待 surface token 与输入框样式就绪后连续复跑 10/10。无 Python 改动，因此无相关 pytest。构建仅有既有单 chunk 超过 500KB 的非阻断提示。
- [x] **Step 3（缺口登记）**：本轮未完成 DST Manager 产品 Windows WebView2 窗口的人工缩放复验；Playwright viewport 断点与 Codex 自身 WebView 均不作为产品验收替代。100/125/150/200% 缩放下代表性模态/编辑页仍未验证，按 ARCH-DM-007 §12 保持计划 `active`，不声称通过。实施提交信息：`完成网格伪表格对齐契约收口`。

## 风险与处置

- **规范与实现的一致性风险**：`grid-table-*` 规则如果先于规范修订落地，就会出现「门禁比规范严」的矛盾。处置：Task 1 必须先于 Task 2，且规则名以 Task 1 定稿为准。
- **语义树与键盘模型风险**：孤立 `role="row"` 无法构成表格，交互式 `role="grid"` 又要求本计划未设计的方向键模型。处置：四张表统一 `role="table"` 根与完整行/格角色，枚举/映射增加最小包裹容器，`ColumnEditor` 的 `ol` 用 `rowgroup` 串接；axe/读屏或 Demo 对照失败时修正结构与关系，不能删除必要角色以压绿扫描。
- **取消双重表头带来的定位回归风险（方案 C 特有）**：移除行内 `label` 会同时移除 `label[for]` 与 `id` 的关联路径，若既有 e2e 以 `getByLabel("枚举值")` 之类可见文案定位行内输入，会变成"命中列头 + 多行控件"的歧义定位而失败。处置：Task 3 Step 1 先记录现状命中数量作为 RED 证据，Step 3 逐一核对并改为 `data-testid` 定位；**不得为了保住旧定位而回退方案 C**（`data-testid` 本就已存在，改造成本低于保留双重标签的可访问性代价）。
- **门禁第四形态被放水风险**：`visible-input-label` 新增的 `aria-labelledby` 形态若实现为"有 `aria-labelledby` 即通过"，会让任意无可见标签的控件蒙混过关。处置：Task 2 Step 1 必须同时写正向与五条反向用例，Task 3 / Task 4 的 Step 3 复核 `check:ui` 在移除 `label` 后**不是**因为门禁被放宽才通过；Task 5 的变异清单须包含第四形态的反向注入。
- **`ColumnEditor` 旧定位与锚点风险**：`sheet-catalog.spec.ts` 有 20+ 处按旧可访问名定位，但组件当前没有 `data-testid`。处置：Task 4 先记录旧定位清单并新增行、列名输入、表达式框锚点，再逐条迁移；可访问名称按「列头文字 + 行号」断言，不为保旧定位回退方案 C。
- **`ColumnEditor` 窄屏可见标签与实例冲突风险**：≤720px 当前隐藏表头，移除行内 `label` 后会失去可见列名；目录页与设置面板可能同时挂载两份组件。处置：Task 4 让可见行内列名只在该断点显示，表头在 DOM 中保留供命名；用 `nextInstanceId()` 前缀生成列头与行序号 ID，测试双实例引用不串联。行号必须进入 `aria-labelledby` 计算名称，`aria-describedby` 不能代替。
- **`DerivedPropertyEditor` 改造的既有断言冲突（方案 C 扩围特有）**：该表当前的可访问性口径是「列头 `aria-hidden` + 行内 `aria-label`/隐藏 `label`」，且 `standards-editor.spec.ts` 第 168–170 行**直接断言**了"`derived-table` 内 `label` 计数 > 0 且首项隐藏"、第 291–292 与 718–719 行以 `getByLabel("属性名")`/`getByLabel("作用域")` 定位行内控件。改为方案 C 后：① 前一条断言必须改写为「count 为 0」；② 后两条定位依赖可访问名不变——`aria-labelledby` 指向的列头文字与现 `aria-label` 文字一致（「属性名」「作用域」「类型」「说明」）时仍可命中。已核实门禁边界（[check-ui-contracts.mjs](file:///c:/Users/sonic/autocad-sheetset/web/scripts/check-ui-contracts.mjs#L449-L528)）：`visible-input-label` 只扫裸 `<input>` 与 `UiInput`/`UiSelect` 调用点，**不扫裸 `<select>`**——作用域列的 `<select class="cell-select" aria-label="作用域">` 因此不受第四形态约束，本轮**保留其 `aria-label` 即可**，但该列若同时存在列头文字，须人工确认不构成视觉双重表头（`select` 无 `label` 元素，不存在 `.ui-input__label` 重复问题）。处置：Step 1 必须先跑一次现状并记录两条定位的实际命中数与断言原文，Step 3 逐条核对改写，**不得为保住旧断言而放弃扩围**。
- **`DerivedPropertyEditor` 的 `aria-hidden` 移除风险**：列头去掉 `aria-hidden` 后，读屏会在进入每行前播报列标题，可能与基准 Demo 的对照结论不一致或造成重复播报（行内控件已通过 `aria-labelledby` 引用同一文字）。处置：Task 3 Step 3 跑 axe 并做一次读屏人工走查（环境缺失时登记缺口），若确认重复播报，按全局约束的最小必要集合裁决——保留 `role="columnheader"`/`id`，仅对纯操作列恢复 `aria-hidden`，并在执行记录登记实际集合。
- **`DerivedPropertyEditor` 的高度不确定性**：`.derived-row` 为 `align-items:start` 且可能含 `.row-issue` 错误行，无法断言恰好 44px。处置：采用「≥44px 且消费该档」，单独断言错误行不裁切、隐藏列在 1050px/780px 断点行为不变；删除 `:deep(.ui-input){gap:0}` 后重新量取行高。
- **`ColumnEditor.vue` 的既有 Bases**：其 ↑/↓/✕ 三个 Unicode 图标例外与 112px 操作轨是 PLAN-DM-023 A1 的已批准裁决，本计划不得借对齐收口之名改写；Task 4/6 只改行几何与对齐，不动操作轨与图标形态。
- **守卫的漏报与误报风险**：仅检查组件是否存在任意表格规则，会放过同组件新增的第二张无规则表；父级全局样式则可能使逐表检查误报。处置：为每张 `<table>`/`role="table"` 根记录稳定锚点和精确规则配对，允许规则位于明确登记的父级全局样式文件；用“同组件第二张表无规则/补规则”双向探针确认。无语义也无登记锚点的纯视觉 class-only 伪表是静态边界，须在执行记录明确，不宣称守卫能自动发现。
- **内容驱动高度与滚动**：`EnumValuesDialog` 与 `MappingPropertyDialog` 的正文滚动、`DerivedPropertyEditor` 的分级响应式可能改变可见列数与行高。处置：保持既有滚动与隐藏行为，长文本、错误态与缩放逐档检查，不把截图差异直接当作业务回归。

## 验证命令

- 静态规则和变异：`rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run check:ui`。
- 前端回归与构建：各任务列明的 `rtk npm --prefix web run test:e2e -- tests/e2e/<目标文件>.spec.ts`；最终运行 `rtk npm --prefix web run test:unit`、`rtk npm --prefix web run build`、`rtk npm --prefix web run test:e2e`。
- 仓库检查：`rtk uv run ruff check .`、`rtk git diff --check`；若实施中修改 Python，再运行相关 pytest，且不以 Ruff 代替测试。

## 完成标准与实际验证

- [x] Task 1 的规范增量修订已落地（含「列头即可访问名 / 禁止双重表头」条款），规则名与 ARCH-DM-007 §9.1 门禁条目一致。
- [ ] 4 张 grid 表均有完整 `role="table" → row → columnheader/cell` 语义树，逐个有行高档、单档令牌化 padding 与行轨道对齐的 Playwright 证据；`ColumnEditor.vue` 纳入静态门禁，不存在整表例外。
- [ ] **双重表头已取消且窄屏可用**：四张表行内 `.ui-input__label` 均为 0；`ColumnEditor` 在桌面态只显示列头，≤720px 每行列名/表达式框均有可见字段名，且各控件计算可访问名称包含列头文字与行号。目录页、设置面板双实例 ID 不冲突；`OrdinaryPropertyEditor` 与 `GroupsStep` 的既有路径未回退；派生表旧 label 断言及目录页 20+ 处旧 `getByLabel` 定位已逐条改写并通过。
- [ ] `TABLE_CONTRACTS` 精确覆盖 18 张真实表与 4 张 grid 表；同组件新增第二张无规则表的 CLI 变异为红，补 marker/配对/规则后为绿。`grid-table-*`、逐表守卫与 `visible-input-label` 第四形态的正反例均通过；全量 `test:contracts`、`test:unit`、`build`、`test:e2e`、`check:i18n` 与 `check:ui` 通过。例外清单仅保留既有未到期条目，无本计划新增到期项。
- [ ] 待办 `2026-09-26-new-table-guard-and-cell-gate-boundary.md` 第 1 项已标注由本计划承接并关闭，第 2–5 项状态已更新。
- [ ] 真实 Windows WebView2 100/125/150/200% 复验通过后才把状态改为 `completed`（[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §12）；桌面复验缺失时保持 `active` 并把缺口写入下表，不得以自动化证据代替真实缩放结论；实施期间保持 `active`，未开始前保持 `proposed`。

| 日期 | Task | RED 证据 | GREEN 与回归命令/结果 | 仍待验证 |
| --- | --- | --- | --- | --- |
| 2026-09-27 | Task 1 规范正文本轮增量修订 | 文档规范任务，无运行时 RED 用例 | §6.4 / §4.3 / §9.1 / §9.3 增量已完成，PLAN-DM-043 规则与 18 张真实表口径保留；`rtk git diff --check` exit 0 | Tasks 3–6 实施；真实 Windows WebView2 缩放复验 |
| 2026-09-27 | Task 2 静态规则与迁移基线 | 首次 `test:contracts` 127 项中 12 项新增用例失败；覆盖几何规则、逐表守卫、第四种标签形态 | `test:contracts` 133/133，27 条 CLI 变异；`check:ui` exit 0；18 张真实表 marker 配对完整，原 10 条例外 + 1 条动态变量未改 | 四张 grid 根将在 Tasks 3/4 落地；屏幕阅读器与真实 WebView2 缩放复验 |
| 2026-09-27 | Task 3 标准平台三张 grid 表 | 派生表旧断言收到 4 个 label；枚举弹窗未找到登记表根；新增语义/几何断言按预期失败 | `test:contracts` 133/133；`check:ui` exit 0；生产 `build` exit 0（含 API/i18n/TypeScript 检查）；两目标 spec 67/67，最终聚焦复跑 34/34；900×768、780×768、1440×900 几何/响应式断言通过；截图人工检查 | `axe-core` 不在依赖树且 Narrator/NVDA 未运行，axe 与人工读屏未验证；真实 WebView2 缩放复验 |
| 2026-09-27 | Task 4 目录列编辑器 | 三项语义/几何/双挂载用例在实现前失败；旧定位盘点 79 处 | `test:contracts` 133/133；`check:ui`、`check:i18n`、生产 `build` exit 0；聚焦用例 36/36，两个目标 spec 135/135；79 处旧定位已改写且残留 0；检查列头名称、720px 标签、双实例引用、Tab 顺序、五列轨道和 112px 操作轨 | 真实 Windows WebView2 100/125/150/200% 缩放复验；axe 与人工读屏仍未验证 |
| 2026-09-27 | Task 5 逐表守卫复核 | 待办探针 A/B 与独立新表、同组件第二表未登记配置均由 CLI 退出 1；无语义 class-only 伪表探针为 0 | 同组件第二表补 marker/根配对/CSS 后 CLI exit 0；登记 22 张表（18 原生 + 4 grid）唯一完整；`check:ui` exit 0；待办第 1 项关闭、第 2–5 项仍未承接 | 全量验证与真实 Windows WebView2 缩放复验 |

## 修订记录

- 2026-09-27 首版（proposed）：依据用户对「grid 伪表格是否属于表格对齐契约」的核查结论起草。范围裁决为语义标记 + 门禁扩展、4 张伪表格全收、守卫一并纳入；明确与 PLAN-DM-043（真实 `<table>`，11 组件 / 18 张表）互不重叠，并把 `ColumnEditor.vue` 的门禁口径裁决单列为 Task 6，避免在范围上做出无证据的承诺。
- 2026-09-27 修订（方案 C，用户裁决）：明确**取消双重表头**——`EnumValuesDialog` 与 `MappingPropertyDialog` 行内不再渲染重复字段标签，可访问名称改由同列 `role="columnheader"` 经 `aria-labelledby` 承担；相应扩展 `visible-input-label` 门禁第四种合法形态（严格三条件，含三条反向变异用例），并在 Task 1 增列规范条款、Task 2 增列门禁实现、Task 3 增列 RED/GREEN 断言与定位回归核对、Review Focus/完成标准/风险新增对应条目。原「保留 label、仅视觉隐藏」的处置仅保留给既有表格；`DerivedPropertyEditor.vue`（列头 `aria-hidden`）本轮不随方案 C 改造，差异已在风险中登记。
- 2026-09-27 修订二（方案 C 扩围，用户追加裁决）：把 `DerivedPropertyEditor.vue` **纳入**方案 C 改造范围，三张 grid 表口径统一。相应新增「列头 `aria-hidden` 与 `aria-labelledby` 共存规则」（移除列头 `aria-hidden`、保留 `id`/`role`、删除两条"隐藏标签"规则、被隐藏列的 `id` 仍在 DOM、空操作列可不参与可访问名），Task 3 的 Interfaces/Step 1/Step 2/Step 3 全部改写（含把 `standards-editor.spec.ts` 第 168–170 行「`label` 计数 > 0 且隐藏」的既有断言按新口径改写、复跑 900×768 网格项隐藏用例、axe 与读屏走查），风险条替换为「既有断言冲突」「`aria-hidden` 移除」「删 `gap:0` 后重新量取行高」三项。原「派生表不改造」的说明与对应完成标准条目已删除。
- 2026-09-27 修订三（方案 C 二次扩围，用户追加裁决）：把 `ColumnEditor.vue`（图纸目录插件的输出列编辑器）**纳入**双重表头改造——截图确认其列头「列名」/「表达式」与行内「输出列名 N」/「表达式 N」构成双重表头，而 Task 4 原稿只安排了几何与轨道对齐，属计划缺口。按用户裁决取「**列头文字 + 行号补足**」（`aria-labelledby` 指向列头，另以 `aria-describedby` 补行号，避免 N 行同报「列名」），并把改造落到 Task 4 的 Interfaces 与三个 Step（含记录并核对 `sheet-catalog.spec.ts` 20+ 处 `getByLabel("输出列名 N")` 定位、≤720px 表头隐藏时列头 `id` 仍留在 DOM）。同时修正门禁第四形态的判定条件：由「必须 `role="columnheader"`」放宽为「`role="columnheader"` 或位于 `role="row"`/`.columns-head` 列头行内」两条路径之一，以适配 `ColumnEditor` 不新增 ARIA 角色的既有裁决，并把反向用例从三条扩到五条。范围由三张表扩为**四张**，相应更新范围裁决、Review Focus、完成标准与两条新增风险。
- 2026-09-27 审查后修订四（仍为 proposed）：修复六项计划缺口。四表统一完整 `role="table"` 语义树，撤销上条“`ColumnEditor` 不新增 ARIA 角色”口径；≤720px 表头隐藏时增加视觉互斥的可见行内列名；行号由 `aria-labelledby` 进入计算名称而非仅由 `aria-describedby` 提供描述；列头与行号 ID 改为实例级并测试双挂载；`ColumnEditor` 先补 `data-testid` 再迁移旧定位；守卫改为按每张表的 `data-ui-table-contract` marker 与 `TABLE_CONTRACTS` 精确配对，验证同组件第二张无规则表也会失败。Task 6 取消“整表例外”分支；上条相冲突的实施口径均以本次修订为准。未实施代码或规范正文。
- 2026-09-27 执行 Task 1：增量修订 SPEC-DM-006 §6.4 与 ARCH-DM-007 §4.3/§9.1/§9.3，固定三条 `grid-table-*` 规则、逐表守卫和第四种严格标签形态；旧 `th/td` 条目未改写。
- 2026-09-27 执行 Task 2：接入三条 `grid-table-*` 规则、逐表 `table-without-cell-contract` 和严格 `aria-labelledby` 第四形态；18 张真实表逐根加 marker，4 张 grid 表的几何配对预登记。Playwright 记录四表初始行高、padding、`align-items` 与计算轨道；原生表 `table-cell-*`、逐表守卫的未豁免基线均为 0，例外清单 10/1 保持原样；计划进入 Tasks 3–6。
- 2026-09-27 执行 Task 3：枚举、映射与派生表补齐语义树、实例级列头 ID 和 `aria-labelledby`，取消三表重复输入标签；三张表契约登记启用。统一使用 44px `min-height` 档、单档令牌 padding 和显式行轨道对齐，保留派生表 1050px/780px 响应式隐藏；axe/读屏工具不可用已记录，计划继续 active。
- 2026-09-27 执行 Task 4：目录列编辑器补齐语义表格角色、实例级列头与行号命名、720px 可见字段名及测试锚点；启用第 4 张 grid 表契约，迁移两个目标 spec 中 79 处编号字段定位。静态契约、i18n、构建与两目标 E2E 135/135 通过；读屏与真实 WebView2 缩放仍待复验。
- 2026-09-27 执行 Task 5：重跑待办探针 A/B、独立新表和同组件第二张表 CLI 正反探针；确认无语义 class-only 伪表是静态边界。22 张根契约唯一且完整、`check:ui` 为 0；关闭待办第 1 项，保留第 2–5 项。
