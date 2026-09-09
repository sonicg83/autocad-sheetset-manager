// 最小语言包键对称检查（PLAN-DM-021 Task 2，I18N-14 的构建期门禁雏形）。
// 仅校验：zh-CN 与 en-US 的域文件集合一致、每个域内键集合（点路径）一致；
// 缺键/多键非零退出。允许清单与用户可见硬编码扫描属 Task 10，不在此实现。
// Node ≥22.18 默认支持 .ts 类型剥离，可直接 import 语言资源文件。
import {readdirSync} from "node:fs";
import path from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";

const localesDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "i18n", "locales");
const REQUIRED_LOCALES = ["zh-CN", "en-US"];

function listDomainFiles(localeDir) {
  return readdirSync(localeDir).filter(name => name.endsWith(".ts")).sort();
}

// 把嵌套资源对象压平成点路径键集合；叶子必须是字符串（翻译文本），不允许对象/数组叶
function flattenKeys(prefix, value, out) {
  for (const [key, child] of Object.entries(value)) {
    const keyPath = prefix === "" ? key : `${prefix}.${key}`;
    if (child !== null && typeof child === "object") {
      if (Array.isArray(child)) throw new Error(`语言资源不允许数组叶子：${keyPath}`);
      flattenKeys(keyPath, child, out);
    } else if (typeof child === "string") {
      out.add(keyPath);
    } else {
      throw new Error(`语言资源叶子必须是字符串：${keyPath}`);
    }
  }
  return out;
}

async function loadLocaleKeys(locale) {
  const localeDir = path.join(localesDir, locale);
  const domains = listDomainFiles(localeDir);
  const keys = new Set();
  for (const domain of domains) {
    const module = await import(pathToFileURL(path.join(localeDir, domain)).href);
    flattenKeys("", module.default, keys);
  }
  return {domains, keys};
}

let failed = false;
const locales = {};
for (const locale of REQUIRED_LOCALES) {
  try {
    locales[locale] = await loadLocaleKeys(locale);
  } catch (error) {
    console.error(`[check:i18n] 读取 ${locale} 语言包失败：${error.message}`);
    failed = true;
  }
}

if (!failed) {
  const [zh, en] = REQUIRED_LOCALES;
  const zhDomains = locales[zh].domains.join(",");
  const enDomains = locales[en].domains.join(",");
  if (zhDomains !== enDomains) {
    console.error(`[check:i18n] 中英文域文件集合不一致：zh-CN=[${zhDomains}] en-US=[${enDomains}]`);
    failed = true;
  } else {
    const missingInEn = [...locales[zh].keys].filter(key => !locales[en].keys.has(key));
    const missingInZh = [...locales[en].keys].filter(key => !locales[zh].keys.has(key));
    if (missingInEn.length > 0) {
      console.error(`[check:i18n] en-US 缺少以下键：\n  ${missingInEn.join("\n  ")}`);
      failed = true;
    }
    if (missingInZh.length > 0) {
      console.error(`[check:i18n] zh-CN 缺少以下键：\n  ${missingInZh.join("\n  ")}`);
      failed = true;
    }
  }
}

if (failed) {
  console.error("[check:i18n] 中英文键集合不对称，构建失败（I18N-14）。");
  process.exit(1);
}
console.log(`[check:i18n] 中英文键集合对称（${locales[REQUIRED_LOCALES[0]].keys.size} 键 / ${locales[REQUIRED_LOCALES[0]].domains.length} 域）。`);
