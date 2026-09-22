---
id: PLAN-DM-036
title: 标准驱动的新图纸集创建实施计划
status: proposed
owners:
- dst-manager
created: 2026-09-21
updated: 2026-09-22
related:
- RFC-INT-003
- PLAN-DM-035
- PLAN-DM-038
- SPEC-DM-017
- ADR-DM-001
- ADR-DM-003
- ADR-DM-005
- SPEC-DM-008
- SPEC-DM-014
---

# 标准驱动的新图纸集创建实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户从已发布图纸标准创建完整 DST/DWG 项目，并在成功后直接进入普通 Manager 工作区。

**Architecture:** 创建草稿是应用数据目录中的可恢复 JSON，不是第二个项目数据库；领域层把标准、输入和现有编号策略编译成不可变 `CreationPlan`；执行层在隔离 attempt 中生成 DWG/DST，再复用 Manager 发布事务原子写入新目录。前端只编辑草稿、导入 XLSX、展示预览和观察任务。

**Tech Stack:** Python 3.12、FastAPI、lxml、openpyxl、现有 Core Console/Worker、Vue 3、TypeScript、Vite、Playwright、pytest。

**Spec:** [`docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md`](../../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)

## Global Constraints

- 必须先完成 PLAN-DM-035 **与 PLAN-DM-038**：本计划消费 SPEC-DM-017 的 Schema v1（普通属性/派生属性/全局 DWG 命名模板），
  通用规则模型与旧顶层 `rules` 已删除；未完成 PLAN-DM-038 时不得开始本计划实现。
- 正式创建只能选择已发布且依赖可用的标准。
- 一个子集创建一个主 DWG，每张图纸对应其中一个布局。
- 创建阶段同一子集统一基础模板、布局模板和图幅；该约束不进入后续归档校验。
- 编号复用现有 `derive_document_structure` 语义，包括连续流水号、补零、后缀样式和不编号关键字。
- 目标只能是尚不存在的新目录或空目录；不得覆盖或合并已有工程。
- 预览不启动 AutoCAD；正式执行只使用固定 Worker 协议和标准包内资产。
- 创建失败不得在目标留下半成品；重试使用新 attempt。

## Review Focus

- XLSX 同一子集出现冲突模板/图幅时必须行级拒绝；Task 2 覆盖。
- 不编号子集不能消耗连续流水号，后续 DWG 范围仍正确；Task 3 覆盖。
- 预览后标准、草稿、目标目录或模板资产变化必须使执行拒绝；Task 4/5 覆盖。
- 新目录发布中途故障必须删除已创建目标并恢复为空前状态；Task 5 的故障注入覆盖。
- CAD 成功但 DST 引用、Handle 或布局集合验证失败时不得发布；Task 5/6 覆盖。

---

### Task 1: 建立可恢复创建草稿

**Files:**
- Create: `src/dst_manager/domain/creation.py`
- Create: `src/dst_manager/infrastructure/creation_drafts.py`
- Create: `src/dst_manager/application/creation_drafts.py`
- Create: `tests/unit/test_creation_drafts.py`
- Modify: `src/dst_manager/application/service.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: PLAN-DM-035 的 `StandardStore`；PLAN-DM-038 的 `DrawingStandard`（Schema v1）、
  `compile_standard_properties`/`evaluate_standard_properties`（派生属性求值）与
  `render_dwg_filename`/`validate_dwg_filenames`（全局 DWG 命名与碰撞预检）。
- Produces: `CreationDraft`、`CreationSubsetInput`、`CreationSheetInput`；`CreationDraftOperations.create/get/save/delete`。

- [ ] **Step 1: 写入标准固定与崩溃恢复测试**

```python
def test_creation_draft_pins_published_standard(tmp_path, service, published_standard) -> None:
    draft = service.create_creation_draft(published_standard.identity)
    restored = service.get_creation_draft(draft.id)
    assert restored.standard == published_standard.identity
    assert restored.revision == 1


def test_save_uses_optimistic_revision(service, draft) -> None:
    service.save_creation_draft(draft.id, expected_revision=1, value=draft.value)
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_CONFLICT"):
        service.save_creation_draft(draft.id, expected_revision=1, value=draft.value)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_creation_drafts.py -q`

Expected: FAIL，创建草稿模块不存在。

- [ ] **Step 3: 实现原子 JSON 草稿存储**

草稿根使用 Manager 应用数据目录的 `creation-drafts/<uuid>/`；保存采用临时文件加 `os.replace`，记录 `schema_version`、标准身份、修订号和用户输入，不保存可执行预览。

- [ ] **Step 4: 覆盖损坏隔离与标准缺失**

Run: `uv run pytest tests/unit/test_creation_drafts.py -q`

Expected: 损坏 JSON 隔离并返回 `CREATION_DRAFT_CORRUPT`；标准版本缺失返回 `CREATION_STANDARD_MISSING`。

- [ ] **Step 5: 提交创建草稿**

```powershell
git add src/dst_manager/domain/creation.py src/dst_manager/infrastructure/creation_drafts.py src/dst_manager/application/creation_drafts.py src/dst_manager/application/service.py tests/unit/test_creation_drafts.py changelog.md
git commit -m "建立可恢复图纸集创建草稿"
```

### Task 2: 实现标准生成的 XLSX 结构导入

**Files:**
- Create: `src/dst_manager/infrastructure/creation_xlsx.py`
- Create: `src/dst_manager/application/creation_import.py`
- Create: `tests/unit/test_creation_xlsx.py`
- Modify: `src/dst_manager/domain/creation.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `DrawingStandard` 和 `CreationDraft`。
- Produces: `build_creation_template(standard) -> bytes`、`parse_creation_workbook(data, standard) -> CreationImportResult`。

- [ ] **Step 1: 写入动态列和冲突输入测试**

```python
def test_template_contains_only_editable_standard_fields(standard) -> None:
    workbook = load_workbook(BytesIO(build_creation_template(standard)))
    assert list(workbook.active.values)[0] == (
        "子集", "图纸名称", "图幅", "基础模板", "布局模板", "比例"
    )


def test_import_rejects_mixed_subset_template_selection(standard) -> None:
    result = parse_creation_workbook(workbook_with_same_subset_two_paper_sizes(), standard)
    assert [item.code for item in result.diagnostics] == ["CREATION_SUBSET_TEMPLATE_CONFLICT"]
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_creation_xlsx.py -q`

Expected: FAIL，XLSX 模块不存在。

- [ ] **Step 3: 实现模板生成和严格解析**

模板按标准可输入字段生成，枚举写入隐藏数据表和 Data Validation；模板资产写稳定 ID。解析拒绝公式、重复表头、未知列、任意路径、派生字段输入和同一子集配置冲突，并返回行号诊断。

- [ ] **Step 4: 运行 XLSX 安全与往返测试**

Run: `uv run pytest tests/unit/test_creation_xlsx.py -q`

Expected: 合法工作簿往返；公式单元格、非法枚举和超限行数均稳定拒绝。

- [ ] **Step 5: 提交结构导入**

```powershell
git add src/dst_manager/infrastructure/creation_xlsx.py src/dst_manager/application/creation_import.py src/dst_manager/domain/creation.py tests/unit/test_creation_xlsx.py changelog.md
git commit -m "实现标准化 XLSX 结构导入"
```

### Task 3: 生成确定性 CreationPlan

**Files:**
- Create: `src/dst_manager/domain/creation_planning.py`
- Create: `tests/unit/test_creation_planning.py`
- Modify: `src/dst_manager/domain/editing.py`
- Modify: `src/dst_manager/domain/planning.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `CreationDraft`、`CompiledStandard`、现有 `SuffixOptions` 与命名派生函数。
- Produces: `create_creation_plan(draft, standard, suffix_options) -> CreationPlan`；计划含最终 DST/DWG/布局、模板来源、诊断和 `preview_digest`。

- [ ] **Step 1: 写入连续编号与后缀复用测试**

```python
def test_plan_reuses_manager_numbering_and_suffix_style() -> None:
    plan = create_creation_plan(draft_with_unnumbered_cover(), standard(), suffix_options(type=2))
    assert [sheet.number for sheet in plan.numbered_sheets] == ["01", "02", "03"]
    assert plan.subsets[1].dwg_name == "RQ01 平面图01-03.dwg"
    assert plan.subsets[1].sheets[1].title.endswith("（二）")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_creation_planning.py -q`

Expected: FAIL，CreationPlan 尚不存在。

- [ ] **Step 3: 抽取可复用编号原语并实现计划器**

不得复制既有编号算法；把 `derive_document_structure` 中与已有 DOM 无关的纯派生抽成同层函数，由编辑和创建共同调用。计划摘要覆盖标准身份、草稿修订、有效项目配置、模板资产身份和全部派生输出。

- [ ] **Step 4: 覆盖命名碰撞、空子集和路径边界**

Run: `uv run pytest tests/unit/test_creation_planning.py tests/unit/test_unnumbered_subsets.py tests/unit/test_v021_editing.py -q`

Expected: 全部通过；现有编辑结果逐字保持。

- [ ] **Step 5: 提交创建计划器**

```powershell
git add src/dst_manager/domain tests/unit/test_creation_planning.py tests/unit/test_unnumbered_subsets.py tests/unit/test_v021_editing.py changelog.md
git commit -m "统一新建与编辑编号派生"
```

### Task 4: 暴露创建预览与执行 API

**Files:**
- Create: `src/dst_manager/application/creation.py`
- Create: `src/dst_manager/interfaces/creation_contracts.py`
- Create: `src/dst_manager/interfaces/creation_api.py`
- Create: `tests/integration/test_creation_api.py`
- Modify: `src/dst_manager/interfaces/api.py`
- Modify: `src/dst_manager/interfaces/responses.py`
- Modify: `web/src/api/openapi.json`
- Modify: `web/src/api/schema.d.ts`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `CreationDraftOperations`、`create_creation_plan()`。
- Produces: `/api/creation-drafts` CRUD、XLSX template/import、`/preview` 与 `/execute`；`CreationOperations.preview/execute`。

- [ ] **Step 1: 写入预览失效和空目录 API 测试**

```python
def test_execute_rejects_stale_preview(client, creation_draft, preview) -> None:
    update_creation_draft(client, creation_draft.id)
    response = client.post(f"/api/creation-drafts/{creation_draft.id}/execute", json={"preview_digest": preview.digest})
    assert response.status_code == 409
    assert response.json()["code"] == "CREATION_PREVIEW_STALE"
```

- [ ] **Step 2: 运行 API 测试并确认失败**

Run: `uv run pytest tests/integration/test_creation_api.py -q`

Expected: FAIL，路由不存在。

- [ ] **Step 3: 实现独立创建路由和应用编排**

接口层不解析 XLSX、不执行命名或文件操作。执行前重新加载标准、草稿与目标状态并重算摘要；非空目标返回 `CREATION_TARGET_NOT_EMPTY`。

- [ ] **Step 4: 生成 OpenAPI 并运行契约测试**

Run: `uv run python scripts/export_openapi.py; uv run pytest tests/integration/test_creation_api.py -q; Set-Location web; npm run check:api; Set-Location ..`

Expected: 全部通过。

- [ ] **Step 5: 提交创建 API**

```powershell
git add src/dst_manager/application/creation.py src/dst_manager/interfaces web/src/api tests/integration/test_creation_api.py changelog.md
git commit -m "开放图纸集创建预览与执行 API"
```

### Task 5: 实现隔离生成与新目录原子发布

**Files:**
- Create: `src/dst_manager/application/creation_job.py`
- Create: `src/dst_manager/infrastructure/acsm_xml/creation.py`
- Create: `src/dst_manager/infrastructure/filesystem/project_publisher.py`
- Create: `tests/unit/test_project_publisher.py`
- Create: `tests/integration/test_creation_job.py`
- Modify: `src/dst_manager/infrastructure/autocad/worker.py`
- Modify: `src/dst_manager/infrastructure/filesystem/publish_recovery.py`
- Modify: `src/dst_manager/infrastructure/persistence/database.py`
- Create: `migrations/versions/0009_creation_jobs.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `CreationPlan` 与现有 Worker 能力。
- Produces: `CreationJobRunner.run(job_id, plan)`；`ProjectPublisher.publish_new_project(candidate, target, ...)`。

- [ ] **Step 1: 写入中途故障和恢复测试**

```python
def test_new_project_publish_failure_leaves_empty_target(tmp_path, fault_injector) -> None:
    target = tmp_path / "new-project"
    target.mkdir()
    fault_injector.fail_after_replace(1)
    with pytest.raises(ProjectPublishError):
        publish_candidate(target)
    assert list(target.iterdir()) == []
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_project_publisher.py tests/integration/test_creation_job.py -q`

Expected: FAIL，新项目发布器和任务不存在。

- [ ] **Step 3: 实现 attempt 目录、CAD 请求与 DST 构造**

每个子集从标准基础 DWG 复制基底，Worker 从所选布局模板精确导入图幅布局并复制为计划布局。CAD 结果返回布局名与 Handle；AcSm 创建器从标准最小骨架写入属性、子集、图纸、引用及保留标准属性。

- [ ] **Step 4: 实现新目录发布事务与启动恢复**

发布日志必须区分“目标原本不存在”和“目标原本为空”。失败或启动恢复后恢复对应状态；禁止把已有非空目录纳入发布。

- [ ] **Step 5: 添加全新数据库升级测试并运行**

Run: `uv run alembic upgrade head; uv run pytest tests/unit/test_project_publisher.py tests/integration/test_creation_job.py tests/unit/test_database.py -q`

Expected: 迁移到 `0009_creation_jobs`；故障注入、恢复和任务状态测试全过。

- [ ] **Step 6: 提交生成任务与发布事务**

```powershell
git add src/dst_manager/application/creation_job.py src/dst_manager/infrastructure migrations tests/unit/test_project_publisher.py tests/integration/test_creation_job.py tests/unit/test_database.py changelog.md
git commit -m "实现新图纸集隔离生成与原子发布"
```

### Task 6: 建立初始修订并验证生成成果可打开

**Files:**
- Create: `tests/integration/test_created_project_opens.py`
- Create: `tests/system_autocad/test_creation_workflow.py`
- Modify: `src/dst_manager/application/creation_job.py`
- Modify: `src/dst_manager/infrastructure/filesystem/workspace.py`
- Modify: `src/dst_manager/application/revisions.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `CreationJobRunner`、`open_workspace()`。
- Produces: 创建成功响应中的 `workspace_id/revision_id/dst_path`，以及项目标准快照和初始修订。

- [ ] **Step 1: 写入生成后打开与绑定断言**

```python
def test_created_project_opens_as_normal_workspace(service, completed_creation) -> None:
    workspace = service.get_workspace(completed_creation.workspace_id)
    assert workspace.document.custom_properties["DSTManager.Standard"] == "szmedi.gas@2.1.0"
    assert workspace.revision_id == completed_creation.revision_id
    assert (workspace.root / ".dst-manager/standards/szmedi.gas/2.1.0").is_dir()
```

- [ ] **Step 2: 运行集成测试并确认初始修订缺失**

Run: `uv run pytest tests/integration/test_created_project_opens.py -q`

Expected: FAIL，创建成功尚未登记普通工作区和初始修订。

- [ ] **Step 3: 在发布成功回调中登记工作区与初始修订**

只在项目发布完全提交后执行；登记失败必须进入可恢复状态，不能把“文件已发布、数据库未登记”显示为普通成功。

- [ ] **Step 4: 运行集成与可选真实 CAD 系统测试**

Run: `uv run pytest tests/integration/test_created_project_opens.py -q`

具备环境时 Run: `$env:DST_MANAGER_RUN_AUTOCAD="1"; uv run pytest tests/system_autocad/test_creation_workflow.py -q`

Expected: 集成测试通过；真实 2016/2020 测试验证布局、Handle、DST 引用和官方 Sheet Set Manager 可打开性。缺少环境时记录跳过原因。

- [ ] **Step 5: 提交创建闭环**

```powershell
git add src/dst_manager/application/creation_job.py src/dst_manager/infrastructure/filesystem/workspace.py src/dst_manager/application/revisions.py tests/integration/test_created_project_opens.py tests/system_autocad/test_creation_workflow.py changelog.md
git commit -m "完成新图纸集创建与工作区接管"
```

### Task 7: 实现六步创建 UI 并完成全量验证

**Files:**
- Create: `web/src/views/CreateSheetSetView.vue`
- Create: `web/src/features/creation/store.ts`
- Create: `web/src/features/creation/types.ts`
- Create: `web/src/components/creation/StandardStep.vue`
- Create: `web/src/components/creation/ProjectStep.vue`
- Create: `web/src/components/creation/StructureStep.vue`
- Create: `web/src/components/creation/TemplatesStep.vue`
- Create: `web/src/components/creation/PreviewStep.vue`
- Create: `web/src/components/creation/ExecuteStep.vue`
- Create: `web/src/api/creation.ts`
- Create: `web/src/features/creation/store.test.ts`
- Create: `web/tests/e2e/create-sheetset.spec.ts`
- Create: `web/src/i18n/locales/zh-CN/creation.ts`
- Create: `web/src/i18n/locales/en-US/creation.ts`
- Modify: `web/src/i18n/index.ts`
- Modify: `web/src/views/WelcomeView.vue`
- Modify: `web/src/App.vue`
- Modify: `docs/dst-manager/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Tasks 4–6 的创建 API 与任务状态。
- Produces: 欢迎页“创建图纸集”入口、六步可恢复向导、XLSX 导入、完整预览和成功后工作区切换。

- [ ] **Step 1: 写入 store 与 E2E 失败用例**

```ts
it("invalidates preview when the draft changes", async () => {
  const store = createCreationStore(fakeCreationApi());
  await store.preview();
  store.updateProjectField("项目名称", "新名称");
  expect(store.previewDigest).toBeNull();
  expect(store.canExecute).toBe(false);
});
```

- [ ] **Step 2: 运行目标前端测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/creation/store.test.ts; npm run test:e2e -- create-sheetset.spec.ts; Set-Location ..`

Expected: FAIL，创建 UI 不存在。

- [ ] **Step 3: 实现向导、行级诊断和任务衔接**

步骤门禁由后端草稿/预览状态驱动；字段组合派生只读实时展示；XLSX 行级错误可聚焦；执行阶段复用全局任务浮层，成功后切换普通工作区。

- [ ] **Step 4: 运行前端完整门禁**

Run: `Set-Location web; npm run test:unit; npm run build; npm run test:e2e -- create-sheetset.spec.ts; Set-Location ..`

Expected: 全部通过，覆盖浅深主题、900×768、键盘操作、恢复草稿、目标冲突和失败重试。

- [ ] **Step 5: 执行全量验证并记录实际结果**

Run: `uv run ruff check .; uv run pytest -q; uv lock --check; uv run alembic upgrade head; Set-Location web; npm run build; npm run test:e2e; Set-Location ..; powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1`

Expected: 全部通过；真实 AutoCAD 测试按环境显式启用并如实记录。

- [ ] **Step 6: 更新计划验证摘要并提交**

```powershell
git add src web tests migrations docs/dst-manager/README.md changelog.md .planning/plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md
git commit -m "交付标准驱动的新图纸集创建"
```
