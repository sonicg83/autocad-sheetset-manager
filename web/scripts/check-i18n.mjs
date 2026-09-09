// 语言包完整性门禁（PLAN-DM-021 Task 10 / I18N-14 / ARCH-DM-005 §5.1）。
// 校验四类约束，任一违规非零退出并定位域/键/文件：
// 1) 中英文域文件集合一致；
// 2) 每个域内键集合一致（缺键/多键/域内重复键），报告 <域>.<键> 与所属资源文件；
// 3) 每个键的命名插值参数集合（{name}）中英一致；
// 4) web/src 无用户可见硬编码中文：源码字符串/模板文本（注释经词法剥离）出现
//    [一-龥] 即违规；豁免仅限 web/src/i18n/hardcoded-allowlist.json 登记项
//    （用户数据示例/协议常量/品牌名，逐项注明原因，不得用于普通 UI 文案）。
// Node ≥22.18 默认支持 .ts 类型剥离，可直接 import 语言资源文件。
import {readdirSync, readFileSync} from "node:fs";
import path from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcRoot = path.join(webRoot, "src");
const localesDir = path.join(srcRoot, "i18n", "locales");
const allowlistPath = path.join(srcRoot, "i18n", "hardcoded-allowlist.json");
const REQUIRED_LOCALES = ["zh-CN", "en-US"];
const CJK = /[一-龥]/; // 计划扫描口径 [一-龥]，与 Step 5 反向扫描一致

let failed = false;
function fail(message) {
  console.error(`[check:i18n] ${message}`);
  failed = true;
}

// ---- 1~3：语言资源键与参数校验 ----

function listDomainFiles(localeDir) {
  return readdirSync(localeDir).filter(name => name.endsWith(".ts")).map(name => name.replace(/\.ts$/, "")).sort();
}

// 把嵌套资源对象压平成点路径键；叶子必须是字符串（翻译文本），不允许对象/数组叶。
// 产出键->文本列表（同键重复出现即域内重复键，单独报告）。
function flattenEntries(prefix, value, out) {
  for (const [key, child] of Object.entries(value)) {
    const keyPath = prefix === "" ? key : `${prefix}.${key}`;
    if (child !== null && typeof child === "object") {
      if (Array.isArray(child)) throw new Error(`语言资源不允许数组叶子：${keyPath}`);
      flattenEntries(keyPath, child, out);
    } else if (typeof child === "string") {
      out.push([keyPath, child]);
    } else {
      throw new Error(`语言资源叶子必须是字符串：${keyPath}`);
    }
  }
  return out;
}

// vue-i18n 命名插值参数：{name}；字面量转义 {'@'} 之类不会命中
const PARAM_RE = /\{(\w+)\}/g;

function extractParams(text) {
  return [...text.matchAll(PARAM_RE)].map(match => match[1]);
}

async function loadDomain(locale, domain) {
  const file = path.join(localesDir, locale, `${domain}.ts`);
  const module = await import(pathToFileURL(file).href);
  const entries = flattenEntries("", module.default, []);
  const keys = new Map(); // key -> 文本（重复键在此暴露）
  const duplicates = [];
  for (const [key, text] of entries) {
    if (keys.has(key)) duplicates.push(key);
    keys.set(key, text);
  }
  return {file, keys, duplicates};
}

async function loadLocale(locale) {
  const domains = listDomainFiles(path.join(localesDir, locale));
  const byDomain = new Map();
  for (const domain of domains) {
    try {
      byDomain.set(domain, await loadDomain(locale, domain));
    } catch (error) {
      fail(`读取 ${locale}/${domain}.ts 失败：${error.message}`);
    }
  }
  return {domains, byDomain};
}

const locales = {};
for (const locale of REQUIRED_LOCALES) {
  locales[locale] = await loadLocale(locale);
}

const [zhLocale, enLocale] = REQUIRED_LOCALES;
const zhDomains = locales[zhLocale].domains;
const enDomains = locales[enLocale].domains;
if (zhDomains.join(",") !== enDomains.join(",")) {
  fail(`中英文域文件集合不一致：zh-CN=[${zhDomains}] en-US=[${enDomains}]`);
} else {
  for (const domain of zhDomains) {
    const zh = locales[zhLocale].byDomain.get(domain);
    const en = locales[enLocale].byDomain.get(domain);
    if (zh === undefined || en === undefined) continue; // 域集合不一致已单独报告
    for (const key of zh.keys.keys()) {
      if (!en.keys.has(key)) fail(`en-US 缺少键 ${domain}.${key}（zh-CN 见 ${path.relative(webRoot, zh.file)}）`);
    }
    for (const key of en.keys.keys()) {
      if (!zh.keys.has(key)) fail(`zh-CN 缺少键 ${domain}.${key}（en-US 见 ${path.relative(webRoot, en.file)}）`);
    }
    for (const key of zh.duplicates) fail(`zh-CN 域 ${domain} 存在重复键 ${key}（${path.relative(webRoot, zh.file)}）`);
    for (const key of en.duplicates) fail(`en-US 域 ${domain} 存在重复键 ${key}（${path.relative(webRoot, en.file)}）`);
    // 命名插值参数一致性（I18N-08）：多参数渲染出空、少参数渲染原文，都必须构建期拦截
    for (const [key, zhText] of zh.keys) {
      const enText = en.keys.get(key);
      if (enText === undefined) continue; // 缺键已单独报告
      const zhParams = new Set(extractParams(zhText));
      const enParams = new Set(extractParams(enText));
      for (const param of zhParams) {
        if (!enParams.has(param)) fail(`键 ${domain}.${key} 命名参数不一致：en-US 缺少 {${param}}（zh-CN：${path.relative(webRoot, zh.file)} / en-US：${path.relative(webRoot, en.file)}）`);
      }
      for (const param of enParams) {
        if (!zhParams.has(param)) fail(`键 ${domain}.${key} 命名参数不一致：zh-CN 缺少 {${param}}（zh-CN：${path.relative(webRoot, zh.file)} / en-US：${path.relative(webRoot, en.file)}）`);
      }
    }
  }
}

// ---- 4：web/src 硬编码中文扫描（注释剥离后检查字符串与模板文本） ----

// 轻量词法扫描：返回出现 CJK 的行号集合。状态机剥离 //、/* */、<!-- --> 注释，
// 并按"前一有效 token"启发式识别正则字面量（除法不误判、字符类内的引号不破坏状态）；
// 其余任意状态（代码、字符串字面量、模板文本、标签属性值）出现 [一-龥] 即命中。
const REGEX_PRECEDING_KEYWORDS = new Set(["return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "case", "do", "else"]);
const REGEX_PRECEDING_CHARS = new Set(["=", "(", "[", "{", "}", ";", ":", ",", "!", "&", "|", "?", "+", "-", "*", "%", "^", "~", "<", ">", "\n"]);

function scanChineseLines(source) {
  const hits = new Set();
  let line = 1;
  let state = "code"; // code | sq | dq | bq | line | block | html | regex | regexClass
  let prevChar = "\n"; // 上一有效（非空白）字符，用于除法/正则判别
  let prevWord = ""; // 尾随标识符，用于 return/typeof 等关键字后接正则的判别
  const n = source.length;
  for (let i = 0; i < n; i += 1) {
    const char = source[i];
    const next = source[i + 1];
    if (char === "\n") {
      line += 1;
      if (state === "line") state = "code";
      if (state === "regex" || state === "regexClass") state = "code"; // 正则不跨行：误判即止损
      continue;
    }
    const wasCode = state === "code"; // 进入本字符时的状态：prev 判别值只能反映"前一个"字符
    switch (state) {
      case "line":
        break;
      case "block":
        if (char === "*" && next === "/") { i += 1; state = "code"; }
        break;
      case "html":
        // 仅以 --> 收尾（消费 > 前先看前两个字符是否为 --）
        if (char === ">" && source[i - 1] === "-" && source[i - 2] === "-") state = "code";
        break;
      case "sq":
      case "dq":
        if (char === "\\") i += 1;
        else if ((state === "sq" && char === "'") || (state === "dq" && char === '"')) state = "code";
        else if (CJK.test(char)) hits.add(line);
        break;
      case "bq":
        if (char === "\\") i += 1;
        else if (char === "`") state = "code";
        else if (CJK.test(char)) hits.add(line);
        break;
      case "regex":
        if (char === "\\") i += 1;
        else if (char === "[") state = "regexClass";
        else if (char === "/") state = "code";
        else if (CJK.test(char)) hits.add(line);
        break;
      case "regexClass":
        if (char === "\\") i += 1;
        else if (char === "]") state = "regex";
        else if (CJK.test(char)) hits.add(line);
        break;
      default:
        if (char === "/" && next === "/") { i += 1; state = "line"; }
        else if (char === "/" && next === "*") { i += 1; state = "block"; }
        else if (char === "<" && next === "!" && source.slice(i, i + 4) === "<!--") { i += 3; state = "html"; }
        else if (char === "/" && (REGEX_PRECEDING_CHARS.has(prevChar) || REGEX_PRECEDING_KEYWORDS.has(prevWord))) state = "regex";
        else if (char === "'") state = "sq";
        else if (char === '"') state = "dq";
        else if (char === "`") state = "bq";
        else if (CJK.test(char)) hits.add(line);
    }
    if (wasCode && state === "code" && !/\s/.test(char)) {
      if (/\w/.test(char)) prevWord = prevWord + char;
      else prevWord = "";
      prevChar = char;
    }
  }
  return hits;
}

function listSourceFiles(dir, out = []) {
  for (const name of readdirSync(dir, {withFileTypes: true})) {
    const full = path.join(dir, name.name);
    if (name.isDirectory()) {
      if (name.name === "locales") continue; // 语言资源本身即是翻译正文
      listSourceFiles(full, out);
    } else if (/\.d\.ts$/.test(name.name)) {
      continue; // 生成产物（openapi 契约类型），中文仅存在于生成的 JSDoc 注释
    } else if (/\.test\.ts$/.test(name.name)) {
      continue; // vitest 单测不进生产构建，测试标题/夹具中文非用户可见界面文案
    } else if (/\.(ts|vue)$/.test(name.name)) {
      out.push(full);
    }
  }
  return out;
}

// 豁免清单：只收用户数据示例、协议常量与必要品牌名，逐项注明原因；
// 条目 {file, match, reason}，file 相对 web/src（正斜杠），match 为行内正则（缺省 = 整文件）。
const allowlist = JSON.parse(readFileSync(allowlistPath, "utf8"));
// 豁免条目必须逐项注明原因，防止清单演变为批量忽略
for (const entry of allowlist) {
  if (typeof entry.file !== "string" || typeof entry.reason !== "string" || entry.reason.trim() === "") {
    fail(`hardcoded-allowlist.json 条目缺少 file/reason：${JSON.stringify(entry)}`);
  }
}

function isAllowed(relativeFile, lineText) {
  return allowlist.some(entry => {
    if (entry.file !== relativeFile) return false;
    if (entry.match === undefined) return true;
    try {
      return new RegExp(entry.match).test(lineText);
    } catch {
      throw new Error(`hardcoded-allowlist.json 条目非法正则 ${entry.match}（${entry.file}）`);
    }
  });
}

const sourceFiles = listSourceFiles(srcRoot);
for (const file of sourceFiles) {
  const relative = path.relative(srcRoot, file).split(path.sep).join("/");
  const lines = readFileSync(file, "utf8").split("\n");
  const hits = scanChineseLines(lines.join("\n"));
  for (const lineNumber of [...hits].sort((a, b) => a - b)) {
    const text = (lines[lineNumber - 1] ?? "").trim();
    if (isAllowed(relative, text)) continue;
    fail(`web/src/${relative}:${lineNumber} 出现硬编码中文：${text}`);
  }
}

if (failed) {
  console.error("[check:i18n] 语言包完整性校验失败，构建被门禁拦截（I18N-14）。");
  process.exit(1);
}
const totalKeys = [...locales[zhLocale].byDomain.values()].reduce((sum, domain) => sum + domain.keys.size, 0);
console.log(`[check:i18n] 中英文键与插值参数对称（${totalKeys} 键 / ${zhDomains.length} 域），web/src 无未登记硬编码中文。`);
