---
id: PLAN-DM-021
title: DST Manager 多语言支持实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-09
updated: 2026-09-09
related:
  - ARCH-DM-001
  - ARCH-DM-005
  - SPEC-DM-013
  - SPEC-DM-011
  - GUIDE-DM-001
---

# DST Manager 多语言支持实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans`；选择会话内分工执行时还必须使用 `superpowers:subagent-driven-development`。每个任务严格先写失败测试，再做最小实现，并在批次检查点停止复核。

**目标：** 在不改变 DST/DWG、工作区、草稿、任务和发布语义的前提下，为桌面界面提供 `zh-CN`/`en-US`、跟随系统、保存后即时切换、结构化本地化错误和受控原生文件对话框。

**架构：** 后端只持有稳定设置 key、错误 code、`message_key`、参数和文件种类，不按请求语言生成业务状态；前端在挂载前解析设置并创建唯一 `vue-i18n` 实例，按域装载两套同构资源。语言切换以设置 PUT 成功为提交点。迁移窗口结束时删除中文元数据与调用点错误映射兼容层。

**技术栈：** Python 3.12、Pydantic、FastAPI、pywebview/WebView2、Vue 3、TypeScript、vue-i18n、Vitest、Vite、Playwright、UV、PyInstaller。

**规范：** [ARCH-DM-005](../../../docs/dst-manager/architecture/ARCH-DM-005-multilingual-support.md)、[SPEC-DM-013](../../../docs/dst-manager/specs/SPEC-DM-013-multilingual-ui.md)、[G4 冻结 Demo](../../../docs/dst-manager/mockups/SPEC-DM-013-multilingual-demo.html)、[G5 技术映射](../../memos/dst-manager/2026-09-09-multilingual-g5-technical-mapping.md)。

## 全局约束

- 执行前阅读根 `README.md`、`docs/README.md`、`docs/dst-manager/README.md`、`ARCH-DM-001`、`ARCH-DM-005`、`SPEC-DM-013` 和本计划；先检查并避开用户已有改动。
- 使用 PowerShell 与 UV；Python 依赖只用 `uv add/remove/sync`，前端依赖变化必须同步 `package.json` 与 `package-lock.json`。
- 每个任务遵循 red → green → refactor。失败测试必须因目标能力缺失而失败；每个任务更新 `changelog.md` 并只提交自身文件。
- `web/src/App.vue` 与 `src/dst_manager/interfaces/api.py` 只允许最小装配；语言解析、资源、错误目录进入本计划指定的新模块。
- domain 不依赖 FastAPI、Vue、locale 或翻译资源；语言不得写入 job、draft、数据库、操作日志、DST 或 DWG。
- 用户输入、路径、图号、布局名、属性名/值、版本、错误码、协议字段和状态码保持原样；未知第三方原文只进可展开诊断。
- 首期只支持 `system`、`zh-CN`、`en-US`；显式设置优先于系统语言，无法读取系统语言回退 `zh-CN`，其他可识别非中文语言映射 `en-US`。
- 设置只在保存成功后切换语言；编辑、取消、422、409、网络错误和 5xx 均保持当前生效语言与本地输入。
- 冻结 Demo 是 G8 基准。若主流程、语言位置、保存时机或错误恢复语义变化，停止实施并回到 G2～G6 更新规范。
- 真实 WebView2 系统语言与原生对话框必须留有 G9 证据，浏览器 mock 不能替代；无真实环境时计划保持 `active`。

## 追踪矩阵（G6 依据）

| 需求 | 实施任务 | 自动测试 | G8/G9 | 初始状态 |
| --- | --- | --- | --- | --- |
| I18N-01 唯一 i18n 与回退 | 2、5～8、11 | locale/key/Vue/E2E | G8 | 已覆盖 |
| I18N-02 设置值与持久化 | 1 | config/registry/API | — | 已覆盖 |
| I18N-03 语言解析规则 | 2 | `locale.test.ts` | G9 | 已覆盖 |
| I18N-04 挂载前解析及失败降级 | 2 | bootstrap/Vue/E2E | G9 | 已覆盖 |
| I18N-05 保存成功才切换 | 3 | settings 单测/E2E | G8 | 已覆盖 |
| I18N-06 html lang 与状态/焦点保持 | 2、3、11 | controller/E2E | G8/G9 | 已覆盖 |
| I18N-07 全部可见文本与可访问名称 | 3、5～8、10 | 硬编码扫描/E2E | G8 | 已覆盖 |
| I18N-08 参数、复数、日期/数字 | 5～8、10 | key 参数扫描/单测 | G8 | 已覆盖 |
| I18N-09 设置元数据 key/file_kind | 1、4 | registry/API/shell | G9 | 已覆盖 |
| I18N-10 结构化 422 | 1、3 | runtime/API/E2E | G8 | 已覆盖 |
| I18N-11 已知 API/CAD/Shell 错误 | 9 | catalog/API/E2E | G8/G9 | 已覆盖 |
| I18N-12 SSE 稳定码且语言不入持久层 | 8、9、12 | job/API/数据库反查 | G9 | 已覆盖 |
| I18N-13 文件种类固定白名单 | 4 | shell Python/TS | G9 | 已覆盖 |
| I18N-14 键与插值参数构建期一致 | 2、10 | `check:i18n` | — | 已覆盖 |
| I18N-15 英文/窄屏/主题/200% | 11 | visual E2E | G8/G9 | 已覆盖 |
| I18N-16 业务数据不变 | 11、12 | 状态与文件 hash 回归 | G9 | 已覆盖 |
| I18N-17 兼容层阶段三删除 | 10 | 全仓扫描/API schema | — | 已覆盖 |
| I18N-18 真实 WebView2 三类语言 | 12 | 浏览器仅作辅助 | G9 | 已覆盖 |

---

## 批次一：语言基础、设置事务与原生对话框契约

批次结果：应用能在挂载前解析语言；设置中心展示语言并只在保存成功后切换；422 结构化；四种文件选择的扩展白名单不再由本地化字符串决定。完成本批次即满足 `PLAN-DM-020` Task 10 的多语言基础前置。

### Task 1：后端语言设置、元数据 key 与结构化字段错误

**Files**

- Modify: `src/dst_manager/config.py`
- Modify: `src/dst_manager/settings/registry.py`
- Modify: `src/dst_manager/settings/runtime.py`
- Modify: `src/dst_manager/interfaces/settings_contracts.py`
- Modify: `src/dst_manager/interfaces/api.py`（仅 `_settings_items` 与 422 响应装配）
- Modify: `tests/unit/test_config.py`
- Modify: `tests/unit/test_settings_registry.py`
- Modify: `tests/unit/test_settings_resolver.py`
- Modify: `tests/unit/test_settings_runtime.py`
- Modify: `tests/integration/test_api_settings.py`
- Modify: `changelog.md`

**目标接口**

```python
UiLocale = Literal["system", "zh-CN", "en-US"]

class Settings(BaseSettings):
    ui_locale: UiLocale = "system"

@dataclass(frozen=True)
class SettingsItemMeta:
    key: str
    label_key: str
    category_key: str
    control: Literal["path", "bool", "int", "enum"]
    file_filter_key: str | None = None
    file_kind: Literal["exe", "dll"] | None = None

class FieldErrorModel(ContractModel):
    code: str
    message_key: str
    params: dict[str, str | int]
    message: str
```

- [ ] **Step 1：写红灯。** 断言默认 `system`、env/file 优先级、三值白名单；registry 首项为“界面/语言”，所有项只靠 key 描述，enum 值支持 `str | int`；422 外层 key 是设置 key，参数不含 label/完整句子。
- [ ] **Step 2：运行红灯。** `uv run pytest tests/unit/test_config.py tests/unit/test_settings_registry.py tests/unit/test_settings_resolver.py tests/unit/test_settings_runtime.py tests/integration/test_api_settings.py -q`。
- [ ] **Step 3：最小实现。** 增加字段与元数据；迁移期响应同时保留旧中文字段和新 key 字段。`SettingsValidationError.errors` 改为结构化对象，`message` 仅兼容，不作为前端新主路径。
- [ ] **Step 4：绿灯与静态检查。** 重跑 Step 2；运行 `uv run ruff check src/dst_manager/config.py src/dst_manager/settings src/dst_manager/interfaces/settings_contracts.py tests/unit/test_settings_*.py tests/integration/test_api_settings.py`。
- [ ] **Step 5：记录并提交。** 更新 changelog，提交 `增加语言设置与结构化字段错误`。

### Task 2：唯一 i18n、系统语言解析与挂载前 bootstrap

**Files**

- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/src/main.ts`
- Create: `web/src/i18n/locale.ts`
- Create: `web/src/i18n/index.ts`
- Create: `web/src/i18n/locales/zh-CN/common.ts`
- Create: `web/src/i18n/locales/en-US/common.ts`
- Create: `web/src/i18n/locales/zh-CN/settings.ts`
- Create: `web/src/i18n/locales/en-US/settings.ts`
- Create: `web/src/i18n/locale.test.ts`
- Create: `web/src/i18n/bootstrap.test.ts`
- Create: `web/vitest.config.ts`
- Modify: `web/tests/global-setup.ts`
- Modify: `changelog.md`

**目标接口**

```ts
export type UiLocaleSetting = "system" | "zh-CN" | "en-US";
export type EffectiveLocale = "zh-CN" | "en-US";
export function resolveLocale(value: UiLocaleSetting, languages?: readonly string[]): EffectiveLocale;
export function applyLocale(locale: EffectiveLocale): Promise<void>;
export async function bootstrap(): Promise<void>;
```

- [ ] **Step 1：先装测试能力。** 用 `npm --prefix web install vue-i18n` 与 `npm --prefix web install -D vitest` 更新依赖和锁文件；新增 `test:unit`，但尚不写生产实现。
- [ ] **Step 2：写红灯。** 覆盖显式值、`zh-*`、非中文、空数组/异常回退；断言设置请求结束前不 mount，读取失败仍按系统规则 mount，只有一个 i18n 实例，`applyLocale` 同步 `<html lang>`。
- [ ] **Step 3：运行红灯。** `npm --prefix web run test:unit -- src/i18n/locale.test.ts src/i18n/bootstrap.test.ts`。
- [ ] **Step 4：最小实现。** `main.ts` 只调用 `bootstrap()`；bootstrap 捕获设置读取失败并用系统规则继续，不渲染错误语言的完整 App。全局 E2E 临时 settings.json 显式写 `ui_locale: "zh-CN"` 固定既有中文基线。
- [ ] **Step 5：绿灯。** 重跑 Step 3，再运行 `npm --prefix web run build`。
- [ ] **Step 6：记录并提交。** 更新 changelog，提交 `建立前端多语言启动基础`。

### Task 3：设置中心语言事务与双语错误恢复

**Files**

- Modify: `web/src/api/settings.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/composables/useSettings.ts`
- Modify: `web/src/components/settings/SettingsDialog.vue`
- Modify: `web/src/components/settings/SettingsFormRow.vue`
- Modify: `web/src/i18n/locales/zh-CN/settings.ts`
- Modify: `web/src/i18n/locales/en-US/settings.ts`
- Modify: `web/src/i18n/locales/zh-CN/common.ts`
- Modify: `web/src/i18n/locales/en-US/common.ts`
- Create: `web/src/composables/useSettings.test.ts`
- Modify: `web/tests/e2e/settings-dialog.spec.ts`
- Modify: `changelog.md`

- [ ] **Step 1：写事务红灯。** 单测断言选择语言不切换、PUT 成功后切换一次、422/409/5xx/取消不切换；E2E 断言对话框保持打开、保存按钮焦点/错误摘要焦点、背景页面与输入不丢失、`html[lang]` 正确。
- [ ] **Step 2：写双语状态红灯。** 覆盖“跟随系统（当前：…）”、英文长标签、成功反馈、逐字段错误、冲突恢复、schema 只读、加载失败；ARIA/tooltip 同步切换。
- [ ] **Step 3：运行红灯。** `npm --prefix web run test:unit -- src/composables/useSettings.test.ts && npm --prefix web run test:e2e -- tests/e2e/settings-dialog.spec.ts --workers=1`。
- [ ] **Step 4：最小实现。** API 映射只向组件暴露 key 与结构化错误；按 category key 分组。`onSave` 以响应快照的 `ui_locale` 为提交值，调用 `applyLocale` 后 `nextTick` 恢复焦点；错误摘要使用 `tabindex=-1` 并链接首个字段。
- [ ] **Step 5：绿灯与构建。** 重跑 Step 3，运行 `npm --prefix web run build`。
- [ ] **Step 6：记录并提交。** 更新 changelog，提交 `实现设置保存后的语言切换事务`。

### Task 4：ShellBridge 固定文件种类与本地化描述

**Files**

- Modify: `src/dst_manager/interfaces/shell.py`
- Modify: `web/src/api/shell.ts`
- Modify: `web/src/App.vue`（仅四处选择文件调用）
- Modify: `tests/unit/test_shell.py`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `web/tests/e2e/sheets-folder.spec.ts`
- Modify: `changelog.md`

**目标接口**

```python
FileKind = Literal["dst", "template", "exe", "dll"]
def select_file(self, file_kind: FileKind, localized_description: str) -> str | None: ...
```

```ts
select_file(fileKind:"dst"|"template"|"exe"|"dll", localizedDescription:string): Promise<string|null>;
```

- [ ] **Step 1：写安全红灯。** Python 断言四种 kind 的固定扩展名、未知 kind 拒绝、本地化描述含伪造 `*.bat` 也不能扩大白名单、取消返回 null、无 window 报明确错误；TS/E2E 断言中英文只改变描述。
- [ ] **Step 2：运行红灯。** `uv run pytest tests/unit/test_shell.py -q` 与 `npm --prefix web run test:e2e -- tests/e2e/main.spec.ts tests/e2e/sheets-folder.spec.ts --workers=1`。
- [ ] **Step 3：最小实现。** Python 根据 kind 拼接固定模式；前端删除过滤器数组，以 i18n 生成描述。同包升级不保留旧 `file_types` 任意字符串签名。
- [ ] **Step 4：绿灯。** 重跑 Step 2，运行 Ruff 与 `npm --prefix web run build`。
- [ ] **Step 5：批次检查点与提交。** 演示设置保存成功/失败和四种选择调用；在 `PLAN-DM-020`“实际验证”记录 `PLAN-DM-021` 基础批次 commit/测试结果后，更新 changelog 并提交 `收紧原生文件选择本地化契约`，停止复核。

---

## 批次二：核心页面按域迁移

批次结果：中文全量基线继续通过，英文可完成打开、图纸、属性、修订、任务和发布关键流程；切换只触发响应式重绘，不重建业务状态。

### Task 5：共享外壳、通用组件与格式化能力

**Files**

- Modify: `web/src/App.vue`（仅调用点）
- Modify: `web/src/layout/TopBar.vue`
- Modify: `web/src/layout/TabBar.vue`
- Modify: `web/src/layout/ActionDock.vue`
- Modify: `web/src/layout/TaskOverlay.vue`
- Modify: `web/src/views/WelcomeView.vue`
- Modify: `web/src/components/ui/ConfirmModal.vue`
- Modify: `web/src/components/ui/UnsavedInputDialog.vue`
- Modify: `web/src/components/ui/ToastHost.vue`
- Modify: `web/src/composables/useConfirm.ts`
- Modify: `web/src/composables/useToast.ts`
- Create: `web/src/i18n/locales/zh-CN/shell.ts`
- Create: `web/src/i18n/locales/en-US/shell.ts`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `changelog.md`

- [ ] **Step 1：写红灯。** 为中英外壳、快捷键提示、确认框、Toast、空状态与日期/数字格式写 Playwright/单元断言；切换前后记录 active tab、workspace id、输入值并断言不变。
- [ ] **Step 2：运行红灯。** `npm --prefix web run test:e2e -- tests/e2e/main.spec.ts --workers=1`。
- [ ] **Step 3：最小迁移。** 模板用 `$t`，脚本用 `useI18n`；动态句子用命名参数/复数，不在调用点拼接翻译片段。用户数据保持原样。
- [ ] **Step 4：绿灯、构建、记录与提交。** 重跑 Step 2 和 build；更新 changelog，提交 `迁移共享外壳与通用组件文案`。

### Task 6：图纸工作区迁移

**Files**

- Modify: `web/src/views/SheetsView.vue`
- Modify: `web/src/components/SheetTable.vue`
- Modify: `web/src/components/sheets/*.vue`
- Modify: `web/src/composables/useSheetsWorkspace.ts`
- Modify: `web/src/composables/useSheetProjection.ts`
- Modify: `web/src/composables/useSheetEditor.ts`
- Modify: `web/src/composables/useSheetColumns.ts`
- Modify: `web/src/features/sheets/commands.ts`
- Modify: `web/src/features/sheets/projection.ts`
- Create: `web/src/i18n/locales/zh-CN/sheets.ts`
- Create: `web/src/i18n/locales/en-US/sheets.ts`
- Modify: `web/tests/e2e/sheets-*.spec.ts`
- Modify: `changelog.md`

- [ ] **Step 1：写英文关键矩阵红灯。** 覆盖导航、空集、选择、编辑、目录、列设置、草稿与错误状态；断言图号、标题、路径和自定义属性不被翻译。
- [ ] **Step 2：运行红灯。** `npm --prefix web run test:e2e -- tests/e2e/sheets-navigation.spec.ts tests/e2e/sheets-editing.spec.ts tests/e2e/sheets-columns.spec.ts tests/e2e/sheets-drafts.spec.ts --workers=1`。
- [ ] **Step 3：最小迁移。** 仅替换用户可见静态/格式化文本；命令 payload、字段名和后端校验保持原契约。
- [ ] **Step 4：完整图纸绿灯。** `npm --prefix web run test:e2e -- tests/e2e/sheets-*.spec.ts --workers=1` 与 build。
- [ ] **Step 5：记录并提交。** 更新 changelog，提交 `迁移图纸工作区双语文案`。

### Task 7：属性工作区迁移

**Files**

- Modify: `web/src/views/PropertiesView.vue`
- Modify: `web/src/components/properties/*.vue`
- Modify: `web/src/composables/usePropertiesWorkspace.ts`
- Modify: `web/src/composables/useCsvImport.ts`
- Modify: `web/src/features/properties/model.ts`
- Create: `web/src/i18n/locales/zh-CN/properties.ts`
- Create: `web/src/i18n/locales/en-US/properties.ts`
- Modify: `web/tests/e2e/properties-*.spec.ts`
- Modify: `changelog.md`

- [ ] **Step 1：写英文关键矩阵红灯。** 覆盖定义/值/比较/CSV/缓冲与空态；属性名、值和 CSV 内容保持原样。
- [ ] **Step 2：运行红灯。** `npm --prefix web run test:e2e -- tests/e2e/properties-workspace.spec.ts tests/e2e/properties-values.spec.ts tests/e2e/properties-csv.spec.ts --workers=1`。
- [ ] **Step 3：最小迁移。** 提取用户文案与格式化表达，保留模型中的稳定 kind/status；CSV 头仅按既有文件契约处理，不随 UI locale 静默改变。
- [ ] **Step 4：完整属性绿灯、构建、记录与提交。** 运行 `npm --prefix web run test:e2e -- tests/e2e/properties-*.spec.ts --workers=1` 和 build；更新 changelog，提交 `迁移属性工作区双语文案`。

### Task 8：修订、预览、修复、草稿与任务状态迁移

**Files**

- Modify: `web/src/views/RevisionsView.vue`
- Modify: `web/src/components/RevisionHistoryPanel.vue`
- Modify: `web/src/components/PreviewPanel.vue`
- Modify: `web/src/components/RepairStatusPanel.vue`
- Modify: `web/src/components/DraftActionsPanel.vue`
- Modify: `web/src/components/JobStatusPanel.vue`
- Modify: `web/src/composables/useRestore.ts`
- Modify: `web/src/composables/useRepair.ts`
- Modify: `web/src/composables/useJobMonitor.ts`
- Create: `web/src/i18n/locales/zh-CN/revisions.ts`
- Create: `web/src/i18n/locales/en-US/revisions.ts`
- Create: `web/src/i18n/locales/zh-CN/jobs.ts`
- Create: `web/src/i18n/locales/en-US/jobs.ts`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `changelog.md`

- [ ] **Step 1：写红灯。** 覆盖 preview/repair/revision/job 各稳定状态；SSE payload 保持 code，前端渲染中英文；NEEDS_REVIEW、断线、重试、取消、失败在切换前后状态不变。
- [ ] **Step 2：运行红灯。** `npm --prefix web run test:e2e -- tests/e2e/main.spec.ts --workers=1`。
- [ ] **Step 3：最小迁移。** 将状态码映射到语义 key，动态数量用复数/参数；不把 locale 传回 job API 或保存到草稿。
- [ ] **Step 4：批次绿灯。** 运行 `npm --prefix web run test:unit`、`npm --prefix web run build`、`npm --prefix web run test:e2e`。
- [ ] **Step 5：记录并提交。** 更新 changelog，提交 `完成核心工作区双语迁移`，停止复核。

---

## 批次三：统一错误目录、构建门禁与兼容清理

### Task 9：已知 API/CAD/Shell 错误结构化

**Files**

- Create: `src/dst_manager/interfaces/message_catalog.py`
- Modify: `src/dst_manager/interfaces/responses.py`（若容量超限则新建 `error_contracts.py`）
- Modify: `src/dst_manager/interfaces/serialization.py`
- Modify: `src/dst_manager/interfaces/api.py`（仅注册统一 handler）
- Modify: `src/dst_manager/application/errors.py`
- Modify: `src/dst_manager/interfaces/shell.py`
- Modify: `web/src/api/client.ts`
- Create: `web/src/i18n/locales/zh-CN/errors.ts`
- Create: `web/src/i18n/locales/en-US/errors.ts`
- Create: `tests/unit/test_message_catalog.py`
- Modify: `tests/integration/test_api.py`
- Modify: `tests/unit/test_shell.py`
- Modify: `web/tests/e2e/main.spec.ts`
- Modify: `changelog.md`

**统一响应**

```json
{"code":"WORKSPACE_NOT_FOUND","message_key":"errors.workspace.notFound","params":{"workspace_id":"..."},"message":"兼容文本"}
```

- [ ] **Step 1：建立错误目录红灯。** 枚举现有已知 API/CAD/Shell code，断言每个有唯一 key、参数 schema 和中英文资源；参数拒绝本地化 label/完整句子。
- [ ] **Step 2：写契约红灯。** API 与桥返回稳定结构；前端已知错误忽略兼容 `message` 并按 key 渲染，未知错误显示本地化摘要且原文只在诊断详情。
- [ ] **Step 3：运行红灯。** `uv run pytest tests/unit/test_message_catalog.py tests/integration/test_api.py tests/unit/test_shell.py -q` 与 main E2E。
- [ ] **Step 4：最小实现。** catalog 仅在接口层适配现有异常；不把翻译资源或 locale 传入 application/domain。日志继续记录稳定 code 与原始诊断。
- [ ] **Step 5：绿灯、记录与提交。** 重跑 Step 3、Ruff、build；更新 changelog，提交 `统一用户可见错误本地化契约`。

### Task 10：语言包完整性与兼容层清理

**Files**

- Create: `web/scripts/check-i18n.mjs`
- Create: `web/src/i18n/hardcoded-allowlist.json`
- Modify: `web/package.json`
- Modify: `src/dst_manager/settings/registry.py`
- Modify: `src/dst_manager/interfaces/settings_contracts.py`
- Modify: `src/dst_manager/interfaces/api.py`
- Modify: `web/src/api/settings.ts`
- Modify: `web/src/api/openapi.json`（生成）
- Modify: `web/src/api/schema.d.ts`（生成）
- Modify: `tests/unit/test_settings_registry.py`
- Modify: `tests/integration/test_api_settings.py`
- Modify: `changelog.md`

- [ ] **Step 1：写检查器红灯夹具。** 分别制造缺键、多键、命名参数不一致和新增硬编码中文，断言 `check:i18n` 非零退出并定位域/键/文件。
- [ ] **Step 2：接入构建。** `build` 先运行 `check:i18n`；允许清单只收用户数据示例、协议常量和必要品牌名，每项注明原因，不能用于跳过普通 UI 文案。
- [ ] **Step 3：删除兼容层。** 全仓确认无调用后删除设置 `label/category/text/file_filter`、前端 `code -> 中文` 主路径与旧任意 `select_file(file_types)`；保留结构化错误的诊断 `message` 兼容字段到架构指定窗口结束。
- [ ] **Step 4：生成并验证契约。** `npm --prefix web run generate:api`，运行设置/API/Shell Python 测试、`npm --prefix web run test:unit`、`npm --prefix web run build`。
- [ ] **Step 5：反向扫描。** `rg -n "\blabel\b|\bcategory\b|file_filter|select_file\(\[|DIAG_TEXTS|[一-龥]" src/dst_manager web/src`，逐项确认只剩允许内容；不能以批量忽略替代迁移。
- [ ] **Step 6：记录并提交。** 更新 changelog，提交 `建立翻译完整性门禁并清理兼容字段`，停止复核。

---

## 批次四：设计 QA、完整回归与真实桌面验收

### Task 11：英文关键矩阵、响应式与业务不变量

**Files**

- Create: `web/tests/e2e/i18n-workflows.spec.ts`
- Create: `web/tests/e2e/i18n-visual-evidence.spec.ts`
- Create: `.planning/memos/dst-manager/PLAN-DM-021-multilingual-design-qa.md`
- Modify: `web/src/style.css`（仅确属共享排版规则时）
- Modify: `changelog.md`

- [ ] **Step 1：写关键矩阵。** 两语言覆盖启动、设置、打开、图纸、属性、修订、任务、预览与发布；语言切换前后断言 workspace/revision/draft/selection/job 标识和输入相同。
- [ ] **Step 2：写视觉/可访问性红灯。** 1440×900 浅色、900×768 深色、200% 缩放；断言无整页横滚、主操作可达、长错误可读、表格只在自身横滚。覆盖 Tab、Esc、焦点圈闭/归还、错误摘要和非颜色状态。
- [ ] **Step 3：运行并最小修复。** `npm --prefix web run test:e2e -- tests/e2e/i18n-workflows.spec.ts tests/e2e/i18n-visual-evidence.spec.ts --workers=1`；布局修复优先落所属组件，只有共享规则才改全局 CSS。
- [ ] **Step 4：执行 G8。** 使用与 G4 相同的虚构数据、视口、主题和状态生成生产截图，与两张冻结图逐项记录一致、可接受差异或缺陷；缺陷修复后重新取证。
- [ ] **Step 5：记录并提交。** G8 无未关闭 P0/P1 后更新 changelog，提交 `完成多语言设计与状态不变量验证`。

### Task 12：打包、完整验证、G9 与状态收口

**Files**

- Modify: `tests/unit/test_packaging_spec.py`
- Create: `.planning/memos/dst-manager/PLAN-DM-021-multilingual-g9-checklist.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-021-multilingual-support.md`
- Modify: `docs/dst-manager/specs/SPEC-DM-013-multilingual-ui.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `changelog.md`

- [ ] **Step 1：打包红灯。** 断言生产 Web 产物包含两种语言资源且不依赖源码目录；运行 `uv run pytest tests/unit/test_packaging_spec.py -q`。
- [ ] **Step 2：完整自动验证。** 所有命令使用新鲜输出且退出码为 0：

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
uv run alembic upgrade head
npm --prefix web ci
npm --prefix web run check:i18n
npm --prefix web run test:unit
npm --prefix web run check:api
npm --prefix web run build
npm --prefix web run test:e2e
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1
```

- [ ] **Step 3：安全与追踪反查。** 逐行核对 I18N-01～18；搜索 locale 进入数据库/job/draft/log、用户数据被翻译、缺键回退报警、旧 Shell 签名、旧中文元数据和未登记硬编码。比较语言切换前后去敏工程副本的 DST/DWG hash 与 mtime。
- [ ] **Step 4：执行 G9。** 在打包后的真实 Windows 桌面壳分别验证：中文显示语言、英文显示语言、非中英显示语言、显式设置覆盖、设置读取失败降级、保存成功/失败、`dst/template/exe/dll` 过滤器与取消、英文窄屏/200%、发布与任务不中断。记录操作者、系统语言、版本、commit、结果和截图。
- [ ] **Step 5：收口状态。** 自动验证与 G8 通过后记录 G7/G8；只有用户真实桌面确认才关闭 G9。无未关闭 P0/P1 且矩阵全部有证据时将本计划改 `completed`；否则保持 `active` 并准确记录剩余项。
- [ ] **Step 6：最终提交。** 更新 Spec/索引/changelog 和实际验证，提交 `完成多语言支持验收与交付记录`。

## 批次回退与失败处理

- 批次一失败：保持中文现状与旧设置响应，不在未提交设置下切换；不得让设置读取失败阻断工作区。
- 批次二失败：已迁移域继续使用唯一 i18n，未迁移域保持既有中文；不得建立第二实例或局部翻译器。
- 批次三失败：保留迁移兼容字段并停止发布，修复调用方后再删除；不能用运行时回退掩盖缺键。
- 批次四失败：计划保持 `active`，记录具体环境/缺陷；不得把浏览器模拟写成 G9 通过。

## G6 计划自审

- I18N-01～I18N-18 每项至少对应一个实施任务和自动测试、G8 或 G9 证据。
- 类型链一致：`ui_locale` 仅三值；有效 locale 仅两值；setting key、error code、message key、file kind 全程稳定，翻译正文只在前端资源。
- 状态链一致：设置编辑缓冲 → PUT 成功 → 新快照 → locale 切换；所有失败分支都不提交 locale。
- 依赖方向一致：domain/application 不依赖本地化；接口层产生稳定 key/参数；Vue 负责显示语言。
- 路径安全一致：`localized_description` 不能决定扩展名，Python 只认可四种 `file_kind`。
- 已明确而未伪装为自动通过的边界只有真实 WebView2 系统语言、原生文件对话框和打包桌面体验，统一留给 G9。
- 计划不含未决占位标记、省略接口或需实施者重新决定的产品语义。

## 实际验证

2026-09-09：计划建立，状态 `proposed`；G4 已由用户确认，G5 技术映射通过，G6 追踪矩阵与任务拆分通过。尚未修改生产代码，也未执行 G7～G9。实施时按批次追加日期、commit、实际命令/退出码、测试数量、G8 证据、G9 操作者与结果、跳过理由和偏差裁决。
