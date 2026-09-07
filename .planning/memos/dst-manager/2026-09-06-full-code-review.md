# 全仓静态审查备忘（dst-manager v0.3.3）

日期：2026-09-06。任务：全仓库代码审查（范围 = 后端 `src/` 四层 + `tests/` 八域 + `web/` 前端 + C# 插件 + 打包/迁移/脚本 + 文档治理与 git 卫生）。
基准：`ARCH-DM-001`（DST/发布安全基线）与 `AGENTS.md`（分层、容量、发布事务、红线）。
审查方式：4 个并行 reviewer 子代理逐文件只读审查 + 主管跨切面分析（依赖方向/容量/死代码/git 卫生/敏感扫描）；所有 P1 级关键结论均回源复核。

**总体结论：未发现 P0（阻断合并）级红线违反。** 核心安全基线（DST→XML DOM→DST 受控流、未知节点/顺序/tail 保真、永久 before 快照＋发布日志＋整批回滚、SCR 注入防护、Handle 校验、127.0.0.1 绑定）实现质量高且测试覆盖广。存在 5 项重要（P1）需在发布前处理，集中在「发布 journal 耐久与恢复容错」「Worker 异常逃逸」「跨层不变量/契约不一致」。

---

## 验证基线（运行证据，全绿）

- `uv run ruff check .` —— 通过。
- `uv run pytest` —— 收集 700 个：**628 passed / 72 skipped / 0 failed**（skipped 均为真实 AutoCAD 系统测试与真实环境用例，未启用 `DST_MANAGER_RUN_AUTOCAD`；含发布器回滚、acsm repair、事务恢复、CAD 并行）。仅 SQLite datetime 适配器弃用告警噪音（Python 3.12）。
- `web` 生产构建 —— 通过（`check:api` OpenAPI 契约一致性校验 + alembic 全新库迁移 + `vue-tsc -b` + `vite build`，EXIT=0）。
- 跨切面正向结论：domain 层无任何 infra/接口/FastAPI/SQLAlchemy/lxml/进程导入（依赖方向干净、无环）；无 TODO/FIXME 遗留；`.gitignore` 覆盖全面；无未跟踪文件；敏感扫描仅命中误报（package-lock integrity、codec 256 映射表、黄金样本哈希）。

---

## 重要（P1，建议发布前修复）

### P1-1 发布 journal 无 fsync 耐久保障，且启动恢复对损坏 journal 无容错（infra）
- 证据：`infrastructure/filesystem/publisher.py:775-776` `_write_journal` 用 `temp.write_text()` + `os.replace()`，写前无 `flush/fsync`；`:339-345` `_archive_journal` 同理（manifest 是 DB finalize 可见性闸门）；`:812` `recover()` 对 journal 直接 `json.loads(path.read_text())` 无 try/except。
- 影响链：断电/进程被杀在写盘窗口 → journal 半截 → 下次启动 `application/service.py:64` `publisher.recover` 抛未捕获 `JSONDecodeError` → **服务整体无法启动**，同 workspace 其余待恢复事务一并阻断。
- 违反/接近红线：AGENTS「正式写入必须保留…发布日志和可回滚事务流程」「中途故障和启动恢复」。仓库其他持久化（`drafts.py:119`、`sheet_preferences.py`）均已 fsync，journal 是唯一权威记录反而没有。
- 建议：`_write_journal`/`_archive_journal` 在 `os.replace` 前 `flush()+os.fsync()`；`recover()` 对每个 journal 独立 try/except，坏日志隔离（`.corrupt-<ts>`）后继续处理其余；补「截断 journal 后启动恢复不中断」回归。

### P1-2 CAD Worker 领取后准备阶段异常无保护，进程退出致任务队列停摆（interfaces）
- 证据：`interfaces/cli.py:88-96` 轮询 `service.run_next_job()` 无 try/except；`application/service.py:104-121` 在 `claim_next_job` 之后执行 `get_workspace()`（DST 被删→`DST_NOT_FOUND`、DST 损坏→`AcsmValidationError`、网络盘离线→`OSError`）与 `_capability()`，全在 `CadJobRunner.run()` 内部兜底之外。
- 影响：异常一路冲出杀死 Worker 进程；桌面壳不重启已退出 Worker；已领取任务滞留 STAGING 至下次应用启动，后续排队任务无人认领。
- 建议：在 `run_next_job` 的 claim+prepare 外层统一捕获 `ApplicationError`/`AcsmValidationError`/`OSError`，落 `FAILED`/`NEEDS_REVIEW` 终态并 `continue`；补「队列中存在 DST 已被删除的工作区」回归。

### P1-3「空子集拒绝」不变量在 XML 导入写主 DST 路径缺校验（domain/application 跨层）
- 证据：`application/xml_io.py:124-125` 导入写回仅把关 `document.validate()`；`AcsmDocument.validate()`（`document.py:876-913`）只检查 Sheet 布局/Number/Title/Handle 与重复/非法 ID，**不检查 AcSmSubset 是否为空**；contract/XSD 亦无此约束。对比 domain derive（`editing.py:268/407/598`）显式拒绝空子集。
- 影响：外部工具产出的含空子集 XML 可经 `export_xml_to_dst` 写入主 DST，之后该工作区所有结构性预览被 `EMPTY_SUBSET` 永久阻塞——同一不变量在不同写入口行为不一致。
- 建议：`AcsmDocument.validate()` 对每个 AcSmSubset 增加等价 `EMPTY_SUBSET` ERROR 检查（或 XML 导入入口显式校验）＋最小 XML fixture 回归。

### P1-4 前后端错误响应契约不匹配（web + interfaces）
- **422 解析成 `[object Object]`**：`web/src/api/client.ts:19` 读 `body.detail`；后端仅注册 `ApplicationError`（`{code,message}`）与 `AcsmValidationError`（422 `{code,message}`），而 Pydantic 字段校验器抛的 422 走 FastAPI 默认 `{"detail":[{loc,msg,type},...]}`（`api.py:66-77` 无 `RequestValidationError` 处理器），`client.ts` 对数组 `String()` 强转成 `[object Object]`。子集标题含 `/`、非法布局名、非 `.dwg/.dwt` 模板即可稳定触发。
- **`ApiError.fields` 契约后端从未兑现**：`client.ts:6` + 消费点 `useSheetEditor.ts:232`/`usePropertiesWorkspace.ts:218-225`/`App.vue:172`，后端所有错误响应均不含 `fields` → 行内字段错误逻辑永远为空。
- 建议：后端统一 422 错误体为 `{code, message, fields?}` + 注册 `RequestValidationError` 处理器；前端 `client.ts` 识别 FastAPI 422 取 `detail[0].msg`（去 `"Value error, "` 前缀）；或明确放弃 `fields` 行内错误。

### P1-5 容量软上限超限且未排期拆分（cross-cutting）
- 7 个文件超 500 行：`acsm_xml/document.py` 996、`filesystem/publisher.py` 930、`application/cad_job.py` 884、`persistence/database.py` 761、`domain/editing.py` 677、`planning.py` 515、`responses.py` 511。
- 5 个类公共方法超 15：`AcsmDocument` 44、`RecoverablePublisher` 32、`Database` 25、`CadJobRunner` 22、`OpenRequest` 23。
- `CadJobRunner` 单类承载 6 类职责；`.planning`/`changelog` 无这些文件的拆分登记，违反 AGENTS「不得默认继续追加」。仓库已用 service.py（1984→269 行）示范拆分方向。
- 建议：按 AGENTS 契约渐进拆分（结构工厂/语义校验/投影、回滚恢复/提交原语、job 状态/单组执行/staged DOM 组装/journal 回调），保持公共接口/错误码/序列化不变、以既有测试兜底。

---

## 一般（P2）

| # | 问题 | 位置 |
|---|---|---|
| P2-1 | SSE 终态集合缺 `NEEDS_REVIEW`：仅 4 态结束流，领域 `TERMINAL_JOB_STATUSES` 含 `NEEDS_REVIEW`，该状态任务被服务端无限轮询（被前端自行 close 遮蔽） | `interfaces/api.py:245` vs `persistence/database.py:174` |
| P2-2 | `NEEDS_REVIEW` 终态仍渲染「安全重试」按钮，点击必失败（`retryJob` 已禁止） | `web/src/components/JobStatusPanel.vue:8` vs `useJobMonitor.ts:43` |
| P2-3 | 逐文件状态在整批提交前即置 `SUCCEEDED`，发布前失败时 job=FAILED 但文件行=SUCCEEDED，审计摘要与终态矛盾 | `application/cad_job.py:673-680/757` |
| P2-4 | 领域校验三处重复且有细节分歧：危险字符正则 3 份、`normalize_property_name` 双份（0x7F 处理不一致）、`validate_xml_text` 双份；`planning.py:37/58/74` 死代码与现行 derive 并存 | `domain/{editing,planning,text_validation}.py` |
| P2-5 | 事务 finalize 回调 5 份复制 + `_committed_result_hash` 双份，恢复语义易漂移 | `editing/cad_job/repair/revisions/xml_io` |
| P2-6 | repair/xml_io 发布后硬编码写元数据 `"2020"`，与 DB `default_cad_version` 来源不一致 | `application/repair.py:197`、`application/xml_io.py:238` |
| P2-7 | infra 遗留 `apply_structural_commands`（`update_sheet` 允许写 `number`、`delete_empty_subset`）与 ADR/SPEC 拒绝语义不一致，构成潜在绕过原语（当前仅测试可达） | `infrastructure/acsm_xml/document.py:254-280` |
| P2-8 | DST codec 用 lxml **默认解析器**（`codec.py:40/47` `etree.fromstring`），未复用 `document.py:151` 的 `XMLParser(resolve_entities=False, no_network=True)`——codec 是外部输入第一道解析点 | `infrastructure/dst_codec/codec.py` |
| P2-9 | SQLite 引擎未设 `busy_timeout`/写冲突退避，Web 线程与 Worker 共用 engine 下并发写缺显式策略 | `infrastructure/persistence/database.py:210-218` |
| P2-10 | `recover()` legacy 回滚分支（`:887-898`）覆盖/删除前不做目标身份/归属校验，可能误删外部新文件（仅 MVP 遗留 journal 可达） | `infrastructure/filesystem/publisher.py` |
| P2-11 | `setup.bat` 将注册表/目录扫描路径经 `echo` 直写 `.env`，未转义 `&`/`\|`/`<`/`>`/`!`（自定义安装目录时低危） | `scripts/setup.bat` |
| P2-12 | `operation_log.py:8` 路径拼接无 operation_id 白名单，追加写无 flush（当前 id 全为 uuid，无注入面） | `infrastructure/operation_log.py` |

---

## 建议（P3，可排期）

- **错误契约收敛**：后端统一 422 为 `{code,message,fields?}` + 注册 `RequestValidationError` 处理器；前端 `client.ts` 识别 FastAPI 422 取 `detail[0].msg`；`responses.py` 显式必填 `actions/blocking_issues`，去掉 `contracts.ts` 交叉类型补丁。
- **`api.py` 模块级 `app=create_app()` 副作用**：桌面壳 `shell.py:265` 导入 `.api` 与 `run_desktop` 同一进程做两次迁移/恢复/建连。
- **FastAPI `version="0.3.0"` 硬编码** 与 `pyproject.toml` 0.3.3 脱节，未纳入 release 门禁。
- **`shell.py:278-280` uvicorn 就绪等待无超时**（bind 失败会永久挂起）。
- **`build_release.ps1:66-68`** 用 `-Recurse -Force` 合并导致旧插件 DLL 残留，应先删目标目录。
- **domain 层使用 `Path.resolve()/.expanduser()`** 有环境副作用，建议在文档标注为既定边界或注入规范化函数。
- **CAD 快照名沿用用户原文件名**（`cad_job.py:253` `f"{sha}-{idx}-{source.name}"`），跨层依赖 worker 的 SCR 转义；建议改纯 ASCII 安全命名。
- **`service.py:270-273` 死方法 `_write_workspace_file`**、`_issue` 延迟导入可收敛。
- **`repair.py:227` 补全节点用裸标签名**，与 `document.py` 命名空间处理不一致（当前 AcSm 样本无命名空间，仅潜在）。
- **`drafts.py:144` 遗留 `.lock` 文件不清理**；**`JobStatusPanel.progress??100`** 对失败态也回退 100%；**`WelcomeView.vue`** 无壳手输路径未校验 `.dst` 扩展名；**C# `LayoutRenameCommand.cs:94`** 尾随空白敏感。

---

## 未提交改动评估（12 文件，Windows 发布打包 + 用户环境初始化）

- `runtime.py` + `packaging/entry.py` + `dst-manager.spec`（`console=False` + `redirect_frozen_stdio` 无窗启动重定向日志）实现合理：重定向仅在标准流不可用时生效、desktop/worker 分文件、失败静默放弃不阻断启动，单测覆盖充分（test_runtime 8 项）。与 ARCH-DM-002 §3.1/§3.5 一致。
- `setup.bat` 见 P2-11；`release.ps1:6` 要求工作区干净，**当前有未提交改动，发布前需先提交**。
- **记录缺口（非代码缺陷）**：changelog 与 PLAN-DM-014 明示「exe 冒烟、release.ps1 冒烟、端到端 release 演练」未执行，发布前需补：解压 zip → 双击 exe 无黑窗、空库自动迁移、`dst-manager.exe doctor` 落盘、`%LOCALAPPDATA%\dst-manager\logs\` 生成 worker.log/dst-manager.log。

---

## 建议优先修复顺序（发布前）

1. **P1-1** journal fsync + recover 容错（数据安全，最高优先）
2. **P1-2** Worker 领取后异常兜底（可靠性）
3. **P1-4** 前后端错误契约统一（直接影响用户体验）
4. **P1-3** XML 导入空子集校验（一致性/防绕过）
5. **P1-5** 容量拆分排期 + **P2-1/P2-2** SSE 终态与 UI 对齐

## 待跟进事项

- [ ] 决定 P1 各项是否转为实施计划（PLAN）与拆分任务。
- [ ] 补 P1-3 最小 XML（含空 AcSmSubset）导入回归用例。
- [ ] 补 P1-1 截断 journal 后启动恢复回归用例。
- [ ] 发布前完成 PLAN-DM-014 记录缺口：exe 冒烟 / release.ps1 冒烟 / 端到端 release 演练，并先提交当前工作区改动。
- [ ] 复核 FastAPI 版本号与发布版本单一来源。
- [ ] （无窗日志专项）Task 11 Step 7 真实构建冒烟增加两项：①双击无黑窗且 `logs/dst-manager.log`/`worker.log`/`doctor-last.json` 按预期产生；②从控制台运行 `dst-manager.exe worker`/`--help` 验证输出去向，据实修订文档断言（P1-无窗）。
- [ ] （无窗日志专项）doctor 能力探测/初始化异常时错误信息也落盘 `doctor-last.json`（P2-无窗-1）。

---

## 附录 A：console=False 无窗日志重定向专项审查（同日追加）

来源：用户指定对未提交 12 文件（Windows 发布打包 + 用户环境初始化）专项审查，重点为“打包 exe 隐藏控制台并输出日志文件”实现。证据：源码/diff/文档全读 + PyInstaller windowed stdio 行为外部查证；pytest 全量通过（628 passed / 72 skipped / 0 failed）。**无数据/发布安全红线问题**；存在 1 项 P1（行为与文档断言不一致）与若干 P2/P3。

### 专项 P1（发布前）

**「从控制台手工运行时输出保持可见」的断言在 frozen 态不成立**

- 证据链：`runtime.py`/`entry.py`/`shell.py:211` 注释、`changelog.md`、ARCH-DM-002 §3.5 均声明 windowed exe 从控制台手工运行时标准流可用；PyInstaller `console=False` 实为 GUI 子系统，bootloader 恒把 `sys.stdout`/`stderr` 替换为 `NullWriter`（官方《Common Issues and Pitfalls》+ 实测 `argparse_gui.exe -V` 无输出）。
- 推论：frozen 态 `_stdio_usable()` 对 desktop/worker 恒 False → 总是重定向；「可用流不替换」分支与相关注释成死逻辑；`test_redirect_frozen_stdio_keeps_usable_stream` 只覆盖开发态，真实 frozen 永不命中。
- 影响：功能兜底成立（日志仍进 `worker.log`/`dst-manager.log`，可观察性目标达成）；但 `--help`/`serve`/`open` 等非映射命令无终端时输出全部丢失且无文件兜底（doctor 有 `doctor-last.json` 不受影响）。
- 建议：Step 7 真实冒烟专项验证后据实修订 §3.5 与各注释；如需保留控制台排障可在入口尝试 `AttachConsole(ATTACH_PARENT_PROCESS)`，MVP 建议直接修正文档；泛化兜底（未知命令回退 `dst-manager.log`）改前需修订文档契约。

### 专项 P2

1. **doctor 异常零反馈**：`cli.py` doctor 先 `capabilities()` 后落盘，配置损坏/DB 异常时异常只进 NullWriter、`doctor-last.json` 不会写出 → 无终端下用户零反馈。建议 `try/except` 后把错误同样落盘。
2. **测试缺口**：`redirect_frozen_stdio` 的 OSError 静默分支无测试；`entry.py` 仅静态文本断言，无“重定向后 echo 真实落盘”行为级测试。
3. **验证口径不一致**：PLAN Task 11 Step 6 记「628 passed / 4 skipped」vs 当前全量「700 收集 / 628 passed / 72 skipped」——建议 PLAN 补记具体 pytest 命令与范围保证可复现。
4. **worker.log 并发 append**：多 worker 实例无锁追加同文件行会交错（MVP 单 Worker 低危，文档注明即可）。

### 专项 P3（简列）

- `_stdio_usable` 依赖 `NullWriter` 类名字符串匹配，脆弱；可改为“fileno 有效”单一判据。
- 两个坏流赋同一文件对象（行缓冲）——现状可，如需区分通道可分别打开。
- 日志不轮转/不清理已明示为 §3.5 设计决策，长期运行会持续增长（排期关注）。

### 专项已确认正确项（无问题）

entry 先重定向后导入（含 uvicorn 时序，有静态守护）；desktop/worker 分文件 + 启动分隔行 + UTF-8 追加 + 行缓冲；坏流才替换三态判断；doctor frozen 落盘/开发态不落盘（有测试）；`console=False` + `disable_windowed_traceback=False`（崩溃弹框可观察）；`_spawn_worker` 不传 stdio 由子进程自身 entry 兜底；数据/日志同根 `%LOCALAPPDATA%\dst-manager\` 不被 zip 更新覆盖；worker 摘要不含 payload/commands/客户 敏感字段（有断言）。
