# PLAN-DM-009 worktree 代码审查元数据

> 用途：为本分支（`feature/dm009-dst-schema-validation-and-repair`）后续代码审查提供
> 分支/提交/变更范围/验证记录与审查建议。实现细节见计划与规范：
> `.planning/plans/dst-manager/PLAN-DM-009-dst-schema-validation-and-repair.md`、
> `docs/dst-manager/specs/SPEC-DM-004-dst-schema-validation-and-repair.md`。

## 1. 分支与工作区

| 项 | 值 |
| --- | --- |
| 分支 | `feature/dm009-dst-schema-validation-and-repair` |
| 基准 | `main`（`github/main` 落后本地 `main` 两笔：`ac0f7e3` 固化契约、`47a4fa5` 拆分计划） |
| worktree | `C:/Users/sonic/autocad-sheetset/.worktrees/dm009-dst-schema-validation-and-repair` |
| 提交 | 7 笔（`main..HEAD`，无未提交文件） |

## 2. 提交清单

| # | 提交 | 说明 | 文件（数量统计） |
| --- | --- | --- | --- |
| 1 | `42e930f` 建立 AcSm contract 与标准 schema | 版本化 contract registry + 修复后 XSD 边界 | contract.py、schema/acsm-v1.xsd、test_acsm_contract.py（4 文件，+532） |
| 2 | `1fe0a4a` 实现 DST XML 内存修复报告 | RepairStatus/Action/Report 值对象 + AcsmRepairer | domain/models.py、repair.py、test_acsm_repair.py（4 文件，+604） |
| 3 | `c66ca1e` 对齐新增 Sheet 的 AcSm 对象契约 | contract-driven 工厂、validate 合并、load_acsm 雏形 | document.py、test_core.py（3 文件，+248/−14） |
| 4 | `cf1cb24` 统一 DST 加载校验并暴露修复诊断 | 统一 loader、写入门禁、repairs/preview+execute、API/序列化 | service/cad_job/api/serialization/document/models/__init__、tests（11 文件，+583/−45） |
| 5 | `1db838f` 为 DST 修复增加独立发布事务 | 修复修订事务回归 + CAD 暂存 VALID 门禁 | cad_job.py、test_core.py（3 文件，+201/−1） |
| 6 | `bc95248` 补充 DST 修复确认界面 | Web 修复面板、写入门禁、确认流程、e2e | App.vue、style.css、main.spec.ts（4 文件，+109/−4） |
| 7 | `35bbb82` 完成 DST schema 校验与修复交付审查 | 计划标记 completed、SPEC 实施说明、验证记录 | PLAN-DM-009、plans README、SPEC-DM-004、changelog（4 文件，+27/−3） |

## 3. 变更总览

- **领域层（models.py）**：新增 `RepairStatus`/`RepairConfidence`/`RepairAction`/`RepairReport`
  不可变值对象；`SheetSetDocument` 挂载 `repair_report`。
- **基础设施（acsm_xml/）**：`contract.py`（7 类对象必需/固定属性 + `AcSmProp` `vt` 表 +
  父级包含关系）、`schema/acsm-v1.xsd`（XSD 1.0 结构边界，lax 保留未知内容）、
  `repair.py`（深拷贝修复器）、`document.py`（parse→契约扫描→修复→XSD→语义；
  contract-driven 工厂；`load_acsm`/`repair_digest`；`validate()` 合并契约/XSD/语义）。
- **应用层（service.py、cad_job.py）**：统一 `load_acsm`；写入门禁
  （`VALID` 可写 / `REPAIRED` 须先确认修复 / `INVALID_*` 只读）；
  `preview_repair`/`execute_repair` 独立修复修订（锁、暂存、永久 before 快照、
  发布日志、回滚、启动恢复，digest 对生成 ID 掩码保证预览/执行一致）；
  CAD 暂存要求 `VALID`。
- **接口层（api.py、serialization.py）**：`REPAIRED` 报告字段 `dst_validation`、
  `POST /api/workspaces/{id}/repairs/preview` 与 `/repairs/execute`。
- **Web（App.vue、style.css）**：修复面板四状态、确认流程、确认前禁用写入发布。
- **测试**：`test_acsm_contract.py`(12)、`test_acsm_repair.py`(10)、
  `test_acsm_load_entrypoints.py`(6)、test_core 新增（工厂/round-trip/事务/CAD 门禁）、
  test_api 新增（修复 API 全流程）、e2e 新增修复流程用例；`tiny_workspace` 夹具改为契约合规。

## 4. 验证记录

- 后端：`uv run ruff check .` 全绿；`uv run pytest -q` **432 passed / 66 skipped**（退出码 0）；
  `uv lock --check` 通过。
- Web：`npm run build`（vue-tsc + vite）通过；Playwright e2e **19/19** 通过。
- 关键样本证据：黄金样本 `project1_sheetset.xml` 打开 `VALID` 零修复；失败样本
  `sheetset-fail.xml` 231 项确定性内存修复（11 Sheet 缺 clsid、33 值 + 66 Prop 缺 vt、
  11 Bag/11 布局缺固定属性、11 Sheet 缺 SheetViews），原件字节与 mtime 不变、不产生
  `.dst-manager/`；新建 Sheet 子树与黄金契约逐字段一致（见 PLAN-DM-009 交付验证记录）。
- **未运行**：真实 AutoCAD 2016/2020 系统测试与官方 Sheet Manager 显示验收
  （本机未设 `DST_MANAGER_RUN_AUTOCAD=1`，无对应 Core Console/Worker/私有 DWG 样本）。

## 5. 代码审查建议

按提交顺序逐层审查便于理解，重点顺序：

1. **契约权威（42e930f）**：`contract.py` 的固定属性表/`vt` 表与黄金样本的对应关系；
   `acsm-v1.xsd` 采用 XSD 1.0 且“结构边界”较弱的取舍（理由写入模块 docstring：
   lxml 不支持 XSD 1.1 assert，必填子节点不变量交给语义校验器）。
2. **修复器（1fe0a4a）**：`repair.py` 修复顺序、`_classify` 的状态分类边界
   （`INVALID_REPAIR_REQUIRED` vs `INVALID_UNRECOVERABLE`）、不覆盖非空错误值、
   空 `Value` 不补写、报告动作逐项可审计。
3. **DOM 接入（c66ca1e）**：`document.py` 的 `repair=False` 状态语义、
   `clone()` 复制报告、工厂固定字段与黄金顺序（bag→layout→Number→SheetViews→Title）。
4. **应用/接口（cf1cb24、1db838f）**：门禁在 `preview_changes`/`preview_xml`/
   `export_xml_to_dst`/`execute_repair` 的放置；`execute_repair` 与既有
   metadata 发布的异同；digest 掩码实现是否有旁路；CAD 暂存 VALID 门禁位置。
5. **Web（bc95248）**：修复面板文案/状态色、确认前禁用范围、加载代次保护。
6. **收尾（35bbb82）**：SPEC-DM-004 实施说明与计划验证记录。

审查关注点（潜在风险）：

- 修复生成的随机 ID 使报告逐字段不可重现——已通过动作计数/掩码摘要规避，注意
  `repair_digest` 的正则只掩码 `ID="g..."` 属性，若未来出现非标准 ID 值需复核。
- `repair=False`（`AcsmDocument(xml, repair=False)`）目前无调用方，属预留分支。
- 空自定义属性缺 `Value` 保持缺失；缺失 Bag/缺失 Value 未做推断创建（SPEC 允许
  inferred，实现选择不伪造），删除/新增属性仍走既有命令。
- `/repairs/execute` 与普通 metadata 发布共用作业表，`error_code`/终态语义需在
  审查时确认与前序任务一致。