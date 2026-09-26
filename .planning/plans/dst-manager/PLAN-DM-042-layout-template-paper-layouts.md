---
id: PLAN-DM-042
title: 布局模板单文件资产与勾选启用图幅实施计划
status: completed
owners:
  - dst-manager
created: 2026-09-26
updated: 2026-09-26
related:
  - ARCH-DM-001
  - ARCH-DM-007
  - SPEC-DM-016
  - SPEC-DM-017
  - SPEC-DM-018
  - PLAN-DM-035
  - PLAN-DM-040
  - PLAN-DM-041
---

# 布局模板单文件资产与勾选启用图幅实施计划

> **实施要求：** 按任务执行 RED → 最小实现 → GREEN → 复核 → 提交；复选框仅在实际完成后勾选。实施前阅读本计划引用的规范、[ARCH-DM-001](../../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)、[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) 和相关源码、测试。前端改动必须严格遵守 ARCH-DM-007 视觉契约：只复用既有 Ui 原语（UiButton/UiIconButton/UiIcon/UiInput/UiSelect/FormField/dialogFocus）、三层令牌（字号/控件高度/圆角/颜色/间距必须经语义令牌或登记的原始令牌）、按钮必须 `type="button"`、输入必须有可见 label，并通过 `check:ui` 静态门禁；不得把静态 demo 的自创样式带入产品。

**目标：** 模板资产统一为"一个资产对应一个 DWG 文件"；布局模板的启用图幅不再是人工输入的 role 声明，而是从受控副本 DWG 读取全部非 `Model` 布局后由用户勾选声明（`paper_layouts`）；消除检查期"恰好相等"与执行期"包含即可"的口径不对称，删除"未声明布局阻断"规则。

**架构：** `StandardAsset` 从 `files: tuple[StandardAssetFile, ...]`（多文件 + role）改为 `file: str`（单文件受控副本路径）+ `paper_layouts: tuple[str, ...]`（勾选启用图幅，仅布局模板有意义）。资产检查只验证：DWG 可读、勾选 ⊆ 实际非 `Model` 布局、布局模板勾选非空；基础模板只验证 DWG 可读。执行期按 `group.paper_layout ∈ asset.paper_layouts` 判定图幅合法并直接使用 `asset.file`。本机模板受控复制端点在复制成功后顺带读取受控副本布局并随响应返回，供编辑器渲染勾选清单。

**技术栈：** Windows 11、Python ≥3.12、UV、FastAPI、Vue 3、TypeScript、Vite、Vitest、Playwright、pywebview/WebView2。

**规范依据：** [SPEC-DM-016](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md) §8（本计划 Task 9 修订）、[SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md)、[SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md)、[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md)。

## 范围、依赖和已确认裁决

- 用户已确认三项裁决：
  1. **单文件结构**：一个布局模板资产只对应一个 DWG 文件（可含多个布局）；基础模板顺带统一为同一单文件结构，role 字段整体退役。
  2. **勾选声明**：启用图幅不手动输入，从提交 DWG 读取全部非 `Model` 布局后由用户勾选；未勾选的布局是中性状态，不再产生"未声明布局"阻断。
  3. **不迁移**：旧多文件/role 形状的标准包与草稿不做自动迁移，要求重新导入/重建。
- 交互已用静态 demo 确认：不显示 `Model` 行；提供全选/清空批量勾选；替换 DWG 后自动保留仍存在的勾选、移除失效项并提示。
- 勾选与布局名的比较保持严格字符串匹配（不去空格、不转换大小写），与布局名来源于同一 DWG 的读取结果，正常流程下天然一致。
- 本计划不改 DST/DWG 发布器、CAD SCR、插件与创建图纸集的执行流程语义；`resolve_layout_template`/`resolve_base_template` 的返回契约（包内相对路径 + 稳定诊断码）不变，仅判定依据从 role 匹配改为勾选成员判断。
- 受控资产信任模型不变：草稿只保存 `assets/managed-<uuid4hex>.dwg|.dwt` 包内相对路径，本机绝对路径不进文档；三重路径门禁（`STANDARD_ASSET_PATH_INVALID`/`STANDARD_ASSET_FILE_MISSING`/包内一致性）继续由后端执行；孤儿副本清理按 `managed-` 前缀与当前引用集合执行。
- Web 服务继续只监听 `127.0.0.1`。

## 版本与接口契约

| 对象 | 约定 |
| --- | --- |
| 领域模型 | `StandardAsset {asset_id: str, kind: str, file: str, paper_layouts: tuple[str, ...] = ()}`；`file` 是包内相对路径，两类资产都必填；`paper_layouts` 仅布局模板有意义，是勾选启用图幅的有序集合（解析时去重保序、丢弃空白项）。`StandardAssetFile` 数据类与 `files`/`role` 字段删除。 |
| 文档 JSON | `assets[*]` 写作 `{"asset_id", "kind", "file", "paper_layouts": [...]}`；基础模板 `paper_layouts` 恒空。旧 `files`/`role` 形状在 schema 校验时报错（稳定码拒绝），不自动转换。 |
| 布局检查规则 | 布局模板：① DWG 可读（能力缺失/读取失败转诊断）；② `paper_layouts` 为空 → `STANDARD_PAPER_LAYOUTS_EMPTY`（error）；③ 存在勾选但 DWG 无同名非 `Model` 布局 → 每项一个 `STANDARD_PAPER_LAYOUT_MISSING`（error）。基础模板：只验证 DWG 可读。`STANDARD_LAYOUT_NAME_MISMATCH` 退役，后端不再产生。 |
| 执行期判定 | `resolve_layout_template`：`asset.file` 直接定位文件；`group.paper_layout` 必须 ∈ `asset.paper_layouts`，否则 `CREATION_PAPER_LAYOUT_INVALID`。`resolve_base_template` 返回 `asset.file`。创建选项 `layouts` 来自 `asset.paper_layouts`。 |
| 复制端点 | `POST /api/standards/drafts/{draft_id}/asset-files` 请求加可选 `cad_version`；响应扩展为 `{path, layouts: string[], layouts_error: string | null}`：复制成功后用该 `cad_version` 读取受控副本布局，成功填 `layouts`（含 `Model`，由前端过滤）；能力缺失/读取失败时 `layouts=[]` 且 `layouts_error` 为对应稳定码；未传 `cad_version` 不读取（`layouts_error=null`）。复制结果不受布局读取失败影响。 |
| 检查端点 | `AssetInspectionResponse {asset_id, kind, layouts, diagnostics}` 形状不变；`layouts` 仍返回 DWG 实际布局（含 `Model`，前端过滤展示）。 |
| 前端类型 | `CopiedAssetFile` 加 `layouts`/`layoutsError`；`CopyAssetFileInput` 加 `cadVersion`；`DraftAsset` 改单文件形状。经 `generate:api` 再生 `openapi.json`/`schema.d.ts`。 |

## 交付顺序

| 批次 | 任务 | 可独立验收的结果 | 前置条件 |
| --- | --- | --- | --- |
| A：领域与基础设施 | 1 → 2 → 3 | 单文件领域模型、schema 拒绝旧形状、路径门禁与孤儿清理按单文件工作 | 无 |
| B：应用与接口 | 4 → 5 | 新检查规则、执行期按勾选判定、复制响应带布局 | A |
| C：前端 | 6 → 7 | 类型再生、勾选编辑器与检查面板符合视觉契约 | B |
| D：测试与文档 | 8 → 9 → 10 | 全量回归、规范修订、changelog | A–C |

## Review Focus

- `paper_layouts` 解析：去重保序、丢弃空白项、非字符串条目拒绝；基础模板忽略勾选不报错。
- 检查口径：勾选 ⊆ 实际（非 `Model`）；"未勾选布局"绝不产生诊断；检查失败（CAD 缺失/读取失败）不得误报为勾选失效。
- 复制端点：布局读取失败不影响复制成功；响应契约向后兼容字段新增。
- 视觉契约：新 UI 只用既有 Ui 原语与令牌；`check:ui`、`check:i18n`、`check:api` 全绿。
- 兼容性：旧 `files`/`role` 文档在保存与导入时稳定拒绝（不静默转换）；无真实历史数据需迁移。

## Task 列表

### Task 1：领域模型单文件化

- Files: `src/dst_manager/domain/standard_models.py`、`src/dst_manager/domain/creation_plan_inputs.py`
- Interfaces: `StandardAsset`（新四字段形状）；`resolve_layout_template`/`resolve_base_template` 按 `file`/`paper_layouts` 判定
- [x] RED：更新涉及 `StandardAsset` 构造与执行期判定的单元测试夹具（`tests/unit/test_creation_plan_inputs.py` 等，以实际 grep 为准）
- [x] GREEN：删除 `StandardAssetFile`；`StandardAsset` 改 `{asset_id, kind, file, paper_layouts}`；`resolve_layout_template` 校验 `paper_layout ∈ asset.paper_layouts`；`resolve_base_template` 返回 `asset.file`

### Task 2：schema 解析与校验

- Files: `src/dst_manager/domain/standard_schema.py`
- Interfaces: `_parse_asset` 解析 `file`（必填非空字符串）与 `paper_layouts`（可选字符串数组，去重保序、丢弃空白项）；旧 `files`/`role` 形状以稳定诊断拒绝
- [x] RED：schema 单测覆盖新形状合法、缺 `file`、空白 `file`、`paper_layouts` 含空白项（被丢弃）与非字符串（拒绝）、重复项去重、旧形状拒绝
- [x] GREEN：实现解析与诊断

### Task 3：基础设施路径门禁与孤儿清理

- Files: `src/dst_manager/infrastructure/standards/asset_paths.py`、`src/dst_manager/infrastructure/standards/store.py`
- Interfaces: `declared_asset_paths`/`resolve_asset_files`/`_prune_managed_assets` 遍历单文件 `asset.file`
- [x] RED：更新 store/路径门禁相关测试夹具为单文件形状
- [x] GREEN：实现单文件遍历；清理语义不变（`managed-` 前缀 + 当前引用集合）

### Task 4：资产检查规则重写

- Files: `src/dst_manager/application/standard_assets.py`
- Interfaces: `inspect_standard_asset`；新码 `STANDARD_PAPER_LAYOUTS_EMPTY`、`STANDARD_PAPER_LAYOUT_MISSING`；删除 `_layout_mismatch`
- [x] RED：重写 `tests/unit/test_standard_assets.py` 检查用例（勾选子集通过、失效勾选逐项报错、空勾选报错、基础模板跳过比较、检查失败不误报勾选失效、路径/文件缺失诊断不变）
- [x] GREEN：实现新规则；`layouts` 返回实际布局；基础模板仍读布局但不比较

### Task 5：复制端点读布局与 API 契约

- Files: `src/dst_manager/application/service.py`（或 `standard_assets.py` 对应方法）、`src/dst_manager/interfaces/standard_contracts.py`、`src/dst_manager/interfaces/standard_api.py`
- Interfaces: `copy_draft_asset_file(draft_id, source_path, cad_version=None)` 返回 `{path, layouts, layouts_error}`；`StandardAssetCopyRequest.cad_version`、`StandardAssetCopyResponse.layouts/layouts_error`
- [x] RED：复制测试断言 `layouts`（fake_reader 成功/能力缺失/读取失败/未传 `cad_version` 不读取）；API 集成测试更新响应契约
- [x] GREEN：实现复制后读取；读取失败不影响复制结果

### Task 6：前端模型与类型再生

- Files: `web/src/features/standards/draftModel.ts`、`web/src/features/standards/publishModel.ts`、`web/src/features/standards/types.ts`、`web/src/api/standards.ts`、`web/src/api/openapi.json`、`web/src/api/schema.d.ts`
- Interfaces: `DraftAsset {asset_id, kind, file, paper_layouts}`；`declaredPaperLayouts`（原 `declaredRoles`）；布局差异函数改为"勾选失效"判定；`CopiedAssetFile.layouts/layoutsError`
- [x] RED：`draftModel.test.ts`/`publishModel.test.ts` 资产用例重写（单文件解析、勾选失效逐项、空勾选、未引用警告、旧形状容错为待修正状态）
- [x] GREEN：实现模型与映射；运行 `npm --prefix web run generate:api` 再生类型

### Task 7：编辑器与检查面板改造（视觉契约）

- Files: `web/src/components/standards/TemplateAssetsEditor.vue`、`web/src/components/standards/AssetInspectionPanel.vue`、`web/src/i18n/locales/*` 各语言 `standards.ts`
- Interfaces: 单文件路径行（选择/替换本机模板 + 开发态来源路径输入）；布局勾选清单（复选框 + 全选/清空）；替换 DWG 后自动保留仍存在勾选并提示移除项；检查面板布局表改为"实际布局 × 启用状态"中性展示 + 勾选失效单列
- [x] RED/Vitest：更新组件测试（勾选写回 `paper_layouts`、全选/清空、替换保留交集、Model 不显示）
- [x] GREEN：实现 UI；i18n 新增键（勾选清单、全选/清空、失效提示等）、删除 `fileRole`/`addFile`/`removeFile`/`layoutExtra` 等退役键；全程只用 Ui 原语与既有令牌；四语言同步

### Task 8：全量测试回归

- [x] `uv run ruff check .`
- [x] `uv run pytest -q`（含 schema、store、creation、API 集成等受影响夹具全部更新）
- [x] `npm --prefix web run test:unit`、`check:api`、`check:i18n`、`check:ui`、`build`
- [x] 涉及资产检查的 Playwright 用例更新并本地通过（真实桌面 G9 验证留待用户环境）

### Task 9：规范与文档修订

- Files: `docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md`、`changelog.md`
- [x] SPEC-DM-016 §8.2 重写为勾选模型（单文件、勾选 ⊆ 实际、空勾选阻断、未勾选中性）；§8.1 同步单文件与复制响应描述
- [x] `changelog.md` 当日追加记录

### Task 10：收尾

- [x] 复核所有复选框与"实际验证"记录；提交前确认未混入 demo 产物与敏感数据

## 完成标准

- 领域、schema、应用、接口、前端全部运行在单文件 + 勾选模型上；`role` 与 `StandardAssetFile` 在产品代码中无残留引用（历史文档仅在规范修订记录中提及）。
- 检查期与执行期口径一致：勾选 ⊆ 实际布局；创建图纸集只允许勾选图幅。
- 视觉契约门禁（`check:ui`）与全部自动化测试通过；`ruff`、`pytest`、`npm run build` 全绿。
- SPEC-DM-016 §8 与实际实现一致；changelog 已记录。

## 修订记录

| 日期 | 修订 |
| --- | --- |
| 2026-09-26 | 初版：依据用户三项裁决与静态 demo 交互确认立项。 |
| 2026-09-26 | 实施完成：Task 1–10 全部执行并勾选。实际验证：`uv run ruff check .` 通过；`uv run pytest -q` 仅剩 `tests/unit/test_setup_bat.py` 两条与本项目无关的既有环境失败（GBK 代码页中文乱码，经 `--lf` 复核）；`npm --prefix web run test:unit`（340 例）、`check:api`/`check:i18n`/`check:ui`/`build` 通过；受影响的三个 Playwright spec 共 75 例通过。真实桌面 G9 验证按计划留待用户环境。SPEC-DM-016 §8 已同步修订，changelog 已记录。 |
