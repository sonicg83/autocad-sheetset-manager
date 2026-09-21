---
id: ARCH-INT-002
title: DST Manager 单产品治理与共享平台
status: accepted
owners:
  - integration
created: 2026-09-17
updated: 2026-09-21
related:
  - RFC-INT-001
  - RFC-INT-002
  - RFC-INT-003
  - ADR-INT-001
  - ARCH-INT-001
  - ARCH-DB-001
  - ARCH-DM-001
document_kind: architecture
---

# DST Manager 单产品治理与共享平台

## 1. 取代关系

本文完整取代 `ARCH-INT-001`，是当前文档组织、产品 scope、编号、生命周期、索引和归档的唯一权威架构。`ARCH-INT-001` 只保留文档治理迁移的历史背景，不再承载现行规范。

2026-09-21 接受 [RFC-INT-003](../rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)，DST Builder 作为独立产品直接退场；本文同步收敛为 DST Manager 单产品治理。`dst-builder` 的公开实现由 Git 历史追溯，本地副本位于被 Git 忽略的 `legacy/dst-builder/`；新建图纸集能力归入 DST Manager，由 [PLAN-DM-035](../../../.planning/plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md) 与 [PLAN-DM-036](../../../.planning/plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md) 承接。`dst-builder` 既有编号、文档和备忘保留为只读历史资料。

## 2. 现役产品边界

| 范围 | 责任 | 不负责 |
| --- | --- | --- |
| `dst-manager` | 检查、编辑、修订和安全发布既有 DST/DWG；按已发布图纸标准创建新图纸集（承接 Builder 退场后的能力） | 维护任何已退场产品的项目事实源 |
| `shared` | Manager 已采用的稳定技术契约和知识 | 产品需求、产品 UI 和潜在公共抽象 |
| `integration` | 跨 scope RFC、提案、依赖方向和治理决策 | Manager 私有实现 |

`dst-builder` 已退场，不再是现役 scope：其文档和备忘保留为只读历史资料，公开实现由 Git 历史追溯，本地副本位于被忽略的 `legacy/dst-builder/`，不接收新的需求、架构、计划或待办。`legacy-refactor` 同样只保留历史文档和研究资料。`legacy/`、`lagacy/` 与 `sample/` 仍属于本地私有输入，不得发布。

`shared/` 中形成于旧双项目阶段的现有资料为保持历史链接暂留原位，不自动视为仍被采用；新的共享内容和后续重分类必须经 Manager 真实使用，并在 `integration` 评审后归入。

## 3. 文档目录与编号

```text
docs/
├─ dst-builder/       # 历史只读入口（产品已退场）
├─ dst-manager/
├─ shared/
├─ integration/
└─ legacy-refactor/   # 历史只读入口

.planning/
├─ roadmaps/dst-builder.md   # 历史只读
├─ plans/dst-builder/        # 历史只读
├─ memos/dst-builder/        # 历史证据
```

新正式文档使用以下永久前缀：

| scope | 前缀 |
| --- | --- |
| DST Builder（历史，冻结） | `DB` |
| DST Manager | `DM` |
| Shared | `SH` |
| Integration | `INT` |

已存在的 `DB` 与 `LR` 编号永久保留，不得重用或批量改号，但均只对应历史 scope，不再新增。历史文档可标记为 `superseded` 或 `archived`，并通过 `related` 和正文链接指向取代文档。

除每个产品固定入口 `product/vision.md` 外，正式文档文件名使用“永久 ID + 英文短名称”，例如 `PRD-DB-001-guided-sheetset-generation.md`。Vision 的永久 ID 保存在 YAML 元数据中。正文标题、内容、注释和提交信息继续使用简体中文。Memo 使用 `YYYY-MM-DD-topic.md`，不分配永久编号；Guide、Reference 和 Research 仅在需要稳定交叉引用时分配永久编号。

### 3.1 文档类型与权威位置

| 类型 | 核心问题 | 权威位置 | 生命周期 |
| --- | --- | --- | --- |
| Vision | 产品最终解决什么问题 | `docs/<product>/product/vision.md` | 长期 |
| PRD | 用户、范围、需求和验收标准 | `docs/<product>/product/prds/` | 长期 |
| Spec | 功能或技术能力如何工作 | `docs/<product>/specs/` | 长期 |
| Architecture | 当前系统结构和模块边界 | `docs/<scope>/architecture/` | 长期 |
| ADR | 一项架构决策及其理由 | `docs/<scope>/adr/` | 长期 |
| RFC | 跨产品或高影响提案及其评审结论 | `docs/integration/rfcs/` | 评审期及结论追溯 |
| Guide | 稳定操作或开发方法 | `docs/<scope>/guides/` | 长期 |
| Research | 调研事实、实验和分析 | `docs/<scope>/research/` | 长期 |
| Reference | 跨 scope 稳定参考契约 | `docs/shared/reference/` | 长期 |
| Roadmap | 产品或整合方向的阶段顺序 | `.planning/roadmaps/` | 有时效性 |
| Plan | 已立项工作的可执行计划 | `.planning/plans/<scope>/` | 有时效性 |
| Todo | 尚未形成正式 Plan 的事项 | `.planning/todos/<scope>/` | 临时 |
| Memo | 评审、交接、测试和阶段记录 | `.planning/memos/<scope>/` | 记录性 |

同一内容只保留一个权威位置。导航文档和其他范围只能链接，不复制正文；待办和备忘不得混入 `docs/`，长期知识不得放入 `.planning/`。

单产品功能遵循：

```text
Vision → PRD → Spec → ADR → Plan → 代码、测试和发布
```

跨 scope 能力遵循：

```text
RFC → 评审通过 → 产品 Spec/Architecture、共享 Reference
或 Integration Architecture/ADR → 对应 scope 的实施 Plan
```

类型边界如下：

- PRD 定义用户、问题、范围、需求和验收，不描述类名、数据库表或逐文件实施步骤。
- Spec 可以定义行为、API、状态机、数据结构、异常、安全边界、兼容性和验收测试，但不承担施工清单职责。
- Architecture 描述当前有效结构；未采纳的架构设想进入 RFC 或 Research。
- ADR 一份只记录一个关键决策；结论变化时新增 ADR，并把旧 ADR 标记为 `superseded`。
- Plan 必须具有明确完成条件；完成后记录实际验证，不继续演变为永久架构文档。
- Research 可以提出建议，但建议只有进入 Spec、Architecture 或 ADR 后才成为当前规范。

### 3.2 元数据与生命周期

PRD、Spec、Architecture、ADR、RFC、Roadmap 和 Plan 必须使用 YAML 元数据，至少包含 `id`、`title`、`status`、`owners`、`created`、`updated` 和 `related`。Guide、Reference、Research 和 Memo 按需使用 YAML 元数据；未分配永久 ID 时不得伪造占位编号。`related` 只填写永久文档 ID，正文提供可点击链接。

- 长期文档状态：`draft`、`review`、`accepted`、`superseded`、`archived`。
- Roadmap、Plan 等计划类文档状态：`proposed`、`active`、`completed`、`cancelled`、`blocked`。
- 永久编号一经分配不得重用；文档移动、改名或被取代都保留原编号。
- ADR 结论变化时必须新建 ADR，不得静默改写旧决策。
- Plan 标记 `completed` 前记录实际验证；标记 `blocked` 时记录原因和恢复条件。

### 3.3 索引与归档

- `docs/README.md`、各 scope `README.md` 和 `.planning/README.md` 只承担导航和当前状态摘要。
- 新增、移动、取代或归档正式文档时同步维护相关索引、永久链接和 `related`。
- 根 `docs/` 不平铺业务文档，仓库根 `README.md` 不累积完整架构、调研或交接正文。
- `docs/archive/` 只保存已经失效、仍有独立追溯价值且不能仅靠 Git 历史理解的材料；被新文档取代的正式规范优先原位保留并标记 `superseded`。
- 无长期价值的临时材料依靠 Git 历史保留，不为完整性创建空目录或复制归档。

索引最低要求：

- `docs/README.md` 链接 `dst-manager` 现役产品文档、`shared`、`integration`、当前治理架构、模板和实际存在的归档入口。
- 产品 `README.md` 说明定位与当前状态，并链接 Vision、Roadmap、有效 PRD、Spec、Architecture、ADR 和适用指南；尚不存在的类型不创建空入口。
- `shared/README.md` 按能力域组织链接，并明确真实消费方门禁。
- `integration/README.md` 列出评审中的 RFC、已接受的跨产品决策和整合路线图。
- 仓库根 `README.md` 只承担仓库简介、快速启动和文档入口。

### 3.4 历史 scope：`dst-builder` 与 `legacy-refactor`

`docs/dst-builder/` 与 `docs/legacy-refactor/` 只作为历史资料入口保留。`dst-builder` 的产品实现已按 RFC-INT-003 整体退场：公开实现由 Git 历史追溯，本地副本位于被忽略的 `legacy/dst-builder/`；`.planning/memos/dst-builder/` 保留为历史证据。既有 `DB` 与 `LR` 文档可以继续更正链接或补充封口说明，但不得在历史 scope 新建当前产品需求、架构、Spec、Roadmap 或 Plan。需要长期复用的历史结论必须经核验后写入 `dst-manager`、`shared` 或 `integration` 的唯一权威位置，并链接原始资料。

### 3.5 模板的最小内容

- PRD：背景、目标用户、问题、目标、非目标、需求、验收标准。
- Spec：背景、范围、行为、接口、数据、异常、安全边界、兼容性、测试。
- ADR：背景、决策、备选方案、影响、替代关系。
- RFC：提案、动机、影响范围、迁移路径、开放问题、评审结论。
- Guide：适用范围、前置条件、步骤、验证、故障处理。
- Roadmap：目标阶段、交付结果、依赖、退出条件。
- Plan：目标、前置条件、任务、验证、风险、完成标准。
- Memo：日期、参与背景、事实、临时结论、待跟进事项。

## 4. 代码依赖方向

```text
dst_manager ─→ dst_platform
```

- 公开仓库只有 `dst_manager` 与 `dst_platform` 两个产品/平台包；已退场的 `dst_builder` 不再存在于公开仓库，其实现由 Git 历史追溯，本地副本位于被忽略的 `legacy/dst-builder/`。
- `dst_platform` 不拥有产品用例、产品路由或产品页面，也不依赖任一产品包。
- 候选共享能力必须先在 Manager 内保持稳定；若未来出现第二个真实消费方，必须先经 `integration` RFC 评审证明公共边界，不得以“未来可能复用”为理由提前抽取。
- 提取共享代码时保持 Manager 公共接口和测试门禁，采用渐进迁移，不做一次性仓库重排。

## 5. 共享能力候选

已由 Manager 采用的共享能力包括：

- AutoCAD 版本发现、能力描述和 Core Console 安全执行；
- 固定 CAD 作业协议、超时、日志净化和结果收集；
- DST 字节 Codec、AcSm Schema 与契约校验；
- 临时工作区、路径边界、文件锁、哈希和原子发布；
- Artifact 清单、结构化诊断和通用执行记录。

以下内容保持产品私有：

- Manager 的现有工作区、受控编辑命令、草稿、修订恢复和扩展平台；
- Manager 的 API、页面状态机、导航和版本路线图；
- 已退场 Builder 的项目、图纸分组、生成计划和向导状态仅作为历史实现存在于 Git 历史与 `legacy/dst-builder/`，不再进入任何共享或私有现役边界。

## 6. 交接与退场边界

当前没有跨产品交接契约，也不存在第二条产品线。DST Builder 已退场，不存在与 Manager 的运行时关系；Manager 通过既有 `POST /api/workspaces/open` 打开任意 DST，从磁盘现状建立工作区与基线。新建图纸集能力归入 Manager，由 RFC-INT-003、PLAN-DM-035 与 PLAN-DM-036 承接。

`RFC-INT-002` 与 `ADR-INT-001` 记录了历史上取消交接契约的决策。若未来重新需要跨产品来源追溯，必须先有被接受的 `RFC-INT-*`，不得直接恢复 `HandoffBundle`。

## 7. 演进规则

- 新的跨 scope 契约先进入 `integration` RFC；接受后再写入产品 Spec、Architecture 或共享 Reference。
- 共享能力的实现归属、版本和兼容范围必须可独立测试。
- Manager 的历史兼容要求不阻碍新能力采用更简洁的领域模型；两者冲突时新建 ADR 裁决。
- 产品合并、共同数据库或统一宿主不在当前目标内；如未来提出，必须新建 RFC。
