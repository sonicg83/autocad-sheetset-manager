---
id: PLAN-DM-035-HANDOFF-TASK10
title: PLAN-DM-035 实施接手文档（Task 9 已提交，Task 10 进行中）
created: 2026-09-22
status: active
---

# PLAN-DM-035 接手文档（2026-09-22 Task 10 起点）

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
| 8 主从分栏标准库 | ✅ | `0ab67de` | |
| 9 分区编辑器 | ✅ | `305a2e6` | `draftModel.ts` + 6 组件 + `standards-editor.spec.ts` 8 项 |
| 10 资产检查 + 发布检查页 | 🔶 **下一步（未开工）** | — | 见 §三 |
| 11 收口（证据/门禁/文档） | ⬜ 未开始 | — | |

验证基线：Task 9 提交时 `vue-tsc -b`、`check:api`、`check:i18n`（1153 键）、`check:ui`、`npm run build` 全过；全量前端单测 209 项通过；标准系 E2E 21 项 + settings-dialog 33 项 + 守卫相关 45 项通过。

## 二、Task 9 交付要点（Task 10 直接依赖）

### 新增文件
- `web/src/features/standards/draftModel.ts`（纯函数，无 Vue/网络）：`toDraftDocument`/`cloneDocument`、`parsePropertyCsv`、`buildMappingRows`、`validateMapping`（行级诊断带 `row`）、`renderCompositionPreview`、`validateDraftStructure`（返回 `{code, ruleId?, field?, row?}`）、`ruleSummary`、`KNOWN/EDITOR_SECTIONS`、`draftKey`、`knownFieldReferences`、`fieldReference`、`isReservedScope`、`nextRuleId`、`isValidPadFormat`。
- `web/src/components/standards/`：`StandardEditor.vue`（壳层）、`StandardSectionNav.vue`、`StandardPropertyEditor.vue`、`StandardRulesEditor.vue`、`MappingTableEditor.vue`、`CompositionEditor.vue`。
- `web/tests/e2e/standards-editor.spec.ts`（8 项）。

### Task 10 必须接手的接线点
1. **占位区**：`StandardEditor.vue` 的 `assets` 与 `publish` 分区当前渲染 `standards.pendingSection.assets` / `standards.pendingSection.publish` 占位文字；「发布检查」按钮由 props `publishAvailable`（缺省 false → 原生禁用 + `standards.editor.publishPending` 说明）控制。Task 10 需要：实现两个分区、把 `publishAvailable` 置真并接 `@publish-check`（或用同一 props 传回调），并**删除这两组不再使用的 i18n 键**。
2. **跳转机制已就绪**：壳层 `focusRequest = {section, ruleId?, row?}` 已传给 `MappingTableEditor`（watch + `nextTick` 后聚焦该行 source 输入，行号 1 起始）。发布检查页的问题跳转应复用同一机制，按需扩展到 assets/rules 分区（给相应组件加同样的 `focus-request` prop）。
3. **结构诊断已在壳层**：`StandardEditor` 的 `diagnostics = validateDraftStructure(buffer)` 含映射行级条目（`row` 有值）并在存在诊断时原生禁用「保存草稿」。发布门禁的“规则/属性/映射”类错误可直接复用这份诊断，不要另写一套校验；资产与依赖类错误来自后端报告。
4. **资产检查 API 已封装**：`store.inspectAsset({draftId, assetId, cadVersion})` → `POST /api/standards/drafts/{draft_id}/assets/{asset_id}/inspect`，响应 `{asset_id, kind, layouts, diagnostics:[{code,severity,message}]}`；`severity` 是 `error|warning|info`。
5. **发布 API 已封装**：`store.publish({draftId})` → `POST /api/standards/drafts/{draft_id}/publish`，成功返回 `{standard_id, version, name}`；缺少受信能力时 409 `STANDARD_DEPENDENCY_MISSING`。发布成功后 SPEC-DM-016 §9.2 要求进入新版本只读详情并提供“导出标准包 / 用于创建图纸集 / 派生新草稿”——`StandardDetailPane` 已具备这三个动作，`StandardsView.leaveEditor()` + `store.refresh()` 已可复用。
6. **E2E 夹具**：`web/tests/e2e/fixtures/standards.ts` 已支持 list/detail/草稿 GET/PUT/创建/删除/导入，并提供 `draftDocument()`、`partialMappingDraft()`、`openDraftEditor(page)`、`openEditorSection(page, id)`、`editorSaveState(page)`。Task 10 需在同一 `installStandards` 内补资产检查与 publish 端点（含失败注入），不要另起夹具。

### 编辑器行为约定（Task 10 勿回退）
- 保存按钮：`invalid`（有结构诊断）时原生 `disabled`；`clean` 时 `aria-disabled`（可聚焦的语义禁用，SPEC-DM-015 §5.2）；`saving` 时 `loading`。
- 保存状态文案：`saving` → 正在保存…；`dirty-invalid` → 有未保存修改，请先修正下方问题；`dirty-valid` → 有未保存修改；`clean` → 已保存。
- 基线必须与缓冲经过同一 `toDraftDocument` 规范化（否则补齐默认键会造成假 dirty）。
- 草稿保存走 `PUT /api/standards/{standard_id}/{version}`（请求体即文档、身份取自文档内部）；`POST /api/standards/drafts` 带已存在 `draft_id` 会 409。
- 草稿读取 `GET /api/standards/drafts/{draft_id}`；创建后可 `store.adoptDraft(created)` 直接进入编辑器，不必多发一次 GET。
- 离开编辑器（返回标准库、切换选中项）必须先过 `StandardEditor` 暴露的 `guard()`；选择切换经 `StandardsView.select()` 的 `editorRef.value?.guard(apply)`。

## 三、Task 10 起手待办（按顺序）

1. 先写 `web/src/features/standards/publishModel.test.ts`（计划 Step 1，先失败）：`buildPublishGate(report)` 对布局严格匹配失败返回 `canPublish=false` 且 `blockingErrors[0].target = {section:"assets", assetId:"layouts", layout:"A3"}`；只有警告时 `canPublish=true` 且 `warnings` 非空。诊断 `severity` 与 `code` 的解释放模型，文案仍经语言包。
2. 实现 `TemplateAssetsEditor.vue`（基础/布局模板为主分类，官方/用户为筛选器；列表显示名称/来源/状态/引用数）与 `AssetInspectionPanel.vue`（受控路径、资产身份、引用关系、检查时间、诊断、重新检查；布局资产列出全部非 `Model` 布局并严格比较图幅）。官方资产只读；用户资产替换前显示影响范围（走 App 共享 `confirmAction`）。
3. 实现 `StandardPublishReview.vue`（独立检查页，不是小确认框）：左侧检查域与错误/警告计数，右侧问题列表与修复入口、版本号/版本说明、发布动作；错误禁用发布、警告可继续并在发布动作附近汇总；每个问题可返回对应分区并聚焦到字段/映射行/资产。
4. 修改 `StandardEditor.vue`：分区 6/7 换成实际面板，`publishAvailable` 置真并接 `@publish-check`，`@publish` 成功后由 `StandardsView` 退出编辑器并刷新到新版本只读详情。
5. 门禁与提交：`npm run test:unit -- src/features/standards/publishModel.test.ts`、`npm run build`、`npm run test:e2e -- standards-assets-publish.spec.ts`；更新 `changelog.md` 后 `git add web/src/components/standards web/src/features/standards web/src/views/StandardsView.vue web/tests/e2e/standards-assets-publish.spec.ts web/tests/e2e/fixtures/standards.ts changelog.md`，commit message：`实现标准模板资产与发布检查界面`。

## 四、API 与领域事实速查

### 端点
- `GET /api/standards`；`POST /api/standards/drafts`（`{draft_id?, document}`）；`GET/DELETE /api/standards/drafts/{draft_id}`；`POST /api/standards/drafts/from-dst`（`{dst_path}`）；`POST /api/standards/drafts/{draft_id}/publish`；`POST /api/standards/drafts/{draft_id}/assets/{asset_id}/inspect`（`{cad_version}`）；`POST /api/standards/import`（`{path}`）；`GET /api/standards/{id}/{ver}/export`（zip）；`GET /api/standards/{id}/{ver}`（detail 含 `document`）；`PUT /api/standards/{id}/{ver}`。
- 错误码：`STANDARD_VERSION_EXISTS`/`STANDARD_DRAFT_EXISTS`/`STANDARD_DEPENDENCY_MISSING`→409；`*_NOT_FOUND`→404；`STANDARD_IDENTITY_MISMATCH` 等→422。这些码**未登记**进 `message_catalog.CATALOG`（前端按未知错误显示原始 message）。

### 资产检查（Task 5 后端语义，前端投影需一致）
- `STANDARD_LAYOUT_NAME_MISMATCH`：声明图幅缺少同名非 `Model` 布局（`"A2 "` ≠ `"A2"`，大小写敏感）。
- `STANDARD_CAD_CAPABILITY_MISSING` / `STANDARD_LAYOUT_READ_FAILED` / `STANDARD_ASSET_FILE_MISSING`：CAD 能力缺失、读取失败、资产缺失。
- 未被引用的有效资产 = 警告（不阻断发布）。

### 标准文档形状（编辑与发布共同依赖）
- `properties[{name, scope, required, default_value, enum_values, description}]`；`scope ∈ sheetset|sheet|subset|derived`（`subset` 首版预留）。
- `rules[{rule_id, kind, target, source?, value?, allowed[], table[[src,tgt]], segments[{field?|literal?, format?}]}]`；`kind ∈ required|enum|fixed|mapping|compose|numbering|naming`（首版求值只处理前六类中的 mapping/compose/naming/fixed/required/enum）。
- `assets[{asset_id, kind∈base-template|layout-template, files[{path, role}]}]`；`numbering{sequence_field, digits, start}`；补零格式码 = 1–12 的整数字符串。

## 五、环境注意

1. rtk 会吞 pytest/vitest 汇总行（用 `> log 2>&1` 后查进度行，或加 `rtk proxy` 前缀）。
2. 前端组件/模板以 `npx vue-tsc -b` 为准修复，禁止目检通过。`vue-tsc` 只覆盖 `src/**`，`tests/e2e` 的类型错误只在运行期暴露。
3. `UiSelect` 无 `options` prop（默认插槽 `<option>`）；`UiButton` 的 `variant` 只有 primary/secondary/danger/link，禁用语义分 `disabled`（原生）与 `ariaDisabled`（可聚焦）。
4. CSS 变量必须已登记（`tokens.css`）：未登记变量即使有 fallback 也会被 `check:ui` 拦截；`min-width:240px` 这类裸视觉值同样违规。图标按钮用 `UiIconButton` + `label`（它的 `@click` 靠属性透传）。
5. `check:i18n` 扫描全部非测试 `.ts/.vue`：模型不得返回中文文案，只返回稳定码/语言包键；用户数据常量需登记进 `web/src/i18n/hardcoded-allowlist.json`（含 reason）。
6. E2E：`npx playwright test <spec>` 会先跑 settings-file-mutating 项目（settings-dialog 33 项）再跑其余，单次约 1–1.5 分钟；标准端点 mock **必须用 URL 谓词**注册（`**/api/standards**` glob 会拦掉 vite 的 `src/api/standards.ts` 模块请求）。Playwright 的 `getByRole(name)` 是子串匹配。
7. 不要用 bash heredoc 里的 Python 脚本改含 `\t`/`\n` 转义的 TS 字符串（本机 shell 会吞反斜杠），改用编辑工具逐处替换。

## 六、剩余任务速查

- **Task 10**（当前）：见 §三。
- **Task 11** 收口：ST-UI 追踪矩阵、视觉证据（`standards-visual-evidence.spec.ts` + `docs/dst-manager/specs/assets/SPEC-DM-016/`）、全量门禁（`npm run check:api/check:i18n/check:ui/test:unit/build/test:e2e` + `ruff/pytest/alembic/uv lock`）、G8/G9 对照；届时统一勾选计划复选框、计划 status 改 `completed`，并补记「`cad_job.py` 未修改」的说明（Task 5 遗留）。SPEC-DM-016 §12 的追踪矩阵需覆盖 ST-UI-01～12，其中 ST-UI-05/06/07/11 已由 `standards-editor.spec.ts` 承接，ST-UI-08/09/10 待 Task 10 的 `standards-assets-publish.spec.ts` 承接。
