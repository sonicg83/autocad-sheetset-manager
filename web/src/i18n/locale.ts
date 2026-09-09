// 语言解析纯逻辑（ARCH-DM-005 §4.2 / I18N-03）。
// 不依赖 vue-i18n 与 DOM 结构，便于单测；navigator 访问异常按空列表处理。
export type UiLocaleSetting = "system" | "zh-CN" | "en-US";
export type EffectiveLocale = "zh-CN" | "en-US";

// 产品基线回退语言：无法读取/识别系统语言时保持既有中文界面（ARCH-DM-005 §4.2 第 4 条）
export const FALLBACK_LOCALE: EffectiveLocale = "zh-CN";

// 读取浏览器/WebView2 的系统语言偏好：navigator.languages 优先，为空再读 navigator.language
export function systemLanguages(): readonly string[] {
  try {
    const nav = globalThis.navigator;
    if (nav.languages && nav.languages.length > 0) return nav.languages;
    if (nav.language) return [nav.language];
    return [];
  } catch {
    return [];
  }
}

// 取语言标签的主子标签（zh-TW → zh；zh_Hans → zh）
function primarySubtag(tag: string): string {
  return tag.trim().toLowerCase().split(/[-_]/, 1)[0];
}

// 主子标签形态可识别：2～8 个字母（ISO 639 语言码 / 脚本等合法形态），排除 undetermined
function isRecognizableLanguageTag(tag: string): boolean {
  const primary = primarySubtag(tag);
  return /^[a-z]{2,8}$/.test(primary) && primary !== "und";
}

// 解析生效语言：显式设置优先于系统语言；zh-* → zh-CN；
// 其他可识别非中文语言 → en-US；空列表/异常/全部不可识别回退 zh-CN。
export function resolveLocale(value: UiLocaleSetting, languages?: readonly string[]): EffectiveLocale {
  if (value === "zh-CN" || value === "en-US") return value; // 显式设置优先
  const candidates = languages ?? systemLanguages();
  for (const tag of candidates) {
    if (typeof tag !== "string") continue;
    if (primarySubtag(tag) === "zh") return "zh-CN";
    if (isRecognizableLanguageTag(tag)) return "en-US";
  }
  return FALLBACK_LOCALE;
}
