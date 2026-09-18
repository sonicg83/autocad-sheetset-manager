---
id: PLAN-INT-002
title: 取消 Builder 与 Manager 显式交接契约实施计划
status: proposed
owners:
  - integration
created: 2026-09-18
updated: 2026-09-18
related:
  - RFC-INT-002
  - ADR-INT-001
  - ARCH-INT-002
  - ARCH-DB-001
  - ARCH-DM-001
  - SPEC-DB-001
  - PRD-DB-001
  - PLAN-DB-001
---

# 取消 Builder 与 Manager 显式交接契约实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 每个代码任务必须先使用 superpowers:test-driven-development，关闭前必须使用 superpowers:verification-before-completion。不要把本文已冻结的契约取舍重新开放为临场设计问题。

**Goal:** 按 RFC-INT-002 取消 Builder → Manager 的显式交接契约，移除正式成果包的 `metadata/` 目录与 `drawings/` 包装层，使两条产品线以 DST 文件为唯一接口。

**Architecture:** 先完成文档治理传播（ADR 与权威架构、规范），再改 Builder 的成果布局与完整性校验，然后补上「Builder 产出可被 Manager 直接打开」的集成测试作为删除交接前的安全网，最后依次移除 Builder 与 Manager 两侧的交接实现。成果目录改为直接包含 `sheetset.dst`、构建后的 DWG 与 `图纸目录.xlsx`；`verify_package` 的 manifest 哈希链语义改为显式的「预期产物集合」校验，判定函数由调用方传入预期路径集合。

**Tech Stack:** Python 3.12+ / FastAPI / SQLAlchemy 2 / Alembic / pytest / Vue 3 + TypeScript + Vite / Playwright / UV / PowerShell 11。

**Spec:** `docs/integration/rfcs/RFC-INT-002-cancel-builder-manager-handoff.md`

## Global Constraints

- 始终使用简体中文编写代码注释、文档、变更记录与 Git commit message；标识符、协议字段、API 路径与错误码保持原始英文形式。
- 所有文本文件使用 UTF-8。
- 目标系统为 Windows 11，默认 Shell 为 PowerShell；命令必须兼容 PowerShell。
- Python 版本不得低于 3.12；依赖只用 `uv add` / `uv remove` / `uv sync` / `uv run`，禁止 `pip install`。
- 依赖方向不得改变：`dst_builder` 不得 import `dst_manager`；`dst_platform` 不得 import 任一产品包。`tests/architecture/test_product_boundaries.py` 是本约束的门禁。
- 只读打开工作区不得创建 `.dst-manager/`、修改 DST/DWG，也不得更新文件时间戳。
- 不得提交 `.env`、`.agents/`、`.venv/`、缓存、覆盖率文件、Playwright 结果、`web/dist/`、`web/node_modules/`、`.dst-manager-data/`，以及 `plugins/autocad2016/`、`plugins/autocad2020/`、`bin/`、`obj/`。
- 每次修改都要更新根目录 `changelog.md`，并在当前日期章节追加简洁、可核验的记录。
- 修改前检查工作区状态，保留并避开用户已有的无关改动。
- 只暂存本任务涉及的文件；Commit message 使用简体中文、动词开头。
- 不得使用 ADR 新增以外的方式改写既有 ADR 结论；`ARCH-INT-002` §6 的结论变化记入新增的 `ADR-INT-001`。
- `RFC-INT-001` 正文不改写；对其中交接相关表述的取代记入 `ADR-INT-001` 的「替代关系」。
- 运行 pytest 时不要再加 `-q`：`pyproject.toml` 的 `addopts` 已含 `-q`，再加会变成 `-qq` 并吞掉通过计数行，使证据无法核对。用 `uv run python -m pytest <路径>`。

---

## 冻结决策

本计划实现 RFC-INT-002 已接受的三条取舍与两项补充判断，实施过程中不得重新讨论：

1. **取消交接**：删除 `SPEC-DB-001` §10、Manager 的 `POST /api/handoffs/open` 与全部交接代码、Builder 的 `handoff_adapter` 与 `POST /api/builds/{id}/handoff`、`handoff_sources` 表。
2. **取消成果包 `metadata/`**：不再生成 `manifest.json`、`handoff.json`、`project-revision.json`、`generation-plan.json`、`validation-report.json`。验证报告仍然生成并作为发布门禁，只是不再落盘。
3. **扁平化布局**：目标目录直接包含三件套，未来附带资产的约定位置为 `<target>/assets/`。
4. **`verify_package` 改为 `verify_target(root, expected_paths)`**：只断言预期产物存在、可读、非空；不比对内容哈希，不约束目录内的其他文件。预期路径集合由调用方显式传入——发布时来自候选文件映射，启动恢复时来自发布证据新增的 `expected_paths` 字段。空集合判为问题，不得静默放行。
5. **保留 `document_revisions.kind` 与 `source_json`**：它们是通用修订元数据，已被 `_revision_json` 暴露给 API 消费方，删除只会增加迁移与序列化回归风险。

## 本计划明确不解的开放问题

RFC-INT-002 的四个开放问题中，第 1 项（`verify_package` 新语义的规范文字）由 Task 2 的 SPEC §9 与 Task 3 的实现共同解决；第 4 项（既有成果包的处置）由 Task 2 的 SPEC §9 明确为「不读取 `metadata/`、不因此拒绝打开」。**以下两项本计划刻意不解决，不得在实施过程中自行发挥**：

- **Builder 向导的末端动作**（RFC 开放问题 2）：Task 5 删掉 `HandoffStep` 后，向导末步 `BuildStep` 只显示「已发布：`<path>`」文本，用户没有跳转到成果目录的手段。是否补「在资源管理器中打开成果目录」或「复制路径」是产品决策；Builder 的 shell 尚未暴露 JS 桥，补桥属新增工作。本计划只记录该缺口，不实现。
- **Manager 失去初始修订的补偿**（RFC 开放问题 3）：不再有 `kind=handoff_initial` 的永久初始修订。首次编辑的基线仍由操作前快照保留，功能无损失。若将来需要「接管时的原始状态」，应新增显式的「建立初始修订」操作，**不得恢复交接**。本计划不实现该操作。

## 文件结构与职责

```text
src/dst_builder/
├─ domain/
│  ├─ models.py                     # 删 MANIFEST_SCHEMA / HANDOFF_SCHEMA
│  ├─ normalization.py              # 删 package_id_from_manifest_sha256
│  └─ planning.py                   # 路径常量去 drawings/ 前缀；预期产物 7 → 3
├─ application/
│  ├─ builds.py                     # 删交接与 metadata 装配、_report_json、_builder_version
│  └─ build_recovery.py             # verify_target + 证据内的预期产物清单
└─ infrastructure/filesystem/
   ├─ package.py                    # 装配改为三件套；verify_package → verify_target
   ├─ publisher.py                  # verify_target(staging/target, files.keys())
   └─ attempts.py                   # PublishEvidence 增加 expected_paths

src/dst_manager/
├─ application/service.py           # 组合中移除 HandoffOperations
├─ interfaces/api.py                # 删 /api/handoffs/open
├─ interfaces/responses.py          # 删 HandoffOpenResponse
├─ interfaces/message_catalog.py    # 删两条交接错误文案
└─ infrastructure/persistence/database.py  # 删 handoff_sources 模型与两个方法

migrations/versions/
└─ 0008_drop_handoff_sources.py     # 新建：drop table handoff_sources

builder-web/src/
├─ App.vue                          # 末尾改为 BuildStep
├─ components/StepRail.vue          # STEP_NAMES 7 → 6
├─ composables/useWizardGuard.ts    # TOTAL_STEPS 7 → 6
└─ composables/useWizardStore.ts    # 删 handoffDone

web/src/
├─ api/openapi.json + schema.d.ts    # 重新生成
└─ i18n/locales/{zh-CN,en-US}/errors.ts  # 删 handoff 段
```

## 接口与依赖

- Task 3 产出的 `verify_target(root: Path, expected_paths: Iterable[str]) -> tuple[str, ...]` 被 `publisher.publish_candidate` 与 `build_recovery` 共用（RFC-INT-002 开放问题 1）。
- Task 3 产出的 `PublishEvidence.expected_paths: tuple[str, ...]` 是启动恢复取得预期产物集合的唯一来源。
- Task 4 产出的集成测试是 Task 6、7 删除交接代码的安全网，必须在 Task 6 之前通过。
- Task 5 必须先于 Task 6：先移除前端对 `/api/builds/{id}/handoff` 的调用，后端端点才会成为无人调用的死代码。
- `plan.expected_artifacts` 的路径集合必须恒等于 `assemble_package_files` 返回的键集合；Task 3 的 `test_plan_expected_artifacts_match_assembled_files` 固化这一点，Task 3 之后任何单侧改动都会失败。

---

### Task 1: 记录决策（ADR-INT-001 与 ARCH-INT-002）

**Files:**
- Create: `docs/integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md`
- Create: `docs/integration/adr/README.md`
- Modify: `docs/integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md`（§2 表格 `dst-builder` 责任行、§6 交接边界整节）
- Modify: `docs/integration/README.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: `RFC-INT-002`（`accepted`）
- Produces: 稳定 ID `ADR-INT-001`，供 Task 2 的 `related` 与后续索引引用

- [ ] **Step 1: 写 ADR-INT-001**

创建 `docs/integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md`（`docs/integration/adr/` 目录不存在，随本次创建；不提交空目录占位文件）：

```markdown
---
id: ADR-INT-001
title: 取消 Builder 与 Manager 的显式交接契约
status: accepted
owners:
  - integration
created: 2026-09-18
updated: 2026-09-18
related:
  - RFC-INT-002
  - ARCH-INT-002
  - RFC-INT-001
  - SPEC-DB-001
document_kind: adr
---

# 取消 Builder 与 Manager 的显式交接契约

## 背景

`ARCH-INT-002` §6 原规定：Builder 通过版本化 `HandoffBundle` 向 Manager 交接，Manager 验证成果清单与哈希后创建自己的初始修订。该契约由 `SPEC-DB-001` §10 固定为六步流程。

真实流程是「Builder 在项目开始时生成框架 → 用户在 AutoCAD 中长期画图与编辑 → Manager 承担中后期的结构调整与成果交付」。交接的三项准入条件——manifest 登记文件大小与 SHA-256 逐一相符、成果包内不得存在未登记文件、DST 引用只落在 `drawings/` 内——都要求成果包自发布起保持字节不变，而人工编辑期必然破坏这一前提。

此外，交接成功后 Manager 的修订目录与发布目标都落在成果包根内（`.dst-manager/` 与包内 `drawings/*.dwg`），「成果包不可变」的语义在交接瞬间即自毁。

## 决策

取消 Builder 向 Manager 的显式交接契约。两条产品线以 DST 文件为唯一接口：

- Builder 把 `sheetset.dst`、构建后的 DWG 与 `图纸目录.xlsx` 发布到一个新建目标目录，构建成功即交付完成，不再产出清单、哈希或来源元数据；
- Manager 通过既有的 `POST /api/workspaces/open` 打开该 DST，从磁盘现状建立工作区与基线。

正式成果包不再有 `metadata/` 目录，也不再保留 `drawings/` 包装层。

## 备选方案

- **保留交接但降级为「接管现状快照」**：保留 provenance 记录，取消字节相符的准入条件。未采用，因为 Builder 的生成历史（`build_id` / `plan_id`）在真实流程中没有确认的消费者，而保留它需要维护跨产品包级字段与两侧契约测试。
- **保留交接并文档化其窄适用条件**：在包已被人工改动时返回可执行指引改用 `/api/workspaces/open`。未采用，因为该场景在真实流程中是常态而非例外，等于把「用户会撞错」当作设计前提。
- **只取消交接，保留成果包 `metadata/`**：未采用，因为 `manifest.json` 与 `handoff.json` 的唯一消费方就是交接，取消交接后五个 metadata 文件全部失去程序消费方。

## 影响

- Manager 侧净删交接实现 616 行、Builder 侧 60 行；测试删除 1,206 行；`handoff_sources` 表通过新迁移删除。
- `document_revisions.kind` 与 `source_json` 保留为通用修订元数据。
- Manager 不再对同一台机器上同一用户产出的文件做硬拒绝，行为回到「打开并报告诊断」，与其通用路径一致。
- Builder 的 `verify_package` 语义由「manifest 自声明的哈希链」改为「预期产物集合存在、可读、非空」。校验职责只剩确认产物写成功，因为发布原子性已由同卷 `os.replace` 保证。该改动同时消除一个既有缺陷：原判定要求成果根只有 `drawings/` 与 `metadata/` 两个目录，用户往成果根放入任何文件都会让后续启动恢复误报 `PUBLISH_RECOVERY_REQUIRED`。
- Manager 失去 `kind=handoff_initial` 的永久初始修订；首次编辑的基线仍由操作前快照保留。若将来需要「接管时的原始状态」，正确做法是在 Manager 侧新增显式的「建立初始修订」操作。

## 替代关系

本 ADR 取代 `ARCH-INT-002` §6「交接边界」原结论，并取代 `RFC-INT-001` 中与本决策冲突的表述：

- 产品生命周期链中的「发布 → 交接 → 检查 → 编辑」改为「发布」结束后由 Manager 直接打开 DST；
- 「DST Builder 在正式交接前拥有唯一项目事实源」不再成立——人工 AutoCAD 编辑期既不属于 Builder 的项目事实源，也不属于 Manager 的维护历史。

`RFC-INT-001` 正文不改写，保留为 2026-09-17 的决策记录；本 ADR 是其交接相关部分的取代依据。
```

- [ ] **Step 2: 修订 ARCH-INT-002 §2 与 §6**

把 `ARCH-INT-002` §2 表格的两行改为：

```markdown
| `dst-builder` | 从项目数据生成首版 DWG、DST、伴随成果并发布到目标目录 | 交接契约、发布后的日常编辑与修订 |
| `dst-manager` | 检查、编辑、修订和安全发布既有 DST/DWG | 维护 Builder 的项目事实源 |
```

把 §6 整节替换为：

```markdown
## 6. 交接边界

当前没有跨产品交接契约。Builder 发布正式成果后即结束，Manager 通过既有 `POST /api/workspaces/open` 打开成果目录中的 DST，从磁盘现状建立工作区与基线；两侧不共享数据库、不共享包级标识，也不存在交接基线。

`RFC-INT-002` 与 `ADR-INT-001` 记录了该契约的取消决策。若未来重新需要跨产品来源追溯，必须先有被接受的 `RFC-INT-*`，不得直接恢复 `HandoffBundle`。
```

- [ ] **Step 3: 更新整合入口与 changelog**

在 `docs/integration/README.md` 的 RFC 链接之前增加 ADR 一节：

```markdown
- [整合 ADR 索引](adr/README.md)
```

并创建 `docs/integration/adr/README.md`：

```markdown
# 整合 ADR 索引

- [ADR-INT-001：取消 Builder 与 Manager 的显式交接契约](ADR-INT-001-cancel-builder-manager-handoff.md)
```

在 `changelog.md` 顶部追加：

```markdown
## 2026-09-18（ARCH-INT-002 §6 交接边界取消）

- 新增 [ADR-INT-001](docs/integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md)，取代 `ARCH-INT-002` §6「交接边界」原结论与 `RFC-INT-001` 中冲突的产品生命周期表述：Builder 发布即结束，Manager 通过 `POST /api/workspaces/open` 直接打开成果目录中的 DST。
- 修订 `ARCH-INT-002` §2 责任边界与 §6 交接边界，新增 `docs/integration/adr/README.md` 索引并接入整合入口。本次仅修改文档，未改动源码、测试或迁移。
```

- [ ] **Step 4: 验证**

Run:

```powershell
uv run python -c "
import re, sys, yaml, pathlib
root = pathlib.Path('.')
bad = []
for p in [root/'docs/integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md',
          root/'docs/integration/adr/README.md',
          root/'docs/integration/README.md',
          root/'docs/integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md']:
    text = p.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if m:
        data = yaml.safe_load(m.group(1))
        assert data['id'] and data['status'], p
    for link in re.findall(r'\]\(([^)#][^)]*)\)', text):
        if link.startswith(('http', 'mailto')):
            continue
        target = (p.parent / link.split('#')[0]).resolve()
        if not target.exists():
            bad.append(f'{p}: {link}')
print('断链:', bad)
sys.exit(1 if bad else 0)
"
```

Expected: 输出 `断链: []` 且退出码 0。

- [ ] **Step 5: Commit**

```powershell
git add docs/integration/adr docs/integration/README.md docs/integration/architecture/ARCH-INT-002-dst-builder-manager-platform-governance.md changelog.md
git commit -m "记录取消 Builder 与 Manager 交接契约的决策"
```

---

### Task 2: 修订 SPEC-DB-001 与 dst-builder 长期文档

**Files:**
- Modify: `docs/dst-builder/specs/SPEC-DB-001-minimal-generation-loop.md`（§1、§2、§9、§10、§11、§12）
- Modify: `docs/dst-builder/README.md`
- Modify: `docs/dst-builder/architecture/ARCH-DB-001-greenfield-desktop-baseline.md`（§1、§4、§7、§8、§10、§11、§12、§13）
- Modify: `docs/dst-builder/product/prds/PRD-DB-001-guided-sheetset-generation.md`（§3、§4、§6、§6.7、§9、§10、§11）
- Modify: `docs/dst-builder/product/vision.md`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1 的 `ADR-INT-001`
- Produces: 不含交接与 metadata 的 `SPEC-DB-001`，作为 Task 3 实现布局与校验的规范依据

- [ ] **Step 1: 修订 SPEC-DB-001 §1 与 §2**

§1 首段末尾的「发布正式成果包，再由 DST Manager 显式接管」改为「发布正式成果包；DST Manager 直接打开成果目录中的 DST」。同时把「七步引导界面」改为「六步引导界面」。

§2 的固定用户流程表格删除第 7 行（`| 7 验收与交接 | ... |`），并把「七步」相关表述改为「六步」。

- [ ] **Step 2: 修订 SPEC-DB-001 §9**

把 §9 标题下的现行布局与 metadata 段落整体替换为：

```markdown
## 9. 正式成果目录

正式成果目标目录直接包含三个文件，没有包装子目录：

```text
<target>/
├─ sheetset.dst
├─ <sheet-number> <title>.dwg
└─ 图纸目录.xlsx
```

目标目录本身就是交付边界，也是用户在 AutoCAD 中继续工作、由 DST Manager 直接打开的工作目录。因此：

- 不生成 `metadata/` 目录，不生成清单、来源元数据或校验报告文件；
- 不约束目标目录内的其他文件；用户自行放入的 DWG、备份文件、说明文件都是合法的；
- 未来需要交付的附带资产约定放在 `<target>/assets/`，首期不创建该目录。

DST 的布局引用使用相对文件名解析，与所在目录名无关；不再存在 `drawings/` 包装层，也不再有「引用不得逃逸 `drawings/`」的包级约束。

候选包全部验证后，在目标父目录创建唯一暂存目录并以一次原子改名发布。目标已存在、跨卷、父目录不可写或最终改名失败时不发布；首期不会删除或替换用户已有成果。

发布事务的完整性判定使用 `verify_target(root, expected_paths)`：断言本次发布的全部预期产物存在、可读、非空，不比对内容哈希，也不检查目录内是否存在其他文件。预期路径集合由调用方显式给出——发布时来自候选文件映射，启动恢复时来自发布证据中的 `expected_paths`；集合为空判为发布证据缺失，不得静默放行。

已发布的旧版成果包带有 `metadata/` 目录与 `drawings/` 包装层，Manager 打开这类目录时不读取该目录，也不因此拒绝打开。
```

- [ ] **Step 3: 修订 SPEC-DB-001 §10、§11 与 §12**

§10「Manager 交接」：**逐字保留原有六步契约正文**，只在节标题下插入 superseded 说明。不要在正文里删除原契约描述——RFC-INT-002「迁移路径」第 4 步要求「§10 整节标记 `superseded` 并保留正文供历史追溯」，AGENTS.md 也规定被取代文档「正文保持历史可追溯」：

```markdown
## 10. Manager 交接

> **状态：`superseded`。** 本节描述的 `HandoffBundle` 交接契约已由 [RFC-INT-002](../../integration/rfcs/RFC-INT-002-cancel-builder-manager-handoff.md) 与 [ADR-INT-001](../../integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md) 取消：其准入条件要求成果包自发布起保持字节不变，与「Builder 生成框架 → 人工 AutoCAD 编辑 → Manager 承担中后期交付」的真实流程冲突。决策理由与替代关系见该 ADR。以下正文保留为历史记录，不再具有规范性。

（原有 §10 正文从「Manager 新增显式入口 `POST /api/handoffs/open`」到「不能伪造一个无法验证的历史项」逐字保留，不做任何改写。）
```

§11 的端点表格删除 `| POST /api/builds/{id}/handoff | 调用本机 Manager 交接适配器 |` 一行；错误码清单从首期固定集合中删除 `HANDOFF_INVALID` 与 `HANDOFF_ID_CONFLICT`。

§12 的验证门禁清单删除 `成果包根只有两个目录，manifest 与 handoff 无循环依赖；` 与 `Manager 交接成功、幂等、冲突、损坏 metadata、哈希漂移和路径逃逸；` 两条，把 `七步门禁、自动保存/恢复、错误聚焦、键盘流程、浅深主题和 200% 缩放；` 改为 `六步门禁、自动保存/恢复、错误聚焦、键盘流程、浅深主题和 200% 缩放；`，并新增 `目标目录含额外文件时发布后校验与启动恢复均不得失败；`。

- [ ] **Step 4: 修订 ARCH-DB-001**

| 位置 | 改法 |
| --- | --- |
| §1 目标 | 「并可通过稳定交接契约进入 DST Manager」改为「并发布到目标目录，由 DST Manager 直接打开其中的 DST」 |
| §4 组件表 | 删除 `HandoffBundle` 行 |
| §7 状态机 | `PROJECT → RULES → SHEETS → TEMPLATES → PREFLIGHT → BUILD → HANDOFF` 改为 `… → BUILD`；「七步门禁」表述改「六步」 |
| §8 生成管线 | 删除末尾的 `→ HandoffBundle` 环节 |
| §10 | 标题改「正式成果目录」；布局改为三件套（同 Task 2 Step 2 的代码块）；删除 manifest / handoff 与「Manager 只读取 handoff.json」段落，改为「Manager 直接打开 DST，从磁盘现状建立工作区」 |
| §11 | 「不改变领域命令、计划或交接契约」改为「不改变领域命令或生成计划」 |
| §12 | 删除「Builder → Manager 契约测试覆盖正常交接、哈希漂移、缺失文件和不支持版本」；「Vue/Playwright 覆盖七步向导、草稿恢复、错误聚焦、取消、重试和交接」改为「…取消和重试」 |
| §13 | 首个实施切片的输出链 `→ drawings/ + metadata/ → DST Manager 打开` 改为 `→ sheetset.dst + DWG + 图纸目录.xlsx → DST Manager 打开` |

- [ ] **Step 5: 修订 PRD-DB-001 与 vision.md**

PRD-DB-001：

- §3 问题：删除「生成链路与后续维护链路边界不清，缺少正式交接证据。」一行；
- §4 目标：「以固定成果结构和版本化元数据交接给 DST Manager；」改为「把 `sheetset.dst`、DWG 与图纸目录 XLSX 发布到目标目录，由 DST Manager 直接打开；」；
- §6 核心用户流程：删除「交接」环节；
- §6.7 标题「验收与交接」改为「验收」，删除「生成 `handoff.json`，并可一键在 DST Manager 中打开。」改为「在目标目录中直接得到 `sheetset.dst`，并由 DST Manager 打开验证。」；
- §9 构建与成果需求：删除成果结构中的 `metadata/` 分支；
- §10「交接需求」整节替换为「## 10. 交付与接管需求」并写为：Builder 只在目标目录产出一套完整成果且不阻止用户在其中增加文件；Manager 通过打开 DST 接管，不校验成果来源；
- §11 验收标准：删除与交接、`handoff.json`、成果包完整性相关的条目，新增「目标目录含用户自有文件时，重新构建的同名目标仍按目标已存在拒绝，不得覆盖」。

`product/vision.md`：产品定位句「并以可审计的基线包交接给 DST Manager」改为「并发布到目标目录，由 DST Manager 直接打开」；删除「DST Builder 负责交接前的…」与「DST Manager 负责交接后的…」两条中的「交接」依赖表述，改为「发布前」与「打开后」；删除「正式交接后，两边历史独立」条目；引导流程条目中的「和 Manager 交接」删除。

- [ ] **Step 6: 更新 changelog 与验证**

在 `changelog.md` 顶部追加：

```markdown
## 2026-09-18（SPEC-DB-001 与 dst-builder 长期文档同步取消交接）

- 按 `RFC-INT-002` / `ADR-INT-001` 修订 `SPEC-DB-001`：§1 与 §2 改为六步引导且不再由 Manager 显式接管；§9 改为「正式成果目录」并固定三件套布局与 `verify_target` 判定；§10 标记 `superseded`；§11 删除交接端点与两个交接错误码；§12 替换交接与成果包结构相关门禁。
- 同步修订 `ARCH-DB-001`（§1/§4/§7/§8/§10/§11/§12/§13）、`PRD-DB-001`（§3/§4/§6/§6.7/§9/§10/§11）与 `product/vision.md`。本次仅修改文档，未改动源码、测试或迁移。
```

Run（与 Task 1 Step 4 同一条断链检查命令，把文件列表换成本次修改的四份文档）：

```powershell
uv run python -c "
import re, sys, yaml, pathlib
root = pathlib.Path('.')
files = ['docs/dst-builder/specs/SPEC-DB-001-minimal-generation-loop.md',
         'docs/dst-builder/README.md',
         'docs/dst-builder/architecture/ARCH-DB-001-greenfield-desktop-baseline.md',
         'docs/dst-builder/product/prds/PRD-DB-001-guided-sheetset-generation.md',
         'docs/dst-builder/product/vision.md']
bad = []
for name in files:
    p = root / name
    text = p.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if m:
        data = yaml.safe_load(m.group(1))
        assert data['id'] and data['status'], p
    for link in re.findall(r'\]\(([^)#][^)]*)\)', text):
        if link.startswith(('http', 'mailto')):
            continue
        target = (p.parent / link.split('#')[0]).resolve()
        if not target.exists():
            bad.append(f'{name}: {link}')
print('断链:', bad)
sys.exit(1 if bad else 0)
"
```

Expected: `断链: []`，退出码 0。

- [ ] **Step 7: Commit**

```powershell
git add docs/dst-builder changelog.md
git commit -m "同步 dst-builder 规范与长期文档取消交接契约"
```

---

### Task 3: 扁平化成果布局、移除 metadata、重写完整性校验

**Files:**
- Modify: `src/dst_builder/domain/planning.py:75-76`（路径常量）、`:354-370`（`_expected_artifacts`）、`:401`（`plan_payload` 的 `target_dwg_path`）、`:438`（`create_plan` 的 `target_dwg_path`）
- Modify: `src/dst_builder/domain/models.py:18-19,46,48`（删两个 Schema 常量）
- Modify: `src/dst_builder/domain/normalization.py:17,51`（删 `package_id_from_manifest_sha256`）
- Modify: `src/dst_builder/infrastructure/filesystem/package.py`（整文件重写）
- Modify: `src/dst_builder/infrastructure/filesystem/publisher.py:70,85`
- Modify: `src/dst_builder/infrastructure/filesystem/attempts.py`（`PublishEvidence` 与读写函数）
- Modify: `src/dst_builder/application/builds.py:189-199,352-353,407,542-543,594-617`
- Modify: `src/dst_builder/application/build_recovery.py:25,155`
- Create: `tests/builder/unit/test_package_layout.py`
- Delete: `tests/builder/unit/test_package_manifest.py`
- Delete: `tests/integration/test_builder_handoff_api.py`
- Delete: `tests/unit/test_handoff_reader.py`
- Delete: `tests/handoff_package_factory.py`
- Modify: `tests/builder/unit/test_planning.py:416-431`
- Modify: `tests/builder/unit/test_contract_examples.py:1-30,102-130`
- Modify: `tests/builder/unit/test_normalization.py:20,74`
- Modify: `tests/builder/unit/test_builder_publisher.py:22-48` 及其用例断言
- Modify: `tests/builder/integration/test_build_recovery.py:262-296,327-382`
- Modify: `tests/builder/integration/test_build_api.py:110`
- Modify: `tests/builder/integration/test_minimal_loop_fake_cad.py:175-177`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: 无
- Produces:
  - `assemble_package_files(*, plan: GenerationPlanV1, dst_bytes: bytes, dwg_bytes: bytes, catalog_bytes: bytes) -> dict[str, bytes]`
  - `verify_target(root: Path, expected_paths: Iterable[str]) -> tuple[str, ...]`
  - `PublishEvidence(target: Path, staging: Path, recorded_at: str, expected_paths: tuple[str, ...])`
  - `write_publish_evidence(attempt_metadata_dir: Path, *, target: Path, staging: Path, expected_paths: Sequence[str]) -> None`
  - `plan.expected_artifacts` 恒为三项，路径与 `assemble_package_files` 的键一致

- [ ] **Step 1: 写失败测试**

创建 `tests/builder/unit/test_package_layout.py`：

```python
"""正式成果布局与完整性校验（RFC-INT-002 / SPEC-DB-001 §9）。

成果目标目录直接包含三件套，不再有 ``drawings/`` 包装层与 ``metadata/``；
``verify_target`` 只断言预期产物存在、可读、非空，不比对内容哈希，也不
约束目录内的其他文件——目标目录就是用户的图纸集工作目录。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from dst_builder.domain.models import (
    DRAFT_SCHEMA_VERSION,
    AssetRole,
    AssetSnapshot,
    GenerationPlanV1,
    NumberingInput,
    ProjectRevisionV1,
    RevisionProject,
    SheetInput,
    TemplateInput,
)
from dst_builder.domain.planning import create_plan
from dst_builder.infrastructure.filesystem.package import (
    assemble_package_files,
    verify_target,
)

REVISION_SHA = "a" * 64
DWG_PATH = "A-001 首层平面图.dwg"


def _make_plan() -> GenerationPlanV1:
    revision = ProjectRevisionV1(
        schema_version=DRAFT_SCHEMA_VERSION,
        ruleset_version=1,
        project=RevisionProject(name="示例工程", stage="施工图", discipline="建筑"),
        numbering=NumberingInput(prefix="A-", start=1, width=3),
        cad_version="2020",
        sheets=(SheetInput(title="首层平面图"),),
        template=TemplateInput(
            base_asset_id="3f6b5a24-6a8e-4c2a-9c8f-0f5d7a1b2c31",
            layout_asset_id="8c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
            source_layout="A1",
        ),
        assets=(
            AssetSnapshot(role=AssetRole.BASE, relative_path="assets/base/x.dwg", sha256="a" * 64, size=10),
            AssetSnapshot(role=AssetRole.LAYOUT, relative_path="assets/layout/y.dwg", sha256="b" * 64, size=20),
        ),
        revision_sha256=REVISION_SHA,
        revision_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"dst-builder:revision:{REVISION_SHA}")),
    )
    return create_plan(revision)


def _make_files(**overrides) -> dict[str, bytes]:
    kwargs = {
        "plan": _make_plan(),
        "dst_bytes": b"dst-bytes",
        "dwg_bytes": b"dwg-bytes",
        "catalog_bytes": b"xlsx-bytes",
    }
    kwargs.update(overrides)
    return assemble_package_files(**kwargs)


def _write(root: Path, files: dict[str, bytes]) -> None:
    for path, content in files.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def test_assembled_files_sit_directly_in_target_root() -> None:
    files = _make_files()
    assert set(files) == {"sheetset.dst", DWG_PATH, "图纸目录.xlsx"}
    assert all("/" not in path for path in files)


def test_plan_expected_artifacts_match_assembled_files() -> None:
    plan = _make_plan()
    files = _make_files(plan=plan)
    assert {artifact.path for artifact in plan.expected_artifacts} == set(files)
    assert {artifact.path: artifact.role for artifact in plan.expected_artifacts} == {
        "sheetset.dst": "dst",
        DWG_PATH: "dwg",
        "图纸目录.xlsx": "sheet-catalog",
    }


def test_assembled_files_are_deterministic() -> None:
    assert _make_files() == _make_files()


def test_verify_target_accepts_complete_target(tmp_path: Path) -> None:
    files = _make_files()
    _write(tmp_path, files)
    assert verify_target(tmp_path, tuple(files)) == ()


def test_verify_target_ignores_unexpected_files(tmp_path: Path) -> None:
    """目标目录就是用户的工作目录：额外文件与子目录不得导致校验失败。"""
    files = _make_files()
    _write(tmp_path, files)
    (tmp_path / "notes.txt").write_text("用户备注", encoding="utf-8")
    (tmp_path / "backup").mkdir()
    (tmp_path / "backup" / "sheetset.bak").write_bytes(b"bak")
    assert verify_target(tmp_path, tuple(files)) == ()


def test_verify_target_does_not_detect_content_change(tmp_path: Path) -> None:
    """改为集合校验后不再比对内容哈希——这是 RFC-INT-002 的有意取舍。"""
    files = _make_files()
    _write(tmp_path, files)
    (tmp_path / "sheetset.dst").write_bytes(b"edited-by-user")
    assert verify_target(tmp_path, tuple(files)) == ()


def test_verify_target_detects_missing_file(tmp_path: Path) -> None:
    files = _make_files()
    _write(tmp_path, files)
    (tmp_path / "图纸目录.xlsx").unlink()
    problems = verify_target(tmp_path, tuple(files))
    assert any("图纸目录.xlsx" in problem for problem in problems)


def test_verify_target_detects_empty_file(tmp_path: Path) -> None:
    files = _make_files()
    _write(tmp_path, files)
    (tmp_path / "sheetset.dst").write_bytes(b"")
    problems = verify_target(tmp_path, tuple(files))
    assert any("sheetset.dst" in problem for problem in problems)


def test_verify_target_rejects_empty_expected_set(tmp_path: Path) -> None:
    """空预期集合是发布证据缺失，不得静默放行。"""
    files = _make_files()
    _write(tmp_path, files)
    assert verify_target(tmp_path, ()) == ("发布证据缺少预期产物清单",)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/builder/unit/test_package_layout.py -q`

Expected: 收集失败或全部失败，报 `ImportError: cannot import name 'verify_target'`。

- [ ] **Step 3: 改路径常量与预期产物集合**

`src/dst_builder/domain/planning.py`：

```python
SHEETSET_PATH = "sheetset.dst"
SHEET_CATALOG_PATH = "图纸目录.xlsx"
```

```python
def _expected_artifacts(dwg: str) -> tuple[ExpectedArtifact, ...]:
    """正式成果全部预期文件（§9）：目标目录直接包含 DST、DWG 与图纸目录。"""
    entries = (
        ExpectedArtifact(path=SHEETSET_PATH, role="dst", required=True),
        ExpectedArtifact(path=dwg, role="dwg", required=True),
        ExpectedArtifact(path=SHEET_CATALOG_PATH, role="sheet-catalog", required=True),
    )
    return tuple(sorted(entries, key=lambda item: item.path))
```

`plan_payload` 与 `create_plan` 中的 `target_dwg_path=f"drawings/{drawing}"` 都改为 `target_dwg_path=drawing`。

- [ ] **Step 4: 重写 package.py**

`src/dst_builder/infrastructure/filesystem/package.py` 整体替换为：

```python
"""正式成果装配与完整性校验（SPEC-DB-001 §9，RFC-INT-002）。

成果目标目录直接包含 ``sheetset.dst``、构建后的 DWG 与 ``图纸目录.xlsx``；
不再生成 ``drawings/`` 包装层与 ``metadata/``，因此不存在清单、哈希链与
来源元数据。:func:`verify_target` 只断言预期产物集合存在、可读、非空——
目标目录就是用户的图纸集工作目录，允许用户在其中放入其他文件。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from dst_builder.domain.models import GenerationPlanV1
from dst_builder.domain.planning import SHEET_CATALOG_PATH, SHEETSET_PATH

__all__ = [
    "assemble_package_files",
    "verify_target",
]


def assemble_package_files(
    *,
    plan: GenerationPlanV1,
    dst_bytes: bytes,
    dwg_bytes: bytes,
    catalog_bytes: bytes,
) -> dict[str, bytes]:
    """装配全部正式文件，键为成果目标目录内的相对路径。"""
    return {
        SHEETSET_PATH: dst_bytes,
        plan.drawing_task.target_dwg_path: dwg_bytes,
        SHEET_CATALOG_PATH: catalog_bytes,
    }


def verify_target(root: Path, expected_paths: Iterable[str]) -> tuple[str, ...]:
    """校验目标目录至少包含预期产物集合；返回问题列表（空元组 = 通过）。

    ``expected_paths`` 由调用方显式给出：发布时来自候选文件映射，启动恢复
    时来自发布证据的 ``expected_paths``。空集合视为发布证据缺失并判为问题，
    避免「没有预期产物即视为完整」的静默放行。不比对内容哈希，也不约束目录
    内的其他文件。
    """
    root = Path(root)
    paths = tuple(expected_paths)
    if not paths:
        return ("发布证据缺少预期产物清单",)
    problems: list[str] = []
    for relative in paths:
        candidate = root / relative
        if not candidate.is_file():
            problems.append(f"预期产物缺失：{relative}")
            continue
        try:
            size = candidate.stat().st_size
        except OSError as error:
            problems.append(f"预期产物不可读：{relative}（{error}）")
            continue
        if size == 0:
            problems.append(f"预期产物为空：{relative}")
    return tuple(problems)
```

同时删除 `src/dst_builder/domain/models.py` 的 `MANIFEST_SCHEMA`、`HANDOFF_SCHEMA` 及其 `__all__` 条目，删除 `src/dst_builder/domain/normalization.py` 的 `package_id_from_manifest_sha256` 及其 `__all__` 条目。

- [ ] **Step 5: 改发布证据与发布器**

`src/dst_builder/infrastructure/filesystem/attempts.py`：

```python
@dataclass(frozen=True, slots=True)
class PublishEvidence:
    """发布证据：PUBLISHING 阶段的目标、暂存绝对路径与预期产物清单。"""

    target: Path
    staging: Path
    recorded_at: str
    expected_paths: tuple[str, ...]


def write_publish_evidence(
    attempt_metadata_dir: Path,
    *,
    target: Path,
    staging: Path,
    expected_paths: Sequence[str],
) -> None:
    """在 PUBLISHING 进入点写发布证据（改名前落盘，供启动恢复裁决）。"""
    payload = {
        "target": str(target),
        "staging": str(staging),
        "recorded_at": utc_now_iso(),
        "expected_paths": sorted(expected_paths),
    }
    attempt_metadata_dir.mkdir(parents=True, exist_ok=True)
    (attempt_metadata_dir / PUBLISH_EVIDENCE_FILE).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
```

`read_publish_evidence` 在 `recorded_at` 校验之后增加：

```python
    expected = payload.get("expected_paths", [])
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        raise PublishEvidenceError("发布证据的 expected_paths 非法")
```

并把返回改为：

```python
    return PublishEvidence(
        target=target,
        staging=staging,
        recorded_at=payload["recorded_at"],
        expected_paths=tuple(expected),
    )
```

`from collections.abc import Sequence` 需加入 imports。

`src/dst_builder/infrastructure/filesystem/publisher.py`：import 改为 `from dst_builder.infrastructure.filesystem.package import verify_target`，并把两处调用改为：

```python
        problems = verify_target(staging, tuple(files))
```

```python
    problems = verify_target(target, tuple(files))
```

`src/dst_builder/application/build_recovery.py`：import 改为 `verify_target`，第 155 行改为：

```python
        problems = verify_target(target, evidence.expected_paths)
```

- [ ] **Step 6: 改 builds.py**

`src/dst_builder/application/builds.py`：

1. 删除 `_builder_version()` 函数定义（约 189-196 行）。
2. 删除 `_report_json(report)` 函数定义（约 198-206 行）。
3. 删除第 352-353 行的 `plan_json = ...` 与 `revision_json = ...`，并把第 407 行 `self._run_build, build_id, attempt, plan, revision_json, plan_json, target` 改为 `self._run_build, build_id, attempt, plan, target`。
4. 删除 `_run_build` 的 `revision_json: str` 与 `plan_json: str` 形参（约 542-543 行）。
5. 装配调用改为：

```python
            candidate = assemble_package_files(
                plan=plan,
                dst_bytes=dst_bytes,
                dwg_bytes=(self._project_root / _built_dwg_relative(build_id, attempt)).read_bytes(),
                catalog_bytes=catalog_bytes,
            )
```

`report = build_validation_report(...)` 与 `if report.blocking: raise DstValidationError(report.issues)` 保留不动——验证报告仍是发布门禁，只是不再落盘。

6. 第 616 行改为：

```python
            write_publish_evidence(
                dirs.metadata, target=target, staging=staging, expected_paths=tuple(candidate)
            )
```

- [ ] **Step 7: 运行测试确认通过**

Run: `uv run pytest tests/builder/unit/test_package_layout.py -q`

Expected: `9 passed`（初稿写 10 有误，`test_package_layout.py` 共 9 个用例）。

- [ ] **Step 8: 更新受影响的既有测试**

- 删除 `tests/builder/unit/test_package_manifest.py`（manifest / handoff 契约整体作废，其完整性用例已由 `test_package_layout.py` 覆盖）。
- **同时删除交接测试面**：`tests/integration/test_builder_handoff_api.py`（497 行）、`tests/unit/test_handoff_reader.py`（305 行）与 `tests/handoff_package_factory.py`（196 行）。

  **为什么必须在本任务删，而不是留给 Task 6 / Task 7**：`tests/handoff_package_factory.py` 第 40-43 行 `from dst_builder.infrastructure.filesystem.package import MANIFEST_FILE, assemble_package_files`，并调用旧签名的 `assemble_package_files(revision_json=..., plan_json=..., report_json=..., build_id=..., builder_version=..., created_at=...)` 来拼出 `drawings/` + `metadata/` 布局。本任务删 `MANIFEST_FILE`、删两个 Schema 常量并改签名后，该夹具会先 `ImportError` 再 `TypeError`，连带 `test_builder_handoff_api.py` 与 `test_handoff_reader.py` 一起收集失败——不删就不可能“本任务结束后工作树仍绿”。

  它也无法低成本改造：夹具的生产用途是合成一份**真实 Builder 工厂产出的合规成果包**（见其 docstring），而本任务之后那种布局已不存在，改造后它只能手写一份与生产无关的假包。因此正确的投资是连同它要测的被删契约一起移除。Manager 的 `reader.py` 与 Builder 的 `handoff_adapter` 在本任务后到 Task 6 / Task 7 删除前处于无测试覆盖状态，这是可接受的中间态：它们只被删除、不被修改，Task 4 已为替代路径建立安全网。
- `tests/builder/unit/test_planning.py::test_expected_artifacts_list_full_deliverable_set`：期望集合改为 `{"sheetset.dst", "A-001 首层平面图.dwg", "图纸目录.xlsx"}`，断言仍检查 `paths == sorted(paths)` 与 `all(artifact.required ...)`。
- `tests/builder/unit/test_contract_examples.py`：删除 `HANDOFF_SCHEMA` / `MANIFEST_SCHEMA` / `package_id_from_manifest_sha256` 的 import；删除 `test_handoff_schema_contract`；把 `test_manifest_and_expected_artifacts_agree` 改名为 `test_expected_artifacts_match_assembled_files` 并断言 `{a.path for a in plan.expected_artifacts} == {"sheetset.dst", "A-001 首层平面图.dwg", "图纸目录.xlsx"}`。
- `tests/builder/unit/test_normalization.py`：删除使用 `package_id_from_manifest_sha256` 的用例及其 import。
- `tests/builder/unit/test_builder_publisher.py`：`_FILES` 改为三项扁平结构，并删除仅由 manifest 使用的 `json` / `hashlib` import（否则 Ruff 报未使用导入）。

```python
_FILES = {
    "sheetset.dst": _DST,
    "A-001 平面.dwg": b"dwg",
    "图纸目录.xlsx": b"xlsx",
}
```

`test_publish_places_complete_package_at_target` 的断言改为按内容集合比较，避免依赖目录迭代顺序：

```python
    assert {path.read_bytes() for path in target.iterdir()} == set(_FILES.values())
```

- `tests/builder/integration/test_build_api.py:110` 与 `tests/builder/integration/test_minimal_loop_fake_cad.py:175-177`：import 改为 `verify_target`，断言改为从目标目录自身推导 DWG 名，避免硬编码：

```python
    dwg = next(env.target.glob("*.dwg")).name
    assert verify_target(env.target, ("sheetset.dst", dwg, "图纸目录.xlsx")) == ()
```
- `tests/builder/integration/test_build_recovery.py`：`test_publishing_with_tampered_target_requires_manual_recovery` 改名为 `test_publishing_with_content_changed_target_still_converges`，断言收敛为 `SUCCEEDED`（内容哈希不再参与判定）；新增 `test_publishing_with_missing_expected_artifact_requires_manual_recovery`（从目标目录删除 `图纸目录.xlsx` 后期望 `PUBLISH_RECOVERY_REQUIRED`）；`test_publishing_file_io_runs_outside_database_transaction` 中 monkeypatch 的符号名改为 `verify_target`。
- `tests/builder/integration/test_build_api.py:110` 与 `tests/builder/integration/test_minimal_loop_fake_cad.py:175-177`：import 改为 `verify_target`，断言改为 `verify_target(env.target, ("sheetset.dst", "<图名>.dwg", "图纸目录.xlsx")) == ()`，DWG 名取自 `plan.drawing_task.target_dwg_path` 或直接遍历 `env.target.glob("*.dwg")`。

- [ ] **Step 9: 全量验证**

Run:

```powershell
uv run ruff check .
uv run pytest -q
```

Expected: Ruff 无告警；pytest 全部通过。

- [ ] **Step 10: 更新 changelog 并提交**

在 `changelog.md` 顶部追加：

```markdown
## 2026-09-18（Builder 正式成果布局扁平化与 metadata 移除）

- `SHEETSET_PATH` / `SHEET_CATALOG_PATH` 去掉 `drawings/` 前缀，`_expected_artifacts` 由 7 项降为 3 项；`assemble_package_files` 只装配 `sheetset.dst`、构建后的 DWG 与 `图纸目录.xlsx`，不再生成 `metadata/` 下的清单、来源元数据与校验报告文件。
- `verify_package` 重写为 `verify_target(root, expected_paths)`：只断言预期产物存在、可读、非空，不比对内容哈希、不约束目录内其他文件；空预期集合判为发布证据缺失。`publish_candidate` 与 `build_recovery` 共用同一判定，发布证据新增 `expected_paths` 字段。
- 该改动同时修正既有缺陷：原判定要求成果根只有 `drawings/` 与 `metadata/` 两个目录，用户往成果根放入文件会让启动恢复误报 `PUBLISH_RECOVERY_REQUIRED`。
- 删除失去使用方的 `MANIFEST_SCHEMA`、`HANDOFF_SCHEMA`、`package_id_from_manifest_sha256`，以及 `builds.py` 中仅为 metadata 服务的 `_report_json`、`_builder_version` 与 revision/plan JSON 传递。验证报告仍作为发布门禁，只是不再落盘。
```

```powershell
git add src/dst_builder tests/builder changelog.md
git commit -m "扁平化 Builder 正式成果布局并移除 metadata 目录"
```

---

### Task 4: 新增 Builder 产出可被 Manager 直接打开的集成测试

**Files:**
- Create: `tests/builder/integration/test_builder_output_opens_in_manager.py`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 3 的扁平布局（`env.target` 直接含 `sheetset.dst`）；`tests/builder/integration/conftest.py` 的 `env` 夹具与 `FakeDrawingBuilder`
- Produces: Task 6、7 删除交接代码前的安全网——替代交接的新主路径的回归测试

**放在 `tests/builder/integration/` 的理由**：该文件需要复用 `env` 夹具（真实 Builder 发布链路 + fake CAD）。`tests/architecture/test_product_boundaries.py` 只扫描 `src/`，测试文件同时 import 两个产品包不违反依赖门禁；`tests/integration/` 无法导入 `tests/builder/integration/` 的夹具，复制一份会与该夹具的后续演进脱钩。

- [ ] **Step 1: 写测试**

创建 `tests/builder/integration/test_builder_output_opens_in_manager.py`：

```python
"""Builder 产出可被 Manager 直接打开（RFC-INT-002 / SPEC-DB-001 §9）。

替代交接契约的新主路径：Builder 发布到目标目录后，Manager 用既有
``POST /api/workspaces/open`` 打开其中的 DST，从磁盘现状建立工作区与
基线。该测试是移除交接代码前的安全网。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dst_manager.config import Settings
from dst_manager.interfaces.api import create_app


def _publish(env) -> Path:
    """用真实 Builder 发布链路把三件套写入目标目录，返回目标目录。"""
    plan = env.submit_plan()
    env.confirm_plan(plan["plan_id"])
    build = env.client.post("/api/builds", json={"plan_id": env.plan_id}).json()
    final = env.wait_terminal(build["build_id"])
    assert final["status"] == "SUCCEEDED", final
    assert Path(final["published_path"]) == env.target
    return env.target


def test_manager_opens_builder_published_dst(tmp_path: Path, env) -> None:
    target = _publish(env)

    # 扁平布局：三件套直接位于目标目录
    assert sorted(path.name for path in target.iterdir()) == [
        "A-001 首层平面图.dwg",
        "sheetset.dst",
        "图纸目录.xlsx",
    ]

    manager = TestClient(create_app(Settings(data_dir=tmp_path / "manager-data")))
    response = manager.post(
        "/api/workspaces/open", json={"dst_path": str(target / "sheetset.dst")}
    )
    assert response.status_code == 200, response.text
    workspace = response.json()

    # 工作区以 DST 所在目录为根，并把 DWG 解析到该目录内（键路径见 WorkspaceResponse）
    assert Path(workspace["root"]).resolve() == target.resolve()
    layout = workspace["sheet_set"]["subsets"][0]["sheets"][0]["layout"]
    assert Path(layout["resolved_path"]).parent == target.resolve()
    assert Path(layout["resolved_path"]).name.endswith(".dwg")
    assert workspace["unreferenced_dwgs"] == []


def test_manager_open_ignores_user_added_files(tmp_path: Path, env) -> None:
    """目标目录是用户的工作目录：Manager 打开时不得因额外文件而失败。"""
    target = _publish(env)
    (target / "notes.txt").write_text("用户备注", encoding="utf-8")
    (target / "backup").mkdir()
    (target / "backup" / "sheetset.bak").write_bytes(b"bak")

    manager = TestClient(create_app(Settings(data_dir=tmp_path / "manager-data")))
    response = manager.post(
        "/api/workspaces/open", json={"dst_path": str(target / "sheetset.dst")}
    )
    assert response.status_code == 200, response.text
```

- [ ] **Step 2: 运行测试**

Run: `uv run pytest tests/builder/integration/test_builder_output_opens_in_manager.py -q`

Expected: `2 passed`。

- [ ] **Step 3: 回归 Builder 与 Manager 两侧**

Run:

```powershell
uv run pytest tests/builder tests/integration/test_api.py -q
```

Expected: 全部通过。

- [ ] **Step 4: 更新 changelog 并提交**

在 `changelog.md` 顶部追加：

```markdown
## 2026-09-18（新增 Builder 产出直接由 Manager 打开的集成测试）

- 新增 `tests/builder/integration/test_builder_output_opens_in_manager.py`：用真实 Builder 发布链路产出扁平成果目录后，Manager 以既有 `POST /api/workspaces/open` 打开其中的 `sheetset.dst`，断言工作区根为目标目录且解析到 Builder 产出的 DWG；另覆盖目标目录含用户自有文件与子目录时打开仍成功。该测试是移除交接代码前的安全网。本次未修改源码。
```

```powershell
git add tests/builder/integration/test_builder_output_opens_in_manager.py changelog.md
git commit -m "新增 Builder 产出由 Manager 直接打开的集成测试"
```

---

### Task 5: Builder 向导移除交接步

**Files:**
- Modify: `builder-web/src/composables/useWizardGuard.ts:6`
- Modify: `builder-web/src/components/StepRail.vue:7`
- Modify: `builder-web/src/App.vue:6,52-53`
- Modify: `builder-web/src/composables/useWizardStore.ts:92,133,213,244,404`
- Modify: `builder-web/src/composables/useWizardGuard.spec.ts`（7 元素 `Completion` 常量与 `toBe(7)` 字面量）
- Modify: `builder-web/src/steps/ReviewStep.vue:30`（第 5 步预览的 `artifactPath`）
- Delete: `builder-web/src/steps/HandoffStep.vue`
- Modify: `builder-web/tests/e2e/helpers/backend-mock.ts:69,262,298-301`
- Modify: `builder-web/tests/e2e/wizard-flow.spec.ts:72-74`
- Modify: `builder-web/tests/e2e/wizard-real-backend.spec.ts:4,29-30`
- Modify: `changelog.md`

**Interfaces:**
- Consumes: 无
- Produces: 向导 6 步、不再调用 `POST /api/builds/{id}/handoff` 的前端；Task 6 据此确认后端端点已无调用方

- [ ] **Step 1: 改步骤数与步骤名**

`builder-web/src/composables/useWizardGuard.ts`：

```typescript
export const TOTAL_STEPS = 6;
```

并把文件首行注释改为 `// 六步门禁状态机（SPEC-DB-001 §2 / ARCH-DB-001 §7）：` 与 `// PROJECT → RULES → SHEETS → TEMPLATES → PREFLIGHT → BUILD。`。

`builder-web/src/components/StepRail.vue`：

```typescript
const STEP_NAMES = ["创建项目", "配置规则", "编排图纸", "匹配模板", "构建前检查", "构建成果"] as const;
```

- [ ] **Step 2: 改路由与状态仓库**

`builder-web/src/App.vue`：删除第 6 行 `import HandoffStep from "./steps/HandoffStep.vue";`，把第 52-53 行改为：

```html
    <BuildStep v-else />
```

`builder-web/src/composables/useWizardStore.ts`：删除接口中的 `handoffDone: Ref<boolean>;`（第 92 行）、`const handoffDone = ref(false);`（第 133 行）、completion 数组最后一项 `handoffDone.value,`（第 213 行）、`handoffDone.value = false;`（第 244 行）与返回对象中的 `handoffDone,`（第 404 行）。

- [ ] **Step 3: 修正成果路径展示的前后端不一致（Task 3 审查 Important 发现，由本任务承接）**

Task 3 已把服务端的产物路径改为目标目录内的裸文件名（`planning.py` 的 `SHEETSET_PATH` / `target_dwg_path`；`validation.py:190`），但前端仍在两处硬编码旧形状：

- `builder-web/src/steps/ReviewStep.vue:30` 的第 5 步预览：`artifactPath: \`drawings/${layoutName}.dwg\`` → 改为裸文件名（与 `dwgName` 一致）。该页在提交前后分别显示前端派生值与服务端返回值，不改就会自相矛盾。
- `builder-web/tests/e2e/helpers/backend-mock.ts:262`：`artifact_path: "drawings/A-001 首层平面图.dwg"` → 改为裸文件名。**不改则 e2e 永远发现不了这个漂移**。

注意：`/api/plans` 的 `artifact_path` 是服务端字段，本步骤只改前端守卫与 mock 夹具，不改 `src/dst_builder`。

- [ ] **Step 4: 删除交接步组件**

删除 `builder-web/src/steps/HandoffStep.vue`。

- [ ] **Step 5: 改 e2e**

`builder-web/tests/e2e/helpers/backend-mock.ts`：删除第 69 行的 `handoff: 0,` 计数字段与第 298-301 行的 `POST /api/builds/build-1/handoff` 路由分支。

`builder-web/tests/e2e/wizard-flow.spec.ts`：删除第 72-74 行的交接按钮点击与结果断言；若该用例随后断言向导完成状态，改为断言第 6 步「构建成果」显示 `published-path`。

`builder-web/tests/e2e/wizard-real-backend.spec.ts`：删除第 4 行注释中的交接说明与第 29-30 行对 `/api/builds/[^/]+/handoff$` 的 route mock。

- [ ] **Step 6: 验证**

Run:

```powershell
Set-Location builder-web
npm run test:unit
npm run build
npm run test:e2e
Set-Location ..
```

Expected: `vue-tsc` 无类型错误、Vite 构建成功、Playwright 全部通过。若 `wizard-flow.spec.ts` 的步骤序号断言（含 `rail-step-7`）失败，按 6 步改为最大 `rail-step-6`。

- [ ] **Step 7: 更新 changelog 并提交**

在 `changelog.md` 顶部追加：

```markdown
## 2026-09-18（Builder 向导移除交接步，七步降为六步）

- 删除 `builder-web/src/steps/HandoffStep.vue` 与向导中的交接调用；`TOTAL_STEPS` 由 7 改为 6，`STEP_NAMES` 与 `App.vue` 路由收口到「构建成果」为末步，`useWizardStore` 移除 `handoffDone` 及其在 completion 与重置逻辑中的引用。
- 修正第 5 步预览的成果路径展示：`ReviewStep.vue` 的 `artifactPath` 与 e2e 夹具 `backend-mock.ts` 不再硬编码 `drawings/` 前缀，与服务端已在 Task 3 改为裸文件名的 `artifact_path` 对齐；此前该页提交前后自相矛盾且 e2e 无法发现。
- 同步清理 Playwright 夹具中的 handoff 路由与调用计数、`wizard-flow.spec.ts` 的交接断言与 `wizard-real-backend.spec.ts` 的交接端点 mock。本次未修改 Python 后端。
```

```powershell
git add builder-web changelog.md
git commit -m "移除 Builder 向导交接步并降为六步"
```

---

### Task 6: Builder 后端移除交接端点、适配器与响应模型

**Files:**
- Delete: `src/dst_builder/application/handoff_adapter.py`
- Modify: `src/dst_builder/application/builds.py`（删四个交接异常类与 `handoff_to_manager`，以及仅为它们服务的 import 与 `__all__` 条目）
- Modify: `src/dst_builder/interfaces/api.py`（删 `HandoffResponse` import、`create_builder_app` 的 `manager_base_url` 与 `handoff_transport` 形参、`app.state.manager_base_url` 与 `app.state.handoff_transport` 赋值、docstring 中的交接适配器说明，以及 `POST /api/builds/{build_id}/handoff` 端点整体）
- Modify: `src/dst_builder/interfaces/schemas.py`（删 `HandoffResponse` 类及其 `__all__` 条目）
- Modify: `builder-web/src/api/openapi.json` 与 `builder-web/src/api/schema.d.ts`（重新生成）
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 5 已移除前端调用；Task 4 的集成测试覆盖替代路径
- Produces: 不含任何交接符号的 Builder 后端

- [ ] **Step 1: 删除交接适配器与四个异常**

删除 `src/dst_builder/application/handoff_adapter.py`。

`src/dst_builder/application/builds.py`：删除 `HandoffNotPublishedError`、`HandoffPackageMissingError`、`HandoffUnavailableError`、`HandoffRejectedError` 四个类定义（约 136-186 行）、`handoff_to_manager` 方法（约 461-500 行）与 `__all__` 中对应的四个名字（约 118-121 行）；删除仅为交接使用的 import（`handoff_adapter` 相关符号、`urllib` 相关符号）。

- [ ] **Step 2: 删除端点与响应模型**

`src/dst_builder/interfaces/api.py`：删除 `HandoffResponse` 的 import（第 78 行）、`create_builder_app` 的 `handoff_transport: object | None = None` 形参（第 301 行）、docstring 中关于 `manager_base_url` / `handoff_transport` 的说明（第 309 行）、`app.state.handoff_transport = handoff_transport`（第 327 行），以及 `POST /api/builds/{build_id}/handoff` 端点整体（第 573-593 行）。

`src/dst_builder/interfaces/schemas.py`：删除 `HandoffResponse` 类及其 `__all__` 条目。

- [ ] **Step 3: 确认交接测试面已随 Task 3 移除**

`tests/integration/test_builder_handoff_api.py` 已在 Task 3 删除（它依赖被删的 package 符号）。本步骤只做确认，不重复删除：

```powershell
uv run python -c "import pathlib,sys; p=pathlib.Path('tests/integration/test_builder_handoff_api.py'); print('still present' if p.exists() else 'removed'); sys.exit(1 if p.exists() else 0)"
```

Expected: 输出 `removed`，退出码 0。

- [ ] **Step 4: 重新生成 Builder OpenAPI 与前端类型**

Run:

```powershell
uv run python scripts/export_builder_openapi.py
Set-Location builder-web
npm run generate:api
Set-Location ..
```

Expected: `builder-web/src/api/openapi.json` 中不再出现 `/api/builds/{build_id}/handoff`；`schema.d.ts` 不再出现 `HandoffResponse` 与 `handoff_build_api_builds__build_id__handoff_post`。

- [ ] **Step 5: 验证**

Run:

```powershell
uv run ruff check .
uv run pytest -q
Set-Location builder-web
npm run build
Set-Location ..
```

Expected: Ruff 无告警、pytest 全部通过、前端类型与构建通过。

- [ ] **Step 6: 更新 changelog 并提交**

在 `changelog.md` 顶部追加：

```markdown
## 2026-09-18（移除 Builder 交接适配器与端点）

- 删除 `src/dst_builder/application/handoff_adapter.py`、`handoff_to_manager` 与四个交接异常类，以及 `POST /api/builds/{id}/handoff` 端点、`HandoffResponse` 响应模型和 `create_builder_app` 的 `handoff_transport` 注入点；重新生成 `builder-web/src/api/openapi.json` 与 `schema.d.ts`。本任务不删测试：交接测试面（`test_builder_handoff_api.py` / `test_handoff_reader.py` / `handoff_package_factory.py`）已在成果布局任务中随被删的 package 符号一并移除。
```

```powershell
git add src/dst_builder builder-web/src/api tests changelog.md
git commit -m "移除 Builder 交接适配器与交接端点"
```

---

### Task 7: Manager 移除交接实现与 handoff_sources 表

**Files:**
- Delete: `src/dst_manager/application/handoff.py`
- Delete: `src/dst_manager/infrastructure/handoff/`（`__init__.py`、`reader.py`）
- Create: `migrations/versions/0008_drop_handoff_sources.py`
- Modify: `src/dst_manager/application/service.py:18,50-59`
- Modify: `src/dst_manager/interfaces/api.py:86-88,280-293`
- Modify: `src/dst_manager/interfaces/responses.py:417-...`
- Modify: `src/dst_manager/interfaces/message_catalog.py:59-60`
- Modify: `src/dst_manager/infrastructure/persistence/database.py`（删 `HandoffSourceRow` 模型与 `handoff_sources` 表定义、`HANDOFF_INITIAL_REVISION_KIND`、`get_handoff_source`、`register_handoff`；**并把 `LATEST_SCHEMA_REVISION` 由 `0007_db001_builder_handoff` 改为 `0008_drop_handoff_sources`**）
- Modify: `tests/unit/test_database.py`（迁移 head 断言与 `handoff_sources` 存在性断言）
- Modify: `tests/unit/test_runtime.py`（`:63` 硬编码的 `0007_db001_builder_handoff`）
- Modify: `tests/unit/test_extension_persistence.py`（`:30` 硬编码的 `0007_db001_builder_handoff`）
- Modify: `web/src/i18n/locales/zh-CN/errors.ts:20-22`、`en-US/errors.ts:20-22`
- Modify: `web/src/api/openapi.json` 与 `web/src/api/schema.d.ts`（重新生成）
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 4 的集成测试（替代路径已覆盖）；Task 6 已移除 Builder 侧调用方
- Produces: 不含交接符号的 Manager；`handoff_sources` 表在 head 迁移后不存在

- [ ] **Step 1: 删除交接读取与编排**

删除 `src/dst_manager/application/handoff.py`（285 行）与整个 `src/dst_manager/infrastructure/handoff/` 目录（`__init__.py` 9 行、`reader.py` 322 行）。

- [ ] **Step 2: 从服务组合移除 HandoffOperations**

`src/dst_manager/application/service.py`：删除 `HandoffOperations` 的 import 与 `DstManagerService` 基类列表中的 `HandoffOperations,`（第 52 行）。

- [ ] **Step 3: 删除端点、响应模型与错误文案**

`src/dst_manager/interfaces/api.py`：删除 `OpenHandoffRequest`（第 86-88 行）与 `POST /api/handoffs/open` 端点整体（第 278-293 行，含 decorator）。注意删除时保留 `on_workspace_opened` 在 `/api/workspaces/open` 中的回调逻辑，只删交接端点。

`src/dst_manager/interfaces/responses.py`：删除 `HandoffOpenResponse` 类及其 `__all__` 条目。

`src/dst_manager/interfaces/message_catalog.py`：删除 `"HANDOFF_INVALID"` 与 `"HANDOFF_ID_CONFLICT"` 两条。

`web/src/i18n/locales/zh-CN/errors.ts` 与 `en-US/errors.ts`：删除 `handoff: { invalid: ..., idConflict: ... }` 整段。两份文件必须同时删除，否则 `npm run check:i18n` 会因键不对称失败。

- [ ] **Step 4: 删除持久化面**

`src/dst_manager/infrastructure/persistence/database.py`：

- 删除 `HandoffSourceRow` 模型类（`__tablename__ = "handoff_sources"`，约第 67 行起）及其上方关于 `metadata`/`source_json` 的注释中仅描述交接的部分；
- 删除模块级常量 `HANDOFF_INITIAL_REVISION_KIND = "handoff_initial"`（第 194 行）；
- 删除 `get_handoff_source`（约第 798 行起）与 `register_handoff`（约第 832 行起）两个方法。

`document_revisions` 的 `kind` 与 `source_json` 列、`RevisionRow` 的对应字段、`add_revision` 的同名形参、`_revision_json` 的取值都保留。

- [ ] **Step 5: 新增迁移**

创建 `migrations/versions/0008_drop_handoff_sources.py`：

```python
"""移除 Builder 成果包交接持久化（RFC-INT-002）。

删除 ``handoff_sources`` 表。``document_revisions.kind`` 与 ``source_json``
保留：它们是通用修订元数据，已由修订读取接口暴露给 API 消费方。
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_drop_handoff_sources"
down_revision = "0007_db001_builder_handoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("handoff_sources")


def downgrade() -> None:
    op.create_table(
        "handoff_sources",
        sa.Column("package_id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("build_id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("handoff_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
```

- [ ] **Step 6: 删除交接测试与更新库测试**

`tests/unit/test_handoff_reader.py` 与 `tests/handoff_package_factory.py` 已在 Task 3 删除（它们依赖被删的 package 符号），本步骤不重复删除。

`tests/unit/test_database.py`：

- 第 337 行的迁移 head 断言改为 `assert revision == "0008_drop_handoff_sources"`；
- `test_fresh_database_has_handoff_sources_and_revision_kind` 改名为 `test_fresh_database_has_revision_kind_columns`，删除 `assert "handoff_sources" in tables`，保留 `kind` / `source_json` 列断言；
- `test_upgrade_from_0006_adds_handoff_columns_and_keeps_rows` 改名为 `test_upgrade_from_0006_adds_revision_kind_columns_and_keeps_rows`，删除 `handoff_sources` 存在性断言，改为断言该表**不存在**，并保留「既有修订行 kind 默认 `operation`」断言；
- `test_handoff_source_round_trip` 删除（其 `add_revision(kind=..., source_json=...)` 的往返已由 `test_fresh_database_has_revision_kind_columns` 与修订读取用例覆盖）。

- [ ] **Step 7: 重新生成 Manager OpenAPI 与前端类型**

Run:

```powershell
Set-Location web
npm run generate:api
Set-Location ..
```

Expected: `web/src/api/openapi.json` 中不再出现 `/api/handoffs/open`；`schema.d.ts` 不再出现 `HandoffOpenResponse`。

- [ ] **Step 8: 验证**

Run:

```powershell
uv run ruff check .
uv run pytest -q
uv run alembic upgrade head
Set-Location web
npm run build
Set-Location ..
```

Expected: Ruff 无告警；pytest 全部通过；`alembic upgrade head` 在全新库上成功且不报错；前端 `check:api`、`check:i18n`、`check:ui`、`vue-tsc` 与构建全部通过。

- [ ] **Step 9: 更新 changelog 并提交**

在 `changelog.md` 顶部追加：

```markdown
## 2026-09-18（移除 Manager 交接实现与 handoff_sources 表）

- 删除 `src/dst_manager/application/handoff.py` 与整个 `src/dst_manager/infrastructure/handoff/`（合计 616 行），以及 `HandoffOperations` 在 `DstManagerService` 中的组合；删除 `POST /api/handoffs/open` 端点、`OpenHandoffRequest`、`HandoffOpenResponse` 与 `HANDOFF_INVALID` / `HANDOFF_ID_CONFLICT` 两条错误文案及对应中英文 i18n 键。
- 删除 `handoff_sources` 表模型、`get_handoff_source`、`register_handoff` 与 `HANDOFF_INITIAL_REVISION_KIND`；新增迁移 `0008_drop_handoff_sources`。`document_revisions.kind` 与 `source_json` 保留为通用修订元数据。
- 更新 `tests/unit/test_database.py` 的迁移 head 与表存在性断言；重新生成 `web/src/api/openapi.json` 与 `schema.d.ts`。交接读取测试面已在成果布局任务中移除。
```

```powershell
git add src/dst_manager migrations tests web/src/api web/src/i18n changelog.md
git commit -m "移除 Manager 交接实现并删除 handoff_sources 表"
```

---

### Task 8: 计划类文档同步与最终验收

**Files:**
- Modify: `.planning/roadmaps/integration.md:19`
- Modify: `.planning/roadmaps/dst-builder.md:69-83`
- Modify: `.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md`（Task 10 / 11 状态）
- Modify: `.planning/README.md`（接入 PLAN-INT-002）
- Modify: `changelog.md`

**Interfaces:**
- Consumes: Task 1–7 的全部产出
- Produces: 与实现一致的路线图与计划索引；`PLAN-INT-002` 的完成状态与验证记录

- [ ] **Step 1: 同步整合路线图**

`.planning/roadmaps/integration.md` 第 19 行中「并建立 Builder → Manager 交接契约」改为「并已按 `RFC-INT-002` / `ADR-INT-001` 取消 Builder → Manager 交接契约，两条产品线以 DST 文件为唯一接口」，并把引用 `RFC-INT-001` 的链接旁补 `RFC-INT-002` 链接。

- [ ] **Step 2: 同步 dst-builder 路线图与 PLAN-DB-001**

`.planning/roadmaps/dst-builder.md`：阶段 5「Manager 交接与产品化」改名为「产品化与交付」，删除其下的 `handoff.json` 契约、一键交接与完整来源追踪两条，退出条件中的「和 Manager 交接闭环」改为「在 DST Manager 中打开已发布 DST」；第 83 行的「版本化 `metadata/` 与 Builder → Manager 交接契约」删除。

`.planning/plans/dst-builder/PLAN-DB-001-minimal-generation-loop.md`：Task 10 与 Task 11 中涉及交接的验收项标注为已由 `RFC-INT-002` 取消，并在计划顶部状态说明中记录该取代关系（不删除历史任务正文）。

- [ ] **Step 3: 校对计划索引**

确认 `.planning/README.md` 已包含 `PLAN-INT-002` 条目（创建本计划时已接入）；若目录结构变化导致链接失效则修正之。`/.planning/plans/integration/` 没有局部 README，本 scope 的计划由 `.planning/README.md` 直接列出。

- [ ] **Step 4: 最终验收**

Run:

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
uv run alembic upgrade head
Set-Location web
npm ci
npm run build
npm run test:e2e
Set-Location ../builder-web
npm ci
npm run build
npm run test:e2e
Set-Location ..
```

Expected: 全部通过。**真实 AutoCAD 系统测试按 AGENTS.md 不在此计划范围内**，需用户显式设置 `DST_MANAGER_RUN_AUTOCAD=1` 并具备本机 Core Console、插件与私有样本后单独执行。

- [ ] **Step 5: 记录实际验证并收口**

把上述命令的**实际输出结论**（不是预期）追加到本计划末尾的「实际验证摘要」一节，然后：

1. 把本计划 frontmatter 的 `status` 由 `proposed` 改为 `completed`；
2. 把 `RFC-INT-002` 的开放问题清单中「`verify_package` 新语义的规范文字」标注为已由 Task 2 与 Task 3 落实；
3. 在 `changelog.md` 顶部追加：

```markdown
## 2026-09-18（PLAN-INT-002 完成：交接契约退场收口）

- 同步 `.planning/roadmaps/integration.md`、`.planning/roadmaps/dst-builder.md`、`PLAN-DB-001` 与 `.planning/README.md`，记录交接契约退场后的路线图与任务取代关系；`PLAN-INT-002` 标记 `completed` 并记录实际验证。
```

```powershell
git add .planning changelog.md docs/integration/rfcs/RFC-INT-002-cancel-builder-manager-handoff.md
git commit -m "同步计划类文档并收口交接契约退场"
```

---

## 最终验收

以下条件全部满足才算完成：

1. `SPEC-DB-001` 的规范性内容不含交接与 `metadata/`（§10 保留原有历史正文并标记 `superseded`）；§9 固定三件套布局与 `verify_target` 判定。
2. `ARCH-INT-002` §6 无 `HandoffBundle` 契约；`ADR-INT-001` 存在且记录取代关系；`RFC-INT-001` 正文未被改写。
3. 代码库中不存在 `handoff_to_manager`、`read_handoff_package`、`HandoffOperations`、`HandoffPackage`、`HandoffResponse`、`HandoffOpenResponse`、`manifest_sha256`、`package_id`、`MANIFEST_SCHEMA`、`HANDOFF_SCHEMA`、`package_id_from_manifest_sha256`、`HANDOFF_INITIAL_REVISION_KIND` 的任何引用。
4. Builder 发布的目标目录直接包含 `sheetset.dst`、构建后的 DWG 与 `图纸目录.xlsx`，无 `metadata/`、无 `drawings/`。
5. `verify_target` 在目标目录含额外文件时通过，在预期产物缺失或为空时失败，在预期集合为空时失败。
6. `migrations/versions/0008_drop_handoff_sources.py` 存在，`uv run alembic upgrade head` 在全新库上成功，`handoff_sources` 不存在而 `document_revisions.kind` / `source_json` 存在。
7. Builder 向导为 6 步，`builder-web` 与 `web` 的 Playwright 测试全部通过。
8. `uv run ruff check .`、`uv run pytest -q`、`uv lock --check` 全部通过。
9. `changelog.md` 在每个任务后有可核验记录。
10. 真实 AutoCAD 系统测试按环境缺失跳过，并在收口时明确报告为未执行。

## 风险与控制

| 风险 | 控制 |
| --- | --- |
| 删除交接后 Manager 无法打开 Builder 产出 | Task 4 的集成测试在 Task 6、7 之前建立并通过；它是本计划的核心安全网 |
| `verify_target` 语义放宽导致发布事务失去有效性检查 | 只放宽「内容哈希」与「目录内其他文件」两项；预期产物缺失、不可读、为空仍判失败；空预期集合判为证据缺失 |
| 旧版发布证据缺少 `expected_paths` 导致启动恢复误判 | 旧证据解析为 `expected_paths=()`，`verify_target` 返回「发布证据缺少预期产物清单」，恢复裁决为 `PUBLISH_RECOVERY_REQUIRED`（保守，不自动删除现场） |
| `plan.expected_artifacts` 与装配结果脱钩 | `test_plan_expected_artifacts_match_assembled_files` 断言两者集合相等，任一侧单独改动都会失败 |
| 删除 `handoff_package_factory.py` 时遗漏使用者 | 该文件仅被 `test_builder_handoff_api.py` 与 `test_handoff_reader.py` 使用，两者在同一任务内删除；Step 8 的全量 pytest 会兜底 |
| 中英文 i18n 键不对称导致 `check:i18n` 失败 | Task 7 Step 3 要求两份 locale 文件同时删除同一段 |
| 前端类型未随 OpenAPI 更新而失配 | Task 6 Step 4 与 Task 7 Step 7 把 `export_*.py` 与 `generate:api` 作为提交前的必经步骤；Manager 的 `npm run build` 内含 `check:api` |
| 迁移与模型不同步导致全新库升级失败 | Task 7 Step 8 强制在全新库上执行 `alembic upgrade head` |

## 实际验证摘要

本节是执行产物，不是计划内容。Task 8 Step 4 执行完毕后，在此逐条记录实际命令与结论（通过 / 失败 / 跳过及原因）；未执行的检查必须写明缺失的环境条件。"真实 AutoCAD 双版本系统测试"因不属于本计划范围，默认记录为未执行。
