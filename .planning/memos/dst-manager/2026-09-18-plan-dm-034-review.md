---
id: MEMO-DM-037
title: PLAN-DM-034 实施计划审查报告
status: final
owners:
  - dst-manager
created: 2026-09-18
updated: 2026-09-18
related:
  - PLAN-DM-034
  - SPEC-DM-015
  - ARCH-DM-007
  - GUIDE-DM-001
document_kind: memo
---

# PLAN-DM-034 实施计划审查报告（MEMO-DM-037）

## 日期

2026-09-18

## 审查范围

- 被审查对象：[PLAN-DM-034](../../plans/dst-manager/PLAN-DM-034-frontend-text-edit-state-alignment.md)（`status: proposed`）。审查时该计划与 SPEC-DM-015 仍为未跟踪新文件，随后已随 `43f1416 docs: 新增前端文本编辑状态与提交动作相关规范与计划` 一并提交；本备忘的核对结论基于该提交内容，仍然成立。
- 权威依据：[SPEC-DM-015](../../../docs/dst-manager/specs/SPEC-DM-015-frontend-text-edit-state-contract.md) 全文，`ARCH-DM-007-frontend-ui-foundations.md`、`GUIDE-DM-001` G7/G8/G9，以及 SPEC-DM-009/010/011/012 的既有对齐条款。
- 事实核对对象：`web/src/components/{ui,sheets,properties,settings,sheet-catalog}` 下五个页面组件与 `UiButton`、对应 composable、`web/package.json` 脚本、`scripts/ui-contract-exceptions.json`、`scripts/check-i18n.mjs`、`web/tests/e2e` 相关 spec、`web/src/styles/tokens.css`，以及 `node_modules/playwright-core`（1.55）的 `aria-disabled` 处理源码。
- 审查性质：**只读静态审查**。未执行任何测试、构建或 `check:*` 门禁，未修改计划正文、应用源码、测试或其它文档。
- 结论映射：下文 F1–F9 与评审对话中报告的 D1–D9 一一对应。

## 结论

计划方向正确：裁决与 SPEC-DM-015 §5/§6 一致，文件清单与多数标识符经核对全部真实存在，`rtk` 前缀也符合近期计划与备忘的既有写法。但存在 **1 项会直接做错的技术方案（F1）**、**3 项会直接导致红测失败或返工的事实性缺口（F2/F3/F4）**，以及 5 项范围、文档同步与令牌约束问题（F5–F9）。建议按 F1–F4 修订计划后再进入实施。

## 已核对通过（无需修改）

| 计划断言 | 核对结果 |
| --- | --- |
| 五个页面组件与 10 个 e2e 文件路径 | 全部存在 |
| `SheetPropertyEditor.vue` 未引入 `UiButton`、页脚 5 个裸 `<button>` | 成立（`SheetPropertyEditor.vue:28` 起 `emit` 定义，页脚裸 button） |
| `PropertyValuePanel.vue` 的"加入草稿"当前 clean 可提交 | 成立（`PropertyValuePanel.vue:217` 无任何禁用绑定） |
| `SettingsDialog.vue` 存在"clean 仍可保存"例外 | 成立（`SettingsDialog.vue:222-225`） |
| `TemplateBar.vue` 用 `!catalog.dirty` 做原生禁用 | 成立（`TemplateBar.vue:95`） |
| `ExtensionSettingsHost.saveDisabled` 混合 read-only 与 clean | 成立（`ExtensionSettingsHost.vue:84`） |
| `.prop-field` / `.value-item` / `.template-state` 选择器 | 全部存在 |
| `modifiedCount` / `dirtyCount` / `hasUnsaved` / `catalog.dirty` / `filterText` / `filterError` | 全部存在 |
| SPEC-DM-015 §4.3 的 `role="status"` 覆盖 | `PropertyValuePanel:208`、`SettingsDialog:441-442`、图纸页页脚已满足；`TemplateBar` 为唯一缺口，Task 6 已覆盖 |
| i18n 域文件集合（`sheets/properties/settings/extensions` × zh-CN/en-US） | 存在，`check-i18n.mjs` 校验域/键/参数一致与硬编码中文 |
| `rtk` 前缀可用性 | `rtk` 已安装，且 PLAN-DM-029/031 的备忘与计划均使用该写法 |
| Step 0 要求先 `git status` 记录用户已有改动 | 必要（已生效）：审查时四份页面 Spec、ARCH-DM-007、GUIDE-DM-001、两个 README 与 SPEC-DM-015/PLAN-DM-034 同处一个未提交工作区，现已由 `43f1416` 一并提交 |

## 审查发现

### F1（阻塞）：Task 1 的 `inheritAttrs:false` + `v-bind="$attrs"` 方案与其自述目标相反

**位置：**

- `.planning/plans/dst-manager/PLAN-DM-034-frontend-text-edit-state-alignment.md` Task 1 Step 2
- `web/src/components/ui/UiButton.vue`（当前无 `emits` 声明、无 `inheritAttrs` 配置）

**事实：**

计划写"使用 `defineOptions({inheritAttrs:false})` + `v-bind="$attrs"` 保留其他原生属性，避免父级 click 监听绕过内部守卫落到根按钮"。该理由不成立：

- 真正使父级 `@click` 不再成为根元素原生监听器的是**声明 `emits: ['click']`**——Vue 会把已声明 emit 对应的监听器从 `$attrs` 中排除，父级通过 `emit('click', event)` 触发，天然不可能绕过内部守卫。
- `v-bind="$attrs"` 会把 `$attrs` 中剩余的监听器（含未来任何未被声明为 emit 的 `onClick`）重新挂到根 `<button>` 上，恰恰是计划想避免的形态。
- 计划同时要求"用 `stopImmediatePropagation()` 且不 emit"，但该写法依赖"内部处理器先于 attrs 监听器执行"的顺序，方案中没有给出任何保证手段。

补充事实：全仓不存在 `<UiButton ... @click.修饰符>` 用法，因此改为声明 `emits` 不破坏任何既有调用点。

**影响：**

按原文实施会得到一个"看起来受保护、实际可能被绕过"的守卫；即使本次侥幸生效，也会在后续重构中静默失效。

**建议：**

改为「声明 `defineEmits<{click: [event: MouseEvent]}>()`，保持默认 `inheritAttrs`，**不使用** `v-bind="$attrs"`；内部处理器在 `ariaDisabled` 时调用 `event.preventDefault()` 并直接返回、不 `emit`」。若坚持 `inheritAttrs:false`，必须显式从绑定中剔除 `onClick`，并补一条"父级 `@click` 在 `ariaDisabled` 下不触发"的组件级测试。

### F2（阻塞）：计划设计的"clean 点击不发请求"e2e 断言会把测试挂死

**位置：**

- 计划 Task 1/2/3/4/5/6 各 Step 1 的"点击不发请求/不发事件"断言
- 计划 Task 7 Step 2 的失败排查指引
- 证据：`web/node_modules/playwright-core/lib/coreBundle.js`

**事实：**

从 Playwright 1.55 实际源码确认：

- `getAriaDisabled(element) = isNativelyDisabled(element) || hasExplicitAriaDisabled(element)`，`kAriaDisabledRoles` 包含 `"button"`。
- 指针动作在非 `force` 时等待 `["visible", "enabled", "stable"]`。

因此 `locator.click()` 遇到 `aria-disabled="true"` 的按钮会**持续等待 enabled 直至超时（默认 30s）失败**，而不是"点了没反应"。

连带结论（两点都要写进计划）：

- 既有断言 `sheets-editing.spec.ts:403`、`extensions-settings.spec.ts:910/921/960/979/1124/1153`、`settings-dialog.spec.ts:38/519/523` 等 `toBeDisabled()` **不会**因语义禁用而失效（Playwright 认 `aria-disabled`），但**也无法证明新语义**；计划已要求补 `aria-disabled="true"` 与"无原生 `disabled`"断言，这部分保持即可。
- `locator.press("Enter"/"Space")` 走 `elementHandle._press → _focus`，**没有** enabled 门禁，因此键盘断言可按计划原样书写。

**影响：**

实施者按计划原文写红测会卡在 actionability 超时上，容易误判为功能缺陷或去放宽断言；Task 7 预设的失败原因（"测试仍假设原生 disabled"）与实际失败原因不符。

**建议：**

在 Task 1–6 的测试步骤中写死一种不触发写操作的点击写法并配断言：

- `await button.click({force: true})` 或 `await button.dispatchEvent("click")`；键盘用 `await button.press("Enter")`；
- 同时断言请求计数/业务事件计数未增加（例如 e2e 内 mock 的 `puts.length` 不变）。
- Task 7 的排查条目改为"e2e 因 actionability 等待 enabled 超时，而非测试假设原生 disabled"。

### F3（阻塞）：Task 4 用 `UiButton` 替换保存按钮会打断焦点归还，"保留 `ref`"不成立

**位置：**

- 计划 Task 4 Step 2（"引入 `UiButton`……保留 `ref`、现有 primary 外观和保存后焦点归还"）
- `web/src/components/settings/SettingsDialog.vue:43`（`ref<HTMLButtonElement|null>`）、`:313`（`saveButtonEl.value?.focus()`）、`:451`（`<button ref="saveButtonEl">`）
- 仓内正确写法：`web/src/components/properties/PropertyDefinitionPanel.vue:93`（`addToggleButton.value?.$el.focus()`）

**事实：**

改为组件后，模板 `ref` 拿到的是组件实例而非 DOM 元素，组件实例没有 `focus()`；`:313` 的焦点归还会失效。计划"保留 `ref`"的表述不足以说明这一点。

**影响：**

保存成功后（含语言切换事务路径）焦点丢失，直接违反 SPEC-DM-015 §5.2 与既有 SC-09 语义；Task 4 自己设计的"保存成功后焦点回到同一保存按钮"断言会失败，但原因会被误判为实现缺陷。

**建议：**

Task 4 Step 2 明确写：「`const saveButtonEl = ref<InstanceType<typeof UiButton> | null>(null)`，`:313` 改为 `saveButtonEl.value?.$el?.focus()`」，或给 `UiButton` 增加 `defineExpose({focus})`。Task 6 若给 TemplateBar 按钮增加 ref 同理。

### F4（阻塞）：标识符名与现网不一致，会导致错误的重命名

**位置：**

- 计划 Task 4 Step 2（两处 `hasValidationErrors`）
- `web/src/components/settings/SettingsDialog.vue:225`（实际为 `hasValidationError`，单数）
- 计划 Task 5 Step 2（"另暴露 `saveNativeDisabled` 与 `saveAriaDisabled`"）
- `web/src/components/settings/ExtensionSettingsHost.vue:175`（`defineExpose({..., saveDisabled, ...})`）与 `web/src/components/settings/SettingsDialog.vue:447`（模板消费 `configHost.saveDisabled`）
- 计划 Task 4 Step 2（"删除 `saveDisabled` 旁'无改动保存仍可聚焦'的旧例外注释"）与 `SettingsDialog.vue:222-225` 注释中引用的 `SPEC-DM-013 G6.3`

**事实：**

- `hasValidationErrors` 在全仓不存在。
- `ExtensionSettingsHost.saveDisabled` 不仅被内部使用，还被 `SettingsDialog.vue:447` 直接消费；计划未说明是保留兼容别名还是同步改造该调用点与相关测试。
- 注释引用的 `SPEC-DM-013 G6.3` 在全仓 `grep` 不到（SPEC-DM-013 是多语言 UI 规范），该引用已失效。

**影响：**

实施者会写出与实际符号不匹配的代码，或做一次影响面未说明的 `defineExpose` 契约变更。

**建议：**

计划内统一改为 `hasValidationError`；Task 5 明确"保留 `saveDisabled` 作为兼容读取项（或同步更新 `SettingsDialog.vue:447` 与相关 e2e）"；删除旧例外时一并修正失效的规范引用。

### F5（重要）：Task 3 部分"补"实际已存在，会浪费一轮或写出重复实现

**位置：**

- 计划 Task 3 Step 2（"将字段状态文字 ID 关联到输入控件；同一字段 dirty + pending 时都可读取"）
- `web/src/components/properties/PropertyValuePanel.vue:69-72`（已按 dirty/pending/error 计算 `aria-describedby`）
- `PropertyValuePanel.vue:212`（已有 clean 提示 `noChanges`）、`:208`（已有 `role="status"` 计数区）
- 计划 Task 5 Step 2（"以当前过滤文本与加载快照精确比较"）
- `web/src/composables/useSheetCatalogSettings.ts:240`、`:480`（`filterDirty` 已实现并导出）

**建议：**

把上述条目改写为"核对/复用现有实现（位置）"，将 Task 3 的工作量收敛到确实缺失的三处：`.value-item` 的琥珀容器、submit 的 clean 语义禁用、submit 路径守卫。

### F6（重要）：Task 5 与 Task 6 在同一渲染面重叠，验收不独立

**位置：**

- 计划 Task 5 / Task 6 文件清单与验证命令
- `web/src/components/settings/SheetCatalogSettingsPanel.vue:90`（内嵌 `<TemplateBar :catalog="catalog" hide-conflict />`）
- `web/tests/e2e/extensions-settings.spec.ts:910/921/960/979/1124/1153`（目录面板保存按钮断言）、`:1147-1151`（只读禁用断言）

**事实：**

Task 6 修改 `TemplateBar.vue` 会同时改变设置中心内的同一组件行为，但 Task 6 的回归命令只列 `sheet-catalog.spec.ts` 与 `sheet-catalog-visual-evidence.spec.ts`，未包含 `extensions-settings.spec.ts`。

**建议：**

Task 6 的回归命令补入 `extensions-settings.spec.ts`（或把 TemplateBar 改动前置为 Task 5 的前置步骤）；并补一句固定裁决：设置子视图内同一组件继续沿用模板级徽标，而过滤文本框保持字段级提示（SPEC-DM-015 §6 对扩展配置判为字段级）。

### F7（重要）：Task 8 文档范围既过宽（含占位符），且审查时与未提交文档基线重叠

**位置：**

- 计划 Task 8 文件清单与 Step 1/Step 3
- 现有对齐条款：`SPEC-DM-009:112`、`SPEC-DM-010:92-101`、`SPEC-DM-011:87`、`SPEC-DM-012:317`
- 工作区状态：审查时上述四份 Spec 与 `ARCH-DM-007`、`GUIDE-DM-001`、`docs/dst-manager/README.md`、`.planning/plans/dst-manager/README.md` 均为未提交修改，`SPEC-DM-015` 与 `PLAN-DM-034` 未跟踪；该批内容随后由 `43f1416` 提交

**事实与建议：**

- 过宽：四份页面 Spec 已在 2026-09-18（`43f1416`）写入与 SPEC-DM-015 的对齐条款，计划只写"修改"却未说明改什么，属占位符。建议改写为"仅在出现已裁决偏差时追加追记段，否则不动这几份 Spec"。
- 冲突风险（已缓解，仍需在实施前确认工作区干净）：审查时文档与计划同处一个未提交工作区，Task 8 的改动容易与正在进行的工作线互相覆盖；该批内容现已提交为 `43f1416`，Step 0 的 `git status` 检查应从"记录用户已有改动"扩展为"确认文档基线已提交、工作区无其它未提交文档改动后再开工"（AGENTS.md 亦要求不得擅自处理用户已有改动）。
- 遗漏：Task 8 未提 `docs/dst-manager/specs/README.md` / `docs/dst-manager/README.md` 的索引同步（若 SPEC-DM-015 状态变化），而 AGENTS.md 要求新增/作废正式文档时同步索引。

### F8（重要）：缺少令牌约束说明，会撞上 `check:ui` 的"新增即失败"棘轮

**位置：**

- 计划 Task 1 Step 2（"可能修改 `tokens.css`"）、Task 2/3/6 的"琥珀语义令牌"
- `web/src/styles/tokens.css:55-56`、`:157-158`（仅 `--color-warning`、`--color-warning-bg` 与 `--color-danger`、`--color-danger-bg`，**无** warning 边框令牌）
- `web/scripts/check-ui-contracts.mjs`（`undefined-css-variable` 等规则按"已知债务基线 + 新增即失败"棘轮）

**建议：**

计划内写明：琥珀边框用 `var(--color-warning)`、底色用 `var(--color-warning-bg)`；若确需新令牌，必须同在 `tokens.css` 定义并跑 `check:ui`。另建议每个代码任务收尾各跑一次 `check:ui`，不要全部压到 Task 8。

### F9（重要）：Task 4 的状态文案二选一未裁决

**位置：**

计划 Task 4 Step 2（"clean 为'无修改可保存'或'已保存'"）。

**建议：**

在计划内裁决单一键名（复用 `settings.saved` 或新增 `settings.noChanges`），否则实施者与验证者的断言会对不上；SPEC-DM-015 §6.1 允许两者，但计划必须给出唯一裁决。

## 未验证与待裁决

1. **未执行任何验证命令**：本审查为静态核对，`test:unit`、`test:e2e`、`check:i18n`、`check:ui`、`build` 均未运行，F1–F9 之外的行为风险仍未覆盖。
2. **G8/G9 环境**：计划 Task 8 要求的同状态成对截图与真实 Windows 桌面壳 100/125/150/200% 缩放验收（GUIDE-DM-001 G8/G9）引用正确，本审查无法确认执行环境是否具备。
3. **证据资产**：`.planning/memos/dst-manager/assets/PLAN-DM-034/` 符合既有目录约定，但计划中"经批准的证据图片（如需长期保留）"为条件式表述，建议改为明确清单。
4. **关键路径**：全量 `test:e2e`（30+ spec、`workers:4`、已知偶发 flaky）只在 Task 8 跑一次，建议在 Task 5/6 后各跑目标 spec 以缩短反馈环。

## 后续动作

- 本备忘不修改 PLAN-DM-034；是否按 F1–F9 回填计划由计划归属方决定。
- 回填范围建议限定为 PLAN-DM-034 单个文件，并在根 `changelog.md` 追加记录；四份页面 Spec 与 ARCH/GUIDE 的既有改动已随 `43f1416` 提交，不属于本备忘的处理范围。
