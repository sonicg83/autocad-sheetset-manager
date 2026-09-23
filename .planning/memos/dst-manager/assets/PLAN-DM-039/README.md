# PLAN-DM-039 候选视觉证据与 Demo 对照裁决

本目录登记 PLAN-DM-039（图纸标准平台欢迎页与编辑器视觉收口）Task 4 Step 2–3 的**候选证据**，
用于在晋升 G4/G8 冻结件之前，由用户对照两份权威 Demo 做人工视觉裁决。

候选证据**不是**冻结件：`docs/dst-manager/specs/assets/SPEC-DM-016/` 下的 G4 与
`production/` 在本轮裁决通过前保持旧文件不变。

## 一、生成口径

| 项 | 值 |
| --- | --- |
| 生成 commit | `20c7ac4` 之上（`收敛标准编辑器响应式布局` + 第二轮候选修正：表格标签与欢迎页任务说明） |
| 生成用例 | `web/tests/e2e/standards-visual-evidence.spec.ts`（既有 G4/G8 生成器，同一夹具、同一状态、同一视口） |
| 生成命令 | 在 `web/` 下：`$env:DST_MANAGER_STANDARDS_EVIDENCE = "plan-dm-039"; npx playwright test tests/e2e/standards-visual-evidence.spec.ts --workers=1` |
| 运行结果 | 35 passed / 0 failed（54s） |
| 语言 | `zh-CN`（与 G4/G8 冻结件一致） |
| 视口 | `1440×900`（标准桌面）；`900×768`（最小支持视口） |
| 主题 | 浅色 / 深色（由 `installPreferenceSnapshot` 注入偏好快照，不写真实 settings.json） |
| 固定时钟 | `2026-09-22T10:00:00`（资产检查时间戳可复现） |
| 数据夹具 | `fixtures/standards.ts` 的 `installStandards` 路由 mock + 本 spec 的 `visualDraft()` / `visualDraftWithMappingGap()`：官方 2.1.0、用户 2.0.0、草稿 1（专业/专业代码/图幅/图签四个属性 + 一条布局模板资产声明） |
| 稳定性处理 | 等待字体就绪、清除活动焦点、鼠标归零、禁用动画 |

候选模式只写入本目录，绝不覆盖 `g4` 与 `production`（`EVIDENCE_DIR` 三分支互斥）。

## 二、候选清单

| 候选文件 | 状态 | 权威对照 | 必须确认 |
| --- | --- | --- | --- |
| `g4-01-welcome-light-1440x900.png` | 欢迎页，浅色 1440×900 | SPEC-DM-016 Welcome Demo | 约 2:1 双栏、唯一主动作、三个次级任务、层级与留白 |
| `g4-09-welcome-dark-1440x900.png` | 欢迎页，深色 1440×900 | 同上 | 深色令牌一致、无第二套配色 |
| `g4-02-library-light-1440x900.png` | 标准库主从分栏，浅色 1440×900 | SPEC-DM-016 §5 | 主从分栏、列表密度、未选择时的详情空态 |
| `g4-10-library-dark-1440x900.png` | 标准库，深色 1440×900 | 同上 | 深色下的选中/只读语义仍可辨识 |
| `g4-03-ordinary-light-1440x900.png` | 普通属性，浅色 1440×900 | SPEC-DM-017 Editor Demo | 独立工作台、导航宽度、身份区、八列表格密度 |
| `g4-04-derived-light-1440x900.png` | 派生属性，浅色 1440x900 | SPEC-DM-017 Editor Demo | 七列层级、编辑动作、说明/摘要不抢宽度 |
| `g4-05-dwg-naming-light-1440x900.png` | DWG 命名，浅色 1440×900 | SPEC-DM-017 Editor Demo | 字段浏览器、令牌、示例预览 |
| `g4-12-dwg-naming-narrow-light-900x768.png` | DWG 命名，浅色 900×768 | SPEC-DM-017 Editor Demo（780–1050px 档） | 侧栏保留、字段浏览器与令牌编辑器双列、无页面级横向滚动 |
| `g4-06-assets-light-1440x900.png` | 模板资产，浅色 1440×900 | SPEC-DM-016 §8 | 分类列表 + 检查面板 |
| `g4-07-publish-error-light-1440x900.png` | 发布错误页，浅色 1440×900 | SPEC-DM-016 §9 | 独立检查页、错误计数与跳转入口 |
| `g4-11-publish-error-dark-1440x900.png` | 发布错误页，深色 1440×900 | 同上 | 深色下错误/警告语义仍不只靠颜色 |
| `g4-08-publish-success-light-1440x900.png` | 发布成功只读详情，浅色 1440×900 | SPEC-DM-016 §9.2 | 进入新版本只读详情、不再停留可编辑表单 |

## 三、逐张检查记录（生成者自查）

生成后逐张打开检查空白、裁切、加载中、错误窗口与焦点闪烁：

- 12 张全部有内容，无空白页、无加载中状态、无残留错误窗口；
- 焦点环已在抓图前统一清除，无光标闪烁造成的局部像素差；
- **第一轮候选后按用户裁决修正了两处，本目录已重抓**：
  1. **普通/派生属性表拥挤错位**（用户反馈重点）：单元格内的 UiInput 可见字段标签与表头/列标题重复，
     把行撑高并造成视觉错位。修正：`OrdinaryPropertyEditor` / `DerivedPropertyEditor` 隐藏单元格标签
     （`display: none`）并给输入框补 `aria-label`，列标题由表头唯一承担；同时把 `UiInput` 在单元格内的
     `gap` 归零。修正后行高回到 Demo 的单行密度，八列/七列对齐。
  2. **欢迎页未含任务说明**：对照 SPEC-DM-016 Welcome Demo 补上三个次级任务行的说明文字
     （创建/管理/导入各一行）与底部“最近打开记录为空”说明，任务行改为“标题 + 说明”两行结构。
- **第一轮已修**：900×768 的 DWG 命名状态下，令牌编辑器操作行的「清空」按钮被长提示文字挤成窄条。
  修正：`TokenExpressionEditor` 操作行加 `flex-wrap: wrap`，提示文字加 `--standards-hint-min-width` 下限。
- 用户第一轮裁决意见（原文）：“与设计有偏差，欢迎页参照 SPEC-DM-016 welcome demo，标准编辑参照
  SPEC-DM-017 demo，请以 demo 为准，尤其是‘普通属性’和‘派生属性’的表格排列拥挤错位。”
  本目录为按该意见修正后的第二轮候选。

## 四、用户裁决

**待用户第二轮裁决。** 请对照：

- SPEC-DM-016 Welcome Demo：`docs/dst-manager/mockups/SPEC-DM-016-welcome-demo.html`
- SPEC-DM-017 Editor Demo：`docs/dst-manager/mockups/SPEC-DM-017-standard-properties-and-dwg-naming-demo.html`

裁决结果逐状态记录如下（用户确认前不得晋升 G4/G8）：

| 状态 | 第一轮裁决 | 第二轮裁决（通过 / 否决+差异） | 裁决人 / 日期 |
| --- | --- | --- | --- |
| 欢迎页 1440×900 浅/深 | 否决：未按 Demo（缺任务说明） | 待裁决 | 用户 / 2026-09-23 |
| 普通属性 1440×900 | 否决：表格排列拥挤错位 | 待裁决 | 用户 / 2026-09-23 |
| 派生属性 1440×900 | 否决：表格排列拥挤错位 | 待裁决 | 用户 / 2026-09-23 |
| 标准库 1440×900 浅/深 | 未单独提出 | 待裁决 | — |
| DWG 命名 1440×900 与 900×768 | 未单独提出（已修窄视口操作行） | 待裁决 | — |
| 模板资产 / 发布错误 / 发布成功 | 未单独提出 | 待裁决 | — |

若任一状态被否决，回到所属 Task 修正并重新生成全部受影响候选截图，再重新裁决。
