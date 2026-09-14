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

**Goal:** 把发布事务的磁盘命名空间从 `revisions/<job_id>`（job 与 attempt 混用）改为 `revisions/<job_id>/attempt-NNN`（嵌套），从而删除 `_reclaim_previous_attempt` 的目录复用机制并永久保留每次 attempt 的发布证据；随后把 1077 行的 `publisher.py` 按职责拆分为 4 个同层模块，使其回到 500 行软上限附近。

**Architecture:** 发布器新增必填关键字参数 `attempt`，日志路径嵌套到 `jobs/<job_id>/attempt-NNN/`、修订目录嵌套到 `revisions/<job_id>/attempt-NNN/`；`journal["operation_id"]` 保持等于 `job_id`（启动恢复与隔离逻辑直接拿它查数据库），新增 `journal["attempt"]` 字段用于重建修订目录。重试永远写入新的 attempt 目录，既不复用也不自动清扫任何旧 attempt；发布前同时执行「当前 attempt 命名空间未占用」和「同一 job 尚无任何 COMMITTED manifest」两层守卫。拆分为纯移动重构：异常 → `publish_errors.py`，无状态原语 → `publish_primitives.py`，日志读写 → `publish_journal.py`，启动恢复 → `publish_recovery.py`，`publisher.py` 保留编排门面并 re-export 既有公共名。

**Tech Stack:** Python 3.12 + UV；pytest；ruff。

**Spec:** 本计划实现两份评审结论：commit `ea5072b` 代码评审发现 #8（机制级修法）与 #9（AGENTS.md 容量契约），以及 PLAN-DM-031 讨论中确认的嵌套方案。

## Global Constraints

- Python 命令统一使用 `uv run`；Windows 11 + PowerShell 环境，计划中的命令不得依赖 Bash 专用的 `wc`、`tail` 等工具。
- 交付前必须通过 `uv run ruff check .` 与 `uv run pytest -q`（AGENTS.md 第 84-85 行）。
- 单个源文件约 500 行软上限（AGENTS.md 第 53 行）；拆分后 `publisher.py` 编排核心允许在 500-600 行区间。
- 拆分必须保持既有公共接口、错误码与序列化契约不变（AGENTS.md 第 56 行）：`publisher.py` 继续 re-export 全部异常类与 `ExpectedFileBaseline`、`capture_file_baseline`、`file_sha256`，application 层既有 import 一律不改。
- 代码注释、commit message 使用简体中文（AGENTS.md 第 8-9 行）。
- 发布安全相关改动，执行前阅读 `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md` 中发布事务与启动恢复章节。
- 每个任务结束时相关测试必须全绿，才允许 commit；禁止把行为变更与拆分混入同一 commit。
- 工作区可能已有用户改动；每次提交只允许显式暂存本任务列出的文件，禁止使用 `git add -A`、`git add .` 或其它宽泛暂存命令。

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

- journal 新增字段 `"attempt": <int>`；`attempt` 必须满足 `type(attempt) is int and attempt >= 1`，目录名必须等于 `f"attempt-{attempt:03d}"`；`"operation_id"` 字段语义不变（= job_id）；`identity_version` 保持 1（files 向量格式未变；日志位置属外部布局，不入不可变投影）。
- 每目标临时文件名使用 attempt 限定串 `uid = f"{job_id}~{attempt:03d}"`：`.{name}.{uid}.tmp`、`.{name}.{uid}.replaced`、`.{name}.{uid}.conflict-published`。
- 所有 attempt 的 journal、before 快照及终态记录永久保留；本计划不提供自动清扫。未来若需保留策略，必须以独立 ADR + 显式维护命令立项，不得挂在发布前路径中隐式删除。
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
- Produces: 私有方法 `RecoverablePublisher._parse_attempt_dir_name(name: str) -> int` 与 `_iter_journal_records(jobs: Path, workspace_root: Path) -> list[tuple[Path, str, int | None, Path]]`（返回 `(journal_path, job_id, attempt, revision_dir)` 四元组；旧平铺布局的 `attempt` 为 `None`；Task 8 将二者随恢复逻辑一并迁入 `publish_recovery.py`）。

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


@pytest.mark.parametrize(
    ("attempt_dir_name", "journal_attempt"),
    [("attempt-foo", 1), ("attempt-000", 0), ("attempt-01", 1), ("attempt-001", 2)],
)
def test_startup_recovery_rejects_noncanonical_or_mismatched_attempt_identity(
    tmp_path: Path,
    attempt_dir_name: str,
    journal_attempt: int,
):
    operation = "bad-attempt-identity"
    journal_path = tmp_path / ".dst-manager" / "jobs" / operation / attempt_dir_name / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    journal_path.write_text(
        json.dumps({"operation_id": operation, "attempt": journal_attempt, "status": "PREPARED", "files": []}),
        encoding="utf-8",
    )
    with pytest.raises(PublishRecoveryError, match="PUBLISH_MANIFEST_IMMUTABLE_MISMATCH"):
        RecoverablePublisher().recover(tmp_path)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit/test_publisher.py::test_startup_recovery_reads_nested_attempt_journal -q`
Expected: FAIL（新布局日志不被现有 glob 发现，`recovered` 为空或目标未被恢复）

- [ ] **Step 3: 实现 `_iter_journal_records` 并改造 `_recover_locked`**

`publisher.py` 中新增（放在 `_recover_locked` 上方）：

```python
    @staticmethod
    def _parse_attempt_dir_name(name: str) -> int:
        raw_attempt = name.removeprefix("attempt-")
        try:
            attempt = int(raw_attempt)
        except ValueError as error:
            raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH") from error
        if attempt < 1 or name != f"attempt-{attempt:03d}":
            raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
        return attempt

    def _iter_journal_records(
        self,
        jobs: Path,
        workspace_root: Path,
    ) -> list[tuple[Path, str, int | None, Path]]:
        """按新旧两种布局枚举发布日志并严格校验 attempt 目录名。返回
        ``(journal_path, job_id, attempt, revision_dir)``。

        嵌套布局 ``jobs/<job_id>/attempt-NNN/`` 与旧平铺布局 ``jobs/<job_id>/`` 并存：
        升级后旧工作区仍必须能被启动恢复与清单枚举读取，因此两套 glob 都要扫。
        """
        records: list[tuple[Path, str, int | None, Path]] = []
        revisions = workspace_root / ".dst-manager" / "revisions"
        for path in jobs.glob("*/attempt-*/publish-journal.json"):
            job_id = path.parent.parent.name
            attempt_dir_name = path.parent.name
            attempt = self._parse_attempt_dir_name(attempt_dir_name)
            records.append((path, job_id, attempt, revisions / job_id / attempt_dir_name))
        for path in jobs.glob("*/publish-journal.json"):
            records.append((path, path.parent.name, None, revisions / path.parent.name))
        return records
```

`_recover_locked`（:945）中把 `for path in jobs.glob("*/publish-journal.json"):` 改为：

```python
        for path, job_id, attempt, revision_dir in self._iter_journal_records(jobs, workspace_root):
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
                if attempt is not None:
                    journal_attempt = journal.get("attempt")
                    if type(journal_attempt) is not int or journal_attempt != attempt:
                        raise PublishRecoveryError("PUBLISH_MANIFEST_IMMUTABLE_MISMATCH")
```

（`revision_dir` 已由 `_iter_journal_records` 给出，删除原构造行；`recovered.append(journal["operation_id"])` 与其余逻辑不动。）

- [ ] **Step 4: 改造 `list_committed_operations` 双 glob**

`_list_committed_operations_locked`（:1051）中按路径携带预期身份：

```python
        revisions = workspace_root / ".dst-manager" / "revisions"
        candidates: list[tuple[Path, str, int | None]] = []
        for path in revisions.glob("*/attempt-*/manifest.json"):
            candidates.append((path, path.parent.parent.name, self._parse_attempt_dir_name(path.parent.name)))
        candidates.extend((path, path.parent.name, None) for path in revisions.glob("*/manifest.json"))
```

循环改为 `for path, expected_job_id, expected_attempt in candidates:`；JSON 解析成功后，只有 `journal["operation_id"] == expected_job_id` 且旧布局 `expected_attempt is None`，或新布局满足 `type(journal.get("attempt")) is int and journal["attempt"] == expected_attempt` 时，才进入既有 COMMITTED/files 校验与去重。路径身份不一致的 manifest 不得用于数据库闭环。按 `operation_id` 排序逻辑不变。

- [ ] **Step 5: 改造 `application/recovery.py`**

:97 处 `revision_dir` 重建改为按 attempt 字段：

```python
                attempt = journal.get("attempt")
                revision_dir = (
                    workspace_root / ".dst-manager" / "revisions" / operation_id / f"attempt-{attempt:03d}"
                    if type(attempt) is int and attempt >= 1
                    else workspace_root / ".dst-manager" / "revisions" / operation_id
                )
```

`_quarantine_unproven_publish_jobs`（:116-137）的枚举改为：

```python
        candidates = list(jobs_root.glob("*/attempt-*/publish-journal.json")) + list(
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

`_quarantine_unproven_publish_jobs` 只从受控目录层级取得 `operation_id`，不得读取 journal 内容来决定数据库主键；attempt 目录名与 journal 身份的一致性由前述 `_recover_locked` 严格校验，失败后本方法按路径中的 job_id 隔离对应任务。其余 `database.get_job` / `finalize_job_terminal` 逻辑不动。

- [ ] **Step 6: 运行测试**

Run: `uv run pytest tests/unit/test_publisher.py tests/unit/test_core.py -q`
Expected: PASS（含 Step 1 新测试）

- [ ] **Step 7: Commit**

```powershell
git add src/dst_manager/infrastructure/filesystem/publisher.py src/dst_manager/application/recovery.py tests/unit/test_publisher.py
git commit -m "feat: 发布日志与清单枚举兼容按 attempt 嵌套的新布局（只读侧）"
```

---

### Task 2: 发布写入侧切换到嵌套布局并删除 reclaim 机制

**Files:**
- Modify: `src/dst_manager/infrastructure/filesystem/publisher.py`（模块 docstring :30-44、`publish` :188、`_publish_locked` :210-298、删除 `_reclaim_previous_attempt` :143-177 与 `_preserve_superseded_journal` :178-186、临时文件名 :325、`_replacement_backup_path` :140 调用点 :268）
- Modify: `src/dst_manager/application/cad_job.py:336`、`editing.py:292`、`repair.py:165`、`revisions.py:207`、`xml_io.py:202`
- Test: `tests/unit/test_publisher.py`（:1637-1815 重试回收测试重写）、`tests/unit/test_core.py`、`tests/integration/test_api.py:524-575`

**Interfaces:**
- Consumes: Task 1 的双 glob 读取（新布局写入的日志立即可恢复）。
- Produces: `RecoverablePublisher.publish(job_id: str, workspace_root: Path, staged: dict[Path, Path | None], *, attempt: int, expected_baselines: ... , before_commit: ..., on_committed: ...) -> Path`——`attempt` 为必填正整数关键字参数；journal 含 `"attempt"` 字段；临时文件名使用 `uid = f"{job_id}~{attempt:03d}"`；同一 job 已有任一 COMMITTED manifest 或当前 attempt 的 jobs/revisions 任一命名空间已占用时，均以 `PUBLISH_OPERATION_CONFLICT` 零改动拒绝。

- [ ] **Step 1: 重写重试相关测试（先写失败测试）**

删除以下 3 个只针对「复用同一目录前回收文件」机制的测试（机制不复存在，其证据保护由 attempt 独占目录替代）：
- `test_stale_snapshot_inconsistent_with_baseline_is_refused`（:1752）
- `test_redundant_replacement_backup_is_reclaimed_on_retry`（:1776）
- `test_replacement_backup_with_unknown_content_is_refused`（:1796）

保留并改写 `test_reusing_committed_operation_is_refused_without_touching_files`：先以 `attempt=1` 成功提交，再以同一 `job_id`、`attempt=2` 发布不同内容，必须抛 `PublishOperationConflictError`；正式文件、attempt-001 manifest/journal 逐字节不变，且不得创建 attempt-002 的 jobs/revisions 目录。另参数化覆盖旧平铺 `revisions/<job_id>/manifest.json`，保证升级后同样拒绝重复提交。

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


def test_same_attempt_job_namespace_conflict_is_refused(tmp_path: Path):
    """仅 jobs attempt 目录存在也属于未恢复现场，禁止覆盖 journal。"""
    job_id = "job-journal-conflict"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    journal_path = tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-001" / "publish-journal.json"
    journal_path.parent.mkdir(parents=True)
    original = b'{"operation_id":"job-journal-conflict","attempt":1,"status":"PUBLISHING","files":[]}'
    journal_path.write_bytes(original)
    with pytest.raises(PublishOperationConflictError):
        RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "before"
    assert journal_path.read_bytes() == original
    assert not (tmp_path / ".dst-manager" / "revisions" / job_id).exists()


@pytest.mark.parametrize("attempt", [0, -1, True, 1.5, "1"])
def test_invalid_attempt_is_rejected_without_creating_manager_files(tmp_path: Path, attempt):
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")
    with pytest.raises((TypeError, ValueError), match="PUBLISH_ATTEMPT_INVALID"):
        RecoverablePublisher().publish(job_id="invalid-attempt", workspace_root=tmp_path, staged={target: staged}, attempt=attempt)
    assert target.read_text() == "before"
    assert not (tmp_path / ".dst-manager").exists()


def test_second_attempt_rollback_still_restores_formal_files(tmp_path: Path):
    """连续两次发布均失败时，attempt-002 仍独立恢复到本次发布前内容。"""
    job_id = "second-rollback"
    target = tmp_path / "target.txt"
    staged = tmp_path / "staged.txt"
    target.write_text("v0")
    staged.write_text("v1")

    def replace(source: Path, target_path: Path):
        raise OSError("注入发布故障")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=1)
    assert target.read_text() == "v0"
    staged.write_text("v2")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert target.read_text() == "v0"
    for attempt in (1, 2):
        journal_path = tmp_path / ".dst-manager" / "jobs" / job_id / f"attempt-{attempt:03d}" / "publish-journal.json"
        assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"
```

> 说明：Task 2 先证明新 attempt 能独立发布；Task 3 再明确断言 attempt-001 的 journal 与 before 快照逐字节保留。任何终态都不得触发发布前自动清扫。

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

`publish` 在解析工作区、创建锁文件路径之前先校验 `type(attempt) is int and attempt >= 1`，失败抛 `ValueError("PUBLISH_ATTEMPT_INVALID")`，确保无效输入不创建 `.dst-manager/`。`_publish_locked` 同步加 `*, attempt: int`，路径派生段（:234-247）替换为：

```python
        manager_dir = workspace_root / ".dst-manager"
        attempt_dir_name = f"attempt-{attempt:03d}"
        revisions_root = manager_dir / "revisions" / job_id
        jobs_root = manager_dir / "jobs" / job_id
        revision_dir = revisions_root / attempt_dir_name
        job_attempt_dir = jobs_root / attempt_dir_name
        before_dir = revision_dir / "before"
        journal_path = job_attempt_dir / "publish-journal.json"
        # operation_id 仍等于 job_id，因此一个 job 最多只能有一个已提交结果；不能因
        # attempt 目录隔离而放宽既有的防重复提交闸门。manifest 文件存在即视为不可
        # 覆盖的提交证据，内容损坏时也不能猜测性忽略。
        committed_manifests = [revisions_root / "manifest.json", *revisions_root.glob("attempt-*/manifest.json")]
        if any(path.exists() for path in committed_manifests):
            raise PublishOperationConflictError(f"同一发布操作已存在提交清单，禁止再次发布：{job_id}")
        # 当前 attempt 任一命名空间已存在都代表重复进入或未恢复现场；尤其是纯新增
        # 文件事务可能已有 journal 而尚未创建 before/revision 目录。
        if revision_dir.exists() or job_attempt_dir.exists():
            raise PublishOperationConflictError(f"同一次尝试的发布命名空间已存在，禁止复用：{attempt_dir_name}")
```

（删除原 `_reclaim_previous_attempt` 调用块；`journal` 字典 :293-298 增加 `"attempt": attempt,`；新增 `operation_uid = f"{job_id}~{attempt:03d}"` 局部变量，:268 `_replacement_backup_path(target, operation_id)` 改传 `operation_uid`，:325 publish_temp 同理，`_commit_existing(entry, publish_temp, operation_id)` :340 改传 `operation_uid`。）

删除 `_reclaim_previous_attempt`（:143-177）与 `_preserve_superseded_journal`（:178-186）整个方法体。模块 docstring（:30-44）中关于「retry_job 复用 job_id 必然第二次面对同一修订目录」的段落改写为：

```
    每次发布尝试独占 ``revisions/<job_id>/attempt-NNN/`` 目录：任务重试由数据库
    attempt 计数严格递增，永远落在新目录上，因此不存在「回收上一次尝试」问题；
    上一次尝试的目录永久保留，不由发布路径自动删除。``journal["operation_id"]``
    保持等于 job_id，是启动恢复与提交后闭环查库的键；``journal["attempt"]``
    用于按路径重建修订目录。
```

- [ ] **Step 4: 更新生产调用点与所有直接测试调用**

- `cad_job.py:336`：`self.publisher.publish(job_id, workspace.root, staged_files, attempt=attempt, expected_baselines=...)`（`attempt` 变量在 `_execute` 作用域内已存在）
- `editing.py:292`、`repair.py:165`、`revisions.py:207`、`xml_io.py:202`：各加 `attempt=1,`（这四类任务不可重试，恒为首次尝试）
- `tests/unit/test_publisher.py`、`tests/unit/test_core.py` 与 `tests/integration/test_api.py` 中所有直接调用 `RecoverablePublisher.publish(...)` 的位置显式补 `attempt`。`tests/integration/test_api.py:524-575` 的旧 reclaim 回归改为真实领取序列：创建任务后先 `claim_next_job("retry-worker")` 取得 `attempt=1` 并用于首次发布，回滚落终态后调用 retry API，再次领取取得 `attempt=2` 并成功发布；断言两个 attempt 的 journal/before 均永久保留，删除 `superseded-journals` 断言。
- 用 `rg -n '\.dst-manager.*(jobs|revisions)|publish-journal\.json|manifest\.json' tests/unit/test_publisher.py tests/unit/test_core.py tests/integration/test_api.py` 枚举磁盘路径断言：凡由本任务新调用 `publish(..., attempt=N)` 生成的路径改为包含 `attempt-NNN`；手工构造、专门验证旧布局兼容的 fixture 保持平铺路径，禁止机械全局替换。

- [ ] **Step 5: 运行测试**

Run: `uv run pytest tests/unit tests/integration/test_api.py -q`
Expected: PASS。测试不得依赖最终收尾才发现遗漏的直接调用或旧平铺路径断言。

- [ ] **Step 6: Ruff 与提交**

Run: `uv run ruff check .`
Expected: 无错误（确认删除 reclaim 后无残留 import）

```powershell
git add src/dst_manager/infrastructure/filesystem/publisher.py src/dst_manager/application/cad_job.py src/dst_manager/application/editing.py src/dst_manager/application/repair.py src/dst_manager/application/revisions.py src/dst_manager/application/xml_io.py tests/unit/test_publisher.py tests/unit/test_core.py tests/integration/test_api.py
git commit -m "feat: 发布写入侧按 attempt 嵌套命名空间并删除目录复用机制"
```

---

### Task 3: 固化 attempt 证据永久保留契约

本任务不新增生产清扫逻辑，只用回归测试证明 Task 2 的新命名空间不会再覆盖或删除旧 attempt。发布前路径禁止调用 `unlink`/`rmtree` 清理旧 journal、before、manifest 或替换证据。

**Files:**
- Test: `tests/unit/test_publisher.py`

**Interfaces:**
- Consumes: Task 2 的 attempt 独占命名空间、跨 attempt COMMITTED 守卫。
- Produces: 无新生产接口；固化「ROLLED_BACK、ABORTED_BASELINE_CHANGED、ROLLBACK_FAILED 与旧平铺现场均永久保留」契约。

- [ ] **Step 1: 写证据保留回归测试**

```python
def test_retry_preserves_rolled_back_previous_attempt_evidence(tmp_path: Path):
    """attempt-002 成功后，attempt-001 的回滚日志与 before 快照仍永久存在。"""
    job_id = "preserve-rolled-back"
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")

    def replace(source: Path, target_path: Path):
        raise OSError("注入首次发布故障")

    with pytest.raises(PublishRolledBackError):
        RecoverablePublisher(replace).publish(job_id, tmp_path, {target: staged}, attempt=1)
    first_journal = tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-001" / "publish-journal.json"
    first_before = tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-001" / "before" / target.name
    journal_bytes = first_journal.read_bytes()
    before_bytes = first_before.read_bytes()

    revision_dir = RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert revision_dir.name == "attempt-002"
    assert first_journal.read_bytes() == journal_bytes
    assert first_before.read_bytes() == before_bytes


@pytest.mark.parametrize("status", ["ABORTED_BASELINE_CHANGED", "ROLLBACK_FAILED"])
def test_new_attempt_never_deletes_previous_terminal_or_unproven_evidence(tmp_path: Path, status: str):
    """旧 attempt 无论已安全终结还是需要人工复核，都不由发布路径自动删除。"""
    job_id = f"preserve-{status.lower()}"
    jobs_attempt = tmp_path / ".dst-manager" / "jobs" / job_id / "attempt-001"
    revisions_attempt = tmp_path / ".dst-manager" / "revisions" / job_id / "attempt-001"
    jobs_attempt.mkdir(parents=True)
    revisions_attempt.mkdir(parents=True)
    journal = {"operation_id": job_id, "attempt": 1, "status": status, "files": []}
    (jobs_attempt / "publish-journal.json").write_text(json.dumps(journal), encoding="utf-8")
    evidence = revisions_attempt / "evidence.bin"
    evidence.write_bytes(b"keep")
    target = tmp_path / "target.txt"
    target.write_text("before")
    staged = tmp_path / "staged.txt"
    staged.write_text("after")

    RecoverablePublisher().publish(job_id, tmp_path, {target: staged}, attempt=2)
    assert (jobs_attempt / "publish-journal.json").is_file()
    assert evidence.read_bytes() == b"keep"
```

- [ ] **Step 2: 运行回归测试**

Run: `uv run pytest tests/unit/test_publisher.py -k "preserve and attempt" -q`
Expected: PASS；若失败，修正 Task 2 实现，禁止引入自动清扫作为修法。

- [ ] **Step 3: Commit**

```powershell
git add tests/unit/test_publisher.py
git commit -m "test: 固化发布 attempt 证据永久保留契约"
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
    """旧平铺 PUBLISHING 残留先被恢复并永久保留，随后新 attempt 正常发布。"""
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
    # 旧布局证据同样永久保留；新 attempt 不复用也不覆盖它。
    assert legacy_journal.is_file()
    assert json.loads(legacy_journal.read_text(encoding="utf-8"))["status"] == "ROLLED_BACK"
    assert backup.read_text() == "before"
```

- [ ] **Step 2: 运行确认失败或通过**

Run: `uv run pytest tests/unit/test_publisher.py -k legacy -q`
Expected: PASS（若 FAIL 则按失败点修正 Task 1-3 的兼容分支——本任务是防线，不是功能）

- [ ] **Step 3: Commit**

```powershell
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

Run: `uv run pytest tests/unit -q`

Run: `uv run ruff check .`
Expected: PASS / 无错误

- [ ] **Step 4: Commit**

```powershell
git add src/dst_manager/infrastructure/filesystem/publish_errors.py src/dst_manager/infrastructure/filesystem/publisher.py
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

Run: `uv run pytest tests/unit -q`

Run: `uv run ruff check .`

Run: `(Get-Content src/dst_manager/infrastructure/filesystem/publisher.py | Measure-Object -Line).Lines`
Expected: PASS / 无错误 / publisher.py 行数下降约 120 行

- [ ] **Step 4: Commit**

```powershell
git add src/dst_manager/infrastructure/filesystem/publish_primitives.py src/dst_manager/infrastructure/filesystem/publisher.py tests/unit/test_publish_primitives.py
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

Run: `uv run pytest tests/unit -q`

Run: `uv run ruff check .`
Expected: PASS / 无错误

- [ ] **Step 3: Commit**

```powershell
git add src/dst_manager/infrastructure/filesystem/publish_journal.py src/dst_manager/infrastructure/filesystem/publisher.py
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

`publish_recovery.py` 内对 `self._rollback`、`self._finish_committed_cleanup`、`self._restore_entry`、`self._restore_backup_by_rename` 等实例方法的调用改为 `publisher._rollback(...)` 形式；`_parse_attempt_dir_name` 与 `_iter_journal_records` 一并迁入为模块私有函数，并把恢复/清单枚举的调用改为直接调用这两个函数。

- [ ] **Step 2: 行数与依赖检查**

Run: `Get-ChildItem src/dst_manager/infrastructure/filesystem -Filter '*.py' | ForEach-Object { [pscustomobject]@{ File = $_.Name; Lines = (Get-Content $_.FullName | Measure-Object -Line).Lines } }`

Run: `uv run ruff check .`
Expected: `publisher.py` ≤ 600 行；ruff 无循环依赖告警

- [ ] **Step 3: 全量验证并提交**

Run: `uv run pytest tests/unit -q`
Expected: PASS

```powershell
git add src/dst_manager/infrastructure/filesystem/publish_recovery.py src/dst_manager/infrastructure/filesystem/publisher.py
git commit -m "refactor: 启动恢复与已提交清单枚举外移到 publish_recovery 模块（纯移动）"
```

---

### Task 9: 测试文件拆分

**Files:**
- Create: `tests/unit/test_publish_journal.py`、`tests/unit/test_publish_recovery.py`、`tests/unit/test_publish_guards.py`
- Modify: `tests/unit/test_publisher.py`、`tests/unit/test_publish_primitives.py`

**Interfaces:** 无生产代码改动；`_deny_journal_replacement` 与 `_JournalDenialWindow` 随日志测试移动，其他辅助函数留在仍使用它们的测试模块；若一个辅助被多个目标模块使用，在各目标模块保留最小同名副本，避免测试模块之间互相 import。

- [ ] **Step 1: 按主题映射搬移测试**

以 `rg -n "^def test_|^class " tests/unit/test_publisher.py` 取当前清单后按下表搬移（函数体逐字移动，不加不改）：

| 目标文件 | 搬移内容（按名匹配） |
|---|---|
| `test_publish_journal.py` | `test_concurrent_journal_writes_use_independent_temporary_files`、`test_transient_journal_denial_is_retried_without_rolling_back`、`test_persistent_journal_denial_fails_before_touching_files`、`test_journal_denial_after_first_replacement_still_restores_files`、`_JournalDenialWindow` 辅助类 |
| `test_publish_recovery.py` | 全部 `test_startup_*`、`test_recovery_rejects_a_publish_holding_the_workspace_transaction_lock`、`test_committed_cleanup_*`、`test_committed_operation_is_not_visible_without_manifest`、`test_archive_*`、`test_committed_callback_runs_after_publish_cleanup_attempt`、`test_crash_before_committed_journal_recovers_batch_with_original_identities`、Task 1/3/4 新增的嵌套恢复、证据保留与 legacy 回归测试 |
| `test_publish_guards.py` | `test_windows_lock_blocks_writers_but_allows_readers`、`test_publish_can_atomically_replace_target_while_write_lock_is_held`、全部 `test_result_guard_*`、`test_windows_result_guard_*`、`test_non_windows_result_guard_*`，以及 Task 2 新增的 attempt 入参、命名空间占用和跨 attempt/旧布局 COMMITTED 守卫测试 |
| `test_publish_primitives.py` | `test_caller_identity_baseline_allows_unchanged_target`、`test_caller_identity_baseline_rejects_same_bytes_replacement_before_publish`、Task 6 新增的原语单测 |
| `test_publisher.py`（保留） | 发布/回滚/提交编排与失败注入路径（其余全部），含 `_SimulatedProcessCrash` |

- [ ] **Step 2: 全量验证与行数核对**

Run: `uv run pytest tests/unit --collect-only -q`（搬移前记录末尾 collected 数）

Run: `uv run pytest tests/unit -q`

Run: `uv run ruff check .`

Run: `Get-ChildItem tests/unit -Filter 'test_publisher*.py' | ForEach-Object { [pscustomobject]@{ File = $_.Name; Lines = (Get-Content $_.FullName | Measure-Object -Line).Lines } }`

Run: `uv run pytest tests/unit --collect-only -q`（搬移后核对 collected 数与搬移前完全一致）

Expected: 用例总数不变；pytest 与 ruff 全绿；各文件向 500 行靠拢

- [ ] **Step 3: Commit**

```powershell
git add tests/unit/test_publisher.py tests/unit/test_publish_journal.py tests/unit/test_publish_recovery.py tests/unit/test_publish_primitives.py tests/unit/test_publish_guards.py
git commit -m "test: 发布事务测试按日志、恢复、平台守卫、原语主题拆分"
```

---

### Task 10: 文档归档与收尾验证

**Files:**
- Modify: `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md`、`docs/dst-manager/README.md`、`changelog.md`、`.planning/plans/dst-manager/README.md`、本文件（status → `completed` 并记录验证）

- [ ] **Step 1: 更新 changelog**

按 `changelog.md` 既有格式追加条目：嵌套 attempt 命名空间、reclaim 目录复用机制删除、全部 attempt 证据永久保留、跨 attempt 防重复提交、旧布局兼容、publisher 拆分（列出 4 个新模块）。

- [ ] **Step 2: 同步权威架构与导航**

更新 `ARCH-DM-001` §8.1 目录树与 §8.2 发布协议：新写入使用 `jobs/<job_id>/attempt-NNN/` 与 `revisions/<job_id>/attempt-NNN/`；重试不复用目录；同一 job 最多一个 COMMITTED manifest；每次 attempt 的 journal 与 before 永久保留；旧平铺布局只读兼容。同步 `updated` 日期。该修订保持 DM-ADR-009「每次操作永久保存原文件与日志」结论，不改变既有 ADR，故无需新增 ADR。

在 `docs/dst-manager/README.md` 当前状态摘要中登记本计划交付，并更新 `.planning/plans/dst-manager/README.md` 中 PLAN-DM-031 的状态。

- [ ] **Step 3: 更新计划状态**

本文件 frontmatter `status` 改 `completed`，`updated` 改为当日，并在文末「实际验证」小节记录：全量 pytest 结果、ruff 结果、PowerShell 行数统计结果。

- [ ] **Step 4: 交付前全量验证**

Run: `uv run ruff check .`

Run: `uv run pytest -q`
Expected: 全绿

- [ ] **Step 5: Commit**

```powershell
git add docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md docs/dst-manager/README.md changelog.md .planning/plans/dst-manager/README.md .planning/plans/dst-manager/PLAN-DM-031-publisher-attempt-namespace-and-split.md
git commit -m "docs: PLAN-DM-031 嵌套命名空间与 publisher 拆分完成归档"
```

---

## 风险与回退

- **最大风险**：Task 2 切换写入布局后，若 Task 1 的读侧分支有漏（如 `recovered.append` 键、隔离路径），崩溃恢复会漏日志。缓解：Task 1 先行合入并独立验证；Task 4 的 legacy 端到端测试 + 既有 60 余个恢复测试为防线。
- **重复提交风险**：attempt 隔离不能把一个 job 变成多个可提交 operation；Task 2 同时保留跨 attempt/旧布局 COMMITTED 闸门，并覆盖「当前 jobs 目录存在但 revisions 目录不存在」的崩溃窗口。
- **证据保留**：所有 attempt 的日志与快照永久保留，不存在自动清扫路径；磁盘保留策略不在本计划范围内，未来必须独立立项。
- **降级不兼容**：旧版本程序读不到嵌套日志。发布说明中注明「升级前确认无进行中发布任务」。
- **回退方式**：每个任务独立 commit；Task 1-4（行为）与 Task 5-9（拆分）分段，任何一段可单独 revert。
