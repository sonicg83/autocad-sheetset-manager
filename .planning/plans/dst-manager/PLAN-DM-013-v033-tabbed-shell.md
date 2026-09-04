---
id: PLAN-DM-013
title: DST Manager v0.3.3 标签化外壳与任务浮层重建实施计划
status: completed
owners:
  - dst-manager
created: 2026-09-04
updated: 2026-09-04
related:
  - SPEC-DM-006
  - SPEC-DM-007
---

# DST Manager v0.3.3 标签化外壳与任务浮层重建实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 依据 [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) 修订后的 §4.1/§4.2，把 `web/` 单页滚动结构重建为**固定标签（① 图纸 / ② 属性 / ③ 修订历史）+ 右缘任务浮层（进度/预览/诊断）+ 全局 ActionDock（含草稿栈浮窗）+ SSE 任务通知 toast** 的标签化外壳，并替换全部原生 `confirm()` 为可访问确认模态。

**Architecture:** 纯前端改造，零后端契约变化。分四步走：①令牌层（§5.1 语义变量 + 双主题）；②确认模态组件化并迁移全部 `confirm()`；③App.vue 状态域拆分到 composables（满足 AGENTS.md 500 行软上限）；④外壳重组（TopBar/TabBar/三视图/任务浮层/ActionDock/toast）。既有 8 个业务组件原样复用迁入新容器，不重写其内部逻辑；演示原型 `docs/dst-manager/mockups/SPEC-DM-006-shell-demo.html` 为交互参照。

**Tech Stack:** Vue 3 + TypeScript + Vite、Playwright（无新依赖）。

**Spec:** `docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md`（§4.1、§4.2、§6.2、§6.6、§6.8、§6.9、§7.1、§7.2 为本次验收依据）；交互原型 `docs/dst-manager/mockups/SPEC-DM-006-shell-demo.html`。

## Global Constraints

- 全程简体中文注释、commit message 与用户文案；标识符保持英文。
- 零后端改动：不修改 `src/`、`migrations/`、`plugins/`；不重新生成 OpenAPI 契约；`web/src/api/schema.d.ts` 保持不动。
- 不改变发布安全流程：预览永远安全；全部正式写入仍绑定 `base_revision_id` + `preview_digest`（`App.vue` 既有 `showPreview`/`execute`/`executeRepair`/`importCsv`/`restoreRevision` 的代次与门禁逻辑原样保留，仅迁移宿主）。
- 界面不得在前端复制后端校验、不得绕过预览与摘要门禁；术语（`clsid`/`vt`/内部 ID）不出现在用户文案。
- `App.vue` 单文件以约 500 行为软上限（AGENTS.md 代码组织契约）；新逻辑优先新建 `composables/`、`layout/`、`views/`、`components/ui/` 模块。
- 令牌（Task 1）落地后，新增/修改的样式一律引用语义 CSS 变量，不得写裸十六进制色值（断点、1px 边框除外）。既有组件内部旧样式允许原样保留，渐进迁移。
- 单字符快捷键（`/`、`?`）本次不引入，故无 SC 2.1.4 关闭/重映射义务；引入时必须同步补齐设置项。
- 每个 task 完成时更新根目录 `changelog.md`（当前日期章节追加）；commit message 简体中文、动词开头。
- 验证基线：`cd web && npm run build && npm run test:e2e`；收尾另跑 `uv run ruff check . && uv run pytest -q` 确认无后端回归（预期全绿且数字与基线一致）。
- e2e 基线：当前 `main.spec.ts` 全绿；每个 task 结束时必须恢复全绿（允许按新交互更新用例，但不得删除覆盖面）。

---

### Task 1: 设计令牌与双主题（SPEC-DM-006 §5.1、§4.1 顶栏主题切换）

**Files:**
- Modify: `web/src/style.css`（文件头部令牌区）
- Create: `web/src/composables/useTheme.ts`
- Modify: `web/src/App.vue`（header 内加主题切换按钮，临时挂载；Task 4 迁入 TopBar）
- Test: `web/tests/e2e/main.spec.ts`（追加用例）

**Interfaces:**
- Consumes: 无。
- Produces: `useTheme(): { theme: Ref<"light"|"dark">; toggleTheme(): void }`（持久化键 `localStorage["dst-manager-theme"]`，写入 `document.documentElement.dataset.theme`）。Task 4 的 TopBar 消费此签名。

- [x] **Step 1: 写失败的 e2e 用例**

`main.spec.ts` 追加（跟随文件内既有用例风格）：

```typescript
test("主题切换写 html data-theme 并持久化",async({page})=>{
  await page.addInitScript(()=>localStorage.setItem("dst-manager-theme","light"));
  await page.goto("/");
  await page.getByRole("button",{name:"切换主题"}).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
});
```

- [x] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e -- -g "主题切换"`
Expected: FAIL（按钮不存在）

- [x] **Step 3: 落地令牌与 composable**

`style.css` 文件头部加入（§5.1 令牌表逐项照抄，浅色默认、`html[data-theme="dark"]` 覆盖）：

```css
:root{
  --color-bg-canvas:#F6F7F9; --color-bg-surface:#FFFFFF; --color-bg-muted:#EEF1F5;
  --color-text-primary:#1A2233; --color-text-secondary:#4A5568; --color-text-muted:#6B7280;
  --color-border-subtle:#E3E8EF; --color-border-strong:#C7D0DB;
  --color-accent:#2F5BE0; --color-accent-hover:#2A50C8; --color-accent-active:#2445AD;
  --color-on-accent:#FFFFFF; --color-focus:#2F5BE0;
  --color-success:#1B7F4B; --color-success-bg:#E7F4EC;
  --color-warning:#946200; --color-warning-bg:#FBF1DB;
  --color-danger:#C2302B; --color-danger-bg:#FBEAE8;
  --color-info:#245FA6; --color-info-bg:#E8F0F9;
  --radius-sm:6px; --radius-md:8px; --radius-lg:12px; --radius-full:9999px;
  --shadow-1:0 1px 2px rgba(16,24,40,.06); --shadow-2:0 4px 12px rgba(16,24,40,.10); --shadow-3:0 12px 32px rgba(16,24,40,.16);
  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-5:24px; --space-6:32px;
}
html[data-theme="dark"]{
  --color-bg-canvas:#10151E; --color-bg-surface:#171E29; --color-bg-muted:#212B39;
  --color-text-primary:#E6EAF2; --color-text-secondary:#AEB8C7; --color-text-muted:#8592A3;
  --color-border-subtle:#2A3444; --color-border-strong:#3B485C;
  --color-accent:#6B8DFF; --color-accent-hover:#7E9CFF; --color-accent-active:#5A7BE8;
  --color-on-accent:#0B1220; --color-focus:#8FAAFF;
  --color-success:#54C98A; --color-success-bg:#12301F;
  --color-warning:#E0B15A; --color-warning-bg:#332712;
  --color-danger:#F0776E; --color-danger-bg:#3A1917;
  --color-info:#7CB0E8; --color-info-bg:#132739;
  --shadow-1:0 1px 2px rgba(0,0,0,.30); --shadow-2:0 4px 12px rgba(0,0,0,.40); --shadow-3:0 12px 32px rgba(0,0,0,.50);
}
```

`composables/useTheme.ts`：

```typescript
import {ref,watch} from "vue";
import type {Ref} from "vue";

type Theme="light"|"dark";
const KEY="dst-manager-theme";

function initial():Theme{
  const saved=localStorage.getItem(KEY);
  return saved==="dark"?"dark":"light";
}

export function useTheme():{theme:Ref<Theme>;toggleTheme:()=>void}{
  const theme=ref<Theme>(initial());
  watch(theme,value=>{document.documentElement.dataset.theme=value;localStorage.setItem(KEY,value)},{immediate:true});
  function toggleTheme(){theme.value=theme.value==="light"?"dark":"light"}
  return {theme,toggleTheme};
}
```

`App.vue` header 内追加（跟随既有压缩单行风格）：`<button type="button" aria-label="切换主题" @click="toggleTheme">◐</button>`，script 引入 `useTheme` 并解构。

- [x] **Step 4: 运行 e2e 与构建确认通过**

Run: `cd web && npm run test:e2e && npm run build`
Expected: PASS（新用例过、既有全绿）

- [x] **Step 5: 更新 changelog 并提交**

```bash
git add web/src/style.css web/src/composables/useTheme.ts web/src/App.vue web/tests/e2e/main.spec.ts changelog.md
git commit -m "落地界面设计令牌与浅深双主题切换"
```

---

### Task 2: 确认模态组件化并替换全部原生 confirm()（SPEC-DM-006 §6.2、§6.9）

**Files:**
- Create: `web/src/components/ui/ConfirmModal.vue`
- Create: `web/src/composables/useConfirm.ts`
- Modify: `web/src/App.vue`（迁移 8 处 `confirm()`：`execute` 414 行、`executeRepair` 492 行、`importCsv` 537 行、`restoreRevision` 461 行、`queueDelete` 338 行、`queueDeleteSubset` 342 行、`reloadAfterDraftConflict` 312 行、`closeWorkspace` 226 行；行号为当前基线，迁移时以内容定位）
- Test: `web/tests/e2e/main.spec.ts`（更新 dialog 相关用例 + 追加勾选门禁用例）

**Interfaces:**
- Consumes: 无。
- Produces: `useConfirm()` 返回 `{ state: ConfirmModalState; confirmAction(options: ConfirmOptions): Promise<boolean>; resolve(value: boolean): void }`；`ConfirmOptions = { title: string; message: string; impactLines?: string[]; confirmText: string; danger?: boolean; requireCheckbox?: boolean; reversibility?: "可撤销"|"不可逆" }`。Task 5 的"确认写入"按钮复用 `confirmAction`。

- [x] **Step 1: 排查并记录待迁移用例**

Run: `grep -n "dialog" web/tests/e2e/main.spec.ts`
记录全部依赖原生 dialog 的用例（已知至少：L110 关闭确认冲刷、L159 删除子集、L421 恢复、L425 修复、L492 关闭确认）。这些用例在 Step 4 统一改为模态交互。

- [x] **Step 2: 写失败的 e2e 用例**

```typescript
test("发布确认模态必须显式勾选后才可提交",async({page})=>{
  // 跟随既有"修复状态展示、写入门禁与确认发布流程"用例的前置 mock，构造预览有效态后：
  await page.getByRole("button",{name:"确认写入"}).click(); // Task 5 前暂为既有发布入口
  const modal=page.getByRole("dialog");
  await expect(modal).toBeVisible();
  await expect(modal.getByText("不可逆")).toBeVisible();
  await expect(modal.getByRole("button",{name:/确认发布/})).toBeDisabled();
  await modal.getByRole("checkbox").check();
  await expect(modal.getByRole("button",{name:/确认发布/})).toBeEnabled();
  await modal.getByRole("button",{name:/确认发布/}).click();
  await expect(modal).toHaveCount(0);
});
```

（本用例中"确认写入"入口在 Task 5 才出现；本 Task 阶段先用既有发布按钮触发同模态，Step 4 落地后统一为可复现的前置步骤，注释注明 Task 5 将更新触发方式。）

- [x] **Step 3: 实现模态与 composable**

`components/ui/ConfirmModal.vue`：

```vue
<script setup lang="ts">
import {watch,ref,nextTick} from "vue";
const props=defineProps<{open:boolean;title:string;message:string;impactLines?:string[];confirmText:string;cancelText?:string;danger?:boolean;requireCheckbox?:boolean;reversibility?:string}>();
const emit=defineEmits<{confirm:[];cancel:[]}>();
const checked=ref(false);const card=ref<HTMLElement|null>(null);const opener=ref<Element|null>(null);
watch(()=>props.open,async open=>{checked.value=false;
  if(open){opener.value=document.activeElement;await nextTick();card.value?.focus();}
  else (opener.value as HTMLElement|null)?.focus?.();});
function onKeydown(e:KeyboardEvent){
  if(e.key==="Escape"){e.stopPropagation();emit("cancel");return}
  if(e.key!=="Tab"||!card.value)return;
  // 焦点困绕：Tab 循环限制在模态内
  const items=[...card.value.querySelectorAll<HTMLElement>("button,input")].filter(el=>!el.hasAttribute("disabled"));
  if(!items.length)return;const first=items[0],last=items[items.length-1];
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
}
</script>
<template>
  <div v-if="open" class="modal-mask" @keydown="onKeydown">
    <div class="modal-card" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1" ref="card">
      <h2>{{title}} <span v-if="reversibility" class="modal-irr" :class="{danger}">{{reversibility}}</span></h2>
      <p class="modal-message">{{message}}</p>
      <ul v-if="impactLines?.length" class="modal-impact"><li v-for="line in impactLines" :key="line" class="mono">{{line}}</li></ul>
      <label v-if="requireCheckbox" class="modal-check"><input type="checkbox" v-model="checked">我已了解本次操作{{reversibility??"不可逆"}}，并已核对受影响内容清单</label>
      <div class="modal-actions">
        <button type="button" @click="emit('cancel')">{{cancelText??"取消"}}</button>
        <button type="button" :class="{danger}" :disabled="Boolean(requireCheckbox)&&!checked" @click="emit('confirm')">{{confirmText}}</button>
      </div>
    </div>
  </div>
</template>
```

（样式类追加进 `style.css`，一律引用 Task 1 令牌：遮罩 `rgba` 允许常量，其余用 `--color-*`。）

`composables/useConfirm.ts`：

```typescript
import {reactive} from "vue";

export type ConfirmOptions={title:string;message:string;impactLines?:string[];confirmText:string;cancelText?:string;danger?:boolean;requireCheckbox?:boolean;reversibility?:string};
type ConfirmModalState=ConfirmOptions&{open:boolean};

export function useConfirm(){
  const state=reactive<ConfirmModalState>({open:false,title:"",message:"",confirmText:"确认"});
  let pending:((value:boolean)=>void)|null=null;
  function confirmAction(options:ConfirmOptions):Promise<boolean>{
    return new Promise(resolve=>{
      pending=resolve;
      Object.assign(state,options,{open:true});
    });
  }
  function resolve(value:boolean){
    state.open=false;pending?.(value);pending=null;
  }
  return {state,confirmAction,resolve};
}
```

`App.vue`：`const {state:confirmState,confirmAction,resolve:resolveConfirm}=useConfirm()`，模板挂 `<ConfirmModal v-bind="confirmState" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />`。8 处迁移模式一致，例如：

```typescript
// 迁移前（execute 内）：
if(!confirm("确认发布？原 DST 和受影响 DWG 将永久备份。"))return;
// 迁移后：
const ok=await confirmAction({title:"确认发布",message:"原 DST 和受影响 DWG 将永久备份。",impactLines:[...受影响清单来源与既有文案一致...],confirmText:"确认发布（原 DST 与受影响 DWG 永久备份）",danger:true,requireCheckbox:true,reversibility:"不可逆"});
if(!ok)return;
```

各处文案原样保留既有 `confirm()` 文本；`queueDelete`/`queueDeleteSubset`/`reloadAfterDraftConflict`/`closeWorkspace` 改为 `async` 函数（模板 `@click` 兼容 Promise）。删除类操作保留"系统不会证明工程外部引用，确认后由用户承担外部影响"声明于 `message`。`queueDelete`（单张图纸）为低风险动作：`danger:false`、无勾选；`queueDeleteSubset`/`closeWorkspace`：`danger:true`；`reloadAfterDraftConflict`：`danger:false`。

- [x] **Step 4: 更新受影响 e2e 用例并验证**

把 Step 1 清单中的 `page.on("dialog")`/`page.once("dialog")` 处理器改为模态交互模式：

```typescript
// 迁移前：page.once("dialog",d=>d.accept());
// 迁移后：
const modal=page.getByRole("dialog");
await modal.getByRole("checkbox").check(); // requireCheckbox 的模态才需要
await modal.getByRole("button",{name:/确定关闭并放弃当前改动|确认发布|确认恢复|确认导入|确认把内存修复发布/}).click();
```

Run: `cd web && npm run test:e2e && npm run build`
Expected: PASS（含新勾选门禁用例）

- [x] **Step 5: 更新 changelog 并提交**

```bash
git add web/src/components/ui/ConfirmModal.vue web/src/composables/useConfirm.ts web/src/App.vue web/src/style.css web/tests/e2e/main.spec.ts changelog.md
git commit -m "发布删除恢复等确认改为应用内可访问模态"
```

---

### Task 3: App.vue 状态域拆分（纯重构，行为零变化）

**Files:**
- Create: `web/src/composables/useJobMonitor.ts`
- Create: `web/src/composables/useRepair.ts`
- Create: `web/src/composables/useRestore.ts`
- Create: `web/src/composables/useCsvImport.ts`
- Modify: `web/src/App.vue`（删除对应状态与函数，改为 composable 调用）

**Interfaces:**
- Consumes: `request`/`ApiError`（`web/src/api/client`）、`Job`/`RepairPreview`/`RestorePreview`/`CsvPreview` 等契约类型（`web/src/api/contracts`）、`terminal`/`monitorMatches` 现有语义（`App.vue:424-425`）。
- Produces（Task 4-7 依赖的精确签名）:
  - `useJobMonitor(deps: { isWorkspaceLoading: Ref<boolean>; workspace: Ref<Workspace|null>; onJobSucceeded(workspaceId: string): Promise<void> })` → `{ job: Ref<Job|null>; connectionMode: Ref<string>; watchJob(id: string, workspaceId: string): void; retryJob(): Promise<void>; invalidateJobMonitor(clearJob: boolean): number; terminal(status: string): boolean; monitorMatches(generation: number, workspaceId: string): boolean }`
  - `useRepair(deps: { workspace: Ref<Workspace|null>; isWorkspaceLoading: Ref<boolean>; isRestoreExecuting: Ref<boolean>; refreshWorkspace(id: string): Promise<void>; setJob(job: Job): void; invalidateJobMonitor(clearJob: boolean): number })` → `{ repairPreview: Ref<RepairPreview|null>; repairContext: Ref<...>; isRepairPreviewing: Ref<boolean>; isRepairExecuting: Ref<boolean>; previewRepair(): Promise<void>; executeRepair(): Promise<void>; repairWritesDisabled: ComputedRef<boolean> }`（`repairWritesDisabled` 连同 `dstValidation` computed 一并迁入）
  - `useRestore(deps: { workspace; isWorkspaceLoading; refreshWorkspace; setJob; invalidateJobMonitor })` → `{ revisions; restorePreview; restorePreviewContext; isRestoreExecuting; loadRevisions(): Promise<void>; loadRevisionsInternal(): Promise<void>; previewRestore(revision: Revision): Promise<void>; restoreRevision(): Promise<void>; invalidateRevisionState(): void }`
  - `useCsvImport(deps: { workspace; isWorkspaceLoading; watchJob; setJob; refreshWorkspace; invalidateJobMonitor })` → `{ csvText; csvPreview; csvPreviewContext; readCsvFile(event: Event): Promise<void>; previewCsv(): Promise<void>; importCsv(): Promise<void>; invalidateCsvPreview(clearText?: boolean): void }`
- 注意：`useRestore` 与 `useRepair` 互相依赖 `isRestoreExecuting`（`openByPath`/`previewRepair` 的门禁）——由 App.vue 创建 `const isRestoreExecuting=ref(false)` 后作为 deps 传入两者，保持单一事实来源。

- [x] **Step 1: 拆分前基线固化**

Run: `cd web && npm run test:e2e && npm run build`
记录通过数字与 `App.vue` 行数（`wc -l web/src/App.vue`）。

- [x] **Step 2: 逐域迁移（每域一提交）**

按 useJobMonitor → useCsvImport → useRepair → useRestore 顺序，每次把 `App.vue` 中对应状态 ref、generation 变量与函数**原样剪切**进 composable，函数体内对 `workspace`/`isWorkspaceLoading` 等的引用改为 `deps.xxx.value`，对 `refreshWorkspace`/`discardDraft` 等的调用改为 deps 注入（`execute`/`watchJob` 成功路径的 `await discardDraft();await refreshWorkspace(...)` 通过 `onJobSucceeded` 注入，App.vue 传入 `async workspaceId=>{await discardDraft();await refreshWorkspace(workspaceId)}`）。**禁止**任何行为修改：确认文案、错误码分支、代次保护逐字保留。每域迁移后运行 `npm run test:e2e` 确认全绿再提交。

- [x] **Step 3: 等价性验证**

Run: `cd web && npm run test:e2e && npm run build && wc -l web/src/App.vue`
Expected: e2e 通过数字与 Step 1 基线一致；`App.vue` 低于约 500 行。

- [x] **Step 4: 更新 changelog 并提交（4 个独立 commit，不与功能混合）**

```bash
git add web/src/composables/useJobMonitor.ts web/src/App.vue changelog.md
git commit -m "拆分任务监控域为 useJobMonitor 组合式函数"
# 其余三域同理：useCsvImport / useRepair / useRestore
```

---

### Task 4: 外壳骨架——TopBar / TabBar / 三视图 / 未打开态（SPEC-DM-006 §4.1、§4.2）

**Files:**
- Create: `web/src/layout/TopBar.vue`
- Create: `web/src/layout/TabBar.vue`
- Create: `web/src/composables/useShellTabs.ts`
- Create: `web/src/views/WelcomeView.vue`
- Create: `web/src/views/SheetsView.vue`
- Create: `web/src/views/PropertiesView.vue`
- Create: `web/src/views/RevisionsView.vue`
- Modify: `web/src/App.vue`（模板重组 + 顶栏/标签挂载）
- Test: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- Consumes: Task 1 `useTheme`、Task 2 模态（关闭确认）、Task 3 各 composable。
- Produces:
  - `useShellTabs<T extends string>(ids: readonly T[], initial: T)` → `{ active: Ref<T>; select(id: T): void; onKeydown(e: KeyboardEvent): void }`——roving `tabindex`、`ArrowLeft/Right/Home/End`（§7.2 标签栏键盘模型）。Task 6 浮层页签复用。
  - `TopBar` props `{ projectPath: string; dstStatus: string; cadVersion: string }`，emits `{ "update:cadVersion": [string]; close: []; }`，内部用 `useTheme` 渲染主题按钮（含 `aria-label="切换主题"`，Task 1 的 e2e 用例依赖此名）。
  - `TabBar` props `{ active: string }`，emits `{ select: [id: string] }`；固定三项 `[{id:"sheets",label:"图纸"},{id:"properties",label:"属性"},{id:"revisions",label:"修订历史"}]`；`role="tablist"`、`role="tab"`+`aria-selected`+`aria-controls`。
  - 视图组件均为受控组件（状态仍由 App.vue 持有，经 props/emits 透传），本次不把业务状态下放进视图。
- **模板归属映射表**（App.vue 现模板 → 新位置；行号为基线）：

| 现位置（基线行号） | 内容 | 新位置 |
| --- | --- | --- |
| L546 header | 品牌与副标题 | `TopBar`（副标题并入项目区） |
| L548 未打开 `section.open` | 路径输入（无壳回退）/ 选择 DST 按钮 | `WelcomeView`（卡片式，含"这是什么"简介位） |
| L548 已打开 `section.open` | 关闭按钮 / 修订历史按钮 | 关闭 → `TopBar`；修订历史 → TabBar ③ |
| L549-551 error / loading | 全局提示条 | App.vue 直属（内容区顶部，所有标签共享） |
| L553 `JobStatusPanel` | 任务进度 | **过渡期保留 App 直属**，Task 6 迁浮层 |
| L555 `RevisionHistoryPanel` | 修订列表 | `RevisionsView` |
| L558 recover-banner | 恢复横幅 | App.vue 直属（内容区顶部） |
| L559 summary | 图纸集名称输入 / 计数 / CAD 版本 / 阻断诊断数 | 名称输入 → `PropertiesView` 图纸集属性卡；计数 → `SheetsView` 标题行；CAD 版本 → `TopBar`；阻断诊断数 → Task 6 浮层红点（过渡期暂留 SheetsView 标题） |
| L560 图纸集自定义属性 | details 表单 | `PropertiesView` 图纸集属性卡 |
| L561 诊断 details | 诊断列表 | **过渡期暂留标签①**，Task 6 迁浮层诊断页签 |
| L563 `RepairStatusPanel` | 修复门禁 | **过渡期暂留标签①顶部**，Task 6 迁浮层诊断页签 |
| L565 `PropertyPanel` | 字段定义 + CSV | `PropertiesView` |
| L567-579 sheet-browser | 浏览筛选 + 表格 + 批量条 | `SheetsView` |
| L581-598 editor | ProjectNavigation + DraftActionsPanel + 保存状态 + 子集编辑 + 批量新增图纸/新建子集表单 | `SheetsView`（DraftActionsPanel 与保存状态 Task 5 迁 ActionDock） |
| L600 `PreviewPanel` | 变更预览 | **过渡期保留 App 直属**，Task 6 迁浮层 |

- [x] **Step 1: 写失败的 e2e 用例**

```typescript
test("打开工作区后显示三个固定标签且默认激活图纸标签",async({page})=>{
  await openWorkspace(page);
  const tabs=page.getByRole("tablist",{name:"功能分区"}).getByRole("tab");
  await expect(tabs).toHaveCount(3);
  await expect(tabs.filter({hasText:"图纸"})).toHaveAttribute("aria-selected","true");
  await tabs.filter({hasText:"属性"}).click();
  await expect(page.getByRole("tabpanel",{name:/属性/})).toBeVisible();
  await expect(page.getByRole("tabpanel",{name:/图纸/})).toHaveCount(0); // 未激活面板不渲染
  await tabs.filter({hasText:"修订历史"}).click();
  await expect(page.getByRole("tabpanel",{name:/修订历史/})).toBeVisible();
});

test("标签栏支持方向键切换",async({page})=>{
  await openWorkspace(page);
  await page.getByRole("tab",{name:/图纸/}).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab",{name:/属性/})).toHaveAttribute("aria-selected","true");
  await page.keyboard.press("Home");
  await expect(page.getByRole("tab",{name:/图纸/})).toHaveAttribute("aria-selected","true");
});

test("关闭按钮位于顶栏且确认后回未打开态",async({page})=>{
  await openWorkspace(page);
  await page.getByRole("button",{name:"关闭工作区"}).click();
  const modal=page.getByRole("dialog");
  await modal.getByRole("checkbox").check();
  await modal.getByRole("button",{name:"关闭工作区"}).click();
  await expect(page.getByText("打开图纸集")).toBeVisible(); // WelcomeView
  await expect(page.getByRole("tablist",{name:"功能分区"})).toHaveCount(0);
});
```

- [x] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e -- -g "固定标签|方向键|顶栏"`
Expected: FAIL

- [x] **Step 3: 实现**

1. `useShellTabs.ts`：

```typescript
import {ref} from "vue";
import type {Ref} from "vue";

export function useShellTabs<T extends string>(ids:readonly T[],initial:T){
  const active=ref<T>(initial);
  function select(id:T){active.value=id}
  function onKeydown(e:KeyboardEvent){
    const i=ids.indexOf(active.value);if(i<0)return;
    let next=-1;
    if(e.key==="ArrowRight")next=(i+1)%ids.length;
    else if(e.key==="ArrowLeft")next=(i-1+ids.length)%ids.length;
    else if(e.key==="Home")next=0;
    else if(e.key==="End")next=ids.length-1;
    if(next>=0){e.preventDefault();active.value=ids[next]}
  }
  return {active,select,onKeydown};
}
```

2. `TopBar.vue` / `TabBar.vue`：按 Interfaces 的 props/emits 实现；TopBar 渲染品牌、`projectPath`（等宽字体回显）、DST 状态胶囊（`VALID` 绿 / `REPAIRED` 黄 / 其余红，用 §5.1 语义色）、CAD 版本下拉（emits `update:cadVersion`）、关闭按钮（`aria-label="关闭工作区"`）、主题按钮；TabBar 渲染三个固定 tab + 末尾"＋ 预留扩展"占位（`disabled` + `title`）。

3. `WelcomeView.vue`：卡片含标题"打开图纸集"、说明、`选择 DST 文件`按钮（emits `select`，App 转调 `selectAndOpenDst`）、无壳回退输入框（`v-if="!hasShell"` 经 prop `hasShell` 传入）、拖拽提示。

4. App.vue 模板重组：按**归属映射表**把内容块剪切进三个视图组件（props/emits 透传，视图组件不自持业务状态）；`v-if="!workspace"` 渲染 `WelcomeView`，`v-else` 渲染 TabBar + 激活面板（非激活面板 `v-if` 不渲染，满足 Step 1 用例第三断言）；`JobStatusPanel`/`PreviewPanel`/诊断/修复面板过渡期挂 App 直属（所有标签共享位置）。

- [x] **Step 4: 全量 e2e 适配与验证**

既有用例中"修订历史"按钮入口（原顶栏）改为标签③路径；确认无遗漏后：

Run: `cd web && npm run test:e2e && npm run build && wc -l web/src/App.vue`
Expected: PASS 全绿；App.vue 行数不高于 Task 3 结束值。

- [x] **Step 5: 更新 changelog 并提交**

```bash
git add web/src/layout web/src/views web/src/composables/useShellTabs.ts web/src/App.vue web/tests/e2e/main.spec.ts changelog.md
git commit -m "重建为固定标签化应用外壳并迁移三视图"
```

---

### Task 5: ActionDock 与草稿栈浮窗 + 快捷键（SPEC-DM-006 §4.1、§6.8、§6.9、§7.1）

**Files:**
- Create: `web/src/layout/ActionDock.vue`
- Create: `web/src/composables/useHotkeys.ts`
- Modify: `web/src/App.vue`（挂载 ActionDock；DraftActionsPanel 迁出；快捷键接线）
- Modify: `web/src/views/SheetsView.vue`（移除 DraftActionsPanel 与保存状态行）
- Test: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- Consumes: Task 2 `confirmAction`（"确认写入"打开发布模态）；`DraftActionsPanel` 既有 props/emits（原样迁入浮窗）。
- Produces:
  - `ActionDock` props `{ commandCount: number; actions: DraftAction[]; cursor: number; stale: boolean; staleReasons: string[]; corrupted: boolean; saveStatusText: string; saveFailed: boolean; canPreview: boolean; canWrite: boolean; writeDisabledReason: string; writeNeedsModal: boolean; previewing: boolean; writesDisabled: boolean }`，emits `{ preview: []; write: []; undo: []; redo: []; clear: []; remove: [index: number]; discard: []; reloadConflict: []; retrySave: [] }`。
  - §6.9 矩阵落地为 App.vue 的 `dock` computed（核心分支，Task 内完整实现）：无草稿 → `canPreview:false`、写入禁用原因"没有待发布变更"；有草稿未预览 → 预览可用、写入禁用原因"请先预览"；预览有效可执行 → `writeNeedsModal:true`（点击开模态）；预览过期/基准变化（`previewContext` 的基准与当前 `workspace.revision_id` 不一致）→ 禁用原因"预览已失效，请重新预览"；`REPAIRED`/`INVALID_*` → 普通写入禁用原因"存在待确认修复"/"需先修复"；`job` 非终态或 `isRestoreExecuting` → 全部禁用原因"任务进行中"。
  - `useHotkeys(handlers: { open: () => void; preview: () => void; write: () => void; undo: () => void; redo: () => void })`——`window` keydown 捕获 `Ctrl/Cmd+O/Enter/S/Z/Shift+Z`，`preventDefault`；`Ctrl+S` 仅在 `writeNeedsModal` 时调用 `write()`（模态内仍需勾选，无执行旁路），否则给非阻断提示（经 `pushToast` 前可先用 `error` 值或 toast，Task 7 前用既有 `error`）。

- [x] **Step 1: 写失败的 e2e 用例**

```typescript
test("ActionDock：无草稿时写入禁用并可见原因，有草稿未预览引导先预览",async({page})=>{
  await openWorkspace(page); // mock 草稿 actions 为空
  await expect(page.getByText("没有待发布变更")).toBeVisible(); // 禁用原因以内联文本呈现（原生 title 不进 DOM，不作为断言通道）
  // 加入一条动作后（跟随既有 mock 方式触发一次属性变更）
  await expect(page.getByText("请先预览")).toBeVisible();
});

test("Ctrl+S 只打开确认模态不直接执行",async({page})=>{
  await openWorkspace(page);
  // mock：加入动作并生成有效预览（跟随既有"普通预览丢弃乱序响应"用例的前置）
  await page.keyboard.press("Control+s");
  const modal=page.getByRole("dialog");
  await expect(modal).toBeVisible();
  await expect(modal.getByRole("checkbox")).toBeVisible(); // 模态内仍需勾选
  let executed=false;
  await page.route("**/changes/execute",route=>{executed=true;return route.fulfill({json:{}})});
  await page.keyboard.press("Escape"); // Esc 关闭 = 取消
  await expect(modal).toHaveCount(0);
  expect(executed).toBeFalsy();
});
```

- [x] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e -- -g "ActionDock|Ctrl\\+S"`
Expected: FAIL

- [x] **Step 3: 实现**

1. `ActionDock.vue`：单行布局——左侧草稿计数芯片（`草稿 N/M ▲`，`aria-expanded`/`aria-controls` 指向浮窗）+ 撤销/重做按钮；右侧 `预览变更`（`Primary`）与 `确认写入`（`Danger`）。禁用时按钮 `disabled` + `title` 与按钮旁内联文本双通道呈现禁用原因。点击"确认写入"时若 `writeNeedsModal` 则 emit `write`（App 内 `confirmAction(发布模态)` → 确认后调 `execute()`），否则按矩阵禁用。
2. 草稿栈浮窗：`position:absolute;bottom:100%` 限高 300px 滚动（参照原型 `docs/dst-manager/mockups/SPEC-DM-006-shell-demo.html` 的 `.pop`），内嵌 `DraftActionsPanel`（props/emits 原样桥接）+ `保存中/已保存/保存失败` 状态 + 失败重试按钮；`Esc` 关闭并把焦点还给计数芯片（§7.2 抽屉模型）。
3. `useHotkeys.ts`：

```typescript
import {onMounted,onUnmounted} from "vue";

type HotkeyHandlers={open:()=>void;preview:()=>void;write:()=>void;undo:()=>void;redo:()=>void};

export function useHotkeys(handlers:HotkeyHandlers):void{
  function onKeydown(e:KeyboardEvent){
    const mod=e.ctrlKey||e.metaKey;if(!mod)return;
    const key=e.key.toLowerCase();
    if(key==="o"){e.preventDefault();handlers.open()}
    else if(key==="enter"){e.preventDefault();handlers.preview()}
    else if(key==="s"){e.preventDefault();handlers.write()}
    else if(key==="z"){e.preventDefault();e.shiftKey?handlers.redo():handlers.undo()}
  }
  onMounted(()=>window.addEventListener("keydown",onKeydown));
  onUnmounted(()=>window.removeEventListener("keydown",onKeydown));
}
```

4. App.vue：实现 `dock` computed（Interfaces 中矩阵分支）；`write()` 入口统一走"模态 → execute"；`open()` 复用 `selectAndOpenDst`（无壳回退聚焦 WelcomeView 输入）。

- [x] **Step 4: 验证**

Run: `cd web && npm run test:e2e && npm run build && wc -l web/src/App.vue`
Expected: PASS 全绿；App.vue 仍低于约 500 行。

- [x] **Step 5: 更新 changelog 并提交**

```bash
git add web/src/layout/ActionDock.vue web/src/composables/useHotkeys.ts web/src/App.vue web/src/views/SheetsView.vue web/tests/e2e/main.spec.ts changelog.md
git commit -m "落地全局操作栏草稿栈浮窗与快捷键门禁"
```

---

### Task 6: 任务浮层——进度 / 预览 / 诊断三页签（SPEC-DM-006 §4.1、§4.2、§7.2）

**Files:**
- Create: `web/src/layout/TaskOverlay.vue`
- Modify: `web/src/App.vue`（浮层状态提升 + 自动激活接线；迁出过渡期面板）
- Test: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- Consumes: `useShellTabs`（Task 4，页签复用）、`JobStatusPanel`/`PreviewPanel`/`RepairStatusPanel` 既有组件。
- Produces:
  - App.vue 持有浮层状态：`overlayOpen: Ref<boolean>`、`overlayTab: Ref<"prog"|"prev"|"diag">`、`openOverlay(tab): void`——**状态在 App 而非组件内**，Task 7 的 toast 抑制与"查看"跳转依赖它。
  - `TaskOverlay` props `{ open: boolean; tab: "prog"|"prev"|"diag"; hasBlocking: boolean; hasRepair: boolean; job: Job|null; connectionMode: string; preview: Preview|null; …（PreviewPanel/RepairStatusPanel/诊断列表所需 props 原样透传）}`，emits `{ "update:tab": [tab]; fold: []; retry: []; "preview-repair": []; "execute-repair": []; cancel-repair: [] }`。
  - 自动激活规则：`showPreview()` 成功回调内 `openOverlay("prev")`；`execute`/`executeRepair`/`importCsv`/`restoreRevision` 发起请求成功拿到 `QUEUED` 后 `openOverlay("prog")`；`blocking.length>0` 时诊断页签渲染红点（`hasBlocking`）。

- [x] **Step 1: 写失败的 e2e 用例**

```typescript
test("点击预览后任务浮层自动展开到修改预览页签",async({page})=>{
  await openWorkspace(page);
  // 跟随既有用例构造草稿并触发预览成功
  await page.getByRole("button",{name:"预览变更"}).click();
  const overlay=page.getByRole("complementary",{name:"任务浮层"});
  await expect(overlay).toBeVisible();
  await expect(overlay.getByRole("tab",{name:"修改预览"})).toHaveAttribute("aria-selected","true");
  await overlay.getByRole("button",{name:"收起任务浮层"}).click();
  await expect(overlay).toBeHidden(); // 折叠不卸载，收起后任务仍在执行
});

test("存在阻断诊断时诊断页签显示红点并可打开",async({page})=>{
  // mock workspace.diagnostics 含 severity==="error" 两条（跟随既有诊断用例前置）
  await openWorkspace(page);
  const overlay=page.getByRole("complementary",{name:"任务浮层"});
  await expect(overlay.getByRole("tab",{name:/诊断/})).toContainText("●");
});
```

- [x] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e -- -g "任务浮层"`
Expected: FAIL

- [x] **Step 3: 实现**

1. `TaskOverlay.vue`：`role="complementary"` + `aria-label="任务浮层"`；页签行复用 `useShellTabs(["prog","prev","diag"],"prog")` 但受控（`tab` prop 变化时同步 `active`，`watch` 双向）；三页签内容——`prog`：`JobStatusPanel` 原样迁入；`prev`：`PreviewPanel` 原样迁入（execute 事件仍 emit 给 App，确认模态在 App 层）；`diag`：诊断列表（沿用现 `details` 内容结构）+ `RepairStatusPanel`。页签 `prog/实施进度`、`prev/修改预览`、`diag/诊断`（红点为 `<span aria-hidden="true">●</span>` + 页签 `aria-description` 提示存在阻断诊断）。折叠按钮 `aria-expanded`/`aria-label="收起任务浮层"`，折叠用 `hidden` 于面板体（页签行保留一条窄条，保证"始终可见的触发按钮"，§4.3）。
2. App.vue：删除过渡期的直属 `JobStatusPanel`/`PreviewPanel`/诊断 details/`RepairStatusPanel` 挂载，改挂 `TaskOverlay`；按 Interfaces 接线自动激活；`refreshWorkspace`/`closeWorkspace`/`beginWorkspaceLoad` 中折叠状态复位（`overlayOpen=false;overlayTab="prog"`）。
3. `< 1120px` 抽屉化：`style.css` 媒体查询 `@media (max-width:1120px)` 下浮层 `position:fixed;right:0;top:0;bottom:0` 覆盖为抽屉、默认折叠；折叠按钮即始终可见触发入口（含 `aria-expanded`/`aria-controls`，§4.3）。
4. `< 900px` 窄屏（§4.3）：同媒体查询断点内补 `TabBar` 容器 `overflow-x:auto`（标签横向滚动）；`ActionDock` 已为吸底常驻布局，无需额外处理。结构树折叠（`< 900px` 标签①左树收起）留待 PLAN-DM-004，见"范围外事项"。

- [x] **Step 4: 验证**

Run: `cd web && npm run test:e2e && npm run build`
Expected: PASS 全绿（既有 JobStatusPanel/PreviewPanel 相关用例改为经浮层定位后全绿）。

- [x] **Step 5: 更新 changelog 并提交**

```bash
git add web/src/layout/TaskOverlay.vue web/src/App.vue web/src/style.css web/tests/e2e/main.spec.ts changelog.md
git commit -m "任务进度预览与诊断迁入右缘三页签任务浮层"
```

---

### Task 7: SSE 任务通知 toast（SPEC-DM-006 §6.6）

**Files:**
- Create: `web/src/composables/useToast.ts`
- Create: `web/src/components/ui/ToastHost.vue`
- Modify: `web/src/composables/useJobMonitor.ts`（终态迁移发通知）
- Modify: `web/src/App.vue`（挂 ToastHost；接线）
- Test: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- Consumes: Task 6 的 `overlayOpen`/`overlayTab`（抑制规则）；`useJobMonitor` 的终态分支。
- Produces:
  - `useToast()` → `{ toasts: Ref<Toast[]>; pushToast(t: { type: "ok"|"fail"; title: string; body: string; jumpTab?: "prog"|"prev"|"diag" }): void; dismiss(id: number): void }`。规则：`ok` 5 秒自动消失、`role="status"`；`fail` **常驻不自动消失**、`role="alert"`；同屏上限 4 条，超出移除最旧。
  - 通知触发点（`useJobMonitor` 内，新增构造参数 `notify: { onTerminal(job: Job): void }` 或经 deps 注入 `pushToast` + `shouldSuppress()`）：`watchJob`/`pollJob` 收到终态时——`SUCCEEDED` → `ok`（"任务成功"，`jumpTab:"prog"`）；`FAILED`/`ROLLED_BACK`/`BLOCKED_FILE_LOCK` → `fail`（body 含 `error_code` 与"整批未发布"既有语义）；`NEEDS_REVIEW` → `fail`（"需人工检查，禁止直接重试"）。**抑制**：`overlayOpen && overlayTab==="prog"` 时不弹（用户正看进度页签）。SSE 断线转轮询后 `pollJob` 同样触发，通知照常。
  - `ToastHost` props `{ toasts: Toast[] }`，emits `{ dismiss: [id]; jump: [tab: string] }`；"查看"按钮 emit `jump`，App 调 `openOverlay(tab)`。

- [x] **Step 1: 写失败的 e2e 用例**

```typescript
test("任务成功经 SSE 推送 toast 且失败通知常驻可查看",async({page})=>{
  await openWorkspace(page);
  // 跟随既有"失败任务显示逐 DWG 详情并可安全重试"用例的 SSE mock：
  // 推送终态 FAILED 事件后
  const toast=page.getByRole("alert").filter({hasText:"任务失败"});
  await expect(toast).toBeVisible();
  await page.waitForTimeout(6000); // 超过成功类自动消失时长
  await expect(toast).toBeVisible(); // 失败常驻
  await toast.getByRole("button",{name:"查看"}).click();
  await expect(page.getByRole("complementary",{name:"任务浮层"}).getByRole("tab",{name:"实施进度"})).toHaveAttribute("aria-selected","true");
  await toast.getByRole("button",{name:"✕"}).click();
  await expect(toast).toHaveCount(0);
});
```

- [x] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e -- -g "SSE 推送 toast"`
Expected: FAIL

- [x] **Step 3: 实现**

`useToast.ts`：

```typescript
import {ref} from "vue";

export type Toast={id:number;type:"ok"|"fail";title:string;body:string;jumpTab?:"prog"|"prev"|"diag"};
let nextId=1;

export function useToast(){
  const toasts=ref<Toast[]>([]);
  function dismiss(id:number){toasts.value=toasts.value.filter(t=>t.id!==id)}
  function pushToast(t:Omit<Toast,"id">){
    const toast:Toast={id:nextId++,...t};
    toasts.value=[...toasts.value.slice(-3),toast]; // 上限 4 条，移除最旧
    if(toast.type==="ok")setTimeout(()=>dismiss(toast.id),5000);
  }
  return {toasts,pushToast,dismiss};
}
```

`ToastHost.vue`：`aria-live="polite"` 容器；`ok` 项 `role="status"`、`fail` 项 `role="alert"`；每项含关闭 `✕` 与可选"查看"按钮。`App.vue` 挂载于根并接线 `jump → openOverlay`；`useJobMonitor` deps 增加 `pushToast` 与 `shouldSuppress: () => boolean`（实现为 `overlayOpen&&overlayTab==="prog"`），在终态分支按 Interfaces 规则调用。

- [x] **Step 4: 验证**

Run: `cd web && npm run test:e2e && npm run build`
Expected: PASS 全绿。

- [x] **Step 5: 更新 changelog 并提交**

```bash
git add web/src/composables/useToast.ts web/src/components/ui/ToastHost.vue web/src/composables/useJobMonitor.ts web/src/App.vue web/tests/e2e/main.spec.ts changelog.md
git commit -m "任务终态经 SSE 驱动非模态通知并支持跳转浮层"
```

---

### Task 8: 修订历史标签完善与收尾（SPEC-DM-006 §4.2 标签③、§6.5）

**Files:**
- Modify: `web/src/App.vue`（激活标签③时加载修订、空状态接线、恢复流程接浮层）
- Modify: `web/src/views/RevisionsView.vue`（空状态卡）
- Modify: `changelog.md`、`docs/dst-manager/README.md`、`.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md`（状态收尾）、`.planning/roadmaps/dst-manager.md`
- Test: `web/tests/e2e/main.spec.ts`

**Interfaces:**
- Consumes: Task 3 `useRestore`（`loadRevisions`/`previewRestore`/`restoreRevision`/`revisions`）、Task 6 `openOverlay`。
- Produces: 无跨任务接口。

- [x] **Step 1: 写失败的 e2e 用例**

```typescript
test("修订历史标签激活时加载列表，空修订显示暂无修订历史",async({page})=>{
  await openWorkspace(page);
  let asked=false;
  await page.route("**/api/revisions**",route=>{asked=true;return route.fulfill({json:[]})});
  await page.getByRole("tab",{name:/修订历史/}).click();
  await expect(page.getByText("暂无修订历史")).toBeVisible();
  expect(asked).toBeTruthy(); // 激活时才加载
});

test("恢复预览在任务浮层修改预览页签呈现",async({page})=>{
  await openWorkspace(page);
  // 跟随既有"修订恢复先预览再确认为新修订"用例 mock 修订列表与 restore-preview
  await page.getByRole("tab",{name:/修订历史/}).click();
  await page.getByRole("button",{name:"预览恢复"}).first().click();
  await expect(page.getByRole("complementary",{name:"任务浮层"}).getByRole("tab",{name:"修改预览"})).toHaveAttribute("aria-selected","true");
});
```

- [x] **Step 2: 运行确认失败**

Run: `cd web && npm run test:e2e -- -g "修订历史标签|恢复预览在任务浮层"`
Expected: FAIL

- [x] **Step 3: 实现**

1. App.vue：`watch(activeTab,tab=>{if(tab==="revisions")void loadRevisions()})`（保留既有代次与执行中门禁——`loadRevisions` 内部已有 `isRestoreExecuting` 防重入）；`previewRestore` 成功回调内 `openOverlay("prev")`；`restoreRevision` 确认执行后 `openOverlay("prog")`。
2. `RevisionsView.vue`：`revisions.length===0` 时渲染空状态卡——标题"暂无修订历史"、说明"发布首个变更后，此处会记录每个可恢复的修订版本。"（§6.5"说明 + 下一步动作"，动作即提示去标签①发起变更，不设跳转按钮以免打断）。
3. 收尾文档：`changelog.md` 汇总条目；`docs/dst-manager/README.md` 当前状态补 v0.3.3 外壳重建说明；`.planning/roadmaps/dst-manager.md` 增补 v0.3.3 行（状态已完成）；本计划追加"实际验证"小节并把状态 `proposed` → `completed`。

- [x] **Step 4: 全量验证**

```powershell
uv run ruff check .
uv run pytest -q
cd web; npm run build; npm run test:e2e
```

Expected: 后端零改动全绿且数字与 v0.3.2 基线一致（545 passed / 72 skipped）；前端构建零类型错误、e2e 全绿（记录实际数字写入 changelog）。

- [x] **Step 5: Commit**

```bash
git add web/src/App.vue web/src/views/RevisionsView.vue web/tests/e2e/main.spec.ts changelog.md docs/dst-manager/README.md .planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md .planning/roadmaps/dst-manager.md
git commit -m "修订历史接入标签化外壳并完成 v0.3.3 收尾"
```

---

## 范围外事项（避免执行者自行扩大）

- 全量 stylelint 令牌消费门禁、树/表格完整键盘模型（§7.2 结构树/表格细则）、`< 900px` 结构树折叠（§4.3）、`/`、`?` 单字符快捷键、§10.2 完整视口×主题视觉回归矩阵、`aria-live` 读屏人工走查——属 PLAN-DM-004 产品化 UI 重建范围。
- 视觉细稿（组件内样式重写、阴影/密度档位应用）不在本次：既有 8 个业务组件内部样式原样迁移，仅外壳容器（TopBar/TabBar/ActionDock/TaskOverlay/toast/模态）消费 Task 1 令牌。

---

## 实际验证

**Task 1-8 全部完成**（2026-09-04）。每个 task 结束时均已恢复 e2e 全绿、更新根目录 `changelog.md`（当前日期章节）并独立 commit；本计划状态 `proposed` → `completed`，全部任务步骤勾选为 `[x]`（唯一未勾选项为文件头部 "For agentic workers" 备注中 `- [ ]` 的字面示例文本）。

**收尾全量验证（Task 8，2026-09-04）**：
- `uv run ruff check .`：All checks passed。
- `uv run pytest -q`：全量 **547 passed / 72 skipped**（619 项，0 failures / 0 errors，退出码 0）。与 v0.3.2 基线 545 passed / 72 skipped 的差异为提交 `a83e92b`（修复派生 DWG 文件名后缀区间压缩与项目前缀对齐）新增 2 项 `tests/unit/test_core.py` 用例所致；本次 Task 8 **后端零改动**（未触碰 `src/`、`migrations/`、`plugins/`、`web/src/api/schema.d.ts`），数字如实记录。环境未显式启用 `DST_MANAGER_RUN_AUTOCAD=1`，真实 AutoCAD 系统测试按既有跳过条件跳过。
- `cd web && npm run build`（check:api + vue-tsc + vite）：零类型错误（71 modules，dist 产出正常）。
- `cd web && npm run test:e2e`：Playwright **55/55 通过**（53 既有 + 2 新增，51.1s）。
- `App.vue` 最终 514 行（相对 Task 7 的 512 +2：`previewRestoreAndOpen` 接线与 `Revision` 类型导入，为 Task 8 必要增量）。

**Task 8 实际交付明细**：
1. 修订历史标签空状态卡（§6.5）：`web/src/views/RevisionsView.vue` 由简单 `<p class="empty">` 升级为空状态卡——标题「暂无修订历史」、说明「发布首个变更后，此处会记录每个可恢复的修订版本。」、下一步动作提示「前往「图纸」标签发起首个变更，发布后即可在此恢复。」（§6.5「说明 + 下一步动作」，动作即提示去标签①发起变更，**不设跳转按钮以免打断**）；样式全部引用设计令牌（无裸十六进制色值）。
2. 恢复预览接入任务浮层修改预览页签：`previewRestore` 成功（`restorePreview` 已写入）后经 App.vue 新增的 `previewRestoreAndOpen` 调 `openOverlay("prev")`——与 `showPreview` 共用 §9.1 统一预览门禁呈现（§4.2 标签③「行内发起恢复：先预览（进任务浮层"修改预览"页签）→ 危险确认模态 → 恢复为新修订」）；`restoreRevision` 确认执行后任务响应经 `setJob` 已自动 `openOverlay("prog")`（Task 6 fix round 1 接线，本次核实未重复）。
3. 激活标签③时加载修订：核实 Task 4 已让 `selectTab`/`onTabKeydown` 在切换到 `revisions` 时触发 `loadRevisions`（内部含 `isRestoreExecuting` 防重入 + `revisionGeneration`/`workspaceLoadGeneration` 代次保护），**未重复加 `watch`**。
4. e2e 新增 2 项（TDD：第 2 条先红后绿）：①「修订历史标签激活时加载列表，空修订显示暂无修订历史」——`page.route("**/api/revisions**")` 在点击标签前安装，断言空状态卡「暂无修订历史」可见且 `asked` 为真（激活时才加载）；②「恢复预览在任务浮层修改预览页签呈现」——跟随既有「修订恢复先预览再确认为新修订」mock 修订列表与 restore-preview，断言点击「恢复预览」后任务浮层「修改预览」页签 `aria-selected="true"`。与简报用例的两处最小修正并记录：恢复按钮名沿用既有契约「恢复预览」（简报正文写作「预览恢复」）；第 ① 条因 Task 4 接线已存在，TDD 首跑即绿（非失败），第 ② 条确认失败后实现转绿。

**Task 1-7 汇总**（逐 task 数字见 `changelog.md` 2026-09-04 章节）：
- Task 1：设计令牌与浅深双主题（§5.1），`useTheme.ts` + `style.css` 令牌区，e2e 40/40。
- Task 2：确认模态组件化（§6.2/§6.9），`ConfirmModal.vue` + `useConfirm.ts`，迁移 8 处原生 `confirm()` + 2 次评审修复（状态泄漏复位、reversibility 类型收紧），e2e 42/42。
- Task 3：App.vue 状态域拆分（行为零变化），`useJobMonitor`/`useCsvImport`/`useRepair`/`useRestore`，App.vue 498 行，e2e 42/42。
- Task 4：固定三标签外壳 + TopBar/TabBar/三视图 + WelcomeView（§4.1/§4.2/§7.2），App.vue 468 行，e2e 45/45。
- Task 5：ActionDock 与草稿栈浮窗 + §6.9 矩阵唯一出口 + `useHotkeys`（§6.8/§6.9/§7.1），3 次评审修复（terminal 终态集、INVALID_UNRECOVERABLE 文案、NEEDS_REVIEW 独立分支），App.vue 500 行，e2e 49/49。
- Task 6：右缘三页签任务浮层（§4.1/§4.2/§7.2）+ `<1120px` 抽屉化 + 2 次评审修复（setJob 全状态展开浮层、refreshWorkspace 仅 SUCCEEDED），App.vue 504 行，e2e 52/52。
- Task 7：SSE 任务通知 toast（§6.6），`useToast.ts` + `ToastHost.vue` + `useJobMonitor` 终态通知，App.vue 512 行，e2e 53/53。
