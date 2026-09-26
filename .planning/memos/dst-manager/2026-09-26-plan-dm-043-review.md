---
id: MEMO-DM-042
title: PLAN-DM-043 表格对齐契约前端收口整支复核记录
status: final
owners:
  - dst-manager
created: 2026-09-26
updated: 2026-09-26
related:
  - PLAN-DM-043
  - SPEC-DM-006
  - ARCH-DM-007
---

# PLAN-DM-043 整支复核记录（2026-09-26）

- **范围**：分支 `feature/plan-dm-043-table-alignment`，`010554d..19a652e`（6 个提交，含 5 个 Task 提交与 1 个计划文档提交）。
- **评审方式**：按 `superpowers:executing-plans` 的最终评审环节派发独立评审代理（只读、`reviewer` 代理，模型为本会话配置内的 `opencode-go/deepseek-v4.1-flash`；更高档模型被 `modelScope` 限制）。评审包：`.superpowers/sdd/PLAN-DM-043-table-alignment-frontend-remediation/review-010554d..19a652e.diff`。
- **评审输入**：计划全文（含接口与 Review Focus）、SPEC-DM-006 §5.3/§6.4、ARCH-DM-007 §4.1/§4.3/§7/§9、账本中的全部 Ruling 行、归档的 RED/GREEN 日志。
- **结论**：**0 Critical、1 Important、5 Minor**，`Ready to merge? With fixes`。

## 一、Important（已修复）

**I1：`ARCH-DM-007` §4.3 与 `SPEC-DM-006` §6.4 的 padding 存量口径与本分支实现及新门禁互相矛盾。** 两处正文仍写"现有 `10px 8px`、`9px`（legacy 兜底）、`4px` 三档为迁移期存量，按 §7 收口"，而本分支已删除 legacy `9px` 档与 `:where(#app) th,td` 兜底规则、把 `10px 8px` 改为 `var(--space-2)`，且新门禁 `table-cell-padding` 会直接拒绝裸 `9px`/`10px 8px`——规范正文当时"授权"了一个门禁拒绝的值。属计划漏掉的文档同步步骤。

**处置（同一修复轮）**：`ARCH-DM-007` §4.3 与 `SPEC-DM-006` §6.4 各补一句"PLAN-DM-043 已完成这轮收口：现役只保留 `--space-2`（8px）与 `--space-1`（4px）两档，`10px 8px` 与 legacy `9px` 档连同 legacy `:where(#app) th,td` 兜底规则已删除，上文三档存量只作历史记录"；`SPEC-DM-006` §1.1 追加 2026-09-26（表格对齐契约前端收口）修订记录。验证：`check:ui` exit 0、`check:i18n` 1622 键对称、`test:contracts` 114/114。

## 二、Minor（决定不修，登记备查）

| 编号 | 内容 | 处置 |
| --- | --- | --- |
| M1 | `table-cells.mjs` 判定边界空洞：`td` 挂类名后的 `.cell{padding:12px}`、`:deep(td)`/`:is(td)`、`tr>*.cell` 可绕过；“同表两档”只比较 `padding` 简写（长手 `padding-top` 与 `padding: var(--space-2) 0` 混合值静默通过）；`@media` 内的同选择器会被判成两档 | 已登记为待办：[新表守卫与单元格门禁判定边界](../../todos/dst-manager/2026-09-26-new-table-guard-and-cell-gate-boundary.md)（含实测探针证据） |
| M2 | 建议新增“含 `<table>` 但无任何 `th/td` 声明即违规”规则（可复用 `findTags`），补 legacy 删除后的默认渲染盲区 | 同上待办（与 M1 合并为同一项守卫规则） |
| M3 | 作业表与预览表只有“≥44px 下限”锚，未钉绝对值 44px | 已在计划 Task 5 证据与账本写明理由（8/6 列在 390px 浮层内必然换行）；44px 值仍由修订表与 Task 4 三张表钉住 |
| M4 | 计划 Task 2/Task 3 行登记的 RED 计数与归档日志不一致（应为每份 spec 2 failed） | 计划正文已按归档订正 |
| M5 | `PreviewPanel` 未按 Task 5 Step 2 "8 张表按列给类名"全部落实（只加了数值列 `count-cell`） | 结果正确（其余列均为标识型文本，左对齐即符合 §6.4），已在计划 Task 5 证据中登记该偏差 |
| M6 | Review Focus #2/#3 的“收起后回到 44px”“内容与操作列不相交”只有间接断言（现有覆盖：四视口批量区不出视口、表窗自身横滚、展开前 44px 与结构行零 padding） | 已并入同一待办的第 5 项：[新表守卫与单元格门禁判定边界](../../todos/dst-manager/2026-09-26-new-table-guard-and-cell-gate-boundary.md) |

## 三、评审"Declined to judge"各项的执行者裁决

1. **首个提交用 `docs:` 前缀**：保留。仓库既有历史同样使用 `docs:`/`fix:` 前缀（`010554d`、`bd1a5b9`），描述为简体中文动词短语；若合并时统一改写为无前缀形式，代价仅为一次 reword。
2. **8px 与 4px 两档并存**：保留。SPEC-DM-006 §6.4 只要求"同一张表同档"，并存两档不违约；若将来统一，代价为一次纯 CSS 改动。
3. **`--sheet-table-row-height` 跨 7 个组件借用**：保留（用户已确认方案 A，计划内已登记语义借用风险与兜底）。
4. **未在三个旧组件重声明 `width:100%`/`border-collapse:collapse`**：保留。legacy 的 `:where(#app) table` 规则仍有全部表格作为消费者，本计划只删除 `th,td` 兜底条；若将来删除该 `table` 规则，需同步在这三处补声明。
5. **耗时列输出裸整数（无千分位）**：保留。SPEC 要求"同列小数位/千分位一致"，同列一致即满足；改数值格式超出"不改底层数值"的计划边界。
6. **"所有 `th/td` 规则必须显式声明 `vertical-align`"的字面口径（14 处冗余声明）**：保留。ARCH §4.3 与 SPEC §6.4 字面支持该口径，评审也确认成立；若后续放宽为"仅装箱属性类规则"，代价为删除这 14 行。
7. **真实 Windows WebView2 100/125/150/200% 复验缺口**：保留。按 ARCH-DM-007 §12，计划保持 `active`，缺口挂在计划上待用户执行。

## 四、评审未发现问题的部分（摘录）

- 消费方普查完整：全仓 `<table>` 恰好 18 处、11 个组件，删除 legacy `th,td` 后每张表的 `padding`/`border-bottom`/`text-align`/`height`/`vertical-align` 均由组件自持；保留的 `table` 与 `td input` 规则仍有真实消费者。
- 结构配对机制（精确"文件 + 选择器" + 跨组件核对内层令牌）实现正确，且 `colspan` 不构成豁免（有 CLI 级变异证据）。
- RED 可信且留痕（每个 Task 的失败数值与原因均与归档日志一致）；GREEN 与门禁数值（697 passed、114/114、340/340、`check:ui` exit 0）与归档日志一致。
- 例外棘轮卫生：`ui-contract-exceptions.json` 只剩 10 条 PLAN-DM-029 存量 + 1 条动态变量，无本计划到期项、无过期条目。
- i18n 对称与死键清理正确（`durationMs` 全仓零命中）。
