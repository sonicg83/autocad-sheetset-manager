---
id: MEMO-DM-025
title: PLAN-DM-021 G8 设计 QA——多语言生产实现 vs SPEC-DM-013 G4 冻结截图比对
status: final
owners:
  - dst-manager
created: 2026-09-09
updated: 2026-09-09
related:
  - PLAN-DM-021
  - SPEC-DM-013
  - ARCH-DM-005
  - MEMO-DM-024
document_kind: memo
---

# PLAN-DM-021 Task 11 G8 设计 QA 备忘（多语言生产实现 vs G4 冻结基准）

## 元信息

- 日期：2026-09-09
- 执行者：PLAN-DM-021 Task 11 实施代理；最终接受与否由用户在 Task 12 裁决（SPEC-DM-013 §7.2：G8 由用户/验证者确认）。
- 方法：与 G4 相同的虚构数据、视口、主题与状态生成生产截图。前端取 `npm --prefix web run build` 生产产物（`web/dist`，含 check:api + check:i18n + vue-tsc 门禁），经临时静态服务器（`node:http`，仅本机 127.0.0.1，未进入提交树）加载；ShellBridge 以 addInitScript 注入与 e2e 同构的假桥；API（settings 快照 / 工作区打开 / 草稿）全部经 Playwright 路由返回结构化虚构数据，无真实后端、无真实工程数据。采集脚本在验证后已删除，不进入提交树。
- 虚构数据（与 G4 Demo §6.1 相同口径）：图纸集 `市政道路改造图纸集` / `Municipal Road Renewal Drawing Set`，路径 `C:\Projects\Municipal Renewal\Drawing Set.dst`，128 张图纸（表格代表性 3 行 C-001～C-003：道路总体平面图 / 道路纵断面图 / 排水构造详图，DWG `01-General-Plan.dwg` 同构），配置修订 r8，语言字段为用户覆盖（用户覆盖徽章可见）。
- 视口与主题（与两张冻结截图一一对应）：`zh-CN 浅色 1440×900`、`en-US 深色 900×768`；状态均为「工作区已打开 + 设置对话框常规配置（界面语言字段可见、当前语言选中）」。
- 产物：`.planning/memos/dst-manager/assets/PLAN-DM-021/`
  - [production-zh-CN-light-1440x900.png](assets/PLAN-DM-021/production-zh-CN-light-1440x900.png)
  - [production-en-US-dark-900x768.png](assets/PLAN-DM-021/production-en-US-dark-900x768.png)
- 对照冻结图：`docs/dst-manager/specs/assets/SPEC-DM-013/settings-zh-CN-light-1440x900.png`、`docs/dst-manager/specs/assets/SPEC-DM-013/settings-en-US-dark-900x768.png`（commit `3ecb754` 冻结）。

## 逐对裁决

### 对 1：zh-CN 浅色 1440×900（设置常规配置 / 界面语言字段）

| 项 | 结论 | 摘要 |
| --- | --- | --- |
| 应用壳顶栏（品牌 / 工作区名 / DST 状态 / AutoCAD 版本 / 关闭 / 主题 / 设置） | 一致 | 生产顶栏结构与冻结一致；AutoCAD 版本选择器与主题按钮为 SPEC-DM-011 既有壳件，Demo 无（已接受差异 D6） |
| 背景工作区（页签 ① 图纸 / ② 属性 / ③ 修订历史、图纸导航、单表、操作栏 草稿/撤销/重做/预览变更/确认写入） | 一致 | 布局与状态同冻结；用户数据（图纸集名、编号、路径）原样未翻译（I18N-16） |
| 对话框结构（标题+配置修订徽章 / 左侧 常规配置·关于 / 右侧面板 / 页脚 取消·保存） | 一致 | 分区、组标题竖条、行结构（label/控件/foot）与冻结一致 |
| 界面语言字段：跟随系统（当前：简体中文） / 简体中文 / English 单选 | 一致 | 复合标签解析结果、自称形式（简体中文 / English）、选中态（简体中文）与冻结完全对应 |
| 用户覆盖徽章 + 恢复继承 | 一致 | source=file 显示「用户覆盖」，冻结同 |
| 任务执行组（最大并行任务数 4，默认 1–10） | 可接受差异（D2） | Demo 为 4/6/8 下拉；生产为数字输入 + min–max 范围提示 + 默认徽章（PLAN-DM-019 G8 已裁决 `.field-foot` 行内模式为有意设计，MEMO-DM-024 终局裁决沿用） |
| 错误与诊断示例组 | 已接受差异（D1） | Demo 专属脚手架（演示未知错误的本地化摘要 + 可展开原文）；生产对应能力在真实错误路径（错误提示下「原始错误详情」），不作为静态示例展示 |
| 页脚状态（无待保存修改 / 取消 / 保存） | 一致 | 与冻结一致 |

### 对 2：en-US 深色 900×768（同状态英文 + 深色主题）

| 项 | 结论 | 摘要 |
| --- | --- | --- |
| 深色主题令牌（表面 / 边框 / 文字 / 强调色） | 一致 | `html[data-theme=dark]` 语义令牌整套生效，与冻结深色观感一致 |
| 全壳英文切换（顶栏 Open Containing Folder / AutoCAD version / Close / Settings，页签 Sheets/Properties/Revision History，操作栏 Draft 0/0、Undo/Redo/Preview Changes/Confirm Write） | 一致 | 语义键渲染；工作区名「市政道路改造图纸集」、编号、路径保持原样（I18N-16） |
| `<html lang>` | 一致 | 切换后 `lang="en-US"`（自动化断言：i18n-workflows / settings-dialog.spec） |
| 界面语言字段：Follow system (current: English) / 简体中文 / English | 一致 | 系统解析结果与自称形式与冻结一致；英文界面显示 current: English |
| 界面语言字段标签文案 | 可接受差异（D3，待用户确认） | 生产英文标签为 **UI language**（稳定键 `settings.items.uiLocale` 的 G5 冻结译文）；Demo 文案为 **Display language**。语义等价，键名已在 G5 技术映射冻结，改动需同步中英资源与后端 label_key——建议按现状接受，如需逐字对齐交 Task 12 用户裁决 |
| Maximum parallel jobs / CAD timeout (seconds)（数字输入 + 范围提示） | 可接受差异（D2） | 同对 1 D2 |
| 英文长文案换行（对话框内 long hint 完整换行、无省略截断） | 一致 | 900×768 最小视口下标签与提示完整显示（自动化断言：i18n-visual-evidence 长错误用例） |
| 页脚 Cancel / Save | 一致 | 与冻结一致 |

## 取证过程中发现并已修复的缺陷（重取证通过）

- **F1（中）整页横向滚动**：任务浮层收起态侧栏（48px）内容宽 102px 且 `overflow:visible`，使英文界面在 1440×900 / 900×768 / 200% 缩放下 `documentElement.scrollWidth` 均超出视口 54px，违反 I18N-15「无整页横滚」。修复落所属组件 `web/src/layout/TaskOverlay.vue`（`.task-rail` 加 `min-width:0;overflow:hidden`，按钮加 `overflow-wrap:anywhere`，未改全局 `style.css`）。修复后三种组合均断言无整页横滚（自动化守卫：`i18n-visual-evidence.spec.ts`）。
- **F2（低）设置模态 Tab 回绕一拍落到 body**：showModal 原生圈闭在尾元素→首元素回绕时有一拍焦点落到 `body`（Chromium 缺口）。修复落所属组件 `web/src/components/settings/SettingsDialog.vue`（`@keydown` 显式 Tab/Shift+Tab 回绕）；Esc 关闭与焦点归还触发按钮行为不变（自动化守卫：i18n-visual-evidence 键盘用例；settings-dialog.spec 既有 17 例回归通过）。
- **F3（低，Task 10 审查绑定修复）**：`useSheetColumns.ts` 对 `SHEET_PREFERENCES_INVALID` 透传桥原始中文 message，未按 Task 9 错误目录 `message_key` 渲染；改为与 App.vue 一致的 `localizedError(message_key, params, message)` 模式（中英文渲染断言见 sheets-columns.spec.ts，原文不出现）。

F1～F3 修复后均已重新取证：生产截图为修复后产物；`npm --prefix web run test:e2e` 全量 320 passed。

## 自动化证据（Task 11 新增）

- `web/tests/e2e/i18n-workflows.spec.ts`（3 例）：zh-CN 与 en-US 各一遍 启动 → 设置 → 打开 → 图纸 → 属性 → 预览 → 发布 → 任务 → 修订 九域关键矩阵（语义键渲染 + 用户数据原样）；语言切换不变量——切换前后 workspace 标识（DST 路径 title / 顶栏名）、未提交输入、选区、草稿计数、任务状态、修订哈希完全一致，发布不重跑（execute 仅一次）、SSE 事件 URL 不携带语言（I18N-06/12/15/16）。
- `web/tests/e2e/i18n-visual-evidence.spec.ts`（7 例）：1440×900 浅色、900×768 深色（含超长错误：本地化摘要完整可读 + 原文进可展开详情且 `overflow-wrap:anywhere`）、200% 缩放（CDP 等价 720×450 CSS 视口 + 2x 渲染，浏览器 200% 缩放语义）；断言无整页横滚、主操作可达、表格只在自身容器横滚（`overflow-x:auto` 且 `scrollWidth>clientWidth`）；Tab 到达全部主操作、Esc 关闭设置并归还焦点、模态焦点圈闭、422 错误摘要聚焦并链接字段（英文）；状态不只靠颜色——禁用属性 + 文字化原因、草稿计数文本、DST 状态徽章文字、`role=status` 通知、Pending/Blocking 文本徽章（I18N-15、§3.5、§5.3）。
- `web/tests/e2e/sheets-columns.spec.ts`（+2 例）：F3 的中英文本地化渲染断言。

## 结论（供控制器登记，不改 SPEC 门禁表）

**G8 设计 QA：无未关闭 P0/P1。** 两对截图的对话框结构、双语内容、语言选择语义、主题令牌与冻结设计一致或属已接受差异（D1/D2/D6 沿用既有裁决，D5 生产数据口径差异）。一项低优先级文案差异 **D3（UI language vs Display language）** 提请 Task 12 用户裁决后即可登记 G8 通过。真实 WebView2 系统语言、原生文件对话框与打包桌面体验按 SPEC-DM-013 §7.2 属 G9，不在本次范围。

## 遗留观察（不阻塞）

- 生产设置 int 字段为数字输入（Demo 为下拉），来源徽章/范围提示结构沿用 `.field-foot` 模式（MEMO-DM-024 终局裁决为有意偏差）。
- 生产配置修订徽章显示真实「配置修订 r8」，Demo 为「r8 · Demo」脚手架。
- 背景工作区生产为真实单表渲染（子集树显示实际子集计数），Demo 为代表性三行示意；数据口径差异不影响比对项。
