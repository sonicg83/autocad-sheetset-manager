---
id: PLAN-DM-026
title: 图纸目录数字格式码实施计划
status: proposed
document_kind: plan
owners:
  - dst-manager
created: 2026-09-12
updated: 2026-09-12
related:
  - SPEC-DM-012
  - RES-DM-001
  - ARCH-DM-005
  - ARCH-DM-006
  - PLAN-DM-020
  - PLAN-DM-023
  - PLAN-DM-025
---

# 图纸目录数字格式码实施计划

> **供代理执行：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐条执行；每个生产改动严格遵循测试先红、最小实现转绿、重构保持绿灯。步骤使用 `- [ ]` 跟踪。本计划只编制实施步骤，不自动修改生产代码或提交 Git。

**目标：** 让用户在只读导出的图纸目录里对**单个字段引用**使用数字格式码，把图号 `01` 输出为 `0001`（`{sheet.number:0000}`）或 `1`（`{sheet.number:0}`），从而在不修改 DST 数据的前提下统一图号宽度。

**架构：** 复用现有表达式 FSM 与唯一求值出口 `evaluate_expression`：解析阶段把可选的 `format := ":" "0"{1,16}` 解析为字段 token 上的 `format_width`，绑定阶段透传，求值出口调用纯函数 `format_value` 做“先归一化前导零、再左补零到目标宽度”的字符串变换。预览 `build_preview` 与导出 `extension._catalog_rows` 都经过该出口，因此格式语义不可能在两条链路上分叉；列投影摘要 `_digest_token` 只在存在格式码时追加 `("format", "0"*width)`，保证未使用格式码的既有模板 `preview_digest` 逐字节不变。前端只在字段浏览器条目上增加格式入口，不改输出列编辑器的 5 轨道布局，也不引入列级格式控件（避免对 `{sheet.专业代码}-{sheet.number}` 这类组合结果整串补零）。

**技术栈：** Python 3.12、FastAPI、Pydantic、Vue 3、TypeScript、vue-i18n、Vite、Vitest、Playwright、pytest、UV。

**规范：** [SPEC-DM-012](../../../docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md) §1、§2.2、§4.1、§5.1～§5.4、§7.2、§11、§15.1、§16；方案证据与业界惯例见 [RES-DM-001](../../../docs/dst-manager/research/RES-DM-001-number-format-code-conventions.md)。

## 全局约束

- 本轮只做**只读导出的输出格式化**：不修改 DST/DWG、不写回任何属性值、不做重编号；Sheet Set Manager 内部按字符串排序的问题属重编号（写 DST）范围，本计划不覆盖。
- 语法增量固定为 `field_reference := "{" scope name_part format? "}"`、`format := ":" "0"{1,16}`；宽度等于 `0` 的个数，`width=1` 即去前导零。不引入函数、参数、条件、管道或数值类型说明符。
- 语义固定（SPEC-DM-012 §5.4）：`format_value(value, width)` 在 `width is None`、空串或值不是纯 ASCII 数字串时原样返回；否则 `(value.lstrip("0") or "0").rjust(width, "0")`。**不得使用 `str.zfill`**（`"00123".zfill(4) == "00123"` 与“先归一化再补宽”冲突，且 `"01".zfill(1) == "01"` 使去零失效）。不 trim、不截断、不解析符号/小数点/全角数字。
- 空值空入空出：格式码绝不把缺值补成 `0000`，缺值仍按 SPEC §4.3 计入 `SHEET_CATALOG_VALUE_MISSING`；非纯数字值原样输出且不产生任何新警告。
- 不新增错误码：格式码缺失、非法字符、重复、宽度越界与未闭合全部复用 `SHEET_CATALOG_EXPRESSION_INVALID`，`source_start` 指向该引用的 `:`（重复格式码指向第二个 `:`）。因此 `errors.py` 四张登记表、双语消息目录与 `tests/unit/test_message_catalog.py` 均不改。
- 模板 `schema_version` 保持 1，无数据迁移、无 API 字段变化、无数据库结构变化、无新依赖。
- 未使用格式码时列投影 token 形态与本次改动前完全一致；`tests/unit/test_sheet_catalog_preview.py::test_preview_digest_uses_canonical_json_with_fixed_keys_and_compact_separators` 是这条不变量的人工钉桩，不得为“顺手统一格式”而改写它。
- 本计划与 PLAN-DM-025 都会修改 `preview.py`、API 类型和前端目录组件，不得并行实施。若 PLAN-DM-025 已先完成，本计划的“无 API 字段变化”指不再新增格式码专用字段，必须保留其 `settings_revision`、`filtered_rows`、设置 digest 与输出过滤语义，并以合并后的当前 canonical 摘要为回归基线。
- 前端不改 `ColumnEditor.vue` 的 5 轨道布局、列签名与光标协议；格式入口只加在 `FieldBrowser.vue` 的字段条目上，插入的引用仍走既有 `insertReference`。新按钮的可访问名不得包含字段引用文本（如 `sheet.number`），否则 `web/tests/e2e/sheet-catalog.spec.ts` 中按 `/sheet\.number/` 定位的严格模式选择器会因多个匹配而失败。
- SPEC §16 门禁：主流程、布局结构与关键状态类别未变，**G3/G4 不重开**；新控件需补 G8 浅深主题与 200% 缩放证据；G9 真实验收清单追加“导出 XLSX 中补零图号为文本单元格”。
- 目标系统 Windows 11 + PowerShell；Python 依赖用 UV 管理，不执行 `pip install`；每个任务更新 `changelog.md`，只提交本任务文件。

## 追踪矩阵

| ID | 要求 | 实施任务 | 自动验证 | 完成判据 |
| --- | --- | --- | --- | --- |
| F1 | 解析 `:0{1,16}`，非法格式码阻断且定位到 `:` | 1 | `tests/unit/test_sheet_catalog_expressions.py` | 接受/拒绝两张参数表全绿 |
| F2 | 求值按 §5.4 语义变换，空值不伪造 | 1 | 同上 | §5.4 表格逐行通过 |
| F3 | 格式宽度贯通绑定与 `field_reference` | 1 | 同上 | 绑定 token 与语法生成一致 |
| F4 | 预览行应用格式，缺值警告保留 | 2 | `tests/unit/test_sheet_catalog_preview.py` | 行值与警告同时成立 |
| F5 | 摘要对格式敏感、对无格式幂等 | 2 | 同上 + 既有 canonical JSON 钉桩 | 无格式摘要不变，格式变化摘要变化 |
| F6 | XLSX 中补零值仍为文本 | 2 | `tests/integration/test_sheet_catalog_export.py` | openpyxl 回读字符串 `0001` |
| F7 | 格式入口可插入语法且预览生效 | 3 | Vitest + Playwright | 单测 + E2E 全绿，`npm run build` 通过 |
| F8 | 门禁证据与索引收口 | 4 | G8 证据 + 全量回归 | 截图留档、索引更新、全量绿 |

---

## 任务 1：表达式解析与求值的数字格式码

**文件：**

- 修改：`src/dst_manager/extensions/builtin/sheet_catalog/expressions.py`
- 修改：`tests/unit/test_sheet_catalog_expressions.py`
- 修改：`changelog.md`

**接口：**

- `FieldToken(scope, name, source_start, quoted=False, format_width=None)`；`BoundFieldToken(scope, canonical_name, builtin, format_width=None)`；`format_width: int | None` 为格式码中 `0` 的个数。
- 新增模块级常量 `_MAX_FORMAT_WIDTH = 16`、`_DIGITS = frozenset("0123456789")`，并在 `__all__` 增加 `"format_value"`。
- 新增纯函数：

  ```python
  def format_value(value: str, width: int | None) -> str:
      """按 §5.4 数字格式码变换：先归一化前导零，再左补零到目标宽度。"""
  ```

- `field_reference(scope: str, canonical_name: str, format_width: int | None = None) -> str`（既有两参调用保持原行为与原文案）。
- 语法：`field_reference := "{" scope name_part format? "}"`、`name_part := "." identifier | "[" json_string "]"`、`format := ":" "0"{1,16}`；点号与方括号两种形式都可后接格式码。
- 错误：一律 `SHEET_CATALOG_EXPRESSION_INVALID`（`blocking=True`），`params["source_start"]` 指向该引用的 `:`；`{sheet.number:0:0}` 指向第二个 `:`。
- 有意的行为微调：`_parse_quoted_name` 改为消费到 `]` 之后返回（原实现要求 `]}` 相邻）。因此 `'{sheet["a" ]}'` 仍在 10 处报错（既有断言不变），而 `'{sheet["a"]x}'` 的报错位置由 10 变为 11（指向 `x`）。这是新的、更精确的位置，不要为“保持旧位置”改回 `]}` 相邻检查。

- [ ] **步骤 1：写解析接受红灯。** 在 `tests/unit/test_sheet_catalog_expressions.py` 的 `test_parse_expression_accepts_restricted_grammar` 之后新增：

  ```python
  @pytest.mark.parametrize(
      ("source", "expected"),
      [
          pytest.param(
              "{sheet.number:0000}",
              (FieldToken("sheet", "number", 0, False, 4),),
              id="补零到 4 位",
          ),
          pytest.param(
              "{sheet.number:0}",
              (FieldToken("sheet", "number", 0, False, 1),),
              id="宽度 1 去前导零",
          ),
          pytest.param(
              '{sheet["专业:代码"]:000}',
              (FieldToken("sheet", "专业:代码", 0, True, 3),),
              id="方括号形式带格式码",
          ),
          pytest.param(
              "{sheet.专业代码}-{sheet.number:00}",
              (
                  FieldToken("sheet", "专业代码", 0, False),
                  LiteralToken("-"),
                  FieldToken("sheet", "number", 13, False, 2),
              ),
              id="组合表达式只格式化一个引用",
          ),
          pytest.param(
              "{sheet.number:0}0",
              (FieldToken("sheet", "number", 0, False, 1), LiteralToken("0")),
              id="引用后紧跟字面量零",
          ),
      ],
  )
  def test_parse_expression_accepts_number_format_code(source, expected):
      assert parse_expression(source) == expected
  ```

- [ ] **步骤 2：写解析拒绝红灯。** 紧跟其后新增（位置均为 0-based）：

  ```python
  @pytest.mark.parametrize(
      ("source", "source_start"),
      [
          pytest.param("{sheet.number:}", 13, id="格式码为空"),
          pytest.param("{sheet.number:abc}", 13, id="格式码含非零字符"),
          pytest.param("{sheet.number:0:0}", 15, id="重复格式码定位第二个冒号"),
          pytest.param("{sheet.number:" + "0" * 17 + "}", 13, id="宽度 17 超限"),
          pytest.param("{sheet.number:0000", 13, id="带格式码未闭合"),
          pytest.param('{sheet["a"]:0 }', 11, id="格式码后有多余内容"),
      ],
  )
  def test_parse_expression_rejects_invalid_number_format_code(source, source_start):
      with pytest.raises(SheetCatalogError) as excinfo:
          parse_expression(source)
      error = excinfo.value
      assert error.code == "SHEET_CATALOG_EXPRESSION_INVALID"
      assert error.blocking is True
      assert error.params["source_start"] == source_start
  ```

- [ ] **步骤 3：跑红灯。**

  ```powershell
  uv run pytest tests/unit/test_sheet_catalog_expressions.py -q -k "number_format_code"
  ```

  预期：接受表因 `FieldToken` 不接受第 5 个参数、拒绝表因 `:` 落入 `_DOT_NAME_FORBIDDEN` 而失败。

- [ ] **步骤 4：实现解析。** 在 `expressions.py` 中：给 `FieldToken`/`BoundFieldToken` 增加 `format_width: int | None = None`；`_parse_dot_name` 的循环终止集合改为 `"}:"`（保留循环内的 `_DOT_NAME_FORBIDDEN` 检查，因此 `{sheet.number()}`、`{sheet.a=b}` 的既有位置断言不变）；`_parse_quoted_name` 改为消费到 `]` 后返回 `index + 1`；新增 `_parse_format` 并在 `_parse_field` 中统一调用：

  ```python
  def _parse_format(source: str, start: int) -> tuple[int | None, int]:
      """解析字段引用尾部的数字格式码，返回 (宽度, 新游标)。"""
      if start >= len(source) or source[start] != ":":
          return None, start
      index = start + 1
      while index < len(source) and source[index] == "0":
          index += 1
      width = index - start - 1
      if width == 0 or width > _MAX_FORMAT_WIDTH:
          raise _invalid(start)
      if index < len(source) and source[index] == ":":
          raise _invalid(index)
      if index >= len(source) or source[index] != "}":
          raise _invalid(start)
      return width, index
  ```

  `_parse_field` 的顺序固定为：作用域 → 名称部分（点号或方括号）→ `_parse_format` → 使用格式码返回的游标断言 `}`，保证 `{sheet.number:0000}` 只可能走通一条路径；因此方括号分支不再提前 `return`：

  ```python
  def _parse_field(source: str, start: int) -> tuple[FieldToken, int]:
      index = start + 1
      scope_start = index
      while index < len(source) and source[index] not in ".[{":
          index += 1
      if index >= len(source) or source[index] == "{":
          raise _invalid(start)
      scope = source[scope_start:index]
      if scope not in _SCOPES:
          raise _invalid(start)
      if source[index] == "[":
          name, index = _parse_quoted_name(source, index + 1, start)
          quoted = True
      elif source[index] == ".":
          name, index = _parse_dot_name(source, index + 1)
          quoted = False
      else:  # "}": 引用缺少名称部分。
          raise _invalid(start)
      width, index = _parse_format(source, index)
      if index >= len(source) or source[index] != "}":
          raise _invalid(index)
      return FieldToken(scope, name, start, quoted=quoted, format_width=width), index + 1
  ```

  并相应修改 `_parse_quoted_name` 的收尾（不再要求 `]}` 相邻）：

  ```python
      if index >= length or source[index] != "]":
          raise _invalid(index)
      return "".join(chars), index + 1
  ```

- [ ] **步骤 5：跑解析绿灯。**

  ```powershell
  uv run pytest tests/unit/test_sheet_catalog_expressions.py -q
  ```

- [ ] **步骤 6：写语义红灯。** 在导入列表中加入 `format_value`（`from dst_manager...expressions import (...)` 内按字母序放在 `field_reference` 之后），并新增语义表用例：

  ```python
  @pytest.mark.parametrize(
      ("value", "width", "expected"),
      [
          pytest.param("1", 4, "0001", id="短值补零"),
          pytest.param("01", 4, "0001", id="已有前导零补到目标宽度"),
          pytest.param("0001", 4, "0001", id="目标宽度幂等"),
          pytest.param("00123", 4, "0123", id="先归一化再补宽"),
          pytest.param("12345", 4, "12345", id="超出宽度不截断"),
          pytest.param("01", 1, "1", id="宽度 1 去前导零"),
          pytest.param("000", 1, "0", id="全零保留一位"),
          pytest.param("0", 4, "0000", id="零补到宽度"),
          pytest.param("", 4, "", id="空值空入空出"),
          pytest.param("A01", 4, "A01", id="非纯数字原样"),
          pytest.param("01A", 4, "01A", id="尾部字母原样"),
          pytest.param("1-2", 4, "1-2", id="区间值原样"),
          pytest.param("1.2", 4, "1.2", id="小数原样"),
          pytest.param("１２３", 4, "１２３", id="全角数字原样"),
          pytest.param(" 01", 4, " 01", id="不 trim 空格"),
          pytest.param("01", None, "01", id="无格式码原样"),
      ],
  )
  def test_format_value_applies_number_format_code(value, width, expected):
      assert format_value(value, width) == expected


  def test_evaluate_expression_applies_format_code_per_field():
      bound = bind_expression(
          parse_expression("{sheet.专业代码}-{sheet.number:0000}"), make_catalog()
      )
      assert evaluate_expression(bound, make_sheetset_scope(), make_sheet()) == "水-0002"


  def test_evaluate_expression_format_code_never_fakes_missing_value():
      sheet = make_sheet()
      sheet = replace(sheet, custom_properties=())
      bound = bind_expression(parse_expression("{sheet.专业代码:0000}"), make_catalog())
      assert evaluate_expression(bound, make_sheetset_scope(), sheet) == ""
  ```

  该文件尚未导入 `replace`，需在顶部新增 `from dataclasses import replace`（ruff isort 会把它排在 `from pathlib import Path` 之前）；`make_catalog()` 已包含 `专业代码`，`make_sheet()` 的 `number="002"`、`专业代码="水"`。

- [ ] **步骤 7：跑语义红灯。**

  ```powershell
  uv run pytest tests/unit/test_sheet_catalog_expressions.py -q -k "format_value or format_code"
  ```

  预期：`format_value` 尚未定义导致导入失败。

- [ ] **步骤 8：实现语义。** 新增 `format_value` 并在 `evaluate_expression` 组装 `parts` 的唯一位置接入：

  ```python
  def format_value(value: str, width: int | None) -> str:
      """按 SPEC-DM-012 §5.4 变换：非纯数字或空值原样，否则先归一化再补宽。"""
      if width is None or not value or any(char not in _DIGITS for char in value):
          return value
      return (value.lstrip("0") or "0").rjust(width, "0")
  ```

  字段分支改为 `parts.append(format_value(value, token.format_width))`；字面量分支不变，且**只在此处调用一次**，不得在 `_catalog_rows` 或 `build_preview` 里二次格式化。

- [ ] **步骤 9：写绑定与语法生成红灯。** 追加：

  ```python
  def test_bind_expression_propagates_format_width():
      bound = bind_expression(parse_expression("{sheet.number:0000}"), make_catalog())
      token = bound.tokens[0]
      assert isinstance(token, BoundFieldToken)
      assert token.format_width == 4


  @pytest.mark.parametrize(
      ("scope", "name", "width", "expected"),
      [
          pytest.param("sheet", "number", 4, "{sheet.number:0000}", id="点号形式补零"),
          pytest.param("sheet", "number", 1, "{sheet.number:0}", id="点号形式去零"),
          pytest.param("sheet", "number", None, "{sheet.number}", id="无格式码保持旧语法"),
          pytest.param("sheet", "专业.代码", 3, '{sheet["专业.代码"]:000}', id="方括号形式补零"),
          pytest.param("sheetset", "项目 名称", None, '{sheetset["项目 名称"]}', id="方括号无格式码"),
      ],
  )
  def test_field_reference_appends_number_format_code(scope, name, width, expected):
      assert field_reference(scope, name, width) == expected
  ```

- [ ] **步骤 10：实现绑定透传与语法生成绿灯。** `_bind_field` 复制 `format_width`；`field_reference` 增加第三参并在引用闭合大括号前拼 `":0" * width`（`width is None` 时保持原输出，`width` 传入时不再做 `_DOT_NAME_FORBIDDEN` 判定，因为已知是规范名）：

  ```python
  def field_reference(scope: str, canonical_name: str, format_width: int | None = None) -> str:
      """生成指向规范名称的引用语法：点号或方括号 JSON 字符串，可附加数字格式码。"""
      needs_quoted = (
          not canonical_name
          or any(char in _DOT_NAME_FORBIDDEN for char in canonical_name)
          or (
              scope == "sheet"
              and canonical_name.casefold() in _BUILTIN_CASEFOLD
              and canonical_name not in SHEET_BUILTIN_FIELDS
          )
      )
      if needs_quoted:
          reference = f'{{{scope}[{json.dumps(canonical_name, ensure_ascii=False)}]}}'
      else:
          reference = f"{{{scope}.{canonical_name}}}"
      if format_width is None:
          return reference
      return f"{reference[:-1]}:{'0' * format_width}}}"
  ```

  名称含 `:` 时 `needs_quoted` 已为真（`:` 在 `_DOT_NAME_FORBIDDEN` 内），因此只会生成 `{sheet["专业:代码"]:000}` 这种无歧义形式。

  ```powershell
  uv run pytest tests/unit/test_sheet_catalog_expressions.py -q
  ```

- [ ] **步骤 11：聚焦回归与静态检查。**

  ```powershell
  uv run pytest tests/unit/test_sheet_catalog_expressions.py tests/unit/test_sheet_catalog_templates.py -q
  uv run ruff check .
  ```

- [ ] **步骤 12：记录并提交。** `changelog.md` 新增当日条目，记录“表达式新增数字格式码 `:0{1,16}`、语义先归一化再补宽、错误复用 `EXPRESSION_INVALID`”；只暂存本任务文件，commit message：`支持图纸目录表达式数字格式码解析与求值`。

## 任务 2：预览摘要、预览行与 XLSX 文本单元格

**文件：**

- 修改：`src/dst_manager/extensions/builtin/sheet_catalog/preview.py`
- 修改：`tests/unit/test_sheet_catalog_preview.py`
- 修改：`tests/integration/test_sheet_catalog_export.py`
- 修改：`changelog.md`

**接口：**

- `_digest_token(token) -> tuple[str, ...]` 签名不变；无格式码时返回既有 4 元组，有格式码时返回 `("field", scope, canonical_name, "builtin"|"custom", "format", "0" * width)`。
- 预览行、`extension._catalog_rows` 与 XLSX 写入路径不改：格式已经在 `evaluate_expression` 内完成。

- [ ] **步骤 1：写预览与摘要红灯。** 在 `tests/unit/test_sheet_catalog_preview.py` 追加：

  ```python
  def test_preview_rows_apply_number_format_code():
      template = make_template(
          make_column("图号", "{sheet.number:0000}"),
          make_column("目录号", "{sheetset.项目号}-{sheet.number:0}"),
      )
      result = build(make_sheet(), template=template)

      assert result.executable is True
      assert result.rows == (("0001", "P-000-1"),)


  def test_preview_digest_changes_with_number_format_code():
      # 固定 column_id/表头，只让 token 不同，避免列 ID 差异掩盖 token 差异
      def digest_with(tokens):
          return preview_digest(
              workspace_id="ws-1",
              revision_id="rev-1",
              template_schema=1,
              normalized_columns=(DigestColumn("c-1", "图号", (tokens,)),),
              extension_version="0.1.0",
              action_id="export-xlsx",
              extension_id="dst-manager.sheet-catalog",
          )

      baseline = digest_with(("field", "sheet", "number", "builtin"))
      padded = digest_with(("field", "sheet", "number", "builtin", "format", "0000"))
      narrower = digest_with(("field", "sheet", "number", "builtin", "format", "000"))

      assert padded != baseline
      assert padded != narrower


  def test_preview_missing_value_warning_survives_number_format_code():
      sheets = (
          make_sheet("sheet-1", properties=(SnapshotProperty("比例", ""),)),
          make_sheet("sheet-2", properties=()),
      )
      template = make_template(make_column("比例", "{sheet.比例:0000}"))

      result = build(*sheets, template=template)

      assert result.executable is True
      assert [warning.code for warning in result.warnings] == ["SHEET_CATALOG_VALUE_MISSING"]
      assert result.rows == (("",), ("",))
  ```

  夹具事实（已核对）：`result.rows` 是元组嵌套（既有断言形如 `result.rows == (("001",), ("002",))`）；`make_sheet()` 默认 `number="001"`、`properties=(SnapshotProperty("比例", "1:100"),)`，快照项目号为 `P-000`；缺值形参是 `properties` 而不是 `custom_properties`，构造“已定义但缺值”要在保留 `definitions` 默认值的同时传空 `properties`；文件顶部已导入 `DigestColumn`、`preview_digest` 与 `SnapshotProperty`，无需新增导入。`test_preview_digest_uses_canonical_json_with_fixed_keys_and_compact_separators` 继续用同一形态的 token 钉住无格式码摘要不变。

- [ ] **步骤 2：跑红灯。**

  ```powershell
  uv run pytest tests/unit/test_sheet_catalog_preview.py -q -k "number_format_code"
  ```

  预期：行值仍是 `001`/`P-000-1`（格式未被求值），而 `padded != baseline` 失败。

- [ ] **步骤 3：实现摘要投影。**

  ```python
  def _digest_token(token: LiteralToken | BoundFieldToken) -> tuple[str, ...]:
      if isinstance(token, LiteralToken):
          return ("literal", token.value)
      base = (
          "field",
          token.scope,
          token.canonical_name,
          "builtin" if token.builtin else "custom",
      )
      if token.format_width is None:
          return base
      return (*base, "format", "0" * token.format_width)
  ```

  不要调整 `_digest_columns`、`preview_digest` 的 payload 键集或 `json.dumps` 参数：既有 `test_preview_digest_uses_canonical_json_with_fixed_keys_and_compact_separators` 是“无格式码摘要不变”的钉桩，必须原样通过。

- [ ] **步骤 4：跑绿灯并钉住无格式不变量。**

  ```powershell
  uv run pytest tests/unit/test_sheet_catalog_preview.py -q
  uv run pytest "tests/unit/test_sheet_catalog_preview.py::test_preview_digest_uses_canonical_json_with_fixed_keys_and_compact_separators" -q
  ```

- [ ] **步骤 5：写导出红灯。** 在 `tests/integration/test_sheet_catalog_export.py` 追加（新建 `format_code_template`，与既有 `draft_template` 并列）：

  ```python
  def format_code_template(expression: str) -> dict:
      """带数字格式码的未保存草稿模板（SPEC-DM-012 §5.4）。"""
      return {
          "template_id": None,
          "name": "格式码草稿",
          "schema_version": 1,
          "columns": [
              {
                  "column_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "export:format-code")),
                  "header": "图号",
                  "expression": expression,
              }
          ],
      }


  def test_number_format_code_exports_string_cell_with_leading_zeros(tmp_path, tiny_workspace):
      client = make_client(tmp_path, save_grants=SaveGrantStore())
      workspace = open_workspace(client, tiny_workspace)
      template = format_code_template("{sheet.number:0000}")
      target = tmp_path / "exports"
      target.mkdir()
      grant = create_grant(grant_store(client), workspace, target / "带格式码.xlsx")
      preview_body = preview_action(client, workspace, template=template)

      assert preview_body["executable"] is True
      assert preview_body["rows"] == [["0001"]]

      resp = execute_action(
          client, workspace, preview_body, grant.save_grant_id, template=template
      )
      assert resp.status_code == 200, resp.text

      workbook = load_workbook(resp.json()["output_path"])
      worksheet = workbook[workbook.sheetnames[0]]
      cell = worksheet.cell(row=2, column=1)
      assert cell.value == "0001"
      assert cell.data_type == "s"  # 文本单元格，不是数值
      workbook.close()
  ```

  `tiny_workspace` 的 `Number` 为 `001`，因此补零到 4 位应得到 `0001`；表名取 `workbook.sheetnames[0]`，不硬编码模板名。

- [ ] **步骤 6：跑红灯。**

  ```powershell
  uv run pytest tests/integration/test_sheet_catalog_export.py -q -k "number_format_code"
  ```

  预期：预览 `executable` 为 `False`，`errors[0]["code"] == "SHEET_CATALOG_EXPRESSION_INVALID"` 且 `source_start` 指向表达式里的 `:`，导出拿不到可用预览。步骤 3～4 之后该用例必须转绿；若仍是红的，优先核对 `evaluate_expression` 是否真的在求值阶段套用格式，而不是靠测试放宽断言。

- [ ] **步骤 7：跑绿灯与聚焦回归。**

  ```powershell
  uv run pytest tests/integration/test_sheet_catalog_export.py tests/unit/test_sheet_catalog_preview.py -q
  uv run pytest tests/unit/test_sheet_catalog_expressions.py -q
  uv run ruff check .
  ```

- [ ] **步骤 8：记录并提交。** changelog 记录“预览行与 XLSX 应用数字格式码、摘要纳入格式宽度且无格式模板摘要不变”；commit message：`在预览摘要与导出链路贯通数字格式码`。

## 任务 3：字段浏览器格式入口

**文件：**

- 新增：`web/src/components/sheet-catalog/formatCode.ts`
- 新增：`web/src/components/sheet-catalog/formatCode.test.ts`
- 修改：`web/src/components/sheet-catalog/FieldBrowser.vue`
- 修改：`web/src/i18n/locales/zh-CN/extensions.ts`
- 修改：`web/src/i18n/locales/en-US/extensions.ts`
- 修改：`web/tests/e2e/fixtures/sheetCatalog.ts`
- 修改：`web/tests/e2e/sheet-catalog.spec.ts`
- 修改：`changelog.md`

**接口：**

- `NUMBER_FORMAT_WIDTHS: readonly number[] = [2, 3, 4, 5, 6]`；`STRIP_ZEROS_WIDTH = 0`。
- `applyNumberFormat(reference: string, width: number): string`：把 `{sheet.number}` 变成 `{sheet.number:0000}`；`width === 0` 得到 `{sheet.number:0}`；`width` 非 1..16 的整数或 `reference` 不以 `}` 结尾时抛出 `Error`（仅开发期护栏，UI 不会触发）。
- 新 i18n 键（两语言各一组，键集合必须一致，`npm run check:i18n` 会校验）：`extensions.sheetCatalog.fieldFormatButton`、`fieldFormatMenuLabel`、`fieldFormatStripZeros`、`fieldFormatPad`（带 `{width}` 占位）。`fieldSyntaxHint` 文案追加格式码说明，覆盖纯文本输入路径。
- **可访问名约束：** 条目按钮名不得包含 `sheet.number` 之类的字段引用文本（用 `fieldFormatButton` 的短文案，如“格式”/“Number format”），否则既有 `getByRole("button", { name: /sheet\.number/ })` 严格模式定位器会因多个匹配而失败。

- [ ] **步骤 1：写纯函数红灯。** 新建 `web/src/components/sheet-catalog/formatCode.test.ts`（Vitest 只收 `src/**/*.test.ts`，node 环境，不加载 SFC）：

  ```ts
  import {describe, expect, it} from "vitest";
  import {applyNumberFormat, NUMBER_FORMAT_WIDTHS} from "./formatCode";

  describe("applyNumberFormat", () => {
    it("按 0 的个数拼接补零格式码", () => {
      expect(applyNumberFormat("{sheet.number}", 4)).toBe("{sheet.number:0000}");
    });

    it("宽度 0 生成去前导零格式码", () => {
      expect(applyNumberFormat("{sheet.number}", 0)).toBe("{sheet.number:0}");
    });

    it("方括号引用同样可附加格式码", () => {
      expect(applyNumberFormat('{sheet["专业:代码"]}', 2)).toBe('{sheet["专业:代码"]:00}');
    });

    it("拒绝越界宽度与非完整引用", () => {
      expect(() => applyNumberFormat("{sheet.number}", 17)).toThrow();
      expect(() => applyNumberFormat("{sheet.number}", -1)).toThrow();
      expect(() => applyNumberFormat("{sheet.number", 4)).toThrow();
    });

    it("可选宽度集合在 1..16 内且不含 1（去零由专门入口承担）", () => {
      expect(NUMBER_FORMAT_WIDTHS).toEqual([2, 3, 4, 5, 6]);
    });
  });
  ```

- [ ] **步骤 2：跑红灯。**

  ```powershell
  npm --prefix web run test:unit -- formatCode
  ```

- [ ] **步骤 3：实现 `formatCode.ts`。**

  ```ts
  /** 图纸目录字段引用的数字格式码（SPEC-DM-012 §5.4）：宽度 = 0 的个数。 */
  export const NUMBER_FORMAT_WIDTHS = [2, 3, 4, 5, 6] as const;
  export const STRIP_ZEROS_WIDTH = 0;

  export function applyNumberFormat(reference: string, width: number): string {
    if (!Number.isInteger(width) || width < STRIP_ZEROS_WIDTH || width > 16) {
      throw new Error(`非法数字格式码宽度：${width}`);
    }
    if (!reference.endsWith("}")) {
      throw new Error(`字段引用未闭合：${reference}`);
    }
    return `${reference.slice(0, -1)}:${"0".repeat(Math.max(width, 1))}}`;
  }
  ```

  `width === 0` 时重复一次 `0`，因此去零入口产出 `:0`。

- [ ] **步骤 4：跑绿灯。**

  ```powershell
  npm --prefix web run test:unit -- formatCode
  ```

- [ ] **步骤 5：写 E2E 红灯。** 在 `web/tests/e2e/sheet-catalog.spec.ts` 追加两个用例，标题必须含“数字格式码”四字（供步骤 6/9 的 `--grep` 选中），例如 `test("数字格式码入口把图号补零到 4 位", ...)` 与 `test("数字格式码入口可去掉前导零", ...)`。用例内容：打开图纸目录 → 在字段浏览器中定位 `sheet.number` 条目所在行 → 点击该行格式入口 → 选择“补零到 4 位” → 断言表达式输入框出现 `{sheet.number:0000}`、预览单元格出现 `0001`；第二个用例选“去前导零”并断言得到 `1`（夹具由 `pad3` 生成图号，首张为 `001`，行内容可在文件内既有断言里核对）。定位器要求：格式入口按钮按 `fieldFormatButton` 文案定位，字段条目按既有 `getByRole("button", { name: /sheet\.number/ })` 定位，二者可访问名不重叠，避免严格模式多重匹配。

  同时给 `web/tests/e2e/fixtures/sheetCatalog.ts` 的格式码支持写红灯断言（fixture 的 `evaluateRow` 目前会把 `number:0000` 当成字段名，导致预览出现 `SHEET_CATALOG_FIELD_UNDEFINED` 而不是 `0001`）。

- [ ] **步骤 6：跑红灯。**

  ```powershell
  npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --grep "数字格式码" --workers=1 --retries=0
  ```

  预期：找不到格式入口按钮（定位器超时），因为 `FieldBrowser.vue` 尚未渲染该控件；即使绕过 UI 直接写入表达式，夹具的 `evaluateRow` 也会把 `number:0000` 当成字段名而报 `SHEET_CATALOG_FIELD_UNDEFINED`。

- [ ] **步骤 7：实现 fixture 格式码求值。** 把 `evaluateRow` 与校验循环中的字段正则同时改为捕获可选格式码，并让缺值判定继续使用**原始值**：

  ```ts
  const fieldRe = /\{(sheetset|sheet)(?:\.([^{}:]+?)|\["((?:[^"\\]|\\.)*)"\])(?::(0{1,16}))?\}/g;
  const formatWidth = match[4]?.length ?? null;
  // …取值逻辑不变，取到原始字符串 value…
  result += formatValue(value, formatWidth);
  ```

  ```ts
  // 与 Python format_value 同语义（SPEC-DM-012 §5.4），仅测试夹具使用
  function formatValue(value: string, width: number | null): string {
    if (width === null || value === "" || !/^[0-9]+$/.test(value)) return value;
    return (value.replace(/^0+/, "") || "0").padStart(width, "0");
  }
  ```

  校验循环只需从同一个正则读取 `match[2]`（点号名不含 `:`），`emptyCount` 仍按原始值统计，因此 `VALUE_MISSING` 警告行为不变。

- [ ] **步骤 8：实现字段浏览器入口与文案。** `FieldBrowser.vue` 在每个字段条目内新增格式菜单（原生按钮 + 现有菜单组件，不引入新依赖）：条目选项为“去前导零”和 `fieldFormatPad`（2/3/4/5/6 位，遍历 `NUMBER_FORMAT_WIDTHS`）；点击后调用 `applyNumberFormat(entry.reference, width)` 并把结果交给既有 `insertReference`（光标协议、`caretRequest` 与列签名逻辑不改）。格式入口与其菜单选项的可访问名**不得包含字段引用文本**（如 `sheet.number`）：既有用例用 `getByRole("button", { name: /sheet\.number/ })` 在“字段浏览器”区域内作严格模式定位（`sheet-catalog.spec.ts` 第 78 行等），区域内多一个匹配就会变红。`zh-CN`/`en-US` 两份 `extensions.ts` 同步新增四个键并更新 `fieldSyntaxHint`（中文示例 `{sheet.number:0000} → 0001`、`{sheet.number:0} → 1`）。

- [ ] **步骤 9：跑绿与前端门禁。**

  ```powershell
  npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --grep "数字格式码" --workers=1 --retries=0
  npm --prefix web run check:i18n
  npm --prefix web run build
  ```

- [ ] **步骤 10：聚焦回归。** 字段浏览器是共享控件，需覆盖导航与既有目录用例：

  ```powershell
  npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts tests/e2e/extensions-navigation.spec.ts --workers=1 --retries=0
  npm --prefix web run test:unit
  ```

- [ ] **步骤 11：记录并提交。** changelog 记录“字段浏览器新增格式入口，可插入 `:0`/`:0000` 等格式码”；commit message：`在字段浏览器提供图号格式码入口`。

## 任务 4：G8 证据、索引与全量回归

**文件：**

- 修改：`web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- 新增证据：`docs/dst-manager/specs/assets/SPEC-DM-012/production/`（格式入口浅/深主题与 200% 缩放截图）
- 修改：`docs/dst-manager/README.md`
- 修改：`.planning/plans/dst-manager/README.md`
- 修改：`.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md`（MEMO-DM-028，G9 真实桌面/Excel 验收清单）
- 修改：`changelog.md`

- [ ] **步骤 1：补 G8 视觉与可访问性证据。** 在 `sheet-catalog-visual-evidence.spec.ts` 追加用例：打开格式菜单后的 1440×1000 浅色与 900×700 深色截图（沿用文件内 `screenshotPath`/附件与 `PRODUCTION_EVIDENCE_DIR` 复制约定，命名如 `g8-format-menu-light-1440x1000.png`），断言菜单在视口内、无整页横向溢出、Tab 可到达格式按钮、菜单可用键盘 Esc 关闭；200% 缩放下格式入口不被遮挡。

  ```powershell
  npm --prefix web run test:e2e -- tests/e2e/sheet-catalog-visual-evidence.spec.ts --workers=1 --retries=0
  ```

  把附件截图复制到 `docs/dst-manager/specs/assets/SPEC-DM-012/production/`，并在 SPEC-DM-012 §16 记录“G3/G4 未重开、G8 已复核”的结论与这次证据文件名。

- [ ] **步骤 2：追加 G9 真实验收项。** 在 `.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md`（MEMO-DM-028）中新增一条并标记待用户执行：导出 XLSX 后确认补零图号是文本单元格（如 `0001`），且未使用格式码的模板导出结果与升级前一致。

- [ ] **步骤 3：核对并推进索引状态。** `docs/dst-manager/README.md` 的“研究与分析”小节与 `.planning/plans/dst-manager/README.md` 的 PLAN-DM-026 条目已在文档批次加入（状态 `proposed`）；实施完成后只需把 PLAN-DM-026 条目状态改为 `active`/`completed` 并补一句实际验证结论，不重复新增链接。

- [ ] **步骤 4：全量回归。**

  ```powershell
  $env:UV_LINK_MODE = "copy"
  uv sync --dev
  uv run ruff check .
  uv run pytest -q
  uv lock --check
  npm --prefix web run test:unit
  npm --prefix web run build
  npm --prefix web run test:e2e
  ```

  真实 AutoCAD 系统测试不属本计划范围（本次不触碰 SCR、插件或布局重建），无需执行 `tests/system_autocad`。

- [ ] **步骤 5：记录并提交。** changelog 记录“门禁证据、索引与全量回归结论”；只暂存本任务文件（含新截图），commit message：`收口图纸目录数字格式码门禁与索引`。

## 风险与回退

- **`00123` + `:0000` 的规范化语义**：若用户期望 `00123`，属预期外；SPEC §5.4 已把“先归一化再补宽”写死并有逐行测试。回退方式是把 `format_value` 换回 `left_strip + zfill` 语义并同步改 §5.4 与测试，但需重新评审，不属实现期自由裁量。
- **前端把格式做成列级下拉**：会重新引入 `0RQ-01` 类错误。SPEC §7.2 区域 3 明确不提供列级控件；评审时以此为准。
- **夹具与后端语义漂移**：`web/tests/e2e/fixtures/sheetCatalog.ts` 是第二实现。E2E 必须同时覆盖 `0001`（补零）与 `1`（去零）两个方向（夹具首张图号为 `001`），避免夹具误实现被忽略。
- **误用 `zfill`**：会产生“幂等失败”和“去零失效”两类静默错误；步骤 6 的语义表已把 `00123`、`01`+宽度 1 两个边界固定下来。
- **既有模板摘要变化**：若步骤 3 意外改动了无格式 token 形态，`test_preview_digest_uses_canonical_json_with_fixed_keys_and_compact_separators` 会立即失败；该测试不可改写以“适配”实现。
- **G4/G8 判定分歧**：格式入口只影响字段条目内部，不改 5 轨道布局与首屏密度；若用户认为布局已变，按 SPEC §16 由用户裁决是否重开 G4，实现方不得自行宣称通过。

## 完成标准

- SPEC-DM-012 §5.1～§5.4 的语法、语义、错误定位全部由自动测试覆盖，§5.4 表格逐行通过。
- 未使用格式码的模板 `preview_digest` 与本次改动前逐字节一致；使用格式码时摘要随宽度变化。
- 缺值、非纯数字、全角数字、含空格值的行为与 SPEC 一致：不伪造、不警告、不 trim、不截断。
- 前端用户可在字段浏览器一键插入 `:0` 与 `:0000` 等格式码，插入后可立即在预览看到 `0001`；两语言文案齐全，`check:i18n` 与 `npm run build` 通过。
- `uv run ruff check .`、`uv run pytest -q`、`uv lock --check`、`npm --prefix web run test:e2e` 全绿；无新增错误码、无迁移、无 API 字段变化。
- 文档与索引一致：SPEC-DM-012、RES-DM-001、PLAN-DM-026、两份 README 与 `changelog.md` 互相链接且状态准确。

## 实际验证

（执行完成后填写：每条命令的实际输出要点、跳过的检查及原因、G8 证据文件名与 G9 待用户执行项。）
