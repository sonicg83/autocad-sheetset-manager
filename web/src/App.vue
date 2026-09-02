<script setup lang="ts">
import {computed,reactive,ref} from "vue";
import {ApiError,request} from "./api/client";
import {getShellBridge,DST_FILE_FILTERS} from "./api/shell";
import {createCommand} from "./api/contracts";
import type {ChangeCommand,CsvPreview,DraftAction,DraftEnvelope,Job,LayoutSourceType,Placement,Preview,PropertyDefinition,PropertyType,RepairPreview,RestorePreview,Revision,SemanticDiff,Sheet,Workspace} from "./api/contracts";
import {projectCommands,projectWorkspace} from "./drafts";
import DraftActionsPanel from "./components/DraftActionsPanel.vue";
import JobStatusPanel from "./components/JobStatusPanel.vue";
import ProjectNavigation from "./components/ProjectNavigation.vue";
import PropertyPanel from "./components/PropertyPanel.vue";
import PreviewPanel from "./components/PreviewPanel.vue";
import RevisionHistoryPanel from "./components/RevisionHistoryPanel.vue";
import RepairStatusPanel from "./components/RepairStatusPanel.vue";
import SheetTable from "./components/SheetTable.vue";

type PreviewContext={workspaceId:string;baseRevisionId:string;cadVersion:string;commands:ChangeCommand[];result:Preview};
type CsvPreviewContext={workspaceId:string;baseRevisionId:string;csv:string;result:CsvPreview};
type RestorePreviewContext={workspaceId:string;baseRevisionId:string;revisionId:string;loadGeneration:number;result:RestorePreview};

const dstPath=ref("");
const workspace=ref<Workspace|null>(null);
const baseWorkspace=ref<Workspace|null>(null);
const selectedId=ref("");
const error=ref("");
const commands=ref<ChangeCommand[]>([]);
const draftActions=ref<DraftAction[]>([]);
const draftCursor=ref(0);
const draftVersion=ref(0);
const draftStale=ref(false);
const draftStaleReasons=ref<string[]>([]);
const draftCorrupted=ref(false);
const draftSaveFailed=ref(false);
const preview=ref<Preview|null>(null);
const previewContext=ref<PreviewContext|null>(null);
const job=ref<Job|null>(null);
const revisions=ref<Revision[]>([]);
const restorePreview=ref<RestorePreview|null>(null);
const restorePreviewContext=ref<RestorePreviewContext|null>(null);
const repairPreview=ref<RepairPreview|null>(null);
const repairContext=ref<{workspaceId:string;baseRevisionId:string;previewDigest:string|undefined;loadGeneration:number}|null>(null);
const isRepairPreviewing=ref(false);
const isRepairExecuting=ref(false);
const connectionMode=ref("SSE");
const csvText=ref("");
const csvPreview=ref<CsvPreview|null>(null);
const csvPreviewContext=ref<CsvPreviewContext|null>(null);
const isWorkspaceLoading=ref(false);
const isRestoreExecuting=ref(false);
const cadVersion=ref("2020");
const searchText=ref("");
const subsetFilter=ref("all");
const pathFilter=ref("all");
const diagnosticFilter=ref("all");
const pendingFilter=ref("all");
const selectedSheetIds=ref<string[]>([]);
const renderLimit=ref(80);
const bulkPropertyName=ref("");
const bulkPropertyValue=ref("");
let previewGeneration=0;
let csvGeneration=0;
let workspaceLoadGeneration=0;
let jobMonitorGeneration=0;
let revisionGeneration=0;
let restoreExecutionGeneration=0;
let repairGeneration=0;
let activeJobEvents:EventSource|null=null;
let pollTimer:number|null=null;
let draftSaveQueue:Promise<void>=Promise.resolve();

const propertyForm=reactive<{type:PropertyType;name:string;defaultValue:string}>({type:"sheet",name:"",defaultValue:""});
const insertSheetForm=reactive<{subsetId:string;sequence:string;direction:Placement;count:string;sourceType:LayoutSourceType;sourceFile:string;sourceLayout:string}>({subsetId:"",sequence:"1",direction:"after",count:"1",sourceType:"template_layout",sourceFile:"",sourceLayout:""});
const insertSubsetForm=reactive<{sequence:string;direction:Placement;title:string;initialSheetCount:string;templateFile:string;templateLayout:string}>({sequence:"1",direction:"after",title:"",initialSheetCount:"1",templateFile:"",templateLayout:""});

const selected=computed(()=>workspace.value?.sheet_set.subsets.find(item=>item.id===selectedId.value)??null);
const blocking=computed(()=>workspace.value?.diagnostics.filter(item=>item.severity==="error")??[]);
const dstValidation=computed(()=>workspace.value?.dst_validation??null);
const repairWritesDisabled=computed(()=>{
  const status=dstValidation.value?.status;
  // 旧客户端/旧 mock 未提供 dst_validation 时视为 VALID（后端仍会门禁）
  if(!status||status==="VALID")return false;
  return true;
});
const hasPropertyDefinitionCommands=computed(()=>commands.value.some(item=>item.type==="add_custom_property"||item.type==="delete_custom_property"));
const hasStructuralCommands=computed(()=>commands.value.some(item=>["update_subset_title","delete_sheet","delete_subset","insert_sheet","insert_subset"].includes(String(item.type))));
const previewGroups=computed(()=>preview.value?.execution_intent?.groups??[]);
const derivedSubsets=computed(()=>preview.value?.execution_intent?.derived_document?.subsets??[]);
const sourceBaselines=computed(()=>preview.value?.execution_intent?.source_baselines??[]);
const subsetOperations=computed(()=>preview.value?.execution_intent?.subset_operations??[]);
const cardinalityFrontier=computed(()=>preview.value?.execution_intent?.cardinality_frontier??null);
const cadValidationDeferred=computed(()=>preview.value?.execution_intent?.cad_validation_deferred===true);
const semanticDiff=computed<SemanticDiff>(()=>preview.value?.semantic_diff??{sheet_set:[],structure:{before:[],after:[]},properties:[],dwgs:[]});
const allSheetRows=computed(()=>(workspace.value?.sheet_set.subsets??[]).flatMap(subset=>subset.sheets.map(sheet=>({subset,sheet}))));
const pendingSheetIds=computed(()=>new Set(commands.value.flatMap(command=>"sheet_id" in command&&typeof command.sheet_id==="string"?[command.sheet_id]:[])));
const diagnosticObjectIds=computed(()=>new Set((workspace.value?.diagnostics??[]).filter(item=>item.severity==="error").map(item=>item.object_id).filter((id):id is string=>Boolean(id))));
const filteredSheetRows=computed(()=>{
  const query=searchText.value.trim().toLocaleLowerCase();
  return allSheetRows.value.filter(({subset,sheet})=>{
    if(subsetFilter.value!=="all"&&subset.id!==subsetFilter.value)return false;
    const resolved=Boolean(sheet.layout.resolved_path);
    if(pathFilter.value==="resolved"&&!resolved)return false;
    if(pathFilter.value==="unresolved"&&resolved)return false;
    const hasDiagnostic=diagnosticObjectIds.value.has(sheet.id);
    if(diagnosticFilter.value==="blocking"&&!hasDiagnostic)return false;
    if(diagnosticFilter.value==="clean"&&hasDiagnostic)return false;
    const pending=pendingSheetIds.value.has(sheet.id);
    if(pendingFilter.value==="pending"&&!pending)return false;
    if(pendingFilter.value==="unchanged"&&pending)return false;
    if(!query)return true;
    return [sheet.number,sheet.title,subset.display_name,sheet.layout.file_name,sheet.layout.relative_file_name,sheet.layout.resolved_path,sheet.layout.layout_name,...Object.entries(sheet.custom_properties).flat()].filter(Boolean).some(value=>String(value).toLocaleLowerCase().includes(query));
  });
});
const visibleSheetRows=computed(()=>filteredSheetRows.value.slice(0,renderLimit.value));
const allFilteredSelected=computed(()=>filteredSheetRows.value.length>0&&filteredSheetRows.value.every(({sheet})=>selectedSheetIds.value.includes(sheet.id)));
const sheetPropertyNames=computed(()=>workspace.value?.sheet_set.property_definitions.filter(item=>item.type==="sheet").map(item=>item.name)??[]);
const executionEstimate=computed(()=>preview.value?.execution_intent?.estimate??null);

function cloneJson<T>(value:T):T{return JSON.parse(JSON.stringify(value))}
function invalidatePreview(){previewGeneration+=1;preview.value=null;previewContext.value=null}
function invalidateCsvPreview(clearText=false){csvGeneration+=1;csvPreview.value=null;csvPreviewContext.value=null;if(clearText)csvText.value=""}
function invalidateRevisionState(){revisionGeneration+=1;revisions.value=[];restorePreview.value=null;restorePreviewContext.value=null}
function invalidateJobMonitor(clearJob=false){jobMonitorGeneration+=1;activeJobEvents?.close();activeJobEvents=null;if(pollTimer!==null){clearTimeout(pollTimer);pollTimer=null}if(clearJob)job.value=null;return jobMonitorGeneration}
function resetEditingState(){commands.value=[];invalidatePreview();invalidateCsvPreview(true);error.value=""}
function resetDraftState(){draftActions.value=[];draftCursor.value=0;draftVersion.value=0;draftStale.value=false;draftStaleReasons.value=[];draftCorrupted.value=false;draftSaveFailed.value=false}
function beginWorkspaceLoad(){workspaceLoadGeneration+=1;isWorkspaceLoading.value=true;resetEditingState();resetDraftState();invalidateRevisionState();return workspaceLoadGeneration}
function selectInitialSubset(){
  selectedId.value=workspace.value?.sheet_set.subsets[0]?.id??"";
  insertSheetForm.subsetId=selectedId.value;
}
function selectSubset(subsetId:string){selectedId.value=subsetId;insertSheetForm.subsetId=subsetId}
function resetNavigation(){searchText.value="";subsetFilter.value="all";pathFilter.value="all";diagnosticFilter.value="all";pendingFilter.value="all";selectedSheetIds.value=[];renderLimit.value=80}
async function openByPath(path:string){
  if(isRestoreExecuting.value){error.value="修订恢复正在执行，请稍候";return}
  isWorkspaceLoading.value=true;
  await draftSaveQueue;
  if(draftSaveFailed.value){isWorkspaceLoading.value=false;return}
  invalidateJobMonitor(true);
  const generation=beginWorkspaceLoad();
  try{
    const loaded:Workspace=await request("/api/workspaces/open",{method:"POST",body:JSON.stringify({dst_path:path})});
    if(generation!==workspaceLoadGeneration)return;
    resetEditingState();baseWorkspace.value=cloneJson(loaded);workspace.value=cloneJson(loaded);selectInitialSubset();resetNavigation();await loadDraft(loaded);isWorkspaceLoading.value=false;
  }
  catch(e){if(generation===workspaceLoadGeneration){isWorkspaceLoading.value=false;error.value=String(e)}}
}
async function openWorkspace(){await openByPath(dstPath.value)}
const hasShell=computed(()=>getShellBridge()!==null);
const DST_EXT=/\.dst$/i;
async function selectAndOpenDst(){
  const bridge=getShellBridge();
  if(!bridge){error.value="桌面壳未就绪，请通过 dst-manager desktop 启动";return}
  const path=await bridge.select_file(DST_FILE_FILTERS);
  if(!path)return;
  if(!DST_EXT.test(path)){error.value="仅支持 DST 文件";return}
  await openByPath(path);
}
async function closeWorkspace(){
  const pending=draftActions.value.length>0||draftSaveFailed.value||draftStale.value;
  if(pending){
    const ok=confirm("存在未发布完毕的改动。改动已自动保存，重新打开同一 DST 可继续处理。确定关闭并放弃当前改动？");
    if(!ok)return;
    await discardDraft();
  }
  // 推进加载代次：关闭后迟到的打开/刷新/修订响应全部按代次失效，防止复活工作区
  workspaceLoadGeneration+=1;isWorkspaceLoading.value=false;resetDraftState();resetEditingState();baseWorkspace.value=null;workspace.value=null;
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
  const previous=selectedId.value;
  const generation=beginWorkspaceLoad();
  try{
    const loaded:Workspace=await request(`/api/workspaces/${workspaceId}`);
    if(generation!==workspaceLoadGeneration)return;
    resetEditingState();baseWorkspace.value=cloneJson(loaded);workspace.value=cloneJson(loaded);
    selectedId.value=loaded.sheet_set.subsets.some(item=>item.id===previous)?previous:(loaded.sheet_set.subsets[0]?.id??"");
    insertSheetForm.subsetId=selectedId.value;await loadDraft(loaded);isWorkspaceLoading.value=false;
  }
  catch(e){if(generation===workspaceLoadGeneration){isWorkspaceLoading.value=false;error.value=String(e)}}
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
  if(result.corrupted)error.value="检测到损坏草稿，已隔离；可安全重新开始编辑";
  else if(result.stale)error.value="草稿基准或修复状态已变化；仅可查看旧意图、手工重做或丢弃，禁止自动 rebase";
}
function commandLabel(command:ChangeCommand){
  const labels:Record<ChangeCommand["type"],string>={update_sheet_set:"更新图纸集",update_subset_title:"更新子集标题",update_sheet_properties:"更新图纸属性",delete_sheet:"删除图纸",insert_sheet:"新增图纸",insert_subset:"新建子集",add_custom_property:"新增属性定义",delete_custom_property:"删除属性定义",delete_subset:"删除子集"};
  return labels[command.type];
}
function rebuildDraftProjection(){
  commands.value=draftStale.value?[]:projectCommands(draftActions.value,draftCursor.value);
  if(baseWorkspace.value)workspace.value=projectWorkspace(baseWorkspace.value,draftStale.value?[]:draftActions.value,draftStale.value?0:draftCursor.value);
  invalidatePreview();
}
function scheduleDraftSave(){
  const workspaceId=workspace.value?.id;
  if(!workspaceId||draftStale.value)return;
  draftSaveQueue=draftSaveQueue.then(async()=>{
    const current=workspace.value;
    if(!current||current.id!==workspaceId||draftStale.value)return;
    try{
      const saved:DraftEnvelope=await request(`/api/workspaces/${workspaceId}/draft`,{method:"PUT",body:JSON.stringify({schema_version:1,base_revision_id:current.revision_id,repair_status:current.dst_validation?.status??"VALID",expected_version:draftVersion.value,cursor:draftCursor.value,actions:cloneJson(draftActions.value)})});
      if(workspace.value?.id===workspaceId&&saved.draft){draftVersion.value=saved.draft.version;draftSaveFailed.value=false}
    }
    catch(e){if(workspace.value?.id===workspaceId&&e instanceof ApiError&&e.code==="DRAFT_CONFLICT"){draftSaveFailed.value=true;draftStale.value=true;draftStaleReasons.value=["DRAFT_VERSION_CONFLICT"];commands.value=[];invalidatePreview();error.value="草稿已在其他窗口更新；当前窗口禁止覆盖，请重新打开工作区"}else throw e}
  }).catch(e=>{if(workspace.value?.id===workspaceId){draftSaveFailed.value=true;error.value=String(e)}});
}
function clearCommands(){draftActions.value=[];draftCursor.value=0;rebuildDraftProjection();scheduleDraftSave();error.value=""}
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
  if(!confirm("将放弃当前窗口未保存的冲突动作，并重新读取服务器上的较新草稿。是否继续？"))return;
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
function positiveInteger(value:string){const parsed=Number(value);return Number.isInteger(parsed)&&parsed>0?parsed:null}

function queueSheetSet(){if(!workspace.value)return;if(!workspace.value.sheet_set.name.trim()){error.value="图纸集名称不能为空";return}addCommand(createCommand.updateSheetSet(workspace.value.sheet_set.name,{...workspace.value.sheet_set.custom_properties}),"metadata")}
function queueSubsetTitle(){if(selected.value)addCommand(createCommand.updateSubsetTitle(selected.value.id,selected.value.title),"structural")}
function queueSheetProperties(sheet:Sheet){addCommand(createCommand.updateSheetProperties(sheet.id,{...sheet.custom_properties}),"metadata")}
function queueDelete(sheet:Sheet){if(selected.value&&confirm(`删除图纸 ${sheet.number}？`))addCommand(createCommand.deleteSheet(sheet.id),"structural")}
function queueDeleteSubset(){
  const subset=selected.value;if(!subset)return;
  const drawing=subset.sheets[0]?.layout.resolved_path??subset.sheets[0]?.layout.file_name??"（未知主 DWG）";
  if(confirm(`删除整个子集“${subset.display_name}”、其中 ${subset.sheets.length} 张图纸及主 DWG：${drawing}？\n系统不会证明工程外部引用，确认后由用户承担外部影响。`))addCommand(createCommand.deleteSubset(subset.id),"structural");
}
function toggleFilteredSelection(){
  const ids=filteredSheetRows.value.map(({sheet})=>sheet.id);
  if(allFilteredSelected.value)selectedSheetIds.value=selectedSheetIds.value.filter(id=>!ids.includes(id));
  else selectedSheetIds.value=Array.from(new Set([...selectedSheetIds.value,...ids]));
}
function toggleSheetSelection(sheetId:string){selectedSheetIds.value=selectedSheetIds.value.includes(sheetId)?selectedSheetIds.value.filter(id=>id!==sheetId):[...selectedSheetIds.value,sheetId]}
function queueBulkSheetProperty(){
  const name=bulkPropertyName.value;
  if(!name||!selectedSheetIds.value.length){error.value="请选择图纸和既有图纸属性";return}
  const selectedIds=new Set(selectedSheetIds.value);
  const batch=allSheetRows.value.filter(({sheet})=>selectedIds.has(sheet.id)).map(({sheet})=>createCommand.updateSheetProperties(sheet.id,{...sheet.custom_properties,[name]:bulkPropertyValue.value}));
  if(addCommandBatch(batch,`批量更新 ${name}（${batch.length} 张）`,"metadata"))selectedSheetIds.value=[];
}
function queuePropertyDefinition(){
  const name=propertyForm.name.trim();if(!name){error.value="属性名称不能为空";return}
  if(addCommand(createCommand.addCustomProperty(propertyForm.type,name,propertyForm.defaultValue),"property")){propertyForm.name="";propertyForm.defaultValue=""}
}
function queueDeleteProperty(definition:PropertyDefinition){addCommand(createCommand.deleteCustomProperty(definition.type,definition.name),"property")}

function queueInsertSheet(){
  if(!workspace.value)return;
  const subset=workspace.value.sheet_set.subsets.find(item=>item.id===insertSheetForm.subsetId);
  if(!subset){error.value="请选择目标子集";return}
  const sequence=positiveInteger(insertSheetForm.sequence);
  const count=positiveInteger(insertSheetForm.count);
  if(sequence===null||sequence>subset.sheets.length){error.value=`图纸序号必须在 1 到 ${subset.sheets.length} 之间`;return}
  if(count===null){error.value="新增图纸数量必须为正整数";return}
  if(!insertSheetForm.sourceFile.trim()||!insertSheetForm.sourceLayout.trim()){error.value="来源文件和来源布局不能为空";return}
  addCommand(createCommand.insertSheet({target_subset_id:subset.id,ordinal:sequence,placement:insertSheetForm.direction,count,source:{type:insertSheetForm.sourceType,file:insertSheetForm.sourceFile.trim(),layout:insertSheetForm.sourceLayout.trim()}}),"structural");
}
function queueInsertSubset(){
  if(!workspace.value)return;
  const sequence=positiveInteger(insertSubsetForm.sequence);
  const count=positiveInteger(insertSubsetForm.initialSheetCount);
  const subsetCount=workspace.value.sheet_set.subsets.length;
  if(sequence===null){error.value="子集序号必须为正整数";return}
  if(subsetCount===0&&sequence!==1){error.value="空图纸集的首个子集序号必须为 1";return}
  if(subsetCount>0&&sequence>subsetCount){error.value=`子集序号必须在 1 到 ${subsetCount} 之间`;return}
  if(!insertSubsetForm.title.trim()){error.value="子集标题不能为空";return}
  if(count===null){error.value="初始图纸数必须为正整数";return}
  if(!insertSubsetForm.templateFile.trim()||!insertSubsetForm.templateLayout.trim()){error.value="模板文件和模板布局不能为空";return}
  addCommand(createCommand.insertSubset({ordinal:sequence,placement:insertSubsetForm.direction,title:insertSubsetForm.title.trim(),initial_sheet_count:count,source:{type:"template_layout",file:insertSubsetForm.templateFile.trim(),layout:insertSubsetForm.templateLayout.trim()}}),"structural");
}

async function showPreview(){
  if(isWorkspaceLoading.value||draftStale.value||!workspace.value||!commands.value.length)return;
  const workspaceId=workspace.value.id;
  const baseRevisionId=workspace.value.revision_id;
  const cadVersionSnapshot=cadVersion.value;
  const commandSnapshot=cloneJson(commands.value);
  const generation=++previewGeneration;
  preview.value=null;previewContext.value=null;
  try{
    const result:Preview=await request(`/api/workspaces/${workspaceId}/changes/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId,commands:commandSnapshot,cad_version:cadVersionSnapshot})});
    if(generation!==previewGeneration||workspace.value?.id!==workspaceId||workspace.value.revision_id!==baseRevisionId)return;
    preview.value=result;previewContext.value={workspaceId,baseRevisionId,cadVersion:cadVersionSnapshot,commands:commandSnapshot,result};error.value="";
  }
  catch(e){if(generation===previewGeneration)error.value=String(e)}
}
async function execute(){
  const context=previewContext.value;
  if(!context||!context.result.executable)return;
  const current=workspace.value;
  if(isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId){invalidatePreview();error.value="工作区或基准修订已变化，请重新预览";return}
  if(!confirm("确认发布？原 DST 和受影响 DWG 将永久备份。"))return;
  const generation=invalidateJobMonitor(false);
  try{
    const result:Job=await request(`/api/workspaces/${context.workspaceId}/changes/execute`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,commands:cloneJson(context.commands),cad_version:context.cadVersion,preview_digest:context.result.preview_digest})});
    if(generation!==jobMonitorGeneration||isWorkspaceLoading.value||workspace.value?.id!==context.workspaceId)return;
    job.value=result;if(result.status==="QUEUED"&&result.id)watchJob(result.id,context.workspaceId);else if(result.status==="SUCCEEDED"){await discardDraft();await refreshWorkspace(context.workspaceId)}
  }
  catch(e){if(generation===jobMonitorGeneration&&workspace.value?.id===context.workspaceId&&!isWorkspaceLoading.value)error.value=String(e)}
}

function terminal(status:string){return ["SUCCEEDED","FAILED","ROLLED_BACK","BLOCKED_FILE_LOCK","NEEDS_REVIEW"].includes(status)}
function monitorMatches(generation:number,workspaceId:string){return generation===jobMonitorGeneration&&!isWorkspaceLoading.value&&workspace.value?.id===workspaceId}
function watchJob(id:string,workspaceId:string){
  const generation=invalidateJobMonitor(false);
  const events=new EventSource(`/api/jobs/${id}/events`);
  activeJobEvents=events;
  events.onmessage=async event=>{if(!monitorMatches(generation,workspaceId))return;const result:Job=JSON.parse(event.data);if(!monitorMatches(generation,workspaceId))return;job.value=result;if(terminal(result.status)){events.close();if(activeJobEvents===events)activeJobEvents=null;if(result.status==="SUCCEEDED"){await discardDraft();await refreshWorkspace(workspaceId)}}};
  events.onerror=()=>{if(!monitorMatches(generation,workspaceId))return;events.close();if(activeJobEvents===events)activeJobEvents=null;connectionMode.value="轮询";schedulePoll(id,workspaceId,generation)};
}
function schedulePoll(id:string,workspaceId:string,generation:number){if(!monitorMatches(generation,workspaceId))return;if(pollTimer!==null)clearTimeout(pollTimer);pollTimer=window.setTimeout(()=>{pollTimer=null;void pollJob(id,workspaceId,generation)},1000)}
async function pollJob(id:string,workspaceId:string,generation:number){if(!monitorMatches(generation,workspaceId)||job.value&&terminal(job.value.status))return;try{const result:Job=await request(`/api/jobs/${id}`);if(!monitorMatches(generation,workspaceId))return;job.value=result;if(!terminal(result.status))schedulePoll(id,workspaceId,generation);else if(result.status==="SUCCEEDED"){await discardDraft();await refreshWorkspace(workspaceId)}}catch(e){if(monitorMatches(generation,workspaceId))error.value=String(e)}}
async function retryJob(){const current=workspace.value;if(!current||!job.value||!job.value.id||isWorkspaceLoading.value)return;if(job.value.status==="NEEDS_REVIEW"){error.value="发布状态需要人工检查，禁止直接重试";return}const workspaceId=current.id,id=job.value.id,generation=invalidateJobMonitor(false);try{const result:Job=await request(`/api/jobs/${id}/retry`,{method:"POST"});if(!monitorMatches(generation,workspaceId))return;job.value=result;if(result.status==="QUEUED")watchJob(id,workspaceId)}catch(e){if(monitorMatches(generation,workspaceId))error.value=String(e)}}

function revisionRequestMatches(generation:number,loadGeneration:number,workspaceId:string){return generation===revisionGeneration&&loadGeneration===workspaceLoadGeneration&&!isWorkspaceLoading.value&&workspace.value?.id===workspaceId}
async function loadRevisions(){
  if(isRestoreExecuting.value)return;
  await loadRevisionsInternal();
}
async function loadRevisionsInternal(){
  const current=workspace.value;if(!current||isWorkspaceLoading.value)return;
  const workspaceId=current.id,loadGeneration=workspaceLoadGeneration,generation=++revisionGeneration;
  revisions.value=[];restorePreview.value=null;restorePreviewContext.value=null;
  try{const result:Revision[]=await request(`/api/revisions?workspace_id=${workspaceId}`);if(revisionRequestMatches(generation,loadGeneration,workspaceId))revisions.value=result}
  catch(e){if(revisionRequestMatches(generation,loadGeneration,workspaceId))error.value=String(e)}
}
async function previewRestore(revision:Revision){
  const current=workspace.value;if(!current||isWorkspaceLoading.value||isRestoreExecuting.value)return;
  const workspaceId=current.id,baseRevisionId=current.revision_id,revisionId=revision.id,loadGeneration=workspaceLoadGeneration,generation=++revisionGeneration;
  restorePreview.value=null;restorePreviewContext.value=null;
  try{const result:RestorePreview=await request(`/api/workspaces/${workspaceId}/revisions/${revisionId}/restore-preview`);if(!revisionRequestMatches(generation,loadGeneration,workspaceId))return;restorePreview.value=result;restorePreviewContext.value={workspaceId,baseRevisionId,revisionId,loadGeneration,result}}
  catch(e){if(revisionRequestMatches(generation,loadGeneration,workspaceId))error.value=String(e)}
}
function restoreExecutionMatches(generation:number,context:RestorePreviewContext){return generation===restoreExecutionGeneration&&context.loadGeneration===workspaceLoadGeneration&&!isWorkspaceLoading.value&&workspace.value?.id===context.workspaceId&&workspace.value.revision_id===context.baseRevisionId}
async function restoreRevision(){
  const context=restorePreviewContext.value,current=workspace.value;
  if(isRestoreExecuting.value||!context||!context.result.executable)return;
  if(isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId||context.loadGeneration!==workspaceLoadGeneration){restorePreview.value=null;restorePreviewContext.value=null;error.value="工作区或基准修订已变化，请重新生成恢复预览";return}
  if(!confirm("确认恢复为新修订？历史修订不会被覆盖。"))return;
  const generation=++restoreExecutionGeneration;
  isRestoreExecuting.value=true;invalidateJobMonitor(true);revisionGeneration+=1;
  try{
    const result:Job=await request(`/api/workspaces/${context.workspaceId}/revisions/${context.revisionId}/restore`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,preview_digest:context.result.preview_digest})});
    if(!restoreExecutionMatches(generation,context))return;
    job.value=result;restorePreview.value=null;restorePreviewContext.value=null;error.value="";await refreshWorkspace(context.workspaceId);if(workspace.value?.id===context.workspaceId&&!isWorkspaceLoading.value)await loadRevisionsInternal();
  }
  catch(e){if(restoreExecutionMatches(generation,context))error.value=String(e)}
  finally{if(generation===restoreExecutionGeneration)isRestoreExecuting.value=false}
}

async function previewRepair(){
  const current=workspace.value;
  if(isWorkspaceLoading.value||!current||isRepairPreviewing.value)return;
  const workspaceId=current.id,baseRevisionId=current.revision_id,loadGeneration=workspaceLoadGeneration,generation=++repairGeneration;
  repairPreview.value=null;repairContext.value=null;isRepairPreviewing.value=true;
  try{
    const result:RepairPreview=await request(`/api/workspaces/${workspaceId}/repairs/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId})});
    // 代次/修订保护：旧修复报告不得覆盖新工作区
    if(generation!==repairGeneration||loadGeneration!==workspaceLoadGeneration||workspace.value?.id!==workspaceId||workspace.value.revision_id!==baseRevisionId)return;
    repairPreview.value=result;repairContext.value={workspaceId,baseRevisionId,previewDigest:result.preview_digest??undefined,loadGeneration};error.value="";
  }
  catch(e){if(generation===repairGeneration)error.value=String(e)}
  finally{if(generation===repairGeneration)isRepairPreviewing.value=false}
}
async function executeRepair(){
  const context=repairContext.value;
  if(!context||isRepairExecuting.value)return;
  const current=workspace.value;
  if(isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId||context.loadGeneration!==workspaceLoadGeneration){repairPreview.value=null;repairContext.value=null;error.value="工作区或基准修订已变化，请重新生成修复预览";return}
  if(!confirm("确认把内存修复发布为独立修订？原 DST 将永久备份。"))return;
  const generation=invalidateJobMonitor(false);
  isRepairExecuting.value=true;
  try{
    const result:Job=await request(`/api/workspaces/${context.workspaceId}/repairs/execute`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,preview_digest:context.previewDigest})});
    if(generation!==jobMonitorGeneration||isWorkspaceLoading.value||workspace.value?.id!==context.workspaceId)return;
    job.value=result;
    if(result.status==="SUCCEEDED"){repairPreview.value=null;repairContext.value=null;await refreshWorkspace(context.workspaceId)}
    else if(result.status==="FAILED"){error.value=result.error_code??"修复发布失败"}
  }
  catch(e){if(generation===jobMonitorGeneration&&workspace.value?.id===context.workspaceId&&!isWorkspaceLoading.value)error.value=String(e)}
  finally{if(generation===jobMonitorGeneration)isRepairExecuting.value=false}
}

async function readCsvFile(event:Event){
  const generation=++csvGeneration;
  csvText.value="";csvPreview.value=null;csvPreviewContext.value=null;error.value="";
  const file=(event.target as HTMLInputElement).files?.[0];
  if(!file)return;
  try{
    const decoded=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());
    if(generation!==csvGeneration)return;
    csvText.value=decoded;
  }
  catch{if(generation===csvGeneration)error.value="CSV 必须使用 UTF-8 编码"}
}
async function previewCsv(){
  if(isWorkspaceLoading.value||!workspace.value||!csvText.value){error.value="请选择 UTF-8 CSV 文件";return}
  const workspaceId=workspace.value.id;
  const baseRevisionId=workspace.value.revision_id;
  const csvSnapshot=csvText.value;
  const generation=++csvGeneration;
  csvPreview.value=null;csvPreviewContext.value=null;
  try{
    const result:CsvPreview=await request(`/api/workspaces/${workspaceId}/custom-properties/import/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId,csv:csvSnapshot})});
    if(generation!==csvGeneration||workspace.value?.id!==workspaceId||workspace.value.revision_id!==baseRevisionId||csvText.value!==csvSnapshot)return;
    csvPreview.value=result;csvPreviewContext.value={workspaceId,baseRevisionId,csv:csvSnapshot,result};error.value="";
  }
  catch(e){if(generation===csvGeneration)error.value=String(e)}
}
async function importCsv(){
  const context=csvPreviewContext.value;
  if(!context||!context.result.executable)return;
  const current=workspace.value;
  if(isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId){invalidateCsvPreview();error.value="工作区或基准修订已变化，请重新预览 CSV";return}
  if(!confirm("确认导入属性定义？"))return;
  const generation=invalidateJobMonitor(false);
  try{const result:Job=await request(`/api/workspaces/${context.workspaceId}/custom-properties/import`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,csv:context.csv,preview_digest:context.result.preview_digest})});if(generation!==jobMonitorGeneration||isWorkspaceLoading.value||workspace.value?.id!==context.workspaceId)return;job.value=result;if(result.status==="QUEUED"&&result.id)watchJob(result.id,context.workspaceId);else if(result.status==="SUCCEEDED"&&!result.no_op)await refreshWorkspace(context.workspaceId)}
  catch(e){if(generation===jobMonitorGeneration&&workspace.value?.id===context.workspaceId&&!isWorkspaceLoading.value)error.value=String(e)}
}

</script>

<template>
  <header><div><h1>DST Manager</h1><span>v0.3 · 受控日常编辑与可恢复发布</span></div></header>
  <main>
    <section v-if="!workspace" class="open"><template v-if="!hasShell"><input v-model="dstPath" placeholder="输入 .dst 绝对路径" @keyup.enter="openWorkspace"><button :disabled="isRestoreExecuting" @click="openWorkspace">打开项目</button></template><button v-else @click="selectAndOpenDst">选择 DST 文件</button></section><section v-else class="open"><button :disabled="isRestoreExecuting" @click="closeWorkspace">关闭</button><button :disabled="isWorkspaceLoading||isRestoreExecuting" @click="loadRevisions">修订历史</button></section>
    <p v-if="error" class="error notice">{{error}}</p>
    <p v-if="isWorkspaceLoading" class="panel loading" role="status">正在加载工作区…</p>
    <p v-if="isRestoreExecuting" class="panel loading" role="status">正在恢复修订…</p>

    <JobStatusPanel v-if="job&&!isWorkspaceLoading" :job="job" :connection-mode="connectionMode" @retry="retryJob" />

    <RevisionHistoryPanel v-if="revisions.length&&!isWorkspaceLoading" :revisions="revisions" :restore-preview="restorePreview" :executing="isRestoreExecuting" @preview="previewRestore" @restore="restoreRevision" />

    <template v-if="workspace&&!isWorkspaceLoading&&!isRestoreExecuting">
      <section class="summary"><div><small>图纸集</small><input v-model="workspace.sheet_set.name"><button @click="queueSheetSet">更新图纸集</button></div><div><small>子集</small><strong>{{workspace.sheet_set.subset_count}}</strong></div><div><small>图纸</small><strong>{{workspace.sheet_set.sheet_count}}</strong></div><div><small>阻断诊断</small><strong>{{blocking.length}}</strong></div><div><label>AutoCAD 版本<select v-model="cadVersion" @change="invalidatePreview"><option value="2016">2016</option><option value="2020">2020</option></select></label></div></section>
      <details v-if="Object.keys(workspace.sheet_set.custom_properties).length"><summary>图纸集自定义属性</summary><div class="form-grid"><label v-for="(_,name) in workspace.sheet_set.custom_properties" :key="name">{{name}}<input v-model="workspace.sheet_set.custom_properties[name]"></label></div><button @click="queueSheetSet">加入属性值变更</button></details>
      <details v-if="workspace.diagnostics.length"><summary>诊断（{{workspace.diagnostics.length}}）</summary><ul><li v-for="item in workspace.diagnostics" :key="item.code+item.message" :class="item.severity">{{item.code}}：{{item.message}}</li></ul></details>

      <RepairStatusPanel v-if="dstValidation&&dstValidation.status!=='VALID'" :validation="dstValidation" :preview="repairPreview" :previewing="isRepairPreviewing" :executing="isRepairExecuting" @preview-repair="previewRepair" @execute-repair="executeRepair" @cancel="repairPreview=null;repairContext=null" />

      <PropertyPanel :workspace-id="workspace.id" :definitions="workspace.sheet_set.property_definitions" :form="propertyForm" :has-csv="Boolean(csvText)" :csv-preview="csvPreview" :csv-executable="Boolean(csvPreviewContext?.result.executable)" :writes-disabled="repairWritesDisabled" @delete-definition="queueDeleteProperty" @add-definition="queuePropertyDefinition" @read-csv="readCsvFile" @preview-csv="previewCsv" @import-csv="importCsv" />

      <section class="panel sheet-browser" aria-label="图纸导航与筛选">
        <div class="section-title"><div><h2>图纸集 / 子集 / 图纸导航</h2><p>派生字段只读；搜索覆盖图号、标题、自定义属性及 DWG 文件名、相对路径和解析路径。</p></div><strong>{{filteredSheetRows.length}} / {{allSheetRows.length}} 张</strong></div>
        <div class="filter-grid">
          <label>搜索图纸<input v-model="searchText" placeholder="图号、标题、属性或 DWG" @input="renderLimit=80"></label>
          <label>子集<select v-model="subsetFilter" @change="renderLimit=80"><option value="all">全部子集</option><option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{subset.display_name}}</option></select></label>
          <label>路径状态<select v-model="pathFilter" @change="renderLimit=80"><option value="all">全部</option><option value="resolved">已解析</option><option value="unresolved">未解析</option></select></label>
          <label>诊断状态<select v-model="diagnosticFilter" @change="renderLimit=80"><option value="all">全部</option><option value="blocking">有阻断诊断</option><option value="clean">无阻断诊断</option></select></label>
          <label>待变更状态<select v-model="pendingFilter" @change="renderLimit=80"><option value="all">全部</option><option value="pending">待变更</option><option value="unchanged">未变更</option></select></label>
        </div>
        <div class="bulk-bar"><button :disabled="!filteredSheetRows.length" @click="toggleFilteredSelection">{{allFilteredSelected?'取消全选':'全选当前结果'}}</button><span>已选 {{selectedSheetIds.length}}</span><label>既有图纸属性<select v-model="bulkPropertyName"><option value="">请选择</option><option v-for="name in sheetPropertyNames" :key="name" :value="name">{{name}}</option></select></label><label>批量值<input v-model="bulkPropertyValue"></label><button :disabled="!selectedSheetIds.length||!bulkPropertyName" @click="queueBulkSheetProperty">批量加入草稿</button></div>
        <SheetTable :rows="visibleSheetRows" :selected-ids="selectedSheetIds" :pending-ids="pendingSheetIds" :diagnostic-ids="diagnosticObjectIds" @toggle="toggleSheetSelection" @open-subset="selectSubset" />
        <button v-if="visibleSheetRows.length<filteredSheetRows.length" @click="renderLimit+=80">继续加载（尚余 {{filteredSheetRows.length-visibleSheetRows.length}}）</button>
      </section>

      <section class="editor">
        <ProjectNavigation :subsets="workspace.sheet_set.subsets" :selected-id="selectedId" @select="selectSubset" />
        <article>
          <DraftActionsPanel :actions="draftActions" :cursor="draftCursor" :command-count="commands.length" :stale="draftStale" :stale-reasons="draftStaleReasons" :corrupted="draftCorrupted" :writes-disabled="repairWritesDisabled" :loading="isWorkspaceLoading" @discard="discardDraft" @reload-conflict="reloadAfterDraftConflict" @undo="undoDraft" @redo="redoDraft" @clear="clearCommands" @preview="showPreview" @remove="removeDraftAction" />
          <section v-if="selected" class="subset-editor"><div class="form-row"><label>当前子集标题<input v-model="selected.title"></label><button @click="queueSubsetTitle">加入标题变更</button><button class="danger" @click="queueDeleteSubset">删除整个子集</button></div><p class="derived">只读图号范围：{{selected.number_range||'—'}} · 显示名：{{selected.display_name}}</p>
            <table><thead><tr><th>图号</th><th>派生标题</th><th>自定义属性</th><th></th></tr></thead><tbody><tr v-for="sheet in selected.sheets" :key="sheet.id"><td><span>{{sheet.number}}</span></td><td><span>{{sheet.title}}</span></td><td><div class="property-values"><label v-for="(_,name) in sheet.custom_properties" :key="name">{{name}}<input v-model="sheet.custom_properties[name]"></label></div></td><td><button @click="queueSheetProperties(sheet)">加入属性变更</button><button class="danger" @click="queueDelete(sheet)">删除</button></td></tr></tbody></table>
          </section>

          <fieldset><legend>批量新增图纸</legend><div class="form-grid">
            <label>目标子集<select v-model="insertSheetForm.subsetId"><option v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :value="subset.id">{{subset.display_name}}</option></select></label>
            <label>图纸序号<input v-model="insertSheetForm.sequence" inputmode="numeric"></label><label>图纸方向<select v-model="insertSheetForm.direction"><option value="before">向前</option><option value="after">向后</option></select></label><label>新增图纸数量<input v-model="insertSheetForm.count" inputmode="numeric"></label>
            <label>来源类型<select v-model="insertSheetForm.sourceType"><option value="template_layout">DWG/DWT 模板布局</option><option value="existing_snapshot">已有布局</option></select></label><label>来源文件<input v-model="insertSheetForm.sourceFile"></label><label>来源布局<input v-model="insertSheetForm.sourceLayout"></label>
          </div><button @click="queueInsertSheet">批量新增图纸</button></fieldset>

          <fieldset><legend>新建子集</legend><div class="form-grid"><label>子集序号<input v-model="insertSubsetForm.sequence" inputmode="numeric"></label><label>子集方向<select v-model="insertSubsetForm.direction"><option value="before">向前</option><option value="after">向后</option></select></label><label>子集标题<input v-model="insertSubsetForm.title"></label><label>初始图纸数<input v-model="insertSubsetForm.initialSheetCount" inputmode="numeric"></label><label>模板文件<input v-model="insertSubsetForm.templateFile"></label><label>模板布局<input v-model="insertSubsetForm.templateLayout"></label></div><button @click="queueInsertSubset">新建子集</button></fieldset>
        </article>
      </section>

      <PreviewPanel v-if="preview" :preview="preview" :semantic-diff="semanticDiff" :estimate="executionEstimate" :cad-validation-deferred="cadValidationDeferred" :cardinality-frontier="cardinalityFrontier" :subset-operations="subsetOperations" :source-baselines="sourceBaselines" :derived-subsets="derivedSubsets" :groups="previewGroups" :writes-disabled="repairWritesDisabled" @execute="execute" />
    </template>
  </main>
</template>
