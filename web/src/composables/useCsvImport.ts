// 自定义属性 CSV 导入域组合式函数：文件读取、行级预览与导入发布（Task 3 拆分，行为零变化）
import {ref} from "vue";
import type {Ref} from "vue";
import {request} from "../api/client";
import type {CsvPreview,Job,Workspace} from "../api/contracts";
import type {ConfirmOptions} from "./useConfirm";

export type CsvPreviewContext={workspaceId:string;baseRevisionId:string;csv:string;result:CsvPreview};

export function useCsvImport(deps:{
  workspace:Ref<Workspace|null>;
  isWorkspaceLoading:Ref<boolean>;
  watchJob(id:string,workspaceId:string):void;
  setJob(job:Job):void;
  refreshWorkspace(id:string):Promise<void>;
  invalidateJobMonitor(clearJob:boolean):number;
  isCurrentJobGeneration(generation:number):boolean;
  error:Ref<string>;
  confirmAction(options:ConfirmOptions):Promise<boolean>;
}){
  const csvText=ref("");
  const csvPreview=ref<CsvPreview|null>(null);
  const csvPreviewContext=ref<CsvPreviewContext|null>(null);
  let csvGeneration=0;

  function invalidateCsvPreview(clearText=false){csvGeneration+=1;csvPreview.value=null;csvPreviewContext.value=null;if(clearText)csvText.value=""}
  async function readCsvFile(event:Event){
    const generation=++csvGeneration;
    csvText.value="";csvPreview.value=null;csvPreviewContext.value=null;deps.error.value="";
    const file=(event.target as HTMLInputElement).files?.[0];
    if(!file)return;
    try{
      const decoded=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());
      if(generation!==csvGeneration)return;
      csvText.value=decoded;
    }
    catch{if(generation===csvGeneration)deps.error.value="CSV 必须使用 UTF-8 编码"}
  }
  async function previewCsv(){
    if(deps.isWorkspaceLoading.value||!deps.workspace.value||!csvText.value){deps.error.value="请选择 UTF-8 CSV 文件";return}
    const workspaceId=deps.workspace.value.id;
    const baseRevisionId=deps.workspace.value.revision_id;
    const csvSnapshot=csvText.value;
    const generation=++csvGeneration;
    csvPreview.value=null;csvPreviewContext.value=null;
    try{
      const result:CsvPreview=await request(`/api/workspaces/${workspaceId}/custom-properties/import/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId,csv:csvSnapshot})});
      if(generation!==csvGeneration||deps.workspace.value?.id!==workspaceId||deps.workspace.value.revision_id!==baseRevisionId||csvText.value!==csvSnapshot)return;
      csvPreview.value=result;csvPreviewContext.value={workspaceId,baseRevisionId,csv:csvSnapshot,result};deps.error.value="";
    }
    catch(e){if(generation===csvGeneration)deps.error.value=String(e)}
  }
  async function importCsv(){
    const context=csvPreviewContext.value;
    if(!context||!context.result.executable)return;
    const current=deps.workspace.value;
    if(deps.isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId){invalidateCsvPreview();deps.error.value="工作区或基准修订已变化，请重新预览 CSV";return}
    // 属性定义导入为正式写入（SPEC-DM-006 §6.2/§10.3）：CSV/XML 不得走弱确认旁路，与 §9.1 全部正式写入共用同一危险确认
    const impactLines=context.result.changes.map(change=>{
      const action=change.action==="add"?"新增":change.action==="skip"?"跳过":"冲突";
      const scope=change.type==="sheetset"?"图纸集":"图纸";
      return `${action}属性「${change.name}」（${scope}${change.affected_sheet_count?`，影响 ${change.affected_sheet_count} 张图纸`:""}）`;
    });
    if(impactLines.length===0)impactLines.push(...(context.result.affected_files.length>0?context.result.affected_files.map(file=>`受影响文件：${file}`):["本次导入不含属性定义变更"]));
    const ok=await deps.confirmAction({title:"确认导入属性定义",message:"将按预览结果把属性定义合并写入图纸集，原 DST 将永久备份。",impactLines,confirmText:"确认导入",danger:true,requireCheckbox:true,reversibility:"不可逆"});
    if(!ok)return;
    const generation=deps.invalidateJobMonitor(false);
    try{const result:Job=await request(`/api/workspaces/${context.workspaceId}/custom-properties/import`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,csv:context.csv,preview_digest:context.result.preview_digest})});if(!deps.isCurrentJobGeneration(generation)||deps.isWorkspaceLoading.value||deps.workspace.value?.id!==context.workspaceId)return;deps.setJob(result);if(result.status==="QUEUED"&&result.id)deps.watchJob(result.id,context.workspaceId);else if(result.status==="SUCCEEDED"&&!result.no_op)await deps.refreshWorkspace(context.workspaceId)}
    catch(e){if(deps.isCurrentJobGeneration(generation)&&deps.workspace.value?.id===context.workspaceId&&!deps.isWorkspaceLoading.value)deps.error.value=String(e)}
  }

  return {csvText,csvPreview,csvPreviewContext,readCsvFile,previewCsv,importCsv,invalidateCsvPreview};
}
