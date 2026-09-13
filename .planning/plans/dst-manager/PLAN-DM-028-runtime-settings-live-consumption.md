---
id: PLAN-DM-028
title: 运行期配置即时生效修复计划
status: completed
owners:
  - dst-manager
created: 2026-09-13
updated: 2026-09-13
related:
  - ARCH-DM-004
  - SPEC-DM-011
  - SPEC-DM-014
  - PLAN-DM-019
  - PLAN-DM-027
---

# 运行期配置即时生效修复计划

> **来源：** 用户缺陷报告（2026-09-13，打包 EXE）：在「设置 → 编号规则 → 不编号图纸关键字」里填入 `封面，扉页` 并保存后，在图纸编辑中新建名为「封面」的子集**仍然被编号**。
> **定位：** 不是 SPEC-DM-014 的领域规则错误（单元测试与预览派生均正确），而是设置中心的接线缺陷：API 进程内服务从未消费 `RuntimeSettings` 快照，界面保存的文件值对预览完全不可见。

**Goal:** 让「设置中心保存的配置对下一次操作立即生效」（ARCH-DM-004 §1.2 目标）在 API 进程内真实成立：预览编号规则、CAD 路径与超时、并发度、租约等运行期字段一律经注入的快照持有者读取，`env`/`.env` 与 `settings.json` 两条通道语义一致，无需重启应用。

**Architecture:** 单点根因、三处修改：

- `interfaces/api.py`：`create_app` 把 `runtime_settings` 一并传给 `DstManagerService`（原先只用于注册 `/api/settings`、`/api/about` 端点）。
- `application/service.py`：新增统一读取口 `_live_settings()`（注入时先 `refresh_if_changed()` 再取 `current()`；未注入时退化为 `self.settings`），并在 `_capability()` 默认值与布局读取超时两处改用它。
- 功能域模块：`application/editing.py`（编号规则 `SuffixOptions`、`cad_max_parallel`）与 `application/recovery.py`（`worker_lease_seconds`）改用读取口。

**Tech Stack:** Python 3.12 + uv + pydantic-settings + FastAPI/TestClient；无前端与 DST 落盘改动。

**Spec:** [SPEC-DM-011](../../../docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md)（SC："每项修改保存后无需重启即对下一次操作生效"）；影响面描述见 [SPEC-DM-014](../../../docs/dst-manager/specs/SPEC-DM-014-unnumbered-subset-keywords.md)（不编号关键字的用户可见效果）；实现口径见 [ARCH-DM-004 §2.4](../../../docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)。

## Global Constraints

- 全程简体中文注释、文档、commit message；标识符与 API 字段保持英文。
- 未注入 `RuntimeSettings`（`cli serve`、大量既有测试）时必须与修复前**完全一致**：读取口退化为构造期 `self.settings`，既有「直接替换 `service.settings` 为替身」的测试继续有效。
- 启动期字段（`data_dir`/`draft_dir`/`database_url`）仍只读构造期快照（ARCH-DM-004 §2.2 非目标），不因本次修复变为运行期可变。
- 不新增设置项、不改 `/api/settings` 契约、不改 DST 落盘与发布链路。

## 缺陷机理（根因）

1. `DstManagerService.__init__(settings, *, runtime_settings=None)` 仅在被注入时记住快照持有者；`_snapshot_settings()` 注入时取运行期快照，否则退化为构造期属性。
2. `create_app(settings, runtime_settings=...)` 把持有者**只**用于端点注册，构造服务时只传 `settings` → `service._runtime is None`。
3. 桌面壳 `run_desktop` 传入的 `settings` 是 `Settings()`（默认值 + `env`/`.env`），**不含** `settings.json` 覆盖；因此服务内 `self.settings.<运行期字段>` 恒为启动期值。
4. 结论：设置中心保存的值改变了 `RuntimeSettings` 快照与文件，但预览仍按旧值派生编号——用户看到「填了关键字仍编号」，且**重启也不会好**（文件值同样进不了构造期 `settings`）。
5. 影响面不止本缺陷：编号后缀开关/后缀类型、CAD Core Console 与插件路径、`cad_timeout_seconds`、`cad_max_parallel`、`worker_lease_seconds` 在 API 进程内同样陈旧（Worker 侧已在 PLAN-DM-019 任务 6 正确接线）。

## Tasks

### Task 1: 复现与失败测试（TDD RED）

- [x] **Step 1**：写集成测试 `tests/integration/test_api_settings.py::test_saved_keywords_apply_to_next_preview_without_restart`（PUT 关键字 → 同进程预览先前插入「封面」子集 → 断言 `number_range` 为 `000`，既有子集仍为 `001`）。
- [x] **Step 2**：写集成测试 `test_settings_file_change_while_running_applies_to_next_preview`（外部手编 settings.json → 预览立即生效）。
- [x] **Step 3**：运行确认失败：`['001', '000'] == ['000', '001']`、`'001' == '000'` —— 正是用户症状（子集被编号）。

### Task 2: 服务读取口与接线（TDD GREEN）

- [x] **Step 1**：`application/service.py` 新增 `_live_settings()`：注入时 `refresh_if_changed()` 后取 `_snapshot_settings()`；`SettingsSchemaOlder`（旧 Schema 只读）时保持上一份快照不抛异常。docstring 明确"只用于运行期字段，启动期字段读 `self.settings`"。
- [x] **Step 2**：`_capability()` 默认值 `settings or self._live_settings()`；`get_layout_names` 的 `cad_timeout_seconds` 改用读取口。
- [x] **Step 3**：`application/editing.py` 预览路径用 `live = self._live_settings()` 构造 `SuffixOptions`，`_estimate_cad_execution` 用 `live.cad_max_parallel`。
- [x] **Step 4**：`application/recovery.py` 的 `worker_lease_seconds` 改用读取口。
- [x] **Step 5**：`interfaces/api.py` `create_app` 改为 `DstManagerService(settings, runtime_settings=runtime_settings)` 并留注释说明后果。
- [x] **Step 6**：运行 Task 1 的两个测试转绿（`tests/integration/test_api_settings.py` 20 passed）。

### Task 3: 读取口单元测试

- [x] **Step 1**：`tests/unit/test_worker_settings_propagation.py` 追加 3 例：外部改文件即刷新、未注入时退化为实例属性（含 `SimpleNamespace` 替身）、旧 Schema 文件保持上一份快照不抛异常；模块 docstring 补「进程内运行期字段读取」要点。
- [x] **Step 2**：`uv run pytest tests/unit/test_worker_settings_propagation.py -q` → 7 passed。

### Task 4: 文档与变更记录

- [x] **Step 1**：ARCH-DM-004 §2.4 增补第 6 条（API 进程内运行期字段读取口、覆盖点清单、启动期字段例外、旧 Schema 容忍）+ §7 测试策略条目 + §8 实现注意点（直接写 `self.settings.<运行期字段>` 即缺陷）。
- [x] **Step 2**：本计划落盘；`.planning/plans/dst-manager/README.md` 增索引行。
- [x] **Step 3**：根 `changelog.md` 追加修复条目（用户症状、根因、改动点、验证、遗留）。

## 实际验证

| 项 | 命令 | 结果 |
| --- | --- | --- |
| RED 证据 | `uv run pytest tests/integration/test_api_settings.py -q` | 修复前：2 failed（`['001','000'] == ['000','001']`、`'001' == '000'`） |
| 新增用例 | `uv run pytest tests/integration/test_api_settings.py tests/unit/test_worker_settings_propagation.py -q` | 27 passed（20 + 7） |
| 全量回归 | `uv run pytest -q --junitxml=...` | **1451 tests / 0 failures / 0 errors / 72 skipped**（修复前 1446；+5 用例） |
| 静态检查 | `uv run ruff check .` | All checks passed!（EXIT=0） |
| 前端 e2e 全量 | `npx playwright test`（29 个 spec，真实后端 + 隔离 settings.json） | **490 passed / 0 failed**（exit 0，3.1m） |
| 前端构建 | `npm run build`（= `check:api` + `check:i18n` + `vue-tsc -b` + `vite build`） | EXIT=0（`✓ built in 1.46s`） |
| 真实 CAD 系统测试 | `DST_MANAGER_RUN_AUTOCAD=1 uv run pytest tests/system_autocad -q` | 未执行（本修复不涉及 SCR/插件/布局重建，且本机无相应环境启用） |
| 用户场景复现 | 临时脚本：PUT `封面，扉页` → 预览插入「封面」 | 保存前 `[[1,'001',['001']],[2,'002',['002']]]` → 保存后 `[[1,'000',['000']],[2,'001',['001']]]`；关键字子串命中（「扉页说明」）同样 `000` |

## 门禁分级与证据缺口（如实记录）

参考 [GUIDE-DM-001](../../../docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md)：本修复**无前端渲染层改动**（无新增控件、无视觉变化），故按 S 级口径执行最小充分门禁：

- 已执行：G0（全量 pytest 1451 项）、G1（Ruff 通过）、G5（`npm run build` EXIT=0）、G6/G7 相关项（e2e 全量 490 passed，真实后端）。
- 未重开：G3/G4（无新视觉设计、无新冻结件）、G8（无新增同态截图需求）、G9（真实桌面验收）。
- **G9 待办**：打包 EXE 重新构建后，需在真实桌面确认「设置 → 编号规则 → 不编号图纸关键字」保存后新建「封面」子集不再编号（本次修复的产品级验收）。构建命令：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1`。
- **G8 待办**（用户 2026-09-13 裁定暂不补）：本项无新视觉、无新控件行，G8 沿用 SPEC-DM-014 未闭合的文本行截图缺口。两项已登记为待办：`.planning/todos/dst-manager/2026-09-13-unnumbered-keywords-gate-gaps.md`。

## 后续项

- `cardinality_frontier` 会让不编号子集之后的子集进入 `rename_only`（多一次 CAD 处理，图号不变）——PLAN-DM-027 已记录，本次不优化。
- 若后续新增运行期设置项，必须同时在服务内使用 `self._live_settings()` 并在 `tests/integration/test_api_settings.py` 或 `tests/unit/test_worker_settings_propagation.py` 补「保存后即时生效」回归。
