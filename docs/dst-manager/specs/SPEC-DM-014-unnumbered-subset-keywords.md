---
id: SPEC-DM-014
title: 不编号图纸关键字规范
status: accepted
document_kind: spec
owners:
  - dst-manager
created: 2026-09-13
updated: 2026-09-13
related:
  - SPEC-DM-001
  - SPEC-DM-011
  - SPEC-DM-012
  - ARCH-DM-004
  - GUIDE-DM-003
  - PLAN-DM-027
  - PLAN-DM-028
---

# 不编号图纸关键字规范

> 定位：本文是**不编号图纸关键字**的唯一权威定义，增量修订 [SPEC-DM-001](SPEC-DM-001-v021-sheetset-editing-adjustment.md) 的「统一派生」编号规则；SPEC-DM-001 的其余规则、DST/XML 受控修改、CAD Worker、永久快照与可恢复整批发布要求全部继续适用。设置中心的控件与保存事务契约见 [SPEC-DM-011](SPEC-DM-011-settings-center-ui.md) 与 [ARCH-DM-004](../architecture/ARCH-DM-004-settings-center.md)，配置字段的操作口径见 [GUIDE-DM-003](../guides/GUIDE-DM-003-settings-config-sop.md)。

## 背景

图纸集里的封面、图纸目录、说明等分册通常不参与连续图号：编号只应落在施工图子集上。v0.21 起，图号由统一派生按子集顺序和子集内图纸顺序连续计算，用户想让某个子集不编号，只能把它排在其他子集之后，或事后手工调整 DST。本规范引入一个由用户维护的关键字列表：**子集名称包含任一关键字时，该子集内的图纸编号固定为 0，且不占用序号**。

## 范围

本规范包括：

- 关键字列表的设置项位置、取值形态与规范化规则；
- 「不编号子集」的判定规则与生效时机；
- 编号派生（序号种子、图号位数、图号、子集显示名/图号范围）的增量规则；
- 预览、错误码与兼容性口径。

本规范不包括：

- 逐张图纸的「不编号」标记（不编号是**子集级**判定）；
- 关键字与特定子集 ID 的绑定或持久化标记（判定是完全动态的，见「行为」§1）；
- 图号格式化本身的改动（格式码与补零惯例见 [RES-DM-001](../research/RES-DM-001-number-format-code-conventions.md) 与 SPEC-DM-012）；
- 样板与模板入口、既有子集的复制流程等旁路入口的并行设计。

## 行为

1. **判定（动态、不持久化）**：对每个子集取**可编辑标题**（子集显示名去掉不可编辑的图号范围前缀后的部分），先 `casefold`，再判断是否**包含**任一关键字（同样 `casefold`）。命中即该子集整体「不编号」。系统**不**在 DST、数据库或配置中记录「这个子集是不编号的」；判定在每次预览/执行时按当时的配置与当时的标题重新计算。
2. **匹配语义**：字面子串匹配，大小写不敏感；不支持通配符、正则或全词匹配。空关键字列表（含空串、纯分隔符）等价于关闭该功能。
3. **序号种子与图号位数**：非不编号子集的首个纯数字图号决定序号起点与位数（既有规则）。计算种子时**跳过**不编号子集，避免其中必然出现的 `000` 把起点拉成 0。若文档内不存在任何非不编号子集的数字图号，则借用文档既有数字图号的位数（起点仍为 1）；文档内确实没有数字图号时回退为 1 位。
4. **图号取值**：不编号子集内的每张图纸图号恒为 `0` 重复到项目位数（如 3 位项目为 `000`）。这是**单一取值，不是编号范围**：子集内无论多少张图纸，子集显示名与图号范围都显示 `000`。
5. **不消耗序号**：遍历不编号子集时不递增序号计数器。因此在该子集中新建图纸、或新建一个命中关键字的子集，**不改变任何其他子集的图号**；编号效果与「该子集不存在于编号序列中」一致。不编号子集排在中间时，其后的施工图子集仍从上一个非不编号子集继续编号。
6. **标题后缀**：沿用全局 `EnableAddNumberSuffix` / `NumberSuffixType` 设置，不因不编号而改变；同标题分组排序沿用既有规则（`000` 的组内起始值最小，排最前）。
7. **生效时机**：关键字列表或子集标题变化后，下一次预览按新结果重算。事后新增关键字、或把既有子集改名命中/脱离关键字，都是一次普通结构变更：释放出来的号段会让后续子集前移，占用号段会让后续子集后移，预览如实呈现（预览 → 执行仍需基准修订与 `preview_digest` 匹配）。
8. **不改 DST 结构**：不编号只改变派生结果（图号、显示名、标题、布局名、目标 DWG 文件名），不引入新的 XML 节点、属性或命名空间；落盘仍走 DST → XML DOM → DST 受控流程。

## 设置项

| 项 | 值 |
| --- | --- |
| key | `unnumbered_subset_keywords` |
| 位置 | 设置 → 编号规则（`settings.categories.numbering`），与「图纸编号追加后缀」「后缀类型」同组 |
| 控件 | `text`（单行文本框；注册表控件类型由 SPEC-DM-011 SC-03 列出） |
| 持久形态 | 规范化字符串（半角逗号分隔，见下节） |
| 默认值 | `""`（空串 = 功能关闭） |
| env 通道 | `DST_MANAGER_UNNUMBERED_SUBSET_KEYWORDS`（沿用 `DST_MANAGER_` 前缀规则） |
| 优先级 | 默认 < env < `settings.json` 文件覆盖 |

字段类型保持字符串而非数组：`.env` 与环境变量通道对 `list` 字段会按 JSON 解析，用户按文档写 `封面,目录` 会让服务启动失败。**数量与长度上限只由保存事务强制**（见下节）。

## 规范化与上限

用户输入与持久形态之间恒做一次规范化，规则如下（半角/全角逗号兼容，与图纸目录插件的「输出图纸过滤」一致）：

1. 按半角 `,` 与全角 `，` 切分；
2. 每项去除首尾空白；
3. 丢弃空项；
4. 按 `casefold` 去重，保留**首次出现的原文**（大小写与原文形式不被改写）；
5. 以半角逗号连接为持久字符串。

上限：

- 关键字数量 ≤ **50**；
- 单个关键字长度 ≤ **100** 字符。

超限时保存被**拒绝**并返回逐字段 422，系统**绝不截断**用户输入。规范化本身不做上限校验、不丢弃超限项：读取既有文件/环境变量时一律原样规范化保留，避免一条超长关键字导致整个文件覆盖被 resolver 丢弃。

## 接口

保存（PUT `/api/settings`）：

```json
{"expected_revision": 12, "set": {"unnumbered_subset_keywords": "封面， 目录,封面"}}
```

响应与后续 GET 中该字段的值恒为规范化结果 `"封面,目录"`。

读取（GET `/api/settings` 的 `items[]`）：

```json
{
  "key": "unnumbered_subset_keywords",
  "label_key": "settings.items.unnumberedSubsetKeywords",
  "category_key": "settings.categories.numbering",
  "control": "text",
  "value": "封面,目录",
  "default": "",
  "source": "file",
  "has_file_override": true
}
```

不新增响应字段：`value`/`default` 的 `bool | int | str | None` 联合已容纳字符串，`text` 控件不声明 `nullable`/`file_filter_key`/`file_kind`/`options`/`min`/`max`。

## 异常

| 错误码 | `message_key` | 触发 | `params` |
| --- | --- | --- | --- |
| `SETTING_TEXT_TYPE` | `settings.validation.textType` | `text` 控件收到非字符串值 | `{}` |
| `SETTING_KEYWORD_LIMIT` | `settings.validation.keywordCountLimit` | 去重后关键字数量 > 50 | `{"limit": 50, "actual": <数量>}` |
| `SETTING_KEYWORD_LIMIT` | `settings.validation.keywordLengthLimit` | 任一关键字长度 > 100 | `{"limit": 100, "actual": <最长长度>}` |

- 全部为逐字段 422（`{key: {code, message_key, params, message}}`），保存失败时 `config_revision` 不变，其他字段的编辑不落盘。
- `params` 只允许 `str | int | bool | list[str]`，不放本地化标签或完整句子（ARCH-DM-005 §6.2）。
- 前端在编辑中即时提示相同的两条上限（数量按去重后计、长度按最长关键字报数），**最终判定仍以上述后端错误为准**。
- `SETTING_TEXT_TYPE` 不可由设置界面触发（文本控件恒发送字符串），仅直接调用 API 的非界面客户端会命中；其文案键 `settings.validation.textType` 已与其余校验键一并登记在中英两份语言资源中。

## 安全边界

- 关键字只参与子集标题的字符串匹配，不进入 SCR 命令、Shell 命令或文件路径拼接。
- 子集显示名、图号与目标 DWG 文件名仍经既有名称校验（危险名称与越界路径拦截），不编号不引入新的文件系统写入口。
- 多张图纸得到同一图号 `000` 是允许的：DST 落盘只校验 `SHEET_FIELD_MISSING`，没有图号唯一性约束。**多个同标题的不编号子集**会派生同名目标 DWG，由既有发布前校验 `DWG_TARGET_COLLISION` 阻断，系统不静默覆盖。

## 兼容性

- **关键字为空时行为与既有版本完全一致**，SPEC-DM-001 的全部编号规则原样适用；本规范纯增量。
- 既有工作区不需要迁移：判定是动态的，DST、数据库与草稿格式均无变化，无新增迁移。
- 后缀关闭且同一不编号子集内出现多张同标题图纸时，仍由既有 `DUPLICATE_LAYOUT_NAME` 拦截（与普通子集同口径）。
- 已知代价（不在本次范围）：不编号子集之后的子集在结构调整时可能因基准确认边界进入 `rename_only`（多一次 CAD 处理、图号不变）；后续如需优化另行立项。

## 测试

- `tests/unit/test_keywords.py`：占位与默认值、半/全角逗号切分、trim、空项、`casefold` 去重保留原文、数量/长度上限、标题匹配。
- `tests/unit/test_unnumbered_subsets.py`：位数继承、`000` 单值、不消耗序号（前置/中间/后置子集图号零影响）、全部不编号时借用既有位数、设置文本 → `SuffixOptions` → 预览图号的服务接线、未设置关键字时的纯回归路径。
- `tests/unit/test_config.py`：默认空串、env 值规范化（半/全角、重复项）、序列值容错、非法负载拒绝。
- `tests/unit/test_settings_registry.py` / `test_settings_runtime.py` / `tests/integration/test_api_settings.py`：`text` 控件元数据、保存规范化往返、空串作为显式覆盖、unset 回落 env、非字符串 422、数量/长度超限 422 与 `params` 白名单。
- `web/tests/e2e/settings-dialog.spec.ts`：文本控件渲染与提示、规范化保存与来源徽章、恢复继承、超限即时行内错误并禁用保存。

## 验证记录

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 静态检查 | `uv run ruff check .` | 通过（2 处 `__all__`/导入排序由 `ruff --fix` 修正后零告警） |
| 后端全量 | `uv run pytest -q` | 1446 项：1374 passed / 72 skipped / 0 failed |
| 前端构建 | `npm run build`（含 `check:api`、`check:i18n`、`vue-tsc`） | 通过 |
| 设置中心 e2e | `npx playwright test tests/e2e/settings-dialog.spec.ts` | 22 passed |
| 真实 CAD | `DST_MANAGER_RUN_AUTOCAD=1 uv run pytest tests/system_autocad -q` | 本次未运行（改动不涉及 SCR/插件/布局重建，编号派生已有单元与预览覆盖） |

设计与关键字语义由用户于 2026-09-13 在设计问答中确认（动态判定、图号统一 `000`、标题后缀沿用全局设置、关键字输入与输出图纸过滤同口径）。

**门禁分级（如实记录）：** 本项引入新控件类型 `text`，按 GUIDE-DM-003 A-6 属 [GUIDE-DM-001](../guides/GUIDE-DM-001-frontend-design-implementation-gates.md) 的 **M 级**。G3/G4（新视觉方向与冻结、Demo）与 G8（新的同态截图证据）**未重开**——本项无新视觉选择，直接复用设置对话框既有行渲染与错误态，既有冻结件与生产证据未重取；G9 真实桌面验收未发起。门禁逐项状态与待补动作见 [PLAN-DM-027](../../../.planning/plans/dst-manager/PLAN-DM-027-unnumbered-subset-keywords.md)「门禁分级与证据缺口」。

**实现缺陷修复（2026-09-13 追记）：** 打包 EXE 内出现「保存了关键字但新建「封面」子集仍被编号」——根因不在本 SPEC 的领域规则，而是设置层到预览的接线：`create_app` 未把 `RuntimeSettings` 注入 `DstManagerService`，服务的运行期字段读取（含 `unnumbered_subset_keywords`）恒为构造期快照，`settings.json` 覆盖值对预览不可见（重启也不生效）。修复与回归证据见 [PLAN-DM-028](../../../.planning/plans/dst-manager/PLAN-DM-028-runtime-settings-live-consumption.md)，并已回写 [ARCH-DM-004 §2.4](../architecture/ARCH-DM-004-settings-center.md)；本节上述行为的定义不变，仅实现现已与之相符。
