// 修订恢复域组合式函数：修订历史、恢复预览与"恢复为新修订"执行（Task 3 拆分，行为零变化）
import {ref} from "vue";
import type {Ref} from "vue";
import {request} from "../api/client";
import type {Job,RestorePreview,Revision,Workspace} from "../api/contracts";
import type {ConfirmOptions} from "./useConfirm";

export type RestorePreviewContext={workspaceId:string;baseRevisionId:string;revisionId:string;loadGeneration:number;result:RestorePreview};

export function useRestore(deps:{
  workspace:Ref<Workspace|null>;
  isWorkspaceLoading:Ref<boolean>;
  refreshWorkspace(id:string):Promise<void>;
  setJob(job:Job):void;
  invalidateJobMonitor(clearJob:boolean):number;
  isCurrentJobGeneration(generation:number):boolean;
  workspaceLoadGeneration:Ref<number>;
  isRestoreExecuting:Ref<boolean>;
  error:Ref<string>;
  confirmAction(options:ConfirmOptions):Promise<boolean>;
}):{
  revisions:Ref<Revision[]>;
  restorePreview:Ref<RestorePreview|null>;
  restorePreviewContext:Ref<RestorePreviewContext|null>;
  isRestoreExecuting:Ref<boolean>;
  loadRevisions():Promise<void>;
  loadRevisionsInternal():Promise<void>;
  previewRestore(revision:Revision):Promise<void>;
  restoreRevision():Promise<void>;
  invalidateRevisionState():void;
}{
  const revisions=ref<Revision[]>([]);
  const restorePreview=ref<RestorePreview|null>(null);
  const restorePreviewContext=ref<RestorePreviewContext|null>(null);
  let revisionGeneration=0;
  let restoreExecutionGeneration=0;

  function invalidateRevisionState(){revisionGeneration+=1;revisions.value=[];restorePreview.value=null;restorePreviewContext.value=null}
  function revisionRequestMatches(generation:number,loadGeneration:number,workspaceId:string){return generation===revisionGeneration&&loadGeneration===deps.workspaceLoadGeneration.value&&!deps.isWorkspaceLoading.value&&deps.workspace.value?.id===workspaceId}
  async function loadRevisions(){
    if(deps.isRestoreExecuting.value)return;
    await loadRevisionsInternal();
  }
  async function loadRevisionsInternal(){
    const current=deps.workspace.value;if(!current||deps.isWorkspaceLoading.value)return;
    const workspaceId=current.id,loadGeneration=deps.workspaceLoadGeneration.value,generation=++revisionGeneration;
    revisions.value=[];restorePreview.value=null;restorePreviewContext.value=null;
    try{const result:Revision[]=await request(`/api/revisions?workspace_id=${workspaceId}`);if(revisionRequestMatches(generation,loadGeneration,workspaceId))revisions.value=result}
    catch(e){if(revisionRequestMatches(generation,loadGeneration,workspaceId))deps.error.value=String(e)}
  }
  async function previewRestore(revision:Revision){
    const current=deps.workspace.value;if(!current||deps.isWorkspaceLoading.value||deps.isRestoreExecuting.value)return;
    const workspaceId=current.id,baseRevisionId=current.revision_id,revisionId=revision.id,loadGeneration=deps.workspaceLoadGeneration.value,generation=++revisionGeneration;
    restorePreview.value=null;restorePreviewContext.value=null;
    try{const result:RestorePreview=await request(`/api/workspaces/${workspaceId}/revisions/${revisionId}/restore-preview`);if(!revisionRequestMatches(generation,loadGeneration,workspaceId))return;restorePreview.value=result;restorePreviewContext.value={workspaceId,baseRevisionId,revisionId,loadGeneration,result}}
    catch(e){if(revisionRequestMatches(generation,loadGeneration,workspaceId))deps.error.value=String(e)}
  }
  function restoreExecutionMatches(generation:number,context:RestorePreviewContext){return generation===restoreExecutionGeneration&&context.loadGeneration===deps.workspaceLoadGeneration.value&&!deps.isWorkspaceLoading.value&&deps.workspace.value?.id===context.workspaceId&&deps.workspace.value.revision_id===context.baseRevisionId}
  async function restoreRevision(){
    const context=restorePreviewContext.value,current=deps.workspace.value;
    if(deps.isRestoreExecuting.value||!context||!context.result.executable)return;
    if(deps.isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId||context.loadGeneration!==deps.workspaceLoadGeneration.value){restorePreview.value=null;restorePreviewContext.value=null;deps.error.value="工作区或基准修订已变化，请重新生成恢复预览";return}
    // 恢复为新修订属不可逆破坏类操作：需要显式勾选后才可确认
    const ok=await deps.confirmAction({title:"确认恢复为新修订",message:"历史修订不会被覆盖。",confirmText:"确认恢复",danger:true,requireCheckbox:true,reversibility:"不可逆"});
    if(!ok)return;
    const generation=++restoreExecutionGeneration;
    deps.isRestoreExecuting.value=true;deps.invalidateJobMonitor(true);revisionGeneration+=1;
    try{
      const result:Job=await request(`/api/workspaces/${context.workspaceId}/revisions/${context.revisionId}/restore`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,preview_digest:context.result.preview_digest})});
      if(!restoreExecutionMatches(generation,context))return;
      deps.setJob(result);restorePreview.value=null;restorePreviewContext.value=null;deps.error.value="";
      // fix round 1（裁决）：refreshWorkspace 仅 SUCCEEDED 时执行——QUEUED/终态 FAILED 等由浮层实施进度页签呈现，避免无条件复位把刚展开的浮层闪关（对齐 execute/executeRepair/importCsv 三入口）
      if(result.status==="SUCCEEDED"){await deps.refreshWorkspace(context.workspaceId);if(deps.workspace.value?.id===context.workspaceId&&!deps.isWorkspaceLoading.value)await loadRevisionsInternal()}
    }
    catch(e){if(restoreExecutionMatches(generation,context))deps.error.value=String(e)}
    finally{if(generation===restoreExecutionGeneration)deps.isRestoreExecuting.value=false}
  }

  return {revisions,restorePreview,restorePreviewContext,isRestoreExecuting:deps.isRestoreExecuting,loadRevisions,loadRevisionsInternal,previewRestore,restoreRevision,invalidateRevisionState};
}
