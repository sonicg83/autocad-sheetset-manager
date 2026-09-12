# 扩展设置相关文件超出/贴近 500 行软上限（容量债）

日期：2026-09-13

状态：待办（未立项；来源 PLAN-DM-025 任务 8 评审 M7 与任务 9 判定的 R25）

关联：`SPEC-DM-011`、`PLAN-DM-025`

## 问题

`AGENTS.md` 的代码组织契约规定单个源文件约 500 行为软上限。PLAN-DM-025 交付后，扩展设置相关文件的实测行数（2026-09-13 在任务 9 收口提交上测得）：

- `web/tests/e2e/extensions-settings.spec.ts`：**1148 行**（任务 7 起持续增长；已超上限 2 倍以上）；
- `web/tests/e2e/sheet-catalog.spec.ts`：**1233 行**（含任务 8 新增的输出图纸过滤与预览契约用例）；
- `web/src/composables/useSheetCatalogSettings.ts`：**496 行**（贴近上限，业务页与设置中心 custom 面板共用同一 composable）；
- 对照（已回落，无需处理）：`web/src/components/settings/SettingsDialog.vue` 由任务 6/7 从 535 行降到 **469 行**，`ExtensionSettingsHost.vue` 285 行、`GeneratedExtensionSettingsForm.vue` 146 行。

这不是正确性缺陷：拆分属重构，必须保持既有公共接口、错误码与序列化契约不变，并依赖现有测试作安全网，因此 PLAN-DM-025 明确不做一次性重写，只登记债务。

## 完成条件

- 按 `AGENTS.md` 的拆分契约把上述 spec 按行为域拆分（例如 `extensions-settings.spec.ts` 拆为「入口与子视图」「generated」「custom」「失败与并发」「高版本只读」等文件），共享夹具继续放在 `web/tests/e2e/fixtures/`，不得复制夹具实现；
- `useSheetCatalogSettings.ts` 按「模板状态」「过滤设置」「预览契约」域拆分或抽纯函数模块，业务页与设置中心两处实例化路径保持不变；
- 拆分后 `npm run check:i18n`、`check:api`、生产构建与四套相关 E2E 全部通过，用例数不得减少（只允许搬迁）。

## 触发重开条件

- 在上述任一文件上继续追加用例或方法之前（先拆、后加）；
- 计划为扩展设置增加第三个 `custom` 面板或将扩展配置入口扩展到更多扩展时。

## 备注

同一批评审中另有少量 Minor 未修（`loadFailed` 仅由 `load()` 清除、闸门初始焦点落在首个按钮而非卡片、新闸门不消费 `ConfirmOptions` 的 `impactLines/danger/requireCheckbox/reversibility`、不支持控件行的 `span[id]` 无引用），均已按「接受不修」裁决记录在 PLAN-DM-025 的 SDD ledger（`.superpowers/sdd/PLAN-DM-025-extension-global-settings/progress.md`，不入提交树），后续维护时一并处理。
