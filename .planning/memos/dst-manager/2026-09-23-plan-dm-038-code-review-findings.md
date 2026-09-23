# PLAN-DM-038 代码审查遗留发现（2026-09-23）

来源：分支 `feature/plan-dm-038-standard-properties-and-dwg-naming`（main..HEAD，12 提交，约 1.46 万行）全量 diff 审查；7 项发现已逐条对照代码独立验证（含运行期实测）。执行记录见 `.superpowers/sdd/PLAN-DM-038-standard-properties-and-dwg-naming-remediation`。

## 已修复（不在遗留范围）

| # | 问题 | 修复 |
| --- | --- | --- |
| F1 | 前端 `DWG_NAME_*` 模板级文件名风险定为 error 并阻断发布，与计划 Task 8 Step 5「前端只提示，发布仍以后端码为准」矛盾（后端发布门禁不做文件名安全检查，后端可发布的标准被前端卡死；`publishModel.test.ts` 与 E2E 均锁定旧行为） | 已改 warning 级（`draftModel.ts` `filenameDiagnostics`），DWG 命名分区新增 `naming-risk-warning` 提示条，提交 `9a49ae1`，全量门禁通过 |

## 遗留发现

### F2 求值输入缺键被当作空值（契约防御缺口，低严重度）

- 位置：`src/dst_manager/domain/standard_rules.py:189`（映射源读取 `result.get(source_property_id, "")`）；同类形状在 `:256`（组合引用普通属性 `result.get(referenced, "")`）。
- 问题：`evaluate_standard_properties` 的 `values` 由宿主按 `property_id` 提供（当前无生产调用方，PLAN-DM-036 创建流程将消费）。宿主**漏传整个键**时，当前实现静默按空值处理并写入映射结果键；而 `standard_naming.py:11-13` 自己写明的约定是「普通属性必须提供键；派生属性上游失败时必须缺失键——缺失即代表上游无法计算」，应报 `DWG_NAMING_SOURCE_MISSING`。
- 实测证据（同一已发布标准，两种输入）：显式 `{"prop-major": ""}` → `{'prop-major': '', 'prop-code': ''}` 无诊断（设计行为，有测试锁定，**不可改**）；漏传 `{}` → `{'prop-code': ''}` 无诊断，命名静默渲染 `-001-003.dwg`。两种情况下游完全无法区分。
- 排除项：标准层面不存在「映射缺目标」——发布门禁已保证枚举值非空不重复（`STANDARD_ENUM_ITEM_INVALID`/`STANDARD_ENUM_ITEM_DUPLICATE`）、映射行固定全覆盖且目标非空（`STANDARD_MAPPING_TARGET_EMPTY`）、映射必须有源（`STANDARD_MAPPING_SOURCE_INVALID`）；非法非空运行值的失败传播链路（`STANDARD_ENUM_VALUE_INVALID` → blocked → 命名 `SOURCE_MISSING`）已验证正确。
- 建议修法：映射求值对「源键缺失」报一条诊断（可复用 `STANDARD_DERIVED_UPSTREAM_INVALID` 或新增码）且不写字典键；组合引用同理。显式 `""` 的合法行为不动。可在 PLAN-DM-036 实施时随宿主接线一起修（届时才有真实调用方）。

### F3 未知 `system_field` 前后端门禁分级不一致（轻微）

- 位置：`web/src/features/standards/draftModel.ts:538-540` vs `src/dst_manager/domain/standard_schema.py:285-291`。
- 问题：文档命名模板含**未知**系统字段（如 `foo.bar`，不在 `SYSTEM_FIELDS`）时，后端草稿解析即抛结构级 `STANDARD_SEGMENT_REFERENCE_UNKNOWN`（保存即 422），前端却归类为发布级 `STANDARD_SEGMENT_SCOPE_INVALID`——前端「结构 OK、可保存」，保存才吃到一个本地诊断列表里不存在的码。
- 影响：窄（文档需带未知系统字段，正常 UI 流程不会产生）；但前后端同一约束的分级口径应一致。
- 建议修法：前端 `segmentDiagnostics` 对不在全局系统字段表内的 `system_field` 先报结构级 `STANDARD_SEGMENT_REFERENCE_UNKNOWN`，再在允许列表校验失败时报 `STANDARD_SEGMENT_SCOPE_INVALID`。

### F4 诊断文案插值参数 `{field}`/`{source}` 未传递（轻微，信息丢失）

- 位置：`web/src/components/standards/StandardEditor.vue:363`（结构摘要只传 `{segment}`）；`publishModel.issueOf` 只传 `propertyName`/`itemId`/`segmentIndex`。
- 问题：zh-CN/en-US 语言包中约 10 条诊断文案含 `{field}`/`{source}` 占位符（如 `STANDARD_ID_INVALID`「标准 ID 非法：{field}」、`STANDARD_MAPPING_SOURCE_DUPLICATE`「源值重复（{source}）」），渲染为空——用户看不到出错的具体值。
- 建议修法：结构摘要路径为本地诊断补上可用参数（如非法的标准 ID 原值），或精简语言包文案去掉用不到的占位符；两条语言键集合需保持对称（check:i18n 会校验）。

### F5 前后端名称规范化口径不一致：`toLocaleLowerCase` vs `casefold`（轻微，边缘字符）

- 位置：`web/src/features/standards/draftModel.ts:330`（`normalizedPropertyName`）vs `src/dst_manager/domain/standard_models.py:54`（`normalize_property_name`）；`draftModel.ts:493,502` 文件名检查同用 `toLocaleLowerCase`。
- 问题：边缘字符大小写折叠不一致（如 `ß`.casefold()=`ss` vs `toLocaleLowerCase`=`ß`）：前端重名检查漏检，发布审查放行，后端发布时 422 `STANDARD_PROPERTY_NAME_DUPLICATE`。
- 建议修法：前端实现与 casefold 等价的规范化（`ß`→`ss`、`ﬀ`→`ff` 等映射表），或在语言包/注释中明确接受后端为最终口径、前端仅近似预检。真实触发概率极低（属性名含此类字符）。

## 已登记事项（审查确认非新发现，不重复处理）

- **`required` 标志发布期不强制**：台账 R10 与计划「残余风险 1」，已明确归属 PLAN-DM-036 创建流程；UI 保留编辑是为将来存数据。
- **应用层/仓储层重复解析与门禁**：R13 有意设计（仓储防线不可绕过），两处目前同源同码；如需消除 divergence 风险，可在 PLAN-DM-036 时评估把发布门禁收敛为仓储单道。

## 处理建议汇总

| 发现 | 建议归属 |
| --- | --- |
| F2 | PLAN-DM-036 实施时随 `evaluate_standard_properties` 宿主接线一起修（最自然）；如提前修需补「缺键→诊断且不写键」用例 |
| F3 | 小修，可并入 PLAN-DM-036 或独立一次提交 |
| F4 | 小修（传参或精简文案二选一），注意双语键对称 |
| F5 | 登记待办即可；建议接受「后端为最终口径」并在前端注释写明近似性 |
