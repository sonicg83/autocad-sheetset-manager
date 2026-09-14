---
id: PLAN-DM-030
title: 数量变化前沿不再强制 CAD 工作范围修复计划
status: completed
owners:
  - dst-manager
created: 2026-09-14
updated: 2026-09-14
related:
  - ADR-DM-003
  - ADR-DM-005
  - SPEC-DM-003
  - SPEC-DM-014
  - PLAN-DM-008
  - PLAN-DM-027
  - PLAN-DM-028
---

# 数量变化前沿不再强制 CAD 工作范围修复计划

> **来源：** 用户缺陷报告（2026-09-14）：向图纸集**插入不编号子集**（图号固定 `000`、不消耗序号）时，其他子集的图号与布局名实际没有任何变化，但系统仍为它们生成 `rename_only` CAD 工作单元，每个都多启动一次 AutoCAD Core Console（10–45 s），属纯浪费。
> **定位：** 不是不编号关键字的领域规则错误（[SPEC-DM-014](../../../docs/dst-manager/specs/SPEC-DM-014-unnumbered-subset-keywords.md) 的派生结果正确），而是 [ADR-DM-003](../../../docs/dst-manager/adr/ADR-DM-003-deferred-cad-validation-and-subset-cad-operations.md) 中「数量变化前沿及其后所有最终子集必须进入 CAD 工作范围」这一保守上界在逐子集证明能力完备后不再必要。

**Goal:** CAD 工作单元只由**可证明差异**决定；数量变化前沿保留为展示信息，不再扩大 CAD 工作范围。

**Architecture:** 单点修改 `src/dst_manager/domain/planning.py`：

- `_cad_operation` 去掉 `in_frontier_scope` 入参，末行判定由 `return "rename_only" if changed or in_frontier_scope else "none"` 改为 `return "rename_only" if changed else "none"`；
- 调用点停止传入 `in_frontier_scope=in_cardinality_scope`，但**保留** `in_cardinality_scope` 的计算与输出（HTTP 契约、计划摘要、Web 预览均不变）。

**Tech Stack:** Python 3.12 + uv + pytest；无前端、无 SCR/插件、无 DST 落盘改动。

**Spec:** [SPEC-DM-003](../../../docs/dst-manager/specs/SPEC-DM-003-deferred-cad-validation-and-subset-cad-operations.md)（§3.1 工作范围口径、§9 验收）；决策变更与理由见新增 [ADR-DM-005](../../../docs/dst-manager/adr/ADR-DM-005-provable-diff-cad-scope.md)；用户可见效果见 [SPEC-DM-014](../../../docs/dst-manager/specs/SPEC-DM-014-unnumbered-subset-keywords.md)（「已知代价」项关闭）。

## Global Constraints

- 全程简体中文注释、文档、commit message；标识符与 API 字段保持英文。
- 不改 HTTP 契约：`cardinality_frontier`、`in_cardinality_scope`、`CardinalityFrontierResponse`、计划摘要字段全部保留原语义与类型。
- 不改安全边界：数量/集合/顺序/来源变化或 Handle 资格不成立时仍必须 `rebuild`；`rename_only` 仍走受限 `DstRenameLayouts`，不重写既有 `AcDbHandle`；预览仍不启动 CAD，发布仍走永久快照与整批回滚。
- 不引入关键字依赖：修复不针对不编号子集做特例，编号子集内部变化同样只让真正变化的子集进入工作范围。

## 缺陷机理（根因）

1. `planning.py` 第 96 行用 `_cardinality_frontier(workspace.document.subsets, derived.subsets)` 求首个图纸数量变化的最终子集下标，第 137 行得到每个子集的 `in_cardinality_scope`。
2. `_cad_operation(..., in_frontier_scope=in_cardinality_scope)` 使「前沿之后」成为 CAD 操作分流的输入。
3. `_subset_changed` 已经逐张比较稳定图纸 ID、顺序、内容来源、图号、图名、布局名、目标 DWG 路径与子集显示名——「图号/布局名可能顺移」这一唯一理由已被完整覆盖；因此 `in_frontier_scope` 只在派生结果与现状**完全一致**时额外生效，效果是对未变化子集做一次无效改名。
4. 插入**不编号子集**是命中该路径的最典型场景：它改变图纸数量（前沿成立），但按 SPEC-DM-014 §行为 5 不消耗序号，其后子集图号不变 → 无差异却被迫 `rename_only`。

## Tasks

### Task 1: 失败测试（TDD RED）

- [x] **Step 1**：改写 `tests/unit/test_core.py::test_cardinality_frontier_propagates_after_subset_deletion`——把参数化的 `expected_groups` 改为 `expected_operations`，删除后仅存续但未变化的子集断言为 `none`，并新增 `plan["groups"] == []` 与 `deleted_subsets` 断言。
- [x] **Step 2**：新增 `test_inserted_unnumbered_subset_adds_no_cad_work_for_unchanged_subsets`（`position` 参数化 `[0, 1]`）：断言 `cardinality_frontier` 照常上报、新子集 `rebuild`、既有子集 `none`、`groups` 只含新子集。
- [x] **Step 3**：新增 `test_numbered_subset_change_skips_unchanged_unnumbered_subset`：编号子集内插图纸 → 未变化的不编号子集 `none`，其后编号子集真实顺移为 `rename_only` 且改名对照旧值可见。
- [x] **Step 4**：新增 `test_change_inside_unnumbered_subset_skips_unchanged_numbered_subset`：不编号子集内插图纸 → 其后未变化的编号子集 `none`。
- [x] **Step 5**：运行确认失败：5 failed / 1 passed，失败点均为实际得到 `rename_only`。失败证据以 `git stash` 方式在修复前后各跑一次（见「实际验证」）。

### Task 2: 实现（TDD GREEN）

- [x] **Step 1**：`_cad_operation` 删除 `in_frontier_scope` 参数，末行改为 `return "rename_only" if changed else "none"`，docstring 引用 ADR-DM-005 说明「前沿只作展示」。
- [x] **Step 2**：调用点停止传入 `in_frontier_scope`，保留 `in_cardinality_scope` 计算并加注释说明原因；计划输出字段不变。
- [x] **Step 3**：运行 Task 1 的 6 项定向用例转绿。

### Task 3: 稳态复现（真实场景验证）

- [x] **Step 1**：临时脚本按「第一轮派生结果 = 第二轮现状」模拟应用发布后的稳态（DST 图号/标题/布局名与 DWG 文件名、Handle 均与派生规则一致）。
- [x] **Step 2**：连续两轮在不编号子集内加图纸：修复前后续子集被强制 `rename_only` 且改名对照为空；修复后为 `none`，`in_cardinality_scope` 仍为 `true`，`groups` 只含真正变化的不编号子集。
- [x] **Step 3**：清理临时脚本与临时目录。

### Task 4: 文档与变更记录

- [x] **Step 1**：新增 [ADR-DM-005](../../../docs/dst-manager/adr/ADR-DM-005-provable-diff-cad-scope.md)，并在 ADR-DM-003 决策处追加「2026-09-14 部分替代」注记（不静默改写旧决策）。
- [x] **Step 2**：修订 SPEC-DM-003 §2.1/§3.1/§3.2/§9/§10 与 SPEC-DM-014「已知代价」；ARCH-DM-001 §6.3 与 v0.21 替代说明同步。
- [x] **Step 3**：本计划落盘；`docs/dst-manager/README.md` 与 `.planning/plans/dst-manager/README.md` 增索引行；PLAN-DM-028「后续项」追加关闭追记。
- [x] **Step 4**：根 `changelog.md` 追加修复条目（症状、根因、改动点、验证、遗留）。

## 实际验证

| 项 | 命令 | 结果 |
| --- | --- | --- |
| RED 证据（修复前） | 把 `planning.py` 的改动存为补丁后 `git checkout -- src/dst_manager/domain/planning.py`，再跑 `uv run pytest tests/unit/test_core.py -k "unnumbered_subset_adds_no_cad_work or skips_unchanged_unnumbered or change_inside_unnumbered or frontier_propagates" -q`，随后 `git apply` 恢复 | 修复前：**5 failed / 1 passed**（`test_cardinality_frontier_propagates_after_subset_deletion[subset-2]`、`test_inserted_unnumbered_subset_adds_no_cad_work_for_unchanged_subsets[0/1]`、`test_numbered_subset_change_skips_unchanged_unnumbered_subset`、`test_change_inside_unnumbered_subset_skips_unchanged_numbered_subset`），失败点均为实际得到 `rename_only` |
| 定向用例（修复后） | `uv run pytest tests/unit/test_core.py -k "unnumbered_subset_adds_no_cad_work or skips_unchanged_unnumbered or change_inside_unnumbered or frontier_propagates" -q` | **6 passed**（EXIT=0） |
| 全量回归 | `uv run pytest -q -p no:warnings --junitxml=.tmp-res.xml` | **1476 项：1404 passed / 72 skipped / 0 failed / 0 errors**（91.2 s；修复前 1472 项 = 1400 passed / 72 skipped，本次 +4 用例） |
| 静态检查 | `uv run ruff check .` | All checks passed!（EXIT=0，含删除临时脚本后复跑） |
| 稳态场景复现 | 临时脚本（连续两轮在不编号子集内加图纸，第一轮结果作为第二轮现状） | 修复前：`subset-2` = `rename_only` 而改名对照 `[]`；修复后：`subset-2` = `none`，`in_cardinality_scope` = `true`，`groups` 只含 `subset-u` |
| 编号子集内插图纸（对照场景） | 同上脚本的编号子集分支 | 修复后下游真实顺移仍为 `rename_only`（改名对照 `[("002 平面图", "003 平面图")]`），未被误降级为 `none` |
| 真实 CAD 系统测试 | `DST_MANAGER_RUN_AUTOCAD=1 uv run pytest tests/system_autocad -q` | 未执行（改动只在计划分流，不涉及 SCR、插件命令、布局重建与 Handle 回读；`rename_only` 的 CAD 行为未变） |
| 前端 | 未改动 | HTTP 契约与 `cardinality_frontier`/`in_cardinality_scope` 字段不变，既有 e2e 断言（`数量变化前沿：第 2/3 个子集`、操作列文案）仍成立，未重跑 Playwright |

## 门禁分级与证据缺口（如实记录）

参考 [GUIDE-DM-001](../../../docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md)：本修复**无前端渲染层改动**（无新增控件、无视觉变化、无 i18n 键变化），按 S 级口径执行最小充分门禁：

- 已执行：G0（全量 pytest 1476 项）、G1（Ruff 通过），以及针对本缺陷的稳态复现脚本。
- 未重开：G3/G4（无新视觉设计）、G5～G8（前端零改动，无新截图需求）、G9（真实桌面验收）。
- **遗留（用户可裁决）**：「子集 CAD 操作」表中的「数量前沿范围」列现在会出现「是 + 无需 CAD 操作」的组合。该组合语义正确（前沿是上界、操作列是实际执行），与 ADR-DM-003「Web 必须显式暴露三类操作」的要求一致，故本轮不改前端文案。若用户希望把该列文案改为「可能受影响」或在同列显示操作结论，属独立的前端文案变更，需重跑 `npm run build` 与 Playwright 门禁，另行立项。
- **G9 待办**：打包 EXE 重建后在真实桌面确认「插入不编号子集 → 其他子集不出现在实施进度的工作单元中，总耗时明显下降」。

## 后续项

- 若后续新增「扩大 CAD 工作范围」的上界规则（例如引入强制重建开关），必须新增 ADR 说明其与「可证明差异」原则的关系，不得直接恢复「前沿之后一律进入工作范围」。
- `rename_only` 与 `rebuild` 的真实 CAD 行为、Handle 保留与插件协议由 PLAN-DM-008 的系统矩阵覆盖，本次未改动该路径。
