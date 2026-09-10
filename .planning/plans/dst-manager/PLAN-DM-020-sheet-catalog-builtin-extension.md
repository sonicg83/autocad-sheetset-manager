---
id: PLAN-DM-020
title: 内置扩展平台与图纸目录 XLSX 实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-09
updated: 2026-09-09
related:
  - PRD-DM-001
  - ARCH-DM-001
  - ARCH-DM-005
  - ARCH-DM-006
  - SPEC-DM-012
  - GUIDE-DM-001
---

# 内置扩展平台与图纸目录 XLSX 实施计划

> **供代理执行：** 必须使用 `superpowers:executing-plans`；选择会话内分工执行时还必须使用 `superpowers:subagent-driven-development`。每个任务严格先写失败测试，再做最小实现，并在批次检查点停止复核。

**目标：** 交付可启停、故障隔离且仅持有最小能力的内置扩展平台，并以 `dst-manager.sheet-catalog` 在独立页面完成三固定字段及可配置表达式模板的 XLSX 导出；用户选择最终位置，Artifact 来源修订和哈希仅在后台记录。

**架构：** 固定代码索引加载随包清单，`ExtensionRegistry` 统一管理生命周期与动作分派，`CapabilityBroker` 只发放带修订身份的冻结快照。图纸目录扩展解析受限表达式并在应用临时目录产生候选 XLSX；宿主消费一次性保存授权、回读校验、同卷原子替换并登记 Artifact。Vue 只渲染宿主允许的编译期页面映射，不能加载扩展提供的脚本或路径。

**技术栈：** Python 3.12、FastAPI、Pydantic、SQLAlchemy/Alembic、PyYAML、openpyxl、pywebview/WebView2、Vue 3、TypeScript、Vite、Playwright、UV、PyInstaller。

**规范：** [ARCH-DM-006](../../../docs/dst-manager/architecture/ARCH-DM-006-builtin-extension-platform.md)、[SPEC-DM-012](../../../docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md)、[G4 冻结 Demo](../../../docs/dst-manager/mockups/SPEC-DM-012-sheet-catalog-demo.html)、[G5 技术映射](../../memos/dst-manager/2026-09-09-sheet-catalog-g5-technical-mapping.md)。

## 全局约束

- 执行前阅读根 `README.md`、`docs/README.md`、`docs/dst-manager/README.md`、`ARCH-DM-001`、`ARCH-DM-006`、`SPEC-DM-012` 和本计划；检查并保留用户已有改动。
- 使用 PowerShell 和 UV；变更 Python 依赖必须同时更新 `pyproject.toml`、`uv.lock`，变更前端依赖必须同步 `package.json`、`package-lock.json`。
- 每个任务遵循 red → green → refactor；失败必须是预期缺失能力，而不是夹具、导入或环境错误。每个批次结束运行最小充分回归并做一次需求/安全自审。
- `DstManagerService` 只组合平台入口；禁止把注册表、表达式、XLSX、Artifact 或保存路径逻辑追加到 `application/service.py`。
- `interfaces/api.py`、`infrastructure/persistence/database.py`、`web/src/App.vue` 已达到容量软上限；只允许最小装配改动，新职责进入本计划指定的新模块。
- 扩展不能取得 `DstManagerService`、SQLAlchemy Session、可变 `Workspace`/DOM、发布器、任务队列、ShellBridge、工作区根路径、DST/DWG 绝对路径或最终保存路径。
- API 不接受客户端提交的任意输出路径；保存路径只能来自桌面壳固定 XLSX `SAVE_DIALOG` 创建的一次性授权。
- `SAVE_DIALOG` 是本计划新增的 pywebview 保存对话框类型接线，不是现有 ShellBridge 能力；宿主根据清单中受支持的 `output_kind=xlsx` 固定过滤器和 `.xlsx` 后缀。
- 导出不调用 CAD Worker，不创建 job/修订/工程写锁，不写 DST/DWG，不创建工程内 `.dst-manager/`；测试只使用临时副本，不修改 `sample/`。
- Artifact 只有最终原子保存成功后才能登记；普通页面不显示来源修订、扩展版本或哈希。
- 冻结 Demo 是 G8 比对基准。主流程、页面结构、表达式语义或保存协议如需改变，停止实施并回到 G2～G6 更新规范和追踪矩阵。
- 批次四依赖 `ARCH-DM-005` 的唯一 `vue-i18n` 实例和 `zh-CN`/`en-US` 资源装载能力。若执行到批次三检查点时该基础仍未实施，保持本计划 `active` 并暂停批次四；不得硬编码中文或创建局部翻译器绕过此前置条件。
- ARCH-DM-005 的实施必须按[多语言实施门禁待办](../../todos/dst-manager/2026-09-09-arch-dm-005-implementation-gates.md)作为独立工作流先完成其 Spec、G4 冻结设计、G5 技术映射和 G6 Plan；PLAN-DM-020 的负责人应在批次二结束前发起该工作流，并在批次三检查点记录其正式 Plan ID 与完成状态。未满足时不得开始 Task 10。
- 每个任务只提交自身文件，commit message 使用简体中文；不得提交 `.superpowers/`、测试输出、缓存、`web/dist/` 或应用数据。
- 每个 Task 都必须在 `changelog.md` 当前日期章节追加可核验记录并与该 Task 同次提交；Task 12 只负责最终门禁和状态收口，不代替 Task 1～11 的逐次变更记录。

## 追踪矩阵（G6 依据）

| ID | Spec/Architecture 要求 | Demo/设计证据 | 实施任务 | 自动测试 | 设计 QA | 真实验收 | 初始状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EP-01 | 固定索引、随包清单、拒绝动态导入（ARCH §4） | 独立入口 | 1、12 | `test_extension_manifest.py`、打包静态检查 | G8 导航 | G9 包内清单 | 已覆盖 |
| EP-02 | 生命周期、启停持久化、故障隔离、调用排空（ARCH §5） | 停用/不兼容状态 | 1～3 | registry/store/API 单测 | G8 停用态 | G9 启停 | 已覆盖 |
| EP-03 | 最小 Capability 与短生命周期上下文（ARCH §6） | 字段浏览器 | 4、6 | capability/snapshot 单测 | — | 核心回归 | 已覆盖 |
| EP-04 | 宿主管理页面贡献与统一动作端点（ARCH §7） | 独立图纸目录页 | 3、6、10 | API + E2E | G8 | G9 | 已覆盖 |
| EP-05 | 扩展设置、工作区偏好及升级隔离（ARCH §8） | 模板栏 | 2、5、11 | store/template/API/E2E | G8 | 重启复验 | 已覆盖 |
| EP-06 | 一次性保存授权、目标漂移、用途隔离（ARCH §9.1） | 模拟另存为 | 8、9、11 | grant/shell/API/E2E | G8 反馈 | G9 原生对话框 | 已覆盖 |
| EP-07 | 原子保存和失败清理（ARCH §9.2） | 导出状态 | 8、9 | 故障注入集成测试 | — | G9 覆盖/漂移 | 已覆盖 |
| EP-08 | Artifact 后台登记和可用性派生（ARCH §9.3） | 成功页隐藏技术字段 | 2、8、9 | store/API 测试 | G8 成功反馈 | 文件移动/修改 | 已覆盖 |
| SC-01 | 固有三字段与 basename（SPEC §4.1） | 默认模板 | 4～7 | snapshot/expression/workbook | G8 默认态 | Excel 回读 | 已覆盖 |
| SC-02 | 两作用域、自定义属性、转义与保留名（SPEC §4.2） | 字段插入 | 4～6、11 | parser/binding/E2E | G8 编辑态 | — | 已覆盖 |
| SC-03 | 缺定义阻断、缺值警告并保留分隔符（SPEC §4.3） | 兼容/警告状态 | 5、6、11 | preview/E2E | G8 错误态 | — | 已覆盖 |
| SC-04 | 受限表达式语法、规范 token、无代码执行（SPEC §5） | 表达式编辑 | 5 | 表驱动安全测试 | — | — | 已覆盖 |
| SC-05 | 最多 100 个用户模板；每模板 1～50 列；模板名 1～80、列名 1～100、表达式 ≤1024 字符（SPEC §5.3） | 多列编辑 | 5、11 | validation/E2E | G8 极限态 | — | 已覆盖 |
| SC-06 | 内置默认模板不可变、用户模板 CRUD/冲突/兼容（SPEC §6） | 保存/另存/删除 | 2、5、11 | repository/API/E2E | G8 模板态 | 重启复验 | 已覆盖 |
| SC-07 | 未保存保护和工作区只记已保存模板（SPEC §3.2） | 三选一确认 | 10、11 | E2E | G8 | G9 关闭工作区 | 已覆盖 |
| SC-08 | 预览 20 行、摘要、空集可执行、漂移重预览（SPEC §8） | 预览/空集 | 6、9、11 | preview/API/E2E | G8 | — | 已覆盖 |
| SC-09 | 单工作表、文本值、冻结/筛选、禁止公式等（SPEC §9） | — | 7、9 | openpyxl 回读 | — | Excel 打开 | 已覆盖 |
| SC-10 | 原生另存为、取消、成功路径及打开文件夹（SPEC §10） | 模拟保存 | 8、9、11 | shell/API/E2E | G8 | G9 | 已覆盖 |
| SC-11 | 7 个 `SHEET_CATALOG_*` 目录码与 `REPREVIEW_REQUIRED`、`SAVE_GRANT_INVALID`、`EXPORT_DESTINATION_CHANGED`、`ARTIFACT_WRITE_FAILED`；日志关联身份但不含敏感值/完整路径（SPEC §11～12） | 可见正文错误 | 3、5、8、9、11 | API/log tests/E2E | G8 | G9 失败恢复 | 已覆盖 |
| UX-01 | 键盘、焦点、Esc、非颜色状态（SPEC §13） | 冻结 Demo | 10～12 | Playwright 语义与焦点断言 | G8 | G9 | 已覆盖 |
| UX-02 | 浅深主题、最小视口、200% 与受控横滚（SPEC §13） | 两张冻结截图 | 11、12 | Playwright 尺寸断言 | 同状态截图 | G9 | 已覆盖 |
| UX-03 | 中英文文案、错误和原生对话框契约（SPEC §13、ARCH-DM-005） | 中文冻结基准 + 英文伸长规则 | 3、8、10～12 | key 对称/缺键/API/E2E | G8 中英文 | G9 原生对话框 | 已覆盖（批次四有已知前置） |
| QA-01 | 只读不产生工程副作用，全新/既有迁移，核心不回退（SPEC §15） | — | 2、4、9、12 | pytest/Alembic/e2e | G8 | G9 | 已覆盖 |

---

## 批次一：宿主可发现、列出和启停内置扩展

批次演示结果：API 能列出 `dst-manager.sheet-catalog` 的版本、状态和编译期页面贡献；启停跨重启持久化，坏清单或工厂失败不影响健康端点和核心 API。

### Task 1：扩展契约、固定索引与生命周期注册表

**Files**

- Create: `src/dst_manager/extensions/__init__.py`
- Create: `src/dst_manager/extensions/contracts.py`
- Create: `src/dst_manager/extensions/manifest.py`
- Create: `src/dst_manager/extensions/registry.py`
- Create: `src/dst_manager/extensions/builtin/__init__.py`
- Create: `src/dst_manager/extensions/builtin/index.py`
- Create: `src/dst_manager/extensions/builtin/sheet_catalog/manifest.yaml`
- Create: `src/dst_manager/extensions/builtin/sheet_catalog/extension.py`（本任务仅最小生命周期空壳）
- Test: `tests/unit/test_extension_manifest.py`
- Test: `tests/unit/test_extension_registry.py`
- Modify: `changelog.md`

**Interfaces（Produces）**

```python
HOST_CONTRACT = 1

@dataclass(frozen=True, slots=True)
class UiContribution:
    contribution_id: str
    kind: Literal["workspace_page"]
    route_key: str

class Extension(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...

@dataclass(frozen=True, slots=True)
class ExtensionActionManifest:
    action_id: str
    output_kind: Literal["xlsx"] | None
    media_type: str | None

@dataclass(frozen=True, slots=True)
class ExtensionManifest:
    extension_id: str
    version: str
    host_contract: int
    enabled_by_default: bool
    name_key: str
    description_key: str
    required_capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    ui_contributions: tuple[UiContribution, ...]
    actions: tuple[ExtensionActionManifest, ...]
    settings_schema: int

@dataclass(frozen=True, slots=True)
class BuiltinExtensionEntry:
    manifest_resource: str
    factory: Callable[[], Extension]

@dataclass(frozen=True, slots=True)
class ExtensionDescriptor:
    manifest: ExtensionManifest
    status: Literal["DISCOVERED", "DISABLED", "STARTING", "AVAILABLE", "WAITING_DEPENDENCY", "INCOMPATIBLE", "FAILED", "STOPPING", "STOPPED"]
    error_code: str | None

@dataclass(frozen=True, slots=True)
class ExtensionInvocation:
    invocation_id: str
    extension: Extension
    manifest: ExtensionManifest

class ExtensionRegistry:
    def discover(self, entries: Sequence[BuiltinExtensionEntry]) -> None: ...
    def list(self) -> tuple[ExtensionDescriptor, ...]: ...
    def set_enabled(self, extension_id: str, enabled: bool) -> ExtensionDescriptor: ...
    @contextmanager
    def invoke(self, extension_id: str, action_id: str) -> Iterator[ExtensionInvocation]: ...
```

- [ ] **Step 1：写失败测试。** 覆盖正确清单、`name_key`/`description_key` 必填、动作 ID 唯一、候选成果动作必须声明 `output_kind=xlsx` 和固定 XLSX MIME、未知输出类型拒绝、缺字段/未知字段、非法 SemVer、非 `builtin`、重复 ID、宿主契约不匹配、工厂启动失败、默认启用/停用、停用先拒绝新调用再等待已进入的同步调用、清理失败进入 `FAILED`；断言清单不能提供模块/脚本/命令字段。已知但当前不可用的必需能力进入 `WAITING_DEPENDENCY`，未知能力或宿主契约不匹配进入 `INCOMPATIBLE`。
- [ ] **Step 2：运行红灯。** `uv run pytest tests/unit/test_extension_manifest.py tests/unit/test_extension_registry.py -q`，预期因 `dst_manager.extensions` 尚不存在而失败。
- [ ] **Step 3：最小实现。** Pydantic 清单模型使用 `extra="forbid"`；固定索引直接引用工厂，不从 YAML 导入模块；注册表逐条捕获错误并生成稳定诊断，使用 `Condition` 维护活动同步调用数；首期拒绝后台资源注册。
- [ ] **Step 4：运行绿灯。** 重跑 Step 2，并运行 `uv run ruff check src/dst_manager/extensions tests/unit/test_extension_manifest.py tests/unit/test_extension_registry.py`。
- [ ] **Step 5：记录并提交。** 在 `changelog.md` 追加清单、动作输出策略和生命周期验证结果；只暂存本任务涉及的文件，提交 `git commit -m "建立内置扩展清单与生命周期注册表"`。

### Task 2：扩展状态、设置、偏好和 Artifact 持久化

**Files**

- Create: `migrations/versions/0006_dm020_extension_platform.py`
- Create: `src/dst_manager/infrastructure/persistence/extensions.py`
- Modify: `src/dst_manager/infrastructure/persistence/database.py`（只更新最新 revision 常量）
- Modify: `migrations/env.py`（确保扩展 ORM 表进入 metadata）
- Test: `tests/unit/test_extension_persistence.py`
- Modify: `tests/unit/test_database.py`
- Modify: `changelog.md`

**Interfaces（Produces）**

```python
@dataclass(frozen=True, slots=True)
class VersionedJson:
    schema_version: int
    revision: int
    value: dict[str, object]

@dataclass(frozen=True, slots=True)
class ExtensionStateRecord:
    extension_id: str
    enabled: bool
    last_loaded_version: str | None
    last_error_code: str | None
    updated_at: datetime

@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    extension_id: str
    extension_version: str
    workspace_id: str
    source_revision_id: str
    kind: str
    media_type: str
    management_relation: Literal["external"]
    output_path: str
    file_name: str
    size_bytes: int
    sha256: str
    created_at: datetime

class ExtensionStore:
    def get_state(self, extension_id: str) -> ExtensionStateRecord | None: ...
    def put_state(self, record: ExtensionStateRecord) -> None: ...
    def get_settings(self, extension_id: str) -> VersionedJson | None: ...
    def put_settings(self, extension_id: str, schema_version: int,
                     value: dict[str, object], expected_revision: int) -> VersionedJson: ...
    def get_preference(self, workspace_id: str, extension_id: str) -> VersionedJson | None: ...
    def put_preference(self, workspace_id: str, extension_id: str,
                       schema_version: int, value: dict[str, object]) -> VersionedJson: ...
    def create_artifact(self, record: ArtifactRecord) -> ArtifactRecord: ...
    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None: ...
```

- [ ] **Step 1：写失败测试。** 验证四表唯一约束、JSON 往返、设置乐观修订冲突不覆盖旧值、工作区与扩展联合隔离、Artifact 必填来源字段；验证删除模板不会删除历史 Artifact；验证从空库和迁移 `0005` 的既有库升级到 `0006`，并更新“已发布迁移不可变”哈希夹具。
- [ ] **Step 2：运行红灯。** `uv run pytest tests/unit/test_extension_persistence.py tests/unit/test_database.py -q`，预期最新 revision/新表断言失败。
- [ ] **Step 3：最小实现。** 迁移创建 `extension_states`、`extension_settings`、`workspace_extension_preferences`、`artifacts`；授权不持久化。仓储接收现有 session factory，不把 Session 交给扩展，不向已 782 行的 `Database` 追加业务 CRUD。
- [ ] **Step 4：运行绿灯。** 重跑 Step 2，并执行 `uv run alembic upgrade head`、`uv run ruff check migrations src/dst_manager/infrastructure/persistence tests/unit/test_extension_persistence.py`。
- [ ] **Step 5：记录并提交。** 在 `changelog.md` 追加迁移、仓储及实际通过命令；只暂存本任务涉及的文件，提交 `git commit -m "新增扩展设置与成果元数据迁移"`。

### Task 3：平台编排、统一管理 API 与结构化错误

**Files**

- Create: `src/dst_manager/application/extensions/__init__.py`
- Create: `src/dst_manager/application/extensions/runtime.py`
- Create: `src/dst_manager/interfaces/extension_contracts.py`
- Create: `src/dst_manager/interfaces/extension_api.py`
- Modify: `src/dst_manager/interfaces/api.py`（仅装配 router、平台和异常处理）
- Test: `tests/integration/test_extension_api.py`
- Modify: `changelog.md`

**Interfaces（Produces）**

```text
GET   /api/extensions
PATCH /api/extensions/{extension_id}/state
GET   /api/extensions/{extension_id}/settings
PUT   /api/extensions/{extension_id}/settings
GET   /api/extensions/{extension_id}/workspaces/{workspace_id}/preferences
PUT   /api/extensions/{extension_id}/workspaces/{workspace_id}/preferences
POST  /api/extensions/{extension_id}/actions/{action_id}/preview
POST  /api/extensions/{extension_id}/actions/{action_id}/execute
GET   /api/artifacts/{artifact_id}
```

```python
ExtensionPlatformErrorCode = Literal[
    "EXTENSION_NOT_FOUND",
    "EXTENSION_DISABLED",
    "EXTENSION_INCOMPATIBLE",
    "EXTENSION_CAPABILITY_UNAVAILABLE",
    "EXTENSION_SETTINGS_INVALID",
    "EXTENSION_ACTION_NOT_FOUND",
    "SAVE_GRANT_INVALID",
    "EXPORT_DESTINATION_CHANGED",
    "REPREVIEW_REQUIRED",
    "ARTIFACT_WRITE_FAILED",
]

class ExtensionErrorResponse(ContractModel):
    code: ExtensionPlatformErrorCode | str
    message_key: str
    params: dict[str, str | int]
    message: str
```

- [ ] **Step 1：写失败集成测试。** 断言列表/启停/重启持久化、未知扩展、禁用动作、错误清单隔离、设置 `expected_revision` 冲突、偏好不存在默认值、Artifact 404；逐一断言上列平台错误码、稳定 `message_key` 与结构化 `params`；断言 OpenAPI 有全部端点且错误包含 `code/message_key/params/message`。
- [ ] **Step 2：钉住启动顺序。** 使用记录事件的 publisher/database/registry 测试替身，断言顺序严格为数据库迁移完成 → 发布恢复完成 → `registry.discover()`；清单或工厂失败后 `/api/health` 与核心工作区 API 仍可调用。
- [ ] **Step 3：运行红灯。** `uv run pytest tests/integration/test_extension_api.py -q`，预期端点 404，启动顺序断言也因 registry 未接线失败。
- [ ] **Step 4：最小实现。** `ExtensionRuntime` 组合 registry/store；统一 router 校验扩展状态、声明动作和请求模型。`create_app()` 只在现有 `DstManagerService` 完成数据库迁移与发布恢复后创建/接收 runtime、调用 discover 并 `include_router()`；任何单扩展发现失败不能影响 `/api/health`。
- [ ] **Step 5：运行绿灯。** 重跑 Step 3，再运行 `uv run pytest tests/integration/test_api.py tests/integration/test_api_settings.py -q` 和 `uv run ruff check src/dst_manager/application/extensions src/dst_manager/interfaces`。
- [ ] **Step 6：批次检查点。** 手工调用健康、扩展列表和启停端点；确认禁用全部扩展后三个核心工作区 API 仍通过。更新计划“实际验证”，记录偏差后停止审查。
- [ ] **Step 7：记录并提交。** 在 `changelog.md` 追加统一 API、稳定错误结构和启动顺序验证；只暂存本任务涉及的文件，提交 `git commit -m "接入内置扩展管理与统一动作接口"`。

---

## 批次二：模板可保存且能预览真实目录数据

批次演示结果：使用 API 打开图纸集后，默认三列和用户表达式模板可生成最多 20 行真实预览；跨图纸集缺定义明显阻断，缺值按字段和图纸数警告。

### Task 4：裁剪的冻结工作区快照与 Capability Broker

**Files**

- Create: `src/dst_manager/extensions/snapshots.py`
- Create: `src/dst_manager/extensions/capabilities.py`
- Create: `src/dst_manager/infrastructure/extension_workspace.py`
- Test: `tests/unit/test_extension_snapshot.py`
- Modify: `tests/integration/test_api.py`（只读副作用回归）
- Modify: `changelog.md`

**Interfaces（Produces）**

```python
@dataclass(frozen=True, slots=True)
class SnapshotProperty:
    canonical_name: str
    value: str

@dataclass(frozen=True, slots=True)
class SnapshotPropertyScope:
    custom_property_definitions: tuple[str, ...]
    custom_properties: tuple[SnapshotProperty, ...]

@dataclass(frozen=True, slots=True)
class SheetSnapshot:
    sheet_id: str
    number: str
    title: str
    file_name: str
    custom_property_definitions: tuple[str, ...]
    custom_properties: tuple[SnapshotProperty, ...]

@dataclass(frozen=True, slots=True)
class FieldDefinition:
    scope: Literal["sheetset", "sheet"]
    canonical_name: str
    builtin: bool

@dataclass(frozen=True, slots=True)
class FieldCatalog:
    sheetset: tuple[FieldDefinition, ...]
    sheet: tuple[FieldDefinition, ...]

@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    workspace_id: str
    revision_id: str
    sheetset: SnapshotPropertyScope
    sheets: tuple[SheetSnapshot, ...]

class CapabilityBroker:
    def context(self, extension_id: str, workspace_id: str,
                required_revision_id: str) -> ExtensionContext: ...

class ExtensionContext:
    def workspace_snapshot(self) -> WorkspaceSnapshot: ...
    def close(self) -> None: ...
```

- [ ] **Step 1：写失败测试。** 构造含 `C:\工程\A.dwg`、`folder/A.dwg`、声明但无值属性、实际但未声明属性和大小写重复属性的工作区；断言顺序、规范名称、两作用域、basename、不可变/可序列化、无 `root/dst_path/resolved_path`。上下文关闭后调用失败，未声明能力被拒绝。
- [ ] **Step 2：写只读回归。** 记录临时 DST/DWG 的 SHA-256、mtime 和工程目录树，构建快照后完全相等且不存在 `.dst-manager/`；应用数据库只读查询不发生 workspace upsert。
- [ ] **Step 3：运行红灯。** `uv run pytest tests/unit/test_extension_snapshot.py tests/integration/test_api.py -q`，预期新模块缺失。
- [ ] **Step 4：最小实现。** 基础设施 reader 从已登记 workspace row 解码当前 DST，但不调用 `open_workspace()`/`upsert_workspace()`；snapshot builder 复用 `property_definitions_from_document()`，跨两种分隔符裁 basename；broker 按清单与宿主 allowlist 交集发能力。
- [ ] **Step 5：运行绿灯并记录。** 重跑 Step 3、运行 Ruff；在 `changelog.md` 追加快照字段裁剪、路径不泄漏和只读不变量结果。
- [ ] **Step 6：提交。** 只暂存本任务涉及的文件，提交 `git commit -m "提供扩展只读快照与最小能力上下文"`。

### Task 5：受限表达式、模板校验和扩展设置语义

**Files**

- Create: `src/dst_manager/extensions/builtin/sheet_catalog/expressions.py`
- Create: `src/dst_manager/extensions/builtin/sheet_catalog/errors.py`
- Create: `src/dst_manager/extensions/builtin/sheet_catalog/templates.py`
- Test: `tests/unit/test_sheet_catalog_expressions.py`
- Test: `tests/unit/test_sheet_catalog_templates.py`
- Modify: `changelog.md`

**Interfaces（Produces）**

```python
SheetCatalogErrorCode = Literal[
    "SHEET_CATALOG_EXPRESSION_INVALID",
    "SHEET_CATALOG_FIELD_UNDEFINED",
    "SHEET_CATALOG_VALUE_MISSING",
    "SHEET_CATALOG_COLUMN_DUPLICATE",
    "SHEET_CATALOG_TEMPLATE_LIMIT",
    "SHEET_CATALOG_TEMPLATE_CONFLICT",
    "SHEET_CATALOG_XLSX_INVALID",
]

@dataclass(frozen=True, slots=True)
class LiteralToken:
    value: str

@dataclass(frozen=True, slots=True)
class FieldToken:
    scope: Literal["sheetset", "sheet"]
    name: str
    source_start: int

ExpressionToken = LiteralToken | FieldToken

@dataclass(frozen=True, slots=True)
class BoundFieldToken:
    scope: Literal["sheetset", "sheet"]
    canonical_name: str
    builtin: bool

@dataclass(frozen=True, slots=True)
class BoundExpression:
    tokens: tuple[LiteralToken | BoundFieldToken, ...]

@dataclass(frozen=True, slots=True)
class TemplateColumn:
    column_id: UUID
    header: str
    expression: str

@dataclass(frozen=True, slots=True)
class SheetCatalogTemplate:
    template_id: UUID | None
    name: str
    schema_version: Literal[1]
    columns: tuple[TemplateColumn, ...]

@dataclass(frozen=True, slots=True)
class TemplateCollection:
    revision: int
    builtin: SheetCatalogTemplate
    user_templates: tuple[SheetCatalogTemplate, ...]

@dataclass(frozen=True, slots=True)
class ValidatedTemplate:
    template: SheetCatalogTemplate
    parsed_columns: tuple[tuple[ExpressionToken, ...], ...]

def parse_expression(source: str) -> tuple[ExpressionToken, ...]: ...
def bind_expression(tokens: tuple[ExpressionToken, ...],
                    fields: FieldCatalog) -> BoundExpression: ...
def evaluate_expression(expression: BoundExpression,
                        sheetset: SnapshotPropertyScope,
                        sheet: SheetSnapshot) -> str: ...
def field_reference(scope: str, canonical_name: str) -> str: ...

DEFAULT_TEMPLATE: SheetCatalogTemplate
def validate_template(template: SheetCatalogTemplate) -> ValidatedTemplate: ...
def load_templates(settings: VersionedJson | None) -> TemplateCollection: ...
def save_templates(collection: TemplateCollection,
                   expected_revision: int) -> dict[str, object]: ...
def delete_template(collection: TemplateCollection,
                    template_id: UUID) -> TemplateCollection: ...
```

- [ ] **Step 1：写 parser 失败测试。** 覆盖字面量、`{{`/`}}`、点号字段、JSON 字符串字段、中文、空表达式、未闭合/多余内容/非法转义/未知作用域/嵌套、函数/Jinja/Python payload；断言错误带 0-based 字符位置且实现源码不含 `eval(`、`exec(`、Jinja。
- [ ] **Step 2：写绑定/求值失败测试。** 固有 `sheet.number/title/file_name` 优先；自定义保留名只能方括号引用；大小写绑定到规范名称；缺定义结构化报错；缺值为空但 `-` 等字面量保留。
- [ ] **Step 3：写模板失败测试。** 默认三列不可改删；用户模板 UUID/column UUID 稳定；最多 100 个用户模板、每个模板 1～50 列、模板名 1～80 字符、输出列名 1～100 字符、单个表达式最多 1024 字符，输出列名和模板名均按 `casefold()` 唯一；保存不要求兼容当前图纸集；删除当前用户模板后选择回退内置默认模板且历史 Artifact 不受影响；未知高 schema 保留原 JSON 并诊断。
- [ ] **Step 4：写错误词汇表失败测试。** 对上列 7 个目录错误码逐一断言固定 `message_key`、允许的结构化参数和用户结果；`SHEET_CATALOG_TEMPLATE_CONFLICT` 必须保留本地编辑，刷新服务端模板修订后允许另存为或按新修订重试；`VALUE_MISSING` 是允许执行的 warning，其余对应阻断语义按 SPEC §11 固定。
- [ ] **Step 5：运行红灯。** `uv run pytest tests/unit/test_sheet_catalog_expressions.py tests/unit/test_sheet_catalog_templates.py -q`。
- [ ] **Step 6：最小实现。** 手写有限状态扫描器并解析 JSON string，不引入通用模板引擎；规范 token 用稳定 dataclass；模板 JSON 严格验证，内置模板由代码常量合并且不写数据库；错误工厂只接受词汇表中定义的参数。
- [ ] **Step 7：运行绿灯并记录。** 重跑 Step 5、Ruff；在 `changelog.md` 记录具体限制值、错误码、冲突恢复和删除回退验证。
- [ ] **Step 8：提交。** 只暂存本任务涉及的文件，提交 `git commit -m "实现图纸目录受限表达式与模板规则"`。

### Task 6：图纸目录预览动作、兼容性与确定性摘要

**Files**

- Modify: `src/dst_manager/extensions/builtin/sheet_catalog/extension.py`
- Create: `src/dst_manager/extensions/builtin/sheet_catalog/preview.py`
- Modify: `src/dst_manager/application/extensions/runtime.py`
- Modify: `src/dst_manager/interfaces/extension_contracts.py`
- Test: `tests/unit/test_sheet_catalog_preview.py`
- Modify: `tests/integration/test_extension_api.py`
- Modify: `changelog.md`

**Interfaces（Produces）**

```python
@dataclass(frozen=True, slots=True)
class SheetCatalogPreviewRequest:
    workspace_id: str
    base_revision_id: str
    template: SheetCatalogTemplate

@dataclass(frozen=True, slots=True)
class SheetCatalogDiagnostic:
    code: SheetCatalogErrorCode
    message_key: str
    params: dict[str, str | int]
    column_id: UUID | None
    source_position: int | None

@dataclass(frozen=True, slots=True)
class SheetCatalogPreview:
    normalized_template: SheetCatalogTemplate
    field_catalog: FieldCatalog
    errors: tuple[SheetCatalogDiagnostic, ...]
    warnings: tuple[SheetCatalogDiagnostic, ...]
    rows: tuple[tuple[str, ...], ...]
    total_rows: int
    preview_digest: str
    executable: bool

class SheetCatalogExtension:
    def preview(self, context: ExtensionContext,
                request: SheetCatalogPreviewRequest) -> SheetCatalogPreview: ...

def preview_digest(workspace_id: str, revision_id: str,
                   template_schema: int, normalized_columns: Sequence[...],
                   extension_version: str, action_id: str) -> str: ...
```

- [ ] **Step 1：写失败测试。** 默认模板真实行、图纸集/图纸组合、最多 20 行和总数、空图纸集 executable、缺定义阻断、缺值字段与受影响图纸数、重复列/超限、Windows/Posix basename；摘要对任一绑定项变化敏感且相同输入稳定。
- [ ] **Step 2：写 API 失败测试。** `POST .../actions/export-xlsx/preview` 重复提交模板快照；未知动作、禁用扩展、工作区/修订不匹配使用稳定错误；响应含字段目录、规范模板、错误/警告、20 行、总数、digest、executable。注入工作区偏好保存失败时，当前模板预览仍成功且返回可诊断的非阻断 warning，不能把偏好失败升级为动作失败。
- [ ] **Step 3：运行红灯。** `uv run pytest tests/unit/test_sheet_catalog_preview.py tests/integration/test_extension_api.py -q`。
- [ ] **Step 4：最小实现。** extension 只从 context 取 snapshot；按列解析/绑定后一次性遍历图纸，缺值统计不记录值；canonical JSON 使用固定键与紧凑分隔符后 SHA-256。
- [ ] **Step 5：运行绿灯。** 重跑 Step 3；运行 Task 4～6 全部单测、Ruff 和 `uv run pytest tests/integration/test_api.py -q`。
- [ ] **Step 6：批次检查点。** 用临时夹具请求默认/不兼容/空集预览并保存响应证据；确认未产生项目文件或新修订；检查 ARCH-DM-005 独立工作流是否已进入 G0～G6，未进入则在本计划“实际验证”登记负责人和下一检查点。
- [ ] **Step 7：记录并提交。** 在 `changelog.md` 追加真实预览、摘要和偏好失败降级结果；只暂存本任务涉及的文件，提交 `git commit -m "完成图纸目录真实数据预览动作"`，停止审查。

---

## 批次三：用户选择路径并安全生成 XLSX

批次演示结果：桌面壳弹出固定 XLSX 另存为，取消无副作用；确认后生成经回读验证的文件并后台登记 Artifact，目标漂移或故障不覆盖目标、不留半文件。

### Task 7：openpyxl 候选工作簿生成与回读验证

**Files**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/dst_manager/extensions/builtin/sheet_catalog/workbook.py`
- Test: `tests/unit/test_sheet_catalog_workbook.py`
- Modify: `changelog.md`

**Interfaces（Produces）**

```python
@dataclass(frozen=True, slots=True)
class WorkbookSummary:
    worksheet_name: Literal["图纸目录"]
    headers: tuple[str, ...]
    data_rows: int

def write_candidate(path: Path, headers: Sequence[str],
                    rows: Iterable[Sequence[str]]) -> WorkbookSummary: ...
def validate_candidate(path: Path, expected_headers: Sequence[str],
                       expected_rows: int) -> WorkbookSummary: ...
```

- [ ] **Step 1：添加依赖。** `uv add "openpyxl>=3.1,<4"`，审查 `pyproject.toml` 与 `uv.lock` 只出现预期依赖变化。
- [ ] **Step 2：写失败测试。** 回读断言唯一可见“图纸目录”、首行、`freeze_panes == "A2"`、auto_filter、顺序、所有 data_type 为字符串、`001` 保留、以 `=+-@` 开头不成为公式、空集仅表头、列宽上限与换行；伪造多表/隐藏表/错误表头/行数/外链候选被拒绝。
- [ ] **Step 3：运行红灯。** `uv run pytest tests/unit/test_sheet_catalog_workbook.py -q`，预期模块缺失。
- [ ] **Step 4：最小实现。** 只写受控样式和值；保存后以 `data_only=False/read_only=False` 重开并验证禁止特性；不创建宏、公式、图表、链接、隐藏列/表。
- [ ] **Step 5：运行绿灯并记录。** 重跑 Step 3、`uv lock --check`、Ruff；在 `changelog.md` 追加 openpyxl 依赖、文本单元格和候选回读验证结果。
- [ ] **Step 6：提交。** 只暂存本任务涉及的文件，提交 `git commit -m "新增图纸目录 XLSX 生成与回读校验"`。

### Task 8：一次性保存授权、ShellBridge 和宿主原子成果发布

**Files**

- Create: `src/dst_manager/extensions/save_grants.py`
- Create: `src/dst_manager/extensions/artifacts.py`
- Modify: `src/dst_manager/interfaces/shell.py`
- Modify: `web/src/api/shell.ts`
- Test: `tests/unit/test_save_grants.py`
- Create: `tests/unit/test_artifact_exporter.py`
- Modify: `tests/unit/test_shell.py`
- Modify: `changelog.md`

**Interfaces（Produces）**

```python
@dataclass(frozen=True, slots=True)
class TargetBaseline:
    existed: bool
    device: int | None
    inode: int | None
    size_bytes: int | None
    modified_ns: int | None
    sha256: str | None

@dataclass(frozen=True, slots=True)
class SaveGrantReceipt:
    save_grant_id: str
    file_name: str
    expires_at: datetime

@dataclass(frozen=True, slots=True)
class ConsumedSaveGrant:
    save_grant_id: str
    extension_id: str
    action_id: str
    workspace_id: str
    target: Path
    baseline: TargetBaseline

@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    extension_id: str
    extension_version: str
    workspace_id: str
    source_revision_id: str
    kind: Literal["sheet-catalog"]
    media_type: Literal["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]

class SaveGrantStore:
    def create(self, extension_id: str, action_id: str, workspace_id: str,
               target: Path, ttl_seconds: int = 300) -> SaveGrantReceipt: ...
    def consume(self, save_grant_id: str, extension_id: str,
                action_id: str, workspace_id: str) -> ConsumedSaveGrant: ...

class ArtifactExporter:
    def publish(self, grant: ConsumedSaveGrant, candidate: Path,
                metadata: ArtifactMetadata) -> ArtifactRecord: ...

class ShellBridge:
    def request_extension_save(self, extension_id: str, action_id: str,
                               workspace_id: str) -> dict: ...
```

- [ ] **Step 1：写授权失败测试。** 随机 ID、固定 `.xlsx` 后缀、TTL、原子消费；伪造/过期/复用/扩展/动作/工作区错配拒绝；记录目标存在性、规范路径、文件身份和 SHA-256；目标漂移拒绝。使用 `ThreadPoolExecutor` 断言同一授权只有一个消费者成功，两个不同授权可并发导出且不取得工作区写锁。
- [ ] **Step 2：写桥失败测试。** 为现有 ShellBridge 新增 pywebview `SAVE_DIALOG` 接线；只允许 registry 中 `ExtensionActionManifest.output_kind == "xlsx"` 且 MIME 匹配的动作；桥不接受前端建议名，宿主从当前可信工作区快照严格生成 `<图纸集名称>-图纸目录.xlsx`，再清理 Windows 非法字符并限制长度；对话框固定 XLSX filter；取消返回 `{ok:true,value:null}` 且不创建授权；前端不收到目标绝对路径。
- [ ] **Step 3：写发布故障注入测试。** 覆盖候选不存在/验证失败、目标目录不可写、复制/flush/fsync/replace/哈希/Artifact 插入各阶段；断言旧目标字节保持或新目标不存在、临时文件清理、失败无 Artifact。成功时同卷临时文件 + `os.replace`，最终哈希/大小/路径登记。捕获日志并断言关联 invocation ID、扩展 ID、扩展版本、workspace ID、source revision ID；普通日志不含求值属性值或完整输出路径。
- [ ] **Step 4：运行红灯。** `uv run pytest tests/unit/test_save_grants.py tests/unit/test_artifact_exporter.py tests/unit/test_shell.py -q`。
- [ ] **Step 5：最小实现。** 授权仅进程内保存并用锁消费；ShellBridge 从可信上下文校验 workspace，并新增固定 `SAVE_DIALOG` 调用；publisher 在目标目录创建唯一临时文件，复制、flush、尽力 fsync、重新核对基准再 replace；异常 finally 清理。日志关联 invocation ID、扩展 ID/版本、workspace ID、source revision ID 和成功后的 artifact ID，不记录求值属性值或完整输出路径。
- [ ] **Step 6：运行绿灯并记录。** 重跑 Step 4 和 Ruff；在 `changelog.md` 追加新增保存对话框、授权并发/漂移和原子失败清理验证。
- [ ] **Step 7：提交。** 只暂存本任务涉及的文件，提交 `git commit -m "实现一次性保存授权与原子成果发布"`。

### Task 9：执行动作、Artifact 查询和桌面共同装配

**Files**

- Modify: `src/dst_manager/extensions/builtin/sheet_catalog/extension.py`
- Modify: `src/dst_manager/application/extensions/runtime.py`
- Modify: `src/dst_manager/interfaces/extension_api.py`
- Modify: `src/dst_manager/interfaces/extension_contracts.py`
- Modify: `src/dst_manager/interfaces/shell.py`（`run_desktop` 共同注入 store）
- Modify: `tests/integration/test_extension_api.py`
- Create: `tests/integration/test_sheet_catalog_export.py`
- Modify: `changelog.md`

**Interfaces（Consumes/Produces）**

```python
@dataclass(frozen=True, slots=True)
class SheetCatalogExecuteRequest:
    workspace_id: str
    base_revision_id: str
    template: SheetCatalogTemplate
    preview_digest: str
    save_grant_id: str

@dataclass(frozen=True, slots=True)
class SheetCatalogExecuteResponse:
    artifact_id: str
    file_name: str
    output_path: str
    warnings: tuple[SheetCatalogDiagnostic, ...]

@dataclass(frozen=True, slots=True)
class ArtifactProposalDirectory:
    root: Path  # 只指向宿主分配的应用临时目录

@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    path: Path
    media_type: str
    expected_headers: tuple[str, ...]
    expected_rows: int

class SheetCatalogExtension:
    def execute(self, context: ExtensionContext,
                request: SheetCatalogExecuteRequest,
                proposal_directory: ArtifactProposalDirectory) -> CandidateArtifact: ...

class ExtensionRuntime:
    def execute_action(self, extension_id: str, action_id: str,
                       request: SheetCatalogExecuteRequest) -> SheetCatalogExecuteResponse: ...
```

- [ ] **Step 1：写失败集成测试。** 预览后执行成功并回读 XLSX/Artifact；未保存模板也能执行；修订、模板、扩展版本、能力或动作摘要变化返回 `REPREVIEW_REQUIRED`；无效/漂移授权分别报错；候选失败不登记；成功响应不含 sha256/source_revision/extension_version，Artifact 查询含后台字段和 `AVAILABLE/MISSING/CHANGED`。
- [ ] **Step 2：写只读不变量测试。** 整个预览→执行前后 DST/DWG hash、mtime 和工程目录树不变；数据库无 job、revision 或 workspace write lock 新记录；应用临时候选清空。
- [ ] **Step 3：运行红灯。** `uv run pytest tests/integration/test_sheet_catalog_export.py tests/integration/test_extension_api.py -q`。
- [ ] **Step 4：最小实现。** execute 重新构建 snapshot、重新解析模板并核对 digest；为扩展分配应用数据目录下唯一临时目录；扩展只写候选；宿主回读、消费 grant、原子保存、登记 Artifact，finally 清理候选。`run_desktop()` 创建同一个 `SaveGrantStore` 注入 API runtime 与 bridge。
- [ ] **Step 5：运行绿灯。** 重跑 Step 3；运行 `uv run pytest tests/unit/test_database.py tests/unit/test_shell.py tests/integration/test_api.py tests/integration/test_transaction_recovery.py -q`、Ruff、Alembic。
- [ ] **Step 6：批次检查点。** 以临时目录实际导出并用 openpyxl 回读；注入目标漂移和 replace 失败；确认零半文件/零错误 Artifact。核对 ARCH-DM-005 独立工作流已具有正式 Spec、G4/G5 证据和实施 Plan，并在“实际验证”记录其 Plan ID 与状态；不满足则本计划保持 `active`、暂停 Task 10。
- [ ] **Step 7：记录并提交。** 在 `changelog.md` 追加执行摘要复核、候选隔离、Artifact 三态与只读不变量结果；只暂存本任务涉及的文件，提交 `git commit -m "贯通图纸目录导出与后台成果登记"`，停止审查。

---

## 批次四：独立页面、设计一致性、打包与验收准备

批次演示结果：打开工作区出现独立“图纸目录”标签，可完成模板管理、字段插入、兼容性修正、预览和原生导出；停用扩展后入口消失且核心三页面不受影响。

### Task 10：前端扩展贡献模型、动态标签与离开保护

**Files**

- Create: `web/src/api/extensions.ts`
- Modify: `web/src/api/contracts.ts`
- Modify: `web/src/api/openapi.json`（生成物）
- Modify: `web/src/api/schema.d.ts`（生成物）
- Create: `web/src/features/extensions/pageRegistry.ts`
- Create: `web/src/views/SheetCatalogView.vue`（只承载已加载扩展的最小页面边界与状态区域）
- Modify: `web/src/i18n/locales/zh-CN/extensions.ts`（由 ARCH-DM-005 前置实现提供）
- Modify: `web/src/i18n/locales/en-US/extensions.ts`（由 ARCH-DM-005 前置实现提供）
- Modify: `web/src/layout/TabBar.vue`
- Modify: `web/src/composables/useShellTabs.ts`
- Modify: `web/src/App.vue`（仅最小装配）
- Create: `web/tests/e2e/extensions-navigation.spec.ts`
- Modify: `changelog.md`

**Interfaces（Produces）**

```ts
export const EXTENSION_PAGE_COMPONENTS = {
  "sheet-catalog": defineAsyncComponent(() => import("../../views/SheetCatalogView.vue")),
} as const;

type TabDescriptor = {id:string; label:string; number?:string; disabled?:boolean; source:"core"|"extension"};
```

- [ ] **Step 1：核对批次前置并生成契约红灯。** 先确认 ARCH-DM-005 的唯一 i18n 实例和两语言资源装载已经存在；不存在则按全局约束暂停。随后运行 `npm --prefix web run generate:api`，确认新端点生成类型；为未知 `route_key` 写安全忽略测试，不让后端值成为动态 import 路径；为扩展名称、状态与错误 key 写中英文集合完全相同的断言。
- [ ] **Step 2：写导航失败 E2E。** 工作区加载且扩展 AVAILABLE 时显示目录标签；DISABLED/FAILED/INCOMPATIBLE 时隐藏；核心三标签顺序固定。停用当前目录页时，有未保存输入先三选一，确认后回图纸页并把焦点归还目录标签原位置的安全邻近元素。
- [ ] **Step 3：运行红灯。** `npm --prefix web run test:e2e -- tests/e2e/extensions-navigation.spec.ts --workers=1`。
- [ ] **Step 4：最小实现。** `TabBar` 接收 descriptors；`useShellTabs` 对动态列表安全校正 active 和方向键；App 只加载列表、映射受信 route key 和挂载组件，不承载目录业务状态；本任务的 `SheetCatalogView` 只提供真实的页面状态容器，业务编辑器由 Task 11 填充；无工作区不显示 workspace_page。
- [ ] **Step 5：运行绿灯并记录。** 重跑 Step 3、`npm --prefix web run check:api`、`npm --prefix web run build`；在 `changelog.md` 追加页面贡献、未知 route 防护和动态导航结果。
- [ ] **Step 6：提交。** 只暂存本任务涉及的文件，提交 `git commit -m "接入扩展页面贡献与动态标签导航"`。

### Task 11：图纸目录页面、模板编辑和导出交互

**Files**

- Create: `web/src/composables/useSheetCatalog.ts`
- Modify: `web/src/views/SheetCatalogView.vue`
- Create: `web/src/components/sheet-catalog/TemplateBar.vue`
- Create: `web/src/components/sheet-catalog/FieldBrowser.vue`
- Create: `web/src/components/sheet-catalog/ColumnEditor.vue`
- Create: `web/src/components/sheet-catalog/CompatibilitySummary.vue`
- Create: `web/src/components/sheet-catalog/CatalogPreview.vue`
- Create: `web/src/components/sheet-catalog/CatalogActions.vue`
- Modify: `web/src/i18n/locales/zh-CN/extensions.ts`
- Modify: `web/src/i18n/locales/en-US/extensions.ts`
- Create: `web/tests/e2e/fixtures/sheetCatalog.ts`
- Create: `web/tests/e2e/sheet-catalog.spec.ts`
- Modify: `changelog.md`

**Interfaces（State owner）**

```ts
export function useSheetCatalog(workspace: Ref<Workspace>) {
  // templates/currentTemplate/draft/dirty/fieldCatalog/preview/status/save/export
  // insertField(columnId, reference, selectionStart, selectionEnd)
  // guardNavigation(next): Promise<"continue"|"stay">
}
```

- [ ] **Step 1：写核心流程 E2E 红灯。** 默认三列、真实 20 行/总数、字段分组、特殊属性在当前光标位置插入 JSON 方括号语法、组合表达式 `RQ-{sheet.number}`、缺定义可见且阻断、缺值带数量但允许导出、空集可导出。
- [ ] **Step 2：写模板状态 E2E 红灯。** 内置模板编辑变未命名且只能另存；用户模板保存/另存/删除/大小写冲突/100 上限；删除当前模板需确认，成功后回到内置默认模板且历史 Artifact 查询仍存在；跨图纸集不兼容模板保留并突出缺少的 `sheetset.<name>`/`sheet.<name>`；工作区偏好只记已保存模板；切换/离开/关闭的三选一保护。模拟 `SHEET_CATALOG_TEMPLATE_CONFLICT` 时保留本地编辑，刷新服务端 revision 后明确提供“另存为”和“按新修订重试”，不能只显示泛化保存失败。
- [ ] **Step 3：写导出状态 E2E 红灯。** 无桌面壳显示可见说明并禁用；取消不改变草稿/预览；旧 preview 禁止导出；成功显示最终路径和“打开所在文件夹”，不显示 Artifact/修订/哈希；漂移、授权失效和写失败保留编辑并可重试。
- [ ] **Step 4：运行红灯。** `npm --prefix web run test:e2e -- tests/e2e/sheet-catalog.spec.ts --workers=1`。
- [ ] **Step 5：最小实现。** composable 作为唯一页面状态所有者并防抖预览；字段浏览器用 textarea selection API 插入；错误聚焦首个问题；预览横滚限制在表容器；全部用户文案、ARIA、tooltip 和错误经宿主 i18n key 渲染，中英文 key 对称；复用现有 toast/ConfirmModal/UnsavedInputDialog 和主题令牌，不复制后端最终校验规则。
- [ ] **Step 6：运行绿灯并记录。** 重跑 Step 4、`npm --prefix web run check:api`、`npm --prefix web run build`；确认新 `.vue` 文件不超过容量软上限；在 `changelog.md` 追加模板冲突恢复、删除回退、字段插入和导出状态结果。
- [ ] **Step 7：提交。** 只暂存本任务涉及的文件，提交 `git commit -m "实现图纸目录模板配置与导出页面"`。

### Task 12：响应式/可访问性、打包、G8 证据与 G9 清单

**Files**

- Modify: `web/tests/e2e/sheet-catalog.spec.ts`
- Create: `web/tests/e2e/sheet-catalog-visual-evidence.spec.ts`
- Modify: `packaging/dst-manager.spec`
- Modify: `tests/unit/test_packaging_spec.py`
- Create: `.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-design-qa.md`
- Create: `.planning/memos/dst-manager/PLAN-DM-020-sheet-catalog-g9-checklist.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-020-sheet-catalog-builtin-extension.md`
- Modify: `docs/dst-manager/specs/SPEC-DM-012-sheet-catalog-extension.md`
- Modify: `docs/dst-manager/README.md`
- Modify: `.planning/plans/dst-manager/README.md`
- Modify: `changelog.md`

- [ ] **Step 1：写响应式与键盘红灯。** 覆盖 1440×1000 浅色、900×700 深色、200% 缩放、1/50 列、长字段/值、大数据摘要；断言无整页横向溢出、主操作可见、预览区独立横滚。覆盖完整 Tab 顺序、字段 Enter/Space 插入、标签方向键、表达式错误焦点、模态 Esc/圈闭/归还以及非颜色状态文字。
- [ ] **Step 2：补打包失败测试。** `manifest.yaml` 必须进入 `datas`，openpyxl 必须可收集且许可证记录可追溯；固定索引列出的资源都存在，包中不扫描用户扩展目录。
- [ ] **Step 3：运行局部红灯并实现。** 调整专用组件样式和 `packaging/dst-manager.spec`；不得用全局 CSS 修复局部布局。运行：

```powershell
uv run pytest tests/unit/test_packaging_spec.py -q
npm --prefix web run test:e2e -- tests/e2e/extensions-navigation.spec.ts tests/e2e/sheet-catalog.spec.ts tests/e2e/sheet-catalog-visual-evidence.spec.ts --workers=1
```

- [ ] **Step 4：执行 G8。** 用与冻结 Demo 相同的虚构数据、状态、视口、主题和展开状态生成成对截图；逐项标记“一致/接受差异/缺陷”，缺陷修复后重新截图，结果写入 design QA 备忘。不能只凭 E2E 宣布视觉通过。
- [ ] **Step 5：运行完整自动验证。** 全部输出必须新鲜且退出码为 0：

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
uv run alembic upgrade head

npm --prefix web ci
npm --prefix web run check:api
npm --prefix web run build
npm --prefix web run test:e2e
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1
```

- [ ] **Step 6：执行安全与追踪反查。** 逐行核对本计划矩阵：每项 Spec 要求至少有实现和测试，每个实际改动能指回要求；搜索未完成标记、临时占位实现、非白名单动态 import、通用代码执行器、客户端路径参数和日志路径泄漏；禁用扩展后运行核心 API/三页面回归。
- [ ] **Step 7：准备并执行 G9。** 使用打包后的 Windows 桌面壳和去敏工程副本，人工验证：启停跨重启、默认/自定义/跨图纸集不兼容模板、原生另存为取消与覆盖确认、目标选择后外部改动、成功打开所在文件夹、Excel 中前导零/筛选/冻结/文本公式安全、文件移动/修改后的 Artifact 可用性、核心页面不回退。记录操作者、日期、版本、commit、结果和遗留项。
- [ ] **Step 8：收口门禁与状态。** 自动验证和 G8 通过后把 G7/G8 记为通过；G9 只有用户真实桌面确认后才能通过。仅当矩阵必需项均已验证且无未关闭 P0/P1，才把本计划标为 `completed`；否则保持 `active` 并准确记录剩余验收。
- [ ] **Step 9：最终提交。** 在 `changelog.md` 追加 G8/G9、完整回归和实际遗留项；只暂存本任务涉及的文件，提交 `git commit -m "完成图纸目录扩展验证与交付记录"`。

## 批次回退与失败处理

- 批次一失败：扩展 router 不装配或默认禁用；核心 API、CAD Worker 和恢复流程必须继续可用。迁移只通过新 revision 前进，禁止回改已发布迁移。
- 批次二失败：保留扩展管理能力但将图纸目录标为 `FAILED`/`INCOMPATIBLE`，不返回编造预览；模板原 JSON 不丢失。
- 批次三失败：消费过的授权不得重用，要求用户重新选路径；清理候选与目标临时文件，绝不登记成功 Artifact，也不触碰工程文件。
- 批次四失败：隐藏扩展页面贡献并保留后端诊断；不得为通过 UI 测试绕过后端校验或改用浏览器下载。

## G6 计划自审

- 追踪矩阵覆盖扩展平台、字段/表达式/模板、预览、XLSX、保存、Artifact、页面、可访问性、双语和只读回归；每行至少指向一个任务和一种自动测试，关键用户流程另有 G8/G9。
- 反向检查 12 个任务均能指回 `ARCH-DM-006` 或 `SPEC-DM-012`；没有加入通用 Artifact 中心、后台长任务、CAD 作业、第三方安装或任意脚本加载。
- 类型链一致：`extension_id/action_id/workspace_id/revision_id` 从清单与工作区贯穿 invocation、preview digest、save grant 和 Artifact；模板与列使用 UUID，设置使用独立乐观 `revision`，不与工作区修订混用。
- 路径链一致：扩展只见候选临时目录，前端只见授权 ID，最终目标只存在于壳/授权/宿主发布器；成功响应按 Spec 显示路径，普通页面不取得哈希和来源修订。
- 已识别而未伪装为自动通过的边界只有两类：批次四的 ARCH-DM-005 运行时前置，以及 G9 的真实 Windows 另存为/Explorer/Excel 验收。两者都有明确暂停点和通过证据。

## 实际验证

2026-09-09：ARCH-DM-005 前置已形成已接受的 `SPEC-DM-013` 与 `PLAN-DM-021`（`proposed`），G4～G6 已关闭；生产多语言基础尚未实施，因此 Task 10 仍被阻断。解除条件为 PLAN-DM-021 批次一完成并记录实际 commit 与自动化结果。

2026-09-09：PLAN-DM-021 批次一（语言基础、设置事务与原生对话框契约）已完成，Task 10 前置解除。分支 `feat/dm-021-multilingual`，commits `48f86d0..f9dd914`：Task 1 `bada4e5`+`d4d48f8`（后端 ui_locale 设置、registry key 化、结构化 422）、Task 2 `d6c2fcf`+`169317f`（唯一 vue-i18n 实例、挂载前 bootstrap、check:i18n 门禁）、Task 3 `065cd28`+`ebc53c9`（设置保存成功才切换语言的事务与双语错误恢复）、Task 4 `f9dd914`（select_file(file_kind, localized_description) 白名单契约）。自动化证据：`uv run pytest` 730 passed/72 skipped、`uv run ruff check .` 通过、`npm --prefix web run test:unit` 28 passed、`npm --prefix web run test:e2e` 全量 295+80 passed、`check:i18n` 81 键对称、`npm --prefix web run build` 通过。真机原生对话框演示（设置保存成功/失败、dst/template/exe/dll 四种选择调用）属 G9 边界，留待 Task 12 真实桌面验证，浏览器 mock 不作替代。

2026-09-09：PLAN-DM-021 批次二（核心页面按域迁移）已完成。commits `f9dd914..bebe547`：Task 5 `d4cf4d1`（共享外壳与通用组件）、Task 6 `20cee67`（图纸工作区）、Task 7 `7a630f3`（属性工作区）、Task 8 `b159c86`+`bebe547`（修订/预览/修复/草稿/任务状态 + 草稿动作 label_key 持久化修复与消息键格式校验）。自动化证据：全量 e2e 314 passed、`npm --prefix web run test:unit` 28 passed、check:i18n 681 键/7 域对称、build 通过、Python 全量 pytest 与 ruff 通过。语言切换前后业务状态不变量（active tab/workspace/输入/草稿/job 状态）有 e2e 断言；「语言不得写入 draft」已在存储边界强制（消息键正则）。真机验证仍留 G9。

2026-09-10：PLAN-DM-020 批次一 Task 3（平台编排、统一管理 API 与结构化错误）已完成。新增 `application/extensions/runtime.py`（ExtensionRuntime 组合 registry/store，启动顺序钉死为服务迁移+发布恢复完成之后 discover+对账）、`interfaces/extension_contracts.py`（10 值平台码 Literal、`ExtensionErrorResponse{code,message_key,params,message}`、稳定文案键映射）、`interfaces/extension_api.py`（9 个统一端点：列表/启停/设置/偏好/动作 preview+execute/Artifact 查询；动作端点本任务只校验状态与声明，可用且已声明时返回 `EXTENSION_CAPABILITY_UNAVAILABLE`，不编造结果）；`api.py` 仅最小装配（`extension_runtime`/`extension_index` 注入点）。批次检查点（HTTP 测试客户端手工验证，2026-09-10）：`GET /api/health` 200；`GET /api/extensions` 200 且 `dst-manager.sheet-catalog` 如实呈现 `WAITING_DEPENDENCY`（能力中心 Task 4 未落地，不谎报 AVAILABLE）；`PATCH /api/extensions/{id}/state` 停用 200 且重启后持久保持；停用全部扩展后 `POST /api/workspaces/open`、`GET /api/workspaces/{id}`、`GET /api/revisions`、`GET /api/workspaces/{id}/draft` 均 200。自动化证据：`uv run pytest tests/integration/test_extension_api.py tests/integration/test_api.py tests/integration/test_api_settings.py` 100 passed、全量 pytest 通过（4 skipped 既有）、`uv run ruff check .` 通过、`uv run python scripts/export_openapi.py` 已同步 `web/src/api/openapi.json`。启动顺序测试用记录事件的 Database/RecoverablePublisher/ExtensionRuntime 替身断言严格三段顺序。偏差：Task 2 遗留的 `tests/unit/test_runtime.py` LATEST_SCHEMA_REVISION 断言（0005→0006）随本任务全量回归修复，已在 changelog 记录。

2026-09-10：PLAN-DM-020 批次二 Task 6（图纸目录预览动作、兼容性与确定性摘要）批次检查点核对 ARCH-DM-005 独立工作流前置：已进入 G0～G6 并关闭——`SPEC-DM-013` 已接受（G4/G5 证据齐备）、`PLAN-DM-021` 批次一～三已完成并记录实际 commit（多语言基础、核心页面按域迁移、按域扩展收尾），Task 10 前置持续满足。负责人：PLAN-DM-020 实施代理（Task 6）；下一检查点：批次三 Task 7 启动时复核 PLAN-DM-021 批次三 commit 记录与 `npm run check:i18n` 门禁是否仍通过。

2026-09-10：PLAN-DM-020 批次三 Task 9（执行动作、Artifact 查询和桌面共同装配）批次检查点复核 ARCH-DM-005 独立工作流前置：正式 Spec `SPEC-DM-013` 已接受、G4/G5 证据齐备、实施 Plan `PLAN-DM-021`（多语言支持）批次一～三已完成并记录实际 commit 与自动化证据——ARCH-DM-005 前置持续满足，Task 10 不阻断。批次检查点自动化证据：临时目录实际导出后 openpyxl 回读通过（表名/表头/行值/冻结/筛选）、目标漂移注入 `EXPORT_DESTINATION_CHANGED`、`os.replace` 故障注入旧目标字节保持，三条失败/注入路径均零半文件残留、零错误 Artifact 登记；整条预览→执行链路 DST/DWG 字节与 mtime、工程目录树、`jobs`/`document_revisions`/`workspace_write_locks` 零变化、应用临时候选清空。负责人：PLAN-DM-020 实施代理（Task 9）；下一检查点：批次四 Task 10 启动时复核 `npm run check:i18n` 与 `generate:api` 门禁。

其余尚未实施。执行时按批次追加：日期、commit、实际命令与退出码、测试数量、G8 截图位置、G9 操作者与结果、跳过项理由、偏差裁决和剩余风险。不得用计划中的“预期通过”替代实际证据。
