---
id: PLAN-DM-038
title: 图纸标准属性与 DWG 命名整改实施计划
status: proposed
owners:
- dst-manager
created: 2026-09-22
updated: 2026-09-22
related:
- SPEC-DM-017
- SPEC-DM-016
- PLAN-DM-035
- PLAN-DM-036
- PLAN-DM-037
---

# 图纸标准属性与 DWG 命名整改实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用普通属性、映射/组合派生属性和唯一全局 DWG 命名模板替换 PLAN-DM-035 的通用规则模型，使标准编辑、保存、发布与后续创建流程共享同一套无歧义 Schema v1。

**Architecture:** 后端把数据结构、跨引用校验/求值和 DWG 文件名渲染拆为三个纯领域单元，草稿只做结构校验，发布执行完整语义门禁。前端草稿模型镜像同一结构，普通属性、派生属性和 DWG 命名分别编辑；组合属性与 DWG 命名共用一个令牌编辑原语。当前未发布的旧 Schema v1 直接替换，开发期旧草稿、包和测试夹具同步重建，不保留兼容层。

**Tech Stack:** Python 3.12、dataclasses、FastAPI/Pydantic、Vue 3、TypeScript、Vitest、Playwright、pytest。

**Spec:** [`docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md`](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md)

## Global Constraints

- 标准 Schema 版本继续为 `1`；不得新增 v2 或旧规则迁移器。
- 属性作用域只有 `sheetset`、`sheet`；所有属性名跨作用域、跨普通/派生类型全局唯一。
- 普通属性种类只有 `text`、`enum`；派生属性种类只有 `mapping`、`composition`。
- 映射源只能是普通枚举属性且全标准唯一占用；组合不能引用组合。
- Sheet 系统字段只有 `sheet.number`、`sheet.title`；不提供 `sheet.name` 或布局名。
- 每个标准必须且只能有一个 DWG 命名模板；允许字段只有 `subset.scope/name/sequence` 与 sheetset 属性。
- 标准创建不使用隐式 DWG 前缀；`.dwg` 由系统追加，非法文件名不自动清洗。
- 草稿允许保存语义未完成内容；发布和标准驱动创建必须通过完整后端门禁。
- 领域层不得依赖 FastAPI、Vue、文件系统或 AutoCAD；前端预览不取代后端最终求值。
- 单个新源文件保持约 500 行以内；不得继续向已接近上限的组件堆叠无关职责。

## Review Focus

- 属性只改变大小写或前后空格时仍与当前/历史名称冲突；Task 1 单元测试覆盖。
- 枚举改名后映射按 `enum_item_id` 保留目标，但进入待确认 warning；Task 2 单元测试覆盖。
- 可选映射源为空应得到空结果而非错误，上游非法非空值必须阻断下游组合；Task 2 单元测试覆盖。
- `CON.dwg`、尾随句点、超长 Unicode 名称及大小写不同的重复目标均不得创建；Task 3 单元测试覆盖。
- 未完成草稿可以保存，但同一文档发布必须失败且不会移动草稿目录；Task 4 仓储/API 集成测试覆盖。

---

### Task 1: 替换 Schema v1 属性模型与结构解析

**Files:**
- Create: `src/dst_manager/domain/standard_models.py`
- Create: `src/dst_manager/domain/standard_schema.py`
- Modify: `src/dst_manager/domain/standards.py`
- Modify: `tests/unit/test_drawing_standards.py`

**Interfaces:**
- Consumes: JSON Schema v1 文档字典。
- Produces: `StandardEnumItem`、`StandardSegment`、`StandardMappingRow`、`StandardProperty`、`DwgNamingTemplate`、`DrawingStandard`；`parse_standard_draft_document(data)` 与 `parse_published_standard_document(data)`。

- [ ] **Step 1: 写入新 Schema 的失败测试**

```python
def test_schema_v1_uses_stable_property_and_enum_ids() -> None:
    standard = parse_published_standard_document(valid_standard_document())
    major = standard.property_by_id("prop-major")
    assert major.kind == "enum"
    assert [(item.item_id, item.value) for item in major.enum_items] == [("enum-gas", "燃气")]
    assert standard.dwg_naming.segments[-1].system_field == "subset.name"

def test_property_names_are_globally_unique_across_scopes_and_history() -> None:
    document = valid_standard_document()
    document["properties"].append({
        "property_id": "prop-sheet", "name": " 专业 ", "previous_names": [],
        "scope": "sheet", "kind": "text", "required": False,
        "default_value": "", "description": "",
    })
    with pytest.raises(StandardSchemaError, match="STANDARD_PROPERTY_NAME_DUPLICATE"):
        parse_published_standard_document(document)
```

- [ ] **Step 2: 运行测试并确认旧模型失败**

Run: `uv run pytest tests/unit/test_drawing_standards.py -q`

Expected: FAIL，旧 `StandardProperty` 不含稳定 ID/kind/enum item，文档仍要求通用 `rules`。

- [ ] **Step 3: 定义冻结模型和两阶段解析入口**

```python
@dataclass(frozen=True, slots=True)
class StandardProperty:
    property_id: str
    name: str
    previous_names: tuple[str, ...]
    scope: Literal["sheetset", "sheet"]
    kind: Literal["text", "enum", "mapping", "composition"]
    required: bool
    default_value: str
    enum_items: tuple[StandardEnumItem, ...]
    source_property_id: str | None
    mapping: tuple[StandardMappingRow, ...]
    confirmed_source_items: tuple[tuple[str, str], ...]
    segments: tuple[StandardSegment, ...]
    description: str

def parse_standard_draft_document(data: Mapping[str, object]) -> DrawingStandard: ...
def parse_published_standard_document(data: Mapping[str, object]) -> DrawingStandard: ...
```

`standard_models.py` 只放数据类型；`standard_schema.py` 负责类型解析、ID/名称/保留字/引用结构校验；`standards.py` 作为既有公共导入门面重导出新接口。草稿解析允许空属性名、空映射目标和空命名片段，但稳定 ID、JSON 类型与引用对象结构必须合法；发布解析在同一模型上追加完整语义校验。

- [ ] **Step 4: 覆盖删除保护所需的反向引用查询**

新增 `DrawingStandard.references_to(property_id) -> tuple[StandardReference, ...]` 测试，确保映射源、组合令牌和 DWG 命名令牌都被枚举，组合不能引用组合，`sheetset`/`sheet` 作用域约束准确。

- [ ] **Step 5: 运行领域 Schema 测试**

Run: `uv run pytest tests/unit/test_drawing_standards.py -q`

Expected: PASS。

- [ ] **Step 6: 提交模型替换**

```powershell
git add src/dst_manager/domain/standard_models.py src/dst_manager/domain/standard_schema.py src/dst_manager/domain/standards.py tests/unit/test_drawing_standards.py
git commit -m "重构图纸标准属性模型"
```

---

### Task 2: 实现映射、组合与发布诊断

**Files:**
- Modify: `src/dst_manager/domain/standard_rules.py`
- Modify: `tests/unit/test_standard_rules.py`

**Interfaces:**
- Consumes: Task 1 的 `DrawingStandard` 与按 `property_id` 提供的普通属性值。
- Produces: `compile_standard_properties(standard) -> CompiledProperties`、`evaluate_standard_properties(compiled, values, system_values) -> EvaluationResult`、`publish_diagnostics(standard) -> tuple[StandardDiagnostic, ...]`。

- [ ] **Step 1: 写入映射身份、作用域与失败传播测试**

先在 `tests/unit/test_standard_rules.py` 增加本地工厂 `standard_document(*, enum_value: str = "燃气", confirmed_value: str | None = "燃气") -> dict[str, object]`，返回 Task 1 新 Schema 的完整最小文档；本任务所有测试只通过该工厂改变源枚举当前值和确认快照。

```python
def test_enum_rename_keeps_mapping_and_requires_confirmation() -> None:
    standard = parse_published_standard_document(standard_document(enum_value="城镇燃气", confirmed_value="燃气"))
    result = evaluate_standard_properties(compile_standard_properties(standard), {"prop-major": "城镇燃气"}, {})
    assert result.values["prop-code"] == "RQ"
    assert "STANDARD_MAPPING_CONFIRMATION_REQUIRED" in codes(publish_diagnostics(standard))

def test_empty_optional_mapping_source_is_empty_but_invalid_source_blocks_composition() -> None:
    compiled = compile_standard_properties(parse_published_standard_document(standard_document()))
    assert evaluate_standard_properties(compiled, {"prop-major": ""}, {}).values["prop-code"] == ""
    invalid = evaluate_standard_properties(compiled, {"prop-major": "未知"}, {})
    assert "prop-label" not in invalid.values
    assert codes(invalid.diagnostics) == ["STANDARD_ENUM_VALUE_INVALID", "STANDARD_DERIVED_UPSTREAM_INVALID"]
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_rules.py -q`

Expected: FAIL，旧求值器按字段字符串和自由规则目标工作。

- [ ] **Step 3: 按固定拓扑实现求值**

```python
def evaluate_standard_properties(compiled, values, system_values):
    result = dict(values)
    evaluate_mappings(compiled.mappings, result)
    evaluate_compositions(compiled.compositions, result, system_values)
    return EvaluationResult(values=result, diagnostics=tuple(diagnostics))
```

映射按 `enum_item_id` 查目标；组合令牌只解析 `property_id`、`sheet.number`、`sheet.title`。可选空值拼接为空字符串；非法非空枚举、未覆盖映射或上游失败不得读取已有派生值。

- [ ] **Step 4: 写入映射源唯一、目标可重复及确认快照测试**

覆盖两个映射共享源时报 `STANDARD_MAPPING_SOURCE_DUPLICATE`、空目标为 error、重复目标合法、枚举新增/删除/排序后的固定行集合与 warning。

- [ ] **Step 5: 运行规则测试**

Run: `uv run pytest tests/unit/test_standard_rules.py -q`

Expected: PASS。

- [ ] **Step 6: 提交属性求值器**

```powershell
git add src/dst_manager/domain/standard_rules.py tests/unit/test_standard_rules.py
git commit -m "实现标准派生属性求值"
```

---

### Task 3: 实现唯一全局 DWG 命名模板

**Files:**
- Create: `src/dst_manager/domain/standard_naming.py`
- Create: `tests/unit/test_standard_naming.py`

**Interfaces:**
- Consumes: `DrawingStandard`、已求值 sheetset 属性、`SubsetNamingContext(scope, name, sequence)`。
- Produces: `render_dwg_filename(...) -> NamingResult`、`validate_dwg_filenames(...) -> tuple[NamingResult, ...]`。

- [ ] **Step 1: 写入字段范围、补零和安全测试**

在新测试文件定义 `naming_standard(*segments) -> DrawingStandard`（返回带 `prop-code` sheetset 映射属性和指定命名片段的最小已发布标准）及 `literal_standard(value: str) -> DrawingStandard`（命名模板仅含该固定文本）。

```python
def test_renders_explicit_prefix_scope_and_name() -> None:
    result = render_dwg_filename(naming_standard(), {"prop-code": "RQ"}, SubsetNamingContext("007-011", "迁改平面图", 1))
    assert result.filename == "RQ-007-011 迁改平面图.dwg"

@pytest.mark.parametrize("name", ["CON", "bad.", "a/b", "..", "x" * 237])
def test_rejects_unsafe_windows_filename(name: str) -> None:
    result = render_dwg_filename(literal_standard(name), {}, SubsetNamingContext("001", "示例", 1))
    assert result.diagnostics
```

- [ ] **Step 2: 运行测试并确认模块不存在**

Run: `uv run pytest tests/unit/test_standard_naming.py -q`

Expected: FAIL with import error。

- [ ] **Step 3: 实现终端命名求值与碰撞检查**

```python
@dataclass(frozen=True, slots=True)
class SubsetNamingContext:
    scope: str
    name: str
    sequence: int

def validate_dwg_filenames(standard, sheetset_values, subsets):
    results = tuple(render_dwg_filename(standard, sheetset_values, item) for item in subsets)
    reject_casefold_collisions(result.filename for result in results)
    return results
```

只允许 `subset.scope/name/sequence` 和 sheetset 属性；`subset.sequence` 允许宽度 1–12 的补零；扩展名固定追加。检查 Windows 非法字符、路径、设备名、尾随空格/句点、240 字符上限与 casefold 冲突，不做字符替换。

- [ ] **Step 4: 覆盖 warning 与失败传播**

测试模板同时缺少 `subset.scope`/`subset.sequence` 时发布 warning；sheet 属性令牌为 error；上游 sheetset 派生失败时命名结果不可用；两个 `000 封面` 发生实际碰撞时返回 `DWG_TARGET_COLLISION`。

- [ ] **Step 5: 运行命名测试并提交**

Run: `uv run pytest tests/unit/test_standard_naming.py -q`

Expected: PASS。

```powershell
git add src/dst_manager/domain/standard_naming.py tests/unit/test_standard_naming.py
git commit -m "实现标准 DWG 命名模板"
```

---

### Task 4: 接线草稿、发布、包与 DST 提取

**Files:**
- Modify: `src/dst_manager/infrastructure/standards/store.py`
- Modify: `src/dst_manager/infrastructure/standards/package.py`
- Modify: `src/dst_manager/infrastructure/standards/dst_import.py`
- Modify: `src/dst_manager/application/standards.py`
- Modify: `src/dst_manager/application/standard_assets.py`
- Modify: `tests/unit/test_standard_store.py`
- Modify: `tests/unit/test_standard_package.py`
- Modify: `tests/unit/test_standard_assets.py`
- Modify: `tests/integration/test_standard_dst_import.py`
- Modify: `tests/integration/test_standard_api.py`

**Interfaces:**
- Consumes: Tasks 1–3 的草稿/发布解析器和 `publish_diagnostics`。
- Produces: 草稿宽松保存、发布严格门禁、按新 Schema 导入导出的应用行为。

- [ ] **Step 1: 写入草稿可保存但不可发布的回归测试**

在 `tests/integration/test_standard_api.py` 增加本地 `incomplete_mapping_document()`：基于该文件的新 Schema 有效夹具，把 `prop-code.mapping[0].value` 设为空字符串，其他字段保持完整。

```python
def test_incomplete_mapping_draft_saves_but_does_not_publish(service) -> None:
    saved = service.create_standard_draft(incomplete_mapping_document())
    with pytest.raises(ApplicationError) as exc:
        service.publish_standard(saved["draft_id"])
    assert exc.value.code == "STANDARD_MAPPING_TARGET_EMPTY"
    assert service.get_standard_draft(saved["draft_id"])
```

- [ ] **Step 2: 运行标准仓储/API 测试并确认失败**

Run: `uv run pytest tests/unit/test_standard_store.py tests/unit/test_standard_package.py tests/integration/test_standard_api.py -q`

Expected: FAIL，当前保存与发布使用同一个严格解析器。

- [ ] **Step 3: 分离草稿与发布门禁**

`create_draft/save_draft` 调用 `parse_standard_draft_document`；`publish/import_package/get published` 调用 `parse_published_standard_document`。应用发布在任何目录移动前汇总 `publish_diagnostics`，首个 error 转为稳定 422；warning 保留在发布检查响应使用的诊断模型中。

- [ ] **Step 4: 更新 DST 提取结果**

提取的每个 DST 自定义属性生成稳定 `property_id`、`kind="text"`、空历史名称；同名跨作用域输入按全局唯一规则拒绝并给出诊断。文档写入必填默认 `dwg_naming`：`subset.scope + " " + subset.name`，不读取或猜测现有 DWG 前缀。

- [ ] **Step 5: 重建所有标准测试夹具**

删除旧顶层 `rules` 结构，改用新属性内嵌映射/组合和 `dwg_naming`；确认 `.dststandard` 导出再导入往返保持 `property_id`、`enum_item_id`、历史名称和令牌引用。

- [ ] **Step 6: 运行后端标准域回归并提交**

Run: `uv run pytest tests/unit/test_drawing_standards.py tests/unit/test_standard_rules.py tests/unit/test_standard_naming.py tests/unit/test_standard_store.py tests/unit/test_standard_package.py tests/unit/test_standard_assets.py tests/integration/test_standard_api.py tests/integration/test_standard_dst_import.py -q`

Expected: PASS。

```powershell
git add src/dst_manager/infrastructure/standards src/dst_manager/application/standards.py src/dst_manager/application/standard_assets.py tests/unit tests/integration/test_standard_api.py tests/integration/test_standard_dst_import.py
git commit -m "接线标准草稿与发布门禁"
```

---

### Task 5: 重建前端草稿模型与诊断路由

**Files:**
- Modify: `web/src/features/standards/draftModel.ts`
- Modify: `web/src/features/standards/draftModel.test.ts`
- Modify: `web/src/features/standards/publishModel.ts`
- Modify: `web/src/features/standards/publishModel.test.ts`
- Modify: `web/src/features/standards/types.ts`

**Interfaces:**
- Consumes: 新 Schema 原始 JSON。
- Produces: `DraftProperty` 判别联合、`DraftSegment`、`DraftDwgNaming`、`draftDiagnostics(document)`、`publishIssues(document)`、`referencesTo(document, propertyId)`。

- [ ] **Step 1: 写入判别联合和诊断测试**

在测试文件顶部定义 `newSchemaDocument(): Record<string, unknown>`，返回包含 `prop-major` 枚举、`prop-code` 映射、默认 DWG 命名和既有资产/编号字段的完整最小文档。

```ts
it("keeps ids and separates ordinary from derived properties", () => {
  const draft = toDraftDocument(newSchemaDocument());
  expect(draft.properties.map(item => [item.property_id, item.kind])).toEqual([
    ["prop-major", "enum"], ["prop-code", "mapping"],
  ]);
  expect(referencesTo(draft, "prop-major")).toEqual([{kind: "mapping", ownerId: "prop-code"}]);
});
```

- [ ] **Step 2: 运行 Vitest 并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/standards/draftModel.test.ts src/features/standards/publishModel.test.ts`

Expected: FAIL，旧模型仍含 `DraftRule` 和七分区导航。

- [ ] **Step 3: 实现新草稿类型与纯函数**

```ts
export type DraftProperty = DraftTextProperty | DraftEnumProperty | DraftMappingProperty | DraftCompositionProperty;
export interface DraftDocument {
  properties: DraftProperty[];
  dwg_naming: {segments: DraftSegment[]};
}
export const EDITOR_SECTIONS = ["basic", "ordinary", "derived", "dwgNaming", "assets", "publish"] as const;
```

删除 `DraftRule`、`ORDINARY_RULE_KINDS`、`COMPOSITION_RULE_KINDS` 和循环拓扑逻辑；实现与后端同码的结构提示、全局名称冲突、引用删除保护、映射快照 warning 和命名字段范围提示。保存门禁只看结构致命错误，发布门禁包含全部 error。

- [ ] **Step 4: 运行前端模型测试并提交**

Run: `Set-Location web; npm run test:unit -- src/features/standards/draftModel.test.ts src/features/standards/publishModel.test.ts`

Expected: PASS。

```powershell
git add web/src/features/standards
git commit -m "重建标准前端草稿模型"
```

---

### Task 6: 实现普通属性表与枚举编辑模态框

**Files:**
- Create: `web/src/components/standards/OrdinaryPropertyEditor.vue`
- Create: `web/src/components/standards/EnumValuesDialog.vue`
- Create: `web/src/components/standards/OrdinaryPropertyEditor.test.ts`
- Delete: `web/src/components/standards/StandardPropertyEditor.vue`
- Delete: `web/src/components/standards/StandardRulesEditor.vue`

**Interfaces:**
- Consumes: Task 5 的 `DraftTextProperty | DraftEnumProperty`。
- Produces: 普通属性表编辑、稳定枚举项维护和受引用删除事件。

- [ ] **Step 1: 写入类型联动和枚举身份测试**

在组件测试内定义 `documentWithEnum(): DraftDocument` 和 `mountEditor(document): VueWrapper`；通过 `document.properties.find(item => item.property_id === id)` 读取修改结果，不使用模块级共享状态。

```ts
it("disables enum input for text and preserves enum item ids on rename", async () => {
  const wrapper = mountEditor(documentWithEnum());
  expect(wrapper.get("[data-testid=enum-summary-prop-text]").attributes("aria-disabled")).toBe("true");
  await wrapper.get("[data-testid=edit-enum-prop-major]").trigger("click");
  await wrapper.get("[data-testid=enum-value-enum-gas]").setValue("城镇燃气");
  const major = wrapper.props("document").properties.find(item => item.property_id === "prop-major");
  expect(major?.enum_items[0]).toEqual({item_id: "enum-gas", value: "城镇燃气"});
});
```

- [ ] **Step 2: 运行组件测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/components/standards/OrdinaryPropertyEditor.test.ts`

Expected: FAIL with missing component。

- [ ] **Step 3: 实现八列表格和模态焦点行为**

表格严格为“属性名/作用域/类型/必填/默认值/枚举值/说明/删除”。文本类型枚举摘要灰显且不可聚焦；枚举模态支持增删改排序，新增项生成稳定 ID，关闭归还触发按钮焦点。删除被引用属性时不修改数组，向上抛出引用列表供可见错误显示。

- [ ] **Step 4: 覆盖默认值、全局名称和 CSV 回归**

测试枚举默认值必须在列表内、sheetset/sheet 同名提示、历史名称冲突以及 CSV 只创建普通 text/enum 属性且不生成派生关系。

- [ ] **Step 5: 运行组件测试并提交**

Run: `Set-Location web; npm run test:unit -- src/components/standards/OrdinaryPropertyEditor.test.ts`

Expected: PASS。

```powershell
git add web/src/components/standards
git commit -m "重构标准普通属性编辑器"
```

---

### Task 7: 实现派生属性表与映射编辑模态框

**Files:**
- Create: `web/src/components/standards/DerivedPropertyEditor.vue`
- Create: `web/src/components/standards/MappingPropertyDialog.vue`
- Create: `web/src/components/standards/DerivedPropertyEditor.test.ts`
- Delete: `web/src/components/standards/MappingTableEditor.vue`

**Interfaces:**
- Consumes: Task 5 的 mapping/composition 属性和 Task 6 的枚举项。
- Produces: 派生属性七列表格、合法源选择器、固定映射行和确认快照。

- [ ] **Step 1: 写入源约束和固定行测试**

在组件测试内定义 `documentWithClaimedSource(): DraftDocument`、`mountDerivedEditor(document): VueWrapper`、`sourceOptions(wrapper): string[]` 和 `mappingRows(wrapper): string[]`；选择器均从组件 `data-testid` 读取，不访问组件内部实例。

```ts
it("offers only unclaimed ordinary enum sources and fixes rows to enum ids", async () => {
  const wrapper = mountDerivedEditor(documentWithClaimedSource());
  await wrapper.get("[data-testid=edit-derived-prop-code]").trigger("click");
  expect(sourceOptions(wrapper)).toEqual(["prop-other-enum"]);
  expect(mappingRows(wrapper)).toEqual(["enum-a", "enum-b"]);
  expect(wrapper.find("[data-testid=add-mapping-row]").exists()).toBe(false);
});
```

- [ ] **Step 2: 运行组件测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/components/standards/DerivedPropertyEditor.test.ts`

Expected: FAIL with missing component。

- [ ] **Step 3: 实现派生表与映射模态框**

派生表列为“属性名/作用域/源属性摘要/类型/说明/编辑/删除”。映射源选择按作用域和唯一占用过滤；源值行来自枚举项且只读，不提供行增删。确认动作把当前有序 `(enum_item_id, value)` 写入 `confirmed_source_items`；枚举变化前保留已有 ID 对应目标并显示 warning。

- [ ] **Step 4: 覆盖新增、删除、改名与目标重复**

测试枚举新增产生空目标 error、删除移除孤儿行、改名保留目标、重排跟随源列表、重复目标允许、空目标阻止发布但草稿仍可保存。

- [ ] **Step 5: 运行组件测试并提交**

Run: `Set-Location web; npm run test:unit -- src/components/standards/DerivedPropertyEditor.test.ts`

Expected: PASS。

```powershell
git add web/src/components/standards
git commit -m "实现标准派生属性与映射编辑"
```

---

### Task 8: 共用令牌编辑器并实现组合属性与 DWG 命名

**Files:**
- Create: `web/src/components/standards/TokenExpressionEditor.vue`
- Create: `web/src/components/standards/CompositionPropertyDialog.vue`
- Create: `web/src/components/standards/DwgNamingEditor.vue`
- Create: `web/src/components/standards/TokenExpressionEditor.test.ts`
- Delete: `web/src/components/standards/CompositionEditor.vue`

**Interfaces:**
- Consumes: `DraftSegment[]`、按上下文过滤的字段令牌和示例值。
- Produces: 左字段浏览器、右单行编辑框、下预览的共享编辑原语。

- [ ] **Step 1: 写入字段可见性和令牌编辑测试**

```ts
it("limits sheet composition and dwg naming to their own field sets", () => {
  expect(compositionFields(document, "sheet")).toEqual(["prop-set", "prop-sheet", "prop-map", "sheet.number", "sheet.title"]);
  expect(dwgNamingFields(document)).toEqual(["subset.scope", "subset.name", "subset.sequence", "prop-set", "prop-map", "prop-composed-set"]);
});
```

- [ ] **Step 2: 运行组件测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/components/standards/TokenExpressionEditor.test.ts`

Expected: FAIL with missing helpers/components。

- [ ] **Step 3: 实现共享令牌编辑器**

字段点击后在当前光标处插入不可拆分 token，固定文字直接输入；序列化仍是结构化 `DraftSegment[]`。删除、左右移动和键盘导航保持令牌原子性，不解析用户输入的 `{...}` 为字段。模态焦点圈闭和关闭归还复用 `dialogFocus.ts`。

- [ ] **Step 4: 实现组合属性模态框和 DWG 命名分区**

组合根据作用域只显示普通/映射字段及 Sheet 的两个系统字段；DWG 命名显示三个 subset 字段和全部 sheetset 属性。标准预览固定使用 sequence=1、按编号位数构造 scope、名称“示例子集”、属性默认值/枚举首项/占位值，并明确标注“示例”；扩展名在编辑框外固定显示 `.dwg`。

- [ ] **Step 5: 覆盖非法文件名与 warning 定位**

测试 `.dwg` 重复输入、路径字符、设备名、尾随句点、240 字符和缺少 scope/sequence warning；前端只提示，发布仍以后端码为准。

- [ ] **Step 6: 运行组件测试并提交**

Run: `Set-Location web; npm run test:unit -- src/components/standards/TokenExpressionEditor.test.ts`

Expected: PASS。

```powershell
git add web/src/components/standards
git commit -m "统一组合属性与 DWG 命名编辑"
```

---

### Task 9: 重接标准编辑器、发布检查、语言包与 E2E

**Files:**
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/components/standards/StandardSectionNav.vue`
- Modify: `web/src/components/standards/StandardPublishReview.vue`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Modify: `web/src/i18n/hardcoded-allowlist.json`
- Modify: `web/tests/e2e/fixtures/standards.ts`
- Modify: `web/tests/e2e/standards-editor.spec.ts`
- Modify: `web/tests/e2e/standards-assets-publish.spec.ts`
- Modify: `web/tests/e2e/standards-visual-evidence.spec.ts`

**Interfaces:**
- Consumes: Tasks 5–8 的草稿模型和组件。
- Produces: 六分区编辑器、可保存未完成草稿、严格发布检查和用户可见完整流程。

- [ ] **Step 1: 先更新 E2E 夹具为新 Schema 并写失败流程**

```ts
test("普通属性到映射、组合和 DWG 命名形成单向流程", async ({page}) => {
  await openStandardDraft(page);
  await expect(page.getByTestId("standard-section-nav").getByRole("button")).toHaveText([
    "基本信息", "普通属性", "派生属性", "DWG 命名", "模板资产", "版本与发布",
  ]);
  await page.getByRole("button", {name: "普通属性"}).click();
  await page.getByTestId("edit-enum-prop-major").click();
  await page.getByTestId("enum-value-enum-gas").fill("城镇燃气");
  await page.getByRole("button", {name: "确定"}).click();
  await page.getByRole("button", {name: "派生属性"}).click();
  await page.getByTestId("edit-derived-prop-code").click();
  await page.getByTestId("mapping-target-enum-gas").fill("RQ");
  await page.getByRole("button", {name: "确认映射"}).click();
  await page.getByRole("button", {name: "DWG 命名"}).click();
  await expect(page.getByTestId("dwg-name-preview")).toContainText("RQ-001-003 示例子集.dwg");
});
```

- [ ] **Step 2: 运行标准 E2E 并确认失败**

Run: `Set-Location web; npx playwright test tests/e2e/standards-editor.spec.ts tests/e2e/standards-assets-publish.spec.ts --workers=1`

Expected: FAIL，页面仍为旧七分区和通用规则编辑器。

- [ ] **Step 3: 重接六分区和诊断跳转**

删除 `rules/mapping/composition` 分区，接入 `ordinary/derived/dwgNaming`。结构错误允许草稿保存；发布 error 禁用发布；映射待确认为 warning。发布问题跳转到属性行、派生编辑按钮/模态框或命名令牌，焦点落到真实可编辑控件。

- [ ] **Step 4: 更新中英文语言包和静态门禁**

删除不再使用的普通规则、批量粘贴映射和自由目标字段文案；新增普通/派生、枚举模态、映射确认、系统字段、文件名错误和示例预览文案。两种语言键集合必须完全一致，不用 allowlist 掩盖新界面硬编码文本。

- [ ] **Step 5: 覆盖关键 E2E 场景**

至少覆盖：全局跨作用域重名、引用删除阻断、枚举改名保留映射、源唯一性、组合字段范围、未完成草稿保存、发布 error/warning 区分、DWG 非法名和碰撞预检、900×768 无横向溢出、纯键盘插入令牌与模态焦点归还。

- [ ] **Step 6: 运行前端门禁并提交**

Run: `Set-Location web; npm run test:unit; npm run check:i18n; npm run check:ui; npm run build; npx playwright test tests/e2e/standards-editor.spec.ts tests/e2e/standards-assets-publish.spec.ts --workers=1`

Expected: 全部通过。

```powershell
git add web/src web/tests/e2e
git commit -m "重接标准属性与 DWG 命名界面"
```

---

### Task 10: 清理旧契约、更新文档并执行全量验证

**Files:**
- Modify: `web/src/api/openapi.json`
- Modify: `web/src/api/schema.d.ts`
- Modify: `.planning/plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `docs/dst-manager/guides/GUIDE-DM-007-official-standard-package-release.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Tasks 1–9 完整实现。
- Produces: 无旧规则残留的仓库契约、PLAN-DM-036 前置关系和可审计验证记录。

- [ ] **Step 1: 静态搜索并删除旧模型残留**

Run: `rg -n "StandardRule|DraftRule|ORDINARY_RULE_KINDS|COMPOSITION_RULE_KINDS|kind.*naming|derived\.dwg_name" src web tests`

Expected: 仅历史文档/变更说明允许命中；生产代码、测试和夹具零命中。

- [ ] **Step 2: 重新生成并核对 API 契约**

Run: `Set-Location web; npm run generate:api; npm run check:api`

Expected: PASS；生成文件与当前后端一致。

- [ ] **Step 3: 更新计划依赖与用户指南**

PLAN-DM-036 明确依赖 PLAN-DM-038，并消费 `render_dwg_filename/validate_dwg_filenames`；官方标准指南使用普通/派生属性和唯一 DWG 模板术语，不再描述通用规则。索引和 changelog 记录实际交付及 Schema v1 直接替换边界。

- [ ] **Step 4: 运行 Python 全量门禁**

Run: `uv run ruff check .`

Expected: PASS。

Run: `uv run pytest -q`

Expected: 0 failed；环境依赖跳过项逐项记录。

Run: `uv lock --check`

Expected: PASS。

- [ ] **Step 5: 运行 Web 全量门禁**

Run: `Set-Location web; npm run test:unit; npm run build; npm run test:e2e`

Expected: 0 failed；如存在配置允许的 flaky，记录用例名、首次失败和重跑结果。

- [ ] **Step 6: 检查改动边界并提交收口**

Run: `git diff --check`

Expected: PASS；`issues/`、私有样本、缓存、`web/dist` 和测试产物未暂存。

```powershell
git add .planning/plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md .planning/plans/dst-manager/PLAN-DM-038-standard-properties-and-dwg-naming-remediation.md .planning/plans/dst-manager/README.md docs/dst-manager/README.md docs/dst-manager/guides/GUIDE-DM-007-official-standard-package-release.md web/src/api/openapi.json web/src/api/schema.d.ts changelog.md
git commit -m "收口标准属性与命名整改"
```

## 实施顺序与退出条件

- Task 1–4 先建立可信后端契约，Task 5–9 再替换前端；不得用前端临时结构倒逼后端兼容旧规则。
- PLAN-DM-036 在 Task 10 更新依赖前不得开始实现，否则会基于即将删除的通用规则模型开发创建流程。
- 退出时新 Schema v1、草稿保存、发布门禁、属性求值和 DWG 命名必须由同一组稳定 ID 与诊断码贯通。
- 绑定标准工作区的持续属性约束和事务改名仍留在独立 Todo，不以本计划“顺手实现”。
