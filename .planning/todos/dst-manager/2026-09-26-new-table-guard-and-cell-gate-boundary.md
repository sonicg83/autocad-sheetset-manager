# 新表守卫与表格单元格门禁判定边界

日期：2026-09-26

状态：待办（未立项；来源 PLAN-DM-043 整支复核 M1 + M2）

关联：`PLAN-DM-043`、`MEMO-DM-042`、`SPEC-DM-006`、`ARCH-DM-007`

## 背景

PLAN-DM-043 已为 `check:ui` 新增 `table-cell-vertical-align` 与 `table-cell-padding` 两条静态规则，并把 11 个含表格组件、共 18 张表的单元格几何收口到明确档位；同时删除了 `legacy.css` 的 `:where(#app) th,:where(#app) td` 兜底规则（详见 MEMO-DM-042 与计划正文的 Task 1–5 执行记录）。

整支复核在确认无功能缺陷后，把两个互相关联的"未来回归入口"列为 Minor 延后项（M1、M2）。它们的共同特点是：**当前 18 张表都已被浏览器断言与全量 e2e 钉住，不会出错；只有新增表格或新增单元格规则时才会静默绕过门禁**。

## 实测证据（2026-09-26 用真实门禁探针，临时文件已删除）

- **探针 A（M1，class-only 绕过）**：组件内写 `th,td{height:var(--sheet-table-row-height);vertical-align:middle}` + `.cell{padding:12px}`（裸 padding 经类名作用在 `<td class="cell">` 上）→ `check:ui` **exit 0**。原因是 `cellTarget()` 要求选择器最后一个复合选择器**以 `th|td` 元素名开头**。同类绕过还包括 `:is(td)`/`:where(td)`/`:deep(td)`、`tr > *.cell`。
- **探针 B（M2，新表无规则）**：新建组件只含 `<table>`、没有任何 `th/td` 规则 → `check:ui` **exit 0**。删除 legacy 兜底之前这类表会继承 9px padding + 左对齐 + 分隔线，"看起来还行"；现在会落到浏览器默认（`th` 居中加粗、无分隔线、单元格 1px padding、基线对齐），与其余表格观感明显不一致。这是 PLAN-DM-043 引入的唯一新暴露面。
- **同类边界（尚无探针，评审 M1 一并列出）**："同表两档"只比较 `padding` 简写，故 `td.col{padding-top:var(--space-4)}`（长手、有令牌、非零）与 `padding:var(--space-2) 0`（令牌 + 字面零混合）静默通过；反向地，`@media(max-width:900px){th,td{padding:var(--space-1)}}` 会被误判为"同表两档"。

## 待处理（按建议顺序）

1. **新增"含 `<table>` 的组件必须声明 `th/td` 规则"的守卫规则**（规则名待定，如 `table-without-cell-contract`）。复用 `web/scripts/ui-contracts/vue-source.mjs` 的 `findTags` 检测模板里的 `<table>`；命中组件再检查其样式区是否存在单元格规则。先写 RED 夹具（有表格无规则 → 失败；有 `th,td` 规则 → 通过），再实现，并把新规则并入 `check-ui-contracts.test.mjs` 的 CLI 级变异清单（分类数、注入数、规则集合三处计数同步）。
2. **把"同表两档"的档位键从 `padding` 简写扩展到 padding 家族**：以该作用域下 padding 家族的规范化值签名为键，覆盖 `padding-top` 等长手与 `var(--space-2) 0` 混合值；同时把 `parseRules` 的 `atRules` 纳入作用域键，避免合法的响应式覆盖被误判成两档。
3. **在 `table-cells.mjs` 头注释登记"不覆盖的写法清单"**：class-only（`.cell` 作用在 `td`）、`:is`/`:where`/`:deep(td)`、padding 长手与混合值、`@media` 内同选择器。让边界成为文档而不是口口相传。
4. **（可选，成本较高需先评估）** 让判定从"选择器文本"升级为"选择器 + 模板结构"的最小关联：模板里存在 `<td class="cell">` 时，把 `.cell` 规则也纳入单元格判定。风险是同一类名可能同时用于非单元格元素而误报，建议先做 1–3，再按真实需求决定是否做此项。
5. **（可与本项合并实施）复核 Minor M3**：补 Review Focus #2/#3 的直接断言——`sheets-layout.spec.ts` 增加"收起编辑行后普通行回到 44px"与"内容盒与操作列不相交"。

## 边界与约束（实施时不要越界）

- 不得为省事放宽既有两条规则的严格度（例如把"所有 `th/td` 规则必须显式声明 `vertical-align`"改成"主规则声明即可"）——该字面口径有 ARCH-DM-007 §4.3 与 SPEC-DM-006 §6.4 正文支持，已在 PLAN-DM-043 中作为裁决登记。
- 新规则仍按 `ui-contract-exceptions.json` 的指纹棘轮登记例外；**实施前先用裸检查器确认存量命中数**。以当前树预期为 0 条（11 个含表格组件都已有 `th/td` 规则），若不为 0 需在计划里列明清退任务与到期条件。
- 判定只看"已声明的规则 + 模板事实"，不猜测最终计算几何；真实几何仍由 Playwright 断言负责。
- 不改动既有规则名、指纹语义与 CLI 输出格式，避免已清退的例外表失效。

## 成本与验收（建议）

- 成本估计：第 1 项约 20–40 行实现 + 3–5 条契约用例（含 1 条 CLI 级变异）；第 2 项取决于档位签名的实现方式，预计同量级；第 3 项为注释与文档，第 4 项需单独评估。
- 验收命令：`rtk npm --prefix web run test:contracts`、`rtk npm --prefix web run check:ui`、`rtk npm --prefix web run build`；并复跑两个探针（有表格无规则、class-only 裸 padding）确认二者都能使 `check:ui` 退出 1。
