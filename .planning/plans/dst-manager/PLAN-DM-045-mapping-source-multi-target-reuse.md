---
id: PLAN-DM-045
title: 映射源一对多复用实施计划
status: completed
owners:
  - dst-manager
created: 2026-09-27
updated: 2026-09-27
related:
  - SPEC-DM-017
  - PLAN-DM-035
  - PLAN-DM-038
  - PLAN-DM-040
  - PLAN-DM-044
---

# 映射源一对多复用实施计划

> **执行约定：** 本计划由用户批准后实施；复选框只在实际完成并登记验证后勾选。

**目标：** 解除「一个普通枚举属性最多被一个映射属性用作源」的限制，使同一枚举源可被多个映射属性独立复用（例：`专业名称 → 专业代码`、`专业名称 → 图册名称`、`专业名称 → 图册代码` 各为一个映射属性）；同时**彻底移除**随之作废的 `STANDARD_MAPPING_SOURCE_DUPLICATE` 阻断码，包括后端诊断、前端诊断、`MODAL_CODES` 分支、中英文文案与全部回归用例，**不保留任何非阻断 warning**。

**架构：** 该约束仅是产品规则，不承载技术不变量。领域层 [compile_standard_properties](../../../src/dst_manager/domain/standard_rules.py) 与 [evaluate_standard_properties](../../../src/dst_manager/domain/standard_rules.py) 按 `property_id` 逐个独立迭代映射，同源多映射互不干扰；属性名已全局唯一（`STANDARD_PROPERTY_NAME_DUPLICATE`），每个映射属性各自物化为一个 DST 文本属性；[referencesTo](../../../web/src/features/standards/draftModel.ts) 已按列表返回全部引用方，删除保护天然支持多引用。因此本轮为**纯放宽**：删除 UI 源占用过滤与前后端两处发布诊断的唯一性判定，保留作用域过滤与源类型校验。数据结构、Schema 版本、HTTP 契约、求值链、物化路径与发布事务均不变，**无数据迁移**。

**技术栈：** Windows 11、Python 3.12（UV、Ruff、pytest）、Vue 3 + TypeScript + Vite（Vitest、Playwright、`node:test`）。

**范围裁决（方案 A，用户 2026-09-27 确认）：** 取「放开源唯一占用」而非「把单个映射属性扩成多目标列」。后者与 [SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md) §5.2「当前派生属性就是目标」及「属性物化为一个 DST 属性」的模型冲突，需重做数据模型、编辑器与求值链，收益与风险不成比例，不采纳。

**移除错误码的合规说明：** `STANDARD_MAPPING_SOURCE_DUPLICATE` 是运行时计算、不持久化的诊断码，只由后端 `publish_diagnostics` 与前端 `propertyPublishDiagnostics` 两处产生；本计划确认无其它消费者后整体删除码定义与文案，不保留休眠码，避免死代码。

## 前置条件

- [SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md) §5.2/§7.1/§9 的现行修订为实施基准；§5.2 第 132 行是待改写条款。
- 已发布标准必然通过过原唯一性门禁，历史数据不可能存在同源多映射；放开为前向兼容，无需迁移或兼容层。
- 本计划不涉及真实 AutoCAD 能力，不需要真实 CAD 作为实施前置；最终真实桌面复验按既有约定另行登记。

## 全局约束

- 任务开始前检查 `rtk git status --short`，保留用户已有改动；只暂存本任务文件。每次实际代码修改同步更新根 `changelog.md`，提交信息用简体中文动词短语。
- **不改** HTTP/API 契约、Schema 版本、字段含义、`source_property_id` 单值结构、props/emits、求值顺序与物化路径。
- **保留**源类型校验（`STANDARD_MAPPING_SOURCE_INVALID`）与作用域校验（`STANDARD_MAPPING_SCOPE_INVALID`），本轮只删唯一占用。
- 中英文语言包必须对称：删除 `sourceOccupied` 与 `STANDARD_MAPPING_SOURCE_DUPLICATE` 文案，并改写 `mapping.source` 提示；`check:i18n` 必须退出 0。
- 诊断码属于对外契约，删除前确认无其它运行时消费者；历史计划文档（PLAN-DM-035 内嵌旧 `validateMapping` 片段）只读保留，不回改。

## 任务

### Task 1: 修订规范正文

**Files:**
- Modify: `docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md`（§5.2、§7.1、§9、元数据 `updated`/`related`，末尾新增「修订记录」）

- [x] **Step 1: 改写 §5.2 第 132 行条款**

把「一个普通枚举属性最多被一个映射属性用作源，不允许两个映射属性共享同一源」改为允许复用，例如「一个普通枚举属性可以被多个映射属性用作源；各映射属性独立维护自己的映射表与确认快照」。

- [x] **Step 2: 修订 §7.1 阻断错误清单**

删除「源被重复占用」，保留「映射源类型/作用域非法、目标为空或枚举未覆盖」。

- [x] **Step 3: 修订 §9 验收第 3 条**

把「映射源类型、作用域和唯一性门禁」改为「映射源类型与作用域门禁、同源多映射允许、目标重复允许、目标空值阻断」。

- [x] **Step 4: 元数据与修订记录**

`updated` 改为 2026-09-27，`related` 增列 `PLAN-DM-045`，末尾「修订记录」登记本次变更（放宽源复用、移除 `STANDARD_MAPPING_SOURCE_DUPLICATE`、不保留 warning）。

### Task 2: 后端移除源唯一占用诊断

**Files:**
- Modify: `src/dst_manager/domain/standard_rules.py`（`publish_diagnostics`）
- Modify: `tests/unit/test_standard_rules.py`

- [x] **Step 1: 写失败测试**

把 `test_two_mappings_sharing_a_source_are_rejected` 改写为「同源多映射被允许且各自独立求值」：构造两个共享 `prop-major` 的映射，断言 `publish_diagnostics` 无 `STANDARD_MAPPING_SOURCE_DUPLICATE`，且 `evaluate_standard_properties` 分别得到各自目标值。

- [x] **Step 2: 移除诊断分支**

删除 `publish_diagnostics` 中的 `claimed` 字典与唯一性判定，仅保留目标非空与待确认判定，并同步更新 docstring（删除「源唯一」表述）。

- [x] **Step 3: 运行定向测试**

Run: `uv run pytest tests/unit/test_standard_rules.py -q`

### Task 3: 前端草稿模型

**Files:**
- Modify: `web/src/features/standards/draftModel.ts`
- Modify: `web/src/features/standards/draftModel.test.ts`
- Modify: `web/src/features/standards/publishModel.test.ts`

- [x] **Step 1: 写失败测试**

`draftModel.test.ts`「reports mapping source duplication…」改为断言同源多映射不再产生该码；`publishModel.test.ts`「passes the duplicated source name to the {source} placeholder」改为同源多映射不进入 `blockingErrors`。

- [x] **Step 2: 放开源过滤**

`selectableMappingSources` 删除 `claimed` 计算与过滤，保留作用域过滤与「当前已选源恒在列表内」。

- [x] **Step 3: 移除前端诊断**

`propertyPublishDiagnostics` 删除 `mappingSources` 字典与 `STANDARD_MAPPING_SOURCE_DUPLICATE` 分支。

- [x] **Step 4: 运行定向测试**

Run: `Set-Location web; npm run test:unit -- src/features/standards/draftModel.test.ts src/features/standards/publishModel.test.ts; Set-Location ..`

### Task 4: 前端组件与文案

**Files:**
- Modify: `web/src/components/standards/MappingPropertyDialog.vue`
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/components/standards/DerivedPropertyEditor.test.ts`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`、`web/src/i18n/locales/en-US/standards.ts`

- [x] **Step 1: 改写组件测试**

`DerivedPropertyEditor.test.ts` 夹具改为「同源复用」（`prop-major` 被 `prop-alias` 与 `prop-code` 共用），删除「只提供未被占用的源」「占用源禁用项」与依赖重复源诊断的用例，改为断言可选源包含已复用源。

- [x] **Step 2: 调整映射弹窗**

`MappingPropertyDialog.vue` 删除 `occupied` 计算、`optionLabel` 占用后缀与 `:disabled`；同步修正文件头与 `options` 注释。

- [x] **Step 3: 调整编辑器壳层**

`StandardEditor.vue` 从 `MODAL_CODES` 移除 `STANDARD_MAPPING_SOURCE_DUPLICATE`；随该码作废的 `{source}` 占位符链路在 `publishModel`、`DerivedPropertyEditor`、`OrdinaryPropertyEditor`、`StandardEditor` 与 `DraftDiagnostic.detail` 注释中一并清理。

- [x] **Step 4: 调整文案（中英对称）**

删除 `mapping.sourceOccupied` 与 `diagnostic.STANDARD_MAPPING_SOURCE_DUPLICATE`；`mapping.source` 改为「源属性（仅普通枚举）」/「Source property (ordinary enum only)」。

- [x] **Step 5: 运行定向测试与 i18n 门禁**

Run: `Set-Location web; npm run test:unit -- src/components/standards/DerivedPropertyEditor.test.ts; npm run check:i18n; Set-Location ..`

### Task 5: e2e 回归

**Files:**
- Modify: `web/tests/e2e/standards-editor.spec.ts`

- [x] **Step 1: 改写「映射源唯一占用与组合字段范围」**

改名为「映射源可复用与组合字段范围」，源占用断言改为「新增映射可再次选择 `prop-major` 并生效」，组合字段范围与 DWG 命名部分保持不变。

- [x] **Step 2: 复核其它映射 e2e**

核查 `standards-editor.spec.ts`、`standards-visual-evidence.spec.ts` 与 `fixtures/standards.ts`、`fixtures/creation.ts`，无残余唯一占用假设。

- [x] **Step 3: 运行定向 e2e**

Run: `Set-Location web; npx playwright test tests/e2e/standards-editor.spec.ts; Set-Location ..`

### Task 6: 全量验证与收口

- [x] **Step 1: Python 门禁**

Run: `$env:UV_LINK_MODE = "copy"; uv run ruff check .; uv run pytest -q`

- [x] **Step 2: 前端门禁**

Run: `Set-Location web; npm run test:unit; npm run test:contracts; npm run check:i18n; npm run check:ui; npm run build; Set-Location ..`

- [x] **Step 3: 更新 changelog 并勾选任务**

在根 `changelog.md` 2026-09-27 章节登记本次变更与验证结果；勾选本计划全部复选框，状态置 `completed`；同步维护 Plan 索引与执行资料索引。

## 完成标准

- 同一枚举源可被任意多个映射属性复用，多个属性各自独立维护映射表、确认快照与物化值。
- 全仓库不再存在 `STANDARD_MAPPING_SOURCE_DUPLICATE` 的运行时产生点、`MODAL_CODES` 分支、中英文文案与断言；不新增 warning。
- 源类型校验、作用域校验、目标非空阻断、待确认 warning、删除引用保护行为不变。
- Ruff、pytest、`test:unit`、`check:i18n`、`check:ui`、`build` 与定向 e2e 全部通过。

## 风险与回退

- **风险：诊断码删除属契约变化。** 已确认仅后端 `publish_diagnostics`、前端 `propertyPublishDiagnostics`、`MODAL_CODES`、中英文语言包、测试五类消费者；诊断不持久化，删除后无残留数据影响。
- **风险：既有认定同源即错误的产品预期。** 本计划按用户裁决改为合法，SPEC-DM-017 同步改写，避免规范与实现漂移。
- **回退：** 变更集中且无数据迁移；如需回退，恢复三处判定与文案即可，不涉及已发布标准数据。

## 实际验证摘要

- **规范：** SPEC-DM-017 §5.2/§7.1/§9 已改写并新增 §11 修订记录，`updated` 与 `related` 同步。
- **后端：** `standard_rules.publish_diagnostics` 移除唯一占用判定与 `claimed`；`tests/unit/test_standard_rules.py` 定向用例通过，`test_two_mappings_may_share_one_source_and_evaluate_independently` 断言两映射各自求值为 `RQ` / `RQ2`。
- **前端：** `draftModel`、`publishModel`、`MappingPropertyDialog.vue`、`StandardEditor.vue` 与中英文语言包按新语义改造；`{source}` 占位符链路清理完毕。
- **测试：** `uv run ruff check .` 通过；`uv run pytest -q` 仅 `tests/unit/test_setup_bat.py` 两条与本任务无关的既有环境失败（GBK 代码页中文乱码，与 PLAN-DM-042 记录的同一环境问题一致，`--tb=no` 复核确认失败仅集中于该文件）；`npm run test:unit` **339 passed**、`test:contracts` **114 passed**、`check:i18n`（**1620 键**对称）/`check:ui`/`build`（含 `check:api`、`vue-tsc`、`vite build`）退出码 0；`npx playwright test tests/e2e/standards-editor.spec.ts` **64 passed**。
- **未执行：** 真实 AutoCAD 系统测试（本轮不涉及 CAD 能力）；真实 Windows WebView2 缩放复验（沿用既有约定，不阻断本计划关闭）。
