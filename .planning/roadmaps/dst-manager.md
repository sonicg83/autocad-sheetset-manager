---
id: ROADMAP-DM-001
title: DST Manager 路线图
status: accepted
owners:
  - dst-manager
created: 2026-08-17
updated: 2026-08-28
related:
  - ARCH-DM-001
  - PLAN-DM-001
  - PLAN-DM-002
  - PLAN-DM-003
  - PLAN-DM-004
  - PLAN-DM-005
  - PLAN-DM-006
  - PLAN-DM-007
  - PLAN-DM-008
  - PLAN-DM-009
---

# DST Manager 路线图

当前基线为 v0.2.1。路线图已按 `PLAN-DM-005` 至 `PLAN-DM-009` 的实际交付重基线：后续版本只能在受控编辑、修复门禁、快速预览和 CAD 分流约束内演进。

本路线图以 [ARCH-DM-001](../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md) 为架构基线；已完成阶段保留验证记录，后续阶段仍为计划，不代表已经实施。

## 目标阶段

| 版本 | 状态 | 目标 | Plan |
| --- | --- | --- | --- |
| v0.2 | 已完成 | 稳定化、修订恢复、任务自救与多 DWG 有界并行 | [PLAN-DM-001](../plans/dst-manager/PLAN-DM-001-v0.2-stabilization-and-multi-dwg-parallel.md) |
| v0.2.1 | 已完成 | 运行与日志、受控图纸集编辑、快速预览与 CAD 分流、DST 可修复加载 | [PLAN-DM-005](../plans/dst-manager/PLAN-DM-005-v0.2.1-runtime-logging-and-acsm-hotfix.md)、[PLAN-DM-006](../plans/dst-manager/PLAN-DM-006-v021-controlled-sheetset-editing.md)、[PLAN-DM-008](../plans/dst-manager/PLAN-DM-008-deferred-cad-validation-and-layout-rename.md)、[PLAN-DM-009](../plans/dst-manager/PLAN-DM-009-dst-schema-validation-and-repair.md) |
| v0.3 | 计划中 | 受控日常编辑器、草稿、人类可读预览与全写入摘要门禁 | [PLAN-DM-002](../plans/dst-manager/PLAN-DM-002-v0.3-daily-editor.md) |
| v0.4 | 计划中 | 单人工作流、受检查模板、CSV 双契约、健康检查与脱敏诊断 | [PLAN-DM-003](../plans/dst-manager/PLAN-DM-003-v0.4-solo-workflow.md) |
| v1.0 | 计划中 | Windows 产品化、升级恢复、保留策略与发布资格 | [PLAN-DM-004](../plans/dst-manager/PLAN-DM-004-v1.0-windows-productization.md) |

下一阶段门禁：在启动 v0.3 前，审查 `SPEC-DM-004` 的正式状态和发布门禁；真实 AutoCAD 2016/2020 与官方 Sheet Manager 显示验收的缺失证据继续作为 v1.0 发布资格门禁，不追溯性标记为通过。

## 退出条件

每一阶段均须保持受控 DST/DWG 写入、整批发布与回滚边界；后续阶段只有在前置阶段的验证证据齐备后才可进入实施。
