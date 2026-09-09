// 自定义属性 CSV 导入域组合式函数：文件读取、行级预览与导入发布（Task 3 拆分；
// Task 5 增加分批门禁：属性定义草稿与 CSV 导入冲突时阻断，预览失效判定仍由调用方按代次/基准驱动）
import {ref} from "vue";
import type {Ref} from "vue";
import {useI18n} from "vue-i18n";
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
  // 命令簿中已有属性定义草稿（add/delete_custom_property）时 CSV 导入与其冲突，必须分批（PLAN-DM-016 任务 5）
  hasConflictingDraft:()=>boolean;
}){
  const {t}=useI18n();
  // 稳定 action/type 枚举 → 语义键映射（I18N-16：协议稳定码本身不翻译）
  const CSV_ACTION_KEYS: Record<string,string>={add:"properties.csv.actions.add",skip:"properties.csv.actions.skip",conflict:"properties.csv.actions.conflict"};
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
    catch{if(generation===csvGeneration)deps.error.value=t("properties.csv.errors.notUtf8")}
  }
  async function previewCsv(){
    if(deps.isWorkspaceLoading.value||!deps.workspace.value||!csvText.value){deps.error.value=t("properties.csv.errors.pickUtf8Csv");return}
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
    // 分批门禁（PLAN-DM-016 任务 5）：命令簿已有属性定义草稿时 CSV 导入与其冲突，
    // 明确阻断并要求分批；预览上下文与草稿任何一方都不清空，由用户自行取舍。
    if(deps.hasConflictingDraft()){deps.error.value=t("properties.csv.errors.conflictingDraft");return}
    const context=csvPreviewContext.value;
    if(!context||!context.result.executable)return;
    const current=deps.workspace.value;
    if(deps.isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId){invalidateCsvPreview();deps.error.value=t("properties.csv.errors.contextStale");return}
    // 属性定义导入为正式写入（SPEC-DM-006 §6.2/§10.3）：CSV/XML 不得走弱确认旁路，与 §9.1 全部正式写入共用同一危险确认
    // 影响行句子用命名参数插值（I18N-08）；action/type 走稳定码映射，属性名与 CSV 内容保持原样（I18N-16）
    const impactLines=context.result.changes.map(change=>{
      const action=t(CSV_ACTION_KEYS[change.action]??CSV_ACTION_KEYS.conflict);
      const scope=t(change.type==="sheetset"?"properties.scope.sheetset":"properties.scope.sheet");
      return change.affected_sheet_count
        ? t("properties.csv.impactChange",{action,name:change.name,scope,count:change.affected_sheet_count})
        : t("properties.csv.impactChangeNoCount",{action,name:change.name,scope});
    });
    if(impactLines.length===0)impactLines.push(...(context.result.affected_files.length>0?context.result.affected_files.map(file=>t("properties.csv.impactFile",{file})):[t("properties.csv.noDefinitionChanges")]));
    const ok=await deps.confirmAction({title:t("properties.csv.confirmTitle"),message:t("properties.csv.confirmMessage"),impactLines,confirmText:t("properties.csv.confirmImport"),danger:true,requireCheckbox:true,reversibility:"irreversible"});
    if(!ok)return;
    const generation=deps.invalidateJobMonitor(false);
    try{const result:Job=await request(`/api/workspaces/${context.workspaceId}/custom-properties/import`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,csv:context.csv,preview_digest:context.result.preview_digest})});if(!deps.isCurrentJobGeneration(generation)||deps.isWorkspaceLoading.value||deps.workspace.value?.id!==context.workspaceId)return;deps.setJob(result);if(result.status==="QUEUED"&&result.id)deps.watchJob(result.id,context.workspaceId);else if(result.status==="SUCCEEDED"&&!result.no_op)await deps.refreshWorkspace(context.workspaceId)}
    catch(e){if(deps.isCurrentJobGeneration(generation)&&deps.workspace.value?.id===context.workspaceId&&!deps.isWorkspaceLoading.value)deps.error.value=String(e)}
  }

  return {csvText,csvPreview,csvPreviewContext,readCsvFile,previewCsv,importCsv,invalidateCsvPreview};
}
