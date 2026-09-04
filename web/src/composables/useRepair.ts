// 内存修复域组合式函数：修复预览、独立修订发布与写入门禁（Task 3 拆分，行为零变化）
import {computed,ref} from "vue";
import type {ComputedRef,Ref} from "vue";
import {request} from "../api/client";
import type {DstValidation,Job,RepairPreview,Workspace} from "../api/contracts";
import type {ConfirmOptions} from "./useConfirm";

export type RepairContext={workspaceId:string;baseRevisionId:string;previewDigest:string|undefined;loadGeneration:number};

export function useRepair(deps:{
  workspace:Ref<Workspace|null>;
  isWorkspaceLoading:Ref<boolean>;
  isRestoreExecuting:Ref<boolean>;
  refreshWorkspace(id:string):Promise<void>;
  setJob(job:Job):void;
  invalidateJobMonitor(clearJob:boolean):number;
  isCurrentJobGeneration(generation:number):boolean;
  workspaceLoadGeneration:Ref<number>;
  error:Ref<string>;
  confirmAction(options:ConfirmOptions):Promise<boolean>;
}):{
  repairPreview:Ref<RepairPreview|null>;
  repairContext:Ref<RepairContext|null>;
  isRepairPreviewing:Ref<boolean>;
  isRepairExecuting:Ref<boolean>;
  previewRepair():Promise<void>;
  executeRepair():Promise<void>;
  repairWritesDisabled:ComputedRef<boolean>;
  dstValidation:ComputedRef<DstValidation|null>;
}{
  const repairPreview=ref<RepairPreview|null>(null);
  const repairContext=ref<RepairContext|null>(null);
  const isRepairPreviewing=ref(false);
  const isRepairExecuting=ref(false);
  let repairGeneration=0;

  const dstValidation=computed(()=>deps.workspace.value?.dst_validation??null);
  const repairWritesDisabled=computed(()=>{
    const status=dstValidation.value?.status;
    // 旧客户端/旧 mock 未提供 dst_validation 时视为 VALID（后端仍会门禁）
    if(!status||status==="VALID")return false;
    return true;
  });

  async function previewRepair(){
    const current=deps.workspace.value;
    if(deps.isWorkspaceLoading.value||!current||isRepairPreviewing.value)return;
    const workspaceId=current.id,baseRevisionId=current.revision_id,loadGeneration=deps.workspaceLoadGeneration.value,generation=++repairGeneration;
    repairPreview.value=null;repairContext.value=null;isRepairPreviewing.value=true;
    try{
      const result:RepairPreview=await request(`/api/workspaces/${workspaceId}/repairs/preview`,{method:"POST",body:JSON.stringify({base_revision_id:baseRevisionId})});
      // 代次/修订保护：旧修复报告不得覆盖新工作区
      if(generation!==repairGeneration||loadGeneration!==deps.workspaceLoadGeneration.value||deps.workspace.value?.id!==workspaceId||deps.workspace.value.revision_id!==baseRevisionId)return;
      repairPreview.value=result;repairContext.value={workspaceId,baseRevisionId,previewDigest:result.preview_digest??undefined,loadGeneration};deps.error.value="";
    }
    catch(e){if(generation===repairGeneration)deps.error.value=String(e)}
    finally{if(generation===repairGeneration)isRepairPreviewing.value=false}
  }
  async function executeRepair(){
    const context=repairContext.value;
    if(!context||isRepairExecuting.value)return;
    const current=deps.workspace.value;
    if(deps.isWorkspaceLoading.value||!current||current.id!==context.workspaceId||current.revision_id!==context.baseRevisionId||context.loadGeneration!==deps.workspaceLoadGeneration.value){repairPreview.value=null;repairContext.value=null;deps.error.value="工作区或基准修订已变化，请重新生成修复预览";return}
    // 发布独立修复修订属不可逆破坏类操作：需要显式勾选后才可确认
    const ok=await deps.confirmAction({title:"确认把内存修复发布为独立修订",message:"原 DST 将永久备份。",confirmText:"确认把内存修复发布",danger:true,requireCheckbox:true,reversibility:"不可逆"});
    if(!ok)return;
    const generation=deps.invalidateJobMonitor(false);
    isRepairExecuting.value=true;
    try{
      const result:Job=await request(`/api/workspaces/${context.workspaceId}/repairs/execute`,{method:"POST",body:JSON.stringify({base_revision_id:context.baseRevisionId,preview_digest:context.previewDigest})});
      if(!deps.isCurrentJobGeneration(generation)||deps.isWorkspaceLoading.value||deps.workspace.value?.id!==context.workspaceId)return;
      deps.setJob(result);
      if(result.status==="SUCCEEDED"){repairPreview.value=null;repairContext.value=null;await deps.refreshWorkspace(context.workspaceId)}
      else if(result.status==="FAILED"){deps.error.value=result.error_code??"修复发布失败"}
    }
    catch(e){if(deps.isCurrentJobGeneration(generation)&&deps.workspace.value?.id===context.workspaceId&&!deps.isWorkspaceLoading.value)deps.error.value=String(e)}
    finally{if(deps.isCurrentJobGeneration(generation))isRepairExecuting.value=false}
  }

  return {repairPreview,repairContext,isRepairPreviewing,isRepairExecuting,previewRepair,executeRepair,repairWritesDisabled,dstValidation};
}
