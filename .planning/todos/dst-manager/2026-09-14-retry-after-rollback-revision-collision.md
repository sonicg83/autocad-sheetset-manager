# 回滚过的发布任务重试必然失败（重试复用同一 job_id 撞已存在的 before 快照）

日期：2026-09-14

状态：已完成（2026-09-14 实施并验证，(a)、(b)、(c) 三项均已交付）

同批已完成：(a) 发布日志有界退避重试、(b) 回滚后重试的修订目录安全复用、(c) 失败真因可见（均见 `changelog.md` 2026-09-14 章节）

关联：`ADR-DM-004`（2026-09-14 补记：修订目录复用契约）、`ARCH-DM-001` §8.1/§8.2、`changelog.md` 的 2026-09-14 章节（发布日志瞬时被拒导致整批回滚 `PUBLISH_ROLLED_BACK`）

## 已完成内容（(a) + (c)，2026-09-14，与本文档同批交付）

用户报告界面「实施进度」出现 `PUBLISH_ROLLED_BACK` 后完成的两项修复，均针对**根因**与**可诊断性**，不涉及本文件登记的 (b)：

### (a) 发布日志原子写加入有界退避重试

- 新增 `src/dst_manager/infrastructure/filesystem/atomic.py`：`atomic_write_text` 每轮使用**新** uuid 临时名后 `os.replace`（旧临时名可能仍被过滤驱动持有）；`retry_transient_contention` 对 `WinError 5/32/33` 与 `EACCES/EAGAIN/EBUSY/ETXTBSY` 做 5 次有界指数退避（20ms 起翻倍、上限 200ms，累计约 0.3s），永久错误（如 `ENOENT`）立即抛出，清理临时文件失败不掩盖原始错误。
- `publisher.py`：`_write_journal` 改走该入口，预算耗尽时包装为新增 `PublishJournalWriteError`（`code = PUBLISH_JOURNAL_WRITE_FAILED`，继承 `OSError` 以保持「日志写失败 = 普通发布故障」语义），消息仅在确认属瞬时争用时追加「已按瞬时占用退避重试 5 次」提示；`_archive_journal` 的 `copy2` 与 manifest 写入同样纳入重试。
- 取舍：`_rollback` 起始的 `ROLLING_BACK` 写入、两个故障分支的回滚前写入与 `ROLLBACK_FAILED` 诊断写入改为 best-effort（日志是诊断记录，磁盘正式文件一致性优先）；`_rollback` 末尾的终态 `ROLLED_BACK` 写入刻意保持严格（持续不可写属环境级故障，沿用「无法证明 → 人工复核」设计）。

### (c) 失败真因可见

- `cad_job.py`：`PUBLISH_ROLLED_BACK`/`PUBLISH_RECOVERY_FAILED`/`BLOCKED_FILE_LOCK`/`CAD_TIMEOUT`/`CAD_PROCESS_FAILED` 操作事件补 `error=`（此前 `logs/events.jsonl` 无据可查）。
- `xml_io.py`：原先丢弃 `PublishRolledBackError` 的分支改为 `finalize_job_terminal(..., "PUBLISH_ROLLED_BACK", str(exc))`。
- Web：`JobStatusPanel.vue` 渲染 `error_detail`（`jobs.job.errorDetail`）；`useJobMonitor` 的失败与 NEEDS_REVIEW toast 追加真因后缀（`jobs.toasts.detailSuffix`，中英键与插值对称）。DB/API/`schema.d.ts` 无需改动。

### 验证（2026-09-14）

`uv run ruff check .` EXIT=0；`uv run pytest -q` EXIT=0（1464 tests，较修复前 +13，72 skipped）；`npm run build` EXIT=0（`check:api` 无漂移、`check:i18n` 946 键 / 9 域）；`npm run test:unit` 48 passed；`npx playwright test` 489 passed / 2 flaky（重试通过）/ 0 failed。

### 与本文档的边界

(a) 消除了瞬时争用导致的回滚，(c) 让失败原因可读；但「对已回滚的任务点『安全重试』」这条路径仍然 100% 失败，即下面的 (b)，已在本文件后续章节修复。

## 已完成内容（(b)，2026-09-14，用户追加授权）

### 选定的修复方向

采用「可能的修复方向」中的**方向 1**：在 `publish()` 内（持 `WorkspaceTransactionLock`）识别同一 `operation_id` 的既有修订目录。未采用方向 2（按 attempt 隔离目录）与方向 3（改用新 `operation_id`）：前者会把修订目录布局与 `revisions/*/manifest.json` 的既有契约一起改掉，后者需同步修订索引与恢复逻辑的关联字段，风险明显高于收益。

### 实现

- `publisher.py` 新增 `PublishOperationConflictError`（继承 `PublishRecoveryError`，`code = PUBLISH_OPERATION_CONFLICT`），使冲突落入既有的「隔离为 `NEEDS_REVIEW`」处置，而不是可重试的 `FAILED`（避免 `retry_job` 放行导致无限失败循环）；该异常在进入发布 try 块之前抛出，不触发回滚，也不被 `except (OSError, PublishBaselineError)` 捕获。
- `_publish_locked` 中原来的 `before_dir.mkdir(parents=True, exist_ok=False)` 改为 `_reclaim_previous_attempt(...)`：`revision_dir/manifest.json` 已存在（已提交修订）→ 拒绝；`before` 快照或残留 `.<名称>.<operation_id>.replaced` 与当前基准逐字节相同（`_verify_baselines` 已证明基准等于正式文件当前内容与身份）→ 判定为冗余副本，`before` 目录 `exist_ok=True` 复用并按需覆盖、`.replaced` 走 `atomic.retry_transient_contention` 回收；证据不足（内容不一致、基准缺失）→ 拒绝并原样保留现场。
- 新增 `_preserve_superseded_journal`：旧 `publish-journal.json` 在重试覆盖前用 `copy2` 留档到 `revisions/<operation_id>/superseded-journals/publish-journal.<NNN>.json`（序号由目录扫描得出）。用复制而非移动，保证「回收完成、新 `PREPARED` 未写入」的崩溃窗口下启动 `recover()` 仍能看到旧日志。
- 新增 `_before_snapshot_path` / `_replacement_backup_path` 两个 static 辅助，供回收与正式条目循环共用，避免路径推导两处漂移。
- `cad_job.py` 的 `PublishRecoveryError` 分支由硬编码 `PUBLISH_RECOVERY_FAILED` 改为 `exc.code`（事件名与 `error_code` 两处，基类同名故既有行为不变）。
- 保留原有 `FileExistsError("PUBLISH_REPLACE_BACKUP_EXISTS")` 检查作为防御性校验；`.tmp` 残留无需处理（`copy2` 直接覆盖）。

### 新增回归测试（先红后绿，红态已实测）

- `tests/unit/test_publisher.py` +6：回滚后同一 `operation_id` 重试发布成功（断言 `before` 快照仍为首次尝试原始字节、旧日志已留档、`recover()` 无待办、`list_committed_operations` 仅一条）；复用后再次整批回滚仍还原为发布前字节且无 `.tmp`/`.replaced` 残留；已提交修订再次发布被拒且正式文件与 `COMMITTED` 日志未被触碰；残留快照与基准不一致时拒发且不删现场；与基准相同的 `.replaced` 被回收；内容不明的 `.replaced` 拒发。新增测试辅助 `_JournalDenialWindow`：只在日志已出现 `api_state == "SUCCEEDED"` 时持续拒绝写入，保证注入点一定发生在正式文件被替换之后（与现场整批回滚形态一致）。
- `tests/unit/test_core.py` +1：runner 级断言冲突码 → `NEEDS_REVIEW` 且事件与任务记录均带真因。
- `tests/integration/test_api.py` +1：回滚 → `POST /api/jobs/{job_id}/retry` 返回 200/`QUEUED` → 同一 `operation_id` 再次发布成功，正式 DST 等于暂存字节，且修订目录保留 `before` 与 `superseded-journals`。
- 红态证据：临时注入旧的 `before_dir.mkdir(parents=True, exist_ok=False)` 后，`test_retry_after_rolled_back_publish_reuses_revision_dir`（单测）与 API 集成测试均复现 `FileExistsError: [WinError 183] ...\revisions\<job>\before`，与现场 `242826c0` attempt-002 的 `error_detail` 一致。

### 验证（2026-09-14，(b) 交付时）

`uv run ruff check .` EXIT=0；`uv run pytest -q` EXIT=0（**1400 passed / 72 skipped**，共 1472 项，较 (a)+(c) 交付后 +8）；前端未改动，未重跑构建与 Playwright。

## 问题（(b) 原始描述，已修复，以下行号为修复前）

`database.retry_job`（`src/dst_manager/infrastructure/persistence/database.py`，`POST /api/jobs/{job_id}/retry` 经 `interfaces/api.py`）允许 `FAILED`/`BLOCKED_FILE_LOCK`/`ROLLED_BACK` 任务重试，且**复用同一 `job_id`**（仅把状态重置为 `QUEUED` 并清空 `error_code`/`error_detail`），但不清理该任务的发布修订目录。

而 `RecoverablePublisher.publish` 在准备阶段执行 `before_dir.mkdir(parents=True, exist_ok=False)`（`revision_dir = <workspace>/.dst-manager/revisions/<operation_id>`，见 `publisher.py:169-172`）。首次尝试失败并回滚后，`revisions/<job_id>/before` 仍然存在（实测残留 `['before', 'plan']`），因此 attempt-002 的 `publish()` 抛 `FileExistsError(183, ...)`；该异常不在 `publish()` 的受控分支内，逃逸到上层通用处理器，记为 `FAILED` + `FILEEXISTSERROR`，且不改写 `publish-journal.json`。

现场证据：`sample\project2 - copy\.dst-manager\jobs\242826c0-406c-4343-8cb9-ffdaf6fc5886` attempt-002 的 `error_detail` 为 `[WinError 183] ... revisions\242826c0-...\before`。

即：**任何回滚过（或准备阶段失败）的发布任务，重试 100% 失败**——界面上的「安全重试」按钮对这类任务必然报错，属用户可感知缺陷。

## 复现条件 / 执行前提

- 任一工作区完成一次失败并回滚的发布（例如让 `publish-journal.json` 的 `os.replace` 持续被拒）；
- 对该任务点击「安全重试」或在 API 调 `POST /api/jobs/{job_id}/retry`；
- 观察结果为 `FAILED` + `FILEEXISTSERROR`，`error_detail` 指向已存在的 `revisions/<job_id>/before`。

补充：同一 `operation_id` 下 `publisher.py:194` 的 `.replaced` 备份与 `publisher.py:250` 的 `.tmp` 暂存名也会复用，回滚/崩溃残留同样需要纳入判断。

## 可能的修复方向（方向 1 已采用，其余备选不采用）

1. 在 `publish()` 内（持 `WorkspaceTransactionLock`）识别同一 `operation_id` 的既有修订目录：校验既有 `before` 快照与当前基准一致后复用，并清理上一轮残留的 `.tmp`/`.replaced`，把不一致情形转为受控错误码而非通用 `FILEEXISTSERROR`（**已采用**）；
2. 重试时按 `attempt` 隔离修订目录（如 `revisions/<job_id>/<attempt>`）；
3. 重试时改用新的 `operation_id` 并保留原任务关联（需同步 `revisions` 表与恢复逻辑的关联字段）。

无论选哪条，都必须覆盖：重试成功路径、重试再次失败后的整批回滚、崩溃中途重试、以及启动恢复与重试并发。

## 完成条件（全部满足）

1. 选定方向并新增/修订相应 ADR 或 Spec 条目 —— **已满足**：采用方向 1；`ADR-DM-004` 新增 2026-09-14 补记（复用前提、`PUBLISH_OPERATION_CONFLICT`、`superseded-journals/` 留档），`ARCH-DM-001` §8.1 目录树与 §8.2 事务步骤同步。
2. 补回归测试（`tests/unit/test_publisher.py` 或 `tests/unit/test_database.py`）：回滚后重试不再失败，且失败批次仍可整批回滚、修订历史与发布日志一致 —— **已满足**：`tests/unit/test_publisher.py` 新增 6 例（含复用后再次回滚、已提交修订拒复用、日志留档断言）。
3. 集成测试覆盖 `POST /api/jobs/{job_id}/retry` 在 `ROLLED_BACK` 状态下的语义（含 Web 侧重试按钮的可见结果） —— **已满足**：`tests/integration/test_api.py::test_retry_after_rolled_back_publish_reuses_revision_dir`。Web 侧重试按钮沿用既有链路：冲突落 `NEEDS_REVIEW` 时按钮隐藏（面板仅对 `FAILED`/`ROLLED_BACK`/`BLOCKED_FILE_LOCK`/`NEEDS_REVIEW` 显示重试，接口对 `NEEDS_REVIEW` 返回 409，属既有行为），已回滚任务的正常重试路径在界面与修复前一致但不再失败。
4. 完成后回填对应变更记录并归档本文件 —— **已满足**：`changelog.md` 2026-09-14「修复 (b)」章节已回填；本文件状态改为「已完成」并保留在 `.planning/todos/dst-manager/`（`changelog.md` 引用本路径）。
