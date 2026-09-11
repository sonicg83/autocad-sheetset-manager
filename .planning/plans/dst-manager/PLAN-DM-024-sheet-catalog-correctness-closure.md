---
id: PLAN-DM-024
title: 图纸目录扩展正确性缺陷收口
status: completed
document_kind: plan
owners:
  - dst-manager
created: 2026-09-11
updated: 2026-09-11
related:
  - ARCH-DM-005
  - ARCH-DM-006
  - SPEC-DM-012
  - PLAN-DM-020
  - PLAN-DM-023
  - MEMO-DM-031
---

# 图纸目录扩展正确性缺陷收口实施计划

> **供代理执行：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐条执行；每个生产改动严格遵循测试先红、最小实现转绿、重构保持绿灯。步骤使用 `- [ ]` 跟踪。本计划只编制整改步骤，不自动修改生产代码或提交 Git。

**目标：** 关闭 MEMO-DM-031 F1～F5，保证扩展状态刷新不会静默丢失图纸目录草稿、保存授权失败必然退出执行中状态、Shell 扩展错误可本地化、模板显示名可区分且用户模板 UUID 唯一。

**架构：** 保持现有扩展平台、页面注册表、模板设置和保存授权协议不变，在既有边界补齐状态提交闸门、Shell 错误适配和服务端模板不变量。`useExtensions` 负责“先取得候选列表、通过回调后再替换”；`App.vue` 负责判断活动扩展页是否会被移除并调用现有目录导航守卫；Python 继续作为模板 UUID 唯一性的权威，当前 locale 下的内置模板显示名冲突由前端阻止并对历史数据做显示消歧。

**技术栈：** Python 3.12、FastAPI、Pydantic、pywebview/WebView2、Vue 3、TypeScript、vue-i18n、Vite、Playwright、pytest、UV。

**规范：** [ARCH-DM-005](../../../docs/dst-manager/architecture/ARCH-DM-005-multilingual-support.md)、[ARCH-DM-006](../../../docs/dst-manager/architecture/ARCH-DM-006-builtin-extension-platform.md)、[SPEC-DM-012](../../../docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md) §3.2、§6、§10、§11、§13；缺陷来源与复核边界见 [MEMO-DM-031](../../memos/dst-manager/2026-09-11-plan-dm022-final-review-defects.md)。

## 全局约束

- 本计划是 PLAN-DM-020 的正确性收口，也是 PLAN-DM-023 的实施前置；PLAN-DM-024 未完成前不得开始 PLAN-DM-023 的生产代码任务。
- 不改变扩展清单、Capability、设置 JSON schema、API 路径、保存授权字段、XLSX、Artifact 或数据库结构；不新增迁移和第三方依赖。
- 不使用 `KeepAlive` 掩盖卸载问题；活动扩展页面因刷新结果即将消失时，必须先走现有 `guardSheetCatalogPage`，用户选择“留在此处”时不得替换当前扩展列表。
- 扩展列表首次加载失败仍可呈现空列表错误态；已有成功列表的瞬时刷新失败必须保留最后一次成功列表并显示失败状态。
- 所有保存授权结果最终都必须离开 `exporting`；已知壳生命周期状态返回结构化错误，前端仍捕获未知 Promise 拒绝作为最后防线。
- UI 可见的已知错误必须通过 `message_key + params` 本地化；原始 `message` 只作兼容诊断，不得在 en-US 正文中显示中文。
- `template_id` 是用户模板身份权威；服务端拒绝重复 UUID。显示名称不能替代身份，也不能让内置模板和用户模板在当前语言下成为不可区分的选项。
- 不把语言包文案引入 Python 领域层；内置模板本地化显示名冲突在前端按当前 locale 校验，服务端继续执行用户模板 UUID 与用户模板名称不变量。
- 用户截图和真实工程数据不进入测试或提交；测试使用现有虚构 fixture 和临时目录。
- 每个任务更新 `changelog.md`，只提交本任务文件；不得提交缓存、测试输出、`web/dist/`、`.superpowers/` 或应用数据。

## 追踪矩阵

| ID | 缺陷与要求 | 实施任务 | 自动验证 | 完成判据 |
| --- | --- | --- | --- | --- |
| F1 | 被动刷新不得绕过守卫丢草稿 | 1 | Playwright：请求失败、AVAILABLE→FAILED、留在/放弃 | 草稿保留或经用户明确放弃 |
| F2 | 保存授权拒绝不得卡在 exporting | 2 | Shell 单测 + Playwright Promise rejection | 可见错误、按钮可重试 |
| F3 | Shell 扩展错误必须携带 message_key | 2 | message catalog + Shell 单测 + en-US E2E | 三个扩展码均渲染英文 |
| F4 | 本地化内置名与用户模板不得不可区分 | 3 | zh-CN/en-US E2E + 切换语言 | 新建被阻止，历史碰撞有消歧 |
| F5 | 用户模板 template_id 必须唯一 | 3 | 模板单测 + PUT API 集成测试 | 重复 UUID 在持久化前拒绝 |

---

## 任务 1：为扩展列表替换增加草稿生命周期闸门

**文件：**

- 修改：`web/src/composables/useExtensions.ts`
- 修改：`web/src/App.vue`
- 修改：`web/tests/e2e/fixtures/sheetCatalog.ts`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`web/tests/e2e/extensions-settings.spec.ts`
- 修改：`changelog.md`

**接口：**

- `useExtensions.reload(beforeReplace?)` 继续返回 `Promise<void>`；新增可选回调：

  ```ts
  type BeforeExtensionListReplace = (
    previous: readonly ExtensionSummary[],
    next: readonly ExtensionSummary[],
  ) => boolean | Promise<boolean>;
  ```

- 请求失败时不调用 `beforeReplace`、不改写已有 `extensions`，只设置 `failed=true`；请求成功且回调返回 `false` 时保留旧列表。
- reload 使用递增 generation；只有最新请求可以提交列表或改写 `loading/failed`，较旧响应不得覆盖较新结果。
- `App.vue` 提供回调：仅当当前活动扩展页会从候选页面集合消失时调用 `guardSheetCatalogPage`；守卫结果为 `continue` 才允许替换。

- [x] **步骤 1：扩展 sheet-catalog fixture。** 增加“下一次 `/api/extensions` 请求失败”和“下一次成功返回 FAILED 状态”的可编程控制，不改变默认成功路径。

- [x] **步骤 2：写请求失败红灯。** 打开图纸目录、修改表达式形成未保存草稿、打开设置并令刷新请求失败；断言图纸目录标签仍存在、仍为活动标签、表达式草稿原样保留，同时设置扩展区显示“扩展列表加载失败”。

- [x] **步骤 3：写成功但活动页失效与并发红灯。** 让刷新成功返回同一扩展的 `FAILED` 状态，断言先出现现有三选一守卫；选择“留在此处”后标签和草稿保留，候选列表不得提交；再次刷新并选择“放弃修改”后才移除标签并回到 `sheets`。再用可控 Promise 令旧请求晚于新请求完成，断言旧响应不覆盖新列表或失败状态。

- [x] **步骤 4：运行红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts tests/e2e/extensions-settings.spec.ts --grep "刷新失败保留目录草稿|活动扩展失效先过守卫" --workers=1 --retries=0
  ```

  预期：当前实现因失败时清空列表或成功列表直接触发 `useShellTabs` 回退而失败；如果测试未红，先核对 fixture 是否真的命中打开设置触发的刷新请求。

- [x] **步骤 5：实现候选列表提交协议。** `useExtensions.reload` 先分配 generation 并把响应保存为局部 `next`；仅最新 generation 通过 `beforeReplace` 后才写入 `extensions.value/loading/failed`，catch 保留旧值。不得把草稿语义或具体 route key 下沉到 `useExtensions`。

- [x] **步骤 6：在 App 装配现有守卫。** 比较前后 `workspace_page` route 集合；当前活动扩展 route 仍存在时直接通过，否则把列表替换作为 `guardSheetCatalogPage` 的 `next` 后续动作。不要修改 `useShellTabs` 的通用动态列表回退语义。

- [x] **步骤 7：运行聚焦回归。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts tests/e2e/extensions-navigation.spec.ts tests/e2e/extensions-settings.spec.ts --workers=1 --retries=0
  ```

- [x] **步骤 8：记录并提交。** changelog 记录“失败保留最后成功列表”和“成功失效先过草稿守卫”；commit message：`防止扩展刷新绕过目录草稿守卫`。

## 任务 2：闭合保存授权异常和 Shell 扩展错误本地化

**文件：**

- 修改：`src/dst_manager/interfaces/message_catalog.py`
- 修改：`src/dst_manager/interfaces/shell.py`
- 修改：`tests/unit/test_message_catalog.py`
- 修改：`tests/unit/test_shell.py`
- 修改：`web/src/composables/useSheetCatalog.ts`
- 修改：`web/tests/e2e/fixtures/sheetCatalog.ts`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`changelog.md`

**接口：**

- `ShellBridge.request_extension_save(...)` 保持现有参数与返回结构；窗口未就绪由抛 `RuntimeError` 改为：

  ```python
  shell_error("EXTENSION_CAPABILITY_UNAVAILABLE", "保存对话框窗口尚未就绪")
  ```

- `message_catalog.CATALOG` 为 `EXTENSION_NOT_FOUND`、`EXTENSION_ACTION_NOT_FOUND`、`EXTENSION_CAPABILITY_UNAVAILABLE` 复用 `extension_contracts.EXTENSION_MESSAGE_KEYS` 的既有键，不新建第二套文案键。
- `exportXlsx()` 捕获 `requestExtensionSave` 的 Promise rejection，写入 `phase="failed"`、`errorCode="EXTENSION_CAPABILITY_UNAVAILABLE"` 和本地化错误正文；随后可再次调用导出。

- [x] **步骤 1：写 Shell 与目录红灯。** 把 `test_request_extension_save_requires_window` 从“期待 RuntimeError”改为断言结构化失败，并为三个扩展错误码逐一断言 `code/message_key/params/message` 四字段完整；在 `test_message_catalog.py` 锁定它们属于已登记 UI 可见错误。

- [x] **步骤 2：运行 Python 红灯。**

  ```powershell
  rtk uv run pytest tests/unit/test_shell.py tests/unit/test_message_catalog.py -q
  ```

- [x] **步骤 3：写前端 Promise rejection 红灯。** fixture 新增一次授权桥拒绝模式；第一次点击导出后断言显示本地化错误且按钮不再显示“正在导出”，切回正常模式再次点击能够成功导出。

- [x] **步骤 4：写 en-US 红灯。** 分别让壳返回三个扩展错误码，断言正文使用 `errors.extension.*` 英文资源，不出现桥返回的中文兼容 message。

- [x] **步骤 5：运行前端红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --grep "授权桥拒绝后可重试|Shell 扩展错误使用当前语言" --workers=1 --retries=0
  ```

- [x] **步骤 6：实现中央错误目录复用。** 从既有 `EXTENSION_MESSAGE_KEYS` 取得三个键并构造 `ErrorCatalogEntry`；确认不存在循环导入，不改变 API 扩展错误的既有映射。

- [x] **步骤 7：实现双层失败闭环。** Python 把已知窗口状态转成结构化错误；TypeScript 把授权请求和执行请求置于可证明覆盖全部出口的 `try/catch`，或为授权段增加等价 catch。不得吞掉用户取消的 `idle` 语义。

- [x] **步骤 8：运行聚焦回归。**

  ```powershell
  rtk uv run pytest tests/unit/test_shell.py tests/unit/test_message_catalog.py -q
  rtk npm --prefix web run check:i18n
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --workers=1 --retries=0
  ```

- [x] **步骤 9：记录并提交。** commit message：`闭合图纸目录保存授权异常与错误本地化`。

## 任务 3：收紧模板显示名与 UUID 不变量

**文件：**

- 修改：`src/dst_manager/extensions/builtin/sheet_catalog/templates.py`
- 修改：`tests/unit/test_sheet_catalog_templates.py`
- 修改：`tests/integration/test_extension_api.py`
- 修改：`web/src/composables/useSheetCatalog.ts`
- 修改：`web/src/components/sheet-catalog/TemplateBar.vue`
- 修改：`web/src/i18n/locales/zh-CN/extensions.ts`
- 修改：`web/src/i18n/locales/en-US/extensions.ts`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`changelog.md`

**接口：**

- `save_templates` 在序列化前维护 `seen_ids: set[uuid.UUID]`；重复 ID 抛稳定 `ValueError` 前缀 `SHEET_CATALOG_TEMPLATE_ID_DUPLICATE`，沿现有设置 PUT 边界映射为 `EXTENSION_SETTINGS_INVALID`，不扩张 SPEC-DM-012 的七个目录业务错误码。
- `saveAs(name)` 在当前 locale 下拒绝与 `t("extensions.sheetCatalog.builtinName")` 大小写不敏感相同的名称，并使用新增对称 i18n 键显示原因。
- `TemplateBar` 对服务端历史数据或直接 API 注入造成的显示碰撞追加本地化“用户模板”后缀；option 的 `value` 和所有模板操作继续使用 UUID。

- [x] **步骤 1：写 UUID 单元红灯。** 构造两个名字不同、`template_id` 相同的用户模板，断言 `save_templates` 在返回 payload 前拒绝；同时保留“不同 UUID、不同名称”正常保存用例。

- [x] **步骤 2：写 PUT 集成红灯。** 直接向扩展设置端点提交重复 UUID，断言请求失败、持久化 revision/value 不变；错误体保持现有扩展设置错误契约。

- [x] **步骤 3：运行 Python 红灯。**

  ```powershell
  rtk uv run pytest tests/unit/test_sheet_catalog_templates.py tests/integration/test_extension_api.py -q
  ```

- [x] **步骤 4：写当前语言名称冲突红灯。** 在 zh-CN 和 en-US 下分别尝试把用户模板另存为当前内置显示名，断言不发送 PUT、对话框保留输入并显示本地化错误。

- [x] **步骤 5：写历史碰撞消歧红灯。** fixture 预置名称为 `Default catalog (built-in)` 的用户模板，切换到 en-US 后断言下拉框中内置项与用户项文本可区分，且选择、原位保存、删除仍按该用户模板 UUID 操作。

- [x] **步骤 6：运行前端红灯。**

  ```powershell
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --grep "内置模板显示名冲突|历史同名模板可区分" --workers=1 --retries=0
  ```

- [x] **步骤 7：实现服务端 UUID 唯一性。** 在名称检查同一循环内先验证非空 ID、再验证 `seen_ids`、最后执行模板内容与名称检查；不要改变 `delete_template` 的按 ID 删除接口。

- [x] **步骤 8：实现前端冲突保护与显示消歧。** 比较时 trim 并使用 locale-aware 小写；只对碰撞的用户 option 增加后缀，不改持久化名称，不把本地化文案发给后端。

- [x] **步骤 9：运行聚焦回归。**

  ```powershell
  rtk uv run pytest tests/unit/test_sheet_catalog_templates.py tests/integration/test_extension_api.py -q
  rtk npm --prefix web run check:i18n
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --workers=1 --retries=0
  ```

- [x] **步骤 10：记录并提交。** commit message：`收紧图纸目录模板名称与 UUID 不变量`。

## 任务 4：完整回归、关闭 G7 并移交视觉整改

**文件：**

- 修改：`.planning/memos/dst-manager/2026-09-11-plan-dm022-final-review-defects.md`
- 修改：`.planning/plans/dst-manager/PLAN-DM-020-sheet-catalog-builtin-extension.md`
- 修改：`.planning/plans/dst-manager/PLAN-DM-023-sheet-catalog-visual-convergence.md`
- 修改：`.planning/plans/dst-manager/PLAN-DM-024-sheet-catalog-correctness-closure.md`
- 修改：`.planning/plans/dst-manager/README.md`
- 修改：`.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md`
- 修改：`docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md`
- 修改：`docs/dst-manager/README.md`
- 修改：`changelog.md`

- [x] **步骤 1：运行静态与聚焦验证。** 所有命令必须使用本轮新鲜输出且退出码为 0：

  ```powershell
  $env:UV_LINK_MODE = "copy"
  rtk uv run ruff check .
  rtk uv run pytest tests/unit/test_shell.py tests/unit/test_message_catalog.py tests/unit/test_sheet_catalog_templates.py tests/integration/test_extension_api.py -q
  rtk uv lock --check
  rtk npm --prefix web run check:api
  rtk npm --prefix web run check:i18n
  rtk npm --prefix web run build
  rtk npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts tests/e2e/extensions-navigation.spec.ts tests/e2e/extensions-settings.spec.ts --workers=1 --retries=0
  ```

- [x] **步骤 2：运行完整自动回归。** 

  ```powershell
  rtk uv run pytest -q
  rtk npm --prefix web run test:e2e
  ```

  若全量 E2E 出现超时或 flaky，必须单独 `--workers=1 --retries=0` 复现并记录，不能把真实回归归类为抖动。

- [x] **步骤 3：逐项关闭 F1～F5。** 在 MEMO-DM-031 记录每项对应测试、实现 commit 和实际结果；F4 明确登记为“本地化显示碰撞”，不得再声称 UUID 身份混淆。

- [x] **步骤 4：恢复 G7。** 只有 F1～F5 全部关闭且聚焦/全量验证通过，才把 SPEC-DM-012 G7 从“未通过（最终评审复核）”改回“通过”，并记录负责人、日期和新鲜验证计数。

- [x] **步骤 5：完成计划并解除 PLAN-DM-023 前置。** 把本计划改为 `completed`，更新 PLAN-DM-020、PLAN-DM-023、G9 清单和两个 README。只解除 PLAN-DM-023 的实施前置；G8 仍保持未通过，G9 仍由 G8 阻断。

- [x] **步骤 6：提交。** 只暂存本计划相关治理文件，commit message：`完成图纸目录正确性缺陷收口`。

## 风险与回退

- 扩展列表替换回调可能引入竞态：每次 reload 只提交自身响应，较旧请求不得覆盖较新状态；如现有实现没有 generation 防护，任务 1 必须用最小 generation token 一并钉住。
- 三选一守卫可能叠在设置原生 `<dialog>` 上：复用现有已验证的 top-layer 目录守卫，不新建第二个模态。
- 前端只阻止当前 locale 的内置显示名碰撞，因此必须同时保留 option 消歧，覆盖切换语言和历史/API 注入数据。
- 重复 UUID 拒绝位于持久化前，不得“自动重写”客户端提交的 UUID；静默修复会破坏调用方对身份和乐观并发的判断。
- Shell 已知错误转结构化结果后，既有测试中期待 `RuntimeError` 的断言必须改为契约断言；不得保留双重行为。
- 若任何修复要求改变公开 API schema、扩展生命周期协议或模板设置 schema，停止本计划并回到 SPEC-DM-012/ARCH-DM-006 评审，不在缺陷修复中暗改契约。

## 完成标准

- MEMO-DM-031 F1～F5 均有先红后绿的自动回归证据和独立 commit。
- 活动目录页在扩展刷新失败或被动失效时不会静默卸载未保存草稿。
- 保存授权的结构化失败和 Promise rejection 都能显示当前语言错误并立即重试。
- 三个 Shell 扩展错误码稳定携带 `message_key`，zh-CN/en-US 正文均不回退原始异语言 message。
- 重复用户模板 UUID 在服务端持久化前被拒；当前语言内置名不能直接另存，历史显示碰撞仍可区分和操作。
- Ruff、相关 pytest、全量 pytest、check:api、check:i18n、生产构建、相关 E2E 和全量 E2E 均通过。
- SPEC-DM-012 G7 重新通过、PLAN-DM-024 标记 `completed` 后，才能开始 PLAN-DM-023；G8/G9 状态不被本计划提前关闭。

## 实际验证

2026-09-11，PLAN-DM-024 实施代理（负责人）。四个任务全部完成并逐任务提交：任务 1 `ecdc3d7` 防止扩展刷新绕过目录草稿守卫（F1）；任务 2 `43eafa2` 闭合图纸目录保存授权异常与错误本地化（F2/F3）；任务 3 `89cab15` 收紧图纸目录模板名称与 UUID 不变量（F4/F5）；任务 4 为本治理收口提交。逐项 TDD 先红后绿证据、commit 与实际结果登记在 [MEMO-DM-031 §7](../../memos/dst-manager/2026-09-11-plan-dm022-final-review-defects.md)（报告工作区文件不入提交树，治理文档只引用 commit 与本轮验证计数）。

本轮新鲜验证（全部退出码 0）：

| 命令 | 结果 |
| --- | --- |
| `uv run ruff check .` | All checks passed! |
| `uv run pytest tests/unit/test_shell.py tests/unit/test_message_catalog.py tests/unit/test_sheet_catalog_templates.py tests/integration/test_extension_api.py -q` | 146 passed |
| `uv lock --check` | Resolved 70 packages |
| `npm --prefix web run check:api` | 通过（OpenAPI 与 schema.d.ts 同步） |
| `npm --prefix web run check:i18n` | 870 键 / 9 域对称 |
| `npm --prefix web run build` | 通过（vue-tsc + vite） |
| `npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts tests/e2e/extensions-navigation.spec.ts tests/e2e/extensions-settings.spec.ts --workers=1 --retries=0` | 57 passed |
| `uv run pytest -q` | 1121 passed / 72 skipped / 0 failed |
| `npm --prefix web run test:e2e` | 418 passed / 0 failed / 1 flaky（`main.spec.ts`「任务回滚终态后 ActionDock 解锁」为 4 worker 下 dev server 启动 `page.goto` 超时；已按计划规则单独 `--workers=1 --retries=0` 复现，1 passed，非真实回归） |

完成标准核对：MEMO-DM-031 F1～F5 均有先红后绿自动回归证据和独立 commit；活动目录页在扩展刷新失败或被动失效时不再静默卸载未保存草稿；保存授权结构化失败与 Promise 拒绝都能显示当前语言错误并立即重试；三个 Shell 扩展错误码稳定携带 `message_key`；重复用户模板 UUID 在服务端持久化前被拒，当前语言内置名不能直接另存，历史显示碰撞可区分和操作。SPEC-DM-012 G7 已于 2026-09-11 恢复“通过”；G8 仍为“未通过（用户真实桌面复验）”、G9 仍由 G8 阻断，未在本计划内提前关闭。PLAN-DM-023 的实施前置就此解除，可开始其生产代码任务。
