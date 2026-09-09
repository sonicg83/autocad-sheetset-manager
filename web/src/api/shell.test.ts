// ShellBridge 前端封装单测（PLAN-DM-021 Task 4）：selectSettingsPath 按 file_kind
// 传固定种类、描述参数化；folder 走独立 select_folder 桥方法；三态语义
//（undefined=桥/方法缺失、null=用户取消、string=选中路径）不得走样。
// 安全红线：前端不再定义/传递任意 file_types 过滤器字符串，白名单由壳侧按 kind 拼接。
import {beforeAll,describe,expect,it,vi} from "vitest";

type ShellModule=typeof import("./shell");

function installWindow(bridge:Record<string,unknown>|null):void{
  // shell.ts 模块顶层与 getShellBridge 均读 window：node 环境下显式注入
  vi.stubGlobal("window",{addEventListener:()=>{},pywebview:bridge===null?undefined:{api:bridge}});
}

function fakeBridge(overrides:Record<string,unknown>={}):Record<string,unknown>{
  return {
    select_file:vi.fn(async()=>null),
    select_folder:vi.fn(async()=>null),
    on_files_dropped:vi.fn(async()=>{}),
    ...overrides,
  };
}

describe("selectSettingsPath（file_kind + 本地化描述）",()=>{
  let shell:ShellModule;
  beforeAll(async()=>{
    installWindow(null); // 模块顶层 shellReady 求值需要 window 存在
    shell=await import("./shell");
  });

  it("无桥返回 undefined（浏览器开发态降级，调用方禁用浏览按钮）",async()=>{
    installWindow(null);
    await expect(shell.selectSettingsPath("exe","Executable program")).resolves.toBeUndefined();
    await expect(shell.selectSettingsPath("folder","")).resolves.toBeUndefined();
  });

  it("exe/dll 按 file_kind 调 select_file 且描述参数化透传",async()=>{
    for(const kind of ["exe","dll"] as const){
      const bridge=fakeBridge();
      installWindow(bridge);
      await expect(shell.selectSettingsPath(kind,`描述-${kind}`)).resolves.toBeNull();
      expect(bridge.select_file).toHaveBeenCalledExactlyOnceWith(kind,`描述-${kind}`);
      expect(bridge.select_folder).not.toHaveBeenCalled();
    }
  });

  it("folder 不进 select_file：走独立 select_folder 桥方法且不传描述",async()=>{
    const bridge=fakeBridge();
    installWindow(bridge);
    await expect(shell.selectSettingsPath("folder","")).resolves.toBeNull();
    expect(bridge.select_folder).toHaveBeenCalledExactlyOnceWith();
    expect(bridge.select_file).not.toHaveBeenCalled();
  });

  it("选中路径原样返回（string 三态）；桥内取消（null）原样透传",async()=>{
    const bridge=fakeBridge({select_file:vi.fn(async()=>"C:\\Tools\\accoreconsole.exe")});
    installWindow(bridge);
    await expect(shell.selectSettingsPath("exe","可执行程序")).resolves.toBe("C:\\Tools\\accoreconsole.exe");
    const cancelling=fakeBridge();
    installWindow(cancelling);
    await expect(shell.selectSettingsPath("exe","可执行程序")).resolves.toBeNull();
  });

  it("旧壳缺 select_file/select_folder 方法返回 undefined（不抛错）",async()=>{
    installWindow({on_files_dropped:vi.fn(async()=>{})});
    await expect(shell.selectSettingsPath("exe","描述")).resolves.toBeUndefined();
    await expect(shell.selectSettingsPath("folder","")).resolves.toBeUndefined();
  });
});
