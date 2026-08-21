<script setup lang="ts">
import {computed,reactive,ref} from "vue";

type PropertyType="sheetset"|"sheet";
type PropertyDefinition={type:PropertyType;name:string;default_value:string};
type Sheet={id:string;number:string;title:string;custom_properties:Record<string,string>};
type Subset={id:string;name:string;title:string;number_range:string;display_name:string;sheets:Sheet[]};
type Workspace={id:string;revision_id:string;sheet_set:{name:string;sheet_count:number;subset_count:number;custom_properties:Record<string,string>;property_definitions:PropertyDefinition[];subsets:Subset[]};diagnostics:{severity:string;code:string;message:string}[]};
type JobFile={target_path:string;status:string;progress:number;duration_ms?:number;error_code?:string;log_summary?:string};
type Job={id:string|null;status:string;progress:number;attempt?:number;error_code?:string;suggestion?:string;files?:JobFile[];no_op?:boolean};
type Revision={id:string;created_at:string;before_hash:string;result_hash:string};
type Diagnostic={severity:string;code:string;message:string;line?:number};
type Preview={executable:boolean;requires_cad?:boolean;changes?:Record<string,any>[];diagnostics?:Diagnostic[];affected_files?:string[];execution_intent?:Record<string,any>|null};
type PreviewContext={workspaceId:string;baseRevisionId:string;commands:Record<string,unknown>[];result:Preview};
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
const connectionMode=ref("SSE");
const csvText=ref("");
const csvPreview=ref<Preview|null>(null);
const csvPreviewContext=ref<CsvPreviewContext|null>(null);
const isWorkspaceLoading=ref(false);
const isRestoreExecuting=ref(false);
let previewGeneration=0;
let csvGeneration=0;
let workspaceLoadGeneration=0;
let jobMonitorGeneration=0;
let revisionGeneration=0;
let restoreExecutionGeneration=0;
let activeJobEvents:EventSource|null=null;
let pollTimer:number|null=null;

const propertyForm=reactive<{type:PropertyType;name:string;defaultValue:string}>({type:"sheet",name:"",defaultValue:""});
const insertSheetForm=reactive({subsetId:"",sequence:"1",direction:"after",count:"1",sourceType:"template_layout",sourceFile:"",sourceLayout:""});
const insertSubsetForm=reactive({sequence:"1",direction:"after",title:"",initialSheetCount:"1",templateFile:"",templateLayout:""});

const selected=computed(()=>workspace.value?.sheet_set.subsets.find(item=>item.id===selectedId.value)??null);
const blocking=computed(()=>workspace.value?.diagnostics.filter(item=>item.severity==="error")??[]);
const hasPropertyDefinitionCommands=computed(()=>commands.value.some(item=>item.type==="add_custom_property"||item.type==="delete_custom_property"));
const hasStructuralCommands=computed(()=>commands.value.some(item=>["update_subset_title","delete_sheet","insert_sheet","insert_subset"].includes(String(item.type))));
const previewGroups=computed(()=>preview.value?.execution_intent?.groups??[]);
const derivedSubsets=computed(()=>preview.value?.execution_intent?.derived_document?.subsets??[]);

async function request(url:string,options?:RequestInit){
  const response=await fetch(url,{headers:{"Content-Type":"application/json"},...options});
  const body=await response.json();
  if(!response.ok)throw new Error(body.message??body.detail??"请求失败");
  return body;
}

function cloneJson<T>(value:T):T{return JSON.parse(JSON.stringify(value))}
function invalidatePreview(){previewGeneration+=1;preview.value=null;previewContext.value=null}
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
  const commandSnapshot=cloneJson(commands.value);
  const generation=++previewGeneration;
  preview.value=null;previewContext.value=null;
  try{
    const result:Preview=await request(`/api/workspaces/${workspaceId}/changes/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId,commands:commandSnapshot})});
    if(generation!==previewGeneration||workspace.value?.id!==workspaceId||workspace.value.revision_id!==baseRevisionId)return;
    preview.value=result;previewContext.value={workspaceId,baseRevisionId,commands:commandSnapshot,result};error.value="";
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
    const result:Job=await request(`/api/workspaces/${context.workspaceId}/changes/execute`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,commands:cloneJson(context.commands),cad_version:"2020"})});
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

function operationLabel(operation:string){return operation==="create"?"创建 DWG":"重建 DWG"}
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
      <table v-if="job.files?.length"><thead><tr><th>DWG</th><th>状态</th><th>进度</th><th>耗时</th><th>错误</th></tr></thead><tbody><template v-for="file in job.files" :key="file.target_path"><tr><td>{{file.target_path}}</td><td>{{file.status}}</td><td>{{file.progress}}%</td><td>{{file.duration_ms??'-'}} ms</td><td class="error">{{file.error_code}}</td></tr><tr v-if="file.log_summary"><td colspan="5"><details><summary>Core Console 输出日志</summary><pre>{{file.log_summary}}</pre></details></td></tr></template></tbody></table>
    </section>

    <section v-if="revisions.length&&!isWorkspaceLoading" class="panel preview"><h2>永久修订</h2><table><thead><tr><th>时间</th><th>修订</th><th>结果摘要</th><th></th></tr></thead><tbody><tr v-for="revision in revisions" :key="revision.id"><td>{{new Date(revision.created_at).toLocaleString()}}</td><td>{{revision.id.slice(0,16)}}</td><td>{{revision.before_hash.slice(0,8)}} → {{revision.result_hash.slice(0,8)}}</td><td><button :disabled="isRestoreExecuting" @click="previewRestore(revision)">恢复预览</button></td></tr></tbody></table><div v-if="restorePreview"><h3>恢复确认</h3><ul><li v-for="file in restorePreview.files" :key="file.path" :class="{error:file.conflict}">{{file.action}} {{file.path}} <span v-if="file.conflict">（当前文件冲突）</span></li></ul><button class="primary" :disabled="isRestoreExecuting||!restorePreview.executable" @click="restoreRevision">恢复为新修订</button></div></section>

    <template v-if="workspace&&!isWorkspaceLoading&&!isRestoreExecuting">
      <section class="summary"><div><small>图纸集</small><input v-model="workspace.sheet_set.name"><button @click="queueSheetSet">更新图纸集</button></div><div><small>子集</small><strong>{{workspace.sheet_set.subset_count}}</strong></div><div><small>图纸</small><strong>{{workspace.sheet_set.sheet_count}}</strong></div><div><small>阻断诊断</small><strong>{{blocking.length}}</strong></div></section>
      <details v-if="Object.keys(workspace.sheet_set.custom_properties).length"><summary>图纸集自定义属性</summary><div class="form-grid"><label v-for="(_,name) in workspace.sheet_set.custom_properties" :key="name">{{name}}<input v-model="workspace.sheet_set.custom_properties[name]"></label></div><button @click="queueSheetSet">加入属性值变更</button></details>
      <details v-if="workspace.diagnostics.length"><summary>诊断（{{workspace.diagnostics.length}}）</summary><ul><li v-for="item in workspace.diagnostics" :key="item.code+item.message" :class="item.severity">{{item.code}}：{{item.message}}</li></ul></details>

      <section class="panel property-panel">
        <div class="section-title"><div><h2>属性定义</h2><p>属性定义与结构变更需分批预览和执行。</p></div><div class="link-actions"><a href="/api/custom-properties/template" download>下载 CSV 模板</a><a :href="`/api/workspaces/${workspace.id}/custom-properties/export`" download>导出当前属性</a></div></div>
        <table><thead><tr><th>作用域</th><th>名称</th><th>默认值</th><th></th></tr></thead><tbody><tr v-for="definition in workspace.sheet_set.property_definitions" :key="definition.type+definition.name"><td>{{definition.type}}</td><td>{{definition.name}}</td><td>{{definition.default_value||'（空）'}}</td><td><button class="danger" @click="queueDeleteProperty(definition)">删除 {{definition.name}}</button></td></tr></tbody></table>
        <div class="form-row"><label>属性作用域<select v-model="propertyForm.type"><option value="sheet">图纸</option><option value="sheetset">图纸集</option></select></label><label>属性名称<input v-model="propertyForm.name"></label><label>默认值<input v-model="propertyForm.defaultValue"></label><button @click="queuePropertyDefinition">加入属性定义</button></div>
        <div class="csv-flow"><label>属性 CSV 文件<input type="file" accept=".csv,text/csv" @change="readCsvFile"></label><button :disabled="!csvText" @click="previewCsv">预览 CSV 导入</button><button class="primary" :disabled="!csvPreviewContext?.result.executable" @click="importCsv">确认导入</button></div>
        <div v-if="csvPreview" class="csv-preview"><h3>CSV 合并预览</h3><ul><li v-for="change in csvPreview.changes" :key="`${change.line}-${change.type}-${change.name}`">第 {{change.line}} 行 · {{change.action}} · {{change.type}} · {{change.name}}</li></ul><ul class="diagnostics"><li v-for="item in csvPreview.diagnostics" :key="`${item.line}-${item.code}`" :class="item.severity"><span v-if="item.line">第 {{item.line}} 行 · </span><b>{{item.code}}</b>：{{item.message}}</li></ul></div>
      </section>

      <section class="editor">
        <aside><button v-for="subset in workspace.sheet_set.subsets" :key="subset.id" :class="{active:selectedId===subset.id}" @click="selectedId=subset.id;insertSheetForm.subsetId=subset.id">{{subset.display_name}} <b>{{subset.sheets.length}}</b></button></aside>
        <article>
          <div class="toolbar"><span>待处理 {{commands.length}}</span><button :disabled="!commands.length" @click="clearCommands">清空</button><button :disabled="!commands.length" @click="showPreview">预览变更</button></div>
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
        <section v-if="preview.execution_intent"><h3>图号范围变化</h3><table v-if="derivedSubsets.length"><thead><tr><th>服务端图号范围</th><th>服务端显示名</th><th>服务端标题</th></tr></thead><tbody><tr v-for="subset in derivedSubsets" :key="subset.acsm_id"><td>{{subset.number_range}}</td><td>{{subset.display_name}}</td><td>{{subset.title}}</td></tr></tbody></table></section>
        <section><h3>变更</h3><ul><li v-for="(change,index) in preview.changes" :key="index"><strong>{{change.label??change.type}}</strong><span v-if="change.before!==undefined||change.after!==undefined">：{{change.before??'—'}} → {{change.after??'—'}}</span></li></ul></section>
        <section v-if="previewGroups.length"><h3>CAD 执行分组</h3><div class="group-grid"><article v-for="group in previewGroups" :key="group.subset_id??group.target_file" class="execution-group"><strong>{{operationLabel(group.operation)}}</strong><h4>{{group.subset_name}}</h4><p>{{group.target_file}}</p><table><thead><tr><th>图号</th><th>服务端标题</th><th>目标布局</th></tr></thead><tbody><tr v-for="layout in group.layouts" :key="layout.sheet_id??layout.target_layout??layout.layout_name"><td>{{layout.number}}</td><td>{{layout.title}}</td><td>{{layout.target_layout??layout.layout_name}}</td></tr></tbody></table></article></div></section>
        <section><h3>诊断</h3><ul class="diagnostics"><li v-for="item in preview.diagnostics" :key="item.code+item.message" :class="item.severity"><b>{{item.code}}</b>：{{item.message}}</li><li v-if="!preview.diagnostics?.length">无阻断诊断</li></ul></section>
        <section><h3>受影响文件</h3><ul><li v-for="file in preview.affected_files" :key="file">{{file}}</li></ul></section>
        <button class="primary" :disabled="preview.executable===false" @click="execute">确认并执行</button>
      </section>
    </template>
  </main>
</template>
