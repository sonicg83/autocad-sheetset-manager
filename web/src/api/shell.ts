import {ref} from "vue";

type ShellBridge={select_file(fileTypes:string[]):Promise<string|null>;on_files_dropped(callbackId:string):Promise<void>};

export function getShellBridge():ShellBridge|null{
  const api=(window as unknown as {pywebview?:{api?:ShellBridge}}).pywebview?.api;
  return api??null;
}

// pywebview 在页面加载后才异步注入 window.pywebview 并派发 pywebviewready 事件；
// 桥就绪状态必须响应式，否则首帧判空后将永远停留在无壳降级界面（Vue 对 window 属性无依赖追踪）
export const shellReady=ref(getShellBridge()!==null);
window.addEventListener("pywebviewready",()=>{shellReady.value=true},{once:true});

// pywebview 的 file_types 使用 "描述 (*.ext)" 括号格式；"描述|*.ext" 竖线格式会在对话框弹出前抛
// ValueError。描述部分还须匹配 pywebview parse_file_type 的 [\w ]+（字母/数字/下标/空格）——
// "DWG/DWT" 这类含斜杠的描述同样会在对话框弹出前抛 ValueError（守卫见 tests/unit/test_shell.py）
export const DST_FILE_FILTERS=["DST 文件 (*.dst)"];
export const TEMPLATE_FILE_FILTERS=["DWG DWT 文件 (*.dwg;*.dwt)"];
