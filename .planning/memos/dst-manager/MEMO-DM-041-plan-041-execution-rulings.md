---
id: MEMO-DM-041
title: PLAN-DM-041 实施裁决与独立复核记录
status: accepted
document_kind: memo
owners:
  - dst-manager
created: 2026-09-25
updated: 2026-09-25
related:
  - PLAN-DM-041
  - SPEC-DM-019
  - SPEC-DM-016
  - PLAN-DM-040
---

# PLAN-DM-041 实施裁决与独立复核记录

本备忘是 [PLAN-DM-041](../../plans/dst-manager/PLAN-DM-041-standard-package-import-picker.md) 内联执行
过程中的裁决台账与独立复核结论的长期留档：执行期的 `.superpowers/sdd/` 工作区按流程在收口后删除，
故把其中仍有解释价值的裁决与延后项转存到这里。实施结果与命令证据见计划「实际验证」与 `changelog.md`。

## 一、任务完成线（含各自测试命令结果）

- Task 1: complete (commits 61156fc..006d2d4, tests: uv run ruff check . → All checks passed!)
- Task 2: complete (commits 006d2d4..6653cd9, tests: uv run pytest -q -p no:xdist -o addopts= tests/unit/test_drawing_standards.py tests/unit/test_standard_package.py tests/integration/test_standard_dst_import.py tests/unit/test_standard_store.py::test_list_reports_integer_versions_and_null_for_drafts tests/unit/test_standard_store.py::test_list_skips_residual_schema_version_one_directories tests/unit/test_standard_store.py::test_get_document_rejects_residual_schema_version_one tests/unit/test_standard_store.py::test_get_rejects_residual_schema_version_one tests/unit/test_standard_store.py::test_get_accepts_integer_and_segment_version tests/unit/test_standard_store.py::test_get_rejects_non_canonical_version_segment → 107 passed, 8 warnings in 2.53s)
- Task 3: complete (commits 6653cd9..87c717d, tests: uv run pytest -q -p no:xdist -o addopts= tests/unit/test_standard_store.py tests/integration/test_standard_api.py tests/unit/test_message_catalog.py → 190 passed, 45 warnings in 14.01s)
- Task 4: complete (commits 87c717d..6ba6af9, tests: uv run pytest -q -p no:xdist -o addopts= tests/unit/test_creation_drafts.py tests/unit/test_creation_xlsx_template.py tests/unit/test_creation_xlsx_import.py tests/integration/test_creation_api.py tests/integration/test_standard_api.py tests/unit/test_standard_service.py → 135 passed, 124 warnings in 33.63s)
- Task 5: complete (commits 6ba6af9..eaccf93, tests: uv run pytest -q -p no:xdist -o addopts= tests/unit/test_standard_import_previews.py tests/integration/test_standard_api.py tests/unit/test_message_catalog.py → 83 passed, 52 warnings in 14.88s)
- Task 6: complete (commits eaccf93..ee51402, tests: npx --prefix web vitest run src/components/standards/standardLibraryModel.test.ts src/features/standards/draftModel.test.ts src/features/standards/store.test.ts →    Duration  1.64s (transform 54%, import 34%, tests 8%, worker 5%))
- Task 7: complete (commits ee51402..3bb02d4, tests: npx --prefix web vitest run --root web src/components/standards/StandardImportDialog.test.ts src/api/shell.test.ts src/features/standards/store.test.ts →    Duration  2.33s (environment 56%, import 21%, tests 18%, transform 4%, worker 2%))
- Task 8: Ruling: 真实 Windows WebView2 G9 **未执行**（用户裁决），Task 8 的 G9 步骤保持未勾选、计划保持 active，并在计划「实际验证」与 SPEC-DM-016 证据目录写明恢复条件（装有 WebView2 的 Windows 桌面 + 任一 .dststandard）— 理由：计划明确「环境缺席时不得标记 completed」，而无桌面条件 — 代价：计划保持 active，G9 通过声明延后。
- Task 8: complete (commits 3bb02d4..85456f5, tests: uv run pytest -q -p no:xdist -o addopts= tests/integration/test_standard_api.py tests/integration/test_creation_api.py → 91 passed, 97 warnings in 29.26s)
- Task 8: complete (commits 3bb02d4..c17317a, tests: uv run pytest -q -p no:xdist -o addopts= tests/unit/test_standard_store.py tests/unit/test_standard_import_previews.py tests/unit/test_drawing_standards.py tests/unit/test_standard_package.py tests/unit/test_message_catalog.py tests/integration/test_standard_api.py → 304 passed, 57 warnings in 20.35s)

## 二、执行期裁决（Ruling）

每条格式为「结论 — 理由 — 代价」。

- Task 1: Ruling: Task 1 的 brief 未指定测试命令；记录的验证门禁取仓库 Python 基线 `uv run ruff check .`（退出码 0），另加一次性文档一致性扫描（YAML front matter 可解析、related/相对链接无失效）— 理由：本任务只改文档，无对应自动化用例，但完成契约仍要求真实命令输出 — 代价：若未来新增文档门禁测试，本任务需补跑。
- Task 2: Ruling: materialize_published_standard / materialize_published_document 接受**草稿文档映射**（`StandardDraft.document`）而不是草稿实体 — 理由：发布时必须保留实现未识别的扩展键与键顺序（与 DST 未知节点不丢失同口径），实体化会重建文档而丢键；参数名写作 draft_document 并写入 docstring — 代价：若后续要求实体入参需加一个薄封装。
- Task 2: Ruling: 草稿与发布领域模型用「共享只读 mixin + 两个独立 dataclass」而不是 dataclass 继承（version 字段排序会触发 "non-default argument follows default argument"）— 理由：保持 DraftDrawingStandard/DrawingStandard 为真实不同类型且共享 find_property/references_to 等读取接口 — 代价：字段声明重复一次。
- Task 2: Ruling: 仓储发布全集（test_standard_store.py 29 例）与依赖发布的标准 API/创建链路用例在本任务中保持红，按计划留待 Task 3（版本分配）与 Task 4（创建与公开契约）转绿；本任务 GREEN 范围 = 计划点名的三个测试文件 + 新增仓储读用例（119 passed）— 理由：计划明确「仓储发布全集在 Task 3 改造后运行」且 publish() 处于显式过渡态 — 代价：Task 2 提交点测试套件不完整为绿。
- Task 2: Ruling: interfaces/standard_contracts.py 的版本类型在 Task 2 就改为 int/int|None — 理由：仓储已无字符串版本，若不同步修改，存在草稿时 GET /api/standards 会因 Pydantic 校验直接 500（功能中断，而非计划允许的阶段性类型红灯）— 代价：Task 4 的契约范围相应缩小到创建契约与路由整数化。
- Task 2: Ruling: 缓存器 package.py 与仓储 read_package 保留 Schema 侧精确错误码（不再统一改写为 STANDARD_PACKAGE_MANIFEST_INVALID）— 理由：SPEC-DM-019 §6 要求 read_package 返回 STANDARD_SCHEMA_VERSION_UNSUPPORTED；旧码随之不再产生 — 代价：依赖旧码的调用方需改用细分码。
- Task 3: Ruling: 在 Task 3 就移除「草稿按身份保存」入口（application.save_standard_by_identity、_draft_id_with_identity 与 PUT /api/standards/{standard_id}/{version}）— 理由：草稿不再携带版本后该路由在语义上无法成立，而 Task 3 的完成标准要求 test_standard_api.py 全绿，保留一个必定失败的路由既无法转绿也会把坏路径带进提交 — 代价：Task 4 的「移除不再成立的草稿按身份保存入口」简化为核对与回归，不再有代码改动。
- Task 3: Ruling: 仓储新增 STANDARD_PUBLISH_FAILED（计划只点名三个码）— 理由：os.replace 在身份目录非 FileExistsError 时失败必须以稳定码返回而不是 500，且失败路径已回滚草稿与空身份目录 — 代价：错误目录与中英文文案多一个键，若最终决定复用既有码需改码表与文案。
- Task 3: Ruling: 发布 warning 诊断由「仓储已校验的发布文档」确定性重算（application._published_diagnostics），而不是让 store.publish 返回诊断 — 理由：app 层不得在分配版本前把草稿当发布文档解析，而 PublishedStandard 结构不引入新字段可避免影响其他调用方 — 代价：发布成功路径多一次解析（确定性、无副作用）。
- Task 3: Ruling: 互斥锁文件位于 user_root/.standards.lock，并更新「非法草稿段不越界写入」用例显式忽略该文件 — 理由：文件锁需要稳定路径且不得落入 drafts/published 扫描根 — 代价：标准库根多一个隐藏制品，若后续要求根目录零制品需改用外部锁目录。
- Task 4: Ruling: 本任务的 RED 证据取「Task 2/3 后创建链路既有用例的 90 项失败」（失败原因恰为身份类型不符：草稿携带 version、standard_version 期望文本、目录拼接 int）而不是新写必定立即变绿的用例；另新增「非法绑定身份的规范化拒绝」参数化覆盖（@0/@01/@1.0.0/@../@-1/@/@1 空格/../@1），该保证已在 Task 2 的 pattern 改动中成立，此处只补 Claim 的用例密度并如实记录它不是 RED。
- Task 4: Ruling: XLSX 隐藏技术表的身份记录继续写规范十进制**文本**（写入与比对都取 str(version)），而不是改为数字单元格 — 理由：该表是文本记录协议（四列均按文本读取），改单元格类型会牵动读取器与既有模板；API JSON 才是必须为整数的契约 — 代价：同一身份在 JSON 是 int、在 XLSX 单元格是文本，需在 SPEC/指南口径下理解。
- Task 4: Ruling: 创建草稿持久化 schema 升为 2，旧文本版本创建草稿按损坏隔离而不做自动迁移 — 理由：用户已确认无已分发数据，且静默接受文本版本会与整数契约冲突 — 代价：本机旧创建草稿需重建。
- Task 4: Ruling: store._scan_published 只跳过「明确写有不受支持 schema_version」的目录，可解析失败/非 UTF-8 的损坏文档仍进列表（空名称）以保持 PLAN-DM-040 「损坏标准作为不可用候选上报」的回归 — 理由：SPEC-DM-019 §2.6 只规定 schema_version:1 残留目录跳过；让损坏标准静默消失会回退 F01 时代已修的行为 — 代价：列表可能包含名称为空的条目，由候选不可用原因承接。
- Task 4: Ruling: 按新契约移除不再成立的草稿按身份保存入口后，把「已发布标准不可原地修改」用例改为断言身份路由 405 + 草稿级路由 404 + 文档零变更 — 理由：写入入口结构性消失后 409 STANDARD_VERSION_IMMUTABLE 不再可达，保留一个仍会失败的断言没有意义 — 代价：STANDARD_VERSION_IMMUTABLE 码在本进程内不再产生（仍保留在码表中待后续清理或复用）。
- Task 5: Ruling: 预检的「非法包」判定只覆盖**无法安全读取**的包（非 zip、manifest 缺失/非法、路径逃逸、禁止扩展名、超限条目）→ 422；而发布门禁类问题（派生/命名诊断、资产缺失或越界、身份冲突、名称冲突）一律以 200 + can_import=false + 诊断呈现 — 理由：SPEC-DM-019 §4.3 只把路径/包读取问题定为 422，前一类用户可重新生成包修好，后一类是内容问题需要展示诊断 — 代价：确认阶段（绕过前端）仍会以 422/409 拒绝同一包，两条路径的错误码需要一起读。
- Task 5: Ruling: 幂等回执与凭证同寿命（内存、15 分钟），确认成功后凭证仍保留以便重复确认返回原结果；过期/取消后重复确认回到 404 — 理由：无需新持久化层，且重启后的重复确认本身必须失败 — 代价：进程重启后同一凭证的重复确认不再是「相同成功结果」。
- Task 5: Ruling: `ImportPreviewStore` 的过期判定改为 `record.is_expired(now)` 并由 store 传入注入时钟（RED 用例捕获了原实现直接用 `time.monotonic()` 而忽略注入时钟的缺陷）— 代价：无。
- Task 5: Ruling: 预检 `existing_versions` 只列**官方与用户库**中同 ID 的已发布整数版本（不含草稿），与 SPEC-DM-019 §4.3 一致 — 代价：无。
- Task 6: Ruling: 分组模型的 RED 用「新模型 + 旧实现」实测（9 例失败）而不是先写模型再补测试 — 理由：视图模型为纯函数且旧模型缺少 groupStandardList/formatStandardVersion、versionHistory 签名不同，直接以旧模块运行新用例即得到真实失败 — 代价：RED 与实现同批产出，需以该实测补足证据。
- Task 6: Ruling: 收起组用 v-show（元素保留在 DOM）→ E2E 断言改为可见性而不是元素计数 — 理由：v-if 会在收起时卸载行、丢失行内焦点与选中元素，而键盘收起只需隐藏 — 代价：DOM 中保留隐藏行，屏幕阅读器由 aria-expanded 承接。
- Task 6: Ruling: 前端导入仍调用已废弃的 POST /api/standards/import {path}（Task 5 起后端只接受 preview_id），本任务不修 — 理由：计划把「原生选择 + 唯一导入弹窗的预检/确认状态」整体归到 Task 7，提前改会与 Task 7 的弹窗状态机重叠 — 代价：Task 6 提交点上「导入标准包」在本机不可用（已存在的过渡态），Task 7 关闭。
- Task 6: Ruling: 导出文件名与详情版本历史均加 `v` 前缀展示、契约字段保持裸整数；版本历史条目增加原名（历史改名可见） — 理由：SPEC-DM-019 要求 UI 展示 v<n> 且历史版本显示其原名称 — 代价：既有 e2e 断言（"v2.0.0 · 用户"）改为 "v1 · 名称 · 用户"。
- Task 6: Ruling: `StandardLibraryPane` 的组头用 UiIcon（chevron-*）而不是 Unicode 字形 — 理由：check:ui 的 unicode-structure-icon 规则禁止字形充当结构图标 — 代价：无。
- Task 7: Ruling: 导入成功后弹窗**不自动关闭**（显示成功态，刷新/展开/定位在成功响应时立即完成，用户点「关闭」后收起）— 理由：计划要求「成功」为可验收状态且成功后刷新并定位，自动关闭会让成功状态永远不可见；同时保留「成功刷新并展开 ID 组、定位返回版本」的结果 — 代价：用户在弹窗打开期间即可看到背后列表已刷新（有意为之）。
- Task 7: Ruling: 收起的归集组状态提升到 StandardsView（collapsedGroups）以便导入成功后展开目标组 — 理由：只展开目标 ID 组需要页面级状态，弹窗无法访问面板内部状态 — 代价：面板新增 collapsedGroups prop 与 toggleGroup 事件。
- Task 7: Ruling: 预先冲突（can_import=false）时 preview_id/expires_at 为 null 且弹窗不显示确认可用；确认阶段失败（409/422）时清除本地预检并保留路径与错误 — 理由：后端已按此契约返回，前端只需忠实呈现；清除预检避免拿旧凭证反复重试 — 代价：确认失败后用户必须先重新预检。
- Task 7: Ruling: 组件新增 `StandardImportDialog.test.ts`（10 例）超出计划点名的测试文件 — 理由：状态机与防重复提交是本任务的核心风险，且计划允许「如抽出局部逻辑，测试与模块同层放置」— 代价：多一个前端单测文件。
- Task 7: Ruling: 该用例捕获了 `devFallback` 只在 open 变化时求值的缺陷（挂载即 open:true 时无壳降级不生效）→ 改为初值取 `!props.shellAvailable` 且 watch 加 immediate — 代价：无。
- Task 8: Ruling: 真实 Windows WebView2 G9 **未执行**（用户裁决），Task 8 的 G9 步骤保持未勾选、计划保持 active，并在计划「实际验证」与 SPEC-DM-016 证据目录写明恢复条件（装有 WebView2 的 Windows 桌面 + 任一 .dststandard）— 理由：计划明确「环境缺席时不得标记 completed」，而无桌面条件 — 代价：计划保持 active，G9 通过声明延后。
- Task 8: Ruling: 端到端闭环用例放在 tests/integration/test_standard_api.py（计划同时点名 test_creation_api.py）— 理由：闭环只用标准库与创建无关的标准端点，放在标准 API 测试里与既有夹具同源 — 代价：test_creation_api.py 本任务无改动。
- Task 8: Ruling: 闭环的最后一步（派生后重新发布）必须重新经 asset-files 端点把模板引入草稿目录 — 理由：派生只复制文档，受控资产不在新草稿目录内，发布门禁会以 STANDARD_ASSET_FILE_MISSING 阻断（真实约束，已在计划中如实记录）— 代价：闭环多两步，但证明派生不自动搬运资产这一既有边界。
- Task 8: Ruling: `.planning/plans/dst-manager/README.md` 中 PLAN-DM-039/PLAN-DM-029 的两条 `../../../memos/...` 链接为**先前已存在**的失效链接（HEAD 中即如此，git show 可证），本次未修 — 代价：索引仍有两条失效链接，建议后续单独修复。
- Final: Ruling: I4 选择改代码而不是改规范 — 理由：SPEC-DM-019 §4.3 是本轮 Task 1 建立并已被 accepted 的绑定权威，实现后改规范以就实现属于把权威降级 — 代价：与既有 asset-files 的 404 口径不再一致，需在规范 §6 明示区分。
- Final: Ruling: I5 选择「读取自愈」而不是评审建议的「暂存目录 + 复制资产 + 删除草稿」— 理由：后者把单次原子 rename 改成复制大量 DWG，引入更长窗口与新失败面；自愈只处理唯一的偏离字段且不弱化新提交的域层门禁 — 代价：草稿目录被外部人为塞入 version 时会被静默忽略而不是报错。

## 三、独立复核结论与处置

整分支（61156fc..85456f5）交独立 reviewer 子代理复核：0 Critical / 5 Important / 10 Minor + 6 项人工裁决点。
Important 全部在本轮修复并各留失败用例（详见 `changelog.md` 同日「固定复核修复轮」条目与计划同名小节）：

| 发现 | 处置 |
| --- | --- |
| 版本路径段超长触发 500 | 位数先于 `int()` 校验；域层与 API 各补用例 |
| 欢迎页直达导入弹窗无初始焦点 | 容器就绪后补聚焦；组件用例以 `attachTo` 断言 `document.activeElement` |
| 快照根无回收路径 | 构造时清空快照根；补用例 |
| 预检「源不存在」404 与规范 §4.3 的 422 冲突 | 改为 422，并登记全部导入与新增稳定码进 §6 |
| 发布硬崩溃窗口留下不可恢复草稿 | `get_draft` 自愈残留 `version`；补用例 |
| 取锁超时 / 导出损坏文档 / 预检遇不可读条目 / 创建候选遇仓储错误会 500 | 分别转 409 / 422 / 200+诊断 / 不可用候选；补用例 |

## 四、延后项（Minor，本次不修）

- 并发发布只覆盖同进程线程，跨进程 WorkspaceTransactionLock 路径无证据（评审 Review Focus 1a）。
- 确认阶段「不同 ID 同名」→ 409 与过期凭证 410 缺少 HTTP 层用例。
- import_package 把所有 os.replace 失败都报成 409 STANDARD_VERSION_EXISTS，未像 publish 那样区分 IO 失败。
- 导入弹窗错误区只显示 ApiError.message，未渲染后端诊断的 message_key；同 ID 已有版本直接拼 official/user 原始 token（中文界面里出现英文来源词）。
- StandardEditor.vue 仍比较 STANDARD_VERSION_IMMUTABLE（src/ 已无产生者）与 test_standard_api.py 模块 docstring 仍声明该 409。
- .planning/plans/dst-manager/README.md 中 PLAN-DM-039/PLAN-DM-029 两条 memos 链接在本次改动前即失效。
- 评审点出的「官方库人工策展出两个不同 ID 同名时首个占用者优先」在当前代码路径不可达；若将来允许人工策展需改成 owner 集合判定。

## 五、仍需人工裁决或执行的事项

1. **真实 Windows WebView2 G9 未执行**：步骤见 [SPEC-DM-016 证据目录 §五](../../../docs/dst-manager/specs/assets/SPEC-DM-016/README.md)；恢复条件为装有 WebView2 的 Windows 桌面 + 任一 `.dststandard`。执行前 PLAN-DM-041 保持 `active`。
2. **跨进程并发发布证据缺口**：现有并发用例只覆盖同进程线程（`_process_lock`），`WorkspaceTransactionLock` 的跨进程路径无实测；是否需要补真实双进程用例属范围裁决。
3. **官方库人工策展**：若未来允许官方源出现两个不同 ID 的同名标准，`published_name_owners` 的「首个占用者优先」需改为 owner 集合判定，否则其中一个自身再发新版会被误报名称冲突。
4. **PLAN-DM-040 的真实桌面 G9** 与本计划 G9 一并待验。

## 修订记录

- 2026-09-25 首版：转存 PLAN-DM-041 执行期裁决台账、任务完成线、独立复核结论与延后项。
