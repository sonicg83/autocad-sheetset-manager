---
id: PLAN-DM-012
title: DST Manager v0.3.2 命名与模板流程需求变更实施计划
status: completed
owners:
  - dst-manager
created: 2026-09-03
updated: 2026-09-03
related:
  - SPEC-DM-008
  - ROADMAP-DM-001
---

# DST Manager v0.3.2 命名与模板流程需求变更实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 依据 [SPEC-DM-008](../../../docs/dst-manager/specs/SPEC-DM-008-v032-naming-and-template-flows.md) 交付：① `service.py` 全量拆分（先于功能变更，行为零变化）；② 序号后缀压缩拼接进入 DWG 文件名；③ 批量新增图纸"已有布局"来源强制解析为目标子集 DWG 与其第一个非 Model 布局；④ 批量新增图纸与新建子集表单文案统一；⑤ 新建子集必填"基础模板文件"并分离 DWG 基底与布局来源；⑥ 顺带关闭遗留项 M6/M4。

**Architecture:** 全部为既有链路内的规则与契约调整：domain（`editing.py` 文件名派生与来源解析）、contracts（`LayoutSource` 字段放宽、`InsertSubsetCommand` 新增 `base_template_file`）、planning（`source_snapshot` 取基础模板文件）、前端（`App.vue` 表单交互与文案）。不改变发布事务、CAD 分流、SCR 渲染器与 Worker 插件。

**Tech Stack:** Python 3.12 + uv、FastAPI + Pydantic、Vue 3 + TypeScript + Vite、Playwright。

**Spec:** `docs/dst-manager/specs/SPEC-DM-008-v032-naming-and-template-flows.md`

## Global Constraints

- 全程简体中文注释、commit message 与用户文案；标识符保持英文。
- 严格 TDD：先写失败测试并确认失败原因正确，再写最小实现。
- 不修改 DST/DWG 写入路径、发布事务、`DST -> XML DOM -> DST` 受控流程、SCR 渲染器与 Worker 插件命令。
- 既有公共接口、错误码与序列化契约保持兼容；`LayoutSource` 仅放宽 `existing_snapshot` 分支，`template_layout` 校验不变。
- 契约变更后必须运行 `npm run generate:api` 重新生成 `web/src/api/openapi.json` 与 `schema.d.ts`，生成文件保持 LF（Windows `core.autocrlf=true` 漂移门禁）。
- Python 依赖与前端依赖发生变化时同步 `pyproject.toml`/`uv.lock` 与 `package.json`/`package-lock.json`（本计划预期无依赖变化）。
- 每个任务完成时更新根目录 `changelog.md`（在 2026-09-03 章节追加）；commit message 简体中文、动词开头。
- 验证基线：`uv run ruff check .`、`uv run pytest -q`；前端 `npm run build`、`npm run test:e2e`。

---

### Task 0: service.py 全量拆分（SPEC-DM-008 F-05，先于全部功能任务）

**Files:**
- Modify: `src/dst_manager/application/service.py`（1984 行 → 编排入口只留跨域公共编排与共享门禁）
- Create: `src/dst_manager/application/` 下若干同层模块（纯辅助模块与功能域模块，命名跟随既有同层风格）
- Test: 既有全量测试（不新增行为测试）

**Interfaces:**
- Consumes: [AGENTS.md「代码组织契约」](../../../AGENTS.md)、[DMv031-deferred-findings](../../../.planning/memos/dst-manager/DMv031-deferred-findings.md) 已决策的拆分方案。
- Produces: 拆分后 `DstManagerService` 保留跨域公共编排与共享门禁（workspace 门禁、修订检查、事务辅助）；`_build_semantic_diff`/`_summarize_*`/`_operation_digest` 等纯辅助迁入无状态模块；drafts/editing/revisions/xml_io/repair 按功能域拆分到同层独立模块并在入口组合。公共接口、错误码与序列化契约不变；本计划后续任务的文件落点以拆分结果为准。

- [x] **Step 1: 拆分前基线固化**

Run: `uv run pytest -q && uv run ruff check .`
记录通过/跳过数字作为拆分等价性基线。

- [x] **Step 2: 阶段一——纯辅助簇迁移**

将 `_build_semantic_diff`、`_summarize_*`、`_operation_digest` 等无状态辅助函数（约 600 行）整体迁移到同层独立模块（如 `application/summaries.py` 等，按内聚命名），`service.py` 以导入引用保持调用点不变。逐簇迁移、每簇提交前跑全量测试。

- [x] **Step 3: 阶段二——功能域拆分**

按功能域把 drafts/editing/revisions/xml_io/repair 的实现拆到同层独立模块，`DstManagerService` 通过组合保留既有公共方法签名（门禁、锁、事务辅助留在入口或共享模块）。**禁止**在拆分提交中夹带任何行为修改。

- [x] **Step 4: 等价性验证**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 通过/跳过数字与 Step 1 基线一致；`service.py` 与各新模块均低于约 500 行软上限。

- [x] **Step 5: 更新 changelog 并提交（拆分为独立 commit，不与功能混合）**

---

### Task 1: 序号后缀压缩拼接进入 DWG 文件名（SPEC-DM-008 F-01）

**Files:**
- Modify: `src/dst_manager/domain/editing.py`（`derive_document_structure` 中 `_target_file_name` 调用与新增压缩辅助函数）
- Test: `tests/unit/test_core.py`（追加用例）

**Interfaces:**
- Consumes: `_target_file_name`（editing.py:598）、`derive_group_titles` 输出的组内标题列表（editing.py:392-396 处 `titles_for_subset`）。
- Produces: 模块内辅助 `_compressed_group_title(base_title: str, sheet_titles: list[str]) -> str`；`DerivedSubset.target_file` 对多张带后缀组含压缩后缀（`RQ-01-02 图纸目录 (1)-(2).dwg`）。不新增公共 API。

- [x] **Step 1: 写失败的 domain 测试**

在 `tests/unit/test_core.py` 的 `test_v021_naming_policy_derives_range_and_sheet_titles` 之后追加三个用例（跟随该用例的构造风格）：

1. `test_derived_target_file_name_compresses_title_suffixes`：两张图纸（`01`、`02`，基础标题 `图纸目录`，来源 DWG `RQ-01 图纸目录.dwg`）+ `SuffixOptions(True, 1)`，断言标题为 `图纸目录 (一)`/`图纸目录 (二)` 且 `target_file` 文件名为 `RQ-01-02 图纸目录 (一)-(二).dwg`；
2. `test_derived_target_file_name_compresses_arabic_suffixes`：同构造 + `SuffixOptions(True, 2)`，断言 `RQ-01-02 图纸目录 (1)-(2).dwg`；
3. `test_derived_target_file_name_keeps_base_title_without_suffix`：单张图纸，断言 `RQ-01 图纸目录.dwg` 不变。

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit/test_core.py -k derived_target_file_name -q`
Expected: 前两个用例 FAIL（文件名缺后缀部分），第三个 PASS（现状兼容行为）。确认失败原因正确后再继续。

- [x] **Step 3: 最小实现**

`editing.py`：

```python
def _compressed_group_title(base_title: str, sheet_titles: list[str]) -> str:
    prefix = f"{base_title} ("
    suffixes: list[str] = []
    for title in sheet_titles:
        if title.startswith(prefix) and title.endswith(")"):
            suffixes.append(title[len(prefix):-1])
        else:
            return base_title  # 结构异常时防御性回退为基础标题
    return f"{prefix}{')-('.join(suffixes)})"
```

`derive_document_structure` 中 `target_file = _target_file_name(source_target, number_range, title)` 改为传入 `_compressed_group_title(title, titles_for_subset)`；规划展示名 `f"{number_range} {title}"` 保持基础标题不变。单张无后缀时 `titles_for_subset[0] == base_title`，`startswith` 不成立自然回退，输出与现状一致。

- [x] **Step 4: 验证 GREEN 且无回归**

Run: `uv run pytest tests/unit/test_core.py -q`（全文件）
Expected: 全部 PASS。

- [x] **Step 5: 更新 changelog 并提交**

---

### Task 2: "已有布局"强制解析为目标子集（SPEC-DM-008 F-02）

**Files:**
- Modify: `src/dst_manager/interfaces/contracts.py`（`LayoutSource` 条件必填）
- Modify: `src/dst_manager/domain/editing.py`（`_layout_source` 放宽 + `insert_sheet` 分支解析）
- Modify: `_collect_structural_source_baselines` 所在模块（Task 0 拆分后按实际落点修改，原位于 `src/dst_manager/application/service.py`）
- Test: `tests/unit/test_core.py`、`tests/unit/` 契约测试所在文件（跟随既有分布）

**Interfaces:**
- Consumes: `_target_subset`、`document.subsets`（原始文档）、`sheet.layout.resolved_path or sheet.layout.file_name` 与 `sheet.layout.layout_name`。
- Produces: `LayoutSource` 在 `type=existing_snapshot` 时 `file`/`layout` 可空（`template_layout` 仍必填）；domain 解析后 `layout_sources[sheet_id]` 三字段齐全，下游（planning、baseline、cad_job）零改动。

- [x] **Step 1: 写失败的契约测试**

`LayoutSource` 用 `model_validator`（mode="after"）替代字段级 `min_length` 强制：`type=template_layout` 时 `file`/`layout` 必须非空；`existing_snapshot` 时允许为空字符串。字段类型改为 `str = ""` 默认。断言：`existing_snapshot` + 空 file/layout 通过校验；`template_layout` + 空 layout 报 `LAYOUT_SOURCE_INVALID`（沿用既有错误码与文案）。

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit -k layout_source -q`（或契约测试实际文件）
Expected: FAIL（现契约拒绝空 file/layout）。

- [x] **Step 3: 写失败的 domain 解析测试**

`derive_document_structure` + `insert_sheet` 命令（`source={"type": "existing_snapshot"}`，无 file/layout）：
1. 目标子集的首张图纸已登记 DWG 与布局 → 断言 `derived.layout_sources[新sheet_id]` 的 `file`/`layout` 被解析为该图纸登记值；
2. 目标子集无任何登记（新造空来源子集）→ 断言抛 `EditingError("LAYOUT_SOURCE_INVALID", ...)`。

- [x] **Step 4: 运行确认失败，然后最小实现**

Run: `uv run pytest tests/unit/test_core.py -k existing_snapshot -q` → FAIL 后实现：

- `_layout_source(command)`：`existing_snapshot` 时允许 file/layout 为空（返回含空值的 dict，类型合法即可）；`template_layout` 校验不变；
- `insert_sheet` 分支（editing.py:318-331）：`source["type"] == "existing_snapshot"` 且 file/layout 任一为空时，从 `document.subsets` 中目标子集的首张图纸解析 file（`resolved_path or file_name`）与 layout（`layout_name`）后**回写进 source dict**再创建 `LayoutReference`；首图缺失或登记为空 → `EditingError("LAYOUT_SOURCE_INVALID", "目标子集缺少可用的已有布局来源")`；
- `_existing_layout_sources` 与下游不变：解析发生在 `layout_sources` 写入前，planning/baseline/cad_job 读到的仍是齐全的三字段。

- [x] **Step 5: baseline 校验回归**

Run: `uv run pytest tests/unit -q`
Expected: 全量 PASS（`_collect_structural_source_baselines` 对解析后文件的行为与现状一致：解析结果天然在工作区内且为 `.dwg`，防御性校验保留）。

- [x] **Step 6: 更新 changelog 并提交**

---

### Task 3: 新建子集基础模板文件（SPEC-DM-008 F-04）

**Files:**
- Modify: `src/dst_manager/interfaces/contracts.py`（`InsertSubsetCommand.base_template_file`）
- Modify: `src/dst_manager/domain/editing.py`（`insert_subset` 分支读取并校验 base_template_file）
- Modify: `src/dst_manager/domain/models.py`（`DerivedSubset` 或 `DerivedDocument` 携带子集级基础模板信息，以对既有序列化影响最小者为准）
- Modify: `src/dst_manager/domain/planning.py`（`source_snapshot` 取基础模板文件）
- Test: `tests/unit/test_core.py`（契约 + planning 用例）

**Interfaces:**
- Consumes: `validate_absolute_source_file`（`domain/text_validation.py`）、planning.py:164 `source_snapshot = source_target or layouts[0]["source_file"]`。
- Produces: `InsertSubsetCommand.base_template_file: str`（必填，`.dwg`/`.dwt`）；planning 中 `create` 组的 `source_snapshot` = 基础模板文件（`.dwt` 时为复制基底，布局仍来自布局模板文件）；错误码 `INSERT_SUBSET_BASE_TEMPLATE_INVALID`（缺失或扩展名非法时，domain 层抛出）。

- [x] **Step 1: 写失败的契约与 domain 测试**

1. 契约：`insert_subset` 命令缺 `base_template_file` → 422 校验错误；`base_template_file` 为相对路径或扩展名非 `.dwg/.dwt` → 校验错误；
2. domain：`derive_document_structure` 处理合法 `insert_subset` 后，派生结果携带该子集的基础模板文件；缺失时抛 `INSERT_SUBSET_BASE_TEMPLATE_INVALID`。

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/unit/test_core.py -k base_template -q`
Expected: FAIL（字段不存在）。

- [x] **Step 3: 最小实现**

- 契约层：`base_template_file: str = Field(min_length=1)` + field_validator 调用 `validate_absolute_source_file`，扩展名白名单 `{".dwg", ".dwt"}`（大小写不敏感）；
- domain 层：`insert_subset` 分支读取 `command["base_template_file"]` 并存入派生结果（推荐：`DerivedDocument.subset_base_templates: dict[str, str]`，默认空 dict，`_serialize_derived_document` 如涉及则同步）；
- planning 层：`source_snapshot = source_target or subset_base_templates.get(subset_id) or layouts[0]["source_file"]`——`create` 组因契约必填总命中第一候选，`rebuild` 组行为不变。

- [x] **Step 4: 验证 GREEN 且无回归**

Run: `uv run pytest tests/unit -q`
Expected: 全部 PASS。注意检查既有"新建子集"用例的命令夹具需补 `base_template_file`（测试夹具属于允许的同步修改）。

- [x] **Step 5: 更新 changelog 并提交**

---

### Task 4: 前端表单交互与文案（SPEC-DM-008 F-02/F-03/F-04）

**Files:**
- Modify: `web/src/App.vue`（批量新增图纸 fieldset 与新建子集 fieldset）
- Modify: `web/src/api/contracts.ts`（`createCommand.insertSubset` 增加必填 `base_template_file`；依赖 Task 5 契约再生成后的 `schema.d.ts`）
- Modify: Playwright 用例中文案/表单选择器（以实际引用为准）

**Interfaces:**
- Consumes: `TEMPLATE_FILE_FILTERS`、`selectTemplateFile`、`loadLayoutOptions`（App.vue 既有）；`createCommand.insertSubset`（`web/src/api/contracts.ts:88-90`）。
- Produces: 批量新增图纸——模板来源选"已有布局"时隐藏并禁用布局模板文件/名称输入，显示只读说明"来源为目标子集 DWG 的第一个布局"；新建子集——新增必填"基础模板文件"选择器（`.dwg/.dwt`，未选不可提交），文案按 SPEC-DM-008 §5 改名。

- [x] **Step 1: 契约先行**

先完成 Task 5 的 `npm run generate:api`（依赖 Task 2/3 的后端契约），使 `schema.d.ts` 中 `InsertSubsetCommand.base_template_file` 与 `LayoutSource` 可选字段可用。

- [x] **Step 2: 表单实现**

`App.vue`：

1. 批量新增图纸：`insertSheetForm.sourceType === "existing_snapshot"` 时用 `v-if` 隐藏文件/布局输入行，替换为只读说明文案；`queueInsertSheet` 中该分支不再要求 sourceFile/sourceLayout 非空，提交 `source: { type, file: "", layout: "" }`；文案改名三处（§5 表）；
2. 新建子集：新增 `baseTemplateFile` 响应式字段与选择按钮（过滤器 `.dwg/.dwt`），`queueInsertSubset` 校验非空后随命令提交；文案改名两处；
3. **顺带关闭 M6**：`closeWorkspace` 重置时同步清空批量新增图纸与新建子集表单的模板文件、模板布局、布局选项与本次新增的 `baseTemplateFile` 状态（原 M6 只重置了部分字段，本次一并补齐）；
4. **顺带关闭 M4**：`loadLayoutOptions` 的 `cad_version` 改用 `cadVersion.value`，去除硬编码 `"2020"`。

- [x] **Step 3: E2E 与构建验证**

Run: `npm run build`、`npm run test:e2e`
Expected: 构建成功、用例全绿（按需更新引用旧文案/表单结构的用例）。

- [x] **Step 4: 更新 changelog 并提交**

---

### Task 5: 契约再生成与全量验证

**Files:**
- Modify: `web/src/api/openapi.json`、`web/src/api/schema.d.ts`（`npm run generate:api` 再生成）
- Modify: `changelog.md`（收尾条目）

- [x] **Step 1: 再生成契约**

Run: `uv run python scripts/export_openapi.py` 后 `npm run generate:api`
Expected: `schema.d.ts` 包含 `base_template_file` 与放宽后的 `LayoutSource`；文件保持 LF。

- [x] **Step 2: 全量验证**

Run: `uv run ruff check . && uv run pytest -q && uv lock --check && npm run build && npm run test:e2e`
Expected: 全部通过；记录 pytest/E2E 实际数字写入 changelog 收尾条目。

- [x] **Step 3: 真实 CAD 系统测试（具备环境时）**

`DST_MANAGER_RUN_AUTOCAD=1` 下验证：新建子集（基础模板文件 `.dwg` 与 `.dwt` 各一 + 布局模板）、"已有布局"批量新增图纸的整批发布与回滚路径。结果记入本计划的「实际验证」小节。

- [x] **Step 4: 更新 PLAN-DM-012 状态与 ROADMAP，收尾提交**

## 实际验证

**全量验证（Task 5，2026-09-03）**：`uv run ruff check .` All checks passed；`uv run pytest -q` 全量 **545 passed / 72 skipped**（617 项，0 failures / 0 errors，退出码 0；62 项真实 AutoCAD 系统测试未显式启用时跳过）；`uv lock --check` 通过；`npm run build`（check:api + vue-tsc + vite）零类型错误；Playwright e2e **39/39 通过**。契约再生成等幂确认：`export_openapi.py` + `generate:api` 重跑后 `web/src/api` 无 git 变更，`openapi.json`/`schema.d.ts` 保持 LF。

**真实 CAD 系统测试（本机具备 AutoCAD 2016 R20.1 / 2020 R23.1 Core Console、匹配插件与私有样本 `sample/project1`）**：`DST_MANAGER_RUN_AUTOCAD=1` 下运行 24 项场景相关系统测试全数通过（0 失败 0 跳过）：

1. **新建子集（基础模板文件 `.dwg` 与 `.dwt` 各一 + 布局模板）**：`test_insert_subset_creates_independent_dwg_with_batch_layouts`（2016/2020 × dwg/dwt 共 4 项）——预览 `source_snapshot` 确认为基础模板文件（`.dwg` 与 `.dwt` 均接受）、`source_target_file` 为 None，执行后新子集 3 张图纸共享独立 DWG（与模板文件不同）、布局名与 Handle 齐全且非 0；
2. **"已有布局"批量新增图纸的整批发布**：`test_existing_snapshot_batch_insert_publishes_whole_batch`（2016/2020）——空来源提交后预览把布局来源解析为目标子集首图登记的 DWG 与布局，rebuild 后 3 张图纸按目标布局顺序发布、Handle 齐全；
3. **"已有布局"批量新增的回滚路径**：`test_existing_snapshot_batch_failure_never_publishes_partial`（2016/2020）——双子集批量插入注入第 2 个 CAD 工作单元失败 → 整批 `FAILED`（`CAD_PROCESS_FAILED`）、全部正式文件 SHA-256 不变、无 publish manifest；
4. **既有整批回滚机制回归**（12 项）：`test_injected_second_dwg_failure_never_publishes_partial_files`、`test_mixed_rename_rebuild_delete_failure_never_publishes`（4 种失败注入）、`test_cad_success_then_dom_failure_keeps_formal_hashes`——均验证失败不回滚、正式文件字节不变。

**真机验证修复的缺陷**：Task 5 系统测试暴露 `DstManagerService._issue`（service.py:265）实例方法签名缺 `self`，`open_workspace` 的 `UNREFERENCED_DWG` 诊断分支（工程根存在未被 DST 引用的 `.dwg`，如置于根目录的基础模板文件）调用即抛 `TypeError`；已补 `self` 并新增单测 `test_open_workspace_reports_unreferenced_dwg_without_crashing`（full-suite 全绿）。系统测试夹具同步：`test_insert_subset_creates_independent_dwg_with_batch_layouts` 补 Task 3 遗漏的必填 `base_template_file` 并按 `.dwg/.dwt` 参数化；新增两个 `existing_snapshot` 系统测试（SPEC-DM-008 §10 验收）。

**Task 3 评审遗留核对（responses.py）**：`DerivedDocumentResponse`（interfaces/responses.py:192-196）未含 `subset_base_templates` 键（`extra="ignore"` 静默丢弃）——核对父链预览响应 `ExecutionIntentResponse.groups[].source_snapshot`（既有字段）：create 组该字段即基础模板文件（planning.py:164-178 的 `source_target or subset_base_templates.get(...) or layouts[0]["source_file"]`），用户所需"新子集 DWG 基底来自哪个文件"的信息已完整暴露，`DerivedDocumentResponse.subset_base_templates` 为冗余内部细节；**结论：无需改动**。
