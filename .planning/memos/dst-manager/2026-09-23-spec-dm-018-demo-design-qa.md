# SPEC-DM-018 交互 Demo 设计 QA（2026-09-23）

## 范围与方法

以 [SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md) 为行为依据，并将既有 [SPEC-DM-016 欢迎页截图](../../../docs/dst-manager/mockups/SPEC-DM-016-welcome-demo-light-900x768.png) 与新 Demo 同视口并列目视对照。通过仅绑定 `127.0.0.1` 的本地静态服务，在应用内浏览器逐步操作；不连接 API，不读写 DST/DWG，也不生成真实 XLSX。

## 已检查

- 欢迎页到四阶段向导、标准详情直达项目信息、跨标准已有草稿先确认、项目目录名独立于「工程名称」：通过。
- 新组复制前一创建组全部输入并聚焦图名、重名提示、选择多组批量修改及「值不相同」提示：通过。
- 预览一组一行；不编号 `00` 不占号，后续 `01-03` / `04-05`；尾序号范围、文件名、动态属性首值及「…」逐张模态：通过。模态关闭后焦点返回触发按钮。
- 编号设置变化使旧预览失效；多张不编号且关闭标题尾序号时，重复布局名阻断创建：通过。
- XLSX 双可见表结构、模拟错误导入保持草稿、有效导入前全量覆盖确认、导入后预览失效：通过。Demo 明示不解析或生成实际工作簿。
- 900×768 浅色与深色：页面 `scrollWidth = innerWidth = 900`，两张宽表仅在各自容器内横向滚动；浏览器错误日志为空。与既有 Demo 保持相同的蓝色主动作、卡片、浅深主题语义令牌。
- 图纸组「操作」列补充复验：对照图纸目录插件生产截图与 `ColumnEditor.vue`，`↑` / `↓` / `✕` 按钮为 32×32、间距 4px；首末行禁用与逐组可访问名称保留，上移后行顺序正确。900×768 深色下整页无横向溢出，操作列可在表格内部横滚到达。
- 模拟创建展示任务中状态并进入模拟工作区；明确不创建实际项目文件。

## 验证与边界

- `node --test tests/demo/*.test.cjs`：28 通过，其中 SPEC-DM-018 新增 5 项。
- `uv run ruff check .`：通过。
- `uv run pytest -q tests/unit/test_unnumbered_subsets.py tests/unit/test_standard_naming.py tests/unit/test_standard_rules.py`：56 通过。
- `uv run pytest -q`：2 项失败，均为未改动的 `tests/unit/test_setup_bat.py` 中中文 `stdout` 文案断言；重复单独运行仍失败，`cmd /c chcp` 为 936。本轮不修改打包脚本或相关测试。
- 当前是独立设计原型，草稿仅保留在**当前页面**，刷新不恢复；数据、标准资产、校验与创建执行均为模拟。真实产品须按规范由后端预览和发布事务提供权威结果。

结论：Demo 可用于讨论 PLAN-DM-036 UI，尚未构成 SPEC-DM-018 设计定稿或产品实施验收。
