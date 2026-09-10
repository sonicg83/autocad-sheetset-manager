---
id: GUIDE-DM-004
title: 多语言与本地化配置 SOP
status: review
document_kind: guide
owners:
- dst-manager
created: 2026-09-10
updated: 2026-09-10
related:
- ARCH-DM-005
- SPEC-DM-013
- PLAN-DM-021
- GUIDE-DM-003
---

# 多语言与本地化配置 SOP

> 定位：指导后续开发在 DST Manager **新增文案、新增错误、本地化设置项、接入原生对话框、扩展现有语言**时的标准操作流程。语言架构方向以 [ARCH-DM-005](../architecture/ARCH-DM-005-multilingual-support.md) 为准，用户可见行为与验收以 [SPEC-DM-013](../specs/SPEC-DM-013-multilingual-ui.md) 为准；本文是执行层操作手册，与上游冲突时以上游为准。
> 首期语言：简体中文 `zh-CN`（回退基线）与英文 `en-US`。后续新增语言（如 `ja-JP`）按本指引 §6 SOP-E 执行。

## 核心不变量（任何改动不得破坏）

1. **唯一 i18n 实例**：全应用只有一个 `vue-i18n` 实例（`web/src/i18n/index.ts`），语言状态全部经它流转；缺键运行时回退 `zh-CN`。
2. **语言不入持久层**：`ui_locale` 只作为普通设置写 `settings.json`；语言不得进入草稿、任务、数据库、操作日志、DST 或 DWG。
3. **键对称硬门禁**：中英文 8 个域的键集合与命名插值参数集合必须完全一致，由 `check:i18n` 在构建期强制，运行时回退不是交付策略。
4. **稳定标识 + 前端翻译**：后端只提供稳定 `code`、`message_key`、`params` 与设置元数据键；正文翻译只存在于前端语言包。
5. **用户数据原样**：路径、图号、布局名、属性名/值、版本号、错误码、状态码、协议字段原样展示，不做区域化转换（I18N-16）。

## 文件与链路总览

| 链路 | 权威文件 | 改动入口 | 自动门禁 |
| --- | --- | --- | --- |
| 语言解析与切换 | `web/src/i18n/locale.ts`、`index.ts`、`format.ts` | 新增语言时改解析逻辑 | `locale.test.ts`、`bootstrap.test.ts` |
| 前端语言包 | `web/src/i18n/locales/{zh-CN,en-US}/`（8 域） | 增删键/文本 | `check:i18n` + 硬编码扫描 |
| 后端错误目录 | `src/dst_manager/interfaces/message_catalog.py` | 新增已知错误码 | `tests/unit/test_message_catalog.py` 交叉守护 |
| 设置元数据 | `src/dst_manager/settings/registry.py`、`config.py` | 新增/修改配置项 | `test_settings_registry.py`、`test_api_settings.py` 等 |
| ShellBridge 原生对话框 | `src/dst_manager/interfaces/shell.py` + `web/src/api/shell.ts` | 新增文件种类 | `tests/unit/test_shell.py`、`web/src/api/shell.test.ts` |

语言包 8 个域：`common`、`shell`、`sheets`、`properties`、`revisions`、`jobs`、`settings`、`errors`。每个域在中英文目录各一个 `.ts` 文件，构建期静态装配（`index.ts` 显式 import，禁止动态 import/fetch 语言包）。

## 1. 前置概念：语言如何解析与切换

### 1.1 解析规则（`web/src/i18n/locale.ts`）

`ui_locale` 只允许 `system`、`zh-CN`、`en-US`，默认 `system`（后端白名单校验）。生效语言 `EffectiveLocale` 只可能是 `zh-CN` 或 `en-US`：

1. 显式 `zh-CN`/`en-US` 直接采用；
2. `system` 时读 `navigator.languages`（为空再读 `navigator.language`）；
3. 系统语言主子标签为 `zh`（`zh-TW`、`zh-Hans` 等）→ `zh-CN`；
4. 其他可识别非中文语言（`ja-JP`、`de-DE`…）→ `en-US`；
5. 无法读取或全部不可识别 → 回退 `zh-CN`。

该函数是纯逻辑，必须保持可单测（`locale.test.ts`）。新增语言时这里与后端 `config.py` 的 `Literal` 白名单、`registry.py` 的 `_ENUM_KEYS` 三处同步（见 §6）。

### 1.2 启动与切换（`web/src/i18n/index.ts`）

- `bootstrap()`：挂载前先请求 `GET /api/settings`（超时 5s）读取 `ui_locale` → `resolveLocale` → `applyLocale` → 再挂载 Vue，避免首屏语言闪烁（I18N-04）；读取失败不阻断启动，按 `system` 规则降级。
- `applyLocale(locale)`：同步 `i18n.global.locale.value` 与 `<html lang>`。设置保存成功（`PUT /api/settings` 200）后复用此函数即时切换；保存失败、取消、`409`/`422`/网络错误一律不切换（I18N-05/I18N-06）。
- 语言名保留**自称形式**：`settings.locale.zhCN="简体中文"`、`enUS="English"`、`systemCurrent="跟随系统（当前：{current}）"`，用户误切语言后仍能识别。

## 2. SOP-A 新增 / 修改前端文案

### A-1 判定：这个文本该不该进语言包

| 判定 | 结论 |
| --- | --- |
| 用户可见静态文本、ARIA、tooltip、placeholder、Toast、确认文案、状态名 | **进**，用语义键（I18N-07） |
| 原生文件对话框标题/过滤器显示名 | **进**，作为 `localized_description` 传桥（§5） |
| 日志、CLI 输出、开发排障详情、代码注释、文档 | **不进**，保持原文 |
| DST/DWG 中的图号、布局名、属性名/值、路径、用户输入 | **不进**，原样展示（I18N-16） |
| 第三方固定名称、错误码、协议字段、API 路径、版本号 | **不进**，原样展示 |

### A-2 选择域与键命名

- 键用稳定语义路径：`sheets.toolbar.addSheet`、`settings.locale.system`、`errors.settings.conflict`；**禁止用中文原文作键**。
- 归属域判断：按承载 UI 的功能域选择（外壳/导航/草稿栈 → `shell`；图纸页 → `sheets`；属性页 → `properties`；修订 → `revisions`；任务/进度 → `jobs`；设置中心 → `settings`；错误 → `errors`；通用 → `common`）。
- 一个功能域的文案尽量收在一个域文件内；不宜堆入 `App.vue` 或单个超大词典。

### A-3 双侧写两套资源文件

对 `web/src/i18n/locales/zh-CN/<domain>.ts` 与 `en-US/<domain>.ts` **同时**增删，保持结构完全对称：

```ts
// settings.ts（zh-CN）
export default {
  validation: {
    integerRange: "必须在 {min}–{max} 之间",
  },
  // …
} as const;

// settings.ts（en-US）
export default {
  validation: {
    integerRange: "Must be between {min} and {max}",
  },
  // …
} as const;
```

规则：

- 叶子必须是字符串，禁止数组叶子、对象叶子嵌套过深、空值；文件以 `as const` 收尾。
- **命名参数**用 `{name}` 占位，中英文同名同集合，由 `check:i18n` 强制一致（I18N-14）。
- **复数**用管道形式（vue-i18n v11）：`"1 command | {count} commands"`（中文通常单形态 `"{count} 条命令"`），调用点传第三个参数：`$t("shell.draft.commandCount", {count}, action.commands.length)`。
- **分隔符**属于可翻译内容（`common.listSeparator: "、"`），调用点不写死全角标点。
- **日期/数字**（`jobs.files.started` 等）经 `formatDateTime`（`Intl.DateTimeFormat` 按生效语言）格式化；业务标识、存储值与 API 负载保持原始格式，非法输入回退原值。
- 英文按比中文长 30%～60% 撰写，布局用弹性宽度/换行处理，不靠缩小字号。

### A-4 调用点

- 模板：`{{ $t("shell.draft.pendingSummary", {count, cursor, total}) }}`；
- 组合式 API：`const {t} = useI18n(); t("shell.errors.draftSaveFailed")`；
- **禁止在调用点拼接可翻译句子**（如 `` `${t("a")} ${t("b")}` ``），参数必须来自用户/业务数据原样值；词序不同、复数和介词的差异只能靠完整句子键承载；
- 开发态需要探测键是否存在时用 `i18n.global.te(key)` 再 `t(key, params)`（`web/src/api/client.ts` 的 `renderError` 即此模式）；
- 旧桥/旧结构允许的原始文本回退只适用于**未知第三方错误诊断**，不得作为正常界面翻译。

### A-5 硬编码中文检查

`check:i18n` 会扫描 `web/src`（排除 `locales/`、`*.d.ts`、`*.test.ts`）剥离注释后的字符串/模板文本中出现的 `[一-龥]`：

- **普通 UI 文案**必须改成语义键，禁止依赖绕过；
- 确属「用户数据示例 / 协议常量 / 必要品牌名」时登记 `web/src/i18n/hardcoded-allowlist.json`，条目 `{file, match?, reason}`，**`reason` 必须逐项注明原因**，禁止批量忽略或登记普通界面文案；
- 两处开发态诊断字符串（`index.ts` 设置读取超时、`useSettings.ts` 快照未加载）统一用英文（开发者诊断，非界面文案），不占用豁免清单。

## 3. SOP-B 新增后端错误码（用户可见错误）

已知会进入桌面界面的 API/CAD/Shell 错误在 `src/dst_manager/interfaces/message_catalog.py` 的 `CATALOG` 登记，与前端 `errors.ts` 的 `message_key` 一一对应（`tests/unit/test_message_catalog.py` 交叉守护：目录枚举、params schema 与占位符对称、类型白名单）。

### B-1 登记目录

```python
"CAD_VERSION_INVALID": _E("errors.cad.versionInvalid", {"cad_version": str}, "cad_version"),
```

- `message_key` 必须是前端 `errors.ts` 已存在的键；`param_schema` 只允许 `str/int/bool/list` 白名单类型，拒绝对象与本地化 label/完整句子；
- `detail_param` 声明从异常详情提取的稳定值（路径/标识/名称/编号；详情形态 `……：<稳定值>` 或 `CODE: <稳定值>`，句子型详情不登记提取）；
- 未知 code 由 `error_payload` 自动不携带 `message_key`，前端显示本地化摘要 `errors.ui.unknownSummary`，原文只进可展开诊断（`lastErrorDiagnostic`）。

### B-2 前端渲染（`web/src/api/client.ts`）

顺序：已知 `message_key` 且 `te()` 命中 → `t(message_key, params)`；否则 `errors.ui.unknownSummary` + 原文进诊断详情。**不要**在调用点重新拼后端 `message` 作为主提示；Shell 桥错误用 `localizedError(message_key, params, fallback)`。

### B-3 约束

- 目录只挂在接口层；application/domain 不导入目录、不依赖语言环境（日志继续记录稳定 code 与原始诊断）。
- 422 逐字段错误外层 code `SETTINGS_VALIDATION_FAILED`，字段键是**稳定设置 key**（如 `cad_max_parallel`），前端用该 key 的 `labelKey` 解析字段标签后，再把标签与 `min`/`max`/`allowed_values` 等结构化参数交给翻译函数；`params` 禁止携带已本地化的 label/枚举文本（I18N-10）。
- SSE 继续传输 `QUEUED`/`STAGING`/`CAD_RUNNING`/`VERIFYING`/`PUBLISHING` 等稳定状态码，由前端翻译状态名（I18N-12）。

## 4. SOP-C 设置项本地化

新增或修改设置中心配置项时，除遵循 [GUIDE-DM-003](GUIDE-DM-003-settings-config-sop.md) 外，必须提供五类稳定键：

### C-1 `registry.py` 登记键

```python
SettingsItemMeta(
    key="cad_max_parallel",
    label_key="settings.items.cadMaxParallel",     # 字段标题
    category_key="settings.categories.execution",  # 分组标题
    # path 控件才需要：
    file_filter_key="settings.fileFilters.executable",  # 过滤器显示名
    file_kind="exe",                                    # 固定扩展名种类，禁止用显示文本推导行为
)
```

- `label_key`/`category_key`/`text_key`/`file_filter_key` 都是前端键，翻译正文只存在语言包 `settings.ts`；注册表不得再存中文显示文本（兼容 `label`/`category`/`text`/`file_filter` 已在阶段三收敛删除）。
- 枚举选项在 `_ENUM_KEYS` 登记 `value → text_key`，选项值扩展为 `int | str`（如 `ui_locale` 的 `"system"`/`"zh-CN"`/`"en-US"`）；`ui_locale` 选项名保留自称形式。

### C-2 语言包配套

在 `settings.ts`（中英两套）补齐 `items.*`、`categories.*`、`enumOptions.*`、`fileFilters.*`、`validation.*` 对应键；`settings.locale.systemCurrent` 的 `{current}` 参数由前端传入当前解析结果。

### C-3 验证

`test_settings_registry.py` 断言稳定键唯一描述、枚举选项无 `text`；`test_api_settings.py` 断言 `label/category/file_filter/text` 不出现在响应；`test_settings_runtime.py` 断言 422 params 无本地化 label。

## 5. SOP-D ShellBridge 原生文件对话框

- 前端调用 `select_file(fileKind, localizedDescription)`：`fileKind` 只能是 `dst`/`template`/`exe`/`dll`；`localizedDescription` 来自 `common.shell.fileKinds.*`（如 `"DST 文件"`），**只作对话框显示描述**。
- 扩展名白名单由壳侧按 `file_kind` 在 `_FILE_KIND_PATTERNS` 固定拼接；前端任意字符串（包括被伪造的本地化描述）不能改变过滤器模式（I18N-13）。
- 文件夹选择走独立 `select_folder()`，不传描述。
- 桥缺 `select_file`/`select_folder` 方法时 `web/src/api/shell.ts` 返回 `undefined`，调用方（设置中心“浏览”按钮）禁用并提示手动输入路径；**不得**回退到旧的任意字符串过滤器透传，也不得用浏览器文件过滤器模拟 Shell 白名单。
- 新增文件种类：改 `shell.py` 的 `FileKind`/`_FILE_KIND_PATTERNS` + TS 侧 `ShellFileKind` 类型 + `common.shell.fileKinds.*`（中英两套）+ `shell.py`/`shell.test.ts` 测试。

## 6. SOP-E 新增语言（如 `ja-JP`）

> 首期架构只支持两种语言，`resolveLocale` 将其他可识别语言映射 `en-US`。新增语言属于架构级变更，先回 ARCH-DM-005 评审（解析规则、回退语义、验收矩阵），再按下列清单交付。

| # | 改动点 | 文件 |
| --- | --- | --- |
| 1 | 后端 `ui_locale: Literal["system","zh-CN","en-US","ja-JP"]` | `src/dst_manager/config.py` |
| 2 | 注册表 `_ENUM_KEYS["ui_locale"]` 增 `"ja-JP": "settings.locale.jaJP"` | `src/dst_manager/settings/registry.py` |
| 3 | 新建 `web/src/i18n/locales/ja-JP/` 8 个域文件，与 zh/en 完全对称 | `web/src/i18n/locales/` |
| 4 | TS 类型：`UiLocaleSetting`/`EffectiveLocale` 扩展；`index.ts` messages 装配 + import | `locale.ts`、`index.ts` |
| 5 | 解析规则：系统语言 `ja` → `ja-JP`；识别规则与回退基线更新 | `locale.ts` |
| 6 | 门禁：`check-i18n.mjs` 的 `REQUIRED_LOCALES` 加入 `ja-JP`，域集合/键集合/参数集合三方一致 | `web/scripts/check-i18n.mjs` |
| 7 | 语言包：`settings.ts` 增 `locale.jaJP`（自称名 `日本語`） | 语言包 |
| 8 | 测试：`locale.test.ts` 增解析用例；`bootstrap.test.ts` 增语言装配；Playwright 增关键矩阵（启动/设置/图纸/发布/错误，`--workers=1`） | 前端测试 |
| 9 | 打包守护：`tests/unit/test_packaging_spec.py` 断言生产 JS 同时嵌入全部语言资源 | 后端测试 |
| 10 | G9 证据：真实 pywebview/WebView2 验证对应 Windows 显示语言解析与四种文件过滤器 | 用户/验证者 |

新增语言后 `check:i18n` 的三方对称、`npm run build`、全量 e2e 必须全绿后才允许合入；G9 未执行前语言不能宣称交付完成。

## 7. 验证清单

| 改动类型 | 必跑命令 | 预期 |
| --- | --- | --- |
| 语言包 / 硬编码扫描 | `npm --prefix web run check:i18n` | 退出码 0，输出「中英文键与插值参数对称（N 键 / 8 域），web/src 无未登记硬编码中文」 |
| 解析 / 启动 / 封装单测 | `npm --prefix web run test:unit` | 全绿（含 `locale.test.ts`、`bootstrap.test.ts`、`shell.test.ts`） |
| 错误目录 / 设置元数据 | `uv run pytest tests/unit/test_message_catalog.py tests/unit/test_settings_registry.py tests/unit/test_settings_runtime.py tests/integration/test_api_settings.py tests/unit/test_shell.py -q` | 全绿 |
| 生产构建门禁 | `npm --prefix web run build` | `check:api` + `check:i18n` + `vue-tsc` + `vite build` 全通过 |
| 关键语言矩阵 | `npm --prefix web run test:e2e -- tests/e2e/i18n-workflows.spec.ts tests/e2e/i18n-visual-evidence.spec.ts --workers=1` | 全绿；全量 e2e 以 `--workers=1` 为准 |
| 全量回归 | `uv sync --dev`、`uv run ruff check .`、`uv run pytest -q`、`uv lock --check` | 全绿 |
| 真实桌面（新增语言/解析规则变更） | [MEMO-DM-026](../../../.planning/memos/dst-manager/PLAN-DM-021-multilingual-g9-checklist.md) 逐项 | zh/en/非中英显示语言 + 四类过滤器 + 取消行为 |

`npm run build` 已内置语言包门禁：任一缺失键/参数不一致/硬编码中文都会**阻断生产构建**（I18N-14），不允许用运行时回退掩盖。

## 8. 故障处理

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| `check:i18n` 报「en-US 缺少键 xxx」 | 单侧增删键 | 双侧同步增删；定位 `<域>.<键>` 与资源文件路径后补全 |
| 报「命名参数不一致：缺少 {param}」 | 中英文占位符集合不同 | 修正为同名同集合占位符，调用点参数名同步 |
| 报「域内重复键」 | 同域文件出现同路径键 | 合并或改名，避免跨域同名键静默合并歧义 |
| 报「web/src/... 出现硬编码中文：…」 | 新增界面文案未进语言包 | 改语义键；确属用户数据示例/协议常量/品牌名才登记 allowlist 并注明 reason |
| 构建通过但运行时回退 zh-CN | 生产构建绕过门禁或旧产物 | 以本地新鲜 `npm run build` 为准，检查 `check:i18n` 是否被跳过 |
| 保存语言后界面不变 | 保存失败 / 未以 200 为提交点 | 检查 `PUT /api/settings` 响应与 `applyLocale` 调用链；`409`/`422`/网络错误本就不切换 |
| `<html lang>` 未更新 | 切换未走 `applyLocale` | 语言切换唯一入口是 `applyLocale`，禁止在组件内直接改 `i18n.global.locale` |
| 英文布局溢出/阻断操作 | 英文伸长 30%～60% 暴露固定宽度 | 用弹性宽度/换行/`overflow-wrap:anywhere`，参考 `i18n-visual-evidence.spec.ts` 三视口断言 |
| 真实 WebView2 语言不反映 Windows 显示语言 | 解析来源不支持 | 按 ARCH-DM-005 §10.3：回架构审查，不得静默改用其他来源 |
| 新增 code 未显示本地化文案 | `message_catalog.py` 未登记或 `errors.ts` 缺键 | B-1/B-2 双向补齐，`test_message_catalog.py` 会在两侧不一致时失败 |

## 9. 反模式清单（勿犯）

- 用中文原文作翻译键；在调用点用 `t("a") + t("b")` 拼可翻译句子；
- 单侧增删键并把缺键留给运行时回退；
- 把语言写入草稿、任务、数据库、操作日志、DST/DWG，或在 SSE 事件 URL 携带语言；
- 在注册表、错误目录或 Shell 桥存中文显示文本、本地化 label 或完整句子；
- 用中文 `file_filter` 是否包含 `exe`/`dll` 推导行为，或向前端透传任意扩展名过滤器；
- 新增硬编码中文后不加 reasons 塞进允许清单；
- 绕过 `applyLocale` 直接改 `i18n.global.locale` / `<html lang>`；
- 新增语言时遗漏 `config.py`、`registry.py`、`check:i18n`、打包守护四处的任一同步点；
- 未执行真实 WebView2 验收就宣称多语言完成（浏览器 mock 不能替代 G9）。

## 10. 参考

- [ARCH-DM-005 多语言支持架构](../architecture/ARCH-DM-005-multilingual-support.md)：架构裁决与数据流
- [SPEC-DM-013 多语言界面与本地化契约规范](../specs/SPEC-DM-013-multilingual-ui.md)：用户可见行为、状态矩阵与验收
- [PLAN-DM-021 多语言支持实施计划](../../../.planning/plans/dst-manager/PLAN-DM-021-multilingual-support.md)：追踪矩阵与 G8/G9 状态
- [GUIDE-DM-003 配置中心配置项增删改 SOP](GUIDE-DM-003-settings-config-sop.md)：设置项生命周期上游流程
- [GUIDE-DM-001 前端功能设计与实施门禁清单](GUIDE-DM-001-frontend-design-implementation-gates.md)：L 级跨域改动的门禁要求