import {reactive} from "vue";

export type ConfirmOptions={title:string;message:string;impactLines?:string[];confirmText:string;cancelText?:string;danger?:boolean;requireCheckbox?:boolean;reversibility?:string};
type ConfirmModalState=ConfirmOptions&{open:boolean};

export function useConfirm(){
  const state=reactive<ConfirmModalState>({open:false,title:"",message:"",confirmText:"确认"});
  let pending:((value:boolean)=>void)|null=null;
  function confirmAction(options:ConfirmOptions):Promise<boolean>{
    return new Promise(resolve=>{
      pending=resolve;
      Object.assign(state,options,{open:true});
    });
  }
  function resolve(value:boolean){
    state.open=false;pending?.(value);pending=null;
  }
  return {state,confirmAction,resolve};
}
