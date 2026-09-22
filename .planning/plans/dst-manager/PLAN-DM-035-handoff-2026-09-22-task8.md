---
id: PLAN-DM-035-HANDOFF-TASK8
title: PLAN-DM-035 实施接手文档（Task 5-7 已提交，Task 8 进行中）
created: 2026-09-22
status: active
---

# PLAN-DM-035 接手文档（2026-09-22 Task 8 暂停点）

> 执行方式：Native 模式（顺序执行，无子代理、无 worktree，`main` 分支直接提交）。
> 计划文件：[`PLAN-DM-035-drawing-standard-platform.md`](./PLAN-DM-035-drawing-standard-platform.md)。
> 前一份接手文档（Task 1-4）：[`PLAN-DM-035-handoff-2026-09-22.md`](./PLAN-DM-035-handoff-2026-09-22.md)——其中 §三（测试惯例）、§四（全局约束）继续有效。

## 一、进度总览

| Task | 状态 | Commit | 说明 |
|---|---|---|---|
| 1 领域模型与 Schema | ✅ | `275fac1` | |
| 2 封闭规则求值 | ✅ | `ff75611` | |
| 3 标准包与标准库 | ✅ | `ab9c937` | |
| 4 草稿/发布/快照编排 | ✅ | `79fc60c` | |
| 5 资产检查与 DST 导入 | ✅ | `62f0efc` | `application/standard_assets.py` + `infrastructure/standards/dst_import.py`；`cad_job.py` 确认不动（Task 11 文档说明） |
| 6 标准 API 与受信依赖 | ✅ | `d82b6ad` | `interfaces/standard_api.py` + `standard_contracts.py`；manifest 增 `provided_capabilities`；发布门禁 `STANDARD_DEPENDENCY_MISSING` |
| 7 前端契约/导航/欢迎页 | ✅ | `380d7ca` | `features/standards/{types,store}` + `api/standards.ts` + `useStartNavigation`；E2E 5 项 |
| 8 主从分栏标准库 | 🔶 **进行中（半成品在工作区）** | — | 见 §二、§三 |
| 9-11 编辑器/发布/收口 | ⬜ 未开始 | — | |

验证基线：Task 7 提交时单测 6 项、i18n 960 键对称、`npm run build` 全过、全量 E2E 38 项通过；Python 侧标准域测试 80 项通过。

## 二、Task 8 已完成的部分

**已提交**：无（Task 8 全部改动都在工作区，未提交）。

**工作区文件（`git status`）**：
- 已修改：`src/dst_manager/application/standards.py`、`src/dst_manager/infrastructure/standards/store.py`、`src/dst_manager/interfaces/standard_contracts.py`、`web/src/api/openapi.json`、`web/src/api/schema.d.ts`、`web/src/features/standards/store.ts`、`web/src/features/standards/types.ts`、`web/src/views/StandardsView.vue`
- 未跟踪：`web/src/components/standards/`（standardLibraryModel.ts / .test.ts、StandardLibraryPane.vue、StandardDetailPane.vue、StandardCreateDialog.vue）

**已完成并验证**：
1. **后端 detail 扩展**（Task 8 需要"派生草稿"的完整文档）：`StandardStore.get_document(id, ver)` 返回原始文档字典；应用层 `get_standard` 返回增加 `document`；`StandardDetailResponse` 增 `document: dict`。`npm run generate:api` 已重跑（openapi.json/schema.d.ts 已更新），`test_standard_api + test_standard_service` 21 项回归通过。**注意：这 3 个后端文件 + 2 个生成文件的改动尚未提交**。
2. **standardLibraryModel.ts**：`DEFAULT_FILTERS`、`filterStandardList(items, filters)`、`buildLibraryState`（`empty-library`/`empty-filter`/`ready` 三态）、`detailActions`（官方→"官方标准只读"、已发布→"已发布版本不可直接修改"、草稿可编辑可删除；`canDerive/canExport` 对已发布为 true）、`versionHistory`。对应测试 `standardLibraryModel.test.ts` 已写好（**尚未重跑通过**——写完 model 后只确认过初始失败）。

**已写但未验证的组件**（vue-tsc 尚未对它们通过）：
- `StandardLibraryPane.vue`（左栏：UiInput 搜索 + 两个 UiSelect（**用默认插槽 option**，UiSelect 无 options prop）+ 空态区分 + 列表 + 新建/导入按钮）
- `StandardDetailPane.vue`（右栏：身份、只读原因、counts、依赖、版本历史、动作按钮）
- `StandardCreateDialog.vue`（三起点：blank/derive/from-dst；deriveVersion 补丁位 +1）
- `StandardsView.vue` 重写（装配 store + 主从分栏 + 959px 断点分级视图 + 导入对话框）

## 三、Task 8 恢复时的待办清单（按顺序）

1. **先跑 `cd web && npx vue-tsc -b`**，按错误清单修复。已知问题：
   - `StandardsView.vue`：`t` 未导入（需 `useI18n`）；模板 `@export-standard="store.exportStandard"` 绑定了不存在的方法（改为本地函数，用 `api/standards.ts` 新增的导出函数实现下载）；`import StandardCreateDialog, {type CreateMode}`——`CreateMode` 已移到 `types.ts`，应从那里导入（script setup 不允许 `export type`，StandardCreateDialog 里的 `export type CreateMode` 会编译报错，需删除并从 types 导入）。
   - `store.ts`：`StandardApi` 接口已有 `deleteDraft(draftId)`（line 29），但 **`StandardStore` 接口与 `createStandardStore` 返回对象都还没有 `deleteDraft`**，`api/standards.ts` 的 `standardsApi` 也缺（后端 `DELETE /api/standards/drafts/{draft_id}` 已存在，`deleteStandardDraft` 函数已在 api/standards.ts 写好未接入）。
   - 生成代码时出现过**同词异拼**（如 UiButton/detail 等标识符多写/漏写字母），**不要目检，一律以 vue-tsc 报错为准逐条修**。
2. `web/src/i18n/locales/{zh-CN,en-US}/standards.ts` 需补大量键：`standards.library.*`（region/searchLabel/searchPlaceholder/sourceLabel/sourceAll/sourceOfficial/sourceUser/statusLabel/statusAll/statusPublished/statusDraft/loading/loadFailed/empty/noMatch/newDraft/import/sourceOfficialBadge/sourceUserBadge/statusDraftBadge/statusPublishedBadge）、`standards.detail.*`（region/empty/standardId/version/status/source/loading/propertiesCount/rulesCount/assetsCount/dependencies/versionHistory/edit/derive/export/useForCreate/delete/editorPending）、`standards.create.*`（title/deriveFrom/nameLabel/versionLabel/dstPathLabel/cancel/confirm/deriveNeedsDetail）、`standards.import.*`（title/pathLabel/confirm）、`standards.delete.*`（title/message/confirm）。中英必须键集对称（`npm run check:i18n` 门禁，现有 960 键基线）。
3. `web/src/App.vue`：给 `<StandardsView>` 传 `:confirm-action="confirmAction"`（App 已有共享实例；删除草稿等走共享 ConfirmModal）。注意 App.vue 中 `watch` 必须在 `workspace` 声明之后注册（Task 7 曾因 TDZ 导致整页白屏，settings-dialog E2E 一过性失败——已修复，勿回退）。
4. 重跑 `npm run test:unit -- src/components/standards/standardLibraryModel.test.ts` 应全过。
5. `npm run build`（含 check:api/check:i18n/check:ui/vue-tsc）全过后写 `web/tests/e2e/standards-library.spec.ts`：按 extensions-navigation.spec 的 route-mock 模式，覆盖计划 Step 1/5 的用例——空库 vs 筛选无结果、官方只读、已发布只读（"已发布版本不可直接修改" + 编辑按钮 count 0）、派生新草稿（"派生新草稿"→ 列表出现"草稿 3"）、加载失败、导入碰撞不改变选中、900×768 分级视图。
6. 跑 `npm run test:e2e -- standards-library.spec.ts`（vite dev + 真后端 9001，Playwright 全量约 1 分钟，38+ 项）。
7. 更新 changelog、按计划 Step 6 提交：`git add web/src/views/StandardsView.vue web/src/components/standards web/src/App.vue web/src/features/standards web/src/api/standards.ts web/src/i18n web/tests/e2e/standards-library.spec.ts src/dst_manager web/src/api changelog.md`（注意把 Task 8 的后端 detail 扩展一并纳入本次或单独先提交），commit message：`实现主从分栏图纸标准库`。

## 四、Task 6/7 建立的关键事实（后续任务直接依赖）

### API 端点（Task 6）
- `GET /api/standards`；`POST /api/standards/drafts`（body `{draft_id?, document}`）；`GET/DELETE /api/standards/drafts/{draft_id}`；`POST /api/standards/drafts/from-dst`（`{dst_path}`）；`POST /api/standards/drafts/{draft_id}/publish`；`POST /api/standards/drafts/{draft_id}/assets/{asset_id}/inspect`（`{cad_version}`）；`POST /api/standards/import`（`{path}`）；`GET /api/standards/{id}/{ver}/export`（zip 下载）；`GET /api/standards/{id}/{ver}`（detail 含 `document`）；`PUT /api/standards/{id}/{ver}`（body 即标准文档；已发布→409 `STANDARD_VERSION_IMMUTABLE`）。
- 错误码映射：`STANDARD_VERSION_EXISTS/STANDARD_DRAFT_EXISTS`→409；`*_NOT_FOUND`→404；其余 422；`STANDARD_DEPENDENCY_MISSING`→409（发布门禁）。这些码**未登记**进 `message_catalog.CATALOG`——前端暂时按未知错误显示原始 message，i18n 文案键随前端任务渐进补齐。

### 受信扩展依赖
- `ExtensionManifest.provided_capabilities: tuple[ExtensionProvidedCapability, ...]`（capability_id + SemVer，YAML `provided_capabilities:`）；`standard_dependency_gaps(dependencies, manifests)` 返回 `extension-missing/capability-missing/version-too-old` 三种缺口。测试可用 `BuiltinExtensionEntry(manifest_resource=str(yaml_path), factory=...)` 注入。

### 前端（Task 7）
- `useStartNavigation()`：`surface: Ref<"welcome"|"standards"|"create-sheetset">` + `openStandards/goWelcome/openCreateSheetset`。
- `createStandardStore(api): StandardStore`：open/refresh 代次保护（乱序丢弃）；pending/error 显式；`api` 契约见 `features/standards/store.ts` 的 `StandardApi`（测试替身模式见 `store.test.ts` 的 `deferredStandardApi`）。
- i18n `standards` 域已注册进 `i18n/index.ts`；E2E 假壳桥注入模式见 `tests/e2e/standards-welcome.spec.ts`。
- `StandardDetail.document` 是 Task 8 新加字段（后端已实现并重生成契约，未提交）。

## 五、环境注意（沿用 + 新增）

1. rtk 会吞 pytest/vitest 汇总行：用 `rtk proxy uv run pytest ... | tail` 或 `rtk proxy` 前缀看完整输出。
2. **输出长标识符时曾出现系统性拼写漂移**（同一词两种拼法）——前端组件/模板一律以 `npx vue-tsc -b` 报错为准修复，禁止目检通过。
3. `UiSelect` 无 `options` prop，选项用默认插槽 `<option>`；`UiInput` 支持 `label` prop；`UiButton` 的 `variant` 只有 secondary/danger 等既有值（用前 grep `web/src/components/ui/UiButton.vue`）。
4. `web/src/style.css` 是入口样式表，**只允许层序与 @import**（check:ui 门禁）；全局新类放 `styles/primitives.css` 的 `@layer primitives`。
5. E2E 全量跑法：`npm run test:e2e -- <spec>` 实际会先跑 settings-file-mutating 项目再并行其余（Playwright projects 配置）；standards 系 spec 放 `web/tests/e2e/`，beforeEach 注入假壳桥 + mock `/api/extensions`。
6. Python 侧 ApplicationError 断言、rtk 注意事项同前一份接手文档 §三。

## 六、剩余任务速查

- **Task 8**（当前）：见 §三。
- **Task 9** 分区编辑器：`buildMappingRows`/`validateMapping`/`renderCompositionPreview`（`features/standards/draftModel.ts`）；`StandardEditor.vue` 等 6 组件；映射批量粘贴 `燃气\tRQ\n...`→一条规则；编辑按钮接线（StandardsView `editorAvailable` 翻转）。
- **Task 10** 资产检查 + 发布检查页：`buildPublishGate`；`StandardStore.inspectDraft()` 对接 Task 5 的 `AssetInspection`。
- **Task 11** 收口：ST-UI 追踪矩阵、视觉证据（`standards-visual-evidence.spec.ts` + `docs/dst-manager/specs/assets/SPEC-DM-016/`）、全量门禁（`npm run check:api/check:i18n/check:ui/test:unit/build/test:e2e` + `ruff/pytest/alembic/uv lock`）、G8/G9 对照；届时统一勾选计划复选框、计划 status 改 `completed`，并补记"`cad_job.py` 未修改"的说明（Task 5 遗留）。
