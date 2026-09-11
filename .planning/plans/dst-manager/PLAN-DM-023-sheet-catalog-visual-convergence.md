---
id: PLAN-DM-023
title: 图纸目录页面视觉收敛整改
status: proposed
document_kind: plan
owners:
  - dst-manager
created: 2026-09-11
updated: 2026-09-11
related:
  - SPEC-DM-006
  - SPEC-DM-012
  - PLAN-DM-020
  - PLAN-DM-024
  - MEMO-DM-027
  - MEMO-DM-030
---

# 图纸目录页面视觉收敛整改实施计划

> **供代理执行：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐条执行；每个生产改动严格遵循测试先红、最小实现转绿、重构保持绿灯。步骤使用 `- [ ]` 跟踪。本计划只编制整改步骤，不自动修改生产代码或提交 Git。

**目标：** 不改变图纸目录后端、表达式、模板、预览、XLSX、Artifact 和桌面壳契约，把生产页面拉回 SPEC-DM-012 G4 冻结 Demo 的紧凑“字段浏览器 + 表格式输出列 + 同屏预览/导出”结构，同时保留用户已接受的 `↑`、`↓`、`✕` 图标操作按钮。

**架构：** 继续由 `useSheetCatalog` 持有全部业务状态，只调整 `SheetCatalogView.vue` 与 `components/sheet-catalog/` 的呈现组合和 scoped CSS。字段搜索保持页面本地瞬时状态；`CompatibilitySummary` 嵌回输出列卡，`CatalogActions` 嵌回预览卡；不复制后端校验规则，不修改 API、ShellBridge 或持久化。

**技术栈：** Vue 3、TypeScript、vue-i18n、Vite、Playwright、pywebview/WebView2。

**规范：** [SPEC-DM-012](../../../docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md) §3、§7、§11、§13、§16；视觉权威为 [G4 冻结 Demo](../../../docs/dst-manager/mockups/SPEC-DM-012-sheet-catalog-demo.html) commit `9f3dfb3` 与 [`default-light-1440x1000.jpg`](../../../docs/dst-manager/specs/assets/SPEC-DM-012/default-light-1440x1000.jpg)、[`default-dark-900x700.jpg`](../../../docs/dst-manager/specs/assets/SPEC-DM-012/default-dark-900x700.jpg)；用户复验裁决见 [MEMO-DM-030](../../memos/dst-manager/2026-09-11-plan-dm020-g8-user-revalidation.md)。

## 全局约束

- PLAN-DM-024 是本计划的正确性前置；只有其 F1～F5 全部关闭、SPEC-DM-012 G7 重新通过后，才能开始本计划的生产代码任务。
- G4 冻结件继续有效；本计划不重开 G3/G4、不改 Demo、不用当前生产布局反向改写 Spec。
- 真实生产壳的顶栏、右缘任务入口和底部 ActionDock 属已接受壳层差异；比较范围从“图纸目录”页面正文开始。页面内容必须适配壳层剩余空间，不能以壳层占高为由放弃首屏密度。
- 保留输出列 `↑`、`↓`、`✕` 图标按钮及现有完整 `aria-label`；不恢复为文字按钮。
- 不修改 Python、数据库、迁移、OpenAPI、扩展清单、ShellBridge、保存授权、XLSX 或 Artifact 代码。
- 不改变 `useSheetCatalog` 的业务状态、请求时机、未保存闸门、错误码映射或模板 CRUD 语义；字段搜索只过滤当前已取得的字段目录。
- 不新增 npm 依赖、不新增全局 CSS；所有布局与视觉改动留在专用 Vue 组件的 `<style scoped>`。
- 页面文案与可访问名继续走宿主 i18n；新增键必须同步 `zh-CN`、`en-US` 并通过 `npm run check:i18n`。
- 用户真实截图含工程显示信息，不复制到仓库。自动化和入库截图只使用 `fixtures/sheetCatalog.ts` 的虚构数据。
- G8 生产证据必须进入 `docs/dst-manager/specs/assets/SPEC-DM-012/production/`；不得只留在 `.superpowers/` 或 `web/test-results/`。
- G8 差异只能由用户裁决。实施代理可以标记“缺陷候选”，不能自行把新差异写成“已接受”。

## 追踪矩阵

| ID | 用户复验要求 | 实施任务 | 自动验证 | G8 证据 |
| --- | --- | --- | --- | --- |
| V1 | 输出列恢复紧凑表格式 | 1、3 | 表头/行几何、首屏密度 E2E | 1440 浅色、900 深色 |
| V2 | 兼容性提示回到输出列上下文 | 4 | DOM 归属、正文与焦点 E2E | 两主题警告态 |
| V3 | 恢复编辑→预览→导出的短反馈环 | 1、4 | 初始滚动位置可见区域 E2E | 1440 浅色 |
| V4 | 恢复字段搜索和常显引用语法 | 2 | 搜索、键盘插入、可见正文 E2E | 两主题默认态 |
| V5 | 恢复列状态、列计数和表头层级 | 3 | `N / 50`、有效/错误、重复列 E2E | 默认/错误态 |
| V6 | 压缩可用态冗余状态区 | 2、4 | AVAILABLE/加载/失败状态 E2E | 1440 浅色 |
| V7 | 900px 字段区限高和单列降级 | 5 | 900×700 几何与内部滚动 E2E | 900 深色 |
| V8 | 控制宽屏扫描距离和列宽 | 3、5 | 1440/超宽几何 E2E | 1440 浅色 + 超宽辅助图 |
| A1 | 保留图标排序/删除按钮 | 3 | aria-label、禁用边界、点击行为 | 默认态 |
| A2 | 保留生产壳层 | 5、6 | 相邻页面和 ActionDock 回归 | 生产截图说明 |

---

## 任务 1：先把冻结布局要求写成会失败的生产证据测试

**文件：**

- 修改：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- 修改：`web/tests/e2e/fixtures/sheetCatalog.ts`（仅补复用的 6 列与错误态虚构模板）

**产出：** 当前卡片式实现稳定红灯；测试不再把“滚动后可达”冒充 G4 一致。

- [ ] **步骤 1：新增 1440×1000 首屏密度红灯。** 使用现有 G4 同口径四列夹具，保持页面初始 `scrollTop=0`，断言预览标题、至少前三行数据和“导出 XLSX”按钮均与视口及底部 ActionDock 不重叠：

  ```ts
  const dockTop = await page.locator(".dock").evaluate(el => el.getBoundingClientRect().top);
  for (const target of [
    page.getByRole("heading", {name: "预览"}),
    page.getByRole("region", {name: "预览"}).getByRole("row").nth(3),
    page.getByRole("button", {name: "导出 XLSX"}),
  ]) {
    const box = await target.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y + box!.height).toBeLessThanOrEqual(dockTop);
  }
  ```

- [ ] **步骤 2：新增结构红灯。** 断言输出列区域内存在唯一表头行“顺序 / 列名 / 表达式 / 状态 / 操作”，四个数据行共享同一列边界；兼容性摘要属于输出列 region，刷新和导出属于预览 region。

- [ ] **步骤 3：新增字段可见性红灯。** 断言“搜索可用字段”输入框可见；`sheet.number` 与“图号”同时作为可见正文出现，不能只存在于 `title` 或 `aria-label`。

- [ ] **步骤 4：新增 6 列真实密度红灯。** 使用六列模板并保持初始滚动位置，断言列编辑区自身可滚动、预览位置不随列数从 4 增至 6 而继续下移超过 2px。

- [ ] **步骤 5：运行并记录预期红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog-visual-evidence.spec.ts --workers=1 --retries=0
  ```

  预期：至少因无字段搜索、无列头/状态、兼容性与操作区 DOM 归属错误、预览不在首屏、6 列撑高页面而失败。若这些断言未红，先确认选择器是否真的命中生产页面，不得削弱标准。

- [ ] **步骤 6：提交。** 仅提交本任务测试和 fixture，commit message：`钉住图纸目录冻结布局回归`。

## 任务 2：压缩页面头部与模板栏，恢复字段搜索和常显语法

**文件：**

- 修改：`web/src/views/SheetCatalogView.vue`
- 修改：`web/src/components/sheet-catalog/TemplateBar.vue`
- 修改：`web/src/components/sheet-catalog/FieldBrowser.vue`
- 修改：`web/src/i18n/locales/zh-CN/extensions.ts`
- 修改：`web/src/i18n/locales/en-US/extensions.ts`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`changelog.md`

**接口：** 字段搜索是 `FieldBrowser.vue` 内部 `ref<string>`，不进入 `SheetCatalogController`，不发 API 请求，不持久化。

- [ ] **步骤 1：为搜索、常显语法和可用态头部写红灯。** 覆盖按中文名、规范引用和作用域搜索；搜索无结果显示可见空态；AVAILABLE 状态下不存在独立 `.catalog-status` 大卡，但版本/生命周期仍有紧凑可见文字或辅助技术文本。

- [ ] **步骤 2：运行聚焦红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --grep "字段搜索|可用态头部" --workers=1 --retries=0
  ```

- [ ] **步骤 3：压缩页面头部。** 删除 AVAILABLE 状态的整行 `.catalog-status` 卡片；标题、说明和 `v{version} · {status}` 组合为紧凑头部。加载失败、扩展不可用等异常仍以可见正文呈现，不隐藏诊断。

- [ ] **步骤 4：压缩模板栏。** 恢复“内置模板/已保存模板”和“已保存/有未保存修改”状态文字；模板选择和三项管理操作保持单行优先、窄屏换行。危险删除继续使用低强调危险文字，不改变确认流程。

- [ ] **步骤 5：实现字段本地搜索。** 在 `FieldBrowser.vue` 增加搜索框和过滤后的 computed 列表；按钮改为双行：第一行常显不带外层花括号的规范引用，第二行显示用户名称。三个固有字段通过 i18n 映射为“图号/图名/文件名”，自定义属性第二行显示规范属性名；特殊属性常显方括号引用。

- [ ] **步骤 6：验证。**

  ```powershell
  rtk npm --prefix web run check:i18n
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts tests/e2e/sheet-catalog-visual-evidence.spec.ts --workers=1 --retries=0
  ```

- [ ] **步骤 7：记录并提交。** changelog 记录头部、模板栏和字段浏览器收敛；commit message：`收敛图纸目录头部与字段浏览器`。

## 任务 3：把输出列恢复为紧凑表格式并保留图标按钮

**文件：**

- 修改：`web/src/components/sheet-catalog/ColumnEditor.vue`
- 修改：`web/src/i18n/locales/zh-CN/extensions.ts`
- 修改：`web/src/i18n/locales/en-US/extensions.ts`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- 修改：`changelog.md`

**产出：** `.columns-head` 与 `.column-row` 使用同一 grid track；列区固定为受控高度并内部滚动；每行同时显示顺序、列名、表达式、状态和操作。

- [ ] **步骤 1：写列几何与状态红灯。** 断言表头和每行五列 `left/right` 对齐误差不超过 1px；四列状态均显示“有效”，未知字段行显示“需修正”及正文错误；显示“4 / 50 列”。

- [ ] **步骤 2：写图标行为保护红灯。** 断言页面不出现可见“上移/下移/删除”文字按钮，但 `getByRole("button", {name:"上移第 2 列"})` 等仍可定位、首尾禁用正确、点击后顺序改变、删除仍走现有规则。

- [ ] **步骤 3：运行红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --grep "表格式输出列|图标列操作" --workers=1 --retries=0
  ```

- [ ] **步骤 4：重排 DOM。** 在 editor header 显示标题、兼容徽标占位和列数；增加 `.columns-head`；把每项 `.column-row` 改为五列网格。表达式错误保留在表达式单元格内，状态单元格显示“有效/需修正”；editor footer 放“添加输出列”和表达式语法说明。

- [ ] **步骤 5：实现紧凑布局。** 参考冻结 Demo 使用同轨道：

  ```css
  .columns-head,.column-row{
    display:grid;
    grid-template-columns:34px minmax(110px,.62fr) minmax(250px,1.8fr) 92px 112px;
    gap:8px;
  }
  .columns{overflow:auto;min-height:0;max-height:330px}
  .column-row{padding:9px 12px;border-bottom:1px solid var(--color-border-subtle)}
  ```

  操作列因保留图标按钮可比 Demo 更窄；这属于 MEMO-DM-030 A1 的用户已接受差异。

- [ ] **步骤 6：验证 1/4/6/50 列及错误态。** 50 列只滚动 `.columns`，不得把页面高度撑长；重复列名、未知字段和语法错误继续聚焦正确输入。

- [ ] **步骤 7：记录并提交。** commit message：`恢复图纸目录紧凑表格式编辑器`。

## 任务 4：把兼容性与操作区嵌回任务上下文

**文件：**

- 修改：`web/src/components/sheet-catalog/ColumnEditor.vue`
- 修改：`web/src/components/sheet-catalog/CompatibilitySummary.vue`
- 修改：`web/src/components/sheet-catalog/CatalogPreview.vue`
- 修改：`web/src/components/sheet-catalog/CatalogActions.vue`
- 修改：`web/src/views/SheetCatalogView.vue`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- 修改：`changelog.md`

**架构：** 组件继续独立存在，但由业务上下文组件组合：`ColumnEditor` 内渲染无外层 panel 的 `CompatibilitySummary`；`CatalogPreview` 内渲染无外层 panel 的 `CatalogActions`。ARIA region 名称继续保留，避免牺牲导航语义。

- [ ] **步骤 1：写 DOM 归属和状态红灯。** 断言兼容性 region 是输出列 region 的后代；操作区 region 是预览 region 的后代；缺值警告允许导出，未知字段错误禁用导出，错误正文和焦点行为不回退。

- [ ] **步骤 2：运行红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --grep "兼容性归属|预览操作坞" --workers=1 --retries=0
  ```

- [ ] **步骤 3：组合兼容性摘要。** 去掉独立 `.panel` 外观，按 ok/warning/error 使用紧凑整行状态带；输出列 header 显示“可以导出/不能导出/检查中”徽标，详细正文紧随 header，不复制诊断计算。

- [ ] **步骤 4：组合预览操作。** 把刷新放进预览 header，把导出和一致性/过期/失败/成功反馈放进预览 footer；删除 `SheetCatalogView.vue` 中独立的 `<CatalogActions>` sibling。导出仍是页面唯一高强调操作。

- [ ] **步骤 5：验证成功、取消、过期、漂移、失败和无桌面壳状态。** 所有既有 `sheet-catalog.spec.ts` 用例必须保持通过，尤其成功路径、打开所在文件夹和重试逻辑。

- [ ] **步骤 6：记录并提交。** commit message：`合并图纸目录兼容性与预览操作区`。

## 任务 5：收敛桌面、最小视口、200% 和宽屏行为

**文件：**

- 修改：`web/src/views/SheetCatalogView.vue`
- 修改：`web/src/components/sheet-catalog/FieldBrowser.vue`
- 修改：`web/src/components/sheet-catalog/ColumnEditor.vue`
- 修改：`web/src/components/sheet-catalog/CatalogPreview.vue`
- 修改：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- 修改：`changelog.md`

- [ ] **步骤 1：写四档几何红灯。** 覆盖 1440×1000、900×700、200%（CSS 720×500）和 1920×1080；每档断言无整页横滚、预览宽列只在表容器横滚、页面主要操作不被 ActionDock/任务入口遮挡。

- [ ] **步骤 2：钉住 900px 字段区限高。** 单列布局时 `.field-browser` 可见高度不超过 235px 且内部列表可滚动；输出列紧随其后，不由字段数量撑高整页。

- [ ] **步骤 3：钉住宽屏扫描距离。** 1920px 下字段浏览器保持约 258px；输出列名、表达式、状态和操作列各自有明确轨道，不因剩余宽度产生不可读的超长空白。具体宽度以冻结 Demo 的 grid 比例和生产壳可用宽度共同计算，不新建全局 `max-width`。

- [ ] **步骤 4：实现响应式样式。** 桌面为 `258px minmax(470px,1fr)`；≤980px 单列、字段卡限高；≤720px 隐藏列头并把每行降级为“顺序 + 单列字段”，操作图标左对齐。保持 `prefers-reduced-motion` 和现有焦点环。

- [ ] **步骤 5：运行聚焦与相邻壳回归。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts tests/e2e/sheet-catalog-visual-evidence.spec.ts tests/e2e/extensions-navigation.spec.ts tests/e2e/main.spec.ts --workers=1 --retries=0
  rtk npm --prefix web run build
  ```

- [ ] **步骤 6：记录并提交。** commit message：`完善图纸目录响应式与宽屏密度`。

## 任务 6：重新执行 G8、取得用户裁决并恢复 G9

**文件：**

- 修改：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-012/production/g8-catalog-light-1440x1000.png`
- 新增：`docs/dst-manager/specs/assets/SPEC-DM-012/production/g8-catalog-dark-900x700.png`
- 修改：`.planning/memos/dst-manager/2026-09-11-plan-dm020-g8-user-revalidation.md`
- 修改：`.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-design-qa.md`
- 修改：`.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md`
- 修改：`.planning/plans/dst-manager/PLAN-DM-020-sheet-catalog-builtin-extension.md`
- 修改：`.planning/plans/dst-manager/PLAN-DM-023-sheet-catalog-visual-convergence.md`
- 修改：`docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md`
- 修改：`docs/dst-manager/README.md`
- 修改：`.planning/plans/dst-manager/README.md`
- 修改：`changelog.md`

- [ ] **步骤 1：生成新鲜生产证据。** 用 G4 同数据、状态、主题、滚动位置和展开状态运行证据 spec，把两张通过自动断言的生产截图复制到版本库 `production/` 目录；确认尺寸分别为 1440×1000、900×700。

- [ ] **步骤 2：逐对检查 V1～V8、A1～A2。** 对照冻结 JPG 和生产 PNG，记录尺寸、间距、对齐、首屏可见内容、内部滚动、状态文字和操作层级；任何新差异先标为缺陷候选，不得自行接受。

- [ ] **步骤 3：交给用户复核。** 在用户逐对确认前，SPEC-DM-012 G8 保持“待用户复核”，PLAN-DM-023 保持 `active`，MEMO-DM-028 的 G9 保持暂停。

- [ ] **步骤 4：用户确认后更新门禁。** 只有用户明确通过，才把 G8 改为“通过”，记录确认人和日期，把 PLAN-DM-023 标记 `completed`，解除 G9 暂停；不得同时替用户填写 G9 结果。

- [ ] **步骤 5：运行完整验证。** 所有输出必须新鲜且退出码为 0：

  ```powershell
  $env:UV_LINK_MODE = "copy"
  rtk uv sync --dev
  rtk uv run ruff check .
  rtk uv run pytest -q
  rtk uv lock --check
  rtk npm --prefix web ci
  rtk npm --prefix web run check:api
  rtk npm --prefix web run check:i18n
  rtk npm --prefix web run build
  rtk npm --prefix web run test:e2e
  ```

- [ ] **步骤 6：提交。** 只暂存本计划相关文件，commit message：`完成图纸目录页面视觉收敛验收`。

## 风险与回退

- 表格式编辑器可能在翻译伸长或长表达式下变窄：通过列区内部横滚和 ≤720px 单列降级处理，不回退为逐列大卡片。
- 兼容性与操作区重新嵌套可能改变无障碍 landmark：保留独立 `aria-label` region，并用 E2E 验证 DOM 归属、Tab 顺序和错误聚焦。
- 固定编辑区高度可能隐藏第 5～50 列：必须提供明显的内部滚动，不截断、不分页、不改变列顺序。
- 生产壳比 Demo 多占空间：只接受壳层差异，内容区用密度和内部滚动适配；不得删除全局 ActionDock 或任务入口来“通过截图”。
- 任一任务造成模板、预览、导出或未保存闸门行为回退时，回退该任务的呈现改动并保持 PLAN-DM-023 `active`；不修改后端绕过。

## 完成标准

- V1～V8 自动验证与同状态截图均关闭；A1、A2 是唯一预先接受差异。
- 1440×1000 浅色和 900×700 深色生产截图已入版本库并可追溯复现。
- 全部既有图纸目录功能、键盘、响应式、主壳和相邻页面回归通过。
- 用户在真实桌面对 G8 逐对确认并记录日期。
- G8 重新通过后才解除 G9 暂停；PLAN-DM-020 仍须等待 G9 才能 `completed`。
