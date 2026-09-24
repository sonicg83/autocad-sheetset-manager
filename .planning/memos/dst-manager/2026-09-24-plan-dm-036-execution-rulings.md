# PLAN-DM-036 执行期间的裁决记录

日期：2026-09-24

状态：记录（来源 PLAN-DM-036 执行台账；台账工作区已按流程删除，此处为持久记录）

关联：`PLAN-DM-036`、`PLAN-DM-037`、`SPEC-DM-017`、`SPEC-DM-018`

## 说明

本文件是 PLAN-DM-036 执行期间控制方对计划缺陷、复核发现与跨任务接口冲突作出的全部裁决（30 条），以及各任务复核延后的 Minor 清单（65 条，详版见 [残差项](../todos/dst-manager/2026-09-24-plan-dm-036-deferred-minors.md)）。每条裁决末尾附「代价（若错）」，便于后续计划复核这些决定。

## 一、裁决（按作出顺序）

- Pre-flight Ruling: `CreationPlan` 必须携带 `target_path`（最终目录的完整路径）——T5 的 `build_minimal_acsm` 需要由它取 `Path(target_path).name` 写入 `AcSmSheetSet.Name`，T4 的内容摘要也需要它；SPEC-DM-018 §3.2 要求图纸集名称取最终目录名。代价（若错）：T5 需从别处传入目录名，接口小改。
- Pre-flight Ruling: `CreationImportResult.value` 使用专用值对象（`target_path`、`sheetset_values`、`groups: tuple[CreationGroupInput, ...]`），不是完整 `CreationDraft`——T2 明确「结果只返回完整最终路径、sheetset 普通值、按行序排列的图纸组……不直接写草稿」，草稿身份/修订由 T4 应用层在一次性保存时补。代价（若错）：T4 导入编排多一次字段搬运。
- Pre-flight Ruling: 创建专用发布入口按 Interfaces 的 `ProjectPublisher.publish_new_project(candidate, target, job_id, attempt) -> PublishedProject` 实现；T6 Step 1 测试里的模块级 `publish_candidate(candidate, target, fault_injector)` 是对发布器的示意调用，实现时以 Interfaces 签名为准并在测试中按新签名调用（故障注入作为显式参数保留）。代价（若错）：测试调用点需改名。
- Pre-flight Ruling: T7 需在应用层暴露 `finish_creation(...)`（测试直接调用）作为「发布成功 → 登记工作区与初始修订」的回调，即使 Produces 段未列名。代价（若错）：命名不同，测试随之调整。
- Pre-flight Ruling: `application/service.py` 只允许增加装配与转发；创建相关工作区登记逻辑放入同层独立模块（T7），保持入口类在 AGENTS.md 的 500 行/15 公共方法软上限内。代价（若错）：入口类多几十行，需后续拆分。
- Pre-flight Ruling: 各任务按序串行执行并要求每任务在自己的提交里追加 `changelog.md` 条目——避免同文件并行冲突。代价（若错）：无，仅记录位置。
- Pre-flight Ruling: 子代理模型作用域仅允许 `opencode-go/deepseek-v4.1-flash`（尝试 `opencode/claude-sonnet-4-6` 被拒），故本计划所有实现者/审查者使用同一模型；「新上下文」收益成立，跨模型能力分层收益未取得。代价（若错）：复杂任务缺少更强模型兜底，靠复核与裁决弥补。
- Task 1: ruling: 复核的 5 条 ⚠️ 均判定为「归属后续任务而非本任务缺口」——`step` 常量由 Task 4/8 复用；`CREATION_*` 错误码登记归 Task 4；「已发布且依赖可用」过滤归 Task 4；缺键/图名/张数/枚举门禁归 Task 3 预览诊断（Global Constraints 明确 `required` 只在预览/执行强制）。代价（若错）：门禁落到错误任务上，需在最终复核再抓一次。
- Task 2: ruling: 复核的 3 条 ⚠️ 逐条裁定——(1) `Sheet` 表空单元格记为显式空串、不回填标准默认值：单元格存在即键存在，符合「完整提供键」与「显式空串 ≠ 缺键」契约，required/枚举门禁交给 Task 3 预览报错（代价若错：用户在 XLSX 留空会拿到必填错误而非默认值，错误可见可改）；(2) 生成端列数护栏列为 deferred minor（>123 个 sheet 属性在本产品范围内不现实，代价若错：巨大标准导出的模板在导入端被明确拒绝）；(3) 图名非法字符归属 Task 3/6 的 DWG 命名门禁，非本任务缺口。
- Task 3: ruling: 复核 3 条 ⚠️ 裁定——(1) 空草稿 `groups == ()` 不阻断，判断归 Task 4 预览入口（Global Constraints「预览不启动 AutoCAD」+ SPEC-DM-018 §6.2 只要求无阻断错误才可点击），故 Task 4 必须显式阻断空组草稿；(2) `plan_digest` 含 `draft.id` 属「绑定草稿身份」口径，Task 4 合成 `preview_digest` 时再叠加标准文档/设置/资产哈希/目标状态，符合 SPEC-DM-018 §6.2；(3) `creation_planning.__all__` 未再导出 `plan_digest`/`target_file_path` 非缺口——下游按 `plan.digest` 属性消费，Task 4 不得从 `domain.creation_planning` 直接 import 这两个名字。代价（若错）：Task 4 需补一处导入或加一条门禁。
- Task 4: ruling: 自陈偏差全部接受——`interfaces/responses.py` 不动（其末类已超软上限，契约放新文件更合规）；导入「先解析后保存」使「修订过期 + 工作簿非法」返回 422（修订过期 + 工作簿合法仍 409 且零变更），符合「失败时草稿零变化」的更高优先约束；新增 `python-multipart` 依赖为 FastAPI `UploadFile` 在路由注册期必需。代价（若错）：422/409 的优先级与前端提示文案需微调。
- Task 4: ruling: 冻结打包未验证 `python-multipart` 的 hiddenimports（`packaging/dst-manager.spec:32`）与 `CREATION_GROUPS_EMPTY` 等诊断码的中英文键（Task 7/9 需补）——登记为后续任务输入，不阻断本任务。代价（若错）：frozen 态上传失败，需补一次打包修复。
- Task 5: Ruling: 实现者发现 `CreationPlan` 缺执行链必需输入（标准身份、property_id→属性名映射、编号策略/后缀选项），无法满足 `build_minimal_acsm(plan)` 单参数契约。裁定采用方案 A——`CreationPlan` 纯追加冻结字段 `settings`（`CreationSettings`），由 `create_creation_plan` 填充；理由：计划是执行链唯一权威输入载体（Task 5/6/7 的 `stage`/`run` 只传 plan），B 会破坏 brief 逐字测试与 Task 6 契约，C 违反 SPEC-DM-017 §3.2。代价（若错）：Task 3 的两个领域文件被追加修改，其原复核范围未覆盖该追加，由 Task 5 复核与最终整分支复核兜住。
- Task 5: Ruling: 候选 DST 文件名常量取 `图纸集数据文件.dst`（证据：legacy `$dstname` 与 `sample/project1|2/图纸集数据文件.dst`）；`DSTManager.StandardOptions` 取版本化 JSON（`version:1` + numbering + suffix，键序稳定）；`DSTManager.Standard` 值为 `<standard_id>@<version>`。代价（若错）：后续读取方需迁移该保留属性格式（有 version 字段可迁移）。
- Task 5: ruling: 报告中的「真实 2016/2020 Core Console 冒烟」属**未验证声明**（复核者无法复现，全程用替身执行器），不作为资格门禁通过；官方图纸集管理器验收归 Task 7。代价（若错）：若真实冒烟实为失败，Task 7 的真实测试会暴露。
- Task 5: ruling: 控制方先前推测 `packaging/dst-manager.spec` 改动是补 `python-multipart` hiddenimports，经复核**与事实不符**——该 diff 只新增骨架资产 datas 条目（本任务新建资源文件后既有守护测试会要求登记），`python-multipart` 打包缺口仍未处理，留待打包相关任务。代价（若错）：frozen 态上传功能可能仍缺失。
- Task 5: ruling: `settings.properties` 落地为 `tuple[CreationProperty]`（含 scope）而非裁决字面「property_id→属性名映射」——信息是超集且 scope 是 DST `Flags` 写入的必需输入，判定为有据收敛；下游必须按 tuple 读取。代价（若错）：Task 6/7 消费方按映射读取会失败。
- Task 5: ruling: 实现者把新增 19 个创建错误码的登记推迟到 Task 6 —— 接受（本任务无 HTTP 入口），Task 6 必须与 `CREATION_PREVIEW_STALE` 同批登记 message_catalog 与中英文 errors.ts。代价（若错）：用户界面显示裸码。
- Task 6: ruling: `JobResponse.workspace_id` 改为可空并新增可选 `creation_draft_id` —— 接受（否则创建任务详情 500，违反「无工作区时仍能记录状态」）；已核对 openapi/schema 与前端无消费点退化。代价（若错）：既有普通任务响应契约面变大。
- Task 6: ruling: 新增 `application/creation_execution.py`、`infrastructure/filesystem/project_publish_types.py` 与 `web/src/i18n/locales/*/creation.ts`（诊断子域 39 键）超出 brief 文件清单 —— 接受为容量拆分与错误码登记义务；**Task 8 必须改为追加界面文案键，不得重建该文件**。代价（若错）：Task 8 覆盖既有诊断键。
- Task 6: ruling: 四轮修复后才收敛，判定根因是「启动路径必须容忍不可信输入」这条不变量最初只被逐形态实现；已在台账固化该口径（未来同类改动按类收口并穷举）。代价（若错）：无。
- Task 7: ruling: brief 文件清单标 Modify 的 `infrastructure/filesystem/workspace.py` 未改动 —— 接受（既有 `write_workspace_metadata` 已满足原子写入与字段需求，不新增第二套元数据格式）。代价（若错）：无。
- Task 7: ruling: 初始修订的 `kind="creation"` 采用「白名单只允许 `operation`」的 fail-closed 门禁，而非在 API/UI 层过滤 —— 理由：门禁必须在预览与执行两条路径都成立，UI 过滤无法覆盖直接调用。代价（若错）：未来出现第三种「无前序状态」的修订类型时需同步调整白名单。
- Task 8: ruling: `CreationApi.seed` 构造期同步注入端口 —— 接受（生产组合实现不提供该字段，无死代码；是满足 plan 逐字用例调用形状的唯一方式）。代价（若错）：测试端口形状与生产初始化路径不同构，需补 `adoptDraft` 单测（已登记为 minor）。
- Task 8: ruling: 改动 `useStartNavigation.ts` 与 `StandardsView.vue`（不在 brief Files 列表）—— 接受为最小必要（不传递标准身份无法满足「标准详情固定版本并直接进入第二阶段」，两处合计 26 行只做身份转发）。代价（若错）：身份传递面多一处。
- Task 8: ruling: 末列 ↑/↓/✕ 采用 Unicode 字形并登记 `check:ui` 例外 —— 接受（SPEC-DM-018 §4.2 明文要求沿用图纸目录插件视觉，既有先例 `ColumnEditor.vue` 同形式同登记）。代价（若错）：图标门禁例外多 3 条（已带到期条件）。
- Task 9: ruling: 创建任务进度在向导内用同一 `JobStatusPanel` 呈现（方案 A），而非让全局浮层在无工作区时渲染（方案 B）——理由：`TaskOverlay` 受 `hasWorkspace` 门控是既有设计，B 会把创建任务的 NULL `workspace_id` 语义纠缠进 `useJobMonitor` 与普通工作区渲染条件；A 把风险限制在新增创建专用监视钩子。代价（若错）：创建期进度不在全局浮层位置呈现，需在 README/计划记录该收敛（已记录）。
- Task 9: ruling: 计划 `status` 置 `active` 而非 `completed` —— 理由：计划 Step 5 明文要求「环境不可用时标明缺口，不能把 Plan 标为 completed」，而「官方图纸集管理器界面打开性」是唯一未做的人工验收项（无法在 Core Console 内自动化）；机器可验证门禁（含真实 2016/2020 系统测试）均已通过并记录。代价（若错）：计划停在 active 需用户确认后再置 completed。
- Final: Ruling: 复核者的 10 条 Declined-to-judge 逐条采纳（含用户无关提交 823f46e 排除、官方 SSM 界面人工验收归计划残余门、`AcSmSubset.Name` 只写图名、frozen 打包 python-multipart 无法本机验证、非 CREATION_* 诊断英文回退后端中文、StandardStore 其它调用点、useSettings 快照观察面、创建进度不进全局浮层、创建与工作区双命名引擎并存、迁移不可变清单不含 0007）——代价（若错）：其中「frozen 打包未验证」与「StandardStore 其它调用点 500」是两条真实残余风险，已登记到 todos。
- Final: Ruling: 修复波的两条自陈扩展（`StandardStore._read_document` 加 `UnicodeDecodeError`；`finalPathEmpty` 文案值变更）——接受，理由：前者是让「非 UTF-8」走到 200 的最小必要改动且仅影响 `list()`，后者键名/键数不变、无断言引用旧文案。代价（若错）：标准列表对损坏文档的展示从报错变为「列出但名为空」。

## 二、复核延后的 Minor（一句话索引）

- Task 1: minor (deferred): `infrastructure/creation_drafts.py:143` 把 `OSError` 一并当作内容损坏并隔离；EDR 瞬时拒绝时可抛原始 OSError 或误移完好草稿，建议只对解析类异常隔离。
- Task 1: minor (deferred): `delete` 的 docstring 与实现不符，隔离文件落在 `<root>/` 且无清理路径。
- Task 1: minor (deferred): 磁盘上身份格式非法时返回 `STANDARD_IDENTITY_INVALID`(422) 而非 `CREATION_STANDARD_MISSING`(404)。
- Task 1: minor (deferred): 仓储不强制「新出现的 `created_order` 必须大于既有最大值」，是否由 Task 4/8 分配 `max+1` 需确认。
- Task 1: minor (deferred): `CreationAssetOption.kind` 未收成 `Literal["base-template","layout-template"]`；Task 4 需按包内 ID 查表，绝不把 `*_asset_id` 当路径。
- Task 2: minor (deferred): 图名/文本属性保留首尾空白入库，尾随空格图名要到 DWG 命名阶段才报错且提示与「图名」无关联。
- Task 2: minor (deferred): 生成端无列数/行数护栏，而导入端有 `MAX_SHEET_COLUMNS = 128`；>123 个普通 sheet 属性的标准会生成自身导不进来的模板。
- Task 2: minor (deferred): `read_creation_workbook` 对工作表数量无上限，且在任何协议判定前展开每张子限规模工作表的网格，恶意包可推高内存。
- Task 2: minor (deferred): `_CreationLists` 候选值表缺失不报错（与「DV 不是信任边界」一致，但模块文档未写明）。
- Task 2: minor (deferred): 三处自反断言（`assert diagnostic(x, CODE).code`）不增加信息；缺一条 sheetset 作用域非法枚举用例；`test_imported_value_matches_ui_input_shape` 仅用字面量断言，待 Task 4 两条路径齐备后补真实对比。
- Task 2: minor (deferred): 空 `Sheet` 表（0 组）被判合法导入，全量覆盖下会把草稿清成 0 组。
- Task 3: minor (deferred): 零填充/顺序编号表达式在 `creation_planning.py:142,144` 与 `editing.py:413,416` 各写一遍（可判 plan-mandated），建议在 `sheet_numbering.py` 增 `format_sheet_number`/`zero_fill_number` 共享。
- Task 3: minor (deferred): `PropertyCellRow` 缺 `title`，"…" 模态需由消费者按索引对齐取 `group.sheets[i].title`；建议加字段。
- Task 3: minor (deferred): 预览投影把「派生失败」与显式空串显示为同形（`creation_planning.py:356` 的 `.get(..., "")`）；若 Task 4 要区分「（空）…」与「未计算」需额外标记。
- Task 3: minor (deferred): 标题后缀退化诊断无 `group_id`（`creation_planning.py:235`），与「错误可定位到图纸组行」不完全对齐。
- Task 3: minor (deferred): DWG 碰撞用例与重复图名纠缠（同一夹具同时触发 `CREATION_GROUP_TITLE_DUPLICATE`），未隔离命名冲突路径。
- Task 3: minor (deferred): `changelog.md` 中 Task 3 条目日期为 2026-09-23 却排在 2026-09-24 条目之上，文件不再严格倒序（待收尾统一）。
- Task 4: minor (deferred): 已发布标准文档损坏时候选列表会 500（`creation_assets.py:183` 只捕获 `StandardSchemaError`，`store.get` 的 `json.loads`/`read_text` 未受保护），与该端点 docstring「给出稳定原因，不冒泡 500」冲突；审查者提示可按仓库「不得 500」口径升级。
- Task 4: minor (deferred): 上传体积先 `await file.read()` 全量入内存（`creation_api.py:126`）后才比对 `MAX_CREATION_XLSX_BYTES`，未防超大输入占内存。
- Task 4: minor (deferred): `creation.py:274` 的 `any(path.iterdir())` 未处理 `OSError`，不可读目标目录（如受保护系统目录）会 500 而不是稳定阻断码。
- Task 4: minor (deferred): `_manifests` 与 `standard_api._manifests` 逐字重复（`creation_api.py:144` vs `standard_api.py:162`）。
- Task 4: minor (deferred): 候选列表对每个标准的每个声明资产做全文件 SHA-256（`creation_assets.py:187/277`），列表只需存在性，标准多时 I/O 放大。
- Task 4: minor (deferred): `step` 白名单违规返回 FastAPI 校验错误形态而非可本地化码（与 `interfaces/contracts.py:28` 先例一致）。
- Task 4: minor (deferred): PUT 保存不校验 `target_path` 形状、导入路径校验，两个入口口径不同。
- Task 5: minor (deferred): 占位 Handle（16 位全 F）不被 `AcsmDocument.validate()` 识别为占位（`document.py:950` 只认 `"0"`），因此中间态 `validate()==[]`；补偿门（`pending_layout_handles` + `apply_layout_handles` + 写盘前 `pending == {}` + 往返比对）齐备，建议把新占位纳入 validate 或在 docstring 明示「非可发布态」。
- Task 5: minor (deferred): `_write_candidate_dst` 先写盘后校验，校验失败会在隔离 attempt 内残留候选形文件，与模块自述「不产出半成品候选」不一致；**Task 6 必须按显式清单恢复，不得按目录扫描 attempt 暂存区**。
- Task 5: minor (deferred): 新增 SCR 生成与请求门禁（`render_create_layouts`/`LayoutCreationRequest`）零直接测试，而同文件既有惯例是每个 renderer 单测；该 seam 正对「不得把用户文本拼进 SCR」的全局约束。
- Task 5: minor (deferred): `AcSmSimpleFileReferece` 的文档结论不精确（真实工程样本 `sheetset-fail.xml` 含该节点，黄金样本不含），应把措辞收窄并留作 Task 7 待验项。
- Task 5: minor (deferred): `stage` 不拒绝复用已存在的 attempt 目录（`creation_job.py:156`），重复 stage 同一 attempt 会静默覆盖上一 attempt 产物；「重试使用新 attempt」目前只由调用方保证。
- Task 5: minor (deferred): DST 内写 `resolve()` 后路径而往返比对用未 resolve 的计划路径（`document.py:790` vs `creation_job.py:449`），junction/符号链接前缀下会误报 `CREATION_ROUNDTRIP_MISMATCH`。
- Task 5: minor (deferred): `tests/integration/test_creation_job.py` 断言机器绝对路径 `r"C:\Projects\新建项目"` 不存在，若本机恰好存在该目录会失败（违背「测试不得依赖遗留文件」）。
- Task 5: minor (deferred): `tests/integration/test_creation_job.py` 547 行超测试文件软上限。
- Task 6: minor (deferred): 已提交日志 `revision_dir` 只校验是字符串，`""` 会把归档写进当前目录；加「必须位于 creation-jobs 根内」会改既有语义，需裁决。
- Task 6: minor (deferred): `lock_path` 含 NUL 时 ctypes 截断导致取锁不互斥（共享原语既有行为）。
- Task 6: minor (deferred): `root.exists()` 的权限类 `OSError`（EACCES）仍会逃出启动路径（环境类，本轮明确不修）。
- Task 6: minor (deferred): 工作区侧发布恢复同一缺陷类未修（`_recover_locked` 的 `json.loads(read_text)` 无守护、`_list_committed_operations_locked` 元组漏 `UnicodeDecodeError`）——控制方裁定不属本计划范围，需独立修复轮。
- Task 6: minor (deferred): 发布路径 `project_publisher.py:169` 回滚失败处理器内的 `write_journal_best_effort` 是同一模式，但日志由发布器自身生成、且不经过 `service.py` 启动路径。
- Task 6: minor (deferred): `atomic.py:88` 只在 `OSError` 时清理临时文件，`UnicodeEncodeError` 会留下 0 字节 `.tmp`（不匹配恢复 glob，无功能影响）。
- Task 6: minor (deferred): 锁竞争 30s 超时抛 `WorkspaceTransactionBusyError`，被 `CreationJobRunner.run` 兜底成 `NEEDS_REVIEW` + 未登记码（界面显示原始类名）且 `retry_job` 不接受该状态；既有工作区路径映射为 `BLOCKED_FILE_LOCK`。
- Task 6: minor (deferred): 暂存阶段未知异常落 `NEEDS_REVIEW`，与 `CadJobRunner` 同类异常落 `FAILED` 不一致。
- Task 6: minor (deferred): SSE 服务端终止集合缺 `NEEDS_REVIEW`（`interfaces/api.py:421`），前端自行关流；建议 Task 9 收口。
- Task 6: minor (deferred): `creation_job.py` 由 496 增至约 594 行、`database.py` 由 796 增至 871 行，均超软上限（两者都在 brief 文件清单内，属 plan-mandated）。
- Task 6: minor (deferred): 新增测试 `test_recovery_contains_a_rollback_journal_with_a_lone_surrogate` 的两个参数化 id 走同一路径，自述与实际不符（修复覆盖仍成立）。
- Task 7: minor (deferred): 标准快照 `_restore_snapshot` 用 `copytree`，中断会留半份快照且补登记不重做；建议后续改原子换名。
- Task 7: minor (deferred): 初始修订仍列在 `/api/revisions` 与界面历史（有意保留，仅不可作恢复来源）。
- Task 7: minor (deferred): `_resume_committed_creation` 的 `outcome.published is None` 分支当前不可达，若将来可达会把任务永久留在非终态且无诊断。
- Task 7: minor (deferred): `_isolate_registration_failure` 忽略 `finalize_job_terminal` 返回值，租约被拒时仍向调用方报 `NEEDS_REVIEW`。
- Task 7: minor (deferred): 容量超限——`test_created_project_opens.py` 717 行、`creation_job.py` 608 行、`database.py` 884 行（均为 plan-mandated 文件）。
- Task 7: minor (deferred): 修复轮新增的测试内第二个 `create_app` 未 dispose engine（仅测试资源）。
- Task 8: minor (deferred): 409 `CREATION_DRAFT_CONFLICT` 后不刷新 `state.revision`，重试会永久 409；`restart` 也失败时用户既不能保存也不能离开，唯一出口是刷新页面（刷新会用服务端草稿覆盖未落盘输入）。建议后续补「冲突后按新修订重试或显式强制离开」。
- Task 8: minor (deferred): `GroupsStep.vue:7-8,60-63` 注释写「四个控件」，实际接线为五个。
- Task 8: minor (deferred): 标准详情入口绕过可用性过滤（候选缺失时合成 `available: true`），不可用标准仍能建草稿，用户到第三阶段才看到原因。
- Task 8: minor (deferred): 10 个未使用语言键（`standard.unavailable/reasons/use/source/*`、`wizard.currentStep/doneStep`、`groups.columnSelect`、`groups.batchApplied`）。
- Task 8: minor (deferred): `useStartNavigation.test.ts` 用例名与本轮改动脱节；`createSheetsetIdentity` 无单测。
- Task 8: minor (deferred): `store.ts` seed 分支绕过 `adoptDraft`（生产无 seed，但 adoptDraft/默认值合并路径无单测）。
- Task 8: minor (deferred): 详情入口会把草稿阶段指针改写为 `project`；`goToStep` 每次保存会使旧预览失效（Task 9 需在预览前保存/重算）。
- Task 8: minor (deferred): 张数输入清空后回落为 `0`（无法表达空中间态）。
- Task 8: minor (deferred): 重复图名前端用 `toLocaleLowerCase()` 而后端用 `casefold()`（仅影响即时提示，后端为权威门禁）；`types.ts` 末尾悬挂一段 `CreationStore` 的 JSDoc。
- Task 9: minor (deferred): 创建任务订阅无 `onUnmounted` 清理；执行中返回欢迎页后 EventSource 仍开着，终态到达会继续 `emit("created")`（与报告所述「卸载后不再订阅」不符）。
- Task 9: minor (deferred): `SUCCEEDED` 但 `workspace_id` 为空时静默无动作，向导会停在「任务已成功」且永不进入工作区。
- Task 9: minor (deferred): `useCreationJob.ts` 是第二套 SSE/轮询订阅实现（面板与终态集合已单一来源），且无单测覆盖轮询回退与 `workspace_id` 缺失分支。
- Task 9: minor (deferred): 「全部检查通过」徽章由前端 `severity==="error"` 计数决定，而按钮门禁用后端 `executable`——今天等价，未来后端引入新严重级别会不一致。
- Task 9: minor (deferred): `LAYOUT_NAME_INVALID`/`DUPLICATE_LAYOUT_NAME` 带 `group_id` 不带 `property_id`，评审页会为这类「派生名冲突、无直接可编辑输入」的诊断渲染「返回修改第 N 项」并聚焦图名输入，与注释及 changelog 表述不符（base 版同分支顺序，非本轮引入）。
- Task 9: minor (deferred): `features/creation/store.ts` 509 行超 500 软上限、`CreationStore` 公共方法约 30 个超 15 软上限（预览逻辑已拆出 `previewSession.ts`）。
- Task 9: minor (deferred): 新增 2 个 previewModel 单测只有 GREEN 记录、无单独 RED 输出（两条 finding 的 RED 由 e2e 提供）。
