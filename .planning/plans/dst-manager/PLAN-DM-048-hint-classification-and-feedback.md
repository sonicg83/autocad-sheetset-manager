---
id: PLAN-DM-048
title: 提示分类与反馈一致性实施计划
status: active
owners:
  - dst-manager
created: 2026-09-30
updated: 2026-10-02
related:
  - SPEC-DM-006
  - SPEC-DM-015
  - SPEC-DM-018
  - SPEC-DM-021
  - ARCH-DM-007
  - GUIDE-DM-001
  - PLAN-DM-029
  - PLAN-DM-034
  - PLAN-DM-047
  - MEMO-DM-043
---

# 提示分类与反馈一致性实施计划

> **执行约定：** 后续实施使用 `superpowers:executing-plans`，逐任务完成回归测试、最小实现、验证与复核；不得自行启动子代理。复选框只在实际完成并登记证据后勾选。用户于 2026-09-30 明确授权执行本计划并接受六项候选原则；SPEC-DM-006 已接受、G4 已冻结、G6 于 2026-10-01 通过。Task 2～7 已完成 G7 实施验证，Task 8 的自动化与生产截图抽样已完成，G8 仍有全页视口/200% 与读屏检查待办；G9 真实 Windows WebView2 验收仍待执行。

**目标：** 将既有界面的提示按 Lead、Help、Status、Banner、Error 五类收口，减少无效说明和重复通知，同时保留状态、错误定位、操作后果和发布安全信息。

**架构：** 在现有 Vue 公共原语中增加两种纯展示提示组件，扩展 `FormField` 的描述关联能力；页面继续拥有业务状态与显示条件。按页面批次迁移文案和样式，任务通知在既有监视器内去重，保持 HTTP/SSE、草稿、创建和发布契约不变。样式继续消费既有语义令牌，不引入新的字号或通用反馈状态管理器。

**技术栈：** Windows 11、Vue 3、TypeScript、Vite、vue-i18n、Vitest、Playwright；Python ≥3.12 与 UV 仅用于后续既有回归。

**设计依据：** [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.7 与 §10.4 是本计划范围，§6.3、§6.6、§7、§9 是保留约束；编辑状态依据 [SPEC-DM-015](../../../docs/dst-manager/specs/SPEC-DM-015-frontend-text-edit-state-contract.md)，创建和级联依据 [SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md)、[SPEC-DM-021](../../../docs/dst-manager/specs/SPEC-DM-021-cascading-enum-properties.md)。实现边界见 [ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md)，门禁见 [GUIDE-DM-001](../../../docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md)。

**既有交付关系：** 沿用 [PLAN-DM-029](PLAN-DM-029-frontend-ui-foundations-remediation.md) 的视觉原语、[PLAN-DM-034](PLAN-DM-034-frontend-text-edit-state-alignment.md) 的编辑状态与 [PLAN-DM-047](PLAN-DM-047-cascading-enum-properties.md) 的级联行为；本计划仅收口提示，不重开这些计划的业务交付。PLAN-DM-034 的 G9 真实桌面检查仍待执行，且与本计划覆盖的编辑页面重叠：本计划 G8/G9 需复用其已冻结的非提示基准，只重开提示有变化的状态；真实桌面验收可安排在同一轮执行，但分别记录两份计划的检查项、结论和证据链接，不能因共用截图自动关闭任一计划。

## 1. 范围、前置条件与全局约束

- 本计划覆盖现有欢迎页、标准管理/编辑、创建向导、图纸/属性编辑、设置/扩展配置、图纸目录、工作区外壳与任务反馈；不重做布局、导航、空状态或任务进度组件。
- 属跨页面及共享外壳变更，按 GUIDE-DM-001 的 L 级组织，拆成任务 2～7 的可独立验收批次；G0～G9 全部登记。沿用视觉方向须记录理由，已冻结页面只重开受影响的提示状态，不静默覆盖原证据。
- SPEC-DM-006 已为 `accepted`，G4 与 G6 已于 2026-10-01 按用户确认通过。剩余 G5 逐消费者细化映射不视为完成；每个迁移批次仍须在开工前补齐其涉及消费者的状态/ARIA/回退映射并由技术负责人复核。
- 任务开始前读取根、docs、scope 索引和相关源码，检查 `rtk git status --short`。仓库可能有其他任务变更，重新定位组件和测试，不覆盖用户改动；执行阶段才按实际需要创建隔离工作区。
- Lead 使用 `--font-label`（13px）与 `--color-text-secondary`；Help 使用 `--font-caption`（12px）与 `--color-text-muted`；Status/Error 使用 `--font-caption`，颜色按真实语义。保持 `tokens, reset, primitives, legacy` 层序。
- 不新增依赖、不改 HTTP/SSE 字段、错误码、后端校验、发布事务、数据库或 CAD Worker；不改变编辑比较基准、clean 动作守卫、级联清空与非法原值保留规则。
- 正式工程文件写入继续走预览、基准/摘要校验、危险确认；不为精简提示删除受影响路径、覆盖后果、外部引用声明或恢复限制。
- 文案同步维护中英文语言包，标识符和协议值保持英文；不要按文案字符串或 CSS 类名推断业务类别、严重程度或事件身份。
- 纯静态文案调整用现有验证和设计走查，不增加复述实现的测试；关联、持续状态、请求守卫和通知去重必须有行为回归。每批实际修改更新 changelog，验证后只暂存该批文件，提交信息使用简体中文动词短语。
- 当前临时演示 `.planning/dst-manager-hint-levels-demo.html` 含旧口径，保持为讨论材料；任务 1 另建本计划候选证据。未经复核的字符比例、类名数量等统计不作为完成门槛。

### 1.1 门禁台账

本计划按 GUIDE-DM-001 的 L 级流程登记 G0～G9。用户于 2026-09-30 明确授权执行本计划并接受 G4 六项候选原则；2026-10-01 又确认固定候选 HTML 可作为 G4 设计冻结基准。冻结件及 28 张截图、27 种状态映射、设计/键盘规格已登记；生产实现同态与运行态键盘核验留在 G8/G9。SPEC-DM-006 已接受；技术负责人批准 G6 已由用户转达，用户确认 G4 冻结并维持执行授权，故 G6 于 2026-10-01 通过并启动计划。G5 的 62 个消费者细化映射尚未全部完成；按本次门禁裁决，将剩余映射作为各对应迁移批次开始前必须补齐的材料，不能当作已完成。风险及裁决见本计划验证记录和执行账本。

| 门禁 | 状态 | 通过证据与责任 |
| --- | --- | --- |
| G0 立项与范围 | 通过（计划执行授权已给出） | Web 提示分类与反馈一致性；不扩大后端、CAD、发布契约；用户授权执行本计划 |
| G1 用户任务与流程 | 通过（纳入 G4/G6 确认） | 创建、标准/导入、属性编辑、设置/目录、全局壳层、异步任务六类路径；用户接受对应候选状态与结束原则 |
| G2 信息架构与交互模型 | 通过（六项候选原则已接受） | Lead、Help、Status、Banner、Error 职责与主要播报/保留原则；用户确认日期 2026-09-30 |
| G3 视觉方向 | 通过（方向 A 已接受） | 沿用现有令牌和中性信息层级，标题自明时不加 Lead；用户确认日期 2026-09-30 |
| G4 Demo 与设计冻结 | 已通过并冻结（2026-10-01，用户确认候选 HTML 可作为设计冻结基准） | 固定版 Demo、28 张截图、27 种状态映射、设计/键盘规格与用户确认；生产同态及运行态键盘验证列入 G8 |
| G5 技术映射 | 初筛与 6 个高风险源复核已备；其余逐消费者细化映射按批次补齐 | 每一对应批次开始前，完成涉及消费者的状态/ARIA/回退映射并复核；技术负责人 |
| G6 | 计划就绪 | **通过（2026-10-01）**：用户确认 G4 冻结、维持实施授权，并转达技术负责人批准。剩余 G5 详表按对应批次前置条件补齐，属本次明确裁决的残余事项 | 已接受 Spec、冻结设计、双向追踪矩阵、可执行批次和验证方案；业务负责人、技术负责人 |
| G7 分批实施 | Task 2～Task 7 已完成；Task 7 通知/UI 单测 23/23、主界面 Playwright 132/132、创建向导 Playwright 46/46、终态后端契约 2/2、check:i18n 与 check:ui 通过。Task 7 G5 映射为执行者自查，不是独立技术负责人签认。G8/G9 验收仍待后续任务 | 每批 RED/GREEN、实现审查和回退记录；技术负责人、实施者 |
| G8 设计 QA | 部分完成（2026-10-02） | 725 项 Playwright 全量通过；完成提示计算样式/对比度矩阵、30 张生产截图和目视审查，修复两项视觉问题。迁移页面全量 4 视口 × 双主题的几何矩阵、指定页面 200% 缩放和人工读屏仍未完成；实施者、业务负责人/验证者 |
| G9 真实验收与关闭 | 未开始 | Windows WebView2 下的真实工作方式、人工读屏、遗留项与最终结论；用户/业务负责人、技术负责人 |

## 2. 只读核对所得的实施起点

以下是 2026-09-30 源码核对结果，不是运行测试结论：

| 位置 | 现状与需处理的边界 | 任务 |
| --- | --- | --- |
| `web/src/components/ui/FormField.vue` | hint/error 使用 `--font-label`；`describedBy` 先 hint 后 error；没有共享说明参数 | 2 |
| `web/src/components/creation/ProjectStep.vue` | 逐字段渲染通用“先选择上级”说明，未给每条级联说明完整共享关联 | 3 |
| `web/src/components/creation/GroupsStep.vue` | 按字段建立级联说明 ID；需按组与上级身份合并，而非整张表去重 | 3 |
| `web/src/styles/legacy.css` | `.notice` 使用 `--color-danger-bg`；不能直接改色后让既有错误失去语义 | 4、7 |
| `web/src/components/ui/ToastHost.vue` | 外层 `aria-live="polite"` 与子项 `status/alert` 嵌套；需验证并收为一个主要播报来源 | 7 |
| `web/src/composables/useToast.ts` | 成功 5000ms 自动关闭、失败无计时；同屏裁切最多 4 条可能移除未处理失败 | 7 |
| `web/src/composables/useJobMonitor.ts` | 已有浮层可见抑制和代次保护；终态通知需增加重复事件回归 | 7 |
| `web/src/features/creation/useCreationJob.ts` | 创建没有普通工作区，保留专用监视器，不能强行替换成普通任务监视器 | 7 |

## 3. 文件结构与共享接口

### 3.1 新建文件及职责

Task 2 已创建提示原语、描述 ID 合并函数及对应测试；任务 3～7 的条目仍按各批次实施。

| 文件 | 职责 |
| --- | --- |
| `web/src/components/ui/UiHint.vue` | Lead/Help/Status/Error 的纯展示容器，不拥有业务状态或隐藏计时 |
| `web/src/components/ui/UiBanner.vue` | 四种横幅的纯展示容器、语义颜色、色条和本地 SVG 图标 |
| `web/src/components/ui/descriptionIds.ts` | 合并错误、字段帮助、共享帮助 ID，按优先顺序去重 |
| `web/src/components/ui/hints.test.ts` | 新原语及描述合并的行为契约 |
| `web/src/features/creation/cascadeHelp.ts`、`cascadeHelp.test.ts` | 按对象和上级属性构建共享帮助分组，不实现候选校验或业务状态机 |
| `web/src/composables/useToast.test.ts`、`useJobMonitor.test.ts` | 计时、保留失败、终态去重与陈旧订阅回归 |
| `web/tests/e2e/hint-contracts.spec.ts` | 跨页面提示关联、反馈唯一性及计算样式验收 |
| `.planning/memos/dst-manager/assets/PLAN-DM-048/README.md` | 候选/生产截图、数据、状态、主题、视口和验证记录索引 |

### 3.2 任务 2 输出的接口

```ts
type HintKind = "lead" | "help" | "status" | "error";
type HintTone = "neutral" | "info" | "success" | "warning" | "error";
type HintLive = "off" | "polite" | "assertive";
// UiHint props；默认插槽承载文本/清单，不内置 i18n 或业务逻辑。
type HintCommonProps = {id?: string; live?: HintLive};
type UiHintProps = HintCommonProps & (
  | {kind: Extract<HintKind, "lead" | "help">; tone?: never}
  | {kind: "status"; tone?: HintTone}
  | {kind: "error"; tone?: "error"}
);
// UiBanner props；默认插槽承载正文，actions 插槽承载既有动作。
type UiBannerProps = {tone: "notice" | "success" | "warning" | "error"; id?: string; live?: HintLive};
function mergeDescriptionIds(errorId?: string, hintId?: string, sharedIds?: string): string | undefined;
```

- 两组件默认 `live="off"`，静态信息不设置 alert；`polite` 使用单一 `role="status"`，`assertive` 使用单一 `role="alert"`，不再嵌套同事件 live region。错误默认取 danger 颜色，判别联合类型禁止 Lead/Help 接受状态 tone，并限制 Error 只能使用 error tone；Status 才接受语义 tone。
- 动态 Status 的 live region 在相关交互开始前常驻 DOM，后续只更新文本；不得随状态文案用条件挂载新建播报容器。静态提示继续使用 `live="off"`。
- `UiBanner` 使用 SPEC-DM-006 §6.7.5 的 `notice/success/warning/error` tone 名称；`notice` 映射到现有 info 语义颜色令牌，不把 `info` 暴露为 Banner tone。
- 状态 tone 由调用方传入；进行中用 info、未提交修改用 warning、失败用 error、中性状态用 neutral。最终可用性仍由既有业务模型判断。
- `FormField` 保留 `label/id/hint/error/required` 和插槽 `id/describedBy/invalid`；只新增可选 `sharedDescribedBy?: string`。合并顺序为错误 → 字段帮助 → 共享帮助；`sharedDescribedBy` 按空白切分，移除空项并按该顺序去重；为空时返回 `undefined`，同 ID 只出现一次。
- `UiInput`/`UiSelect` 既有 `describedBy` 与 `invalid` 接口不变。已有自建表格错误列表不强制包成 `FormField`，但每个出错控件必须有唯一稳定错误 ID、在 `aria-describedby` 中引用当前可见错误，并设置 `aria-invalid="true"`。
- 两组件根元素提供 `data-hint-kind`（对应类别）供稳定验收，Banner 值为 `banner`；不向公共组件加入倒计时、关闭业务或自动去重。

### 3.3 任务 3 输出的接口

```ts
type CascadeHelpInput = {propertyId: string; sourcePropertyId: string; sourceName: string};
type CascadeHelpGroup = {id: string; sourcePropertyId: string; sourceName: string; propertyIds: string[]};
function groupCascadeHelp(instanceId: string, objectId: string, fields: readonly CascadeHelpInput[]): CascadeHelpGroup[];
```

只传入当前确需禁用说明的级联字段，以已有属性 ID 定位上级、名称生成本地化提示。实例 ID 复用 `web/src/components/ui/instanceId.ts`；DOM ID 使用 `web/src/components/ui/domId.ts` 导出的 `domIdToken`，格式固定为 `cascade-help-${domIdToken(JSON.stringify([instanceId, objectId, sourcePropertyId]))}`。不得以替换非法字符或直接用连字符拼接字段生成 ID；固定元组编码避免冒号、空格、中文、百分号、连字符或重复分隔符造成碰撞。

## 4. 审查重点与任务依赖

1. 相同提示文本但上级、对象不同：只能在同一依赖范围合并（任务 3）。
2. 多个必填错误、格式帮助和共享帮助同时出现：不漏关联、不丢错误定位、不悬空（任务 2、5）。
3. 长请求、失败关闭与跨标签：持续状态和业务阻断不能被计时或通知关闭清除（任务 5、6、7）。
4. SSE 重复终态、转轮询和同 ID 重试：每次监视尝试只通知一次，新的尝试仍可通知（任务 7）。
5. 长路径、中英文长文与 200% 缩放：信息不裁切，危险后果不被“简化”删除（任务 3、4、8）。
6. 动态 Status 的 live region 在文本更新前已挂载，且错误控件同时保留 `aria-describedby` 和 `aria-invalid="true"`（任务 2、3、5、8）。

顺序：任务 1 → G6 审核通过 → 任务 2 → 3 → 4 → 5 → 6 → 7 → 8。任务 1 可以先做只读盘点、设计候选和门禁资料；G6 未通过不得开始任务 2 或任何生产文件修改。每个迁移批次单独保留可验收结果；任务 7 涉及共享通知，必须在全量验收前收口。实施中发现新页面或组件时补入任务 1 清单与责任批次，不静默扩大范围。

## 5. 任务

### 任务 1：形成迁移清单与候选基准（G0～G6）

**规格映射：** SPEC-DM-006 §6.7、§10.1、§10.2、§10.4；GUIDE-DM-001 G0～G6。

**文件：** 只读 `web/src/views/`、`web/src/components/`、`web/src/layout/`、`web/src/composables/` 与语言包；新建 `.planning/memos/dst-manager/2026-09-30-plan-dm-048-hint-inventory.md`、`.planning/memos/dst-manager/assets/PLAN-DM-048/README.md`、`docs/dst-manager/mockups/PLAN-DM-048-hint-classification.html`；修改本计划、`.planning/README.md`、`.planning/plans/dst-manager/README.md`、`docs/dst-manager/README.md` 与 `changelog.md`。候选 HTML 放在指南建议的 `docs/dst-manager/mockups/`，截图和持久验证证据放资产索引；不覆写 `.planning/dst-manager-hint-levels-demo.html`。

**接口：** 输入现有 props、业务状态及已接受的规范；输出逐提示清单（文件/语言 key、用途、作用对象、显示条件、结束条件、主要播报者、保留/删除/合并方案、负责批次、准确测试名与断言）和 GUIDE-DM-001 全列追踪矩阵。清单包含所有提示消费方，未改项也记录保留理由；任务 4～6 的测试名、i18n key 和断言在分批开始前冻结到清单。

- [x] 记录 G0～G4 的范围、用户路径、提示职责和 A/B 视觉方向候选；登记 SPEC-DM-006 的初始阻断状态，现已于 2026-10-01 接受。
- [x] 建立 62 个 Vue 消费者的初筛，标出字面 key、候选类别和责任任务，并静态复核 6 个共享/高风险状态源；余下逐消费者用途、作用对象、显示/结束条件、状态所有者、播报者、测试断言、风险和回退须在对应迁移批次开始前补齐并由技术负责人复核（依据 2026-10-01 G6 裁决转为批次前置条件，不代表映射已完成）。
- [x] 用同一份虚构数据建立可操作候选，提供 27 种情形入口、主题切换、模拟创建步骤和重置方式；用户于 2026-10-01 确认该 HTML 可作为 G4 设计冻结基准。
- [x] 将候选职责、token/字号档位、自然换行、状态保留和播报候选写入盘点备忘；用户于 2026-09-30 接受六项原则，并于 2026-10-01 确认设计冻结。生产同态差异和运行态键盘核验纳入 G8，不宣称生产已经符合冻结候选。
- [x] 在 `.planning/memos/dst-manager/assets/PLAN-DM-048/README.md` 登记 28 张冻结截图及视口、主题、缩放、状态、滚动位置、图像像素尺寸、采集日期、裁决记录与 SHA-256；遵循 ARCH-DM-007 §9.3 的每页 4–6 张及整轮 24–30 张预算。冻结截图不等同生产验收。
- [x] 完成并双向核对 §7 追踪矩阵：每条 Spec 要求均映射任务、自动测试、设计 QA 与真实验收，每个任务均有 Spec 映射；实施覆盖状态仍为“未覆盖”。
- [x] SPEC-DM-006 已接受；用户于 2026-10-01 确认 G4 冻结并维持执行授权，技术负责人批准 G6 已由用户转达；记录 G6 通过。G5 未完成的逐消费者明细按上项作为各批次开始前条件补齐。
- [x] 按仓库约定将候选预览服务绑定 `127.0.0.1` 并在检查后停止；已更新本批 changelog、导航和证据索引。
- [x] 用户已明确授权执行且 G6 已通过；计划状态转为 `active` 并进入任务 2。按仓库约定只暂存本批文件并使用简体中文动词短语提交。

### 任务 2：建立提示原语与描述关联

**规格映射：** SPEC-DM-006 §6.7.1、§6.7.4、§6.7.5、§7.4。

**文件：** 新建 §3.1 的 `UiHint.vue`、`UiBanner.vue`、`descriptionIds.ts`、`hints.test.ts`；修改 `FormField.vue`、`uiPrimitives.test.ts`。图标使用现有 `UiIcon.vue/icons.ts`，必要图标仅按现有注册机制补充。

**接口：** 输入现有令牌、实例 ID 和控件插槽；输出 §3.2 接口，供任务 3～7 消费。原语不读取 API、store 或计时器。

- [x] 为 `description_error_first_and_unique`、`hint_and_error_remain_visible`、`shared_description_updates_without_dangling_id`、`static_banner_is_not_alert`、`dynamic_hint_has_one_live_owner`、`lead_help_use_fixed_semantic_color` 编写失败测试。验证 Status live region 先挂载再更新，且同一动态事件只有一个 live owner；判别联合类型拒绝 Lead/Help 的语义 tone 及 Error 的非 error tone。RED 由 FormField 错误优先顺序断言证实；新测试模块在组件创建前无法收集，不计为行为 RED。

```ts
expect(mergeDescriptionIds("field-error", "field-help", "group-help field-help"))
  .toBe("field-error field-help group-help");
expect(mergeDescriptionIds()).toBeUndefined();
```

- [x] 在 `web/` 运行 `rtk npm run test:unit -- src/components/ui/hints.test.ts src/components/ui/uiPrimitives.test.ts`，记录新增契约的预期失败，不把依赖故障当 RED。
- [x] 实现 §3.2；FormField 同时保留必要 Help/Error 并改用 caption。缺失共享元素由调用方负责条件同步，组件不遍历全局 DOM猜测业务。
- [x] 重跑上述用例并运行 `rtk npm run check:ui`；随后迁移批次用浏览器计算样式证明实际字号/颜色，不能用 happy-dom 样式字符串检查代替视觉结果。后续 G8 浏览器计算样式验收仍未完成。
- [x] 更新本批 changelog，只暂存原语、测试和变更记录并以简体中文动词短语提交。

### 任务 3：创建向导与级联共享帮助

**规格映射：** SPEC-DM-006 §6.7.2–§6.7.4、§10.4；SPEC-DM-018/021 对应创建和级联契约。

**文件：** 新建 `features/creation/cascadeHelp.ts` 与测试；修改 `components/creation/ProjectStep.vue`、`GroupsStep.vue`、`StandardStep.vue`、`ReviewStep.vue`、`GroupBatchDialog.vue`、`SheetValuesDialog.vue`、`XlsxImportDialog.vue`、`views/CreateSheetSetView.vue` 及中英文 `creation.ts`；扩展 `tests/e2e/create-sheetset-input.spec.ts`、`create-sheetset-review.spec.ts` 和 `fixtures/creation.ts`。

**接口：** 消费任务 2 原语及既有创建 store/inputModel 的属性身份、取值、候选与错误；输出 §3.3 分组及控件描述关联，不改创建草稿负载。

- [x] Task 3 开工门槛：技术负责人已复核盘点备忘 §9.5 的状态/显示条件/ARIA/恢复映射，并批准 XLSX 失败关闭后保留最近尝试诊断至新文件/新尝试。
- [x] 编写 `same_parent_one_shared_help`、`different_parent_separate_help`、`different_group_separate_help`、`shared_help_ids_do_not_collide` 单测及对应输入 E2E；ID 用例覆盖冒号与连字符、空格、中文、百分号、重复分隔符、分隔符边界歧义和不同表单实例。加入 `creation_switch_and_xlsx_override_preserve_affected_inputs_and_target`，断言切换/覆盖前可见受影响输入、最终路径与不可覆盖事实；同时覆盖两个必填错误（各自 `aria-invalid="true"` 且关联可见 Error）、非法旧级联值、上级选择后说明消失。
- [x] 运行 `rtk npm run test:unit -- src/features/creation/cascadeHelp.test.ts` 与 `rtk npm run test:e2e -- create-sheetset-input.spec.ts --workers=1 --retries=0`，记录有意义的 RED。
- [x] 实现分组并接入 ProjectStep/GroupsStep 的禁用说明；共享 Help 指明上级名称，绑定所有相关控件，保留非法原值及清空入口。其他步骤按任务 1 清单迁移，保留最终路径、标准切换影响、XLSX 全量覆盖确认和不可覆盖声明。
- [x] 重跑单测及 `create-sheetset-input.spec.ts`、`create-sheetset-review.spec.ts`；通过后核对请求负载、草稿保留与预览失效行为未漂移，保存候选/生产同状态证据。
- [x] 更新本批 changelog，只暂存本批页面、测试与变更记录并以简体中文动词短语提交。

### 任务 4：欢迎页与标准管理/编辑文案收口

**文件：** 修改 `views/WelcomeView.vue`、`StandardsView.vue`，`components/standards/StandardLibraryPane.vue`、`StandardDetailPane.vue`、`StandardEditor.vue`、`StandardBasicEditor.vue`、`StandardPublishReview.vue`、`StandardImportDialog.vue` 及任务 1 清单内的属性/模板子组件；中英文 `shell.ts/standards.ts`；扩展 `standards-welcome.spec.ts`、`standards-editor.spec.ts`、`standards-assets-publish.spec.ts`、`standards-library.spec.ts`。

**规格映射：** SPEC-DM-006 §6.7.1、§6.7.2、§10.4；SPEC-DM-016 对应页面行为。

**接口：** 消费现有标准身份、描述、输入状态及原语；不改标准 Schema、保存/发布/复制/删除接口。已有资产复制、编号位数等其他任务交付保持原行为。

- [x] Task 4 G5 开工门槛：技术负责人于 2026-10-01 批准盘点备忘 §9.6 的状态/ARIA/恢复映射；导入 ID/名称冲突、确认竞态、删除影响变化与发布 warning/blocker 门禁按映射执行。
- [x] 覆盖自明区块标题不重复 Lead，并保留身份/字段规则说明；复用现有 ID 冲突不可改名绕过、名称冲突改本机副本名和删除影响变化后二次确认用例，新增确认竞态保留源路径/候选/冲突目标、作废旧凭证且要求重预检的回归。编号位数帮助与字段 Error 并存，Error 排在 `aria-describedby` 首位。
- [x] 按任务 1 清单复核本批消费者；保留欢迎页打开 DST 优先、已有帮助中的范围/下一步/恢复说明与原布局，不把空态文本强制包成 Status。自明区块无冗余 Lead，未发现需要删除的欢迎页说明。
- [x] 运行四份 Task 4 E2E（124/124）、导入弹窗单测（15/15）、`check:i18n`、`check:ui` 与生产构建；E2E 同时覆盖 900×768、200% 缩放、暗色英文及超长名称。构建通过，仍报告主 JavaScript 包超过 500 kB；G8 浏览器视觉证据与 G9 WebView2 验收保留待办。
- [x] 更新本批 changelog 与盘点备忘，只暂存 Task 4 计划、备忘、实现和测试文件，并以简体中文动词短语提交。

### 任务 5：图纸、属性与标准字段的持续状态和错误定位

**G5 状态：** 用户于 2026-10-01 确认批准本节映射，Task 5 获准开工。映射覆盖盘点 §6 中标记为 Task 5 的全部消费者；已由 Task 4 完成的标准管理提示/操作路径只复核其边界与证据，不重复迁移。Task 4 明确延期的标准子编辑器字段级 Error/Status/Help 关联纳入本批，避免无归属地遗留。

**文件：** 图纸/属性主流程：`views/SheetsView.vue/PropertiesView.vue`、`components/sheets/SheetPropertyEditor.vue/SheetOperationForm.vue/SheetToolbar.vue/ColumnSettings.vue`、`components/properties/PropertyValuePanel.vue/PropertyDefinitionPanel.vue/PropertyCsvPanel.vue/PropertyValueCompareDialog.vue`；标准字段子编辑器的剩余关联核对：`CascadePropertyEditor.vue`、`CompositionPropertyDialog.vue`、`DerivedPropertyEditor.vue`、`DwgNamingEditor.vue`、`EnumValuesDialog.vue`、`MappingPropertyDialog.vue`、`OrdinaryPropertyEditor.vue`、`TokenExpressionEditor.vue`。`StandardBasicEditor.vue` 的编号帮助/错误顺序和 `AssetInspectionPanel.vue`、`StandardEditor.vue`、`StandardImportDialog.vue`、`StandardLibraryPane.vue`、`StandardPublishReview.vue`、`TemplateAssetsEditor.vue` 等 Task 4 已处理路径沿用 §9.6 完成证据，发现新缺口才纳入变更。同步中英文 `sheets.ts`/`properties.ts`/`standards.ts`；扩展 `sheets-editing.spec.ts`、`sheets-drafts.spec.ts`、`properties-values.spec.ts`、`properties-definitions.spec.ts`、`properties-csv.spec.ts`，标准字段关联有变更时扩展 `standards-editor.spec.ts`。

**规格映射：** SPEC-DM-006 §§6.3、6.7.1、6.7.3、6.7.4、10.4；SPEC-DM-015 §9；标准编辑器沿用 SPEC-DM-016 与 SPEC-DM-021 既有校验、草稿和错误语义。

**接口：** 只消费 `useSheetEditor`、`usePropertiesWorkspace`、标准编辑器现有 draft/diagnostic 与既有 events；不改变比较基准、请求契约、公开 props/emits、clean 守卫或级联/非法原值保留规则。仅在真实字段身份稳定时建立字段 IDREF；聚合操作错误保留聚合摘要，不伪造字段归属。

- [x] 用户于 2026-10-01 确认批准备忘 §9.7 的完整消费者矩阵与裁决，允许开始 Task 5 实现。每个输入 Error 在 `aria-describedby` 中先于 dirty/pending Status 和 Help；有 Error 的控件保留 `aria-invalid="true"`；属性错误摘要可聚焦且链接能逐项到达字段；SheetOperationForm 没有可靠字段路径的聚合错误聚焦摘要，不添加虚构字段链接。
- [x] 保持成功 Toast 与持续状态分离：图纸/属性字段提交路径不产生成功 Toast，不为其合成通知；对 `SheetToolbar` 批量属性草稿使用真实成功 Toast，关闭 Toast 后 `SheetTable` 的“待变更”仍在。字段编辑从当前草稿投影值改回基准时请求数不增加。
- [x] 覆盖空必填字段逐项关联/摘要跳转、Help 与 Error 共存顺序、dirty/pending/error 状态共存、CSV 预览诊断与关闭确认、定义字段失败保留输入、标准子编辑器的真实字段/聚合错误边界。复用 Task 4 已通过的标准编号 Help+Error 回归，不重复造同义测试；若本批改动该消费者则在 `standards-editor.spec.ts` 保持断言。
- [x] 运行 `sheets-editing.spec.ts`、`sheets-drafts.spec.ts`、`properties-values.spec.ts`、`properties-definitions.spec.ts`、`properties-csv.spec.ts` 与涉及标准字段修改时的 `standards-editor.spec.ts`；运行 `rtk npm run test:unit -- src/composables/useSheetProjection.test.ts src/composables/useDraftGuards.test.ts src/components/standards/OrdinaryPropertyEditor.test.ts` 及实际改动标准子编辑器的定向单测。按实际文案/组件改动运行 `check:i18n`、`check:ui` 和生产构建，验证 clean/error gates 与请求数不漂移。
- [x] 更新 changelog、计划、盘点备忘和 scope 导航；只暂存本批文件，验证后用简体中文动词短语提交。为 G8 保留相同状态计算/生产渲染证据与当前源码播报者记录。

### 任务 6：设置、扩展配置与图纸目录

**文件：** 修改 `components/settings/SettingsFormRow.vue/SettingsDialog.vue/GeneratedExtensionSettingsForm.vue/ExtensionSettingsHost.vue/SheetCatalogSettingsPanel.vue`、`views/SheetCatalogView.vue`、`components/sheet-catalog/TemplateBar.vue/CatalogActions.vue/CatalogPreview.vue` 及清单内其他提示；中英文 `settings.ts/extensions.ts`；扩展 `settings-dialog.spec.ts`、`extensions-settings.spec.ts`、`sheet-catalog.spec.ts`。

**规格映射：** SPEC-DM-006 §6.7.1–§6.7.4、§10.1、§10.4；SPEC-DM-015 §9。

**接口：** 消费 `useSettings/useExtensionSettings/useSheetCatalog` 的原有保存、错误和只读状态；用任务 2 关联/原语承接提示，不复制 Provider 校验。

**G5 状态：** 按用户“继续完成后续任务，中间不用间断”的指示，执行者以已接受 Spec、前序用户裁决、源代码和现有测试完成 §9.8 消费者映射自查后继续实施；此为透明记录的自查，不冒称已取得独立技术负责人签认。若映射漏掉消费路径，可能遗漏 ARIA、恢复或阻断边界并产生返工；完整消费者表、指定 E2E 和最终独立整分支审查作为风险缓解。

- [x] 新增 `settings_help_error_remain_associated_after_provider_conflict`，用边界注入 Provider 409 验证 Help/Error 并存、IDREF、dirty、写入守卫与原 422 详情保持；新增 `sheet_catalog_save_has_one_primary_success_announcement`，断言模板保存只有持续状态这一主要 live 通知；覆盖范围帮助与错误并存。
- [x] 迁移共享及生成式表单提示；范围/描述帮助、Error 与 dirty 均由稳定 ID 关联，错误摘要负责主要播报，逐字段错误不再重复 alert；保留“无修改可保存”和只读原因。
- [x] 运行 `rtk npm run test:unit -- src/composables/useSettings.test.ts src/composables/useExtensionSettings.test.ts`（13/13）、`settings-dialog.spec.ts`（33/33）、`extensions-settings.spec.ts`（72/72）、`sheet-catalog.spec.ts`（108/108）与 `rtk npm run check:i18n`；覆盖取消、保存、导出、未提交输入保护与错误/冲突。目录保存不再重复发出成功 Toast。
- [x] 更新本批 changelog、计划、盘点备忘和 scope 导航；只暂存本批页面、测试和变更记录并以简体中文动词短语提交。

### 任务 7：全局横幅、任务通知与剩余消费方

**规格映射：** SPEC-DM-006 §6.6、§6.7.3、§6.7.5、§10.1、§10.4；SPEC-DM-015 §9。

**文件：** 修改 `layout/WorkspaceShell.vue/ActionDock.vue/TaskOverlay.vue`、`components/JobStatusPanel.vue/PreviewPanel.vue/RepairStatusPanel.vue/RevisionHistoryPanel.vue/DraftActionsPanel.vue`、`components/ui/ToastHost.vue`、`composables/useToast.ts/useJobMonitor.ts`、`styles/legacy.css`；复核 `features/creation/useCreationJob.ts`，只在其回归失败表明需要时修改；中英文 `shell.ts/jobs.ts/revisions.ts`。新建 §3.1 通知单测，扩展 `tests/e2e/main.spec.ts`、`create-sheetset-review.spec.ts`。

**接口：** `useToast()` 继续返回 `toasts/pushToast/dismiss`，Toast 的 `id/type/title/body/jumpTab` 和普通/创建任务监视器公开接口保持不变；使用已有 job ID、订阅代次和每次尝试终态标记去重，不在协议新增事件字段。

**G5 状态：** 按用户“请继续完成后续任务，中间不用间断”的指示，执行者对盘点备忘 §9.9 的全局错误、任务状态/通知、创建任务与 legacy `.notice` 消费方映射逐项自查后实施；这不是独立技术负责人签认。若遗漏 owner/ARIA/恢复边界，可能造成重复播报、误解除 blocker 或失败信息丢失；以 12 个 notice 实例全量扫描、单测、两套页面 E2E 和 G8 独立整分支复核缓解。

- [x] 用假计时器、伪 EventSource 和受控轮询覆盖 `duplicate_terminal_events_notify_once_per_attempt`、`polling_fallback_does_not_repeat_notification`、`failure_and_conflict_remain_visible_until_recovery`、`stale_subscription_has_no_effect`；另验证浮层可见时不弹、同 ID retry 新 attempt 可再通知、成功 5000ms 自动关闭、失败不被数量上限淘汰，`NEEDS_REVIEW` 不发直接重试请求。`useCreationJob` 的 RED 用例复现重复终态会重复切换工作区，故按同一订阅代次修正。
- [x] 对成功 Toast 5000ms 自动关闭及 0.18s 入场动效按 SC 2.2.2 条件评估并记入备忘 §9.9：成功项是静态单次内容，有可访问的逐项关闭/隐藏按钮；动效仅 0.18 秒并且 `prefers-reduced-motion: reduce` 时不运行，未满足超过 5 秒的移动内容条件；关闭控件同时给用户控制隐藏的路径。失败项常驻，逐项查看/关闭；此裁决不代替 G9 读屏播报验证。
- [x] 运行通知单测首轮 RED，再实现 GREEN；最终 `useToast`/`useJobMonitor`/`useCreationJob`/`DraftActionsPanel`/提示原语定向单测 23/23。
- [x] 收口 ToastHost 播报归属：移除父级重复 `aria-live`，每条 Toast 自己承担单一 `status/alert`；useJobMonitor 在订阅代次内先标记再通知/刷新，防止异步刷新期间重复处理。数量上限只清理成功项，不淘汰未处理失败。
- [x] 将全部 12 个 `.notice` markup（8 个 Vue 源文件）迁到显式 `notice/success/warning/error` tone，移除危险红色通用兜底；错误诊断仍可展开。`DraftActionsPanel` 的 corrupted/stale 使用持续 note，动态全局错误 alert 为主要播报者；安全恢复、Disabled 原因和原始错误仍在。
- [x] 按 §9.9 收口任务、修订与结构性表单提示：不存在额外 legacy `.notice` 的 `ActionDock`、`TaskOverlay`、`JobStatusPanel`、`RepairStatusPanel`、`RevisionHistoryPanel` 保留各 owner 和恢复路径；筛选 warning 与 NEEDS_REVIEW blocker 共存且发布仍受阻断。
- [x] 为 `DraftActionsPanel` 的 `corrupted`/`stale` 新增单测，验证 tone、ARIA、危险后果、禁用预览和重新加载/丢弃恢复动作；新增 `independent_global_blocker_remains_visible_with_warning` 与“关闭 Toast/全局错误不解除 job blocker”的 E2E。
- [x] 终验：通知及创建任务定向单测 23/23；`main.spec.ts` 命令 132/132（含 Playwright 设置项目依赖）；`create-sheetset-review.spec.ts` 命令 46/46（含设置项目依赖）；`tests/unit/test_job_terminal_statuses.py` 2/2；`check:i18n`（1664 键/11 域）及 `check:ui` 退出码 0。两次首次 E2E 的失败均为旧宽松“关闭”定位和树默认折叠测试前置，已收紧为精确工作区按钮/先展开树并复跑通过。生产构建、跨页 G8 与真实 WebView2/读屏 G9 留待 Task 8。
- [x] 更新本批 changelog、计划、备忘和导航；只暂存 Task 7 文件并以简体中文动词短语提交。

### 任务 8：综合验收、证据和文档收口（G7～G9）

**规格映射：** SPEC-DM-006 §10.1、§10.2、§10.4；GUIDE-DM-001 G8/G9；ARCH-DM-007 §9.3。

**文件：** 新建 `web/tests/e2e/hint-contracts.spec.ts` 和仓库根 `design-qa.md`；维护 `web/src/components/JobStatusPanel.vue`、`web/src/styles/tokens.css`、相关回归定位、候选资产索引、Task 1 清单、本计划实际验证记录及 `changelog.md`、`.planning/README.md`、计划索引和 `docs/dst-manager/README.md`。正式行为仍引用 SPEC-DM-006，不将规范正文复制进多个文档。

**接口：** 消费原语稳定标记、各页面 fixture 和既有状态/请求；输出 §10.4 十组场景的证据、门禁结论和剩余项。

- [x] 新增 `hint-contracts.spec.ts` 验证真实 Lead/Help/Status/Error 与四种 Banner 计算颜色、字号和对比度；按 light/dark × 4 视口记录 8 份 JSON，提示最小对比度 4.834:1，横幅文本/边线最小对比度 4.669:1。同步断言唯一 ID、有效描述引用与错误 `aria-invalid`；常驻状态/通知去重继续由 Task 2～7 行为回归守卫。
- [x] 创建预览完成 light/dark × `1024×768 / 1120×768 / 1440×900 / 900×768` 矩阵，无整页横溢；长路径、长中文和多行错误通过换行/内容高度断言。按 ARCH-DM-007 §9.3 采集并目视检查 30 张生产截图（每个页面/展示组 4–6 张，900px 为韧性边界）。
- [ ] 其余迁移页面尚未全部纳入 `4 视口 × 双主题` 自动几何矩阵；补齐属性页、图纸目录页、图纸页的浏览器 200% 检查并记录缩放设置。已有独立页面回归与正交截图不替代该门槛。
- [x] 执行 §6 全部命令并登记退出码、数量、失败/跳过原因；完整结果记于 §9。主包 >500 kB 为现存构建提示，不是失败。
- [ ] 人工读屏验证错误摘要聚焦、字段关联、禁用组说明、内联 Status 文本更新播报、SSE/轮询终态只播报一次；责任人为用户/业务负责人，恢复条件为可操作的 Windows 屏幕阅读器环境。axe 或 DOM 数量仅作辅助，不能证明实际播报不重复。
- [ ] 真实 Windows WebView2 浅/深主题 × 100/125/150/200% 复验创建、属性/设置、图纸目录、全局失败与任务结果；责任人为用户/业务负责人和技术负责人，恢复条件为可交互 WebView2 桌面会话。与 PLAN-DM-034 联合取证但分别关闭，任一计划自身的 G9/用户裁决未完成时不得替它关闭。
- [x] 清单已有迁移/保留结论；将跨页完整矩阵、200% 缩放、人工读屏及 WebView2 验收责任人与恢复条件记录到 `design-qa.md` 和证据索引。
- [ ] 全部 G8/G9 及逐项结论闭合后，更新计划状态和索引。
- [x] 更新计划/产品索引、QA/资产证据与本批 changelog，只暂存本批文件并以简体中文动词短语提交；G8/G9 未闭合时保持 `active`。

## 6. 验证命令（按批次执行）

任务内先执行最小相关测试，集成收口执行以下基线；命令兼容 PowerShell。本计划 Task 8 已运行，实际退出码、数量与限制登记于 §9：

```powershell
# 仓库根：不同步/变更依赖；环境缺失时按项目环境流程准备
rtk proxy uv run ruff check .
rtk proxy uv run pytest -q
rtk proxy uv lock --check

# web：定向用例见各任务；最终收口
Set-Location web
rtk npm run test:unit
rtk npm run test:contracts
rtk npm run check:api
rtk npm run check:i18n
rtk npm run check:ui
rtk npm run build
rtk npm run test:e2e -- --retries=0
```

不新增数据模型或后端行为，本计划无需新增 Alembic 迁移、重建插件或启用真实 CAD 测试；实际执行时如出现相关范围变化，先修订计划。真实 CAD 测试仍仅在明确启用和私有样本副本上运行。

## 7. Spec 双向追踪矩阵与完成标准

以下矩阵是 G6 的基线；设计证据统一登记在 `docs/dst-manager/mockups/PLAN-DM-048-hint-classification.html` 和 `.planning/memos/dst-manager/assets/PLAN-DM-048/README.md`，任务 1 为每条提示清单补齐精确截图/状态索引、测试名和断言。状态在自动回归、G8 设计 QA、G9 真实验收分别完成前保持“未覆盖”。正向检查每条 Spec 要求都有任务和验证，反向检查任务 1～8 均有 Spec 映射，禁止在实施中暗增业务规则。

| ID | Spec 要求 | 设计证据（Demo/冻结状态） | 实施任务 | 自动测试 | 设计 QA | 真实验收 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DM048-01 | §6.7.1 五类提示的职责、位置、数量、字号和颜色 | 分类总览、自明标题、需解释区块、并存 Help/Error | 1–7 | `lead_help_use_fixed_semantic_color`；`hint-contracts.spec.ts` 计算样式 | G8 同状态核对数量、字号、颜色、位置 | G9 创建/标准/编辑/设置页面抽查 | 未覆盖 |
| DM048-02 | §6.7.2 提示选型、内部说明边界及目标路径/影响/恢复事实 | 标准导入冲突、删除/切换、XLSX 覆盖及发布风险 | 1、3–7 | `standard_import_conflict_preserves_target_and_recovery_action` 及任务清单逐行断言 | G8 候选与生产逐项比较 | G9 核对关键操作后果与恢复动作 | 未覆盖 |
| DM048-03 | §6.7.3 短暂成功、进行中、失败、dirty/冲突持续状态 | 延迟保存、失败、关闭通知后仍 dirty/待写入 | 1、2、3、5–7 | `success_feedback_dismissal_keeps_pending_write_status`、`settings_help_error_remain_associated_after_provider_conflict` | G8 状态结束条件与显示一致 | G9 实际操作关闭通知并确认阻断不解除 | 未覆盖 |
| DM048-04 | §6.6、§6.7.3 异步终态、同事件播报去重与成功通知结束方式 | 浮层可见/隐藏、SSE 重复、轮询回退、同 ID 重试、成功通知自动关闭 | 1、7 | `useToast`/`useJobMonitor` 终态用例、`hint-contracts.spec.ts` 通知计数 | G8 检查唯一主要播报来源；按 §7.3 记录 5 秒自动关闭和入场动效对 SC 2.2.2 的适用判断 | G9 读屏确认任务终态只播报一次，核对适用的暂停/停止/隐藏或更新频率控制 | 未覆盖 |
| DM048-05 | §6.7.4 共享 Help 的同作用范围、身份稳定与唯一关联 | 同/不同上级、不同对象/图纸组、双实例 | 1、2、3 | `same_parent_one_shared_help`、`different_parent_separate_help`、`different_group_separate_help`、`shared_help_ids_do_not_collide` | G8 检查 IDREF 无悬空、跨实例不串联 | G9 键盘/读屏检查禁用字段及共享说明 | 未覆盖 |
| DM048-06 | §6.3、§6.7.4 多字段 Error 定位、Help/Error 共存和 `aria-invalid` | 两个空字段、范围帮助与错误、摘要跳转 | 1–3、5、6 | `empty_required_fields_remain_individually_described_and_invalid`；`description_error_first_and_unique` | G8 检查焦点、关联与修正说明 | G9 读屏确认摘要及字段定位 | 未覆盖 |
| DM048-07 | §6.7.5 四种横幅、多风险独立显示与语义匹配 | notice/warning/error/success、多独立风险 | 1、2、4、7 | `static_banner_is_not_alert`、横幅计算色/对比度断言 | G8 检查每项风险可见及颜色/文字/图标一致 | G9 检查阻断风险不自动消失 | 未覆盖 |
| DM048-08 | §7.3 SC 2.2.2 适用判断；§10.1 对比度与 §10.2 视口/主题/缩放矩阵 | Toast 自动关闭/入场动效适用性、light/dark、四视口、长文/长路径、关键密集页 200% | 1、7、8 | `hint-contracts.spec.ts` 实际颜色比值及视口/溢出断言；若 SC 2.2.2 适用，按判断补对应交互断言 | G8 正交抽样截图，遵守 4–6/页和 24–30/轮；记录 SC 2.2.2 逐项判断及所需控制 | G9 Windows WebView2 100/125/150/200%，验证适用控制可发现且可操作 | 未覆盖 |
| DM048-09A | §10.4 标题自明/用途需解释 | 自明标题与需 Lead 区块 | 1、4 | `self_describing_standard_sections_do_not_add_redundant_lead` | G8 比较容器数量与文案职责 | G9 标准页真实使用检查 | 未覆盖 |
| DM048-09B | §10.4 多控件依赖同/不同上级 | 同上级、不同上级及不同图纸组 | 1、3 | `same_parent_one_shared_help`、`different_parent_separate_help`、`different_group_separate_help`、`shared_help_ids_do_not_collide` | G8 对照依赖关系、ID 与关联 | G9 键盘/读屏检查共享说明 | 未覆盖 |
| DM048-09C | §10.4 多个必填字段为空 | 两个空字段及摘要定位 | 1、3、5 | `empty_required_fields_remain_individually_described_and_invalid` | G8 检查焦点归位和逐字段关联 | G9 读屏确认摘要定位 | 未覆盖 |
| DM048-09D | §10.4 范围或格式错误 | 范围 Help 与字段 Error 并存 | 1、2、5、6 | `range_help_and_error_remain_associated` | G8 对照修正说明和错误优先级 | G9 键盘/读屏检查修正路径 | 未覆盖 |
| DM048-09E | §10.4 保存成功与编辑状态 | 短暂成功结束后仍 dirty/待写入 | 1、5、6 | `success_feedback_dismissal_keeps_pending_write_status` | G8 检查持续状态和 Toast 去重 | G9 实际保存/关闭反馈并检查状态 | 未覆盖 |
| DM048-09F | §10.4 进行中、失败与冲突 | 延迟、失败、冲突、关闭反馈 | 1、6、7 | `failure_and_conflict_remain_visible_until_recovery` | G8 检查失败原因、下一步与阻断 | G9 真实失败恢复操作 | 未覆盖 |
| DM048-09G | §10.4 浮层显示/收起后的任务结果 | 浮层开/关、重复终态与轮询回退 | 1、7 | `duplicate_terminal_events_notify_once_per_attempt`、`polling_fallback_does_not_repeat_notification` | G8 核对单一主要播报来源 | G9 读屏确认无重复播报 | 未覆盖 |
| DM048-09H | §10.4 全局警告与独立阻断并存 | warning 与独立 error 同时出现 | 1、7 | `independent_global_blocker_remains_visible_with_warning` | G8 检查独立风险、颜色和动作门禁 | G9 检查阻断持续可发现 | 未覆盖 |
| DM048-09I | §10.4 路径、切换后果与撤销承诺 | 切换标准、XLSX 覆盖、最终路径、发布后恢复 | 1、3、4、7 | `creation_switch_and_xlsx_override_preserve_affected_inputs_and_target`、`standard_import_conflict_preserves_target_and_recovery_action` | G8 与业务 Spec 逐项核对 | G9 检查关键路径与恢复说明 | 未覆盖 |
| DM048-09J | §10.4 浅深主题、最小视口与 200% 缩放 | 双主题、四视口、长文及密集页面缩放 | 1、8 | `hint_contrast_ratio_meets_wcag_threshold` 及视口/溢出断言 | G8 正交抽样截图并核对十组场景 | G9 WebView2 100/125/150/200% | 未覆盖 |
| DM048-10 | SPEC-DM-015 §9 编辑状态/请求守卫；SPEC-DM-018/021 创建与级联边界 | clean/dirty/revert、非法级联旧值、创建预览失效 | 1、3、5、6、8 | 请求数、基准恢复、旧值保留与预览失效回归 | G8 验证提示不改变业务契约 | 与 PLAN-DM-034 合并 G9 检查并分别登记 | 未覆盖 |

任务到 Spec 的反向索引：任务 1 → §6.7/§10.1/§10.2/§10.4；任务 2 → §6.7.1/§6.7.4/§6.7.5/§7.4；任务 3 → §6.7.2–§6.7.4、SPEC-DM-018/021；任务 4 → §6.7.1/§6.7.2、SPEC-DM-016；任务 5 → §6.3/§6.7.1/§6.7.3/§6.7.4、SPEC-DM-015 §9；任务 6 → §6.7.1–§6.7.4/§10.1、SPEC-DM-015 §9；任务 7 → §6.6/§6.7.3/§6.7.5；任务 8 → §10.1/§10.2/§10.4、GUIDE-DM-001 G8/G9、ARCH-DM-007 §9.3。

完成必须同时满足：任务 1 清单无遗漏、任务 2～7 对应行为和样式通过、任务 8 的自动化与人工证据完整、必要安全信息没有被删除、HTTP/SSE 和业务状态无漂移、changelog 与索引状态一致。代码测试通过而 G8/G9 未闭合时不得完成。

## 8. 风险与恢复策略

- 原语改动影响已迁移的其他页面：先增加关联回归，逐页检查真实样式；不批量替换所有小字或按类名猜用途。
- 合并提示隐藏不同依赖或同义字段错误：以对象/上级身份分组，只合并帮助；保留错误摘要和逐字段定位。
- 去重抑制新任务或重试结果：去重限定于当前监视尝试，测试同 ID 重试、跨工作区和陈旧回调。
- 用户关闭提示被误解为解除错误：展示组件不得修改业务阻断状态；未解决原因保持入口和状态可见。
- 全局类被其他页面使用或同期代码变化：先复查消费清单和当前工作区，只删除已无消费者的规则；偏差记录到本计划，不擅自还原其他任务。

## 9. 实际验证记录

2026-09-30（依据 MEMO-DM-043 修订）：补齐 G6 前置、完整追踪矩阵、G3/G4 交付清单、精确 ID 编码、任务 4～6 的 RED 断言、对比度与正交截图策略、PLAN-DM-034 联合验收关系及逐批提交步骤；当时未执行产品测试、构建、浏览器、读屏或真实桌面验收。

2026-09-30（Task 1 候选证据）：在隔离 worktree 中扫描计划目标目录的 153 个文件，列出 62 个含提示/关联语义标记的 Vue 消费者及字面 key；新增 [提示迁移盘点](../../memos/dst-manager/2026-09-30-plan-dm-048-hint-inventory.md)、[候选资产索引](../../memos/dst-manager/assets/PLAN-DM-048/README.md) 和 [交互候选](../../../docs/dst-manager/mockups/PLAN-DM-048-hint-classification.html)。用户于 2026-09-30 明确接受六项候选原则。原型 HTML SHA-256 为 `b6d8c0dfd02cf0ec9a9d877992cdb77aeec5fa52adc8b47eea3c9dd564b54a0d`，大小 46101 bytes；静态预检确认 103 个唯一 id、11 个 aria-describedby 引用均有目标、27 种情形与页面/区块映射完整，唯一内嵌脚本通过 node --check。候选预览曾由 127.0.0.1 本地服务返回 HTTP 200，并在 Codex Browser 加载。

2026-09-30（G4 候选截图）：为 7 个页面/展示组采集 28 张全页 JPEG 候选截图，每组 4 张，记录 CSS 视口、主题、默认缩放、顶部滚动位置、图像像素尺寸和 SHA-256；覆盖 1440×900、1024×768、1120×768、900×768 与 light/dark。900×768 仅为韧性检查。对 900×768 的 warning/blocker、1120×768 深色任务复核、1440×900 四种 Banner tone 样本做目视核对。截图索引与文件已登记，原型/截图均为虚构演示，尚未作为生产 G8 证据。

截至 2026-09-30：本批相对链接检查 7 份目标文档无缺失，`rtk git diff --check` 通过。G4 仍未冻结：逐状态 Demo/生产差异表与键盘焦点规格尚待复核；G5 仍待逐消费者技术映射及技术负责人复核；SPEC-DM-006 当时为 `review`，G6 未通过。G7～G9 未开始，计划保持 `proposed`。未修改生产组件、API、Spec 或业务测试，未运行产品测试或生产构建，只做了有限的候选页 Tab/Enter/Space 抽样，未做穷尽键盘遍历、屏幕阅读器或真实 Windows WebView2 验收。

2026-10-01：SPEC-DM-006 §7.3 澄清 SC 2.2.2/3.1.2 并转为 `accepted`；本计划 §7 将 SC 2.2.2 条件判断映射到 Toast 自动关闭/动效的 G8/G9 检查。静态复核 FormField、Toast、普通与创建任务监视器、WorkspaceShell、DraftActionsPanel 六个高风险源并登记到迁移盘点；该样本不是全部 62 个消费者的完整 G5 映射。G4 逐状态差异/键盘规格、剩余 G5 映射与技术负责人复核、G6 双负责人签认仍未完成；G7～G9 未开始，计划保持 `proposed`，未改生产组件/测试/API，未运行产品测试或构建。

2026-10-01：依据用户转达，记录技术负责人已确认批准 G6。此为技术签认记录；当时 G4 冻结确认尚未收到，G5 全部消费者映射与追踪矩阵交叉核对仍未完成，故综合 G6 仍未通过，Task 2 和生产修改仍未启动。

2026-10-01：用户确认 `docs/dst-manager/mockups/PLAN-DM-048-hint-classification.html` 可作为 G4 设计冻结基准。冻结对象为 SHA-256 `b6d8c0dfd02cf0ec9a9d877992cdb77aeec5fa52adc8b47eea3c9dd564b54a0d`、46101 bytes 的固定候选版本，连同 28 张截图、27 种状态映射和设计/键盘规格；G4 记为通过。生产同态与运行态键盘核验留在 G8。

2026-10-01：用户转达技术负责人批准 G6，并确认继续此前执行授权，综合 G6 记为通过，计划转为 `active`。Ruling：将尚未完成的逐消费者 G5 明细转为对应迁移批次的开始前置条件，不把未完成映射记为完成；如果该裁决错误，批次可能遗漏特定消费者、播报或恢复边界，造成返工/回归，因此每批必须先补齐并由技术负责人复核映射。开始 Task 2。

2026-10-01（Task 2）：按盘点备忘 §9.4 的批次映射新增 `UiHint`、`UiBanner` 和 `mergeDescriptionIds`，扩展 `FormField.sharedDescribedBy`，将 Help/Error字号改为 caption，并调整描述顺序为错误→字段帮助→共享帮助。RED：修改后的 FormField 契约先失败，实际仍输出 hint→error；新提示测试在组件文件建立前无法收集，此结果未记作行为 RED。GREEN：`rtk npm run test:unit -- src/components/ui/hints.test.ts src/components/ui/uiPrimitives.test.ts`，40 tests 通过；`rtk npm run check:ui` 通过；`rtk npm run build` 通过（含 API/i18n/UI 检查、`vue-tsc -b` 与 Vite 构建）。构建保留既有主包超过 500 kB 的体积提示。G8 浏览器计算样式及 G9 WebView2/读屏验收未执行；Task 3 尚待开始。

2026-10-01（Task 3 G5 预备）：按计划涉及源码和既有 E2E/Store 测试核对八个消费点，将级联禁用/保存非法值、切换/导入、预览 Error 与 notice、组行定位、最终路径和草稿恢复边界记入盘点备忘 §9.5。发现 XLSX 对话框关闭会清空失败诊断，提出依照已接受原则保留最近失败摘要至新文件/新尝试。Task 3 页面/测试尚未修改，等待技术负责人复核该批映射与此处置。

2026-10-01：用户确认技术负责人批准 Task 3 的 G5 映射与 XLSX 失败详情保留方案；允许开始本批 RED 测试和实现。

2026-10-01（Task 3）：完成级联共享 Help、IDREF 生命周期、向导提示原语迁移及 XLSX 失败诊断保留。RED：实现前定向 E2E 暴露具名 Help/IDREF 缺失和关闭导入对话框会清除失败诊断；GREEN：级联/提示单测 44 项、输入 E2E 55 项、复核 E2E 46 项通过，`check:ui`、`check:i18n` 与完整 Web build 通过。build 保留现有主包 >500 kB 提示。Task 3 已提交；G8 生产浏览器计算样式与运行态 QA、G9 Windows WebView2/读屏验收仍待后续任务。
2026-10-01（Task 4）：按已复核的欢迎页/标准管理映射完成提示迁移、冲突恢复和 warning/blocker 并存门禁。RED/GREEN 回归后，四份 E2E 124/124、导入弹窗单测 15/15、`check:i18n`、`check:ui` 与生产构建通过；构建保留主包 >500 kB 提示。生产视觉/读屏及 WebView2 留待 Task 8/G8/G9。

2026-10-01（Task 5）：按用户批准的 G5 映射完成图纸/属性错误定位与持续状态收口。RED 先复现属性摘要未聚焦、操作摘要不可聚焦、字段 IDREF 为 Status→Error、标准普通属性诊断缺少 IDREF；GREEN：六份 E2E 152/152（含项目依赖），定向单测 41/41，check:i18n、check:ui、OpenAPI 检查、vue-tsc -b 和完整 Vite 构建通过。构建仍有主 JavaScript 包 >500 kB 提示。G8 生产视觉/键盘 QA、G9 Windows WebView2/读屏验收仍待执行。

2026-10-01（Task 6）：按设置、generated 扩展设置与图纸目录映射完成 Error→dirty Status→Help 关联、Provider 409 状态保留及模板成功反馈去重。设置 E2E 33/33、扩展 E2E 72/72、目录 E2E 108/108、composable 单测 13/13、`check:i18n` 通过；映射由执行者自查，未将其写成独立技术复核。G8/G9 留待 Task 8。

2026-10-02（Task 7）：完成全局提示、Toast 和任务通知收口；Vitest 23/23、主界面 Playwright 132/132、创建向导 Playwright 46/46、终态后端契约 2/2、`check:i18n`（1664 keys / 11 domains）与 `check:ui` 通过。Task 7 G5 映射由执行者自查并记载风险；G8/G9 尚未闭合。

2026-10-02（Task 8 自动验收与视觉抽样）：`hint-contracts.spec.ts` 覆盖创建预览双主题 × 四视口计算样式、颜色对比度、IDREF/`aria-invalid` 和长错误换行，持久化 8 份 JSON；采集并目视审查 30 张生产截图。发现浅色成功文字原令牌在 `#E7F4EC` 上对比度 4.433:1，调整至 4.834:1；任务抽屉窄容器导致摘要逐词换行，新增内容宽度换行规则及 RED/GREEN 回归；修正两个过期/不唯一 E2E 定位器。G4 候选 HTML 未修改，仍为 46101 bytes、SHA-256 `b6d8c0dfd02cf0ec9a9d877992cdb77aeec5fa52adc8b47eea3c9dd564b54a0d`。最终完整验证：`rtk proxy uv run ruff check .`、`rtk proxy uv lock --check`、`rtk npm --prefix web run test:unit`（389/389）、`test:contracts`（133/133）、`check:api`、`check:i18n`（1664 keys / 11 domains）、`check:ui`、生产 build 全部通过；`rtk proxy uv run pytest -q` 退出码 0、进度 100%，RTK 未保留最终数量；任务浮层定向 Playwright 34/34、全量 Playwright `--retries=0 --workers=4` 为 725/725。早前 8-worker 探索运行曾遇一次布局 requestAnimationFrame 超时，单 worker 重复 3/3 稳定，最终 4-worker 全量通过。主包 >500 kB 提示仍存在。

截至 2026-10-02：G8 部分完成，生产截图目视抽样及自动验证通过；其它迁移页完整 4 视口 × 双主题矩阵、指定页实际 200% 缩放与人工读屏仍待执行。G9 Windows WebView2 浅/深 × 100/125/150/200% 真实验收未开始。责任人及恢复条件见 `design-qa.md` 和资产索引。计划保持 `active`，不得将本轮通过数字记为 G8/G9 完成。
