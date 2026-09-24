// 设置中心 e2e 夹具：与 tests/global-setup.ts 约定同一隔离配置目录（固定路径，
// 因 globalSetup 的 process.env 无法传给测试 worker）。
// 场景写入均为"外部手编 settings.json"真实路径：后端 GET 前按文件指纹刷新（refresh_if_changed），
// 写坏/写新 schema 后重新打开对话框即可触发对应诊断，无需重启后端。
import {mkdirSync, writeFileSync} from "node:fs";
import os from "node:os";
import path from "node:path";
import {expect,type Page} from "@playwright/test";

export const SETTINGS_DIR = path.join(os.tmpdir(), "dst-manager-e2e-settings");
export const SETTINGS_PATH = path.join(SETTINGS_DIR, "settings.json");

export function preferenceSnapshot(theme: "light" | "dark" = "light",cadVersion: "2016" | "2020" = "2020",configRevision=1,locale:"zh-CN"|"en-US"="zh-CN") {
  return {
    schema_version:1,config_revision:configRevision,diagnostics:[],schema_blocked:false,
    items:[
      {key:"ui_locale",control:"enum",value:locale,default:"system",source:"file",has_file_override:true,label_key:"settings.items.uiLocale",category_key:"settings.categories.interface",options:[{value:"system",text_key:"settings.locale.system"},{value:"zh-CN",text_key:"settings.locale.zhCN"},{value:"en-US",text_key:"settings.locale.enUS"}]},
      {key:"ui_theme",control:"enum",value:theme,default:"light",source:"file",has_file_override:true,label_key:"settings.items.uiTheme",category_key:"settings.categories.interface",options:[{value:"light",text_key:"settings.enum.themeLight"},{value:"dark",text_key:"settings.enum.themeDark"}]},
      {key:"cad_version",control:"enum",value:cadVersion,default:"2020",source:"file",has_file_override:true,label_key:"settings.items.cadVersion",category_key:"settings.categories.execution",options:[{value:"2016",text_key:"settings.enum.autocad2016"},{value:"2020",text_key:"settings.enum.autocad2020"}]},
      {key:"cad_timeout_seconds",control:"int",value:600,default:600,source:"default",has_file_override:false,label_key:"settings.items.cadTimeout",category_key:"settings.categories.execution",min:30,max:3600},
    ],
  };
}

export async function installPreferenceSnapshot(page:Page,theme:"light"|"dark"="light",cadVersion:"2016"|"2020"="2020",locale:"zh-CN"|"en-US"="zh-CN"):Promise<void>{
  let currentTheme=theme;
  let currentCadVersion=cadVersion;
  let currentLocale=locale;
  let revision=1;
  await page.route("**/api/settings",async route=>{
    if(route.request().method()==="PUT"){
      const body=await route.request().postDataJSON() as {set?:Record<string,unknown>};
      if(body.set?.ui_theme==="light"||body.set?.ui_theme==="dark")currentTheme=body.set.ui_theme;
      if(body.set?.cad_version==="2016"||body.set?.cad_version==="2020")currentCadVersion=body.set.cad_version;
      if(body.set?.ui_locale==="zh-CN"||body.set?.ui_locale==="en-US")currentLocale=body.set.ui_locale;
      revision+=1;
    }
    await route.fulfill({json:preferenceSnapshot(currentTheme,currentCadVersion,revision,currentLocale)});
  });
}

/** 生效编号设置（创建向导的编号设置失效接线用例观察对象）。 */
export interface NumberingSettings{
  suffixEnabled:boolean;
  suffixType:number;
  keywords:string;
}

/**
 * 含生效编号设置的快照：`enable_add_number_suffix`、`number_suffix_type`、
 * `unnumbered_subset_keywords` 三个编号键，加最小界面偏好使启动引导照常解析。
 */
export function numberingSettingsSnapshot(values:NumberingSettings,configRevision=1){
  return {
    schema_version:1,config_revision:configRevision,diagnostics:[],schema_blocked:false,
    items:[
      {key:"ui_locale",control:"enum",value:"zh-CN",default:"system",source:"file",has_file_override:true,label_key:"settings.items.uiLocale",category_key:"settings.categories.interface",options:[{value:"system",text_key:"settings.locale.system"},{value:"zh-CN",text_key:"settings.locale.zhCN"},{value:"en-US",text_key:"settings.locale.enUS"}]},
      {key:"ui_theme",control:"enum",value:"light",default:"light",source:"default",has_file_override:false,label_key:"settings.items.uiTheme",category_key:"settings.categories.interface",options:[{value:"light",text_key:"settings.enumOptions.themeLight"},{value:"dark",text_key:"settings.enumOptions.themeDark"}]},
      {key:"enable_add_number_suffix",control:"bool",value:values.suffixEnabled,default:true,source:"file",has_file_override:true,label_key:"settings.items.addNumberSuffix",category_key:"settings.categories.numbering"},
      {key:"number_suffix_type",control:"enum",value:values.suffixType,default:1,source:"file",has_file_override:true,label_key:"settings.items.numberSuffixType",category_key:"settings.categories.numbering",options:[{value:1,text_key:"settings.enumOptions.suffixChinese"},{value:2,text_key:"settings.enumOptions.suffixArabic"}]},
      {key:"unnumbered_subset_keywords",control:"text",value:values.keywords,default:"",source:"default",has_file_override:false,label_key:"settings.items.unnumberedSubsetKeywords",category_key:"settings.categories.numbering"},
    ],
  };
}

/**
 * 安装编号设置端点 mock：PUT 把提交的编号键写回后返回新快照（与真实后端同形：保存后的
 * 快照就是新的生效值）。创建向导的失效接线用例据此观察“生效编号设置变化”。
 */
export async function installNumberingSettings(page:Page,initial:Partial<NumberingSettings>={}):Promise<void>{
  let values:NumberingSettings={suffixEnabled:initial.suffixEnabled??true,suffixType:initial.suffixType??1,keywords:initial.keywords??""};
  let revision=1;
  await page.route("**/api/settings",async route=>{
    if(route.request().method()==="PUT"){
      const body=await route.request().postDataJSON() as {set?:Record<string,unknown>};
      const set=body.set??{};
      values={
        suffixEnabled:typeof set.enable_add_number_suffix==="boolean"?set.enable_add_number_suffix:values.suffixEnabled,
        suffixType:typeof set.number_suffix_type==="number"?set.number_suffix_type:values.suffixType,
        keywords:typeof set.unnumbered_subset_keywords==="string"?set.unnumbered_subset_keywords:values.keywords,
      };
      revision+=1;
    }
    await route.fulfill({json:numberingSettingsSnapshot(values,revision)});
  });
}

export function writeSettingsFile(
  values: Record<string, unknown>,
  configRevision = 0,
  schemaVersion: number | string = 1,
): void {
  mkdirSync(SETTINGS_DIR, {recursive: true});
  const payload = typeof schemaVersion === "number"
    ? JSON.stringify({schema_version: schemaVersion, config_revision: configRevision, values})
    : schemaVersion; // 传入非数字时按原始文本写入（损坏场景）
  writeFileSync(SETTINGS_PATH, payload, "utf-8");
}

export async function openSettingsDialog(page: Page): Promise<void> {
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
}

export async function expectDialog(page: Page): Promise<void> {
  await expect(page.getByRole("dialog", {name: "设置"})).toBeVisible();
  // 快照加载完成的标志：首字段已渲染（load() 为异步，对话框先于数据显示）
  await page.locator('input[data-key="cad_timeout_seconds"]').waitFor();
}
