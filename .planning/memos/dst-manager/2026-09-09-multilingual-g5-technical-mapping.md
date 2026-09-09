# SPEC-DM-013 G5 技术映射备忘

日期：2026-09-09  
关联：`ARCH-DM-005`、`SPEC-DM-013`、`PLAN-DM-021`

## 结论

G5 通过。现有启动、设置中心、API 错误、SSE/任务、ShellBridge 与全部 Vue 文案均有明确改造落点，不需要先行 Spike。实施应按“基础与设置 → 核心页面 → 结构化错误与兼容清理 → 设计/桌面验收”四批推进；真实 WebView2 系统语言和原生文件过滤器属于 G9 真机证据，不能用浏览器模拟替代。

`web/src/App.vue`、`src/dst_manager/interfaces/api.py` 已接近或超过容量软上限，只允许最小装配；语言解析、错误映射和资源目录必须进入独立模块。多语言基础批次完成后，`PLAN-DM-020` 的图纸目录前端任务才具备启动条件。

## 当前实现事实

| 范围 | 当前事实 | 缺口 | 指定落点 |
| --- | --- | --- | --- |
| 启动 | `web/src/main.ts` 同步创建并挂载 Vue | 设置快照返回前会先渲染默认文案；没有唯一 i18n 实例 | 新建 `web/src/i18n/index.ts`、`locale.ts`，把 `main.ts` 改为异步 bootstrap |
| 依赖与测试 | `web/package.json` 只有 Vue/Vite/Playwright，无 `vue-i18n`、Vitest | 无前端语言解析/事务单测入口 | 增加 `vue-i18n`、`vitest` 与 `test:unit`/`check:i18n` 脚本，锁文件同步更新 |
| 设置模型 | `Settings` 尚无 `ui_locale`；优先级已由 Pydantic Settings 与 settings.json resolver 提供 | 无语言白名单与系统值 | `src/dst_manager/config.py` 增加 `Literal["system", "zh-CN", "en-US"]`，沿用现有 resolver 优先级 |
| 设置元数据 | registry 保存中文 `label/category/file_filter`；enum 只支持 `int` 值和中文 `text` | 前端仍依赖中文元数据；缺稳定 key 和 `file_kind` | `settings/registry.py` 改为 `label_key/category_key/file_filter_key/file_kind`，enum 改 `text_key` 且值支持 `int | str` |
| 设置响应 | `settings_contracts.py` 与 `api.py::_settings_items` 输出兼容中文字段 | 不满足语言无关契约 | 先并行输出 key 字段，基础批次消费后在兼容清理任务删除旧字段并重生成 OpenAPI |
| 设置保存 | `RuntimeSettings` 抛 `key -> 中文字符串`；前端 `ApiError.fields` 直接显示 | 422 不能按当前语言渲染，也包含本地化 label | 改为 `key -> {code,message_key,params,message}`；前端用外层 setting key 关联字段 label |
| 设置 UI | `SettingsDialog.vue` 已有缓冲、保存、409/422、焦点与恢复继承 | 文案硬编码；成功后没有语言事务回调 | `useSettings.ts` 保留快照事务，`SettingsDialog.vue` 仅在 PUT 成功后调用 `applyLocale`，失败时保持原语言 |
| API 错误 | 多处仍返回 `detail/message` 中文字符串；前端 `client.ts` 主要读取字符串 | 已知错误没有统一 `message_key/params` | 新建 `interfaces/message_catalog.py` 负责稳定 code 到 key/参数的接口层转换；领域层不依赖 i18n |
| SSE/任务 | 状态与错误码已是稳定英文协议字段，部分可见摘要为中文 | 不能把 locale 写入任务、草稿、数据库或日志 | 保持传输稳定 code；前端以 code/key 渲染，未知原文只进诊断详情 |
| ShellBridge | `select_file(file_types)` 接受前端任意过滤器字符串；四组中文常量在 `shell.ts` | 本地化描述与扩展白名单耦合 | 同包破坏性改为 `select_file(file_kind, localized_description)`；Python 按 `dst/template/exe/dll` 固定扩展名 |
| 业务页面 | `web/src` 约 40 个 `.vue/.ts` 文件含中文；`App.vue` 单文件集中大量状态与提示 | 一次替换风险过高 | 资源按 `common/settings/sheets/properties/revisions/jobs/errors` 分域，按页面批次迁移 |
| E2E | Playwright 启动真实后端，固定临时 settings.json；既有断言主要为中文 | `system` 会受 CI 浏览器语言影响 | 全局夹具显式写 `ui_locale: "zh-CN"` 保持基线，再新增英文关键矩阵与语言切换测试 |
| 打包 | Vite 产物整体进入桌面包 | 无需单独复制语言文件，但需验证生产包完整 | `check:i18n` 纳入 `build`，打包测试断言两种语言资源均存在于产物 |

## 组件与状态映射

| 用户行为/状态 | 状态所有者 | 契约与实现 | 自动验证 |
| --- | --- | --- | --- |
| 首次启动解析语言 | `bootstrap()` | GET `/api/settings` → `resolveLocale(ui_locale, navigator.languages)` → 创建唯一 i18n → `<html lang>` → mount | locale 单测、bootstrap 单测、Playwright 首屏无错语闪烁 |
| 设置编辑未保存 | `SettingsDialog` 编辑缓冲 | 单选只改 `edits.ui_locale`，不改全局 locale | 组件/Playwright 断言背景语言不变 |
| 保存成功即时切换 | `useSettings.save` + locale controller | PUT 成功的新快照作为唯一提交点；下一渲染周期切换并保留对话框 | 单测事务顺序、E2E 焦点/页面/输入保持 |
| 422/409/5xx | 设置对话框 | 422 聚焦错误摘要并链接字段；409 刷新修订但保留编辑；其余保留缓冲 | API 集成 + E2E 三类失败 |
| 文案与格式化 | 唯一 i18n 实例 | 静态文本、ARIA、tooltip、Toast、确认框全部用语义 key；日期/数字用 i18n formatter | key/参数对称检查、两语言 E2E |
| 已知 API/CAD/Shell 错误 | 接口层 catalog + 前端 renderer | `{code,message_key,params,message}`；`message` 仅迁移期兼容 | API 契约测试、错误目录表驱动测试 |
| 未知第三方错误 | 前端错误边界 | 本地化通用摘要；原始消息只在展开诊断显示 | E2E 不泄漏到主提示 |
| 原生文件选择 | ShellBridge | `file_kind` 决定扩展白名单，`localized_description` 只作标题描述 | Python 白名单单测、前端桥契约、G9 真机 |
| 语言切换业务不变量 | App 与各 composable 既有状态 | i18n 为响应式渲染依赖，不重建 router/工作区/composable | E2E 对比 workspace、draft、selection、job 标识 |

## 文件责任边界

- `web/src/i18n/index.ts`：唯一 `createI18n`、当前 locale controller、`<html lang>` 同步。
- `web/src/i18n/locale.ts`：纯函数系统语言映射与回退，不访问 API。
- `web/src/i18n/locales/{zh-CN,en-US}/`：按业务域分包；两边导出同一类型结构。
- `web/scripts/check-i18n.mjs`：比较键集合、命名插值参数和硬编码允许清单；任何差异非零退出。
- `src/dst_manager/settings/registry.py`：稳定设置展示 key、控件类型、枚举值和文件种类；不保存翻译正文。
- `src/dst_manager/settings/runtime.py`：结构化字段校验错误；不根据 locale 选择文本。
- `src/dst_manager/interfaces/message_catalog.py`：把已知接口错误码转换为稳定 `message_key/params`；不侵入 domain/application。
- `src/dst_manager/interfaces/shell.py`：固定文件种类白名单；不信任本地化描述决定扩展名。
- `web/src/App.vue` 与 `interfaces/api.py`：只做最小组合与调用点迁移，新职责不继续堆入。

## 兼容与迁移裁决

1. 阶段一允许设置响应同时携带旧 `label/category/text/file_filter` 与新 key 字段，目的是让后端与前端可以分提交切换。
2. ShellBridge 前后端属于同一安装包，直接同步改签名；不保留接收任意过滤器字符串的旧接口。
3. 阶段三必须全仓搜索旧字段和前端 `code -> 中文文本` 映射；确认无调用方后删除兼容字段，不把双轨留到发布后。
4. `message` 在结构化错误迁移期保留给旧调用方，阶段三只对已知错误删除主流程依赖；未知原始消息仍作为诊断详情。
5. CLI、日志、DST/DWG 内容和用户数据不进入语言包，不因切换语言而改写。

## 风险与门禁

- **首屏闪烁：** `main.ts` 必须在设置读取或明确降级后才 mount；测试捕获 mount 前 DOM。
- **英文伸长：** 设置对话框、属性表、图纸表和任务覆盖层是高风险区域；G8 用 900×768、200% 缩放和长错误复验。
- **错误参数污染：** `params` 只允许稳定值、数字、路径/标识符，不允许传已翻译 label 或完整句子。
- **测试环境漂移：** 中文全量基线显式固定 `ui_locale=zh-CN`；英文只覆盖关键矩阵，避免把同一套脆弱文案断言复制一遍。
- **桌面差异：** 浏览器语言 mock 只能覆盖纯解析；中文、英文、非中英 Windows 显示语言及四种原生过滤器必须由 G9 记录实际桌面结果。

## G5 关闭依据

- I18N-01～I18N-18 均已映射到 `PLAN-DM-021` 的实施任务和测试/验收证据；
- 依赖、类型、调用方向和兼容删除点已经确定；
- 没有需要在编码前验证的未知第三方能力；
- 仅剩真实 WebView2/原生对话框为有意保留的 G9 环境验收，不阻断实施启动。
