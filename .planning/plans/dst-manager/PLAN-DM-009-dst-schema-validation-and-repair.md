---
id: PLAN-DM-009
title: DST XML Schema 校验与可修复加载实施计划
status: completed
owners:
  - dst-manager
created: 2026-08-27
updated: 2026-08-28
related:
  - SPEC-DM-004
  - ARCH-DM-001
  - RES-SH-001
---

# DST XML Schema 校验与可修复加载 Implementation Plan

> **治理闭环（2026-08-28）：** 本计划已按 2026-08-27 的交付验证记录标记为 `completed`，下方验收复选框同步更新；实施任务的历史复选框保留原始执行分解，交付验证记录是完成状态的权威证据。真实 AutoCAD 2016/2020 与官方 Sheet Manager 显示验收未在本机运行，仍是 v1.0 发布资格门禁，不被表述为已通过。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax so progress can be tracked.

**Goal:** 让 DST Manager 在所有 DST/XML 加载入口执行统一的 AcSm 结构、固定属性和语义校验；对可确定修复的缺失元数据只在内存中修复并生成可审计报告；在用户单独确认后，沿现有发布事务把修复作为独立修订写回，从而保证 AutoCAD 官方 Sheet Manager 能识别新增 Sheet。

**Architecture:** 在 `AcsmDocument` 之上增加版本化 AcSm contract registry、检查后修复的 XML DOM pipeline 和 `RepairReport`。XSD 负责修复后的结构边界，Python contract/semantic validator 负责固定 `clsid`、`propname`、`vt`、对象关系及推断边界。应用层统一调用 loader，领域层只保存与序列化无关的诊断值对象；发布层复用现有锁、暂存、基准校验、before 快照、发布日志和回滚事务。未知节点、未知属性、节点顺序和 tail 文本继续由原始 lxml DOM 保留。

**Tech Stack:** Python 3.12+、UV、lxml `etree.XMLSchema`、FastAPI/Pydantic、pytest、Ruff、Vue 3、TypeScript、Vite、现有 DST codec 与 `RecoverablePublisher`。

**Spec:** [docs/dst-manager/specs/SPEC-DM-004-dst-schema-validation-and-repair.md](../../../docs/dst-manager/specs/SPEC-DM-004-dst-schema-validation-and-repair.md)

## Global Constraints

- 先写失败测试，再写最小实现；每个任务完成后运行该任务列出的验证命令并提交一个中文动词开头的 commit。
- 所有 DST 读写必须经过 `DST -> XML DOM -> DST`；读取或内存修复不得写回 DST、创建 `.dst-manager/` 或改变文件时间戳。
- 正式写回只能通过现有锁、暂存、校验、永久 before 快照、发布日志、失败回滚和启动恢复流程；不得直接覆盖正式 DST。
- XSD/contract 只约束已知 AcSm 对象的契约；未知元素、未知属性、原有顺序和 tail 文本不得丢失或重排。
- 失败样本只从 `docs/shared/research/project1-dst-xml/sheetset-fail.xml` 复制到 pytest 临时目录后使用；不得修改 `sample/` 或研究原件。
- ID 只能使用现有 `g` + UUID 格式生成并检查全局不重复；非空的错误 `clsid`、错误 `vt` 或冲突业务值不能静默覆盖，必须进入阻断诊断。
- 空自定义属性缺少 `Value` 是合法状态；不得为了通过 schema 擅自补写空 `Value`。
- Python 依赖只用 UV 管理；若依赖没有变化，不修改 `pyproject.toml` 或 `uv.lock`。
- 用户可见文本、代码注释、文档和 commit message 使用简体中文；协议字段、错误码和第三方固定名称保持英文。
- Web 服务仍只监听 `127.0.0.1`；不得把任意用户文本拼接进 Shell、SCR 或文件操作。
- 没有本机 AutoCAD 2016/2020、Worker 或私有样本时，只运行非 CAD 测试并明确记录跳过原因。

## File and Interface Map

| Layer | Existing or new files | Responsibility |
| --- | --- | --- |
| Domain | `src/dst_manager/domain/models.py` | `RepairStatus`、`RepairAction`、`RepairReport` 等不可变诊断值对象 |
| Infrastructure contract | `src/dst_manager/infrastructure/acsm_xml/contract.py`、`src/dst_manager/infrastructure/acsm_xml/schema/acsm-v1.xsd` | 版本化固定属性表、属性 `vt` 表和修复后 XSD |
| Infrastructure repair | `src/dst_manager/infrastructure/acsm_xml/repair.py` | 复制 DOM、确定性/推断修复、冲突阻断和报告 |
| Infrastructure DOM | `src/dst_manager/infrastructure/acsm_xml/document.py` | 统一 load、工厂、contract/schema/semantic validation、投影和序列化 |
| Application | `src/dst_manager/application/service.py`、`src/dst_manager/application/cad_job.py` | 所有工作区、预览、XML、暂存和 CAD 入口使用统一 loader；独立修复发布 |
| Interface | `src/dst_manager/interfaces/api.py`、`src/dst_manager/interfaces/serialization.py` | 修复报告 API、确认请求和可理解的阻断响应 |
| Web | `web/src/App.vue`、`web/src/style.css` | 修复状态、逐项报告和用户确认流程 |
| Tests | `tests/unit/test_acsm_contract.py`、`tests/unit/test_acsm_repair.py`、现有 AcSm/core/API 测试 | 契约、修复、工厂、发布事务和入口回归 |
| Governance | `.planning/plans/dst-manager/README.md`、`changelog.md` | 计划索引和变更记录 |

## Implementation Tasks

### Task 1: 建立版本化 AcSm contract registry 与标准 XSD

**Files:**

- Create `src/dst_manager/infrastructure/acsm_xml/contract.py`。
- Create `src/dst_manager/infrastructure/acsm_xml/schema/acsm-v1.xsd`。
- Create `tests/unit/test_acsm_contract.py`。
- Modify `changelog.md`，在 `2026-08-27` 章节记录 contract/XSD 开始落地。

**Interfaces:**

```python
CONTRACT_VERSION = "acsm-1.1"

@dataclass(frozen=True, slots=True)
class ObjectContract:
    local_name: str
    required_attributes: frozenset[str]
    fixed_attributes: Mapping[str, str]

def object_contract(local_name: str) -> ObjectContract | None: ...
def expected_prop_vt(owner_local_name: str, propname: str) -> str | None: ...
def validate_contract(root: etree._Element) -> list[ValidationIssue]: ...
def validate_schema(root: etree._Element, version: str = CONTRACT_VERSION) -> list[ValidationIssue]: ...
```

**Steps:**

- [ ] 先在 `test_acsm_contract.py` 加入 Project1 黄金样本测试：`project1_sheetset.xml` 经过 contract 和 XSD 检查无错误；断言 `AcSmSheet` 仅要求 `ID` 与固定 `clsid`，不错误要求 `propname`/`vt`。
- [ ] 加入固定 ID 表测试，覆盖 `AcSmSheetSet`、`AcSmSubset`、`AcSmSheet`、`AcSmCustomPropertyBag`、`AcSmCustomPropertyValue`、`AcSmAcDbLayoutReference`、`AcSmSheetViews` 七类对象。
- [ ] 加入属性类型测试：`Flags=3`、非空自定义 `Value=8`、布局四字段及 `Number`/`Title=8`；覆盖 `PromptForDwt=2`、`FileRevision=3` 等非文本样本，禁止把所有 `AcSmProp` 默认成 `8`。
- [ ] 加入未知元素、未知属性、原有顺序和 tail 文本被 validator 忽略的测试；加入错误固定属性、缺 ID、缺 `vt` 和错误节点层级的失败测试。
- [ ] 实现 registry 和严格后置 XSD。XSD 对已知对象声明必要结构，允许扩展元素/属性以保留未知内容；动态自定义属性名不能写成固定枚举。
- [ ] 运行 `uv run pytest tests/unit/test_acsm_contract.py -q`，确认测试通过；运行 `uv run ruff check src/dst_manager/infrastructure/acsm_xml/contract.py tests/unit/test_acsm_contract.py`。
- [ ] 运行 `git diff --check`，提交 `建立 AcSm contract 与标准 schema`。

### Task 2: 实现内存修复器与可审计 RepairReport

**Files:**

- Modify `src/dst_manager/domain/models.py`。
- Create `src/dst_manager/infrastructure/acsm_xml/repair.py`。
- Create `tests/unit/test_acsm_repair.py`。
- Modify `changelog.md`，记录内存修复和阻断策略。

**Interfaces:**

```python
RepairStatus = Literal[
    "VALID",
    "REPAIRED",
    "INVALID_REPAIR_REQUIRED",
    "INVALID_UNRECOVERABLE",
]
RepairConfidence = Literal["deterministic", "inferred"]

@dataclass(frozen=True, slots=True)
class RepairAction:
    code: str
    node_path: str
    object_id: str | None
    confidence: RepairConfidence
    before: dict[str, str | None]
    after: dict[str, str | None]
    message: str

@dataclass(frozen=True, slots=True)
class RepairReport:
    status: RepairStatus
    actions: tuple[RepairAction, ...] = ()
    blocking_issues: tuple[ValidationIssue, ...] = ()

class AcsmRepairer:
    def repair(self, root: etree._Element) -> tuple[etree._Element, RepairReport]: ...
```

**Steps:**

- [ ] 先写失败测试，使用临时复制的 `sheetset-fail.xml`，断言缺失 `clsid`、`propname`、`vt`、`AcSmSheetViews` 和可推断固定节点均生成对应 action；每个生成 ID 符合格式且全局唯一。
- [ ] 写 golden no-op 测试：黄金样本返回 `VALID`、空 actions，传入 root 的序列化结果保持一致；写输入 root 未被修改测试。
- [ ] 写负例测试：重复/冲突 ID、非空错误 `clsid`、无法确定的布局、缺失 `Number`/`Title` 业务值、多个布局引用、属性 scope 冲突返回 `INVALID_UNRECOVERABLE` 或 `INVALID_REPAIR_REQUIRED`，不覆盖原值。
- [ ] 实现深拷贝 DOM 后的修复顺序：先建立全局 ID 索引，再补可生成 ID，补固定对象属性，按黄金样本位置补 `AcSmSheetViews`，最后补可由同级/投影信息确定的结构节点。
- [ ] 对 `AcSmCustomPropertyBag`、`AcSmCustomPropertyValue`、`AcSmAcDbLayoutReference`、`AcSmSheetViews` 使用 Task 1 registry；空 `Value` 保持缺失，不生成伪造业务值。
- [ ] 让报告记录节点 XPath-like 路径、旧/新属性、对象 ID、修复置信度、错误码和中文说明；修复器不负责写文件。
- [ ] 运行 `uv run pytest tests/unit/test_acsm_repair.py -q` 和 `uv run ruff check src/dst_manager/domain/models.py src/dst_manager/infrastructure/acsm_xml/repair.py tests/unit/test_acsm_repair.py`。
- [ ] 运行 `git diff --check`，提交 `实现 DST XML 内存修复报告`。

### Task 3: 将校验、修复和完整对象工厂接入 AcsmDocument

**Files:**

- Modify `src/dst_manager/infrastructure/acsm_xml/document.py`。
- Modify `tests/unit/test_acsm_custom_properties.py`。
- Modify `tests/unit/test_v021_domain_dom_hardening.py`。
- Modify `tests/unit/test_core.py`。
- Modify `changelog.md`，记录新增 Sheet 工厂与黄金契约对齐。

**Interfaces:**

```python
class AcsmDocument:
    def __init__(self, xml: bytes, *, repair: bool = True): ...

    @property
    def repair_report(self) -> RepairReport: ...

    def validate(self) -> list[ValidationIssue]: ...
    def clone(self) -> "AcsmDocument": ...
    def to_bytes(self) -> bytes: ...
```

**Steps:**

- [ ] 先补工厂失败断言：`_make_sheet_node` 生成的新 Sheet 必须含完整 bag/layout/sheet views/Number/Title 子树；每类固定对象属性和每个已知 `AcSmProp` 的 `vt` 与黄金样本一致。
- [ ] 补 `insert_sheet`、`insert_subset`、`apply_derived_document` 回归测试，验证新增 Sheet 在 DOM 中均含 `AcSmSheetViews`，并保留原有兄弟节点、未知节点和节点顺序。
- [ ] 补失败样本 round-trip 测试，断言加载后投影可见所有可推断 Sheet，`validate()` 只保留不可修复问题；原始 `sheetset-fail.xml` 字节和 mtime 不变。
- [ ] 修改 `AcsmDocument` 初始化流程为 parse → tolerant contract scan → 可选内存 repair → XSD → semantic validate；parseable 但不可发布的 XML 保留 DOM 与诊断，真正写入由应用层阻断。
- [ ] 让 `clone()` 同时复制 repair report 状态，所有 structural/derived 变更在 clone 或现有事务 DOM 上操作；不要让 repair 直接改变源对象或文件。
- [ ] 将 `_make_prop`、`_make_property_value`、`_make_custom_property_bag`、`_make_subset_node`、`_make_sheet_node` 统一改为 contract-driven factory；修正布局引用、SheetViews、Number/Title 和自定义属性的固定字段。
- [ ] 扩展 `validate()` 合并 contract、XSD、semantic 和现有 custom-property diagnostics，并保持既有错误码兼容；新增错误码使用稳定英文标识。
- [ ] 运行 `uv run pytest tests/unit/test_acsm_custom_properties.py tests/unit/test_v021_domain_dom_hardening.py tests/unit/test_core.py -q`，再运行 `uv run ruff check src/dst_manager/infrastructure/acsm_xml/document.py tests/unit`。
- [ ] 运行 `git diff --check`，提交 `对齐新增 Sheet 的 AcSm 对象契约`。

### Task 4: 统一应用层加载入口并公开诊断

**Files:**

- Modify `src/dst_manager/application/service.py`。
- Modify `src/dst_manager/application/cad_job.py`。
- Modify `src/dst_manager/interfaces/serialization.py`。
- Modify `src/dst_manager/interfaces/api.py`。
- Modify `tests/integration/test_api.py`。
- Create or modify `tests/unit/test_acsm_load_entrypoints.py`。
- Modify `changelog.md`，记录统一加载入口和 API 诊断字段。

**Interfaces:**

```python
class ChangeRequest(BaseModel):
    base_revision_id: str
    commands: list[dict[str, Any]] = Field(default_factory=list)
    cad_version: str = "2020"
    preview_digest: str | None = None

class RepairRequest(BaseModel):
    base_revision_id: str
    preview_digest: str | None = None

def workspace_json(workspace) -> dict[str, Any]: ...

def load_acsm(xml: bytes, *, repair: bool = True) -> AcsmDocument: ...
```

**Steps:**

- [ ] 先写入口一致性测试，覆盖 `open_workspace`、`get_workspace`、普通 preview/execute、XML preview/export、CAD job staged re-open；所有入口都观察到同一个 `RepairReport` 语义，禁止继续直接构造绕过 loader 的 `AcsmDocument`。
- [ ] 在工作区序列化中加入稳定字段 `dst_validation`：`status`、`actions`、`blocking_issues`；保持现有 `diagnostics` 字段向后兼容，不能返回 lxml 对象或随机内部路径。
- [ ] 修改 service、CAD job、XML 入口全部调用统一 `load_acsm`；原始文件 SHA-256 仍是 revision baseline，内存 repair 不改变 revision，读取不产生发布目录或文件时间戳变化。
- [ ] 在 `preview_changes`/`execute_changes` 及 XML/CAD 发布前加入 repair 状态门禁：`VALID` 才能正常写入；`REPAIRED` 必须先完成独立修复修订；两个 INVALID 状态只能读和显示诊断，不能创建可写任务。
- [ ] 实现 `RepairRequest` 对应的 `POST /api/workspaces/{workspace_id}/repairs/preview` 与 `/repairs/execute`。preview 固定 base revision 和修复摘要；execute 要求 preview digest 匹配并进入现有受控发布事务，不允许通过普通业务 commands 绕过确认。
- [ ] 补 API 测试：黄金样本打开无修复；失败样本返回修复报告但不改文件；未确认 repair 的变化被明确错误码阻断；确认后产生新 revision，重载为 `VALID`；发布基准变化、锁冲突、发布失败仍走原有回滚。
- [ ] 运行 `uv run pytest tests/unit/test_acsm_load_entrypoints.py tests/integration/test_api.py -q` 和 `uv run ruff check src/dst_manager/application src/dst_manager/interfaces tests/integration/test_api.py tests/unit/test_acsm_load_entrypoints.py`。
- [ ] 运行 `git diff --check`，提交 `统一 DST 加载校验并暴露修复诊断`。

### Task 5: 完成修复独立修订的事务、恢复和 CAD 边界验证

**Files:**

- Modify `src/dst_manager/application/service.py`。
- Modify `src/dst_manager/application/cad_job.py`。
- Modify `tests/unit/test_core.py`。
- Modify `tests/unit/test_v021_domain_dom_hardening.py`。
- Modify `tests/integration/test_api.py`。
- Modify `tests/system_autocad/test_capabilities.py` only when the existing guarded test pattern can cover the repaired fixture。
- Modify `changelog.md`，记录恢复和暂存校验。

**Interfaces:**

```python
def preview_repair(self, workspace_id: str, base_revision_id: str) -> dict[str, Any]: ...
def execute_repair(self, workspace_id: str, base_revision_id: str, preview_digest: str) -> dict[str, Any]: ...
```

**Steps:**

- [ ] 先写事务失败测试：修复发布在暂存校验失败、正式目标 baseline 改变、发布中途异常和进程启动恢复时，正式 DST 恢复为发布前字节，before 快照和 operation journal 可追踪。
- [ ] 补“修复后立即业务编辑”的测试：修复成功后重新加载 workspace，revision 更新且 status 为 `VALID`，随后普通 metadata/structural/CAD 流程继续经过现有基准和权限校验。
- [ ] 让 repair preview 的 digest 由修复后 DOM 的 canonical bytes 与 base revision 组成，执行时再次从正式 DST 解码、修复、严格校验，禁止使用 preview 中可被客户端篡改的 XML。
- [ ] CAD job 对暂存 DST 重新加载时要求 `VALID`；任何 repair/blocking diagnostics 进入任务失败或 `NEEDS_REVIEW`，不能把不完整 sheet 交给 AutoCAD Worker。
- [ ] 运行 `uv run pytest tests/unit/test_core.py tests/unit/test_v021_domain_dom_hardening.py tests/integration/test_api.py -q`。
- [ ] 若本机设置 `DST_MANAGER_RUN_AUTOCAD=1` 且存在匹配 AutoCAD/Worker/私有样本，运行 `uv run pytest tests/system_autocad -q`；否则记录跳过条件，不伪造通过结果。
- [ ] 运行 `git diff --check`，提交 `为 DST 修复增加独立发布事务`。

### Task 6: 在 Web 中加入修复报告和确认流程

**Files:**

- Modify `web/src/App.vue`。
- Modify `web/src/style.css`。
- Modify `changelog.md`，记录前端诊断与确认交互。

**Interfaces:**

```typescript
type RepairAction = {
  code: string;
  node_path: string;
  object_id?: string | null;
  confidence: "deterministic" | "inferred";
  before: Record<string, string | null>;
  after: Record<string, string | null>;
  message: string;
};

type DstValidation = {
  status: "VALID" | "REPAIRED" | "INVALID_REPAIR_REQUIRED" | "INVALID_UNRECOVERABLE";
  actions: RepairAction[];
  blocking_issues: Diagnostic[];
};
```

**Steps:**

- [ ] 先补现有前端构建可通过的类型和渲染测试路径，明确四种状态的颜色、文案和按钮可用性；不把后端 contract 规则复制到前端。
- [ ] 在 workspace 诊断区域显示修复状态、修复数量、每项 code/path/before/after/confidence 和阻断原因；长路径和属性差异可读且不泄露敏感绝对路径。
- [ ] `REPAIRED` 状态显示“预览并确认修复”操作，调用 repair preview/execute；确认前禁用普通编辑发布；`INVALID_*` 只显示诊断并禁用所有写入操作。
- [ ] 处理加载代次、workspace revision 变化和任务终态，避免旧修复报告覆盖新工作区；修复成功后刷新 workspace、revision 和 diagnostics。
- [ ] 运行 `Set-Location web`、`npm ci`、`npm run build`；回到仓库根目录运行 `git diff --check`，提交 `补充 DST 修复确认界面`。

### Task 7: 收尾文档、全量验证与交付审查

**Files:**

- Modify `docs/dst-manager/specs/SPEC-DM-004-dst-schema-validation-and-repair.md` only if implementation exposes a verified contract difference。
- Modify `docs/shared/research/project1-dst-xml/RES-SH-001-project1-dst-xml-analysis.md` only if verified sample evidence needs an explicit implementation note。
- Modify `.planning/plans/dst-manager/README.md`，将 PLAN-DM-009 链接加入详细计划并在完成后更新状态。
- Modify `changelog.md`，记录最终验证结果、未运行的 CAD 检查及交付状态。

**Steps:**

- [ ] 运行 `uv sync --dev`，再运行 `uv run ruff check .`、`uv run pytest -q`、`uv lock --check`。
- [ ] 运行针对黄金样本、失败样本和最小 XML 夹具的回归测试，确认样本原件未变、只读打开无 `.dst-manager`、DST/DWG mtime 不变、未知 DOM 内容可 round-trip。
- [ ] 对每个写入入口检查：永久 before 快照、baseline hash、锁、暂存严格校验、发布日志、失败回滚和启动恢复；输出与 AutoCAD 官方 Sheet Manager 兼容的新增 Sheet XML 子树证据。
- [ ] 用 `rtk git diff --check` 和 `rtk git status --short --branch --untracked-files=all` 检查无敏感文件、样本原件、构建产物或缓存进入变更。
- [ ] 根据执行结果将本计划从 `proposed` 改为 `completed` 或保留 `proposed` 并记录未完成项；同步 README 和 changelog，提交 `完成 DST schema 校验与修复交付审查`。

## Acceptance Checklist

- [x] 黄金样本加载状态为 `VALID`，无 repair action 和 blocking issue。
- [x] `sheetset-fail.xml` 的可确定元数据缺失在内存中稳定修复，报告可审计；原始文件未被修改。
- [x] 新建 Sheet 具备完整 `clsid`、`ID`、布局引用、属性袋、正确 `vt`、`Number`/`Title` 和 `AcSmSheetViews`，并保留未知 DOM 内容与顺序。
- [x] 冲突 ID、错误非空固定值、缺失业务信息和无法唯一推断的节点不会被静默修复，所有写入均被阻断并可显示诊断。
- [x] 只有用户确认的独立 repair revision 才能写回；写回走现有发布事务并能回滚/恢复。
- [x] 所有应用层和 CAD 暂存加载入口使用同一 loader；API 与 Web 能展示报告并防止绕过确认。
- [x] Ruff、相关 pytest、全量 pytest、UV lock check 和可用的 CAD 系统测试均有实际结果记录。

## 交付验证记录（2026-08-27）

- **全量验证**：`uv sync --dev`、`uv run ruff check .`、`uv run pytest -q`（432 passed，66 skipped，退出码 0）与 `uv lock --check` 全部通过。
- **黄金样本**：`project1_sheetset.xml` 打开为 `VALID`，零修复动作、零阻断；contract 与 XSD 双层校验无错误。
- **失败样本**：`sheetset-fail.xml` 的 11 个 Sheet 缺 `clsid`、11 个 Bag 缺固定属性、33 个属性值与 66 个 `AcSmProp` 缺 `vt`、11 个布局引用无属性、11 个 Sheet 缺 `AcSmSheetViews` 均在内存稳定修复（231 项可审计动作），原始文件字节与 mtime 不变；修复不生成 `.dst-manager/`。
- **新建 Sheet**：工厂输出含完整 `clsid`/`ID`/布局引用（四字段 `vt=8`）/属性袋/`Number`/`Title`/`AcSmSheetViews`，与黄金契约逐字段一致，未知 DOM 内容与顺序保留；冲突 ID、错误非空固定值、缺业务信息与无法唯一推断节点均阻断且不覆盖。
- **发布事务**：写回仅经用户确认的独立 repair revision，走现有锁/暂存/永久 before 快照/发布日志/失败回滚/启动恢复；异常注入、基准漂移、暂存失败均有回归。
- **入口与 UI**：service/CAD/XML 全部使用统一 `load_acsm`；API 的 repairs/preview、repairs/execute 与 Web 修复确认界面（含 e2e 19/19）覆盖确认前禁用与成功后刷新。
- **未运行**：真实 AutoCAD 2016/2020 系统测试与官方 Sheet Manager 显示验收因本机未设置 `DST_MANAGER_RUN_AUTOCAD=1`（且无对应 Core Console/Worker/私有 DWG 样本）而跳过，不视为伪造通过。
