---
id: GUIDE-DM-005
title: Builtin 内置扩展开发指南（以图纸目录为例）
status: review
document_kind: guide
owners:
  - dst-manager
created: 2026-09-11
updated: 2026-09-11
related:
  - PRD-DM-001
  - ARCH-DM-001
  - ARCH-DM-006
  - SPEC-DM-012
  - GUIDE-DM-001
  - GUIDE-DM-004
---

# Builtin 内置扩展开发指南（以图纸目录为例）

> 定位：指导开发者以首个内置业务扩展 `dst-manager.sheet-catalog` 为参照，在 DST Manager 中设计、实现、测试和打包新的 Builtin 扩展。平台架构权威是 [ARCH-DM-006](../architecture/ARCH-DM-006-builtin-extension-platform.md)，图纸目录行为权威是 [SPEC-DM-012](../specs/SPEC-DM-012-sheet-catalog-extension.md)；本文只解释如何沿现有实现安全开发，与上游规范冲突时以上游为准。

## 1. 先澄清：这里的“插件”是什么

本文中的 Builtin 插件是 **DST Manager 内置业务扩展**。它与下列概念不同：

| 名称 | 位置 | 运行方式 | 本文是否覆盖 |
| --- | --- | --- | --- |
| Builtin 业务扩展 | `src/dst_manager/extensions/builtin/` | 与 Python 宿主同进程，由固定代码索引加载 | 是 |
| AutoCAD Worker Plugin | `plugins/src/DstManager.AutoCAD/` | 由 AutoCAD/Core Console 加载的 .NET Framework 4.8 DLL | 否 |
| 第三方可安装插件 | 用户目录或远程包 | 当前产品没有开放动态安装和任意代码加载 | 否 |

Builtin 扩展适合承载只读检查、统计、预览和受控成果导出。需要修改 DST/DWG、启动 CAD、访问网络、加载任意脚本或绕过宿主保存流程的能力，不应直接放入当前 Builtin 扩展；应先形成 PRD、Spec 和架构决策，再扩展宿主 Capability。

## 2. 当前平台能力与限制

### 2.1 已经通用化的能力

当前宿主已经提供：

- 固定索引发现与逐扩展故障隔离；
- Manifest 严格校验、宿主契约版本和 Capability 分类；
- `start()` / `stop()` 生命周期、启停持久化和活动调用排空；
- 应用级 JSON 设置与工作区级 JSON 偏好；
- `workspace.snapshot.read.v1` 只读快照；
- `workspace_page` 前端页面贡献；
- 统一扩展列表、启停、设置、偏好、预览和执行 URL；
- 一次性保存授权、候选文件校验、原子保存和 Artifact 登记；
- PyInstaller 随包资源和前端静态构建。

### 2.2 尚未完全通用化的能力

新增扩展前必须核对以下现状，不能把“统一 URL”误认为“任意动作即插即用”：

1. `src/dst_manager/interfaces/extension_contracts.py` 的预览、执行模型仍是图纸目录模板模型。
2. `src/dst_manager/interfaces/extension_api.py` 的 `_dispatch_preview()`、`_dispatch_execute()` 直接构造和序列化图纸目录对象。
3. `src/dst_manager/application/extensions/runtime.py` 的 `execute_action()` 接收 `SheetCatalogExecuteRequest`，并使用图纸目录 XLSX 校验器。
4. 图纸目录模板保存通过 `_TEMPLATE_SETTINGS_EXTENSION_ID` 进入专用服务端校验；其他扩展设置只走通用 JSON 乐观并发存储。
5. `ExtensionActionManifest.output_kind` 当前只支持 `xlsx` 或无输出；`xlsx` 只接受固定 MIME。
6. 宿主当前只认识和发放 `workspace.snapshot.read.v1`。
7. 前端当前只支持 `workspace_page`，页面必须命中编译期 `route_key -> Vue component` 白名单。

因此，只有生命周期、设置或偏好需求与现有通用契约一致的扩展可以直接复用平台。新增不同预览负载、不同输出格式、写工作区、CAD 操作或新 Capability 时，必须先修改 ARCH-DM-006 或新增 Spec，再通用化宿主契约；不要在新扩展内复制或绕过图纸目录特例。

## 3. 核心安全不变量

任何 Builtin 扩展都必须保持以下边界：

1. **代码入口只来自固定索引。** `manifest.yaml` 是数据，不得包含模块名、类名、脚本、命令或动态 import 入口。
2. **扩展只获得声明且获准的 Capability。** 不向扩展注入 `DstManagerService`、SQLAlchemy Session、可变 Workspace、发布器、任务队列或 ShellBridge。
3. **工作区读取使用冻结快照。** 扩展不直接打开 DST/DWG，不泄露工程绝对路径，并以 `base_revision_id` 阻止修订漂移。
4. **预览与执行绑定。** 执行前由宿主重新预览并逐字节核对 `preview_digest`；不能信任前端缓存。
5. **扩展不接触最终保存路径。** 扩展只在宿主分配的临时候选目录中写文件，宿主负责授权、回读、原子替换和 Artifact 登记。
6. **前端代码也使用白名单。** 后端 `route_key` 只用于查表，不能参与动态 import 表达式。
7. **单扩展失败不能拖垮宿主。** Manifest、工厂、启动和停止错误必须收敛为稳定状态或错误码。
8. **首期不注册后台资源。** 不创建计时器、后台线程、外部进程或网络连接；同步动作由注册表统计活动调用。
9. **错误使用稳定标识。** API 返回 `code`、`message_key` 和结构化 `params`；用户正文在前端语言包翻译，日志不记录属性值、表达式结果或完整保存路径。
10. **只读动作不产生工程副作用。** 不创建 `.dst-manager/`，不修改 DST/DWG，不更新时间戳，不取得发布写锁。

## 4. 图纸目录范例全景

### 4.1 代码结构

```text
src/dst_manager/
├─ extensions/
│  ├─ contracts.py                 # 跨扩展稳定值对象与 Protocol
│  ├─ manifest.py                  # Manifest Pydantic 严格校验
│  ├─ registry.py                  # 发现、状态机、启停与活动调用计数
│  ├─ capabilities.py              # CapabilityBroker 与短生命周期上下文
│  ├─ snapshots.py                 # 冻结工作区最小投影
│  ├─ save_grants.py               # 一次性保存授权
│  ├─ artifacts.py                 # 回读、原子保存和 Artifact 元数据
│  └─ builtin/
│     ├─ index.py                  # 受信工厂与 Manifest 资源固定索引
│     └─ sheet_catalog/
│        ├─ manifest.yaml          # 图纸目录扩展声明
│        ├─ extension.py           # 生命周期、preview/repreview/execute
│        ├─ expressions.py         # 受限表达式解析、绑定、求值
│        ├─ templates.py           # 模板模型、限制、迁移与持久化校验
│        ├─ preview.py             # 诊断、规范化预览与摘要
│        ├─ workbook.py            # XLSX 候选写入与回读验证
│        └─ errors.py              # 领域错误与 message_key 映射
├─ application/extensions/runtime.py   # 宿主编排与持久化对账
└─ interfaces/
   ├─ extension_contracts.py       # HTTP 请求/响应模型
   └─ extension_api.py             # 统一 API 与分派

web/src/
├─ features/extensions/pageRegistry.ts # route_key 编译期白名单
├─ api/extensions.ts                    # 扩展 HTTP 客户端
├─ composables/useExtensions.ts         # 扩展列表/启停状态
├─ composables/useSheetCatalog.ts       # 图纸目录页面状态所有者
├─ views/SheetCatalogView.vue           # 页面编排
├─ components/sheet-catalog/            # 聚焦展示组件
└─ i18n/locales/{zh-CN,en-US}/extensions.ts
```

### 4.2 调用链

```text
BuiltinExtensionIndex
  -> load_manifest() 严格校验
  -> ExtensionRegistry.discover()/start()
  -> ExtensionRuntime 持久化启停状态
  -> GET /api/extensions
  -> App.vue 过滤 AVAILABLE + workspace_page + 已知 route_key
  -> Vue 页面发起 preview
  -> Registry.invoke() 增加 active_calls
  -> CapabilityBroker 发放 ExtensionContext
  -> extension.preview(冻结快照, 请求)
  -> 返回诊断、预览行、preview_digest、executable
  -> ShellBridge 创建一次性 save_grant
  -> execute 请求重复提交模板快照与 preview_digest
  -> 宿主 repreview 并核对摘要
  -> 扩展写候选文件
  -> 宿主消费授权、回读校验、原子保存、登记 Artifact
  -> finally 清理候选目录并减少 active_calls
```

停用顺序是“先拒绝新调用，再等待 `active_calls == 0`，最后 `stop()`”。不要在扩展内部另造并发计数或停用状态。

## 5. 开发前判定

### 5.1 是否应该做成 Builtin 扩展

同时满足下列条件时优先考虑 Builtin 扩展：

- 能力对用户是独立功能域，可单独启停；
- 失败不应阻止宿主核心功能启动；
- 主要依赖受控只读数据或受控成果输出；
- 页面和设置可以按 `extension_id` 隔离；
- 不需要任意代码发现、第三方包安装或自更新。

如果只是核心发布流程中的必需校验、多个核心页面共用的领域规则或 AutoCAD Worker 必需命令，应放在相应 domain/application/infrastructure 或 Worker Plugin，而不是为了“模块化”强行包装成可停用扩展。

### 5.2 先做契约差距表

开发前至少回答：

| 问题 | 现有答案 | 超出时怎么办 |
| --- | --- | --- |
| 数据来源是什么？ | `workspace.snapshot.read.v1` | 先设计新的最小 Capability 与快照，不直接注入服务对象 |
| 是否需要写 DST/DWG？ | 不允许 | 走受控预览/修订/发布主流程，不在扩展内写文件 |
| 是否产生文件？ | 只支持 XLSX 候选 | 新输出种类先扩展 Manifest、保存对话框、验证器和打包测试 |
| 动作负载是否等同图纸目录模板？ | 当前 HTTP 契约是 | 不同则先拆出按扩展/动作分派的请求响应契约 |
| 是否需要页面？ | `workspace_page` | 新贡献类型先更新架构、宿主和前端白名单 |
| 是否需要持久化？ | 通用设置/偏好 JSON | 复杂业务数据要定义仓储、迁移、并发和降级策略 |
| 是否有后台任务？ | 首期不允许 | 先定义生命周期、取消、恢复和可观察性，不在 `start()` 偷启线程 |

## 6. SOP-A：建立扩展后端骨架

以下示例假设新增 `dst-manager.sheet-audit`，提供工作区页面和一个 XLSX 动作。标识仅作写法示范，正式名称应来自获批 Spec。

### A-1 创建聚焦目录

```text
src/dst_manager/extensions/builtin/sheet_audit/
├─ __init__.py
├─ manifest.yaml
├─ extension.py
├─ models.py       # 请求、响应和值对象；简单时可合并进 extension.py
├─ preview.py      # 纯计算、诊断和摘要
├─ workbook.py     # 仅在确实输出 XLSX 时创建
└─ errors.py       # 扩展专属稳定错误映射
```

单文件以约 500 行为软上限。生命周期/动作入口只负责编排；解析、业务规则、摘要和输出适配器按职责拆分。不要把新扩展逻辑继续塞进 `runtime.py` 或 `extension_api.py`。

### A-2 编写 Manifest

以图纸目录的 `manifest.yaml` 为准：

```yaml
extension_id: dst-manager.sheet-audit
version: 0.1.0
extension_type: builtin
host_contract: 1
enabled_by_default: false
name_key: extensions.sheetAudit.name
description_key: extensions.sheetAudit.description
required_capabilities:
  - workspace.snapshot.read.v1
permissions:
  - workspace.snapshot.read
  - artifact.output.propose
ui_contributions:
  - contribution_id: workspace-page
    kind: workspace_page
    route_key: sheet-audit
actions:
  - action_id: export-xlsx
    output_kind: xlsx
    media_type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
settings_schema: 1
```

字段规则：

| 字段 | 规则 |
| --- | --- |
| `extension_id` | 永久稳定、全局唯一的英文标识；发布后不要改名 |
| `version` | 严格 SemVer `MAJOR.MINOR.PATCH`，扩展行为变更时同步工厂常量与测试 |
| `extension_type` | 当前只能是 `builtin` |
| `host_contract` | 当前必须等于 `HOST_CONTRACT == 1`；不匹配进入 `INCOMPATIBLE` |
| `enabled_by_default` | 只决定首次发现意图；已有用户启停记录优先 |
| `name_key` / `description_key` | 稳定 i18n 键，不写中文正文 |
| `required_capabilities` | 扩展实际必需的宿主能力；未知能力不兼容，已知但不可用则等待依赖 |
| `permissions` | 审计声明；不能代替 CapabilityBroker 的运行时授权 |
| `ui_contributions` | 当前只支持 `workspace_page`，`route_key` 必须登记到前端白名单 |
| `actions` | `action_id` 在扩展内唯一；产生 XLSX 时输出种类和 MIME 必须成对声明 |
| `settings_schema` | 设置与偏好 JSON 的结构版本；格式或语义不兼容时才升级，并提供迁移/保护策略 |

`manifest.py` 使用 `extra="forbid"`。不要往清单加入 `module`、`class_name`、`entry_point`、`script`、`command` 等字段；即使能改校验器放行，也违反受信加载模型。

### A-3 实现最小生命周期与工厂

```python
from dst_manager.extensions.contracts import Extension

EXTENSION_ID = "dst-manager.sheet-audit"
EXTENSION_VERSION = "0.1.0"


class SheetAuditExtension:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def create_sheet_audit_extension() -> Extension:
    return SheetAuditExtension()
```

要求：

- 工厂每次返回新实例，不读取用户目录或扫描模块；
- `start()` 只建立轻量同步状态，异常会使该扩展进入 `FAILED`；
- `stop()` 必须幂等、可在活动调用排空后执行，失败会显示 `EXTENSION_STOP_FAILED`；
- 不在生命周期里创建网络连接、外部进程、线程或计时器。

### A-4 登记固定索引

在 `src/dst_manager/extensions/builtin/index.py` 显式导入工厂并追加条目：

```python
BuiltinExtensionEntry(
    manifest_resource="dst_manager/extensions/builtin/sheet_audit/manifest.yaml",
    factory=create_sheet_audit_extension,
),
```

固定索引同时是信任边界和打包清单。禁止改成 `pkgutil`、目录扫描、字符串模块名或 YAML 反射导入。

### A-5 先写发现与生命周期测试

至少覆盖：

- Manifest 可加载，所有字段与预期一致；
- Manifest 与 `EXTENSION_ID` / `EXTENSION_VERSION` 常量一致；
- 默认启用或停用行为正确；
- 未声明动作返回 `EXTENSION_ACTION_NOT_FOUND`；
- 工厂/`start()`/`stop()` 失败只影响本扩展；
- 重复 `extension_id` 保留先发现者；
- 停用期间拒绝新调用并等待既有调用退出；
- 宿主契约不匹配、未知能力、能力不可用分别进入正确状态。

参考 `tests/unit/test_extension_manifest.py`、`tests/unit/test_extension_registry.py` 和 `tests/unit/test_extension_persistence.py`，不要只验证 happy path。

## 7. SOP-B：实现只读数据、预览与执行

### B-1 只通过 ExtensionContext 取数据

动作方法接收 `ExtensionContext`，调用：

```python
snapshot = context.workspace_snapshot()
```

当前快照提供工作区与修订身份、图纸集名称和自定义属性、按 DST 顺序冻结的图纸最小字段及自定义属性。文件名只保留 basename；不含工作区根、DST/DWG 绝对路径、可变 DOM 或数据库对象。

如果现有快照缺字段：

1. 先证明字段是新扩展必需的最小只读数据；
2. 更新 ARCH-DM-006/对应 Spec 的快照契约；
3. 在 `snapshots.py` 增加不可变、可序列化字段；
4. 补路径裁剪、顺序、字段冲突、空值和只读时间戳回归；
5. 必要时升级 Capability 名称，而不是静默改变 `v1` 语义。

禁止从上下文绕回 reader、Session 或文件系统。

### B-2 把预览设计成确定性纯投影

图纸目录的 `preview.py` 做四件事：

1. 规范化并校验请求模板；
2. 绑定字段定义并生成阻断错误/非阻断警告；
3. 求值有限数量的预览行；
4. 用工作区、修订、规范化输入、扩展版本和动作身份生成 `preview_digest`。

新扩展应保持相同性质：相同冻结快照和相同规范化输入必须产生相同摘要。摘要中至少绑定：

```text
extension_id + extension_version + action_id
+ workspace_id + revision_id
+ normalized_request
+ affects_execution 的诊断/选项
```

不要把随机数、时间、临时候选路径、用户最终保存路径或预览行截断副作用放进摘要。

### B-3 区分三类结果

- **阻断错误**：输入无法解释、字段未定义、限制超出；`executable=false`。
- **非阻断警告**：字段已定义但部分记录缺值；允许执行。
- **平台错误**：扩展不可用、修订漂移、Capability 缺失、保存授权失效；由宿主契约处理。

扩展专属诊断应包含稳定 `code`、`message_key`、结构化 `params`，以及必要的字段/列/字符位置。不要只返回中文句子。

### B-4 实现 `preview()`、`repreview()` 和 `execute()`

图纸目录入口可概括为：

```python
class SheetCatalogExtension:
    def preview(self, context, request):
        snapshot = context.workspace_snapshot()
        return build_preview(snapshot, request.template, ...)

    def repreview(self, context, execute_request):
        return self.preview(context, preview_request_from(execute_request))

    def execute(self, context, request, proposal_directory):
        snapshot = context.workspace_snapshot()
        headers, rows = build_all_rows(snapshot, request.template)
        candidate = proposal_directory.root / "fixed-candidate-name.xlsx"
        summary = write_candidate(candidate, headers, rows)
        return CandidateArtifact(...)
```

关键点：

- 执行请求必须重复提交完整输入快照，不能只传数据库 ID；
- `repreview()` 必须与 `preview()` 使用同一规范化和求值路径；
- 预览可以截断展示，执行必须处理全量数据；
- 候选名是固定安全名称，只能落在 `proposal_directory.root`；
- 返回的 `expected_headers` / `expected_rows` 供宿主回读交叉校验；
- 扩展不得消费 `save_grant_id`，也不得得知最终 `output_path`；
- 任一失败不能登记成功 Artifact，候选目录由宿主 `finally` 清理。

### B-5 不同动作负载要先拆通用分派

如果新扩展不是图纸目录同构动作，不要把它伪装成 `SheetCatalogTemplate`。应先设计并实现至少以下宿主能力：

- 按 `(extension_id, action_id)` 选择请求解析器、预览响应序列化器和执行响应序列化器；
- 将 `runtime.execute_action()` 的图纸目录类型依赖替换为稳定动作协议；
- 将候选验证器按 `output_kind/media_type` 从宿主白名单选择；
- 保持动作实现拿不到 FastAPI Request、ShellBridge、目标路径和 ArtifactStore；
- 为未知动作类型、负载不匹配、响应不匹配提供稳定 fail-closed 错误；
- 更新 OpenAPI、前端生成类型与集成测试。

这属于宿主契约变更，不是复制 `sheet_catalog` 文件夹能完成的小改动。

## 8. SOP-C：设置与工作区偏好

### C-1 选择正确作用域

| 数据 | 存储位置 | 示例 |
| --- | --- | --- |
| 随包且不可变的默认值 | 扩展代码 | 图纸目录内置默认模板 |
| 跨工作区复用的用户配置 | 扩展 settings | 用户模板集合 |
| 某工作区的轻量选择 | workspace preference | 上次选中的模板 ID |
| 工作区事实 | 冻结 snapshot | 图纸与属性 |
| 导出成果记录 | Artifact | 最终路径、大小、哈希、来源修订 |

不要把用户设置写进 Manifest，也不要把应用设置混进工作区修订。

### C-2 通用设置接口

```text
GET /api/extensions/{extension_id}/settings
PUT /api/extensions/{extension_id}/settings
GET /api/extensions/{extension_id}/workspaces/{workspace_id}/preferences
PUT /api/extensions/{extension_id}/workspaces/{workspace_id}/preferences
```

设置返回 `{schema_version, revision, value}`。PUT 必须提交 `expected_revision`，冲突时保留本地编辑并让用户刷新/另存；偏好用于可丢失、可重建的轻量状态，不承载关键业务数据。

### C-3 扩展专属设置校验

通用存储只保证 JSON、schema 版本和乐观并发，不理解业务不变量。图纸目录通过 `runtime.py` 的专用分派强制模板 UUID、大小写重名、100 个上限、内置不可变和未知高版本保护。

新扩展若有业务约束，必须：

1. 在扩展域模块实现纯校验、规范化、序列化和迁移；
2. 在应用层建立明确的按扩展身份分派，不在接口层复制规则；
3. 对畸形 JSON fail-closed；
4. 保留未知高版本原 JSON，防止旧程序写回丢数据；
5. 覆盖新增、更新、并发冲突、超限、旧版本迁移和高版本降级测试。

不要照抄 `_TEMPLATE_SETTINGS_EXTENSION_ID` 再增加一串 `if`。当第二个专属校验出现时，应抽出 `extension_id -> settings codec/validator` 的受信编译期注册表。

## 9. SOP-D：接入 HTTP 契约

### D-1 复用通用管理 URL

平台当前 URL：

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

扩展不能自挂 FastAPI router。接口层只做 Pydantic 输入输出、HTTP 状态、稳定错误响应和运行时分派；领域规则留在扩展模块，保存与 Artifact 规则留在宿主。

### D-2 更新契约模型和 OpenAPI

新动作若需要新模型：

- 在 `extension_contracts.py` 定义严格模型，保持 API 字段为稳定英文；
- 在 `extension_api.py` 只做模型转换与分派；
- 更新 `tests/integration/test_extension_api.py`；
- 运行 `web` 的 `npm run generate:api` 生成 `src/api/openapi.json` 和 `schema.d.ts`；
- 最终用 `npm run check:api` 验证生成物无漂移。

不要手改 `schema.d.ts`，也不要在 TypeScript 中重新猜后端结构。

### D-3 错误码与 HTTP 状态

优先复用 ARCH-DM-006 已定义的平台码：

- `EXTENSION_NOT_FOUND`：404；
- `EXTENSION_DISABLED`：409；
- `EXTENSION_INCOMPATIBLE`：409；
- `EXTENSION_ACTION_NOT_FOUND`：404；
- `EXTENSION_CAPABILITY_UNAVAILABLE`：503；
- `REPREVIEW_REQUIRED`：409；
- `SAVE_GRANT_INVALID` / `EXPORT_DESTINATION_CHANGED`：409；
- `ARTIFACT_WRITE_FAILED`：503。

扩展专属业务错误应在 Spec 中定义语义、阻断性、HTTP 状态、`message_key` 与 `params`。依照 [GUIDE-DM-004](GUIDE-DM-004-multilingual-config-sop.md) 同步后端消息目录和中英文资源。

## 10. SOP-E：接入前端页面

### E-1 登记编译期页面白名单

在 `web/src/features/extensions/pageRegistry.ts` 增加静态字面量：

```ts
export const EXTENSION_PAGE_COMPONENTS = {
  "sheet-catalog": defineAsyncComponent(() => import("../../views/SheetCatalogView.vue")),
  "sheet-audit": defineAsyncComponent(() => import("../../views/SheetAuditView.vue")),
} as const;
```

同步更新 `pageRegistry.test.ts` 的精确键集合。禁止：

```ts
// 错误：后端输入进入动态 import
defineAsyncComponent(() => import(`../../views/${routeKey}.vue`));
```

`App.vue` 只挂载 `status === "AVAILABLE"`、贡献类型为 `workspace_page` 且 `isExtensionRouteKey()` 命中的页面。未知键安全忽略，不要增加 fallback 动态加载。

### E-2 分离页面编排和状态

参照图纸目录：

- `View.vue` 负责编排区域、传 props 和接收事件；
- `useXxx.ts` 是该扩展页面状态的唯一所有者，处理请求、脏状态、竞态和取消；
- `components/<extension>/` 组件按展示职责拆分；
- `api/extensions.ts` 承担协议调用与类型转换；
- 不把扩展状态追加到已较大的 `App.vue`；
- 前端不复制后端最终校验规则，只做即时输入反馈和错误定位。

必须处理：扩展列表刷新、停用当前页、工作区切换、修订变化、请求乱序、未保存输入、预览过期、保存取消和执行失败。

### E-3 i18n 与可访问性

在中英文 `extensions.ts` 同步新增：

- Manifest 的 `name_key` / `description_key`；
- 页面标题、操作、空态、加载态、错误、警告和成功反馈；
- ARIA label、tooltip、placeholder 和确认文案；
- 新错误码对应的 `errors.*` 键。

运行 `npm run check:i18n` 保证两套键和插值参数完全对称。页面需支持键盘操作、可见焦点、错误聚焦、200% 缩放和最小支持视口；可见 UI 改动按 [GUIDE-DM-001](GUIDE-DM-001-frontend-design-implementation-gates.md) 完成设计门禁和视觉证据。

## 11. SOP-F：成果输出与保存

### F-1 扩展只产候选

候选输出必须满足：

- 路径严格位于宿主本次分配的唯一目录；
- 固定受控文件名和已声明 MIME；
- 返回宿主回读需要的结构摘要；
- 不包含公式、宏、外部链接、绝对工程路径等禁止特性；
- 写入失败抛扩展领域错误或 `OSError`，由运行时契约化为 `ARTIFACT_WRITE_FAILED`。

### F-2 宿主负责最终发布

保存链路不可在扩展中重写：

1. 桌面壳使用固定输出种类打开原生“另存为”；
2. `SaveGrantStore` 记录扩展、动作、工作区、修订、目标基线和有效期；
3. 执行前重建预览并校验摘要；
4. 扩展生成候选；
5. 宿主消费一次性授权并检查目标漂移；
6. 宿主回读候选、临时复制、flush/fsync、原子替换；
7. 成功后登记 Artifact；
8. 无论成功失败都清理候选目录。

新增输出格式必须同时增加固定 Shell 过滤器、Manifest 白名单、候选验证器、原子保存测试、Artifact kind/MIME 契约和真实桌面验收。绝不能让前端提交任意扩展名、MIME 或过滤器。

## 12. SOP-G：数据库、迁移和打包

### G-1 持久化

复用现有 `extension_states`、`extension_settings`、`extension_workspace_preferences` 和 `artifacts` 时通常不需要新表。需要新模型时：

- 在独立 infrastructure 模块实现仓储，不向现有超限文件继续追加；
- 同时创建 Alembic revision；
- 验证全新数据库 `upgrade head` 和旧数据库升级；
- 明确失败恢复、唯一约束、乐观并发和删除语义；
- 不把 SQLAlchemy 类型泄露进扩展领域模块。

### G-2 PyInstaller 随包资源

Python 模块通常由 import 图收集，但 YAML、模板、XSD 等数据资源必须显式进入 `packaging/dst-manager.spec` 的 `datas`。新 Manifest 示例：

```python
(
    "..\\src\\dst_manager\\extensions\\builtin\\sheet_audit\\manifest.yaml",
    "dst_manager/extensions/builtin/sheet_audit",
),
```

第二项是**目标目录**，PyInstaller 会保留 basename。不要写成 `.../manifest.yaml`，否则可能产生 `manifest.yaml/manifest.yaml` 双层路径。

同步扩展 `tests/unit/test_packaging_spec.py`：

- 源 Manifest 存在；
- 固定索引引用同一路径；
- `datas` 源和目标目录精确正确；
- 新的运行时数据文件全部被收集；
- 新生产依赖位于 `pyproject.toml` 与 `uv.lock`，许可证可追溯且未被 `excludes` 排除；
- 前端页面已进入 `web/dist` 构建产物。

修改 Python 依赖只用 `uv add` / `uv remove` / `uv sync`，并提交 `pyproject.toml` 与 `uv.lock`。修改 Web 依赖同步提交 `package.json` 与 `package-lock.json`。

## 13. 测试矩阵

### 13.1 后端单元测试

| 层 | 必测内容 | 图纸目录参考 |
| --- | --- | --- |
| Manifest | 字段、SemVer、extra forbid、重复动作、输出/MIME 配对 | `test_extension_manifest.py` |
| Registry | 发现、隔离、状态、启停、排空、重复 ID、能力分类 | `test_extension_registry.py` |
| Capability | 未声明/未知/不可用、上下文关闭、修订漂移、路径裁剪 | `test_extension_snapshot.py` |
| 纯业务 | 边界、空值、恶意输入、确定性、顺序、上限 | `test_sheet_catalog_expressions.py` 等 |
| 设置 | 默认值、CRUD、修订冲突、迁移、高版本保护 | `test_sheet_catalog_templates.py` |
| 输出 | 类型、前导零、禁止特性、回读、损坏候选 | `test_sheet_catalog_workbook.py` |
| 保存 | 授权过期/复用/错配、目标漂移、故障注入、残留清理 | 扩展保存与 Artifact 单测 |
| 打包 | Manifest/data/依赖/许可证/前端资源 | `test_packaging_spec.py` |

### 13.2 API 集成测试

至少覆盖：

- 扩展列表完整摘要与未知扩展；
- 启停持久化和不可用状态；
- 设置/偏好默认、保存、并发与 schema 错误；
- 动作未声明、扩展停用、Capability 不可用；
- 预览请求/响应结构和稳定错误；
- 执行摘要漂移、授权错配、成功 Artifact 和失败不登记；
- 只读打开、预览和导出不创建工程管理目录、不改变源文件时间戳；
- OpenAPI 与前端生成类型一致。

### 13.3 前端与 E2E

覆盖可用、停用、加载失败、空数据、阻断错误、非阻断警告、修订漂移、保存取消、导出成功和导出失败。对异步预览使用延迟与乱序响应测试，确认旧响应不能覆盖新草稿。

UI 可见扩展还应验证：浅色/深色、最小视口、200% 缩放、长文本、最大数据边界、键盘顺序、错误聚焦、Esc、焦点归还和停用当前页。

### 13.4 真实验收

自动测试不能替代以下真机项目：

- 打包后的 Manifest 可发现且页面可加载；
- 原生“另存为”、取消、覆盖确认和目标漂移；
- 最终文件能被目标桌面软件正常打开；
- “打开所在文件夹”、最终路径和 Artifact 查询一致；
- 安装包更新不覆盖用户数据。

涉及 AutoCAD 的新能力还必须由环境显式设置 `DST_MANAGER_RUN_AUTOCAD=1`，执行双版本真实系统测试；普通只读/XLSX 扩展不应无故引入 AutoCAD 依赖。

## 14. 推荐实施顺序

按以下顺序开发可以尽早暴露契约问题：

1. 完成 PRD/Spec、契约差距表和前端门禁分级。
2. 写 Manifest 失败测试和解析测试。
3. 写最小扩展、工厂、固定索引和 Registry 生命周期测试。
4. 先以纯函数实现请求模型、业务计算、诊断和确定性摘要。
5. 接入冻结快照与 Capability，上下文关闭后不可复用。
6. 接入应用运行时，补修订漂移和启停排空测试。
7. 接入 HTTP 契约并更新 OpenAPI。
8. 若有设置，完成业务校验、并发和 schema 迁移。
9. 若有成果，先完成候选写入/回读测试，再接保存授权与 Artifact。
10. 登记前端页面白名单，建立页面状态 composable 和组件。
11. 同步中英文 i18n、可访问性、E2E 和视觉证据。
12. 更新 PyInstaller `datas`、打包守护、文档和 `changelog.md`。
13. 运行完整门禁，再执行打包真机验收。

每个阶段先写失败测试，再写最小实现。不要先做整页 UI，最后才发现后端动作契约仍是图纸目录专用。

## 15. 验证命令

在仓库根目录使用 Windows PowerShell：

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
uv run alembic upgrade head

Set-Location web
npm ci
npm run test:unit
npm run build
npm run test:e2e
```

打包验证：

```powershell
Set-Location ..
.\scripts\build_release.ps1
```

如果只修改 Python/Vue 业务代码而未改 AutoCAD Worker 源码，开发期可以按任务风险使用聚焦测试；正式发布包仍须确认所需 Worker 产物存在。`-SkipPlugins` 只表示复用既有 Worker DLL，不会跳过 Builtin Python 扩展。

## 16. 常见错误与处理

| 反模式 | 后果 | 正确做法 |
| --- | --- | --- |
| 把 Builtin 与 AutoCAD Worker DLL 混称“插件” | 构建、权限和运行时边界混乱 | 文档和代码评审中明确写“Builtin 业务扩展”或“AutoCAD Worker Plugin” |
| 扫描 `builtin/` 自动加载 | 任意代码进入信任边界，打包行为不确定 | 只改固定 `BUILTIN_EXTENSION_INDEX` |
| 在 YAML 写 Python 类名 | 把数据清单变成执行入口 | Manifest 只声明元数据；工厂由代码直接引用 |
| 声明新 Capability 就直接使用 | Registry 会判不兼容，或开发者绕开 Broker | 先设计宿主能力、allowlist、最小上下文和测试 |
| 扩展直接读数据库/DST/工作区路径 | 破坏隔离、只读和隐私边界 | 只使用冻结 `WorkspaceSnapshot` |
| 执行只提交 `template_id` | 存储内容漂移，预览与导出不一致 | 重复提交完整输入快照并核对 digest |
| 扩展直接写用户目标 | 绕过授权、漂移检测、原子保存和审计 | 只写宿主候选目录，返回 `CandidateArtifact` |
| 用后端 `route_key` 拼动态 import | 后端数据变成代码加载路径 | 静态 `EXTENSION_PAGE_COMPONENTS` 查表 |
| 在 `App.vue` 堆扩展业务状态 | 文件继续膨胀、生命周期互相污染 | 独立 View + composable + 聚焦组件 |
| 前端复制最终业务校验 | 前后端规则漂移 | 前端只做提示，后端重新校验并决定 `executable` |
| 新动作套用图纸目录请求模型 | API 看似成功复用，语义错误且难演进 | 先通用化按扩展/动作分派契约 |
| 新专属设置继续加 `if extension_id == ...` | Runtime 成为扩展规则集合 | 第二个特例出现时抽受信 settings codec 注册表 |
| 忘记把 Manifest 加入 PyInstaller datas | 源码运行正常，打包后显示 `EXTENSION_MANIFEST_INVALID` | spec 与打包静态测试同步更新 |
| 只跑单测不构建 Web | OpenAPI、i18n 或异步组件路径在交付时才失败 | 至少运行 `test:unit`、`build` 与相关 E2E |
| 在日志输出完整 payload/路径 | 泄露工程数据 | 只记录稳定 ID、code、stage 和必要计数 |

## 17. 故障排查

### 17.1 扩展未出现在列表

1. 检查是否加入 `BUILTIN_EXTENSION_INDEX`。
2. 检查 `manifest_resource` 是否使用包路径和正斜杠。
3. 运行 `test_extension_manifest.py`。
4. 查看服务端日志中的 `EXTENSION_MANIFEST_INVALID` 或 `EXTENSION_ID_DUPLICATED`。
5. 打包环境再检查 `packaging/dst-manager.spec` 的 `datas` 目标目录。

### 17.2 列表存在但状态不可用

| 状态 | 常见原因 |
| --- | --- |
| `DISABLED` / `STOPPED` | 用户持久化为停用，或清单默认停用 |
| `WAITING_DEPENDENCY` | Capability 已知但宿主当前未提供 |
| `INCOMPATIBLE` | `host_contract` 不匹配或请求未知 Capability |
| `FAILED` | Manifest、工厂、`start()` 或 `stop()` 失败 |

先看 `error_code`，不要通过强制改状态绕过分类。

### 17.3 后端 AVAILABLE 但页面不显示

依次检查：

- 工作区是否已加载；
- Manifest 是否声明 `kind: workspace_page`；
- `route_key` 是否精确命中 `EXTENSION_PAGE_COMPONENTS`；
- `pageRegistry.test.ts` 是否包含该键；
- 异步 import 的文件名大小写是否一致；
- `npm run build` 是否已把页面打进 `web/dist`。

### 17.4 预览成功但执行要求重新预览

这是安全门禁，不要捕获后继续执行。检查：

- `base_revision_id` 是否变化；
- 执行提交的规范化输入是否与预览一致；
- `extension_version`、`action_id` 是否进入摘要；
- 前端是否把旧请求响应覆盖到新草稿；
- 摘要计算是否混入时间、随机数或展示截断数据。

### 17.5 源码环境正常、打包环境失败

优先检查：

- Manifest/模板/XSD 是否在 `datas`；
- 动态导入依赖是否需要 `hiddenimports`；
- 生产依赖是否在 `pyproject.toml` 和 `uv.lock`；
- 前端是否先构建 `web/dist`；
- `tests/unit/test_packaging_spec.py` 是否对新资源建立精确守护。

## 18. 交付检查表

### 设计与边界

- [ ] 已明确该能力适合 Builtin，而非核心流程或 AutoCAD Worker。
- [ ] 已完成数据、Capability、动作负载、输出、持久化和页面贡献差距分析。
- [ ] 超出现有宿主契约的部分已有获批 Spec/Architecture 更新。
- [ ] 未引入动态发现、任意代码入口、网络、后台线程或直接工作区写入。

### 后端

- [ ] Manifest、扩展常量、工厂和固定索引一致。
- [ ] 业务规则按模块拆分，入口只负责编排。
- [ ] 只通过短生命周期 `ExtensionContext` 读取冻结快照。
- [ ] preview/repreview/execute 共享同一规范化语义并绑定 digest。
- [ ] 错误码、HTTP 状态、message_key 和 params 已形成闭合契约。
- [ ] 设置的 schema、并发、迁移和高版本保护已覆盖。
- [ ] 候选输出不接触最终路径，失败不登记 Artifact。

### 前端

- [ ] `route_key` 已加入编译期页面白名单和精确键测试。
- [ ] 页面状态在独立 composable，未继续膨胀 `App.vue`。
- [ ] API 类型来自 OpenAPI，不手写漂移结构。
- [ ] 中英文键与插值参数对称，用户数据不翻译。
- [ ] 加载、空态、错误、警告、停用、漂移、取消和成功状态齐全。
- [ ] 键盘、焦点、缩放、主题和最小视口通过验证。

### 测试、打包与文档

- [ ] Manifest/Registry/Capability/业务/设置/输出/Artifact 单测齐全。
- [ ] API、OpenAPI、前端单测和相关 E2E 通过。
- [ ] Alembic 全新升级和既有数据库升级通过（如涉及模型）。
- [ ] 所有随包资源已登记 PyInstaller `datas` 并有静态守护。
- [ ] 新依赖和许可证可追溯，锁文件同步。
- [ ] Ruff、pytest、UV lock、Web build 与相关 E2E 实际通过。
- [ ] 打包后的发现、页面、原生保存和成果打开完成真机验收。
- [ ] 相关 README、Spec/Architecture、测试说明和根 `changelog.md` 已同步。

