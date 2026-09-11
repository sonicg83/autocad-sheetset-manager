---
id: MEMO-DM-031
title: PLAN-DM-022 最终评审遗留缺陷登记（均属 PLAN-DM-020 范围，未修）
status: final
document_kind: memo
owners:
  - dst-manager
created: 2026-09-11
updated: 2026-09-11
related:
  - PLAN-DM-022
  - PLAN-DM-020
  - PLAN-DM-023
  - PLAN-DM-024
  - ARCH-DM-006
  - SPEC-DM-012
---

# PLAN-DM-022 最终评审遗留缺陷登记

## 1. 来源与验证边界

- 来源：PLAN-DM-022 最终评审（2026-09-11）。多代理正确性评审对候选发现逐条对证（10 项：6 CONFIRMED / 4 PLAUSIBLE / 0 REFUTED），其中 5 项正确性缺陷经复核确认（下表 F1～F5）。
- **范围归属**：5 项缺陷均不在 PLAN-DM-022 的改动文件内（DM-022 只动了 `web/src/components/settings/`、语言包与 e2e），全部位于 PLAN-DM-020（内置扩展平台与图纸目录）交付的代码。DM-022 本体结论不受影响，缺陷挂账到 DM-020 名下，本 memo 作为登记与后续分流的依据。
- 复核方式：F3、F4 由评审人独立读码抽查属实；F1、F2、F5 由验证代理带具体失败场景对证（CONFIRMED）。均未写修复、未跑新增测试。
- 同次评审还发现 1 项仓库卫生问题（见 §3）与 4 项潜在设计债（见 §4），一并留档但不计入本缺陷清单。

## 2. 缺陷清单（F1～F5，按影响排序）

### F1 扩展列表加载失败会绕过导航守卫丢弃未保存草稿（最高优先级）

- **位置**：`web/src/App.vue:115`（`openSettings` 触发的 `reloadExtensions()`），配合 `web/src/composables/useExtensions.ts:44-46`。
- **问题**：`reloadExtensions()` 的 catch 分支把扩展清成 `[]`；用户停在 sheet-catalog 标签页且草稿未保存时打开设置，一旦 `listExtensions()` 失败，`extensionPages`/`tabIds` 不再包含 `sheet-catalog`，`useShellTabs` 的 watch 会把 active 重置回 `sheets`——该路径**绕过** `guardSheetCatalogPage` 脏检查（停用路径有闸门，错误路径没有）。
- **后果**：`SheetCatalogView` 被卸载（无 KeepAlive，草稿是实例内状态），未保存草稿静默丢失。
- **修复方向**：加载失败时保留旧列表；成功刷新若使当前活动扩展页从可用页面集合消失，也必须在提交新列表和卸载页面前经过导航守卫。与 SC-15「停用不关窗」的闸门语义对齐。

### F2 保存授权桥接失败后导出状态永久卡死

- **位置**：`web/src/composables/useSheetCatalog.ts:536` 附近（`exportXlsx` 中 `await requestExtensionSave(...)`）。
- **问题**：该 await 不在任何 try/catch 内（try 块从执行段才开始，也没有 finally）。`src/dst_manager/interfaces/shell.py:275-276` 在保存对话框窗口未就绪时抛 `RuntimeError`，pywebview 把它变成 JS 侧 Promise 拒绝。
- **后果**：`exportState.phase` 永久停在 `exporting`，`exportReady` 要求 `phase !== 'exporting'`，导出/重试两个按钮全部死锁，直到页面重挂载，且无任何错误提示。
- **修复方向**：把授权请求纳入 try 或补 catch/finally，失败时转入错误态并展示可重试信息。

### F3 Shell 错误码缺 message_key，en-US 界面渲染原始中文

- **位置**：`src/dst_manager/interfaces/shell.py:247`、`257`、`268`（`EXTENSION_CAPABILITY_UNAVAILABLE` / `EXTENSION_NOT_FOUND` / `EXTENSION_ACTION_NOT_FOUND`）。
- **问题**：这三处 `shell_error` 只带硬编码中文 message，不带 `message_key`，对应键不在 `message_catalog.CATALOG` 中登记。
- **后果**：前端 `localizedError`（`useSheetCatalog.ts:546`）回退到 `grant.message`，en-US 用户看到原始中文串（如「保存授权通道未装配」）；而 `locales/en-US/errors.ts:122-128` 的现成译文不可达。违反 I18N-11「每个 UI 可见错误码必须登记」不变量。
- **修复方向**：补 `message_key` 并在 catalog 登记（en-US 译文已存在，只差接线）；顺带排查其余 `shell_error` 调用点（`shell.py:273`、`292`、`312` 同为裸 message）。
- **复核**：评审人独立读码属实。

### F4 内置模板保留名硬编码中文，en-US 唯一性守卫失效

- **位置**：`src/dst_manager/extensions/builtin/sheet_catalog/templates.py:92`（`_BUILTIN_TEMPLATE_NAME = "默认图纸目录（内置）"`）与 `:257`（`save_templates` 的 `seen_names`）。
- **问题**：服务端唯一性守卫只预置中文保留名；en-US 下前端渲染的是本地化名（`en-US/extensions.ts:7` 的 `Default catalog (built-in)`），`saveAs` 又没有客户端名校验。
- **后果**：en-US 用户能保存一个与内置条目**可见名称完全相同**的模板——下拉框出现两条不可区分的条目，守卫/冲突提示语义失效。
- **修复方向**：`template_id` 继续作为身份权威；当前 locale 下另存为与内置显示名碰撞时由前端拒绝，历史数据或直接 API 注入的碰撞项在下拉框追加“用户模板”标识。不能把语言包显示文案引入 Python 领域层，也不能只改用 ID 后仍留下两个不可区分的可见选项。
- **复核**：评审人独立读码属实。

### F5 `save_templates` 不校验 template_id 唯一，删除时一次带走两条

- **位置**：`src/dst_manager/extensions/builtin/sheet_catalog/templates.py:258`（只做 casefold 名字唯一）；`:328-332`（`delete_template` 按 id 过滤）。
- **问题**：直接 PUT 设置端点可以持久化两条名字不同但 `template_id` 相同的模板（`runtime.py` 的 `_save_catalog_templates` 只拒绝 None id）；前端 `removeTemplate`（`useSheetCatalog.ts:467`）也按 id 过滤。
- **后果**：一次删除会把两条同时移除，按 id 选择产生歧义。
- **边界**：当前 UI 自身产生不了重复 id，需直接调端点才触发——服务端不变量缺失，UI 不是缓解。
- **修复方向**：`save_templates` 内对 `template_id` 做唯一校验，与名字唯一同级别报错。

## 3. 同次评审的仓库卫生发现（已修复）

`.claude/worktrees/plan-dm-020-sheet-catalog` 曾在 `bae415d`（v0.3.5 发布提交）中作为 gitlink（mode 160000，指向本机 commit `7634cae`）被提交进仓库树；其他克隆会得到悬挂引用，违反 AGENTS.md 暂存规则。**2026-09-11 已随本 memo 登记同日修复**：`git rm --cached` 移除索引项并提交，`.gitignore` 补 `.claude/worktrees/` 规则；`git ls-files -s` 复核无 160000 条目。历史提交树（`bae415d` 及其后）中的 gitlink 记录不回改，以本节为准。

## 4. 潜在设计债（PLAUSIBLE，当前无触发路径，不挂账）

仅留档防止丢失，均不必单独立项，待相关文件下次被动时顺带处理：

1. `templates.py:337` `delete_template` 重建 `TemplateCollection` 时丢失 `unknown_schema_preserved` 标志，绕过「不得覆写更高 schema 设置」守卫（当前无生产调用方走该路径）。
2. `extension_api.py:89` `_error_response` 对未映射扩展码直接 `KeyError` → 500，`runtime.py:709-715` 对注册表码有同型守卫而 capability 路径没有。
3. `message_catalog.py:166` `_sanitize_params` 遇未登记参数抛 `ValueError`，`api.py` 的异常处理器未包 try——非 schema 调用方一出现就把 4xx 变 500。
4. `useSheetCatalog.ts:67` 未保存草稿导航守卫是模块级单例，第二个扩展页面接入该 API 会静默覆盖第一个页面的脏检查（当前 `pageRegistry` 只有一个条目）。

## 5. 分流建议

- F1、F2 是**用户可见的功能缺陷**（草稿丢失 / 按钮死锁），建议独立小计划或并入下一个 DM-020 系计划优先处理，不等 PLAN-DM-023（其范围是视觉收敛）。
- F3、F4、F5 涉及 DM-020 的后端契约与 i18n 不变量，可与 F1、F2 合并成一个「DM-020 遗留缺陷修复」批次；F3 与 I18N-11 的关系建议在修复时顺带复核 `shell_error` 全部调用点。
- §3 的 gitlink 清理已完成，无须再排。

## 6. 针对性复核结论与实施入口

2026-09-11 针对当前代码、调用链和测试进行二次复核：F1～F5 均确认存在；其中 F1 的边界扩展到“成功刷新后活动扩展变为非 AVAILABLE”，F4 重新定性为本地化显示碰撞而非 UUID 身份混淆。最小运行时复现确认英文内置显示名可保存为用户模板，且两个不同名称、相同 `template_id` 的模板可被 `save_templates` 接受并在一次删除中同时移除；既有 `test_shell.py`、`test_sheet_catalog_templates.py`、`test_message_catalog.py` 仍全绿，证明缺少相应回归用例。

F1～F5 统一进入 [PLAN-DM-024](../../plans/dst-manager/PLAN-DM-024-sheet-catalog-correctness-closure.md)，与视觉整改 PLAN-DM-023 分开实施。执行顺序为 PLAN-DM-024 → PLAN-DM-023；本计划完成并使 SPEC-DM-012 G7 重新通过前，不开始视觉生产改动。
