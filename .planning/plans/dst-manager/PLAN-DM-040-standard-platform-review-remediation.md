---
id: PLAN-DM-040
title: 图纸标准平台审查问题修复计划
status: active
owners:
  - dst-manager
created: 2026-09-24
updated: 2026-09-24
related:
  - ARCH-DM-001
  - ARCH-DM-007
  - SPEC-DM-016
  - SPEC-DM-017
  - PLAN-DM-035
  - PLAN-DM-036
  - PLAN-DM-038
  - PLAN-DM-039
  - PLAN-DM-041
---

# 图纸标准平台审查问题修复计划

> **执行要求：** 实施前阅读 [SPEC-DM-016](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md)、[SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md)、[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) 和 [ARCH-DM-001](../../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)。每个任务按 Step 执行：先写失败用例并运行记录 RED（保留实际失败输出），再做最小实现、验证 GREEN、更新 `changelog.md`、提交；复选框只在实际实施和验证后勾选。命令在仓库根目录执行，Web 命令统一用 `npm --prefix web` 形式；如需用 `rtk` 过滤输出，保持命令语义与结果不变。

**目标：** 关闭 PLAN-DM-035/038/039 代码审查与真实草稿编辑测试发现的 F01–F15 与 F17 共 16 项问题，使用户能把本机 DWG 安全纳入草稿、检查、发布并导出可用的 `.dststandard` 包，同时恢复标准身份、页面状态和 UI 契约的正确性。

**架构：** 标准文档继续只保存包内相对路径；本机绝对路径只作为一次性导入来源。桌面壳选择 DWG 后，由后端把文件复制到草稿受控目录并返回可判定的受控副本名。草稿段与身份段（`standard_id`/`version`）的路径边界统一在仓储层校验；文件存在性、路径合法性与包清单一致性在发布、导入和导出前做最终门禁。编辑器在打开时固定 `draft_id`，保存、检查、发布只用该身份；前端检查结果只对应已保存的文档修订，不承担最终安全门禁。

**技术栈：** Windows 11、Python ≥3.12、UV、FastAPI、Vue 3、TypeScript、Vite、Vitest、Playwright、pywebview/WebView2、AutoCAD 2016/2020。

**规范依据：** SPEC-DM-016 §4、§5、§8～§12（Task 3 显式修订 §8.1 并在 `updated` 记录变更）；SPEC-DM-017 §3～§9；ARCH-DM-007 §4～§9；[官方标准包制作指南](../../../docs/dst-manager/guides/GUIDE-DM-007-official-standard-package-release.md) §8.4、§9.3、§10。

## 范围与分级

| 编号 | 级别 | 已发现的问题 | 承接任务 | 基线证据 |
| --- | --- | --- | --- | --- |
| F01 | **阻断** | 草稿编辑器只能声明包内路径，不能把本机 DWG/DWT 纳入草稿，带模板资产的标准包无法通过界面闭环创建 | Task 3 | 源码核实 |
| F02 | 高 | 缺失的模板资产仍可发布或由包导入 | Task 2 | 实测复现 |
| F03 | 高 | 新建草稿后检查/发布可能指向旧草稿 | Task 5 | 源码核实 |
| F04 | 高 | 客户端 `draft_id` 可造成草稿目录越界写入 | Task 1 | 源码核实（同类 F17 已实测） |
| F05 | 高 | 同来源、同版本的不同标准共用列表键 | Task 5 | 源码核实 |
| F06 | 中 | 资产检查针对已保存旧文档，发布却保存并使用新文档 | Task 4 | 源码核实 |
| F07 | 中 | 未取得资产检查结果时面板仍显示“本次检查未发现问题” | Task 4 | 用户 2026-09-24 真实桌面截图（草稿编辑器“模板资产”分区）+ 源码核实 |
| F08 | 中 | 派生草稿可复用上一标准的陈旧详情 | Task 6 | 源码核实 |
| F09 | 中 | 版本历史跨官方/用户来源跳转失败 | Task 6 | 源码核实 |
| F10 | 中 | 切换映射源后旧目标值可进入新映射 | Task 7 | 源码核实 |
| F11 | 中 | 编辑器允许修改标准 ID/版本，但保存无法按新身份完成 | Task 7 | 源码核实 |
| F12 | 中 | 窄屏标准库未实现真正的列表与详情两级页面 | Task 8 | 源码核实 + 现有 900×768 E2E 断言 |
| F13 | 中 | 新建、CSV 弹窗未复用焦点工具（标准包导入弹窗由 PLAN-DM-041 承接） | Task 9 | 源码核实 |
| F14 | 中 | 列表/详情失败缺重试、筛选无结果缺清除入口 | Task 8 | 源码核实 |
| F15 | 低 | 包内原始 `..` 分量经规范化后可能被接受 | Task 2 | 源码核实 |
| F17 | 高 | 身份路由 `standard_id`/`version` 未做路径段校验，可经 `%2E%2E` 越界读取标准库根外 `document.json`，并可用 `/export` 把该目录打成 zip | Task 1 | 实测复现 |

F16（现成 `.dststandard` 包的受控选择，PLAN-DM-039 F7）已拆分为独立的 [PLAN-DM-041](PLAN-DM-041-standard-package-import-picker.md)，包含其导入弹窗的焦点契约；本计划只处理 DWG/DWT 进入草稿的文件选择、资产闭环与身份/草稿路径边界。

## 发现溯源与基线证据

- 逐项的核实方式、源码位置与一次性实测输出见 [PLAN-DM-040 发现核实与基线证据](../../memos/dst-manager/2026-09-24-plan-dm-040-findings-verification.md)。
- F02、F15、F17 已在临时目录实测复现；F04 与 F17 属同一缺陷类（客户端路径段未校验），由 Task 1 统一修复；F07 的截图证据来自用户 2026-09-24 的真实桌面状态。
- 本计划把这些一次性探针固化为 Task 1/2/3 的 RED 用例；不把先前绿色测试视为这些问题已关闭。

## 全局约束

- 不改变标准 Schema 版本 `1`，不把本机绝对路径写进 `document.json`、发布目录或包内 `manifest.json`。
- 后端仍是资产可用性、发布和包导入的最终权威；前端预检不能替代最终校验。
- 草稿允许保存语义未完成内容；发布、导入与标准驱动创建不得消费缺失或越界的模板文件。
- 桌面 Web 服务只监听 `127.0.0.1`；文件来源是用户显式选择或无壳本地开发态显式输入，不拼接进 Shell、SCR 或 CAD 命令。
- 文件操作只落在标准草稿受控目录的临时路径和最终路径；失败不得覆盖原 DWG、破坏既有草稿或留下可发布的半成品。
- 不修改 `sample/` 原件，不提交私有样本、`web/dist/`、`web/node_modules/`、插件产物或真实客户路径。
- 每个代码任务的提交步骤同步更新 `changelog.md`；API 变化同步更新契约、生成的 OpenAPI/TS 类型、集成测试及中英文文案。
- 实施前重新检查工作区，保留当前已有的 `changelog.md` 和 Web 测试配置等无关改动；仅暂存本任务文件。

## 交付批次和依赖

| 批次 | 任务 | 可独立验收的结果 | 前置条件 |
| --- | --- | --- | --- |
| A：边界与发布安全 | 1 → 2 | 草稿与身份路由不越界；缺失、非法或清单不一致的资产不能发布/导入/导出 | 无 |
| B：创建闭环 | 3 → 4 | 本机模板复制入草稿；编辑、检查、发布、导出使用同一份内容 | A |
| C：编辑身份 | 5 → 6 → 7 | 选择、派生、版本跳转、映射与保存身份正确 | A |
| D：UI 与验收 | 8 → 9 → 10 | 窄屏、重试、弹窗焦点与桌面复验完成 | B、C |

任务按 1→10 串行执行。B/C 之间没有接口依赖，但 Task 3/4/5/7 共同修改 `web/src/components/standards/StandardEditor.vue`、Task 3/6 共同修改 `web/src/features/standards/store.ts`，并行分支会产生合并冲突，并可能让 Task 5“编辑器固定 `draft_id`”的前提在合并后失效；如确需并行，先冻结这两个文件的接口，合并后复跑批次 A、B 的全部门禁。

## Review Focus

1. 选择含中文、空格或 OneDrive 路径的 DWG/DWT 后，来源文件的哈希和 mtime 不变，草稿只保存 `assets/managed-*` 相对路径；Task 3 覆盖。
2. 导入来源在复制途中消失、超过 64 MiB、扩展名不符或复制中断时，不创建半成品资产且原草稿仍可打开；Task 3 覆盖。
3. 发布、导入、导出前文件被删除、替换为符号链接、使用绝对路径/`..` 或清单与包内条目不一致时，仓储与 HTTP 入口都拒绝，原草稿和发布目标保持不变；Task 2 覆盖。
4. `%2E%2E`、`..`、盘符、设备名等路径段在草稿与身份入口都不可越界；新建、切换、派生、保存只使用当前身份；Task 1、5、6、7 覆盖。
5. 900×768 和 200% 缩放下，详情返回、错误重试、弹窗底部动作与键盘焦点都可达；Task 8、9、10 覆盖。

---

### Task 1：封闭草稿与身份路径段（F04、F17）

**Files:**
- Modify: `src/dst_manager/infrastructure/standards/store.py`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Test: `tests/unit/test_standard_store.py`
- Test: `tests/integration/test_standard_api.py`

**Interfaces:**
- Consumes: `StandardStore.create_draft/get_draft/save_draft/delete_draft/publish/list/get/get_document/export_package` 的既有 `draft_id`、`standard_id`、`version` 字符串。
- Produces: 仓储内单一 `_safe_segment(value: str, kind: str) -> str`、`_draft_dir(draft_id: str) -> Path`、`_published_dir(standard_id: str, version: str) -> Path`。草稿段非法使用稳定 `STANDARD_DRAFT_ID_INVALID`（HTTP 422）；身份段非法复用 `STANDARD_ID_INVALID`/`STANDARD_VERSION_INVALID`（HTTP 422）。合法 ID 的响应格式与公共 API 不变；`list()` 跳过目录名非法的历史草稿而不是整体失败。

- [x] **Step 1：写草稿段 RED**
  在 `tests/unit/test_standard_store.py` 用 `tmp_path` 夹具覆盖：`create_draft/get_draft/save_draft/delete_draft/publish` 对 `"../outside"`、`"..\\outside"`、`"C:\\outside"`、`"."`、`".."`、`"a/b"`、`"a\\b"`、空串、`CON`/`LPT1`/`CON.dwg`、尾随点或空格一律拒绝（`STANDARD_DRAFT_ID_INVALID`），并断言草稿根外的文件哈希与目录列表不变。合法 ID（`draft-1`、`legacy`、`draft-gas`）仍可用；草稿根存在非法目录名时 `list()` 仍返回其余草稿。

- [x] **Step 2：写身份段 RED（F17）**
  在 `tests/integration/test_standard_api.py` 增加：`GET /api/standards/%2E%2E/%2E%2E`、`GET /api/standards/%2E%2E/%2E%2E/export` 以及直接调用 `store.get/get_document/export_package` 时，含 `..`、盘符、空段的身份一律 404 或 422；在标准库根外放置合法 `document.json` 与 `assets/secret.dwg`，断言响应不包含其内容、导出 zip 不含该目录条目。合法身份的详情与导出响应不变。

- [x] **Step 3：运行 RED 并记录**
  `uv run pytest tests/unit/test_standard_store.py tests/integration/test_standard_api.py -q -p no:xdist`
  期望：新用例失败。记录 `%2E%2E` 当前返回 200、`/export` 当前返回根外 zip 的实际输出，作为缺陷与后续对照的 RED 证据。

- [x] **Step 4：实现最小边界**
  在 `store.py` 实现 `_safe_segment`/`_draft_dir`/`_published_dir`：单段校验、`resolve()` 后父目录边界、Windows 保留设备名与尾随点/空格拒绝、长度上限；创建、读取、保存、删除、发布、导出及 Task 3 的资产复制入口全部复用。`_iter_drafts` 对目录名非法的历史草稿跳过。身份段复用 `STANDARD_ID_PATTERN`/`STANDARD_VERSION_PATTERN`（从 `dst_manager.domain.standards` 导入），不改写文档内身份校验的既有码。

- [x] **Step 5：运行 GREEN 与回归**
  同 Step 3 命令，加 `uv run pytest tests/unit/test_standard_assets.py tests/unit/test_standard_package.py -q` 与 `uv run ruff check .`；记录全绿。

- [x] **Step 6：登记文案、changelog 并提交**
  在 `standards.ts` 诊断域登记 `STANDARD_DRAFT_ID_INVALID`（中英对称），`npm --prefix web run check:i18n` 通过；更新 `changelog.md`；只暂存本任务文件并提交（简体中文 commit message）。

### Task 2：把资产存在性变成发布、导入与导出硬门禁（F02、F15）

**Files:**
- Create: `src/dst_manager/infrastructure/standards/asset_paths.py`（包内路径解析、受控根目录检查、资产文件集合校验）
- Modify: `src/dst_manager/infrastructure/standards/store.py`
- Modify: `src/dst_manager/infrastructure/standards/package.py`
- Modify: `src/dst_manager/application/standard_assets.py`
- Test: `tests/unit/test_standard_store.py`
- Test: `tests/unit/test_standard_package.py`
- Test: `tests/unit/test_standard_assets.py`
- Test: `tests/integration/test_standard_api.py`

**Interfaces:**
- Consumes: `DrawingStandard.assets[*].files[*].path`、草稿目录或经验证的 ZIP 条目集合。
- Produces: `validate_asset_files(standard, root: Path) -> None` 与 `validate_package_asset_files(standard, entries: Collection[str]) -> None`；非法相对路径与缺失文件复用既有 `STANDARD_ASSET_PATH_INVALID`、`STANDARD_ASSET_FILE_MISSING`（不新增码；前端诊断文案已存在）。

- [x] **Step 1：写发布侧 RED**
  草稿声明 `assets/missing.dwg` 但文件不存在、声明绝对路径/盘符/UNC/`..`、或声明指向受控根外的符号链接时，`publish()` 拒绝且草稿目录、发布根不变；已有文件、合法子目录与中文文件名通过。记录当前 `publish()` 对缺失与绝对路径资产均返回成功的失败输出。

- [x] **Step 2：写包侧 RED（导入与导出）**
  ZIP 原始名 `assets/../A2.dwg`、`assets\\..\\A2.dwg` 在规范化前即拒绝；清单声明文件缺失、清单声明与包内真实条目双向不一致（缺失与多余）都拒绝；`export_package()` 只导出被文档声明且校验通过的资产，不把未引用的草稿临时文件混进包。失败时不移动草稿、不创建目标版本、导入暂存目录被清理。

- [x] **Step 3：运行 RED 并记录**
  `uv run pytest tests/unit/test_standard_store.py tests/unit/test_standard_package.py tests/unit/test_standard_assets.py tests/integration/test_standard_api.py -q -p no:xdist`；记录缺失资产导入 200、缺失/绝对路径发布 200 的失败输出。

- [x] **Step 4：实现最小门禁**
  创建 `asset_paths.py` 并在仓储最终 `os.replace` 之前对草稿目录运行 `validate_asset_files`，对导入暂存目录/条目集合运行 `validate_package_asset_files`；`package.py` 的条目规范化改为先拒绝 `..` 分量再做归一化；`export_package()` 改为按文档声明白名单导出。

- [x] **Step 5：运行 GREEN 与夹具回归**
  同 Step 3 命令加 `uv run ruff check .`；确认既有合法官方包夹具仍可读，记录全绿。

- [x] **Step 6：changelog 并提交**
  更新 `changelog.md`；只暂存本任务文件并提交。

### Task 3：将本机模板文件受控复制进草稿（F01，阻断）

**Files:**
- Modify: `docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md`（§8.1 来源路径、包内路径、复制失败与无壳回退契约；同步 `updated`）
- Modify: `src/dst_manager/infrastructure/standards/store.py`
- Modify: `src/dst_manager/application/standard_assets.py`
- Modify: `src/dst_manager/interfaces/standard_contracts.py`
- Modify: `src/dst_manager/interfaces/standard_api.py`
- Modify: `web/src/api/standards.ts`
- Modify: `web/src/features/standards/types.ts`
- Modify: `web/src/features/standards/store.ts`
- Modify: `web/src/components/standards/TemplateAssetsEditor.vue`
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Test: `tests/unit/test_standard_assets.py`、`tests/integration/test_standard_api.py`、`web/tests/e2e/standards-assets-publish.spec.ts`

**Interfaces:**
- Consumes: 既有桌面桥 `select_file("template", description)`（固定 `*.dwg;*.dwt`）、Task 1 的安全草稿根目录与 Task 2 的资产校验。
- Produces: `POST /api/standards/drafts/{draft_id}/asset-files`，请求 `{source_path: string}`，成功返回 `{path: string}`；`path` 只为服务器生成的受控副本名 `assets/managed-<uuid4hex>.dwg|.dwt`，前端将其写入当前草稿文件行，不保存 `source_path`。清理规则：保存或发布成功后，只删除草稿 `assets/` 下**未被当前文档引用且文件名匹配 `managed-` 前缀**的副本；其他文件一律不触碰。

- [x] **Step 1：写正常路径 RED**
  以中文、空格、OneDrive 绝对路径来源复制 DWG/DWT；响应只含受控相对路径；源文件哈希/mtime 不变，副本内容相同，保存草稿后检查可读取副本；取消文件选择不发 API 请求；新建与替换文件行均覆盖。

- [x] **Step 2：写故障与原子性 RED**
  来源不存在、不是文件、扩展名不符、超过单文件 64 MiB、草稿不存在或 `draft_id` 非法、复制中断、目标碰撞均拒绝且无半文件；已有文件与 `document.json` 不变；实现须先写草稿内随机临时文件、校验完成后原子改名，不跟随草稿内路径逃逸或覆盖已有文件。

- [x] **Step 3：写 UI RED**
  “受控路径”显示为只读包内路径，新增“选择本机模板”与“替换文件”；有壳时只调用固定 `template` 文件种类。无壳本地开发态提供单独标明的“来源绝对路径”输入并调用同一 API，不把浏览器 `<input type=file>` 的 `fakepath` 交给路径 API。复制成功才修改编辑缓冲；失败保留旧声明与 dirty 状态并就地显示错误。

- [x] **Step 4：实现后端复制与契约**
  实现复制端点、`_draft_dir` 校正、大小与扩展名校验、临时文件 + 原子改名；登记 `standard_contracts.py` 的请求/响应模型，更新 OpenAPI 与 TS 类型（`npm --prefix web run generate:api` 后 `check:api` 通过）。

- [x] **Step 5：实现前端接线与文案**
  更新 `web/src/api/standards.ts`、`types.ts`、`store.ts` 与资产编辑器/编辑器壳层；中英文文案同步。

- [x] **Step 6：写清理规则 RED/GREEN**
  保存成功与发布成功后清理未被引用且匹配 `managed-` 的副本；旧草稿中手工放置的 `assets/A2.dwg` 不被清理；文档未引用但本次会话刚复制的副本在用户放弃编辑后保留到下次保存/发布再清理（显式断言该行为）。

- [x] **Step 7：回归、文档与提交**
  运行后端单元/集成测试、`npm --prefix web run check:api`、`check:i18n`、`npm --prefix web run test:e2e -- tests/e2e/standards-assets-publish.spec.ts`、`npm --prefix web run build`；用临时 DWG 夹具完成“选择→复制→保存→检查→发布→导出→重新导入”闭环；按规范依据修订 SPEC-DM-016 §8.1 与 `updated`；更新 `changelog.md`；提交。

### Task 4：检查结果绑定已保存草稿，并修正未检查空态（F06、F07）

**Files:**
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/components/standards/TemplateAssetsEditor.vue`
- Modify: `web/src/components/standards/AssetInspectionPanel.vue`
- Modify: `web/src/features/standards/publishModel.ts`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Test: `web/src/features/standards/publishModel.test.ts`
- Test: `web/tests/e2e/standards-assets-publish.spec.ts`

**Interfaces:**
- Consumes: Task 3 的受控资产副本、既有 `saveDraft()` 与 `inspectAsset()`。
- Produces: 每次检查记录 `draft_id` 与已保存文档快照；编辑缓冲发生任何相关变更后标记结果已失效。未收到某资产检查结果时显示“未检查”，而不是“未发现问题”。

- [x] **Step 1：写状态机 RED**
  覆盖新建未保存资产、编辑已检查路径、检查期间继续编辑、保存失败、切换草稿、检查返回顺序颠倒：不把旧结果显示为当前结果；无检查记录时断言“未检查”可见且“未发现问题”不可见。

- [x] **Step 2：运行 RED 并记录**
  `npm --prefix web run test:unit -- src/features/standards/publishModel.test.ts`；记录旧结果被当作当前结果的失败输出。

- [x] **Step 3：实现“保存并检查”与代次保护**
  `runInspections()` 对 dirty 草稿先执行显式“保存并检查”：结构无效或保存失败即停止检查并显示原因；保存成功后基于返回文档与固定 `draft_id` 检查。异步结果用代次与快照身份防止过期响应覆盖新状态；发布检查打开和点击发布前都核对当前快照，快照不一致时重新检查并阻断前端继续动作。

- [x] **Step 4：修正未检查空态并补文案**
  `AssetInspectionPanel` 在无检查记录时显示“未检查”；新增文案写入中英语言包并用 `check:i18n` 验证对称。

- [x] **Step 5：验证与提交**
  运行 `npm --prefix web run test:unit`、`npm --prefix web run test:e2e -- tests/e2e/standards-assets-publish.spec.ts`、`npm --prefix web run build`；更新 `changelog.md`；提交。后端 Task 2 门禁独立重验，不依赖前端检查缓存。

### Task 5：统一标准列表键与编辑草稿身份（F03、F05）

**Files:**
- Modify: `web/src/features/standards/draftModel.ts`
- Modify: `web/src/views/StandardsView.vue`
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/components/standards/StandardLibraryPane.vue`
- Test: `web/src/features/standards/draftModel.test.ts`
- Test: `web/tests/e2e/standards-library.spec.ts`
- Test: `web/tests/e2e/standards-editor.spec.ts`

**Interfaces:**
- Consumes: `StandardSummary.source/standard_id/version/draft_id`、编辑器 `props.draft.draft_id`。
- Produces: `draftKey(summary)` 对草稿使用稳定 `draft_id`，对已发布版本使用 `source/standard_id/version`；编辑器检查、发布与保存始终使用打开时的 `draft_id`，不从列表选择反推。

- [x] **Step 1：写 RED**
  两个官方标准同为 `1.0.0` 时列表键不重复且点击各项获得对应详情；空库新建草稿、以及此前选中过旧草稿后新建，保存、资产检查与发布都只调用新草稿 ID。

- [x] **Step 2：运行 RED 并记录**
  `npm --prefix web run test:unit -- src/features/standards/draftModel.test.ts` 与 `npm --prefix web run test:e2e -- tests/e2e/standards-library.spec.ts`；记录键冲突与旧草稿 ID 被调用的失败输出。

- [x] **Step 3：实现键与身份固定**
  `draftKey` 纳入 `standard_id`；`StandardLibraryPane` 改为复用 `draftKey`，删除内联键表达式；新建成功时更新选中身份，发布成功时按返回的 `standard_id/version` 精确选中新发布版本；编辑器生命周期内固定 `draft_id`，列表刷新或筛选不改变操作目标。

- [x] **Step 4：验证与提交**
  运行相关单测、标准库/编辑器 Playwright 与构建；更新 `changelog.md`；提交。

### Task 6：阻断陈旧详情派生并修正跨来源版本跳转（F08、F09）

**Files:**
- Modify: `web/src/features/standards/store.ts`
- Modify: `web/src/views/StandardsView.vue`
- Modify: `web/src/components/standards/StandardDetailPane.vue`
- Test: `web/src/features/standards/store.test.ts`
- Test: `web/tests/e2e/standards-library.spec.ts`

**Interfaces:**
- Consumes: Task 5 的完整标准键与 `StandardIdentity`（`VersionEntry` 保持 `version/source`，事件补充 `summary.standard_id` 组成完整身份）。
- Produces: 详情结果携带与当前选择可比对的 `standard_id/version`；版本链接发出完整身份；派生只消费身份匹配且已完成加载的详情。

- [x] **Step 1：写 RED**
  选中 A 后快速切 B：B 加载中或加载失败时派生不可用且不会复制 A；B 成功加载后只派生 B。版本历史跨官方/用户来源时点击目标条目选中正确标准。

- [x] **Step 2：运行 RED 并记录**
  `npm --prefix web run test:unit -- src/features/standards/store.test.ts` 与 `npm --prefix web run test:e2e -- tests/e2e/standards-library.spec.ts`。

- [x] **Step 3：实现失效与完整身份**
  切换选择即清除旧详情；在途响应按代次与身份丢弃；`StandardDetailPane` 的版本事件携带 `source/standard_id/version`，视图用 `draftKey` 选中。

- [x] **Step 4：验证与提交**
  运行 store 单测、标准库 Playwright 与构建；更新 `changelog.md`；提交。

### Task 7：隔离映射源、草稿级保存与身份只读（F10、F11）

**Files:**
- Modify: `web/src/components/standards/MappingPropertyDialog.vue`
- Modify: `web/src/components/standards/StandardEditor.vue`
- Modify: `web/src/views/StandardsView.vue`
- Modify: `web/src/features/standards/types.ts`
- Modify: `web/src/features/standards/store.ts`
- Modify: `web/src/api/standards.ts`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Modify: `src/dst_manager/application/standards.py`
- Modify: `src/dst_manager/interfaces/standard_api.py`
- Test: `web/src/features/standards/draftModel.test.ts`
- Test: `web/src/features/standards/store.test.ts`
- Test: `web/tests/e2e/standards-editor.spec.ts`
- Test: `tests/unit/test_standard_service.py`
- Test: `tests/integration/test_standard_api.py`

**Interfaces:**
- Consumes: 映射源 `source_property_id` 与各源内稳定 `enum_item_id`；草稿已存身份（`store.get_draft`）。
- Produces: 映射目标缓冲按 `(source_property_id, enum_item_id)` 隔离；草稿创建后的 `standard_id/version` 在编辑器中只读。新增草稿级保存路由 `PUT /api/standards/drafts/{draft_id}`，请求复用 `StandardDocumentRequest`（`{document}`），响应复用 `StandardDraftResponse`；草稿不存在 404，结构非法 422，请求体身份与草稿已存身份不一致返回 `STANDARD_IDENTITY_MISMATCH`（422），不静默改写。既有 `PUT /api/standards/{standard_id}/{version}` 行为保持不变（兼容保留）；前端改为 `SaveDraftInput {draftId, document}` 并删除只按身份保存的调用路径。

- [x] **Step 1：写映射隔离 RED**
  两个枚举源恰有相同 `enum_item_id` 时切换源不得继承旧目标；切回原源按明确的缓冲策略恢复其未提交输入；确认新源前空目标仍触发既有门禁。

- [x] **Step 2：写保存路由 RED**
  新路由：成功返回保存后文档；草稿不存在 404；请求体身份与草稿已存身份不一致 422 `STANDARD_IDENTITY_MISMATCH`；结构非法 422。既有身份路由回归不变。

- [x] **Step 3：运行后端 RED 并记录**
  `uv run pytest tests/unit/test_standard_service.py tests/integration/test_standard_api.py -q -p no:xdist`；记录新路由不存在（404/405）与身份不一致用例的失败输出。

- [x] **Step 4：实现后端保存语义**
  在应用层加入“文档身份必须等于草稿已存身份”的核对（两个保存入口共用），注册草稿级 `PUT` 路由并放在身份路由之前注册；登记契约与生成类型，`npm --prefix web run check:api` 通过。

- [x] **Step 5：实现前端**
  映射缓冲按 `(source_property_id, enum_item_id)` 隔离；编辑器身份字段只读并保留可访问说明；`StandardsView.saveEditorDocument` 改用固定 `draft_id` 调用新保存 API；中英文文案同步。

- [x] **Step 6：验证与提交**
  运行 Python 单测、前端单测、编辑器 Playwright、构建；更新 `changelog.md`；提交。

### Task 8：补齐窄屏标准库和异步操作入口（F12、F14）

**Files:**
- Modify: `web/src/views/StandardsView.vue`
- Modify: `web/src/components/standards/StandardLibraryPane.vue`
- Modify: `web/src/components/standards/StandardDetailPane.vue`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Test: `web/tests/e2e/standards-library.spec.ts`

**Interfaces:**
- Consumes: Task 5/6 的完整选择身份与现有 `store.refresh/open()`。
- Produces: 宽度 ≤959px 时互斥 `list/detail` 视图；详情页有可见“返回列表”按钮。列表、详情失败各自就地重试，筛选无结果可清除筛选。

- [x] **Step 1：写 RED**
  把现有 900×768 E2E 中“详情打开后列表仍可见”的断言改为：选中后列表隐藏、详情显示、返回按钮可见；返回后筛选与选择保留，无页面级横向滚动。

- [x] **Step 2：运行 RED 并记录**
  `npm --prefix web run test:e2e -- tests/e2e/standards-library.spec.ts`；记录列表仍然可见、返回按钮不存在的失败输出。

- [x] **Step 3：实现两级视图与重试**
  两级视图及宽窄切换的状态保留；错误重试只重发对应请求，加载中禁重复提交；清除筛选恢复 `DEFAULT_FILTERS`，不误清除已选标准；新文案中英同步。

- [x] **Step 4：补验收 E2E 并提交**
  添加 900×768、200% 缩放、长中英文文案、键盘操作与失败恢复用例；运行 `npm --prefix web run check:i18n`、`check:ui`、相关 Playwright 与构建；更新 `changelog.md`；提交。

### Task 9：统一新建与 CSV 弹窗焦点（F13）

**Files:**
- Modify: `web/src/components/standards/StandardCreateDialog.vue`
- Modify: `web/src/components/standards/OrdinaryPropertyEditor.vue`
- Modify: `web/src/i18n/locales/zh-CN/standards.ts`
- Modify: `web/src/i18n/locales/en-US/standards.ts`
- Test: `web/tests/e2e/standards-library.spec.ts`（新建草稿弹窗）
- Test: `web/tests/e2e/standards-editor.spec.ts`（CSV 导入弹窗）

**Interfaces:**
- Consumes: `web/src/components/ui/dialogFocus.ts`（既有 `UnsavedInputDialog`/`ConfirmModal` 同源）。
- Produces: 新建与 CSV 导入弹窗都有初始焦点、Tab 圈闭、Escape、关闭后焦点归还；CSV textarea 有可见关联标签。标准包导入弹窗由 [PLAN-DM-041](PLAN-DM-041-standard-package-import-picker.md) 同批处理，本任务不重复实现。

- [x] **Step 1：写 RED**
  两个弹窗分别覆盖打开焦点、Tab/Shift+Tab 圈闭、Esc、取消与提交后焦点归还；CSV textarea 的可见关联标签。当前两个弹窗均为手写遮罩而非原生 `<dialog>`，统一接入 `useDialogFocus`，不与编辑器三选一门禁叠加第二个焦点圈。

- [x] **Step 2：运行 RED 并记录**
  `npm --prefix web run test:e2e -- tests/e2e/standards-library.spec.ts tests/e2e/standards-editor.spec.ts`；记录焦点不进入弹窗、Esc 无响应等失败输出。

- [x] **Step 3：实现并验证**
  接入焦点工具、补可见标签与文案；运行前端单测、相关 Playwright、`npm --prefix web run check:ui` 与构建；更新 `changelog.md`；提交。

### Task 10：端到端验收、文档回写与完成门禁

**Files:**
- Modify: `docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md`
- Modify: `docs/dst-manager/specs/assets/SPEC-DM-016/README.md`
- Modify: `docs/dst-manager/guides/GUIDE-DM-007-official-standard-package-release.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-040-standard-platform-review-remediation.md`
- Modify: `changelog.md`
- Test: `tests/integration/test_standard_api.py`、`web/tests/e2e/standards-assets-publish.spec.ts`、`web/tests/e2e/standards-library.spec.ts`

**Interfaces:**
- Consumes: Task 1–9 的稳定 API、UI 与诊断码。
- Produces: 可复现验证记录、更新后的操作指南与契约索引；只有所有阻断和高优先级项均验证关闭，计划才可标记 `completed`。

- [x] **Step 1：闭环验证**
  用临时、非私有样本完成“本机 DWG → 草稿资产副本 → 保存 → CAD 布局检查 → 发布 → 导出 `.dststandard` → 新库导入 → 标准驱动创建预览”闭环；逐段记录包内路径、文件哈希与来源文件不变。无真实 CAD 环境时只记录明确跳过，不把替身测试当成 G9。

- [x] **Step 2：运行全量门禁**
  `uv run ruff check .`、`uv run pytest -q`、`uv lock --check`；`npm --prefix web run test:unit`、`check:api`、`check:i18n`、`check:ui`、`build`、`test:e2e`。本计划不涉及数据库迁移，不额外运行 Alembic；插件或真实 CAD 变更才按仓库门禁另跑双版本构建与系统测试。

- [ ] **Step 3：真实桌面 G9**
  在真实 Windows WebView2 按 SPEC-DM-016 G9 验证 DWG/DWT 资产文件选择、取消、中文/OneDrive 路径、200% 缩放、键盘焦点与导出；更新 G4/G8 生产证据并与已批准 Demo 逐项比较。标准包导入选择由 PLAN-DM-041 验收。真实桌面未执行时保持计划为 `active`，记录待验范围，不声称完成。

- [ ] **Step 4：复查与归档**
  复查 F01–F15 与 F17 每项的 RED/GREEN 证据、永久文档链接、`changelog.md` 与 Git 暂存内容；写入实际验证与遗留风险；全部完成后将计划状态改为 `completed` 并同步索引；只提交本计划涉及文件。

## 残余风险与回退

- **新资产复制端点的信任模型：** `POST /api/standards/drafts/{draft_id}/asset-files` 接受客户端给出的本机 `source_path`，任意本机进程都能让服务复制机器上任意 `*.dwg`/`*.dwt` 文件到草稿目录。这与既有 `POST /api/standards/drafts/from-dst`、`POST /api/standards/import` 处于同一信任等级（服务只监听 `127.0.0.1`、无鉴权）；缓解为：只接受 `.dwg/.dwt`、单文件 ≤64 MiB、只写入受控草稿目录、桌面 UI 只能经固定 `template` 对话框产生来源，无壳开发态显式标注为路径输入。
- **旧草稿目录名：** 目录名不符合单段规则的既有草稿在 `list()` 中被跳过，不会被删除；用户可手工重命名后恢复可见，`get_draft` 等入口对该目录返回稳定 `STANDARD_DRAFT_ID_INVALID`。
- **清理边界：** 只清理未被文档引用且匹配 `managed-` 前缀的受控副本，旧草稿或用户手工放置的 `assets/` 文件不受影响；放弃编辑产生的孤儿副本保留到下次保存/发布再清理。
- **契约兼容：** 草稿级保存路由为新增路由，既有身份路由保留且行为不变；如新端点需要回退，隐藏前端入口即可，已复制的受控资产副本仍可检查、发布与导出。
- **SPEC-DM-016 变更：** Task 3 修订 §8.1 与 `updated`，不改变 Schema 版本与既有文档合法性；实施前如用户要求改动契约范围，先更新规范再改代码。

## 完成标准

- F01–F15 与 F17 有针对性回归与通过记录；F16 由 [PLAN-DM-041](PLAN-DM-041-standard-package-import-picker.md) 独立验收，不作为本计划完成门禁。
- 模板资产从外部来源到发布包的每个边界只使用受控副本和包内相对路径；外部来源的哈希与 mtime 不变。
- 草稿与身份路由越界、缺失/非法资产发布/导入/导出、清单不一致、错误草稿操作四类高风险用例在仓储/API/E2E 对应层稳定失败后转绿。
- 标准库、编辑器和弹窗满足 SPEC-DM-016/017 与 ARCH-DM-007 的窄屏、焦点、标签、重试与双主题要求。
- 自动门禁与真实桌面 G9 均有实际结果；若环境缺失，记录跳过和恢复条件，计划不提前标记 `completed`。

## 修订记录

- 2026-09-24 首版：建立 F01–F16 与 Task 1–10，列明批次依赖与完成标准。
- 2026-09-24 审查后修订：F16 拆出为 PLAN-DM-041（用户裁决）；新增实测复现的 F17 并并入 Task 1；Task 1 边界扩展到 `standard_id`/`version` 身份段；Task 7 定案为新增草稿级保存路由并同步契约/TS；所有任务按 Step 展开（RED 断言、运行命令、期望失败、GREEN、changelog、提交）；补“发现溯源与基线证据”与核实 memo；明确 Task 3 受控副本命名与清理标记；批次改为串行执行；补齐 i18n 文件、残余风险与回退、命令形式；修复 front matter 的 YAML 缩进。

## 执行记录（2026-09-24）

任务按 1→10 串行执行，每个任务都先写失败用例、记录 RED，再实现并验证 GREEN，最后更新 `changelog.md`
并单独提交。提交：Task 1 `5a29dc4`、Task 2 `6188fcf`、Task 3 `51b1d8d`、Task 4 `fdf8026`、Task 5 `a8f7a59`、
Task 6 `112c86a`、Task 7 `7087315`、Task 8 `22a3637`（changelog 由 `926af41` 修复）、Task 9 `97b0fd4`。

### F01–F15 与 F17 关闭证据

| 编号 | 承接 | RED 证据（修复前实测） | GREEN 证据 |
| --- | --- | --- | --- |
| F01 | Task 3 | `asset-files` 端点 404；E2E 无「选择本机模板」入口 | 端点返回 `assets/managed-<uuid4hex>.dwg`；复制→保存→检查→发布 E2E 通过；真实 CAD 闭环（本文末）通过 |
| F02 | Task 2 | 发布缺失/绝对路径资产 HTTP **200**；导入缺失资产 HTTP **200** | 分别返回 422 `STANDARD_ASSET_FILE_MISSING` / `STANDARD_ASSET_PATH_INVALID`；草稿与发布根不变 |
| F03 | Task 5 | 空库新建后发布找不到详情；选中旧草稿后新建时检查命中 `draft-1` | 新建后选中身份指向新草稿；检查/复制/发布只调用 `draft-new-1` |
| F04 | Task 1 | 草稿 5 个入口 × 13 类非法输入全部 `DID NOT RAISE`，`../outside` 可写出草稿根外 | 全部 422 `STANDARD_DRAFT_ID_INVALID`；根外目录与文件哈希不变 |
| F05 | Task 5 | 同来源同版本两标准共用键，点第二项仍显示第一项详情 | `draftKey` 纳入 `standard_id`；两项详情与选中高亮各自正确 |
| F06 | Task 4 | 检查结果不绑定已保存快照，发布先保存再发布 | 「保存并检查」+ 代次/身份/快照三重校验；编辑后结果失效并阻断发布 |
| F07 | Task 4 | 无检查记录时面板显示「本次检查未发现问题」 | 显示「未检查」（含布局表），不再给假结论 |
| F08 | Task 6 | B 加载失败时派生仍从 A 提交 | 切换选择即清除旧详情；派生只消费身份匹配的已加载详情 |
| F09 | Task 6 | 点「v2.0.0 · 用户」后详情面板为空（键沿用官方来源） | 版本条目自带来源与标准 ID，跳转后显示用户来源详情 |
| F10 | Task 7 | 两个枚举源共用 `enum_item_id` 时切换源继承旧目标 | 目标缓冲按 `(source_property_id, enum_item_id)` 隔离，切回恢复未提交输入 |
| F11 | Task 7 | 身份字段可编辑，保存按新身份找不到草稿 | 身份只读 + 草稿级 `PUT /api/standards/drafts/{draft_id}`；身份不符 422 `STANDARD_IDENTITY_MISMATCH` |
| F12 | Task 8 | 详情打开后列表仍可见、无返回按钮 | ≤959px 列表↔详情互斥 + 可见「返回列表」；200% 缩放可达 |
| F13 | Task 9 | 两个弹窗打开后焦点留在页面、无圈闭与 Escape 响应 | 接入 `useDialogFocus`（初始焦点/圈闭/Escape/归还）+ CSV 可见关联标签 |
| F14 | Task 8 | 列表/详情错误无重试入口，筛选无结果无清除按钮 | 各自就地重试（禁用重复提交）+ 「清除筛选」恢复默认筛选且不误清选择 |
| F15 | Task 2 | `assets/../A2.dwg`、`assets\..\A2.dwg` 经 `normpath` 洗成合法条目 | 归一化前按分量拒绝 422 `STANDARD_PACKAGE_PATH_INVALID` |
| F17 | Task 1 | `GET /api/standards/%2E%2E/%2E%2E` 实测 **200** 并返回标准库根外 `document.json`；`/export` 把根外目录打成 zip | 身份路由与仓储三入口一律 422，响应与导出均不含根外内容 |

### 全量门禁（2026-09-24 实跑）

- `uv run pytest -q`：全量通过（含 `tests/integration/test_creation_api.py` 等；`test_candidate_without_template_files_is_unavailable` 已改为「发布后删除模板文件」以适配新发布门禁）。
- `uv run ruff check .`：通过。`uv lock --check`：通过（未改依赖）。本计划未改数据库模型，未额外运行 Alembic。
- `npm --prefix web run test:unit`：314 例通过；`npm --prefix web run check:api` / `check:i18n`（1593 键对称）/ `check:ui` / `build`：通过。
- `npm --prefix web run test:e2e`：全部标准相关 spec 通过（`standards-library` 51、`standards-editor` + `standards-assets-publish` + `standards-welcome` 79 及全量回归）。

### 真实 CAD 闭环（Task 10 Step 1）

用本机 AutoCAD 2016 Core Console 与双版本插件，以 `sample/project1` 真实 DWG 的临时副本完成
「本机模板 → 受控副本 → 保存 → 真实布局检查（诊断为空）→ 发布 → 导出 → 新库导入 → 标准驱动创建候选
（`available: true`，两个资产选项可用）」；全程来源与样本原件哈希/mtime 不变，包内路径一律相对路径。
逐段输出见 `docs/dst-manager/specs/assets/SPEC-DM-016/README.md` §三之四。

### 未完成与遗留

- **真实桌面 G9（Task 10 Step 3）未执行**：需要人工在真实 Windows WebView2 会话按 README §五逐项验收
  （原生文件选择对话框、系统缩放、键盘焦点、导出下载）。因此本计划保持 `active`，不得声明 G9 通过。
- **提交 22a3637 历史不干净**：该提交误把 `changelog.md` 暂存为空文件，已由 926af41 修复内容；如需干净
  历史须人工 rebase/squash（`git rebase -i 334704e`），代理未擅自改写历史。
- **工作区存在并发会话改动**：`PLAN-DM-041` 计划重写及其 `changelog.md` 段落、`.planning/README.md`、
  `docs/dst-manager/README.md` 的对应行由另一会话持有，本计划一律未暂存、未覆盖。
- **未纳入本计划**：F16（现成 `.dststandard` 包的受控选择与导入弹窗焦点）由 PLAN-DM-041 承接；
  `STANDARD_*` 业务码尚未进入 `message_catalog`，标准相关失败在界面上仍以通用文案 + 原始文本呈现。
