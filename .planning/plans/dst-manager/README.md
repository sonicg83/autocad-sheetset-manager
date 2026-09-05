# DST Manager MVP 后续实施计划

状态：持续规划中；当前能力基线为 v0.2.1（含 PLAN-DM-005、PLAN-DM-006、PLAN-DM-008 与 PLAN-DM-009）。
目标：把当前技术验证型 MVP 完善为可长期、可靠地处理真实工程的单人单机图纸集编辑管理工具。

## 阶段顺序

| 阶段 | 版本目标 | 核心成果 | 前置条件 |
| --- | --- | --- | --- |
| 1 | v0.2 稳定化 | 数据安全、修订恢复、任务自救、多 DWG 有界并行 | 当前 MVP |
| 2 | v0.3 受控日常编辑器 | 草稿、批量属性维护、人类可读预览、修复状态与全写入摘要门禁 | v0.2.1 基线稳定，SPEC-DM-004 门禁已明确 |
| 3 | v0.4 单人工作流与维护支持 | 最近项目、受检查模板、CSV 双契约、健康检查与脱敏诊断 | 阶段 2 完成 |
| 4 | v1.0 Windows 产品化与发布资格 | 安装升级、恢复、保留策略、双版本 CAD 与官方 Sheet Manager 资格 | 阶段 3 完成，发布门禁具备实际证据 |

详细计划：

- [图纸工作区与任务浮层视觉收敛整改计划（PLAN-DM-017，proposed，依据 SPEC-DM-006/SPEC-DM-009）](PLAN-DM-017-sheets-visual-convergence.md)
- [属性页分区编辑实施计划（PLAN-DM-016，proposed，依据已接受的 SPEC-DM-010）](PLAN-DM-016-properties-workspace-ui.md)
- [图纸页单表工作区实施计划（PLAN-DM-015，active，依据已接受的 SPEC-DM-009；S-07 由 PLAN-DM-017 整改，S-09 真实桌面验收待用户）](PLAN-DM-015-sheets-workspace-ui.md)
- [v0.3.2 命名与模板流程需求变更（PLAN-DM-012，completed，依据 SPEC-DM-008；含 service.py 拆分与 M6/M4）](PLAN-DM-012-v032-naming-and-template-flows.md)
- [v0.3.1 桌面壳与操作易用性迭代（PLAN-DM-011，completed，依据 SPEC-DM-007）](PLAN-DM-011-v031-shell-and-usability.md)
- v0.3.3 桌面界面人性化与易用性重构（PLAN-DM-010，待编制，依据 SPEC-DM-006）
- [延后 CAD 校验与布局批量改名（PLAN-DM-008，已完成）](PLAN-DM-008-deferred-cad-validation-and-layout-rename.md)
- [v0.21 CAD 单脚本布局重建（PLAN-DM-007，已取消：范围由 PLAN-DM-008 吸收）](PLAN-DM-007-v021-cad-single-script-execution.md)
- [v0.21 受控图纸集编辑（PLAN-DM-006，已完成）](PLAN-DM-006-v021-controlled-sheetset-editing.md)
- [v0.2.1 紧急修复：运行时、日志与 AcSm 兼容性（PLAN-DM-005，已完成）](PLAN-DM-005-v0.2.1-runtime-logging-and-acsm-hotfix.md)
- [阶段 1：v0.2 稳定化与多 DWG 并行（PLAN-DM-001，已完成）](PLAN-DM-001-v0.2-stabilization-and-multi-dwg-parallel.md)
- [阶段 2：v0.3 日常编辑器（PLAN-DM-002，已完成）](PLAN-DM-002-v0.3-daily-editor.md)
- [阶段 3：v0.4 单人工作流（PLAN-DM-003，计划中）](PLAN-DM-003-v0.4-solo-workflow.md)
- [阶段 4：v1.0 Windows 产品化（PLAN-DM-004，计划中）](PLAN-DM-004-v1.0-windows-productization.md)

## 全局实施原则

- 始终保留 `DST → XML DOM → DST` 受控链路，不开放任意 XML、SCR 或 Shell 输入。
- 正式写入继续采用永久 before 快照、暂存校验、整批发布和失败回滚。
- 多 DWG 并行只发生在任务暂存区；DST 更新和正式发布必须集中、串行、原子执行。
- 同一工作区同一时刻只允许一个写任务；阶段 1 不开放多个通用 Worker 并发领队列。
- 所有真实 CAD 测试只操作私有样本的临时副本。
- 每个阶段都要先通过非 CAD 自动化测试，再执行 AutoCAD 2016/2020 系统测试。
- 新增功能必须包含错误码、日志、恢复路径和用户可理解的提示。
- v0.2.1 紧急修复未验收前，暂停 v0.3 日常编辑器功能开发，先恢复单实例运行和可信日志基线。

## 暂不纳入 v1.0

- 多用户、权限、SSO 和远程任务调度。
- RustFS、DM8、对象存储和跨机器 Worker。
- 任意 AutoCAD 命令、SCR 或 AcSm XML 编辑器。
- Word/PDF 成果生成、图框内容智能生成和模型空间重绘。
- AutoCAD 2025 及以上版本迁移，除非真实项目形成明确需求。
