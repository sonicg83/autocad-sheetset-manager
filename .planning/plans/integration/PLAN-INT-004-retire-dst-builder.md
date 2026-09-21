---
id: PLAN-INT-004
title: DST Builder 整体归档与文档封口实施计划
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

# DST Builder 整体归档与文档封口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已停止使用且与 DST Manager 无运行关系的 DST Builder 整体移入本地 `legacy/dst-builder/`，清除全部 Builder 专用入口与脚本，并把现役治理和文档封口为 Manager 单产品状态。

**Architecture:** 本次不迁移数据、不拆解或复用 Builder 实现，也不为退场新增永久测试。先把 Builder 的完整产品目录、测试、插件、打包文件和专用脚本原样移动到被 Git 忽略的本地归档目录，再删除公开仓库中的 Builder 包入口和引用；最后仅更新权威治理、历史文档状态和索引。Git 历史继续承担公开源码追溯，`legacy/dst-builder/` 只作为当前工作机上的便捷留档。

**Tech Stack:** Windows 11、PowerShell、Git、UV、Python 3.12、Markdown。

**Spec:** [`docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md`](../../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)

## Global Constraints

- 不新增数据库迁移；`builder_migrations/` 随 Builder 归档，Manager 的 `0007_db001_builder_handoff.py` 与 `0008_drop_handoff_sources.py` 直接删除。
- `document_revisions.kind` 与 `source_json` 仍由 Manager 使用，必须直接并入 `0001_initial.py`；迁移 head 回到 `0006_dm020_extension_platform`。
- 不兼容已标记为 0007/0008 的现有 Manager 数据库，也不得自动删除它们；用户需要自行删除应用数据数据库并重新创建。
- 不兼容 `project.dstb`，不导入 Builder 草稿，也不把 Builder 实现搬入 Manager。
- `src/dst_platform/` 由 Manager 继续使用，不属于 Builder 归档范围。
- `docs/dst-builder/` 和 `.planning/memos/dst-builder/` 保留在公开仓库中作为历史资料；只更新状态、封口说明和索引。
- `legacy/` 已被 `.gitignore` 忽略；归档移动前必须解析并核对源、目标绝对路径，目标已存在时停止，不得合并或覆盖。
- Builder 专用脚本必须全部归档；共享脚本只移除 Builder 分支或 Builder 配置，不得影响 Manager 构建、发布或插件流程。
- 每个任务只暂存明确列出的文件，更新 `changelog.md`，并使用简体中文提交信息。

## Review Focus

- `legacy/dst-builder/` 已存在或包含同名目标时必须停止，不能覆盖用户已有归档；Task 1 的预检负责保证。
- Builder 专用 PowerShell/Python 脚本、PyInstaller 入口和 console script 必须同时消失，不能留下半可用入口；Task 1 的残留扫描负责保证。
- Manager 仍依赖 `dst_platform`，归档不得移动或删改该包；Task 1 的导入检查负责保证。
- 全新 Manager 数据库必须从压平后的 0001 升到 0006，并包含 `document_revisions.kind/source_json`；Task 1 的迁移测试负责保证。
- 历史文档仍应可检索，但不得继续把 Builder 描述为现役产品或开放计划；Task 2 的文档扫描负责保证。

---

### Task 1: 整体归档 Builder 并清除全部运行入口

**Files:**
- Move locally: `src/dst_builder/` → `legacy/dst-builder/src/dst_builder/`
- Move locally: `builder-web/` → `legacy/dst-builder/builder-web/`
- Move locally: `builder_migrations/` → `legacy/dst-builder/builder_migrations/`
- Move locally: `builder_alembic.ini` → `legacy/dst-builder/builder_alembic.ini`
- Move locally: `tests/builder/` → `legacy/dst-builder/tests/builder/`
- Move locally: `plugins/src/DstBuilder.AutoCAD/` → `legacy/dst-builder/plugins/src/DstBuilder.AutoCAD/`
- Move locally: `plugins/tests/DstBuilder.AutoCAD.Tests/` → `legacy/dst-builder/plugins/tests/DstBuilder.AutoCAD.Tests/`
- Move locally: `packaging/dst-builder.spec` → `legacy/dst-builder/packaging/dst-builder.spec`
- Move locally: `packaging/builder_entry.py` → `legacy/dst-builder/packaging/builder_entry.py`
- Move locally: `scripts/build_builder_plugins.ps1` → `legacy/dst-builder/scripts/build_builder_plugins.ps1`
- Move locally: `scripts/build_builder_release.ps1` → `legacy/dst-builder/scripts/build_builder_release.ps1`
- Move locally: `scripts/export_builder_openapi.py` → `legacy/dst-builder/scripts/export_builder_openapi.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `scripts/setup.bat`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `migrations/versions/0001_initial.py`
- Delete: `migrations/versions/0007_db001_builder_handoff.py`
- Delete: `migrations/versions/0008_drop_handoff_sources.py`
- Modify: `src/dst_manager/infrastructure/persistence/database.py`
- Modify: `tests/unit/test_database.py`
- Modify: `tests/unit/test_runtime.py`
- Modify: `tests/unit/test_extension_persistence.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: RFC-INT-003 的 Builder 直接退场结论，以及 `.gitignore` 中 `/legacy/` 的本地私有目录约定。
- Produces: 仅暴露 `dst-manager` console script、`dst_manager` 与 `dst_platform` Python 包的公开仓库；本机保留完整 `legacy/dst-builder/` 归档。

- [ ] **Step 1: 检查工作区和归档目标**

运行：

```powershell
git status --short
$repoRoot = (Resolve-Path -LiteralPath ".").Path
$legacyRoot = (Resolve-Path -LiteralPath "legacy").Path
$archiveRoot = Join-Path $legacyRoot "dst-builder"
if (-not $legacyRoot.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "legacy 目录不在仓库内：$legacyRoot"
}
if (Test-Path -LiteralPath $archiveRoot) {
    throw "归档目标已存在，停止以避免覆盖：$archiveRoot"
}
```

Expected: 工作区现有改动被记录；`legacy` 解析到当前仓库内；`legacy/dst-builder/` 不存在。若目标存在，停止并由用户决定新目录名或处理旧归档。

- [ ] **Step 2: 建立清单并核对全部源路径**

使用以下唯一归档清单：

```powershell
$moves = [ordered]@{
    "src\dst_builder" = "src\dst_builder"
    "builder-web" = "builder-web"
    "builder_migrations" = "builder_migrations"
    "builder_alembic.ini" = "builder_alembic.ini"
    "tests\builder" = "tests\builder"
    "plugins\src\DstBuilder.AutoCAD" = "plugins\src\DstBuilder.AutoCAD"
    "plugins\tests\DstBuilder.AutoCAD.Tests" = "plugins\tests\DstBuilder.AutoCAD.Tests"
    "packaging\dst-builder.spec" = "packaging\dst-builder.spec"
    "packaging\builder_entry.py" = "packaging\builder_entry.py"
    "scripts\build_builder_plugins.ps1" = "scripts\build_builder_plugins.ps1"
    "scripts\build_builder_release.ps1" = "scripts\build_builder_release.ps1"
    "scripts\export_builder_openapi.py" = "scripts\export_builder_openapi.py"
}
$missing = @($moves.Keys | Where-Object { -not (Test-Path -LiteralPath (Join-Path $repoRoot $_)) })
if ($missing.Count -gt 0) { throw "归档源缺失：$($missing -join ', ')" }
```

Expected: 所有源路径存在；清单包含 Builder Python、Web、数据库迁移、测试、插件、打包入口以及三个专用脚本。

- [ ] **Step 3: 按清单移动到本地归档并核验**

```powershell
New-Item -ItemType Directory -Path $archiveRoot | Out-Null
foreach ($entry in $moves.GetEnumerator()) {
    $source = Join-Path $repoRoot $entry.Key
    $destination = Join-Path $archiveRoot $entry.Value
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    Move-Item -LiteralPath $source -Destination $destination
}
$notArchived = @($moves.Values | Where-Object { -not (Test-Path -LiteralPath (Join-Path $archiveRoot $_)) })
if ($notArchived.Count -gt 0) { throw "归档不完整：$($notArchived -join ', ')" }
```

Expected: 清单中的源路径全部从仓库工作树消失，目标路径全部存在于 `legacy/dst-builder/`；Git 将其识别为删除，因为 `legacy/` 不被跟踪。

- [ ] **Step 4: 清除包、安装和根文档中的 Builder 入口**

将 `pyproject.toml` 收缩为：

```toml
[project.scripts]
dst-manager = "dst_manager.interfaces.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/dst_manager", "src/dst_platform"]
```

从 `scripts/setup.bat` 移除所有 `DST_BUILDER_*` 设置以及 Builder 启动提示。从中英文根 README 删除 Builder 启动、构建、发布和现役产品描述，只保留指向历史文档入口的说明。执行 `uv lock` 同步锁文件；仅移除经 `uv lock` 判定不再被 Manager 使用的依赖。

同时删除 Manager 的 `0007_db001_builder_handoff.py` 与 `0008_drop_handoff_sources.py`，并把 0007 中仍被 Manager 使用的两列直接写入 `0001_initial.py` 的 `document_revisions` 定义：

```python
sa.Column("kind", sa.String(20), nullable=False, server_default="operation"),
sa.Column("source_json", sa.Text(), nullable=True),
```

把 `database.py` 的 `LATEST_SCHEMA_REVISION` 改为 `0006_dm020_extension_platform`，同步更新 `test_database.py`、`test_runtime.py` 和 `test_extension_persistence.py` 的 head、迁移哈希与全新库断言。不得为 0007/0008 数据库增加兼容分支；README 和 changelog 明确说明现有本地 Manager 数据库需要手工重建，程序不自动删除用户数据。

- [ ] **Step 5: 扫描所有 Builder 运行入口和专用脚本残留**

```powershell
git grep -n -E "dst-builder|dst_builder|builder-web|builder_migrations|DstBuilder|build_builder|export_builder" -- pyproject.toml scripts packaging plugins src tests
git grep -n -E "dst-builder (serve|build)|build_builder|export_builder|第二条产品线" -- README.md README.en.md scripts/setup.bat
if (Test-Path -LiteralPath "migrations/versions/0007_db001_builder_handoff.py") { throw "0007 仍存在" }
if (Test-Path -LiteralPath "migrations/versions/0008_drop_handoff_sources.py") { throw "0008 仍存在" }
```

Expected: 两次扫描均无命中；活动源码、测试、插件、打包、脚本、包元数据和根 README 不再包含 Builder 运行入口。历史文档链接允许继续使用产品名称；Manager 的迁移目录也不再包含 0007/0008。

- [ ] **Step 6: 验证 Manager 的最小独立运行面**

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv lock --check
uv run dst-manager --help
uv run python -c "import dst_manager; import dst_platform"
uv run pytest tests/unit/test_database.py tests/unit/test_runtime.py tests/unit/test_extension_persistence.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
```

Expected: UV 同步和锁文件检查成功；Manager CLI 与两个包导入成功；数据库测试证明全新库 head 为 0006 且通用修订字段存在；AutoCAD 2016/2020 Manager 插件构建不再查找 Builder 项目。

- [ ] **Step 7: 记录并提交整体归档**

在 `changelog.md` 记录本地归档位置、公开仓库删除范围、Builder 专用脚本清理结果、迁移基线压平方式，以及现有 Manager 数据库必须手工重建。只暂存本任务涉及的删除和修改，不暂存 `legacy/`：

```powershell
git add pyproject.toml uv.lock scripts/setup.bat README.md README.en.md migrations/versions/0001_initial.py src/dst_manager/infrastructure/persistence/database.py tests/unit/test_database.py tests/unit/test_runtime.py tests/unit/test_extension_persistence.py changelog.md
git add -u -- src/dst_builder builder-web builder_migrations builder_alembic.ini tests/builder plugins/src/DstBuilder.AutoCAD plugins/tests/DstBuilder.AutoCAD.Tests packaging/dst-builder.spec packaging/builder_entry.py scripts/build_builder_plugins.ps1 scripts/build_builder_release.ps1 scripts/export_builder_openapi.py migrations/versions/0007_db001_builder_handoff.py migrations/versions/0008_drop_handoff_sources.py
git commit -m "归档 DST Builder 并清理专用脚本"
```

### Task 2: 封口历史文档并收敛为 Manager 单产品治理

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md`
- Modify: `docs/dst-builder/README.md`
- Modify: `docs/dst-builder/product/vision.md`
- Modify: `docs/dst-builder/product/prds/PRD-DB-001-guided-sheetset-generation.md`
- Modify: `docs/dst-builder/architecture/ARCH-DB-001-greenfield-desktop-baseline.md`
- Modify: `docs/dst-builder/specs/SPEC-DB-001-minimal-generation-loop.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `docs/integration/README.md`
- Modify: `docs/README.md`
- Modify: `.planning/roadmaps/dst-builder.md`
- Modify: `.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md`
- Modify: `.planning/plans/dst-builder/README.md`
- Modify: `.planning/plans/integration/PLAN-INT-003-test-system-consolidation.md`
- Delete: `.planning/todos/integration/2026-09-18-builder-status-torn-read.md`
- Modify: `.planning/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1 形成的 Manager 单产品仓库，以及 RFC-INT-003 的取代关系。
- Produces: 现役 scope 仅为 `dst-manager`、`shared`、`integration`；Builder 文档和备忘保留为只读历史入口，不再产生新需求、计划或发布工作。

- [ ] **Step 1: 更新权威治理和仓库规则**

把 `ARCH-INT-002` 更新为当前单产品事实：`dst-builder` 已按 RFC-INT-003 退场，公开实现由 Git 历史追溯，本地副本位于被忽略的 `legacy/dst-builder/`，新建图纸集能力归入 Manager。同步 `AGENTS.md`：现役 scope 仅保留 `dst-manager`、`shared`、`integration`；`dst-builder` 与 `legacy-refactor` 都是历史 scope，不接收新需求、架构、计划或待办。

- [ ] **Step 2: 将 Builder 正式文档封口为历史资料**

将 `VISION-DB-001`、`PRD-DB-001`、`ARCH-DB-001`、`SPEC-DB-001` 的 `status` 改为 `archived`，`updated` 改为 `2026-09-21`，并在标题后增加统一说明：文档描述退场前的产品，不再作为现役实现依据；替代方向见 RFC-INT-003、PLAN-DM-035 与 PLAN-DM-036。`docs/dst-builder/README.md` 只保留历史导航和上述封口说明，不复制实现细节。

- [ ] **Step 3: 关闭 Builder 路线图、计划和待办**

将 `ROADMAP-DB-001` 与 `PLAN-DB-001` 标记为 `cancelled`，原因明确写为“产品方向终止，不代表实施失败”；把 `PLAN-INT-003` 标记为 `cancelled`，说明双产品测试治理已失去前提，未来 Manager 测试治理另行立项。删除尚未形成正式计划且已失效的 Builder 状态撕裂 Todo；保留 `.planning/memos/dst-builder/` 作为历史证据。

- [ ] **Step 4: 同步所有现役导航**

更新根、`docs/`、`docs/integration/`、`docs/dst-manager/`、`.planning/` 与两个计划目录的 README：Builder 只出现在“历史资料”语境中；Manager 标准驱动创建由 RFC-INT-003、PLAN-DM-035 和 PLAN-DM-036 承接。历史 RFC、ADR 和 changelog 保留原始事实；现役文档明确迁移历史已压平且旧本地数据库不兼容。

- [ ] **Step 5: 执行文档封口和 Manager 回归验证**

```powershell
git diff --check
git grep -n -E "现役.*Builder|Builder.*现役|双产品|第二条产品线" -- README.md README.en.md AGENTS.md docs .planning
uv run ruff check .
uv run pytest -q
uv run alembic upgrade head
Set-Location web
npm run build
Set-Location ..
```

Expected: 差异格式检查通过；扫描命中只存在于明确标记为历史的原始决策正文，不存在现役声明；Ruff、pytest、全新数据库升级和 Manager Web 构建通过。真实 AutoCAD 系统测试不是本次文档与归档变更的必需门禁。

- [ ] **Step 6: 记录验证并提交文档封口**

把实际命令结果、跳过项和 Builder 专用脚本清理清单写入 `changelog.md`，满足后将本计划状态改为 `completed`：

```powershell
git add AGENTS.md docs .planning changelog.md
git commit -m "封口 Builder 历史文档与单产品治理"
```
