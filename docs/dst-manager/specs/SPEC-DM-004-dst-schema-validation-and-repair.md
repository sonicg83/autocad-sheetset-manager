---
id: SPEC-DM-004
title: DST XML Schema 校验与可修复加载契约
status: draft
document_kind: spec
created: 2026-08-27
updated: 2026-08-27
related:
- ARCH-DM-001
- SPEC-DM-001
- SPEC-DM-002
- PLAN-DM-006
- RES-SH-001
---

# DST XML Schema 校验与可修复加载契约

## 1. 范围与目标

本规范定义 DST Manager 对 `DST -> XML -> AcSm DOM` 的版本化结构契约、加载校验和安全修复边界，首先覆盖 `DbVersion=1.1` 的 Project1 AcSm XML 形态。目标是让官方 AutoCAD Sheet Manager 能识别程序新增的 Sheet，同时使历史 DST 中可证明的持久化元数据缺失能够被发现、记录和受控修复。

本规范不把黄金样本中的业务数量、具体项目名称、属性名称、文件路径或对象 `ID` 固化为通用格式。黄金样本是结构证据；通用约束只固化稳定的对象类型、字段类型、必需节点、顺序和跨节点不变量。

## 2. 契约版本与证据

- 契约版本以 `AcSmDatabase` 的 `DbVersion=1.1` 及当前根对象形态识别。
- `project1_sheetset.xml` 是完整黄金结构样本。
- `sheetset-fail.xml` 是失败样本，证明新增 Sheet 子树可能缺少固定 `clsid`、`propname`、`vt` 和 `AcSmSheetViews`。
- 具体对象 `ID` 每次新建或修复时独立生成，必须唯一且符合既有 `g{GUID}` 格式。

## 3. AcSm 最小结构契约

### 3.1 对象节点

| 节点 | 必需固定属性 | 说明 |
| --- | --- | --- |
| `AcSmSheetSet` | `ID`、`clsid`、`propname=SheetSet`、`vt=13` | 图纸集根对象 |
| `AcSmSubset` | `ID`、`clsid` | 子集对象；`Name` 使用 `AcSmProp vt=8` |
| `AcSmSheet` | `ID`、`clsid` | 黄金 XML 中 Sheet 根节点不要求额外的 `propname` 或 `vt` |
| `AcSmCustomPropertyBag` | `ID`、`clsid`、`propname=CustomPropertyBag`、`vt=13` | Sheet 和 SheetSet 的属性容器 |
| `AcSmCustomPropertyValue` | `ID`、`clsid`、属性名、`vt=13` | 属性定义/值对象 |
| `AcSmAcDbLayoutReference` | `ID`、`clsid`、`propname=Layout`、`vt=13` | Sheet 的唯一布局引用 |
| `AcSmSheetViews` | `ID`、`clsid`、`propname=SheetViews`、`vt=13` | Sheet 的空或非空视图容器 |

稳定的 Project1 `clsid` 为：

| 节点 | `clsid` |
| --- | --- |
| `AcSmSheetSet` | `gB20534F2-0978-418C-8D14-2E6928A077ED` |
| `AcSmSubset` | `g076D548F-B0F5-4FE1-B35D-7F7B73B8D322` |
| `AcSmSheet` | `g16A07941-BC15-4D48-A880-9D5A211D5065` |
| `AcSmCustomPropertyBag` | `g4D103908-8C86-4D95-BBF4-68B9A7B00731` |
| `AcSmCustomPropertyValue` | `g8D22A2A4-1777-4D78-84CC-69EF741FE954` |
| `AcSmAcDbLayoutReference` | `g94910E94-4FCA-427C-B6ED-2EC9E1C900C7` |
| `AcSmSheetViews` | `gF40F931B-64BC-4B90-9FC8-A11A77D6815B` |

### 3.2 Sheet 子树

每个 `AcSmSheet` 必须具有以下受控结构：

```text
AcSmSheet
├─ AcSmCustomPropertyBag
│  └─ AcSmCustomPropertyValue × N
├─ AcSmAcDbLayoutReference
│  ├─ AcDbHandle: vt=8
│  ├─ FileName: vt=8
│  ├─ Name: vt=8
│  └─ Relative_FileName: vt=8
├─ Number: vt=8
├─ AcSmSheetViews
└─ Title: vt=8
```

图纸属性的 `Flags` 使用 `vt=3`，非空 `Value` 使用 `vt=8`。空自定义属性缺少 `Value` 是合法表示，不得自动补写空 `Value`。

### 3.3 语义不变量

- 全文 `ID` 大小写不敏感唯一，并符合 AcSm ID 格式。
- 每张 Sheet 恰好有一个 `AcSmAcDbLayoutReference`。
- 布局引用包含 `AcDbHandle`、`FileName`、`Name` 和 `Relative_FileName`。
- 正式完成的布局 Handle 不能为占位值 `0`，且必须是合法十六进制文本。
- 每个自定义属性值恰好有一个合法 `Flags`，其作用域与所有者一致。
- 已知受控节点的固定属性和受控 `AcSmProp` 的 `vt` 必须与上下文契约一致。
- 未知节点、未知属性、未知兄弟顺序和混合内容边界必须保留。

## 4. 校验器与修复器

实现由三层组成：

1. 版本化 `AcsmContract` 提供节点、属性、顺序和修复规则；
2. 严格 Schema 校验器检查修复后的结构，允许未知扩展保留；
3. 语义校验器检查 ID、布局、属性作用域、Handle 和跨节点关系。

严格 schema 不能直接作为第一步，因为可修复输入本身可能缺少 schema 所需属性。实际顺序是“宽松契约扫描 → 内存副本修复 → 严格 schema → 语义校验”。

### 4.1 允许自动修复

| 问题 | 修复规则 | 等级 |
| --- | --- | --- |
| 对象缺 `ID` | 生成唯一随机 AcSm ID | deterministic |
| 已知对象缺 `clsid` | 按节点类型补固定 `clsid` | deterministic |
| 已知对象缺 `propname` 或 `vt` | 按节点上下文补固定值 | deterministic |
| `AcSmProp` 缺 `vt` | 按属性名、父节点和同类样本推断 | deterministic 或 inferred |
| Sheet 缺 `AcSmSheetViews` | 创建带完整固定属性的空节点 | deterministic |
| Sheet 缺属性袋 | 依据已确认的 Sheet 属性定义创建 | inferred |
| Sheet 缺属性项 | 仅在 SheetSet 或其他 Sheet 能唯一确认定义和作用域时创建 | inferred |

修复必须在 DOM 副本上事务式执行。任一修复无法完成时，丢弃副本并保留原始解析结果，不产生半修复对象。

> 实施说明（PLAN-DM-009 已落地）：`AcsmRepairer` 对深拷贝 DOM 顺序执行
> “全局 ID 索引 → 补 ID → 补固定属性 → 补 AcSmProp vt → 黄金位置补
> `AcSmSheetViews`”；无法确定的修复（缺业务值、布局缺失/冲突、属性作用域
> 冲突、非空错误固定值）不覆盖原值，而是进入 `blocking_issues` 并形成
> `INVALID_REPAIR_REQUIRED`/`INVALID_UNRECOVERABLE` 阻断状态，不再以
> “丢弃整个副本”处理——这与本规范的“可识别修复 + 阻断诊断”目标一致。

### 4.2 必须阻断

- XML 编码、语法或 DST 解码失败；
- ID 重复、ID 无法唯一归属或外部引用冲突；
- 缺少 `Number`、`Title`、文件路径、布局名称等业务信息；
- 缺少布局且没有足够信息重建；
- 多个布局引用无法判定；
- 自定义属性作用域、Flags 或值存在冲突；
- 修复后仍不能通过严格 schema 或语义校验。

## 5. 统一加载与发布

所有读取 XML 的入口都必须使用统一加载器：

```text
DST decode
 → XML parse
 → 宽松契约扫描
 → 内存修复
 → 严格 schema
 → 语义校验
 → 领域投影
```

加载器返回原始文件基准、修复后的 DOM/领域对象和 `RepairReport`。原始 DST 的 hash 继续作为工作区和发布基准，不能用修复后的 DOM hash 替代。

加载阶段不得修改 DST、DWG、文件时间戳或创建 `.dst-manager/`。用户只读查看或取消时直接丢弃修复结果。用户确认修复或提交业务编辑时，修复作为独立受控修订进入现有 before 快照、写锁、暂存、复核、发布和回滚流程。

发布阶段在写锁内重新读取 DST，并复核原始文件 hash/identity；然后重新执行相同修复、应用业务变更、严格校验、DST 往返校验后才允许发布。

## 6. 诊断与接口表现

每条自动修复记录节点 ID 或 XPath、问题代码、原始状态、修复后状态、规则来源和 `deterministic`/`inferred` 等级。修复完成但仍存在环境问题时，环境问题继续作为诊断返回；不可恢复问题阻断可写流程。

建议区分以下结果：

- `VALID`：无问题；
- `REPAIRED`：修复后通过校验，等待用户确认是否持久化；
- `INVALID_REPAIR_REQUIRED`：存在可识别但未获确认的修复；
- `INVALID_UNRECOVERABLE`：存在不可恢复问题，禁止发布。

## 7. 测试与验收

- 黄金 XML：零修复，严格 schema 和语义校验通过。
- `sheetset-fail.xml`：固定缺失属性和节点能够被修复，修复报告稳定，修复后通过校验。
- 新建 Sheet/Subset：生成完整固定对象属性、布局字段、属性袋和 `AcSmSheetViews`。
- 空自定义属性：不因缺少 `Value` 被误修复。
- 缺业务信息、重复 ID、冲突布局和冲突属性作用域：稳定阻断。
- 加载修复不改变原始文件、hash、DWG 和时间戳。
- 用户确认后修复作为受控修订发布，失败时整批回滚。
- 所有 DST/XML 入口均覆盖统一加载器，未知节点和属性保持不变。

真实 AutoCAD 2016/2020 组件验收仍需在具备私有样本、Core Console 和 Worker 的环境中执行；schema/修复单元测试不替代官方 Sheet Manager 显示验收。

## 8. 非目标

- 不自动猜测缺失的业务标题、图号、文件路径或布局名称；
- 不修复重复 ID、冲突引用或多个候选布局；
- 不在加载时直接写回原始 DST；
- 不把 Project1 的属性数量和项目文字变成所有 DST 的硬编码要求；
- 不删除或规范化未知 AcSm 扩展节点。
