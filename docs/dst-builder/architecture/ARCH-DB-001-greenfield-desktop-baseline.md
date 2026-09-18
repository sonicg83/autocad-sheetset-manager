---
id: ARCH-DB-001
title: DST Builder 绿地桌面架构基线
status: accepted
owners:
  - dst-builder
created: 2026-09-17
updated: 2026-09-18
related:
  - VISION-DB-001
  - PRD-DB-001
  - RFC-INT-001
  - ARCH-INT-002
  - ARCH-DM-001
document_kind: architecture
---

# DST Builder 绿地桌面架构基线

## 1. 架构目标

- 为单人本地桌面产品提供完整、可恢复、可审计的图纸集生成工作流。
- 用全新的领域模型表达项目、图纸分组、展开结果、模板绑定和生成计划。
- 复用 DST Manager 已验证的安全能力，但不继承其编辑型工作区模型和历史兼容负担。
- 首版不部署服务器组件，同时通过端口隔离 SQLite、本地 Artifact Store 和 Core Console，为未来内网服务化保留替换空间。
- 所有正式成果在完整验证后原子发布，并发布到目标目录，由 DST Manager 直接打开其中的 DST。

## 2. 非目标

- 不兼容旧 Builder、PowerShell/WPF、旧数据库、旧 API 或旧项目格式。
- 不维护 Legacy 与 Builder 双轨运行。
- 不建设多人身份、审批、远程 Worker、DM8 或 RustFS。
- 不把外围 AutoCAD 插件纳入首版。
- 不建立 Builder 与 Manager 的共享数据库或隐式同步。

## 3. 总体结构

```text
Builder Vue / WebView2 / CLI
            ↓
    interfaces / bootstrap
            ↓
       application
            ↓
          domain
            ↑
      ports / adapters
            ↓
SQLite / local files / dst_platform / Core Console
```

依赖只由外向内：

- `domain` 不依赖 FastAPI、Pydantic、SQLAlchemy、文件系统、Excel、AutoCAD 或 Manager。
- `application` 编排领域对象和端口，不直接拼接 SCR 或操作正式成果目录。
- `infrastructure` 实现 SQLite、Excel、模板目录、本地 Artifact、DST 和 CAD 适配器。
- `interfaces` 只负责 HTTP/CLI/桌面壳输入输出和依赖装配。

## 4. 产品与共享包

建议的逻辑包边界：

```text
src/
├─ dst_builder/
│  ├─ domain/
│  ├─ application/
│  ├─ infrastructure/
│  ├─ interfaces/
│  └─ bootstrap/
├─ dst_manager/
└─ dst_platform/
```

`dst_builder` 自有：

- 项目与修订；
- 图纸分组、展开规则和模板绑定；
- `GenerationPlan` 与生成编排；
- 向导状态、Builder API 和 Builder 前端；
- Excel 兼容导入和项目导出。

`dst_platform` 只在形成两个真实消费方后接收：

- AutoCAD 运行时发现与能力描述；
- Core Console 安全启动、超时、日志净化和结果收集；
- 固定 CAD 作业协议；
- DST 字节 Codec 和 AcSm 契约校验；
- 隔离工作区、文件锁、路径边界、哈希和原子发布；
- Artifact 清单和结构化诊断。

Builder 不导入 Manager 内部模块。共享提取采用渐进迁移，不以前置重构整个 Manager 为启动条件。

## 5. 领域模型

| 类型 | 责任 | 关键约束 |
| --- | --- | --- |
| `BuilderProject` | 项目身份和当前草稿 | 稳定 UUID、明确 schema 版本 |
| `ProjectDraft` | 可变编辑事务 | 自动保存、乐观版本 |
| `ProjectRevision` | 构建输入快照 | 提交后不可变、规范化哈希 |
| `SheetGroupSpec` | 用户录入的图纸分组 | 只表达业务输入，不含 CAD 命令 |
| `ExpandedSheet` | 展开的最终图纸 | 图号、标题和归属确定且唯一 |
| `TemplateBinding` | 模板与资产选择 | 内容哈希固定、兼容版本明确 |
| `CadDocumentPlan` | 单个 DWG 的 CAD 意图 | 可序列化、无任意命令文本 |
| `GenerationPlan` | 一次完整生成计划 | 引用固定修订与资产、不可变 |
| `BuildRun` | 一次逻辑构建 | 包含多个独立 attempt |
| `ArtifactManifest` | 成果与验证结果 | 全文件哈希、来源和角色明确 |

## 6. 项目存储

```text
项目目录/
├─ project.dstb
├─ assets/
├─ builds/
└─ exports/
```

- `project.dstb` 是本地 SQLite 数据库，保存项目、草稿、修订、计划、运行索引和向导状态。
- 输入、模板和辅助文件纳入 `assets/` 并按哈希登记；构建不依赖未冻结外部路径。
- 每个 attempt 使用 `builds/<build-id>/attempt-NNN/` 独立目录。
- 数据库启用外键和 WAL；数据库访问隐藏在 Repository 端口后。
- `%LOCALAPPDATA%\dst-builder\` 只保存应用设置、最近项目、日志和本机能力缓存，不成为项目事实源。

## 7. 引导应用结构

向导是可持久化的应用状态机：

```text
PROJECT → RULES → SHEETS → TEMPLATES → PREFLIGHT → BUILD
```

- 步骤状态从领域完成条件和诊断推导，不由前端自行判定。
- 已完成步骤可返回；后续步骤只有在前置门禁满足后开放。
- 进入 `PREFLIGHT` 时提交不可变项目修订；确认计划后，当前构建输入冻结。
- 关键校验同时提供内联提示和可聚焦错误摘要。
- 前端可以复用共享设计令牌和基础控件，但拥有独立导航、页面和状态机。

## 8. 生成管线

```text
ProjectDraft
→ ProjectRevision
→ GenerationPlan
→ isolated attempt workspace
→ DWG CAD tasks
→ layout/Handle verification
→ SheetSetDocument
→ AcSm DOM
→ schema/contract validation
→ DstCodec
→ accompanying artifacts
→ ArtifactManifest
→ atomic publish
```

### 8.1 CAD

- CAD 作业只接受结构化 `CadDocumentPlan`。
- SCR 由固定渲染器生成，用户文本必须经过名称和参数校验。
- 使用匹配 AutoCAD 2016/2020 的最小 Worker 插件执行 Python/Core Console 无法可靠完成的数据库操作。
- DWG 可以有界并行；并发度、超时和能力版本进入计划与审计。

### 8.2 DST

Builder 首版只有一个正式 DST 写入实现：

```text
Builder 模型 → SheetSetDocument → 全新 AcSm XML DOM
→ Schema/契约校验 → DstCodec 编码
```

- 不依赖现有 DST 作为结构模板。
- 不依赖旧 `UtilityClass.dll`。
- 不保留第二套运行时实现作为回退。
- SSO COM 只可作为研究、独立验证或未来 ADR 候选，首版不进入生产依赖。
- 生成结果必须由 AutoCAD 2016/2020 的官方 Sheet Set Manager 实际打开验证。

## 9. 构建状态与失败语义

```text
DRAFT → REVISION_READY → PLANNED → QUEUED → PREPARING
→ BUILDING_DWG → BUILDING_DST → VERIFYING → PUBLISHING → SUCCEEDED
```

- `FAILED` 和 `CANCELLED` 为终止状态，不从终态倒退。
- 重试创建新 attempt，不覆盖旧日志、工作目录和结果。
- 任一必需 CAD 任务失败时不生成可交付 DST。
- 崩溃恢复不续跑半完成 CAD 命令，只收敛文件事务并允许新 attempt。
- 发布阶段必须完成或恢复到一致状态后才响应取消完成。
- 错误包含稳定错误码、步骤、对象、摘要和恢复动作。

## 10. 正式成果目录

目标目录直接包含三个文件，没有包装子目录：

```text
<target>/
├─ sheetset.dst
├─ <sheet-number> <title>.dwg
└─ 图纸目录.xlsx
```

目标目录本身就是交付边界，其 DST 引用按相对文件名解析，与所在目录名无关。不生成清单、来源元数据或校验报告文件；发布完整性判定只断言预期产物存在、可读、非空，不检查目录内是否存在其他文件。

Manager 直接打开该 DST，从磁盘现状建立工作区，不访问 `project.dstb`，也不校验成果来源。

## 11. 未来服务化边界

首版不实现服务端，但以下端口不得绑定本地实现：

- `ProjectRepository`
- `ArtifactStore`
- `CadExecutor`
- `TemplateCatalog`
- `BuildRunRepository`
- `EventPublisher`

未来内网服务化可以替换适配器和部署拓扑，不改变领域命令或生成计划。首版不得为未实现的服务场景引入账号、租约、对象存储或分布式一致性代码。

## 12. 测试与发布门禁

- 领域单元测试覆盖展开、编号、命名、字段回退和模板选择。
- JSON Schema 契约测试覆盖计划、CAD 作业和 Artifact。
- 黄金样本比较业务语义，不要求与 Legacy 文件二进制相同。
- 无 CAD 集成测试覆盖 SQLite、项目复制、哈希、崩溃恢复和发布故障注入。
- AutoCAD 2016/2020 系统测试覆盖 DWG、布局、Handle、DST 打开和引用解析。
- Vue/Playwright 覆盖六步向导、草稿恢复、错误聚焦、取消和重试。
- 正式版本必须在打包后的 Windows WebView2 桌面壳使用真实项目验收。

## 13. 首个实施切片

首个 Spec 只实现一个项目、一种编号规则、一个图纸组和一个输出 DWG，但必须完整贯通：

```text
向导录入 → GenerationPlan → DWG → Handle → DST
→ sheetset.dst + DWG + 图纸目录.xlsx → DST Manager 打开
```

该切片通过 AutoCAD 2016/2020 后，再扩展项目编辑器、规则、模板和多 DWG 并行。禁止先搭建空的企业控制面或全量插件框架。
