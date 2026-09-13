# 打包守护与 E2E 夹具的已知残留缺口

日期：2026-09-13

状态：待办（未立项；来源 PLAN-DM-025 任务 9 第二轮全分支评审）

关联：`PLAN-DM-025`、`ARCH-DM-006`、`SPEC-DM-011`、`SPEC-DM-012`

## 问题

PLAN-DM-025 任务 9 的第二轮评审（两条只读通道：门禁复算、修复闭环复核）认定下列缺口**不阻塞本计划验收**，但每条都有明确的误伤/漏检/失真路径，故登记为债务而非就地修改。

### 1. frozen 打包守护对合法扩展 fail-closed 误伤（清单键词段）

- 现象：`tests/unit/test_packaging_spec.py` 按**词段**（非字母数字边界 + 驼峰切分）匹配禁用词，`path`/`file`/`module`/`exec` 等词段出现在合法业务键里也会被拒。
- 触发条件：未来扩展的清单键含上述词段但语义与「可执行入口」无关（例如展示用的 `user_profile_path_label`、`source_file_hint`）。
- 影响：拦下**合法**扩展（不会放过非法扩展），红灯信息误导排查方向。
- 修法建议：改为「词段命中 + 值形态判定」双条件，或维护显式白名单键；修时必须同时补一条「合法键带 `path` 词段仍应通过」的绿灯用例。

### 2. `pathex` 的 `os.path.join(...)` 形式未覆盖

- 现象：`pathex` 守卫只按字符串字面量判定，`pathex=[os.path.join("..", "src")]` 一类等价写法既不命中也不报错。
- 影响：属**漏检**（方向是放松而非误伤），可被等价写法绕过。
- 修法建议：对 `pathex` 元素做受限求值（只允许字面量拼接），或直接断言「元素必须是字符串字面量」，让等价写法落到显式报错而非静默通过。

### 3. 属性形式入口（`module.SYMBOL`）不做符号存在性校验

- 现象：`_module_level_binding()` 只校验「名字在目标模块确有模块级定义」，`ast.Attribute` 形态（如 `settings.SHEET_CATALOG_SETTINGS_PROVIDER`）未做符号存在性校验。
- 影响：既有缺口（非 PLAN-DM-025 引入），属性名拼错不会被静态守护发现。
- 修法建议：属性形态解析为 `(模块, 属性名)` 后复用同一条符号存在性检查。

### 4. 夹具 `preview_digest` 的 `+1` 是死表达式

- 现象：`web/tests/e2e/fixtures/sheetCatalog.ts` 的 `preview_digest: \`digest-${state.previewRequests.length + 1}\`` 随后被 route 统一覆写为 `state.lastDigest`，`+1` 永不生效。
- 影响：今日无害；一旦删掉覆写行，摘要会与 `state.lastDigest` 静默失配，产生难归因的 409。
- 修法建议：改为 `state.lastDigest`，或删掉覆写行让该表达式成为唯一来源（二选一，不留两处语义）。

## 完成条件

- 1/2/3 各自补齐红/绿用例（合法键通过 + 等价写法被拒 + 属性拼错被拒）后，可删去对应条目；4 清理为单一来源即可关闭；
- 修改打包守护后必须重跑 `tests/unit/test_packaging_spec.py` 与 `tests/unit/test_sheet_catalog_settings.py`，并复跑受影响的 E2E（`extensions-settings.spec.ts`、`settings-extensions-production-evidence.spec.ts`）。

## 触发重开条件

- 新增扩展清单字段、调整扩展打包方式（PyInstaller `datas`/`pathex`/固定索引），或改动 E2E 夹具摘要逻辑之前，先读本待办再动手。
