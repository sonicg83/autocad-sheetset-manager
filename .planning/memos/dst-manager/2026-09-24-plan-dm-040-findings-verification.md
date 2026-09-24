# PLAN-DM-040 发现核实与基线证据（2026-09-24）

来源：对 PLAN-DM-040《图纸标准平台审查问题修复计划》首版的独立审查。核实方式分两类：
对照源码定位（含既有测试与 E2E 断言），以及在系统临时目录中用 FastAPI `TestClient`
对 HTTP 入口做一次性实测复现。所有复现都只使用 `tempfile` 临时目录，未读取或修改
`sample/`、用户工作区与真实标准库。

本文与 [PLAN-DM-040](../../plans/dst-manager/PLAN-DM-040-standard-platform-review-remediation.md)
的范围表配套：范围表只给证据类型，本文给逐项位置与实测输出。一次性探针不作为回归测试
长期保留；对应 RED/GREEN 由 PLAN-DM-040 Task 1/2/3 固化为正式用例。

## 一、实测复现（临时目录 + TestClient）

| 发现 | 复现输入 | 实测结果（修复前） |
| --- | --- | --- |
| F02（导入） | ZIP 内 `manifest.json` 声明 `assets/missing.dwg`，但包内没有该条目；`POST /api/standards/import` | **200**，标准已写入用户标准库，文档保留悬空声明 |
| F02（发布-缺失） | 草稿声明 `assets/missing.dwg` 且文件不存在；`POST /api/standards/drafts/d1/publish` | **200**，草稿被移动为已发布版本 |
| F02（发布-绝对路径） | 草稿声明 `C:\outside\secret.dwg`；`POST /api/standards/drafts/d2/publish` | **200**，与本计划“不把本机绝对路径写进 `document.json`”的全局约束冲突 |
| F15（同批核实） | 包内条目原始名 `assets/../A2.dwg` | `_normalize_entry_name` 先 `posixpath.normpath` 再检查分量，归一为 `A2.dwg` 后通过；未构造逃逸写入（`../../x` 仍被拒绝） |
| F17（读取） | `GET /api/standards/%2E%2E/%2E%2E`，在标准库根上两级预置合法 `document.json` | **200**，响应体为该根外文档的完整内容（`standard_id`/`name` 均来自根外文件） |
| F17（导出） | `GET /api/standards/%2E%2E/%2E%2E/export`，根外目录同时含 `assets/secret.dwg` | **200 application/zip**，zip 条目为 `['manifest.json', 'assets/secret.dwg']`，根外文件被打包 |

补充说明：

- 未编码的 `GET /api/standards/../..` 会被测试客户端按 RFC 3986 归一化，不能到达路由；
  `%2E%2E` 形式可直接进入路由，`standard_id`/`version` 均为 `..`，因此该缺陷真实可达。
- 写入侧不可越界：发布与导入的目录名来自文档内身份，已过 `STANDARD_ID_PATTERN`/
  `STANDARD_VERSION_PATTERN`；越界面是 `GET` 详情/导出与 `save_standard_by_identity` 的
  `store.get` 读取路径。
- F04（草稿段）未构造运行期复现，按源码定位确认；与 F17 属同一缺陷类，Task 1 统一修复。

## 二、源码核实（未构造运行期复现）

| 发现 | 核实位置 | 结论 |
| --- | --- | --- |
| F01 | `web/src/components/standards/TemplateAssetsEditor.vue` 文件行只有 `UiInput v-model="file.path"`（占位 `assets/template.dwg`），组件注释自述后端无资产上传端点 | 真 |
| F03 | `web/src/views/StandardsView.vue` `submitCreate()` 创建后不更新 `selectedKey`；`inspectEditorAsset()`/`publishEditorDraft()` 取 `selected.value.draft_id` | 真 |
| F04 | `src/dst_manager/infrastructure/standards/store.py` 的 `get_draft/save_draft/delete_draft/publish` 均直接 `self._drafts_root / draft_id`；`StandardDraftRequest.draft_id` 可由客户端提供 | 真 |
| F05 | `web/src/features/standards/draftModel.ts:1020` `draftKey` 与 `StandardLibraryPane.vue` 内联键都只用 `source + draft_id ?? version`，不含 `standard_id` | 真 |
| F06 | `StandardEditor.vue` `openReview()` 先按服务端草稿检查，`publish()` 才在 dirty 时 `save()` | 真 |
| F07 | `AssetInspectionPanel.vue` 在 `inspection === undefined` 且无 failure 时渲染 `standards.assets.noDiagnostics`（“本次检查未发现问题。”） | 真 |
| F08 | `web/src/features/standards/store.ts` `open()` 不清空 `detail.value`；`StandardsView.submitCreate()` 派生取 `store.detail.value?.document` | 真 |
| F09 | `standardLibraryModel.ts:66` `versionHistory` 按 `standard_id` 聚合两个来源；`StandardDetailPane.vue` 只 `emit('openVersion', version)`，`StandardsView.openVersion` 保留当前 `source` | 真 |
| F10 | `MappingPropertyDialog.vue` 的 `targets` 只按 `item_id` 索引，切换 `sourceId` 既不清空也不隔离 | 真 |
| F11 | `StandardEditor.vue` 基础分区 `standard_id`/`version` 可编辑；保存经 `save_standard_by_identity`，改 ID 后按新身份找不到草稿返回 404 | 真 |
| F12 | `StandardsView.vue` 的 `@media (max-width:959px)` 只隐藏“未选中时的详情”，列表始终可见且无返回按钮；`standards-library.spec.ts:186` 正是“详情打开后标准库仍可见”的旧断言 | 真 |
| F13 | `useDialogFocus` 已被 10+ 组件使用，但 `StandardCreateDialog.vue`、`StandardsView.vue` 导入弹窗、`OrdinaryPropertyEditor.vue` CSV 弹窗均未接入 | 真 |
| F14 | `StandardLibraryPane.vue` 列表错误只有文本、`empty-filter` 无清除入口；`StandardDetailPane.vue` 详情错误无重试 | 真 |
| F16 | `src/dst_manager/interfaces/shell.py` `FileKind`/`_FILE_KIND_PATTERNS` 与 `web/src/api/shell.ts` `ShellFileKind` 均无 `dststandard`；对应 PLAN-DM-039 F7（第 588 行） | 真，已拆分为 PLAN-DM-041 |

## 三、与既有审查记录的关系

- PLAN-DM-038 的遗留发现（F2 求值缺键、F5 casefold 口径）不在本计划范围，已分别归属
  PLAN-DM-036 与待办 `2026-09-23-standard-name-casefold-parity.md`。
- PLAN-DM-039 的 F1–F6、F8、F9 已在其计划内关闭或登记；F7（原 F16）由 PLAN-DM-041 承接。
- 本计划的 F02、F04、F15、F17 在首版计划中写为“先前审查已复现”，但未见归档记录；
  本文补上可核验的源码位置与实测输出。
