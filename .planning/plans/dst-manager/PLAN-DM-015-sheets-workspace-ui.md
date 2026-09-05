---
id: PLAN-DM-015
title: DST Manager 图纸页单表工作区实施计划
status: active
document_kind: plan
owners:
  - dst-manager
created: 2026-09-04
updated: 2026-09-05
related:
  - SPEC-DM-009
  - SPEC-DM-006
  - SPEC-DM-008
  - SPEC-DM-005
  - ARCH-DM-001
  - PLAN-DM-013
  - PLAN-DM-014
  - PLAN-DM-017
---

# DST Manager 图纸页单表工作区实施计划

> 执行代理：使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans` 逐任务实施；按复选框记录进度。本次只编制计划，不启动实施、不自动提交 Git、不指定发布版本。

**目标：** 将图纸页改为左树右单表工作区，完整实现已确认的导航、列配置、缓冲编辑、参照插入与草稿交互。

**架构：** 保留 Vue 3 外壳及现有 HTTP/SSE、命令、持久草稿和发布链路。图纸状态从 App.vue 定向拆分；结构显示消费已有服务端预览派生结果，不在浏览器实现命名算法。原生文件夹入口与列偏好通过受限壳桥提供，偏好只写应用数据目录。

**技术栈：** Vue 3、TypeScript、Vite、Playwright；Python 3.12+、UV、FastAPI、pywebview/WebView2。默认不增加依赖或数据库迁移。

**规范：** [SPEC-DM-009（accepted）](../../../docs/dst-manager/specs/SPEC-DM-009-sheets-workspace-ui.md)。交互参考：[HTML Demo](../../../docs/dst-manager/mockups/SPEC-DM-009-sheets-demo.html)。公共门禁：[SPEC-DM-006](../../../docs/dst-manager/specs/SPEC-DM-006-dst-manager-desktop-ui-ux.md)；模板：[SPEC-DM-008](../../../docs/dst-manager/specs/SPEC-DM-008-v032-naming-and-template-flows.md)；整子集删除：[SPEC-DM-005](../../../docs/dst-manager/specs/SPEC-DM-005-controlled-subset-deletion.md)；安全基线：[ARCH-DM-001](../../../docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md)。

## 1. 全局约束与前置检查

- “HTTP/SSE、序列化字段与错误码均不变。”壳桥新增方法不进入业务 OpenAPI；若现有派生响应无法支持要求，先报告具体缺口并评审，不自行扩展业务协议。
- “配置按图纸集记忆在应用数据目录，不写入 DST 或工程目录”。不能把 Demo 的 localStorage 当正式存储。
- “图号、派生标题、范围和文件/布局派生名不可编辑。”前端仅映射对象参照至既有 ordinal/placement，不重新实现后端派生或最终校验。
- “只有成功加入既有持久草稿的动作才承诺重开恢复”。内存缓冲与服务端草稿保存状态必须分开。
- “单行编辑、新增表单、子集标题编辑和批量编辑共用一个活动编辑上下文”。不改变属性页 SPEC-DM-010，不复制该页的定义管理功能。
- Windows 11 / PowerShell；服务仅监听 `127.0.0.1`；UTF-8、简体中文。保留未知 AcSm 数据、before 快照、锁、暂存、回滚、预览摘要与任务门禁。
- 不改 `sample/` 原件；所有公开夹具虚构。真实 CAD 测试需显式启用；不复制 Demo 的计数上限 20、属性长度 200 或模拟文件名。
- 文件约 500 行为软上限。App.vue 当前已接近/超过上限，新图纸状态与逻辑不得继续堆入；只做本域拆分，不重构无关发布/修复域。
- 开始执行时先检查 `git status --short`、相关 AGENTS/README 与依赖锁。与 [PLAN-DM-014](PLAN-DM-014-windows-release-packaging.md) 都会接触 `shell.py`/`api.py`，必须基于最新版本合并，保留 frozen 资源路径、Worker 启动与生命周期行为。
- 每项实施遵循失败测试→最小实现→回归→审查；每个可独立交付任务更新 changelog。只有用户授权提交时才按任务提交，不自动 tag、打包或发布。

## 2. 当前代码依据与关键风险

| 当前文件 | 已观察事实 | 计划处理 |
| --- | --- | --- |
| `web/src/views/SheetsView.vue` | 全局表、子集编辑表并存；新增表单常驻，直接 v-model 修改 props 内对象 | 任务 3、5、6：唯一主表与独立缓冲 |
| `web/src/App.vue` | selectedId 与 subsetFilter 独立；持有查询、批量、模板和新增状态 | 任务 3、5、6：统一 scope，状态宿主在主标签之外 |
| `web/src/drafts.ts` | projectWorkspace 只投影元数据/字段定义；未投影 insert/delete；projectCommands 按键压缩命令 | 任务 1：验证完整结构投影与稳定对象身份 |
| `domain/planning.py` | new_acsm_id 由基准、命令索引与 suffix 确定；derived_document 含 acsm_id/派生名称/属性/布局 | 命令压缩或移除早期动作可能改变新增 ID，禁止按行号偷偷重绑 |
| `web/src/api/shell.ts`、`interfaces/shell.py` | 仅文件选择、拖拽桥；没有可信当前工作区与偏好接口 | 任务 2：显式会话上下文和安全存储 |
| `useConfirm.ts` | 现有确认只返回 boolean | 任务 5：独立三选一输入保护，不破坏既有强确认 |
| `web/tests/e2e/main.spec.ts` | 集中式假壳与 API 路由夹具，旧选择器依赖旧结构 | 新建本域测试和夹具，迁移旧选择器而不删减安全断言 |

最先验证结构投影，不先画完组件再发现数据不支持。普通元数据可沿用本地只读副本投影；结构变化通过现有 `/changes/preview` 的 `execution_intent.derived_document` 获取权威显示结果。该内部请求与用户显式发布预览分离：绝不设置 `previewContext`、不打开发布确认、不启动 CAD。

## 3. 文件与接口分工

下列新增路径为实施目标，不表示文件已经存在。接口属于前端/壳内部，不改业务命令 schema。

| 文件 | 职责 |
| --- | --- |
| `web/src/features/sheets/types.ts` | scope、列身份、编辑上下文、版本快照 |
| `web/src/features/sheets/projection.ts` | derived_document → Workspace 显示副本适配 |
| `web/src/features/sheets/commands.ts` | 参照 ID → 现有 createCommand；完整属性副本 |
| `web/src/composables/useSheetsWorkspace.ts` | scope、查询、选择、80 行加载、定位 |
| `web/src/composables/useSheetProjection.ts` | 结构请求、代次丢弃、失败/失效状态 |
| `web/src/composables/useSheetColumns.ts` | 列偏好、字段墓碑、存储失败回退 |
| `web/src/composables/useSheetEditor.ts` | 唯一上下文、缓冲、分页、错误、提交生命周期 |
| `web/src/components/sheets/SheetTree.vue` | 全部/子集/图纸树与键盘导航 |
| `web/src/components/sheets/SheetToolbar.vue` | 搜索、低频筛选、条件标签、选择条 |
| `web/src/components/sheets/ColumnSettings.vue` | 固定列锁定、可选列搜索与重置 |
| `web/src/components/sheets/SheetPropertyEditor.vue` | 每页 6 属性与错误跳转 |
| `web/src/components/sheets/SheetOperationForm.vue` | rename/insert-sheet/insert-subset/bulk 表单；若接近 500 行按表单拆分 |
| `web/src/components/sheets/UnsavedInputDialog.vue` | 保存继续/放弃/留下三选一 |
| `src/dst_manager/application/shell_context.py` | 可信桌面当前工作区登记，不暴露任意路径设置 |
| `src/dst_manager/infrastructure/sheet_preferences.py` | 应用目录 JSON 原子存储；无工程写入 |
| `src/dst_manager/infrastructure/explorer.py` | Windows 文件资源管理器结构化调用 |

修改现有 `SheetsView.vue`、`SheetTable.vue`、`App.vue`、`TopBar.vue`、`api/shell.ts`、`drafts.ts`、`interfaces/shell.py`、`interfaces/api.py`；定向删除不再引用的 ProjectNavigation（执行前确认无其他调用）。样式优先组件 scoped，必要公共令牌复用 `style.css`，不重写属性/修订页样式。

公共类型在任务 1 建立：

```ts
import type {ChangeCommand, Placement, Workspace} from '../../api/contracts';
export type SheetScope = {kind:'all'} | {kind:'subset';id:string};
export type ProjectionStamp = {
  workspaceId:string; revisionId:string; generation:number; commandKey:string;
};
export type PropertyKey = `sheet:${string}`;
export type ColumnPreferences = {
  schemaVersion:1; file:boolean; layout:boolean;
  subsetAll:boolean; subsetSingle:boolean;
  properties:Record<PropertyKey,boolean>;
};
export type SheetRef = {subsetId:string;sheetId:string;placement:Placement};
export type SubmitResult =
  | {ok:true}
  | {ok:false;message:string;fields?:Record<string,string>};
export type SubmitCommands = (
  commands:ChangeCommand[], label:string,
  category:'metadata'|'structural'
) => Promise<SubmitResult>;
```

`PropertyKey` 的名称按既有大小写匹配规则规范化；实际显示仍保留服务端原名。内置列使用独立 `builtin:` 命名空间。stamp 的 commandKey 是当前有效命令的规范化 JSON，不是发布摘要。

## 4. 任务清单

### 任务 1：权威结构投影与命令身份验证（先行门禁）

文件：新增 `types.ts`、`projection.ts`、`useSheetProjection.ts`；修改 `drafts.ts` 与 App.vue 的 `rebuildDraftProjection` 调用边界；新增 `web/tests/e2e/sheets-projection.spec.ts`、`tests/unit/test_sheet_projection_contract.py`。读取 `domain/planning.py`、`interfaces/responses.py`、`tests/unit/test_v021_editing.py`。

产出：`applyDerivedProjection(base:Workspace, preview:Preview):Workspace`；`useSheetProjection` 提供只读 projection、stamp、pending、error 和 `refresh():Promise<SubmitResult>`。不将显示副本写回 baseWorkspace。

- [ ] 写失败测试：用最小临时 DST 夹具通过既有预览路径依次覆盖 insert→属性编辑、insert→insert、delete→undo、rename→insert；无 CAD。断言响应 ID、数量、属性、顺序以及重复请求一致。
- [ ] 加浏览器失败用例：两个投影请求逆序返回只能应用最后一个；投影请求不得使“确认写入”启用。

```ts
// 在 sheets-projection.spec.ts，使用任务 3 的虚构夹具初始化页面。
await expect(page.getByRole('button',{name:'确认写入'})).toBeDisabled();
// 假路由释放新 generation，再释放旧 generation 后仍显示最新数量。
await expect(page.getByText('匹配 15 / 全部 15 张',{exact:true})).toBeVisible();
await expect(page.getByRole('button',{name:'确认写入'})).toBeDisabled();
```

- [ ] 运行 `rtk proxy uv run pytest tests/unit/test_sheet_projection_contract.py -q` 与 `rtk proxy npm --prefix web run test:e2e -- sheets-projection.spec.ts`，确认失败原因确为缺少投影接线。
- [ ] 按以下适配核心实现；完整 Subset/Sheet 必填字段对照生成类型逐个映射，新增对象不得填造真实 Handle 或 resolved_path。

```ts
const derived = preview.execution_intent?.derived_document;
if (!derived) throw new Error('缺少结构投影，请重新预览');
// acsm_id 映射为 UI id；名称、number、layout、custom_properties 全部取响应。
// sheet_count/subset_count 从完整响应集合计数，base 不可原位修改。
```

- [ ] 投影按 workspace/revision/命令快照/请求代次校验；结构加载时禁用依赖对象的新提交，失败保留输入与上一份结果并标为失效，不展示“已同步”。属性定义变更仍用既有元数据投影。
- [ ] 固化命令索引风险：结构动作后不再对其之前命令做跨边界去重压缩；旧草稿仍按原兼容逻辑恢复并验证。撤销、删除早期动作使新增 ID 消失时，后续失效参照必须阻断并可定位动作，不按编号/标题重绑、不丢弃后续动作。对不可执行响应不得使用残缺集合冒充完整投影。
- [ ] 同时覆盖持久草稿恢复与 `projectCommands` 兼容测试；若无需协议变化不能保持上述语义，记录具体反例并停在本任务评审，不扩展 schema 或自行生成 UUID5。恢复条件：明确获批的兼容方案及回归用例。
- [ ] 上述命令转绿后审查任务 1，再启动依赖它的表单任务。

### 任务 2：可信壳上下文、列偏好存储与文件夹入口

文件：新增 `application/shell_context.py`、`infrastructure/sheet_preferences.py`、`infrastructure/explorer.py`；修改 `interfaces/shell.py`、`interfaces/api.py`、`web/src/api/shell.ts`、`TopBar.vue`；新增 `tests/unit/test_sheet_preferences.py`、`tests/unit/test_shell_workspace.py`，保留 `test_shell.py`。

接口设计：`create_app` 增加仅 Python 内部可选回调 `on_workspace_opened`（默认 None，不改 HTTP）；成功打开后以服务端 Workspace 登记当前上下文。ShellBridge 接收该上下文与偏好仓库。以下新方法均检查预期 workspace_id 等于当前有效上下文，路径只从上下文取得：

```ts
type ShellResult<T> = {ok:true;value:T} | {ok:false;code:string;message:string};
interface SheetShellBridge {
  open_workspace_folder(workspace_id:string):Promise<ShellResult<null>>;
  load_sheet_columns(workspace_id:string):Promise<ShellResult<ColumnPreferences|null>>;
  save_sheet_columns(workspace_id:string,preferences:ColumnPreferences):Promise<ShellResult<null>>;
  clear_workspace_context(workspace_id:string):Promise<ShellResult<null>>;
}
```

Python 暴露同名方法并返回上述可序列化字典；这是新增桥接口，旧 select_file/on_files_dropped 不改返回类型。

- [ ] 写失败单测：未打开工作区、其他 workspace_id、关闭后调用、目录消失、空格/中文路径；传入路径或命令不能成为目标。fake Explorer 调用器只记录参数，测试不弹出窗口。
- [ ] 写偏好单测：两个 ID 隔离、同一 ID 重开、坏 JSON、只读数据目录、未知 schema、字段与数量限制；只读 load 不创建文件。断言临时工程目录文件及 mtime 不变。

```python
def test_preferences_read_does_not_create_directory(tmp_path):
    from dst_manager.infrastructure.sheet_preferences import SheetPreferences
    store = SheetPreferences(tmp_path / 'app-data')
    assert store.load('workspace-1') is None
    assert not (tmp_path / 'app-data').exists()
```

- [ ] 运行 `rtk proxy uv run pytest tests/unit/test_shell_workspace.py tests/unit/test_sheet_preferences.py tests/unit/test_shell.py -q`，先记录失败。
- [ ] 实现 `SheetPreferences(data_dir:Path)` 的 `load(workspace_id)->dict|None`、`save(workspace_id,preferences)->None`。将校验后的 schemaVersion=1 JSON 存入 `settings.data_dir/ui-preferences/sheets/<sha256(workspace_id)>.json`；临时文件同目录 + os.replace，串行写入与锁防止并发损坏，失败保留旧文件。
- [ ] Explorer 适配使用 Windows Shell API 的结构化目录/选中文件参数；优先选中当前 DST，无法选中时打开已验证目录。禁止 shell=True、cmd /c、拼接用户字符串；非 Windows 返回不支持。
- [ ] TopBar 图标具有名称“打开图纸集所在文件夹”；无壳禁用并解释。桥晚到更新状态；旧桥缺方法可降级。关闭成功清上下文，异步返回再次比较 workspace_id，防止旧窗口结果进入新工作区。
- [ ] 壳桥独立错误码用 `SHELL_WORKSPACE_UNAVAILABLE`、`SHELL_DIRECTORY_NOT_FOUND`、`SHELL_OPEN_FAILED`、`SHEET_PREFERENCES_INVALID`、`SHEET_PREFERENCES_IO`；不改 HTTP 错误码。
- [ ] 测试转绿，另在可用 Windows 桌面手动验证空格目录与实际选中 DST；不以 mock 代替系统集成证据。

### 任务 3：统一范围与单表导航

文件：新增 `useSheetsWorkspace.ts`、`SheetTree.vue`、`SheetToolbar.vue`；修改 `SheetsView.vue`、`SheetTable.vue`、App.vue；新增 `web/tests/e2e/fixtures/sheets.ts`、`sheets-navigation.spec.ts`。

消费任务 1 的 projection；产出 `scope`、`focusedSheetId`、`selectedIds`、`filteredRows`、`visibleRows`、`hiddenSelectedCount`。初始 scope 为 all；行 ID 取服务端 ID。

- [ ] 夹具导出 `installSheetsFixture(page:Page, options?:{sheetCount?:number;propertyCount?:number}):Promise<void>`：默认 5 子集/13 图纸/36 字段；路由复用既有响应字段，支持 161 张大列表、空集、无属性、长文本、双状态。只含虚构路径；fake 壳持有当前 ID 和独立偏好映射，持久草稿路由保持 expected_version 语义。
- [ ] 写失败行为测试：只有一个表；全部范围 13、子集 3；点击图纸定位不勾选；过滤隐藏目标提示；161 项首屏 80，全选选择 161；切范围保留集合、取消全选只取消当前匹配项。

```ts
import {test,expect} from '@playwright/test';
import {installSheetsFixture} from './fixtures/sheets';
test('单表初始范围',async({page})=>{
  await installSheetsFixture(page);
  await page.goto('/');
  await page.getByRole('button',{name:'选择 DST 文件'}).click();
  await expect(page.getByRole('table',{name:'图纸表格'})).toHaveCount(1);
  await expect(page.getByText('匹配 13 / 全部 13 张',{exact:true})).toBeVisible();
});
```

- [ ] 运行 `rtk proxy npm --prefix web run test:e2e -- sheets-navigation.spec.ts`，确认旧页面失败。
- [ ] 从 App.vue 移动范围/过滤/选择逻辑到 composable，在主标签之外实例化，移除 selectedId/subsetFilter 双真源。查询继续覆盖完整路径与隐藏属性；不依赖显示列。

```ts
const visibleRows = computed(()=>filteredRows.value.slice(0,renderLimit.value));
const hiddenSelectedCount = computed(()=>[...selectedIds.value]
  .filter(id=>!filteredRows.value.some(row=>row.sheet.id===id)).length);
```

- [ ] 主视图改为树与唯一 SheetTable；新增操作暂接任务 6 的入口，不保留旧第二表。选择条吸顶、树独立滚动；主表计数显示匹配/范围总数与已加载数。
- [ ] 转绿后迁移 main.spec.ts 中仅因 DOM 结构变化失效的选择器，保留原业务断言；确认属性/修订标签和任务浮层可达。

### 任务 4：可配置列与图纸集级恢复

文件：新增 `useSheetColumns.ts`、`ColumnSettings.vue`；修改 SheetTable、SheetToolbar、SheetsView；新增 `web/tests/e2e/sheets-columns.spec.ts`。

消费任务 2 的 load/save 桥和服务端字段定义。产出 `visibleColumns`、`preferences`、`newPropertyCount`、`saveError`、`reset():Promise<void>`。列配置不改变业务对象。

- [ ] 写失败测试：固定图号/标题/状态/操作不可关；文件名默认开、布局默认关、前三自定义属性开；两种 scope 分别记忆子集列。不同工作区不串，重开恢复，存储失败当前选择仍生效。

```ts
await page.getByRole('button',{name:'显示列'}).click();
await expect(page.getByRole('checkbox',{name:'图号 固定'})).toBeDisabled();
await page.getByRole('checkbox',{name:'布局',exact:true}).check();
await page.getByRole('button',{name:'关闭显示列'}).click();
await expect(page.getByRole('columnheader',{name:'布局',exact:true})).toBeVisible();
```

- [ ] 运行 `rtk proxy npm --prefix web run test:e2e -- sheets-columns.spec.ts`，确认失败。
- [ ] 实现以 `builtin:`/`sheet:` 区分列；删除字段只从可见配置列表移除，其偏好以墓碑保留，撤销恢复。新增字段默认 false 并提示；首次没有存储才应用前三项默认。保存按 ID 排队，切工作区时不覆盖新工作区。
- [ ] 表格固定选择、图号、操作列；标题最多两行，状态不逐字换行；可选列宽度不足仅内部滚动，不自动隐藏。完整文本可键盘聚焦查看；异常状态进入诊断并可复制原始路径。
- [ ] 转绿并确认 36 字段搜索、同名内置列、删除/恢复和失败回退。

### 任务 5：分页编辑缓冲与全局输入保护

文件：新增 `useSheetEditor.ts`、`SheetPropertyEditor.vue`、`UnsavedInputDialog.vue`；修改 SheetTable、SheetsView、App.vue 全局动作接线；新增 `web/tests/e2e/sheets-editing.spec.ts`。

唯一上下文为 null 或 sheet/rename/insert-sheet/insert-subset/bulk；保留 workspaceId、revisionId、projection stamp、objectId、original、values、errors。类型按联合分支定义，不用任意 any。`guard(next:()=>Promise<void>):Promise<void>` 使用任务 1 的 SubmitCommands；保存失败不能继续 next。

- [ ] 写失败测试：36 属性为 6 页，第一页修改图幅、第六页修改另一字段，搜索隐藏后仍提交两项；取消不污染 base；切标签恢复；错误摘要跳到第六页字段。

```ts
await page.getByRole('button',{name:'编辑属性'}).first().click();
await page.getByRole('textbox',{name:'属性 图幅',exact:true}).fill('A2');
await page.getByRole('tab',{name:'属性',exact:true}).click();
await page.getByRole('tab',{name:'图纸',exact:true}).click();
await expect(page.getByRole('textbox',{name:'属性 图幅',exact:true})).toHaveValue('A2');
```

- [ ] 运行 `rtk proxy npm --prefix web run test:e2e -- sheets-editing.spec.ts`；旧代码直接改对象/缺缓冲应失败。
- [ ] 用完整副本编辑，搜索/翻页只派生视图；提交 `createCommand.updateSheetProperties(id,{...values})`，不能只发当前页。后台错误保留原值、字段错误和焦点，未给字段路径的错误保留摘要，不编造字段归因。
- [ ] 三选一模态单独实现，复用公共可访问模态样式/焦点管理，不改现有 boolean 强确认协议。无改动直接继续；保存→等待草稿持久化与投影成功→继续；失败留下；放弃明确清空；Esc 等于留下。
- [ ] App.vue 的 showPreview/write、关闭、更换工作区、快捷键及删除入口均先接 guard；加入草稿后使旧 previewContext 失效。write 不能捕获旧 context 后在保存继续时执行，必须要求重新预览。切主标签不触发 guard、不销毁状态宿主。
- [ ] 外部刷新或对象消失保留失效缓冲供核对并禁止提交；只读值更新不能自动覆盖用户输入。草稿保存失败重试不重复加入同一命令批次。
- [ ] 转绿，补齐提交失败、DRAFT_CONFLICT、保存中切换、基准刷新与键盘焦点恢复。

### 任务 6：三类操作表单与参照位置映射

文件：新增 `commands.ts`、`SheetOperationForm.vue`；修改 `useSheetEditor.ts`、SheetsView、App.vue 模板选择/布局读取接线；新增 `web/tests/e2e/sheets-forms.spec.ts`。

消费 projection、SheetRef 与 SubmitCommands。产出 `resolveSheetOrdinal(workspace:Workspace, ref:SheetRef):number`、`resolveSubsetOrdinal(workspace:Workspace, subsetId:string):number`，失效参照抛可见错误，不回退为 1。

- [ ] 写失败用例：单子集预填/全部必须选择、变目标清参照、删除参照需重选、同 ID 顺序变化重新映射、空子集禁用新增、空集新子集 ordinal=1；基础与布局模板分离。
- [ ] 运行 `rtk proxy npm --prefix web run test:e2e -- sheets-forms.spec.ts`，先红。
- [ ] 实现映射核心，并在提交前固定当前 stamp；请求/基准变化拒绝提交旧索引。

```ts
const subset = workspace.sheet_set.subsets.find(s=>s.id===ref.subsetId);
const index = subset?.sheets.findIndex(s=>s.id===ref.sheetId) ?? -1;
if(index<0) throw new Error('参照图纸已失效，请重新选择');
const ordinal = index + 1;
// createCommand.insertSheet 使用 ordinal、ref.placement 和原 source 契约。
```

- [ ] rename 仅缓冲标题；insert-sheet 使用 target_subset_id/ordinal/placement/count/source；insert-subset 使用 ordinal/placement/title/initial_sheet_count/base_template_file/source。三类均原 command schema，不携带 UI ref 或演示 token。
- [ ] 复用现有 selectTemplateFile/selectSubsetTemplateFile/selectBaseTemplateFile 和 layout-names 错误回退；给异步读取增加上下文代次，取消/切表单/切版本后的旧布局响应不回填。已有布局来源不额外要求用户文件/布局。
- [ ] 表单置于主表上方，一次一种，长表单内部滚动，取消入口可达；成功等待权威投影后定位，原筛选保留并提示目标隐藏；失败原输入保留。新增 ID 从派生结果取得，不从计数拼造。
- [ ] 转绿，重跑既有模板默认、Model 排除、人工布局回退与双版本选择 E2E。

### 任务 7：批量、删除及草稿动作联动

文件：修改 SheetOperationForm、useSheetEditor、useSheetsWorkspace、App.vue 草稿提交边界；新增 `web/tests/e2e/sheets-drafts.spec.ts`。

消费完整 selectedIds、任务 1 投影、既有 createCommand/addCommandBatch；不新增批量后端命令。SubmitCommands 应返回明确成功/失败，等待原 draftSaveQueue，不以入队即宣称持久保存成功。

- [ ] 写失败用例：跨范围两张批量只改指定字段并保留其他字段；设置空输入不生成命令；显式清空确认数量；单删移除并取消勾选；撤销恢复但不恢复勾选；整子集强确认字段不变。

```ts
await page.getByRole('button',{name:'删除',exact:true}).first().click();
await page.getByRole('button',{name:'加入删除草稿',exact:true}).click();
await expect(page.getByText('匹配 12 / 全部 12 张',{exact:true})).toBeVisible();
await page.getByRole('button',{name:'撤销',exact:true}).click();
await expect(page.getByText('匹配 13 / 全部 13 张',{exact:true})).toBeVisible();
```

- [ ] 运行 `rtk proxy npm --prefix web run test:e2e -- sheets-drafts.spec.ts`，先红。
- [ ] bulk 遍历完整选择 ID，逐张复制 custom_properties 后仅改指定名称；clear 明确设空字符串且仍经服务端校验，set 空串只提示不提交。提交摘要含完整数量/跨子集信息。
- [ ] 删除不再依赖旧 selected 子集变量；单删取 row.id，整子集取编辑上下文 ID。先处理缓冲再确认；整子集仍需 confirm_delete_all_sheets/confirm_delete_main_dwg、影响 DWG 及外部引用声明。
- [ ] 删除投影移除、选择修剪、toast、草稿动作栈与撤销/重做联动；已删除对象不进入批量。失败不显示正式删除成功；属性定义与结构变更分批门禁保持。
- [ ] 转绿并重跑草稿持久化、冲突恢复、移除中间动作、预览失效、NEEDS_REVIEW、修复/恢复中禁用等既有回归。

### 任务 8：视觉、可访问性、回归与交付

文件：完善组件 scoped 样式、必要的 `web/src/style.css`；新增 `web/tests/e2e/sheets-layout.spec.ts`；更新 main.spec.ts 选择器、docs/dst-manager/README.md、changelog.md、本计划实际验证。

- [ ] 写视口失败断言：1024×768、1120×768、1440×900、900×768 × 浅/深主题；默认、行编辑、三类表单、浮层展开和长列状态。900px 树抽屉可键盘开关并回焦，不与任务浮层同时锁焦。

```ts
await page.setViewportSize({width:900,height:768});
await expect(page.getByRole('button',{name:'打开图纸导航'})).toBeVisible();
expect(await page.evaluate(()=>document.documentElement.scrollWidth))
  .toBeLessThanOrEqual(900);
```

- [ ] 运行 `rtk proxy npm --prefix web run test:e2e -- sheets-layout.spec.ts`；使用既有语义令牌修正问题。按规范实现树方向键、表格可访问名称、展开 aria-expanded、错误焦点、完整文本读取、减少动画与对比度。
- [ ] 确认只剩一张业务表；搜索栏、选择条、固定列、ActionDock 不重叠；展开编辑页脚始终可滚动到达。截图仅作为视觉证据，不替代行为断言。
- [ ] 完整执行以下命令，记录实际数量、退出码与跳过原因；新增测试不可全靠 mock 确认真实命令映射，任务 1 的 Python 集成证据必须同时通过。

```powershell
rtk proxy uv run ruff check .
rtk proxy uv run pytest tests/unit/test_shell.py tests/unit/test_shell_workspace.py tests/unit/test_sheet_preferences.py tests/unit/test_sheet_projection_contract.py tests/unit/test_drafts.py tests/unit/test_v021_editing.py tests/unit/test_contracts.py -q
rtk proxy npm --prefix web run build
rtk proxy npm --prefix web run test:e2e
rtk git diff --check
```

- [ ] 不涉及 CAD/发布器实现时不要求为本次 UI 自动启动真实 CAD；有显式授权和环境时仅用样本副本做桌面人工验收。无环境记录未执行，不写“完整系统验收通过”。
- [ ] 更新文档导航、changelog 与本节实际验证；只有 S-01～S-12 全部有对应证据、关键风险关闭后才将计划置 `completed`。保留 SPEC accepted；属性页不随之升级状态。

## 5. 顺序与审查节点

任务 1 为先行数据门禁；任务 2 可与任务 1 独立推进，但 shell.py/api.py 与打包计划必须串行合并。任务 3 依赖 1；任务 4 依赖 2、3；任务 5 依赖 1、3；任务 6、7 依赖 5；任务 8 汇总全部。

每任务红绿后独立审查。建议三个用户可验证节点：任务 3+4 的单表与列配置；任务 5 的缓冲/分页/错误保护；任务 6+7 的真实草稿闭环。发现必须新增业务 API、改变命名/ID 契约或修改发布事务时暂停该节点评审，不扩大本计划权限。

## 6. 规范覆盖与完成标准

| SPEC 验收 | 任务与证据 |
| --- | --- |
| S-01、S-02 | 3：单表、统一 scope、隐藏定位；8：滚动布局 |
| S-03 | 3、7：161 项全选、跨范围批量 |
| S-04 | 2、4：偏好持久化、固定列、诊断完整路径复制 |
| S-05 | 5、6、7：缓冲、失败、取消、唯一上下文 |
| S-06 | 1、6、7、8：命令/模板/删除/发布既有回归 |
| S-07 | 8：四尺寸双主题及三种操作状态截图 |
| S-08 | 8：生产构建、Playwright、Ruff、pytest |
| S-09 | 2：可信当前上下文、无壳降级、路径拒绝、系统调用 |
| S-10 | 1、6：投影稳定身份、参照重校验、首个子集 |
| S-11 | 5、7：36 字段跨页/搜索、错误跳转、显式清空 |
| S-12 | 1、4、7：删除投影、反馈、撤销、窄屏不丢列 |

退出条件：以上全部通过；旧草稿/模板/修复/恢复/发布门禁无回归；列偏好不触碰工程；未引入前端命名算法；遗留风险有明确证据且无阻断项。Demo 仅作为设计参考保留，不发布为产品入口。

## 7. 实际验证与状态记录

2026-09-04：完成计划编写与规范对照，状态 `proposed`。产品代码实施、上述新增测试与产品视觉验收尚未执行；不得引用 Demo 测试结果替代本计划验收。

本次文档变更检查：`git diff --check` 通过；现有 `tests/unit/test_shell.py` 与 `tests/unit/test_drafts.py` 共 37 项通过（Alembic 既有弃用警告）。全量 Ruff 当次未通过：其他工作区文件 `runtime.py:25` 的 B009 与 `test_runtime.py:58` 的 I001/F401，未修改这些文件。此结果不等同于实施完成，也不解除实施阶段的全量检查要求。

2026-09-05：任务 1–8 全部实施完成。任务 8 按简报 verbatim 执行以下验证，实际输出如下（完整记录见 [任务 8 报告](../../../.superpowers/sdd/PLAN-DM-015-sheets-workspace-ui/task-8-report.md)）：

| 命令 | 实际结果 | 说明 |
| --- | --- | --- |
| `rtk proxy uv run ruff check .` | All checks passed（退出码 0） | 全量，无遗留 |
| `rtk proxy uv run pytest <简报 8 个文件> -q` | **138 passed**（退出码 0，约 3.3s） | 含任务 1 的 `test_sheet_projection_contract.py` 4 项 Python 集成证据 |
| `rtk proxy npm --prefix web run build` | 零错误（check:api + vue-tsc + vite，914ms） | 生产构建 |
| `rtk proxy npm --prefix web run test:e2e` | **串行 146/146 通过**；并行默认下 2 项既有时序敏感用例（300 行性能预算、壳桥延迟注入/文件夹禁用等）高负载偶发超时，单独重跑与串行全绿 | 137 既有 + 任务 8 新增 9 项 sheets-layout |
| `rtk git diff --check` | 通过 | 无空白错误 |

S-01～S-12 证据核对（自动化证据来源）：
- S-01（单表/树顶部/两类新增表单不常驻）：sheets-navigation「单表初始范围」+ sheets-layout「只剩一张业务表」。
- S-02（树/搜索/筛选共用范围、隐藏定位显式反馈）：sheets-navigation「点击子集切换范围」「筛选排除目标」「低频筛选展开与条件标签」。
- S-03（全选覆盖未加载、跨范围批量对象数一致）：sheets-navigation「161 项首屏 80 与全选覆盖未加载」+ sheets-drafts「跨范围两张批量」。
- S-04（短列不换行、固定列不可隐藏、偏好逐图纸集恢复、诊断路径与后端原值一致且可复制）：sheets-columns 系列 + TaskOverlay 诊断复制（S-04）。
- S-05（单行/批量/新增/子集编辑成功失败取消与未提交保护）：sheets-editing、sheets-forms、sheets-drafts。
- S-06（新增来源、整子集删除、草稿恢复及全部发布门禁无回归）：main.spec + sheets-forms + sheets-drafts + sheets-projection。
- S-07（四尺寸双主题截图、浮层/行编辑/新增态可达）：任务 8 sheets-layout 截图测试产出 4 尺寸 × 浅深默认态截图与 1440×900 浅深行编辑/编辑子集/浮层展开截图（Playwright test-results 附件，仅作视觉证据），各态行为断言（可达、无横向溢出、页脚可滚动）同时通过。截图人工逐张目检待用户执行。
- S-08（Playwright 回归 + 生产构建 + Ruff/pytest）：上表命令全部通过。
- S-09（打开所在文件夹仅用当前 DST 目录，覆盖无壳/无工作区/目录缺失/空格中文路径/任意路径命令拒绝）：`test_shell_workspace.py`（20 项）+ `test_shell.py` + `sheets-folder.spec.ts`（4 项）。真实 Windows 桌面人工验收（空格/中文目录实际打开并选中 DST）待用户执行，不以 mock 代替系统集成证据。
- S-10（参照对象与前后位置映射，覆盖目标变化/参照删除/序号变化/首个子集）：sheets-forms 系列 + `test_sheet_projection_contract.py`。
- S-11（多页属性编辑、搜索隐藏修改、跨页错误定位不丢数据；批量空输入不误清空、显式清空走原门禁）：sheets-editing + sheets-drafts。
- S-12（删除仅入草稿、投影移除、反馈、撤销、未提交编辑保护；已配置列不因窄屏消失）：sheets-navigation/sheets-drafts + sheets-layout「长列状态」与 900px 抽屉（树收起为抽屉但表格与列配置保留）。

状态判定：S-01～S-12 均有自动化证据且无阻断风险，但 S-09 的真实桌面人工验收与 S-07 截图人工目检尚未由用户在真实 Windows 桌面执行，属关键待验收项；SPEC-DM-009 保持 `accepted`，属性页 SPEC-DM-010 不随本计划升级状态（保持 `review`）。因此本计划状态维持 `active`，不标记 `completed`。

2026-09-05 整改补充：针对实施评审发现的可见偏差，已修复文件夹入口、顶栏对象名称、导航长文本/宽度/默认展开、主表 basename、工作区高度、关键表格列宽与 900px 底部操作遮挡。浏览器同视口设计 QA 已将 Demo 与实现的 1440×900 全景及聚焦区域放入同一比较输入，响应式另核对 900×768 深色态；结果记录于仓库根目录 `design-qa.md`，`final result: passed`。验证更新为生产构建通过、Playwright E2E 153/153、Ruff 通过、相关 Python 测试 51/51。S-07 本轮视觉偏差已关闭；S-09 真实 Windows Explorer 选中 DST 仍待人工验收，计划继续保持 `active`。

2026-09-05 视觉复验更正：用户在真实桌面继续检查编辑子集、新增图纸、新建子集、浅深主题、导航拖拽和任务浮层展开状态后，确认前述 `design-qa.md` 的通过范围不足，不能代表 S-07 已关闭。具体缺口为操作表单未形成独立编辑卡片、输入/下拉仍受原生与全局样式影响、表格背景/分隔线与 hover/选中态缺失、树宽变化后 sticky 列重叠，以及宽屏任务浮层挤压主内容。SPEC-DM-006 与 SPEC-DM-009 已补充约束，整改由 [PLAN-DM-017](PLAN-DM-017-sheets-visual-convergence.md) 承接；本计划继续保持 `active`，S-07 恢复为待验收。

2026-09-05 补充：SPEC-DM-010 的接受发生于任务 8 之后（用户并行完成其规范接受，规范 frontmatter 与文档入口均已更新为 `accepted`，实施计划为 PLAN-DM-016）；上句「保持 `review`」为任务 8 收尾时的状态快照，本计划不改写历史记录。

2026-09-05 最终审查与修复：整分支最终审查（db2980e..90646a1）判定 With fixes，2 项 Important 已修复并经局部复审确认（commit 95aa2ca）：①`submitCommands` 去重未检查撤销/重做光标，撤销后重新提交相同命令批次被静默吞掉——已加光标守卫并补先红后绿 e2e；②`docs/dst-manager/README.md` 中 SPEC-DM-010 状态自相矛盾——已更正。顺手删除编辑上下文未消费的 `stamp` 字段（陈旧注释更正见 b75b632）。修复后全量 e2e 串行 **147/147**、生产构建零错误。最终审查同时确认：任务 1 混合批次显示缺口、任务 3 行编辑/按钮可见性/首子集误触、任务 4 操作列延迟、任务 5 死代码、任务 6 遗留指针（含子集标题缓冲纳入 guard）等历史挂起项均已在此前任务中解决。

已知挂起项（均为 Minor，不阻断，后续计划可择机处理）：
- `STRUCTURAL_TYPES` 在 `web/src/drafts.ts` 与 `useSheetProjection.ts` 重复定义，宜上提至 `features/sheets/types.ts`。
- 操作表单 `dirty` 标记为粘性（取消参照选择后仍提示未保存）；同类按钮点击先触发 guard 再 no-op。
- `useSheetColumns` 存储加载与用户切换存在窄窗口竞态；`saveError` 成功后不清除；有偏好的工作区默认值闪现一帧。
- 投影重建与刷新完成间显示短暂回退本地投影（flicker）；`commandKey` 为非规范化 JSON 比较。
- 结构投影失败时显示降级为本地投影（无数据损失，错误已提示）；含未加载行的批量路径与 guard 竞态修复缺独立确定性 e2e。
- 编辑器渲染于表格上方而非 SPEC 字面的"该行下展开"；提交失败焦点移至摘要；App.vue 约 600 行（计划既定超限）。
- Python 侧：`SheetPreferences._validate` 不拒未知顶层字段、`open_workspace_folder` 理论 TOCTOU、`load` 未加锁。
- 任务 8：长列状态矩阵 2 尺寸×2 主题（非全 4×2）、对比度冒烟取样，均已如实记录。

2026-09-05 PLAN-DM-017 实施补充：令牌、双卡片、表单、表格几何与交互、任务覆盖抽屉已落地；已保存19张虚构实现截图。当前结果与证据见[设计 QA](../../../design-qa.md)及 [PLAN-DM-017](../../../.planning/plans/dst-manager/PLAN-DM-017-sheets-visual-convergence.md)。本地 Demo 被浏览器 URL 安全策略拒绝，缺少其他主题/状态匹配参考，S-07 仍待同状态验收；S-09 真实 Explorer 仍待人工验收，计划保持 active。

2026-09-05 最终视觉验收：用户在真实桌面完成连续复验与反馈闭环后，明确确认 PLAN-DM-017 可标记为 `completed`，因此 S-07 通过。S-09 的真实 Windows Explorer 打开正确目录并选中当前 DST 仍待人工验收，本计划继续保持 `active`。
