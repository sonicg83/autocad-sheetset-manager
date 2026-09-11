<script setup lang="ts">
import {computed,ref,watch} from "vue";
import {useI18n} from "vue-i18n";
import {ApiError,lastErrorDiagnostic,localizedError,request} from "./api/client";
import {clearWorkspaceContext,getShellBridge,shellReady,openWorkspaceFolder as bridgeOpenWorkspaceFolder} from "./api/shell";
import {useExtensions} from "./composables/useExtensions";
import type {BeforeExtensionListReplace,ExtensionsPanel} from "./composables/useExtensions";
import {EXTENSION_PAGE_COMPONENTS,isExtensionRouteKey,type ExtensionRouteKey} from "./features/extensions/pageRegistry";
import {createCommand} from "./api/contracts";
import type {ChangeCommand,DraftAction,DraftEnvelope,ExtensionSummary,Job,Preview,PropertyDefinition,Revision,SemanticDiff,Sheet,Subset,Workspace} from "./api/contracts";
import {projectCommands,projectWorkspace} from "./drafts";
import type {InsertSheetEditContext, InsertSubsetEditContext, SubmitResult, DraftActionLabel} from "./features/sheets/types";
import type {GuardChoice} from "./features/sheets/types";
import type {PropertyKey, PropertySearchMode, ValueKey} from "./features/properties/types";
import type {DefinitionScopeFilter} from "./features/properties/model";
import {useShellTabs} from "./composables/useShellTabs";
import {useJobMonitor} from "./composables/useJobMonitor";
import {useCsvImport} from "./composables/useCsvImport";
import {useRepair} from "./composables/useRepair";
import {useRestore} from "./composables/useRestore";
import {useSheetProjection} from "./composables/useSheetProjection";
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
import {useHotkeys} from "./composables/useHotkeys";
import type {TabDescriptor} from "./composables/useShellTabs";
import WelcomeView from "./views/WelcomeView.vue";
import SheetsView from "./views/SheetsView.vue";
import PropertiesView from "./views/PropertiesView.vue";
import RevisionsView from "./views/RevisionsView.vue";

type PreviewContext={workspaceId:string;baseRevisionId:string;cadVersion:string;commands:ChangeCommand[];result:Preview};

// PLAN-DM-021 Task 4：文件选择经桥的 file_kind + 本地化描述（描述取自语言包，仅作对话框显示）
const {t}=useI18n();
const {state:confirmState,confirmAction,resolve:resolveConfirm}=useConfirm();
const workspace=ref<Workspace|null>(null);
const baseWorkspace=ref<Workspace|null>(null);
const error=ref("");
const commands=ref<ChangeCommand[]>([]);
const draftActions=ref<DraftAction[]>([]);
const draftCursor=ref(0);
const draftVersion=ref(0);
const draftStale=ref(false);
const draftStaleReasons=ref<string[]>([]);
const draftCorrupted=ref(false);
const draftSaveFailed=ref(false);
const lastDraftError=ref<ApiError|null>(null); // 最近一次草稿保存错误（字段级错误供编辑器行内/摘要消费）
const draftSaving=ref(false);
const draftRecovered=ref<number|null>(null);
const preview=ref<Preview|null>(null);
const previewContext=ref<PreviewContext|null>(null);
// 预览请求进行中（Task 5 ActionDock 门禁：仅作按钮 loading 呈现，不阻止再次发起——竞态由 previewGeneration 丢弃乱序响应）
const isPreviewing=ref(false);
const isWorkspaceLoading=ref(false);
const isRestoreExecuting=ref(false);
// 工作区加载代次为跨域共享的单一 ref：App.vue（打开/关闭/刷新）与修复/恢复域组合式函数共用
const workspaceLoadGeneration=ref(0);
// 任务浮层状态（SPEC-DM-006 §4.1）：open/tab 由 App 持有（Task 7 toast 抑制与"查看"跳转依赖）；openOverlay 为唯一自动展开入口
const overlayOpen=ref(false),overlayTab=ref<"prog"|"prev"|"diag">("prog");
function openOverlay(tab:"prog"|"prev"|"diag"){overlayTab.value=tab;overlayOpen.value=true}
// 非模态任务通知（SPEC-DM-006 §6.6）：toast 状态/推送/关闭；"查看"跳转仅放行合法页签后复用 openOverlay
const {toasts,pushToast,dismiss}=useToast();
// 设置中心（PLAN-DM-019 任务 10/11）：入口在 TopBar 齿轮；toast 复用宿主 useToast
const settingsOpen=ref(false);
function jumpOverlay(tab:string){if(tab==="prog"||tab==="prev"||tab==="diag")openOverlay(tab)}
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
const cadVersion=ref("2020");
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
// 标签描述符：核心三标签（图纸/属性/修订历史）顺序固定不被扩展替换，扩展页面追加在后；
// 无工作区时不显示 workspace_page 贡献。修订历史与扩展页在加载/恢复期间禁用（页面内容
// 未渲染，防中途点击进入空态），守卫语义与旧 TabBar 的 revisions-disabled 绑定一致
const tabDescriptors=computed<TabDescriptor[]>(()=>{
  const busyDisabled=isRestoreExecuting.value||isWorkspaceLoading.value;
  const core:TabDescriptor[]=[
    {id:"sheets",label:t("shell.tabs.sheets"),number:"①",source:"core"},
    {id:"properties",label:t("shell.tabs.properties"),number:"②",source:"core"},
    {id:"revisions",label:t("shell.tabs.revisions"),number:"③",source:"core",disabled:busyDisabled},
  ];
  if(workspace.value===null)return core;
  for(const page of extensionPages.value)core.push({id:page.routeKey,label:t(page.summary.name_key),source:"extension",disabled:busyDisabled});
  return core;
});
const tabIds=computed(()=>tabDescriptors.value.map(descriptor=>descriptor.id));
// 固定标签栏状态（SPEC-DM-006 §7.2）：active/select/onKeydown 由 useShellTabs 提供，TabBar 为受控组件；
// 动态列表下激活项被移除时安全校正回首个核心标签
const {active,select,onKeydown}=useShellTabs<string>(tabIds,"sheets","sheets");
// 切换页签先过图纸目录页未保存草稿闸门（PLAN-DM-020 Task 11 / SPEC-DM-012 §3.2：
// 目录页未挂载时守卫为空操作）；目录页自身草稿在离开前必须三选一。
// 重复点击当前页签保留既有语义：不重开闸门，修订历史页签仍然重新加载列表
function selectTab(id:string){
  if(id===active.value){ if(id==="revisions")void loadRevisions(); return }
  if(!sheetCatalogNavigationNeeded()){select(id);if(id==="revisions")void loadRevisions();return}
  void doSelectTab(id);
}
async function doSelectTab(id:string){
  await guardSheetCatalogPage(()=>{select(id);if(id==="revisions")void loadRevisions()});
}
function onTabKeydown(e:KeyboardEvent){
  const before=active.value;onKeydown(e);
  const target=active.value;
  if(target===before)return;
  // 无未保存草稿时保持既有同步切换（useShellTabs 已改写 active）；有草稿才走闸门
  if(!sheetCatalogNavigationNeeded()){if(target==="revisions")void loadRevisions();return}
  active.value=before;void doSelectTab(target);
}
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
function onCadVersionChange(value:string){cadVersion.value=value;layoutReadGeneration+=1;invalidatePreview()}
const bulkPropertyName=ref("");
const bulkPropertyValue=ref("");
const bulkMode=ref<"set"|"clear">("set"); // 批量模式：设置值 / 清空值（SPEC-DM-009 §6.1 显式区分）
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
let draftSaveQueue:Promise<void>=Promise.resolve();

const DWG_DWT_EXT=/\.(dwg|dwt)$/i;
// 布局读取代次：取消/切表单/切 CAD 版本后的旧布局响应不回填（任务 6）
let layoutReadGeneration=0;

const blocking=computed(()=>workspace.value?.diagnostics.filter(item=>item.severity==="error")??[]);
const hasPropertyDefinitionCommands=computed(()=>commands.value.some(item=>item.type==="add_custom_property"||item.type==="delete_custom_property"));
const hasStructuralCommands=computed(()=>commands.value.some(item=>["update_subset_title","delete_sheet","delete_subset","insert_sheet","insert_subset"].includes(String(item.type))));
const previewGroups=computed(()=>preview.value?.execution_intent?.groups??[]);
const derivedSubsets=computed(()=>preview.value?.execution_intent?.derived_document?.subsets??[]);
const sourceBaselines=computed(()=>preview.value?.execution_intent?.source_baselines??[]);
const subsetOperations=computed(()=>preview.value?.execution_intent?.subset_operations??[]);
const cardinalityFrontier=computed(()=>preview.value?.execution_intent?.cardinality_frontier??null);
const cadValidationDeferred=computed(()=>preview.value?.execution_intent?.cad_validation_deferred===true);
const semanticDiff=computed<SemanticDiff>(()=>preview.value?.semantic_diff??{sheet_set:[],structure:{before:[],after:[]},properties:[],dwgs:[]});
const sheetPropertyNames=computed(()=>workspace.value?.sheet_set.property_definitions.filter(item=>item.type==="sheet").map(item=>item.name)??[]);
const executionEstimate=computed(()=>preview.value?.execution_intent?.estimate??null);
const saveStatusText=computed(()=>draftSaveFailed.value?t("shell.dock.saveStatusFailed"):draftSaving.value?t("shell.dock.saveStatusSaving"):draftStale.value?t("shell.dock.saveStatusStale"):t("shell.dock.saveStatusSaved"));
// —— 提交命令（SubmitCommands）：加入草稿动作并等待持久化与投影成功，不以入队即宣称保存 ——
// label 为 DraftActionLabel（稳定 label_key + 命名 params，PLAN-DM-021 Task 8/I18N-12）：语言不写入草稿
async function submitCommands(commands:ChangeCommand[],label:DraftActionLabel,category:"metadata"|"structural"|"property"):Promise<SubmitResult>{
  if(draftStale.value)return{ok:false,message:t("shell.errors.draftStaleAction")};
  // 结构变更与属性定义变更必须分批；属性值编辑（metadata）可与结构并存（混合批次显示由命令簿叠加合成）
  if(category==="structural"&&hasPropertyDefinitionCommands.value)return{ok:false,message:t("shell.errors.mixedBatches")};
  if(category==="property"&&hasStructuralCommands.value)return{ok:false,message:t("shell.errors.mixedBatches")};
  // 草稿保存失败重试：仅当撤销/重做光标位于栈顶且与最后一条草稿动作等价时，
  // 视为保存失败重试而不重复加入同一命令批次；撤销后重提交相同命令必须重新入栈（I-1 修复）
  const last=draftActions.value[draftActions.value.length-1];
  const sameBatch=last?.kind==="command_batch"&&draftCursor.value===draftActions.value.length&&JSON.stringify(last.commands)===JSON.stringify(commands);
  if(!sameBatch){if(!addCommandBatch(commands,label,category))return{ok:false,message:error.value||t("shell.errors.addDraftFailed")}}
  // 保存失败重试去重：不重复入栈，但用户确实执行了一次加入草稿动作，旧预览同样失效
  else {scheduleDraftSave();invalidatePreview()}
  await draftSaveQueue;
  if(draftSaveFailed.value)return{ok:false,message:lastDraftError.value?.message??t("shell.errors.draftSaveFailed"),fields:lastDraftError.value?.fields};
  const projection=await refreshSheetProjection();
  if(!projection.ok)return projection;
  return{ok:true};
}
// —— 分页编辑缓冲与全局输入保护（PLAN-DM-015 任务 5）：唯一活动编辑上下文，跨主标签保留 ——
const editor=useSheetEditor({
  workspace,baseWorkspace,commands,sheetPropertyNames,
  refreshSheetProjection,submitCommands,
  locateSheet,selectSubset:sheetsSelectSubset, // 操作表单成功后定位新增/编辑对象并更新到其所在范围
});
// 未提交输入保护接线（SPEC-DM-009 §6.2）：范围/筛选改变若隐藏当前编辑对象，
// 先还原快照再三选一（加入草稿后继续/放弃输入/留在此处），保存/放弃后再应用
function runScopeChange(apply:()=>void){
  const ctx=editor.context.value;
  if(!ctx||ctx.kind!=="sheet"||!editor.hasUnsavedChanges.value){apply();return}
  const snapshot=sheetsSnapshotState();
  apply();
  const hidden=!sheets.filteredRows.value.some(row=>row.sheet.id===ctx.objectId);
  if(!hidden)return;
  sheetsRestoreState(snapshot);
  void editor.guard(apply);
}
function guardedFilter<T>(apply:(value:T)=>void){return(value:T)=>runScopeChange(()=>apply(value))}
// 过滤条件经保护接线（v-model 语义保持，仅在隐藏当前编辑对象时三选一）
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
// 固定先处理当前主标签的活动编辑器，再处理另一域；任一步「留在此处」即终止 next。
// 页面只挂载一个共享 UnsavedInputDialog（见模板），两个 guard 顺序开合同一实例，不叠加模态。
// PLAN-DM-020 Task 11：核心输入域过闸后再征询图纸目录页未保存模板草稿的三选一守卫
// （目录页未挂载时为空操作）；「留在此处」同样终止 next。
async function guardAllInputs(next:()=>void|Promise<void>){
  const core=async()=>{if(active.value==="properties")await properties.guard(()=>editor.guard(next));else await editor.guard(()=>properties.guard(next))};
  await guardSheetCatalogPage(core);
}
function resolveSharedGuard(choice:GuardChoice){editor.resolveGuard(choice);properties.resolveGuard(choice)}
const sharedGuardState=computed(()=>properties.guardState.value.open?properties.guardState.value:editor.guardState.value);

function cloneJson<T>(value:T):T{return JSON.parse(JSON.stringify(value))}
function invalidatePreview(){previewGeneration+=1;preview.value=null;previewContext.value=null}
function resetEditingState(){commands.value=[];invalidatePreview();invalidateCsvPreview(true);error.value=""}
function resetDraftState(){draftActions.value=[];draftCursor.value=0;draftVersion.value=0;draftStale.value=false;draftStaleReasons.value=[];draftCorrupted.value=false;draftSaveFailed.value=false;draftSaving.value=false;draftRecovered.value=null}
function beginWorkspaceLoad(){workspaceLoadGeneration.value+=1;isWorkspaceLoading.value=true;resetEditingState();resetDraftState();invalidateRevisionState();overlayOpen.value=false;overlayTab.value="prog";return workspaceLoadGeneration.value}
async function openByPath(path:string){
  // 重新打开/切换工作区前先过全局输入保护（无未提交输入时直接通过）
  await guardAllInputs(()=>doOpenByPath(path));
}
async function doOpenByPath(path:string){
  if(isRestoreExecuting.value){error.value=t("shell.errors.restoreRunning");return}
  isWorkspaceLoading.value=true;
  await draftSaveQueue;
  if(draftSaveFailed.value){isWorkspaceLoading.value=false;return}
  invalidateJobMonitor(true);
  const generation=beginWorkspaceLoad();
  try{
    const loaded:Workspace=await request("/api/workspaces/open",{method:"POST",body:JSON.stringify({dst_path:path})});
    if(generation!==workspaceLoadGeneration.value)return;
    resetEditingState();baseWorkspace.value=cloneJson(loaded);workspace.value=cloneJson(loaded);resetSheetsWorkspace();await loadDraft(loaded);isWorkspaceLoading.value=false;
    void reloadExtensions();
    // 打开成功后若停留在修订历史标签，重载修订列表（beginWorkspaceLoad 已 invalidateRevisionState 清空，避免虚假空态）
    if(active.value==="revisions")void loadRevisions();
  }
  catch(e){if(generation===workspaceLoadGeneration.value){isWorkspaceLoading.value=false;error.value=String(e)}}
}
// 桥晚于首帧注入（pywebviewready）：依赖 shellReady 才能在就绪时重算，否则永远显示无壳降级界面
const hasShell=computed(()=>shellReady.value&&getShellBridge()!==null);
// 打开图纸集所在文件夹（PLAN-DM-015 任务 2）：目标路径由服务端可信上下文解析，前端只传
// workspace_id；异步返回后再比较一次，旧工作区结果不进入新工作区
async function openFolder(){
  const current=workspace.value;
  if(!current||!hasShell.value)return;
  const result=await bridgeOpenWorkspaceFolder(current.id);
  if(workspace.value?.id!==current.id)return;
  if(!result){error.value=t("shell.errors.shellFolderUnsupported");return}
  if(!result.ok)error.value=result.code==="SHELL_WORKSPACE_UNAVAILABLE"?t("shell.errors.workspaceSwitched"):localizedError(result.message_key,result.params,result.message);
}
const DST_EXT=/\.dst$/i;
const DROP_CALLBACK_ID="__dstManagerAcceptDst";
async function acceptDstPath(path:string){
  // 设置对话框打开时丢弃壳侧 document 级 drop 回调（SC-14 双保险：对话框已 stop 冒泡）
  if(settingsOpen.value)return;
  if(workspace.value){error.value=t("shell.errors.closeFirst");return}
  if(!DST_EXT.test(path)){error.value=t("shell.errors.dstOnly");return}
  await openByPath(path);
}
async function selectAndOpenDst(){
  const bridge=getShellBridge();
  if(!bridge){error.value=t("shell.errors.shellNotReady");return}
  const path=await bridge.select_file("dst",t("common.shell.fileKinds.dst"));
  if(!path)return;
  await acceptDstPath(path);
}
function registerDropBridge(){
  const bridge=getShellBridge();
  // 老/部分桥面可能只暴露 select_file：on_files_dropped 缺失时静默跳过拖拽接桥
  if(!bridge||typeof bridge.on_files_dropped!=="function")return;
  // 拖拽热区接桥：壳侧 document drop 监听（pywebview 原生 pywebviewFullPath）→ 本全局回调
  (window as unknown as Record<string,unknown>)[DROP_CALLBACK_ID]=(path:unknown)=>{void acceptDstPath(String(path))};
  void bridge.on_files_dropped(DROP_CALLBACK_ID).catch(()=>{});
}
// 桥就绪时机不定（早于/晚于首帧注入都可能）：immediate 覆盖已就绪，watch 覆盖 pywebviewready 晚到
watch(shellReady,ready=>{if(ready)registerDropBridge()},{immediate:true});
// 布局读取写入当前活动表单上下文：经代次 + 对象身份校验，取消/切表单/切版本后的旧响应不回填
function activeLayoutContext(kind:"insert-sheet"):InsertSheetEditContext|null;
function activeLayoutContext(kind:"insert-subset"):InsertSubsetEditContext|null;
function activeLayoutContext(kind:"insert-sheet"|"insert-subset"):InsertSheetEditContext|InsertSubsetEditContext|null{
  const ctx=editor.context.value;
  return ctx&&ctx.kind===kind?(ctx as InsertSheetEditContext|InsertSubsetEditContext):null;
}
async function loadLayoutOptions(path:string,ctx:InsertSheetEditContext|InsertSubsetEditContext){
  const gen=++layoutReadGeneration;
  ctx.layoutLoading=true;ctx.layoutOptions=[];
  // M4：cad_version 使用当前工作区的响应式版本，去除硬编码 "2020"
  try{
    const r=await request<{layouts:string[];cached:boolean;file_hash:string}>(`/api/layout-names`,{method:"POST",body:JSON.stringify({file_path:path,cad_version:cadVersion.value})});
    if(gen!==layoutReadGeneration||editor.context.value!==ctx)return;
    ctx.layoutOptions=r.layouts;
  }catch(e){
    if(gen!==layoutReadGeneration||editor.context.value!==ctx)return;
    ctx.layoutError=e instanceof ApiError?e.message:t("shell.errors.layoutReadFailed");ctx.layoutManual=true;
  }finally{
    if(gen===layoutReadGeneration&&editor.context.value===ctx)ctx.layoutLoading=false;
  }
}
async function selectTemplateFile(){
  const bridge=getShellBridge();
  if(!bridge){error.value=t("shell.errors.shellNotReadyShort");return}
  const path=await bridge.select_file("template",t("common.shell.fileKinds.template"));
  if(!path)return;
  if(!DWG_DWT_EXT.test(path)){error.value=t("shell.errors.templateOnly");return}
  const ctx=activeLayoutContext("insert-sheet");
  if(!ctx)return;
  ctx.sourceFile=path;ctx.layoutError="";ctx.layoutManual=false;ctx.dirty=true;
  await loadLayoutOptions(path,ctx);
}
async function selectSubsetTemplateFile(){
  const bridge=getShellBridge();
  if(!bridge){error.value=t("shell.errors.shellNotReadyShort");return}
  const path=await bridge.select_file("template",t("common.shell.fileKinds.template"));
  if(!path)return;
  if(!DWG_DWT_EXT.test(path)){error.value=t("shell.errors.templateOnly");return}
  // 与新增图纸对齐：选文件后读取布局列表（缓存优先），下拉选择布局名称
  const ctx=activeLayoutContext("insert-subset");
  if(!ctx)return;
  ctx.templateFile=path;ctx.layoutError="";ctx.layoutManual=false;ctx.dirty=true;
  await loadLayoutOptions(path,ctx);
}
async function selectBaseTemplateFile(){
  const bridge=getShellBridge();
  if(!bridge){error.value=t("shell.errors.shellNotReadyShort");return}
  const path=await bridge.select_file("template",t("common.shell.fileKinds.template"));
  if(!path)return;
  if(!DWG_DWT_EXT.test(path)){error.value=t("shell.errors.templateOnly");return}
  const ctx=activeLayoutContext("insert-subset");
  if(!ctx)return;
  ctx.baseTemplateFile=path;ctx.dirty=true;
}
// 关闭工作区：先接全局输入保护（三选一），再纳入现有关闭确认，不静默丢弃
async function closeWorkspace(){
  await guardAllInputs(async()=>{await doCloseWorkspace()});
}
async function doCloseWorkspace(){
  const pending=draftActions.value.length>0||draftSaveFailed.value||draftStale.value;
  if(pending){
    // 关闭工作区属于不可逆破坏类操作：需要显式勾选后才可确认
    const ok=await confirmAction({title:t("shell.workspace.closeConfirmTitle"),message:t("shell.workspace.closeConfirmMessage"),confirmText:t("shell.workspace.closeConfirmConfirm"),danger:true,requireCheckbox:true,reversibility:"irreversible"});
    if(!ok)return;
    await discardDraft();
  }
  const closedId=workspace.value?.id;
  // 推进加载代次：关闭后迟到的打开/刷新/修订响应全部按代次失效，防止复活工作区
  workspaceLoadGeneration.value+=1;isWorkspaceLoading.value=false;resetDraftState();resetEditingState();editor.reset();baseWorkspace.value=null;workspace.value=null;invalidateJobMonitor(true);invalidateRevisionState();overlayOpen.value=false;overlayTab.value="prog";
  clearExtensions();
  // 关闭成功清空服务端可信上下文（best-effort：旧 ID 的迟到清除请求由服务端按上下文匹配拒绝，不影响新工作区）
  if(closedId)void clearWorkspaceContext(closedId);
  // 重置图纸页工作区状态；操作表单/编辑缓冲状态已由 editor.reset() 清空，旧模板路径不残留
  resetSheetsWorkspace();layoutReadGeneration+=1;
}
// 刷新工作区同样先过全局输入保护（基准即将重建，未提交输入须先三选一）
async function refreshWorkspace(expectedWorkspaceId?:string){
  await guardAllInputs(()=>doRefreshWorkspace(expectedWorkspaceId));
}
async function doRefreshWorkspace(expectedWorkspaceId?:string){
  const current=workspace.value;
  if(!current||isWorkspaceLoading.value)return;
  const workspaceId=expectedWorkspaceId??current.id;
  if(current.id!==workspaceId)return;
  isWorkspaceLoading.value=true;
  await draftSaveQueue;
  if(draftSaveFailed.value){isWorkspaceLoading.value=false;return}
  if(workspace.value?.id!==workspaceId)return;
  const generation=beginWorkspaceLoad();
  try{
    const loaded:Workspace=await request(`/api/workspaces/${workspaceId}`);
    if(generation!==workspaceLoadGeneration.value)return;
    resetEditingState();baseWorkspace.value=cloneJson(loaded);workspace.value=cloneJson(loaded);
    await loadDraft(loaded);isWorkspaceLoading.value=false;
    void reloadExtensions();
    // 刷新成功后若停留在修订历史标签，重载修订列表（发布/关闭等路径已 invalidateRevisionState 清空，避免虚假空态）
    if(active.value==="revisions")void loadRevisions();
  }
  catch(e){if(generation===workspaceLoadGeneration.value){isWorkspaceLoading.value=false;error.value=String(e)}}
}

async function loadDraft(loaded:Workspace){
  const result:DraftEnvelope=await request(`/api/workspaces/${loaded.id}/draft`);
  if(workspace.value?.id!==loaded.id)return;
  draftCorrupted.value=result.corrupted;
  draftStale.value=result.stale;
  draftStaleReasons.value=result.stale_reasons;
  const draft=result.draft;
  if(!draft){resetDraftState();draftCorrupted.value=result.corrupted;return}
  draftActions.value=draft.actions;
  draftCursor.value=draft.cursor;
  draftVersion.value=draft.version;
  rebuildDraftProjection();
  draftRecovered.value=draft.actions.length>0?commands.value.length:null;
  if(result.corrupted)error.value=t("shell.errors.draftCorrupted");
  else if(result.stale)error.value=t("shell.errors.draftStale");
}
// 命令类型 → 语义键（I18N-07/I18N-12）：稳定命令类型不进用户文案；草稿动作只持久化
// label_key，显示文本由 DraftActionsPanel 在渲染期经语言包翻译（语言不写入草稿）
const COMMAND_LABEL_KEYS:Record<ChangeCommand["type"],string>={update_sheet_set:"shell.commands.updateSheetSet",update_subset_title:"shell.commands.updateSubsetTitle",update_sheet_properties:"shell.commands.updateSheetProperties",delete_sheet:"shell.commands.deleteSheet",insert_sheet:"shell.commands.insertSheet",insert_subset:"shell.commands.insertSubset",add_custom_property:"shell.commands.addCustomProperty",delete_custom_property:"shell.commands.deleteCustomProperty",delete_subset:"shell.commands.deleteSubset"};
function rebuildDraftProjection(){
  commands.value=draftStale.value?[]:projectCommands(draftActions.value,draftCursor.value);
  if(baseWorkspace.value){
    // 元数据/属性定义沿用本地只读副本投影；结构动作由内部投影请求以服务端权威派生结果显示
    workspace.value=projectWorkspace(baseWorkspace.value,draftStale.value?[]:draftActions.value,draftStale.value?0:draftCursor.value);
    void refreshSheetProjection();
  }
  invalidatePreview();
}
function scheduleDraftSave(){
  const workspaceId=workspace.value?.id;
  if(!workspaceId||draftStale.value)return;
  draftSaving.value=true;
  draftSaveQueue=draftSaveQueue.then(async()=>{
    const current=workspace.value;
    if(!current||current.id!==workspaceId||draftStale.value)return;
    try{
      const saved:DraftEnvelope=await request(`/api/workspaces/${workspaceId}/draft`,{method:"PUT",body:JSON.stringify({schema_version:1,base_revision_id:current.revision_id,repair_status:current.dst_validation?.status??"VALID",expected_version:draftVersion.value,cursor:draftCursor.value,actions:cloneJson(draftActions.value)})});
      if(workspace.value?.id===workspaceId&&saved.draft){draftVersion.value=saved.draft.version;draftSaveFailed.value=false;lastDraftError.value=null}
    }
    catch(e){if(workspace.value?.id===workspaceId&&e instanceof ApiError&&e.code==="DRAFT_CONFLICT"){draftSaveFailed.value=true;lastDraftError.value=e;draftStale.value=true;draftStaleReasons.value=["DRAFT_VERSION_CONFLICT"];commands.value=[];invalidatePreview();error.value=t("shell.errors.draftConflictOverwrite")}else throw e}
  }).catch(e=>{if(workspace.value?.id===workspaceId){draftSaveFailed.value=true;lastDraftError.value=e instanceof ApiError?e:null}}).finally(()=>{draftSaving.value=false});
}
function clearCommands(){draftActions.value=[];draftCursor.value=0;rebuildDraftProjection();scheduleDraftSave();error.value=""}
function clearDraftRestart(){draftRecovered.value=null;clearCommands();void discardDraft()}
function undoDraft(){if(draftStale.value||draftCursor.value===0)return;draftCursor.value-=1;rebuildDraftProjection();scheduleDraftSave()}
function redoDraft(){if(draftStale.value||draftCursor.value>=draftActions.value.length)return;draftCursor.value+=1;rebuildDraftProjection();scheduleDraftSave()}
function removeDraftAction(index:number){if(draftStale.value)return;const removedActive=index<draftCursor.value;draftActions.value.splice(index,1);if(removedActive)draftCursor.value-=1;draftCursor.value=Math.min(draftCursor.value,draftActions.value.length);rebuildDraftProjection();scheduleDraftSave()}
async function discardDraft(){
  const current=workspace.value;if(!current)return;
  await draftSaveQueue;
  if(workspace.value?.id!==current.id)return;
  try{await request(`/api/workspaces/${current.id}/draft`,{method:"DELETE",body:JSON.stringify({expected_version:draftVersion.value})})}catch(e){if(e instanceof ApiError&&e.code==="DRAFT_CONFLICT"){draftStale.value=true;draftStaleReasons.value=["DRAFT_VERSION_CONFLICT"];error.value=t("shell.errors.draftConflictDelete");return}throw e}
  resetDraftState();rebuildDraftProjection();
}
async function reloadAfterDraftConflict(){
  const current=workspace.value;if(!current||!draftStaleReasons.value.includes("DRAFT_VERSION_CONFLICT"))return;
  // 丢弃本地冲突动作并重新读取较新草稿：不改变服务器数据，属低风险动作（danger:false、无需勾选）
  const ok=await confirmAction({title:t("shell.workspace.reloadConflictTitle"),message:t("shell.workspace.reloadConflictMessage"),confirmText:t("shell.workspace.reloadConflictConfirm"),danger:false});
  if(!ok)return;
  draftSaveFailed.value=false;
  // 此路径已带明确「放弃并重新加载」确认：直接刷新，不再叠加三选一（保存对过期草稿也必然失败）
  await doRefreshWorkspace(current.id);
}
function addCommand(command:ChangeCommand,category:"property"|"structural"|"metadata"){
  if(draftStale.value){error.value=t("shell.errors.draftStaleAction");return false}
  if(category==="property"&&hasStructuralCommands.value){error.value=t("shell.errors.mixedBatches");return false}
  if(category==="structural"&&hasPropertyDefinitionCommands.value){error.value=t("shell.errors.mixedBatches");return false}
  draftActions.value=draftActions.value.slice(0,draftCursor.value);
  draftActions.value.push({id:crypto.randomUUID(),kind:"command_batch",label_key:COMMAND_LABEL_KEYS[command.type],commands:[command]});
  draftCursor.value=draftActions.value.length;rebuildDraftProjection();scheduleDraftSave();error.value="";return true;
}
function addCommandBatch(batch:ChangeCommand[],label:DraftActionLabel,category:"property"|"structural"|"metadata"){
  if(!batch.length)return false;
  if(draftStale.value){error.value=t("shell.errors.draftStaleAction");return false}
  if(category==="property"&&hasStructuralCommands.value){error.value=t("shell.errors.mixedBatches");return false}
  if(category==="structural"&&hasPropertyDefinitionCommands.value){error.value=t("shell.errors.mixedBatches");return false}
  draftActions.value=draftActions.value.slice(0,draftCursor.value);
  draftActions.value.push({id:crypto.randomUUID(),kind:"command_batch",label_key:label.key,...(label.params?{params:label.params}:{}),commands:batch});
  draftCursor.value=draftActions.value.length;rebuildDraftProjection();scheduleDraftSave();error.value="";return true;
}
// 属性页名称/值的提交改走 usePropertiesWorkspace.submitValues()（一个完整 update_sheet_set 命令），
// 不再直接读取 workspace props 编排（PLAN-DM-016 任务 2）
async function guardedImportCsv(){
  // CSV 是正式写入：确认导入前先处理普通未提交输入（三选一），不静默混批
  await guardAllInputs(async()=>{await importCsv()});
}
async function closeCsvImport(){
  // 关闭导入区（2026-09-06 用户裁决）：有未导入数据（已选文件/预览）先确认，确认后清空文件与预览缓存；
  // 在途任务不取消（job 监控独立于导入区 UI）
  if(Boolean(csvText.value)||Boolean(csvPreview.value)){
    const ok=await confirmAction({title:t("shell.flows.closeCsv.title"),message:t("shell.flows.closeCsv.message"),confirmText:t("shell.flows.closeCsv.confirm"),danger:false});
    if(!ok)return;
  }
  invalidateCsvPreview(true);
  properties.csvOpen.value=false;
}
async function queueDelete(sheet:Sheet){
  // 编辑未提交时先处理缓冲（三选一），再按删除确认流程；删除命令不得夹带未确认的属性变更
  await editor.guard(async()=>{await doQueueDelete(sheet)});
}
async function doQueueDelete(sheet:Sheet){
  // 单张图纸删除为低风险动作：danger:false、无需勾选；确认文案明确「加入删除草稿」，不是立即删除文件（SPEC-DM-009 §6.3）
  const ok=await confirmAction({title:t("shell.flows.deleteSheet.title"),message:t("shell.flows.deleteSheet.message",{number:sheet.number}),confirmText:t("shell.flows.deleteSheet.confirm"),danger:false});
  if(!ok)return;
  if(addCommand(createCommand.deleteSheet(sheet.id),"structural")){
    // 删除成功进入草稿：目标已从投影移除，结束对应编辑上下文，避免预览/写入被「未提交输入」误报
    editor.discardIfTargeting(sheet.id);
    pushToast({type:"ok",title:t("shell.flows.deleteSheet.toastTitle"),body:t("shell.flows.deleteSheet.toastBody",{number:sheet.number})});
  }
}
// 删除整个子集：目标取编辑子集表单的编辑对象；编辑未提交时先三选一决策（保存后再删除），
// 再走整子集删除确认流程。目标 ID 在 guard 前捕获——保存标题会关闭表单，删除仍作用于原目标。
async function queueDeleteSubset(){
  const ctx=editor.context.value;
  const subsetId=ctx?.kind==="rename"?ctx.objectId:"";
  await editor.guard(async()=>{await doQueueDeleteSubset(subsetId)});
}
async function doQueueDeleteSubset(subsetId:string){
  const subset=workspace.value?.sheet_set.subsets.find(item=>item.id===subsetId);
  if(!subset)return;
  const drawing=subset.sheets[0]?.layout.resolved_path??subset.sheets[0]?.layout.file_name??t("shell.flows.deleteSubset.unknownDrawing");
  // 删除整个子集属不可逆破坏类操作：需要显式勾选后才可确认
  const ok=await confirmAction({title:t("shell.flows.deleteSubset.title"),message:t("shell.flows.deleteSubset.message",{name:subset.display_name,count:subset.sheets.length,drawing}),confirmText:t("shell.flows.deleteSubset.confirm"),danger:true,requireCheckbox:true,reversibility:"irreversible"});
  if(!ok)return;
  if(addCommand(createCommand.deleteSubset(subset.id),"structural")){
    // 删除成功进入草稿：目标已从投影移除，结束对应「编辑子集」上下文，
    // 否则残留的失效上下文会在下一次预览/写入时被「未提交输入」误报（2026-09-10 用户反馈 bug1）
    editor.discardIfTargeting(subset.id);
    pushToast({type:"ok",title:t("shell.flows.deleteSubset.toastTitle"),body:t("shell.flows.deleteSubset.toastBody",{name:subset.display_name,count:subset.sheets.length})});
  }
}
// 批量加入草稿：与单行编辑共用一个活动编辑上下文，有未提交输入先三选一
function queueBulkSheetProperty(){
  void editor.guard(()=>doQueueBulkSheetProperty());
}
// 批量编辑（SPEC-DM-009 §4.2/§6.1）：遍历完整勾选集合（含未加载行，不隐式缩为当前可见行）；
// 逐张复制 custom_properties 后仅改指定名称，已删除对象按 ID 匹配不到自然不进入批量。
// 设置值模式空输入不生成修改只提示；清空值须显式选择并确认受影响数量（是否允许空值仍由服务端校验 S-11）。
async function doQueueBulkSheetProperty(){
  const name=bulkPropertyName.value;
  if(!name||!selectedIds.value.length){error.value=t("shell.errors.selectSheetAndProperty");return}
  const selected=new Set(selectedIds.value);
  const targets=allRows.value.filter(({sheet})=>selected.has(sheet.id));
  if(!targets.length){error.value=t("shell.errors.bulkTargetsUnavailable");return}
  if(bulkMode.value==="set"){
    if(!bulkPropertyValue.value.trim()){error.value=t("shell.errors.bulkEmptyValue");return}
    applyBulkBatch(targets,name,bulkPropertyValue.value,"set");
    return;
  }
  const affected=targets.filter(({sheet})=>(sheet.custom_properties[name]??"").trim()!=="");
  if(!affected.length){error.value=t("shell.errors.bulkAllEmpty",{name});return}
  const ok=await confirmAction({
    title:t("shell.flows.clearValues.title"),
    message:t("shell.flows.clearValues.message",{count:affected.length,name}),
    confirmText:t("shell.flows.clearValues.confirm"),danger:false,
  });
  if(!ok)return;
  applyBulkBatch(affected,name,"","clear"); // 只改实际受影响图纸，与确认数量一致
}
function applyBulkBatch(targets:{sheet:Sheet;subset:Subset}[],name:string,value:string,mode:"set"|"clear"){
  const batch=targets.map(({sheet})=>createCommand.updateSheetProperties(sheet.id,{...sheet.custom_properties,[name]:value}));
  const subsetCount=new Set(targets.map(({subset})=>subset.id)).size;
  const labelKey=mode==="set"?"shell.flows.bulk.setLabel":"shell.flows.bulk.clearLabel";
  const toastKey=mode==="set"?"shell.flows.bulk.setToast":"shell.flows.bulk.clearToast";
  // 草稿动作持久化 label_key + 命名参数（属性名与数量是用户数据，I18N-12）；显示文本由动作栈渲染期翻译
  if(addCommandBatch(batch,{key:labelKey,params:{name,count:batch.length}},"metadata")){
    // 连续批量编辑保留勾选集合与展开状态，只初始化本次属性输入。
    bulkMode.value="set";bulkPropertyName.value="";bulkPropertyValue.value="";
    pushToast({type:"ok",title:t("shell.flows.bulk.toastTitle"),body:t(toastKey,{name,count:batch.length,subsets:subsetCount})});
  }
}
// 删除属性定义（PLAN-DM-016 任务 4 / SPEC-DM-010 §4.2）：沿用既有草稿与确认语义；
// 目标 sheetset 值仍 dirty 时先运行属性输入 guard（三选一）再弹删除确认；空文本值不视为删除定义。
// 确认文案只说明作用域与草稿语义，不虚构级联影响数量；受影响范围以预览时服务端结果为准。
function queueDeleteProperty(definition:PropertyDefinition){void properties.guard(()=>doQueueDeleteProperty(definition))}
async function doQueueDeleteProperty(definition:PropertyDefinition){
  const scopeLabel=t(definition.type==="sheetset"?"shell.flows.deleteProperty.scopeSheetset":"shell.flows.deleteProperty.scopeSheet");
  const ok=await confirmAction({title:t("shell.flows.deleteProperty.title"),message:t("shell.flows.deleteProperty.message",{scope:scopeLabel,name:definition.name}),confirmText:t("shell.flows.deleteProperty.confirm"),danger:false});
  if(!ok)return;
  if(addCommand(createCommand.deleteCustomProperty(definition.type,definition.name),"property")){
    pushToast({type:"ok",title:t("shell.flows.deleteProperty.toastTitle"),body:t("shell.flows.deleteProperty.toastBody",{scope:scopeLabel,name:definition.name})});
  }
}
// 新增图纸/新建子集提交由 useSheetEditor 处理：参照对象 → ordinal 映射（commands.ts）、
// 原 command schema、成功定位与失败保留输入（任务 6），不在 App.vue 重复实现。

// 全局预览/确认写入：有未提交输入先三选一（图纸页与属性页依次过闸）；加入草稿使旧预览失效，不能静默忽略输入
async function showPreview(){
  await guardAllInputs(async()=>{await doShowPreview()});
}
async function doShowPreview(){
  if(isWorkspaceLoading.value||draftStale.value||!workspace.value||!commands.value.length)return;
  const workspaceId=workspace.value.id;
  const baseRevisionId=workspace.value.revision_id;
  const cadVersionSnapshot=cadVersion.value;
  const commandSnapshot=cloneJson(commands.value);
  const generation=++previewGeneration;
  preview.value=null;previewContext.value=null;isPreviewing.value=true;
  try{
    const result:Preview=await request(`/api/workspaces/${workspaceId}/changes/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId,commands:commandSnapshot,cad_version:cadVersionSnapshot})});
    if(generation!==previewGeneration||workspace.value?.id!==workspaceId||workspace.value.revision_id!==baseRevisionId)return;
    preview.value=result;previewContext.value={workspaceId,baseRevisionId,cadVersion:cadVersionSnapshot,commands:commandSnapshot,result};error.value="";openOverlay("prev");
  }
  catch(e){if(generation===previewGeneration)error.value=String(e)}
  finally{if(generation===previewGeneration)isPreviewing.value=false}
}
// 执行正式写入（Task 5：模态上移到 write()，execute 不再自行开模态）
async function execute(){
  const context=previewContext.value;
  if(!context||!context.result.executable)return;
  const current=workspace.value;
  if(isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId){invalidatePreview();error.value=t("shell.errors.previewContextStale");return}
  const generation=invalidateJobMonitor(false);
  try{
    const result:Job=await request(`/api/workspaces/${context.workspaceId}/changes/execute`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,commands:cloneJson(context.commands),cad_version:context.cadVersion,preview_digest:context.result.preview_digest})});
    if(!isCurrentJobGeneration(generation)||isWorkspaceLoading.value||workspace.value?.id!==context.workspaceId)return;
    setJob(result);if(result.status==="QUEUED"&&result.id)watchJob(result.id,context.workspaceId);else if(result.status==="SUCCEEDED"){await discardDraft();await refreshWorkspace(context.workspaceId)}
  }
  catch(e){if(isCurrentJobGeneration(generation)&&workspace.value?.id===context.workspaceId&&!isWorkspaceLoading.value)error.value=String(e)}
}

const dock=computed(()=>{ // ActionDock 门禁（SPEC-DM-006 §6.9 矩阵唯一出口）
  const taskRunning=isWorkspaceLoading.value||isRestoreExecuting.value||Boolean(job.value&&!terminal(job.value.status));
  const base={commandCount:commands.value.length,actions:draftActions.value,cursor:draftCursor.value,stale:draftStale.value,staleReasons:draftStaleReasons.value,corrupted:draftCorrupted.value,saveStatusText:saveStatusText.value,saveFailed:draftSaveFailed.value,previewing:isPreviewing.value,writesDisabled:taskRunning||repairWritesDisabled.value};
  if(taskRunning)return{...base,canPreview:false,canWrite:false,writeDisabledReason:t("shell.dock.reasonTaskRunning"),writeNeedsModal:false};
  if(job.value?.status==="NEEDS_REVIEW")return{...base,canPreview:false,canWrite:false,writeDisabledReason:t("shell.dock.reasonNeedsReview"),writeNeedsModal:false}; // 终态但需人工检查：dst_validation 是加载快照仅 SUCCEEDED 刷新，须独立锁定（§6.9 行）
  const status=dstValidation.value?.status??"VALID";
  if(status!=="VALID")return{...base,canPreview:false,canWrite:false,writeDisabledReason:status==="REPAIRED"?t("shell.dock.reasonRepaired"):status==="INVALID_UNRECOVERABLE"?t("shell.dock.reasonUnrecoverable"):t("shell.dock.reasonNeedsRepair"),writeNeedsModal:false};
  if(!commands.value.length)return{...base,canPreview:false,canWrite:false,writeDisabledReason:t("shell.dock.reasonNoChanges"),writeNeedsModal:false};
  const context=previewContext.value;
  if(!context)return{...base,canPreview:true,canWrite:false,writeDisabledReason:t("shell.dock.reasonPreviewFirst"),writeNeedsModal:false};
  if(context.workspaceId!==workspace.value?.id||context.baseRevisionId!==workspace.value?.revision_id)return{...base,canPreview:true,canWrite:false,writeDisabledReason:t("shell.dock.reasonPreviewStale"),writeNeedsModal:false};
  if(context.result.executable===false)return{...base,canPreview:true,canWrite:false,writeDisabledReason:t("shell.dock.reasonNotExecutable"),writeNeedsModal:false};
  return{...base,canPreview:true,canWrite:true,writeDisabledReason:"",writeNeedsModal:true};
});
// write 不能捕获旧 context 后在保存继续时执行：guard 保存后 previewContext 已失效，必须重新预览
async function write(){
  await guardAllInputs(async()=>{await doWrite()});
}
async function doWrite(){
  const context=previewContext.value;
  if(!context||context.result.executable===false)return;
  if(await confirmAction({title:t("shell.flows.publish.title"),message:t("shell.flows.publish.message"),impactLines:context.result.affected_files,confirmText:t("shell.flows.publish.confirm"),danger:true,requireCheckbox:true,reversibility:"irreversible"}))await execute();
}
// 全局快捷键（SPEC-DM-006 §7.1）：Ctrl+S 只在 writeNeedsModal 时开模态，否则给非阻断提示（Task 7 toast 前用既有 error）
useHotkeys({
  open:()=>{if(workspace.value){error.value=t("shell.errors.closeFirst");return}if(hasShell.value)void selectAndOpenDst();else(document.querySelector<HTMLInputElement>(".no-shell input"))?.focus()},
  preview:()=>{if(dock.value.canPreview)void showPreview();else error.value=dock.value.writeDisabledReason||t("shell.dock.reasonPreviewUnavailable")},
  write:()=>{if(dock.value.writeNeedsModal)void write();else error.value=dock.value.writeDisabledReason||t("shell.dock.reasonWriteUnavailable")},
  undo:()=>undoDraft(),
  redo:()=>redoDraft(),
});

</script>

<template>
  <TopBar :sheet-set-name="sheetSetName" :dst-path="dstPath" :dst-status="dstStatus" :cad-version="cadVersion" :close-disabled="isRestoreExecuting||isRepairExecuting" :has-shell="hasShell" :workspace-id="workspace?.id ?? ''" @update:cadVersion="onCadVersionChange" @close="closeWorkspace" @open-folder="openFolder" @open-settings="openSettings" />
  <div class="shell-body">
    <main class="shell-main" :class="{'sheets-active': Boolean(workspace) && active === 'sheets'}">
      <p v-if="error" class="error notice">{{error}}</p>
      <!-- PLAN-DM-021 Task 9（I18N-11）：未知错误的原始文本只在可展开诊断详情呈现 -->
      <details v-if="error && lastErrorDiagnostic" class="error notice"><summary>{{ $t("errors.ui.diagnosticsDetails") }}</summary><pre class="error-raw">{{ lastErrorDiagnostic }}</pre></details>
      <p v-if="isWorkspaceLoading" class="panel loading" role="status">{{ $t("shell.workspace.loading") }}</p>
      <p v-if="isRestoreExecuting" class="panel loading" role="status">{{ $t("shell.workspace.restoring") }}</p>
      <template v-if="!workspace">
        <WelcomeView :has-shell="hasShell" @select="selectAndOpenDst" @submit-path="openByPath" />
      </template>
      <template v-else>
        <TabBar :descriptors="tabDescriptors" :active="active" @select="selectTab" @keydown="onTabKeydown" />
        <div v-if="draftRecovered!==null&&draftRecovered>0&&!isWorkspaceLoading" class="recover-banner" role="status">{{ $t("shell.workspace.recoveredBanner",{count:draftRecovered},draftRecovered) }}<button @click="draftRecovered=null">{{ $t("shell.workspace.resume") }}</button><button @click="clearDraftRestart">{{ $t("shell.workspace.restart") }}</button></div>
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
    </main>
    <TaskOverlay v-if="workspace" :open="overlayOpen" :tab="overlayTab" :has-blocking="blocking.length>0" :has-repair="Boolean(dstValidation&&dstValidation.status!=='VALID')" :job="job" :connection-mode="connectionMode" :preview="preview" :semantic-diff="semanticDiff" :estimate="executionEstimate" :cad-validation-deferred="cadValidationDeferred" :cardinality-frontier="cardinalityFrontier" :subset-operations="subsetOperations" :source-baselines="sourceBaselines" :derived-subsets="derivedSubsets" :groups="previewGroups" :diagnostics="workspace.diagnostics" :dst-validation="dstValidation" :repair-preview="repairPreview" :is-repair-previewing="isRepairPreviewing" :is-repair-executing="isRepairExecuting" @update:tab="overlayTab=$event" @fold="overlayOpen=!overlayOpen" @retry="retryJob" @preview-repair="previewRepair" @execute-repair="executeRepair" @cancel-repair="repairPreview=null;repairContext=null" />
  </div>
  <ActionDock v-if="workspace" v-bind="dock" @preview="showPreview" @write="write" @undo="undoDraft" @redo="redoDraft" @clear="clearCommands" @remove="removeDraftAction" @discard="discardDraft" @reload-conflict="reloadAfterDraftConflict" @retry-save="scheduleDraftSave" />
  <ConfirmModal v-bind="confirmState" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />
  <SettingsDialog :open="settingsOpen" :push-toast="pushToast" :extensions-panel="extensionsPanel" @close="settingsOpen=false" />
  <!-- 唯一共享三选一模态：图纸页与属性页 guard 顺序开合同一实例，状态取当前打开者 -->
  <UnsavedInputDialog v-bind="sharedGuardState" @save-and-continue="resolveSharedGuard('save')" @discard="resolveSharedGuard('discard')" @stay="resolveSharedGuard('stay')" />
  <ToastHost :toasts="toasts" @dismiss="dismiss" @jump="jumpOverlay" />
</template>

<style scoped>
.shell-body{display:flex;align-items:stretch;height:calc(100vh - 104px);min-height:0}
.shell-main{display:flex;flex-direction:column;gap:var(--space-3);flex:1;min-width:0;min-height:0;max-width:none;margin:0;padding:var(--space-5);overflow:auto}
.shell-main.sheets-active{overflow:hidden}
</style>

