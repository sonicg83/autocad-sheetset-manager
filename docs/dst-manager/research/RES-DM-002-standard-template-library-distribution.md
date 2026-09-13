---
id: RES-DM-002
title: 图纸目录标准模板库分发方案调研与提案
status: draft
owners:
  - dst-manager
created: 2026-09-13
updated: 2026-09-13
related:
  - SPEC-DM-012
  - ARCH-DM-006
  - GUIDE-DM-005
  - RES-DM-001
---

# 图纸目录标准模板库分发方案调研与提案

> 调研日期：2026-09-13
> 触发问题：开发者维护一份标准图纸目录模板库，如何快速分发到用户机器
> 结论性质：**提案**。本文件只记录现状事实与候选方案，不改变任何现有实现；建议只有进入 [SPEC-DM-012](../specs/SPEC-DM-012-sheet-catalog-extension.md) 或架构文档后才成为规范

## 1. 结论摘要

1. 图纸目录模板目前只有两类：**随包内置一套**（代码常量，不可变，作为兜底）与**用户自建模板**（按 Windows 用户存储在 SQLite）。两者之间没有“开发者维护、可分发的标准模板库”这一层，这是本提案要补的缺口。
2. 模板的持久位置只有一处（`extension_settings` 行的 `value_json.user_templates`），但**有两条写入路径**：本地 HTTP API（走 Provider 官方校验，推荐）与直接写 SQLite（只适合装机预置）。两条路都不需要改动本项目代码。
3. **分发的关键不是通道，而是模板 ID 的稳定性。** 用 `uuid5(固定命名空间, 稳定 slug)` 生成 `template_id`/`column_id`（与内置模板 `templates.py:113-118` 的 `_COLUMN_NAMESPACE`/`_stable_uuid` 同一思路），才能让重复导入成为幂等 upsert，并让 `workspace_extension_preferences` 里已记录的用户选择在标准库升级后继续指向同一套模板。
4. 推荐分两步走：**通道 A（独立标准库仓库 + pack 文件 + 本地 API 导入脚本）现在就能用，零代码改动**；**通道 B（装机预置直接写库）只用于新机器批量铺底**。随包发布（通道 C）继续只承担“一套兜底模板”，不作为标准库的载体。产品化的“导入/更新标准模板库”入口（通道 D）需要 settings schema 升到 v3 并修改 SPEC-DM-012，属后续立项。
5. **当前数据模型无法区分“标准模板”与“用户自建模板”**（模板条目只有 `template_id`/`name`/`schema_version`/`columns` 四个字段）。直接后果：在引入来源字段之前，导入语义只能是“**按 ID 只增改、不删除**”，且用户对导入模板的本地修改会在下次导入时被覆盖。这是本提案最主要的开放问题（§8.1）。
6. 模板表达式引用工作区字段目录中的字段（如 `{sheetset.专业名称}`、`{sheet.备注}`），所以标准库**必须与字段命名规范配套分发**，否则导入即不兼容。pack 应携带所需字段清单用于导入前预检。

## 2. 现状事实（可核验）

### 2.1 存储位置

| 项目 | 事实 | 出处 |
| --- | --- | --- |
| 用户模板 | SQLite `extension_settings` 表一行，`extension_id = 'dst-manager.sheet-catalog'`，主键固定；列为 `schema_version`（当前 2）、`revision`、`value_json`、`updated_at` | `src/dst_manager/infrastructure/persistence/extensions.py:39` |
| `value_json` 内容 | 只含 `user_templates` 与可选的 `excluded_title_keywords`；**内置模板不落库**（Provider 默认零值为 `{}`） | `src/dst_manager/extensions/builtin/sheet_catalog/settings.py:175` |
| 单个模板条目 | `{template_id, name, schema_version: 1, columns: [{column_id, header, expression}]}` | `src/dst_manager/extensions/builtin/sheet_catalog/templates.py:194` |
| 数据库文件（打包态） | `%LOCALAPPDATA%\dst-manager\data\dst-manager.db` | `src/dst_manager/config.py:26` |
| 数据库文件（开发态） | `<当前工作目录>\.dst-manager-data\dst-manager.db` | 同上 |
| 覆盖方式 | `DST_MANAGER_DATA_DIR` 环境变量 | `src/dst_manager/config.py:112` |
| 工作区偏好 | `workspace_extension_preferences` 表，主键 `(workspace_id, extension_id)`，值为 `{"template_id": ...}`；内置模板不写偏好 | `src/dst_manager/interfaces/extension_api.py:290` |

**推论（用户可见后果）**：打包态与开发态各有独立数据目录，两边的模板互不可见；模板按 Windows 用户隔离，不随程序安装包或共享盘自动传播。

### 2.2 两条写入路径

**路径 1：本地 HTTP API（走官方校验）**

```
GET /api/extensions/dst-manager.sheet-catalog/settings
PUT /api/extensions/dst-manager.sheet-catalog/settings
body: {"schema_version": 2,
       "value": {"user_templates": [...], "excluded_title_keywords": [...]},
       "expected_revision": <GET 返回的 revision>}
```

- 路由在 `src/dst_manager/interfaces/extension_api.py:426`（GET）与 `:440`（PUT）；请求契约 `ExtensionSettingsPutRequest` 在 `src/dst_manager/interfaces/extension_contracts.py:206`。
- 编排由 `ExtensionSettingsService` 统一负责：Provider 校验与规范化 → 乐观并发条件更新 → 竞争写入 409（`src/dst_manager/application/extensions/settings.py`）。
- **`value` 是整值替换，不是补丁**：请求里不带 `excluded_title_keywords` 即等于清空用户的过滤词。导入器必须“先 GET、原样带回”。
- Web 服务在 MVP 阶段只监听 `127.0.0.1`，因此导入客户端必须运行在同一台机器；扩展被停用不影响设置的读写（`runtime.get_settings`/`put_settings` 只依赖清单登记，不检查启用状态）。

**路径 2：直接写 SQLite**

- 先停服务，再改写 `value_json`，`revision` 必须自增，最后启动。
- 只在装机预置（新机器、新 Windows 用户）时值得采用。代价：绕过 Provider 校验，UUID 重复/重名/超限只会在用户下次于界面保存时暴露；`schema_version` 写错会触发只读降级。

### 2.3 校验约束清单（导入必须满足）

| 约束 | 限制值 | 违反时的错误 | 出处 |
| --- | --- | --- | --- |
| 用户模板总数 | ≤ 100 | `SHEET_CATALOG_TEMPLATE_LIMIT{kind: user_templates}` / 422 | `templates.py:93`、`:267` |
| 每套模板列数 | ≤ 50 | `SHEET_CATALOG_TEMPLATE_LIMIT{kind: columns}` / 422 | `templates.py:94` |
| 模板名长度 | ≤ 80 字符 | `SHEET_CATALOG_TEMPLATE_LIMIT{kind: template_name}` / 422 | `templates.py:95` |
| 表头长度 | ≤ 100 字符 | `SHEET_CATALOG_TEMPLATE_LIMIT{kind: header}` / 422 | `templates.py:96` |
| 表达式长度 | ≤ 1024 字符 | 同上 | `templates.py:97` |
| 模板名唯一 | `casefold()` 后不得与内置名“默认图纸目录（内置）”或彼此重名 | `SHEET_CATALOG_COLUMN_DUPLICATE`（重名复用此码，`params.header` 携带名称）/ 409 | `templates.py:107`（内置名）、`:305`（预置内置名）、`:325`（拒绝重名） |
| `template_id` 必填且唯一 | 保存前必须已分配 UUID | `SHEET_CATALOG_TEMPLATE_ID_REQUIRED`、`SHEET_CATALOG_TEMPLATE_ID_DUPLICATE` / 422 | `templates.py:227`（解析）、`:313`、`:317`（保存） |
| 表达式语法 | 必须能被目录表达式解析器解析 | `SHEET_CATALOG_EXPRESSION_INVALID` / 422 | `templates.py:146` |
| 过滤关键词 | ≤ 50 项、单项 ≤ 100 字符 | `EXTENSION_SETTINGS_INVALID{field: excluded_title_keywords}` / 422 | `settings.py:139` |
| 修订号一致 | `expected_revision` 必须等于当前 `revision` | `SHEET_CATALOG_TEMPLATE_CONFLICT` / 409 | `templates.py:289` |
| 设置 schema | 不得高于当前支持版本（高版本只读，禁止覆盖） | `EXTENSION_SETTINGS_SCHEMA_NEWER` / 409 | `application/extensions/settings.py` |

超限一律**拒绝保存、绝不截断**，因此 pack 一旦超限就是整批失败（不会部分成功）。

补充语义：`load_templates`（`templates.py:341`）是**容错读取**——坏条目、重名条目逐条跳过并记稳定诊断，不阻止宿主启动；而设置读写的 PUT 路径是**严格校验**。两者行为不同，导入器面对的是严格那一侧。

### 2.4 与分发直接相关的既有设计取向

- 内置模板是“随扩展版本交付的代码常量”，被 SPEC-DM-012 §6.2 定义为不可变兜底；`save_templates` 以 `collection.builtin != DEFAULT_TEMPLATE` 强制其身份（`templates.py:297`）。
- 扩展设置链路把“用户可见配置”与“随包默认值”明确分开：设置响应同时返回 `value`（持久值）与 `effective_value`（含代码默认值），两者语义不同、不得互相代替。
- 发布物中没有模板资源文件（`packaging/dst-manager.spec` 的 datas 不含模板），内置模板不落库，因此**没有数据迁移成本**，但改内置模板必须重新构建发版。

## 3. 分发问题的三个子问题

| 子问题 | 具体问法 | 本提案的答案位置 |
| --- | --- | --- |
| 分发物是什么 | 用什么格式承载“一套套标准模板” | §4 pack 格式 |
| 怎么落到用户机器 | 走哪条通道、用户要做什么动作 | §5 通道对比 |
| 重复导入怎么办 | 幂等、升级、删除、冲突 | §6 导入算法、§7 升级语义 |

## 4. pack 格式提案

```jsonc
{
  "pack_id": "dst-manager.standard-catalog",
  "pack_version": 3,
  "app_settings_schema": 2,          // 目标 value_json schema，不匹配则拒绝导入
  "released_at": "2026-09-13",
  "requires": {                       // pack 级所需字段清单，仅用于导入前预检
    "sheetset": ["专业代码", "专业名称"],
    "sheet": ["图幅", "备注"]
  },
  "templates": [
    {
      "template_id": "3f2c1a0e-...",   // uuid5(命名空间, "municipal-standard")
      "name": "市政标准目录",
      "schema_version": 1,
      "columns": [
        {"column_id": "9b1d...", "header": "序号", "expression": "{sheet.number:0}"},
        {"column_id": "4c7e...", "header": "专业", "expression": "{sheetset.专业名称}"}
      ]
    }
  ]
}
```

四条约定，按重要性排序：

1. **ID 必须由稳定 slug 派生，不得手拍随机 UUID。** 规则与内置模板一致：先取固定命名空间 `uuid5(NAMESPACE_URL, "dst-manager.standard-catalog")`，再算 `uuid5(该命名空间, "<模板 slug>")`，列用 `uuid5(该命名空间, "<模板 slug>:<表头>")`。收益有两层：
   - 重复导入变成**幂等 upsert**，不会产生“市政标准目录(2)(3)”这类重复模板；
   - `workspace_extension_preferences` 存的是 `template_id`，ID 稳定意味着**用户上次选中的模板在标准库升级后自动指向新内容**，无需重选。
   这一条应当作为标准库仓库的 CI 门禁。
2. **`requires` 只在导入器预检阶段使用，不会被持久化。** `_template_from_json`（`templates.py:233`）只读 `template_id`/`name`/`schema_version`/`columns` 四个键，`template_to_json`（`templates.py:194`）也只写这四个键——pack 条目里的额外键会被静默丢弃。它的用途是拿当前工作区的字段目录做比对，提前给出“这套模板需要 `sheet.备注`，当前图纸集没有”的提示，而不是让用户导入后只看到“不兼容”。
3. **pack 必须自证合规**：遵守 §2.3 的全部限制值，不占用内置显示名，`schema_version` 为 1、设置 `schema_version` 为 2。超限是整批失败。
4. **pack 不携带 `excluded_title_keywords`**：过滤词是用户个人偏好，标准库不应覆盖。

## 5. 通道对比

| 通道 | 用户侧动作 | 分发延迟 | 主要风险 | 是否改本项目代码 |
| --- | --- | --- | --- | --- |
| **A 独立标准库仓库 + pack 文件 + 本地 API 导入脚本** | 在本机跑一条命令（或远程协助一条命令） | 秒级，无需发版 | 低：走 Provider 校验，不碰数据库文件 | 否 |
| **B 装机预置直接写库** | 无（装机脚本完成） | 与装机同步 | 中：绕过校验；需自行维护 `revision`/`schema_version` | 否 |
| **C 随包发布**（代码常量，或 pack 作为打包资源） | 无 | 等发版 | 最低 | 是 |
| **D 产品化“导入/更新标准模板库”入口** | 设置中心点一次，可“检查更新” | 秒级 | 低 | 是（需 schema v3 + SPEC 修订） |

职责划分建议：

- **C 继续只承担“开箱可用的一套兜底模板”**（现状即是），不承载持续演进的标准库；
- **A 是当前推荐通道**：标准库维护在独立仓库，与产品发版解耦；
- **B 只在装机批量铺底时使用**；
- **D 是后续产品化目标**，其立项前提见 §8.1。

通道 A 的落地形态（全部位于标准库自己的仓库，不进本项目）：

```text
standard-catalog-templates/          # 独立仓库
  templates/*.json                   # 一套模板一个文件，便于评审 diff
  build_pack.py                      # 生成 pack，按 §4 约定 1 派生稳定 ID
  validate_pack.py                   # 离线门禁：复用服务端同一校验函数
  import_pack.py                     # GET → 合并 → PUT（走本地 API）
  dist/standard-catalog-v3.json      # 分发物，挂 Release 或共享盘
```

`validate_pack.py` 不需要重写校验逻辑，直接调用产品里同一个函数即可（只读 import，不修改产品代码）：

```python
from dst_manager.extensions.builtin.sheet_catalog.templates import (
    DEFAULT_TEMPLATE, TemplateCollection, parse_user_templates, save_templates,
)

# 与 PUT 路径执行完全相同的校验：限制值、UUID 唯一、名称 casefold 唯一、逐列表达式解析
save_templates(TemplateCollection(0, DEFAULT_TEMPLATE,
                                  parse_user_templates(pack["templates"])))
```

**这条是本方案可验证性的关键**：CI 与服务端跑的是同一段代码，不存在“CI 通过但保存被拒”的漂移。

## 6. 导入算法

```text
1. GET settings → revision / value.user_templates / value.excluded_title_keywords
2. 若 read_only（EXTENSION_SETTINGS_SCHEMA_NEWER）→ 立即中止，绝不覆盖高版本数据
3. 预检 pack：
   a. app_settings_schema 与目标一致；
   b. 条目数与列数在限制内；名称非空且 casefold 不与内置名/彼此冲突；
   c. 表达式可解析（复用 §5 的 `save_templates`）；
   d. requires 与当前工作区字段目录比对，列出缺失字段（仅警告，不阻断）
4. 合并：以 template_id 为键 upsert；同 ID 且内容不同 → 按策略处理（见 §7）
   过滤词原样带回，不参与合并
5. PUT（expected_revision = 步骤 1 读到的 revision）
6. 失败处理：
   - 409 → 重新 GET 后重试（设次数上限，避免与他人的界面编辑互相抖动）
   - 422 → 按 params.{field,kind,limit,actual} 定位到具体模板/列，整体失败不落盘
   - 503 → 扩展设置不可用（Provider 未登记/重复/ID 不符），提示用户升级或重装程序
7. 成功 → GET 回读，核对 revision 递增与模板集合内容
```

## 7. 升级与删除语义（当前模型的硬约束）

| 场景 | 现状可做到的语义 | 局限 |
| --- | --- | --- |
| 新增模板 | 直接 upsert | 无 |
| 修改标准模板内容 | 同 ID 覆盖 | **用户对导入模板的本地改动会被覆盖**，且模型无法识别“这条被用户改过” |
| 删除标准模板 | **做不到** | 模型没有来源标记，导入器无法区分“该删的标准模板”与“用户自建模板”；只能长期追加 |
| 长期累积 | — | 反复增改会逼近 `MAX_USER_TEMPLATES = 100` 上限，撞限后整批导入失败 |

因此在引入来源字段之前，通道 A 的对外语义应明确写成“**按 ID 只增改、不删除；本地修改会在下次导入时被覆盖**”，并要求 pack 变更说明中标注被移除的模板，由用户手动删除。

## 8. 开放问题（决策点）

### 8.1 是否为模板条目引入来源标识（settings schema v2 → v3）

这是通道 D 的核心成本，也是 §7 全部局限的根源。可选做法：

- **加 `source`（如 `"standard:<pack_id>"`）与 `pack_version` 字段**：可支持“仅当未被修改时才更新”“同步时删除本 pack 已移除的模板”“界面标注来源与版本”。代价：settings schema 升 v3、Provider 迁移与校验扩展、前端类型与 UI、SPEC-DM-012 §6.4 修订、回归测试。
- **不加字段，靠稳定 ID + 约定**：零成本，但永久接受 §7 的三条局限。

需要产品侧裁决：标准库是“偶尔换一次的初始素材”还是“需要持续演进、可追溯来源的受管资产”。前者不必升 v3，后者必须升。

### 8.2 pack 是否需要从远端拉取

“检查更新”若通过网络拉取 pack，会引入新的信任边界与网络依赖，与当前“Web 服务只监听 `127.0.0.1`、以本地文件为中心”的取向冲突。**本提案默认不支持远端拉取**：pack 由用户/管理员放到本地（共享盘、企业 IM、Release 附件）后导入。若确需远端，应单独设计签名、来源校验与失败降级。

### 8.3 标准库与字段命名规范的配套

模板表达式引用的是工作区字段目录里的字段名，这些是用户自定义属性而非产品内置字段。因此标准库若要“导入即可用”，必须与一份字段命名规范（对照表）同步分发。**需裁决**：该规范放在标准库仓库，还是沉淀为本项目的一份长期文档（`docs/dst-manager/`）。

### 8.4 上限的长期管理

100 套/用户的限制在“只增不删”的语义下会逐年逼近。需要决定：超出时由谁清理、是否要求标准库维护“退役模板清单”、是否在导入器中提供“清理未使用模板”的辅助能力。

### 8.5 用户改动策略的默认值

同一模板 ID 内容不同时，默认行为应是覆盖、跳过，还是“先另存副本再覆盖”？最后一种最安全但会消耗模板配额，且在无来源字段时无法自动判断哪些副本是历史残留。

## 9. 与本项目的关系

- **本文件不改变任何现有实现**，只是提案与事实记录。
- 若采纳通道 A/B：**不需要改本项目任何代码**，只需产出标准库仓库与导入脚本。
- 若采纳通道 D：需要同步修改的权威文档为 [SPEC-DM-012](../specs/SPEC-DM-012-sheet-catalog-extension.md)（§6 模板契约与设置 schema、§11 错误规则、§16 前端门禁记录）、[ARCH-DM-006](../architecture/ARCH-DM-006-builtin-extension-platform.md)（§8.1 应用级扩展设置、§8.3 工作区偏好、§11 同步执行与并发（设置快照与修订绑定）），以及 [GUIDE-DM-005](../guides/GUIDE-DM-005-builtin-extension-development.md) 中“随包且不可变的默认值”一节；实施需配套 settings schema v2 → v3 迁移与回归测试。
- 与 [RES-DM-001](RES-DM-001-number-format-code-conventions.md) 的关系：那份调研确定表达式语法形态（含格式码），本提案确定模板的批量分发方式，两者都作用于同一份模板契约，互不冲突。

## 10. 验证方式

| 层级 | 验证内容 |
| --- | --- |
| 标准库 CI（离线） | pack 结构、稳定 ID 派生规则可复现（同输入产生同 ID）、调用产品 `save_templates` 通过全部限制值校验、`requires` 字段清单与模板表达式实际引用一致 |
| 导入脚本（本地） | 幂等：连续导入两次，`user_templates` 与 `revision` 只按预期变化；过滤词在导入前后逐字一致；只读（schema 较新）时中止且不写入 |
| 端到端（真实应用） | 导入后在图纸目录设置界面可见、可选、可预览；已有工作区偏好仍指向同一模板；重名/超限 pack 被整体拒绝且界面数据未变 |
| 回归 | 导入不影响核心页面与其他扩展设置；`revision` 递增后旧客户端的乐观并发行为符合既有 409 语义 |

## 11. 调研过程与局限

- 事实全部来自本仓库源码与 `%LOCALAPPDATA%\dst-manager\data\dst-manager.db` 的实际内容读取（只读方式打开，未修改），未依赖外部资料，因此不存在版本漂移风险。
- 局限：本提案未在实际用户机器上执行过通道 A 的完整脚本流程，“秒级分发”是基于接口语义与数据体量的估计；`revision` 在导入瞬间与用户界面编辑并发时的实际抖动频率未实测。
- 局限：§7 的语义约束是从数据模型推出的必然结论，但“用户是否真的会编辑标准模板”属产品判断，需要真实使用反馈。
