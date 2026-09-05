<script setup lang="ts">
import {computed,reactive,ref,watch} from "vue";
import {ApiError,request} from "./api/client";
import {clearWorkspaceContext,getShellBridge,shellReady,openWorkspaceFolder as bridgeOpenWorkspaceFolder,DST_FILE_FILTERS,TEMPLATE_FILE_FILTERS} from "./api/shell";
import {createCommand} from "./api/contracts";
import type {ChangeCommand,DraftAction,DraftEnvelope,Job,Preview,PropertyDefinition,PropertyType,Revision,SemanticDiff,Sheet,Workspace} from "./api/contracts";
import {projectCommands,projectWorkspace} from "./drafts";
import type {InsertSheetEditContext, InsertSubsetEditContext, SubmitResult} from "./features/sheets/types";
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
import type {OperationKind} from "./components/sheets/SheetToolbar.vue";
import UnsavedInputDialog from "./components/sheets/UnsavedInputDialog.vue";
import {useConfirm} from "./composables/useConfirm";
import {useToast} from "./composables/useToast";
import ConfirmModal from "./components/ui/ConfirmModal.vue";
import ToastHost from "./components/ui/ToastHost.vue";
import TopBar from "./layout/TopBar.vue";
import TabBar from "./layout/TabBar.vue";
import ActionDock from "./layout/ActionDock.vue";
import TaskOverlay from "./layout/TaskOverlay.vue";
import {useHotkeys} from "./composables/useHotkeys";
import WelcomeView from "./views/WelcomeView.vue";
import SheetsView from "./views/SheetsView.vue";
import PropertiesView from "./views/PropertiesView.vue";
import RevisionsView from "./views/RevisionsView.vue";

type PreviewContext={workspaceId:string;baseRevisionId:string;cadVersion:string;commands:ChangeCommand[];result:Preview};

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
// 只读 projection 由 watch 应用到显示 workspace；stamp/pending/error 供后续任务消费。
const {projection:sheetProjection,stamp:sheetProjectionStamp,refresh:refreshSheetProjection}=useSheetProjection({workspace,baseWorkspace,commands,cadVersion});
watch(sheetProjection,(value)=>{if(value)workspace.value=value});
// 固定标签栏状态（SPEC-DM-006 §7.2）：active/select/onKeydown 由 useShellTabs 提供，TabBar 为受控组件
const {active,select,onKeydown}=useShellTabs<string>(["sheets","properties","revisions"],"sheets");
const projectPath=computed(()=>workspace.value?.dst_path??"");
const dstStatus=computed(()=>workspace.value?.dst_validation?.status??"");
function selectTab(id:string){select(id);if(id==="revisions")void loadRevisions()}
function onTabKeydown(e:KeyboardEvent){const before=active.value;onKeydown(e);if(active.value!==before&&active.value==="revisions")void loadRevisions()}
// 恢复预览成功（restorePreview 已写入）后展开任务浮层到修改预览页签，与 showPreview 共用 §9.1 统一预览门禁呈现
async function previewRestoreAndOpen(revision:Revision){await previewRestore(revision);if(restorePreview.value)openOverlay("prev")}
function onCadVersionChange(value:string){cadVersion.value=value;layoutReadGeneration+=1;invalidatePreview()}
const bulkPropertyName=ref("");
const bulkPropertyValue=ref("");
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
  void editor.guard(()=>doOpenOperation(kind));
}
function doOpenOperation(kind:OperationKind){
  const currentCtx=editor.context.value;
  if(currentCtx?.kind===kind)return; // 同一表单已打开：不重开
  if(!workspace.value)return;
  const targetId=sheets.scope.value.kind==="subset"?sheets.scope.value.id:"";
  if(kind==="rename")editor.openRename(targetId);
  else if(kind==="insert-sheet")editor.openInsertSheet(targetId);
  else if(kind==="insert-subset")editor.openInsertSubset();
}
let previewGeneration=0;
let draftSaveQueue:Promise<void>=Promise.resolve();

const propertyForm=reactive<{type:PropertyType;name:string;defaultValue:string}>({type:"sheet",name:"",defaultValue:""});
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
const saveStatusText=computed(()=>draftSaveFailed.value?"保存失败":draftSaving.value?"保存中":draftStale.value?"草稿已过期":"已保存");
// —— 提交命令（SubmitCommands）：加入草稿动作并等待持久化与投影成功，不以入队即宣称保存 ——
async function submitCommands(commands:ChangeCommand[],label:string,category:"metadata"|"structural"):Promise<SubmitResult>{
  if(draftStale.value)return{ok:false,message:"草稿已过期，必须丢弃或重新打开后手工重做"};
  // 结构变更与属性定义变更必须分批；属性值编辑（metadata）可与结构并存（混合批次显示由命令簿叠加合成）
  if(category==="structural"&&hasPropertyDefinitionCommands.value)return{ok:false,message:"属性定义与结构变更必须分批预览和执行"};
  // 草稿保存失败重试：与最后一条草稿动作等价时不重复加入同一命令批次，仅重试保存
  const last=draftActions.value[draftActions.value.length-1];
  const sameBatch=last?.kind==="command_batch"&&JSON.stringify(last.commands)===JSON.stringify(commands);
  if(!sameBatch){if(!addCommandBatch(commands,label,category))return{ok:false,message:error.value||"加入草稿失败"}}
  else scheduleDraftSave();
  await draftSaveQueue;
  if(draftSaveFailed.value)return{ok:false,message:lastDraftError.value?.message??"草稿保存失败",fields:lastDraftError.value?.fields};
  const projection=await refreshSheetProjection();
  if(!projection.ok)return projection;
  return{ok:true};
}
// —— 分页编辑缓冲与全局输入保护（PLAN-DM-015 任务 5）：唯一活动编辑上下文，跨主标签保留 ——
const editor=useSheetEditor({
  workspace,baseWorkspace,commands,sheetPropertyNames,projectionStamp:sheetProjectionStamp,
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

function cloneJson<T>(value:T):T{return JSON.parse(JSON.stringify(value))}
function invalidatePreview(){previewGeneration+=1;preview.value=null;previewContext.value=null}
function resetEditingState(){commands.value=[];invalidatePreview();invalidateCsvPreview(true);error.value=""}
function resetDraftState(){draftActions.value=[];draftCursor.value=0;draftVersion.value=0;draftStale.value=false;draftStaleReasons.value=[];draftCorrupted.value=false;draftSaveFailed.value=false;draftSaving.value=false;draftRecovered.value=null}
function beginWorkspaceLoad(){workspaceLoadGeneration.value+=1;isWorkspaceLoading.value=true;resetEditingState();resetDraftState();invalidateRevisionState();overlayOpen.value=false;overlayTab.value="prog";return workspaceLoadGeneration.value}
async function openByPath(path:string){
  if(isRestoreExecuting.value){error.value="修订恢复正在执行，请稍候";return}
  isWorkspaceLoading.value=true;
  await draftSaveQueue;
  if(draftSaveFailed.value){isWorkspaceLoading.value=false;return}
  invalidateJobMonitor(true);
  const generation=beginWorkspaceLoad();
  try{
    const loaded:Workspace=await request("/api/workspaces/open",{method:"POST",body:JSON.stringify({dst_path:path})});
    if(generation!==workspaceLoadGeneration.value)return;
    resetEditingState();baseWorkspace.value=cloneJson(loaded);workspace.value=cloneJson(loaded);resetSheetsWorkspace();await loadDraft(loaded);isWorkspaceLoading.value=false;
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
  if(!result){error.value="当前桌面壳不支持打开图纸集所在文件夹";return}
  if(!result.ok)error.value=result.code==="SHELL_WORKSPACE_UNAVAILABLE"?"工作区已切换或未打开，请重新打开":result.message;
}
const DST_EXT=/\.dst$/i;
const DROP_CALLBACK_ID="__dstManagerAcceptDst";
async function acceptDstPath(path:string){
  if(workspace.value){error.value="请先关闭当前工作区，再打开新的 DST 文件";return}
  if(!DST_EXT.test(path)){error.value="仅支持 DST 文件";return}
  await openByPath(path);
}
async function selectAndOpenDst(){
  const bridge=getShellBridge();
  if(!bridge){error.value="桌面壳未就绪，请通过 dst-manager desktop 启动";return}
  const path=await bridge.select_file(DST_FILE_FILTERS);
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
    ctx.layoutError=e instanceof ApiError?e.message:"读取布局失败";ctx.layoutManual=true;
  }finally{
    if(gen===layoutReadGeneration&&editor.context.value===ctx)ctx.layoutLoading=false;
  }
}
async function selectTemplateFile(){
  const bridge=getShellBridge();
  if(!bridge){error.value="桌面壳未就绪";return}
  const path=await bridge.select_file(TEMPLATE_FILE_FILTERS);
  if(!path)return;
  if(!DWG_DWT_EXT.test(path)){error.value="仅支持 .dwg/.dwt 模板文件";return}
  const ctx=activeLayoutContext("insert-sheet");
  if(!ctx)return;
  ctx.sourceFile=path;ctx.layoutError="";ctx.layoutManual=false;ctx.dirty=true;
  await loadLayoutOptions(path,ctx);
}
async function selectSubsetTemplateFile(){
  const bridge=getShellBridge();
  if(!bridge){error.value="桌面壳未就绪";return}
  const path=await bridge.select_file(TEMPLATE_FILE_FILTERS);
  if(!path)return;
  if(!DWG_DWT_EXT.test(path)){error.value="仅支持 .dwg/.dwt 模板文件";return}
  // 与新增图纸对齐：选文件后读取布局列表（缓存优先），下拉选择布局名称
  const ctx=activeLayoutContext("insert-subset");
  if(!ctx)return;
  ctx.templateFile=path;ctx.layoutError="";ctx.layoutManual=false;ctx.dirty=true;
  await loadLayoutOptions(path,ctx);
}
async function selectBaseTemplateFile(){
  const bridge=getShellBridge();
  if(!bridge){error.value="桌面壳未就绪";return}
  const path=await bridge.select_file(TEMPLATE_FILE_FILTERS);
  if(!path)return;
  if(!DWG_DWT_EXT.test(path)){error.value="仅支持 .dwg/.dwt 模板文件";return}
  const ctx=activeLayoutContext("insert-subset");
  if(!ctx)return;
  ctx.baseTemplateFile=path;ctx.dirty=true;
}
// 关闭工作区：先接未提交输入保护（三选一），再纳入现有关闭确认，不静默丢弃
async function closeWorkspace(){
  await editor.guard(async()=>{await doCloseWorkspace()});
}
async function doCloseWorkspace(){
  const pending=draftActions.value.length>0||draftSaveFailed.value||draftStale.value;
  if(pending){
    // 关闭工作区属于不可逆破坏类操作：需要显式勾选后才可确认
    const ok=await confirmAction({title:"关闭工作区",message:"存在未发布完毕的改动。改动已自动保存，重新打开同一 DST 可继续处理。确定关闭并放弃当前改动？",confirmText:"确定关闭并放弃当前改动",danger:true,requireCheckbox:true,reversibility:"不可逆"});
    if(!ok)return;
    await discardDraft();
  }
  const closedId=workspace.value?.id;
  // 推进加载代次：关闭后迟到的打开/刷新/修订响应全部按代次失效，防止复活工作区
  workspaceLoadGeneration.value+=1;isWorkspaceLoading.value=false;resetDraftState();resetEditingState();editor.reset();baseWorkspace.value=null;workspace.value=null;invalidateJobMonitor(true);invalidateRevisionState();overlayOpen.value=false;overlayTab.value="prog";
  // 关闭成功清空服务端可信上下文（best-effort：旧 ID 的迟到清除请求由服务端按上下文匹配拒绝，不影响新工作区）
  if(closedId)void clearWorkspaceContext(closedId);
  // 重置图纸页工作区状态；操作表单/编辑缓冲状态已由 editor.reset() 清空，旧模板路径不残留
  resetSheetsWorkspace();layoutReadGeneration+=1;
}
async function refreshWorkspace(expectedWorkspaceId?:string){
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
  if(result.corrupted)error.value="检测到损坏草稿，已隔离；可安全重新开始编辑";
  else if(result.stale)error.value="草稿基准或修复状态已变化；仅可查看旧意图、手工重做或丢弃，禁止自动 rebase";
}
function commandLabel(command:ChangeCommand){
  const labels:Record<ChangeCommand["type"],string>={update_sheet_set:"更新图纸集",update_subset_title:"更新子集标题",update_sheet_properties:"更新图纸属性",delete_sheet:"删除图纸",insert_sheet:"新增图纸",insert_subset:"新建子集",add_custom_property:"新增属性定义",delete_custom_property:"删除属性定义",delete_subset:"删除子集"};
  return labels[command.type];
}
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
    catch(e){if(workspace.value?.id===workspaceId&&e instanceof ApiError&&e.code==="DRAFT_CONFLICT"){draftSaveFailed.value=true;lastDraftError.value=e;draftStale.value=true;draftStaleReasons.value=["DRAFT_VERSION_CONFLICT"];commands.value=[];invalidatePreview();error.value="草稿已在其他窗口更新；当前窗口禁止覆盖，请重新打开工作区"}else throw e}
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
  try{await request(`/api/workspaces/${current.id}/draft`,{method:"DELETE",body:JSON.stringify({expected_version:draftVersion.value})})}catch(e){if(e instanceof ApiError&&e.code==="DRAFT_CONFLICT"){draftStale.value=true;draftStaleReasons.value=["DRAFT_VERSION_CONFLICT"];error.value="草稿已在其他窗口更新，未删除较新版本；请重新打开工作区";return}throw e}
  resetDraftState();rebuildDraftProjection();
}
async function reloadAfterDraftConflict(){
  const current=workspace.value;if(!current||!draftStaleReasons.value.includes("DRAFT_VERSION_CONFLICT"))return;
  // 丢弃本地冲突动作并重新读取较新草稿：不改变服务器数据，属低风险动作（danger:false、无需勾选）
  const ok=await confirmAction({title:"放弃冲突动作并重新加载",message:"将放弃当前窗口未保存的冲突动作，并重新读取服务器上的较新草稿。是否继续？",confirmText:"确定放弃冲突动作并重新加载",danger:false});
  if(!ok)return;
  draftSaveFailed.value=false;
  await refreshWorkspace(current.id);
}
function addCommand(command:ChangeCommand,category:"property"|"structural"|"metadata"){
  if(draftStale.value){error.value="草稿已过期，必须丢弃或重新打开后手工重做";return false}
  if(category==="property"&&hasStructuralCommands.value){error.value="属性定义与结构变更必须分批预览和执行";return false}
  if(category==="structural"&&hasPropertyDefinitionCommands.value){error.value="属性定义与结构变更必须分批预览和执行";return false}
  draftActions.value=draftActions.value.slice(0,draftCursor.value);
  draftActions.value.push({id:crypto.randomUUID(),kind:"command_batch",label:commandLabel(command),commands:[command]});
  draftCursor.value=draftActions.value.length;rebuildDraftProjection();scheduleDraftSave();error.value="";return true;
}
function addCommandBatch(batch:ChangeCommand[],label:string,category:"property"|"structural"|"metadata"){
  if(!batch.length)return false;
  if(draftStale.value){error.value="草稿已过期，必须丢弃或重新打开后手工重做";return false}
  if(category==="property"&&hasStructuralCommands.value){error.value="属性定义与结构变更必须分批预览和执行";return false}
  if(category==="structural"&&hasPropertyDefinitionCommands.value){error.value="属性定义与结构变更必须分批预览和执行";return false}
  draftActions.value=draftActions.value.slice(0,draftCursor.value);
  draftActions.value.push({id:crypto.randomUUID(),kind:"command_batch",label,commands:batch});
  draftCursor.value=draftActions.value.length;rebuildDraftProjection();scheduleDraftSave();error.value="";return true;
}
function queueSheetSet(){if(!workspace.value)return;if(!workspace.value.sheet_set.name.trim()){error.value="图纸集名称不能为空";return}addCommand(createCommand.updateSheetSet(workspace.value.sheet_set.name,{...workspace.value.sheet_set.custom_properties}),"metadata")}
async function queueDelete(sheet:Sheet){
  // 编辑未提交时先处理缓冲（三选一），再按删除确认流程；删除命令不得夹带未确认的属性变更
  await editor.guard(async()=>{await doQueueDelete(sheet)});
}
async function doQueueDelete(sheet:Sheet){
  // 单张图纸删除为低风险动作：danger:false、无需勾选
  const ok=await confirmAction({title:"删除图纸",message:`删除图纸 ${sheet.number}？`,confirmText:"确认删除",danger:false});
  if(!ok)return;
  addCommand(createCommand.deleteSheet(sheet.id),"structural");
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
  const drawing=subset.sheets[0]?.layout.resolved_path??subset.sheets[0]?.layout.file_name??"（未知主 DWG）";
  // 删除整个子集属不可逆破坏类操作：需要显式勾选后才可确认
  const ok=await confirmAction({title:"删除整个子集",message:`删除整个子集“${subset.display_name}”、其中 ${subset.sheets.length} 张图纸及主 DWG：${drawing}？\n系统不会证明工程外部引用，确认后由用户承担外部影响。`,confirmText:"确定删除整个子集",danger:true,requireCheckbox:true,reversibility:"不可逆"});
  if(!ok)return;
  addCommand(createCommand.deleteSubset(subset.id),"structural");
}
// 批量加入草稿：与单行编辑共用一个活动编辑上下文，有未提交输入先三选一
function queueBulkSheetProperty(){
  void editor.guard(()=>doQueueBulkSheetProperty());
}
function doQueueBulkSheetProperty(){
  const name=bulkPropertyName.value;
  if(!name||!selectedIds.value.length){error.value="请选择图纸和既有图纸属性";return}
  const selected=new Set(selectedIds.value);
  const batch=allRows.value.filter(({sheet})=>selected.has(sheet.id)).map(({sheet})=>createCommand.updateSheetProperties(sheet.id,{...sheet.custom_properties,[name]:bulkPropertyValue.value}));
  if(addCommandBatch(batch,`批量更新 ${name}（${batch.length} 张）`,"metadata")){clearSelection();bulkPropertyName.value="";bulkPropertyValue.value=""}
}
function queuePropertyDefinition(){
  const name=propertyForm.name.trim();if(!name){error.value="属性名称不能为空";return}
  if(addCommand(createCommand.addCustomProperty(propertyForm.type,name,propertyForm.defaultValue),"property")){propertyForm.name="";propertyForm.defaultValue=""}
}
function queueDeleteProperty(definition:PropertyDefinition){addCommand(createCommand.deleteCustomProperty(definition.type,definition.name),"property")}
// 新增图纸/新建子集提交由 useSheetEditor 处理：参照对象 → ordinal 映射（commands.ts）、
// 原 command schema、成功定位与失败保留输入（任务 6），不在 App.vue 重复实现。

// 全局预览/确认写入：有未提交输入先三选一；加入草稿使旧预览失效，不能静默忽略输入
async function showPreview(){
  await editor.guard(async()=>{await doShowPreview()});
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
  if(isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId){invalidatePreview();error.value="工作区或基准修订已变化，请重新预览";return}
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
  if(taskRunning)return{...base,canPreview:false,canWrite:false,writeDisabledReason:"任务进行中",writeNeedsModal:false};
  if(job.value?.status==="NEEDS_REVIEW")return{...base,canPreview:false,canWrite:false,writeDisabledReason:"需人工检查，禁止直接重试",writeNeedsModal:false}; // 终态但需人工检查：dst_validation 是加载快照仅 SUCCEEDED 刷新，须独立锁定（§6.9 行）
  const status=dstValidation.value?.status??"VALID";
  if(status!=="VALID")return{...base,canPreview:false,canWrite:false,writeDisabledReason:status==="REPAIRED"?"存在待确认修复":status==="INVALID_UNRECOVERABLE"?"不可恢复":"需先修复",writeNeedsModal:false};
  if(!commands.value.length)return{...base,canPreview:false,canWrite:false,writeDisabledReason:"没有待发布变更",writeNeedsModal:false};
  const context=previewContext.value;
  if(!context)return{...base,canPreview:true,canWrite:false,writeDisabledReason:"请先预览",writeNeedsModal:false};
  if(context.workspaceId!==workspace.value?.id||context.baseRevisionId!==workspace.value?.revision_id)return{...base,canPreview:true,canWrite:false,writeDisabledReason:"预览已失效，请重新预览",writeNeedsModal:false};
  if(context.result.executable===false)return{...base,canPreview:true,canWrite:false,writeDisabledReason:"预览不可执行",writeNeedsModal:false};
  return{...base,canPreview:true,canWrite:true,writeDisabledReason:"",writeNeedsModal:true};
});
// write 不能捕获旧 context 后在保存继续时执行：guard 保存后 previewContext 已失效，必须重新预览
async function write(){
  await editor.guard(async()=>{await doWrite()});
}
async function doWrite(){
  const context=previewContext.value;
  if(!context||context.result.executable===false)return;
  if(await confirmAction({title:"确认发布",message:"原 DST 和受影响 DWG 将永久备份。",impactLines:context.result.affected_files,confirmText:"确认发布（原 DST 与受影响 DWG 永久备份）",danger:true,requireCheckbox:true,reversibility:"不可逆"}))await execute();
}
// 全局快捷键（SPEC-DM-006 §7.1）：Ctrl+S 只在 writeNeedsModal 时开模态，否则给非阻断提示（Task 7 toast 前用既有 error）
useHotkeys({
  open:()=>{if(workspace.value){error.value="请先关闭当前工作区，再打开新的 DST 文件";return}if(hasShell.value)void selectAndOpenDst();else(document.querySelector<HTMLInputElement>(".no-shell input"))?.focus()},
  preview:()=>{if(dock.value.canPreview)void showPreview();else error.value=dock.value.writeDisabledReason||"当前状态不可预览"},
  write:()=>{if(dock.value.writeNeedsModal)void write();else error.value=dock.value.writeDisabledReason||"当前状态不可写入"},
  undo:()=>undoDraft(),
  redo:()=>redoDraft(),
});

</script>

<template>
  <TopBar :project-path="projectPath" :dst-status="dstStatus" :cad-version="cadVersion" :close-disabled="isRestoreExecuting||isRepairExecuting" :has-shell="hasShell" :workspace-id="workspace?.id ?? ''" @update:cadVersion="onCadVersionChange" @close="closeWorkspace" @open-folder="openFolder" />
  <div class="shell-body">
    <main class="shell-main">
      <p v-if="error" class="error notice">{{error}}</p>
      <p v-if="isWorkspaceLoading" class="panel loading" role="status">正在加载工作区…</p>
      <p v-if="isRestoreExecuting" class="panel loading" role="status">正在恢复修订…</p>
      <template v-if="!workspace">
        <WelcomeView :has-shell="hasShell" @select="selectAndOpenDst" @submit-path="openByPath" />
      </template>
      <template v-else>
        <TabBar :active="active" :revisions-disabled="isRestoreExecuting||isWorkspaceLoading" @select="selectTab" @keydown="onTabKeydown" />
        <div v-if="draftRecovered!==null&&draftRecovered>0&&!isWorkspaceLoading" class="recover-banner" role="status">已恢复上次未完成的改动（{{draftRecovered}} 条待处理）<button @click="draftRecovered=null">继续</button><button @click="clearDraftRestart">清空重来</button></div>
        <SheetsView v-if="active==='sheets'&&!isWorkspaceLoading&&!isRestoreExecuting" :workspace="workspace" :scope="scope" :focused-sheet-id="focusedSheetId" :selected-ids="selectedIds" :filtered-rows="filteredRows" :visible-rows="visibleRows" :hidden-selected-count="hiddenSelectedCount" :all-filtered-selected="allFilteredSelected" :hidden-target="hiddenTarget" :prune-message="pruneMessage" :scope-total="scopeTotal" :all-total="allTotal" :range-total="rangeTotal" :pending-sheet-ids="pendingSheetIds" :diagnostic-object-ids="diagnosticObjectIds" :sheet-property-names="sheetPropertyNames" :visible-columns="visibleColumns" :column-options="columnOptions" :new-property-count="newPropertyCount" :column-save-error="columnSaveError" :edit-context="editor.context.value" :search-text="searchText" :search-all="searchAll" v-model:filters-visible="filtersVisible" :path-filter="pathFilter" :diagnostic-filter="diagnosticFilter" :pending-filter="pendingFilter" v-model:render-limit="renderLimit" v-model:bulk-property-name="bulkPropertyName" v-model:bulk-property-value="bulkPropertyValue" @update:search-text="guardedSearchText" @update:search-all="guardedSearchAll" @update:path-filter="guardedPathFilter" @update:diagnostic-filter="guardedDiagnosticFilter" @update:pending-filter="guardedPendingFilter" @select-all="() => runScopeChange(() => sheetsSelectAll())" @select-subset="(id) => runScopeChange(() => sheetsSelectSubset(id))" @select-sheet="(id) => runScopeChange(() => locateSheet(id))" @toggle-filtered-selection="toggleFilteredSelection" @clear-selection="clearSelection" @clear-filters="clearFilters" @toggle-sheet="toggleSheet" @edit-sheet="onEditSheet" @delete-sheet="queueDelete" @editor-set-value="editor.setFieldValue" @editor-set-page="editor.setPage" @editor-set-search="editor.setSearch" @editor-submit="() => void editor.submit()" @editor-cancel="editor.cancel" @editor-jump-error="editor.jumpToError" @queue-bulk-sheet-property="queueBulkSheetProperty" @open-operation="openOperation" @operation-submit="() => void editor.submit()" @operation-cancel="editor.cancel" @operation-delete-subset="queueDeleteSubset" @select-template-file="selectTemplateFile" @select-subset-template-file="selectSubsetTemplateFile" @select-base-template-file="selectBaseTemplateFile" @toggle-builtin="setBuiltin" @toggle-property="setProperty" @reset-columns="resetColumns" @open-diagnostics="() => openOverlay('diag')" />
        <PropertiesView v-if="active==='properties'&&!isWorkspaceLoading&&!isRestoreExecuting" :workspace="workspace" :property-form="propertyForm" :has-csv="Boolean(csvText)" :csv-preview="csvPreview" :csv-executable="Boolean(csvPreviewContext?.result.executable)" :repair-writes-disabled="repairWritesDisabled" @queue-sheet-set="queueSheetSet" @queue-property-definition="queuePropertyDefinition" @queue-delete-property="queueDeleteProperty" @read-csv="readCsvFile" @preview-csv="previewCsv" @import-csv="importCsv" />
        <RevisionsView v-if="active==='revisions'" :revisions="revisions" :restore-preview="restorePreview" :executing="isRestoreExecuting" :is-workspace-loading="isWorkspaceLoading" @preview="previewRestoreAndOpen" @restore="restoreRevision" />
      </template>
    </main>
    <TaskOverlay v-if="workspace" :open="overlayOpen" :tab="overlayTab" :has-blocking="blocking.length>0" :has-repair="Boolean(dstValidation&&dstValidation.status!=='VALID')" :job="job" :connection-mode="connectionMode" :preview="preview" :semantic-diff="semanticDiff" :estimate="executionEstimate" :cad-validation-deferred="cadValidationDeferred" :cardinality-frontier="cardinalityFrontier" :subset-operations="subsetOperations" :source-baselines="sourceBaselines" :derived-subsets="derivedSubsets" :groups="previewGroups" :diagnostics="workspace.diagnostics" :dst-validation="dstValidation" :repair-preview="repairPreview" :is-repair-previewing="isRepairPreviewing" :is-repair-executing="isRepairExecuting" @update:tab="overlayTab=$event" @fold="overlayOpen=!overlayOpen" @retry="retryJob" @preview-repair="previewRepair" @execute-repair="executeRepair" @cancel-repair="repairPreview=null;repairContext=null" />
  </div>
  <ActionDock v-if="workspace" v-bind="dock" @preview="showPreview" @write="write" @undo="undoDraft" @redo="redoDraft" @clear="clearCommands" @remove="removeDraftAction" @discard="discardDraft" @reload-conflict="reloadAfterDraftConflict" @retry-save="scheduleDraftSave" />
  <ConfirmModal v-bind="confirmState" @confirm="resolveConfirm(true)" @cancel="resolveConfirm(false)" />
  <UnsavedInputDialog v-bind="editor.guardState.value" @save-and-continue="editor.resolveGuard('save')" @discard="editor.resolveGuard('discard')" @stay="editor.resolveGuard('stay')" />
  <ToastHost :toasts="toasts" @dismiss="dismiss" @jump="jumpOverlay" />
</template>

<style scoped>
.shell-body{display:flex;align-items:stretch;min-height:calc(100vh - 104px)}
.shell-main{display:flex;flex-direction:column;gap:var(--space-3);flex:1;min-width:0;max-width:none;margin:0;padding:var(--space-5)}
</style>

