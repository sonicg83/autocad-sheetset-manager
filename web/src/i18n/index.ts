// i18n 唯一入口（ARCH-DM-005 §5.1 / I18N-01）：创建并导出唯一 vue-i18n 实例，
// 提供语言应用（applyLocale）与挂载前启动流程（bootstrap）。
// main.ts 只调用 bootstrap()：先确定语言再挂载 Vue，避免首屏语言闪烁（I18N-04）。
import {createApp} from "vue";
import {createI18n} from "vue-i18n";
import {fetchSettings, type SettingsSnapshot} from "../api/settings";
import App from "../App.vue";
import {resolveLocale, type EffectiveLocale, type UiLocaleSetting} from "./locale";
import zhCNCommon from "./locales/zh-CN/common";
import zhCNProperties from "./locales/zh-CN/properties";
import zhCNSettings from "./locales/zh-CN/settings";
import zhCNShell from "./locales/zh-CN/shell";
import zhCNSheets from "./locales/zh-CN/sheets";
import enUSCommon from "./locales/en-US/common";
import enUSProperties from "./locales/en-US/properties";
import enUSSettings from "./locales/en-US/settings";
import enUSShell from "./locales/en-US/shell";
import enUSSheets from "./locales/en-US/sheets";

// 语言资源按功能域装两套同构文件，构建期合并（ARCH-DM-005 §5.1）
const messages = {
  "zh-CN": {common: zhCNCommon, properties: zhCNProperties, settings: zhCNSettings, shell: zhCNShell, sheets: zhCNSheets},
  "en-US": {common: enUSCommon, properties: enUSProperties, settings: enUSSettings, shell: enUSShell, sheets: enUSSheets},
};

// 唯一实例：语言状态全部经此实例流转；缺键运行时回退 zh-CN（键对称由 check:i18n 保证）
export const i18n = createI18n({
  legacy: false,
  locale: "zh-CN", // 初始基线；bootstrap 解析后由 applyLocale 覆盖
  fallbackLocale: "zh-CN",
  messages,
});

// 启动前设置读取超时：挂起超过该时限视为读取失败，按系统规则降级启动（I18N-04）
const SETTINGS_TIMEOUT_MS = 5_000;
const UI_LOCALE_KEY = "ui_locale";

// 从设置快照提取 ui_locale；缺失或非法值一律视为 system（后端已白名单校验，此处兜底）
function readUiLocaleSetting(snapshot: SettingsSnapshot): UiLocaleSetting {
  const value = snapshot.items.find(item => item.key === UI_LOCALE_KEY)?.value;
  return value === "zh-CN" || value === "en-US" || value === "system" ? value : "system";
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`settings 读取超时（${timeoutMs}ms）`)), timeoutMs);
    promise.then(
      value => { clearTimeout(timer); resolve(value); },
      error => { clearTimeout(timer); reject(error); },
    );
  });
}

// 应用生效语言：同步唯一 i18n 实例与 <html lang>（I18N-06）。
// 设置保存成功后的即时切换（Task 3）复用本函数。
export async function applyLocale(locale: EffectiveLocale): Promise<void> {
  i18n.global.locale.value = locale;
  if (typeof document !== "undefined") document.documentElement.lang = locale;
}

// 挂载前启动：请求设置 → 解析生效语言 → 初始化语言 → 注册 i18n 插件 → 挂载（ARCH-DM-005 §8.1）。
// 设置读取失败/超时不阻断启动：按系统语言规则继续挂载，不先渲染错误语言的完整 App；
// 读取失败的呈现沿用既有设置加载错误处理，不在启动路径引入阻断。
export async function bootstrap(): Promise<void> {
  let setting: UiLocaleSetting = "system";
  try {
    setting = readUiLocaleSetting(await withTimeout(fetchSettings(), SETTINGS_TIMEOUT_MS));
  } catch {
    // 降级：设置不可用时按 system 规则解析（显式 try 使降级路径显式可见）
  }
  await applyLocale(resolveLocale(setting));
  // 唯一实例必须先注册为插件再挂载，组件内 useI18n()/$t 才可用（I18N-01）
  const app = createApp(App);
  app.use(i18n);
  app.mount("#app");
}
