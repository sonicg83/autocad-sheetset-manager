---
id: MEMO-DM-032
title: DST 诊断阻断判定设计评审备忘（码集边界、实测证据与收敛建议）
status: final
document_kind: memo
owners:
  - dst-manager
created: 2026-09-12
updated: 2026-09-12
related:
  - SPEC-DM-004
  - ARCH-DM-005
---

# DST 诊断阻断判定设计评审备忘

本备忘记录 2026-09-12 一次只读调研的完整过程与结论：先梳理 DST 诊断的阻断信息全清单与判定设计，再逐条核验当前设计存在的问题。全程未修改源码、配置或依赖。

## 日期

2026-09-12

## 背景

调研由两个连续问题驱动：

1. 列出 DST 诊断的所有阻断信息（blocking diagnostics）与判定设计（如何判定阻断/状态分类）。
2. 在此基础上详细解释当前设计存在的问题，要求有证据、区分"真实缺陷"与"设计权衡"，不得凭空断言。

范围界定为 DST 核心通道的端到端链路：

```
DST 解码 → 契约扫描 → 内存修复 → 严格 XSD → 语义校验 → 应用门禁 → 前端判定
```

同时纳入编辑/导入预览诊断与扩展目录（sheet_catalog）的阻断词表作为对照。

## 事实

### 1. 诊断数据模型

| 模型 | 定义位置 | 要点 |
|---|---|---|
| `Severity` | `src/dst_manager/domain/models.py:8` | `info` / `warning` / `error`；核心通道实际只用 `error` 与 `info`，`Severity.WARNING` 在 `src/` 零引用 |
| `ValidationIssue` | `domain/models.py:32` | `code, severity, message, object_id, location`；**无 `file` 字段，无 `message_key`/`params`** |
| `RepairReport` | `domain/models.py:69` | `status, actions, blocking_issues` |
| `RepairStatus` | `domain/models.py:45` | `VALID` / `REPAIRED` / `INVALID_REPAIR_REQUIRED` / `INVALID_UNRECOVERABLE` |

序列化出口位于 `src/dst_manager/interfaces/serialization.py:52`，对外暴露 `workspace.diagnostics`（含 info）与 `workspace.dst_validation`。

### 2. 阻断码分层清单

| 层 | 实现 | 码 |
|---|---|---|
| 解码层 | `infrastructure/dst_codec/codec.py:42,49,54` | `DST_DECODE_INVALID_XML`、`XML_INVALID`、`DST_NOT_FOUND` |
| 契约层 | `infrastructure/acsm_xml/contract.py:154` `validate_contract` | `CONTRACT_ATTRIBUTE_MISSING`、`CONTRACT_ATTRIBUTE_VALUE`、`CONTRACT_PARENT_INVALID`、`PROP_VT_MISSING`、`PROP_VT_MISMATCH`（全 `ERROR`） |
| XSD 层 | `contract.py:253` `validate_schema` | `XSD_INVALID`；只取 `schema.error_log.last_error`（`contract.py:259`），多条结构错误仅暴露最后一条 |
| 语义层 | `infrastructure/acsm_xml/document.py` `AcsmDocument.validate()` | `_custom_property_issues()` + `validate_contract` + `validate_schema`，再加 `SHEET_SET_MISSING`、`DATABASE_VERSION_MISSING`、`DUPLICATE_ACSM_ID`、`INVALID_ACSM_ID`、`SHEET_LAYOUT_COUNT`、`LAYOUT_FIELD_MISSING`、`LAYOUT_HANDLE_PLACEHOLDER`、`LAYOUT_HANDLE_INVALID`、`SHEET_FIELD_MISSING` |
| 修复器 | `infrastructure/acsm_xml/repair.py` | 自有阻断集 + 步骤 7 用 `validate_contract(working)` 合并（`repair.py:279` `_merge_contract_issues`），去重键 `(code, object_id, message)` |
| 不可恢复集 | `repair.py:45` | `_UNRECOVERABLE_CODES = {DUPLICATE_ACSM_ID, INVALID_ACSM_ID, XML_ROOT_INVALID}` |
| 环境诊断 | `document.py:996`、`application/service.py:104` | `DWG_PATH_NOT_FOUND`（`error`）、`UNREFERENCED_DWG`（`info`） |
| 编辑/导入预览 | `application/editing.py`、`application/property_import.py`、`application/xml_io.py` | `SHEET_NOT_FOUND`、`LAYOUT_SOURCE_REQUIRED`、`COMMAND_COMBINATION_UNSUPPORTED`、`LAYOUT_SOURCE_OUTSIDE_WORKSPACE`/`EXTENSION_INVALID`/`NOT_FOUND`/`UNREADABLE`、`CUSTOM_PROPERTY_CSV_*`、`XML_TEXT_INVALID` |
| 扩展目录 | `extensions/builtin/sheet_catalog/errors.py` | 7 个码；`SHEET_CATALOG_VALUE_MISSING` 是唯一 `blocking=False`（`severity=warning`） |

### 3. 判定设计（现状）

- 门禁 `_gate_writable`（`application/service.py:274-282`）：只读 `repair_report.status`。`VALID` 放行；`REPAIRED` → 409 `REPAIR_CONFIRMATION_REQUIRED`；`INVALID_REPAIR_REQUIRED` → 409 `REPAIR_BLOCKED`；其余 → 409 `REPAIR_UNRECOVERABLE`；**`status is None` 直接放行（fail-open）**。
- 状态分类 `_classify`（`repair.py:324-328`）：不可恢复优先，其次有阻断，其次有动作，否则 `VALID`。
- CAD 门禁 `_require_valid_staging`（`application/cad_job.py:853`）：非 `VALID` → `DST_REPAIR_GATE_BLOCKED`。
- 计划门禁：`PLAN_INVALID` / `XML_VALIDATION_FAILED` / `REPREVIEW_REQUIRED`。
- 白名单豁免：planned sheet 的 `LAYOUT_FIELD_MISSING` / `LAYOUT_HANDLE_PLACEHOLDER`（`application/editing.py:130`）。
- 前端唯一阻断判据：`severity === "error"`（`web/src/App.vue:255`、`web/src/composables/useSheetsWorkspace.ts:65`）。

因此同一份诊断数据存在**三个消费方、三套判据**：

| 消费方 | 判据 | 位置 |
|---|---|---|
| 前端 | `severity === "error"` | `App.vue:255`、`useSheetsWorkspace.ts:65` |
| 写入门禁 | `repair_report.status` | `application/service.py:274-282` |
| 变更预览 | `validate()` 的返回结果 | `application/editing.py:120-133` |

### 4. 码集边界对照矩阵（实测）

在 `repair=False` 下让 `validate()` 与 `AcsmRepairer().repair()` 看同一份 DOM，逐项注入变异：

| 变异 | `validate()` 报出 | `blocking_issues` | `status` | 仅 `validate()` 有 |
|---|---|---|---|---|
| 基线（未改） | — | — | `VALID` | — |
| `AcDbHandle=ZZ` 非法 | `LAYOUT_HANDLE_INVALID` | 空 | **`VALID`** | `LAYOUT_HANDLE_INVALID` |
| `AcDbHandle=0` 占位 | `LAYOUT_HANDLE_PLACEHOLDER` | 空 | **`VALID`** | `LAYOUT_HANDLE_PLACEHOLDER` |
| 删除 `DbVersion` | `DATABASE_VERSION_MISSING` | 空 | **`VALID`** | `DATABASE_VERSION_MISSING` |
| 一个属性多个 `Value` | `CUSTOM_PROPERTY_VALUE_DUPLICATED` | 空 | **`VALID`** | `CUSTOM_PROPERTY_VALUE_DUPLICATED` |
| 删除 `Number` | `SHEET_FIELD_MISSING` | `SHEET_FIELD_MISSING` | `INVALID_REPAIR_REQUIRED` | — |
| `Number` 的 `vt` 错配 | `PROP_VT_MISMATCH` | `PROP_VT_MISMATCH` | `INVALID_REPAIR_REQUIRED` | — |
| `Flags` 缺失 | `CUSTOM_PROPERTY_FLAGS_MISSING` | `CUSTOM_PROPERTY_FLAGS_INVALID` | `INVALID_REPAIR_REQUIRED` | `..._FLAGS_MISSING`（**码名漂移**） |
| 删除 `AcSmSheetSet` | `CONTRACT_PARENT_INVALID`、`SHEET_SET_MISSING` | `CONTRACT_PARENT_INVALID` | `INVALID_REPAIR_REQUIRED` | `SHEET_SET_MISSING` |

结论：9 项中有 4 项属于"`validate()` 报 `error` 但 `status=VALID`"，即后端门禁对这些 error 完全不设防。

### 5. 端到端场景实测

经真实 `DstManagerService` + `TestClient`（复用 `tests/conftest.py::tiny_workspace`）：

| 场景 | `diagnostics` | `dst_validation.status` | `blocking_issues` | 预览结果 |
|---|---|---|---|---|
| A：删除布局引用的 DWG | `DWG_PATH_NOT_FOUND`(error) | `VALID` | 空 | **200，`executable=true`** |
| B：`AcDbHandle=ZZ` | `LAYOUT_HANDLE_INVALID`(error) | `VALID` | 空 | 200，`executable=false` |
| C：删除 `AcSmSheetViews`（`repair=False`） | 空 | `INVALID_REPAIR_REQUIRED` | 空 | — |
| D：`Number` 的 `vt` 错配 | `PROP_VT_MISMATCH`(error，`object_id=None`) | `INVALID_REPAIR_REQUIRED` | `[PROP_VT_MISMATCH]` | 409 阻断 |

补充实测：

- `AcsmDocument.validate()` **不校验必需子节点存在性**：删除 `AcSmSheetViews` 与图纸级 `AcSmCustomPropertyBag` 后 `validate()` 返回空列表。XSD 头注释明示放弃该职责，契约层只管属性，语义层只管布局/Number/Title。
- `Flags` 缺失时 `validate()` 报 `..._FLAGS_MISSING`、修复器报 `..._FLAGS_INVALID`，同一事实两个稳定标识，根因是 `document._custom_property_scope`（`document.py:78-87`）与 `repair._property_scope_issues`（`repair.py:283-298`）双实现漂移，后者还少报 `VALUE_DUPLICATED`。
- `GET /api/workspaces/{id}`（`interfaces/api.py:274-275`）每次全量重算 decode + 修复 + XSD + 语义校验，无缓存。实测 5 次耗时：10 张图纸 0.030s、50 张 0.088s、200 张 0.330s（近似线性）。
- 诊断 API 返回字段为 `['code','location','message','object_id','severity']`，**无 `message_key`/`params`**；`ARCH-DM-005:191,254` 明确要求 DST 诊断遵循稳定标识原则并建立映射；`message_catalog.py` 仅登记部分 DST 码（`SHEET_LAYOUT_COUNT:114`、`SHEET_SET_MISSING:123`、`CUSTOM_PROPERTY_*:124-136`、`DUPLICATE_ACSM_ID:137`），缺 `SHEET_FIELD_MISSING`、`LAYOUT_FIELD_MISSING`、`LAYOUT_HANDLE_*`、`DATABASE_VERSION_MISSING`、`INVALID_ACSM_ID`、`CONTRACT_*`、`PROP_VT_*`、`XSD_INVALID`、`DWG_PATH_NOT_FOUND`、`LAYOUT_SOURCE_*`、`CUSTOM_PROPERTY_CSV_*`。

### 6. 复现方式

临时 pytest 探针，复用 `tests/conftest.py::tiny_workspace`：

```powershell
$env:UV_LINK_MODE = "copy"
$env:PYTHONIOENCODING = "utf-8"   # 避免中文诊断文案在控制台 GBK 乱码
uv run pytest tests/<探针文件> -s
```

探针文件在调研结束后已删除；调研期间未对 `src/`、`web/`、测试或依赖产生任何改动。

## 临时结论

### P0：阻断能力失效或可用性死锁

| 编号 | 问题 | 关键证据 |
|---|---|---|
| P0-1 | `error` 级诊断不参与任何后端门禁。`DWG_PATH_NOT_FOUND` 由 `document.py:996` 在路径解析阶段产生，从不进入 `RepairReport`；门禁只看 `status` 故放行。而前端 `blocking`（`App.vue:255`）非空导致 UI 宣称“存在阻断”。**前端严格、后端宽松**，且预览面板会显示“无诊断”，与工作区诊断面板直接矛盾。SPEC-DM-004 §4.2 明确要求“缺少 `Number`、`Title`、**文件路径**、布局名称等业务信息”必须阻断 | 场景 A：200 / `executable=true` / `preview.diagnostics=[]` |
| P0-2 | UI 死锁：`LAYOUT_HANDLE_INVALID` 等码落在 `validate() 报出的码 − blocking_issues − 修复器动作集` 的盲区。`status=VALID` 使修复预览 `executable=false`（“无需修复”），编辑预览又因 `validate()` 报 `error` 而 `executable=false`。用户无任何 UI 动作可消除该 error；白名单（`editing.py:130`）只覆盖 `LAYOUT_FIELD_MISSING`/`LAYOUT_HANDLE_PLACEHOLDER`。SPEC-DM-004 §4.2 末项要求“修复后仍不能通过严格 schema 或语义校验”必须阻断 | 场景 B；矩阵中 4 项 `status=VALID` 的 error |
| P0-3 | "必需子节点"不变量没有独立校验器。XSD 明示放弃（`acsm-v1.xsd` 头注释）、契约层只管属性、`validate()` 只管业务不变量，唯一检测者是修复器"识别到 `REPAIR_SHEET_VIEWS_MISSING`/`REPAIR_ATTR_MISSING`"的副作用。修复器若不再识别某必需子节点，XSD 与 `validate()` 均不报错、`status=VALID`，缺陷 DST 静默发布。附带产生自相矛盾状态：`INVALID_REPAIR_REQUIRED` + `blocking_issues=[]`，前端 `RepairStatusPanel.vue:18` 的 `v-if` 使界面不显示任何阻断原因 | 场景 C：`validate()` 返回空 |

### P1

| 编号 | 问题 | 关键证据 |
|---|---|---|
| P1-4 | `object_id` 为空导致前端定位失效。契约层 `_validate_prop_vt` 传 `None`（与其余 `CONTRACT_*` 传 `ID or propname` 的约定并存）；前端 `useSheetsWorkspace.ts:62-68` 用 `filter(Boolean)` 丢弃空值 → `SheetTable.vue:101` 永不命中，表格不打"阻断"标记；更严重的是 `diagnosticFilter==="blocking"`（`useSheetsWorkspace.ts:93`）会过滤掉**所有行**，得到空表 | 场景 D：`object_id=None` |
| P1-5 | 诊断未本地化，直接违反 `ARCH-DM-005:191,254`。诊断响应无 `message_key`/`params`，`message` 为领域/基础设施层硬编码中文；扩展平台错误体已带 `message_key`+`params`，仓库内两套诊断契约并存；`message_catalog.py` 对 DST 码覆盖不完整，即使前端想查表也无键可查 | 实测 `keys`；`document.py:885-914`、`contract.py:266` 硬编码文案 |
| P1-6 | 同一事实两个错误码。`Flags` 缺失 → `validate()`=`CUSTOM_PROPERTY_FLAGS_MISSING`，修复器=`CUSTOM_PROPERTY_FLAGS_INVALID`；双实现漂移且修复器侧少报 `VALUE_DUPLICATED`。诊断面板与修复阻断面板对同一问题显示不同 code，用户会误以为存在两个问题。附带：`document.py:853` 把 `..._FLAGS_MISSING` 的文案写死为"Flags 无效"，code 与 message 措辞不符 | 矩阵"Flags 缺失"行 |

### P2

| 编号 | 问题 | 关键证据 |
|---|---|---|
| P2-7 | XSD 只暴露最后一条结构错误，多条错误需反复修 | `contract.py:259` 只取 `error_log.last_error` |
| P2-8 | `GET /api/workspaces/{id}` 每次全量重算，无缓存、无基于 revision 的短路 | `api.py:274-275`；实测 200 张图纸 66ms/次 |
| P2-9 | 门禁 fail-open：`status is None` 直接放行（"未知即放行"）；`load_acsm` 是约定而非类型强制，靠 `tests/unit/test_acsm_load_entrypoints.py` 反射兜底 | `service.py:281-282` |
| P2-10 | `Severity.WARNING` 在 `src/` 零引用，三级严重度实际只有两级，无法表达"可忽略告警"；唯一例外是扩展目录 `SHEET_CATALOG_VALUE_MISSING`（`blocking=False`），与核心诊断语义不统一 | `domain/models.py:8` |
| P2-11 | `repair=False` 无生产调用点（死路径），但它是"报告与 DOM 不一致"的唯一来源 | `document.py:162-173` 把 `REPAIRED` 降级为 `INVALID_REPAIR_REQUIRED` |

### 属于合理设计权衡（不应计入缺陷）

- 宽容契约扫描 + XSD `xs:any processContents="lax"` 保留未知节点/属性/顺序/tail —— DST 往返安全的前提。
- `_UNRECOVERABLE_CODES` 硬编码 —— 领域判断，合理。
- 不覆盖原值、`deterministic`/`inferred` 置信度、去重键 `(code, object_id, message)`、修复前必须确认 —— 合理。
- planned sheet 的 `LAYOUT_FIELD_MISSING`/`LAYOUT_HANDLE_PLACEHOLDER` 白名单豁免 —— 合理。

### 收敛建议（按优先级）

1. **P0** 把阻断判据收敛为单一权威量，让门禁、预览、前端读同一个派生值。最小改动：让 `DWG_PATH_NOT_FOUND` 一类 error 级诊断同步写入 `RepairReport.blocking_issues`，或让 `_gate_writable` 同时检查 `validate()` 的 error 级结果。
2. **P0** 为"修复器不处理但 `validate()` 报 error"的码给出出路：要么让修复器处理，要么显式标记为"无法通过界面消除"并给出可操作说明，消除场景 B 的死锁。
3. **P0** 为必需子节点（`AcSmSheetViews`、属性袋等）补独立校验器，不再只靠修复器动作识别。
4. **P1** DST 诊断序列化补 `message_key`+`params`，并按 `ARCH-DM-005` 补齐 `message_catalog` 覆盖；或反向修订 `ARCH-DM-005`，明确 DST 诊断属"原始技术详情"不参与翻译。
5. **P1** 统一契约层 `object_id` 填充规则；前端增加"无法定位时不产生空表"的降级路径。
6. **P1** 合并 `document._custom_property_scope` 与 `repair._property_scope_issues`，并修正 `document.py:853` 文案。
7. **P2** XSD 报出 `error_log` 全部错误（限量）；`GET /workspaces/{id}` 增加基于 revision 的诊断缓存；统一 `blocking` 的二值语义（扩展的 `blocking: bool` vs 核心的 `severity === "error"`）。

## 待跟进事项

- 上述 P0/P1/P2 均只登记问题与建议，**尚未立项、尚未修复**。是否立项、由哪个 Plan 承接，需要用户决策。
- 未做的验证：未运行完整 pytest 套件（本次为只读调研，未改动源码）；未运行真实 AutoCAD 系统测试（`DST_MANAGER_RUN_AUTOCAD`）；未验证 Web 侧 Playwright 用例对 `diagnosticFilter` 空表情形的覆盖情况。
- 未确认的问题：`XSD_INVALID` 在 `lax` schema 下的实际可触发路径；`message_catalog.py` 中已登记的 DST 码是否真的被接口层使用（诊断响应当前不含 `message_key`，疑似登记后未接线），需要看接口适配层代码确认。
- 追责边界：实测与 `docs/dst-manager/specs/SPEC-DM-004-dst-schema-validation-and-repair.md` 不符，且属于**实现偏离规范**而非规范缺失：§4.2“必须阻断”末项要求“修复后仍不能通过严格 schema 或语义校验”，直接覆盖 `LAYOUT_HANDLE_INVALID`、`LAYOUT_HANDLE_PLACEHOLDER`、`DATABASE_VERSION_MISSING`、`CUSTOM_PROPERTY_VALUE_DUPLICATED`、`XSD_INVALID`，首项覆盖解码失败；§4.2 第三项及 §7“缺业务信息、重复 ID、冲突布局和冲突属性作用域：稳定阻断”覆盖 `DWG_PATH_NOT_FOUND`。这些条目在实现中均未阻断入写入门禁。是否需要据此开缺陷或修订规范，待用户裁决。

## 参考

- `docs/dst-manager/specs/SPEC-DM-004-dst-schema-validation-and-repair.md`（§3 契约、§4 修复/阻断边界、§5 校验顺序、§6 诊断分级）
- `docs/dst-manager/architecture/ARCH-DM-005-multilingual-support.md`（:191、:254 诊断稳定标识与映射要求）
- `src/dst_manager/infrastructure/acsm_xml/`（`contract.py`、`document.py`、`repair.py`、`schema/acsm-v1.xsd`）
- `src/dst_manager/application/`（`service.py`、`editing.py`、`repair.py`、`cad_job.py`、`xml_io.py`）
- `src/dst_manager/interfaces/message_catalog.py`、`serialization.py`
- `web/src/App.vue`、`web/src/composables/useSheetsWorkspace.ts`、`web/src/components/SheetTable.vue`、`RepairStatusPanel.vue`
