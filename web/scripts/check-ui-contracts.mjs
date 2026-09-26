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
import {collectAssetViolations} from "./ui-contracts/font-assets.mjs";
import {collectTableCellViolations} from "./ui-contracts/table-cells.mjs";
import {NON_EXEMPTIBLE_RULES, RULE, compareViolations, formatViolation, violation} from "./ui-contracts/types.mjs";
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
    } catch (error) {
      // 目录读不了必须让整次扫描失败：默默跳过一层目录等于把这一层的债务从门禁里删掉，
      // 属于假绿。调用方（runCli）把它转成退出码 2 并说明原因。
      throw new Error(`无法读取目录：${current}（${error.code ?? error.message}）`, {cause: error});
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
    if (missing.length !== 0) {
      violations.push(
        configViolation(
          `动态变量条目必须同时登记 ${REQUIRED_DYNAMIC_FIELDS.join("、")}，第 ${index + 1} 条缺少：${missing.join("、")}`,
          `dynamic-entry-${index + 1}-${missing.join(",")}`,
          RULE.dynamicVariableNotRegistered,
        ),
      );
      continue;
    }
    // 生产者文件必须真实存在，否则白名单就是幽灵条目：它会让一个根本不存在的运行时
    // 来源静默通过。（只校验生产者：消费方可能有多处，但那不影响来源是否成立。）
    if (!existsSync(resolve(root, entry.producer))) {
      violations.push(
        configViolation(
          `动态变量 ${entry.variable} 登记的生产者文件不存在：${entry.producer}`,
          `dynamic-producer-missing-${entry.variable}`,
          RULE.dynamicVariableNotRegistered,
        ),
      );
    }
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
    // 例外条目是「按指纹登记、按指纹掩盖」的：下面 `registered` 以 `entry.fingerprint` 为键，
    // 而棘轮掩盖时只查 `item.fingerprint`。若条目的 `rule` 字段与指纹首段不一致，就会用
    // 一个可豁免的规则名把一条硬门禁违规掩盖掉（例如 `rule:"raw-visual-value"` 配上
    // `missing-font-asset|…` 的指纹），因此两个字段必须逐字一致，并且以指纹首段为准做
    // 硬门禁判定——指纹才是掩盖时真正生效的键。
    const fingerprintRule = String(entry.fingerprint).split("|")[0];
    if (entry.rule !== fingerprintRule) {
      violations.push(
        configViolation(
          `例外条目的 rule 与指纹首段不一致：rule=${entry.rule}，指纹=${entry.fingerprint}`,
          `rule-fingerprint-mismatch-${entry.fingerprint}`,
        ),
      );
      continue;
    }
    // 资产事实类硬门禁不可登记例外（Task 2 Step 7）：可白名单化等于没有门禁。
    if (NON_EXEMPTIBLE_RULES.includes(fingerprintRule)) {
      violations.push(configViolation(`硬门禁规则不允许登记例外：${fingerprintRule}`, `non-exemptible-${fingerprintRule}-${entry.fingerprint}`));
      continue;
    }
    // 例外表不得豁免「关于例外文件自身」的配置错误（Task 2 收口责任 C②）：配置类违规
    // （`invalid-exception-entry`、`stale-exception`）的 `file` 恒为例外文件自身，而它们的规则名
    // 不在 `NON_EXEMPTIBLE_RULES` 里。因此若只看规则名，就能再登一条条目把它自己的配置错误吃掉——
    // 棘轮将失去自我纠错能力（实测：自豁免条目会连同底层配置违规一起消失）。真正该挡住
    // 这种情况的不是规则名，而是**被指向的文件**：例外表的错误永远不由例外表自己豁免。
    if (normalizeExceptionFile(entry.file) === DEFAULT_EXCEPTIONS_FILE) {
      violations.push(
        configViolation(
          `例外条目不得豁免例外文件自身的配置错误：${entry.file}`,
          `exceptions-file-self-exemption-${entry.fingerprint}`,
        ),
      );
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

  // 第三遍：资产事实类规则（Task 2 Step 7）：字体文件是否存在/是否远程/合计体积与样式入口结构。
  violations.push(...collectAssetViolations({root, files, emitFor: createEmitter}));

  // 第四遍：表格单元格结构与令牌化规则（PLAN-DM-043 Task 1）：显式 vertical-align、
  // 单档令牌化 padding，以及登记在 STRUCTURAL_CELL_PAIRS 里的跨列结构零 padding 配对。
  violations.push(...collectTableCellViolations({files, emitFor: createEmitter}));

  return applyRatchet(violations, registered).sort(compareViolations);
}

/** 归一化例外条目里的文件路径，仅用于与例外文件自身比较：统一分隔符、去掉 `./` 与可选的 `web/` 前缀
 * （仓库里两种写法都存在：`src/App.vue` 与 `web/src/App.vue`）。 */
function normalizeExceptionFile(file) {
  return String(file).split("\\").join("/").replace(/^\.\//, "").replace(/^web\//, "");
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
      // `offset` 是该 `<style>` 块在文件中的起点，`declaration.valueStart` 相对块内容文本；
      // 两者相加才是文件绝对下标（`.css` 文件的块起点为 0，故与整份文件下标重合）。
      const position = toPosition(file.text, offset + declaration.valueStart);
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

/** 把 HTML 注释**逐字符等长**换成空格（保留换行）。
 *
 * 不能用变长替换（如把整段注释换成一个空格）：那样 `match.index` 之后再回查原文
 * 会产生整体偏移，把注释之后的图标位置算到前面的行上。
 */
function maskHtmlComments(html) {
  return html.replace(/<!--[\s\S]*?-->/g, (match) => match.replace(/[^\n]/g, " "));
}

// CSS 注释必须同样遮蔽（责任 X）：`iconRegions` 对模板区用了 `maskHtmlComments`，
// 但样式区原先直接取 `style.content` 原文，于是「只出现在 CSS 注释里的装饰性箭头」
// 被误判为结构图标——而同一字符写在模板注释或脚本注释里都不会。本规则自己的注释
// 写着「脚本与 i18n 文案里的普通标点不参与」，可见本意就是「只算真实标记与样式」。
// 与 maskHtmlComments 一致，**保持长度**（换行保留）以免扫描偏移错位（见上）。
function maskCssComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "));
}

/** 读取模板开标签的插槽名；非具名插槽（含 `v-slot` 缩写与 `#default`）返回 `"default"`，
 * 不是插槽模板返回 `null`。 */
function templateSlotName(openTagText) {
  const hash = /#([\w.-]+)/.exec(openTagText);
  if (hash) return hash[1];
  const named = /v-slot:([\w.-]+)/.exec(openTagText);
  if (named) return named[1];
  if (/\sv-slot(\s|=|>)/.test(openTagText)) return "default";
  return null;
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

  // 组件化输入调用点（PLAN-DM-029 Task 12 责任 U / 审查 I3）：
  // `<UiInput>`/`<UiSelect>` 的可见 label 在原语内部条件渲染，只看原语文件无法证明调用方
  // 真的提供了标签——新增一个无标签的 `<UiInput />` 时 `check:ui` 仍会全绿。因此必须在
  // 调用方模板里判定合法形态（同一字段只用其一，与 `UiInput.vue` 头注释一致）：
  // 1) 调用点自带非空 `label`（静态字符串或非空绑定表达式）；
  // 2) 位于 `FormField` 默认插槽内（`FormField` 渲染可见 label 并经插槽下发 `id`），
  //    且 `FormField` 自身 label 非空——`FormField` 缺 label 是单独的违规，不落到控件头上；
  // 3) 同一模板存在**有可见文字**的外部 `<label for="X">`，与控件的 `id` 值一致
  //    （含 `:for`/`:id` 绑定表达式文本相等，判定口径与上方裸 `<input>` 扫描相同）。
  // 已知静态边界：绑定表达式只能比对文本，不能求值——`:label="maybeEmpty"` 这类
  // 「可能为空」的绑定按非空对待，由组件评审与 e2e 兜底。
  const componentInputTags = [
    ...findTags(html, "UiInput"),
    ...findTags(html, "ui-input"),
    ...findTags(html, "UiSelect"),
    ...findTags(html, "ui-select"),
  ].sort((a, b) => a.start - b.start);
  if (componentInputTags.length > 0) {
    const formFieldRanges = [...findRanges(html, "FormField"), ...findRanges(html, "form-field")];
    // FormField 内的具名插槽内容不是默认插槽（`#hint` 里的控件不被 FormField 的 label 覆盖）。
    const namedSlotRanges = findRanges(html, "template").filter((range) => {
      const open = html.slice(range.start, range.contentStart);
      const slotName = templateSlotName(open);
      return slotName !== null && slotName !== "default";
    });
    const visibleLabelFors = new Set(
      findTags(html, "label")
        .map((tag) => {
          const forValue = getAttribute(tag.text, "for");
          const closeIndex = html.indexOf("</label>", tag.openEnd);
          return {forValue, visible: closeIndex !== -1 && hasVisibleText(html.slice(tag.openEnd, closeIndex))};
        })
        .filter((item) => item.forValue !== null && item.visible)
        .map((item) => item.forValue),
    );

    for (const tag of componentInputTags) {
      const labelAttr = getAttribute(tag.text, "label");
      if (labelAttr !== null && labelAttr.trim() !== "") continue;
      const component = /^<([a-z-]+)/i.exec(tag.text)[1] ?? "component-input";
      const inDefaultFormFieldSlot = formFieldRanges.some(
        (range) =>
          tag.start >= range.start && tag.start < range.end &&
          !namedSlotRanges.some((slot) => slot.start >= range.start && slot.end <= range.end && tag.start >= slot.start && tag.start < slot.end),
      );
      if (inDefaultFormFieldSlot) continue;
      const controlId = getAttribute(tag.text, "id");
      if (controlId !== null && visibleLabelFors.has(controlId)) continue;
      const signature = controlId ?? getAttribute(tag.text, "v-model") ?? getAttribute(tag.text, "placeholder") ?? "";
      violations.push(
        emit({
          rule: RULE.visibleInputLabel,
          ...at(tag.start),
          message: "组件化输入缺少可见 label（自带非空 label、FormField 默认插槽或外部 label[for] 关联至少满足一项）",
          semantic: `${component}:${signature}`,
        }),
      );
    }

    for (const range of formFieldRanges) {
      const open = html.slice(range.start, range.contentStart);
      const labelAttr = getAttribute(open, "label");
      if (labelAttr !== null && labelAttr.trim() !== "") continue;
      const signature = textSignature(html.slice(range.contentStart, range.contentEnd)) || "form-field";
      violations.push(
        emit({
          rule: RULE.visibleInputLabel,
          ...at(range.start),
          message: "FormField 缺少非空 label（可见标签是字段的可访问名称来源）",
          semantic: `form-field:${signature}`,
        }),
      );
    }
  }

  // 结构图标只在模板与样式块里判定；脚本与 i18n 文案里的普通标点不参与。
  const iconRegions = [
    {text: maskHtmlComments(html), offset: template.offset},
    ...file.sfc.styles.map((style) => ({text: maskCssComments(style.content), offset: style.offset})),
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
  let violations;
  try {
    violations = collectUiContractViolations({root, exceptions});
  } catch (error) {
    // 扫描根目录不可读/不存在时不能默默当作「零违规」通过，必须明确失败。
    return {exitCode: 2, stdout: "", stderr: `扫描源码失败：${error.message}\n`};
  }
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
