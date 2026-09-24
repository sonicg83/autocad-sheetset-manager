# 测试体系性能分析与套件审计（2026-09-24）

来源：针对「一次全量测试耗时过久」的实测分析，以及随之展开的测试套件静态审计。
所有耗时数据均为本机（Windows 11，10 逻辑核）实测；审计由两路静态排查完成（Python
侧与 Web 侧），未运行测试，结论按「确认 / 疑似 / 健康」三档给出证据。

## 一、测试体系结构与提速前基线

| 层 | 工具 | 规模 | 提速前 | 提速后 |
| --- | --- | --- | --- | --- |
| Python（unit/integration/platform/architecture） | pytest | 1962 例（unit 1588 / integration 291 / platform+architecture 约 83） | 3m16s（串行） | **39.4s**（`-n auto`） |
| 前端单元测试 | vitest | 303 例 / 28 文件 | 25.7s | 约 24s |
| 前端 E2E | Playwright | 654 例 / 36 spec | 4 workers（时长未精确记录） | **5.4m**（8 workers + 产物服务） |
| 真实 AutoCAD 系统测试 | pytest | `tests/system_autocad` | 默认跳过（`DST_MANAGER_RUN_AUTOCAD=1` 显式启用），不计入 | 同左 |

提速前各层瓶颈定位：

- **pytest**：dev 依赖无 pytest-xdist，全程单进程串行；最慢单用例仅 1.63s，前 30 名
  都在 0.6–1.6s 区间——无失控用例，是「平均 100ms × 1962」的数量堆积。集成测试
  setup 每例 0.6–0.96s（`test_created_project_opens.py`、`test_creation_api.py` 明显）。
- **vitest**：transform 占单次运行约 60–76% 且每次重算（无持久缓存）。
- **Playwright**：单一 vite dev server 的按需转译是吞吐上限——workers=10 时过载出现
  `net::ERR_ABORTED`，被迫压到 4（见提速前 `playwright.config.ts` 注释）。

## 二、已实施的提速改动（2026-09-24，均已验证）

1. **pytest 默认并行**：`pyproject.toml` `addopts` 由 `-q` 改为 `-q -n auto`
   （pytest-xdist 已入 dev 依赖与 `uv.lock`）。全量并行实测 1888 passed / 74 skipped /
   0 failed / 39.4s——印证 AGENTS.md「测试不依赖执行顺序」约定真实成立。串行调试用
   `-p no:xdist`；个别独占资源用例可加 `xdist_group`。
2. **e2e 产物化 + workers 4→8**：`web/playwright.config.ts` 的 webServer 由「单一
   vite dev server」改为「`vite build` + `vite preview`」。preview 继承
   `vite.config.ts` 的 `server.proxy`（`/api` → `DST_MANAGER_API_TARGET`），真实后端
   契约红线不变；preview 默认端口即 4173，加 `--strictPort` 防漂移。
3. **vitest `fsModuleCache: true`**：transform 持久化到 `node_modules/.vite/vitest/`。
   实测收益有限（约 1–2s，transform 占比 76%→68%）——套件仅 28 文件，规模不足以体现
   持久缓存优势；保留主要利于 watch 模式重跑。
4. **e2e 暴露的一处 dev 耦合修复**：`settings-dialog.spec.ts` 品牌标志用例原断言
   logo `src` 文件名，生产构建下必然失败（资源 URL 加内容哈希；64px logo 小于 4KB
   被 Vite 内联成 base64 data URI）。改为断言 `toHaveJSProperty("naturalWidth", 64/512)`，
   dev 与构建都成立且更贴合「小图标 vs 大图标」用例意图。

验证记录：`settings-dialog.spec.ts` 33/33（dev server 对照组亦 33/33）；e2e 全量
653 passed / 2 flaky / 1 failed（5.4m）——失败项 `properties-layout.spec.ts:152` 为
满负载下视口/缩放视觉用例抖动，单文件重跑 45/45 通过；对照 PLAN-DM-036 Task 9 记录的
dev server 基线（2 failed / 1–2 flaky 同类抖动），8 workers 不劣于原 4 workers 基线。
`npm run build` 通过（chunk 大小警告为既有问题）。

## 三、套件审计：数量是否过大

结论：**数量不算过大，问题在组织**。提速后全量约 6 分钟，运行成本已不是问题。审计
发现的「过时」几乎都不是测错东西或测已删功能，而是三类组织问题：版本锁死命名、巨型
文件堆积、验收证据与回归断言混写。

### 3.1 确认过时/冗余（有证据）

**Python 侧**

- `tests/unit/test_core.py`：4338 行、136 用例的巨型聚合文件，混合至少 15 种关注点
  （控制台编码、黄金样本回环、CAD 执行、发布恢复、租约隔离等）。最明确的组织过时项。
- `tests/unit/test_v021_editing.py`（583 行 / 27 例）与
  `tests/unit/test_v021_domain_dom_hardening.py`（676 行 / 23 例）：文件名锁死 v0.2.1
  （当前 0.3.5）。但 `format_sheet_title`、`parse_property_csv`、
  `normalize_property_name`、`derive_group_titles`、transdigit 等行为**只在这两个文件
  有覆盖**，是独立回归网而非重复遗留物——处置是拆分重命名，**绝不能直接删**。
- ACSM contract 三件套部分重复：`tests/unit/test_acsm_contract.py`（12 例，测 re-export
  路径）与 `tests/platform/test_platform_acsm_contract.py`（10 例，测
  `dst_platform.acsm.contract` 本体）平行跑了两遍黄金样本与错误报告用例；可用一条
  「re-export 同一性」测试替代 unit 侧大部分重复。`tests/platform/test_acsm_codec.py`
  与两者不重复，分层清晰。

**e2e 侧**

- `web/tests/e2e/fixtures/sheetCatalog.ts` 的 `demoErrorTemplate` 是真死代码（全仓库
  唯一引用是定义本身）。
- `settings-demo-visual-evidence.spec.ts` 后 6 例行为钉子（SC-16/SC-17 基线）钉的是
  冻结的 Demo HTML（不会再变），等价行为已由 `extensions-settings.spec.ts` 更完整
  覆盖（其 237/814/844/890/916/926 行），回归价值趋零。
- `main.spec.ts`：96 例 / 2247 行大杂烩（CAD 分流、草稿撤销、CSV、工作区竞争、任务
  浮层、英文界面系列等横跨至少 8 个已有专属 spec 的领域）。尾部 2154 行起 4 例
  「旧页面持久证据」纯截图存档；1224/1386 行语言切换不变量与 `i18n-workflows.spec.ts`
  重复；1022 行 `waitForTimeout(6000)` 为全套件最脆的一处。**但它含独有的竞争/时序
  用例（工作区切换丢弃迟到响应、SSE 迟到终态、恢复预览门禁），只能拆分归位，不能
  整体判废**。
- `properties-visual-evidence.spec.ts` 的密度/同行对齐/窄屏/200% 缩放断言与
  `properties-layout.spec.ts` 是同一断言的两份实现；evidence 文件真正独有的只有令牌
  色解析比对与截图附件。
- `settings-extensions-production-evidence.spec.ts` 的 task8-01~05 几何用例与
  `settings-dialog.spec.ts`（615/579/686 行）及 `extensions-settings.spec.ts:408`
  明显重复；g8-ext-01~10 纯截图存档有保留价值。
- 辅助函数 `expectNoPageHScroll` 在 `i18n-visual-evidence.spec.ts` 与
  `sheet-catalog-visual-evidence.spec.ts` 各复制一份（代码重复）。

### 3.2 疑似但需人工判断

- `test_v021_domain_dom_hardening.py` 与 `test_core.py:274` 的
  `test_v021_naming_policy_derives_range_and_sheet_titles` 是同一命名派生行为的纯函数
  层 vs service 集成层，拆分时部分断言可合并。
- `sheet-catalog-visual-evidence.spec.ts`（28 例）几何/密度类用例与
  `sheet-catalog.spec.ts`（70 例）同一契约两份实现，且 evidence 文件带
  `DST_MANAGER_WRITE_G8_EVIDENCE` 写库开关、定位混乱；需决定 G4 证据归档是否完成后
  裁撤几何断言。
- `sheets-visual-evidence.spec.ts`（5 例）与 `sheets-visual-regressions.spec.ts` /
  `sheets-layout.spec.ts` 在「双主题截图 + 无横滚断言」上职责交叉。
- `standards-visual-evidence.spec.ts`（2 例展开 12 态）纯 G4/G8 截图存档；去留取决于
  SPEC-DM-016 验收资产是否已定稿入库（流程问题）。
- `main.spec.ts` 的「英文界面」系列（约 12 例）与 `i18n-workflows.spec.ts` 关键矩阵
  部分重叠；CSV 三例与 `properties-csv.spec.ts` 职责边界模糊。
- 生产侧反向发现：`web/src/features/standards/draftModel.ts` 的 `enumItemByValue`
  导出全仓库无调用者（生产与测试都没有），可删。
- `tests/demo/*.test.cjs`（6 个 Node demo 测试）：被已取消的 PLAN-INT-003 判定
  「删除两项休眠 Demo 测试」，未指明哪两项；低价值候选。

### 3.3 明确健康（不用动）

- 74 个跳过全部来自 `system_autocad` 显式 opt-in 设计与平台条件跳过，无僵尸 skip。
- 约 30 处含 "legacy" 字样的用例均为「拒绝旧格式/旧字段必须有明确错误」的前向兼容
  回归，是有效证据。
- `dst_builder` 在 tests/ 引用为 0，Builder 退场（PLAN-INT-004）清理彻底。
- vitest 28 文件逐一核对：被测导出全部有生产调用方；`appCompositionTestSupport` 是
  设计内的测试辅助模块。
- 未见「测已删除 UI」的 spec；`main.spec.ts:517`「旧编辑入口已移除」是防复活负向
  钉子，属合理回归。
- `tests/unit/test_database.py`（783 行 / 31 例）、`tests/unit/creation_xlsx_fixtures.py`
  （共享夹具，非测试）、`test_about_version.py`（monkeypatch 假值，不锁版本号）、
  `tests/architecture/test_product_boundaries.py` 均健康。
- e2e 的 `standards-library/editor/assets-publish`（9+25+7 例）、
  `i18n-visual-evidence.spec.ts`（实为响应式/键盘/可访问性回归，不做像素比对）、
  `create-sheetset-*`（25 例，最新）、`settings-dialog` / `extensions-settings` 均
  职责清晰。

## 四、处置建议（按风险与依赖排序）

1. **立即可做（低风险）**：删 `demoErrorTemplate`；裁掉 `settings-demo-visual-evidence`
   的 demo 钉子 6 例与 `properties-visual-evidence` 的重复密度断言。约省 15–20 例，
   主要收益是可读性而非时长。
2. **需要规划的中型重构**：拆分 `test_core.py`（已取消的
   `PLAN-INT-003-test-system-consolidation.md` 有现成的 17 文件聚焦清单与处置原则——
   「只有完全重复、已有更高层替代证据的内容可删；不得借去冗余删除尚无替代证据的
   断言」——可参考复活）；`test_v021_*` 重命名去版本锁；ACSM unit 侧改 re-export
   同一性测试。
3. **需要流程决策**：7 个 `*-visual-evidence` spec 是否已归档完毕（G4/G8 验收资产
   定稿入库）——若已完成，把行为/几何断言从证据文件剥离，只留环境开关控制的截图
   存档，e2e 可瘦身约 40–50 例。
4. **可选**：`main.spec.ts` 按域拆分归位；`waitForTimeout(6000)` 改为状态等待。

## 附：本次提速相关提交前状态备注

- 本备忘记录的配置改动（`pyproject.toml`、`web/playwright.config.ts`、
  `web/vitest.config.ts`、`web/tests/e2e/settings-dialog.spec.ts`）与 PLAN-DM-036
  Task 9 的未提交工作混在同一工作区，提交时需分开暂存。
- 相关 changelog 条目：2026-09-24「pytest 默认并行执行」「web 测试提速」两节。
