---
id: ROADMAP-INT-001
title: 跨项目整合路线图
status: proposed
owners:
  - integration
created: 2026-08-17
updated: 2026-09-21
related:
  - ARCH-INT-001
  - ARCH-INT-002
  - RFC-INT-001
  - RFC-INT-002
  - RFC-INT-003
  - ADR-INT-001
---

# 跨项目整合路线图

> **状态更新（2026-09-21）：** [RFC-INT-003](../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md) 已接受 DST Builder 退场，退场实施与治理收敛由 [PLAN-INT-004](../plans/integration/PLAN-INT-004-retire-dst-builder.md)（completed）完成；仓库现为 DST Manager 单产品状态，`dst-builder` 相关路线与边界仅作历史记录。下方历史段落保留原决策事实。

历史阶段已完成 DST Builder 正式立项、双产品边界和文档治理重基线；该边界已随 Builder 退场终止。

现行规则：仓库只保留 DST Manager 一个现役产品；共享能力必须经 Manager 真实使用并在 `integration` 评审后归入，若未来出现第二个真实消费方必须先有被接受的 `RFC-INT-*` 证明公共边界。已按 [RFC-INT-002](../../docs/integration/rfcs/RFC-INT-002-cancel-builder-manager-handoff.md) / [ADR-INT-001](../../docs/integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md) 取消的 Builder → Manager 交接契约不随退场恢复。任何新的代码合并、领域模型共用或部署整合仍必须先有被接受的 `RFC-INT-*`。

目前没有已批准的产品合并里程碑，也不设置虚构日期。
