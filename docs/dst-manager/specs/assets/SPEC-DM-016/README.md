# SPEC-DM-016 视觉证据与验收记录（PLAN-DM-035 Task 11；PLAN-DM-039 重建）

> 本文件是 SPEC-DM-016 的证据目录索引（证据清单、逐对裁决、G9 清单），随
> [SPEC-DM-016](../../SPEC-DM-016-drawing-standard-management-ui.md)（status: accepted）、
> [PLAN-DM-035](../../../../../.planning/plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md)
> （status: completed）与
> [PLAN-DM-039](../../../../../.planning/plans/dst-manager/PLAN-DM-039-standard-platform-ui-visual-closure.md)
> 一同维护；无独立文档 ID，不进入正式文档编号序列。

本目录保存图纸标准管理 UI 的冻结状态证据（G4）与生产证据（G8），以及逐对裁决、自动化验收
承接关系和真实桌面检查清单（G9）。证据由 `web/tests/e2e/standards-visual-evidence.spec.ts`
生成：同一状态集可分别写入本目录（G4 冻结件）与 `production/`（G8 生产证据）。

## 一、生成方式（可复现）

```powershell
Set-Location web
$env:DST_MANAGER_STANDARDS_EVIDENCE = "g4"          # 写 G4 冻结件到本目录
npm run test:e2e -- standards-visual-evidence.spec.ts
$env:DST_MANAGER_STANDARDS_EVIDENCE = "production"  # 写 G8 生产证据到 production/
npm run test:e2e -- standards-visual-evidence.spec.ts
Remove-Item Env:\DST_MANAGER_STANDARDS_EVIDENCE     # 常规回归不再改写仓库资产
```

未设置该环境变量时只产出测试附件，不改写本目录（避免常规回归覆盖验收资产）。三个目标目录
互斥：候选模式（`plan-dm-039`）**绝不覆盖** G4 与 `production`。

> **重建记录（PLAN-DM-039 Task 4，2026-09-23）**：欢迎页恢复“打开优先”约 2:1 双栏、标准草稿
> 编辑改为独立全宽工作台后，**全部 12 张 G4/G8 已重抓**，并删除被 SPEC-DM-017 六分区取代的
> 四个旧状态文件（`g4-03-properties`、`g4-04-mapping`、`g4-05-composition`、
> `g4-12-mapping-narrow`）。本目录文件名已全部对齐六分区语义。

抓图稳定性措施：固定时钟（`page.clock.setFixedTime("2026-09-22T10:00:00")`，使资产检查时间
戳可复现）、`animations: "disabled"`、等待 `document.fonts.ready`、抓图前 blur 掉活动焦点
（消除光标闪烁/焦点环造成的局部像素差）、鼠标归位到 (0,0)（消除悬停态）。全部状态使用
`web/tests/e2e/fixtures/standards.ts` 的虚构夹具，不含真实客户路径或工程内容。

## 二、G4 冻结状态集（1440×900 浅色为基准）

| 文件 | 状态 |
| --- | --- |
| `g4-01-welcome-light-1440x900.png` | 欢迎页：打开图纸集为唯一主动作，“其他任务”含“创建新图纸集 / 管理图纸标准 / 导入标准包”三个带说明的次级入口 |
| `g4-02-library-light-1440x900.png` | 标准库主从分栏（官方 2.1.0 / 用户 2.0.0 / 草稿 1 三条） |
| `g4-03-ordinary-light-1440x900.png` | 独立全宽编辑器·普通属性（八列表格；枚举值以“摘要即触发器”呈现） |
| `g4-04-derived-light-1440x900.png` | 派生属性（映射 + 组合两行的七列层级与编辑/删除动作） |
| `g4-05-dwg-naming-light-1440x900.png` | DWG 命名（字段浏览器 + 令牌编辑器 + 示例预览） |
| `g4-06-assets-light-1440x900.png` | 模板资产（检查通过：声明 A2/A3 与实际一致） |
| `g4-07-publish-error-light-1440x900.png` | 发布检查页·含错误（映射表未覆盖源值，发布禁用） |
| `g4-08-publish-success-light-1440x900.png` | 发布成功后的新版本只读详情 |
| `g4-09-welcome-dark-1440x900.png` | 补充：欢迎页深色 |
| `g4-10-library-dark-1440x900.png` | 补充：标准库深色 |
| `g4-11-publish-error-dark-1440x900.png` | 补充：发布错误页深色 |
| `g4-12-dwg-naming-narrow-light-900x768.png` | 补充：DWG 命名 900×768 窄视口（保留侧栏双列，无横向溢出） |

SPEC-DM-016 §12.2 要求「欢迎页、标准库、字段映射和发布页至少各有浅色标准视口、深色或窄视口
补充状态」：对应 `g4-09`（欢迎页深色）、`g4-10`（标准库深色）、`g4-12`（DWG 命名窄视口，承接原
字段映射窄视口状态）、`g4-11`（发布页深色）。

> **状态变更（PLAN-DM-038→PLAN-DM-039，2026-09-23 完成）**：属性定义、字段映射与字段组合三个旧状态
> 已由 [SPEC-DM-017](../../SPEC-DM-017-standard-properties-and-dwg-naming.md) 的六分区取代；
> 四个旧冻结件已删除，上表与 `production/` 均为新状态。

## 三、G8 逐对裁决

`production/` 中的 12 张与上表同名同状态，由同一次夹具数据、同主题、同视口、同时钟生成，
逐对比对工具与结果：

| 比对 | 结果 |
| --- | --- |
| 12 对（同名逐张，PLAN-DM-039 修复轮重抓后） | 12/12 **字节完全相同**（SHA-256 一致） |

**比对工具（可复现）**：`python compare-evidence.py`（在本目录执行，只依赖 Python 标准库，
内置最小 PNG 解码器）；也可传入两张图路径单独比对。判定口径：

1. 字节完全相同 → 通过；
2. 字节不同但**像素差 ≤ 20 个且单通道最大差 ≤ 1** → 字体栅格化伪影，通过（须在下方登记实例）；
3. 其他任何差异 → 不通过，必须定位到具体状态与元素并裁决。

**已登记的伪影实例（PLAN-DM-039 修复轮实测）**：`g4-02-library-light-1440x900.png` 在不同
轮次的生成中曾出现 19 个像素差、单通道最大差 1、包围盒 `(48,152)-(59,163)`（12×12，位于
左栏搜索标签文字处）；用本工具定位为子像素字体栅格化差异，不改变任何布局、文字或状态。
该实例是阈值口径的来源；同一轮内 G4 与 G8 仍要求字节一致。

比对方法：`sha256` 逐对比较；若出现差异，用 `compare-evidence.py` 输出差异像素数与包围盒，
定位差异区域后再裁决。首轮 G4 抓图曾出现同一位置的 19 像素差；定位为活动焦点/光标类渲染层
差异，按上文在抓图前 blur 活动焦点后差异消失。**结论：G8 与 G4 在数据、状态、主题、视口四个
维度无差异，无未关闭视觉差异。**

## 三之二、用户 Demo 对照裁决（PLAN-DM-039 Task 4 Step 3）

本目录 12 张 G4 冻结件在晋升前经过**用户对照两份 Demo 的三轮人工视觉裁决**（候选证据与逐轮
差异记录见 [PLAN-DM-039 资产登记](../../../../../.planning/memos/dst-manager/assets/PLAN-DM-039/README.md)）。

| 裁决轮次 | 用户意见 | 处置 |
| --- | --- | --- |
| 第一轮 | 「与设计有偏差」，要求以 Demo 为准，尤其普通/派生属性表「排列拥挤错位」 | 隐藏属性表单元格内与表头重复的字段标签；欢迎页补三个次级任务的说明文字与“最近打开记录为空”说明 |
| 第二轮 | 「普通属性页里的编辑枚举值按钮大小不固定」，并澄清「demo 中枚举值编辑按钮不是独立的，是通过点击展示枚举值的文本框来进入编辑」 | 枚举单元格合并为单一 `enum-trigger` 按钮（文本即枚举值摘要，点击进入编辑） |
| 第三轮 | **通过，同意晋升 G4/G8** | 生成 G4 与 G8，12 对 SHA-256 全部一致 |

对照基准：欢迎页 [SPEC-DM-016 Welcome Demo](../../../mockups/SPEC-DM-016-welcome-demo.html)、
标准编辑器 [SPEC-DM-017 Editor Demo](../../../mockups/SPEC-DM-017-standard-properties-and-dwg-naming-demo.html)。

## 三之三、真实 Windows WebView2 缩放检查（PLAN-DM-039 Task 4 Step 6）

浏览器 E2E 不替代真实桌面渲染，本项在真实 WebView2 壳下执行（用户执行并确认）：

- 入口：`uv run dst-manager desktop`（pywebview/WebView2，窗口标题「DST Manager」）；缩放用 Windows 系统显示缩放，主题用顶栏按钮。
- 覆盖：欢迎页、普通属性、DWG 命名、组合模态、发布检查 × 100%/125%/150%/200% × 浅色/深色。
- 结果：**全部通过**——无裁切、无页面级横向滚动（宽表只在自身容器内滚动）、模态底部操作栏持续可见且可点、Tab/Shift+Tab 可达主要动作且 Enter/Space 生效。
- 本项不需要 AutoCAD，与需真实 CAD 的 G9 清单（本目录 §五）无关：**G9 仍待执行**。

## 三之四、真实 AutoCAD 闭环验证（PLAN-DM-040 Task 10 Step 1）

在装有 AutoCAD 2016/2020 Core Console 与双版本插件的本机，用一次性脚本（以 `sample/` 真实 DWG 的
临时副本为来源，逐段打印并断言）完成以下闭环；下表为实际运行结果的逐段记录：

| 段 | 结果 |
| --- | --- |
| 来源 | `sample/project1` 真实 DWG 的临时副本（探测后布局为 `0000 封面`）；样本原件与来源副本的哈希/mtime 全程不变 |
| 受控复制 | 两次复制得到不同的 `assets/managed-<uuid4hex>.dwg`，副本哈希与来源一致，文档不含本机绝对路径 |
| 保存 | `save_standard_draft` 通过；文档只含包内相对路径 |
| CAD 布局检查 | 真实 Core Console 枚举布局 `['0000 封面']`，布局模板与基础模板诊断均为空 |
| 发布 | `loop.template@1.0.0` 发布成功，0 error / 0 warning |
| 导出 | `.dststandard` 条目 = `manifest.json` + 两个声明副本，包内副本哈希与来源一致 |
| 新库导入 | 导入后副本哈希不变，文档不含本机路径 |
| 标准驱动创建 | `GET /api/creation-drafts/standards` 返回 `available: true`，基础模板与布局模板选项均可用 |

本项证明「本机模板 → 受控副本 → 保存 → CAD 检查 → 发布 → 导出 → 导入 → 创建候选」在真实 CAD 下成立；
**不**替代真实桌面 G9（原生文件选择对话框、WebView2 缩放与键盘行为仍需人工执行）。

## 四、自动化验收承接（ST-UI-01～12）

| ID | 承接用例 |
| --- | --- |
| ST-UI-01 | `standards-welcome.spec.ts`（欢迎页主任务唯一性） |
| ST-UI-02 | `standards-welcome.spec.ts`（900×768 单列无横向滚动） |
| ST-UI-03 | `standards-library.spec.ts`（空库与筛选无结果区分、来源/状态筛选） |
| ST-UI-04 | `standards-library.spec.ts`（官方与用户发布版本只读） |
| ST-UI-05 | `standards-editor.spec.ts`（改回回 clean、保存失败、修订冲突保留输入） |
| ST-UI-06 | `standards-editor.spec.ts`（批量粘贴生成一条映射规则并定位重复/空值） |
| ST-UI-07 | `standards-editor.spec.ts` + `draftModel.test.ts`（组合片段与示例、非法格式码就地诊断） |
| ST-UI-08 | `standards-assets-publish.spec.ts`（`A3 ` 与 A3 的精确差异并阻断发布） |
| ST-UI-09 | `standards-assets-publish.spec.ts`（错误禁用发布、警告可发布、问题跳回并聚焦） |
| ST-UI-10 | `standards-assets-publish.spec.ts`（发布成功进入只读新版本详情） |
| ST-UI-11 | `standards-editor.spec.ts`（离开 dirty 草稿三选一门禁） |
| ST-UI-12 | `standards-library.spec.ts`（列表加载失败就地说明与重试）+ `standards-assets-publish.spec.ts`（检查失败可重试、未检查空态） |

单元测试面（`npm run test:unit`）：`standardLibraryModel`（只读边界与筛选空态）、
`draftModel`（映射行级诊断、组合预览、结构体检）、`publishModel`（发布门禁、布局严格比较、
资产引用与未覆盖警告）、`store`（代次保护、草稿加载与乱序丢弃）。

## 五、G9 真实桌面检查清单（pywebview/WebView2）

浏览器 E2E 不替代真实桌面验证，以下项目需在装有 AutoCAD 与双版本插件的 Windows 桌面执行，
逐项记录操作者、日期与结果；未执行前不得声明通过。

| # | 检查项 | 通过判据 |
| --- | --- | --- |
| G9-1 | 桌面壳文件选择 | 欢迎页「选择 DST 文件」打开原生对话框；返回路径后正常打开普通 DST |
| G9-2 | 标准包导入/导出 | 欢迎页与标准库进入同一导入弹窗；原生过滤器只显示 `*.dststandard`；选择中文/空格/OneDrive 路径后预检展示候选 `v<n>` 身份、同 ID 已有版本与可否导入；冲突与失败留在弹窗、保留路径可重选/重试；取消不预检；确认导入后定位到导入版本详情；导出下载完整 zip 且可再次导入 |
| G9-3 | 键盘可达性 | Tab/Shift+Tab 可达分区导航、映射行、发布检查问题与发布动作；Enter/Space 生效 |
| G9-4 | 最小窗口 | 最小窗口尺寸下主从分栏切换为分级视图，无横向滚动，关键动作可点 |
| G9-5 | 200% 系统缩放 | 检查域计数、问题清单与发布动作仍可见可点，无内容截断 |
| G9-6 | DWG 资产检查启动与返回 | 触发布局检查时 CAD 只读枚举布局，返回后仍停留在检查页并保留结果；DWG 不被修改 |
| G9-7 | 发布后只读状态 | 发布成功后停留在新版本只读详情，编辑入口消失，导出/派生/用于创建可用 |
| G9-8 | 只读打开不落盘 | 未发布状态下关闭窗口再打开，工作区未产生 `.dst-manager/`、DST/DWG 时间戳未变 |

### G9-2 追加步骤（PLAN-DM-041 Task 7/8：两步导入与原生选择）

除上表 G9-2 的判据外，本轮追加以下桌面步骤；每步记录操作者、日期与结果：

1. 欢迎页「导入标准包」与标准库「导入标准包」进入**同一**弹窗（不存在第二套导入表单）。
2. 点「选择标准包文件…」出现 Windows 原生对话框，过滤器固定为「标准包文件 (*.dststandard)」，
   看不到其他扩展名；取消对话框后弹窗内不出现任何预检结果。
3. 选一个含中文、空格与 OneDrive 路径的包（例如 `C:\Users\<用户>\OneDrive - <组织>\标准 包\x.dststandard`），
   路径只读回显原样；点「预检」展示候选身份 `v<n>`、同 ID 已有版本与诊断。
4. 选一个与库内同 ID 同版本的包：预检显示阻断诊断（`STANDARD_VERSION_EXISTS`）、确认按钮不可用，
   弹窗保持打开且路径保留；换文件后旧预检结果消失。
5. 选一个不同 ID 但同名（含全角、空白或大小写差异）的包：预检显示 `STANDARD_NAME_CONFLICT` 阻断。
6. 正常包「确认导入」后：列表按 ID 归集并展开该组、选中导入版本，详情显示 `v<n>`；重复点确认不产生第二份。
7. 键盘：打开弹窗焦点落在弹窗内，Tab/Shift+Tab 圈闭不逃出，Esc 关闭并把焦点归还给打开按钮；
   错误区经屏幕阅读器可读出（`role=alert`）。
8. 900×768 与 200% 系统缩放下弹窗与目标组定位均可达、无横向滚动。

## 六、未关闭差异与残余风险

1. **草稿资产文件本体写入（已关闭，PLAN-DM-040 Task 3）**：`POST /api/standards/drafts/{draft_id}/asset-files`
   把用户显式选择的本机 DWG/DWT 复制进草稿受控目录，只返回 `assets/managed-<uuid4hex>.dwg|.dwt`
   受控副本名；单文件 ≤ 64 MiB、扩展名只允许 `.dwg`/`.dwt`，先写随机临时文件再原子改名，失败不留半文件。
   保存与发布成功后只清理未被文档引用且带 `managed-` 前缀的副本。原残余项（只能编辑资产**声明**、
   文件不在草稿目录内时由 `STANDARD_ASSET_FILE_MISSING` 阻断）仍作为门禁保留，不再是能力缺口。
2. **版本说明字段**：SPEC-DM-016 §9.1 要求的版本说明以顶层 `release_notes` 随草稿文档保存并
   随标准包导出，不进入领域校验；若后续需要强类型或必填，须修订标准 Schema。
3. **`cad_job.py` 未修改**：Task 5 复用既有 CAD 读取协议，经探索确认 `cad_job.py` 无直接可复用
   函数，因此未改动（Task 5 遗留说明）。
