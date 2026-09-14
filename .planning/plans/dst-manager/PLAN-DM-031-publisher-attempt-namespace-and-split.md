---
id: PLAN-DM-031
title: 发布事务按 attempt 嵌套命名空间并拆分 publisher 模块实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-14
updated: 2026-09-14
related:
  - ARCH-DM-001
  - PLAN-DM-028
---

# 发布事务按 attempt 嵌套命名空间并拆分 publisher 模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把发布事务的磁盘命名空间从 `revisions/<job_id>`（job 与 attempt 混用）改为 `revisions/<job_id>/attempt-NNN`（嵌套），从而整体删除 `_reclaim_previous_attempt` 证据回收机制；随后把 1077 行的 `publisher.py` 按职责拆分为 4 个同层模块，使其回到 500 行软上限附近。

**Architecture:** 发布器新增必填关键字参数 `attempt`，日志路径嵌套到 `jobs/<job_id>/attempt-NNN/`、修订目录嵌套到 `revisions/<job_id>/attempt-NNN/`；`journal["operation_id"]` 保持等于 `job_id`（启动恢复与隔离逻辑直接拿它查数据库），新增 `journal["attempt"]` 字段用于重建修订目录。重试永远写入新的 attempt 目录，回收机制降级为「按日志终态清扫旧 attempt 目录」。拆分为纯移动重构：异常 → `publish_errors.py`，无状态原语 → `publish_primitives.py`，日志读写 → `publish_journal.py`，启动恢复 → `publish_recovery.py`，`publisher.py` 保留编排门面并 re-export 既有公共名。

**Tech Stack:** Python 3.12 + UV；pytest；ruff。

**Spec:** 本计划实现两份评审结论：commit `ea5072b` 代码评审发现 #8（机制级修法）与 #9（AGENTS.md 容量契约），以及 PLAN-DM-031 讨论中确认的嵌套方案。

## Global Constraints

- 所有命令使用 `uv run` 前缀（AGENTS.md 第 36 行）；Windows 11 + PowerShell 环境。
- 交付前必须通过 `uv run ruff check .` 与 `uv run pytest -q`（AGENTS.md 第 84-85 行）。
- 单个源文件约 500 行软上限（AGENTS.md 第 53 行）；拆分后 `publisher.py` 编排核心允许在 500-600 行区间。
- 拆分必须保持既有公共接口、错误码与序列化契约不变（AGENTS.md 第 56 行）：`publisher.py` 继续 re-export 全部异常类与 `ExpectedFileBaseline`、`capture_file_baseline`、`file_sha256`，application 层既有 import 一律不改。
- 代码注释、commit message 使用简体中文（AGENTS.md 第 8-9 行）。
- 发布安全相关改动，执行前阅读 `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md` 中发布事务与启动恢复章节。
- 每个任务结束时测试必须全绿，才允许 commit；禁止把行为变更与拆分混入同一 commit。

## 背景事实（执行者必读）

1. `publisher.publish()` 现有 5 个调用点，第一个位置参数当前传的都是数据库 job_id：
   - `src/dst_manager/application/cad_job.py:336`（传 `job_id`，作用域内有 `attempt` 变量，来自 `JobRow.attempt`，重试时严格递增）
   - `src/dst_manager/application/editing.py:292`（`operation_id = job_id`，:232）
   - `src/dst_manager/application/repair.py:165`（`operation_id = job_id`，:93）
   - `src/dst_manager/application/revisions.py:207`（传 `job_id`）
   - `src/dst_manager/application/xml_io.py:202`（传 `job_id`）
2. 只有 change_set 任务可重试（`database.py:487` `retry_job` 校验 `_is_cad_change_set`），因此只有 cad_job 的 attempt 会大于 1；其余四类任务恒传 `attempt=1`。
3. `journal["operation_id"]` 被 `application/recovery.py:42-43` 直接用于 `database.get_job(operation_id)`，被 `list_committed_operations` 用作去重键，被 `revisions.py:215` 拼进 `record_id = f"restore-{job_id}"`——**该字段必须保持等于 job_id，不得改成 attempt 派生串**。
4. 消费发布日志路径的三处（本计划全部要改）：
   - `publisher.py:946` `_recover_locked` 的 `jobs.glob("*/publish-journal.json")`
   - `publisher.py:1054` `_list_committed_operations_locked` 的 `revisions.glob("*/manifest.json")`
   - `application/recovery.py:122` `_quarantine_unproven_publish_jobs` 的 `jobs_root.glob("*/publish-journal.json")`
5. `application/recovery.py:97` 在启动恢复闭环时按 `revisions/<operation_id>` 重建 `revision_dir` 传给 `database.finalize_committed_job`——新布局下必须按 `journal["attempt"]` 重建嵌套路径。
6. `cad_job.py:202` 已在 `revisions/<job_id>/plan` 写规划文件：嵌套布局与该目录天然共存（`plan/` 与 `attempt-NNN/` 平级），无需迁移。
7. `revisions/<job_id>/manifest.json` 只在 COMMITTED 后存在（不可变归档）；被重试的任务必然是 ROLLED_BACK/FAILED，所以「同 job_id 嵌套后旧平铺残留」与「新 attempt 目录」互不冲突。
8. 测试基线：`tests/unit/test_publisher.py`（约 1815 行）全部是模块级测试函数（无测试类）；重试回收相关测试在 :1637-1815。

## 新磁盘布局与 journal 契约（权威定义）

```
.dst-manager/
  jobs/<job_id>/attempt-NNN/publish-journal.json      # 新布局（NNN = f"{attempt:03d}"）
  jobs/<job_id>/publish-journal.json                  # 旧布局，只读兼容
  revisions/<job_id>/attempt-NNN/{before/, manifest.json, publish-journal.json}
  revisions/<job_id>/manifest.json                    # 旧布局 COMMITTED 归档，只读兼容
  revisions/<job_id>/plan/                            # cad_job 规划目录，位置不变
```

- journal 新增字段 `"attempt": <int>`；`"operation_id"` 字段语义不变（= job_id）；`identity_version` 保持 1（files 向量格式未变；日志位置属外部布局，不入不可变投影）。
- 每目标临时文件名使用 attempt 限定串 `uid = f"{job_id}~{attempt:03d}"`：`.{name}.{uid}.tmp`、`.{name}.{uid}.replaced`、`.{name}.{uid}.conflict-published`。
- 不支持降级：旧版本程序读不到嵌套日志。升版前须确认用户工作区无进行中任务。

---

### Task 1: 发布日志与清单的兼容读取（双 glob，行为不变）

先让所有「读」侧同时认识新旧两种布局。本任务不改任何写入路径，既有测试必须全绿。

**Files:**
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`（`_recover_locked` :945-1039、`_list_committed_operations_locked` :1051-1068）
- Modify: `src/dst_manager/application/recovery.py`（:97 `revision_dir` 重建、:122-125 `_quarantine_unproven_publish_jobs`）
- Test: `tests/unit/test_publisher.py`

**Interfaces:**
- Consumes: 现有 `RecoverablePublisher.recover()/_recover_locked()/list_committed_operations()` 签名不变。
- Produces: 私有方法 `RecoverablePublisher._iter_journal_records(jobs: Path, workspace_root: Path) -> list[tuple[Path, str, Path]]`（返回 `(journal_path, job_id, revision_dir)` 三元组；Task 8 随恢复逻辑一并迁入 `publish_recovery.py`）。

- [ ] **Step 1: 写失败测试——新布局日志能被启动恢复识别**

在 `tests/unit/test_publisher.py` 末尾追加（fixture 手工构造 journal，模式同 `test_startup_recovery_closes_unfinished_journal` :356）：

```python
@pytest.mark.parametrize("status", ["PREPARED", "PUBLISHING", "ROLLING_BACK"])
def test_startup_recovery_reads_nested_attempt_journal(tmp_path: Path, status: str):
    """嵌套 attempt 布局下的未完成日志在启动恢复时按嵌套路径回滚。"""
    operation = "nested-crash"
    target = tmp_path / "target.txt"
    target.write_text("after")
    backup = tmp_path / ".dst-manager" / "revisions" / operation / "attempt-001" / "before" / target.name
    backup.parent.mkdir(parents=True)
    backup.write_text("before")
    journal_path = tmp_path / ".dst-manager" / "jobs" / operation / "attempt-001" / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal = {
        "operation_id": operation,
        "attempt": 1,
        "status": status,
        "files": [{"target": str(target), "backup": str(backup), "staged": None, "replaced": status != "PREPARED"}],
    }
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    assert RecoverablePublisher().recover(tmp_path) == [operation]
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"
    assert target.read_text() == ("after" if status == "PREPARED" else "before")
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit/test_publisher.py::test_startup_recovery_reads_nested_attempt_journal -q`
Expected: FAIL（新布局日志不被现有 glob 发现，`recovered` 为空或目标未被恢复）

- [ ] **Step 3: 实现 `_iter_journal_records` 并改造 `_recover_locked`**

`publisher.py` 中新增（放在 `_recover_locked` 上方）：

```python
    def _iter_journal_records(
        self,
        jobs: Path,
        workspace_root: Path,
    ) -> list[tuple[Path, str, Path]]:
        """按新旧两种布局枚举发布日志，返回 ``(journal_path, job_id, revision_dir)``。

        嵌套布局 ``jobs/<job_id>/attempt-NNN/`` 与旧平铺布局 ``jobs/<job_id>/`` 并存：
        升级后旧工作区仍必须能被启动恢复与清单枚举读取，因此两套 glob 都要扫。
        """
        records: list[tuple[Path, str, Path]] = []
        revisions = workspace_root / ".dst-manager" / "revisions"
        for path in jobs.glob("*/*/publish-journal.json"):
            job_id = path.parent.parent.name
            records.append((path, job_id, revisions / job_id / path.parent.name))
        for path in jobs.glob("*/publish-journal.json"):
            records.append((path, path.parent.name, revisions / path.parent.name))
        return records
```

`_recover_locked`（:945）中把 `for path in jobs.glob("*/publish-journal.json"):` 改为：

```python
        for path, job_id, revision_dir in self._iter_journal_records(jobs, workspace_root):
```

并把原 :963-967 两行：

```python
                operation_id = path.parent.name
                if journal.get("operation_id") != operation_id:
                    raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
                revision_dir = workspace_root / ".dst-manager" / "revisions" / operation_id
```

改为（嵌套布局额外校验 attempt 目录名与 journal 字段一致）：

```python
                if journal.get("operation_id") != job_id:
                    raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
                attempt_dir_name = path.parent.name
                if attempt_dir_name.startswith("attempt-"):
                    attempt_from_path = int(attempt_dir_name.removeprefix("attempt-"))
                    if journal.get("attempt") != attempt_from_path:
                        raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
```

（`revision_dir` 已由 `_iter_journal_records` 给出，删除原构造行；`recovered.append(journal["operation_id"])` 与其余逻辑不动。）

- [ ] **Step 4: 改造 `list_committed_operations` 双 glob**

`_list_committed_operations_locked`（:1051）中：

```python
        candidates = list((workspace_root / ".dst-manager" / "revisions").glob("*/*/manifest.json")) + list(
            (workspace_root / ".dst-manager" / "revisions").glob("*/manifest.json")
        )
```

其余（按 `operation_id` 去重、排序）不变——`journal["operation_id"]` 语义未变，去重逻辑天然兼容。

- [ ] **Step 5: 改造 `application/recovery.py`**

:97 处 `revision_dir` 重建改为按 attempt 字段：

```python
                attempt = journal.get("attempt")
                revision_dir = (
                    workspace_root / ".dst-manager" / "revisions" / operation_id / f"attempt-{attempt:03d}"
                    if isinstance(attempt, int)
                    else workspace_root / ".dst-manager" / "revisions" / operation_id
                )
```

`_quarantine_unproven_publish_jobs`（:116-137）的枚举改为：

```python
        candidates = list(jobs_root.glob("*/*/publish-journal.json")) + list(
            jobs_root.glob("*/publish-journal.json")
        )
        for journal_path in candidates:
            if journal_path.parent.parent == jobs_root:
                operation_id = journal_path.parent.name
            else:
                operation_id = journal_path.parent.parent.name
            if not operation_id:
                continue
```

（其余 `database.get_job` / `finalize_job_terminal` 逻辑不动。）

- [ ] **Step 6: 运行测试**

Run: `uv run pytest tests/unit/test_publisher.py tests/unit/test_core.py -q`
Expected: PASS（含 Step 1 新测试）

- [ ] **Step 7: Commit**

```bash
git add src/dst_manager/infrastructure/filesystem/publisher.py src/dst_manager/application/recovery.py tests/unit/test_publisher.py
git commit -m "feat: 发布日志与清单枚举兼容按 attempt 嵌套的新布局（只读侧）"
```

---

### Task 2: 发布写入侧切换到嵌套布局并删除 reclaim 机制

**Files:**
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`（模块 docstring :30-44、`publish` :188、`_publish_locked` :210-298、删除 `_reclaim_previous_attempt` :143-177 与 `_preserve_superseded_journal` :178-186、临时文件名 :325、`_replacement_backup_path` :140 调用点 :268）
- Modify: `src/dst_manager/application/cad_job.py:336`、`editing.py:292`、`repair.py:165`、`revisions.py:207`、`xml_io.py:202`
- Test: `tests/unit/test_publisher.py`（:1637-1815 重试回收测试重写）

**Interfaces:**
- Consumes: Task 1 的双 glob 读取（新布局写入的日志立即可恢复）。
- Produces: `RecoverablePublisher.publish(job_id: str, workspace_root: Path, staged: dict[Path, Path | None], *, attempt: int, expected_baselines: ... , before_commit: ..., on_committed: ...) -> Path`——`attempt` 为必填关键字参数；journal 含 `"attempt"` 字段；临时文件名使用 `uid = f"{job_id}~{attempt:03d}"`。

- [ ] **Step 1: 重写重试相关测试（先写失败测试）**

删除以下 4 个针对已消亡 reclaim 机制的测试（机制不复存在，其保护由「目录不复用 + 终态清扫」替代）：
- `test_stale_snapshot_inconsistent_with_baseline_is_refused`（:1752）
- `test_redundant_replacement_backup_is_reclaimed_on_retry`（:1776）
- `test_replacement_backup_with_unknown_content_is_refused`（:1796）
- `test_reusing_committed_operation_is_refused_without_touching_files`（:1717，其「防重复提交」职责由下述新测试承担）

重写 :1637 与 :1685 两个测试（原 `test_retry_after_rolled_back_publish_reuses_revision_dir`、`test_reused_revision_dir_rollback_still_restores_formal_files`），并新增：

```python
def test_retry_publishes_into_new_attempt_directory(tmp_path: Path):
    """重试写入 attempt-002 新目录并正常提交，不依赖上一次尝试的任何产物。"""
    job_id = "retry-jobs"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    publisher = RecoverablePublisher()

    def replace(source: Path, target_path: Path):
        raise OSError("注入首次发布故障")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "before"

    revision_dir = publisher.publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert revision_dir == tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-002"
    assert target.read_text() == "after"
    second_journal = json.loads(
        (tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-002" / "publish-journal.json").read_text(encoding="utf-8"),
    )
    assert second_journal["status"] == "COMMITTED"
    assert second_journal["operation_id"] == job_id
    assert second_journal["attempt"] == 2


def test_same_attempt_revision_dir_conflict_is_refused(tmp_path: Path):
    """同号 attempt 的修订目录已存在（重复提交防护）时拒绝且不触碰任何文件。"""
    job_id = "conflict-job"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    revision_dir = tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-001"
    revision_dir.mkdir(parents=True)
    (revision_dir / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PublishOperationConflictError):
        RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "before"
    assert not (tmp_path / ".dst-manager" / "jobs" / job_id).exists()


def test_second_attempt_rollback_still_restores_formal_files(tmp_path: Path):
    """attempt-002 发布失败整批回滚后，正式文件回到 attempt-001 发布后的内容。"""
    job_id = "second-rollback"
    target = tmp_path / "target.txt"
    staged = tmp_path / "staged.txt"
    target.write_text("v0")
    staged.write_text("v1")
    RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "v1"
    staged.write_text("v2")

    def replace(source: Path, target_path: Path):
        raise OSError("注入二次发布故障")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert target.read_text() == "v1"
```

> 说明：本任务的测试不断言「attempt-001 目录保留」——attempt-001 的日志终态为 ROLLED_BACK，Task 3 落地后会在重试发布前被整目录清扫；「不可证明的旧 attempt 保留」由 Task 3 的 `test_sweep_preserves_unproven_previous_attempt` 固化。

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit/test_publisher.py -k "attempt" -q`
Expected: FAIL（publish 尚无 attempt 参数：TypeError）

- [ ] **Step 3: 改 `publish` 签名与 `_publish_locked` 路径派生**

`publish`（:188）签名改为（首参更名 `job_id`，五个调用点都是位置传参，不受影响）：

```python
    def publish(
        self,
        job_id: str,
        workspace_root: Path,
        staged: dict[Path, Path | None],
        *,
        attempt: int,
        expected_baselines: dict[Path, ExpectedFileBaseline | None] | None = None,
        before_commit: Callable[[], None] | None = None,
        on_committed: Callable[[Path, dict], None] | None = None,
    ) -> Path:
```

`_publish_locked` 同步加 `*, attempt: int`，路径派生段（:234-247）替换为：

```python
        manager_dir = workspace_root / ".dst-manager"
        attempt_dir_name = f"attempt-{attempt:03d}"
        revision_dir = manager_dir / "revisions" / job_id / attempt_dir_name
        before_dir = revision_dir / "before"
        journal_path = manager_dir / "jobs" / job_id / attempt_dir_name / "publish-journal.json"
        # 每次尝试独占 attempt-NNN 目录，重试不再复用上一次的修订目录；目录已存在
        # 只可能是同号重复提交，直接拒绝（早前尝试的终态清扫由 Task 3 落地后在此前调用）。
        if revision_dir.exists():
            raise PublishOperationConflictError(f"同一次尝试的修订目录已存在，禁止复用：{revision_dir}")
```

（删除原 `_reclaim_previous_attempt` 调用块；`journal` 字典 :293-298 增加 `"attempt": attempt,`；新增 `operation_uid = f"{job_id}~{attempt:03d}"` 局部变量，:268 `_replacement_backup_path(target, operation_id)` 改传 `operation_uid`，:325 publish_temp 同理，`_commit_existing(entry, publish_temp, operation_id)` :340 改传 `operation_uid`。）

删除 `_reclaim_previous_attempt`（:143-177）与 `_preserve_superseded_journal`（:178-186）整个方法体。模块 docstring（:30-44）中关于「retry_job 复用 job_id 必然第二次面对同一修订目录」的段落改写为：

```
    每次发布尝试独占 ``revisions/<job_id>/attempt-NNN/`` 目录：任务重试由数据库
    attempt 计数严格递增，永远落在新目录上，因此不存在「回收上一次尝试」问题；
    上一次尝试的目录由 ``_sweep_superseded_attempts`` 按日志终态回收（见该方法的
    证据边界说明）。``journal["operation_id"]`` 保持等于 job_id，是启动恢复与
    提交后闭环查库的键；``journal["attempt"]`` 用于按路径重建修订目录。
```

- [ ] **Step 4: 更新 5 个调用点**

- `cad_job.py:336`：`self.publisher.publish(job_id, workspace.root, staged_files, attempt=attempt, expected_baselines=...)`（`attempt` 变量在 `_execute` 作用域内已存在）
- `editing.py:292`、`repair.py:165`、`revisions.py:207`、`xml_io.py:202`：各加 `attempt=1,`（这四类任务不可重试，恒为首次尝试）

- [ ] **Step 5: 运行测试**

Run: `uv run pytest tests/unit -q`
Expected: PASS。若既有测试直接调用 `publisher.publish(...)` 报缺 `attempt`，逐一补 `attempt=1`（重试语义的测试按需传 2/3）。

- [ ] **Step 6: Ruff 与提交**

Run: `uv run ruff check .`
Expected: 无错误（确认删除 reclaim 后无残留 import）

```bash
git add -A
git commit -m "feat: 发布写入侧按 attempt 嵌套命名空间并删除 reclaim 证据回收机制"
```

---

### Task 3: 新增 `_sweep_superseded_attempts` 终态清扫

**Files:**
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`（`_publish_locked` 路径派生段之后、`publish` 与 `_publish_locked` 之间新增方法）
- Test: `tests/unit/test_publisher.py`

**Interfaces:**
- Consumes: Task 1 的 `TERMINAL_ROLLBACK_STATUSES`（本任务落地该常量到模块顶层：`TERMINAL_ROLLBACK_STATUSES = {"ROLLED_BACK", "ABORTED_BASELINE_CHANGED"}`）。
- Produces: `RecoverablePublisher._sweep_superseded_attempts(manager_dir: Path, job_id: str, current_attempt: int) -> None`——在 `_publish_locked` 于路径守卫之前调用。

- [ ] **Step 1: 写失败测试**

```python
def test_sweep_removes_rolled_back_previous_attempt(tmp_path: Path):
    """attempt-001 日志终态为 ROLLED_BACK 时，attempt-002 发布前整目录清扫。"""
    job_id = "sweep-rolled-back"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")

    def replace(source: Path, target_path: Path):
        raise OSError("注入首次发布故障")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=1)

    RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert not (tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-001").exists()
    assert not (tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-001").exists()


def test_sweep_preserves_unproven_previous_attempt(tmp_path: Path):
    """日志缺失、不可解析或 ROLLBACK_FAILED 的旧 attempt 目录一律保留。"""
    job_id = "preserve-unproven"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    jobs_root = tmp_path / ".dst-manager" / "jobs" / job_id

    # 现场一：journal 缺失（中途崩溃，连日志都没写出来）。
    (jobs_root / "attempt-001").mkdir(parents=True)
    # 现场二：journal 不可解析。
    (jobs_root / "attempt-002").mkdir(parents=True)
    (jobs_root / "attempt-002" / "publish-journal.json").write_text("{broken", encoding="utf-8")
    # 现场三：ROLLBACK_FAILED（未被证明回到发布前状态）。
    (jobs_root / "attempt-003").mkdir(parents=True)
    (jobs_root / "attempt-003" / "publish-journal.json").write_text(
        json.dumps({"operation_id": job_id, "attempt": 3, "status": "ROLLBACK_FAILED", "files": []}),
        encoding="utf-8",
    )

    revision_dir = RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=4)
    assert target.read_text() == "after"
    assert revision_dir.name == "attempt-004"
    assert (jobs_root / "attempt-001").exists()
    assert (jobs_root / "attempt-002").exists()
    assert (jobs_root / "attempt-003").exists()


def test_sweep_removes_legacy_flat_rolled_back_layout(tmp_path: Path):
    """旧平铺布局的已回滚残留（journal + before/ + superseded-journals/）在发布时清理。"""
    job_id = "legacy-sweep"
    target = tmp_path / "target.txt"
    target.write_text("before")
    backup = tmp_path / ".dst-manager" / "revisions" / job_id / "before" / target.name
    backup.parent.mkdir(parents=True)
    backup.write_text("before")
    superseded = tmp_path / ".dst-manager" / "revisions" / job_id / "superseded-journals"
    superseded.mkdir(parents=True)
    legacy_journal = tmp_path / ".dst-manager" / "jobs" / job_id / "publish-journal.json"
    legacy_journal.parent.mkdir(parents=True)
    legacy_journal.write_text(
        json.dumps({"operation_id": job_id, "status": "ROLLED_BACK", "files": []}),
        encoding="utf-8",
    )
    staged = tmp_path / "staged.txt"
    staged.write_text("after")

    RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert not legacy_journal.exists()
    assert not (tmp_path / ".dst-manager" / "revisions" / job_id / "before").exists()
    assert not superseded.exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit/test_publisher.py -k sweep -q`
Expected: FAIL（方法不存在，attempt-001 目录未清理）

- [ ] **Step 3: 实现清扫方法**

```python
    def _sweep_superseded_attempts(self, manager_dir: Path, job_id: str, current_attempt: int) -> None:
        """按日志终态清扫同任务早前尝试的发布产物；无法证明冗余的一律保留。

        嵌套布局下发布本身不需要回收任何目录（每次尝试独占 attempt-NNN），这里
        只做磁盘空间回收：终态为已回滚（ROLLED_BACK / ABORTED_BASELINE_CHANGED）
        的目录，其 before 快照与替换备份都已随整批恢复而冗余，可整体删除；其余
        状态（ROLLBACK_FAILED、中途崩溃、日志缺失或不可解析）说明该次尝试尚未
        被证明回到发布前状态，保留给启动恢复或人工处置，绝不猜测性清理。
        旧平铺布局的残留只清理已被日志证明冗余的三类产物，manifest.json 等
        未证明项一律不碰。
        """
        jobs_root = manager_dir / "jobs" / job_id
        revisions_root = manager_dir / "revisions" / job_id
        for journal_path in jobs_root.glob("attempt-*/publish-journal.json"):
            attempt_dir = journal_path.parent
            if attempt_dir.name == f"attempt-{current_attempt:03d}":
                continue
            if self._journal_status(journal_path) in TERMINAL_ROLLBACK_STATUSES:
                try:
                    atomic.retry_transient_contention(lambda d=attempt_dir: shutil.rmtree(d))
                    shutil.rmtree(revisions_root / attempt_dir.name, ignore_errors=True)
                except OSError:
                    # 清扫是空间回收，不是发布的前置条件；失败保留现场，下次发布再试。
                    continue
        # 旧平铺布局的日志永远属于更早的运行（新布局写入 attempt-NNN 子目录），
        # 已被日志证明整批回滚的，随其快照目录一并清理，无 attempt 号比较。
        legacy_journal = jobs_root / "publish-journal.json"
        if self._journal_status(legacy_journal) in TERMINAL_ROLLBACK_STATUSES:
            try:
                atomic.retry_transient_contention(lambda p=legacy_journal: p.unlink(missing_ok=True))
                shutil.rmtree(revisions_root / "before", ignore_errors=True)
                shutil.rmtree(revisions_root / "superseded-journals", ignore_errors=True)
            except OSError:  # noqa: BLE001, S110 - 同上，清扫失败不影响本次发布
                pass

    @staticmethod
    def _journal_status(journal_path: Path) -> str | None:
        try:
            return json.loads(journal_path.read_text(encoding="utf-8")).get("status")
        except (OSError, json.JSONDecodeError):
            return None
```

在 `_publish_locked` 的 `if revision_dir.exists():` 守卫**之前**插入调用：

```python
        self._sweep_superseded_attempts(manager_dir, job_id, attempt)
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/unit/test_publisher.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: 重试发布前按日志终态清扫早前 attempt 的发布产物"
```

---

### Task 4: 旧布局端到端兼容回归

**Files:**
- Test: `tests/unit/test_publisher.py`

**Interfaces:**
- Consumes: Task 1-3 的读写两侧实现。
- Produces: 无新接口；固化「升级现场」回归防线。

- [ ] **Step 1: 写端到端回归测试**

```python
def test_legacy_flat_committed_manifest_is_listed_after_upgrade(tmp_path: Path):
    """旧布局 COMMITTED 清单在升级后仍可被 list/read_committed_operation 枚举。"""
    operation = "legacy-committed"
    revisions = tmp_path / ".dst-manager" / "revisions" / operation
    revisions.mkdir(parents=True)
    manifest = {
        "identity_version": 1,
        "operation_id": operation,
        "status": "COMMITTED",
        "files": [{"target": str(tmp_path / "target.txt")}],
    }
    (revisions / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    publisher = RecoverablePublisher()
    listed = publisher.list_committed_operations(tmp_path)
    assert [journal["operation_id"] for journal in listed] == [operation]
    assert publisher.read_committed_operation(tmp_path, operation) == manifest


def test_legacy_flat_publishing_journal_recovers_before_new_publish(tmp_path: Path):
    """旧平铺 PUBLISHING 残留先被启动恢复回滚，随后 attempt=1 的全新发布不受残留干扰。"""
    operation = "legacy-publishing"
    target = tmp_path / "target.txt"
    target.write_text("after")
    backup = tmp_path / ".dst-manager" / "revisions" / operation / "before" / target.name
    backup.parent.mkdir(parents=True)
    backup.write_text("before")
    legacy_journal = tmp_path / ".dst-manager" / "jobs" / operation / "publish-journal.json"
    legacy_journal.parent.mkdir(parents=True)
    legacy_journal.write_text(
        json.dumps({
            "operation_id": operation,
            "status": "PUBLISHING",
            "files": [{"target": str(target), "backup": str(backup), "staged": None, "replaced": True}],
        }),
        encoding="utf-8",
    )
    publisher = RecoverablePublisher()
    assert publisher.recover(tmp_path) == [operation]
    assert target.read_text() == "before"

    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    revision_dir = publisher.publish(operation, tmp_path, {target: staged}, attempt=1)
    assert revision_dir == tmp_path / ".dst-manager" / "revisions" / operation / "attempt-001"
    assert target.read_text() == "after"
    # 已回滚的平铺日志属被证明冗余的旧布局残留，发布时被一并清扫。
    assert not legacy_journal.exists()
```

- [ ] **Step 2: 运行确认失败或通过**

Run: `uv run pytest tests/unit/test_publisher.py -k legacy -q`
Expected: PASS（若 FAIL 则按失败点修正 Task 1-3 的兼容分支——本任务是防线，不是功能）

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_publisher.py
git commit -m "test: 固化新旧发布布局共存的端到端兼容回归"
```

---

### Task 5: 异常类外移到 `publish_errors.py`

从本任务起进入拆分阶段（纯移动，无行为变化）。**每个拆分任务的模式相同**：新建模块 → 原地剪切 → publisher.py 以 re-export 保持 application 层 import 不变 → 全量测试 → commit。

**Files:**
- Create: `src/dst_manager/infrastructure/filesystem/publish_errors.py`
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`（:25-60 异常类段）
- Test: 既有测试为安全网，无新增

**Interfaces:**
- Produces: `publish_errors.py` 导出 `PublishRolledBackError`、`PublishRecoveryError`、`PublishOperationConflictError`、`PublishBaselineError`、`PublishJournalWriteError`（含各自 docstring 与 `code` 属性，逐字保留）。

- [ ] **Step 1: 新建 `publish_errors.py`**

将 publisher.py :25-60 的 5 个异常类（含 docstring 与 `code = "..."` 类属性）**逐字**剪切入新文件，文件头：

```python
"""发布事务异常（自 publisher.py 拆分；错误码与继承关系逐字保留）。"""
```

- [ ] **Step 2: publisher.py 改为 re-export**

原类定义位置替换为：

```python
# 既有公共接口：application 层从 publisher 导入这些异常，拆分后此处必须继续可导入。
from dst_manager.infrastructure.filesystem.publish_errors import (  # noqa: F401
    PublishBaselineError,
    PublishJournalWriteError,
    PublishOperationConflictError,
    PublishRecoveryError,
    PublishRolledBackError,
)
```

注意：`publish_errors.py` 不得 import publisher.py（叶模块，依赖方向只能是 publisher → publish_errors）。

- [ ] **Step 3: 全量验证**

Run: `uv run pytest tests/unit -q && uv run ruff check .`
Expected: PASS / 无错误

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: 发布事务异常外移到 publish_errors 模块（纯移动）"
```

---

### Task 6: 无状态原语外移到 `publish_primitives.py`

**Files:**
- Create: `src/dst_manager/infrastructure/filesystem/publish_primitives.py`
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`
- Test: `tests/unit/test_publisher.py`（既有用例为安全网）+ 新增直接单测

**Interfaces:**
- Produces: 模块级函数（类方法原样转函数，签名不变，`self` 去除）：
  - `file_sha256(path: Path) -> str`
  - `capture_file_baseline(path: Path) -> ExpectedFileBaseline | None` 与 `ExpectedFileBaseline` 数据类
  - `move_no_replace(source: Path, target: Path) -> None`（原 `_move_no_replace` :95）
  - `replace_existing(source: Path, target: Path, backup: Path) -> None`（原 `_replace_existing` :109）
  - `file_identity(path: Path) -> list[int]`（原 `_file_identity` :822）
  - `before_snapshot_path(before_dir: Path, workspace_root: Path, target: Path) -> Path`（原 :136）
  - `replacement_backup_path(target: Path, operation_uid: str) -> Path`（原 :140）

- [ ] **Step 1: 新建模块并剪切**

文件头：`"""发布事务文件原语（自 publisher.py 拆分；哈希、基线、替换与身份识别）。"""`

剪切上述 8 个成员。若 `replace_existing` 内部调用 `self._move_no_replace`，改为直接调用模块函数 `move_no_replace`。publisher.py 中全部 `self._move_no_replace(...)`、`self._replace_existing(...)`、`self._file_identity(...)`、`self._before_snapshot_path(...)`、`self._replacement_backup_path(...)` 调用点（grep 确认，约 20 处）改为模块函数调用；类顶部 import 并 re-export：

```python
from dst_manager.infrastructure.filesystem.publish_primitives import (  # noqa: F401
    ExpectedFileBaseline,
    before_snapshot_path,
    capture_file_baseline,
    file_identity,
    file_sha256,
    move_no_replace,
    replacement_backup_path,
    replace_existing,
)
```

（`application/recovery.py:17` 现从 publisher 导入 `capture_file_baseline`，re-export 保证其不变。）

- [ ] **Step 2: 新增原语直接单测**

`tests/unit/test_publish_primitives.py` 新建（import 路径以拆分后模块为准）：

```python
import hashlib
from pathlib import Path

import pytest

from dst_manager.infrastructure.filesystem.publish_primitives import (
    capture_file_baseline,
    file_sha256,
    move_no_replace,
    replace_existing,
)


def test_file_sha256_matches_known_digest(tmp_path: Path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"known-bytes")
    assert file_sha256(target) == hashlib.sha256(b"known-bytes").hexdigest()


def test_capture_file_baseline_distinguishes_existing_and_missing(tmp_path: Path):
    target = tmp_path / "a.txt"
    assert capture_file_baseline(target) is None
    target.write_bytes(b"payload")
    baseline = capture_file_baseline(target)
    assert baseline is not None and baseline.sha256 == file_sha256(target)


def test_move_no_replace_rejects_existing_target(tmp_path: Path):
    source = tmp_path / "src.txt"
    source.write_text("moved")
    existing = tmp_path / "dst.txt"
    existing.write_text("occupied")
    with pytest.raises(FileExistsError):
        move_no_replace(source, existing)
    assert source.exists() and existing.read_text() == "occupied"


def test_replace_existing_preserves_previous_content_in_backup(tmp_path: Path):
    source = tmp_path / "new.txt"
    source.write_text("new")
    target = tmp_path / "formal.txt"
    target.write_text("old")
    backup = tmp_path / "backup.txt"
    replace_existing(source, target, backup)
    assert target.read_text() == "new"
    assert backup.read_text() == "old"
    assert not source.exists()
```

- [ ] **Step 3: 全量验证**

Run: `uv run pytest tests/unit -q && uv run ruff check . && wc -l src/dst_manager/infrastructure/filesystem/publisher.py`
Expected: PASS / 无错误 / publisher.py 行数下降约 120 行

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: 发布事务文件原语外移到 publish_primitives 模块（纯移动）"
```

---

### Task 7: 日志读写外移到 `publish_journal.py`

**Files:**
- Create: `src/dst_manager/infrastructure/filesystem/publish_journal.py`
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`

**Interfaces:**
- Consumes: `publish_errors.PublishJournalWriteError`、`atomic` 模块。
- Produces: 模块级函数：
  - `write_journal(path: Path, journal: dict) -> None`（原 `_write_journal` :885，含原子写入与 `PublishJournalWriteError` 包装，逻辑逐字保留）
  - `write_journal_best_effort(path: Path, journal: dict) -> None`（原 :897）
  - `archive_journal(revision_dir: Path, journal_path: Path, journal: dict) -> None`（原 `_archive_journal` :446）
  - `immutable_transaction_projection(workspace_root: Path, journal: dict) -> dict`（原 :457）

- [ ] **Step 1: 剪切与替换调用点**

publisher.py 内 `self._write_journal(...)`（约 18 处）、`self._write_journal_best_effort(...)`（3 处）、`self._archive_journal(...)`（3 处）、`self._immutable_transaction_projection(...)`（2 处）全部改为模块函数调用；`_rollback_legacy_attempted` 中的 `RecoverablePublisher._write_journal(...)`（:904）改为 `write_journal(...)`。re-export `write_journal`/`write_journal_best_effort`（测试可能直接引用，先 grep `tests/` 确认清单）。

- [ ] **Step 2: 全量验证**

Run: `uv run pytest tests/unit -q && uv run ruff check .`
Expected: PASS / 无错误

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: 发布日志读写外移到 publish_journal 模块（纯移动）"
```

---

### Task 8: 启动恢复与清单枚举外移到 `publish_recovery.py`

**Files:**
- Create: `src/dst_manager/infrastructure/filesystem/publish_recovery.py`
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`

**Interfaces:**
- Consumes: `publisher.RecoverablePublisher` 实例（鸭子类型参数，**不 import publisher**，保持依赖单向 publisher → publish_recovery）；`publish_journal`、`publish_errors`、`publish_primitives`。
- Produces:
  - `recover(publisher, workspace_root: Path) -> list[str]`（原 `recover`+`_recover_locked`，锁的获取与释放逻辑一并移入）
  - `list_committed_operations(publisher, workspace_root: Path) -> list[dict]`
  - `read_committed_operation(publisher, workspace_root: Path, operation_id: str) -> dict | None`
  - `_rollback_legacy_attempted`（:908）与 `_legacy_rollback_source`（:930）随迁移（经 publisher 参数调用其恢复原语）

- [ ] **Step 1: 剪切为以 publisher 为首参的模块函数**

`RecoverablePublisher` 中原方法改为薄委托：

```python
    def recover(self, workspace_root: Path) -> list[str]:
        return publish_recovery.recover(self, workspace_root)

    def list_committed_operations(self, workspace_root: Path) -> list[dict]:
        return publish_recovery.list_committed_operations(self, workspace_root)

    def read_committed_operation(self, workspace_root: Path, operation_id: str) -> dict | None:
        return publish_recovery.read_committed_operation(self, workspace_root, operation_id)
```

`publish_recovery.py` 内对 `self._rollback`、`self._finish_committed_cleanup`、`self._restore_entry`、`self._restore_backup_by_rename` 等实例方法的调用改为 `publisher._rollback(...)` 形式；`_iter_journal_records`、`_journal_status` 一并迁入（它们只被恢复侧使用）。

- [ ] **Step 2: 行数与依赖检查**

Run: `wc -l src/dst_manager/infrastructure/filesystem/*.py && uv run ruff check .`
Expected: `publisher.py` ≤ 600 行；ruff 无循环依赖告警

- [ ] **Step 3: 全量验证并提交**

Run: `uv run pytest tests/unit -q`
Expected: PASS

```bash
git add -A
git commit -m "refactor: 启动恢复与已提交清单枚举外移到 publish_recovery 模块（纯移动）"
```

---

### Task 9: 测试文件拆分

**Files:**
- Create: `tests/unit/test_publish_journal.py`、`tests/unit/test_publish_recovery.py`、`tests/unit/test_publish_primitives.py`、`tests/unit/test_publish_guards.py`
- Modify: `tests/unit/test_publisher.py`

**Interfaces:** 无生产代码改动；共享 fixture 留在原文件或移入 `tests/conftest.py`（执行时按实际引用决定，引用方 import 路径同步更新）。

- [ ] **Step 1: 按主题映射搬移测试**

以 `grep -n "^def test_\|^class " tests/unit/test_publisher.py` 取当前清单后按下表搬移（函数体逐字移动，不加不改）：

| 目标文件 | 搬移内容（按名匹配） |
|---|---|
| `test_publish_journal.py` | `test_concurrent_journal_writes_use_independent_temporary_files`、`test_transient_journal_denial_is_retried_without_rolling_back`、`test_persistent_journal_denial_fails_before_touching_files`、`test_journal_denial_after_first_replacement_still_restores_files`、`_JournalDenialWindow` 辅助类 |
| `test_publish_recovery.py` | 全部 `test_startup_*`、`test_recovery_rejects_a_publish_holding_the_workspace_transaction_lock`、`test_committed_cleanup_*`、`test_committed_operation_is_not_visible_without_manifest`、`test_archive_*`、`test_committed_callback_runs_after_publish_cleanup_attempt`、`test_crash_before_committed_journal_recovers_batch_with_original_identities`、Task 1-4 新增的嵌套/清扫/legacy 回归测试 |
| `test_publish_guards.py` | `test_windows_lock_blocks_writers_but_allows_readers`、`test_publish_can_atomically_replace_target_while_write_lock_is_held`、全部 `test_result_guard_*`、`test_windows_result_guard_*`、`test_non_windows_result_guard_*` |
| `test_publish_primitives.py` | `test_caller_identity_baseline_allows_unchanged_target`、`test_caller_identity_baseline_rejects_same_bytes_replacement_before_publish`、Task 6 新增的原语单测 |
| `test_publisher.py`（保留） | 发布/回滚/提交编排与失败注入路径（其余全部），含 `_SimulatedProcessCrash` |

- [ ] **Step 2: 全量验证与行数核对**

Run: `uv run pytest tests/unit -q && uv run ruff check . && wc -l tests/unit/test_publisher*.py`
Expected: 用例总数与搬移前一致（`uv run pytest tests/unit --collect-only -q | tail -1` 前后对比）；各文件向 500 行靠拢

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: 发布事务测试按日志、恢复、平台守卫、原语主题拆分"
```

---

### Task 10: 文档归档与收尾验证

**Files:**
- Modify: `changelog.md`、`.planning/plans/dst-manager/README.md`、本文件（status → `completed` 并记录验证）

- [ ] **Step 1: 更新 changelog**

按 `changelog.md` 既有格式追加条目：嵌套 attempt 命名空间、reclaim 机制删除、终态清扫、旧布局兼容、publisher 拆分（列出 4 个新模块）。

- [ ] **Step 2: 更新计划索引与状态**

`.planning/plans/dst-manager/README.md` 索引加入 PLAN-DM-031；本文件 frontmatter `status` 改 `completed`，`updated` 改为当日，并在文末「实际验证」小节记录：全量 pytest 结果、ruff 结果、`wc -l` 各文件最终行数。

- [ ] **Step 3: 交付前全量验证**

Run: `uv run ruff check . && uv run pytest -q`
Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: PLAN-DM-031 嵌套命名空间与 publisher 拆分完成归档"
```

---

## 风险与回退

- **最大风险**：Task 2 切换写入布局后，若 Task 1 的读侧分支有漏（如 `recovered.append` 键、隔离路径），崩溃恢复会漏日志。缓解：Task 1 先行合入并独立验证；Task 4 的 legacy 端到端测试 + 既有 60 余个恢复测试为防线。
- **降级不兼容**：旧版本程序读不到嵌套日志。发布说明中注明「升级前确认无进行中发布任务」。
- **回退方式**：每个任务独立 commit；Task 1-4（行为）与 Task 5-9（拆分）分段，任何一段可单独 revert。
