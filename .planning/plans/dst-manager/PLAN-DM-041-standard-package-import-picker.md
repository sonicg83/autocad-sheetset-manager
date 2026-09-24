---
id: PLAN-DM-041
title: 标准整数版本、按 ID 归集与标准包预检导入实施计划
status: active
owners:
  - dst-manager
created: 2026-09-24
updated: 2026-09-25
related:
  - ARCH-DM-001
  - ARCH-DM-007
  - SPEC-DM-016
  - SPEC-DM-017
  - SPEC-DM-018
  - PLAN-DM-035
  - PLAN-DM-039
  - PLAN-DM-040
---

# 标准整数版本、按 ID 归集与标准包预检导入实施计划

> **实施要求：** 按任务执行 RED → 最小实现 → GREEN → 复核 → 提交；复选框仅在实际完成后勾选。实施前阅读本计划引用的规范、[ARCH-DM-001](../../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)、[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) 和相关源码、测试。本文是实施计划，Task 1 建立长期权威规范。

**目标：** 草稿发布时由服务端分配 `v1、v2…` 整数版本；标准库按 `standard_id` 归集；桌面用户选择 `.dststandard` 后先看独立预检，再确认导入，重复身份或不同 ID 的同名标准不能进入标准库。

**架构：** 标准发布版本的领域值与包内 `manifest.json` 字段是正整数，界面加 `v` 展示。草稿不持有正式版本；发布时从官方库与用户库同 ID 的现有版本计算下一整数并在受控写入边界内占用身份。导入先把选定的包复制到应用数据目录的限时快照，校验并返回预检凭证；确认只消费该快照，重新检查身份、名称与包门禁后原子写入用户库。

**技术栈：** Windows 11、Python ≥3.12、UV、FastAPI、Vue 3、TypeScript、Vite、Vitest、Playwright、pywebview/WebView2。

**规范依据：** [SPEC-DM-016](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md) §4、§5、§12，[SPEC-DM-017](../../../docs/dst-manager/specs/SPEC-DM-017-standard-properties-and-dwg-naming.md)，[SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md)，[官方包指南](../../../docs/dst-manager/guides/GUIDE-DM-007-official-standard-package-release.md)。Task 1 先补本轮增量规范，后续代码任务据此执行。

## 范围、依赖和已确认裁决

- 本轮重写取代原 PLAN-DM-041 的“只补文件选择、继续直接调用路径导入”方案。原 F16／PLAN-DM-039 F7、无壳开发态回退、导入弹窗焦点和真实桌面验收仍由本计划负责。
- 用户已确认：标准版本是正整数，用户看到 `v1、v2`；草稿不让用户填写版本，本机发布由后端分配；导入保留包内版本，不重编号、不覆盖旧版，也不要求导入版本高于库内最高版。
- 同一 `standard_id + version` 在官方与用户库之间仍唯一。相同 ID 的多个版本可沿用同一显示名称；不同 ID 的已发布标准显示名称冲突时，预检与最终写入均阻止。导入弹窗不改写包内名称，提示修改原始标准并重新生成包。本机发布执行同一名称门禁。
- 用户确认目前**没有已分发的真实标准包或绑定工程**。实施前再次核实；若出现真实数据，先补兼容/迁移设计，不得直接进行不兼容格式变更。仓库里的旧测试夹具与 Demo 均须更新。
- 与正在执行的 [PLAN-DM-040](PLAN-DM-040-standard-platform-review-remediation.md) 串行衔接：其共享的后端路径/资产门禁和标准库 UI 任务落地后，按最新代码复核本计划文件清单。PLAN-DM-040 负责 F01–F15/F17；本计划不重复 F05 的选择键、F09 的跨来源跳转或 F13 的新建/CSV 弹窗焦点修复。两份计划分别记录 G9，最后复跑资产到包的完整链路。
- 不改动 DST/DWG 发布器、CAD SCR 或插件。标准包路径逃逸、资产存在性、大小上限和发布门禁继续由后端最终执行；壳过滤器仅协助选择。Web 服务继续只监听 `127.0.0.1`。

## 版本与接口契约

| 对象 | 约定 |
| --- | --- |
| 正式标准文档及包 | `schema_version: 2`，`version` 是 `1..2147483647` 的 JSON 整数；`0`、负数、布尔值、小数和旧三段字符串拒绝。`schema_version` 是文档格式版本，与标准发布版本不同。 |
| 草稿文档 | `schema_version: 2`，不含 `version` 字段；派生草稿也不预占版本。列表响应以 `version: null` 表示草稿，已发布项为整数。 |
| 依赖版本 | `dependencies[*].min_version` 是扩展能力版本，保留三段语义化字符串（如 `1.2.0`），与标准发布整数版本无关；`schema_version: 2` 不改变其格式与校验。实现时把现 `_parse_version` 拆为标准版本与依赖版本两个解析器，不得共用同一 pattern。 |
| 残留 v1 数据 | 目录名合法但 `schema_version: 1` 的历史草稿/发布目录不做自动迁移：`list()` 跳过（沿用 PLAN-DM-040 Task 1 非法草稿目录先例），`get`/`get_document`/`read_package` 返回稳定 `STANDARD_SCHEMA_VERSION_UNSUPPORTED`（422）。出现真实历史数据时先暂停并修订兼容规则。 |
| API、目录与工程绑定 | API JSON 的 `version`/`standard_version` 为整数；路由采用十进制正整数路径段，发布目录是 `<standard_id>/<n>/`，工程保留属性是 `<standard_id>@<n>`。UI 展示 `v<n>`，导出文件名是 `<standard_id>-v<n>.dststandard`。 |
| 本机发布 | 后端在官方与用户库中取同 ID 的最高整数，分配 `max+1`；无历史为 `1`。并发发布不得得到相同版本，失败不消耗版本，也不留下半成品。 |
| 外来包导入 | 保留包内整数版本；相同 ID/版本拒绝，尚不存在的较早版本允许。不同 ID 的规范化同名拒绝。 |
| 名称比较 | 对官方/用户已发布版本的名称使用 Unicode NFKC、首尾去空白、连续空白归一和 `str.casefold()` 大小写折叠比较（不得用 `lower()`，避免德语 ẞ、土耳其 İ 等归一不一致）；草稿不占名称。同 ID 跨版本改名允许；组标题取当前筛选结果中最高整数版本的名称，仅有草稿时用标准 ID，历史版本显示其原名称。 |
| 预检 | `POST /api/standards/import-previews` 接收 `{path}`，返回候选身份、同 ID 已有版本、稳定诊断、`can_import`、可用时的不透明 `preview_id` 与到期时间；身份/名称冲突返回 200 且 `can_import=false`，包或路径非法返回 422；预检不写标准库。 |
| 确认 | `POST /api/standards/import` 仅接收 `{preview_id}`，不得继续接受 `{path}`；确认复核库状态并从预检快照导入。同一凭证重复确认返回相同成功结果，不二次写入；过期、伪造或重启后失效的凭证要求重新预检。 |

上述整数身份须贯穿标准创建草稿、预览、执行、XLSX 元数据、工程绑定与 OpenAPI/TS 类型，不得只改标准库页面。旧 `schema_version: 1` 不进入新包导入与发布路径；如果实施前出现真实历史数据，先暂停并修订兼容规则。

## 交付顺序

| 批次 | 任务 | 可独立验收的结果 | 前置条件 |
| --- | --- | --- | --- |
| A：长期契约与领域 | 1 → 2 | 增量规范、v2 整数解析、无版本草稿；发布入口处于显式暂停态（422 `STANDARD_VERSION_UNASSIGNED`），由 Task 3 解除 | PLAN-DM-040 共享代码阶段收敛 |
| B：发布身份 | 3 → 4 | 自动分配、同名门禁、创建与绑定全链路整数身份 | A |
| C：两步导入 | 5 | 限时快照、预检凭证和确认导入 | B；复用 PLAN-DM-040 资产门禁 |
| D：桌面界面 | 6 → 7 | 按 ID 归集、无版本输入、原生选择和弹窗状态 | C；复用 PLAN-DM-040 F05/F09 结果 |
| E：验收 | 8 | 自动门禁及真实桌面 G9 实证 | A–D |

PLAN-DM-040 尚在修改 `StandardsView.vue`、`StandardLibraryPane.vue`、`StandardDetailPane.vue` 等共享文件时，本计划只做文档和只读核对，不并发修改这些文件。实际实施时先重新核对最新接口；若已有实现与下方文件清单不同，先修订任务的文件和测试入口，再开始 RED。

## Review Focus

1. 两份同 ID 草稿并发发布，各得到不同整数；故障后原草稿、资产和已发布版本完整。Task 3 覆盖。
2. 先导入 `v3` 再导入缺失的 `v2` 可行；同 ID/同版本即使包文件名不同也拒绝。Task 5 覆盖。
3. 不同 ID 的名称仅在全角、空白或大小写上不同，或预检后库状态变化：预检及最终写入均阻止。Task 3、5 覆盖。
4. 原文件在预检后被替换/删除、凭证重放/伪造/过期、复制中断或应用重启：只消费限时快照或要求重新预检，不出现部分导入。Task 5、7 覆盖。
5. `v10` 与 `v9`、同 ID 多来源版本、不同 ID 同版本、900×768 和 200% 缩放：分组、选中、跳转及导入定位正确。Task 6–8 覆盖。

---

### Task 1：建立整数版本和两步导入的长期规范

**Files:** 新建 `docs/dst-manager/specs/SPEC-DM-019-standard-version-and-package-import.md`；修改 `docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md`、`docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md`、`docs/dst-manager/guides/GUIDE-DM-007-official-standard-package-release.md`、`docs/dst-manager/README.md`、`changelog.md`。

**Interfaces:** SPEC-DM-019 成为 v2 标准文档、版本分配、名称唯一和预检确认的长期权威；SPEC-DM-016/018 只写页面行为并链接它，官方包指南写制作/审核流程。

- [x] 核对 PLAN-DM-040 已交付门禁，按本计划“版本与接口契约”创建 SPEC-DM-019，使用 YAML 元数据和未占用永久 ID；在 SPEC-DM-016 §4.2/§5、SPEC-DM-018 的版本展示处做增量修订，保留已有规范历史。SPEC-DM-019 必须写明：`dependencies[*].min_version` 保留三段字符串、标准 `version` 用 `casefold()` 比较名称、残留 v1 目录“`list()` 跳过、读取返回 `STANDARD_SCHEMA_VERSION_UNSUPPORTED`”的处置规则。
- [x] 固定临时快照根 `settings.data_dir/tmp/standard-import-previews`、15 分钟有效期、256 MiB 压缩源文件上限、过期/取消清理和重启后凭证失效；临时文件不得进入工程目录。固定非法包/路径为 422，同身份/同名为 409，过期凭证为 410，未知凭证为 404；预检冲突以 `can_import=false` 与诊断呈现。在 SPEC-DM-019 显式记录预检信任模型：与 PLAN-DM-040 `asset-files`/`from-dst` 同级（服务只监听 `127.0.0.1`、无鉴权，任意本机进程可请求复制 `.dststandard` 入快照根），缓解为扩展名白名单、256 MiB 上限、限时清理、重启失效与快照根隔离。
- [x] 更新官方包指南的 `schema_version: 2`、整数版本、不可覆盖和文件名示例。检查新文档、索引链接、YAML 与本文一致，再提交文档；后续代码任务以此规范为依据。

### Task 2：正整数领域契约与无版本草稿

**Files:** `src/dst_manager/domain/standard_schema.py`、`src/dst_manager/domain/standard_models.py`、`src/dst_manager/domain/standards.py`、`src/dst_manager/application/standard_assets.py`、`src/dst_manager/infrastructure/standards/store.py`、`src/dst_manager/infrastructure/standards/package.py`、`src/dst_manager/infrastructure/standards/dst_import.py`；`tests/unit/test_drawing_standards.py`、`tests/unit/test_standard_store.py`、`tests/unit/test_standard_package.py`、`tests/integration/test_standard_dst_import.py`、`changelog.md`。

**Interfaces:** `parse_standard_draft_document(data) -> DraftDrawingStandard` 不带版本；`materialize_published_standard(draft, version: int) -> DrawingStandard` 构造发布候选；`parse_published_standard_document(data) -> DrawingStandard` 只接受 v2 正整数。`_parse_version` 拆为 `_parse_standard_version`（正整数，含布尔/小数/字符串拒绝）与 `_parse_dependency_version`（保留三段 `X.Y.Z`），两者不得共用 pattern。仓储摘要中草稿版本为 `None`，已发布版本为整数；目录段仍执行 PLAN-DM-040 的路径边界检查。

- [x] 写 RED：无 `version` 草稿及从 DST 提取的草稿都可保存，草稿携带版本被拒；发布文档接受 `1`/`10`，拒绝 `0`、`-1`、`True`、`1.5`、`"1"`、`"1.0.0"`、超过上限和 `schema_version=1`；依赖 `min_version` 继续接受 `"1.2.0"`、拒绝 `1`、`"1"`，证明两个解析器已拆分；不同整数版本并存，导出包保留整数；`schema_version: 1` 残留目录在 `list()` 中跳过，`get_document`/`read_package` 返回 `STANDARD_SCHEMA_VERSION_UNSUPPORTED`。运行 `rtk uv run pytest -q -p no:xdist tests/unit/test_drawing_standards.py tests/unit/test_standard_package.py tests/integration/test_standard_dst_import.py` 及新增仓储读取用例，记录 RED。
- [x] 拆分草稿与发布领域模型；保留资产/属性的公共读取接口，发布时才由 `materialize_published_standard` 注入整数版本并过完整解析。更新仓储读取、目录、包序列化与夹具；不混淆文档格式版本和发布版本。本任务完成后、Task 3 改造前，`store.publish()` 进入显式过渡态：草稿无版本可分配时返回稳定 422 `STANDARD_VERSION_UNASSIGNED`，不写任何目录；既有发布用例改为断言该过渡码（直接以 `materialize_published_standard` 构造发布文档的夹具不受影响）。上述用例、`rtk uv run ruff check .` 为 GREEN；仓储发布全集在 Task 3 改造后运行，并在 `changelog.md` 记录阶段性范围（含过渡码仅为 Task 2→3 衔接而存在、由 Task 3 移除）。

### Task 3：服务端自动分配版本与名称唯一门禁

**Files:** `src/dst_manager/application/standards.py`、`src/dst_manager/infrastructure/standards/store.py`、`src/dst_manager/interfaces/message_catalog.py`、新建 `src/dst_manager/domain/standard_identity.py`；`tests/unit/test_standard_store.py`、`tests/integration/test_standard_api.py`、`changelog.md`。

**Interfaces:** `normalize_standard_name(name: str) -> str` 是无文件系统依赖的纯函数；`publish(draft_id)` 在最终门禁和受控锁内分配 `max(official,user)+1`；本机发布与导入共用 `check_published_name(standard_id, name)`。名称冲突码 `STANDARD_NAME_CONFLICT`，身份冲突仍为 `STANDARD_VERSION_EXISTS`，版本耗尽用 `STANDARD_VERSION_LIMIT_REACHED`；三个码随本任务登记进 `message_catalog`，同时移除 Task 2 的过渡码 `STANDARD_VERSION_UNASSIGNED`。

- [x] 写 RED：首版 `1`、次版 `2`，已有官方 `3` 时本机下一版 `4`；同 ID 沿用/更改名称可发布，不同 ID 的规范化同名在官方或用户库中返回 409；草稿同名不占用；最高版为 `2147483647` 时稳定拒绝。并发两发布得到不同版本，注入暂存/移动失败后草稿及资产不丢失。运行 `rtk uv run pytest -q -p no:xdist tests/unit/test_standard_store.py tests/integration/test_standard_api.py` 记录 RED。
- [x] 在仓储集中执行名称规范化、官方/用户枚举、版本分配与按标准库根互斥；锁覆盖读取最高版本到原子发布全程。发布文档在暂存区写入整数版本并完整校验，失败恢复草稿/临时文件，不预留空版本；删除过渡码 `STANDARD_VERSION_UNASSIGNED` 及其用例，把 `STANDARD_NAME_CONFLICT`、`STANDARD_VERSION_EXISTS`、`STANDARD_VERSION_LIMIT_REACHED` 登记进 `message_catalog`。运行上述测试和 Ruff 为 GREEN；记录冲突码和并发验证。

### Task 4：把整数身份传递到创建、绑定与公开契约

**Files:** `src/dst_manager/application/creation.py`、`src/dst_manager/application/creation_drafts.py`、`src/dst_manager/application/creation_assets.py`、`src/dst_manager/application/standards.py`、`src/dst_manager/domain/creation.py`、`src/dst_manager/infrastructure/creation_drafts.py`、`src/dst_manager/infrastructure/creation_xlsx_protocol.py`、`src/dst_manager/application/creation_import_metadata.py`、`src/dst_manager/interfaces/standard_contracts.py`、`src/dst_manager/interfaces/creation_contracts.py`、`src/dst_manager/interfaces/standard_api.py`、`src/dst_manager/interfaces/creation_api.py`、`web/src/api/openapi.json`、`web/src/api/schema.d.ts`；相关创建与标准 API 测试、`changelog.md`。

**Interfaces:** JSON 的 `version`/`standard_version` 为整数；`standard_id@<n>` 是工程绑定字符串。版本路由仅接受规范十进制正整数，保留 PLAN-DM-040 的越界拒绝。创建草稿、XLSX 元数据和预览摘要仍固定精确标准身份。

- [x] 写 RED：`standard_id@1` 可解析并恢复同版快照，`@0`、`@1.0.0`、`@../` 拒绝；创建草稿/预览/执行和 XLSX 元数据传同一整数，版本或标准内容变化使旧预览失效。运行 `rtk uv run pytest -q -p no:xdist tests/unit/test_creation_drafts.py tests/unit/test_creation_xlsx_template.py tests/unit/test_creation_xlsx_import.py tests/integration/test_creation_api.py tests/integration/test_standard_api.py` 记录 RED。
- [x] 调整领域、持久化和 API 类型、快照目录及 Excel 元数据解析，不降低 PLAN-DM-036 的版本固定、资产可用性和 `preview_digest` 门禁。草稿级保存只核对不可变 `standard_id` 与草稿 ID，不再核对尚未分配的版本；移除不再成立的草稿按身份保存入口，保留 PLAN-DM-040 的草稿级保存。上述测试为 GREEN 后运行 `rtk npm --prefix web run generate:api`、`rtk npm --prefix web run check:api`、Ruff；前端消费方阶段性类型红灯记录到 Task 6，不冒称全量构建通过。

### Task 5：实现限时快照预检与凭证确认导入

**Files:** 新建 `src/dst_manager/infrastructure/standards/import_previews.py`、`tests/unit/test_standard_import_previews.py`；修改 `src/dst_manager/application/standards.py`、`src/dst_manager/interfaces/standard_contracts.py`、`src/dst_manager/interfaces/standard_api.py`、`src/dst_manager/infrastructure/standards/store.py`、`src/dst_manager/interfaces/message_catalog.py`、`tests/integration/test_standard_api.py`、`changelog.md`。

**Interfaces:** `POST /api/standards/import-previews {path}` 返回 `{preview_id,expires_at,standard,existing_versions,diagnostics,can_import}`；`POST /api/standards/import {preview_id}` 返回已发布身份；`DELETE /api/standards/import-previews/{preview_id}` 取消。凭证随机、不可猜测，只关联服务端快照。

- [x] 写 RED：预检展示整数身份、官方/用户已有版本与冲突，标准库零新增；损坏包、非法资产、源消失、超限文件有稳定诊断。预检后原文件被替换/删除仍只导入快照字节；伪造、过期、重启失效凭证拒绝；确认前新增身份/名称冲突返回 409；同凭证成功重试返回原成功结果；取消、过期、复制中断或发布故障不留半包。运行 `rtk uv run pytest -q -p no:xdist tests/unit/test_standard_import_previews.py tests/integration/test_standard_api.py` 记录 RED。
- [x] 限制源扩展名和压缩字节数，流式复制到应用数据临时根随机文件，完成后原子定稿，再使用现有安全读取器和 PLAN-DM-040 资产门禁校验。凭证 15 分钟后清理；确认在仓储写入锁下复核名称、身份及包内容，并调用既有暂存发布流程；成功保存短期幂等回执。取消或重启后要求重新预检。
- [x] 移除 HTTP `{path}` 直接导入，避免绕过预检；应用内部路径导入若保留，只允许凭证流程调用。上述测试、Ruff、`rtk npm --prefix web run generate:api` 和 `check:api` 为 GREEN，记录验证。

### Task 6：移除版本输入并按 ID 归集标准库

**Files:** `web/src/components/standards/StandardCreateDialog.vue`、`web/src/components/standards/StandardEditor.vue`、`web/src/components/standards/StandardLibraryPane.vue`、`web/src/components/standards/StandardDetailPane.vue`、`web/src/components/standards/standardLibraryModel.ts`、`web/src/features/standards/draftModel.ts`、`web/src/features/standards/types.ts`、`web/src/features/creation/types.ts`、`web/src/features/creation/store.ts`、`web/src/api/creation.ts`、`web/src/views/StandardsView.vue`、相关中英文文案、Vitest 和标准库/编辑器/创建 E2E、`changelog.md`。

**Interfaces:** 分组键为 `standard_id`；组内按整数降序，显示 `v<n>`、来源及各版本原名称，草稿按稳定 `draft_id` 归组。具体选择仍使用 PLAN-DM-040 的完整身份键；创建/编辑无版本输入，发布成功按服务端返回版本定位。

- [x] 写 RED：`v10` 排在 `v9` 前；同 ID 的官方/用户版本及草稿归一组，不同 ID 的 `v1` 不串位；来源/状态/搜索筛选只留下匹配版本与组，清除后复原；组标题取当前可见最高版名称、仅有草稿时显示 ID，历史改名仍可见；键盘展开/收起和窄视口列表→详情可达。新建/派生草稿无版本字段，创建向导传整数。运行前端单测与相关 Playwright 记录 RED。
- [x] 在纯视图模型实现分组与排序，组件只渲染并发出完整身份。移除 `deriveVersion`、版本输入和前端预分配，保留标准 ID 与草稿 ID 的既有边界；创建消费方与 `v<n>` 展示同步。执行 `rtk npm --prefix web run test:unit`、`check:api`、`check:i18n`、`check:ui`、`build` 为 GREEN；复核 PLAN-DM-040 F05/F09 回归仍通过。

### Task 7：原生选择与唯一导入弹窗的预检/确认状态

**Files:** `src/dst_manager/interfaces/shell.py`、`web/src/api/shell.ts`、`web/src/api/standards.ts`、`web/src/features/standards/store.ts`、`web/src/views/StandardsView.vue`（超限时抽出同层导入组件）、中英文 `common`/`standards` 文案；`tests/unit/test_shell.py`、`web/src/api/shell.test.ts`、`web/src/features/standards/store.test.ts`、`web/tests/e2e/standards-welcome.spec.ts`、`web/tests/e2e/standards-library.spec.ts`、`changelog.md`。

**Interfaces:** 壳固定种类增加 `dststandard -> *.dststandard`。欢迎页与标准库进入同一弹窗；桌面壳用原生选择和只读路径，无壳浏览器才显示明确标注的本机路径开发态回退。状态为未选择、预检中、可确认、受阻、导入中、成功；换文件、取消和凭证过期清除旧预检。

- [x] 写 RED：过滤器不受本地化描述伪造影响，未知 kind 拒绝、取消返回 `null` 且不预检；中文/空格/OneDrive 路径原样传给预检；桥迟到注入后不滞留在无壳模式；空路径禁用，预检中/导入中防重复提交；冲突与失败留在弹窗，保留路径、可重选/重试；成功刷新并展开 ID 组、定位返回版本。运行壳、前端单测和欢迎页/标准库 E2E 记录 RED。
- [x] 接入预检、凭证确认、取消清理，删除前端 `importPackage({path})` 路径。复用 `dialogFocus.ts` 完成初始焦点、Tab/Shift+Tab 圈闭、Escape 与焦点归还；错误区用 `role=alert`，按钮和路径有可访问名称。执行 `rtk uv run pytest -q -p no:xdist tests/unit/test_shell.py`、`rtk npm --prefix web run test:unit`、相关 E2E、`check:i18n`、`check:ui`、`build` 为 GREEN。

### Task 8：端到端联验、真实桌面 G9 与归档

**Files:** `tests/integration/test_standard_api.py`、`tests/integration/test_creation_api.py`、相关标准 E2E、`docs/dst-manager/specs/assets/SPEC-DM-016/README.md`、本计划、相关索引与 `changelog.md`。

- [x] 用临时 v2 包演练“受控草稿资产 → 自动发布 `v1` → 导出 → 原生选择 → 预检 → 在另一数据根确认导入 → 按 ID 定位 `v1` → 再发布 `v2`”。同时覆盖同名不同 ID、重复身份、较早空缺版本、失败回滚。PLAN-DM-040 的受控资产参与闭环；其桌面 G9 未完成时单独记录待验。
- [ ] 在 Windows WebView2 按 SPEC-DM-016 G9 检查过滤器、取消、中文/空格/OneDrive 路径、冲突重试、定位、键盘焦点、900×768 和 200% 系统缩放；浏览器 E2E 不替代真实桌面证据。**未执行**：按用户裁决，Task 1–7 的自动门禁与闭环完成后由用户在有桌面条件时执行；恢复条件 = 装有 WebView2 的 Windows 桌面 + 本机任一 `.dststandard`（可用导出的用户标准包）；执行前计划保持 `active`，不得声明 G9 通过。桌面步骤清单见 `docs/dst-manager/specs/assets/SPEC-DM-016/README.md` §五「G9-2 追加步骤」。
- [x] 执行 `rtk uv run ruff check .`、相关 `rtk uv run pytest -q`、`rtk uv lock --check`、`rtk npm --prefix web run test:unit`、`check:api`、`check:i18n`、`check:ui`、`build` 及相关 Playwright；版本变更波及全量用例时运行完整 pytest 与 Web E2E。记录实际命令、通过数、跳过及偏差，更新规范、G9 证据与索引。仅暂存本任务文件，确认私有样本/路径和构建产物未入提交树。

## 完成标准

- 标准发布版本由服务端分配整数，草稿不可填写/预占；并发、失败重试和 `v1`/`v2` 有证据。新包使用 v2 文档格式和整数 `version`，创建、绑定、XLSX、OpenAPI/TS 一致。
- 标准库按 ID 归集并按整数排序；同身份不覆盖、空缺较早版本可导入；不同 ID 的规范化同名在发布、预检与确认时均被阻止。
- 原 F16 的桌面受控选择、无壳回退、独立预检、限时快照确认、失败恢复、成功定位与弹窗焦点有可复现证据；服务端不接受绕过预检的路径导入。
- PLAN-DM-040 的路径/资产/身份门禁和 UI 修复未回退。自动门禁及真实 Windows WebView2 G9 都有实际结果；环境缺席时不得标记 `completed`。

## 修订记录

- 2026-09-24 首版：整数版本、按 ID 归集与两步导入的完整计划。
- 2026-09-25 审查后修订：裁决 `dependencies[*].min_version` 保留三段字符串并要求拆分两个版本解析器（Task 1/2）；定义 Task 2→3 之间 `publish()` 的过渡态（422 `STANDARD_VERSION_UNASSIGNED`，Task 3 移除）；明确残留 v1 目录“`list()` 跳过、读取 422”处置（契约表、Task 1/2）；名称比较固定 `casefold()`；Task 3 把新错误码登记进 `message_catalog`；SPEC-DM-019 记录预检信任模型与缓解。

## 实际验证（Task 1–8，2026-09-25）

| 项 | 命令 | 结果 |
| --- | --- | --- |
| Ruff | `uv run ruff check .` | All checks passed |
| 全量 Python | `uv run pytest -q`（xdist 并行） | **2186 项 / 0 failed / 0 error / 74 skipped** |
| 依赖锁 | `uv lock --check` | 通过 |
| 标准库与包（点名） | `tests/unit/test_standard_store.py`、`test_standard_package.py`、`test_drawing_standards.py`、`test_standard_import_previews.py`、`test_message_catalog.py` | 全绿（含新增的版本分配、名称归一、快照与凭证用例） |
| 标准与创建 API（点名） | `tests/integration/test_standard_api.py`、`test_creation_api.py`、`test_standard_dst_import.py`、`tests/unit/test_creation_drafts.py`、`test_creation_xlsx_*` | 全绿（含新增的端到端闭环与发布失败回滚） |
| 前端单测 | `npm --prefix web run test:unit` | **336 例** 全绿（含导入弹窗状态机 10 例、`selectStandardPackagePath` 4 例、分组模型 16 例） |
| 前端门禁 | `npm --prefix web run check:api` / `check:i18n` / `check:ui` | 通过（i18n 1619 键 / 11 域） |
| 生产构建 | `npm --prefix web run build`（含 `vue-tsc -b`） | 通过 |
| Playwright 全量 | `npm --prefix web run test:e2e` | **682 passed**（0 failed；`main.spec.ts` 的性能预算用例曾标 1 次 flaky，重跑通过） |
| 端到端闭环 | `test_standard_package_full_loop_from_draft_asset_to_next_version` | 通过：受控草稿资产 → 自动 `v1` → 导出 → 预检 → 另一数据根确认导入 → 按 ID 定位 → 较早空缺版本 2/3 → 同名不同 ID 阻断 → 再发布 `v4` |
| 真实桌面 G9 | 见 SPEC-DM-016 证据目录 §五 | **未执行**（用户裁决留待有桌面条件时执行）；计划保持 `active` |

与 PLAN-DM-040 的衔接：其共享的后端路径/资产门禁与标准库 UI 修复未回退
（`test_standard_store.py`、`test_standard_api.py`、`test_standard_assets.py`、标准 E2E 全绿）；
PLAN-DM-040 的真实桌面 G9 仍未执行，与本计划的 G9 一并待验。

## 修订记录（续）

- 2026-09-25 实施完成 Task 1–7 与 Task 8 的自动门禁部分：SPEC-DM-019 转为 `accepted`；
  真实桌面 G9 未执行，计划保持 `active`，Task 8 的 G9 步骤保持未勾选并写明恢复条件。
