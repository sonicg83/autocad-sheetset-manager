---
id: PLAN-DM-035-HANDOFF-TASK9
title: PLAN-DM-035 实施接手文档（Task 8 已提交，Task 9 进行中）
created: 2026-09-22
status: active
---

# PLAN-DM-035 接手文档（2026-09-22 Task 9 起点）

> 执行方式：Native 模式（顺序执行，无子代理、无 worktree，`main` 分支直接提交）。
> 计划文件：[`PLAN-DM-035-drawing-standard-platform.md`](./PLAN-DM-035-drawing-standard-platform.md)。

## 一、进度总览

| Task | 状态 | Commit | 说明 |
|---|---|---|---|
| 1 领域模型与 Schema | ✅ | `275fac1` | |
| 2 封闭规则求值 | ✅ | `ff75611` | |
| 3 标准包与标准库 | ✅ | `ab9c937` | |
| 4 草稿/发布/快照编排 | ✅ | `79fc60c` | |
| 5 资产检查与 DST 导入 | ✅ | `62f0efc` | `cad_job.py` 确认不动（Task 11 文档说明） |
| 6 标准 API 与受信依赖 | ✅ | `d82b6ad` | |
| 7 前端契约/导航/欢迎页 | ✅ | `380d7ca` | |
| 8 主从分栏标准库 | ✅ | `0ab67de` | `standardLibraryModel` + 3 个面板组件 + `standards-library.spec.ts` 8 项 |
| 9 分区编辑器 | 🔶 **下一步（未开工）** | — | 见 §三 |
| 10 资产检查 + 发布检查页 | ⬜ 未开始 | — | |
| 11 收口（证据/门禁/文档） | ⬜ 未开始 | — | |

验证基线：Task 8 提交时 `vue-tsc -b`、`check:api`、`check:i18n`（1016 键）、`check:ui`、`npm run build` 全过；标准域单测 15 项、Python 标准域 71 项通过；E2E 标准系 13 项加 settings-dialog 33 项共 46 项通过。

## 二、Task 8 交付要点（后续任务直接依赖）

### 前端文件
- `web/src/views/StandardsView.vue`：主从分栏装配。**任务 9 的接线点都在这里**：
  - `const editorAvailable = false;` → 翻转为 `true` 才会启用草稿的「编辑」按键；
  - `StandardDetailPane` 的 `edit` 事件**当前未绑定**（按键在 `editorAvailable=false` 时不可达），任务 9 需补 `@edit="enterEditor"`；
  - `store.detail.value.document` 是「派生」用的基础文档；草稿编辑需要的是**草稿自身**的文档（见下方缺口）。
- `web/src/components/standards/standardLibraryModel.ts`：`DEFAULT_FILTERS`、`filterStandardList`、`buildLibraryState`（`empty-library`/`empty-filter`/`ready`）、`detailActions`（`ReadOnlyReason = "official" | "published" | null` + `canEdit/canDelete/canDerive/canExport`）、`versionHistory`。**模型不持有用户可见中文**（check:i18n 会扫非测试源文件），一律返回稳定码由视图经 `$t` 渲染。
- `StandardLibraryPane.vue` / `StandardDetailPane.vue` / `StandardCreateDialog.vue`：左栏、右栏与三起点对话框（`CreateMode` 定义在 `features/standards/types.ts`；`<script setup>` 里不要再 `export type`）。
- `web/src/features/standards/store.ts`：`StandardStore` 现含 `refresh/open/clearDetail/createDraft/saveDraft/createDraftFromDst/publish/importPackage/deleteDraft/inspectAsset`，pending/error 显式分离，open/refresh 有代次保护。
- `web/src/api/standards.ts`：`standardsApi` 组合实现 + `standardExportUrl(identity)`；`fetchStandardDraft(draftId)` 已写好但**尚未接入 store**。
- i18n `standards` 域已补齐 `library.*`/`detail.*`/`create.*`/`import.*`/`delete.*`（中英同构 1016 键）；`standardLibraryModel.ts` 的 `readOnlyReason` 渲染为 `standards.detail.readOnlyOfficial|readOnlyPublished`，`defaultDraftName` 为 `standards.create.defaultName`。
- E2E：`web/tests/e2e/fixtures/standards.ts` 提供 `StandardSummary` 构造器、`installStandards(page, list, options)`（GET list / GET detail / POST drafts / DELETE drafts/{id} / POST import）、`openStandards(page)`、`libraryItems(page)`。

### 任务 9 需要先补齐的缺口（都在 Task 8 边界之外，有意留给编辑器）
1. **草稿读取未接线**：`StandardApi` 没有 `fetchDraft`，store 也没有加载草稿文档的方法。编辑器必须能 `GET /api/standards/drafts/{draft_id}`（`fetchStandardDraft` 已存在）并在进入编辑分区前拿到 `document`。
2. **创建结果被丢弃**：`StandardsView.submitCreate()` 只 `refresh()` 列表，没有保存返回的 `{draft_id, document}`；任务 9 应据其直接进入编辑器（草稿身份在文档内，列表项无版本号）。
3. **共享夹具缺草稿端点**：`installStandards` 对 `GET/PUT /api/standards/drafts/{id}` 与 `POST .../publish` 目前返回 404（GET 被 `match[1] !== "drafts"` 挡住、DELETE 单独分支）。任务 9 在该夹具内扩展，不要另起一套。
4. **离开守卫未接线**：`App.vue` 的 `UnsavedInputDialog`（共享三选一实例）已存在但标准编辑页尚未接；SPEC-DM-015 的直接保存状态机需按同一门禁语义接入。
5. `editorAvailable` 翻转后，`standards-library.spec.ts` 的「草稿可维护：编辑入口因编辑器未交付而禁用」用例断言（`toBeDisabled` + `editorPending` title）**必须同步改写**。

## 三、Task 9 起手待办（按顺序）

1. 先写 `web/src/features/standards/draftModel.ts` 的失败测试 `draftModel.test.ts`（计划 Step 1）：`buildMappingRows("燃气\tRQ\n建筑\tJZ\n结构\tJG\n给排水\tGPS")` → 4 行；`validateMapping` 对重复源值返回 `STANDARD_MAPPING_SOURCE_DUPLICATE` 并给出行号、对未覆盖值返回 `STANDARD_MAPPING_SOURCE_UNCOVERED` 且 `row: null`；`renderCompositionPreview(segments, sampleValues)` 只做纯展示（不复制后端最终求值）。
2. 再实现 `StandardEditor.vue`、`StandardSectionNav.vue`、`StandardPropertyEditor.vue`、`StandardRulesEditor.vue`、`MappingTableEditor.vue`、`CompositionEditor.vue`；分区顺序按 SPEC-DM-016 §6，子集属性只显示预留说明。
3. 接线（已验证的后端语义，勿靠猜）：
   - **草稿保存**用 `PUT /api/standards/{standard_id}/{version}`，请求体就是文档本身；身份取自草稿文档内的 `standard_id`/`version`（草稿推荐摘要的 `version` 恒为空串，身份在文档内）。路径与文档身份不一致→422 `STANDARD_IDENTITY_MISMATCH`；已发布身份→409 `STANDARD_VERSION_IMMUTABLE`；没有匹配草稿→404 `STANDARD_DRAFT_NOT_FOUND`。`StandardStore.saveDraft(input: SaveDraftByIdentityInput)` 已按此封装。
   - **`POST /api/standards/drafts` 带已存在的 `draft_id` 会 409 `STANDARD_DRAFT_EXISTS`**（不覆盖），所以不能拿它当保存接口。
   - 读取草稿文档用 `GET /api/standards/drafts/{draft_id}`（`fetchStandardDraft` 已写好，需接进 store）。
4. 验收门禁：`npm run test:unit -- src/features/standards/draftModel.test.ts`、`npm run build`、`npm run test:e2e -- standards-editor.spec.ts`（vite dev + 真后端 9001，全量约 1 分钟）。
5. 更新 `changelog.md`，提交：`git add web/src/components/standards web/src/features/standards web/src/views/StandardsView.vue web/tests/e2e/standards-editor.spec.ts web/tests/e2e/fixtures/standards.ts changelog.md`，commit message：`实现图纸标准分区编辑器`。

## 四、Task 6/7 建立的关键事实

### API 端点
- `GET /api/standards`；`POST /api/standards/drafts`（body `{draft_id?, document}`）；`GET/DELETE /api/standards/drafts/{draft_id}`；`POST /api/standards/drafts/from-dst`（`{dst_path}`）；`POST /api/standards/drafts/{draft_id}/publish`；`POST /api/standards/drafts/{draft_id}/assets/{asset_id}/inspect`（`{cad_version}`）；`POST /api/standards/import`（`{path}`）；`GET /api/standards/{id}/{ver}/export`（zip 下载）；`GET /api/standards/{id}/{ver}`（detail 含 `document`）；`PUT /api/standards/{id}/{ver}`（body 即标准文档；已发布→409 `STANDARD_VERSION_IMMUTABLE`）。
- 错误码映射：`STANDARD_VERSION_EXISTS/STANDARD_DRAFT_EXISTS`→409；`*_NOT_FOUND`→404；其余 422；`STANDARD_DEPENDENCY_MISSING`→409（发布门禁）。这些码**未登记**进 `message_catalog.CATALOG`——前端暂时按未知错误显示原始 message。

### 受信扩展依赖
- `ExtensionManifest.provided_capabilities`（capability_id + SemVer，YAML `provided_capabilities:`）；`standard_dependency_gaps(dependencies, manifests)` 返回 `extension-missing/capability-missing/version-too-old`。测试可用 `BuiltinExtensionEntry(manifest_resource=str(yaml_path), factory=...)` 注入。

### 前端
- `useStartNavigation()`：`surface: Ref<"welcome"|"standards"|"create-sheetset">` + `openStandards/goWelcome/openCreateSheetset`。
- 「用于创建图纸集」入口自 Task 8 起位于**已发布版本详情动作**（SPEC-DM-016 §5 的逐标准动作矩阵），不再挂在标准页头部；`standards-welcome.spec.ts` 已按此改写。
- 标准端点 E2E mock **必须用 URL 判定**注册：`**/api/standards**` 这类 glob 会匹配 vite 的 `/src/api/standards.ts` 模块请求，返回 JSON 后触发 MIME 错误导致整个应用启动失败（Task 8 踩过一次）。

## 五、环境注意

1. rtk 会吞 pytest/vitest 汇总行（`uv run pytest ... > log 2>&1` 后看 `[100%]` 进度行计数，或加 `rtk proxy` 前缀）。
2. 输出长标识符时曾出现系统性拼写漂移——前端组件/模板一律以 `npx vue-tsc -b` 报错为准修复，禁止目检通过。
3. `UiSelect` 无 `options` prop（用默认插槽 `<option>`）；`UiInput`/`UiSelect` 支持 `label`；`UiButton` 的 `variant` 只有 primary/secondary/danger/link（用前 grep 组件）。
4. `web/src/style.css` 只允许层序与 `@import`（check:ui 门禁）；全局新类放 `styles/primitives.css`；组件内引用未登记 CSS 变量会被 `check:ui` 拦截（Task 8 的 `--radius-pill` → `--radius-full`）。
5. `check:i18n` 扫描全部非测试 `.ts/.vue`（跳过 `locales/`、`.d.ts`、`.test.ts`）：模型/组件里不得出现中文用户文案，返回稳定码由 `$t` 渲染。
6. E2E：`npm run test:e2e -- <spec>` 会先跑 settings-file-mutating 项目再跑其余（约 1 分钟）；standards 系 spec 放 `web/tests/e2e/`，`beforeEach` 注入假壳桥 + mock `/api/extensions`。
7. Playwright 的 `page.route` 第一个参数传谓词 `url => ...` 时拿到的是 URL 对象（Task 8 用 `url.pathname`）。

## 六、剩余任务速查

- **Task 9**（当前）：见 §三。
- **Task 10** 资产检查 + 发布检查页：`buildPublishGate`；`StandardStore.inspectDraft()` 对接 Task 5 的 `AssetInspection`（store 现有 `inspectAsset({draftId, assetId, cadVersion})`）。
- **Task 11** 收口：ST-UI 追踪矩阵、视觉证据（`standards-visual-evidence.spec.ts` + `docs/dst-manager/specs/assets/SPEC-DM-016/`）、全量门禁（`npm run check:api/check:i18n/check:ui/test:unit/build/test:e2e` + `ruff/pytest/alembic/uv lock`）、G8/G9 对照；届时统一勾选计划复选框、计划 status 改 `completed`，并补记「`cad_job.py` 未修改」的说明（Task 5 遗留）。计划 Task 9/10 的 E2E 仍会复用 `fixtures/standards.ts`，扩展时保持既有导出签名不变。
