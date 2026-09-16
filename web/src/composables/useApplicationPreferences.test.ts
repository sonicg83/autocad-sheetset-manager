import {beforeEach,describe,expect,it,vi} from "vitest";
import "vue"; // 先在无 DOM 的 Node 环境加载 runtime-dom，再安装本测试所需的最小 document 桩
import type {SettingsItem,SettingsSnapshot,SettingsValue} from "../api/settings";

function item(key:string,value:SettingsValue):SettingsItem{
  return {key,labelKey:`settings.items.${key}`,categoryKey:"settings.categories.interface",control:"enum",value,default:value,source:"file",hasFileOverride:true};
}

function snapshot(cadVersion:SettingsValue,uiTheme:SettingsValue):SettingsSnapshot{
  return {schemaVersion:1,configRevision:1,items:[item("cad_version",cadVersion),item("ui_theme",uiTheme)],diagnostics:[],schemaBlocked:false};
}

async function freshPreferences(){
  vi.resetModules();
  return import("./useApplicationPreferences");
}

beforeEach(()=>{
  vi.unstubAllGlobals();
  vi.stubGlobal("document",{documentElement:{dataset:{}}});
  vi.stubGlobal("localStorage",{getItem:vi.fn(()=>"dark"),setItem:vi.fn()});
});

describe("应用偏好",()=>{
  it("启动快照决定 AutoCAD 版本和初始主题，不读取或写入 localStorage",async()=>{
    const {initializeApplicationPreferences,useApplicationPreferences}=await freshPreferences();
    initializeApplicationPreferences(snapshot("2016","dark"));
    const {cadVersion,theme}=useApplicationPreferences();
    expect(cadVersion.value).toBe("2016");
    expect(theme.value).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem).not.toHaveBeenCalled();
    expect(localStorage.setItem).not.toHaveBeenCalled();
  });

  it("Topbar 主题切换只改本次会话，保存无关配置不会覆盖临时主题",async()=>{
    const {initializeApplicationPreferences,applySavedApplicationPreferences,useApplicationPreferences}=await freshPreferences();
    initializeApplicationPreferences(snapshot("2020","light"));
    const {theme,toggleTheme}=useApplicationPreferences();
    toggleTheme();
    expect(theme.value).toBe("dark");
    applySavedApplicationPreferences(snapshot("2020","light"),new Set(["cad_timeout_seconds"]));
    expect(theme.value).toBe("dark");
    expect(localStorage.setItem).not.toHaveBeenCalled();
  });

  it("配置中心明确保存或恢复主题时覆盖临时主题，并同步 AutoCAD 版本",async()=>{
    const {initializeApplicationPreferences,applySavedApplicationPreferences,useApplicationPreferences}=await freshPreferences();
    initializeApplicationPreferences(snapshot("2020","light"));
    const preferences=useApplicationPreferences();
    preferences.toggleTheme();
    applySavedApplicationPreferences(snapshot("2016","light"),new Set(["cad_version","ui_theme"]));
    expect(preferences.cadVersion.value).toBe("2016");
    expect(preferences.theme.value).toBe("light");
  });

  it("启动读取失败后首次成功加载补初始化，后续打开设置不覆盖临时主题",async()=>{
    const {initializeApplicationPreferencesIfNeeded,useApplicationPreferences}=await freshPreferences();
    const preferences=useApplicationPreferences();
    expect(initializeApplicationPreferencesIfNeeded(snapshot("2016","dark"))).toBe(true);
    expect(preferences.cadVersion.value).toBe("2016");
    expect(preferences.theme.value).toBe("dark");
    preferences.toggleTheme();
    expect(initializeApplicationPreferencesIfNeeded(snapshot("2020","dark"))).toBe(false);
    expect(preferences.cadVersion.value).toBe("2016");
    expect(preferences.theme.value).toBe("light");
  });
});
