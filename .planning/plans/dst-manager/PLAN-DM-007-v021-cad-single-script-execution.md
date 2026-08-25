---
id: PLAN-DM-007
title: v0.21 CAD 单脚本布局重建实施计划
status: proposed
owners:
  - dst-manager
created: 2026-08-25
updated: 2026-08-25
related:
  - SPEC-DM-002
  - ARCH-DM-001
  - GUIDE-SH-001
---

# DST Manager v0.21 CAD 单脚本布局重建实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项实施；步骤使用复选框跟踪。

**Goal:** 将结构性 DWG 重建与布局 Handle 获取合并到一次 Core Console 执行，保持现有布局绑定、发布事务和双版本 CAD 兼容性，同时减少每个受影响 DWG 的进程启动次数。

**Architecture:** 保留现有 `ScriptRenderer`、`CoreConsoleExecutor`、`CadJobRunner` 和固定 AutoCAD Worker 插件边界，只把结构性重建脚本从“重建脚本 + Handle 脚本”改为一个包含两者的脚本。生产路径在同一 Core Console 会话中完成布局修改、Handle 清单生成、保存和退出；独立新进程重开只作为真实验收和诊断步骤，不再作为正常任务成功的必要条件。

**Tech Stack:** Python 3.12、pytest、Ruff、`uv`、PowerShell、AutoCAD 2016/2020 Core Console、.NET Framework 4.8 Worker 插件。

**Spec:** [`SPEC-DM-002`](../../../docs/dst-manager/specs/SPEC-DM-002-v021-cad-single-script-execution.md)

## 全局约束

- 目标系统为 Windows 11；Python 不低于 3.12，依赖统一使用 `uv` 管理。
- 所有结构性写入继续经过 `DST → XML DOM → DST`、永久 before 快照、暂存校验、发布日志和可恢复整批发布。
- 只读模板检查不创建 `.dst-manager/`，不修改正式 DST/DWG，也不更新时间戳。
- 所有用户输入继续通过路径、布局名和 SCR 参数编码器校验；不得拼接任意 SCR、Shell 命令或未校验路径。
- 每个 `RebuildWorkUnit` 必须只生成一个结构性重建 SCR，并只调用一次 `CoreConsoleExecutor.run()`。
- `DstGetLayoutHandles` 必须在所有布局结构变更之后、最终 `QSAVE` 之前执行；Handle 校验通过前不得生成最终 DST 绑定。
- `render_handles()` 继续保留给模板检查等独立只读流程；不新增配置项、API、数据库字段或迁移。
- `cad_max_parallel` 的取值和调度模型不变；并行只发生在不可变源快照和任务暂存区。
- 正常任务不再依赖新进程重新打开 DWG；AutoCAD 2016/2020 的真实验收仍必须包含独立重开验证。
- 代码注释、文档、测试说明和 Git commit message 使用简体中文；固定 API、命令名、错误码和路径保持原始英文。
- 每项实现任务先写失败测试，再完成最小实现并运行相关测试；计划完成前不得将状态改为 `completed`。

## 文件结构与职责

| 文件 | 责任 |
| --- | --- |
| `docs/dst-manager/adr/ADR-DM-002-v021-cad-single-script-execution.md` | 记录取消生产路径新进程重开验证、采用单脚本执行及其后果。 |
| `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md` | 将第 6.3 节的旧双脚本描述改为单脚本顺序，保留独立真实验收重开步骤。 |
| `src/dst_manager/infrastructure/autocad/worker.py` | 保持 `render_rebuild()` 签名不变，使其输出布局重建、Handle 获取、保存和退出的完整 SCR；保留 `render_handles()`。 |
| `src/dst_manager/application/cad_job.py` | 删除结构性重建路径的第二次脚本生成和执行，统一处理一次执行结果、日志、Handle 解析及耗时。 |
| `tests/unit/test_autocad_worker.py` | 新增固定 SCR 命令顺序、单次 NETLOAD/Handle/QSAVE 和独立 Handle 脚本回归测试。 |
| `tests/unit/test_core.py` | 更新 CAD 执行器假实现，覆盖首次调用产生 Handle、每个工作单元一次调用、绑定结果和失败不发布。 |
| `tests/system_autocad/test_capabilities.py` | 调整双 DWG 失败注入计数，验证 2016/2020 单脚本真实重建和独立重开验收。 |
| `docs/dst-manager/specs/SPEC-DM-002-v021-cad-single-script-execution.md` | 记录已确认的需求边界、测试和验收要求。 |
| `.planning/plans/dst-manager/README.md` | 增加 `PLAN-DM-007` 入口和状态。 |
| `changelog.md` | 记录需求接受、计划建立和最终实现/验证结果。 |

---

### Task 1：冻结决策、架构基线和性能基线

**文件：**

- Create: `docs/dst-manager/adr/ADR-DM-002-v021-cad-single-script-execution.md`
- Modify: `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md:234-246`
- Modify: `docs/dst-manager/specs/SPEC-DM-002-v021-cad-single-script-execution.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `changelog.md`

**Interfaces:**

- 新增 `ADR-DM-002`，结论为“结构性重建默认采用单脚本单次 Core Console；生产路径取消新进程重开验证；新进程重开保留为双版本系统验收/诊断”。
- `ARCH-DM-001` 第 6.3 节必须描述同一脚本的固定顺序，并明确第 12.2 节的独立重开验收不属于正常任务执行。
- `SPEC-DM-002` 已为 `accepted`；本任务确认其 `related` 包含 `ADR-DM-002` 和 `PLAN-DM-007`。

- [ ] **步骤 1：记录当前双脚本基线**

在修改 Python 代码前，使用现有私有样本的临时副本运行一条代表性结构性任务，记录受影响 DWG 数量 `G`、每个组的 `rebuild-*.scr` 和 `handles-*.scr` 数量、单 DWG `duration_ms`、整批墙钟时间、AutoCAD 版本和 `cad_max_parallel`。当前代码基线应满足：

```text
结构性重建 Core Console 调用数 = 2G
每个重建组都存在 rebuild-xxx.scr 和 handles-xxx.scr
```

如果真实样本不可用，记录可由当前 `cad_job.py` 两次 `executor.run()` 直接证明的调用数公式，并明确真实基线的恢复条件。

基线运行命令：

```powershell
$env:DST_MANAGER_RUN_AUTOCAD = "1"
uv run pytest tests/system_autocad/test_capabilities.py -q -k "structural_subset_title_change_rebuilds_dwg_and_dst or largest_25_layout_group_rebuilds_in_order"
```

- [ ] **步骤 2：写 ADR 和架构基线的失败检查**

运行：

```powershell
rtk rg -n "ADR-DM-002|第二次用 Core Console|一次 Core Console|DstGetLayoutHandles" docs/dst-manager .planning/plans/dst-manager
```

预期：`ARCH-DM-001` 仍能定位旧的第二次 Core Console 描述，`ADR-DM-002` 尚不存在；该检查用于确认本任务确实覆盖旧决策。

- [ ] **步骤 3：最小实现决策和架构文字**

创建 `ADR-DM-002`，说明 Legacy 单脚本证据、减少启动成本的收益、取消新进程重开验证的风险、保留双版本独立验收的缓解措施，以及不采用配置开关的理由。将 `ARCH-DM-001` 第 6.3 节改为：

```text
1. 暂存基础 DWG；
2. 设置 FILEDIA/SECURELOAD/CMDECHO；
3. NETLOAD 匹配版本插件；
4. DstDeleteLayouts；
5. 按最终顺序导入和重命名布局；
6. DstDeleteDefaultLayout；
7. DstGetLayoutHandles；
8. 恢复变量、QSAVE、QUIT；
9. Core Console 退出后解析 .dst-handles.txt，并完成计划匹配校验。
```

在架构测试策略中保留“独立新进程重新打开最终 DWG”的 2016/2020 验收步骤，但删除其作为正常生产路径步骤的表述。更新规范、README、计划索引和 `changelog.md` 的状态及链接。

- [ ] **步骤 4：运行文档元数据和链接检查**

运行：

```powershell
rtk rg -n "^id:|^status:|ADR-DM-002|PLAN-DM-007|SPEC-DM-002" docs/dst-manager .planning/plans/dst-manager
rtk git diff --check
```

预期：永久 ID 唯一，SPEC 为 `accepted`，PLAN 为 `proposed`，README 链接目标存在，diff 无空白错误。

- [ ] **步骤 5：提交决策基线**

```powershell
git add docs/dst-manager/adr/ADR-DM-002-v021-cad-single-script-execution.md docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md docs/dst-manager/specs/SPEC-DM-002-v021-cad-single-script-execution.md docs/dst-manager/README.md .planning/plans/dst-manager/README.md changelog.md
git commit -m "确定CAD单脚本布局重建决策"
```

### Task 2：先测试再合并 SCR 渲染顺序

**文件：**

- Modify: `src/dst_manager/infrastructure/autocad/worker.py:29-47`
- Create: `tests/unit/test_autocad_worker.py`

**Interfaces:**

- 保持 `ScriptRenderer.render_rebuild(plugin: Path, layouts: list[dict[str, str]]) -> str` 签名不变。
- `render_rebuild()` 生成一个完整 SCR，包含一次 `_.NETLOAD`、一次 `DstGetLayoutHandles`、一次 `_.QSAVE` 和一次 `_.QUIT`。
- `DstGetLayoutHandles` 必须晚于 `DstDeleteDefaultLayout` 和所有布局重命名，早于 `_.QSAVE`。
- `render_handles(plugin: Path) -> str` 保持独立 Handle 检查脚本的现有语义。

- [ ] **步骤 1：写 SCR 顺序失败测试**

在 `tests/unit/test_autocad_worker.py` 添加：

```python
from pathlib import Path

from dst_manager.infrastructure.autocad.worker import ScriptRenderer


def test_render_rebuild_contains_handle_read_in_the_same_script():
    script = ScriptRenderer().render_rebuild(
        Path("C:/plugins/DstManager.AutoCAD.dll"),
        [{
            "source_file": "C:/sources/template.dwg",
            "source_layout": "A3",
            "target_layout": "001 平面",
        }],
    )

    assert script.count("_.NETLOAD") == 1
    assert script.count("DstGetLayoutHandles") == 1
    assert script.count("_.QSAVE") == 1
    assert script.count("_.QUIT") == 1
    assert script.index("DstDeleteDefaultLayout") < script.index("DstGetLayoutHandles")
    assert script.index("DstGetLayoutHandles") < script.index("_.QSAVE") < script.index("_.QUIT")


def test_render_handles_remains_a_standalone_handle_script():
    script = ScriptRenderer().render_handles(Path("C:/plugins/DstManager.AutoCAD.dll"))

    assert "DstGetLayoutHandles" in script
    assert "DstDeleteLayouts" not in script
```

- [ ] **步骤 2：运行失败测试**

运行：`uv run pytest tests/unit/test_autocad_worker.py -q`

预期：第一项失败，因为当前 `render_rebuild()` 没有 `DstGetLayoutHandles`；第二项保持通过。

- [ ] **步骤 3：最小修改渲染器**

在 `render_rebuild()` 的 `DstDeleteDefaultLayout` 之后、恢复环境变量之前插入：

```python
lines.append("DstGetLayoutHandles")
```

保持现有固定命令、参数编码、布局临时名称、危险字符拒绝和 `render_handles()` 不变；不要在本任务引入新的脚本模式、配置项或命令参数。

- [ ] **步骤 4：运行渲染器回归测试**

运行：

```powershell
uv run pytest tests/unit/test_autocad_worker.py -q
uv run ruff check src/dst_manager/infrastructure/autocad/worker.py tests/unit/test_autocad_worker.py
```

预期：两项测试通过，Ruff 无错误；脚本命令顺序与 `SPEC-DM-002` 一致。

- [ ] **步骤 5：提交渲染器变更**

```powershell
git add src/dst_manager/infrastructure/autocad/worker.py tests/unit/test_autocad_worker.py
git commit -m "合并布局重建与Handle读取脚本"
```

### Task 3：让 CadJobRunner 每个工作单元只执行一次

**文件：**

- Modify: `src/dst_manager/application/cad_job.py:479-520`
- Modify: `tests/unit/test_core.py:1676-1705`

**Interfaces:**

- `_rebuild_group()` 继续返回 `RebuildResult`，其 `bindings`、`duration_ms`、`peak_memory_bytes`、`staging_bytes` 字段含义不变。
- 结构性重建只写入 `rebuild-xxx.scr`，不再创建 `handles-xxx.scr`。
- `CoreConsoleExecutor.run()` 的结果只需合并一次日志；阶段名统一为“重建布局并读取布局 Handle”。
- `parse_handles()`、计划布局集合校验、零 Handle 校验和最终绑定生成保持不变。

- [ ] **步骤 1：写一次调用失败测试**

在现有 `_SuccessfulCadExecutor` 基础上增加一次调用断言，使 Handle 在第一次调用时写出：

```python
class _SingleCallSuccessfulCadExecutor:
    def __init__(self, handle_text: str):
        self.handle_text = handle_text
        self.calls = 0
        self.scripts: list[Path] = []

    def run(self, _capability, drawing, script, _timeout):
        self.calls += 1
        self.scripts.append(script)
        drawing.with_suffix(".dst-handles.txt").write_text(self.handle_text, encoding="utf-8")
        return SimpleNamespace(stdout="", stderr="", peak_memory_bytes=1)


def test_rebuild_group_uses_one_combined_console_call(tmp_path):
    # 复用现有 RebuildWorkUnit、_planning_workspace 和 create 组夹具。
    executor = _SingleCallSuccessfulCadExecutor("001 新建子集=AB\n")
    runner.executor = executor

    result = runner._rebuild_group("job-1", workspace, capability, unit)

    assert result.bindings["sheet-new"]["handle"] == "AB"
    assert executor.calls == 1
    assert [script.name for script in executor.scripts] == ["rebuild-000.scr"]
    assert not (scripts / "handles-000.scr").exists()
```

测试必须继续覆盖既有重建组、创建组、多布局组和 `HANDLE_LAYOUT_MISMATCH`/`HANDLE_OUTPUT_INVALID` 分支。

- [ ] **步骤 2：运行失败测试**

运行：`uv run pytest tests/unit/test_core.py -q -k "rebuild_group or handle or create_group or chained"`

预期：新增一次调用测试失败；现有模拟器因仍把 Handle 写在第二次调用或只识别 `handles-*.scr` 而失败，证明测试确实锁定了新契约。

- [ ] **步骤 3：最小修改 CadJobRunner 和假执行器**

在 `_rebuild_group()` 中保留一次脚本写入和一次执行：

```python
rebuild_script.write_text(
    self.renderer.render_rebuild(capability.plugin, group["layouts"]),
    encoding="mbcs",
)
phase = "重建布局并读取布局 Handle"
completed = self.executor.run(capability, staged, rebuild_script, unit.timeout)
output += self._format_console_output(phase, completed.stdout, completed.stderr)
```

随后直接读取 `staged.with_suffix(".dst-handles.txt")`，继续执行原有集合、重复、零值和绑定校验。删除 `handle_script` 的生成和第二次 `executor.run()`；`peak_memory_bytes` 直接使用本次结果，`duration_ms` 仍覆盖整个工作单元。同步修改 `_SuccessfulCadExecutor` 和 `_PerDrawingCadExecutor`，使它们在每次重建脚本执行时写出对应 Handle，而不依赖脚本 stem 为 `handles-*`。

- [ ] **步骤 4：运行 CAD Worker 非真实回归**

运行：

```powershell
uv run pytest tests/unit/test_autocad_worker.py tests/unit/test_core.py -q
uv run ruff check src/dst_manager/application/cad_job.py tests/unit/test_core.py
```

预期：脚本顺序、单次执行、创建/重建、Handle 校验、最终 DST 绑定和不发布失败路径全部通过；Ruff 无错误。

- [ ] **步骤 5：提交 Worker 变更**

```powershell
git add src/dst_manager/application/cad_job.py tests/unit/test_core.py
git commit -m "让CAD工作单元单次完成布局重建和Handle读取"
```

### Task 4：修正失败注入、日志和多 DWG 回归

**文件：**

- Modify: `tests/system_autocad/test_capabilities.py:314-331`
- Modify: `tests/unit/test_core.py`
- Modify: `src/dst_manager/application/cad_job.py`

**Interfaces:**

- 双 DWG 失败注入必须按单脚本调用序列注入第二个 Core Console 调用失败，而不是第三个。
- 失败时仍返回 `CAD_PROCESS_FAILED`，正式文件哈希保持不变，修订目录不生成成功 manifest。
- 逐 DWG 日志只保留一个合并阶段，仍包含 stdout、stderr、退出码和异常上下文。
- 不新增任务状态、错误码或 API 字段。

- [ ] **步骤 1：先收紧失败注入断言**

把现有 `fail_third_console_call` 改为 `fail_second_console_call`，记录失败脚本名，并保留以下关键断言：

```python
failed_script = None


def fail_second_console_call(self, capability, drawing, script, timeout):
    nonlocal calls, failed_script
    calls += 1
    if calls == 2:
        failed_script = Path(script).name
        raise subprocess.CalledProcessError(1, [str(capability.console)], "", "INJECTED_DWG_FAILURE")
    return original_run(self, capability, drawing, script, timeout)


assert result["status"] == "FAILED"
assert result["error_code"] == "CAD_PROCESS_FAILED"
assert after == before
assert not (tmp_path / ".dst-manager" / "revisions" / result["id"] / "manifest.json").exists()
assert failed_script == "rebuild-001.scr"
```

- [ ] **步骤 2：运行失败注入测试确认计数不匹配**

运行：`uv run pytest tests/system_autocad/test_capabilities.py -q -k "injected_second_dwg_failure"`

预期：单脚本实现中第二个工作单元的 `rebuild-001.scr` 失败；旧双脚本实现会在第一个工作单元的 `handles-000.scr` 失败，因此脚本名断言能够区分两种调用契约。若真实 CAD 前置条件缺失，使用同等逻辑的单元假执行器覆盖，不把跳过误判为通过。

- [ ] **步骤 3：调整日志阶段和失败上下文**

确认 `_rebuild_group()` 的 `phase` 从两个阶段合并为“重建布局并读取布局 Handle”，并保留 `CalledProcessError` 的 stdout/stderr、退出码和 `repr(exc)` 写入逐 DWG 日志。不要删除错误日志中的 DWG、脚本和工作单元路径信息。

- [ ] **步骤 4：运行事务与并行回归**

运行：

```powershell
uv run pytest tests/unit/test_core.py tests/unit/test_cad_parallel.py tests/integration/test_transaction_recovery.py -q
```

预期：单工作单元失败停止后续提交、并行上限、创建/替换/删除混合发布、发布回滚和启动恢复行为不变。

- [ ] **步骤 5：提交失败语义回归**

```powershell
git add src/dst_manager/application/cad_job.py tests/unit/test_core.py tests/system_autocad/test_capabilities.py
git commit -m "更新单脚本CAD失败回滚回归"
```

### Task 5：执行双版本真实 CAD 验收和性能验证

**文件：**

- Modify: `tests/system_autocad/test_capabilities.py`（仅在需要补充单脚本断言时）
- Modify: `.planning/plans/dst-manager/PLAN-DM-007-v021-cad-single-script-execution.md`（追加实际验证记录）
- Modify: `changelog.md`（记录实际可核验结果）

**Interfaces:**

- AutoCAD 2016/2020 均使用匹配的 Core Console 和 Worker 插件；测试只操作私有样本的临时副本。
- 结构性任务成功后，必须用独立验证步骤重新打开最终 DWG，验证生产路径取消新进程重开没有掩盖 DWG 兼容性问题。
- 性能报告至少包含 1、2、25 布局工作单元，以及 `cad_max_parallel=1/2` 的 Core Console 调用数和墙钟耗时。

- [ ] **步骤 1：构建匹配版本插件并确认能力**

运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
uv run dst-manager doctor
```

预期：2016/2020 插件构建成功；能力诊断明确列出匹配的 `accoreconsole.exe` 和 DLL。缺少私有样本不影响能力探针，但必须在验证记录中说明。

- [ ] **步骤 2：运行双版本结构性系统测试**

运行：

```powershell
$env:DST_MANAGER_RUN_AUTOCAD = "1"
uv run pytest tests/system_autocad/test_capabilities.py -q
```

预期：2016/2020 均通过单布局重建、模板创建、布局顺序/命名/Handle 回读、25 布局分组和失败不发布测试；如果样本或 Core Console 不可用，测试只能按既有 skip 规则跳过，并记录恢复条件。

- [ ] **步骤 3：验证独立新进程重开**

在单脚本任务成功后，对暂存或已发布临时副本分别用 2016/2020 新启动一次 Core Console，执行现有独立 `render_handles()` 脚本并解析清单。断言 DWG 可打开、Handle 清单非空、布局集合与计划一致；该步骤不得回写正式工作区。

- [ ] **步骤 4：记录前后性能证据**

对相同私有样本和相同任务参数记录：

```text
基线：G 个 DWG -> 2G 次 Core Console，rebuild/handles 两类脚本各 G 个
目标：G 个 DWG -> G 次 Core Console，仅 rebuild 脚本 G 个
```

同时记录每个 DWG 的 `duration_ms`、整批墙钟耗时、布局数量、AutoCAD 版本、并行度、插件加载次数和失败时正式文件 hash。墙钟测量可使用现有系统测试外层 PowerShell `Measure-Command`，不把一次机器抖动解释为性能结论。

- [ ] **步骤 5：提交真实验收记录**

```powershell
git add tests/system_autocad/test_capabilities.py .planning/plans/dst-manager/PLAN-DM-007-v021-cad-single-script-execution.md changelog.md
git commit -m "完成单脚本CAD双版本验收记录"
```

### Task 6：全量验证、文档闭环和交付状态

**文件：**

- Modify: `docs/dst-manager/README.md`
- Modify: `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md`
- Modify: `docs/dst-manager/adr/ADR-DM-002-v021-cad-single-script-execution.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-007-v021-cad-single-script-execution.md`
- Modify: `changelog.md`

**Interfaces:**

- 所有文档的 ID、状态、related、索引和实际验证结果一致。
- `SPEC-DM-002` 与 `ADR-DM-002` 保持 `accepted`；实现和验证完成后补充可核验的实施证据，本计划只有在要求全部满足后标记为 `completed`。
- 若真实 CAD 环境缺失，计划保持 `active`，并记录具体恢复条件，不把跳过项写成通过。

- [ ] **步骤 1：运行最小充分的非 CAD 验证**

运行：

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest tests/unit/test_autocad_worker.py tests/unit/test_core.py tests/unit/test_cad_parallel.py tests/integration/test_transaction_recovery.py -q
uv lock --check
git diff --check
```

预期：依赖、Ruff、相关单元/集成测试、锁文件和空白检查全部通过；不因本任务未修改 Web 而额外执行 Web E2E。

- [ ] **步骤 2：运行完整 Python 回归**

运行：`uv run pytest -q`

预期：全量 Python 测试通过；真实 CAD 测试只在显式环境变量和私有样本存在时执行，跳过原因可复现。

- [ ] **步骤 3：核对文档和发布边界**

运行：

```powershell
rtk rg -n "第二次用 Core Console|handles-\{group_index|两次启动|render_handles\(capability\.plugin\)" src docs tests
```

预期：`render_handles()` 只保留在模板/独立 Handle 流程及对应测试中；结构性 `_rebuild_group()` 不再生成或执行 `handles-xxx.scr`；架构文档把独立重开明确标为验收/诊断。

- [ ] **步骤 4：补充最终验证摘要并更新状态**

在本计划的“实际验证记录”中追加每条命令的退出码、通过/跳过数量、AutoCAD 版本、性能数据和恢复条件；同步将 `ADR-DM-002`、`ARCH-DM-001`、README 和 `changelog.md` 更新为最终可核验状态。只有单脚本功能、事务回归、2016/2020 可用环境验收和性能证据完成后，才把本计划标记为 `completed`。

- [ ] **步骤 5：提交交付闭环**

```powershell
git add docs/dst-manager .planning/plans/dst-manager changelog.md
git commit -m "完成CAD单脚本布局重建交付闭环"
```

## 风险与回退

- **同一会话读取到的布局字典与保存结果不一致：** 生产路径在脚本中先完成全部布局修改，再执行 `DstGetLayoutHandles` 和 `QSAVE`；双版本验收额外用新进程重开验证保存结果。
- **Handle 文件缺失或残留：** 每个任务使用独立 attempt/group 暂存目录；执行后只接受当前暂存 DWG 同目录生成且通过集合校验的 `.dst-handles.txt`，缺失或异常立即失败，不回退到第二次生产调用。
- **单脚本失败后暂存 DWG 已部分修改：** 所有修改仍只发生在任务暂存区，正式发布前继续执行基准、结构和 Handle 校验；任何失败都不进入发布器。
- **失败注入仍按旧调用数判断：** 任务 4 将第二个 Core Console 失败注入、正式 hash 不变和无 manifest 断言固定下来，避免回归测试漏掉调用契约变化。
- **性能收益被布局处理时间掩盖：** 用相同样本、版本、布局数量和并行度记录墙钟与单 DWG `duration_ms`，同时以 `2G → G` 的进程数变化作为确定性收益，不预设耗时比例。
- **需要临时恢复旧验证：** 不新增生产配置开关；如验收发现必须保留重开验证，应暂停合并、将计划标记为 `blocked`，新增决策后再调整规范和实现，不在代码中悄悄恢复第二次调用。

## 完成标准

- 每个结构性 `RebuildWorkUnit` 只生成一个 SCR、只调用一次 Core Console，并在同一脚本内完成布局修改、Handle 获取、保存和退出。
- `render_handles()` 的模板检查流程仍可独立运行。
- Handle 绑定、布局顺序/名称、DST/XML 校验、永久快照、发布和回滚结果与原流程一致。
- 单元、集成和失败注入测试通过；2016/2020 真实 CAD 测试在可用环境中通过，缺失环境有明确跳过记录。
- 受影响 DWG 的 Core Console 调用数由 `2G` 降为 `G`，并完成相同条件下的性能记录。
- `uv run ruff check .`、`uv run pytest -q`、`uv lock --check` 和相关真实 CAD 验收均有实际结果；计划、规范、ADR、架构、索引和 `changelog.md` 可相互追溯。
