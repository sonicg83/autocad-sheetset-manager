---
id: MEMO-DM-036
title: PLAN-DM-031 提交代码审查报告
status: final
owners:
  - dst-manager
created: 2026-09-15
updated: 2026-09-15
related:
  - PLAN-DM-031
  - ARCH-DM-001
document_kind: memo
---

# PLAN-DM-031 提交代码审查报告（MEMO-DM-036）

## 日期

2026-09-15

## 审查范围

- 基线 commit：`fab9174`
- 被审查范围：`fab9174..b9cfadf`
- 提交数量：11
- 主要改动：发布事务按 `attempt` 嵌套命名空间、旧平铺布局只读兼容、发布证据永久保留、`publisher.py` 职责拆分、测试拆分与文档归档。
- 审查性质：只读代码审查；未修改生产代码、测试代码或提交历史。

## 结论

本轮发现 3 项需跟进事项：1 项发布恢复正确性问题（P2）、1 项完成验证记录问题（P2）、1 项代码容量与计划收口问题（P3）。发布与恢复专项测试、Ruff 和 `git diff --check` 均通过，但不建议把当前提交范围视为“无遗留问题通过”：应优先修复嵌套 manifest 的 `attempt` 不可变校验，并更正 PLAN-DM-031 的验证与完成记录。

## 审查发现

### F1（P2）：manifest 的 `attempt` 损坏不会触发恢复错误

**位置：**

- `src/dst_manager/infrastructure/filesystem/publish_journal.py:51-70`
- `src/dst_manager/infrastructure/filesystem/publish_recovery.py:128-145`
- `src/dst_manager/infrastructure/filesystem/publish_recovery.py:217-236`

**事实：**

`immutable_transaction_projection()` 返回的不可变投影包含 `identity_version`、`operation_id`、`root`、`status` 与 `files`，但没有包含新布局的身份字段 `attempt`。启动恢复比较主 journal 与归档 manifest 时使用该投影，因此两者的 `attempt` 不一致不会触发 `PUBLISH_MANIFEST_IMMUTABLE_MISMATCH`。其后 `_list_committed_operations_locked()` 又会校验 manifest 的 `attempt` 是否等于目录名携带的 attempt；不一致时直接跳过该清单。

**最小复现：**

1. 以 `attempt=1` 正常发布并形成 `jobs/<job_id>/attempt-001/publish-journal.json` 与 `revisions/<job_id>/attempt-001/manifest.json`；
2. 仅把 manifest 中的 `"attempt"` 从 `1` 改为 `2`；
3. 调用 `recover()` 与 `list_committed_operations()`。

实际结果：

```text
{'recover': [], 'committed_count': 0}
```

`recover()` 没有报错，已提交清单却在枚举阶段被静默丢弃。数据库因而不能依据该 COMMITTED 证据完成闭环，也没有进入预期的明确隔离错误路径。

**建议：**

- 把 `attempt` 纳入 `immutable_transaction_projection()`；旧平铺布局两侧均为缺失值，不影响兼容比较。
- 增加回归测试：嵌套 manifest 的 `attempt` 与主 journal 或目录名不一致时，`recover()` 必须抛出 `PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")`，并保持原始证据不被覆盖。

### F2（P2）：局部测试被记录为“全量测试”，完成门禁证据不准确

**位置：**

- `.planning/plans/dst-manager/PLAN-DM-031-publisher-attempt-namespace-and-split.md:29`
- `.planning/plans/dst-manager/PLAN-DM-031-publisher-attempt-namespace-and-split.md:955-960`

**事实：**

计划 Global Constraints 要求交付前执行 `uv run pytest -q`。实际验证只记录了：

- `uv run pytest tests/unit -q`
- `uv run pytest tests/integration/test_api.py -q`

但该节将其表述为“全量测试”。这两条命令没有覆盖其余 integration、脚本与其他测试目录，不能作为仓库级全量门禁证据。

本轮按仓库约束通过 RTK 执行 `uv run pytest -q` 时出现 2 个失败：

- `tests/unit/test_setup_bat.py::test_2013_2014_mapped_to_2016_bucket_with_warning`
- `tests/unit/test_setup_bat.py::test_no_autocad_detected_leaves_keys_commented`

两个失败均为 `setup.bat` 中文输出的编码断言；`scripts/setup.bat` 与 `tests/unit/test_setup_bat.py` 不在 `fab9174..b9cfadf` 的改动范围内，因此没有证据表明它们是 PLAN-DM-031 引入的回归。该结果仍说明当前计划文档不能把局部测试记录为仓库级“全量测试”。

**建议：**

- 更正“全量测试”措辞，准确列出当时实际执行的测试范围。
- 在可复现项目标准控制台编码的环境中重新执行 `uv run pytest -q`；若仍失败，先处理或明确登记既有基线失败，再更新完成门禁证据。

### F3（P3）：拆分容量目标未完成，且没有建立正式后续计划

**位置：**

- `.planning/plans/dst-manager/PLAN-DM-031-publisher-attempt-namespace-and-split.md:18`
- `.planning/plans/dst-manager/PLAN-DM-031-publisher-attempt-namespace-and-split.md:30`
- `.planning/plans/dst-manager/PLAN-DM-031-publisher-attempt-namespace-and-split.md:962-964`

**事实：**

PLAN-DM-031 的 Goal 是把 `publisher.py` 拆回约 500 行，Global Constraints 允许编排核心在 500～600 行区间。当前实际行数为：

| 文件 | 行数 |
| --- | ---: |
| `src/dst_manager/infrastructure/filesystem/publisher.py` | 721 |
| `tests/unit/test_publisher.py` | 567 |
| `tests/unit/test_publish_recovery.py` | 887 |

计划已明确记录这一偏差，但在 `status: completed` 下只写“留作后续计划”。本轮搜索 `.planning/plans/` 与相关文档，没有找到承接剩余回滚/提交原语拆分的正式后续 Plan。

**建议：**

- 后续范围只拆 `publisher.py` 生产代码，不拆现有测试文件；测试仅为适配新的注入位置而做必要修改。
- 建立带文件范围、接口、测试与完成条件的正式后续 Plan，按下述推荐方案继续拆分；在该计划建立前，应把 PLAN-DM-031 明确视为经批准的阶段性交付，而不是没有承接项的延期备注。

#### F3 后续拆分推荐方案

采用“两个叶模块 + `publisher.py` 事务编排门面”：新增 `publish_apply.py` 承载正向文件应用和结果校验，新增 `publish_rollback.py` 承载回滚、恢复原语与替换备份清理。`publisher.py` 保留路径与 attempt 守卫、journal 构造和状态迁移、异常分流、归档、回调时序，以及 `recover/list/read` 门面。预计可把 `publisher.py` 从 721 行降至约 350 行，两个新模块均控制在 300 行以内。

不推荐只提取回滚逻辑：该方案只能把 `publisher.py` 压到约 500 行，仍混合事务编排与正向文件提交，几乎没有后续增长空间。不推荐本轮引入 `Committer`/`RollbackEngine` 类、Protocol 或抽象基类：当前被迁移方法除构造时注入的 `replace_file` 外均无实例状态，模块级函数更直接，且不会扩大接口与测试改造范围。

##### 模块职责

`publish_apply.py` 迁移以下职责：

- `verify_baselines`
- `verify_entry_baseline`
- `commit_create`
- `commit_existing`
- `commit_delete`
- `restore_captured_external`
- `capture_result`
- `verify_committed_results`

`publish_rollback.py` 迁移以下职责：

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

`publisher.py` 继续承担：

- 获取与释放 `WorkspaceTransactionLock`；
- 校验 `attempt` 并派生 jobs/revisions 命名空间；
- 检查当前 attempt 占用与跨 attempt COMMITTED 冲突；
- 构造 entries 与 journal；
- 驱动 `PREPARED → PUBLISHING → COMMITTED` 及失败/回滚状态迁移；
- 管理 `WindowsResultGuards`、归档、`before_commit` 和 `on_committed` 的严格时序；
- 保留 `recover()`、`list_committed_operations()`、`read_committed_operation()` 门面。

##### 依赖方向与接口

依赖方向固定为：

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

两个新模块不得反向 import `publisher.py`。正向提交模块使用显式参数接收唯一实例配置，例如：

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

为降低纯移动重构风险，`RecoverablePublisher` 本轮暂时保留 `_rollback()`、`_commit_existing()`、`_commit_delete()` 与 `_cleanup_replace_backups()` 等极薄私有委托，由委托调用新模块函数。这样 `publish_recovery.py` 的既有鸭子调用无需同时改造，当前基于实例方法的故障注入测试也可保持语义。待拆分稳定后，如确需移除委托，应另行评估，不与本轮纯重构混合。

##### 实施顺序

1. 记录当前 Ruff、发布专项测试与全量测试基线；F1 的 manifest `attempt` 修复必须作为独立行为提交，不与 F3 纯拆分提交混合。
2. 新增 `publish_apply.py`，逐字迁移正向提交及结果校验逻辑；除去 `self`、显式传递 `replace_file` 和增加薄委托外，不改变分支、异常类型、错误消息或调用顺序。
3. 新增 `publish_rollback.py`，逐字迁移回滚、身份保护与清理逻辑；保留 publisher 私有委托作为恢复与测试兼容层。
4. 枚举并核对现有故障注入点，重点覆盖 `_commit_existing`、`_commit_delete`、`_cleanup_replace_backups`、`replace_existing` 和 `move_no_replace`；只有实现不再经过 publisher 导入别名时，才把对应 monkeypatch 更新到新叶模块。
5. 分别提交“正向应用逻辑外移”和“回滚逻辑外移”，每个提交都独立运行 Ruff 与发布/恢复专项测试；最后运行仓库级 `uv run pytest -q`。

##### 完成门禁

- `publisher.py` 不超过 400 行；`publish_apply.py` 与 `publish_rollback.py` 各不超过 300 行。
- application 层现有 import 零改动；`RecoverablePublisher.publish/recover/list_committed_operations/read_committed_operation` 签名零改动。
- journal 字段、状态迁移、错误码、错误消息、before/manifest 布局、文件身份保护与回调时序零行为变化。
- 所有现有故障注入窗口继续生效，发布失败、进程崩溃、启动恢复、提交后清理与 Windows 平台守卫测试通过。
- `uv run ruff check .` 与仓库级 `uv run pytest -q` 通过；真实 AutoCAD 测试仍按环境显式启用规则执行。

## 验证记录

### 通过

```powershell
rtk git diff --check fab9174..b9cfadf
rtk uv run ruff check .
rtk uv run pytest tests/unit/test_publisher.py tests/unit/test_publish_recovery.py tests/unit/test_publish_guards.py tests/unit/test_publish_journal.py tests/unit/test_publish_primitives.py tests/integration/test_transaction_recovery.py -q
```

结果：差异格式检查通过；Ruff 输出 `All checks passed!`；发布、恢复、守卫、日志、原语与事务恢复专项测试无失败。

### 未通过及边界

```powershell
rtk uv run pytest -q
```

结果：上述两个 `test_setup_bat.py` 中文输出编码断言失败。相关生产文件和测试文件未被本提交范围修改；本报告不把它们归因为 PLAN-DM-031 回归，也不把仓库全量测试记录为通过。

真实 AutoCAD 系统测试未执行：本轮为提交代码审查，没有显式启用 `DST_MANAGER_RUN_AUTOCAD=1`，且发现项不涉及 SCR、Worker 插件命令或真实 CAD 布局重建。

## 待跟进事项

1. 修复 F1，并以 manifest `attempt` 篡改/损坏用例建立回归防线。
2. 更正 PLAN-DM-031 的“全量测试”及完成验证记录。
3. 按 F3 推荐方案为 `publisher.py` 生产代码的剩余拆分建立正式后续计划；现有测试文件不属于该拆分范围。
