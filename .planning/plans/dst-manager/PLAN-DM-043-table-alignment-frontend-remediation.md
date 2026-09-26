---
id: PLAN-DM-043
title: 表格对齐契约前端收口实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-26
updated: 2026-09-26
related:
  - ARCH-DM-007
  - SPEC-DM-006
  - SPEC-DM-009
  - SPEC-DM-010
  - SPEC-DM-012
  - SPEC-DM-017
  - SPEC-DM-018
  - PLAN-DM-029
---

# 表格对齐契约前端收口实施计划

> **执行约定：** 实施者逐任务使用 `superpowers:executing-plans` 或经用户选定的同等流程，按 RED → 最小实现 → GREEN → 复核执行；复选框只在实际完成并登记验证后勾选。本文是待执行计划，不代表前端样式或检查器已完成整改。

**目标：** 让现有用户可见数据表符合 [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §5.3/§6.4：**11 个含 `<table>` 的组件、共 18 张表本轮全部命中一档**（2 张常驻 38px 输入框的编辑表取 48px，其余 16 张取 44px，`PreviewPanel.vue` 一个组件占 8 张）；普通表以可容纳内容的基础行高、统一 padding 和明确对齐呈现；跨列详情行按内容增高且内部负责间距；静态门禁与浏览器断言能阻止回退。

**架构：** 扩展现有 `check:ui` CSS 解析与例外棘轮，在静态层约束单元格声明和令牌使用，在 Playwright 计算样式层验证同表实际几何。先覆盖图纸/属性主表，再覆盖常驻编辑表，最后收口其余只读表与旧页面；不引入新的表格框架或全局覆盖样式。

**技术栈：** Windows 11、Vue 3、TypeScript、Vite、Node.js 内置 `node:test`、Vitest、Playwright、CSS 自定义属性；Python 仅运行既有 Ruff/pytest 回归。

**规范依据：** 用户可见口径以 [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.4 为唯一权威；实现及门禁边界见 [ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §4.3/§9，存量 `10px 8px`／`9px`／`4px` 三档的迁移归属按同文 §7（SPEC-DM-006 §6.4 明确“存量 10px/9px/4px 档按 ARCH-DM-007 §7 迁移顺序收口”）。图纸表、属性表、图纸目录预览、标准编辑与创建向导分别遵守 [SPEC-DM-009](../../../docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md)、[SPEC-DM-010](../../../docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md)、[SPEC-DM-012](../../../docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md)、[SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md)、[SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md) 的既有交互。

**与 §7 迁移顺序的偏差（本轮裁决）：** §7 的顺序用于**页面级**视觉迁移（属性 → 目录 → 图纸/浮层 → 设置 → 旧页面）；本计划是**横向表格契约收口**，只改单元格几何与对齐，不承接页面原语迁移进度，故按“门禁 → 图纸/属性主表 → 常驻编辑表 → 其余只读表 → 旧表”排列：主表已消费 44px 令牌、存量偏差最小，可作为静态门禁与计算样式断言的样板；旧表放在最后与 §7 第 5 项一致。该偏差不改变 §7 对 legacy 规则删除时点的约束。

**令牌归属裁决（2026-09-26 用户确认，方案 A）：** 7 个组件的只读表与旧表消费**既有** `--sheet-table-row-height`，不新增中性 44px 令牌。依据：SPEC-DM-006 §5.3 与 ARCH-DM-007 §4.3 的正文点名的正是 `--sheet-table-row-height` / `--definition-row-height` 两个令牌，跨页消费 `--sheet-*` 已有先例（`GroupsStep.vue` 消费 `--sheet-property-search-width`），方案 A 不需要改动任何已接受规范的正文。备选方案 B（新增中性令牌、旧令牌保留字面值，会造出 3 份同值 44px 定义）与方案 C（新增中性令牌并把两个旧令牌改为别名，需改动两个已验收页面的令牌定义）都需同批修订 SPEC-DM-006 §5.3、ARCH-DM-007 §4.3、`docs/dst-manager/README.md` 与根 `changelog.md`；用户已否决，故本计划不含令牌体系改造任务。该借用的语义风险、后果与兜底见「风险与处置」。

## 前置条件

- SPEC-DM-006 与 ARCH-DM-007 的 2026-09-26 行高、padding 修订是实施基准；PLAN-DM-029 已完成的令牌、`check:ui` 与例外棘轮保持可用，本计划不重做其通用视觉基础。
- 实施前在 Windows 11 工作区确认 Web 依赖可用，并用既有 fixture 跑一次目标 e2e 基线；若基线已失败，先定位与本计划无关的失败并记录，不将其误判为 RED 证据。
- 本计划为纯前端视觉与静态门禁调整；不需要真实 AutoCAD 作为代码实施前置条件。最终桌面缩放复验需要 Windows WebView2；缺失时记录证据缺口并**保持 `active`**，不得据此宣布验收通过（[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §12）。
- Task 1 的迁移基线必须一次量取全部 11 个含表格组件的现状计算值（行高、单元格 padding、`vertical-align`、是否落在 44px 档），作为 Task 2–5 的 RED 依据与最终命中证据；不得凭源码推断未量取的表格已符合。

## 全局约束

- 任务开始前检查 `rtk git status --short`，保留用户已有改动；只暂存本任务文件。每次实际代码修改同步更新根 `changelog.md`，提交信息用简体中文动词短语。
- 不改 HTTP/SSE、后端校验、字段含义、props/emits、i18n key、键盘焦点和表格选择行为；视觉改动须保留固定列、内部横向滚动与现有可访问名称。
- 不新增密度切换入口或持久化设置。`32px` 是仅在内容与控件可容纳时可用的紧凑档；本轮不能把 38px 输入框压入 32px 行，也不能缩小既有控件命中区。
- 普通单行数据表的舒适基础档为 `44px`（现有 `--sheet-table-row-height` / `--definition-row-height`）；常驻 38px 控件且上下各 4px padding 的编辑表以新组件令牌取 `48px`；表头匹配同表普通行的基础档。多行文本、错误提示及跨列详情行允许增高，禁止裁切内容。
- **18 张表全部命中一档，不留 legacy 兜底（令牌选择见「令牌归属裁决」，不得自行改名）**：图纸/属性主表继续消费各自页面令牌（`--sheet-table-row-height` / `--definition-row-height`），其余 7 个组件的只读表与旧表按 [ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §4.3 的口径消费既有 `--sheet-table-row-height`；本轮不新增 44px 令牌，也不把没有 `th/td` 规则的表格留给 `legacy.css` 的 `9px` + `top` 兜底。实施中若发现某张表确实不适合 44px 档，按「风险与处置」的处置路径上升裁决，不得就地换令牌名。
- 普通 `th/td` 同表同档 padding，消费间距令牌或组件令牌。本轮跨列结构单元格只有三处，实施时按此清单核对、不得扩大：`SheetTable.vue` 的 `.sheet-editor-row>td`（`padding:0`，内层 `SheetPropertyEditor.vue` 的 `.sheet-property-editor` 消费 `--space-4`）、`AssetInspectionPanel.vue` 的 `td.panel-note[colspan=2]`（空态说明行，仍按普通格同档 padding，不取零）、`JobStatusPanel.vue` 的 `td[colspan=8]` 日志详情（若取 `padding:0`，按 Task 1 的配对机制登记并给内层容器令牌化间距）。`vertical-align` 显式取 `middle`，仅多行长文本单元格可取 `top`；**出错行整行同档切换**，不允许单格 `top` 造成同行控件中心错位。
- 三张旧页面组件（`PreviewPanel.vue`、`JobStatusPanel.vue`、`RevisionHistoryPanel.vue`）当前没有 `<style>` 块，单元格几何完全来自 `legacy.css`。本轮迁移后 `legacy.css` 的 `:where(#app) th,:where(#app) td` 规则已无消费者，由 Task 5 按 §7 明确处置（删除，或登记到“§7 第 5 项页面迁移完成”为止的到期条件），不得留在无到期条件的例外表里。
- 标识符型数字（图号、编号、handle、哈希、版本）按文本左对齐；进度、数量、耗时等可比较数值及对应表头右对齐并使用 `tabular-nums`。同一数值列统一小数位与千分位，单位写入表头；如需调整现有单元格单位文案，同时更新中英文值与断言，不改底层数值或 API。
- 每个实现任务先写能因目标缺陷失败的测试，再做最小改动并复跑。静态门禁新增或规则变更须运行变异用例；现存偏差按 `ui-contract-exceptions.json` 的指纹棘轮登记与逐项清退，不以全局白名单掩盖新表格。

## 文件与责任边界

| 责任 | 主要文件 | 验收位置 |
| --- | --- | --- |
| 静态规则与例外棘轮 | `web/scripts/ui-contracts/table-cells.mjs`（新增）、`types.mjs`、`check-ui-contracts.mjs`、`ui-contract-exceptions.json` | `web/scripts/check-ui-contracts.test.mjs` |
| 基础档与主表 | `web/src/styles/tokens.css`、`web/src/components/SheetTable.vue`、`web/src/components/properties/PropertyDefinitionTable.vue` | `web/tests/e2e/sheets-layout.spec.ts`、`properties-visual-evidence.spec.ts` |
| 常驻编辑表 | `web/src/components/standards/OrdinaryPropertyEditor.vue`、`web/src/components/creation/GroupsStep.vue` | `web/tests/e2e/standards-editor.spec.ts`、`create-sheetset-input.spec.ts` |
| 其余只读表 | `web/src/components/standards/AssetInspectionPanel.vue`、`web/src/components/creation/ReviewStep.vue`、`web/src/components/creation/SheetValuesDialog.vue`、`web/src/components/sheet-catalog/CatalogPreview.vue` | `standards-assets-publish.spec.ts`、`create-sheetset-review.spec.ts`、`sheet-catalog.spec.ts` |
| 旧页面表 | `web/src/components/PreviewPanel.vue`（8 张表，需按列给类名）、`web/src/components/JobStatusPanel.vue`、`web/src/components/RevisionHistoryPanel.vue`、`web/src/styles/legacy.css` | `web/tests/e2e/main.spec.ts` 等既有流程用例 |

`web/src/components/sheets/SheetPropertyEditor.vue` 已以 `--space-4` 给跨列编辑面板提供内边距；本计划只验证该责任边界，不为零 padding 再加一层外边距。`PreviewPanel.vue`、`JobStatusPanel.vue`、`RevisionHistoryPanel.vue` 目前**没有任何 `<style>` 块**，Task 5 需新建 `<style scoped>` 并显式重声明 `legacy.css` 现在提供的全部单元格声明（`width`、`border-collapse`、`border-bottom`、`text-align`、行高与 `vertical-align`），不是只加类名。`GroupsStep.vue` 的 `.group-table`、`SheetValuesDialog.vue` 的 `.values-table`、`AssetInspectionPanel.vue` 的 `.layout-table` 目前在 `web/tests/e2e/**` 中无任何选择器引用，Task 3/4 必须先补稳定锚点（`data-testid` 或可访问名）再写 RED。若执行时发现未列出的 `<table>` 或表格角色，应按同一契约纳入本计划并更新清单，不能因静态规则未识别而跳过。

## Review Focus

1. 38px 输入框 + 4px 上下 padding + 分隔线至少需 47px：48px 编辑行与表头不裁切；错误提示出现时仅该数据行按内容增高（Task 3）。
2. 图纸表展开编辑区是跨列结构行：`td` 的零 padding 不被误判，内部 16px 间距仍在，收起后普通行回到 44px；跨列结构单元格只有 `.sheet-editor-row>td`、`AssetInspectionPanel` 的 `td.panel-note[colspan=2]`、`JobStatusPanel` 的 `td[colspan=8]` 三处，任何一处都不构成普通格的通用豁免（Task 2、4、5）。
3. 200% 缩放或长文本使行增高时，表头仍只匹配普通行基础档，内容和操作按钮不重叠（Task 2、3、4）。
4. 进度/数量/耗时右对齐且同列格式统一、单位在表头；图号、handle、版本与哈希仍左对齐；表头方向与列数据一致（Task 4、5）。
5. **18 张表逐张有明确基础档**：9 个组件的 16 张表命中 44px 档、两张常驻编辑表命中 48px 档，且每张表都有计算样式证据；靠 `legacy.css` 兜底或完全没有 `th/td` 规则的表格（`CatalogPreview`、`JobStatusPanel` 的日志详情格）必须由 Playwright 断言兜底（Task 2、3、4、5）。
6. 新增裸 padding、**已声明 `th/td` 规则却缺 `vertical-align`**、同表两档 padding 或把普通 `td` 伪装成结构例外必须使 `check:ui` 失败；静态门禁只约束已声明的规则，看不到“完全没有规则、只能继承 `legacy.css`”的单元格，这类只能靠浏览器断言，不得在计划或提交说明里声称已被静态门禁覆盖。旧例外清退后不能留下过期条目（Task 1、5）。

## 任务

### Task 1：建立表格静态契约与迁移基线

**Files:** 新建 `web/scripts/ui-contracts/table-cells.mjs`；修改 `web/scripts/ui-contracts/types.mjs`、`web/scripts/check-ui-contracts.mjs`、`web/scripts/check-ui-contracts.test.mjs`、`web/scripts/ui-contract-exceptions.json`。

**接口：** `collectTableCellViolations({files, emitFor})` 接收检查器已读取的文件列表（相对路径、源码和 SFC 分段），复用既有 CSS 规则/声明解析并产出既有 `Violation` 结构；规则名固定为 `table-cell-vertical-align` 与 `table-cell-padding`，沿用现有指纹和 CLI 棘轮。

**结构配对落地形式（本轮裁决，与全局约束“配对放行”同口径）：** 跨列结构单元格的放行**不进 `ui-contract-exceptions.json`**——该文件条目被 `REQUIRED_EXCEPTION_FIELDS`（`rule/file/fingerprint/reason/expiresWith`）固定，无法承载“内层容器必须消费间距令牌”这一条件。配对改由 `table-cells.mjs` 内的常量 `STRUCTURAL_CELL_PAIRS` 表达，形如 `{file, selector, innerFile, innerSelector, requiredToken}` 的**精确**条目：只有 `SheetTable.vue` 的 `.sheet-editor-row>td` 命中 `file+selector` 时才去 `SheetPropertyEditor.vue` 的 `.sheet-property-editor` 核对 `padding` 消费了间距令牌，否则仍判违规。例外表只登记“规则 + 文件 + 稳定语义 + 到期条件”的存量债务，不承担结构放行。不把“有 `colspan`”当豁免条件。

- [ ] **Step 1（RED）**：在临时 Vue/CSS 夹具写用例：表格基础 `th/td` 缺 `vertical-align`、使用裸非零 padding、同表普通格两档 padding、普通 `td{padding:0}`、伪造通用 `td[colspan]{padding:0}` 均失败；`.sheet-editor-row>td{padding:0}` 且内层容器消费 `var(--space-4)` 通过，删内层间距令牌后失败；非表格的 `td` 字符串/注释不触发。运行 `rtk npm --prefix web run test:contracts`，确认目标用例 RED。
- [ ] **Step 2（GREEN）**：复用 `css-vars.mjs` 的 `parseRules`/`parseDeclarations` 解析规则与声明，按表格基准选择器与具体结构选择器判定；`padding:0` 只对 `STRUCTURAL_CELL_PAIRS` 里的精确配对放行，不按任意 `colspan` 放行。静态层检查声明和令牌，不以源码猜测几何；同表最终计算值由浏览器测试覆盖。注意门禁只约束**已声明的 `th/td` 规则**：某张表完全没有规则时不产生违规（只是继承 `legacy.css`），这类表格由 Task 4/5 的浏览器断言兜底。
- [ ] **Step 3（棘轮）**：Task 1 先量取并登记 11 个含表格组件的现状（行高、padding、`vertical-align`、是否落在 44px 档），再把存量违规按文件、规则、稳定语义登记到 `ui-contract-exceptions.json`，每条写明迁移任务与到期条件；新表格和新违规立即失败。注入每种规则的变异夹具，把新规则并入 `check-ui-contracts.test.mjs` 既有的“每类判定都有 CLI 级变异证据”清单，验证 CLI 退出 1；恢复夹具后退出 0，陈旧例外使检查失败。
- [ ] **Step 4（验证/提交）**：运行 `rtk npm --prefix web run test:contracts` 与 `rtk npm --prefix web run check:ui`；只提交本任务文件及本次 `changelog.md` 记录，提交信息：`建立表格单元格静态门禁`。

### Task 2：图纸与属性主表的普通行及跨列详情

**Files:** `web/src/components/SheetTable.vue`、`web/src/components/properties/PropertyDefinitionTable.vue`、`web/tests/e2e/sheets-layout.spec.ts`、`web/tests/e2e/properties-visual-evidence.spec.ts`、`web/scripts/ui-contract-exceptions.json`。

**接口：** 保持既有 `--sheet-table-row-height` 与 `--definition-row-height` 均为 44px；普通 `th/td` 统一使用 `padding:var(--space-2)`（上下左右均 8px），`.sheet-editor-row>td` 仍显式为 `height:auto;padding:0`。

- [ ] **Step 1（RED）**：在图纸表断言表头与单行普通数据行消费 44px 档（图纸表已有 `th` 44px 断言，属既有 GREEN，RED 只来自 padding）、普通格计算 padding 四边均为 `--space-2` 的 8px、展开行单元格计算 padding 为 0、编辑面板计算 padding 来自 `--space-4`；在属性定义表断言表头 44px（`--definition-row-height`）与同样的 8px padding、**数据行 ≥44px 且长默认值展开后完整可读**——不得断言数据行恰好 44px：`properties-visual-evidence.spec.ts` 已记录定义表表体行被单元格内的展开/删除按钮撑高，属既有事实，按字面断言会得到与本次改动无关、无法转绿的 RED。运行对应两份 e2e，确认现行 `10px 8px` 使新增 padding 断言 RED。
- [ ] **Step 2（GREEN）**：将两表的 `10px 8px` 普通格 padding 收敛为 `var(--space-2)`，显式保留 `vertical-align:middle`；图纸表结构行按 Task 1 的 `STRUCTURAL_CELL_PAIRS` 配对放行（不新增例外表条目），保持编辑器内部间距与固定列阴影行为。若新 padding 导致布局回归，先查几何原因并按 SPEC 修订表格局部布局，不改全局 `legacy.css` 兜底或用裁切恢复旧截图。
- [ ] **Step 3（验证/提交）**：运行这两份 e2e、`rtk npm --prefix web run check:ui`；核对 1024×768 与 1440×900 下横向滚动仍只在表格内，清退命中的旧例外；提交信息：`统一图纸与属性主表单元格几何`。

### Task 3：常驻编辑表的 48px 档与错误增高

**Files:** `web/src/styles/tokens.css`、`web/src/components/standards/OrdinaryPropertyEditor.vue`、`web/src/components/creation/GroupsStep.vue`、`web/tests/e2e/standards-editor.spec.ts`、`web/tests/e2e/create-sheetset-input.spec.ts`、`web/scripts/ui-contract-exceptions.json`。

**接口：** 在 `tokens.css` 新增组件令牌 `--editable-table-row-height:48px`；两张常驻编辑表的普通表头/数据格消费它及同一 `--space-1` padding，不复用图纸浏览表的 44px 令牌。

- [ ] **Step 1（RED）**：测试两表的无错误普通行及表头基础高度均为 48px，输入控件计算高度为 38px；同行控件/复选命中区中心差 ≤1px；标准表错误段落（`td.col-name` 内的 `.row-issue`）、创建表 `.row-issues` 出现时该行增高且文案、输入、操作按钮无裁切，**且该行内所有 38px 控件与复选命中区的垂直中点差仍 ≤1px**（出错行整行同档对齐，见 Step 2）。运行两份目标 e2e，确认新断言 RED。
- [ ] **Step 2（GREEN）**：新增 48px 组件令牌，普通 `th/td` 显式 `height`、`vertical-align:middle` 和同档令牌化 padding。出错行**不得只让出错格取 `top`**：行被错误文案撑高后，兄弟格仍 `middle` 会把同行输入中心错开（行高约 68px 时约 11px，超出 SPEC-DM-006 §6.4 的 ±1px）。实现给出错行加行级类（如 `tr.has-issue`），用一条 `tr.has-issue>td{vertical-align:top}` 整行切换，使该行所有 38px 控件顶边对齐；`middle`/`top` 仍只有这两种取值，不引入第三种。保留标准表 16×16 复选框本体、≥32px 命中区及创建表 32px 行操作轨，不为满足高度指标拉伸控件。
- [ ] **Step 3（验证/提交）**：运行两份目标 e2e、`rtk npm --prefix web run check:ui` 和生产构建；在 900×768/1440×900 及 200% 浏览器缩放检查编辑控件可达、无页面级横溢；清退对应例外，提交信息：`落实表格编辑行四十八像素档`。

### Task 4：其余标准、创建与目录只读表

**Files:** `web/src/components/standards/AssetInspectionPanel.vue`、`web/src/components/creation/ReviewStep.vue`、`web/src/components/creation/SheetValuesDialog.vue`、`web/src/components/sheet-catalog/CatalogPreview.vue`；测试为 `web/tests/e2e/standards-assets-publish.spec.ts`、`create-sheetset-review.spec.ts`、`sheet-catalog.spec.ts`；更新例外表。

- [ ] **Step 1（RED）**：先给 `AssetInspectionPanel.vue` 的 `.layout-table`、`SheetValuesDialog.vue` 的 `.values-table` 与 `CatalogPreview.vue` 的预览表补稳定锚点（`data-testid` 或可访问名），再在目标 e2e 断言四张表普通 `th/td` 消费 44px 档（`--sheet-table-row-height`）、表头与无增高的普通行同时钉令牌名与计算绝对值 `44px`（口径同 `sheets-layout.spec.ts:609` 的绝对锚，使令牌取值变化能被测试发现）、普通格 padding 同档且令牌化、`vertical-align` 显式取 `middle`、表头随列数据对齐；`AssetInspectionPanel` 的 `td.panel-note[colspan=2]` 空态说明行按普通格同档 padding 计数、不因 `colspan` 放行；创建预览的 `sheet_count` 作为可比较数值右对齐并启用 `tabular-nums`，图号/范围仍按文本左对齐；长布局名、诊断摘要在内容增高时不裁切（数据行断言 **≥44px 且消费该档**，不断言恰好 44px）。运行对应 e2e 确认 RED。
- [ ] **Step 2（GREEN）**：只在所属组件 scoped 样式声明表格基础格规则，把 44px 行高、同档令牌化 padding、`vertical-align` 一并显式声明，移除对 `legacy.css` 的 `9px` + 顶端对齐依赖；为真正多行内容格限定 `top`，普通格用 `middle`。目录预览列值由用户模板决定，不根据字符串外观推断数值列；只有有确定类型的列使用数值对齐（本轮 `CatalogPreview` 无确定类型列，只收口基础格规则）。
- [ ] **Step 3（验证/提交）**：运行三份目标 e2e 与 `check:ui`，清退对应例外；提交信息：`收口标准创建与目录表格对齐`。

### Task 5：预览、任务与修订旧表及全局验证

**Files:** `web/src/components/PreviewPanel.vue`、`web/src/components/JobStatusPanel.vue`、`web/src/components/RevisionHistoryPanel.vue`、`web/src/styles/legacy.css`、`web/src/i18n/locales/zh-CN/jobs.ts`、`web/src/i18n/locales/en-US/jobs.ts`、`web/tests/e2e/main.spec.ts`、`web/scripts/ui-contract-exceptions.json`；按实际覆盖更新其它相关 e2e 与 `changelog.md`。

- [ ] **Step 1（RED）**：在既有流程夹具中断言三个旧组件（`PreviewPanel.vue` 8 张、`JobStatusPanel.vue` 与 `RevisionHistoryPanel.vue` 各 1 张）的普通 `th/td` 显式消费 44px 档（`--sheet-table-row-height`）并在同一断言处钉计算绝对值 `44px`，表头同档、中部对齐并令牌化同档 padding（含 36px 按钮的行会按内容增到 ≥44px，属允许增高）；任务进度/耗时与预览影响张数右对齐且 `tabular-nums`，进度表头带 `%`、耗时表头带 `ms` 且对应单元格只输出同列一致的数值格式，修订 ID、哈希、文件路径左对齐；任务日志跨列详情按内容增高且可展开阅读。运行目标 e2e 确认 RED。
- [ ] **Step 2（GREEN）**：三个组件都**新建 `<style scoped>`**（当前没有样式块），把单元格几何放回各自组件并显式重声明 `legacy.css` 现在提供的一切：`width:100%`、`border-collapse:collapse`、`border-bottom`、`text-align`、44px 行高与 `vertical-align:middle`；`PreviewPanel.vue` 的 8 张表按列给类名（影响张数、SHA-256、路径、布局名等）。更新任务表中英文列名及单元格格式（底层数值不变），并把随之失去引用的 `jobs.files.durationMs` 从 `zh-CN/jobs.ts` 与 `en-US/jobs.ts` 一并删除（`check:i18n` 不检查未使用键，需人工清理）；`JobStatusPanel.vue` 任务摘要行里的 `{{job.progress}}%` 不是表格单元格，本任务不改。跨列日志详情若需要零 padding，按 Task 1 的 `STRUCTURAL_CELL_PAIRS` 机制登记并给内层容器令牌化间距，不做通用 `colspan` 放行。
- [ ] **Step 3（legacy 收口）**：本轮 18 张表全部迁移完成后，`legacy.css` 的 `:where(#app) th,:where(#app) td` 规则已无消费者，本任务按 ARCH-DM-007 §7 处置——优先直接删除该条（相邻的 `table` 与 `td input` 规则不在本任务范围，删除前用检查器确认消费者）；若因尚未迁移的页面必须保留，则把到期条件写成“ARCH-DM-007 §7 第 5 项页面迁移完成时”并登记为有到期条件的例外，不接受无到期条件的白名单。
- [ ] **Step 4（全量验证）**：运行 `rtk npm --prefix web run test:contracts`、`test:unit`、`build`、`test:e2e`，以及 `rtk uv run ruff check .` 与受影响的 pytest（若无 Python 改动，记录无相关用例）；删除 legacy 规则后重跑生产构建与全量 e2e，确认 18 张表几何无回归。补 100/125/150/200% Windows WebView2 的代表性表格人工复验；环境缺失时按 ARCH-DM-007 §12 **保持 `active`** 并明记缺口，不声称通过。复核例外清单无本计划到期项、18 张表逐张有 44px/48px 档证据且 `git diff --check` 通过；提交信息：`完成表格对齐契约前端收口`。

## 风险与处置

- 浏览表原有 `10px 8px` padding 未落在 4px 刻度的单一纵横档；令牌化可能改变列宽或 44px 实际行高。先量现状和固定列几何，再在该表组件令牌中选择能保留视觉的值，禁止用裁切强压 44px。
- CSS 选择器静态解析不能证明最终计算样式；静态门禁只守声明与例外边界，真实行高、中心点和表头方向由 Playwright 断言。变异测试必须证明违规会失败，不能仅打印警告。
- 当前 `legacy.css` 对旧表统一 `vertical-align:top`；迁移时应显式限定组件覆盖，并在最后确认旧规则清退不会改变非目标页面。三个旧页面组件没有样式块，删除全局规则与新建组件规则必须同批完成，分批会出现中间提交里表格丢边框/掉宽度的回归。
- 静态门禁只能约束**已声明**的 `th/td` 规则，管不到“完全没有规则、只能继承 `legacy.css`”的表格（`CatalogPreview`、`JobStatusPanel` 日志格）。这类表格的 44px 命中与 `middle` 对齐只能由 Task 4/5 的 Playwright 断言提供证据，计划、提交说明和完成标准都不得声称已被静态门禁覆盖。
- **已裁决的语义借用（方案 A，2026-09-26 用户确认）**：`--sheet-table-row-height` 不是语义中立令牌，却被创建向导、标准、目录预览与三张旧表消费。后果：将来若图纸页把该令牌改成非 44px 或可切换值（例如启用 SPEC-DM-006 §5.3 的 32px 紧凑档），这 7 个组件的行高会跟着漂移，而 `check:ui` 不会报错（它只检查“是否消费令牌”，不看令牌语义，见 ARCH-DM-007 §4.1「语义说谎」条）。处置：① Task 4/5 的断言在钉令牌名的同时**钉计算绝对值 `44px`**（口径同 `sheets-layout.spec.ts:609`），使令牌取值变化能被测试发现；② 任何改动 `--sheet-table-row-height` 语义或取值的工作，必须先修订 SPEC-DM-006 §5.3、ARCH-DM-007 §4.3 与 `tokens.css` 头注释，并在独立任务里同步改 7 个组件的消费语句与本轮新增断言；③ 本轮不新增第三种 44px 令牌（方案 B 会造出 3 份同值定义，方案 C 会扩大到两个已验收页面）；新增 `--editable-table-row-height` 时同步补 `tokens.css` 头注释的组件层尺寸清单。
- 内容驱动高度与大量行的滚动可能改变视口内可见行数；保持既有分页/滚动行为，检查长文本、错误态及缩放，不把截图差异直接当作业务回归。

## 验证命令

- 静态规则和变异：`rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run check:ui`。
- 前端回归与构建：各任务列明的 `rtk npm --prefix web run test:e2e -- tests/e2e/<目标文件>.spec.ts`；最终运行 `rtk npm --prefix web run test:unit`、`rtk npm --prefix web run build`、`rtk npm --prefix web run test:e2e`。
- 仓库检查：`rtk uv run ruff check .`、`rtk git diff --check`；若实施中修改 Python，再运行相关 pytest，且不以 Ruff 代替测试。

## 完成标准与实际验证

- [ ] 上述五个 Task 的 RED/GREEN、提交与对应验证命令、结果、日期已逐项记录。
- [ ] 18 张用户可见表逐张有明确基础档（2 张常驻编辑表 48px，其余 16 张 44px）与消费的令牌名、单元格 padding 与垂直对齐；48px 编辑表、出错行增高与结构性零 padding 例外都有浏览器几何证据。
- [ ] `check:ui` 的新增规则及变异测试、生产构建、相关及全量 Playwright、Ruff 通过；`legacy.css` 的 `th,td` 规则已删除或已登记带到期条件的例外；任何 pytest/真实桌面缺口如实登记。
- [ ] 真实 Windows WebView2 100/125/150/200% 复验通过后才把状态改为 `completed`（[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §12）；桌面复验缺失时保持 `active` 并把缺口写入验证表，不得以自动化证据代替真实缩放结论；实施期间保持 `active`，未开始前保持 `proposed`。

| 日期 | Task | RED 证据 | GREEN 与回归命令/结果 | 仍待验证 |
| --- | --- | --- | --- | --- |
| 2026-09-26 | Task 1 建立表格静态契约与迁移基线 | 新增 13 条用例在规则未实现时 `pass 4 / fail 9`（exit 1） | `test:contracts` **114 passed / 0 failed**（含 5 条 CLI 级变异）；`check:ui` exit 0，27 条存量违规已登记 | Task 2–5 样式与计算样式断言；真实桌面缩放复验 |

### Task 1 执行记录（2026-09-26，分支 `feature/plan-dm-043-table-alignment`）

- **RED**：新增 `describe("表格单元格对齐与 padding 契约")` 13 条用例（`web/scripts/check-ui-contracts.test.mjs`），规则未实现时 `node --test --test-name-pattern="表格单元格对齐与 padding 契约"` → `tests 13 / pass 4 / fail 9`（exit 1），失败信息均为「期望恰好 1 条 table-cell-*，实际：[]」。
- **GREEN**：新建 `web/scripts/ui-contracts/table-cells.mjs`（两条规则 + `STRUCTURAL_CELL_PAIRS`），并把 `tableCellVerticalAlign`/`tableCellPadding` 接入 `types.mjs` 与 `check-ui-contracts.mjs` 的第四遍扫描；同一筛选 → `pass 13 / fail 0`；`rtk npm --prefix web run test:contracts` → **114 passed / 0 failed**。
- **CLI 级变异证据**：新增 5 条注入并入既有「每类判定都有 CLI 级变异证据」清单（分类数 15 → 20、注入数 17 → 22、规则集合 14 → 16）：表格单元格缺 vertical-align、表格单元格裸 padding、同表普通格两档 padding、普通单元格零 padding、伪造 colspan 零 padding——均实测真实子进程 exit 1 且输出含对应规则标签；恢复夹具后 exit 0。
- **真实仓库变异探针**：临时新增 `src/components/__tmp_plan043_probe.vue`（普通表+ `padding:12px 6px`）后 `check:ui` exit 1 并报 `[table-cell-padding] … 禁止裸值`；删除探针后 exit 0（探针未进入提交树）。
- **迁移基线（11 个含表格组件 + legacy 兜底，逐条量取声明值）**：

| 组件 | th/td 规则 | padding 现状 | vertical-align 现状 | 行高现状 |
| --- | --- | --- | --- | --- |
| `SheetTable.vue` | 9 | 主规则 `10px 8px`（裸值）；结构行 `0` | 主规则 `middle`；7 条辅助规则缺声明 | `--sheet-table-row-height`（44px）；结构行 `auto` |
| `PropertyDefinitionTable.vue` | 7 | 主规则 `10px 8px`（裸值） | 主规则 `middle`；6 条缺声明 | `--definition-row-height`（44px） |
| `OrdinaryPropertyEditor.vue` | 2 | `var(--space-1)` | 主规则 `top`；表头规则缺声明 | 无声明（内容驱动） |
| `GroupsStep.vue` | 2 | `var(--space-1)` | 主规则 `top`；表头规则缺声明 | 无声明 |
| `AssetInspectionPanel.vue` | 2 | `var(--space-1)` | 2 条均缺声明 | 无声明 |
| `ReviewStep.vue` | 3 | `var(--space-1)` | 主规则 `top`；2 条缺声明 | 无声明 |
| `SheetValuesDialog.vue` | 3 | `var(--space-1)` | 3 条均缺声明 | 无声明 |
| `CatalogPreview.vue` | 1 | 未声明（继承 legacy `9px`） | 缺声明 | 无声明 |
| `PreviewPanel.vue` | 0 | 继承 legacy `9px` | 继承 legacy `top` | 无声明 |
| `JobStatusPanel.vue` | 0 | 同上 | 同上 | 无声明 |
| `RevisionHistoryPanel.vue` | 0 | 同上 | 同上 | 无声明 |
| `legacy.css`（全局兜底） | 1 | `9px`（裸值） | `top`（取值为合规项） | 无声明 |

  结论：命中 44px 档的只有图纸/属性两个主表；其余 9 个组件的 16 张表全部无 `height` 声明（Task 3 的 2 张按 48px 档、Task 4/5 的 14 张按 44px 档），与「18 张表全部命中一档」的待办一致。零 padding 结构配对实测通过：`SheetTable.vue` 的 `.sheet-editor-row>td` ↔ `src/components/sheets/SheetPropertyEditor.vue` 的 `.sheet-property-editor`（`padding:var(--space-4)`）。
- **棘轮基线**：存量违规 **27 条**（`table-cell-vertical-align` 24 条、`table-cell-padding` 3 条）已按「文件 + 稳定语义」登记进 `ui-contract-exceptions.json`（总条目 10 → 37），到期任务分布：Task 2 **16 条**、Task 3 **2 条**、Task 4 **8 条**、Task 5 **1 条**；`rtk npm --prefix web run check:ui` → exit 0。指纹不含行号，各 Task 清退时以检查器输出重新生成该文件条目。
- **仍待验证**：Task 2–5 的样式改动与 Playwright 计算样式断言；真实 Windows WebView2 100/125/150/200% 复验。

## 修订记录

- 2026-09-26（审查修订）：按计划审查意见修订九处。① 目标、全局约束与 Review Focus 明确“11 个含 `<table>` 的组件 / 18 张表”的完整口径（原文只给主表与编辑表写了行高指令，其余 7 个组件会在改完 padding 后仍停在内容高度）；并写明跨页只读表按 ARCH-DM-007 §4.3 消费既有 `--sheet-table-row-height`，本轮不新造 44px 令牌。② Task 4/5 补 44px 行的实现与断言，并把数据行断言改为“消费 44px 档且 ≥44px”，不再要求恰好 44px（属性定义表表体行被展开/删除按钮撑高、含 36px 按钮的行会到 45px；同一口径已在 Task 2、Task 4、Task 5 三处一致写明）。③ Task 5 明确三个旧组件需新建 `<style scoped>` 并重声明 legacy 现状声明，`PreviewPanel` 的 8 张表按列给类名，并新增 Step 3 决定 `legacy.css` 的 `th,td` 规则删除或登记到“§7 第 5 项完成”为止的到期条件。④ Task 1 把结构放行落到 `table-cells.mjs` 的 `STRUCTURAL_CELL_PAIRS`（例外表字段被 `REQUIRED_EXCEPTION_FIELDS` 固定，无法承载跨组件内层校验），消除“配对放行/登记豁免”两处口径分歧。⑤ Task 3 出错行改为整行 `tr.has-issue>td` 切 `top`，并在出错行补 ±1px 中心对齐断言（原口径在行高约 68px 时会错开约 11px）。⑥ Review Focus #5/#6 改为准确口径：静态门禁只管已声明的 `th/td` 规则，无规则的表格只能由浏览器断言兜底。⑦ Task 5 补 `jobs.files.durationMs` 死键清理与“任务摘要行不在口径内”说明，Task 3/4 补三个目标表的 e2e 锚点。⑧ 完成标准与 ARCH-DM-007 §12 对齐（桌面复验缺失时保持 `active`），并补 SPEC-DM-012 引用、`§7` 顺序偏差说明与跨列结构单元格三处清单。⑨ 按 2026-09-26 用户裁决固化令牌归属（**方案 A**：7 个组件的只读表与旧表消费既有 `--sheet-table-row-height`，不新增 44px 令牌、不改 SPEC-DM-006 §5.3 与 ARCH-DM-007 §4.3 正文），并把该跨页语义借用登记为有界风险：Task 4/5 断言在钉令牌名的同时钉计算绝对值 `44px`（口径同 `sheets-layout.spec.ts:609`），后续改动该令牌语义或取值必须在独立任务里同步改 7 个组件与新增断言。
