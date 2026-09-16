// 主题组合式函数：模块级单例状态。持久主题由设置快照初始化；顶栏按钮只改
// 本次运行的内存状态，不使用 localStorage，刷新/重启后重新以配置中心为准。
import {ref,watch} from "vue";
import type {Ref} from "vue";

export type Theme="light"|"dark";
const theme=ref<Theme>("light");
watch(theme,value=>{
  if(typeof document==="undefined")return;
  const dataset=(document.documentElement as HTMLElement & {dataset?:DOMStringMap}).dataset;
  if(dataset)dataset.theme=value;
},{immediate:true,flush:"sync"});
function toggleTheme(){theme.value=theme.value==="light"?"dark":"light"}
export function applyTheme(value:Theme){theme.value=value}

export function useTheme():{theme:Ref<Theme>;toggleTheme:()=>void}{
  return {theme,toggleTheme};
}
