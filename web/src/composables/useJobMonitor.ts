// 任务监控域组合式函数：Job 的 SSE/轮询订阅、代次失效与失败重试（Task 3 拆分，行为零变化）
// Task 7：终态分支发非模态 toast 通知（SPEC-DM-006 §6.6），经 deps 注入 pushToast 与 shouldSuppress
import {ref} from "vue";
import type {Ref} from "vue";
import {request} from "../api/client";
import type {Job,Workspace} from "../api/contracts";
import type {Toast} from "./useToast";

export function useJobMonitor(deps:{
  isWorkspaceLoading:Ref<boolean>;
  workspace:Ref<Workspace|null>;
  onJobSucceeded(workspaceId:string):Promise<void>;
  error:Ref<string>;
  pushToast?:(t:Omit<Toast,"id">)=>void;
  shouldSuppress?:()=>boolean;
}){
  const job=ref<Job|null>(null);
  const connectionMode=ref("SSE");
  let jobMonitorGeneration=0;
  let activeJobEvents:EventSource|null=null;
  let pollTimer:number|null=null;

  function invalidateJobMonitor(clearJob=false){jobMonitorGeneration+=1;activeJobEvents?.close();activeJobEvents=null;if(pollTimer!==null){clearTimeout(pollTimer);pollTimer=null}if(clearJob)job.value=null;return jobMonitorGeneration}
  function terminal(status:string){return ["SUCCEEDED","FAILED","ROLLED_BACK","BLOCKED_FILE_LOCK","NEEDS_REVIEW"].includes(status)}
  function monitorMatches(generation:number,workspaceId:string){return generation===jobMonitorGeneration&&!deps.isWorkspaceLoading.value&&deps.workspace.value?.id===workspaceId}
  // Task 7 终态通知（SPEC-DM-006 §6.6）：SUCCEEDED→ok、FAILED/ROLLED_BACK/BLOCKED_FILE_LOCK→fail（含 error_code 与"整批未发布"语义）、NEEDS_REVIEW→fail（沿用既有禁止直接重试文案）；用户正停留在浮层实施进度页签（shouldSuppress）时不弹
  function notifyTerminal(job:Job){
    if(deps.shouldSuppress?.())return;
    if(job.status==="SUCCEEDED"){deps.pushToast?.({type:"ok",title:"任务成功",body:"任务已完成发布",jumpTab:"prog"});return}
    if(job.status==="NEEDS_REVIEW"){deps.pushToast?.({type:"fail",title:"需人工检查",body:"发布状态需要人工检查，禁止直接重试",jumpTab:"prog"});return}
    const code=job.error_code??"";
    deps.pushToast?.({type:"fail",title:"任务失败",body:code?`${code}，整批未发布`:"整批未发布",jumpTab:"prog"});
  }
  function watchJob(id:string,workspaceId:string){
    const generation=invalidateJobMonitor(false);
    const events=new EventSource(`/api/jobs/${id}/events`);
    activeJobEvents=events;
    events.onmessage=async event=>{if(!monitorMatches(generation,workspaceId))return;const result:Job=JSON.parse(event.data);if(!monitorMatches(generation,workspaceId))return;job.value=result;if(terminal(result.status)){notifyTerminal(result);events.close();if(activeJobEvents===events)activeJobEvents=null;if(result.status==="SUCCEEDED"){await deps.onJobSucceeded(workspaceId)}}};
    events.onerror=()=>{if(!monitorMatches(generation,workspaceId))return;events.close();if(activeJobEvents===events)activeJobEvents=null;connectionMode.value="轮询";schedulePoll(id,workspaceId,generation)};
  }
  function schedulePoll(id:string,workspaceId:string,generation:number){if(!monitorMatches(generation,workspaceId))return;if(pollTimer!==null)clearTimeout(pollTimer);pollTimer=window.setTimeout(()=>{pollTimer=null;void pollJob(id,workspaceId,generation)},1000)}
  async function pollJob(id:string,workspaceId:string,generation:number){if(!monitorMatches(generation,workspaceId)||job.value&&terminal(job.value.status))return;try{const result:Job=await request(`/api/jobs/${id}`);if(!monitorMatches(generation,workspaceId))return;job.value=result;if(!terminal(result.status))schedulePoll(id,workspaceId,generation);else{notifyTerminal(result);if(result.status==="SUCCEEDED"){await deps.onJobSucceeded(workspaceId)}}}catch(e){if(monitorMatches(generation,workspaceId))deps.error.value=String(e)}}
  async function retryJob(){const current=deps.workspace.value;if(!current||!job.value||!job.value.id||deps.isWorkspaceLoading.value)return;if(job.value.status==="NEEDS_REVIEW"){deps.error.value="发布状态需要人工检查，禁止直接重试";return}const workspaceId=current.id,id=job.value.id,generation=invalidateJobMonitor(false);try{const result:Job=await request(`/api/jobs/${id}/retry`,{method:"POST"});if(!monitorMatches(generation,workspaceId))return;job.value=result;if(result.status==="QUEUED")watchJob(id,workspaceId)}catch(e){if(monitorMatches(generation,workspaceId))deps.error.value=String(e)}}
  // 供 App.vue 及相邻域组合式函数做 jobMonitorGeneration 的纯代次校验（行为与直接比较 jobMonitorGeneration 等价）
  function isCurrentJobGeneration(generation:number){return generation===jobMonitorGeneration}

  return {job,connectionMode,watchJob,retryJob,invalidateJobMonitor,terminal,monitorMatches,isCurrentJobGeneration};
}
