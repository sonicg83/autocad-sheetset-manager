# PLAN-DM-021 多语言支持实施计划审查备忘

## 日期

2026-09-09

## 背景

本备忘记录对 [PLAN-DM-021：多语言支持实施计划](../../plans/dst-manager/PLAN-DM-021-multilingual-support.md) 的只读审查。审查在计划 `proposed` 状态、开工前进行，目标是把契约缺口和执行偏差在执行前修掉。

审查对照 [ARCH-DM-005](../../../docs/dst-manager/architecture/ARCH-DM-005-multilingual-support.md)、[SPEC-DM-013](../../../docs/dst-manager/specs/SPEC-DM-013-multilingual-ui.md)、[G5 技术映射](../../memos/dst-manager/2026-09-09-multilingual-g5-technical-mapping.md) 与 [PLAN-DM-020](../../plans/dst-manager/PLAN-DM-020-sheet-catalog-builtin-extension.md) 前置门禁逐条核对追踪矩阵和 12 个任务，并对计划引用的既有代码事实做了逐项核实（注册表结构与顺序、422 结构、ShellBridge 签名、App.vue 调用点、启动挂载、E2E 夹具、打包脚本等）。

## 审查结论

**计划质量很高，可以进入执行：3 项重要偏差（其中 1 项在严格按 Files 执行时必然漏改）与 4 项建议应在开工前修订；无流程级阻塞缺口。** 追踪矩阵 I18N-01～18 与 SPEC §4 需求域一一对应，批次划分与 ARCH §9 四阶段一致，语言模型、保存事务、错误结构、ShellBridge 契约与兼容删除窗口均对齐。

## 重要项（开工前建议修订）

### 1. 设置中心 exe/dll「浏览」迁移锚点缺失（接近阻塞）

Task 4 目标写明"四种 file_kind 全部迁移"，但 Files 与步骤只锚定 App.vue 的 dst/template 调用点与 `main.spec.ts`/`sheets-folder.spec.ts`。而：

- `SettingsDialog.vue:149` 的 `onBrowse` 用 `item.fileFilter?.includes("exe")` 推导类型——正是 ARCH-DM-005 §6.1 禁止的反模式；
- `shell.ts` 的 `selectSettingsPath("exe"|"dll")` 仍以中文字符串过滤器数组调用 `bridge.select_file(...)`。

Task 4 换签 `select_file(file_kind, localized_description)` 后，设置中心 exe/dll 浏览会经旧签名调用而断裂（同包升级无旧壳兜底）。Task 3 的 Files 虽含 `SettingsDialog.vue`，但其步骤只写语言事务；Task 4 E2E 不含 `settings-dialog.spec.ts`。**按 Files 严格执行必漏。** 修订：Task 4 显式包含 onBrowse/selectSettingsPath 接线、`shell.test.ts` 单测与 settings-dialog 的 exe/dll 浏览断言，批次检查点补验设置中心浏览仍可用。

### 2. Task 4 的 TS 侧红灯无文件锚点

Step 1 声称"TS/E2E 断言中英文只改变描述"，但 Files 无新建 `.test.ts`。修订：Task 4 新增 `web/src/api/shell.test.ts`（复用 Task 2 装的 Vitest）。

### 3. `check:i18n` 门禁接入过晚（批次三 Task 10）

批次二（Task 5～8）迁移 6+ 域 ×2 语言共 10+ 资源，期间无键对称/插值参数一致性门禁，缺口靠人工与"批次绿灯"兜底，Task 10 一次性补扫成本高。修订：Task 2 先落最小版（仅键集合对称、非零退出、纳入 `build`），Task 10 再扩展允许清单、硬编码扫描与参数一致性。

## 建议补强

4. **bootstrap 无请求超时兜底**：SPEC I18N-04 只定义"读取失败"，未定义"请求挂起"；桌面壳下设置请求长期 pending 会导致 App 永不挂载。修订：Task 2 增加挂起超时（如 5s）按失败降级，并纳入 `bootstrap.test.ts`。
5. **`FieldErrorModel.params` 类型过窄**：`dict[str, str | int]` 不含 SPEC §6.2 提到的 `allowed_values`（列表）等参数。修订：定义为 `ParamValue = str | int | bool | list[str]` 联合。
6. **Task 10 反向扫描自我排除**：正则 `[一-龥]` 会扫到 `hardcoded-allowlist.json` 中可能含中文的条目本身。修订：扫描显式排除该清单文件。
7. **微型（保留现状）**：Task 10 Step 5 扫描命令未列 `settings_contracts.py` 等全部待删点；因删除发生在 Step 3、扫描仅为确认手段，可接受。

## 事实核对（已验证属实）

- REGISTRY 现 9 项、4 组分类，当前首项为 `autocad_2016_console`；`REGISTRY` 顺序即 API 稳定顺序，设置对话框按首次出现分组（`SettingsDialog.vue:102` 的 `groups`）→ "界面"放首位可行；`test_settings_registry.py` 无固定首位断言，插入首项安全。
- `SettingsValidationError.errors` 现为 `dict[str,str]` 中文；`api.py:491-492` 的 422 返回 `{"errors": ...}`，与 Task 1 结构化目标一致。
- `select_file(file_types: list[str])` 在 `shell.py:189`；`select_folder` 独立；无 `SAVE_DIALOG`。
- App.vue 恰好 4 处 `select_file`：DST×1（`selectAndOpenDst`）、TEMPLATE×3（`selectTemplateFile`/`selectSubsetTemplateFile`/`selectBaseTemplateFile`）。✓
- `shell.ts:16-28` 四个中文过滤器常量；`SettingsDialog.vue:149` 存在 ARCH 禁止的类型推导。✓（重要项 1 的直接证据）
- `main.ts` 为同步挂载、无 i18n；`web/src` 无 `i18n/` 目录；`package.json` 无 vue-i18n/vitest 与 `test:unit`/`check:i18n` 脚本。✓
- `global-setup.ts` 以 `DST_MANAGER_SETTINGS_PATH` 隔离并写空 values 的 settings.json，`fixtures/settings.ts` 的 `writeSettingsFile` 可写 `ui_locale` → Task 2"显式写 zh-CN 固定基线"可行。✓
- api.py 512 行、App.vue 683 行（>500 软上限）与"只允许最小装配"一致；responses.py 511 行，Task 9 已预包容量的分支。✓
- 验证命令依赖齐备：`web/package-lock.json`、`uv.lock`、`alembic.ini`、`scripts/export_openapi.py`、`scripts/build_release.ps1`、`packaging/dst-manager.spec`、`tests/unit/test_packaging_spec.py`；Task 1/4/9/12 引用的 Python 测试文件均存在。✓
- 冻结截图实际位于 `docs/dst-manager/specs/assets/SPEC-DM-013/`（相对 SPEC 链接正确）；Demo HTML 含场景切换与中英/深浅主题。✓
- DM-020 Task 10 前置 = 唯一 i18n 实例 + 两语言资源装载，批次一 Task 2 恰好提供；DM-020"实际验证"与[门禁待办](../../todos/dst-manager/2026-09-09-arch-dm-005-implementation-gates.md)均已记录解除条件。✓

## 一致确认（核对过且对齐的需求域）

批次划分与 ARCH §9 四阶段一一对应；资源八域（common/settings/shell/sheets/properties/revisions/jobs/errors）与 ARCH §5.1 一致；12 任务均为 red→green、逐任务更新 changelog 并独立提交；追踪矩阵 I18N-01～18 与 SPEC §4 逐条对应且每行有任务/测试/G8/G9 锚点；语言解析链（显式 → 系统映射 → zh-CN 回退）、保存提交点（PUT 成功）、409/422/5xx 保持原语言、file_kind 固定扩展名、兼容字段三阶段删除窗口、SSE 稳定码、领域层不依赖 i18n —— 均与 ARCH-DM-005/SPEC-DM-013 一致；唯一留白（真实 WebView2 系统语言、原生文件对话框、打包桌面体验）按 G9 记录，未伪装为自动通过。

## 修订处理记录

2026-09-09 已完成开工前计划修订，未修改规范、源码或测试：

- 重要项 1 已写入 Task 4：`SettingsDialog.vue` 浏览接线（`file_kind` + 本地化描述）、`web/src/api/shell.test.ts`、`web/tests/e2e/settings-dialog.spec.ts` 的 exe/dll 浏览断言进入 Files/步骤，批次检查点补验设置中心 exe/dll"浏览"仍可用；Task 3 注明浏览接线不随语言事务提前改。
- 重要项 2 已写入：Task 4 新增 `shell.test.ts`，红灯/绿灯命令纳入 `test:unit`。
- 重要项 3 已写入：Task 2 先落 `check:i18n` 最小版（键集合对称、纳入 `build`），Task 10 改为"扩展允许清单、硬编码扫描与参数一致性"。
- 建议项 4～6 已写入：Task 2 bootstrap 挂起超时降级（5s）、Task 1 `FieldErrorModel.params` 白名单（str/int/bool/list[str]）、Task 10 反向扫描排除允许清单自身。
- 建议项 7 保留现状（扫描为确认手段，删除点已在 Step 3 收口）。
- PLAN-DM-021 继续保持 `proposed`，待用户选择执行方式后再转 `active`；本次修订不触发 G2～G6 重开。