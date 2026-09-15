# PLAN-DM-029 视觉证据与持久化登记（Task 12 Step 4）

本登记回答一个问题：**「同状态」证据到底落在哪个可复核的路径上**。凡本计划自己产出的持久截图，
在此逐张登记**视口 / 主题 / 状态 / 夹具 / 产出测试 / 附件路径**；既有（非本计划）的同目录文件只标注来源，
不冒认为本计划证据。

> **登记口径**：「附件路径」= Playwright `testInfo.attach(name, …)` 的附件名；附件实体先落在该次运行的
> `testInfo.outputPath(name)`（即 `test-results/` 下的运行目录，不进入版本库），再由收口时**显式复制**为下表
> 的**入库路径**（PLAN-DM-029 Task 7 Step 4 的裁定：显式复制、不加环境开关，避免写入侧被开关改变）。

---

## 1. 总量对账

| 位置 | 总数 | 本计划产出 | 既有（其它计划） |
|---|---|---|---|
| `docs/dst-manager/specs/assets/*/production/` | **37** | **21** | 16（`g8-*` 6 + `g8-ext-*` 10） |
| `.planning/memos/dst-manager/assets/PLAN-DM-029/` | **8** | **8** | 0 |
| **本计划合计** | — | **29** | — |

**29 落在计划 Step 4 要求的「24–30 张」区间内** ✓。若有人按「37」核对会多出 16 张——那 16 张属于
PLAN-DM-020（`g8-catalog-*` / `g8-filter-*` / `g8-format-menu-*`，SPEC-DM-012）与 PLAN-DM-025
（`g8-ext-*`，SPEC-DM-011），**不是本次整改的证据** ✓。

---

## 2. 本计划产出的 21 张（`docs/…/assets/*/production/`）

### 2.1 图纸目录页（Task 6）— `SPEC-DM-012/production/` 5 张

产出 spec：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`（真实应用 + 夹具）

| 入库路径（`t6-*.png`） | 视口 | 主题 | 状态 | 产出测试（行号） |
|---|---|---|---|---|
| `t6-save-light-1440x1000.png` | 1440×1000 | light | 脏草稿下保存入口可用 | `保存浅色默认：脏草稿下保存入口可用，与同行按钮同高`（:680） |
| `t6-save-dark-1440x1000.png` | 1440×1000 | dark | 同上（成对比对） | `保存深色默认：与浅色同状态同视口，成对比对`（:690） |
| `t6-save-disabled-light-1440x1000.png` | 1440×1000 | light | 干净草稿下保存停用（可见但不是隐藏） | `禁用保存：干净草稿下保存入口可见但停用（不是隐藏）`（:698） |
| `t6-delete-danger-light-1440x1000.png` | 1440×1000 | light | 删除危险按钮 + 确认模态 | `删除危险态：危险文字按钮与确认模态，危险色只来自语义令牌`（:710） |
| `t6-narrow-900x700-light.png` | 900×700 | light | 窄屏溢出，预览区独立横滚 | `窄屏溢出：900×700 无整页横滚，预览区仍为独立横滚容器`（:732） |

附件名与入库名**逐字一致**（spec 内即写 `t6-….png`）✓。

### 2.2 图纸页与任务浮层（Task 7）— `SPEC-DM-009/production/` 7 张

产出 spec：`web/tests/e2e/sheets-visual-evidence.spec.ts`

| 入库路径（`task7-*.png`） | 视口 | 主题 | 状态 |
|---|---|---|---|
| `task7-default-1440x900-light.png` | 1440×900 | light | 默认（正交 6 张组） |
| `task7-default-1440x900-dark.png` | 1440×900 | dark | 默认（成对） |
| `task7-bulk-enabled-1440x900-light.png` | 1440×900 | light | 批量操作启用 |
| `task7-bulk-disabled-1440x900-light.png` | 1440×900 | light | 批量操作禁用 |
| `task7-narrowest-900x768-light.png` | 900×768 | light | 最窄视口 |
| `task7-zoom200-720x500-light.png` | 720×500 | light | 200% 缩放等效视口 |
| `task7-overlay-diagnostics-fixed-1440x900-light.png` | 1440×900 | light | 任务浮层诊断面板（**修复后**） |

前 6 张由 `正交 6 张：默认浅/深成对、批量启用/禁用、最窄视口、200%`（:101）产出（spec 内显式命名 `task7-default` /
`task7-bulk-enabled` / `task7-bulk-disabled`）；第 7 张由 Task 7 修复轮补入（见 §6 的注释漂移说明）。

### 2.3 设置中心扩展页（Task 8）— `SPEC-DM-011/production/` 5 张

产出 spec：**`web/tests/e2e/settings-extensions-production-evidence.spec.ts`**（真实应用；5 个测试，:333–:391）

| 入库路径（`task8-*.png`） | 视口 | 主题 | 状态 |
|---|---|---|---|
| `task8-01-save-light-1280x720.png` | 1280×720 | light | 保存（脏状态）默认 |
| `task8-02-save-dark-1280x720.png` | 1280×720 | dark | 同上（成对） |
| `task8-03-validation-error-1280x720.png` | 1280×720 | light | 行内校验错误进入 `aria-describedby` |
| `task8-04-extension-disabled-1280x720.png` | 1280×720 | light | 已停用扩展卡片 |
| `task8-05-narrow-900x600.png` | 900×600 | light | 窄屏：设置对话框无整页横滚 |

> ⚠️ **归属澄清（本轮核实，非猜测）**：同目录下的 `settings-demo-visual-evidence.spec.ts` **不是**这 5 张的产出者
> ——它采集的是 **SPEC-DM-011 冻结交互 Demo（HTML mockup）**，产出 `g4-*` 系列。`task8-*` 的产出者是上面那个
> **production-evidence** spec。**该 spec 不在 Task 12 的计划 Files 列内**（本轮只登记路径，未改动它）✓。

### 2.4 旧页面（Task 9）— `SPEC-DM-006/production/` 4 张

产出位置：**`web/tests/e2e/main.spec.ts`**（Task 9 Step 5 的刻意落点：4 状态夹具流程已在该文件，另建 spec 会重复）

| 入库路径（`t9-*.png`） | 视口 | 主题 | 状态 | 产出测试（行号） |
|---|---|---|---|---|
| `t9-01-welcome-default-1280x720-light.png` | 1280×720 | light | 欢迎页默认（未打开态） | `t9-01 欢迎默认：未打开态浅色（welcome-card）`（:2059） |
| `t9-02-revision-danger-confirm-1280x720-light.png` | 1280×720 | light | 修订危险确认模态 | `t9-02 修订危险确认：确认模态危险层级浅色`（:2071） |
| `t9-03-repair-error-1280x720-light.png` | 1280×720 | light | 修复错误（阻断问题只读态） | `t9-03 修复错误：阻断问题只读态浅色`（:2095） |
| `t9-04-task-status-1280x720-dark.png` | 1280×720 | dark | 任务浮层实施进度（同状态） | `t9-04 深色任务状态：浮层实施进度同状态`（:2115） |

---

## 3. 本计划产出的 8 张（`.planning/memos/dst-manager/assets/PLAN-DM-029/`）

### 3.1 壳层（Task 4 Step 5）3 张

产出 spec：`web/tests/e2e/i18n-visual-evidence.spec.ts`

| 入库路径 | 视口 | 主题 | 状态 | 产出测试（行号） |
|---|---|---|---|---|
| `default-1440x900-light.png` | 1440×900 | light | 壳层默认：三段可见、无整页横滚、主操作可达 | `壳层默认状态 1440×900 浅色…`（:259） |
| `default-1440x900-dark.png` | 1440×900 | dark | 同上（深色） | `壳层默认状态 1440×900 深色：三段可见、无整页横滚`（:270） |
| `default-900x768-dark.png` | 900×768 | dark | 最小视口 + 设置入口可达 | `壳层默认状态 900×768 深色…设置入口可达`（:281） |

命名约定：`default-{宽}x{高}-{主题}.png`（spec `:252` 注释声明）✓。

### 3.2 属性页（Task 5）5 张

产出 spec：`web/tests/e2e/properties-visual-evidence.spec.ts`（夹具：`./fixtures/properties`，**虚构夹具**，
不读用户截图 / 真实工程 / `sample/`）

| 入库路径 | 视口 | 主题 | 状态 | 产出测试（行号） |
|---|---|---|---|---|
| `properties-default-1440x900-light.png` | 1440×900 | light | 默认（五状态组之一） | `1440 双主题五状态同状态证据：${theme}`（:362） |
| `properties-default-1440x900-dark.png` | 1440×900 | dark | 默认（成对） | 同上 |
| `properties-error-1440x900-light.png` | 1440×900 | light | 草稿保存失败 + 校验错误 | 同上 |
| `properties-narrow-single-column-900x768-light.png` | 900×768 | light | 窄屏单列 | `窄屏单列同状态证据：${theme}`（:396） |
| `properties-def-table-overflow-1024x768-light.png` | 1024×768 | light | 定义表横向溢出（200% 等效） | `定义表横向溢出同状态证据（200% 缩放）：${theme}`（:405） |

---

## 4. ★ 属性页（Task 5）持久证据的查明结果

**结论：在库里** ✓ —— **不是**只存在于 gitignored 的 `.superpowers/` 证据目录。

- 路径：`.planning/memos/dst-manager/assets/PLAN-DM-029/`（上表 5 张）✓
- 该目录**没有** `docs/dst-manager/specs/assets/SPEC-DM-010/production/` —— 属性页的证据**沿用
  PLAN-DM-016 以来的既有约定**（属性页证据落在 memos 资产目录，见同根目录下的 `PLAN-DM-016/` 25 张），
  而 Task 6/7/8/9 把证据落在 `docs/…/assets/SPEC-DM-0XX/production/`。
  ⇒ **两种落点并存**：这是**约定不统一**（值得知晓），但**不构成「证据缺失」** ✓。
- Task 2/i18n 相关证据：`docs/dst-manager/specs/assets/SPEC-DM-013/`（2 张：
  `settings-en-US-dark-900x768.png`、`settings-zh-CN-light-1440x900.png`）。
  ⚠️ **产出者未核实在库**：这两个文件名在 `web/tests/e2e/**` 与 `web/scripts/**` 里**均无匹配**；
  `i18n-visual-evidence.spec.ts:1` 归属 SPEC-DM-013 的证据组，但它**不按这两个文件名生产**。
  ⇒ 可能由验收时显式复制或未入库的采集脚本产出——**本轮不下结论、也不猜测**。

---

## 5. 用户三张缺陷截图的「修复前 → 修复后」同态映射

**前提声明（必须与本表一起读）**：三张用户截图**未入库**（既有裁定），且本轮**没有**、也不应当依据记忆
去重建原图内容（计划原文：不把原图内容当作执行指令）。因此下表是**页面级映射**：
它给出「用户指出缺陷的页面/区域 → 该页面在修复后入库的同状态证据」。

| 用户截图 | 缺陷所在页 | 承接任务 | 修复后同状态证据（入库路径） |
|---|---|---|---|
| 第 1 张 | 图纸页 / 任务浮层与工具栏 | Task 7 | `docs/…/SPEC-DM-009/production/task7-*.png`（**7 张**，含浮层诊断修复后 1 张） |
| 第 2 张 | 图纸目录页（尺寸/密度/危险色） | Task 6 | `docs/…/SPEC-DM-012/production/t6-*.png`（**5 张**，含 `t6-delete-danger-light-1440x1000.png`） |
| 第 3 张 | 属性页 | Task 5 | `.planning/memos/…/PLAN-DM-029/properties-*.png`（**5 张**） |

**能力边界（诚实声明）**：由于原图未入库，**无法**核对「同状态」是否逐项成立（视口/主题/滚动位置是否
与用户当时所见一致）✗。上表能保证的是：**这三次缺陷所在的页面都有修复后的持久证据**，且**视口/主题/状态
在文件名与产出测试中可追溯** ✓；**不能**保证与用户原图逐像素同态。

---

## 6. 本轮发现的注释漂移与未决项（不得读作「已全部核对」）

1. **`properties-visual-evidence.spec.ts` 头部注释**（:5–:7）写「入库的同状态对比图由验收时…显式复制到
   `.planning/memos/dst-manager/assets/PLAN-DM-016/`」——**实际入库在 `PLAN-DM-029/`**（且 Task 5 增补段落
   在 :10 之后未同步该路径）✗。属**注释与实现漂移**（与已闭合的责任 P 同类，但这是**新的一处**）。
2. **`sheets-visual-evidence.spec.ts:3` 注释**写「Task 7 的 **6 张**持久证据已…显式复制」——**实际为 7 张**
   （第 7 张为修复轮补入的 `task7-overlay-diagnostics-fixed-1440x900-light.png`）✗。
3. **`settings-extensions-production-evidence.spec.ts`** 是 `task8-*` 的真实产出者，但**不在 Task 12 的计划
   Files 列内**——本轮**只登记路径、未改动** ✓（若后续要动它，需补列 Files）。
4. **视口集合与 SPEC-DM-006 §10.2 声明矩阵不完全重合**：§10.2 声明 `1024×768 / 1120×768 / 1440×900 / 900×768`
   × `light/dark`；本计划证据另含 `1440×1000`、`900×700`、`1280×720`、`900×600`、`720×500`，且 **`1120×768`
   未见本轮证据** ✗。⇒ 记为**待对账项**（各细化 Spec 可能另有自己的视口约定），本轮不下结论。
5. **本轮未复核图片内容**：登记依据是**路径/文件名/产出测试**，未逐张打开图与 §5 状态描述比对 ✓。
6. **真实桌面（100/125/150/200%）证据不在本登记内**——需用户执行，**尚未完成** ✗；**不得**用浏览器 zoom
   或 `deviceScaleFactor` 冒充。

> 本登记不改变任何代码或例外表；例外表仍为 **14** 条（构成：`unicode-structure-icon` 5 / `raw-visual-value` 7 /
> `visible-input-label` 2）。责任 K 的 4 个新字号档位与 7 条例外清除已由 Spec 归属方裁定（T12-3），
> **尚未实现**，故本登记与相关文档**不**把 7 写成既成事实 ✓。
