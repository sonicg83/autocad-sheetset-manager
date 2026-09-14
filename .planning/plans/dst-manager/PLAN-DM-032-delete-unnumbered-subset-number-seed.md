---
id: PLAN-DM-032
title: 删除不编号子集导致后续子集重编号修复计划
status: completed
owners:
  - dst-manager
created: 2026-09-14
updated: 2026-09-14
related:
  - ADR-DM-005
  - SPEC-DM-014
  - SPEC-DM-003
  - PLAN-DM-027
  - PLAN-DM-030
---

# 删除不编号子集导致后续子集重编号修复计划

> **来源：** 用户在 PLAN-DM-030 交付验证中报告（2026-09-14）：原第一个子集为 `01 图纸目录`，插入「封面」后得到 `00 封面；01 图纸目录`（正确），**再删除封面**却得到 `00 图纸目录`——后续编号子集被重编为 0 起；且该子集还会按「改名」进入 CAD。另一形态：关键字刚开启、封面尚未应用 `0` 填充（仍为 `001`）时删除它，后续子集整体前移。
> **定位：** 与 [PLAN-DM-030](PLAN-DM-030-provable-diff-cad-scope.md)（CAD 工作范围）根因不同，本项是**编号派生**缺陷：`_number_seed` 的排除集合与它读取的文档快照不一致。

**Goal:** 不编号子集的**删除**与**新建**对称——不改变任何其他子集的图号、显示名、布局名与目标 DWG，因此也不产生任何 CAD 工作单元。

**Architecture:** 单点修改 `src/dst_manager/domain/editing.py::derive_document_structure`：

- 在不编号判定之后补一份「命令前文档」的判定（复用刚初始化的 `titles` 快照），与「命令后」判定取并集后传给 `_number_seed`；
- `_number_seed` 本体不变（它读命令前文档既有图号是既有规则，用于继承项目编号起点与位数）。

**Tech Stack:** Python 3.12 + uv + pytest；无前端、无 SCR、无 DST 落盘格式改动。

**Spec:** [SPEC-DM-014](../../../docs/dst-manager/specs/SPEC-DM-014-unnumbered-subset-keywords.md) §行为 3（序号种子与图号位数）、§行为 5（不消耗序号）；实施记录见 [PLAN-DM-027](PLAN-DM-027-unnumbered-subset-keywords.md)。

## Global Constraints

- 不改 HTTP 契约与前端：只影响派生出的图号/显示名，字段与文案不动。
- 不改「继承既有编号起点与位数」的既有规则：`_number_seed` 仍读命令前文档的图号，只是排除集合补齐为命令前 ∪ 命令后。
- 不改安全边界：本项不触碰 DST Codec、发布事务、SCR 与插件命令。
- 编号派生结果变化会经 `_subset_changed` 反映为 CAD 操作（图号真变则 `rename_only`），因此本项同时消除「删除不编号子集后无谓改名」的 CAD 开销。

## 缺陷机理（根因）

`editing.py::derive_document_structure`：

1. `unnumbered_subset_ids` 依据**命令应用后**的 `subsets` + `titles` 判定（SPEC-DM-014 §3.1 动态判定，本身正确）。
2. `_number_seed(document, unnumbered_subset_ids)` 却遍历**命令前**的 `document.subsets` 取「首个纯数字图号」作为起点与位数。
3. `delete_subset`（以及 `update_subset` 改名脱离关键字）会让某个不编号子集从第 1 步的集合中消失，但它的既有图号仍在第 2 步被读取：
   - 已应用 0 填充的封面（`00`/`000`）→ 起点被拉成 `0`，后续子集全部重编为 0 起（用户看到的 `00 图纸目录`）；
   - 尚未应用 0 填充的封面（`001`）→ 起点从 1 起算，后续子集整体前移一位。
4. 后果不止显示名：图号变化使 `_subset_changed` 为真 → 该子集进入 `rename_only`，每次删除不编号子集都白启动一次 Core Console 并改写图号/布局名。

## Tasks

### Task 1: 失败测试（TDD RED）

- [x] **Step 1**：新增 `tests/unit/test_unnumbered_subsets.py::test_deleting_applied_unnumbered_subset_does_not_drag_number_seed_to_zero`（位数参数化 `00/01`、`000/001`、`0000/0001`）：删除已应用 0 填充的封面后，图纸目录图号与显示名保持不变。
- [x] **Step 2**：新增 `test_deleting_unnumbered_subset_keeps_following_numbers_without_zero_padding`：封面仍为既有编号（`001`）时删除它，后续子集也不前移。
- [x] **Step 3**：新增计划级用例 `tests/unit/test_core.py::test_deleting_unnumbered_subset_keeps_following_numbers_and_cad_scope`：删除 `00 封面` 后，图纸目录 `cad_operation == "none"`、`groups == []`、`deleted_subsets == ["subset-u"]`。
- [x] **Step 4**：确认红态：5 例全部失败（`[['00']] == [['01']]`、`[['001']] == [['002']]`、`{'subset-c': 'rename_only'} == {'subset-c': 'none'}`），修复前证据由「`git diff` 存补丁 → `git checkout --` → 复跑 → `git apply` 恢复」取得。

### Task 2: 实现（TDD GREEN）

- [x] **Step 1**：`derive_document_structure` 在 `titles` 初始化后立即计算 `original_unnumbered_subset_ids`（命令前快照判定，含中文注释说明为何必须与种子快照一致）。
- [x] **Step 2**：`_number_seed(document, unnumbered_subset_ids | original_unnumbered_subset_ids)`。
- [x] **Step 3**：5 例转绿，`tests/unit/test_unnumbered_subsets.py` 22 passed（新增 4 例）。

### Task 3: 文档与变更记录

- [x] **Step 1**：SPEC-DM-014 §行为 3 补充「排除集合必须与种子快照一致，取命令前 ∪ 命令后判定」，§行为 5 补充「删除图纸、删除命中关键字的子集同样不改变其他子集图号」。
- [x] **Step 2**：SPEC-DM-014 追加「实现缺陷修复（2026-09-14 追记）」，说明现象、根因、修复范围与回归证据；front matter 增 `PLAN-DM-032`。
- [x] **Step 3**：本计划落盘；`docs/dst-manager/README.md` 与 `.planning/plans/dst-manager/README.md` 增索引行。
- [x] **Step 4**：根 `changelog.md` 追加修复条目。

## 实际验证

| 项 | 命令 | 结果 |
| --- | --- | --- |
| RED 证据（修复前） | 还原 `editing.py` 后 `uv run pytest tests/unit/test_unnumbered_subsets.py tests/unit/test_core.py::test_deleting_unnumbered_subset_keeps_following_numbers_and_cad_scope -q` | **5 failed / 18 passed**：`[['00']] != [['01']]`、`[['000']] != [['001']]`、`[['0000']] != [['0001']]`、`[['001']] != [['002']]`、`{'subset-c': 'rename_only'} != {'subset-c': 'none'}` |
| 定向用例（修复后） | `uv run pytest tests/unit/test_unnumbered_subsets.py -q` | **22 passed**（EXIT=0） |
| 全量回归 | `uv run pytest -q -p no:warnings --junitxml=.tmp-res.xml` | **1481 项：1409 passed / 72 skipped / 0 failed / 0 errors**（107.4 s；本项 +5 用例） |
| 静态检查 | `uv run ruff check .` | All checks passed!（EXIT=0） |
| 真实 CAD 系统测试 | `DST_MANAGER_RUN_AUTOCAD=1 uv run pytest tests/system_autocad -q` | 未执行（改动只在编号派生，不涉及 SCR、插件命令、布局重建与 Handle 回读） |
| 前端 | 未改动 | HTTP 契约与响应字段不变，`npm run build` / Playwright 未重跑 |

## 门禁分级与证据缺口（如实记录）

参考 [GUIDE-DM-001](../../../docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md)：本项为纯领域计算缺陷修复，**无前端渲染层改动**（无新增控件、无视觉变化、无 i18n 键变化），按 S 级口径执行最小充分门禁：

- 已执行：G0（全量 pytest 1481 项）、G1（Ruff 通过）、针对本缺陷的定向红绿证据。
- 未重开：G3/G4/G5～G8（前端零改动）、G9（真实桌面验收）。
- **G9 待办**：打包 EXE 重建后在真实桌面复验「插入封面 → 删除封面」两轮后 `01 图纸目录` 图号与布局名不变、不产生 CAD 工作单元。

## 后续项

- 同类的「判定快照不一致」风险点：`_number_seed` 之外的派生分支是否还有「读命令前快照、却用命令后判定」的组合，暂无其他已知实例；后续如新增派生输入，需同时指明它读的是哪个快照。
- 编号派生与 CAD 操作的关系见 [PLAN-DM-030](PLAN-DM-030-provable-diff-cad-scope.md)：本项修复后，删除不编号子集既不重编号也不产生 CAD 工作单元，两条修复互为验证。
