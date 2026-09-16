// 字体资产与样式入口门禁（PLAN-DM-029 Task 2 Step 7）。
//
// `visual-values.mjs` 只能看选择器与声明字面值，看不到「引用的文件在不在」「合计多大」这类
// 资产事实。本模块补上这两类静态断言，产出与检查器其它规则相同的 Violation：
// - `missing-font-asset`：`@font-face` 引用的本地字体文件不存在；
// - `remote-font-url`：`@font-face` 引用远程 URL（生产运行时不得访问 CDN，ARCH-DM-007 §4.2）；
// - `font-budget-exceeded`：本地字体资产合计超过预算（ARCH-DM-007 §4.2 的 250 KiB）；
// - `entry-stylesheet-not-import-only`：样式入口出现层顺序声明与 `@import` 之外的内容。
//
// 相对 URL 按 CSS 规范从样式表所在目录解析（Vite 对 SFC `<style>` 块同样以组件文件所在
// 目录为基准）；以 `/` 开头的 URL 从工作区根解析。
//
// 这四条规则属于硬门禁，`types.mjs` 的 `NON_EXEMPTIBLE_RULES` 禁止它们在例外表中登记。

import {existsSync, statSync} from "node:fs";
import {dirname, resolve} from "node:path";
import {maskNonCode, parseDeclarations, parseRules} from "./css-vars.mjs";
import {toPosition} from "./vue-source.mjs";
import {RULE} from "./types.mjs";

/** 生产字体资产合计预算：250 KiB（ARCH-DM-007 §4.2）。 */
export const FONT_BUDGET_BYTES = 256000;
/** 样式入口文件：层顺序声明 + 四个 `@import`，不得承载业务规则。 */
export const ENTRY_STYLESHEET = "src/style.css";
/** 入口必须固定的层顺序（PLAN-DM-029 Global Constraints）。 */
export const ENTRY_LAYER_ORDER = ["tokens", "reset", "primitives", "legacy"];
/** 入口允许导入的分层样式表。 */
export const ENTRY_IMPORTS = ENTRY_LAYER_ORDER.map((name) => `./styles/${name}.css`);

const URL_IN_VALUE_PATTERN = /url\(\s*(?:"([^"]*)"|'([^']*)'|([^)'"]*))\s*\)/gi;
/** 远程 URL：带 scheme，或协议相对（`//host/...`）。 */
const REMOTE_URL_PATTERN = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;
// 入口语句一律在 `maskNonCode` 结果上匹配：注释与字符串内容已抹平，因此注释插在语句
// 前后、或语句里带字符串都不会误判；字符串内容需要另从原文提取。
const IMPORT_STATEMENT_PATTERN = /^@import\s+["'][^"']*["']$/;
const IMPORT_PATH_PATTERN = /^@import\s+["']([^"']+)["']/;
const LAYER_STATEMENT_PATTERN = /^@layer\s+([A-Za-z][\w-]*(?:\s*,\s*[A-Za-z][\w-]*)*)$/;

/**
 * 汇总资产事实类规则。
 *
 * `files` 是扫描结果：`{relative, text, sfc}`，`sfc` 为 `splitSfc` 结果或 `null`。
 * `emitFor(relative)` 由调用方提供按文件计数出现序号的 emit 工厂；本模块按文件缓存它，
 * 保证同一 (rule, semantic) 同一文件下不会因为多段样式区域而重号。
 */
export function collectAssetViolations({root, files, emitFor, budgetBytes = FONT_BUDGET_BYTES}) {
  const emitters = new Map();
  const emit = (spec) => {
    if (!emitters.has(spec.file)) emitters.set(spec.file, emitFor(spec.file));
    return emitters.get(spec.file)(spec);
  };
  const regions = [];
  for (const file of files) {
    for (const block of file.sfc ? file.sfc.styles : [{content: file.text, offset: 0}]) {
      regions.push({file: file.relative, text: file.text, content: block.content, offset: block.offset});
    }
  }
  return [
    ...collectFontAssetViolations({root, regions, emit, budgetBytes}),
    ...collectEntryStylesheetViolations({root, files, emit}),
  ];
}

/** `@font-face` 规则的选择器拼写（小写比较）。 */
const FONT_FACE_SELECTOR = "@font-face";

/** 校验 `@font-face` 引用的字体资产：本地文件必须存在、不得远程、合计不得超预算。 */
function collectFontAssetViolations({root, regions, emit, budgetBytes}) {
  const violations = [];
  const sizes = new Map();
  let firstAsset = null;
  for (const region of regions) {
    // `@font-face` 是 at-rule，`parseRules` 默认不返回它（避免裸选择器误报），
    // 这里显式索取 at-rule 块，否则整条字体门禁会静默失效。
    for (const rule of parseRules(region.content, {includeAtRules: true})) {
      if (maskNonCode(rule.selector).trim().toLowerCase() !== FONT_FACE_SELECTOR) continue;
      for (const declaration of parseDeclarations(region.content, rule)) {
        if (declaration.property.trim().toLowerCase() !== "src") continue;
        const raw = region.content.slice(declaration.valueStart, declaration.valueEnd);
        for (const match of raw.matchAll(URL_IN_VALUE_PATTERN)) {
          const url = (match[1] ?? match[2] ?? match[3] ?? "").trim();
          if (url === "") continue;
          const position = toPosition(region.text, region.offset + declaration.valueStart + match.index);
          const base = {file: region.file, ...position};
          if (REMOTE_URL_PATTERN.test(url)) {
            violations.push(emit({...base, rule: RULE.remoteFontUrl, message: `字体不得引用远程 URL：${url}`, semantic: url}));
            continue;
          }
          const path = localFontPath(root, region.file, url);
          if (!existsSync(path)) {
            violations.push(emit({...base, rule: RULE.missingFontAsset, message: `字体文件不存在：${url}`, semantic: url}));
            continue;
          }
          if (!sizes.has(path)) sizes.set(path, statSync(path).size);
          firstAsset ??= base;
        }
      }
    }
  }
  const total = [...sizes.values()].reduce((sum, size) => sum + size, 0);
  if (total > budgetBytes && firstAsset !== null) {
    violations.push(
      emit({
        ...firstAsset,
        rule: RULE.fontBudgetExceeded,
        message: `本地字体资产合计 ${total} 字节，超过预算 ${budgetBytes} 字节`,
        semantic: `font-budget:${total}:${budgetBytes}`,
      }),
    );
  }
  return violations;
}

/**
 * 校验样式入口：只允许层顺序声明、四个分层 `@import` 以及注释与空行。
 *
 * 注释与空行先用 `maskNonCode` 抹平再切分语句，因此后续任务可以自由添加入口注释；出现
 * 规则块、多余语句、层顺序不符或导入清单不完整都算违规。
 */
function collectEntryStylesheetViolations({root, files, emit}) {
  const violations = [];
  // 入口文件缺失（或未被扫描）时，下面的逐文件循环一条都不走，整条入口门禁会静默失效：
  // 「入口只能是入口」这条约束等于被删除，而这恰好是删掉/改名入口文件时才会发生的场景。
  // 这里先断言入口确实在扫描结果里。
  if (!files.some((file) => file.relative === ENTRY_STYLESHEET)) {
    const onDisk = existsSync(resolve(root, ENTRY_STYLESHEET));
    violations.push(
      emit({
        rule: RULE.entryStylesheetNotImportOnly,
        file: ENTRY_STYLESHEET,
        line: 1,
        column: 1,
        message: onDisk ? `样式入口未被扫描：${ENTRY_STYLESHEET}` : `样式入口文件不存在：${ENTRY_STYLESHEET}`,
        semantic: onDisk ? "unscanned-entry-stylesheet" : "missing-entry-stylesheet",
      }),
    );
  }
  for (const entry of files) {
    if (entry.relative !== ENTRY_STYLESHEET) continue;
    const report = (offset, message, semantic) =>
      violations.push(
        emit({
          rule: RULE.entryStylesheetNotImportOnly,
          file: entry.relative,
          ...toPosition(entry.text, offset),
          message,
          semantic,
        }),
      );
    for (const rule of parseRules(entry.text)) {
      const selector = maskNonCode(rule.selector).trim().replace(/\s+/g, " ").slice(0, 40);
      report(rule.selectorStart, `样式入口不得承载样式规则：${selector}`, `rule:${selector}`);
    }
    const imports = [];
    let order = null;
    let cursor = 0;
    for (const segment of maskNonCode(entry.text).split(";")) {
      const from = cursor;
      cursor += segment.length + 1;
      const masked = segment.trim();
      if (masked === "") continue;
      const sliced = entry.text.slice(from, from + segment.length);
      const raw = sliced.trim();
      const offset = from + (sliced.length - sliced.trimStart().length);
      const layerMatch = LAYER_STATEMENT_PATTERN.exec(masked);
      if (layerMatch !== null) {
        const names = layerMatch[1].split(",").map((name) => name.trim());
        order ??= {names, offset};
        if (names.join(",") !== ENTRY_LAYER_ORDER.join(",")) {
          report(offset, `层顺序必须为 ${ENTRY_LAYER_ORDER.join(", ")}，实际为 ${names.join(", ")}`, `layer-order:${names.join(",")}`);
        }
        continue;
      }
      if (IMPORT_STATEMENT_PATTERN.test(masked)) {
        const path = IMPORT_PATH_PATTERN.exec(raw);
        imports.push(path === null ? raw : path[1]);
        continue;
      }
      // 规则块已由上面的 `parseRules` 逐条报告，这里只报真正的「多余语句」，避免同一次
      // 错误产生两条噪声。
      if (masked.includes("{")) continue;
      report(offset, `样式入口只能包含层顺序声明与 @import：${raw.slice(0, 40)}`, `statement:${masked.slice(0, 40)}`);
    }
    if (order === null) {
      report(0, `样式入口缺少层顺序声明：@layer ${ENTRY_LAYER_ORDER.join(", ")}`, "missing-layer-order");
    } else if (order.names.join(",") === ENTRY_LAYER_ORDER.join(",")) {
      const actual = [...imports].sort().join(",");
      if (actual !== [...ENTRY_IMPORTS].sort().join(",")) {
        report(order.offset, `样式入口必须导入四个分层样式表，实际导入 ${imports.join(", ") || "无"}`, `imports:${actual}`);
      }
    }
  }
  return violations;
}

function localFontPath(root, stylesheet, url) {
  const target = url.split("#")[0].split("?")[0];
  if (target.startsWith("/")) return resolve(root, `.${target}`);
  return resolve(root, dirname(stylesheet), target);
}
