<script setup lang="ts">
import {computed,ref,watch} from "vue";
import {useI18n} from "vue-i18n";
import {lastErrorDiagnostic,localizedError} from "./api/client";
import {useExtensions} from "./composables/useExtensions";
import type {BeforeExtensionListReplace,ExtensionsPanel} from "./composables/useExtensions";
import {EXTENSION_PAGE_COMPONENTS,isExtensionRouteKey,type ExtensionRouteKey} from "./features/extensions/pageRegistry";
import {createCommand} from "./api/contracts";
import type {DraftEnvelope,ExtensionSummary,Job,Preview,PropertyDefinition,Revision,Sheet,Subset,Workspace} from "./api/contracts";
import type {PropertyKey, PropertySearchMode, ValueKey} from "./features/properties/types";
import type {DefinitionScopeFilter} from "./features/properties/model";
import {useShellNavigation} from "./composables/useShellNavigation";
import {useDraftGuards} from "./composables/useDraftGuards";
import {useWorkspaceLifecycle} from "./composables/useWorkspaceLifecycle";
import {useWorkspaceCommands,type PreviewContext} from "./composables/useWorkspaceCommands";
import {useJobMonitor} from "./composables/useJobMonitor";
import {useCsvImport} from "./composables/useCsvImport";
import {useRepair} from "./composables/useRepair";
import {useRestore} from "./composables/useRestore";
import {useSheetProjection} from "./composables/useSheetProjection";
import {useApplicationPreferences} from "./composables/useApplicationPreferences";
import {useSheetsWorkspace} from "./composables/useSheetsWorkspace";
import type {SheetDiagFilter, SheetPathFilter, SheetPendingFilter} from "./composables/useSheetsWorkspace";
import {useSheetColumns} from "./composables/useSheetColumns";
import {useSheetEditor} from "./composables/useSheetEditor";
import {usePropertiesWorkspace} from "./composables/usePropertiesWorkspace";
import {guardSheetCatalogPage,sheetCatalogNavigationNeeded} from "./composables/useSheetCatalog";
import type {OperationKind} from "./components/sheets/SheetToolbar.vue";
import UnsavedInputDialog from "./components/ui/UnsavedInputDialog.vue";
import {useConfirm} from "./composables/useConfirm";
import {useToast} from "./composables/useToast";
import ConfirmModal from "./components/ui/ConfirmModal.vue";
import ToastHost from "./components/ui/ToastHost.vue";
import SettingsDialog from "./components/settings/SettingsDialog.vue";
import TopBar from "./layout/TopBar.vue";
import TabBar from "./layout/TabBar.vue";
import ActionDock from "./layout/ActionDock.vue";
import TaskOverlay from "./layout/TaskOverlay.vue";
import WorkspaceShell from "./layout/WorkspaceShell.vue";
import WelcomeView from "./views/WelcomeView.vue";
import StandardsView from "./views/StandardsView.vue";
import CreateSheetSetView from "./views/CreateSheetSetView.vue";
import SheetsView from "./views/SheetsView.vue";
import PropertiesView from "./views/PropertiesView.vue";
import RevisionsView from "./views/RevisionsView.vue";

import {useStartNavigation} from "./composables/useStartNavigation";
import type {StandardsEntryIntent} from "./composables/useStartNavigation";

const {t}=useI18n();
// 应用级起始面（PLAN-DM-035 Task 7）：无工作区时欢迎页/标准管理/创建图纸集切换。
// 标准管理是应用级页面，不进工作区标签栏；工作区关闭后回到欢迎页
//（回欢迎页的 watch 在 workspace 声明之后注册，见下方同名注释块）。
const startNavigation=useStartNavigation();
const standardsEntryIntent=computed<StandardsEntryIntent>(()=>startNavigation.standardsEntryIntent.value);
const {state:confirmState,confirmAction,resolve:resolveConfirm}=useConfirm();
const workspace=ref<Workspace|null>(null);
watch(()=>workspace.value,(value)=>{if(value===null)startNavigation.goWelcome();});
const baseWorkspace=ref<Workspace|null>(null);
const error=ref("");
const preview=ref<Preview|null>(null);
const previewContext=ref<PreviewContext|null>(null);
// 预览请求进行中（Task 5 ActionDock 门禁：仅作按钮 loading 呈现，不阻止再次发起——竞态由 previewGeneration 丢弃乱序响应）
const isPreviewing=ref(false);
const isWorkspaceLoading=ref(false);
const isRestoreExecuting=ref(false);
// 非模态任务通知（SPEC-DM-006 §6.6）：toast 状态/推送/关闭；"查看"跳转（jumpOverlay）复用浮层的唯一自动展开入口
// —— 草稿栈与未提交输入门禁（Task 11 第 11c 轮：抽出 useDraftGuards）——
// 草稿栈状态与三选一 guard 已迁入组合式函数；此处解构回同名局部变量，模板与其余接线不变。
// 位置要求：`commands` 是 useSheetsWorkspace/useSheetEditor/useSheetProjection 的**直接实参**
// （setup 期求值），故本调用必须早于它们；而本方依赖的 `editor`/`properties`/`sheets`/`active`
// 在下面才创建，`refreshSheetProjection` 也晚于本处，故一律以**懒取值函数/闭包**传入，
// 只在动作被调用时才解引用（见 useDraftGuards 头部说明）。
// 生命周期域容器：草稿域在 setup 期就需要一个可调用的 `reloadWorkspace` 引用，而生命周期模块又依赖
// 草稿域的返回值 ⇒ 提前声明容器、只在动作被调用时解引用（避免 setup 期循环依赖与声明顺序耦合）。
let lifecycle:ReturnType<typeof useWorkspaceLifecycle>;
const draftGuards=useDraftGuards({
  workspace,baseWorkspace,error,t,cloneJson,invalidatePreview,
  refreshSheetProjection:()=>refreshSheetProjection(),
  getActive:()=>active.value,
  getEditor:()=>editor,
  getProperties:()=>properties,
  getSheets:()=>sheets,
  reloadWorkspace:(workspaceId)=>lifecycle.doRefreshWorkspace(workspaceId),
  confirmAction,
});
const {
  commands, draftActions, draftCursor, draftVersion, draftStale, draftStaleReasons, draftCorrupted,
  draftSaveFailed, lastDraftError, draftSaving, draftRecovered,
  hasPropertyDefinitionCommands, hasStructuralCommands,
  resetDraftState, rebuildDraftProjection, scheduleDraftSave, clearCommands, clearDraftRestart,
  undoDraft, redoDraft, removeDraftAction, discardDraft, reloadAfterDraftConflict,
  addCommand, addCommandBatch,
  runScopeChange, guardedFilter, guardAllInputs, resolveSharedGuard, sharedGuardState, pendingDraftSave,
}=draftGuards;
// —— 工作区生命周期域（Task 11 第 11d 轮：抽出 useWorkspaceLifecycle）——
// 打开/关闭/刷新/清空编辑态与壳桥接（选择 DST、拖拽接收、打开所在文件夹）已迁入组合式函数；
// 此处解构回同名局部变量，模板与其余接线不变（因此 `<template>` 一行未改）。
// 位置要求：`refreshWorkspace`/`workspaceLoadGeneration` 是 useCsvImport/useRepair/useRestore 的
// **直接实参**（setup 期求值），故本调用必须早于它们；而本方依赖的 `invalidateJobMonitor`/`editor`/
// `sheets`/`active`/`settingsOpen` 等更晚创建，`layoutReadGeneration` 还是会被重赋的 `let`（不能靠
// 解构或直接引用拿到），故一律以**懒取值函数/回调**传入，只在动作被调用时才解引用
// （见 useWorkspaceLifecycle 头部说明）。
lifecycle=useWorkspaceLifecycle({
  workspace,baseWorkspace,error,isWorkspaceLoading,isRestoreExecuting,
  draft:draftGuards,
  cloneJson,invalidatePreview,t,confirmAction,
  invalidateLayoutReads:()=>{layoutReadGeneration+=1},
  resetSheetsWorkspace:()=>resetSheetsWorkspace(),
  reloadExtensions:()=>reloadExtensions(),
  clearExtensions:()=>clearExtensions(),
  loadRevisions:()=>loadRevisions(),
  invalidateRevisionState:()=>invalidateRevisionState(),
  invalidateJobMonitor:(force)=>invalidateJobMonitor(force),
  resetOverlay:()=>resetOverlay(),
  resetEditor:()=>editor.reset(),
  invalidateCsvPreview:(clearFile)=>invalidateCsvPreview(clearFile),
  isSettingsOpen:()=>settingsOpen.value,
  getActive:()=>active.value,
});
const {workspaceLoadGeneration,hasShell,openByPath,closeWorkspace,refreshWorkspace,openFolder,selectAndOpenDst}=lifecycle;
const {toasts,pushToast,dismiss}=useToast();
// 设置中心（PLAN-DM-019 任务 10/11）：入口在 TopBar 齿轮；toast 复用宿主 useToast
const settingsOpen=ref(false);
// 任务监控域（Task 3 拆分）：Job 订阅/轮询/重试与代次失效；job 为单一 ref，供 execute/CSV/修复/恢复写入
const {job,connectionMode,watchJob,retryJob,invalidateJobMonitor,terminal,isCurrentJobGeneration}=useJobMonitor({
  isWorkspaceLoading,workspace,
  onJobSucceeded:async(workspaceId:string)=>{await discardDraft();await refreshWorkspace(workspaceId)},
  error,
  pushToast,
  shouldSuppress:()=>overlayOpen.value&&overlayTab.value==="prog",
});
// job 为 useJobMonitor 单一 ref：CSV 导入/修复/恢复域经 setJob 写入；任何任务响应（排队或已终态）均展开到实施进度页签——用户刚发起动作任务必须可见，已展开时幂等不重复弹（fix round 1：restore 同步直返终态时不再静默）
const setJob=(j:Job)=>{job.value=j;openOverlay("prog")};
// 自定义属性 CSV 导入域（Task 3 拆分）
const {csvText,csvPreview,csvPreviewContext,readCsvFile,previewCsv,importCsv,invalidateCsvPreview}=useCsvImport({
  workspace,isWorkspaceLoading,watchJob,setJob,refreshWorkspace,invalidateJobMonitor,isCurrentJobGeneration,error,confirmAction,
  hasConflictingDraft:()=>hasPropertyDefinitionCommands.value,
});
// 内存修复域（Task 3 拆分）：修复预览/独立修订发布与写入门禁；isRestoreExecuting 为 App.vue 单一 ref 注入
const {repairPreview,repairContext,isRepairPreviewing,isRepairExecuting,previewRepair,executeRepair,repairWritesDisabled,dstValidation}=useRepair({
  workspace,isWorkspaceLoading,isRestoreExecuting,refreshWorkspace,setJob,invalidateJobMonitor,isCurrentJobGeneration,workspaceLoadGeneration,error,confirmAction,
});
// 修订恢复域（Task 3 拆分）：isRestoreExecuting 复用 App.vue 单一 ref，useRestore 返回同一 ref 保持单一事实来源
const {revisions,restorePreview,restorePreviewContext,loadRevisions,loadRevisionsInternal,previewRestore,restoreRevision,invalidateRevisionState}=useRestore({
  workspace,isWorkspaceLoading,refreshWorkspace,setJob,invalidateJobMonitor,isCurrentJobGeneration,workspaceLoadGeneration,isRestoreExecuting,error,confirmAction,
});
const {cadVersion}=useApplicationPreferences();
// 结构投影域（Task 1）：内部 /changes/preview 获取权威结构显示，与显式发布预览分离。
// 只读 projection 由 watch 应用到显示 workspace；pending/error 供后续任务消费。
const {projection:sheetProjection,refresh:refreshSheetProjection}=useSheetProjection({workspace,baseWorkspace,commands,cadVersion});
watch(sheetProjection,(value)=>{if(value)workspace.value=value});
// —— 扩展页面贡献（PLAN-DM-020 Task 10）：App 只装配列表与挂载组件，不承载目录业务状态 ——
// 扩展清单是应用级状态（不属于任何工作区），标签栏装配与设置中心扩展分区共用一份数据源
const {extensions,loading:extensionsLoading,failed:extensionsFailed,reload:reloadExtensions,setEnabled:setExtensionEnabled,clear:clearExtensions}=useExtensions();
// 打开设置即刷新扩展清单：扩展分区因此不依赖工作区加载，
// “手头没打开 DST”的卡死用户也能在这里恢复被停用的扩展
//（紧邻 reloadExtensions 定义，避免在 setup 期引用未初始化的 const）
function openSettings(){settingsOpen.value=true;void guardedReloadExtensions()}
// PLAN-DM-024 F1：扩展列表替换的草稿生命周期闸门（在 App 装配，草稿语义不进 useExtensions）。
// 比较前后 workspace_page route 集合：仅当当前活动扩展页会从候选页面集合消失时征询
// guardSheetCatalogPage 三选一；守卫结果为 continue 才允许替换。列表替换本身由 reload
// 协议在本回调返回 true 后提交——guard 的 next 后续动作在此不双写列表。
async function guardExtensionListReplace(previous:readonly ExtensionSummary[],next:readonly ExtensionSummary[]):Promise<boolean>{
  const contributionRoutes=(list:readonly ExtensionSummary[])=>{
    const routes=new Set<string>();
    for(const ext of list){
      if(ext.status!=="AVAILABLE")continue;
      for(const contribution of ext.ui_contributions??[]){
        if(contribution.kind==="workspace_page")routes.add(contribution.route_key);
      }
    }
    return routes;
  };
  const currentRoute=active.value;
  // 活动页不是扩展页直接放行；活动扩展页不在刷新前候选集合中亦无从"消失"（防御）
  if(!isExtensionRouteKey(currentRoute)||!contributionRoutes(previous).has(currentRoute))return true;
  // 活动扩展页刷新后仍在候选集合中：直接通过，不打扰用户
  if(contributionRoutes(next).has(currentRoute))return true;
  const result=await guardSheetCatalogPage(()=>{});
  return result==="continue";
}
// 设置中心触发的刷新统一走闸门回调（打开设置与扩展分区"重试"共用）
function guardedReloadExtensions(){return reloadExtensions(guardExtensionListReplace)}
// 只挂载已加载（AVAILABLE）扩展声明的 workspace_page 贡献，且 route_key 必须命中
// 编译期映射；未知 route_key 与非 workspace_page 贡献安全忽略，后端值绝不成为
// 动态 import 路径（ARCH-DM-006 §7）
const extensionPages=computed(()=>{
  const pages:{routeKey:ExtensionRouteKey;summary:ExtensionSummary}[]=[];
  for(const ext of extensions.value){
    if(ext.status!=="AVAILABLE")continue;
    for(const contribution of ext.ui_contributions??[]){
      if(contribution.kind!=="workspace_page"||!isExtensionRouteKey(contribution.route_key))continue;
      // 同一 route_key 只取首个声明（编译期映射键唯一，重复声明不产生重复标签）
      if(!pages.some(page=>page.routeKey===contribution.route_key))pages.push({routeKey:contribution.route_key,summary:ext});
    }
  }
  return pages;
});
// 壳层导航（页签 + 任务浮层）已抽出（Task 11 Step 4 上半 / 第 11b 轮）：页签 active/select/onKeydown
// 由既有 `useShellTabs` **组合**而来（本模块不重新实现页签状态，也不注册快捷键）；浮层的 open/tab 与
// 唯一自动展开入口 openOverlay 同样归它持有。
// 解构回同名局部变量 ⇒ 本文件其余代码与 `<template>` 一行都不用改。注意上方若干闭包（如 useJobMonitor
// 的 shouldSuppress、setJob）引用了 overlayOpen/openOverlay，它们都在本模块初始化**之后**才被调用，
// 因此不存在“先用后定义”的求值顺序问题。
const {tabDescriptors,active,overlayOpen,overlayTab,openOverlay,resetOverlay,jumpOverlay,selectTab,onTabKeydown}=useShellNavigation({
  workspace,
  extensionPages,
  isRestoreExecuting,
  isWorkspaceLoading,
  t,
  loadRevisions,
  catalogNavigationNeeded:sheetCatalogNavigationNeeded,
  guardCatalogPage:guardSheetCatalogPage,
});
// 停用/启用扩展（本次修复：入口唯一在设置中心，扩展页面不再提供停用；否则停用会移除
// 页面入口本身，开关变成单向、用户被永久卡死）。启用不移除任何入口，直接落库；
// 停用可能移除当前目录页并丢弃页内草稿，必须先过全局未保存输入三选一闸门
//（与切换页签/关闭工作区同一闸门）。SPEC-DM-011「启停交互改进」修订起两个闸门模态都是原生 <dialog>，
// 会自行叠在仍在打开的设置对话框之上，故停用流程不再需要先关闭设置窗口。失败向上
// 抛出，由设置对话框就地行内呈现。
async function toggleExtensionFromSettings(extensionId:string,enabled:boolean){
  if(enabled){await setExtensionEnabled(extensionId,true);return}
  await guardAllInputs(()=>setExtensionEnabled(extensionId,false));
}
// SPEC-DM-011「启停交互改进」修订起不再做「焦点归还被移除标签的邻近标签」：停用发生在设置对话框打开期间，
// 对话框是 top layer 模态、标签栏处于 inert，对 inert 元素调 focus() 是空操作（写了也
// 无效的死代码）。焦点应收敛在对话框内部，由 SettingsDialog 在启停结束后归还到同一开关。
// 设置中心扩展分区视图模型：列表状态来自 useExtensions，toggle 必须走上方的闸门编排
//（设置分区自己调端点会绕过闸门直接丢草稿）
const extensionsPanel=computed<ExtensionsPanel>(()=>({
  list:extensions.value,loading:extensionsLoading.value,failed:extensionsFailed.value,
  reload:guardedReloadExtensions,toggle:toggleExtensionFromSettings,
}));
const sheetSetName=computed(()=>workspace.value?.sheet_set.name??"");
const dstPath=computed(()=>workspace.value?.dst_path??"");
const dstStatus=computed(()=>workspace.value?.dst_validation?.status??"");
// 恢复预览成功（restorePreview 已写入）后展开任务浮层到修改预览页签，与 showPreview 共用 §9.1 统一预览门禁呈现
async function previewRestoreAndOpen(revision:Revision){await previewRestore(revision);if(restorePreview.value)openOverlay("prev")}
// 图纸页工作区状态（PLAN-DM-015 任务 3）：范围/搜索/低频筛选/勾选集合/首屏加载。
// 在主标签之外实例化，切换主标签保留勾选集合与筛选；行 ID 取服务端 ID。
const sheets=useSheetsWorkspace({workspace,commands});
const {
  scope,focusedSheetId,selectedIds,searchText,searchAll,filtersVisible,
  pathFilter,diagnosticFilter,pendingFilter,renderLimit,
  filteredRows,visibleRows,hiddenSelectedCount,allFilteredSelected,
  hiddenTarget,pruneMessage,scopeTotal,allTotal,rangeTotal,
  pendingSheetIds,diagnosticObjectIds,allRows,
}=sheets;
const {selectAll:sheetsSelectAll,selectSubset:sheetsSelectSubset,locateSheet,toggleSheet,toggleFilteredSelection,clearSelection,clearFilters,reset:resetSheetsWorkspace,snapshotState:sheetsSnapshotState,restoreState:sheetsRestoreState}=sheets;
// 显示列配置（PLAN-DM-015 任务 4）：按图纸集记忆，依赖工作区与当前范围（子集列两种范围分别记忆）
const {visibleColumns,columnOptions,newPropertyCount,saveError:columnSaveError,setBuiltin,setProperty,reset:resetColumns}=useSheetColumns({workspace,scope:sheets.scope});
// 新增操作入口（任务 6 接真实表单）：三类操作表单共用一个唯一编辑上下文，一次只出现一种。
// 单子集范围预填目标子集，全部图纸范围必须明确选择（不使用隐含的上次子集）。
function openOperation(kind:OperationKind){
  // 同一表单已打开：不重开（先于 guard，避免无谓三选一提示后再空操作）
  if(editor.context.value?.kind===kind)return;
  void editor.guard(()=>doOpenOperation(kind));
}
function doOpenOperation(kind:OperationKind){
  if(!workspace.value)return;
  const targetId=sheets.scope.value.kind==="subset"?sheets.scope.value.id:"";
  if(kind==="rename")editor.openRename(targetId);
  else if(kind==="insert-sheet")editor.openInsertSheet(targetId);
  else if(kind==="insert-subset")editor.openInsertSubset();
}
let previewGeneration=0;

// 布局读取代次：取消/切表单/切 CAD 版本后的旧布局响应不回填（任务 6）
let layoutReadGeneration=0;

const blocking=computed(()=>workspace.value?.diagnostics.filter(item=>item.severity==="error")??[]);
const sheetPropertyNames=computed(()=>workspace.value?.sheet_set.property_definitions.filter(item=>item.type==="sheet").map(item=>item.name)??[]);
// —— 页面事件 → 命令/API 编排（Task 11 第 11e 轮：抽出 useWorkspaceCommands）——
// 提交命令/预览/写入/ActionDock 门禁矩阵/布局模板读取/全局快捷键与 CSV 导入编排已迁入组合式函数；
// 此处解构回同名局部变量，`<template>` 与其余接线不变。
// 位置要求：`submitCommands` 是 `useSheetEditor` 与 `usePropertiesWorkspace` 的**直接实参**
// （setup 期求值），故本调用必须早于它们；而 `editor`/`properties` 在下方才创建，
// 代次计数又是会被重赋值的 `let`（不能解构回同名），故一律以**懒取值函数/闭包**传入
// （见 useWorkspaceCommands 头部说明）。
const commandsApi=useWorkspaceCommands({
  workspace,error,preview,previewContext,isPreviewing,isWorkspaceLoading,isRestoreExecuting,cadVersion,
  t,confirmAction,pushToast,cloneJson,invalidatePreview,
  nextPreviewGeneration:()=>++previewGeneration,
  currentPreviewGeneration:()=>previewGeneration,
  nextLayoutReadGeneration:()=>++layoutReadGeneration,
  currentLayoutReadGeneration:()=>layoutReadGeneration,
  draft:draftGuards,
  nav:{openOverlay},
  getLifecycle:()=>lifecycle,
  getEditor:()=>editor,
  getProperties:()=>properties,
  getSheets:()=>sheets,
  getJobMonitor:()=>({job,terminal,watchJob,invalidateJobMonitor,isCurrentJobGeneration}),
  getRepair:()=>({dstValidation,repairWritesDisabled}),
  getCsvImport:()=>({importCsv,invalidateCsvPreview,csvText,csvPreview}),
  setJob,hasShell,selectAndOpenDst,
  refreshSheetProjection:()=>refreshSheetProjection(),
});
const {
  bulkPropertyName,bulkPropertyValue,bulkMode,
  submitCommands,
  queueDelete,queueDeleteSubset,queueBulkSheetProperty,queueDeleteProperty,
  guardedImportCsv,closeCsvImport,
  showPreview,execute,write,dock,
  selectTemplateFile,selectSubsetTemplateFile,selectBaseTemplateFile,
  previewGroups,derivedSubsets,sourceBaselines,subsetOperations,cardinalityFrontier,
  cadValidationDeferred,semanticDiff,executionEstimate,
}=commandsApi;
// —— 分页编辑缓冲与全局输入保护（PLAN-DM-015 任务 5）：唯一活动编辑上下文，跨主标签保留 ——
const editor=useSheetEditor({
  workspace,baseWorkspace,commands,sheetPropertyNames,
  refreshSheetProjection,submitCommands,
  locateSheet,selectSubset:sheetsSelectSubset, // 操作表单成功后定位新增/编辑对象并更新到其所在范围
});
// 未提交输入保护接线（SPEC-DM-009 §6.2）：`runScopeChange`/`guardedFilter` 已迁入 useDraftGuards，
// 此处只保留五个经保护接线的过滤条件（v-model 语义保持，仅在隐藏当前编辑对象时三选一）
const guardedSearchText=guardedFilter((value:string)=>{searchText.value=value});
const guardedSearchAll=guardedFilter((value:boolean)=>{searchAll.value=value});
const guardedPathFilter=guardedFilter((value:SheetPathFilter)=>{pathFilter.value=value});
const guardedDiagnosticFilter=guardedFilter((value:SheetDiagFilter)=>{diagnosticFilter.value=value});
const guardedPendingFilter=guardedFilter((value:SheetPendingFilter)=>{pendingFilter.value=value});
// 「编辑属性」：打开唯一编辑上下文（操作表单等另一上下文内有未提交输入先三选一）
function onEditSheet(sheet:Sheet){editor.openSheetEditor(sheet.id)}
// 属性页会话缓冲域（PLAN-DM-016 任务 2/6）：三层快照/提交生命周期/三选一 guard/面板会话态，
// 状态在此不在页面；新增属性定义仍经既有 addCommand('property') 命令簿门禁，页面不持有草稿栈
const properties=usePropertiesWorkspace({workspace,baseWorkspace,submitCommands,
  addPropertyDefinition:(form)=>addCommand(createCommand.addCustomProperty(form.type,form.name,form.defaultValue),"property"),
  notifyError:(message)=>{error.value=message}});
// 删除属性定义命令使对应图纸集值字段进入失效集合；撤销/移除后随命令簿整体重算自动解除
watch(()=>commands.value.map(item=>item.type==="delete_custom_property"?`${item.property_type}:${item.name.toLocaleLowerCase()}`:"").join("|"),()=>{
  const keys=new Set<PropertyKey>();
  for(const item of commands.value)if(item.type==="delete_custom_property"&&item.property_type==="sheetset")keys.add(`sheetset:${item.name}`);
  properties.invalidateDefinitions(keys);
},{immediate:true});
// —— CSV 预览失效（PLAN-DM-016 任务 5）：预览结果只对发起时的基准与定义投影有效 ——
// 影响属性定义的命令簿变化（新增/删除属性定义，含撤销/移除）使预览失效；仅失效预览，不清除已选文件文本
watch(()=>commands.value.map(item=>item.type==="add_custom_property"?`add:${item.property_type}:${item.name.toLocaleLowerCase()}`:item.type==="delete_custom_property"?`del:${item.property_type}:${item.name.toLocaleLowerCase()}`:"").join("|"),()=>{
  invalidateCsvPreview(false);
},{immediate:true});
// 工作区或基准修订变化（重开/刷新/任务成功后刷新）使预览失效：不能以旧预览上下文确认新基准
watch(()=>`${workspace.value?.id??""}:${workspace.value?.revision_id??""}`,()=>{
  invalidateCsvPreview(false);
},{immediate:true});
// —— 全局输入保护（PLAN-DM-016 任务 2）：图纸页与属性页两个活动输入域依次过闸 ——
// `guardAllInputs`/`resolveSharedGuard`/`sharedGuardState` 已迁入 useDraftGuards（注释随迁）

function cloneJson<T>(value:T):T{return JSON.parse(JSON.stringify(value))}
function invalidatePreview(){previewGeneration+=1;preview.value=null;previewContext.value=null}
// 配置中心保存 AutoCAD 版本后，后续布局读取与预览统一使用新版本；旧预览立即失效。
watch(cadVersion,()=>{
  layoutReadGeneration+=1;
  invalidatePreview();
  void refreshSheetProjection();
});
// 删除整个子集：目标取编辑子集表单的编辑对象；编辑未提交时先三选一决策（保存后再删除），
// 再走整子集删除确认流程。目标 ID 在 guard 前捕获——保存标题会关闭表单，删除仍作用于原目标。
// 批量加入草稿：与单行编辑共用一个活动编辑上下文，有未提交输入先三选一
// 删除属性定义（PLAN-DM-016 任务 4 / SPEC-DM-010 §4.2）：沿用既有草稿与确认语义；
// 目标 sheetset 值仍 dirty 时先运行属性输入 guard（三选一）再弹删除确认；空文本值不视为删除定义。
// 确认文案只说明作用域与草稿语义，不虚构级联影响数量；受影响范围以预览时服务端结果为准。
// 新增图纸/新建子集提交由 useSheetEditor 处理：参照对象 → ordinal 映射（commands.ts）、
// 原 command schema、成功定位与失败保留输入（任务 6），不在 App.vue 重复实现。

// 壳层 props 分组（Task 11 Step 6 / 11a）：把子组件所需 props 组装成对象交给 WorkspaceShell。
// 分组而非逐个传递，是为了让「键名写错」成为**编译错误**（对象字面量受 excess property 检查约束），
// 而逐个写 prop 名若拼错会静默落进 `$attrs`（正是本重构最想避免的隐性行为漂移）。
// `dock` 已在上面定义，直接透传。
type TopBarProps=InstanceType<typeof TopBar>["$props"];
type TabBarProps=InstanceType<typeof TabBar>["$props"];
type TaskOverlayProps=InstanceType<typeof TaskOverlay>["$props"];
const topBarProps=computed<TopBarProps>(()=>({
  sheetSetName:sheetSetName.value,
  dstPath:dstPath.value,
  dstStatus:dstStatus.value,
  closeDisabled:isRestoreExecuting.value||isRepairExecuting.value,
  hasShell:hasShell.value,
  workspaceId:workspace.value?.id??"",
}));
const tabBarProps=computed<TabBarProps>(()=>({
  descriptors:tabDescriptors.value,
  active:active.value,
}));
const taskOverlayProps=computed<TaskOverlayProps>(()=>({
  open:overlayOpen.value,
  tab:overlayTab.value,
  hasBlocking:blocking.value.length>0,
  hasRepair:Boolean(dstValidation.value&&dstValidation.value.status!=="VALID"),
  job:job.value,
  connectionMode:connectionMode.value,
  preview:preview.value,
  semanticDiff:semanticDiff.value,
  estimate:executionEstimate.value,
  cadValidationDeferred:cadValidationDeferred.value,
  cardinalityFrontier:cardinalityFrontier.value,
  subsetOperations:subsetOperations.value,
  sourceBaselines:sourceBaselines.value,
  derivedSubsets:derivedSubsets.value,
  groups:previewGroups.value,
  diagnostics:workspace.value?.diagnostics??[],
  dstValidation:dstValidation.value,
  repairPreview:repairPreview.value,
  isRepairPreviewing:isRepairPreviewing.value,
  isRepairExecuting:isRepairExecuting.value,
}));

</script>

<template>
  <WorkspaceShell
    :has-workspace="Boolean(workspace)"
    :sheets-active="Boolean(workspace) && active === 'sheets'"
    :error="error"
    :last-error-diagnostic="lastErrorDiagnostic"
    :is-workspace-loading="isWorkspaceLoading"
    :is-restore-executing="isRestoreExecuting"
    :top-bar="topBarProps"
    :tab-bar="tabBarProps"
    :task-overlay="taskOverlayProps"
    :dock="dock"
    @close="closeWorkspace"
    @open-folder="openFolder"
    @open-settings="openSettings"
    @select="selectTab"
    @keydown="onTabKeydown"
    @update:tab="overlayTab=$event"
    @fold="overlayOpen=!overlayOpen"
    @retry="retryJob"
    @preview-repair="previewRepair"
    @execute-repair="executeRepair"
    @cancel-repair="repairPreview=null;repairContext=null"
    @preview="showPreview"
    @write="write"
    @undo="undoDraft"
    @redo="redoDraft"
    @clear="clearCommands"
    @remove="removeDraftAction"
    @discard="discardDraft"
    @reload-conflict="reloadAfterDraftConflict"
    @retry-save="scheduleDraftSave"
  >
      <template v-if="!workspace">
        <!-- PLAN-DM-035 Task 7：无工作区时按起始面装配；标准管理不进工作区标签栏。
             PLAN-DM-039 Task 1：欢迎页三个次级入口各走唯一既有去向——创建进创建向导，
             管理进标准库，导入把一次性意图交给标准页以打开同一个导入对话框。
             PLAN-DM-036 Task 8：创建向导取代原“后续版本提供”占位；标准详情「用于创建」
             把固定发布版本作为一次性身份传入，向导据此直接进入第二阶段。 -->
        <WelcomeView v-if="startNavigation.surface.value==='welcome'" :has-shell="hasShell" @select="selectAndOpenDst" @submit-path="openByPath" @create-sheetset="startNavigation.openCreateSheetset()" @manage-standards="startNavigation.openStandards()" @import-standard="startNavigation.openStandards('import-package')" />
        <StandardsView v-else-if="startNavigation.surface.value==='standards'" :confirm-action="confirmAction" :entry-intent="standardsEntryIntent" @back="startNavigation.goWelcome()" @open-create-sheetset="startNavigation.openCreateSheetset($event)" />
        <CreateSheetSetView v-else :confirm-action="confirmAction" :entry-identity="startNavigation.createSheetsetIdentity.value" @back="startNavigation.goWelcome()" @standards="startNavigation.openStandards()" />
      </template>
      <template v-else>
        <div v-if="draftRecovered!==null&&draftRecovered>0&&!isWorkspaceLoading" class="recover-banner" role="status">{{ $t("shell.workspace.recoveredBanner",{count:draftRecovered},draftRecovered) }}<button type="button" @click="draftRecovered=null">{{ $t("shell.workspace.resume") }}</button><button type="button" @click="clearDraftRestart">{{ $t("shell.workspace.restart") }}</button></div>
        <SheetsView v-if="active==='sheets'&&!isWorkspaceLoading&&!isRestoreExecuting" :workspace="workspace" :scope="scope" :focused-sheet-id="focusedSheetId" :selected-ids="selectedIds" :filtered-rows="filteredRows" :visible-rows="visibleRows" :hidden-selected-count="hiddenSelectedCount" :all-filtered-selected="allFilteredSelected" :hidden-target="hiddenTarget" :prune-message="pruneMessage" :scope-total="scopeTotal" :all-total="allTotal" :range-total="rangeTotal" :pending-sheet-ids="pendingSheetIds" :diagnostic-object-ids="diagnosticObjectIds" :sheet-property-names="sheetPropertyNames" :visible-columns="visibleColumns" :column-options="columnOptions" :new-property-count="newPropertyCount" :column-save-error="columnSaveError" :edit-context="editor.context.value" :search-text="searchText" :search-all="searchAll" v-model:filters-visible="filtersVisible" :path-filter="pathFilter" :diagnostic-filter="diagnosticFilter" :pending-filter="pendingFilter" v-model:render-limit="renderLimit" v-model:bulk-property-name="bulkPropertyName" v-model:bulk-property-value="bulkPropertyValue" v-model:bulk-mode="bulkMode" @update:search-text="guardedSearchText" @update:search-all="guardedSearchAll" @update:path-filter="guardedPathFilter" @update:diagnostic-filter="guardedDiagnosticFilter" @update:pending-filter="guardedPendingFilter" @select-all="() => runScopeChange(() => sheetsSelectAll())" @select-subset="(id) => runScopeChange(() => sheetsSelectSubset(id))" @select-sheet="(id) => runScopeChange(() => locateSheet(id))" @toggle-filtered-selection="toggleFilteredSelection" @clear-selection="clearSelection" @clear-filters="clearFilters" @toggle-sheet="toggleSheet" @edit-sheet="onEditSheet" @delete-sheet="queueDelete" @editor-set-value="editor.setFieldValue" @editor-set-page="editor.setPage" @editor-set-search="editor.setSearch" @editor-submit="() => void editor.submit()" @editor-cancel="editor.cancel" @editor-jump-error="editor.jumpToError" @queue-bulk-sheet-property="queueBulkSheetProperty" @open-operation="openOperation" @operation-submit="() => void editor.submit()" @operation-cancel="editor.cancel" @operation-delete-subset="queueDeleteSubset" @select-template-file="selectTemplateFile" @select-subset-template-file="selectSubsetTemplateFile" @select-base-template-file="selectBaseTemplateFile" @toggle-builtin="setBuiltin" @toggle-property="setProperty" @reset-columns="resetColumns" @open-diagnostics="() => openOverlay('diag')" />
        <PropertiesView v-if="active==='properties'&&!isWorkspaceLoading&&!isRestoreExecuting" :workspace="workspace" :property-input="properties.input.value" :property-base="properties.base.value" :property-draft="properties.draft.value" :property-status-of="properties.statusOf" :property-errors="properties.errors.value" :property-summary-error="properties.summaryError.value" :property-matched-keys="properties.matchedKeys.value" :property-hidden-dirty-count="properties.hiddenDirtyCount.value" :property-search="properties.search.value" :property-search-mode="properties.searchMode.value" :property-changed-only="properties.changedOnly.value" :property-active-key="properties.activeKey.value" :property-definition-form="properties.definitionForm" :property-definitions-collapsed="properties.definitionsCollapsed.value" :property-values-collapsed="properties.valuesCollapsed.value" :property-csv-collapsed="properties.csvCollapsed.value" :property-csv-open="properties.csvOpen.value" :property-definitions-query="properties.definitionsQuery.value" :property-definitions-scope="properties.definitionsScope.value" :property-definitions-page="properties.definitionsPage.value" :has-csv="Boolean(csvText)" :csv-preview="csvPreview" :csv-executable="Boolean(csvPreviewContext?.result.executable)" :repair-writes-disabled="repairWritesDisabled" @set-property-value="(key:ValueKey,value:string)=>properties.setValue(key,value)" @submit-values="() => void properties.submitValues()" @revert-value="(key:ValueKey)=>properties.revertValue(key)" @update:property-search="(value:string)=>properties.search.value=value" @update:property-search-mode="(value:PropertySearchMode)=>properties.searchMode.value=value" @update:property-changed-only="(value:boolean)=>properties.changedOnly.value=value" @update:property-active-key="(key:ValueKey|null)=>properties.activeKey.value=key" @update:property-definitions-collapsed="(value:boolean)=>properties.definitionsCollapsed.value=value" @update:property-values-collapsed="(value:boolean)=>properties.valuesCollapsed.value=value" @update:property-csv-collapsed="(value:boolean)=>properties.csvCollapsed.value=value" @update:property-csv-open="(value:boolean)=>properties.csvOpen.value=value" @update:property-definitions-query="(value:string)=>properties.definitionsQuery.value=value" @update:property-definitions-scope="(value:DefinitionScopeFilter)=>properties.definitionsScope.value=value" @update:property-definitions-page="(value:number)=>properties.definitionsPage.value=value" @discard-property-input="properties.discardInput" @queue-property-definition="properties.queuePropertyDefinition" @queue-delete-property="queueDeleteProperty" @read-csv="readCsvFile" @preview-csv="previewCsv" @import-csv="guardedImportCsv" @close-csv="closeCsvImport" />
        <RevisionsView v-if="active==='revisions'" :revisions="revisions" :restore-preview="restorePreview" :executing="isRestoreExecuting" :is-workspace-loading="isWorkspaceLoading" @preview="previewRestoreAndOpen" @restore="restoreRevision" />
        <!-- 扩展页面贡献（PLAN-DM-020 Task 10）：组件来自编译期 pageRegistry 映射，
             App 只装配挂载，不承载目录业务状态；加载/恢复期间暂停交互与其他主标签一致。
             启停入口已收归设置中心扩展分区，页面不再暴露 toggle 事件 -->
        <template v-for="page in extensionPages" :key="page.routeKey">
          <component :is="EXTENSION_PAGE_COMPONENTS[page.routeKey]" v-if="active===page.routeKey&&!isWorkspaceLoading&&!isRestoreExecuting" :extension="page.summary" :workspace="workspace" />
        </template>
      </template>
  </WorkspaceShell>
  <ConfirmModal v-bind="confirmState" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />
  <SettingsDialog :open="settingsOpen" :push-toast="pushToast" :extensions-panel="extensionsPanel" @close="settingsOpen=false" />
  <!-- 唯一共享三选一模态：图纸页与属性页 guard 顺序开合同一实例，状态取当前打开者 -->
  <UnsavedInputDialog v-bind="sharedGuardState" @save-and-continue="resolveSharedGuard('save')" @discard="resolveSharedGuard('discard')" @stay="resolveSharedGuard('stay')" />
  <ToastHost :toasts="toasts" @dismiss="dismiss" @jump="jumpOverlay" />
</template>
