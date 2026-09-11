---
id: MEMO-DM-029
title: PLAN-DM-022 SDD 执行交接——扩展卡片基线与布尔开关统一下沉（T1–T3 完成、T4 半成品）
status: draft
owners:
  - dst-manager
created: 2026-09-10
updated: 2026-09-10
related:
  - PLAN-DM-022
  - SPEC-DM-011
  - SPEC-DM-006
  - ARCH-DM-006
---

# PLAN-DM-022 SDD 执行交接（MEMO-DM-029）

> **性质：** 会话中断交接单。本次执行按 `superpowers:subagent-driven-development` 逐任务派子代理、逐任务评审，用户在中途要求暂停。**T1～T3 已完成（评审通过、提交在案）；T4 为半成品（未提交，已验证可运行）**。下次从 T4 继续。

## 1. 一句话状态与下一步入口

- 计划：[PLAN-DM-022](../../plans/dst-manager/PLAN-DM-022-extension-card-baseline.md)（状态仍为 `proposed`，未改为 `active`）。
- 进度：批次 1（T1）与批次 2（T2、T3）已完成；批次 3（T4：G8 生产证据 + 文档收口）未完成。
- 下一步：**从 T4 继续** → 跑证据 spec 产出 5 张图 → 复制到 `docs/dst-manager/specs/assets/SPEC-DM-011/production/` → 逐张与冻结件比对 → 更新 `SPEC-DM-011` §7/§8/§9 与 `changelog.md` → 提交；然后**最终全分支评审** → `superpowers:finishing-a-development-branch`。
- SDD 台账（git-ignored，仅本机存在）：`.superpowers/sdd/PLAN-DM-022-extension-card-baseline/progress.md`。本 memo 第 7、8、9 节是它的持久副本，即使 `.superpowers/` 被清理也能恢复。

## 2. 本次会话做了两件事

**上半程：确立扩展卡片基线（已完成并提交）**
1. 讨论并裁决卡片基线四项：单列卡片 + 面板滚动、≥6 条按 `enabled` 分段、四层信息、卡片不可点击（唯一交互是开关）；并按用户选择把布尔状态控件**统一为滑动开关**。
2. 交付基线：`SPEC-DM-011` 正文条款（§1/§3.2/§3.3/§4 SC-16/§5 二次 G3 裁决/§6/§7/§8/§9）、`SPEC-DM-006` §6.3 控件规范、Demo 重开（新增扩展分区三档条目数 + 统一开关）、12 张 G4 证据截图（`docs/dst-manager/specs/assets/SPEC-DM-011/g4-01…g4-12`）、新证据 spec `web/tests/e2e/settings-demo-visual-evidence.spec.ts`（13 例）。
3. 用户对重开后的 Demo 操作确认 → `SPEC-DM-011` §8 的 G4 由「进行中（重开）」改为**通过**。
4. 顺带修掉两处悬空引用：代码注释里 15 处 `PLAN-DM-022`（当时该 Plan 不存在）改为 `SPEC-DM-011 修订「启停交互改进」`；`UnsavedInputDialog.vue` 头部的 `SPEC-DM-015 任务 5`（SPEC-DM-015 不存在）改为 `SPEC-DM-009 §6.2 / PLAN-DM-016 任务 2`。
5. 发现并记录一个既有缺口：`SPEC-DM-011` §7/§8 一直引用 `assets/SPEC-DM-011/` 与 `production/` 作为 G4/G8 证据，但这些图**从未进入版本库**、本地亦已不可复现（`.superpowers/` 被 `.gitignore` 忽略）。本次重冻结把 12 张标准集提交进仓库，并在 §7 写明证据位置约定。

**下半程：执行 PLAN-DM-022（T1–T3 完成，T4 半成品）**
- 用户选择「子代理驱动」执行，并同意「先提交当前批次，再在 main 上逐任务实施并提交」。
- 期间发现历史被外部提交过一版：`bae415d`（release v0.3.5）已把「停用不可逆 + 启停交互改进」整批收入历史；故开工前只补了两个收尾提交 `d61d79f`、`93c632b`。

## 3. Git 现状

**HEAD = `4d67755`**（`main` 分支）。本次相关提交（新→旧）：

| 提交 | 内容 |
| --- | --- |
| `4d67755` | 为扩展分区补按启用状态分段的增长机制（**T3**） |
| `fa041de` | 下沉扩展卡片承接四层信息（**T2**） |
| `addf04c` | 按冻结件统一卡片状态文字类名（计划修正，Ruling 4） |
| `2bfac5c` | 统一设置中心布尔状态控件为滑动开关（**T1**） |
| `e93f482` | 修正 bool 行断言的元素限定避免多元素命中（计划修正） |
| `cdbe7a2` | 修正计划中开关文字位置与红灯预期（计划修正，Ruling 2） |
| `93c632b` | 确立扩展卡片基线并补冻结件与证据（含 12 张 G4 截图 + PLAN-DM-022 + 新证据 spec） |
| `d61d79f` | 修正注释中对不存在的 Plan 与 Spec 的悬空引用 |

**工作区残留（T4 半成品，故意未提交）**——交接时**不要** `git clean`/`git checkout` 丢弃：

- `M web/tests/e2e/extensions-settings.spec.ts`：夹具提取后的 import 改动（纯搬移）。
- `?? web/tests/e2e/fixtures/extensions.ts`：从该 spec 提取的 `extensionSummary` / `installExtensions` / `ExtensionsState`。
- `?? web/tests/e2e/settings-extensions-production-evidence.spec.ts`：T4 的证据 spec，**5 个用例已按 Ruling 1 全部写出**（`g8-ext-01…05`）。

已做的安全性核验（交接时实测）：夹具提取后 `extensions-settings.spec.ts` **10 passed**（与提取前一致）；证据 spec 单独跑 `-g "g8-ext-01"` **1 passed**。尚未做：跑完整证据 spec 产出 5 张图、复制进 `docs/`、逐张比对、文档更新、提交。

## 4. 下次接手的确切步骤（T4 剩余）

1. 跑 `cd web && npx playwright test tests/e2e/settings-extensions-production-evidence.spec.ts --reporter=line --retries=0`（应产出 5 张 `g8-ext-*.png` 到 `web/test-results/`）。
2. 复制进版本库：`docs/dst-manager/specs/assets/SPEC-DM-011/production/`（PowerShell 见计划 Task 4 Step 3）。
3. 逐张与冻结件比对并分类（缺陷（须修）/ 有意偏差（须记））：`g8-ext-01↔g4-07`、`g8-ext-02↔g4-08`、`g8-ext-03↔g4-10`、`g8-ext-04↔g4-11`；`g8-ext-05`（900×600）**无冻结对照**，仅供 SPEC §3.2 视口维度证据，文档里要单独说明。
4. 更新 `SPEC-DM-011` §8（G8 行：覆盖 SC-15/SC-16 的新结论 + 证据路径 + 偏差裁决；注意原 G8 只覆盖 SC-01～SC-14）、§9（各条打勾）、§7（`production/` 说明）；`changelog.md` 追加一条，数字必须真实。
5. 提交（建议 `git add` 上述 spec/夹具/图片/文档/changelog）。
6. 最终全分支评审（SDD 要求用本会话可用的最高档模型，见第 6 节）+ 一次性修复波 + 一次 scoped 复评。
7. 收尾：`superpowers:finishing-a-development-branch`；把 PLAN-DM-022 的 `status` 从 `proposed` 改为实际状态，并按需更新 `.planning/plans/dst-manager/README.md` 的摘要。

## 5. 改代码前必读的契约（本次执行沉淀）

- **`BooleanSwitch.vue`**（`web/src/components/settings/`）：设置中心唯一开关原语。props `{checked, disabled?, label, dataKey?, inputId?}`，emits `change:[boolean]`；根元素 `button.switch[role="switch"]`；**不渲染可见状态文字**（冻结件里扩展卡片文字在左、常规配置 bool 字段文字在右，故文字由调用方布局）。
- **`.switch` 类名归属**：属于 `BooleanSwitch` 的按钮；`SettingsDialog.focusExtensionSwitch` 依赖在 `[data-extension-id]` 行内 `querySelector(".switch")` 定位开关。表单行原来的 `<span class="switch">` 已改名为 `.bool-line`。
- **`.ext-state` 类名归属**：扩展卡片左侧的可见状态文字（`aria-hidden`），被冻结件与 `extensions-settings.spec.ts` 的 4 处断言使用，**不得改名**。
- **`ExtensionCard.vue`**：props `{extension, busy}`，emits `toggle:[id, enabled]`；根元素 `li.ext-card[data-extension-id]`；四层信息＝名称 / 描述（`description_key`）/ `.ext-meta` 内「版本徽标 + 状态徽标 + 诊断码」/ `.ext-state` + 开关；**卡片不可点击、不导航**，卡内唯一可聚焦元素是开关。
- **`ExtensionsSection.vue`**：`GROUP_THRESHOLD = 6`，≥6 条按 **`enabled`**（不是 `status`）分「已启用/已停用」，空段不渲染；分组标题复用语言包既有 `settings.extensions.stateOn/stateOff`（未新增同义键）。
- **开关方向只取服务端 `enabled`**；「已启用 + 启动失败」是合法组合，必须能同时呈现（`FAILED`/`INCOMPATIBLE` 属"天然不可用"，与用户意图在 `extension_states` 上可区分）。
- **`SettingsDialog.vue` 已 535 行**（越过 500 行软上限，待办 `.planning/todos/dst-manager/2026-09-10-settings-dialog-file-split.md`）：本计划不允许它增长，卡片与开关都落在新组件里。
- **不新增全局 CSS 规则**（`web/src/style.css` 未改）；样式只在组件 `<style scoped>` 内，只用 SPEC-DM-006 令牌。
- **e2e 纪律**：`/api/extensions` 必须 mock（真实后端会写用户数据库的 `extension_states`）；除 `settings-dialog.spec.ts` 外任何 e2e 文件不得保存设置（该文件串行共享同一配置文件）。

## 6. 基础设施坑（下次派子代理前先读）

- **模型可用性**：`opencode/*` 返回 `CreditsError: Insufficient balance`（opencode.ai 余额为 0）；`deepseek/*` 返回 API key 无效；**本环境可用的是 `opencode-go/*` 网关**。本次用：实现者 `opencode-go/deepseek-v4-pro`、任务评审者 `opencode-go/glm-5.3`；最终评审计划用 `opencode-go/qwen3.8-max`。
- **`reviewer` agent 用不了**：它只有读取类工具，harness 会把评审任务判成"实现任务"并拒绝启动（连试两次、改中文措辞无效）。改用新鲜上下文的 `delegate` agent（有 bash 但不许写）并在提示词里强制只读；评审质量本次可接受。
- 本次子代理总开销约 $1.55（7 个子代理），父会话约 $0.41。

## 7. 控制器替用户做的裁定（Rulings，含错了的代价）

1. **Ruling 1**：计划 T4 的「其余三例同构」视为计划缺陷，实施者必须写出全部 4（后为 5）个截图用例，不得用注释代替代码。代价：多写约 40 行测试。
2. **Ruling 2**：`BooleanSwitch` **不渲染**可见状态文字，文字由调用方布局（冻结件里两处文字位置相反）。代价：日后若要内置文字，需重改两个调用点与两条断言。
3. **Ruling 3**：全部子代理改用 `opencode-go/*` 模型（因计费与密钥限制），不降级为会话默认 flash 档。代价：若日后充值/换密钥，仅影响档位选择。
4. **Ruling 3b**：评审者角色改用 `delegate` agent（`reviewer` 被 harness 拒绝）。代价：评审者的工具面比专用 reviewer 宽，靠提示词约束只读。
5. **Ruling 4**：卡片的可见状态文字类名沿用既有 `.ext-state`（计划原写 `.switch-state`）——既有 3 处断言与冻结件都用 `.ext-state`。代价：若日后想让卡片与表单行共用一个类名，需另开重构。
6. **Ruling 5**：T4 产出 **5 张**截图而非 4 张——计划里的「深色 900×600」在冻结件中没有对照图，故前 4 张严格对齐冻结件（1280×720），第 5 张（900×600）作为额外视口证据并单独说明。代价：多写一个用例。
7. **范围裁定（T2）**：T2 改动了 4 处既有合并断言（`v0.1.0 · 状态` 拆成版本/状态两条），超出计划明文授权；经评审独立核查语义覆盖未削弱，且属冻结件卡片布局的必然结果——**接受该偏离，不回退**。代价：若日后认为不该动既有断言，需回退这 4 处。

## 8. 未决项与欠债

- **deferred minors（供最终评审 triage，均未修）**：
  1. `SettingsFormRow.vue` 脚本区头部注释未同步说明 bool 字段的 `data-key`/`id` 现位于按钮而非 `input`。
  2. `BooleanSwitch` 的点击翻转基于同步受控 prop，快速连点有理论丢翻转风险（当前无实际风险）。
  3. 重试用例里版本徽标校验随合并断言拆分丢失（版本与状态同一模板路径，风险极低）。
  4. `extensions-settings.spec.ts:156/258` 的选择器写法与前文 `card` 变量不一致（纯风格）。
- **G8 结论待定**：T4 完成后才能给出生产 vs 冻结件的逐张比对结论；原 G8 记录只覆盖 SC-01～SC-14（扩展分区与卡片基线从未做过 G8）。
- **PLAN-DM-022 的 `status` 仍是 `proposed`**，完成后需按实际改写。
- **`.planning/plans/dst-manager/README.md` 里 PLAN-DM-021 的摘要可能过期**：它写着"全量 e2e 有批次三遗留回归待修复"，但本次会话两次全量 e2e 均为 0 failed。未核实、未改动。
- `SPEC-DM-011` 的 `production/` 目录（G8 生产截图）仍不存在——本次 T4 才会建立。
- 与本次任务无关的既有残留：`.claude/worktrees/plan-dm-020-sheet-catalog/` 是遗留的未跟踪工作树目录，其内部旧文件仍带 `SPEC-DM-015` 引用；未处理。

## 9. 已跑过的验证（真实数字）

- T1：`settings-dialog` 18 passed、`extensions-settings` 7 passed、`check:i18n` 867 键、`vue-tsc` 通过；控制器独立复跑 = **25 passed**。
- T2：`extensions-settings` 8 passed、`settings-dialog` 18 passed、`check:i18n` 868 键（+`diagnosticCode`）、`vue-tsc` 通过；控制器独立复跑 = **26 passed**。
- T3：`extensions-settings` 10 passed、`sheet-catalog` + `extensions-navigation` 39 passed、`check:i18n` 868、`vue-tsc` 通过；控制器独立复跑 = **49 passed**。
- 交接前实测：夹具提取后 `extensions-settings` 10 passed；证据 spec `-g "g8-ext-01"` 1 passed。
- 基线阶段（上半程）：`ruff check` 全绿、`pytest -o addopts="" -q` 1112 passed / 72 skipped、`check:i18n` 867 键、`npm run build` 通过、新证据 spec 13 passed、全量 e2e 连跑两次 0 failed（402 项：400/2 flaky、401/1 flaky，flaky 均为既有环境抖动）。
- **尚未跑**：T1–T3 合并后的全量 e2e（4 workers）、`npm run build`、`pytest` 全量——按 SDD 流程这一步属于"最终全分支评审前"的整体验证，建议下次在 T4 提交后执行。

## 10. 相关文件清单

- 计划：`.planning/plans/dst-manager/PLAN-DM-022-extension-card-baseline.md`
- 台账：`.superpowers/sdd/PLAN-DM-022-extension-card-baseline/progress.md`（git-ignored；另有 `task-1..4-brief.md`、`task-1..3-report.md`、`review-*.diff`）
- 任务报告：`task-1-report.md`、`task-2-report.md`、`task-3-report.md`（T4 未产出）
- 生产实现：`web/src/components/settings/BooleanSwitch.vue`、`ExtensionCard.vue`、`ExtensionsSection.vue`、`SettingsFormRow.vue`
- 测试：`web/tests/e2e/settings-dialog.spec.ts`、`extensions-settings.spec.ts`、`fixtures/extensions.ts`、`settings-demo-visual-evidence.spec.ts`、`settings-extensions-production-evidence.spec.ts`
- 文档与证据：`docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md`、`SPEC-DM-006-...md`、`docs/dst-manager/specs/assets/SPEC-DM-011/`（g4-01…g4-12）、`docs/dst-manager/mockups/SPEC-DM-011-settings-demo.html`
