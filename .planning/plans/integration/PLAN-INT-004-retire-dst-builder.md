---
id: PLAN-INT-004
title: DST Builder 直接退场实施计划
status: proposed
owners:
- integration
created: 2026-09-21
updated: 2026-09-21
related:
- RFC-INT-003
- ARCH-INT-002
- PRD-DB-001
- ARCH-DB-001
- SPEC-DB-001
- PLAN-INT-003
---

# DST Builder 直接退场实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 DST Builder 的全部可运行产品面，同时保留历史决策、Manager 迁移链和普通 DST/DWG 兼容性。

**Architecture:** 先以仓库契约测试固定“Builder 不再可运行、历史资料仍可追溯”的边界，再依次移除 Python/前端/插件/发布入口，最后更新单产品治理与验证编排。不得把 Builder 实现搬入 Manager；后续新建能力由 PLAN-DM-035 与 PLAN-DM-036 重新实现。

**Tech Stack:** Python 3.12、UV、pytest、Ruff、Vue 3/TypeScript/Vite、PowerShell、.NET Framework 4.8、Markdown。

**Spec:** [`docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md`](../../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)

## Global Constraints

- 保留 `migrations/versions/0007_db001_builder_handoff.py` 与 `0008_drop_handoff_sources.py`，保证 Manager 全新数据库迁移链可重放。
- 保留 `docs/dst-builder/`、既有 RFC/ADR/Plan/Memo 和 changelog 作为历史记录；只更新状态、索引和取代关系。
- 不兼容 `project.dstb`，不提供 Builder 草稿迁移器。
- 已发布 DST/DWG 必须继续通过既有 `/api/workspaces/open` 打开。
- 删除文件使用明确清单；不得触碰 `legacy/`、`lagacy/`、`sample/` 或用户未提交改动。
- 每个任务更新 `changelog.md`，提交信息使用简体中文。

## Review Focus

- 全新数据库仍能经过 0007/0008 升级到 head；Task 4 的迁移测试必须覆盖。
- 打包、CLI、setup 和文档中不能残留可启动 Builder 的入口；Task 2/3 的退场契约测试必须覆盖。
- Manager 发布脚本与 AutoCAD 插件工程不能因删除 Builder 项目而失效；Task 3 必须执行双版本非 CAD 构建门禁。
- `PLAN-INT-003` 的双产品测试计划会被本计划部分取代；Task 4 必须明确取代关系，不能留下错误执行入口。
- 历史文档可检索 Builder，但现役 README、脚本和包元数据不得把它描述为可用产品；Task 4 必须分别断言允许和禁止范围。

---

### Task 1: 固定 Builder 退场仓库契约

**Files:**
- Create: `tests/unit/test_builder_retirement.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: RFC-INT-003 的退场清单。
- Produces: `test_builder_runtime_surfaces_are_absent()` 与 `test_builder_history_is_preserved()`，供后续删除任务作为安全网。

- [ ] **Step 1: 写入会因现有 Builder 产品面而失败的契约测试**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_builder_runtime_surfaces_are_absent() -> None:
    forbidden = [
        "src/dst_builder",
        "builder-web",
        "builder_migrations",
        "builder_alembic.ini",
        "packaging/dst-builder.spec",
        "packaging/builder_entry.py",
        "plugins/src/DstBuilder.AutoCAD",
        "plugins/tests/DstBuilder.AutoCAD.Tests",
        "scripts/build_builder_plugins.ps1",
        "scripts/build_builder_release.ps1",
        "scripts/export_builder_openapi.py",
        "tests/builder",
    ]
    assert [path for path in forbidden if (ROOT / path).exists()] == []


def test_builder_history_is_preserved() -> None:
    required = [
        "docs/dst-builder/README.md",
        "docs/integration/rfcs/RFC-INT-001-dst-builder-product-establishment.md",
        "migrations/versions/0007_db001_builder_handoff.py",
        "migrations/versions/0008_drop_handoff_sources.py",
    ]
    assert [path for path in required if not (ROOT / path).is_file()] == []
```

- [ ] **Step 2: 运行目标测试并确认第一条失败、历史保留测试通过**

Run: `uv run pytest tests/unit/test_builder_retirement.py -q`

Expected: `test_builder_runtime_surfaces_are_absent` 列出当前 Builder 路径并失败；`test_builder_history_is_preserved` 通过。

- [ ] **Step 3: 在 changelog 记录退场契约安全网**

写明新增测试固定删除范围与历史保留范围，尚未删除实现。

- [ ] **Step 4: 提交契约测试**

```powershell
git add tests/unit/test_builder_retirement.py changelog.md
git commit -m "固定 Builder 退场仓库契约"
```

### Task 2: 删除 Python、迁移项目与产品入口

**Files:**
- Delete: `src/dst_builder/`
- Delete: `tests/builder/`
- Delete: `builder_migrations/`
- Delete: `builder_alembic.ini`
- Delete: `packaging/dst-builder.spec`
- Delete: `packaging/builder_entry.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `scripts/setup.bat`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1 的禁止路径契约。
- Produces: 仅含 `dst-manager` 的 Python 包和 CLI；Manager 依赖集合保持不变。

- [ ] **Step 1: 从包元数据移除 Builder CLI 与包**

将 `pyproject.toml` 调整为：

```toml
[project.scripts]
dst-manager = "dst_manager.interfaces.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/dst_manager", "src/dst_platform"]
```

- [ ] **Step 2: 删除明确列出的 Builder Python、独立迁移与打包文件**

删除本任务 `Files` 中的目录和文件；不得删除 Manager 的 `migrations/versions/0007_*` 与 `0008_*`。

- [ ] **Step 3: 移除 setup 与 README 的运行入口**

从 `scripts/setup.bat` 删除所有 `DST_BUILDER_*` 环境变量写入，从根 README 中删除 Builder 启动、发布和现役产品描述，保留历史文档链接并标注 retired。

- [ ] **Step 4: 同步锁文件并运行目标契约**

Run: `uv lock && uv run pytest tests/unit/test_builder_retirement.py -q`

Expected: 锁文件成功更新；两个退场契约测试通过。

- [ ] **Step 5: 验证 Manager CLI 与导入面**

Run: `uv run dst-manager --help; uv run python -c "import dst_manager; import dst_platform"`

Expected: 两条命令退出码均为 0；不再存在 `dst-builder` console script。

- [ ] **Step 6: 提交 Python 产品面退场**

```powershell
git add pyproject.toml uv.lock scripts/setup.bat README.md README.en.md changelog.md src tests builder_migrations builder_alembic.ini packaging
git commit -m "移除 Builder Python 产品面"
```

### Task 3: 删除 Builder Web、插件与发布工具

**Files:**
- Delete: `builder-web/`
- Delete: `plugins/src/DstBuilder.AutoCAD/`
- Delete: `plugins/tests/DstBuilder.AutoCAD.Tests/`
- Delete: `scripts/build_builder_plugins.ps1`
- Delete: `scripts/build_builder_release.ps1`
- Delete: `scripts/export_builder_openapi.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1 的禁止路径契约与 Task 2 的单 CLI 包。
- Produces: 只构建 Manager Web、Manager 插件和 Manager Windows 发布包的工具链。

- [ ] **Step 1: 运行退场契约并确认剩余产品面仍使测试失败**

Run: `uv run pytest tests/unit/test_builder_retirement.py::test_builder_runtime_surfaces_are_absent -q`

Expected: FAIL，并列出 `builder-web`、Builder 插件和 Builder 发布脚本。

- [ ] **Step 2: 删除独立前端、插件工程和发布脚本**

删除本任务列出的 Builder 目录与脚本；Manager 的 `DstManager.AutoCAD` 工程及 `scripts/build_plugins.ps1`、`scripts/build_release.ps1` 保持原有输出路径。

- [ ] **Step 3: 运行退场契约和 Manager Web 构建**

Run: `uv run pytest tests/unit/test_builder_retirement.py -q; Set-Location web; npm run build; Set-Location ..`

Expected: 契约测试全过；Manager Web 的 API、i18n、UI、TypeScript 和 Vite 门禁全过。

- [ ] **Step 4: 运行 Manager 插件双版本构建**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1`

Expected: 2016/2020 Manager 插件均成功；无 Builder 项目查找错误。

- [ ] **Step 5: 提交前端、插件与发布面退场**

```powershell
git add builder-web plugins/src/DstBuilder.AutoCAD plugins/tests/DstBuilder.AutoCAD.Tests scripts/build_builder_plugins.ps1 scripts/build_builder_release.ps1 scripts/export_builder_openapi.py changelog.md
git commit -m "移除 Builder 前端插件与发布工具"
```

### Task 4: 收口单产品治理、计划状态与全量验证

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md`
- Create: `docs/integration/adr/ADR-INT-002-retire-dst-builder.md`
- Modify: `docs/integration/adr/README.md`
- Modify: `docs/dst-builder/README.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `docs/README.md`
- Modify: `.planning/roadmaps/integration.md`
- Modify: `.planning/roadmaps/dst-builder.md`
- Modify: `.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md`
- Modify: `.planning/plans/dst-builder/README.md`
- Modify: `.planning/plans/integration/PLAN-INT-003-test-system-consolidation.md`
- Modify: `.planning/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Tasks 1–3 的单产品仓库状态。
- Produces: 接受的单产品治理架构、Builder 历史索引和完整验证证据。

- [ ] **Step 1: 新增 ADR 并更新权威治理**

`ADR-INT-002` 记录 RFC-INT-003 的落地决定、删除范围、无 `.dstb` 迁移承诺和历史迁移保留；`ARCH-INT-002` 改为 Manager 单产品治理并声明取代原双产品章节。

- [ ] **Step 2: 归档 Builder 计划和路线图**

将 `PLAN-DB-001` 标记 `cancelled`，原因写明产品退场而非实现失败；Builder 路线图和计划入口改为历史只读。更新 `PLAN-INT-003`，删除将要维护 Builder 测试入口的任务，并记录由本计划取代的具体范围。

- [ ] **Step 3: 更新仓库级 scope 规则和索引**

`AGENTS.md` 的现役 scope 改为 `dst-manager`、`shared`、`integration`；`dst-builder` 与 `legacy-refactor` 均为历史 scope，不接收新需求。同步所有 README 和 changelog。

- [ ] **Step 4: 执行完整验证**

Run:

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
uv run alembic upgrade head
Set-Location web
npm ci
npm run build
npm run test:e2e
Set-Location ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
```

Expected: Ruff、pytest、锁文件、迁移、Manager Web build/e2e 和双版本插件构建全部通过；pytest 收集结果不再包含 `tests/builder`。

- [ ] **Step 5: 记录实际验证并关闭计划**

把每条命令的退出码、通过/跳过数量和环境缺口写入本计划末尾；确认真实 AutoCAD 系统测试未启用时明确记录未执行。全部满足后把本计划状态改为 `completed`。

- [ ] **Step 6: 提交治理收口**

```powershell
git add AGENTS.md docs .planning changelog.md
git commit -m "收口 Builder 退场与单产品治理"
```
