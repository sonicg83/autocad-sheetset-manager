# PLAN-DM-029 Task 1–11 执行审查报告

## 日期

2026-09-16

## 背景

本备忘记录对 [PLAN-DM-029 前端视觉基础与一致性整改实施计划](../../plans/dst-manager/PLAN-DM-029-frontend-ui-foundations-remediation.md) Task 1–11 执行情况的一次只读审查。审查对象为 worktree `plan-dm-029-frontend-ui-foundations`，用户给出的 Git 范围为基点 `b248ff1396e83ec08cc840ea8e3f057b08106d4e` 至目标 `a92388622a868e827ffcfe5c5057fa3bf6a7b492`。

审查重点包括：计划步骤是否真实落地、前端契约门禁是否覆盖迁移后的组件形态、公共视觉原语与焦点模型是否保持既有行为、页面迁移是否满足尺寸与无障碍基线、`App.vue` 拆分是否保持跨域接线，以及测试、文档和提交台账是否一致。审查过程未修改应用源码、测试或计划正文。

## 审查结论

Task 1–11 主体完成度较高：字体与令牌、样式分层、公共原语、属性/目录/图纸/设置/旧页面迁移、统一焦点工具及 `App.vue` 拆分均已落地，自动化覆盖也有明显增强。未发现 Critical 级的数据损坏、安全或发布风险。

但当前目标提交不建议原样合并，结论为 **With fixes**。审查确认存在 3 项 Important 实现缺口：一个未获 Spec 豁免的小点击目标、一个图纸树鼠标—键盘焦点衔接回归，以及一个组件化输入可绕过静态标签门禁的问题。此外，给定 Head 已包含 19 个 Task 12 提交，且 Task 12 的权威文档状态未完全同步，审查范围和执行台账需要先校正。

## 范围与提交台账

精确 Git 计数如下：

| 范围 | 提交数 | 说明 |
| --- | ---: | --- |
| `b248ff1..a923886` | 135 | 用户给出的完整范围；不是 134 |
| `b248ff1..77c869e` | 116 | Task 1–11 实际终点，`77c869e` 为“关闭 Task 11 并记录评审闭环与后续项” |
| `77c869e..a923886` | 19 | Task 12 的契约硬化、证据盘点、字号责任 K 收口与文档工作 |

因此，`a923886` 不是纯 Task 1–11 交付点。若只评审 Task 1–11，权威范围应止于 `77c869e`；若准备合并 `a923886`，则必须同时把这 19 个 Task 12 提交纳入验收和文档一致性检查。

计划中 Task 1–11 共 97 个步骤，当前全部勾选：

| Task | 已勾选 | 未勾选 |
| --- | ---: | ---: |
| 1 | 10 | 0 |
| 2 | 9 | 0 |
| 3 | 9 | 0 |
| 4 | 7 | 0 |
| 5 | 14 | 0 |
| 6 | 9 | 0 |
| 7 | 8 | 0 |
| 8 | 7 | 0 |
| 9 | 8 | 0 |
| 10 | 7 | 0 |
| 11 | 9 | 0 |

## 做得好的部分

1. UI 契约门禁采用 fail-closed、例外棘轮、陈旧例外拒绝和 CLI 级变异测试，当前 `test:contracts` 实跑为 86/86 passed。
2. 本地 Inter/IBM Plex Mono 字体、`tokens/reset/primitives/legacy` 四层样式入口、三层令牌和本地图标注册表均已落地；构建过程会运行 API、i18n 与 UI 契约检查。
3. `UiButton`、`UiIconButton`、`UiInput`、`UiSelect`、`FormField` 和 `useDialogFocus` 的公共边界清晰，单元测试覆盖唯一实例 ID、焦点圈闭、回焦、单选组和隐藏元素等边界。
4. 属性、图纸目录、图纸与任务浮层、设置中心、欢迎/修订/修复/草稿等旧页面已分阶段迁移，并保存了 29 张持久视觉证据。
5. `App.vue` 从 809 行收敛到 450 行；`WorkspaceShell.vue` 保持纯展示边界，四个业务组合式函数均低于仓库 500 行软上限。
6. 计划没有把未完成的真实桌面验收伪装成完成：Windows WebView2 100/125/150/200% 验收尚未执行，因此计划继续保持 `active`，这一状态判定正确。

## Important 问题

### I1. 条件标签清除按钮仍约 12×12px，未满足 32px 点击下限

位置：

- [`web/src/components/sheets/SheetToolbar.vue`](../../../web/src/components/sheets/SheetToolbar.vue)，模板约第 151 行；
- 同文件 `.chip-clear` 样式约第 200 行；
- [`docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md`](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md) §4.1、§10；
- [`docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md`](../../../docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md) §3。

`.chip-clear` 使用 12px 字号、`padding:0`，没有最小宽高，实际点击面积约为 12×12px。PLAN-DM-029 全局约束和 ARCH-DM-007 都要求全部按钮至少 32px；图标按钮通常还应达到 36×36px。

现有 SPEC-DM-010 豁免只适用于“表头/数据行共享且宽度不超过 112px 的密集表格操作轨”，用于目录页列编辑器的上移、下移和删除按钮。条件标签清除按钮不属于该操作轨，不能沿用这项豁免。例外表虽然诚实记录了该缺口，但记录本身不等于 Spec 批准。

影响：Task 7 的点击目标验收未完全闭合，鼠标精确操作、触屏和高缩放环境下的可用性不足。

建议：把可见 `✕` 与点击盒分离，为按钮提供至少 32×32px 的透明点击区域，同时保持标签胶囊的视觉尺寸；若布局确实无法容纳，应由图纸页对应 Spec 单独批准有界豁免，并补真实几何断言。

### I2. 点击图纸树 chevron 后，roving tabindex 与真实焦点仍留在旧上下文

位置：

- [`web/src/components/sheets/SheetTree.vue`](../../../web/src/components/sheets/SheetTree.vue)，树项点击约第 139 行，chevron 点击约第 149 行；
- [`web/src/components/sheets/SheetTree.test.ts`](../../../web/src/components/sheets/SheetTree.test.ts)，chevron 测试约第 180 行；
- PLAN-DM-029 Task 10 的已知行为差异记录约第 851 行。

迁移前的展开按钮会执行：

```text
focusIndex = index; toggleCollapse(node)
```

迁移后 chevron 是不可聚焦的 `<span>`，点击只执行 `toggleCollapse(node)`。当用户点击另一个子集的 chevron 时：

- 唯一 `tabindex="0"` 仍属于此前节点；
- `<span>` 不会像原生按钮那样取得真实 DOM 焦点；
- 随后使用方向键可能继续操作旧节点，或因为焦点仍在树外而无法进入树的键盘处理。

现有组件测试只验证“点击后展开”，没有验证点击前后的 `tabindex` 所有者和 `document.activeElement`。计划把差异登记为“可能更好”，但未通过用户流程或双向断言证明这一点；对于要求保持用户流程的视觉迁移，不能据此视为已验收。

建议：点击 chevron 时同步更新 `focusIndex` 并把焦点交给对应 `treeitem`；增加“点击非当前节点 chevron 后，该节点成为唯一 `tabindex=0` 且取得焦点”的组件测试，并复跑图纸树 E2E。

### I3. `visible-input-label` 门禁无法检查组件化输入调用点

位置：

- [`web/scripts/check-ui-contracts.mjs`](../../../web/scripts/check-ui-contracts.mjs)，`visible-input-label` 扫描约第 433 行；
- [`web/src/components/ui/UiInput.vue`](../../../web/src/components/ui/UiInput.vue)，可选 `label` prop 约第 17 行；
- [`web/src/components/ui/UiSelect.vue`](../../../web/src/components/ui/UiSelect.vue)；
- [`web/src/components/ui/FormField.vue`](../../../web/src/components/ui/FormField.vue)；
- PLAN-DM-029 Task 12 责任 U。

当前检查器只扫描原始 `<input>` 标签。页面迁移成 `<UiInput>`/`<UiSelect>` 后，检查器只能看到原语组件内部的条件标签，看不到调用方是否传入 `label`，也无法证明调用点是否位于提供关联标签的 `FormField` 中。由于 `UiInput.label` 和 `UiSelect.label` 都是可选的，后续新增一个无标签的 `<UiInput />`，`check:ui` 仍可全绿。

影响：Task 1 的核心门禁承诺没有覆盖迁移后的主流输入形态；静态检查结果不能证明 ARCH-DM-007“所有输入具有可见标签”的完成标准。

建议：扩展 Vue 模板分析，识别 `UiInput`、`UiSelect` 与 `FormField` 的合法组合；至少要求调用点传入非空 `label`，或能静态证明位于提供 `id`/`label[for]` 关联的 `FormField`/外部标签中。同步增加 CLI 级正反夹具与变异测试。

### I4. 当前 Head 的 Task 12 状态与权威文档不一致

位置：

- [`docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md`](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md)，约第 46、177 行；
- [`docs/dst-manager/README.md`](../../../docs/dst-manager/README.md)，约第 7 行；
- [`.planning/plans/dst-manager/README.md`](../../plans/dst-manager/README.md)，约第 23 行；
- 当前 Head 的 `web/src/styles/tokens.css` 与 `web/scripts/ui-contract-exceptions.json`。

Head 已实现责任 K：新增 15/16/17/20px 与 14/18px 语义字号档位，相关 7 条例外也已清除，当前例外表为 7 条。但上述文档仍声明“4 个档位尚未实现”“例外仍为 14 条”，与代码、计划后段和 changelog 相互矛盾。

影响：后续实施者可能重复执行已完成工作，并错误判断 PLAN-DM-029 的剩余关闭条件；这也违反 README 只承担当前状态摘要的文档治理约束。

建议：如果合并目标是 `a923886`，同步把责任 K 标为已闭合、例外更新为 7，并明确仍未完成的硬关闭条件是真实 Windows WebView2 验收及其它已登记待裁项。如果合并目标止于 `77c869e`，则不应携带这 19 个 Task 12 提交。

## Minor 问题

### M1. 新增测试文件超过容量软上限

[`web/src/composables/appComposition.test.ts`](../../../web/src/composables/appComposition.test.ts) 为 957 行，接近仓库约 500 行软上限的两倍。计划已登记该偏离，但当前 Head 尚未拆分。

建议按导航、草稿门禁、生命周期和命令编排拆为独立测试文件；共享 hoisted mock 可抽到测试 helper，避免复制第二份事实源。

### M2. 正式文档的 `updated` 日期未随本轮正文变更同步

ARCH-DM-007、GUIDE-DM-001、GUIDE-DM-002、SPEC-DM-006 和 SPEC-DM-010 均在本范围内增加了 2026-09-15 内容，但 YAML `updated` 仍是更早日期。建议同步实际修订日期，保持追溯信息可信。

### M3. 删除嵌套 chevron 按钮后留下孤儿 i18n 键

`sheets.tree.collapseSubset` 和 `sheets.tree.expandSubset` 已无生产组件调用，只在中英文资源和测试夹具中残留。建议在确定新焦点模型后删除孤儿键，或重新用于树项的可访问说明。

### M4. `git diff --check` 仍有两处提交卫生问题

- `web/src/App.vue:449`：文件末尾多余空行；
- `web/src/assets/fonts/OFL-IBM-Plex-Mono.txt:21`：行尾空格。

两项不影响运行，但应在合并前清理。

## Task 1–11 覆盖与偏离

| Task | 核实结果 |
| --- | --- |
| 1 | 契约检查器、CLI、棘轮和变异测试已完成；组件化输入检测存在责任 U 缺口。 |
| 2 | 字体资产、令牌、样式分层和构建接入已完成。 |
| 3 | 公共原语与统一焦点工具已完成，组件单测较充分。 |
| 4 | 壳层迁移完成；后续已补浏览器几何断言。 |
| 5 | 属性页迁移、状态优先级与视觉证据闭环较完整。 |
| 6 | 目录页迁移完成；32px 密集表格操作轨豁免已写入 SPEC-DM-010。 |
| 7 | 图纸页与浮层迁移主体完成，但约 12×12px 的条件标签清除按钮使点击面积验收未闭合。 |
| 8 | 设置页迁移、焦点和视觉证据覆盖较完整。 |
| 9 | 旧页面、确认模态及错误态迁移总体完成。 |
| 10 | 树与模态焦点工具复用完成，但 chevron 点击改变了鼠标—键盘焦点衔接。 |
| 11 | `App.vue` 拆分达到 450 行目标，接线安全网充分；957 行测试文件偏离容量软上限。 |

## 实际验证

审查期间在 `a923886` 上实际执行：

| 命令 | 结果 |
| --- | --- |
| `rtk npm --prefix web run test:contracts` | EXIT 0，86/86 passed |
| `rtk npm --prefix web run test:unit` | EXIT 0，13 files / 166 passed |
| `rtk npm --prefix web run build` | EXIT 0；API、i18n、UI 契约、`vue-tsc`、Vite build 均通过 |
| `rtk npm --prefix web run test:e2e` | EXIT 0，550 passed / 2 flaky，耗时约 4 分钟 |
| `rtk uv run ruff check .` | EXIT 0 |
| `rtk uv lock --check` | EXIT 0 |
| `rtk uv run pytest -q` | EXIT 1；2 个 `test_setup_bat.py` 中文输出编码断言失败 |
| `rtk git diff --check b248ff1..a923886` | EXIT 非全绿；发现 M4 两处空白问题 |

两条 E2E flaky 都是等待启动引导按钮超时：一条等待“设置”，一条等待“选择 DST 文件”；Playwright 重试后通过，与计划已登记的引导期 flaky 签名一致。

后端 pytest 的两个失败分别是：

- `test_2013_2014_mapped_to_2016_bucket_with_warning`；
- `test_no_autocad_detected_leaves_keys_commented`。

失败原因是当前控制台环境中 `setup.bat` 中文 stdout 被解码为乱码。对主工作区复跑同两项得到相同失败，因此没有证据表明它们由 PLAN-DM-029 分支引入；但在本次审查环境下，不能声称后端全量 pytest 已复现为全绿。

验证完成后 worktree 仍保持干净，未修改用户源码或测试。

## 用户验收补充（2026-09-16，暂不执行）

本节记录审查完成后用户在真实桌面界面继续验收时发现的视觉与布局问题，以及后续归属裁定。它是对原审查结论的补充，不表示代码、Spec、Plan 或测试已经完成相应修改。本轮仅更新本备忘与变更记录。

### 新发现的问题

1. **模态操作按钮的悬停反馈不一致。** 用户最初发现“取消 / 保存”等确认操作按钮缺少期望的悬停阴影；随后确认“展开编辑”对话框中的按钮已有悬停阴影。后续修复应以运行时 computed style 和桌面壳复验为准，统一所有 `.modal-actions` 可用按钮的悬停抬升效果，同时保证禁用按钮不出现误导反馈，不能只根据静态截图推断现状。
2. **表单弹窗的输入区与按钮区缺少垂直间距。** “另存为模板”的模板名称输入框与按钮区贴合，“展开编辑”的 `textarea` 与按钮区也存在同类问题。源码中两处均是表单控件后直接跟随 `.modal-actions`，操作区自身没有上间距。拟采用表单弹窗专用的 16px 语义间距，避免给普通确认文案已有的下间距再次叠加。
3. **属性值面板在宽屏下空间利用不足。** 当前 `.value-grid` 固定为两列 `repeat(2, minmax(240px, 360px))` 并左对齐，因此在全屏桌面窗口右侧形成大面积空白。用户希望增加手动切换 2 列 / 4 列的展示控制，而不是只把既有两列居中。

### 当前跨列规则核实

属性项跨列是明确的实现规则，不是浏览器偶然排版：

- `PropertyValuePanel.vue` 的 `isLong()` 以当前输入值长度大于 40 个字符作为长值判定；
- 图纸集名称始终带 `name` class；长值带 `full` class；
- `.value-item.full, .value-item.name { grid-column: 1 / -1; }` 使两者占满当前网格的全部列；
- 因而用户截图中的“图册全称”是因为值长度超过 40 个字符，在当前两列模式下占据整行。

该规则若不调整，直接增加四列后，长值会从“占两列”扩大为“占满四列”，仍不能达到期望的宽屏密度。后续设计裁定为：普通属性占 1 列；长值固定占 2 列；图纸集名称继续占满整行。这样长值在两列模式下占整行，在四列模式下只占半行。

### 拟纳入 PLAN-DM-029 的处理方式

这些事项不回写为 Task 1–11 的既有成果，也不另起无关联修复；PLAN-DM-029 当前仍为 `active`，且真实 Windows WebView2 验收尚未关闭，后续应作为 **Task 12 用户验收修复轮** 一并处理：

- 在属性值工具区提供可访问的“2 列 / 4 列”展示选择，默认保持 2 列并记忆用户偏好；
- 四列只在可用宽度足够时生效，空间不足时响应式降为两列，窄屏继续降为一列，不产生横向滚动；
- 每列继续保持约 240–360px 的可读宽度，网格在可用区域内居中；不使用会打乱视觉顺序与键盘顺序的 `grid-auto-flow: dense`；
- 统一模态操作按钮的悬停阴影，并为“另存为模板”“展开编辑”等表单弹窗增加独立操作区间距；
- `SPEC-DM-006` 记录模态按钮与表单弹窗间距，`SPEC-DM-010` 把“最多两列”修订为用户可切换 2/4 列并定义跨列、降级规则；PLAN-DM-029 记录验收修复步骤和证据；本备忘只追加后续状态，不改写原审查快照；
- 补充 Playwright 断言，至少覆盖悬停阴影、表单控件与按钮区不重叠、2/4 列切换、长值跨两列、名称整行、窄屏降级及无横向溢出，并在真实桌面壳重新验收。

### 影响边界与当前状态

拟议修改只改变前端视觉反馈和展示偏好，不改变属性原顺序、输入值、草稿语义、API 契约、DST/DWG 内容或发布流程。公共模态样式仍有跨页面回归面，因此必须用公共样式断言和页面级视觉证据共同约束。

**当前状态：仅记录并归档，暂不执行。** 截至本节写入时，没有修改应用源码、测试、SPEC-DM-006、SPEC-DM-010 或 PLAN-DM-029，也没有声称上述问题已经修复。

## 临时结论

PLAN-DM-029 Task 1–11 的核心方向和大部分实施质量可以认可，但“全部关闭”这一表述需要附带边界：Task 7 的点击目标和 Task 10 的鼠标—键盘焦点衔接仍有实际行为缺口，Task 1 的标签门禁也未覆盖迁移后的组件输入。当前 Head 还混入 Task 12 的 19 个提交，不能再按“只完成 Task 1–11”的口径描述。

合并判断为 **With fixes**：先修复 I1–I3，并根据最终合并范围处理 I4；之后重跑契约测试、图纸树组件测试、相关图纸页 E2E、生产构建和 `git diff --check`。真实 Windows WebView2 100/125/150/200% 验收未完成前，PLAN-DM-029 应继续保持 `active`。

## 待跟进事项

1. 为条件标签清除按钮补至少 32×32px 点击区域，或取得图纸页 Spec 的独立有界豁免。
2. 修复 chevron 点击后的 `focusIndex` 与真实 DOM 焦点，并补双向组件测试。
3. 扩展 `visible-input-label` 规则，使其覆盖 `UiInput`/`UiSelect` 调用点和 `FormField` 组合。
4. 决定实际合并边界：Task 1–11 终点 `77c869e`，或包含 Task 12 部分工作的 `a923886`。
5. 若采用 `a923886`，同步 SPEC-DM-006、两个 README 和例外统计。
6. 拆分 `appComposition.test.ts`，清理孤儿 i18n 键和两处空白问题。
7. 在真实 Windows WebView2 壳中执行 100/125/150/200% 验收；125% 必须覆盖属性、目录和图纸三个用户缺陷场景。
8. 后续在 Task 12 用户验收修复轮中处理模态按钮悬停一致性、两个表单弹窗的操作区间距，以及属性值 2/4 列切换；当前仅完成问题归档，尚未实施。

## 修复执行状态（2026-09-16 同日追加；不改写上方审查快照）

依据用户裁定（合并范围取 `a923886` 并同步文档；新问题按 Task 12 用户验收修复轮全部实施；`appComposition.test.ts` 本轮拆分；孤儿 i18n 键删除），待跟进事项处置如下：

1. **I1 条件标签清除按钮**：已修复（可见字形与点击盒分离，`--tap-target-min` 32×32px 点击区，负 margin 保持胶囊视觉尺寸），e2e 补几何断言；未走 Spec 豁免路线。→ 关闭
2. **I2 chevron 焦点衔接**：已修复（`toggleCollapseFromChevron` 同步 roving tabindex 与真实 DOM 焦点），补双向组件测试。→ 关闭
3. **I3 组件化输入门禁（责任 U）**：已闭合（`UiInput`/`UiSelect` 调用点三种合法形态 + `FormField` 缺 label 独立违规；9 组正反夹具 + 1 条 CLI 变异；0 新例外）。→ 关闭
4. **合并边界**：经用户裁定取 `a923886`。→ 关闭
5. **I4 文档同步**：SPEC-DM-006、两个 README 已同步责任 K 闭合与例外 14 → 7。→ 关闭
6. **拆分与卫生**：`appComposition.test.ts` 已按域拆为 4 文件 + 共享夹具模块（断言零改动，168 项全绿）；孤儿 i18n 键已删除；两处空白问题已清理。→ 关闭
7. **真实 Windows WebView2 100/125/150/200% 验收**：仍待用户执行（125% 覆盖属性/目录/图纸三场景）。→ 未关闭
8. **用户验收修复轮**：已实施——模态操作按钮悬停统一（`.modal-danger` 仅抬升不变色，缺 `--color-danger-hover` 令牌，如需变色交 Spec 归属方）、表单弹窗 16px 操作区间距、属性值 2/4 列切换（长值 span 2、名称整行、单列降级退 `auto`）；SPEC-DM-006 §6.2 与 SPEC-DM-010 同步修订，Playwright 断言覆盖悬停、间距、跨列、降级与无横向溢出。→ 已实施，待真实桌面复验

修复轮的提交与门禁实绩见 [PLAN-DM-029](../../plans/dst-manager/PLAN-DM-029-frontend-ui-foundations-remediation.md) T12-5 节与根 `changelog.md`。
