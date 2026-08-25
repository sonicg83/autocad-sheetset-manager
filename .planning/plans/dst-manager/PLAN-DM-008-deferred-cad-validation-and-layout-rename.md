---
id: PLAN-DM-008
title: 延后 CAD 校验与布局批量改名实施计划
status: proposed
owners:
  - dst-manager
created: 2026-08-25
updated: 2026-08-25
related:
  - ARCH-DM-001
  - ADR-DM-002
  - ADR-DM-003
  - SPEC-DM-002
  - SPEC-DM-003
---

# 延后 CAD 校验与布局批量改名实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让结构差异预览不再启动 AutoCAD，并按子集数量变化前沿把受影响 DWG 分流为布局批量改名或完整重建，在保持 Handle 与事务安全的前提下降低等待时间。

**Architecture:** 领域规划器一次派生最终结构并生成 `subset_operations` 与带 `cad_operation` 的 CAD 工作组；预览只捕获文件身份和 SHA-256，确认后的 Worker 在同一全局进程池中为每组启动一次 Core Console。`rename_only` 使用固定副文件协议和 `DstRenameLayouts` 两阶段改名，不读取或回写 Handle；`rebuild` 保留现有清除、导入和 Handle 回读链路，二者最后仍由同一发布事务整批提交。

**Tech Stack:** Python 3.12、pytest、Pydantic Settings、Vue 3、TypeScript、Vite、Playwright、AutoCAD 2016/2020 Core Console、C#、.NET Framework 4.8、SQLite、UV、npm、PowerShell。

**Spec:** [`SPEC-DM-003`](../../../docs/dst-manager/specs/SPEC-DM-003-deferred-cad-validation-and-subset-cad-operations.md)

## Global Constraints

- 目标系统为 Windows 11；Python 不低于 3.12，依赖只使用 UV 管理。
- AutoCAD Worker 为 x64、.NET Framework 4.8，并分别引用 AutoCAD 2016 和 2020 托管程序集。
- 快速预览不得启动 Core Console、创建 `.dst-manager/`、写任务记录或修改 DST/DWG。
- `DST_MANAGER_CAD_MAX_PARALLEL` 与 `Settings.cad_max_parallel` 取值范围为 1–10，默认值为 4；所有 CAD 工作单元共用一个进程池。
- 每个 `rename_only` 或 `rebuild` 工作单元只允许一次 `CoreConsoleExecutor.run()`。
- `rename_only` 不得调用 `DstDeleteLayouts`、布局导入或 `DstGetLayoutHandles`，不得覆盖原 `AcDbHandle`。
- 所有正式写入继续经过 `DST → XML DOM → DST`、写锁、永久 before 快照、暂存校验、发布日志、整批回滚和启动恢复。
- 用户文本不得直接拼接进 SCR、Shell 或文件操作；改名请求和结果使用暂存 DWG 旁的固定文件名。
- 测试只操作临时副本；真实 CAD 测试必须显式设置 `DST_MANAGER_RUN_AUTOCAD=1`。
- 代码注释、文档、测试说明与 Git commit message 使用简体中文；协议字段、命令名和错误码保留英文。

## 文件结构与职责

| 文件 | 职责 |
| --- | --- |
| `src/dst_manager/domain/planning.py` | 计算数量变化前沿，分类 `none`、`rename_only`、`rebuild`，输出完整子集操作摘要和 CAD 工作组。 |
| `src/dst_manager/application/service.py` | 生成无 CAD 的快速预览，捕获来源路径、身份和 SHA-256，形成确认摘要。 |
| `src/dst_manager/infrastructure/autocad/worker.py` | 渲染固定改名 SCR，写入改名请求并严格解析结果副文件。 |
| `plugins/src/DstManager.AutoCAD/LayoutRenameCommand.cs` | 读取固定请求、验证完整布局集合、两阶段改名并写出结果。 |
| `plugins/src/DstManager.AutoCAD/Commands.cs` | 暴露 `DstRenameLayouts`、现有删除布局和 Handle 命令入口。 |
| `src/dst_manager/application/cad_job.py` | 在共享并发池中分派改名/重建单元，验证结果并只为重建单元生成 Handle 绑定。 |
| `src/dst_manager/infrastructure/acsm_xml/document.py` | 更新布局文件/名称引用而保留 Handle，并继续为重建结果写入新 Handle。 |
| `src/dst_manager/infrastructure/persistence/database.py` | 持久化每个 CAD 单元的操作类型、开始/结束时间、耗时与错误。 |
| `migrations/versions/0003_dm008_job_file_cad_operation.py` | 为既有 SQLite 增加 CAD 单元操作与时间字段。 |
| `src/dst_manager/config.py` | 提供默认 4、范围 1–10 的 CAD 并发配置。 |
| `web/src/App.vue` | 展示快速预览的 CAD 操作、延后校验提示及任务文件操作类型。 |
| `tests/unit/test_core.py` | 覆盖领域前沿、快速预览、混合 Worker、Handle 保留和失败不发布。 |
| `tests/unit/test_autocad_worker.py` | 覆盖改名请求/结果协议和固定 SCR 命令集合。 |
| `tests/unit/test_cad_parallel.py` | 覆盖 1、4、10 并发上限及混合单元共享预算。 |
| `tests/integration/test_api.py` | 固定预览/执行 API 契约，不再依赖预览期 CAD 检查证据。 |
| `web/tests/e2e/main.spec.ts` | 验证操作标签、延后校验提示和任务进度展示。 |
| `tests/system_autocad/test_capabilities.py` | 验证 2016/2020 改名正确、Handle 不变、失败不发布和并发性能。 |
| `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md` | 实现完成后同步新的生产流程与测试边界。 |

---

### Task 1：用领域测试固定数量变化前沿与 CAD 操作分类

**Files:**

- Modify: `src/dst_manager/domain/planning.py:76-183`
- Modify: `tests/unit/test_core.py:501-646`

**Interfaces:**

- Produces: `_cardinality_frontier(original: list[Subset], derived: list[DerivedSubset]) -> int | None`，返回首个需要向后传播的最终子集下标；删除子集时返回其后第一个存续子集下标，尾部删除且无后续子集时返回 `len(derived)`。
- Produces: `_cad_operation(original: Subset | None, derived: DerivedSubset, layout_sources: Mapping[str, dict[str, str]], *, in_frontier_scope: bool, source_target: str | None, target: Path) -> Literal["none", "rename_only", "rebuild"]`。
- Produces: `execution_intent["subset_operations"]`，按最终顺序为每个子集记录 `subset_id`、`cad_operation`、`target_file` 和 `in_cardinality_scope`。
- Produces: 每个非 `none` group 保留发布字段 `operation=create|rebuild`，新增 `cad_operation=rename_only|rebuild`；每个布局新增 `original_layout: str | None`。

- [ ] **Step 1：写出前沿和标题改名的失败测试**

在 `tests/unit/test_core.py` 增加以下断言，使用文件中已有 `_planning_workspace()`、`_planning_sheet()` 和 `SuffixOptions`：

```python
def test_subset_title_only_renames_target_without_touching_following_subset(tmp_path: Path):
    first = tmp_path / "001 第一册.dwg"
    second = tmp_path / "002 第二册.dwg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    workspace = _planning_workspace(tmp_path, [
        Subset("subset-1", "001 第一册", 0, [_planning_sheet("sheet-1", "001", "第一册", first, "001 第一册")]),
        Subset("subset-2", "002 第二册", 1, [_planning_sheet("sheet-2", "002", "第二册", second, "002 第二册")]),
    ])

    plan = build_structural_plan(
        workspace,
        [{"type": "update_subset_title", "subset_id": "subset-1", "title": "第一分册"}],
        SuffixOptions(True, 1),
    )

    assert [(item["subset_id"], item["cad_operation"]) for item in plan["subset_operations"]] == [
        ("subset-1", "rename_only"),
        ("subset-2", "none"),
    ]
    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]] == [
        ("subset-1", "rename_only"),
    ]


def test_sheet_count_change_rebuilds_frontier_and_renames_following_subset(tmp_path: Path):
    first = tmp_path / "001 第一册.dwg"
    second = tmp_path / "002 第二册.dwg"
    template = tmp_path / "模板.dwt"
    for path in (first, second, template):
        path.write_bytes(path.name.encode("utf-8"))
    workspace = _planning_workspace(tmp_path, [
        Subset("subset-1", "001 第一册", 0, [_planning_sheet("sheet-1", "001", "第一册", first, "001 第一册")]),
        Subset("subset-2", "002 第二册", 1, [_planning_sheet("sheet-2", "002", "第二册", second, "002 第二册")]),
    ])

    plan = build_structural_plan(workspace, [{
        "type": "insert_sheet",
        "target_subset_id": "subset-1",
        "ordinal": 1,
        "placement": "after",
        "count": 1,
        "source": {"type": "template_layout", "file": str(template), "layout": "A3"},
    }], SuffixOptions(True, 1))

    assert plan["cardinality_frontier"] == {"index": 0, "subset_id": "subset-1"}
    assert [(group["subset_id"], group["cad_operation"]) for group in plan["groups"]] == [
        ("subset-1", "rebuild"),
        ("subset-2", "rename_only"),
    ]
    assert plan["groups"][1]["layouts"][0]["original_layout"] == "002 第二册"
```

- [ ] **Step 2：运行测试并确认旧规划器失败**

Run:

```powershell
rtk uv run pytest tests/unit/test_core.py -q -k "title_only_renames_target or sheet_count_change_rebuilds_frontier"
```

Expected: FAIL，旧计划缺少 `subset_operations`、`cardinality_frontier`、`cad_operation` 和 `original_layout`，且会把后续组统一当作完整重建。

- [ ] **Step 3：实现最小分类函数并接入计划**

在 `planning.py` 增加并从 `build_structural_plan()` 调用：

```python
CadOperation = Literal["none", "rename_only", "rebuild"]


def _cardinality_frontier(original: list[Subset], derived: list[DerivedSubset]) -> int | None:
    final_index = {subset.acsm_id: index for index, subset in enumerate(derived)}
    candidates: list[int] = []
    for index, subset in enumerate(derived):
        before = next((item for item in original if item.acsm_id == subset.acsm_id), None)
        if before is None or len(before.sheets) != len(subset.sheets):
            candidates.append(index)
    for original_index, subset in enumerate(original):
        if subset.acsm_id in final_index:
            continue
        following = next(
            (final_index[item.acsm_id] for item in original[original_index + 1 :] if item.acsm_id in final_index),
            len(derived),
        )
        candidates.append(following)
    return min(candidates) if candidates else None


def _cad_operation(
    original: Subset | None,
    derived: DerivedSubset,
    layout_sources: Mapping[str, dict[str, str]],
    *,
    in_frontier_scope: bool,
    source_target: str | None,
    target: Path,
) -> CadOperation:
    if original is None:
        return "rebuild"
    same_ids = [sheet.acsm_id for sheet in original.sheets] == [sheet.acsm_id for sheet in derived.sheets]
    try:
        stable_handles = all(int(sheet.layout.handle, 16) != 0 for sheet in original.sheets)
    except (TypeError, ValueError):
        stable_handles = False
    same_sources = same_ids
    for before, after in zip(original.sheets, derived.sheets, strict=True):
        source = layout_sources.get(after.acsm_id)
        if (
            source is None
            or source.get("type") != "existing_snapshot"
            or Path(str(source.get("file", ""))).resolve()
            != Path(before.layout.resolved_path or before.layout.file_name).resolve()
            or source.get("layout") != before.layout.layout_name
        ):
            same_sources = False
            break
    if not same_ids or not stable_handles or not same_sources:
        return "rebuild"
    changed = _subset_changed(original, derived, source_target or "", target)
    return "rename_only" if changed or in_frontier_scope else "none"
```

构造 `layouts` 时从 `original.sheets` 的稳定 ID 映射填入 `original_layout`；仅为非 `none` 子集添加 group。`cardinality_frontier` 使用最终索引和子集 ID，尾部删除没有存续后续组时允许 `subset_id=None`。

- [ ] **Step 4：补齐插入/删除子集和尾部删除回归并运行**

新增参数化用例，固定以下结果：插入子集为 `rebuild` 且后续为 `rename_only`；删除中间子集时后续为 `rename_only`；删除末尾子集不创建不存在的 CAD 组；同图纸数但稳定 ID/顺序不一致必须 `rebuild`。然后运行：

```powershell
rtk uv run pytest tests/unit/test_core.py -q -k "plan or frontier or rename_only"
rtk uv run ruff check src/dst_manager/domain/planning.py tests/unit/test_core.py
```

Expected: PASS；所有 group 都含合法 `cad_operation`，所有最终子集都出现在 `subset_operations` 一次。

- [ ] **Step 5：提交领域规划变更**

```powershell
rtk git add src/dst_manager/domain/planning.py tests/unit/test_core.py
rtk git commit -m "按子集数量变化前沿规划CAD操作"
```

### Task 2：把 CAD 布局检查移出快速预览

**Files:**

- Modify: `src/dst_manager/application/service.py:221-363,967-1095,1297-1322`
- Modify: `src/dst_manager/application/cad_job.py:75-93,275-341`
- Modify: `tests/unit/test_core.py:947-1200`
- Modify: `tests/integration/test_api.py:138-185`

**Interfaces:**

- Produces: `_collect_structural_source_baselines(workspace, execution_intent) -> list[dict[str, Any]]`，只做路径边界、扩展名、存在性、可读性和 `capture_file_baseline()`。
- Produces: `execution_intent["source_baselines"]`，元素为 `path`、`sha256`、`identity`、`source_types`、`requested_layouts`。
- Produces: `execution_intent["cad_validation_deferred"] = True`。
- Replaces: `CadJobRunner._validate_source_inspections()` 改为 `_validate_source_baselines()`；它只验证计划证据形状、覆盖集合和 hash/identity 一致性，不宣称布局已检查。

- [ ] **Step 1：把“不调用 CAD、无持久写入”写成失败测试**

```python
def test_structural_preview_is_fast_and_defers_cad_validation(tiny_workspace, tmp_path: Path):
    dst, _ = tiny_workspace
    service = DstManagerService(Settings(data_dir=tmp_path / "data"))
    service.inspect_template = Mock(side_effect=AssertionError("预览不得调用 CAD"))
    workspace = service.open_workspace(dst)
    command = {
        "type": "insert_subset",
        "ordinal": 1,
        "placement": "after",
        "title": "新建子集",
        "initial_sheet_count": 1,
        "source": {"type": "template_layout", "file": str(tmp_path / "A.dwg"), "layout": "001 平面"},
    }

    preview = service.preview_changes(workspace.id, workspace.revision_id, [command], "2016")

    assert preview["executable"] is True
    assert preview["execution_intent"]["cad_validation_deferred"] is True
    assert preview["execution_intent"]["source_baselines"][0]["sha256"] == file_sha256(tmp_path / "A.dwg")
    assert "source_inspections" not in preview["execution_intent"]
    assert not (tmp_path / ".dst-manager").exists()
    service.inspect_template.assert_not_called()
```

- [ ] **Step 2：运行快速预览和 API 测试，确认旧行为失败**

```powershell
rtk uv run pytest tests/unit/test_core.py tests/integration/test_api.py -q -k "fast_and_defers or structural_preview_and_execute"
```

Expected: FAIL；旧预览调用 `inspect_template()` 并返回 `source_inspections`。

- [ ] **Step 3：拆出轻量来源基准收集**

用 `_collect_structural_source_baselines()` 保留原 `_inspect_structural_sources()` 的路径注册、工作区边界、`.dwg/.dwt`、存在性和可读性诊断，删除临时副本、`WindowsWriteLocks` 和 `inspect_template()` 循环。核心输出为：

```python
baseline = capture_file_baseline(path)
if baseline is None:
    return [diagnostic("LAYOUT_SOURCE_NOT_FOUND", f"布局来源不存在：{path}")]
baselines.append({
    "path": str(path),
    "sha256": baseline.sha256,
    "identity": list(baseline.identity),
    "source_types": sorted(item["types"]),
    "requested_layouts": sorted(item["requested_layouts"], key=str.casefold),
})
execution_intent["source_baselines"] = baselines
execution_intent["cad_validation_deferred"] = True
```

`preview_changes()` 调用该函数后再调用 `_attach_expected_file_hashes()`；后者从 `source_baselines` 复用 hash/identity。保留 `execute_changes()` 的再次轻量预览和 `preview_digest` 比对，使确认瞬间的变化返回 `REPREVIEW_REQUIRED`。

- [ ] **Step 4：让确认 Worker 只验证基准证据，CAD 内容由每个单元验证**

将 `run()` 中的调用改为：

```python
self._validate_source_baselines(plan)
return self._execute(job_id, worker_id, job.get("attempt", 1), workspace, capability, payload["commands"], plan)
```

`_validate_source_baselines()` 必须确认来源集合与 group 的 `source_snapshot/source_file` 完全相等、无重复、请求布局集合相等、hash 对应 `expected_file_hashes`、identity 对应 `expected_file_identities`，但不得要求 `layouts` 或 `cad_version` 字段。缺失证据使用 `EXECUTION_SOURCE_BASELINE_MISSING`，不匹配使用 `EXECUTION_SOURCE_BASELINE_MISMATCH`。

运行：

```powershell
rtk uv run pytest tests/unit/test_core.py tests/integration/test_api.py -q -k "structural_preview or source_baseline or preview_digest"
rtk uv run ruff check src/dst_manager/application/service.py src/dst_manager/application/cad_job.py tests/unit/test_core.py tests/integration/test_api.py
```

Expected: PASS；预览无 Core Console，预览后或锁内来源漂移仍被拒绝。

- [ ] **Step 5：提交快速预览变更**

```powershell
rtk git add src/dst_manager/application/service.py src/dst_manager/application/cad_job.py tests/unit/test_core.py tests/integration/test_api.py
rtk git commit -m "将CAD布局校验延后到确认任务"
```

### Task 3：定义 Python 布局改名协议与固定 SCR

**Files:**

- Modify: `src/dst_manager/infrastructure/autocad/worker.py:23-62`
- Modify: `tests/unit/test_autocad_worker.py`

**Interfaces:**

- Produces: `rename_request_path(drawing: Path) -> Path`，固定后缀 `.dst-layout-rename-request.json`。
- Produces: `rename_result_path(drawing: Path) -> Path`，固定后缀 `.dst-layout-rename-result.json`。
- Produces: `write_rename_request(drawing: Path, layouts: list[dict[str, str]]) -> Path`，写 UTF-8、`version=1`、完整 `old_name/new_name` 数组。
- Produces: `parse_rename_result(text: str, expected_layouts: set[str]) -> int`，验证版本、最终集合和非负改名数量。
- Produces: `ScriptRenderer.render_rename(plugin: Path, request: Path) -> str`，固定命令只有环境设置、`NETLOAD`、`DstRenameLayouts`、经 `encode_scr_argument()` 编码的受控请求路径、恢复变量、`QSAVE`、`QUIT`。

- [ ] **Step 1：写协议与 SCR 失败测试**

```python
def test_render_rename_has_no_destructive_or_handle_commands():
    script = ScriptRenderer().render_rename(
        Path("C:/plugins/DstManager.AutoCAD.dll"),
        Path("C:/staging/001.dst-layout-rename-request.json"),
    )
    assert script.count("_.NETLOAD") == 1
    assert script.count("DstRenameLayouts") == 1
    assert script.count("_.QSAVE") == 1
    for forbidden in ("DstDeleteLayouts", "DstGetLayoutHandles", "_.-LAYOUT", "_Template"):
        assert forbidden not in script


def test_rename_sidecars_use_fixed_names_and_strict_result(tmp_path: Path):
    drawing = tmp_path / "001 第一册.dwg"
    request = write_rename_request(drawing, [
        {"original_layout": "001 第一册", "target_layout": "002 第一册"},
    ])
    assert request == drawing.with_suffix(".dst-layout-rename-request.json")
    assert json.loads(request.read_text(encoding="utf-8")) == {
        "version": 1,
        "layouts": [{"old_name": "001 第一册", "new_name": "002 第一册"}],
    }
    assert parse_rename_result(
        '{"version":1,"renamed_count":1,"final_layouts":["002 第一册"]}',
        {"002 第一册"},
    ) == 1
    with pytest.raises(ValueError, match="LAYOUT_RENAME_RESULT_INVALID"):
        parse_rename_result('{"version":1,"renamed_count":1,"final_layouts":["错误"]}', {"002 第一册"})
```

- [ ] **Step 2：运行测试确认接口尚不存在**

```powershell
rtk uv run pytest tests/unit/test_autocad_worker.py -q
```

Expected: FAIL，缺少 `render_rename`、请求写入与结果解析函数。

- [ ] **Step 3：实现固定协议**

实现路径函数和严格 JSON 校验；请求写入前拒绝 `original_layout` 缺失、大小写重复的旧名/新名和空名称：

```python
def write_rename_request(drawing: Path, layouts: list[dict[str, str]]) -> Path:
    rows = [{"old_name": item["original_layout"], "new_name": item["target_layout"]} for item in layouts]
    old_keys = [item["old_name"].casefold() for item in rows]
    new_keys = [item["new_name"].casefold() for item in rows]
    if not rows or any(not item["old_name"] or not item["new_name"] for item in rows):
        raise ValueError("LAYOUT_RENAME_REQUEST_INVALID")
    if len(old_keys) != len(set(old_keys)) or len(new_keys) != len(set(new_keys)):
        raise ValueError("LAYOUT_RENAME_REQUEST_INVALID")
    path = rename_request_path(drawing)
    path.write_text(json.dumps({"version": 1, "layouts": rows}, ensure_ascii=False), encoding="utf-8")
    return path
```

结果解析必须拒绝额外/缺失布局、布尔型 `renamed_count`、负数、重复结果和未知版本。

- [ ] **Step 4：运行协议回归和 Ruff**

```powershell
rtk uv run pytest tests/unit/test_autocad_worker.py -q
rtk uv run ruff check src/dst_manager/infrastructure/autocad/worker.py tests/unit/test_autocad_worker.py
```

Expected: PASS；改名脚本不含删除、导入或 Handle 命令。

- [ ] **Step 5：提交 Python 协议**

```powershell
rtk git add src/dst_manager/infrastructure/autocad/worker.py tests/unit/test_autocad_worker.py
rtk git commit -m "定义受控布局改名副文件协议"
```

### Task 4：实现 AutoCAD 2016/2020 `DstRenameLayouts` 命令

**Files:**

- Create: `plugins/src/DstManager.AutoCAD/LayoutRenameCommand.cs`
- Modify: `plugins/src/DstManager.AutoCAD/Commands.cs`
- Modify: `plugins/src/DstManager.AutoCAD/DstManager.AutoCAD.csproj`
- Modify: `tests/system_autocad/test_capabilities.py`

**Interfaces:**

- Consumes: 当前 DWG 旁固定的 `<stem>.dst-layout-rename-request.json`，schema 为 Task 3 的 `version/layouts/old_name/new_name`。
- Produces: `<stem>.dst-layout-rename-result.json`，schema 为 `version/renamed_count/final_layouts`。
- Produces: `[CommandMethod("DstRenameLayouts")] Commands.RenameLayouts()`，只接收 Worker 生成并经 SCR 编码的请求路径，且插件复核该路径等于当前 DWG 旁的固定请求路径。

- [ ] **Step 1：先写真实 CAD 命令契约测试**

在 `tests/system_autocad/test_capabilities.py` 增加一个参数化测试：先复制私有样本 DWG 到 `tmp_path`，用独立 `render_handles()` 记录 Handle；写入交换名称的请求，运行 `render_rename()`；再次用独立 `render_handles()` 读取结果并断言：

```python
assert set(after_handles) == set(expected_final_names)
assert sorted(before_handles.values()) == sorted(after_handles.values())
assert parse_rename_result(rename_result_path(drawing).read_text(encoding="utf-8"), set(expected_final_names)) == 2
```

再增加缺失旧布局、重复目标和意外额外布局三个失败用例，断言 Core Console 非零退出或结果副文件缺失，且测试只操作临时副本。

- [ ] **Step 2：运行双版本定向测试确认命令缺失**

```powershell
$env:DST_MANAGER_RUN_AUTOCAD = "1"
rtk uv run pytest tests/system_autocad/test_capabilities.py -q -k "rename_layouts"
```

Expected: 在可用 CAD 环境中 FAIL，AutoCAD 报告未知命令 `DstRenameLayouts`；环境缺失时明确 SKIP 并记录缺失条件，不能把 SKIP 当作通过。

- [ ] **Step 3：实现严格读取、全集合校验和两阶段改名**

`LayoutRenameCommand.cs` 使用 `DataContractJsonSerializer` 定义 `RenameRequest`、`RenameRow`、`RenameResult`。入口算法固定为：

```csharp
string expectedRequestPath = SidecarPath(database.Filename, ".dst-layout-rename-request.json");
string requestPath = ReadRequestPath(document.Editor);
if (!string.Equals(Path.GetFullPath(requestPath), expectedRequestPath, StringComparison.OrdinalIgnoreCase))
    throw new InvalidDataException("LAYOUT_RENAME_REQUEST_PATH_INVALID");
RenameRequest request = ReadRequest(requestPath);
List<string> current = ReadPaperLayoutNames(database);
ValidateRequest(request, current);
var temporary = request.Layouts.Select((row, index) => new {
    Row = row,
    Name = "DST_RENAME_" + Guid.NewGuid().ToString("N") + "_" + index.ToString("D4")
}).ToList();
foreach (var item in temporary)
    manager.RenameLayout(item.Row.OldName, item.Name);
foreach (var item in temporary)
    manager.RenameLayout(item.Name, item.Row.NewName);
List<string> finalNames = ReadPaperLayoutNames(database);
ValidateFinalNames(request, finalNames);
WriteResult(SidecarPath(database.Filename, ".dst-layout-rename-result.json"), finalNames, request.Layouts.Count);
```

比较使用 `StringComparer.OrdinalIgnoreCase`；拒绝 `Model`、空白、控制字符、长度大于 255、`<>/\":;?*|=` 中任一字符、旧/新名称大小写重复、当前集合与旧集合不相等。结果使用实际最终布局名排序写出。任何异常写入 Editor 错误消息后继续抛出，确保 Worker 得不到成功结果。

- [ ] **Step 4：接入命令和双版本工程构建**

在 `Commands.cs` 添加：

```csharp
[CommandMethod("DstRenameLayouts")]
public void RenameLayouts()
{
    LayoutRenameCommand.Execute(Application.DocumentManager.MdiActiveDocument);
}
```

在 `.csproj` 添加 `System.Runtime.Serialization` 引用和 `LayoutRenameCommand.cs` 编译项，然后运行：

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
```

Expected: AutoCAD 2016/2020 两套 x64、.NET Framework 4.8 插件均构建成功。

- [ ] **Step 5：重跑真实改名测试并提交插件**

```powershell
$env:DST_MANAGER_RUN_AUTOCAD = "1"
rtk uv run pytest tests/system_autocad/test_capabilities.py -q -k "rename_layouts"
rtk git add plugins/src/DstManager.AutoCAD tests/system_autocad/test_capabilities.py
rtk git commit -m "实现双版本AutoCAD布局批量改名命令"
```

Expected: 可用环境中名称互换和循环成功且 Handle 集合不变；非法请求失败且正式文件未参与测试。

### Task 5：让 CAD Worker 混合执行改名与重建并保留 Handle

**Files:**

- Modify: `src/dst_manager/application/cad_job.py:43-72,124-273,402-571`
- Modify: `src/dst_manager/infrastructure/acsm_xml/document.py:290-352,672-720`
- Modify: `src/dst_manager/infrastructure/persistence/database.py:87-105,158,401-425`
- Create: `migrations/versions/0003_dm008_job_file_cad_operation.py`
- Modify: `tests/unit/test_core.py:1670-2140`
- Modify: `tests/unit/test_database.py:193-240`

**Interfaces:**

- Replaces: `RebuildWorkUnit/RebuildResult` 重命名为 `CadWorkUnit/CadWorkResult`，字段不变，`bindings` 对 `rename_only` 为空。
- Produces: `_execute_group(...) -> CadWorkResult`，按 `group["cad_operation"]` 分派 `_rename_group()` 或 `_rebuild_group()`；未知/缺失值抛 `CAD_OPERATION_INVALID`。
- Produces: `AcsmDocument.apply_layout_references(references: dict[str, dict[str, str]], dst_dir: Path) -> None`，只更新 `FileName`、`Relative_FileName`、`Name`，不改 `AcDbHandle`。
- Produces: `job_files.cad_operation`、`started_at`、`finished_at`，API 的 `files[]` 原样返回三个字段。

- [ ] **Step 1：写改名单元一次调用且无 Handle 绑定的失败测试**

```python
def test_rename_group_uses_one_console_call_and_returns_no_bindings(tmp_path: Path):
    group = {
        "subset_id": "subset-1",
        "subset_name": "002 第一册",
        "operation": "rebuild",
        "cad_operation": "rename_only",
        "source_target_file": str(tmp_path / "001 第一册.dwg"),
        "target_file": str(tmp_path / "002 第一册.dwg"),
        "layouts": [{"sheet_id": "sheet-1", "original_layout": "001 第一册", "target_layout": "002 第一册"}],
    }
    executor = _RenameSuccessfulCadExecutor(["002 第一册"])
    runner.executor = executor

    result = runner._execute_group("job-1", workspace, capability, unit_for(group))

    assert executor.calls == 1
    assert executor.scripts[0].name == "rename-000.scr"
    assert result.bindings == {}
    assert rename_result_path(result.staged).is_file()
    assert not result.staged.with_suffix(".dst-handles.txt").exists()
```

再写 `_write_staged_dst()` 测试，原始 `AcDbHandle=AB`、文件和布局名变化后断言最终 XML 仍为 `AB`；另一个 `rebuild` 图纸必须使用回读的新 Handle。

- [ ] **Step 2：运行混合执行测试确认旧 Worker 失败**

```powershell
rtk uv run pytest tests/unit/test_core.py -q -k "rename_group or preserves_handle or mixed_cad"
```

Expected: FAIL；旧 Worker 只有 `_rebuild_group()`，并要求所有 group 返回 Handle。

- [ ] **Step 3：实现 `_rename_group()` 与统一分派**

统一 `_execute_group()`：

```python
def _execute_group(self, job_id, workspace, capability, unit):
    operation = unit.group.get("cad_operation")
    if operation == "rename_only":
        return self._rename_group(job_id, workspace, capability, unit)
    if operation == "rebuild":
        return self._rebuild_group(job_id, workspace, capability, unit)
    raise PlanningError("CAD_OPERATION_INVALID", f"CAD 工作单元操作无效：{operation}")
```

`_rename_group()` 复制不可变快照到 group 暂存目录，写固定请求，把该路径传给 `render_rename()`，生成 `rename-xxx.scr`，调用一次 executor，严格解析固定结果，验证最终名称集合，返回空 bindings，并在 job file 的日志摘要中使用阶段名“校验并批量改名布局”。`_rebuild_group()` 保持现有一次 Core Console 和 Handle 读取。

- [ ] **Step 4：分离名称/路径引用更新与 Handle 绑定**

在 `AcsmDocument` 实现：

```python
def apply_layout_references(self, references: dict[str, dict[str, str]], dst_dir: Path) -> None:
    for sheet_id, reference in references.items():
        sheet = self._find_by_id("AcSmSheet", sheet_id)
        if sheet is None:
            raise AcsmValidationError(f"SHEET_NOT_FOUND: {sheet_id}")
        layouts = _children(sheet, "AcSmAcDbLayoutReference")
        if len(layouts) != 1:
            raise AcsmValidationError(f"SHEET_LAYOUT_COUNT: {sheet_id}")
        layout = layouts[0]
        target = Path(reference["file"]).resolve()
        _set_prop(layout, "FileName", str(target))
        _set_prop(layout, "Relative_FileName", os.path.relpath(target, dst_dir))
        _set_prop(layout, "Name", reference["layout"])
```

`_write_staged_dst()` 只要求 `cad_operation == "rebuild"` 的 sheet 出现在 bindings；先 `apply_derived_document()`，再为 `rename_only` 调用 `apply_layout_references()`，最后只为 `rebuild` 调用 `apply_layout_bindings()`。执行后遍历所有最终图纸，拒绝空、非十六进制或 0 Handle。

新增 Alembic `0003_dm008_job_file_cad_operation`，为 `job_files` 增加可空 `cad_operation VARCHAR(20)`、`started_at DATETIME`、`finished_at DATETIME`；同步 ORM、`LATEST_SCHEMA_REVISION`、`_job_json()` 和旧库升级/物理漂移测试。每组进入时写 `cad_operation` 与 `started_at`，成功或失败时写 `finished_at`、耗时和错误。

运行：

```powershell
rtk uv run pytest tests/unit/test_core.py tests/unit/test_database.py tests/integration/test_transaction_recovery.py -q -k "rename or rebuild or handle or publish or recovery or upgraded"
rtk uv run alembic upgrade head
rtk uv run ruff check src/dst_manager/application/cad_job.py src/dst_manager/infrastructure/acsm_xml/document.py src/dst_manager/infrastructure/persistence/database.py migrations/versions/0003_dm008_job_file_cad_operation.py tests/unit/test_core.py tests/unit/test_database.py
```

Expected: PASS；改名保留 Handle，重建更新 Handle，混合任一失败均不发布。

- [ ] **Step 5：提交混合 Worker**

```powershell
rtk git add src/dst_manager/application/cad_job.py src/dst_manager/infrastructure/acsm_xml/document.py src/dst_manager/infrastructure/persistence/database.py migrations/versions/0003_dm008_job_file_cad_operation.py tests/unit/test_core.py tests/unit/test_database.py
rtk git commit -m "分流CAD布局改名与完整重建任务"
```

### Task 6：扩大并统一 CAD 并发预算

**Files:**

- Modify: `src/dst_manager/config.py:16-17`
- Modify: `src/dst_manager/application/cad_job.py:67-72,436-468`
- Modify: `tests/unit/test_cad_parallel.py`
- Modify: `tests/system_autocad/test_capabilities.py:260-310`

**Interfaces:**

- `Settings.cad_max_parallel: int = Field(default=4, ge=1, le=10)`。
- `CadJobRunner(..., max_parallel: int = 4)` 接受 1–10。
- `_run_groups()` 只向同一个 `ThreadPoolExecutor` 提交 `_execute_group()`，改名和重建不得拥有独立池。

- [ ] **Step 1：先修改并发测试为 1、4、10**

```python
def test_parallel_setting_defaults_to_four_and_rejects_out_of_range(tmp_path: Path):
    assert Settings(data_dir=tmp_path).cad_max_parallel == 4
    for value in (0, 11):
        with pytest.raises(ValidationError):
            Settings(data_dir=tmp_path, cad_max_parallel=value)


@pytest.mark.parametrize(("parallel", "expected"), [(1, 1), (4, 4), (10, 6)])
def test_mixed_group_scheduler_is_globally_bounded(tmp_path: Path, parallel: int, expected: int):
    # 六个 CadWorkUnit 交替使用 rename_only/rebuild，_execute_group 记录同时运行数。
    assert maximum == expected
```

- [ ] **Step 2：运行测试确认旧范围失败**

```powershell
rtk uv run pytest tests/unit/test_cad_parallel.py -q
```

Expected: FAIL；旧默认值为 2、上限为 4，并且调度器仍调用旧 `_rebuild_group()`。

- [ ] **Step 3：更新配置和共享调度器**

```python
cad_max_parallel: int = Field(default=4, ge=1, le=10)
```

将 `CadJobRunner` 的构造检查同步为 `1 <= max_parallel <= 10`，把线程池提交目标统一改为 `_execute_group`。失败后不再提交新组，已启动进程等待安全退出后统一抛出，结果仍按 `index` 确定性合并。

- [ ] **Step 4：运行并发、配置与混合失败测试**

```powershell
rtk uv run pytest tests/unit/test_cad_parallel.py tests/unit/test_core.py -q -k "parallel or mixed or failure_stops"
rtk uv run ruff check src/dst_manager/config.py src/dst_manager/application/cad_job.py tests/unit/test_cad_parallel.py
```

Expected: PASS；最大活跃进程不超过 1/4/10 配置，共享池中任一类型失败都停止提交新组。

- [ ] **Step 5：提交并发配置**

```powershell
rtk git add src/dst_manager/config.py src/dst_manager/application/cad_job.py tests/unit/test_cad_parallel.py tests/system_autocad/test_capabilities.py
rtk git commit -m "扩大并统一CAD并发预算"
```

### Task 7：在 Web 预览和任务进度中展示真实 CAD 操作

**Files:**

- Modify: `web/src/App.vue:13-56,265,276-325`
- Modify: `web/tests/e2e/main.spec.ts:20-40,150-165`

**Interfaces:**

- Consumes: `execution_intent.cad_validation_deferred`、`cardinality_frontier`、`subset_operations`、`groups[].cad_operation`、`source_baselines`。
- Produces: `cadOperationLabel("rename_only") = "批量改名布局"`，`cadOperationLabel("rebuild") = "清除并重建布局"`。
- Produces: 任务文件操作直接显示后端持久化的 `job.files[].cad_operation`、`started_at`、`finished_at` 和 `duration_ms`，不在前端重新判断操作资格。

- [ ] **Step 1：写 E2E 失败测试**

把结构预览 mock 改为一组 `rename_only` 和一组 `rebuild`，然后断言：

```typescript
await expect(page.getByText("CAD 布局校验将在确认后执行")).toBeVisible();
await expect(page.getByText("批量改名布局")).toBeVisible();
await expect(page.getByText("清除并重建布局")).toBeVisible();
await expect(page.getByText("数量变化前沿：第 2 个子集")).toBeVisible();
```

任务 mock 的 `files` 分别提供 `cad_operation=rename_only/rebuild`、`started_at`、`finished_at` 和 `duration_ms`，断言每行显示对应模式与时间。

- [ ] **Step 2：运行 E2E 确认旧 UI 失败**

```powershell
Set-Location web
rtk npm run test:e2e -- --grep "CAD 操作分流"
Set-Location ..
```

Expected: FAIL；旧界面只显示“创建 DWG/重建 DWG”和预览期“布局来源验证”。

- [ ] **Step 3：实现预览和任务显示**

新增纯显示函数：

```typescript
function cadOperationLabel(operation:string){
  if(operation==="rename_only")return "批量改名布局";
  if(operation==="rebuild")return "清除并重建布局";
  return "无需 CAD 操作";
}
```

移除“可用布局”预览表，改为来源路径/SHA-256/请求布局的轻量基准表；显示延后校验提示、前沿、每组模式和工作图纸数。任务表新增“操作”“开始”“结束”列，直接使用服务端文件进度字段。

- [ ] **Step 4：运行 Web 构建和全量 E2E**

```powershell
Set-Location web
rtk npm run build
rtk npm run test:e2e
Set-Location ..
```

Expected: TypeScript/Vite 构建成功；现有 latest-wins、跨工作区任务隔离、重试和新增 CAD 操作展示全部通过。

- [ ] **Step 5：提交 Web 变更**

```powershell
rtk git add web/src/App.vue web/tests/e2e/main.spec.ts
rtk git commit -m "展示CAD操作分流与延后校验状态"
```

### Task 8：完成事务回归、双版本验收、性能记录和文档闭环

**Files:**

- Modify: `tests/system_autocad/test_capabilities.py`
- Modify: `docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md`
- Modify: `docs/dst-manager/adr/ADR-DM-003-deferred-cad-validation-and-subset-cad-operations.md`
- Modify: `docs/dst-manager/specs/SPEC-DM-003-deferred-cad-validation-and-subset-cad-operations.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-008-deferred-cad-validation-and-layout-rename.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `changelog.md`

**Interfaces:**

- 2016/2020 均使用版本匹配的 Core Console 与插件；Handle 不变由生产改名流程之外的独立 `render_handles()` 前后检查证明。
- 性能记录至少包含并发 1、4、10、CAD 版本、工作单元数量、每种操作数量、每组 `duration_ms`、整批墙钟时间和峰值内存。
- 只有代码、非 CAD 回归、双版本真实 CAD、事务恢复和性能证据全部完成，才能把 Plan 改为 `completed`；环境缺失则记录恢复条件并保持 `active` 或按实际阻塞状态处理。

- [ ] **Step 1：补齐混合事务与漂移失败测试**

增加一个 `rename_only + rebuild + delete` 混合任务，分别在改名结果缺失、重建 Handle 错误、锁后源文件替换和第二个 CAD 单元进程失败处注入故障。每个用例必须断言：

```python
assert result["status"] == "FAILED"
assert {path: file_sha256(path) for path in official_files} == before_hashes
assert not (workspace.root / ".dst-manager" / "revisions" / result["id"] / "manifest.json").exists()
```

同时运行现有启动恢复测试，确认 create/replace/delete 混合发布与 COMMITTED 恢复不变。

- [ ] **Step 2：执行最小充分非 CAD 验证**

```powershell
$env:UV_LINK_MODE = "copy"
rtk uv sync --dev
rtk uv run ruff check .
rtk uv run pytest tests/unit/test_autocad_worker.py tests/unit/test_cad_parallel.py tests/unit/test_core.py tests/unit/test_database.py tests/integration/test_api.py tests/integration/test_transaction_recovery.py -q
rtk uv lock --check
rtk uv run alembic upgrade head
rtk git diff --check
```

Expected: 所有非 CAD 相关测试、Ruff、锁文件、数据库升级和空白检查通过。

- [ ] **Step 3：构建并运行双版本真实 CAD 验收**

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
rtk uv run dst-manager doctor
$env:DST_MANAGER_RUN_AUTOCAD = "1"
rtk uv run pytest tests/system_autocad/test_capabilities.py -q
```

Expected: 2016/2020 均通过标题改名 Handle 不变、名称交换/循环、数量前沿混合操作、完整重建、任一失败不发布和独立重开验证。若私有样本、console 或 DLL 缺失，记录具体 SKIP 数和恢复命令，不写成通过。

- [ ] **Step 4：记录并发 1、4、10 的真实性能**

对同一临时样本和相同 10 个 CAD 工作单元分别设置：

```powershell
$env:DST_MANAGER_CAD_MAX_PARALLEL = "1"
rtk uv run pytest tests/system_autocad/test_capabilities.py -q -k "mixed_operation_performance"
$env:DST_MANAGER_CAD_MAX_PARALLEL = "4"
rtk uv run pytest tests/system_autocad/test_capabilities.py -q -k "mixed_operation_performance"
$env:DST_MANAGER_CAD_MAX_PARALLEL = "10"
rtk uv run pytest tests/system_autocad/test_capabilities.py -q -k "mixed_operation_performance"
```

把 CAD 版本、CPU、内存、工作单元构成、进程峰值、各组耗时和整批墙钟写入本 Plan 的“实际验证记录”。结论只使用实测数据；不把单次波动描述为稳定加速比例。

- [ ] **Step 5：执行全量验证并闭环文档**

```powershell
rtk uv run pytest -q
Set-Location web
rtk npm run build
rtk npm run test:e2e
Set-Location ..
rtk git diff --check
```

将 `ARCH-DM-001` 的生产链改为快速预览无 CAD、确认后每组单次 Core Console、改名/重建分流和共享并发预算；在 `ADR-DM-003`、`SPEC-DM-003`、README、Plan 与 `changelog.md` 中记录实际命令、通过/跳过数和真实 CAD 证据。只有全部完成后将 Plan 标为 `completed`。

- [ ] **Step 6：提交最终验收与文档闭环**

```powershell
rtk git add tests/system_autocad/test_capabilities.py docs/dst-manager .planning/plans/dst-manager changelog.md
rtk git commit -m "完成CAD校验延后与布局改名交付闭环"
```

## 风险与回退

- **改名资格误判：** 资格必须同时证明稳定图纸 ID、顺序、数量、来源和非零 Handle；任何缺项选择 `rebuild` 或失败，绝不猜测。
- **布局名称交换导致碰撞：** 插件先把所有旧名改为 GUID 临时名，再统一改为最终名；任一步失败只污染暂存副本。
- **改名后 Handle 意外变化：** 生产路径不读 Handle，双版本验收必须用独立进程前后比较；若任一版本变化，停止接受该实现并将 Plan 标为 `blocked`，不得偷偷回写新 Handle。
- **确认后才发现来源布局错误：** 错误发生在暂存任务，界面展示具体工作组、阶段和日志；正式文件保持不变。
- **10 路并发内存压力：** 默认保持 4，10 只是允许上限；真实性能记录必须包含峰值内存，若 10 路不稳定则通过配置降低，不建立第二进程池。
- **旧任务缺少 `cad_operation`：** Worker 使用 `CAD_OPERATION_INVALID` 安全隔离，不能默认改名；任务重试必须重新预览生成新计划。
- **副文件残留或伪造：** 每个 attempt/group 使用独立暂存目录；执行前删除同名结果，执行后只接受当前 DWG 旁、schema v1 且完整集合匹配的结果。

## 完成标准

- 快速结构预览不启动 Core Console，不创建持久状态，并立即显示受影响 DWG、数量变化前沿与 CAD 操作类型。
- 仅子集名或布局名称顺行变化时使用 `rename_only`；数量变化子集重建，其后稳定子集批量改名。
- `rename_only` 每组一次 Core Console，不删除/导入布局、不读 Handle，最终 DST 保留原 Handle。
- `rebuild` 每组一次 Core Console，完整重建并严格回读 Handle。
- 共享并发预算默认 4、合法范围 1–10，混合单元不会超过总上限。
- Web 预览和任务进度展示后端给出的模式、耗时和失败信息。
- Ruff、相关及全量 Python、Web 构建/E2E、插件双版本构建、2016/2020 真实 CAD、事务恢复和性能记录均有可核验结果。
- ADR、Spec、Architecture、Plan、索引和 `changelog.md` 状态一致；未完成真实 CAD 验收时不得把本 Plan 标为 `completed`。

## 实际验证记录

计划建立时尚未实施代码，未运行实现测试或真实性能采样。本节由执行者按 Task 8 记录每条命令的退出码、测试通过/跳过数、双版本结果、硬件信息和并发 1/4/10 的墙钟及内存数据。
