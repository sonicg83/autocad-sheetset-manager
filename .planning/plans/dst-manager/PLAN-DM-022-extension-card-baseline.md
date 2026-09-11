---
id: PLAN-DM-022
title: 扩展卡片基线与布尔开关统一下沉
status: proposed
document_kind: plan
owners:
  - dst-manager
created: 2026-09-10
updated: 2026-09-10
related:
  - ARCH-DM-006
  - SPEC-DM-006
  - SPEC-DM-011
  - PLAN-DM-019
  - PLAN-DM-020
---

# 扩展卡片基线与布尔开关统一下沉实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐条执行。步骤用 `- [ ]` 复选语法跟踪。

**Goal:** 把已冻结的扩展卡片基线（SPEC-DM-011 SC-16）落成生产实现——单列卡片承载四层信息、条目 ≥6 按 `enabled` 分段——并把布尔状态控件统一为同一个滑动开关（扩展开关与常规配置 bool 字段同形态）。

**Architecture:** 只动 `web/src/components/settings/` 一层，不改后端与 API 契约：新增两个纯呈现组件（`BooleanSwitch.vue` 承载唯一开关视觉语言、`ExtensionCard.vue` 承载四层信息），`ExtensionsSection.vue` 退化为"取数 + 分段 + 列表语义"的组合层，`SettingsFormRow.vue` 的 bool 分支改为复用 `BooleanSwitch.vue`。`SettingsDialog.vue` 只做一处选择器适配（`focusExtensionSwitch` 改按 `[role="switch"]` 定位），**不再增长**。

**Tech Stack:** Vue 3 + TypeScript、vue-i18n、Vite、Playwright（本仓库无组件级单测依赖，UI 验证一律走 e2e）、vitest（仅语言包/纯逻辑）。

**Spec:** [SPEC-DM-011](../../../docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md)（SC-16 与 §3.3 卡片基线，UI 权威 + 冻结件）· [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md)（§6.2 模态原语 / §6.3 布尔控件规范 / 令牌）· [ARCH-DM-006](../../../docs/dst-manager/architecture/ARCH-DM-006-builtin-extension-platform.md)（§4.1 固定索引 / §7 页面入口 / §8 设置归属）

## Global Constraints

- 文件一律 UTF-8；注释、文档与 commit message 用简体中文，commit 动词开头（AGENTS.md）。
- 只用 SPEC-DM-006 令牌，**不新增全局 CSS 规则**（SPEC-DM-011 §5）：开关与卡片的样式写在组件 `<style scoped>` 内。
- 单源文件约 500 行软上限：`SettingsDialog.vue` 已 535 行（待办 `.planning/todos/dst-manager/2026-09-10-settings-dialog-file-split.md`）——**本计划不允许它增长**；卡片与开关一律落在新组件内。
- 语言包键中英必须对称（`npm run check:i18n`）：本计划只新增 `settings.extensions.diagnosticCode`（en-US 同步）；分组标题与卡片状态文字共用 `stateOn/stateOff` 的同一措辞，**不另造同义键**（如后续确实需要区分，再单独拆键并同步 Spec）。
- **不改**任何后端代码、API 契约、序列化字段或 `web/src/api/**`；`GET /api/extensions` 已含 `description_key`/`error_code`，无须扩展契约。
- 既有契约不得破坏：`jumpToError` 依赖 `[data-key="<key>"]` 可聚焦；`SettingsDialog.focusExtensionSwitch` 依赖行容器 `[data-extension-id]`；开关可访问名沿用「启用 {name}」/「停用 {name}」；可见状态文字对辅助技术隐藏（`aria-hidden`）。
- 扩展是否启用只以服务端 `enabled` 为准，**不得**由 `status` 反推开关方向；「已启用 + 启动失败」是合法组合，必须能同时呈现。
- 不引入动画以外的新交互：滑动过渡遵循 `prefers-reduced-motion: reduce`（关闭过渡）。
- e2e 只能用 `web/tests/e2e/serve_backend.py` 装配的真实后端（`DST_MANAGER_SETTINGS_PATH` 隔离）；`/api/extensions` 必须 mock（真实后端会写用户 `.dst-manager-data/dst-manager.db` 的 `extension_states`）。
- **除 `settings-dialog.spec.ts` 以外，任何 e2e 文件不得保存设置**（它串行共享同一配置文件，是本仓库既有约定）；本计划的 bool 用例追加在该文件末尾且不落盘。
- 验证命令（仓库根 `C:\Users\sonic\autocad-sheetset`）：`uv run ruff check .`、`uv run pytest -o addopts="" -q`、`web` 下 `npm run check:i18n`、`npx vue-tsc -b`、`npm run build`、`npx playwright test`。

## 追踪矩阵（G6 依据）

| ID | 要求（来源） | 实施任务 | 自动测试 | 设计 QA | 真实验收 |
| --- | --- | --- | --- | --- | --- |
| SC-16 语义角色 | 卡片不可点击、不导航，唯一交互是开关（SPEC-DM-011 §3.3） | 任务 2 | `extensions-settings.spec.ts` 新增用例 | G8 截图 | — |
| SC-16 四层信息 | 名称版本 / 描述 / 状态徽标 + 诊断码 / 开关（同上） | 任务 2 | 同上 | G8 截图 | — |
| SC-16 增长机制 | 单列 + 面板滚动；≥6 条按 `enabled` 分段（同上） | 任务 3 | `extensions-settings.spec.ts` 新增阈值用例 | G8 截图 | — |
| SC-16 统一开关 | 布尔状态控件统一为滑动开关（SPEC-DM-006 §6.3） | 任务 1 | `settings-dialog.spec.ts` 追加用例 | G8 截图 `g4-12` 对照 | — |
| SC-15 非回归 | 停用不关窗、闸门叠于设置窗口之上、焦点归还开关（SPEC-DM-011 SC-15） | 任务 2、3 | `extensions-settings.spec.ts` 既有 7 例必须保持全绿 | — | — |
| SC-03 / SC-06 非回归 | 动态渲染与即时校验：bool 字段仍走编辑缓冲、保存前不落盘、错误聚焦可达 | 任务 1 | `settings-dialog.spec.ts` 全文件（串行基线） | — | — |
| 证据与门禁 | G8 生产同状态截图 + `SPEC-DM-011` §8/§9 更新 | 任务 4 | 新证据 spec | G8 比对 | G9 手工 |

## 交付前须知的现状（读代码时的事实）

- `ExtensionsSection.vue`（89 行）现为单行列表：`.ext-row > .ext-info + .ext-control`，开关是内联 `<button class="switch" role="switch">`；`.ext-state` 为可见状态文字。
- `SettingsFormRow.vue` 的 bool 分支现为原生 checkbox：`<span class="switch"><input type="checkbox" role="switch" :data-key>` + `.f-hint` 文案 `settings.row.on/off`；处理器 `onBoolInput(event)` 读 `event.target.checked`。
- `SettingsDialog.vue` 的 `focusExtensionSwitch(extensionId)` 按 `Array.from(dialog.querySelectorAll("[data-extension-id]"))` 找行，再 `row.querySelector(".switch")` 聚焦——**本计划实施后 `.switch` 仍是开关根按钮的类名**（由 `BooleanSwitch` 保留），故该方法可不动；任务 1 附带一条断言钉子即可。
- `settings-dialog.spec.ts` 文件头 `test.describe.configure({mode:"serial"})`，用例之间共享同一配置文件（例如「恢复继承」用例依赖前一例已写入 900）。
- 本仓库 `web/package.json` 无 `@vue/test-utils`/`jsdom`/`happy-dom`：**不要**为组件写单测，一律 e2e。

---

### Task 1: `BooleanSwitch.vue` 统一滑动开关，并让 `SettingsFormRow.vue` 的 bool 字段下沉

**Files:**
- Create: `web/src/components/settings/BooleanSwitch.vue`
- Modify: `web/src/components/settings/SettingsFormRow.vue`（bool 分支与其处理器）
- Modify: `web/src/i18n/locales/zh-CN/settings.ts`、`web/src/i18n/locales/en-US/settings.ts`（仅当需要新键；本任务预计不需要）
- Test: `web/tests/e2e/settings-dialog.spec.ts`（追加到文件末尾）

**Interfaces:**
- Produces: `BooleanSwitch` —— props `{checked:boolean; disabled?:boolean; label:string; dataKey?:string; inputId?:string}`，emits `change:[boolean]`；根元素为 `button.switch[role="switch"]`，内部 `span.switch-thumb`。**不渲染可见状态文字**：冻结件里两处的文字位置不同（扩展开关文字在左、bool 字段文字在右），故文字一律由调用方布局（卡片用 `.switch-state`，表单行沿用既有 `.f-hint`）。
- Consumes: 无。

- [ ] **Step 1: 写失败测试（追加到 `settings-dialog.spec.ts` 末尾）**

```ts
// 布尔状态控件统一为滑动开关（SPEC-DM-006 §6.3 / SPEC-DM-011 §3.3）。
// 追加在文件末尾且**不落盘**：本文件串行共享同一配置文件，保存会污染后续基线。
test("布尔字段是滑动开关：role=switch + aria-checked + 可见状态文字，且仍走保存缓冲", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  const toggle = page.getByRole("switch", {name: "图纸编号追加后缀"});
  await expect(toggle).toBeVisible();
  // 初始为快照值 true；可见状态文字在开关右侧（与冻结件 g4-12 一致）
  // 注意必须限定 .bool-line：行内 .f-foot 里还有一个空的 .f-hint，直接取 .f-hint 会多元素命中
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await expect(page.locator('[data-field="enable_add_number_suffix"] .bool-line .f-hint')).toHaveText("开启");
  // 缓冲语义：点击后进入编辑缓冲（保存按钮点亮），但未保存不落库
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(page.locator('[data-field="enable_add_number_suffix"] .bool-line .f-hint')).toHaveText("关闭");
  await expect(page.getByRole("button", {name: "保存"})).toBeEnabled();
  // 放弃修改并关闭：回到快照值，不留持久化痕迹
  await page.keyboard.press("Escape");
  await page.locator('[role="dialog"][aria-modal="true"]').getByRole("button", {name: "放弃修改并关闭"}).click();
  await expect(page.locator('dialog[aria-labelledby="settings-title"]')).toBeHidden();
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  await expect(page.getByRole("switch", {name: "图纸编号追加后缀"})).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");
});
```

- [ ] **Step 2: 运行红灯**

Run: `npx playwright test tests/e2e/settings-dialog.spec.ts -g "布尔字段是滑动开关" --reporter=line --retries=0`
Expected: FAIL —— 原生 checkbox 虽已带 `role="switch"`（可访问名可解析），但**不写** `aria-checked` 属性（浏览器不把 checked 属性化为该 ARIA 属性）→ `toHaveAttribute("aria-checked", "true")` 失败；红即成立。

- [ ] **Step 3: 新建 `web/src/components/settings/BooleanSwitch.vue`**

```vue
<script setup lang="ts">
// 布尔状态控件唯一视觉语言（SPEC-DM-006 §6.3 / SPEC-DM-011 §3.3）：
// 「点击即落库的启停开关」与「随表单保存的布尔字段」共用本组件，语义差异由
// 调用方文案与"保存"按钮是否点亮传达，不由控件形态区分。
// 根元素是 button[role=switch]：Space/Enter 原生可切换，方向由 aria-checked 承担。
// 不渲染可见状态文字：冻结件中扩展开关的文字在左、bool 字段的文字在右，
// 文字由调用方布局（避免为一个组件引入两种内部顺序）。
// dataKey/inputId 保持既有契约：错误跳转依赖 [data-key] 可聚焦、表单 label 依赖 :for。
defineProps<{
  checked: boolean;
  disabled?: boolean;
  label: string;        // 可访问名（调用方本地化后传入）
  dataKey?: string;     // 写入根按钮的 [data-key]
  inputId?: string;     // 写入根按钮的 id，供 <label for> 关联
}>();
const emit = defineEmits<{change: [boolean]}>();
</script>
<template>
  <button
    :id="inputId" type="button" class="switch" role="switch"
    :data-key="dataKey" :aria-checked="checked" :aria-label="label" :disabled="disabled === true"
    @click="emit('change', !checked)"
  ><span class="switch-thumb" aria-hidden="true"></span></button>
</template>
<style scoped>
.switch{position:relative;flex:none;width:44px;height:24px;padding:0;border:1px solid var(--color-border-strong);border-radius:var(--radius-full);background:var(--color-bg-muted);cursor:pointer;transition:background-color .15s ease,border-color .15s ease}
.switch[aria-checked="true"]{background:var(--color-accent);border-color:var(--color-accent)}
.switch:disabled{cursor:not-allowed}
.switch-thumb{position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:var(--radius-full);background:var(--color-bg-surface);box-shadow:var(--shadow-1);transition:transform .15s ease}
.switch[aria-checked="true"] .switch-thumb{transform:translateX(20px)}
@media (prefers-reduced-motion:reduce){.switch,.switch-thumb{transition:none}}
</style>
```

- [ ] **Step 4: `SettingsFormRow.vue` 的 bool 分支改为复用（保持 `data-key`、`disabled`、label 关联与 `commit` 归一化）**

模板：把

```vue
      <span v-else-if="item.control==='bool'" class="switch">
        <input :id="`settings-input-${item.key}`" type="checkbox" role="switch" :data-key="item.key" :checked="Boolean(shown)" :disabled="disabled" @change="onBoolInput">
        <span class="f-hint">{{shown?t("settings.row.on"):t("settings.row.off")}}</span>
      </span>
```

替换为

```vue
      <span v-else-if="item.control==='bool'" class="bool-line">
        <BooleanSwitch
          :checked="Boolean(shown)" :disabled="disabled" :label="label"
          :data-key="item.key" :input-id="`settings-input-${item.key}`"
          @change="onBoolChange"
        />
        <span class="f-hint">{{shown?t("settings.row.on"):t("settings.row.off")}}</span>
      </span>
```

脚本：`import BooleanSwitch from "./BooleanSwitch.vue";`，并把事件型处理器改为值型

```ts
// 滑动开关直接给出目标值（不再是 checkbox 的 change 事件）
function onBoolChange(value:boolean){commit(value)}
```

样式：删除 `SettingsFormRow.vue` 中已无用的 `input[type="checkbox"]{...}` 规则，并把原 `.switch{display:inline-flex;align-items:center;gap:var(--space-2);padding-top:var(--space-2)}` 改名为 `.bool-line{...}`（`.switch` 类名现在属于 `BooleanSwitch` 的按钮，`SettingsDialog.focusExtensionSwitch` 依赖它，不得占用）。

- [ ] **Step 5: 运行绿灯 + 语言包与类型门禁**

Run: `npx playwright test tests/e2e/settings-dialog.spec.ts --reporter=line --retries=0`
Expected: PASS（全文件，含既有串行基线用例）
Run: `npm run check:i18n && npx vue-tsc -b --pretty false`
Expected: `867 键 / 9 域对称`；无类型错误
Run: `npx playwright test tests/e2e/extensions-settings.spec.ts --reporter=line --retries=0`
Expected: PASS（7 例；证明 `.switch` 类名与 `focusExtensionSwitch` 契约未破）

- [ ] **Step 6: 提交**

```bash
git add web/src/components/settings/BooleanSwitch.vue web/src/components/settings/SettingsFormRow.vue web/tests/e2e/settings-dialog.spec.ts
git commit -m "统一设置中心布尔状态控件为滑动开关"
```

---

### Task 2: `ExtensionCard.vue` 承载四层信息，卡片不可点击

**Files:**
- Create: `web/src/components/settings/ExtensionCard.vue`
- Modify: `web/src/components/settings/ExtensionsSection.vue`（行渲染改为卡片，本任务**不**做分段）
- Modify: `web/src/i18n/locales/zh-CN/settings.ts`、`web/src/i18n/locales/en-US/settings.ts`（新增 `extensions.diagnosticCode`）
- Test: `web/tests/e2e/extensions-settings.spec.ts`

**Interfaces:**
- Consumes: `BooleanSwitch`（任务 1）——`{checked,disabled,label,dataKey}` + `change`（可见状态文字由本卡片自己渲染在开关左侧）。
- Produces: `ExtensionCard` —— props `{extension:ExtensionSummary; busy:boolean}`，emits `toggle:[extensionId:string, enabled:boolean]`；根元素 `li.ext-card[data-extension-id]`。

- [ ] **Step 1: 写失败测试（`extensions-settings.spec.ts` 追加）**

```ts
test("SC-16 卡片四层信息与不可点击：唯一可聚焦元素是开关", async ({page}) => {
  const ext = await installExtensions(page, [extensionSummary({status: "FAILED", enabled: true, error_code: "EXTENSION_START_FAILED"})]);
  await openWorkspace(page);
  await openExtensionsSection(page);

  const card = page.locator('[data-extension-id="dst-manager.sheet-catalog"]');
  // 四层：名称 + 描述（description_key）/ 版本 / 状态徽标 + 诊断码 / 开关与状态文字
  await expect(card.getByText("图纸目录", {exact: true})).toBeVisible();
  await expect(card.getByText("从当前工作区快照生成可配置的图纸目录表，并导出为 XLSX 文件")).toBeVisible();
  await expect(card.getByText("v0.1.0")).toBeVisible();
  await expect(card.locator(".badge", {hasText: "启动失败"})).toBeVisible();
  await expect(card.getByText("诊断码 EXTENSION_START_FAILED")).toBeVisible();
  // 「已启用 + 启动失败」必须同时成立：开关在开位，状态文字为已启用
  await expect(card.getByRole("switch", {name: "停用 图纸目录"})).toHaveAttribute("aria-checked", "true");
  await expect(card.locator(".switch-state")).toHaveText("已启用");
  // 卡片不可点击：内部唯一可聚焦元素是开关（无链接、无按钮角色、无 tabindex 容器）
  const focusables = await card.evaluate(el => Array.from(el.querySelectorAll("[tabindex],a[href],button,[role=button],[role=link]")).map(n => n.tagName + (n.getAttribute("role") ? `[${n.getAttribute("role")}]` : "")));
  expect(focusables).toEqual(["BUTTON[switch]"]);
  // 状态徽标与开关方向来自不同权威：FAILED 不改变开关方向（不由 status 反推）
  expect(ext.patchBodies).toHaveLength(0);
});
```

- [ ] **Step 2: 运行红灯**

Run: `npx playwright test tests/e2e/extensions-settings.spec.ts -g "卡片四层信息与不可点击" --reporter=line --retries=0`
Expected: FAIL —— 描述文案与 `诊断码 …` 尚未渲染（现列表只有名称、`v{version} · {status}`、开关）；`.switch-state` 类名不存在（现为 `.ext-state`）。

- [ ] **Step 3: 新增语言包键（中英同步）**

`zh-CN/settings.ts` 的 `extensions` 小节追加：

```ts
    // 诊断码前缀：与诊断横幅同一措辞（settings.diagnostics.* 的「（诊断码 {code}）」保持独立，不合并）
    diagnosticCode: "诊断码 {code}",
```

`en-US/settings.ts` 对称追加：

```ts
    diagnosticCode: "Code {code}",
```

- [ ] **Step 4: 新建 `web/src/components/settings/ExtensionCard.vue`**

```vue
<script setup lang="ts">
// 扩展卡片（SPEC-DM-011 §3.3 / SC-16）。纯呈现：状态容器 + 唯一开关，
// 不可点击、不导航——卡片上不得长出扩展自身设置的入口（后者归扩展页面，ARCH-DM-006 §8）。
// 四层信息固定顺序：①名称+版本 ②描述 ③状态徽标+诊断码 ④开关与可见状态文字。
// 开关方向只取服务端 enabled；status 只决定徽标色调与诊断码，"已启用 + 启动失败"
// 是合法组合，不得互相否认（ARCH-DM-006 §5）。
import {computed} from "vue";
import {useI18n} from "vue-i18n";
import type {ExtensionSummary} from "../../api/contracts";
import BooleanSwitch from "./BooleanSwitch.vue";

const props = defineProps<{extension: ExtensionSummary; busy: boolean}>();
const emit = defineEmits<{toggle: [extensionId: string, enabled: boolean]}>();
const {t} = useI18n();

const name = computed(() => t(props.extension.name_key));
const enabled = computed(() => props.extension.enabled);
// 徽标色调：可用=成功、启动失败=危险、不兼容/等待依赖=警告，其余（已停用/过渡态）=弱化
const tone = computed(() => {
  switch (props.extension.status) {
    case "AVAILABLE": return "success";
    case "FAILED": return "danger";
    case "INCOMPATIBLE":
    case "WAITING_DEPENDENCY": return "warning";
    default: return "muted";
  }
});
// 可见状态文字与分组标题共用措辞（同一状态不出现两套说法）；位置在开关左侧，
// 与冻结件 g4-07～g4-11 一致（控件本身不渲染文字，由本卡片布局）
const stateText = computed(() => enabled.value ? t("settings.extensions.stateOn") : t("settings.extensions.stateOff"));
const switchLabel = computed(() => enabled.value
  ? t("settings.extensions.disableNamed", {name: name.value})
  : t("settings.extensions.enableNamed", {name: name.value}));
</script>
<template>
  <li class="ext-card" :data-extension-id="extension.extension_id">
    <div class="ext-main">
      <span class="ext-name">{{ name }}</span>
      <span class="ext-desc">{{ t(extension.description_key) }}</span>
      <span class="ext-meta">
        <span class="badge muted">v{{ extension.version }}</span>
        <span class="badge" :class="tone">{{ t(`extensions.status.${extension.status}`) }}</span>
        <!-- 诊断码原样显示稳定枚举名，不翻译、不拼接后端文本（ARCH-DM-006 §4.3） -->
        <span v-if="extension.error_code" class="ext-diag">{{ t("settings.extensions.diagnosticCode", {code: extension.error_code}) }}</span>
      </span>
    </div>
    <div class="ext-side">
      <span class="switch-state" :class="{on:enabled}" aria-hidden="true">{{ stateText }}</span>
      <BooleanSwitch
        :checked="enabled" :disabled="busy" :label="switchLabel"
        :data-key="extension.extension_id"
        @change="value => emit('toggle', extension.extension_id, value)"
      />
    </div>
  </li>
</template>
<style scoped>
.ext-card{display:flex;align-items:flex-start;gap:var(--space-3);padding:var(--space-3) var(--space-4);border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-bg-surface)}
.ext-main{display:flex;flex-direction:column;gap:var(--space-1);min-width:0;flex:1}
.ext-name{color:var(--color-text-primary);font-size:14px;font-weight:500;overflow-wrap:anywhere}
.ext-desc{color:var(--color-text-secondary);font-size:12px;line-height:1.7}
.ext-meta{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;font-size:12px}
.badge{font-size:12px;padding:2px 10px;border-radius:var(--radius-full)}
.badge.muted{background:var(--color-bg-muted);color:var(--color-text-secondary)}
.badge.success{background:var(--color-success-bg);color:var(--color-success)}
.badge.warning{background:var(--color-warning-bg);color:var(--color-warning)}
.badge.danger{background:var(--color-danger-bg);color:var(--color-danger)}
.ext-diag{color:var(--color-text-muted)}
.ext-side{display:flex;align-items:center;gap:var(--space-2);flex:none;padding-top:2px}
.switch-state{font-size:12px;color:var(--color-text-muted)}
.switch-state.on{color:var(--color-success)}
</style>
```

- [ ] **Step 5: `ExtensionsSection.vue` 改用卡片渲染（本任务保持单一列表）**

模板中 `ul.ext-list` 内改为

```vue
      <ExtensionCard
        v-for="extension in list" :key="extension.extension_id"
        :extension="extension" :busy="busy" @toggle="(id, value) => $emit('toggle', id, value)"
      />
```

（`ul.ext-list > li` 语义由 `ExtensionCard` 的根 `li` 承担；本任务删除分区内已迁走的 `.ext-row`/`.ext-info`/`.ext-control`/`.ext-state`/旧 `.switch` 样式与内联开关标记；`busy` 继续由分区透传给卡片用于禁用开关。）

- [ ] **Step 6: 运行绿灯 + 非回归**

Run: `npx playwright test tests/e2e/extensions-settings.spec.ts --reporter=line --retries=0`
Expected: PASS（既有 7 例 + 本任务 1 例；如既有用例断言 `getByRole("switch", …)` 的可访问名，语义不变）
Run: `npm run check:i18n && npx vue-tsc -b --pretty false`
Expected: 键对称（新增 1 键 → 868）+ 无类型错误

- [ ] **Step 7: 提交**

```bash
git add web/src/components/settings/ExtensionCard.vue web/src/components/settings/ExtensionsSection.vue web/src/i18n/locales/zh-CN/settings.ts web/src/i18n/locales/en-US/settings.ts web/tests/e2e/extensions-settings.spec.ts
git commit -m "下沉扩展卡片承接四层信息"
```

---

### Task 3: `ExtensionsSection.vue` 按 `enabled` 分段（阈值 6 条）

**Files:**
- Modify: `web/src/components/settings/ExtensionsSection.vue`
- Test: `web/tests/e2e/extensions-settings.spec.ts`

**Interfaces:**
- Consumes: `ExtensionCard`（任务 2）。
- Produces: 无（分段是分区内部的呈现细节，不改任何对外契约）。

- [ ] **Step 1: 写失败测试（阈值两侧各一条）**

```ts
// 扩展清单缩放（SPEC-DM-011 §3.3）：<6 条保持单列不分段；≥6 条按 enabled 分两段。
// 两条用例各自独立装数据，不依赖执行顺序。
test("SC-16 分段阈值下侧：5 条不分段", async ({page}) => {
  await installExtensions(page, [1, 2, 3, 4, 5].map((n) => extensionSummary({
    extension_id: `demo.ext-${n}`, enabled: n % 2 === 1, status: n % 2 === 1 ? "AVAILABLE" : "DISABLED",
  })));
  await page.goto("/");
  await openExtensionsSection(page);
  await expect(page.locator(".ext-card")).toHaveCount(5);
  await expect(page.locator(".group-title")).toHaveCount(0);
});

test("SC-16 分段阈值上侧：6 条分两段且分组键与开关同一权威", async ({page}) => {
  await installExtensions(page, [1, 2, 3, 4, 5, 6].map((n) => extensionSummary({
    extension_id: `demo.ext-${n}`, enabled: n % 2 === 1, status: n % 2 === 1 ? "AVAILABLE" : "DISABLED",
  })));
  await page.goto("/");
  await openExtensionsSection(page);
  await expect(page.locator(".ext-card")).toHaveCount(6);
  await expect(page.locator(".group-title")).toHaveCount(2);
  await expect(page.locator(".group-title").first()).toHaveText("已启用");
  await expect(page.locator(".group-title").last()).toHaveText("已停用");
  // 分组键与开关同一权威：任何一段内不得出现与段名矛盾的开关方向
  await expect(page.locator(".ext-group").first().locator('[aria-checked="false"]')).toHaveCount(0);
  await expect(page.locator(".ext-group").last().locator('[aria-checked="true"]')).toHaveCount(0);
});
```

（`extensionSummary` 默认 `name_key` 为 `extensions.sheetCatalog.name`，六条卡片同名不影响断言：定位一律用 `.ext-card` 计数与 `[aria-checked]`，不用可访问名。）

- [ ] **Step 2: 运行红灯**

Run: `npx playwright test tests/e2e/extensions-settings.spec.ts -g "分段阈值" --reporter=line --retries=0`
Expected: FAIL —— `.group-title` 与 `.ext-group` 尚不存在。

- [ ] **Step 3: 不需要改语言包**

分组标题与卡片状态文字同措辞，直接复用已有键 `settings.extensions.stateOn/stateOff`（已在中英两份语言包中）；不新增 `groupOn/groupOff`，避免同义键分叉。若实施中发现确需区分措辞，停手先改 `SPEC-DM-011` §3.3 再回来加键。

- [ ] **Step 4: 实现分段渲染**（先在 `<script setup>` 的 vue import 里补 `computed`）

```ts
// 增长机制的唯一预设答案（SPEC-DM-011 §3.3）：单列 + 面板滚动；条目 ≥6 条按
// enabled 分「已启用 / 已停用」两段——分组键必须与开关同一权威，否则同一卡片
// 会在两段之间跳变。搜索/筛选/排序/分页/多列网格是明确的非目标。
const GROUP_THRESHOLD = 6;
const groups = computed(() => {
  if (props.list.length < GROUP_THRESHOLD) return [{key: "", title: "", items: props.list}];
  return [
    {key: "on", title: t("settings.extensions.stateOn"), items: props.list.filter(item => item.enabled)},
    {key: "off", title: t("settings.extensions.stateOff"), items: props.list.filter(item => !item.enabled)},
  ].filter(group => group.items.length > 0);
});
```

模板（分组标题复用 `.group-title` 视觉，空组不渲染）：

```vue
    <div v-for="group in groups" :key="group.key" class="ext-group">
      <div v-if="group.title" class="group-title">{{ group.title }}</div>
      <ul class="ext-list">
        <ExtensionCard
          v-for="extension in group.items" :key="extension.extension_id"
          :extension="extension" :busy="busy" @toggle="(id, value) => $emit('toggle', id, value)"
        />
      </ul>
    </div>
```

- [ ] **Step 5: 运行绿灯 + 全分区非回归**

Run: `npx playwright test tests/e2e/extensions-settings.spec.ts --reporter=line --retries=0`
Expected: PASS（含既有「停用不关窗」「闸门叠在设置窗口之上」等 SC-15 用例）
Run: `npx playwright test tests/e2e/sheet-catalog.spec.ts tests/e2e/extensions-navigation.spec.ts --reporter=line --retries=0`
Expected: PASS（目录页三选一与标签收敛未受影响）

- [ ] **Step 6: 提交**

```bash
git add web/src/components/settings/ExtensionsSection.vue web/tests/e2e/extensions-settings.spec.ts
git commit -m "为扩展分区补按启用状态分段的增长机制"
```

---

### Task 4: G8 生产同状态证据与文档收尾

**Files:**
- Create: `web/tests/e2e/settings-extensions-production-evidence.spec.ts`
- Create: `web/tests/e2e/fixtures/extensions.ts`（从 `extensions-settings.spec.ts` 提取 `extensionSummary`/`installExtensions`）
- Modify: `web/tests/e2e/extensions-settings.spec.ts`（改为 import 提取后的夹具，纯搬移不改行为）
- Create: `docs/dst-manager/specs/assets/SPEC-DM-011/production/`（G8 时从 `test-results/` 复制，与 `g4-*` 同名对应）
- Modify: `docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md`（§8 G8 行、§9 追踪、§7 证据位置说明）
- Modify: `changelog.md`

**Interfaces:**
- Consumes: 任务 1~3 的生产实现。
- Produces: G8 比对用的生产截图集合（`g8-ext-01…04`）。

- [ ] **Step 1: 写证据 spec（复用既有 mock 与夹具，禁止保存设置）**

```ts
// 扩展卡片 G8 生产同状态证据（GUIDE-DM-001 G8 / SPEC-DM-011 §9）。
// 真实后端 + mock /api/extensions（真实 PATCH 会写用户数据库）；只打开设置对话框
// 与切换分区，不保存任何设置（settings-dialog.spec.ts 串行共享配置文件）。
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {openSettingsDialog} from "./fixtures/settings";
import {extensionSummary} from "./fixtures/extensions";

async function shoot(page: Page, info: TestInfo, name: string): Promise<void> {
  const file = info.outputPath(name);
  await page.screenshot({path: file, animations: "disabled"});
  await info.attach(name, {path: file, contentType: "image/png"});
}

test("g8-ext-01 扩展分区·单条（浅色·1280×720）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  await page.route("**/api/extensions", route => route.fulfill({json: [extensionSummary()]}));
  await page.goto("/");
  await openSettingsDialog(page);
  await page.getByRole("tab", {name: "扩展"}).click();
  await expect(page.locator(".ext-card")).toHaveCount(1);
  await shoot(page, info, "g8-ext-01-single-light.png");
});
// 其余三例同构：四条多状态（含 FAILED+enabled）、八条分段（滚动到分段边界）、深色 900×600
```

> 实施提示：`extensionSummary` 与 `installExtensions` 目前在 `extensions-settings.spec.ts` 内私有定义，**先把它们提取到 `web/tests/e2e/fixtures/extensions.ts` 并在原文件改 import**（纯搬移，不改行为），再写本 spec；不要复制粘贴两份 mock。

- [ ] **Step 2: 运行并产出证据**

Run: `npx playwright test tests/e2e/settings-extensions-production-evidence.spec.ts --reporter=line --retries=0`
Expected: PASS，`test-results/` 下生成 4 张 `g8-ext-*.png`

- [ ] **Step 3: 复制为标准证据并逐张比对冻结件**

```powershell
New-Item -ItemType Directory -Force docs/dst-manager/specs/assets/SPEC-DM-011/production
Get-ChildItem -Recurse web/test-results -Filter 'g8-ext-*.png' | Copy-Item -Destination docs/dst-manager/specs/assets/SPEC-DM-011/production
```

逐张与 §7 的 `g4-07…g4-11` 对比，把差异按"缺陷（须修）/ 有意偏差（须记）"分类；差异结论写入 `SPEC-DM-011` §8 G8 行的证据列（有不可忽略差异时另立 memo，与 MEMO-DM-024 同格式）。

- [ ] **Step 4: 更新 Spec 与变更记录**

- `SPEC-DM-011` §8：G8 行从"通过（覆盖 SC-01～SC-14）"改为覆盖 SC-15/SC-16 的新结论（含新证据路径与偏差裁决）；§9 各条打勾；
- `SPEC-DM-011` §7：`production/` 证据位置与文件名补全（原 `production/` 缺失说明可随之收敛）；
- `changelog.md`：追加一条（改了什么、实际跑了什么命令、结果数字、跳过项与原因）。

- [ ] **Step 5: 全量回归与文档校验**

Run: `uv run ruff check .`
Expected: All checks passed
Run: `uv run pytest -o addopts="" -q`
Expected: exit 0（本计划未改 Python；作为交付基线兜底）
Run（`web`）: `npm run check:i18n && npx vue-tsc -b --pretty false && npm run build && npx playwright test`
Expected: 键对称、构建通过、e2e 全量 0 failed（新增用例计入总数）

- [ ] **Step 6: 提交**

```bash
git add web/tests/e2e/settings-extensions-production-evidence.spec.ts web/tests/e2e/fixtures/extensions.ts docs/dst-manager/specs/assets/SPEC-DM-011/production docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md changelog.md
git commit -m "补扩展卡片 G8 生产证据并收口文档"
```

---

## 批次划分（G7）

| 批次 | 任务 | 可独立验收的边界 | 回退方式 |
| --- | --- | --- | --- |
| 批次 1 | 任务 1 | 常规配置 bool 字段变为滑动开关；既有设置保存/校验/串行基线全绿 | 恢复 `SettingsFormRow.vue` 的 checkbox 分支并删除 `BooleanSwitch.vue`（无其他消费者） |
| 批次 2 | 任务 2、3 | 扩展分区卡片化与分段；SC-15 既有 7 例全绿 | 恢复 `ExtensionsSection.vue` 单行渲染（`ExtensionCard.vue` 变为无引用） |
| 批次 3 | 任务 4 | G8 证据与文档收口 | 证据目录与 Spec 改动可单独回退，不影响前两批代码 |

## 风险与已评估的替代

- **卡片把 `ExtensionsSection.vue` 撑大**：卡片与开关都下沉为独立组件，分区只留"取数 + 分段 + 列表"，预计 ≤120 行，仍在软上限内。若实施时超出，再拆 `ExtensionsGroup.vue`，不得把分段逻辑塞进 `SettingsDialog.vue`。
- **`BooleanSwitch` 同时服务两种语义（即时生效 / 缓冲保存）会误导**：由分区文案（「扩展启停立即生效，不受下方取消影响」）与保存按钮是否点亮承担区分；这是 G3 已裁决项，实施时不得私自让 bool 字段"立即生效"。
- **分段阈值写死为 6**：SPEC-DM-011 §3.3 已写明重启条件是平台具备运行时安装能力；实施时不得引入"可配置阈值"或搜索框。
- **未采纳的替代**（见 SPEC-DM-011 §5 第二次裁决）：多列网格、"失败时可展开诊断 + 重试启动"（需先裁决重试语义）、把 bool 字段保持在原生 checkbox。

## 实际验证

> 执行完成后在此登记：每批次改动的文件与 commit、每道命令的原始结果（含 e2e 总数/通过数/flaky 明细）、任何跳过项与原因、G8 逐张比对结论与偏差裁决。未登记的批次不得标记 `completed`。
