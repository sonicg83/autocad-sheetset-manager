// 设置中心组合式函数（PLAN-DM-019 任务 9）：模块级单例状态（模式同 useTheme.ts）。
// 设置对话框为单实例，无需并发保护；409/422 的 ApiError 由 save 原样上抛，
// 交由组件层处理行内错误与冲突提示，本层不吞错。
import {ref} from "vue";
import type {Ref} from "vue";
import {fetchSettings,putSettings} from "../api/settings";
import type {SettingsSnapshot} from "../api/settings";

const snapshot=ref<SettingsSnapshot|null>(null);
const loading=ref(false);

export function useSettings():{
  snapshot:Ref<SettingsSnapshot|null>;
  loading:Ref<boolean>;
  load:()=>Promise<void>;
  save:(set:Record<string,unknown>,unset:string[])=>Promise<void>;
}{
  async function load():Promise<void>{
    loading.value=true;
    try{
      snapshot.value=await fetchSettings();
    }finally{
      loading.value=false;
    }
  }

  async function save(set:Record<string,unknown>,unset:string[]):Promise<void>{
    const current=snapshot.value;
    if(current===null)throw new Error("设置快照未加载，无法保存");
    // 乐观并发：以打开对话框时的 config_revision 为期望修订号；
    // 成功后用响应快照整体替换（含最新 config_revision），失败则快照保持不变。
    snapshot.value=await putSettings(current.configRevision,set,unset);
  }

  return {snapshot,loading,load,save};
}
