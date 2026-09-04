# 变更记录

## 2026-09-04（v0.3.3 标签化外壳 Task 3：App.vue 四个业务状态域拆分组合式函数）

- Task 3 步骤 1/4：拆分任务监控域为 useJobMonitor 组合式函数（新增 `web/src/composables/useJobMonitor.ts`，行为零变化）。`job`/`connectionMode` 状态、`jobMonitorGeneration` 代次、`activeJobEvents`/`pollTimer` 与 `invalidateJobMonitor`/`terminal`/`monitorMatches`/`watchJob`/`schedulePoll`/`pollJob`/`retryJob` 函数体原样迁入（对 `workspace`/`isWorkspaceLoading`/`error` 的引用改经 deps 注入；`watchJob`/`pollJob` 成功路径的 `await discardDraft();await refreshWorkspace(...)` 改经 `onJobSucceeded` 注入，App.vue 传入 `async workspaceId=>{await discardDraft();await refreshWorkspace(workspaceId)}`）。对外返回 `job`/`connectionMode`/`watchJob`/`retryJob`/`invalidateJobMonitor`/`terminal`/`monitorMatches` 契约供 Task 4-7 复用，并额外暴露 `isCurrentJobGeneration` 供 App.vue 的 `execute` 及后续 CSV/修复/恢复域做 `jobMonitorGeneration` 纯代次校验（与原比较行为等价）。`App.vue` 改为解构调用、删除对应状态与函数；确认文案、错误码分支、代次保护逐字保留。Playwright e2e **42/42 通过**、`npm run build`（check:api + vue-tsc + vite）零类型错误。
- Task 3 步骤 2/4：拆分自定义属性 CSV 导入域为 useCsvImport 组合式函数（新增 `web/src/composables/useCsvImport.ts`，行为零变化）。`csvText`/`csvPreview`/`csvPreviewContext` 状态、`csvGeneration` 代次与 `readCsvFile`/`previewCsv`/`importCsv`/`invalidateCsvPreview` 函数体原样迁入（`workspace`/`isWorkspaceLoading`/`error` 引用改经 deps 注入，`job.value=result` 改经 `setJob` 注入，`watchJob`/`invalidateJobMonitor`/`isCurrentJobGeneration`/`refreshWorkspace`/`confirmAction` 由 App.vue 传入）；导入确认文案与危险等级（低风险 `danger:false`、confirmText「确认导入」）逐字保留。`App.vue` 删除对应状态与函数并解构调用；Playwright e2e **42/42 通过**、`npm run build`（check:api + vue-tsc + vite）零类型错误。
- Task 3 步骤 3/4：拆分内存修复域为 useRepair 组合式函数（新增 `web/src/composables/useRepair.ts`，行为零变化）。`repairPreview`/`repairContext`/`isRepairPreviewing`/`isRepairExecuting` 状态、`repairGeneration` 代次、`dstValidation`/`repairWritesDisabled` 两计算属性与 `previewRepair`/`executeRepair` 函数体原样迁入（`workspace`/`isWorkspaceLoading`/`error` 与 `workspaceLoadGeneration` 改经 deps 注入，`job.value=result` 改经 `setJob`，`invalidateJobMonitor`/`isCurrentJobGeneration`/`refreshWorkspace`/`confirmAction` 由 App.vue 传入；`isRestoreExecuting` 按单一事实来源由 App.vue 创建后作为 deps 传入，本域函数体原不使用该门禁故未新增判断）；`dstValidation` 一并返回以支撑模板渲染。`App.vue` 删除对应状态/计算属性/函数并解构调用，`workspaceLoadGeneration` 由局部 `let` 改为跨域共享 ref（打开/关闭/刷新/修订均改 `.value`，行为等价）；修复确认文案与不可逆危险等级（`danger:true` + `requireCheckbox`）逐字保留。Playwright e2e **42/42 通过**、`npm run build`（check:api + vue-tsc + vite）零类型错误。

## 2026-09-04（v0.3.3 标签化外壳 Task 2：发布/删除/恢复等确认改为应用内可访问模态）

- 把 `web/src/App.vue` 全部 8 处原生 `confirm()` 迁移为应用内可访问确认模态（[PLAN-DM-013](.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md) Task 2，对应 [SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.2、§6.9）：新增 `web/src/components/ui/ConfirmModal.vue`（`role="dialog"`/`aria-modal`/`aria-label`、焦点困绕、Tab/Escape 键盘模型、`watch(open)` 归还焦点到触发元素，全部样式引用 Task 1 设计令牌；遮罩 rgba 常量除外）与 `web/src/composables/useConfirm.ts`（`useConfirm()` 返回 `{ state, confirmAction(options): Promise<boolean>, resolve(value) }`，供 Task 5"确认写入"按钮复用）。8 处迁移均保留既有 `confirm()` 文案原文，不可逆破坏类（关闭工作区、删除整个子集、执行发布、恢复为新修订、执行修复）按统一门禁走 `danger:true + requireCheckbox:true + reversibility:"不可逆"` 并显式勾选"我已了解本次操作不可逆…"后确认按钮才可用；低风险动作（单张图纸删除、冲突后重新加载、CSV 属性定义导入）为 `danger:false` 且不勾选（导入 confirmText 用"确认导入"）；`closeWorkspace`/`queueDelete`/`queueDeleteSubset` 改为 `async`，模板 `@click` 兼容 Promise。e2e 全量更新：23 处 `page.once("dialog",…)` 原生 dialog 处理器改为模态交互（`getByRole("dialog")` 内勾选 + 点确认/取消），并新增「发布确认模态必须显式勾选后才可提交」用例（Task 5 前暂以既有发布入口"确认并执行"触发同一模态，用例已注释 Task 5 将改触发方式）。Playwright e2e **41/41 通过**（40 既有 + 1 新增）、`npm run build`（check:api + vue-tsc + vite）零类型错误。
- 评审修复（Important）：`useConfirm()` 的共享 reactive 状态跨次泄漏——`confirmAction` 内 `Object.assign(state, options, {open:true})` 只覆盖传入键，先打开 `requireCheckbox`/`impactLines` 模态后取消，再触发低风险模态会残留复选框/「不可逆」徽标/上次受影响文件清单。修复：`confirmAction` 打开前把全部可选键复位为干净初值（`impactLines`/`cancelText`/`reversibility` 置 `undefined`、`danger`/`requireCheckbox` 置 `false`），语义为"每次打开都是干净状态"；顺手把 `reversibility` 类型收紧回 `"可撤销"|"不可逆"`（useConfirm.ts 与 ConfirmModal.vue 两处，原为 Minor）。e2e 新增回归用例「取消高门槛模态后低风险模态不残留勾选与不可逆徽标」（先取消发布模态再触发单张图纸删除，断言无复选框/徽标/受影响清单且确认按钮不被门禁；验证先红后绿）。Playwright e2e **42/42 通过**（41 既有 + 1 回归新增）、`npm run build` 零类型错误。

## 2026-09-04（v0.3.3 标签化外壳 Task 1：设计令牌与浅深双主题）

- 落地界面设计令牌与浅深双主题切换（[PLAN-DM-013](.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md) Task 1，对应 [SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §5.1、§4.1 顶栏主题切换）：`web/src/style.css` 文件头部新增 `:root` 浅色与 `html[data-theme="dark"]` 深色两套设计令牌（背景/文字/边框/强调/语义色、圆角、阴影、间距共 8 组），浅色默认；新增 `web/src/composables/useTheme.ts`（`useTheme(): { theme, toggleTheme }`，持久化键 `localStorage["dst-manager-theme"]`，watch immediate 写 `document.documentElement.dataset.theme`）；`web/src/App.vue` header 内临时挂载主题切换按钮（`aria-label="切换主题"`，Task 4 迁入 TopBar）。e2e 新增「主题切换写 html data-theme 并持久化」用例（先红后绿；用例中 `addInitScript` 播种初始主题改为"仅当未持久化时写入"，规避 Playwright 每次导航重跑 init script 会把 reload 后已持久化的 dark 冲回 light 的语义陷阱）。全量 Playwright e2e **40/40 通过**（39 既有 + 1 新增）、`npm run build`（check:api + vue-tsc + vite）零类型错误。

## 2026-09-03（v0.3.2 实测修复：文件名后缀区间压缩与项目前缀对齐）

- 依据 `sample/project3 - copy2` 图纸集实测反馈修订派生 DWG 文件名两条规则（[SPEC-DM-008](docs/dst-manager/specs/SPEC-DM-008-v032-naming-and-template-flows.md) §3.2 同步修订并补修订记录）：① 后缀压缩改为**区间形式**——文件名后缀只保留首末两张图纸的序号，六张图纸为 `RQ-011-016 … (一)-(六).dwg` 而非 `(一)-(二)-(三)-(四)-(五)-(六).dwg`（`domain/editing.py` 的 `_compressed_group_title` 改为 `首后缀)-(末后缀` 拼接；两张时与原输出一致，既有用例不变）；② **项目前缀对齐**——新增 `_project_dwgs_prefix(document)` 从图纸集既有 DWG 登记名提取项目级前缀（如 `RQ-001-002 大运北站图纸目录 (一)-(二).dwg` → `RQ-`），`_target_file_name` 增加回退参数：来源文件名自带前缀优先，模板来源（新建子集的布局模板文件无前缀）时回退项目前缀，新子集派生 `RQ-003-004 主要设备及材料表 (一)-(二).dwg` 而非 `003-004 …`。`tests/unit/test_core.py` 新增 6 张区间压缩与新建子集前缀继承两用例（先确认失败原因正确再实现）；全量 `uv run pytest` **619 项，547 passed / 72 skipped / 0 failed**、`ruff check .` 无违规。

## 2026-09-03（v0.3.2 补遗：新建子集布局模板选择与添加图纸对齐）

- 新建子集表单的"布局模板文件/布局模板名称"从手动输入对齐为批量新增图纸同款交互——按钮打开文件选择对话框（`.dwg/.dwt` 过滤器）→ 选取后经 `/api/layout-names` 读取布局列表（后端缓存优先）→ 从下拉列表选择布局名称（读取失败回退手动输入，与批量新增图纸一致）。`web/src/App.vue`：`loadLayoutOptions(path, target)` 泛化为按表单注入目标状态组（`LayoutPickerTarget`），新增子集独立的 `subsetLayoutOptions/Loading/Error/Manual` 四件套避免与批量新增图纸共享串扰，新增 `selectSubsetTemplateFile`（复用 `TEMPLATE_FILE_FILTERS`、`DWG_DWT_EXT` 校验与 `selectTemplateFile` 同构流程）；M6 重置同步清空子集布局选项状态。E2E 同步：新建子集入队用例改为按钮选择 + 下拉选布局（命令断言不变），关闭重置用例改为断言子集布局路径与下拉清空。`npm run build` 零类型错误、Playwright e2e **39/39 通过**。

## 2026-09-03（v0.3.2 评审修复：旧草稿回放后向兼容）

- 修复最终整分支评审 Important #1（旧草稿回放后向兼容缺口）：v0.3.1 前保存、含 `insert_subset` 命令的旧草稿在升级后首次加载被草稿形状校验器以缺 `base_template_file` 判为损坏并隔离（`os.replace` 至 `.corrupt-*.json`、UI 标记 corrupted、draft 置 None），用户待办的新建子集命令从活跃草稿丢失，破坏"草稿是待发布工作的确定性载体"的既有承诺。修复：`src/dst_manager/infrastructure/drafts.py` 的 `_COMMAND_KEYS["insert_subset"]` 将 `base_template_file` 移入可选集、`_validate_command` 改为"命令含该字段才校验非空绝对路径"——旧草稿恢复/回放可正常加载（不再 422/静默隔离），缺基础模板的预览/执行仍由既有下游 `INSERT_SUBSET_BASE_TEMPLATE_INVALID` 明确拒绝（草稿保留、用户补选后重预览）；Task 2/3 已落地的契约必填与扩展名白名单语义不变，命令含该字段但非法（相对路径）仍按损坏草稿隔离。`tests/unit/test_drafts.py` 新增"旧草稿 insert_subset 缺 base_template_file 可加载"单测，并将既有"缺字段/非法路径"参数化用例拆分为"非法路径仍隔离"专项（缺字段移入兼容用例）。全量 `uv run pytest tests/unit -q` **479 passed / 4 skipped**（0 failures / 0 errors，退出码 0）、`uv run ruff check .` 无违规。

## 2026-09-03（v0.3.2 基线：SPEC-DM-008 / PLAN-DM-012 与版本重基线）

- PLAN-DM-012 Task 5（v0.3.2 收尾：契约再生成等幂确认与全量验证）：`uv run python scripts/export_openapi.py` + `npm run generate:api` 再生成后 `web/src/api/openapi.json`/`schema.d.ts` 无任何 git 变更（等幂，commit cf18c42 产物与本次一致；含 `InsertSubsetCommand.base_template_file` 必填与放宽后的 `LayoutSource`），两文件保持 LF（0 CRLF，`git diff --check` 通过）。全量验证：`uv run ruff check .`（All checks passed）、`uv run pytest -q` 全量 **545 passed / 72 skipped**（617 项，0 failures / 0 errors，退出码 0；其中 68 项真实 AutoCAD 系统测试因未显式启用而跳过）、`uv lock --check` 通过（53 包解析一致）、`npm run build` 成功（check:api + vue-tsc + vite 零类型错误）、Playwright e2e **39/39 通过**（54.3s）。真实 CAD 系统测试（本机具备 AutoCAD 2016 R20.1/2020 R23.1 Core Console 与匹配插件、私有样本）：`DST_MANAGER_RUN_AUTOCAD=1` 下 24 项真实 CAD 系统测试全数通过（0 失败 0 跳过；两批 `-k` 选择、junittest 计数 12+12＝场景相关 12 项＋既有整批回滚机制回归 12 项）。场景相关 12 项＝新建子集（基础模板文件 `.dwg`/`.dwt` 各一 + 布局模板，4 项；`source_snapshot` 确认为基础模板文件、3 布局独立 DWG 创建成功）＋"已有布局"批量新增整批发布（2 项；来源解析为目标子集首图登记的 DWG 与布局、rebuild 后 3 图纸 Handle 齐全）＋"已有布局"批量新增回滚（2 项；注入第 2 个 CAD 工作单元失败 → 整批 FAILED、正式文件哈希不变、无 manifest）＋批量重建顺序（2 项）＋缺失模板布局确认后失败不回滚（2 项）；既有整批回滚机制回归 12 项＝混合 rename+rebuild+delete 失败 8＋注入 DWG 失败 2＋CAD 成功后 DOM 失败 2，均验证失败不回滚、正式文件字节不变。顺带修复 Task 5 真机验证发现的潜在缺陷：`DstManagerService._issue`（service.py:265）实例方法签名缺 `self`，`open_workspace` 的 `UNREFERENCED_DWG` 诊断分支（工程根存在未被 DST 引用的 `.dwg`，如置于根目录的基础模板文件）调用即抛 `TypeError`；补齐 `self` 并新增单测 `test_open_workspace_reports_unreferenced_dwg_without_crashing` 固化。同步更新系统测试夹具/用例：`test_insert_subset_creates_independent_dwg_with_batch_layouts` 补 Task 3 遗漏的必填 `base_template_file` 并按 `.dwg/.dwt` 参数化；新增 `test_existing_snapshot_batch_insert_publishes_whole_batch` 与 `test_existing_snapshot_batch_failure_never_publishes_partial`（SPEC-DM-008 §10 真实 CAD 验收）。[PLAN-DM-012](.planning/plans/dst-manager/PLAN-DM-012-v032-naming-and-template-flows.md) 标记 `completed`（「实际验证」小节记入全部真实结果），[SPEC-DM-008](docs/dst-manager/specs/SPEC-DM-008-v032-naming-and-template-flows.md) 状态 `review` → `accepted`（仅改状态字段），ROADMAP-DM-001 v0.3.2 行更新为已完成。
- PLAN-DM-012 Task 4（SPEC-DM-008 F-02/F-03/F-04 前端表单与文案，顺带关闭 M6/M4）：`web/src/App.vue` 批量新增图纸"模板来源"选"已有布局"（`existing_snapshot`）时用 `v-if` 隐藏"布局模板文件/布局模板名称"输入行并显示只读说明"来源为目标子集 DWG 的第一个非 Model 布局"，`queueInsertSheet` 该分支不再要求来源文件/布局非空、提交 `source:{type:"existing_snapshot",file:"",layout:""}`（后端预览期解析为目标子集首图登记）；新建子集表单新增必填"基础模板文件"选择器（`.dwg/.dwt` 过滤器，未选不可提交，新增 `selectBaseTemplateFile`），`queueInsertSubset` 校验非空后随命令提交 `base_template_file`；文案按 §5 统一改名五处（批量新增：来源类型→模板来源、来源文件→布局模板文件、来源布局→布局模板名称；新建子集：模板文件→布局模板文件、模板布局→布局模板名称）；顺带关闭 M6（`closeWorkspace` 重置批量新增/新建子集表单的模板文件、模板布局、布局选项与 `baseTemplateFile` 状态）与 M4（`loadLayoutOptions` 的 `cad_version` 改用 `cadVersion.value` 去除硬编码 `"2020"`）。契约经 `npm run generate:api` 再生成（`InsertSubsetCommand.base_template_file` 必填、`LayoutSource` 放宽，产物保持 LF，`git diff --check` 通过）；`contracts.ts` 的 `createCommand.insertSubset` 经生成类型自动强制必填 `base_template_file`；集成面最小修复 `infrastructure/drafts.py` 草稿形状校验器——`_COMMAND_KEYS["insert_subset"]` 纳入 `base_template_file`、`_validate_source` 对 `existing_snapshot` 允许空 file/layout（`template_layout` 仍必填）、`_validate_command` 校验 `base_template_file` 非空绝对路径，配套 `tests/unit/test_drafts.py` 新增 6 项（避免前端入队含新字段命令后草稿保存被误判损坏）；`npm run build` 零类型错误、Playwright e2e **39/39 通过**（更新 5 处引用旧文案/结构的用例 + 新增已有布局来源空来源提交、关闭重置模板状态与布局读取跟随 CAD 版本 2 项）、`uv run pytest tests/unit -q` 全绿（474 passed / 4 skipped）、`ruff check .` 无违规。
- PLAN-DM-012 Task 3（SPEC-DM-008 F-04）：新建子集新增必填"基础模板文件"（图纸模板），实现 DWG 基底与布局来源分离——`interfaces/contracts.py` 的 `InsertSubsetCommand` 新增必填字段 `base_template_file`（绝对路径，`field_validator` 复用 `validate_absolute_source_file` 并追加扩展名白名单 `.dwg/.dwt`、大小写不敏感，非法报 `INSERT_SUBSET_BASE_TEMPLATE_INVALID`）；`domain/editing.py` 的 `insert_subset` 分支经新增模块级私有 `_base_template_file` 读取并校验（缺失或扩展名非法抛 `EditingError("INSERT_SUBSET_BASE_TEMPLATE_INVALID")`），结果存入 `DerivedDocument.subset_base_templates: dict[str, str]`（默认空 dict，`_serialize_derived_document` 与 `derived_document_from_plan` 同步序列化/恢复）；`domain/planning.py` 的 `source_snapshot` 改为 `source_target or subset_base_templates.get(subset_id) or layouts[0]["source_file"]`——create 组取基础模板文件作新子集 DWG 基底，rebuild 组仍命中 `source_target` 行为不变，布局仍从布局模板文件的指定布局复制（`source` 语义收窄为布局模板来源，不动 Task 2 的 `existing_snapshot` 放宽）。新增契约测试 `tests/unit/test_contracts.py`（9 项）、域派生/规划测试 `tests/unit/test_core.py`（4 项），并同步补齐既有"新建子集"用例命令夹具的 `base_template_file`（`test_core.py`/`test_v021_editing.py`/`test_v021_domain_dom_hardening.py`/`test_api.py`）；全量 `uv run pytest` **538 passed / 66 skipped**、`ruff check .` 无违规。
- PLAN-DM-012 Task 2（SPEC-DM-008 F-02）：批量新增图纸"已有布局"来源强制解析为目标子集 DWG 与其第一个非 Model 布局——`interfaces/contracts.py` 的 `LayoutSource` 改 `model_validator(mode="after")` 条件必填：`existing_snapshot` 允许空 `file`/`layout`（字段类型 `str = ""` 默认，空值时跳过绝对路径/布局名校验），`template_layout` 两字段仍必填、缺失报 `LAYOUT_SOURCE_INVALID`（沿用既有错误码与文案）；`domain/editing.py` 的 `_layout_source` 对 `existing_snapshot` 放宽为空值直通、`insert_sheet` 分支在 `source["type"] == "existing_snapshot"` 且 file/layout 任一为空时从原始 `document.subsets` 中目标子集首张图纸解析 file（`resolved_path or file_name`）与 layout（`layout_name`）后回写进 source dict 再建 `LayoutReference`（解析先于插入位置计算，`LAYOUT_SOURCE_INVALID` 优先于 `SHEET_POSITION_INVALID`），新增模块级私有 `_resolve_existing_snapshot`（目标子集缺图或首图登记为空 → `EditingError("LAYOUT_SOURCE_INVALID", "目标子集缺少可用的已有布局来源")`）；解析发生在 `layout_sources` 写入前，planning/baseline/cad_job 读到的三字段齐全，`_collect_structural_source_baselines` 对解析后 DWG 的越界/扩展名/存在性防御性校验不变。新增契约测试 `tests/unit/test_contracts.py`（6 项）、域解析测试 `tests/unit/test_v021_editing.py`（4 项）、应用层预览回归 `tests/unit/test_core.py`（1 项），全量 `uv run pytest` 525 passed / 66 skipped、`ruff check .` 无违规。
- PLAN-DM-012 Task 1（SPEC-DM-008 F-01）：序号后缀压缩拼接进入 DWG 文件名——`editing.py` 新增模块级私有 `_compressed_group_title(base_title, sheet_titles)`，把组内多张带后缀图纸标题压缩为单个区间后缀标题（如 `图纸目录 (一)`/`图纸目录 (二)` → `图纸目录 (一)-(二)`，`RQ-01-02 图纸目录 (一)-(二).dwg`）；任一张标题结构不符合 `基础标题 (后缀)` 时防御性回退为基础标题，单张无后缀行为与现状一致。`derive_document_structure` 中 `_target_file_name` 的标题实参改为 `_compressed_group_title(title, titles_for_subset)`，规划展示名 `{number_range} {title}` 保持基础标题不变。`tests/unit/test_core.py` 新增三个派生文件名用例（中文/阿拉伯数字后缀压缩与单张回退）。
- 立项 v0.3.2「命名与模板流程需求变更」：[SPEC-DM-008](docs/dst-manager/specs/SPEC-DM-008-v032-naming-and-template-flows.md)（review）与 [PLAN-DM-012](.planning/plans/dst-manager/PLAN-DM-012-v032-naming-and-template-flows.md)（active）。四项需求：① 序号后缀压缩拼接进入 DWG 文件名；② 批量新增图纸"已有布局"来源强制解析为目标子集 DWG 与第一个非 Model 布局（只读 DST，不调 CAD 脚本，执行期失败整批回滚）；③ 批量新增图纸/新建子集表单文案统一；④ 新建子集必填"基础模板文件"（图纸模板），DWG 基底与布局来源分离。经评审并入两项既有事项：`service.py` 全量拆分（先辅助簇后功能域，置于功能变更之前，行为零变化）与遗留项 M6/M4。
- 版本重基线：原 v0.3.2（SPEC-DM-006 桌面界面重构，PLAN-DM-010 编号含义不变）延后为 **v0.3.3**，v0.3.1 其余遗留项（M1-M5、M7、T 系列）随 v0.3.3；同步更新 [SPEC-DM-007](docs/dst-manager/specs/SPEC-DM-007-v031-shell-and-usability.md)、[ROADMAP-DM-001](.planning/roadmaps/dst-manager.md)、plans/README、[DMv031-deferred-findings](.planning/memos/dst-manager/DMv031-deferred-findings.md)（保留原记录并加重基线注）。
- PLAN-DM-012 Task 0（SPEC-DM-008 F-05）：`application/service.py` 全量拆分（1969 行 → 269 行），行为零变化。先拆无状态辅助簇到 `summaries.py`（`build_semantic_diff`/`summarize_*`/`operation_digest`/`parallel_makespan`/`attach_expected_file_hashes`），再按功能域拆分 mixin 并组合进 `DstManagerService`：`drafts.py`（草稿）、`property_import.py`（自定义属性 CSV 导入导出）、`editing.py`（受控编辑预览/执行与布局来源基准、CAD 估算）、`revisions.py`（修订恢复）、`xml_io.py`（XML 导入导出）、`repair.py`（修复）、`recovery.py`（发布事务/启动恢复共享辅助）；`ApplicationError` 独立为 `errors.py` 并以 service 模块再导出保持既有导入兼容。共享小核心（workspace 门禁 `_check_revision`/`_gate_writable`、修订检查、事务辅助、新增基准捕获门禁 `_capture_baseline`）保留在编排入口与共享模块，公共方法签名、错误码与序列化契约不变；等价性验证 514 passed / 66 skipped 与拆分前基线一致，`ruff check .` 无违规。

## 2026-09-03（清理：移除孤儿模板检查 API `/api/templates/inspect`）

- 删除 `inspect_template` 及其 `/api/templates/inspect` 端点：该接口（v0.2 模板布局检查，返回布局名+Handle）在 PLAN-DM-008 将 CAD 校验延期到执行期后已无任何调用方（预览不再调 CAD，前端只用 v0.3.1 的 `/api/layout-names`），与 `get_layout_names` 构成同功能两套 accoreconsole 只读包装且错误处理不一致（占用/超时时裸抛 500，无友好错误码）。同步删除 `TemplateRequest`、`TemplateInspectResponse`、`TemplateLayoutResponse` 及 `service.py` 中 `parse_handles` 导入；`render_handles()` 按 SPEC-DM-002 保留（真实 CAD 系统测试的诊断工具）。"预览不得调用 CAD"守卫测试改为 mock `get_layout_names`；`ARCH-DM-001` 端点表以 `/api/layout-names` 替换该行；`web/src/api` 契约经 `npm run generate:api` 重新生成。

## 2026-09-03（v0.3.1 修复：壳桥就绪响应式与拖拽放行、模板过滤器格式、布局读取误报、CAD 插件相对路径；搜索工具约束）

- 修复"布局枚举未产出结果"：`.env` 中的相对插件路径（`./plugins/...`）在 Python 侧 `is_file` 检查（相对项目根）能通过，但 accoreconsole 子进程内 `NETLOAD` 按自身工作目录解析而加载失败（"无法加载程序集"→`DstGetLayoutNames` 成未知命令），退出码仍为 0、无 sidecar。`config.py` 新增 `validate_cad_paths`：四个 CAD 路径字段在 Settings 源头统一 `resolve()` 为绝对路径（doctor/脚本渲染/NETLOAD 全链路一致）。`test_config.py` 新增相对路径规范化与 None 不变两项（511 passed / 66 skipped）；真机验证 `Settings()`（读 .env 相对路径）经 `get_layout_names` 对 `sample/template/市政项目模板-通用.dwg` 成功枚举 `['A1','A2','A3','A3NS']`。

- 修复新增图纸"读取布局失败：DWG 可能被 AutoCAD 占用"误报：根因为本机 `.env` 缺 `DST_MANAGER_AUTOCAD_*_PLUGIN` 两行（`CadCapability.available` 要求 console 与 plugin 同时存在），`CoreConsoleExecutor` 抛出的 `CAD_CAPABILITY_UNAVAILABLE` 被 `get_layout_names` 一律包装成"文件被占用"。两处修复：① `service.py` 在调用 Core Console 前置能力检查，未配置时抛 `CAD_CAPABILITY_UNAVAILABLE`(503) 并给出可操作提示（对齐 `inspect_template` 先例，履行 SPEC-DM-007"关闭占用提示"要求）；② `.env` 补齐两个插件路径（DLL 位于 `plugins/autocad2016|2020/`），`dst-manager doctor` 双版本 `available: true`。`test_layout_names.py` 新增未配置分流用例并让 mock executor 用例显式传可用路径（不再依赖宿主机 `.env`），全量 pytest **509 passed / 66 skipped**；`DST_MANAGER_RUN_AUTOCAD=1` 下真实 AutoCAD 2016/2020 布局枚举系统测试通过。

- 修复新增图纸「选择模板文件」报错：`TEMPLATE_FILE_FILTERS` 描述 "DWG/DWT 文件" 含 `/`，不满足 pywebview `parse_file_type` 校验的 `[\w ]+`（描述仅允许字母/数字/下划线/空格），真实壳在对话框弹出前抛 ValueError；描述改为 "DWG DWT 文件"，`shell.ts` 注释补充格式约束，`tests/unit/test_shell.py` 新增契约测试直接以 pywebview 校验 `shell.ts` 全部过滤器字符串（假桥 e2e 不经过该校验），15 passed；`web/dist` 已重建。

- `AGENTS.md` 新增「网络搜索工具」约束：网页搜索/调研必须使用已注册的 `tavily-cli` 技能（`tvly search`、`tvly extract` 等），不得使用内置原生搜索工具；搜索失败时先排查 `tvly` 安装与认证状态，仍失败则向用户说明并等待指示。

## 2026-09-03（v0.3.1 收尾补丁：壳托管 CAD Worker 与代码组织契约）

- 桌面壳补齐 CAD Worker 子进程托管（修复壳模式下发布/布局重建等队列型 CAD 任务无人认领的缺口）：`run_desktop` 在窗口创建前经 `_spawn_worker` 拉起 `sys.executable -m dst_manager.interfaces.cli worker`（`cwd` 与 `--project-root` 同取当前工作目录，与壳内 API 同库同队列；`PYTHONUTF8=1` 继承），`_report_early_exit` 后台线程观察 2 秒、立即退出（配置错误等）时向 stderr 输出可见警告，窗口关闭时 `_shutdown_worker` terminate→wait(5)→升级 kill 回收（与 start.ps1 Stop 强杀语义一致，Worker 中断的任务由既有启动恢复闭环）；`tests/unit/test_shell.py` 新增 6 项（13 passed），真实壳冒烟验证 Worker 父子链拉起与整树回收（taskkill 后 0 残留）。注意：强杀壳进程（taskkill /T /F）走 OS 级树杀，正常关窗路径的 terminate 回收逻辑由单测覆盖；孤儿 Worker 仍可被 start.ps1 -Action Stop 按既有命令行匹配清理。
- `AGENTS.md` 新增「代码组织契约（容量与拆分）」：单文件约 500 行/单类约 15 个公共方法软上限、编排入口类只留跨域公共编排与共享门禁、功能域与纯辅助拆同层独立模块、新功能优先新建模块组合、拆分保持公共接口与错误码不变渐进进行。`application/service.py`（1984 行）拆分作为 v0.3.2 事项执行（先拆 ~600 行纯辅助簇，再按功能域拆服务），依据记录见 [DMv031-deferred-findings](.planning/memos/dst-manager/DMv031-deferred-findings.md)。

## 2026-09-03（v0.3.1 交付收尾与全量验证）

- 完成 [PLAN-DM-011](.planning/plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md)（状态 `completed`）v0.3.1 交付收尾与全量验证：`uv sync --dev`、`uv run ruff check .`（All checks passed）、`uv lock --check` 通过；`uv run pytest -q` 全量 566 项 **500 passed / 66 skipped**（其中 62 项真实 AutoCAD 测试因未显式启用而跳过），退出码 0；设置 `DST_MANAGER_RUN_AUTOCAD=1` 后全量 pytest **562 passed / 4 skipped**（0 failures、0 errors，退出码 0），62 项真实 AutoCAD 2016/2020 系统测试全数通过（含 Task 2 新增的 `DstGetLayoutNames` 只读布局枚举命令双版本用例：sidecar 产出 `{"version":1,"layouts":["0000 封面"]}` 且原 DWG 时间戳不变）；`npm ci`、`npm run build`（vue-tsc + vite 零类型错误）、Playwright e2e **35/35 通过**；`scripts/build_plugins.ps1` 2016/2020 双版本构建成功（0 error，2 个警告为并发真实 CAD 运行时 DLL 被占用触发的 MSBuild 重试，均自动重试成功）。
- 桌面壳启动冒烟（v0.3.1 唯一交付入口 `uv run dst-manager desktop`）：后台启动后 uvicorn 在 `127.0.0.1` 临时端口（本次 2036）承载 `create_app()`，Alembic 迁移（含 0004 布局缓存表）执行完成，`GET /api/health` 返回 `{"status":"ok",...}`，WebView2 窗口创建（标题 `DST Manager`、句柄有效），强制终止后进程树退出干净、日志无报错。依赖活跃桌面交互的文件对话框/OS 级拖拽/关闭确认等走查项无法在本会话自动完成，列为遗留人工验收项（清单见 PLAN-DM-011「实际验证」小节）。
- 本迭代（v0.3.1，SPEC-DM-007）实际交付汇总：布局名全局缓存（SQLite 迁移 `0004_dm007_layout_name_cache` + `LayoutNameCacheRow`）；Worker 插件只读布局枚举命令 `DstGetLayoutNames`（不修改图纸、不 QSAVE）与 SCR/sidecar 渲染解析；`POST /api/layout-names` 端点（SHA-256 缓存命中直返、未命中在临时副本上 accoreconsole 枚举、`LAYOUT_READ_FAILED` 502）；pywebview 桌面壳 `src/dst_manager/interfaces/shell.py`（`uv run dst-manager desktop` 唯一入口）；前端两态状态机（DST 文件选择/关闭确认/草稿恢复提示/保存状态可见性/来源文件选择+布局下拉）；拖拽路径原生桥 `ShellBridge.on_files_dropped`（pywebview ≥5 WebView2 原生 `pywebviewFullPath`，不做 WinForms IDropTarget 降级）。

## 2026-09-03（v0.3.1 重基线与 SPEC-DM-007）

- 拖拽文件路径 spike 结论与落地（PLAN-DM-011 Task 8）：验证 **pywebview ≥5 EdgeChromium/WebView2 原生暴露拖拽文件绝对路径**（`webview.dom` drop → `CoreWebView2File` → `pywebviewFullPath`），不采用 WinForms `IDropTarget` 降级；落地 `ShellBridge.on_files_dropped(callback_id)`（document 级 drop 监听 + `prevent_default` 拦截导航，命中后 `evaluate_js` 调前端全局回调）并顺手把 `settings` 转发给 `create_app`；前端 `selectAndOpenDst` 抽出 `acceptDstPath(path)`（含 `.dst` 校验与 `openByPath`，已打开工作区时拒绝）供拖拽复用，`onMounted` 注册 `window.__dstManagerAcceptDst` 接桥，未打开态提示"或将 .dst 文件拖入窗口"；`test_shell.py` 新增 4 项（合计 7 passed）、`ruff check .` 与 `npm run build` 通过；决策记录见 [DMv031-drag-drop-spike](.planning/memos/dst-manager/DMv031-drag-drop-spike.md)（本机断开 RDP 会话输入桌面不活跃，OS 级拖拽最后一跳留待活跃桌面人工冒烟）。
- 批量新增图纸"来源文件"改为文件选择并下拉加载布局（PLAN-DM-011 Task 7）：新增 `selectTemplateFile`（经 `getShellBridge().select_file(TEMPLATE_FILE_FILTERS)` 选择并校验 `.dwg/.dwt` 扩展名后回显路径，选择按钮加 `aria-label` 规避 `<label>` 覆盖 accessible name）与 `loadLayoutOptions`（`POST /api/layout-names`，`cad_version` 固定 `"2020"`——workspace 响应无默认 CAD 版本字段）；"来源布局"三态渲染——`layoutLoading` 显示"正在读取布局…"、有 `layoutOptions` 且未回退时渲染 `<select>` 下拉、`layoutError` 时显示含"读取布局失败"的错误文案并回退手动输入 `<input>`；`queueInsertSheet` 校验与命令形状不变；e2e 新增选择文件加载布局下拉与读取失败回退两用例，既有"批量新增图纸校验"改用新 UI（假桥选择文件 + 布局下拉）、"维护属性"用例的 `模板文件` 定位改 `{exact:true}` 消歧义，35/35 通过、`npm run build` 零类型错误。
- 新增草稿恢复提示与保存状态可见性（PLAN-DM-011 Task 6）：`draftRecovered` 在 `loadDraft` 恢复非空草稿后按 `projectCommands(actions,cursor)` 计数置为待处理条数、`resetDraftState` 重置为 null，已打开态显示"已恢复上次未完成的改动（N 条待处理）"横幅（"继续"仅关横幅，"清空重来"走既有 `clearCommands`+`discardDraft`）；新增 `draftSaving` 并在 `scheduleDraftSave` 队列推进前后置位，草稿工具栏旁常驻 `saveStatusText` 四态展示（保存失败/保存中/草稿已过期/已保存），保存失败时给出"重试"按钮复用 `scheduleDraftSave` 保持幂等；泛型保存失败不再单独写 `error`（由常驻保存状态承担）；e2e 新增恢复横幅与保存失败两用例，33/33 通过、`npm run build` 零类型错误。
- 前端落地 DST 文件选择与关闭确认状态机（PLAN-DM-011 Task 5）：新增 `web/src/api/shell.ts`（`getShellBridge` 桥探测 + `DST_FILE_FILTERS`/`TEMPLATE_FILE_FILTERS`，过滤器采用 pywebview 括号格式 `"DST 文件 (*.dst)"`，规避竖线格式实测抛 ValueError）；App.vue 两态状态机——未打开态仅文件选择区（壳桥可用时"选择 DST 文件"并经 `.dst` 校验后自动打开，无壳回退保留原路径输入框），已打开态以"关闭"替换"打开项目"、修订历史保留；`openWorkspace` 抽出 `openByPath(path)`（保留 `beginWorkspaceLoad` 代次保护、`resetEditingState`、`loadDraft` 顺序），新增 `closeWorkspace`（未发布改动确认弹窗 + `discardDraft`，pending 判定按 SPEC §4.3"草稿动作非空"用 `draftActions.length>0||saveFailed||stale`；关闭时推进 `workspaceLoadGeneration` 并复位加载态，使关闭后迟到的打开/刷新/修订响应按代次失效，不会复活工作区）；e2e 经 `page.addInitScript` 注入壳桥假件，既有依赖路径输入框用例全部改经假桥点击"选择 DST 文件"，新增未打开态/非 `.dst` 提示/关闭确认/关闭后迟到刷新不复活四用例；`vue-tsc` 与 Playwright e2e 31/31 通过。
- 手动冒烟（本机 RDP 会话，WebView2 Runtime 已安装）：`uv run dst-manager desktop` 主窗口打开（标题 `DST Manager`，句柄有效）、后端在 `127.0.0.1` 临时端口启动并挂载 `web/dist` 前端、关闭窗口后应用与 uv 进程全部退出且端口释放；`select_file` 原生对话框返回绝对路径依赖交互点击，无交互桌面下无法自动验证，留待 Task 7 前端联调。
- 新增 pywebview 桌面壳（v0.3.1 唯一交付入口）：`uv add "pywebview>=5,<6"`；新增 `src/dst_manager/interfaces/shell.py`——`ShellBridge.select_file(file_types: list[str]) -> str | None` js_api 桥（未绑定窗口抛 `RuntimeError`，绑定后经 `window.create_file_dialog` 返回首个路径或 `None`）、`run_desktop` 以 `127.0.0.1:0` 临时端口启动 uvicorn 承载 `create_app()` 并打开 WebView2 窗口；`cli.py` 对齐 `serve` 风格新增 `desktop` 命令；新增 `tests/unit/test_shell.py` 3 项轻量单测（未绑定报错、返回首个路径、取消返回 None），`ruff check .` 与 `uv lock --check` 通过。
- 审查修复：`tests/unit/test_layout_names.py` 补充"executor 成功但未产出 sidecar"分支用例（`LAYOUT_READ_FAILED` 502 第二条路径），纯测试补覆盖，不改生产代码。
- 新增 `POST /api/layout-names` 布局名读取端点与 `DstManagerService.get_layout_names`：请求 `{"file_path": "<绝对路径>", "cad_version": "2016"|"2020"}`（`extra="forbid"`），响应 `{"layouts": [...], "cached": bool, "file_hash": "<sha256>"}`；复用 `open_workspace` 对用户路径的 `expanduser().resolve()` + 扩展名 + `is_file` 入口校验，命中全局缓存直接返回，未命中时在全新 `TemporaryDirectory` 副本（`.dwt` 同样复制为 `source.dwg`）上运行 `DstGetLayoutNames` 只读枚举并解析 sidecar；executor 失败（非零/超时/CAD 不可用）转换为 `LAYOUT_READ_FAILED`(502)，缓存结果经 `Database.get_layout_names`/`save_layout_names` 持久化；集成测试与注入假 executor 的 service 单测覆盖缓存二次命中、原 DWG 不被修改、`.dwt` 副本路径与 DB roundtrip/upsert/缺失→None。
- 新增 Worker 插件只读布局枚举命令 `DstGetLayoutNames`（仅遍历纸张空间布局、不修改图纸、不 QSAVE）与 `ScriptRenderer.render_layout_names`/`parse_layout_names`（`<dwg>.dst-layout-names.json` sidecar 渲染与解析，未知版本/解析失败抛 `ApplicationError("LAYOUT_READ_FAILED", ...)`）；单元测试全绿，插件 2016/2020 双版本构建成功，真实 AutoCAD Core Console 验证布局枚举与 Sheet Manager 显示一致且原 DWG 时间戳不变。
- 新增 `0004_dm007_layout_name_cache` 迁移与 `LayoutNameCacheRow` ORM：布局名全局缓存表 `layout_name_cache`（`file_hash` 主键 + `source_path`/`layouts` JSON/`created_at`），`Database.get_layout_names`/`save_layout_names` 实现读取与 upsert；`LATEST_SCHEMA_REVISION` 提升至 `0004_dm007_layout_name_cache`，全新库升级与旧 MVP 库升级测试同步更新。
- 新增 [PLAN-DM-011](.planning/plans/dst-manager/PLAN-DM-011-v031-shell-and-usability.md)（v0.3.1 实施计划，状态 `proposed`）：9 个任务覆盖布局缓存迁移、Worker 插件只读布局枚举命令、`POST /api/layout-names` 端点、pywebview 桌面壳、前端两态状态机/关闭确认/恢复提示/布局下拉、拖拽路径 spike 与交付收尾。
- 依据 v0.3 测试后意见（`.planning/memos/DMv03-test-report.md`）评审并重基线：新增 [SPEC-DM-007](docs/dst-manager/specs/SPEC-DM-007-v031-shell-and-usability.md)（桌面壳与操作易用性迭代，状态 `draft`）作为 v0.3.1 依据；SPEC-DM-006 界面重构推后为 v0.3.2（PLAN-DM-010 待编制）。关键决策：提前实现 WebView2 桌面壳（pywebview 选型倾向）并作为唯一交付入口；草稿暂存能力经核对已存在（确定性 workspace_id、自动保存、重开恢复、清空与发布后清除），定性为恢复可发现性改进；`template_layout` 保留 DWG/DWT 双支持；布局缓存（SHA-256 → 布局名）与暂存均存后端应用数据目录，不触碰工作区。同步更新 ROADMAP-DM-001 与计划索引。

- 按 UI/UX 审查报告（`.planning/memos/dst-manager/SPEC-DM-006-ui-ux-review.md`）修订 F-01～F-08，状态转为 `review`：新增 §9.1"正式工程文件写入"统一分类（普通发布/CSV/XML/修复/恢复共用预览 + 冻结摘要 + 基准复核 + 危险确认门禁）；修正 `Ctrl+S` 只打开确认模态不直接执行；§8 区分草稿 `expected_version`、任务重试复用冻结计划与正式写入 `base_revision_id + preview_digest`；§6.8 澄清草稿持久化到 `%LOCALAPPDATA%` 应用数据目录而非工程文件；新增 §6.9 ActionDock 操作×状态矩阵；§7 列出适用 WCAG 2.1 成功准则与树/表格/抽屉键盘模型；修订恢复引用改指 PLAN-DM-001/002 与 ADR-DM-004；§5.1 补齐浅色/深色完整令牌映射，§10 明确组合对比度、多次采样性能与视口×主题回归矩阵。
- 新增并升级静态 UI/UX demo（`.planning/dst-manager-ui-demo.html`，离线自包含）：落地三区外壳、令牌化双主题、危险确认模态与表单错误摘要；demo 底部操作栏改为由 §6.9 状态矩阵驱动，可一键切换 12 种状态（无工作区、无草稿、有草稿未预览、预览生成中、预览有效、预览过期、REPAIRED、两类 INVALID、任务执行中、NEEDS_REVIEW、恢复执行中），联动展示 CTA 文案/等级、禁用原因、顶栏 DST 状态、编辑/切换锁与快捷键旁路防护，并把发布/修复/恢复确认模态参数化以演示 F-01 统一门禁。
- 按复审报告闭环 SPEC R-01～R-03 与 Demo D-01～D-07：§7.3 承诺完整 WCAG 2.1 AA（含响应式变体与人工读屏），§7.1 为 `/`、`?` 增加 SC 2.1.4 关闭/重映射要求；`REPAIRED` 拆分为预览修复（Primary）与确认发布修复（Danger，仅预览后可用），声明不存在 Warning 按钮层级；视觉回归矩阵固定 `1024×768 / 1120×768 / 1440×900 / 900×768`（900 为韧性测试）。Demo 修复 `[hidden]` 状态同屏（加互斥断言）、1120/900 断点左右抽屉（触发按钮 + `aria-expanded` + 焦点困绕/归还）、树/表格/Tab 完整键盘模型（roving tabindex、方向键、typeahead、单停靠点行焦点、卸载焦点恢复、`aria-controls`）、正式写入文案统一、错误摘要标题聚焦与链接直指控件、单字符快捷键开关持久化、toast 可关闭且错误保留。
- 新增 `SPEC-DM-006` UI/UX 规范审查备忘录：记录正式写入分类、危险快捷键、API 契约、草稿持久化、CTA 状态、无障碍、修订恢复引用和验收口径等问题，并给出修订顺序与接受门禁。
- 更新 `SPEC-DM-006` UI/UX 审查备忘录为修订后复审报告：确认初审 5 项关闭、3 项部分关闭，补充 WCAG 2.1 AA/单字符快捷键、未定义 `Primary/Warning` 和确定视口问题；新增静态 HTML Demo 的状态互斥、响应式抽屉、复合组件键盘模型、错误摘要与文案一致性审查及接受门禁。

## 2026-09-01（DST 契约与 v0.3 计划审查）

- 固定 OpenAPI 与 TypeScript 生成契约使用 LF，避免 Windows `core.autocrlf=true` 检出后误触发生成漂移门禁。
- `SPEC-DM-004`（DST XML Schema 校验与可修复加载契约）状态由 `draft` 转为 `accepted`，同步更新文档索引与元数据；作为 `PLAN-DM-002`（v0.3 受控日常编辑器）的前置门禁生效。
- 完成 `PLAN-DM-002` 灰区审查并回写计划：API/Web 采用 Pydantic/OpenAPI 单一契约来源，所有用户发起的正式工程文件写入统一绑定当前基准与预览摘要；草稿明确为版本化动作历史且不自动 rebase，300 张图纸交互增加量化预算。
- 明确新增独立 `delete_subset` 语义：整体删除 `AcSmSubset` 子树、全部图纸及主 DWG，不探测工程外部引用但保留内部 ID/存活图纸断链阻断；正式文件删除须先由后续 Spec/ADR 定义 before 快照、发布事务和恢复协议。
- 启动 `PLAN-DM-002` 实施：变更命令改为 Pydantic 判别联合并拒绝未知命令、未知字段和 `subset` 自定义属性作用域；预览/执行请求正式分离，普通变更与 CSV 导入执行均强制复核 `preview_digest`，Web CSV 发布同步提交冻结摘要。
- 完成 `PLAN-DM-002`：补齐响应模型、OpenAPI/TypeScript 生成与漂移门禁，正式写入统一版本化预览摘要；新增原子持久草稿、撤销/重做、过期/冲突隔离，以及拆分后的导航、图纸表格、属性、草稿、预览、任务、修复和历史组件。
- Web 新增图纸集/子集/图纸三级导航，按图号、标题、自定义属性及 DWG 多路径搜索，诊断/路径/待变更过滤，多选、当前结果全选、既有图纸属性原子批量动作和 80 行增量渲染；300 行 Chromium 最终采样首屏 193 ms、中位数 31.9 ms、P95 33.3 ms。
- 接受 `ADR-DM-004` 与 `SPEC-DM-005` 并实现独立 `delete_subset`：明确确认后删除完整 AcSm 子树、全部图纸和主 DWG；内部未知 ID 引用及存活 DWG 引用阻断，纯删除不要求 Core Console但仍走永久 before、多文件 journal、回滚和启动恢复。
- 预览新增按 AutoCAD 版本与 `cad_operation` 的历史耗时估算；历史样本不足时使用版本化保守 fallback，并显示 Core Console 数量、并发度、范围和来源。
- 完成交付审查修复：草稿对合法 JSON 做完整语义校验并隔离损坏文件，动作移除不再误激活 redo 区，undo/redo/重开同时投影表单与命令；CAD 估算按并发槽计算 makespan，图纸集名称显示 before/after，子集删除在预览阶段阻断越界或多主 DWG；核心预览结构改为 Pydantic/OpenAPI 明确模型并移除前端 `any` 覆盖，应用版本统一为 `0.3.0`。
- 同步 `ROADMAP-DM-001`、DST Manager 计划索引与产品入口，统一当前基线为 v0.2.1 并补全 PLAN-DM-005 至 PLAN-DM-009 的追溯关系。

## 2026-08-27（PLAN-DM-009 审查修复）

- 修复器在修复后合并契约复核（`validate_contract`）到阻断集：父级包含关系等修复器未建模的契约错误不再伪装成 `REPAIRED`/`VALID`，而是进入 `INVALID_REPAIR_REQUIRED` 并以 `REPAIR_BLOCKED` 阻断写入；与既有 `CONTRACT_*` 按（code、object、message）去重避免重复报告，消除“用户确认修复后必然 `XML_VALIDATION_FAILED`”和“`dst_validation=VALID` 却带有结构错误”的死胡同（对应审查 Important #1）。
- `repairs/preview` 的 `preview_digest` 仅在 `REPAIRED` 状态返回，`INVALID_*` 不返回摘要，避免把“不可执行阻断”与“待确认修复”混为一谈（对应审查 Minor #4）。
- `AcsmDocument(repair=False)` 的 actions 语义注释明确为“本次识别但未应用的修复记录”，`RepairReport` docstring 补充契约层层级/必需属性错误归入 `INVALID_REPAIR_REQUIRED`（对应审查 Minor #3）。
- 新增回归：层级错误样本（`AcSmSheet` 直属 `AcSmDatabase`，其余结构完整）打开即 `INVALID_REPAIR_REQUIRED` 且预览写入 409（修复器级 + 入口级两条）；两次独立解码修复的 `repair_digest` 一致且绑定基准修订（固化掩码不变量，对应审查 Important #2）。
- 决策记录：`restore_revision` 不受修复门禁限制（显式破坏性恢复是 `INVALID_*` 状态下用户唯一出路，恢复后重新校验），保持既有行为（对应审查 Minor #5）。

## 2026-08-27（PLAN-DM-009 交付审查）

- 完成 PLAN-DM-009 交付验证：`uv sync --dev`、`uv run ruff check .`、`uv run pytest -q`（432 passed / 66 skipped，退出码 0）、`uv lock --check` 全部通过；黄金样本 `VALID` 零修复、失败样本 231 项可审计内存修复且原件/时间戳不变、新建 Sheet 子树与黄金契约逐字段一致并保留未知内容与顺序。
- 发布事务回归覆盖写入门禁、独立修复修订、异常/基线漂移/暂存失败回滚与启动恢复；service/CAD/XML 全部入口统一 `load_acsm`；Web 修复确认界面与 e2e 19/19 通过。
- 真实 AutoCAD 2016/2020 系统测试与官方 Sheet Manager 显示验收：本机未设置 `DST_MANAGER_RUN_AUTOCAD=1` 且无对应 Core Console/Worker/私有 DWG 样本，按计划记录跳过条件，不视为通过。
- PLAN-DM-009 标记为 `completed`，交付验证记录写入计划正文；SPEC-DM-004 补充修复器“不丢弃副本、未确定修复进入阻断诊断”的实施说明。

## 2026-08-27（PLAN-DM-009：修复确认界面）

- Web 新增 `DstValidation`/`RepairAction` 类型与修复面板：四种状态各自的文案、颜色与按钮可用性（`VALID` 无面板；`REPAIRED` 显示“预览并确认修复”；两个 `INVALID_*` 只显示诊断）；逐项展示凭 code/路径/before/after/confidence 与阻断原因，长路径可换行且不含敏感绝对路径。
- 修复确认流程：预览调用 `repairs/preview` 固定基准并展示摘要，确认后经 `repairs/execute` 发布；确认前普通编辑发布按钮（预览变更/确认执行/CSV 导入）全部禁用；修复成功后刷新工作区、修订与诊断。加载代次/workspace 修订变化时丢弃旧修复报告。
- 前端生产构建通过（vue-tsc + vite），Playwright e2e 新增修复流程用例，19/19 全部通过。

## 2026-08-27（PLAN-DM-009：修复事务与 CAD 边界）

- CAD 暂存加载（`_write_staged_dst` 及其 round-trip）要求统一 loader 结果为 `VALID`，任何修复/阻断诊断都会以 `DST_REPAIR_GATE_BLOCKED` 使任务失败，不把不完整图纸交给 AutoCAD Worker。
- 修复独立修订的发布完全复用现有锁、暂存、永久 before 快照、发布日志、失败回滚与启动恢复流程：新增事务回归（发布中途异常 → ROLLED_BACK/NEEDS_REVIEW/FAILED 安全终态且正式 DST 保持发布前字节、暂存编码失败可追踪无 manifest、PUBLISHING 中断后启动恢复回滚正式 DST）。
- 修复成功后工作区重载为 `VALID`，普通元数据/结构/CAD 流程继续经过既有基准与权限校验（含修复后 24 张图的 CAD 暂存可达 VALID）。
- AutoCAD 系统测试跳过：本机未设置 `DST_MANAGER_RUN_AUTOCAD=1`（且未确认 Core Console/Worker/私有样本），按计划记录跳过条件，不伪造通过结果。

## 2026-08-27（PLAN-DM-009：统一加载与修复确认）

- 新增统一 loader `load_acsm`（service/cad_job/XML 入口全部改用，工作区序列化新增稳定字段 `dst_validation`：`status`/`actions`/`blocking_issues`，`diagnostics` 保持向后兼容）；文件 SHA-256 仍是 revision 基准，内存修复不改 revision，只读打开不产生 `.dst-manager/` 或时间戳变化。
- 新增写入门禁：`VALID` 才能正常预览/执行；`REPAIRED` 必须先经独立修复修订确认（409 `REPAIR_CONFIRMATION_REQUIRED`）；`INVALID_REPAIR_REQUIRED`/`INVALID_UNRECOVERABLE` 只能读和显示诊断（409 `REPAIR_BLOCKED`/`REPAIR_UNRECOVERABLE`）。
- 新增 `POST /api/workspaces/{id}/repairs/preview` 与 `/repairs/execute`：预览固定 base revision 并返回修复摘要（修复后 DOM canonical 字节对 `ID` 值掩码后与基准组合，保证预览/执行独立重解码结果一致）；执行从正式 DST 重新解码、修复、严格校验并复核摘要，沿现有锁/暂存/永久 before 快照/发布日志/回滚发布独立修复修订。
- 新增入口一致性测试与 API 覆盖：黄金样本打开 `VALID`、失败样本返回报告且不改文件、未确认修复被明确错误码阻断、确认后产生新修订并重载为 `VALID`、篡改摘要/基准漂移被拒。
- `tiny_workspace` 测试夹具改为契约合规文档（固定 clsid/propname/vt + AcSmSheetViews），既有测试全部回归通过；属性作用域冲突的工作区改为“打开即可见阻断诊断、写入 409”。

## 2026-08-27（PLAN-DM-009：新增 Sheet 契约对齐）

- `AcsmDocument` 加载流程改为 parse → 宽容契约扫描 → 可选内存修复 → 严格 XSD → 语义校验；新增可选参数 `repair`（默认 True）与 `repair_report` 属性，修复只作用深拷贝副本，`clone()` 同步复制报告状态；`repair=False` 时已识别但未应用的修复标记为 `INVALID_REPAIR_REQUIRED`。
- `_make_sheet_node`/`_make_subset_node`/`_make_custom_property_bag`/`_make_property_value` 改为 contract-driven 工厂：补齐 `clsid`、固定 `propname`、`vt=13`，布局四字段与 `Number`/`Title` 使用 `vt=8`，新 Sheet 按黄金顺序补齐 `AcSmSheetViews`。
- `validate()` 合并契约、严格 XSD、语义与既有自定义属性诊断，保持既有错误码兼容，新增稳定英文错误码（`CONTRACT_*`/`PROP_VT_*`/`XSD_INVALID`）。
- 新增回归测试：工厂输出与黄金契约逐字段一致、`insert_sheet`/`insert_subset`/`apply_derived_document` 的新图纸均含 `AcSmSheetViews` 且保留未知节点与顺序、失败样本加载修复后 24 张图纸全部可见且 `validate()` 零问题、样本原件字节与 mtime 不变。

## 2026-08-27（PLAN-DM-009：内存修复与报告）

- 领域层新增 `RepairStatus`（VALID/REPAIRED/INVALID_REPAIR_REQUIRED/INVALID_UNRECOVERABLE）、`RepairConfidence`、不可变 `RepairAction` 与 `RepairReport` 诊断值对象，不依赖 lxml/文件系统。
- 新建 `src/dst_manager/infrastructure/acsm_xml/repair.py`：`AcsmRepairer` 在深拷贝 DOM 上按固定顺序修复（全局 ID 索引 → 补 ID → 按 contract 补固定属性 → 补 AcSmProp vt → 黄金位置补 AcSmSheetViews → 汇总阻断诊断）；不修改传入 root、不写文件；状态分类为结构性不可恢复（重复/非法 ID、根错误）→ `INVALID_UNRECOVERABLE`，其余阻断（缺业务值、布局冲突、错误非空固定值、属性作用域冲突）→ `INVALID_REPAIR_REQUIRED` 且不覆盖原值。
- 新增 `tests/unit/test_acsm_repair.py`（10 项）：黄金 no-op（VALID/零 action/序列化一致/输入不变）、失败样本内存修复（补齐 SheetViews≥11、生成 ID 合法且全局唯一、contract 通过、样本原件不变）及负例阻断（重复 ID、非空错误 clsid、缺业务值、缺/多布局、Flags 作用域冲突）。

## 2026-08-27（PLAN-DM-009：AcSm 契约与 schema）

- 新建 `src/dst_manager/infrastructure/acsm_xml/contract.py`：版本化 AcSm contract registry，固化七类已知对象（`AcSmSheetSet`/`AcSmSubset`/`AcSmSheet`/`AcSmCustomPropertyBag`/`AcSmCustomPropertyValue`/`AcSmAcDbLayoutReference`/`AcSmSheetViews`）的必需属性、固定 `clsid` 和已知 `AcSmProp` 的 `vt` 类型表，并校验已知对象父级包含关系；未知元素/属性/顺序/tail 一律宽容保留。
- 新建 `src/dst_manager/infrastructure/acsm_xml/schema/acsm-v1.xsd`：修复后结构边界，声明已知对象类型并允许扩展节点/属性；由于 lxml 不支持 XSD 1.1 assert，必需子节点不变量由契约/语义校验器承担（已在代码注释与规范中记录职责分工）。
- 新增 `tests/unit/test_acsm_contract.py`（12 项）：黄金样本 contract+XSD 零错误、Sheet 仅要求 ID+固定 clsid、固定 ID 表、`vt` 类型区分（`Flags=3`/文本=8/`PromptForDwt`/`FileRevision`=2/3，不默认 8）、未知内容忽略与负例（缺 ID/错误固定值/缺 vt/错误层级/错误根）。

## 2026-08-27（PLAN-DM-008 复审修复）

- 新增 `PLAN-DM-009` 实施计划：按 `SPEC-DM-004` 分解 AcSm contract/XSD、内存修复报告、统一加载门禁、独立修复发布事务、Web 确认和全量验证任务。
- 新增 `SPEC-DM-004` 草案，基于 Project1 黄金/失败 XML 固化 AcSm 新建 Sheet 最小契约、加载时可修复校验边界及用户确认后的受控发布流程；同步修正 `RES-SH-001` 对 `AcSmSheet` 标签属性的描述。
- 新增 `scripts/dst-to-xml.ps1`：复用 `DstCodec` 将 `.dst` 解码为原始 XML 字节，支持单文件/目录递归输入、指定输出目录及默认同目录输出，已用临时 DST 往返一致验证。
- 加固 CAD Worker 租约隔离：发布替换正式文件前、发布过程中及 finalize 前持续复核 worker/attempt；失权的旧进程只能进入安全隔离状态，不能恢复任务成功或写入修订。
- 将过期任务回收放入每次 Worker 领取前的轮询路径，避免服务重启后租约尚未过期而长期阻塞队列；JobFile 更新同时绑定 worker/attempt，旧 attempt 不能覆盖新 attempt。
- 并发 CAD 单元失败后排空当前批次再按工作单元序号选择首个失败，补充发布租约、任务租约、JobFile 隔离和轮询回收回归测试。

## 2026-08-26（PLAN-DM-008 延后 CAD 校验与布局批量改名）

- 修复最终审查问题：`rename_only` 按十六进制数值拒绝同一 DWG 内重复 Handle，发布前再次执行 DWG+Handle 全局复核；长 CAD 单元按租约续写 heartbeat，旧 attempt 失权后不能更新、补充工作或发布。
- SQLite 领取事务强制同一数据库仅一个活跃 CAD job；安全重试原子清空 JobFile 的上次 attempt 终态；同批并发失败稳定选择最小工作单元下标。布局改名协议文档统一为“按暂存 DWG 派生固定 sidecar，SCR 不传请求路径”。
- 完成 `PLAN-DM-008`：快速结构预览不启动 Core Console，只采集路径、身份与 SHA-256；用户确认后在暂存任务中执行真实布局集合、来源与 CAD 版本校验，并按子集分类 `none`、`rename_only`、`rebuild`。
- 新增 AutoCAD 2016/2020 `DstRenameLayouts` 固定协议与两阶段布局改名；`rename_only` 不删除/导入布局、不读取或覆盖 Handle，`rebuild` 才完整重建并回读 Handle。共享 Core Console 并发默认 4、合法范围 1–10，任一单元、DOM 或发布失败均不发布正式文件。
- 完成事务与接口回归：混合 rename/rebuild/delete、来源基线漂移、结果缺失、Handle 非法、第二 CAD 进程失败均保持正式文件哈希不变且无 manifest；`GET /api/jobs/{job_id}` 直接返回文件级 `cad_operation`、`started_at`、`finished_at`。
- AutoCAD 2016/2020 非性能系统矩阵 54/54 passed；布局改名协议矩阵 16/16 passed，改名前后 Handle 不变，`acad.err` 前后保持 2178 bytes/54 lines。双版本插件构建成功，0 warning、0 error。
- 10 个真实 CAD 工作单元（5 `rename_only` + 5 `rebuild`）性能矩阵 6/6 passed：2016 的并发 1/4/10 墙钟分别为 37236/16290/13436 ms，2020 分别为 42307/15604/10802 ms；任务时长、逐文件耗时和峰值内存记录在 `PLAN-DM-008`，不把单轮数据表述为稳定加速比例。
- 最终验证：相关 Python 200 passed；全量 Python 367 passed、64 skipped（60 项真实 CAD 在普通全量命令中因未显式启用而跳过，已由上述独立真实 CAD 命令覆盖；另 4 项为既有环境跳过）；Ruff、`uv lock --check`、全新 Alembic 升级与 `git diff --check` 通过；Web production build 通过，Playwright 18 passed。

## 2026-08-25（DST Manager v0.21 CAD 单脚本布局重建需求调整）

- 接受 `ADR-DM-003` 与 `SPEC-DM-003`，新增 `PLAN-DM-008`：将快速预览、数量变化前沿、布局批量改名、Handle 保留、共享 1–10 并发、Web 展示及双版本真实 CAD 验收拆分为可测试任务；后续实现与验收见 2026-08-26 记录。
- 新增 `ADR-DM-003` 与 `SPEC-DM-003` 评审设计：结构预览延后 CAD 校验、按子集图纸数量变化前沿安排 CAD 工作，并将仅布局名称变化分流为保留 Handle 的批量改名；实施证据见 2026-08-26 记录。
- 接受 `SPEC-DM-002` 并新增 `ADR-DM-002`：确认结构性 DWG 重建将布局修改与 Handle 获取合并为一次 Core Console 执行，更新 `ARCH-DM-001` 的生产流程；保留 Handle 校验、暂存发布、回滚和双版本真实 CAD 验收边界，并将新进程重新打开验证从生产必要条件调整为验收/诊断手段。
- 新增 `PLAN-DM-007`，拆分决策基线、SCR 渲染器、CAD Worker 单次执行、失败回滚回归、双版本 CAD 性能验证和文档闭环任务。
- 完成单脚本实现：每个 `RebuildWorkUnit` 在一个 `rebuild-*.scr` 和一次 Core Console 调用中完成布局重建、Handle 获取、校验和保存，结构性路径调用数由 `2G` 降为 `G`；保留模板检查用的独立 `render_handles()`。
- 全量 Python 测试、Ruff 和锁文件检查均通过；全量 pytest 为 302 passed、32 skipped。真实 CAD 系统测试在显式设置 `DST_MANAGER_RUN_AUTOCAD=1` 后为 26 skipped：私有样本缺失，现有的 2016/2020 `accoreconsole.exe` 路径尚未显式配置，双版本 Worker DLL 尚未构建和配置，`dst-manager doctor` 因此报告两个版本不可用。插件构建、独立新进程重开验收和性能采样均未执行；`PLAN-DM-007` 因未完成真实双版本验收和性能测量标记为受阻，恢复条件见计划实际验证记录。

## 2026-08-23

- 新增 MIT 开源协议文件、README 许可证入口及 Python 包许可证元数据声明。

## 2026-08-21（v0.21 受控图纸集编辑计划）

- 更新 `PLAN-DM-006` 最终验证记录：在最终修复 `cc249f9` 上重跑依赖同步、Ruff、298 项 Python 通过/32 项跳过、锁文件、Alembic、Web 构建、17 项 Playwright、双版本插件和显式 CAD 收集；真实 CAD 的 26 项仍因隔离工作树缺少私有 `sample/project1` 跳过。

- 同步 `SPEC-DM-001` 与 `ADR-DM-001` 的最终验收计数和提交范围，保持规范、决策、计划与变更记录的可追溯性一致。

- 加固结构预览确认链：摘要绑定基准、CAD 版本、规范化命令、布局快照证据与语义差异；模板检查改在写锁内的临时快照上完成，并由 Worker 复核源文件 hash/identity。结构执行必须回传该摘要；允许合法的工作区外绝对模板，受控既有 DWG 仍限制在工作区。同步修正属性命令归一化、派生 DWG 陈旧范围前缀及不可证明发布清单的启动隔离。

- 完成 `PLAN-DM-006` 最终交付闭环：受控图纸集编辑规范转为已接受、架构基线标明 v0.21 替代关系，并记录非 CAD 全量验证、双版本插件构建及因私有样本缺失而待补跑的真实 CAD 验收。
  - 修正 `PLAN-DM-006` 到 `SPEC-DM-001` 的相对链接，并验证链接目标文件存在。
- 修复最终事务审查缺口：结构计划持久化 DST、既有 DWG 与模板源内容基准，CAD、metadata 和修订恢复在写锁内拒绝预览后的外部替换；COMMITTED 发布通过幂等数据库事务一次闭环修订、当前版本、任务终态与写锁，启动时可从主 journal/manifest 恢复各提交崩溃窗口；旧恢复任务按类型隔离，恢复与 XML 导出的 staging、回滚、恢复失败及提交后诊断均稳定落入安全终态。
  - 后续事务审查修复：发布结果在最终复核、`COMMITTED` 落盘和数据库 finalize 之间持续持有不可写不可删除句柄，删除结果以同名 delete-pending 占位阻断重建；启动恢复重新验证结果 hash/identity，修订 ID 改为操作唯一；永久恢复源绑定 hash/identity，非主 DST XML 导出绑定预览目标基准，历史非 CAD 排队任务统一隔离并释放写锁。
  - 第三轮事务审查修复：Windows delete-pending 占位关闭后不再按路径二次删除，非 Windows 回退仅清理创建时同一文件身份；manifest 改为归档最后原子发布的数据库可见性闸门，归档失败不执行 finalize，任务先隔离并在启动归档恢复后幂等成功。
  - 第四轮事务审查修复：非 Windows 占位先原子移入操作私有 tombstone 再核验身份，外部替换对象恢复或留档隔离；启动恢复逐项比较 COMMITTED 主 journal 与 manifest，自动刷新 cleanup 状态或内容陈旧的归档。
  - 第五轮事务审查修复：正式发布结果守卫在非 Windows 明确 fail-closed，不再执行任何按路径清理；COMMITTED 恢复以 manifest 的不可变事务投影为安全基准，仅在 operation、工作区根、状态及完整文件审计向量一致时同步 cleanup 字段，篡改时保留 manifest 并隔离任务。
- 修复 `PLAN-DM-006` 最终领域与 AcSm DOM 审查缺口：结构 ID 按数据库及当前对象顺序确定性派生并阻断全局冲突，Sheet/Subset 重建按原受控槽位一次协调且保留未知兄弟节点，兼容 1–999 的 Legacy `Transdigit`，以 SheetSet `Flags=2` 锚点持久化空图纸集的 sheet 属性定义，并统一受控 XML 1.0 文本校验。
  - 后续审查修复：受控 Sheet/Subset 重排、删除或插入时将 `tail` 作为原 child 槽位后的混合内容边界保留，避免文本随节点移动、被删除或跨越未知兄弟节点。
- 修复 `PLAN-DM-006` 最终预览审查缺口：结构预览按所选 AutoCAD 2016/2020 在任务创建前检查工作区内 DWG/DWT 来源及布局，固化路径、内容哈希、版本、可用布局和请求布局证据；CAD Worker 在启动前复核完整证据并继续使用锁内内容基准阻断漂移。预览新增服务端完整前后有序结构、属性影响数及 DWG/布局语义差异，Web 冻结同一 CAD 版本用于预览和执行并直接展示这些证据。
- 实现 `PLAN-DM-006` 任务 6：Web 编辑器移除图纸移动、排序及手工图号/标题入口，新增属性定义与 CSV 流程、按位置批量插图和新建子集表单；普通预览只呈现服务端变更、诊断、受影响文件及 create/rebuild 执行分组，并保留任务重试与修订恢复交互。
  - 修复轮次 1：普通命令与 CSV 预览绑定不可变工作区、基准修订和输入快照，使用 generation 丢弃换文件、清空、修改命令及乱序请求产生的过期响应；CSV 改用严格 UTF-8 解码并在非法字节进入 API 前稳定阻断。
  - 修复轮次 2：打开与刷新工作区共享 latest-wins 加载代次，加载期间隐藏旧工作区操作入口，并在新工作区落地时再次清除预览上下文；执行普通变更或 CSV 导入前额外复核工作区 ID 与基准修订，阻断跨工作区提交。
  - 修复轮次 3：任务 SSE/轮询、重试与执行结果绑定工作区和监控代次，显式打开新工作区会关闭旧监控并阻止旧终态刷新；修订列表、恢复预览与恢复执行同样采用工作区快照和 latest-wins 代次，迟到响应不再污染新工作区。
  - 修复轮次 4：修订恢复写入使用独立执行代次和不可变工作区上下文，不再受修订列表或恢复预览读取代次影响；执行期间同时在界面和函数入口阻断打开、历史及恢复操作，成功后刷新工作区与修订列表，失败后稳定解锁并显示错误。
- 实现 `PLAN-DM-006` 任务 5：提供属性 CSV 模板、行级诊断、幂等导入与导出 API，扩展工作区属性定义和子集派生字段序列化；受控命令白名单移除旧移动、排序、重编号及手工图号/标题入口，属性新增、删除继续经过基准修订、受控 DOM、永久快照和事务发布。
  - 修复轮次 1：全量跳过的 CSV 导入改为不创建任务、修订、发布或写锁的稳定 no-op；领域解析一次性返回逻辑记录物理起始行与诊断，CSV 预览合并主预览的 DOM/文件执行语义；图纸属性定义默认值统一稳定为空字符串，非法 Unicode 请求返回可预测编码诊断。
  - 修复轮次 2：属性默认值按 XML 1.0 合法字符集统一校验，CSV 保留非法值所在逻辑记录的物理起始行；直接属性定义命令与 AcSm 文本工厂将非法字符转换为稳定诊断，不再泄漏 lxml 异常或返回 500。
- 实现 `PLAN-DM-006` 任务 4：结构计划区分既有 DWG 重建与模板新建，持久化单次 `DerivedDocument` 派生结果；CAD Worker 在 Handle 一一对应且非零后写入最终 DOM，并通过既有事务发布器覆盖创建、替换和删除混合回滚。
  - 修复轮次 1：新增完整 DWG 来源到最终目标路径图和 create 空基准，阻断既有目标碰撞；源快照、CAD 与发布统一保持在写锁内，发布器在正式替换前复核存在/不存在基准，并以锁内原子替换支持连锁改名、竞态阻断和整批回滚；旧手工图号/标题命令统一拒绝。
  - 修复轮次 2：create 正式提交改用原子 no-replace 移动，既有目标以带同卷 backup 的 `ReplaceFileW` 捕获并复核实际被替换版本；发布前持久化 attempted 状态，补齐 API 部分失败与启动恢复，并新增中部插入 DWG 路径重叠的完整发布回归。
  - 修复轮次 3：发布 journal 持久化 baseline、暂存结果、正式结果和 replacement backup 的文件身份；替换、删除、回滚与启动恢复只操作可证明属于本批的文件，同字节不同身份或目标缺失歧义会保留现场并稳定报错；replacement backup 清理改为 Windows 文件句柄锁内的身份复核删除，旧 journal 继续走显式兼容分支。
  - 修复轮次 4：调用方以不可变 hash/identity 对象固定发布基准，CadJob 在写锁内且复制快照前采样；journal 持久化 Win32 API source 与调用状态，按 source 文件身份消除崩溃恢复歧义并拒绝未知身份版本；replacement backup 改为先持久化 `COMMITTED` 再身份安全清理，失败保留 pending 诊断并支持启动重试；WinError 32 回滚仅通过原 backup 文件对象换名恢复，否则保留现场并报告失败。
- 实现 `PLAN-DM-006` 任务 3：新增 AcSm 属性定义增删、受控子集/批量图纸节点工厂和 `DerivedDocument` DOM 写入，旧移动/手工标题结构命令在 DOM 边界被拒绝。
  - 修复轮次 1：新增图纸绑定前统一使用占位 Handle `0`，最终 `validate()` 拒绝占位 Handle；`apply_derived_document()` 改为事务式写入，失败不污染原 DOM，并补齐多图纸属性删除作用域测试。
- 修复 `PLAN-DM-006` 任务 2 审查缺口：同批属性导入会覆盖后续新增图纸，CSV 属性名拒绝控制字符，同名标题组统一使用首个拼写，并恢复受控删除图纸派生。
- 实现 `PLAN-DM-006` 任务 2：新增纯领域图纸集编辑规则、CSV 属性定义校验、标题后缀派生和统一 `DerivedDocument`，结构计划改为消费同一派生结果。
- 新增 `PLAN-DM-006` 拆分属性定义与 CSV、统一派生、受控 AcSm DOM、独立 DWG 创建、安全发布、API/Web 替换及双版本 CAD 验收任务；计划尚未开始实施。
- 新增 `ADR-DM-001`，将图纸集编辑从自由排序/手工标题切换为受控插入与统一派生，并为标题后缀补充 `EnableAddNumberSuffix`、`NumberSuffixType` 配置及校验测试。

## 2026-08-21（DST Manager v0.21 需求调整规范）

- 新增 `SPEC-DM-001` 草案，固化图纸集/图纸属性维护、CSV 契约、子集与图纸受控插入、标题后缀及旧编辑能力替代规则，并明确预览、发布安全和测试验收边界。

## 2026-08-20（启动依赖复用）

- 更新 `scripts/start.ps1`：Python 同步严格使用 `uv.lock`；Web 依赖以 `package-lock.json` SHA-256 与 `npm ls` 校验已安装内容，仅在锁文件变化、依赖缺失或校验失败时重新执行 `npm ci`，避免重复启动时反复安装包。

## 2026-08-18（同步文档协作约束）

- 将双项目文档治理的 scope 边界、文档类型、正式文档元数据与状态、唯一权威位置及索引维护要求同步到 `AGENTS.md`，并指向完整治理设计。

## 2026-08-18（黄金样本模板）

- 在本地 `sample/golden-template/` 新增黄金样本模板，包含 Legacy 输入、基线成果、来源记录、验收清单和语义期望文件；DST、DWG 和 Excel 先以 0 字节文件占位，并明确标记为未验收模板。
- 调整 Git 忽略规则，仅允许追踪 `sample/golden-template/`，继续忽略 `sample/` 下的其他本地样本。

## 2026-08-18（文档迁移终审修复）

- 补齐长期文档与执行资料的模板、三条路线图和归档导航，确保当前有效文档与模板可在三次点击内到达。
- 闭合双项目文档迁移计划的完成态记录，并将本地链接审计收紧为四个获准历史引用的精确组合。
- 完善 Legacy Python 重构与 DST Manager 产品入口的定位、状态、规范和指南说明，移除 README 的孤立正式编号。

## 2026-08-17（DST Manager 文档与计划迁移）

- 归档 DST Manager 架构基线、产品愿景、路线图与 v0.2 至 v1.0 正式 Plan，并为架构与计划补充统一 ID、状态和关联元数据。
- 更新文档、执行资料、根入口和代理必读路径，DST Manager 现通过产品入口、路线图和 Plan 索引导航。

- 归档两条产品线共用的 DST/AcSm、AutoCAD 插件和版本兼容技术资料；为五份资料补充稳定 ID、统一元数据和共享入口，并将 Project1 XML/CSV 研究证据与对应分析共置。
- 完成双项目文档迁移与链接审计：两条产品线、共享能力和跨项目整合入口均已建立；旧平铺文档已通过 `git mv` 归档至新位置，Project1 XML/CSV 样本证据 SHA-256 保持一致。

## 2026-08-17（双项目文档治理设计）

- 修复 Legacy 文档迁移后的根入口和历史脚本相对链接。
- 归档 Legacy Python 重构文档，建立产品愿景、路线图、架构基线、评估和开发交接入口。
- 建立文档治理入口、模板和整合路线图；尚未移动业务文档。
- 新增 `docs/integration/architecture/ARCH-INT-001-documentation-organization.md`，明确 Legacy Python 重构、DST Manager、公共能力和跨项目整合四类文档边界。
- 统一 Vision、PRD、Spec、Architecture、ADR、RFC、Roadmap、Plan、Todo、Memo、Guide、Reference 和 Research 的职责、状态、编号、索引与流转规则。
- 制定现有文档的渐进迁移映射和三阶段整理方案；本次仅落地设计，不移动或拆分现有文档。
- 新增 `.planning/plans/integration/PLAN-INT-001-documentation-migration.md`，把目录骨架、Legacy/DST Manager/共享资料迁移、索引收口和断链审计拆为五个可独立验证的实施任务。
- 将 `.worktrees/` 加入 Git 忽略规则，为文档迁移建立项目内隔离工作区，避免工作树内容进入提交。

## 2026-08-12（DST Manager v0.2.1）

- Core Console 每次调用的 stdout/stderr 现在按“重建布局”和“读取布局 Handle”分段归档；非零退出时也会写入对应逐 DWG 日志，并在 Web 任务详情中展开显示。
- 将 AcSm 自定义属性身份改为 `propname + Flags`：`Flags=1` 仅供 SheetSet 命令修改，`Flags=2` 仅供 Sheet 命令修改；投影、更新和克隆清空均按作用域隔离。
- 按 AutoCAD 规范化行为处理空属性：缺失 `Value` 代表空值，语义未变化时保持 DOM，清空非空值时删除节点，非空写入按已验证的 `vt=8` 结构受控创建；重复/非法结构返回稳定业务错误码。
- 预览阶段在 AcSm DOM 克隆上复用正式命令处理器，不依赖 CAD 的结构错误会使 `executable=false`，不再进入 Core Console 后才失败。
- 重构 `scripts/start.ps1`：使用确定的虚拟环境 Python 入口、`run_id` 健康校验、精确项目进程树识别、重复实例保护、完整停止、独立运行日志目录、严格 UTF-8 校验、日志尾部查看和仅清理已停止实例的保留策略；旧根目录日志会保留原始 `.legacy.bin` 并生成可读 UTF-8 文本。
- Worker stdout 收敛为单行任务摘要，AutoCAD 系统代码页输出统一解码、清理控制字符后以 UTF-8 归档；API 健康接口返回当前 `run_id`。
- 数据库启动闸门同时校验 Alembic revision 与 SQLAlchemy 物理表/列，并用迁移哈希测试保护已发布 revision 不被原地修改。
- 版本提升至 `0.2.1`，补充 AcSm、API、数据库、PowerShell 生命周期、日志字节、Worker 摘要、并发等价、双版本 AutoCAD 热修复和失败不发布回归测试。

## 2026-08-12（文档归档约定）

- 更新 `AGENTS.md`，明确计划类、备忘/对话记录类和知识类文档分别归档到 `.planning/todos/`、`.planning/memos/` 和 `docs/`。

## 2026-08-12（v0.2.1 修复计划）

- 新增 `.planning/todos/05-v0.2.1-runtime-logging-and-acsm-hotfix.md`，基于真实测试中发现的缺失 AcSm `Value` 节点、重复 API/Worker、端口误判、混合编码及 NUL 日志问题，制定 P0 修复工作包、实施顺序、测试矩阵和验收标准。
- 根据 AutoCAD 实测修订 AcSm 自定义属性热修复规则：明确空值的规范形式为缺失 `Value`，清空操作应删除 `Value`；将 `Flags=1/2` 分别纳入 SheetSet/Sheet 作用域校验，并补充克隆清空、预览前移、错误码和双版本回归要求。
- 更新待办索引，将 v0.2.1 运行时与兼容性修复设为进入 v0.3 日常编辑器前的阻断条件。

## 2026-08-12（启动脚本）

- 新增 `scripts/start.ps1`：提供 `Start`、`Status`、`Stop` 三种操作，一键完成环境初始化、依赖同步、Web 构建、Alembic 升级、Web/API 与 CAD Worker 后台启动及健康检查；支持跳过同步/构建、禁用 Worker、关闭自动打开浏览器和自定义端口。
- 后台进程状态与标准输出/错误日志保存在 `.dst-manager-data/runtime/`；停止前校验 PID 和启动时间，并按进程树关闭本任务启动的服务，避免误停复用 PID 的其他进程。
- 将 `start.ps1` 与其复用的 `setup-env.ps1` 保存为 UTF-8 BOM，确保 Windows PowerShell 5.1 能正确解析中文注释和输出。
- 修复 Windows PowerShell 5.1 优先调用新版 Node.js `npm.ps1` 时把 `& npm ci` 错误解析为 `pm ci` 的问题；Web 安装和构建现在显式使用 `npm.cmd`。
- 启动同步前仅清理 `.venv/Lib/site-packages` 中缺少 `RECORD` 的旧版项目包元数据，并直接使用同步后的 Alembic 入口执行迁移，消除 v0.1 升级残留警告和重复环境刷新。

## 2026-08-12（DST Manager v0.2）

- 将 SQLite 初始化与升级统一收口到 Alembic，新增 v0.2 迁移、schema 版本闸门，并覆盖空库和既有 MVP 数据库升级。
- 为任务补充 `worker_id`、attempt、租约心跳、起止时间、错误详情和状态时间线；原子领取仅允许 `QUEUED → STAGING`，遗留任务按安全阶段重排队或转人工复核。
- 新增 `DST_MANAGER_CAD_MAX_PARALLEL`（默认 2、范围 1～4），以不可变 DWG 工作单元和有界线程池并行执行 Core Console；源文件先哈希快照，结果由调度线程确定性合并，任一失败时停止提交新组且不进入发布。
- 为逐 DWG 执行记录状态、进度、耗时、哈希、日志和错误，并在任务 API/Web 中提供汇总、时间线、脱敏日志摘要、错误建议、安全重试和 SSE 断线轮询降级。
- 新增按工作区筛选的修订历史、逐文件恢复预览与“恢复为新修订”；当前哈希冲突会阻断恢复，确认恢复继续复用永久 before 快照和可恢复整批发布。
- Web 更新为 v0.2 任务详情和修订恢复界面；增加任务并发/失败停止、原子领取、租约恢复、迁移升级、恢复冲突和 Playwright 交互测试。

## 2026-08-11

- 新增 `.planning/todos/` 后续实施计划：按 v0.2 稳定化与多 DWG 有界并行、v0.3 日常编辑器、v0.4 单人工作流和 v1.0 Windows 产品化拆分目标、工作包、测试矩阵、验收标准与风险边界。
- 新增 `scripts/setup-env.ps1` 与根目录 `.env.example`：自动生成 `.env`、探测本机 AutoCAD 2016/2020 的 `accoreconsole.exe` 写回 `.env`，并注入 `UV_LINK_MODE=copy` 与项目独立 `UV_CACHE_DIR`；脚本幂等、仅在项目根目录生效，支持 `-Force` 重建 `.env`。
- 更新 `README.md` 启动说明：改为先执行 `scripts/setup-env.ps1` 自动设置环境，并说明 `$PROFILE` 集成方式与 `.env` 变量来源。
- 新增 `docs/PROJECT1_DST_XML_ANALYSIS.md`、`docs/project1_sheetset.xml` 和 `docs/project1_sheet_manifest.csv`：使用项目 `DstCodec` 只读解码 `sample/project1` 的 DST，记录 AcSm XML 结构、节点统计、图纸/DWG 布局绑定和受控修改边界，并导出 298 张图纸清单。

## 2026-08-10（DST Manager MVP）

- 完善 `AGENTS.md`：补充语言与环境、架构依赖方向、DST/DWG 发布安全、私有目录、验证命令、测试分层和 Git 协作规范。
- 准备公开 GitHub 仓库：忽略 `legacy`、`lagacy`、`sample`、本地环境和工具缓存；公开克隆缺少私有样本时自动跳过对应测试，并更新启动说明。
- 创建 `src/dst_manager` MVP：实现兼容 legacy 的 DST/XML Codec、AcSm DOM 投影/校验、未知节点保留和DWG路径重定位。
- 新增受控编辑与预览、修订冲突检查、SQLite WAL任务索引、永久before快照和可恢复发布。
- 新增固定SCR渲染、危险参数拒绝、Handle解析、2016/2020能力探针、FastAPI/SSE、CLI和Vue界面。
- 新增黄金样本、Codec、未知XML保留、API执行和修订冲突测试，并更新UV依赖和启动说明。
- 调整打开工作区为文件层只读，只有确认执行时才在项目中创建 `.dst-manager`，确保黄金样本探针不写原件。
- 新增最小 AutoCAD Worker 插件源码及双版本构建脚本，提供受控布局清理与UTF-8布局Handle清单命令。
- 新增结构命令确定性规划、SQLite Worker领队列、DWG暂存重建、二次Handle回读、AcSm结构更新及整批发布链路。
- 新增模板布局检查API、用户根目录路径重绑定、固定源文件哈希快照、Windows写阻断锁和永久脚本/日志/发布清单归档。
- Web表单补齐插入、删除、重排、跨子集移动、模板来源、任务进度、诊断和修订历史流程。
- 新增Playwright主流程测试，覆盖打开工作区、模板新增、变更预览和确认执行。
- 实现图纸集/子集属性命令、批量重编号及 legacy 兼容的布局名、子集名、主DWG文件名同步派生。
- 完善多文件发布的新增/删除/替换回滚、数据库单写任务锁、启动恢复同步、磁盘空间检查和JSON Lines操作日志。
- 增加SQLAlchemy完整元数据表及Alembic初始迁移；XML导入提供对象级语义差异，XML导出纳入任务和永久修订。
- 分别使用AutoCAD 2016和2020通过插件加载、Handle回读、改名、插入、删除、重排、跨子集移动和25布局最大分组真实系统测试。
- 固化黄金项目54个DST/DWG、总字节数和逐文件哈希清单摘要，自动化测试会在解析前拒绝任何样本漂移。
- Web编辑器补齐图纸集名称、图纸集/图纸自定义属性和子集名称/排序编辑，并确保属性随受控命令提交。
- 将 Ruff 固化为 UV 开发依赖，并增加图纸集/图纸已有自定义属性往返测试。
- 新增 `docs/DST_MANAGER_MVP_DESIGN.md`，基于现有现代化重构方案建立DST Manager前期技术验证基线。
- 根据最终确认的 DM-ADR-001 至 DM-ADR-010 重写MVP设计，确定不使用SSO COM，采用 `DST → XML → DST` 与 `accoreconsole` 重建DWG布局的实现路径。
- 审计新增黄金样本 `sample/project1`：确认298张图、45个子集、45个主DWG、8个额外DWG，并把旧绝对路径重定位纳入MVP正式能力。
- 明确新增图纸既可复制已有布局，也可从DWG/DWT模板布局创建空白业务布局；支持插入、删除、重排和跨子集移动。
- 补充整批可恢复发布协议、永久修订目录、XML未知结构保留、双AutoCAD版本测试矩阵、阶段退出条件和可量化验收标准。
- 记录UtilityClass编解码、DWG字段刷新和XML兼容导入的验证边界；早期SSO COM探针结论仅保留为被否决方案，不进入MVP实现。
- 关闭混合拓扑、AutoCAD版本、DST写入方式、DWG同步范围、文件保护、XML契约、历史和锁处理等全部DM-ADR灰区。
- 补充DST Manager领域模型、SQLite元数据表、永久修订目录、本地Web/API骨架及同机CAD Worker边界。

## 2026-08-10

- 新增 `docs/MODERN_PYTHON_REFACTOR_ARCHITECTURE.md`，记录本地与云端双形态 Python 重构的确定性架构基线。
- 将云端 CAD 执行位置、Python/C# 边界、AutoCAD 版本、插件范围、界面形态、租户模型、文件安全和兼容级别登记为待用户确认的架构决策，避免隐含假设。
- 补充领域模型、端口与适配器、任务状态机、运行隔离、安全、可观测性、分层测试和分阶段迁移门槛。
- 根据用户决策将目标收敛为内网控制面、企业 Windows CAD Worker、统一 Web UI/CLI、自建账号、RustFS、SQLite/达梦双数据库契约，以及 AutoCAD 2016/2020 双版本插件构建。
- 明确 Python 3.12、FastAPI、Vue 3、SQLAlchemy 2、S3 适配器、HTTPS 拉取与数据库租约等技术基线，并登记本地离线、插件形态、权限、保留策略、容量、目标运行环境和 Excel 公式缓存等二级决策。
- 根据第二轮确认关闭离线模式、交互插件、RBAC、安全边界、保留期限、容量和部署平台决策；将 DM8 实例验证设为生产准入门槛。
- 只读分析五个真实 Excel 输入样本，将输入重构为工程表单、图纸分组数据网格、版本化字典/扩展字段、不可变修订和 Excel 兼容桥，并把剩余录入交互登记为 ADR-019。
- 确认多专业/分册工程、Excel 兼容桥、扩展字段、多人乐观锁编辑、项目管理员审批、自动编号、RustFS 资产与成果交付、高密度数据网格；补充稳定图纸 UUID 和可审计插入/删除机制。
- 确认草稿插入/删除自动紧凑重排，正式修订保持不可变，新修订生成图号变更映射并由项目管理员确认。
- 定稿数据库实体、HTTP API、RBAC、错误码、指标与容量基线、全部插件迁移矩阵、DST Windows Worker 边界、Linux Compose/Windows Worker 部署、CI/CD、生命周期、回滚和现有能力追踪矩阵。
- 只读核对本机 RustFS 开发容器为单实例本地卷且当前健康检查失败，将独立备份、恢复演练和 RPO/RTO 设为生产准入条件。
- 关闭最终灾备与本地身份决策：离线模式使用 Windows 隐式身份和一次性浏览器令牌；数据库/审计 RPO 15分钟、对象 RPO 1小时、控制面 RTO 4小时、历史文件 RTO 24小时；独立内网备份位置作为生产部署前置条件后定。
- 将现代化 Python 重构架构文档标记为最终定稿，ADR-001 至 ADR-020 全部关闭。

## 2026-07-15

- 新增 `docs/TRANSFORM_MATRIX_ANALYSIS.md`，结合 Autodesk 官方 `Matrix3d`、WCS/UCS、ADETRANSFORM 和 Map 3D 坐标转换说明，分析 `Transform` 插件的四参数矩阵推导、正反向可逆性、默认参数往返误差、Z 坐标影响、适用边界、运行风险、重构方向和测试矩阵。
- 在 `README.md` 增加 Transform 插件矩阵运算准确性分析文档入口。
- 本次仅新增和更新文档，未修改 Transform 插件源码、配置、项目文件或 DLL。
- 新增 `docs/UTILITYCLASS_DST_XML_ANALYSIS.md`，整理 `UtilityClass.DstViewer` 的 DST/XML 查表转换算法、四个公共接口、XML 序列化行为、PowerShell 集成边界、异常与性能特征、维护风险、重构方向和测试矩阵。
- 在 `README.md` 增加 UtilityClass DST/XML 转换分析文档入口。
- 本次仅新增和更新文档，未修改 PowerShell、C# 源码、项目配置或仓库 DLL。
- 新增 `docs/AUTOCAD_2025_PLUS_MIGRATION_ANALYSIS.md`，分析 AutoCAD 2025/2026 的 .NET 8、AutoCAD 2027 的 .NET 10 迁移边界，以及 4 个插件项目的构建结构、版本化部署、PowerShell 兼容、测试矩阵、风险优先级和推荐实施顺序。
- 在 `README.md` 增加 AutoCAD 2025 及以上版本迁移分析文档入口。
- 本次迁移工作仅新增和更新文档，未修改插件源码、项目配置或仓库 DLL。
- 新增 `docs/PLUGIN_DEVELOPMENT.md`，完整整理 `plugin/` 下 4 个 C# 项目的技术基线、源码结构、AutoCAD 命令、公共 API、配置和持久化契约、主程序集成、构建部署、测试矩阵、已知问题及接手优先级。
- 在 `README.md` 和 `docs/DEVELOPMENT.md` 增加插件开发文档入口，并将 AutoCAD 升级说明更新为当前已有可追溯源码的状态。
- 根据 `Ainsert` 源码修订 `docs/PYTHON_REFACTOR_ASSESSMENT.md`，明确其“向所有图纸布局原点附着同一外参”的实际语义及 COM 替换验证要求。
- 验证 4 个插件项目均可使用 Visual Studio 2022 的 64 位 MSBuild 以 Debug 配置构建；构建输出仅写入系统临时目录，未替换仓库 DLL。
- 新增 `README.md`，说明项目用途、当前接手状态、启动方式和主要入口。
- 新增 `docs/DEVELOPMENT.md`，整理系统架构、运行流程、Excel 输入契约、配置项、模板规则、关键函数、依赖、故障定位、验证方法、扩展手册和技术债。
- 新增 `docs/PYTHON_REFACTOR_ASSESSMENT.md`，记录 Python/pyautocad 重构可行性、功能映射、收益与风险、目标架构、迁移阶段、工作量和验收指标。
- 在 `README.md` 增加 Python/pyautocad 重构评估文档入口。
- 本次仅新增文档，未修改 PowerShell、配置、Excel、DWG 或 DLL。
