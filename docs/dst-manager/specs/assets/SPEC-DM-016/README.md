# SPEC-DM-016 视觉证据与验收记录（PLAN-DM-035 Task 11）

> 本文件是 SPEC-DM-016 的证据目录索引（证据清单、逐对裁决、G9 清单），随
> [SPEC-DM-016](../../SPEC-DM-016-drawing-standard-management-ui.md)（status: accepted）与
> [PLAN-DM-035](../../../../../.planning/plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md)
> （status: completed）一同维护；无独立文档 ID，不进入正式文档编号序列。

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

未设置该环境变量时只产出测试附件，不改写本目录（避免常规回归覆盖验收资产）。

抓图稳定性措施：固定时钟（`page.clock.setFixedTime("2026-09-22T10:00:00")`，使资产检查时间
戳可复现）、`animations: "disabled"`、等待 `document.fonts.ready`、抓图前 blur 掉活动焦点
（消除光标闪烁/焦点环造成的局部像素差）、鼠标归位到 (0,0)（消除悬停态）。全部状态使用
`web/tests/e2e/fixtures/standards.ts` 的虚构夹具，不含真实客户路径或工程内容。

## 二、G4 冻结状态集（1440×900 浅色为基准）

| 文件 | 状态 |
| --- | --- |
| `g4-01-welcome-light-1440x900.png` | 欢迎页（打开 DST 为主任务，标准管理为次级入口） |
| `g4-02-library-light-1440x900.png` | 标准库主从分栏（官方 2.1.0 / 用户 2.0.0 / 草稿 1 三条） |
| `g4-03-properties-light-1440x900.png` | 编辑器·属性定义（三条属性，含枚举与图幅）——旧状态，见下方状态变更说明 |
| `g4-04-mapping-light-1440x900.png` | 字段映射（一条映射规则 + 三行专业映射）——旧状态 |
| `g4-05-composition-light-1440x900.png` | 字段组合派生与 DWG 命名（片段 + 示例结果）——旧状态 |
| `g4-06-assets-light-1440x900.png` | 模板资产（检查通过：声明 A2/A3 与实际一致） |
| `g4-07-publish-error-light-1440x900.png` | 发布检查页·含错误（映射表未覆盖源值，发布禁用） |
| `g4-08-publish-success-light-1440x900.png` | 发布成功后的新版本只读详情 |
| `g4-09-welcome-dark-1440x900.png` | 补充：欢迎页深色 |
| `g4-10-library-dark-1440x900.png` | 补充：标准库深色 |
| `g4-11-publish-error-dark-1440x900.png` | 补充：发布错误页深色 |
| `g4-12-mapping-narrow-light-900x768.png` | 补充：字段映射 900×768 窄视口（无横向溢出）——旧状态 |

SPEC-DM-016 §12.2 要求「欢迎页、标准库、字段映射和发布页至少各有浅色标准视口、深色或窄视口
补充状态」：对应 `g4-09`（欢迎页深色）、`g4-10`（标准库深色）、`g4-12`（字段映射窄视口）、
`g4-11`（发布页深色）。

> **状态变更（PLAN-DM-038，2026-09-22）**：属性定义、字段映射与字段组合三个状态已由
> [SPEC-DM-017](../../SPEC-DM-017-standard-properties-and-dwg-naming.md) 的六分区取代
> （普通属性 / 派生属性 / DWG 命名）。**目录中现有的 `g4-03`/`g4-04`/`g4-05`/`g4-12`
> 仍是旧状态的冻结件，尚未按新状态重新生成**：`standards-visual-evidence.spec.ts` 已改为
> 输出 `g4-03-ordinary-…`/`g4-04-derived-…`/`g4-05-dwg-naming-…`/`g4-12-dwg-naming-narrow-…`，
> 需要设置 `DST_MANAGER_STANDARDS_EVIDENCE=g4`（G8 为 `production`）重跑该 spec 才会落盘，
> 重跑前上述四个旧文件与 README 表格保持一一对应。`g4-01`/`g4-02`/`g4-06`～`g4-11`
> 的状态不变；旧的三分区状态在产品中已不存在，重跑后即可删除旧文件并把表格换为新名。

## 三、G8 逐对裁决

`production/` 中的 12 张与上表同名同状态，由同一次夹具数据、同主题、同视口、同时钟生成，
逐对比对工具与结果：

| 比对 | 结果 |
| --- | --- |
| 12 对（同名逐张） | 12/12 **像素完全一致**（SHA-256 相同） |

比对方法：`sha256` 逐对比较；若出现差异，用本目录留档的裁剪工具（解码 PNG 并输出差异包围盒）
定位差异区域后再裁决。首轮 G4 抓图曾出现 `g4-02-library` 的 19 像素差（12×12 包围盒，位于左栏
搜索标签文字处）；定位为活动焦点/光标类渲染层差异，按上文在抓图前 blur 活动焦点后差异消失，
两组证据重抓后 12/12 完全一致。**结论：G8 与 G4 在数据、状态、主题、视口四个维度无差异，
无未关闭视觉差异。**

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
