# DST Manager 文档入口

## 定位与当前状态

DST Manager 面向单人单机真实工程，提供既有 DST/DWG 的检查、受控编辑和安全发布能力。当前版本为 `v0.3.1`。既有 `v0.3` 基线已包含受控图纸集编辑、快速预览/确认阶段 CAD 分流、DST XML 契约校验与可修复加载，以及 `PLAN-DM-002` 的持久草稿、大项目导航、统一写入摘要门禁和子集整体删除；图号、范围、标题、后缀和文件/布局命名均由受控规则统一派生。

2026-09-03 交付 `v0.3.1`（[PLAN-DM-011](../../.planning/plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md)，依据 [SPEC-DM-007](specs/SPEC-DM-007-v031-shell-and-usability.md)）：新增 pywebview（WebView2）桌面壳，`uv run dst-manager desktop` 为唯一交付入口；前端两态状态机（DST 文件选择/关闭确认/草稿恢复提示/保存状态可见性）、来源文件选择与布局下拉；后端新增 `POST /api/layout-names` 布局名读取端点与全局缓存（SHA-256 → 布局名，SQLite 迁移 0004），Worker 插件新增只读布局枚举命令 `DstGetLayoutNames`（不修改图纸、不 QSAVE）。全量验证与真实 AutoCAD 2016/2020 系统测试记录见 [PLAN-DM-011](../../.planning/plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md)「实际验证」小节。

2026-08-26 已在私有 `sample/project1` 临时副本上完成 `PLAN-DM-008` 的 AutoCAD 2016/2020 验收：非性能系统矩阵 54/54、并发 1/4/10 性能矩阵 6/6、双版本插件构建成功；全量 Python 为 367 passed、64 skipped，Web E2E 为 18 passed。`rename_only` 不删除/导入布局且保持 Handle，`rebuild` 才回读 Handle；默认并发为 4、合法范围 1–10，任一单元失败均不发布。`PLAN-DM-009` 已完成非 CAD 交付验证（全量 Python 432 passed、66 skipped；Web E2E 19/19）；其真实 AutoCAD 2016/2020 与官方 Sheet Manager 显示验收尚未在该环境运行，保留为 v1.0 发布资格门禁。具体记录见 [PLAN-DM-008](../../.planning/plans/dst-manager/PLAN-DM-008-deferred-cad-validation-and-layout-rename.md) 与 [PLAN-DM-009](../../.planning/plans/dst-manager/PLAN-DM-009-dst-schema-validation-and-repair.md)。

## 当前规范与决策

- [产品愿景（VISION-DM-001）](product/vision.md)
- [已接受的架构基线（ARCH-DM-001）](architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)
- [受控图纸集编辑替代自由调整模型（ADR-DM-001）](adr/ADR-DM-001-controlled-sheetset-editing.md)
- [CAD 单脚本布局重建（ADR-DM-002）](adr/ADR-DM-002-v021-cad-single-script-execution.md)
- [延后 CAD 校验与子集级 CAD 操作分流（ADR-DM-003，已实施）](adr/ADR-DM-003-deferred-cad-validation-and-subset-cad-operations.md)
- [正式工程文件删除纳入可恢复发布事务（ADR-DM-004，已接受）](adr/ADR-DM-004-recoverable-file-deletion.md)
- [实施路线图（ROADMAP-DM-001）](../../.planning/roadmaps/dst-manager.md)
- [当前 Plan 索引](../../.planning/plans/dst-manager/README.md)

当前没有独立 PRD。功能规范：

- [v0.21 图纸集编辑需求调整规范（SPEC-DM-001，已接受）](specs/SPEC-DM-001-v021-sheetset-editing-adjustment.md)
- [v0.21 CAD 单脚本布局重建需求调整规范（SPEC-DM-002，已接受）](specs/SPEC-DM-002-v021-cad-single-script-execution.md)
- [延后 CAD 校验与子集级 CAD 操作分流规范（SPEC-DM-003，已验收）](specs/SPEC-DM-003-deferred-cad-validation-and-subset-cad-operations.md)
- [DST XML Schema 校验与可修复加载契约（SPEC-DM-004，已接受）](specs/SPEC-DM-004-dst-schema-validation-and-repair.md)
- [受控子集整体删除与文件事务规范（SPEC-DM-005，已接受）](specs/SPEC-DM-005-controlled-subset-deletion.md)
- [单人桌面界面人性化与易用性设计规范（SPEC-DM-006，评审中）](specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md)
- [v0.3.1 桌面壳与操作易用性迭代设计规范（SPEC-DM-007，草稿）](specs/SPEC-DM-007-v031-shell-and-usability.md)
- [v0.3.2 命名与模板流程需求变更规范（SPEC-DM-008，已接受）](specs/SPEC-DM-008-v032-naming-and-template-flows.md)

## 指南

- [启动、使用和开发说明](../../README.md#一键启动)
- [测试策略](architecture/ARCH-DM-001-dst-manager-mvp-baseline.md#12-测试策略)

当前暂无独立部署指南；开发与测试入口以上述仓库说明和架构基线为准。
