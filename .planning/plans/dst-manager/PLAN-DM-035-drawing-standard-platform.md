---
id: PLAN-DM-035
title: 图纸标准平台与标准编辑器实施计划
status: proposed
owners:
- dst-manager
created: 2026-09-21
updated: 2026-09-21
related:
- RFC-INT-003
- ARCH-DM-001
- ARCH-DM-004
- ARCH-DM-006
---

# 图纸标准平台与标准编辑器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 DST Manager 中建立纯数据、版本不可变、普通用户可维护的图纸标准库与标准编辑器。

**Architecture:** 领域层定义标准 Schema 和封闭规则求值器；基础设施层负责官方/用户/项目三层存储与 `.dststandard` 导入导出；应用层编排草稿、校验和发布；接口与 Vue 页面只承载契约和交互。标准不含可执行代码，正式工程写入仍完全属于宿主。

**Tech Stack:** Python 3.12、dataclasses/Pydantic、FastAPI、lxml、openpyxl、Vue 3、TypeScript、Vite、Vitest、Playwright、pytest。

**Spec:** [`docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md`](../../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)

## Global Constraints

- 本计划在 PLAN-INT-004 完成后实施，不导入或复制 `dst_builder` 代码。
- 标准身份仅为 `standard_id + version`；不实现内容指纹绑定。
- 已发布版本不可原地修改；任何内容变化必须产生新版本。
- 标准包不得包含 Python、DLL、SCR、Shell、AutoLISP 或其他可执行内容。
- 首版规则只含必填、枚举、固定值、一对一映射、字段组合、编号与受控命名；不含日期格式化或通用公式。
- 子集属性只预留 Schema，不进入首版编辑表单和强制校验。
- 单个新增源文件保持在约 500 行以内；标准服务不得继续膨胀 `application/service.py`。

## Review Focus

- 同一标准 ID/版本的重复发布、导入碰撞和大小写差异必须稳定拒绝；Task 3 的仓储测试覆盖。
- 字段组合对未知引用、循环引用、缺失可选值和格式码错误必须确定性失败；Task 2 的领域测试覆盖。
- `.dststandard` 中的绝对路径、`..`、重复规范化路径和可执行扩展名必须拒绝；Task 3 的包安全测试覆盖。
- 布局模板声明的图幅与实际布局不一致时不能发布；Task 5 的资产检查测试覆盖。
- 项目快照缺失时按 ID/版本恢复，找不到时只降级标准能力而不阻止普通工作区打开；Task 4 的应用测试覆盖。

---

### Task 1: 定义标准领域模型与 Schema

**Files:**
- Create: `src/dst_manager/domain/standards.py`
- Create: `tests/unit/test_drawing_standards.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: 无。
- Produces: `DrawingStandard`, `StandardProperty`, `StandardAsset`, `NumberingPolicy`, `StandardDependency` 与 `parse_standard_document(data: Mapping[str, object]) -> DrawingStandard`。

- [ ] **Step 1: 写入最小标准解析失败测试**

```python
def test_parse_standard_requires_stable_identity() -> None:
    with pytest.raises(StandardSchemaError, match="STANDARD_ID_INVALID"):
        parse_standard_document({"schema_version": 1, "standard_id": "", "version": "1.0.0"})
```

- [ ] **Step 2: 运行测试并确认导入失败**

Run: `uv run pytest tests/unit/test_drawing_standards.py::test_parse_standard_requires_stable_identity -q`

Expected: FAIL，原因是 `dst_manager.domain.standards` 不存在。

- [ ] **Step 3: 实现冻结领域对象与严格解析器**

```python
@dataclass(frozen=True)
class DrawingStandard:
    schema_version: int
    standard_id: str
    version: str
    name: str
    supported_cad_versions: tuple[str, ...]
    properties: tuple[StandardProperty, ...]
    rules: tuple[StandardRule, ...]
    assets: tuple[StandardAsset, ...]
    numbering: NumberingPolicy
    dependencies: tuple[StandardDependency, ...] = ()
```

解析器必须拒绝未知 Schema 版本、重复字段、非法 ID/版本、未知作用域和重复资产 ID。

- [ ] **Step 4: 添加标准往返与边界测试并运行**

Run: `uv run pytest tests/unit/test_drawing_standards.py -q`

Expected: 合法标准往返稳定；全部非法输入返回稳定错误码。

- [ ] **Step 5: 提交领域 Schema**

```powershell
git add src/dst_manager/domain/standards.py tests/unit/test_drawing_standards.py changelog.md
git commit -m "建立图纸标准领域模型"
```

### Task 2: 实现封闭规则求值与字段组合

**Files:**
- Create: `src/dst_manager/domain/standard_rules.py`
- Create: `tests/unit/test_standard_rules.py`
- Modify: `src/dst_manager/domain/standards.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1 的 `StandardProperty` 与 `StandardRule`。
- Produces: `compile_standard_rules(standard) -> CompiledStandard`、`evaluate_fields(compiled, values, context) -> EvaluationResult`。

- [ ] **Step 1: 写入映射、组合与循环检测测试**

```python
def test_mapping_then_compose_uses_derived_value() -> None:
    compiled = compile_standard_rules(standard_with_gas_mapping())
    result = evaluate_fields(compiled, {"sheetset.专业名称": "燃气"}, {"subset.sequence": 3})
    assert result.values["sheetset.专业代码"] == "RQ"
    assert result.values["derived.dwg_name"] == "RQ03 平面图01-05"


def test_compile_rejects_indirect_cycle() -> None:
    with pytest.raises(StandardRuleError, match="STANDARD_RULE_CYCLE"):
        compile_standard_rules(standard_with_cycle("a", "b", "a"))
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_rules.py -q`

Expected: FAIL，规则编译与求值函数尚不存在。

- [ ] **Step 3: 实现结构化片段和拓扑求值**

```python
@dataclass(frozen=True)
class FieldSegment:
    field: str | None = None
    literal: str | None = None
    format: str | None = None


def evaluate_compose(segments: tuple[FieldSegment, ...], values: Mapping[str, str]) -> str:
    return "".join(_render_segment(segment, values) for segment in segments)
```

只允许宿主登记的数字补零格式；缺失必需来源、未知字段和循环均返回稳定诊断，不执行 `eval`、模板脚本或动态导入。

- [ ] **Step 4: 运行领域测试与 Ruff**

Run: `uv run pytest tests/unit/test_drawing_standards.py tests/unit/test_standard_rules.py -q; uv run ruff check src/dst_manager/domain/standards.py src/dst_manager/domain/standard_rules.py tests/unit/test_drawing_standards.py tests/unit/test_standard_rules.py`

Expected: 全部通过。

- [ ] **Step 5: 提交规则引擎**

```powershell
git add src/dst_manager/domain tests/unit/test_standard_rules.py tests/unit/test_drawing_standards.py changelog.md
git commit -m "实现图纸标准封闭规则求值"
```

### Task 3: 建立标准包与官方/用户标准库

**Files:**
- Create: `src/dst_manager/infrastructure/standards/__init__.py`
- Create: `src/dst_manager/infrastructure/standards/package.py`
- Create: `src/dst_manager/infrastructure/standards/store.py`
- Create: `tests/unit/test_standard_package.py`
- Create: `tests/unit/test_standard_store.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `parse_standard_document()`。
- Produces: `StandardPackageReader.read(path) -> LoadedStandardPackage`、`StandardStore.list/get/create_draft/publish/import_package/export_package`。

- [ ] **Step 1: 写入路径逃逸和版本不可变测试**

```python
def test_package_rejects_parent_path(tmp_path: Path) -> None:
    package = write_zip(tmp_path, {"manifest.json": VALID_MANIFEST, "../escape.dwg": b"x"})
    with pytest.raises(StandardPackageError, match="STANDARD_PACKAGE_PATH_INVALID"):
        StandardPackageReader().read(package)


def test_publish_rejects_existing_identity(store: StandardStore) -> None:
    store.publish("draft-1")
    with pytest.raises(StandardStoreError, match="STANDARD_VERSION_EXISTS"):
        store.publish("draft-2")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_package.py tests/unit/test_standard_store.py -q`

Expected: FAIL，标准包与仓储模块不存在。

- [ ] **Step 3: 实现安全包读取与原子标准库**

发布目录使用 `<standard_id>/<version>/`；官方根只读，用户草稿与发布根分离。导入先解压到临时目录，验证全部路径、扩展名、大小和 Schema 后使用同目录原子替换，不覆盖既有身份。

- [ ] **Step 4: 添加重启往返、重复路径和非法扩展测试并运行**

Run: `uv run pytest tests/unit/test_standard_package.py tests/unit/test_standard_store.py -q`

Expected: 全部通过；`.py`、`.dll`、`.scr`、`.lsp`、`.exe` 与重复规范化路径均拒绝。

- [ ] **Step 5: 提交标准存储**

```powershell
git add src/dst_manager/infrastructure/standards tests/unit/test_standard_package.py tests/unit/test_standard_store.py changelog.md
git commit -m "建立图纸标准包与标准库"
```

### Task 4: 编排标准草稿、发布和项目快照恢复

**Files:**
- Create: `src/dst_manager/application/standards.py`
- Create: `tests/unit/test_standard_service.py`
- Modify: `src/dst_manager/application/service.py`
- Modify: `src/dst_manager/domain/models.py`
- Modify: `src/dst_manager/infrastructure/acsm_xml/document.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `StandardStore`、`CompiledStandard` 与现有 `Workspace`。
- Produces: `StandardOperations` mixin；`resolve_workspace_standard(workspace) -> StandardResolution`；保留属性 `DSTManager.Standard` 与 `DSTManager.StandardOptions`。

- [ ] **Step 1: 写入缺失快照恢复和降级测试**

```python
def test_resolve_restores_project_snapshot_from_user_library(service, workspace, standard_store) -> None:
    bind_standard(workspace, "szmedi.gas@2.1.0")
    resolution = service.resolve_workspace_standard(workspace.id)
    assert resolution.status == "resolved"
    assert (workspace.root / ".dst-manager/standards/szmedi.gas/2.1.0").is_dir()


def test_missing_standard_does_not_block_workspace_open(service, workspace) -> None:
    bind_standard(workspace, "missing@1.0.0")
    assert service.open_workspace(workspace.dst_path).standard.status == "missing"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_service.py -q`

Expected: FAIL，标准应用服务尚不存在。

- [ ] **Step 3: 实现独立 StandardOperations 组合模块**

`DstManagerService` 只负责组合；标准列表、草稿保存、发布、绑定解析和项目快照恢复全部放入 `application/standards.py`。普通工作区打开遇到标准缺失只附加诊断，不创建项目快照。

- [ ] **Step 4: 实现保留属性读写保护**

AcSm DOM 只允许标准应用服务通过专用命令更新两个保留属性；普通 `update_sheet_set` 和属性定义删除必须以 `STANDARD_PROPERTY_RESERVED` 拒绝。

- [ ] **Step 5: 运行应用、DOM 和既有编辑回归**

Run: `uv run pytest tests/unit/test_standard_service.py tests/unit/test_acsm_custom_properties.py tests/unit/test_v021_editing.py -q`

Expected: 新测试和既有属性编辑测试全部通过。

- [ ] **Step 6: 提交标准应用服务**

```powershell
git add src/dst_manager/application src/dst_manager/domain/models.py src/dst_manager/infrastructure/acsm_xml/document.py tests/unit/test_standard_service.py changelog.md
git commit -m "编排标准发布绑定与快照恢复"
```

### Task 5: 实现模板资产检查与从 DST 建立草稿

**Files:**
- Create: `src/dst_manager/application/standard_assets.py`
- Create: `src/dst_manager/infrastructure/standards/dst_import.py`
- Create: `tests/unit/test_standard_assets.py`
- Create: `tests/integration/test_standard_dst_import.py`
- Modify: `src/dst_manager/application/cad_job.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: 标准草稿、现有 DST codec/AcSm DOM 与布局读取能力。
- Produces: `inspect_standard_asset(draft_id, asset_id, cad_version) -> AssetInspection`、`create_draft_from_dst(path) -> StandardDraft`。

- [ ] **Step 1: 写入严格图幅布局和 DST 清理测试**

```python
def test_layout_asset_requires_exact_paper_layout(fake_inspector, service) -> None:
    fake_inspector.layouts = ["Model", "A2 ", "A3"]
    result = service.inspect_standard_asset("draft", "layouts", "2020")
    assert result.diagnostics[0].code == "STANDARD_LAYOUT_NAME_MISMATCH"


def test_dst_import_excludes_project_structure(imported_draft) -> None:
    assert imported_draft.subsets == ()
    assert imported_draft.external_paths == ()
```

- [ ] **Step 2: 运行目标测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_assets.py tests/integration/test_standard_dst_import.py -q`

Expected: FAIL，资产检查与 DST 导入器尚不存在。

- [ ] **Step 3: 实现资产复制、布局检查和 DST 提取**

资产导入先复制到草稿私有目录；布局检查复用固定 CAD 读取协议，严格比较图幅枚举与非 Model 布局。DST 导入只提取属性定义和最小安全结构，不复制子集、图纸、工程路径或引用。

- [ ] **Step 4: 覆盖 2016/2020 能力缺失和非法 DST**

Run: `uv run pytest tests/unit/test_standard_assets.py tests/integration/test_standard_dst_import.py -q`

Expected: 能力缺失返回 `STANDARD_CAD_CAPABILITY_MISSING`；非法 DST 返回稳定诊断且不留下草稿资产半成品。

- [ ] **Step 5: 提交资产与 DST 导入能力**

```powershell
git add src/dst_manager/application/standard_assets.py src/dst_manager/infrastructure/standards/dst_import.py src/dst_manager/application/cad_job.py tests/unit/test_standard_assets.py tests/integration/test_standard_dst_import.py changelog.md
git commit -m "实现标准模板检查与 DST 提取"
```

### Task 6: 暴露标准 API 与受信扩展依赖

**Files:**
- Create: `src/dst_manager/interfaces/standard_contracts.py`
- Create: `src/dst_manager/interfaces/standard_api.py`
- Create: `tests/integration/test_standard_api.py`
- Modify: `src/dst_manager/interfaces/api.py`
- Modify: `src/dst_manager/interfaces/responses.py`
- Modify: `src/dst_manager/extensions/capabilities.py`
- Modify: `src/dst_manager/extensions/manifest.py`
- Modify: `web/src/api/openapi.json`
- Modify: `web/src/api/schema.d.ts`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `StandardOperations`。
- Produces: `/api/standards` 列表、草稿、检查、发布、导入、导出与资产检查端点；扩展依赖字段 `extension_id/capability_id/min_version`。

- [ ] **Step 1: 写入 API 契约测试**

```python
def test_published_standard_cannot_be_updated(client, published_standard) -> None:
    response = client.put(f"/api/standards/{published_standard.id}/{published_standard.version}", json={"name": "changed"})
    assert response.status_code == 409
    assert response.json()["code"] == "STANDARD_VERSION_IMMUTABLE"
```

- [ ] **Step 2: 运行测试并确认 404/导入失败**

Run: `uv run pytest tests/integration/test_standard_api.py -q`

Expected: FAIL，路由不存在。

- [ ] **Step 3: 实现独立 standard router 与 Pydantic 契约**

路由只转换请求/响应和错误码，不包含规则、文件或发布逻辑。缺少声明的受信能力时返回 `STANDARD_DEPENDENCY_MISSING`。

- [ ] **Step 4: 重新生成 OpenAPI 并运行契约检查**

Run: `uv run python scripts/export_openapi.py; uv run pytest tests/integration/test_standard_api.py tests/unit/test_extension_manifest.py -q; Set-Location web; npm run check:api; Set-Location ..`

Expected: API 与生成类型一致，测试全过。

- [ ] **Step 5: 提交 API 与扩展依赖契约**

```powershell
git add src/dst_manager/interfaces src/dst_manager/extensions web/src/api tests/integration/test_standard_api.py tests/unit/test_extension_manifest.py changelog.md
git commit -m "开放图纸标准管理 API"
```

### Task 7: 实现标准管理前端并完成阶段验证

**Files:**
- Create: `web/src/views/StandardsView.vue`
- Create: `web/src/features/standards/types.ts`
- Create: `web/src/features/standards/store.ts`
- Create: `web/src/components/standards/StandardList.vue`
- Create: `web/src/components/standards/StandardEditor.vue`
- Create: `web/src/components/standards/PropertyRulesEditor.vue`
- Create: `web/src/components/standards/TemplateAssetsEditor.vue`
- Create: `web/src/api/standards.ts`
- Create: `web/src/features/standards/store.test.ts`
- Create: `web/tests/e2e/standards.spec.ts`
- Create: `web/src/i18n/locales/zh-CN/standards.ts`
- Create: `web/src/i18n/locales/en-US/standards.ts`
- Modify: `web/src/i18n/index.ts`
- Modify: `web/src/App.vue`
- Modify: `web/src/views/WelcomeView.vue`
- Modify: `docs/dst-manager/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 6 的标准 API。
- Produces: 欢迎页“标准管理”入口、官方/用户分区、草稿编辑、资产检查、发布和导入导出 UI。

- [ ] **Step 1: 写入 store 与 E2E 失败用例**

```ts
it("keeps a published standard read-only", async () => {
  const store = createStandardStore(fakeApiWithPublishedStandard());
  await store.open("szmedi.gas", "2.1.0");
  expect(store.editor.readOnly).toBe(true);
});
```

E2E 覆盖从官方标准复制、添加枚举与映射、组合字段、导入两个 DWG、检查并发布。

- [ ] **Step 2: 运行前端测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/standards/store.test.ts; npm run test:e2e -- standards.spec.ts; Set-Location ..`

Expected: FAIL，新页面与 store 不存在。

- [ ] **Step 3: 实现标准列表、编辑器与错误聚焦**

官方标准卡片只读；用户草稿可编辑；发布版本只提供查看、导出、复制新草稿。字段组合使用字段浏览器和片段模型，不暴露 JSON 文本框。

- [ ] **Step 4: 运行前端单元、构建和目标 E2E**

Run: `Set-Location web; npm run test:unit; npm run build; npm run test:e2e -- standards.spec.ts; Set-Location ..`

Expected: 全部通过；中英文键集合一致，900×768 与 1440×900 无横向溢出。

- [ ] **Step 5: 运行阶段全量验证并记录证据**

Run: `uv run ruff check .; uv run pytest -q; uv lock --check; Set-Location web; npm run build; npm run test:e2e; Set-Location ..`

Expected: 全部通过。真实 CAD 资产检查在具备 2016/2020 环境时另运行 `DST_MANAGER_RUN_AUTOCAD=1` 系统测试；缺少环境时明确记录跳过。

- [ ] **Step 6: 更新计划验证摘要并提交**

```powershell
git add src web tests docs/dst-manager/README.md changelog.md .planning/plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md
git commit -m "交付图纸标准平台与编辑器"
```
