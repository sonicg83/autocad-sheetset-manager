---
id: PLAN-DB-001
title: DST Builder 单张图纸最小生成闭环实施计划
status: active
owners:
  - dst-builder
created: 2026-09-17
updated: 2026-09-18
related:
  - SPEC-DB-001
  - PRD-DB-001
  - ARCH-DB-001
  - RFC-INT-001
  - ARCH-INT-002
---

# DST Builder 单张图纸最小生成闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（当前会话逐任务实施）或 `superpowers:executing-plans`（独立会话按检查点实施）。每个任务严格按 TDD 的 RED → GREEN → REFACTOR 执行，复选框是唯一进度记录。

**Goal:** 交付第一条真实纵向闭环：七步向导创建“一项目、一张图纸”，生成不可变计划，通过 AutoCAD 2016/2020 Worker 生成 DWG，从零生成 DST 和图纸目录，原子发布只有 `drawings/`、`metadata/` 两个根目录的成果包，并由 DST Manager 显式接管为初始修订。

**Architecture:** 新增独立 `dst_builder` 后端、独立 `builder-web` 前端、独立桌面入口和项目数据库；当 Builder 成为第二个真实消费方时，把 DST Codec、AcSm 契约诊断和 Core Console 进程原语提取到 `dst_platform`，Manager 继续通过薄兼容导出使用这些实现。Builder 不导入 `dst_manager.*`。Manager 只通过版本化 `handoff.json` 接管，不读取 Builder 数据库。

**Tech Stack:** Python 3.12、UV、FastAPI、Typer、SQLAlchemy/Alembic、lxml、openpyxl、pytest、ruff；Vue 3、TypeScript、Vite、Vitest、Playwright；.NET Framework 4.8、AutoCAD 2016/2020 托管程序集；PyInstaller/WebView2。

**Spec:** [SPEC-DB-001：单张图纸最小生成闭环规范](../../../docs/dst-builder/specs/SPEC-DB-001-minimal-generation-loop.md)。本计划不得扩大该规范的首期规模。Excel、批量图纸、覆盖既有成果、外围插件和服务化只记录为后续需求，不留不可验证的备用实现。

## 1. 全局约束与实施顺序

- 先阅读根 `README.md`、`docs/README.md`、`docs/dst-builder/README.md`、SPEC-DB-001、ARCH-DB-001、ARCH-INT-002、RFC-INT-001；涉及 Manager 交接或发布安全时再读 ARCH-DM-001。
- 依赖顺序固定为：契约测试 → Builder 项目模型 → 引导界面 → 共享能力提取 → CAD/DST 生成 → 发布 → Manager 交接 → 打包与真实 CAD 资格。后序任务不得用 stub 宣称闭环完成。
- 每个 Python 行为先写失败测试；每个界面行为先写 Vitest/Playwright 失败用例；每个插件行为先写无需 AutoCAD 的纯契约测试，再执行可选真实 CAD 测试。
- 所有生成只在 `builds/<build-id>/attempt-NNN/` 内发生；正式目标在 Task 9 前始终不存在。
- 用户值只进入 JSON/DOM/参数数组，不进入 SCR、Shell 字符串或未校验路径操作。
- Builder 与 Manager 可执行名、端口选择、`%LOCALAPPDATA%`、前端目录、数据库、迁移链和发布物完全分离。
- `src/dst_builder/domain/` 不依赖 FastAPI、SQLAlchemy、文件系统、AutoCAD 或 Manager；`src/dst_platform/` 不依赖任一产品包。
- 每个源文件遵守约 500 行软上限；应用编排按 project/planning/build/handoff 拆分，禁止创建 Builder 版巨型 `service.py`。
- 每个任务只暂存列出的文件并使用简体中文 commit message；不得使用 `git add .`。
- 完成代码任务后至少运行 `uv run ruff check .` 与相关 pytest；修改 Web 时运行 `npm run build` 和相关 Playwright；改迁移时验证全新库升级。

## 2. 目标模块与依赖

```text
builder-web ─HTTP/SSE─> dst_builder.interfaces
                            │
                    dst_builder.application
                      │                 │
             dst_builder.domain   dst_builder.infrastructure
                                      │
                                  dst_platform

dst_manager.application.handoff ──> dst_platform.contracts
dst_manager.infrastructure ───────> dst_platform.acsm/autocad
```

必须通过静态测试禁止以下依赖：

```python
FORBIDDEN = {
    "src/dst_builder": ("dst_manager",),
    "src/dst_platform": ("dst_builder", "dst_manager", "fastapi", "sqlalchemy"),
    "src/dst_builder/domain": ("fastapi", "sqlalchemy", "lxml", "dst_manager"),
}
```

## 3. 实施任务

### Task 1：冻结跨层契约与独立产品骨架

**Files:**

- Create: `src/dst_builder/__init__.py`
- Create: `src/dst_builder/domain/__init__.py`
- Create: `src/dst_builder/application/__init__.py`
- Create: `src/dst_builder/infrastructure/__init__.py`
- Create: `src/dst_builder/interfaces/__init__.py`
- Create: `src/dst_builder/interfaces/cli.py`
- Create: `src/dst_platform/__init__.py`
- Create: `tests/architecture/test_product_boundaries.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [x] RED：写 `test_product_boundaries.py`，AST 扫描并证明 `dst_builder` 不引用 `dst_manager`、`dst_platform` 不引用产品包、Builder domain 不引用框架；此时因包不存在而失败。
- [x] GREEN：创建五层 Builder 包和无产品依赖的 `dst_platform` 包；`pyproject.toml` 的 Hatch packages 改为三个包，并新增独立脚本：

```toml
[project.scripts]
dst-manager = "dst_manager.interfaces.cli:app"
dst-builder = "dst_builder.interfaces.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/dst_manager", "src/dst_builder", "src/dst_platform"]
```

- [x] 新建最小 CLI `dst-builder --version`，不得启动 Manager 或复用 Manager 应用工厂。
- [x] Verify：`uv lock --check`、`uv run ruff check .`、`uv run pytest tests/architecture/test_product_boundaries.py -q`，并执行 `uv run dst-builder --version`。
- [x] Commit：`建立 DST Builder 独立产品骨架与依赖门禁`。

### Task 2：实现领域模型、规范化哈希和构建状态机

**Files:**

- Create: `src/dst_builder/domain/models.py`
- Create: `src/dst_builder/domain/normalization.py`
- Create: `src/dst_platform/contracts/__init__.py`
- Create: `src/dst_platform/contracts/naming.py`
- Create: `src/dst_builder/domain/planning.py`
- Create: `src/dst_builder/domain/build_state.py`
- Create: `tests/builder/unit/test_normalization.py`
- Create: `tests/builder/unit/test_naming.py`
- Create: `tests/builder/unit/test_planning.py`
- Create: `tests/builder/unit/test_build_state.py`
- Create: `tests/builder/unit/test_contract_examples.py`

- [x] RED：把 SPEC-DB-001 的 `DraftProjectV1`、`ProjectRevisionV1`、`GenerationPlanV1`、`BuildEventV1`、manifest 和 handoff 示例固化为契约测试夹具，先因模型不存在失败。
- [x] RED：参数化测试字符串长度、非法字符、保留设备名、尾点/空格、图号溢出、恰好一张图纸和输出目录已存在；覆盖所有 SPEC 错误码，并用 Manager 既有危险名称样例证明共享纯函数语义一致。
- [x] RED：证明键顺序和机器路径变化不改变哈希，业务字段或资产字节变化必然改变修订/计划 ID。
- [x] RED：证明所有非法状态迁移和 `PUBLISHING` 取消被拒绝。
- [x] GREEN：以冻结 dataclass/StrEnum 实现模型，入口保持纯函数：

```python
def validate_draft(draft: DraftProjectV1, *, output_exists: bool) -> tuple[Diagnostic, ...]: ...
def commit_revision(draft: DraftProjectV1, assets: tuple[AssetSnapshot, ...]) -> ProjectRevisionV1: ...
def create_plan(revision: ProjectRevisionV1) -> GenerationPlanV1: ...
def transition(current: BuildStatus, target: BuildStatus) -> BuildStatus: ...
```

- [x] GREEN：计划中的 `expected_artifacts` 必须明确列出 DST、DWG、XLSX，以及 `project-revision.json`、`generation-plan.json`、`validation-report.json`、`handoff.json`；manifest/handoff 的最终字节在 Task 9 生成。
- [x] REFACTOR：模型只保存 POSIX 相对路径；Windows 绝对路径只存在于 application/infrastructure 边界。`output_path` 不进入修订/计划哈希，由 `BuildRun` 单独快照。
- [x] Verify：`uv run pytest tests/builder/unit/test_contract_examples.py tests/builder/unit/test_normalization.py tests/builder/unit/test_naming.py tests/builder/unit/test_planning.py tests/builder/unit/test_build_state.py -q`。
- [x] Commit：`实现 Builder 确定性修订计划与构建状态机`。

### Task 3：建立项目数据库、独立迁移和草稿 API

**Files:**

- Create: `builder_alembic.ini`
- Create: `builder_migrations/env.py`
- Create: `builder_migrations/script.py.mako`
- Create: `builder_migrations/versions/0001_db001_initial.py`
- Create: `src/dst_builder/infrastructure/persistence/__init__.py`
- Create: `src/dst_builder/infrastructure/persistence/database.py`
- Create: `src/dst_builder/infrastructure/persistence/repositories.py`
- Create: `src/dst_builder/application/projects.py`
- Create: `src/dst_builder/interfaces/schemas.py`
- Create: `src/dst_builder/interfaces/responses.py`
- Create: `src/dst_builder/interfaces/api.py`
- Modify: `src/dst_builder/interfaces/cli.py`
- Create: `tests/builder/integration/test_builder_migrations.py`
- Create: `tests/builder/integration/test_project_api.py`
- Create: `scripts/export_builder_openapi.py`

- [x] RED：从空目录升级后断言 SPEC-DB-001 的八张表、唯一约束与 Schema 版本；Manager 数据库表不得出现。
- [x] RED：API 测试创建项目、读取当前草稿、带 `base_updated_at` 保存、过期写入返回 `409 DRAFT_CONFLICT`、只读打开不改变资产/构建目录。
- [x] GREEN：实现 `ProjectRepository`、`RevisionRepository`、`BuildRepository` Protocol 及 SQLite adapter；事务边界由 application service 控制。
- [x] GREEN：实现独立应用工厂：

```python
def create_builder_app(project_root: Path | None = None) -> FastAPI: ...
```

并提供 `POST /api/projects`、`GET /api/projects/current`、`PATCH /api/projects/current/draft`。
- [x] GREEN：CLI `dst-builder serve --project <path>` 只监听 `127.0.0.1`；数据库不存在时只有创建项目接口可以写入。
- [x] 生成并提交 Builder OpenAPI；生成脚本导入 Builder app，不能改写 `web/src/api/openapi.json`。
- [x] Verify：`uv run alembic -c builder_alembic.ini upgrade head`（任务专用临时库）、`uv run pytest tests/builder/integration/test_builder_migrations.py tests/builder/integration/test_project_api.py -q`。
- [x] Commit：`建立 Builder 项目库迁移与草稿接口`。

### Task 4：实现资产纳入、路径边界和 CAD 能力探测

**Files:**

- Create: `src/dst_builder/domain/paths.py`
- Create: `src/dst_builder/application/assets.py`
- Create: `src/dst_builder/infrastructure/assets/__init__.py`
- Create: `src/dst_builder/infrastructure/assets/store.py`
- Create: `src/dst_builder/infrastructure/autocad/__init__.py`
- Create: `src/dst_builder/infrastructure/autocad/capabilities.py`
- Modify: `src/dst_builder/interfaces/api.py`
- Modify: `src/dst_builder/interfaces/schemas.py`
- Create: `tests/builder/unit/test_project_paths.py`
- Create: `tests/builder/integration/test_asset_api.py`
- Create: `tests/builder/integration/test_cad_capabilities.py`

- [x] RED：覆盖绝对/相对路径、`..`、junction/symlink、大小写碰撞、同内容去重、复制中源文件变化和 2 GiB 上限。
- [x] RED：CAD 探测只接受已配置且版本匹配的 2016/2020 Core Console 与插件，不允许“找到任意 acad.exe”视为可用。
- [x] GREEN：资产先复制到项目内临时文件，复制前后校验大小和 SHA-256，再以内容寻址名称原子改名；数据库与文件提交失败时都不留下假记录。
- [x] GREEN：实现 `POST /api/assets` 和只读 capability 响应；布局 inspection 先定义端口，Task 7 接真实执行器。
- [x] Verify：`uv run pytest tests/builder/unit/test_project_paths.py tests/builder/integration/test_asset_api.py tests/builder/integration/test_cad_capabilities.py -q`。
- [x] Commit：`实现 Builder 资产纳入与 CAD 能力探测`。

### Task 5：实现独立七步引导前端

**Files:**

- Create: `builder-web/package.json`
- Create: `builder-web/package-lock.json`
- Create: `builder-web/vite.config.ts`
- Create: `builder-web/playwright.config.ts`
- Create: `builder-web/index.html`
- Create: `builder-web/src/main.ts`
- Create: `builder-web/src/App.vue`
- Create: `builder-web/src/styles/tokens.css`
- Create: `builder-web/src/api/client.ts`
- Create: `builder-web/src/api/schema.d.ts`
- Create: `builder-web/src/components/WizardShell.vue`
- Create: `builder-web/src/components/StepRail.vue`
- Create: `builder-web/src/components/GuidancePanel.vue`
- Create: `builder-web/src/components/ActionDock.vue`
- Create: `builder-web/src/steps/ProjectStep.vue`
- Create: `builder-web/src/steps/RulesStep.vue`
- Create: `builder-web/src/steps/SheetsStep.vue`
- Create: `builder-web/src/steps/TemplatesStep.vue`
- Create: `builder-web/src/steps/ReviewStep.vue`
- Create: `builder-web/src/steps/BuildStep.vue`
- Create: `builder-web/src/steps/HandoffStep.vue`
- Create: `builder-web/src/composables/useDraftAutosave.ts`
- Create: `builder-web/src/composables/useWizardGuard.ts`
- Create: `builder-web/tests/e2e/wizard-flow.spec.ts`
- Create: `builder-web/tests/e2e/wizard-accessibility.spec.ts`

- [x] RED：Playwright 先覆盖七步顺序、前置门禁、已完成步骤回访、500 ms 自动保存、重启恢复、步骤 5 不自动确认、字段错误摘要聚焦和键盘主流程。
- [x] RED：覆盖 1280×720、最小支持视口、浅/深主题与浏览器 200% 缩放，无横向溢出和固定操作栏遮挡焦点。
- [x] GREEN：创建独立 Vue 应用；只复刻 ARCH-DB-001 已接受的语义令牌值，不从 Manager `web/` 做相对源码 import。形成两个真实消费方后，若令牌确需共享，另提共享资产任务。
- [x] GREEN：每一步只渲染本期字段；推迟能力不显示 disabled 占位。后端字段诊断映射到具体控件，Toast 只作补充。
- [x] GREEN：从 Builder OpenAPI 生成 `schema.d.ts`，API client 不手写重复枚举。
- [x] Verify：在 `builder-web/` 执行 `npm ci`、`npm run build`、`npm run test:unit`、`npm run test:e2e -- wizard-flow.spec.ts wizard-accessibility.spec.ts`。
- [x] Commit：`实现 DST Builder 七步引导界面`。

### Task 6：把第二消费方需要的稳定能力提取到 `dst_platform`

**Files:**

- Create: `src/dst_platform/contracts/diagnostics.py`
- Modify: `src/dst_platform/contracts/naming.py`
- Modify: Manager 现有危险名称校验入口，改为调用共享纯函数
- Create: `src/dst_platform/acsm/__init__.py`
- Create: `src/dst_platform/acsm/codec.py`
- Create: `src/dst_platform/acsm/contract.py`
- Create: `src/dst_platform/acsm/schema/acsm-v1.xsd`
- Create: `src/dst_platform/autocad/__init__.py`
- Create: `src/dst_platform/autocad/process.py`
- Modify: `src/dst_manager/domain/models.py`
- Modify: `src/dst_manager/infrastructure/dst_codec/codec.py`
- Modify: `src/dst_manager/infrastructure/acsm_xml/contract.py`
- Modify: `src/dst_manager/infrastructure/autocad/worker.py`
- Modify: PyInstaller hidden data/config where required
- Create: `tests/platform/test_acsm_codec.py`
- Create: `tests/platform/test_acsm_contract.py`
- Create: `tests/platform/test_core_console_process.py`
- Modify: existing Manager codec/AcSm/worker tests only for import ownership assertions

- [x] RED：为共享 API 写产品无关测试，先证明当前实现只能从 Manager import。
- [x] RED：增加 AST 门禁，`dst_platform` 对 Builder/Manager 反向 import 立即失败。
- [x] GREEN：移动实现和 XSD，不复制第二份逻辑；共享稳定接口固定为：

```python
class DstCodec: ...
def validate_contract(root: etree._Element) -> tuple[ValidationIssue, ...]: ...
def validate_schema(root: etree._Element, version: str = CONTRACT_VERSION) -> tuple[ValidationIssue, ...]: ...
class CoreConsoleExecutor:
    def run(self, request: CoreConsoleRequest) -> CoreConsoleResult: ...
```

- [x] GREEN：Manager 原路径只做薄 re-export/adapter，既有公共导入、错误码、日志解码和 SCR 渲染行为不变；Builder 只引用 `dst_platform`。
- [x] REFACTOR：`Severity`、`ValidationIssue` 所有权迁至 `dst_platform.contracts`，Manager domain 兼容导出同一类型，避免两套诊断模型。
- [x] Verify：共享专项测试、全部既有 `tests/unit/test_acsm_contract.py tests/unit/test_autocad_worker.py`、`uv run ruff check .`。
- [x] Commit：`提取 Builder 与 Manager 共用的 DST 和 CAD 原语`。

### Task 7：实现独立 Builder AutoCAD Worker 与单 DWG 生成

**Files:**

- Create: `plugins/src/DstBuilder.AutoCAD/DstBuilder.AutoCAD.csproj`
- Create: `plugins/src/DstBuilder.AutoCAD/Commands.cs`
- Create: `plugins/src/DstBuilder.AutoCAD/Contracts.cs`
- Create: `plugins/tests/DstBuilder.AutoCAD.Tests/DstBuilder.AutoCAD.Tests.csproj`
- Create: `plugins/tests/DstBuilder.AutoCAD.Tests/ContractValidationTests.cs`
- Create: `scripts/build_builder_plugins.ps1`
- Create: `src/dst_builder/infrastructure/autocad/request.py`
- Create: `src/dst_builder/infrastructure/autocad/script.py`
- Create: `src/dst_builder/infrastructure/autocad/drawing.py`
- Modify: `src/dst_builder/application/assets.py`
- Create: `tests/builder/unit/test_cad_request.py`
- Create: `tests/builder/unit/test_builder_script.py`
- Create: `tests/builder/integration/test_drawing_builder.py`
- Create: `tests/builder/system_autocad/test_minimal_drawing.py`

- [x] RED：测试结构化 request/result Schema、项目/attempt 路径约束、固定 SCR 命令、用户文本不出现在 SCR、参数数组执行、超时/取消/缺结果/版本不匹配。
- [x] RED：C# 纯契约测试覆盖未知 Schema、路径逃逸、`Model` 布局、源布局不存在、目标布局冲突和结果原子写入；测试项目只链接纯 `Contracts.cs`，不加载 AutoCAD 程序集。
- [x] GREEN：插件唯一命令为 `DSTBUILDER_CREATE_DRAWING`；从固定 request JSON 导入布局、保留 `Model` 加唯一目标布局、保存并输出 Handle/版本/诊断。
- [x] GREEN：Python adapter 实现：

```python
class DrawingBuilder(Protocol):
    def inspect_layouts(self, asset: AssetSnapshot, cad_version: CadVersion) -> tuple[str, ...]: ...
    def build(self, task: DrawingTask, attempt: AttemptPaths) -> CadDrawingResultV1: ...
```

- [x] 非 CAD 测试用 fake executor 验证编排；真实测试只操作私有样本副本并由 `DST_BUILDER_RUN_AUTOCAD=1` 显式启用。
- [x] Verify：`dotnet test plugins/tests/DstBuilder.AutoCAD.Tests/DstBuilder.AutoCAD.Tests.csproj`、`powershell -File scripts/build_builder_plugins.ps1`（环境具备时）及 Python 非 CAD 专项测试；分别记录 2016/2020 系统测试是否执行。
- [x] Commit：`实现 Builder 单图纸 AutoCAD Worker`。

### Task 8：从零生成 DST、XLSX 与完整验证报告

**Files:**

- Create: `src/dst_builder/infrastructure/acsm/factory.py`
- Create: `src/dst_builder/infrastructure/acsm/__init__.py`
- Create: `src/dst_builder/infrastructure/acsm/projection.py`
- Create: `src/dst_builder/infrastructure/catalog/__init__.py`
- Create: `src/dst_builder/infrastructure/catalog/xlsx.py`
- Create: `src/dst_builder/application/validation.py`
- Create: `tests/builder/unit/test_acsm_factory.py`
- Create: `tests/builder/unit/test_acsm_projection.py`
- Create: `tests/builder/unit/test_catalog_xlsx.py`
- Create: `tests/builder/integration/test_dst_artifacts.py`

- [x] RED：同一计划与 CAD 结果两次构造 XML 字节一致、对象 UUIDv5 一致；不同计划改变对象 ID。
- [x] RED：测试 SheetSet/Subset/Sheet/LayoutReference 必需节点、相对 DWG 路径、布局 Handle、Codec 往返、Schema 和语义投影；任何不一致返回 `DST_VALIDATION_FAILED`。
- [x] RED：XLSX 固定工作表、表头、唯一数据行和字符串图号（保留前导零）。
- [x] GREEN：Builder AcSm factory 直接构造新 DOM；不读取模板 DST，不调用 Manager document/editing 层，不实现旧 DLL 回退。
- [x] GREEN：验证报告汇总输入、DWG、DST、XLSX、引用边界和校验器版本；报告诊断使用共享类型。
- [x] Verify：`uv run pytest tests/builder/unit/test_acsm_factory.py tests/builder/unit/test_acsm_projection.py tests/builder/unit/test_catalog_xlsx.py tests/builder/integration/test_dst_artifacts.py -q`。
- [x] Commit：`实现 Builder DST 与图纸目录确定性生成`。

### Task 9：实现 build/attempt 编排、SSE、恢复和原子发布

**Files:**

- Create: `src/dst_builder/application/builds.py`
- Create: `src/dst_builder/application/build_recovery.py`
- Create: `src/dst_builder/infrastructure/filesystem/__init__.py`
- Create: `src/dst_builder/infrastructure/filesystem/attempts.py`
- Create: `src/dst_builder/infrastructure/filesystem/package.py`
- Create: `src/dst_builder/infrastructure/filesystem/publisher.py`
- Modify: `src/dst_builder/interfaces/api.py`
- Modify: `src/dst_builder/interfaces/schemas.py`
- Create: `tests/builder/unit/test_package_manifest.py`
- Create: `tests/builder/unit/test_builder_publisher.py`
- Create: `tests/builder/integration/test_build_api.py`
- Create: `tests/builder/integration/test_build_recovery.py`
- Create: `tests/builder/integration/test_minimal_loop_fake_cad.py`

- [x] RED：以 fake CAD 跑完整状态序列，验证事件序号、`Last-Event-ID` 重放、计划冻结、安全取消和新 attempt 递增。
- [x] RED：每个阶段故障注入；在最终改名前正式目标必须不存在。目标预存在返回 `PACKAGE_TARGET_EXISTS` 且不修改它。
- [x] RED：manifest 排序、路径/大小/哈希、根目录只有两项、handoff 不进 manifest、无空 assets 目录、成果内无绝对路径。
- [x] RED：启动恢复覆盖 PREPARING～VERIFYING 中断、PUBLISHING 未改名、已完整改名和歧义现场。
- [x] GREEN：实现 `BuildCoordinator`，每次状态变化和事件写入同一数据库事务；阻塞 CAD 调用在线程执行器中运行，不阻塞 SSE event loop。
- [x] GREEN：候选包在 attempt 内完成后复制到目标父目录的唯一暂存目录，重新验证，再执行同卷 `os.replace(staging, target)`；首期禁止替换现有目标。
- [x] GREEN：实现 `POST /api/plans`、confirm、build/cancel/status/events；UI 步骤 5～7 接真实 API，构建中字段只读。
- [x] Verify：Builder unit/integration 全量，`builder-web` build 与 wizard e2e。
- [x] Commit：`贯通 Builder 构建编排与原子成果发布`。

### Task 10：实现 Manager 显式交接和真实初始修订

**Files:**

- Create: `src/dst_manager/application/handoff.py`
- Create: `src/dst_manager/infrastructure/handoff/__init__.py`
- Create: `src/dst_manager/infrastructure/handoff/reader.py`
- Modify: `src/dst_manager/infrastructure/persistence/database.py`
- Modify: `src/dst_manager/interfaces/api.py`
- Modify: `src/dst_manager/interfaces/schemas.py`
- Modify: `src/dst_manager/interfaces/responses.py`
- Create: `migrations/versions/0007_db001_builder_handoff.py`
- Create: `tests/unit/test_handoff_reader.py`
- Create: `tests/integration/test_builder_handoff_api.py`
- Modify: revision restore/list tests for `kind` and `source_json`
- Modify: `src/dst_builder/application/builds.py`
- Modify: `builder-web/src/steps/HandoffStep.vue`

- [x] 先阅读 ARCH-DM-001 的只读打开、永久 before 快照、发布事务与启动恢复约束。
- [x] RED：交接成功、重复幂等、ID 冲突、未知 Schema、manifest 漂移、文件缺失、绝对/`..`/symlink 逃逸、大小写碰撞、DST 引用出界全部先失败。
- [x] RED：任何验证失败都断言 `workspaces`、`handoff_sources`、`document_revisions` 和修订目录零新增。
- [x] RED：成功后初始修订 `kind=handoff_initial`，before/result 都是 DST 哈希，revision directory 含可验证 manifest、完整 `drawings/` 基线和 Builder metadata 副本；现有修订列表/恢复逻辑仍工作。
- [x] GREEN：迁移新增 `handoff_sources` 表，并给 `document_revisions` 增加非空默认 `kind='operation'` 与可空 `source_json`；全新数据库和旧数据库升级都测试。
- [x] GREEN：新增 `POST /api/handoffs/open`；调用先验证再创建数据库与文件证据。普通 `/api/workspaces/open` 不推断 handoff，不改变只读语义。
- [x] GREEN：Builder 的“一键交接”通过显式 adapter 调用 Manager API；Manager 不可用时保留已发布包并显示可执行恢复动作。
- [x] Verify：迁移升级、handoff 专项、Manager revisions/publisher/recovery 回归和 `tests/integration/test_api.py`。
- [x] Commit：`实现 Builder 成果向 Manager 的显式交接`。

### Task 11：桌面壳、独立打包与双产品共存

**Files:**

- Create: `src/dst_builder/interfaces/desktop.py`
- Create: `src/dst_builder/interfaces/shell.py`
- Create: `packaging/builder_entry.py`
- Create: `packaging/dst-builder.spec`
- Create: `scripts/build_builder_release.ps1`
- Modify: Builder PyInstaller data/hidden imports for `builder-web/dist`、XSD、迁移和双版本插件
- Create: `tests/builder/unit/test_builder_desktop.py`
- Create: `tests/builder/integration/test_builder_packaging_contract.py`

- [x] RED：测试 Builder 使用独立应用 ID、进程标题、单实例锁、动态回环端口和 `%LOCALAPPDATA%/dst-builder`；与 Manager 同时运行互不抢占。
- [x] RED：打包契约必须包含 Builder web、Builder 迁移、共享 XSD、2016/2020 Builder 插件；不得捆入 Manager web 或私有样本。
- [x] GREEN：借鉴 Manager 已验证的 WebView2 壳模式，但独立实现产品入口和资源发现；不从 Manager shell import。
- [x] GREEN：发布压缩包与可执行文件明确命名 `dst-builder`，版本独立；Manager 发布脚本行为不变。
- [x] Verify：`npm --prefix builder-web run build`、PyInstaller 构建、解包敏感文件扫描、Builder/Manager 并行启动冒烟。
- [x] Commit：`完成 DST Builder 独立桌面打包与共存验证`。

### Task 12：全量门禁、真实 CAD 资格与文档收口

**Files:**

- Modify: `docs/dst-builder/specs/SPEC-DB-001-minimal-generation-loop.md`
- Modify: `.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md`
- Modify: `docs/dst-builder/README.md`
- Modify: `.planning/plans/dst-builder/README.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `changelog.md`
- Create: `.planning/memos/dst-builder/PLAN-DB-001-release-evidence.md`

- [x] 运行 Python 全量：`uv run ruff check .`、`uv run pytest -q`（2186 passed / 75 skipped / 0 failed）、`uv lock --check`、Builder/Manager 两条 Alembic 全新升级。
- [x] 运行两个 Web：Manager `npm ci && npm run build && npm run test:e2e`；Builder 同等命令（builder-web e2e 20 passed）。
- [x] 构建两个 Builder 插件与 Builder EXE；确认公开提交树不含 `sample/`、插件 bin/obj、密钥、真实客户路径或生成物。
- [ ] 用户/环境显式启用后，分别用 AutoCAD 2016、2020 完成：布局导入、DWG 保存（两版本真实系统测试已通过）、DST Codec/Schema（无 CAD 自动化覆盖）、官方 Sheet Set Manager 打开、成果发布、Manager 接管和初始修订恢复（后四项的真实端到端执行待人工/后续任务完成）。
- [x] 真实 CAD 任一版本未执行时，在 evidence memo 和最终报告明确标为“开发闭环完成，正式双版本资格未满足”，不得把跳过写成通过。
- [ ] 对七步 UI 执行键盘、错误聚焦、浅深主题、最小视口、200% 缩放（builder-web e2e 自动化覆盖）和真实 WebView2 验收（人工未执行，见 evidence memo）。
- [x] 独立代码审查必须确认 0 Critical、0 Important；Minor 要么修复，要么在 memo 中逐项裁决（终审 0 Critical/3 Important，3 项已修复并复验；Minor 逐项裁决见发布证据备忘）。
- [x] 所有证据齐全后将 SPEC-DB-001 从 `review` 改为 `accepted`，PLAN-DB-001 从 `active` 改为 `completed`；若只完成开发门禁而缺真实资格，计划保持 `active` 并列出唯一剩余门禁（当前按后者执行：SPEC 保持 `review`，PLAN 保持 `active`）。
- [x] Commit：`收口 DST Builder 最小生成闭环验证与文档`。

> **剩余唯一门禁（2026-09-18）：** 真实双版本发布资格未满足——官方 Sheet Set Manager 打开生成 DST、真实端到端“成果发布 → Manager 接管 → 初始修订恢复”链路，以及真实 WebView2 七步 UI 人工验收尚未执行；证据与命令记录见 [PLAN-DB-001 发布证据备忘](../../memos/dst-builder/PLAN-DB-001-release-evidence.md)。

## 4. 检查点

| 检查点 | 完成任务 | 必须证明 | 未通过时 |
| --- | --- | --- | --- |
| G0 契约冻结 | 1～2 | 模型、哈希、状态和依赖方向已测试 | 不创建数据库/API |
| G1 可保存向导 | 3～5 | 七步草稿可保存恢复，未启动 CAD | 不提取/接入 CAD |
| G2 生成内核 | 6～8 | fake/真实 adapter 可产出并验证 DWG、DST、XLSX | 不发布正式目录 |
| G3 成果发布 | 9 | 故障注入下目标不存在或完整 | 不接入 Manager |
| G4 显式接管 | 10 | Manager 验证、幂等、初始修订真实可读 | 不宣称端到端完成 |
| G5 产品化 | 11～12 | 双产品共存、全量门禁、真实 CAD 证据 | 不宣称正式发布资格 |

每个检查点结束都由实施者复核实际 diff 与 SPEC；出现需求变化时先修订 SPEC 并回到用户确认，不在代码中静默扩展。

## 5. 最终完成标准

- 一个新用户可只通过七步界面从空白项目生成一张真实图纸，不需要理解 XML、SCR、Handle 或数据库。
- 相同修订和资产产生相同计划、AcSm 对象 ID 和确定性 metadata；时间只出现在非哈希运行记录中。
- AutoCAD 2016/2020 各自使用匹配插件；无旧 DLL、第二实现或隐式回退。
- 正式成果根目录恰好只有 `drawings/`、`metadata/`；首期目标预存在时明确拒绝且不修改。
- Manager 只通过版本化 handoff 接管，损坏包零写入，重复包幂等，初始修订含可验证永久基线。
- Builder 与 Manager 可独立安装、启动、升级、打包和发布；Builder 不导入 Manager 内部实现。
- 自动化门禁全绿；真实 CAD 与 WebView2 未执行项如实登记，且不会被自动化替代为发布资格。

## 6. 主要风险与止损

- **AcSm 新建 DOM 与官方行为不一致：** Task 8 先做单张黄金样本与官方打开测试；无法证明时计划阻断，不引入旧 DLL 回退。
- **共享提取导致 Manager 回归：** 只移动已出现第二消费方的稳定原语，保留旧 import 的薄适配；共享专项与 Manager 全量回归同一提交执行。
- **AutoCAD 版本差异：** 插件双目标构建、请求 Schema 相同、结果分别验收；不使用一个版本结果推断另一个版本。
- **发布目录跨卷或已存在：** 暂存固定在目标父目录且首期拒绝覆盖；不做复制后删除的伪原子发布。
- **Manager 初始修订不可恢复：** 测试必须从永久基线执行恢复并重新验证 DST；仅新增数据库行不算完成。
- **首期范围膨胀：** 任何 Excel、批量、外围插件、覆盖发布或服务化诉求进入新的 DB Spec/Plan，不插入本计划。
