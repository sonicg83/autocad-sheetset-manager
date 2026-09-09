// 设置中心组合式函数（PLAN-DM-019 任务 9；PLAN-DM-021 Task 3 语言切换事务）。
// 模块级单例状态（模式同 useTheme.ts）。设置对话框为单实例，无需并发保护。
// 语言事务（I18N-05/06）：只有 PUT 成功才允许切换语言，且以响应快照的 ui_locale
// 为准恰好切换一次（applyLocale 唯一入口）；load、选择未保存、取消、422/409/5xx
// 均不切换，快照与本地编辑保持不变。
import {ref} from "vue";
import type {Ref} from "vue";
import {applyLocale} from "../i18n";
import {resolveLocale, type UiLocaleSetting} from "../i18n/locale";
import {fetchSettings,putSettings} from "../api/settings";
import type {SettingsSnapshot} from "../api/settings";

const snapshot=ref<SettingsSnapshot|null>(null);
const loading=ref(false);

// 快照中的 ui_locale 值白名单（与后端 I18N-02 一致）；缺失或非法值视为 system。
// 与 i18n/index.ts 的启动读取各自独立：启动解析走 bootstrap，保存事务走本层。
function readUiLocale(snap:SettingsSnapshot):UiLocaleSetting{
  const value=snap.items.find(item=>item.key==="ui_locale")?.value;
  return value==="zh-CN"||value==="en-US"||value==="system"?value:"system";
}

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
    if(current===null)throw new Error("Settings snapshot not loaded; cannot save"); // 开发态诊断，非界面文案
    // 乐观并发：以打开对话框时的 config_revision 为期望修订号。
    // 失败（422/409/网络/5xx）原样上抛：快照不替换、语言不切换。
    const next=await putSettings(current.configRevision,set,unset);
    snapshot.value=next;
    // 语言切换事务：成功后以响应快照 ui_locale 解析生效语言，变化时切换一次
    const before=resolveLocale(readUiLocale(current));
    const after=resolveLocale(readUiLocale(next));
    if(after!==before)await applyLocale(after);
  }

  return {snapshot,loading,load,save};
}
