---
id: ROADMAP-DB-001
title: DST Builder 路线图
status: cancelled
owners:
  - dst-builder
created: 2026-09-17
updated: 2026-09-21
related:
  - VISION-DB-001
  - PRD-DB-001
  - ARCH-DB-001
  - RFC-INT-001
  - SPEC-DB-001
  - PLAN-DB-001
  - RFC-INT-002
  - RFC-INT-003
  - ADR-INT-001
---

# DST Builder 路线图

> **取消说明（2026-09-21）：** 本路线图因产品方向终止而取消——[RFC-INT-003](../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md) 接受 DST Builder 退场，不代表实施失败；阶段 1 的实施与自动化开发门禁已全部通过，仅真实双版本发布资格未执行。替代方向见 RFC-INT-003、PLAN-DM-035 与 PLAN-DM-036。正文按历史记录保留。

本路线图描述已批准的产品阶段，不代表代码已经实施。每个阶段必须先建立对应 Spec 和 Plan，并以前一阶段的真实验证证据为输入。

## 目标阶段

### 阶段 0：产品正式立项

- 建立 `dst-builder` scope、`DB` 编号、产品愿景、PRD 和绿地架构基线。
- 固化 Builder、Manager 与共享平台边界。
- 保留并标记 `LR` 历史基线，建立黄金样本和旧规则清单。

退出条件：产品边界、首版范围、术语和验收口径全部明确。

### 阶段 1：最小生成闭环

支持一个项目、一种规则、一个图纸组和一个输出 DWG，完整贯通向导录入、计划、DWG、Handle、DST、成果包和 Manager 打开。

实施依据：[SPEC-DB-001](../../docs/dst-builder/specs/SPEC-DB-001-minimal-generation-loop.md) 与 [PLAN-DB-001](../plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md)。

退出条件：AutoCAD 2016/2020 均通过真实结果验收，运行时不依赖 Legacy 代码。

### 阶段 2：项目编辑器与规则系统

- 项目草稿与不可变修订；
- 图纸分组、展开、编号和命名；
- 字段定义、字典和批量粘贴；
- Excel 兼容导入；
- 向导前三个步骤完整可用。

退出条件：黄金样本的纯业务输入能够稳定转换为确定性项目修订。

### 阶段 3：模板、资产与完整计划

- 模板目录、内容哈希和资产纳管；
- 基础 DWG、布局、图幅及附带资产；
- 构建前检查与完整 `GenerationPlan`；
- 缺失依赖与版本兼容诊断。

退出条件：所有可静态发现的问题都能在 AutoCAD 启动前报告。

### 阶段 4：生产级构建与发布

- 多 DWG 有界并行；
- 取消、超时、重试和启动恢复；
- AcSm DOM 全新生成；
- Artifact 校验和原子发布；
- 固定 `sheetset.dst`、构建后的 DWG 与 `图纸目录.xlsx` 直接位于目标目录的扁平成果契约。

退出条件：故障矩阵证明不会发布半成品，标准黄金项目能够重复生成。

### 阶段 5：产品化与交付

- 绿色包、诊断工具和真实桌面验收；
- 首个可正式使用版本。

退出条件：打包后的 Builder 使用真实工程完成创建、构建、验收，并在 DST Manager 中打开已发布 DST。

## 交付结果

- 独立 DST Builder 桌面产品；
- 可复现的项目修订、计划、构建和成果记录；
- 可脱离 Builder 使用的成果目录（目标目录本身即交付边界）；
- 经两个 AutoCAD 版本和真实桌面验证的发布证据。

## 依赖

- 可合法用于测试的最小与标准黄金样本；
- AutoCAD 2016/2020 Core Console 与对应 Worker 构建环境；
- DST Manager 保持稳定的 DST 打开与校验入口（直接打开成果目录中的 DST，不依赖交接基线或初始修订）；
- 每项共享能力有两个真实消费方后再提取。

## 退出条件

每个阶段必须记录自动测试、真实 CAD、桌面验收、失败恢复和未执行检查。缺少真实 AutoCAD 或官方 Sheet Set Manager 证据时，不得把相关阶段标记为完成。
