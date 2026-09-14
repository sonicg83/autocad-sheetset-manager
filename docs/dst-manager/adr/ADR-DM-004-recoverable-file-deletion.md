---
id: ADR-DM-004
title: 正式工程文件删除纳入可恢复发布事务
status: accepted
document_kind: adr
owners:
  - dst-manager
created: 2026-09-01
updated: 2026-09-14
related:
  - ARCH-DM-001
  - ADR-DM-001
  - SPEC-DM-005
  - PLAN-DM-002
---

# 正式工程文件删除纳入可恢复发布事务

## 背景

`delete_subset` 同时删除 DST 中完整 `AcSmSubset` 子树和对应主 DWG。只替换 DST 会留下孤立 DWG，只删除 DWG 则可能留下无法打开的图纸引用；两者必须属于同一批可恢复发布。既有 `RecoverablePublisher` 已支持以 `staged=None` 表示删除，并具备永久 before、同步 journal、逐文件提交、逆序回滚和启动恢复能力，需要把该能力确认为正式契约，而不是仅作为内部实现细节。

## 决策

- 发布清单的每个目标只有 `create`、`replace`、`delete` 三种结果语义；删除以 `staged=null` 表示，目标在预览与执行时都必须存在并绑定内容哈希和文件身份。
- 删除目标与替换目标使用同一个 `operation_id`、同一个 `publish-journal.json` 和同一个 `COMMITTED` 闸门。不能先提交 DST 再单独删除 DWG。
- 提交前，把每个既有目标复制到永久 `revisions/<operation-id>/before/<relative-path>` 并复核哈希；删除文件的 before 副本与替换文件同等永久保留。
- journal 必须记录目标、before 路径/哈希/身份、操作 API 状态和最终结果。删除成功的 `result_hash` 为 `null`，启动恢复据此要求目标保持不存在。
- 中途故障按已尝试条目逆序恢复：删除目标从永久 before 恢复，替换目标恢复旧版本，新建目标移除。任何恢复结果无法证明时进入 `NEEDS_REVIEW`，不得继续编辑或自动重跑。
- `COMMITTED` 后才允许写入 SQLite 修订索引；归档或 SQLite 闭环失败不得回滚已经提交且可由 journal 证明的文件结果，启动恢复负责补齐或隔离。
- 所有目标必须位于规范化工作区根内；基准漂移、锁冲突、目标意外消失/出现、同卷发布临时文件冲突均阻断整批发布。

## 备选方案

- 将 DWG 移入回收站：跨环境行为和恢复标识不稳定，不能形成确定性事务清单。
- 先删除 DWG、再替换 DST：崩溃窗口会留下断链 DST。
- 仅在 DST 中移除子集并保留 DWG：不符合用户确认的整体删除语义。
- 删除前扫描工程外部引用：无法证明完整性，产生虚假安全保证。

## 影响

- `delete_subset` 可以复用既有发布器，不需要新的旁路删除 API。
- 磁盘预算必须包含待删除文件的永久 before 副本。
- 修订恢复将删除结果解释为“从 before 重新创建目标”，并继续受当前结果基准检查约束。
- 工程外部引用仍由用户确认承担；内部 AcSm ID 引用与存活图纸 DWG 引用属于发布前阻断规则。

## 替代关系

本 ADR 细化 `ARCH-DM-001` 第 8 节的多文件事务语义；不替代其永久修订、文件锁和启动恢复要求。

## 补记（2026-09-14）：同一 `operation_id` 重试时的修订目录复用契约

`retry_job` 复用 `job_id`，发布器又以 `job_id` 作为 `operation_id`，因此回滚后的重试必然第二次面对 `revisions/<operation-id>/`。上述决策（同一 `operation_id`、永久 `before`、`COMMITTED` 闸门、无法证明即 `NEEDS_REVIEW`）**不变**，仅补充复用前提：

- 重试可在**证明上一次尝试已整批回到发布前状态**时复用既有修订目录：`before` 快照与当前正式文件基准（哈希与文件身份）逐字节相同，才允许复用并按需覆盖；与基准逐字节相同的残留 `.<名称>.<operation_id>.replaced` 替换备份属冗余副本，可在持锁发布器内回收。回收只发生在已证明一致之后，不做猜测性清理，也不删除无法证明的残留。
- `manifest.json` 已存在（即该 `operation_id` 已有已提交修订）或证据不足时一律拒绝复用，返回 `PUBLISH_OPERATION_CONFLICT` 并进入 `NEEDS_REVIEW` 人工复核，**不得自动重跑**（避免覆盖已提交修订历史或把半发布状态当成基准）。
- 重试覆盖前，上一次尝试的 `publish-journal.json` 必须复制留档到 `revisions/<operation-id>/superseded-journals/publish-journal.<NNN>.json`：journal 是文件级证据的唯一载体，不得因重试静默丢失。用复制而非移动，使「回收完成但新 `PREPARED` 未写入」的崩溃窗口下启动恢复仍能看到旧日志。

## 补记（2026-09-14，第二次）：修订目录复用契约已被 attempt 嵌套命名空间取代（PLAN-DM-031）

上一节「补记（2026-09-14）：同一 `operation_id` 重试时的修订目录复用契约」中与目录复用相关的机制**自本补记起全部废止**，原文保留于上文仅作历史记录，不再构成现行契约。

`retry_job` 复用 `job_id`（即发布器的 `operation_id`）这一事实不变，但 PLAN-DM-031 引入 attempt 嵌套命名空间后，每次重试永远写入严格递增的新 attempt 目录——`revisions/<job_id>/attempt-NNN/` 与 `jobs/<job_id>/attempt-NNN/`（`NNN` 为三位零填充的 attempt 序号）——不再存在「重试第二次面对同一修订目录」的前提。据此：

- 上一补记的三个机制已全部删除：重试不再复用既有修订目录（故「证明一致后按需覆盖」的前提消失）；与基准逐字节相同的 `.<名称>.<operation_id>.replaced` 替换备份不再回收（临时文件与替换备份改按 `job~attempt` 命名，跨 attempt 天然隔离，无需回收旧副本）；`superseded-journals/` 留档机制整体删除（每个 attempt 有独立的 `publish-journal.json`，覆盖场景不复存在）。
- 「与基准逐字节相同的替换备份属冗余副本、可回收」的表述同时废止：它与本 ADR 决策中 before 快照与证据永久保留的契约直接冲突。现行契约为：**所有 attempt** 的 `publish-journal.json`、`before` 快照与终态记录一律永久保留，发布路径不存在自动清扫；磁盘保留策略须未来通过独立 ADR 与显式维护命令立项。
- 上一补记中仍然有效并被强化的部分：`manifest.json` 已存在（该 `operation_id` 已有已提交修订，现覆盖同一 job 的任一新旧布局 manifest）或当前 attempt 的发布命名空间已被占用时，一律拒绝发布，返回 `PUBLISH_OPERATION_CONFLICT` 并进入 `NEEDS_REVIEW` 人工复核，不得自动重跑。
