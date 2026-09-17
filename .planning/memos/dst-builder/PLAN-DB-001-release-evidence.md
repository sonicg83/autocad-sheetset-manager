---
id: MEMO-DB-001
title: PLAN-DB-001 发布证据备忘（Task 12 收口记录）
scope: dst-builder
type: memo
status: active
created: 2026-09-18
updated: 2026-09-18
related:
  - PLAN-DB-001
  - SPEC-DB-001
---

# PLAN-DB-001 发布证据备忘（Task 12 收口记录）

本备忘如实记录 2026-09-18 Task 12 实际执行的验证、环境受限项与待办人工项。结论先行：**开发闭环完成，正式双版本资格未满足**。SPEC-DB-001 保持 `review`，PLAN-DB-001 保持 `active`，唯一剩余门禁见文末。

## 1. 实际执行的验证（命令与结果）

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| Ruff | `uv run ruff check .` | 通过，0 违规 |
| pytest 全量 | `uv run pytest -q` | **2186 passed / 75 skipped / 0 failed**（skip 均为真实 CAD 显式启用门禁与私有样本门禁） |
| uv.lock | `uv lock --check` | 通过（Resolved 70 packages） |
| Builder 迁移全新升级 | `DST_BUILDER_DATABASE_URL=sqlite:///<临时目录>/builder-fresh.dstb uv run alembic -c builder_alembic.ini upgrade head` | 通过（→ `0001_db001_initial`） |
| Manager 迁移全新升级 | `DST_MANAGER_DATABASE_URL=sqlite:///<临时目录>/manager-fresh.db uv run alembic upgrade head` | 通过（→ `0007_db001_builder_handoff`） |
| Manager Web | `cd web && npm ci && npm run build && npm run test:e2e` | build 通过（含 `check:api`/`check:i18n`/`check:ui`）；e2e **555 passed**（契约漂移修复后独立重跑） |
| Builder Web | `cd builder-web && npm ci && npm run build && npm run test:e2e` | build 通过；**e2e 20 passed**（含真实后端全流程：创建项目→资产→计划确认→构建→交接 mock） |
| 双版本 Builder 插件 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_builder_plugins.ps1` | 通过，0 警告 0 错误（2016/2020 各产出 `DstBuilder.AutoCAD.dll`） |
| Builder EXE | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_builder_release.ps1` | 通过，产出 `dist/releases/dst-builder-v0.3.5-win64.zip`（28.8 MB，2026-09-18 重建，详见附录 A） |

### 1.1 真实 CAD 系统测试（显式启用，本机环境探测可用）

探测结论：本机存在 `C:\Program Files\Autodesk\AutoCAD 2016\accoreconsole.exe` 与 `AutoCAD 2020\accoreconsole.exe`；`plugins/builder/autocad{2016,2020}/DstBuilder.AutoCAD.dll` 已构建；私有样本 `sample/project1/GP-0000 封面.dwg`（85 KB，唯一纸空间布局 `0000 封面`）可用。据此以 `DST_BUILDER_RUN_AUTOCAD=1` + `DST_BUILDER_AUTOCAD_<版本>_CONSOLE/_PLUGIN/_SAMPLE_DWG/_SAMPLE_LAYOUT` 显式启用执行。

| 版本 | 命令 | 结果 |
| --- | --- | --- |
| AutoCAD 2020 | `DST_BUILDER_AUTOCAD_VERSION=2020 uv run pytest tests/builder/system_autocad -q` | **通过**（真实布局导入、布局改名/清理、DWG 保存、Handle 与 SHA-256 校验） |
| AutoCAD 2016 | `DST_BUILDER_AUTOCAD_VERSION=2016 uv run pytest tests/builder/system_autocad -q` | **通过**（同上） |

两版本均使用各自匹配的 Core Console 与插件 DLL，未以一个版本结果推断另一个版本。

**时序澄清（Task 12 终审评审补记）：** 2020 系统测试通过时使用的是**最终重建前**的 DLL；2016 首跑暴露插件缺陷后，经 `build_builder_plugins.ps1` 重建**双版本** DLL，2016 用重建后二进制通过。因两版本共享同一份 `Commands.cs` 源码（缺陷修复在源码层，重建仅重编译同一源码），最终重建后 2020 未复跑系统测试；此点如实登记，如需严格同二进制复验可在人工验证轮补跑 2020。
**SaveDrawing 版本澄清（Task 12 终审评审补记）：** 插件 `SaveDrawing` 改用 `DwgVersion.Current`：产物 DWG 版本随宿主 Core Console（与 `cad_version` 匹配）的原生版本而定；DWG SHA-256 只作发布留痕（§9 provenance），不参与确定性比对（计划冻结比对在计划/修订 JSON 层），故不指定固定 DWG 版本号。

**执行中发现并修复的真实缺陷（Task 7 插件潜伏缺陷，此前真实测试从未具备环境执行）：**

1. **布局导入策略缺陷**：直接 `WblockCloneObjects` 克隆 Layout 对象到目标库布局字典时，源/目标 DWG 的匿名纸空间块（`*Paper_Space0`）同名，`DuplicateRecordCloning.Ignore` 跳过克隆导致两布局共享同一块表记录，AutoCAD 自动补出默认布局（如“布局1”），最终布局集合校验失败（`DSTBUILDER_FINAL_LAYOUT_SET_INVALID`）。修复（`plugins/src/DstBuilder.AutoCAD/Commands.cs`）：改为在目标库 `CreateLayout` 创建全新布局后**实体级克隆**纸空间内容，再 `CopyFrom` 复制打印设置。
2. **Core Console 保存限制**：`Database.SaveAs` 覆盖当前文档自身已打开路径抛 `eInvalidInput`（同路径各参数形态均复现；另存新路径成功且文档句柄不释放）。修复：插件保存到 attempt 目录内固定派生名 `working.saved.dwg`，进程退出、句柄释放后由 `CoreConsoleDrawingBuilder.build` 收敛回 `working.dwg`（`src/dst_builder/infrastructure/autocad/drawing.py`），并新增回归测试 `test_build_converges_core_console_saved_file_back_to_working_dwg`。
3. 插件保留 `DSTBUILDER_IMPORT=`/`DSTBUILDER_FINAL=` 诊断输出行（与既有 `DSTBUILDER_OK`/`DSTBUILDER_FAILED` 同风格），便于后续真实 CAD 排障。

修复后重跑：fake-CAD 专项 27 passed；真实 CAD 2020 与 2016 系统测试先后通过（2020 先于插件重建通过；2016 首跑失败原因是插件 DLL 未含修复，经 `build_builder_plugins.ps1` 重建双版本后通过）。

### 1.2 Task 12 发现并修复的契约漂移

Task 10 新增 Manager `POST /api/handoffs/open` 后，`web/src/api/openapi.json`/`schema.d.ts` 未重新生成，`npm run build` 的 `check:api` 门禁失败（`OpenAPI 契约已漂移`）。已执行 `cd web && npm run generate:api` 重新生成并提交。同时按收口要求重新生成了 `builder-web/src/api/openapi.json` 与 `schema.d.ts`（含 `GET /api/cadabilities` 与 Task 9/10 端点）。

## 2. 环境受限项与未执行项（不得视为通过）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 官方 Sheet Set Manager 打开生成的 DST | **未执行** | 需要完整 AutoCAD GUI 人工打开验证，无法经 accoreconsole 自动化替代 |
| 真实端到端“成果发布 → Manager 接管 → 初始修订恢复” | **未执行（真实 CAD 链路）** | 自动化覆盖止于 fake CAD 全流程与真实单 DWG 生成；真实包发布+真实交接+真实恢复的人工链路待执行 |
| 真实 WebView2 七步 UI 验收 | **未执行（人工）** | builder-web e2e 已覆盖键盘、错误聚焦、浅深主题、最小视口与 200% 缩放的自动化断言，但不构成真实 WebView2 人工验收 |
| 双 GUI 人工双开冒烟 | **未执行（人工）** | Task 11 已做并行启动冒烟，正式资格仍需人工复验 |
| 200% 缩放真实桌面复验 | **未执行（人工）** | 同上，e2e 断言不能替代 |
| Manager 全量真实 CAD 系统测试（`tests/system_autocad`）复跑 | **本轮未执行** | Manager 全量真实 CAD 回归属 Manager 计划自身的资格门禁，本轮仅执行 Builder 侧真实测试；共享原语提取（Task 6）后的 Manager 全量真实回归建议在下一人工验证轮执行 |
| 提交树敏感性核验 | `git ls-files` 扫描 | `sample/project1` 等真实样本与 `plugins/**/bin|obj`、`web/dist`、`.dst-manager-data` 均不在提交树；`sample/golden-template/` 下 11 个**零字节占位文件**系 2026-08-18 `d34417a` 有意追踪的目录结构模板（先于本分支存在），无真实客户数据 |

## 3. 独立代码审查

### 3.1 终审结论（2026-09-18 回填）

全分支终审已由 controller 执行（范围 `838c4da..3427171`，六遍遍历），结论：**0 Critical / 3 Important / 12 Minor（Ready to merge: With fixes）**。3 项 Important 已在本分支修复并复验：

1. **`_STATUS_BY_ERROR` 精确类型匹配 → MRO 查找**（`src/dst_builder/interfaces/api.py`）：未逐字登记的异常子类经 `exc.__class__.__mro__` 继承最近命中基类的状态码，不再静默落 400；补子类回归测试。
2. **`recover_pending_builds` 事务内文件 I/O 拆分**（`src/dst_builder/application/build_recovery.py`）：改为短事务只读待恢复项 → 事务关闭后执行文件现场裁决（读发布证据、verify 大包哈希、清理暂存）→ 每项独立短事务写回结果；四分支裁决语义不变，补"文件 I/O 不在事务内"回归测试。
3. **资源清理**（`src/dst_builder/application/builds.py` + lifespan）：终态（CANCELLED/SUCCEEDED/FAILED）迁移即清除 `(build_id, attempt)` 取消标志；新增 `BuildCoordinator.close()` 关闭后台构建线程执行器，并接入 `create_builder_app` lifespan shutdown 钩子；补两项回归测试。

**修复后终审结论：0 Critical / 0 Important。** 复验门禁：`uv run pytest tests/builder/ tests/architecture/`（686 passed / 3 skipped）、全量 `uv run pytest`（2267 tests，0 failures，75 skipped）、`uv run ruff check .`（0 违规）。

### 3.2 Minor 逐项裁决（终审 + 各任务评审积压，均不阻塞合并）

**Task 1（架构守卫）**
- 覆盖守卫按位置索引 `FORBIDDEN_RELATIONS[1][2]` 有顺序耦合且用子集断言：接受——最小架构门禁可辩护，超集绕过不构成实际漏洞。
- 动态 import 可绕过 AST 门禁：接受——已知限制，已记录于测试 docstring。
- CLI 无参建议 `no_args_is_help`、守卫 `==3` 放宽 `>=3`、探针文件进程强杀残留（try/finally 已覆盖常规路径）、xdist 并行探针理论竞争（当前串行）：接受现状。
- fix report"四成员均在探针覆盖内"表述略夸大：接受——实为 import 形态覆盖，扫描器与名称无关，实质成立。

**Task 2（规范化/命名）**
- `normalization.py` docstring 误写"计划哈希"（task_id 实派生自 revision sha256，循环自由、符合意图）：接受——Task 4/8 dispatch 已注明系有意为之。
- 前缀尾空格与 0x7F 未参数化：接受——行为正确，仅测试参数化程度问题。
- RED 证据省略 2/5 模块输出：接受——流程性改进，已向后续任务要求完整 RED 输出。

**Task 3（项目/草稿 API）**
- `create_project` 非原子（记录插入失败遗留空 .dstb）：推迟——仅全新目录创建时可能触发，概率极低，留下一轮。
- `_STATUS_BY_ERROR` 精确类型匹配致子类静默落 400：**已修复**（终审 Important ①）。
- 422 handler details 可能含不可 JSON 序列化 input：接受——FastAPI 校验错误结构受控，风险极低。
- OpenAPI 422 记录与自定义 handler 实际形态不符：推迟——可用 `openapi_extra` 修，留下一轮。
- `_validate_wizard_step` 裸 ValueError 死防御、测试名不副实、`_error_response` 恒输出 `details:null`：接受——无行为影响。

**Task 5（前端七步 UI）**
- WizardShell `--space-8` 未定义令牌靠 fallback：接受——视觉结果正确。
- HandoffStep 硬编码 build-1、buildId 未上收 store：接受——Task 9/10 已接线实际数据，残留清理留后续。
- ProjectStep 仅 output_path 有行内 aria 错误、hydrating 标志死代码：接受——无行为影响。
- rulesOk 内联复制校验规则：接受——建议 SPEC 稳定后补权威来源注释。
- blocking 诊断无 field 永不阻断：接受——行为符合契约，建议补注释。
- TemplatesStep cad_version 强转（先纳入资产后选版本会发空值）：接受——UI 引导顺序已隐含约束。
- `--font-ui` 字体栈与 Manager 不同：接受——本地选择，建议注释明示。
- error Toast 宜 `role="alert"`：接受——可访问性改进留下一轮。
- BuildStep 轮询失败静默无上限：接受——单用户桌面场景风险低。
- openapi.json inspect 端点缺 501 声明：接受——Task 12 已整体重生成双侧 OpenAPI 契约，如仍缺 501 声明留下一轮补 `openapi_extra`。

**Task 6（共享原语）**
- `test_platform_acsm_contract.py` 函数内局部 import dst_manager：接受——brief 强制的同类型断言所需。
- Manager codec.py `__all__` 导出私有名 `_DECODE/_ENCODE`：接受——既有 test_core.py 依赖，改名涉及 Manager 侧回归。
- CoreConsoleRequest.locale 默认 zh-CN 为 brief 外微小新增：接受——与目标环境一致。

**Task 7（CAD 管线）**
- `_write_script` 的 mbcs 写入在 try 外：接受——生僻字符场景失败即构建失败（fail-closed）。
- C# 侧不校验 layout_asset_path containment + 未 resolve 符号链接：接受——Python 侧第一道防御已校验，C# 侧为纵深弱化而非缺失。
- drawing.py docstring 提及取消路径：接受——Task 8+ 已实现，注释不再超前。
- 绿证据 log 缺 pytest 汇总行：接受——流程记录问题。
- Contracts.cs 依赖 ExtensionDataObject 私有字段名 "members"：接受——fail-closed 可接受。
- 提交体量 2573 行：接受——C#+Python 范围决定，可辩护。

**Task 9（build/attempt 编排）**
- 并发双 POST /api/builds 可同时过检：接受——单用户桌面应用；建议后续捕获完整性错误。
- UI 用 500ms 轮询而非消费 SSE 端点：接受——SSE 服务端完整已测，轮询为前端简化。
- `unique_staging_name` 忽略参数：接受——签名冗余，无行为影响。
- `recover_pending_builds` 事务内 rmtree/verify：**已修复**（终审 Important ②）；`list_attempts[-1]` 可能 IndexError：接受——正常路径不产生无 attempt 的 run。
- stream_events 每 100ms 全量重读 O(n²)：接受——单构建事件量小，桌面场景可接受。
- ThreadPoolExecutor 从不关闭：**已修复**（终审 Important ③）。
- builds.py 行数超软上限：接受——已拆分后仍超，进一步拆分收益低。

**Task 10（交接）**
- 崩溃残留复用路径无测试（"目录在 DB 无行"场景）：接受——防御逻辑存在，测试补齐留下一轮。
- 集成零写入矩阵缺 symlink/绝对路径/DST 损坏 3 场景：接受——结构上不可能写入，字面偏差。
- 幂等路径不补写 workspace.json：接受——重开走 DB 不受影响。
- 并发异哈希窄窗错误码 HANDOFF_INVALID 替代 ID_CONFLICT：接受——瞬态，重试即正确。
- builds.py 753 行既有债务：接受——同 Task 9。
- HandoffStep.vue:85 冗余三元：接受——纯清理。

**Task 11（桌面打包）**
- +1150 行超软上限 2.3 倍：接受——brief 测试体量驱动。
- 第二实例无前台唤起（与 Manager 行为差异）：接受——有意裁剪，建议 docstring 明示。
- start_local_server 忙等无超时：接受——与 Manager 同病，本地环回场景风险低。
- Path(__file__) 守护测试重复两份、test_non_windows_platform_allows_startup 全平台 monkeypatch 更优：接受——测试风格建议。

**Task 12（收口）**
- ① "最终重建后的 2020 DLL 未复跑系统测试"未明确：**已澄清**——补入本备忘 §1.1 时序澄清段。
- ② 收敛逻辑宽进条件（saved 缺失时可能发布 base 副本）：接受——现状不可达，真实路径已要求 saved 存在；如后续放宽需先加防御。
- ③ Commands.cs:62-64 改名分支近乎死代码：接受——保留作诊断/兼容分支，建议后续补触发条件注释。
- ④ SaveDrawing 改 `DwgVersion.Current` 未说明理由：**已澄清**——补入本备忘 §1.1 版本澄清段。

## 4. 结论与剩余门禁

- **开发闭环完成，正式双版本资格未满足。**
- SPEC-DB-001 保持 `status: review`；PLAN-DB-001 保持 `status: active`。
- **唯一剩余门禁**：真实双版本发布资格——AutoCAD 2016 与 2020 各自完成官方 Sheet Set Manager 打开生成 DST、真实端到端“成果发布 → Manager 显式接管 → 初始修订恢复”，以及真实 WebView2 七步 UI 人工验收；执行后按 SPEC-DB-001 §12 规则评审流转 SPEC/PLAN 状态。

## 附录 A：Builder EXE 构建结果

- 命令：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_builder_release.ps1`（退出码 0）。
- 产物：`dist/releases/dst-builder-v0.3.5-win64.zip`（28.8 MB，2026-09-18 04:12 本轮重建）；该脚本依次完成 builder-web `npm ci && npm run build`、双版本插件重建与 PyInstaller 打包，产物全部落在 `dst-builder` 命名空间，与 Manager 分发包并列互不影响。
