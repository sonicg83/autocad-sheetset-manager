---
id: PLAN-DM-027
title: 不编号图纸关键字实施计划
status: completed
owners:
  - dst-manager
created: 2026-09-13
updated: 2026-09-13
related:
  - SPEC-DM-014
  - SPEC-DM-001
  - SPEC-DM-011
  - ARCH-DM-004
  - GUIDE-DM-003
---

# 不编号图纸关键字实施计划

> **来源：** 用户需求（2026-09-13）：在「图纸管理」中维护一份关键字列表；新建子集时若**子集名称包含关键字**，该子集及其内图纸编号固定为 0（符合项目编号位数），且**不影响其他子集编号**；关键字设置放在**设置 → 编号规则**，逗号分隔文本框，与图纸目录插件的「输出图纸过滤」同口径。设计经用户确认后进入 TDD 实现。

**Goal:** 让封面、图纸目录一类分册不占用连续图号：子集标题命中关键字即整体不编号（图号 `000`），且不消耗序号，对其他子集的编号零影响。

**Architecture:** 三层增量，不引入新持久化结构：

- `domain/keywords.py`（新增纯函数模块）：规范化/格式化/解析/匹配 + 上限常量，无外部依赖。
- `domain/editing.py`：编号派生识别「不编号子集」，`_number_seed` 跳过它们，其内图号恒为 `0`×位数且不递增计数器；`SuffixOptions` 增加 `unnumbered_keywords` 字段承载设置。
- `settings` 与 `interfaces`：`Settings.unnumbered_subset_keywords`（str）+ 注册表 `text` 控件 + 保存事务规范化与上限校验（结构化 422）；Web 端新增 `text` 控件渲染与即时校验。

**Tech Stack:** Python 3.12 + uv + pydantic-settings、Vue 3 + TypeScript + vite + vue-i18n + Playwright。

**Spec:** [SPEC-DM-014](../../../docs/dst-manager/specs/SPEC-DM-014-unnumbered-subset-keywords.md)（不编号图纸关键字的唯一权威定义，增量修订 SPEC-DM-001 的统一派生）。

## Global Constraints

- 全程简体中文注释、文档、commit message；标识符与 API 字段保持英文。
- 关键字为空时与既有行为**完全一致**（纯回归路径），既有工作区无需迁移。
- 不改 DST XML 结构、不改发布链路：只改派生结果，落盘仍走 `DST → XML DOM → DST` 受控流程。
- 设置层不依赖 `interfaces` 层；`params` 只放 `str | int | bool | list[str]`（ARCH-DM-005 §6.2）。
- 上限由保存事务强制，**拒绝保存、绝不截断**；读取路径只规范化不丢项。
- 前端不复制后端最终校验：即时提示可以，最终判定以 422 为准。
- Python 验证基线：`uv run ruff check .` 与 `uv run pytest -q` 全绿；Web 改动必须跑 `npm run build` 与相关 e2e。

---

### Task 1: 关键字纯函数模块

**Files:**
- Create: `src/dst_manager/domain/keywords.py`
- Test: `tests/unit/test_keywords.py`

**Interfaces:**
- Produces：`normalize_keywords(value: str) -> tuple[str, ...]`、`format_keywords(items) -> str`、`parse_keywords(value, *, max_items, max_chars) -> tuple[str, ...]`（超限抛 `KeywordLimitError(kind, limit, actual)`）、`title_matches_keywords(title, keywords) -> bool`、常量 `MAX_UNNUMBERED_KEYWORDS = 50` / `MAX_UNNUMBERED_KEYWORD_CHARS = 100`。

- [x] **Step 1: 写失败测试**：占位与默认值、半/全角逗号切分、trim、空项丢弃、`casefold` 去重保留首次原文、数量与长度超限的错误字段、标题大小写不敏感子串匹配。
- [x] **Step 2: 实现模块**：分隔符 `re.compile("[,，]")`；上限只在 `parse_keywords` 校验，`normalize_keywords` 不丢项。
- [x] **Step 3: 测试转绿**（11 项）。

### Task 2: 领域编号派生（TDD）

**Files:**
- Modify: `src/dst_manager/domain/models.py`（`SuffixOptions` 增第三字段 `unnumbered_keywords: tuple[str, ...] = ()`，保留类名避免改动 ~70 处位置调用）
- Modify: `src/dst_manager/domain/editing.py`
- Test: `tests/unit/test_unnumbered_subsets.py`

**Interfaces:**
- Consumes: Task 1 的匹配函数。
- Produces：`derive_document_structure` 在存在不编号子集时输出 `0`×位数图号；`SuffixOptions(enabled, suffix_type, unnumbered_keywords)`。

- [x] **Step 1: 写失败测试**：命中关键字的子集图号 `000`、其内多张图纸同为 `000`、前置/中间/后置位置下其他子集图号零影响、`_number_seed` 跳过不编号子集、全部子集都不编号时借用文档既有数字图号位数、关键字为空时的回归路径。
- [x] **Step 2: 实现**：命令循环后按最终标题计算 `unnumbered_subset_ids`；编号循环内不编号子集写 `"0" * width` 且不递增；`_number_seed(document, unnumbered_subset_ids)` 只用非不编号子集定种子；新增「全不编号」兜底（借用既有数字图号位数，无数字图号回退 1 位）；`_number_range` 首尾相等时返回单值。
- [x] **Step 3: 测试转绿** + `tests/unit` 全绿（无回归）。

### Task 3: 设置层 `text` 控件与保存事务

**Files:**
- Modify: `src/dst_manager/config.py`、`src/dst_manager/settings/registry.py`、`src/dst_manager/settings/runtime.py`、`src/dst_manager/interfaces/api.py`、`src/dst_manager/interfaces/settings_contracts.py`
- Test: `tests/unit/test_config.py`、`tests/unit/test_settings_registry.py`、`tests/unit/test_settings_runtime.py`、`tests/integration/test_api_settings.py`

**Interfaces:**
- Produces：`control: Literal["path","bool","int","enum","text"]`；`SETTING_TEXT_TYPE`（非字符串）与 `SETTING_KEYWORD_LIMIT`（数量/长度超限，`message_key` 区分两条文案）两个稳定错误码；GET 快照 `text` 项直接返回字符串值。

- [x] **Step 1: 写失败测试**：默认空串、env 半/全角与重复项规范化、序列/dict 负载拒绝、持久规范化往返、空串作为显式覆盖、unset 回落 env、非字符串 422、51 项与 101 字符的 422（`params` 为 `{"limit","actual"}`）、`params` 白名单。
- [x] **Step 2: 实现**：字段类型保持 `str`（`.env`/env 通道对 `list` 字段按 JSON 解析会启动报错）；`config.py` 的 `field_validator(mode="before")` **只规范化、不强制上限**（避免一条超长关键字使 resolver 丢弃整个文件覆盖）；`settings/runtime.py` 的保存事务强制上限并写回规范形态；`_validate_value` 增加 `text` 分支；`interfaces/api.py` 的 `_settings_items` 用 `elif meta.control == "int"` 收窄，text 走无附加元数据路径。
- [x] **Step 3: 测试转绿**（设置层相关 94 项全绿），并补 `settings_contracts.py` / `registry.py` 的 docstring 说明。

### Task 4: 应用层接线与预览验证

**Files:**
- Modify: `src/dst_manager/application/editing.py`（`SuffixOptions(..., normalize_keywords(self.settings.unnumbered_subset_keywords))`）
- Test: `tests/unit/test_unnumbered_subsets.py`

- [x] **Step 1: 写失败测试**：`DstManagerService(Settings(data_dir=..., unnumbered_subset_keywords=" 封面， 目录,封面 "))` + `open_workspace` + `preview_changes(update_subset_title 改名为「封面」)`，断言计划 `groups[0].subset_name == "000 封面"`、`layouts[].number == "000"`、目标文件名为 `000 封面.dwg`；未设置关键字时同流程仍为 `001 封面`。
- [x] **Step 2: 实现接线**（唯一生产调用点 `application/editing.py`）。
- [x] **Step 3: 测试转绿**（18 项），`tests/unit tests/integration` 全绿。

### Task 5: Web 设置中心 `text` 控件

**Files:**
- Modify: `web/src/api/settings.ts`、`web/src/components/settings/SettingsFormRow.vue`、`web/src/components/settings/SettingsDialog.vue`、`web/src/i18n/locales/zh-CN/settings.ts`、`web/src/i18n/locales/en-US/settings.ts`
- Test: `web/tests/e2e/settings-dialog.spec.ts`

**Interfaces:**
- Produces：`SettingsControl` 增 `"text"`；导出上限常量供行内提示与即时校验共用；`previewKeys` 纳入 `unnumbered_subset_keywords`（保存后追加「相关预览将按新配置重算」）。

- [x] **Step 1: 写失败测试**（e2e）：文本控件渲染与提示、规范化保存与来源徽章、恢复继承、数量/长度超限即时行内错误并禁用保存、去重计数口径。
- [x] **Step 2: 实现**：单行 `input`（`data-key` 直接位于 `.f-main` 内，与 int 行同约定）、行内错误/脏边框/来源徽章/恢复继承全部复用现有机制；`localError` 增加 text 分支（与后端同规范化规则，仅即时反馈）。
- [x] **Step 3: 测试转绿**：新用例 2 项通过，`settings-dialog.spec.ts` 全文件 22 项通过。

### Task 6: 文档与门禁

**Files:**
- Create: `docs/dst-manager/specs/SPEC-DM-014-unnumbered-subset-keywords.md`
- Create: `.planning/plans/dst-manager/PLAN-DM-027-unnumbered-subset-keywords.md`
- Modify: `docs/dst-manager/specs/SPEC-DM-001-v021-sheetset-editing-adjustment.md`（修订指向）、`docs/dst-manager/specs/SPEC-DM-011-settings-center-ui.md`（SC-03 控件集合）、`docs/dst-manager/README.md`、`.planning/plans/dst-manager/README.md`、`changelog.md`

- [x] **Step 1: 写 SPEC-DM-014**：背景/范围/行为/设置项/规范化与上限/接口/异常/安全边界/兼容性/测试/验证记录。
- [x] **Step 2: 索引同步**：`docs/dst-manager/README.md` 规范清单与 `.planning/plans/dst-manager/README.md` 详细计划清单各增一行；SPEC-DM-001 增修订指引；SPEC-DM-011 SC-03 控件集合补 `text`。
- [x] **Step 3: 记录验证**（见下）。

## 实际验证

- `uv run ruff check .`：通过（`domain/keywords.py` 的 `__all__` 排序、`settings/runtime.py` 导入分组由 `ruff --fix` 修正，修正后零告警）。
- `uv run pytest -q`：**1446 collected / 1374 passed / 72 skipped / 0 failed**（72 skipped 为需 `DST_MANAGER_RUN_AUTOCAD=1` 或缺失私有样本的真实 CAD 系统测试）。
- `cd web && npm run build`：通过（`check:api` 契约未变化、`check:i18n` 944 键 / 9 域对称、`vue-tsc` 与 `vite build` 成功）。
- `npx playwright test tests/e2e/settings-dialog.spec.ts`：**22 passed**（含本次新增 2 项；语言资源补 `settings.validation.textType` 后重跑仍为 22 passed）。
- 未执行：真实 AutoCAD 2016/2020 系统测试（改动不涉及 SCR/插件/布局重建，编号派生已由单元测试与预览断言覆盖）。

## 门禁分级与证据缺口（如实记录）

按 [GUIDE-DM-003](../../../docs/dst-manager/guides/GUIDE-DM-003-settings-config-sop.md) A-6，本次引入**新控件类型**（`text`），因此按 [GUIDE-DM-001](../../../docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md) 属 **M 级**（G0～G9 全部）。实际状态：

- **已有证据**：G0/G1（用户需求与范围、四问设计问答）、G2（空值/超限/即时错误/禁用保存/恢复继承状态均有用例）、G5（技术映射：注册表控件、设置链、领域派生）、G6（SPEC-DM-014 + 本计划）、G7（TDD 分批实施、逐层测试转绿）。
- **未重开**：G3/G4（本项没有新的视觉方向或布局选择，直接复用设置对话框既有行渲染、令牌与错误态；未新增 Demo/冻结件）、G8（未采集新同态截图；既有 `SPEC-DM-011` 生产证据未重取、未重开）、G9（未发起用户真实桌面验收；`SPEC-DM-011` G9 基线保持原结论）。
- **如需 M 级完整闭合**，待用户裁决的最小动作：为新的文本行补浅/深主题同态截图并入 `docs/dst-manager/specs/assets/SPEC-DM-011/production/` 与 `SPEC-DM-011` §7 索引（不重取既有冻结件），再安排一次真实桌面验收。
- **裁定结果（2026-09-13）**：用户选择「暂不补，登记为待办」；与 [PLAN-DM-028](../../../.planning/plans/dst-manager/PLAN-DM-028-runtime-settings-live-consumption.md) 的 G9 待办合并登记在 `2026-09-13-unnumbered-keywords-gate-gaps.md`（G8 截图 + 打包版 G9 验收步骤）。

## 后续项（不在本次范围）

- 不编号子集之后的子集在结构调整时可能因基准确认边界进入 `rename_only`（多一次 CAD 处理、图号不变），未做优化。
- 关键字列表不提供「候选关键字」下拉或从现有子集标题提取的辅助输入。
