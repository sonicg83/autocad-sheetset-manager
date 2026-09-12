---
id: MEMO-DM-033
title: PLAN-DM-025 扩展全局设置实施计划审查报告
status: final
document_kind: memo
owners:
  - dst-manager
created: 2026-09-12
updated: 2026-09-12
related:
  - PLAN-DM-025
  - ARCH-DM-006
  - SPEC-DM-011
  - PLAN-DM-020
  - PLAN-DM-022
---

# PLAN-DM-025 扩展全局设置实施计划审查报告

本备忘记录 2026-09-12 对 [PLAN-DM-025](../../plans/dst-manager/PLAN-DM-025-extension-global-settings.md)（proposed）的一次只读方案审查：逐项核对计划声称的代码事实（后端与前端各派一个探查代理独立核实）、对照 ARCH-DM-006/SPEC-DM-011 的权威裁决、并检查任务编排与既有门禁记录的一致性。全程未修改源码与计划正文。

## 结论

方案结构扎实：TDD 纪律、任务边界、G4 用户确认门禁、"先抽 controller 再做 UI"的顺序均与 AGENTS.md 和 ARCH-DM-006 高度一致；计划声称"新建"的文件经核实确实均不存在，既有文件名全部准确。但存在 **2 个阻断级问题**和若干边界含糊点，建议修订后再批准开工。

## 阻断级问题（会导致执行失败或与权威架构冲突）

### B1. `scripts/export_openapi.ps1` 不存在

任务 3 步骤 4 与任务 4 步骤 6 均引用：

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File scripts/export_openapi.ps1
```

实际 `scripts/` 目录下只有 `export_openapi.py`（约 1.7K，`npm run check:api` 内部调用的就是它），不存在任何 `.ps1` 版本。该命令在任务 3、任务 4 各出现一次，红灯阶段会直接失败。应改为 `rtk uv run python scripts/export_openapi.py` 或项目既有的 OpenAPI 生成方式。

### B2. 任务 4 偏离 ARCH-DM-006 §11/§12，但未安排修订架构文档

ARCH-DM-006 §11 明确要求每次预览绑定"**相关工作区偏好修订**"，§12 中 `REPREVIEW_REQUIRED` 的触发条件也包含"偏好"。而计划任务 4 接口写明"当前工作区偏好只决定上次选择，不影响输出，因此不进入当前动作摘要"，Preview 响应只回传 `settings_revision`。

偏离理由技术上成立：选择模板会 best-effort 写工作区偏好，若偏好修订进入摘要，刚生成的预览会被自己立刻作废（执行时 409），形成死循环。但这构成计划与权威架构的直接矛盾，且任务 4 的文件清单里没有 `ARCH-DM-006`。二选一：

1. 在任务 4 中同步修订 ARCH-DM-006 §11/§12（把偏好从预览绑定清单和 `REPREVIEW_REQUIRED` 触发条件移除，写明理由与日期）；或
2. 恢复架构要求，把偏好修订纳入摘要。

不能带着矛盾进入实施。

## 建议修订（中优先级）

### M1. `generated` 呈现缺少测试与运行载体

唯一的 Builtin 扩展（`dst-manager.sheet-catalog`）是 `custom` 呈现，固定索引 `BUILTIN_EXTENSION_INDEX`（`src/dst_manager/extensions/builtin/index.py:15-20`）也不再有第二个扩展。任务 3 集成测试要覆盖"generated 字段合并"、任务 6 E2E 要覆盖 generated 表单——后端集成测试需要一个注册了 Provider 且 Manifest 声明 `generated` 的扩展走全链路，计划未说明该载体从哪来（测试专用 index fixture？FastAPI 依赖装配覆盖？）。建议在任务 2 或任务 3 中明确，否则这两步红灯写不出来。前端 E2E 可用 `fixtures/extensions.ts` 模拟，不受此限。

### M2. SettingsDialog.vue 拆分待办未协调

文件实测 535 行（已越过而非计划所称"超过或接近"500 行软上限），且当时存在拆分缺口（首选方案：抽 `AboutSection.vue` + `fetchAbout` 模块级 memo）——**该缺口已于 2026-09-13 由任务 6/7 关闭**：`AboutSection.vue` 已抽出、扩展设置落 `ExtensionSettingsHost.vue`，`SettingsDialog.vue` 实测 469 行；本条不复建待办文件。任务 6 还要往里加"当前 ID 与 dirty 装配"。建议把该待办的裁决与抽出动作并入任务 6 的前置步骤，否则违反"不得把新方法追加进已超限的既有文件"的容量契约。另：`application/extensions/runtime.py` 实测 781 行（计划判断属实且更紧迫），任务 2 删除模板特判后会明显回缩。

### M3. 既有 E2E 钉子与生产证据未纳入回归范围

- SPEC-DM-011 已验证的钉子"卡片内唯一可聚焦元素是开关"（SC-16，2026-09-11 达成）会被任务 5 的"配置"按钮打破，任务 5/6 需显式重写该断言；
- `web/tests/e2e/settings-extensions-production-evidence.spec.ts` 与 `web/tests/e2e/sheet-catalog-visual-evidence.spec.ts` 未列入任务 6/7/8 的文件清单与回归命令——设置中心 UI 变化后，已入库的生产证据截图（`docs/dst-manager/specs/assets/SPEC-DM-011/production/`、`.../SPEC-DM-012/production/`）可能失效，G8 范围应说明是否需要重产。

### M4. ColumnEditor 的 controller 收窄边界未写清

实测 `web/src/components/sheet-catalog/TemplateBar.vue` 与 `ColumnEditor.vue` 的 props 都是完整 `SheetCatalogController`，且 ColumnEditor 还消费 `catalog.preview`、`catalog.trackCaret`。任务 7 步骤 3 说"接收缩窄的 `SheetCatalogTemplateController`"，但设置面板场景（无工作区、无 preview）下这两个依赖如何注入/降级，只有一句"不显示字段浏览器"。这是本次前端重构工作量最大、最容易走样的一步，建议在任务 7 接口段写明缩窄后的接口形状（哪些属性/方法进入 `SheetCatalogTemplateController`）。

## 小问题（提示即可）

- **`EXTENSION_SETTINGS_SCHEMA_NEWER` 是文案键不是错误码**：任务 3 未写明 PUT 未知高版本 409 响应用什么 `code`（复用 `EXTENSION_SETTINGS_INVALID`？），ARCH-DM-006 §12 错误码表也没有对应条目，建议补一句并同步错误码表。
- **`web/src/composables/useSheetCatalog.ts` 实测 680 行**，同样超软上限——任务 7 抽取 `useSheetCatalogTemplates` 恰好能改善，可在任务 7 验收中加"行数回落"一条，呼应容量契约。
- **存量设置数据形状**：任务 2 步骤 4 未提既有存量数据——当前 `extension_settings` 表里已存有 PLAN-DM-020 写入的模板 JSON。若旧实现存的是"完整模板集"而新 Provider 语义是"只存用户模板"，需要一次迁移（哪怕同 schema 版本内规范化）剥离内置模板，否则"内置不可变"校验会把存量内置模板当作用户数据。建议任务 2 红灯加一条存量形状测试。

## 事实核对记录（抽样）

| 计划声称 | 核实结果 |
| --- | --- |
| 新建 `src/dst_manager/extensions/settings.py`、`application/extensions/settings.py`、三个 Vue 组件、两个 composable、`test_extension_settings_contracts.py`、`test_extension_settings_service.py` | 均不存在，确属新建 |
| `_TEMPLATE_SETTINGS_EXTENSION_ID`、`_save_catalog_templates()`、专用 `if` 分支 | 属实：`application/extensions/runtime.py:94,340,363-407` |
| `extension_settings` / `workspace_extension_preferences` 表 | 存在于 `infrastructure/persistence/extensions.py`，字段与"不新增表"前提一致 |
| `BuiltinExtensionEntry` 仅 `manifest_resource`/`factory` 两字段 | 属实（`contracts.py:58-62`），加 `settings_provider` 属真新增 |
| manifest 无 `settings_contribution` 概念 | 属实（`manifest.py` 仅 `settings_schema`） |
| `ExtensionContext` 目前只有 `workspace_snapshot()` 能力 | 属实（`capabilities.py:60-122`） |
| `npm run check:api`/`check:i18n`/`build`/`test:e2e` 脚本 | 齐全（`web/package.json`） |
| g4-01～g4-12 冻结截图存在 | 属实（`docs/dst-manager/specs/assets/SPEC-DM-011/`），新增 g4-13～15 编号连续 |
| SC-16 现行文本（"卡片不承载设置入口"）与 ARCH-DM-006 §8.2（设置中心统一入口）矛盾 | 属实；任务 5 修订 SC-16 并新增 SC-17 正确解决 |
| 迁移不落库、未知高版本只读、摘要冻结、副作用前检查漂移、打包守护 | 与 ARCH-DM-006 §8/§11/§13 精确对齐 |

## 处置建议

修复 B1、B2 并对 M1～M4 补充说明后，PLAN-DM-025 可进入批准状态。小问题可在实施中顺带处理，不阻塞批准。
