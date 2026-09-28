---
id: PLAN-DM-046
title: 无版本图纸标准身份与标准库管理实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-28
updated: 2026-09-28
related:
  - SPEC-DM-020
  - SPEC-DM-016
  - SPEC-DM-018
  - SPEC-DM-019
  - ARCH-DM-001
---

# 无版本图纸标准身份与标准库管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以独立 UUID、名称和 UTC 发布时间替换标准包发布版本；按已确认 Demo 改造标准管理页，将「版本说明」迁移为「标准描述」，完成平铺管理、改名导入和带关联草稿清理的用户已发布标准删除。

**Architecture:** 标准文档升级为 `schema_version: 3`，草稿创建时分配 UUIDv4，发布时写入 UTC Unix 毫秒时间戳。标准库以 UUID 定位包；导入仍使用限时快照和凭证确认，删除使用影响预览与可恢复的多目录事务；图纸集新创建链路只写 UUID，已有工程保持只读兼容。

**Tech Stack:** Windows 11、Python ≥3.12、UV、FastAPI、Vue 3、TypeScript、Vite、Vitest、Playwright、pywebview/WebView2。

**Spec:** [SPEC-DM-020](../../../docs/dst-manager/specs/SPEC-DM-020-versionless-standard-identity-and-management.md)；页面约束见 [SPEC-DM-016](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md) 和 [SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md)。

## 实施前迁移补充（2026-09-28）

计划执行前只读清点发现：默认本地数据根有 1 份用户标准草稿，格式为 `schema_version: 1`，使用非 UUID 身份且含旧 `version` 字段；草稿无 `description`、无 `release_notes` 且无资产。官方与用户已发布标准包、图纸集创建草稿均为 0。登记工作区有 302 条，其中 300 条目标 DST 已不存在；其余 2 个 DST 只读解析成功，均无 `DSTManager.Standard` 绑定或项目标准快照，读取前后时间戳一致。备用 `%LOCALAPPDATA%\dst-manager` 数据根没有标准库数据。清点未读取或记录标准名称、描述正文或私有路径。

为保留这份旧草稿，实施增加以下专用迁移路径：

1. 在第一次迁移前将整个本地 `standards/` 数据树复制到忽略目录下的 PLAN-DM-046 备份目录；校验源与副本文件数及 SHA-256 清单相同后才允许迁移。备份保留旧文件原始字节，不进入 Git。
2. 标准库初始化时，在既有进程互斥与跨进程文件锁内扫描用户草稿；只迁移草稿目录中的 schema v1/v2 文档，不迁移已发布包、不迁移工程 DST。每份草稿保留内部 `draft_id`、资产和其他受控字段，分配一次 UUIDv4 `standard_id`，改写为 schema v3、`published_at: null`，移除标准 `version`。
3. `description` 已存在时原样保留；否则从字符串 `release_notes` 原样迁移；没有可信文本时为空字符串；迁移后的新文档移除 `release_notes`。双字段冲突以 `description` 为准，并在不含原文、名称、ID 或路径的本地迁移报告中记录冲突数量。
4. 迁移前验证目标 UUID 与规范化名称可用；通过同目录临时文件及原子替换写入。失败时保留原草稿和备份；重试不得重复分配身份或丢失文本。迁移报告只记格式类别、数量、冲突数和结果，不记私有内容。
5. 在标准库与迁移模块回归测试中覆盖 UUID 稳定性、发布时间为空、旧版本字段移除、`release_notes` 原文迁移、双字段冲突计数、原子写入失败回滚与重入。若以后在目标数据根发现旧发布包或含标准绑定的旧项目，当前迁移不自动处理，必须先增加相应映射与备份设计。

## Global Constraints

- `standard_id`：新草稿使用 UUIDv4；输入允许 UUID 文本大小写差异并规范化为小写带连字符形式，拒绝缺连字符或非法值；没有标准发布 `version` 或来源关系。
- `published_at`：草稿为 `null`；新发布为 UTC Unix 毫秒整数；导入保留包内值；UI 按系统时区显示 `YYYY/MM/DD HH:mm`。
- `description`：可为空的标准级纯文本；草稿可编辑，发布、复制和包导入导出保留；新 v3 文档不写 `release_notes`。迁移旧 `release_notes` 时保留原文，双字段冲突列入迁移报告。
- 新格式文档与包使用 `schema_version: 3`；`dependencies[*].min_version` 的三段版本不变。
- 已发布内容只读；仅用户已发布标准与用户草稿可删除，官方标准前后端均禁止删除；导入改名只修改本机入库副本，不修改原包；官方／用户来源过滤与名称／ID 搜索、状态过滤继续可用。
- 正式页面保留 Demo 的布局和信息层级，使用现有浅深主题及真实数据／真实动作；列表名称下一行显示可截断描述，不显示 ID，详情标题下不显示描述，完整描述放在内容概览。
- 新写入的创建草稿、计划、XLSX 元数据、工程绑定仅用 UUID；只读打开旧工程不改 DST/DWG。
- 标准库写入沿用进程内互斥和跨进程文件锁；导入与删除须保持失败可恢复，不接受部分结果。
- Web 服务只监听 `127.0.0.1`；包路径、资产、大小上限和凭证安全门禁沿用现有实现。
- 每个代码任务更新 `changelog.md`；实施前清点旧标准数据与绑定工程，发现真实旧数据先完成备份和迁移设计，不能直接不兼容写入。

## Review Focus

1. UUID 只有大小写或格式差异、名称只有 NFKC／空白／大小写差异：规范化后不产生第二个标准。Task 1、2、3 测试覆盖。
2. 导入预检后同 ID 或最终名称被另一请求占用：确认时稳定拒绝，原包与已有数据不变。Task 3 测试覆盖。
3. 删除影响预览后新建关联草稿：旧确认失效，必须重新展示数量，不多删。Task 5 测试覆盖。
4. 删除中途断电或目录移动失败：启动恢复使标准与关联草稿全有或全无。Task 5 测试覆盖。
5. 系统时区、夏令时与无可信旧发布时间：只在展示层转换，新 v3 包不伪造时间，旧工程只读打开无副作用。Task 1、4、6 测试覆盖。
6. 旧版 `release_notes` 到 `description` 的迁移：草稿与已发布包不丢文字，新包没有旧字段，列表摘要与详情读取一致。Task 1、2、3、6、7 测试覆盖。
7. 官方标准删除：界面无入口，直接请求也被拒绝，不能删除官方包或关联草稿。Task 5、6 测试覆盖。

---

### Task 1：领域身份与文档格式

**Files:** 修改 `src/dst_manager/domain/standard_models.py`、`standard_schema.py`、`standards.py`、`standard_identity.py`；新建 `standard_errors.py`、`standard_versioning.py` 以守住文件容量边界；修改 `tests/unit/test_drawing_standards.py`、`tests/unit/creation_xlsx_fixtures.py`；更新 `changelog.md`。

**Interfaces:** `new_standard_id() -> str` 返回小写 UUIDv4；`parse_standard_id(value: object) -> str` 接受大小写差异并返回规范小写 UUID，拒绝缺连字符或非法值；`materialize_published_document(document: Mapping[str, object], published_at: int) -> dict[str, object]` 仅注入发布时间；`parse_standard_draft_document` 接受 `published_at: null`，`parse_published_standard_document` 接受有效 UTC 毫秒值，均拒绝标准发布 `version`。两种 v3 文档接受可为空的顶层 `description: str`，新写入不含 `release_notes`。

- [x] **Step 1: Write failing tests.** 新空白／复制／DST 草稿都各有 UUID、`published_at=null`；已发布文档有有效毫秒整数；布尔、小数、字符串、无效 UUID、遗留 `version` 均稳定拒绝；扩展 `min_version="1.2.0"` 仍接受。描述在草稿与发布物化后保持一致，空描述合法，非字符串描述拒绝，v3 新写入不含 `release_notes`。
- [x] **Step 2: Verify RED.** Run `rtk uv run pytest -q -p no:xdist -o addopts='' tests/unit/test_drawing_standards.py`；新断言失败于尚未实现的新字段或签名。
- [x] **Step 3: Implement domain signatures above.** 保留属性、资产与规则解析；仅替换标准身份字段和发布物化。发布时间由调用者注入，不读取文件时间推断发布时间。
- [x] **Step 4: Verify GREEN.** 重跑上述测试并运行领域 Ruff 检查；均通过。
- [x] **Step 5: Commit this task.** 仅暂存本任务文件与 `changelog.md`，提交中文动词开头的说明（`9a96eab`）。

### Task 2：标准库 UUID 存储、发布与平铺摘要

**Files:** 修改 `src/dst_manager/infrastructure/standards/store.py`、`src/dst_manager/application/standards.py`、`src/dst_manager/domain/standard_schema.py`（允许草稿名称为空但仍要求名称字段）；新建 `src/dst_manager/infrastructure/standards/identity_index.py`（名称和 ID 占用判断，避免继续扩张大型 store）、`migration.py`（v1/v2 草稿备份与原子迁移）；修改 `tests/unit/test_standard_store.py`、`tests/unit/test_drawing_standards.py`，新增 `tests/unit/test_standard_store_identity.py`、`tests/unit/test_standard_migration.py`；更新 `changelog.md`。

**Interfaces:** `StandardStore.get(standard_id: str) -> DrawingStandard | None`；`StandardStore.publish(draft_id: str, *, published_at: int) -> PublishedStandard`；`StandardStore.check_available_identity(standard_id: str, name: str) -> None`；摘要含 `description: str`、`published_at: int | None`，不含 `version`，列表无需逐项加载详情。新目录为 `official/<uuid>/document.json`、`user/published/<uuid>/document.json`，草稿沿用独立 `draft_id` 目录。

- [x] **Step 1: Write failing tests.** 两个从同一源复制的草稿发布后成为两个独立 UUID；名称冲突对官方、用户和非空草稿一致；并发发布不会产生同 ID；发布故障后草稿和资产仍在；列表每包一项且摘要携带草稿／已发布描述，不归集版本。迁移用例覆盖 v1/v2、UUID 稳定、描述／旧说明保留与冲突计数、完整备份哈希校验、原子写入失败保留原稿及部分完成后可重入。
- [x] **Step 2: Verify RED.** 已运行 `tests/unit/test_standard_store_identity.py` 与 `tests/unit/test_standard_migration.py`，新断言失败。
- [x] **Step 3: Implement the interfaces.** 在既有库锁内校验 ID／名称并发布；`draft_id` 仍只定位存储目录。使用 `time.time_ns() // 1_000_000` 获取发布时间，并在测试中注入固定时钟。移除下一发布版本分配和 `standard_id/<n>` 新写入，保持路径越界、资产和原子发布门禁。发现用户 v1/v2 草稿时，先验证整棵标准库备份及 SHA-256 清单，再仅迁移草稿目录中的文档；不迁移旧发布包或工程 DST。
- [x] **Step 4: Verify GREEN.** 重跑本任务测试并执行计划范围的 Ruff 检查。
- [x] **Step 5: Commit this task.** 只提交本任务改动。

### Task 3：标准包预检、改名导入与导出

**Files:** 修改 `src/dst_manager/infrastructure/standards/package.py`、`import_previews.py`、`store.py`，`src/dst_manager/application/standards.py`，`src/dst_manager/interfaces/standard_contracts.py`、`standard_api.py`、`message_catalog.py`；修改 `tests/unit/test_standard_import_previews.py`、`tests/unit/test_standard_package.py`、`tests/integration/test_standard_api.py`；更新 `changelog.md`。

**Interfaces:** 预检响应保留 `preview_id`、`expires_at`、`can_import` 和诊断，改为 `standard_id`、`name`、`description`、`published_at`、`name_conflict: bool`、`existing_name: str | None`；确认请求为 `{preview_id, name?: str}`，名称相同且 ID 不同须提供可用新名称；同 ID 返回 `STANDARD_ID_EXISTS` 并优先于名称冲突。导出文件名 `<uuid>.dststandard`，manifest／document 保留 `description`。

- [ ] **Step 1: Write failing tests.** 同 ID、不同名、不同时间仍阻止且显示本机已有名称；仅同名时保留预检凭证，改名后导入保留 ID／时间／描述、原包字节不变；导出再导入描述一致且不产生 `release_notes`；并发占用在确认时返回 409；重复确认同一凭证幂等返回首次结果；非法包和逃逸资产仍拒绝。
- [ ] **Step 2: Verify RED.** Run `rtk uv run pytest -q -p no:xdist tests/unit/test_standard_import_previews.py tests/unit/test_standard_package.py tests/integration/test_standard_api.py`。
- [ ] **Step 3: Implement preview and confirm.** 继续只消费预检快照；在库锁内校验最终名称和 ID，仅重写入库副本 manifest／document 的 `name` 并重新执行完整校验，原压缩包不写回。更新 OpenAPI 生成类型和中英文错误文案。
- [ ] **Step 4: Verify GREEN.** 重跑本任务测试与 `rtk uv run ruff check .`；生成的 `web/src/api/schema.d.ts` 与接口一致。
- [ ] **Step 5: Commit this task.** 只提交本任务改动。

### Task 4：创建草稿、计划、XLSX 与工程绑定改为 UUID

**Files:** 修改 `src/dst_manager/domain/creation.py`、`creation_plan_models.py`、`creation_planning.py`，`src/dst_manager/infrastructure/creation_drafts.py`、`creation_xlsx_protocol.py`、`acsm_xml/creation.py`，`src/dst_manager/application/creation_drafts.py`、`creation.py`、`creation_assets.py`、`creation_execution.py`、`standards.py`，`src/dst_manager/interfaces/creation_contracts.py`、`creation_api.py`；修改对应 `tests/unit/test_creation_drafts.py`、`tests/integration/test_creation_api.py`、`test_created_project_opens.py`、`test_standard_service.py`；更新 `changelog.md`。

**Interfaces:** `create_creation_draft(standard_id: str) -> CreationDraft`；`CreationDraft.standard_id: str` 且无 `standard_version`；`standard_package_root(store: StandardStore, standard_id: str) -> Path | None`；新工程 `DSTManager.Standard=<uuid>`；新 XLSX 元数据 `standard_id=<uuid>` 且不写 `standard_version`。创建草稿和创建任务入队与标准删除共用生命周期锁。

- [ ] **Step 1: Write failing tests.** 创建／恢复／预览／执行都只按 UUID 定位；模板导入匹配 UUID；新工程绑定与项目快照目录为 UUID；删除库内标准后已创建项目仍由快照打开；旧 `id@version` 工程只读解析且打开不写磁盘。运行中任务继续锁定原标准内容。
- [ ] **Step 2: Verify RED.** Run `rtk uv run pytest -q -p no:xdist tests/unit/test_creation_drafts.py tests/integration/test_creation_api.py tests/integration/test_created_project_opens.py tests/unit/test_standard_service.py`。
- [ ] **Step 3: Implement the interfaces.** 保留旧工程绑定解析为只读兼容分支，不对旧 DST／快照执行身份迁移；新创建链路不得写旧格式。旧数据清点结果若含真实用户包或创建草稿，按 Global Constraints 先追加独立迁移设计和测试再继续。
- [ ] **Step 4: Verify GREEN.** 重跑本任务测试和 `rtk uv run ruff check .`；旧工程只读测试核对 DST／DWG 文件哈希与时间戳均不变。
- [ ] **Step 5: Commit this task.** 只提交本任务改动。

### Task 5：删除影响预览与关联草稿事务

**Files:** 新建 `src/dst_manager/infrastructure/standards/delete_transaction.py`；修改 `src/dst_manager/infrastructure/creation_drafts.py`、`src/dst_manager/application/standards.py`、`src/dst_manager/interfaces/standard_contracts.py`、`standard_api.py`、`message_catalog.py`；新建 `tests/integration/test_standard_delete.py`，修改 `tests/unit/test_standard_store.py`；更新 `changelog.md`。

**Interfaces:** `GET /api/standards/{standard_id}/delete-impact` 返回 `{standard_id, affected_count, impact_token}`；`POST /api/standards/{standard_id}/delete` 接收 `{impact_token}`。服务端确认时重算关联集合，变化返回 `STANDARD_DELETE_IMPACT_CHANGED`（409）；非终态创建任务返回 `STANDARD_DELETE_JOB_ACTIVE`（409）；成功返回删除数量。`CreationDraftStore.list_by_standard(standard_id: str) -> tuple[str, ...]` 只枚举有效草稿；`impact_token` 是关联 ID 集合和目标身份的摘要，仅用于检测预览变化，不是授权凭证。

- [ ] **Step 1: Write failing tests.** 零／多个关联草稿的预览与确认；取消不改变；确认后只删除目标用户标准和匹配草稿；官方标准即使被直接调用预览或删除 API 也稳定拒绝且不清除草稿；预览后新增草稿使旧 token 失效；运行中任务拒绝；注入每次目录移动失败和重启恢复，验证无部分删除；已建工程快照仍可读。
- [ ] **Step 2: Verify RED.** Run `rtk uv run pytest -q -p no:xdist tests/integration/test_standard_delete.py tests/unit/test_standard_store.py`。
- [ ] **Step 3: Implement the transaction.** 在库锁内完成最终关联扫描与任务状态检查；把目标包和关联草稿移动到同一数据根的事务暂存区，持久化清单与提交标记，失败回滚，启动时按标记恢复或完成清理。路径严格由校验后的 UUID／草稿 ID 构造；不碰项目快照或 DST/DWG。
- [ ] **Step 4: Verify GREEN.** 重跑本任务测试与 `rtk uv run ruff check .`；重复确认、缺失对象和重启恢复具有稳定响应。
- [ ] **Step 5: Commit this task.** 只提交本任务改动。

### Task 6：标准管理与创建向导界面

**Files:** 修改 `web/src/components/standards/standardLibraryModel.ts`、`StandardLibraryPane.vue`、`StandardDetailPane.vue`、`StandardImportDialog.vue`、`StandardEditor.vue`、`StandardPublishReview.vue`，`web/src/views/StandardsView.vue`，`web/src/features/standards/types.ts`、`store.ts`、`draftModel.ts`，`web/src/api/standards.ts`、`creation.ts`，创建向导的 `StandardStep.vue`、`ReviewStep.vue`，中英文 `standards.ts`／`errors.ts`；修改相关 Vitest 与 `web/tests/e2e/standards-library.spec.ts`、`standards-welcome.spec.ts`、`standards-assets-publish.spec.ts`、`create-sheetset-input.spec.ts`；更新 `changelog.md`。

**Interfaces:** 列表数据模型为平铺 `StandardSummary[]`，摘要包含 `description`，保留 `StandardFilters`；顶部按钮顺序固定；显示时间用 `Intl.DateTimeFormat` 的系统时区和显式数字字段组装 `YYYY/MM/DD HH:mm`，避免区域设置改变分隔符。发布检查输入改为「标准描述」并绑定 `description`。删除对话框消费 `delete-impact`，提交 token；名称冲突导入对话框编辑 `name`。

- [ ] **Step 1: Write failing tests.** 平铺列表不显示版本组；名称下显示描述，长描述单行省略，列表不显示 ID 但 ID 搜索仍命中；详情标题下无描述，内容概览显示全文；搜索和来源／状态过滤保持原行为；固定顶部按钮在长列表、900×768 和 200% 缩放可见；浅深主题布局一致；时间按模拟时区转换；发布检查「标准描述」保存后在摘要和详情可见；同 ID 导入阻止、同名导入改名；仅用户已发布标准有删除动作，删除关联数量和取消／确认文案正确；创建向导不显示版本。
- [ ] **Step 2: Verify RED.** Run `rtk npm run test:unit`（工作目录 `web`）及定向 Playwright 用例；新增断言失败。
- [ ] **Step 3: Implement UI.** 依 Demo 改造顶部标题／操作区、左侧标准库卡片和右侧详情分区，沿用现有主题令牌及真实服务端动作，不带入演示数据和情境切换。删除组展开状态和版本历史视图；保留现有名称／ID 搜索和过滤逻辑。列表卡片名称下一行使用单行省略的描述并提供完整文本访问方式；移除卡片 ID，详情基本信息仍完整显示且可复制。详情标题下不渲染描述，内容概览中完整展示。将新建、导入动作移到 `StandardsView` 顶部返回按钮左侧，从列表底部移除重复入口；保留已有「用于创建图纸集」等正式动作。把 `releaseNotes` UI 状态与文案迁移为 `description`。删除失败与影响变化时保留当前标准并刷新数量。
- [ ] **Step 4: Verify GREEN and visual acceptance.** Run `rtk npm run test:unit`、`rtk npm run build` 和定向 `rtk npx playwright test ...`（工作目录 `web`）；全部通过。另在 1440×900 浅色／深色、900×768 和 200% 缩放下截取真实页面证据，对照 [Demo 截图](../../../docs/dst-manager/specs/assets/SPEC-DM-020/standard-management-demo-light.png) 及下列验收项逐项核对，记录通过／偏差；截图只作布局参照，以 SPEC-DM-020 的后续文字修订覆盖其中旧 ID／描述位置。
- [ ] **Step 5: Commit this task.** 只提交本任务改动。

**Task 6 视觉验收项：**

1. 页眉下是标题与独立操作区；「新建草稿」「导入标准包」「返回欢迎页」按此顺序排列，列表滚动时仍可见，前两项不落到列表底部。
2. 桌面宽度下为左侧标准库卡片、右侧详情卡片的主从布局；搜索及来源／状态筛选位于左卡片顶部，较长的标准列表在自身区域滚动，不推动操作区离开视口。
3. 列表项的视觉顺序为名称及来源／状态徽标、下一行单行省略的标准描述、已发布时的本地发布时间；不出现 ID、发布版本或版本组。无描述有统一空值提示；键盘及屏幕阅读器可获得完整描述。
4. 详情依次为名称／徽标／动作、基本信息、标准内容概览；名称正下方不显示描述。基本信息完整展示并可复制 UUID，概览可读描述全文；用户已发布标准有删除动作，官方标准无删除动作。
5. 两种主题使用现有语义令牌，层级、间距和可读性一致；窄视口按列表→详情切换，900×768 与 200% 缩放下没有横向溢出、遮挡或不可达动作。Demo 的假数据、情境切换和演示提示均不进入产品。

### Task 7：兼容清点、端到端验证与交付文档

**Files:** 修改 `docs/dst-manager/guides/GUIDE-DM-007-official-standard-package-release.md`、`README.md`、`docs/dst-manager/README.md`、`.planning/README.md`、`changelog.md`；按实际生成结果更新测试夹具及 `web/src/api/openapi.json`、`schema.d.ts`。

**Interfaces:** 发布包指南只描述 UUID＋发布时间＋标准描述；旧 `schema_version: 2`、`release_notes` 与 `id@version` 数据清点报告包括目录／数量和双字段冲突数量而不包含用户私有路径或描述正文；任何真实旧用户数据触发迁移设计门禁，不执行删除重建。

- [ ] **Step 1: Record migration inventory.** 检查官方／用户库、创建草稿与绑定工程是否存在旧身份及 `release_notes`；只记录数量、类型和双字段冲突数量，不记录描述正文。若有真实数据，先补迁移方案、备份与回归测试，验证原文字迁移；无真实数据时更新公开夹具和官方包制作流程。
- [ ] **Step 2: Run backend gates.** `rtk uv run ruff check .`、`rtk uv run pytest -q`、`rtk uv lock --check`；按结果处理真实失败，不把既有环境失败写成通过。
- [ ] **Step 3: Run frontend gates.** 在 `web` 中运行 `rtk npm run test:unit`、`rtk npm run build`、相关 `rtk npx playwright test`；核对生成 OpenAPI、类型与 i18n 守卫。
- [ ] **Step 4: Review user flows.** 逐项走新建→输入标准描述→发布→在列表／详情查看描述→导出→导入（同 ID／同名）→创建草稿→用户标准删除确认→已建项目打开；核对官方标准删除请求被拒绝。复核 Task 6 五项视觉验收及截图证据；在真实桌面壳可用时验证原生包选择器、浅深主题与窄视口，缺少环境则如实记录未验证。
- [ ] **Step 5: Update docs and commit.** 仅在实现完成后更新 README 的“当前功能”描述，将本计划状态及验证结果记入文档；只提交本任务文件。
