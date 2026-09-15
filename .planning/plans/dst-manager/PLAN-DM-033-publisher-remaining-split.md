---
id: PLAN-DM-033
title: publisher 生产代码剩余拆分实施计划（publish_apply 与 publish_rollback）
status: proposed
owners:
  - dst-manager
created: 2026-09-15
updated: 2026-09-15
related:
  - PLAN-DM-031
  - ARCH-DM-001
  - MEMO-DM-036
---

# publisher 生产代码剩余拆分实施计划（publish_apply 与 publish_rollback）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 PLAN-DM-031 未竟的容量目标：把 `publisher.py`（721 行）拆回容量契约区间。采用「两个叶模块 + 编排门面」方案——新增 `publish_apply.py` 承载正向文件应用与结果校验，新增 `publish_rollback.py` 承载回滚、身份保护与替换备份清理；`publisher.py` 只保留事务编排与公共门面，目标不超过 400 行，两个新模块各不超过 300 行。

**Architecture:** 纯移动重构。`publish_apply.py` 与 `publish_rollback.py` 为无实例状态的模块级函数集合（被迁移方法除构造时注入的 `replace_file` 外均无实例状态，不引入 `Committer`/`RollbackEngine` 类、Protocol 或抽象基类），以显式参数接收唯一实例配置；`publisher.py` 保留路径与 attempt 守卫、journal 构造与状态迁移、异常分流、归档、回调时序以及 `recover`/`list_committed_operations`/`read_committed_operation` 门面，并暂时保留 `_rollback()`、`_commit_existing()`、`_commit_delete()`、`_cleanup_replace_backups()` 等极薄私有委托调用新模块函数，维持 `publish_recovery.py` 的鸭子调用与既有故障注入测试语义。两个新模块不得反向 import `publisher.py`。

**Tech Stack:** Python 3.12 + UV；pytest；ruff。

**Spec:** 承接 MEMO-DM-036（[2026-09-15-plan-dm031-code-review.md](../../memos/dst-manager/2026-09-15-plan-dm031-code-review.md)）F3 的经用户确认推荐方案；补齐 [PLAN-DM-031](PLAN-DM-031-publisher-attempt-namespace-and-split.md) 偏差说明中「留作后续计划」的正式承接项。本计划只拆 `publisher.py` 生产代码，不拆现有测试文件；测试仅为适配新的注入位置做必要修改。

## Global Constraints

- 纯移动重构：除 `self`、显式传递 `replace_file` 和新增薄委托外，不改变分支、异常类型、错误消息或调用顺序；journal 字段、状态迁移、错误码、错误消息、before/manifest 布局、文件身份保护与回调时序零行为变化。
- application 层现有 import 零改动；`RecoverablePublisher.publish/recover/list_committed_operations/read_committed_operation` 签名零改动。
- 依赖方向固定（见下节），两个新模块不得反向 import `publisher.py`。
- 现有测试文件不做结构性拆分，仅在故障注入点不再经过 publisher 导入别名时，把对应 monkeypatch 更新到新叶模块。
- 行为修复（如 MEMO-DM-036 F1）必须独立提交，不与本计划纯拆分提交混合。
- Python 命令统一使用 `uv run`；每个提交独立运行 `uv run ruff check .` 与发布/恢复专项测试；收尾运行仓库级 `uv run pytest -q`。
- 工作区可能已有用户改动；每次提交只允许显式暂存本任务列出的文件，禁止宽泛暂存。
- 修改发布事务前阅读 `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md` 发布事务与启动恢复章节。

## 模块职责

### `publish_apply.py` 迁移职责

- `verify_baselines`
- `verify_entry_baseline`
- `commit_create`
- `commit_existing`
- `commit_delete`
- `restore_captured_external`
- `capture_result`
- `verify_committed_results`

### `publish_rollback.py` 迁移职责

- `rollback`
- `restore_entry`
- `restore_backup_by_rename`
- `publish_source_still_owned`
- `cleanup_publish_source`
- `checked_replacement_backup`
- `checked_before_snapshot`
- `published_identities`
- `cleanup_replace_backups`
- `unlink_owned`

### `publisher.py` 继续承担

- 获取与释放 `WorkspaceTransactionLock`；
- 校验 `attempt` 并派生 jobs/revisions 嵌套命名空间；
- 检查当前 attempt 占用与跨 attempt COMMITTED 冲突；
- 构造 entries 与 journal；
- 驱动 `PREPARED → PUBLISHING → COMMITTED` 及失败/回滚状态迁移；
- 管理 `WindowsResultGuards`、归档、`before_commit` 和 `on_committed` 的严格时序；
- 保留 `recover()`、`list_committed_operations()`、`read_committed_operation()` 门面。

## 依赖方向与接口

```text
publisher
  ├─ publish_apply
  ├─ publish_rollback
  ├─ publish_recovery
  ├─ publish_journal
  └─ publish_primitives

publish_apply
  └─ publish_errors + publish_primitives

publish_rollback
  └─ publish_errors + publish_journal + publish_primitives
```

正向提交模块使用显式参数接收唯一实例配置，例如：

```python
commit_create(entry, publish_temp, *, replace_file=None)
commit_existing(entry, publish_temp, operation_uid, *, replace_file=None)
commit_delete(entry)
```

回滚模块保持无状态函数接口，例如：

```python
rollback(journal_path, journal, entries)
cleanup_replace_backups(entries)
```

为降低纯移动重构风险，`RecoverablePublisher` 本轮暂时保留 `_rollback()`、`_commit_existing()`、`_commit_delete()` 与 `_cleanup_replace_backups()` 等极薄私有委托，由委托调用新模块函数。待拆分稳定后，如确需移除委托，应另行评估，不与本轮纯重构混合。

## 任务分解

### Task 1: 基线记录

**Files:** 无代码改动。

- [ ] 记录当前基线：`uv run ruff check .`、发布/恢复专项测试（`tests/unit/test_publisher.py tests/unit/test_publish_recovery.py tests/unit/test_publish_guards.py tests/unit/test_publish_journal.py tests/unit/test_publish_primitives.py tests/integration/test_transaction_recovery.py`）与仓库级 `uv run pytest -q`。
- [ ] 确认 MEMO-DM-036 F1 的 manifest `attempt` 修复已作为独立行为提交合入（commit `9b4f831`），不与本计划混合。
- [ ] 用 `Measure-Object -Line` 记录 `publisher.py`（721 行，2026-09-15）与既有模块行数，作为完成门禁对照。

### Task 2: 正向应用逻辑外移（`publish_apply.py`）

**Files:**
- Create: `src/dst_manager/infrastructure/filesystem/publish_apply.py`
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`（删除迁移体、新增 import 与薄委托）
- Modify: 相关测试仅适配故障注入位置（见 Task 4）

- [ ] 新增 `publish_apply.py`，逐字迁移 `verify_baselines`、`verify_entry_baseline`、`commit_create`、`commit_existing`、`commit_delete`、`restore_captured_external`、`capture_result`、`verify_committed_results`；除去 `self`、显式传递 `replace_file` 外不改任何分支、异常类型、错误消息或调用顺序。
- [ ] `publisher.py` 改为调用新模块函数；为 `_commit_existing()`、`_commit_delete()` 等既有故障注入路径保留极薄私有委托。
- [ ] 运行 Ruff 与发布/恢复专项测试，全绿后提交：`refactor: 发布正向应用与结果校验外移到 publish_apply 模块（纯移动）`。

### Task 3: 回滚逻辑外移（`publish_rollback.py`）

**Files:**
- Create: `src/dst_manager/infrastructure/filesystem/publish_rollback.py`
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`

- [ ] 新增 `publish_rollback.py`，逐字迁移 `rollback`、`restore_entry`、`restore_backup_by_rename`、`publish_source_still_owned`、`cleanup_publish_source`、`checked_replacement_backup`、`checked_before_snapshot`、`published_identities`、`cleanup_replace_backups`、`unlink_owned`；保留 publisher 私有委托作为恢复与测试兼容层。
- [ ] 运行 Ruff 与发布/恢复专项测试，全绿后提交：`refactor: 发布回滚、身份保护与清理逻辑外移到 publish_rollback 模块（纯移动）`。

### Task 4: 故障注入点核对与测试适配

**Files:**
- Modify: 仅有必要的测试文件（预期 `tests/unit/test_publisher.py` 或 `tests/unit/test_publish_recovery.py` 的个别 monkeypatch 目标）

- [ ] 枚举现有故障注入点，重点核对 `_commit_existing`、`_commit_delete`、`_cleanup_replace_backups`、`replace_existing`、`move_no_replace`。
- [ ] 仅当实现不再经过 publisher 导入别名时，把对应 monkeypatch 更新到新叶模块；不改测试结构、不删用例。
- [ ] 运行 Ruff 与发布/恢复专项测试，全绿后提交（如无适配则记录零改动）。

### Task 5: 收尾验证与归档

**Files:**
- Modify: `changelog.md`、`.planning/plans/dst-manager/README.md`、本文件（status → `completed` 并记录实际验证）

- [ ] 行数门禁核对：`publisher.py` ≤ 400 行；`publish_apply.py`、`publish_rollback.py` 各 ≤ 300 行。
- [ ] 接口核对：application 层 import 零改动；`RecoverablePublisher` 公共方法签名零改动。
- [ ] Run: `uv run ruff check .`；Run: `uv run pytest -q`；Expected: 全绿。
- [ ] 更新 changelog、plans 索引与本计划状态，提交：`docs: PLAN-DM-033 publisher 剩余拆分完成归档`。

## 风险与回退

- **故障注入窗口失效**：薄委托的存在使基于实例方法的 monkeypatch 继续生效；仅别名直连的注入需要改指新模块。缓解：Task 4 逐一枚举注入点。
- **鸭子调用断裂**：`publish_recovery.py` 以 `publisher._rollback` 等鸭子类型调用；薄委托保证其不变，且 `publish_recovery` 不 import `publisher` 的依赖方向不动。
- **回退方式**：Task 2、Task 3 独立提交，可单独 revert；全程零行为变化，出现行为差异即回退该提交。

## 完成门禁

- `publisher.py` 不超过 400 行；`publish_apply.py` 与 `publish_rollback.py` 各不超过 300 行。
- application 层现有 import 零改动；`RecoverablePublisher.publish/recover/list_committed_operations/read_committed_operation` 签名零改动。
- journal 字段、状态迁移、错误码、错误消息、before/manifest 布局、文件身份保护与回调时序零行为变化。
- 所有现有故障注入窗口继续生效；发布失败、进程崩溃、启动恢复、提交后清理与 Windows 平台守卫测试通过。
- `uv run ruff check .` 与仓库级 `uv run pytest -q` 通过；真实 AutoCAD 测试仍按环境显式启用规则执行。
