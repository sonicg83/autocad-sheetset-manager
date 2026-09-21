---
id: PLAN-INT-003
title: 双产品测试体系收敛与过时内容清理实施计划
status: cancelled
owners:
  - integration
created: 2026-09-19
updated: 2026-09-21
related:
  - ARCH-INT-002
  - ARCH-DB-001
  - ARCH-DM-001
  - PLAN-DB-001
  - PLAN-DM-014
  - PLAN-DM-029
---

# 双产品测试体系收敛与过时内容清理实施计划

> **取消说明（2026-09-21）：** 本计划以双产品并存为前提，而 DST Builder 已按 [RFC-INT-003](../../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md) 整体退场，双产品测试治理已失去前提，计划不再执行；未来 Manager 测试治理（验证矩阵、发布门禁与测试清理）另行立项。正文按历史记录保留，其中的审计基线仍可作为后续立项的输入。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 每个代码任务必须先使用 `superpowers:test-driven-development`；每项提交前及最终收口前必须使用 `superpowers:verification-before-completion`。测试迁移只允许保持或增强既有行为证据，不得借“去冗余”删除尚无替代证据的断言。

**Goal:** 恢复稳定且可重复的测试基线，建立 Manager、Builder 与共享平台统一的分层验证入口，并清理休眠、重复、历史命名及超大测试文件，确保发布门禁实际执行两侧前端与后端测试。

**Architecture:** 采用渐进式收敛：先固定现有 GBK 批处理测试环境并消除仓库自有弃用告警，再建立唯一 PowerShell 验证编排器并接入发布门禁；随后分离普通回归、视觉证据和真实 CAD 测试，最后执行可证明的去重与机械拆分。所有拆分前后都用收集清单、测试节点集合和全量结果对比，避免把文件整理变成行为改写。

**Tech Stack:** Windows 11 / PowerShell / Python 3.12+ / UV / pytest 8 / Ruff / Vue 3 / TypeScript / Vite / Vitest 5 / Playwright / Node.js test runner。

**Spec:** 本计划不新增产品 Spec；依据 `docs/integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md`、`docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md`、`AGENTS.md` 的现行测试要求，以及 2026-09-19 测试体系审计结果。

## Global Constraints

- 始终使用简体中文编写代码注释、文档、变更记录与 Git commit message；标识符、协议字段、API 路径和错误码保持原始英文形式。
- 目标系统为 Windows 11，默认 Shell 为 PowerShell；所有新增命令与脚本必须兼容 PowerShell，不得假设 Bash 可用。
- Python 版本不得低于 3.12；依赖只通过 UV 管理，依赖变化必须同步更新 `pyproject.toml` 与 `uv.lock`。
- Web 依赖变化必须同步更新对应的 `package.json` 与 `package-lock.json`。
- 只读和测试流程不得修改 `sample/` 原件；真实 AutoCAD 测试继续要求显式环境变量、匹配插件和私有样本。
- Manager、Builder 与 `dst_platform` 的依赖方向保持不变；不得为复用测试夹具引入产品包之间的反向 import。
- 默认验证不执行真实 AutoCAD、真实 PyInstaller 构建和进程生命周期测试；这些高成本测试必须有独立、显式入口。
- 不提交覆盖率文件、Playwright 结果、截图临时产物、`web/dist/`、`builder-web/dist/`、`node_modules/`、`.venv/` 或 `.dst-manager-data/`。
- 每个任务只暂存本任务文件，并在 `changelog.md` 当前日期章节追加实际、可核验的记录。
- 执行前保留当前工作区已有的 `changelog.md` 与 `web/playwright.config.ts` 改动；不得覆盖或重写用户正在完成的设置中心 E2E 隔离修复。
- 运行 pytest 时使用 `uv run python -m pytest ...`；不要在已有 `addopts = "-q"` 的基础上再加 `-q`，以免 `-qq` 吞掉可核验的汇总。

## Review Focus

- 非 CP936 父终端启动 GBK `setup.bat` 测试时，测试必须显式建立代码页前提，不能因宿主终端编码不同而误报业务失败。
- 任一前端单测、契约测试或普通 E2E 失败时，release 必须失败；视觉证据生成和真实 CAD 缺环境不能伪装为普通回归成功。
- `Manager`、`Builder` 与 `All` 三种验证范围必须各自只运行声明的测试集合，且 `All` 不得遗漏共享平台与架构测试。
- 拆分测试文件后，pytest 节点集合除有记录的重命名外必须一一对应，参数化 case 数量不得减少。
- Playwright 设置文件隔离、普通并行回归和视觉证据三个 project 必须保持确定的依赖顺序，不能重新引入共享 `settings.json` 污染。

---

## 冻结决策

1. **不以删测试换速度。** 只有完全重复、无程序入口且已有更高层替代证据的内容可以删除；其余“旧”测试只重命名或拆分。
2. **唯一编排入口。** 新增 `scripts/verify.ps1` 作为仓库验证矩阵的唯一权威入口；各 package script 继续负责本目录内的原子命令，release 脚本只调用编排器，不复制命令清单。
3. **两级常规门禁。** `Fast` 包含 Ruff、Python 非高成本测试、锁文件、两侧前端单测/契约检查/生产构建；`Full` 在 `Fast` 基础上增加两侧普通 Playwright 回归。
4. **高成本测试分轨。** 真实 AutoCAD、PyInstaller 冒烟、真实进程生命周期和视觉证据生成不进入 `Fast`/`Full` 默认矩阵，保留显式入口并在 release 说明中报告是否执行。
5. **视觉证据不是视觉回归。** 只写 `page.screenshot()` 的用例归入 `visual-evidence` project；真正的回归必须依赖 DOM、几何、可访问性或明确的截图基线断言。
6. **不引入任意覆盖率阈值。** 当前 `pytest-cov` 没有调用方，先移除未使用依赖；若未来要建立覆盖率门禁，必须基于独立基线与风险分层另行立项。
7. **首轮只拆最严重文件。** 本计划拆分 `test_core.py` 与两个 `test_v021_*`；其余超过 500 行的测试文件登记后续候选，不在同一轮扩大重排范围。

## 当前基线

2026-09-19 审计结果，供实施后比较：

| 测试面 | 当前结果 |
| --- | --- |
| pytest 收集 | 91 个 Python 测试文件，2256 项 |
| pytest 当前宿主直跑 | 2180 passed / 74 skipped / 2 failed；失败均为 `setup.bat` 中文输出代码页断言 |
| pytest 显式 CP936 | 仓库既有记录为 2181 passed / 75 skipped / 0 failed；实施时必须重新生成新鲜结果 |
| Manager Vitest | 18 files / 179 passed |
| Manager UI 契约 | 96 passed |
| Manager Playwright | 29 files / 582 tests（仅完成 `--list` 审计；已有工作区记录显示 3 轮全绿） |
| Builder Vitest | 2 files / 27 passed |
| Builder Playwright | 3 files / 20 tests（仅完成 `--list` 审计） |
| 主要告警 | Alembic `path_separator` 约 340 次；SQLite datetime adapter 6 次；Starlette TestClient 1 次 |

上述数字是审计快照，不是永久断言。任务完成条件以“预期删除/替换项有说明，其余节点不丢失，全部门禁通过”为准。

## 文件结构与职责

```text
scripts/
├─ verify.ps1                       # 新增：双产品 Fast/Full 验证矩阵唯一编排入口
├─ release.ps1                      # 改为调用 verify.ps1，不再内嵌重复命令
├─ build_release.ps1                # 保持纯构建职责
└─ build_builder_release.ps1        # 保持纯构建职责

tests/
├─ conftest.py                      # 高成本 marker 注册/公共收集约束（如需要）
├─ unit/
│  ├─ test_verify_script.py         # verify.ps1 命令矩阵与失败传播
│  ├─ test_alembic_config.py        # Alembic 路径分隔配置契约
│  ├─ test_core.py                  # 最终删除，由聚焦文件替代
│  ├─ test_console_and_cli.py
│  ├─ test_golden_workspace.py
│  ├─ test_structural_dom.py
│  ├─ test_structural_change_scope.py
│  ├─ test_structural_create_plan.py
│  ├─ test_execution_baselines.py
│  ├─ test_structural_preview.py
│  ├─ test_job_recovery_integration.py
│  ├─ test_cad_rename_groups.py
│  ├─ test_cad_parallel_failures.py
│  ├─ test_cad_publish_flow.py
│  ├─ test_subset_deletion.py
│  ├─ test_repair_end_to_end.py
│  └─ test_publish_end_to_end.py
└─ demo/                            # 删除两项休眠 Demo 测试；HTML Demo 与 QA 备忘保留

web/
├─ package.json                     # 普通 E2E 与视觉证据脚本分轨
└─ playwright.config.ts             # settings 隔离、regression、visual-evidence 三类 project
```

## 接口与依赖

- `scripts/verify.ps1` 接口固定为 `-Product Manager|Builder|All`、`-Tier Fast|Full`、`-ListOnly`；Task 3 的 release 接入和 Task 8 的最终验收只依赖这三个参数。
- `-ListOnly` 输出每一步的稳定 `Name`、`WorkingDirectory`、`FilePath` 与 `Arguments`，不执行命令；`tests/unit/test_verify_script.py` 用它验证矩阵，避免以脆弱的脚本文本搜索代替行为测试。
- `web` 的 `test:e2e` 只运行 `settings-file-mutating` 与 `regression`；`test:evidence` 只运行 `visual-evidence`，后者依赖前者完成共享设置文件隔离。
- Task 6、7 的测试拆分只移动测试与测试私有 helper，不修改 `src/`、API、错误码或序列化契约。

---

### Task 1: 稳定 Python 基线并消除仓库自有告警

**Files:**
- Modify: `tests/unit/test_setup_bat.py:39-62, 132-151, 211-225`
- Modify: `alembic.ini:1-5`
- Create: `tests/unit/test_alembic_config.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `scripts/setup.bat` 既有 GBK、无 BOM、面向 CP936 的明确契约
- Produces: 与父终端代码页无关的 `_run_setup(...)`；`alembic.ini` 明确的 `path_separator = os`

- [ ] **Step 1: 为非 CP936 父终端写失败测试**

在 `test_setup_bat.py` 增加一个 helper 参数与回归用例：先以 `chcp 65001` 启动外层 `cmd`，再由测试命令显式切回 936 后 `call setup.bat`；断言生成的 `.env` 与“警告/手工”中文语义均正确。测试必须证明旧 `_run_setup` 会因父环境不同失败，而新 helper 固定 936 后通过。

```python
def test_runner_pins_cp936_before_calling_gbk_setup(tmp_path: Path):
    app_dir = tmp_path / "app"
    autodesk_root = tmp_path / "autodesk"
    app_dir.mkdir()
    _make_fake_autocad(autodesk_root, "2014")

    result = _run_setup(app_dir, autodesk_root, parent_code_page=65001)

    assert result.returncode == 0
    assert "警告" in result.stdout
    assert "DST_MANAGER_AUTOCAD_2016_CONSOLE" in (app_dir / ".env").read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行失败用例确认红灯**

Run:

```powershell
uv run python -m pytest tests/unit/test_setup_bat.py::test_runner_pins_cp936_before_calling_gbk_setup -vv
```

Expected: FAIL，失败原因是旧 helper 未接受 `parent_code_page` 或中文输出无法按 GBK 得到预期文本。

- [ ] **Step 3: 最小化修正测试执行环境**

将 `_run_setup` 的 `cmd` 调用固定为：

```python
prefix = f"chcp {parent_code_page}>nul & " if parent_code_page is not None else ""
command = f"{prefix}chcp 936>nul & call .\\setup.bat"
completed = subprocess.run(
    ["cmd", "/d", "/c", command],
    cwd=app_dir,
    env=env,
    capture_output=True,
    timeout=120,
    check=False,
)
```

`parent_code_page` 仅用于回归用例在外层构造不同代码页环境，不改变 `setup.bat` 的 GBK 产品契约。保留行为断言，不把中文提示断言删成只有返回码。

- [ ] **Step 4: 为 Alembic 配置写失败测试并修正**

创建 `tests/unit/test_alembic_config.py`：

```python
from configparser import ConfigParser
from pathlib import Path


def test_alembic_uses_os_path_separator() -> None:
    config = ConfigParser()
    config.read(Path(__file__).parents[2] / "alembic.ini", encoding="utf-8")
    assert config["alembic"]["path_separator"] == "os"
```

先运行并确认缺键失败，再在 `alembic.ini` 的 `prepend_sys_path = .` 后增加：

```ini
path_separator = os
```

- [ ] **Step 5: 验证 Python 基线**

Run:

```powershell
uv run python -m pytest tests/unit/test_setup_bat.py tests/unit/test_alembic_config.py
uv run alembic current
uv run python -m pytest
```

Expected: 两个目标文件通过；全量 pytest 0 failed。真实 CAD、生命周期和 PyInstaller 冒烟按现有条件跳过；Alembic `No path_separator` 告警为 0。SQLite 与 Starlette 的第三方弃用告警数量如仍存在，记录到 Task 8，不在本任务用全局 ignore 隐藏。

- [ ] **Step 6: 更新 changelog 并提交**

```powershell
git add tests/unit/test_setup_bat.py tests/unit/test_alembic_config.py alembic.ini changelog.md
git commit -m "稳定 GBK 初始化脚本测试并修正 Alembic 配置"
```

---

### Task 2: 建立统一验证编排器

**Files:**
- Create: `scripts/verify.ps1`
- Create: `tests/unit/test_verify_script.py`
- Modify: `pyproject.toml:42-44`
- Modify: `tests/system_autocad/test_capabilities.py:35-40`
- Modify: `tests/builder/system_autocad/test_minimal_drawing.py:32-38`
- Modify: `tests/builder/integration/test_builder_packaging_contract.py:253-258`
- Modify: `tests/unit/test_start_script.py:93-95, 157-174`
- Modify: `changelog.md`

**Interfaces:**
- Produces: `scripts/verify.ps1 -Product <Manager|Builder|All> -Tier <Fast|Full> [-ListOnly]`
- Consumes: 两侧 `package.json` 中现有 `test:unit`、`test:contracts`、`build`、`test:e2e` 脚本

- [ ] **Step 1: 注册高成本 marker 并写矩阵失败测试**

在 `pyproject.toml` 注册：

```toml
markers = [
    "system_autocad: 需要真实 AutoCAD、匹配插件与私有样本",
    "packaging_smoke: 执行真实 PyInstaller 构建与产物扫描",
    "lifecycle: 启动真实 API/Worker 进程并验证生命周期",
]
```

把三个现有条件测试面分别加上对应 marker。创建 `test_verify_script.py`，先断言不存在的编排器会失败；随后固定以下矩阵：

| Product | Python 路径 | 前端目录 |
| --- | --- | --- |
| Manager | `tests/architecture tests/platform tests/unit tests/integration` | `web` |
| Builder | `tests/architecture tests/platform tests/builder/unit tests/builder/integration` | `builder-web` |
| All | 上述路径去重后的并集 | `web` + `builder-web` |

所有 Python 命令追加 `-m "not system_autocad and not packaging_smoke and not lifecycle"`。

- [ ] **Step 2: 实现稳定、不可注入的命令模型**

`verify.ps1` 使用固定参数白名单与参数数组，不接受任意命令字符串。每一步表示为：

```powershell
[pscustomobject]@{
    Name = "python-tests"
    WorkingDirectory = $projectRoot
    FilePath = "uv"
    Arguments = @("run", "python", "-m", "pytest", "tests/unit", "-m", "not system_autocad and not packaging_smoke and not lifecycle")
}
```

执行顺序固定为：`uv sync --dev` → Ruff → Python → `uv lock --check` → 对应前端的 `npm ci` → 单测/契约 → build；`Full` 在每个产品 build 后增加普通 `test:e2e`。任一步非零立即 `throw`，后续步骤不得继续。

- [ ] **Step 3: 实现 `-ListOnly` 并验证矩阵**

`-ListOnly` 将步骤数组转换为 JSON 后退出 0，不执行外部命令。测试至少覆盖：

```python
def test_manager_fast_lists_backend_and_manager_frontend_without_e2e(): ...
def test_builder_fast_lists_builder_frontend_without_manager_frontend(): ...
def test_all_full_lists_both_frontends_and_both_e2e_suites_once(): ...
def test_unknown_product_is_rejected_by_powershell_parameter_binding(): ...
```

Run:

```powershell
uv run python -m pytest tests/unit/test_verify_script.py -vv
```

Expected: PASS，且 `All/Full` 中共享 Python 路径只出现一次。

- [ ] **Step 4: 运行 Fast 矩阵**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Product All -Tier Fast
```

Expected: Ruff、Python、锁文件、Manager 179 项 Vitest、UI 契约、Manager build、Builder 27 项 Vitest、Builder build 全部通过；不启动 Playwright、AutoCAD、PyInstaller 或生命周期测试。

- [ ] **Step 5: 更新 changelog 并提交**

```powershell
git add scripts/verify.ps1 tests/unit/test_verify_script.py pyproject.toml tests/system_autocad tests/builder/system_autocad tests/builder/integration/test_builder_packaging_contract.py tests/unit/test_start_script.py changelog.md
git commit -m "建立双产品统一验证矩阵"
```

---

### Task 3: 把统一矩阵接入 release 与开发文档

**Files:**
- Modify: `scripts/release.ps1:27-34`
- Modify: `tests/unit/test_release_scripts.py`
- Modify: `README.md:96-116`
- Modify: `README.en.md` 对应验证章节
- Modify: `docs/dst-manager/guides/GUIDE-DM-003-settings-config-sop.md`
- Modify: `docs/dst-manager/guides/GUIDE-DM-005-builtin-extension-development.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 2 的 `verify.ps1`
- Produces: Manager release 的 `Full` 硬门禁；统一的开发者命令入口

- [ ] **Step 1: 写 release 调用失败测试**

在 `test_release_scripts.py` 新增静态与 PowerShell 解析断言：`release.ps1` 必须且只调用一次 `verify.ps1 -Product Manager -Tier Full`，并且不再直接包含 `uv run pytest`、`ruff check` 或 `npm run test:e2e`。

- [ ] **Step 2: 用编排器替换重复门禁**

将 `release.ps1` 第 2 阶段替换为：

```powershell
& (Join-Path $PSScriptRoot "verify.ps1") -Product Manager -Tier Full
if ($LASTEXITCODE -ne 0) { throw "完整验证矩阵未通过" }
```

`build_release.ps1` 与 `build_builder_release.ps1` 保持“纯构建、不做门禁”的既有职责，不把验证命令复制进去。

- [ ] **Step 3: 更新开发者入口文档**

根 README 中把分散命令改为以下主入口，并保留原子命令作为故障排查说明：

```powershell
# 日常快速验证
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Product All -Tier Fast

# 发布前完整验证（不含真实 CAD/真实打包冒烟）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Product All -Tier Full
```

中英文 README 同步；两份 Manager Guide 改为引用统一入口，不复制一套可能漂移的完整矩阵。

- [ ] **Step 4: 验证 release 脚本契约**

Run:

```powershell
uv run python -m pytest tests/unit/test_release_scripts.py tests/unit/test_verify_script.py -vv
```

Expected: PASS；不实际创建 tag 或分发 zip。

- [ ] **Step 5: 更新 changelog 并提交**

```powershell
git add scripts/release.ps1 tests/unit/test_release_scripts.py README.md README.en.md docs/dst-manager/guides/GUIDE-DM-003-settings-config-sop.md docs/dst-manager/guides/GUIDE-DM-005-builtin-extension-development.md changelog.md
git commit -m "将完整测试矩阵接入发布门禁"
```

---

### Task 4: 清理确定的休眠与重复内容

**Files:**
- Delete: `tests/demo/properties-demo.test.cjs`
- Delete: `tests/demo/sheets-demo.test.cjs`
- Modify: `tests/platform/test_platform_acsm_contract.py:65-68`
- Modify: `tests/unit/test_acsm_contract.py:25-72`
- Modify: `pyproject.toml:27-34`
- Modify: `uv.lock`
- Modify: `.planning/memos/dst-manager/2026-09-04-sheets-demo-qa.md`
- Modify: `.planning/memos/dst-manager/2026-09-05-properties-demo-qa.md`
- Modify: `changelog.md`

**Interfaces:**
- Produces: 无休眠 Demo 测试；AcSm 平台实现与 Manager 兼容入口各有唯一职责；开发依赖不再包含无调用方的 `pytest-cov`

- [ ] **Step 1: 固化 AcSm re-export 兼容证据**

在 `test_acsm_contract.py` 增加：

```python
def test_manager_contract_entrypoint_reexports_platform_functions() -> None:
    from dst_manager.infrastructure.acsm_xml import contract as manager_contract
    from dst_platform.acsm import contract as platform_contract

    assert manager_contract.validate_contract is platform_contract.validate_contract
    assert manager_contract.validate_schema is platform_contract.validate_schema
```

运行通过后，从 `test_platform_acsm_contract.py` 删除与 Manager 文件完全相同的 `test_golden_sheetset_passes_contract_and_schema`；保留平台侧其他产品无关契约测试和 Manager 侧黄金样本测试。

- [ ] **Step 2: 删除休眠 Demo 测试但保留设计资料**

删除两项 `.cjs`。HTML Demo、SPEC 链接和 QA 备忘保留；在两份 QA 备忘的原测试命令后补充说明：“该命令为 2026-09-04/05 当次设计证据，生产实现完成后测试脚本已由 PLAN-INT-003 移除，不属于持续回归门禁。”

- [ ] **Step 3: 移除未使用的覆盖率依赖**

Run:

```powershell
uv remove --dev pytest-cov
```

Expected: `pyproject.toml` 删除 `pytest-cov`，`uv.lock` 同步；`rg -n "pytest-cov|--cov" . --glob '!changelog.md'` 只允许命中本计划的历史说明，不允许存在执行入口。

- [ ] **Step 4: 验证收集与目标测试**

Run:

```powershell
uv run python -m pytest tests/platform/test_platform_acsm_contract.py tests/unit/test_acsm_contract.py -vv
uv run python -m pytest --collect-only
if (Test-Path -LiteralPath "tests/demo/properties-demo.test.cjs") { throw "properties Demo 测试仍存在" }
if (Test-Path -LiteralPath "tests/demo/sheets-demo.test.cjs") { throw "sheets Demo 测试仍存在" }
```

Expected: AcSm 测试通过；pytest 收集总量相对 Task 1 基线只发生计划内的“删除一个重复测试、增加一个 re-export 测试”，净变化 0；两个休眠 Demo 测试文件均不存在。

- [ ] **Step 5: 更新 changelog 并提交**

```powershell
git add -A tests/demo
git add tests/platform/test_platform_acsm_contract.py tests/unit/test_acsm_contract.py pyproject.toml uv.lock .planning/memos/dst-manager changelog.md
git commit -m "清理休眠 Demo 测试与重复契约覆盖"
```

---

### Task 5: 分离普通 E2E 与视觉证据并关闭全局重试

**Files:**
- Modify: `web/playwright.config.ts`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/tests/e2e/*-visual-evidence.spec.ts`（只在 project 分类需要显式标记时改动）
- Modify: `web/tests/e2e/settings-extensions-production-evidence.spec.ts`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: 当前工作区已实现的 `settings-file-mutating` project 与 `parallel` 依赖关系
- Produces: `npm run test:e2e` 普通回归入口；`npm run test:evidence` 显式视觉证据入口；全局 `retries: 0`

- [ ] **Step 1: 先用列表测试冻结分类**

视觉证据集合固定为以下六个文件：

```text
i18n-visual-evidence.spec.ts
properties-visual-evidence.spec.ts
settings-demo-visual-evidence.spec.ts
settings-extensions-production-evidence.spec.ts
sheet-catalog-visual-evidence.spec.ts
sheets-visual-evidence.spec.ts
```

先保存 `npx playwright test --list` 的节点清单到任务临时目录（不得提交），并逐项检查这六个文件中的非截图断言：若某断言是唯一业务回归证据，先把该断言迁入最接近的普通 spec，再把原文件归入 evidence；不得只因文件名含 evidence 就丢失唯一断言。

- [ ] **Step 2: 配置三个职责明确的 project**

在保留用户当前设置隔离修复的基础上，将 project 固定为：

```typescript
projects: [
  {name: "settings-file-mutating", testMatch: "settings-dialog.spec.ts"},
  {
    name: "regression",
    testIgnore: ["settings-dialog.spec.ts", "*-visual-evidence.spec.ts", "settings-extensions-production-evidence.spec.ts"],
    dependencies: ["settings-file-mutating"],
  },
  {
    name: "visual-evidence",
    testMatch: ["*-visual-evidence.spec.ts", "settings-extensions-production-evidence.spec.ts"],
    dependencies: ["settings-file-mutating"],
  },
],
```

把全局 `retries` 从 `1` 改为 `0`。若将来只需 CI 基础设施重试，应通过 CI 命令显式传 `--retries=1`，不得重新启用本地全局重试。

- [ ] **Step 3: 增加明确 npm 入口**

`web/package.json`：

```json
"test:e2e": "playwright test --project=settings-file-mutating --project=regression --retries=0",
"test:evidence": "playwright test --project=visual-evidence --workers=1 --retries=0"
```

运行 `npm install --package-lock-only` 同步 lockfile（即使只改 script 也保持 package 元数据一致）。

- [ ] **Step 4: 验证分类、隔离与稳定性**

Run:

```powershell
Set-Location web
npm run test:e2e -- --list
npm run test:evidence -- --list
npm run test:e2e
npm run test:e2e
npm run test:e2e
npm run test:evidence
Set-Location ..
```

Expected: 普通清单不含六个 evidence 文件；证据清单只含六个文件及其 `settings-file-mutating` 依赖；普通回归在 `retries=0` 下连续三轮 0 failed / 0 flaky；视觉证据单 worker 通过并生成到既有忽略目录。

- [ ] **Step 5: 更新 changelog 并提交**

```powershell
git add web/playwright.config.ts web/package.json web/package-lock.json web/tests/e2e changelog.md
git commit -m "分离 Playwright 回归与视觉证据测试"
```

---

### Task 6: 拆分 `test_core.py` 巨型聚合文件

**Files:**
- Delete: `tests/unit/test_core.py`
- Create: `tests/unit/test_console_and_cli.py`（原 91-226）
- Create: `tests/unit/test_golden_workspace.py`（原 234-262）
- Create: `tests/unit/test_structural_dom.py`（原 274-616）
- Create: `tests/unit/test_structural_change_scope.py`（原 652-1126，连同其局部 helper）
- Create: `tests/unit/test_structural_create_plan.py`（原 1151-1367）
- Create: `tests/unit/test_execution_baselines.py`（原 1368-1641）
- Create: `tests/unit/test_structural_preview.py`（原 1661-2128）
- Create: `tests/unit/test_job_recovery_integration.py`（原 2169-2563）
- Create: `tests/unit/test_cad_rename_groups.py`（原 2586-2898，连同 executor helper）
- Create: `tests/unit/test_cad_parallel_failures.py`（原 2920-3339，连同 executor helper）
- Create: `tests/unit/test_cad_publish_flow.py`（原 3428-3826）
- Create: `tests/unit/test_repair_end_to_end.py`（原 3827-4177，连同 repair helper）
- Create: `tests/unit/test_publish_end_to_end.py`（原 4178-4290，连同 publish helper）
- Modify: `changelog.md`

**Interfaces:**
- Produces: 与原 `test_core.py` 相同的 136 个测试函数及全部参数化节点，按当前领域边界拆分

- [ ] **Step 1: 保存拆分前节点与测试名清单**

Run:

```powershell
uv run python -m pytest tests/unit/test_core.py --collect-only | Out-File -Encoding utf8 "$env:TEMP\plan-int-003-test-core-before.txt"
uv run python -m pytest tests/unit/test_core.py
```

Expected: 当前文件通过；收集到 136 个测试函数对应的完整参数化节点。临时清单不提交。

- [ ] **Step 2: 按文件清单机械移动测试与局部 helper**

逐个目标文件移动对应行段；每个新文件只保留自身所需 import。`_execute_confirmed`、`_restore_confirmed` 等很短且跨文件使用的 helper 可以就近保留一份，但不得抽取生产代码或让 Builder/Manager 测试互相依赖。每创建一个文件立即运行该文件，再继续下一个。

- [ ] **Step 3: 删除聚合文件并比较节点语义**

测试文件路径变化会改变 nodeid 前缀，因此比较时去掉第一个 `::` 之前的路径，只比较 `test_name[param-id]` 多重集合：

```powershell
uv run python -m pytest tests/unit/test_console_and_cli.py tests/unit/test_golden_workspace.py tests/unit/test_structural_dom.py tests/unit/test_structural_change_scope.py tests/unit/test_structural_create_plan.py tests/unit/test_execution_baselines.py tests/unit/test_structural_preview.py tests/unit/test_job_recovery_integration.py tests/unit/test_cad_rename_groups.py tests/unit/test_cad_parallel_failures.py tests/unit/test_cad_publish_flow.py tests/unit/test_repair_end_to_end.py tests/unit/test_publish_end_to_end.py --collect-only | Out-File -Encoding utf8 "$env:TEMP\plan-int-003-test-core-after.txt"
```

用只读比较脚本断言拆分前后测试名多重集合相等；若同名参数化测试存在，必须保留重复计数，不能只比较 `set`。

- [ ] **Step 4: 运行拆分测试与全量 Python**

Run:

```powershell
uv run python -m pytest tests/unit/test_console_and_cli.py tests/unit/test_golden_workspace.py tests/unit/test_structural_dom.py tests/unit/test_structural_change_scope.py tests/unit/test_structural_create_plan.py tests/unit/test_execution_baselines.py tests/unit/test_structural_preview.py tests/unit/test_job_recovery_integration.py tests/unit/test_cad_rename_groups.py tests/unit/test_cad_parallel_failures.py tests/unit/test_cad_publish_flow.py tests/unit/test_repair_end_to_end.py tests/unit/test_publish_end_to_end.py
uv run python -m pytest
uv run ruff check tests
```

Expected: 全部通过；pytest 总节点数与 Task 4 基线一致；新文件单个不超过约 500 行。若某目标仍超过 500 行，在本任务内继续按最近的领域边界拆分，不得留下“以后再拆”的注释。

- [ ] **Step 5: 更新 changelog 并提交**

```powershell
git add tests/unit changelog.md
git commit -m "按领域拆分核心聚合测试"
```

---

### Task 7: 消除 `v021` 历史文件名并完成第二轮聚焦拆分

**Files:**
- Delete: `tests/unit/test_v021_domain_dom_hardening.py`
- Delete: `tests/unit/test_v021_editing.py`
- Create: `tests/unit/test_acsm_id_stability.py`
- Create: `tests/unit/test_acsm_slot_reconciliation.py`
- Create: `tests/unit/test_acsm_property_dom.py`
- Create: `tests/unit/test_editing_naming.py`
- Create: `tests/unit/test_property_csv.py`
- Create: `tests/unit/test_existing_snapshot_sources.py`
- Modify: `changelog.md`

**Interfaces:**
- Produces: 不含版本号命名的当前领域测试；原 87 个 pytest 项及参数化 case 全部保留

- [ ] **Step 1: 保存两个旧文件的节点清单并运行基线**

```powershell
uv run python -m pytest tests/unit/test_v021_domain_dom_hardening.py tests/unit/test_v021_editing.py --collect-only | Out-File -Encoding utf8 "$env:TEMP\plan-int-003-v021-before.txt"
uv run python -m pytest tests/unit/test_v021_domain_dom_hardening.py tests/unit/test_v021_editing.py
```

- [ ] **Step 2: 按现行领域归属移动测试**

移动规则：

| 旧文件范围 | 新文件 |
| --- | --- |
| domain hardening 69-185 | `test_acsm_id_stability.py` |
| domain hardening 272-516 | `test_acsm_slot_reconciliation.py` |
| domain hardening 517-676 | `test_acsm_property_dom.py` |
| editing 43-104、295-415 | `test_editing_naming.py` |
| editing 104-294 | `test_property_csv.py` |
| editing 416-583 | `test_existing_snapshot_sources.py` |

`legacy_transdigit` 名称描述的是仍受支持的兼容算法，可保留函数名；只删除文件名中的发布版本号，不把有效兼容测试误判为历史垃圾。

- [ ] **Step 3: 比较节点语义并验证**

与 Task 6 相同，忽略 nodeid 的文件路径前缀后比较测试名多重集合，随后运行：

```powershell
uv run python -m pytest tests/unit/test_acsm_id_stability.py tests/unit/test_acsm_slot_reconciliation.py tests/unit/test_acsm_property_dom.py tests/unit/test_editing_naming.py tests/unit/test_property_csv.py tests/unit/test_existing_snapshot_sources.py
uv run ruff check tests
```

Expected: 节点语义与拆分前一致，全部通过，每个文件低于约 500 行。

- [ ] **Step 4: 更新 changelog 并提交**

```powershell
git add tests/unit changelog.md
git commit -m "按现行领域重组 v0.2.1 回归测试"
```

---

### Task 8: 最终矩阵、文档收口与后续候选登记

**Files:**
- Modify: `.planning/plans/integration/PLAN-INT-003-test-system-consolidation.md`
- Modify: `.planning/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1-7 全部产出
- Produces: 可复核的最终验证记录；计划状态 `completed` 或带恢复条件的 `blocked`

- [ ] **Step 1: 运行最终 Fast 与 Full 矩阵**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Product All -Tier Fast
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Product All -Tier Full
```

Expected: 两条命令退出 0；`Full` 包含 Manager/Builder 普通 E2E，但不包含视觉证据、真实 CAD、PyInstaller 冒烟或生命周期测试。

- [ ] **Step 2: 单独运行视觉证据并检查高成本入口可发现性**

```powershell
Set-Location web
npm run test:evidence
Set-Location ..
uv run python -m pytest --markers
```

Expected: 视觉证据通过；marker 输出包含 `system_autocad`、`packaging_smoke`、`lifecycle` 及清楚说明。

- [ ] **Step 3: 记录未纳入本轮的超大文件候选**

在本计划“实际验证摘要”中列出仍超过 500 行的测试文件、行数及后续建议，但不在本任务继续拆分。至少复核：

```text
tests/integration/test_api.py
tests/integration/test_extension_api.py
tests/integration/test_sheet_catalog_export.py
tests/system_autocad/test_capabilities.py
tests/unit/test_publish_recovery.py
tests/unit/test_shell.py
```

这些是下一轮候选，不作为本计划完成阻塞条件；`test_core.py` 与 `test_v021_*` 必须已经不存在。

- [ ] **Step 4: 记录实际结果并关闭计划**

在本文末尾追加实际命令、通过/失败/跳过数量、告警数量与未执行原因。全部完成时把 frontmatter `status` 改为 `completed`；若同一环境性阻塞连续三轮无法解除，改为 `blocked` 并写明恢复条件。同步 `.planning/README.md` 条目的状态与摘要。

- [ ] **Step 5: 最终提交**

```powershell
git add .planning changelog.md
git commit -m "完成双产品测试体系收敛"
```

---

## 最终验收

以下条件全部满足才算完成：

1. `scripts/verify.ps1` 是唯一完整矩阵编排入口，`Manager|Builder|All` 与 `Fast|Full` 的 `-ListOnly` 矩阵有自动化测试。
2. 当前宿主直接运行统一 Python 门禁 0 failed；`setup.bat` 测试不再依赖父终端恰好为 CP936。
3. Alembic `No path_separator` 告警为 0；剩余第三方弃用告警逐类记录，未用全局 ignore 隐藏。
4. Manager release 在构建和打 tag 前调用 `Manager/Full`，任一前端或后端回归失败都会中止。
5. `npm run test:e2e` 不生成视觉证据，`npm run test:evidence` 只运行证据 project；两者都使用 `retries=0`。
6. `tests/demo/*.test.cjs` 不存在；两份 HTML Demo 与历史 QA 备忘仍可追溯。
7. AcSm 黄金样本不被同一实现路径重复执行；Manager re-export 兼容性由身份断言守护。
8. `pytest-cov` 不在 `pyproject.toml`、`uv.lock` 或执行脚本中。
9. `test_core.py`、`test_v021_domain_dom_hardening.py`、`test_v021_editing.py` 不存在；替代文件节点语义完整、每个约 500 行以内。
10. Fast、Full、视觉证据全部通过；真实 CAD、PyInstaller 冒烟和生命周期测试未执行时明确报告环境条件，不能写成“全部通过”。

## 风险与控制

| 风险 | 控制 |
| --- | --- |
| 测试文件移动时丢失参数化 case | 拆分前后比较去路径后的 nodeid 多重集合，并运行全量 pytest |
| 统一编排器用字符串拼接引入命令注入或路径转义问题 | 参数使用 `ValidateSet`，命令使用固定 `FilePath + Arguments[]`，不接受用户提供的任意命令 |
| Manager release 被 Builder 无关失败阻断或反之 | `-Product` 明确产品范围；`All` 只用于仓库级验证 |
| 视觉证据分轨后丢失唯一业务断言 | Task 5 逐文件映射非截图断言，唯一断言先迁入普通 spec 再分轨 |
| 关闭 Playwright retry 后重新暴露基础设施抖动 | 先落地现有 settings 隔离，普通回归 `retries=0` 连跑三轮；失败必须修根因或明确阻塞，不恢复全局 retry |
| 删除 Demo 测试损失设计追溯 | HTML Demo、SPEC 链接与 QA 备忘保留，并在备忘说明脚本退场时间和原因 |
| 去掉 `pytest-cov` 妨碍临时覆盖率分析 | 需要时可用 `uv run --with pytest-cov pytest --cov=...` 临时运行；正式门禁另行立项后再加入依赖 |
| 超大测试拆分制造跨文件 helper 耦合 | helper 随唯一消费域移动；小型跨域 helper 优先就近重复，不把测试便利函数放进生产代码 |

## 实际验证摘要

本节由 Task 8 填写。必须记录 Fast、Full、视觉证据、pytest 收集总数、passed/failed/skipped、告警分类，以及真实 CAD、PyInstaller 冒烟和生命周期测试的执行或跳过原因；不得用“同上”或“全部通过”代替具体结果。
