---
id: ROADMAP-DM-001
title: DST Manager 路线图
status: accepted
owners:
  - dst-manager
created: 2026-08-17
updated: 2026-09-03
related:
  - ARCH-DM-001
  - SPEC-DM-007
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

当前基线为 v0.2.1。路线图已按 `PLAN-DM-005` 至 `PLAN-DM-009` 的实际交付重基线：后续版本只能在受控编辑、修复门禁、快速预览和 CAD 分流约束内演进。2026-09-03 依据 [v0.3 测试后意见](../memos/DMv03-test-report.md) 再次重基线：v0.3.1 改为 [SPEC-DM-007](../../docs/dst-manager/specs/SPEC-DM-007-v031-shell-and-usability.md) 驱动的桌面壳与易用性迭代，SPEC-DM-006 界面重构推后为 v0.3.2。

本路线图以 [ARCH-DM-001](../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md) 为架构基线；已完成阶段保留验证记录，后续阶段仍为计划，不代表已经实施。

## 目标阶段

| 版本 | 状态 | 目标 | Plan |
| --- | --- | --- | --- |
| v0.2 | 已完成 | 稳定化、修订恢复、任务自救与多 DWG 有界并行 | [PLAN-DM-001](../plans/dst-manager/PLAN-DM-001-v0.2-stabilization-and-multi-dwg-parallel.md) |
| v0.2.1 | 已完成 | 运行与日志、受控图纸集编辑、快速预览与 CAD 分流、DST 可修复加载 | [PLAN-DM-005](../plans/dst-manager/PLAN-DM-005-v0.2.1-runtime-logging-and-acsm-hotfix.md)、[PLAN-DM-006](../plans/dst-manager/PLAN-DM-006-v021-controlled-sheetset-editing.md)、[PLAN-DM-008](../plans/dst-manager/PLAN-DM-008-deferred-cad-validation-and-layout-rename.md)、[PLAN-DM-009](../plans/dst-manager/PLAN-DM-009-dst-schema-validation-and-repair.md) |
| v0.3 | 已完成 | 受控日常编辑器、草稿、人类可读预览与全写入摘要门禁 | [PLAN-DM-002](../plans/dst-manager/PLAN-DM-002-v0.3-daily-editor.md) |
| v0.4 | 计划中 | 单人工作流、受检查模板、CSV 双契约、健康检查与脱敏诊断 | [PLAN-DM-003](../plans/dst-manager/PLAN-DM-003-v0.4-solo-workflow.md) |
| v0.3.1 | 已完成 | 桌面壳（WebView2）与操作易用性迭代：壳为唯一入口、DST 文件选择/关闭确认、草稿恢复可发现性、来源文件与布局选择、布局缓存 | [PLAN-DM-011](../plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md)，依据 [SPEC-DM-007](../../docs/dst-manager/specs/SPEC-DM-007-v031-shell-and-usability.md) |
| v0.3.2 | 计划中 | 桌面界面人性化与易用性重构：依据 SPEC-DM-006 落地（令牌化双主题、统一组件、三区外壳、ActionDock 与无障碍验收） | PLAN-DM-010（待编制） |

下一阶段门禁：在启动 v0.3 前，审查 `SPEC-DM-004` 的正式状态和发布门禁；真实 AutoCAD 2016/2020 与官方 Sheet Manager 显示验收的缺失证据继续作为 v1.0 发布资格门禁，不追溯性标记为通过。

## 退出条件

每一阶段均须保持受控 DST/DWG 写入、整批发布与回滚边界；后续阶段只有在前置阶段的验证证据齐备后才可进入实施。
