---
id: PLAN-DM-047
title: 级联枚举属性实施计划
status: completed
owners:
  - dst-manager
created: 2026-09-29
updated: 2026-09-30
related:
  - SPEC-DM-021
  - SPEC-DM-017
  - SPEC-DM-018
  - SPEC-DM-020
  - ARCH-DM-001
---

# 级联枚举属性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在图纸标准、创建向导和 XLSX 输入中增加 `sheetset`/`sheet` 两级均可使用的级联枚举属性，保证上级同作用域、输入成对有效，最终 DST 只写上级属性与级联结果。

**Architecture:** 标准文档 v4 新增 `kind: cascade`，按同作用域普通枚举的稳定项 ID 关联有序候选数组；级联与普通属性同属创建输入，后端对图纸集和每个图纸组分别校验成对取值后再求映射、组合和 DWG 命名。标准编辑器增加独立分区，网页向导在项目信息与图纸组各自联动，XLSX 两张可见表保持静态候选下拉并由导入/预览校验组合。

**Tech Stack:** Windows 11、Python ≥3.12、UV、FastAPI、openpyxl、Vue 3、TypeScript、Vite、Vitest、Playwright。

**Spec:** [SPEC-DM-021](../../../docs/dst-manager/specs/SPEC-DM-021-cascading-enum-properties.md)；原属性与创建契约见 [SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md) 和 [SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md)。

## Global Constraints

- 首版支持 `sheetset` 普通枚举 → 一级 `sheetset` 级联，以及 `sheet` 普通枚举 → 一级 `sheet` 级联；跨作用域或多级引用禁止，级联没有默认值，不可作为映射源。
- 配置以 `source_item_id` 关联上级 `enum_item_id`，候选持久化为字符串数组；半角/全角逗号只用于编辑器输入，单行重复、空值和缺行阻断发布。
- 新写入标准文档与包使用 `schema_version: 4`；现有 v3 已发布标准继续只读加载、导出和创建；v3 草稿只在显式保存时升级，不因只读操作改写。**v3 升级 v4 由后端保存路径完成**：`application/standards.py` 的 `save_standard_draft` 在结构门禁与身份核对之后把文档归一为 `schema_version: 4` 再写盘，并把升级后文档作为响应返回；前端 `blankStandardDocument` 直接写 v4，`toDraftDocument` 保留来源文档版本（缺失回退 3），不主动改写。
- v3 文档出现级联字段（任意属性的 `cascade_options`）或 `kind: "cascade"` 一律拒绝，不按文本属性降级；v4 读取器对未知 `kind` 或不合法 `cascade_options` 同样明确报错。
- `kind: cascade` 不进入 `DERIVED_PROPERTY_KINDS`。`domain/creation.py` 的 `ordinary_properties` 谓词从 `not prop.is_derived` 改为 `prop.kind in ORDINARY_PROPERTY_KINDS`；新增的 input 口径（`input_properties`、初值、已知键集合）同步供草稿保存与创建输入使用，`ordinary_*` 不再被创建链路当作输入来源。
- `REFERENCE_KINDS` 增加 `cascade`，`references_to` 把「普通枚举被级联用作上级」登记为 `StandardReference(kind="cascade", owner_id=<级联属性 ID>)`；删除被级联引用的上级枚举属性由编辑器阻断并显示引用方，后端发布门禁兜底。
- 发布诊断的行级定位沿用既有惯例：专业行标识写入诊断 `message`，不新增契约字段；前端 `publishIssues` 用已有的 `itemId`（源枚举项 ID）做结构化跳转。确有结构化透传需求时按契约变更流程另立任务。
- 创建输入的必填与缺键复用既有码：缺键 `CREATION_SHEETSET_VALUE_MISSING` / `CREATION_GROUP_VALUE_MISSING`，必填空 `CREATION_REQUIRED_VALUE_MISSING`；`STANDARD_CASCADE_VALUE_INVALID` 只用于「上级与级联值不匹配」。
- `sheetset` 级联保存在草稿 `sheetset_values`，`sheet` 级联保存在各图纸组的 `sheet_values`；最终只在对应图纸集或 Sheet 节点物化级联值，不存在中间分册属性。
- 网页向导切换上级时，只清空同一图纸集或受影响图纸组的依赖值；批量修改上级清空选中组，批量设置级联须对所有选中组有效且整批生效（先全量校验、再一次提交，不允许逐组部分成功）。草稿恢复、XLSX 和 API 的非法组合保留原输入、给出诊断，预览和执行都须阻断。
- XLSX 可见表仍只有 `SheetSet` 与 `Sheet`，级联分别作为输入行或列，候选静态列出且不生成公式；导入错误定位到 `SheetSet` 的 B 列或 `Sheet` 的实际行列。
- 领域层不得依赖 FastAPI、SQLAlchemy、文件系统或 AutoCAD；只读打开不改 DST/DWG 或文件时间戳；正式创建沿用既有可回滚发布事务。
- 按仓库约定使用简体中文注释、文档、变更记录与 commit message；每个实际代码变更任务同步更新 `changelog.md`，不提交私有样本和生成物。

## 文件职责与接口

| 范围 | 预计文件 | 职责 |
| --- | --- | --- |
| 标准模型/门禁 | `src/dst_manager/domain/standard_models.py`、`standard_schema.py`、`standard_semantics.py`、`standard_rules.py`，新建 `standard_cascade.py` | 保存级联结构与反向引用、v4 解析与 v3 拒绝口径、发布配置校验、成对输入校验；`publish_diagnostics` 聚合级联定义诊断；独立纯函数避免继续扩张现有文件。 |
| 标准存储/包/保存 | `src/dst_manager/infrastructure/standards/draft_storage.py`、`store_core.py`、`package.py`、`package_io.py`、`src/dst_manager/application/standards.py` | v3/v4 读取、两处版本门禁、显式草稿保存升级 v4、包往返与预检；manifest 即标准文档，只有唯一版本入口。 |
| 创建领域/API | `src/dst_manager/domain/creation.py`、`creation_plan_inputs.py`、`creation_planning.py`、`src/dst_manager/application/creation.py`、`creation_drafts.py`、`src/dst_manager/interfaces/creation_api.py` | 把两级级联列为输入、拼装初值与已知键集合、图纸集/逐组成对校验、预览/执行/实时求值一致物化；接口层只核对透传，契约预期不改。 |
| XLSX | `src/dst_manager/infrastructure/creation_xlsx_protocol.py`、`creation_xlsx_template.py`、`src/dst_manager/application/creation_import_rows.py`（必要时 `creation_import.py`） | `SheetSet` 输入行、`Sheet` 输入列、静态去重候选与按行成对诊断；校验插在两张表全量读取之后。 |
| 标准前端 | `web/src/features/standards/draftModel.ts`、`publishModel.ts`、`web/src/components/standards/StandardEditor.vue`、`StandardPublishReview.vue`，新建 `CascadePropertyEditor.vue` | 新分区、两列配置、同步源项、发布错误定位、删除保护、v4 文档模板。 |
| 创建前端 | `web/src/features/creation/inputModel.ts`、`store.ts`、`types.ts`、`web/src/components/creation/ProjectStep.vue`、`GroupsStep.vue`、`GroupBatchDialog.vue` | 两级级联输入、逐组清空、批量原子修改与草稿恢复无损显示。 |

核心领域接口固定为 `validate_cascade_definition(standard: DrawingStandard) -> tuple[StandardDiagnostic, ...]` 与 `validate_cascade_values(standard: DrawingStandard, scope: str, values: Mapping[str, str]) -> tuple[StandardDiagnostic, ...]`；前者由 `publish_diagnostics` 聚合（error 才阻断），后者在发布与创建共用，创建编排对 `sheetset_values` 调用一次、对每个图纸组的 `sheet_values` 分别调用并附加组定位。创建侧新增 `input_properties(standard: DrawingStandard, scope: str) -> tuple[StandardProperty, ...]`（文本、普通枚举与级联），并配套 input 口径的初值与已知键辅助函数；`ordinary_properties` 只保留普通属性语义供确实需要的调用方使用。前端使用同名的级联候选解析纯函数，且不得取代后端校验。

## Review Focus

1. 两个上级枚举项都含「分册一」：相同文本在不同候选行合法，`SheetSet` 与 `Sheet` 的导入/预览都按本对象上级选行。Task 1、3、4 测试覆盖。
2. 上级枚举项改名、增删或更换：稳定 ID 保留匹配行，缺失/过时行阻断发布，绝不把旧行套到新源；删除被级联引用的上级枚举属性被阻断并显示引用方。Task 1、5、7 测试覆盖。
3. 图纸组 A 改选上级后仍持有旧级联值、图纸组 B 未修改：网页只清空 A；API、恢复草稿和 XLSX 保留非法原值并准确报错；批量级联对混合上级不合法时整批拒绝、无部分成功。Task 3、4、6 测试覆盖。
4. v3 标准及草稿与 v4 包混用：v3 只读不变、显式保存升级、v3 含级联字段被拒绝、包往返不丢级联，未知种类不降级。Task 1、2 测试覆盖。
5. `sheet` 级联被同级组合引用、`sheetset` 级联被 DWG 命名引用且值非法：不得物化部分结果、写入 DWG 或执行旧预览摘要；`sheet` 级联不能越权进入 DWG 命名。Task 1、3 测试覆盖。

---

### Task 1：标准模型、Schema v4 与级联发布门禁

**Files:** `src/dst_manager/domain/standard_models.py`、`standard_schema.py`、`standard_semantics.py`、`standard_rules.py`、新建 `standard_cascade.py`；`tests/unit/test_drawing_standards.py`、`tests/unit/test_standard_rules.py`。

**Interfaces:** 产出 `StandardCascadeRow(source_item_id: str, values: tuple[str, ...])`、`StandardProperty.cascade_options`、`validate_cascade_definition`、`validate_cascade_values`；`publish_diagnostics` 聚合前者，`store_common._publish_gate_error`、`application/standards.py`、`application/standard_packages.py` 无需改动即可生效。`REFERENCE_KINDS` 增加 `cascade`，`references_to` 返回级联对上级枚举的引用（删除保护与前端共用）。`kind: cascade` 不进入 `DERIVED_PROPERTY_KINDS`；同级组合可引用级联，只有 `sheetset` 级联可进入 DWG 命名（沿用 `validate_naming_segments` 的作用域判定，不新增码）。`validate_mapping_sources` 与 `_validate_references` 对 `kind == "cascade"` 跳过映射语义检查，级联源检查归 `validate_cascade_definition`。

- [x] Step 1：写失败测试：v4 解析和序列化两种作用域的级联；v3 无级联仍可读；v3 文档出现 `kind: "cascade"` 或 `cascade_options` 被拒绝；未知 kind、跨作用域源/非普通枚举源/自引用拒绝；同名候选在不同源项合法；源枚举无项、单行空项/重复与缺失/过时行分别以 `STANDARD_CASCADE_SOURCE_INVALID`、`STANDARD_CASCADE_OPTIONS_INVALID` 阻断发布；`sheet` 级联进入 DWG 命名时拒绝；`references_to` 对上级枚举返回 `cascade` 引用，删除级联属性仍被组合/DWG 命名引用保护。
- [x] Step 2：执行 `rtk uv run pytest tests/unit/test_drawing_standards.py tests/unit/test_standard_rules.py -q -o addopts=`，记录新增用例的失败结果。
- [x] Step 3：增加模型、反向引用、解析/序列化与门禁；版本相关校验需要把 `schema_version` 传到属性解析或在解析后统一检查；发布门禁调用 `validate_cascade_definition` 并接入 `publish_diagnostics`；映射源与引用检查对级联跳过。实现按 `scope` 与本对象值校验的 `validate_cascade_values`：上级为空只允许级联空，非空值必须属于对应源项候选，上级本身非法时不推断候选（不匹配用 `STANDARD_CASCADE_VALUE_INVALID`；必填与缺键由创建侧既有码处理）。
- [x] Step 4：重跑 Step 2 命令，确认新增与既有领域用例通过；更新本任务涉及的 `changelog.md` 条目。
- [x] Step 5：只暂存本任务文件并以简体中文动词开头提交；提交前核对 `git diff --cached --name-only`。

### Task 2：标准草稿、标准包与保存升级

**Files:** `src/dst_manager/infrastructure/standards/draft_storage.py`、`store_core.py`、`package.py`、`package_io.py`、`src/dst_manager/application/standards.py`；`tests/unit/test_standard_store.py`、`test_standard_package.py`、`tests/integration/test_standard_api.py`。

**Interfaces:** 消费 Task 1 的 v3/v4 读取器；发布与导出保留 v4 的 `cascade_options`；标准详情与发布诊断透传级联字段和错误码（document 为透传 dict，行级定位只在 message，不新增契约字段）。`SUPPORTED_SCHEMA_VERSIONS` 扩为 `(3, 4)`。

- [x] Step 1：写失败测试：v3 已发布包继续导入、导出和创建；v3 草稿打开前后文件字节及修改时间不变，显式保存后落盘与响应均为 v4；v3 含级联字段的草稿保存被拒绝；v4 草稿保存/发布/导出/预检/导入往返保持源 ID 与候选顺序；未知 v4 kind 被明确拒绝。
- [x] Step 2：运行 `rtk uv run pytest tests/unit/test_standard_store.py tests/unit/test_standard_package.py tests/integration/test_standard_api.py -q -o addopts=`，确认新增用例失败。
- [x] Step 3：更新存储、包与应用层支持 v3/v4：`store_core.py` 两处版本门禁（已发布标准扫描约 174 行、文档读取约 233 行）统一按 `schema_version not in SUPPORTED_SCHEMA_VERSIONS` 判定，保留 v3 无发布时间的历史分支；`save_standard_draft` 在结构门禁与身份核对之后归一 `schema_version: 4` 再写盘并返回升级后文档；预检与确认共用同一读取语义；不增加只读写入。包内 `manifest.json` 即标准文档本体，只有唯一版本入口，不存在独立 manifest 版本。
- [x] Step 4：重跑 Step 2 命令；更新本任务涉及的 `changelog.md` 条目。
- [x] Step 5：只暂存本任务文件并以简体中文动词开头提交。

### Task 3：创建输入、预览与物化

**Files:** `src/dst_manager/domain/creation.py`、`creation_plan_inputs.py`、`creation_planning.py`、`src/dst_manager/application/creation.py`、`creation_drafts.py`；核对（预期不改）`src/dst_manager/interfaces/creation_api.py`；`tests/unit/test_creation_planning.py`、`tests/integration/test_creation_api.py`、`test_creation_job.py`。

**Interfaces:** 提供 `input_properties` 与 input 口径的初值/已知键辅助；`ordinary_properties` 谓词改为 `kind in ORDINARY_PROPERTY_KINDS` 后不再包含级联。创建草稿的 `sheetset_values` 与每组 `sheet_values` 分别包含本作用域级联 `property_id`；`creation_drafts.py` 的播种与键门禁切换到 input 口径，级联键不被当作未知字段。预览与执行对图纸集和每组调用 Task 1 的 `validate_cascade_values`，使用同一标准快照和错误码；合法级联值参与同级组合，仅 `sheetset` 级联参与 DWG 命名。

- [x] Step 1：写失败测试：`ordinary_properties` 两类作用域都不包含级联、`input_properties` 包含级联；含级联键的草稿可保存且不报未知字段；新草稿级联初值为空键齐全；图纸集与两组 Sheet 的有效配对分别写入对应 DST 节点；第二组错配时诊断定位该组/属性且第一组不被发布；上级空/级联非空与非法上级按属性定位，必填空复用 `CREATION_REQUIRED_VALUE_MISSING`、缺键复用既有组内码；同级组合与合法 DWG 命名使用有效值；API 直写非法组合及旧摘要执行均阻断且不产生半成品。
- [x] Step 2：运行 `rtk uv run pytest tests/unit/test_creation_planning.py tests/integration/test_creation_api.py tests/integration/test_creation_job.py -q -o addopts=`，确认新增用例失败。
- [x] Step 3：把两级级联纳入可输入属性与创建计划；`creation.py` 改谓词并新增 input 口径辅助，`creation_drafts.py` 切换初值播种与键门禁，`creation_planning.py` 在输入门禁后对图纸集调用一次、每组分别校验并把组值复制到该组每张 Sheet；校验先于映射/组合/命名，`sheetset` 实时求值、预览和最终执行同口径；诊断保持属性级（与 `_dedupe` 的 (码, 组, 属性) 折叠一致），行级细节放进 message；删除保护与配置检查不得交给前端。
- [x] Step 4：重跑 Step 2 命令；核对预览/执行没有新增直接 DST 覆盖路径；更新 `changelog.md`。
- [x] Step 5：只暂存本任务文件并以简体中文动词开头提交。

### Task 4：XLSX 静态下拉与成对导入校验

**Files:** `src/dst_manager/infrastructure/creation_xlsx_protocol.py`、`creation_xlsx_template.py`、`src/dst_manager/application/creation_import_rows.py`；核对（预期不改）`src/dst_manager/application/creation_import.py`；`tests/unit/test_creation_xlsx_template.py`、`test_creation_xlsx_import.py`、`test_creation_xlsx_rows.py`。

**Interfaces:** `SheetSet` 为本级级联增加输入行，`Sheet` 为本级级联增加输入列；隐藏候选表为每个级联保存按首次出现顺序去重的静态列表；读取完整 `sheetset_values` 和每个 `Sheet` 数据行后分别调用 Task 1 的领域校验，并把诊断映射到对应单元格（`CreationDiagnostic` 已有 `sheet/row/column`）。

- [x] Step 1：写失败测试：模板只有两张可见表、无公式，`SheetSet` 级联行与 `Sheet` 级联列及各自去重候选齐全；两源项共享「分册一」在本级列表只出现一次；合法导入与网页输入同值；粘贴绕过下拉的错配分别定位 `SheetSet!B<n>` 与 `Sheet!<列><行>`，任一组错误都整批不改草稿；`SheetSet` 与 `Sheet` 的错配诊断同时存在时仍整批拒绝。
- [x] Step 2：运行 `rtk uv run pytest tests/unit/test_creation_xlsx_template.py tests/unit/test_creation_xlsx_import.py tests/unit/test_creation_xlsx_rows.py -q -o addopts=`，确认新增用例失败。
- [x] Step 3：扩展模板输入行/列和候选列；成对校验作为 `_read_sheetset` / `_read_groups` 的收尾步骤（全量读取之后）实现于 `creation_import_rows.py`，不生成 `INDIRECT` 或其他 Excel 公式；原有公式/宏/隐藏元数据门禁继续有效；若阶段顺序需要调整，才把 `creation_import.py` 一并列入本任务。
- [x] Step 4：重跑 Step 2 命令；更新 `changelog.md`。
- [x] Step 5：只暂存本任务文件并以简体中文动词开头提交。

### Task 5：标准编辑器第三分区

**Files:** `web/src/features/standards/draftModel.ts`、`publishModel.ts`、`web/src/components/standards/StandardEditor.vue`、`StandardPublishReview.vue`、新建 `CascadePropertyEditor.vue`、`web/src/i18n/locales/zh-CN/standards.ts` 与 `en-US/standards.ts`；`web/src/features/standards/draftModel.test.ts`、`publishModel.test.ts`、新建 `CascadePropertyEditor.test.ts`、`web/tests/e2e/standards-editor.spec.ts`。

**Interfaces:** 前端草稿模型保存 Task 1 的 `cascade_options` 数组，分区为普通/级联/派生；`EditorSectionId` 增加 `"cascade"` 并插在 `ordinary` 与 `derived` 之间；`sectionCounts`、`sectionOfDiagnostic`、`PUBLISH_SECTIONS`、`StandardPublishReview` 的 `sectionLabelKeys` 与 `publishIssues` 增加级联分支；`ReferenceKind` 增加 `cascade`，删除被级联引用的上级枚举显示引用方并阻断；`blankStandardDocument` 写 `schema_version: 4`，`toDraftDocument` 保留来源版本。作用域选择限制上级候选为同级普通枚举；候选文本框接受半角/全角逗号，仅在界面解析；同源多级联可并存。

- [x] Step 1：写失败单元与 E2E：第三分区可创建/编辑/删除两种作用域的级联；选择 `sheetset` 时看不到 `sheet` 源，反之亦然；两列表行由上级枚举固定，改名保留行、加删源项显示同步与发布诊断；切换上级或作用域不继承旧候选；空片段/重复项不可确认；删除被级联引用的上级枚举被阻断并显示引用方；新建标准文档为 v4、打开 v3 草稿保存后采用服务端返回的 v4 基准；键盘、窄视口与浅深主题操作可用。
- [x] Step 2：运行 `rtk npm --prefix web run test:unit -- draftModel.test.ts publishModel.test.ts CascadePropertyEditor.test.ts`，确认新增用例失败；再运行 `rtk npm --prefix web run test:e2e -- tests/e2e/standards-editor.spec.ts --workers=1 --retries=0` 定向确认失败。
- [x] Step 3：实现纯草稿变换与独立级联编辑组件，在 `StandardEditor.vue` 只做分区装配，在 `publishModel.ts` 完成评审分区映射与跳转，登记中英文文案与后端错误码定位，不复制发布最终校验。
- [x] Step 4：执行 `rtk npm --prefix web run test:unit`、`rtk npm --prefix web run check:i18n`、`rtk npm --prefix web run check:ui`、`rtk npm --prefix web run build`，并执行 `rtk npm --prefix web run test:e2e -- tests/e2e/standards-editor.spec.ts --workers=1 --retries=0`；更新 `changelog.md`。
- [x] Step 5：只暂存本任务文件并以简体中文动词开头提交。

### Task 6：创建向导联动与草稿恢复

**Files:** `web/src/features/creation/inputModel.ts`、`store.ts`、`types.ts`、`web/src/components/creation/ProjectStep.vue`、`GroupsStep.vue`、`GroupBatchDialog.vue`、`web/src/i18n/locales/zh-CN/creation.ts` 与 `en-US/creation.ts`；`web/src/features/creation/store.test.ts`、`web/tests/e2e/create-sheetset-input.spec.ts`、`create-sheetset-review.spec.ts`。

**Interfaces:** 项目信息页展示 `sheetset` 级联，图纸组页每组展示 `sheet` 级联；上级变更只清空本对象的依赖值并使预览失效；批量上级更改只清空选中组；批量级联更改按所有选中组的当前上级取合法候选交集，并把 `batchUpdate` 改为先全量校验、再一次提交（任何一组不合法即整批拒绝，清空操作除外）；草稿恢复保留后端返回的非法原值和组定位，显示可修正诊断。

- [x] Step 1：写失败测试：两级未选上级时级联禁用且为空，选道路/燃气时选项不同；修改图纸组 A 上级只清空 A 的同源级联，B 不变；新组复制上级/级联配对；批量上级更改只清空选中组；批量级联设置对混合上级不合法时整批拒绝且所有选中组保持原值；草稿恢复非法组合保留原值、可见错误与清空入口；有效组合可保存、重新预览并显示最终值。
- [x] Step 2：运行 `rtk npm --prefix web run test:unit -- store.test.ts`，确认新增用例失败；再运行 `rtk npm --prefix web run test:e2e -- tests/e2e/create-sheetset-input.spec.ts tests/e2e/create-sheetset-review.spec.ts --workers=1 --retries=0` 定向确认关键场景失败。
- [x] Step 3：在输入模型建立按作用域/对象解析候选的纯函数，在 store 处理图纸集、单组与批量上级更改（批量先全量校验再提交）、交集限制及预览失效；在 `ProjectStep.vue`、`GroupsStep.vue`、`GroupBatchDialog.vue` 渲染可访问候选、禁用提示与整批拒绝反馈；后端诊断定位继续复用项目字段/图纸组机制。
- [x] Step 4：执行 `rtk npm --prefix web run test:unit`、`rtk npm --prefix web run check:i18n`、`rtk npm --prefix web run build`，并执行 `rtk npm --prefix web run test:e2e -- tests/e2e/create-sheetset-input.spec.ts tests/e2e/create-sheetset-review.spec.ts --workers=1 --retries=0`；更新 `changelog.md`。
- [x] Step 5：只暂存本任务文件并以简体中文动词开头提交。

### Task 7：契约、回归和文档收口

**Files:** `docs/dst-manager/specs/SPEC-DM-021-cascading-enum-properties.md`、`SPEC-DM-017-standard-properties-and-dwg-naming.md`、`SPEC-DM-018-standard-driven-sheetset-creation-ui.md`、`docs/dst-manager/guides/GUIDE-DM-006-user-guide.md`、`docs/dst-manager/README.md`、`.planning/plans/dst-manager/PLAN-DM-047-cascading-enum-properties.md`、`.planning/plans/dst-manager/README.md`、`changelog.md`；按 API/类型生成结果补相关文件。

**Interfaces:** 不新增业务接口；核对标准文档、标准包、创建 API、XLSX、Web 与 DST 输出的同一字段语义；SPEC-DM-021 状态从 `draft` 收口并同步索引。

- [x] Step 1：补两级跨链路回归：v3 标准基线、v4 包往返、`SheetSet`/`Sheet` XLSX 错配、API 直写、组级预览摘要失效与 DST 仅含对应目标属性；缺少真实 CAD 环境时记录跳过，不伪造运行结论。
- [x] Step 2：运行 `rtk uv run ruff check .`、相关 `rtk uv run pytest ... -q`、`rtk uv lock --check`、`rtk npm --prefix web run check:api`、`check:i18n`、`check:ui`、`test:unit`、`build` 和相关 Playwright E2E；仅在实际验证后记录通过数量。标准包 Schema 变化无需数据库迁移，若实施时触及模型则另补 Alembic 全新库升级验证。
- [x] Step 3：同步用户指南和既有规范中的级联入口、创建与 XLSX 说明；检查本 Spec 的每条验收场景均有对应测试和实现，更新 SPEC-DM-021 状态与 `.planning/README.md`、计划 README 索引；更新本计划实际验证摘要后才将状态标为 `completed`。
- [x] Step 4：检查 `git diff --check`、`git status --short` 与暂存树，确认私有目录、凭据和生成物未入提交；只暂存本任务文件并以简体中文动词开头提交。

## 完成条件

SPEC-DM-021 §8 的六组验收场景全部有自动化或明确记录的真实环境验证，其中「删除被级联引用的上级枚举属性被阻断」与「批量级联整批拒绝」有专门用例；`sheetset` 与 `sheet` 级联只引用同级普通枚举；v3 标准继续使用且只读零写入，v3 含级联字段被拒绝，显式保存由后端升级 v4；级联配置在 v4 标准包往返不丢失；网页项目/图纸组联动、XLSX 两表静态下拉与后端成对校验一致；任一组非法组合均无法预览或创建；创建后 DST 只在对应节点物化上级和级联属性；Ruff、相关 pytest、Web 契约/单元/构建和定向 E2E 均有实际通过记录；SPEC-DM-021 状态与索引已收口。真实 AutoCAD 系统测试只在用户或运行环境显式启用且具备 Core Console、插件与私有样本时执行。

## 实际验证摘要

- Task 1–7 均完成。Task 1–6 提交依次为 `5d7c59a`、`daa411c`、`5a8c891`、`ffe51eb`、`ee5c7df`、`08d6113`；Task 7 的文档、测试与本摘要随该任务提交。
- §8 场景与回归对应：标准两作用域 Schema、源项与引用删除保护由 `test_drawing_standards.py`、`test_standard_rules.py` 和 `OrdinaryPropertyEditor.test.ts` 覆盖；v3 读取/只读零写入/显式升级与 v4 包往返由 `test_standard_api.py` 覆盖；创建页联动、草稿恢复和整批批量拒绝由 Web 单测及创建向导 E2E 覆盖；XLSX 两作用域错配由 `test_creation_xlsx_rows.py` 覆盖；API 直写与组级级联变化使旧预览失效由 `test_creation_api.py` 覆盖；预览求值和 DST 作用域物化由 `test_creation_planning.py`、`test_creation_job.py` 覆盖。
- 验证通过：`rtk uv run ruff check .`、相关 pytest **354 passed**、`rtk uv lock --check`、Web `check:api` / `check:i18n`（1664 键、11 域）/ `check:ui`、单测 **359 passed**、生产构建、定向 Playwright **99 passed**。生产构建提示主 JavaScript 包为 781.54 kB，超出 500 kB 建议阈值。
- 未修改数据库模型或迁移。真实 AutoCAD 系统测试跳过：执行环境未设置 `DST_MANAGER_RUN_AUTOCAD=1`。
