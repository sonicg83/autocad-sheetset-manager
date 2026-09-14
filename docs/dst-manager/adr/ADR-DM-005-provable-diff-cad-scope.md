---
id: ADR-DM-005
title: CAD 工作范围按可证明差异收敛
status: accepted
document_kind: adr
created: 2026-09-14
updated: 2026-09-14
related:
  - ARCH-DM-001
  - ADR-DM-003
  - SPEC-DM-003
  - SPEC-DM-014
  - PLAN-DM-008
  - PLAN-DM-027
  - PLAN-DM-028
  - PLAN-DM-030
---

# CAD 工作范围按可证明差异收敛

## 背景

[ADR-DM-003](ADR-DM-003-deferred-cad-validation-and-subset-cad-operations.md) 在把子集操作分流为 `none`、`rename_only`、`rebuild` 时，给了「数量变化前沿」一个**工作范围**职责：前沿及其后的所有最终子集都必须进入 CAD 工作范围，理由是「全局图号和布局名称可能顺移」。这在当时是保守上界——前沿之后能否免于 CAD 取决于逐子集证明，而逐子集证明恰好是同一决策要引入的能力。

`rename_only` 落地后，逐子集证明已经完整：`DerivedDocument` 与原始结构逐张比较稳定图纸 ID、顺序、内容来源、图号、图名、布局名、目标 DWG 路径与子集显示名（`_subset_changed`）。**「图号或布局名可能顺移」这一全部理由都被该判定覆盖**——真顺移时派生结果与现状必然存在可证明差异，判定必然为真。于是「位于前沿之后」只在派生结果与现状**完全一致**时才额外生效，其唯一效果是给未变化的子集启动一次 Core Console 做无效改名（每单元约 10–45 s），并让用户看到一批并不成立的「改名」工作。

[SPEC-DM-014](../specs/SPEC-DM-014-unnumbered-subset-keywords.md) 已把该现象记为「已知代价」（不编号子集之后的子集在结构调整时可能因基准确认边界进入 `rename_only`），[PLAN-DM-028](../../../.planning/plans/dst-manager/PLAN-DM-028-runtime-settings-live-consumption.md) 的「后续项」也登记为待优化，本次关闭该遗留项。

## 决策

### 工作单元只由可证明差异决定

`planning.py` 的 CAD 操作判定改为：

```
cad_operation = "none"  if 原始与派生结构在可证明范围内完全一致
                "rebuild"    if 数量、图纸集合、顺序、内容来源变化，或 Handle 不满足唯一非零要求
                "rename_only" if 仅派生名称/图号/路径变化，且 Handle 资格成立
```

实现上即 `_cad_operation` 只依据自身差异与 Handle 资格返回 `rename_only` 或 `none`，**不再接收**「是否位于数量变化前沿之后」这一输入。`none` 一律不生成 CAD 工作单元。

### 前沿保留为信息，不再决定工作范围

`cardinality_frontier` 与逐子集的 `in_cardinality_scope` 继续按原规则计算并出现在计划、HTTP 响应与 Web 预览中，语义收窄为**「结构顺序可能受影响的范围（上界）」**：

- 它是诊断与展示信息，供用户理解「从这里开始序号/布局名可能整体移动」；
- 它不再是操作分流的输入，`in_cardinality_scope == true` 与 `cad_operation == "none"` 是**合法且常见**的组合；
- 对外契约（字段名、类型、`CardinalityFrontierResponse`）不变，前端无需改动即可继续展示。

### 安全边界不变

本 ADR 只收窄工作范围，不放松任何安全要求：

- 数量、图纸集合、顺序、内容来源变化，或 Handle 缺失/重复/非法/为零时，仍必须 `rebuild`；无法证明安全时不得选择 `rename_only`；
- `rename_only` 仍由受限 `DstRenameLayouts` 执行，仍不删除/导入布局、不获取 Handle、不重写既有 `AcDbHandle`；
- 快速预览仍不启动 CAD，确认后仍是一单元一次 Core Console、共用全局并发预算；
- 仍保持永久 before 快照、来源基准复核、DST DOM 受控写入、整批发布与可回滚事务。

## 后果

- 向图纸集插入**不编号子集**（图号恒为 `000`、不消耗序号）或在其中增删图纸时，其他子集的图号与布局名事实上未变，不再为它们启动 Core Console。
- 不编号子集内插图纸、编号子集内插图纸等混合场景下，只有可证明发生变化的子集进入 CAD 工作范围，任务耗时与暂存 DWG 数量同时下降。
- 计划与预览中会出现「处于前沿范围但无需 CAD 操作」的行。前端已有的「操作」列（`无需 CAD 操作`/`批量改名布局`/`清除并重建布局`）如实表达真实执行范围，「数量前沿范围」列表达上界；二者组合即可读出「可能受影响」与「实际要动」的区别，因此本轮不修改前端契约与文案。
- [ADR-DM-003](ADR-DM-003-deferred-cad-validation-and-subset-cad-operations.md) 中「数量变化前沿及其后的所有最终子集都必须进入 CAD 工作范围」被本 ADR 替代；其「快速预览不启动 AutoCAD」「一个 CAD 工作单元只启动一次 Core Console」「`rename_only` 由受限插件命令执行」「事务边界不变」四项决策，以及 `none`/`rename_only`/`rebuild` 三分类本身，继续有效。

## 未采纳方案

- **仅豁免不编号子集**：改动更小，但把「是否浪费」绑在关键字配置上——编号子集内部插图纸同样会让其后的未变化子集进入 `rename_only`（实测复现），浪费仍在，只是换了个触发条件。
- **把「仅子集显示名变化」也归为 `none`**：不成立。子集标题变化会经 `derive_group_titles` 传播到该子集每张图纸的标题与布局名，属真实 CAD 工作。
- **保留原决策但只在前端隐藏**：不减少进程启动，只是把浪费藏起来。
- **彻底删除前沿字段**：前沿仍是理解「序号整体移动」的有效信息，且删除会破坏既有 HTTP 契约与前端渲染，收益为零。

## 实施状态

本 ADR 由 [PLAN-DM-030](../../../.planning/plans/dst-manager/PLAN-DM-030-provable-diff-cad-scope.md) 实施，2026-09-14 完成：

- 失败测试先于实现（TDD RED）：`tests/unit/test_core.py` 新增「插入不编号子集不得为未变化子集生成工作单元」（2 个插入位置）、「编号子集内插图纸时未变化的不编号子集保持 `none`」、「不编号子集内插图纸时其后未变化的编号子集保持 `none`」；并把原有的前沿传播测试改为同时断言 `groups == []` 与 `deleted_subsets`。全部 5 项在修复前失败（实际得到 `rename_only`），修复后转绿。
- 连续运行稳态复现：在不编号子集内连续加图纸，第二轮 `subset-2` 为 `none` 且 `in_cardinality_scope` 仍为 `true`，`groups` 只含真正变化的不编号子集——修复前该子集会被强制 `rename_only`。

接口与行为要求见 [SPEC-DM-003](../specs/SPEC-DM-003-deferred-cad-validation-and-subset-cad-operations.md)（§3.1/§9）与 [SPEC-DM-014](../specs/SPEC-DM-014-unnumbered-subset-keywords.md)（「已知代价」项已关闭）。
