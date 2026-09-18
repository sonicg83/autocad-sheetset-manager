---
id: PLAN-DM-034
title: 前端文本编辑状态与提交动作对齐实施计划
status: proposed
owners:
- dst-manager
created: 2026-09-18
updated: 2026-09-18
related:
- SPEC-DM-015
- ARCH-DM-007
- SPEC-DM-009
- SPEC-DM-010
- SPEC-DM-011
- SPEC-DM-012
- GUIDE-DM-001
- MEMO-DM-037
---

# 前端文本编辑状态与提交动作对齐实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实施；每个代码任务必须先使用 `superpowers:test-driven-development`，关闭前必须使用 `superpowers:verification-before-completion`。不要把本文的页面裁决重新开放为临场设计问题。

**目标：** 让五处文本编辑界面统一遵循 [SPEC-DM-015](../../../docs/dst-manager/specs/SPEC-DM-015-frontend-text-edit-state-contract.md)：准确比较可信基准，提供可见且可访问的修改反馈，并在无可执行差异时阻止写操作。

**实现架构：** 保留现有页面 composable 与后端契约，在展示组件中复用已经存在的 `dirty`/`modifiedCount`/`saveDisabled` 派生状态；只给 `UiButton` 增加通用的可聚焦语义禁用能力。普通表单采用字段级提示，图纸目录采用模板级提示。所有写事件在视图和处理函数两层守卫，避免只靠 CSS 或 DOM 属性阻断。

**技术栈：** Vue 3、TypeScript、Vue I18n、Vitest、Playwright、Vite、CSS 语义令牌。

## 0. 冻结决策与实施边界

- [ ] 实施前重读 SPEC-DM-015、ARCH-DM-007 §5/§8/§9/§13、GUIDE-DM-001 G2/G7/G8/G9，以及对应页面 Spec。
- [ ] 先执行 `rtk git status --short` 和 `rtk git log -1 --oneline`，确认 SPEC-DM-015、PLAN-DM-034 及四份页面 Spec 的文档基线已提交；若这些文档仍有未提交修改，先停下并与修改所有者核对，不得覆盖。无关用户改动只记录并避开。
- [ ] 不改变任何 HTTP 请求体、响应体、错误码、修订号或后端服务。
- [ ] 不改变草稿与正式保存的业务边界，不新增“自动保存”。
- [ ] 不给图纸目录每个单元格或每行新增 dirty 模型；本轮只增强模板栏状态。
- [ ] 不把即时生效的扩展启停开关改成缓冲保存。
- [ ] 不使用输入框焦点、是否触发过 `input` 事件或“曾编辑”标志判定修改；一律比较当前值与可信基准。
- [ ] 不静默规范化文本；保留既有领域明确规定的规范化行为。
- [ ] 任何新增文案同时更新 `zh-CN` 与 `en-US`，并通过 `check:i18n`。
- [ ] 本计划不新增颜色私值：dirty 边框固定使用 `var(--color-warning)`，dirty 底色固定使用 `var(--color-warning-bg)`，错误使用既有 danger 令牌。若事实证明必须新增令牌，必须同时在 `web/src/styles/tokens.css` 的浅/深主题定义并在该任务运行 `check:ui`。
- [ ] Playwright 1.55 把 `aria-disabled="true"` 视为 disabled；验证 click 守卫时使用 `click({force:true})` 或 `dispatchEvent("click")`，并断言请求/事件计数不增加。普通 `locator.click()` 会等待 enabled 直至超时，不得用它测试“点击无反应”。Enter/Space 使用 `press()`，它不受指针 actionability 门禁影响。
- [ ] 每个代码任务采用 RED → GREEN → REFACTOR，并在对应任务下记录实际失败/通过命令。

### 0.1 MEMO-DM-037 回填追踪

| 审查项 | 本计划的确定性处理 |
| --- | --- |
| F1 | Task 1 使用显式 `click` emit + 默认 attrs 继承；删除 `inheritAttrs:false`/手工 `$attrs` 方案 |
| F2 | 全局约束及 Task 2～6 固定使用强制点击/事件派发、Enter/Space 与请求计数断言 |
| F3 | Task 4 明确组件实例 ref 类型及 `$el.focus()` 调用 |
| F4 | Task 4 使用 `hasValidationError`；Task 5 保留 `saveDisabled` 兼容项并同步消费点 |
| F5 | Task 3 复用 `describedBy()`；Task 5 复用 `filterDirty` 与既有 dirty 样式 |
| F6 | Task 6 把 `extensions-settings.spec.ts` 纳入共享 `TemplateBar` 回归 |
| F7 | Task 8 只在已裁决偏差下更新 Spec/Guide，并按实际存在的唯一索引收口 |
| F8 | 全局固定 warning 令牌，Task 1～6 每批运行 `check:ui` |
| F9 | Task 4 clean 文案唯一复用 `settings.saved` |

## Task 1：为 `UiButton` 增加可聚焦语义禁用

**涉及文件：**

- 修改：`web/src/components/ui/UiButton.vue`
- 修改：`web/src/components/ui/uiPrimitives.test.ts`

**接口：**

- 新增 prop：`ariaDisabled?: boolean`。
- 新增显式事件：`click: [event: MouseEvent]`；父组件 `@click` 只由组件内部 `emit` 触发。
- 保持既有 `disabled`、`loading`、`label`、variant、size、type 及默认属性透传行为不变。

### Step 1：先写失败测试

- [ ] 在 `uiPrimitives.test.ts` 增加 `ariaDisabled` 用例，断言：
  - `ariaDisabled=true` 时按钮仍无原生 `disabled` 属性；
  - 输出 `aria-disabled="true"` 和统一禁用 class；
  - 对根按钮派发原生 click 时，父组件监听器和 wrapper 的 `click` emit 计数均保持 0；
  - `loading=true` 或 `disabled=true` 仍使用原生 `disabled`；
  - `ariaDisabled=false` 不输出多余属性，既有按钮行为不变。
- [ ] 运行 `rtk npm --prefix web run test:unit -- src/components/ui/uiPrimitives.test.ts`，确认新用例因能力缺失而失败。

### Step 2：实现最小原语契约

- [ ] 给 `UiButton` 增加 `ariaDisabled?: boolean` prop，并声明 `defineEmits<{click: [event: MouseEvent]}>()`；保持 Vue 默认 `inheritAttrs`，不使用 `inheritAttrs:false`，也不手工 `v-bind="$attrs"`。已声明的 `onClick` 会从 fallthrough attrs 中排除，其他 class、ARIA 与原生属性仍自动落到唯一根按钮。
- [ ] 计算 `blocked = disabled || loading || ariaDisabled`；原生 `disabled` 只绑定 `disabled || loading`。
- [ ] 根按钮的内部 click 处理器在 `ariaDisabled` 下调用 `event.preventDefault()` 并直接返回、不 emit；可用时才 `emit("click", event)`。原生 button 的 Enter/Space/程序化 `.click()` 最终都经过该 click 守卫，不另造页面级键盘逻辑。
- [ ] 输出 `aria-disabled`，并让 hover/active/禁用外观同时识别 `:disabled` 与 `.ui-button--aria-disabled`。
- [ ] 保留 `focus-visible`，不得设置 `pointer-events:none`，否则无法提供一致的鼠标反馈和测试事件守卫。

建议模板结构：

```vue
<button
  :disabled="disabled || loading"
  :aria-disabled="ariaDisabled ? 'true' : undefined"
  :class="{'ui-button--aria-disabled': ariaDisabled}"
  @click="onClick"
>
```

事件守卫只负责禁用语义，不承载页面业务。

### Step 3：验证与提交

- [ ] 重跑 `uiPrimitives.test.ts` 并确认通过。
- [ ] 运行 `rtk npm --prefix web run check:ui`，确认共享原语没有新增 UI 契约违规。
- [ ] 运行 `rtk npm --prefix web run test:unit`，确认共享原语没有回归。
- [ ] 检查键盘 Tab 仍可聚焦 `ariaDisabled` 按钮，原生 `disabled` 仍不进入 Tab 顺序。
- [ ] 提交：`统一按钮可聚焦语义禁用行为`。

## Task 2：对齐图纸页属性编辑

**涉及文件：**

- 修改：`web/src/components/sheets/SheetPropertyEditor.vue`
- 修改：`web/tests/e2e/sheets-editing.spec.ts`
- 修改：`web/tests/e2e/sheets-visual-evidence.spec.ts`（只补必要的稳定视觉证据）

**接口：** 复用现有 `modifiedCount` 与 `sheets.editor.statusDraft/statusClean`；不新增状态 store、API 或 i18n 键。

### Step 1：锁定现状与失败用例

- [ ] 用现有 fixture 打开一张含至少两个跨页属性的图纸，记录初始草稿投影。
- [ ] 先写 Playwright 用例，记录现有 `draftBodies.length`，断言初始“加入草稿”有 `aria-disabled="true"` 且无原生 `disabled`；分别执行 `click({force:true})`、`press("Enter")`、`press("Space")` 后，`draftBodies.length` 均不增加。
- [ ] 输入不同值后断言对应 `.prop-field` 同时出现 dirty class、琥珀边框/底色和可见“未加入草稿”文字，按钮转为可执行。
- [ ] 改回草稿投影值后断言字段提示和跨页修改数清除，按钮恢复语义禁用。
- [ ] 增加 dirty + invalid 组合断言：红色错误边框优先，但“未加入草稿”文字保留。
- [ ] 运行 `rtk npm --prefix web run test:e2e -- sheets-editing.spec.ts`，确认新增断言失败且失败原因与预期一致。

### Step 2：最小实现

- [ ] 复用现有 `modifiedCount` 与字段值比较，不新增第二套 dirty store。
- [ ] 给字段容器增加 `is-dirty` class；字段状态文字放在输入附近并通过 `aria-describedby` 关联。
- [ ] 在 `SheetPropertyEditor.vue` 引入 `UiButton`，只迁移页脚“取消/加入草稿”两个动作；分页和错误跳转按钮不在本任务顺带迁移。调整页脚局部样式，保持既有尺寸和布局。
- [ ] `modifiedCount === 0` 时给“加入草稿”传 `:aria-disabled="true"`；`context.invalid`、加载中或失效仍使用原生 `disabled`。
- [ ] 新增 `onSubmit()`，在 emit 前检查 `modifiedCount > 0 && !context.invalid`，保证编程调用也不能创建空草稿。
- [ ] 使用现有主题语义令牌实现琥珀状态；错误选择器优先级必须高于 dirty。

### Step 3：验证与提交

- [ ] 运行 `sheets-editing.spec.ts` 与 `sheets-drafts.spec.ts`。
- [ ] 运行 `rtk npm --prefix web run check:ui`。
- [ ] 在浅色与深色各验证一次 dirty/invalid 状态；视觉证据只保留能证明本次差异的最小集合。
- [ ] 提交：`对齐图纸属性编辑状态与草稿动作`。

## Task 3：对齐属性页属性值编辑

**涉及文件：**

- 修改：`web/src/components/properties/PropertyValuePanel.vue`
- 修改：`web/tests/e2e/properties-values.spec.ts`
- 修改：`web/tests/e2e/properties-visual-evidence.spec.ts`（只补必要证据）

**接口：** 复用 `dirtyCount`、现有 `describedBy()` 以及 `properties.values.flagDirty/dirtyCount/noChanges`；不新增 i18n 键。

### Step 1：先把缺失契约写进测试

- [ ] 在现有“三态并存”用例中补断言：dirty 字段容器必须有琥珀视觉，pending 字段仍为蓝色，错误字段为红色且保留 dirty 文字。
- [ ] 新增 clean 初始态：记录 fixture 的 `draftBodies.length`，断言“加入草稿”有 `aria-disabled="true"`、无原生 `disabled`；分别执行 `click({force:true})`、Enter、Space 后计数不增加。“放弃本区输入”保持既有行为，不在本计划扩大次要动作规则。
- [ ] 新增“输入不同 → 改回草稿值”场景，断言 dirty 计数、隐藏修改数、字段标记与按钮状态同步归零。
- [ ] 运行 `rtk npm --prefix web run test:e2e -- properties-values.spec.ts`，确认新增断言先失败。

### Step 2：修正展示与动作守卫

- [ ] 给 `.value-item` 补 `is-dirty` class，使用 SPEC-DM-010 已规定的琥珀边框/底色；不得把待写入状态误涂成 dirty。
- [ ] 核对并复用现有 `describedBy()`（当前已把 dirty/pending 状态 ID 与错误 ID 关联到输入）；不得另写第二套 ARIA 计算。
- [ ] `dirtyCount === 0` 时，“加入草稿”使用 `ariaDisabled`；invalid/冲突等现有阻断继续原生禁用。
- [ ] 给 submit 处理路径补 `dirtyCount > 0` 守卫；discard 行为不变。
- [ ] 保持筛选隐藏的 dirty 字段仍计入提交，不因当前不可见而误判 clean。

### Step 3：验证与提交

- [ ] 运行 `properties-values.spec.ts`、`properties-workspace.spec.ts`、`properties-model.spec.ts`。
- [ ] 运行 `rtk npm --prefix web run check:ui`。
- [ ] 核对浅色、深色、2/4 列切换下的 dirty/error 优先级。
- [ ] 提交：`补齐属性值修改提示与空提交守卫`。

## Task 4：对齐设置中心常规设置

**涉及文件：**

- 修改：`web/src/components/settings/SettingsDialog.vue`
- 修改：`web/tests/e2e/settings-dialog.spec.ts`

**接口：** clean 文案唯一裁决为复用 `settings.saved`；使用现有单数标识符 `hasValidationError`。常规保存按钮 ref 改为 `ref<InstanceType<typeof UiButton> | null>`。

### Step 1：用测试移除特殊例外

- [ ] 修改/新增测试：常规设置初始打开时显示 `settings.saved`，保存按钮可聚焦、`aria-disabled="true"`、无原生 `disabled`。在 `/api/settings` 测试 route 中记录 PUT 次数，分别执行 `click({force:true})`、Enter、Space 后次数保持不变。
- [ ] 编辑任一文本字段后保存按钮恢复可执行，字段行继续保持既有琥珀提示。
- [ ] 改回已保存快照后按钮再次语义禁用；保存成功后焦点回到同一保存按钮且按钮处于可聚焦的 clean 状态。
- [ ] 校验失败、保存中、Schema 阻断仍使用现有强阻断语义，不因 `ariaDisabled` 放宽。
- [ ] 运行 `rtk npm --prefix web run test:e2e -- settings-dialog.spec.ts`，确认旧“clean 仍可保存”行为导致测试失败。

### Step 2：实现统一判定

- [ ] 删除 `saveDisabled` 旁“clean 仍可执行空保存”的旧例外；把失效的 `SPEC-DM-013 G6.3` 注释改为 `SPEC-DM-015 §5.2`，语言切换部分仍引用现有 I18N-06。
- [ ] 在 `SettingsDialog.vue` 引入 `UiButton`，只迁移常规设置的主保存按钮，不顺带迁移全部裸按钮。把 `saveButtonEl` 改为 `ref<InstanceType<typeof UiButton> | null>`，保存成功后的调用改为 `saveButtonEl.value?.$el?.focus()`。
- [ ] 拆分 `saveNativeDisabled = saving || schemaBlocked || hasValidationError` 与 `saveAriaDisabled = !hasUnsaved`；模板分别绑定 `:disabled="saveNativeDisabled"`、`:aria-disabled="saveAriaDisabled"`。
- [ ] 保存处理函数首行守卫 `hasUnsaved && !saveNativeDisabled`；clean 点击不得调用 API、递增修订或显示新的成功 toast。
- [ ] 操作区 clean 状态固定复用 `settings.saved`（“已保存”）；dirty 与 saving 继续使用既有状态表达，不新增 `settings.noChanges`。
- [ ] 不改 `SettingsFormRow.vue` 已存在的字段级琥珀样式，除非测试证明错误优先级或 ARIA 关联缺失；若修改，必须补对应组件或 e2e 测试。

### Step 3：验证与提交

- [ ] 运行 `settings-dialog.spec.ts` 和设置相关 Vitest。
- [ ] 运行 `rtk npm --prefix web run check:ui`。
- [ ] 复验保存成功后的焦点、Esc/关闭未保存保护与主题即时生效行为。
- [ ] 提交：`统一常规设置保存动作与修改状态`。

## Task 5：对齐扩展配置生成式表单与自定义面板

**涉及文件：**

- 修改：`web/src/components/settings/ExtensionSettingsHost.vue`
- 修改：`web/src/components/settings/GeneratedExtensionSettingsForm.vue`（仅补 ARIA/错误优先级缺口）
- 修改：`web/src/components/settings/SheetCatalogSettingsPanel.vue`
- 修改：`web/src/components/settings/SettingsDialog.vue`（扩展子视图按钮接线）
- 修改：`web/tests/e2e/extensions-settings.spec.ts`
- 修改：`web/tests/e2e/settings-extensions-production-evidence.spec.ts`（只补必要证据）

**接口：** `ExtensionSettingsHost` 新暴露 `saveNativeDisabled`、`saveAriaDisabled`，并保留 `saveDisabled = saveNativeDisabled || saveAriaDisabled` 兼容读取项；复用现有 `filterDirty`、`extensions.sheetCatalog.dirtyBadge` 与 `settings.extensionSettings.saved`。

### Step 1：扩展设置状态测试

- [ ] 生成式表单：锁定 clean/dirty/revert/invalid/saving/saved/read-only 状态，clean 保存必须可聚焦且 `aria-disabled`，只读 Schema 仍原生禁用。
- [ ] 自定义图纸目录设置：编辑输出过滤文本后，字段容器出现琥珀提示和“有未保存修改”；改回服务端快照后提示清除。
- [ ] 自定义字段 dirty + 数量/长度错误时红色优先但修改文字保留，保存不可执行。
- [ ] clean 状态保存按钮断言 `aria-disabled="true"` 且无原生 `disabled`；分别执行 `click({force:true})`、Enter、Space 后 `mock.puts.length` 不变。dirty 保存成功后重建快照并显示“已保存”。
- [ ] 运行 `rtk npm --prefix web run test:e2e -- extensions-settings.spec.ts`，确认缺失的自定义字段提示与按钮语义导致失败。

### Step 2：实现与接线

- [ ] 定义 `saveNativeDisabled = saving || readOnly || snapshot === null || hasFieldErrors`、`saveAriaDisabled = !dirty`、兼容项 `saveDisabled = saveNativeDisabled || saveAriaDisabled`，三者一并 `defineExpose`；同步更新 `SettingsDialog.vue` 的消费点，不能留下只读 `configHost.saveDisabled` 的旧接线。
- [ ] `SettingsDialog` 扩展子视图保存按钮接入 `UiButton`；clean 绑定 `configHost.saveAriaDisabled`，saving/read-only/snapshot 缺失/字段错误绑定 `configHost.saveNativeDisabled`。
- [ ] `SheetCatalogSettingsPanel` 直接复用控制器已导出的 `catalog.filterDirty`，给过滤字段容器添加 dirty class、可见 `extensions.sheetCatalog.dirtyBadge` 和稳定状态 ID；输入的 `aria-describedby` 同时包含现有 hint、dirty 状态（存在时）及 error（存在时）。不得重新比较快照，也不得引用模板 dirty。
- [ ] `GeneratedExtensionSettingsForm` 沿用已有 `.ef-row.dirty` 和 `.ef-row.error`，只增加可见 dirty 文字、稳定 ID 与 `aria-describedby`；错误 class 继续后置并覆盖 dirty 边框/底色。
- [ ] save 入口保留业务守卫，防止外部 ref 调用绕过按钮状态。

### Step 3：验证与提交

- [ ] 运行 `extensions-settings.spec.ts`、设置单测和扩展 i18n 契约测试。
- [ ] 运行 `rtk npm --prefix web run check:ui`。
- [ ] 回归返回扩展列表、关闭确认、冲突重试、只读 Schema 和焦点归还。
- [ ] 提交：`对齐扩展配置修改提示与保存语义`。

## Task 6：增强图纸目录模板级状态

**涉及文件：**

- 修改：`web/src/components/sheet-catalog/TemplateBar.vue`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- 修改：`web/tests/e2e/extensions-settings.spec.ts`（同一 `TemplateBar` 也嵌入设置子视图）

**接口：** 复用 `catalog.dirty`、`extensions.sheetCatalog.dirtyBadge/templateStateSaved` 与 Task 1 的 `UiButton.ariaDisabled`；不新增行级状态或 i18n 键。

### Step 1：先锁定分组级契约

- [ ] 新增测试：clean 模板显示中性“已保存”，保存修改按钮有 `aria-disabled="true"` 且无原生 `disabled`。对按钮执行 `click({force:true})`、Enter、Space，断言 `state.putExpectedRevisions` 不增加。
- [ ] 修改列名或表达式后，模板栏出现具有警示视觉的“有未保存修改”徽标，保存修改按钮可执行。
- [ ] 改回模板快照后状态恢复 clean，保存按钮重新语义禁用。
- [ ] 表达式错误时保留“有未保存修改”，错误就地呈现，保存不可执行。
- [ ] 断言列输入框没有被统一添加 dirty 背景，防止偏离 SPEC-DM-015 的模板级裁决。
- [ ] 在 `extensions-settings.spec.ts` 同步断言嵌入设置子视图的 `TemplateBar` 仍使用模板级徽标；同页输出过滤文本框继续使用 Task 5 的字段级提示，两种层级不得互相替代。
- [ ] 运行 `rtk npm --prefix web run test:e2e -- sheet-catalog.spec.ts`，确认新增视觉/语义断言先失败。

### Step 2：实现模板栏提示

- [ ] 把 `.template-state` 从普通 muted 文本升级为中性/警示两种徽标；dirty 使用琥珀语义令牌和可见文字。
- [ ] 将“保存修改”的 clean 状态从原生 `disabled` 改为 `ariaDisabled`；read-only、saving 等现有强阻断继续原生禁用，不新增控制器并不存在的 invalid 派生状态。
- [ ] 保存处理函数同时守卫 `catalog.dirty.value` 和现有可保存条件。
- [ ] 状态变化使用 `role="status"`，避免频繁输入造成侵入式 `alert` 播报。
- [ ] 不修改 `ColumnEditor.vue` 的字段视觉和差异模型。

### Step 3：验证与提交

- [ ] 运行 `sheet-catalog.spec.ts`、`sheet-catalog-visual-evidence.spec.ts` 与 `extensions-settings.spec.ts`。
- [ ] 运行 `rtk npm --prefix web run check:ui`。
- [ ] 更新浅色/深色、1440 基准视口与 900 最小视口的必要证据；确认警示徽标不挤压模板操作。
- [ ] 提交：`增强图纸目录模板修改状态提示`。

## Task 7：跨页面契约、文案与回归收口

**涉及文件：**

- 复核：Task 1–6 已修改的组件与既有 e2e 文件；本任务不预设新增跨页 spec 或 i18n 文件。

**接口：** 五处页面统一消费 Task 1 的 `ariaDisabled`；所有用户文案复用现有键，因此 `check:i18n` 的中英文键集合不得变化。

### Step 1：静态与行为契约

- [ ] 搜索所有“加入草稿”“保存修改”“保存”入口，确认本计划五处没有 `clean` 可写例外。
- [ ] 检查 `aria-disabled` 使用者都由 `UiButton` 统一守卫；禁止裸按钮只加属性而不拦截事件。
- [ ] 检查草稿流只使用“未加入草稿/待写入”，直存流只使用“有未保存修改/已保存”。
- [ ] 确认错误状态没有删除修改文字，焦点态没有被当作 dirty。
- [ ] 运行 `rtk npm --prefix web run check:i18n`。

### Step 2：最小充分回归

- [ ] 运行 `rtk npm --prefix web run test:unit`。
- [ ] 运行五个相关 e2e：

```powershell
rtk npm --prefix web run test:e2e -- sheets-editing.spec.ts properties-values.spec.ts settings-dialog.spec.ts extensions-settings.spec.ts sheet-catalog.spec.ts
```

- [ ] 运行 `rtk npm --prefix web run build`。
- [ ] 若 e2e 卡在按钮 actionability，先检查测试是否对 `aria-disabled` 按钮误用了普通 `click()`；守卫测试应使用强制点击/事件派发并核对请求计数。若 `toBeDisabled()` 仍通过但缺少新语义证据，补 `aria-disabled="true"` 与无原生 `disabled` 的断言，不得批量放宽断言。

### Step 3：检查点

- [ ] 无代码修正时只记录验证结果，不创建空提交；如回归发现并修复跨页面问题，只提交本任务实际修正的文件，提交信息为 `收口文本编辑状态跨页面回归`。

## Task 8：设计 QA、文档同步与计划关闭

**涉及文件：**

- 修改：`.planning/plans/dst-manager/PLAN-DM-034-frontend-text-edit-state-alignment.md`
- 修改：`.planning/plans/dst-manager/README.md`
- 修改：`changelog.md`
- 新增：`.planning/memos/dst-manager/assets/PLAN-DM-034/README.md`
- 新增证据：`.planning/memos/dst-manager/assets/PLAN-DM-034/sheets-dirty-invalid-light-1440.png`
- 新增证据：`.planning/memos/dst-manager/assets/PLAN-DM-034/properties-three-states-dark-1440.png`
- 新增证据：`.planning/memos/dst-manager/assets/PLAN-DM-034/settings-general-dirty-light-900.png`
- 新增证据：`.planning/memos/dst-manager/assets/PLAN-DM-034/extensions-generated-invalid-dark-900.png`
- 新增证据：`.planning/memos/dst-manager/assets/PLAN-DM-034/extensions-custom-filter-dirty-light-1440.png`
- 新增证据：`.planning/memos/dst-manager/assets/PLAN-DM-034/catalog-template-dirty-dark-1440.png`
- 条件修改：`docs/dst-manager/specs/SPEC-DM-015-frontend-text-edit-state-contract.md`（只有出现经用户裁决的规范偏差时追加追记）
- 条件修改：`docs/dst-manager/specs/SPEC-DM-009～012` 与 `GUIDE-DM-001`（现有 `43f1416` 对齐条款不足且偏差已经裁决时才修改，不重复通用规则）
- 条件修改：`docs/dst-manager/README.md`（只有 SPEC-DM-015 状态或权威入口变化时更新；仓库不存在 `docs/dst-manager/specs/README.md`，不得凭空创建第二份索引）

### Step 1：G8 设计 QA

- [ ] 对五处页面逐项执行 SPEC-DM-015 §7 八个验收场景；用同一虚构数据比较 clean/dirty/invalid/revert。
- [ ] 生成并登记文件清单中 6 张正交证据：合计覆盖浅/深主题、1440px/900px、字段级 dirty、模板级 dirty、dirty + invalid、属性页三态与两类扩展配置。证据 README 逐张记录 fixture、主题、视口、状态、生成命令和对应 SPEC-DM-015 条款。
- [ ] 另执行浏览器 200% 缩放自动检查并把结果写入证据 README；它只属于 G8 响应式证据，不冒充 G9 的真实 Windows 缩放截图。
- [ ] 手工键盘检查 Tab、Enter、Space、Esc、错误聚焦和保存后焦点归还。
- [ ] 逐项记录差异为“缺陷、已接受差异或后续项”，注明日期和裁决人；影响本规范主目标的差异不得留到计划关闭后。

### Step 2：全量门禁

- [ ] 运行：

```powershell
rtk npm --prefix web run check:i18n
rtk npm --prefix web run check:ui
rtk npm --prefix web run test:unit
rtk npm --prefix web run build
rtk npm --prefix web run test:e2e
rtk uv run ruff check .
rtk uv run pytest -q
rtk uv lock --check
```

- [ ] 任何失败都记录命令、失败数、根因和处理结果；不得只记录最终绿色结果。
- [ ] 本计划不涉及 AutoCAD SCR、插件命令或布局重建，除非实施中意外触及这些文件，否则不运行真实 CAD 系统测试，并在关闭记录中注明未运行原因。

### Step 3：G9 与文档关闭

- [ ] 在真实 Windows 桌面壳检查五处页面的 clean/dirty/revert、键盘焦点和浅深主题；100/125/150/200% 缩放按 GUIDE-DM-001 G9 执行，浏览器模拟不代替真实缩放。
- [ ] 把实际测试数量、视觉证据、真实桌面结果和偏差写回本计划；只有必需门禁完成后才把状态改为 `completed`。
- [ ] 同步计划索引和 `changelog.md`。只有发生已裁决偏差才追记 SPEC-DM-015；页面 Spec 与 GUIDE 已由 `43f1416` 建立引用，若无新裁决则保持不动。
- [ ] 最终提交：`完成前端文本编辑状态对齐验收`。

## 9. 完成定义

只有同时满足以下条件，PLAN-DM-034 才能关闭：

- [ ] 五处页面均以可信基准派生 dirty，改回原值立即 clean；
- [ ] 普通表单字段级提示与目录模板分组级提示符合 SPEC-DM-015；
- [ ] clean 主动作可聚焦但不会执行写操作，强阻断状态仍使用原生 disabled；
- [ ] dirty + invalid 的错误视觉优先且修改文字保留；
- [ ] 草稿流与直存流术语不混用，中英文键集合一致；
- [ ] 相关单测、e2e、生产构建、全量前端回归及仓库规定门禁通过；
- [ ] G8 证据与 G9 真实桌面结果已记录；
- [ ] 所有实现偏差已经裁决并同步到唯一权威文档，没有只存在于代码注释的例外。
