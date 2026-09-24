---
id: PLAN-DM-036
title: 标准驱动的新图纸集创建实施计划
status: active
owners:
- dst-manager
created: 2026-09-21
updated: 2026-09-24
related:
- RFC-INT-003
- PLAN-DM-035
- PLAN-DM-038
- SPEC-DM-017
- SPEC-DM-018
- ADR-DM-001
- ADR-DM-003
- ADR-DM-005
- SPEC-DM-008
- SPEC-DM-014
---

# 标准驱动的新图纸集创建实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已接受的四阶段 UI 规范，从已发布标准和按组输入创建完整 DST/DWG 项目，成功后直接进入普通 Manager 工作区。

**Architecture:** 创建草稿是应用数据目录中的可恢复 JSON，不是第二个项目数据库；一行图纸组展开为一个主 DWG 和多张 Sheet。领域层把标准、完整普通属性输入及编号配置编译成不可变 `CreationPlan`；执行层以 Manager 内置的受控最小 AcSm 骨架和标准包 DWG 资产在隔离 attempt 中生成成果，再经可恢复事务发布到新目录。前端只编辑草稿、导入 XLSX、展示后端按组预览和观察任务。

**Tech Stack:** Python 3.12、FastAPI、lxml、openpyxl、现有 Core Console/Worker、Vue 3、TypeScript、Vite、Playwright、pytest。

**Spec:** [SPEC-DM-018（已接受的 UI/导入/预览契约）](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md)、[SPEC-DM-017（属性与命名）](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md)、[RFC-INT-003（创建与内置骨架）](../../../docs/integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)。实施时对照 [四阶段 HTML Demo](../../../docs/dst-manager/mockups/SPEC-DM-018-creation-demo.html)；Demo 是模拟数据，不是权威求值器。

## Global Constraints

- PLAN-DM-035 与 PLAN-DM-038 已完成；本计划只消费 SPEC-DM-017 Schema v1（普通/派生属性、唯一全局 DWG 命名），不得复活旧顶层 `rules` 或 Builder 模型。
- 只使用已发布且依赖、模板文件可用的标准；标准资产只含 `base-template` 与 `layout-template`，不得为内置 DST 骨架扩展标准包资产类型。
- 用户给出的 legacy PowerShell XML 只作候选节点清单；不得执行其中的 PowerShell、保留示例路径/名称或直接复制 GUID。内置骨架必须作为受版本控制的静态资产或构造器，经当前 AcSm 契约、DST 往返和双版本 AutoCAD 验证。
- 一个子集创建一个主 DWG，每张图纸对应其中一个布局。
- 创建阶段同一图纸组的全部 Sheet 继承相同普通 `sheet` 输入、基础模板、布局模板和图幅；逐张差异化仅在创建后的普通工作区编辑。
- 标准 `numbering.digits/start` 决定图号位数与起点；标题后缀和 `unnumbered_subset_keywords` 取创建时有效设置并随项目保存。复用现有编辑派生原语，不复制另一套算法；不编号组全组图号为补零的 `0` 且不占号。
- `required` 只在有实际项目值的创建预览/执行时强制；标准可以没有必填属性默认值。普通输入必须按 `property_id` 完整提供键，显式空串与遗漏键不可混同；任何派生失败都阻止创建，不写伪结果。
- UI 选择已存在上级目录与可编辑目录名（默认「新建项目」）；XLSX 输入含最终目录名的完整路径，两者存入同一 `target_path` 字段，绝不由「项目名称」等自定义属性推断。
- `AcSmSheetSet.Name` 由最终项目目录名写入，不设第二个名称输入，也不取任何自定义属性；创建后可在普通工作区受控修改。
- 目标只能是尚不存在的新目录或空目录；不得覆盖或合并已有工程。
- 预览不启动 AutoCAD；正式执行只使用固定 Worker 协议和标准包内资产。
- 创建失败不得在目标留下半成品；重试使用新 attempt。
- F3/F4 已由独立小修处理；F5 归[独立 Todo](../../todos/dst-manager/2026-09-23-standard-name-casefold-parity.md)。本计划不重复实现标准编辑器修复，不把 F5 设为创建前置。审查备忘仅供核对 F2：[PLAN-DM-038 遗留发现](../../memos/dst-manager/2026-09-23-plan-dm-038-code-review-findings.md)。

## Review Focus

- 宿主漏传普通属性键必须报诊断且不写派生结果；显式空串仍遵循“可选源为空”的既有规则。Task 3 覆盖。
- XLSX 粘贴可绕过 Data Validation、隐藏元数据可篡改、固定表头可与属性名碰撞；解析须按稳定 ID 定位，非法整批拒绝且原草稿不变。Task 2/4 覆盖。
- 不编号组不能占用连续图号；改变关键字或后缀后旧预览不能执行。Task 3/4 覆盖。
- 标准/资产、草稿、目标目录在预览后变化，或新目录发布中途失败，必须拒绝或恢复到发布前状态。Task 4/6 覆盖。
- CAD 成功但 DST 引用、Handle、布局集合或内置骨架验证失败时不得发布。Task 5/6 覆盖。

---

### Task 1: 建立按图纸组保存的可恢复创建草稿

**Files:**
- Create: `src/dst_manager/domain/creation.py`（`CreationDraft`/`CreationGroupInput`，只含输入与稳定身份）
- Create: `src/dst_manager/infrastructure/creation_drafts.py`
- Create: `src/dst_manager/application/creation_drafts.py`
- Create: `tests/unit/test_creation_drafts.py`
- Modify: `src/dst_manager/application/service.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: PLAN-DM-035 的 `StandardStore` 与 PLAN-DM-038 的 `DrawingStandard`（Schema v1）；不在草稿保存时运行派生、编号或 DWG 命名。
- Produces: `CreationDraft(id, standard_id, standard_version, revision, step, target_path, sheetset_values, groups)`、`CreationGroupInput(group_id, created_order, title, count, base_asset_id, layout_asset_id, paper_layout, sheet_values)`、`CreationAssetOption(asset_id, kind, label, layouts)`；`CreationDraftOperations.create/get/save/delete`。`sheetset_values`/`sheet_values` 只存可输入普通属性的 `property_id → str`，不保存派生结果或逐张 Sheet 输入；`created_order` 单调递增且重排不改变它，用于“复制最近创建的组”。

- [ ] **Step 1: 写入标准固定与崩溃恢复测试**

```python
from dataclasses import replace

def test_creation_draft_pins_published_standard(tmp_path, service, published_standard) -> None:
    draft = service.create_creation_draft(published_standard.identity)
    restored = service.get_creation_draft(draft.id)
    assert (restored.standard_id, restored.standard_version) == published_standard.identity
    assert restored.revision == 1
    assert restored.target_path == ""
    assert restored.groups == ()


def test_save_uses_optimistic_revision(service, draft) -> None:
    service.save_creation_draft(draft.id, expected_revision=1, value=draft)
    with pytest.raises(ApplicationError, match="CREATION_DRAFT_CONFLICT"):
        service.save_creation_draft(draft.id, expected_revision=1, value=draft)


def test_explicitly_cleared_value_survives_restore(service, draft) -> None:
    value = replace(draft, sheetset_values={**draft.sheetset_values, "prop-name": ""})
    saved = service.save_creation_draft(draft.id, expected_revision=1, value=value)
    assert service.get_creation_draft(draft.id).sheetset_values["prop-name"] == ""
    assert saved.revision == 2
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_creation_drafts.py -q`

Expected: FAIL，创建草稿模块不存在。

- [ ] **Step 3: 实现原子 JSON 草稿存储**

草稿根使用 Manager 应用数据目录的 `creation-drafts/<uuid>/`；保存采用临时文件加 `os.replace`，记录 `schema_version`、标准身份、修订号、当前阶段、完整最终 `target_path` 与按序图纸组，不保存可执行预览。初建时对每个普通属性仅应用一次标准默认值；恢复和保存时不得重新回填用户主动清空的值。拒绝来自请求的派生字段、任意模板路径和逐张 Sheet 输入。组顺序由数组顺序决定，`group_id` 用于稳定定位而非图号。

- [ ] **Step 4: 覆盖损坏隔离与标准缺失**

Run: `uv run pytest tests/unit/test_creation_drafts.py -q`

Expected: 损坏 JSON 隔离并返回 `CREATION_DRAFT_CORRUPT`；标准版本缺失返回 `CREATION_STANDARD_MISSING`；草稿恢复后旧预览不存在，用户明确空值不回填。每次提交组新增、删除、排序或字段修改均递增修订并失效旧预览。

- [ ] **Step 5: 提交创建草稿**

```powershell
git add src/dst_manager/domain/creation.py src/dst_manager/infrastructure/creation_drafts.py src/dst_manager/application/creation_drafts.py src/dst_manager/application/service.py tests/unit/test_creation_drafts.py changelog.md
git commit -m "建立可恢复图纸集创建草稿"
```

### Task 2: 实现双工作表 XLSX 模板与全量结构导入

**Files:**
- Create: `src/dst_manager/infrastructure/creation_xlsx.py`
- Create: `src/dst_manager/application/creation_import.py`
- Create: `tests/unit/test_creation_xlsx_template.py`、`tests/unit/test_creation_xlsx_import.py`、`tests/unit/test_creation_xlsx_rows.py`、`tests/unit/creation_xlsx_fixtures.py`（实施时按容量契约拆分，原单文件 762 行超 AGENTS.md 软上限）
- Modify: `src/dst_manager/domain/creation.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `DrawingStandard`、Task 1 的 `CreationAssetOption` 和当前草稿固定标准身份。
- Produces: `build_creation_template(standard: DrawingStandard, asset_options: tuple[CreationAssetOption, ...]) -> bytes`、`parse_creation_workbook(data: bytes, standard: DrawingStandard, asset_options: tuple[CreationAssetOption, ...]) -> CreationImportResult`；结果只返回完整最终路径、sheetset 普通值、按行序排列的图纸组及带工作表/行/列的诊断，不直接写草稿。资产用户标签从受控包内文件名/相对路径生成并在同类候选中唯一，隐藏元数据映射稳定 ID，不在业务单元格显示 ID。

- [ ] **Step 1: 写入双表模板与绕过验证测试**

```python
def test_template_has_legacy_style_two_visible_sheets_and_validation(standard, options) -> None:
    workbook = load_workbook(BytesIO(build_creation_template(standard, options)))
    assert [sheet.title for sheet in workbook if sheet.sheet_state == "visible"] == ["SheetSet", "Sheet"]
    assert workbook["Sheet"].cell(1, 1).value == "图名"
    assert [workbook["Sheet"].cell(1, col).value for col in range(1, 6)] == [
        "图名", "张数", "基础模板", "布局模板", "图幅"
    ]
    assert "派生属性" not in [cell.value for cell in workbook["Sheet"][1]]
    assert len(workbook["Sheet"].data_validations.dataValidation) >= 3


def test_fixed_header_collision_is_disambiguated_by_stable_property_id(standard_with_sheet_property_named_count, options) -> None:
    workbook = load_workbook(BytesIO(build_creation_template(standard_with_sheet_property_named_count, options)))
    headers = [cell.value for cell in workbook["Sheet"][1]]
    assert headers[1] == "张数"
    assert headers.count("张数") == 1
    assert len(headers) == len(set(headers))


def test_pasted_invalid_enum_rejects_entire_workbook(standard, options) -> None:
    result = parse_creation_workbook(workbook_with_invalid_enum(), standard, options)
    assert result.value is None
    assert (result.diagnostics[0].sheet, result.diagnostics[0].row) == ("Sheet", 2)


def test_xlsx_final_path_and_group_count_round_trip(standard, options) -> None:
    result = parse_creation_workbook(valid_group_workbook(path=r"C:\Projects\道路工程", count=3), standard, options)
    assert result.value.target_path == r"C:\Projects\道路工程"
    assert len(result.value.groups) == 1
    assert result.value.groups[0].count == 3
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_creation_xlsx_template.py tests/unit/test_creation_xlsx_import.py tests/unit/test_creation_xlsx_rows.py -q`

Expected: FAIL，XLSX 模块不存在。

- [ ] **Step 3: 实现模板生成和严格解析**

只生成 `SheetSet`（A 属性名/B 输入值，另有「项目保存路径」完整最终路径）与 `Sheet`（每行一组：图名、张数、基础模板、布局模板、图幅、其他普通 `sheet` 属性）两个可见工作表；枚举和三类模板/布局选项加 Data Validation。属性名与固定表头同名时给动态列加可读限定语，解析仍只按技术表的稳定 `property_id` 映射。隐藏技术表保存模板版本、精确标准身份、字段 `property_id` 和资产 `asset_id`；不得在可见表写派生属性、业务公式或逐张 Sheet 行。解析按固定标准身份与技术元数据解析可见列，拒绝公式、外部链接、未知/重复/缺失表头、非法隐藏映射、无效枚举/资产/布局、重复图名、非法张数、越界/危险路径和受控规模超限；单元格 Data Validation 不作信任边界。`Sheet` 行序即组序，绝不把张数行解释为逐张属性输入。

- [ ] **Step 4: 运行 XLSX 安全与往返测试**

Run: `uv run pytest tests/unit/test_creation_xlsx_template.py tests/unit/test_creation_xlsx_import.py tests/unit/test_creation_xlsx_rows.py -q`

Expected: 合法工作簿往返且仅有两张可见表；公式单元格、隐藏元数据篡改、非法枚举、失效资产、模板/图幅不匹配和超限行数均返回稳定工作表/行/列诊断，不产生部分结果。与 UI 输入相同的最终路径和图纸组得到同一草稿形态。

- [ ] **Step 5: 提交结构导入**

```powershell
git add src/dst_manager/infrastructure/creation_xlsx*.py src/dst_manager/application/creation_import*.py src/dst_manager/domain/creation.py tests/unit/test_creation_xlsx_*.py tests/unit/creation_xlsx_fixtures.py tests/unit/conftest.py changelog.md
git commit -m "实现标准化 XLSX 结构导入"
```

### Task 3: 修复缺键传播并生成确定性 CreationPlan

**Files:**
- Create: `src/dst_manager/domain/creation_planning.py`
- Create: `tests/unit/test_creation_planning.py`
- Modify: `src/dst_manager/domain/standard_rules.py`
- Modify: `tests/unit/test_standard_rules.py`
- Modify: `src/dst_manager/domain/editing.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `CreationDraft`、`DrawingStandard`/`CompiledProperties`、现有 `SuffixOptions`、`render_dwg_filename`/`validate_dwg_filenames` 和编辑域标题/编号原语。
- Produces: `create_creation_plan(draft: CreationDraft, standard: DrawingStandard, suffix_options: SuffixOptions) -> CreationPlan`；计划含最终 DST/DWG/布局、完整逐张 `sheet.number/title`、两级普通与派生属性、每组模板/图幅、按组预览投影、诊断和可供应用层绑定外部状态的确定性内容摘要。`CreationPlan` 不读文件系统、不启动 CAD。

- [ ] **Step 1: 写入 F2 缺键、必填和按组派生失败测试**

```python
def test_mapping_missing_key_does_not_become_empty_result(compiled) -> None:
    missing = evaluate_standard_properties(compiled, {}, {})
    assert "prop-code" not in missing.values
    assert "STANDARD_DERIVED_UPSTREAM_INVALID" in [item.code for item in missing.diagnostics]
    explicit_empty = evaluate_standard_properties(compiled, {"prop-major": ""}, {})
    assert explicit_empty.values["prop-code"] == ""


def test_required_sheet_value_blocks_every_expanded_sheet(draft, standard, options) -> None:
    plan = create_creation_plan(draft, standard, options)  # 夹具含 3 张且 prop-required 被明确清空
    assert plan.has_errors
    assert [(item.group_id, item.property_id) for item in plan.diagnostics if item.code == "CREATION_REQUIRED_VALUE_MISSING"] == [
        (draft.groups[0].group_id, "prop-required")
    ]
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_creation_planning.py -q`

Expected: 缺键用例先失败（当前 `standard_rules.py` 把漏传键当空值）；创建计划用例因模块不存在失败。

- [ ] **Step 3: 修复求值器并抽取可复用编号原语**

在映射源与组合普通属性令牌处先判断键是否存在：缺键报 `STANDARD_DERIVED_UPSTREAM_INVALID`，不写该派生键，阻断下游；显式 `""` 保持可选空值的既有语义。`required` 非空只在创建实际值门禁判断，不改标准发布门禁。把 `derive_document_structure` 中与既有 DOM 无关的连续编号/不编号原语抽为同层纯函数，编辑和创建共同调用；标题沿用 `derive_group_titles`/`format_sheet_title`，布局名沿用现有派生与碰撞校验，不复制规则。

- [ ] **Step 4: 实现计划器与按组预览投影**

要求 `sheetset` 与每组 `sheet` 普通值已经是完整的 `property_id` 字典；缺键报创建输入诊断，不在求值时临时补空串，绝不从旧派生值回填。验证必填非空、枚举合法和组图名/张数/资产声明。按标准 `numbering.start/digits` 与有效关键字派生每张图号，命中关键字的组统一为补零 `0` 且不占号；每张图纸再用自己的 `sheet.number/title` 求 `sheet` 派生属性。`sheetset` 派生结果用于全局 DWG 命名，失败或冲突使计划阻断，不得使用半成品文件名。预览每组一行：图纸范围单值/首末值、标题紧凑范围、张数、真实文件名、模板/图幅、其他 `sheet` 属性摘要；属性不一致时返回首张实际值与完整逐张列表供前端「…」模态使用。内容摘要覆盖标准身份、草稿修订、有效编号配置和全部派生输出，文件/资产/目标状态由 Task 4 应用层另行绑定。

- [ ] **Step 5: 覆盖不编号、命名碰撞与领域回归**

```python
def test_unnumbered_group_is_zero_and_does_not_advance_numbering() -> None:
    plan = create_creation_plan(draft_with_cover_and_groups((2, 3, 2)), standard_with_digits(2), options_with_keyword("封面"))
    assert [group.number_range for group in plan.groups] == ["00", "01-03", "04-05"]
    assert [sheet.number for sheet in plan.groups[0].sheets] == ["00", "00"]


def test_group_preview_keeps_first_value_and_full_sheet_detail() -> None:
    plan = create_creation_plan(draft_with_sheet_number_composition(), standard_with_sheet_number_composition(), options())
    assert plan.groups[0].property_cells["prop-label"].first_value == "平面图-01"
    assert [row.value for row in plan.groups[0].property_cells["prop-label"].sheets] == ["平面图-01", "平面图-02"]
```

Run: `uv run pytest tests/unit/test_standard_rules.py tests/unit/test_creation_planning.py tests/unit/test_unnumbered_subsets.py tests/unit/test_v021_editing.py tests/unit/test_standard_naming.py -q`

Expected: 缺键阻断、显式空串仍可求值；不编号组与后续范围正确；同名组、空组、重复布局名、DWG 文件名冲突或必填/枚举非法均诊断且不可执行；现有编辑结果逐字保持。

- [ ] **Step 6: 提交领域计划器与 F2 修复**

```powershell
git add src/dst_manager/domain/standard_rules.py src/dst_manager/domain/editing.py src/dst_manager/domain/creation_planning.py tests/unit/test_standard_rules.py tests/unit/test_creation_planning.py changelog.md
git commit -m "补齐创建求值缺键门禁并复用编号派生"
```

### Task 4: 暴露创建草稿、XLSX 与权威预览 API

**Files:**
- Create: `src/dst_manager/application/creation.py`
- Create: `src/dst_manager/application/creation_assets.py`（受控标准资产解析与身份快照）
- Create: `src/dst_manager/interfaces/creation_contracts.py`
- Create: `src/dst_manager/interfaces/creation_api.py`
- Create: `tests/integration/test_creation_api.py`
- Modify: `src/dst_manager/interfaces/api.py`
- Modify: `src/dst_manager/interfaces/responses.py`
- Modify: `web/src/api/openapi.json`
- Modify: `web/src/api/schema.d.ts`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `CreationDraftOperations`、`build_creation_template`/`parse_creation_workbook`、`create_creation_plan()`、`StandardStore`、当前设置与标准资产检查结果。
- Produces: `/api/creation-drafts` CRUD、`/{id}/xlsx-template`、`/{id}/xlsx-import` 与 `/{id}/preview`；`CreationOperations.preview`。预览响应带按组表格数据、逐张属性模态明细、定位诊断、`preview_digest`。`/{id}/execute` 由 Task 6 在创建任务持久化后接入，不在本任务暴露半成品执行端点。

- [ ] **Step 1: 写入全量导入、预览身份和路径 API 测试**

```python
def test_preview_digest_changes_after_draft_edit(client, creation_draft) -> None:
    preview = client.post(f"/api/creation-drafts/{creation_draft.id}/preview").json()
    update_creation_draft(client, creation_draft.id)
    updated = client.post(f"/api/creation-drafts/{creation_draft.id}/preview").json()
    assert updated["preview_digest"] != preview["preview_digest"]


def test_invalid_import_keeps_draft_unchanged(client, creation_draft, invalid_xlsx) -> None:
    before = client.get(f"/api/creation-drafts/{creation_draft.id}").json()
    response = client.post(f"/api/creation-drafts/{creation_draft.id}/xlsx-import", files={"file": invalid_xlsx})
    assert response.status_code == 422
    assert client.get(f"/api/creation-drafts/{creation_draft.id}").json() == before


def test_nonempty_target_blocks_preview(client, creation_draft, nonempty_target) -> None:
    response = client.post(f"/api/creation-drafts/{creation_draft.id}/preview")
    assert response.status_code == 422
    assert response.json()["code"] == "CREATION_TARGET_NOT_EMPTY"
```

- [ ] **Step 2: 运行 API 测试并确认失败**

Run: `uv run pytest tests/integration/test_creation_api.py -q`

Expected: FAIL，路由不存在。

- [ ] **Step 3: 实现独立创建路由和应用编排**

接口层不解析 XLSX、不执行命名或文件操作。应用层只列出已发布且依赖、受控资产可用的标准；选择时固定版本。UI 上级目录+可编辑目录名在 API 前合成为完整 `target_path`；XLSX 路径直接写同一字段，均按现有路径安全规则检查，不从自定义属性推断。导入先完整解析、校验标准身份与期望草稿修订，再一次性保存新项目信息及全部组；失败保持原 JSON/修订。预览重新加载标准、当前设置、草稿与目标状态，验证资产文件/布局声明及内容哈希；摘要绑定标准文档、草稿修订、有效设置、资产哈希、目标状态和领域计划内容。非空目标返回 `CREATION_TARGET_NOT_EMPTY`；预览全过程不得启动 CAD。

- [ ] **Step 4: 生成 OpenAPI 并运行契约测试**

Run（逐行执行）：

```powershell
uv run python scripts/export_openapi.py
uv run pytest tests/integration/test_creation_api.py -q
Set-Location web
npm run check:api
Set-Location ..
```

Expected: API 契约生成与集成测试全部通过；已发布但缺依赖/模板文件的标准不可选且有原因；导入取消由 UI 处理，服务端非法导入零变更；路径、标准、设置、资产或草稿变化产生不同摘要，预览全过程不启动 CAD。

- [ ] **Step 5: 提交创建 API**

```powershell
git add src/dst_manager/application/creation.py src/dst_manager/application/creation_assets.py src/dst_manager/interfaces/creation_contracts.py src/dst_manager/interfaces/creation_api.py src/dst_manager/interfaces/api.py src/dst_manager/interfaces/responses.py web/src/api/openapi.json web/src/api/schema.d.ts tests/integration/test_creation_api.py changelog.md
git commit -m "开放图纸集创建草稿与预览 API"
```

### Task 5: 验证内置 DST 骨架并在隔离区生成候选成果

**Files:**
- Create: `src/dst_manager/application/creation_job.py`
- Create: `src/dst_manager/infrastructure/acsm_xml/creation.py`
- Create: `src/dst_manager/infrastructure/acsm_xml/assets/minimal_sheetset.xml`（唯一受版本控制的权威骨架；实例化时用 DOM 写入动态值）
- Create: `tests/unit/test_creation_acsm.py`
- Create: `tests/integration/test_creation_job.py`
- Modify: `src/dst_manager/infrastructure/autocad/worker.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: 无阻断诊断的 `CreationPlan`、Task 4 固定身份的标准包 DWG 资产与现有 Core Console/Worker 固定命令能力。
- Produces: `build_minimal_acsm(plan: CreationPlan) -> AcsmDocument`、`CreationJobRunner.stage(job_id, attempt, plan) -> CreationCandidate`；候选物包含 DST、每组主 DWG、最终布局/Handle 清单和校验报告，全部位于独立 attempt 暂存目录，不写目标项目目录。

- [ ] **Step 1: 写入骨架契约与重复构建测试**

```python
from pathlib import Path


def test_minimal_acsm_has_fresh_ids_and_no_legacy_placeholders(plan) -> None:
    first = build_minimal_acsm(plan)
    second = build_minimal_acsm(plan)
    assert first.repair_report.status == "VALID"
    assert first.validate() == []
    assert set(first.root.xpath("//@ID")).isdisjoint(set(second.root.xpath("//@ID")))
    assert b"SheetSet Name" not in first.to_bytes()
    assert "工程路径" not in first.to_bytes().decode("utf-8")
    assert first.root.xpath("//*[local-name()='AcSmSheetSet']/*[local-name()='AcSmProp' and @propname='Name']/text()") == [
        Path(plan.target_path).name
    ]


def test_staged_candidate_has_one_dwg_per_group_and_all_layout_handles(runner, plan) -> None:
    candidate = runner.stage("job-1", 1, plan)
    assert len(candidate.dwgs) == len(plan.groups)
    assert len(candidate.handles) == sum(group.count for group in plan.groups)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_creation_acsm.py tests/integration/test_creation_job.py -q`

Expected: FAIL，内置骨架构造器和候选生成器不存在。

- [ ] **Step 3: 核定 legacy 候选骨架并实现安全构造**

逐节点对照用户提供的 legacy XML、现有 `acsm_xml/contract.py`/XSD 和已通过官方 Sheet Set Manager 验收的最小 DST。保留确为 AcSm 协议所需的 `clsid`、`vt`、节点顺序与精确节点名（例如看似拼写异常的名称也必须以实测为准）；删除示例 `Name`/`Desc`/`NewSheetLocation` 等硬编码业务值，建立唯一受版本控制的内置骨架。每次实例化生成新的数据库指纹、根/子对象 AcSm ID，`AcSmSheetSet.Name` 写最终项目目录名，另写项目路径、普通与派生文本属性、`DSTManager.Standard` 与有效编号配置保留属性；按计划创建子集/Sheet、布局引用。禁止字符串替换 XML 或执行 legacy PowerShell，使用受控 DOM 构造、当前加载器及编码器往返校验。

- [ ] **Step 4: 实现 CAD 暂存工作单元及候选校验**

每个图纸组从已验证基础 DWG 复制一个主 DWG；Worker 以固定请求从选中布局模板导入选中图幅并为组内每张 Sheet 创建计划布局，回传完整布局名与非零唯一 Handle；若布局模板的真实布局集合与标准声明不符，整个任务失败。将最终相对/绝对 DWG 引用及 Handle 写入内置骨架生成的 AcSm DOM；运行契约/XSD/语义校验、DST 编码→解码往返、DWG 实际布局集合与计划逐项比对。任何一步失败只留隔离 attempt 日志，不调用发布器。

- [ ] **Step 5: 运行无 CAD 回归与双版本真实资格测试**

Run: `uv run pytest tests/unit/test_creation_acsm.py tests/integration/test_creation_job.py tests/unit/test_acsm_contract.py -q`

Expected: 模拟 Worker 下生成完整候选且任何非法 Handle/布局/引用均拒绝；现有 AcSm 契约回归通过。具备本机 AutoCAD 2016/2020 时分别独立打开真实候选 DWG/DST，记录官方 Sheet Set Manager 的子集、图号、标题、布局与自定义属性结果；缺环境时明确记录为尚未满足真实资格门禁，不以模拟测试宣称双版本通过。

- [ ] **Step 6: 提交内置骨架与候选生成**

```powershell
git add src/dst_manager/application/creation_job.py src/dst_manager/infrastructure/acsm_xml/creation.py src/dst_manager/infrastructure/acsm_xml/assets/minimal_sheetset.xml src/dst_manager/infrastructure/autocad/worker.py tests/unit/test_creation_acsm.py tests/integration/test_creation_job.py changelog.md
git commit -m "建立内置 DST 骨架与隔离候选生成"
```

### Task 6: 为新目录建立可恢复发布事务与创建任务状态

**Files:**
- Create: `src/dst_manager/infrastructure/filesystem/project_publisher.py`（只负责新项目的目标占有、日志、发布与回滚）
- Create: `tests/unit/test_project_publisher.py`
- Modify: `src/dst_manager/infrastructure/filesystem/publish_recovery.py`
- Modify: `src/dst_manager/infrastructure/persistence/database.py`
- Create: `migrations/versions/0007_creation_jobs.py`（当前 head 为 `0006_dm020_extension_platform`；执行前若 head 已变，先查新 head 并按其后继分配 revision，绝不覆盖已有迁移）
- Modify: `src/dst_manager/application/creation_job.py`
- Modify: `src/dst_manager/application/creation.py`
- Modify: `src/dst_manager/interfaces/creation_api.py`
- Modify: `src/dst_manager/interfaces/creation_contracts.py`
- Modify: `web/src/api/openapi.json`
- Modify: `web/src/api/schema.d.ts`
- Modify: `tests/integration/test_creation_api.py`
- Modify: `tests/integration/test_creation_job.py`
- Modify: `tests/unit/test_database.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 5 的已验证 `CreationCandidate` 与 Task 4 的预览身份快照。
- Produces: `ProjectPublisher.publish_new_project(candidate: CreationCandidate, target: Path, job_id: str, attempt: int) -> PublishedProject`；`CreationJobRunner.run(job_id, attempt, plan)` 在 Task 5 暂存成功后调用发布器。`POST /api/creation-drafts/{id}/execute` 只接受 `preview_digest`，重新构建 Task 4 的完整预览身份后才能入队；创建任务在普通工作区尚不存在时仍能记录状态、进度、SSE 事件与失败诊断。

- [ ] **Step 1: 写入目标原状态与故障注入测试**

```python
@pytest.mark.parametrize("target_existed", [False, True])
def test_publish_failure_restores_original_target(tmp_path, candidate, fault_injector, target_existed) -> None:
    target = tmp_path / "new-project"
    if target_existed:
        target.mkdir()
    fault_injector.fail_after_replace(1)
    with pytest.raises(ProjectPublishError):
        publish_candidate(candidate, target, fault_injector)
    assert target.exists() is target_existed
    if target_existed:
        assert list(target.iterdir()) == []


def test_nonempty_target_is_not_touched(tmp_path, candidate) -> None:
    target = tmp_path / "new-project"
    target.mkdir()
    marker = target / "existing.txt"
    marker.write_text("保留", encoding="utf-8")
    with pytest.raises(ProjectPublishError, match="CREATION_TARGET_NOT_EMPTY"):
        publish_candidate(candidate, target)
    assert marker.read_text(encoding="utf-8") == "保留"


def test_execute_rejects_stale_preview(client, creation_draft, preview) -> None:
    update_creation_draft(client, creation_draft.id)
    response = client.post(
        f"/api/creation-drafts/{creation_draft.id}/execute",
        json={"preview_digest": preview.digest},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CREATION_PREVIEW_STALE"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/test_project_publisher.py tests/integration/test_creation_job.py -q`

Expected: FAIL，创建专用事务及无工作区任务登记尚不存在。

- [ ] **Step 3: 实现新目录的持久发布日志与数据库迁移**

复用现有发布原语与日志格式中可复用的部分，不绕过锁、暂存、校验和启动恢复。执行路由只接收草稿 ID/`preview_digest`；执行前重新加载标准、草稿、目标与设置/资产快照并重算摘要，漂移报 `CREATION_PREVIEW_STALE`，禁止客户端提供派生输出。创建日志先放 Manager 应用数据目录并记录目标在发布前是“不存在”还是“已存在且为空”、目标身份、候选清单/哈希、job_id/attempt 与每个已提交文件；首次创建目录后只可操作本次占有的精确路径。为 `jobs` 增加创建前可空 `workspace_id` 与稳定 `creation_draft_id`（或等价独立关联，保持既有普通任务契约），用下一有效 Alembic revision 迁移并验证全新库/既有库升级。发布成功后才建立工作区关联。不得使用宽泛递归删除；恢复时若目标出现不属于本次清单的外部文件，停止自动清理、保留日志并标记 `NEEDS_REVIEW`。

- [ ] **Step 4: 实现失败回滚、启动恢复与重试新 attempt**

新建目标中途失败时，只回滚本次已创建且身份匹配的文件，随后恢复“目录不存在”或“目录存在且为空”的精确原状态；空目录不误删，外来内容不误删。分别注入第一个、中间、最后一个文件失败及 `PREPARED`/`PUBLISHING` 进程中断；启动恢复根据持久日志幂等处理。重试创建严格使用新 attempt 目录，不重用状态不明的 CAD 成果；日志和修订证据保留。

- [ ] **Step 5: 运行迁移和事务回归**

Run（逐行执行）：

```powershell
uv run python scripts/export_openapi.py
uv run pytest tests/unit/test_project_publisher.py tests/integration/test_creation_job.py tests/integration/test_creation_api.py tests/unit/test_database.py -q
Set-Location web
npm run check:api
Set-Location ..
```

迁移另在由 `DST_MANAGER_DATABASE_URL` 指向的全新临时数据库与既有库升级夹具各执行 `uv run alembic upgrade head`，不得对用户本地数据库直接试跑。

Expected: 迁移、API 契约与测试通过；旧摘要执行 409；非空目标零改动；所有故障点与启动恢复返回发布前状态或安全 `NEEDS_REVIEW`，绝不留下可被误报成功的半成品。

- [ ] **Step 6: 提交创建事务**

```powershell
git add src/dst_manager/infrastructure/filesystem/project_publisher.py src/dst_manager/infrastructure/filesystem/publish_recovery.py src/dst_manager/infrastructure/persistence/database.py src/dst_manager/application/creation_job.py src/dst_manager/application/creation.py src/dst_manager/interfaces/creation_api.py src/dst_manager/interfaces/creation_contracts.py web/src/api/openapi.json web/src/api/schema.d.ts migrations/versions tests/unit/test_project_publisher.py tests/integration/test_creation_job.py tests/integration/test_creation_api.py tests/unit/test_database.py changelog.md
git commit -m "建立新图纸集可恢复发布事务"
```

### Task 7: 建立初始修订并验证生成成果可打开

**Files:**
- Create: `tests/integration/test_created_project_opens.py`
- Create: `tests/system_autocad/test_creation_workflow.py`
- Modify: `src/dst_manager/application/creation_job.py`
- Modify: `src/dst_manager/infrastructure/filesystem/workspace.py`
- Modify: `src/dst_manager/application/revisions.py`
- Modify: `src/dst_manager/application/service.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 6 已提交的 `PublishedProject`、`open_workspace()`、固定版本 `StandardStore`。
- Produces: 创建成功响应中的 `workspace_id/revision_id/dst_path`，项目 `.dst-manager/standards/` 的精确已发布标准快照、有效配置快照和初始修订；未登记完成时任务不得成为普通 `SUCCEEDED`。

- [ ] **Step 1: 写入生成后打开与绑定断言**

```python
def test_created_project_opens_as_normal_workspace(service, completed_creation) -> None:
    workspace = service.get_workspace(completed_creation.workspace_id)
    assert workspace.document.custom_properties["DSTManager.Standard"] == "szmedi.gas@2.1.0"
    assert workspace.revision_id == completed_creation.revision_id
    assert (workspace.root / ".dst-manager/standards/szmedi.gas/2.1.0").is_dir()


def test_registration_failure_is_recoverable_not_successful(service, published_candidate, fault_injector) -> None:
    fault_injector.fail_before_workspace_registration()
    result = service.finish_creation(published_candidate)
    assert result.status == "NEEDS_REVIEW"
    assert result.workspace_id is None
```

- [ ] **Step 2: 运行集成测试并确认初始修订缺失**

Run: `uv run pytest tests/integration/test_created_project_opens.py -q`

Expected: FAIL，创建成功尚未登记普通工作区和初始修订。

- [ ] **Step 3: 在发布成功回调中登记工作区与初始修订**

只在项目文件完整发布后登记普通工作区、保存标准包绑定版本快照、有效编号配置和初始修订；对外成功响应必须在文件/SQLite/修订清单一致且 `open_workspace()` 可重新打开后产生。登记失败时保留已发布文件、日志与足够的续办身份，任务进入 `NEEDS_REVIEW`（或可恢复中间态）而不是普通成功；启动恢复可幂等补登记，不能再次生成或覆盖 DWG。标准库版本缺失时仍可由项目快照恢复语义。

- [ ] **Step 4: 运行集成与可选真实 CAD 系统测试**

Run: `uv run pytest tests/integration/test_created_project_opens.py -q`

具备环境时 Run: `$env:DST_MANAGER_RUN_AUTOCAD="1"; uv run pytest tests/system_autocad/test_creation_workflow.py -q`

Expected: 集成测试验证重新打开后属性物化、标准绑定、编号、DWG 引用、初始修订一致；真实 2016/2020 测试验证每组主 DWG、全部布局/Handle、DST 引用和官方 Sheet Set Manager 可打开性。缺少环境时记录跳过原因，不把系统验收标为通过。

- [ ] **Step 5: 提交创建闭环**

```powershell
git add src/dst_manager/application/creation_job.py src/dst_manager/application/service.py src/dst_manager/infrastructure/filesystem/workspace.py src/dst_manager/application/revisions.py tests/integration/test_created_project_opens.py tests/system_autocad/test_creation_workflow.py changelog.md
git commit -m "完成新图纸集创建与工作区接管"
```

### Task 8: 实现四阶段创建 UI 与按组输入

**Files:**
- Create: `web/src/views/CreateSheetSetView.vue`
- Create: `web/src/features/creation/store.ts`
- Create: `web/src/features/creation/types.ts`
- Create: `web/src/components/creation/StandardStep.vue`
- Create: `web/src/components/creation/ProjectStep.vue`
- Create: `web/src/components/creation/GroupsStep.vue`
- Create: `web/src/components/creation/GroupBatchDialog.vue`
- Create: `web/src/components/creation/XlsxImportDialog.vue`
- Create: `web/src/api/creation.ts`
- Create: `web/src/features/creation/store.test.ts`
- Create: `web/tests/e2e/create-sheetset-input.spec.ts`
- Create: `web/src/i18n/locales/zh-CN/creation.ts`
- Create: `web/src/i18n/locales/en-US/creation.ts`
- Modify: `web/src/i18n/index.ts`
- Modify: `web/src/views/WelcomeView.vue`
- Modify: `web/src/components/standards/StandardDetailPane.vue`
- Modify: `web/src/App.vue`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 4 的创建草稿、标准候选、XLSX 模板/导入 API，以及现有 `shell.select_folder` 桥和共享 UI 原语。
- Produces: 欢迎页“创建新图纸集”与标准详情“用于创建”入口、四阶段向导的前三阶段、可恢复输入/草稿、按组编辑和全量 XLSX 导入；第四阶段在 Task 9 接入，不新增“模板”或“执行”独立阶段。

- [ ] **Step 1: 写入草稿、复制与批量修改失败用例**

```ts
it("copies the most recently created group after reorder", async () => {
  const store = createCreationStore(fakeCreationApi());
  store.addGroup();
  const latest = store.addGroup();
  store.updateGroup(latest.group_id, {title: "平面图", count: 3});
  store.moveGroup(1, 0);
  const added = store.addGroup();
  expect(added.title).toBe("平面图");
  expect(added.count).toBe(3);
  expect(added.group_id).not.toBe(latest.group_id);
  expect(store.previewDigest).toBeNull();
});

it("applies an explicit clear only to selected groups", async () => {
  const store = createCreationStore(fakeCreationApi());
  store.batchUpdate(["group-1", "group-3"], "prop-stage", {kind: "clear"});
  expect(store.group("group-1").sheet_values["prop-stage"]).toBe("");
  expect(store.group("group-2").sheet_values["prop-stage"]).toBe("保留");
});
```

- [ ] **Step 2: 运行目标前端测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/creation/store.test.ts; npm run test:e2e -- create-sheetset-input.spec.ts; Set-Location ..`

Expected: FAIL，创建 UI 不存在。

- [ ] **Step 3: 实现标准选择、项目路径和图纸组表**

入口只列已发布且依赖/资产可用标准；标准详情入口固定版本并直接到项目信息。首版只保留四阶段导航，切换标准明确清除不兼容输入，退出/恢复/重新开始遵循草稿确认。项目属性动态显示普通文本/枚举、必填和默认值，派生只读或待计算。项目路径复用 `shell.select_folder` 选已存在上一级目录，另有可编辑目录名默认「新建项目」，合成完整路径并展示；桥不可用时提供明确路径输入并由后端同样校验。图纸组一行一子集，动态列含图名、张数、基础模板、布局模板、图幅及普通 `sheet` 属性；新建从最大 `created_order` 的组复制全部可编辑值并聚焦图名，重复名保留错误而不自动改名；批量修改只作用选中组，混合值与明确清空分开。末列「操作」沿用图纸目录插件的 32×32 图标按钮视觉：上移、下移、✕ 删除，各自可访问名称且首末行禁用正确。

- [ ] **Step 4: 实现 XLSX 导出/导入确认与失败定位**

模板来自固定标准版本；若草稿已有项目属性、路径或组，导入前说明将全量覆盖这些输入，无差异比较。取消不发写请求；导入错误按工作表、行、列与字段定位，原草稿和预览状态不变；成功一次性替换输入并使预览失效。前端不解析公式或复算派生，不把 Data Validation 当作合法性证明。

- [ ] **Step 5: 运行输入流程测试与构建**

Run: `Set-Location web; npm run test:unit -- src/features/creation/store.test.ts; npm run check:i18n; npm run check:ui; npm run build; npm run test:e2e -- create-sheetset-input.spec.ts; Set-Location ..`

Expected: 四阶段壳、草稿恢复、两入口、路径、复制/重排/批改、导入取消/失败/成功及浅深主题/键盘输入测试通过；不要求第四阶段在本任务可执行。

- [ ] **Step 6: 提交创建输入 UI**

```powershell
git add web/src/views/CreateSheetSetView.vue web/src/features/creation web/src/components/creation web/src/api/creation.ts web/src/i18n web/src/views/WelcomeView.vue web/src/components/standards/StandardDetailPane.vue web/src/App.vue web/tests/e2e/create-sheetset-input.spec.ts changelog.md
git commit -m "实现四阶段图纸集创建输入界面"
```

### Task 9: 实现按组预览、逐张属性模态与创建闭环

**Files:**
- Create: `web/src/components/creation/ReviewStep.vue`
- Create: `web/src/components/creation/SheetValuesDialog.vue`
- Create: `web/src/features/creation/previewModel.ts`
- Create: `web/src/features/creation/previewModel.test.ts`
- Create: `web/tests/e2e/create-sheetset-review.spec.ts`
- Modify: `web/src/views/CreateSheetSetView.vue`
- Modify: `web/src/features/creation/store.ts`
- Modify: `web/src/i18n/locales/zh-CN/creation.ts`
- Modify: `web/src/i18n/locales/en-US/creation.ts`
- Modify: `docs/dst-manager/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 3/4 的按组预览响应、`preview_digest`、Task 6/7 的创建任务进度与成功工作区身份。
- Produces: “检查并创建”单页的权威按组表、诊断定位、逐张属性值模态、预览失效状态、执行/重试与成功后工作区切换。

- [ ] **Step 1: 写入按组摘要与失效用例**

```ts
it("shows first sheet value and opens all values only when values differ", () => {
  const cell = summarizeSheetValues([{number: "01", value: "平面图-01"}, {number: "02", value: "平面图-02"}]);
  expect(cell.text).toBe("平面图-01");
  expect(cell.showDetails).toBe(true);
  expect(cell.rows).toHaveLength(2);
});

it("invalidates preview after a project setting changes", async () => {
  const store = createCreationStore(fakeCreationApi());
  await store.preview();
  store.invalidateForSettingsChange();
  expect(store.previewDigest).toBeNull();
  expect(store.canExecute).toBe(false);
});
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `Set-Location web; npm run test:unit -- src/features/creation/previewModel.test.ts; npm run test:e2e -- create-sheetset-review.spec.ts; Set-Location ..`

Expected: FAIL，预览模型/组件尚不存在。

- [ ] **Step 3: 实现预览表、模态与诊断定位**

主表每组一行：`图纸组 | 图纸范围 | 图纸 | 张数 | 文件名 | 基础模板 | 布局模板 | 图幅 | 动态 sheet 属性`，不提供单张 Sheet 行或“布局”列。范围显示后端 `01-03` 等结果；不编号组只显示同位数单值 `00`。图纸标题使用后端紧凑结果，不自行拼接。动态属性全组同值直接显示；多值显示首张实际值和可点击「…」，首张空值显示「（空）…」，绝不显示“多值”。模态按组内顺序列出全部图号、图纸标题和值，支持键盘、Esc、焦点圈定/回归。错误可跳回项目字段/组行/模板图幅/XLSX 位置。主表自身横向滚动、首列保持可见；900×768、浅深主题和 200% 缩放下页面整体不横溢。

- [ ] **Step 4: 接入预览门禁、任务浮层和成功切换**

任何草稿输入、标准身份或编号设置变化立即禁用旧预览；服务端摘要最终决定能否执行。创建前展示最终路径与不可覆盖确认，执行只发送 `preview_digest`；任务进度复用全局任务浮层，失败保留草稿和诊断、允许修正后重新预览/新 attempt 重试，成功用返回的 `workspace_id` 切换普通工作区。前端不从草稿自行推算图号、标题、DWG 文件名或派生值。

- [ ] **Step 5: 执行相关与全量验证并记录实际结果**

Run（逐行执行；迁移仅对 Task 6 的临时全新库和升级夹具运行，不直接修改用户本地数据库）：

```powershell
uv run ruff check .
uv run pytest -q
uv lock --check
Set-Location web
npm run check:api
npm run check:i18n
npm run check:ui
npm run test:unit
npm run build
npm run test:e2e
Set-Location ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
```

Expected: 自动化全部通过；真实 AutoCAD 2016/2020 与官方 Sheet Set Manager 按 Task 5/7 验收并记录具体结果，环境不可用时标明缺口，不能把 Plan 标为 `completed`。记录 UI 浅深主题、900×768、200% 缩放、键盘和桌面壳文件夹选择证据。

- [ ] **Step 6: 更新计划实际验证并提交**

```powershell
git add web/src/views/CreateSheetSetView.vue web/src/components/creation/ReviewStep.vue web/src/components/creation/SheetValuesDialog.vue web/src/features/creation web/src/i18n/locales/zh-CN/creation.ts web/src/i18n/locales/en-US/creation.ts web/tests/e2e/create-sheetset-review.spec.ts docs/dst-manager/README.md changelog.md .planning/plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md
git commit -m "交付标准驱动的新图纸集创建"
```

## 实际验证（2026-09-24，Task 9 收口）

**全部 9 个任务已实施并通过自动化门禁；官方 SSM 界面人工验收待用户确认后即可置为 `completed`。**
本节只记录实际执行结果，不改写上方任务的需求描述与步骤。

逐行执行的门禁与实际结果：

| 门禁 | 命令 | 实际结果 |
| --- | --- | --- |
| Python 静态检查 | `uv run ruff check .` | 通过（All checks passed!） |
| Python 全量测试 | `uv run pytest -rs -p no:warnings` | **1888 passed / 74 skipped / 0 failed**（272.15s；含本次新增 3 例） |
| 依赖锁定 | `uv lock --check` | 通过（Resolved 71 packages，无变更） |
| API 契约 | `npm run check:api`（web/） | 通过（`web/src/api/schema.d.ts` 无漂移） |
| 语言包 | `npm run check:i18n`（web/） | 通过（**1571 键 / 11 域**中英对称，无未登记硬编码中文） |
| UI 静态契约 | `npm run check:ui`（web/） | 通过（0 违规、无 stale 例外） |
| 前端单测 | `npm run test:unit`（web/） | **300 passed / 28 files** |
| 前端构建 | `npm run build`（web/） | 通过（check:api + check:i18n + check:ui + vue-tsc + vite） |
| 端到端 | `npm run test:e2e`（web/） | **654 passed / 0 failed / 0 flaky**（最终提交状态全量；此前两次全量分别为 651 passed / 2 failed / 1 flaky 与 652 passed / 2 flaky，全部失败/flaky 项均为 `page.goto` 被中断的既有 vite dev server 并行抖动，两个 spec 单独重跑 141 passed） |
| 双版本插件 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1` | 通过（2016 与 2020 重建，0 警告 / 0 错误） |

迁移说明：本任务未新增 Alembic 迁移；`npm run check:api` 触发的迁移只作用于 `tmp_path` 下的全新临时库夹具，未触碰用户本地数据库。

真实 AutoCAD 与官方 SSM：

- 真实 AutoCAD 2016/2020 系统测试由 Task 7 跑通（`tests/system_autocad/test_creation_workflow.py`，`DST_MANAGER_RUN_AUTOCAD=1` 下 **2 passed**：2020 16.45s / 2016 12.19s）；本任务未重跑（`uv run pytest -q` 按设计跳过需要该开关的系统测试）。
- **人工残余验收项**：官方图纸集管理器（SSM）界面对生成成果的打开性无法在 Core Console 内自动化，**本任务未执行、不记为已通过**。用户以真实 AutoCAD 打开新建项目的 DST 并确认图纸集/子集/图纸/自定义属性/布局引用显示正常后，本计划方可置为 `completed`。

UI 证据口径：浅深主题、900×768 与 200% 缩放（CSS `zoom: 2`，与既有视觉证据 spec 同口径）下的整页不横溢与主表自身横向滚动由 `web/tests/e2e/create-sheetset-review.spec.ts` 自动断言；键盘与模态焦点回归（打开、Tab 圈定、Esc/关闭退出、焦点归还）由同一 spec 断言；桌面壳文件夹选择由 Task 8 的 `create-sheetset-input.spec.ts` 覆盖（本任务保持通过）。

Task 9 实施中的偏差（已由控制方裁决）：创建任务的进度复用全局任务浮层的**同一任务面板组件与同一终态集合**，但 `TaskOverlay` 受 `hasWorkspace` 门控、创建期尚无普通工作区，故创建进度在向导的「检查并创建」页内呈现；为此把 `web/src/App.vue`、`web/src/composables/useWorkspaceLifecycle.ts`（新增 `openWorkspaceById`）与 `web/src/composables/useJobMonitor.ts`（导出共享终态集合）纳入本次变更集。

## 整分支最终复核与修复波（2026-09-24）

- 范围：`c657ab5..556eb35`（19 提交，含用户自行提交的无关改动 `823f46e`「pytest 默认并行」，未纳入结论）。复核方式：全新上下文审查者按「领域 / 基础设施与事务与 API / 前端 / 证据自洽」四遍只读复核，并逐条 triage 各任务延后的 Minor。
- 结论：**With fixes**，0 Critical / 1 Important。Important 为「创建任务全程不续租（无 heartbeat），并发恢复会误回收在飞任务，代价是成果已生成却报失败」；另将台账 T5「`render_create_layouts`/`LayoutCreationRequest` 零直接测试」（本计划唯一新增的「用户文本进 SCR」seam）升级为合并前必须修。
- 修复波（提交 `8bc3daf`，四项，各自先 RED 后 GREEN）：① 新增 `_LeaseRenewal`，与 `CadJobRunner` 同 `min(30, lease/3)` 节奏、同 `CREATION_JOB_LEASE_LOST` 语义，覆盖「每组之间」与「发布前」两处空档；② 补 `test_autocad_worker.py` 9 例 SCR seam 单测（结构顺序、引号包裹、8 类非法/重复输入构造期拒绝）；③ `creation_assets._candidate` 与 `StandardStore._read_document` 的异常面收宽（损坏 `document.json` 时候选列表仍 200 且该标准不可用且有原因）；④ 空目录名不再退化为上级目录（由既有 `CREATION_TARGET_PATH_EMPTY` 诊断承担，不新增错误码）。
- 再复核（范围收窄到 `556eb35..8bc3daf`）：四项全部 **ADDRESSED**，无新增 Critical/Important。
- 控制方独立复跑最终门禁（修复波之后）：`uv run ruff check .` 通过；`uv run pytest` **1900 passed / 74 skipped / 0 failed**（1974 collected，120.8s）；`uv lock --check` 通过；`npm run test:unit` **303 passed / 28 files**；`check:i18n` **1571 键 / 11 域**；`check:ui` 0 违规；`npm run build` 通过；全量 `npx playwright test` **654 passed**（其中 `main.spec.ts:290` 性能预算用例在满载并行下记为 1 flaky，单独重跑 `main.spec.ts` **129 passed**，判定为既有负载抖动而非回归）。
- 未修残差项（含各任务延后的 Minor 与本次复核新增项）已登记到 [PLAN-DM-036 最终复核残差项](../../../todos/dst-manager/2026-09-24-plan-dm-036-deferred-minors.md)，不阻塞本计划主体交付。
