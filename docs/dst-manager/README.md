# DST Manager 文档入口

## 定位与当前状态

DST Manager 面向单人单机真实工程，提供既有 DST/DWG 的检查、受控编辑和安全发布能力。当前版本为 `v0.2.1`，已完成 v0.21 受控图纸集编辑交付：支持属性定义与 CSV、按位置批量插图、创建非空子集及独立 DWG，并统一派生图号、范围、标题、后缀和文件/布局命名。

非 CAD 自动化、Web E2E 和 AutoCAD 2016/2020 插件构建已经验收。由于公开隔离工作树不包含私有 `sample/project1`，本机本轮未执行双版本真实 CAD 系统验收；补齐样本后仍需运行 2016/2020 Core Console 测试。

## 当前规范与决策

- [产品愿景（VISION-DM-001）](product/vision.md)
- [已接受的架构基线（ARCH-DM-001）](architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)
- [受控图纸集编辑替代自由调整模型（ADR-DM-001）](adr/ADR-DM-001-controlled-sheetset-editing.md)
- [实施路线图（ROADMAP-DM-001）](../../.planning/roadmaps/dst-manager.md)
- [当前 Plan 索引](../../.planning/plans/dst-manager/README.md)

当前没有独立 PRD。功能规范：

- [v0.21 图纸集编辑需求调整规范（SPEC-DM-001，已接受）](specs/SPEC-DM-001-v021-sheetset-editing-adjustment.md)

## 指南

- [启动、使用和开发说明](../../README.md#一键启动)
- [测试策略](architecture/ARCH-DM-001-dst-manager-mvp-baseline.md#12-测试策略)

当前暂无独立部署指南；开发与测试入口以上述仓库说明和架构基线为准。
