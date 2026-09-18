# PLAN-DM-034 视觉证据与持久化登记（Task 8 G8 设计 QA）

本目录登记 PLAN-DM-034（前端文本编辑状态与提交动作对齐，[SPEC-DM-015](../../../../../docs/dst-manager/specs/SPEC-DM-015-frontend-text-edit-state-contract.md)）G8 阶段产出的 6 张正交证据截图，以及浏览器 200% 缩放自动检查结果。

- **生成方式**：全部截图来自**真实 dev app 渲染**（Vite dev server + 真实测试后端，`web/tests/e2e/` 既有 Playwright 夹具注入虚构数据），不是手工拼装 DOM。生成用临时 spec `web/tests/e2e/plan-dm-034-evidence.spec.ts` 在证据落盘后删除，不入库；状态断言（dirty class、徽标文字、按钮 aria 语义、主题属性）先于截图执行，保证截图时刻就是要登记的状态。
- **生成命令**（在仓库根执行）：
  - `rtk npm --prefix web run test:e2e -- plan-dm-034-evidence.spec.ts` → 8 passed (12.0s)：6 张证据 + 2 项 200% 缩放检查（Z1/Z2）。
  - 首轮后对 E1/E5 补了一次 `scrollIntoViewIfNeeded` 让状态文字入镜，重跑 `rtk npm --prefix web run test:e2e -- plan-dm-034-evidence.spec.ts -g "E1|E5"` → 2 passed (7.6s)，最终入库的 6 张均来自通过运行。
- **视口口径**：`1440` = 1440×1000（仓库 G8 基准视口惯例，见 `sheet-catalog-visual-evidence.spec.ts`）；`900` = 900×700（最小支持视口惯例）。
- **对应验证**：本目录截图是静态证据；同状态的交互行为断言（clean 语义禁用守卫、revert 归零、dirty+invalid 优先级、焦点归还等）由任务 2～6 的 e2e 用例承担，在全量 `test:e2e` 门禁中执行。

## 证据清单

| 文件 | 页面 / 组件 | 夹具 | 主题 | 视口 | 登记状态 | 生成用例 | SPEC-DM-015 条款 |
|---|---|---|---|---|---|---|---|
| `sheets-dirty-invalid-light-1440.png` | 图纸页属性编辑（`SheetPropertyEditor`） | `fixtures/sheets.ts` `installSheetsFixture` + `failDraftSave`（图幅 PROPERTY_VALIDATION「值无效」）；偏好快照 `ui_theme=light` | 浅色 | 1440×1000 | `dirty-invalid`：图幅 A2 红色错误边框优先，琥珀「尚未加入草稿（仅本会话保留）」文字保留，错误摘要「图幅：值无效」可见，页脚「已修改 1 项 · 加入草稿失败，可修正后重试」 | `E1 sheets-dirty-invalid-light-1440` | §4.1 字段级琥珀+文字；§4.3 错误优先、修改文字保留；§2.1 草稿流文案 |
| `properties-three-states-dark-1440.png` | 属性页属性值（`PropertyValuePanel`） | `installSheetsFixture` + 33 项虚构 sheetset 属性 + `PENDING_DRAFT`（工程名称预置草稿投影）+ `failDraftSave`（项目编号「演示校验错误」） | 深色 | 1440×1000 | 三态并存：工程名称蓝色「待写入」、项目编号红色错误（待写入徽标+错误文字保留）、设计阶段琥珀 dirty「未加入草稿」；顶部徽标「未加入草稿 1 项 / 待写入 2 项 / 错误 1 项」 | `E2 properties-three-states-dark-1440` | §4.1/§4.3 三态视觉与优先级；§2.1「待写入」与「未加入草稿」并存；§6 页面裁决 |
| `settings-general-dirty-light-900.png` | 设置中心常规设置（`SettingsDialog`） | 真实后端（契约红线不 mock `/api/settings`），`writeSettingsFile({ui_locale, cad_max_parallel}, r101)` | 浅色 | 900×700 | dirty：CAD 超时行琥珀脏标记（600→840），「已保存」pill 消失，保存按钮解除 `aria-disabled` 可执行 | `E3 settings-general-dirty-light-900` | §4.1 字段行级琥珀；§5.1/§5.2 clean 语义禁用与 dirty 可执行 |
| `extensions-generated-invalid-dark-900.png` | 扩展配置生成式表单（`ExtensionSettingsHost` + `GeneratedExtensionSettingsForm`） | `fixtures/extensions.ts` `installExtensionSettings`（batch_limit max=200）+ 虚构 generated 扩展「图框批量更新」；偏好快照 `ui_theme=dark` | 深色 | 900×700 | `dirty-invalid`：batch_limit=999 保存 422 后行 `dirty`+`error`，红边框优先、「有未保存修改」文字保留、「1-200」错误与错误摘要横幅可见，保存原生 disabled | `E4 extensions-generated-invalid-dark-900` | §4.1/§4.3 错误优先、修改文字保留；§5.1 invalid 不可执行（强阻断保持原生 disabled） |
| `extensions-custom-filter-dirty-light-1440.png` | 扩展配置自定义面板（`SheetCatalogSettingsPanel` 输出图纸过滤） | `installExtensionSettings({schemaVersion:2, value:{user_templates:[标准目录]}})` + `extensionSummary()` | 浅色 | 1440×1000 | 字段级 dirty：输出过滤「草图」琥珀边框 + 可见「有未保存修改」徽标 + hint 共存，模板栏保持中性（字段级与模板级不互相替代） | `E5 extensions-custom-filter-dirty-light-1440` | §4.1 字段级提示 + `aria-describedby` 关联；§6 扩展配置裁决 |
| `catalog-template-dirty-dark-1440.png` | 图纸目录模板栏（`TemplateBar`） | `fixtures/sheetCatalog.ts` `installSheetCatalogFixture`（用户模板「标准目录」+ 偏好指向）；偏好快照 `ui_theme=dark` | 深色 | 1440×1000 | 模板级 dirty：模板栏警示徽标「有未保存修改」（琥珀语义令牌，`role="status"`），列名 图号→图纸编号A，保存修改按钮可执行；列输入框不铺 dirty 底色（§4.2 裁决） | `E6 catalog-template-dirty-dark-1440` | §4.2 分组级徽标；§5.2 clean 语义禁用（对照：clean 态显示中性「已保存」） |

## 200% 缩放自动检查（G8 响应式证据）

- **方法**：浏览器模拟——Playwright `browser.newContext({viewport: 720×500, deviceScaleFactor: 2})`，即 CSS 视口减半 + 每.CSS 像素 2 设备像素渲染，等效浏览器 200% 缩放下的布局与渲染压力。**它只属于 G8 响应式证据，不冒充 G9 的真实 Windows 桌面缩放截图**（GUIDE-DM-001 G9 仍按原口径待人工执行）。
- **Z1 常规设置 dirty（浅色）**：通过。断言：页面无横向滚动（`scrollWidth ≤ clientWidth`）；CAD 超时行 dirty 琥珀保持可见；保存按钮 dirty 态可执行；`Tab` 键盘聚焦后 `outline-style ≠ none` 且 `outline-width > 0`（焦点环在 200% 下可辨识）。
- **Z2 图纸目录模板 dirty 徽标（深色）**：通过。断言：页面无横向滚动；模板栏「有未保存修改」警示徽标可见且文字正确；保存修改按钮可执行。
- 覆盖范围说明：两项抽查覆盖了字段级提示（普通表单）与模板级徽标（分组级）两种层级、浅/深两种主题；其余三个页面未单独跑 200% 用例，其最小视口（900×700）行为由 E3/E4 及各页面 visual-evidence spec 覆盖。

## 键盘与焦点验证口径（诚实声明）

brief 中「手工键盘检查 Tab、Enter、Space、Esc、错误聚焦和保存后焦点归还」的人手操作部分**未以真人手工形式执行**；等价验证来自任务 1～6 e2e 中的 **Playwright 自动键盘验证**（`press("Enter"/"Space")`、`focus()`/`toBeFocused()`、force click + 请求计数、Esc 关闭与焦点归还断言），全量 `test:e2e` 门禁通过即为证据。对应代表用例：

- clean 主动作 Enter/Space/force click 不产生写请求：`sheets-editing.spec.ts`「初始加入草稿语义禁用…」、`properties-values.spec.ts`「clean 初始态加入草稿语义禁用…」、`settings-dialog.spec.ts`「clean 语义禁用…」、`sheet-catalog.spec.ts`「clean：中性已保存徽标与语义禁用保存按钮…」；
- 错误聚焦：`settings-dialog.spec.ts`「422 结构化错误：错误摘要聚焦并链接字段」、`extensions-settings.spec.ts`（保存 422 后错误摘要取得焦点）；
- 保存后焦点归还：`settings-dialog.spec.ts`「保存成功后焦点回到保存按钮且处于可聚焦 clean 态」；
- Esc 关闭/归还焦点：`settings-dialog.spec.ts`「焦点圈闭与归还」、`extensions-settings.spec.ts`「Esc 与遮罩在子视图内等价于返回扩展列表」。

## G9 真实 Windows 桌面检查

**待人工执行（未运行）**。真实 Windows 桌面壳下五处页面的 clean/dirty/revert、键盘焦点、浅深主题与 100/125/150/200% 缩放检查需要用户在真实桌面环境操作，本次验收未执行；PLAN-DM-034 状态保持 `proposed`，待用户完成 G9 后再关闭。
