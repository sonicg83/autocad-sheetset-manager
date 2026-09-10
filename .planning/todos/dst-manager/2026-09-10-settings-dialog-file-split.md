# SettingsDialog.vue 拆分待办（越过 500 行软上限）

日期：2026-09-10

状态：待立项；由「停用不可逆」修复引入

关联：`SPEC-DM-011`（SC-15 扩展分区）、`ARCH-DM-006` §7、`AGENTS.md` 代码组织契约

## 背景

`AGENTS.md` 规定单个源文件以约 500 行为软上限，并要求「接近上限时应在当次变更或后续计划中安排拆分，不得默认继续追加」。本次修复「图纸目录扩展停用不可逆」时，在设置中心新增了第三分区（扩展）及其停用编排：

| 文件 | 改动前 | 改动后 |
| --- | --- | --- |
| `web/src/components/settings/SettingsDialog.vue` | 465 行 | **534 行**（PLAN-DM-022 修订后 535 行） |

拆分动作（新增 `components/settings/ExtensionsSection.vue`、`composables/useExtensions.ts`）本身已按契约执行——新功能没有堆进既有文件，但编排逻辑（让位给宿主三选一闸门、两处失败呈现路径）必须留在持有 `close()` 与 `hasUnsaved` 的对话框内，仍使该文件越过了软上限。

> **PLAN-DM-022 修订后重估（2026-09-10）**：启停交互改进删掉了「停用前关闭对话框让出 top layer」整条路径（闸门已改为原生 `<dialog showModal>`，自行叠在设置窗口之上），`onToggleExtension` 精简为「落库 → 就地收敛/行内呈现 → 归还开关焦点」，文件净 +1 行。因此待办原因收窄为：扩展开关的编排、`extensionsError` 行内呈现与焦点归还仍需要对话框持有的 `dialogEl` 与 `extensionsPanel`，而那两处（`extensionsBusy`/`focusExtensionSwitch`）都是约 10 行的编排，不足以单独成模块。方案与裁决顺序不变，优先级可下调。

## 已评估的拆分方案与取舍

1. **抽出 AboutSection（SC-11，约 90 行）——首选，但需解决语义保持问题。**
   现状 `showAbout()` 在 `about.value` 已加载时提前返回；会话内切换分区不重新拉取。改为子组件后，`v-if` 会在每次切回时重新挂载并重放 `GET /api/about`，用户会看到一次「正在加载…」闪烁，与既有行为不一致。解决方式二选一：在 `api/settings.ts` 为 `fetchAbout` 增加模块级 memo（About 是静态应用元数据，缓存语义成立），或让子组件常驻并以 `v-show` 控制显隐、暴露 `activate()` 供懒加载。需要先裁决，不能顺手改。
2. **把扩展编排抽成 composable——否决。**
   它需要注入 `panel` / `isDirty` / `confirmDiscard` / `closeDialog` / `notifyFailure` / `errorText` 六个依赖，只是搬运行数而非建立真实边界，不改善可读性也不降低耦合。
3. **把扩展编排下推到 ExtensionsSection——否决。**
   同样需要注入关闭对话框、未保存状态与两个失败呈现通道；分区从纯呈现组件退化为持有对话框生命周期知识的组件，边界更差。

## 安排

1. 先裁决方案 1 的缓存/懒加载语义（建议：`fetchAbout` 模块级 memo，理由与 `useSettings`/`useTheme` 的模块级单例模式一致），并在 `SPEC-DM-011` 记一句关于分区数据的加载语义。
2. 抽出 `components/settings/AboutSection.vue`，保持既有可访问名与文案键不变（`settings.about.*`）。
3. 以 `tests/e2e/settings-dialog.spec.ts` 的「关于分区：应用名+版本、MIT 全文与外链」为安全网，补一条「分区来回切换不重放 GET /api/about」的钉子。
4. 复核拆分后 `SettingsDialog.vue` 是否回到软上限内；若仍有富余，继续评估把扩展编排拆为 `ExtensionsPanelController` 的真实边界（届时 `useConfirm` 若已是模块级单例，可减少注入面）。

## 完成条件

- `SettingsDialog.vue` 回落到约 500 行以内，且不改变任何既有可访问名、文案键、保存/取消语义与拖动拦截行为；
- 关于分区仍保持「会话内不重复拉取」的既有行为，并有自动化钉子；
- 无新增 `AGENTS.md` 禁止的目录/生成物进入提交树。
