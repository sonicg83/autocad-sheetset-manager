---
id: SPEC-DB-001
title: 单张图纸最小生成闭环规范
status: archived
owners:
  - dst-builder
created: 2026-09-17
updated: 2026-09-21
related:
  - PRD-DB-001
  - ARCH-DB-001
  - RFC-INT-001
  - RFC-INT-002
  - RFC-INT-003
  - ADR-INT-001
  - ARCH-INT-002
---

# 单张图纸最小生成闭环规范

> **封口说明（2026-09-21）：** 本文档描述已退场的 DST Builder 产品能力，仅作为历史资料保留，不再作为现役实现依据；替代方向见 [RFC-INT-003](../../integration/rfcs/RFC-INT-003-retire-builder-standard-driven-sheetset-creation.md)、[PLAN-DM-035](../../../.planning/plans/dst-manager/PLAN-DM-035-drawing-standard-platform.md) 与 [PLAN-DM-036](../../../.planning/plans/dst-manager/PLAN-DM-036-standard-driven-sheetset-creation.md)。

## 1. 目的与范围

本规范把 DST Builder 的第一条可实施纵向切片固定为：在六步引导界面中创建一个项目，定义一张图纸，冻结不可变项目修订与生成计划，通过匹配版本的 AutoCAD 生成一个 DWG，从零生成并验证一个 DST，发布正式成果包；DST Manager 直接打开成果目录中的 DST。

首个闭环有意限制为“一项目、一分组、一张图纸、一个 DWG、一个布局”。限制的是首期输入规模，不是领域模型的容量；模型和 JSON 契约仍使用数组，以便后续扩展时不破坏版本 1 契约。

本规范不包含旧 Builder 项目导入、Excel 导入、批量图纸、多分组、自定义属性编辑、外围 CAD 插件、覆盖既有成果包、多用户或远程 Worker。它们不得阻塞本闭环，也不得以空壳按钮进入正式界面。

## 2. 固定用户流程

六个步骤及首期完成条件如下：

| 步骤 | 用户任务 | 完成条件 |
| --- | --- | --- |
| 1 创建项目 | 选择自包含项目目录，填写工程名称、阶段、专业和成果目录 | `project.dstb` 已创建；成果目录是不存在的新目录 |
| 2 配置规则 | 选择 AutoCAD 2016/2020，填写图号前缀、起始序号和位数 | 示例图号可生成且规则合法 |
| 3 编排图纸 | 填写唯一图纸的图名 | 最终图号、图名和文件名无冲突且通过危险字符校验 |
| 4 匹配模板 | 纳入基础 DWG、布局模板，选择源布局 | 两项资产已复制进项目并固定 SHA-256；源布局已由匹配版本 CAD 验证存在 |
| 5 构建前检查 | 查看完整预览，提交修订并确认计划 | 阻断诊断为零；用户确认的 `ProjectRevision` 与 `GenerationPlan` 已持久化 |
| 6 构建成果 | 启动并观察构建 | 唯一 build attempt 到达终止状态；运行中冻结计划不可编辑 |

草稿每次字段变更后 500 ms 防抖保存。应用恢复时返回最后一个可进入步骤和该步骤最后聚焦字段；恢复不能自动越过需用户确认的步骤 5。

## 3. 项目目录与数据库

```text
<project-root>/
├─ project.dstb
├─ assets/
│  ├─ base/<sha256>.<ext>
│  └─ layout/<sha256>.<ext>
└─ builds/
   └─ <build-id>/attempt-001/
      ├─ input/
      ├─ work/
      ├─ logs/
      ├─ metadata/
      └─ candidate/
```

`project.dstb` 是该项目的唯一事实源。外部资产被纳入 `assets/` 后，草稿和计划只引用内容哈希与项目内相对路径，不再依赖原始绝对路径。`builds/` 是可审计运行证据，不是正式成果。

首版数据库 Schema 版本为 `1`，至少包含下列实体：

| 表 | 关键字段 | 约束 |
| --- | --- | --- |
| `projects` | `id`, `name`, `stage`, `discipline`, `output_path`, `created_at`, `updated_at` | 单库恰好一条；`id` 为 UUID |
| `drafts` | `project_id`, `payload_json`, `wizard_step`, `focused_field`, `updated_at` | `payload_json` 通过当前草稿 Schema 校验 |
| `assets` | `id`, `role`, `relative_path`, `sha256`, `size`, `source_name` | `(role, sha256)` 唯一；路径必须位于项目根内 |
| `project_revisions` | `id`, `canonical_json`, `sha256`, `created_at` | 内容不可更新；`sha256` 唯一 |
| `generation_plans` | `id`, `revision_id`, `canonical_json`, `sha256`, `confirmed_at` | 内容不可更新；引用固定修订 |
| `build_runs` | `id`, `plan_id`, `status`, `published_path`, `created_at`, `finished_at` | 一个运行引用一个计划 |
| `build_attempts` | `build_id`, `attempt`, `status`, `progress`, `error_code`, `error_detail` | `(build_id, attempt)` 唯一；历史不覆盖 |
| `build_events` | `id`, `build_id`, `attempt`, `sequence`, `event_json`, `created_at` | `(build_id, attempt, sequence)` 唯一 |

Builder 使用独立 Alembic 配置和迁移链，不能把项目库挂到 Manager 的应用数据库迁移上。首期只承诺从空目录创建 Schema 1，不承诺导入或降级任何历史项目库。

## 4. 草稿输入契约

内部草稿 `DraftProjectV1` 使用以下字段；所有字符串保存前去除首尾空白。

```json
{
  "schema_version": 1,
  "project": {
    "name": "示例工程",
    "stage": "施工图",
    "discipline": "建筑",
    "output_path": "D:/deliveries/example-package"
  },
  "numbering": {
    "prefix": "A-",
    "start": 1,
    "width": 3
  },
  "cad_version": "2020",
  "sheets": [
    {"title": "首层平面图"}
  ],
  "template": {
    "base_asset_id": "<uuid>",
    "layout_asset_id": "<uuid>",
    "source_layout": "A1"
  }
}
```

字段规则：

- `name`、`stage`、`discipline`、`title` 长度为 1～100 个 Unicode 字符；控制字符禁止。
- `prefix` 长度为 0～20，不得包含 Windows 文件名非法字符、路径分隔符或尾部句点/空格。
- `start` 为 0～999999 的整数；`width` 为 1～6；`start` 的十进制位数不得超过 `width`。
- `cad_version` 只接受字符串 `"2016"` 或 `"2020"`。
- `sheets` 在本规范中必须恰好一项。
- `output_path` 必须是绝对路径；确认计划时目标不得存在，父目录必须存在且可写。首期不覆盖或合并既有目录。
- 基础资产扩展名必须是 `.dwg`；布局资产是 `.dwg` 或 `.dwt`；单文件不超过 2 GiB。
- `source_layout` 必须是非 `Model` 的实际布局名。

派生值：

```text
sheet_number = prefix + zero_pad(start, width)
sheetset_name = project.name
subset_name   = project.discipline
layout_name  = sheet_number + " " + title
dwg_name     = layout_name + ".dwg"
artifact_path = dwg_name
dst_reference_path = dwg_name
```

`layout_name` 和 `dwg_name` 不得包含 `<>:"/\\|?*;=` 或控制字符（含 DEL `0x7F`），不得以句点/空格结尾，也不得在去除扩展名并忽略大小写后等于 `CON`、`PRN`、`AUX`、`NUL`、`COM1`～`COM9`、`LPT1`～`LPT9`；规范化后的文件基名最长 180 个字符。该规则已提取为共享纯函数 `dst_platform.contracts.naming.validate_windows_file_name`：禁止字符集取 Builder 与 Manager 既有规则的并集（Manager 原规则额外禁止 `;` 与 `=`），控制字符判定对 Manager 收紧一个码点（DEL `0x7F`），语义只紧不松；Manager 的危险名称校验入口已切换到同一共享实现。Builder 不得导入 `dst_manager.*`。

## 5. 不可变修订与确定性计划

用户进入步骤 5 时，服务先把草稿转换为 `ProjectRevisionV1`。规范化 JSON 使用 UTF-8、键名排序、无多余空白、数组保序和 `ensure_ascii=false`；时间、绝对项目路径、运行机器信息不得进入哈希输入。

```python
canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
revision_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dst-builder:revision:{sha256}"))
```

`ProjectRevisionV1` 固定草稿中的业务字段及项目内资产的 `relative_path`、`sha256`、`size`，并包含 `ruleset_version: 1`。`project.output_path` 是本机发布位置，不进入修订和计划的规范化 JSON；它由 `projects` 保存，并在创建 `BuildRun` 时单独快照。相同业务输入和资产字节必须得到相同修订哈希与 ID。

`GenerationPlanV1` 至少包含：

- `schema_version: 1`、`revision_id`、`revision_sha256`、`ruleset_version: 1`；
- AutoCAD 版本与固定 Worker 命令名；
- 一个 `drawing_task`：任务 ID、基础资产、布局资产、源/目标布局、目标 DWG 相对路径；
- 一个 `sheetset_task`：DST 相对路径、图纸集名、图号、图名、DWG 相对路径、布局名；
- `expected_artifacts`：正式成果中每个预期文件的相对路径、角色和是否必需；
- `diagnostics`：按 `blocking`、`warning`、`info` 分类的构建前诊断。

计划规范化和哈希算法与修订相同，ID 命名空间为 `dst-builder:plan:<sha256>`。`confirmed_at`、构建 ID、attempt、日志路径和最后生成的 Handle 不进入计划哈希。

任何进入规范化修订的业务字段或资产变化都使当前确认失效。只改变 `output_path` 不产生新修订，但创建构建前必须重新执行目标不存在、父目录可写和同卷暂存检查。已经启动的构建始终使用创建时快照的计划与发布目标，不被后续草稿覆盖。

## 6. 构建状态、事件与取消

状态只允许下列迁移：

```text
DRAFT → REVISION_READY → PLANNED → QUEUED → PREPARING
→ BUILDING_DWG → BUILDING_DST → VERIFYING → PUBLISHING → SUCCEEDED

QUEUED|PREPARING|BUILDING_DWG|BUILDING_DST|VERIFYING → CANCELLED
任一非终止构建状态 → FAILED
```

`PUBLISHING` 不响应取消，以免把完成原子发布与用户取消竞态混合；首期发布仅对一个不存在的新目标目录执行同父目录暂存后原子改名。

`BuildEventV1` 包含 `schema_version`、单调递增 `sequence`、`status`、`progress`（0～100）、`message_key`、可选 `artifact_path`、`error_code` 和 `created_at`。HTTP API 使用 SSE 重放 `Last-Event-ID` 之后的持久化事件；断线不影响构建。

应用启动时把遗留在 `PREPARING` 至 `VERIFYING` 的 attempt 标为 `FAILED/BUILD_INTERRUPTED`，保留现场，不续跑半完成 CAD 命令。用户只能基于同一计划创建递增的新 attempt。若发现 `PUBLISHING` 遗留暂存目录：目标不存在时清理暂存并标记失败；目标存在且通过 `verify_target` 校验时收敛为成功；其他情况标记 `PUBLISH_RECOVERY_REQUIRED` 并阻止自动删除现场。

## 7. DWG 生成契约

Builder 使用独立最小插件 `DstBuilder.AutoCAD`，分别针对 AutoCAD 2016 与 2020 构建。首期唯一命令为固定名称 `DSTBUILDER_CREATE_DRAWING`。

执行器必须使用参数数组启动匹配版本 `accoreconsole.exe`，`shell=False`，并生成固定结构 SCR。用户文本、路径和布局名不得直接插入 SCR；命令从 attempt 目录中的版本化 JSON 请求读取结构化数据。

`CadDrawingRequestV1` 包含：基础 DWG 工作副本、布局资产项目内路径、源布局、目标布局、结果 JSON 路径。进入插件前，Python 端必须确认所有路径解析在项目或 attempt 目录内。插件负责：

1. 打开已经由 Core Console 加载的基础 DWG 工作副本；
2. 从布局资产导入指定纸空间布局；
3. 将导入布局改为计划中的目标名，删除除 `Model` 和目标布局以外的纸空间布局；
4. 保存 DWG；
5. 写出 `CadDrawingResultV1`，包含 request ID、布局名、布局 Handle、数据库版本和诊断；Python 在插件退出且文件句柄释放后计算最终 DWG 大小与 SHA-256。

插件失败、超时、结果 JSON 缺失、布局集合不匹配或 Handle 非法均以阻断错误结束 attempt。不得调用旧 `UtilityClass.dll` 或其他回退实现。

## 8. DST 与图纸目录生成

DST 从新的 AcSm DOM 构造，不读取模板 DST。稳定共享包提供二进制 DST Codec、AcSm Schema 装载和 Core Console 进程执行原语；Builder 自己拥有从 `GenerationPlanV1` 到 AcSm DOM 的工厂。

首期 DST 必须表达：一个 SheetSet、一个 Subset、一个 Sheet、一个 LayoutReference；SheetSet 名固定为工程名称，Subset 名固定为专业名称。Sheet 的编号、标题、DWG 相对路径、布局名和插件返回的布局 Handle 必须与计划及实际 DWG 一致。DST 与 DWG 位于同一目标目录，因此 DST 内的 DWG 引用只保存 `dwg_name`。对象 ID 由计划哈希和对象语义路径使用 UUIDv5 派生，不能使用随机值。

编码前后均执行 AcSm Schema 与 Builder 语义校验；编码后重新解码并投影，投影必须与计划一致。任何未知的编码、Schema 或语义错误都阻断发布。

`图纸目录.xlsx` 使用固定工作表 `图纸目录`，第一行为 `图号`、`图名`、`DWG`、`布局`，第二行为唯一图纸数据。它是伴随成果，不是项目事实源。

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

## 10. Manager 交接

> **状态：`superseded`。** 本节描述的 `HandoffBundle` 交接契约已由 [RFC-INT-002](../../integration/rfcs/RFC-INT-002-cancel-builder-manager-handoff.md) 与 [ADR-INT-001](../../integration/adr/ADR-INT-001-cancel-builder-manager-handoff.md) 取消：其准入条件要求成果包自发布起保持字节不变，与「Builder 生成框架 → 人工 AutoCAD 编辑 → Manager 承担中后期交付」的真实流程冲突。决策理由与替代关系见该 ADR。以下正文保留为历史记录，不再具有规范性。

Manager 新增显式入口 `POST /api/handoffs/open`，请求只包含绝对 `handoff_path`。普通 `POST /api/workspaces/open` 语义保持不变。

交接按顺序执行：

1. 确认 `handoff.json`、manifest、DST 和所有登记文件位于同一成果包根内，拒绝绝对路径、`..`、符号链接逃逸与大小写碰撞；
2. 验证受支持 Schema、manifest 哈希、每个文件大小和 SHA-256；
3. 用 Manager 现有只读投影打开 DST，并确认引用只落在 `drawings/` 内且与登记文件一致；
4. 在 Manager 数据库记录 `package_id`、`build_id`、`plan_id`、manifest 哈希和 handoff 路径；
5. 创建 Manager 自己的初始工作区修订，永久保存交接时 `drawings/` 基线及 Builder metadata 副本；
6. 返回工作区和初始修订信息。

相同 `package_id` 与相同 manifest 哈希重复交接必须幂等返回同一工作区和初始修订；相同 `package_id` 对应不同哈希必须报 `HANDOFF_ID_CONFLICT`。验证失败不得创建工作区、来源记录或修订目录。

Manager 修订表增加 `kind`（默认 `operation`，交接为 `handoff_initial`）与可空 `source_json`。交接修订的 `before_hash` 和 `result_hash` 都等于交接时 DST 哈希；`source_json` 保存版本化来源摘要。修订目录中的 manifest 必须继续满足 Manager 修订读取/恢复所需结构，不能伪造一个无法验证的历史项。

## 11. HTTP 与错误契约

Builder 首期 API：

| 方法与路径 | 用途 |
| --- | --- |
| `POST /api/projects` | 创建项目库和初始草稿 |
| `GET /api/projects/current` | 读取项目、草稿、步骤和诊断 |
| `PATCH /api/projects/current/draft` | 带 `base_updated_at` 保存草稿并返回字段诊断 |
| `POST /api/assets` | 纳入并哈希一个模板资产 |
| `POST /api/assets/{id}/inspect` | 用匹配 CAD 读取可用布局 |
| `GET /api/cadabilities` | 只读探测本机 2016/2020 Core Console 与 Builder 插件的显式配置可用性 |
| `POST /api/plans` | 提交修订并产生预览计划 |
| `POST /api/plans/{id}/confirm` | 明确确认计划 |
| `POST /api/builds` | 基于已确认计划创建 build/attempt |
| `POST /api/builds/{id}/cancel` | 请求安全取消 |
| `GET /api/builds/{id}` | 读取状态、诊断和成果 |
| `GET /api/builds/{id}/events` | SSE 事件流与重放 |

错误响应统一含 `code`、`message`、`field`、`recovery_action` 和可选 `details`。首期至少固定：`PROJECT_PATH_INVALID`、`DRAFT_CONFLICT`、`ASSET_OUTSIDE_PROJECT`、`ASSET_HASH_MISMATCH`、`CAD_VERSION_UNAVAILABLE`、`LAYOUT_NOT_FOUND`、`PLAN_STALE`、`BUILD_INTERRUPTED`、`CAD_EXECUTION_FAILED`、`DST_VALIDATION_FAILED`、`PACKAGE_TARGET_EXISTS`、`PUBLISH_RECOVERY_REQUIRED`。

## 12. 验证门禁

自动化验收至少覆盖：

- 相同草稿与资产产生完全相同的修订、计划和 DST 对象 ID；
- 每个字段边界、危险名称、路径逃逸、符号链接、大小写碰撞和 stale plan 被拒绝；
- 模拟 CAD 成功、失败、超时、取消、进程中断和不可信结果 JSON；
- AcSm 构造、Codec 往返、Schema、语义投影、DWG 布局与 Handle 一致性；
- 发布前各故障点不产生正式目录，原子改名后只存在完整成果；
- 目标目录含额外文件时发布后校验与启动恢复均不得失败；
- 六步门禁、自动保存/恢复、错误聚焦、键盘流程、浅深主题和 200% 缩放；
- 打包 Builder 与 Manager 共存，互不覆盖设置、端口、进程名和发布物。

真实发布资格必须在用户显式启用的环境中分别通过 AutoCAD 2016、2020：导入源布局、保存 DWG、官方 Sheet Set Manager 打开 DST、由 DST Manager 直接打开已发布 DST。缺少任一真实版本证据时只能标记开发闭环完成，不能宣称双版本正式发布资格。

## 13. 明确推迟项

- Excel/CSV 导入与导出；
- 多图纸、多分组、特殊图纸、人员字典和自定义属性；
- 覆盖既有成果包与旧版本保留策略；
- `<target>/assets/` 的字体、打印样式和外部参照收集；
- 远程数据库、对象存储、跨机器 Worker 和服务端认证；
- Builder 与 Manager 的反向同步或共同编辑；
- 旧 Builder、旧数据库、旧 API 和旧 DLL 的兼容层。

这些能力进入后续 Spec 前，不得提前扩张版本 1 契约或在首期实现中保留无法验证的备用路径。
