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
| 12 对（同名逐张，PLAN-DM-039 重建后） | 12/12 **像素完全一致**（SHA-256 相同，0 处差异） |

比对方法：`sha256` 逐对比较；若出现差异，用本目录留档的裁剪工具（解码 PNG 并输出差异包围盒）
定位差异区域后再裁决。首轮 G4 抓图曾出现 `g4-02-library` 的 19 像素差（12×12 包围盒，位于左栏
搜索标签文字处）；定位为活动焦点/光标类渲染层差异，按上文在抓图前 blur 活动焦点后差异消失。
**结论：G8 与 G4 在数据、状态、主题、视口四个维度无差异，无未关闭视觉差异。**

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
| ST-UI-12 | `standards-library.spec.ts`（列表加载失败就地说明）+ `standards-assets-publish.spec.ts`（检查失败可重试） |

单元测试面（`npm run test:unit`）：`standardLibraryModel`（只读边界与筛选空态）、
`draftModel`（映射行级诊断、组合预览、结构体检）、`publishModel`（发布门禁、布局严格比较、
资产引用与未覆盖警告）、`store`（代次保护、草稿加载与乱序丢弃）。

## 五、G9 真实桌面检查清单（pywebview/WebView2）

浏览器 E2E 不替代真实桌面验证，以下项目需在装有 AutoCAD 与双版本插件的 Windows 桌面执行，
逐项记录操作者、日期与结果；未执行前不得声明通过。

| # | 检查项 | 通过判据 |
| --- | --- | --- |
| G9-1 | 桌面壳文件选择 | 欢迎页「选择 DST 文件」打开原生对话框；返回路径后正常打开普通 DST |
| G9-2 | 标准包导入/导出 | 导入 `.dststandard` 后定位到导入版本详情；导出下载完整 zip 且可再次导入 |
| G9-3 | 键盘可达性 | Tab/Shift+Tab 可达分区导航、映射行、发布检查问题与发布动作；Enter/Space 生效 |
| G9-4 | 最小窗口 | 最小窗口尺寸下主从分栏切换为分级视图，无横向滚动，关键动作可点 |
| G9-5 | 200% 系统缩放 | 检查域计数、问题清单与发布动作仍可见可点，无内容截断 |
| G9-6 | DWG 资产检查启动与返回 | 触发布局检查时 CAD 只读枚举布局，返回后仍停留在检查页并保留结果；DWG 不被修改 |
| G9-7 | 发布后只读状态 | 发布成功后停留在新版本只读详情，编辑入口消失，导出/派生/用于创建可用 |
| G9-8 | 只读打开不落盘 | 未发布状态下关闭窗口再打开，工作区未产生 `.dst-manager/`、DST/DWG 时间戳未变 |

## 六、未关闭差异与残余风险

1. **草稿资产文件本体不可写入**：后端没有把资产文件写入草稿受控目录的端点（PLAN-DM-035
   Task 3/5/6 范围），因此编辑器只能编辑资产**声明**；声明了但文件不在草稿目录内的资产由
   `STANDARD_ASSET_FILE_MISSING` 阻断发布。补齐需要新端点（路径、扩展名、大小与事务安全校验）
   与后续计划，当前不伪造「已替换文件」。
2. **版本说明字段**：SPEC-DM-016 §9.1 要求的版本说明以顶层 `release_notes` 随草稿文档保存并
   随标准包导出，不进入领域校验；若后续需要强类型或必填，须修订标准 Schema。
3. **`cad_job.py` 未修改**：Task 5 复用既有 CAD 读取协议，经探索确认 `cad_job.py` 无直接可复用
   函数，因此未改动（Task 5 遗留说明）。
