---
id: ROADMAP-INT-001
title: 跨项目整合路线图
status: proposed
owners:
  - integration
created: 2026-08-17
updated: 2026-09-18
related:
  - ARCH-INT-001
  - ARCH-INT-002
  - RFC-INT-001
  - RFC-INT-002
  - ADR-INT-001
---

# 跨项目整合路线图

当前阶段已完成 DST Builder 正式立项、双产品边界和文档治理重基线。

下一阶段只允许按 [RFC-INT-001](../../docs/integration/rfcs/RFC-INT-001-dst-builder-product-establishment.md) 提取已有两个真实消费方的稳定能力，并已按 [RFC-INT-002](../../docs/integration/rfcs/RFC-INT-002-cancel-builder-manager-handoff.md) / [ADR-INT-001](../../docs/integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md) 取消 Builder → Manager 交接契约，两条产品线以 DST 文件为唯一接口。任何新的代码合并、领域模型共用或部署整合仍必须先有被接受的 `RFC-INT-*`。

目前没有已批准的产品合并里程碑，也不设置虚构日期。
