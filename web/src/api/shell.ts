import {ref} from "vue";
import type {ColumnPreferences} from "../features/sheets/types";

type ShellBridge={select_file(fileTypes:string[]):Promise<string|null>;select_folder():Promise<string|null>;on_files_dropped(callbackId:string):Promise<void>} & Partial<SheetShellBridge>;

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
// 设置中心"浏览"按钮过滤器（PLAN-DM-019 任务 8）。描述部分必须通过 pywebview parse_file_type
// 的 [\w ]+ 校验：".NET" 的前导点不合法，会在对话框弹出前抛 ValueError，故写作 "NET 程序集"。
export const EXE_FILE_FILTERS=["可执行程序 (*.exe)"];
export const DLL_FILE_FILTERS=["NET 程序集 (*.dll)"];

// ---- PLAN-DM-015 任务 2：可信上下文与列偏好桥（PLAN-DM-015 接口，不进业务 OpenAPI） ----
// workspace_id 只用于服务端匹配，路径一律由服务端可信上下文提供，前端不传任何路径/命令。
export type ShellResult<T>={ok:true;value:T}|{ok:false;code:string;message:string};
export interface SheetShellBridge {
  open_workspace_folder(workspace_id:string):Promise<ShellResult<null>>;
  load_sheet_columns(workspace_id:string):Promise<ShellResult<ColumnPreferences|null>>;
  save_sheet_columns(workspace_id:string,preferences:ColumnPreferences):Promise<ShellResult<null>>;
  clear_workspace_context(workspace_id:string):Promise<ShellResult<null>>;
}

// 旧/部分桥可能只暴露 select_file/on_files_dropped：新方法缺失时返回 null，
// 调用方按“不可用/降级”处理（按钮禁用或静默跳过），不抛错。
export async function openWorkspaceFolder(workspaceId:string):Promise<ShellResult<null>|null>{
  const bridge=getShellBridge();
  if(!bridge||typeof bridge.open_workspace_folder!=="function")return null;
  return bridge.open_workspace_folder(workspaceId);
}
export async function loadSheetColumns(workspaceId:string):Promise<ShellResult<ColumnPreferences|null>|null>{
  const bridge=getShellBridge();
  if(!bridge||typeof bridge.load_sheet_columns!=="function")return null;
  return bridge.load_sheet_columns(workspaceId);
}
export async function saveSheetColumns(workspaceId:string,preferences:ColumnPreferences):Promise<ShellResult<null>|null>{
  const bridge=getShellBridge();
  if(!bridge||typeof bridge.save_sheet_columns!=="function")return null;
  return bridge.save_sheet_columns(workspaceId,preferences);
}
export async function clearWorkspaceContext(workspaceId:string):Promise<ShellResult<null>|null>{
  const bridge=getShellBridge();
  if(!bridge||typeof bridge.clear_workspace_context!=="function")return null;
  return bridge.clear_workspace_context(workspaceId);
}

// ---- PLAN-DM-019 任务 8：设置中心"浏览"按钮统一封装 ----
// 三态语义（Task 10 消费方依赖，不得走样）：
// - undefined = 桥不可用或 select_file/select_folder 方法缺失（浏览器开发态/旧壳）→ 调用方禁用"浏览"按钮；
// - null      = 用户取消对话框；
// - string    = 用户选中的路径。
export async function selectSettingsPath(filter:"exe"|"dll"|"folder"):Promise<string|null|undefined>{
  const bridge=getShellBridge();
  if(!bridge)return undefined;
  if(filter==="folder"){
    if(typeof bridge.select_folder!=="function")return undefined;
    return bridge.select_folder();
  }
  if(typeof bridge.select_file!=="function")return undefined;
  return bridge.select_file(filter==="exe"?EXE_FILE_FILTERS:DLL_FILE_FILTERS);
}
