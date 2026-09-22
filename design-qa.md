# DST Manager 视觉验收记录

## SPEC-DM-016 欢迎页 Demo（2026-09-22）

final result: passed

### 对照证据

- 源视觉真值：[生产欢迎页深色截图](docs/dst-manager/specs/assets/SPEC-DM-016/production/g4-09-welcome-dark-1440x900.png)，1440×900。
- 实现截图：[欢迎页 Demo 深色 1440×900](docs/dst-manager/mockups/SPEC-DM-016-welcome-demo-dark-1440x900.png)；响应式证据：[浅色 900×768](docs/dst-manager/mockups/SPEC-DM-016-welcome-demo-light-900x768.png)。
- CSS 视口与截图输出均为 1440×900；浏览器报告 `devicePixelRatio = 1.5`，截图已由浏览器归一为 CSS 视口像素。补充验证 900×768，文档宽度恰为 900，无横向滚动。
- 状态：深色默认态；另验证 DST 类型错误/成功、创建向导不可用说明、标准包预检错误/成功、浅色主题和窄视口单列态。

### 全图与重点区域比较

- 全图比较：顶部应用栏、深色画布、卡片边框、蓝色主动作、圆角和字体层级继承冻结生产截图。实现按 SPEC-DM-016 §4.1 把旧单卡欢迎页扩展为约 2:1 双栏，属于已确认的信息架构变更；打开 DST 仍保持唯一主强调动作。
- 重点区域无需额外裁剪：页面只有一个完整欢迎区，1440×900 全图可清晰判断标题、主辅栏比例、按钮层级、说明文本和边界提示。
- 字体与排版：沿用 `Inter`、`Microsoft YaHei` 和系统字体；主标题、卡片标题、正文、辅助说明层级明确，无异常截断。
- 间距与布局：双栏宽度约 709:355，16px 间距；900×768 改为单列，主任务顶部为 176px，辅任务顶部为 591px，顺序正确。
- 色彩与令牌：深浅主题均沿用生产截图的中性画布、表面、边框和蓝色动作色；错误、成功与说明状态有独立语义色。
- 图片与资产：直接复用仓库现有 `dst-manager-logo-64.png`，未使用占位图、CSS 图形或自制 SVG 替代品牌资产。
- 文案与内容：创建流程明确指向标准选择且无空白回退；导入标准包明确使用 `.dststandard` 文件；最近记录为空时不伪造项目。

### 交互与控制台验证

- DST 文件选择对 `.zip` 返回扩展名错误；有效 `.dst` 显示模拟验证成功并指向工作区。
- 创建新图纸集显示 PLAN-DM-036 未实施、目标步骤为标准选择且无标准回退。
- 标准包路径对 `.zip` 返回错误，对 `.dststandard` 显示预检通过。
- 主题切换和 900×768 主任务优先单列通过；浏览器页面脚本错误为 0。

### 比较历史与结论

首轮全图比较未发现 P0/P1/P2；双栏与旧单卡截图的差异是 SPEC-DM-016 的明确目标，不是实现漂移。无视觉修复轮。P3：900×768 下辅栏需要纵向滚动才能看到全部三项任务，这是主任务优先和无横向滚动约束下的预期行为。

## SPEC-DM-017 标准属性与 DWG 命名 Demo（2026-09-22）

历史结论：passed

### 对照证据

- 源视觉真值：`C:\Users\sonic\AppData\Local\Temp\codex-clipboard-87ad465b-e3b7-43ad-82a3-0d30d931ebf9.png`（用户提供的图纸目录字段浏览器／编辑器／预览结构，2468×986）。
- 实现截图：[DWG 命名 1440×900](docs/dst-manager/mockups/SPEC-DM-017-demo-dwg-naming-1440x900.png)；补充截图：[普通属性 1440×900](docs/dst-manager/mockups/SPEC-DM-017-demo-ordinary-1440x900.png)。
- CSS 视口：1440×900；截图输出 1440×900；浏览器报告 `devicePixelRatio = 1.5`，截图已由浏览器归一为 CSS 视口像素。另验证 900×768 与 450×768（200% 缩放等效窄视口）无整页横向溢出。
- 状态：深色主题；普通属性默认态、枚举编辑、映射编辑、组合编辑、DWG 命名有效态与缺少 `subset.sequence`/`subset.scope` 的 warning 态。

### 全图与重点区域比较

- 全图比较：实现沿用参考图的深色低对比画布、独立卡片、细边框、蓝色选中态与紧凑表单密度；增加六分区标准编辑器外壳属于产品信息架构要求，不是视觉漂移。
- 重点区域比较：已把参考图上半部的“左字段浏览器／右编辑器／下预览”与实现中的 DWG 命名区域裁剪到同一高度并置比较。实现把多行输出列改为规范要求的单行原子令牌编辑器，字段浏览器与预览的相对层级、间距和语义状态保持一致。
- 字体与排版：沿用 `Inter`、`Microsoft YaHei`、系统字体和等宽代码字体；标题、正文、辅助说明与令牌层级清晰，无异常换行或截断。
- 间距与布局：1440×900 主从分栏稳定；900×768 无水平溢出，组合模态框完整落在视口内；450×768 自动改为单列与横向分区导航。
- 色彩与令牌：画布、表面、边框、蓝色动作、绿色有效、黄色 warning、红色危险操作与既有 DST Manager 深色风格一致。
- 图片与资产：参考与实现均不依赖内容图片；本 Demo 未以 CSS 图形、占位图片或自制 SVG 替代可见资产。
- 文案与内容：字段、作用域、类型、系统保留字段、风险说明和示例值均与 SPEC-DM-017 一致。

### 交互与控制台验证

- 枚举值改名后保存，关联映射显示“待确认”；新增枚举行保留尚未提交的当前输入。
- sheetset 映射只列出合法的 sheetset 普通枚举源，映射表按 3 个枚举项预填且源值只读。
- 组合编辑器可从字段浏览器插入 `sheetset.专业名称`，预览由 `001 管道平面图` 更新为 `001 管道平面图燃气`。
- DWG 命名默认预览为 `RQ-001-003 示例子集.dwg`；载入风险示例后显示“可能产生重名” warning。
- 浏览器页面脚本错误：0。浏览器自身的 Statsig 初始化 warning 与页面实现无关。

### 比较历史与结论

首轮全图比较确认布局、颜色和字体基线一致；重点区域比较确认字段浏览器、编辑器、预览三段结构符合参考。未发现 P0/P1/P2 差异，因此无需视觉修复轮。保留一个 P3：参考图在超宽画布下信息密度更高，而本 Demo 优先匹配标准编辑器的 1440×900 与 900×768 目标视口。

## 历史记录：PLAN-DM-017 图纸工作区视觉验收

历史结论：passed

本记录取代此前 PLAN-DM-015 的视觉通过结论。历史检查范围不足，已被用户真实桌面复验推翻；历史过程见[实施评审](.planning/memos/dst-manager/PLAN-DM-015-sheets-workspace-ui-review.md)。当前以 [PLAN-DM-017](.planning/plans/dst-manager/PLAN-DM-017-sheets-visual-convergence.md) 的实际验证为准。

## 对照范围与限制

- 现有参考为 [1440×900 浅色默认态](.planning/memos/dst-manager/assets/PLAN-DM-015-qa-reference-1440x900.png)，来自 SPEC-DM-009 Demo 的历史渲染。
- 实现截图仅使用虚构夹具，不保存真实客户路径、DST 或 DWG 内容。
- Browser URL 安全策略拒绝打开本地 Demo，并明确禁止改用其他入口绕过，因此本次不重新生成 Demo 参考。
- 深色主题、三类表单、hover、选中和任务抽屉缺少匹配参考图。实现截图及自动化通过不能替代同状态视觉比较，不能宣称 P0/P1/P2 已全面清零。

## 实施与行为验证

已收敛局部控件令牌、独立编辑/列表卡片、38px 表单、确定列宽与内部滚动、树和表格交互背景；任务面板采用 48px 常驻入口栏及覆盖抽屉。计算样式、单元格边界、四宽双主题抽屉几何和滚动保持均有自动化覆盖。完整命令和计数统一记录在计划的“实际验证”，不复制历史通过数。

## 验收结论

- 2026-09-05，用户基于真实桌面连续复验、逐项反馈及修正后的界面，明确确认 PLAN-DM-017 可以完成；本轮视觉验收通过，并关闭 PLAN-DM-015 的 S-07。
- Browser 无法重新渲染本地 Demo、部分状态缺少匹配参考图的限制作为验收过程记录保留；最终结论以用户对真实桌面最终实现的确认及本轮自动化证据为准。
- 在真实 Windows 桌面壳完成 Explorer 选中 DST 的 S-09 验收；浏览器夹具和壳桥 mock 不替代此项。
- S-09 不属于 PLAN-DM-017，PLAN-DM-015 因该项继续保持 `active`。

## 本次截图与比较结果

1440×900 浅色默认参考与最终实现已在同一次比较输入中核对：画布间隔、独立树/列表卡片、表头及行分隔线可见；实现保留既有 320px 可调树宽、搜索/选择操作和固定列宽，因此相较 Demo 列表起点更靠右，操作列在内部横向滚动后可达。这些差异有行为证据，不能直接推导其他状态视觉通过。19 张实现图均已检查：三类表单与列表独立，长表单主体内部滚动且页脚保留；浅深主题的 hover/选中背景可见，抽屉覆盖主区且底部动作仍可见。

| 状态 | 浅色实现 | 深色实现 |
|---|---|---|
| 1440×900 default | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/default-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/default-1440x900-dark.png) |
| 1440×900 edit-subset | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/edit-subset-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/edit-subset-1440x900-dark.png) |
| 1440×900 insert-sheet | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/insert-sheet-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/insert-sheet-1440x900-dark.png) |
| 1440×900 insert-subset | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/insert-subset-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/insert-subset-1440x900-dark.png) |
| 1440×900 hover | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/hover-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/hover-1440x900-dark.png) |
| 1440×900 selected | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/selected-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/selected-1440x900-dark.png) |
| 1440×900 overlay | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1440x900-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1440x900-dark.png) |
| 1024×768 overlay | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1024x768-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1024x768-dark.png) |
| 1120×768 overlay | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1120x768-light.png) | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-1120x768-dark.png) |
| 900×768 overlay | 本计划未要求 | [截图](.planning/memos/dst-manager/assets/PLAN-DM-017/overlay-900x768-dark.png) |

## PLAN-DM-016 属性页遗留复评清单（Task 6/7 复评入口）

以下偏离来自 Task 3 实现，均有真实回归约束支撑，暂缓至页面组合（Task 6）与视觉收敛（Task 7）时统一裁决。Task 6（页面组合）复评结论如下，Task 7 视觉收敛时复核第 1 条的最终视觉呈现：

1. **"更新图纸集 / 放弃本区输入"按钮位于值面板标题行右侧 —— 保留（有意差异）**：Task 6 起值面板支持折叠（默认展开、切工作区重置展开），面板标题行是折叠后唯一常驻的操作与状态层（dirty/pending/error 计数、"加入草稿"摘要与两个按钮同层展示）；移到 Demo 的卡片底部会让折叠态失去全部操作入口，且重现原偏离记录中 TaskOverlay 抽屉（fixed 右侧 390px）遮挡底部按钮导致的 3 个 main.spec 既有用例回归。
2. **"加入草稿：共 N 项，其中 M 项当前未显示"摘要行 —— 已解决**：Task 6 将摘要移入值面板标题行动作区（`.submit-hint`，紧邻"更新图纸集"按钮），满足 SPEC-DM-010 §5.2 "提交按钮旁"；面板底部 `.local-actions` 已删除，`properties-values.spec` 断言同步迁移，且折叠后摘要仍可见。
3. **`button.link` 已在 fix round 1 修复，升为 36px 普通档**（min-height 36px、8px 横向留白、不透明语义背景 `--color-bg-surface`）：34px 档仅限工具栏紧凑按钮，值面板行内文字操作按钮按 `.properties-view button` 36px 基线执行，`sheets-visual-regressions` "点击留白"用例（浅/深双主题）已恢复通过。

复评时逐项决定：保留（记录为有意差异）或调整；调整不得破坏 main.spec 既有流程几何。

## PLAN-DM-016 追加遗留项（Task 7 裁决产出）

4. **共享外壳 200% 缩放横向溢出适配**：Task 7 实测 topbar/dock 在 200% 缩放下产生整页横向溢出（图纸页同现状，PLAN-DM-017 之前既有）。计划 Task 7 Step 2 的"整页无横向溢出"在 200% 缩放档收窄为属性页区域自身（已双处留痕：properties-layout.spec.ts 注释 + QA 备忘第 41 行）；规范 P-07 的整页义务仅约束四个未缩放视口，未违反。后续：另立任务适配外壳 200% 缩放，并补图纸页/外壳在 zoom 下的整页溢出持久回归测试（当前图纸页侧无任何持久佐证）。

## PLAN-DM-016 视觉核对追加观察（2026-09-06 用户确认 passed 时登记）

QA 备忘 14 项已由控制器代用户逐对核对（28 张 PNG，浅/深全覆盖）并经用户裁决通过；以下观察项不阻塞验收，列为后续跟进候选：

5. **定义表「删除」按钮强调度**：SPEC-DM-010 §4.1 要求低强调危险文字按钮；现实现为 danger 文字 + 边框按钮，视觉略重于 Demo 纯文字样式。待裁决：接受现状或去除边框降为纯文字。
6. **定义表表头纵向不吸附**：页面纵向滚动经过定义表时表头随内容滚走（单主滚动区设计下表格无自身纵向滚动区域）。SPEC §4.1「表头保持可见」按横向滚动语境理解可满足；是否需要纵向吸附（如 `position: sticky` 贴 topbar 下缘）另议。
