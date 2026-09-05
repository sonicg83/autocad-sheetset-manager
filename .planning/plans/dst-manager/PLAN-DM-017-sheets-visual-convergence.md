---
id: PLAN-DM-017
title: DST Manager 图纸工作区与任务浮层视觉收敛整改计划
status: completed
document_kind: plan
owners:
  - dst-manager
created: 2026-09-05
updated: 2026-09-05
related:
  - SPEC-DM-006
  - SPEC-DM-009
  - PLAN-DM-013
  - PLAN-DM-015
---

# DST Manager 图纸工作区与任务浮层视觉收敛整改计划

> **执行代理：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务实施；每个生产改动遵循测试先红、实现转绿、重构保持绿灯。复选框用于记录执行状态。本计划只编制整改步骤，不自动提交 Git。

**目标：** 在不改变 HTTP/SSE、草稿命令、桌面壳桥和发布安全门禁的前提下，使图纸工作区的布局、控件、表格、交互状态和右侧任务面板与 SPEC-DM-009 Demo 的浅深主题视觉及行为一致。

**架构：** 继续使用 Vue 3 scoped CSS 与 SPEC-DM-006 已声明的语义令牌，不引入第三方 UI 框架。图纸页拆为活动编辑卡片和图纸列表卡片；表格通过确定列宽和容器断点保证内部滚动、不互相覆盖；任务浮层拆为常驻右缘入口栏与不参与 flex 布局的 fixed 覆盖面板。

**技术栈：** Vue 3、TypeScript、Vite、Playwright、pywebview/WebView2；Python 3.12+ 与 UV 仅用于既有契约和桌面壳回归。

**规范：** [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §4.1/§4.3/§5/§6 与 [SPEC-DM-009](../../../docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md) §3/§5/§6、S-13～S-17；视觉目标为 [SPEC-DM-009 HTML Demo](../../../docs/dst-manager/mockups/SPEC-DM-009-sheets-demo.html)。

## 全局约束

- Windows 11、PowerShell、Python 3.12+；命令通过 `rtk` 执行，Python 依赖继续由 UV 管理，Web 依赖继续由 npm lockfile 管理。
- 不新增 npm/Python 依赖，不修改 HTTP/SSE、OpenAPI、草稿命令、DST/DWG、SQLite 或 CAD Worker。
- 只使用 SPEC-DM-006 §5 已声明且浅深主题均有值的令牌；不得新增裸十六进制组件色值，不得依赖无效 CSS 变量回退。
- 用户截图只用于本地视觉核对，不复制到公开测试夹具；自动化使用 `web/tests/e2e/fixtures/sheets.ts` 的虚构数据。
- 保留未提交输入保护、草稿投影、任务页签自动激活、toast 抑制、诊断复制和 ActionDock 门禁。
- 视觉验收必须比较相同视口、相同主题、相同展开状态的 Demo 与实现；截图不是行为测试的替代品。

---

## 任务 1：统一令牌消费并建立控件视觉基线

**文件：**

- 修改：`web/src/style.css`
- 修改：`web/src/components/sheets/SheetTree.vue`
- 修改：`web/src/components/SheetTable.vue`
- 修改：`web/src/components/sheets/SheetOperationForm.vue`
- 修改：`web/src/views/SheetsView.vue`
- 修改：`web/tests/e2e/sheets-visual-regressions.spec.ts`

**接口：**

- 消费：SPEC-DM-006 已声明的 `--color-bg-canvas`、`--color-bg-surface`、`--color-bg-muted`、`--color-border-subtle`、`--color-border-strong`、`--color-info-bg`、`--color-warning-bg`、`--color-danger-bg`、`--color-focus`。
- 产出：图纸页所有可见背景、边框和状态色均能从已声明令牌解析；后续任务不再使用 `--color-bg-surface-2`、`--color-border`、`--color-accent-soft`、`--color-bg-hover`、`--color-warning-soft`、`--color-danger-soft`。

- [x] **步骤 1：为真实计算样式写失败断言**

  在 `sheets-visual-regressions.spec.ts` 增加浅深主题循环，读取操作表单输入框、表头、正文行、分割线和树节点的 `getComputedStyle`；断言输入框高度处于 `36–40px`、表头背景不同于正文、边框颜色非透明，并断言下列变量在组件节点上均为空，证明组件未再依赖这些未声明别名：

  ```ts
  const forbidden = [
    "--color-bg-surface-2", "--color-border", "--color-accent-soft",
    "--color-bg-hover", "--color-warning-soft", "--color-danger-soft",
  ];
  const values = await form.evaluate((el, names) =>
    names.map(name => getComputedStyle(el).getPropertyValue(name).trim()), forbidden);
  expect(values).toEqual(forbidden.map(() => ""));
  ```

- [x] **步骤 2：运行用例并确认先红**

  运行：

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-visual-regressions.spec.ts --workers=1
  ```

  预期：至少因当前输入框高度/边框、表头背景或分割线不可辨识而失败；若全部通过，收紧断言到 Demo 的实际计算样式后重新确认失败。

- [x] **步骤 3：替换未定义令牌并收敛全局控件规则**

  在上述组件中按以下映射替换，不创建同义别名：

  ```text
  --color-bg-surface-2 → --color-bg-muted
  --color-border       → --color-border-subtle
  --color-accent-soft  → --color-info-bg
  --color-bg-hover     → --color-bg-muted
  --color-warning-soft → --color-warning-bg
  --color-danger-soft  → --color-danger-bg
  ```

  将 `style.css` 中无作用域的按钮/输入规则限制为基础 reset；具体高度、层级和状态交给组件类，避免 `button,a` 的 padding 再次覆盖图标按钮、页签和文字链接。保留 `box-sizing`、字体继承、主题 color-scheme 与通用 `focus-visible`。

- [x] **步骤 4：运行视觉基线与既有外壳回归**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-visual-regressions.spec.ts main.spec.ts --workers=1
  ```

  预期：新增计算样式断言转绿；顶栏、模态、ActionDock、任务页签和图纸页既有行为继续通过。

## 任务 2：把操作表单与图纸列表拆成上下独立卡片

**文件：**

- 修改：`web/src/views/SheetsView.vue`
- 修改：`web/src/components/sheets/SheetOperationForm.vue`
- 修改：`web/tests/e2e/sheets-layout.spec.ts`
- 修改：`web/tests/e2e/sheets-forms.spec.ts`

**接口：**

- 消费：既有 `operationContext`、`editContext` 与 `openOperation/operationSubmit/operationCancel` 事件，不改变事件签名。
- 产出：`.sheet-editor-card`（仅活动编辑时存在）和 `.sheet-list-card`（始终存在）；`SheetToolbar` 与 `SheetTable` 始终位于列表卡片内。

- [x] **步骤 1：写 DOM 归属与几何顺序失败测试**

  在 `sheets-layout.spec.ts` 打开“编辑子集”“新增图纸”“新建子集”，分别断言：

  ```ts
  const editor = page.locator(".sheet-editor-card");
  const list = page.locator(".sheet-list-card");
  await expect(editor).toHaveCount(1);
  await expect(list.locator(".sheets-toolbar")).toHaveCount(1);
  await expect(editor.locator(".sheets-toolbar")).toHaveCount(0);
  const [editorBox, listBox] = await Promise.all([editor.boundingBox(), list.boundingBox()]);
  expect(editorBox!.bottom).toBeLessThanOrEqual(listBox!.top + 1);
  ```

  关闭操作表单后断言 `.sheet-editor-card` 不存在、`.sheet-list-card` 填满剩余高度。

- [x] **步骤 2：运行用例并确认先红**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-layout.spec.ts --grep "独立编辑卡片" --workers=1
  ```

  预期：当前 DOM 没有两个独立卡片，测试失败。

- [x] **步骤 3：重排 SheetsView 结构**

  将右侧结构调整为：

  ```vue
  <main class="sheets-main">
    <section v-if="operationContext || editContext" class="sheet-editor-card">
      <SheetOperationForm v-if="operationContext" ... />
      <SheetPropertyEditor v-else-if="editContext?.kind === 'sheet'" ... />
    </section>
    <section class="sheet-list-card">
      <SheetToolbar ... />
      <!-- notice / selection / empty state / SheetTable -->
    </section>
  </main>
  ```

  编辑卡片 `flex:none`、列表卡片 `flex:1; min-height:0`；两者各自使用 surface、border、radius，列表工具栏与表格之间不再插入操作表单。

- [x] **步骤 4：保持业务事件与未提交保护转绿**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-layout.spec.ts sheets-forms.spec.ts sheets-editing.spec.ts --workers=1
  ```

  预期：三类表单位置断言、提交/取消、字段错误、参照失效和未提交输入保护全部通过。

## 任务 3：统一三类操作表单的输入、下拉和动作层级

**文件：**

- 修改：`web/src/components/sheets/SheetOperationForm.vue`
- 修改：`web/tests/e2e/sheets-visual-regressions.spec.ts`
- 修改：`web/tests/e2e/sheets-forms.spec.ts`

**接口：**

- 消费：任务 1 的规范令牌和任务 2 的 `.sheet-editor-card`。
- 产出：桌面最多两列的 `.form-body`、统一 `.form-control`、Primary“加入草稿”、Secondary“取消”和独立 `.form-danger`。

- [x] **步骤 1：写控件尺寸、列数和按钮层级失败测试**

  对三种操作态分别断言所有可见 `input/select` 的高度在 `36–40px`、边框半径一致；通过首行字段的 `top` 值集合证明 1440px 下最多两列；断言提交按钮具有 `.primary`，危险按钮不与页脚主按钮同行。

- [x] **步骤 2：运行并确认当前原生控件和 auto-fill 网格失败**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-visual-regressions.spec.ts --grep "操作表单控件" --workers=1
  ```

  预期：当前 `auto-fill` 多列、原生控件高度或主按钮层级至少一项失败。

- [x] **步骤 3：实现统一表单视觉**

  为操作表单内 `input/select` 统一应用：

  ```css
  .operation-form :is(input:not([type="checkbox"]),select,textarea){
    width:100%;height:38px;min-width:0;padding:6px 10px;
    color:var(--color-text-primary);background:var(--color-bg-surface);
    border:1px solid var(--color-border-strong);border-radius:var(--radius-md);
  }
  .operation-form :is(input,select,textarea):focus-visible{
    outline:2px solid var(--color-focus);outline-offset:2px;
  }
  .form-body{grid-template-columns:repeat(2,minmax(0,1fr));}
  ```

  900px 韧性视口切为一列；给提交按钮增加 `primary`，将状态、页脚和危险区的分隔线改用 `--color-border-subtle`。

- [x] **步骤 4：运行三类表单与视觉回归**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-forms.spec.ts sheets-visual-regressions.spec.ts --workers=1
  ```

  预期：功能和视觉断言同时通过。

## 任务 4：建立确定列宽并消除导航拖拽后的表格重叠

**文件：**

- 修改：`web/src/components/SheetTable.vue`
- 修改：`web/src/composables/useSheetColumns.ts`
- 修改：`web/tests/e2e/sheets-layout.spec.ts`
- 修改：`web/tests/e2e/sheets-columns.spec.ts`

**接口：**

- 消费：`SheetColumn[]` 与现有显示列偏好，不改变持久化键、内置列 key 或自定义属性身份。
- 产出：`columnWidth(column): number`、`tableMinWidth`；选择/图号左侧固定，操作列仅在容器足够宽时固定。

- [x] **步骤 1：写三档树宽与浮层展开的无重叠失败断言**

  在 1440×900 深色主题下依次将分隔条设置为 260/320/420px，并在最后一次展开任务浮层。对表头和第一行所有可见单元格取得矩形，断言相邻单元格不交叠：

  ```ts
  const rects = await page.locator(".sheet-table-window tbody tr").first()
    .locator("td").evaluateAll(cells => cells.map(cell => {
      const r = cell.getBoundingClientRect();
      return {left:r.left,right:r.right,width:r.width};
    }));
  for (let i = 1; i < rects.length; i++) {
    expect(rects[i].left).toBeGreaterThanOrEqual(rects[i - 1].right - 1);
  }
  ```

  同时断言 `documentElement.scrollWidth <= viewport.width` 且 `.sheet-table-window.scrollWidth > clientWidth` 时滚动只属于表格窗口。

- [x] **步骤 2：运行并确认重叠场景先红**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-layout.spec.ts --grep "导航拖拽后表格列不重叠" --workers=1
  ```

  预期：420px 树宽或浮层展开状态下，当前 sticky 操作列与中间列发生几何重叠。

- [x] **步骤 3：实现列宽模型和容器级 sticky 降级**

  在 `SheetTable.vue` 为每列输出 `<colgroup>`，按以下初始宽度计算表格最小宽度：选择 40、图号 72、标题 270、子集 220、文件名 260、布局 160、状态 96、操作 150、自定义属性 140px。表格使用 `table-layout:fixed`，标题允许两行，其余短列不换行。

  为 `.sheet-table-window` 设置 `container-type:inline-size`；容器小于能同时容纳左右固定列及一个 420px 中间阅读区时，将操作列改为普通列：

  ```css
  @container (max-width: 682px){
    th.col-actions,td.col-actions{position:static;}
  }
  ```

  固定列背景必须不透明并带边界/滚动阴影，避免滚动内容透出造成视觉重叠。

- [x] **步骤 4：运行列配置、导航和布局回归**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-columns.spec.ts sheets-navigation.spec.ts sheets-layout.spec.ts --workers=1
  ```

  预期：显示列偏好、固定列不可隐藏、三档树宽和任务浮层展开几何断言全部通过。

## 任务 5：补齐树与表格的 hover、焦点、当前对象和勾选状态

**文件：**

- 修改：`web/src/components/sheets/SheetTree.vue`
- 修改：`web/src/components/SheetTable.vue`
- 修改：`web/tests/e2e/sheets-navigation.spec.ts`
- 修改：`web/tests/e2e/sheets-visual-regressions.spec.ts`

**接口：**

- 消费：现有 `scope`、`focusedSheetId`、`selectedIds`；不合并三种业务状态。
- 产出：树 `.active/.focused` 与表格 `.focused/.selected/:hover/:focus-within` 的独立视觉反馈。

- [x] **步骤 1：写鼠标和键盘状态的失败测试**

  用 `locator.hover()`、树节点点击、图纸定位和复选框勾选分别采集背景色，断言：

  - 普通 hover 背景不同于默认背景；
  - 当前子集为强调色实底，当前图纸为强调色软底；
  - 勾选行获得 `.selected`，取消后移除；
  - `focused` 与 `selected` 可并存；
  - 键盘 `focus-visible` 仍有非零 outline，状态不只靠颜色。

- [x] **步骤 2：运行并确认 hover/selected 先红**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-visual-regressions.spec.ts --grep "交互状态" --workers=1
  ```

  预期：当前表格没有行 hover，也没有将 `selectedIds` 映射为行 class，测试失败。

- [x] **步骤 3：实现状态 class 与规范令牌背景**

  表格行绑定：

  ```vue
  <tr :class="{
    focused: row.sheet.id === focusedSheetId,
    selected: selectedIds.includes(row.sheet.id),
  }">
  ```

  使用 `--color-bg-muted` 表达 hover，使用 `--color-info-bg` 表达 focused/selected，并确保 sticky 单元格继承该行的状态背景。树当前子集使用 `--color-accent` + `--color-on-accent`，当前图纸使用 `--color-info-bg` + `--color-accent`；保留文字、层级与键盘焦点轮廓。

- [x] **步骤 4：运行导航、选择和视觉回归**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-navigation.spec.ts sheets-visual-regressions.spec.ts --workers=1
  ```

  预期：业务选择语义不变，四种视觉状态均可观察。

## 任务 6：将任务浮层改为固定入口栏与悬浮覆盖面板

**文件：**

- 修改：`web/src/App.vue`
- 修改：`web/src/layout/TaskOverlay.vue`
- 修改：`web/src/style.css`
- 修改：`web/tests/e2e/main.spec.ts`
- 修改：`web/tests/e2e/sheets-layout.spec.ts`
- 修改：`web/tests/e2e/sheets-visual-regressions.spec.ts`

**接口：**

- 消费：现有 `open`、`tab` props 与 `update:tab`、`fold`、`retry`、修复事件；不改变任务数据和自动激活规则。
- 产出：`.task-overlay` 继续作为常驻 `complementary` landmark，但只占 `44–48px`；内部 `.task-rail` 提供入口，`.task-drawer` 使用 fixed 覆盖，展开前后 `.shell-main` 几何边界不变。

- [x] **步骤 1：写展开前后主内容不移动的失败测试**

  在 1024/1120/1440px、浅深主题下记录展开前 `.shell-main` 和 `.sheets-workspace` 的 `left/right/width/scrollTop`，展开后断言误差不超过 1px；同时断言抽屉覆盖主内容、入口栏仍可见、抽屉上边界低于顶栏且下边界高于 ActionDock。

- [x] **步骤 2：写 Esc、Tab 困绕与焦点归还失败测试**

  从右缘入口打开“修改预览”，断言焦点进入活动页签；连续 `Tab/Shift+Tab` 不离开抽屉；按 `Escape` 后抽屉关闭且焦点回到对应入口按钮。任务执行、toast 抑制和诊断红点继续使用既有断言。

- [x] **步骤 3：运行并确认宽屏挤压和焦点行为先红**

  ```powershell
  rtk npm --prefix web run test:e2e -- sheets-layout.spec.ts main.spec.ts --grep "任务浮层" --workers=1
  ```

  预期：1440px 下 `.task-overlay` 仍作为 340px flex 子项挤压 `.shell-main`，几何断言失败；当前组件没有完整 Esc/焦点归还，键盘断言失败。

- [x] **步骤 4：重构 TaskOverlay 的壳层结构**

  根节点只保留常驻入口栏宽度；展开内容成为入口栏左侧 fixed 面板：

  ```vue
  <aside class="task-overlay" role="complementary" aria-label="任务浮层">
    <nav class="task-rail" aria-label="任务入口">
      <button v-for="item in OV_TABS" :aria-expanded="open && active===item.id" ... />
    </nav>
    <section v-if="open" ref="drawer" class="task-drawer"
      role="region" :aria-label="activeTabLabel" @keydown="onDrawerKeydown">
      <!-- 页签标题与现有 ov-body -->
    </section>
  </aside>
  ```

  样式目标：

  ```css
  .task-overlay{flex:0 0 48px;position:relative;z-index:100;}
  .task-rail{width:48px;height:100%;}
  .task-drawer{
    position:fixed;right:48px;top:104px;bottom:62px;
    width:min(390px,calc(100vw - 48px));z-index:100;
    background:var(--color-bg-surface);
    border-left:1px solid var(--color-border-subtle);
    box-shadow:var(--shadow-3);
  }
  ```

  点击关闭状态的页签先激活该页签再触发既有 `fold`；打开后用现有 DOM 顺序实现 Tab 困绕，`Escape` 触发关闭并将焦点归还该页签按钮。`prefers-reduced-motion` 下关闭抽屉过渡。

  `activeTabLabel` 由现有 `OV_TABS` 派生，不建立第二份文案映射：

  ```ts
  const activeTabLabel = computed(() => OV_TABS.find(item => item.id === active.value)?.label ?? "任务详情");
  ```

- [x] **步骤 5：运行浮层、任务和布局回归**

  ```powershell
  rtk npm --prefix web run test:e2e -- main.spec.ts sheets-layout.spec.ts sheets-visual-regressions.spec.ts --workers=1
  ```

  预期：三档正式宽度和 900px 韧性宽度均覆盖而不挤压，任务页签自动激活、修复入口、诊断复制和 ActionDock 不回归。

## 任务 7：同视口设计 QA、文档收口与完整验证

**文件：**

- 修改：`design-qa.md`
- 修改：`.planning/memos/dst-manager/PLAN-DM-015-sheets-workspace-ui-review.md`
- 修改：`.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md`
- 修改：`.planning/plans/dst-manager/PLAN-DM-017-sheets-visual-convergence.md`
- 修改：`.planning/plans/dst-manager/README.md`
- 修改：`docs/dst-manager/README.md`
- 修改：`changelog.md`

**接口：**

- 消费：任务 1～6 的测试和实现、SPEC-DM-009 Demo。
- 产出：同状态视觉证据、完整验证记录和可追溯计划状态。

- [x] **步骤 1：生成规定状态的实现截图**

  使用 `sheets-layout.spec.ts` 的虚构夹具生成 1440×900 浅/深主题下：默认、编辑子集、新增图纸、新建子集、表格 hover、表格选中、任务浮层展开；另生成 1024×768 和 1120×768 的浮层展开，以及 900×768 深色韧性截图。

- [x] **步骤 2：按相同视口和状态执行设计 QA**

  将 Demo 截图与最新实现截图放入同一比较输入，逐项核对卡片边界、字段位置、控件高度、表头/分割线、hover/选中背景、抽屉遮盖、字体、间距、圆角和深色层级。P0/P1/P2 未清零时继续回到对应任务修复；`design-qa.md` 只有在相同状态比较通过后才可写 `final result: passed`。

- [x] **步骤 3：运行生产构建和完整 Web 回归**

  ```powershell
  rtk npm --prefix web run build
  rtk npm --prefix web run test:e2e -- --workers=1
  ```

  预期：TypeScript/Vite 构建退出码 0，Playwright 0 failed；记录实际通过数量，不沿用历史数字。

- [x] **步骤 4：运行仓库级静态与相关 Python 回归**

  ```powershell
  $env:UV_LINK_MODE = "copy"
  rtk uv run ruff check .
  rtk uv run pytest -q tests/test_shell.py tests/test_shell_workspace.py
  rtk uv lock --check
  ```

  预期：Ruff、壳桥相关 pytest 与 lock 检查退出码均为 0；真实 Windows Explorer 选中 DST 仍单独记录为人工验收，不用 mock 代替。

- [x] **步骤 5：更新计划状态与索引**

  将本计划的实际命令、通过数量、视觉证据和任何跳过项写入“实际验证”。只有 S-13～S-17、构建和回归全部通过时，才把 PLAN-DM-017 标记为 `completed`，并把 PLAN-DM-015 的 S-07 标记为通过；若 S-09 真实 Explorer 验收仍未执行，PLAN-DM-015 继续保持 `active`。

## 风险与控制

- **全局 CSS 回归：** `style.css` 仍服务属性页、修订页和外壳；每次收敛全局规则都同时运行 `main.spec.ts`，不要一次性重写整个样式文件。
- **sticky 列遮盖：** 不能只断言页面无横向溢出；必须检查非冻结列顺序、操作列右边界和内部横向滚动。表格横向溢出时固定右侧操作列，完整容纳时恢复普通列。
- **浮层焦点回归：** fixed 定位不等于可访问抽屉；Esc、焦点困绕、归还和任务自动激活必须作为行为门禁。
- **截图误判：** 自动截图附件不等于视觉通过；必须把 Demo 与实现置于同一比较输入，并覆盖 hover/选中/展开等动态状态。
- **脏工作区：** 执行前再次检查 `git status --short`，保留当前 PLAN-DM-015 整改和用户已有改动，只暂存本计划实际修改的文件。

## 完成标准

- SPEC-DM-009 S-13～S-17 全部有自动化行为证据和同状态视觉证据。
- 任务浮层在 900/1024/1120/1440px 下展开前后主内容几何不变，入口栏常驻，Esc 与焦点归还正确。
- 导航宽度 260/320/420px 下表格列无重叠，用户已选列不被自动隐藏，横向滚动不扩散到页面。
- 三类操作表单位于独立编辑卡片，控件、表格、树的浅深主题和交互态与 Demo 对齐。
- `design-qa.md` 为 `final result: passed`，生产构建、完整 Playwright、Ruff、相关 pytest 与 `uv lock --check` 均有本次新鲜通过记录。

## 实际验证

2026-09-05 开始实施，状态为 `active`，未自动提交 Git。

- 任务 1：计算样式测试先红（2 failed / 6 passed），确认输入高度 21px、圆角与分隔线失效、树当前节点透明。令牌替换及局部控件修复后通过；审查再发现全局按钮 reset 的旧组件回归，补充工具栏、属性/CSV、恢复横幅、草稿浮窗、任务重试、修订恢复及属性编辑页脚的受控样式基线。两轮修复均有先红证据，最终 `rtk npm --prefix web run test:e2e -- sheets-visual-regressions.spec.ts main.spec.ts --workers=1` 为 **70 passed**，复审通过。
- 执行裁定：任务清单遗漏的 `SheetToolbar`、`ColumnSettings`、`SheetPropertyEditor` 也在图纸页可见，纳入相同机械令牌映射和源码扫描；无业务逻辑变化。Playwright `boundingBox()` 示例改用 `x/y/width/height` 计算边界。
- 任务 2：三类独立编辑卡片测试先红（3 failed），重排后 `rtk npm --prefix web run test:e2e -- sheets-layout.spec.ts sheets-forms.spec.ts sheets-editing.spec.ts --workers=1` 为 **48 passed**；包含关闭后高度恢复、DOM 归属、bulk 无空卡片及原有输入保护。独立审查通过。
- 任务 3：三态双主题样式测试先红（6 项），修复局部标题被全局 header 污染、两列/900px 单列、38px 控件及真实 Primary 色。工具栏搜索/筛选同步采用局部控件基线；原高度回归暴露双重 padding 后，去掉工作区外层面板并使树独立卡片化，未放宽原 `<=20px` 断言。`sheets-forms.spec.ts sheets-visual-regressions.spec.ts sheets-layout.spec.ts --workers=1` 为 **44 passed**，生产构建及独立审查通过。
- 任务 4：三档导航宽度测试先红，明确观测右操作列覆盖前列；`colgroup`、确定表宽、44px 普通行、长值省略与双状态布局落地后，`sheets-columns.spec.ts sheets-navigation.spec.ts sheets-layout.spec.ts --workers=1` 为 **43 passed**。最终收紧表宽避免自动拉伸选择列后，3 项定向测试及生产构建通过，独立审查通过。安全裁定：除 682px 阈值外，按实际总列宽决定右侧固定，避免较宽容器仍覆盖字段；降级时操作列可由内部横向滚动访问，已选列不隐藏。
- 任务 5：树实底/软底、行 hover、focused/selected 并存及固定单元格背景有先红证据。审查发现浅色当前子集的内偏移焦点环与背景同色，修复为 2px 外偏移和令牌间距，并补双主题边界/对比断言；最终 `sheets-navigation.spec.ts sheets-visual-regressions.spec.ts --workers=1` 为 **32 passed**，复审通过。
- 环境：独立工作树初始化 UV 环境遇到 Windows 文件占用，改用既有根目录 `.venv` 后生产构建通过；最终收口时再对最终代码构建。
- 仓库检查：Ruff、`uv lock --check` 通过；计划旧测试路径实际已迁至 `tests/unit/`，`rtk uv run pytest -q tests/unit/test_shell.py tests/unit/test_shell_workspace.py` 为 **34 passed**（同一未修改 Python 基线）。
- 视觉限制：Browser URL 安全策略拒绝打开本地 Demo 文件并明确禁止绕过。现有参考图仅覆盖 1440×900 浅色默认态，其余规定状态缺少匹配参考；在完成同状态对照前，不将 `design-qa.md` 或 S-07 标记通过。

- 任务 6：48px 常驻栏、覆盖抽屉与实际 TabBar/Dock 边界定位完成。main/layout/visual 首次完整相关回归为 90 passed / 4 failed：三项旧流程未先收起覆盖预览，另一项仍假定工作区整体 surface。按新交互显式收起、分别断言 canvas 与卡片 surface 后，定向 12 项通过；业务断言均保留。键盘明确验证关闭、summary、复制按钮及双向循环；原无条件调焦疑点未在 Chromium 复现，不记为已证实缺陷。调焦仅保留四导航键，独立复审通过。
- 任务 7 截图：新增 `sheets-visual-evidence.spec.ts`，8 项通过，包含 2200→1024→2200 操作列降级/恢复。19 张虚构实现截图已保存至 [证据目录](../../memos/dst-manager/assets/PLAN-DM-017/)，覆盖规定尺寸和状态；已逐张检查，并将现有 1440×900 浅色默认参考与本次实现放入同一比较输入。其余状态缺少同状态参考，视觉验收仍 pending。
- 最终代码生产构建：设置既有 `UV_PROJECT_ENVIRONMENT` 后 `rtk npm --prefix web run build` 通过（OpenAPI 检查、TypeScript、Vite）。最终 Ruff、34 项 `tests/unit/test_shell.py tests/unit/test_shell_workspace.py` 及 `uv lock --check` 再次通过。真实 CAD 未启用，本轮无 CAD 改动；真实 Explorer 仍待人工验收。
- 完整 Web 首轮为 **182 passed / 1 failed**，唯一失败是编辑回归在预览覆盖后未先收起抽屉；补真实收起步骤，保留旧预览失效与不得执行断言，独立复审通过。最终重新运行 `rtk npm --prefix web run test:e2e -- --workers=1` 为 **183 passed，0 failed（2.2 分钟）**。最终代码审查及 `git diff --check` 通过；既有夹具未拦截请求的代理连接警告、环境颜色警告和 Python 弃用提示不影响断言。
- 收口状态：任务 1～6 完成，任务 7 的截图、完整自动化和文档更新完成；步骤 2 的完整同状态视觉比较仍缺参考，因此 PLAN-DM-017 保持 `active`、`design-qa.md` 为 `pending`，PLAN-DM-015 的 S-07/S-09 不标通过。未自动提交 Git。
- 用户确认的后续调整（2026-09-05）：表头首列改为当前结果全选/半选复选框并移除独立入口；顶部和批量按钮统一为 34px；批量控件独占第二行，成功加入草稿后保留选择与展开状态并初始化输入；单张属性编辑器改为紧跟目标行的全宽详情行，桌面三列、窄屏两列/一列；横向溢出时固定操作列；标题、子集、文件名、布局和自定义属性统一最多两行。该确认覆盖任务 4 先前“容器不足时取消操作列固定”的裁定。
- 后续调整采用 TDD：新增 `sheets-followup-adjustments.spec.ts`，生产代码修改前 **6 failed**，实现后 **6 passed**。完整 Web 首轮 **179 passed / 10 failed**，失败均为旧全选入口、单行省略、36px 操作按钮、焦点顺序和旧 sticky 几何断言；更新为新契约后，受影响 5 文件 **117 passed / 2 failed**（测试中误用 Playwright `boundingBox().right`），修正为 `x + width` 后布局与视觉证据 **25 passed**。生产构建（OpenAPI、TypeScript、Vite）和 Ruff 通过；最终完整 Web、相关 Python 与 lock 检查记录见本节后续条目。计划继续保持 `active`，既有同状态视觉参考缺口不变。
- 后续调整最终验证：`rtk npm --prefix web run test:e2e -- --workers=1` 为 **189 passed（2.3 分钟）**；300 行性能样本首屏 **244ms**、中位数 **31.8ms**、P95 **33.2ms**。`rtk uv run pytest -q tests/unit/test_shell.py tests/unit/test_shell_workspace.py` 为 **34 passed**；`rtk npm --prefix web run build`、`rtk uv run ruff check .`、`rtk uv lock --check`、`rtk git diff --check` 均通过。19 张持久视觉证据已用本轮通过的同名 Playwright 截图刷新，抽查浅色选中态确认表头半选框、紧凑按钮和右侧操作列符合新实现。代理连接与第三方弃用警告不影响断言；本轮无 Python、CAD 或真实 Explorer 行为修改，未自动提交 Git。
- 行内属性编辑器深色样式修复：根因是 `style.css` 的裸 `header` 规则命中 `.editor-head`，同时编辑器输入未定义完整控件基线而回退到浏览器默认 2px 边框。新增深色计算样式测试先红，实测污染值为 `min-height:68px`、`padding-top:12px`、surface 背景；限定规则到 `.topbar` 后测试继续以 2px 输入边框失败，补齐编辑器 38px/1px/圆角/实底/focus 基线后转绿。最新深色截图目检通过；`sheets-followup-adjustments.spec.ts sheets-editing.spec.ts sheets-layout.spec.ts sheets-visual-regressions.spec.ts --workers=1` 为 **64 passed**，生产构建和 Ruff 通过。
- 2026-09-05 最终验收：用户在真实桌面连续复验并完成针对全选、按钮尺寸、批量编辑、行内属性编辑、冻结操作列和双行字段的反馈闭环后，明确确认本计划可标记为 `completed`。该确认关闭任务 7 步骤 2、`design-qa.md` 与 PLAN-DM-015 的 S-07；此前关于参考图不足及保持 `active` 的记录作为验收前历史保留。S-09 的真实 Windows Explorer 打开与选中 DST 验收不属于本计划，PLAN-DM-015 因该项继续保持 `active`。
- 提交前最终验证：`rtk npm --prefix web run test:e2e -- --workers=1` 为 **190 passed（3.0 分钟）**，300 行性能首屏 **273ms**、中位数 **31.7ms**、P95 **33ms**；`rtk uv run pytest -q tests/unit/test_shell.py tests/unit/test_shell_workspace.py` 为 **34 passed**。`rtk npm --prefix web run build`、`rtk uv run ruff check .`、`rtk uv lock --check` 与 `rtk git diff --check` 均通过。
