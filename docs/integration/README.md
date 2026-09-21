# 跨项目整合

本目录保存产品边界调整、跨 scope RFC、整合架构、已确认的整合 ADR 及稳定边界。产品私有功能不得放入本目录。

当前有效架构为 [ARCH-INT-002：DST Manager 单产品治理与共享平台](architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md)。[ARCH-INT-001](architecture/ARCH-INT-001-documentation-organization.md) 已被取代并保留历史追溯。

[RFC-INT-003](rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md) 已接受 Builder 直接退场及标准驱动创建归入 Manager；退场实施与治理收敛已由 [PLAN-INT-004](../../.planning/plans/integration/PLAN-INT-004-retire-dst-builder.md)（completed）完成：Builder 实现归档至本地 `legacy/dst-builder/`（公开实现由 Git 历史追溯），`ARCH-INT-002` 已更新为 Manager 单产品治理，Builder 文档保留为只读历史资料。标准驱动创建由 [PLAN-DM-035](../../.planning/plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md) 与 [PLAN-DM-036](../../.planning/plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md) 承接。

- [整合 ADR 索引](adr/README.md)
- [RFC 索引](rfcs/README.md)
- [RFC-INT-003：DST Builder 退场与标准驱动的图纸集创建（accepted）](rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)
- [RFC-INT-002：取消 Builder 与 Manager 的显式交接契约（accepted）](rfcs/RFC-INT-002-cancel-builder-manager-handoff.md)
- [RFC-INT-001：DST Builder 立项与共享平台边界](rfcs/RFC-INT-001-dst-builder-product-establishment.md)
- [整合路线图](../../.planning/roadmaps/integration.md)
