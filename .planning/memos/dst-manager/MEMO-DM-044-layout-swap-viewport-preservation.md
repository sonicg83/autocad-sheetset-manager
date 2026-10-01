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
| — | **（已否决）** 模型 XREF + 各阶段图框图纸 | 主 DWG 只放模型，各阶段图框 DWG 自带图框与视口 | 100% | 很高 | 与"一 DWG 一布局 + DST 引用布局 Handle"的既有结构不兼容，等于重做产品模型；且原生 Place View 自带 xref 行为（第七节） |

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
| 5 | 只存 UCS，恢复时不设 `UcsPerViewport / UcsName`、`AnnotationScale`、`VisualStyleId`、前后剪裁 | 参数集补全 | 覆盖不全；这些在 .NET 里均可读写 |
| 6 | 视图名 = 纯数字编号，布局名首段也是编号 | 匹配规则必须与"命名规则统一派生"同源 | 现有布局名由受控规则生成（含范围/后缀），不能在两处各写一份匹配 |
| 7 | 捕获源是模型空间的"视图框"矩形（要求设计人员先画框） | 改为**从布局现有视口反推**（`GetViewportBoundsInMS` 的逆运算） | 用户诉求是"保持设计人员已设好的视口"，不应逼其改工作习惯；首次套图框前捕获即可 |

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

## 六、方案 3（图签块重定义）详解

### 6.1 成立原理

```
标准包布局模板资产
└─ 图签 = 增强属性块（块定义 BlockTableRecord + ATTDEF 列表，字段在 ATTDEF 中）
   └─ 布局内 = BlockReference（块参照）
        视口（AcDbViewport）——不碰
        图签（BlockReference）——只换它的「定义」，不换参照本身
```

`BlockTableRecord`（块定义）是**数据库级**对象，`BlockReference`（块参照）才是布局内实体。
**换定义 → 所有参照自动更新**，参照的 ObjectId、位置、所属布局全不变。

### 6.2 实现机制

| 步 | 动作 | 要点 |
| --- | --- | --- |
| 1 | 把标准资产 DWG 的**同名块定义**克隆进目标 DB | 用 `IdMapping` 一并带入嵌套块、图层、线型、文字样式等依赖；避免交互式 `-INSERT` 重定义 |
| 2 | `ATTSYNC <块名>` 同步属性 | Tag 相同 → **保留实例已有值**；新块多出的 Tag → 用 ATTDEF 的 Default（即字段）初始化；旧块多出的 Tag → 删除 |
| 3 | 若图幅也变，另行 `AcDbPlotSettings::copyFrom` | 图幅 / 图纸尺寸 / 打印样式 / 打印区域属于 `Layout`，**不属于块** |
| 4 | 回读校验 + before/after 哈希 | 走既有发布事务 |

### 6.3 能力边界（须写入 Spec）

| 能管 | 不能管 |
| --- | --- |
| 图签 / 会签栏 / 图框边框（只要是块） | 图幅、页面设置、打印样式（`Layout.PlotSettings`） |
| 图签里的字段（ATTDEF Default） | 布局里**非块**的散落实体（指北针、说明文字） |
| 图签内的静态内容（规范号、版本号、行数） | 视口本身（正因不碰它，才零风险） |
| 嵌套子块（图框 → 内嵌图签） | 图号 / 图名等 DST 属性（本就该改 DST，无需换图） |

### 6.4 五个必须写进设计的坑

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

### 6.5 收益（相对方案 1）

- 视口 **100%** 不动：VP 覆盖、非矩形剪裁、注释比例、锁定全都不用管
- **布局 Handle 不变 → DST 完全不需要回填**（比方案 1 少一整个变更面）
- 图号 / 图名等字段**本就自动求值**，改 DST 属性即可
- 无序列化、无视图/视口往返 → 实现最简、最好测、最易审计

## 七、Callout Block / 视图标签块：概念与实证

### 7.1 四个相邻但不同的概念

| 概念 | 是什么 | 存在哪 | 谁创建 |
| --- | --- | --- | --- |
| **Model View**（模型视图） | 模型空间的命名视图（`VIEW` 命令），**可选带"保存图层快照"** | DWG 的 `ViewTable`（符号表，数据库级） | 设计人员 / legacy `SetViews` |
| **Sheet View**（图纸视图） | 把一个 Model View **放到某张图纸上**的实例：编号、标题、类别 + 那个视口 | DST：`AcSmSheet` → `AcSmSheetViews` → `AcSmSheetView` | SSM 的"放置视图" |
| **View Label Block**（视图标签块） | 放置视图时**自动插在图口左下角**的块，显示该视图编号 / 标题 / 比例 | DST：`AcSmSheetSet` → `AcSmAcDbBlockRecordReference propname="DefLabelBlk"`（**单数，只能挂一个**） | 图纸集属性中指定 |
| **Callout Block**（标注块） | **不是视图**，是"指路牌"块：典型内容 *见 3/A-402*，引用**别的图纸上的视图** | DST：`AcSmSheetSet` → `AcSmCalloutBlocks`（**复数**）；或按视图类别挂 `AcSmViewCategory` → `AcSmCalloutBlockReferences` | 图纸集属性中指定（可多个） |

### 7.2 关键机制：`SheetSetPlaceholder` 字段

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

### 7.3 Callout 块的制作四要点

1. 字段必须插在 **`BATTMAN` → 属性定义 → `Default`**（默认值）里，**绝不能**插在实例的 `Value` 里
2. 属性定义 **`Preset = Yes`**（预设），插入时不提示用户输入
3. 可选勾选 **Associate hyperlink**
4. 块可存为"独立 DWG 文件"，也可存为"某 DWG / DWT 里的块定义"；图纸集属性取用时两种模式：
   `Select the drawing file as a block` 或 `Choose blocks in the drawing file`

### 7.4 使用流程

```
SSM → Sheet Views 选项卡 → 右键某个视图 → Place Callout Block → 在图纸布局上点插入点
（首次会提示先 Select Blocks，把 callout 块挂到图纸集属性上）
```

### 7.5 与图签块的对照

| | 图签块 | Callout 块 |
| --- | --- | --- |
| 作用 | 显示**本图**的信息 | 引用**别的图纸 / 视图** |
| 字段类别 | `SheetSet`（`CurrentSheet*`） | `SheetSetPlaceholder`（`SheetNumber` / `ViewNumber`） |
| 求值时机 | 插入即求值，随 DST 属性自动更新 | 由 SSM 插入时填值 + 建超链接 |
| 挂在哪 | 直接在布局里，标准资产携带 | 图纸集属性（可多个）或视图类别下 |
| 数量 | 不限 | 图纸集级不限；视图类别级按类别挂 |

### 7.6 原生「Place View」不能用来解视口问题

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

## 八、本地真实样本证据（普查）

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

## 九、待确认项（会改变实现细节）

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

## 十、真机验证清单（未执行）

均需在真实 AutoCAD（2016 / 2020 双版本，优先 Core Console）上验证：

1. **量化现状丢失范围**：扩展读取命令，统计现有 rebuild 路径下每布局的视口数、视图参数、
   VP 覆盖层数、纸空间非视口实体数（同时回答第九节第 3、4 点）。
2. **`-LAYOUT _Template` 替换布局后，同 DB 的 `ViewTable` 与 `LayerState` 是否完整存活**
   （预期存活，因二者都是数据库级；须实测确认 `-LAYOUT` 不清符号表 / 扩展字典）。
3. **`RestoreLayerState(name, VP.Id, 1, LayerStateMasks.None)`** 对**新建视口**在双版本是否生效、
   还原结果是否等同捕获时所见（.NET 与 AutoLISP 两条路径分别验证）。
4. **`ViewTableRecord.CenterPoint` 的 DCS / WCS 语义**：legacy 用 `CT.TransformBy(Rotation(TwistAngle))`，
   是否与 `Viewport.ViewCenter` 期望的坐标系一致 —— **全链路最易错处**，须用已知样本做往返一致性验证。
5. **模板布局自带视口**时与重建视口如何共存（先删模板视口 / 复用占位视口）。
6. **图纸集字段在导入的新布局中是否照常求值**（含 DST 回填新 Handle 之后），确认方案 1 的前提假设。
7. **块定义替换 + `ATTSYNC` 后字段是否仍正常求值**，以及人工覆盖过的属性值是否真的会吃掉字段。

## 十一、后续落点建议

| 能力 | 方案 | 风险 | 前置 |
| --- | --- | --- | --- |
| **阶段切换换图签** | **方案 3**：块定义替换 + `ATTSYNC` + 校验 | 低 | 标准侧约定"图签块名 / 角色映射"；体检字段在 `Default` 而非 `Value` |
| 阶段切换含图幅 / 页面设置 | 方案 3 + `PlotSettings.copyFrom` | 中 | 图幅参数从标准派生（已有 `图幅` / `出图比例` 属性可利用） |
| 布局必须整体重建 | **方案 1**：命名视图 + 图层状态（legacy 机制现代化） | 中高 | 5.5 节 7 项改造清单 |
| 图纸交叉引用自动更新 | Callout / Label Block | 中 | 先补 5 类 AcSm 对象进 contract registry |

**推荐的组合策略**：以**方案 3 为主**（覆盖绝大多数阶段差异，零视口风险），**方案 1 为兜底**
（仅在布局/图幅必须重建时启用），Callout 作为独立能力另行立项。

## 十二、来源清单

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

## 十三、本轮未做的事

- 未修改任何产品代码、插件、标准 Schema、DST codec 或测试。
- 未在真实 AutoCAD 上执行任何验证（第十节清单全部待执行）。
- 未立项、未创建 Spec 或 Plan；收敛的业务问题只登记在第九节，未写入 `todos/`。
- 未归档长期知识到 `docs/`（见文首"定位说明"）。
