import {ref} from "vue";
import type {ColumnPreferences} from "../features/sheets/types";

// PLAN-DM-021 Task 4：原生文件对话框种类（白名单由壳侧按 kind 固定拼接）。
// 前端只传种类与本地化描述，不再定义/传递任意 file_types 过滤器字符串；
// 描述仅作对话框显示，含伪造模式也不能扩大白名单（壳侧净化 + 固定拼接）。
export type ShellFileKind="dst"|"template"|"exe"|"dll";
type ShellBridge={select_file(fileKind:ShellFileKind,localizedDescription:string):Promise<string|null>;select_folder():Promise<string|null>;on_files_dropped(callbackId:string):Promise<void>} & Partial<SheetShellBridge>;

export function getShellBridge():ShellBridge|null{
  const api=(window as unknown as {pywebview?:{api?:ShellBridge}}).pywebview?.api;
  return api??null;
}

// pywebview 在页面加载后才异步注入 window.pywebview 并派发 pywebviewready 事件；
// 桥就绪状态必须响应式，否则首帧判空后将永远停留在无壳降级界面（Vue 对 window 属性无依赖追踪）
export const shellReady=ref(getShellBridge()!==null);
window.addEventListener("pywebviewready",()=>{shellReady.value=true},{once:true});

// pywebview 的 file_types 使用 "描述 (*.ext)" 括号格式，描述部分须匹配 parse_file_type
// 的 [\w ]+；该格式约束自 Task 4 起完全由壳侧保证（见 tests/unit/test_shell.py 契约测试），
// 前端不再持有过滤器字符串常量。

// ---- PLAN-DM-015 任务 2：可信上下文与列偏好桥（PLAN-DM-015 接口，不进业务 OpenAPI） ----
// workspace_id 只用于服务端匹配，路径一律由服务端可信上下文提供，前端不传任何路径/命令。
// PLAN-DM-021 Task 9（I18N-11）：桥错误补 message_key/params（与后端统一错误目录同构），
// message 保留为兼容原始文本，仅在未知 code 时作为回退。
export type ShellResult<T>={ok:true;value:T}|{ok:false;code:string;message:string;message_key?:string;params?:Record<string,string|number|boolean|string[]>};
export interface SheetShellBridge {
  open_workspace_folder(workspace_id:string):Promise<ShellResult<null>>;
  load_sheet_columns(workspace_id:string):Promise<ShellResult<ColumnPreferences|null>>;
  save_sheet_columns(workspace_id:string,preferences:ColumnPreferences):Promise<ShellResult<null>>;
  clear_workspace_context(workspace_id:string):Promise<ShellResult<null>>;
  // SC-11（SPEC-DM-011 §4 / ARCH-DM-004 §4.2）：外链经系统浏览器打开；
  // url 只能是 GET /api/about 返回的后端登记值，桥侧再按代码内白名单二次校验
  open_external(url:string):Promise<ShellResult<null>>;
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

// ---- PLAN-DM-019 任务 8：设置中心"浏览"按钮统一封装（PLAN-DM-021 Task 4 file_kind 化） ----
// 三态语义（Task 10 消费方依赖，不得走样）：
// - undefined = 桥不可用或 select_file/select_folder 方法缺失（浏览器开发态/旧壳）→ 调用方禁用"浏览"按钮；
// - null      = 用户取消对话框；
// - string    = 用户选中的路径。
// kind "folder" 走独立 select_folder 桥方法（FOLDER_DIALOG 无过滤器概念，不传描述）；
// exe/dll 经 select_file(fileKind, localizedDescription)，扩展名白名单由壳侧固定拼接。
export async function selectSettingsPath(kind:"exe"|"dll"|"folder",localizedDescription:string):Promise<string|null|undefined>{
  const bridge=getShellBridge();
  if(!bridge)return undefined;
  if(kind==="folder"){
    if(typeof bridge.select_folder!=="function")return undefined;
    return bridge.select_folder();
  }
  if(typeof bridge.select_file!=="function")return undefined;
  return bridge.select_file(kind,localizedDescription);
}

// ---- PLAN-DM-019 修复波：SC-11 外链经系统默认浏览器打开 ----
// 三态语义：undefined = 桥或 open_external 方法缺失（浏览器开发态/旧壳，调用方走 window.open 回退）；
// true = 壳已交给系统默认浏览器；false = 桥侧白名单校验拒绝（SHELL_EXTERNAL_URL_REJECTED）。
// url 必须来自 GET /api/about 的后端登记值，前端不得传任意字符串。
export async function openExternalLink(url:string):Promise<boolean|undefined>{
  const bridge=getShellBridge();
  if(!bridge||typeof bridge.open_external!=="function")return undefined;
  const result=await bridge.open_external(url);
  return result.ok===true?true:false;
}
