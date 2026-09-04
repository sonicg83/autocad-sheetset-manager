import {reactive} from "vue";

export type ConfirmOptions={title:string;message:string;impactLines?:string[];confirmText:string;cancelText?:string;danger?:boolean;requireCheckbox?:boolean;reversibility?: "可撤销"|"不可逆"};
type ConfirmModalState=ConfirmOptions&{open:boolean};

export function useConfirm(){
  const state=reactive<ConfirmModalState>({open:false,title:"",message:"",confirmText:"确认"});
  let pending:((value:boolean)=>void)|null=null;
  function confirmAction(options:ConfirmOptions):Promise<boolean>{
    return new Promise(resolve=>{
      // 防御：旧 pending 若尚未 resolve（模态被新的 confirmAction 覆盖，旧 Promise 不可达），以 false 结束，避免悬挂 Promise
      pending?.(false);
      pending=resolve;
      // 每次打开都是干净状态：先复位全部可选键，避免上一次模态的 requireCheckbox/reversibility/impactLines/cancelText/danger 跨次泄漏
      state.impactLines=undefined;
      state.cancelText=undefined;
      state.danger=false;
      state.requireCheckbox=false;
      state.reversibility=undefined;
      Object.assign(state,options,{open:true});
    });
  }
  function resolve(value:boolean){
    state.open=false;pending?.(value);pending=null;
  }
  return {state,confirmAction,resolve};
}
