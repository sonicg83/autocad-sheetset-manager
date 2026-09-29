# 执行资料索引

本目录保存有时效性的路线图、实施计划、待办和备忘；长期事实、规范和可复用知识请查阅 [`docs/README.md`](../docs/README.md)。

- [DST Builder 路线图（cancelled）](roadmaps/dst-builder.md)
- [Legacy Python 重构历史路线图（cancelled）](roadmaps/legacy-refactor.md)
- [DST Manager 路线图](roadmaps/dst-manager.md)
- [跨项目整合路线图](roadmaps/integration.md)
- [DST Manager Plan 索引](plans/dst-manager/README.md)
- [无版本图纸标准身份与标准库管理实施计划（PLAN-DM-046，completed）](plans/dst-manager/PLAN-DM-046-versionless-standard-management.md)：完成 UUID＋发布时间、描述、改名导入、平铺管理、关联创建草稿删除、旧版本只读兼容迁移与端到端验证。
- [DST Builder Plan 索引（历史资料）](plans/dst-builder/README.md)
- 待办见 [`todos/dst-manager/`](todos/dst-manager/)；Builder 相关待办已随 Builder 退场清理（PLAN-INT-004）。
- 备忘：[PLAN-INT-002 交付记录（MEMO-INT-001）](memos/integration/MEMO-INT-001-plan-int-002-delivery-record.md)：执行方式、26 项控制器裁定、计划缺陷与待决事项。
- [表格对齐契约前端收口实施计划（PLAN-DM-043，active——Task 1–5 已完成，真实桌面缩放复验待用户执行）](plans/dst-manager/PLAN-DM-043-table-alignment-frontend-remediation.md)：落实普通、常驻编辑与跨列详情三类表格行高和内边距边界，扩展 `check:ui` 与计算样式回归。
- [映射源一对多复用实施计划（PLAN-DM-045，completed）](plans/dst-manager/PLAN-DM-045-mapping-source-multi-target-reuse.md)：解除 SPEC-DM-017 §5.2 源唯一占用限制，允许同一枚举源被多个映射属性复用，并移除 `STANDARD_MAPPING_SOURCE_DUPLICATE` 阻断码与相关文案、门禁分支与回归用例。
- [语义化 grid 伪表格对齐契约收口实施计划（PLAN-DM-044，active）](plans/dst-manager/PLAN-DM-044-grid-pseudo-table-alignment.md)：承接 grid 伪表格（枚举值、映射属性、派生属性、目录列编辑器）的对齐契约缺口，补语义标记与 `grid-table-*` 门禁及新表守卫；与 PLAN-DM-043 不重叠。
- [双项目文档迁移实施计划](plans/integration/PLAN-INT-001-documentation-migration.md)
- [取消 Builder 与 Manager 显式交接契约实施计划（PLAN-INT-002，completed）](plans/integration/PLAN-INT-002-cancel-builder-manager-handoff.md)：已按 RFC-INT-002 / ADR-INT-001 移除两侧交接实现与 `handoff_sources` 表，Builder 成果改为扁平三件套。
- [双产品测试体系收敛与过时内容清理实施计划（PLAN-INT-003，cancelled）](plans/integration/PLAN-INT-003-test-system-consolidation.md)：DST Builder 已退场，双产品测试治理失去前提；未来 Manager 测试治理另行立项。
- [DST Builder 整体归档与文档封口实施计划（PLAN-INT-004，completed）](plans/integration/PLAN-INT-004-retire-dst-builder.md)：已将 Builder 产品面和专用脚本整体移入本地 `legacy/`，删除 0007/0008 并压平 Manager 迁移基线（head `0006_dm020_extension_platform`，旧本地数据库需手工重建），历史文档已封口为 Manager 单产品治理。
- [标准整数版本、按 ID 归集与标准包预检导入实施计划（PLAN-DM-041，active——Task 1–7 与 Task 8 自动门禁已完成，真实桌面 G9 待用户执行）](plans/dst-manager/PLAN-DM-041-standard-package-import-picker.md)：记录当前实现与验证；原 [SPEC-DM-019](../docs/dst-manager/specs/SPEC-DM-019-standard-version-and-package-import.md) 已由 SPEC-DM-020 取代，后续改造按 PLAN-DM-046。
- [图纸标准平台审查问题修复计划（PLAN-DM-040，active）](plans/dst-manager/PLAN-DM-040-standard-platform-review-remediation.md)：F01–F15 与 F17 共 16 项问题按 Step 串行分批收口，模板资产文件无法加入草稿列为阻断级；原 F16 拆至 PLAN-DM-041。任务 1–9 已实施并验证，任务 10 的闭环与全量门禁完成、真实桌面 G9 待人工执行。
- [图纸标准平台与标准编辑器实施计划（PLAN-DM-035，completed）](plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md)
- [标准驱动的新图纸集创建实施计划（PLAN-DM-036，active）](plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md)
- [图纸标准校验与 HTML JSON 报告实施计划（PLAN-DM-037，proposed）](plans/dst-manager/PLAN-DM-037-standard-validation-reports.md)

## 模板

- [备忘模板](_templates/memo.md)
- [实施计划模板](_templates/plan.md)
- [路线图模板](_templates/roadmap.md)
