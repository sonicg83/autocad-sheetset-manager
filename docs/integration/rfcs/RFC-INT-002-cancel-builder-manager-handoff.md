---
id: RFC-INT-002
title: 取消 Builder 与 Manager 的显式交接契约
status: accepted
owners:
  - integration
created: 2026-09-18
updated: 2026-09-18
related:
  - RFC-INT-001
  - ARCH-INT-002
  - ARCH-DB-001
  - ARCH-DM-001
  - SPEC-DB-001
  - PLAN-DB-001
---

# 取消 Builder 与 Manager 的显式交接契约

## 提案

取消 DST Builder 向 DST Manager 的显式交接契约（`SPEC-DB-001` §10 的六步 `HandoffBundle` 交接），并一并取消正式成果包的 `metadata/` 目录与 `drawings/` 包装层。两条产品线以 DST 文件为唯一接口：

- DST Builder 把 `<sheet-number> <title>.dwg`、`sheetset.dst` 与 `图纸目录.xlsx` 发布到一个新建目标目录，构建成功即交付完成；
- DST Manager 通过既有的 `POST /api/workspaces/open` 直接打开该 DST，从磁盘现状建立工作区与基线。

Builder 不再产出清单、哈希或来源元数据，Manager 不再校验成果包完整性，两侧不再共享 `package_id`、`build_id`、`plan_id`、`manifest_sha256` 中任何包级标识。

## 动机

### 一、交接的准入条件与它服务的流程在时序上错位

`SPEC-DB-001` §10 要求 Manager 在交接时验证 manifest 哈希与每个登记文件的大小和 SHA-256，且成果包内不得存在未登记文件。这组条件隐含一个前提：**成果包自发布起保持字节不变**。

真实流程是「Builder 在项目开始时生成框架 → 用户在 AutoCAD 中长期画图与编辑 → Manager 承担中后期的结构调整与成果交付」。DWG 与 DST 在那段人工编辑期里都会被改变。因此在 Manager 真正接触项目文件时：

- 交接要么根本不被调用——用户直接用 `POST /api/workspaces/open` 打开 DST；
- 要么被调用而必然失败——`src/dst_manager/infrastructure/handoff/reader.py` 会因 `DST 哈希与 manifest 登记不符`、`manifest 登记文件 SHA-256 不符` 或 `成果包存在未登记文件` 直接抛 `HANDOFF_INVALID`。

交接口唯一可行的时机是「构建成功后、任何人碰过包之前」，这个窗口在真实流程中长度为 0。因此该契约不是「较少使用」，而是**适用条件过窄**。

### 二、交接成功后的完整性会立刻自毁

`src/dst_manager/application/handoff.py` 把 Manager 的修订目录建在成果包根内：

```python
revision_dir = root / ".dst-manager" / "revisions" / operation_id / "attempt-001"
```

而修订清单的发布目标是 `package.root / entry["path"]`，即包内 `drawings/*.dwg`。**交接即接管**：交接完成后成果包根成为 Manager 的工作目录，`.dst-manager/` 写入包内，后续发布把结果写回 `drawings/`。

「成果包不可变 + manifest 哈希链」只在交接那一瞬间成立，与 `ARCH-INT-002` §2 把 Builder 产出定义为交付成果的语义冲突。

### 三、交接门禁比 Manager 的通用路径更严格，且与真实 DST 冲突

`reader.py` 要求 DST 的每条布局引用都解析到 `drawings/` 内、且命中 manifest 登记集合，否则抛 `DST 引用越出 drawings/`。

但 Manager 的路径解析（`src/dst_manager/infrastructure/acsm_xml/document.py` 的 `resolve_paths`）按「相对路径 → 绝对路径 → 同目录同名 → `root_override` 同名」依次尝试，**绝对路径是合法的候选来源**。这不是疏漏：真实图纸集常见引用工程目录之外的 DWG，AcSm 同时保存 `FileName` 与 `Relative_FileName` 正是为此。

因此该项检查不是「丢了一个安全检查」，而是交接路径独有的、比通用路径更严格且与真实 DST 不兼容的约束。交接硬拒绝的另一个例子是 DST 结构校验：`reader.py` 在 `repair_report.status` 不属于 `VALID` / `REPAIRED` 时直接拒绝，而 `open_workspace` 不设此门禁——Manager 另有修复流程承担结构问题。

取消交接使 Manager 的行为回到一致：**打开并报告诊断**，而不是对同一台机器上同一用户产出的文件硬拒绝。

### 四、交接消失后五个 metadata 文件全部失去消费方

`metadata/manifest.json` 与 `metadata/handoff.json` 的唯一消费方就是交接（哈希链锚点、幂等键与来源身份）。而 `metadata/project-revision.json`、`metadata/generation-plan.json`、`metadata/validation-report.json` **从未被任何代码解析**——Manager 只把三者随 `metadata_entries` 原样搬运到本地基线副本，全仓无解析点；Builder 自身也不回读。

交接退场后 `metadata/` 下五个文件都不再有程序消费方，而 Builder 为它们的字节级确定性（canonical JSON、固定时间戳）持续付出实现与测试成本。

### 五、两侧都已具备替代路径

- Manager：`src/dst_manager/application/service.py` 的 `open_workspace(dst_path, root_override)` 只要求一个存在的 `.dst`，不校验任何 provenance；前端 `web/src/App.vue` 的首屏 `WelcomeView` 已提供「选择 DST 文件」（经 `bridge.select_file("dst")` 原生对话框）与「手填路径」两个入口。
- Builder：`builder-web/src/steps/BuildStep.vue` 已在构建成功后显示 `published_path`。

取消交接不需要在 Manager 侧新增任何入口。

## 影响范围

### 产品与生命周期

```text
DST Builder                              DST Manager
项目建模 → 预览 → 构建 → 发布              打开 DST → 检查 → 编辑 → 修订 → 安全发布
              └────────── 人工 AutoCAD 画图与编辑 ──────────┘
```

`ARCH-INT-002` §2 的责任边界相应调整：Builder 负责生成首版成果并结束，不承担交接；Manager 从它被打开的磁盘现状开始拥有维护历史，不再存在「交接基线」。`ARCH-INT-002` §6「交接边界」整节作废。Builder 向导由七步变为六步。

### 跨项目契约

`HandoffBundle` 契约取消。两侧不再共享 `dst-builder.handoff/v1`、`dst-builder.manifest/v1`，以及 `dst-builder.validation-report/v1` 中的任何包级字段。

`read_handoff_package` 的六步验证（同根路径、受支持 Schema、manifest 哈希、逐文件大小与 SHA-256、未登记文件检测、DST 只读投影与引用边界）不再是跨产品契约。如「动机三」所述，其引用边界与结构状态两项在通用路径中本就不存在，取消后不补等价硬门禁。

### 正式成果布局

现行 §9 要求正式根目录只能包含 `drawings/` 与 `metadata/`，且 `drawings/` 是未来附带资产的约定父目录。取消 `metadata/` 后 `drawings/` 成为根下唯一且无语义的包装层，因此一并扁平化：

```text
<target>/
├─ sheetset.dst
├─ <sheet-number> <title>.dwg
└─ 图纸目录.xlsx
```

DST 的布局引用是相对文件名，与所在目录名无关，因此扁平化不改变任何引用解析。未来附带资产的约定位置改由 `<target>/assets/` 承接，需在修订 §9 时明确。

### 发布安全

`verify_package` 是三处承重调用的核心：`src/dst_builder/infrastructure/filesystem/publisher.py` 的暂存校验（改名之前）与事后校验（改名之后），以及 `src/dst_builder/application/build_recovery.py` 启动时对 PUBLISHING 遗留现场的裁决。它必须被**重写**而不是删除。

校验语义从「manifest 自声明的哈希链」改为「预期产物集合」：

- 目标目录**至少包含** `sheetset.dst`、`<sheet-number> <title>.dwg`、`图纸目录.xlsx`，且每项存在、可读、非空；
- 不再检查目录中是否存在其他文件。

理由：哈希链的信任模型解决的是「对方交来的东西是否等于它声称的那个」，当不存在跨进程消费方时该模型不再必要；发布原子性已由同卷 `os.replace(staging, target)` 保证，校验的职责只需确认产物都写成功了。

**这一改动同时修正一个既有缺陷**：现行 `verify_package` 要求 `top_level == ["drawings", "metadata"]`，用户往成果根放入任何文件都会让后续启动恢复误报 `PUBLISH_RECOVERY_REQUIRED`。它与交接门禁是同一个根因——把「结构未变」当作准入条件。

### 代码、数据与前端

**Manager（净删 616 行实现）**

| 对象 | 位置 |
| --- | --- |
| 交接编排 | `src/dst_manager/application/handoff.py`（285 行） |
| 交接读取与六步验证 | `src/dst_manager/infrastructure/handoff/`（322 + 9 行） |
| 交接端点与错误码 | `POST /api/handoffs/open`、`OpenHandoffRequest`、`HandoffOpenResponse`、`HANDOFF_INVALID`、`HANDOFF_ID_CONFLICT` |
| 来源记录 | `handoff_sources` 表、`get_handoff_source`、`register_handoff`、`HANDOFF_INITIAL_REVISION_KIND` |
| 前端错误文案 | `web/src/i18n/locales/zh-CN/errors.ts` 与 `en-US/errors.ts` 的 handoff 段 |

新增 Alembic 迁移删除 `handoff_sources` 表。`document_revisions.kind` 与 `source_json` 两列**保留**：它们是通用修订元数据，已由 `_revision_json` 暴露给 API 消费方，删除只会增加迁移与序列化回归风险。

**Builder（净删 60 行实现）**

| 对象 | 位置 |
| --- | --- |
| 交接适配器 | `src/dst_builder/application/handoff_adapter.py`（60 行） |
| 交接编排与四个异常 | `handoff_to_manager`、`HandoffUnavailableError`、`HandoffRejectedError`、`HandoffNotPublishedError`、`HandoffPackageMissingError` |
| 交接端点与响应模型 | `POST /api/builds/{id}/handoff`、`HandoffResponse` |
| 向导末步 | `builder-web/src/steps/HandoffStep.vue`、`useWizardStore` 的 `handoffDone` |
| 包装配 | `package.py` 的 manifest / handoff 构造与 `package_id` 派生；`planning.py` 的 metadata 预期产物与路径常量 |

**测试**

删除 `tests/integration/test_builder_handoff_api.py`（497 行）、`tests/unit/test_handoff_reader.py`（305 行）、`tests/handoff_package_factory.py`（196 行）、`tests/builder/unit/test_package_manifest.py`（208 行），合计 1,206 行；改写 `tests/builder/unit/test_planning.py`（预期产物 7 项降为 3 项）、`test_contract_examples.py`、`tests/builder/integration/test_build_recovery.py`、`test_build_api.py`、`test_minimal_loop_fake_cad.py` 的路径断言。

新增：扁平化布局回归；`verify_package` 新语义（目录中存在额外文件不得判为失败）；**用 `open_workspace` 直接打开 Builder 产出的 DST**——这是替代交接的新主路径，必须有集成测试覆盖。

**保留不动**

发布事务（暂存 → 原子改名 → 事后校验 → 启动恢复裁决）、验证报告作为发布门禁（不再落盘）、`open_workspace`、Manager 首屏 `WelcomeView`、attempt 目录的 `metadata/` 子目录（位于 Builder 数据目录，与成果包无关）。

## 迁移路径

按 `ARCH-INT-002` §7，新的跨产品契约先进入 `integration` RFC，接受后再写入产品 Spec、Architecture 或共享 Reference。因此顺序为：

1. 本 RFC 接受。
2. 新增 `ADR-INT-001`，记录「取消交接、以 DST 文件为唯一接口」的决策。`ARCH-INT-002` §6 的结论发生变化，按治理规则新增 ADR 而非静默改写。
3. 修订 `ARCH-INT-002` §2 责任边界与 §6 交接边界。`RFC-INT-001` 正文不改写——它是 2026-09-17 的决策记录；对其中交接相关表述（产品生命周期链、「Builder 在正式交接前拥有唯一项目事实源」）的取代记入 `ADR-INT-001` 的「替代关系」。
4. 修订 `SPEC-DB-001`：§1（范围中的七步引导与「由 DST Manager 显式接管」）、§2（固定用户流程第 7 步「验收与交接」）、§9（布局、`manifest.json`、`handoff.json`、`package_id` 派生）、§11（`POST /api/builds/{id}/handoff` 端点行与 `HANDOFF_INVALID` / `HANDOFF_ID_CONFLICT` 错误码）、§12（验证门禁中「成果包根只有两个目录」「manifest 与 handoff 无循环依赖」与「七步门禁」条目）；§10 整节标记 `superseded` 并保留正文供历史追溯。§3 项目目录中的 `metadata/` 属于 attempt 目录，**不变**。
5. 修订受影响的 dst-builder 长期文档：
   - `docs/dst-builder/README.md`：产品简介与当前状态摘要；
   - `ARCH-DB-001`：§1 目标中「可通过稳定交接契约进入 DST Manager」、§4 组件表的 `HandoffBundle` 行、§7 状态机 `… → BUILD → HANDOFF`、§8 生成管线中的 `→ HandoffBundle`、§10「正式成果与交接」整节、§11 中「不改变……交接契约」、§12 测试门禁中的交接契约测试与七步向导、§13 首个实施切片的输出链；
   - `PRD-DB-001`：§3 问题、§4 目标、§6 核心用户流程、§6.7「验收与交接」、§9 构建与成果需求中的成果结构、§10「交接需求」整节、§11 验收标准；
   - `product/vision.md`：产品定位、两条产品线边界、「正式交接后两边历史独立」表述与引导流程条目。

   vision 与 PRD 属产品级表述，需同步更新对应验收条目而不是只改叙述文字。
6. 同步计划类文档：`.planning/roadmaps/integration.md`、`.planning/roadmaps/dst-builder.md`（阶段 5「Manager 交接与产品化」及其退出条件）与 `.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md` 中 Task 10 / 11 的状态。
7. 实现。建议顺序：先落 Manager 侧新主路径的集成测试（`open_workspace` 打开 Builder 产出），再删 Builder 包装配与 metadata，最后删交接代码与执行迁移——保证每一步都有安全网。本 RFC 的实现跨两个产品、前端与一次数据库迁移，实施计划可按产品拆分为两份，但契约取舍必须作为一个整体一次落地，不得出现只删一侧的中间态。

## 开放问题

1. **`verify_package` 新语义的最终形态**：本文档给出「至少包含预期产物集合」的判定，需在修订 `SPEC-DB-001` §9 时固定为规范文字，并确保 `publisher.py` 与 `build_recovery.py` 两处调用共享同一判定。
2. **Builder 向导的末端动作**：删除 `HandoffStep` 后，向导最后一个动作只剩 `BuildStep` 的「已发布：`<path>`」文本，用户没有跳转到成果目录的手段。是否需要提供「在资源管理器中打开成果目录」或「复制路径」由产品决定。注意 Builder 的 shell 目前未暴露 JS 桥（`src/dst_builder/interfaces/shell.py` 的 `create_window` 未传 `js_api`），Manager 的 `ShellBridge` 是现成参考，但引入桥属于新增工作。
3. **Manager 失去初始修订的补偿**：取消交接后不再有 `kind=handoff_initial` 的永久初始修订。功能上无损失——首次编辑的基线仍由 `editing.py` 的操作前快照保留——但修订历史中不再有「接管时的原始状态」。若将来需要，正确做法是在 Manager 侧提供显式的「建立初始修订」操作，而不是复活交接。
4. **既有成果包的处置**：已发布的成果包带有 `metadata/` 目录。Manager 打开这类目录时是否需要提示或忽略该目录，需在修订 §9 时一并确定。

## 评审结论

2026-09-18 用户在设计评审中确认三条方向：

- 取消 Builder → Manager 的显式交接契约，两条产品线以 DST 文件为唯一接口；
- 取消正式成果包的整个 `metadata/` 目录；
- 一并扁平化 `drawings/` 包装层，目标目录直接包含三件套。

2026-09-18 用户复审本文档并确认接受。本 RFC 据此转为 `accepted`，成为取消交接契约的权威依据；后续按「迁移路径」逐项落地。

评审中保留为未决、不阻断接受的开放问题共 4 项（见上一节）：`verify_package` 新语义的规范文字、Builder 向导末端动作、Manager 初始修订的补偿方式、既有成果包的处置。前三项需在修订 `SPEC-DB-001` §9 或实施计划中确定，第四项在修订 §9 时确定。
