---
id: PLAN-DM-016
title: DST Manager 属性页分区编辑实施计划
status: proposed
document_kind: plan
owners:
  - dst-manager
created: 2026-09-05
updated: 2026-09-05
related:
  - SPEC-DM-010
  - SPEC-DM-006
  - SPEC-DM-009
  - ARCH-DM-001
  - PLAN-DM-013
  - PLAN-DM-015
---

# DST Manager 属性页分区编辑实施计划

> **执行代理：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实施；按复选框记录进度。本次只编制计划，不启动实施、不自动提交 Git、不指定发布版本。

**目标：** 将属性标签实现为字段定义与图纸集属性值相互独立、可折叠且有可靠输入缓冲的工作区，并完整保留既有草稿、CSV 与正式发布安全门禁。

**架构：** 后端 HTTP/SSE、命令 schema、CSV 格式和 DST 发布链路保持不变。新增属性页专用纯函数和 `usePropertiesWorkspace` 组合式函数，分别负责三基准比较、搜索/分页以及会话缓冲；`PropertiesView` 只组合面板组件，`App.vue` 只保留跨域草稿提交与全局门禁编排。字段定义增删继续投影到既有命令簿，CSV 继续使用现有正式导入端点。

**技术栈：** Vue 3、TypeScript、Vite、Playwright；Python 3.12+、UV、FastAPI（仅做兼容性回归）。默认不增加依赖、不增加数据库迁移、不修改业务 OpenAPI。

**规范：** [SPEC-DM-010（accepted）](../../../docs/dst-manager/specs/SPEC-DM-010-properties-workspace-ui.md)。交互参考：[HTML Demo](../../../docs/dst-manager/mockups/SPEC-DM-010-properties-demo.html)。公共门禁：[SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md)；图纸页输入保护：[SPEC-DM-009 §6.2](../../../docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md#62-未提交输入保护)；安全基线：[ARCH-DM-001](../../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)。

## 1. 全局约束

- 先完成或合并 PLAN-DM-015，再从最新工作树执行本计划；两计划共同涉及 `web/src/App.vue`、`web/src/style.css`、`web/tests/e2e/fixtures/sheets.ts` 时按语义合并，不覆盖图纸页的新状态、列配置、编辑器或测试。
- 保持 `update_sheet_set`、`add_custom_property`、`delete_custom_property` 及三个 CSV 端点 verbatim；不新增字段分组、类型、重命名、默认值编辑、数据库表或壳桥。
- 图纸集名称与自定义属性“工程名称”是不同身份；属性值只使用字符串，不 trim、转换、合并日期或用默认值补空值。
- 页面缓冲由正式基准、草稿投影、当前输入三层比较；琥珀表示未加入草稿，蓝色表示待写入，红色只表示错误/冲突，并同时配文字。
- 字段定义与结构命令继续分批；CSV 是正式写入，不能加入普通草稿、不能顺带提交属性值缓冲、不能绕过强确认。
- 只读打开不写工程目录；所有正式写入继续走预览、基准修订、永久 before 快照、暂存与回滚。测试不得读写 `sample/` 原件。
- Windows 11、PowerShell、UTF-8、简体中文；服务仍仅监听 `127.0.0.1`。不增加 npm/Python 依赖。
- 单文件约 500 行为软上限。不得把属性页状态继续堆入已经超限的 `App.vue`；通用 UI 原语才进入 `components/ui/`，属性业务组件放入 `components/properties/`。
- 每项任务遵循失败测试→最小实现→相关回归→审查。仅在用户明确授权时提交；建议提交消息已列出，但不自动执行。

## 2. 当前代码依据与文件分工

| 当前事实 | 处理方向 |
| --- | --- |
| `PropertiesView.vue` 直接 `v-model` 修改 `workspace`，名称和属性分别提交时都发送完整 `update_sheet_set` | 改为独立缓冲，单次提交完整名称与属性副本，不污染 props |
| `PropertyPanel.vue` 常驻显示全部定义、新增表单和 CSV 控件 | 拆成定义面板、分页表、新增区和按需 CSV 区 |
| `App.vue` 的 `queueSheetSet`、`queuePropertyDefinition`、`queueDeleteProperty` 直接编排 | 元数据提交改走组合式函数；定义命令仍经现有 `submitCommands`/命令簿门禁 |
| `projectWorkspace` 已投影名称、属性值及定义增删；`submitCommands` 已处理保存失败与权威投影 | 复用，禁止另建属性草稿栈或前端最终校验器 |
| `useCsvImport` 已校验工作区、revision、CSV 快照并使用强确认 | 扩展界面状态和统一缓冲门禁，不改变请求/响应契约 |
| 现有 E2E 主要集中在 `main.spec.ts` | 新增属性页独立夹具与 spec，旧断言仅做必要迁移 |

计划新增文件：

| 文件 | 单一职责 |
| --- | --- |
| `web/src/features/properties/types.ts` | 字段身份、缓冲、比较状态、搜索范围、折叠/分页状态类型 |
| `web/src/features/properties/model.ts` | 无副作用的比较、过滤、分页、隐藏修改统计和命令构造 |
| `web/src/composables/usePropertiesWorkspace.ts` | 会话缓冲、活动字段、错误映射、折叠/查询状态及提交生命周期 |
| `web/src/components/properties/PropertyDefinitionPanel.vue` | 定义面板外壳、查询、分页、新增/删除和 CSV 区组合 |
| `web/src/components/properties/PropertyDefinitionTable.vue` | 六条分页表、空态、长默认值与可访问删除按钮 |
| `web/src/components/properties/PropertyValuePanel.vue` | 名称、值搜索、三态标记、值对照和局部提交 |
| `web/src/components/properties/PropertyValueCompareDialog.vue` | 原文件/草稿/输入三阶段对照与焦点归还 |
| `web/src/components/properties/PropertyCsvPanel.vue` | 选择、预览、诊断、确认入口及预览失效状态 |
| `web/src/components/properties/PropertyUnsavedDialog.vue` | 加入草稿后继续/放弃输入/留在此处三选一 |
| `web/tests/e2e/fixtures/properties.ts` | 36 定义、33 值及 API/草稿/CSV 失败场景的虚构夹具 |
| `web/tests/e2e/properties-workspace.spec.ts` | SPEC-DM-010 功能、响应式、键盘与安全门禁验收 |

## 3. 公共接口

任务 1 建立并由后续任务复用以下接口；字段身份始终是 `type + name`，不能只用名称：

```ts
export type PropertyKey = `${'sheetset'|'sheet'}:${string}`;
export type ValueKey = '@name' | `sheetset:${string}`;
export type PropertySearchMode = 'all'|'name'|'value';
export type ValueStatus = {dirty:boolean; pending:boolean; invalid:boolean};
export type PropertyBuffer = {name:string; values:Record<string,string>};
export type PropertySubmitResult = {ok:boolean; message?:string; fields?:Record<string,string>};

export function createPropertyBuffer(workspace:Workspace):PropertyBuffer;
export function valueStatus(base:PropertyBuffer,draft:PropertyBuffer,input:PropertyBuffer,key:ValueKey,invalid:Set<ValueKey>):ValueStatus;
export function filterValueKeys(input:PropertyBuffer,query:string,mode:PropertySearchMode,changedOnly:boolean,statusOf:(key:ValueKey)=>ValueStatus):ValueKey[];
export function buildSheetSetCommand(input:PropertyBuffer):ChangeCommand;
```

组合式函数接口：

```ts
export function usePropertiesWorkspace(deps:{
  workspace:Ref<Workspace|null>;
  baseWorkspace:Ref<Workspace|null>;
  submitCommands(commands:ChangeCommand[],label:string,category:'metadata'|'structural'|'property'):Promise<PropertySubmitResult>;
}):{
  input:Ref<PropertyBuffer|null>; dirtyKeys:ComputedRef<ValueKey[]>; pendingKeys:ComputedRef<ValueKey[]>;
  hiddenDirtyCount:ComputedRef<number>; submitValues():Promise<PropertySubmitResult>;
  revertValue(key:ValueKey):void; discardInput():void; guard(next:()=>void|Promise<void>):Promise<void>;
  syncFromProjection():void; markInvalid(names:string[]):void;
};
```

## 4. 实施任务

### Task 1：属性三基准模型与契约测试

**文件：**
- Create: `web/src/features/properties/types.ts`
- Create: `web/src/features/properties/model.ts`
- Create: `web/tests/e2e/properties-model.spec.ts`

**接口：** 产出第 3 节所有纯函数和类型；只消费 `Workspace`、`ChangeCommand`，不依赖 Vue DOM。

- [ ] **Step 1：先写失败测试**，用 33 项值夹具断言：名称/工程名称身份独立；dirty 与 pending 可并存；空串、空格、前导零原样保留；字段名/当前值三种搜索；仅看修改；活动字段不匹配时暂留且隐藏数为 0；失效字段不进入命令。

```ts
expect(valueStatus(base,draft,input,'sheetset:工程名称',new Set())).toEqual({dirty:true,pending:true,invalid:false});
expect(buildSheetSetCommand(input)).toEqual({type:'update_sheet_set',name:input.name,custom_properties:input.values});
expect(filterValueKeys(input,'二期','value',false,statusOf)).toContain('sheetset:工程名称');
```

- [ ] **Step 2：运行红灯**：`cd web; npx playwright test tests/e2e/properties-model.spec.ts`；预期因模块不存在失败。
- [ ] **Step 3：最小实现纯函数**。比较必须使用严格字符串相等；搜索仅为 `toLocaleLowerCase().includes()`；`buildSheetSetCommand` 复制完整映射且遇到 invalid key 抛出 `PROPERTY_BUFFER_STALE`。
- [ ] **Step 4：运行绿灯与类型检查**：同一 Playwright 文件通过；`npm run build` 零类型错误。
- [ ] **Step 5：审查并按授权提交**：只暂存本任务三个文件；建议消息 `建立属性页三基准状态模型`。

### Task 2：会话缓冲、提交生命周期与统一输入保护

**文件：**
- Create: `web/src/composables/usePropertiesWorkspace.ts`
- Create: `web/src/components/properties/PropertyUnsavedDialog.vue`
- Modify: `web/src/App.vue`
- Test: `web/tests/e2e/properties-buffer.spec.ts`

**接口：** 消费 Task 1 模型和现有 `submitCommands`；产出第 3 节组合式接口。`App.vue` 把属性 guard 与 PLAN-DM-015 的 sheet editor guard 串联成 `guardAllInputs(next)`。

- [ ] **Step 1：写失败测试**：直接编辑不改变 workspace props；隐藏的两项修改一次完整加入草稿；失败保留输入和字段错误；成功后以草稿投影重建输入；撤回仅回到草稿；折叠/标签切换保留；关闭、刷新、预览、确认、CSV 和切工作区均触发三选一。

```ts
await page.getByLabel('属性 工程名称').fill('二期');
await page.getByRole('tab',{name:'图纸'}).click();
await page.getByRole('tab',{name:'属性'}).click();
await expect(page.getByLabel('属性 工程名称')).toHaveValue('二期');
expect(lastDraft.commands[0].custom_properties).toEqual(expect.objectContaining({'工程名称':'二期','编号':'001'}));
```

- [ ] **Step 2：运行红灯**：`cd web; npx playwright test tests/e2e/properties-buffer.spec.ts`；预期旧页面直接修改 workspace 或无三选一而失败。
- [ ] **Step 3：实现组合式函数**：workspace/revision 切换时新建三层快照；普通投影变化调用 `syncFromProjection()`；删除定义使活动 key 进入 invalid 集合并保留输入；`submitValues()` 只生成一个完整 `update_sheet_set` 命令并等待 `submitCommands(...,'metadata')` 结果。把现有 `submitCommands` 的 category 联合扩为 `'metadata'|'structural'|'property'`，property 分支复用 `addCommandBatch` 的结构冲突门禁和保存失败重试。
- [ ] **Step 4：接入全局门禁**：`showPreview`、`write`、`closeWorkspace`、刷新/重新打开和 `importCsv` 的前置入口统一调用 `guardAllInputs`；“加入草稿后继续”必须等待保存与投影，“放弃”只清输入，“留在此处”不执行 next。
- [ ] **Step 5：验证**：本任务 spec 通过；现有 `sheets-editor.spec.ts`、`main.spec.ts` 中预览/关闭/CSV 用例通过，证明没有绕过图纸页保护。
- [ ] **Step 6：审查并按授权提交**：建议消息 `实现属性页缓冲与全局输入保护`。

### Task 3：属性值面板、搜索与三态反馈

**文件：**
- Create: `web/src/components/properties/PropertyValuePanel.vue`
- Create: `web/src/components/properties/PropertyValueCompareDialog.vue`
- Modify: `web/src/views/PropertiesView.vue`
- Test: `web/tests/e2e/properties-values.spec.ts`

**接口：** 消费 `usePropertiesWorkspace` 的缓冲、状态、过滤和动作；不直接 emit API 命令，不修改 `Workspace`。

- [ ] **Step 1：写失败测试**：33 项原顺序、最多两列、无分组无分页；全部为 text input；图纸集名称独立；字段名/值搜索和仅看修改取交集；暂留活动字段；琥珀/蓝/红及文字并存；隐藏修改计数；值对照和单项撤回。

```ts
await expect(page.getByText('未加入草稿')).toBeVisible();
await expect(page.getByText('待写入')).toBeVisible();
await page.getByRole('button',{name:'值对照 工程名称'}).click();
await expect(page.getByRole('dialog')).toContainText('原文件值');
```

- [ ] **Step 2：运行红灯**：`cd web; npx playwright test tests/e2e/properties-values.spec.ts`；预期旧 `details/form-grid` 不满足断言。
- [ ] **Step 3：实现值面板**：CSS Grid 使用 `repeat(2,minmax(240px,360px))` 并在窄宽度降为一列；长值项设置 full-width/展开编辑；DOM 顺序与服务端映射顺序一致，不排序、不补定义。
- [ ] **Step 4：实现三态与可访问性**：输入 `aria-describedby` 指向状态/错误；错误边框优先但保留 dirty/pending 文本；对照 dialog 支持 Esc、焦点圈闭和关闭后回触发按钮。
- [ ] **Step 5：验证**：本任务测试通过；用 1024×768、1120×768、1440×900、900×768 的浅/深主题断言 `document.documentElement.scrollWidth <= innerWidth`。
- [ ] **Step 6：审查并按授权提交**：建议消息 `重建属性值编辑面板`。

### Task 4：字段定义折叠、查询、六条分页与增删

**文件：**
- Create: `web/src/components/properties/PropertyDefinitionPanel.vue`
- Create: `web/src/components/properties/PropertyDefinitionTable.vue`
- Modify: `web/src/views/PropertiesView.vue`
- Modify or Delete when unreferenced: `web/src/components/PropertyPanel.vue`
- Test: `web/tests/e2e/properties-definitions.spec.ts`

**接口：** 输入草稿投影的 `PropertyDefinition[]`；新增/删除输出既有 `ChangeCommand`，经 App 提供的 `submitCommands(...,'property')` 加入同一草稿栈；不得绕过 `hasStructuralCommands` 门禁。

- [ ] **Step 1：写失败测试**：36 定义初始折叠；展开只显示六条；名称/默认值搜索、作用域筛选、页码复位、最后一页删除回退；同名跨作用域独立；空/长默认值；新增失败保留输入；筛选不匹配时“查看字段”；删除前处理对应未提交值。
- [ ] **Step 2：运行红灯**：`cd web; npx playwright test tests/e2e/properties-definitions.spec.ts`；预期旧无限表失败。
- [ ] **Step 3：实现表格纯派生**：`filteredDefinitions` 保持输入顺序；`pageSize=6`；查询变化 `page=1`；删除后 `page=Math.min(page,lastPage)`；key 为 `${type}:${name.toLocaleLowerCase()}`。
- [ ] **Step 4：实现新增与删除**：新增区只有作用域/名称/默认值；成功关闭或清空输入，失败映射字段错误；删除按钮可见且 accessible name 含作用域和名称，确认文案不虚构影响数量。
- [ ] **Step 5：接分批门禁**：若有结构命令，新增/删除返回既有提示；若目标 sheetset 值仍 dirty，先运行属性输入 guard，再弹删除确认；空值不视为删除。
- [ ] **Step 6：验证与审查**：本任务测试、`properties-buffer.spec.ts` 及生产构建通过；无引用后才删除旧 `PropertyPanel.vue`。建议提交 `实现属性字段定义分页维护`。

### Task 5：CSV 渐进流程和普通草稿隔离

**文件：**
- Create: `web/src/components/properties/PropertyCsvPanel.vue`
- Modify: `web/src/components/properties/PropertyDefinitionPanel.vue`
- Modify: `web/src/composables/useCsvImport.ts`
- Modify: `web/src/App.vue`
- Test: `web/tests/e2e/properties-csv.spec.ts`

**接口：** 继续消费 `CsvPreviewContext={workspaceId,baseRevisionId,csv,result}` 和现有三个 API；组件只展示/派发动作，正式确认仍由 `useCsvImport.importCsv()` 完成。

- [ ] **Step 1：写失败测试**：默认不显示 file input；打开、UTF-8 读取、预览新增/跳过/冲突及行号；无效数据禁用确认；换文件/workspace/revision/定义基准后预览失效；强确认勾选前禁用；普通未提交输入必须三选一且 CSV 不自动保存；已有普通草稿冲突按门禁阻断。
- [ ] **Step 2：运行红灯**：`cd web; npx playwright test tests/e2e/properties-csv.spec.ts`；预期旧常驻 CSV 流程和隔离不足失败。
- [ ] **Step 3：实现按需面板**：下载模板/导出链接保持原 URL；选择文件后才显示预览操作；changes 按 response 顺序显示 action/type/name/line，diagnostics 保留 code/message/severity。
- [ ] **Step 4：完善失效与门禁**：文件选择代次沿用 `csvGeneration`；投影中影响定义的命令变化调用 `invalidateCsvPreview(false)`；确认前先 `guardAllInputs`，但选择“加入草稿后继续”若造成普通草稿与 CSV 冲突则明确阻断并要求分批，不清空任何一方。
- [ ] **Step 5：验证**：本任务测试与已有 CSV API 集成测试通过：`uv run pytest tests/integration/test_api.py -k "property_csv" -q`；确认请求仍含原 `base_revision_id/csv/preview_digest`。
- [ ] **Step 6：审查并按授权提交**：建议消息 `完善属性 CSV 渐进导入门禁`。

### Task 6：页面组合、状态摘要、折叠恢复和错误跳转

**文件：**
- Modify: `web/src/views/PropertiesView.vue`
- Modify: `web/src/App.vue`
- Modify: `web/src/style.css`（仅必要公共令牌；优先 scoped）
- Create: `web/tests/e2e/fixtures/properties.ts`
- Create: `web/tests/e2e/properties-workspace.spec.ts`
- Modify: `web/tests/e2e/main.spec.ts`（仅迁移旧属性选择器）

**接口：** `PropertiesView` 接收已组合的 view-model 与动作；不持有 API、草稿栈或正式写入逻辑。折叠/查询/页码为工作区会话态，切 workspace 重置为定义折叠、值展开。

- [ ] **Step 1：建立虚构夹具**：生成 36 个定义、33 个真实存在的 sheetset 值、3 个 sheet 定义；包括空值、长值、同名跨作用域和错误响应，不含真实客户路径。
- [ ] **Step 2：写端到端失败测试**：覆盖 P-01 至 P-12；面板标题折叠后仍显示字段/dirty/pending/error/CSV 状态；错误摘要展开目标面板并聚焦字段；切标签保留，切工作区重置。
- [ ] **Step 3：组合页面**：删除旧名称横条；定义和值面板顺序固定；无定义与查询无结果采用不同空态；无自定义值时仍展示名称和新增 sheetset 字段入口。
- [ ] **Step 4：收紧 App 边界**：移除旧 `propertyForm`、`queueSheetSet` 等页面专用状态或改为组合式依赖；保留 `submitCommands`、命令簿、预览/执行、CSV/job 的跨域编排。若 App 仍新增净行数，继续把属性门禁协调抽到组合式函数，不能突破软上限后再追加。
- [ ] **Step 5：迁移旧测试**：只替换旧 `.summary input`、`更新图纸集` 和 `PropertyPanel` 选择器；原草稿恢复、撤销重做、发布、CSV 强确认断言必须保留或增强，不得删除以换取通过。
- [ ] **Step 6：验证与审查**：运行属性页全部 E2E、`main.spec.ts` 与 `npm run build`。建议提交 `接入属性页分区工作区`。

### Task 7：全量回归、人工矩阵与文档收口

**文件：**
- Modify: `changelog.md`
- Modify: `.planning/plans/dst-manager/PLAN-DM-016-properties-workspace-ui.md`
- Modify: `docs/dst-manager/README.md`（仅状态完成时）

**接口：** 不新增产品能力；只记录实际证据。计划仅在全部完成标准满足后改为 `completed`。

- [ ] **Step 1：运行静态与后端回归**：`uv run ruff check .`、`uv run pytest -q`、`uv lock --check`、`uv run alembic upgrade head`；记录通过/跳过/失败数及原因。
- [ ] **Step 2：运行 Web 全量验证**：`cd web; npm ci; npm run build; npm run test:e2e`；必须包含 PLAN-DM-015 的图纸页用例，确认共享 App/样式未回归。
- [ ] **Step 3：人工视觉/键盘矩阵**：1024×768、1120×768、1440×900、900×768 × 浅深主题，分别检查默认、dirty+pending、错误、新增、CSV；Tab/Shift+Tab、Enter/Space、Esc、焦点归还、200% 缩放，无整页横向溢出。
- [ ] **Step 4：安全抽查**：浏览器网络面板确认局部“加入草稿”只 PUT draft/预览投影，不调用 execute/import；CSV 强确认才调用 import；真实工程测试仅复制样本到临时目录且由用户显式授权。
- [ ] **Step 5：记录结果**：changelog 写实际文件和数字；计划增加“实际验证”小节。任一必需门禁失败时保持 `active` 或 `blocked` 并写恢复条件，不得写完成。
- [ ] **Step 6：最终差异审查**：`git diff --check`、`git status --short`；确认无 `.env`、sample、截图、Playwright 结果、`web/dist`、`node_modules` 或私有路径进入提交树。
- [ ] **Step 7：按授权提交**：只暂存本计划实现文件；建议消息 `完成属性页分区编辑工作区`。不自动 tag、发布或推送。

## 5. 验证映射

| SPEC 验收 | 计划任务 |
| --- | --- |
| P-01、P-02 字段定义分页/筛选/边界 | Task 4、6 |
| P-03 三十多个文本值、顺序、两列、名称隔离 | Task 1、3、6 |
| P-04 输入生命周期、失败、冲突、恢复语义 | Task 2、6 |
| P-05 定义/结构分批与局部草稿 | Task 2、4 |
| P-06 CSV 全流程与无旁路 | Task 5、7 |
| P-07 视口与双主题 | Task 3、7 |
| P-08 自动验证和虚构夹具 | Task 6、7 |
| P-09 独立折叠与状态保留 | Task 2、6 |
| P-10 三态、对照、撤回、保存失败 | Task 1、2、3 |
| P-11 搜索、暂留、隐藏计数、完整提交 | Task 1、2、3 |
| P-12 空值、删除冲突、CSV 隔离 | Task 1、4、5 |

## 6. 风险与控制

- **与 PLAN-DM-015 并发冲突：** 本计划不在当前并发工作树直接实施；执行前以最新 App、样式和夹具为基准重新读文件，禁止覆盖式回退。
- **直接修改 props 导致基准污染：** Task 1/2 先建纯缓冲模型，组件只绑定 input；E2E 检查未提交时预览命令为空。
- **完整映射提交误覆盖：** 命令必须来自当前草稿投影的全量副本，再应用本区缓冲；定义删除导致 key 失效时阻断，不把值重绑到同名字段。
- **双重 guard 顺序混乱：** `guardAllInputs` 固定先处理当前可见活动编辑器，再处理另一域；任一步选择“留在此处”即终止 next，不能出现两个模态叠加。
- **CSV 与草稿形成隐式混合批次：** 正式 CSV 保留独立 preview digest 和强确认；存在冲突命令时明确要求先完成/放弃一批。
- **大字段量渲染与可读性：** 值不分页但只有文本输入和计算状态；36/100/300 字段夹具做响应性基线，不引入虚拟化改变交互。

## 7. 完成标准

- SPEC-DM-010 P-01 至 P-12 均有自动或明确人工证据，且 Demo 与生产文案差异已审查。
- 属性页不再直接修改 workspace props；名称和值的隐藏修改完整加入同一 `update_sheet_set` 草稿动作，失败不丢输入。
- 定义默认折叠、每页六条；值默认展开、原顺序、最多两列、不分组不分页；折叠和标签切换保留会话状态。
- 三态标记、值对照、撤回、错误聚焦、活动字段暂留和隐藏计数均可键盘使用且不只依赖颜色。
- 字段定义/结构分批、普通草稿/CSV 隔离、基准漂移、预览失效和强确认不存在旁路。
- 后端 API、OpenAPI、数据库和 DST/CAD 发布链路无非必要变化；PLAN-DM-015 全量用例通过。
- Ruff、pytest、UV lock、迁移、Web build、Playwright 全量及 `git diff --check` 通过；任何跳过均有可核验原因。
- changelog、计划实际验证和索引同步；计划状态仅在全部条件满足后改为 `completed`。
