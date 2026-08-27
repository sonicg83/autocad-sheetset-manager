<script setup lang="ts">
import {computed,reactive,ref} from "vue";

type PropertyType="sheetset"|"sheet";
type PropertyDefinition={type:PropertyType;name:string;default_value:string};
type Sheet={id:string;number:string;title:string;custom_properties:Record<string,string>};
type Subset={id:string;name:string;title:string;number_range:string;display_name:string;sheets:Sheet[]};
type RepairAction={code:string;node_path:string;object_id?:string|null;confidence:"deterministic"|"inferred";before:Record<string,string|null>;after:Record<string,string|null>;message:string};
type DstValidation={status:"VALID"|"REPAIRED"|"INVALID_REPAIR_REQUIRED"|"INVALID_UNRECOVERABLE";actions:RepairAction[];blocking_issues:Diagnostic[]};
type Workspace={id:string;revision_id:string;sheet_set:{name:string;sheet_count:number;subset_count:number;custom_properties:Record<string,string>;property_definitions:PropertyDefinition[];subsets:Subset[]};diagnostics:{severity:string;code:string;message:string}[];dst_validation?:DstValidation};
type JobFile={target_path:string;status:string;progress:number;cad_operation?:string;started_at?:string;finished_at?:string;duration_ms?:number;error_code?:string;log_summary?:string};
type Job={id:string|null;status:string;progress:number;attempt?:number;error_code?:string;suggestion?:string;files?:JobFile[];no_op?:boolean};
type Revision={id:string;created_at:string;before_hash:string;result_hash:string};
type Diagnostic={severity:string;code:string;message:string;line?:number};
type Preview={executable:boolean;requires_cad?:boolean;preview_digest?:string;changes?:Record<string,any>[];diagnostics?:Diagnostic[];affected_files?:string[];execution_intent?:Record<string,any>|null;semantic_diff?:Record<string,any>};
type PreviewContext={workspaceId:string;baseRevisionId:string;cadVersion:string;commands:Record<string,unknown>[];result:Preview};
type CsvPreviewContext={workspaceId:string;baseRevisionId:string;csv:string;result:Preview};
type RestorePreviewContext={workspaceId:string;baseRevisionId:string;revisionId:string;loadGeneration:number;result:Record<string,any>};

const dstPath=ref("");
const workspace=ref<Workspace|null>(null);
const selectedId=ref("");
const error=ref("");
const commands=ref<Record<string,unknown>[]>([]);
const preview=ref<Preview|null>(null);
const previewContext=ref<PreviewContext|null>(null);
const job=ref<Job|null>(null);
const revisions=ref<Revision[]>([]);
const restorePreview=ref<Record<string,any>|null>(null);
const restorePreviewContext=ref<RestorePreviewContext|null>(null);
const repairPreview=ref<Record<string,any>|null>(null);
const repairContext=ref<{workspaceId:string;baseRevisionId:string;previewDigest:string|undefined;loadGeneration:number}|null>(null);
const isRepairPreviewing=ref(false);
const isRepairExecuting=ref(false);
const connectionMode=ref("SSE");
const csvText=ref("");
const csvPreview=ref<Preview|null>(null);
const csvPreviewContext=ref<CsvPreviewContext|null>(null);
const isWorkspaceLoading=ref(false);
const isRestoreExecuting=ref(false);
const cadVersion=ref("2020");
let previewGeneration=0;
let csvGeneration=0;
let workspaceLoadGeneration=0;
let jobMonitorGeneration=0;
let revisionGeneration=0;
let restoreExecutionGeneration=0;
let repairGeneration=0;
let activeJobEvents:EventSource|null=null;
let pollTimer:number|null=null;

const propertyForm=reactive<{type:PropertyType;name:string;defaultValue:string}>({type:"sheet",name:"",defaultValue:""});
const insertSheetForm=reactive({subsetId:"",sequence:"1",direction:"after",count:"1",sourceType:"template_layout",sourceFile:"",sourceLayout:""});
const insertSubsetForm=reactive({sequence:"1",direction:"after",title:"",initialSheetCount:"1",templateFile:"",templateLayout:""});

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
const hasStructuralCommands=computed(()=>commands.value.some(item=>["update_subset_title","delete_sheet","insert_sheet","insert_subset"].includes(String(item.type))));
const previewGroups=computed(()=>preview.value?.execution_intent?.groups??[]);
const derivedSubsets=computed(()=>preview.value?.execution_intent?.derived_document?.subsets??[]);
const sourceBaselines=computed(()=>preview.value?.execution_intent?.source_baselines??[]);
const subsetOperations=computed(()=>preview.value?.execution_intent?.subset_operations??[]);
const cardinalityFrontier=computed(()=>preview.value?.execution_intent?.cardinality_frontier??null);
const cadValidationDeferred=computed(()=>preview.value?.execution_intent?.cad_validation_deferred===true);
const semanticDiff=computed(()=>preview.value?.semantic_diff??{structure:{before:[],after:[]},properties:[],dwgs:[]});

async function request(url:string,options?:RequestInit){
  const response=await fetch(url,{headers:{"Content-Type":"application/json"},...options});
  const body=await response.json();
  if(!response.ok)throw new Error(body.message??body.detail??"请求失败");
  return body;
}

function cloneJson<T>(value:T):T{return JSON.parse(JSON.stringify(value))}
function invalidatePreview(){previewGeneration+=1;preview.value=null;previewContext.value=null}
function formatSemanticValue(value:unknown){if(value===null||value===undefined||value==="")return "—";return typeof value==="object"?JSON.stringify(value):String(value)}
function invalidateCsvPreview(clearText=false){csvGeneration+=1;csvPreview.value=null;csvPreviewContext.value=null;if(clearText)csvText.value=""}
function invalidateRevisionState(){revisionGeneration+=1;revisions.value=[];restorePreview.value=null;restorePreviewContext.value=null}
function invalidateJobMonitor(clearJob=false){jobMonitorGeneration+=1;activeJobEvents?.close();activeJobEvents=null;if(pollTimer!==null){clearTimeout(pollTimer);pollTimer=null}if(clearJob)job.value=null;return jobMonitorGeneration}
function resetEditingState(){commands.value=[];invalidatePreview();invalidateCsvPreview(true);error.value=""}
function beginWorkspaceLoad(){workspaceLoadGeneration+=1;isWorkspaceLoading.value=true;resetEditingState();invalidateRevisionState();return workspaceLoadGeneration}
function selectInitialSubset(){
  selectedId.value=workspace.value?.sheet_set.subsets[0]?.id??"";
  insertSheetForm.subsetId=selectedId.value;
}
async function openWorkspace(){
  if(isRestoreExecuting.value){error.value="修订恢复正在执行，请稍候";return}
  const pathSnapshot=dstPath.value;
  invalidateJobMonitor(true);
  const generation=beginWorkspaceLoad();
  try{
    const loaded:Workspace=await request("/api/workspaces/open",{method:"POST",body:JSON.stringify({dst_path:pathSnapshot})});
    if(generation!==workspaceLoadGeneration)return;
    resetEditingState();workspace.value=loaded;selectInitialSubset();isWorkspaceLoading.value=false;
  }
  catch(e){if(generation===workspaceLoadGeneration){isWorkspaceLoading.value=false;error.value=String(e)}}
}
async function refreshWorkspace(expectedWorkspaceId?:string){
  const current=workspace.value;
  if(!current||isWorkspaceLoading.value)return;
  const workspaceId=expectedWorkspaceId??current.id;
  if(current.id!==workspaceId)return;
  const previous=selectedId.value;
  const generation=beginWorkspaceLoad();
  try{
    const loaded:Workspace=await request(`/api/workspaces/${workspaceId}`);
    if(generation!==workspaceLoadGeneration)return;
    resetEditingState();workspace.value=loaded;
    selectedId.value=loaded.sheet_set.subsets.some(item=>item.id===previous)?previous:(loaded.sheet_set.subsets[0]?.id??"");
    insertSheetForm.subsetId=selectedId.value;isWorkspaceLoading.value=false;
  }
  catch(e){if(generation===workspaceLoadGeneration){isWorkspaceLoading.value=false;error.value=String(e)}}
}

function clearCommands(){commands.value=[];invalidatePreview();error.value=""}
function addCommand(command:Record<string,unknown>,category:"property"|"structural"|"metadata"){
  if(category==="property"&&hasStructuralCommands.value){error.value="属性定义与结构变更必须分批预览和执行";return false}
  if(category==="structural"&&hasPropertyDefinitionCommands.value){error.value="属性定义与结构变更必须分批预览和执行";return false}
  commands.value.push(command);invalidatePreview();error.value="";return true;
}
function positiveInteger(value:string){const parsed=Number(value);return Number.isInteger(parsed)&&parsed>0?parsed:null}

function queueSheetSet(){if(workspace.value)addCommand({type:"update_sheet_set",name:workspace.value.sheet_set.name,custom_properties:{...workspace.value.sheet_set.custom_properties}},"metadata")}
function queueSubsetTitle(){if(selected.value)addCommand({type:"update_subset_title",subset_id:selected.value.id,title:selected.value.title},"structural")}
function queueSheetProperties(sheet:Sheet){addCommand({type:"update_sheet_properties",sheet_id:sheet.id,custom_properties:{...sheet.custom_properties}},"metadata")}
function queueDelete(sheet:Sheet){if(selected.value&&confirm(`删除图纸 ${sheet.number}？`))addCommand({type:"delete_sheet",sheet_id:sheet.id,delete_empty_subset:selected.value.sheets.length===1},"structural")}
function queuePropertyDefinition(){
  const name=propertyForm.name.trim();if(!name){error.value="属性名称不能为空";return}
  if(addCommand({type:"add_custom_property",property_type:propertyForm.type,name,default_value:propertyForm.defaultValue},"property")){propertyForm.name="";propertyForm.defaultValue=""}
}
function queueDeleteProperty(definition:PropertyDefinition){addCommand({type:"delete_custom_property",property_type:definition.type,name:definition.name},"property")}

function queueInsertSheet(){
  if(!workspace.value)return;
  const subset=workspace.value.sheet_set.subsets.find(item=>item.id===insertSheetForm.subsetId);
  if(!subset){error.value="请选择目标子集";return}
  const sequence=positiveInteger(insertSheetForm.sequence);
  const count=positiveInteger(insertSheetForm.count);
  if(sequence===null||sequence>subset.sheets.length){error.value=`图纸序号必须在 1 到 ${subset.sheets.length} 之间`;return}
  if(count===null){error.value="新增图纸数量必须为正整数";return}
  if(!insertSheetForm.sourceFile.trim()||!insertSheetForm.sourceLayout.trim()){error.value="来源文件和来源布局不能为空";return}
  addCommand({type:"insert_sheet",target_subset_id:subset.id,ordinal:sequence,placement:insertSheetForm.direction,count,source:{type:insertSheetForm.sourceType,file:insertSheetForm.sourceFile.trim(),layout:insertSheetForm.sourceLayout.trim()}},"structural");
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
  addCommand({type:"insert_subset",ordinal:sequence,placement:insertSubsetForm.direction,title:insertSubsetForm.title.trim(),initial_sheet_count:count,source:{type:"template_layout",file:insertSubsetForm.templateFile.trim(),layout:insertSubsetForm.templateLayout.trim()}},"structural");
}

async function showPreview(){
  if(isWorkspaceLoading.value||!workspace.value||!commands.value.length)return;
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
    job.value=result;if(result.status==="QUEUED"&&result.id)watchJob(result.id,context.workspaceId);else if(result.status==="SUCCEEDED")await refreshWorkspace(context.workspaceId);
  }
  catch(e){if(generation===jobMonitorGeneration&&workspace.value?.id===context.workspaceId&&!isWorkspaceLoading.value)error.value=String(e)}
}

function terminal(status:string){return ["SUCCEEDED","FAILED","ROLLED_BACK","BLOCKED_FILE_LOCK","NEEDS_REVIEW"].includes(status)}
function monitorMatches(generation:number,workspaceId:string){return generation===jobMonitorGeneration&&!isWorkspaceLoading.value&&workspace.value?.id===workspaceId}
function watchJob(id:string,workspaceId:string){
  const generation=invalidateJobMonitor(false);
  const events=new EventSource(`/api/jobs/${id}/events`);
  activeJobEvents=events;
  events.onmessage=async event=>{if(!monitorMatches(generation,workspaceId))return;const result:Job=JSON.parse(event.data);if(!monitorMatches(generation,workspaceId))return;job.value=result;if(terminal(result.status)){events.close();if(activeJobEvents===events)activeJobEvents=null;if(result.status==="SUCCEEDED")await refreshWorkspace(workspaceId)}};
  events.onerror=()=>{if(!monitorMatches(generation,workspaceId))return;events.close();if(activeJobEvents===events)activeJobEvents=null;connectionMode.value="轮询";schedulePoll(id,workspaceId,generation)};
}
function schedulePoll(id:string,workspaceId:string,generation:number){if(!monitorMatches(generation,workspaceId))return;if(pollTimer!==null)clearTimeout(pollTimer);pollTimer=window.setTimeout(()=>{pollTimer=null;void pollJob(id,workspaceId,generation)},1000)}
async function pollJob(id:string,workspaceId:string,generation:number){if(!monitorMatches(generation,workspaceId)||job.value&&terminal(job.value.status))return;try{const result:Job=await request(`/api/jobs/${id}`);if(!monitorMatches(generation,workspaceId))return;job.value=result;if(!terminal(result.status))schedulePoll(id,workspaceId,generation);else if(result.status==="SUCCEEDED")await refreshWorkspace(workspaceId)}catch(e){if(monitorMatches(generation,workspaceId))error.value=String(e)}}
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
  try{const result:Record<string,any>=await request(`/api/workspaces/${workspaceId}/revisions/${revisionId}/restore-preview`);if(!revisionRequestMatches(generation,loadGeneration,workspaceId))return;restorePreview.value=result;restorePreviewContext.value={workspaceId,baseRevisionId,revisionId,loadGeneration,result}}
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
    const result:Job=await request(`/api/workspaces/${context.workspaceId}/revisions/${context.revisionId}/restore`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId})});
    if(!restoreExecutionMatches(generation,context))return;
    job.value=result;restorePreview.value=null;restorePreviewContext.value=null;error.value="";await refreshWorkspace(context.workspaceId);if(workspace.value?.id===context.workspaceId&&!isWorkspaceLoading.value)await loadRevisionsInternal();
  }
  catch(e){if(restoreExecutionMatches(generation,context))error.value=String(e)}
  finally{if(generation===restoreExecutionGeneration)isRestoreExecuting.value=false}
}

function repairStatusLabel(status:string){switch(status){case"VALID":return"无问题";case"REPAIRED":return"已修复（待确认）";case"INVALID_REPAIR_REQUIRED":return"需补充信息（阻断）";case"INVALID_UNRECOVERABLE":return"不可恢复";default:return status}}
function repairAttr(value:Record<string,string|null>){const entries=Object.entries(value??{});return entries.length?entries.map(([k,v])=>`${k}=${v??'（空）'}`).join("，"):"—"}
async function previewRepair(){
  const current=workspace.value;
  if(isWorkspaceLoading.value||!current||isRepairPreviewing.value)return;
  const workspaceId=current.id,baseRevisionId=current.revision_id,loadGeneration=workspaceLoadGeneration,generation=++repairGeneration;
  repairPreview.value=null;repairContext.value=null;isRepairPreviewing.value=true;
  try{
    const result:Record<string,any>=await request(`/api/workspaces/${workspaceId}/repairs/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId})});
    // 代次/修订保护：旧修复报告不得覆盖新工作区
    if(generation!==repairGeneration||loadGeneration!==workspaceLoadGeneration||workspace.value?.id!==workspaceId||workspace.value.revision_id!==baseRevisionId)return;
    repairPreview.value=result;repairContext.value={workspaceId,baseRevisionId,previewDigest:result.preview_digest,loadGeneration};error.value="";
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
    const result:Preview=await request(`/api/workspaces/${workspaceId}/custom-properties/import/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId,csv:csvSnapshot})});
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
  try{const result:Job=await request(`/api/workspaces/${context.workspaceId}/custom-properties/import`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,csv:context.csv})});if(generation!==jobMonitorGeneration||isWorkspaceLoading.value||workspace.value?.id!==context.workspaceId)return;job.value=result;if(result.status==="QUEUED"&&result.id)watchJob(result.id,context.workspaceId);else if(result.status==="SUCCEEDED"&&!result.no_op)await refreshWorkspace(context.workspaceId)}
  catch(e){if(generation===jobMonitorGeneration&&workspace.value?.id===context.workspaceId&&!isWorkspaceLoading.value)error.value=String(e)}
}

function cadOperationLabel(operation?:string|null){
  if(operation==="rename_only")return "批量改名布局";
  if(operation==="rebuild")return "清除并重建布局";
  if(operation==="none")return "无需 CAD 操作";
  if(operation===undefined||operation===null||operation==="")return "未提供 CAD 操作";
  return `未知 CAD 操作：${operation}`;
}
</script>

<template>
  <header><div><h1>DST Manager</h1><span>v0.2.1 · 受控编辑与可恢复发布</span></div></header>
  <main>
    <section class="open"><input v-model="dstPath" placeholder="输入 .dst 绝对路径" @keyup.enter="openWorkspace"><button :disabled="isRestoreExecuting" @click="openWorkspace">打开项目</button><button :disabled="isWorkspaceLoading||isRestoreExecuting" @click="loadRevisions">修订历史</button></section>
    <p v-if="error" class="error notice">{{error}}</p>
    <p v-if="isWorkspaceLoading" class="panel loading" role="status">正在加载工作区…</p>
    <p v-if="isRestoreExecuting" class="panel loading" role="status">正在恢复修订…</p>

    <section v-if="job&&!isWorkspaceLoading" class="job-detail">
      <div class="job"><b>任务 {{job.id??'（无变更）'}}</b><span>{{job.status}} · {{job.progress??100}}% · 第 {{job.attempt??0}} 次</span><small>{{connectionMode}}</small><span v-if="job.error_code" class="error">{{job.error_code}}</span><button v-if="['FAILED','ROLLED_BACK','BLOCKED_FILE_LOCK','NEEDS_REVIEW'].includes(job.status)" @click="retryJob">安全重试</button></div>
      <p v-if="job.suggestion">{{job.suggestion}}</p>
      <table v-if="job.files?.length"><thead><tr><th>DWG</th><th>操作</th><th>状态</th><th>进度</th><th>开始</th><th>结束</th><th>耗时</th><th>错误</th></tr></thead><tbody><template v-for="file in job.files" :key="file.target_path"><tr><td>{{file.target_path}}</td><td>{{cadOperationLabel(file.cad_operation)}}</td><td>{{file.status}}</td><td>{{file.progress}}%</td><td>{{file.started_at??'-'}}</td><td>{{file.finished_at??'-'}}</td><td>{{file.duration_ms??'-'}} ms</td><td class="error">{{file.error_code}}</td></tr><tr v-if="file.log_summary"><td colspan="8"><details><summary>Core Console 输出日志</summary><pre>{{file.log_summary}}</pre></details></td></tr></template></tbody></table>
    </section>

    <section v-if="revisions.length&&!isWorkspaceLoading" class="panel preview"><h2>永久修订</h2><table><thead><tr><th>时间</th><th>修订</th><th>结果摘要</th><th></th></tr></thead><tbody><tr v-for="revision in revisions" :key="revision.id"><td>{{new Date(revision.created_at).toLocaleString()}}</td><td>{{revision.id.slice(0,16)}}</td><td>{{revision.before_hash.slice(0,8)}} → {{revision.result_hash.slice(0,8)}}</td><td><button :disabled="isRestoreExecuting" @click="previewRestore(revision)">恢复预览</button></td></tr></tbody></table><div v-if="restorePreview"><h3>恢复确认</h3><ul><li v-for="file in restorePreview.files" :key="file.path" :class="{error:file.conflict}">{{file.action}} {{file.path}} <span v-if="file.conflict">（当前文件冲突）</span></li></ul><button class="primary" :disabled="isRestoreExecuting||!restorePreview.executable" @click="restoreRevision">恢复为新修订</button></div></section>

    <template v-if="workspace&&!isWorkspaceLoading&&!isRestoreExecuting">
      <section class="summary"><div><small>图纸集</small><input v-model="workspace.sheet_set.name"><button @click="queueSheetSet">更新图纸集</button></div><div><small>子集</small><strong>{{workspace.sheet_set.subset_count}}</strong></div><div><small>图纸</small><strong>{{workspace.sheet_set.sheet_count}}</strong></div><div><small>阻断诊断</small><strong>{{blocking.length}}</strong></div><div><label>AutoCAD 版本<select v-model="cadVersion" @change="invalidatePreview"><option value="2016">2016</option><option value="2020">2020</option></select></label></div></section>
      <details v-if="Object.keys(workspace.sheet_set.custom_properties).length"><summary>图纸集自定义属性</summary><div class="form-grid"><label v-for="(_,name) in workspace.sheet_set.custom_properties" :key="name">{{name}}<input v-model="workspace.sheet_set.custom_properties[name]"></label></div><button @click="queueSheetSet">加入属性值变更</button></details>
      <details v-if="workspace.diagnostics.length"><summary>诊断（{{workspace.diagnostics.length}}）</summary><ul><li v-for="item in workspace.diagnostics" :key="item.code+item.message" :class="item.severity">{{item.code}}：{{item.message}}</li></ul></details>

      <section v-if="dstValidation&&dstValidation.status!=='VALID'" class="panel repair" :class="`repair-${dstValidation.status}`">
        <h2>DST 修复状态：{{repairStatusLabel(dstValidation.status)}}</h2>
        <p v-if="dstValidation.status==='REPAIRED'" class="warning">检测到可修复的元数据缺失，已在本机内存中修复；必须先确认并发布独立修复修订，普通编辑发布已被禁用。</p>
        <p v-if="dstValidation.status==='INVALID_REPAIR_REQUIRED'||dstValidation.status==='INVALID_UNRECOVERABLE'" class="error">存在阻断问题；当前只读，所有写入操作已禁用。请先修复 DST 后重新打开。</p>
        <details v-if="dstValidation.actions.length"><summary>修复明细（{{dstValidation.actions.length}}）</summary><ul class="repair-actions">
          <li v-for="(action,index) in dstValidation.actions" :key="index"><b>{{action.code}}</b> · {{action.confidence}} · {{action.object_id??'—'}}<br><span class="attr-diff">{{action.node_path}}</span><br><span class="attr-diff">前：{{repairAttr(action.before)}}</span><br><span class="attr-diff">后：{{repairAttr(action.after)}}</span><br>{{action.message}}</li>
        </ul></details>
        <details v-if="dstValidation.blocking_issues.length"><summary>阻断原因（{{dstValidation.blocking_issues.length}}）</summary><ul class="diagnostics"><li v-for="issue in dstValidation.blocking_issues" :key="issue.code+issue.message" :class="issue.severity"><b>{{issue.code}}</b>：{{issue.message}}</li></ul></details>
        <div v-if="dstValidation.status==='REPAIRED'" class="link-actions">
          <button :disabled="isRepairPreviewing||isRepairExecuting" @click="previewRepair">预览并确认修复</button>
          <template v-if="repairPreview">
            <span class="derived">修复 {{repairPreview.actions?.length??0}} 项 · 摘要 {{repairPreview.preview_digest?.slice(0,16)}}</span>
            <button class="primary" :disabled="isRepairExecuting||!repairPreview.executable" @click="executeRepair">确认发布修复修订</button>
            <button :disabled="isRepairExecuting" @click="repairPreview=null;repairContext=null">取消确认</button>
          </template>
        </div>
      </section>

      <section class="panel property-panel">
        <div class="section-title"><div><h2>属性定义</h2><p>属性定义与结构变更需分批预览和执行。</p></div><div class="link-actions"><a href="/api/custom-properties/template" download>下载 CSV 模板</a><a :href="`/api/workspaces/${workspace.id}/custom-properties/export`" download>导出当前属性</a></div></div>
        <table><thead><tr><th>作用域</th><th>名称</th><th>默认值</th><th></th></tr></thead><tbody><tr v-for="definition in workspace.sheet_set.property_definitions" :key="definition.type+definition.name"><td>{{definition.type}}</td><td>{{definition.name}}</td><td>{{definition.default_value||'（空）'}}</td><td><button class="danger" @click="queueDeleteProperty(definition)">删除 {{definition.name}}</button></td></tr></tbody></table>
        <div class="form-row"><label>属性作用域<select v-model="propertyForm.type"><option value="sheet">图纸</option><option value="sheetset">图纸集</option></select></label><label>属性名称<input v-model="propertyForm.name"></label><label>默认值<input v-model="propertyForm.defaultValue"></label><button @click="queuePropertyDefinition">加入属性定义</button></div>
        <div class="csv-flow"><label>属性 CSV 文件<input type="file" accept=".csv,text/csv" @change="readCsvFile"></label><button :disabled="!csvText" @click="previewCsv">预览 CSV 导入</button><button class="primary" :disabled="repairWritesDisabled||!csvPreviewContext?.result.executable" @click="importCsv">确认导入</button></div>
        <div v-if="csvPreview" class="csv-preview"><h3>CSV 合并预览</h3><ul><li v-for="change in csvPreview.changes" :key="`${change.line}-${change.type}-${change.name}`">第 {{change.line}} 行 · {{change.action}} · {{change.type}} · {{change.name}}</li></ul><ul class="diagnostics"><li v-for="item in csvPreview.diagnostics" :key="`${item.line}-${item.code}`" :class="item.severity"><span v-if="item.line">第 {{item.line}} 行 · </span><b>{{item.code}}</b>：{{item.message}}</li></ul></div>
      </section>

      <section class="editor">
        <aside><button v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :class="{active:selectedId===subset.id}" @click="selectedId=subset.id;insertSheetForm.subsetId=subset.id">{{subset.display_name}} <b>{{subset.sheets.length}}</b></button></aside>
        <article>
          <div class="toolbar"><span>待处理 {{commands.length}}</span><button :disabled="!commands.length" @click="clearCommands">清空</button><button :disabled="!commands.length||repairWritesDisabled||isWorkspaceLoading" @click="showPreview">预览变更</button></div>
          <section v-if="selected" class="subset-editor"><div class="form-row"><label>当前子集标题<input v-model="selected.title"></label><button @click="queueSubsetTitle">加入标题变更</button></div><p class="derived">只读图号范围：{{selected.number_range||'—'}} · 显示名：{{selected.display_name}}</p>
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

      <section v-if="preview" class="panel preview"><h2>完整变更预览</h2>
        <section><h3>前后有序结构</h3><div class="group-grid"><article v-for="side in ['before','after']" :key="side"><h4>{{side==='before'?'变更前':'变更后'}}</h4><table><thead><tr><th>位置</th><th>子集 / 图纸</th><th>图号范围 / 后缀</th><th>DWG / 布局</th></tr></thead><tbody><template v-for="subset in semanticDiff.structure?.[side]??[]" :key="subset.id"><tr><td>{{subset.position}}</td><td>{{subset.display_name}} · {{subset.title}}</td><td>{{subset.number_range}}</td><td>{{subset.dwg_file}}</td></tr><tr v-for="sheet in subset.sheets" :key="sheet.id"><td>{{subset.position}}.{{sheet.position}}</td><td>{{sheet.number}} · {{sheet.title}}</td><td>{{sheet.suffix||'—'}}</td><td>{{sheet.dwg_file}} · {{sheet.layout_name}}</td></tr></template></tbody></table></article></div></section>
        <section v-if="semanticDiff.properties?.length"><h3>属性差异</h3><table><thead><tr><th>操作</th><th>作用域</th><th>名称</th><th>前值</th><th>后值</th><th>受影响图纸</th></tr></thead><tbody><tr v-for="item in semanticDiff.properties" :key="`${item.action}-${item.type}-${item.name}`"><td>{{item.action}}</td><td>{{item.type}}</td><td>{{item.name}}</td><td>{{formatSemanticValue(item.before)}}</td><td>{{formatSemanticValue(item.after)}}</td><td>{{item.affected_sheet_count}}</td></tr></tbody></table></section>
        <section v-if="semanticDiff.dwgs?.length"><h3>DWG 与布局差异</h3><table><thead><tr><th>操作</th><th>变更前文件 / 布局</th><th>变更后文件 / 布局</th></tr></thead><tbody><tr v-for="item in semanticDiff.dwgs" :key="`${item.action}-${item.subset_id}`"><td>{{item.action}}</td><td>{{item.before?.file??'—'}} · {{item.before?.layouts?.join('、')??'—'}}</td><td>{{item.after?.file??'—'}} · {{item.after?.layouts?.join('、')??'—'}}</td></tr></tbody></table></section>
        <section v-if="cadValidationDeferred" class="notice"><h3>CAD 校验</h3><p>CAD 布局校验将在确认后执行</p></section>
        <section v-if="cardinalityFrontier"><h3>数量变化前沿</h3><p>数量变化前沿：第 {{cardinalityFrontier.index + 1}} 个子集</p></section>
        <section v-if="subsetOperations.length"><h3>子集 CAD 操作</h3><table><thead><tr><th>子集</th><th>操作</th><th>目标 DWG</th><th>数量前沿范围</th></tr></thead><tbody><tr v-for="item in subsetOperations" :key="item.subset_id"><td>{{item.subset_id}}</td><td>{{cadOperationLabel(item.cad_operation)}}</td><td>{{item.target_file}}</td><td>{{item.in_cardinality_scope ? '是' : '否'}}</td></tr></tbody></table></section>
        <section v-if="sourceBaselines.length"><h3>来源基准</h3><table><thead><tr><th>来源路径</th><th>SHA-256</th><th>请求布局</th><th>来源类型</th></tr></thead><tbody><tr v-for="item in sourceBaselines" :key="item.path"><td>{{item.path}}</td><td>{{item.sha256}}</td><td>{{item.requested_layouts?.join('、')}}</td><td>{{item.source_types?.join('、')}}</td></tr></tbody></table></section>
        <section v-if="preview.execution_intent"><h3>图号范围变化</h3><table v-if="derivedSubsets.length"><thead><tr><th>服务端图号范围</th><th>服务端显示名</th><th>服务端标题</th></tr></thead><tbody><tr v-for="subset in derivedSubsets" :key="subset.acsm_id"><td>{{subset.number_range}}</td><td>{{subset.display_name}}</td><td>{{subset.title}}</td></tr></tbody></table></section>
        <section><h3>兼容变更清单</h3><ul><li v-for="(change,index) in preview.changes" :key="index"><strong>{{change.label??change.type}}</strong><span v-if="change.affected_sheet_count!==undefined"> · 受影响图纸 {{change.affected_sheet_count}}</span></li></ul></section>
        <section v-if="previewGroups.length"><h3>CAD 执行分组</h3><div class="group-grid"><article v-for="group in previewGroups" :key="group.subset_id??group.target_file" class="execution-group"><strong>{{cadOperationLabel(group.cad_operation)}}</strong><h4>{{group.subset_name}}</h4><p>{{group.target_file}}</p><table><thead><tr><th>图号</th><th>服务端标题</th><th>目标布局</th></tr></thead><tbody><tr v-for="layout in group.layouts" :key="layout.sheet_id??layout.target_layout??layout.layout_name"><td>{{layout.number}}</td><td>{{layout.title}}</td><td>{{layout.target_layout??layout.layout_name}}</td></tr></tbody></table></article></div></section>
        <section><h3>诊断</h3><ul class="diagnostics"><li v-for="item in preview.diagnostics" :key="item.code+item.message" :class="item.severity"><b>{{item.code}}</b>：{{item.message}}</li><li v-if="!preview.diagnostics?.length">无阻断诊断</li></ul></section>
        <section><h3>受影响文件</h3><ul><li v-for="file in preview.affected_files" :key="file">{{file}}</li></ul></section>
        <button class="primary" :disabled="repairWritesDisabled||preview.executable===false" @click="execute">确认并执行</button>
      </section>
    </template>
  </main>
</template>
