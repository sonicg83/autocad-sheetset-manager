// 扩展清单与启停状态所有者（PLAN-DM-020 Task 10 / ARCH-DM-006 §7）。
// 从 App.vue 提取：扩展清单是应用级状态（不属于任何工作区），标签栏装配与设置中心
// 扩展分区共用同一份数据源；若两处各自持有列表并各自发 PATCH，必然出现状态漂移。
//
// 失败语义刻意不对称：
// - reload 不抛出：列表加载失败不阻断核心工作区，按无扩展呈现，同时把 failed 置位，
//   让设置分区给出可见降级与重试，而不是静默显示为空列表；
// - setEnabled 抛出：启停失败必须让用户看到。SPEC-DM-011「启停交互改进」修订起设置对话框不再因停用
//   而关闭（闸门已改为原生 <dialog>，会自行叠在设置窗口之上），因此启用与停用
//   失败都在设置分区内就地行内呈现。
import {ref} from "vue";
import type {Ref} from "vue";
import {listExtensions,patchExtensionState} from "../api/extensions";
import type {ExtensionSummary} from "../api/contracts";

// 设置中心扩展分区所需的视图模型：由 App 装配后传入 SettingsDialog，再转交
// ExtensionsSection。toggle 由 App 注入而不是分区自己调用端点——停用需要经过
// 未保存输入三选一闸门与标签/焦点编排，绕过它们会直接丢用户草稿。
export interface ExtensionsPanel {
  list: ExtensionSummary[];
  loading: boolean;
  failed: boolean;
  reload: () => void | Promise<void>;
  toggle: (extensionId: string, enabled: boolean) => Promise<void>;
}

export function useExtensions():{
  extensions:Ref<ExtensionSummary[]>;
  loading:Ref<boolean>;
  failed:Ref<boolean>;
  reload:()=>Promise<void>;
  setEnabled:(extensionId:string,enabled:boolean)=>Promise<void>;
  clear:()=>void;
}{
  const extensions=ref<ExtensionSummary[]>([]);
  const loading=ref(false);
  const failed=ref(false);

  async function reload():Promise<void>{
    loading.value=true;
    failed.value=false;
    try{
      extensions.value=await listExtensions();
    }catch{
      extensions.value=[];
      failed.value=true;
    }finally{
      loading.value=false;
    }
  }

  async function setEnabled(extensionId:string,enabled:boolean):Promise<void>{
    const updated=await patchExtensionState(extensionId,enabled);
    extensions.value=extensions.value.map(ext=>ext.extension_id===extensionId?updated:ext);
  }

  // 关闭工作区：扩展页面标签随工作区消失，列表不跨工作区保留
  // （设置中心打开时会重新拉取，故无工作区状态下依然可达）
  function clear():void{
    extensions.value=[];
    failed.value=false;
  }

  return {extensions,loading,failed,reload,setEnabled,clear};
}
