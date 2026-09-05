# PLAN-DM-016 属性页分区编辑 · 设计 QA 备忘（视觉基线与同状态证据）

日期：2026-09-06。任务：PLAN-DM-016 Task 7（视觉基线、同状态证据与回归）。
基准：[SPEC-DM-010 属性页 Demo](../../docs/dst-manager/mockups/SPEC-DM-010-properties-demo.html)（卡片层级与比例）+ 用户确认的生产控件密度（38px 输入 / 36px 普通按钮 / 34px 紧凑工具档）。

**当前状态：`pending`（待人工确认）。** 按计划 Step 5，只有用户完成同状态对比并确认后本备忘才可标记 `passed`；未确认时计划保持 `active`。自动截图与计算样式断言不替代真实视觉验收（键盘焦点、Esc、焦点归还、200% 缩放与长文本完整读取需人工复核）。

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
| 卡片层级 | 三卡纵排；1px 边框 + 浅阴影 + 10px 圆角 | 三卡纵排；1px 边框 + `--shadow-1` + `--radius-lg`（12px） | 有意：圆角取语义令牌 `--radius-lg`，不复制演示原值 | 待人工确认 |
| 标题栏 | `card-head` min-height 60px | 三面板 `.panel-head` min-height 60px（折叠态不变） | 一致 | 待人工确认 |
| 两列节奏 | `repeat(2,minmax(0,1fr))` 拉伸、列距 32px | `repeat(2,minmax(240px,360px))` 起始对齐、`--space-3/--space-5` 间距 | 有意：已确认生产输入 38px 密度与可读性上限，保持 Task 3 决定 | 待人工确认 |
| 单列断点 | 视口 ≤900px 降一列 | 视口 ≤900px 降一列（本次由 700px 对齐到 900px）；另有容器 <512px 兜底（200% 缩放/极窄容器） | 一致 + 生产增强 | 待人工确认 |
| 状态徽标 | 琥珀未加入草稿 / 蓝待写入 / 红错误 pill | `.flag.dirty/pending/error`，颜色逐一来自 `--color-warning(-bg)/--color-info(-bg)/--color-danger(-bg)`（自动断言） | 一致 | 待人工确认 |
| 渐进展开 | 定义默认折叠、CSV 按需、导入区开关 | 相同（会话态在 usePropertiesWorkspace） | 一致 | 待人工确认 |
| 控件密度 | 输入/选择器 36px、按钮 min 34px | 输入/选择器 38px、普通按钮 ≥36px | 有意：生产密度以用户确认的 38/36 为准，Demo 36px 输入仅比例参考 | 待人工确认 |
| 34px 紧凑工具档 / 图标按钮 | Demo 存在 34px 档与 quiet 图标按钮 | 属性页当前无 34px 紧凑工具按钮、无图标按钮；断言维持「按钮 ≥36px、图标按钮若引入须 ≥36×36」下限 | 有意：34px 档在属性页无使用场景，未引入 | 待人工确认 |
| 定义表横向溢出 | 无 sticky 操作列；窄屏换行不溢出 | 容器不足时冻结右缘「操作」列 + 不透明表头 + 分隔阴影；无溢出时普通列无阴影（自动断言） | 有意：SPEC-DM-010 P-02/P-14 要求生产实现冻结列 | 待人工确认 |
| 焦点 / 禁用 | 蓝色焦点环、禁用降透明度 | 焦点环 `--color-focus` 2px、禁用 opacity .5 + not-allowed（自动断言，浅/深主题） | 一致 | 待人工确认 |
| CSV 折叠死键（遗留 1） | — | 已修复：面板折叠时「导入 / 导出」按钮禁用（菜单目标在隐藏面板体内） | 行为修复（最小 UI 修复，经控制器确认范围） | 待人工确认 |
| button 内 h2（遗留 2） | — | 已修复：三面板标题改 `span.head-title`，面板名由 section `aria-label` 与按钮 `aria-label` 提供 | 行为修复（最小 UI 修复） | 待人工确认 |
| 卡片间距（遗留 3） | 卡片间距 16px | 已修复：`.properties-view` 间距改用 `--space-4`，移除 `.definition-panel` 旧 `margin-bottom`（原可见间距 32px）；断言改读 row-gap 并校验相邻卡片可见间距 =16px | 行为修复 | 待人工确认 |
| 200% 缩放整页溢出 | Demo 缩放下内容换行避让 | 属性页区域自身无横向溢出、值网格降一列（自动断言）；**整页级溢出来自共享外壳（topbar/dock 内容不随缩放压缩），图纸页在 200% 缩放下现状相同** | 有意（范围裁决）：外壳修复属全局计划范围，本任务禁止改外壳/图纸页样式 | 待人工确认（外壳项建议另立任务） |

## 会话态 rebuild 语义核实（遗留 5）

结论：**正式执行写入后，属性页会话折叠/查询/导入区确实被重置**。链路：`execute()` 成功 → `discardDraft()` + `refreshWorkspace()` 重载工作区（新 `revision_id`）→ `usePropertiesWorkspace` 的 watch 以 `ws.id:ws.revision_id` 为签名判定基准重建 → `rebuild()` → `resetSessionState()`（定义折叠、值展开、CSV 导入区关闭、查询/页码清零）。普通提交（加入草稿）与草稿保存只更新投影、不改变 `revision_id`，走 `syncFromProjection()` 保留会话态。该重置与 P-09「基准重建重置会话态、输入不跨基准保留」一致，本任务不作行为变更；若产品上希望正式写入后保留折叠偏好，另行立项。

## 自动验证

- `rtk npm --prefix web run test:e2e -- tests/e2e/properties-layout.spec.ts tests/e2e/properties-visual-evidence.spec.ts --workers=1`：24/24 通过（先红后绿：红项为卡片间距 32px、900px 未降一列、200% 缩放溢出、对齐行选择器错误）。
- 既有属性页回归（values/csv/workspace/definitions/buffer/model）：62/62 通过。
- Step 6 回归矩阵与生产构建结果见任务报告。

## 边界

- 本任务不改交互逻辑（遗留 1/2 的最小 UI 修复除外），视觉收敛限定属性页 scoped 样式；图纸页组件未改动。
- 证据全部为虚构数据；生产截图经 Playwright 夹具注入，不含本地路径之外的用户内容（topbar 显示夹具虚构 DST 路径 `C:\虚构工程\图纸集.dst`）。
- 键盘焦点、Esc、焦点归还、长文本完整读取的自动覆盖在既有 spec（values/workspace/definitions/layout），最终验收仍需人工确认后才能把本备忘标记 `passed`。
