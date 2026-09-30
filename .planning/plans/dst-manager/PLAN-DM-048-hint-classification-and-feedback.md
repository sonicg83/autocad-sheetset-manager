---
id: PLAN-DM-048
title: 提示分类与反馈一致性实施计划
status: proposed
owners:
  - dst-manager
created: 2026-09-30
updated: 2026-09-30
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
---

# 提示分类与反馈一致性实施计划

> **执行约定：** 后续实施使用 `superpowers:executing-plans`，或用户另行选定的执行方式，逐任务完成回归测试、最小实现、验证与复核；不得自行启动子代理。复选框只在实际完成并登记证据后勾选。**当前用户仅授权编写文档，本计划未执行，不代表实现、门禁或真实桌面验收通过。**

**目标：** 将既有界面的提示按 Lead、Help、Status、Banner、Error 五类收口，减少无效说明和重复通知，同时保留状态、错误定位、操作后果和发布安全信息。

**架构：** 在现有 Vue 公共原语中增加两种纯展示提示组件，扩展 `FormField` 的描述关联能力；页面继续拥有业务状态与显示条件。按页面批次迁移文案和样式，任务通知在既有监视器内去重，保持 HTTP/SSE、草稿、创建和发布契约不变。样式继续消费既有语义令牌，不引入新的字号或通用反馈状态管理器。

**技术栈：** Windows 11、Vue 3、TypeScript、Vite、vue-i18n、Vitest、Playwright；Python ≥3.12 与 UV 仅用于后续既有回归。

**设计依据：** [SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md) §6.7 与 §10.4 是本计划范围，§6.3、§6.6、§7、§9 是保留约束；编辑状态依据 [SPEC-DM-015](../../../docs/dst-manager/specs/SPEC-DM-015-frontend-text-edit-state-contract.md)，创建和级联依据 [SPEC-DM-018](../../../docs/dst-manager/specs/SPEC-DM-018-standard-driven-sheetset-creation-ui.md)、[SPEC-DM-021](../../../docs/dst-manager/specs/SPEC-DM-021-cascading-enum-properties.md)。实现边界见 [ARCH-DM-007](../../../docs/dst-manager/architecture/ARCH-DM-007-frontend-ui-foundations.md)，门禁见 [GUIDE-DM-001](../../../docs/dst-manager/guides/GUIDE-DM-001-frontend-design-implementation-gates.md)。

**既有交付关系：** 沿用 [PLAN-DM-029](PLAN-DM-029-frontend-ui-foundations-remediation.md) 的视觉原语、[PLAN-DM-034](PLAN-DM-034-frontend-text-edit-state-alignment.md) 的编辑状态与 [PLAN-DM-047](PLAN-DM-047-cascading-enum-properties.md) 的级联行为；本计划仅收口提示，不重开这些计划的业务交付。

## 1. 范围、前置条件与全局约束

- 本计划覆盖现有欢迎页、标准管理/编辑、创建向导、图纸/属性编辑、设置/扩展配置、图纸目录、工作区外壳与任务反馈；不重做布局、导航、空状态或任务进度组件。
- 属跨页面及共享外壳变更，按 GUIDE-DM-001 的 L 级组织，拆成任务 2～7 的可独立验收批次；G0～G9 全部登记。沿用视觉方向须记录理由，已冻结页面只重开受影响的提示状态，不静默覆盖原证据。
- 编写计划不等于 G4 冻结。SPEC-DM-006 仍为 `review`；实施前确认 §6.7 口径和任务 1 的候选证据，不能把本次文档授权视为执行或发布授权。
- 任务开始前读取根、docs、scope 索引和相关源码，检查 `rtk git status --short`。仓库可能有其他任务变更，重新定位组件和测试，不覆盖用户改动；执行阶段才按实际需要创建隔离工作区。
- Lead 使用 `--font-label`（13px）与 `--color-text-secondary`；Help 使用 `--font-caption`（12px）与 `--color-text-muted`；Status/Error 使用 `--font-caption`，颜色按真实语义。保持 `tokens, reset, primitives, legacy` 层序。
- 不新增依赖、不改 HTTP/SSE 字段、错误码、后端校验、发布事务、数据库或 CAD Worker；不改变编辑比较基准、clean 动作守卫、级联清空与非法原值保留规则。
- 正式工程文件写入继续走预览、基准/摘要校验、危险确认；不为精简提示删除受影响路径、覆盖后果、外部引用声明或恢复限制。
- 文案同步维护中英文语言包，标识符和协议值保持英文；不要按文案字符串或 CSS 类名推断业务类别、严重程度或事件身份。
- 纯静态文案调整用现有验证和设计走查，不增加复述实现的测试；关联、持续状态、请求守卫和通知去重必须有行为回归。每批实际修改更新 changelog，验证后只暂存该批文件，提交信息使用简体中文动词短语。
- 当前临时演示 `.planning/dst-manager-hint-levels-demo.html` 含旧口径，保持为讨论材料；任务 1 另建本计划候选证据。未经复核的字符比例、类名数量等统计不作为完成门槛。

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

### 3.1 新建文件及职责（均待执行）

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
type UiHintProps = {kind: HintKind; id?: string; tone?: HintTone; live?: HintLive};
// UiBanner props；默认插槽承载正文，actions 插槽承载既有动作。
type UiBannerProps = {tone: "info" | "success" | "warning" | "error"; id?: string; live?: HintLive};
function mergeDescriptionIds(errorId?: string, hintId?: string, sharedIds?: string): string | undefined;
```

- 两组件默认 `live="off"`，静态信息不设置 alert；`polite` 使用单一 `role="status"`，`assertive` 使用单一 `role="alert"`，不再嵌套同事件 live region。错误默认取 danger 颜色，Lead/Help 不接受状态色覆盖。
- 状态 tone 由调用方传入；进行中用 info、未提交修改用 warning、失败用 error、中性状态用 neutral。最终可用性仍由既有业务模型判断。
- `FormField` 保留 `label/id/hint/error/required` 和插槽 `id/describedBy/invalid`；只新增可选 `sharedDescribedBy?: string`。合并顺序为错误 → 字段帮助 → 共享帮助；为空时返回 `undefined`，同 ID 只出现一次。
- `UiInput`/`UiSelect` 既有 `describedBy` 与 `invalid` 接口不变。已有自建表格错误列表不强制包成 `FormField`，但须满足相同关联规则。
- 两组件根元素提供 `data-hint-kind`（对应类别）供稳定验收，Banner 值为 `banner`；不向公共组件加入倒计时、关闭业务或自动去重。

### 3.3 任务 3 输出的接口

```ts
type CascadeHelpInput = {propertyId: string; sourcePropertyId: string; sourceName: string};
type CascadeHelpGroup = {id: string; sourcePropertyId: string; sourceName: string; propertyIds: string[]};
function groupCascadeHelp(instanceId: string, objectId: string, fields: readonly CascadeHelpInput[]): CascadeHelpGroup[];
```

只传入当前确需禁用说明的级联字段，以已有属性 ID 定位上级、名称生成本地化提示。ID 由表单实例、对象与上级身份构成，不由显示名称构成；使用安全编码保证不同 ID 不因清洗字符而碰撞。实例 ID 复用既有 `instanceId.ts`。

## 4. 审查重点与任务依赖

1. 相同提示文本但上级、对象不同：只能在同一依赖范围合并（任务 3）。
2. 多个必填错误、格式帮助和共享帮助同时出现：不漏关联、不丢错误定位、不悬空（任务 2、5）。
3. 长请求、失败关闭与跨标签：持续状态和业务阻断不能被计时或通知关闭清除（任务 5、6、7）。
4. SSE 重复终态、转轮询和同 ID 重试：每次监视尝试只通知一次，新的尝试仍可通知（任务 7）。
5. 长路径、中英文长文与 200% 缩放：信息不裁切，危险后果不被“简化”删除（任务 3、4、8）。

顺序：任务 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8。每个迁移批次单独保留可验收结果；任务 7 涉及共享通知，必须在全量验收前收口。实施中发现新页面或组件时补入任务 1 清单与责任批次，不静默扩大范围。

## 5. 任务

### 任务 1：形成迁移清单与候选基准（G0～G5）

**文件：** 只读 `web/src/views/`、`web/src/components/`、`web/src/layout/`、`web/src/composables/` 与语言包；新建 `.planning/memos/dst-manager/2026-09-30-plan-dm-048-hint-inventory.md`、本计划资产索引及候选 HTML。候选 HTML 位于本计划资产目录，不覆写用户临时演示。

**接口：** 输入现有 props、业务状态及规范；输出逐提示清单（文件/语言 key、用途、作用对象、显示条件、结束条件、主要播报者、保留/删除/合并方案、负责批次）。清单包含所有提示消费方，未改项也记录保留理由。

- [ ] 按上述目录枚举提示，定位目前遗漏的组件；对每条拟删除文案核对目标路径、输入清除、导入覆盖和恢复边界，禁止仅因出现 UUID 等词整体删除。
- [ ] 用同一数据建立候选状态：初始、未提交、待写入、进行中、失败、冲突、同/不同上级级联、多字段错误、独立全局风险；与现有页面做成对比较。
- [ ] 按 GUIDE-DM-001 记录沿用视觉方向、受影响的 G2/G4 重开范围和候选裁决；若发生需求空白先修规范，不在 Plan 内新增业务规则。
- [ ] 验证迁移清单覆盖所有消费方、候选使用现有令牌且保留必要后果；取得 G4 冻结证据后才进入生产修改。候选预览按仓库约定绑定 `127.0.0.1` 的局部 HTTP 服务，用完停止。

### 任务 2：建立提示原语与描述关联

**文件：** 新建 §3.1 的 `UiHint.vue`、`UiBanner.vue`、`descriptionIds.ts`、`hints.test.ts`；修改 `FormField.vue`、`uiPrimitives.test.ts`。图标使用现有 `UiIcon.vue/icons.ts`，必要图标仅按现有注册机制补充。

**接口：** 输入现有令牌、实例 ID 和控件插槽；输出 §3.2 接口，供任务 3～7 消费。原语不读取 API、store 或计时器。

- [ ] 为 `description_error_first_and_unique`、`hint_and_error_remain_visible`、`shared_description_updates_without_dangling_id`、`static_banner_is_not_alert`、`dynamic_hint_has_one_live_owner` 编写失败测试。示例关键断言：

```ts
expect(mergeDescriptionIds("field-error", "field-help", "group-help field-help"))
  .toBe("field-error field-help group-help");
expect(mergeDescriptionIds()).toBeUndefined();
```

- [ ] 在 `web/` 运行 `rtk npm run test:unit -- src/components/ui/hints.test.ts src/components/ui/uiPrimitives.test.ts`，记录新增契约的预期失败，不把依赖故障当 RED。
- [ ] 实现 §3.2；FormField 同时保留必要 Help/Error 并改用 caption。缺失共享元素由调用方负责条件同步，组件不遍历全局 DOM猜测业务。
- [ ] 重跑上述用例并运行 `rtk npm run check:ui`；随后迁移批次用浏览器计算样式证明实际字号/颜色，不能用 happy-dom 样式字符串检查代替视觉结果。

### 任务 3：创建向导与级联共享帮助

**文件：** 新建 `features/creation/cascadeHelp.ts` 与测试；修改 `components/creation/ProjectStep.vue`、`GroupsStep.vue`、`StandardStep.vue`、`ReviewStep.vue`、`GroupBatchDialog.vue`、`SheetValuesDialog.vue`、`XlsxImportDialog.vue`、`views/CreateSheetSetView.vue` 及中英文 `creation.ts`；扩展 `tests/e2e/create-sheetset-input.spec.ts`、`create-sheetset-review.spec.ts` 和 `fixtures/creation.ts`。

**接口：** 消费任务 2 原语及既有创建 store/inputModel 的属性身份、取值、候选与错误；输出 §3.3 分组及控件描述关联，不改创建草稿负载。

- [ ] 编写 `same_parent_one_shared_help`、`different_parent_separate_help`、`different_group_separate_help`、`shared_help_ids_do_not_collide` 单测及对应输入 E2E；加入两个必填错误、非法旧级联值、上级选择后说明消失的回归。
- [ ] 运行 `rtk npm run test:unit -- src/features/creation/cascadeHelp.test.ts` 与 `rtk npm run test:e2e -- create-sheetset-input.spec.ts --workers=1 --retries=0`，记录有意义的 RED。
- [ ] 实现分组并接入 ProjectStep/GroupsStep 的禁用说明；共享 Help 指明上级名称，绑定所有相关控件，保留非法原值及清空入口。其他步骤按任务 1 清单迁移，保留最终路径、标准切换影响、XLSX 全量覆盖确认和不可覆盖声明。
- [ ] 重跑单测及 `create-sheetset-input.spec.ts`、`create-sheetset-review.spec.ts`；通过后核对请求负载、草稿保留与预览失效行为未漂移，保存候选/生产同状态证据。

### 任务 4：欢迎页与标准管理/编辑文案收口

**文件：** 修改 `views/WelcomeView.vue`、`StandardsView.vue`，`components/standards/StandardLibraryPane.vue`、`StandardDetailPane.vue`、`StandardEditor.vue`、`StandardBasicEditor.vue`、`StandardPublishReview.vue`、`StandardImportDialog.vue` 及任务 1 清单内的属性/模板子组件；中英文 `shell.ts/standards.ts`；扩展 `standards-welcome.spec.ts`、`standards-editor.spec.ts`、`standards-assets-publish.spec.ts`。

**接口：** 消费现有标准身份、描述、输入状态及原语；不改标准 Schema、保存/发布/复制/删除接口。已有资产复制、编号位数等其他任务交付保持原行为。

- [ ] 对修改状态/错误/危险后果写回归：无歧义标题不重复 Lead；编号位数帮助与错误可并存；导入、删除、标准切换保留后果；内部说明删除不影响必要身份和诊断数据。纯文案调整直接纳入候选走查。
- [ ] 运行对应失败用例，按清单迁移；保留欢迎页打开 DST 优先与现有布局，空状态按 §6.5 处理，不把空态文本强制包成 Status。
- [ ] 运行 `rtk npm run test:e2e -- standards-welcome.spec.ts standards-editor.spec.ts standards-assets-publish.spec.ts --workers=1 --retries=0` 与 `rtk npm run check:i18n`；核对浅深主题和长文本证据，记录本批差异裁决。

### 任务 5：图纸与属性编辑保留持续状态和错误定位

**文件：** 修改 `views/SheetsView.vue/PropertiesView.vue`、`components/sheets/SheetPropertyEditor.vue/SheetOperationForm.vue`、`components/properties/PropertyValuePanel.vue/PropertyDefinitionPanel.vue/PropertyCsvPanel.vue` 和清单内其他提示；中英文 `sheets.ts/properties.ts`；扩展 `sheets-editing.spec.ts`、`properties-values.spec.ts`、`properties-definitions.spec.ts`、`properties-csv.spec.ts`。

**接口：** 消费既有 `useSheetEditor`、`usePropertiesWorkspace` 状态和提交事件；不改比较基准或公开 props/emits。自建表格的行错误继续关联具体字段。

- [ ] 先写回归：两个空字段都能从摘要定位；范围帮助与错误并存；改回基准无写请求；延迟保存期间状态持续；失败保留输入；加入草稿后“待写入”在短暂成功提示结束后仍可见。
- [ ] 运行各归属 E2E 的新增用例取得 RED；迁移提示外观与描述顺序，只删除重复通知，不删 SPEC-DM-015 要求的修改文字或错误摘要。
- [ ] 重跑上述四份 E2E，并运行 `rtk npm run test:unit -- src/composables/useSheetProjection.test.ts src/composables/useDraftGuards.test.ts`。验证只影响提示、clean 动作和错误门禁保持；记录同状态截图及主要播报来源。

### 任务 6：设置、扩展配置与图纸目录

**文件：** 修改 `components/settings/SettingsFormRow.vue/SettingsDialog.vue/GeneratedExtensionSettingsForm.vue/ExtensionSettingsHost.vue/SheetCatalogSettingsPanel.vue`、`views/SheetCatalogView.vue`、`components/sheet-catalog/TemplateBar.vue/CatalogActions.vue/CatalogPreview.vue` 及清单内其他提示；中英文 `settings.ts/extensions.ts`；扩展 `settings-dialog.spec.ts`、`extensions-settings.spec.ts`、`sheet-catalog.spec.ts`。

**接口：** 消费 `useSettings/useExtensionSettings/useSheetCatalog` 的原有保存、错误和只读状态；用任务 2 关联/原语承接提示，不复制 Provider 校验。

- [ ] 为 SettingsFormRow 的 help/error 顺序、长格式说明、失败后脏状态保留、关闭反馈不解禁写入、目录模板保存不重复通知新增行为回归；已裁决的 Provider 409 口径沿用 SPEC-DM-015 §9。
- [ ] 运行新增失败用例；迁移共享及生成式表单提示，保留“无修改可保存”和只读原因。共享错误摘要负责播报时，逐字段说明保留关联并取消重复 alert。
- [ ] 运行 `rtk npm run test:unit -- src/composables/useSettings.test.ts src/composables/useExtensionSettings.test.ts`，上述三份 E2E 与 i18n 检查；确认保存/导出请求次数、取消行为、未提交输入保护不变。

### 任务 7：全局横幅、任务通知与剩余消费方

**文件：** 修改 `layout/WorkspaceShell.vue/ActionDock.vue/TaskOverlay.vue`、`components/JobStatusPanel.vue/PreviewPanel.vue/RepairStatusPanel.vue/RevisionHistoryPanel.vue`、`components/ui/ToastHost.vue`、`composables/useToast.ts/useJobMonitor.ts`、`styles/legacy.css`；复核 `features/creation/useCreationJob.ts`，只在其回归失败表明需要时修改；中英文 `shell.ts/jobs.ts/revisions.ts`。新建 §3.1 通知单测，扩展 `tests/e2e/main.spec.ts`、`create-sheetset-review.spec.ts`。

**接口：** `useToast()` 继续返回 `toasts/pushToast/dismiss`，Toast 的 `id/type/title/body/jumpTab` 和普通/创建任务监视器公开接口保持不变；使用已有 job ID、订阅代次和每次尝试终态标记去重，不在协议新增事件字段。

- [ ] 使用假计时器、伪 EventSource 和受控轮询写回归：成功 5000ms 结束、失败不自动消失、更多成功不能裁切掉未处理失败、浮层可见不弹、相同终态重复只通知一次、断线回退无重复、同 ID 新尝试能再次通知、陈旧订阅无副作用、`NEEDS_REVIEW` 不发直接重试请求。
- [ ] 运行 `rtk npm run test:unit -- src/composables/useToast.test.ts src/composables/useJobMonitor.test.ts` 取得 RED。
- [ ] 收口 ToastHost 的播报归属；在 useJobMonitor 现有代次范围内标记终态已处理，保留成功后刷新等既有动作恰好一次。useToast 的数量上限只裁切可丢弃的成功通知；失败如需视觉折叠，必须有可见汇总和完整查看入口，先回到 G4 裁决，不在实现时静默隐藏。
- [ ] 将 `.notice` 消费方逐一迁移到显式 tone；确认全部消费者和展开诊断已改后才删除危险底色兜底，不能全局换成中性底色让真实失败弱化。全局错误关闭仅改变呈现，后端/页面阻断状态保持，原始错误详情仍可查。
- [ ] 按任务 1 清单收口尚未覆盖的浮层、修订与结构性表单提示；复核同时存在 warning/error 时阻断可见、恢复动作仍经预览确认。
- [ ] 重跑通知单测、`main.spec.ts` 和 `create-sheetset-review.spec.ts`，并运行 `rtk proxy uv run pytest tests/unit/test_job_terminal_statuses.py -q`（仓库根目录）。UI 消费方通过后运行 `rtk npm run check:ui`；不新增按旧类名粗暴禁止的规则。

### 任务 8：综合验收、证据和文档收口（G7～G9）

**文件：** 新建 `web/tests/e2e/hint-contracts.spec.ts`；维护资产索引、任务 1 清单、本计划实际验证记录及 `changelog.md`、计划/产品索引。正式行为仍引用 SPEC-DM-006，不将规范正文复制进多个文档。

**接口：** 消费原语稳定标记、各页面 fixture 和既有状态/请求；输出 §10.4 十组场景的证据、门禁结论和剩余项。

- [ ] 新增跨页回归，验证真实计算样式：Lead 13px/secondary、Help 12px/muted、Status/Error 12px/对应语义色，四种 Banner 的前景/背景匹配；同时检查唯一 ID、有效描述引用、必要状态持续和同事件主要通知数量。不得把不同职责的“待写入”和“已加入草稿”算成重复。
- [ ] 在 `1024×768 / 1120×768 / 1440×900 / 900×768` × light/dark 采集矩阵；900px 仅作韧性测试。用长中文、英文、路径和多条错误覆盖换行/内容高度；浏览器 200% 检查记录实际设置，不能仅凭改视口宣称已测缩放。
- [ ] 执行 §6 的命令并逐条登记退出码、数量、失败/跳过原因。失败先修复或如实分类，不能沿用其他计划的通过数字。
- [ ] 人工读屏验证错误摘要聚焦、字段关联、禁用组说明、SSE/轮询终态只播报一次；axe 或 DOM 数量仅作辅助，不能证明实际播报不重复。
- [ ] 真实 Windows WebView2 浅/深主题 × 100/125/150/200% 复验创建、属性/设置、全局失败与任务结果；登记系统/壳版本、状态和裁决。真实桌面或读屏证据缺失时，已启动计划保持 `active`，不标 `completed`。
- [ ] 清单每条都有已迁移或经裁决保留的结论，未完成事项记录责任和恢复条件；全部门禁闭合后再更新计划状态、索引与 changelog。

## 6. 后续验证命令（本次不执行）

任务内先执行最小相关测试，集成收口时执行以下基线；命令均兼容 PowerShell，测试由执行阶段运行：

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

## 7. 规范覆盖与完成标准

| 规范要求 | 实施任务 | 证据 |
| --- | --- | --- |
| §6.7.1 分类、字号、数量与作用范围 | 1、2、3～7 | 迁移清单、原语契约、计算样式 |
| §6.7.2 提示选择、内部说明边界与安全承诺 | 1、3、4、5、7 | 候选裁决、路径/影响/恢复场景 |
| §6.7.3 持续状态、事件与播报去重 | 5、6、7 | 状态/请求断言、通知回归、人工读屏 |
| §6.7.4 共享 Help、逐字段 Error 与关联 | 2、3、5、6 | 依赖分组、唯一 ID、描述与摘要定位 |
| §6.7.5 四种横幅及独立风险 | 2、7 | 多风险回归、计算颜色、门禁保持 |
| §10.4 十组场景、§10.2 矩阵 | 8 | 分场景结果、截图与真实桌面记录 |

完成必须同时满足：任务 1 清单无遗漏、任务 2～7 对应行为和样式通过、任务 8 的自动化与人工证据完整、必要安全信息没有被删除、HTTP/SSE 和业务状态无漂移、changelog 与索引状态一致。代码测试通过而 G8/G9 未闭合时不得完成。

## 8. 风险与恢复策略

- 原语改动影响已迁移的其他页面：先增加关联回归，逐页检查真实样式；不批量替换所有小字或按类名猜用途。
- 合并提示隐藏不同依赖或同义字段错误：以对象/上级身份分组，只合并帮助；保留错误摘要和逐字段定位。
- 去重抑制新任务或重试结果：去重限定于当前监视尝试，测试同 ID 重试、跨工作区和陈旧回调。
- 用户关闭提示被误解为解除错误：展示组件不得修改业务阻断状态；未解决原因保持入口和状态可见。
- 全局类被其他页面使用或同期代码变化：先复查消费清单和当前工作区，只删除已无消费者的规则；偏差记录到本计划，不擅自还原其他任务。

## 9. 实际验证记录

2026-09-30：仅编写实施计划、维护导航和变更记录。计划任务均未执行，未运行本计划的产品测试、构建、浏览器、读屏或真实桌面验收。文档检查结果由本次交付报告提供；实施阶段在此追加任务、命令、退出码、证据链接与门禁裁决。
