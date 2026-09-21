# DST Builder 文档入口（历史资料）

> **封口说明（2026-09-21）：** DST Builder 已按 [RFC-INT-003](../integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md) 整体退场：公开实现由 Git 历史追溯，本地副本位于被 Git 忽略的 `legacy/dst-builder/`。本目录仅保留历史导航和封口说明，不复制实现细节，也不再接收新的 Builder 产品需求、计划或发布工作。新建图纸集能力归入 DST Manager，替代方向见 [RFC-INT-003](../integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)、[PLAN-DM-035](../../.planning/plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md) 与 [PLAN-DM-036](../../.planning/plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md)。

## 历史文档导航

- [产品愿景（VISION-DB-001，archived）](product/vision.md)
- [引导式图纸集生成产品需求（PRD-DB-001，archived）](product/prds/PRD-DB-001-guided-sheetset-generation.md)
- [绿地桌面架构基线（ARCH-DB-001，archived）](architecture/ARCH-DB-001-greenfield-desktop-baseline.md)
- [单张图纸最小生成闭环规范（SPEC-DB-001，archived）](specs/SPEC-DB-001-minimal-generation-loop.md)
- [实施路线图（ROADMAP-DB-001，cancelled）](../../.planning/roadmaps/dst-builder.md)
- [单张图纸最小生成闭环实施计划（PLAN-DB-001，cancelled）](../../.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md)
- [发布证据备忘（PLAN-DB-001）](../../.planning/memos/dst-builder/PLAN-DB-001-release-evidence.md)
- [DST Builder 立项与共享平台边界（RFC-INT-001）](../integration/rfcs/RFC-INT-001-dst-builder-product-establishment.md)
- [取消 Builder 与 Manager 显式交接契约（RFC-INT-002）](../integration/rfcs/RFC-INT-002-cancel-builder-manager-handoff.md)
- [交接契约取消决策（ADR-INT-001）](../integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md)
- [DST Manager 单产品治理与共享平台（ARCH-INT-002，现行权威）](../integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md)
- [Builder 退场与标准驱动创建（RFC-INT-003，accepted）](../integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)

## 历史证据与输入

- `.planning/memos/dst-builder/` 保留为 Builder 历史证据（发布证据、评审与阶段记录），只读，不新增条目。
- 旧 `legacy-refactor` 愿景、架构和路线图记录 Builder 之前的规则考古、黄金样本和迁移背景，入口见[历史 Legacy Python 重构资料](../legacy-refactor/README.md)。
- 以上历史资料不构成任何运行时兼容承诺，也不再作为现役实现依据。
