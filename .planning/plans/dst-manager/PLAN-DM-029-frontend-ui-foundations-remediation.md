---
id: PLAN-DM-029
title: 前端视觉基础与一致性整改实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-14
updated: 2026-09-14
related:
  - ARCH-DM-007
  - SPEC-DM-006
  - SPEC-DM-009
  - SPEC-DM-010
  - SPEC-DM-011
  - SPEC-DM-012
  - GUIDE-DM-001
  - GUIDE-DM-002
  - PLAN-DM-015
  - PLAN-DM-016
  - PLAN-DM-017
  - PLAN-DM-023
---

# 前端视觉基础与一致性整改实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除用户截图中局部控件“视觉上大一号”的根因，建立可持续的字体、尺寸、图标、样式作用域与无障碍基础，并在不改变既有业务契约的前提下完成全前端渐进迁移。

**Architecture:** 严格执行 `1 基线与门禁 → 2 公共原语 → 3 页面迁移 → 4 结构治理 → 5 验收闭环`。全局样式拆为 `tokens/reset/primitives/legacy` 四层；迁移页面只消费公共原语和已声明令牌；静态检查采用“已知债务基线 + 新增即失败 + 迁移即清退”的棘轮机制；页面迁移顺序固定为属性页、图纸目录页、图纸页与任务浮层、设置中心、旧页面。

**Tech Stack:** Vue 3、TypeScript、Vite、Vitest、`@vue/test-utils`、happy-dom、Playwright、CSS Cascade Layers、本地 WOFF2 字体与本地 SVG 图标；后端仅执行既有 Ruff/pytest 回归，不修改 HTTP/SSE、DST、DWG 或发布事务。

**Spec:** 权威架构为 [ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md)；用户可见规则分别以 [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md)、[SPEC-DM-009](../../../docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md)、[SPEC-DM-010](../../../docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md)、[SPEC-DM-011](../../../docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md) 与 [SPEC-DM-012](../../../docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md) 为准；实施和验收门禁分别遵循 [GUIDE-DM-001](../../../docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md) 与 [GUIDE-DM-002](../../../docs/dst-manager/guides/GUIDE-DM-002-frontend-gates-plain-language.md)。

## Global Constraints

- 开始每个任务前执行 `rtk git status --short`，保留用户已有改动；只暂存该任务列出的文件。
- 每个实现任务遵循 RED → GREEN → REFACTOR；先看到目标测试因预期原因失败，再做最小实现，最后运行任务级回归。
- 不改变组件公开 props/emits、API 请求、i18n key、草稿命令、错误码、序列化结构或用户流程；如必须改变业务行为，停止实施并另立 Spec/ADR。
- `web/src/style.css` 最终只保留四个 `@import`；级联固定为 `@layer tokens, reset, primitives, legacy`。Vue SFC 的页面布局样式保持 scoped/unlayered，不新建 `components` layer，不以 specificity 竞赛覆盖原语。
- 普通控件 `36px`、表单输入 `38px`、紧凑工具栏 `34px`、图标按钮不小于 `36×36px`、所有可点目标高度不小于 `32px`；SPEC 已批准的例外必须登记原因和清退条件。
- Inter 与 IBM Plex Mono 只打包 Basic Latin、Latin-1 Supplement 和界面实际通用标点，不含 CJK；两套生产 WOFF2 合计不超过 `250 KiB`，许可证随资产入库，运行时不得访问 CDN。
- 图标只接受 `UiIconName` 联合类型中的本地 SVG；不允许任意 HTML/SVG 注入。`ColumnEditor.vue` 的 `↑ / ↓ / ✕` 是唯一初始用户可见临时例外，复核前保持行为与外观。
- 每页持久截图控制在 `4–6` 张，全轮新增基准控制在 `24–30` 张；其余状态以行为和计算样式断言覆盖。浏览器 `zoom` 只做韧性测试，不能替代 Windows 显示缩放验收。
- 阶段 4 必须等待阶段 3 全部完成；不得与页面迁移并行修改 `App.vue`、`SheetTree.vue`、`TopBar.vue`、`TaskOverlay.vue` 或直接依赖。
- 每个任务完成后更新本计划勾选项与“实际验证”表，并在根 `changelog.md` 当前日期下追加可核验证据；commit message 使用简体中文动词短语。

## 阶段 1：基线、令牌与自动门禁

### Task 1: 建立可变异验证的 UI 静态契约检查器

**Files:**

- Create: `web/scripts/ui-contracts/types.mjs`
- Create: `web/scripts/ui-contracts/css-vars.mjs`
- Create: `web/scripts/ui-contracts/vue-source.mjs`
- Create: `web/scripts/ui-contracts/visual-values.mjs`
- Create: `web/scripts/check-ui-contracts.mjs`
- Create: `web/scripts/check-ui-contracts.test.mjs`
- Create: `web/scripts/ui-contract-exceptions.json`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/src/layout/TaskOverlay.vue`

- [x] **Step 1（RED）**：用 Node 内置 `node:test` 写临时目录夹具，覆盖未定义变量、嵌套 fallback 未定义、循环引用、动态变量缺生产者、按钮无 `type`、搜索输入无可见 label、图标按钮无可读名称、Unicode 结构图标、裸全局选择器、未登记十六进制色和裸字号/高度/圆角/图标尺寸；运行 `rtk npm --prefix web run test:contracts`，确认命令缺失或断言失败。
- [x] **Step 2（接口）**：实现 `collectUiContractViolations(options): Violation[]`，其中 `Violation` 固定为 `{rule, file, line, column, message, fingerprint}`；CLI 无违规返回 0，有违规按 `file:line:column [rule] message` 输出并返回 1。
- [x] **Step 3（CSS 变量）**：实现平衡括号解析，不用单层正则处理 `var()`；递归解析 fallback、检测循环，并让动态白名单条目必须同时包含 `variable`、`producer`、`consumer`、`reason`、`expiresWith`。
- [x] **Step 4（Vue/视觉规则）**：实现 `explicit-button-type`、`visible-input-label`、`icon-button-name`、`unicode-structure-icon`、`global-selector-in-component`、`raw-hex-color`、`raw-visual-value`；对 `style`、模板和脚本分别定位，不扫描 i18n 文案中的普通标点。
- [x] **Step 5（棘轮）**：把现存违规逐条写入 `ui-contract-exceptions.json`，fingerprint 必须含规则、文件和稳定语义，不使用纯行号；检查器同时拒绝“未登记新违规”和“已不再命中的过期例外”。
- [x] **Step 6（先修确定缺陷）**：将 `TaskOverlay.vue` 的未定义 `--color-border`、`--color-bg-surface-2` 替换为 ARCH-DM-007 已声明语义令牌，不为这两项建立例外。
- [x] **Step 7（接入）**：新增 `check:ui` 与 `test:contracts` scripts；`build` 顺序固定为 `check:api → check:i18n → check:ui → vue-tsc → vite build`。
- [x] **Step 8（变异证据）**：测试中依次向合法夹具注入 Step 1 所列每类违规并断言每类都使 CLI 退出 1；恢复夹具后断言退出 0。该测试仅在检查器、规则或例外格式变化时要求重跑。
- [x] **Step 9（验证）**：运行 `rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run build`，确认检查器测试通过且现仓库只因已登记债务而通过。
- [x] **Step 10（提交）**：只提交本任务文件，commit：`建立前端 UI 静态契约门禁`。

### Task 2: 拆分全局样式并落地字体、尺寸和主题令牌

**Files:**

- Create: `web/src/styles/tokens.css`
- Create: `web/src/styles/reset.css`
- Create: `web/src/styles/primitives.css`
- Create: `web/src/styles/legacy.css`
- Create: `web/src/assets/fonts/InterLatin.woff2`
- Create: `web/src/assets/fonts/IBMPlexMonoLatin.woff2`
- Create: `web/src/assets/fonts/OFL-Inter.txt`
- Create: `web/src/assets/fonts/OFL-IBM-Plex-Mono.txt`
- Modify: `web/src/style.css`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `web/scripts/check-ui-contracts.test.mjs`

- [ ] **Step 1（资产核验）**：从 Inter 与 IBM Plex Mono 官方 OFL 发行物生成/选取 WOFF2 拉丁子集；记录字符范围 `U+0020–007E,U+00A0–00FF` 和实际标点；检查文件合计大小不超过 `256000` 字节，许可证文本与字体一同入库。
- [ ] **Step 2（RED）**：在 `main.spec.ts` 增加根计算样式断言：正文 `14px/21px`、首选字体含 `Inter`，等宽探针含 `IBM Plex Mono`，`button/input/select/textarea` 均继承字体；确认当前基线失败。
- [ ] **Step 3（令牌）**：建立 primitive → semantic → component 三层变量，至少覆盖字体、12/13/14px 字号、34/36/38px 高度、32px 点击下限、36px 图标按钮、间距、圆角、边框、焦点、状态色和图标尺寸；浅/深主题只在 `tokens.css` 映射。
- [ ] **Step 4（重置）**：在 `reset.css` 设置 `box-sizing`、body margin、继承字体、`:focus-visible` 和 `prefers-reduced-motion`；确保字体失败时仍由固定高度/line-height 保持盒模型。
- [ ] **Step 5（分层）**：把 `style.css` 内容无行为变化地迁入四层，`style.css` 只保留层顺序声明和四个导入；既有全局业务选择器全部置于有根类限定的 `legacy.css`。
- [ ] **Step 6（字体规则）**：添加本地 `@font-face`、`font-display: swap` 和 unicode-range；路径/哈希/错误码等宽区域改消费 `--font-mono`，中文继续回落 `Microsoft YaHei, system-ui`。
- [ ] **Step 7（门禁收紧）**：检查器增加字体文件存在、不得远程 URL、体积预算、`style.css` 仅入口的断言；清退已被本任务关闭的 raw visual/global selector 例外。
- [ ] **Step 8（GREEN）**：运行 `rtk npm --prefix web run test:e2e -- main.spec.ts`、`rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run build`。
- [ ] **Step 9（提交）**：commit：`统一前端字体令牌与样式分层`。

## 阶段 2：公共视觉原语与壳层纵向验证

### Task 3: 实现按钮、图标、输入、字段和焦点原语

**Files:**

- Create: `web/src/components/ui/UiButton.vue`
- Create: `web/src/components/ui/UiIconButton.vue`
- Create: `web/src/components/ui/UiIcon.vue`
- Create: `web/src/components/ui/icons.ts`
- Create: `web/src/components/ui/UiInput.vue`
- Create: `web/src/components/ui/UiSelect.vue`
- Create: `web/src/components/ui/FormField.vue`
- Create: `web/src/components/ui/dialogFocus.ts`
- Create: `web/src/components/ui/uiPrimitives.test.ts`
- Create: `web/src/components/ui/dialogFocus.test.ts`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

- [ ] **Step 1（测试环境）**：用 `rtk npm --prefix web install --save-dev @vue/test-utils happy-dom` 更新两份依赖清单；组件测试文件使用 `// @vitest-environment happy-dom`，不改变现有测试默认环境。
- [ ] **Step 2（RED：组件契约）**：先写失败测试，覆盖 `UiButton` 的 `primary/secondary/danger/link`、`default/compact`、disabled/loading 与默认 `type=button`；`UiIconButton` 缺 `label` 时类型/运行期失败；`FormField` 的 label、hint/error ID 与 `aria-describedby` 关联。
- [ ] **Step 3（RED：焦点契约）**：为 `dialogFocus.ts` 写初始焦点、Tab/Shift+Tab 圈闭、Escape 回调、关闭后焦点归还和无可聚焦元素五类失败测试。
- [ ] **Step 4（图标注册表）**：在 `icons.ts` 导出封闭的 `UiIconName` 与 SVG path 数据；首批名称固定为 `theme`、`settings`、`close`、`chevron-left/right/up/down`、`status-dot`、`search`、`folder`、`copy`，记录 Lucide MIT 来源，不接受任意字符串或 `v-html`。
- [ ] **Step 5（GREEN：视觉原语）**：实现各组件，只处理语义、外观、焦点和状态；尺寸通过 variant 和 CSS 自定义属性消费 Task 2 令牌，不导入业务 composable 或 API 类型。
- [ ] **Step 6（GREEN：焦点工具）**：导出 `useDialogFocus({open, container, initialFocus, onEscape})`，返回 `onDialogKeydown`；工具只管理焦点，不决定是否可关闭。
- [ ] **Step 7（验证）**：运行 `rtk npm --prefix web run test:unit -- src/components/ui/uiPrimitives.test.ts src/components/ui/dialogFocus.test.ts`、`rtk npm --prefix web run build`。
- [ ] **Step 8（提交）**：commit：`新增前端公共视觉与焦点原语`。

### Task 4: 用壳层完成原语纵向验证

**Files:**

- Modify: `web/src/layout/TopBar.vue`
- Modify: `web/src/layout/TabBar.vue`
- Modify: `web/src/layout/ActionDock.vue`
- Modify: `web/src/layout/TaskOverlay.vue`
- Modify: `web/src/components/ui/ToastHost.vue`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `web/tests/e2e/i18n-visual-evidence.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [ ] **Step 1（RED）**：在 `main.spec.ts` 增加壳层按钮计算样式、图标 accessible name、装饰图标 `aria-hidden`、最小点击面积、键盘焦点和任务浮层折叠状态断言；确认 Unicode 图标和尺寸断言失败。
- [ ] **Step 2（迁移）**：把 `◐`、`⚙`、`✕`、`▸/▾`、`«/»`、`●` 替换为 `UiIcon`/`UiIconButton`；保留可见文案和 i18n key，状态按钮补 `aria-expanded`/`aria-pressed`。
- [ ] **Step 3（尺寸）**：壳层普通按钮使用 `default`，任务浮层紧凑动作使用 `compact`；所有独立图标按钮达到 `36×36px`，不以 SVG 尺寸充当点击面积。
- [ ] **Step 4（例外清退）**：删除上述壳层 Unicode 例外；运行检查器并确认只剩页面级债务和 `ColumnEditor.vue` 临时例外。
- [ ] **Step 5（证据）**：在 `1440×900` 浅/深主题各保留壳层默认截图，在 `900×768` 保留窄视口一张，并用计算样式覆盖 hover/focus/disabled，不额外保存状态截图。
- [ ] **Step 6（验证）**：运行 `rtk npm --prefix web run test:e2e -- main.spec.ts i18n-visual-evidence.spec.ts`、`rtk npm --prefix web run test:unit`、`rtk npm --prefix web run build`。
- [ ] **Step 7（提交）**：commit：`迁移桌面壳层到统一视觉原语`。

## 阶段 3：按固定顺序迁移页面

### Task 5: 迁移属性页并关闭用户截图中的字号突增

**Files:**

- Modify: `web/src/views/PropertiesView.vue`
- Modify: `web/src/components/properties/PropertyDefinitionPanel.vue`
- Modify: `web/src/components/properties/PropertyDefinitionTable.vue`
- Modify: `web/src/components/properties/PropertyCsvPanel.vue`
- Modify: `web/src/components/properties/PropertyValuePanel.vue`
- Modify: `web/src/components/properties/PropertyValueCompareDialog.vue`
- Modify: `web/tests/e2e/properties-layout.spec.ts`
- Modify: `web/tests/e2e/properties-visual-evidence.spec.ts`
- Modify: `web/tests/e2e/properties-definitions.spec.ts`
- Modify: `web/tests/e2e/properties-values.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [ ] **Step 1（RED）**：扩充计算样式断言，明确截图红框内折叠标题、导入导出、搜索、主次动作的 `font-size/font-family/line-height/height/padding/radius`；搜索框必须有可见弱化 label；确认当前原生 16px 泄漏失败。
- [ ] **Step 2（原语迁移）**：按钮、输入、选择器和字段组合改用公共原语；生产输入继续保持 SPEC-DM-010 的 `38px`，不得为统一而降为 36px。
- [ ] **Step 3（层级收敛）**：折叠标题、计数、状态徽标、工具行和主按钮分别消费 label/caption/body/action 语义令牌；移除局部重复字体、盒模型和焦点样式。
- [ ] **Step 4（行为回归）**：验证字段定义展开、新增字段、CSV 导入导出、搜索、对照、撤回和更新图纸集行为及 accessible name 不变。
- [ ] **Step 5（正交证据）**：持久保存浅色默认、深色默认、错误态、`900×768` 单列、200% 定义表溢出共 5 张；其余状态沿用行为/计算样式断言。
- [ ] **Step 6（例外清退）**：删除属性页 raw size、裸颜色、无 label、按钮 type 等全部例外；检查器对属性目录零例外。
- [ ] **Step 7（验证）**：运行 `rtk npm --prefix web run test:e2e -- properties-layout.spec.ts properties-visual-evidence.spec.ts properties-definitions.spec.ts properties-values.spec.ts` 与 `rtk npm --prefix web run build`；人工对照用户第 3 张截图，确认同层级控件不再突大且主次层级清晰。
- [ ] **Step 8（提交）**：commit：`统一属性页控件视觉基础`。

### Task 6: 迁移图纸目录页并复核历史图标例外

**Files:**

- Modify: `web/src/views/SheetCatalogView.vue`
- Modify: `web/src/components/sheet-catalog/CatalogActions.vue`
- Modify: `web/src/components/sheet-catalog/CatalogPreview.vue`
- Modify: `web/src/components/sheet-catalog/ColumnEditor.vue`
- Modify: `web/src/components/sheet-catalog/FieldBrowser.vue`
- Modify: `web/src/components/sheet-catalog/TemplateBar.vue`
- Modify: `web/tests/e2e/sheet-catalog.spec.ts`
- Modify: `web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [ ] **Step 1（RED）**：针对截图红框内保存/另存/删除、添加输出列、导出 XLSX 写计算样式和对齐断言；覆盖 disabled、danger、primary 层级和可见 label。
- [ ] **Step 2（迁移）**：工具栏、列编辑器和预览动作改用公共原语；保持字段拖插、表达式、模板保存、预览刷新和 XLSX 导出契约不变。
- [ ] **Step 3（图标复核）**：对 `ColumnEditor.vue` 的 `↑ / ↓ / ✕` 做同状态截图与键盘行为对照；若 SVG 在辨识度与行为上等价或更好则迁移并删除例外，否则保留原字符但补齐 `type`、accessible name、点击面积，并把例外到期条件改为下一次目录页视觉 Spec 修订。
- [ ] **Step 4（字体复核）**：对表达式等宽字体、长列名、50 列计数和表格横向溢出做布局断言，确认 IBM Plex Mono 不造成截断或动作列覆盖。
- [ ] **Step 5（正交证据）**：保存浅/深默认、禁用保存、删除危险态、窄屏溢出共 5 张。
- [ ] **Step 6（例外清退）**：除经 Step 3 复核保留的唯一条目外，图纸目录目录零例外。
- [ ] **Step 7（验证）**：运行 `rtk npm --prefix web run test:e2e -- sheet-catalog.spec.ts sheet-catalog-visual-evidence.spec.ts`、`rtk npm --prefix web run build`；人工对照用户第 2 张截图。
- [ ] **Step 8（提交）**：commit：`统一图纸目录页控件视觉基础`。

### Task 7: 迁移图纸页与任务浮层内部控件

**Files:**

- Modify: `web/src/views/SheetsView.vue`
- Modify: `web/src/components/sheets/SheetToolbar.vue`
- Modify: `web/src/components/sheets/ColumnSettings.vue`
- Modify: `web/src/components/sheets/SheetOperationForm.vue`
- Modify: `web/src/components/sheets/SheetPropertyEditor.vue`
- Modify: `web/src/components/SheetTable.vue`
- Modify: `web/src/layout/TaskOverlay.vue`
- Modify: `web/tests/e2e/sheets-layout.spec.ts`
- Modify: `web/tests/e2e/sheets-forms.spec.ts`
- Modify: `web/tests/e2e/sheets-visual-evidence.spec.ts`
- Modify: `web/tests/e2e/sheets-visual-regressions.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [ ] **Step 1（RED）**：为截图第 1 张的批量模式、属性选择、批量值、批量加入草稿写同行中心、字号、36/38px 档位、disabled 与长文本溢出断言；补任务浮层动作与状态控件断言。
- [ ] **Step 2（迁移）**：工具栏、表单、列设置、属性编辑、表格动作和浮层内部动作改用原语；保持选中、批量修改、草稿与任务 SSE 流程不变。
- [ ] **Step 3（动态变量）**：对图纸树宽度等运行时 CSS 变量，在白名单中同时登记写入方与消费方；能改为静态令牌的变量立即清退，不以 fallback 隐藏未定义变量。
- [ ] **Step 4（密集布局）**：在 `900/1024/1120/1440` 四视口验证批量编辑区不撑破表格、操作列可达、横向滚动条不遮挡内容；关键控件 200% 浏览器韧性测试通过。
- [ ] **Step 5（正交证据）**：保存浅/深默认、批量编辑启用、批量编辑禁用、最窄视口、200% 共 6 张。
- [ ] **Step 6（例外清退）**：除阶段 4 专门处理的 `SheetTree.vue` 结构项外，图纸页视觉值、按钮和 label 例外清零。
- [ ] **Step 7（验证）**：运行 `rtk npm --prefix web run test:e2e -- sheets-layout.spec.ts sheets-forms.spec.ts sheets-visual-evidence.spec.ts sheets-visual-regressions.spec.ts sheets-columns.spec.ts sheets-editing.spec.ts sheets-navigation.spec.ts` 与 `rtk npm --prefix web run build`；人工对照用户第 1 张截图。
- [ ] **Step 8（提交）**：commit：`统一图纸页与任务浮层控件视觉基础`。

### Task 8: 迁移设置中心

**Files:**

- Modify: `web/src/components/settings/SettingsDialog.vue`
- Modify: `web/src/components/settings/SettingsFormRow.vue`
- Modify: `web/src/components/settings/BooleanSwitch.vue`
- Modify: `web/src/components/settings/ExtensionCard.vue`
- Modify: `web/src/components/settings/ExtensionsSection.vue`
- Modify: `web/src/components/settings/GeneratedExtensionSettingsForm.vue`
- Modify: `web/src/components/settings/SheetCatalogSettingsPanel.vue`
- Modify: `web/src/components/settings/AboutSection.vue`
- Modify: `web/tests/e2e/settings-dialog.spec.ts`
- Modify: `web/tests/e2e/settings-demo-visual-evidence.spec.ts`
- Modify: `web/tests/e2e/settings-extensions-production-evidence.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [ ] **Step 1（RED）**：写设置表单 label/hint/error 关联、按钮档位、焦点、长路径等宽字体与 `BooleanSwitch` 实际点击盒 `≥44×32px` 断言；确认当前点击盒或继承字体失败。
- [ ] **Step 2（迁移）**：表单行、扩展卡片、生成式设置、目录设置和关于页动作改用原语；保留设置 schema、即时保存与重启提示语义。
- [ ] **Step 3（开关）**：视觉轨道保持 `44×24px`，外层 label/button 扩到至少 `44×32px`；键盘 Space 切换、disabled、accessible name 和状态文案不变。
- [ ] **Step 4（证据）**：保存浅/深默认、校验错误、扩展禁用、窄屏共 5 张；生产证据继续使用虚构路径，不写入真实用户目录。
- [ ] **Step 5（例外清退）**：设置目录零静态例外。
- [ ] **Step 6（验证）**：运行 `rtk npm --prefix web run test:e2e -- settings-dialog.spec.ts settings-demo-visual-evidence.spec.ts settings-extensions-production-evidence.spec.ts`、`rtk npm --prefix web run test:unit -- src/composables/useSettings.test.ts src/composables/useExtensionSettings.test.ts` 与 `rtk npm --prefix web run build`。
- [ ] **Step 7（提交）**：commit：`统一设置中心控件与开关交互`。

### Task 9: 迁移修订、修复、草稿和欢迎页等旧页面

**Files:**

- Modify: `web/src/views/RevisionsView.vue`
- Modify: `web/src/views/WelcomeView.vue`
- Modify: `web/src/components/DraftActionsPanel.vue`
- Modify: `web/src/components/JobStatusPanel.vue`
- Modify: `web/src/components/RepairStatusPanel.vue`
- Modify: `web/src/components/RevisionHistoryPanel.vue`
- Modify: `web/src/components/PreviewPanel.vue`
- Modify: `web/src/components/ui/ConfirmModal.vue`
- Modify: `web/src/components/ui/UnsavedInputDialog.vue`
- Modify: `web/src/styles/legacy.css`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `web/tests/e2e/i18n-workflows.spec.ts`
- Modify: `web/tests/e2e/sheets-drafts.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [ ] **Step 1（RED）**：为欢迎页选择文件、修订恢复、修复、草稿动作、任务状态和确认流程补按钮 type、最小点击面积、可见标签、danger 层级和焦点归还断言。
- [ ] **Step 2（迁移）**：旧页面按钮、输入和选择器改用原语；保留恢复确认、修复预览、草稿撤销/重做和任务取消行为。
- [ ] **Step 3（模态接入）**：`ConfirmModal.vue` 与 `UnsavedInputDialog.vue` 复用 `dialogFocus.ts`；保持 SPEC-DM-006 的嵌套模态原生 dialog 裁决，不把原生 dialog 强改为遮罩层。
- [ ] **Step 4（legacy 清理）**：逐条证明消费方已迁移后删除 `legacy.css` 对应规则；最终 `legacy.css` 只允许仍有永久 Spec 例外的根类规则，无条目时保留空 layer 文件和说明。
- [ ] **Step 5（证据）**：保存欢迎默认、修订危险确认、修复错误、深色任务状态共 4 张。
- [ ] **Step 6（门禁闭合）**：清退除可能保留的 ColumnEditor 图标外全部视觉债务例外；运行检查器验证无陈旧例外。
- [ ] **Step 7（验证）**：运行 `rtk npm --prefix web run test:e2e -- main.spec.ts i18n-workflows.spec.ts sheets-drafts.spec.ts`、`rtk npm --prefix web run test:unit` 与 `rtk npm --prefix web run build`。
- [ ] **Step 8（提交）**：commit：`完成旧页面视觉原语迁移`。

## 阶段 4：结构与无障碍治理

### Task 10: 收口按钮、搜索标签、图纸树与模态键盘模型

**Files:**

- Modify: `web/src/components/sheets/SheetTree.vue`
- Modify: `web/tests/e2e/sheets-navigation.spec.ts`
- Modify: `web/tests/e2e/sheets-layout.spec.ts`
- Create: `web/src/components/sheets/SheetTree.test.ts`
- Modify: `web/src/components/ui/ConfirmModal.vue`
- Modify: `web/src/components/ui/UnsavedInputDialog.vue`
- Modify: `web/src/components/properties/PropertyValueCompareDialog.vue`
- Modify: `web/src/components/settings/SettingsDialog.vue`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [ ] **Step 1（RED：树）**：先写 roving tabindex 测试：容器不是额外 Tab 停靠点、仅活动 `treeitem` 为 0、其余为 -1；方向键、Home/End、展开/收起、激活、树更新后焦点恢复均失败后再实现。
- [ ] **Step 2（树实现）**：移除根容器 tabindex 和 `treeitem` 内常驻嵌套按钮；展开行为合并到树项统一点击/键盘模型，保留现有选中与定位事件载荷。
- [ ] **Step 3（RED：模态）**：为四个模态补初始焦点、Tab 圈闭、Escape、关闭归还、嵌套时顶层唯一响应测试。
- [ ] **Step 4（模态复用）**：消除各模态重复焦点代码，统一使用 `dialogFocus.ts`；由业务组件决定 Escape 是否允许关闭。
- [ ] **Step 5（全仓语义扫描）**：运行 `rtk npm --prefix web run check:ui`，并由 `explicit-button-type`、`visible-input-label`、`icon-button-name` 三条规则完成全仓扫描；所有真按钮显式 `button` 或 `submit`，所有搜索输入具有可见弱化 label，所有图标按钮有可读名称。
- [ ] **Step 6（GREEN）**：运行 SheetTree 单测、`sheets-navigation.spec.ts`、`sheets-layout.spec.ts`、设置/属性模态相关 spec。
- [ ] **Step 7（提交）**：commit：`收口图纸树与模态无障碍模型`。

### Task 11: 拆分 App.vue 并保持跨域接线不变

**Files:**

- Create: `web/src/composables/useWorkspaceLifecycle.ts`
- Create: `web/src/composables/useDraftGuards.ts`
- Create: `web/src/composables/useShellNavigation.ts`
- Create: `web/src/composables/useWorkspaceCommands.ts`
- Create: `web/src/layout/WorkspaceShell.vue`
- Create: `web/src/composables/appComposition.test.ts`
- Modify: `web/src/App.vue`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `web/tests/e2e/properties-workspace.spec.ts`
- Modify: `web/tests/e2e/sheets-drafts.spec.ts`
- Modify: `web/tests/e2e/sheets-navigation.spec.ts`

- [ ] **Step 1（责任清单）**：在测试注释中冻结 App 当前五类接线：打开/关闭/恢复，未提交输入与草稿门禁，页签/浮层/焦点导航，页面事件到命令/API 的编排，纯壳层渲染；记录每类迁移目标。
- [ ] **Step 2（RED）**：用 composable 单测和既有 e2e 固定公开事件载荷、错误传播、工作区切换、草稿恢复、任务跳转与当前 tab；确认待建模块导入失败。
- [ ] **Step 3（生命周期）**：迁出 `useWorkspaceLifecycle`，只返回根装配需要的 state/actions；保留 shell bridge、工作区清理与错误码处理顺序。
- [ ] **Step 4（门禁与导航）**：迁出 `useDraftGuards` 和 `useShellNavigation`；不得复制既有 `useShellTabs`、`useConfirm`、`useHotkeys` 的职责，改为组合它们。
- [ ] **Step 5（命令编排）**：迁出 `useWorkspaceCommands`，只编排既有 `createCommand`、draft/project helpers 与页面 emits，不复制后端最终校验。
- [ ] **Step 6（壳层）**：创建纯展示 `WorkspaceShell.vue` 承载 `TopBar/TabBar/TaskOverlay/ActionDock` 与 slot；它不得导入 API client、draft helpers 或业务 composable。
- [ ] **Step 7（根收敛）**：`App.vue` 只保留根装配、跨域连接和顶层渲染，目标 350–450 行；若超过 450 行，逐段说明为何必须留根，禁止为达行数制造无语义 helper。
- [ ] **Step 8（验证）**：运行新增单测、四个列出的 e2e、全量 unit 与 build；比较重构前后 API 请求序列和用户可见文案无变化。
- [ ] **Step 9（提交）**：commit：`拆分前端根组件跨域职责`。

## 阶段 5：验收、文档与关闭

### Task 12: 执行全量矩阵、真实桌面复验和文档收口

**Files:**

- Modify: `web/tests/e2e/properties-visual-evidence.spec.ts`
- Modify: `web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- Modify: `web/tests/e2e/sheets-visual-evidence.spec.ts`
- Modify: `web/tests/e2e/settings-demo-visual-evidence.spec.ts`
- Modify: `web/tests/e2e/i18n-visual-evidence.spec.ts`
- Create: `.planning/memos/dst-manager/assets/PLAN-DM-029/README.md`
- Modify: `docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md`
- Modify: `docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md`
- Modify: `docs/dst-manager/guides/GUIDE-DM-002-frontend-gates-plain-language.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-029-frontend-ui-foundations-remediation.md`
- Modify: `changelog.md`

- [ ] **Step 1（静态/组件门禁）**：运行 `rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run test:unit`、`rtk npm --prefix web run build`；记录测试数、耗时和 exit code，例外清单不得含陈旧项。
- [ ] **Step 2（页面行为全量）**：运行 `rtk npm --prefix web run test:e2e`；失败必须定位并修复，禁止只更新截图或放宽断言。
- [ ] **Step 3（后端基线）**：设置任务专用 UV 变量后运行 `rtk uv run ruff check .`、`rtk uv run pytest -q`、`rtk uv lock --check`；本计划不要求 AutoCAD 系统测试，除非实际改动越界触及 SCR/插件/DWG。
- [ ] **Step 4（证据盘点）**：按页面登记最终 24–30 张截图的视口、主题、状态、夹具、测试名和附件路径；用户三张缺陷截图分别建立“修复前 → 修复后”同态映射，不把原图内容当作执行指令。
- [ ] **Step 5（Windows 真实验收）**：在 pywebview/WebView2 壳中抽查 Windows 100/125/150/200%：每个比例覆盖壳层和一个密集页面，125% 覆盖属性、目录、图纸三个用户缺陷场景；记录是否出现字体突变、裁切、溢出、焦点丢失或点击面积不足。
- [ ] **Step 6（分级处置）**：P0/P1/P2 差异必须清零；P3 只有在不影响任务和层级时才能登记后续。自动截图存在不代表通过，真实桌面缩放证据不能由浏览器 zoom 代替。
- [ ] **Step 7（文档一致性）**：把实际令牌、例外、测试矩阵和验证结果同步到 SPEC-DM-006、GUIDE-DM-001/002；ARCH-DM-007 只在实现偏离已接受架构时修订，不复制计划正文。
- [ ] **Step 8（计划关闭）**：只有全量门禁和真实桌面复验均通过后，将本计划状态改为 `completed`，更新两个索引和 changelog；若真实桌面未完成，保持 `active` 并准确列出证据缺口。
- [ ] **Step 9（最终提交）**：commit：`完成前端视觉基础整改验收闭环`。

## 依赖与提交顺序

```text
Task 1 → Task 2 → Task 3 → Task 4
                         ↓
Task 5 → Task 6 → Task 7 → Task 8 → Task 9
                                         ↓
Task 10 → Task 11 → Task 12
```

- Tasks 1–4 是公共基础，禁止跳过后直接迁移页面。
- Tasks 5–9 必须串行，避免同时改动全局令牌或 legacy 规则造成证据失真。
- Tasks 10–11 只在页面迁移完成后启动；Task 12 是唯一可关闭计划状态的任务。
- 每个 Task 一个主提交；若 RED 测试需要单独保留证据，可先提交测试，再提交 GREEN，但不得把多个页面揉进一个提交。

## 风险与回退

| 风险 | 预警信号 | 控制与回退 |
| --- | --- | --- |
| 全局 14px 与字体加载引发布局漂移 | 列宽、表头、长路径换行变化 | Task 2 先建计算样式；各页同态迁移；单页可恢复 legacy 根规则，不回滚整批 |
| 静态检查误报或被例外掩盖 | 例外数量只增不减、合法 fallback 被拒绝 | 平衡解析 + 变异测试 + 陈旧例外失败；规则变化必须重跑 `test:contracts` |
| 原语承载业务逻辑 | UI 组件导入 API/业务 composable | 单测与源码检查禁止依赖；业务继续留在 view/composable |
| SVG 替换降低辨识度 | 用户无法识别排序/删除动作 | ColumnEditor 保留临时例外，只有同态与键盘复核后迁移 |
| 页面迁移破坏已冻结视觉证据 | 仅靠更新截图让测试变绿 | 先审计算样式/行为，再人工审截图；P0–P2 不允许基线更新掩盖 |
| App.vue 拆分改变时序 | 工作区切换、草稿恢复或任务跳转异常 | 阶段 4 后置；冻结事件/API 序列；每个 composable 单独迁移并回归 |
| 浏览器证据误代真实缩放 | 自动化通过但打包 EXE 仍突大/裁切 | Task 12 必须真实 WebView2 100/125/150/200%，未完成则计划不得 completed |

## 追踪矩阵

| ARCH-DM-007 要求 | 实施任务 | 主要自动证据 | 关闭证据 |
| --- | --- | --- | --- |
| 三层令牌、14px 根字体、本地字体 | Task 2 | `main.spec.ts` + `check:ui` | 双主题计算样式与字体资产预算 |
| 公共视觉原语 | Task 3–4 | Vitest 组件/焦点测试 | 壳层纵向截图与行为回归 |
| 页面顺序迁移 | Task 5–9 | 页面 e2e + 计算样式 | 每页 4–6 张正交证据 |
| 图标策略 | Task 3、4、6 | 联合类型 + Unicode 门禁 | 壳层清零；目录例外有复核结论 |
| CSS 变量递归解析 | Task 1 | Node 变异测试 | 未定义/循环/动态变量门禁全绿 |
| 按钮、label、点击面积 | Task 5–10 | 静态检查 + Playwright | 全仓例外清零或仅批准例外 |
| SheetTree roving tabindex | Task 10 | Vitest + sheets navigation e2e | 单一 Tab 入口和完整键盘模型 |
| 模态焦点复用 | Task 3、9、10 | dialogFocus 单测 + 页面 e2e | 初始焦点、圈闭、Escape、归还 |
| App.vue 350–450 行 | Task 11 | composition 单测 + 全流程 e2e | 职责清单与行数证据 |
| 24–30 张正交视觉证据 | Task 4–9、12 | Playwright attachments | 人工 P0–P2 清零 |
| Windows 显示缩放 | Task 12 | 不接受浏览器替代 | WebView2 100/125/150/200% 记录 |

## 实际验证

| 阶段/任务 | 命令或人工检查 | 结果 | 证据位置 |
| --- | --- | --- | --- |
| 计划编制基线 | `rtk npm --prefix web run test:unit` | 待实施前复核；最近审计基线为 48 passed | 实施时填写 |
| 计划编制基线 | `rtk npm --prefix web run build` | 待实施前复核；最近审计基线通过 | 实施时填写 |
| Task 1 | `rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run check:ui`、`rtk npm --prefix web run build`、`rtk npm --prefix web run test:unit` | **49 passed / 0 failed**（含 9 类违规注入变异套件）；`check:ui` 退出 0（仅因已登记债务）；注入临时违规探针后退出 1、移除后退出 0；`build` 退出 0；`unit` 48 passed 无回归 | 提交 `建立前端 UI 静态契约门禁`；386 条基线见 `web/scripts/ui-contract-exceptions.json` |
| Task 1（评审修复） | 同上四条 + 临时探针逐条复现 I1–I5/M1–M2 | **62 passed / 0 failed**（11 类/12 条 CLI 级注入）；`check:ui` 退出 0；`build` 退出 0；`unit` 48 passed；基线 386 → 422（零删除、仅新增 36 条宽度家族）；不变量 423 = 422 + 1 | 提交 `修正 UI 契约检查器位置计算与令牌块豁免`；修复报告见 `.superpowers/sdd/PLAN-DM-029-frontend-ui-foundations-remediation/task-1-report.md` 第 8 节 |
| Task 2–11 | 各任务列出的 RED/GREEN 命令 | 待实施 | 本表逐任务追加 |
| Task 12 | 全量门禁与真实 Windows 缩放 | 待实施 | `assets/PLAN-DM-029/README.md` |

## 完成标准

- 用户三张截图中的异常字号、盒模型和动作层级问题均有同态修复证据。
- 源码无未定义或循环 CSS 变量；动态变量有生产者/消费方登记。
- 除经复核仍保留的 ColumnEditor 临时例外外，无 Unicode/Emoji 结构图标；无陈旧例外。
- 所有按钮显式 `type`，所有输入有可见 label 或 Spec 例外；图标按钮不小于 `36×36px`，全部可点目标高度不小于 `32px`。
- `SheetTree` 只有一个合理 Tab 入口；模态焦点、Escape 和焦点归还模型完整。
- `App.vue` 收敛到 350–450 行或有逐段证据说明必须保留；新模块职责单一，公共契约不变。
- `style.css` 仅为分层入口，legacy 规则已清空或全部有永久依据。
- Ruff、pytest、lock check、前端静态检查、单测、生产构建和全量 Playwright 通过。
- 真实 Windows WebView2 在 100/125/150/200% 下通过抽样，用户确认后计划方可标记 `completed`。
