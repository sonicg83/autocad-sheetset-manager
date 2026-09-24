---
id: PLAN-DM-041
title: 标准包导入受控文件选择修复计划
status: proposed
owners:
- dst-manager
created: 2026-09-24
updated: 2026-09-24
related:
- ARCH-DM-001
- ARCH-DM-007
- SPEC-DM-016
- PLAN-DM-035
- PLAN-DM-039
- PLAN-DM-040
---

# 标准包导入受控文件选择修复计划

> **执行要求：** 实施前阅读 [SPEC-DM-016](../../../docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md)、[ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md)、[ARCH-DM-001](../../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md) 和相关源码、测试。各代码任务先写失败用例并记录 RED，再实现与验证 GREEN；复选框仅在实际完成后勾选。

## 背景与边界

PLAN-DM-039 收口记录 F7：欢迎页称“选择 `.dststandard` 文件”，实际导入弹窗只有路径文本框。标准库入口也进入同一弹窗。宿主 `select_file(file_kind, localized_description)` 已用固定白名单提供原生文件选择，但目前只认 `dst`、`template`、`exe`、`dll`；前端 `ShellFileKind` 同样缺少 `dststandard`。这就是原 F16 的受控选择缺口，直接偏离 SPEC-DM-016 §4.2。现有 `/api/standards/import` 已接收本机路径并由服务端读取、校验、发布门禁后导入；本计划复用该接口，不把浏览器文件输入框伪装成能提供本机绝对路径的选择器。

**目标：** 桌面用户从欢迎页或标准库导入现成 `.dststandard` 包时，能通过原生过滤器选择文件，并在同一导入弹窗内完成预检反馈、失败恢复与成功后的版本定位；浏览器无壳开发态明确提供路径输入回退。补齐该弹窗的焦点和可访问性契约。

**范围：** 仅承接 PLAN-DM-039 F7／原 F16 和导入弹窗自身的焦点缺口。外部 DWG/DWT 加入草稿、包内资产存在性及路径安全门禁、草稿发布与导出由 [PLAN-DM-040](PLAN-DM-040-standard-platform-review-remediation.md) 承接；本计划不改变标准 Schema、包格式和后端最终校验规则。两个计划可分别实施、分别验收；合并时复跑标准包创建与导入的完整闭环。

**预检定义：** 现有导入 API 会在写库前校验包和发布条件。本计划须在界面上区分“正在检查/导入”、包校验失败、身份冲突与成功，并确认失败不产生标准库记录。若实施前发现 SPEC-DM-016 的“进入导入预检”要求独立的人工确认预览，而现有 API 无法满足，应先补充接口设计和契约测试，不能把直接导入冒称为独立预览。

## 任务与验收

### Task 1：扩展宿主固定文件种类

**Files:** `src/dst_manager/interfaces/shell.py`、`web/src/api/shell.ts`、`tests/unit/test_shell.py`、`web/src/api/shell.test.ts`。

**接口：** 在既有 `select_file` 的 `FileKind` 与 `_FILE_KIND_PATTERNS` 白名单中增加 `dststandard -> *.dststandard`，同步扩展前端 `ShellFileKind`；保留原方法、取消返回 `null`、未知 kind 拒绝和本地化描述净化规则。不接受前端传入任意过滤器或文件类型字符串。

- [ ] 先写 RED：`dststandard` 只生成 `*.dststandard` 过滤器；恶意或含伪造扩展名的描述不能放宽过滤器；取消返回 `None`/`null`；原有四种 kind 行为不变。
- [ ] 实现白名单与 TS 类型，运行宿主和前端相关单测，记录 GREEN。

### Task 2：统一导入弹窗与结果状态

**Files:** `web/src/views/StandardsView.vue`、`web/src/i18n/locales/zh-CN/standards.ts`、`web/src/i18n/locales/en-US/standards.ts`、`web/tests/e2e/standards-welcome.spec.ts`、`web/tests/e2e/standards-library.spec.ts`；如抽出局部逻辑，测试与模块同层放置。

**接口：** 欢迎页 `openStandards("import-package")` 与标准库按钮继续进入唯一的 `StandardsView` 导入弹窗。桌面壳可用时显示“选择标准包”按钮和所选只读路径，调用 `select_file("dststandard", localizedDescription)`；取消选择保持弹窗并不发导入请求。无壳浏览器显示明确标注的“本机路径（开发态）”输入回退，不使用 `<input type="file">` 的浏览器伪路径。确认导入继续调用 `store.importPackage({path})` 与既有 API，不新增第二套导入状态。

- [ ] 先写 RED：欢迎页与标准库入口打开同一弹窗；有壳时调用固定 kind、取消不导入、所选路径可核对且中文/空格/OneDrive 路径原样传给 API；无壳路径回退可用，空路径不能提交。
- [ ] 先写 RED：检查中阻止重复提交；包校验失败与身份冲突在弹窗内显示后端诊断，路径与输入保留、可重新选择或重试、库不新增记录；成功关闭弹窗、刷新列表并定位到导入版本详情，不留下旧选择或旧错误。
- [ ] 依 ARCH-DM-007 复用 `dialogFocus.ts`，覆盖初始焦点、Tab/Shift+Tab 圈闭、Escape、取消及提交后的焦点归还；错误消息、路径字段和按钮有可访问名称，900×768 与 200% 缩放下操作可达。先写交互 RED 后实现。
- [ ] 中英文文案同步；运行相关单测、Playwright、`check:i18n`、`check:ui` 与生产构建，记录 GREEN。

### Task 3：服务端边界、桌面实测与归档

**Files:** `tests/integration/test_standard_api.py`、`docs/dst-manager/specs/SPEC-DM-016-drawing-standard-management-ui.md`、`docs/dst-manager/specs/assets/SPEC-DM-016/README.md`、本计划、相关索引与 `changelog.md`。服务端测试若已有同等覆盖，引用用例与结果，不重复写镜像测试。

- [ ] 核实后端包校验、身份冲突、导入失败不写库及成功返回身份的既有测试；缺失的边界先补 RED，再修正实现。不得为方便 UI 绕过现有包验证与发布门禁。
- [ ] 在 Windows WebView2 真实桌面按 SPEC-DM-016 G9 检查文件过滤、取消、中文/空格/OneDrive 路径、导入失败重试、成功后详情定位、键盘焦点、900×768 和 200% 缩放。浏览器 E2E 不替代桌面证据；桌面缺席时记录跳过与恢复条件，状态保持 `active`。
- [ ] 用临时有效 `.dststandard` 包独立验证原生选择、导入与详情定位。PLAN-DM-040 完成后，再由较晚完成的计划复跑“受控草稿资产 → 发布 → 导出 `.dststandard` → 原生选择 → 导入 → 详情定位”联验；若另一计划尚未完成，只记录联验待办，不阻断本计划独立验收。
- [ ] 执行 `rtk uv run ruff check .`、相关 `rtk uv run pytest -q`、`rtk uv lock --check`；在 `web/` 执行 `rtk npm run test:unit`、`rtk npm run check:api`、`rtk npm run check:i18n`、`rtk npm run check:ui`、`rtk npm run build` 与相关 Playwright。回写 G9 证据、偏差、`changelog.md` 和索引，只暂存本计划文件。

## 完成标准

- 原 F16／PLAN-DM-039 F7 有桌面原生选择、无壳回退、取消、失败恢复与成功定位的可复现证据；导入弹窗满足焦点与响应式契约。
- 宿主过滤器由固定 kind 决定，导入 API 继续是包校验与写入的最终权威；校验失败或身份冲突不污染标准库。
- 真实桌面 G9 和独立导入验收均有实际结果；与 PLAN-DM-040 的联验按较晚完成者执行，并在两份计划间交叉记录结果。
