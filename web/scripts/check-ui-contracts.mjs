// UI 静态契约检查器（PLAN-DM-029 Task 1）。
//
// 这是前端视觉基础整改的自动门禁：它把「令牌化、语义化、可访问」三条设计约束变成
// 可失败的确定性检查，用「已知债务基线 + 新增即失败 + 迁移即清退」的棘轮保证债务
// 只减不增。
//
// 用法：
//   node scripts/check-ui-contracts.mjs [--root=<工作区根>] [--exceptions=<例外文件>]
// 无违规退出 0；有违规按 `file:line:column [rule] message` 输出并退出 1；例外文件
// 缺失或不可解析时退出 2（不静默通过）。
//
// 棘轮语义：
// - 违规指纹未在 `scripts/ui-contract-exceptions.json` 登记 → 报告并失败；
// - 已登记的例外在本次扫描中不再命中 → 报 `stale-exception` 并失败（迁移必须清退）；
// - 例外条目缺少 `reason`/`expiresWith`，或动态变量条目缺少五个登记字段 → 报错失败。
//
// 规则范围（与 ARCH-DM-007 §9.1 对齐，细节见 `ui-contracts/visual-values.mjs`）：
// `raw-hex-color` 与 `global-selector-in-component` 只作用于业务组件（`.vue`）与全局
// 业务样式表；令牌定义块（`:root`/`html[...]`）与 reset 层文件不在此列。

import {existsSync, readFileSync, readdirSync} from "node:fs";
import {dirname, join, relative, resolve} from "node:path";
import {fileURLToPath} from "node:url";

import {
  collectCustomPropertyDeclarations,
  findCircularVariables,
  findVarNodes,
  flattenVarNodes,
  parseDeclarations,
  parseRules,
} from "./ui-contracts/css-vars.mjs";
import {RULE, compareViolations, formatViolation, violation} from "./ui-contracts/types.mjs";
import {findHexColorsInValue, isBareGlobalSelector, isRawVisualValue, isTokenBlock} from "./ui-contracts/visual-values.mjs";
import {
  findRanges,
  findTags,
  getAttribute,
  hasAttribute,
  hasVisibleText,
  innerContent,
  splitSfc,
  textSignature,
  toPosition,
} from "./ui-contracts/vue-source.mjs";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
/** 默认工作区根：`web/`（脚本位于 `web/scripts/`）。 */
export const DEFAULT_WEB_ROOT = dirname(SCRIPT_DIR);
export const DEFAULT_EXCEPTIONS_FILE = "scripts/ui-contract-exceptions.json";
// 输出格式是检查器的对外契约，从本模块一并导出，调用方无需知道 types 模块。
export {formatViolation};
/** 全局业务样式表：这里的裸选择器属于业务债务。
 * `tokens.css`/`reset.css` 的全局选择器是分层设计本身要求，不在扫描范围。 */
const GLOBAL_BUSINESS_STYLESHEETS = new Set(["src/style.css", "src/styles/legacy.css", "src/styles/primitives.css"]);
const SOURCE_EXTENSIONS = [".vue", ".css"];
const SKIPPED_DIRECTORIES = new Set(["node_modules", "dist", ".git"]);
const REQUIRED_EXCEPTION_FIELDS = ["rule", "file", "fingerprint", "reason", "expiresWith"];
const REQUIRED_DYNAMIC_FIELDS = ["variable", "producer", "consumer", "reason", "expiresWith"];
// 结构图标：箭头、技术符号、几何图形、杂项符号与 dingbats、补充箭头、emoji 变体选择符。
// 刻意不含普通标点（如 «»）与中文文案，避免把正常文本判成图标。
const STRUCTURE_ICON_PATTERN =
  /[\u2190-\u21FF\u2300-\u23FF\u25A0-\u25FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]|[\u{1F300}-\u{1FAFF}]/gu;

function listSourceFiles(directory) {
  const files = [];
  const walk = (current) => {
    let entries;
    try {
      entries = readdirSync(current, {withFileTypes: true});
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (!SKIPPED_DIRECTORIES.has(entry.name)) walk(join(current, entry.name));
        continue;
      }
      if (SOURCE_EXTENSIONS.some((extension) => entry.name.endsWith(extension))) {
        files.push(join(current, entry.name));
      }
    }
  };
  walk(directory);
  return files.sort();
}

function isFilled(value) {
  return typeof value === "string" && value.trim() !== "";
}

function missingExceptionFields(entry) {
  if (entry === null || typeof entry !== "object") return REQUIRED_EXCEPTION_FIELDS;
  return REQUIRED_EXCEPTION_FIELDS.filter((field) => !isFilled(entry[field]));
}

function missingDynamicFields(entry) {
  if (entry === null || typeof entry !== "object") return REQUIRED_DYNAMIC_FIELDS;
  return REQUIRED_DYNAMIC_FIELDS.filter((field) => !isFilled(entry[field]));
}

/**
 * 收集 UI 静态契约违规。
 *
 * @param {{root?: string, srcDir?: string, exceptions?: object}} options
 *   `root` 为工作区根（默认 `web/`）；`exceptions` 为已解析的例外文件内容，传入
 *   空清单即可得到「未施加棘轮」的原始违规全集，用于生成基线。
 * @returns {{rule: string, file: string, line: number, column: number, message: string, fingerprint: string}[]}
 */
export function collectUiContractViolations(options = {}) {
  const root = resolve(options.root ?? DEFAULT_WEB_ROOT);
  const srcDir = options.srcDir ?? "src";
  const exceptions = options.exceptions ?? {exceptions: [], dynamicVariables: []};
  const violations = [];

  if (exceptions.exceptions !== undefined && !Array.isArray(exceptions.exceptions)) {
    violations.push(
      configViolation("例外清单 `exceptions` 必须是数组", "exceptions-not-array"),
    );
  }

  const dynamicEntries = Array.isArray(exceptions.dynamicVariables) ? exceptions.dynamicVariables : [];
  for (const [index, entry] of dynamicEntries.entries()) {
    const missing = missingDynamicFields(entry);
    if (missing.length === 0) continue;
    violations.push(
      configViolation(
        `动态变量条目必须同时登记 ${REQUIRED_DYNAMIC_FIELDS.join("、")}，第 ${index + 1} 条缺少：${missing.join("、")}`,
        `dynamic-entry-${index + 1}-${missing.join(",")}`,
        RULE.dynamicVariableNotRegistered,
      ),
    );
  }
  // 只要变量名出现在动态白名单里就视为「已登记」：条目本身缺字段时只报条目错误，
  // 不再对每个使用点重复报未定义引用，避免一次根因产生多条噪声。
  const dynamicNames = new Set(dynamicEntries.map((entry) => entry?.variable).filter(isFilled));

  const registered = new Map();
  for (const entry of exceptions.exceptions ?? []) {
    const missing = missingExceptionFields(entry);
    if (missing.length !== 0) {
      violations.push(configViolation(`例外条目缺少必填字段：${missing.join("、")}`, `exception-entry-${entry?.fingerprint ?? "unknown"}-${missing.join(",")}`));
      continue;
    }
    // 重复指纹会让后写入的条目静默生效、前一条永远不再命中，属于棘轮里的黑洞，必须拒绝。
    if (registered.has(entry.fingerprint)) {
      violations.push(configViolation(`例外指纹重复登记：${entry.fingerprint}`, `duplicate-fingerprint-${entry.fingerprint}`));
      continue;
    }
    registered.set(entry.fingerprint, entry);
  }

  const srcRoot = resolve(root, srcDir);
  const files = listSourceFiles(srcRoot).map((absolute) => ({
    absolute,
    relative: relative(root, absolute).split("\\").join("/"),
    text: readFileSync(absolute, "utf8"),
    sfc: null,
  }));

  // 第一遍：收集自定义属性声明。`.css` 文件的声明与组件内 `:root`/`html[...]` 块视为
  // 全局令牌；组件其它块的声明只在本文件内可见（Vue scoped 样式不会跨组件生效）。
  const globalDeclarations = new Set();
  const fileDeclarations = new Map();
  for (const file of files) {
    const names = new Set();
    if (file.relative.endsWith(".vue")) {
      file.sfc = splitSfc(file.text);
      for (const style of file.sfc.styles) {
        for (const declaration of collectCustomPropertyDeclarations(style.content)) {
          names.add(declaration.name);
          if (isTokenBlock(declaration.rule.selector)) globalDeclarations.add(declaration.name);
        }
      }
    } else {
      for (const declaration of collectCustomPropertyDeclarations(file.text)) {
        names.add(declaration.name);
        globalDeclarations.add(declaration.name);
      }
    }
    fileDeclarations.set(file.relative, names);
  }

  // 第二遍：规则判定。
  for (const file of files) {
    const localNames = fileDeclarations.get(file.relative) ?? new Set();
    const isDefined = (name) => localNames.has(name) || globalDeclarations.has(name) || dynamicNames.has(name);
    const emit = createEmitter(file.relative);
    if (file.sfc) {
      analyzeVueFile(file, emit, isDefined, violations);
    } else {
      analyzeStyleSource({
        file,
        text: file.text,
        offset: 0,
        emit,
        isDefined,
        violations,
        applyComponentRules: GLOBAL_BUSINESS_STYLESHEETS.has(file.relative),
      });
    }
  }

  return applyRatchet(violations, registered).sort(compareViolations);
}

function configViolation(message, semantic, rule = RULE.invalidExceptionEntry) {
  return violation({
    rule,
    file: DEFAULT_EXCEPTIONS_FILE,
    line: 1,
    column: 1,
    message,
    semantic,
    occurrence: 1,
  });
}

function createEmitter(relativePath) {
  const counters = new Map();
  return (spec) => {
    const key = `${spec.rule}|${spec.semantic}`;
    const occurrence = (counters.get(key) ?? 0) + 1;
    counters.set(key, occurrence);
    return violation({...spec, file: relativePath, occurrence});
  };
}

/** 检查一段 CSS 文本（整份 `.css` 文件或一个 `<style>` 块）。 */
function analyzeStyleSource({file, text, offset, emit, isDefined, violations, applyComponentRules}) {
  const at = (index) => toPosition(file.text, offset + index);
  const declarations = collectCustomPropertyDeclarations(text);
  const rules = parseRules(text);

  for (const cycle of findCircularVariables(declarations)) {
    violations.push(
      emit({
        rule: RULE.circularCssVariable,
        ...at(cycle.start),
        message: `CSS 变量存在循环引用：${cycle.names.join(" ← ")}`,
        semantic: cycle.names.join(","),
      }),
    );
  }

  // 必须遍历整棵引用树：外层变量已定义不代表 fallback 里的变量也成立，遗漏内层节点
  // 会放过 `var(--ok, var(--typo))` 这类实际写错的声明。
  for (const node of flattenVarNodes(findVarNodes(text))) {
    if (isDefined(node.name)) continue;
    violations.push(
      emit({
        rule: RULE.undefinedCssVariable,
        ...at(node.start),
        message: `引用了未定义或未登记的 CSS 变量：${node.name}`,
        semantic: node.name,
      }),
    );
  }

  for (const rule of rules) {
    if (applyComponentRules && !isTokenBlock(rule.selector) && isBareGlobalSelector(rule.selector)) {
      violations.push(
        emit({
          rule: RULE.globalSelectorInComponent,
          ...at(rule.selectorStart),
          message: `裸全局选择器缺少根类限定：${rule.selector}`,
          semantic: rule.selector,
        }),
      );
    }
    if (isTokenBlock(rule.selector)) continue;
    for (const declaration of parseDeclarations(text, rule)) {
      const valueIndex = offset + rule.contentStart + declaration.valueStart;
      const position = toPosition(file.text, valueIndex);
      for (const hex of findHexColorsInValue(declaration.value)) {
        violations.push(
          emit({
            rule: RULE.rawHexColor,
            ...position,
            message: `未登记的十六进制颜色：${hex}`,
            semantic: `${rule.selector} ${hex.toLowerCase()}`,
          }),
        );
      }
      if (isRawVisualValue(declaration)) {
        violations.push(
          emit({
            rule: RULE.rawVisualValue,
            ...position,
            message: `裸视觉值（应使用令牌或登记白名单）：${declaration.property}:${declaration.value}`,
            semantic: `${rule.selector} ${declaration.property}:${declaration.value}`,
          }),
        );
      }
    }
  }
}

function analyzeVueFile(file, emit, isDefined, violations) {
  for (const style of file.sfc.styles) {
    analyzeStyleSource({
      file,
      text: style.content,
      offset: style.offset,
      emit,
      isDefined,
      violations,
      // Vue scoped 样式是页面覆盖全局默认值的既定前提（ARCH-DM-007 §7），
      // 只有非 scoped 块里的元素选择器才是「裸全局选择器」。
      applyComponentRules: !style.scoped,
    });
  }

  const template = file.sfc.template;
  if (template === null) return;
  const at = (index) => toPosition(file.text, template.offset + index);
  const html = template.content;

  const labelRanges = findRanges(html, "label");
  const labelTargets = new Set(
    findTags(html, "label")
      .map((tag) => getAttribute(tag.text, "for"))
      .filter((value) => value !== null),
  );

  for (const tag of findTags(html, "button")) {
    const inner = innerContent(html, tag, "button");
    if (!hasAttribute(tag.text, "type")) {
      violations.push(
        emit({
          rule: RULE.explicitButtonType,
          ...at(tag.start),
          message: '按钮必须显式声明 type="button" 或 type="submit"',
          semantic: textSignature(inner) || getAttribute(tag.text, "class") || "button",
        }),
      );
    }
    const hasName =
      hasAttribute(tag.text, "aria-label") ||
      hasAttribute(tag.text, "aria-labelledby") ||
      hasAttribute(tag.text, "title") ||
      hasVisibleText(inner);
    if (!hasName) {
      violations.push(
        emit({
          rule: RULE.iconButtonName,
          ...at(tag.start),
          message: "图标按钮缺少可读名称（需要 aria-label、aria-labelledby、title 或可见文字）",
          semantic: getAttribute(tag.text, "class") || "button",
        }),
      );
    }
  }

  for (const tag of findTags(html, "input")) {
    const type = getAttribute(tag.text, "type");
    if (type === "hidden") continue;
    const insideLabel = labelRanges.some((range) => tag.start >= range.start && tag.start < range.end);
    const id = getAttribute(tag.text, "id");
    if (insideLabel || (id !== null && labelTargets.has(id))) continue;
    const signature =
      id ??
      getAttribute(tag.text, "name") ??
      getAttribute(tag.text, "v-model") ??
      getAttribute(tag.text, "placeholder") ??
      "";
    violations.push(
      emit({
        rule: RULE.visibleInputLabel,
        ...at(tag.start),
        message: "输入框缺少可见 label（label 包裹或 label[for] 关联至少满足一项）",
        semantic: `input:${type ?? "text"}:${signature}`,
      }),
    );
  }

  // 结构图标只在模板与样式块里判定；脚本与 i18n 文案里的普通标点不参与。
  const iconRegions = [
    {text: html.replace(/<!--[\s\S]*?-->/g, " "), offset: template.offset},
    ...file.sfc.styles.map((style) => ({text: style.content, offset: style.offset})),
  ];
  for (const region of iconRegions) {
    for (const match of region.text.matchAll(STRUCTURE_ICON_PATTERN)) {
      violations.push(
        emit({
          rule: RULE.unicodeStructureIcon,
          ...toPosition(file.text, region.offset + match.index),
          message: `以 Unicode 字形充当结构图标：${match[0]}（应使用本地 SVG 图标）`,
          semantic: match[0],
        }),
      );
    }
  }
}

function applyRatchet(violations, registered) {
  const hits = new Set();
  const kept = [];
  for (const item of violations) {
    if (registered.has(item.fingerprint)) {
      hits.add(item.fingerprint);
      continue;
    }
    kept.push(item);
  }
  for (const [fingerprint, entry] of registered) {
    if (hits.has(fingerprint)) continue;
    kept.push(
      violation({
        rule: RULE.staleException,
        file: entry.file,
        line: 1,
        column: 1,
        message: `登记的例外已不再命中，必须清退：${entry.rule} @ ${entry.file}`,
        semantic: fingerprint,
        occurrence: 1,
      }),
    );
  }
  return kept;
}

/** 解析命令行参数。 */
export function parseCliArgs(argv = []) {
  const options = {};
  for (const arg of argv) {
    if (arg.startsWith("--root=")) options.root = arg.slice("--root=".length);
    else if (arg.startsWith("--exceptions=")) options.exceptions = arg.slice("--exceptions=".length);
  }
  return options;
}

/** 执行 CLI：返回退出码与输出，便于测试直接断言而不依赖进程。 */
export function runCli(argv = []) {
  const options = parseCliArgs(argv);
  const root = resolve(options.root ?? DEFAULT_WEB_ROOT);
  const exceptionsPath = resolve(options.exceptions ?? join(root, DEFAULT_EXCEPTIONS_FILE));
  if (!existsSync(exceptionsPath)) {
    return {exitCode: 2, stdout: "", stderr: `未找到 UI 契约例外文件：${exceptionsPath}\n`};
  }
  let exceptions;
  try {
    exceptions = JSON.parse(readFileSync(exceptionsPath, "utf8"));
  } catch (error) {
    return {exitCode: 2, stdout: "", stderr: `无法解析 ${exceptionsPath}：${error.message}\n`};
  }
  const violations = collectUiContractViolations({root, exceptions});
  if (violations.length === 0) return {exitCode: 0, stdout: "", stderr: ""};
  return {exitCode: 1, stdout: `${violations.map(formatViolation).join("\n")}\n`, stderr: ""};
}

function main() {
  const result = runCli(process.argv.slice(2));
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  process.exitCode = result.exitCode;
}

if (process.argv[1] !== undefined && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
