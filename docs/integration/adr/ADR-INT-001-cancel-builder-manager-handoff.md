---
id: ADR-INT-001
title: 取消 Builder 与 Manager 的显式交接契约
status: accepted
owners:
  - integration
created: 2026-09-18
updated: 2026-09-18
related:
  - RFC-INT-002
  - ARCH-INT-002
  - RFC-INT-001
  - SPEC-DB-001
document_kind: adr
---

# 取消 Builder 与 Manager 的显式交接契约

## 背景

`ARCH-INT-002` §6 原规定：Builder 通过版本化 `HandoffBundle` 向 Manager 交接，Manager 验证成果清单与哈希后创建自己的初始修订。该契约由 `SPEC-DB-001` §10 固定为六步流程。

真实流程是「Builder 在项目开始时生成框架 → 用户在 AutoCAD 中长期画图与编辑 → Manager 承担中后期的结构调整与成果交付」。交接的三项准入条件——manifest 登记文件大小与 SHA-256 逐一相符、成果包内不得存在未登记文件、DST 引用只落在 `drawings/` 内——都要求成果包自发布起保持字节不变，而人工编辑期必然破坏这一前提。

此外，交接成功后 Manager 的修订目录与发布目标都落在成果包根内（`.dst-manager/` 与包内 `drawings/*.dwg`），「成果包不可变」的语义在交接瞬间即自毁。

## 决策

取消 Builder 向 Manager 的显式交接契约。两条产品线以 DST 文件为唯一接口：

- Builder 把 `sheetset.dst`、构建后的 DWG 与 `图纸目录.xlsx` 发布到一个新建目标目录，构建成功即交付完成，不再产出清单、哈希或来源元数据；
- Manager 通过既有的 `POST /api/workspaces/open` 打开该 DST，从磁盘现状建立工作区与基线。

正式成果包不再有 `metadata/` 目录，也不再保留 `drawings/` 包装层。

## 备选方案

- **保留交接但降级为「接管现状快照」**：保留 provenance 记录，取消字节相符的准入条件。未采用，因为 Builder 的生成历史（`build_id` / `plan_id`）在真实流程中没有确认的消费者，而保留它需要维护跨产品包级字段与两侧契约测试。
- **保留交接并文档化其窄适用条件**：在包已被人工改动时返回可执行指引改用 `/api/workspaces/open`。未采用，因为该场景在真实流程中是常态而非例外，等于把「用户会撞错」当作设计前提。
- **只取消交接，保留成果包 `metadata/`**：未采用，因为 `manifest.json` 与 `handoff.json` 的唯一消费方就是交接，取消交接后五个 metadata 文件全部失去程序消费方。

## 影响

- Manager 侧净删交接实现 616 行、Builder 侧 60 行；测试删除 1,206 行；`handoff_sources` 表通过新迁移删除。
- `document_revisions.kind` 与 `source_json` 保留为通用修订元数据。
- Manager 不再对同一台机器上同一用户产出的文件做硬拒绝，行为回到「打开并报告诊断」，与其通用路径一致。
- Builder 的 `verify_package` 语义由「manifest 自声明的哈希链」改为「预期产物集合存在、可读、非空」。校验职责只剩确认产物写成功，因为发布原子性已由同卷 `os.replace` 保证。该改动同时消除一个既有缺陷：原判定要求成果根只有 `drawings/` 与 `metadata/` 两个目录，用户往成果根放入任何文件都会让后续启动恢复误报 `PUBLISH_RECOVERY_REQUIRED`。
- Manager 失去 `kind=handoff_initial` 的永久初始修订；首次编辑的基线仍由操作前快照保留。若将来需要「接管时的原始状态」，正确做法是在 Manager 侧新增显式的「建立初始修订」操作。

## 替代关系

本 ADR 取代 `ARCH-INT-002` §6「交接边界」原结论，并取代 `RFC-INT-001` 中与本决策冲突的表述：

- 产品生命周期链中的「发布 → 交接 → 检查 → 编辑」改为「发布」结束后由 Manager 直接打开 DST；
- 「DST Builder 在正式交接前拥有唯一项目事实源」不再成立——人工 AutoCAD 编辑期既不属于 Builder 的项目事实源，也不属于 Manager 的维护历史。

`RFC-INT-001` 正文不改写，保留为 2026-09-17 的决策记录；本 ADR 是其交接相关部分的取代依据。
