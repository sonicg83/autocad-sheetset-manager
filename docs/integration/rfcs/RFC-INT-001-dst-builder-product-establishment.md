---
id: RFC-INT-001
title: DST Builder 立项与共享平台边界
status: superseded
owners:
  - integration
created: 2026-09-17
updated: 2026-09-21
related:
  - VISION-DB-001
  - PRD-DB-001
  - ARCH-DB-001
  - ARCH-INT-002
  - VISION-DM-001
  - ARCH-DM-001
  - VISION-LR-001
  - ARCH-LR-001
---

# DST Builder 立项与共享平台边界

> **历史说明（2026-09-21）：** 本 RFC 记录 DST Builder 的原始立项决策；该产品已按 [RFC-INT-003](RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md) 整体退场，“双产品壳”边界随之终止，本文仅作为历史决策正文保留，不再代表现行治理。现行治理以 [ARCH-INT-002](../architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md) 为唯一权威。

## 提案

将原 `legacy-refactor` 方向正式立项为独立产品 **DST Builder**，与 DST Manager 组成两个并列产品：

- DST Builder：从结构化项目数据生成首版 DWG、DST 和伴随成果；
- DST Manager：打开、检查、编辑、修订并安全发布既有 DST/DWG。

两者采用“共享平台、双产品壳”模式。共享层只接收已经被双方实际采用的稳定能力，不把任一产品的领域模型或页面状态机提前提升为公共抽象。

## 动机

原 `legacy-refactor` 文档以替换 PowerShell/WPF 旧链路为主叙事，包含内网多人控制面、旧实现迁移和插件全量替代等大范围目标。当前产品决策已经变化：

- 新产品具有正式名称和独立用户价值，不再只是技术重构项目；
- 首版应是单人本地桌面产品，同时保持未来服务化端口；
- 应用内项目模型是唯一事实源，Excel 降级为兼容输入和交换格式；
- 产品采用分步引导界面；
- 首版只闭环图纸集主生成链路；
- 产品从零设计，不承担旧运行时、旧数据库和旧 API 的兼容或降级责任。

继续沿用 `legacy-refactor` 名称和迁移型架构，会把历史实现错误地变成新产品约束。

## 影响范围

### 产品与生命周期

```text
DST Builder                         DST Manager
项目建模 → 预览 → 构建 → 发布 → 交接 → 检查 → 编辑 → 修订 → 安全发布
```

DST Builder 在正式交接前拥有唯一项目事实源和生成历史；DST Manager 从交接基线开始拥有后续维护历史。首版不进行隐式双向同步。

### 代码与部署

- 新产品包名为 `dst_builder`，分发名和命令为 `dst-builder`。
- 首版为 Windows 11 本地桌面应用，复用 Vue 3、WebView2、本地 API、SQLite 和 Core Console 技术方向。
- 不复制或分叉整个 DST Manager；Builder 创建独立领域、应用、接口和前端。
- 共享平台候选包括 AutoCAD 运行时、Core Console 安全执行、DST Codec/AcSm 契约、工作区、哈希、Artifact 和原子发布。
- 共享候选只有在两边形成真实消费方后才能进入公共包。

### 文档治理

- 当前产品 scope 由 `legacy-refactor` 变更为 `dst-builder`。
- 新正式文档使用 `DB` 前缀，例如 `VISION-DB-001`、`PRD-DB-001`、`ARCH-DB-001`。
- 已分配的 `LR` 编号永久保留，不重用、不改号；旧基线标记为 `superseded`。
- `legacy-refactor` 目录作为历史资料入口保留，不再接收当前产品需求、架构或计划。

## 迁移路径

1. 建立 `docs/dst-builder/`、`ROADMAP-DB-001` 和对应索引。
2. 用 `ARCH-INT-002` 取代旧双项目治理中的现役产品定义。
3. 将 `VISION-LR-001`、`ARCH-LR-001` 标记为 `superseded`，将计划类的 `ROADMAP-LR-001` 标记为 `cancelled`，正文保持历史可追溯。
4. 首个实现阶段先完成一条最小纵向生成闭环，不先搭建多人控制面或迁移外围插件。
5. 共享能力按真实复用逐项提取；禁止为潜在复用一次性拆分 DST Manager。

## 开放问题

当前无阻断立项的开放问题。首个纵向 Spec 仍需明确最小 AcSm 文档骨架、Builder CAD 作业协议和交接 JSON Schema 的字段级契约。

## 评审结论

2026-09-17 用户确认：

- 采用共享平台、双产品壳；
- 首版桌面交付、架构预留服务化；
- 应用内项目模型为唯一事实源；
- 交接后由 DST Manager 接管；
- 首版仅覆盖图纸集主生成链路；
- 绿地设计不保留旧实现回退，但保留事务安全；
- 正式文档切换为 `dst-builder` scope 和 `DB` 前缀。

本 RFC 据此接受。
