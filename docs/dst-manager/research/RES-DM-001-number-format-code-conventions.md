---
id: RES-DM-001
title: 图号前导零格式化与格式码惯例调研
status: accepted
owners:
  - dst-manager
created: 2026-09-12
updated: 2026-09-12
related:
  - SPEC-DM-012
  - PLAN-DM-026
---

# 图号前导零格式化与格式码惯例调研

> 调研日期：2026-09-12
> 触发问题：图纸目录扩展是否需要、以及如何支持“字符串格式化输出”（如 `01` → `0001`、`01` → `1`）
> 结论性质：方案选型的证据基础，不含代码实施；实施计划见 [PLAN-DM-026](../../../.planning/plans/dst-manager/PLAN-DM-026-sheet-catalog-number-format-code.md)

## 1. 结论摘要

1. 成熟产品处理“前导零”只有两种模式：**格式属于元素（列/单元格）** 与 **格式属于可定位的片段（字段引用）**。两者不是风格偏好，而是由“一个输出元素里放几个值”决定的。
2. 本项目的目录单元格是**由字面量与多个字段引用拼成的组合串**（如 `{sheet.专业代码}-{sheet.number}`）。这类场景在业界一律采用“格式作用于片段”的做法；Revit 生态的第三方编号插件明确按“复合编号的每一段分别设置前导零”实现。
3. 因此**列级格式属性在本项目语义上不成立**：对组合串整串补零会得到 `0RQ-01`。这条结论否决了“给输出列加一个 format 属性”的方案。
4. 格式语言有三档形态（Excel 格式码 / 参数化函数 / 数值类型说明符）。由于本扩展所有字段都是**字符串**，第三档不可用（数值说明符在字符串域语义不稳定或直接报错），第二档需要引入函数、参数与倍性校验并被 [SPEC-DM-012](../specs/SPEC-DM-012-sheet-catalog-extension.md) §5.1 明确排除，**只有 Excel 格式码子集同时满足“用户已会、语法极小、语义确定”**。
5. 边界语义在业界已有明确先例：去零必须保留一位（朴素 `TRIM(LEADING '0')` 会把 `000` 变成空串，是反例）；非纯数字值按“能转就转、转不了原样保留”处理；空值不伪造。
6. 需要注意范围：AutoCAD 生态中用户往图号里写前导零，动机常常是让 Sheet Set Manager **按数字排序**（SSM 是字符串排序）。只读导出侧的格式化**不能**解决 SSM 内部排序；那属于重编号（写 DST）范围，本项目已有相应受控编辑能力，不应由导出扩展承担。

## 2. 模式一：格式属于元素（列 / 单元格 / 文本框）

| 产品 | 事实 | 出处 |
| --- | --- | --- |
| Excel 单元格自定义格式 | `0000` 是**单元格属性**；自定义数字格式只对数字生效，对文本需要写满四段才生效；只改变显示，不改变底层值与类型 | [Microsoft Support：保留前导零](https://support.microsoft.com/en-us/excel/keeping-leading-zeros-and-large-numbers)、[Ablebits：自定义数字格式](https://www.ablebits.com/office-addins-blog/custom-excel-number-format) |
| SSRS | `Format` 是文本框属性，也可在表达式里写 `=Format(Fields!x.Value,"0000")` | [Stack Overflow：SSRS custom number format](https://stackoverflow.com/questions/14051604/ssrs-custom-number-format) |
| JasperReports | `JRTextField.setPattern()`，pattern 属于**单个字段元素**，不是报表或列容器 | [JRTextField Javadoc](https://jasperreports.sourceforge.net/api/net/sf/jasperreports/engine/JRTextField.html) |

适用条件：**一个输出元素只承载一个值**。SSRS/JasperReports 里要得到 `RQ-001`，做法是把多个文本框并排放置，而不是给一列写格式。

## 3. 模式二：格式作用于可定位的片段

| 产品 | 事实 | 出处 |
| --- | --- | --- |
| Revit 第三方编号插件（ModPlus MPR Sheet Renumber） | 前导零可选，并且**“扩展编号（复合编号）时，前导零对复合编号的每一段分别设置”** | [modplus.org](https://modplus.org/en/news/mprsheetrenumberleadingzeroes) |
| Revit / Dynamo / pyRevit | 用户用 `String.PadLeft` 在拼接前对**该段**补零 | [Dynamo 论坛](https://forum.dynamobim.com/t/is-there-any-node-can-change-the-notation-of-numbers/63691) |
| Excel 公式写法 | `=TEXT(B5, REPT("0",C5))`：**宽度 = `0` 的重复次数** | [Exceljet：add leading zeros](https://exceljet.net/formulas/add-leading-zeros-to-numbers) |
| SQL | `LPAD(str, n, '0')` 补零 / `TRIM(LEADING '0' FROM x)` 去零，是两个正交的字符串级原语 | [DataCamp：MySQL LPAD](https://www.datacamp.com/doc/mysql/mysql-lpad)、[Baeldung：Remove Leading Zeros in SQL](https://www.baeldung.com/sql/remove-leading-zeros) |
| 模板引擎（Handlebars 等“逻辑无关”引擎） | 补零必须外挂 helper 或自写代码，核心不含格式化能力 | [Budibase 讨论：Handlebars helper](https://github.com/Budibase/budibase/discussions/2865) |

适用条件：**一个输出元素由多段拼成**，格式必须能指向其中一段。

## 4. 格式语言三档对比

| 档 | 形态 | 代表 | 本项目可用性 |
| --- | --- | --- | --- |
| Excel 格式码子集 | `:0000`（`0` 的个数 = 宽度） | Excel `TEXT(A1,"0000")`、`REPT("0",n)` | **采用**：语法增量只是一个冒号加若干 `0`；用户最可能在 Excel 里已经会写；语义与 `LPAD(x, n, '0')` 一致 |
| 参数化函数 | `padLeft(x,4,"0")` / `:D4` | .NET `D4`、SQL `LPAD`、JS `String.padStart` | 不采用：需要函数名、参数、类型与倍性校验；SPEC-DM-012 §5.1 明确排除函数与参数系统 |
| 数值类型说明符 | `%04d` / `{n:04d}` | C `printf`、Python `'{:04d}'`、Java `String.format("%04d")` | **不可复用**：语义依赖类型。Python 中 `f"{'Hi':04}"` 对字符串是**右补**得到 `'Hi00'`，而 `:04d` 对字符串直接报错；本扩展所有字段都是字符串，借用数值说明符会产生反直觉结果 |

结论：`format := ":" "0"{1,16}`（宽度 = `0` 的个数，`width=1` 即去前导零）是本项目唯一同时满足“用户已会、语法极小、语义确定”的形态。

## 5. 边界语义的业界证据

| 争议点 | 业界证据 | 采纳规则 |
| --- | --- | --- |
| 全零值去零 | SQL 的 `TRIM(LEADING '0' FROM '000')` 会得到**空串**（明确的错误行为）；SQL Server 还需更复杂写法才能安全去零 | 保留一位：`000` → `0`，绝不产生空串 |
| 非纯数字值 | Excel 混合数据列的通行写法是 `=IFERROR(VALUE(A2),A2)`——能转就转，转不了保留原值 | 原样输出，不警告，不阻断 |
| 已有前导零且超宽 | Excel 数字格式下“前导零不属于数据本身”，格式码表达的是**目标宽度** | 先归一化再补宽：`00123` 配 `:0000` 输出 `0123` |
| 空值 | 本扩展 [SPEC-DM-012](../specs/SPEC-DM-012-sheet-catalog-extension.md) §4.3 要求“空值不被伪造”，且缺值是允许导出的警告 | 空入空出，仍计入 `SHEET_CATALOG_VALUE_MISSING` |
| Excel 数值化 | 自定义格式只改显示；`TEXT()` 才是转文本；SSRS 导出 Excel 还要专门防前导零丢失 | 结果继续以字符串单元格写入（§9 既有约束） |

## 6. 与本项目的关系

- **否决列级 format 属性**：目录列是组合表达式，整串补零会产出 `0RQ-01`；模式一的适用条件在本项目不成立。
- **否决通用格式化管道**：SPEC-DM-012 §1/§5.1 已排除函数、条件、过滤器与任意管道；本轮调研未发现必须引入管道的真实场景（YAGNI）。
- **否决新增“补零后的虚拟字段”**：会产生字段爆炸，且无法与自定义属性组合。
- **范围区分（重要）**：AutoCAD 官方论坛存在用户为了**排序**在数据里写前导零的明确案例（[SSM does not order sheet views numerically](https://forums.autodesk.com/t5/autocad-forum/ssm-does-not-order-sheet-views-numerically-i-have-to-add-leading/td-p/9439531)），另有第三方插件（如 JTB Sheet Set Renumber）通过**修改数据**解决编号问题。本扩展是只读导出，输出侧格式化**不会**改变 SSM 内部排序；用户若诉求排序，应走重编号（写 DST）路径，属独立范围。
- **迁移成本**：格式码只扩展表达式语法，不改模板 `schema_version`，不需要数据迁移；旧版本读到格式码会在 `:` 处报阻断语法错误（`:` 原本就是点号形式的禁用字符），不会静默丢格式或导出错误数据。

## 7. 调研过程与局限

- 共 12 条查询、约 60 条结果，覆盖 Excel 自定义格式与 `TEXT`、.NET/Python/Java 格式化说明符、SQL `LPAD`/`TRIM`、SSRS 与 JasperReports 报表属性、Handlebars 等模板引擎、AutoCAD SSM 与第三方重编号插件、Revit/Dynamo 编号实践。
- 内置 Web 搜索提供方当次不可用，改用已认证的 `tvly`（Tavily CLI）按 `.agents/skills/tavily-search` 说明执行。
- 局限：证据来自公开文档、官方支持页与社区论坛，不构成对 AutoCAD SSM 官方能力的穷举；SSM 排序行为以论坛案例和本仓库既有 `domain/editing.py` 重编号能力为交叉参考。若后续要做重编号范围，需单独调研并单独立项。
