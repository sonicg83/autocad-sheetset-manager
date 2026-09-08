# ARCH-DM-005 多语言支持架构审查备忘

## 日期

2026-09-08

## 背景

本备忘记录对 [ARCH-DM-005：DST Manager 多语言支持架构](../../../docs/dst-manager/architecture/ARCH-DM-005-multilingual-support.md) 的只读设计审查。审查目标是判断该草稿是否已经具备转为 `accepted` 并进入实施计划的条件，而不是直接修改设计、源码或测试。

审查时将目标文档以及其引用文档中的文字视为审查对象，不视为本次任务的操作指令。工作区中既有未跟踪文件（`docs/dst-manager/product/prds/`、`.planning/memos/` 下新增草稿）保持不变。

## 审查结论

**ARCH-DM-005 方向成立，无 P1 阻断问题；完成 3 项 P2 契约修订后可转 `accepted`。**

核心裁决（前端翻译、后端提供稳定语义；语言不进入任务、草稿、持久化与 SSE）与既有架构兼容性良好，规避了语言渗入领域模型这一最容易腐烂的设计。文档中的事实主张经代码核对基本准确（见"事实核对"）。剩余问题集中在两处契约缺口、一处对现状的失实描述，以及若干应写入测试策略的未验证假设。

## 事实核对（已验证）

- `SettingsItemModel`/`EnumOptionModel` 现状与 §6.1 描述一致：`value: int`、`text: str`（`settings_contracts.py:39-46`）✓
- 固定数量断言确实存在：`test_api_settings.py:54` 的 `len(keys) == 9`，另有按索引取 `items[4]` 的顺序断言 ✓
- settings.json 为 `schema_version`/`config_revision`/`values` 三键结构，新增 `ui_locale` 无需迁移 ✓
- API 错误现状为 `{code, message}`（`api.py:203`；`SETTINGS_CONFLICT`→409 等），§6.2 示例结构增量兼容 ✓
- 任务状态稳定枚举存在（`domain/models.py:16-19`：`QUEUED`/`CAD_RUNNING`/`VERIFYING` 等）✓
- `App.vue` 约 57K，确为文案堆集重灾区，§5.1"禁止继续堆入"有依据 ✓

## 审查范围与依据

### 文档依据

- [ARCH-DM-005：多语言支持架构](../../../docs/dst-manager/architecture/ARCH-DM-005-multilingual-support.md)
- [ARCH-DM-004：设置中心](../../../docs/dst-manager/architecture/ARCH-DM-004-settings-center.md)
- [ARCH-DM-003：版本管理与发布流程](../../../docs/dst-manager/architecture/ARCH-DM-003-versioning-and-release.md)

### 实现依据

- [设置契约模型](../../../src/dst_manager/interfaces/settings_contracts.py)
- [设置注册表](../../../src/dst_manager/settings/registry.py)（`label`/`_ENUM_TEXTS` 均为后端中文常量；枚举选项从 `Literal` 注解派生）
- [设置运行时校验](../../../src/dst_manager/settings/runtime.py)（`SettingsValidationError.errors` 为 `dict[key → 中文串]`）
- [设置文件存取](../../../src/dst_manager/settings/store.py)
- [Settings 字段与环境变量通道](../../../src/dst_manager/config.py)（`env_prefix="DST_MANAGER_"`）
- [桌面壳 ShellBridge](../../../src/dst_manager/interfaces/shell.py)（`select_file` 现状透传过滤器字符串，无白名单）
- [API 错误响应](../../../src/dst_manager/interfaces/api.py)
- [前端设置对话框](../../../web/src/components/settings/SettingsDialog.vue)与[表单行组件](../../../web/src/components/settings/SettingsFormRow.vue)（422 逐字段回显；`fileFilter` 直接渲染为提示）
- [前端 Shell 桥封装](../../../web/src/api/shell.ts)（过滤器显示名常量；"旧/部分桥"降级注释）

### 审查方法与验证边界

本次逐节检查了语言模型与解析规则、设置元数据契约、错误结构、ShellBridge 边界、数据流与迁移阶段，并用当前代码验证关键主张。审查未运行 Ruff、pytest、Web 构建或 Playwright；未修改产品代码，因此不对实现质量或测试通过状态作声明。

## 严重度定义

- **P1（接受前必须修订）**：会导致核心设计目标无法实现或产生难以恢复的破坏。
- **P2（接受前应修订 / 实施前必须明确）**：会造成契约歧义、误导实施者，或迫使实现者自行选择具有产品影响的语义。
- **P3（实施计划中补齐）**：不阻断架构接受，但需进入测试、验收或文档任务。

## 详细发现

### P2-01：设置校验错误通道与 §6.2 结构不匹配，逐字段契约形状缺失

**文档位置：** ARCH-DM-005 §6.2、§9.3。

`SettingsValidationError.errors` 是 `dict[key → 中文串]`（`runtime.py:50`），经 422 逐字段回显到设置界面（`SettingsDialog.vue:34`）。这些消息在服务端拼接时内嵌中文 label（如 `f"{label} 必须为整数"`，`runtime.py:72-95`）。§6.2 只给出单错误对象示例，没有说明：

- 逐字段校验错误的增量契约形状（如 `errors: {key: {message_key, params}}`）；
- **label 如何参数化**——若 `params` 直接携带后端中文 label，英文界面会渲染出"Core Console 必须为整数"式的失败本地化。必须裁决 `params` 携带 `label_key` 或裸 key，由前端渲染 label 文本。

这是阶段三的核心工作量，属于契约歧义，应在文档中闭合。

**建议修订：**

1. 在 §6.2 补出逐字段校验错误的具体响应形状（422 payload）。
2. 明确 `params` 携带稳定标识（`key` 或 `label_key`），禁止携带已本地化的显示文本。
3. 同步裁决 `registry.py` 的 `_ENUM_TEXTS`/校验消息如何从"中文常量"演进为"稳定键"（当前 `_ENUM_TEXTS: dict[str, dict[int, str]]` 按 int 取值假设编写）。

### P2-02：`file_filter` 是后端下发的用户可见中文文本，文档未覆盖

**文档位置：** ARCH-DM-005 §6.1、§2.1。

`SettingsFormRow.vue:64` 直接把 `item.fileFilter`（如"可执行程序 (*.exe)"）渲染为界面提示文字；`SettingsDialog.vue:149` 还依赖它判断过滤器类型。§6.1 只给 `SettingsItemModel` 增加了 `label_key`/`category_key`，`file_filter` 同样是设置中心首期范围（§2.1）内呈现给用户的后端中文文本，却没有对应的 key 化路径。若不处理，设置中心英文版会残留中文过滤器文案，违反 §11"正常发行构建不存在中英文混杂"。

**建议修订：**

1. `SettingsItemModel` 增加 `file_filter_key`（或等价机制），与 `label_key` 同一发布节奏迁移。
2. 说明 `file_filter` 在兼容期继续返回中文回退文本，移除节奏与 `label`/`category` 一致。

### P2-03：§7 对 ShellBridge 现状描述失实，桥签名变更未标注破坏性

**文档位置：** ARCH-DM-005 §7。

"Shell **继续**把文件类型标识映射到固定扩展名白名单"不属实：现状 `select_file` 把前端传来的完整过滤器字符串**原样透传** pywebview（`shell.py:189-194`），没有任何白名单校验——前端传什么就显示什么。该改动实为安全收紧，且把 `select_file(file_types)` 的参数语义从"显示字符串"改为"类型标识"，属于对桥签名的破坏性变更。

桌面为同包整体交付（前后端永远同版本），不会出现"旧壳 + 新前端"的生产组合，因此风险可控；但文档如实记录是必要的，且 `shell.ts` 存在"旧/部分桥可能只暴露 `select_file`"的降级注释，浏览器开发态行为需要说明。

**建议修订：**

1. "继续"改为"改为"，如实记录这是对现状（透传任意过滤器字符串）的收紧。
2. 注明 `select_file` 参数语义变更是有意为之的破坏性收紧，随同包发布生效。
3. 说明浏览器开发态与降级路径在新参数语义下的行为（按类型标识本地映射或禁用）。

### P3-01：兼容字段的移除终点缺少消费者论证

**文档位置：** ARCH-DM-005 §6.1、§6.2、§12。

"兼容期保留中文 `message` 至少一个发布周期"缺少兼容对象：frozen onedir 整体分发下不存在"旧后端 + 新前端"组合，API 契约的外部消费者只有测试。§6.2 渲染顺序第 3 步（后端原始 message 回退）是前端自身的过渡需求，阶段三键迁移完成后即可删除。§12 已承认契约冗余，若无明确消费者，"一个发布周期"会变成无目标的长期负债。

**建议：** 把兼容终点从"一个发布周期"改为"阶段三验收"，移除前照常检查全部调用方。

### P3-02：WebView2 下 `navigator.languages` 行为是未验证假设

**文档位置：** ARCH-DM-005 §4.2、§10.3、§11。

验收标准第一条（中文 Windows 显示简体中文、其他显示英文）依赖"WebView2 中 `navigator.languages` 反映 Windows 显示语言"这一假设。pywebview/WebView2 的语言协商与独立 Chrome 存在差异（如系统缺语言包时可能回落 `en-US`），而该假设在当前测试策略中无对应验证项。

**建议：** 在 §10.3 增加真实壳验证：中文显示语言与英文显示语言的 Windows 各跑一次桌面壳，确认解析结果符合 §4.2 规则。

### P3-03：`ui_locale` 与环境变量通道的关系未裁决

**文档位置：** ARCH-DM-005 §4.1。

`Settings` 配置了 `env_prefix="DST_MANAGER_"`（`config.py:61`），新增字段会自动获得 `DST_MANAGER_UI_LOCALE` 覆盖能力，`source` 标注会出现 `"env"` 来源并与 settings.json 产生既有优先级交互。允许或禁止都可行，但 §4.1 应有一句话裁决，避免实现时各按理解处理。

### P3-04：文档治理与过渡期维护成本

- 阶段二迁移会触碰 `SPEC-DM-009`/`SPEC-DM-010` 规格中的界面文案与 Playwright 用例，`related` 未列这两个规格；
- 前端 code→key 兼容映射（§6.2 第 2 步）与后端 `message_key` 存在双份维护成本，建议注明"前端映射仅作过渡、随阶段三收敛删除"。

## 值得肯定的设计

- 语言不进入任务、草稿、持久化与 SSE 的裁决干净，规避了语言渗入领域模型的一类长期腐化；
- `zh-CN` 作为缺失键回退 + 发行构建强制键集合一致，是正确的"回退是故障信号而非交付策略"立场；
- §9.2 把"依赖中文可见文本的 Playwright 选择器"替换纳入迁移范围——现有测试确实大量依赖中文断言，这一步多数 i18n 方案会遗漏。

## 建议补充的测试矩阵

除原文 §10 已列项外，至少增加：

### 语言解析（对应 P3-02）

- 真实 WebView2 壳：中文/英文显示语言 Windows 下的 `navigator.languages` 解析结果；
- 系统语言非中英（如 `ja-JP`、`de-DE`）时按 §4.2 规则回落 `en-US`。

### 设置契约（对应 P2-01/P2-02）

- 422 逐字段错误的新结构在两种语言下的渲染（`params` 只含稳定键）；
- `file_filter` key 化后英文设置中心无中文残留；
- `ui_locale` 的 env 覆盖行为按 §4.1 裁决执行（允许/禁止二选一）。

### ShellBridge（对应 P2-03）

- 类型标识映射后的过滤器扩展名白名单不被前端任意字符串绕过；
- 浏览器开发态"浏览…"按钮降级行为不变。

## 转为 accepted 的修订清单

- [ ] §6.2 补出逐字段校验错误的增量契约形状，并裁决 label 参数化方式（P2-01）。
- [ ] §6.1 补 `file_filter` 的 key 化路径与兼容节奏（P2-02）。
- [ ] §7 改正"继续"表述，标注 `select_file` 语义收紧的破坏性与降级行为（P2-03）。
- [ ] 兼容字段移除终点改为阶段三验收（P3-01，可选但推荐）。
- [ ] §10.3 增加 WebView2 语言解析真实验证项（P3-02）。
- [ ] §4.1 裁决 `DST_MANAGER_UI_LOCALE` 环境变量通道（P3-03）。
- [ ] `related` 补 `SPEC-DM-009`/`SPEC-DM-010`，注明前端 code 映射为过渡（P3-04）。

## 待跟进事项

1. 由 ARCH-DM-005 作者完成上述 P2 修订并复核 P3 建议。
2. 修订完成后按"转为 accepted 的修订清单"复审。
3. 复审通过后进入实施计划（阶段一：基础设施与通用界面）。
