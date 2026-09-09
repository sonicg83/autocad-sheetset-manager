# PLAN-DM-020 内置扩展平台与图纸目录实施计划审查备忘

## 日期

2026-09-09

## 背景

本备忘记录对 [PLAN-DM-020：内置扩展平台与图纸目录 XLSX 实施计划](../../plans/dst-manager/PLAN-DM-020-sheet-catalog-builtin-extension.md) 的只读审查。审查在计划 `proposed` 状态、开工前进行，目标是把规范覆盖缺口和内部矛盾在执行前修掉，而不是修改规范、源码或测试。

审查对照 [ARCH-DM-006](../../../docs/dst-manager/architecture/ARCH-DM-006-builtin-extension-platform.md) 与 [SPEC-DM-012](../../../docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md) 逐条核对追踪矩阵和 12 个任务，并对计划引用的既有代码事实做了逐项核实（行数、迁移版本、测试夹具、函数落点等）。

## 审查结论

**计划质量很高，可以按小修订进入执行：3 项阻塞级缺口（限制数值、错误码词汇表、清单 schema）与 4 项重要偏差（日志语义、`SAVE_DIALOG` 现状、Step 9 措辞、changelog 时机）应在开工前修订；其余为测试锚点补强。** 规范覆盖面本身没有结构性遗漏——24 行追踪矩阵与两份规范的需求域基本一一对应，9 个 API 端点与 ARCH §7 逐字一致，保存协议、XLSX 校验、Artifact 三态、G8/G9 证据链均对齐。

## 阻塞级（执行前必须修）

### 1. SPEC §5.3 限制值 80/100/1024 未钉进任何任务

规范 `SPEC-DM-012:170-172` 规定模板名 1～80 字符、输出列名 1～100 字符、单个表达式 1024 字符。计划 Task 5 Step 3 只写"名称/列名/表达式长度"，三个数值均未出现；追踪矩阵 SC-05 声称"已覆盖"，实现者会自选数值。属于"全局约束必须逐字复制规范值"的违反。

### 2. SPEC §11 错误码词汇表无落地锚点

规范 `SPEC-DM-012:328-340` 定义 `SHEET_CATALOG_EXPRESSION_INVALID`、`FIELD_UNDEFINED`、`VALUE_MISSING`、`COLUMN_DUPLICATE`、`TEMPLATE_LIMIT`、`TEMPLATE_CONFLICT`、`XLSX_INVALID` 等稳定错误码。计划只定义错误**结构**（Task 3 的 `ExtensionErrorResponse`），从未枚举 code 字符串；`TEMPLATE_CONFLICT` 的"保留本地编辑 → 刷新修订 → 另存/重试"用户流程在 Task 11 只有"保存失败输入保留"。矩阵 SC-11 属于"声称已覆盖、条款未落 Task"的典型行。

### 3. `ExtensionManifest` 缺少支持 Task 8 的机制字段

Task 8 Step 2 要求 ShellBridge"只允许 registry 声明为 **XLSX 输出**的动作"，但 Task 1 的 `ExtensionManifest` 只有 `actions: tuple[str, ...]`，无法表达动作输出类型。同时 ARCH §4.2（`ARCH-DM-006:125-126`）要求的 `name_key`/`description_key` 清单字段缺失。清单 schema 需要一次修订。

## 重要（会造成执行偏差或与规范冲突）

### 4. 日志语义与 ARCH §12 方向相反

ARCH §12（`ARCH-DM-006:329`）要求日志**关联** invocation ID、扩展 ID、版本、工作区和来源修订（仅禁敏感值与完整路径）；计划 Task 8 Step 5 写"日志**只含** invocation/artifact ID"，收得过窄，照做会丢关联性。

### 5. `SAVE_DIALOG` 被当作既有约定，实际不存在

现有 `shell.py` 只有 `OPEN_DIALOG` 和 `FOLDER_DIALOG`。计划全局约束与 Task 8 把"固定 XLSX `SAVE_DIALOG`"写成既有协议，应明确"新增保存对话框类型"这一工作项。

### 6. Task 12 Step 9 措辞自相矛盾

"只暂存本计划文件"——但该任务同时创建 design QA 备忘、G9 清单并修改 SPEC/README/changelog，按此措辞均不会入库。应为"只暂存本任务涉及的文件"。

### 7. changelog 时机违反 AGENTS.md

AGENTS.md 要求"每次修改都要更新根目录 changelog.md"，计划把 changelog 挪到 Task 12 一次性更新，Task 1～11 的提交均不含。需裁决：每个批次提交附带 changelog，或在计划中记录"收口时统一补记"的偏差。

### 8. 批次四前置几乎必然触发暂停且无排期

`web/src/i18n/` 整个目录不存在、vue-i18n 未安装；ARCH-DM-005 只有架构文档与 [评审备忘](2026-09-08-arch-dm-005-review.md)，**没有实施计划**。计划的暂停点设计正确，但建议先为 ARCH-DM-005 立计划，否则批次三结束即无限期阻塞。

## 建议补强（测试锚点与一致性）

9. **仓储文件命名与 G5 冻结裁决不一致**：SPEC §14 与 G5 备忘裁决 `infrastructure/persistence/extensions.py`，计划 Task 2 用 `extension_store.py`，建议改回或记录偏差。
10. **接口草图不完整**：Task 9 `execute_export(request)` 缺 `context` 参数，与 Task 6 `preview(self, context, request)` 不对称；`VersionedJson`、`TemplateCollection`、`SaveGrantReceipt`、`ArtifactRecord` 等类型未在任何任务的 Produces 中定义，应至少给出关键字段。
11. **建议文件名模式未钉死**：SPEC §9（`SPEC-DM-012:312`）固定 `<图纸集名称>-图纸目录.xlsx`，Task 8 只写"清理非法字符和长度"。
12. **杂项测试锚点**：模板名 casefold 唯一只有 E2E 无单测；删除模板后"回退内置默认模板"与"删除不删历史 Artifact"（SPEC §3.2）无断言；ARCH §4.3 启动顺序（先迁移/恢复再发现扩展）未作为可测约束；`WAITING_DEPENDENCY` 状态未裁决为不可达；多授权并发导出（ARCH §11）无用例；偏好保存失败不阻断预览（ARCH §8.2）无测试；Task 12 交付命令缺 `npm run check:api`（SPEC §15.3）。

## 事实核对（已验证属实）

- `database.py` 确为 782 行（`api.py` 实际 512 行、`App.vue` 683 行、`service.py` 307 行）✓
- 迁移最新为 `0005_dm019_job_lease_seconds`，无 0006+；`migrations/env.py` 存在 ✓
- `test_database.py:16` 有 `test_published_migrations_are_immutable` 哈希夹具 ✓
- `property_definitions_from_document()` 在 `domain/editing.py:134`；`upsert_workspace`（`database.py:256`）、`open_workspace`（`service.py:92`）均存在 ✓
- Toast/ConfirmModal/UnsavedInputDialog 组件、`openapi.json`/`schema.d.ts`、`generate:api`/`test:e2e` 脚本齐备 ✓
- 打包三件套（`packaging/dst-manager.spec`、`test_packaging_spec.py`、`build_release.ps1`）存在 ✓
- 应用临时目录与 `%LOCALAPPDATA%/dst-manager` 既有约定属实（`config.py:13`、`service.py:238`、`shell.py:265`）✓
- ARCH-DM-005 前置未落地属实（无 `web/src/i18n/`、无 vue-i18n 依赖）✓

## 一致确认（核对过且对齐的需求域）

扩展平台骨架（固定索引/生命周期/故障隔离）、只读快照语义（两作用域/casefold/basename/无路径泄漏）、受限表达式（禁 eval/Jinja、0-based 位置、缺定义阻断/缺值警告）、预览与 digest 五要素、模板契约（内置不可变/UUID/乐观并发）、保存协议（一次性授权/TTL/同卷原子替换/失败不登记）、XLSX 回读校验、Artifact 三态与成功响应隐藏技术字段、API 端点逐字一致、前端页面贡献模型与可访问性、G8/G9 证据链。

## 建议处置

阻塞级 1～3 与重要 4～7 值得在开工前修订计划（改动小、不需重开 G2～G6 门禁）；建议补强项可作为执行时备忘逐批落实。修订后计划即可转 `active` 并进入批次一。

## 修订处理记录

2026-09-09 已完成开工前计划修订：

- 阻塞项 1～3 已写入明确数值、稳定错误码及恢复流程，并把清单动作改为包含 `action_id`、`output_kind`、`media_type` 的结构；`name_key`、`description_key` 同时补齐。
- 重要项 4～7 已修正日志关联语义、明确 `SAVE_DIALOG` 为新增接线、修正 Task 12 暂存范围，并要求 Task 1～12 各自更新 `changelog.md`。
- 多语言前置不并入本计划临时实现；已建立[ARCH-DM-005 多语言实施门禁待办](../../todos/dst-manager/2026-09-09-arch-dm-005-implementation-gates.md)，要求在批次二检查点前启动独立 G0～G6 工作流，未完成时阻断 Task 10。
- 建议项 9～12 已纳入：持久化文件统一为 `persistence/extensions.py`，补齐跨任务接口字段，固定建议文件名模式，并增加启动顺序、`WAITING_DEPENDENCY`、多授权并发、偏好失败降级、模板删除/冲突和 `npm run check:api` 测试锚点。
- 本次只修订计划与架构契约，未开始生产实现；PLAN-DM-020 继续保持 `proposed`，待用户选择执行方式后再转 `active`。
