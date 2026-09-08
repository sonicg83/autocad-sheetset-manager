---
id: GUIDE-DM-003
title: 配置中心配置项增删改 SOP
status: review
document_kind: guide
owners:
  - dst-manager
created: 2026-09-08
updated: 2026-09-08
related:
  - ARCH-DM-004
  - SPEC-DM-011
  - PLAN-DM-019
  - GUIDE-DM-001
---

# 配置中心配置项增删改 SOP

> 定位：指导在 DST Manager 设置中心**新增 / 修改 / 移除配置项**的标准操作流程。架构与行为权威是 [ARCH-DM-004](../architecture/ARCH-DM-004-settings-center.md)，UI 交互权威是 [SPEC-DM-011](../specs/SPEC-DM-011-settings-center-ui.md)；本文是执行层操作手册，与两者冲突时以上游为准。
> 核心不变量（任何操作不得破坏，详见 ARCH-DM-004 §2.1–§2.3）：
> 1. **Pydantic `Settings`（`src/dst_manager/config.py`）是配置语义唯一权威**——默认值、约束、校验只在这里定义；
> 2. **`registry.py` 只存展示元数据**，min/max/枚举选项从 Settings Schema 派生，禁止抄第二份；
> 3. **`settings.json` 只存显式覆盖值**，依赖方向永远 `settings/* → config.py` 单向；
> 4. **运行期配置即时生效**：任务级快照冻结 + `config_revision` 变更检测（ARCH-DM-004 §2.4）。

## 1. 前置判定：这个配置该不该进配置中心

新增需求先过这棵决策树（依据 ARCH-DM-004 §1.3 范围外清单）：

| 判定 | 结论 |
| --- | --- |
| 是凭据/令牌/密钥？ | **不进**。凭据永远不进普通设置（PRD-DM-001 SEC-003） |
| 是启动期配置（建目录、派生数据库 URL，如 `data_dir`/`draft_dir`）？ | **不进**。改动需重启且涉及数据迁移，收益不抵风险；用环境变量覆盖 |
| 只有开发者会用、无需图形界面？ | **不进**。`.env`/环境变量通道已覆盖 |
| 运行期业务参数、用户可能需要调整？ | **进**。走 SOP-A |

"进配置中心"的完整交付 = `config.py` 字段 + `registry.py` 一行 + 测试；**API 与前端表单零改动**（元数据驱动，`GET /api/settings` 自动序列化、前端按描述渲染）。这正是扩展平台（PRD-DM-001）未来贡献设置分区的同款机制。

## 2. SOP-A：新增配置项

按顺序执行，每步含验证点。全程参考既有样例：`cad_max_parallel`（int 带范围）、`enable_add_number_suffix`（bool 带 alias 容错）、`autocad_2016_console`（nullable path 带 file_filter）、`number_suffix_type`（enum）。

### A-1 `config.py` 定义字段（语义权威）

```python
template_dir: Path | None = None                          # path 类：可空
cad_max_parallel: int = Field(default=4, ge=1, le=10)     # int 类：约束写在 Field
enable_xxx: bool = True                                   # bool 类
xxx_mode: Literal[1, 2] = 1                               # enum 类：用 Literal
```

- 需要**字符串容错**（`.env`/手编文件中 `"true"`/`"1"`）时加 `field_validator(mode="before")`，参照 `validate_enable_add_number_suffix`。
- 需要**路径规范化**时加 validator，参照 `validate_cad_paths`（相对路径规范化为绝对——这是既有兼容行为，勿改）。
- ⚠️ 约束（ge/le/Literal）写在这里之后，注册表自动派生；**不要**在 registry 里重复。
- 注意 alias 字段（`validation_alias=...`）与按名构造共存依赖 `populate_by_name=True`（已在 `model_config` 开启），新字段默认可用。

### A-2 `settings/registry.py` 登记展示元数据

在 `REGISTRY` 元组中**按 API 稳定排序**追加一项：

```python
SettingsItemMeta(key="template_dir", label="模板目录", category="路径", control="path", nullable=True, file_filter=None),
```

- `label` 用最终用户可读的中文，不出现 key 名或占位词（教训：`number_suffix_type` 曾用"类型 1/2"占位，评审裁决改为领域真实语义——先查 `domain/` 里该配置的真实行为再定文案）。
- enum 字段必须同步在 `_ENUM_TEXTS` 补表（`registry.py`），否则运行时 KeyError（刻意的 fail-fast，防占位文案上线）。
- `category` 优先复用既有分组（"AutoCAD 2016"/"AutoCAD 2020"/"任务执行"/"编号规则"）；新分组等于冻结设计新增分区，属视觉变更，按 GUIDE-DM-001 评估是否重开 G4。
- `file_filter` 注意 pywebview 格式约束：描述部分匹配 `[\w ]+`（**不允许 `.`、`/` 开头**，如 ".NET 程序集" 会弹出前崩溃，现有契约测试会拦）。

### A-3 更新受影响的既有测试

- `tests/unit/test_settings_registry.py::test_registry_covers_exactly_the_nine_ui_fields`——字段集合是**硬断言**，加/删字段必须同步更新（这是防孤儿字段的守卫，不是障碍）。
- `tests/integration/test_api_settings.py`——`items` 数量与硬锚（如 `items[4]["default"] == 600`，按 REGISTRY 第 5 项定位）需按新排序更新。
- 派生约束用例（`min_max`/`enum_options`）按新字段补断言。

### A-4 新增行为测试

- `test_settings_resolver.py`：新字段的 env/覆盖/来源判定（如适用）。
- `test_settings_runtime.py`：新字段可 set/unset、约束越界 422。
- **Worker 传播**（仅当字段被任务执行消费）：`test_worker_settings_propagation.py` 仿 timeout/lease 用例；`service.py` 执行链遵循**冻结模式**——认领时读入局部变量，运行期不再读 `self.settings`。

### A-5 前端与 API：确认零改动即可工作

- `GET /api/settings` 自动带出新项（`_settings_items` 遍历 REGISTRY）；`SettingsDialog` 自动渲染。
- 跑 `cd web && npm run build`（含 OpenAPI 契约校验）+ `npx playwright test` 确认无回归。
- 若新项需要 e2e：在 `web/tests/e2e/settings-dialog.spec.ts` serial 链**尾部**追加（链尾状态是"恢复默认"后的干净态）。

### A-6 文档与验证收尾

- `ARCH-DM-004` §2.1 的 9 项字段清单更新（数量与清单同步）。
- 根 `changelog.md` 追加条目。
- 全量验证：`uv run ruff check .`、`uv run pytest -q`、`uv lock --check`、`npm run build`、`npx playwright test`。
- GUIDE-DM-001 分级：纯后端字段+登记通常 S 级（走快速通道，G0/G1/G5–G9）；若引入新分组/新控件类型，升 M 级。

## 3. SOP-B：修改配置项

### B-1 改默认值（`config.py` Field default）

- 影响：`default` 经 API 透传；**已有用户覆盖值不受影响**（file > default），env 优先级高于 default。
- 同步更新：`test_config.py`、`test_api_settings.py` 硬锚（如 `== 600`）、依赖默认值的 e2e 断言（serial 链尾的 `600`）。
- 若默认值语义变化对用户可感知（如超时 600→900），在 changelog 标注。

### B-2 加约束（如给 `cad_timeout_seconds` 补 ge/le）

- 约束写在 `config.py`（权威），registry 自动派生。
- **存量 `settings.json` 里的非法覆盖值**由 resolver 降级自愈机制处理：构造失败时忽略该键按继承值运行并附诊断，用户下次保存合法值时自愈——不需要迁移，但 changelog 必须告知用户。
- 这是**唯一允许改 `config.py` 字段语义的操作**（ARCH-DM-004 §2.1 的"语义不变"指不破坏既有行为；收紧约束是新决策）——先在 ARCH-DM-004 记录决策再动代码。

### B-3 改文案/分组（`registry.py`）

- 只改 `label`/`category`/`_ENUM_TEXTS` + 对应测试断言。无数据迁移。
- 改 `category` 分组顺序影响 API items 排序 → 更新 `test_api_settings.py` 硬锚索引。

### B-4 改控件类型（path↔bool↔int↔enum）

- 罕见；意味着用户 `settings.json` 里的旧覆盖值类型可能不再合法（自愈机制兜底）。
- 属交互变更：按 GUIDE-DM-001 评估等级，重开 SPEC-DM-011 对应条目与 G4（若视觉受影响）。

## 4. SOP-C：移除配置项

两档操作，先选档位：

### C-1 下架 UI（字段保留）

适用：功能还在但不再暴露给用户（如过渡期保留环境变量通道）。

1. `registry.py` 删除该项 `SettingsItemMeta`（及 `_ENUM_TEXTS` 对应行）。
2. `config.py` **保留**字段与 validator（环境变量通道仍有效）。
3. 更新完整性测试的字段集合断言、API 测试的 items 数量与硬锚。
4. 前端零改动（该项自动从表单消失）；`settings.json` 里的残留覆盖键被 resolver 过滤（`_filter_registry` 忽略未知键），**不会报错**，无需迁移。
5. changelog 告知用户"XX 已从设置界面移除，可用环境变量 `DST_MANAGER_XXX` 继续 override"。

### C-2 彻底删除（字段也删）

适用：能力整体下线。

1. `config.py` 删字段与 validator → **确认无生产代码引用**（grep 字段名；`service.py`/`database.py` 的消费点一并处理）。
2. registry 删除登记；完整性测试字段集合更新。
3. 存量 `settings.json` 残留键：resolver 过滤保证不炸（C-1 第 4 条同机制）；**不要**为此 bump `schema_version`（见 §5）。
4. 删除该字段的全部专属测试（registry/api/runtime/e2e）。
5. `ARCH-DM-004` §2.1 清单、changelog 同步；若该字段被 PRD-DM-001 未来分区引用，先查引用再删。

## 5. schema_version 什么时候 bump

**只在存储格式或语义发生不兼容变化时**（如 values 结构改变、字段改名需要迁移）。以下情况**不需要**：

- 新增 key（旧程序经 `_filter_registry` 忽略未知键；新程序读旧文件缺 key 取继承值）；
- 移除 key（同上双向兼容）；
- 约束收紧（自愈机制兜底）。

bump 规则见 ARCH-DM-004 §5：过旧 → 有迁移器则迁移（保留备份），无迁移器按损坏类处理；**过新 → 只读降级禁止 PUT**——bump 前必须先写迁移器或接受只读降级。

## 6. 通用验证清单（每次增删改后）

```powershell
uv run ruff check .
uv run pytest -q                      # 0 failed；关注 registry/api/runtime 三个设置测试文件
uv lock --check
cd web; npm run build; npx playwright test
```

- 涉及 Worker 消费的变更：跑 `tests/unit/test_worker_settings_propagation.py` 并确认冻结模式未破坏。
- 涉及 UI 可见变化：对照 `assets/SPEC-DM-011/production/` 基准截图，按 GUIDE-DM-001 G8 判定缺陷/有意差异。
- 文档同步：`ARCH-DM-004`（字段清单/契约）、根 `changelog.md`、（如影响交互）`SPEC-DM-011`。
- 打包相关变更（file_filter 等）列入 G9 手工清单验证。

## 7. 常见错误（反模式）

| 反模式 | 后果 | 正确做法 |
| --- | --- | --- |
| 在 registry 抄一份默认值/范围 | 双权威漂移，改一处漏一处 | 只在 `config.py` 定义，registry 派生 |
| 用 getattr(当前值) 当 default | env/覆盖下与 value 重复且漂移 | 取 `model_fields` 的字段默认（api.py `_settings_items` 现行做法） |
| 文案占位上线（"类型 1"） | 用户不可读 | 先查 domain 真实行为再定 label；enum 必须补 `_ENUM_TEXTS` |
| 保存时把 GET 的全量有效值 PUT 回去 | env/default 固化进用户文件，升级遮蔽新默认 | PUT 只交 `set`（有修改的字段）与 `unset` |
| 新字段忘了加进完整性测试断言 | 孤儿字段（有 Settings 无 UI） | `test_registry_covers_exactly_*` 是守卫，同步更新 |
| 顺手 bump schema_version | 旧版本程序进入只读降级 | 只有格式不兼容才 bump，且须先备迁移器 |
| file_filter 描述含 `.`/`/` | 桌面壳弹窗前 ValueError | 描述匹配 `[\w ]+`（如 "NET 程序集 (*.dll)"） |
| 运行期执行链直接读 `self.settings` | 配置热更新对该消费点失效 | 认领时冻结局部变量（见 `run_next_job` 现行模式） |
