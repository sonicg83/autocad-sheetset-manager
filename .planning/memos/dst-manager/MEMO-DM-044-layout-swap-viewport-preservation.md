---
id: MEMO-DM-044
title: 布局替换后视口保持的可行性调研与方案比选
status: accepted
document_kind: memo
owners:
  - dst-manager
created: 2026-10-01
updated: 2026-10-01
related:
  - ARCH-DM-001
  - PLAN-DM-042
  - SPEC-DM-016
  - SPEC-DM-018
  - RES-SH-002
---

# 布局替换后视口保持的可行性调研与方案比选

本备忘记录一次**只做调研、未改任何产品代码**的可行性分析过程与结论，供后续立项
（Spec / Plan）直接引用。调研问题与约束由用户提出，全部结论都标注了**可核验来源**
（源码行号、本地真实样本、官方文档或社区来源），未经真机验证的推断已显式标注。

配套可视化：[方案比选图（HTML）](assets/MEMO-DM-044/scheme-comparison.html)。

> 定位说明：本文按用户要求先落在备忘。若后续要做成长期可复用知识，应在
> `docs/dst-manager/research/` 另立 `RES-DM-00X`，正文只保留一份权威位置，本备忘改为链接。

## 一、问题

工程希望"同一套图纸按工程阶段套用不同图框出图"（方案 / 初步设计 / 施工图）。标准→图纸集驱动的
框架已经能驱动这套流程，但**替换布局（图幅）后，设计人员在布局里设置好的模型视口一并消失**。
用户提出的目标是：能否把设计人员最初设置的视口保存为**可复用数据**，在替换后恢复。

用户在讨论中追加了一条决定性约束（见第三节）：图框与字段必须以**布局为求值上下文**，因此
"把图框换成外部参照"的路线不成立。

## 二、根因定位（代码事实）

现状的替换方式是"**删掉全部布局 → 从模板 DWG 重新导入布局**"：

| 位置 | 事实 |
| --- | --- |
| `src/dst_manager/infrastructure/autocad/worker.py` L185–201 | `ScriptRenderer.render_rebuild()`：先 `DstDeleteLayouts`，再对每张图幅执行 `_.-LAYOUT _Template <模板DWG> <图幅>` 后改名 |
| `src/dst_manager/infrastructure/autocad/worker.py` L216–272 | `ScriptRenderer.render_create_layouts()`：创建期同一套步骤 |
| `plugins/src/DstManager.AutoCAD/Commands.cs` L17 | `DstDeleteLayouts` 删除除 `Model` 外的**全部**布局 |
| `src/dst_manager/application/cad_job.py` L715 / L746 | `_rebuild_group()` 调用 `render_rebuild` |
| `src/dst_manager/application/creation_job.py` L434 | 创建期构造 `LayoutCreationRequest` |

**结论**：浮动视口（`AcDbViewport`）是布局的图纸空间 BlockTableRecord 内的实体。布局被删除，
视口连同它的视图参数、比例、非矩形剪裁、锁定、**视口级图层覆盖（VP 冻结 / VP 颜色等）**一起消失。
这是当前实现方式的**必然结果**，不是"忘记保存"。

## 三、决定性硬约束：图纸集字段只在布局中求值

| 事实 | 来源 |
| --- | --- |
| 图纸集字段放在布局里正常、放在模型空间失效 | [Autodesk 论坛：Sheet Set Number will not update in View callout block in model](https://forums.autodesk.com/t5/autocad-lt-forum/sheet-set-number-will-not-update-in-view-callout-block-in-model/td-p/10330053)、[Reddit 同题](https://www.reddit.com/r/AutoCAD/comments/ni08ga/is_there_a_workaround_for_using_automated_sheet)（原话："that field only works when the block is in paper space"） |
| xref 图框拿不到图纸集字段，官方给的替代是"图框可外部参照，但**标题栏数据要以文字存在每一张图纸里**" | [Autodesk Blog：Automate Title Block Data](https://www.autodesk.com/blogs/autocad/automate-title-block-data-autocad) |
| 工程界同题结论即"xref 标题栏就放弃图纸集字段" | [Reddit /r/civil3d](https://www.reddit.com/r/civil3d/comments/1jy8o0h/do_you_have_your_title_block_in_the_sheet_layout) |

**推论（比"xref 不行"更强）**：字段必须活在该布局的求值上下文里，因此

> **图框 + 字段 + 视口，三者必须同处宿主 DWG 的同一个布局内。**

这解释了现状实现为何是"删布局 + 从模板导入布局"：**布局不只是视口的宿主，它同时是"标准
（图框 + 字段 + 页面设置）"的载体**。方案设计要做的，是把这两个身份**解耦**。

仍然成立的分支：**图框做成"含字段属性的块参照"插在布局里，字段可正常求值**（这是图纸集标题栏
的主流做法）。被否决的是 **xref 分支**，不是"块"分支。用户已确认：**标准包布局模板资产中的字段
就是放在图签块（增强属性块）里的** —— 这直接使方案 3 成立。

## 四、方案空间与比选

阶段差异所在层级决定要不要动布局：

```
阶段之间差异是什么？
├─ A. 只是图纸集属性值不同（图号/图名/项目名）
│     → 不动布局。改 DST 属性，字段自动求值。（已有能力：属性分区编辑 + 发布）
├─ B. 图签样式/图签栏/规范号不同，图幅与图号不变
│     → B1 图签资产规范化为含字段属性的块 → 只换块定义 + ATTSYNC（视口零风险）★方案 3
│     → B2 布局整体替换 + 视口快照恢复
└─ C. 图幅也变（A1→A2），或图号/图名随阶段变（本质是另一套图纸）
      → 必须动布局。C1 替换 + 快照恢复（需按新内框重映射）；C2 多布局/多阶段并存
```

> 注意：**一个布局只能挂到图纸集里的一张 Sheet，而一张 Sheet 只有一个图号。** 若图号随阶段变，
> "同一张图纸换皮"在数据模型上就不成立，必然是**多布局（或多 DWG）并存**。

### 4.1 比选表

| 排序 | 方案 | 做法 | 视口保住度 | 代价 | 成立条件 |
| --- | --- | --- | --- | --- | --- |
| **1** | **命名视图 + 图层快照**（legacy 机制现代化） | 替换前把每个视口的视图状态存为命名视图（`ViewTableRecord`）并把图层状态写入 `ViewTableRecord.LayerState`；替换后按命名视图重建视口 | 视图/几何/比例/锁定 **100%**；VP 覆盖走图层状态还原 | 中高：插件新增捕获/恢复固定命令 + 7 项改造 | 无额外前提，**覆盖全部阶段组合**，唯一无条件兜底 |
| **2** | **图签块重定义**（即方案 3） | 不删布局；用标准资产的同名块定义替换目标 DWG 的定义 + `ATTSYNC` | **100%**（块参照不动，视口不动） | 低代码 + 资产治理成本 | 图签必须是块参照且各阶段**同名**；需标准约定"角色→块名" |
| 3 | 视口实体克隆 | 把旧布局视口实体克隆进新布局 | 视图/几何/比例保留，**VP 覆盖必丢** | 低 | 仅当确认无人使用 VP 覆盖时可作为方案 1 的简化实现 |
| 4 | 一布局多套图框 + 图层/可见性切换 | 各阶段图框放不同图层或同一动态块不同可见性 | **100%**（纯显示操作） | 低 | **仅当阶段间图号与字段值相同**；图号一变此路断 |
| — | **（已否决）** 图框改为外部参照 | 换阶段 = 换 xref 路径 | 100% | 低 | **不成立**：xref 拿不到图纸集字段（第三节） |
| — | **（已否决）** 模型 XREF + 各阶段图框图纸 | 主 DWG 只放模型，各阶段图框 DWG 自带图框与视口 | 100% | 很高 | 与"一 DWG 一布局 + DST 引用布局 Handle"的既有结构不兼容，等于重做产品模型；且原生 Place View 自带 xref 行为（第八节） |

### 4.2 关键判定：为什么"克隆视口"不等于"保住视口"

官方明确：**视口的图层覆盖（VP 冻结 / VP 颜色 / VP 线型…）无法随视口复制，即使在同一张图纸内
复制也不行**，替代办法是图层状态。

来源：[Autodesk 支持文章：Viewport overrides are not maintained if viewport is copied to another layout](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Viewport-overrides-are-not-maintained-if-viewport-is-copied-to-another-layout.html)（原文："Every layout viewport can have its own set of layer overrides but they cannot be copied, even in the same layout. Solution: Use layer states…"）

因为这条限制，方案 1 才必须配图层状态兜底；方案 3 才显得特别干净（块参照根本不动，覆盖问题不存在）。

### 4.3 方案 1 的机制依据（第三方来源）

| 事实 | 来源 |
| --- | --- |
| 视口视图状态可完整序列化/回填：`ViewCenter / ViewHeight / ViewTarget / ViewDirection / LensLength / TwistAngle / 前后剪裁 / VisualStyleId / UCS随视口` | [Autodesk 开发者博客：Get Viewport Bounds（`SetViewportProperties(AcDbViewport* → AcDbViewTableRecord&)`）](https://blog.autodesk.io/how-to-get-viewport-bounds-in-autocad-model-space) |
| 程序化新建图纸空间视口：`new Viewport()` + 追加到该布局的 BTR；改视图前必须 `On = false`，激活用 `acedSetCurrentVPort` | [Create Paper Space Viewports (.NET)](https://help.autodesk.com/cloudhelp/2026/ENU/OARX-DevGuide-Managed/files/GUID-61C22902-F63B-4204-86EC-FA37312D1B6E.htm) |
| 图层状态可**按视口**还原为视口覆盖：`(layerstate-restore 名称 视口ename 4)`，flag 4 = 还原为视口覆盖（要求给定视口） | [AutoLISP layerstate-restore](https://documentation.help/AutoLISP-Functions/WS1a9193826455f5ffd9a7a610ecb0483d5-67b6.htm) |
| .NET 侧社区反馈 `LayerStateManager.RestoreLayerState` **不还原** VP Freeze / VP Color / VP Linetype（页面抓取被拒，仅标题与摘要，**须实测**） | [Autodesk 论坛帖](https://forums.autodesk.com/t5/net-forum/layerstate-api-restorelayerstate-not-working-on-layouts/td-p/9457129) |
| 基于既有布局建新布局的 API：`AcApLayoutManager::cloneLayout`、`AcDbLayout::copyFrom`（含 `AcDbPlotSettings::copyFrom`） | [Autodesk 开发者博客：Creating new Layout based on another Layout using ObjectARX](https://blog.autodesk.io/creating-new-layout-based-on-another-layout-using-objectarx) |
| `-LAYOUT _Template` 是**整体导入布局**（含图纸空间对象与页面设置），含视口对象 | [LAYOUT 命令](https://help.autodesk.com/cloudhelp/2027/ENU/AutoCAD-Core/files/GUID-BCE3AD90-9DE0-488C-9CA4-5FDB9401DCE0.htm)、[Reuse Layouts and Layout Settings](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-LT-MAC/files/GUID-A6D40A6B-D65C-4368-9650-476CAD3DA0C3.htm) |

## 五、legacy 资产提取：`SetViews` / `SetViewPort`

用户在讨论中指出仓库 `legacy/plugin/` 下有两个历史插件（本地私有目录，不进入公开仓库）。
读完源码后确认：**它们就是"把视口保存为可复用数据并恢复"的完整实现**，而且用到的机制全部是
AutoCAD 原生结构。

### 5.1 `legacy/plugin/setviews/SetViews/myCommands.cs`（捕获侧）

1. 提示用户在**模型空间**用封闭矩形多段线框出"视图框"（`PromptEntityOptions` 只收 `Polyline`）
2. 取 4 角点算中心 `CT`、宽 `W`、高 `H`
3. 用当前 UCS 的 `Ucsxdir / Ucsydir` 算 `TwistAngle`，`CT` 做旋转得 DCS 中心
4. 在 **`ViewTable` 符号表**创建 `ViewTableRecord`：
   `Name` = 图纸编号、`CenterPoint`、`Height` / `Width`、`ViewTwist`、`SetUcs(db.Ucsorg, db.Ucsxdir, db.Ucsydir)`
5. **同时** `LayerStateManager.SaveLayerState("ACAD_VIEWS_<编号>", LayerStateMasks.None, new ObjectId())`，
   并把快照名写入 **`NewVr.LayerState`**（AutoCAD 原生字段：命名视图自带图层状态关联）
6. 续号持久化：`NamedObjectsDictionary` 里一个 `DataTable`（`GCLViewCount` / `LastNumber`）

### 5.2 `legacy/plugin/setviewport/SetViewPort/myCommands.cs`（恢复侧）

1. 从 DST 读该 Sheet 的自定义属性 **`图幅`**，经 `config.ini [Size]` 映射成图幅长度
2. 遍历布局，用**布局名首段数字**（`^0*\d{1,}` 去前导零）匹配同名命名视图
3. `Scale = 图幅长度 / 视图宽`，`GetViewport()` 回填：

```
CenterPoint（纸空间，基准点 + 宽高/2 × Scale）   Width / Height = 视图宽高 × Scale
ViewCenter = VR.CenterPoint                     ViewHeight = VR.Height
ViewTarget = VR.Target                          ViewDirection / TwistAngle = VR.ViewTwist
VP.Layer = "TK-视口"   VP.On = true   VP.Locked = true
layerState.RestoreLayerState(VR.LayerState, VP.Id, 1, LayerStateMasks.None)   ← 带 viewportId 的重载
```

4. 用 `TK-视口` 图层上的多段线做非矩形裁剪（`NonRectClipEntityId` + `NonRectClipOn`）
5. 把算出的比例写回 DST 的 `出图比例` 自定义属性（供字段显示）；比例公式类 `Scale` 内含
   **建筑口径 `1:1/x`** 与 **市政口径 `1:1000/x`** 两套

### 5.3 为什么这条机制能成立（三个关键点）

| 机制 | 效果 |
| --- | --- |
| `ViewTable` 是**数据库级符号表** | 布局被 `DstDeleteLayouts` 删除，命名视图照样存活 |
| `LayerStateManager` 的图层状态也是**数据库级**，且 `ViewTableRecord.LayerState` 是原生耦合字段 | 用官方推荐的替代路径解决"VP 覆盖不可复制"，并用原生关联免去自建映射 |
| 比例是**算出来的**（图幅长度 ÷ 视图宽），不是抄视口的 | **换图幅（A1→A2）自动重算比例与视口尺寸**，正好解决"图幅变化需重映射"问题 |

**独立印证**：`VIEW` 命令创建模型视图时的"**保存图层快照（Save layer snapshot with view）**"官方说明为——
勾选后捕获当前图层状态，包括 ON/OFF、Freeze/THAW、LOCK 及图层颜色等属性，恢复视图时一并恢复。
即 `ViewTableRecord.LayerState` 就是它，legacy 只是把同一件事编程化了。
来源：[Design & Motion：Adding Sheet Views to the Sheet Set](https://designandmotion.net/autodesk/autocad/adding-sheet-views-sheet-set)

### 5.4 目标链路

```
DstDeleteLayouts → _. -LAYOUT _Template（新阶段图框 + 字段 + 页面设置）
                → DstRestoreViewports（按命名视图重建视口 + 还原图层状态 + 重建裁剪边界）
                → DstGetLayoutHandles 回填 Handle
```

### 5.5 现代化必须改造的 7 个点

| # | legacy 现状 | 必改 | 原因 |
| --- | --- | --- | --- |
| 1 | 全交互式（`GetEntity` / `GetKeywords` / `GetInteger` / `GetDouble`） | 固定命令 + JSON 参数/结果，无人值守 | Manager 走 accoreconsole + SCR，且禁止自由拼接命令 |
| 2 | 插件内直接 `DstViewer.DstToXml / XmlToDst` 读写 DST | DST 读写全部回 Python 侧受控链路，插件只收参数、只吐 JSON | 违反安全边界；`UtilityClass` 已被 `dst_platform/acsm` 取代（见 `RES-SH-002`） |
| 3 | `query.First()`：一布局只取一个视图、建一个视口 | 扩展为"一布局 N 视图 / N 视口" | 真实图纸常有总图 + 详图多视口 |
| 4 | 裁剪框靠布局里预先画好的 `TK-视口` 多段线 | **由命名视图数据自动重建矩形**（中心 + 宽高 + 扭转可完整还原矩形） | 布局被删时多段线也一并消失——**这是 legacy 方案的真实缺口**，但正好能自洽补上 |
| 5 | 只存 UCS，恢复时不设 `UcsPerViewport / UcsName`、`AnnotationScale`、`VisualStyleId`、前后剪裁 | 参数集补全（含 `UcsPerViewport` / `Ucs`） | 覆盖不全；这些在 .NET 里均可读写。**注意：不设 `UcsPerViewport` 则存下的 UCS 不会生效（§6.16）** |
| 6 | 视图名 = 纯数字编号，布局名首段也是编号 | 匹配规则必须与"命名规则统一派生"同源 | 现有布局名由受控规则生成（含范围/后缀），不能在两处各写一份匹配 |
| 7 | 捕获源是模型空间的"视图框"矩形（要求设计人员先画框） | 改为**从布局现有视口反推**（`GetViewportBoundsInMS` 的逆运算） | 用户诉求是"保持设计人员已设好的视口"，不应逼其改工作习惯；首次套图框前捕获即可。批量化的顺序设计见第六节 |

### 5.6 工程风险

- **目标框架**：legacy 为 .NET 4.5 / 4.7，Manager 插件为 .NET 4.8 双版本（2016 / 2020）。
  `ViewTableRecord.LayerState` 与 `RestoreLayerState(name, ObjectId, int, LayerStateMasks)` 重载在两端
  SDK 的编译与运行可用性**需实测**。
- **`config.ini` 本地已不存在**（图幅→长度映射、`[ClipLayer]`、`[DefaultScaleType]` 都在其中）。
  需按 `ARCH-LR-001` §10.3"旧 `config.ini` 只作迁移输入、目标用带 schema 的 TOML"重建，
  并保留其中**建筑 / 市政两套比例口径**。

### 5.7 与既有计划的关系（避免重复立项）

- `docs/legacy-refactor/architecture/ARCH-LR-001-modern-python-refactor-baseline.md` §10.5 曾把
  `SetViews` / `SetViewPort` 列为迁移目标，但定位是 **AutoCAD 桌面交互插件**（"视图编号和状态逻辑抽出；
  比例计算移入纯类库"）。
- `docs/dst-builder/product/prds/PRD-DB-001-guided-sheetset-generation.md` §5 又把这两个列入**非目标**。
- 两份都属历史 scope（`legacy-refactor` / `dst-builder`，只读保留）。Builder 已退场、Manager 是唯一现役
  产品，而本需求正需要这块能力 → 性质是**新立项**：把机制**重新实现**为 Manager 的固定 Worker 命令，
  不是复活旧插件。
- `RES-SH-002` 已把 `UtilityClass` 的 DST/XML 机制研究完毕，并由 `dst_platform/acsm` 取代。
  **legacy 插件中唯一仍有独立价值的部分，就是"命名视图 + 图层状态"这套视口持久化机制。**

## 六、批量视图框提取、顺序与朝向确定

本节回应"能否用『提取某图层的全部封闭多边形』替代逐个人工拾取"、"批量提取如何确定顺序"，
以及"从 view 到 viewport 涉及的坐标系转换与 UCS 依赖"。
结论是：**能，但顺序与朝向都不能靠算法猜——必须变成项目级显式声明 + 一次性建序 + N 次非交互复用；
且坐标系换算应优先交给 AutoCAD 自带入口，不要自己算 DCS。**

### 6.1 两条已确认的现实约束（2026-10-01）

1. **图框矩形一般不带标识**（矩形内没有图号属性/文字，图框块名也不含图号）⇒"矩形自带标识"不能作为默认路径。
2. **顺序与工程类型相关**：
   - **线性工程**：图框沿一条曲线（道路中心线等）铺设，顺序 = 沿中心线的推进顺序（里程/桩号序）。
   - **非线性工程**：按设计者喜好排布（从左到右、从上到下、多排从左到右，也可能随意摆放）⇒**无通用几何规则**。

### 6.2 关键结论：先把"顺序"的语义还原出来

`SetViews` 的循环里，拾取顺序唯一的产物是编号，编号被写进 `ViewTableRecord.Name`；恢复侧 `SetViewPort`
用"布局名首段数字 ↔ 视图名数字"对齐。所以：

> **拾取顺序承载的是"这个矩形属于哪张图（哪个布局 / 图号）"，不是几何次序。**

推论：

- 几何排序只能产出"第 k 个"，而恢复需要的是**图号**；
- 二者等价依赖一条隐含假设——**布局顺序 == 矩形几何顺序**。批量化必须把这条假设显式化为可校验项，
  否则错配了也看不出来；
- **"非交互"的正确形态是"一次建序 + N 次非交互复用"**：换阶段是反复发生的事件，建序是一次性事件。
  把一次性人工成本转移到建序，才是这个需求的正确解。

### 6.3 三档排序策略（由项目 / 标准显式声明）

| 模式 | 适用 | 排序键 | 自动化程度 |
| --- | --- | --- | --- |
| `linear` | 线性工程：图框沿中心线铺设（含旋转对齐） | 矩形中心投影到中心线的**里程参数** | 全自动 |
| `grid` | 非线性但排布规整：从左到右 / 从上到下 / 多排 | AABB 分带聚类 → 带内从左到右 | 自动 + 预览确认 |
| `manual` | 任意排布、蛇形、随意摆放 | 已持久化的顺序表 | **一次性交互建序**，之后全非交互 |

要点：

- 非线性工程里"从左到右 / 从上到下 / 多排从左到右"都是 **reading order 的变体**，`grid` 能覆盖；真正需要
  `manual` 的是"随意摆放"与**蛇形排布**（第一行左→右、第二行右→左）——后者 reading order 必然判错。
- `linear` 是必须支持的：图框**旋转对齐中心线**时，任何行列分带法都会失效。
- 工程类型、中心线图层、排序方向应作为**标准或项目级配置**显式声明，不要让算法去猜。可选辅助：对矩形中心
  点云做主成分/曲线拟合，只在"沿主轴推进是否单调、残差是否小"层面给出**建议模式**提示，**不作为自动决策依据**。

### 6.4 `linear`：沿中心线里程排序

1. 取约定图层上的中心线（`LWPOLYLINE` / `SPLINE` / `ARC`，或多段链）。
2. 对每个矩形中心 `c`：`nearest = curve.GetClosestPointTo(c, false)`；`param = curve.GetParameterAtPoint(nearest)`；
   `station = curve.GetDistanceAtParameter(param)`。
3. 按 `station` 升序 ⇒ 里程序，与线性工程的图号顺序天然一致。

注意：

- 多条中心线（多工点 / 多条路）时，先按"矩形中心离哪条中心线最近"分组，组内按里程排；
  **组间顺序仍需要外部清单**（回到清单驱动）。
- 同一里程附近可能并存多套图框（平面 / 纵断 / 横断）⇒ 需第二排序键（到中心线的侧向距离与方向），
  否则退回 `manual`。

### 6.5 `grid`：带容差的 reading order

```
1. 对每个矩形取 AABB（扭转矩形用轴对齐包围盒：中心不变、区间稳定）
2. tol = 0.5 × median(AABB 高度)
3. 分带：按 AABB.cy 降序聚类；相邻 cy 之差 ≤ tol 视为同带
   （更稳：两个 AABB 在 y 方向有重叠 → 同带）
4. 带内按 AABB.cx 升序
5. 行序方向、列序方向作为参数（支持从下到上 / 从右到左）
```

三个稳定性要求：

- 扭转矩形必须用 **AABB**，不能用顶点坐标（旋转后顶点顺序会变）。
- **稳定 tie-breaker**：`cx` → `cy` → 面积降序。**绝不能用句柄**——句柄随编辑变化，捕获与恢复两次运行
  结果会不一致。
- 结果必须**预览确认**后才能落库。

### 6.6 `manual`：沿用交互拾取作为建序步骤

`SetViews` 的交互形态在"建序"这一次性场景下**反而是最优的**：人拾取时能立刻在屏幕上看到选中的是哪个图框，
是最可靠的一次性确认。改造点只是：拾取完成后写入**顺序表 + 几何指纹**，此后全部非交互。

### 6.7 顺序表与几何指纹（可恢复性的核心）

只把编号写进 `ViewTableRecord.Name` 是不够的：图被增删改、矩形数量变化时会**静默错配**（把 A 图的视口内容
还原到 B 图）。因此每个命名视图还应携带**来源指纹**：

| 字段 | 用途 |
| --- | --- |
| `view_number`（= 图号） | 写在 `ViewTableRecord.Name`，恢复侧的对齐键 |
| `frame_fingerprint`：源矩形的中心 + 宽高 + 扭转（或 AABB 的规范化哈希） | 检测"图框被移动 / 替换" |
| `frame_count`：捕获时的矩形总数 | 数量不符即阻断 |
| `order_mode` + 策略参数（中心线图层、行/列方向） | 复现排序前提 |

存放位置候选：`ViewTableRecord` 的扩展字典 / XDATA（**需实测确认该符号表记录的可写面**），
或退回 Manager 侧随工作区保存的 JSON。

### 6.8 恢复时的双向校验（无标识下的错配检测）

因为没有标识，只能用"一一对应"兜底：

- 每个命名视图反算模型范围 → 必须**恰好落在一个矩形内**；
- 每个矩形 → 必须**恰好被一个视图覆盖**（双射）；
- 矩形总数 == `frame_count`；
- 任一不符 → 报稳定诊断码并提示重新建序，**绝不静默按顺序硬配**。

再叠加"从已有视口反推"（§5.5 改造项 7）作为第三条独立来源，可进一步降低错配概率。

### 6.9 命令形态（两步分离，便于预览与审计）

```
① DstListViewFrames <图层名>
   → 只读枚举该图层上的封闭多边形，输出 JSON：
     { handle, aabb{cx,cy,w,h}, center, width, height, twist, area }
     （不做业务排序、不写库；可选附带 order_key 供预览）

② DstCreateViews <映射JSON>
   → 按 Manager 给定的 {view_number → frame_handle | frame_fingerprint} 建命名视图，
     并写入 order_mode 元数据；写完回读做 §6.8 的双向校验
```

排序与配对决策全部留在 Python 领域层（纯函数、可单元测试、可预览、可回滚），插件只做 CAD 数据库操作——
与 `AGENTS.md` 的分层契约一致。

### 6.10 批量前必须收紧的三处

| # | 现状 | 问题 |
| --- | --- | --- |
| 1 | `if (PL.NumberOfVertices != 4 && !PL.Closed)` | 守卫用 `&&`，只拒绝"既非 4 顶点又未闭合"，于是**4 顶点未闭合的折线**和**≥5 顶点的闭合多段线**都会被接受，再只取前 4 个点当矩形 |
| 2 | `TwistAngle` 由当前 UCS 推导（`db.Ucsxdir / db.Ucsydir`） | 依赖执行时的 UCS 状态，无人值守不可控。应改为从矩形自身边方向推导，并保证 `ViewTwist` 与 `ViewCenter` 的 DCS 表达同源（见第十一节 V4 往返验证） |
| 3 | 循环靠 `PromptStatus.OK` 结束 | 批量化后终止条件变为"没有更多多边形"，**校验与确认必须前移到预览步骤**，不能依赖用户逐个按键 |

另需补：边长的长度下限与自交检查（`IsPerpendicularTo` 对零长度向量行为未定义）；
`if (V1.Length > V4.Length)` 判定长短边依赖顶点顺序，扭转矩形下需复核。

### 6.11 第三个自由度：朝向（UCS 依赖）

用户在 2026-10-01 补充：在 `SetViews` 选择矩形框**之前**，需人工以矩形框为基准设置 UCS（**底边为 X、高为 Y、
X 正向朝着序号增加的方向**）；**只要矩形框不平行，每次都要重设 UCS**。

这说明 legacy 流程实际是在人工提供两个自由度：

| 自由度 | 含义 |
| --- | --- |
| ① 底边方向 | 矩形的"右"朝哪（对应矩形自身坐标系的 X 轴） |
| ② X 正向 | 沿底边的两个方向里选一个（指向"下一张图"的那个） |

而 `SetViews` 的 `TwistAngle` 正是从 `db.Ucsxdir / Ucsydir` 推导的（以及 `NewVr.SetUcs(db.Ucsorg, db.Ucsxdir, db.Ucsydir)`）——
即**朝向的唯一输入源就是这个人工 UCS**。若批量化只解决顺序、朝向仍靠人工设 UCS，则"非交互"目标并未真正达成。

关键观察：**自由度 ② 恰恰就是"顺序"决定的**。朝向与顺序不是两件事，是同一件事的两面。

### 6.12 AutoCAD 坐标系体系与各字段归属

| 名称 | 定义要点 | 谁在用 |
| --- | --- | --- |
| **WCS** | 世界坐标系，永不变；.NET API 未特别说明的点均按 WCS | `ViewDirection`、`ViewTarget`、模型/图纸空间实体坐标 |
| **UCS** | 用户坐标系，工作用 | 命令行输入输出；每视口保存的 `Ucs` + `UcsPerViewport`(UCSVP) |
| **OCS / ECS** | 对象坐标系，由实体自身拉伸方向定义 | 部分实体属性（`Polyline2d` 等） |
| **DCS** | **显示坐标系：原点 = `TARGET`（视图目标点），Z 轴 = 视线方向**；"视口永远是它自己 DCS 的正投影" | **`ViewCenter` / `ViewHeight`**、`AbstractViewTableRecord.CenterPoint / Height / Width` |
| **PSDCS** | 图纸空间 DCS，**只能**与某个模型空间视口的 DCS 互转，本质是 2D 相似变换（可求比例） | 图纸空间 ↔ 视口 的位置/比例换算 |

字段归属（逐条核对 Managed Reference）：

- `Viewport.ViewCenter` —— "view center (**in display coordinate system coordinates**)" ⇒ **DCS**
- `Viewport.ViewHeight` —— "height (**in display coordinate system coordinates**) of the Model Space view" ⇒ **DCS**
- `Viewport.ViewDirection` —— "(in Model Space **WCS** coordinates)"，方向为 target → camera ⇒ **WCS**
- `AbstractViewTableRecord.CenterPoint` —— "center point of the view **in DCS coordinates**"；`Height` / `Width` 同 ⇒ **DCS**
- `Viewport.TwistAngle` / `AbstractViewTableRecord.ViewTwist` —— 绕**视线**旋转，**零角在水平向右（即 DCS 正 X 轴）**；`VIEWTWIST` 系统变量"视图旋转角，相对于 WCS 度量"

两个推论：

1. **legacy 的"逐字段直接拷贝"（`VP.ViewCenter = VR.CenterPoint`）是成立的**：两侧 DCS 由同样三个量
   （`target` / `viewDirection` / `twist`）定义，属同构坐标系。
2. **twist / `DVIEW` 的"视图旋转"语义容易与直觉相反**（官方专文 *Objects in a Layout Viewport Appear Rotated
   Even Though They Look Correct in Model Space*），任何手算都必须实测标定。

### 6.13 关键简化：`ViewTarget = 矩形中心` ⇒ `ViewCenter` 恒为 (0,0)

因为 **DCS 的原点就是 `TARGET`**，只要令 `ViewTarget = 矩形中心`，`ViewCenter` 就恒为 `(0,0)`。
这把"要算的 DCS 映射"降级为"一个约定"。legacy 之所以要手算
`DcsCenter = CT.TransformBy(Matrix2d.Rotation(TwistAngle, origin))`，正是因为它没动 `target`（默认原点）。

新实现应固定该约定，并把 `ViewCenter` 写为 `(0,0)`。

### 6.14 朝向的自动化规则

| 自由度 | 来源（按优先级） | 适用 |
| --- | --- | --- |
| ① 底边方向 | **中心线在该投影点处的切线方向** | 线性工程（与排序同源，最优雅） |
| | **"最接近水平的那条边"作为底边**（\|angle\| ≤ 45° 规则）+ 用矩形 W:H 与标准图幅长宽比（含 90° 旋转）消歧 | 非线性工程（绝大多数图框正放） |
| | 显式标注（XDATA / 属性） | 可选覆盖 |
| ② X 正向 | **相邻矩形中心增量**：取"矩形 i 中心 → 矩形 i+1 中心"在底边方向上的投影符号；最后一个矩形沿用前一增量 | 自动，适用 `grid` 与 `linear` |
| | 线性工程直接用**里程增加方向**（中心线切线） | 线性工程 |

即：**先排好序，朝向由排序结果的增量方向倒推** —— 用户手工设 UCS 的两个自由度均可自动求解。

风险：若图框旋转 90° 摆放（纵向图幅），"最接近水平边"可能选中短边 ⇒ 必须用"矩形 W:H 与标准图幅长宽比匹配
（含 90° 旋转）"做消歧校验，无法消歧时转 `manual`。

### 6.15 twist 符号必须实测标定

官方只说"绕视线、从屏幕前方看向后方、零角在 DCS 正 X 轴"，**未给出符号约定**；legacy 的
`if (Ucsxdir.Y > 0) TwistAngle = 2π − angle` 分支也无法从静态阅读判定正误（取决于
`Vector2d.GetAngleTo` 的确切取值区间）。因此：

1. **优先用 AutoCAD 自带入口，绕开手算**：ObjectARX 全局函数
   `acedSetCurrentView(AcDbViewTableRecord* pVwRec, AcDbViewport* pVP)` 把视图记录直接应用到某视口，
   **DCS 换算由 AutoCAD 自己完成**（可与 legacy 用 `acedSetCurrentVPort` 同一套 P/Invoke 手法处理，需实测可行性）。
2. **若必须手算**：把符号收敛到**一个纯函数**，并用**回读闭环**标定——设一次、读回
   `ViewCenter / ViewHeight / TwistAngle` 与视口的模型空间范围，与矩形逐项比对；约定做成常量或首次标定。
3. **单位口径必须显式声明**：`CustomScale` = 图纸单位 / 模型单位，与坐标系无关，但"图幅长度"的单位口径
   （模型为米、图纸为毫米）若弄错，1:1000 会差 1000 倍。

### 6.16 legacy 遗漏：UCS 存了但不会生效

`Viewport.UcsPerViewport`（UCSVP）的说明是"若为 true，则随该视口保存的 UCS 生效"。legacy 用 `SetUcs(...)`
存了 UCS，但恢复时既未设 `UcsPerViewport`，也未设 `Ucs` ⇒ **该 UCS 实际上不会被激活**。
这是 §5.5 改造项 5 的精确落点。

### 6.17 用"一台相机"理解 view 存了什么

矩形框只是"圈个范围"；**view 记录的是一台相机的姿态**——相机站在哪、朝哪看、镜头怎么转、取景框多大。
viewport 就是"把这台相机架到图纸上的某个位置，并告诉它按什么比例成像"。

坐标系之所以绕，是因为**相机相关的数字（看哪、看多大）必须以相机自己为原点来量**，而相机自己的原点又是由
另外几个数字生成的——所以它们**必须成组保存**，单独存一个没有意义。

| 字段 | 含义（大白话） | 坐标系 |
| --- | --- | --- |
| `ViewTarget` | 相机**盯着模型上的哪个点**（镜头中心落点） | **WCS** |
| `ViewDirection` | 相机**朝哪个方向看**（从 target 指向相机） | **WCS** |
| `ViewTwist` | 相机**绕视线自转了多少度** | 角度，零位 = DCS 正 X 轴 |
| `CenterPoint` | **看到的模型中心** | **DCS** |
| `Width` / `Height` | **取景框的宽和高**（模型单位长度） | **DCS** |
| `Ucs`（`SetUcs`） | 顺手记下的一把尺子 | UCS 定义 |
| `LayerState` | 顺手记下的图层状态名 | — |

**为什么 `CenterPoint` 是 DCS 而不是 WCS**：

```
ViewTarget     → 相机放在模型上的哪个点   （决定 DCS 原点）
ViewDirection  → 相机朝哪看               （决定 DCS 的 Z 轴）
ViewTwist      → 相机绕视线自转多少度     （决定 DCS 的 X/Y 朝向）
─────────────────────────────────────────────────
⇒ 这三件事定了，DCS 就唯一确定了
⇒ 这时 "CenterPoint = (0,0)" 才有明确含义：矩形中心正好在镜头中心
```

> **`CenterPoint` 单独存是完全没意义的**；它只有在"和 target / direction / twist 配套"时才能还原出实际位置。
> 这就是"创建 view 需要保存的坐标系关系"——**不是一个值，是一组互相依赖的值**。

**宽高的"方向语义"**：`Width` / `Height` 是两个标量，但它们对应**屏幕的左右和上下**，而屏幕的左右由 `ViewTwist` 决定。
即：**朝向一变，"矩形的哪条边算宽"就跟着变**。例如矩形底边与 X 轴成 30°、尺寸 200×100：

- 朝向取 30°（底边当"宽"）⇒ `Width=200, Height=100`，出图时是横的 ✅
- 朝向取 120°（高边当"宽"）⇒ `Width=100, Height=200`，出图时转了 90° ❌

这正是 legacy 要人工设 UCS 的原因：`TwistAngle` 从 `db.Ucsxdir / Ucsydir` 推出，**UCS 是当时唯一能告诉程序
"哪边是底边、哪头是正方向"的手段**（替代方案见 §6.14）。

### 6.18 从 view 到 viewport 的实现流程

viewport 是纸空间里的一个"窗户"，它有**两套**互不相干的几何量：

| 属性 | 含义 | 坐标系 |
| --- | --- | --- |
| `CenterPoint` / `Width` / `Height` | 这个**窗户本身**画在图纸上的位置和大小（mm） | 图纸空间坐标 |
| `ViewCenter` / `ViewHeight` | 透过窗户看到的**模型内容**的中心和高度 | **DCS** |
| `CustomScale` | 两者之间的换算比（图纸长度 ÷ 模型长度） | 标量 |
| `ViewTarget` / `ViewDirection` / `TwistAngle` | 相机姿态 | WCS / WCS / 角度 |

```
【捕获侧】在模型空间（设计人员已经调好了视口，或画了视图框）
  1. 拿到矩形：中心 C、宽 W、高 H、底边方向角 θ          ← 全在 WCS
  2. 定相机：
       ViewTarget    = C                    （镜头对着矩形中心）
       ViewDirection = (0,0,1)              （平面图都是俯视）
       ViewTwist     = θ                    （相机自转，让底边变水平）
  3. 定取景框（因为 target = C，所以）：
       CenterPoint   = (0, 0)               ← 不用算！
       Width = W,  Height = H
  4. 顺手存：SetUcs(矩形左下角, 底边方向, 高方向) + 图层状态名
  ⇒ 写进一个 ViewTableRecord

【恢复侧】在图纸空间的布局里
  5. 打开该布局的图纸空间 BTR（每个布局有自己独立的纸空间 BTR）
  6. new Viewport()，先摆窗户（图纸空间坐标）：
       CenterPoint = 图框内框中心（纸空间位置）
       Width  = W × Scale
       Height = H × Scale          （Scale = 图幅内框长 ÷ W，见 §6.19）
  7. 再装相机（从 view 记录里搬）：
       ViewTarget    = VR.ViewTarget        (WCS)
       ViewDirection = VR.ViewDirection     (WCS)
       TwistAngle    = VR.ViewTwist         (角度)
       ViewCenter    = VR.CenterPoint       (DCS —— 与存的 (0,0) 一致)
       ViewHeight    = VR.Height            (DCS)
  8. 收尾：Layer = "TK-视口"、On = true、Locked = true
            NonRectClipEntityId / NonRectClipOn   ← 非矩形裁剪
            RestoreLayerState(VR.LayerState, VP.Id, …)   ← 还原该视口的图层显示
            UcsPerViewport = true + Ucs   ← ⚠️ 不设这个，第 4 步存的 UCS 不生效（§6.16）
  9. 回读校验（见 §6.20）
```

**为什么第 7 步"直接把 `CenterPoint` 拷到 `ViewCenter`"能成立**：因为两侧的 DCS 由同样三个量
（target / direction / twist）定义，如同两个人用同一把尺子量，数字可以直接搬。

这也解释了 legacy 那句看似多余的旋转：`DcsCenter = CT.TransformBy(Rotation(TwistAngle, origin))` —— 它是因为
**没有改 `ViewTarget`**（还是默认原点），所以必须手动把 WCS 的中心转进 DCS。
若把 `ViewTarget` 设成矩形中心（§6.13），这个旋转完全不需要。

### 6.19 两个"中心点"、比例与单位口径

最容易糊涂的地方，用一句话钉住：

> **`CenterPoint` 是"窗户画在图纸的哪块地方"；`ViewCenter` 是"从窗户往里看，看到的是模型哪块地方"。**

- 换纸空间位置 → 只改 `CenterPoint`
- 平移看到的模型内容 → 只改 `ViewCenter` / `ViewTarget`
- 换比例 → 改 `CustomScale`（`Width` / `Height` / `ViewHeight` 会跟着联动）

另一条反直觉的点：

> **视口自己永远不转，转的是"里面的模型"。**

图纸上那个矩形窗口永远是正的（`CenterPoint` / `Width` / `Height` 相对图纸）；斜的是窗口**里面**的图。
所以"旋转视口"是常见错误说法，实际改的是 `TwistAngle`。

比例（legacy 口径）：

```
Scale = 图幅内框长（图纸单位） ÷ 视图宽 W（模型单位）
视口纸空间宽 = W × Scale   ← 正好等于图幅内框长
视口纸空间高 = H × Scale   ← 应正好等于图幅内框宽
```

`CustomScale` 的官方定义是"图纸单位与模型单位的比值"，**与坐标系无关**，但：

> ⚠️ **单位口径必须显式声明。** 模型按米画、图纸按毫米出，若口径搞反，1:1000 会差 **1000 倍**。
> 它比 twist 符号更容易踩，因为它不报错，只是图错。

### 6.20 一条能自动暴露朝向错误的等式

若 twist 设对了，**视口纸空间矩形的宽高比必须等于模型矩形的宽高比**：

```
Width / ViewWidth  ==  Height / ViewHeight
```

**适用范围（附录 B 标定推演后修正）**：本条只验证「图幅内框宽高比 == 声明视图宽高比」的**自洽性**，
因为 `ViewWidth` / `ViewHeight` 是我们自己写进去的，两边必然等比例。它能抓**图幅与视口不匹配**或
Manager 算错 `paper_height`，但**不能抓 twist 错误**（无论差 90° 还是符号相反）。

twist 错误必须用**定向角点比对**（附录 B 判据 A）：把 DCS 窗口四角按 `twist` 映回 WCS，应与矩形
四角逐个重合。

> 特别注意：**AABB 也区分不了 +θ 与 −θ**（`w=W|cosθ|+H|sinθ|` 对 θ 对称），
> 所以「反算包围盒相等」不能当作朝向正确的证据。

叠加"矩形个数 == 视图个数"与"每个视图范围恰好落在一个矩形内"两条，即构成无标识条件下的一整套错配防线
（§6.8）；符号方向的最终确认靠附录 B 判据 C（样本内放文字/箭头目视）。

## 七、方案 3（图签块重定义）详解

### 7.1 成立原理

```
标准包布局模板资产
└─ 图签 = 增强属性块（块定义 BlockTableRecord + ATTDEF 列表，字段在 ATTDEF 中）
   └─ 布局内 = BlockReference（块参照）
        视口（AcDbViewport）——不碰
        图签（BlockReference）——只换它的「定义」，不换参照本身
```

`BlockTableRecord`（块定义）是**数据库级**对象，`BlockReference`（块参照）才是布局内实体。
**换定义 → 所有参照自动更新**，参照的 ObjectId、位置、所属布局全不变。

### 7.2 实现机制

| 步 | 动作 | 要点 |
| --- | --- | --- |
| 1 | 把标准资产 DWG 的**同名块定义**克隆进目标 DB | 用 `IdMapping` 一并带入嵌套块、图层、线型、文字样式等依赖；避免交互式 `-INSERT` 重定义 |
| 2 | `ATTSYNC <块名>` 同步属性 | Tag 相同 → **保留实例已有值**；新块多出的 Tag → 用 ATTDEF 的 Default（即字段）初始化；旧块多出的 Tag → 删除 |
| 3 | 若图幅也变，另行 `AcDbPlotSettings::copyFrom` | 图幅 / 图纸尺寸 / 打印样式 / 打印区域属于 `Layout`，**不属于块** |
| 4 | 回读校验 + before/after 哈希 | 走既有发布事务 |

### 7.3 能力边界（须写入 Spec）

| 能管 | 不能管 |
| --- | --- |
| 图签 / 会签栏 / 图框边框（只要是块） | 图幅、页面设置、打印样式（`Layout.PlotSettings`） |
| 图签里的字段（ATTDEF Default） | 布局里**非块**的散落实体（指北针、说明文字） |
| 图签内的静态内容（规范号、版本号、行数） | 视口本身（正因不碰它，才零风险） |
| 嵌套子块（图框 → 内嵌图签） | 图号 / 图名等 DST 属性（本就该改 DST，无需换图） |

### 7.4 五个必须写进设计的坑

1. **页面设置不跟着变**：阶段变化若含 A1→A2，只换图签块会出现"框线换了、纸张还是旧的"→ 出图错。
   标准里必须把"图签块资产"与"页面设置参数"拆成两类，切换时一起处理。
2. **块重定义是全局的**：同一 DWG 内所有该块名的参照都会换。多布局同阶段时正合意；若同 DWG 要并存
   两种图签（封面 vs 图纸），**必须用不同块名按角色区分**，并在标准里声明角色→块名映射。
3. **ATTSYNC 保留旧值 = 字段可能被"人工覆盖"吃掉**：若有人改的是属性**值**（而非定义默认值），
   ATTSYNC 会保留该旧值 → 字段丢失。设计里要加校验项。
4. **字段必须放在 ATTDEF 的 `Default`，不能放在实例的 `Value`**。Autodesk 对此有明确警告
   （"**NEVER insert a field in an attribute 'Value.'**"）。这同时是对现有资产的**体检项**。
5. **动态块**：重定义会整体替换定义（含参数与可见性状态），实例当前可见性状态可能被重置；若标准资产
   是动态块，须专门验证。

### 7.5 收益（相对方案 1）

- 视口 **100%** 不动：VP 覆盖、非矩形剪裁、注释比例、锁定全都不用管
- **布局 Handle 不变 → DST 完全不需要回填**（比方案 1 少一整个变更面）
- 图号 / 图名等字段**本就自动求值**，改 DST 属性即可
- 无序列化、无视图/视口往返 → 实现最简、最好测、最易审计

## 八、Callout Block / 视图标签块：概念与实证

### 8.1 四个相邻但不同的概念

| 概念 | 是什么 | 存在哪 | 谁创建 |
| --- | --- | --- | --- |
| **Model View**（模型视图） | 模型空间的命名视图（`VIEW` 命令），**可选带"保存图层快照"** | DWG 的 `ViewTable`（符号表，数据库级） | 设计人员 / legacy `SetViews` |
| **Sheet View**（图纸视图） | 把一个 Model View **放到某张图纸上**的实例：编号、标题、类别 + 那个视口 | DST：`AcSmSheet` → `AcSmSheetViews` → `AcSmSheetView` | SSM 的"放置视图" |
| **View Label Block**（视图标签块） | 放置视图时**自动插在图口左下角**的块，显示该视图编号 / 标题 / 比例 | DST：`AcSmSheetSet` → `AcSmAcDbBlockRecordReference propname="DefLabelBlk"`（**单数，只能挂一个**） | 图纸集属性中指定 |
| **Callout Block**（标注块） | **不是视图**，是"指路牌"块：典型内容 *见 3/A-402*，引用**别的图纸上的视图** | DST：`AcSmSheetSet` → `AcSmCalloutBlocks`（**复数**）；或按视图类别挂 `AcSmViewCategory` → `AcSmCalloutBlockReferences` | 图纸集属性中指定（可多个） |

### 8.2 关键机制：`SheetSetPlaceholder` 字段

AutoCAD 的 Field 对话框里有**两个容易混淆的字段类别**：

| 字段类别 | 符号 | 行为 |
| --- | --- | --- |
| **`SheetSet`** | `CurrentSheetNumber` / `CurrentSheetTitle` / `CurrentSheetCustom` … | **与具体图纸绑定**，插入即求值。**图签块用这一种** |
| **`SheetSetPlaceholder`** | `SheetNumber` / `ViewNumber` 等占位类型 | **不与任何图纸或图纸集绑定**，是"槽位"；由 SSM 在插入时填入被引用视图的图号与视图号 |

Autodesk 原话：「Using the SheetSetPlaceholder field in your callout block enables you to define block
attributes for fields that **are not associated with any particular sheet or sheet set**.」

**为什么必须这样设计**：Callout 块是模板——造块时还不知道将来要指向哪张图，所以用占位符，
由 SSM 插入时填值，并可选 **Associate hyperlink**（点击标注块直接跳到被引用图纸并缩放到该视图）。

来源：[Autodesk Blog：Automate Callout Data](https://www.autodesk.com/blogs/autocad/sheet-sets-automate-callout-data-autocad)、
[To Insert a Sheet Set Placeholder Field](https://help.autodesk.com/view/ACDLT/2026/ENU?caas=caas%2Fdocumentation%2FACDLT%2F2014%2FENU%2Ffiles%2FGUID-DA868354-801C-43E1-AA31-9C14B51F6D9C-htm.html)、
[engineering.com：How to Make and Work with AutoCAD Sheet Sets](https://www.engineering.com/how-to-make-and-work-with-autocad-sheet-sets)

### 8.3 Callout 块的制作四要点

1. 字段必须插在 **`BATTMAN` → 属性定义 → `Default`**（默认值）里，**绝不能**插在实例的 `Value` 里
2. 属性定义 **`Preset = Yes`**（预设），插入时不提示用户输入
3. 可选勾选 **Associate hyperlink**
4. 块可存为"独立 DWG 文件"，也可存为"某 DWG / DWT 里的块定义"；图纸集属性取用时两种模式：
   `Select the drawing file as a block` 或 `Choose blocks in the drawing file`

### 8.4 使用流程

```
SSM → Sheet Views 选项卡 → 右键某个视图 → Place Callout Block → 在图纸布局上点插入点
（首次会提示先 Select Blocks，把 callout 块挂到图纸集属性上）
```

### 8.5 与图签块的对照

| | 图签块 | Callout 块 |
| --- | --- | --- |
| 作用 | 显示**本图**的信息 | 引用**别的图纸 / 视图** |
| 字段类别 | `SheetSet`（`CurrentSheet*`） | `SheetSetPlaceholder`（`SheetNumber` / `ViewNumber`） |
| 求值时机 | 插入即求值，随 DST 属性自动更新 | 由 SSM 插入时填值 + 建超链接 |
| 挂在哪 | 直接在布局里，标准资产携带 | 图纸集属性（可多个）或视图类别下 |
| 数量 | 不限 | 图纸集级不限；视图类别级按类别挂 |

### 8.6 原生「Place View」不能用来解视口问题

SSM 的原生放置机制：把 Model View 拖到图纸布局 → **AutoCAD 把该图作为 XREF 附着到模型空间，
按视图范围生成视口，并按比例设置缩放**；放置时自动插入视图标签块。
来源：[Design & Motion：Adding Sheet Views](https://designandmotion.net/autodesk/autocad/adding-sheet-views-sheet-set)、
[Autodesk Blog：Add View Labels](https://www.autodesk.com/blogs/autocad/sheet-sets-add-view-labels-autocad)

三个硬伤：

1. **它会自带 XREF** —— 为 Autodesk 力推的"模型文件 / 图纸文件分家"范式设计。而本项目是
   **模型与布局同 DWG**，用原生 Place View 就变成"自己 xref 自己"，或被迫拆成两个文件；
   而这正是第三节已否决的 xref 方向。
2. **它是交互式的**（拖放 + 预览 + 右键选比例），accoreconsole 无人值守场景基本无法驱动。
3. **它只"加"视口，不"替换"** —— "换阶段时旧视口怎么办"这个核心问题一点没解。

**结论**：Callout 不是视口方案。它的价值在于"图与图之间引用自动更新"（见 3/A-402 在重编号后自动跟改），
而这恰是"同模型多阶段出图"最易错乱、最值得自动化的场景——**该做，但要与视口问题解耦**。

## 九、本地真实样本证据（普查）

对本地 3 个真实工程 DST（`sample/project3 - copy/图纸集数据文件.xml`、
`docs/shared/research/project1-dst-xml/project1_sheetset.xml`、`sheetset-fail.xml`）做了元素普查：

| 元素 | 出现次数 | 状态 |
| --- | --- | --- |
| `AcSmSheetViews` | 324 | 每张图纸一个容器，**全部为空** |
| `AcSmCalloutBlocks` | 3 | SheetSet 级，**空容器** |
| `AcSmViewCategories` / `AcSmViewCategory` | 3 / 3 | 仅一个默认类别 |
| `AcSmCalloutBlockReferences` | 3 | 挂在 ViewCategory 下，**空容器** |
| `AcSmAcDbBlockRecordReference` | 3 | `propname="DefLabelBlk"`，**空** |
| `AcSmSheetView`（单数实例） | 0 | 从未创建过任何图纸视图 |
| `LabelBlockForViews` | 0 | 未出现 |

**结论：**

1. **现有工程完全没用这套原生机制**。容器骨架都在但全空 ⇒ "套图框出图"目前靠 legacy 的自研路线，
   与 DST 里这些容器无关；反证这块是**真空**。
2. **DST 里已有 `设计阶段` 自定义属性**（样本值 `初步设计`）；`图幅` 是**自定义图幅名**
   （样本值 `A3轨道`，不是标准 A3）；`出图比例` 为 `1:1000`。⇒ "按阶段出图"在属性层面已就绪，
   缺的只是**图签 / 图幅 / 视口这一层的切换机制**。
3. **DST contract 只登记了 7 类对象**（`src/dst_platform/acsm/contract.py`）：`AcSmSheetSet`、
   `AcSmSubset`、`AcSmSheet`、`AcSmCustomPropertyBag`、`AcSmCustomPropertyValue`、
   `AcSmAcDbLayoutReference`、`AcSmSheetViews`。**`AcSmCalloutBlocks`、`AcSmViewCategories`、
   `AcSmViewCategory`、`AcSmCalloutBlockReferences`、`AcSmAcDbBlockRecordReference` 全部未登记**，
   目前靠"未知元素宽容保留"。⇒ **要做 callout / label block 功能，第一步必须先把这些纳入 contract
   registry**（已知对象清单 + 必需属性 + clsid + `vt` 类型表 + 父级包含关系），否则写入结构没有校验保障。

## 十、待确认项（会改变实现细节）

1. **标准包各阶段的图签块是否同名？**
   - 同名 → 纯"块定义替换"，最干净（方案 3 直通）
   - 不同名（如 `图签-初设` / `图签-施工图`）→ 需多一步"替换块参照"（删旧参照 + 插新参照 + 搬属性值），
     仍在布局内、仍不动视口，但标准里要加"阶段 → 图签块名"映射
2. **图签块的字段是在 ATTDEF 的 `Default` 还是实例的 `Value`？**（决定方案 3 是否需要配套校验与资产返工）
3. **设计人员会不会在纸空间画东西**（注记、标注、图例）？会的话"布局整体替换"的破坏面远不止视口，
   方案 1 必须定义"迁移集"。
4. **视口里是否用了 VP 冻结 / VP 颜色等视口级图层覆盖？**（决定方案 1 是否必须做图层状态兜底）
5. **阶段之间图号 / 图名是否变化？** 变了就是"多套图纸"，方案 4（一布局多图框）直接出局，
   数据模型上要多布局并存。
6. **图幅是否会变？** 变则方案 3 必须与 `PlotSettings` 处理成对出现。

## 十一、真机验证清单（未执行）

均需在真实 AutoCAD（2016 / 2020 双版本，优先 Core Console）上验证：

1. **量化现状丢失范围**：扩展读取命令，统计现有 rebuild 路径下每布局的视口数、视图参数、
   VP 覆盖层数、纸空间非视口实体数（同时回答第十节第 3、4 点）。
2. **`-LAYOUT _Template` 替换布局后，同 DB 的 `ViewTable` 与 `LayerState` 是否完整存活**
   （预期存活，因二者都是数据库级；须实测确认 `-LAYOUT` 不清符号表 / 扩展字典）。
3. **`RestoreLayerState(name, VP.Id, 1, LayerStateMasks.None)`** 对**新建视口**在双版本是否生效、
   还原结果是否等同捕获时所见（.NET 与 AutoLISP 两条路径分别验证）。
4. **`ViewTableRecord.CenterPoint` 的 DCS / WCS 语义**：legacy 用 `CT.TransformBy(Rotation(TwistAngle))`，
   是否与 `Viewport.ViewCenter` 期望的坐标系一致 —— **全链路最易错处**，须用已知样本做往返一致性验证。
5. **模板布局自带视口**时与重建视口如何共存（先删模板视口 / 复用占位视口）。
6. **图纸集字段在导入的新布局中是否照常求值**（含 DST 回填新 Handle 之后），确认方案 1 的前提假设。
7. **块定义替换 + `ATTSYNC` 后字段是否仍正常求值**，以及人工覆盖过的属性值是否真的会吃掉字段。
8. **标定 twist 符号与 DCS 约定**（§6.15）：在真实 CAD 上用已知旋转角（如 30°）的矩形建一次视口，
   回读 `Viewport.ViewCenter / ViewHeight / TwistAngle` 与视口的模型空间范围，与矩形逐项比对；
   同时验证 `acedSetCurrentView` 是否可 P/Invoke 使用。

## 十二、后续落点建议

| 能力 | 方案 | 风险 | 前置 |
| --- | --- | --- | --- |
| **阶段切换换图签** | **方案 3**：块定义替换 + `ATTSYNC` + 校验 | 低 | 标准侧约定"图签块名 / 角色映射"；体检字段在 `Default` 而非 `Value` |
| 阶段切换含图幅 / 页面设置 | 方案 3 + `PlotSettings.copyFrom` | 中 | 图幅参数从标准派生（已有 `图幅` / `出图比例` 属性可利用） |
| 布局必须整体重建 | **方案 1**：命名视图 + 图层状态（legacy 机制现代化） | 中高 | 5.5 节 7 项改造清单 |
| 图纸交叉引用自动更新 | Callout / Label Block | 中 | 先补 5 类 AcSm 对象进 contract registry |

**推荐的组合策略**：以**方案 3 为主**（覆盖绝大多数阶段差异，零视口风险），**方案 1 为兜底**
（仅在布局/图幅必须重建时启用），Callout 作为独立能力另行立项。

## 十三、来源清单

**项目内（代码与样本）**

- `src/dst_manager/infrastructure/autocad/worker.py` L185–201、L216–272
- `plugins/src/DstManager.AutoCAD/Commands.cs` L17（`DstDeleteLayouts`）
- `src/dst_manager/application/cad_job.py` L715、L746；`src/dst_manager/application/creation_job.py` L434
- `legacy/plugin/setviews/SetViews/myCommands.cs`、`legacy/plugin/setviewport/SetViewPort/myCommands.cs`（本地私有目录）
- `src/dst_platform/acsm/contract.py`（7 类已知对象契约）
- `sample/project3 - copy/图纸集数据文件.xml`（本地私有样本）
- [`ARCH-LR-001`](../../../docs/legacy-refactor/architecture/ARCH-LR-001-modern-python-refactor-baseline.md) §10.3、§10.5
- [`PRD-DB-001`](../../../docs/dst-builder/product/prds/PRD-DB-001-guided-sheetset-generation.md) §5
- [`RES-SH-002`](../../../docs/shared/research/RES-SH-002-utilityclass-dst-xml-analysis.md)
- [`PLAN-DM-042`](../../plans/dst-manager/PLAN-DM-042-layout-template-paper-layouts.md)（布局模板资产单文件 + 勾选图幅）

**外部（官方文档与社区）**

- [AutoCAD 支持：Viewport overrides are not maintained if viewport is copied to another layout](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Viewport-overrides-are-not-maintained-if-viewport-is-copied-to-another-layout.html)
- [AutoLISP `layerstate-restore`](https://documentation.help/AutoLISP-Functions/WS1a9193826455f5ffd9a7a610ecb0483d5-67b6.htm)
- [Create Paper Space Viewports (.NET)](https://help.autodesk.com/cloudhelp/2026/ENU/OARX-DevGuide-Managed/files/GUID-61C22902-F63B-4204-86EC-FA37312D1B6E.htm)
- [Autodesk 开发者博客：How to Get Viewport Bounds in AutoCAD Model Space](https://blog.autodesk.io/how-to-get-viewport-bounds-in-autocad-model-space)
- [Autodesk 开发者博客：Creating new Layout based on another Layout using ObjectARX](https://blog.autodesk.io/creating-new-layout-based-on-another-layout-using-objectarx)
- [LAYOUT（命令）](https://help.autodesk.com/cloudhelp/2027/ENU/AutoCAD-Core/files/GUID-BCE3AD90-9DE0-488C-9CA4-5FDB9401DCE0.htm)、[Reuse Layouts and Layout Settings](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-LT-MAC/files/GUID-A6D40A6B-D65C-4368-9650-476CAD3DA0C3.htm)
- [Autodesk Blog：Automate Title Block Data](https://www.autodesk.com/blogs/autocad/automate-title-block-data-autocad)
- [Autodesk Blog：Automate Callout Data](https://www.autodesk.com/blogs/autocad/sheet-sets-automate-callout-data-autocad)、[Add View Labels](https://www.autodesk.com/blogs/autocad/sheet-sets-add-view-labels-autocad)
- [To Insert a Sheet Set Placeholder Field](https://help.autodesk.com/view/ACDLT/2026/ENU?caas=caas%2Fdocumentation%2FACDLT%2F2014%2FENU%2Ffiles%2FGUID-DA868354-801C-43E1-AA31-9C14B51F6D9C-htm.html)
- [Autodesk 论坛：Sheet Set Number 在模型空间不更新](https://forums.autodesk.com/t5/autocad-lt-forum/sheet-set-number-will-not-update-in-view-callout-block-in-model/td-p/10330053)、[Reddit 同题](https://www.reddit.com/r/AutoCAD/comments/ni08ga/is_there_a_workaround_for_using_automated_sheet)
- [Reddit /r/civil3d：标题栏放布局还是 xref](https://www.reddit.com/r/civil3d/comments/1jy8o0h/do_you_have_your_title_block_in_the_sheet_layout)
- [Autodesk 论坛：LayerState API RestoreLayerState 对布局/视口不生效](https://forums.autodesk.com/t5/net-forum/layerstate-api-restorelayerstate-not-working-on-layouts/td-p/9457129)
- [Design & Motion：Adding Sheet Views to the Sheet Set](https://designandmotion.net/autodesk/autocad/adding-sheet-views-sheet-set)
- [engineering.com：How to Make and Work with AutoCAD Sheet Sets](https://www.engineering.com/how-to-make-and-work-with-autocad-sheet-sets)
- [Autodesk 支持：Loaded external reference (XREF) does not display](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Loaded-xref-does-not-display-inside-a-drawing-in-AutoCAD.html)

## 十四、本轮未做的事

- 未修改任何产品代码、插件、标准 Schema、DST codec 或测试。
- 未在真实 AutoCAD 上执行任何验证（第十一节清单全部待执行）。
- 未立项、未创建 Spec 或 Plan；收敛的业务问题只登记在第十节，未写入 `todos/`。
- 未归档长期知识到 `docs/`（见文首"定位说明"）。

---

# 附录 A：`DstCreateViews` 字段契约与领域层纯函数签名草案

> **状态：draft（待立项）。** 本附录是 §6.17–6.20 的直接工程化，**不是已批准的设计**：
> 尚未确定编号的 Spec、未写实现代码、未做真机验证。待用户确认 G 节待裁决项后，
> 应另立 `SPEC-DM-0XX`（长期知识）与 `.planning/plans/dst-manager/` 实施计划，
> 本附录改为指向该 Spec 的链接（避免一内容两权威位置）。

## A.1 为什么是两个命令而不是一个

沿用 §6.9 已确立的两步分离原则，并把它落到字段级：

| 命令 | 性质 | 做什么 | 不做什么 |
| --- | --- | --- | --- |
| `DstListViewFrames` | **只读** | 枚举指定图层上的封闭多边形，输出几何 JSON | 不排序、不写库、不 QSAVE |
| `DstCreateViews` | **受控写入** | 按 Manager 给定的映射建命名视图（+ 可选建视口）并回读校验 | 不猜顺序、不猜朝向、不读 DST |

排序与配对决策全部留在 Python 领域层（纯函数、可单测、可预览、可回滚），插件只做 CAD 数据库操作——与
`AGENTS.md` 的分层契约一致。

## A.2 `DstListViewFrames` 契约

**固定参数**（不接受自由文本；`layer` 走受控字符集校验）

```
DstListViewFrames <视图框图层> [中心线图层] [order_mode=linear|grid|manual]
```

**输出**：写到 DWG 同目录的 `<dwg基名>.dst-viewframes.json`（沿用既有 `.dst-layout-names.json` 约定），
UTF-8 无 BOM。

```json
{
  "version": 1,
  "dwg": "RQ-002-006 现状燃气管道平面图.dwg",
  "layout": "002 现状燃气管道平面图 (一)",
  "frames": [
    {
      "handle": "2A1F",
      "closed": true,
      "vertex_count": 4,
      "corners": [[1024.0, 2048.0], [1224.0, 2048.0], [1224.0, 2148.0], [1024.0, 2148.0]],
      "aabb": {"min": [1024.0, 2048.0], "max": [1224.0, 2148.0],
                "cx": 1124.0, "cy": 2098.0, "w": 200.0, "h": 100.0},
      "area": 20000.0,
      "edge_angles": [0.0, 1.5707963267948966, 3.141592653589793, 4.71238898038469],
      "long_edge":  {"length": 200.0, "angle": 0.0},
      "short_edge": {"length": 100.0, "angle": 1.5707963267948966},
      "inside_block": {"name": "TK-A1", "attributes": {}},
      "inside_texts": [],
      "order_key": null
    }
  ],
  "count": 12,
  "diagnostics": []
}
```

要点：

- 全部几何为 **WCS + 标量**，不含任何 CAD 对象引用（领域层可直接用）。
- `order_key` **仅供预览**，不写库；生产路径不依赖它。
- 多段线守卫必须收紧（§6.10）：要求 `Closed == true` **且** `vertex_count == 4`，四条边两两垂直，
  边长有下限，并做自交/零长度向量检查（原实现 `!= 4 && !Closed` 会放过两类非法输入）。
- 浮点数用不变式格式输出（不使用会随区域设置变化的格式），避免精度打印差异影响 §A.4 的指纹。

**稳定诊断码**

| 码 | 含义 |
| --- | --- |
| `VIEWFRAME_LAYER_MISSING` | 指定图层不存在 |
| `VIEWFRAME_NONE_ON_LAYER` | 图层存在但无封闭多边形 |
| `VIEWFRAME_NOT_CLOSED` | 多边形未闭合 |
| `VIEWFRAME_VERTEX_COUNT` | 顶点数 ≠ 4 |
| `VIEWFRAME_NOT_RECTANGLE` | 四边不两两垂直 / 零长度边 |
| `VIEWFRAME_AREA_TOO_SMALL` | 面积低于下限（防误选图框内小矩形） |
| `VIEWFRAME_LAYER_ARG_INVALID` | 图层名含不安全字符 |

## A.3 `DstCreateViews` 契约

**输入**：Manager 生成的固定路径映射文件 `<dwg基名>.dst-create-views.json`。

```json
{
  "version": 1,
  "request_id": "9f1c…",
  "order_mode": "linear",
  "u_cs": {
    "convention": "dcs_x_is_bottom_edge",
    "twist_sign": 1,
    "twist_offset": 0.0,
    "center_transform": "target_is_frame_center"
  },
  "unit_basis": { "model_unit": "m", "paper_unit": "mm", "scale_denominator": 1000 },
  "frame_count": 12,
  "views": [
    {
      "view_number": "002",
      "frame_handle": "2A1F",
      "frame_key": { "cx": 1124.0, "cy": 2098.0, "w": 200.0, "h": 100.0,
                     "theta_min": 0.0, "area": 20000.0 },
      "frame_hash": "sha256:…",
      "target": [1124.0, 2098.0, 0.0],
      "view_direction": [0.0, 0.0, 1.0],
      "twist": 0.5235987755982988,
      "view_center": [0.0, 0.0],
      "width": 200.0,
      "height": 100.0,
      "ucs": { "origin": [1024.0, 2048.0, 0.0],
               "x_axis": [0.8660254037844387, 0.5, 0.0],
               "y_axis": [-0.5, 0.8660254037844387, 0.0] },
      "layer_state": "ACAD_VIEWS_002",
      "expected_viewport": { "paper_center": [210.0, 148.5],
                              "paper_width": 841.0, "paper_height": 420.5 }
    }
  ]
}
```

**输出**：回执 JSON

```json
{
  "version": 1,
  "request_id": "9f1c…",
  "created":   [{ "view_number": "002", "view_handle": "5C1D", "layer_state": "ACAD_VIEWS_002" }],
  "updated":   [],
  "skipped":   [],
  "verify": {
    "bijection_ok": true,
    "ratio_ok": true,
    "width_over_view_width": 4.205,
    "height_over_view_height": 4.205,
    "readback": [{ "view_number": "002", "twist": 0.5235987755982988,
                   "view_center": [0.0, 0.0], "view_height": 100.0 }]
  },
  "diagnostics": []
}
```

**稳定诊断码**

| 码 | 含义 |
| --- | --- |
| `VIEW_FRAME_HANDLE_INVALID` | 句柄不存在 / 不是该图层上的闭合矩形 |
| `VIEW_FRAME_KEY_MISMATCH` | 当前矩形与 `frame_key` 超出容差（图框被移动 / 替换） |
| `VIEW_FRAME_COUNT_MISMATCH` | 当前矩形总数 ≠ `frame_count` |
| `VIEW_VIEWTARGET_INVALID` | `target` 非有限值 / 与矩形中心不符 |
| `VIEW_VIEWDIRECTION_INVALID` | 视线方向非单位向量或为零向量 |
| `VIEW_TWIST_OUT_OF_RANGE` | `twist` 不在 [0, 2π) |
| `VIEW_RATIO_MISMATCH` | **§6.20 自检等式失败 ⇒ 朝向或 twist 可疑（阻断）** |
| `VIEW_BIPOSECTION_FAILED` | 视图与矩形无法一一对应（阻断） |
| `LAYER_STATE_SAVE_FAILED` | 图层状态保存失败 |
| `UCS_APPLY_FAILED` | `UcsPerViewport` / `Ucs` 设置失败 |
| `VIEW_WRITE_ORDER_INVALID` | 输入 JSON 结构非法（fail-closed，不部分应用） |

**写入语义**

- 按 `view_number` **先删同名视图再建**（与 legacy 一致，保证幂等）。
- 全部校验失败则**整体不写**（fail-closed），不部分应用。
- 写库后不 QSAVE，由既有 staging + 发布事务负责落盘（与 DST 发布同一套回滚语义）。

## A.4 `frame_key` / `frame_hash`：可容差比较的几何指纹

**问题**：句柄会随编辑变化；浮点打印有差异；顶点顺序/起点可能变。

**规范量**（与顶点顺序、起点、朝向都无关）：

```
frame_key = { cx, cy, w, h, theta_min, area }        ← 全部为浮点数（可做容差比较）
  cx, cy      AABB 中心（WCS）
  w, h        AABB 宽高
  theta_min   4 条边方向角先对 π/2 取模再取最小值（消除 90° 倍数与旋转方向歧义）
  area        多边形面积

frame_hash = "sha256:" + sha256("F|{}|{}|{}|{}|{}|{}".format(
                  round(cx*1e6), round(cy*1e6), round(w*1e6),
                  round(h*1e6),  round(theta_min*1e6), round(area*1e6)))
```

要点：

- 用 **AABB 中心/宽高**而不是顶点——消除顶点顺序与起点差异。
- 用 **`theta_min`（模 π/2 归一）**——消除 90° 倍数与旋转方向歧义。
  → 这样"**朝向设错**"不会被指纹掩盖，而是被 §6.20 的宽高比等式抓出来（两者职责分离）。
- **帧指纹不含句柄**（句柄进映射文件但不进指纹）。
- **不能只存哈希**：哈希无法做容差比较。所以同时存 `frame_key`（比较用）与 `frame_hash`（日志/审计用）。

**匹配算法**（`match_bijection`）

```
1) 先按 frame_hash 做精确匹配
2) 剩余做容差匹配：keys_match(rel=1e-4, abs=1e-6)，按"距离最近的先配"
3) 仍剩余的 → 报 VIEW_FRAME_KEY_MISMATCH / VIEW_BIPOSECTION_FAILED
4) 任一步出现多对多歧义 → 整体阻断
```

## A.5 twist 标定常量（不写死在代码里）

因为符号约定无法从文档或静态阅读确定（§6.15），把它做成**声明式配置**而不是代码常量：

```json
"u_cs": {
  "convention": "dcs_x_is_bottom_edge" | "autocad_native",
  "twist_sign": 1,
  "twist_offset": 0.0,
  "center_transform": "target_is_frame_center"
}
```

| `convention` | 含义 | 手算 |
| --- | --- | --- |
| `autocad_native` | 用 `acedSetCurrentView(pVwRec, pVP)` 把 view 记录直接应用到视口，**DCS 换算由 AutoCAD 完成** | 不做 |
| `dcs_x_is_bottom_edge` | 自己算：DCS 的 X 轴 = 矩形底边方向，配合 `twist_sign` / `twist_offset` 修正 | 做 |

**标定步骤（即 V8）**

```
1. 造已知样本：底边与 X 轴成 30°、200×100 的矩形，target = 矩形中心
2. 用 twist_sign = +1 建一次视口
3. 回读：ViewTwist / ViewCenter / ViewHeight / Width / Height，
         并用 GetViewportBoundsInMS 反算视口的模型空间范围
4. 三条判据：
   ① 反算范围 == 原矩形（容差内）
   ② Width / ViewWidth == Height / ViewHeight   （§6.20）
   ③ 底边在视口里呈水平
5. 不成立 → 改 twist_sign = -1 重跑；仍不成立 → 查 twist_offset / convention
6. 标定结果写入标准或项目配置（**双版本 2016 / 2020 各自标定**）
```

> **为什么必须是配置而不是常量**：符号约定是 AutoCAD 的实现细节，双版本可能不同、未来版本可能变；
> 且它属于"项目/标准的出图规则"，放进标准才可审计、可回滚。

## A.6 领域层纯函数签名（`src/dst_manager/domain/`）

依赖方向契约：**不依赖 FastAPI / SQLAlchemy / 文件系统 / AutoCAD 进程**。

```python
# dst_manager/domain/view_frames.py
"""视图框 → 命名视图的确定性规划（纯函数）。"""

@dataclass(frozen=True, slots=True)
class FrameGeometry:
    """插件回读的一个视图框（全为 WCS 与标量，无 CAD 类型）。"""
    handle: str
    corners: tuple[tuple[float, float], ...]
    aabb_center: tuple[float, float]
    aabb_size: tuple[float, float]
    edge_angles: tuple[float, ...]
    area: float
    inside_block_name: str | None = None
    inside_texts: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class FrameKey:
    cx: float; cy: float; w: float; h: float; theta_min: float; area: float

@dataclass(frozen=True, slots=True)
class SheetRef:
    """恢复侧的对齐键：图纸集里一张图纸的图号与顺序。"""
    sheet_number: str
    order_index: int
    layout_name: str | None = None

@dataclass(frozen=True, slots=True)
class UnitBasis:
    model_unit: Literal["m", "mm"]
    paper_unit: Literal["m", "mm"]
    scale_denominator: int | None      # 1:N 的 N；None ⇒ 由图幅内框长 / 视图宽 推导

@dataclass(frozen=True, slots=True)
class OrientationPolicy:
    mode: Literal["linear", "grid", "manual"]
    centerline: tuple[tuple[float, float], ...] | None = None
    row_direction: Literal["top_down", "bottom_up"] = "top_down"
    column_direction: Literal["left_right", "right_left"] = "left_right"
    band_tolerance_ratio: float = 0.5
    horizontal_edge_tolerance_deg: float = 45.0

@dataclass(frozen=True, slots=True)
class UcsDefinition:
    origin: tuple[float, float, float]
    x_axis: tuple[float, float, float]
    y_axis: tuple[float, float, float]

@dataclass(frozen=True, slots=True)
class PlannedView:
    """可直接序列化为 §A.3 的 views[*]（除 paper_* 需另算）。"""
    view_number: str            # = 图号 = ViewTableRecord.Name
    frame_handle: str
    frame_key: FrameKey
    frame_hash: str
    target: tuple[float, float, float]
    view_direction: tuple[float, float, float]
    twist: float                # 弧度
    view_center: tuple[float, float]   # 恒为 (0.0, 0.0)
    width: float                # 模型单位
    height: float
    ucs: UcsDefinition
    layer_state_name: str

@dataclass(frozen=True, slots=True)
class PlanDiagnostic:
    code: str
    severity: Severity
    detail: str
    frame_handle: str | None = None
    sheet_number: str | None = None

# ---- 指纹 ----
def frame_key(frame: FrameGeometry) -> FrameKey: ...
def frame_hash(key: FrameKey) -> str: ...
def keys_match(a: FrameKey, b: FrameKey, *, rel: float = 1e-4, abs_: float = 1e-6) -> bool: ...
def match_bijection(
    snapshot: Sequence[FrameKey], current: Sequence[FrameKey], **tol
) -> tuple[tuple[int, int], ...]: ...

# ---- 排序 ----
def order_frames_linear(
    frames: Sequence[FrameGeometry],
    centerline: Sequence[tuple[float, float]],
    *, ascending: bool = True,
) -> tuple[tuple[FrameGeometry, float], ...]: ...      # → [(frame, 里程)], 已排序
def order_frames_grid(
    frames: Sequence[FrameGeometry], policy: OrientationPolicy
) -> tuple[FrameGeometry, ...]: ...
def order_frames(
    frames: Sequence[FrameGeometry], policy: OrientationPolicy
) -> tuple[FrameGeometry, ...]: ...                    # 门面：linear → grid → manual

# ---- 朝向 ----
def bottom_edge_direction(
    frame: FrameGeometry, policy: OrientationPolicy,
    *, station: float | None = None,
) -> float: ...                                        # 底边方向角（弧度, WCS, [0, 2π)）
def resolve_flip(
    frame: FrameGeometry, neighbour: FrameGeometry | None,
    direction: float, *, ascending: bool = True,
) -> bool: ...                                         # X 正向是否与排序增量反向

# ---- 规划门面 ----
def plan_view_records(
    frames: Sequence[FrameGeometry],
    sheets: Sequence[SheetRef],
    policy: OrientationPolicy,
    u_cs: UcsConvention,
    unit_basis: UnitBasis,
) -> tuple[tuple[PlannedView, ...], tuple[PlanDiagnostic, ...]]: ...

def check_ratio(
    view: PlannedView, paper_width: float, paper_height: float
) -> bool: ...                                         # §6.20 自检等式
```

**与九步流程的字段映射（可逐项核对）**

| §6.18 步骤 | 契约字段 | 校验点 |
| --- | --- | --- |
| 1 读矩形 | `FrameGeometry`（`DstListViewFrames` 输出） | 闭合 / 4 顶点 / 垂直 / 面积下限 |
| 2 定相机 | `PlannedView.target` / `view_direction` / `twist` | `target` == 矩形 AABB 中心；`twist` ∈ [0, 2π) |
| 3 定取景框 | `PlannedView.view_center` / `width` / `height` | `view_center` 恒为 (0,0)；宽高与 AABB 一致 |
| 4 存 UCS + 图层状态 | `PlannedView.ucs` / `layer_state_name` | 命名 `ACAD_VIEWS_<图号>` 唯一 |
| 5 打开布局纸空间 BTR | 不在契约里（插件内部） | — |
| 6 摆窗户 | `expected_viewport.*` | `Width / ViewWidth == Height / ViewHeight` |
| 7 装相机 | 第 2、3 步字段 | 回读四量 == 请求值 |
| 8 收尾 | `UcsPerViewport` / `LayerState` / 非矩形剪裁 | `UCS_APPLY_FAILED` 等诊断 |
| 9 回读校验 | 回执 `verify.bijection_ok` / `ratio_ok` | 双射 + 自检等式 |

## A.7 安全边界与不变量

- 命令参数一律经既有 `encode_scr_argument` 同款不安全字符拒绝；图层名走受控字符集。
- JSON 输入只从 Manager 生成的**固定路径**读取，**不接受用户文本拼接为命令/路径**。
- **插件不读不写 DST**；`unit_basis` / `scale_denominator` / `order_mode` / `u_cs` 全部由 Manager 传入。
- 两个命令都登记进现有固定命令集，不引入自由命令。
- 只读命令不改 DWG、不更新文件时间戳；写入命令走既有 staging + 发布事务与回滚语义。
- 任何校验失败 **fail-closed**（整体不写），不部分应用。

## A.8 待裁决项（阻塞实现）

| # | 待裁决 | 谁定 | 对应验证 |
| --- | --- | --- | --- |
| 1 | `twist_sign` 的标定值 | 真机 | V8 |
| 2 | 能否走 `convention = autocad_native`（`acedSetCurrentView` 可用性） | 真机 | V8 |
| 3 | `unit_basis` 的实际口径（模型 m / 图纸 mm ？） | 用户 | V1 |
| 4 | `frame_key` 容差取值（1e-4 / 1e-6 是否合适） | 真机 | V1 / V7 |
| 5 | 是顺带建视口（`expected_viewport`）还是只建命名视图、视口由布局替换流程负责 | 用户 | — |
| 6 | 双版本（2016 / 2020）是否各自需要独立标定 | 真机 | V8 |

---

# 附录 B：twist 标定真机核对表（V8）

> **用途：** 附录 A 的 `u_cs.twist_sign` / `twist_offset` 无法从文档或静态阅读确定（§6.15），
> 本附录给出**可逐项打勾、可留证**的标定流程。
> **适用范围：** 只标定"DCS 约定与 twist 符号"，不验证视口重建的其它属性。

## B.1 前置条件

| # | 项 | 要求 | 已备？ |
| --- | --- | --- | --- |
| 1 | AutoCAD 版本 | 2016（R20.1）与 2020（R23.1）**各跑一遇**，分别记录 | ☐ |
| 2 | 运行方式 | 优先 Core Console + Worker 插件；无则桌面 AutoCAD 手工执行 | ☐ |
| 3 | 插件 | 含 `DstCreateViews` 与回读命令的构建（或等价手工操作） | ☐ |
| 4 | 样本 DWG | 新建空图（无图框、无视口干扰） | ☐ |
| 5 | 单位口径 | 记录 `INSUNITS` 与 `MEASUREMENT`（附录 A 待裁决项 3） | ☐ |
| 6 | 图幅内框 | 标定样本**人为取 400 × 200**（不要求真实图幅，只要求宽高比自洽） | ☐ |
| 7 | 不对称内容 | 在矩形内放一段水平文字（如 `CAL-30`）或一个箭头（判据 C 用） | ☐ |

## B.2 标定样本（8 个已知量，可直接键入）

底边与 X 轴成 **30°**、尺寸 **200 × 100**（模型单位），左下角取 **(1000, 2000)**：

```
u_R = (cos30°, sin30°) = (0.8660254037844387, 0.5)
u_U = (−sin30°, cos30°) = (−0.5, 0.8660254037844387)

P1 = (1000.0000000, 2000.0000000)   ← 左下（起点）
P2 = (1173.2050808, 2100.0000000)
P3 = (1123.2050808, 2186.6025404)
P4 = ( 950.0000000, 2086.6025404)

矩形中心 = (1061.6025404, 2093.3012702)      ← 也等于 AABB 中心，无歧义
AABB     = (950.0000000, 2000.0000000) – (1173.2050808, 2186.6025404)
AABB 宽高 = 223.2050808 × 186.6025404        ← 注意：比 200×100 大，因为矩形是斜的
面积     = 20000.0000000
四边方向角 = 30° / 120° / 210° / 300°  ⇒ 对 π/2 取模后均为 30°
           ⇒ theta_min = 30°（与朝向、起点、顶点顺序无关）
```

**请求值**（第一次尝试）：

```
target          = (1061.6025404, 2093.3012702, 0)
view_direction  = (0, 0, 1)
twist           = +0.5235987755982988   (twist_sign = +1)
view_center     = (0.0, 0.0)            (center_transform = target_is_frame_center)
width / height  = 200.0 / 100.0
Scale = 400 / 200 = 2.0  ⇒  视口纸空间 400.0 × 200.0
```

## B.3 执行步骤

```
Step 1  在样本 DWG 里按 B.2 画出矩形，放到约定图层；内侧放一段水平文字/箭头
Step 2  记录 INSUNITS / MEASUREMENT，并截图存档（模板编号：V8-00）
Step 3  以 u_cs = { convention: dcs_x_is_bottom_edge, twist_sign: +1, twist_offset: 0 }
        建立命名视图（或直接建视口），target / twist / width / height 取 B.2 请求值
Step 4  回读六个量：TwistAngle · ViewCenter · ViewHeight · Width（纸） · Height（纸） · ViewWidth
Step 5  做判据 A（定向角点）→ 判据 B（宽高比）→ 判据 C（目视）
Step 6  若 A 不通过：改 twist_sign = −1 重跑 Step 3–5
Step 7  若仍不通过：查 twist_offset（以 5° 步进扫）与 convention；仍不行则记录为
        “本版本不支持手算”，改走 convention = autocad_native
Step 8  把通过的一组写进标准/项目配置，本表连同截图一并归档（双版本各一份）
```

> **切换版时必须重跑**：不要把 2016 的标定值直接用在 2020 上（附录 A 待裁决项 6）。

## B.4 三条判据（及各自的职责边界）

### 判据 A：定向角点比对（唯一能把 twist 全部错误抓全的客观判据）

把 DCS 窗口四角按 `target` + `twist` 映回 WCS，必须逐个命中矩形四角：

```
窗口角 (u, v) → WCS = target + u · u_R(twist) + v · u_U(twist)

期望（twist 正确时）：
  (+100, +50) → P3 = (1123.2050808, 2186.6025404)
  (+100, −50) → P2 = (1173.2050808, 2100.0000000)
  (−100, +50) → P4 = ( 950.0000000, 2086.6025404)
  (−100, −50) → P1 = (1000.0000000, 2000.0000000)

容差：相对 1e-6 / 绝对 1e-6
```

| 情形 | 角点比对 | 说明 |
| --- | --- | --- |
| twist = +30°（正确） | ✅ 全中 | — |
| twist = −30°（符号反） | ❌ | 得到的是相对矩形转了 −60° 的另一个矩形 |
| twist = +120°（差 90°） | ❌ | 宽高互换位置 |

> ⚠️ **不能用 AABB 代替角点**：`w(θ)=W|cosθ|+H|sinθ|` 对 θ 对称，**+30° 与 −30° 的 AABB 完全相同**
> （都是 223.2050808 × 186.6025404）。所以“反算包围盒相等”**不能**作为朝向正确的证据。

### 判据 B：宽高比自洽（辅助，不抓 twist）

```
Width / ViewWidth  ==  Height / ViewHeight== 2.0
```

它验证的是"**图幅内框宽高比 == 声明视图宽高比**"。因为 `ViewWidth/ViewHeight` 是请求里写进去的，
它**总能相等**，所以只能抓图幅 / 视口尺寸不自洽或 Manager 算错 `paper_height`，**不抓朝向**。

### 判据 C：目视（判据 A 通过后的最终确认）

样本内侧的水平文字/箭头在视口中应**水平可读**；若歪 60°，说明符号反。
这是最直观的入眼确认，也是唯一能发现“A 通过但物理上仍然反了”之类意外的手段（尽管按 A 的推导不应出现）。

## B.5 记录表（打印或复制到备忘）

| 项 | `twist_sign = +1` | `twist_sign = −1` | 通过？ |
| --- | --- | --- | --- |
| 回读 `TwistAngle`（rad / deg） | | | |
| A：定向角点是否命中 P1–P4 | ☐ | ☐ | |
| B：`Width/ViewWidth` 与 `Height/ViewHeight` | | | |
| C：文字是否水平（图号 V8-01/02） | ☐ | ☐ | |
| `twist_offset` 扫描范围与结果 | | | |
| `convention = autocad_native` 是否可用 | ☐ | ☐ | |
| AutoCAD 版本 / 构建号 | 2016:  | 2020:  | |
| 结论：采用的 `twist_sign` / `twist_offset` | | | |

## B.6 常见失败模式与排查

| 现象 | 可能原因 | 排查 |
| --- | --- | --- |
| 角点全中，但视口里图是歪的 60° | 判据 A 用了错误的 `u_R/u_U` 基（例如把 `u_U` 取成了顺时针） | 检查 `u_U = (−sinθ, cosθ)` 而非 `(sinθ, −cosθ)` |
| 角点全不中，且偏 60° | `twist_sign` 反了 | 切 −1 重跑 |
| 角点全不中，偏 90° | 把“宽高”对应到了短边（底边方向取错） | 检查底边规则（§6.14）与图幅长宽比消歧 |
| 角点差一个固定平移 | `ViewTarget` 不是矩形中心（或 `view_center` 不是 (0,0)） | 检查 `center_transform` |
| 角点中但视口纸空间尺寸不对 | `unit_basis` 口径错，或 `Scale` 算错 | 对照 B.4 判据 B 与附录 A `unit_basis` |
| 建模期就报 `VIEW_RATIO_MISMATCH` | 图幅内框宽高比 ≠ 视图框宽高比 | 修正图幅内框或矩形取值 |
| 回读 `TwistAngle` 与请求不同 | 符号被 AutoCAD 归一化（如 −30° → 330°） | 比较时统一归一化到 [0, 2π) |

## B.7 结论落点

通过的组合写到**标准 / 项目配置**的 `u_cs` 字段（附录 A.5），而不是代码常量：

```json
"u_cs": {
  "convention": "dcs_x_is_bottom_edge",
  "twist_sign": -1,
  "twist_offset": 0.0,
  "center_transform": "target_is_frame_center",
  "calibrated": { "autocad": "2020", "build": "R23.1", "date": "YYYY-MM-DD", "evidence": ["V8-01", "V8-02"] }
}
```

建议在配置里**同时保留 `calibrated` 溯源字段**（版本 / 构建号 / 日期 / 证据编号），使该值可审计、可回滚。

## B.8 需留存的证据

- ☐ `V8-00` 样本布置截图（含文字/箭头）
- ☐ `V8-01` `twist_sign = +1` 的视口截图
- ☐ `V8-02` `twist_sign = −1` 的视口截图
- ☐ 两次的四角点回算结果（可用回执 JSON 的 `verify.readback`）
- ☐ `INSUNITS` / `MEASUREMENT` / 图幅内框取值
- ☐ 双版本各自的记录表（B.5）

> 本节证据为真机操作产物，本轮（2026-10-01）**未执行**；待具备 AutoCAD 2016/2020 环境时按本表逐项完成。

