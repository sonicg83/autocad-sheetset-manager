---
id: PLAN-DM-037
title: 图纸标准校验与 HTML JSON 报告实施计划
status: proposed
owners:
- dst-manager
created: 2026-09-21
updated: 2026-09-21
related:
- RFC-INT-003
- PLAN-DM-035
- PLAN-DM-036
- ARCH-DM-006
---

# 图纸标准校验与 HTML JSON 报告实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用项目绑定标准检查当前 DST/DWG，并从同一结果模型生成可审阅 HTML 与可机器读取 JSON 报告。

**Architecture:** 宿主完整性检查和标准规则检查汇入不可变 `ValidationReport`；校验固定工作区修订和标准版本，长过程结束时重新核对漂移；HTML/JSON 渲染器只消费同一模型并在候选目录回读验证。首版报告是 Artifact，不复制工程文件，也不创建归档包。

**Tech Stack:** Python 3.12、lxml、Jinja2、FastAPI、Vue 3、TypeScript、Playwright、pytest。

**Spec:** [`docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md`](../../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)

## Global Constraints

- 必须先完成 PLAN-DM-035 与 PLAN-DM-036；后者产出的项目作为主要集成样本。
- 标准身份按 ID + 版本解析，不实施内容摘要匹配。
- 创建期“同一子集统一图幅和模板”不得进入归档校验。
- 报告生成成功不等于项目符合标准；存在错误时仍应生成完整报告。
- HTML 与 JSON 必须来自同一个冻结结果对象，不得分别重新校验。
- 首版不收集、复制或压缩工程文件，不生成归档移交包。

## Review Focus

- 标准缺失、依赖插件缺失和 CAD 能力缺失必须区分“无法检查”与“不符合”；Task 1/2 覆盖。
- 校验期间 DST/DWG 漂移必须使候选报告作废；Task 3 覆盖。
- 用户属性含 HTML、公式前缀或超长文本时不得造成注入或损坏 JSON；Task 3 覆盖。
- HTML 与 JSON 的规则数量、状态和对象定位必须完全一致；Task 3 的往返测试覆盖。
- 报告生成失败不得登记成功 Artifact 或修改工作区修订；Task 4 覆盖。

---

### Task 1: 定义统一验证结果模型与整体裁决

**Files:**
- Create: `src/dst_manager/domain/standard_validation.py`
- Create: `tests/unit/test_standard_validation_model.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: PLAN-DM-035 的标准领域类型。
- Produces: `ValidationStatus`、`ValidationFinding`、`ValidationReport`、`summarize_validation(findings) -> ValidationStatus`。

- [ ] **Step 1: 写入状态汇总测试**

```python
@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["passed"], "compliant"),
        (["passed", "warning"], "compliant_with_warnings"),
        (["error", "warning"], "noncompliant"),
        (["unavailable"], "unable_to_validate"),
    ],
)
def test_summary_statuses(statuses, expected) -> None:
    assert summarize_validation(findings(statuses)).value == expected
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_validation_model.py -q`

Expected: FAIL，结果模型不存在。

- [ ] **Step 3: 实现冻结、可序列化的结果模型**

每条 Finding 包含稳定规则 ID、类别、状态、对象类型/ID、期望值、实际值、说明和修复建议；模型不得包含 `Path`、异常对象或不可 JSON 化值。

- [ ] **Step 4: 运行结果模型测试**

Run: `uv run pytest tests/unit/test_standard_validation_model.py -q`

Expected: 全部通过。

- [ ] **Step 5: 提交结果模型**

```powershell
git add src/dst_manager/domain/standard_validation.py tests/unit/test_standard_validation_model.py changelog.md
git commit -m "建立统一标准验证结果模型"
```

### Task 2: 实现宿主完整性与标准规则检查器

**Files:**
- Create: `src/dst_manager/application/standard_validation.py`
- Create: `src/dst_manager/domain/standard_checks.py`
- Create: `tests/unit/test_standard_checks.py`
- Create: `tests/integration/test_standard_validation.py`
- Modify: `src/dst_manager/application/service.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `Workspace`、`CompiledStandard`、现有 AcSm/布局诊断与 `evaluate_fields()`。
- Produces: `StandardValidationOperations.validate_workspace(workspace_id) -> ValidationReport`。

- [ ] **Step 1: 写入枚举、映射、组合与创建期约束排除测试**

```python
def test_validation_ignores_mixed_paper_sizes_inside_subset(bound_workspace) -> None:
    report = validate(bound_workspace.with_paper_sizes("A2", "A3"))
    assert "creation.subset.uniform-paper-size" not in {item.rule_id for item in report.findings}


def test_mapping_mismatch_is_noncompliant(bound_workspace) -> None:
    report = validate(bound_workspace.with_properties({"专业名称": "燃气", "专业代码": "DL"}))
    finding = next(item for item in report.findings if item.rule_id == "property.profession-code")
    assert finding.status == "error"
    assert finding.expected == "RQ"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_checks.py tests/integration/test_standard_validation.py -q`

Expected: FAIL，检查器不存在。

- [ ] **Step 3: 实现两阶段检查编排**

先运行 DST/DWG/布局/Handle/路径宿主检查，再运行标准属性、枚举、映射、组合、编号和命名检查。标准或依赖缺失产生 `unavailable`，实际值违反已执行规则产生 `error`。

- [ ] **Step 4: 添加现有工作区与创建项目集成样本**

Run: `uv run pytest tests/unit/test_standard_checks.py tests/integration/test_standard_validation.py tests/integration/test_created_project_opens.py -q`

Expected: 新建项目初始报告为 compliant；人为改坏专业代码、DWG 名称和布局引用分别命中稳定规则 ID。

- [ ] **Step 5: 提交检查器**

```powershell
git add src/dst_manager/application/standard_validation.py src/dst_manager/domain/standard_checks.py src/dst_manager/application/service.py tests/unit/test_standard_checks.py tests/integration/test_standard_validation.py changelog.md
git commit -m "实现宿主与标准统一校验"
```

### Task 3: 从同一模型生成并回读 HTML JSON

**Files:**
- Create: `src/dst_manager/infrastructure/reports/__init__.py`
- Create: `src/dst_manager/infrastructure/reports/standard_json.py`
- Create: `src/dst_manager/infrastructure/reports/standard_html.py`
- Create: `src/dst_manager/infrastructure/reports/templates/standard-report.html`
- Create: `tests/unit/test_standard_reports.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `ValidationReport`。
- Produces: `render_validation_json(report) -> bytes`、`render_validation_html(report) -> bytes`、`verify_rendered_report(html, json) -> None`。

- [ ] **Step 1: 写入同源一致性与注入测试**

```python
def test_html_and_json_have_identical_finding_identity(report_with_html_text) -> None:
    html = render_validation_html(report_with_html_text)
    payload = json.loads(render_validation_json(report_with_html_text))
    parsed = parse_report_html(html)
    assert parsed.finding_ids == [item["id"] for item in payload["findings"]]
    assert b"<script>alert(1)</script>" not in html
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in html
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_reports.py -q`

Expected: FAIL，渲染器不存在。

- [ ] **Step 3: 实现确定性 JSON 与自动转义 HTML**

先使用 `uv add "jinja2>=3.1,<4"` 增加显式运行依赖。JSON 使用稳定 Schema 版本、UTF-8 与确定性键顺序；Jinja2 环境必须启用自动转义，不执行用户内容。

- [ ] **Step 4: 实现回读验证与漂移输入保护测试**

Run: `uv run pytest tests/unit/test_standard_reports.py -q; uv lock --check`

Expected: JSON 可解析、HTML 含全部 finding ID、状态汇总一致；超长值安全截断仅发生在展示层，JSON 保留完整值。

- [ ] **Step 5: 提交报告渲染器**

```powershell
git add src/dst_manager/infrastructure/reports tests/unit/test_standard_reports.py pyproject.toml uv.lock changelog.md
git commit -m "生成同源标准校验报告"
```

### Task 4: 编排报告任务、Artifact 与 API

**Files:**
- Create: `src/dst_manager/application/standard_report.py`
- Create: `src/dst_manager/interfaces/standard_report_contracts.py`
- Create: `src/dst_manager/interfaces/standard_report_api.py`
- Create: `tests/integration/test_standard_report_api.py`
- Modify: `src/dst_manager/interfaces/api.py`
- Modify: `src/dst_manager/extensions/artifacts.py`
- Modify: `src/dst_manager/infrastructure/persistence/database.py`
- Create: `migrations/versions/0010_standard_report_artifacts.py`
- Modify: `web/src/api/openapi.json`
- Modify: `web/src/api/schema.d.ts`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `validate_workspace()` 与两个渲染器。
- Produces: `POST /api/workspaces/{id}/standard-reports`、任务状态、成对 HTML/JSON Artifact。

- [ ] **Step 1: 写入漂移与失败不登记测试**

```python
def test_report_drift_discards_candidates(client, workspace, mutate_dst_during_render) -> None:
    response = client.post(f"/api/workspaces/{workspace.id}/standard-reports")
    job = wait_for_job(response.json()["job_id"])
    assert job["status"] == "FAILED"
    assert job["error_code"] == "STANDARD_REPORT_SOURCE_CHANGED"
    assert list_artifacts(workspace.id, kind="standard-report") == []
```

- [ ] **Step 2: 运行 API 测试并确认失败**

Run: `uv run pytest tests/integration/test_standard_report_api.py -q`

Expected: FAIL，报告端点不存在。

- [ ] **Step 3: 实现冻结输入、候选目录和成对 Artifact 提交**

任务开始记录工作区修订、标准 ID/版本和正式文件身份；渲染后再次比较。HTML/JSON 任一回读失败则两者都不登记。报告只读工程，不创建工程修订。

- [ ] **Step 4: 生成 OpenAPI、升级全新数据库并运行测试**

Run: `uv run alembic upgrade head; uv run python scripts/export_openapi.py; uv run pytest tests/integration/test_standard_report_api.py tests/unit/test_database.py -q; Set-Location web; npm run check:api; Set-Location ..`

Expected: 迁移到 `0010_standard_report_artifacts`；API 和数据库测试全过。

- [ ] **Step 5: 提交报告任务与 API**

```powershell
git add src/dst_manager/application/standard_report.py src/dst_manager/interfaces src/dst_manager/extensions/artifacts.py src/dst_manager/infrastructure/persistence/database.py migrations web/src/api tests/integration/test_standard_report_api.py tests/unit/test_database.py changelog.md
git commit -m "编排标准校验报告任务"
```

### Task 5: 实现校验报告 UI 并完成全量验证

**Files:**
- Create: `web/src/views/StandardValidationView.vue`
- Create: `web/src/features/validation/store.ts`
- Create: `web/src/features/validation/types.ts`
- Create: `web/src/components/validation/ValidationSummary.vue`
- Create: `web/src/components/validation/ValidationFindings.vue`
- Create: `web/src/api/standardReports.ts`
- Create: `web/src/features/validation/store.test.ts`
- Create: `web/tests/e2e/standard-validation.spec.ts`
- Create: `web/src/i18n/locales/zh-CN/validation.ts`
- Create: `web/src/i18n/locales/en-US/validation.ts`
- Modify: `web/src/i18n/index.ts`
- Modify: `web/src/features/extensions/pageRegistry.ts`
- Modify: `docs/dst-manager/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 4 的报告 API、任务与 Artifact。
- Produces: 工作区“标准校验”页面、状态汇总、对象级定位、HTML/JSON 保存入口。

- [ ] **Step 1: 写入状态展示和缺失标准用例**

```ts
it("does not present an unavailable report as noncompliant", async () => {
  const store = createValidationStore(fakeReport({status: "unable_to_validate"}));
  await store.load();
  expect(store.summaryTone).toBe("neutral");
  expect(store.canDownload).toBe(true);
});
```

- [ ] **Step 2: 运行前端目标测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/validation/store.test.ts; npm run test:e2e -- standard-validation.spec.ts; Set-Location ..`

Expected: FAIL，校验页面不存在。

- [ ] **Step 3: 实现页面、筛选、对象定位和下载**

页面明确区分四种整体结果；规则列表支持状态和对象类型筛选；失败项显示实际/期望/修复建议；HTML 与 JSON 分别通过宿主保存授权导出。

- [ ] **Step 4: 运行前端门禁与目标 E2E**

Run: `Set-Location web; npm run test:unit; npm run build; npm run test:e2e -- standard-validation.spec.ts; Set-Location ..`

Expected: 全部通过，覆盖无标准、标准缺失、符合、警告、不符合、漂移失败和报告保存。

- [ ] **Step 5: 执行全量验证并记录实际结果**

Run: `uv run ruff check .; uv run pytest -q; uv lock --check; uv run alembic upgrade head; Set-Location web; npm run build; npm run test:e2e; Set-Location ..`

Expected: 全部通过；报告生成不改变 DST/DWG 哈希和工作区修订。

- [ ] **Step 6: 更新计划验证摘要并提交**

```powershell
git add src web tests migrations docs/dst-manager/README.md changelog.md .planning/plans/dst-manager/PLAN-DM-037-standard-validation-reports.md
git commit -m "交付图纸标准校验报告"
```
