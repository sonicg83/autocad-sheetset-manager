type ShellBridge={select_file(fileTypes:string[]):Promise<string|null>;on_files_dropped(callbackId:string):Promise<void>};

export function getShellBridge():ShellBridge|null{
  const api=(window as unknown as {pywebview?:{api?:ShellBridge}}).pywebview?.api;
  return api??null;
}

// pywebview 的 file_types 使用 "描述 (*.ext)" 括号格式；"描述|*.ext" 竖线格式会在对话框弹出前抛 ValueError
export const DST_FILE_FILTERS=["DST 文件 (*.dst)"];
export const TEMPLATE_FILE_FILTERS=["DWG/DWT 文件 (*.dwg;*.dwt)"];
