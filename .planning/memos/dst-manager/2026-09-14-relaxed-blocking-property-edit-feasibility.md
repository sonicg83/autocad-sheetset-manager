---
id: MEMO-DM-035
title: 阻断状态下放开属性编辑的可行性评估（门禁分级与增量校验）
status: final
document_kind: memo
owners:
  - dst-manager
created: 2026-09-14
updated: 2026-09-14
related:
  - MEMO-DM-032
  - ARCH-DM-001
  - SPEC-DM-004
---

# 阻断状态下放开属性编辑的可行性评估备忘

## 日期

2026-09-14

## 背景

用户需求：当前阻断限制过于严格。当 DST 因**图纸结构类**阻断问题（如图纸缺 Number/Title、图纸不在子集内、缺少子集等）处于 `INVALID_REPAIR_REQUIRED` 状态时，期望的行为是：

1. 禁止图纸结构编辑（CAD Worker 不可用）；
2. 但允许浏览图纸结构；
3. 并允许修改属性（图纸属性与图纸集属性）。

本备忘为只读调研结论，评估实现难度并给出建议方案，未修改源码。

## 结论

**实现不难，属中低难度改动，无架构级障碍。** 门禁与命令体系已具备区分结构/非结构命令的能力，核心工作集中在两点：

1. `_gate_writable` 从"一刀切"改为按命令类型分级；
2. 发布路径从全量校验改为增量（差集）校验——这是目前真正的硬阻断点。

估计一到两天开发量（后端核心 + 前端交互 + 测试）。

## 现状事实

### 1. 状态分类（加载时确定）

DST 加载时由 `AcsmRepairer.repair` 产出四态分类（`src/dst_manager/infrastructure/acsm_xml/document.py` `AcsmDocument.__init__`）：

- `VALID` — 正常；
- `REPAIRED` — 有可自动修复的缺失，待确认；
- `INVALID_REPAIR_REQUIRED` — 存在阻断诊断（目标场景）；
- `INVALID_UNRECOVERABLE` — 不可恢复。

阻断诊断来源见 `infrastructure/acsm_xml/repair.py`：`SHEET_FIELD_MISSING`（图纸缺 Number/Title）、`SHEET_LAYOUT_COUNT`、`LAYOUT_FIELD_MISSING`、`CUSTOM_PROPERTY_FLAGS_INVALID` 等；另经 `_merge_contract_issues` 并入契约复核问题。

### 2. 唯一的写入门禁是一刀切

`_gate_writable`（`src/dst_manager/application/service.py`）只看状态不看命令类型：非 `VALID` 一律 409。挂载点：

- `preview_changes`（`application/editing.py`）→ `execute_changes` 先调 preview，所有编辑全被挡；
- XML 导入导出（`application/xml_io.py`，两处）。

### 3. 命令体系本身已区分结构/非结构

`application/editing.py` 中命令分两类，且该区分已贯穿预览与执行：

| 类型 | 命令 | 是否需要 CAD Worker |
|---|---|---|
| 结构命令 | `insert_sheet`、`insert_subset`、`delete_sheet`、`delete_subset`、`update_subset` | 是 |
| 元数据命令 | `update_sheet_set`（图纸集属性）、`update_sheet`（图纸属性）、`add/delete_custom_property` | 否 |

注意：`update_sheet_properties` 不允许直接改 Number/Title（`_normalize_commands` 会拒绝），图号/标题归结构域，需要 CAD。

### 4. CAD Worker 侧已有独立门禁（双保险）

`application/cad_job.py`：CAD 暂存加载强制要求 `VALID`，否则抛 `DST_REPAIR_GATE_BLOCKED`。即使放开预览层，结构任务也到不了 Worker。

### 5. 浏览不受影响

结构投影（`AcsmDocument.project()`）不依赖状态，阻断时本来就能浏览树和诊断（`RepairStatusPanel.vue`）。

## 建议方案

### 改动一：门禁分级（简单）

把 `_gate_writable` 改为接受命令上下文：

- `INVALID_UNRECOVERABLE`、`REPAIRED` → 维持全禁；
- `INVALID_REPAIR_REQUIRED` → 拒绝结构命令，放行元数据命令。

`preview_changes` 里已有 `structural` 标志，在此分支即可。

**设计决策提示**：`REPAIRED` 建议维持全禁。REPAIRED 的 DOM 包含未确认的自动修复动作，若此时放行属性编辑并发布，会把修复动作夹带进属性修订，绕过"独立修复修订"的审计要求。

### 改动二：发布路径改增量校验（主要工作量）

`execute_changes` 的非 CAD 分支在应用命令后做**全量** `acsm.validate()`，任何 ERROR 都抛 `XML_VALIDATION_FAILED`。阻断状态下文档本来就带着旧错误（例如别张图纸的 `SHEET_FIELD_MISSING`），所以即使放开门禁，提交也 100% 失败——这是目前真正的硬阻断点。

需改为差集校验：发布前先取既有错误集（在 repair 后的 DOM 上取），应用命令后再取一次，只拒绝**新增**的错误。`preview_changes` 已有同款思路（对 planned sheets 跳过已知问题），模式可直接复用。

### 改动三：前端交互（中等）

前端按 `validation.status` 禁用编辑控件的逻辑改为"结构按钮禁用 + 属性面板可用"，补 i18n 文案与 `RepairStatusPanel` 提示。

### 改动四：测试

需覆盖：

- 阻断状态下属性预览 `executable=true`；
- 结构命令仍 409；
- 含旧错误的提交成功；
- 命令引入新错误时提交被拒；
- 提交后状态重算仍为 `INVALID_REPAIR_REQUIRED`（不误升级/降级）。

同步更新 changelog 与相关文档中"非 VALID 只能读"的表述。

## 风险评估

- **安全性**：属性编辑沿用既有 `DST → XML DOM → DST` 受控流程和发布事务；修复器只补缺失、不覆盖非空值，与属性写入无冲突，不违反 ARCH-DM-001 的 DST 安全约束。
- **语义收益**：部分阻断问题（如自定义属性作用域类）本身就要靠属性编辑来修复，现有全禁反而造成"死锁"，放开方向合理。
- **范围控制**：XML 导入导出（`xml_io`）维持原门禁，不必一并放开。

## 后续

若决定立项，按 `.planning/plans/` 规范立实施计划；本备忘仅记录评估结论，不承载实施细节。
