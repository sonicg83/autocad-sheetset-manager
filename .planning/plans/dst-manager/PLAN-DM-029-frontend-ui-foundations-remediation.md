---
id: PLAN-DM-029
title: 前端视觉基础与一致性整改实施计划
status: active
owners:
  - dst-manager
created: 2026-09-14
updated: 2026-09-15
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
- 阶段 4 必须等待阶段 3 全部完成；**阶段 4 不得与页面迁移并行修改** `App.vue`、`SheetTree.vue`、`TopBar.vue`、`TaskOverlay.vue` 或直接依赖（本条只约束「阶段 4 与页面迁移并行」，不限制阶段 2 的 Task 4 修改它自己 Files 里已列的 `TopBar.vue`/`TaskOverlay.vue`）。
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
- Create: `web/scripts/ui-contracts/font-assets.mjs`（计划原 Files 列表漏列检查器侧文件，实施时按控制器裁定补齐）
- Modify: `web/src/style.css`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `web/scripts/check-ui-contracts.test.mjs`
- Modify: `web/scripts/check-ui-contracts.mjs`
- Modify: `web/scripts/ui-contracts/types.mjs`
- Modify: `web/scripts/ui-contracts/css-vars.mjs`（`parseRules` 增加可选 `includeAtRules`，默认行为不变）
- Modify: `web/scripts/ui-contract-exceptions.json`
- Modify: `web/src/components/SheetTable.vue`
- Modify: `web/src/components/sheet-catalog/CatalogActions.vue`
- Modify: `web/src/components/sheet-catalog/ColumnEditor.vue`
- Modify: `web/src/components/sheet-catalog/FieldBrowser.vue`

- [x] **Step 1（资产核验）**：从 Inter 与 IBM Plex Mono 官方 OFL 发行物生成/选取 WOFF2 拉丁子集；记录字符范围 `U+0020–007E,U+00A0–00FF` 和实际标点；检查文件合计大小不超过 `256000` 字节，许可证文本与字体一同入库。
- [x] **Step 2（RED）**：在 `main.spec.ts` 增加根计算样式断言：正文 `14px/21px`、首选字体含 `Inter`，等宽探针含 `IBM Plex Mono`，`button/input/select/textarea` 均继承字体；确认当前基线失败。
- [x] **Step 3（令牌）**：建立 primitive → semantic → component 三层变量，至少覆盖字体、12/13/14px 字号、34/36/38px 高度、32px 点击下限、36px 图标按钮、间距、圆角、边框、焦点、状态色和图标尺寸；浅/深主题只在 `tokens.css` 映射。
- [x] **Step 4（重置）**：在 `reset.css` 设置 `box-sizing`、body margin、继承字体、`:focus-visible` 和 `prefers-reduced-motion`；确保字体失败时仍由固定高度/line-height 保持盒模型。
- [x] **Step 5（分层）**：把 `style.css` 内容无行为变化地迁入四层，`style.css` 只保留层顺序声明和四个导入；既有全局业务选择器全部置于有根类限定的 `legacy.css`。
- [x] **Step 6（字体规则）**：添加本地 `@font-face`、`font-display: swap` 和 unicode-range；路径/哈希/错误码等宽区域改消费 `--font-mono`，中文继续回落 `Microsoft YaHei, system-ui`。
- [x] **Step 7（门禁收紧）**：检查器增加字体文件存在、不得远程 URL、体积预算、`style.css` 仅入口的断言；清退已被本任务关闭的 raw visual/global selector 例外。
- [x] **Step 8（GREEN）**：运行 `rtk npm --prefix web run test:e2e -- main.spec.ts`、`rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run build`。
- [x] **Step 9（提交）**：commit：`统一前端字体令牌与样式分层`。

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
- Create: `web/src/components/ui/instanceId.ts`（首轮评审修复：兜底 DOM id 的模块级计数器）
- Create: `web/src/components/ui/ISC-Lucide.txt`（Lucide 图标集的 ISC 许可原文，取自 `lucide-static@1.46.0`）
- Create: `web/src/components/ui/uiPrimitives.test.ts`
- Create: `web/src/components/ui/dialogFocus.test.ts`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/vitest.config.ts`（挂载 SFC 所需：加载 vue 插件，默认 environment 与 include 不变）
- Modify: `web/src/styles/tokens.css`（组件令牌层补 `--input-font-size`）

- [x] **Step 1（测试环境）**：用 `rtk npm --prefix web install --save-dev @vue/test-utils happy-dom` 更新两份依赖清单（实得 `@vue/test-utils@2.5.0`、`happy-dom@20.14.5`）；组件测试文件使用 `// @vitest-environment happy-dom`，不改变现有测试默认环境（已完成：`vitest.config.ts` 只加 `plugins: [vue()]`，`environment: "node"` 与 `include` 保持原样）。
- [x] **Step 2（RED：组件契约）**：先写失败测试，覆盖 `UiButton` 的 `primary/secondary/danger/link`、`default/compact`、disabled/loading 与默认 `type=button`；`UiIconButton` 缺 `label` 时类型/运行期失败；`FormField` 的 label、hint/error ID 与 `aria-describedby` 关联；`UiSelect` 默认高度 = `38px`（消费 `--input-height`）。**该 38px 只测到「声明消费了令牌 + 令牌链解出 38px」**：happy-dom 不算布局，且 `web/tests/e2e/properties-definitions.spec.ts:344-346` 量的是 `.definition-panel` 里的遗留控件，与本案新增原语无关；真实计算高度必须在 Task 4 接入壳层后另加计算样式断言（首轮评审 F3 订正）。
- [x] **Step 3（RED：焦点契约）**：为 `dialogFocus.ts` 写初始焦点、Tab/Shift+Tab 圈闭、Escape 回调、关闭后焦点归还和无可聚焦元素五类失败测试。
- [x] **Step 4（图标注册表）**：在 `icons.ts` 导出封闭的 `UiIconName` 与 SVG path 数据；首批名称固定为 `theme`、`settings`、`close`、`chevron-left/right/up/down`、`status-dot`、`search`、`folder`、`copy`，记录 Lucide 来源与许可（ISC，许可原文随代码入库；几何数据是按 24×24 规格转写、不与上游版本同步，逐图标比对结果与可复跑命令见 Task 3 报告与 `icons.ts` 注释），不接受任意字符串或 `v-html`。
- [x] **Step 5（GREEN：视觉原语）**：实现各组件，只处理语义、外观、焦点和状态；尺寸通过 variant 和 CSS 自定义属性消费 Task 2 令牌，不导入业务 composable 或 API 类型（实得两处补充：`tokens.css` 组件令牌层新增 `--input-font-size`；`UiButton` 增加可选 `label` → `aria-label`，理由见 Task 3 报告）。
- [x] **Step 6（GREEN：焦点工具）**：导出 `useDialogFocus({open, container, initialFocus, onEscape})`，返回 `onDialogKeydown`；工具只管理焦点，不决定是否可关闭。
- [x] **Step 7（验证）**：运行 `rtk npm --prefix web run test:unit -- src/components/ui/uiPrimitives.test.ts src/components/ui/dialogFocus.test.ts`（30 passed）、`rtk npm --prefix web run test:unit`（78 passed）、`rtk npm --prefix web run check:ui`（退出 0）、`rtk npm --prefix web run test:contracts`（83 passed）、`rtk npm --prefix web run build`（退出 0）。
- [x] **Step 8（提交）**：commit：`新增前端公共视觉与焦点原语`。
- [x] **Step 9（首轮评审修复）**：修 `FormField`/`UiInput`/`UiSelect` 的兜底 id（原实现在实例作用域计数，同页多实例会生成同一个 DOM id，`label[for]`/`aria-describedby` 全部指错）与 `dialogFocus.ts` 的可聚焦元素集合（原拼写让隐藏元素、`contenteditable`、非 `0` 的 `tabindex`、单选组全部错位）；新增 `instanceId.ts` 与 `ISC-Lucide.txt`；测试增至 `uiPrimitives.test.ts` 25 条 + `dialogFocus.test.ts` 11 条 = **36 条**；commit：`修正原语实例标识与焦点圈闭边界`。

### Task 4: 用壳层完成原语纵向验证

**Files:**

- Modify: `web/src/layout/TopBar.vue`
- Modify: `web/src/layout/TabBar.vue`
- Modify: `web/src/layout/ActionDock.vue`
- Modify: `web/src/layout/TaskOverlay.vue`
- Modify: `web/src/components/ui/ToastHost.vue`
- Modify: `web/src/styles/tokens.css`（**计划缺陷补齐，Ruling 25**：新增壳层/浮层/提示宿主的组件层结构尺寸令牌）
- Modify: `web/src/components/ui/dialogFocus.ts`（**计划缺陷补齐，Ruling 28/R2-1**：新增可选 `returnFocus` 解析器）
- Modify: `web/src/components/ui/dialogFocus.test.ts`（同上，新增 5 条用例）
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `web/tests/e2e/i18n-visual-evidence.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [x] **Step 1（RED）**：在 `main.spec.ts` 增加壳层按钮计算样式、图标 accessible name、装饰图标 `aria-hidden`、最小点击面积、键盘焦点和任务浮层折叠状态断言；确认 Unicode 图标和尺寸断言失败。计算样式必须直接量壳层里已迁移控件的 `getBoundingClientRect()`：**输入类 38px、普通与图标按钮 36px、紧凑按钮 34px、可点目标 ≥ 32px**。Task 3 只在源码与令牌链层面锁定了这组尺寸（happy-dom 不算布局，`properties-definitions.spec.ts:344-346` 量的是 `.definition-panel` 的遗留控件），所以真实计算高度由本步骤补齐（首轮评审 F3）。同时把 Task 3 无法在本地验证的焦点可见性（`[hidden]`/`inert`/`display:none`/`visibility` 叠加、`0×0`）在浏览器里覆盖（首轮评审 F2）。
- [x] **Step 2（迁移）**：把 `◐`、`⚙`、`✕`、`▸/▾`、`«/»`、`●` 替换为 `UiIcon`/`UiIconButton`；保留可见文案和 i18n key，状态按钮补 `aria-expanded`/`aria-pressed`。**纯图标按钮必须用 `UiIconButton`（`label` 必填）**；`UiButton` 只用于「插槽无可读文案」的图形性按钮并可传 `label`，而带可见文案的 `UiButton` 若同时传 `label`，两者文字必须一致（WCAG 2.5.3「名称包含可见文本」）；`UiIconButton`/`UiButton.label` 对 ARCH-DM-007 §5 的补充属文档收口，登记为 Task 12 收口责任 D，本任务不改 ARCH 正文（首轮评审 F4）。
- [x] **Step 3（尺寸与焦点语义）**：壳层普通按钮使用 `default`，任务浮层紧凑动作使用 `compact`；所有独立图标按钮达到 `36×36px`，不以 SVG 尺寸充当点击面积。同时把 `TaskOverlay.vue:74-82` 的手写焦点副本（`onDrawerKeydown` + 内联选择器 + `tabIndex`/`getClientRects` 过滤）整体换成 `useDialogFocus`，**用 `onEscape(event)` 保留原有 `preventDefault` + `stopPropagation` 语义**（浮层下还有文档/window 级 Escape 处理器，传播一旦被工具吞掉就会变成误关闭）；迁移后浮层内 **不得对 Tab 调 `stopPropagation`**，否则事件到不了绑在容器上的 `onDialogKeydown`，Tab 圈闭静默失效。**按字面「整体换成 `useDialogFocus`」会丢三处行为，本步骤验收时逐条对齐（Task 3 三轮评审 H4）**：
    - ① **显式传 `initialFocus`**：浮层打开时聚焦**当前激活**页签，迁移后由 `initialFocus: activeTabElement` 显式承载。**本句原理由已订正（Task 4 迁移轮 2；独立复审 F2-2 指出、控制器复核通过）**：非激活页签带 `:tabindex="active===tab.id?0:-1"`，而 `dialogFocus.ts` 的 `isTabStop` 排除负 `tabindex`，故迁移后 `focusables()[0]` **恒等于**当前激活页签——「不传 `initialFocus` 就会落到第一个页签」不成立；显式传参是表达意图，不是修 bug。
    - ② **关闭回焦语义不同**：现在回焦的是 `rail` 上 `[data-entry="${active}"]`（`closeDrawer`，`:73`），工具归还的是**打开时捕获的 `opener`** → 「打开后切换过页签」时两者不同；必须保留原语义，或明确接受变更并记录理由与用户可见差异。
    - ③ **过滤条件有变**：现有 `el.tabIndex>=0 && el.getClientRects().length>0`（`:78`）中的 `getClientRects()`（真实布局可见）会被**丢弃**（工具只按属性 + 计算样式判定），候选也从 `[tabindex="0"]` **放宽**为 `[tabindex]`（带正 `tabindex` 的元素会成为停靠点）；两点必须在本步骤写明并判断是否可接受，不可接受就先补工具能力，不得在迁移里用本地副本绕过。
- [x] **Step 4（例外清退）**：删除上述壳层 Unicode 例外；运行检查器并确认只剩页面级债务和 `ColumnEditor.vue` 临时例外。
- [x] **Step 5（证据）**：在 `1440×900` 浅/深主题各保留壳层默认截图，在 `900×768` 保留窄视口一张，并用计算样式覆盖 hover/focus/disabled，不额外保存状态截图。**壳层截图必须重拍基准**：Task 2 的基准里壳层还是 Unicode 字符与旧尺寸，Task 4 迁移后像素必变；重拍件要按计划的全轮配额计账。同时记录级联事实：`primitives.css:36` 的 `.modal-actions button{padding:9px 16px}` 会被原语的固定高度 + `padding:0 var(--space-4)` 静默覆盖（scoped/无层优先于命名层），属**预期行为**，不再为旧选择器补声明；发现其他同类覆盖时同例处理，不引入特异性竞争（首轮评审 F5）。
- [x] **Step 6（验证）**：运行 `rtk npm --prefix web run test:e2e -- main.spec.ts i18n-visual-evidence.spec.ts`、`rtk npm --prefix web run test:unit`、`rtk npm --prefix web run build`。
- [x] **Step 7（提交）**：commit：`迁移桌面壳层到统一视觉原语`。

> **Task 4 实测与口径（Ruling 25/26/28 收口，2026-09-14）**
> **范围**：本任务把**整个桌面壳层**迁完——`TopBar`/`TabBar`/`ActionDock`/`TaskOverlay`/`ToastHost`（视觉 + 焦点 + 例外全部清退）。依据：本条 Files 已列 `TaskOverlay.vue`，line 46 括注明文允许「阶段 2 的 Task 4 修改它自己 Files 里已列的 `TopBar.vue`/`TaskOverlay.vue`」，Step 2 的图形清单含 `«/»`、`●`、`✕`（只存在于这两个文件），Step 4 的验收要求「只剩**页面级**债务」。**Ruling 26 曾把这两个文件判给 Task 7/Task 10，已在 Ruling 28 撤回**；Task 7 对本文件的浮层内部控件降级为**验证**（其 Step 2 的相关子句与 Step 6 的浮层部分事实上清零），Task 10 Step 4 只负责 `ConfirmModal`/`UnsavedInputDialog`/`PropertyValueCompareDialog`/`SettingsDialog` 四个模态（其 Files 不含 `TaskOverlay.vue`）。
> **Step 4 验收口径订正**：「只剩页面级债务和 `ColumnEditor.vue` 临时例外」在本任务范围内不可达且不准确——清退后仍会有其它任务名下例外（Task 5/6/7/8/9/10/11）。实际口径：**本任务名下 62 条清零（41 + 21）+ 零新增违规 + `check:ui` 只剩其它任务名下例外**。
> **结果**：例外表 **382 → 320**（Task 4 名下 62 条：`ActionDock` 12、`TabBar` 5、`TopBar` 24、`TaskOverlay` 15、`ToastHost` 6），`dynamicVariables` 恒为 1，棘轮不变量 **321 = 320 + 1**、`waivedViolations 0`。
> **计划缺陷补齐**：本条 Files 另补 `web/src/styles/tokens.css`（Ruling 25）与 `web/src/components/ui/dialogFocus.ts`/`dialogFocus.test.ts`（Ruling 28/R2-1，新增可选 `returnFocus` 解析器以保留「关闭回焦当前激活入口」的原语义）。
> **提交**：`4f0082d 迁移桌面壳层到统一视觉原语`、`d078249 补齐焦点守卫存活变异用例`、`e9750c8 修正壳层字号令牌层级与焦点测试覆盖`、`ec9b41b 迁移任务浮层焦点与控件到公共原语`、`3834e26 迁移提示宿主并清退壳层例外`、`da4d3bb 计划册记 Task 4 收口与 Ruling 26/28 写回`（控制器）、`76dcb92 补齐焦点工具防滚动参数与提示宿主断言`。
> **评审闭环**：首评 `Needs fixes`（0 must-fix / 6 should-fix / 4 nit）→ 修复轮 1 → 迁移轮 2 → 二审 `Needs fixes`（1 must-fix = **控制器证据归档失误**，3 should-fix / 6 nit，**无代码级缺陷**）→ 二审修复轮 → **复审复核 `Approve`**。控制器终验：例外 **382 → 320**（本任务名下 62 条全清）、不变量 **321 = 320 + 1**、四门禁 **0 / 102 / 83 / 0**、全量 e2e **499 passed / 1 flaky / 0 failed**（flaky = `settings-extensions-production-evidence.spec.ts:230`，负载敏感族）、7 项变异全程留档。

## 阶段 3：按固定顺序迁移页面

### Task 5: 迁移属性页并关闭用户截图中的字号突增

**Files:**

- Modify: `web/src/views/PropertiesView.vue`
- Modify: `web/src/components/properties/PropertyDefinitionPanel.vue`
- Modify: `web/src/components/properties/PropertyDefinitionTable.vue`
- Modify: `web/src/components/properties/PropertyCsvPanel.vue`
- Modify: `web/src/components/properties/PropertyValuePanel.vue`
- Modify: `web/src/components/properties/PropertyValueCompareDialog.vue`
- Modify: `web/src/styles/tokens.css`
- Modify: `web/tests/e2e/properties-layout.spec.ts`
- Modify: `web/tests/e2e/properties-visual-evidence.spec.ts`
- Modify: `web/tests/e2e/properties-definitions.spec.ts`
- Modify: `web/tests/e2e/properties-values.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`

- [x] **Step 1（RED）**：扩充计算样式断言，明确截图红框内折叠标题、导入导出、搜索、主次动作的 `font-size/font-family/line-height/height/padding/radius`；搜索框必须有可见弱化 label；确认当前原生 16px 泄漏失败。
- [x] **Step 2（原语迁移）**：按钮、输入、选择器和字段组合改用公共原语；生产输入继续保持 SPEC-DM-010 的 `38px`，不得为统一而降为 36px。
- [x] **Step 3（层级收敛）**：折叠标题、计数、状态徽标、工具行和主按钮分别消费 label/caption/body/action 语义令牌；移除局部重复字体、盒模型和焦点样式。折叠标题落 `--font-label`（13px）、模态标题落 `--modal-title-font-size`（经原语层 `.modal-card h2` 覆盖，页面 SFC **不得**新增重复声明——**实测两处 `<h2>` 均在 `.modal-card` 内，T5-1 原判「UA16px 泄漏」有误，见 Ruling 32**），页面不得消费 `--font-body`（`font` 简写，根元素专用）或 `--font-size-*` 原始层令牌。**结构尺寸不得就地写常量**：新增 6 个组件层令牌落 `tokens.css`（Ruling 31，与 Ruling 25 同口径，零视觉变化的逐字搬运）——`--panel-head-min-height:60px`、`--panel-search-width:280px`、`--definition-row-height:44px`、`--compare-card-max-width:560px`、`--compare-item-max-height:180px`、`--expand-editor-min-height:140px`；不新增字号令牌，不得用 `clamp()/min()/max()` 包裹常量绕检查器。
- [x] **Step 4（行为回归）**：验证字段定义展开、新增字段、CSV 导入导出、搜索、对照、撤回和更新图纸集行为及 accessible name 不变。
- [x] **Step 5（正交证据）**：持久保存浅色默认、深色默认、错误态、`900×768` 单列、200% 定义表溢出共 5 张；其余状态沿用行为/计算样式断言。
- [x] **Step 6（例外清退）**：删除属性页 raw size、裸颜色、无 label、按钮 type 等全部例外；检查器对属性目录零例外。
- [x] **Step 7（验证）**：运行 `rtk npm --prefix web run test:e2e -- properties-layout.spec.ts properties-visual-evidence.spec.ts properties-definitions.spec.ts properties-values.spec.ts` 与 `rtk npm --prefix web run build`；人工对照用户第 3 张截图，确认同层级控件不再突大且主次层级清晰。**（2026-09-15 用户本人已人工确认「可以通过」，该门禁关闭；截图未入库，控制器无法代验，已如实登记）**
- [x] **Step 8（提交）**：commit：`统一属性页控件视觉基础`。

> **Task 5 实测与口径（Ruling 31/32/33/35 收口，2026-09-15）**
>
> **提交链**：`0ff550e 统一属性页控件视觉基础`（14 文件 +298/−576，父 `a0c0b24`）→ `3ff847d 补齐输入原语的悬停状态` → `55ab38b 清除属性页死规则并补齐字体断言` → `58dbc90 修正原语中错误态优先于悬停的定序` → `8667b8d 补错误态悬停守卫并订正视觉证据注释`。控制器计划/文档提交穿插其间（`79e7d90`、`a0c0b24`、`e36d4cd`、`9fc1d93`），与实现提交无重叠文件。
>
> **三轮评审闭环**：首评 `Needs fixes`（0 Critical / 2 Important / 4 Minor）→ 修复轮 1（Ruling 33，原语补 hover + 删死规则 + 补字体断言）→ 二次评审判 `All findings addressed, no new Critical/Important breakage`，但把一项状态优先级交控制器裁定 → Ruling 35 裁定修正（错误态优先于 hover）→ 第二轮修复。**两条 Important 均由控制器独立复核属实后才派发，不是直接采纳评审意见**；Ruling 32 与 34 是控制器自我更正（分别纠正 T5-1 的「UA 16px 泄漏」误判、以及实施者把共享原语影响面说小）。
>
> **例外表**：320 → **258**（−62，纯删除，0 增）；被删集合恰为 Task 5 名下 62 条，与 Files **逐文件 1:1 重合**，零误删其他任务条目。控制器自写空例外探针（`controller-task-5-probe.mjs`，独立于实施者的）不变量 **259 = 258 + 1**（基线 321 = 320 + 1），**Task 5 六文件残留原始违规 = 0**（违规真被消除而非取消登记），陈旧例外 = 0。
>
> **令牌**：`tokens.css` +12/−0 **纯新增**，6 个结构令牌值 `60/280/44/560/180/140` **逐字等值**，无字号令牌、无 `calc/clamp/min/max` 包裹。
>
> **字号泄漏实况**：真泄漏只有 `.head-title` 显式 16px 三处（→ `--font-label`）；两处 `<h2>` 已被 `primitives.css` 的 `.modal-card h2` 覆盖（**不是**泄漏）。任务级步 3 的文件内消费约束实测：Task 5 六文件 `--font-size-*` 原始层消费 0、残留裸 `font-size:Npx` 0、`font-size:var(--font-body)` 误用 0。
>
> **实际验证（控制器亲跑，不引用子代理自述）**：
>
> | 项 | 命令 | 结果 |
> |---|---|---|
> | 静态契约 | `npm run check:ui` | EXIT 0（静默） |
> | 契约测试 | `npm run test:contracts` | 83 passed / 0 failed |
> | 单测 | `npm run test:unit` | 11 文件 / 104 passed |
> | 属性页 e2e | `npx playwright test properties-visual-evidence.spec.ts` | 18 passed / 0 failed（首次即过，无 retry） |
> | RED 归因 | `evidence/task-5-fix2-red.txt` | `:183` 非悬停断言**通过** + `:191` `toBeEnabled()` **通过** → 仅 `:193` 悬停后断言失败，`Received` = `--color-accent` 两主题值（`#2F5BE0`/`#6B8DFF`）、`Expected` = `--color-danger` 两主题值（`#C2302B`/`#F0776E`），四个 RGB 逐值对得上 `tokens.css` |
> | 构建 | `npm run build` | EXIT 0 |
>
> **两轮 e2e 配额**：实施轮 5/5（55 passed / 1 flaky，retry 后过）、修复轮 1 用 2/2、修复轮 2 用 2/2。**全量 e2e 留到 Task 12 控制器收口时跑一次。**
>
> **未覆盖（如实登记）**：hover 与错误态的**组合**在修复轮 1 时无断言（守卫用了 `.value-item:not(.invalid)`），已由修复轮 2 补上**双向**守卫（invalid+hover → 危险色、非 invalid+hover → 强调色同时成立）；`UiSelect` 仍只有源文本断言、无独立 e2e；`SheetPropertyEditor.vue:108`（**Task 7** 目标文件）同款 hover 规则仍需在 **Task 7** 删除（原语已就位）；真实 Windows WebView2 与显示缩放复验留 Task 12。

**修复轮（Ruling 33，两轮独立提交）**

首轮任务级评审判 `Needs fixes`，两条 Important 均由控制器独立复核属实：

- **Important-1（死规则 + 失实注释）**：`PropertyValuePanel.vue:309` 的 `.value-item input:hover:not(:disabled){border-color:var(--color-accent)}` 在控件换成 `UiInput` 后**永不可能命中**——`UiInput` 根元素是 `<span class="ui-input">`，真正的 `<input class="ui-input__control">` 不是根元素，而 Vue scoped CSS 的 `data-v-*` 只追加到子组件根元素上。该规则因此静默丢失字段输入的悬停强调，紧邻注释却声称「此处只保留悬停强调（原语无 hover 规则）」。
  根因不在 Task 5 而在 Task 3 的原语缺陷：`UiInput`/`UiSelect` 已提供 `focus-visible`（`reset.css:34`）、`disabled` 与错误态，**独缺 `hover`**，而 SPEC-DM-006 §232 明确要求文本输入/下拉框/文本域「完整提供 `hover`、`focus-visible`、`disabled` 与错误态」。故属冻结 Spec 违规，不是可选打磨。
  处置：**新建原语补充轮**，在 `UiInput.vue`/`UiSelect.vue` 的 scoped 样式内逐字补回既有事实标准 `.ui-input__control:hover:not(:disabled){border-color:var(--color-accent)}`（同一值已独立出现在 `PropertyValuePanel.vue:309` 与 `SheetPropertyEditor.vue:108`，属零视觉变化的原样上移），随后删除页面侧的死亡规则。**驳回页面侧 `:deep(.ui-input__control)`**：那会让每个消费 `UiInput` 的页面各自复制一条 hover 规则，正是 Step 3 要消除的局部重复；仓库内唯一 `:deep()` 先例（`SheetToolbar.vue:184`）位于尚未迁移的遗留文件，不构成新约定。
  **必须现在做而不是推给 Task 12**：`SheetPropertyEditor.vue:108` 正是 **Task 7**（图纸页）的目标文件且含同一条规则，Task 7 迁移后会原样复现同一缺陷；集中修一次可避免 Task 6–9 各撞一次。
  **控制器自我更正（Ruling 36）**：本条与下方「实测与口径」初稿把该文件误记为「Task 6 目标文件」——实际它在 `web/src/components/sheets/`（图纸页），属 **Task 7** Files（计划 `:325`）。Task 6 是图纸**目录**页，其 Files 不含此文件。**不影响 Ruling 33 的实际结论**：原语已就位后，Task 7 只需删页面规则；仅任务编号错误，已全处订正。

- **Important-2（Step 1 点名的断言缺失）**：Step 1 逐字要求覆盖 `font-size/font-family/line-height/height/padding/radius`，实测 `properties-visual-evidence.spec.ts` 中 `font-family` 与 `line-height` **零命中**。处置：为 Step 1 点名的元素（折叠标题、导入导出、搜索、主次动作）补**计算样式**断言。
  `line-height` **不得新增令牌**：`tokens.css` 只有 `--line-height-body:1.5`（`--font-body` 简写专用、根元素限定），`primitives.css:29` 与 Task 5 三处用的是裸 `1.6`/`1.7` 无单位倍数，静态检查器不将其计为视觉值。故本步骤只**锁定既有计算值**防回归，并在收口责任 N 登记「line-height 无令牌层」。

**回归守卫必须是活的**：本次缺陷的本质是「看起来正确但永不命中的规则」，所以除 `uiPrimitives.test.ts` 的源文本断言外，必须在 `properties-visual-evidence.spec.ts` 增加**真实 hover 后的计算样式断言**（`locator.hover()` 后读 `getComputedStyle(input).borderColor`）。该断言在补原语之前必须**先红**，用以自证诊断成立。

Files（`web/src/components/ui/**` 的修改权仅限本轮，Task 5 主体步骤仍受 T5-3 约束）：

- Modify: `web/src/components/ui/UiInput.vue`
- Modify: `web/src/components/ui/UiSelect.vue`
- Modify: `web/src/components/ui/uiPrimitives.test.ts`
- Modify: `web/src/components/properties/PropertyValuePanel.vue`
- Modify: `web/tests/e2e/properties-visual-evidence.spec.ts`

- [x] **Step F1（RED）**：在 `properties-visual-evidence.spec.ts` 加真实 hover 计算样式断言 → 必须因 `borderColor` 不等于强调色而失败，保存失败输出自证诊断。
      **实测**：`2 failed / 2 passed`。失败值 `Received "rgb(199, 208, 219)"`（浅色 `--color-border-strong` `#C7D0DB`）与 `"rgb(59, 72, 92)"`（深色 `#3B485C`）恰为该令牌两主题解析值，即 hover 后边框**仍是常规色**；且 hover **之前**的默认态断言**先通过**，证明选择器命中的是真实、非 invalid、非 disabled 的 `.ui-input__control`。故失败只能归因「hover 无规则」，排除「选择器写错也报红」的假红。证据 `evidence/task-5-fix-red.txt`。
- [x] **Step F2（GREEN，提交一）**：在 `uiPrimitives.test.ts` 加源文本断言（RED）→ 在 `UiInput.vue`/`UiSelect.vue` 补 hover 声明（GREEN）。commit：`补齐输入原语的悬停状态`（`3ff847d`）。
- [x] **Step F3（GREEN，提交二）**：删除 `PropertyValuePanel.vue` 的死亡规则并把注释改为陈述事实；补 `font-family`/`line-height` 计算样式断言。commit：`清除属性页死规则并补齐字体断言`（`55ab38b`）。
      **实测**：GREEN `6 passed / 0 failed`，且在**页面死亡规则已删除**的代码状态下取得 → 直接证明 hover 由原语提供。e2e 用 2/2 配额（RED 1 + GREEN 1）。

**第一轮修复的评审闭环（re-review `d5020185`，BASE `e36d4cd` / HEAD `55ab38b`）**：判 `All findings addressed, no new Critical/Important breakage`；两条 Important 与「活的回归守卫」要求均闭环，RED 证据经评审者独立用 `tokens.css` 逐值核验成立。遗留 3 条 Minor + 1 项需控制器裁定的状态优先级（见下方第二轮修复）。

**第二轮修复（Ruling 35，两轮独立提交）**

re-review 把「hover 压过错误态」交由控制器显式裁定。控制器裁**定为必须修正**，理由与代价如下：

- **事实**：`UiInput.vue` 的 `.ui-input__control:hover:not(:disabled)` 特异度 **(0,3,0)** 压过 `.ui-input--invalid .ui-input__control` 的 **(0,2,0)**（`UiSelect.vue` 同形）；插入位置在 `--invalid` 之前不改变结论，**特异度优先于源顺序**。
- **对值面板是既有行为**：迁移前 `.value-item input:hover:not(:disabled)` (0,3,1) 已压过 `.value-item.invalid input` (0,2,1)，相对次序完全相同，故该页外观未变。
- **对定义面板及其余消费方是本轮新引入**：`PropertyDefinitionPanel.vue` 传 `:invalid`，而其迁移前**根本没有 hover 规则**（全仓 `input:hover` 仅 `PropertyValuePanel.vue` 与 `SheetPropertyEditor.vue` 两处），迁移前规则是 `.add-grid input[aria-invalid="true"]` (0,2,1)。实施者报告此前只识别出值面板的既有行为，**把共享原语的影响面说小了**。
- **裁定理由**：错误态是**持久语义态**、hover 是**瞬时可供性反馈**，用可供性遮蔽语义态是已知反模式；该 hover 现已位于**共享原语**，代价将随 Task 6–9 每个新迁移页面放大，此刻修最便宜（两个选择器 + 两处测试字符串 + 一条活的守卫）。且 `SPEC-DM-006:169` 明确「**所有态须在前景观测下可分辨**」，遮蔽方向与该条相悖。
- **有意偏离**：本修正会**改变值面板迁移前的既有外观**——悬停无效字段时输入描边由强调色变为危险色（容器级危险描边/底色不变）。这是对「逐字搬移/零视觉变化」的**有意定序修正**，只影响 hover+invalid 这一条路径，不影响默认态与错误态断言（`properties-visual-evidence.spec.ts` 未悬停处仍断言 `--color-danger`）。
- **未变得不可感知**：错误态另有独立通道——`PropertyDefinitionPanel.vue` 的 `<p v-if="nameError" id="definition-name-error" class="field-error" role="alert">`（配 `aria-invalid`/`aria-describedby`）与值面板容器级 `.value-item.invalid{border-color/background:--color-danger(-bg)}`；`aria-invalid` 不受 hover 影响。故本修正属**优先级定序**，不是可感知性补救。

Files（本轮）：

- Modify: `web/src/components/ui/UiInput.vue`（选择器改为 `.ui-input:not(.ui-input--invalid) .ui-input__control:hover:not(:disabled)`）
- Modify: `web/src/components/ui/UiSelect.vue`（同形以 `.ui-select:not(.ui-select--invalid)`）
- Modify: `web/src/components/ui/uiPrimitives.test.ts`（两处源文本断言锚定完整选择器字符串，必须同步改；其先红本身即该耦合的正面证明）
- Modify: `web/tests/e2e/properties-visual-evidence.spec.ts`（新增 hover+invalid 活的守卫；订正注释不精确；搜索元素改用稳健定位器）

- [x] **Step G1（RED）**：在既有 `error` 状态夹具下，对 `.value-panel .value-item.invalid input` 先断言默认态为 `--color-danger`、**显式断言该控件为 enabled**（`toBeEnabled()`，否则禁用控件会让守卫假绿），再 `hover()` 后断言**仍为** `--color-danger` → 当前代码下必须失败（显示强调色），保存失败输出。同时订正 `properties-visual-evidence.spec.ts` 的两处注释不精确（`padding/radius` 覆盖高估；`prod-` 前缀与实现不符），并把搜索元素由顺序相关的 `.first()` 改为同用例已定义的 `valueSearch` 角色定位器（`expectTokenFontFamily` 需接受 `Locator`）。
      **实测 RED（控制器逐行核验）**：失败位置 `:193` 正是**悬停后**那条断言，而 `:183`（非悬停=危险色）与 `:191`（`toBeEnabled()`）两条**先通过**——即「选择器确实命中真实、invalid、enabled 的控件」与「只有 hover 改变颜色」同时成立，失败只能归因 hover，**排除假红也排除禁用控件假绿**。
- [x] **Step G2（GREEN，提交一）**：改 `UiInput.vue`/`UiSelect.vue` 两个选择器 + `uiPrimitives.test.ts` 两处断言。commit：`修正原语中错误态优先于悬停的定序`（`58dbc90`，3 文件 +6/−2）。两处源文本断言**锚定完整选择器字符串**（含 `:not(.ui-input--invalid)`），改选择器即红。
- [x] **Step G3（GREEN，提交二）**：确认新守卫与既有 hover 断言同时通过（非 invalid 悬停仍为强调色、invalid 悬停为危险色）。commit：`补错误态悬停守卫并订正视觉证据注释`（`8667b8d`，1 文件 +24/−8）。**实测 18 passed / 0 failed，首次即过、无 retry。**

**实现者一处主动汇报的自我更正要保留记录**：新加注释写的行号引用（`:243`/`:246`）被自己插入的守卫代码推得过期——**正是本轮在修的同一类缺陷**（注释声称与代码现状不符）。实现者改写为**不带行号**的表述并 `--amend` 了提交 2（仍为两个提交，仅注释文字变化），且主动写进报告而非隐藏。控制器判该处置正确（行号引用本就应在 spec 里避开，否则每次插入代码都会复发）；与 Ruling 33/35 追究的「失实注释」一脉相承，属正面行为。

**未攞弱的既有断言（控制器机械核验）**：`8667b8d` 的全部 `-` 行只有四类——① 两条注释订正（`prod-` 前缀、`padding/radius` 覆盖高估）；② `expectTokenFontFamily` 签名重构（由仅接受 `string` 改为 `Locator | string`，旧的 1 条 `expect(` 被新的 1 条 1:1 取代）；③/④ 搜索元素由 `.value-panel .ui-input__control` + `.first()` 改为已定义的 `valueSearch`（共 2 处，对应新增 2 处）。**无任何断言被删除或放宽。** 断言数 112 → 114，增量恰为新增的双向 hover 守卫。

**配额**：`check:ui` ≤2、`test:contracts` ≤2、`test:unit` ≤2、e2e（仅属性页 spec）≤2、`build` ≤1；**禁跑全量 e2e**（由控制器收口时执行）。

### Task 6: 迁移图纸目录页并复核历史图标例外

> **状态：已关闭**（Step 1–8 全部完成）。Step 7b 人工门禁经用户确认通过（第一轮比对发现红底红字应用级缺陷，已修复并复核通过，见 T6-15）。实现由三轮独立评审闭环（T6-14），责任 R 已裁定（T6-16）。

**Files:**

- Modify: `web/src/views/SheetCatalogView.vue`
- Modify: `web/src/components/sheet-catalog/CatalogActions.vue`
- Modify: `web/src/components/sheet-catalog/CatalogPreview.vue`
- Modify: `web/src/components/sheet-catalog/ColumnEditor.vue`
- Modify: `web/src/components/sheet-catalog/FieldBrowser.vue`
- Modify: `web/src/components/sheet-catalog/TemplateBar.vue`
- Modify: `web/src/components/sheet-catalog/CompatibilitySummary.vue`（原计划漏列，经 Ruling 37 补齐：它仅被 Task 6 Files 内的 `ColumnEditor.vue` 引用，且有 1 条 `expiresWith: Task 6` 的例外）
- Modify: `web/tests/e2e/sheet-catalog.spec.ts`
- Modify: `web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- Modify: `web/scripts/ui-contract-exceptions.json`
- Modify: `web/src/styles/tokens.css`（原计划漏列，经 Ruling 39 补齐：本页有 8 处容器结构尺寸在既有令牌中**无逐字等值项**，而 `raw-visual-value` 按设计**有意覆盖宽高家族**，故唯一合法路径是追加组件层结构令牌）

- [x] **Step 1（RED）**：针对截图红框内保存/另存/删除、添加输出列、导出 XLSX 写计算样式和对齐断言；覆盖 disabled、danger、primary 层级和可见 label。
  - 证据 `evidence/task-6-red.txt`：**5 failed**。红因是**本轮刻意的值变化**（6 个按钮高度归一 36px + 新增可见 label），不是断言写错——见 T6-10。
- [x] **Step 2（迁移）**：工具栏、列编辑器和预览动作改用公共原语；保持字段拖插、表达式、模板保存、预览刷新和 XLSX 导出契约不变。
- [x] **Step 3（图标复核）**：对 `ColumnEditor.vue` 的 `↑ / ↓ / ✕` 做同状态截图与键盘行为对照；**判保留**（依 T6-8 的四条判据 + `ColumnEditor.vue:8` 的 A1 用户已接受差异），未迁移、未加宽 112px 轨道；3 条例外的 `reason` 写全判据与 A1 依据，`expiresWith` 已改写为「下一次目录页视觉 Spec 修订」。
- [x] **Step 4（字体复核）**：对表达式等宽字体、长列名、50 列计数和表格横向溢出做布局断言，确认 IBM Plex Mono 不造成截断或动作列覆盖。字号全部借语义/组件令牌，**未新增字号令牌**（T6-3 / Ruling 38）。
- [x] **Step 5（正交证据）**：保存浅/深默认、禁用保存、删除危险态、窄屏溢出共 5 张。已入库 `docs/dst-manager/specs/assets/SPEC-DM-012/production/t6-*.png`（提交 `387efb5`）；每张均配计算样式或几何断言。需 `DST_MANAGER_WRITE_G8_EVIDENCE=1` 才会写入版本库目录。
- [x] **Step 6（例外清退）**：除经 Step 3 复核保留的 **3 条** `unicode-structure-icon`（`↑ / ↓ / ✕`，依 A1）外，图纸目录页零例外。**实测达成**：目录页 75 → 3，全表 258 → **186**；`check:ui` EXIT=0。
  - **原措辞为计划缺陷（Ruling 39 订正）**：原文写「保留的**唯一**条目」，但 `↑ / ↓ / ✕` 本就是 **3 条**独立例外，字面目标不可达。先例：Ruling 37。
  - **收口不变量**：Task 6 名下原 **75** 条（74 Files 内 + 1 `CompatibilitySummary.vue`）→ 清退 69 条 `raw-visual-value` + 2 条 `visible-input-label`，保留 3 条 → **终态 186 条 = 258 − 75 + 3**；`check:ui` 裸违规 **187 = 186 + 1 动态白名单**。
- [x] **Step 7a（自动验证，控制器亲跑）**：`check:ui` **EXIT 0**；`test:contracts` **0**（83/83）；`test:unit` **0**（11 文件/104）；`build` **0**；两个目录页 spec **0**（**91 passed / 0 failed / 0 flaky**）。未跑全量 e2e（控制器收口时跑）。详见 T6-11。
  - **评审轮后重跑（T6-12 落地后）**：spec **0**（**91 passed / 0 failed / 0 flaky**）、`check:ui` **0**；5 张 t6 PNG 已按终态重采入库。
- [x] **Step 7b（人工门禁）**：人工对照用户第 2 张截图——**待用户确认**（该截图未入库，worker 被明确禁止声称完成）。**实现与三轮评审均已闭环（T6-14）。** 5 张持久 PNG 已入库：`docs/dst-manager/specs/assets/SPEC-DM-012/production/t6-{save-light-1440x1000,save-dark-1440x1000,save-disabled-light-1440x1000,delete-danger-light-1440x1000,narrow-900x700-light}.png`。
  - **第一轮人工比对结果：发现缺陷**（删除确认对话框红色按钮文字不可见）→ 已诊断、修复、变异自证、全量 e2e 514 passed（详见 **T6-15**），相关证据 PNG 已按修复后状态重采。**第二轮人工比对：用户确认通过**（答「已确认通过，关闭 Task 6」）。**Task 6 正式关闭。**
- [x] **Step 8（提交）**：本任务实际分为逐步提交（超时/崩溃后不再丢进度）：`eb7fa66` 承接迁移 → `43e5a72` 断言 → `2926cfb`/`392e8a3` 高度归一 → `7d3a214` 例外清退 → `b229729` 证据 spec → `387efb5` 证据入库与断言稳定性修正；报告 `task-6-report.md`。原计划的单一提交 `统一图纸目录页控件视觉基础` 被逐步提交取代（运维必要性，非计划偏离）。

#### Task 6 控制器裁定（T6-1 … T6-6，派发前下达）

**T6-1（例外基线，控制器实测）**：Task 6 名下例外 = **74 条**，逐文件为 `SheetCatalogView.vue` 7、`CatalogActions.vue` 9、`CatalogPreview.vue` 8、`ColumnEditor.vue` 26、`FieldBrowser.vue` 13、`TemplateBar.vue` 11；按规则为 `raw-visual-value` 69、`unicode-structure-icon` 3、`visible-input-label` 2。与 Files **1:1 对应、零外溢**。开工前不变量 **259 = 258 例外 + 1 动态白名单**。

**T6-2（Ruling 37，计划缺陷订正）**：`expiresWith` 写 `Task 6` 的条目共 **75** 条，比 Task 6 Files 内的 74 条多 **1** 条——孤儿为 `src/components/sheet-catalog/CompatibilitySummary.vue` 的 `raw-visual-value|.compat-line font-size:13px`。该文件**仅被 `ColumnEditor.vue` 引用**（Task 6 Files 内），其排除属计划漏列。**裁定：把 `CompatibilitySummary.vue` 加入 Task 6 Files**（沿用 Ruling 25/31 先例）。否则 Step 6 的「零例外」字面目标不可达，worker 只会撞上无解冲突。

**T6-3（字号层级落点，接续 T5-1 与责任 K）**：控制器实测语义层**确实没有** 14px / 18px 独立档位（`--font-label`/`--font-table`=13px、`--font-caption`=12px、`--font-body` 是 **size/line-height 对**且只许用于根元素、`--font-ui`/`--font-mono` 是**字族非字号**）。故：
- **裁定：本轮不新增任何字号令牌**，与 Ruling 31 口径一致。14px 标题**借用组件层 `--button-font-size`**、18px 页标题**借用 `--modal-title-font-size`**，均**逐字等值、零视觉变化**，并在使用处加注释指向责任 K。
- **合规依据（重要，勿被误判为违规）**：ARCH-DM-007 §4.1 要求「只消费**已声明的语义令牌或组件令牌**」——借用组件令牌**符合**该约束；**真正违规**的是直接使用 `--font-size-*` 原语。
- **先例**：Task 4 已对 `.brand` 借用 `--button-font-size`，责任 K 已把该借用登记为既有事实。
- **责任 K 升级**：消费者从「Task 4 的 1 处」扩到「Task 6–8 至少 7 处」；Task 12 必须裁决「补 `--font-title` 语义令牌还是明文允许借用」，**不得**让借用沉淀为事实标准。
- **先查层叠再改字号（Ruling 32 教训）**：控制器已核实全仓**无**全局 `h3` 规则、`.modal-card h2` 也不覆盖 `.catalog-head h2`（页面本地规则，**有效**）——与 Task 5 两个 `<h2>` 被 `.modal-card h2` 覆盖的情形不同。同理 `.head-title` 先例落 `--font-label`(13px)。

**T6-4（Step 3 图标复核的可核验判据）**：`↑ / ↓ / ✕` 三条 `unicode-structure-icon` 例外**必须**走 Step 3 的对照程序，判据四条全中才判「等价或更好」：① 可点面积 ≥ `--tap-target-min`(32px)；② 有 accessible name（不能只靠字符本身）；③ 原生 `button` 键盘可聚焦可激活；④ 同状态（默认/悬停/禁用）截图视觉不劣化。若判迁移：`UiIconName` **已含** `chevron-up` / `chevron-down` / `close`，**无需扩联合类型**，直接删 3 条例外。若判保留：**必须**补齐 `type`、accessible name、点击面积，且例外 `expiresWith` 改写为「下一次目录页视觉 Spec 修订」——**不得**继续写 `PLAN-DM-029 Task 6`（否则留下永久假到期债务）。

**T6-5（两处 `visible-input-label`）**：`ColumnEditor.vue` 的 `input:text:` 与 `FieldBrowser.vue` 的 `input:text:query` 必须补**可见 label**（检查器规则名为 `visible-input-label`，仅加 `aria-label` **不解除**该例外）。`CompatibilitySummary.vue` 虽无该规则条目，同一输入同样适用。

**T6-6（门禁配额）**：每项门禁最多 **2** 次；Step 7 的 e2e 只跑两个 spec 文件（用文件名收窄，**禁跑全量**）；`build` ≤1 次。**禁触**：`web/src/components/ui/**`（原语已定稿）、`web/src/styles/**`、其他页面的 spec、`.planning/**`、`changelog.md`、`.superpowers/**`。**遇冲突停下报告，不得自行放宽任何约束。**

**T6-7（Ruling 39：结构尺寸无令牌 → 开放 `tokens.css`，新增 7 个组件层结构令牌）**：worker 侦察后停下报告「Step 6 在当前 Files 内不可达」，控制器**逐条独立复核为属实**：8 处容器结构尺寸在语义层/组件层无逐字等值令牌。裁定 **A（修正版）**，驳回「保留为残留例外」（B）。

- **驳回 B 的依据（控制器实读检查器源码）**：`web/scripts/ui-contracts/visual-values.mjs` 的 `RAW_VISUAL_PROPERTIES` **有意包含** `width/min-width/max-width/height/min-height/max-height`，其文件头注释原文为「图标/控件**尺寸**（宽高家族成对书写，只覆盖高度会漏掉图标）」——**布局几何量按设计就是要令牌化的**，把结构尺寸留作永久例外与该规则的设计意图直接冲突。
- **同一文件证实责任 H 为真**：`COMPUTED_VALUE_PATTERN` 豁免 `calc(`/`min(`/`max(`/`clamp(`/`env(`/`var(`，故用 `calc(425px)` 包裹常量可静默过检。worker **未**采用该手法，也**未**用 `flex-basis`/inline style 夹带尺寸，**保留记录**。
- **8 条中的 2 条实为「值等值但语义不符」**：`--overlay-pop-max-height`=300px（语义为浮窗）、`--shell-bar-height`=52px（语义为壳层条高）。**借用它们才是真错误**（Ruling 33/35 所打的语义说谎反模式）→ 必须另立令牌。
- **授权范围（严格）**：`tokens.css` **仅追加**组件层结构令牌，**仅 7 个**，值**逐字等值**、零视觉变化；**禁止**改既有令牌的名字/值/顺序；**禁止**新增字号令牌（T6-3 不变）；**禁止**改令牌文件描述性注释（责任 I 措辞收窄由控制器收口时处理）。
- **令牌名（按角色/域命名，单一一致前缀）**：沿用既有 `--definition-row-height`/`--compare-card-max-width` 先例。控制器**澄清**「令牌名不得含页面名」的原意是禁止**视图文件名派生**（如 `--sheet-catalog-view-*`）；`sheet-catalog` 是**功能域**非页面名，且统一前缀使这笔债可成组审计。7 个：`--catalog-pane-height:425px`、`--catalog-preview-min-height:250px`、`--catalog-preview-table-max-height:300px`、`--catalog-columns-max-height:330px`、`--catalog-field-browser-max-height:235px`、`--catalog-template-select-min-width:220px`、`--catalog-column-expression-min-height:52px`。
  - **其中 `--catalog-pane-height` 必须合并 worker 原提的两条**（`.catalog-row{height:425px}` 与 `.column-editor{min-height:425px}`@≤980px 属**同一套 425px 首屏密度预算**）。拆成两个同值令牌正是责任 I 点名的「单点组件令牌」重复，**照拆打回**。
- **圆角授权**：`.column-row input`/`textarea` 的 `border-radius:5px` → `var(--radius-sm)`(6px) **批准**。理由：仓库无 5px 档位，为 1px 去动原始圆角刻度属更大的架构改动；先例为 Task 5 把 `999px` 归一到 `--radius-full`(9999px)。**这是本轮唯一的显式视觉偏离，必须在报告中单列披露。** **→ 本项已被 T6-12 取代**（实际落点为 8px；文本域也改为 8px），以 T6-12 为准。
- **责任 I 记账**：组件层结构令牌由 6 条增至 **13** 条。

**T6-8（Step 3 图标复核结论与 `32px` 折中 → 新登记责任 R）**：worker 依 T6-4 授权判**保留**，控制器独立复核其四条理由**全部属实**（实读 `UiIconButton.vue:28-43`：确为 `border:1px solid transparent` + `--color-text-secondary` + `var(--icon-button-size)`(36px) + `background:none`；实读 `ColumnEditor.vue:195/211-214`：末轨确为 `112px`、`.row-actions{gap:4px}`，本行为 `--color-border-strong` 实边框 + `--color-bg-surface` 底 + `--color-text-primary` + ✕ 带 `--color-danger`）。

- **控制器补入的决定性证据（worker 未引用）**：`ColumnEditor.vue:8` 逐字记录 **「A1（用户已接受差异）：操作列继续使用 ↑ / ↓ / ✕ 图标按钮与完整 aria-label，因此该轨道（112px）比冻结 Demo 的 188px 文字按钮列更窄。」** —— 保留图标是**已被用户接受的设计**，112px 轨道是其**后果**。故判**保留、不得迁移、不得把轨道加宽回 188px**。
- **点击面积 `30px` → `var(--tap-target-min)`(32px) 批准**，轨道预算实测：现行 3×30+2×4=98 ≤112；32px 时 3×32+8=**104 ≤112 ✓**；36px 需 3×36+8=**116 >112 ✗**，gap 压到 2px 才恰好 112（零余量）。**即 36×36 在不推翻 A1 的前提下不可达。**
- **新登记责任 R（Task 12 收口）**：密集表格行内动作按钮的尺寸上限受 A1 的 112px 冻结轨道约束，**无法**满足 SPEC-DM-010「图标按钮 ≥36×36」；本轮取 `--tap-target-min`(32×32) 折中，需由 Spec 归属方确认或调整轨道宽。
- `30→32` 与圆角 1px 同属**可见变化**，必须一并单列披露（依据：Step 3「补齐…点击面积」）。`type="button"` 与完整 aria-label 已存在（`ColumnEditor.vue:167-169`），**保持不动**。

**T6-9（实施轮超时与「承接」裁定，Ruling 40）**：首轮 worker（`2a200b54`）在 `timeoutMs:1800000` 超时失败，**未产生任何 commit**，工作区留下 8 个已改文件。控制器取证（**全部亲跑，不采信任何转述**）：

- **未完成面**：两个 e2e spec（`sheet-catalog.spec.ts` / `sheet-catalog-visual-evidence.spec.ts`）与例外表**均未被触碰** → Step 1（RED）、Step 5（证据）、Step 6（清退落盘）、Step 7、Step 8 全未完成。
- **零验证**：日志检索显示它**从未调用任何门禁或测试**（`check:ui`/`test:unit`/`test:contracts` 的全部命中都是提示词与计划正文，非工具调用）。故其改动属**未经任何验证**的代码。
- **死因线索（已澄清，非纪律问题）**：它自写的清退脚本在**每文件清退条数断言**上抛错（`ColumnEditor.vue` 实际 **23** / 预期 24），随后把预期改成 **23** 再超时——它是在**修正自己的计数**，**不是**放宽断言。（控制器读回该脚本：预期表已为 23，且含 `kept !== 3`、`before - total !== 186` 两道断言。）
- **控制器亲跑 `check:ui`**：**EXIT=1，但真实违规 0 行**；全部失败均为 `stale-exception`，共 **72** 条（70 `raw-visual-value` + 2 `visible-input-label`）→ **75 − 72 = 3**，恰为保留的 3 条 `↑/↓/✕`；终态 **186 = 258 − 72**，与 T6-7 预告值**逐字吻合**。
- **改动质量实测**：`tokens.css` = **+7 行，恰为 T6-7 指定的 7 个令牌名与逐字等值**（已并入同层组件令牌块）；`.row-actions button` 已落 `var(--tap-target-min)` 与 `var(--radius-sm)`；T6-5 两处**可见 label 已补**（两条 `visible-input-label` 均已 stale）。未触碰 `ui/**` 与其他 `styles/**`。

**裁定：承接（不重做）**。理由：迁移经检查器亲测**零真实违规**、与 T6-7/T6-8 口径逐字一致；重做只会再耗 30 分钟并可能产出更差结果。控制器已把该 diff 存为补丁 `task-6-partial-timeout.diff` 并建参考分支 `wip/task6-timeout-2a200b54` 作锚点。

**暴露的流程偏差（如实登记，不掩饰）**：该轮把 Step 2（迁移）做在 Step 1（RED）**之前**，违返「RED → GREEN」。**补救要求**：续轮必须**先把迁移 revert（`git stash`）后写断言并捕获 RED**，再恢复迁移取 GREEN——证据等价、顺序不同；对「迁移前后均通过」的回归钉断言，必须另做**变异自证**证明其非空转。

**操作教训（本轮最重要）**：30 分钟默认超时不足以覆盖「8 文件迁移 + 2 spec + 例外表」的体量。续轮须**每完成一步即提交**，使超时不致丢失进度。

**T6-10（控件高度归一裁定：Ruling 41，接受 36px）**：续轮写断言后跑 RED，**5 条断言全红（EXIT=1）**，红因是承接的迁移把本页 6 个动作按钮的高度**字面量归一为 `UiButton` 默认 36px**，而迁移前为 34/34/30/30/30/32。worker 主动停下请裁定 A（回到 34px 紧凑档）或 B（接受 36px 归一）。

控制器独立复核（全部亲跑）：
- worker 列了 4 条，**漏报了 2 条**：`CatalogActions.vue` 的 `.success button` 与 `.export-error button` 也是 30px → 被改高度的控件共 **6 个**。
- `UiButton.vue:14` **已内置 `size="compact"`**（34px、padding `--space-3`）→ **A 是可实现的**；控制器驳回 A **不是因为做不到**。
- **全仓 `size="compact"` 消费数 = 0**；Task 4/5 已接受并经评审的迁移中，属性页 16 处 `UiButton` 全部用默认 36px，`.head-actions`/`.link-actions`/`.io-menu` 等工具栏行**无任何 34px 用法**。
- **ARCH-DM-007:34 把该问题本身定义为缺陷**（原文「控件高度存在 `24/28/30/32/34/36/38px` 多档，部分按钮低于 `32px` 最小可点高度」）→ A 会把多档重新铺回，方向与该条相反。
- `TemplateBar.vue:142` 确认 `.template-row .danger-text{min-height:var(--control-height-compact)}`(34px) 与同行 `UiButton` 的 36px **不一致属实**。

**裁定 B**：全页动作按钮统一 `UiButton` 默认 **36px**，**全页禁止 `size="compact"`**；并**必须一并修 `TemplateBar.vue:142`** 使 `--template-row` 行内高度真正统一（保持其「透明底 + 危险文字、不用实心 danger 变体」的低强调写法与理由不动）。

**代价必须披露（不许含糊）**：**Task 6 对这部分控件不是「零视觉变化」**。报告需单列「有意视觉变化清单」（文件:规则 → 前值 → 后值 → 依据），至少覆盖 6 处高度 `34/34/30/30/30/32 → 36`，以及 **3 处水平内边距 `--space-3`(12px) → `--space-4`(16px)**（`.dock-row` 迁移前已是 `--space-4`，无变化）。

**断言要求**：钉新值 36px + 额外加一条「行内一致性」断言（`--template-row` 与 `--dock-row` 内所有按钮 computed height 相等）并**先红自证**（改回 34px 必须能失败）。

**T6-11（Ruling 42：runner 二次失败后的控制器收口 + 两处断言稳定性修正 + `g8` 资产还原）**：续轮 worker `4b447117` 完成 Steps 1–6 后，runner 进程在 ~33 分钟（**非超时**，预算 60 分钟）消失（`proof-write-failed`）。**已提交的 6 个 commit 全部保全**——「每完成一步即提交」的纪律直接兑现了，与首轮「超时即丢 30 分钟」形成对照。剩 Step 7/8。

- **控制器接手 Step 7 的理由**：剩余工作**只剩跑命令**；`check:ui` 与 e2e 本来就是控制器的独立复核职责；连续两次 runner 失败，再派一轮的期望收益低于风险。
- **首次 e2e 暴露 2 个问题**：① `sheet-catalog-visual-evidence.spec.ts:436` 的**既有**键盘 Tab 环用例**真红**（该用例在 `eb7fa66^` 就已存在且通过，anchors 一字未改）→ 初判象是产品回归；② `sheet-catalog.spec.ts` 的新用例 **flaky**（`label[for="ui-input-7"]` 找不到，重试通过）。
- **根因（控制器实证，非推理）**：迁移把列名输入与字段搜索由 `aria-label` 改为 `UiInput :label`（T6-5 要求**可见 label**，仅 `aria-label` 不解除该例外）。那个键盘用例用 `getAttribute("aria-label") ?? textContent` 取可访问名称 → **看不到由 `label[for]` 命名的控件**，于是 anchors 里的「输出列名 1」永远不出现。而 `ui-input` 的兜底 id 来自**模块级计数器**（`instanceId.ts`），**按挂载顺序而非行序分配**（实测同一页为 `ui-input-1/8/9/10`），旧断言「先读 id 再查 `label[for]`」跨**两次往返**，控件重挂载即换 id → flaky。
- **裁定：两处都是断言方法学问题，不是产品回归**（Tab 环本身完整、`label[for]` 关联本身正确，其实是可访问性**改善**）。修法**不得放宽语义**：Tab 环 anchors 一字未改，只把名称提取改为「`aria-label` 优先，否则取 `el.labels[0]`」；`expectVisibleLabel` 改为 Playwright 原生 `toHaveAccessibleName` + 独立可见 label 定位，并**新增**「命中 INPUT」「不是仅靠 `aria-label`」两条**更严**约束。
- **变异自证（证明守卫是活的）**：`tabindex="-1"` → 键盘用例**红**；`.ui-input__label{display:none}` → 可见性断言**红**，而同次 `toHaveAccessibleName`（`:1272`）**仍通过** → 证明 Chrome 在 label 被隐藏时**仍**用它的文字命名，**必须靠可见性断言才真正落实 T6-5**。两处临时变异**已完全还原**（`git status` 确认）。
- **`g8-*.png` 主动还原**：以 `DST_MANAGER_WRITE_G8_EVIDENCE=1` 跑一次目录页证据 spec 会**连带无条件覆盖** SPEC-DM-012 的 6 张既有生产证据。实测**本机截图逐字节不可复现**（同 spec 连跑两次，5 张 t6 PNG 的 md5 **全不同**）→ 这 6 张的字节变化**既不能归因**给 Task 6 的刻意改动、**也不能排除**是采集噪声。**在无法归因的情况下重写他 Spec 的验收资产不可接受** → `git checkout` 还原，只提交 Task 6 自己的 5 张。新登记**责任 T**。
- **最终门禁（控制器亲跑，取真实 EXIT 码）**：`check:ui` **0**；`test:contracts` **0**（83/83）；`test:unit` **0**（11 文件/104）；`build` **0**；两个目录页 spec **0**（**91 passed / 0 failed / 0 flaky**）。e2e 共 4 次（RED、变异、GREEN×2）。
- **工具陷阱（记入计划）**：`npm ... | tail -30; echo "EXIT=$?"` 打印的是 **`tail` 的退出码**；必须重定向到文件再取 `$?`——否则会把 `check:ui` 的 EXIT 1 **误报为 0**。
- **评审轮**（`2ce5d5a5`，`opencode-go/deepseek-v4.1-flash`）：结论 **Needs fixes / 0 Critical**。技术面（72 删除/0 新增/186/保留 3、令牌 +7 逐字等值、`ui/**` 与 6 张 `g8-*` 未动、无 `size="compact"`、**控制器两处断言改动确实未削弱守卫**）均经**独立复核确认**。问题全部落在**披露表**即控制器自己写的那部分：报告把列名输入圆角写成 6px（**代码实为 8px**）、把删除按钮误列入 padding 12→16px、且漏披露两处输入迁到 `UiInput` 的高度/字号/padding 变化。**控制器已逐条复核为属实并全部修正**（见 T6-12 与报告 §10）。

**T6-12（Ruling 43：圆角落点与输入类型还原 —— 评审轮处置）**：

- **列名输入 5px → `--radius-md`(8px)：追认批准**。`.column-row input` 规则**整条删除**，输入改由 `UiInput` 渲染，半径由原语提供（`UiInput.vue:53`）。页面侧覆写原语半径会与 `UiInput`/`UiButton` 的分工相冲（同 Ruling 33/35 驳回页面侧 `:deep()` 的口径）。**它超出 T6-7 字面授权的 6px，必须以裁定追认，不得只靠改表含糊过去。**
- **表达式文本域 5px → 也改为 `--radius-md`(8px)**。理由：同一行相邻控件的圆角必须一致（**T6-10 已就「同行高度不一致」立过同一原则**），且 8px 是全应用表单控件档；`--radius-sm`(6px) 在本仓属**文字/链接型按钮**档（Task 5 的 `button.link`、`.empty-values button` 先例）。保留 T6-7 的 6px 会留下「输入 8px / 文本域 6px」的同行不一致，与 T6-10 的裁定自相矛盾。
- **字段搜索框 `type="search"` → 还原为 `type="text"`**。~~该变更未获授权、未披露……属 Spec 侧决策~~ **→ 本项已被 T6-13 推翻（控制器误判，见 T6-13）。最终状态为 `type="search"`。**
- **落地与验证**：三项均已实现（提交 `aec713e`），5 张 t6 PNG 按终态重采入库（先前版本已过时）；重跑两个目录页 spec **91 passed / 0 failed / 0 flaky**、`check:ui` **EXIT 0**。
- **备忘（Minor-6）**：`sheet-catalog.spec.ts` 已增至 ~1408 行；本次新增块属计划点名（plan-mandated），未来可把 Task 6 块拆为独立 spec。

**T6-13（Ruling 44：推翻 T6-12 第③项 —— 字段搜索框保持 `type="search"`；控制器误判自纠）**：T6-12 第③项把字段搜索框由 `type="search"` 还原为 `type="text"`，理由是「未获授权、未披露」。二次评审（`bbd6a82c`）指出该前提**未计入既有先例**，控制器**复核为属实**：

- `PropertyDefinitionPanel.vue:164`、`PropertyValuePanel.vue:214`（Task 4/5，**已评审且 Task 5 已关闭**）均为 `<UiInput type="search" :label=…>` —— 与本页修复前**完全同一个组件＋属性组合**。
- 且其规格是**按角色钉死的**：`properties-definitions.spec.ts:106` 与 `properties-buffer.spec.ts:72` 均用 `getByRole("searchbox", …)`。还原后，图纸目录页的字段搜索框成为全应用**唯一**不是 searchbox 的搜索框 —— 而控制器在 T6-12 第①项中**正是用「全应用一致」论证 8px 圆角的**，属自相矛盾。
- `SPEC-DM-012` **未**规定该输入的 type/外观（评审者已 grep 核实）→ 不存在「冻结 Demo 迫使还原」的理由。
- 目录页两个 spec 里 `searchbox` 出现 **0** 次 → 套件全绿**不能**佐证任一方向。
- **裁定：恢复 `type="search"`**，并**新增 searchbox 角色断言**把该惯例变成机械守卫（同责任 S/U 的一贯做法）。它本来就是 worker 的原始实现——**还原是控制器的错误，不是 worker 的**。

**方法论教训（本计划第三次同类，已写入 T6-13）**：控制器在只有推理、**未检索既有先例**时就裁定了「未获授权」。
- Ruling 36 教训 = 不得凭目录名推断归属；Ruling 39 教训 = 裁定前必须实读检查器源码；**本条 = 宣判「未授权/无先例」之前必须全仓检索同类用法（组件＋属性组合），把命中的先例写进裁定**。
- 附带一条工具纪律：**当 `grep` 对评审者声称存在的东西返回空结果时，不得据此判定评审者失真**——本会话已知 bash 包装器会吞引号造成**假阴性**（控制器第一次 `grep 'type="search"'` 即得空结果，改用 `sed` 直读才看到真相，**差点据此误判评审者造假**）。必须换方法（`sed`/`read`）复核。

**T6-14（评审闭环，Task 6 实现部分收口）**：三轮独立评审（`2ce5d5a5` 首轮 → `bbd6a82c` 二次 → `2638454a` 最终验证）均已闭环：

- 最终验证结论：**All findings addressed, no new Critical/Important breakage**。
- 首轮遗留的 Important（披露表把 8px 写成 6px）与 3 条 Minor 均已 ADDRESSED；二次评审新引入的 Important（`type` 还原方向错）已由 T6-13 纠正为 ADDRESSED，且评审者核实新守卫**有效且非空转**（`fieldSearchLabel` 与 `type="search"` 在该作用域各只出现一次）。
- **本轮全部门禁（控制器亲跑，真实 EXIT）**：`check:ui` **0**；`test:contracts` **0**（83/83）；`test:unit` **0**（11 文件/104）；`build` **0**；两个目录页 spec **0**（**91 passed / 0 failed / 0 flaky**）。
- **例外表**：目录页 **75 → 3**，全表 **258 → 186**（`186 = 258 − 72`）。
- **Step 7b 人工门禁已完成**（用户确认通过；第一轮比对发现的应用级缺陷见 T6-15），以及已单独登记的责任 A–V（Task 12 收口）。
- **提交链**：`eb7fa66` → `43e5a72` → `2926cfb` → `392e8a3` → `7d3a214` → `b229729` → `387efb5` → `aec713e` → `416d11d`（+ 控制器计划/changelog 提交 `b11306c`/`6097924`/`08e0bd7`/`ad777e5`/`c4ef846`）。

**T6-15（Step 7b 人工门禁发现的应用级缺陷与修复 —— 用户报告）**：用户在对照第 2 张截图时报告「`t6-delete-danger-light-1440x1000.png` 中删除模板确认对话框的红色按钮文字没有显示」。

- **根因（已浏览器实测确认，非推理）**：`legacy.css:36` 的通用规则 `.danger,.error{color:var(--color-danger)}` 在 **legacy 层**，与 `primitives.css` 的 `.modal-actions button.…danger{color:var(--color-on-accent)}` 在 **primitives 层**——而**层顺序优先于选择器特异性** → legacy 层静默胜出 → `color` 与 `background` 都是 `--color-danger`，红底红字。实测：`{"text":"删除","color":"rgb(194, 48, 43)","bg":"rgb(194, 48, 43)","opacity":"1"}`。
- **影响面**：`ConfirmModal` 是共享原语，`danger: true` 的调用点共 **8 处**（`App.vue` 关闭工作区/删除子集/发布、设置面板、CSV 导入、修复、恢复、目录页）→ **全部**确认按钮文字不可见。
- **归因：不是 Task 6 引入**。Task 6 对 `styles/` 只改了 `tokens.css`（+7 行令牌）。该回归由**分层工作本身**引入（`b0786d7 统一前端字体令牌与样式分层` = 本计划 Phase 1）：分层前高特异性规则胜出，分层后 legacy 层无视特异性胜出。
- **修复（不动被广泛依赖的通用 `.danger`，而是给原语修饰类做命名空间化）**：`ConfirmModal.vue` 的 `:class="{danger}"` → `:class="{'modal-danger': danger}"`，`primitives.css` 同名规则同改；并去掉 `.modal-irr` 上冗余的 `{danger}`（其颜色由 `.modal-irr` 无条件提供）。
- **回归守卫（已变异自证）**：断言危险按钮 `color` **等于 `--color-on-accent`** 且 **不等于 background**；把类名改回 `danger` 时该用例**红**且报错正是预期那条。
- **系统性扫描（`controller-layer-collision.mjs`）**：两层「同名 class 且属性重叠」——修复前 **1 个**（恰好就是 `.danger`/`color`，**别无他例**），修复后 **0 个**。
- **验证**：原语被 8 处调用，故跑**全量 e2e**：**514 passed / EXIT 0**；`check:ui` 0、`test:contracts` 0（83/83）、`test:unit` 0（104）、`build` 0；重采证据后**目视确认**白字「删除」已显示。

> **收口责任 V（分层级联的静默覆写；本次由用户人工门禁发现）**：固定层顺序 `tokens, reset, primitives, legacy` 使**层顺序优先于特异性**，于是 legacy 层里任何与原语同名的通用 class 都会静默改写原语样式——本计划的 Phase 1 分层工作因此引入了**一个应用级的视觉回归**（红底红字，8 个确认弹窗受影响），而且**现有任何门禁都发现不了**：`check:ui` 只查规则合规性、e2e 没有对比度/可见性断言、也没有基线截图比对。这与责任 S（值变化）、责任 U（组件化输入脱离检查器覆盖）构成**同一模式：现有门禁验证的是「规则」，不是「渲染结果」**。收口方向：① 把「primitives 层不得使用与 legacy 同名的通用 class」变成**可机械检查的规则**（可扩展 `check-ui-contracts.mjs`；当前扫描结果 0，基底干净，正是立规则的好时机）；② 考虑补一类「不可见文字」检查（文字色 == 底色、或对比度过低），至少覆盖阴影/着色按钮；③ Task 12 把「门禁只能验规则、不能验渲染」作为一个共同风险统一裁决（S/U/V 三条已构成模式）。

**T6-16（责任 R 裁定结果 —— Spec 归属方 = 用户，2026-09-15）**：用户裁定选 **「豁免 36px 下限，保持 32×32」**。

- **裁定内容**：图纸目录页同行 `↑ ↓ ✕` 保持 **32×32**（已满足全局最小可点 ≥32px），并在 **SPEC-DM-010** 写入一条**有界豁免**：密集表格行内图标按钮的下限为 32px（附前置条件：仅限行内密集操作轨且轨道宽 ≤112px，防止外溢到普通图标按钮）。A1 的 **112px 轨道不变**。
- **理由**：① 零视觉变化，A1（用户已接受差异）不被推翻；② 32px 满足 ARCH-DM-007 §4.1 的全局最小可点下限；③ 轨道预算 3×32+2×4=104 ≤112，尚有 8px 余量。
- **实现状态**：**当前代码已符合**（T6-8 已把点击面积由 30px 提到 `--tap-target-min`(32px)），故**无需改代码**；剩余的只是把豁免写进 SPEC 文档。
- **待办归属**：**SPEC-DM-010 的措辞修改交 Task 12「文档收口」**（与责任 A–U 一并落地），本任务不顺手改冻结 Spec。**拟写文本已固定如下，以防漂移**：
  > 密集表格行内的图标按钮（表格行操作轨，如列编辑器的上移/下移/删除）最小点击区域为 **32px**（全局最小可点下限），不适用普通图标按钮的 36×36 下限；前置条件：该按钮位于表头/数据行共享的轨道内，且轨道宽度 ≤112px。
- **圆角子项（仍留待 Task 12 与上述措辞一并处理）**：同行 `.row-actions button` 现为 `--radius-sm`(6px)（T6-8 保值），而同行两个字段已因原语约束成为 `--radius-md`(8px)。用户本次选的是「零视觉变化」方向，故**按钮圆角保持 6px 不动**；此差异作为「原语拥有字段半径 + 密集行保留既有按钮样式」的**已知后果**记录，若 Spec 归属方日后希望同行统一，在同一份 SPEC 修订里一并标注。

### Task 7: 迁移图纸页与任务浮层内部控件

> **状态：已关闭**。Step 1–8 全部完成（Step 7 的人工门禁经用户确认通过）。实现经**两轮独立评审**闭环（首轮 Needs fixes / 0 Critical → 修复轮 → 二审 All findings addressed）。除迁移本体外，本任务还**发现并修复了一个先前既有的应用级缺陷**（浮层诊断面板不可读，见 T7-6）与**一个检查器假阳性**（责任 X）。

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
- Modify: `web/tests/e2e/main.spec.ts`（**T7-5 补列**：`main.spec.ts` 是壳层计算样式断言的**既定落点**——Task 2 的 Step 2、Task 4 的 Step 1 都写在它，且 Task 4 的 Step 1 已点名「任务浮层折叠状态」；Step 1 明文要求的「任务浮层动作与状态控件断言」在原 Files 内**无合适落点**——`sheets-*` 是页面 spec，而浮层是壳层组件）

- [x] **Step 1（RED）**：为截图第 1 张的批量模式、属性选择、批量值、批量加入草稿写同行中心、字号、36/38px 档位、disabled 与长文本溢出断言；补任务浮层动作与状态控件断言。
  - **前半已交付**（`sheets-layout.spec.ts` 新增 11 用例，含四视口/200%/批量编辑/表格结构等）。
  - **后半（任务浮层动作与状态控件断言）首轮静默缺席，已由 T7-5 裁定补交**（落点改为 `main.spec.ts`），修复轮 `a355aafe` 执行中。
- [x] **Step 2（迁移）**：工具栏、表单、列设置、属性编辑、表格动作和浮层内部动作改用原语（**注：`TaskOverlay.vue` 的浮层内部控件与手写焦点副本已由 Task 4 按 Ruling 28 迁完，本步骤对该文件是验证性 no-op**）；保持选中、批量修改、草稿与任务 SSE 流程不变。
- [x] **Step 3（动态变量）**：对图纸树宽度等运行时 CSS 变量，在白名单中同时登记写入方与消费方；能改为静态令牌的变量立即清退，不以 fallback 隐藏未定义变量。
- [x] **Step 4（密集布局）**：在 `900/1024/1120/1440` 四视口验证批量编辑区不撑破表格、操作列可达、横向滚动条不遮挡内容；关键控件 200% 浏览器韧性测试通过。
- [x] **Step 5（正交证据）**：保存浅/深默认、批量编辑启用、批量编辑禁用、最窄视口、200% 共 6 张。
- [x] **Step 6（例外清退）**：除阶段 4 专门处理的 `SheetTree.vue` 结构项（**9 条，属 Task 10 Files**）外，图纸页视觉值、按钮和 label 例外清零（`TaskOverlay.vue` 名下 15 条已由 Task 4 清退，无需重复）。
  - **原措辞为计划缺陷（T7-1(F) 订正）**：原文未含字号保留项，但 `15px`/`17px` **无可借值等值令牌且不得新增字号令牌**（T6-3/Ruling 38）→ 必须保留 **4 条**显式例外（`expiresWith` = 责任 K）。先例：Ruling 39 订正 Task 6 Step 6。
  - **收口不变量（T7-1(G)）**：Task 7 清退 **61** 条 = 65 − 4（保留字号例外）→ 全表 **186 → 125**；`check:ui` 裸违规应为 **126 = 125 + 1 动态白名单**。
- [x] **Step 7（验证）**：运行 `rtk npm --prefix web run test:e2e -- sheets-layout.spec.ts sheets-forms.spec.ts sheets-visual-evidence.spec.ts sheets-visual-regressions.spec.ts sheets-columns.spec.ts sheets-editing.spec.ts sheets-navigation.spec.ts` 与 `rtk npm --prefix web run build`；人工对照用户第 1 张截图。
  - **自动验证已由控制器亲跑完成**：`check:ui` **EXIT 0**（例外表 128、零新增）；`main.spec.ts` + 上述 7 个 sheets spec **EXIT 0：211 passed / 0 failed / 0 flaky**；`build` 0；`test:unit` 0（104）；`test:contracts` 0（83/83）。未跑全量 e2e（留待控制器在 Task 12 收口时跑）。
  - **[x] 人工对照用户第 1 张截图：用户已确认通过**（答「已确认通过，关闭 Task 7」）→ **Task 7 正式关闭**。
- [x] **Step 8（提交）**：commit：`统一图纸页与任务浮层控件视觉基础`。

#### Task 7 控制器裁定（T7-1，派发前下达）

**T7-1（令牌/借用政策：预先避开 Task 6 撞过的塔）**。Task 6 的 worker 因「结构尺寸无令牌」在第 6 步停下请裁定（Ruling 39）。控制器已对 Task 7 做同类侦察（`controller-task-7-baseline.mjs`），**同样的塔会重现，故提前裁定**。

**侦察实测**：Task 7 名下 **74** 条 = Files 内 **65**（raw-visual-value 60、visible-input-label 2、raw-hex-color 1、unicode-structure-icon 1、explicit-button-type 1）+ `SheetTree.vue` **9**（只在 Task 10 Files，**已在计划第 715 行登记，非缺陷**）。65 条中的 60 条裸值去重后共 **17 个值**。

**(A) 开放 `tokens.css`：仅追加以下 9 个组件层令牌（取值逐字等值、零视觉变化、按角色/域命名）**：

| 令牌 | 值 | 消费处 |
|---|---|---|
| `--sheet-columns-panel-width` | `380px` | `ColumnSettings.vue` 列设置弹层宽 |
| `--sheet-search-width` | `260px` | `SheetToolbar.vue` `.search-box input` |
| `--sheet-property-search-width` | `180px` | `SheetPropertyEditor.vue` `.editor-search input` |
| `--sheet-bulk-hint-max-width` | `220px` | `SheetToolbar.vue` `.bulk-hint` |
| `--sheet-table-window-min-height` | `130px` | `SheetTable.vue` 表格窗口 |
| `--sheet-title-max-width` | `280px` | `SheetTable.vue` `.title-text` |
| `--sheet-table-row-height` | `44px` | `SheetTable.vue` `th,td` 行高 |
| `--sheet-table-line-height` | `20px` | `SheetTable.vue` `th,td` 行盒高 |
| `--sheet-status-radius` | `10px` | `SheetTable.vue` `.status` 胶囊圆角 |

**(B) 禁止借用（值等值但语义不符 —— 语义说谎，按 Ruling 33/35/39 驳回）**：
- `180px` → `--compare-item-max-height` / `--workspace-name-max-width`（一个是对比卡最大高、一个是工作区名最大宽）
- `130px` → `--workspace-name-max-width-narrow`
- `220px` → `--catalog-template-select-min-width`（**还是 Task 6 的目录域令牌，跨域借用更严重**）
- `280px` → `--panel-search-width`
- `44px` → `--definition-row-height`（属性定义表行高 ≠ 图纸表行高，借用会把两个功能域耦合）
- `20px` → `--icon-size-lg`（图标尺寸 ≠ 行高）

**(C) 允许借用（语义正确）**：`38px` → `--control-height-form`/`--input-height`；`36px` → `--control-height-default`/`--button-height`；`34px` → `--control-height-compact`；`13px` → `--font-label`/`--font-table`；`12px` → `--font-caption`；`14px` → 借组件令牌 `--button-font-size`/`--input-font-size`（**不得用 primitive `--font-size-14`**，同 Ruling 38）；`.chip border-radius:12px` → `--radius-lg`（12px 是真半径档）。

**(D) ★ 字号 15px / 17px：不新增字号令牌，保留为显式例外**（沿用 T6-3 / Ruling 38 政策 + 责任 K）。
- 这两个值**无值等值的可借令牌**（实测），而 T6-3 已定「不新增字号令牌」→ **保留为例外**，`expiresWith` 写「下一次字号阶修订（责任 K，Task 12）」。
- `15px` 有 **3** 个消费者且语义相同（均为面板/区块标题）：`ColumnSettings.vue:109 .cols-title`、`SheetOperationForm.vue:312 .form-head h3`、`SheetPropertyEditor.vue:105 .editor-head h3`；`17px` **1** 个：`SheetToolbar.vue:181 .range-title`。
- **原则性区分（重要，防止与 Task 6 自相矛盾）**：**几何量**（宽/高/最小高/最大宽/行高/圆角）**没有「设计档位」语义** → 可以自由令牌化并保值；**字号代表排版层级** → **不得由页面迁移任务自行发明新档位**，必须交 Spec 归属方。这正是 Task 6 能加 7 个结构令牌、而字号缺口一直登记为责任 K 的原因。

**(E) `raw-hex-color`（1 条）**：`ColumnSettings.vue:107` 的 `box-shadow:var(--shadow-2,0 8px 24px #17203333)`——hex 在 **`var()` 的死 fallback** 里（`--shadow-2` 已定义）。修法：**清退死 fallback** 或把 fallback 里的颜色换成令牌；**不得原样留下**。同见 Step 3「不以 fallback 隐藏未定义变量」。

**(F) Step 6 措辞需订正（先例：Ruling 39 订正 Task 6 Step 6）**：原文「图纸页视觉值、按钮和 label 例外清零」**不可达**，必须明示两类保留：① `SheetTree.vue` 结构项 **9 条**（Task 10）；② `15px`/`17px` 字号例外 **4 条**（责任 K）。

**(G) 收口不变量（控制器实测预告）**：Task 7 清退 **61** 条（65 − 保留的 4 条字号例外）→ 全表 **186 → 125**；`check:ui` 裸违规应为 **126 = 125 + 1 动态白名单**。

**(H) `SheetToolbar.vue` 的 `unicode-structure-icon`（1 条）必须走与 Task 6 Step 3 同构的复核程序**（T6-4 的四条判据：可点面积 ≥32px、有 accessible name、原生 button 键盘可及、同状态截图不劣化）；判迁移则用 `UiIconName` 联合类型（已含 `chevron-*`/`close`），判保留则**必须**把 `expiresWith` 改为「下一次图纸页视觉 Spec 修订」而不得继续写 `PLAN-DM-029 Task 7`。

**T7-2（首轮交付后的复核与裁定 —— 控制器独立复核）**：worker `4336920f` **交付一半即停下并如实披露**（好行为）。控制器独立复核结论：

**已核实为真实且合格**（不采信转述）：
- `tokens.css` **恰 +9 行**、逐字等值、**无 `-` 行**（未改既有令牌）、无字号令牌；**9 个令牌每个都有且仅有 1 个消费文件**（无死令牌）。
- `ui/**` 未被触碰；`styles/**` 只有 `tokens.css`；`TaskOverlay.vue` 正确为验证性 no-op。
- 例外表 **186 → 128**；**删除 58 / 新增 0**（用**指纹集合**比较确认，不是看 diff 的 +/- 行——diff 里那行 `+fingerprint` 只是条目**重排**造成的假象）。
- RED 证据 `evidence/task-7-red.txt` 真实（**4 failed / 3 passed**，红因与变更值一一对应）。
- **质量亮点**：worker **自己的断言抓到它自己引入的回归**——删掉页面规则后 `.filter-toggle` 落到 `legacy.css:102` 变 **37.5px**，当场报红并修复（改为 `UiButton size="compact"`，34px 保值）。

**裁定（针对 worker 提的 3 项）**：
1. **保留 7 条而非 4 条：接受，分三类**：4 条字号（T7-1(D) 已授权）；**2 条 `SheetTable.vue` 复选框接受为有界豁免**（数据表惯例由 `<th>` 列头承担可见标签，检查器只认 `<label>`/`label[for]`，**模型覆盖不到表头即标签** → 登记为规则缺口）；**1 条 `✕` 接受保留**，但其**可点面积约 12×12px 低于 ≥32px 下限** → **并入责任 R**（同属「密集行内控件」待裁问题），不硬撑 32px（会撑破 12px 标签胶囊）。
2. **续轮优先级与配额**：见下（已派发 `eeb6c0e0`）。
3. **密集单行控件保持原生（不用 `UiInput`/`UiSelect`）：接受** —— 这些控件本身已有可见 label，换成原语会把行压成两行＝视觉回归，与「布局保持」契约冲突 → 登记为**原语缺口**（与责任 O 同类）。

**控制器发现并已下令修正**：
- **假到期债务**：例外表里 **9 条 `SheetTree.vue` 条目的 `expiresWith` 仍写「PLAN-DM-029 Task 7」**，而该文件属 **Task 10 Files** → 指向永远不会再碰它们的任务（T6-4 明令禁止的写法）→ 续轮改为 `PLAN-DM-029 Task 10`。（顺带核实：全表已无指向已关闭 Task 5/Task 6 的过期条件 ✓）
- **责任 W 已登记**：两页工具栏密度不一致（见下），**不改 worker 实现**。

**T7-3（续轮工作清单）**：Step 1 补强（`--sheet-property-search-width` 断言 + **回归钉变异自证 ≥2 条**）→ Step 3 动态变量（白名单登记写入方与消费方，可静态化的立即清退，不得用 fallback 掩盖）→ Step 4 四视口 + 200% → Step 5 六张截图 → 例外表两处机械修正 → Step 7 重跑（不变式：仍为 128 条、`check:ui` EXIT 0）→ Step 8 提交。

**T7-4（证据持久化落点；worker 提出的「前提与实际不符」经核实为正确行为）**：指令里「带 env 开关写库」的前提与实际不符——`sheets-visual-evidence.spec.ts` **没有**写库目录与 env 开关，其头部明确写着「持久证据由验收时显式复制，**避免自动改写仓库文件**」；且 `docs/.../assets/` 下**没有图纸页资产目录**。worker **没有自创路径**，图另存到计划证据目录。
- 控制器核实**属实**，且该「不自动写库」的设计**恰恰避开了 Task 6 踩过的坑**（目录页那套 env 开关会**无条件覆盖**既有验收资产 → 责任 T）。
- **裁定**：① 新建 `docs/dst-manager/specs/assets/SPEC-DM-009/production/`（SPEC-DM-009 正是图纸工作区 Spec；011/012/013 已有资产目录，009 缺位属缺口），**显式复制** 6 张 PNG；② **不**给该 spec 增加 env 开关，但在其头部注明持久证据位置与为何不加自动写库。已执行（提交 `2589173`）。

**T7-5（首轮评审 Important-1 的裁定：任务浮层断言静默缺席）**：评审者发现 Step 1 明文要求的「补任务浮层动作与状态控件断言」**未交付且未在报告中登记为缺口**（其它缺口都如实登记了）。
- **控制器补充核实（比评审者所见更严重）**：`main.spec.ts:1554` 的 `shell = page.locator(".topbar button, .tabbar button, .dock button")` **不含浮层按钮** → Task 4 的尺寸循环**从未覆盖过浮层控件**；全仓 e2e **没有任何** `.ov-*`/`.diag-*` 元素的样式或几何断言（已 grep 核实）；而 Task 4 把 `.ov-fold` 从 **40×40 改为 36×36**，该变更**只写在报告里、无任何断言钉住** → 静默回归风险。
- **裁定**：`main.spec.ts` **加入 Task 7 Files**（理由见上）；修复轮在该文件为浮层**动作控件**（`.ov-tab`/`.ov-fold`）与**状态控件**（`.ov-dot`/`.diagnostics`/`.diag-copy`/`.diag-text`/`.ov-empty`）补计算样式与几何断言，量真实 `getBoundingClientRect()`，**`.ov-fold` 必须钉到 36×36**，状态色用令牌探针而非硬编码 rgb，并做**变异自证**（尺寸/颜色/可点下限各 1 条）。
- **另**：`.cols-toggle` 的特异性相等冲突（`ColumnSettings.vue` 本体 vs `SheetToolbar.vue` 的 `:deep()`）→ 先量当前生效 padding，再删冗余侧并钉住，**不得改变当前视觉结果**。
- **已裁定接受的 Minor（不动）**：`--sheet-status-radius` 仅有取值钉（状态夹具到不了）；`.multiline-text` 的 line-clamp 未断言（该属性本次未改）。
- **如实记录**：`sheets-forms.spec.ts` 与 `sheets-visual-regressions.spec.ts` 在首轮/续轮 diff 中**零 hunk**（Files 列表是**授权而非义务**）；浮层断言落在 `main.spec.ts` 是有依据的选择，不视为这些文件的缺口。
- 修复轮已派发：`a355aafe-57ce-45e5-91e8-96483b32a356`。

**T7-6（修复轮途中发现：任务浮层诊断面板**可读性缺陷** —— 属先前既有，非本计划引入）**：修复轮 worker 在执行「凡可点元素都要过 ≥32px 下限」时发现：断言在此代码上**无法变绿**，因为浮层诊断面板是坏的。它**停下来报告而不是放宽断言或越权改代码** ✓（纪律正确）。

- **实测缺陷**：诊断列表**每行只显示一个字符**（垂直堆叠），`li` 高达 520px。
- **根因链（控制器已逐条独立复核）**：
  1. `legacy.css:24` 的 `:where(#app) aside button{display:flex;justify-content:space-between;width:100%;border:0;text-align:left}` —— 而 `TaskOverlay.vue:120` 的**根元素就是** `<aside class="task-overlay">` → 浮层内**所有** button 吃到 `width:100%`。
  2. `.diag-copy{flex-shrink:0;…}`（`:178`，**当前未声明 `width`**）→ 独占整行。
  3. `.diag-text{flex:1;min-width:0;word-break:break-word}`（`:177`）被挤成 **0 宽** → 每字一行。
- **归因（已用 git 核实）：先前既有，非本计划引入**。`aside button{…width:100%…}` 在**计划基点 `b248ff1` 的单体 `style.css` 里逐字存在**；`b0786d7` 只是把它搬进 `legacy.css`；`.diag-text`/`.diag-copy` 规则与基点**结构完全一致**（仅原始值→令牌）。Task 2/4/7 都没碰坏它。
- **裁定 A（授权在 `TaskOverlay.vue` 做最小修复）**：① `.diag-copy{width:auto}` 恢复可读性；② `.diag-copy` 与 `.ov-diagnostics summary` 加 `min-height:var(--tap-target-min)`（32px）。
  - **可行性依据（控制器核实）**：组件 scoped 样式是**无层级**（unlayered）的，而**无层级声明胜过所有 `@layer` 内的声明** → `.diag-copy[data-v-*]` 能稳定压过 legacy 层，无需 `!important`、无需动 `legacy.css`（也不在 Files 内）。
  - **为何选 A 而非 B/C**：修复对象是**不可读的面板**（现状即是缺陷），且 ≥32px 可点下限是 ARCH-DM-007 §10 的硬验收线；B 会让我们自己的断言对已知缺陷失明；C 只修一半。**“可视变化”在此是修复而非回归**，但仍需在报告中单列披露（行变高 + 文本恢复可读）。
  - **要求**：代码里写明根因注释（否则后来者会把它「修回去」）；缺陷前后对比截图存 `evidence/`（**不入 `docs/`**）。
- **附：要求一轮清点（只报不改）**：浮层根是 `<aside>`，所以 legacy 里**所有 `aside ...` 元素选择器规则**都会落到浮层内部 —— 请列出当前还有哪些此类规则命中浮层内部的哪些元素（`legacy.css:119` 附近已列出 13 条元素/伪类开头的选择器可作起点），并实测是否还有**第二个**类似实例。发现别的破损停下报告。

**T7-7（二审闭环 —— 控制器复核）**：二审 verdict = **All findings addressed, no new Critical/Important breakage** ✓。
- 上一轮 4 项（Important ×1 + Minor ×1 + 已裁定接受 ×2）全部逐条 ADDRESSED。
- **评审者做得比控制器要求的两处更硬**：① 它不只采信「删后复量一致」，而是**独立核了结构前提**——`grep -rn "ColumnSettings" src/` 证明 `.cols-toggle` **恒在工具栏 `:deep()` 作用域内**，所以删子组件侧**不可能**波及其它上下文（「零视觉变化」的**推理**成立，不只是碰巧测出来一致）；② 它核了枚举的**完整性**——`grep -nE "<input|<select|<textarea|role=\"button\"|tabindex"` 在 `TaskOverlay.vue` **零命中**，证明浮层内**不存在**未被覆盖的可点元素类型。（并合理区分了「隐藏元素应排除」与「枚举落空不得真空通过」，后者有 `visible.length > 0` 守卫。）
- **新登记责任 X（检查器缺陷，评审者发现并控制器实读源码核实）**：`unicode-structure-icon` 对注释的处理**不对称**（`check-ui-contracts.mjs:428` 对模板用 `maskHtmlComments(html)` **剥离了 HTML 注释**，而 `:429` 对 `<style>` 直接取 `style.content` **未剥离 CSS 注释**；`STRUCTURE_ICON_PATTERN` 含 `\u2190-\u21FF`（箭头区）→ **在 CSS 注释里写一个装饰性 `→` 会被判违规**，而同一字符写在模板注释或脚本注释里不会。该规则自己的注释写着「脚本与 i18n 文案里的普通标点不参与」，可见**本意就是「只算真实标记/样式，不算注释与文本」**，故这是**无意的设计缺口**（非有意的严格）。
  - **实际代价**：修复轮 worker 真的踩到了——它在 CSS 注释里写 `→`，导致 `check:ui` 与 `build` **同时 EXIT=1**，多花一个提交（`477fe31`）去修。
  - **收口方向**：对 style 块也做等价的注释剥离（或显式排除注释区），并在 Rule 文档里写明「注释不算」。**→ 已按此实现（提交 `6bf4613`，含 2 条回归测试与变异自证）；闭环记录见「依赖与提交顺序」前的责任 X 条目。**
- **两条 Minor（非阻塞，已登记不阻塞关闭）**：① `main.spec.ts` 新增的模块级 `tokenColorOf` 与既有「壳层交互态」用例内的局部 `tokenColor` **逐字重复**（6 行）——评审者**有意不按 rubric 升为 Important**，理由：它是**测试脚手架**、仅 6 行，且既有副本是**用例内局部**的，消重就得改动无关的既有用例，与「最小 diff」冲突；控制器**接受该判断**，登记为后续清理候选。② 非空转守卫用 `visible.length > 0`（枚举集合若意外缩小不会被察觉）——缓解因素是具体控件已被逐条钉住（`.ov-fold`/`.diag-text`/`.diag-copy`），风险低。
- **Out-of-scope（已并入既有责任）**：① legacy 仍对浮层内**所有** button 强制 `display:flex` + `justify-content:space-between` + `text-align:left`（`legacy.css:24`）——今日被浮层自身 flex 布局掩盖，与责任 V 现有两例同族，**一并收口**；② 各 sheets spec 里的 `shell` 定位器仍按**选择器清单**枚举（`.topbar/.tabbar/.dock`），而非按**可点性**枚举——本次新增断言已把浮层纳入，但口径本身仍是弱点，登记供 Task 12 参考。

### Task 8: 迁移设置中心

> **状态：已关闭**。Step 1–7 全部完成。实现经**两轮独立评审**闭环（首轮 Needs fixes / 0 Critical → 修复轮 → 二审 **All findings addressed**）。本任务**无用户截图人工门禁**（计划 Step 6 只要求 3 个 settings spec + build）。

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
- Modify: `web/src/components/settings/ExtensionSettingsHost.vue`（**T8-1 补列**：它有 **10** 条 `expiresWith: PLAN-DM-029 Task 8` 的例外，但原 Files 没包含它——正是**责任 L** 已登记的「例外到期任务与承载文件错位」实例之一；按责任 L 的收口方向与 Ruling 37 先例补入）
- Modify: `web/scripts/ui-contract-exceptions.json`

- [x] **Step 1（RED）**：写设置表单 label/hint/error 关联、按钮档位、焦点、长路径等宽字体与 `BooleanSwitch` 实际点击盒 `≥44×32px` 断言；确认当前点击盒或继承字体失败。
- [x] **Step 2（迁移）**：表单行、扩展卡片、生成式设置、目录设置和关于页动作改用原语；保留设置 schema、即时保存与重启提示语义。
- [x] **Step 3（开关）**：视觉轨道保持 `44×24px`，外层 label/button 扩到至少 `44×32px`；键盘 Space 切换、disabled、accessible name 和状态文案不变。
- [x] **Step 4（证据）**：保存浅/深默认、校验错误、扩展禁用、窄屏共 5 张；生产证据继续使用虚构路径，不写入真实用户目录。
- [x] **Step 5（例外清退）**：除经 T8-1(F) 保留的 **1 条** 16px 字号例外（责任 K）外，设置目录零静态例外。
  - **原措辞为计划缺陷（T8-1(H) 订正）**：「零静态例外」**不可达**——`.dlg-head h2{font-size:16px}` 是**离刻度**值（刻度为 11/12/13/14/18），而政策禁止新增字号令牌，也无值等值的可借令牌 → 必须保留。先例：Ruling 39 订正 Task 6 Step 6、T7-1(F) 订正 Task 7 Step 6。
  - **收口不变量（T8-1）**：Task 8 名下 **66** 条（Files 内 56 + 孤儿 10）→ 清退 **65** 条、保留 **1** 条 → 全表 **128 → 63**；`check:ui` 裸违规应为 **64 = 63 + 1 动态白名单**。
- [x] **Step 6（验证）**：运行 `rtk npm --prefix web run test:e2e -- settings-dialog.spec.ts settings-demo-visual-evidence.spec.ts settings-extensions-production-evidence.spec.ts`、`rtk npm --prefix web run test:unit -- src/composables/useSettings.test.ts src/composables/useExtensionSettings.test.ts` 与 `rtk npm --prefix web run build`。
- [x] **Step 7（提交）**：commit：`统一设置中心控件与开关交互`。

**T8-3（二审闭环 + Task 8 收口 —— 控制器复核）**：二审 verdict = **All findings addressed, no new Critical/Important breakage** ✓。

- 评审者**逐条核过**（且比要求更严）：① bool 关联**确实成立**而非只写在调用处（`describedBy` 在 `hasError` 时 push `errorId`、无 id 时返回 `undefined` → 不渲染空属性）；DOM 断言**两种失效都排除**（读 `[role=switch]` 自身 `tagName` 排除「属性落到包裹节点」；要求被引用 id `toHaveCount(1)` + 非空文案排除**悬空引用**）；红→绿→再红闭环。
- ② **Minor-4 的重构逐分支核过**，并指出一处最易踩空的正确处理：新代码用 **`!== undefined` 而非真值判断**，所以 `t()` 返回空串时新旧行为一致（老渲染空 span / 新 `"" !== undefined` 仍渲染）；int 分支的 `0` 与 en-dash、text 的无条件分支、bool/enum 返回 `undefined` **均语义等价**；且分支以 `control` 互斥，与老 `v-else-if` 顺序等价。
- ③ 评审者**独立读图**确认重采后的 `task8-03` 里错误文案已在可视区 ✓（不只采信声称）。
- **New Minor（非阻塞，已登记）**：`toBeInViewport()` 默认 `ratio: 0` 只要求**任意相交**（理论上一像素即算过）；若要「完全落入」应用 `{ratio: 1}`。此处经读图确认取景良好，且属同文件既有约定，**不阻塞**。
- **Out-of-scope（已登记）**：`fontFamily` 仍为令牌自指断言（报告已如实登记）；bool 行的**视觉** on/off 文案（`.f-hint`，无 id）不进 `describedBy`——状态由 `aria-checked` 承担，**无实际缺口**，但措辞易与「hint 必须关联」混淆，**宜在 Task 10 无障碍收口时一并定调**；760px 对话框 <768px 视口未验（已裁定接受，有 `max-width` 兜底）。
- **Task 8 最终账**：例外表 **128 → 63**（清退 **65**、新增 **0**）；`tokens.css` **+7** 令牌（逐字等值、无删除行、无死令牌）；新增 **1** 条例外保留（16px 字号 → 责任 K）；`check:ui` **0**；全量 `test:unit` **0（11 文件 / 104）**；3 个 settings spec **0（63 passed / 0 failed / 0 flaky）**；`test:contracts` **0（85/85）**；`build` **0**。持久证据 **5 张**in `docs/dst-manager/specs/assets/SPEC-DM-011/production/`。
- **有意视觉变化**：`.link-btn` min-height 28→32（**硬下限违规修复**）；`.cs-field input` 圆角 5→6px；`.icon-btn` 图标 14px 字形 → 16px `UiIcon`（已补 16px 值锚）。

#### Task 8 控制器裁定（T8-1，派发前下达）

控制器已做同类侦察（`controller-task-baseline.mjs 8`，脚本已参数化）——**同样的塔会重现，故提前拆掉**。侦察实测：Files 内 **56** 条（`SettingsDialog` 16、`SettingsFormRow` 11、`ExtensionCard` 7、`GeneratedExtensionSettingsForm` 6、`SheetCatalogSettingsPanel` 6、`BooleanSwitch` 4、`AboutSection` 3、`ExtensionsSection` 3；规则：`raw-visual-value` 55 + `unicode-structure-icon` 1）+ **孤儿 10** 条；55 条裸值去重后 **14 个值**。

**(A) 开放 `tokens.css`：仅追加以下 7 个组件层令牌（取值逐字等值、零视觉变化、按角色命名）**：

| 令牌 | 值 | 消费处 |
|---|---|---|
| `--settings-license-max-height` | `200px` | `AboutSection.vue` `.license max-height` |
| `--settings-dialog-width` | `760px` | `SettingsDialog.vue` `.settings-dialog width` |
| `--settings-nav-width` | `150px` | `SettingsDialog.vue` `.sections width` |
| `--settings-switch-width` | `44px` | `BooleanSwitch.vue` `.switch width`（Step 3 明示保持 44×24） |
| `--settings-switch-height` | `24px` | `BooleanSwitch.vue` `.switch height` |
| `--settings-switch-thumb-size` | `18px` | `BooleanSwitch.vue` `.switch-thumb width/height` |
| `--settings-foot-min-height` | `24px` | `.ext-config` / `.ef-foot` / `.f-foot` 三处同语义 `min-height` |

**(B) 禁止借用（值等值但语义不符 —— 语义说谎，按 Ruling 33/35/39 驳回）**：`24px` → `--space-5`（**间距令牌，不是高度**）；`18px` → `--badge-size` / `--font-size-18` / `--modal-title-font-size`（徽标/字号 ≠ 开关滑块）；`44px` → `--definition-row-height` / `--sheet-table-row-height`（他域行高）；`16px` → `--space-4` / `--icon-size-md`（间距/图标 ≠ 字号）。

**(C) 允许借用**：`12px` → `--font-caption`；`13px` → `--font-label`；`14px` → `--button-font-size`/`--input-font-size`（**不得用 primitive `--font-size-14`**，同 Ruling 38）；`32px` → `--tap-target-min`（`.icon-btn min-width/min-height` 本就是可点目标 ✓）；`34px` → `--control-height-compact`。

**(D) ★ 34px 表单输入的档位问题 → 先用 compact 令牌，档位本身不单方面改**：`SettingsFormRow`/`GeneratedExtensionSettingsForm` 的 `input[type=text|number] height:34px` 与 `.browse-btn height:34px`。
- 34px 同名 `--control-height-compact`（令牌名中性：「紧凑控件高度」，不是「工具栏高度」）✓。
- **但** ARCH-DM-007 §4.1 的档位表把**表单输入 = 38px**（`--control-height-form`）、34px 归「紧凑工具栏」；且**其它页面的表单输入已是 38px**（Task 6/Task 7 均如此）→ 存在**跨页不一致**。
- 34px **不低于** 32px 下限，因此**不是硬违规，而是档位选择问题** → 与**责任 W**（工具栏密度）同族，**不属页面迁移任务单方面决定** → **保持 34px + 用 compact 令牌**，并把该不一致**并入责任 W** 交 Task 12 / Spec 归属方以档位表裁决。
- **明令**：**不得**为「统一」把 34px 单方面改成 38px（那是替设计系统做档位决定）；也**不得**改成其它值。

**(E) 硬违规必须修**：`SettingsFormRow.vue` `.link-btn min-height:28px` —— **低于 32px 最小可点下限**（ARCH-DM-007 §10 硬验收线）→ 提到 `--tap-target-min`(32px)，并作为**有意视觉变化披露**。先例：T6-8 的 30→32、Task 6 的 30→36。

**(F) 字号 `16px`（`.dlg-head h2`）→ 保留为显式例外 + 责任 K**：字号刻度为 11/12/13/14/18，16px **离刻度**；按 T6-3 / Ruling 38「不新增字号令牌」政策，且**无值等值的可借令牌** → 保留例外，`expiresWith` = 责任 K。**不得**改成 18/14（那是视觉变化）。

**(G) 圆角 `5px`（`.cs-field input`）→ `--radius-sm`(6px)**：**1px 偏差、作为有意视觉变化披露**。先例：T6-7 与 T7-1(C)；仓库半径档为 6/8/12/9999，无 5px。

**(H) Step 5 措辞已订正**（见上）：必须保留 1 条 16px 字号例外；不变量 **128 → 63**。

**(I) Step 3 的三层尺寸别混淆**：视觉**轨道 44×24**（Step 3 明示保持）、**滑块 18px**、**外层可点盒 ≥44×32**（Step 1/Step 3）。断言要量**外层 label/button 的点击盒**，不是轨道本身。

**(J) 证据纪律**：Step 4 的 5 张（保存浅/深默认、校验错误、扩展禁用、窄屏）+ Step 6 的 3 个 settings spec。**生产证据必须用虚构路径、不得写真实用户目录**（Step 4 明示）。沿用 `settings-extensions-production-evidence.spec.ts` 的**既有落盘约定**——**不要自创路径、不要给 spec 加 env 开关**（T7-4 先例：目录页那套 env 开关会无差别覆盖他 Spec 资产，已登记责任 T）；若确需新建资产目录 → **停下报告**。若沿用机制仍连带改写了别的 Spec 的 PNG → `git checkout` 还原并在报告里说明。

**T8-2（首轮评审结果与修复轮裁定 —— 控制器复核）**：首轮评审 **Needs fixes / 0 Critical**（1 Important + 5 Minor）。**迁移本体与 T8-1 (A)–(J) 逐条经复核合规**：7 个令牌逐字等值无删除行、零禁用借用、允许借用逐条命中、**34px 未被越权改成 38px**、`.link-btn` 28→32 已修、16px 逐字保留且理由与代码一致、5px→`--radius-sm`、开关三层尺寸**分开量**（外层 `≥44×32` / 轨道 44×24 / 滑块 18）、`ExtensionSettingsHost.vue`（T8-1 补列）**确已清退**、两个 spec 均为**纯追加**（唯一触碰的既有行是 import）。

- **评审者额外肯定（值得记）**：`BooleanSwitch.vue` 的**两层拆分是正确解**——外层 `button` 承担可点盒、视觉轨道移入内部元素，同时满足「可点盒 ≥44×32」与「轨道保持 44×24」两条看似冲突的约束（注释写清了取舍）；且 `aria-checked`/`:id`/`data-key`/Space/状态文案的语义路径与 `prefers-reduced-motion` 均未漏。
- **[Important] 已裁定修复 —— 而且它上轮给出的「阻断理由」经核实是错的**：worker 报告 §7.3 称「bool 行加错误关联需给 `BooleanSwitch` 加可选 prop，而派发明令禁改公开 props」→ **控制器实读源码核实该理由不成立**：`BooleanSwitch.vue` 模板是**单根** `<button role="switch">`（`:18-24`）且**无 `inheritAttrs: false`** → Vue 默认透传会把 `:aria-describedby` **直接落到根 button**，**无需任何 prop**，改动点是 `SettingsFormRow.vue` 上的**一个属性**。
  - **影响如实（不夸大）**：`:116` 保留 `role="alert"`，错误**出现时**仍会被播报；缺的是**持久关联**（回头聚焦不再复述）+ 一个**悬空 id**。
  - **为何算 Important**：它是 Step 1 明列交付物（label/hint/error 关联）在**一种控件类型**上的缺失，且**理由错误**——若不纠正，会被当作「受约束、不可做」**继承给后续任务**，而它其实是一行可完成项。
- **★ 流程教训（与控制器自己的三次教训同根）**：本次是 worker **未验证前提就宣告「不可做」**；而控制器先前三次是**未验证前提就下裁定**（Ruling 36 凭目录名推断归属、Ruling 39 未实读检查器源码、Ruling 44 未检索既有先例）。**共同根因：把一个未经验证的前提当成约束。** 纪律：**在宣告「不可做/需改公开接口/无先例」之前，必须实读被引用的源码并写出所查行号。**
- **Minor 处置**：2（字体断言**令牌自指**，需补绝对值锚——责任 S 的同一教训）；3（`.icon-btn` 图标 14px 字形→16px `UiIcon`，**唯一未被逐值钉住的视觉变化**）；4（`hasHint` 与模板 v-if 链是同一逻辑的**两处手写副本**，分叉会导致 hint 不播报或指向不存在的 id → 改为单一 computed）；5（校验错误证据图**未把错误文案纳入可视区**，沿用同文件已有的 `toBeInViewport()` 约定）→ **均要求修复**。6（760px 对话框在更窄视口下的布局）→ **裁定接受**（有 `max-width:calc(100vw - 32px)` 兜底，风险低）。
- 修复轮已派发：`fa9d8277-129a-4fcc-b023-d2017476e05a`。

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
- [ ] **Step 4（legacy 清理）**：逐条证明消费方已迁移后删除 `legacy.css` 对应规则；最终 `legacy.css` 只允许仍有永久 Spec 例外的根类规则，无条目时保留空 layer 文件和说明。`.summary` 等**已无 `class="summary"` 渲染点的死规则**随本次清理整体删除。注意：`parseRules` 会把紧邻规则的前置注释并入选择器，**注释文本因此进入例外指纹**（全表 **23 条**受影响，涉及 9 个文件、18 段不同注释文本），因此删除或改写这些注释必须与 `ui-contract-exceptions.json` 的更新落在同一次改动里，否则会立即变成陈旧例外。
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
- [ ] **Step 3（RED：模态）**：为四个模态补初始焦点、Tab 圈闭、Escape、关闭归还、嵌套时顶层唯一响应测试（四个模态 = `ConfirmModal.vue`/`UnsavedInputDialog.vue`/`PropertyValueCompareDialog.vue`/`SettingsDialog.vue`，均在本任务 Files 内；**不含** `TaskOverlay.vue`——它的焦点副本已由 Task 4 迁完，见 Ruling 28）。
- [ ] **Step 4（模态复用）**：消除各模态重复焦点代码，统一使用 `dialogFocus.ts`；由业务组件决定 Escape 是否允许关闭（`dialogFocus.ts` 另可选传 `returnFocus` 解析器，用于「关闭回焦触发按钮之外」的落点，见 Task 4/R2-1）。
- [ ] **Step 5（全仓语义扫描）**：运行 `rtk npm --prefix web run check:ui`，并由 `explicit-button-type`、`visible-input-label`、`icon-button-name` 三条规则完成全仓扫描；所有真按钮显式 `button` 或 `submit`，所有搜索输入具有可见弱化 label，所有图标按钮有可读名称。同时确认 `<aside>` 内不再用 `[hidden]` 作为隐藏手段：`legacy.css:24` 的 `:where(#app) aside button{display:flex}` 会压过 UA 的 `[hidden]{display:none}`，浮层靠自己的 `.task-overlay [hidden]{display:none!important}` 兜底而散落元素没有（控制器实测证据见 Task 4 报告；已登记 Task 12 收口责任 M）。
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

> **收口责任 A（字体真实加载当前未被自动化覆盖）**：Task 2 的三条 e2e 用例只断言 **CSSOM 声明层**
> （`@font-face` 规则文本、`getComputedStyle()` 字体栈、`unicode-range` 区间语义），**不验证两套 WOFF2
> 在运行时被真实请求**（仓库内 `document.fonts` 零命中，也无任何网络请求断言）。Task 12 的验收证据必须
> 包含这一项：运行时确认两套 WOFF2 被真实请求且响应来自本地 `/assets/…`、全程无远程字体访问
> （推荐在 `main.spec.ts` 的 Task 2 一节补 `document.fonts.ready` + 请求监听断言；若选该方式，需把
> `web/tests/e2e/main.spec.ts` 一并加入本任务 Files；若改为人工核验，必须在
> `.planning/memos/dst-manager/assets/PLAN-DM-029/README.md` 留下可核查记录）。在该证据到位前，
> 不得在任何文档里声称「字体产物真的被加载」已覆盖。
>
> **收口责任 B（字体子集化命令）**：两套 WOFF2 的原始 `pyftsubset` 命令行未被记录，且在本机无法逐字复原
> （Plex 复原物 11220 B ≠ 已入库 12488 B，Inter 上游发行包不可达），详见
> `web/src/assets/fonts/README.md` 与 Task 2 报告 4.5 节。如需命令级可复现，必须在可访问上游的环境重做
> 子集化并同步替换产物（含体积、字符集、浏览器加载三类复核），并把新命令写入该 README；
> **不得用推测的命令文本或其他环境下的复原物替换已入库资产**。
>
> **收口责任 C（例外表跟踪项，Task 2 本轮不动数据）**：
> ① 例外条目的 `rule` 字段已是冗余项——安全语义完全由 `fingerprint` 首段承载，`rule` 只参与一致性
> 卫生检查。它是**临时防御**：单一事实源应在指纹首段，两处事实源必留漂移面。下次重新生成例外表时
> 删除该字段、改为从指纹派生，并同步调整 `check-ui-contracts.mjs` 的那处一致性断言（当前 382 条数据
> 与一处消息字符串被等值断言绑在一起）。
> ② 例外表可自掩蔽自身的配置错误（低危）：配置类违规（`invalid-exception-entry`、`stale-exception`）的
> `file` 恒为 `scripts/ui-contract-exceptions.json`，其规则 id 不在 `NON_EXEMPTIBLE_RULES` 中，理论上可
> 再登一条条目把「关于例外文件本身的配置错误」吃掉（当前此类条目 0 条）。加固方向：拒绝
> `entry.file` 等于例外文件自身的登记。
> ③ 注释–指纹耦合：全表 23 条指纹内嵌了前置注释（9 个文件、18 段注释文本），改动这些注释会同时改动
> 指纹；处置义务已写在 Task 9 Step 4。
>
> **收口责任 E（令牌分层未落实到位，Task 3 二轮评审 G1）**：Task 3 新增原语中尺寸、字号、字体族
> 消费语义/组件令牌，但**颜色、间距、圆角、图标尺寸仍是跨层直取原始令牌**（`--color-*`/`--space-*`/
> `--radius-*`/`--icon-size-*`）——ARCH-DM-007 §3 要求「组件只能消费已声明的语义令牌或组件令牌」，
> 而仓库当前没有颜色/间距/圆角/图标尺寸这一层的语义令牌。按既有约定（口径：
> `grep -rhoE 'var\(--(color|space|radius|icon-size)-' web/src --include=*.vue | wc -l` → 当前 **1104 处**，
> 同一命令以 `grep -rlE` 取文件数 → **44 个 `.vue` 文件**；Task 3 落地前 `8985a64` 为 1049 处 / 38 个文件，
> 差集 55 处即本轮 6 个新原语自身的直取。三轮评审 H1 发现原文「40 个文件、1079 处」九种口径均不可复现，
> 已改为上式可跑口径）先保持一致，不得为本轮新造色板；待语义层补齐后统一收口，并同时把这条
> 实际约束写回 ARCH-DM-007 §3 或明确豁免口径。
>
> **收口责任 F（`fieldset[disabled]` 的禁用继承未建模，Task 3 三轮评审 H2）**：`dialogFocus.ts` 的
> 禁用守卫按元素自身的 `[disabled]` 属性判定，不建模 `fieldset` 的禁用继承。三点必须一并处理：
> ① 缺口只能从候选集合的 `[tabindex]` 分支漏入（`button`/`input` 分支由真实浏览器的 `:disabled`
> 继承正确挡住），且**本仓库当前不可达**——唯一的 `<fieldset disabled>`
> （`SheetCatalogSettingsPanel.vue:84-85` 只读态）内没有非负 `tabindex`（带 `tabindex` 的是 `:118` 的 `-1`，
> 两个按钮 `:122`/`:123` 不带）；② 精确判定**不能**用朴素的 `closest("fieldset[disabled]")`——按 HTML
> 规范，禁用 `fieldset` 的**第一个 `<legend>` 元素子节点内**的后代控件仍然可用，必须按层跳过
> 「元素落在该 fieldset 第一个 `legend` 子树内」的情形（规范例外已核实成立）；③ 现场参照：
> `SheetCatalogSettingsPanel.vue:84`（settings 只读态）与 `SettingsDialog.vue:123`（它自带的选择器里
> `select`/`textarea` 分支**没有**禁用过滤、也不建模 `fieldset` 继承 → 只读态下端点会指向真实浏览器
> 不可聚焦的控件，同属禁用态欠虑，可与 `dialogFocus.ts` 一并评估是否共用同一判定）。
>
> **收口责任 G（存活变异补测：Task 3 三轮评审 H5 用「哪些变异能存活」问出的未覆盖分支）**：把
> `dialogFocus.ts` 的实现改坏后测试仍全绿的分支共 4 处，其中 2 处属真实回归面，必须补测；补测需要
> `web/src/components/ui/dialogFocus.test.ts`（当前不在任何后续任务的 Files 里，届时需把它补进
> 对应任务的 Files 列表）：
> ① `shouldReturnFocus` 的「关闭前焦点已被移到容器外 → **不抢**焦点」分支与 `active === body` 分支
> **完全无用例**（最该补：用户可见症状是「关掉对话框后焦点被拽回来」）；
> ② 无名 `radio` 应**各自独立停靠**——现有 4 条单选组用例全部带 `name="group"`，把 `isNamedRadio`
> 的 `name !== ""` 判定删掉仍全绿，需补一条无 `name` 的 `<input type="radio">` 用例；
> ③ 不同 `form` 下的**同名** `radio` 分组——把 `radioStopPoints` 的 `element.form` 维度去掉仍全绿，
> 需补一条「两个各带独立 `<form>` 的同名 radio 组」用例；
> ④ Shift+Tab 起点在**容器自身**时的回绕分支——唯一「容器获得焦点」的用例走的是「无可聚焦元素
> 早退」那条路，该分支未被真正执行。
> 另有 2 处**构造上不可杀/无覆盖**，登记为已知未覆盖、不得计入已覆盖边界：
> `DEFAULT_FOCUSABLE_SELECTOR` 里新增的 `:not([disabled])` 不可达（`isTabStop` 已先排除同一元素，
> 属冗余防御）；`visibility` 的 `collapse` 取值没有任何用例。
>
> **收口责任 D（`UiButton.label`/`UiIconButton` 尚未写进 ARCH-DM-007 §5，Task 3 首轮评审 F4）**：
> ARCH-DM-007 §5 未记录两点新增约束——① 纯图标按钮用 `UiIconButton`（`label` 必填）而非
> `UiButton` + `label`；② `UiButton` 带可见文案时若同时传 `label`，两者文字必须一致（WCAG 2.5.3）。
> 这两条现在只存在于源码注释、测试与 Task 4 Step 2；需在 Task 12 的文档收口轮把 §5 补齐（含
> `UiButton.label` 只用于「插槽无可读文案」的边界），并同时校正 §6 的图标许可描述（Lucide 是 **ISC**，
> 不是 MIT；几何数据为按名称转写、未与上游版本同步，逐图标比对结论见 Task 3 报告）。

> **收口责任 H（检查器对 `calc/min/max/clamp/env` 无参数检查；Task 4 Ruling 25 实测）**：
> `web/scripts/ui-contracts/visual-values.mjs:37` 的 `COMPUTED_VALUE_PATTERN` 只要值里出现 `var(`/`calc(`/`min(`/
> `max(`/`clamp(`/`env(` 就在 `:66` 直接放行，**不检查参数是否含裸值**。因此 `width:clamp(32px,32px,32px)` 这类
> 「用函数包裹常量」的写法能绕过 `raw-visual-value`。收口方向：对上述函数**递归检查参数**，只含常量
> （无 `var(`/`%`/视口单位/`env(`）时仍判裸值。Task 4 未使用该手法，但检查器漏洞必须堵。

> **收口责任 I（ARCH-DM-007 §4.1/§5 与新增令牌/约束对齐）**：Task 4 在组件层新增壳层、浮层、提示宿主的
> 结构尺寸令牌（`--shell-bar-height`、`--workspace-name-max-width(-narrow)`、`--folder-action-min-width`、
> `--badge-size`、`--status-dot-size`、`--overlay-pop-width/-max-height`、`--dock-note-max-width`、
> `--task-rail-width`、`--task-rail-action-size`、`--task-drawer-max-width`、`--toast-max-width`），§4.1 对该层的
> 枚举不再完整；`tokens.css:4/8` 又把原始层描述为「十六进制颜色与原始档位的唯一合法定义处」，与
> 「组件层写入字面 px 常量」存在措辞张力。需一并收窄措辞并把组件层枚举补全。**Task 5 沿用同一路径再新增 6 个
> 组件层结构令牌**（`--panel-head-min-height`、`--panel-search-width`、`--definition-row-height`、
> `--compare-card-max-width`、`--compare-item-max-height`、`--expand-editor-min-height`，Ruling 31）——
> 其中后三项目前可能只被属性页消费，属**单点组件令牌**，收口时需复核是否应合并或下沉，不能只补枚举了事。

> **收口责任 J（`0×0` 候选仍算停靠点）**：`getClientRects()`（及迁移后的 `isHidden`）都不排除零尺寸元素，
> `main.spec.ts` 的浮层焦点用例把这一行为冻结为特性化断言。若终局判定「零尺寸元素不应成为 Tab 端点」，
> 需在 `dialogFocus.ts` 与断言两侧同步改并说明理由。

> **收口责任 K（语义层缺「非控件用途的独立 14px 档位」）**：语义层的字号只有 `--font-body`（`font` 简写形态，
> 仅供根元素）、`--font-label`(13)、`--font-table`(13)、`--font-caption`(12)，没有独立 14px；因此顶栏品牌名
> `.brand` 与提示标题 `.toast-main strong` 只能**借用组件层** `--button-font-size`。需在 Task 12 决策：补一个
> 语义令牌（如 `--font-title`）还是明文允许这种借用，避免每处靠注释解释。

> **收口责任 L（例外 `expiresWith` 与任务 Files 的错位）**：复审机械统计发现多条债务的「到期任务」改不到
> 承载它的文件：Task 10 名下 34 条分布在 7 个文件且**无一在其 Files 内**（`DraftActionsPanel.vue` 7、
> `JobStatusPanel.vue` 1、`RepairStatusPanel.vue` 3、`RevisionHistoryPanel.vue` 3、`ToastHost.vue` 6、
> `RevisionsView.vue` 2、`WelcomeView.vue` 12）；同类的还有 Task 7 的 `SheetTree.vue`(9，只在 Task 10 Files)、
> Task 8 的 `ExtensionSettingsHost.vue`(10)、Task 6 的 `CompatibilitySummary.vue`(1)、Task 9 的 `primitives.css`(2)。
> 检查器不校验这件事（只要求字段存在）。收口方向：在终局审计前把这些文件补进对应任务的 Files，或统一
> 改写 `expiresWith`；否则 Task 12 会以「债务无法清零」的形式暴露。

> **收口责任 M（`<aside>` 内 `[hidden]` 不是可靠的隐藏手段；Task 4 控制器实测）**：`legacy.css:24` 的
> `:where(#app) aside button{display:flex}`（命名层作者规则）压过 UA 的 `[hidden]{display:none}`：在真实浮层里
> `createElement` 造的 `<button hidden>` 仍 `display:flex`（高 21px、有 client rect、`focus()` 成功），
> 证据 `evidence/controller-task-4-probe-hidden.json`。浮层自己的元素之所以正常，是因为组件 scoped 规则里有
> `.task-overlay [hidden]{display:none!important}` 兜底（scoped 选择器带 `[data-v-*]`，裸元素命中不了）。
> 结论：能否真隐藏取决于元素是否落在组件 scoped 兜底内；`dialogFocus.ts` 只能按属性判定，所以它在这类元素上
> 「判为隐藏但浏览器仍可聚焦」的偏差是有意的。收口方向：审计 `<aside>` 内是否还有依赖 `[hidden]` 做视觉隐藏的元素，
> 必要时改用 `v-if` 或 `display:none` 的样式钩子。
>
> **收口责任 N（`line-height` 没有令牌层；Task 5 修复轮实测）**：语义层只有 `--line-height-body:1.5`，且其用途被限定在 `--font-body` 简写（根元素专用）。界面其余行高散落为裸无单位倍数：`primitives.css:29` 的 `line-height:1.6`，以及 `PropertyValueCompareDialog.vue:66`、`PropertyValuePanel.vue:314`、`PropertyValuePanel.vue:330` 三处 `line-height:1.7`。静态检查器不把无单位倍数计为 `raw-visual-value`，所以这些值既无令牌也不进例外表，属「检查器盲区内的既有债务」。Task 5 只能锁定既有计算值（Important-2），不能新增字号/行高令牌。收口方向：评估是否补一档 `--line-height-*` 语义令牌并让检查器覆盖无单位行高；在此之前不得声称行高已令牌化。
>
> **收口责任 O（SPEC-DM-006 §232 的「文本域」当前无原语；Task 5 修复轮实测）**：`web/src/components/ui/` 没有 textarea 原语（`dialogFocus.ts:31` 只在焦点选择器里认 `textarea`），属性页的展开编辑用原生 textarea。因此 §232 对文本域的三态要求既无原语承载、也无页面 hover 规则可迁移（全仓 `textarea:hover` 零命中，故本轮无回归）。收口方向：要么新增 textarea 原语并补齐状态，要么在 Spec 里明确文本域沿用原生并给出可核验的状态声明。
>
> **收口责任 P（视觉证据注释与实现不符；Task 5 第二轮修复已订正，保留记录）**：`properties-visual-evidence.spec.ts` 头部注释写「附件为 `prod-{状态}-{宽}x{高}-{主题}.png`」，而 `attachScreenshot` 实际写 `${state}-${宽}x${高}-${主题}.png`（**无 `prod-` 前缀**），调用点传入 `default`/`narrow-single-column`/`def-table-overflow`；同文件新增注释又声称「height/padding/radius 已由上方令牌断言覆盖」，而全文件 `padding`/`radius` 断言各仅 1 条且都指向定义面板查询区，**不覆盖**折叠标题、导入导出与两个按钮。两者均属「注释声称强于实际」的文档债务，与 Ruling 33 追究的失实注释同类，已在 Step G1 一并订正。保留本条以说明「注释准确性」是本计划的持续关注点。
>
> **收口责任 Q（输入 hover 的表现形式与 SPEC-DM-006 §5.1 通用规则不一致；Task 5 第二轮评审发现）**：`SPEC-DM-006:169` 的交互态映射规则写「`hover` 在 surface/muted 上升亮度约 +4%」，而本轮制度化到共享原语的输入 hover 是**描边变色** `border-color:var(--color-accent)`（`:232` 未规定输入 hover 的表现形式）。该形式是仓库既有事实标准（迁移前已逐字相同地出现在 `PropertyValuePanel.vue` 与 `SheetPropertyEditor.vue` 两处），且现已提升为**原语契约**，会被 Task 6–9 逐页沿用。收口方向：请 Spec 归属方确认「描边变色」是被接受的输入 hover 表现，或在文栅上对齐 +4% 规则；**本轮不动表现形式**（那比定序修正的可见变化大得多，超出迁移任务范围），但在定调前不得声称输入 hover 已符合 §5.1。

> **收口责任 R（密集表格行内动作按钮无法满足 SPEC-DM-010「图标按钮 ≥36×36」；Task 6 派发前侦察发现）**：`ColumnEditor.vue` 的 `↑ / ↓ / ✕` 行内动作按钮受 `ColumnEditor.vue:8` 记录的 **A1（用户已接受差异）** 约束：保留字符图标导致操作列轨道由冻结 Demo 的 188px 收窄为 **112px**。轨道预算实测：3×30+2×4=98；提到 `--tap-target-min`(32px) 后 3×32+8=104 ≤112；但 **36×36 需 116 >112**，把 gap 压到 2px 才恰好 112（零余量）——**即 SPEC-DM-010 的图标按钮下限在不推翻 A1 的前提下不可达**。本轮取 32×32 折中（满足可点目标 ≥32px）。收口方向：请 Spec 归属方在「调整轨道宽（推翻 A1）」与「为密集表格行内按钮豁免 36px 下限」之间裁定，并把该豁免写回 SPEC-DM-010。**扩展（T6-13 评审建议纳入）**：同一行 `.row-actions button` 的**圆角**（现为 `--radius-sm`(6px)，属 T6-8 保值）也一并交 Spec 归属方裁定——因为同一行的两个字段已因原语约束成为 `--radius-md`(8px)，而 T6-12 自立的「同行相邻控件圆角必须一致」原则与该行的保值要求冲突（保值 vs 统一）。本任务**不再单方面微调**这一行：尺寸（36px 不可达）与圆角（6 vs 8）同属「密集表格行内动作按钮」这一个待裁问题。
>
> **→ T6-16 已裁定（Spec 归属方 = 用户，2026-09-15）：选「豁免 36px 下限，保持 32×32」**。此段保留作历史依据。
>
> **→ T7-2 扩展（2026-09-15）**：同一类问题又出现第二个实例——**`SheetToolbar.vue` 的条件标签清除按钮（`✕`）可点面积约 12×12px**，低于 ≥32px 最小可点下限，但提到 32px 会撑破 12px 高的标签胶囊（撑破风险已由 worker 的判据④实证）。两例同属「**密集行内控件的可点面积下限**」，**合并成一份 SPEC 豁免申请**交 Spec 归属方，不分别碎片化裁定。

> **收口责任 S（缺「迁移不得改变既有计算值」的机械检查；Task 6 续轮 RED 暴露）**：`check:ui` 只验**规则合规性**（裸值是否使用令牌、例外是否陈旧），**无法**发现「迁移把某个计算值改掉了」——例如把 `min-height:34px` 换成 `UiButton` 默认 `36px` 后，两边都“合规”，检查器全绿。Task 6 续轮写断言后跑 RED、捕获 **5 条全红**，才发现承接的迁移把 6 个动作按钮高度从 34/34/30/30/30/32 统一成了 36px。**教训：规则合规 ≠ 值保持**；控制器当时只跑 `check:ui` 就判定「0 真实违规」是**必要但不充分**的验证。收口方向：考虑为迁移类任务提供「迁移前后计算值快照对比」的机械手段（或在计划中强制「每个被迁移规则至少一条计算样式断言」），使值变化只能是有意为之且必须披露。

> **收口责任 T（SPEC-DM-012 生产证据 `g8-*.png` 已陈旧，且该证据不可逐字节复现；Task 6 收口发现）**：Task 6 的刻意视觉变化（Ruling 41 的 36px 归一 + T6-5 的可见 label）会影响图纸目录页，而 SPEC-DM-012 与冻结 Demo 的比对依赖 `docs/dst-manager/specs/assets/SPEC-DM-012/production/g8-*.png`。实测两件事：① 这些图**对采集环境敏感**——同一 spec 连跑两次，新采集的 5 张 t6 PNG 的 md5 **全不同**（本机无 PNG 解码器，无法逐像素归因）；② 只要带 `DST_MANAGER_WRITE_G8_EVIDENCE=1` 跑一次目录页证据 spec，就会**无条件覆盖**这 6 张。收口方向：视觉变更全部落定后（Task 12）**重新生成** SPEC-DM-012 生产证据，并在 Spec 侧写明该目录的**再生成时机**与「带该环境变量跑 e2e 会弄脏工作区」的提示，避免下一位开发者把噪声 diff 误提交。

> **收口责任 U（`visible-input-label` 已看不见 `UiInput`；Task 6 评审轮发现）**：该规则从**模板源码**解析 `<input>` 标签（`check-ui-contracts.mjs:406-419`，遍历全部 `<input>` 且只跳过 `type="hidden"`）。Task 6 把列名输入与字段搜索迁到 `<UiInput>` 后，规则**根本看不到它们**，因而「必须有可见 label」这条保证**不再由检查器提供**，而只靠 `sheet-catalog.spec.ts` 里的断言守着。本轮结论正确（label 确实存在且被测试钉住），但 `UiInput` 的 `label` 是**可选**属性（`FormField` 是另一种提供方式），下一个消费者完全可能不传 `label` 而检查器**不会报**。收口方向：让 `check-ui-contracts.mjs` 能识别 `UiInput`/`FormField`（要么解析组件用法，要么要求必须经 `FormField`），或至少在 Rule 文档里声明「组件化输入不在本规则覆盖范围内、由 e2e 兜底」。

> **收口责任 V**（分层级联静默覆写 + 门禁只验规则不验渲染）正文见 **T6-15 之后的 blockquote**（含「跟现有门禁只能验规则、不能验渲染」的 S/U/V 模式归并，由 Task 12 统一裁决）。

> **收口责任 W（跨页工具栏密度不一致；Task 7 复核发现）**：Task 6 把**图纸目录页**工具栏按钮归一为 **36px（默认档）**，而 Task 7 把**图纸页**工具栏 8 枚动作按钮保留为 **34px（`UiButton size="compact"`）** → 两页栏密度不一致。（注：`.dock-row`/`.template-row`/`.sheet-toolbar .operations` 语义上都是「紧凑工具栏」。）
>
> **✔ 控制器自我修正（记录在案，不掩饰）**：Task 6 的 Ruling 41 驳回 34px 时用过一条论据「全仓 `size="compact"` 消費数 = 0，选它会让你成为唯一 compact 页」。**该论据现在已失效**——Task 7 引入了 8+ 个 compact 消费者；而且 ARCH-DM-007 §4.1 档位表**本身就声明了**「紧凑工具栏 = `--control-height-compact` = 34px」，所以「无现有消费者」不应被当作反对一个**已声明档位**的理由（当时真正站得住的论据只有「同行 34/36 不一致」）。
>
> **收口方向**：Task 12 / Spec 归属方以 **ARCH-DM-007 §4.1 档位表**为准裁决「工具栏到底用 34 还是 36」；若结论是 34px，则 Task 6 已关闭的目录页工具栏需另开一次**带用户确认**的变更（不能静默改已验收页面）；若结论是 36px，则 Task 7 的保留选择需改并同样披露。**两类情形都不属页面迁移任务自行决定的范围。
>
> **→ T7-6 加入第二个实例（2026-09-15）**：任务浮层的诊断面板被 **legacy 的 `:where(#app) aside button{width:100%;…}` 静默改写**——因为 `TaskOverlay.vue` 的根元素**就是 `<aside>`**，该元素选择器因此命中浮层内**所有** button，导致 `.diag-text` 被 `.diag-copy`（吃到 `width:100%` 且 `flex-shrink:0`）挤成 **0 宽**、每字一行、不可读。
>
> **两个实例的共同模式（这才是要收口的东西）**：legacy 层的**元素/通用选择器**（`.danger`、`aside button`）会静默改写它不该管的组件内部样式，而**现有任何门禁都发现不了**（`check:ui` 只看裸值是否令牌化，看不到渲染结果）。已要求修复轮做一轮**可枚举的清点**（列出所有命中浮层内部的 legacy `aside ...` 规则），而不是抽样印象；清点结果归入本责任。
>
> **收口方向（补充）**：除「以档位表裁决工具栏密度」外，还需把「**primitives/组件内部不得被 legacy 层的元素/通用选择器接管**」变成可机械检查的规则（当前扫描已得「primitives 层与 legacy 层**零**同名 class」，基底干净，可在此基础上加元素选择器维度）。

> **收口责任 X（`unicode-structure-icon` 对注释处理不对称 → 假阳性）—— 已修复（2026-09-15，`6bf4613`）**
> 问题：`check-ui-contracts.mjs` 对模板区用 `maskHtmlComments` 剥了 HTML 注释，但对 `<style>` 区直接取 `style.content` **未剥 CSS 注释** → 在 CSS 注释里写个装饰性 `→` 会被判违规（同字符写在模板/脚本注释里则不会），与规则自己「只算真实标记与样式」的本意相悖。
> **已修**：新增 `maskCssComments`（与 `maskHtmlComments` 同样**保持长度**，以免扫描偏移错位），样式区改用遮蔽后的文本；并补 **2 条回归测试**（假阳性不报 + 遮蔽不得吞掉样式区**真实**图标）。
> **验证**：修复前用临时探针复现了真违规（`EXIT=1` 并报出 `注释里的箭头`）；修复后 `check:ui` **EXIT 0**、例外表仍 **128**（无条目变陈旧）；`test:contracts` **85/85**（原 83 + 新增 2）；**变异自证**——撤销修复后 2 条新测试均**红**，还原后均绿。
> → 本责任**已闭环**，不遗入 Task 12。**

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
| Task 1（复审修复） | 同上四条；另做「临时移除 `parseRules` 的 `@` 跳过」红/绿对照实验 | **62 passed / 0 failed**（连续两次运行）；`check:ui` 退出 0；`build` 退出 0；`unit` 48 passed；基线仍 422 条、不变量仍 423 = 422 + 1；前奏测试在该注入下确实变红（3 条 `global-selector-in-component` 误报），还原后复跑为绿 | 提交 `补齐 UI 契约门禁文档与回归测试细节`；证据见同报告第 9 节 |
| Task 2 | `rtk npm --prefix web run test:contracts`、`check:ui`、`build`、`test:unit`、`test:e2e -- main.spec.ts` | **80 passed / 0 failed**（新增 14 条资产/入口规则用例 + 4 条 CLI 级变异；覆盖面守卫 15 类/16 条注入/14 条规则）；`check:ui` 退出 0；`build` 退出 0（`dist` 产出两个本地 WOFF2，`url()` 为 `/assets/...`）；`unit` 48 passed；`e2e` **78 passed / 0 failed**；三项针对性变异（预算 `>` 改 `>=`、相对路径忽略样式表目录、移除 `NON_EXEMPTIBLE_RULES` 判定）均使对应用例转红，还原后复跑全绿；例外 422 → 382（Task 2 名下 53 条结清：40 清退 + 13 重定向 Task 9），不变量 383 = 382 + 1；字体 56928 + 12488 = 69416 ≤ 256000，实测无 CJK | 提交 `统一前端字体令牌与样式分层`；报告与证据见 `.superpowers/sdd/PLAN-DM-029-frontend-ui-foundations-remediation/task-2-report.md`（证据文件 `.tmp-tc-b.txt`/`.tmp-cu-b.txt`/`.tmp-build-b.txt`/`.tmp-unit-b.txt`/`.tmp-e2e-c.txt` 已摘录后删除） |
| Task 2（收口轮修复） | 同上；另做主流程 `pytest -q` 之外的独立核验：清空例外表复算原始违规、`git show BASE:ui-contract-exceptions.json` 指纹级比对、fontTools 直读 `cmap`、独立 Chromium 探针复现 `select` 行高 | 修复两处「门禁空转」缺陷（入口规则 `report` 未 push、`@font-face` 被 `parseRules` 默认过滤）后才由红转绿；修复前 12 项失败均为「期望恰好 1 条 X，实际：[]」 | 同报告第 2、3.1、5 节 |
| Task 2–11 | 各任务列出的 RED/GREEN 命令 | Task 4 起待实施 | 本表逐任务追加 |
| Task 3 | `rtk npm --prefix web run test:unit -- src/components/ui/uiPrimitives.test.ts src/components/ui/dialogFocus.test.ts`、`test:unit`、`check:ui`、`test:contracts`、`build` | 定向 **30 passed / 0 failed**（新增 `uiPrimitives.test.ts` 23 条 + `dialogFocus.test.ts` 7 条）；全量 `unit` **78 passed**（48 基线 + 30 新增，无回归）；`check:ui` 退出 0；`test:contracts` **83 passed / 0 failed**；`build` 退出 0（`vue-tsc` 类型检查通过、`check:i18n` 946 键、`dist` 产出不变）；三项变异（`UiSelect` 高度令牌改写 1 红、删除 `UiIconButton` 空 label 守卫 1 红、关闭 Tab 圈闭 2 红）均转红并逐字节还原；棘轮不变量 383 = 382 + 1 未被扰动，`components/ui` 新增文件零新增违规；例外表 blob 仍为 `b82f03f0…`（382 条，Task 3 例外配额 0） | 提交 `新增前端公共视觉与焦点原语`；报告与证据见 `.superpowers/sdd/PLAN-DM-029-frontend-ui-foundations-remediation/`（`task-3-report.md`、`evidence/task-3-{red,green,mutations,invariant}.txt`） |
| Task 2（评审修复轮 2） | `rtk npm --prefix web run test:contracts`、`check:ui`、三条新用例的聚焦变异运行 | **83 passed / 0 failed**（+3：例外 `rule`/指纹不一致 2 条 + 入口缺失 1 条）；382 条存量例外审计 **382/382 自洽、指纹零改动**；变异 A（停用一致性校验）使 2 条转红、变异 B（停用入口缺失判定）使 1 条转红，逐字节还原后复绿；`check:ui` 退出 0；未跑 `build`/`test:unit`（改动不触 `.vue`/`.ts`/入口样式表） | 提交 `收紧 UI 契约例外一致性与字体溯源记录`；报告见 `task-2-report.md` 第 11 节 |
| Task 2（评审修复轮 3：文档/注释级） | 只跑 `check:ui`、`test:contracts` 与 PowerShell 字体复核命令（不跑 e2e/build） | 按三轮再审落实 D1–D7：差集复算为 Inter 缺 `U+00AD`、Plex 缺 `U+201B`（均为字体未提供，越界 0）；README 四条硬门禁区分为「字体类三条 + 入口一条」，补齐 Plex/差集/CJK 三条可复制命令并附实测输出；删除 `document.fonts` 误述，将「真实加载」标为未覆盖并登记为本任务收口责任 A；`legacy.css` 的 `:where()` 措辞收窄 | 提交 `校正字体溯源文档与契约注释措辞`；报告见 `task-2-report.md` 第 12 节 |
| Task 3（首轮评审修复） | `test:unit -- src/components/ui/uiPrimitives.test.ts src/components/ui/dialogFocus.test.ts`、`test:unit`、`check:ui`、`test:contracts`、`build`；另做图标溯源逐名称比对与三项变异重跑 | 定向 RED **29 passed / 7 failed**（F1 的 2 条 + F2 的 4 条 + 一条因注释里出现 `v-html` 而误报的断言），修正后 **36 passed / 0 failed**；全量 `unit` **84 passed**；`check:ui` 退出 0；`test:contracts` **83 passed / 0 failed**；`build` 退出 0；例外表 blob 仍 `b82f03f0…`（382 条），不变量 383 = 382 + 1 | 提交 `修正原语实例标识与焦点圈闭边界`；报告与证据见 `task-3-report.md` 第 12–14 节与 `evidence/task-3-fix-*.txt` |
| Task 3（二轮评审收口） | 同上一行的五道门禁；另做 12 项变异重跑（含新增边界项） | 定向 RED **43 passed / 3 failed**（新增的禁用两例 + Escape 事件透传一例）→ GREEN **46 passed / 0 failed**（`dialogFocus.test.ts` 11 → 21 条，共 25 + 21 = 46）；全量 `unit` **94 passed**；`check:ui` 退出 0；`test:contracts` **83 passed / 0 failed**；`build` 退出 0；12 项变异均转红并逐字节还原（去掉禁用守卫 2 红、`closest`→`matches` 1 红、单选组恒取首个 1 红、祖先 `display` 上溯 1 红、`visibility` 1 红、非法 `tabindex` 1 红、Escape 不传事件 1 红等）；不变量 383 = 382 + 1，例外表 blob 仍 `b82f03f0…`（配额 0） | 提交 `订正溯源表述并补齐焦点边界守卫`；报告见 `task-3-report.md` 第 16 节与 `evidence/task-3-fix2-*.txt` |
| Task 3（三轮评审收口：纯文本轮） | `npx vitest run`（全量）、`check:ui`、`test:contracts`、`build`；实现源码仅注释变化 | 全量 `unit` **94 passed**（与二轮收口相同，无用例增减）；`check:ui` 退出 0、例外表 blob 仍 `b82f03f0276155cd0be2b7a2430e9ea031da9118`（382 条，Task 3 配额 0）、`test:contracts` **83 passed / 0 failed**、`build` 退出 0；不变量 383 = 382 + 1、`components/ui` 新增文件零新增违规；本提交只改注释/文档/计划（`dialogFocus.ts` 无逻辑变化），无 e2e | 提交 `订正令牌统计口径与缺口登记落点`；报告见 `task-3-report.md` 第 17 节 |
| Task 4 | `check:ui`、`test:unit`、`test:contracts`、`build`、`test:e2e -- main.spec.ts i18n-visual-evidence.spec.ts`；控制器另跑全量 e2e | 定向 **90 passed / 0 failed / 0 flaky**；`test:unit` **94**；`test:contracts` **83**；`check:ui` 0；`build` 0；例外 382 → 341（本任务名下 41 条 = 38 raw + 3 unicode）；不变量 **342 = 341 + 1**；控制器独立取证：全量 e2e **498 passed / 1 flaky / 0 failed**（flaky 为负载型，隔离 5/5 通过）、4 项变异确认新断言有杀伤力（令牌 `--button-height` 36→34 → e2e 报 `Expected 36 / Received 34`）、3 张截图像素分析非空且主题正确 | 提交 `迁移桌面壳层到统一视觉原语` + `补齐焦点守卫存活变异用例`；报告 `task-4-report.md` |
| Task 4（评审修复轮 1） | 四门禁 + `main.spec.ts` 聚焦 e2e | 四门禁全绿（`test:unit` 97）；`font-size:var(--font-size-14)` → `var(--button-font-size)` 两处（业务侧原始层消费 0 → 2 处，检查器与债务口径**双向不可见**）；原隐藏探针在**非端点**、不参与断言（控制器变异证明：去掉 `getClientRects()` 过滤后仍全绿）→ 改为端点级 + 补 hover/focus/disabled 计算样式断言 | 提交 `修正壳层字号令牌层级与焦点测试覆盖`；复审判定 `Needs fixes`（0 must-fix / 6 should-fix / 4 nit）逐条落实 |
| Task 4（迁移轮 2：浮层与提示宿主） | 四门禁 + `main.spec.ts i18n-visual-evidence.spec.ts` + toast 聚焦 e2e；控制器跑全量 e2e | `test:unit` **102**（+5 条 `returnFocus` 用例）、`test:contracts` **83**、`check:ui` 0、`build` 0；例外 **341 → 320**（删除恰 21 条：`TaskOverlay` 15 + `ToastHost` 6；18 raw + 3 unicode；**零新增**），不变量 **321 = 320 + 1**、`waivedViolations 0`；隐藏形态**先红后绿**（RED `Received "probe-head-hidden"` → GREEN 1 passed）；3 张截图重拍（blob 均变化、尺寸不变）；控制器全量 e2e **498 passed / 2 flaky / 0 failed**（两个 flaky 的失败点分别是 `openWorkspace` 的「选择 DST 文件」按钮 30s 未出现与既有 spec 的负载超时，均与本轮无因果） | 提交 `迁移任务浮层焦点与控件到公共原语` + `迁移提示宿主并清退壳层例外`；报告 `task-4-report.md` §11 |
| Task 4（二审修复轮） | 四门禁 + `main.spec.ts sheets-layout.spec.ts` + 全量 e2e（控制器） | 三处 `.focus({preventScroll:true})` 补回（旧手写副本语义；`sheets-layout.spec.ts` 有零容差 `scrollTop` 断言）；toast 补结构/尺寸断言（36×36，变异 `width:30px` → `Expected 36 / Received 30`）；订正「`shouldReturnFocus` 先行判定」表述（解析器总会先被调用、守卫最后求值，**不重排代码**）；像素/差异清单补齐（`.toast-close` 描边外观丢失、折叠按钮 hover 态新增、红点墨迹 ≈6px→≈5px、「用户可见差异 = 0」收窄到交互路径）；控制器补归档本轮全量 e2e（499 passed / 1 flaky / 0 failed，行号 1551/1586/1624 自证）与 `returnFocus` 变异复现日志 | 提交 `补齐焦点工具防滚动参数与提示宿主断言`；**复审复核 `Approve`**（1 must-fix + 3 should-fix + 6 nit 全部清项） |
| Task 12 | 全量门禁与真实 Windows 缩放；另承担字体真实加载（收口责任 A）与字体子集化命令（收口责任 B）的收口，以及例外表跟踪项（收口责任 C）、`UiButton.label`/`UiIconButton` 的 ARCH 补充（收口责任 D）、令牌分层收口（收口责任 E）、`fieldset[disabled]` 禁用继承与禁用态欠虑（收口责任 F）、存活变异补测的 4 处未覆盖分支（收口责任 G）、检查器 `calc/min/max/clamp/env` 参数检查（收口责任 H）、ARCH-DM-007 §4.1/§5 对齐（收口责任 I）、`0×0` 停靠点语义（收口责任 J）、非控件 14px 语义档位（收口责任 K）、例外 `expiresWith` 与 Files 错位（收口责任 L）、`<aside>` 内 `[hidden]` 兜底（收口责任 M）、`line-height` 令牌层缺失（收口责任 N）、SPEC-DM-006 §232「文本域」无原语（收口责任 O） | 待实施 | `assets/PLAN-DM-029/README.md` |

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
