# PLAN-DM-016 属性页分区编辑 · 设计 QA 备忘（视觉基线与同状态证据）

日期：2026-09-06。任务：PLAN-DM-016 Task 7（视觉基线、同状态证据与回归）。
基准：[SPEC-DM-010 属性页 Demo](../../docs/dst-manager/mockups/SPEC-DM-010-properties-demo.html)（卡片层级与比例）+ 用户确认的生产控件密度（38px 输入 / 36px 普通按钮 / 34px 紧凑工具档）。

**当前状态：`passed`（2026-09-06 用户确认）。** 同状态对比由控制器代为执行：逐对读取全部 28 张 PNG（7 状态 × 浅/深主题），逐项结论见下表「验收结论」列，核对中发现的备忘未记载事项记入「核对观察」，用户裁决整体通过并选择不阻塞的观察项（A–D）另列跟进。键盘焦点、Esc、焦点归还、长文本完整读取的自动覆盖在既有 spec（values/workspace/definitions/layout）；200% 缩放外壳项属全局范围，见核对观察 D 与设计 QA 遗留清单。

## 同状态证据索引

全部 PNG 位于 `assets/PLAN-DM-016/`，成对命名（`demo-*` 与 `prod-*`），只使用 `web/tests/e2e/fixtures/properties.ts` 虚构夹具与 Demo 内置虚构数据，不读取用户截图、真实工程或 `sample/`：

| 状态 | 视口 | 文件对（light/dark） |
| --- | --- | --- |
| 默认 | 1440×900 | `demo/prod-default-1440x900-{light,dark}.png` |
| dirty+pending | 1440×900 | `demo/prod-dirty-pending-1440x900-{light,dark}.png` |
| 错误 | 1440×900 | `demo/prod-error-1440x900-{light,dark}.png` |
| 新增字段 | 1440×900 | `demo/prod-add-field-1440x900-{light,dark}.png` |
| CSV | 1440×900 | `demo/prod-csv-1440x900-{light,dark}.png` |
| 窄屏单列 | 900×768 | `demo/prod-narrow-single-column-900x768-{light,dark}.png` |
| 定义表横向溢出（200% 缩放） | 1024×768 | `demo/prod-def-table-overflow-1024x768-{light,dark}.png` |

生产侧由 `web/tests/e2e/properties-visual-evidence.spec.ts` 生成（普通回归只产附件，持久证据为验收时显式复制）；Demo 侧由同视口同状态的临时采集脚本生成（脚本不进入提交树）。

## 逐项对比

| 项 | Demo 基准 | 生产实现 | 差异是否有意 | 验收结论 |
| --- | --- | --- | --- | --- |
| 卡片层级 | 三卡纵排；1px 边框 + 浅阴影 + 10px 圆角 | 三卡纵排；1px 边框 + `--shadow-1` + `--radius-lg`（12px） | 有意：圆角取语义令牌 `--radius-lg`，不复制演示原值 | 一致（2026-09-06 视觉核对） |
| 标题栏 | `card-head` min-height 60px | 三面板 `.panel-head` min-height 60px（折叠态不变） | 一致 | 一致（2026-09-06 视觉核对） |
| 两列节奏 | `repeat(2,minmax(0,1fr))` 拉伸、列距 32px | `repeat(2,minmax(240px,360px))` 起始对齐、`--space-3/--space-5` 间距 | 有意：已确认生产输入 38px 密度与可读性上限，保持 Task 3 决定 | 确认：差异与记载相符，1440 下右侧留白可见 |
| 单列断点 | 视口 ≤900px 降一列 | 视口 ≤900px 降一列（本次由 700px 对齐到 900px）；另有容器 <512px 兜底（200% 缩放/极窄容器） | 一致 + 生产增强 | 确认：900×768 无整页横向溢出，单列由自动化断言覆盖 |
| 状态徽标 | 琥珀未加入草稿 / 蓝待写入 / 红错误 pill | `.flag.dirty/pending/error`，颜色逐一来自 `--color-warning(-bg)/--color-info(-bg)/--color-danger(-bg)`（自动断言） | 一致 | 一致（浅/深主题均逐对核对，文字+颜色双通道） |
| 渐进展开 | 定义默认折叠、CSV 按需、导入区开关 | 相同（会话态在 usePropertiesWorkspace） | 一致 | 一致（生产默认折叠由 properties-workspace 自动断言兜底；prod-default 证据为展开态采集口径，见观察 A） |
| 控件密度 | 输入/选择器 36px、按钮 min 34px | 输入/选择器 38px、普通按钮 ≥36px | 有意：生产密度以用户确认的 38/36 为准，Demo 36px 输入仅比例参考 | 确认：自动化逐元素断言 + 视觉无违例 |
| 34px 紧凑工具档 / 图标按钮 | Demo 存在 34px 档与 quiet 图标按钮 | 属性页当前无 34px 紧凑工具按钮、无图标按钮；断言维持「按钮 ≥36px、图标按钮若引入须 ≥36×36」下限 | 有意：34px 档在属性页无使用场景，未引入 | 确认：截图中无违反下限的元素 |
| 定义表横向溢出 | 无 sticky 操作列；窄屏换行不溢出 | 容器不足时冻结右缘「操作」列 + 不透明表头 + 分隔阴影；无溢出时普通列无阴影（自动断言） | 有意：SPEC-DM-010 P-02/P-14 要求生产实现冻结列 | 确认：200% 下冻结列与分隔线生效，1440/900 无溢出无阴影 |
| 焦点 / 禁用 | 蓝色焦点环、禁用降透明度 | 焦点环 `--color-focus` 2px、禁用 opacity .5 + not-allowed（自动断言，浅/深主题） | 一致 | 确认（焦点环两侧截图一致；禁用态由自动化断言） |
| CSV 折叠死键（遗留 1） | — | 已修复：面板折叠时「导入 / 导出」按钮禁用（菜单目标在隐藏面板体内） | 行为修复（最小 UI 修复，经控制器确认范围） | 确认修复：折叠态菜单不可达，展开态菜单/流程正常 |
| button 内 h2（遗留 2） | — | 已修复：三面板标题改 `span.head-title`，面板名由 section `aria-label` 与按钮 `aria-label` 提供 | 行为修复（最小 UI 修复） | 确认修复：三面板标题渲染正常 |
| 卡片间距（遗留 3） | 卡片间距 16px | 已修复：`.properties-view` 间距改用 `--space-4`，移除 `.definition-panel` 旧 `margin-bottom`（原可见间距 32px）；断言改读 row-gap 并校验相邻卡片可见间距 =16px | 行为修复 | 确认修复：16px 间距两侧节奏一致 |
| 200% 缩放整页溢出 | Demo 缩放下内容换行避让 | 属性页区域自身无横向溢出、值网格降一列（自动断言）；**整页级溢出来自共享外壳（topbar/dock 内容不随缩放压缩），图纸页在 200% 缩放下现状相同** | 有意（范围裁决）：外壳修复属全局计划范围，本任务禁止改外壳/图纸页样式 | 确认：属性页区域无溢出；外壳溢出复现（200% 下 dock「确认写入」按钮右缘裁切），另立任务跟进 |

## 核对观察（2026-09-06，备忘未记载事项）

视觉核对中发现以下备忘未记载事项，经用户裁决均不阻塞本次验收：

- **A（证据采集口径）**：`prod-default-*` 截图由 `openWorkspace()`（properties-visual-evidence.spec.ts:14-19）在展开定义面板并打开「导入 / 导出」菜单后采集，与 demo 默认态（定义折叠 + 值展开）不构成严格同状态；卡片层级/表格样式仍可比，生产「默认折叠」行为由 `properties-workspace.spec` 自动断言兜底。如需严格同状态默认对比，可另补采未展开的 prod 默认图。
- **B（新增区位置与文案）**：demo 新增字段区在表格上方、生产在表格下方（分页之后）；按钮文案 demo 为「字段加入草稿」、生产为「加入草稿」。不影响任何验收准则，接受现状。
- **C（删除按钮强调度，跟进候选）**：SPEC-DM-010 §4.1 要求「删除」为低强调危险文字按钮；生产实现为 danger 文字 + 边框按钮，视觉略重于 demo 的纯文字样式。已列入设计 QA 遗留清单待裁决。
- **D（表头纵向不吸附，跟进候选）**：页面纵向滚动经过定义表时表头随内容滚走（窄屏与 200% 截图均可见）。单主滚动区设计下表格无自身纵向滚动区域，SPEC §4.1「表头保持可见」按横向滚动语境理解可满足（冻结列与不透明表头仅服务横向溢出）；是否需要纵向吸附另议。

> **验收后变更（2026-09-06 同日）**：用户反馈二级菜单多一步操作且桌面壳内下载失效，裁决取消「导入 / 导出」菜单——面板展开后三个操作常驻（SPEC-DM-010 §6 已修订）；逐项对比表「CSV 折叠死键（遗留 1）」所载的禁用修复随之被取代（菜单不复存在，折叠态无死键）。下载失效根因（pywebview 5 默认阻断页面内下载）已修复。本备忘其余记录为验收时点历史，不再更新。

## 会话态 rebuild 语义核实（遗留 5）



结论：**正式执行写入后，属性页会话折叠/查询/导入区确实被重置**。链路：`execute()` 成功 → `discardDraft()` + `refreshWorkspace()` 重载工作区（新 `revision_id`）→ `usePropertiesWorkspace` 的 watch 以 `ws.id:ws.revision_id` 为签名判定基准重建 → `rebuild()` → `resetSessionState()`（定义折叠、值展开、CSV 导入区关闭、查询/页码清零）。普通提交（加入草稿）与草稿保存只更新投影、不改变 `revision_id`，走 `syncFromProjection()` 保留会话态。该重置与 P-09「基准重建重置会话态、输入不跨基准保留」一致，本任务不作行为变更；若产品上希望正式写入后保留折叠偏好，另行立项。

## 自动验证

- `rtk npm --prefix web run test:e2e -- tests/e2e/properties-layout.spec.ts tests/e2e/properties-visual-evidence.spec.ts --workers=1`：24/24 通过（先红后绿：红项为卡片间距 32px、900px 未降一列、200% 缩放溢出、对齐行选择器错误）。
- 既有属性页回归（values/csv/workspace/definitions/buffer/model）：62/62 通过。
- Step 6 回归矩阵与生产构建结果见任务报告。

## 边界

- 本任务不改交互逻辑（遗留 1/2 的最小 UI 修复除外），视觉收敛限定属性页 scoped 样式；图纸页组件未改动。
- 证据全部为虚构数据；生产截图经 Playwright 夹具注入，不含本地路径之外的用户内容（topbar 显示夹具虚构 DST 路径 `C:\虚构工程\图纸集.dst`）。
- 键盘焦点、Esc、焦点归还、长文本完整读取的自动覆盖在既有 spec（values/workspace/definitions/layout）；本备忘已于 2026-09-06 经用户确认标记 `passed`（键盘矩阵人工走查仍按计划 §8.3 由用户执行）。
