// 全局快捷键（SPEC-DM-006 §7.1）：Ctrl/Cmd+O 打开、Ctrl/Cmd+Enter 预览、Ctrl/Cmd+S 写入、Ctrl/Cmd+Z 撤销、Ctrl/Cmd+Shift+Z 重做
import {onMounted,onUnmounted} from "vue";

type HotkeyHandlers={open:()=>void;preview:()=>void;write:()=>void;undo:()=>void;redo:()=>void};

export function useHotkeys(handlers:HotkeyHandlers):void{
  function onKeydown(e:KeyboardEvent){
    const mod=e.ctrlKey||e.metaKey;if(!mod)return;
    const key=e.key.toLowerCase();
    if(key==="o"){e.preventDefault();handlers.open()}
    else if(key==="enter"){e.preventDefault();handlers.preview()}
    else if(key==="s"){e.preventDefault();handlers.write()}
    else if(key==="z"){e.preventDefault();e.shiftKey?handlers.redo():handlers.undo()}
  }
  onMounted(()=>window.addEventListener("keydown",onKeydown));
  onUnmounted(()=>window.removeEventListener("keydown",onKeydown));
}
