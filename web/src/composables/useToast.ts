// 任务终态非模态通知组合式函数（SPEC-DM-006 §6.6）：
// ok 5 秒自动消失（role="status"）、fail 常驻不自动消失（role="alert"）；通常保留 4 条，失败超量由宿主滚动呈现
import {ref} from "vue";
import type {Ref} from "vue";

export type ToastTab="prog"|"prev"|"diag";
export type Toast={id:number;type:"ok"|"fail";title:string;body:string;jumpTab?:ToastTab};
let nextId=1;

export function useToast(){
  const toasts=ref<Toast[]>([]);
  function dismiss(id:number){toasts.value=toasts.value.filter(item=>item.id!==id)}
  function pushToast(t:Omit<Toast,"id">){
    const toast:Toast={id:nextId++,...t};
    const next=[...toasts.value,toast];
    if(next.length>4){
      // 只清理旧成功通知；失败承载恢复信息，新通知必须先得到完整展示机会。
      const oldestSuccess=next.findIndex(item=>item.type==="ok"&&item.id!==toast.id);
      if(oldestSuccess>=0)next.splice(oldestSuccess,1);
    }
    toasts.value=next;
    if(toast.type==="ok")setTimeout(()=>dismiss(toast.id),5000); // ok 5 秒自动消失
  }
  return {toasts,pushToast,dismiss};
}
