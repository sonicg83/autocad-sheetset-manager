---
id: MEMO-DM-034
title: PLAN-DM-025 任务 5 G4 设计门禁确认记录
status: final
document_kind: memo
owners:
  - dst-manager
created: 2026-09-12
updated: 2026-09-12
related:
  - PLAN-DM-025
  - SPEC-DM-011
  - ARCH-DM-006
  - MEMO-DM-033
---

# PLAN-DM-025 任务 5 G4 设计门禁确认记录

本备忘记录 [PLAN-DM-025](../../plans/dst-manager/PLAN-DM-025-extension-global-settings.md) 任务 5 步骤 5 的强制暂停点：**扩展全局设置入口（SPEC-DM-011 SC-17）的 G4 设计门禁第三次重开，用户已确认通过**。门禁记录同步写入 [SPEC-DM-011 §8](../../../docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md)。

## 提交给用户的门禁材料

- **可操作 Demo**：`docs/dst-manager/mockups/SPEC-DM-011-settings-demo.html`（`file://` 自包含，无后端；CSP `connect-src 'none'`）。
- **规格**：`docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md` —— SC-16 修订 + 新增 SC-17（§3.3 四条状态规则、§5 第三次裁决、§7 冻结件索引、§9 证据归属）。
- **三张新冻结图**：`docs/dst-manager/specs/assets/SPEC-DM-011/g4-13-extension-config-entry-light.png`、`g4-14-extension-config-generated-light.png`、`g4-15-extension-config-custom-dark.png`（由 `web/tests/e2e/settings-demo-visual-evidence.spec.ts` 以 `file://` 驱动 Demo 产出，21 例全绿）。

## 用户批准的内容

| 项 | 批准结论 |
| --- | --- |
| 入口形态 | 卡片本体仍不可点击、不可聚焦；仅声明设置的扩展出现文字「配置」按钮 |
| 动作行顺序 | 固定为「配置按钮 → 状态文字 → 开关」，可访问名「配置 {name}」 |
| 子视图 | 与扩展列表同处一个设置 `<dialog>`，平级子视图 + 可见「返回扩展列表」，不叠第二层模态 |
| 类型分派 | `generated` 由 Provider 字段元数据渲染动态表单；`custom` 使用扩展专属组件（复杂设置不退化为 JSON 文本框） |
| 保存粒度 | 按扩展独立保存，不与核心设置共享提交或修订号 |
| 脏状态闸门 | 返回 / Esc / 遮罩 / 关闭确认四条出路均先过闸门 |
| 焦点归还 | 返回子视图 → 卡片「配置」按钮；关闭对话框 → 齿轮入口（SC-09） |
| 服务端三态 | 字段超限行内定位、修订冲突保留输入、更高 Schema 只读禁用保存 |

确认人：用户。确认日期：2026-09-12。确认方式：控制器在任务 5 修复轮复核通过后提交门禁材料，用户明确答复「确认通过」。

## 提交时向用户显式声明的保留意见

以下 5 点在请求确认时已一并告知，属**已接受的设计证据边界**，不构成未关闭事项：

1. `g4-14` 的 `generated` 扩展（`demo.frame-update`「图框批量更新」）是 **Demo 专属设计证据**，不在生产 `BUILTIN_EXTENSION_INDEX` 内（生产只有图纸目录 `custom`）——任务 7/8 不得据此新增扩展；SPEC-DM-011 §7 已声明。
2. `g4-07～g4-12` 是**重开前**的冻结件，看不到「配置」按钮，不得据其判断新动作行；该目录不重取、不覆盖（SPEC §7 已声明）。
3. 深色/分段列表动作行、子视图最小视口与 200% 缩放、以及超限/冲突/只读三态**没有冻结图**，只有行为用例。
4. 门禁未重跑实现者自述的全部测试数字（独立复核范围为只读核对：定向命令与变异验证已复现）。
5. `config_revision r7`、`设置修订 r2-r8` 等均为 Demo 模拟值，不代表生产状态。

## 门禁通过后的必交项（随任务 7/8 收口）

- **任务 7/8 必交**：更新 `web/tests/e2e/extensions-settings.spec.ts:226-243` 的可聚焦元素钉子（现断言 `["BUTTON[switch]"]`），并让夹具 `extensionSummary()`（`web/tests/e2e/fixtures/extensions.ts`）声明 `settings_contribution`；在该钉子更新前不得把 SC-17 当作已有自动化证据（SPEC-DM-011 §9 已写明）。
- **任务 8 承接**：`total_rows` 口径变更（现为过滤后的实际输出行数）对应的 `CatalogPreview.vue` 文案与「已过滤 N 张图纸」元素、`filteredRows` 映射，以及与 SPEC-DM-011/012 中冻结断言「共 N 张图纸」的协调（改文案时一并处置，但不得重取历史图片）；预览响应违约（`settings_revision` 非 number）时的可见诊断。
- **任务 9 承接**：`filtered_rows`/`total_rows` 的 SPEC/GUIDE 字段表同步；`SHEET_CATALOG_TEMPLATE_CONFLICT` 的生产可达性或删除收口。

## 门禁后的执行顺序

任务 6（`SettingsDialog.vue` 容量拆分）可与任务 7 并行或先行；任务 7、8 在门禁通过后可开始，且均须按 PLAN-DM-025 的 TDD 与独立复核流程执行；任务 9 收口全量回归与文档。
