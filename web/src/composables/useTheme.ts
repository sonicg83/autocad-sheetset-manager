// 主题组合式函数：模块级单例状态（Task 4 修正——App.vue 与 TopBar 各自调用 useTheme 时共享同一实例，避免主题按钮产生第二份状态）
import {ref,watch} from "vue";
import type {Ref} from "vue";

type Theme="light"|"dark";
const KEY="dst-manager-theme";

function initial():Theme{
  const saved=localStorage.getItem(KEY);
  return saved==="dark"?"dark":"light";
}

const theme=ref<Theme>(initial());
watch(theme,value=>{document.documentElement.dataset.theme=value;localStorage.setItem(KEY,value)},{immediate:true});
function toggleTheme(){theme.value=theme.value==="light"?"dark":"light"}

export function useTheme():{theme:Ref<Theme>;toggleTheme:()=>void}{
  return {theme,toggleTheme};
}
