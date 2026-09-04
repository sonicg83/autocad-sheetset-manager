import {ref,watch} from "vue";
import type {Ref} from "vue";

type Theme="light"|"dark";
const KEY="dst-manager-theme";

function initial():Theme{
  const saved=localStorage.getItem(KEY);
  return saved==="dark"?"dark":"light";
}

export function useTheme():{theme:Ref<Theme>;toggleTheme:()=>void}{
  const theme=ref<Theme>(initial());
  watch(theme,value=>{document.documentElement.dataset.theme=value;localStorage.setItem(KEY,value)},{immediate:true});
  function toggleTheme(){theme.value=theme.value==="light"?"dark":"light"}
  return {theme,toggleTheme};
}
