# DST Builder 文档入口

## 定位与当前状态

DST Builder 是面向图纸集首版生产的本地桌面应用。它把结构化项目数据转换为经过校验的 DWG、DST 和伴随成果，并以可审计的基线包交接给 DST Manager。

当前产品愿景、首期需求和绿地桌面架构已经接受；首个单张图纸生成闭环 Spec 进入 `review`，实施计划为 `proposed`，尚未创建代码骨架或声明独立产品版本。

## 当前规范与决策

- [产品愿景（VISION-DB-001）](product/vision.md)
- [引导式图纸集生成产品需求（PRD-DB-001）](product/prds/PRD-DB-001-guided-sheetset-generation.md)
- [绿地桌面架构基线（ARCH-DB-001）](architecture/ARCH-DB-001-greenfield-desktop-baseline.md)
- [单张图纸最小生成闭环规范（SPEC-DB-001，review）](specs/SPEC-DB-001-minimal-generation-loop.md)
- [实施路线图（ROADMAP-DB-001）](../../.planning/roadmaps/dst-builder.md)
- [单张图纸最小生成闭环实施计划（PLAN-DB-001，proposed）](../../.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md)
- [DST Builder 立项与共享平台边界（RFC-INT-001）](../integration/rfcs/RFC-INT-001-dst-builder-product-establishment.md)
- [双产品与共享平台治理（ARCH-INT-002）](../integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md)

## 历史输入

旧 `legacy-refactor` 愿景、架构和路线图已由本产品基线取代，但继续保留为规则考古、黄金样本和迁移背景。它们不是 DST Builder 的运行时兼容承诺，入口见[历史 Legacy Python 重构资料](../legacy-refactor/README.md)。

当前暂无独立 ADR、Guide 或 Research。SPEC-DB-001 与 PLAN-DB-001 是首个代码实施阶段的范围和执行门禁；两者未获确认前不进入代码实施。
