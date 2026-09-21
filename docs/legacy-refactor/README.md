# Legacy Python 重构历史资料入口

## 状态

原 `legacy-refactor` 曾演进为独立产品 **DST Builder**；DST Builder 本身也已按 [RFC-INT-003](../integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md) 整体退场，其实现由 Git 历史追溯，本地副本位于被忽略的 `legacy/dst-builder/`。本目录与 `dst-builder` 均为历史 scope，不再接收新的产品需求、架构或实施计划；唯一现役产品是 DST Manager，其入口见 [DST Manager 文档](../dst-manager/README.md)，DST Builder 历史资料见 [DST Builder 文档（历史资料）](../dst-builder/README.md)。

## 被取代的基线

- [Legacy 产品愿景（VISION-LR-001，superseded）](product/vision.md)
- [现代 Python 重构架构基线（ARCH-LR-001，superseded）](architecture/ARCH-LR-001-modern-python-refactor-baseline.md)
- [Legacy Python 重构路线图（ROADMAP-LR-001，cancelled）](../../.planning/roadmaps/legacy-refactor.md)

## 仍可复用的历史资料

- [Python 与 pyautocad 重构可行性评估（RES-LR-001）](research/RES-LR-001-python-refactor-assessment.md)
- [Legacy 开发与交接指南（GUIDE-LR-001）](guides/GUIDE-LR-001-legacy-development-handover.md)

这些资料可用于规则考古、黄金样本设计和旧链路理解，但不构成 DST Builder 或 DST Manager 的兼容承诺。新的稳定结论应写入 `dst-manager`、`shared` 或 `integration` 对应权威位置，并链接历史来源。
