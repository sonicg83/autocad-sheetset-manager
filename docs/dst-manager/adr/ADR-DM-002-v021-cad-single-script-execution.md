---
id: ADR-DM-002
title: v0.21 CAD 单脚本布局重建
status: accepted
owners:
  - dst-manager
created: 2026-08-25
updated: 2026-08-25
related:
  - ARCH-DM-001
  - SPEC-DM-002
  - PLAN-DM-007
document_kind: adr
---

# v0.21 CAD 单脚本布局重建

## 背景

v0.21 的结构性图纸编辑以受影响 DWG 分组重建布局。原实现为每个分组先启动一次 Core Console 完成删除、导入、重命名和保存，再启动一个新进程重新打开暂存 DWG 获取布局 Handle。因此，受影响分组数为 `G` 时，生产路径会启动 `2G` 次 Core Console，并生成成对的 `rebuild-*.scr` 与 `handles-*.scr`。

Legacy 项目已在同一个 SCR 中先重建布局、再调用 `GetLayoutHandles`，证明这两个插件命令可以在同一 Core Console 会话内按固定顺序执行。重新启动进程只提供额外的独立打开验证，不是生成正确 Handle 的前置条件。

## 决策

结构性布局重建默认采用“一 DWG 分组、一份 SCR、一次 Core Console 执行”。生产 SCR 必须按以下固定顺序执行：

1. 准备暂存基础 DWG；
2. 设置 `FILEDIA`、`SECURELOAD`、`CMDECHO`；
3. `NETLOAD` 与目标 AutoCAD 版本匹配的固定插件；
4. 执行 `DstDeleteLayouts`；
5. 按最终顺序导入并重命名布局；
6. 执行 `DstDeleteDefaultLayout`；
7. 执行 `DstGetLayoutHandles`；
8. 恢复系统变量、`QSAVE`、`QUIT`；
9. Core Console 退出后，Python 解析 `.dst-handles.txt`，并校验布局名与非零、唯一 Handle 同执行计划一一对应。

正常生产任务不再为 Handle 获取额外启动新进程。模板布局检查保留独立的 Handle 枚举脚本；AutoCAD 2016/2020 系统验收和故障诊断仍须以新的 Core Console 进程重新打开最终暂存 DWG，独立验证布局与 Handle。

不提供双脚本/单脚本运行时配置开关。两种路径会扩大测试矩阵、日志解释和故障恢复面；如未来真实 CAD 证据证明单脚本不可靠，应新增 ADR，而非以隐式开关回退。

## 备选方案

### 保留两次 Core Console 调用

该方案保留独立重新打开验证，但每个重建分组都承担一次额外的进程启动、插件加载和 DWG 打开成本；Legacy 实践已表明该成本不是获取 Handle 的必要条件。

### 通过配置开关同时支持两种生产路径

该方案会使同一变更计划产生两套运行时行为，并使错误注入、事务回滚、性能统计和用户日志都需要按开关分支维护，收益不足以抵消复杂度。

## 影响

- 生产路径的 Core Console 调用数从 `2G` 降为 `G`；实际墙钟时间仍须由不同布局规模、AutoCAD 版本和并行度的系统测试测量，不承诺按比例减半。
- `DstGetLayoutHandles` 的输出、解析、唯一性/非零性校验、DST 写入、暂存发布、永久 before 快照和整批回滚语义保持不变。
- 执行日志与脚本清单应能证明每个分组只执行 `rebuild-*.scr`，不再产生生产用的 `handles-*.scr`。
- 独立新进程重开从生产必要步骤调整为双版本验收和诊断手段；其失败仍应阻止相应验收结论，但不改变正常任务的单次执行粒度。

## 替代关系

本 ADR 替代 `ARCH-DM-001` 第 6.3 节中“第二次用 Core Console 打开最终暂存 DWG 获取 Handle”的生产流程描述，并补充该架构基线的第 12.2 节。它不替代 `ADR-DM-001` 的受控编辑决策，也不改变 `ARCH-DM-001` 中的 AutoCAD 双版本、DST/XML 受控修改或发布事务边界。

## 实施与验证边界

在私有样本可用时，按 `PLAN-DM-007` 记录旧路径 `2G` 调用基线，以及新路径在 1、2、25 布局分组和不同 `cad_max_parallel` 下的调用数、单 DWG `duration_ms` 与整批墙钟时间。公开隔离工作树缺少私有样本时，调用数公式可由编排器的两次 `executor.run()` 旧实现及单次调用新实现验证；真实性能结论须待 2016/2020 系统测试恢复后补充。
