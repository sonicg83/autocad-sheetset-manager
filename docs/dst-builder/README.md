# DST Builder 文档入口

## 定位与当前状态

DST Builder 是面向图纸集首版生产的本地桌面应用。它把结构化项目数据转换为经过校验的 DWG、DST 和伴随成果，并发布到目标目录，由 DST Manager 直接打开。

当前产品愿景、首期需求和绿地桌面架构已经接受。首个单张图纸最小生成闭环已按 SPEC-DB-001 完成实施（PLAN-DB-001 Task 1–12）：独立项目库、AutoCAD 2016/2020 Worker、DST/图纸目录生成、原子发布与独立桌面打包均已落地，开发门禁全绿；向导六步化与正式成果布局扁平化已由 [PLAN-INT-002](../../.planning/plans/integration/PLAN-INT-002-cancel-builder-manager-handoff.md)（`completed`）落地。Manager 交接契约已由 [RFC-INT-002](../integration/rfcs/RFC-INT-002-cancel-builder-manager-handoff.md) 与 [ADR-INT-001](../integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md) 取消，两条产品线以 DST 文件为唯一接口。SPEC-DB-001 维持 `review`、PLAN-DB-001 维持 `active`：真实双版本发布资格（官方 Sheet Set Manager 打开 DST、真实端到端发布与 Manager 打开验收、真实 WebView2 人工验收）尚未执行，证据见[发布证据备忘](../../.planning/memos/dst-builder/PLAN-DB-001-release-evidence.md)。

## 当前规范与决策

- [产品愿景（VISION-DB-001）](product/vision.md)
- [引导式图纸集生成产品需求（PRD-DB-001）](product/prds/PRD-DB-001-guided-sheetset-generation.md)
- [绿地桌面架构基线（ARCH-DB-001）](architecture/ARCH-DB-001-greenfield-desktop-baseline.md)
- [单张图纸最小生成闭环规范（SPEC-DB-001，review）](specs/SPEC-DB-001-minimal-generation-loop.md)
- [实施路线图（ROADMAP-DB-001）](../../.planning/roadmaps/dst-builder.md)
- [单张图纸最小生成闭环实施计划（PLAN-DB-001，active）](../../.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md)
- [发布证据备忘（PLAN-DB-001）](../../.planning/memos/dst-builder/PLAN-DB-001-release-evidence.md)
- [DST Builder 立项与共享平台边界（RFC-INT-001）](../integration/rfcs/RFC-INT-001-dst-builder-product-establishment.md)
- [双产品与共享平台治理（ARCH-INT-002）](../integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md)

## 历史输入

旧 `legacy-refactor` 愿景、架构和路线图已由本产品基线取代，但继续保留为规则考古、黄金样本和迁移背景。它们不是 DST Builder 的运行时兼容承诺，入口见[历史 Legacy Python 重构资料](../legacy-refactor/README.md)。

当前暂无独立 ADR、Guide 或 Research。SPEC-DB-001 与 PLAN-DB-001 是首个代码实施阶段的范围和执行门禁；实施已完成并通过自动化门禁，正式发布资格以真实 CAD 与人工验收证据为准。
