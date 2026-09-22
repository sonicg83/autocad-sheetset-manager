---
id: PLAN-DM-035
title: 图纸标准平台与标准编辑器实施计划
status: completed
owners:
- dst-manager
created: 2026-09-21
updated: 2026-09-22
related:
- RFC-INT-003
- ARCH-DM-001
- ARCH-DM-004
- ARCH-DM-006
- ARCH-DM-007
- SPEC-DM-015
- SPEC-DM-016
---

# 图纸标准平台与标准编辑器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在 DST Manager 中建立纯数据、版本不可变、普通用户可维护的图纸标准库与标准编辑器。

**Architecture:** 领域层定义标准 Schema 和封闭规则求值器；基础设施层负责官方/用户/项目三层存储与 `.dststandard` 导入导出；应用层编排草稿、校验和发布；接口与 Vue 页面只承载契约和交互。标准不含可执行代码，正式工程写入仍完全属于宿主。

**Tech Stack:** Python 3.12、dataclasses/Pydantic、FastAPI、lxml、openpyxl、Vue 3、TypeScript、Vite、Vitest、Playwright、pytest。

**Spec:** [`SPEC-DM-016 图纸标准管理与欢迎页入口 UI 规范`](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md)；领域范围与标准包决策来源为 [`RFC-INT-003`](../../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)。

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
- 十余个专业的一对一派生必须由一条映射表规则批量维护，重复源值、空值和枚举未覆盖项必须定位到表格行；Task 9 的前端测试覆盖。
- 官方标准、已发布版本和用户草稿的只读/可写边界不得因页面切换或加载失败而漂移；Task 8 与 Task 11 的 E2E 覆盖。
- 900×768、200% 缩放和键盘操作下，主从分栏、映射表、资产检查与发布问题跳转仍须可达；Task 11 的视觉与可访问性门禁覆盖。

---

### Task 1: 定义标准领域模型与 Schema

**Files:**
- Create: `src/dst_manager/domain/standards.py`
- Create: `tests/unit/test_drawing_standards.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: 无。
- Produces: `DrawingStandard`, `StandardProperty`, `StandardAsset`, `NumberingPolicy`, `StandardDependency` 与 `parse_standard_document(data: Mapping[str, object]) -> DrawingStandard`。

- [x] **Step 1: 写入最小标准解析失败测试**

```python
def test_parse_standard_requires_stable_identity() -> None:
    with pytest.raises(StandardSchemaError, match="STANDARD_ID_INVALID"):
        parse_standard_document({"schema_version": 1, "standard_id": "", "version": "1.0.0"})
```

- [x] **Step 2: 运行测试并确认导入失败**

Run: `uv run pytest tests/unit/test_drawing_standards.py::test_parse_standard_requires_stable_identity -q`

Expected: FAIL，原因是 `dst_manager.domain.standards` 不存在。

- [x] **Step 3: 实现冻结领域对象与严格解析器**

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

- [x] **Step 4: 添加标准往返与边界测试并运行**

Run: `uv run pytest tests/unit/test_drawing_standards.py -q`

Expected: 合法标准往返稳定；全部非法输入返回稳定错误码。

- [x] **Step 5: 提交领域 Schema**

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

- [x] **Step 1: 写入映射、组合与循环检测测试**

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

- [x] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_rules.py -q`

Expected: FAIL，规则编译与求值函数尚不存在。

- [x] **Step 3: 实现结构化片段和拓扑求值**

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

- [x] **Step 4: 运行领域测试与 Ruff**

Run: `uv run pytest tests/unit/test_drawing_standards.py tests/unit/test_standard_rules.py -q; uv run ruff check src/dst_manager/domain/standards.py src/dst_manager/domain/standard_rules.py tests/unit/test_drawing_standards.py tests/unit/test_standard_rules.py`

Expected: 全部通过。

- [x] **Step 5: 提交规则引擎**

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

- [x] **Step 1: 写入路径逃逸和版本不可变测试**

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

- [x] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_package.py tests/unit/test_standard_store.py -q`

Expected: FAIL，标准包与仓储模块不存在。

- [x] **Step 3: 实现安全包读取与原子标准库**

发布目录使用 `<standard_id>/<version>/`；官方根只读，用户草稿与发布根分离。导入先解压到临时目录，验证全部路径、扩展名、大小和 Schema 后使用同目录原子替换，不覆盖既有身份。

- [x] **Step 4: 添加重启往返、重复路径和非法扩展测试并运行**

Run: `uv run pytest tests/unit/test_standard_package.py tests/unit/test_standard_store.py -q`

Expected: 全部通过；`.py`、`.dll`、`.scr`、`.lsp`、`.exe` 与重复规范化路径均拒绝。

- [x] **Step 5: 提交标准存储**

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

- [x] **Step 1: 写入缺失快照恢复和降级测试**

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

- [x] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_service.py -q`

Expected: FAIL，标准应用服务尚不存在。

- [x] **Step 3: 实现独立 StandardOperations 组合模块**

`DstManagerService` 只负责组合；标准列表、草稿保存、发布、绑定解析和项目快照恢复全部放入 `application/standards.py`。普通工作区打开遇到标准缺失只附加诊断，不创建项目快照。

- [x] **Step 4: 实现保留属性读写保护**

AcSm DOM 只允许标准应用服务通过专用命令更新两个保留属性；普通 `update_sheet_set` 和属性定义删除必须以 `STANDARD_PROPERTY_RESERVED` 拒绝。

- [x] **Step 5: 运行应用、DOM 和既有编辑回归**

Run: `uv run pytest tests/unit/test_standard_service.py tests/unit/test_acsm_custom_properties.py tests/unit/test_v021_editing.py -q`

Expected: 新测试和既有属性编辑测试全部通过。

- [x] **Step 6: 提交标准应用服务**

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

- [x] **Step 1: 写入严格图幅布局和 DST 清理测试**

```python
def test_layout_asset_requires_exact_paper_layout(fake_inspector, service) -> None:
    fake_inspector.layouts = ["Model", "A2 ", "A3"]
    result = service.inspect_standard_asset("draft", "layouts", "2020")
    assert result.diagnostics[0].code == "STANDARD_LAYOUT_NAME_MISMATCH"


def test_dst_import_excludes_project_structure(imported_draft) -> None:
    assert imported_draft.subsets == ()
    assert imported_draft.external_paths == ()
```

- [x] **Step 2: 运行目标测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_assets.py tests/integration/test_standard_dst_import.py -q`

Expected: FAIL，资产检查与 DST 导入器尚不存在。

- [x] **Step 3: 实现资产复制、布局检查和 DST 提取**

资产导入先复制到草稿私有目录；布局检查复用固定 CAD 读取协议，严格比较图幅枚举与非 Model 布局。DST 导入只提取属性定义和最小安全结构，不复制子集、图纸、工程路径或引用。

- [x] **Step 4: 覆盖 2016/2020 能力缺失和非法 DST**

Run: `uv run pytest tests/unit/test_standard_assets.py tests/integration/test_standard_dst_import.py -q`

Expected: 能力缺失返回 `STANDARD_CAD_CAPABILITY_MISSING`；非法 DST 返回稳定诊断且不留下草稿资产半成品。

- [x] **Step 5: 提交资产与 DST 导入能力**

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

- [x] **Step 1: 写入 API 契约测试**

```python
def test_published_standard_cannot_be_updated(client, published_standard) -> None:
    response = client.put(f"/api/standards/{published_standard.id}/{published_standard.version}", json={"name": "changed"})
    assert response.status_code == 409
    assert response.json()["code"] == "STANDARD_VERSION_IMMUTABLE"
```

- [x] **Step 2: 运行测试并确认 404/导入失败**

Run: `uv run pytest tests/integration/test_standard_api.py -q`

Expected: FAIL，路由不存在。

- [x] **Step 3: 实现独立 standard router 与 Pydantic 契约**

路由只转换请求/响应和错误码，不包含规则、文件或发布逻辑。缺少声明的受信能力时返回 `STANDARD_DEPENDENCY_MISSING`。

- [x] **Step 4: 重新生成 OpenAPI 并运行契约检查**

Run: `uv run python scripts/export_openapi.py; uv run pytest tests/integration/test_standard_api.py tests/unit/test_extension_manifest.py -q; Set-Location web; npm run check:api; Set-Location ..`

Expected: API 与生成类型一致，测试全过。

- [x] **Step 5: 提交 API 与扩展依赖契约**

```powershell
git add src/dst_manager/interfaces src/dst_manager/extensions web/src/api tests/integration/test_standard_api.py tests/unit/test_extension_manifest.py changelog.md
git commit -m "开放图纸标准管理 API"
```

### Task 7: 建立标准前端契约、状态控制器与欢迎页入口

**Files:**
- Create: `web/src/api/standards.ts`
- Create: `web/src/features/standards/types.ts`
- Create: `web/src/features/standards/store.ts`
- Create: `web/src/features/standards/store.test.ts`
- Create: `web/src/composables/useStartNavigation.ts`
- Create: `web/src/composables/useStartNavigation.test.ts`
- Create: `web/src/i18n/locales/zh-CN/standards.ts`
- Create: `web/src/i18n/locales/en-US/standards.ts`
- Create: `web/tests/e2e/standards-welcome.spec.ts`
- Modify: `web/src/i18n/index.ts`
- Modify: `web/src/App.vue`
- Modify: `web/src/views/WelcomeView.vue`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 6 生成的 OpenAPI 类型与标准 API。
- Produces: `type StartSurface = "welcome" | "standards" | "create-sheetset"`、`useStartNavigation()`、`createStandardStore(api): StandardStore`；`StandardStore` 暴露 `list()`, `open(identity)`, `createDraft(input)`, `saveDraft(input)`, `inspectDraft(id)`, `publish(input)`, `importPackage(file)` 与明确的 pending/error/generation 状态。

- [x] **Step 1: 写入应用级导航和乱序响应失败测试**

```ts
it("returns from standards without creating a workspace", () => {
  const navigation = useStartNavigation();
  navigation.openStandards();
  expect(navigation.surface.value).toBe("standards");
  navigation.goWelcome();
  expect(navigation.surface.value).toBe("welcome");
});

it("does not let an older detail response replace the current standard", async () => {
  const api = deferredStandardApi();
  const store = createStandardStore(api);
  const first = store.open({standardId: "official.a", version: "1.0.0"});
  const second = store.open({standardId: "user.b", version: "2.0.0"});
  api.resolveDetail("user.b", publishedDetail("user.b", "2.0.0"));
  api.resolveDetail("official.a", publishedDetail("official.a", "1.0.0"));
  await Promise.all([first, second]);
  expect(store.detail.value?.standardId).toBe("user.b");
});
```

- [x] **Step 2: 运行定向单元测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/standards/store.test.ts src/composables/useStartNavigation.test.ts; Set-Location ..`

Expected: FAIL，标准状态控制器与应用级导航尚不存在。

- [x] **Step 3: 实现 API 包装、代次保护与应用级页面装配**

`types.ts` 只为生成契约建立窄别名和 UI 判别联合，不复制后端最终校验规则。`App.vue` 在无工作区时按 `StartSurface` 装配欢迎页或标准管理页；`standards` 不加入工作区标签栏。`create-sheetset` 只保留 PLAN-DM-036 的编译期入口占位，未实现时显示明确不可用说明，不回退为无标准创建。

- [x] **Step 4: 实现欢迎页“打开优先”双栏与入口 E2E**

```ts
test("欢迎页保持打开 DST 为唯一主任务", async ({page}) => {
  await expect(page.getByRole("heading", {name: "打开图纸集"})).toBeVisible();
  await expect(page.getByRole("button", {name: "选择 DST 文件"})).toHaveClass(/primary/);
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(page.getByRole("heading", {name: "标准管理"})).toBeVisible();
  await expect(page.locator(".workspace-tabs")).toHaveCount(0);
});
```

同时覆盖无桌面壳路径输入、标准包导入失败留在标准上下文、900×768 单列顺序和普通 DST 打开行为不回归。

- [x] **Step 5: 运行单元、i18n、构建与欢迎页 E2E**

Run: `Set-Location web; npm run test:unit -- src/features/standards/store.test.ts src/composables/useStartNavigation.test.ts; npm run check:i18n; npm run build; npm run test:e2e -- standards-welcome.spec.ts; Set-Location ..`

Expected: 全部通过；中英文键集合一致，欢迎页在 900×768 无横向滚动。

- [x] **Step 6: 提交前端契约与欢迎页**

```powershell
git add web/src/api/standards.ts web/src/features/standards web/src/composables/useStartNavigation.ts web/src/composables/useStartNavigation.test.ts web/src/i18n web/src/App.vue web/src/views/WelcomeView.vue web/tests/e2e/standards-welcome.spec.ts changelog.md
git commit -m "建立标准前端状态与欢迎页入口"
```

### Task 8: 实现主从分栏标准库与只读边界

**Files:**
- Create: `web/src/views/StandardsView.vue`
- Create: `web/src/components/standards/StandardLibraryPane.vue`
- Create: `web/src/components/standards/StandardDetailPane.vue`
- Create: `web/src/components/standards/StandardCreateDialog.vue`
- Create: `web/src/components/standards/standardLibraryModel.ts`
- Create: `web/src/components/standards/standardLibraryModel.test.ts`
- Create: `web/tests/e2e/standards-library.spec.ts`
- Modify: `web/src/App.vue`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 7 的 `StandardStore` 与 `StartSurface`。
- Produces: `StandardsView` 的 `back`, `open-create-sheetset` 事件；`filterStandardList(items, query): StandardListItem[]`；标准库选择、筛选、详情和新建草稿 UI。

- [x] **Step 1: 写入筛选、空态与只读动作测试**

```ts
it("separates an empty library from an empty filter result", () => {
  expect(buildLibraryState([], DEFAULT_FILTERS).kind).toBe("empty-library");
  expect(buildLibraryState([officialStandard()], {source: "user", status: "all", query: ""}).kind)
    .toBe("empty-filter");
});

it("keeps official and published versions read-only", () => {
  expect(detailActions(officialStandard()).canEdit).toBe(false);
  expect(detailActions(publishedUserStandard()).canEdit).toBe(false);
  expect(detailActions(userDraft()).canEdit).toBe(true);
});
```

- [x] **Step 2: 运行定向测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/components/standards/standardLibraryModel.test.ts; Set-Location ..`

Expected: FAIL，标准库模型与组件尚不存在。

- [x] **Step 3: 实现主从分栏、筛选与详情动作**

左栏实现名称/ID 搜索、来源和状态筛选；右栏实现身份、能力摘要、版本历史、草稿和动作。官方标准与已发布版本只显示查看、导出、复制/派生和用于创建；所有禁用动作附带可见原因。900×768 改为“列表 → 详情”分级视图。

- [x] **Step 4: 实现新建空白、复制发布版本、从 DST 提取与导入预检**

新建对话框只负责选择三个草稿起点；标准包导入保持独立动作。删除草稿、替换当前选择和离开标准库均通过共享确认模态；导入碰撞或校验失败不改变列表选择。

- [x] **Step 5: 添加标准库 E2E 并运行目标门禁**

```ts
test("发布版本只读并可派生草稿", async ({page}) => {
  await openStandard(page, "市政燃气施工图", "2.1.0");
  await expect(page.getByText("已发布版本不可直接修改")).toBeVisible();
  await expect(page.getByRole("button", {name: "编辑"})).toHaveCount(0);
  await page.getByRole("button", {name: "派生新草稿"}).click();
  await expect(page.getByText("草稿 3")).toBeVisible();
});
```

Run: `Set-Location web; npm run test:unit -- src/components/standards/standardLibraryModel.test.ts; npm run build; npm run test:e2e -- standards-library.spec.ts; Set-Location ..`

Expected: 全部通过；加载失败、搜索无结果、官方只读、发布只读和草稿可编辑边界稳定。

- [x] **Step 6: 提交标准库**

```powershell
git add web/src/views/StandardsView.vue web/src/components/standards web/src/App.vue web/tests/e2e/standards-library.spec.ts changelog.md
git commit -m "实现主从分栏图纸标准库"
```

### Task 9: 实现分区标准编辑器、映射表与字段组合

**Files:**
- Create: `web/src/components/standards/StandardEditor.vue`
- Create: `web/src/components/standards/StandardSectionNav.vue`
- Create: `web/src/components/standards/StandardPropertyEditor.vue`
- Create: `web/src/components/standards/StandardRulesEditor.vue`
- Create: `web/src/components/standards/MappingTableEditor.vue`
- Create: `web/src/components/standards/CompositionEditor.vue`
- Create: `web/src/features/standards/draftModel.ts`
- Create: `web/src/features/standards/draftModel.test.ts`
- Create: `web/tests/e2e/standards-editor.spec.ts`
- Modify: `web/src/views/StandardsView.vue`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 7 的 `StandardStore.saveDraft()`、Task 6 的草稿/诊断契约和 SPEC-DM-015 的直接保存状态机。
- Produces: `buildMappingRows(text): MappingRow[]`、`validateMapping(rows, sourceDomain, targetRule): RowDiagnostic[]`、`renderCompositionPreview(segments, sampleValues): PreviewResult`；分区编辑、错误跳转与未保存离开门禁。

- [x] **Step 1: 写入十余行映射批量粘贴与组合预览失败测试**

```ts
it("imports many specialty mappings into one mapping rule", () => {
  const rows = buildMappingRows("燃气\tRQ\n建筑\tJZ\n结构\tJG\n给排水\tGPS");
  expect(rows).toHaveLength(4);
  expect(rows[0]).toEqual({source: "燃气", target: "RQ"});
});

it("locates duplicate and uncovered source values", () => {
  const diagnostics = validateMapping(
    [{source: "燃气", target: "RQ"}, {source: "燃气", target: "GAS"}],
    ["燃气", "建筑"],
    codeRule(),
  );
  expect(diagnostics.map(item => [item.code, item.row])).toEqual([
    ["STANDARD_MAPPING_SOURCE_DUPLICATE", 2],
    ["STANDARD_MAPPING_SOURCE_UNCOVERED", null],
  ]);
});
```

- [x] **Step 2: 运行定向测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/standards/draftModel.test.ts; Set-Location ..`

Expected: FAIL，草稿编辑模型尚不存在。

- [x] **Step 3: 实现分区壳、属性定义与普通规则编辑器**

顶部固定显示草稿身份、保存状态、保存和发布检查；左侧导航按 SPEC-DM-016 §6 排列。属性定义支持现有 CSV 导入；普通规则采用列表 + 侧边结构化编辑器并生成自然语言摘要。子集属性只显示预留说明。

- [x] **Step 4: 实现字段映射表**

一条映射规则选择一个源字段和一个目标字段，以两列表维护全部值；支持逐行编辑、制表符/CSV 批量导入。源值唯一且非空，目标值接受目标字段约束；未覆盖项阻止发布。映射目标在创建流程中标记为派生只读，不产生十几条普通联动规则。

- [x] **Step 5: 实现字段组合与 DWG 命名片段编辑器**

片段只允许字段令牌、固定文本和受控序号令牌；字段浏览器过滤不可引用字段，预览使用后端返回或同契约纯展示结果，不在前端复制最终规则求值。未知引用、循环和非法格式码显示就地诊断，不暴露 JSON 文本框。

- [x] **Step 6: 添加编辑器状态、键盘与门禁 E2E**

```ts
test("映射批量粘贴后保存为一条规则", async ({page}) => {
  await openDraftSection(page, "字段映射");
  await page.getByRole("button", {name: "批量粘贴"}).click();
  await page.getByLabel("映射内容").fill("燃气\tRQ\n建筑\tJZ\n结构\tJG");
  await page.getByRole("button", {name: "应用 3 行"}).click();
  await expect(page.getByRole("row")).toHaveCount(4);
  await expect(page.getByText("1 条字段映射规则")).toBeVisible();
});
```

同时覆盖 dirty 改回、保存失败、修订冲突、分区切换不丢输入、离开三选一门禁、错误摘要跳到映射行与纯键盘操作。

Run: `Set-Location web; npm run test:unit -- src/features/standards/draftModel.test.ts; npm run build; npm run test:e2e -- standards-editor.spec.ts; Set-Location ..`

Expected: 全部通过；字段映射和字段组合是两个独立派生类型。

- [x] **Step 7: 提交标准编辑器**

```powershell
git add web/src/components/standards web/src/features/standards/draftModel.ts web/src/features/standards/draftModel.test.ts web/src/views/StandardsView.vue web/tests/e2e/standards-editor.spec.ts changelog.md
git commit -m "实现图纸标准分区编辑器"
```

### Task 10: 实现模板资产检查与独立发布检查页

**Files:**
- Create: `web/src/components/standards/TemplateAssetsEditor.vue`
- Create: `web/src/components/standards/AssetInspectionPanel.vue`
- Create: `web/src/components/standards/StandardPublishReview.vue`
- Create: `web/src/features/standards/publishModel.ts`
- Create: `web/src/features/standards/publishModel.test.ts`
- Create: `web/tests/e2e/standards-assets-publish.spec.ts`
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/views/StandardsView.vue`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 5 的 `AssetInspection`、Task 7 的 `StandardStore.inspectDraft()` / `publish()`。
- Produces: 基础/布局模板分类列表、来源筛选、资产检查面板和 `buildPublishGate(report): PublishGate`；`PublishGate` 明确 `blockingErrors`, `warnings`, `canPublish` 与问题目标。

- [x] **Step 1: 写入布局严格匹配与发布门禁失败测试**

```ts
it("blocks publish for a missing exact paper layout", () => {
  const gate = buildPublishGate(reportWithLayouts({declared: ["A2", "A3"], actual: ["A2", "A3 "]}));
  expect(gate.canPublish).toBe(false);
  expect(gate.blockingErrors[0].target).toEqual({section: "assets", assetId: "layouts", layout: "A3"});
});

it("allows publish with warnings only", () => {
  const gate = buildPublishGate(reportWithUnusedAssetWarning());
  expect(gate.canPublish).toBe(true);
  expect(gate.warnings).toHaveLength(1);
});
```

- [x] **Step 2: 运行定向测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/standards/publishModel.test.ts; Set-Location ..`

Expected: FAIL，资产和发布视图模型尚不存在。

- [x] **Step 3: 实现分类资产列表与检查面板**

基础/布局模板为主分类，官方/用户为筛选器；列表显示名称、来源、状态和引用数。右侧显示路径、引用关系、检查时间和诊断；布局资产列出全部非 `Model` 布局并严格比较图幅。官方资产只读，用户资产替换前显示影响范围。

- [x] **Step 4: 实现独立发布检查页与问题跳转**

检查页按基本信息、属性、规则、命名、资产和包结构分组。错误禁用发布，警告允许继续；版本号和说明采用 SPEC-DM-015 直接保存语义。问题跳转返回编辑器对应分区并聚焦真实字段、映射行或资产。发布成功后进入新版本只读详情。

- [x] **Step 5: 添加资产丢失、CAD 能力缺失和发布完整流程 E2E**

```ts
test("发布错误可返回映射表并聚焦缺失项", async ({page}) => {
  await page.getByRole("button", {name: "发布检查"}).click();
  await page.getByRole("link", {name: /专业代码映射不完整/}).click();
  await expect(page.getByRole("heading", {name: "专业代码映射"})).toBeVisible();
  await expect(page.getByTestId("mapping-uncovered-summary")).toBeFocused();
});
```

Run: `Set-Location web; npm run test:unit -- src/features/standards/publishModel.test.ts; npm run build; npm run test:e2e -- standards-assets-publish.spec.ts; Set-Location ..`

Expected: 全部通过；资产移动、布局不匹配、检查任务失败、警告发布和成功后只读均有稳定行为。

- [x] **Step 6: 提交资产与发布 UI**

```powershell
git add web/src/components/standards web/src/features/standards/publishModel.ts web/src/features/standards/publishModel.test.ts web/src/views/StandardsView.vue web/tests/e2e/standards-assets-publish.spec.ts changelog.md
git commit -m "实现标准模板资产与发布检查界面"
```

### Task 11: 完成设计证据、全量验证与文档收口

**Files:**
- Create: `web/tests/e2e/standards-visual-evidence.spec.ts`
- Create: `docs/dst-manager/specs/assets/SPEC-DM-016/README.md`
- Create: `docs/dst-manager/specs/assets/SPEC-DM-016/production/`
- Modify: `docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 7–10 的完整标准管理 UI 与 SPEC-DM-016 ST-UI-01～12。
- Produces: G8 生产视觉证据、自动化验收记录和 G9 真实桌面检查清单。

- [x] **Step 1: 为 ST-UI-01～12 建立追踪矩阵**

在 SPEC-DM-016 §12 追加每条场景对应的单元/E2E 用例、生产截图、操作者、日期和未关闭差异。任何没有自动化或证据承接的条目不得标记通过。

- [x] **Step 2: 编写视觉证据用例**

`standards-visual-evidence.spec.ts` 固定相同数据和状态，输出欢迎页、标准库、属性编辑、字段映射、字段组合、模板资产、发布错误和发布成功详情；覆盖 1440×900 浅色，以及关键页面的深色或 900×768 状态。每张截图禁用动画并等待字体与异步数据稳定。

- [x] **Step 3: 运行前端完整门禁与静态 UI 检查**

Run: `Set-Location web; npm run check:api; npm run check:i18n; npm run check:ui; npm run test:unit; npm run build; npm run test:e2e; Set-Location ..`

Expected: 全部通过；900×768 无横向溢出，键盘焦点与错误跳转用例全绿。

- [x] **Step 4: 运行 Python、迁移与锁文件门禁**

Run: `uv run ruff check .; uv run pytest -q; uv run alembic upgrade head; uv lock --check`

Expected: 全部通过；全新数据库可升级到 head，既有 Manager 编辑与只读打开回归无失败。

- [x] **Step 5: 运行可用环境内的双版本 CAD 资产检查**

Run: `$env:DST_MANAGER_RUN_AUTOCAD = "1"; uv run pytest tests/system_autocad -q`

Expected: AutoCAD 2016/2020 均能只读枚举布局且不修改 DWG。环境缺失时记录具体缺项和跳过数量，不伪称通过。

- [x] **Step 6: 执行 G8 对照与编制 G9 清单**

逐张比较 SPEC-DM-016 冻结设计与 `production/` 证据，记录相同点、差异分类和裁决。G9 清单必须覆盖真实 pywebview/WebView2 文件选择、导入导出、键盘焦点、最小窗口、200% 系统缩放、DWG 检查启动/返回和发布成功后的只读状态。

- [x] **Step 7: 更新实际验证摘要并提交阶段交付**

```powershell
git add src web tests docs/dst-manager .planning/plans/dst-manager changelog.md
git commit -m "交付图纸标准平台与编辑器"
```

---

## 实际验证摘要（2026-09-22，Task 11 收口）

### 交付范围

Task 1–11 全部完成，提交序列：`275fac1`（领域模型）→ `ff75611`（封闭规则求值）→ `ab9c937`
（标准包与标准库）→ `79fc60c`（草稿/发布/快照编排）→ `62f0efc`（资产检查与 DST 导入）→
`d82b6ad`（标准 API 与受信依赖）→ `380d7ca`（前端契约与欢迎页入口）→ `0ab67de`（主从分栏标准库）→
`305a2e6`（分区编辑器）→ `85916b4`（模板资产与发布检查）→ 本计划收口提交。

### 自动化验收

| 门禁 | 结果 |
| --- | --- |
| `npm run check:api` / `check:i18n` / `check:ui` / `build` | 通过（i18n 中英同构 1253 键，无未登记硬编码中文；UI 契约无新增违规） |
| `npm run test:unit` | 221 项通过（含 `draftModel` 16、`publishModel` 11、`standardLibraryModel` 6、`store` 6） |
| `npm run test:e2e`（全量） | 见 §「全量门禁执行记录」 |
| `uv run ruff check .` | 通过 |
| `uv run pytest -q` | 见 §「全量门禁执行记录」 |
| `uv run alembic upgrade head` | 见 §「全量门禁执行记录」 |
| `uv lock --check` | 通过 |

标准域专用回归：Python `tests/unit/test_drawing_standards.py`、`test_standard_rules.py`、
`test_standard_package.py`、`test_standard_store.py`、`test_standard_service.py`、
`test_standard_assets.py`、`tests/integration/test_standard_api.py`、
`tests/integration/test_standard_dst_import.py` 共 71 项通过；前端标准系 E2E 28 项
（`standards-welcome` 5、`standards-library` 8、`standards-editor` 8、`standards-assets-publish` 7）
通过，视觉证据 2 项通过。

### 视觉证据与 G8/G9

- G4 冻结件与 G8 生产证据各 12 张，存放于
  [`docs/dst-manager/specs/assets/SPEC-DM-016/`](../../../docs/dst-manager/specs/assets/SPEC-DM-016/README.md)
  （生产证据在 `production/`）；12 对逐张像素完全一致（SHA-256 相同），无未关闭视觉差异。
- 每张证据的抓图参数固定（时钟、禁用动画、字体就绪、blur 活动焦点、鼠标归位），可复现步骤见该目录 README §一。
- G9 真实桌面清单 8 项（文件选择、导入导出、键盘、最小窗口、200% 缩放、DWG 检查启动/返回、
  发布后只读、只读打开不落盘）已编制，状态：**待真实桌面环境执行**，未执行前不声明通过。

### 未修改项与残余风险（不静默略过）

1. **`cad_job.py` 未修改**（Task 5 遗留说明）：资产检查复用既有 `get_layout_names` 固定 CAD
   只读读取协议，经探索确认 `cad_job.py` 无直接可复用函数，故 Task 5/10 均未改动该文件。
2. **草稿资产文件本体无法经 API 写入**：后端没有把资产文件写入草稿受控目录的端点，编辑器只
   编辑资产声明；声明了但文件缺失的资产由 `STANDARD_ASSET_FILE_MISSING` 阻断发布，不伪造
   「已替换文件」。补齐需要新端点（路径、扩展名、大小与事务安全校验）与后续计划。
3. **版本说明字段**：SPEC-DM-016 §9.1 要求的版本说明以顶层 `release_notes` 随草稿文档保存并随
   标准包导出，不进入领域 Schema 校验；如需强类型或必填须修订标准 Schema（新增 ADR/修订 Spec）。
4. **错误码文案**：`STANDARD_*` 系列未登记进 `message_catalog.CATALOG`，前端按稳定码 + 语言包
   渲染，未知码回退后端原始文本；登记进 message catalog 可作为后续统一工作。
5. **双版本 AutoCAD 系统测试**：需本机 Core Console、插件与私有样本，按环境记录跳过项（见
   §「全量门禁执行记录」），未伪称通过。

### 全量门禁执行记录（2026-09-22）

| 命令 | 结果 |
| --- | --- |
| `npm run check:api`（`npm run build` 内含） | 通过：`openapi.json`/`schema.d.ts` 与后端契约一致（含 `StandardDetailResponse.document`） |
| `npm run check:i18n` | 通过：中英同构 **1253 键 / 10 域**，`web/src` 无未登记硬编码中文（allowlist 仅 1 条：属性 CSV 布尔别名） |
| `npm run check:ui` | 通过：无新增 UI 契约违规（未登记 CSS 变量、裸视觉值、缺少可见 label 等均为 0） |
| `npm run test:unit` | **221 passed**（23 文件） |
| `npm run build` | 通过（vue-tsc + vite build） |
| `npm run test:e2e`（全量，workers=4，retries=1） | **612 passed / 0 failed（4.8 分钟）** |
| `npm run test:contracts` | 通过（fail 0） |
| `uv run ruff check .` | 通过（`[]`） |
| `uv run pytest -q` | **1561 passed / 72 skipped / 0 failed**（共 1633 项；较 PLAN-DM-034 基线的 2280 项减少来自 2026-09-21 归档 DST Builder 时删除的 builder 测试） |
| `uv run alembic upgrade head`（指向全新临时库） | 通过：`0001_initial → 0006_dm020_extension_platform` 全量升级成功 |
| `uv lock --check` | 通过 |
| `DST_MANAGER_RUN_AUTOCAD=1`（`tests/system_autocad -k layout`，2016+2020） | **30 passed / 2 failed**：失败项为 `test_structural_subset_title_change_renames_layout_and_preserves_handle[2016/2020]`，断言 `revisions/<job>/before/<dst>` 的旧布局；PLAN-DM-031（2026-09-14）已把发布写入侧改为 attempt 嵌套命名空间，故该断言过期。与标准平台无关（该用例的布局重命名、Handle 保留、标题更新断言均通过），未在本次修改（属发布器后续计划范围）。 |
| 双版本 CAD 标准资产检查（`inspect_standard_asset`，Ad-hoc 校验） | 通过：AutoCAD 2016 与 2020 均只读枚举出布局 `['0000 封面']`，声明图幅 `A3` 与实际布局严格不一致时返回 `STANDARD_LAYOUT_NAME_MISMATCH`；样本 DWG 的 sha256 与 mtime 均未变化 |
| 完整 68 项 CAD 套件 | **未运行**：`-k layout` 子集单跑已 17 分钟，剩余用例与标准平台无关；CAD 系统测试需显式启用，记录为未执行而不是通过 |

环境修复记录（不涉及仓库内容）：`scripts/setup.bat` 在工作区被写成 LF 行尾，导致 `cmd` 无法执行该批处理、`tests/unit/test_setup_bat.py` 6 项失败；按 `core.autocrlf=true` 的约定恢复为 CRLF 后 6 项全部通过（索引内容无变化，未产生代码改动）。
