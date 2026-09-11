# 变更记录

## 2026-09-11（PLAN-DM-022 收尾登记：计划状态与实际验证）

- 计划状态：`.planning/plans/dst-manager/PLAN-DM-022-extension-card-baseline.md` 的元数据 `status` 由 `proposed` 改为 `completed`、`updated` 改为 2026-09-11；末尾「实际验证」章节由引导语改为真实登记（改动文件、commit、逐命令原始结果、跳过项与原因、G8 逐张比对结论与偏差裁决）。未改动计划正文条款、追踪矩阵、批次划分与风险章节。
- 批次 1（任务 1，`cdbe7a2`/`e93f482`/`2bfac5c`）：`settings-dialog` **18 passed**、`extensions-settings` **7 passed**、`check:i18n` **867 键**、`vue-tsc` 通过；控制器独立复跑 **25 passed**。
- 批次 2（任务 2/3，`addf04c`/`fa041de`/`4d67755`）：任务 2 → `extensions-settings` **8 passed**、`settings-dialog` **18 passed**、`check:i18n` **868 键**（+`diagnosticCode`）、`vue-tsc` 通过，控制器独立复跑 **26 passed**；任务 3 → `extensions-settings` **10 passed**、`sheet-catalog` + `extensions-navigation` **39 passed**、`check:i18n` **868**、`vue-tsc` 通过，控制器独立复跑 **49 passed**。已知偏离（裁决接受）：任务 2 改动 4 处既有合并断言（把 `v0.1.0 · 状态` 拆成版本/状态两条），超出计划明文授权，但为冻结件卡片布局的必然结果、语义覆盖经评审独立核查未削弱，不回退。
- 批次 3（任务 4，`c19149f`/`1de7b4e`/`a61ecd5`）：证据 spec **5 passed**、`extensions-settings` **10 passed**、`settings-dialog` **18 passed**（均 `--retries=0`）；`uv run ruff check .` → All checks passed；`uv run pytest -o addopts="" -q` → **1112 passed / 72 skipped**；`npm run check:i18n` → **868 键 / 9 域对称**；`npx vue-tsc -b --pretty false` → **exit 0**；`npm run build` → 通过。全量 e2e 连跑两次：第一次 **411 项：408 passed / 1 failed / 2 flaky**，第二次 **411 项：408 passed / 0 failed / 3 flaky**；唯一 failed 为 `properties-layout.spec.ts` 的四视口双主题覆盖用例（`page.goto` 超时，单跑 29.6s 已贴 30s 上限，`--workers=1` 单跑通过），与本次改动无关；两次 flaky 集合不同，均为 `playwright.config.ts` 已记录的 4 worker 下 dev server 启动抖动，重跑全部通过。
- G8 逐张比对结论：`g8-ext-01↔g4-07`、`g8-ext-02↔g4-08`、`g8-ext-03↔g4-10`、`g8-ext-04↔g4-11` 四对在结构、四层信息、状态徽标色、开关方向、诊断码字面上一致，差异属 Demo 固有（演示工具条、`配置修订 r7 · 模拟`、页脚模拟提示、`保存` 按钮近似色、数据字面与像素级行高微差）；**发现并修复 1 项须修缺陷**——生产诊断码用 `--color-text-muted` 而冻结件用 `--amber`（即生产 `--color-warning` 的近似映射），已在 `a61ecd5` 把 `.ext-diag` 对齐为 `var(--color-warning)` 并重取受影响的 4 张证据图（`g8-ext-02/03/04/05`；`g8-ext-01` 无诊断码、字节未变）；`g8-ext-05`（900×600）冻结件无对照图，不构成比对通过。范围偏离（裁决接受）：`g8-ext-03` 取景由 `scrollIntoViewIfNeeded()` 改为 `scrollIntoView({block:"center"})` + 视口内断言。
- 跳过项：未执行 `$env:DST_MANAGER_RUN_AUTOCAD=1` 的真实 AutoCAD 系统测试（本计划不涉及 CAD 侧，环境亦未启用）；首轮 G8（SC-01～SC-14）的 `production/` 截图仍未入库，该缺口在 `SPEC-DM-011` §8 保持未关闭（非本批引入）。收尾状态：G9 真实桌面验收仍待用户（`SPEC-DM-011` §8 的 G9 行为「未开始」），与 `PLAN-DM-018`「completed；真实桌面复验待用户」同口径。
- 文档同步：`.planning/plans/dst-manager/README.md` 第 17 行 PLAN-DM-022 摘要由「proposed，…待批准开工」改为与事实一致的 `completed`（见上）；第 18 行 PLAN-DM-021 摘要删去未经核实的「全量 e2e 有批次三遗留回归待修复」一句（本次会话两次全量 e2e 均为 0 failed，唯一 failed 为 `properties-layout.spec.ts` 超时抖动、`--workers=1` 单跑通过，与 PLAN-DM-021 无关），其余内容与状态未改，改动处未新增断言。

## 2026-09-11（合并前修复波：对齐扩展诊断码配色并校正 G8 证据表述）

- 修复（最终全分支评审唯一修复派发；Important + 1 条 Minor，控制器 Ruling 8）：①`web/src/components/settings/ExtensionCard.vue` 的 `.ext-diag` 由 `color:var(--color-text-muted)` 改为 `color:var(--color-warning)`——冻结 Demo 的 `.ext-diag` 用 `--amber`（浅 `#896000` / 深 `#eac784`），即生产 `--color-warning`（浅 `#946200` / 深 `#E0B15A`）的近似映射，冻结意图是「诊断码＝警告色调」；修复前生产实采浅色 `#6B7280` / 深色 `#8592A3` 是真实偏差（G8 门禁的存在意义即防生产背离冻结件）。只用一个 SPEC-DM-006 既有令牌，未新增令牌与全局 CSS，无契约影响。
- 证据重取：`cd web && npx playwright test tests/e2e/settings-extensions-production-evidence.spec.ts --reporter=line --retries=0` → **5 passed**（11.8s）。新产出的 5 张与 `docs/dst-manager/specs/assets/SPEC-DM-011/production/` 已入库件逐张 `cmp`：`g8-ext-01` 字节相同（该清单 1 条、无 `error_code`），`g8-ext-02`/`g8-ext-03`/`g8-ext-04`/`g8-ext-05` **4 张变化并替换**——原预期只 2 张变化，实际深色 `g8-ext-04` 与最小视口 `g8-ext-05` 的清单同样含诊断码，故一并变化。逐像素差分确认变化只落在诊断码文字行内（浅色 `#6B7280`→`#946200`、深色 `#8592A3`→`#E0B15A`，其余为文字抗锯齿混合色，无布局位移）；`production/` 下仍 5 张、尺寸仍为 1280×720 四张 + 900×600 一张。
- 文档：`SPEC-DM-011` §8 逐对裁决表按重取后的图复核——`g8-ext-02/03/04` 的「相同点」补记诊断码配色已对齐冻结件、「差异与分类」补记色值为令牌近似映射（非逐字节相同），证据段与 G8 门禁行标明 4 张已重取，表末结论由「未发现须修缺陷（无 `web/src/**` 改动）」改为「发现 1 项须修缺陷并已修复」的事实表述；§7 令牌表补 `--color-warning` ↔ Demo `--amber` 的映射。未重开 G4（冻结件未变，本次只把生产拉回冻结件）。
- 文档（口径校正，Minor）：同日上一条目「断言段标题与**首张**停用卡片在视口内」与代码不符——`settings-extensions-production-evidence.spec.ts` 断言的是 `demo.batch-plot`，按 `groupedList()` 顺序为「已停用」段第 3 张卡片；已改为与代码事实一致的表述。
- 验证（全部实跑，未改断言语义）：证据 spec **5 passed**、`web/tests/e2e/extensions-settings.spec.ts` **10 passed**、`web/tests/e2e/settings-dialog.spec.ts` **18 passed**（均 `--reporter=line --retries=0`）；`npm run check:i18n` → **868 键**；`npx vue-tsc -b --pretty false` → **exit 0**。本次只改一行 CSS 与文档文字，按评审约定未跑全量 e2e/pytest。

## 2026-09-11（交付扩展卡片基线实现与 G8 生产证据收口：统一滑动开关 + 四层信息卡片 + 按 enabled 分段）

- 交付范围：`PLAN-DM-022`「扩展卡片基线与布尔开关统一下沉」三批次全部落地（批次 1–3 的代码变更在各自提交时未写本次变更记录，本次一并登记，仅记为变更清单与守卫，不重述实现理由）。
- 批次 1（`2bfac5c` 统一设置中心布尔状态控件为滑动开关）：新增 `web/src/components/settings/BooleanSwitch.vue`（32 行，布尔状态控件唯一视觉语言，`button.switch[role="switch"]` + `aria-checked`，SPEC-DM-006 §6.3 / SPEC-DM-011 §3.3），`SettingsFormRow.vue` 的 bool 分支由原生 checkbox 改为复用该原语且仍走保存缓冲（不即时落盘）；`.switch` 类名让给新按钮，保住 `SettingsDialog.focusExtensionSwitch` 的选择器契约。
- 批次 2（`fa041de` 下沉扩展卡片承接四层信息）：新增 `ExtensionCard.vue`（72 行，四层信息顺序固定：名称+版本 / 描述 / 状态徽标+诊断码 / 开关+可见状态文字；卡片不可点击、不导航，唯一可聚焦元素是开关），`ExtensionsSection.vue` 退化为「取数 + 分段 + 列表」（89 → 77 行）；语言包中英同步新增 `settings.extensions.diagnosticCode`。
- 批次 2（`4d67755` 为扩展分区补按启用状态分段的增长机制）：条目 ≥6 条按服务端 `enabled` 分「已启用 / 已停用」两段（阈值 6 为 Spec 固定值，不引入可配置阈值/搜索），分组标题不显示计数。`SettingsDialog.vue` 全程未增长（仍 535 行，未越过本次计划的“不得增长”约束）。
- 批次 3（本次，G8 收口）：新增 `web/tests/e2e/settings-extensions-production-evidence.spec.ts` 5 例（`g8-ext-01` 1 条 / `g8-ext-02` 4 条多状态 / `g8-ext-03` 8 条分段边界 / `g8-ext-04` 4 条深色 / `g8-ext-05` 4 条最小视口），共用新提取的 `web/tests/e2e/fixtures/extensions.ts`（`extensionSummary`/`installExtensions` 从 `extensions-settings.spec.ts` **纯搬移**提取，原文件改 import，行为不变）；只打开设置对话框与切换分区，`/api/extensions` 全 mock，不保存任何设置。
- G8 证据入版本库：`docs/dst-manager/specs/assets/SPEC-DM-011/production/g8-ext-01～05`（1280×720 四张 + 900×600 一张），由证据 spec 从 `web/test-results/` 复制。**可读图**：逐张与冻结件 `g4-07`/`g4-08`/`g4-10`/`g4-11` 目视 + 像素采样比对——四层信息位置与层级、开关几何与轨道色（实采 `#2f5be0`）、徽标底色（实采 `#e7f4ec`）、四段状态色语言（可用/已停用/启动失败/不兼容）、诊断码字面、「已启用 + 启动失败」合法组合（开关方向取自 `enabled`、未由 `status` 反推）**均一致**；差异全部属 Demo 固有（演示工具条、`配置修订 r7 · 模拟`、页脚模拟提示、`保存` 按钮近似色 `#a1b5f1`、描述/版本号取自真实数据、卡片行高像素级微差），分类为「有意偏差（依据 SPEC-DM-011 §6 差异表 + MEMO-DM-024 已接受差异 D2/D3/顶部栏条）」，**未发现须修缺陷**，因此本任务未改任何 `web/src/**`、也未另立 memo。
- 证据修正（本任务自查）：`g8-ext-03` 按冻结件 `g4-10` 重新取景——原 `scrollIntoViewIfNeeded()` 只把「已停用」段标题贴到面板底边，拍不到该段任何卡片；改为 `scrollIntoView({block:"center"})` 并断言段标题与该段卡片 `demo.batch-plot`（按 `groupedList()` 顺序为「已停用」段第 3 张）在视口内，重取后取景与 g4-10 一致（上一段尾部 + 段标题 + 该段卡片）。`g8-ext-05`（最小视口）在冻结件里**没有对照图**，已在 §7/§8/§9 显式标注「不构成与冻结件的比对通过」，不冒充比对结论。
- 文档：`SPEC-DM-011` §7 补 `production/` 证据位置与 5 个文件名/冻结对照关系（含 `g8-ext-05` 无对照声明）、§8 G8 行由「通过（覆盖 SC-01～SC-14）」改为「第一轮 SC-01～SC-14 + 2026-09-11 重跑覆盖 SC-15/SC-16」并新增逐对裁决表（相同点/差异分类/依据）、§9 SC-15 与 SC-16 按实跑结论打勾并写明证据文件名与例外，元数据 `updated` 同步 2026-09-11。首轮 G8 的 `production/`（SC-01～SC-14 生产侧）仍未入库，该缺口保持未关闭并在 §8 写明。
- 验证（全部实跑）：`uv run ruff check .` → All checks passed；`uv run pytest -o addopts="" -q` → **1112 passed / 72 skipped**（本计划未改 Python 代码，作为交付基线兜底）；`web` 下 `npm run check:i18n` → **868 键 / 9 域对称**、`npx vue-tsc -b --pretty false` → **exit 0**、`npm run build` → **通过**；证据 spec 单跑 **5 passed**（`--retries=0`）、`extensions-settings.spec.ts` 单跑 **10 passed**（与夹具提取前一致）。`npx playwright test` 全量连跑两次：第一次 **411 项：408 passed / 1 failed / 2 flaky**，第二次 **411 项：408 passed / 0 failed / 3 flaky**。唯一 failed 为 `properties-layout.spec.ts`「四视口双主题覆盖 dirty+pending、…、CSV 状态无整页横向溢出」（`page.goto` 超时；该用例单测内部 32 次导航、单跑耗时 29.6s 已贴 30s 上限，`--workers=1` 单跑通过），与本次改动无关；两次 flaky 集合不同（`g8-ext-03`、`main.spec.ts` ActionDock、`sheet-catalog-visual-evidence.spec.ts` 200% 缩放、`properties-layout.spec.ts` 同一用例），均为 `playwright.config.ts` 已记录的 4 worker 下 dev server 启动抖动，重跑全部通过。
- 评审修复（第 1 轮 Important）：`web/tests/e2e/settings-extensions-production-evidence.spec.ts` 的 `openExtensions()` 由手写 `page.route("**/api/extensions")` 改为复用 `fixtures/extensions.ts` 的 `installExtensions()`，使 `/api/extensions` 与 `/api/extensions/*/state` 两条路由均由夹具统一装配（原文只 mock 列表路由，一旦该 spec 日后新增一次切换即会真写用户 `.dst-manager-data/dst-manager.db`）。`fixtures/extensions.ts` 未改，5 个用例的列表内容/视口/主题/断言与截图取景全部不变；重跑证据 spec **5 passed**、`extensions-settings.spec.ts` **10 passed**，重跑产出的 5 张 `g8-ext-*.png` 与已入库证据逐张 `cmp` 全部字节相同，故未替换任何图片。
- 跳过项：无。未执行 `$env:DST_MANAGER_RUN_AUTOCAD=1` 的真实 AutoCAD 系统测试（本计划不涉及 CAD 侧，环境亦未启用）。

## 2026-09-10（确立扩展卡片基线：Spec 条款 + Demo 重冻结件 + 可复现证据）

- 背景：用户提出「扩展卡片重排」以后会需要，应先定基线。本次只交付**基线本身**（设计条款 + 冻结件 + 证据），**不写生产卡片布局**——卡片实现与设置中心 bool 控件打通并入同一实现批次（G6 之后另开 Plan）。
- 前提校正（影响基线取向）：①扩展增长是**编译期固定索引**（`src/dst_manager/extensions/builtin/index.py` 的 `BUILTIN_EXTENSION_INDEX` 现为 1 条；ARCH-DM-006 把扫描用户目录、entry point、在线安装、市场、第三方 SDK/沙箱列为非目标），新增一个 = 清单 + 工厂 + `pageRegistry` 映射 + PyInstaller 资源，故近期规模是个位数、随发版逐个加入——据此明确**不为「几十条」预设搜索/分页/虚拟滚动**；②该分区的视觉基线**原本不存在**：`docs/dst-manager/mockups/SPEC-DM-011-settings-demo.html` 里「扩展」出现 0 次（SC-15 是 Demo 冻结 commit `a570986` 之后才加的），故上一轮的滑动开关与行布局不在任何冻结基线内。
- 用户裁决四项（写入 `SPEC-DM-011`）：①基线落点＝SPEC + 重开 G3/G4（含补齐截图索引）；②增长机制＝单列卡片 + 面板滚动，**条目 ≥6 按 `enabled` 分「已启用/已停用」两段**，阈值写成条款而非「以后再说」，搜索/筛选/排序/分页/虚拟滚动/多列网格进非目标并写明重启条件（平台具备运行时安装能力时重新裁决）；③信息层级＝四层（名称+版本 / 描述 / 状态徽标+诊断码 / 开关），`actions` 与 `ui_contributions` 不进卡片；④卡片语义角色＝**不可点击、不导航、不承载扩展自身设置入口**（否则与 ARCH-DM-006 §8 冲突），唯一交互是开关。
- 第五项判断（用户选定了非推荐档）：布尔状态控件**统一为滑动开关**——扩展启停（点击即落库）与常规配置的缓冲式 bool 字段（保存时落盘）共用同一形态，语义差异由分区文案与「保存」是否点亮传达，不再靠控件形态区分。代价是 `SettingsFormRow.vue` 的 bool 控件必须与卡片布局在同一实现批次落地，已记在 §6 追踪矩阵。
- 关键发现（顺带修掉一个文档可信度缺口）：`SPEC-DM-011` §7/§8 一直引用 `assets/SPEC-DM-011/`（g4-01～g4-06）与 `production/` 作为 G4/G8 证据，但该目录**从未进入版本库**（`git ls-files docs/dst-manager/specs/assets` 只有 SPEC-DM-012/013），且 `.superpowers/` 已被 `.gitignore` 忽略、本地也已不可复现——即 G8 门禁的「已比对截图」在仓库里无法核验。本次重冻结把标准集（g4-01～g4-12）提交进仓库，并在 §7 写明证据位置与复现方式；实现批次后需重跑 G8（原 G8 只覆盖 SC-01～SC-14，不含扩展分区）。
- 交付物：①`SPEC-DM-011`：§1 非目标（推迟项 + 重启条件）、§3.2 状态矩阵（卡片状态 × 条目数 1/4/8）、§3.3 卡片基线五条（语义角色/四层信息与字段权威/增长机制与阈值/统一滑动开关/a11y 契约）、§4 新增 **SC-16**、§5 第二次 G3 裁决（含逐项否决理由）、§6 SC-16 技术映射（新建 `components/settings/ExtensionCard.vue`，并记录 `SettingsDialog.vue` 535 行越限、不得再堆卡片）、§7 冻结包（Demo 重开说明 + 12 张截图索引 + 证据位置约定）、§8 门禁记录（G3 重开通过；G4 重开为进行中，**2026-09-10 经用户对重开后的 Demo 操作确认后转为通过**；G8 标注不覆盖扩展分区）、§9 SC-16 验收覆盖；②`SPEC-DM-006` §6.3 新增一条控制规范（布尔状态控件统一为滑动开关，定义正文仍留在 SPEC-DM-011，出现第二个消费者时再提升），`related` 补 SPEC-DM-011，`updated` 同步；③`mockups/SPEC-DM-011-settings-demo.html`：新增「扩展」分区（1/4/8 三档条目数演示工具、启用/停用/启动失败/不兼容四态、≥6 条分段）、常规配置 bool 字段改为同一滑动开关、最小视口下演示工具条不再换行（本页 chrome 不占证据注意力）；④新增 `web/tests/e2e/settings-demo-visual-evidence.spec.ts` 13 例：12 张 G4 截图（`testInfo` 附件留档，验收时复制进 `assets/SPEC-DM-011/`）+ 1 例 SC-16 行为钉子（分段阈值、卡片唯一可聚焦元素是开关、`aria-checked` 与可见状态文字同步、bool 与扩展开关同形态）。
- 顺手修正（自查发现）：上一轮的代码注释与待办共 15 处引用了 `PLAN-DM-022`，但仓库现有 Plan 只到 `PLAN-DM-021`——引用了一个不存在的 Plan ID（由本次会话上一轮写下）。已全部改为真实权威：`SPEC-DM-011 修订「启停交互改进」`（同时避免占用 `PLAN-DM-022`，该号留给卡片实现批次的 Plan）。涉及 `web/src` 5 个文件、`i18n` 双语 2 个文件、e2e 2 个文件、`.planning/todos` 1 个文件，均为注释文本，无行为变更；en-US 语言包保持英文注释。
- 不做（明确留到实现批次）：生产卡片布局与 `ExtensionCard.vue`、`SettingsFormRow.vue` 滑动开关打通、多列网格/搜索/筛选/分页、失败卡片展开与「重试启动」（后者需先裁决重试语义，即第 4 项讨论里未采纳的那块）。
- 下一步已立项：**`PLAN-DM-022`（proposed）——「扩展卡片基线与布尔开关统一下沉」**，4 任务 3 批次（批次 1：新建 `BooleanSwitch.vue` 作唯一开关原语并下沉 `SettingsFormRow` 的 bool 控件；批次 2：新建 `ExtensionCard.vue` 承载四层信息 + `ExtensionsSection` 分段；批次 3：G8 生产同状态证据与文档收口），含追踪矩阵、Global Constraints（`SettingsDialog.vue` 535 行不得再增长、不新增全局 CSS、键对称、不得由 `status` 反推开关、除 `settings-dialog.spec.ts` 外不得保存设置）与逐任务红灯/绿灯/提交步骤。`SPEC-DM-011` §8 G6 行同步指向该 Plan，`.planning/plans/dst-manager/README.md` 索引补录（另注：首次编辑时误以为 PLAN-DM-021 未入索引而重复插入一行，已自查删除）。
- 顺带修正一处**既有**悬空引用：`UnsavedInputDialog.vue` 头部原写 `SPEC-DM-015 任务 5`，但 `docs/dst-manager/specs/` 只有 SPEC-DM-001～013；经核实改为 `SPEC-DM-009 §6.2「未提交输入保护」；实现见 PLAN-DM-016 任务 2「会话缓冲、提交生命周期与统一输入保护」`（该引用为上一轮未提交改动里原有，非本次引入）。
- 验证（本批）：`uv run ruff check .` 全绿；`npm run check:i18n` 867 键 / 9 域对称；本轮未改任何**行为**：`web/src` 只有 5 个文件的注释标签修正（悬空 Plan ID → SPEC-DM-011 修订；另 `UnsavedInputDialog.vue` 引用修正），Python 源码零变更，故未重跑 `npm run build` 与 `pytest`（上一轮同会话内 `uv run pytest -o addopts="" -q` 为 1112 passed / 72 skipped，之后 Python 树无变更）；新增证据 spec 单跑 13 passed；`npx playwright test` 全量连跑两次均 **0 failed**（402 项：第一次 400 passed / 2 flaky，第二次 401 passed / 1 flaky；两次 flaky 集合不同且都是 `playwright.config.ts` 已记录的 4 worker 负载下启动抖动——第一次为 `sheet-catalog-visual-evidence.spec.ts`「大数据摘要：500 张图纸」与 `sheet-catalog.spec.ts`「空图纸集返回有效预览且可导出」，第二次为 `main.spec.ts`「存在阻断诊断时任务浮层诊断页签显示红点并可打开」，均重跑通过）。相对上一轮 389 项新增本次 13 例；`docs/dst-manager/specs/assets/SPEC-DM-011/` 12 张截图已纳入版本控制。收尾批（悬空引用修正 + PLAN-DM-022 创建 + 索引与 Spec G6 同步）另复跑 `npx vue-tsc -b --pretty false`、`npm run check:i18n` 与 `extensions-settings`+`settings-demo-visual-evidence`（20 passed）均全绿。

## 2026-09-10（设置中心扩展启停交互：滑动开关 + 停用不再关闭配置窗口）

- 用户诉求两项：①启停控件改为现代滑动开关；②点停用后配置窗口立即关闭显得突兀，应与启用一致保留在配置窗口，由用户手动关闭。
- 根因（②不是产品意图，而是被模态层叠逼出来的）：设置对话框是原生 `<dialog showModal>`，进入 top layer 后页面其余内容 inert；而当时两个闸门模态（宿主未提交输入三选一 `UnsavedInputDialog`、目录页三选一）都是**页面内联遮罩**（`.modal-mask` + `position:fixed;z-index:1000`），会被上层模态 inert——弹框可见但点不动，`PATCH /api/extensions/{id}/state` 永远不会发出。因此旧实现只能「先关窗让出 top layer 再走闸门」。实施中另发现只 teleport 宿主闸门不够：目录页守卫是页面内联渲染的（`SheetCatalogView.vue`），同样被吞。
- 修复（从根因下手，改用平台层叠）：两个闸门模态均改为原生 `<dialog showModal>`（新增公共 `.gate-dialog` 原语，遮罩由 `::backdrop` 承接，与 `.modal-mask` 同色；`Esc` 改由 `@cancel.prevent` 承接，Tab 焦点圈闭逻辑保留）。原生模态自带 top layer，会自行叠在设置窗口之上，且 Esc 只作用于最上层模态，不需要各窗口互相感知。据此停用与启用完全对称：`onToggleExtension` 去掉 `close()` 与宿主 toast 旁路，落库 → 成功就地收敛 → 失败就地行内呈现（`.ext-error`）。
- 开关（①）：`ExtensionsSection.vue` 的文字按钮改为 `role="switch"` + `aria-checked`，开关旁给出可见状态文字「已启用/已停用」（对辅助技术隐藏 `aria-hidden`，语义由 `aria-checked` 承担，避免重复播报）。方向取自服务端 `enabled`，**不**由 `status` 反推；轨道/滑块全用 SPEC-DM-006 令牌（`--color-accent`/`--color-bg-muted`/`--radius-full`），并遵循 `prefers-reduced-motion`。
- 连带简化三处（均为「关窗」消失后的必然结果，已在代码与 Spec 里写明）：①停用不再关闭窗口，也就不会丢弃本对话框的编辑缓冲，「放弃修改并关闭」前置确认删除（`hasUnsaved` 闸门与 `settings.confirm.*` 文案仍由 `tryClose` 使用）；②原「焦点归还被移除标签的邻近标签」失效——停用时标签栏处于 inert，对 inert 元素调 `focus()` 是空操作，改为在启停结束后把焦点归还到同一开关；③停用失败不再经宿主 toast。
- 测试：改写 `extensions-settings.spec.ts`（5 例→7 例）——断言改为 `getByRole("switch")` + `aria-checked` + 状态文字；核心钉子改为「停用不关窗、标签移除、开关就地翻转、再拨回启用标签恢复、用户手动 Esc 关窗」；新增「闸门内按 Esc = 留在此处，只关闸门不连带关闭设置窗口」与「启停失败就地行内呈现且开关不乐观翻转」两例。`sheet-catalog.spec.ts` 的停用用例补断言「设置窗口仍开着时目录页三选一可见可点」。两处测试基建随之修正：`expectTabIds` 限定到 `.tabbar`（停用不再关窗后设置分区导航与外壳标签栏两个 `role="tablist"` 同时存在）；守卫可访问性断言锚点改用 `.modal-card`，且原生模态**不**写显式 `role`/`aria-modal`——闸门元素常驻 DOM（关闭即 `display:none`），写显式属性会让全仓通用的 `[role="dialog"][aria-modal="true"]` 选择器误命中隐藏闸门（首轮实测为 strict mode violation，3 元素命中）。
- 文档：`SPEC-DM-011` 追加修订说明并同步 §3.1 扩展分区路径、§3.3 关键状态规则（新增开关语义与「停用不关窗」两条）、SC-15、§6 技术映射与 §9 e2e 覆盖要求；`SPEC-DM-006` §6.2 补一条模态原语选型规则（不重叠用遮罩式，需叠在其他模态之上的必须用原生 top layer，并说明常驻 DOM 的模态不写显式 `role`/`aria-modal` 的理由），元数据 `updated` 同步；`ARCH-DM-006` §7 把「宿主级停用必须先关闭设置对话框」改写为真正的不变量「需要叠在已有模态之上的闸门/确认模态必须是原生模态」。旧结论不是失效而沉默，而是被替代并已在三处同步。
- 验证：`uv run ruff check .` 通过（本次未改任何 Python 代码）；`uv run pytest -o addopts="" -q` 1112 passed / 72 skipped / exit 0（纯 Web 改动，Python 侧无新增测试；顺手记一笔：仓库 `addopts=-q` 与命令行 `-q` 会叠成 `-qq`，汇总行被吞掉，读计数需用 `-o addopts=""` 覆盖）；`web` 下 `npm run check:i18n` 867 键 / 9 域对称（较上一版 868 键少 1：删除 3 个无引用键 `settings.extensions.enable`/`disable`/`toggleFailedTitle`，新增 `stateOn`/`stateOff`）；`npm run build` 通过（check:api / check:i18n / vue-tsc / vite build）；`npm run test:unit` 35 passed；`npx playwright test` 全量 389 项 388 passed / 0 failed / 1 flaky（`sheets-columns.spec.ts`「自定义属性多时支持名称搜索」为 `playwright.config.ts` 已记录的 4 worker 负载下启动抖动，重跑通过，与本次改动无关；相对改动前 387 项新增本次 2 例）；最后一轮去掉无用的 `nextTick` 导入后，又单独复跑 `vue-tsc` 与 `extensions-settings`+`settings-dialog`（共 24 项）均全绿。

## 2026-09-10（修复删除后「未提交输入」误报：删除成功即结束对应编辑上下文）

- Important——修复用户报告的「删除子集功能操作 bug」：点击编辑子集 → 选择目标子集 → 删除整个子集 → 确认后点击「预览变更」，会弹出「未提交输入」，必须多点一次「放弃输入」才能继续。实测确认弹框内容是误报，与草稿提交和服务端删除逻辑无关。
- 根因（前端「编辑上下文生命周期」，非后端）：`web/src/App.vue` 的 `doQueueDeleteSubset` 在 `addCommand(delete_subset)` 成功后只弹 toast，没有结束 `useSheetEditor` 里那个 `rename` 编辑上下文；随后 `rebuildDraftProjection()` 触发内部结构投影，显示工作区按服务端派生文档移除该子集，`useSheetEditor.ts` 的 `watch` 因「编辑目标已不存在」把上下文标为 `invalid`；而 `guard()` 的弹框条件是「有未保存修改**或**上下文失效」，于是用户明明没有任何未提交输入，点「预览变更」仍被拦下。空上下文弹框只提供「留在此处/放弃输入」（失效时 `canSave=false`），交互上等价于被迫丢弃一次。
- 修复（局部，按用户建议不放宽通用失效守卫）：`useSheetEditor.ts` 新增 `discardIfTargeting(objectId)`——仅当当前编辑上下文的编辑对象正是刚被删除的对象时 `discard()`（关闭表单并把焦点归还触发按钮）；`App.vue` 在 `doQueueDeleteSubset` 与 `doQueueDelete` 的 `addCommand(...)` 成功分支各调用一次（`delete_subset` / `delete_sheet`，第 604、625 行）。单张删除存在同一根因（用户确认删除当前正在编辑的图纸后，点预览同样被误报），本次一并收口。外部基准刷新、撤销或其他结构变化仍按原规则标 `invalid` 并保留输入供核对，因为那些场景丢失的是真实输入，不能静默丢弃。
- 测试：新增 3 例 Playwright 回归（`web/tests/e2e/sheets-drafts.spec.ts`「删除整个子集后编辑表单关闭且正式预览不误报未提交输入」「先改子集标题再删除：只出现删除前一次输入决策」，`sheets-editing.spec.ts`「删除正在编辑的图纸后编辑区关闭且正式预览不误报未提交输入」）。红灯先行：`toHaveCount(0)` 表单未关闭与「完整变更预览」未出现（预览被弹框挡住）均在修复前按预期失败；另用临时用例单独证明症状（删除后点预览确实弹出「未提交输入」）后删除该临时文件。
- 测试覆盖缺口一并封堵：原有「删除整个子集强确认字段不变…」用例只断言 `/changes/preview` 收到过 `delete_subset`，而内部结构投影本来就会调同一端点，因此即使预览被弹框拦截测试也照样通过（用户报告已指出该假通过）。新用例先在投影落地后取请求基线次数，再要求用户点击「预览变更」时**新增一次**同端点请求并展开「完整变更预览」，从行为上区分内部投影与用户正式预览；不为此改动请求体（HTTP 契约与序列化字段保持不变）。
- 文档：`docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md` §6.2 把原「基准刷新或对象消失」行拆为两类——外部基准变化/撤销仍标失效并保留输入，「用户自己确认的删除命令成功加入草稿」则必须结束对应编辑上下文；同步在 §9 补 2026-09-10 评审记录并更新 `updated` 元数据（状态保持 `accepted`）。未新增文档、未改动其他契约。
- 验证：`uv run ruff check .` 通过；`uv run pytest -q` exit 0（1112 passed / 74 skipped，纯前端改动无新增 Python 测试与跳过）；`web` 下 `npm run test:unit` 35 passed；`npm run build` 通过（check:api / check:i18n 868 键对称 / vue-tsc / vite build）；`npx playwright test` 全量 387 项 385 passed / 0 failed / 2 flaky（`main.spec.ts`「Ctrl+S 只打开确认模态不直接执行」与 `sheet-catalog.spec.ts`「跨图纸集不兼容模板保留…」均为 `playwright.config.ts` 已记录的 4 worker 负载下启动抖动，重跑通过，与本次改动无关；相对改动前全量 384 项正好新增本次 3 例）。

## 2026-09-10（修复顶部栏「打开所在文件夹」在含空格路径下打开「文档」目录）

- 修复用户报告的「顶部栏『打开所在文件夹』打开的是 `C:\Users\sonic\Documents` 而不是 DST 所在目录」。根因在 `src/dst_manager/infrastructure/explorer.py`：`Explorer.open_folder_and_select` 原先以 argv 列表调用 `subprocess.Popen(["explorer", f"/select,{file}"])`，而 Python 的 `subprocess.list2cmdline` 在路径含空格时会把**整个** `/select,<path>` 参数用双引号包住（`explorer "/select,C:\...\project3 - 2\图纸集数据文件.dst"`）。explorer 不按 CRT 引号规则解析、而是自行解析原始命令行，于是把该参数当成一个普通路径，解析失败后回退打开用户「文档」目录。无空格路径不带引号，故一直表现正常，掩盖了该缺陷。
- 本机实测（`Shell.Application` 枚举窗口 `LocationURL`/`SelectedItems`，探针窗口用完即关）三类对照：无空格路径 → 正确目录并选中 DST；含空格路径用旧写法 → `file:///C:/Users/sonic/Documents`（精确复现用户症状）；含空格路径改成只给路径加引号的 `explorer /select,"<path>"` → 正确目录并选中 DST。含空格目录走 `open_folder`（`explorer "<folder>"`）实测正常，未改动。
- 修复：新增 `_select_command_line()` 按 explorer 的解析规则显式构造原始命令行（开关留在引号外、只给路径加引号；`shell=False`、不经 shell，路径来源仍是服务端可信上下文且壳桥已校验存在），`open_folder_and_select` 改用它；路径含双引号（Windows 文件名非法）时抛 `ExplorerError` 而非转义，杜绝命令行逃逸。无空格与含空格路径走同一条构造路径，不再按是否含空格分叉。扩展导出成果的「打开所在文件夹」（`ShellBridge.open_artifact_folder`）复用同一方法，同步修复。
- 测试：新增 `tests/unit/test_explorer.py` 5 例，断言「explorer 最终收到的命令行」（字符串参数原样、列表经 `list2cmdline` 还原）分别为含空格路径 `explorer /select,"<path>"`、无空格路径同形、中文+逗号+`&`+`#`+括号原样保留、含双引号路径被拒且不启动 explorer、非 Windows 直接不支持。红灯先行：4 例在实现前按预期失败（旧实现给出列表参数且不拒绝引号）。
- 验证：`uv run ruff check .` 通过；`uv run pytest` 1112 passed / 72 skipped（4 项按环境跳过为既有基线之外，本次无新增跳过）。修复后以真实 explorer 复跑四种路径（无空格样本、含空格样本 `sample\project3 - 2`、临时构造的 `dstm-probe 工程,甲 & #1 (终)\图纸 集, v2.dst`、用户实际路径 `F:\WORK\古春雷\16号线共建管廊\前期工程\cad\综合井14-15 道路.dst`），四例均打开正确目录并选中目标 DST；验证用的临时目录与探针脚本已删除。
- 前端与契约未改动（前端只传 `workspace_id`，路径权威仍在宿主），无需更新 Web 测试；未改动任何文档契约，故除本记录外无文档变更。

## 2026-09-10（修复图纸目录扩展「停用不可逆」：启停入口收归设置中心扩展分区）

- Important——修复用户报告的「点了停用按钮没有看到再开启的入口」：启停控件原先只长在扩展自己的页面上（`web/src/views/SheetCatalogView.vue` 的「停用扩展」，且 `enabled` 硬编码为 `false`，只会停用），而 `ARCH-DM-006` §7 要求停用后移除该页面入口，`web/src/App.vue` 的 `extensionPages` 又按 `status!=="AVAILABLE"` 过滤标签，于是开关变成单向：点一次停用即永久失去入口，且启停意图持久化在 `extension_states`（`runtime.py` 启动对账仍会重新停掉），用户被卡死。实测本机两处数据库均停在 `enabled=0`（`%LOCALAPPDATA%\dst-manager\data\dst-manager.db` 与仓库 `.dst-manager-data/dst-manager.db`）。
- 修复：新增设置中心「扩展」分区作为**唯一**启停入口。`web/src/components/settings/ExtensionsSection.vue`（纯呈现：列表/加载/失败/错误文案全部由上层传入，不自行调扩展端点）、`web/src/composables/useExtensions.ts`（清单与启停状态所有者，应用级而非工作区级）、`SettingsDialog.vue` 加第三分区与编排、`App.vue` 接入闸门与标签/焦点收敛；`SheetCatalogView.vue` 移除「停用扩展」按钮，改为指向设置中心的提示（`extensions.page.manageHint` 替换 `extensions.page.disable`，中英同步）。后端零改动：`GET /api/extensions` 已返回含停用/失败条目，`PATCH /api/extensions/{id}/state` 已支持 `enabled:true`。
- 关键约束（实现中发现并已处理）——设置对话框是原生 `<dialog showModal>`，进入 top layer 后页面其余内容 inert，宿主渲染在对话框外的三选一闸门（`UnsavedInputDialog` 与目录页守卫模态）既不可见也不可点击，PATCH 永远不会发出。故停用顺序固定为：先处理设置对话框自身的未保存编辑确认（选「留在此处」则停用中止）→ `close()` 让出 top layer → 再走 `guardAllInputs`。启用不移除任何入口，不跑闸门、不关对话框，失败就地行内呈现；停用因对话框已关闭，失败改走宿主 toast。开关**不**进入 `edits` 缓冲、不计入 `hasUnsaved`，分区内固定说明「立即生效，不受下方取消影响」。
- 顺带修复（发现于实施过程中）——`web/tests/e2e/fixtures/sheetCatalog.ts` 只 mock 了 `GET /api/extensions`，未 mock `PATCH /api/extensions/*/state`，于是旧用例「停用扩展（离开页面）先经过三选一保护」的停用请求会打到**真实后端**并持久化停用意图，把开发环境的扩展真停掉（与用户报告的卡死现象同源）。夹具现持有 `extensionEnabled`/`extensionPatchBodies` 并接管 `/state`，列表随状态收敛，既堵住测试污染也支撑新断言。
- 测试：新增 `web/tests/e2e/extensions-settings.spec.ts` 5 例（无工作区即可列出并启用；**停用→标签消失→再进设置可重新启用→标签恢复**这一停用可逆核心钉子；设置内有未保存修改时停用先确认且「留在此处」中止；目录页有草稿时从设置中心停用必须出三选一、闸门未被 top layer 吞掉；清单加载失败给可见降级与重试）；改写 `extensions-navigation.spec.ts` 为「扩展页面不再提供停用入口并指引到设置中心」（防回退），改写 `sheet-catalog.spec.ts` 的同名用例改走设置中心。红灯先行：5 例与新钉子均在实现前按预期失败。焦点归还（被移除标签原位置的邻近标签）与三选一前置保护由新用例继续钉住。
- 文档：`SPEC-DM-011` 收窄原「扩展中心为非目标」的整条排除（设置中心只承载启停与状态查看，扩展自身设置与偏好仍归扩展页面，完整扩展中心仍属后续立项），新增 §1 修订说明、§3.1 扩展分区路径、§3.2 扩展状态行、§3.3 两条规则、SC-15 需求条目、§6 技术映射行与 §9 e2e 覆盖要求；`ARCH-DM-006` §7 补「页面入口的移除不等于启停入口消失」与「宿主级停用必须先关闭设置对话框」两条约束，并互相链接。
- 验证：`uv run ruff check .` 通过；`uv run pytest -q` 1179 项收集、exit 0（4 项按环境跳过）；`npm run build` 通过（check:api / check:i18n 868 键对称 / vue-tsc / vite build）；`npx playwright test` 全量 383 passed、0 failed、1 flaky（`main.spec.ts`「关闭后迟到的刷新响应不会复活工作区」，连同早前一次全量中的 `sheet-catalog`「内置模板编辑即变为未命名草稿」与 `sheets-columns`「拉丁字母属性名…」，三例均为 `playwright.config.ts` 已记录的 4 worker 负载下 `openWorkspace` 启动等待抖动，失败点都在打开工作区之前且与本次改动无关；涉及的三个文件分别以 `--workers=4 --retries=0` 单独复跑，sheet-catalog 33/33、sheets-columns 19/19、main 74/74 全绿）。未修改任何 Python 代码。
- 已知欠债（按 AGENTS.md「代码组织契约」记录，未静默留债）：`web/src/components/settings/SettingsDialog.vue` 由 465 行增至 534 行，越过了约 500 行的软上限。新功能本身已按契约新建同层模块（`ExtensionsSection.vue`、`useExtensions.ts`），但停用编排必须留在持有 `close()` 与 `hasUnsaved` 的对话框内。已立项拆分待办 `.planning/todos/dst-manager/2026-09-10-settings-dialog-file-split.md`，含两个已否决方案的理由（抽 composable / 下推到分区均只是搬运行数而不形成真实边界）与首选方案（抽出 `AboutSection.vue`）必须先裁决的缓存语义问题（`showAbout()` 现为会话内不重复拉取，改子组件后会重放 `GET /api/about`）。

## 2026-09-10（新增多语言配置指引 GUIDE-DM-004）

- 新增 `docs/dst-manager/guides/GUIDE-DM-004-multilingual-config-sop.md`，作为多语言与本地化配置的操作手册：核心不变量（唯一 i18n 实例、语言不入持久层、键对称硬门禁、稳定标识+前端翻译、用户数据原样）；五条链路总览（语言解析/切换、前端 8 域语言包、后端错误目录、设置元数据、ShellBridge 原生对话框）；SOP-A 新增/修改前端文案（键命名、命名参数、复数/分隔符/日期数字、硬编码扫描与豁免纪律）、SOP-B 新增后端错误码（message_catalog 与 errors.ts 双侧对称）、SOP-C 设置项本地化五类稳定键、SOP-D 原生对话框 file_kind 白名单、SOP-E 新增语言（如 ja-JP）十点改动清单；验证清单（check:i18n、vitest、pytest、build、e2e、G9）、故障处理表与反模式清单。权威边界以上游 ARCH-DM-005 / SPEC-DM-013 / PLAN-DM-021 为准。
- 在 `docs/dst-manager/README.md` 指南区追加 GUIDE-DM-004 索引条目。仅新增文档，未修改任何源码、测试或既有文档正文。

## 2026-09-10（实施 PLAN-DM-020 全分支终审修复：Artifact 可用性 OSError 兜底与模板冲突文案标签纠偏）

- Important——封堵 `GET /api/artifacts/{id}` 非契约 500 逃逸窗口：`src/dst_manager/extensions/save_grants.py` 的 `capture_baseline` 此前只在 stat 段捕 `FileNotFoundError`，`target.open("rb")` 裸抛——目标文件在 stat 与 open 之间被删除/独占锁定/权限变化（Windows 上 Excel/AV 占用是常态）时 `PermissionError`/`FileNotFoundError` 一路穿透 `runtime.artifact_availability`（无包装）与 `extension_api.get_artifact`（只捕 `ExtensionPlatformError`）成为 FastAPI 默认 500。修复：`capture_baseline` 全量兜住 OSError——`FileNotFoundError` 返回不存在基线（MISSING 语义不变），其余 OS 级失败（含 stat 段权限失败与 open/哈希读取段）语义定为「目标存在但基线不可读」，返回 `existed=True` 且身份字段全 None 的 `_UNREADABLE` 基线，由调用方 fail-closed 归类；`runtime.artifact_availability` 注释明确不可读归为 `CHANGED`（文件在但身份无法确认，与「内容可能已被改动」同样不可信，宁可让用户复核也不伪称可用），派生只返回三态、绝不 500。同源修正：execute 通道 `except OSError` 兜底注释原声称 OS 失败「必然发生在授权消费之前」，但 `SaveGrantStore.consume` 内部也调 `capture_baseline`，目标哈希读取 IO 失败会在授权已烧毁后命中兜底——现 consume 显式把不可读基线包装为 `SaveGrantError("EXPORT_DESTINATION_CHANGED", "保存目标当前不可读…")`（fail-closed，契约化上报），注释改为与实际一致（消费通道不再产生裸 OSError）。新增测试：`tests/unit/test_save_grants.py` 两例（`Path.open` 注入 PermissionError → `capture_baseline` 返回不可读基线不裸抛；consume 对不可读目标按 `EXPORT_DESTINATION_CHANGED` 拒绝且授权烧毁）、`tests/integration/test_extension_api.py` 一例（seed 真实文件 Artifact 先验 AVAILABLE，`Path.open` 注入 PermissionError 后 `GET /api/artifacts/{id}` 仍 200 且 `availability=CHANGED`，绝不 500）。
- Minor（G9 前修正）——`SHEET_CATALOG_TEMPLATE_CONFLICT` 本地/服务端标签写反：按 `save_templates(collection, expected_revision)` 参数语义（与设置保存乐观并发一致），`current_revision` 是服务端最新修订、`expected_revision` 是客户端提交的过期修订，而 `src/dst_manager/extensions/builtin/sheet_catalog/errors.py` 默认文案与 `web/src/i18n/locales/{zh-CN,en-US}/errors.ts` 的 `templateConflict` 均写成「本地 r{current_revision}/服务端 r{expected_revision}」，用户看到互换的错误信息。修复：三处交换标签为「服务端 r{current_revision}/本地 r{expected_revision}」（en 同步 server r{current_revision}, local r{expected_revision}），params 契约命名不动；既有测试与 e2e 均只断言 code/params/message_key 或文案前缀「模板已被其他保存更新」，无需改断言。
- 验证：`uv run ruff check .` 通过；`uv run pytest tests/unit/test_save_grants.py tests/unit/test_artifact_exporter.py tests/integration/test_extension_api.py tests/unit/test_sheet_catalog_templates.py` 99 passed（含 3 例新增）；`uv run pytest tests/unit/test_sheet_catalog_expressions.py` 59 passed（错误词汇表回归）；`npm --prefix web run check:i18n` 通过（858 键对称）；`npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --workers=1` 33 passed。

## 2026-09-10（实施 PLAN-DM-020 Task 12：响应式/可访问性、打包、G8 证据与 G9 清单）

- 可访问性修复（SPEC-DM-012 §13，Task 11 两项遗留缺口补齐并钉住）：`web/src/views/SheetCatalogView.vue` 三选一守卫模态打开时焦点移入模态卡片、Tab 在模态内可聚焦元素间圈闭（禁用的「保存为模板」不参与）、Esc=留在此处、关闭归还触发元素（与 `ConfirmModal` 同款模式）；`web/src/components/sheet-catalog/ColumnEditor.vue` 阻断错误聚焦规则补齐——未知字段/语法错误（带 `column_id`）定位到该列表达式输入框（此前未知字段会聚焦列名框，违反「表达式错误聚焦具体编辑框」），无 `column_id` 的重名列错误按结构化 `header` 参数定位到最后一个匹配列的列名输入框（此前完全无法聚焦任何输入）；`web/src/components/sheet-catalog/TemplateBar.vue` 另存为模态补 Tab 圈闭与关闭归还触发按钮。钉住用例：`sheet-catalog.spec.ts` 新增「可访问性」4 例（守卫模态焦点移入/圈闭/Esc/归还、表达式错误聚焦表达式框、重名列聚焦列名框、另存为模态 Esc/圈闭/归还）。
- 响应式与键盘证据（SPEC §7.3 视图行 + §13）：新建 `web/tests/e2e/sheet-catalog-visual-evidence.spec.ts` 8 例——G8 两对同状态截图（见下）、200% 缩放（CDP 720×500 CSS 视口 + 2x 渲染等价）、1 列/50 列极限、长字段名/长值、500 张图纸大数据摘要；布局断言全部为几何/滚动语义：无整页横向溢出（html/body scrollWidth）、主操作滚动后可达且无横向裁剪、宽预览只在 `.table-window` 容器内横滚；键盘：Tab 有序经过 模板栏→字段浏览器→列编辑器→操作区、字段浏览器按钮 Enter/Space 键盘插入语法到光标位置、状态不只靠颜色（脏标记/兼容性警告/生命周期状态文字）。夹具 `fixtures/sheetCatalog.ts` 扩展 `dstPath`/`sheetSetName`/`sheetTitles`/按图纸索引的属性值序列选项（G8 同冻结 Demo 数据口径，既有用例不受影响）。
- 打包守护（EP-01/SC-09）：`packaging/dst-manager.spec` datas 新增内置扩展随包清单——`src/dst_manager/extensions/builtin/sheet_catalog/manifest.yaml` → 包内目录 `dst_manager/extensions/builtin/sheet_catalog`（PyInstaller datas 目标是目录、文件保留 basename 复制进该目录；首次实测写成文件名结尾会产出 `manifest.yaml/manifest.yaml` 双层路径使 frozen 态 `importlib.resources` 清单读取失败，已在 `build_release.ps1` 产物 dist 树复核并修正）。`tests/unit/test_packaging_spec.py` 新增 5 例：manifest.yaml 源与目标目录形态钉住、openpyxl 生产依赖 + 未被 excludes + LICENSE/pyproject.toml 随包（许可证与版本记录可追溯，uv.lock 锁定核对）、固定索引列出的清单资源存在且被 datas 覆盖、datas 条目不含用户可写目录标记 + `runtime.py` 扩展发现不使用 glob/iterdir/listdir/scandir（只经 `BUILTIN_EXTENSION_INDEX`）。红灯先行：3 例在 spec 补条目前失败。
- G8 设计 QA（SPEC-DM-012 §7.4 冻结基准 vs 生产实现）：与冻结 Demo（commit `9f3dfb3`，工作区副本经 `git diff` 核对一致）相同虚构数据（滨河市政工程.dst、项目名称/项目编号/项目.编号、专业代码/设计人缺值 2 张、市政标准目录四列）、状态、视口（1440×1000 浅色 / 900×700 深色）与展开状态生成成对截图，逐项比对：页面结构/六区域功能/数据/双主题令牌一致或已接受差异（D1～D10），无未关闭 P0/P1；取证中修复上述 F1（守卫模态焦点）/F2（重名列聚焦）后重截。证据与逐项结论：`.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-design-qa.md`（MEMO-DM-027）；截图存 `.superpowers/g8/`（gitignore，不入提交树），生产侧经 `sheet-catalog-visual-evidence.spec.ts` G8 用例可复现。
- G9 清单（真实桌面验收待用户）：新建 `.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md`（MEMO-DM-028）——启停跨重启、默认/自定义/跨图纸集不兼容模板、原生另存为取消与覆盖确认、目标选择后外部改动、成功后打开所在文件夹（Task 11B `open_artifact_folder` 专用桥）、Excel 前导零/筛选/冻结/文本公式安全、文件移动/修改后 Artifact 三态、核心页面不回退；含 Ruling-10 遗留项复核（Artifact 插入失败时文件已保存但未登记的一致性窗口：文件可见且正确、后台可查日志 reconciliation，低危已裁决接受并钉住）。全部结果字段留空待操作者填写；填写并由用户确认前 PLAN-DM-020 保持 `active`。
- 门禁收口：SPEC-DM-012 §16 门禁表 G7=通过（本分支实施 + 全量自动验证）、G8=通过（MEMO-DM-027 证据）、G9=未开始（待用户）；计划 `status` proposed→`active`（G9 未过不标 completed），「实际验证」追加 Task 12 记录；`docs/dst-manager/README.md` 与 `.planning/plans/dst-manager/README.md` 状态行同步。
- 验证（全部退出码 0）：`uv sync --dev`；`uv run ruff check .`；`uv run pytest`（1176 项 = 1102 passed / 74 skipped / 0 failed）；`uv lock --check`；`uv run alembic upgrade head`；`npm --prefix web ci`；`npm --prefix web run check:api`；`npm --prefix web run build`（check:api + check:i18n + vue-tsc + vite）；`npm --prefix web run test:e2e` 全量 **379 passed**（1 例基础设施抖动经既有 retries=1 吸收，main.spec 既有已知 flake）；聚焦套件 `extensions-navigation + sheet-catalog + sheet-catalog-visual-evidence --workers=1` **48 passed**；`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1` 产物 `dist/releases/dst-manager-v0.3.3-win64.zip`，dist 树复核 `manifest.yaml` 落位正确。安全与追踪反查：追踪矩阵 EP-01～QA-01 逐行均有实现+测试；无 TODO/FIXME/未完成标记；动态 import 仅 pageRegistry 编译期白名单映射（及测试自有模块）；扩展代码无 eval/exec/Jinja/子进程；API 不接受客户端路径参数；扩展/发布日志仅含稳定标识与文件名 basename（无完整路径、无求值值）；禁用扩展后核心 API 回归（`test_extension_api.py`+`test_api.py` 102 passed）与三页面 e2e（`extensions-navigation.spec.ts`）钉住。延后 Minor 逐条 triage 见 Task 12 报告：两项 a11y 缺口已修复，其余为内部代码质量项（并发窄竞态、TOCTOU 窗口、计时器清理、诊断文案等），无用户可观察行为缺陷，随维护处理并在 MEMO-DM-028 §4 登记。

## 2026-09-10（实施 PLAN-DM-020 Task 11B（补充任务，Ruling-11）：模板校验服务端接线与导出文件夹桥方法）

- `application/extensions/runtime.py`（SC-06 服务端接线）：`dst-manager.sheet-catalog` 的设置 PUT 按 `extension_id`/`settings_schema` 分派到 Task 5 的 `save_templates(collection, expected_revision=服务端修订)`——casefold 重名、100 上限、内置不可变（同名影子模板）、修订冲突（expected/current）与未知高 schema 拒绝（Ruling-9：原 JSON 原样保留）此前从未在真实后端强制，会静默接受重名/超限保存；现在按 Task 5 错误词汇契约化返回 `SHEET_CATALOG_TEMPLATE_CONFLICT`/`SHEET_CATALOG_COLUMN_DUPLICATE`/`SHEET_CATALOG_TEMPLATE_LIMIT`（409/409/422，结构化 code/message_key/params/message，`key_override` 承接 `SHEET_CATALOG_MESSAGE_KEYS` 稳定文案键），结构性坏负载（缺模板 UUID/坏条目形状）按 `EXTENSION_SETTINGS_INVALID` 422 拒绝；成功保存持久化 `save_templates` 的规范序列化负载（GET 回读一致），乐观并发写入仍由 `ExtensionStore.put_settings` 条件更新原子保证；无 sheet-catalog 契约的其他扩展（未来）保持既有通用 JSON 存储路径不变。
- `interfaces/shell.py`（SPEC-DM-012 §10「打开所在文件夹」专用桥方法）：新增 `ShellBridge.open_artifact_folder(extension_id, artifact_id)`——前端只传扩展与 Artifact 标识，路径权威在宿主：经 `ExtensionStore.get_artifact` 校验 Artifact 存在且 `extension_id` 匹配后，打开登记 `output_path` 所在目录并尽量选中文件（Windows 资源管理器 `/select`，沿用既有 `Explorer` 适配与 `open_workspace_folder` 风格）；Artifact 不存在/身份不匹配返回 `EXTENSION_ARTIFACT_NOT_FOUND`（复用扩展域 `errors.extension.artifactNotFound` 键），目录已被移动删除返回新码 `SHELL_ARTIFACT_DIRECTORY_NOT_FOUND`（专用键 `errors.shell.artifactDirectoryNotFound`，中英 locale 对称补齐），explorer 失败沿用 `SHELL_OPEN_FAILED`，仓储未装配契约化 `EXTENSION_CAPABILITY_UNAVAILABLE`。`message_catalog.py` 登记两个新 Shell 码（中英资源交叉校验同步），`ExtensionRuntime` 新增只读 `store` 属性供桌面装配注入与 API 同一个扩展仓储；`run_desktop` 接线。
- 前端（`web/src/api/shell.ts` + `web/src/composables/useSheetCatalog.ts`）：`SheetShellBridge` 契约同步新增 `open_artifact_folder` 与 `openArtifactFolder` 封装（三态：方法缺失 null/成功/结构化失败）；`openExportFolder` 不再用 `workspace_id` 调 `open_workspace_folder`（用户把 XLSX 另存到任意目录时打开的是无关的 DST 目录），改为成功导出后用 execute 响应中的 `artifact_id` 调新桥方法（导出状态新增 `artifactId`，重试导出先复位）。
- 测试（TDD）：集成矩阵 7 例（`tests/integration/test_extension_api.py`）——合法保存→GET 规范回读、schema 契约 422 先行、过期修订 409 模板冲突词汇、casefold 重名/与内置同名 409 且原设置不变、101 模板 422 具体限制、内置影子模板 409 与缺 UUID 422、高 schema JSON 后 PUT 拒绝且原 JSON 逐键保留、其他扩展通用路径原样存储回读；`tests/unit/test_shell.py` 8 例钉住桥方法成功（选中文件）/不存在/错配/目录已移动/explorer 失败/未装配/签名只有标识参数；e2e 假桥记录 `open_artifact_folder(extension_id, artifact_id)` 调用参数，spec 断言「打开所在文件夹」走新方法且不再调用 `open_workspace_folder`。红灯先行：实现前集成 7 失败、桥单测 7 失败、错误目录交叉校验 1 失败、e2e 1 失败（均为预期缺失能力），实现后聚焦迭代至全绿。
- 验证：`uv run pytest tests/unit tests/integration` **1096 passed, 6 skipped**（聚焦 `test_extension_api.py`+`test_shell.py`+`test_message_catalog.py` 101 passed）；`uv run ruff check src/dst_manager tests/...` 通过；`npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --workers=1` **29 passed**；`check:api`/`check:i18n`（858 键 / 9 域）/`vue-tsc`/`vite build` 通过。
- 修复（评审 Important，fix round 1）：分派条件与字面 schema 版本 1 硬耦合——清单守卫已保证 `schema_version == manifest.settings_schema`，`and schema_version == TEMPLATE_SCHEMA_VERSION` 是冗余条件，未来 sheet-catalog `settings_schema` 升级后 v2 PUT 会通过清单守卫、跳过 `save_templates` 静默落通用 JSON 路径（fail-open，重名/超限/内置不可变重新失去服务端强制）且无测试报警。现分派只按 `extension_id`（采用评审第一选项）：非 v1 负载在分派内天然 fail-closed——模板条目按 v1 严格解析、服务端高 schema 行经 `unknown_schema_preserved` 走 Ruling-9 冲突拒绝。新增 fail-closed 钉子：模拟 `settings_schema: 2` 的 sheet-catalog 清单，casefold 重名 PUT 仍 409 `SHEET_CATALOG_COLUMN_DUPLICATE` 且不落库（修复前该负载 200 静默落通用路径，红灯复现）；"其他扩展通用路径"钉子仍通过；移除 runtime 中不再使用的 `TEMPLATE_SCHEMA_VERSION` 导入。修复验证：`uv run pytest tests/integration/test_extension_api.py tests/unit/test_shell.py` **86 passed**，`tests/unit`+`tests/integration` 全量 **1097 passed, 6 skipped**，ruff 通过。

## 2026-09-10（实施 PLAN-DM-020 Task 11：图纸目录页面、模板编辑和导出交互）

- 新建 `web/src/composables/useSheetCatalog.ts`（唯一页面状态所有者，SPEC-DM-012 §3/§7/§8/§10/§11）：模板集合/当前模板/未保存草稿/脏标记（列序列稳定对比）、字段目录、防抖预览（300ms + 代次丢弃乱序响应）、保存/另存为/删除/冲突恢复、导出状态机、字段插入与三选一导航守卫。内置默认模板为代码常量（表头经宿主 i18n 渲染，SPEC §6.2），编辑即成未命名草稿且只能另存；用户模板原位保存走 `PUT /api/extensions/{id}/settings`（乐观并发 `expected_revision`），另存为生成新 UUID 并即时写入工作区偏好（只记已保存模板，`GET/PUT .../workspaces/{id}/preferences`），删除确认后回内置默认模板（历史 Artifact 不受影响）。冲突恢复（SPEC §11）：`SHEET_CATALOG_TEMPLATE_CONFLICT`（兼容 409 `EXTENSION_SETTINGS_INVALID` 乐观冲突）保留本地编辑，面板明确提供「另存为新模板」与「按新修订重试」（先 GET 刷新服务端修订再原样重放保存负载），不只显示泛化保存失败。字段插入镜像后端 `field_reference` 语法契约（点号形式受限字符集与固有字段保留名裁决，含空格/点号等特殊名称自动改写为 `{scope["name"]}` JSON 方括号形式），经 textarea selection API 在当前光标位置拼接并把光标放回插入点之后。导出（SPEC §10）：无桌面壳可见说明并禁用（桥可用性响应式判定）；`requestExtensionSave` 用户取消不改变草稿/预览且不发执行请求；只有「预览就绪 + 可执行 + 与当前草稿列一致」才允许导出（旧预览/在途预览禁用并给出可见解释）；成功只显示最终路径/文件名与「打开所在文件夹」，不显示 Artifact/修订/哈希；`REPREVIEW_REQUIRED`/`SAVE_GRANT_INVALID`/`EXPORT_DESTINATION_CHANGED`/`ARTIFACT_WRITE_FAILED` 均保留编辑、可重试（漂移提示先刷新预览）。模块级守卫登记（`registerSheetCatalogNavigationGuard`/`guardSheetCatalogPage`，useTheme 同款模块级单例先例）：页面视图挂载期间注册、卸载注销，宿主 `guardAllInputs` 与页签切换据此征询目录页草稿闸门（SPEC §3.2 切换模板/切换页签/停用/关闭统一三选一；未命名草稿在守卫中禁用「保存为模板」分支——需先命名另存为）。
- 新建 `web/src/components/sheet-catalog/` 六组件（各单一职责，只经控制器 props 交互；41～120 行）：`TemplateBar.vue`（模板选择/保存/另存为/删除入口 + 另存为命名模态 + 保存错误与冲突恢复面板）、`FieldBrowser.vue`（固有字段/图纸集自定义属性/图纸自定义属性三组，按钮 title 即插入语法预览）、`ColumnEditor.vue`（列名 + 表达式逐列编辑、添加/删除/上下移；阻断错误定位到具体列并聚焦首个可操作问题——正在编辑器内输入时不抢焦点）、`CompatibilitySummary.vue`（缺定义为阻断 role="alert"、缺值为带图纸数量的警告 role="status"，全部经后端 `message_key` + 结构化参数渲染）、`CatalogPreview.vue`（≤20 行真实数据 + 总数，横向滚动限制在表容器内）、`CatalogActions.vue`（刷新预览 + 导出 XLSX 唯一高强调操作、无壳说明/旧预览/不可执行提示、成功路径面板、失败可重试）。`web/src/views/SheetCatalogView.vue` 只做装配（Task 10 页面状态容器保留），并承载目录域三选一模态、删除确认模态（复用 ConfirmModal/主题令牌）与 toast。
- `web/src/App.vue` 最小接线（SPEC §14「修改 App.vue 最小接线」）：扩展页组件传入 `:workspace`；页签点击/方向键切换经 `guardSheetCatalogPage` 闸门（目录页未挂载时空操作）；`guardAllInputs` 核心输入域过闸后追加目录页草稿守卫。
- i18n（Ruling-3）：`extensions` 域增补图纸目录页面正文文案（模板栏/字段浏览器/输出列编辑器/兼容性/预览/导出/三选一守卫，中英 key 对称，857 键）；`errors` 域新增 `sheetCatalog` 小节 7 键，与 `sheet_catalog/errors.py` 的 `SHEET_CATALOG_MESSAGE_KEYS` 七目录码逐一对应（预览诊断与保存/导出错误共用同一 message_key 渲染通道；`templateConflict` 按修订冲突语义登记，兼容 Task 5 高 schema 冲突空 params 形态）。
- 测试（TDD）：新建 `web/tests/e2e/fixtures/sheetCatalog.ts`（工作区/扩展设置/偏好/预览/执行/Artifact 路由与可编程假桥的最小语义模拟：缺定义阻断、缺值带数量、前 20 行 + 总数、递增摘要、执行摘要复核）与 `web/tests/e2e/sheet-catalog.spec.ts` 28 用例——默认三列真实 20 行/总数、字段三分组、特殊属性光标位置方括号语法与点号语法、组合表达式 `RQ-001`、缺定义可见且阻断、缺值带数量允许导出、空集可导出；内置编辑变未命名只能另存、用户模板原位保存/另存/删除确认回默认（历史 Artifact 查询仍在）、大小写冲突/100 上限错误可见且本地编辑保留、跨集不兼容模板保留并突出缺失字段、偏好只记已保存模板、切换/放弃/关闭/停用三选一保护、冲突保留编辑按新修订重试与改走另存；无壳禁用带说明、取消不变更草稿预览、旧预览禁止导出、成功只显示最终路径 + 打开所在文件夹（不显示 artifact/修订/哈希）、漂移/授权失效/写失败保留编辑可重试。红灯先行：实现前 28/28 failed（页面/交互缺失），实现后聚焦迭代至全绿。
- 验证：`npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --workers=1` **28 passed**；`main.spec.ts` + `extensions-navigation.spec.ts` 回归通过；`check:api`/`check:i18n`（857 键 / 9 域）/`vue-tsc`/`vite build` 通过。
- 修复（评审 Important，fix round 1）：冲突后「另存为新模板」对真实后端会陷入死循环——`saveAs` 用未刷新的 `settingsRevision` 作 `expected_revision`，连续冲突时每次 PUT 都携带过期修订，SPEC §11 的两条出路之一实际不可用（原 fixture 的冲突单次消费 + 不核对 `expected_revision` 掩盖了该行为）。现冲突态进入另存为时先经 `refreshServerRevision()`（与「按新修订重试」同一条 GET 路径）刷新服务端修订再保存，冲突面板在对话框打开期间保持可见以承载该状态；`retryAfterConflict` 复用同一路径。fixture 修正为真实语义：冲突响应推进服务端修订并写入"其他窗口的模板"（持续到用例改写 controls），ok 模式强制核对 `expected_revision`（与 `runtime.put_settings` 同语义），并记录每次 PUT 的 `expected_revision` 供断言。E2E 更新/新增：冲突重试与冲突后另存为断言服务端修订推进与 PUT 携带刷新后的修订；新增「连续冲突下另存为每次携带最新服务端修订并最终成功」（r3→r4→r5 三次 PUT，`expected_revision` 3/4/5 逐一断言）。修复验证：临时禁用 `saveAs` 冲突刷新后两个新旧用例均失败（红灯），恢复后全绿；聚焦套件 `sheet-catalog.spec.ts` **29 passed**，`main.spec.ts`+`extensions-navigation.spec.ts` **81 passed**，`check:i18n`/`vue-tsc`/`build` 通过。

## 2026-09-10（实施 PLAN-DM-020 Task 10：前端扩展贡献模型、动态标签与离开保护）

- `web/src/api/schema.d.ts`：用 `npm run generate:api` 再生成（Task 6 起 `check:api` 门禁因未再生成的漂移失败，本任务计划内修复）；`openapi.json` 内容未变，扩展端点（`GET /api/extensions`、`PATCH /api/extensions/{id}/state` 等）与 `ExtensionSummaryModel`/`ExtensionUiContributionModel` 类型全部生成。
- `web/src/api/contracts.ts` + 新建 `web/src/api/extensions.ts`：扩展契约类型（`ExtensionSummary`/`ExtensionUiContribution`/`ExtensionLifecycleStatus`）与列表/状态切换客户端；错误经 `api/client` 既有已知/未知分流（`message_key` 命中 `errors.extension.*` 渲染，未知走 `errors.ui.unknownSummary` + 可展开诊断）。`web/src/api/shell.ts` 的 `requestExtensionSave` 注释复核：951b87f 已修正为 `null` 语义，本任务无改动。
- 新建 `web/src/features/extensions/pageRegistry.ts`：唯一 `route_key -> Vue 组件` 编译期映射（`EXTENSION_PAGE_COMPONENTS`，动态 import 路径全部来自文件内静态字面量）+ `isExtensionRouteKey` 受信校验（hasOwnProperty，原型链键不放行）。后端/清单返回的 route_key 只作查表键，未知 route_key 与非 `workspace_page` 贡献安全忽略，绝不成为动态 import 路径（ARCH-DM-006 §7）；构建产物中 `SheetCatalogView` 为独立异步 chunk。
- 新建 `web/src/views/SheetCatalogView.vue`（最小页面边界与状态区域）：名称/描述经清单 `name_key`/`description_key` 由宿主 i18n 渲染，版本与生命周期状态九值呈现；状态区域含「停用扩展」控制入口（经 App 全局未提交输入闸门后 PATCH 状态）。模板编辑/字段浏览/导出交互留待 Task 11 的 `useSheetCatalog` 填充。
- `web/src/composables/useShellTabs.ts` + `web/src/layout/TabBar.vue`：标签栏升级为描述符驱动——新增 `TabDescriptor{id,label,number?,disabled?,source:"core"|"extension"}`，`useShellTabs` 接受固定数组或动态 `ComputedRef`，激活项被移除时安全校正回 fallback（首个核心标签），方向键始终在当前列表内循环；TabBar 渲染描述符（label 已本地化），核心三标签顺序固定不被扩展替换。
- `web/src/App.vue` 最小装配（689 行 → 757 行，均为装配代码与注释，无目录业务状态下沉）：工作区打开/刷新后 best-effort 拉取扩展列表（失败按无扩展呈现，不阻断核心工作区），关闭时清空；`extensionPages` 只保留 AVAILABLE 扩展声明的 `workspace_page` 贡献且 route_key 命中编译期映射（同一 route_key 首个声明生效）；无工作区不显示 `workspace_page`；停用当前扩展页走既有 `guardAllInputs` 三选一闸门（Task 11 再深化目录页自身草稿），PATCH 成功按服务端权威摘要收敛标签，被移除的是当前页时回图纸页并把 DOM 焦点归还被移除标签原位置的安全邻近标签。
- i18n（Ruling-3）：新建 `web/src/i18n/locales/{zh-CN,en-US}/extensions.ts` 域（内置扩展 name/description、生命周期状态九值、页面状态区文案）并注册进 `web/src/i18n/index.ts` 唯一实例（现 9 域 784 键）；`errors` 域新增 `extension` 小节 12 键，与 `extension_contracts.py` 的 `EXTENSION_MESSAGE_KEYS`（十平台码）及 `runtime.py` 的 Artifact 404 key_override、`preview.py` 偏好保存失败 warning 键逐一对应，键文案取无插值安全形态。
- 测试（TDD）：新建 `web/src/i18n/extensions-domain.test.ts`（中英键集合相同、内置扩展 name/description 承接、生命周期九值逐一登记、后端 12 个扩展错误键中英对称且全部承接）与 `web/src/features/extensions/pageRegistry.test.ts`（编译期白名单、内置 route key 命中、未知/路径形/原型链 route_key 一律拒绝——测试断言不涉及动态 import 路径）；新建 `web/tests/e2e/extensions-navigation.spec.ts` 6 用例——AVAILABLE 显示目录标签且核心三标签顺序固定、DISABLED/FAILED/INCOMPATIBLE 隐藏且核心功能可用、未知 route_key/非 workspace_page 贡献安全忽略、方向键在动态列表内循环并切换页面、停用当前页（无未保存输入直接停用/有未保存输入先三选一，确认后回图纸页且焦点归还 `tab-revisions` 邻近标签、PATCH 体为 `{enabled:false}`）。既有 specs 的标签世界保护：`main.spec.ts`、`sheets-folder.spec.ts` 与 `fixtures/sheets.ts` 的 `installSheetsFixture` 统一 mock `GET /api/extensions` 为空列表（扩展导航由本任务专属 spec 覆盖）。红灯先行：实现前聚焦 spec 4 failed（标签/页面/停用流缺失）、unit 2 文件导入失败（预期缺失能力）。
- 验证：`npm --prefix web run test:e2e -- tests/e2e/extensions-navigation.spec.ts --workers=1` **7 passed**；`npm --prefix web run test:unit` 35 passed；`check:api`/`check:i18n`（784 键 / 9 域）/`vue-tsc`/`vite build` 通过；`main.spec.ts` 回归通过（74 passed）。
- 修复（评审 Important，fix round 1）：标签重构为 `tabDescriptors` 时旧 TabBar `revisions-disabled` 绑定的 `isWorkspaceLoading` 一支被静默丢弃（只写 `isRestoreExecuting`）——工作区刷新加载期间修订历史标签从"禁用"回归为"可点击"。现 `tabDescriptors` 用 `busyDisabled=isRestoreExecuting||isWorkspaceLoading` 统一钉回，并同样应用于扩展页签（扩展页在加载窗口本就不渲染，防中途点击进入空态）；`RevisionsView` 渲染条件 `active==='revisions'` 无需同步修改——加载/恢复期间两个页签均不可点击，不存在经标签进入的加载中途路径（若刷新开始时已停留在修订页，页面以 `is-workspace-loading` 属性自呈现加载态，为既有设计）。新增 e2e 钉子：发布成功触发的刷新 GET 挂起窗口内断言 `#tab-revisions` 与 `#tab-sheet-catalog` 均 disabled、释放后恢复 enabled；红灯验证——临时回退守卫后该用例失败（禁用断言超时），恢复后通过。

## 2026-09-10（实施 PLAN-DM-020 Task 9：执行动作、Artifact 查询和桌面共同装配）

- `extensions/builtin/sheet_catalog/extension.py`：新增执行侧值对象与动作实现（SPEC-DM-012 §8.2/§9）。`SheetCatalogExecuteRequest{workspace_id, base_revision_id, template, preview_digest, save_grant_id}` 重复提交模板快照与预览摘要；`SheetCatalogExtension.repreview()` 由宿主运行时在执行前对当前快照重建同一预览投影供摘要复核；`execute(context, request, proposal_directory)` 只组装"上下文快照 → 候选文件"——`_catalog_rows` 按预览相同求值语义输出**全量**行（预览只回 20 行，导出必须全量），`write_candidate` 写入宿主分配的 `ArtifactProposalDirectory` 内固定候选名并返回 `CandidateArtifact{path, media_type, expected_headers, expected_rows}`。扩展全程不见目标路径、不消费授权、不登记 Artifact；`SheetCatalogExecuteResponse{artifact_id, file_name, output_path, warnings}` 刻意不含 sha256/source_revision/extension_version（后台字段只经 Artifact 查询披露）。
- `application/extensions/runtime.py`：`ExtensionRuntime.execute_action()` 宿主编排（ARCH-DM-006 §11）——注册表可用性/动作声明校验 → `extension_context` + `repreview` 摘要复核（快照修订漂移经能力上下文、模板/扩展版本/动作摘要变化经 digest 逐字节比对、模板不再可执行，均 `REPREVIEW_REQUIRED` 409，保留编辑语义且不烧毁授权）→ 在 `proposal_root` 下按次创建唯一候选目录 → 扩展写候选 → 原子消费一次性授权 → `ArtifactExporter.publish`（注入 `validate_candidate` 宿主回读校验钩子核对工作表形状/表头/行数/禁止特性）→ 登记 Artifact → `finally` 清理候选目录（SPEC §10 应用数据目录不残留候选）。`SaveGrantError`/`ArtifactExportError`/`SheetCatalogError` 统一契约化为平台错误（`SAVE_GRANT_INVALID`/`EXPORT_DESTINATION_CHANGED` 409，`ARTIFACT_WRITE_FAILED` 503）；授权通道或候选根未装配时契约化 503，绝不 AttributeError。新增 `artifact_availability()`：按当前文件系统状态派生 `AVAILABLE`（存在且 SHA-256/大小一致）/`MISSING`（已删除）/`CHANGED`（被移动或修改）——历史记录不伪装成当前可用；`registry`/`save_grants`/`proposal_root` 只读属性暴露给桌面装配。`default_runtime()` 与 `_ERROR_STATUS` 相应扩展。
- `interfaces/extension_api.py` + `extension_contracts.py`：执行端点接管 Task 3 的 503 过渡——请求契约 `ExtensionExecuteRequest`（移除占位 `ExtensionActionRequest`），成功响应 `SheetCatalogExecuteResponseModel` 四字段；`GET /api/artifacts/{id}` 响应新增 `availability` 三态字段；`openapi.json` 已用 `scripts/export_openapi.py` 重新生成（`schema.d.ts` 再生成仍属 Task 10 Step 1 的 `generate:api`）。
- `interfaces/api.py` + `interfaces/shell.py`：`create_app` 新增 `save_grants` 注入点（缺省时默认装配自建实例，执行通道默认可用）；`run_desktop()` 创建**同一个** `SaveGrantStore` 同时注入 API extension runtime 与 `ShellBridge`（桥"另存为"创建的授权才能被 API 执行消费；两处各建实例会让所有导出 `SAVE_GRANT_INVALID`），桥的 registry 取自 `app.state.extension_runtime.registry`。`web/src/api/shell.ts` 顺手修正 `requestExtensionSave` 注释（实现返回 `null` 而非 `undefined` 表示桥/方法缺失）。
- 测试（TDD）：新增 `tests/integration/test_sheet_catalog_export.py` 19 个测试——预览后执行成功并 openpyxl 回读真实落盘文件（表名/表头/行值/冻结/筛选）与 Artifact 全字段回查（sha256/size/source_revision/availability=AVAILABLE）、未保存草稿模板可执行（不依赖服务端模板状态）、修订变化 `REPREVIEW_REQUIRED` 且授权保留可重试、模板/扩展版本/动作摘要变化 `REPREVIEW_REQUIRED`、能力不可发放 503 且授权保留、停用扩展 409、无效/错配/漂移/复用授权分别 `SAVE_GRANT_INVALID`/`EXPORT_DESTINATION_CHANGED`、伪造候选 `ARTIFACT_WRITE_FAILED` 且目标不存在零残留零登记、`os.replace` 故障注入旧目标字节保持零半文件零登记（Ruling-10 邻接语义不变）、裸装配 503、**桥创建的授权被 API 执行消费**（同一 store 实例的行为钉子）、Artifact 三态 `AVAILABLE/MISSING/CHANGED`、整条预览→执行链路只读不变量（DST/DWG 字节+mtime、工程目录树、`jobs`/`document_revisions`/`workspace_write_locks` 计数、应用临时候选清空）。`tests/integration/test_extension_api.py` 更新执行端点过渡断言（真实分派：未登记工作区 404、缺字段 422）与种子 Artifact 的 `MISSING` 可用性。红灯先行：实现前聚焦套件收集失败 `TypeError: create_app() got an unexpected keyword argument 'save_grants'`（预期缺失能力）。
- 批次三检查点（Step 6）：以临时目录实际导出并 openpyxl 回读通过（`test_preview_then_execute_roundtrip_registers_artifact`）；目标漂移注入（`test_drifted_destination_rejected_with_export_destination_changed`）与 replace 故障注入（`test_replace_failure_keeps_old_target_without_artifact`）均零半文件、零 Artifact 登记。ARCH-DM-005 独立工作流前置复核：`SPEC-DM-013` 已接受（G4/G5 证据齐备）、`PLAN-DM-021` 批次一～三已完成并记录实际 commit，Plan ID `PLAN-DM-021` 状态"批次一～三完成"，Task 10 前置持续满足，已在计划"实际验证"追加一行。
- 验证：聚焦套件 `uv run pytest tests/integration/test_sheet_catalog_export.py tests/integration/test_extension_api.py -q` **39 passed**；回归 `uv run pytest tests/unit/test_database.py tests/unit/test_shell.py tests/integration/test_api.py tests/integration/test_transaction_recovery.py -q` 通过；全量 `tests/unit tests/integration` 无失败；`uv run ruff check src/dst_manager tests/integration/test_sheet_catalog_export.py tests/integration/test_extension_api.py` 通过；`uv run alembic upgrade head` 通过（0006 已是 head）。
- 修复（评审 Important，fix round 1）：候选写入的 OS 级错误逃逸为非契约 500——`execute_action` 的 except 链未捕 `OSError`，候选目录 `mkdir` 或 `workbook.save(path)`（磁盘满/AV 锁定/权限）会穿透为 FastAPI 兜底 500，违反统一错误契约。现 `execute_action` 兜底 `OSError` → `ARTIFACT_WRITE_FAILED`（503）；候选目录创建纳入 `try/finally` 清理范围（创建半途失败也清残目录）。失败语义保持：`ArtifactExporter` 已把发布期 OS 错误包装为 `ArtifactExportError`，故逃逸的 `OSError` 只发生在授权消费之前——授权未被烧毁，重试不要求重新"另存为"。新增 2 个测试：候选目录创建 `OSError`（选择性拦截候选目录路径）与 `Workbook.save` `OSError` 均返回四字段契约错误体、`active_count()==1`（授权未消费）、候选零残留、`artifacts` 表零登记；红灯先行：修复前两测试 500 失败（预期逃逸路径）。聚焦套件 **41 passed**；回归四套件 + Ruff 通过。

## 2026-09-10（实施 PLAN-DM-020 Task 8：一次性保存授权、ShellBridge 与宿主原子成果发布）

- 新增 `src/dst_manager/extensions/save_grants.py`（ARCH-DM-006 §9.1）：进程内一次性保存授权（不落库，Task 2 已确认授权不持久化；新实例不认识旧授权由测试钉住）。`SaveGrantStore.create()` 生成随机 UUID 授权、强制规范化 `.xlsx` 后缀（缺后缀自动补齐）与 `resolve()` 规范路径，记录选择时目标基线 `TargetBaseline{existed, device, inode, size_bytes, modified_ns, sha256}`（device/inode 在 Windows/NTFS 可用，测试不假设 inode 恒非零），TTL 默认 300s。`consume()` 持锁原子消费：任何消费尝试（成功、伪造、过期、复用、扩展/动作/工作区错配）都先销毁授权再校验，拒绝统一 `SAVE_GRANT_INVALID`（错配尝试同样烧毁授权，防伪造探测）；消费时重算基线与选择时基线全字段比对，目标被创建/修改/删除均按 `EXPORT_DESTINATION_CHANGED` 拒绝。`capture_baseline()` 公开供发布器复核复用。
- 新增 `src/dst_manager/extensions/artifacts.py`（ARCH-DM-006 §9.2）：宿主原子成果发布。`ArtifactExporter.publish(grant, candidate, metadata)` 流程：候选存在性 + 可注入 `candidate_validator` 宿主回读校验钩子（Task 9 接线 SPEC §9 回读）→ 目标目录内 `mkstemp` 唯一同卷临时文件 → 复制 + flush → 尽力 fsync（平台能力差异容忍失败，且置于复制错误包装之外，不误判为复制失败）→ 重算目标基线核对授权基线（漂移 `EXPORT_DESTINATION_CHANGED`）→ `os.replace` 原子替换 → 最终哈希/大小在 replace 前对临时文件计算（内容与目标一致）→ 登记 Artifact（`management_relation="external"`）。任一步失败经 finally 清理目标临时文件（不留半写 XLSX）；`os.replace` 之前失败旧目标字节保持；仓储层失败统一契约化为 `ARTIFACT_WRITE_FAILED`，不登记成功 Artifact。日志关联 invocation ID、扩展 ID/版本、workspace ID、source revision ID、artifact ID 与 file_name，普通日志不含求值属性值与完整输出路径（失败日志只留异常类型与阶段标识）。
- `interfaces/shell.py`：`ShellBridge` 新增 `request_extension_save(extension_id, action_id, workspace_id)` 与 pywebview `SAVE_DIALOG` 接线（本计划新增的保存对话框类型）。安全边界：工作区必须匹配当前可信上下文（沿用 `_context_error`）；只允许 registry 中 `ExtensionActionManifest.output_kind == "xlsx"` 且 MIME 精确匹配 `XLSX_MEDIA_TYPE` 的动作（未知扩展 `EXTENSION_NOT_FOUND`、未声明动作 `EXTENSION_ACTION_NOT_FOUND`、非 XLSX 动作 `EXTENSION_CAPABILITY_UNAVAILABLE`）；桥签名只有三个标识参数，不接受前端建议名/路径——建议文件名由宿主从可信工作区 DST 严格生成 `<图纸集名称>-图纸目录.xlsx`（`_suggested_catalog_name`：`<>:"/\|?*` 与控制字符逐个替换下划线、剥离首尾空白与点、名称段限长 100、清洗后为空回退稳定默认名）；对话框固定 `XLSX 工作簿 (*.xlsx)` 过滤器（经 pywebview `parse_file_type` 契约测试守护）；用户取消返回 `{ok:true, value:null}` 且不创建授权；确认后经与 API runtime 共享的 `SaveGrantStore` 创建授权，返回值只含 `save_grant_id/file_name/expires_at`，前端不收到目标绝对路径。授权通道未装配（裸桥）时契约化拒绝而非 AttributeError；`run_desktop` 的共同注入由 Task 9 接管。
- `web/src/api/shell.ts`：`SheetShellBridge` 新增 `request_extension_save` 与 `ShellSaveGrant` 回执类型（前端只拿 save_grant_id/file_name/expires_at，无目标路径），封装 `requestExtensionSave()` 沿用既有三态语义（undefined=桥缺失降级、value=null=取消、ok:false=校验拒绝）；无新前端依赖。
- 测试（TDD）：新增 `tests/unit/test_save_grants.py` 16 个测试（随机 ID/固定后缀/TTL、规范路径绑定、进程内不持久化、伪造/过期/复用/扩展/动作/工作区错配拒绝矩阵与错配烧毁、基线存在性/文件身份/SHA-256/规范路径、创建/修改/删除三类漂移拒绝、`ThreadPoolExecutor` 下同一授权 8 并发恰一成功、两授权并发消费成功且 DST 哈希不变）；新增 `tests/unit/test_artifact_exporter.py` 13 个测试（成功替换与 Artifact 回查、临时文件在目标目录内创建、日志关联身份且不含完整路径/求值属性值、候选缺失、验证失败、目录不可写、复制/flush/replace/哈希/Artifact 插入故障注入、fsync 尽力容忍、漂移拒绝时旧目标字节保持、失败无 Artifact 与临时清理）；`tests/unit/test_shell.py` 新增 12 个桥测试（无窗口、无上下文、裸桥未装配、未知扩展/动作、非 XLSX 与 MIME 错配拒绝、签名钉住不接受建议名、SAVE_DIALOG 固定过滤器与建议名清洗、返回体无目标路径、授权单次可消费、取消不建授权）。红灯先行：实现前 `uv run pytest tests/unit/test_save_grants.py tests/unit/test_artifact_exporter.py tests/unit/test_shell.py -q` 收集失败 `ModuleNotFoundError: ... save_grants`（预期缺失能力）。
- 验证：聚焦套件 `uv run pytest tests/unit/test_save_grants.py tests/unit/test_artifact_exporter.py tests/unit/test_shell.py -q` **78 passed**；`tests/unit` 全量 **947 passed, 6 skipped** 无回归；`uv run ruff check src/dst_manager/extensions src/dst_manager/interfaces tests/unit/test_save_grants.py tests/unit/test_artifact_exporter.py tests/unit/test_shell.py` 通过；`web` 侧 `vue-tsc -b`、`vite build` 与 vitest（28 passed）通过。已知边界：`npm --prefix web run build` 内的 `check:api` 门禁在本任务之前即失败——`web/src/api/schema.d.ts` 相对 `openapi.json` 缺少 Task 3~6 已入库的扩展端点类型（生成物再生成属 Task 10 Step 1 的 `generate:api`），本任务未动接口契约，不在本次处理。
- 环境备注（既有行为，非本次引入）：`migrations/env.py` 的 `fileConfig`（`disable_existing_loggers=True` 默认）会在 Database 迁移初始化时禁用当时已存在的 logger 并移除根处理器，导致同一测试会话内"先初始化 Database 再断言日志"拿不到记录；日志断言测试使用仓储替身避免同测试内 Database 初始化。生产侧同类影响（启动期模块 logger 被禁用）建议后续单独核查。

- 修复（评审 Important，fix round 1，Ruling-10）：显式钉住 Artifact 插入失败阶段的已知窗口——`os.replace` 成功后、`register-artifact` 阶段登记失败时，用户目标已是完整的新文件（非半文件），失败语义为"文件已保存但未登记"，与其余阶段"旧目标字节保持或新目标不存在"不同。裁决接受该窗口、不做预登记（计划全局约束明文"Artifact 只有最终原子保存成功后才能登记"，预登记+确认违反计划），窗口记入 Task 12 G9 清单。`artifacts.py` 模块注释明确记录该窗口与理由，失败日志保留完整调用身份（invocation/扩展 ID/版本/workspace/来源修订 + `stage=register-artifact`）供运维 reconciliation。新增 3 个测试：目标在授权时已存在/不存在两条路径下，登记失败后目标均存在且内容等于候选内容、临时文件无残留；登记失败日志断言全部身份字段 + 阶段 + 无完整路径。聚焦套件 **81 passed**；`tests/unit` 全量 **950 passed, 6 skipped**；Ruff 通过。

## 2026-09-10（实施 PLAN-DM-020 Task 7：openpyxl 候选工作簿生成与回读验证）
- 新增依赖 `openpyxl>=3.1,<4`（pyproject.toml + uv.lock，仅引入 openpyxl 及其传递依赖 et-xmlfile；`uv lock --check` 通过）。
- 新增 `src/dst_manager/extensions/builtin/sheet_catalog/workbook.py`（SPEC-DM-012 §9）：`write_candidate(path, headers, rows)` 由扩展侧把规范化列写成候选 XLSX——唯一可见"图纸目录"工作表、首行列名、`freeze_panes == "A2"`、auto_filter、数据自第二行按传入顺序、单元格一律字符串（`001` 前导零保留；以 `=`/`+`/`-`/`@` 开头的值显式压回 `data_type="s"`，绝不成为公式）、空集仅表头、按表头与内容（CJK 计 2）估算可读列宽并夹在 `MIN_COLUMN_WIDTH=8`/`MAX_COLUMN_WIDTH=40` 之间、数据单元格超长换行（wrap_text）；样式全部常量化，不创建公式、宏、图表、外部链接、隐藏列/表，也不嵌入工程绝对路径（无定义名称、无超链接）。落盘后以 `data_only=False/read_only=False` 重开自检并返回 `WorkbookSummary{worksheet_name: Literal["图纸目录"], headers: tuple[str, ...], data_rows: int}`（`frozen=True, slots=True`）。
- `validate_candidate(path, expected_headers, expected_rows)` 由宿主侧回读校验：可打开性、包内禁止部件（`vbaProject`/`externalLinks`/`charts`/`activeX`）、工作表数与名称、可见性、外部链接/定义名称、表头逐字一致、数据行数、公式与非文本单元格、超链接、隐藏列；任何一条不满足抛阻断结构化错误 `SHEET_CATALOG_XLSX_INVALID`（params 仅 `check` 标识，`message_key=errors.sheetCatalog.xlsxInvalid`）。Task 9 将消费这两个函数做宿主回读校验。
- 测试（TDD）：新增 `tests/unit/test_sheet_catalog_workbook.py` 24 个测试（唯一可见表与名称、首行/冻结/筛选、顺序与字符串类型、`=+-@`/前导零不变形、空集仅表头、列宽上限与换行、禁止特性、WorkbookSummary 形状冻结；伪造多表/隐藏表（openpyxl 拒绝保存单隐藏表，经包级 `state="hidden"` 伪造）/错误表头/行数不符/公式单元格/隐藏列/注入宏/外链/图表/activeX 部件/损坏文件被拒绝）。红灯先行：实现前 `uv run pytest tests/unit/test_sheet_catalog_workbook.py -q` 收集失败 `ModuleNotFoundError: ... sheet_catalog.workbook`（预期缺失能力）。
- 修复（评审 Important，fix round 1）：行尾全空数据行导致 `write_candidate` 拒绝自己的输出——原先写入侧对空串跳过（不产生任何单元格），末行全空时 `max_row` 停在表头行，自检 `data_rows=0` 与输入行数不符而误抛 `SHEET_CATALOG_XLSX_INVALID(data_row_count)`，且行"消失"破坏 Task 9 按行消费的行数语义。现空值仍创建占位单元格并施加样式（XLSX 只落盘有样式的空单元格），读回 `None`/`n`，`max_row` 覆盖全部数据行；`validate_candidate` 本就跳过空单元格不触发 `non_text_cells`，行数按 `max_row - 1` 继续成立。新增回归测试：全部行为空的候选写出+自检+读回行数一致、尾部全空行行数一致；既有 26 项测试（含 `=+-@`/`001`/表头/禁止特性拒绝路径）不回归。

- 验证（Task 7）：`uv run pytest tests/unit/test_sheet_catalog_workbook.py -q` **26 passed**；`tests/unit` 全量 **905 passed, 6 skipped** 无回归；`uv run ruff check src/dst_manager/extensions/builtin/sheet_catalog tests/unit/test_sheet_catalog_workbook.py` 通过；`uv lock --check` 通过。语义说明：XLSX 无持久化空串，空值落盘为带样式的空单元格（读回 `None`），行数与输入严格一致。

## 2026-09-10（实施 PLAN-DM-020 Task 6：图纸目录预览动作、兼容性与确定性摘要）

- 新增 `src/dst_manager/extensions/builtin/sheet_catalog/preview.py`：预览构建、兼容性诊断与确定性摘要（SPEC-DM-012 §8.1）。`build_preview(snapshot, template, *, extension_id, extension_version, action_id)` 为纯函数：模板限制/语法/字段定义全部通过才 `executable=true`；任何阻断错误（`EXPRESSION_INVALID`/`FIELD_UNDEFINED`/`COLUMN_DUPLICATE`/`TEMPLATE_LIMIT`，经 `validate_template`+逐列 `bind_expression` 得到，可定位到列 ID 与 0-based 字符位置）不产出半截行（`rows=()`）；缺值字段按 `(scope, 规范名)` 聚合受影响图纸数（同一图纸同字段只计一次），产出允许执行的非阻断 `SHEET_CATALOG_VALUE_MISSING` warning，诊断与日志只含字段标识与计数、**绝不含属性值**；行最多回传 20 条（`PREVIEW_ROW_LIMIT`）而 `total_rows` 始终统计全部图纸，空图纸集 `executable=true` 且 `total_rows=0`。`preview_digest` 对 workspace_id、base_revision_id、模板 schema 版本、按序列的规范化列（列 ID/表头/规范化 token：字面量或 `(scope, 规范名, builtin|custom)`）、扩展 ID（Ruling-4，经 keyword-only 参数以模块常量传入）、扩展版本与动作 ID 全部敏感、相同输入逐字节稳定；实现为 canonical JSON（`sort_keys` 固定键序 + 紧凑分隔符 + `ensure_ascii=False`）后 SHA-256。`SheetCatalogPreviewRequest`/`SheetCatalogDiagnostic`/`SheetCatalogPreview`/`DigestColumn` 与计划 Interfaces 块形状一致（`frozen=True, slots=True`）；`SheetCatalogDiagnostic.code` 在 7 个目录码之上扩展宿主平台诊断 `EXTENSION_PREFERENCE_SAVE_FAILED`（ARCH-DM-006 §8.2 偏好失败必须可诊断；不属 SPEC §11 目录词汇，稳定文案键 `errors.extension.preferenceSaveFailed`，由 Task 10 前端承接）。
- `extensions/builtin/sheet_catalog/extension.py`：`SheetCatalogExtension` 新增 `preview(context, request)`——只从 `ExtensionContext.workspace_snapshot()` 获取冻结快照（不触碰 reader/DST/数据库/文件系统，修订漂移由上下文拒绝），交给 `build_preview`；新增模块常量 `EXTENSION_ID`/`EXTENSION_VERSION`/`PREVIEW_ACTION_ID`，单元测试钉住与随包 manifest.yaml 一致（防漂移）。
- `application/extensions/runtime.py`：接线 CapabilityBroker（Task 4 因批次边界未接线）——新增 `extension_context(extension_id, workspace_id, required_revision_id)` 上下文管理器（按注册表当前清单发放短生命周期上下文、退出即 `close()`），`__init__` 新增 keyword-only `reader`（`default_runtime` 装配 `ExtensionWorkspaceReader`；缺 reader 显式契约化 503，绝不 AttributeError→500），新增 `settings_schema()` 公开访问器与模块级 `capability_platform_error()`（`CapabilityError` → §12 平台错误映射），`_ERROR_STATUS` 补 `REPREVIEW_REQUIRED: 409`。
- `extensions/registry.py`：宿主能力 allowlist `AVAILABLE_CAPABILITIES` 更新为真实可发放的 `{"workspace.snapshot.read.v1"}`——内置图纸目录扩展发现状态由 WAITING_DEPENDENCY 变为 AVAILABLE（预期翻转 Task 1/3 钉住的过渡断言：`test_extension_registry.py` 真实索引发现测试、`test_extension_api.py` 列表/启停/动作相关断言同步更新，用户停用后状态机如实进入 STOPPED）。
- `interfaces/extension_contracts.py`：新增预览请求契约 `ExtensionPreviewRequest`（workspace_id/base_revision_id + 模板快照，未知高 schema 版本由 `Literal[1]` 直接 422）与响应契约 `SheetCatalogPreviewResponse`（规范化模板、按作用域字段目录、错误/警告、rows、total_rows、preview_digest、executable），及诊断/模板/字段目录嵌套模型。
- `interfaces/extension_api.py`：preview 端点替换 Task 3 的 503 过渡行为为真实分派（可用性/动作声明校验 → `extension_context` → 扩展 `preview`），execute 仍为 Task 9 前的 503 过渡；工作区偏好按 ARCH-DM-006 §8.2 best-effort 更新——仅对已保存模板（template_id 非空）写入"上次选中模板"，未保存草稿不进入偏好；保存失败只记录稳定诊断日志（仅含 extension_id/workspace_id/template_id，不含属性值）并降级为响应内非阻断 `EXTENSION_PREFERENCE_SAVE_FAILED` warning，**不升级为动作失败**。已知边界：`invoke_action` 的 except 范围覆盖调用体（Task 3 遗留 Minor）——预览体内只抛 `CapabilityError`（不会被误归因为注册表错误），未在本次收窄。
- 顺手修复（Task 4 遗留 Minor，披露）：`extensions/snapshots.py` 的 canonical 映射原先把 sheetset/sheet 两作用域混入同一 casefold 字典，跨作用域同名属性（如图纸集 `Dwg` 与图纸 `dwg`）会互相覆盖规范拼写，导致预览查值误报缺值；现按 `definition.type` 分两张作用域映射。新增跨作用域 casefold 冲突回归测试钉住。
- `web/src/api/openapi.json`：随 preview 端点请求/响应契约变化重新导出（`scripts/export_openapi.py`）。
- 测试（TDD）：新增 `tests/unit/test_sheet_catalog_preview.py` 20 个测试（默认模板真实行、两作用域组合、20 行上限+总数、空集可执行、缺定义/语法/重复列/超限阻断与列/位置定位、缺值字段与图纸数且不含属性值、同图纸同字段只计一次、Windows/Posix basename 经真实文档投影、跨作用域同名属性、摘要稳定性/对每项绑定输入敏感/规范化 token 归一/canonical JSON 固定键+紧凑分隔符、扩展常量与清单一致、偏好失败诊断形状）；`tests/integration/test_extension_api.py` 新增 5 个真实预览集成测试（真实行+字段目录+digest 稳定、修订不匹配 409 `REPREVIEW_REQUIRED` 与未登记工作区 404、缺定义阻断结构化错误、偏好保存与草稿跳过、偏好失败降级为非阻断 warning）并同步更新能力接线后的状态断言与不可用预览 503 钉子。红灯先行：实现前 `uv run pytest tests/unit/test_sheet_catalog_preview.py tests/integration/test_extension_api.py -q` 收集失败 `ImportError: cannot import name 'EXTENSION_ID'`（预期缺失能力）。
- 验证：`uv run pytest tests/unit/test_sheet_catalog_preview.py tests/integration/test_extension_api.py -q` **47 passed**；Task 4～6 单测 + 扩展域单测 + `tests/unit` 全量通过；`uv run pytest tests/integration/test_api.py -q` 无回归；`uv run ruff check src/dst_manager tests/unit/test_sheet_catalog_preview.py tests/integration/test_extension_api.py` 通过。批次二检查点（Step 6）：经临时夹具真实请求默认/不兼容/空集预览，响应证据存于 `task-6-report.md`，未产生工程文件、未创建新修订、DST/DWG 时间戳与内容哈希不变；ARCH-DM-005 独立工作流核对见计划"实际验证"。

## 2026-09-10（实施 PLAN-DM-020 Task 5：受限表达式、模板校验与扩展设置语义）

- 新增 `src/dst_manager/extensions/builtin/sheet_catalog/errors.py`：图纸目录错误词汇表（SPEC-DM-012 §11）——7 个目录错误码 `SHEET_CATALOG_EXPRESSION_INVALID`/`FIELD_UNDEFINED`/`VALUE_MISSING`/`COLUMN_DUPLICATE`/`TEMPLATE_LIMIT`/`TEMPLATE_CONFLICT`/`XLSX_INVALID` 的封闭 Literal，逐一固定 `message_key`（`errors.sheetCatalog.<camelCase>`，与既有 `message_catalog.py`/`EXTENSION_MESSAGE_KEYS` 键风格一致）、结构化参数白名单（键+类型双重校验，工厂拒绝词汇外 code/参数/类型；`params` 允许白名单子集，供解析与校验阶段分步补齐上下文）、SPEC §11 固定用户结果与阻断语义（`VALUE_MISSING` 为 `blocking=False` 的可执行 warning，其余六码均阻断）。`SheetCatalogError` 为普通异常类（frozen/slots dataclass 与异常基类组合会破坏 `raise`/`except` 匹配，已实测）。
- 新增 `src/dst_manager/extensions/builtin/sheet_catalog/expressions.py`：受限表达式手写有限状态扫描器（SPEC-DM-012 §5.1 语法：字面量、`{{`/`}}` 转义、`{scope.name}` 点号与 `{scope["json_string"]}` 方括号引用，scope 封闭为 `sheetset`/`sheet`）。空表达式、未闭合引用、多余 `}`、未知作用域、嵌套引用、非法 JSON 转义、引用后多余内容均为语法错误且带 0-based 字符位置（`source_start`）；函数调用/赋值/模板引擎/代码 payload 一律拒绝或退化为字面量（`{{ 7*7 }}` → 文本 `{ 7*7 }`），不引入通用模板引擎。`FieldToken` 增设 `quoted: bool`（计划 Interfaces 块形状之外的最小补充，用于绑定阶段落实保留名裁决）。`bind_expression` 大小写不敏感匹配当前字段目录规范名称：点号形式固有字段优先，方括号形式显式寻址自定义属性——与固有字段同名的自定义保留属性只能经方括号引用（SPEC §4.1/§4.2）；缺定义抛 `SHEET_CATALOG_FIELD_UNDEFINED`。`evaluate_expression` 缺值求值为空字符串且分隔符等字面量原样保留（专业代码为空时 `{sheet.专业代码}-{sheet.number}` → `-002`），缺值统计留给 Task 6 预览聚合。`field_reference` 按规范名称输出正确语法（保留名冲突/含特殊字符走 JSON 方括号并转义）。
- 新增 `src/dst_manager/extensions/builtin/sheet_catalog/templates.py`：模板数据类（`TemplateColumn`/`SheetCatalogTemplate`/`TemplateCollection`/`ValidatedTemplate`，均 `frozen=True, slots=True`）、限制值常量（最多 100 个用户模板、每模板 1～50 列、模板名 1～80 字符、输出列名 1～100 字符且 casefold 唯一、单表达式 ≤1024 字符）与内置默认模板代码常量（图号/图名/文件名三列，`template_id=None`，列 ID 为 `uuid5` 稳定常量；不写数据库、不可改删，`save_templates` 拒绝非恒等的 builtin）。`validate_template` 校验结构/限制/逐列解析（解析错误包装 `column_header` 上下文参数），保存不要求兼容当前字段目录（兼容性属预览阶段）。`save_templates` 先做乐观并发核对（`collection.revision != expected_revision` 抛 `SHEET_CATALOG_TEMPLATE_CONFLICT`，本地编辑原样保留，刷新服务端修订后可重试或另存）、校验模板数/模板名 casefold 唯一（含与内置名冲突）、要求已分配模板 UUID，返回 `{"schema_version": 1, "user_templates": [...]}` settings 负载。`load_templates` 合并代码常量与 settings JSON：坏条目逐条隔离并以稳定诊断 `SHEET_CATALOG_TEMPLATES_SKIPPED` 记录（不含模板名等用户数据），未知高 schema 不加载为可编辑状态、原 JSON 只读保留（不重写不变更）并输出 `SHEET_CATALOG_SETTINGS_SCHEMA_UNSUPPORTED` 诊断，不阻止宿主启动。`delete_template` 为纯函数：只移除当前用户模板、内置默认模板原样保留（选择层据此回退默认模板），只动模板设置，不触碰历史 Artifact；未知 `template_id` 抛稳定前缀 `ValueError`。
- 测试（TDD）：新增 `tests/unit/test_sheet_catalog_expressions.py` 41 个测试（语法正向表驱动 10 例、语法错误+0-based 位置表驱动 15 例、非法转义位置、模板引擎/运算 payload 退化为字面量、固有字段优先、保留名方括号寻址、大小写绑定规范名、缺定义结构化报错、缺值空串+分隔符保留、图纸集作用域逐行重复、`field_reference` 8 例、7 码词汇表逐码断言 `message_key`/参数白名单/用户结果/阻断语义、工厂参数拒绝、源码不含通用执行器红线）；新增 `tests/unit/test_sheet_catalog_templates.py` 24 个测试（内置三列固定与列 ID 稳定、`validate_template` 限制值表驱动 7 例+1024 边界、列名/模板名 casefold 唯一、解析错误包装列名、保存不要求兼容、保存负载序列化、保存/加载往返 UUID 稳定、冲突保留本地编辑+按刷新修订重试、内置不可变、101 个模板拒绝/100 个接受、草稿须先分配 UUID、坏条目隔离诊断、未知高 schema 保留原 JSON+诊断、非列表负载诊断、删除仅移除目标且回退内置、未知/内置标识拒绝删除）。诊断断言附 autouse 夹具恢复被 Alembic `fileConfig`（`disable_existing_loggers=True`）禁用的模块 logger。红灯先行：实现前 `uv run pytest tests/unit/test_sheet_catalog_expressions.py tests/unit/test_sheet_catalog_templates.py -q` 收集失败 `ModuleNotFoundError: No module named 'dst_manager.extensions.builtin.sheet_catalog.errors'`（预期缺失能力）。
- 验证：`uv run pytest tests/unit/test_sheet_catalog_expressions.py tests/unit/test_sheet_catalog_templates.py -q` **90 passed**；全量 `uv run pytest tests/unit tests/integration/test_extension_api.py` **865 passed, 6 skipped**（既有跳过）；`uv run ruff check src/dst_manager/extensions/builtin/sheet_catalog tests/unit/test_sheet_catalog_expressions.py tests/unit/test_sheet_catalog_templates.py` 通过。
- 评审修复（Ruling-9，同一日）：堵住未知高 schema 的 v1 覆盖 v2 JSON 数据丢失通路——`TemplateCollection` 增加 keyword-only 附加字段 `unknown_schema_preserved: bool = False`（带默认值、向后兼容），`load_templates` 检测到高 schema 置 True，`save_templates` 遇 True 一律抛 `SHEET_CATALOG_TEMPLATE_CONFLICT`（诊断信息说明服务端模板 schema 高于当前版本、原 JSON 已保留，本地编辑保留，等待升级后重试或另存），即使 revision 恰与 `expected_revision` 一致也不得保存为 v1 负载。修复 `load_templates` 不检查用户模板名与内置名 casefold 冲突的问题：load 路径沿用"坏条目跳过 + 稳定诊断"哲学，`seen_names` 预置内置名，同名用户模板跳过并记录 `SHEET_CATALOG_TEMPLATES_SKIPPED: template_name_duplicate`，避免损坏 settings JSON 卡死之后的全部保存。新增 4 个测试钉住：高 schema 载入集合带标记且 save 被拒、原 JSON 未被改写、字段默认 False 时正常保存不受影响、与内置同名的用户模板被跳过且其余正常加载后保存正常。验证：两文件 **94 passed**；全量 `uv run pytest tests/unit tests/integration/test_extension_api.py` **868 passed, 6 skipped**；Ruff 通过。

## 2026-09-10（实施 PLAN-DM-020 Task 4：裁剪的冻结工作区快照与 Capability Broker）

- 新增 `src/dst_manager/extensions/snapshots.py`：`workspace.snapshot.read.v1` 的冻结、可序列化最小投影。值对象 `SnapshotProperty`/`SnapshotPropertyScope`/`SheetSnapshot`/`FieldDefinition`/`FieldCatalog`/`WorkspaceSnapshot` 全部 `frozen=True, slots=True`，与计划 Interfaces 块逐字一致。`build_workspace_snapshot()` 复用领域函数 `property_definitions_from_document()`（不复制合并/规范化规则）：图纸集定义来自 sheetset 作用域、图纸定义为声明与实际投影的 casefold 并集，属性值绑定到规范名称并按 `(casefold(), 名称)` 排序，"声明但无值"只出现在定义、"实际但未声明"同时进入定义与值；图纸按子集顺序、图纸顺序展平；`file_name` 跨 Windows/Posix 分隔符裁 basename。快照不含 `root`/`dst_path`/`resolved_path`/`Relative_FileName` 或任何绝对路径。`build_field_catalog()` 从快照推导字段目录：固有字段 `number`/`title`/`file_name` 置 `builtin`（SPEC-DM-012 §4.1 保留标识），自定义属性为普通字段。
- 新增 `src/dst_manager/infrastructure/extension_workspace.py`：只读 reader `ExtensionWorkspaceReader`，从应用数据库**已登记**的 `workspaces` 行定位当前 DST 并解码投影为 `DecodedWorkspace(workspace_id, revision_id, document)`。刻意不调用 `DstManagerService.open_workspace()`（避免重算登记并触发 `upsert_workspace` 写库）与任何写路径：不写 DST/DWG、不创建工程内 `.dst-manager/`、不改变工程文件时间戳；根目录/DST 绝对路径/`root_override` 停留在 reader 内部，不进入快照。未登记工作区抛 `EXTENSION_NOT_FOUND`，DST 投影不可用（codec/校验/OSError）抛 `EXTENSION_CAPABILITY_UNAVAILABLE`，修订漂移由上层判 `REPREVIEW_REQUIRED`。
- 新增 `src/dst_manager/extensions/capabilities.py`：`CapabilityBroker` 按"清单声明 ∩ 宿主 allowlist"发放短生命周期 `ExtensionContext`（绑定 `extension_id`/`workspace_id`/`required_revision_id`/invocation ID），`close()` 后所有请求失败。上下文唯一出口是 `workspace_snapshot()` 返回的冻结快照，不暴露 `DstManagerService`、SQLAlchemy Session、可变 Workspace/DOM、发布器、任务队列、ShellBridge、工作区根路径或 DST/DWG 绝对路径。错误 `code` 只复用既有封闭词汇（`ExtensionDiagnosticCode` 六值诊断码 + §12 平台码：未声明/未在 allowlist/上下文关闭 → `EXTENSION_CAPABILITY_UNAVAILABLE`，宿主词汇外能力 → `EXTENSION_CAPABILITY_UNKNOWN`，未登记扩展 → `EXTENSION_NOT_FOUND`，修订漂移 → `REPREVIEW_REQUIRED`），未新增诊断码。**broker 本体不接入 `ExtensionRuntime`/`discover` 对账**（能力接线属 Task 6，避免翻转 Task 3 已钉住的 WAITING_DEPENDENCY 断言）；宿主 allowlist 缺省沿用 `registry.AVAILABLE_CAPABILITIES`。
- 测试（TDD）：新增 `tests/unit/test_extension_snapshot.py` 13 个测试（定义/值合并与 casefold 规范化、大小写重复属性绑定声明侧规范名、声明但无值、实际但未声明、两作用域、`(casefold, 名称)` 排序、子集/图纸展平顺序、`C:\工程\A.dwg` 与 `folder/A.dwg` 两种分隔符 basename、冻结不可变 + `asdict`/JSON 可序列化、序列化输出无 root/dst_path/resolved_path 且无目录片段、字段目录 builtin 标记；broker：声明∩allowlist 发放、上下文关闭后调用失败、未声明能力拒绝、宿主词汇外 `EXTENSION_CAPABILITY_UNKNOWN`、空 allowlist 拒绝、未登记扩展 404 语义、修订漂移 `REPREVIEW_REQUIRED`、reader 错误映射为结构化 `CapabilityError`）。`tests/integration/test_api.py` 新增 `test_extension_snapshot_build_is_read_only`：复用 `tiny_workspace` 夹具经真实 API 开启工作区后，monkeypatch `Database.upsert_workspace` 与 `DstManagerService.open_workspace` 为必败桩，经 broker 构建快照断言 DST/DWG 的 SHA-256 与 mtime、工程目录树完全不变、不存在 `.dst-manager/`、workspaces 行五元组不变。
- 红灯先行：实现前 `uv run pytest tests/unit/test_extension_snapshot.py tests/integration/test_api.py -q` 收集失败 `ModuleNotFoundError: No module named 'dst_manager.extensions.capabilities'`（预期缺失能力）。
- 验证：`uv run pytest tests/unit/test_extension_snapshot.py tests/integration/test_api.py` **87 passed**；扩展域回归 `test_extension_manifest/test_extension_registry/test_extension_persistence/test_extension_api` + 两文件共 **159 passed**（Task 3 断言未翻转）；`uv run ruff check src/dst_manager/extensions src/dst_manager/infrastructure tests/unit/test_extension_snapshot.py tests/integration/test_api.py` 通过。

## 2026-09-10（实施 PLAN-DM-020 Task 3：平台编排、统一管理 API 与结构化错误）

- 新增 `src/dst_manager/application/extensions/runtime.py`：`ExtensionRuntime` 组合 `ExtensionRegistry` 与 `ExtensionStore`。启动顺序钉死为 `DstManagerService` 完成数据库迁移与发布恢复之后才 `start()`（内部先 `registry.discover()`，再按 `extension_states` 持久化启停意图对账：用户停用的扩展在重启后重新排空停用，用户启用但未拉起的尝试重新启用、被注册表以平台码拒绝时保持持久化停用并记录稳定诊断）；对账与持久化逐扩展隔离失败，任何单扩展发现失败不影响 `/api/health`。错误契约（Ruling-7 修正后表述）：**错误响应用平台码**——应用层统一抛 `ExtensionPlatformError`（ARCH-DM-006 §12 平台码 + HTTP 状态 + 结构化 params，未映射诊断码兜底为 503 契约化错误体）；**列表摘要暴露封闭诊断码用于诊断展示**（ARCH §4.3 诊断面，`error_code` 限定 `ExtensionDiagnosticCode` 六值词汇，不携带原始异常文本或路径）；清单不可读的占位条目以不含路径的稳定标识 `builtin.invalid-<资源名 slug>` 登记（不把服务端绝对路径暴露给客户端），不落库、不可启用。
- 新增 `src/dst_manager/interfaces/extension_contracts.py`：`ExtensionPlatformErrorCode` 十值 Literal（与计划 Interfaces 块逐字一致）、`ExtensionErrorResponse(code/message_key/params/message)`、列表/启停/版本化设置与偏好/动作请求/Artifact 响应 Pydantic 契约，以及平台码到稳定文案键的 `EXTENSION_MESSAGE_KEYS` 映射（Task 10 前端 extensions 域逐一对应）。
- 新增 `src/dst_manager/interfaces/extension_api.py`：`register_extension_routes(app)` 注册 9 个统一端点（GET /api/extensions、PATCH state、GET/PUT settings、GET/PUT 工作区偏好、POST actions preview/execute、GET /api/artifacts/{id}）。router 只做扩展状态、动作声明与请求模型校验：未知扩展/Artifact 404、禁用 409 `EXTENSION_DISABLED`、不兼容 409 `EXTENSION_INCOMPATIBLE`、能力不可用 503、设置 schema 不匹配 422 与 `expected_revision` 冲突 409（同码 `EXTENSION_SETTINGS_INVALID`，params 区分）、未声明动作 404 `EXTENSION_ACTION_NOT_FOUND`；错误响应经 `ExtensionErrorResponse` 出口自检。preview/execute 在扩展可用且动作已声明时也返回 `EXTENSION_CAPABILITY_UNAVAILABLE`（预览逻辑属 Task 6、执行属 Task 9），不编造结果。路由直接注册到宿主 app（与 api.py 既有形态一致），不引入 `include_router`，`app.routes` 仍全部是具体路由对象。
- `src/dst_manager/interfaces/api.py` 仅最小装配：新增 `extension_runtime`/`extension_index` 两个可选注入点（测试与桌面装配用），在 service 构造（迁移+发布恢复完成）后创建默认 runtime、`start(BUILTIN_EXTENSION_INDEX)` 并注册扩展路由；整体失败只记录 `EXTENSION_BOOTSTRAP_FAILED` 警告。
- 测试（TDD）：新增 `tests/integration/test_extension_api.py` 13 个测试（真实依赖状态呈现 WAITING_DEPENDENCY 不谎报、启停与重启持久化、失败启用不翻转持久化意图、未知扩展/Artifact 结构化 404、Artifact 元数据查询、设置往返/修订冲突/schema 守卫、偏好零值默认与工作区隔离、动作可用性与声明校验（含禁用 409 与未知动作 404）、坏清单与工厂失败隔离（/api/health 与 /api/revisions 仍 200）、不兼容扩展 409、OpenAPI 全端点与 10 个平台码、启动顺序三段严格断言：以记录事件的 Database/RecoverablePublisher/ExtensionRuntime 测试替身断言 `database-migrated → publish-recovered → registry-discovered`）。红灯先行：实现前 `uv run pytest tests/integration/test_extension_api.py -q` 收集失败 `ModuleNotFoundError: No module named 'dst_manager.application.extensions'`（预期缺失能力）。
- 验证：`uv run pytest tests/integration/test_extension_api.py tests/integration/test_api.py tests/integration/test_api_settings.py` **100 passed**；全量 `uv run pytest` 通过（4 skipped 为既有）；`uv run ruff check .` 通过；`uv run python scripts/export_openapi.py` 重新导出 `web/src/api/openapi.json`（新增扩展端点与错误契约，未触碰前端其他文件）。批次检查点经 HTTP 测试客户端手工验证：禁用全部扩展后 `/api/health`、`POST /api/workspaces/open`、`GET /api/workspaces/{id}`、`GET /api/revisions` 均 200（证据见 task-3-report.md）。
- 顺手修复（Task 2 遗留，一处断言）：`tests/unit/test_runtime.py::test_migrate_database_uses_resource_dir` 仍断言 `LATEST_SCHEMA_REVISION == "0005_…"`，Task 2 前移 head 至 `0006` 时漏更新，导致该测试自 Task 2 起在全量回归中红；本任务随全量回归改为断言 `0006_dm020_extension_platform`。
- 评审修复（fix round 1，2 Important 按 Ruling-7 处理）：①`ExtensionRuntime._platform_error` 对未映射注册表诊断码不再 KeyError→非契约 500，统一兜底为 503 `EXTENSION_CAPABILITY_UNAVAILABLE` 契约化错误体（原始诊断保留在 `message`），并对清单不可读占位条目的"启用"显式契约化拒绝（此前会触发注册表 `factory is None` 断言逃逸成 500），新增 `test_enable_factory_failed_extension_stays_contract_compliant` 与 `test_enable_placeholder_extension_returns_contract_error` 钉住；②列表摘要 `error_code` 收敛为 `ExtensionDiagnosticCode` 六值封闭词汇（错误响应仍是 §12 平台码，修正前次 changelog"诊断码不外溢到 API"的相反表述），占位条目 `extension_id` 改为不含路径的 `builtin.invalid-<slug>`（`extensions/registry.py::_placeholder_id`，重复占位保留先发现者），集成测试断言响应不含 `tmp_path` 绝对路径且 `error_code ∈ 封闭词汇`；同步更新 Task 1 `tests/unit/test_extension_registry.py::test_manifest_load_failure_is_isolated` 的占位 ID 断言（原断言占位 ID 等于资源串）。修复后 `uv run pytest tests/integration/test_extension_api.py tests/unit/test_extension_registry.py tests/unit/test_extension_manifest.py tests/unit/test_extension_persistence.py` **72 passed**。

## 2026-09-10（实施 PLAN-DM-020 Task 2：扩展状态、设置、偏好与 Artifact 持久化）

- 新增迁移 `migrations/versions/0006_dm020_extension_platform.py`（down_revision=`0005_dm019_job_lease_seconds`），创建四张扩展持久化表：`extension_states`（PK extension_id，enabled/last_loaded_version/last_error_code/updated_at）、`extension_settings`（PK extension_id，schema_version/revision/value_json）、`workspace_extension_preferences`（联合 PK workspace_id+extension_id）、`artifacts`（PK artifact_id，必填来源字段 extension_id/extension_version/workspace_id/source_revision_id，`management_relation` 带 `IN ('external')` CHECK 约束）。授权（save grant）不持久化。`migrations/env.py` 导入扩展 ORM 模块使四表进入 `Base.metadata`；`database.py` 仅把 `LATEST_SCHEMA_REVISION` 更新为 `0006_dm020_extension_platform`（未追加任何业务 CRUD）。
- 新增仓储 `src/dst_manager/infrastructure/persistence/extensions.py`：冻结值对象 `VersionedJson`/`ExtensionStateRecord`/`ArtifactRecord`（`frozen=True, slots=True`，与计划 Interfaces 块逐字一致）与 `ExtensionStore`（接收宿主现有 session factory，不把 Session 暴露给扩展层）。`put_settings` 乐观并发：expected_revision 与当前行修订（无行为 0）不一致抛 `SettingsRevisionConflictError` 且不覆盖旧值，成功后修订 +1；`put_preference` 按（工作区，扩展）联合键 upsert、修订递增；`create_artifact` 校验四个必填来源字段（缺失抛 `EXTENSION_ARTIFACT_SOURCE_INVALID`）与 `management_relation=="external"`（否则 `EXTENSION_ARTIFACT_RELATION_INVALID`），重复 artifact_id 由主键约束拒绝；时间统一规范化为 UTC。
- 模板存于 extension_settings 的 JSON，与 artifacts 无外键/级联：删除设置行后历史 Artifact 记录保留（测试断言 `PRAGMA foreign_key_list(artifacts)` 为空）。
- 测试（TDD）：新增 `tests/unit/test_extension_persistence.py` 12 个测试函数（参数化后 19 例：状态 upsert 单行、设置 JSON 往返、修订冲突不覆盖旧值、设置按扩展隔离、偏好联合键隔离与单行、Artifact 必填来源字段与 external-only 参数化、重复 artifact_id IntegrityError、设置删除不删 Artifact、四表主键声明、空库与 0005 既有库两条升级路径到 `0006`）。`tests/unit/test_database.py`：迁移哈希夹具加入 `0006`（SHA-256 `7e86a66e…bc205`）；既有 MVP 升级用例断言更新到新 head；`test_job_lease_seconds_migration_round_trip` 的 `downgrade -1` 改为显式目标 `0004_dm007_layout_name_cache`（head 前移后 `-1` 不再指向 0005，用例意图不变）。红灯先行：实现前 `uv run pytest` 两文件失败 `ModuleNotFoundError: No module named 'dst_manager.infrastructure.persistence.extensions'`、哈希夹具与 head 断言失败（预期缺失能力）。
- 验证：`uv run pytest tests/unit/test_extension_persistence.py tests/unit/test_database.py` **43 passed**；`uv run alembic upgrade head` 通过（0005→0006）；`uv run ruff check migrations src/dst_manager/infrastructure/persistence tests/unit/test_extension_persistence.py tests/unit/test_database.py` 通过。
- 评审修复（fix round 1，两项 Important）：①按 Ruling-6 直接在未发布的 0006 中为 `extension_settings`/`workspace_extension_preferences` 补 `updated_at`（DateTime(timezone=True)，与 ORM 逐一对应），`put_settings`/`put_preference` 写入时落 UTC 时间戳，并同步更新迁移哈希夹具（新 SHA-256 `6940e7f2…af8a3`）；②`put_settings` 乐观并发改为原子条件 `UPDATE … WHERE extension_id=:id AND revision=:expected` 按受影响行数判定冲突（首次写入路径并发抢先由主键约束转 `SettingsRevisionConflictError`），消除读-改-写窗口的静默覆盖，新增两线程竞争同一 `expected_revision` 恰一成功的并发测试，另在设置/偏好用例中断言 `updated_at` 落库且随修订推进。修复后 `uv run pytest tests/unit/test_extension_persistence.py tests/unit/test_database.py` **44 passed**（47 条警告均为既有第三方 DeprecationWarning：alembic.ini 缺 `path_separator` 与 SQLAlchemy sqlite3 datetime adapter，非本任务引入）；`uv run ruff check migrations src/dst_manager/infrastructure/persistence tests/unit/test_extension_persistence.py` 通过；本机库经 `alembic downgrade 0005…`→`upgrade head` 往返验证补列迁移可重放。

## 2026-09-10（实施 PLAN-DM-020 Task 1：扩展契约、固定索引与生命周期注册表）

- 新增 `src/dst_manager/extensions/` 扩展平台纵向切片（ARCH-DM-006 §4、§5、§11）：`contracts.py` 定义 `HOST_CONTRACT=1`、固定 XLSX MIME 常量与 `UiContribution`/`Extension`/`ExtensionActionManifest`/`ExtensionManifest`/`BuiltinExtensionEntry`/`ExtensionDescriptor`/`ExtensionInvocation` 冻结值对象（`frozen=True, slots=True`，状态字面量与计划 Interfaces 块逐字一致）；`manifest.py` 用 Pydantic `extra="forbid"` 严格校验随包 `manifest.yaml`（SemVer、`extension_type` 仅 `builtin`、`name_key`/`description_key` 必填非空、动作 ID 唯一、`output_kind=xlsx` 必须携带固定 `media_type`、未声明 `output_kind` 不得携带 `media_type`、未知 `output_kind`/缺字段/未知字段拒绝），并拒绝 `module`/`class_name`/`script`/`command`/`entry_point` 可执行入口字段；`registry.py` 实现线程安全 `ExtensionRegistry`（`discover`/`list`/`set_enabled`/`invoke`），逐条捕获清单加载、工厂启动与停用清理失败并生成稳定诊断（`EXTENSION_MANIFEST_INVALID`/`EXTENSION_START_FAILED`/`EXTENSION_STOP_FAILED`），重复扩展 ID 保留先发现者并记录 `EXTENSION_ID_DUPLICATED`。
- 生命周期：默认启用清单经 STARTING 到 `AVAILABLE`，默认停用为 `DISABLED`（启用前重新校验宿主契约与必需能力，不通过抛 `EXTENSION_INCOMPATIBLE`/`EXTENSION_CAPABILITY_UNAVAILABLE`）；已知但当前不可用的必需能力（`workspace.snapshot.read.v1`，CapabilityBroker 属 Task 4）进入 `WAITING_DEPENDENCY`，未知能力或 `host_contract` 不匹配进入 `INCOMPATIBLE`；停用先置 draining 拒绝新调用（`EXTENSION_DISABLED`）再经 `Condition` 等待活动同步调用排空，成功后 `STOPPING`→`STOPPED`，清理失败进入 `FAILED`；首期拒绝后台资源注册，生命周期只跟踪页面贡献、动作处理器与活动调用计数。
- 新增固定索引 `extensions/builtin/index.py`（`BUILTIN_EXTENSION_INDEX` 直接引用 `create_sheet_catalog_extension` 工厂，不从 YAML 导入模块）与首个扩展 `builtin/sheet_catalog/`（`manifest.yaml` 按 ARCH-DM-006 §4.2：id `dst-manager.sheet-catalog`、version `0.1.0`、route_key `sheet-catalog`、action `export-xlsx` + `output_kind=xlsx` + 固定 MIME；`extension.py` 本任务仅 start/stop 最小生命周期外壳）。
- 测试（TDD）：新增 `tests/unit/test_extension_manifest.py`（26 例含参数化：真实随包清单契约、固定索引直引工厂 + YAML 无可执行字段、显示键必填/非空、动作 ID 唯一、xlsx 固定 MIME、media_type 依赖 output_kind、未知输出类型、缺字段/未知字段、6 种非法 SemVer、非 builtin、5 种可执行入口字段、资源缺失）与 `tests/unit/test_extension_registry.py`（11 例：真实索引发现在 WAITING_DEPENDENCY、默认启用/停用与再启用、未知扩展/未知动作、宿主契约不匹配、未知能力、工厂失败隔离、清单加载失败隔离、重复 ID 保留先发现者、停用先拒新调用再排空（多线程）、清理失败 FAILED），共 37 例。红灯先行：实现前 `uv run pytest` 两文件收集失败 `ModuleNotFoundError: No module named 'dst_manager.extensions'`（预期缺失能力）。
- 验证：`uv run pytest tests/unit/test_extension_manifest.py tests/unit/test_extension_registry.py` **37 passed**；`uv run ruff check src/dst_manager/extensions tests/unit/test_extension_manifest.py tests/unit/test_extension_registry.py` 通过；`uv run pytest tests/unit/test_database.py tests/unit/test_packaging_spec.py` 33 passed（未破坏既有导入与打包守护）。`application/service.py`、`interfaces/api.py`、`infrastructure/persistence/database.py` 零改动。

## 2026-09-10（实施 PLAN-DM-021 e2e 回归修复：对齐错误契约的夹具断言）

- 控制器裁决：Task 9 统一错误契约（I18N-11）为正确产品行为，不回退。Task 12 揭示的 12 个 e2e 失败根因全部是批次三之前夹具以虚构 code（`DRAFT_SAVE_FAILED`/`PROPERTY_VALIDATION`，不在 `message_catalog.CATALOG`）注入草稿保存失败并断言兼容 `message`"草稿保存失败"出现在摘要——该呈现已被"未知 code 显示本地化摘要 `errors.ui.unknownSummary`、原文只进诊断详情"取代。真实后端草稿保存失败仅产生 `DRAFT_CONFLICT`（409，走草稿过期专用 UX），与用例的"字段校验错误 + 输入保留"场景不匹配，故修测试：摘要断言改为本地化未知摘要、兼容原文断言不出现；草稿端点字符串 `fields` 兼容契约的字段错误/摘要跳转/错误计数断言全部保留；未新增重复的未知 code 专项用例。
- 修改 6 个 e2e 文件（`properties-buffer/layout/values/visual-evidence/workspace`、`sheets-drafts` spec），产品代码零改动。
- 新鲜验证：失败子集 6 文件 `--workers=1` 70 passed（退出码 0）；全量 `npm --prefix web run test:e2e --workers=1` **332 passed / 0 failed / 0 flaky**（6.6m，退出码 0）；`scripts/build_release.ps1` **退出码 0**（产物 `dist/releases/dst-manager-v0.3.3-win64.zip`）。
- flaky 复核：Task 12 的 2 个 flaky 隔离 8 连跑全过、无逻辑竞态；`--workers=4` 全量平行复跑 3 轮 flaky 名单逐轮随机且症状为 30s click 超时/高载几何偏差，与 `playwright.config.ts` 已记载的单一 vite dev server 高负载抖动一致，属基础设施抖动而非用例缺陷；门禁以 `--workers=1` 全量绿为准。PLAN-DM-021 剩余项 2、3 关闭。
- 2026-09-10：修正 SPEC-DM-013 G7 记录与最终验证数字对齐（状态行与门禁表改为 12/12 门全通过：e2e 332 passed / 0 failed（workers=1）、`build_release.ps1` exit 0 产物 `dst-manager-v0.3.3-win64.zip`，移除「e2e 回归修复 + 发布构建补跑」未关闭事项；G8/G9 维持未关闭）。
- 2026-09-10：新增概念解读备忘 `.planning/memos/dst-manager/2026-09-10-prd-dm-001-artifact-and-change-proposal.md`，整理 PRD-DM-001 中 `Artifact` 与 `Change Proposal` 的通俗解释与实例。备忘整理事实依据：PRD-DM-001 §2 决策 4/5、§7、§8.1、EXT-005/006/008/011、AC-005，ARCH-DM-006 §9.1/§9.3，SPEC-DM-012 §42，以及 2026-09-07 审查备忘。仅新增阅读笔记，未修改任何源码、测试或正式文档；备忘注明自身非权威定义，冲突时以 PRD/ARCH/SPEC 正文为准。

## 2026-09-09（实施 PLAN-DM-021 Task 12：打包、完整验证、G9 与状态收口）

- 打包静态守护扩展 `tests/unit/test_packaging_spec.py`（+4 项）：spec datas 必含 `web\dist`；生产 JS 产物同时嵌入 zh-CN/en-US 全部 8 域语言资源（逐域最长文案基准）；产物不回指 `web/src`/`node_modules`/绝对盘符路径；`web/src/i18n/index.ts` 仅构建期静态装配 16 个域资源、无 locales 动态 import/fetch。与既有 5 项共 9 项通过；在 Task 12 新鲜 `npm run build` 产物上复跑通过。当前产物本就合规，红验证经突变测试证实（剥离 bundle 内 en-US 最长文案 → 失败，还原 → 通过）。
- 全量新鲜验证（Task 12 Step 2 顺序，日志存 `.superpowers` 不入库）：`uv sync --dev`、`ruff check .`、`uv run pytest`（**779 passed / 72 skipped**）、`uv lock --check`、`alembic upgrade head`、`npm ci`、`check:i18n`（**759 键 / 8 域**）、`test:unit`（**28 passed**）、`check:api`、`build` 全部退出码 0；**`test:e2e` 退出码 1（318 passed / 12 failed / 2 flaky）**；`build_release.ps1` 按失败即停未执行。
- 定位批次三遗留 e2e 回归（非本任务引入，`--workers=1` 复跑失败子集仍 12 failed）：Task 9/10 按 I18N-11 改为"已知 code 按 `message_key` 渲染、未知 code 显示本地化摘要 `errors.ui.unknownSummary` 且原文只进诊断详情"，而批次三之前的 e2e 夹具以虚构 code `DRAFT_SAVE_FAILED` 注入草稿保存失败并断言兼容 `message`"草稿保存失败"出现在摘要，与现契约冲突。修复裁决（夹具改真实 code + 新断言，或后端真实返回专用 code 并登记目录）留待后续任务，不得以运行时回退掩盖。
- Step 3 反查（I18N-01～18 自动化部分）：locale 不入 migrations/application/infrastructure（`worker.py` `"/l zh-CN"` 为计划前既有 Core Console 参数）；`select_file` 仅新 `file_kind` 签名；registry 无中文元数据；`check:i18n` 守护未登记硬编码；I18N-16 文件不变量——对去敏副本 `sample/project2`（1 DST + 5 DWG）以真实后端执行打开 + `ui_locale` zh-CN→en-US→zh-CN 设置事务，SHA-256 与 mtime_ns 全部零变化，`settings.json` 只落隔离目录。
- G9 准备：新增 [MEMO-DM-026 填空清单](.planning/memos/dst-manager/PLAN-DM-021-multilingual-g9-checklist.md)（中文/英文/非中英显示语言、显式覆盖、读取失败降级、保存成功/失败、四类过滤器与取消、英文窄屏/200%、发布与任务不中断、物理 hash 复验；结果字段留空）。计划状态保持 **`active`**，剩余项：D3 文案裁决（G8）、批次三 e2e 回归修复 + 全量 e2e 绿、`build_release.ps1` 补跑、G9 真实桌面执行、I18N-17 窗口收尾（`DraftActionsPanel.vue` 旧草稿 `label` 回退与诊断 `message` 兼容字段）。

## 2026-09-09（实施 PLAN-DM-021 Task 11：英文关键矩阵、响应式与业务不变量）

- 新增 `web/tests/e2e/i18n-workflows.spec.ts`（3 例）：zh-CN 与 en-US 各跑一遍 启动→设置→打开→图纸→属性→预览→发布→任务→修订 九域关键矩阵（语义键渲染 + 用户数据原样，I18N-07/16）；语言切换不变量——切换前后 workspace 标识（DST 路径 title/顶栏名）、未提交输入、选区、草稿计数、任务状态、修订哈希一致，发布不重跑（execute 仅一次）、SSE 事件 URL 不携带语言（I18N-06/12）。
- 新增 `web/tests/e2e/i18n-visual-evidence.spec.ts`（7 例）：1440×900 浅色、900×768 深色、200% 缩放（CDP 720×450 CSS 视口 + 2x 渲染等价浏览器 200%）三组合断言无整页横滚、主操作可达、长错误完整可读（本地化摘要 + `overflow-wrap:anywhere` 可展开原文）、表格只在自身容器横滚；Tab 到达主操作、Esc 关闭设置并归还焦点、设置模态焦点圈闭、422 错误摘要聚焦并链接字段（英文）、状态不只靠颜色（禁用属性/文字化原因/计数文本/`role=status`/文本徽章）（I18N-15、§3.5、§5.3）。
- 布局缺陷最小修复（落所属组件，未改全局 `style.css`）：`web/src/layout/TaskOverlay.vue` 收起态任务侧栏内容溢出致英文界面整页横滚 54px（1440×900 / 900×768 / 200% 均复现），`.task-rail` 加 `min-width:0;overflow:hidden`、按钮加 `overflow-wrap:anywhere`；`web/src/components/settings/SettingsDialog.vue` 补 `@keydown` Tab/Shift+Tab 显式回绕，消除 showModal 原生圈闭尾→首回绕一拍落到 body 的缺口（Esc 归还焦点行为不变）。
- Task 10 审查绑定修复：`web/src/composables/useSheetColumns.ts` 对 `SHEET_PREFERENCES_INVALID` 不再透传桥原始中文 message，改按 Task 9 错误目录 `message_key+params` 经 `localizedError` 渲染（与 App.vue 壳桥错误同模式）；`web/tests/e2e/sheets-columns.spec.ts` 新增中英文渲染断言（本地化文案出现、原文不出现）。
- G8 设计 QA 取证：以 `npm run build` 生产产物 + 与 G4 相同虚构数据/视口/主题/状态采集生产截图（`.planning/memos/dst-manager/assets/PLAN-DM-021/production-{zh-CN-light-1440x900,en-US-dark-900x768}.png`），与两张冻结截图逐项比对记录于 `.planning/memos/dst-manager/PLAN-DM-021-multilingual-design-qa.md`（MEMO-DM-025）：结构/双语内容/语言选择语义/主题一致或属已接受差异，无未关闭 P0/P1；低优先级文案差异 D3（UI language vs Demo 的 Display language）提请 Task 12 用户裁决。F1～F3 修复后重取证，采集脚本未进入提交树。
- Files 清单外必要增量（已披露）：`web/src/layout/TaskOverlay.vue`、`web/src/components/settings/SettingsDialog.vue`（Step 3 布局/焦点最小修复落点）、`web/tests/e2e/sheets-columns.spec.ts`（绑定修复测试）、`web/src/composables/useSheetColumns.ts`（绑定修复，Task 10 审查授权）。
- 验证：`npm --prefix web run test:unit` 28 passed；`npm --prefix web run build`（check:api + check:i18n 759 键对称 + vue-tsc + vite）通过；`npm --prefix web run test:e2e -- tests/e2e/i18n-workflows.spec.ts tests/e2e/i18n-visual-evidence.spec.ts --workers=1` 多轮通过（新增 spec 各自 ≥2 连续全绿）；全量 `npm --prefix web run test:e2e` 320 passed / 0 failed。Python 侧零改动（未涉及 pytest/ruff）。

## 2026-09-09（实施 PLAN-DM-021 Task 10：语言包完整性门禁与兼容层清理）

- 语言包门禁升级（I18N-14）：`web/scripts/check-i18n.mjs` 从最小键对称版扩展为四类约束——中英域文件集合一致、域内键集合一致（缺键/多键/域内重复键，报告 `<域>.<键>` 与资源文件路径）、每个键的命名插值参数（`{name}`）集合中英严格一致、`web/src` 硬编码中文扫描（词法剥离 `//`、`/* */`、`<!-- -->` 注释并按前一有效 token 识别正则字面量，字符串/模板文本/属性值出现 `[一-龥]` 即违规并报告 `文件:行`；语言资源目录、`*.d.ts` 生成产物与 vitest `*.test.ts`（不进生产构建）不入扫描范围）。任一违规非零退出并已纳入 `build`。顺带修复旧版单 Set 压平导致的跨域同名键静默合并（`revisions.confirm.title/message` ↔ `settings.confirm.*`、`properties.view.regionAria` ↔ `sheets.*`，键总数 756→759 的口径修正）。
- 新增 `web/src/i18n/hardcoded-allowlist.json`：当前为空数组——全仓扫描后无属于「用户数据示例/协议常量/必要品牌名」的豁免项；两处开发态诊断字符串（`i18n/index.ts` 设置读取超时、`useSettings.ts` 快照未加载）改写英文（开发者诊断，非界面文案），不占用豁免清单。
- 兼容层删除（I18N-17，全仓 rg 确认无调用后执行）：后端 `SettingsItemMeta` 删除 `label/category/file_filter` 与 `EXE_FILTER`/`DLL_FILTER` 常量，`_ENUM_META` 只保留 `text_key`；`SettingsItemModel`/`EnumOptionModel` 契约删除 `label/category/file_filter/text`；`api.py` 序列化同步收敛；`settings/runtime.py` 422 兼容 `message` 前缀由中文 label 改为稳定 `meta.key`（兼容 `message` 字段本身按架构窗口保留）。前端 `web/src/api/settings.ts` 删除 `label/category/fileFilter/text` 接口与映射（labelKey/categoryKey/textKey 转必填），`SettingsFormRow.vue`/`SettingsDialog.vue` 删除兼容中文回退主路径。ARCH-DM-005 §7 一处 `messageKey` 笔误按控制器裁决改为 `message_key`（与全文一致，仅文档）。草稿 `DraftAction.label` 兼容（Task 8 迁移窗口）不在本任务 Step 3 清单，按计划保留。
- 测试（TDD）：门禁红灯夹具四类先行——缺键（en-US 删 `close`，旧版已拦截但定位无域/文件）、多键（en-US 加 `extraOnlyKey`）、命名参数不一致（en-US `settings.title` 添 `{bogusParam}`，旧版 exit 0 证明能力缺失）、硬编码中文（`format.ts` 加字符串字面量，旧版 exit 0）；实现后四类均 exit 1 且定位域/键/文件，夹具随即还原。`test_settings_registry.py` 增 `test_no_legacy_localized_fields_remain` 并改断言稳定键唯一描述、枚举选项无 `text`；`test_api_settings.py` 契约改 key-only 并断言 `label/category/file_filter/text` 不在响应；`test_settings_runtime.py` 改以稳定 key 判别 params 无本地化 label。
- 验证：`uv run pytest tests/unit/test_settings_registry.py tests/unit/test_settings_resolver.py tests/unit/test_settings_runtime.py tests/unit/test_settings_store.py tests/integration/test_api_settings.py tests/integration/test_api.py tests/unit/test_shell.py tests/unit/test_shell_workspace.py tests/unit/test_message_catalog.py tests/unit/test_config.py tests/unit/test_worker_settings_propagation.py -q` 230 passed；`uv run ruff check .` 通过；`npm --prefix web run test:unit` 28 passed；`npm --prefix web run build`（check:api + check:i18n + vue-tsc + vite）通过（`generate:api` 再生零差异——settings 端点本就不在业务 OpenAPI 内）；`npm --prefix web run test:e2e -- tests/e2e/settings-dialog.spec.ts --workers=1` 17 passed。反向扫描（`\blabel\b|\bcategory\b|file_filter|select_file\(\[|DIAG_TEXTS|[一-龥]` over `src/dst_manager web/src`）：`select_file\(\[` 与 `DIAG_TEXTS` 零命中；web/src 余留 `label`/`category` 均为 HTML `<label>`/`aria-label`、草稿批次 `category` 参数、图纸/树/列选项用户数据 `label`、草稿动作兼容 `label`（Task 8 窗口）；src/dst_manager 余留中文为代码注释与结构化错误兼容 `message`/诊断原文（架构窗口内保留，已知错误前端只按 `message_key` 渲染）。
- Files 清单外必要增量（已披露）：`src/dst_manager/settings/runtime.py`（删除 `meta.label` 后 422 兼容 message 改用 `meta.key`，否则属性不存在）、`web/src/components/settings/SettingsFormRow.vue`/`SettingsDialog.vue`（前端兼容中文回退主路径删除的落点，属 Step 3 范围）、`web/src/i18n/bootstrap.test.ts`/`web/src/composables/useSettings.test.ts`（夹具补 labelKey/categoryKey 必填键）、`web/src/composables/useSettings.ts`/`web/src/i18n/index.ts`（两处开发态诊断 Error 文本改英文，避免超范围豁免项）、`tests/unit/test_settings_runtime.py`（同上测试修订）。

## 2026-09-09（修复 PLAN-DM-021 语言迁移批次遗留的三处 main.spec e2e 回归）

- 根因定位（worktree 检出 b159c86 复跑实证：三处失败均先于 Task 9 提交 fabb4be 存在，Task 8 检查点「全量绿」结论对这三例不成立）：①`失败任务显示逐 DWG 详情并可安全重试`——b159c86 重写断言时误写「第 0 次」，而重试响应 attempt=1 且任务域契约（I18N-12）按 payload 原值渲染「第 1 次」（与同批 SSE 用例口径一致），属过期测试期望，改断言为「第 1 次」；②`壳桥延迟注入`——bootstrap 先取设置再挂载（I18N-04）后首帧晚于 load+30ms 的模拟注入点，降级界面从未渲染即切有壳态（注入早于挂载时应用直接有壳起步，产品行为正确），测试夹具改为等 `#app` 挂载（降级界面已渲染）再延迟 30ms 注入，`pywebviewready` 晚到切换断言全部保留；③`语言切换不变量`——切 en-US 后图纸集名称输入可访问名合法变为 "Sheet set name"（label/for 经 fieldId(key) 稳定绑定，值「改名后的图纸集」实际保留，见失败快照），属过期定位器，改双语 label 正则语言容忍定位，不变量断言（active tab/工作区/未提交输入值）全部保留。产品代码零改动。
- 验证：`npm --prefix web run test:e2e -- tests/e2e/main.spec.ts --workers=1` 74 passed / 0 failed。

## 2026-09-09（实施 PLAN-DM-021 Task 9：已知 API/CAD/Shell 错误结构化）

- 新增接口层错误目录 `src/dst_manager/interfaces/message_catalog.py`（I18N-11 / ARCH-DM-005 §6.2）：枚举登记全部已知稳定 code——26 个 `ApplicationError`、37 个 `AcsmValidationError`（含 `ACSMSHEET/SUBSET_NOT_FOUND|DUPLICATED` 动态族具体值）、4 个设置 409/422 外层 code、6 个 ShellBridge code，共 73 项；每项对应唯一 `message_key`、参数 schema（str/int/bool/list 白名单）与可选详情提取参数，不发明新业务错误码。`ApplicationError` 增加可选结构化 `params`（仅稳定值，默认 None，向后兼容）；`ApplicationError`/`AcsmValidationError` 统一 handler 与设置 409 改经 `error_payload` 输出 `{code, message_key, params, message}`（未知 code 不携带 `message_key`，原文仅作诊断）。DST 诊断、任务状态与 CSV 诊断 code 不在目录（按功能域渐进迁移）。
- 新增 `src/dst_manager/interfaces/error_contracts.py`（`ErrorPayloadModel`，参数类型白名单复用 `settings/errors.py` 的 `ParamValue`；`responses.py` 已达 516 行软上限，按计划授权独立成模块）。`interfaces/shell.py` 全部 `{ok:false}` 错误改经 `shell_error` 输出统一结构，保留 `code`/`message` 兼容。
- 前端（I18N-11）：`web/src/api/client.ts` 解析 `message_key/params`——已知错误按 key+params 渲染并忽略兼容 `message`（原文仅存 `rawMessage`）；未知错误显示本地化摘要，原文只写入新增 `lastErrorDiagnostic`，仅经 `App.vue` 错误提示下可展开的「原始错误详情」呈现（`style.css` 补 `.error-raw` 换行规则防溢出）。新增错误域语言资源 `web/src/i18n/locales/{zh-CN,en-US}/errors.ts`（74 键对称，含 `ui.unknownSummary`/`ui.diagnosticsDetails`）并注册进唯一 i18n 实例（756 键 / 8 域，`check:i18n` 通过）；`web/src/api/shell.ts` `ShellResult` 补 `message_key/params`，`App.vue` 壳桥错误改按 key 渲染（未知 code 回退原文）。路径、图号、属性名/值、错误码与协议字段保持原样（I18N-16）；locale/翻译资源不进入 domain/application（`message_catalog` 无任何语言环境依赖，application/domain 无 `message_catalog`/`message_key` 引用，测试断言守护）。
- 测试（TDD，红灯先行：stash 源码实现后运行新增测试确认收集失败/断言失败）：新增 `tests/unit/test_message_catalog.py` 16 例——73 个 code 清单锁定、`message_key` 唯一性、参数 schema 白名单、中英资源键覆盖与翻译占位符 ↔ 参数 schema 严格对称、统一负载形态（已知/未知/详情提取/越界 params 拒绝/显式 params 优先）、Shell 桥结构、目录仅在接口层；`tests/integration/test_api.py` 新增已知错误（`DST_NOT_FOUND` 带路径参数）、CAD 结构校验（损坏 DST → `XML_ROOT_INVALID`）与未知 code（`FUTURE_CODE` 不带 key）3 例；`tests/unit/test_shell.py` 新增桥错误 `message_key` 3 例；`main.spec.ts` 新增已知错误按 key 渲染并忽略兼容 message、未知错误摘要+可展开诊断详情 2 例。
- 验证：`uv run pytest tests/unit/test_message_catalog.py tests/integration/test_api.py tests/unit/test_shell.py -q` 123 passed；全量 `uv run pytest -q` 通过（中文基线，0 失败）；`uv run ruff check .` 通过；`uv lock --check` 通过；`npm run test:unit` 28 passed；`npm run build`（check:api + check:i18n + vue-tsc + vite）通过；`npm run test:e2e -- tests/e2e/main.spec.ts --workers=1` 72 passed / 2 failed——`失败任务显示逐 DWG 详情`（main.spec.ts:569）与`语言切换不变量`（main.spec.ts:1122）为分支既有失败，经 stash 本任务全部改动复跑确认与 Task 9 无关。
- Files 清单外必要增量（已披露）：`src/dst_manager/interfaces/error_contracts.py`（计划授权的容量拆分落点）、`web/src/i18n/index.ts`（errors 域注册）、`web/src/api/shell.ts`（ShellResult 类型补 message_key/params）、`web/src/App.vue`（未知错误可展开诊断详情 + 壳桥错误按 key 渲染，共 3 行级改动）、`web/src/style.css`（`.error-raw` 一条规则）。

## 2026-09-09（实施 PLAN-DM-021 Task 8：修订、预览、修复、草稿与任务状态迁移）

- 新增修订与任务域语言资源 `web/src/i18n/locales/{zh-CN,en-US}/revisions.ts`、`jobs.ts`（键对称）并注册进唯一 i18n 实例（681 键 / 7 域，`check:i18n` 通过）；`common` 域新增共享 `cadOperation` 映射与 `listSeparator`，`shell` 域新增 `draft`/`preview`/`repair` 分节（草稿栈、完整变更预览与修复面板属外壳浮层/操作栏域）。
- 迁移（I18N-07/08）：`RevisionsView.vue`（tabpanel aria 与空状态卡）、`RevisionHistoryPanel.vue`（表头、恢复入口、恢复确认与冲突提示；时间经新增 `web/src/i18n/format.ts` 的 `formatDateTime` 按 `Intl` 生效语言格式化，Task 5 遗留项落地）、`PreviewPanel.vue`（全部标题/表头/估算摘要与来源样本复数插值、数量前沿、诊断行 `{code}：{message}` 分隔取自语言包）、`RepairStatusPanel.vue`（状态码→语义键、修复/阻断计数、前后值差异、预览摘要）、`JobStatusPanel.vue`（任务标题/尝试次数/状态码→语义键、逐 DWG 表头、起止时间本地化、耗时插值）、`DraftActionsPanel.vue`（待处理/动作计数、清空/移除、过期原因连接符取语言包、`{count} 条命令` 复数）全部改用 `$t`/`useI18n`；composables：`useJobMonitor.ts` 终态 toast 与 NEEDS_REVIEW 禁止重试文案改语义键、`connectionMode` 存稳定 code（`sse`/`polling`）展示层映射；`useRepair.ts`/`useRestore.ts` 确认框与上下文失效文案改语义键。SSE/任务 payload 保持稳定状态码（I18N-12），未知状态码回退原码；错误码、DWG 名、路径、哈希、属性名/值与后端 suggestion 保持原样（I18N-16）。
- 绑定修复（Tasks 5-7 裁决，I18N-12「语言不得写入 job、draft」）：草稿动作标签由创建时 `t(...)` 本地化文本改为持久化稳定 `label_key` + 可选命名 `params`。存储侧：`App.vue` `addCommand`/`addCommandBatch`/`applyBulkBatch`（label_key + `{name,count}` 参数）、`useSheetEditor.ts` 四处 `submitCommands` 调用点、`usePropertiesWorkspace.ts` `update_sheet_set` 调用点，`features/sheets/types.ts` `SubmitCommands` 签名改为 `DraftActionLabel`；渲染侧：`DraftActionsPanel.vue` 按存储 `label_key`(+params) 在渲染期翻译，旧版本草稿的本地化 `label` 仅迁移窗口内回退展示。已 rg 核验：`draftActions` 仅两处构造点（`App.vue:472/481`）均存 `label_key`，全部 5 处 `submitCommands`/`addCommandBatch` 调用点传稳定键，无其他创建时 `t()` 标签流入。
- 草稿后端最小扩展（核验结论：草稿并非不透明存储——`DraftPutRequest`（`interfaces/contracts.py`）与 `DraftStore._validate_draft_document`（`infrastructure/drafts.py`）均按固定键集校验 `label` 非空文本）：`DraftAction`/`DraftActionResponse` 增加可选 `label_key`、`params`（值仅限字符串/数量标量），`label` 与 `label_key` 必须二选一，`params` 形状违规按损坏草稿隔离；`label_key` 限定 ASCII 点分消息键形态（`^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$`，contracts 与 drafts 校验处同步），任意本地化句子/含空格标点/非点分值一律拒绝，杜绝「语言经 label_key 写入草稿」；schema_version 与端点契约不变。`web/src/api/openapi.json`/`schema.d.ts` 经 `generate:api` 再生。
- 评审修复（Important）：`tests/unit/test_drafts.py` 补 `label_key` 键格式用例——中文句子（`更新图纸属性（含中文）`）、含空格/标点、非点分、数字开头共 5 种隔离用例与 `shell.commands.updateSheetProperties` 合法键用例；`tests/unit/test_drafts.py` 35 passed，`tests/integration/test_api.py` 与全量 `uv run pytest -q`、`npm run build` 复跑通过。
- 测试（TDD）：`tests/unit/test_drafts.py` 新增 label_key+params 合法、旧 `label` 兼容加载与 5 种形状违规隔离用例（红灯先行）；`main.spec.ts` 新增 8 例红灯先行：草稿 PUT 断言 `label_key`/`params` 且动作栈随语言切换双语渲染（绑定修复）、英文完整变更预览（字段名/路径/哈希原样）、英文任务状态+错误码原样+安全重试、英文 NEEDS_REVIEW 锁定与禁止重试提示、语言切换不变量（QUEUED→RUNNING→FAILED→重试 NEEDS_REVIEW 跨切换状态保持、SSE 事件 URL 不携带语言）、英文修订历史+日期本地化+恢复冲突提示、修订空态、英文修复状态全流程；既有两处中文断言随日期/状态本地化更新（任务起止时间改 `Intl` zh-CN 格式比对、重试后 `/QUEUED/` 改语义键文案）。
- 验证：`npm run test:unit` 28 passed；`npm run build`（check:api + check:i18n + vue-tsc + vite）通过；全量 `npm run test:e2e` 313 passed（2.6m）；`uv run ruff check` 与全量 `uv run pytest -q` 通过（Python 中文全量基线）。
- Files 清单外必要增量（已披露）：绑定修复触及 `web/src/features/sheets/types.ts`（签名）、`web/src/api/openapi.json`+`schema.d.ts`（再生）、后端 `src/dst_manager/interfaces/contracts.py`、`responses.py`、`src/dst_manager/infrastructure/drafts.py`、`tests/unit/test_drafts.py`；日期本地化新增 `web/src/i18n/format.ts`；`web/src/i18n/index.ts` 注册 revisions/jobs 域；`common.ts`/`shell.ts`（中英）按域新增必要键。

## 2026-09-09（实施 PLAN-DM-021 Task 7：属性工作区迁移）

- 新增属性域语言资源 `web/src/i18n/locales/{zh-CN,en-US}/properties.ts`（132 键对称）并注册进唯一 i18n 实例（548 键 / 5 域，`check:i18n` 通过）。
- 属性工作区迁移（I18N-07）：`PropertiesView.vue`（分区 ARIA、错误摘要字段项「{label}：{message}」改语义键插值）、`PropertyDefinitionPanel.vue`（面板 ARIA/折叠开关、标题计数、查询/作用域筛选选项、新增区标签/提示/错误、加入草稿提示（作用域×名称命名参数，取消调用点拼接）、「查看字段」）、`PropertyDefinitionTable.vue`（表头列名改 `labelKey` 语义键、空默认值/展开收起/删除 aria（作用域与名称插值）、两种空态、清除查询、分页页脚「匹配 {matched} 项 · 第 {page} / {total} 页」）、`PropertyValuePanel.vue`（标题计数、dirty/pending/error 计数与三态徽标、提交摘要、搜索三模式与仅看修改、匹配计数与隐藏后缀、字段 aria（`属性 {name}`，属性名原样）、值对照入口、撤回、暂留提示、两种空态、展开编辑对话框）、`PropertyValueCompareDialog.vue`（对照提示、缺失/空文本占位、关闭按钮）全部改用 `$t`/`useI18n`。
- composables 迁移：`usePropertiesWorkspace.ts` 无活动工作区（复用 `shell.errors.noWorkspace`）、失效字段阻断提示、批次标签（复用 `shell.commands.updateSheetSet`）、加入草稿失败（复用 `shell.errors.addDraftFailed`）、属性名称为空提示、三选一摘要（`properties.guard.summary`）；`useCsvImport.ts` UTF-8 编码/选择文件/分批阻断/预览失效提示，强确认标题/正文/确认文案与影响行（稳定 action 码走 `CSV_ACTION_KEYS` 语义键映射，句子用命名参数插值）。属性名、属性值、CSV 头与 CSV 内容保持原样（I18N-16）；命令 payload 与后端校验契约未变；`features/properties/model.ts` 无用户可见文案，未改动（稳定 kind/status 与 `PROPERTY_BUFFER_STALE` 原样）。
- 测试（TDD）：三个属性 spec 新增 4 例英文关键矩阵红灯先行（工作区骨架/定义面板/空态、值面板三态/值对照/展开编辑、CSV 流程/强确认/预览行），断言属性名与值、CSV 头与 CSV 内容、诊断消息不被翻译，导入请求体 CSV 原样；语言来源沿用 page 级 `/api/settings` 路由（不写共享 settings.json）。
- 验证：三个聚焦 spec `--workers=1` 39 passed；`properties-*.spec.ts` 全量 8 个 spec 92 passed（1 例既有基础设施抖动重跑通过）；`npm run test:unit` 28 passed；`npm run build`（check:api + check:i18n + vue-tsc + vite）通过。
- Files 清单外必要增量（已披露）：`web/src/i18n/index.ts` 注册 properties 域。

## 2026-09-09（实施 PLAN-DM-021 Task 6：图纸工作区迁移）

- 新增图纸域语言资源 `web/src/i18n/locales/{zh-CN,en-US}/sheets.ts`（179 键对称）并注册进唯一 i18n 实例（416 键 / 4 域，`check:i18n` 通过）。
- 图纸工作区迁移（I18N-07）：`SheetsView.vue`（树根计数插值、抽屉开关 ARIA、空集/无范围/无匹配引导、隐藏目标提示、继续加载）、`SheetTable.vue`（表格/窗口 ARIA、全选与行选择 aria（图号插值）、状态枚举 待变更/阻断/正常/诊断、编辑属性/删除）、`SheetToolbar.vue`（计数、已加载行数、三类操作入口、搜索 label/placeholder、低频筛选与选项、可清除条件标签（稳定筛选值→语义键映射）、选择条摘要、批量控件）、`SheetTree.vue`（树 ARIA、全部图纸节点、节点计数、展开/收起子集 aria）、`SheetOperationForm.vue`（三类表单标题映射、全部字段/选项/按钮/提示/状态行）、`SheetPropertyEditor.vue`（标题/提示/搜索/分页计数/状态文本/错误摘要/属性字段 label（`属性 {name}`）/页脚按钮）、`ColumnSettings.vue`（入口/面板/提示/固定标记/新字段/恢复默认）全部改用 `$t`/`useI18n`。
- composables 与 features 迁移：`useSheetsWorkspace.ts` 修剪提示（复数插值）；`useSheetColumns.ts` 内置列名与「所属子集（当前范围）」改语义键映射（属性列保留服务端原名），列配置保存/读取失败提示；`useSheetEditor.ts` 编辑主题（`图纸 {number}`/`子集 {name}`）、三选一摘要（`{subject} 属性编辑` 命名参数）、全部提交校验提示与批次标签（复用 `shell.commands.*`/`shell.errors.addDraftFailed`）；`useSheetProjection.ts`/`projection.ts`/`commands.ts`（非组件模块经唯一实例 `i18n.global.t`）投影缺失/不可执行与参照失效错误。命令 payload、字段名与后端校验契约未变；图号、标题、路径、属性名/值、错误码保持原样（I18N-16）。
- 测试（TDD）：四个图纸 spec 新增 5 例英文关键矩阵红灯先行（导航/计数/筛选/状态、空集引导、属性编辑器+错误摘要+三选一、显示列配置、选择条+批量入草稿），断言图号、标题、路径、图纸集名、子集名、属性名/值与后端字段消息不被翻译，命令 payload 保持原契约；`main.spec.ts` 两处英文用例的图纸域控件名随迁移更新为英文名（Task 5 时该域未迁移，暂用中文名）。语言来源沿用 page 级 `/api/settings` 路由（不写共享 settings.json）。
- 验证：四个聚焦 spec `--workers=1` 63 passed；`sheets-*.spec.ts` 全量 136 passed；`main.spec.ts`+`settings-dialog.spec.ts` 81 passed；`npm run test:unit` 28 passed；`npm run build`（check:api + check:i18n + vue-tsc + vite）通过。
- Files 清单外必要增量（已披露）：`web/src/i18n/index.ts` 注册 sheets 域；`web/tests/e2e/main.spec.ts` 两处英文用例控件名更新（图纸域双语化后的必要跟随）。

## 2026-09-09（实施 PLAN-DM-021 Task 5：共享外壳、通用组件与格式化能力）

- 新增外壳域语言资源 `web/src/i18n/locales/{zh-CN,en-US}/shell.ts`（约 150 键对称）并注册进唯一 i18n 实例（237 键 / 3 域，`check:i18n` 通过）：覆盖顶栏（副标题、状态胶囊、文件夹/关闭/主题/设置入口及 ARIA、tooltip）、标签栏（分区/页签/预留位）、操作栏（草稿芯片计数插值、撤销/重做/预览/写入、草稿动作栈 ARIA）、任务浮层（页签/入口 ARIA、阻断诊断 aria-description、诊断计数、复制按钮、空状态）、欢迎区、通用模态与 Toast。
- 共享外壳迁移（I18N-07）：`TopBar.vue`/`TabBar.vue`/`ActionDock.vue`/`TaskOverlay.vue`/`WelcomeView.vue` 模板全部改用 `$t`（页签 label 改为语义键 `labelKey`，稳定 id/枚举不进文案）；`UnsavedInputDialog.vue`/`ToastHost.vue`（新增关闭按钮 aria-label）双语化。
- 通用组件与调用点迁移：`ConfirmModal.vue` 的 `reversibility` 由中文字面量类型 `"可撤销"|"不可逆"` 改为稳定语义值 `"reversible"|"irreversible"`，显示文本与危险勾选说明（命名参数）经语言包渲染，取消/确认缺省文案也走语言包；`useConfirm.ts` 状态层不再持有默认文案。`App.vue`（仅调用点）迁移恢复横幅（复数/计数插值）、加载/恢复状态、全部 `error` 提示、`saveStatusText`、操作栏禁用原因矩阵、命令标签映射（稳定命令类型→语义键）、8 处确认框与 5 处 Toast（删除图纸/删除子集/清空属性值/删除属性定义/关闭 CSV/发布/关闭工作区/放弃冲突，含批量标签与摘要），动态句子全部用命名参数，无调用点拼接。
- 语言切换不变量（I18N-06）：切换前后 active tab、工作区身份与未提交输入保持不变（响应式重绘，不重建业务状态）；用户数据（图纸编号、图纸集名称、路径、错误码、原始消息）保持原样。
- 测试（TDD）：`main.spec.ts` 新增 5 例红灯先行（英文外壳/欢迎区/标签栏/操作栏渲染、草稿恢复横幅计数+快捷键提示+任务浮层空状态、删除确认框与 Toast 双语且图纸编号不翻译、发布确认模态不可逆标记与危险勾选、保存成功切换前后 active tab/工作区/输入值不变）；英文用例以 page 级 `/api/settings` 路由提供语言来源（不写共享 settings.json，避免并行 worker 串扰；真实设置事务仍由 settings-dialog.spec 真实后端承担），切换不变量用例仅拦截 PUT 驱动前端 applyLocale；既有中文用例同步更新两处（`selectDst` 按钮名参数化、Toast 关闭按钮 aria-label）。验证：`npm run test:e2e -- tests/e2e/main.spec.ts --workers=1` 64 passed，`properties-buffer`/`sheets-drafts`/`sheets-editing` 抽样 38 passed，`npm run test:unit` 28 passed，`npm run build`（check:api + check:i18n + vue-tsc + vite）通过。
- Files 清单外必要增量（已披露）：`web/src/i18n/index.ts` 注册 shell 域；`useCsvImport.ts`/`useRepair.ts`/`useRestore.ts` 各 1 处 `reversibility:"不可逆"` 字面量随类型契约改为 `"irreversible"`（显示文本不变）。

## 2026-09-09（实施 PLAN-DM-021 Task 4：ShellBridge 固定文件种类与本地化描述）

- `src/dst_manager/interfaces/shell.py` 原生文件选择契约收紧（安全红线）：`select_file` 签名由 `file_types: list[str]`（前端任意过滤器字符串）改为 `select_file(file_kind: FileKind, localized_description: str)`，`FileKind = Literal["dst", "template", "exe", "dll"]`；扩展名白名单只由壳侧 `_FILE_KIND_PATTERNS` 按 kind 固定拼接（dst→`*.dst`、template→`*.dwg;*.dwt`、exe→`*.exe`、dll→`*.dll`），未知 kind 抛 `ValueError` 且不弹对话框；本地化描述经 `_sanitize_description` 净化为 pywebview `parse_file_type` 允许的 `[\w ]+` 文本——伪造 `危险 (*.bat)` 退化为纯文本、不能扩大白名单，也不会在对话框弹出前抛 `ValueError`；取消返回 None、无窗口报明确错误不变。文件夹选择不经 `file_kind`，维持独立 `select_folder`（FOLDER_DIALOG 无过滤器概念）。
- `web/src/api/shell.ts`：删除 `DST_FILE_FILTERS`/`TEMPLATE_FILE_FILTERS`/`EXE_FILE_FILTERS`/`DLL_FILE_FILTERS` 过滤器常量数组（同包升级不保留旧 `file_types` 任意字符串签名），新增 `ShellFileKind` 类型；`selectSettingsPath(kind, localizedDescription)` 按 `file_kind` 传参且描述参数化，三态语义（undefined=桥/方法缺失、null=取消、string=路径）与 folder 走 `select_folder` 的行为不变。
- `web/src/i18n/locales/{zh-CN,en-US}/common.ts` 新增 `shell.fileKinds.{dst,template,exe,dll}` 四键（对话框描述专用，85 键对称）：中英文只改变描述文本，白名单与语言无关。设置行内的过滤器提示 `settings.fileFilters.*` 保持原样（冻结 Demo 文案不变）。
- `web/src/App.vue` 四处选择文件调用（打开 DST、新增图纸模板、新建子集布局/基础模板）全部改为 `select_file(kind, t("common.shell.fileKinds.*"))`；`web/src/components/settings/SettingsDialog.vue` `onBrowse` 以注册表 `file_kind` 取代过滤器文本解析，exe/dll 描述取自语言包，folder（无 `file_kind` 的 path 项）走 `select_folder`。设置中心 exe/dll"浏览"仍可用。
- 测试（TDD）：红灯（Python 14 例失败、TS 1 例失败）→ 最小实现 → 绿灯。`tests/unit/test_shell.py` 重写 select_file 契约：四种 kind 的固定白名单与 `parse_file_type` 格式契约（取代原前端源码过滤器正则守护）、未知 kind（含 `folder`/`bat`/空串/None/列表）拒绝且不弹对话框、伪造描述不能扩大白名单、取消 None、无窗口明确错误，并断言 `web/src/api/shell.ts` 代码内不再持有过滤器常量；新增 `web/src/api/shell.test.ts` 5 例（file_kind 传参+描述参数化、folder 走 select_folder、三态语义、旧壳降级）；e2e 随调用点迁移：`settings-dialog.spec.ts` 新增 exe/dll 浏览断言（注入记录型假桥，中英文各点一次，断言固定种类不变、描述随语言包切换），`main.spec.ts`/`sheets-folder.spec.ts` 假桥更新为新签名并在非 .dst 用例记录 `select_file` 调用参数（kind=dst + 中文描述）。验证：`uv run pytest tests/unit/test_shell.py -q` 33 passed、全量 `tests/unit` 654 passed/4 skipped、`uv run ruff check` 通过、`npm run test:unit` 28 passed、e2e（main + sheets-folder + settings-dialog，`--workers=1`）80 passed、`npm run build`（check:api + check:i18n + vue-tsc + vite）通过。

## 2026-09-09（实施 PLAN-DM-021 Task 3：设置中心语言事务与双语错误恢复）

- `web/src/composables/useSettings.ts` 新增语言切换事务（I18N-05/06）：只有 PUT 成功才切换语言，且以响应快照的 `ui_locale` 为准（`system` 按系统规则解析）经 `applyLocale` 恰好切换一次；`load`（409 刷新/打开对话框）、选择未保存、取消与 422/409/网络/5xx 均不切换，快照不替换、本地编辑保留。
- `web/src/api/client.ts` 支持结构化逐字段错误（ARCH-DM-005 §6.2）：`ApiError` 新增 `fieldErrors`（`{key: {code, messageKey, params, message}}`，snake_case `message_key` 归一化），原 `fields`（字符串消息）保持兼容，草稿等既有消费方不受影响。
- `web/src/api/settings.ts` 映射只向组件暴露稳定显示键：`labelKey`/`categoryKey`/`fileFilterKey`/`fileKind` 与枚举选项 `textKey`（`value` 扩展为 `int | str` 以承载 `ui_locale`）；`label`/`category`/`text`/`fileFilter` 为迁移期兼容回退（I18N-17，阶段三删除）。
- `web/src/components/settings/SettingsDialog.vue` 双语化（I18N-07）：标题/分区/按钮/确认模态/诊断横幅/关于分区/Toast 全部改走语言包；按 `category key` 分组；新增 422 错误摘要（`tabindex=-1` 可聚焦、逐条链接字段并跳转聚焦、字段标签 + `message_key` 结构化参数渲染）；409 冲突与网络/5xx 显示当前语言提示（原始消息仅作 tooltip 诊断详情）；保存成功在语言切换重渲染后 `nextTick` 归焦保存按钮（与冻结 Demo 一致：无未保存修改时保存按钮保持可聚焦、空保存由 `onSave` no-op 守卫承担）。浏览接线（`selectSettingsPath`）未改，仅以注册表 `file_kind` 取代过滤器文本解析（桥签名迁移留 Task 4）。
- `web/src/components/settings/SettingsFormRow.vue`：标签/徽章/按钮/hint/placeholder/ARIA（radiogroup 标签）/tooltip 全部经语言包渲染；"跟随系统"选项用 `settings.locale.systemCurrent` 命名参数渲染"跟随系统（当前：…）"，当前生效语言名保留自称形式（I18N-08）；修复字符串枚举（`ui_locale`）被 `Number()` 强转的问题（非数字枚举值原样入缓冲）。
- 语言资源扩展 `web/src/i18n/locales/{zh-CN,en-US}/settings.ts`（81 键对称，`check:i18n` 门禁通过）：设置中心全部静态文案、`settings.categories.*`/`settings.items.*`/`settings.validation.*`（与后端 `message_key` 对齐）/`settings.fileFilters.*`。
- 测试（TDD）：新增 `web/src/composables/useSettings.test.ts` 8 例（选择/刷新不切换、成功恰好切换一次、响应快照优先、语言未变不切换、422/409/5xx 不切换且快照保持、快照未加载不切换）；`web/tests/e2e/settings-dialog.spec.ts` 新增 4 例（取消不切换、422 错误摘要聚焦/链接字段/输入与语言保留、409 冲突恢复、保存成功切换 `html[lang]`/对话框保持/焦点恢复/背景输入不丢失），并修正损坏/Schema 降级用例的语言竞态（先写文件后加载、还原时带回 `ui_locale`，降级场景断言按双语容忍）。验证：`test:unit` 23 passed、`settings-dialog` e2e 16 passed、`check:i18n` 81 键对称、`npm run build` 通过。

## 2026-09-09（实施 PLAN-DM-021 Task 2：前端多语言启动基础）

- 新增 `web/src/i18n/locale.ts`：语言解析纯逻辑（I18N-03 / ARCH-DM-005 §4.2）——显式 `zh-CN`/`en-US` 优先于系统语言；`system` 按 `navigator.languages`（缺省读 `navigator.language`）解析，`zh-*` → `zh-CN`，其他可识别语言 → `en-US`；空列表/navigator 异常/全部不可识别标签回退 `zh-CN`。
- 新增 `web/src/i18n/index.ts` 唯一 i18n 入口（I18N-01）：创建并导出唯一 `vue-i18n` 实例（`legacy: false`，缺键运行时回退 `zh-CN`）；`applyLocale` 同步实例 locale 与 `<html lang>`；`bootstrap()` 在挂载前请求 `GET /api/settings` 提取 `ui_locale`（缺失/非法值视为 `system`），读取设 5s 超时，失败/超时按系统规则降级挂载、不渲染错误语言的完整 App（I18N-04）；挂载前以 `app.use(i18n)` 把唯一实例注册为 Vue 插件（评审修复：否则组件内 `useI18n()`/`$t` 运行时不可用），测试断言 use 先于 mount。
- `web/src/main.ts` 只调用 `bootstrap()`（含 `style.css` 引入），挂载职责移入 bootstrap，保证"先定语言再挂载"。
- 新增最小骨架语言资源 `web/src/i18n/locales/{zh-CN,en-US}/{common,settings}.ts`（`app.title`、`errors.settingsLoadFailed`、`settings.locale.*` 四键，语言名保留自称形式）；本任务未迁移任何既有组件文案。
- 新增 `web/scripts/check-i18n.mjs` 并纳入 `build`（I18N-14 雏形）：校验中英文域文件集合与键集合（点路径）对称，叶子必须为字符串，缺键/多键非零退出；允许清单与硬编码扫描留 Task 10。已实测对不对称输入退出码 1。
- `web/package.json` 新增依赖 `vue-i18n` 与 devDependency `vitest`（经 `npm --prefix web install` 同步 lock 文件），新增 `test:unit`、`check:i18n` 脚本，`build` 串联 `check:i18n`；新增 `web/vitest.config.ts`（node 环境，仅收 `src/**/*.test.ts`，不加载 vue 插件）。
- `web/tests/global-setup.ts` 预置 settings.json 显式写入 `ui_locale: "zh-CN"`：多语言启动上线后固定既有中文 e2e 基线（Playwright 浏览器 navigator 默认非中文，否则中文文案选择器会漂移）。
- 测试（TDD）：红灯（两测试文件因 `./locale`/`./index` 缺失整体失败）→ 最小实现 → 绿灯。`web/src/i18n/locale.test.ts`（7 例：显式覆盖、zh 系映射、非中文映射、navigator 读取顺序、空列表回退、navigator 异常回退、不可识别标签跳过）与 `web/src/i18n/bootstrap.test.ts`（8 例：请求结束前不 mount、挂载前注册 i18n 插件且 use 先于 mount、读取失败降级、5s 超时降级、显式值覆盖系统语言并同步 `<html lang>`、缺失/非法 ui_locale 视为 system、唯一实例不重建、applyLocale 同步）。验证：focused `test:unit` 15 passed、`check:i18n` 通过、`npm run build` 通过；另跑 `settings-dialog` e2e 12 passed 确认 global-setup 改动无回归。

## 2026-09-09（实施 PLAN-DM-021 Task 1：后端语言设置与结构化字段错误）

- `config.py` 新增 `ui_locale`（`Literal["system", "zh-CN", "en-US"]`，默认 `system`）：只保存显式覆盖值，支持 `DST_MANAGER_UI_LOCALE` 环境变量通道，沿用 默认 < env < settings.json 文件覆盖 优先级；不进工作区、草稿或数据库。
- `settings/registry.py` 元数据 key 化（ARCH-DM-005 §6.1）：`SettingsItemMeta` 增加 `label_key`/`category_key`/`file_filter_key` 与稳定 `file_kind`（exe/dll），`ui_locale`（界面/语言）居首；枚举选项改为稳定 `text_key` + 兼容中文 `text`，取值扩展为 `int | str`；兼容中文 `label`/`category`/`file_filter` 迁移期保留。
- `settings/errors.py`（评审裁决下沉）：权威定义 `ParamValue`/`FieldErrorModel`，使 `settings/runtime.py` 不再依赖 interfaces 层、`application` 不传递性依赖 interfaces；`interfaces/settings_contracts.py` 原样重导出，外部导入面不变。
- `settings/runtime.py`：`SettingsValidationError.errors` 由 `key → 中文字符串` 改为 `key → FieldErrorModel`（`code`/`message_key`/`params`/兼容 `message`）；`params` 白名单为 `str | int | bool | list[str]`，只携带 `min`/`max`/`allowed_values` 等结构化参数，不含本地化 label 或完整句子。
- `interfaces/settings_contracts.py` 重导出 `ParamValue`/`FieldErrorModel`，`EnumOptionModel` 增加 `text_key` 且 `value` 支持 `int | str`，`SettingsItemModel` 并行返回新旧元数据字段；`interfaces/api.py` 仅调整 `_settings_items` 装配并把 422 响应改为 `{"code": "SETTINGS_VALIDATION_FAILED", "errors": {设置 key: 结构化错误}}`（`api.py` 其余部分未动）。
- 测试：按 TDD 新增/修订 `tests/unit/test_config.py`、`tests/unit/test_settings_registry.py`、`tests/unit/test_settings_resolver.py`、`tests/unit/test_settings_runtime.py` 与 `tests/integration/test_api_settings.py` 共 26 个用例（三值白名单、env/file 优先级、注册表 key 覆盖、422 结构与参数白名单）；注册表完整性断言改为由 `Settings` 字段派生，不再使用固定数量/索引。验证：`uv run pytest`（focused 77 passed，全量 730 passed、72 skipped）、`uv run ruff check` 通过。

## 2026-09-09（冻结多语言设计并完成 G5～G6）

- 用户确认 SPEC-DM-013 双语 Demo，冻结 commit `3ecb754`、中文浅色 1440×900 与英文深色 900×768 截图，G4 关闭。
- 新增 [G5 技术映射备忘](.planning/memos/dst-manager/2026-09-09-multilingual-g5-technical-mapping.md)：核对启动挂载、设置事务、结构化错误、SSE、ShellBridge、全部 Vue 文案、测试与打包落点；无需先行 Spike，真实 WebView2 与原生过滤器留至 G9。
- 新增 [PLAN-DM-021](.planning/plans/dst-manager/PLAN-DM-021-multilingual-support.md)（`proposed`），以四个批次、12 个 TDD 任务追踪 I18N-01～I18N-18；SPEC-DM-013 转 `accepted`，G5/G6 关闭。本次未修改生产代码。
- 修正 ARCH-DM-005 门禁待办的正式 Spec/Plan 编号，并在 PLAN-DM-020 记录多语言前置状态：只有 PLAN-DM-021 批次一实际完成后才解除其 Task 10 阻断。

## 2026-09-09（启动多语言界面 G4 设计冻结）

- 新增 [SPEC-DM-013](docs/dst-manager/specs/SPEC-DM-013-multilingual-ui.md)（`draft`）：把 ARCH-DM-005 落为用户流程、状态矩阵、18 条可追踪需求、视觉方向与验收边界；纠正旧 Todo 中已被图纸目录占用的 `SPEC-DM-012`/`PLAN-DM-020` 编号，后续实施计划使用 `PLAN-DM-021`。
- 新增双语交互 Demo，供用户确认设置入口、保存后即时切换、失败不切换、英文伸长、浅深主题和最小视口；G4 通过前不修改生产代码。
- 同步更新 DST Manager 文档入口索引。

## 2026-09-09（审查 PLAN-DM-020 实施计划）

- 新增 [PLAN-DM-020 实施计划审查备忘](.planning/memos/dst-manager/2026-09-09-plan-dm-020-review.md)：对照 ARCH-DM-006 与 SPEC-DM-012 逐条核对追踪矩阵并验证代码事实，识别 3 项阻塞级缺口（SPEC §5.3 限制值 80/100/1024、SPEC §11 错误码词汇表、清单缺动作输出类型与 `name_key`/`description_key` 字段）、5 项重要偏差（日志语义反向、`SAVE_DIALOG` 非既有约定、Step 9 暂存措辞、changelog 时机、ARCH-DM-005 前置无排期）及若干测试锚点补强项；计划主体覆盖面确认无结构性遗漏，修订后可转 `active`。
- 按审查修订 PLAN-DM-020：钉死模板/列名/表达式限制值和全部稳定错误码，补齐清单动作输出策略、跨任务数据类型、日志关联、建议文件名、启动顺序、并发授权、偏好降级、模板冲突/删除及逐 Task 变更记录要求；ARCH-DM-006 同步把 `actions` 收紧为结构化声明。
- 新增 [ARCH-DM-005 多语言实施门禁待办](.planning/todos/dst-manager/2026-09-09-arch-dm-005-implementation-gates.md)，安排独立 G0～G6 工作流并明确其为 PLAN-DM-020 Task 10 的前置条件；计划保持 `proposed`，本次未开始生产实现。

## 2026-09-09（设计内置扩展平台与图纸目录 XLSX 试点）

- 新增 [ARCH-DM-006](docs/dst-manager/architecture/ARCH-DM-006-builtin-extension-platform.md)（`review`）：确定首期只加载固定代码白名单与随包清单中的受信内置扩展，建立注册表、生命周期、Capability Broker、裁剪后的只读工作区快照、宿主管理页面贡献、扩展设置、一次性保存授权和后台 Artifact 边界。
- 新增 [SPEC-DM-012](docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md)（`review`）：定义独立“图纸目录”页面、应用级命名模板、`sheetset`/`sheet` 属性作用域、受限组合表达式、缺定义阻断/缺值警告、XLSX 文本输出和用户原生另存为流程；记录 G0～G3 已通过，G4 Demo 与设计冻结尚未开始。
- 更新 PRD-DM-001 的关联文档和 DST Manager 导航状态；忽略可视化设计会话生成的 `.superpowers/` 本地目录，避免临时文件进入提交树。
- 新增 SPEC-DM-012 图纸目录单文件交互 Demo，覆盖模板另存与切换保护、字段光标插入、缺定义阻断、缺值警告、空图纸集、浅深主题和模拟原生另存为；自动化 QA 已通过，G4 等待用户实际操作确认。
- 用户确认认可图纸目录交互 Demo，冻结 commit `9f3dfb3` 及浅色桌面/深色最小视口截图，SPEC-DM-012 转为 `accepted`，G4 关闭。
- 完成 SPEC-DM-012 G5 技术映射与风险复核，明确扩展注册表、冻结快照、隔离设置、受限表达式、XLSX、一次性保存授权、后台 Artifact、统一 API 和独立页面的现有落点；无须先行 Spike，原生另存为与 Excel 结果保留 G9 真机验收。
- 新增 [PLAN-DM-020](.planning/plans/dst-manager/PLAN-DM-020-sheet-catalog-builtin-extension.md)（`proposed`），以四个可独立验证批次和 12 个 TDD 任务覆盖内置扩展平台及首个图纸目录 XLSX 扩展，SPEC-DM-012 G6 关闭；本阶段未修改生产代码。

## 2026-09-08（按审查接受 DST Manager 多语言支持架构）

- 按 2026-09-08 架构审查修订 [ARCH-DM-005](docs/dst-manager/architecture/ARCH-DM-005-multilingual-support.md)：补齐 422 逐字段错误结构、`file_filter` key 化与稳定 `file_kind`、ShellBridge 签名收紧和浏览器降级行为；明确兼容字段收敛门禁、WebView2 真实语言验证、`DST_MANAGER_UI_LOCALE` 优先级及前端过渡映射删除条件。
- ARCH-DM-005 状态由 `draft` 更新为 `accepted`，并同步更新 DST Manager 文档入口。

## 2026-09-08（策划 DST Manager 多语言支持）

- 新增 [ARCH-DM-005](docs/dst-manager/architecture/ARCH-DM-005-multilingual-support.md)（`draft`）：确定首期支持简体中文与英文，采用前端翻译、后端提供稳定错误码/文案键/参数的架构，并定义系统语言解析、设置持久化、兼容契约、分阶段迁移和验收门禁。
- 同步更新 DST Manager 文档入口索引。

## 2026-09-08（编制配置中心配置项增删改 SOP）

- 新增 [GUIDE-DM-003](docs/dst-manager/guides/GUIDE-DM-003-settings-config-sop.md)（`review`）：基于 PLAN-DM-019 交付后的实际代码结构，沉淀配置项**新增 / 修改 / 移除**三套标准操作流程——前置判定决策树（凭据/启动期配置不进设置中心）、`config.py` 唯一权威 + `registry.py` 展示元数据的分工边界、完整性测试与 API 硬锚的同步要求、enum 文案 fail-fast 与 pywebview 过滤器格式陷阱、存量 `settings.json` 的自愈与 `schema_version` bump 判据（区分读取兼容与往返保留）、Worker 冻结模式与反模式对照表。
- 同步更新 DST Manager 文档入口索引。
- 按实现复审修订 GUIDE-DM-003：补齐新增配置的生产消费点与 API/Worker 生命周期要求；明确 registry `file_filter` 与前端 pywebview 过滤器的当前映射边界；纠正非法存量值会使全部文件覆盖暂时降级的语义；区分未知 key 的读取兼容与往返保留，避免旧程序保存时静默丢失新字段覆盖；验证命令统一使用 `npm run test:e2e`。

## 2026-09-08（交付设置中心 PLAN-DM-019 批次 1–4）

- 按 [PLAN-DM-019](.planning/plans/dst-manager/PLAN-DM-019-settings-center.md)（依据 [ARCH-DM-004](docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)）交付设置中心全部 11 个实施任务：后端配置域四件套（`settings/store.py` 原子存储与四类诊断码、`registry.py` 展示元数据注册表、`resolver.py` 三层合并快照、`runtime.py` 保存事务与热替换）；API 三端点（`GET/PUT /api/settings`、`GET /api/about`，仅桌面壳装配注册）；Worker 任务级配置快照与 `jobs.lease_seconds` 按行租约回收（迁移 0005）；前端 `SettingsDialog.vue` 动态表单 + 来源标记/恢复继承/校验状态机/诊断横幅 + TopBar 齿轮入口（e2e 真实打后端）；打包触点（spec 随附 `LICENSE` 与 `pyproject.toml`）。
- 关键裁决（执行台账为 git-ignored 的 SDD 工作区草稿，未入库；裁决要点已由逐任务 commit message 与本记录留痕）：①`/api/about` 版本查询发行名为 `autocad-sheetset`（`copy_metadata("dst-manager")` 不可行，改随包打入 `pyproject.toml` 走兜底链）；②`config.py` 增加 `populate_by_name=True` 使 alias 字段 init-kwargs 合并机制生效（env 通道行为不变）；③enum 选项文案以 `domain/editing.py` 真实序号语义为准（1=中文序号、2=数字序号）；④e2e 必须真实打后端（`schema.d.ts` 不覆盖设置端点契约），经 globalSetup 注入 `DST_MANAGER_SETTINGS_PATH` 启动真实服务。
- 验证（实际运行）：`uv run ruff check .` 全绿；`uv lock --check` 通过（Resolved 68 packages）；全量 `uv run pytest -q` **703 passed / 72 skipped / 0 failed**（775 项，junitxml 精确计数；含 0005 迁移 upgrade→downgrade→upgrade 往返单测）；`npm ci` + `npm run build` 通过（构建预检含全新库 alembic 迁移链至 0005、OpenAPI 契约一致性、vue-tsc）；`npx playwright test` 全量 **291 passed / 0 failed**（1.6m）。G8 截图比对与 G9 真实桌面验收（路径选择器真实弹窗、外链、frozen 版本/LICENSE、真实 CAD 任务生效等）未开始，见 PLAN-DM-019「实际验证」待办。

## 2026-09-08（立项设置中心实施计划 PLAN-DM-019）

- 新增 [PLAN-DM-019](.planning/plans/dst-manager/PLAN-DM-019-settings-center.md)（`proposed`，依据 [ARCH-DM-004](docs/dst-manager/architecture/ARCH-DM-004-settings-center.md) 与 [SPEC-DM-011](docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md)）：12 个 TDD 任务分四批交付——批次 1 配置域（settings.json 原子存储/展示元数据注册表/快照解析器/运行时持有者与保存事务），批次 2 三个设置 API 端点 + Worker 任务级配置快照与租约按行回收（含迁移 0005）+ 打包触点，批次 3 前端纵向切片（ShellBridge 文件夹选择器/useSettings/SettingsDialog/TopBar 齿轮入口），批次 4 全量回归与 G8 设计 QA、G9 手工清单。
- 含 SC-01～SC-14 与 A-01～A-07 追踪矩阵、全局约束与逐任务接口签名；同步更新 Plan 索引。

## 2026-09-08（SPEC-DM-011 G4 设计冻结）

- 用户操作[设置中心交互 Demo](docs/dst-manager/mockups/SPEC-DM-011-settings-demo.html)确认通过，[SPEC-DM-011](docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md) G4 转为通过；冻结截图索引落 `assets/SPEC-DM-011/`（默认态/校验失败/保存成功/深色常规/深色关于/损坏诊断×最小视口共 6 张）。
- 冻结前修复 Demo 两处缺陷：重开对话框时分区高亮未重置（`aria-selected` 与内容不同步）；损坏诊断横幅误用红色只读样式（按 ARCH-DM-004 §5，损坏=amber 警告，Schema 过新才红色只读）。
- 下一步按 G6 创建实施 Plan 与 SC-01～SC-14 追踪矩阵。

## 2026-09-08（设置中心 UI 立项 SPEC-DM-011 与 G4 Demo）

- 按 [GUIDE-DM-001](docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md) 将设置中心前端子项目立项为 [SPEC-DM-011](docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md)（`draft`）：L 级跨域改动拆分为配置域后端（走常规工程门禁）与设置中心 UI（走 G0～G9）两个子项目；沉淀 G0～G5 门禁证据——业务目标、用户流程与状态矩阵、14 条可追踪需求（SC-01～SC-14）、视觉方向裁决（齿轮+对话框，否决标签页方案）、技术映射表与门禁记录。
- 新增[设置中心交互 Demo](docs/dst-manager/mockups/SPEC-DM-011-settings-demo.html)（G4 证据，去敏虚构数据）：覆盖分区切换、动态表单、来源/覆盖标记与恢复继承、即时与保存校验、保存失败、损坏文件诊断横幅、未保存关闭确认、浅深主题；已经 Playwright 实测关键交互（渲染、校验、保存修订号递增、焦点管理、控制台零报错）。
- G4 待用户操作 Demo 并冻结截图后转通过，随后按 G6 创建实施 Plan 与追踪矩阵；行为权威仍为 [ARCH-DM-004](docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)，Spec 只引用不复制。

## 2026-09-08（按设计审查修订 ARCH-DM-004 设置中心）

- 依据[设计审查备忘](.planning/memos/dst-manager/2026-09-07-settings-center-design-review.md)修订 [ARCH-DM-004](docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)，关闭全部 P1/P2：新增 §2.4 跨进程配置传播（Worker 认领任务前检测 `config_revision` 重载、任务级配置快照冻结、租约按任务快照判断以防过渡期误回收）；`settings.json` 语义改为**只存用户显式覆盖值**（PUT 改为 PATCH 风格 `set`/`unset` + `expected_revision`/409，杜绝 env/default 值被固化进用户文件）；保存事务改为进程内锁覆盖"读基准→校验→落盘→换快照"全程；Pydantic `Settings` 确立为唯一权威、注册表只存展示元数据并从 Schema 派生约束。
- 补充可空路径契约（`null` 表示未配置、空字符串绝不解析为 cwd、EXE/DLL 过滤器按字段声明）、损坏文件与未知高版本 Schema 的分流恢复策略（备份重建 vs 只读降级禁写）、相对路径保持现有兼容规范化行为，并按备忘测试矩阵扩充 §7。
- 文档状态保持 `draft`，待按备忘复审清单复审通过后转 `accepted`。

## 2026-09-07（应用 PRD-DM-001 审查修订）

- 按审查备忘（`.planning/memos/dst-manager/2026-09-07-prd-dm-001-review.md`）修订 [PRD-DM-001](docs/dst-manager/product/prds/PRD-DM-001-extensible-capability-platform.md)：`related` 补入 `ARCH-DM-004`；统一“插件式扩展平台/分层扩展”叫法；§8.2 与 UI-002 贡献点对齐；明确 Capability 与权限概念；统一“停用中/停用待任务完成”状态表述；新增 AC-009～AC-012 覆盖 EXT-003/007/012/013；补充同进程资源治理、扩展间互调边界、AutoLISP 独立评估及 §13/§14 定位说明。

## 2026-09-07（归档设置中心架构设计审查）

- 新增 [ARCH-DM-004 设置中心设计审查备忘](.planning/memos/dst-manager/2026-09-07-settings-center-design-review.md)：对照当前 `Settings`、API、桌面壳、独立 CAD Worker、打包资源和单实例守卫，记录 3 项 P1 与 4 项 P2；结论为当前草稿暂不应转 `accepted`，需先补齐跨进程热更新、覆盖值/继承值、并发保存事务、可空路径、未知 Schema、相对路径兼容和校验唯一来源。
- 补充建议目标配置流程、测试矩阵和转为 `accepted` 的复审清单；本次仅归档审查，不修改 ARCH-DM-004、产品代码或测试。

## 2026-09-07（立项设置中心架构设计 ARCH-DM-004）

- 新增 [ARCH-DM-004](docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)（`draft`）：针对 exe 桌面软件形态下"编辑 .env 改配置"不可用的问题，确立应用内设置中心设计——声明式配置注册表 + 动态表单渲染、`%LOCALAPPDATA%\dst-manager\settings.json` 原子存储（带 `schema_version`，合并优先级默认 < env < 用户文件）、全部界面配置即时生效（运行时 Settings 持有者热替换）、`GET/PUT /api/settings` 与 `GET /api/about` 版本化契约、顶部齿轮入口 + 未加载 DST 可用的模态对话框（含关于页：版本号、MIT 协议、主页/反馈入口）。
- 明确范围外与预留：`data_dir`/`draft_dir` 不界面化、模板目录与扩展设置本体后续立项；UI 分区结构、扩展设置独立存储命名空间和"描述 + 值"渲染契约为 [PRD-DM-001](docs/dst-manager/product/prds/PRD-DM-001-extensible-capability-platform.md)（EXT-013、UI-001/UI-002）预留接入点。
- 同步更新 DST Manager 文档入口索引。

## 2026-09-07（编制插件式扩展平台产品需求）

- 新增 [PRD-DM-001](docs/dst-manager/product/prds/PRD-DM-001-extensible-capability-platform.md)：将已确认的分层扩展平台路线、内部受信扩展、随包交付并启停、`Change Proposal` 统一写入权和 Cordis 借鉴边界整理为长期产品需求；定义内置扩展、受控 AutoCAD 作业、连接器、嵌入应用、Artifact、AutoCAD 运行时提供者及安全/兼容验收要求。
- 结合 [GUIDE-DM-001](docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md)，将扩展中心、动态贡献点和嵌入页面定为 L 级跨域前端改动，要求拆分子项目并逐项通过 G0～G9、状态矩阵、设计冻结、技术映射、追踪矩阵、设计 QA 和真实 Windows 桌面验收；同步更新 DST Manager 文档入口。本文仅定义长期需求，不创建近期实施计划。
- 修订 EXT-008：取消通用“自定义自动化”设想，改为仅随包交付的内部“受控 AutoCAD 作业扩展”；固定通过 `accoreconsole`、SCR 及声明的 .NET Worker/AutoLISP 在任务副本上执行打印和归档作业，严格采用 Artifact-only 模型，禁止 Proposal、正式发布和源工程回写，并补充普通派生 DWG 的布局/DST 不变量及 `detached` 归档成果要求。

## 2026-09-07（修复发布与恢复并发踩踏）

- 修复用户连续编辑时第二次预览/打开工作区会对仍在发布的 journal 启动回滚、最终进入 `PUBLISH_RECOVERY_FAILED` 的问题：普通 `open_workspace()` 恢复为纯读取路径，发布恢复仅由服务启动流程负责。
- 新增工作区级跨进程发布事务锁，串行化 API 与 CAD Worker 的发布、启动恢复及已提交清单读取；将数据库提交回调延后到发布日志归档和清理尝试完成之后，避免工作区写锁提前释放；journal 原子写入改用唯一临时文件，消除固定 `publish-journal.tmp` 的源文件争用。
- 新增回归测试，覆盖活动发布不被恢复、普通打开不触发恢复、并发 journal 写入使用独立临时文件，以及提交回调发生在发布清理之后。
- 验证（实际运行）：`uv run ruff check .` 全绿；全量 `uv run pytest -q` 在批处理约定的 GBK 控制台代码页下 **642 passed / 72 skipped / 0 failed**。直接继承当前 UTF-8 控制台时，仅既有 `setup.bat` 的 2 项中文输出解码断言失败，切换 `chcp 936` 后单项与全量均通过。

## 2026-09-07（桌面壳单实例守卫）

- 新增 `src/dst_manager/infrastructure/single_instance.py`（仅标准库 + ctypes 直调 Win32，无新依赖）：命名互斥量（`Local\dst-manager-<用户维度摘要>`）检测已有实例，内核对象随进程退出自动释放；第二个实例弹置顶警告框，用户点击“确定”后由后启动进程（持前台权限）把既有窗口 `ShowWindow(SW_RESTORE)` 还原并 `SetForegroundWindow` 置前，前台锁拦截时退化为任务栏闪烁兜底。
- `run_desktop` 集成单实例守卫（[PLAN-DM-018](.planning/plans/dst-manager/PLAN-DM-018-desktop-single-instance.md)）：第二个实例弹窗报错后退出，不再与第一个实例同时操作同一工作区的 `.dst-manager` 锁、发布 journal 与任务队列（回应 `tests/user-feedback/logs/user-weng/` 中 `PUBLISH_RECOVERY_FAILED` / `WinError 32` 所见的双进程踩踏）；`desktop` 为唯一受限入口，`worker`（壳子进程）与 `serve`/`doctor` 不受影响，非 Windows 平台守卫放行。
- 新增 10 项单实例单测（`tests/unit/test_single_instance.py`）：互斥量名称确定性派生、真实内核持锁/后启动被拒/释放重入（Windows 实跑）、非 Windows 放行标记、唤起容错（窗口缺失不崩溃）。
- 验证（实际运行）：`uv run ruff check .` 全绿；全量 `uv run pytest -q` 退出码 0，**638 passed / 72 skipped / 0 failed**（基线 628 + 新增 10，无回归）。真实桌面双开冒烟（弹窗→确认→切换、最小化还原置前）待用户本机复验。

## 2026-09-07（建立前端功能设计与实施门禁）

- 新增 `GUIDE-DM-001`，以 G0～G9 十道门禁规范前端功能从立项、业务目标、流程状态、视觉方向、Demo 冻结、技术映射、计划追踪、分批实施到设计 QA 和真实环境验收的全过程；提供 S/M/L 风险分级、小改快速通道、强制追踪矩阵和门禁记录模板。
- 新增 `GUIDE-DM-002`，面向非前端专业人员解释各门禁的目的、需要业务负责人确认的事项、Agent/技术负责人职责，以及 Figma、Demo、Spec、Plan、设计 QA 和真实环境验收的区别。
- 更新 DST Manager 文档入口；两份指南保持“权威清单 + 通俗解释”的单向引用关系，避免重复规则形成双重权威。

## 2026-09-06（全仓静态审查归档备忘）

- 完成全仓库静态审查（后端 src 四层 + tests 八域 + web 前端 + C# 插件 + 打包/迁移/脚本 + 文档治理与 git 卫生），结论归档为 `[2026-09-06-full-code-review](.planning/memos/dst-manager/2026-09-06-full-code-review.md)`。
- 审查结论：未发现 P0 阻断项；5 项 P1（发布 journal 无 fsync 且恢复对坏日志无容错、Worker 领取后准备阶段异常逃逸致进程退出、XML 导入写主 DST 路径缺空子集校验、前后端 422/fields 错误契约不匹配、7 文件超 500 行容量红线未排期）＋ 12 项 P2 ＋ 若干 P3 与未提交打包改动评估。
- 验证（实际运行）：`ruff check .` 通过；pytest（排除真实 CAD 系统测试）**628 passed / 72 skipped / 0 failed**（700 收集，72 个跳过为真实 AutoCAD 与真实环境用例）含发布器回滚、acsm repair、事务恢复、CAD 并行；web 生产构建通过（OpenAPI 契约一致性 + 全新库 alembic 迁移 + vue-tsc + vite）；依赖方向扫描确认 domain 层无违规导入。
- 同日追加：应用户要求对未提交的“打包 exe 隐藏控制台 + 无窗日志”12 文件专项审查，结论以附录 A 追加至备忘底部——无数据/发布安全红线；P1 为“windowed exe 从控制台手工运行时输出保持可见”断言不成立（PyInstaller windowed stdio 恒 NullWriter，需 Step 7 冒烟实测后修订文档），另有 doctor 异常零反馈、测试缺口、验证口径不一致等 P2。

## 2026-09-06（隐藏打包 exe 终端黑窗，日志改走文件）

- 按用户裁决修订 ARCH-DM-002 的 `console=True` 决策为 `console=False`：双击 `dst-manager.exe` 不再弹出终端黑窗；"Worker 日志与启动警告必须可观察"的约束保留，观察通道由控制台改为日志文件（ARCH-DM-002 §3.5 新增）。
- 新增无窗日志通道：`runtime.py` 增加 `log_dir()`（`%LOCALAPPDATA%/dst-manager/logs/`，与数据目录同根）与 `redirect_frozen_stdio()`——`packaging/entry.py` 在导入业务代码（含 uvicorn 日志接管）之前，把 windowed 态不可用的标准流（PyInstaller `NullWriter`）按命令重定向到 `dst-manager.log`（壳进程：uvicorn/Alembic/Worker 提前退出警告）或 `worker.log`（Worker 任务认领摘要），追加模式带启动分隔行。重定向只补"无终端"缺口：从控制台手工运行 `dst-manager.exe worker` 等命令时标准流可用、输出照常可见；`doctor`/`serve` 不重定向。
- `doctor` 自检在 frozen 态除命令行输出外落盘 `%LOCALAPPDATA%/dst-manager/logs/doctor-last.json`，便于无终端环境下排障与反馈；开发态不落盘。`_spawn_worker` 无需改动：Worker 子进程由自身入口的 entry.py 重定向接住（从控制台手工运行时认领日志仍然打印到终端）。
- 防回归守护：`test_packaging_spec.py` 新增 `console=False` 静态断言与"entry.py 重定向必须发生在导入 cli 之前"断言；`test_runtime.py` 新增 8 项（NullWriter 识别、LOCALAPPDATA 日志根、开发态/控制台子命令不重定向、双文件名、坏流替换与好流保留）；`test_core.py` 新增 doctor frozen 落盘/开发态不落盘两用例。
- 文档同步：ARCH-DM-002 §3.3 决策改写 + 新增 §3.5 + §6 验证口径（Worker 认领日志见 `worker.log`、双击无黑窗）；README 打包章节补充"双击无终端、日志位置与反馈方式、doctor-last.json"。
- 验证（实际运行）：pytest 全量（排除真实 CAD 系统测试）**628 passed / 4 skipped，0 失败**，退出码 0。

## 2026-09-06（新增 setup.bat 最终用户环境初始化脚本）

- 新增 `scripts/setup.bat` 并随包分发：面向打包分发后的最终用户，双击运行即在程序目录生成/补全 `.env`，免去手工配置。按年份升序探测注册表 `HKLM\SOFTWARE\Autodesk\AutoCAD\Rxx.x`（回退 `C:\Program Files\Autodesk\AutoCAD *\accoreconsole.exe` 目录扫描）定位本机 `accoreconsole.exe`，按 .NET 插件向前兼容口径写入版本桶：2015-2019 → `DST_MANAGER_AUTOCAD_2016_CONSOLE`，2020-2024 → `DST_MANAGER_AUTOCAD_2020_CONSOLE`（同组多版本取最新，两组独立填写）；2013/2014 输出兼容性风险警告后仍写入 2016 桶；2025 及以上（.NET 8）明确提示不支持；accoreconsole 自 2013 起才有，更早版本不在探测范围。脚本幂等，只补缺失键、绝不覆盖已有 `.env`；未探测到时模板保留注释占位并提示手工填写。`build_release.ps1` 组包阶段将 `setup.bat` 拷入 `dist/DSTManager/`。
- 编码例外：`setup.bat` 保存为 GBK（ANSI，zh-CN 默认代码页）——实测 UTF-8 批处理在 cmd 下多字节解析不可靠（会吞字符），沿用 SCR 先例豁免仓库 UTF-8 规则；`.env` 模板注释刻意全 ASCII，保证写出的 `.env` 恒为合法 UTF-8（pydantic-settings 按 utf-8 读取）。测试钩子 `DST_SETUP_AUTODESK_ROOT` / `DST_SETUP_SKIP_REGISTRY` / `DST_SETUP_NO_PAUSE` 支持无 AutoCAD 环境的沙箱集成测试。
- 修复设置读取的既有缺陷：`NumberSuffixType=1`（`.env.example` 引导的写法）会使 `Settings` 校验崩溃——`Literal[1, 2]` 不接受字符串，补 `validate_number_suffix_type` 字符串容错校验器（与 `EnableAddNumberSuffix` 同风格），新增 "1"/"2" 字符串接受用例。
- 文档同步：ARCH-DM-002 §3.4 增补 setup.bat 探测与兼容组映射约定（运行期仍保持显式配置、不在包内猜测）、§4 组包步骤补 `setup.bat`；README 打包章节改为解压后先运行 `setup.bat` 的引导。
- 验证（实际运行）：新增 `tests/unit/test_setup_bat.py`（静态契约 + 6 项沙箱集成测试：双桶映射、2013/2014 警告映射、组内取最新、2025 不支持、幂等不覆盖、未发现时注释占位）；`test_setup_bat.py + test_release_scripts.py + test_packaging_spec.py + test_config.py` 31/31 通过；真实环境运行 `setup.bat`（注册表探测）生成本机 2016/2020 双桶路径的合法 UTF-8 `.env`，重复运行确认幂等跳过，`dst-manager doctor` 成功读取写回的路径。
- 计划同步：[PLAN-DM-014](.planning/plans/dst-manager/PLAN-DM-014-windows-release-packaging.md) 追加 Task 10（setup.bat，含随包验证待办），并逐任务核查完成情况——Task 1-9 代码全部落地（提交 `ccecb99`…`76d99b2`、审查修复 `4dc87cc`，`dist/DSTManager` 与 v0.3.3 zip 构建产物在盘佐证冒烟已执行），勾选 50 项；遗留 3 项人工/冒烟未做（exe 冒烟无记录、release.ps1 前置校验冒烟未执行、端到端 release 演练确认未做过——version 0.3.3 且无任何 git tag），状态 `proposed` → `active`，核查明细见计划新增「完成情况核查」章节。

## 2026-09-06（修复属性导入导出下载失效并简化操作层级）

- 立项产品化阶段版本管理与发布流程设计 [ARCH-DM-003](docs/dst-manager/architecture/ARCH-DM-003-versioning-and-release.md)：SemVer（0.x 阶段）+ rc 预发布渠道 + tag 驱动 GitHub Releases + GitHub Actions 门禁与自动发布；接手 ARCH-DM-002 明确范围外的 CI 自动构建与远程发布。本文档阶段仅设计，实施另行立项。

- 修复桌面壳内「下载 CSV 模板 / 导出当前属性」点击无响应的阻断性缺陷：pywebview 5 默认 `ALLOW_DOWNLOADS = False`，WebView2 会静默吞掉页面内 `<a download>`；`run_desktop` 启动前经 `enable_native_downloads()` 显式放行，并新增单测锁定该前提。
- 两个下载端点（`/api/custom-properties/template`、`/api/workspaces/{id}/custom-properties/export`）补 `Content-Disposition: attachment` 固定 CSV 落盘文件名（URL 末段无扩展名，WebView2 依该头命名），集成测试同步断言。
- 按用户裁决简化属性导入导出操作层级：移除「导入 / 导出」二级菜单按钮，面板展开后下载模板、导出当前属性、导入 CSV 三个操作常驻（面板折叠时不可达，原遗留 1 的禁用修复随之不再需要）；SPEC-DM-010 §6 与评审状态同步修订，CSV 相关 e2e 口径全部迁移。
- 同日追加裁决（关闭导入清空缓存）：「关闭导入」不再仅收起——存在未导入数据（已选文件或预览）时先经 `useConfirm` 确认提醒"数据尚未写入正式文件，关闭将清空这些提交数据"，确认后经 `invalidateCsvPreview(true)` 清空文件与预览缓存并由组件 watch 重置原生 file input，重新打开需重新选择文件并预览；无数据时直接收起不弹确认。在途导入任务不受关闭影响（job 监控独立于导入区 UI）。SPEC-DM-010 §6 同步修订。
- 新增 e2e「关闭导入清空缓存：有未导入数据先确认，取消保留、确认清空文件与预览」，覆盖取消保留与确认清空两分支（含重开后预览清空、确认禁用、file input 值清空断言）。
- 验证（实际运行）：生产构建（vue-tsc + vite）零错误；Playwright 属性页 csv/workspace/layout/buffer + main **96/96**。
- 验证（实际运行）：Ruff 通过；`test_shell.py + test_api.py` 85/85；生产构建（vue-tsc + vite）零错误；Playwright 属性页 csv/workspace/buffer/layout 36/36、main + 其余属性页 111/111、sheets-visual-regressions 19/19。
- 同日早前：PLAN-DM-016 设计 QA 备忘经 28 张成对证据逐项视觉核对并由用户确认标记 `passed`（核对观察 A–D 与跟进候选 5/6 登记于备忘与 `design-qa.md`）。

## 2026-09-06（完成属性页分区编辑工作区）

- 落地 [PLAN-DM-016](.planning/plans/dst-manager/PLAN-DM-016-properties-workspace-ui.md) 任务 1～7（三基准缓冲模型、会话缓冲与全局输入保护、值面板、字段定义六条分页、CSV 渐进导入门禁、页面组合、视觉基线与 7 状态 × 双主题的 demo/prod 去敏成对证据共 28 张 PNG）并执行任务 8 收口；全部实际数字记录于计划新增「8. 实际验证」小节。
- 全量验证（实际运行）：Ruff 通过；pytest **604 passed / 72 skipped（676 项，0 失败，无新增跳过）**；`uv lock --check` 通过；`alembic upgrade head` 应用 0001→0004 退出码 0；`npm ci` 与生产构建（vue-tsc + vite）零错误；Playwright 全量 **276/276**（`--workers=4`，1.4m）。默认并行下连续 4 次全量各出现 1 个互不相同的 30s 开发服务器负载抖动用例（单独重跑均通过），已在计划如实记录，不作为功能回归。
- 修复全量回归中发现的真实迁移缺口：`web/tests/e2e/sheets-columns.spec.ts`「删除字段从配置移除且撤销恢复此前开关」未按计划 Task 6 Step 5 迁移旧属性选择器，补齐「展开属性字段定义 → 搜索定位 → 删除属性定义确认」既有交互步骤，断言意图不变；修复后该文件 16/16。
- 两处文档修订：QA 备忘索引表文件名模板 `1440x90{0}` 笔误更正为 `1440x900`；`web/tests/e2e/properties-visual-evidence.spec.ts` 头注释更正为实际证据采集方式（回归仅产 testInfo 附件，持久对比图为验收时显式复制入库，demo 侧临时脚本不进入提交树）。
- 人工事项未代行、不写完成：4 视口 × 双主题 × 5 状态视觉矩阵与键盘专项整理为计划 8.3 核对清单待用户执行；QA 备忘 14 项全部保持待人工确认，PLAN-DM-016 保持 `active`（计划索引同步更新）；浏览器网络面板安全抽查以自动化断言证据替代记录（草稿端点隔离与 CSV 强确认各 5 处 spec:行号见计划 8.2），真实工程测试未执行（无授权）。

## 2026-09-05（修订 PLAN-DM-016 属性页前端实施基线）

- 以已完成的 PLAN-DM-017 和提交 `b9f7d60` 为实施基线，修订属性页计划的共享输入保护、字段身份失效接口、实际测试文件名、RTK 命令和图纸页回归范围。
- 结合 SPEC-DM-010 Demo 的独立卡片、60px 标题栏、双列节奏、状态徽标和渐进展开关系，明确生产控件采用 38px 输入/选择器、36px 普通按钮、34px 紧凑按钮及至少 36×36px 图标按钮；属性样式只使用语义令牌和受限作用域。
- 补充定义表横向滚动与操作列冻结、单一主纵向滚动区、长值完整读取、同状态去敏视觉证据和用户视觉确认门禁；规范与 Demo 的非模态新增关闭文案同步改为“关闭新增”。

## 2026-09-05（完成 PLAN-DM-017 图纸工作区视觉收敛整改）

- 用户在真实桌面连续复验并确认视觉整改可以完成；将 PLAN-DM-017 与 `design-qa.md` 分别更新为 `completed` 和 `passed`，同步关闭 PLAN-DM-015 的 S-07，并在计划索引和 DST Manager 文档索引中保留 S-09 真实 Explorer 验收这一独立待办。
- 收口提交包含图纸表格全选、紧凑按钮、批量属性连续编辑、行内三列属性抽屉、冻结操作列、双行字段显示、任务覆盖抽屉、深色属性编辑器样式修复、完整 Playwright 回归与 19 张持久视觉证据；最终新鲜验证结果记录于 PLAN-DM-017 的“实际验证”。
- 提交前最终验证通过：生产构建、完整 Playwright **190/190**、相关 Python **34/34**、Ruff、`uv lock --check` 与 `git diff --check` 均成功。

## 2026-09-05（修复行内属性编辑器深色样式污染）

- 将无范围的全局 `header` 样式限定到应用 `.topbar`，避免行内属性编辑器误继承 68px 最小高度、顶栏内边距、surface 背景和 `color-on-accent` 深色文字。
- 为属性编辑器的搜索框和属性输入补齐 38px 高度、1px 语义边框、圆角、实底及 hover/focus 状态，消除浏览器默认的粗白色立体边框。
- 新增深色主题计算样式回归并保留先红后绿证据；属性编辑、布局和视觉相关 **64/64**、生产构建及 Ruff 通过，并目检最新深色编辑截图。

## 2026-09-05（优化图纸表格选择、批量编辑与横向阅读）

- 将“全选当前结果”移入表头首列复选框并支持全选/半选状态，移除独立全选入口和“选择”表头文字；统一筛选、显示列、顶部操作和批量操作按钮为 34px 紧凑高度。
- 将批量属性控件移至选择摘要下方独立一行；批量加入草稿成功后保留勾选集合与批量模式，仅重置模式、属性和值，直到用户取消当前结果或清除选择时退出。
- 将单张图纸属性编辑器插入目标表格行下方，桌面端每行展示 3 个属性并在窄视口降为 2/1 列；横向溢出时冻结右侧操作列，标题、子集、文件名、布局和自定义属性统一为最多两行并保留完整值读取入口。
- 新增 6 项专项 Playwright 回归并更新既有全选、键盘顺序、列显示、冻结列和紧凑按钮断言；最终完整 Web **189/189**、相关 Python **34/34**、生产构建、Ruff、锁文件及补丁格式检查通过。

## 2026-09-05（执行图纸工作区视觉收敛整改）

- 落地 PLAN-DM-017 任务 1～6：收敛局部语义令牌和按钮样式，拆分编辑/列表卡片，统一 38px 表单及浅深主题交互背景；确定表格列宽、44px 普通行与安全固定列降级，避免导航调宽后覆盖字段。
- 将任务浮层改为 48px 常驻入口栏与固定覆盖抽屉，沿实际标签栏和底栏边界定位；补齐页签键盘、Tab 困绕、Esc 焦点归还及四宽双主题非零滚动保持回归。
- 保存 19 张虚构夹具实现截图并更新设计 QA、计划和索引；已有浅色默认参考完成同输入对照，其他状态因缺少匹配参考继续待验收，PLAN-DM-017 保持 `active`，不沿用历史视觉通过结论。
- 最终生产构建、完整 Web 183 项、Ruff、壳桥相关 Python 34 项和锁文件检查通过；独立审查通过，未提交 Git。真实 Explorer 与 CAD 系统检查未执行。

## 2026-09-05（编制图纸工作区视觉收敛整改计划）

- 修订 SPEC-DM-006：任务浮层在所有支持宽度下统一为“固定右缘入口栏 + 向左悬浮覆盖”，展开前后不得挤压主内容；补充已声明令牌、表单控件和表格交互态约束。
- 修订 SPEC-DM-009：增加独立编辑/列表卡片、统一输入与下拉、表格分层、hover/焦点/选中、导航拖拽后列不重叠及同视口设计 QA 要求，新增 S-13～S-17。
- 新增 PLAN-DM-017，按令牌、双卡片、表单、表格几何、交互状态、悬浮任务面板和最终视觉验收七个任务承接整改；更正 PLAN-DM-015 的 S-07 状态，保留 S-09 真实 Explorer 人工验收。

## 2026-09-05（整改 PLAN-DM-015 图纸工作区视觉与入口问题）

- 顶栏改为显示图纸集名称，并在名称旁提供清晰的“打开所在文件夹”文字按钮；修复图标按钮继承全局 padding 后被压缩的问题，同时保留可信桌面壳桥与无壳禁用语义。
- 图纸导航默认只呈现子集，选择后渐进展开；桌面宽度改为 320px 并支持鼠标拖动及键盘调节（260～420px），子集与图纸名称支持双行显示，900px 抽屉同步加宽。
- 主表文件名列只展示 basename，完整路径继续留在诊断区；图纸工作区改为填满 ActionDock 上方空间并由树、表格内部滚动。
- 新增用户可见结果回归，覆盖顶栏名称/文件夹按钮尺寸、basename、导航折行/调宽/默认展开和工作区高度；补强既有文件名与树键盘测试。
- 同视口视觉复核后为标题、子集和文件名列补充 180/200/240px 最小宽度，并在窄屏为底部操作栏预留右侧任务栏空间；900×768 下持续操作不再被遮挡。
- 新增根目录 `design-qa.md` 及 1440×900 同视口、聚焦区域和 900×768 深色响应式证据；生产构建、153 项 E2E、Ruff 与 51 项相关 Python 测试通过，真实 Windows Explorer 选中 DST 仍保留为 S-09 人工验收。

## 2026-09-05（整理 PLAN-DM-015 图纸工作区实施评审）

- 新增 [PLAN-DM-015 图纸工作区实施评审报告](.planning/memos/dst-manager/PLAN-DM-015-sheets-workspace-ui-review.md)：汇总真实桌面截图、SPEC/交互 Demo、生产源码与既有测试的对照结果，确认文件夹入口被全局按钮 padding 压缩、导航长名称裁剪、文件名误显完整路径、顶栏身份信息错误、默认展开和工作区高度偏差，以及自动化只验 DOM 未验可见结果等问题；给出 P1/P2/P3 分级、整改顺序与 S-07/S-09 复验清单。PLAN-DM-015 建议继续保持 `active`。

## 2026-09-05（调整网络搜索工具优先级）

- 更新仓库代理规则：网页搜索、资料查找和外部调研优先使用内置搜索工具；仅在内置搜索不可用或报错时检查并使用 Tavily，两者均不可用时向用户说明并等待指示。

## 2026-09-05（接受属性页规范并编制实施计划）

- 将 [SPEC-DM-010](docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md) 状态由 `review` 转为 `accepted`，记录用户对完整修订与交互 Demo 的确认；接受状态不代表生产实现完成。
- 新增 [PLAN-DM-016](.planning/plans/dst-manager/PLAN-DM-016-properties-workspace-ui.md)（`proposed`）：以后端/API 零扩展为默认边界，分七个 TDD 任务实施三基准属性缓冲、属性值面板、字段定义六条分页、CSV 隔离、统一未提交输入保护、响应式/无障碍矩阵及全量回归；明确在 PLAN-DM-015 合入后的最新基线上执行并保留共享代码变更。

## 2026-09-05（视觉、可访问性、回归与交付）

- **新增视口与可访问性回归测试（[PLAN-DM-015](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 任务 8，SPEC-DM-009 §3.2/§8）**：新增 `web/tests/e2e/sheets-layout.spec.ts`（9 项）：四尺寸（1024×768/1120×768/1440×900/900×768）× 浅深主题视口矩阵，覆盖默认、行编辑、编辑子集/新增图纸/新建子集三类操作表单、任务浮层展开与长列状态，断言无页面横向溢出且主表可达；900px 树抽屉键盘开关、焦点移入树、Tab 可离开（不与任务浮层同时锁焦）、Esc 关闭并回焦；只剩一张业务表且搜索栏/选择条/固定列/ActionDock 不重叠；小视口下属性编辑与操作表单页脚可滚动到达；a11y 语义（树方向键移动焦点、展开按钮 aria-expanded、表格可访问名、完整文本键盘读取）；浅深主题实际渲染前景/背景组合对比度正文 ≥4.5:1、强调色 ≥3:1。
- **900px 树收起为可访问抽屉（SPEC-DM-006 §4.3/§7.2、SPEC-DM-009 §3.2）**：`SheetsView.vue` 新增始终可见「打开图纸导航」触发按钮（aria-expanded/aria-controls），打开后焦点移入树，选择节点或 Esc 关闭并把焦点还给触发按钮；抽屉不设焦点困绕（与任务浮层同时展开时 Tab 仍可离开），全局 Esc 兜底与模态自身 stopPropagation 不冲突。窄屏下树绝对定位抽屉化，关闭用 visibility:hidden 移出可访问树与焦点序。
- **a11y 补口（SPEC-DM-009 §8/SPEC-DM-006 §7）**：`SheetTree.vue` 方向键/Home/End 真正移动焦点（roving tabindex 焦点落到目标节点，后续按键经事件冒泡回容器处理）；`ColumnSettings.vue`「显示列」触发按钮补 aria-expanded/aria-controls；`style.css` 新增全局 `prefers-reduced-motion:reduce` 关闭非必要过渡/动画；`TaskOverlay.vue` 页签 flex 补 min-width:0/ellipsis 并给浮层 overflow-x:hidden，消除展开宽度过渡期间页签行挤压导致的瞬时横向溢出。
- **验证（按简报 verbatim）**：`cd web && npm run build`（check:api + vue-tsc + vite）零错误；Playwright e2e **146/146 通过**（137 既有 + 新增 9；并行默认下 2 项既有时序敏感用例高负载偶发超时，单独重跑与串行全绿）；`uv run ruff check .` All checks passed；指定 pytest 选集（test_shell/test_shell_workspace/test_sheet_preferences/test_sheet_projection_contract/test_drafts/test_v021_editing/test_contracts）**138 passed**（含任务 1 的 `test_sheet_projection_contract.py` 集成证据）；`git diff --check` 通过。本任务只改 `web/`、计划/索引、README 与 changelog，Python 侧未触碰；S-09 真实桌面人工验收与 S-07 截图人工目检待用户执行，不写「完整系统验收通过」；仓库所有者并行的 SPEC-DM-010 文档/演示改动未纳入本提交。

## 2026-09-05（批量、删除及草稿动作联动）

- **批量属性编辑区分「设置值/清空值」（[PLAN-DM-015](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 任务 7，SPEC-DM-009 §4.2/§6.1）**：`SheetToolbar.vue` 批量输入新增「批量模式」切换（设置值/清空值）。遍历完整勾选集合（含未加载行，批量范围不隐式缩为当前可见行），逐张复制 `custom_properties` 后仅改指定名称，已删除对象按 ID 匹配不到自然不进入批量。设置值模式空输入不生成修改、只提示改走清空；清空值模式必须显式选择并确认受影响数量（设为空字符串，是否允许空值仍由服务端校验 S-11），且只改实际受影响图纸、与确认数量一致。提交摘要（toast）含完整数量与跨子集范围，草稿动作标签保持既有「N 张」格式。
- **删除确认文案对齐「加入删除草稿」并补反馈（SPEC-DM-009 §6.3）**：单张图纸删除确认按钮由「确认删除」改为「加入删除草稿」，明确不是立即删除文件；成功后推送 toast 反馈（可在草稿栈查看与撤销）。整子集删除保持 confirm_delete_all_sheets/confirm_delete_main_dwg 强确认（不可逆 + 勾选 + 影响 DWG 与外部引用声明）并补 toast。删除命令经既有 guard 先处理未提交缓冲，不夹带未确认的属性变更；投影移除、选择修剪与撤销/重做联动不变，撤销恢复图纸但不自动恢复勾选（S-12）。
- **清理前序任务遗留（任务 5/6 审查项）**：`useSheetEditor.guard` 等待在途保存后复检 guardState.open，修复两个排队 guard 动作在提交失败后都能越过防重入检查、后者覆盖 guardResolver 丢弃前者续延的微竞态；`SheetOperationForm` 编辑子集未选择对象时禁用「删除整个子集」危险入口（不再静默无操作）；`App.vue` 同类操作入口点击的同类型短路前移到 guard 之前（不再无谓触发三选一）。
- **测试（TDD，先红后绿）**：新增 `web/tests/e2e/sheets-drafts.spec.ts`（7 项：跨范围两张批量只改指定字段并保留其他字段、设置值空输入不生成命令且仅提示、清空值显式确认受影响数量且只清指定字段、单张删除加入草稿后从投影表与勾选集合移除、撤销恢复图纸但不自动恢复勾选（含简报 verbatim 计数联动）、删除整个子集强确认字段不变且声明影响 DWG 与外部引用、结构表单服务端失败保留完整输入）；`sheets-forms.spec.ts` 新增「同类操作入口点击不触发三选一且表单保留」并给「编辑子集全部范围先选择编辑对象」补危险入口禁用/可用断言；同步迁移 6 处既有「确认删除」为「加入删除草稿」。
- 验证：`cd web && npm run build`（check:api + vue-tsc + vite）零错误；Playwright e2e **137/137 通过**（129 既有 + 新增 8）。本任务只改 `web/` 与 changelog，Python 侧未触碰；仓库所有者并行的 SPEC-DM-010 文档/演示改动未纳入本提交。

## 2026-09-05（三类操作表单与参照位置映射）

- **新增参照对象 → 既有 ordinal/placement 命令映射（[PLAN-DM-015](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 任务 6，SPEC-DM-009 §6.3）**：`web/src/features/sheets/commands.ts` 产出 `resolveSheetOrdinal(workspace,ref)`/`resolveSubsetOrdinal(workspace,subsetId)`，把稳定对象 ID 映射为既有序号/方向命令（ordinal 为锚对象序位、placement 相对其前后），失效参照抛可见错误、不回退为 1；不重新实现后端派生命名、不增加自由排序能力。原 command schema（insert_sheet 的 target_subset_id/ordinal/placement/count/source，insert_subset 的 ordinal/placement/title/initial_sheet_count/base_template_file/source），不携带 UI ref 或演示 token。
- **新增三类操作表单（`web/src/components/sheets/SheetOperationForm.vue`）**：编辑子集/新增图纸/新建子集统一在主表上方展开、一次只出现一种、长表单内部滚动且保留标题与「取消/加入草稿」入口；编辑子集仅缓冲标题（全部图纸范围先选择编辑对象、单子集范围预填，图号范围只读），新增图纸选择目标子集与参照图纸而非手填序号（单子集范围预填目标、全部范围必须明确选择，目标变化后清除不属于新目标的参照），新建子集选择参照子集与前后（空图纸集显示「创建首个子集」、不展示不存在的参照、沿用首个序号为 1 的契约），基础模板决定新 DWG 基底、布局模板提供布局，两者分开标注。
- **唯一编辑上下文接入操作表单（`useSheetEditor.ts`、`types.ts`）**：rename/insert-sheet/insert-subset 分支携带表单字段与布局读取状态，dirty 标记纳入三选一输入保护（编辑子集标题缓冲折入 rename 上下文，不再游离于 guard 之外）；提交前固定打开时的投影快照、基准/对象变化由 watch 标 invalid 拦截旧索引；加入草稿时重新核对参照（已删除/失效保留表单并要求重选、不静默替换对象），成功等待权威投影后从派生结果取得新增 ID 并定位到其所在范围（原筛选保留、隐藏目标提示清除后定位），失败保留完整输入；空子集无可用图纸参照时提示流程不可用并禁用新增。清理 `added` 死字段与 `sheetView` 死计算（视图逻辑与组件重复）。
- **模板/布局接线（`App.vue`）**：复用 selectTemplateFile/selectSubsetTemplateFile/selectBaseTemplateFile 壳桥与 layout-names 错误回退；布局异步读取增加上下文代次与对象身份校验，取消/切表单/切 CAD 版本后的旧响应不回填；已有布局来源不重新要求用户文件/布局，选择模板来源才展开对应文件与布局选择。
- **替换任务 3 过渡实现**：非驻留过渡表单与「全部范围默认取首个子集」改为正式参照表单与显式对象选择；工具栏三类操作入口常驻显示（同一表单已打开点击不重开，另一表单经三选一切换），消除操作按钮可见性不一致。
- **测试（TDD，先红后绿）**：夹具 `fixtures/sheets.ts` 新增 `buildPreviewFromBase`（把命令应用到基底生成权威派生文档，新增对象用独立派生 ID，证明前端不从计数拼造）与 `installSmartPreview`，`installSheetsFixture` 返回基底工作区；新增 `web/tests/e2e/sheets-forms.spec.ts`（13 项：单子集预填/全部必须选择、变目标清参照、删除参照需重选、同 ID 顺序变化重新映射、空子集禁用新增、空集新子集 ordinal=1、基础与布局模板分离、成功关闭表单并定位派生新增对象、失败保留完整输入、编辑子集全部范围先选择编辑对象、成功后保留筛选并提示目标隐藏）；迁移 sheets-editing/sheets-projection/main.spec 中旧过渡表单交互到参照表单（编辑子集先选对象、新增图纸选参照对象、提交按钮统一「加入草稿」）。
- 验证：`cd web && npm run build`（check:api + vue-tsc + vite）零错误；Playwright e2e **129/129 通过**（116 既有 + 新增 13）；`git diff --check` 通过。本任务只改 `web/` 与 changelog，Python 侧未触碰；仓库所有者并行的 SPEC-DM-010 文档/演示改动未纳入本提交。

## 2026-09-05（分页编辑缓冲与全局输入保护）

- **新增唯一活动编辑上下文组合式函数（[PLAN-DM-015](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 任务 5，SPEC-DM-009 §6.1/§6.2）**：`web/src/composables/useSheetEditor.ts`。上下文为 `null | sheet | rename | insert-sheet | insert-subset | bulk` 联合分支（类型建于 `features/sheets/types.ts`，不用 any），每分支保留 workspaceId/revisionId/投影快照/objectId/original/values/errors。sheet 分支在 `custom_properties` 完整副本上编辑，搜索/翻页只派生视图、不丢输入、不自动提交；提交 `createCommand.updateSheetProperties(id,{...values})` 覆盖全部属性页（不只当前页），成功退出编辑并更新既有草稿投影与计数，失败保留输入并呈现行内错误与可聚焦摘要，未给字段路径的错误只进摘要、不编造字段归因。`guard(next)` 三选一「加入草稿后继续/放弃输入/留在此处」：无改动直接继续；保存→等待草稿持久化与投影成功→继续（`SubmitCommands` 等原 `draftSaveQueue`，不以入队即宣称保存）；失败不能继续 next；放弃明确清空缓冲；Esc 等于留下。基准刷新或对象消失标记上下文失效、保留可见输入供核对、禁止提交到新基准；只读值更新不自动覆盖用户输入；保存中切换等保存完成再继续、不重复提示；关闭编辑器焦点回到触发按钮。
- **新增分页属性编辑器（`web/src/components/sheets/SheetPropertyEditor.vue`）**：最多两列、每页 6 个属性、属性名称搜索；页脚显示总属性数/页码/跨页已修改数并显式区分「尚未加入草稿（仅本会话保留）」与「草稿已保存」；错误摘要可聚焦、字段错误提供跳到对应页与字段的入口。「编辑属性」入口落在 `SheetTable` 操作列（一次只展开一张图纸，勾选不等同进入编辑）。
- **新增未提交输入三选一模态（`web/src/components/sheets/UnsavedInputDialog.vue`）**：独立实现，复用公共可访问模态样式与焦点管理（焦点困绕、Esc=留在此处、关闭归还焦点）；不改 `useConfirm` 的 boolean 强确认协议。
- **App.vue 全局动作接线（`web/src/App.vue`）**：showPreview/write、关闭工作区、删除入口、快捷键、打开另一编辑上下文（新增操作/批量/编辑属性）及范围/筛选改变（隐藏当前编辑对象时经 `useSheetsWorkspace` 新增 `snapshotState`/`restoreState` 先还原再提示）均先接 guard；加入草稿使旧 `previewContext` 失效；write 不能捕获旧 context 在保存继续时执行，必须重新预览。切主标签不触发 guard、不销毁状态宿主（编辑上下文在标签之外实例化）。`submitCommands` 实现 `SubmitCommands`：草稿保存失败重试与最后一条动作等价时不重复加入同一命令批次。
- **混合批次显示缺口修复（任务 1 审查遗留）**：`features/sheets/projection.ts` 新增 `applyCommandOverlay`，`useSheetProjection.refresh()` 在结构派生结果上叠加命令簿元数据命令（update_sheet_properties/update_sheet_set/属性定义增删），批次同时含结构命令与属性值编辑时显示不回退既有图纸属性值；只叠加显示、不写回 base、不称已保存。`api/client.ts` 的 `ApiError` 透传服务端字段级错误（`fields`），供编辑器行内错误/摘要跳转消费。
- **测试（TDD，先红后绿）**：`web/tests/e2e/fixtures/sheets.ts` 扩展 `failDraftSave`（草稿 PUT 注入 422，含字段错误/DRAFT_CONFLICT，经闭包一次性/条件触发）、`transformWorkspaceGet`（工作区 GET 变换模拟基准刷新/版本变化）、`onDraftPut`（捕获草稿 PUT 请求体）；`derivedDocument` 既有图纸补基底属性值（贴近真实派生响应）。新增 `web/tests/e2e/sheets-editing.spec.ts`（19 项：跨页修改且搜索隐藏后仍提交两项、取消不污染 base、切主标签恢复缓冲且不触发保护、加入草稿成功退出并更新投影与计数、提交失败保留输入并呈现行内错误与可聚焦摘要、错误摘要跳转到第六页字段并聚焦、DRAFT_CONFLICT 保留输入提示过期、保存失败重试不重复加入同一命令批次、切换范围三选一三种选择、打开另一编辑上下文先三选一、全局预览先处理未提交输入且预览含全部命令、确认写入保存后旧预览失效必须重新预览且不执行、删除入口先处理缓冲且删除命令不夹带属性变更、基准刷新后编辑失效保留输入禁止提交、键盘焦点恢复、混合批次显示不回退既有属性值、保存中切换范围等保存完成不重复提示）。
- **任务审查修复（fix round 1，Important）**：`queueDeleteSubset` 未接 guard——用户可先打开编辑子集表单（编辑器干净放行）后产生未提交输入，再点「删除整个子集」直接走删除流程，投影移除子集后未保存缓冲被搁浅（可见但不可提交）。修复：`queueDeleteSubset` 与单行删除一致先接 `editor.guard`，有未提交输入先三选一决策（失败留下），确认后再走既有整子集删除强确认（confirm_delete_all_sheets/confirm_delete_main_dwg）。e2e 新增 2 项：「删除整个子集先处理未提交输入：加入草稿后继续进入整子集删除确认」（草稿只含属性编辑批次、不夹带删除命令）与「删除整个子集三选一：留在此处时子集删除不发生」。
- 验证：`cd web && npm run build`（check:api + vue-tsc + vite）零错误；Playwright e2e **116/116 通过**（95 既有 + 新增 21）。本任务只改 `web/` 与 changelog，Python 侧未触碰；仓库所有者并行的 SPEC-DM-010 文档/演示改动未纳入本提交。

## 2026-09-05（属性页独立交互 Demo）

- 新增 [SPEC-DM-010 属性页 Demo](docs/dst-manager/mockups/SPEC-DM-010-properties-demo.html)：两面板独立折叠、字段定义六条分页与增删、33 项文本属性平铺、字段名/值搜索、隐藏修改统计、三态标记、值对照、撤回输入、草稿撤销重做及 CSV/发布强确认模拟。
- 新增九项独立 Node 模型测试；修正搜索期间暂留字段误计为隐藏修改的问题。Node 测试 9/9、相关属性 pytest 20/20 与 Ruff 通过；完成桌面/窄窗浏览器检查，详见 [QA 记录](.planning/memos/dst-manager/2026-09-05-properties-demo-qa.md)。未修改生产 Web、后端或 PLAN-DM-015；SPEC-DM-010 保持 `review`。

## 2026-09-05（可配置列与图纸集级恢复）

- **新增显示列配置组合式函数（[PLAN-DM-015](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 任务 4，SPEC-DM-009 §5）**：`web/src/composables/useSheetColumns.ts` 产出 `visibleColumns`/`preferences`/`newPropertyCount`/`saveError`/`reset():Promise<void>`。消费任务 2 的 load/save_sheet_columns 壳桥与服务端图纸属性定义；`builtin:`/`sheet:` 命名空间区分内置列与自定义属性（字段身份含作用域，不与内置列同名冲突）；PropertyKey 名称按既有大小写匹配规则规范化、显示保留服务端原名。首次无存储时应用默认（文件名开、布局关、子集列全部范围显示/单子集范围隐藏、按定义顺序前三项属性开、不足三项全显）；已有存储时新增字段默认关并在入口计数提示，勾选后不再计数。删除字段只从可见配置移除、偏好以墓碑保留，撤销删除恢复此前开关。保存按工作区 ID 排队，切工作区后旧保存按代次作废、不覆盖新工作区偏好；存储失败显示提示且当前会话选择仍生效；恢复默认仅影响当前图纸集。
- **新增显示列配置面板（`web/src/components/sheets/ColumnSettings.vue`，接入 SheetToolbar「筛选」旁）**：固定图号/标题/状态/操作以禁用复选框锁定展示（可访问名「图号 固定」）；可选内置列与自定义属性复选框；自定义属性多时支持名称搜索；「恢复默认」按钮。面板打开状态自持，Esc/Tab 键盘模型与关闭后焦点回到触发按钮对齐确认模态；第一版只提供开关与「恢复默认」，不提供拖拽排序。
- **SheetTable 改为列配置驱动（`web/src/components/SheetTable.vue`）**：按 SPEC-DM-009 §5 列序渲染——固定选择/图号/标题/状态/操作 + 可选子集/文件名/布局 + 可见属性列（位于状态与操作之间）；选择 40px、图号最小 72px、操作稳定宽度且选择/图号/操作横向吸顶（左 0/40px、右 0），宽度不足仅表格内部横向滚动、不自动隐藏已配置列；标题最多两行（-webkit-line-clamp 2）且完整值悬停/键盘聚焦读取；文件名列只显示登记文件名部分（不同时堆叠三种路径），省略时可悬停/键盘聚焦读取完整值；状态列阻断与待变更可并存不遮盖，异常行提供「诊断」跳转入口。
- **诊断完整值复制（`web/src/layout/TaskOverlay.vue` 诊断页签）**：诊断列表项新增「复制」按钮（剪贴板不可用时回退 execCommand），复制内容为后端原值（code：message，含原始路径），满足 S-04「诊断路径与后端原值一致且可复制」。
- **测试（TDD，先红后绿）**：`web/tests/e2e/fixtures/sheets.ts` 扩展 `propertyNames`/`initialColumns`/`failSaveColumns`/`failLoadColumns`/`secondWorkspace` 选项（打开路由按 DST 路径分发第二工作区、预置偏好映射、存储失败注入）；新增 `web/tests/e2e/sheets-columns.spec.ts`（15 项：固定列不可关、默认列与前三属性、显示列开关立即生效、子集列按两种范围分别记忆、36 字段搜索、同名内置列独立配置、拉丁字母属性名取值按原始大小写、删除字段墓碑/撤销恢复、新增字段默认关并提示、恢复默认、重开恢复、不同工作区不串、存储失败回退、标题两行/文件名键盘聚焦、窄屏不隐藏、异常状态进诊断并可复制原始路径）；`main.spec.ts` 按 SPEC 列序更新图号/标题只读断言（td 下标 2/3 → 1/2，列序由旧 选择/子集/图号/标题 调整为 SPEC 的 选择/图号/标题/子集）。
- **任务 4 审查修复（fix round 1，Important）**：属性单元格取值改用服务端原始大小写键——`SheetTable.vue` 的 `propertyValue` 原先用 `col.key`（经 `toLocaleLowerCase()` 规范化的 PropertyKey）切片取值，而 `custom_properties` 按定义的原始大小写键控（Python `normalize_property_name` 只 trim、序列化原样透传），拉丁字母属性名（如 "No."/"Scale"）即使有值也静默显示「—」（中文属性名夹具未捕获）。修复：`SheetColumn` 携带原始 `name`（仅用于取值），小写 PropertyKey 只作偏好身份；新增 e2e「拉丁字母属性名取值按原始大小写且重开后偏好身份稳定」（先红后绿：临时回退修复后断言 `V4` 未显示而失败），夹具 `buildSubsets` 为附加/拉丁属性补确定性值。
- 验证：`cd web && npm run build`（check:api + vue-tsc + vite）零错误；Playwright e2e **95/95 通过**（80 既有 + 新增 15）；`git diff --check` 通过。本任务只改 `web/`，Python 侧未触碰。

## 2026-09-05（属性页功能讨论修订）

- 修订 [SPEC-DM-010](docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md)：取消人为属性分组，统一文本编辑；明确两面板独立折叠、属性值平铺不分页、字段名/属性值搜索、仅看修改，以及琥珀/蓝/红三态标记、比较基准和撤回边界。补齐空值、定义删除和 CSV 与未提交输入的冲突规则及 P-09～P-12 验收项。仅修改文档，状态保持 `review`，未实施产品功能。

## 2026-09-05（图纸页统一范围与单表导航）

- **新增图纸工作区状态组合式函数（[PLAN-DM-015](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 任务 3）**：`web/src/composables/useSheetsWorkspace.ts` 产出 `scope`/`focusedSheetId`/`selectedIds`/`filteredRows`/`visibleRows`/`hiddenSelectedCount`（初始 scope 为 all，行 ID 取服务端 ID），实例化于主标签之外，切换主标签保留勾选集合与筛选；从 `App.vue` 迁出范围/搜索/低频筛选/选择/首屏加载状态，移除 `selectedId`/`subsetFilter` 双真源。搜索覆盖完整路径与隐藏自定义属性（不依赖显示列）；全选覆盖全部匹配项（含未加载 80 行之后的 161 项），取消全选只移除当前匹配；投影删除对象从勾选集合修剪并提示「已从选择中移除 N 张已删除图纸」；范围子集被删除时降级为全部。
- **新增图纸导航树与工具栏（`web/src/components/sheets/SheetTree.vue`、`SheetToolbar.vue`）**：左树右表工作区——树为 全部图纸/子集/图纸 平铺（aria-level + 方向键/Home/End 漫游，子集可展开/收起），点击「全部图纸」只切范围、点击子集切范围、点击图纸经 `locateSheet` 切到所属子集并定位且不自动勾选，筛选排除目标时显示「目标被筛选隐藏」+「清除筛选并定位」而不暗中清条件。工具栏含常驻搜索、「搜索全部图纸」入口、经「筛选」展开的路径/诊断/待变更低频筛选、可清除条件标签、「已选 N 张，其中 M 张不在当前结果」吸顶选择条与「批量修改属性」展开输入。
- **图纸页改为唯一主表（`SheetsView.vue`、`SheetTable.vue`、`App.vue`）**：移除上下两张业务表与常驻新增表单；`SheetTable` 保留 `.sheet-table-window`/「图纸表格」可访问名，新增操作列「删除」入口与定位行高亮，状态列「阻断」与「待变更」可并存显示。新增操作（编辑子集/新增图纸/新建子集）改为主表上方非驻留过渡表单（一次只出现一种，任务 6 接入正式参照表单）；「编辑子集」目标子集由 `operationSubsetId` 指定、标题走缓冲副本不直接改工作区对象；空集/空范围/无结果分别给出原因与「创建首个子集」/「查看全部图纸」/「清除筛选」入口，不渲染无说明空表头。删除不再被引用的 `ProjectNavigation.vue`。
- **夹具扩展为全能力（`web/tests/e2e/fixtures/sheets.ts`）**：`installSheetsFixture(page,{sheetCount,subsetCount,propertyCount,empty,noProperties,longText,dualStatus,initialDraft})` 默认 5 子集/13 图纸/36 字段；fake 壳持有当前工作区 ID 与独立偏好映射（open_workspace_folder/load/save_sheet_columns/clear_workspace_context），持久草稿路由保持 expected_version 语义；`select_file` 缺省返回虚构 DST，支持 161 张大列表、空集、无属性、长标题超长路径与阻断/待变更双状态并存。
- **测试（TDD）**：新增 `web/tests/e2e/sheets-navigation.spec.ts`（13 项：单表初始范围、全部/子集范围切换、树点击定位不勾选、筛选隐藏目标提示、161 项首屏 80 与全选覆盖未加载、切范围保留集合与取消全选只移除当前匹配、投影删除修剪选择、隐藏属性/完整路径搜索、搜索默认当前范围可切全部、低频筛选展开与条件标签、空集引导、无结果清除入口、双状态并存）；迁移 `main.spec.ts` 中仅因 DOM 结构变化的 16 处选择器/交互（`.filter-grid`→树、`.subset-editor`→唯一主表、批量输入经「批量修改属性」展开、删除整个子集迁入编辑子集表单、`.editor`/`.sheet-browser`/`.filter-grid` 主题选择器），并给 `sheets-projection.spec.ts` 前两项补「新增图纸/编辑子集」入口展开，业务断言全部保留。
- 验证：`cd web && npm run build`（check:api + vue-tsc + vite）零错误；Playwright e2e **80/80 通过**（基线 67 + 新增 13）；`git diff --check` 通过。本任务只改 `web/`，Python 侧未触碰。

## 2026-09-04（可信壳上下文、列偏好存储与文件夹入口）

- **新增可信桌面当前工作区登记（[PLAN-DM-015](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 任务 2）**：`src/dst_manager/application/shell_context.py` 的 `ShellContext` 线程安全登记当前有效上下文（id/root/dst_path 全部来自服务端 Workspace）；`create_app` 新增仅 Python 内部可选回调 `on_workspace_opened`（默认 None，不改 HTTP/SSE 契约），`/api/workspaces/open` 成功后被以服务端 Workspace 调用一次，`run_desktop` 接线 `create_app(..., on_workspace_opened=context.set_workspace)`。壳桥四个新方法 `open_workspace_folder`/`load_sheet_columns`/`save_sheet_columns`/`clear_workspace_context` 均校验前端 workspace_id 等于当前有效上下文，路径只从上下文取得，返回 `{ok,value}/{ok,code,message}` 可序列化字典；旧 `select_file`/`on_files_dropped` 返回类型不变。独立桥错误码：`SHELL_WORKSPACE_UNAVAILABLE`、`SHELL_DIRECTORY_NOT_FOUND`、`SHELL_OPEN_FAILED`、`SHEET_PREFERENCES_INVALID`、`SHEET_PREFERENCES_IO`，不改任何 HTTP 错误码与业务 OpenAPI。
- **新增图纸集列偏好原子存储（`src/dst_manager/infrastructure/sheet_preferences.py`）**：`SheetPreferences(data_dir)` 的 `load`/`save` 将校验后的 schemaVersion=1 JSON（结构对应任务 1 的 `ColumnPreferences`：file/layout/subsetAll/subsetSingle 布尔 + `sheet:` 前缀属性开关映射，含字段/类型/数量上限校验，未知 schema 拒绝）存入 `data_dir/ui-preferences/sheets/<sha256(workspace_id)>.json`——workspace_id 只参与 SHA-256 摘要，绝不作为路径组成部分；同目录临时文件 + `os.replace` 原子替换、进程内锁串行化写入、失败保留旧文件；`load` 只读不创建目录，不触碰 DST/工程目录。
- **新增 Windows 资源管理器适配（`src/dst_manager/infrastructure/explorer.py`）**：以结构化 argv（`shell=False`，无 shell=True/cmd /c、不拼接用户字符串）调用 explorer 打开目录并尽量选中 DST，无法选中时打开已验证目录，目录缺失返回 `SHELL_DIRECTORY_NOT_FOUND`；非 Windows 返回不支持。
- **TopBar 文件夹入口与前端接线**：`web/src/layout/TopBar.vue` 新增可访问名称为「打开图纸集所在文件夹」的图标按钮——无桌面壳时禁用并解释（`title` 说明原因），桥晚到由 `shellReady` 响应式更新；`web/src/api/shell.ts` 按简报 verbatim 增加 `ShellResult`/`SheetShellBridge` 接口与 `openWorkspaceFolder`/`loadSheetColumns`/`saveSheetColumns`/`clearWorkspaceContext` 包装（旧桥缺新方法时返回 null 降级不抛错）；`App.vue` 点击经桥传当前 workspace_id（异步返回后再比较，旧工作区结果不进入新工作区），关闭成功后 best-effort 清空服务端上下文。
- **测试（TDD）**：新增 `tests/unit/test_sheet_preferences.py`（16 项：两 ID 隔离、同一 ID 重开、坏 JSON/未知 schema/字段与数量限制拒绝、数据目录不可写 IO 错、只读 load 不建目录、写入不触碰工程目录且失败保留旧文件、workspace_id 摘要防注入）与 `tests/unit/test_shell_workspace.py`（20 项：fake Explorer 只记录参数不弹窗，覆盖未打开/其他 ID/关闭后/目录消失/空格中文路径/路径命令注入拒绝/非 Windows 不支持/五个错误码/成功路径/create_app 回调登记与 HTTP 契约不变）；新增 `web/tests/e2e/sheets-folder.spec.ts`（4 项：无壳禁用并解释、新桥传当前 ID 且成功不报错、旧桥缺方法降级提示、关闭后清上下文且按钮消失）。
- 验证：`uv run ruff check .` All checks passed；`uv run pytest -q` 全量 **676 项（604 passed / 72 skipped，0 failures，退出码 0）**——基线 641 + 本任务新增 35；`cd web && npm run build`（check:api + vue-tsc + vite）零错误；Playwright e2e **67/67 通过**（63 既有 + 新增 4）；`git diff --check` 通过。真实 Windows 桌面「空格目录打开并实际选中 DST」人工验收留待用户执行，未以 mock 代替系统集成证据。

## 2026-09-04（建立图纸页权威结构投影与命令身份验证）

- **新增图纸页权威结构投影先行门禁（[PLAN-DM-015](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md) 任务 1）**：结构变化（insert/delete/rename）的显示结果改为经内部 `/changes/preview` 的 `execution_intent.derived_document` 获取服务端权威投影，浏览器不再本地拼装结构；该内部请求与用户显式发布预览分离——绝不设置 `previewContext`、不打开发布确认、不启动 CAD，因此不会启用「确认写入」。新增 `web/src/features/sheets/types.ts`（公共类型 verbatim：SheetScope/ProjectionStamp/PropertyKey/ColumnPreferences/SheetRef/SubmitResult/SubmitCommands）、`web/src/features/sheets/projection.ts`（`applyDerivedProjection(base,preview)`：acsm_id 映射 UI id，名称/number/layout/custom_properties 全取响应，sheet_count/subset_count 从完整集合计数，新增对象不填造 Handle 或 resolved_path，不改 base）、`web/src/composables/useSheetProjection.ts`（只读 projection/stamp/pending/error + `refresh():Promise<SubmitResult>`；按 workspace/revision/命令快照/请求代次校验，乱序响应只应用最新代次；失败保留上一份结果并标为失效，不展示「已同步」；非结构动作清空旧投影并失效在途请求）。`App.vue` 仅改 `rebuildDraftProjection` 调用边界：元数据/属性定义沿用本地 `projectWorkspace`，结构动作额外触发内部投影并经 watch 应用到显示 workspace。
- **固化命令索引风险（drafts.ts）**：`projectCommands` 新增结构边界——结构动作（update_subset_title/delete_sheet/delete_subset/insert_sheet/insert_subset）之间的同键命令不再跨边界去重压缩，避免早期命令被移除使其后的结构命令索引前移、改变服务端派生的新增 AcSm ID；旧草稿仍按原兼容逻辑恢复。前端只显示服务端派生 ID，不按行号偷偷重绑、不自行生成 UUID5。
- **显示文案对齐 SPEC-DM-009 单表格式**：`SheetsView.vue` 计数由「15 / 15 张」改为「匹配 15 / 全部 15 张」（任务 3 单表导航沿用同一文案），使投影结果可被 e2e 观测。
- **测试（TDD）**：新增 `tests/unit/test_sheet_projection_contract.py`（4 项，用最小临时 DST 夹具经真实 `preview_changes` 路径、无 CAD，覆盖 insert→属性编辑 ID 稳定、insert→insert 顺序/去重一致、delete→undo 不持久化、rename→insert 命令索引敏感）；新增 `web/tests/e2e/sheets-projection.spec.ts`（4 项，先红后绿：投影请求不启用确认写入且逆序响应只应用最新代次；结构动作之间不跨边界去重、服务端命令索引稳定；撤销结构动作后早期返回恢复 pending、旧在途响应被丢弃且可再次投影；持久草稿恢复跨结构边界同键命令不被去重压缩）与最小夹具 `web/tests/e2e/fixtures/sheets.ts`（`installSheetsFixture(page,{sheetCount,propertyCount,initialDraft})`，只含虚构路径与假壳/假路由；任务 3 再扩展全能力）。
- **任务审查修复（fix round 1）**：`useSheetProjection` 早期返回分支（无结构动作）补 `pending.value=false`/`error.value=""`，避免撤销结构动作后在途请求的 finally 因代次不匹配跳过重置导致 pending 永久卡死；夹具与规格按审查补齐持久草稿恢复兼容用例。
- 验证：`uv run ruff check .` All checks passed；`uv run pytest -q` 全量 **641 项通过**（退出码 0；基线 637 + 新增 4）；`cd web && npm run build`（check:api + vue-tsc + vite）零错误；`npm run test:e2e` **63/63 通过**（59 既有 + 新增 4）。

## 2026-09-04（修复打包遗漏 XSD 与 changelog 门禁误配）

- **修复分发包遗漏 acsm-v1.xsd（Critical，PLAN-DM-014 最终审查 C-1）**：`src/dst_manager/infrastructure/acsm_xml/contract.py` 的 `_load_schema()` 用 `Path(__file__)` 定位 `schema/acsm-v1.xsd`，frozen 态下 `__file__` 指向 `_internal` 内 .pyc，而 `packaging/dst-manager.spec` 的 `datas` 未含 schema 目录 → 打包后真实 DST 加载（load_acsm → validate_schema）必崩。修复：spec `datas` 追加 `..\src\dst_manager\infrastructure\acsm_xml\schema` → `dst_manager/infrastructure/acsm_xml/schema`；新增静态守护测试 [tests/unit/test_packaging_spec.py](tests/unit/test_packaging_spec.py)（不跑 PyInstaller）：断言 XSD 存在、spec datas 含 schema 路径条目，并扫描 `src/dst_manager` 内新增 `Path(__file__)` 资源定位必须登记白名单（contract/api/database/runtime）且被 spec 覆盖，防止未来再次遗漏。
- **修复 release.ps1 changelog 门禁子串误配（Important，最终审查 I-1）**：旧 `.Contains("v$Version")` 会让 `v0.3.3` 误命中 `v0.3.30` 记录且版本号未正则转义。改为章节标题正则 `(?m)^## .*v$([regex]::Escape($Version))\b` 匹配；[tests/unit/test_release_scripts.py](tests/unit/test_release_scripts.py) 的 `REQUIRED_RELEASE_STEPS` 仍含 "changelog.md"，无需改动。
- **附带小修**：[packaging/entry.py](packaging/entry.py) docstring 更正开发态入口表述（`pyproject.toml` `[project.scripts]` 的 `dst-manager` script，原误指 main.py）；根 [README.md](README.md)「打包与 release」补 `.env` 按启动时工作目录解析（双击启动即 exe 同级）与数据/草稿目录（`%LOCALAPPDATA%\dst-manager\data\` 与 `drafts\` 为同级目录）说明，修正原文易误读为 drafts 位于 data 之下的措辞；[tests/unit/test_packaging_spec.py](tests/unit/test_packaging_spec.py) 按复审意见收紧：白名单改按相对 src/dst_manager 的路径登记、断言 spec datas 目标路径与 frozen 态 __file__ 定位逐级吻合、注明扫描仅覆盖 `Path(__file__)` 字面写法。
- 验证：`uv run ruff check .` All checks passed；`uv run pytest -q` 全量 **637 项 565 passed / 72 skipped**（0 failures / 0 errors，退出码 0，约 40s；634 项基线 + 新增 test_packaging_spec 3 项）。

## 2026-09-04（v0.3.4 打包与 release 收尾：根 README 文档与全量回归）

- 根 [README.md](README.md) 新增「打包与 release」小节（[PLAN-DM-014](.planning/plans/dst-manager/PLAN-DM-014-windows-release-packaging.md) Task 9，位于「一键启动」相关章节之后）：面向分发给内部同事的绿色免安装包，给出 `scripts/build_release.ps1`（`-Version`/`-SkipPlugins`，版本缺省取 pyproject.toml）与 `scripts/release.ps1 -Version <版本>`（前置校验 + Ruff/pytest 门禁 + 构建 + 本地 tag）两条命令，并说明产物 `dist/releases/dst-manager-v<版本>-win64.zip` 解压即用：双击 `dst-manager.exe` 打开桌面壳、数据与草稿在 `%LOCALAPPDATA%\dst-manager\`、Core Console 经 exe 同级 `.env` 配置（`autocad_2016_console`/`autocad_2020_console`）、`dst-manager.exe doctor` 自检、tag 仅本地不推送。
- 全量回归（真实验证）：`uv run ruff check .` 首查报 3 项——`src/dst_manager/runtime.py:25` B009（对常量属性使用 `getattr(sys, "_MEIPASS")`）与 `tests/unit/test_runtime.py:58` I001/F401（import 未排序 + `sqlalchemy.inspect` 未使用），均来自本计划 Task 1-4 已提交代码；已就地修复并复核 Ruff 全绿，修复改动留在工作区未随本提交入库（本提交按任务范围仅暂存 README.md 与 changelog.md），下次执行 release 前需一并提交。`uv run pytest -q` 全量 **634 项 562 passed / 72 skipped**（0 failures / 0 errors，退出码 0，约 40s），与基线 547/72 + 本计划新增 15 项（runtime 3 + api 1 + migrate 1 + shell 1 + config 3 + release_scripts 6）一致。
- 简报 Step 3「端到端 release 演练」按任务约定跳过留待用户：`release.ps1` 要求干净工作区、main 分支、`pyproject.toml version` 与 changelog `v<版本>` 记录到位；当前工作区含用户未提交改动且 lint 修复未提交，不具备执行条件。

## 2026-09-04（接受图纸页规范并编制实施计划）

- 根据用户对交互 Demo 的确认，将 [SPEC-DM-009](docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md) 标记为 `accepted`，追加确认记录并更新文档索引；SPEC-DM-010 仍为 `review`。
- 新增 [PLAN-DM-015 图纸页单表工作区实施计划](.planning/plans/dst-manager/PLAN-DM-015-sheets-workspace-ui.md)，状态为 `proposed`：8 项任务覆盖权威结构投影、受限壳桥与列偏好、统一单表、列配置、分页缓冲、参照表单、草稿操作和完整验收，明确新增对象 ID 与命令压缩的先行验证门禁。本次只修改文档，未启动产品代码实施。

## 2026-09-04（图纸页交互 Demo）

- 新增 [SPEC-DM-009 单文件交互 Demo](docs/dst-manager/mockups/SPEC-DM-009-sheets-demo.html)，供功能评审：单表导航、范围筛选、显示列记忆、12 项属性分页编辑、未提交输入保护、参照位置插入、子集表单、删除、批量属性和草稿撤销/重做。文件夹、模板选择及发布均明确模拟，未修改产品前后端或工程文件。
- 新增独立 Node 数据模型测试（7/7 通过），完成浏览器交互与 1440px/900px 截图检查；相关 `tests/unit/test_core.py` 通过。全量 Ruff 当次检查受其他工作区改动 `src/dst_manager/runtime.py:25` 的 B009 阻塞，未越界修改。详细范围与限制见 [Demo 验证记录](.planning/memos/dst-manager/2026-09-04-sheets-demo-qa.md)。

## 2026-09-04（图纸页功能设计讨论修订）

- 修订 [SPEC-DM-009](docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md)：纳入已确认的参照对象插入交互、显示列配置与图纸集级记忆、属性编辑分页、直接删除及灰区规则；明确顶栏图纸集名称、打开所在文件夹的受限壳桥扩展和全部图纸范围语义，补充验收条件。仅修改文档，未实施功能；规范仍为 `review`。

## 2026-09-04（PLAN-DM-014 Windows 打包与 release 实施计划）

- 新增 [PLAN-DM-014 Windows 绿色分发包与一键 release 流程实施计划](.planning/plans/dst-manager/PLAN-DM-014-windows-release-packaging.md)，状态为 `proposed`，依据 [ARCH-DM-002](docs/dst-manager/architecture/ARCH-DM-002-windows-release-packaging.md)：9 个任务依次为 `runtime.py` 路径解析模块、三处 frozen 路径适配（前端静态目录/Alembic 迁移/Worker 拉起）、`Settings` frozen 默认值、`packaging/entry.py` + PyInstaller spec 与本地构建冒烟、`build_release.ps1` 纯构建脚本、`release.ps1` 一键 release（门禁 + 本地 tag）、文档与全量回归。本次仅编写计划，未修改产品代码。

## 2026-09-04（ARCH-DM-002 Windows 打包与 release 流程设计）

- 新增 [ARCH-DM-002 Windows 绿色分发包与一键 release 流程](docs/dst-manager/architecture/ARCH-DM-002-windows-release-packaging.md)，状态为 `accepted`（2026-09-04 用户确认）：确定 PyInstaller onedir + zip 绿色包方案（否决 onefile 与嵌入式 Python），明确三处 frozen 路径适配（前端静态目录、Alembic 迁移、Worker 子进程拉起）、`packaging/entry.py` 双击入口、spec 数据文件与 hiddenimports 清单、分发包内插件 DLL 与 `data_dir` 默认值，以及 `build_release.ps1` / `release.ps1` 两层构建与门禁流程；代码签名、安装器、CI 与远程 Release 明确列为范围外。更新 DST Manager 文档索引。本次仅编写设计文档，未修改产品代码。

## 2026-09-04（中心工作区双 SPEC 设计）

- 新增 [SPEC-DM-009 图纸页](docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md) 与 [SPEC-DM-010 属性页](docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md)，状态为 `review`：分别定义单表导航与按需编辑、字段定义分页与属性分组表单，补齐未提交输入保护、异常与验收标准。
- 更新 DST Manager 文档索引及 SPEC-DM-006 细化文档入口；公共外壳和写入安全门禁仍引用既有规范。本次仅编写文档，未修改产品代码或发布版本。

## 2026-09-04（v0.3.3 修复输入控件不随主题切换）

- **修复深色/浅色模式下文本输入框与下拉选单视觉不变**：旧样式块对 `input`/`select` 只设置 `padding`/`border`，背景与文字色落到浏览器 UA 默认白底黑字，且全站未声明 `color-scheme`。修复两项：① `web/src/style.css` 令牌区声明 `:root{color-scheme:light}` 与 `html[data-theme="dark"]{color-scheme:dark}`（原生控件、下拉弹出列表与滚动条随主题渲染）；② 旧块新增通用控件规则 `input:not([type="checkbox"]):not([type="radio"]),select,textarea{background:var(--color-bg-surface);color:var(--color-text-primary)}`——排除 checkbox/radio 以免影响确认模态勾选框外观（`ConfirmModal` 的勾选框由 UA 按 `color-scheme` 自行渲染）。e2e 新增「深色模式下文本输入框与下拉选单随主题切换背景」（先红后绿：断言 `.filter-grid` 输入框与下拉计算背景为 `--color-bg-surface` 深色值）。
- 验证：`cd web && npm run test:e2e` **59/59 通过**（58 既有 + 新增 1）、`npm run build` 零错误；后端零改动。

## 2026-09-04（v0.3.3 修复中心视图区域不随主题切换）

- **修复深色/浅色切换只作用于外围框架、标签中心区域不生效**：`web/src/style.css` 存在两层并存——语义令牌区（`:root` 浅色 + `html[data-theme="dark"]` 深色，外壳 TopBar/TabBar/ActionDock/任务浮层/模态消费令牌，随主题切换）与旧单页版压缩样式块（`.editor`、`aside`、`table`、`.panel`、`.sheet-table-window`、`fieldset` 等，被中心视图区域命中）。旧块全部硬编码浅色值（`background:white`、`#172033`、`#f7f9fc` 等 24 种），不消费任何令牌，CSS 变量切换对其无效。修复：旧块内全部硬编码颜色等值映射到既有语义令牌（`background:white→var(--color-bg-surface)`、文字色→`--color-text-primary/secondary/muted`、边框→`--color-border-subtle/strong`、状态色→`--color-accent/success/warning/danger` 及对应 `-bg`、`box-shadow:0 1px 3px #17203312→var(--shadow-1)`），仅 `.modal-mask` 遮罩的 `rgba(16,24,40,.55)` 保留（半透明黑双主题皆宜）。e2e 新增「深色模式下中心视图区域随主题切换背景」（先红后绿：播种 dark 主题打开工作区，断言 `.sheet-browser` 计算背景为 `--color-bg-surface` 深色值）。
- 验证：`cd web && npm run test:e2e` **58/58 通过**（57 既有 + 新增 1）、`npm run build` 零错误；后端零改动。

## 2026-09-04（v0.3.3 标签化外壳最终分支审查修复）

- **修复 CSV 导入确认模态对齐发布强确认**（Important，[SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.2/§10.3）：`web/src/composables/useCsvImport.ts` 的 `importCsv` 确认由 `danger:false`、无勾选、message 仅"确认导入属性定义？"改为与 §9.1 全部正式写入共用同一危险确认——`danger:true + requireCheckbox:true + reversibility:"不可逆" + impactLines 受影响属性定义清单`（从 `csvPreview.changes` 派生：`新增/跳过/冲突属性「名称」（作用域，影响 N 张图纸）`，changes 为空时回退受影响文件清单）；message 明确"原 DST 将永久备份"。同步更正 changelog Task 2/Task 3 将 CSV 导入归类为"低风险动作"的表述。e2e 新增「CSV 导入确认模态为强确认：未勾选时确认按钮禁用」（先红后绿）。
- **修复标签激活态随工作区加载复位**（Important）：`active` 停留在 `revisions` 时，`openByPath`/`refreshWorkspace` 成功路径不重载修订列表，而 `beginWorkspaceLoad` 内 `invalidateRevisionState` 已清空 `revisions`，导致虚假"暂无修订历史"空态（closeWorkspace 与发布 SUCCEEDED 后 refreshWorkspace 均触发）。修复（最外科方案）：`web/src/App.vue` 两处成功路径末尾加 `if(active.value==="revisions")void loadRevisions()`；不在 `beginWorkspaceLoad` 复位 active（不强制切走用户页签），`loadRevisions` 的 `isRestoreExecuting`/`isWorkspaceLoading`/代次防重入门禁原样保留。e2e 新增「停留在修订历史标签重开工作区后修订列表重新加载」（先红后绿）。
- **修复 TopBar 状态胶囊展示原始枚举**（Minor）：`web/src/layout/TopBar.vue` 的 `DST {{dstStatus}}` 直接显示 `dst_validation.status` 原始枚举（`INVALID_REPAIR_REQUIRED`/`INVALID_UNRECOVERABLE`），违反"枚举不进用户文案"约定。新增 `statusLabel(status)` 映射为中文三态（与 `RepairStatusPanel`/App.vue dock 文案一致风格）：`VALID→正常`、`REPAIRED→已修复`、`INVALID_UNRECOVERABLE→不可恢复`、其余 `INVALID_*→需修复`；颜色映射 `statusClass` 不变。
- **修复修复执行中关闭工作区导致 isRepairExecuting 卡死**（Minor）：`executeRepair` 请求在途时用户可点关闭 → `closeWorkspace` → `invalidateJobMonitor(true)` → 请求返回时 `isCurrentJobGeneration` 为 false → `useRepair.ts` finally 不复位 → `isRepairExecuting` 永久 true、修复按钮永久禁用。选**关闭禁用**方案（与恢复语义对齐）：`App.vue` 的 `:close-disabled` 由 `isRestoreExecuting` 扩为 `isRestoreExecuting||isRepairExecuting`——props 链（App.vue → TopBar）为直连式简单，无需备选的 closeWorkspace 显式复位；修复执行中关闭被禁用后，代次失效只能由外部触发，该卡死路径不可达。
- 验证：`cd web && npm run test:e2e` **57/57 通过**（55 既有 + 新增 2）、`npm run build`（check:api + vue-tsc + vite）零错误；后端零改动（`uv run ruff check .` 如实记录无 Python 变更）。

## 2026-09-04（v0.3.3 标签化外壳 Task 8 收尾：修订历史标签完善与 v0.3.3 全量验证）

- 修订历史标签完善（[PLAN-DM-013](.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md) Task 8，对应 [SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §4.2 标签③、§6.5）：`web/src/views/RevisionsView.vue` 空状态由简单 `<p class="empty">` 升级为空状态卡——标题「暂无修订历史」、说明「发布首个变更后，此处会记录每个可恢复的修订版本。」、下一步动作提示「前往「图纸」标签发起首个变更，发布后即可在此恢复。」（§6.5「说明 + 下一步动作」，动作即提示去标签①发起变更，不设跳转按钮以免打断）；样式全部引用设计令牌。
- `web/src/App.vue`（512→514 行）恢复预览接入任务浮层修改预览页签：新增 `previewRestoreAndOpen(revision)` 包装——`previewRestore` 成功（`restorePreview` 已写入）后 `openOverlay("prev")`，与 `showPreview` 共用 §9.1 统一预览门禁呈现（§4.2 标签③「先预览（进任务浮层"修改预览"页签）→ 危险确认模态 → 恢复为新修订」）；`RevisionsView` 的 `@preview` 由 `previewRestore` 改接 `previewRestoreAndOpen`。`restoreRevision` 确认执行后任务响应经 `setJob` 已自动 `openOverlay("prog")`（Task 6 fix round 1 接线，核实未重复）。激活标签③时加载修订**核实 Task 4 已接线**（`selectTab`/`onTabKeydown` 切换至 `revisions` 即调 `loadRevisions`，内部含 `isRestoreExecuting` 防重入与 `revisionGeneration`/`workspaceLoadGeneration` 代次保护），未重复加 `watch`。
- e2e 新增 2 项（TDD：第 2 条先红后绿，第 1 条因接线已存在首跑即绿）：①「修订历史标签激活时加载列表，空修订显示暂无修订历史」——`page.route("**/api/revisions**")` 在点击标签前安装，断言空状态卡「暂无修订历史」可见且 `asked` 为真（激活时才加载）；②「恢复预览在任务浮层修改预览页签呈现」——跟随既有「修订恢复先预览再确认为新修订」mock 修订列表与 restore-preview，断言点击「恢复预览」后任务浮层「修改预览」页签 `aria-selected="true"`。与简报用例的最小修正：恢复按钮名沿用既有契约「恢复预览」（简报正文写作「预览恢复」）。
- **v0.3.3 收尾**：`PLAN-DM-013` 状态 `proposed` → `completed`（全部任务步骤勾选，追加「实际验证」小节）；[ROADMAP-DM-001](.planning/roadmaps/dst-manager.md) v0.3.3 行更新为已完成并引用 PLAN-DM-013；[docs/dst-manager/README.md](docs/dst-manager/README.md) 当前版本更新为 `v0.3.3` 并补外壳重建说明。全量验证：`uv run ruff check .` All checks passed；`uv run pytest -q` **547 passed / 72 skipped**（619 项，0 failures / 0 errors，退出码 0）——与 v0.3.2 基线 545 passed / 72 skipped 的差异为提交 `a83e92b`（修复派生 DWG 文件名后缀区间压缩）新增 2 项 `test_core.py` 用例，本次后端零改动如实记录；`cd web && npm run build`（check:api + vue-tsc + vite）零类型错误；Playwright e2e **55/55 通过**（53 既有 + 2 新增，51.1s）。本计划 Task 1-7 的 e2e 数字演进：40→42→42→45→49→52→53→55，逐 task 记录见下方各章节。

## 2026-09-04（v0.3.3 标签化外壳 Task 7：SSE 任务通知 toast 与浮层跳转）

- 新增 `web/src/composables/useToast.ts`（[PLAN-DM-013](.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md) Task 7，对应 [SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.6）：`useToast()` 返回 `{toasts,pushToast,dismiss}`——`pushToast({type:"ok"|"fail",title,body,jumpTab?})`，`ok` 5 秒自动消失、`fail` 常驻不自动消失；同屏上限 4 条，超出移除最旧（`slice(-3)`）。`Toast` 类型含 `jumpTab?:"prog"|"prev"|"diag"`。
- 新增 `web/src/components/ui/ToastHost.vue`：`aria-live="polite"` 固定容器（`position:fixed;top/right`，z-index 1100 高于确认模态 1000）；`ok` 项 `role="status"`、`fail` 项 `role="alert"`；每项关闭 `✕` 与可选"查看"按钮（`jumpTab` 存在时渲染，emit `jump` → App 调 `openOverlay(tab)`）；样式全部引用设计令牌（无裸十六进制），`prefers-reduced-motion:no-preference` 下才播放滑入动画。
- `web/src/composables/useJobMonitor.ts`：deps 增加可选的 `pushToast` 与 `shouldSuppress`（经 deps 注入，保持既有 deps 兼容），新增 `notifyTerminal(job)` 在 `watchJob.onmessage` 与 `pollJob` 的终态分支调用（SSE 断线转轮询后通知照常）：`SUCCEEDED`→`ok("任务成功",jumpTab:"prog")`；`FAILED`/`ROLLED_BACK`/`BLOCKED_FILE_LOCK`→`fail("任务失败",body 含 error_code 与"整批未发布"语义,jumpTab:"prog")`；`NEEDS_REVIEW`→`fail("需人工检查","发布状态需要人工检查，禁止直接重试")`。**抑制规则**：`shouldSuppress()` 为 `overlayOpen&&overlayTab==="prog"` 时不弹（用户正看实施进度页签）；SUCCEEDED 分支在 `onJobSucceeded` 刷新工作区（复位浮层）前先评估抑制，保证"正看进度不重复弹"。通知不经 `setJob`（onmessage 直写 `job.value`），故用户折叠/切走浮层后任务到达终态仍能感知。
- `App.vue`（504→512 行）：浮层状态 `overlayOpen/overlayTab/openOverlay` 上移到 `useJobMonitor` 之前供 `shouldSuppress` 闭包引用；新增 `useToast()` 接线 `pushToast`/`dismiss` 与 `shouldSuppress`；新增 `jumpOverlay(tab)`（仅放行 `prog/prev/diag` 合法页签后复用 `openOverlay`）并在根模板挂载 `<ToastHost :toasts @dismiss @jump>`。`setJob` 语义保持 Task 6 fix round 1 不变（任何状态任务响应均 `openOverlay("prog")`）。
- e2e 新增 1 项「任务成功经 SSE 推送 toast 且失败通知常驻可查看」（先红后绿）：跟随既有 SSE mock（`installMockEventSource`），execute 返回 QUEUED 启动 watchJob，折叠浮层（模拟用户切走）后 `__emitJob` 推送终态 FAILED——断言 `role="alert"` 含"任务失败"可见、`waitForTimeout(6000)` 后仍常驻、点"查看"跳浮层实施进度页签（`aria-selected=true`）、点"✕"后移除；抑制规则由既有「任务回滚终态后 ActionDock 解锁」「NEEDS_REVIEW 终态时 ActionDock 锁定」两用例隐式覆盖（浮层开在实施进度页签时终态到，不弹 toast、既有断言不受干扰）。Playwright e2e **53/53 通过**（52 既有 + 1 新增）、`npm run build`（check:api + vue-tsc + vite）零类型错误、`App.vue` 512 行（相对 Task 6 的 504 +8：toast 接线与模板挂载为 Task 7 必要增量）。

## 2026-09-04（v0.3.3 标签化外壳 Task 6：任务进度预览与诊断迁入右缘三页签任务浮层）

- 新增 `web/src/layout/TaskOverlay.vue`（[PLAN-DM-013](.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md) Task 6，对应 [SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §4.1/§4.2/§7.2）：右缘任务浮层 `aside[role="complementary"][aria-label="任务浮层"]`，三页签 `实施进度/修改预览/诊断` 复用 `useShellTabs` 键盘模型（受控：`tab` prop 变化同步 `active`，`watch` 双向回写 `update:tab`）；`prog` 原样迁入 `JobStatusPanel`（`retry` 上抛）、`prev` 原样迁入 `PreviewPanel`（确认模态仍在 App 层）、`diag` 迁入诊断列表（沿用 `<details>` 结构）+ `RepairStatusPanel`（previewRepair/executeRepair/cancel 上抛）；存在阻断诊断时诊断页签渲染红点 `<span aria-hidden="true">●</span>` + `aria-description` 提示；折叠用 `hidden` 于面板体、页签行保留窄条（始终可见触发按钮，折叠按钮 `aria-expanded`/`aria-label="收起任务浮层"`/`aria-controls`），折叠不卸载、任务继续执行。
- `App.vue`（500→504 行）持有浮层状态 `overlayOpen`/`overlayTab`/`openOverlay`（Task 7 toast 抑制与"查看"跳转依赖），并把 `setJob` 收敛为 QUEUED 自动激活唯一入口（execute/executeRepair/importCsv/restoreRevision 拿到 QUEUED 即 `openOverlay("prog")`）；`showPreview` 成功回调内 `openOverlay("prev")`；`refreshWorkspace`/`closeWorkspace`/`beginWorkspaceLoad` 复位浮层（`overlayOpen=false`、`overlayTab="prog"`）。迁移过渡期直属面板：删除 App 直属 `JobStatusPanel`/`PreviewPanel` 挂载与 `SheetsView` 的 `RepairStatusPanel`/诊断 details（移除相关 props/emits），模板重构为 `TopBar + shell-body（内容区 + 右缘浮层）+ ActionDock` 布局；`SheetsView` 保留 `blocking` 计数标题行、迁出修复门禁与诊断列表。
- `web/src/style.css` 新增响应式断点（§4.3）：`@media (max-width:1120px)` 浮层 `position:fixed;right:0;top:0;bottom:0` 抽屉化（默认折叠，折叠按钮即始终可见触发入口）；`@media (max-width:900px)` 补 `TabBar` 容器横向滚动（TabBar 组件内已含 `overflow-x:auto`，规则兜底）；结构树折叠留待 PLAN-DM-004。
- e2e 全量适配 + 新增 2 项（Playwright 语义/既有 mock 冲突处最小修正并记录）：① 简报用例缺前置（`showPreview` 需已有草稿命令且 mock 预览成功），补"加入动作 + mock 预览"；② 折叠断言 `overlay.toBeHidden()` 与 §4.3"页签行保留窄条（始终可见触发按钮）"冲突——折叠后页签行仍是可见窄条而非整体隐藏，改为断言面板体 `.ov-body` `toBeHidden` + 折叠按钮 `aria-expanded="false"`；红点用例折叠态页签不可见，先点"展开任务浮层"再断言；③ 既有 49 项覆盖不删——`JobStatusPanel`/诊断 details/`RepairStatusPanel` 相关定位（`CAD 操作分流`/`失败任务逐 DWG 详情`/`CSV 导入`/`修复门禁`/`修订恢复` 五处）改为经浮层路径：预览成功后浮层自动展开到修改预览页签、FAILED/SUCCEEDED 直返任务切"实施进度"页签查看、修复门禁先展开并切"诊断"页签。Playwright e2e **51/51 通过**（49 既有适配 + 2 新增）、`npm run build`（check:api + vue-tsc + vite）零类型错误、`App.vue` 504 行（相对 Task 5 的 500 仅 +4，浮层状态与自动激活接线为 Task 6 必要增量，迁出面板省下的行数被接线抵消）。
- 评审修复（Task 6 fix round 1/5，2 条 Important）：① 终态（非 QUEUED）任务响应在浮层关闭时不可见（迁移回归）——后端 restore 为同步发布可直返 FAILED/ROLLED_BACK/NEEDS_REVIEW 终态，恢复预览不触发 `openOverlay`、`useRestore` 对 FAILED 响应不设 error，用户点"恢复为新修订"后静默失败无任何信号（Task 6 前内联 `JobStatusPanel` 恒可见）。修复：`setJob` 由"仅 QUEUED"改为**收到任务响应（任何状态）即 `openOverlay("prog")`**——用户刚发起动作任务无论排队还是已终态都应可见；已开浮层时幂等不重复弹；QUEUED 分支语义保留，仅扩大到全部状态。② `restoreRevision` 的 QUEUED 自动激活被同函数无条件 `refreshWorkspace` 复位抵消（useRestore.ts：setJob 后紧跟 `await refreshWorkspace` → `beginWorkspaceLoad` 置 `overlayOpen=false`，浮层闪开即闭；当前后端不返回 QUEUED 故不可达，但接线实际失效）。修复（经裁决）：`refreshWorkspace` 收敛到仅 `SUCCEEDED` 时执行（对齐 execute/executeRepair/importCsv 三入口），非 SUCCEEDED 终态任务详情由浮层实施进度页签呈现（与①配合提供信号）。e2e 新增回归用例「恢复直返终态 FAILED 时任务浮层自动展开到实施进度页签」（restore 路由 mock 直返终态 FAILED，断言点击"确认恢复"后浮层可见、实施进度页签激活、"任务 restore-failed"/`RESTORE_FAILED` 可见，先红后绿）。Playwright e2e **52/52 通过**（51 + 回归 1）、`npm run build` 零类型错误。

## 2026-09-04（v0.3.3 标签化外壳 Task 5：落地全局操作栏草稿栈浮窗与快捷键门禁）

- 新增全局底部操作栏 `web/src/layout/ActionDock.vue`（[PLAN-DM-013](.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md) Task 5，对应 [SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §4.1/§6.8/§6.9/§7.1）：`footer[role="contentinfo"]` 常驻底栏（`position:sticky;bottom:0`），左侧草稿计数芯片（`草稿 N/M ▲`，`aria-expanded`/`aria-controls` 指向浮窗）＋撤销/重做，右侧 `预览变更`（Primary）＋`确认写入`（Danger）＋内联禁用原因；禁用时 `disabled` + `title` + 内联文本双通道。草稿栈浮窗（`position:absolute;bottom:100%` 限高 300px 滚动，`role="dialog" aria-label="草稿动作栈"`）内嵌 `DraftActionsPanel`（props/emits 原样桥接，组件零改动）＋ 保存状态行（保存中/已保存/保存失败）＋失败重试按钮；`Esc` 关闭并把焦点还给计数芯片（§7.2 抽屉模型，全局 Esc 兜底，模态遮罩自身 `stopPropagation` 互不干扰）。
- 新增 `web/src/composables/useHotkeys.ts`（§7.1）：window keydown 捕获 `Ctrl/Cmd+O/Enter/S/Z/Shift+Z` 并 `preventDefault`；`Ctrl+S` 仅在 `writeNeedsModal` 时调 `write()`（模态内仍需勾选，无执行旁路），否则给非阻断提示（Task 7 toast 前用既有 `error` 值）；`Ctrl+O` 复用 `selectAndOpenDst`（无壳回退聚焦 WelcomeView 路径输入），`Ctrl+Enter` 仅在允许预览态触发，`Ctrl+Z/Shift+Z` 直接走 `undoDraft/redoDraft`（内部自带 stale/cursor 守卫）。
- `App.vue`（468→500 行）落地 §6.9 操作×状态矩阵为 `dock` computed 唯一出口并统一写入门禁：新增 `isPreviewing` ref（仅作按钮 loading 呈现，不阻止再次发起——竞态仍由 `previewGeneration` 丢弃乱序响应）；`write()` 统一入口——`writeNeedsModal` 时 `confirmAction(发布模态)`（沿用 Task 2 迁移文案：`danger:true + requireCheckbox:true + reversibility:"不可逆" + impactLines 受影响清单`）→ 确认后调 `execute()`，`execute()` 移除自行开模态改由 `write()` 前置；矩阵分支逐条落地（任务进行中/恢复执行中→全部禁用"任务进行中"、REPAIRED/INVALID→"存在待确认修复"/"需先修复"、无草稿→"没有待发布变更"、未预览→"请先预览"、预览过期/基准变化→"预览已失效，请重新预览"、不可执行→"预览不可执行"、有效可执行→开模态）；`PreviewPanel` 既有"确认并执行"入口移除（dock 为唯一门禁出口），`SheetsView` 迁出 DraftActionsPanel 与保存状态行并移除相关 props/emits。
- e2e 全量适配 + 新增 2 项（Playwright 语义/既有 mock 冲突处最小修正并记录）：① 简报用例缺前置步骤，补"加入动作并生成有效预览"（跟随"普通预览丢弃乱序响应"前置）；② 确认模态与草稿栈浮窗均带 `role="dialog"`，`confirmModal/cancelModal` 改为 `[role="dialog"][aria-modal="true"]` 精确匹配（浮窗无 `aria-modal`）；③ `openDraftPop` 用 `.draft-chip` 类定位避免 `/草稿/` 名称正则会中"批量加入草稿"；④ 既有 10 处"确认并执行"改为 dock"确认写入"、2 处 `toHaveCount(0)` 改 `toBeDisabled`（写入门禁常驻仅状态变化）、草稿面板内容定位器（动作 N/M、`.draft-actions`、清空、保存失败/重试、过期/冲突卡）改走浮窗开合；新增「ActionDock：无草稿时写入禁用并可见原因，有草稿未预览引导先预览」与「Ctrl+S 只打开确认模态不直接执行」。Playwright e2e **47/47 通过**（45 既有适配 + 2 新增）、`npm run build`（check:api + vue-tsc + vite）零类型错误、`App.vue` 500 行（≤ Task 4 结束值 468 的规模约束）。
- 顺手加一行防御：`useConfirm.confirmAction` 打开新模态前把旧 `pending` 以 `false` resolve，避免旧 Promise 被模态遮罩隔离后永不 resolve（任务允许；本次 `write()` 复用确认入口后触发面扩大）。
- 评审修复（Task 5 fix round 1/5，Important + 裁决）：① `dock` computed 的 `taskRunning` 改为复用 `useJobMonitor` 导出的 `terminal`（终态集 SUCCEEDED/FAILED/ROLLED_BACK/BLOCKED_FILE_LOCK/NEEDS_REVIEW），替换原来仅覆盖 SUCCEEDED/FAILED 的内联数组——修复发布失败回滚到 `ROLLED_BACK`/`BLOCKED_FILE_LOCK` 时 dock 永久"任务进行中"锁死预览/写入的不对称；`NEEDS_REVIEW` 属终态释放矩阵，其禁用由 `dstValidation`/REPAIRED 分支接管（文案"需先修复"符合 §6.9"需人工检查，禁止直接重试"禁用语义）。② 按裁决 SPEC §6.9 优先于简报统一文案：`INVALID_UNRECOVERABLE` 禁用文案由"需先修复"改为"不可恢复"（对不可恢复 DST 提示"需先修复"有误导），其余 `INVALID_*` 保持"需先修复"。e2e 新增回归用例「任务回滚终态后 ActionDock 解锁不再锁定任务进行中」（SSE mock 下 QUEUED 锁定→`__emitJob` 发 `ROLLED_BACK` 终态→断言"任务进行中"消失且"预览变更"恢复可用，先红后绿）。Playwright e2e **48/48 通过**（47 既有适配 + 1 回归新增）、`npm run build` 零类型错误、`App.vue` 500 行不变。
- 评审修复（Task 5 fix round 2/5，重审裁决 Important）：NEEDS_REVIEW 释放路径缺失 §6.9 独立行禁用兜底——round 1"由 dstValidation/REPAIRED 分支兜底"经核实不成立（`dst_validation` 是加载时快照，所有任务消费点仅在 `SUCCEEDED` 时刷新工作区：useJobMonitor.ts:26/30、useCsvImport.ts:62、useRepair.ts:73），加载为 VALID 的工作区遇 NEEDS_REVIEW 后客户端 `dst_validation` 仍是 VALID → dock 会落入"有效可执行"（canWrite:true）放行直接重试。修复：`dock` computed 在 dstValidation 分支之前为 `job.value?.status==="NEEDS_REVIEW"` 增加独立分支（`canPreview:false, canWrite:false, writeDisabledReason:"需人工检查，禁止直接重试", writeNeedsModal:false`），不依赖 dst_validation 兜底，与 useJobMonitor.ts:31 `retryJob` 的 NEEDS_REVIEW 禁止重试及后端可重试集（database.py:462 不含 NEEDS_REVIEW）一致。e2e 新增回归用例「NEEDS_REVIEW 终态时 ActionDock 锁定并提示需人工检查禁止直接重试」（SSE mock：QUEUED 锁定→`__emitJob` 发 `NEEDS_REVIEW` 终态→断言内联文本"需人工检查，禁止直接重试"可见且"预览变更"/"确认写入"均禁用，先红后绿）。Playwright e2e **49/49 通过**（48 + 回归新增 1）、`npm run build` 零类型错误、`App.vue` 500 行不变。

## 2026-09-04（v0.3.3 标签化外壳 Task 4：重建为固定标签化应用外壳并迁移三视图）

- 落地固定标签化外壳骨架（[PLAN-DM-013](.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md) Task 4，对应 [SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §4.1/§4.2/§7.2）：新增 `web/src/composables/useShellTabs.ts`（`useShellTabs<T>(ids,initial)` 返回 `{active,select,onKeydown}`，roving tabindex 激活态 + `ArrowLeft/Right/Home/End` 键盘模型）、`web/src/layout/TopBar.vue`（品牌/副标题、项目路径等宽回显、DST 状态胶囊 `VALID` 绿/`REPAIRED` 黄/其余红、AutoCAD 版本下拉 emits `update:cadVersion`、关闭工作区按钮 `aria-label="关闭工作区"`、主题按钮内聚调用 `useTheme`）、`web/src/layout/TabBar.vue`（固定三标签 `① 图纸/② 属性/③ 修订历史`，`role="tablist" aria-label="功能分区"` + `role="tab"`/`aria-selected`/`aria-controls`/roving `tabindex`，末尾"＋ 预留扩展"占位以普通 `span` 渲染避免污染 `role="tab"` 计数）、`web/src/views/WelcomeView.vue`（"打开图纸集"卡片，无壳回退路径输入 + 壳态"选择 DST 文件"按钮 + 拖拽提示）。`App.vue` 模板按**归属映射表**重组：未打开态渲染 WelcomeView；已打开态渲染 TabBar + 激活面板（非激活面板 `v-if` 不渲染，满足 e2e 第三断言），`JobStatusPanel`/`PreviewPanel`/诊断 details/`RepairStatusPanel` 过渡期保留 App 直属（所有标签共享位置，Task 6 迁浮层）；图纸集名称输入 → 属性视图属性卡、计数 → 图纸视图标题行、CAD 版本 → TopBar、修订历史 → 标签③。
- 新增三个视图（受控组件，业务状态仍由 App.vue 持有经 props/emits 透传）：`web/src/views/SheetsView.vue`（标签① 图纸，含计数标题行、过渡期 `RepairStatusPanel` 顶部、诊断 details、sheet-browser 与 editor 全部表单/批量条/字段集）、`web/src/views/PropertiesView.vue`（标签② 属性，含图纸集名称属性卡 `.summary`、自定义属性 details、`PropertyPanel` 属性定义与 CSV 导入）、`web/src/views/RevisionsView.vue`（标签③ 修订历史，含 `RevisionHistoryPanel` 与空态"暂无修订历史"）。
- 修正 `useTheme` 为**模块级单例状态**（Task 4 职责）：`theme` ref 提到模块作用域，`useTheme()` 返回同一实例——TopBar 与 App.vue 各自调用不再产生第二份主题状态；导出签名（`{theme,toggleTheme}`）与持久化/watch 行为不变。
- e2e 全量适配：新增 3 项外壳用例（固定三标签默认图纸、方向键切换、关闭按钮位于顶栏确认后回未打开态），其中两处做 Playwright 语义最小修正并记录——① 关闭工作区在**无未发布改动时直接回未打开态不弹模态**、且确认模态按钮文本为既有契约"确定关闭并放弃当前改动"（非"关闭工作区"），故该用例先切属性标签制造改动再走勾选确认路径；② 标签栏末尾占位非 `role="tab"`（避免三标签 `toHaveCount(3)` 断言冲突）。既有 42 项用例按新交互适配：`修订历史` 入口由按钮改为标签③路径、涉及图纸集名称/更新图纸集/属性定义/CSV 的用例先切换到属性标签、涉及图纸浏览/编辑器/批量条的用例默认图纸标签不变、`AutoCAD 版本` 由 TopBar 提供无需切标签；恢复冲突用例的 `revisionCalls` 期望由 2 改为 3（首次切标签③ + 恢复成功后自动刷新 + 断言后切回标签③，沿用旧"按钮每次点击即加载"语义）。Playwright e2e **45/45 通过**（42 既有适配 + 3 新增）、`npm run build`（check:api + vue-tsc + vite）零类型错误、`App.vue` 468 行（≤ Task 3 结束值 498）。

## 2026-09-04（v0.3.3 标签化外壳 Task 3：App.vue 四个业务状态域拆分组合式函数）

- Task 3 步骤 1/4：拆分任务监控域为 useJobMonitor 组合式函数（新增 `web/src/composables/useJobMonitor.ts`，行为零变化）。`job`/`connectionMode` 状态、`jobMonitorGeneration` 代次、`activeJobEvents`/`pollTimer` 与 `invalidateJobMonitor`/`terminal`/`monitorMatches`/`watchJob`/`schedulePoll`/`pollJob`/`retryJob` 函数体原样迁入（对 `workspace`/`isWorkspaceLoading`/`error` 的引用改经 deps 注入；`watchJob`/`pollJob` 成功路径的 `await discardDraft();await refreshWorkspace(...)` 改经 `onJobSucceeded` 注入，App.vue 传入 `async workspaceId=>{await discardDraft();await refreshWorkspace(workspaceId)}`）。对外返回 `job`/`connectionMode`/`watchJob`/`retryJob`/`invalidateJobMonitor`/`terminal`/`monitorMatches` 契约供 Task 4-7 复用，并额外暴露 `isCurrentJobGeneration` 供 App.vue 的 `execute` 及后续 CSV/修复/恢复域做 `jobMonitorGeneration` 纯代次校验（与原比较行为等价）。`App.vue` 改为解构调用、删除对应状态与函数；确认文案、错误码分支、代次保护逐字保留。Playwright e2e **42/42 通过**、`npm run build`（check:api + vue-tsc + vite）零类型错误。
- Task 3 步骤 2/4：拆分自定义属性 CSV 导入域为 useCsvImport 组合式函数（新增 `web/src/composables/useCsvImport.ts`，行为零变化）。`csvText`/`csvPreview`/`csvPreviewContext` 状态、`csvGeneration` 代次与 `readCsvFile`/`previewCsv`/`importCsv`/`invalidateCsvPreview` 函数体原样迁入（`workspace`/`isWorkspaceLoading`/`error` 引用改经 deps 注入，`job.value=result` 改经 `setJob` 注入，`watchJob`/`invalidateJobMonitor`/`isCurrentJobGeneration`/`refreshWorkspace`/`confirmAction` 由 App.vue 传入）；导入确认文案与危险等级（confirmText「确认导入」逐字保留；`danger:false` 属最终分支审查前旧状，按 SPEC-DM-006 §6.2/§10.3 已更正为强确认，见本日"最终分支审查修复"）。`App.vue` 删除对应状态与函数并解构调用；Playwright e2e **42/42 通过**、`npm run build`（check:api + vue-tsc + vite）零类型错误。
- Task 3 步骤 3/4：拆分内存修复域为 useRepair 组合式函数（新增 `web/src/composables/useRepair.ts`，行为零变化）。`repairPreview`/`repairContext`/`isRepairPreviewing`/`isRepairExecuting` 状态、`repairGeneration` 代次、`dstValidation`/`repairWritesDisabled` 两计算属性与 `previewRepair`/`executeRepair` 函数体原样迁入（`workspace`/`isWorkspaceLoading`/`error` 与 `workspaceLoadGeneration` 改经 deps 注入，`job.value=result` 改经 `setJob`，`invalidateJobMonitor`/`isCurrentJobGeneration`/`refreshWorkspace`/`confirmAction` 由 App.vue 传入；`isRestoreExecuting` 按单一事实来源由 App.vue 创建后作为 deps 传入，本域函数体原不使用该门禁故未新增判断）；`dstValidation` 一并返回以支撑模板渲染。`App.vue` 删除对应状态/计算属性/函数并解构调用，`workspaceLoadGeneration` 由局部 `let` 改为跨域共享 ref（打开/关闭/刷新/修订均改 `.value`，行为等价）；修复确认文案与不可逆危险等级（`danger:true` + `requireCheckbox`）逐字保留。Playwright e2e **42/42 通过**、`npm run build`（check:api + vue-tsc + vite）零类型错误。
- Task 3 步骤 4/4：拆分修订恢复域为 useRestore 组合式函数（新增 `web/src/composables/useRestore.ts`，行为零变化）。`revisions`/`restorePreview`/`restorePreviewContext` 状态、`revisionGeneration`/`restoreExecutionGeneration` 代次与 `invalidateRevisionState`/`revisionRequestMatches`/`loadRevisions`/`loadRevisionsInternal`/`previewRestore`/`restoreExecutionMatches`/`restoreRevision` 函数体原样迁入（`workspace`/`isWorkspaceLoading`/`error` 与 `workspaceLoadGeneration` 改经 deps 注入，`job.value=result` 改经 `setJob`，`invalidateJobMonitor`/`refreshWorkspace`/`confirmAction` 由 App.vue 传入）；`isRestoreExecuting` 按注意段由 App.vue 创建单一 ref 后同时注入 useRepair 与 useRestore，useRestore 返回同一 ref 保持单一事实来源；恢复确认文案与不可逆危险等级（`danger:true` + `requireCheckbox`）逐字保留。`App.vue` 删除对应状态/函数并解构调用；Playwright e2e **42/42 通过**、`npm run build`（check:api + vue-tsc + vite）零类型错误。

## 2026-09-04（v0.3.3 标签化外壳 Task 2：发布/删除/恢复等确认改为应用内可访问模态）

- 把 `web/src/App.vue` 全部 8 处原生 `confirm()` 迁移为应用内可访问确认模态（[PLAN-DM-013](.planning/plans/dst-manager/PLAN-DM-013-v033-tabbed-shell.md) Task 2，对应 [SPEC-DM-006](docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.2、§6.9）：新增 `web/src/components/ui/ConfirmModal.vue`（`role="dialog"`/`aria-modal`/`aria-label`、焦点困绕、Tab/Escape 键盘模型、`watch(open)` 归还焦点到触发元素，全部样式引用 Task 1 设计令牌；遮罩 rgba 常量除外）与 `web/src/composables/useConfirm.ts`（`useConfirm()` 返回 `{ state, confirmAction(options): Promise<boolean>, resolve(value) }`，供 Task 5"确认写入"按钮复用）。8 处迁移均保留既有 `confirm()` 文案原文，不可逆破坏类（关闭工作区、删除整个子集、执行发布、恢复为新修订、执行修复）按统一门禁走 `danger:true + requireCheckbox:true + reversibility:"不可逆"` 并显式勾选"我已了解本次操作不可逆…"后确认按钮才可用；低风险动作（单张图纸删除、冲突后重新加载）为 `danger:false` 且不勾选；CSV 属性定义导入当时沿用 `danger:false`、confirmText「确认导入」——按 SPEC-DM-006 §6.2/§10.3 属弱确认旁路，已于最终分支审查更正为强确认（见本日"最终分支审查修复"）；`closeWorkspace`/`queueDelete`/`queueDeleteSubset` 改为 `async`，模板 `@click` 兼容 Promise。e2e 全量更新：23 处 `page.once("dialog",…)` 原生 dialog 处理器改为模态交互（`getByRole("dialog")` 内勾选 + 点确认/取消），并新增「发布确认模态必须显式勾选后才可提交」用例（Task 5 前暂以既有发布入口"确认并执行"触发同一模态，用例已注释 Task 5 将改触发方式）。Playwright e2e **41/41 通过**（40 既有 + 1 新增）、`npm run build`（check:api + vue-tsc + vite）零类型错误。
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
