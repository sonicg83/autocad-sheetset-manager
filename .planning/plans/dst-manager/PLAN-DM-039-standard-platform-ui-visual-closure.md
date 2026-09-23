---
id: PLAN-DM-039
title: 图纸标准平台欢迎页与编辑器视觉收口实施计划
status: active
owners:
  - dst-manager
created: 2026-09-23
updated: 2026-09-23
related:
  - ARCH-DM-007
  - SPEC-DM-016
  - SPEC-DM-017
  - PLAN-DM-035
  - PLAN-DM-038
---

# 图纸标准平台欢迎页与编辑器视觉收口实施计划

> **执行要求：** 实施者必须使用 `superpowers:subagent-driven-development`（推荐）或
> `superpowers:executing-plans` 逐任务执行；每个步骤使用复选框跟踪。进入实现前重新阅读
> [SPEC-DM-016](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md)、
> [SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md)、
> [欢迎页 Demo](../../../docs/dst-manager/mockups/SPEC-DM-016-welcome-demo.html) 与
> [标准编辑器 Demo](../../../docs/dst-manager/mockups/SPEC-DM-017-standard-properties-and-dwg-naming-demo.html)。

**目标：** 补齐 PLAN-DM-035 与 PLAN-DM-038 已接通功能但未落地的页面级布局：欢迎页恢复“打开 DST 优先”的约 2:1 双栏，标准草稿进入独立全宽编辑工作台，并以新的候选截图、人工 Demo 对照和可复现自动门禁重建可信视觉证据。

**架构：** 不改变标准 Schema、后端 API、草稿/发布门禁或 PLAN-DM-036 创建流程。应用级起始面继续由 `useStartNavigation` 管理；欢迎页只补齐三个次级入口的既有去向，标准管理页把“标准库/详情”和“草稿编辑器”明确拆成互斥页面状态。布局使用 ARCH-DM-007 既有令牌和 Vue scoped CSS，不引入新 UI 框架或第二套设计令牌。

**技术栈：** Vue 3、TypeScript、Vue I18n、Vitest、Playwright、Vite、既有 UI 原语与三层 CSS 令牌。

**Spec：** SPEC-DM-016 §4、§6、§11、§12 与 SPEC-DM-017 §2、§4～§9；两个 HTML Demo 只负责布局、文案层级和交互状态，领域规则仍以 Spec 为准。

## 背景与根因

- PLAN-DM-035 Task 7 Step 4 要求欢迎页采用“打开优先”双栏，但生产 `WelcomeView.vue` 只在旧 520px 单卡片底部增加了“管理图纸标准”按钮；创建与导入入口、2:1 布局均未落地。
- PLAN-DM-038 Task 9 要求以完整编辑器 Demo 作为视觉与交互对照，但任务文件清单遗漏 `StandardsView.vue`；生产仍把 `StandardEditor` 放在旧 `library-split` 右栏，编辑器内部再分一次导航/正文，形成双重侧栏并压缩表格。
- `standards-visual-evidence.spec.ts` 能从同一生产页面分别写 G4/G8，但没有证明页面符合 Demo；SPEC-DM-016 证据 README 还明确登记四张 PLAN-DM-038 新状态截图尚未生成，因此旧“12/12 一致”不能作为本次布局通过证据。

## 全局约束

- 不修改 Python、数据库迁移、标准 Schema、诊断码、求值、资产检查、包导入或发布安全逻辑。
- 欢迎页“选择 DST 文件”始终是唯一 primary；创建、标准管理、标准包导入均为 secondary。
- “创建新图纸集”继续进入现有明确不可用占位，不实现 PLAN-DM-036，不提供无标准创建回退。
- “导入标准包”复用现有 `StandardsView` 导入对话框和 API，不新增第二套导入表单或导入状态。
- 标准库继续采用主从分栏；只有打开草稿编辑器时才切换为独立工作台。返回标准库必须保留当前标准选择、筛选与已加载详情。
- 离开 dirty 草稿继续经过现有“保存/放弃/留在此处”门禁；不得通过页面重排绕过 `StandardEditor.guard()`。
- 900×768 不产生页面级横向滚动；宽表只能在表格自身容器内滚动。200% 缩放下模态底部操作栏持续可见且可由键盘到达。
- 浅色、深色、中英文共用同一结构；不为单一主题或语言复制模板。
- 不在本计划修改欢迎页“最近打开”能力；没有可信记录时继续不渲染占位项目。
- 所有代码注释、计划记录、changelog 与 commit message 使用简体中文。

## Review Focus

1. 有壳与无壳欢迎页都必须保留打开 DST 的原行为；布局变化不能让路径输入、拖放或系统文件选择器失效。
2. 三个次级入口必须各走唯一既有去向：创建占位、标准库、标准库导入对话框；不得创建第二套状态或绕过标准绑定。
3. 草稿编辑器切换为独立工作台后，dirty 离开门禁、发布后只读详情、返回时选择/筛选保留必须不回归。
4. 长中文、英文和诊断标签不能把按钮推出视口；900×768 与 200% 缩放必须覆盖真实操作栏可达性。
5. 新 G4 必须先由用户对照两个 Demo 确认，再生成 G8 并逐对比较；禁止再次用“同一页面抓两遍完全一致”代替设计裁决。

---

### Task 1：锁定起始面意图并重建欢迎页双栏

**Files:**
- Modify: `web/src/composables/useStartNavigation.ts`
- Modify: `web/src/composables/useStartNavigation.test.ts`
- Modify: `web/src/views/WelcomeView.vue`
- Modify: `web/src/views/StandardsView.vue`
- Modify: `web/src/App.vue`
- Modify: `web/src/i18n/locales/zh-CN/shell.ts`
- Modify: `web/src/i18n/locales/en-US/shell.ts`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Modify: `web/tests/e2e/standards-welcome.spec.ts`

**Interfaces:**
- Consumes: 既有 `StartSurface = "welcome" | "standards" | "create-sheetset"`、`StandardsView` 内部标准包导入对话框、`WelcomeView` 的 `select/submitPath/manageStandards` 事件。
- Produces: `type StandardsEntryIntent = "browse" | "import-package"`；`openStandards(intent?: StandardsEntryIntent)`；`standardsEntryIntent: Ref<StandardsEntryIntent>`；欢迎页新增 `createSheetset` 与 `importStandard` 事件；`StandardsView.entryIntent` 仅决定首次进入是否打开既有导入对话框。

- [x] **Step 1：先写导航意图单元测试**

```ts
it("records and clears the one-shot standards entry intent", () => {
  const navigation = useStartNavigation();
  navigation.openStandards("import-package");
  expect(navigation.surface.value).toBe("standards");
  expect(navigation.standardsEntryIntent.value).toBe("import-package");
  navigation.goWelcome();
  expect(navigation.surface.value).toBe("welcome");
  expect(navigation.standardsEntryIntent.value).toBe("browse");
});
```

- [x] **Step 2：先写欢迎页结构与入口失败 E2E**

```ts
test("欢迎页为打开优先双栏且三个次级任务走既有去向", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/");
  const layout = page.getByTestId("welcome-layout");
  await expect(layout).toBeVisible();
  await expect(layout.getByTestId("welcome-open-card")).toBeVisible();
  await expect(layout.getByTestId("welcome-task-card")).toBeVisible();
  await expect(page.locator("button.primary")).toHaveCount(1);
  await expect(page.getByRole("button", {name: "创建新图纸集"})).toBeVisible();
  await expect(page.getByRole("button", {name: "管理图纸标准"})).toBeVisible();
  await page.getByRole("button", {name: "导入标准包"}).click();
  await expect(page.getByRole("heading", {name: "标准管理"})).toBeVisible();
  await expect(page.getByRole("dialog", {name: "导入标准包"})).toBeVisible();
});
```

另新增 `900×768` 用例：`welcome-layout` 降为一列，“打开图纸集”在 DOM 与视觉顺序中均位于“其他任务”之前，`documentElement.scrollWidth <= 900`。

- [x] **Step 3：运行 RED 并记录准确失败**

Run:

```powershell
Set-Location web
npm run test:unit -- src/composables/useStartNavigation.test.ts
npx playwright test tests/e2e/standards-welcome.spec.ts --workers=1
```

Expected: 单元测试因 `openStandards` 不接收意图而失败；E2E 因欢迎页仍是单卡片且没有创建/导入入口而失败。若 `4173` 被非本任务进程占用，先记录 PID 并让占用方结束或改用任务专用 Playwright 配置端口；不得终止未知用户进程。

- [x] **Step 4：实现最小导航意图，不复制导入状态**

```ts
export type StandardsEntryIntent = "browse" | "import-package";

const standardsEntryIntent = ref<StandardsEntryIntent>("browse");

function openStandards(intent: StandardsEntryIntent = "browse"): void {
  standardsEntryIntent.value = intent;
  surface.value = "standards";
}

function goWelcome(): void {
  standardsEntryIntent.value = "browse";
  surface.value = "welcome";
}
```

`App.vue` 只装配事件：创建调用既有 `openCreateSheetset()`，管理调用 `openStandards()`，导入调用 `openStandards("import-package")`。`StandardsView` 以 `entryIntent === "import-package"` 初始化现有 `importDialogOpen`，后续导入仍走同一个 `importPackage()`。

- [x] **Step 5：按 Demo 重建欢迎页结构**

`WelcomeView.vue` 使用以下稳定结构，不复制 Demo 的模拟逻辑和硬编码数据：

```vue
<section class="welcome-page" role="region" :aria-label="$t('shell.welcome.region')">
  <header class="welcome-intro">
    <h1>{{ $t("shell.welcome.startTitle") }}</h1>
    <p>{{ $t("shell.welcome.startDesc") }}</p>
  </header>
  <div class="welcome-layout" data-testid="welcome-layout">
    <article class="welcome-open-card" data-testid="welcome-open-card">
      <h2>{{ $t("shell.welcome.title") }}</h2>
      <p>{{ $t("shell.welcome.desc") }}</p>
      <template v-if="!hasShell">
        <label :for="pathInputId">{{ $t("shell.welcome.pathPlaceholder") }}</label>
        <input :id="pathInputId" v-model="path" @keyup.enter="$emit('submitPath', path)">
        <UiButton variant="secondary" @click="$emit('submitPath', path)">{{ $t("shell.welcome.openProject") }}</UiButton>
      </template>
      <template v-else>
        <button type="button" class="primary" @click="$emit('select')">{{ $t("shell.welcome.selectDst") }}</button>
        <p>{{ $t("shell.welcome.dropHint") }}</p>
      </template>
    </article>
    <aside class="welcome-task-card" data-testid="welcome-task-card">
      <h2>{{ $t("shell.welcome.otherTasksTitle") }}</h2>
      <p>{{ $t("shell.welcome.otherTasksDesc") }}</p>
      <button type="button" class="task-item" @click="$emit('createSheetset')">{{ $t("standards.createEntry") }}</button>
      <button type="button" class="task-item" @click="$emit('manageStandards')">{{ $t("standards.entry") }}</button>
      <button type="button" class="task-item" @click="$emit('importStandard')">{{ $t("standards.library.import") }}</button>
      <p class="boundary-note">{{ $t("shell.welcome.standardBoundary") }}</p>
    </aside>
  </div>
</section>
```

标准视口使用 `grid-template-columns:minmax(0,2fr) minmax(280px,1fr)`；`max-width` 使用既有 `--shell-content-max-width`；`@media (max-width:900px)` 改为单列。主卡保留现有有壳/无壳分支，次级任务使用现有 `UiButton`/可访问按钮，不手写 SVG、字体图标或新色值。

- [x] **Step 6：补齐中英文文案并运行 Task 1 门禁**

至少增加同构键：欢迎页总标题/说明、其他任务标题/说明、创建说明、标准管理说明、导入说明、不可用边界说明。运行：

```powershell
Set-Location web
npm run test:unit -- src/composables/useStartNavigation.test.ts
npm run check:i18n
npm run check:ui
npx playwright test tests/e2e/standards-welcome.spec.ts --workers=1
npm run build
```

Expected: 全部通过；欢迎页只有一个 primary；创建仍进入明确不可用占位；导入直接打开唯一既有导入对话框。

- [x] **Step 7：提交欢迎页任务**

```powershell
git add web/src/composables/useStartNavigation.ts web/src/composables/useStartNavigation.test.ts web/src/views/WelcomeView.vue web/src/views/StandardsView.vue web/src/App.vue web/src/i18n/locales/zh-CN/shell.ts web/src/i18n/locales/en-US/shell.ts web/src/i18n/locales/zh-CN/standards.ts web/src/i18n/locales/en-US/standards.ts web/tests/e2e/standards-welcome.spec.ts changelog.md
git commit -m "重建打开优先欢迎页双栏"
```

---

### Task 2：把标准草稿编辑器切换为独立全宽工作台

**Files:**
- Modify: `web/src/views/StandardsView.vue`
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/components/standards/StandardSectionNav.vue`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Modify: `web/tests/e2e/standards-editor.spec.ts`
- Modify: `web/tests/e2e/standards-library.spec.ts`

**Interfaces:**
- Consumes: `editorOpen`、`selectedKey`、`store.draft`、`leaveEditor()`、`StandardEditor.guard()` 与六分区 `EDITOR_SECTIONS`。
- Produces: `StandardsView` 互斥的 `library-mode` / `editor-mode` 页面结构；`StandardEditor` 自带标题、身份/动作栏和“导航 + 内容面板”工作区；公共事件与 API props 保持不变。

- [x] **Step 1：先写编辑模式结构失败 E2E**

```ts
test("草稿编辑器替换标准库主从分栏并在返回后恢复选择", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await expect(page.getByTestId("standards-editor-mode")).toBeVisible();
  await expect(page.getByRole("region", {name: "标准库"})).toHaveCount(0);
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();
  await page.getByRole("button", {name: "返回标准库"}).click();
  await expect(page.getByRole("region", {name: "标准库"})).toBeVisible();
  await expect(page.getByRole("region", {name: "标准详情"})).toContainText("草稿 1");
});
```

再增加 dirty 变体：修改标准名称后点击“返回标准库”，必须出现现有三选一门禁；选择“留在此处”后仍处于 `standards-editor-mode` 且输入不丢失。

- [x] **Step 2：写标准视口几何约束测试**

```ts
const metrics = await page.getByTestId("standards-editor-workspace").evaluate(element => {
  const box = element.getBoundingClientRect();
  const columns = getComputedStyle(element).gridTemplateColumns;
  return {width: box.width, columns};
});
expect(metrics.width).toBeGreaterThan(1100);
expect(metrics.columns.split(" ")).toHaveLength(2);
```

在 1440×900 固定视口下执行；同时断言 `documentElement.scrollWidth <= 1440`。该测试锁定“独立全宽工作台”，避免只检查六个按钮存在而再次放过双重侧栏。

- [x] **Step 3：运行 RED**

Run:

```powershell
Set-Location web
npx playwright test tests/e2e/standards-editor.spec.ts tests/e2e/standards-library.spec.ts --workers=1
```

Expected: 新结构用例失败，因为 `StandardLibraryPane` 与 `StandardEditor` 仍同时位于 `library-split`。

- [x] **Step 4：重排 `StandardsView` 为互斥页面模式**

模板必须采用以下分支边界：

```vue
<section class="standards-page" :class="{'is-editor': editorOpen}">
  <StandardEditor
    v-if="editorOpen && store.draft.value"
    ref="editorRef"
    data-testid="standards-editor-mode"
    :draft="store.draft.value"
    :save-draft="saveEditorDocument"
    :inspect-asset="inspectEditorAsset"
    :publish-draft="publishEditorDraft"
    :official-assets="officialAssets"
    :official-standard-id="officialStandardId"
    @close="leaveEditor"
  />
  <template v-else>
    <div class="standards-header">
      <h2 class="standards-title">{{ $t("standards.title") }}</h2>
      <UiButton variant="secondary" @click="$emit('back')">{{ $t("standards.back") }}</UiButton>
    </div>
    <div class="library-split" data-testid="standards-library-mode">
      <StandardLibraryPane
        class="library-col"
        :items="store.summaries.value"
        :filters="filters"
        :selected-key="selectedKey"
        :list-pending="store.listPending.value"
        :list-error="store.listError.value"
        @select="select"
        @update-filters="filters = $event"
        @import-package="importDialogOpen = true"
        @create-new="openCreateDialog"
      />
      <StandardDetailPane
        class="detail-col"
        :summary="selected"
        :detail="store.detail.value"
        :detail-pending="store.detailPending.value"
        :detail-error="store.detailError.value || store.draftError.value"
        :items="store.summaries.value"
        @edit="openEditor"
        @derive="startCreate('derive')"
        @export-standard="exportSelectedStandard"
        @delete-draft="deleteSelectedDraft"
        @use-for-create="$emit('openCreateSheetset')"
        @open-version="openVersion"
      />
    </div>
  </template>
</section>
```

不得在 CSS 中简单隐藏仍挂载的标准库；必须用 Vue 分支卸载库视图，避免重复地标、不可见可聚焦元素和屏幕阅读器重复内容。返回编辑器沿用 `leaveEditor()`，不重建 store，不清空 `selectedKey`、筛选或已加载详情。

- [x] **Step 5：对齐编辑器标题、身份区和内容面板**

`StandardEditor` 采用 Demo 的三层结构：

1. `editor-titlebar`：显示“编辑标准 · {name}”、说明、保存状态；
2. `editor-identity`：标准名称、版本/草稿 ID、保存、发布检查；
3. `editor-workspace`：左分区导航，右侧有独立边框/标题层级的内容面板。

新增 `data-testid="standards-editor-workspace"`。原有 `saveDraft/publishCheck/back` 动作、结构诊断、发布检查切换和 `UnsavedInputDialog` 均保留原事件链；本步骤不得移动任何诊断计算到视图层。

- [x] **Step 6：运行编辑/标准库回归并提交**

```powershell
Set-Location web
npm run check:i18n
npm run check:ui
npx playwright test tests/e2e/standards-editor.spec.ts tests/e2e/standards-library.spec.ts tests/e2e/standards-assets-publish.spec.ts --workers=1
npm run build
```

Expected: 独立工作台、返回选择恢复、dirty 门禁、发布检查和已发布详情全部通过。

```powershell
git add web/src/views/StandardsView.vue web/src/components/standards/StandardEditor.vue web/src/components/standards/StandardSectionNav.vue web/src/i18n/locales/zh-CN/standards.ts web/src/i18n/locales/en-US/standards.ts web/tests/e2e/standards-editor.spec.ts web/tests/e2e/standards-library.spec.ts changelog.md
git commit -m "拆分标准库与全宽编辑工作台"
```

---

### Task 3：收敛宽表、响应式与缩放可达性

**Files:**
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/components/standards/StandardSectionNav.vue`
- Modify: `web/src/components/standards/OrdinaryPropertyEditor.vue`
- Modify: `web/src/components/standards/DerivedPropertyEditor.vue`
- Modify: `web/src/components/standards/DwgNamingEditor.vue`
- Modify: `web/tests/e2e/standards-editor.spec.ts`
- Modify: `web/tests/e2e/standards-visual-evidence.spec.ts`

**Interfaces:**
- Consumes: Task 2 的 `standards-editor-workspace`、既有六分区组件和 `TokenExpressionEditor`。
- Produces: ≥781px 的侧栏/内容双列、≤780px 的水平可滚动分区导航、宽表局部滚动容器、900×768 与 200% 缩放稳定状态。

- [x] **Step 1：先补响应式失败测试**

在 `standards-editor.spec.ts` 增加：

```ts
test("900×768 编辑工作台保留侧栏且宽表只在自身滚动", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "ordinary");
  const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(pageWidth).toBeLessThanOrEqual(900);
  const table = page.getByTestId("ordinary-table-scroll");
  const overflow = await table.evaluate(element => element.scrollWidth > element.clientWidth);
  expect(overflow).toBe(true);
});
```

保留既有 200% 组合模态操作栏用例，并增加欢迎页、编辑器正文和发布检查页在 CSS 视口 720×450 下无页面级横向溢出的断言。

- [x] **Step 2：运行 RED**

Run:

```powershell
Set-Location web
npx playwright test tests/e2e/standards-editor.spec.ts --workers=1
```

Expected: 普通属性表尚无局部滚动容器；当前 959px 断点会提前把导航堆叠成整列，与 Demo 的 900px 状态不一致。

- [x] **Step 3：实现分级响应式布局**

- `StandardEditor` 在标准视口使用 `238px minmax(0,1fr)`；1050px 以下收窄导航到约 210px；780px 以下才变成单列。
- `StandardSectionNav` 在 780px 以下改为单行水平滚动，按钮保持完整可访问名称和最小点击高度；不截短成只剩序号。
- `OrdinaryPropertyEditor` 用 `data-testid="ordinary-table-scroll"` 容器包住表格，表格 `min-width` 取 Demo 的 930px 结构基线，页面本身不横向滚动。
- `DerivedPropertyEditor` 在 1050px 以下隐藏纯说明列，在 780px 以下隐藏可由编辑模态读取的源摘要列；不得隐藏属性名、类型、编辑或删除动作。
- `DwgNamingEditor` 与 `TokenExpressionEditor` 保持字段浏览器/编辑器双列，780px 以下改为单列；预览内容允许断词，不得把页面撑宽。

- [x] **Step 4：补键盘、英语和深色回归**

运行现有纯键盘令牌插入、焦点归还、模态底部操作栏测试；将一个 900×768 状态切换到英文并断言主要动作全部可见，再以深色主题执行 DWG 命名状态。只断言可见性、可达性和无溢出，不以固定文本像素宽度制造平台脆弱测试。

- [x] **Step 5：运行 Task 3 门禁并提交**

```powershell
Set-Location web
npm run test:unit
npm run check:i18n
npm run check:ui
npx playwright test tests/e2e/standards-welcome.spec.ts tests/e2e/standards-editor.spec.ts tests/e2e/standards-visual-evidence.spec.ts --workers=1
npm run build
```

Expected: 全部通过；900×768 页面无横向滚动；200% 缩放操作栏可达；宽表只在自身容器滚动。

```powershell
git add web/src/components/standards/StandardEditor.vue web/src/components/standards/StandardSectionNav.vue web/src/components/standards/OrdinaryPropertyEditor.vue web/src/components/standards/DerivedPropertyEditor.vue web/src/components/standards/DwgNamingEditor.vue web/tests/e2e/standards-editor.spec.ts web/tests/e2e/standards-visual-evidence.spec.ts changelog.md
git commit -m "收敛标准编辑器响应式布局"
```

---

### Task 4：候选视觉裁决、证据重建与计划收口

**Files:**
- Modify: `web/tests/e2e/standards-visual-evidence.spec.ts`
- Create: `.planning/memos/dst-manager/assets/PLAN-DM-039/README.md`
- Create: `.planning/memos/dst-manager/assets/PLAN-DM-039/*.png`
- Modify: `docs/dst-manager/specs/assets/SPEC-DM-016/README.md`
- Replace: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-01-welcome-light-1440x900.png`
- Replace: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-09-welcome-dark-1440x900.png`
- Create: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-03-ordinary-light-1440x900.png`
- Create: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-04-derived-light-1440x900.png`
- Create: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-05-dwg-naming-light-1440x900.png`
- Create: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-12-dwg-naming-narrow-light-900x768.png`
- Delete: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-03-properties-light-1440x900.png`
- Delete: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-04-mapping-light-1440x900.png`
- Delete: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-05-composition-light-1440x900.png`
- Delete: `docs/dst-manager/specs/assets/SPEC-DM-016/g4-12-mapping-narrow-light-900x768.png`
- Replace/Create/Delete: `docs/dst-manager/specs/assets/SPEC-DM-016/production/` 中对应同名状态
- Modify: `.planning/plans/dst-manager/PLAN-DM-039-standard-platform-ui-visual-closure.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Tasks 1–3 已通过的结构/响应式门禁、两个 HTML Demo、现有 G4/G8 证据生成器。
- Produces: PLAN-DM-039 候选证据、用户裁决记录、新命名的 G4/G8 状态集、无自相矛盾的证据 README 与最终验证摘要。

- [x] **Step 1：让证据生成器支持独立候选目录**

扩展现有环境变量分支：

```ts
const EVIDENCE_DIR = EVIDENCE_TARGET === "plan-dm-039"
  ? path.resolve(process.cwd(), "..", ".planning", "memos", "dst-manager", "assets", "PLAN-DM-039")
  : EVIDENCE_TARGET === "production"
    ? path.join(EVIDENCE_ROOT, "production")
    : EVIDENCE_TARGET === "g4" ? EVIDENCE_ROOT : null;
```

候选模式只写 memo 资产目录，绝不覆盖 G4/production。README 记录 commit、视口、主题、数据夹具、生成命令和每张截图对应的 Demo 状态。

- [x] **Step 2：生成候选证据并逐张打开检查**

```powershell
Set-Location web
$env:DST_MANAGER_STANDARDS_EVIDENCE = "plan-dm-039"
npx playwright test tests/e2e/standards-visual-evidence.spec.ts --workers=1
Remove-Item Env:\DST_MANAGER_STANDARDS_EVIDENCE
```

Expected: 候选目录包含欢迎页浅/深、标准库、普通属性、派生属性、DWG 命名、模板资产、发布错误/成功和 900×768 DWG 命名状态。逐张检查空白、裁切、加载中、错误窗口和焦点闪烁；不合格截图必须先修代码再重抓。

- [x] **Step 3：执行 Demo 对照并等待用户视觉裁决**

对照矩阵：

| 候选状态 | 权威对照 | 必须确认 |
| --- | --- | --- |
| 欢迎页 1440×900 浅/深 | SPEC-DM-016 Welcome Demo | 约 2:1、唯一主动作、三个次级任务、层级/留白 |
| 普通属性 1440×900 | SPEC-DM-017 Editor Demo | 独立工作台、导航宽度、身份区、八列表格密度 |
| 派生属性 1440×900 | SPEC-DM-017 Editor Demo | 七列层级、编辑动作、说明/摘要不抢宽度 |
| DWG 命名 1440×900 与 900×768 | SPEC-DM-017 Editor Demo | 字段浏览器、令牌、预览和响应式状态 |

将差异和裁决写入 PLAN-DM-039 资产 README。**用户未明确确认前不得执行 Step 4，不得用自动测试通过代替该裁决。** 若用户否决任一状态，返回所属 Task 修正并重新生成全部受影响候选截图。

- [x] **Step 4：用户确认后重建 G4 与 G8**

```powershell
Set-Location web
$env:DST_MANAGER_STANDARDS_EVIDENCE = "g4"
npx playwright test tests/e2e/standards-visual-evidence.spec.ts --workers=1
$env:DST_MANAGER_STANDARDS_EVIDENCE = "production"
npx playwright test tests/e2e/standards-visual-evidence.spec.ts --workers=1
Remove-Item Env:\DST_MANAGER_STANDARDS_EVIDENCE
```

删除四张被新六分区取代的旧文件，更新 README 清单。对同名 G4/G8 执行 SHA-256 或像素 diff；任何非零差异必须定位并裁决，不能只写“可接受”。欢迎页和四张新编辑状态必须额外链接用户在 Step 3 的 Demo 对照结论。

- [x] **Step 5：运行完整前端门禁**

```powershell
Set-Location web
npm ci
npm run test:unit
npm run check:api
npm run check:i18n
npm run check:ui
npm run build
npm run test:e2e
```

Expected: 全部退出码为 0；记录准确 passed/skipped/flaky 数，不得只写“通过”。本计划未修改 Python；仍运行 `uv run ruff check .` 作为仓库基线，`pytest` 可按根计划收口策略执行全量或说明为何仅运行前端。

- [ ] **Step 6：执行真实 Windows WebView2 视觉检查**

至少检查浅/深主题下的 100%、125%、150%、200%：欢迎页、普通属性、DWG 命名、组合模态和发布检查。记录窗口尺寸、系统缩放、是否出现裁切/页面级横向滚动、键盘是否可达。该步骤不需要 AutoCAD；若环境无法执行，计划不得标记 `completed`，状态保持 `active` 并明确恢复条件。

- [x] **Step 7：更新文档、changelog 与实际验证摘要**

- SPEC-DM-016 证据 README 删除“PLAN-DM-038 新状态尚未生成”和旧“无差异”结论，改为 PLAN-DM-039 的实际裁决。
- `docs/dst-manager/README.md` 与计划索引链接 PLAN-DM-039，并说明它只收口 UI/证据，不改变标准领域能力。
- 每一轮实现均在 `changelog.md` 当前日期章节追加可核验记录。
- 所有自动化、候选裁决与 WebView2 检查完成后，才把本计划状态改为 `completed`；否则保持 `active`，不能由“用户暂时接受”替代缺失证据。

- [x] **Step 8：提交证据与计划收口**

```powershell
git add web/tests/e2e/standards-visual-evidence.spec.ts .planning/memos/dst-manager/assets/PLAN-DM-039 docs/dst-manager/specs/assets/SPEC-DM-016 .planning/plans/dst-manager/PLAN-DM-039-standard-platform-ui-visual-closure.md .planning/plans/dst-manager/README.md docs/dst-manager/README.md changelog.md
git commit -m "重建标准平台视觉证据并收口验收"
```

## 验证矩阵

| 层级 | 命令/证据 | 通过条件 |
| --- | --- | --- |
| 导航模型 | `npm run test:unit -- src/composables/useStartNavigation.test.ts` | browse/import 意图稳定，回欢迎页清除意图 |
| 欢迎页流程 | `standards-welcome.spec.ts` | 唯一主动作、三次级入口、无壳路径、DST 打开、900×768 |
| 标准库/编辑器 | `standards-library.spec.ts`、`standards-editor.spec.ts` | 两种页面模式互斥、返回恢复、dirty 门禁、六分区不回归 |
| 发布与资产 | `standards-assets-publish.spec.ts` | 发布检查、资产检查、成功后只读不回归 |
| 静态门禁 | `check:api`、`check:i18n`、`check:ui`、`build` | 退出码 0，无新例外掩盖 |
| 视觉候选 | `DST_MANAGER_STANDARDS_EVIDENCE=plan-dm-039` | 每张有效并完成 Demo 对照，用户明确裁决 |
| G4/G8 | 同状态双次生成 + SHA-256/像素 diff | 同名状态一致，且 G4 已由用户认可 |
| 桌面缩放 | WebView2 100/125/150/200% | 无裁切、页面级横向滚动或不可达操作 |

## 风险与控制

- **把视觉修复扩大成业务开发：** 创建入口只能进入既有占位；导入只复用现有对话框。PLAN-DM-036、Schema 和 API 均不在范围内。
- **编辑模式卸载标准库导致状态丢失：** store 与筛选 refs 继续由 `StandardsView` 持有，仅条件渲染子组件；E2E 锁定返回后的选择与详情。
- **宽表为了“无溢出”被压到不可读：** 页面无横向滚动不等于表格无滚动；普通属性表使用局部滚动和稳定最小宽度。
- **证据再次自证：** 候选目录与 G4/G8 分离；用户先对照 Demo 裁决，确认后才能晋升冻结件。
- **WebView2 与浏览器渲染差异：** 自动化不能替代真实缩放；缺少桌面证据时计划保持 active。

## 完成标准

- 欢迎页在标准视口呈现约 2:1 双栏，在 900×768 单列，打开 DST 是唯一 primary，三个次级入口行为符合既有边界。
- 草稿编辑器不再与标准库并列，独立占用标准页内容宽度；返回后选择、筛选、详情和 dirty 门禁保持正确。
- 普通/派生/DWG 命名在标准、900×768 和 200% 状态下可读、可操作、无页面级横向溢出。
- 新 G4/G8 清单使用六分区文件名，旧四张状态删除，README 不再包含“尚未生成却无视觉差异”的矛盾结论。
- 用户完成两个 Demo 的候选视觉裁决；真实 WebView2 100/125/150/200% 检查有记录。
- 前端全量门禁与仓库 Ruff 基线通过，实际数字写入计划和 changelog；没有未说明的跳过项。

## 实际验证摘要（2026-09-23）

**Task 1–3 已全部完成**（各步骤已在正文勾选）；**Task 4 已完成 Step 1–5、7、8；仅 Step 6
（真实 Windows WebView2 100/125/150/200% 检查）待用户执行**。因此本计划状态为 `active`，
不因自动化全绿而提前关闭。

### 实施提交

| 提交 | 内容 |
| --- | --- |
| `02ef5d0` | 重建打开优先欢迎页双栏（Task 1） |
| `3f4e270` | 拆分标准库与全宽编辑工作台（Task 2） |
| `20c7ac4` | 收敛标准编辑器响应式布局（Task 3） |
| `7375c95` | 生成候选证据并修正窄视口操作行（Task 4 首轮候选） |
| `0fd0aaf` | 按 Demo 修正属性表标签重复与欢迎页任务说明（用户第一轮裁决） |
| `6d9c7e7`、`4c9bcaa` | 枚举值改为点击摘要进入编辑（用户第二轮裁决） |
| 本轮收口 | G4/G8 重建、证据 README、索引与计划收口（Task 4 Step 4/5/7/8） |

### 门禁实测数字

| 门禁 | 结果 |
| --- | --- |
| `npm ci` | 成功 |
| `npm run test:unit` | 26 文件 / **275 passed** / 0 failed |
| `npm run check:api` | 退出码 0 |
| `npm run check:i18n` | **1305 键 / 10 域**，无未登记硬编码中文 |
| `npm run check:ui` | 退出码 0（无新增例外；新增 `--standards-table-min-width`、`--standards-hint-min-width` 两个令牌） |
| `npm run build` | 退出码 0（仅既有 chunk 体积警告） |
| `npm run test:e2e` | **630 passed / 0 failed / 0 flaky**（4.3 分钟，workers=4） |
| `uv run ruff check .` | 退出码 0 |
| `uv lock --check` | 通过（70 包） |
| `uv run pytest -q` | collected **1700** / **1628 passed** / **72 skipped** / 0 failed / 0 errors（与 PLAN-DM-038 基线逐值一致；本计划未改 Python） |

### 视觉证据与用户裁决

- 候选证据（12 张）与逐轮裁决记录：[`.planning/memos/dst-manager/assets/PLAN-DM-039/`](../../../.planning/memos/dst-manager/assets/PLAN-DM-039/README.md)。
- 用户共三轮裁决：第一轮否决（要求以 Demo 为准，普通/派生属性表拥挤错位）→ 第二轮指出枚举入口不是独立按钮 → **第三轮通过**。
- G4 与 G8 各 12 张已重建，逐对 SHA-256 **12/12 完全一致（0 处差异）**；四个旧状态文件（`g4-03-properties`、`g4-04-mapping`、`g4-05-composition`、`g4-12-mapping-narrow`）已删除。
- 证据 README：[`docs/dst-manager/specs/assets/SPEC-DM-016/README.md`](../../../docs/dst-manager/specs/assets/SPEC-DM-016/README.md)；其 §三之二 记录本轮 Demo 对照裁决。

### 已登记的偏差与裁决（见 SDD ledger 全文）

1. **标准页宽度收缩的根因不在编辑器**：壳层 `main` 是列向 flex 容器，`.standards-page` 的 `margin:0 auto` 使子项按内容宽度收缩（实测标准库模式仅 666px）；补 `width:100%` 后由 `max-width` 成为唯一上限。属修正，但会改变标准库截图（已随本轮 G4/G8 重建）。
2. **计划 Files 清单与实际改动点的两处不一致**：`StandardSectionNav.vue` 的响应式改造落在 Task 3；`DwgNamingEditor.vue` 不含双列布局，实际改的是 `TokenExpressionEditor.vue`。
3. **计划外的两处必要改动**：`StandardLibraryPane.vue` 增加 `data-testid="library-list"`（英文场景下按中文区域名定位会永远解析不到元素）；`main.spec.ts` 两条 PLAN-DM-029 遗留用例从旧单卡片（`.welcome-card` 520px 上限）改为新双栏页（页宽上限取 `--shell-content-max-width`、可读文本上限取 `--welcome-path-max-width`）。
4. **已删除的死键**：`standards.ordinary.editEnum`（枚举入口合并为摘要触发器后不再使用）。
5. **待执行**：Step 6 真实 Windows WebView2 浅/深 × 100/125/150/200% 检查（欢迎页、普通属性、DWG 命名、组合模态、发布检查）；恢复条件为在装有 WebView2 的 Windows 桌面启动 `uv run dst-manager desktop` 后逐项记录窗口尺寸、缩放、裁切与键盘可达性。未执行前本计划保持 `active`。
