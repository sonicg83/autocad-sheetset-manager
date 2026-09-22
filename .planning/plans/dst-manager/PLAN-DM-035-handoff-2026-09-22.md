---
id: PLAN-DM-035-HANDOFF
title: PLAN-DM-035 实施接手文档（Task 1-4 已完成）
created: 2026-09-22
status: active
---

# PLAN-DM-035 接手文档（2026-09-22 暂停点）

> 执行方式：Native 模式（当前会话顺序执行 Task 1-11，无子代理、无 worktree，直接在 `main` 分支提交）。
> 计划文件：[`PLAN-DM-035-drawing-standard-platform.md`](./PLAN-DM-035-drawing-standard-platform.md)。
> 计划复选框尚未统一勾选，完成状态以本文档与 git log 为准。

## 一、进度总览

| Task | 状态 | Commit | 说明 |
|---|---|---|---|
| 1 领域模型与 Schema | ✅ 完成 | `275fac1` | 领域对象 + 严格解析器 |
| 2 封闭规则求值 | ✅ 完成 | `ff75611` | 拓扑编译 + 求值 |
| 3 标准包与标准库 | ✅ 完成 | `ab9c937` | `.dststandard` 安全读取 + 官方/用户库 |
| 4 草稿/发布/快照编排 | ✅ 完成 | `79fc60c` | StandardOperations mixin + 保留属性保护 |
| 5 模板资产检查与 DST 导入 | 🔶 未开始（仅探索） | — | 见 §五 |
| 6-11 API/前端/证据 | ⬜ 未开始 | — | |

验证基线：Task 4 完成时 `test_standard_service + test_acsm_custom_properties + test_v021_editing` 76 项全过，Ruff 干净。

## 二、已交付接口（后续 Task 直接依赖）

### 领域层 `src/dst_manager/domain/standards.py`
- 冻结 dataclass：`DrawingStandard`、`StandardProperty`、`StandardRule`、`StandardSegment`、`StandardAsset`、`StandardAssetFile`、`NumberingPolicy`、`StandardDependency`。
- `parse_standard_document(data: Mapping) -> DrawingStandard`、`loads_standard_document(text)`；错误 `StandardSchemaError`（消息以 `STANDARD_*` 码开头）。
- **标准文档 JSON 格式**（Task 6 契约 / Task 9 编辑器必须对齐）：
  - 顶层：`schema_version`(仅 1)、`standard_id`（小写域式 `^[a-z][a-z0-9-]*(\.[a-z0-9-]+)*$`，大小写不合规即拒绝）、`version`（`^\d+\.\d+\.\d+$`）、`name`、`supported_cad_versions`（非空字符串列表）、`properties`、`rules`、`assets`、`numbering`、`dependencies`。
  - `properties[]`：`name`、`scope`（`sheetset`/`sheet`/`subset`/`derived`，`subset` 仅预留）、`required`、`default_value`、`enum_values`、`description`。
  - `rules[]`：`rule_id`、`kind`（`required`/`enum`/`fixed`/`mapping`/`compose`/`numbering`/`naming`）、`target`（`scope.字段名`）、`source`（mapping 必填）、`value`（fixed）、`allowed`（enum）、**`table`（mapping 必填，形如 `[["燃气","RQ"],...]`，解析期拒绝空值与重复源值）**、`segments`（compose：`{"field":...,"format":...}` 或 `{"literal":...}`，field 与 literal 互斥）。
  - `assets[]`：`asset_id`、`kind`（`base-template`/`layout-template`）、`files[]`（`path` 包内相对路径、`role` 如图幅枚举值）。
  - `numbering`：`sequence_field`（如 `subset.sequence`）、`digits`（正整数）、`start`。
  - `dependencies[]`：`extension_id`/`capability_id`/`min_version`（Task 6 用）。

### 领域层 `src/dst_manager/domain/standard_rules.py`
- `compile_standard_rules(standard) -> CompiledStandard`：编译期拒绝 `STANDARD_RULE_FIELD_UNKNOWN`（未知引用）、`STANDARD_RULE_TARGET_DUPLICATE`、`STANDARD_RULE_FORMAT_INVALID`（格式码只允许 `^\d{1,2}$` 且 1-12 位数字补零；literal 片段禁带格式）、`STANDARD_RULE_CYCLE`（含间接循环）。
- `evaluate_fields(compiled, values, context=None) -> EvaluationResult`：`values` 优先于 `context`；属性级 `required=True` 自动检查（显式 required 规则去重）；诊断码：`STANDARD_RULE_REQUIRED_MISSING`、`STANDARD_RULE_ENUM_VIOLATION`、`STANDARD_RULE_SOURCE_MISSING`（缺失可选值，该条规则确定性失败但其余规则继续）、`STANDARD_MAPPING_SOURCE_UNCOVERED`、`STANDARD_RULE_FORMAT_INVALID`（非整数补零值）。
- 全程无 `eval`/动态导入。

### 基础设施层 `src/dst_manager/infrastructure/standards/`
- `package.py`：`StandardPackageReader().read(path) -> LoadedStandardPackage(standard, entries, source_path)`。拒绝：`..`/绝对路径/重复规范化路径→`STANDARD_PACKAGE_PATH_INVALID`；可执行扩展名（`.py/.pyc/.dll/.exe/.scr/.lsp/.fas/.vlx/.bat/.cmd/.ps1/.com/.sh/.vbs/.js/.msi`）→`STANDARD_PACKAGE_EXTENSION_FORBIDDEN`；单条目 >64MiB / 包 >256MiB→`STANDARD_PACKAGE_TOO_LARGE`；缺 manifest→`STANDARD_PACKAGE_MANIFEST_MISSING`；Schema 错误包装为 `STANDARD_PACKAGE_MANIFEST_INVALID: <原码>`（`match=` 可命中原码）。
- `store.py`：`StandardStore(official_root=..., user_root=...)`，目录布局 `official/<id>/<ver>/`、`user/published/<id>/<ver>/`、`user/drafts/<draft_id>/`。方法：`list() -> list[StandardSummary]`（source=`official|user`，status=`published|draft`）、`get(id, ver) -> DrawingStandard|None`、`create_draft(document, draft_id=None)`、`save_draft`、`get_draft`、`delete_draft`、`publish(draft_id) -> PublishedStandard`、`import_package(path)`、`export_package(id, ver, dest_dir) -> Path`。重复身份/导入碰撞/官方冲突→`STANDARD_VERSION_EXISTS`；缺草稿→`STANDARD_DRAFT_NOT_FOUND`；发布/导入均为同盘原子 rename，已发布不可原地修改。属性：`official_root`/`published_root`/`drafts_root`。

### 应用层 `src/dst_manager/application/standards.py`
- `StandardResolution`（frozen dataclass）：`status`(`unbound`/`resolved`/`missing`)、`standard_id`、`version`、`standard`、`source`(`""`/`project-snapshot`/`user-library`/`official-library`)、`diagnostics`。
- `parse_standard_identity("id@ver") -> (id, ver)`，非法→`ApplicationError("STANDARD_IDENTITY_INVALID", 422)`。
- `StandardOperations` mixin（已组合进 `DstManagerService`，`self.standard_store` 在 `service.py __init__` 注入，根为 `settings.data_dir/"standards"/{official,user}`）：
  - `list_standards()`、`resolve_workspace_standard(workspace_id)`（**会恢复快照**：库→复制到 `workspace.root/.dst-manager/standards/<id>/<ver>/`）、`peek_workspace_standard(workspace)`（只读，open_workspace 挂载用）、`bind_workspace_standard(workspace_id, identity, base_revision_id)`（preview→execute 事务，写保留属性）。
- **保留属性**：`DSTManager.Standard`（绑定身份）、`DSTManager.StandardOptions`。仅 `bind_standard` DOM 命令可写；普通 `update_sheet_set`/`delete_custom_property` 在应用层（409）与 DOM 层双重拒绝 `STANDARD_PROPERTY_RESERVED`。
- `Workspace.standard` 字段（`domain/models.py`，字符串注解 `StandardResolution | None`，TYPE_CHECKING 导入），`open_workspace` 自动挂载只读解析；`missing` 时给 `document.diagnostics` 追加 `STANDARD_MISSING`（warning），不阻止打开、不建快照。

## 三、环境与测试惯例（避免踩坑）

1. **rtk 会吞掉 pytest 的汇总行**：`uv run pytest ... | tail` 常显示 "No tests collected"。断言结果用 `rtk proxy uv run pytest ... 2>&1 | tail -5`（看到 `..../[100%]` 点数）或加 `-p no:warnings`。
2. **ApplicationError 断言惯例**：`str(exc)` 只有 message 不含 code，用 `pytest.raises(...) as exc_info` + `assert exc_info.value.code == "..."`；`StandardSchemaError`/`StandardRuleError`/`StandardPackageError`/`StandardStoreError` 消息含码前缀，可用 `match=`。
3. **DOM 错误**：`AcsmValidationError("CODE: 详情")` 模式。
4. 新增源文件 ≤500 行；Ruff 默认 88 列；`Mapping` 从 `collections.abc` 导入（UP035）；`store.py` 因类方法名 `list` 遮蔽内置类型，文件头有 `from __future__ import annotations`，新方法注解勿依赖运行时求值。
5. service 测试构造：`DstManagerService(Settings(data_dir=tmp_path / "data"))`；DST 样例用根 `tests/conftest.py` 的 `tiny_workspace` fixture（返回 `(dst, sheet_id)`）。
6. `execute_changes` 必须先 `preview_changes` 拿 `preview_digest` 再传参执行（`bind_workspace_standard` 是范例）。

## 四、全局约束核对（全部遵守中）

- 标准纯数据、无可执行内容；身份仅 `standard_id+version`；已发布不可原地修改；首版规则无日期格式/通用公式；子集属性仅预留 Schema（`subset` scope 可解析但不进首版表单）；`application/service.py` 未膨胀（标准逻辑全在 `application/standards.py`）。

## 五、Task 5 设计准备（已探索，未写码）

计划要求：`inspect_standard_asset(draft_id, asset_id, cad_version) -> AssetInspection`、`create_draft_from_dst(path)`；Modify `application/cad_job.py`（探索后判断可最小化或不动，若不动需在 Task 11 文档说明）。

已确认事实：
- 布局只读枚举协议在 `service.py get_layout_names()`（`ScriptRenderer`+`CoreConsoleExecutor`+`parse_layout_names`，写入临时副本不碰原 DWG）。`fake_inspector` 测试通过替换 reader 注入即可，`cad_job.py` 无直接可复用函数。
- `document.py _sheet_property_definitions()`（line ~563）只提取 scope=2（图纸）属性定义；DST 导入若需图纸集（scope=1）属性定义，可在 `dst_import.py` 内用 xpath 直接提取（`AcSmCustomPropertyValue` 节点 + `_custom_property_scope`），**避免改 `document.py`**（它不在 Task 5 Files 列表）。
- 计划测试要求 `imported_draft.subsets == ()` 且 `imported_draft.external_paths == ()` → 需 `ImportedStandardDraft` dataclass 带这两个恒空字段（证明不复制子集/图纸/引用）。
- 关键行为：`STANDARD_LAYOUT_NAME_MISMATCH` **严格比较**（声明图幅 roles vs 实际非 Model 布局；`"A2 "` ≠ `"A2"`）；能力缺失→诊断 `STANDARD_CAD_CAPABILITY_MISSING`（CAD 读取抛 `ApplicationError` 时转换，不抛出）；非法 DST→稳定诊断且**不留下半成品草稿**（create_draft 失败清理草稿目录——Task 3 的 `create_draft` 已自带失败清理）。

## 六、剩余任务速查

- **Task 6** `/api/standards`（列表/草稿/检查/发布/导入/导出/资产检查）+ 扩展依赖字段 `extension_id/capability_id/min_version` + `export_openapi.py` 再生成 + `npm run check:api`。注意已发布 PUT→409 `STANDARD_VERSION_IMMUTABLE`；缺受信能力→`STANDARD_DEPENDENCY_MISSING`。
- **Task 7** 前端契约/状态机/欢迎页（`useStartNavigation`、`createStandardStore`、代次保护防乱序响应）。
- **Task 8** 主从分栏标准库（`filterStandardList`、`detailActions` 只读边界）。
- **Task 9** 分区编辑器（`buildMappingRows`、`validateMapping`、`renderCompositionPreview`；映射表一条规则装十余行）。
- **Task 10** 资产检查面板 + `buildPublishGate` 发布检查页与问题跳转。
- **Task 11** ST-UI-01~12 追踪矩阵、视觉证据、全量门禁（`npm run check:api/check:i18n/check:ui/test:unit/build/test:e2e` + `ruff/pytest/alembic/uv lock`）、G8/G9 对照。届时统一勾选计划复选框、把计划 status 改 `completed`。

## 七、恢复执行

从 Task 5 Step 1（写 `tests/unit/test_standard_assets.py` 与 `tests/integration/test_standard_dst_import.py` 失败测试）继续，严格 TDD；每 Task 结束按各自 Step 运行验证、更新 changelog、按仓库惯例提交（commit 末尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`）。
