# PLAN-DM-036 最终复核残差项

日期：2026-09-24

状态：待办（未立项；来源 PLAN-DM-036 整分支最终复核与修复波再复核）

关联：`PLAN-DM-036`、`PLAN-DM-037`、`SPEC-DM-017`、`SPEC-DM-018`、`ARCH-DM-001`

## 背景

PLAN-DM-036（标准驱动的新图纸集创建）9 个任务全部实施并通过自动化门禁；整分支最终复核给出「With fixes」，修复波（提交 `8bc3daf`）已处理 1 条 Important（创建任务租约续期）与 3 项升级项（SCR seam 单测、候选列表损坏文档 500、空目录名退化），再复核确认 4 项全部 ADDRESSED、无新增 Critical/Important。

本文件登记复核后**未修**的残差项，供后续计划立项时取舍。台账（含逐条裁定与理由）原在 `.superpowers/sdd/PLAN-DM-036-standard-driven-sheetset-creation/progress.md`，该目录为一次性工作区，已按流程删除；此处为持久记录。

## 合并前已知、可延后（复核者已 triage）

### 1. 同一「已发布文件是不可信输入」缺陷类仍在候选列表之外

- `StandardStore.get`/`get_document`（`infrastructure/standards/store.py:163-180`）与 `application/standards.py` 的工作区打开路径仍直接 `read_text` + `json.loads`：损坏的已发布 `document.json` 会让 GET 标准详情、标准保存的已发布检查、工作区标准解析冒泡 500。
- 本轮只收口了创建候选列表端点（`application/creation_assets.py` + `store.py::_read_document`）。
- 同类的 `RecursionError`（病态深嵌套 JSON）也未纳入。

### 2. 创建任务租约与单次 CAD 调用的关系

- 默认 `cad_timeout_seconds=600` > `worker_lease_seconds=120`，单次 Core Console 调用可能超过一个租约周期；当前设计是「无法在调用内穿插续租，失租后在下一边界立即停手（不发布、不落终态）」，代价是多跑一次 CAD。
- 生产侧心跳口径（`application/creation_execution.py` 的 `min(30.0, lease_seconds / 3)`）没有测试钉住；普通任务侧有对应钉法可参照。

### 3. 创建发布路径的其余健壮性

- 已提交日志的 `revision_dir` 只校验「是字符串」，`""` 会把归档写进当前目录；收紧为「必须位于 creation-jobs 根内」会改动既有语义，需先裁决。
- `root.exists()` 的权限类 `OSError`（EACCES）仍会逃出启动恢复路径（环境类）。
- 标准快照 `_restore_snapshot` 用 `copytree`，中断留半份快照且补登记不重做；建议改原子换名。
- `_resume_committed_creation` 的 `published is None` 分支当前不可达；`_isolate_registration_failure` 忽略 `finalize_job_terminal` 返回值。
- `atomic.py` 只在 `OSError` 时清理临时文件，`UnicodeEncodeError` 会留下 0 字节 `.tmp`（不匹配恢复 glob，无功能影响）。

### 4. 前端创建域

- 409 `CREATION_DRAFT_CONFLICT` 后不刷新 `state.revision`，重试会永久 409；持续失败时用户既不能保存也不能离开，唯一出口是刷新页面（会用服务端草稿覆盖未落盘输入）。建议补「冲突后按新修订重试或显式强制离开」。
- 创建任务订阅无 `onUnmounted` 清理：执行中返回欢迎页后 `EventSource` 仍存活，终态到达会继续 `writeStoredDraftId("")`（服务端草稿变孤儿）——与 Task 9 报告所述「卸载后不再订阅」不符。
- `SUCCEEDED` 但 `workspace_id` 为空时静默无动作（当前生产路径不可达，但新增调用方会变成「任务成功却永不进入工作区」）。
- 标准详情入口绕过可用性过滤：候选缺失时合成 `available: true`，不可用标准仍能建草稿，用户到第三阶段才看到原因。
- `LAYOUT_NAME_INVALID`/`DUPLICATE_LAYOUT_NAME` 带 `group_id` 不带 `property_id`，评审页会为这类「派生名冲突、无直接可编辑输入」的诊断渲染「返回修改第 N 项」并聚焦图名输入。
- 「全部检查通过」徽章由前端 `severity === "error"` 计数决定，按钮门禁用后端 `executable`；今天等价，后端引入新严重级别会不一致。
- 10 个未使用语言键；`useStartNavigation.test.ts` 用例名与本轮改动脱节且 `createSheetsetIdentity` 无单测；`store.ts` 的 seed 分支绕过 `adoptDraft`（生产无 seed）；张数输入清空回落为 `0`；重复图名前端用 `toLocaleLowerCase()` 而后端用 `casefold()`（仅影响即时提示）。

### 5. 其它

- 容量软上限：`application/creation_job.py` 608 行、`web/src/features/creation/store.ts` 509 行（`CreationStore` 公共方法约 30 个）、`database.py` 884 行（既有超限 + 本次 +88）；测试文件 `test_creation_job.py` 1251、`test_creation_api.py` 1107、`test_project_publisher.py` 1059、`test_created_project_opens.py` 717 行。
- SCR seam 单测（`tests/unit/test_autocad_worker.py`）不是 golden script：`-LAYOUT _Template` 两参数互换、把 `DstDeleteLayouts` 换成任意命令、删除 `_Set` 都不会失败。
- 测试输出噪声：`database.py:273` 的 `session.get(WorkspaceRow, workspace_id)` 在 `workspace_id IS NULL` 时抛 SQLAlchemy `SAWarning: fully NULL primary key identity cannot load any object`（本计划新增的可空 `workspace_id` 引入，未来 SQLAlchemy 版本可能改为报错）。
- 已延后的测试健壮性项：`tests/integration/test_creation_job.py` 断言机器绝对路径 `C:\Projects\新建项目` 不存在（本机恰好存在该目录即失败）；`test_recovery_contains_a_rollback_journal_with_a_lone_surrogate` 两个参数化 id 走同一路径。

## 未完成的人工验收门（计划保持 active 的原因）

- **官方图纸集管理器界面打开性**：新建项目 DST 需由用户在真实 AutoCAD（2016/2020）的 Sheet Set Manager 界面打开确认（子集、图号、标题、布局与自定义属性）。机器可验证面（每组主 DWG、全部布局/Handle、DST 引用、`repair=VALID`、往返一致）已由 `tests/system_autocad/test_creation_workflow.py` 在 2016/2020 双版本跑通（2 passed）。
- 完成该人工验收后，方可将 `PLAN-DM-036` 的 `status` 由 `active` 置为 `completed`。
