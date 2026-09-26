// 表格单元格对齐与 padding 门禁（PLAN-DM-043 Task 1）。
//
// `visual-values.mjs` 只按「属性是否用了令牌」检查视觉值，看不到表格单元格的两条结构性
// 约束（SPEC-DM-006 §6.4「单元格对齐契约」、ARCH-DM-007 §4.3）：
// - `table-cell-vertical-align`：**所有** `th/td` 规则必须显式声明 `vertical-align`，
//   取值仅 `middle`（默认）与 `top`（多行长文本单元格）；禁止依赖浏览器默认基线对齐。
// - `table-cell-padding`：普通表头/数据格的 padding 必须消费令牌、同表同档，且不得用
//   裸值或 `padding:0`；跨列承载独立编辑容器的结构性 `td` 只有登记在
//   `STRUCTURAL_CELL_PAIRS` 里的**精确**（文件 + 选择器）配对才可零 padding，并且必须
//   由内层容器消费间距令牌。
//
// 本模块刻意只看**已声明的** `th/td` 规则：某张表一条规则都没有（单元格几何全部继承
// `legacy.css`）时这里不会产生违规，那类表格由 Playwright 计算样式断言兜底（PLAN-DM-043
// Review Focus #5/#6）。
//
// 结构配对不写进 `ui-contract-exceptions.json`：例外条目字段被 `REQUIRED_EXCEPTION_FIELDS`
// 固定为「规则 + 文件 + 指纹 + 原因 + 到期条件」，无法承载「内层容器必须消费令牌」这一
// 条件。配对在此以常量表达，只在**命中** `file + selector` 时才去核对内层容器；配对本身
// 不产生陈旧判定（外层选择器不存在时它自然不匹配，不会把其它夹具拖红）。

import {maskNonCode, parseDeclarations, parseRules} from "./css-vars.mjs";
import {toPosition} from "./vue-source.mjs";
import {RULE} from "./types.mjs";

/** `vertical-align` 的允许取值（ARCH-DM-007 §4.3）。 */
export const ALLOWED_VERTICAL_ALIGN = Object.freeze(["middle", "top"]);

/**
 * 跨列结构单元格的精确配对：外层零 padding，内层容器消费间距令牌。
 *
 * `selector` / `innerSelector` 按「去掉注释与全部空白」后的规范形式比较（`.a > td` 与
 * `.a>td` 等价）；`requiredToken` 必须出现在内层容器 `padding` 声明里。
 */
export const STRUCTURAL_CELL_PAIRS = Object.freeze([
  {
    file: "src/components/SheetTable.vue",
    selector: ".sheet-editor-row>td",
    innerFile: "src/components/sheets/SheetPropertyEditor.vue",
    innerSelector: ".sheet-property-editor",
    requiredToken: "--space-4",
  },
]);

/** 参与单表单档与令牌化的 padding 家族（含逻辑属性）。 */
const PADDING_PROPERTY_PATTERN = /^padding(?:-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?)?$/i;
const ZERO_VALUE_PATTERN = /^0(?:px|rem|em|%)?$/i;
const PADDING_KEYWORD_PATTERN = /^(?:inherit|initial|unset|revert|revert-layer)$/i;

/** 选择器规范形式：抹掉注释与全部空白，用于精确比较（不做任何语义推断）。 */
export function normalizeSelector(selector) {
  return maskNonCode(selector).replace(/\s+/g, "");
}

/** 顶层逗号切分选择器列表（忽略 `()`/`[]` 内的逗号）。 */
function splitSelectorList(selector) {
  const parts = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < selector.length; i += 1) {
    const ch = selector[i];
    if (ch === "(" || ch === "[") depth += 1;
    else if (ch === ")" || ch === "]") depth = Math.max(0, depth - 1);
    else if (ch === "," && depth === 0) {
      parts.push(selector.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(selector.slice(start));
  return parts.map((part) => part.trim()).filter((part) => part !== "");
}

/** 选择器片段里最后一个复合选择器（按 `+ ~ >` 与空白等顶层组合符切分）。 */
function lastCompound(part) {
  const segments = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < part.length; i += 1) {
    const ch = part[i];
    if (ch === "(" || ch === "[") depth += 1;
    else if (ch === ")" || ch === "]") depth = Math.max(0, depth - 1);
    else if (depth === 0 && (ch === ">" || ch === "+" || ch === "~" || /\s/.test(ch))) {
      segments.push(part.slice(start, i));
      start = i + 1;
    }
  }
  segments.push(part.slice(start));
  return segments.map((segment) => segment.trim()).filter((segment) => segment !== "").pop() ?? "";
}

/**
 * 判定单个选择器片段是否直接命中单元格，并给出它所属的「表作用域」。
 *
 * 作用域用于「同表同档」比较：把最后一个复合选择器里的元素名摘掉（`td.col-default` →
 * `.col-default`、`.ordinary-table td` → `.ordinary-table`、`th,td` → 空），再加上前置
 * 组合部分。刻意不做语义推断：不同前缀（两张结构各异的表）视为不同作用域，不强行合并。
 */
function cellTarget(part) {
  const compound = lastCompound(part);
  const match = /^([A-Za-z][\w-]*)/.exec(compound);
  if (match === null) return null;
  const element = match[1].toLowerCase();
  if (element !== "th" && element !== "td") return null;
  const rest = compound.slice(match[1].length);
  const prefix = part.slice(0, part.length - compound.length).trim().replace(/\s+/g, " ");
  return {element, scope: `${prefix}${prefix !== "" && rest !== "" ? " " : ""}${rest}`.trim(), compound};
}

function isPaddingDeclaration(declaration) {
  return PADDING_PROPERTY_PATTERN.test(declaration.property.trim());
}

function isZeroValue(value) {
  return ZERO_VALUE_PATTERN.test(value.trim());
}

function consumesToken(value) {
  return /var\(/i.test(value);
}

function isKeywordValue(value) {
  return PADDING_KEYWORD_PATTERN.test(value.trim());
}

/**
 * 汇总表格单元格规则违规。
 *
 * `files` 是检查器的扫描结果：`{relative, text, sfc}`，`sfc` 为 `splitSfc` 结果或 `null`。
 * `emitFor(relative)` 由调用方提供按文件计数出现序号的 emit 工厂；本模块按文件缓存它，
 * 保证同一 (rule, semantic) 在同一文件下不会因为多段 `<style>` 而重号。
 */
export function collectTableCellViolations({files, emitFor, pairs = STRUCTURAL_CELL_PAIRS}) {
  const emitters = new Map();
  const emit = (spec) => {
    if (!emitters.has(spec.file)) emitters.set(spec.file, emitFor(spec.file));
    return emitters.get(spec.file)(spec);
  };

  const regions = [];
  for (const file of files) {
    const blocks = file.sfc ? file.sfc.styles : [{content: file.text, offset: 0}];
    for (const block of blocks) {
      regions.push({file: file.relative, text: file.text, content: block.content, offset: block.offset});
    }
  }

  // 精确选择器索引：跨文件核对结构配对的内层容器时需要按 (文件, 选择器) 反查规则。
  const rulesByKey = new Map();
  for (const region of regions) {
    for (const rule of parseRules(region.content)) {
      const key = `${region.file}|${normalizeSelector(rule.selector)}`;
      if (rulesByKey.has(key)) continue;
      rulesByKey.set(key, {region, rule, declarations: parseDeclarations(region.content, rule)});
    }
  }

  const pairKeys = new Set(pairs.map((pair) => `${pair.file}|${normalizeSelector(pair.selector)}`));
  const verifiedPairs = new Set();
  /** 每个 (文件, 作用域) 已登记的第一个 padding 档，用于「同表同档」比较。 */
  const paddingTier = new Map();
  const violations = [];

  const report = (region, index, rule, message, semantic) =>
    violations.push(
      emit({rule, file: region.file, ...toPosition(region.text, region.offset + index), message, semantic}),
    );

  for (const region of regions) {
    for (const rule of parseRules(region.content)) {
      const selector = maskNonCode(rule.selector).replace(/\s+/g, " ").trim();
      const targets = splitSelectorList(selector).map(cellTarget).filter((target) => target !== null);
      if (targets.length === 0) continue;

      const declarations = parseDeclarations(region.content, rule);
      const normalized = `${region.file}|${normalizeSelector(rule.selector)}`;
      const isStructuralPair = pairKeys.has(normalized);

      // —— 规则 1：显式 vertical-align（仅 middle/top）——
      const alignment = declarations.find((item) => item.property.trim().toLowerCase() === "vertical-align");
      if (alignment === undefined) {
        report(
          region,
          rule.selectorStart,
          RULE.tableCellVerticalAlign,
          `表格单元格规则必须显式声明 vertical-align（仅 ${ALLOWED_VERTICAL_ALIGN.join("/")}）：${selector}`,
          `missing:${selector}`,
        );
      } else {
        const value = alignment.value.trim().toLowerCase();
        if (!ALLOWED_VERTICAL_ALIGN.includes(value)) {
          report(
            region,
            alignment.start,
            RULE.tableCellVerticalAlign,
            `vertical-align 取值只允许 ${ALLOWED_VERTICAL_ALIGN.join("/")}，实际为 ${value}：${selector}`,
            `value:${selector}:${value}`,
          );
        }
      }

      // —— 规则 2：padding 令牌化、单档、零值与结构配对 ——
      const paddings = declarations.filter(isPaddingDeclaration);
      const zeroDeclarations = paddings.filter((item) => isZeroValue(item.value));
      const bareDeclarations = paddings.filter(
        (item) => !isZeroValue(item.value) && !consumesToken(item.value) && !isKeywordValue(item.value),
      );

      for (const declaration of bareDeclarations) {
        report(
          region,
          declaration.start,
          RULE.tableCellPadding,
          `表格单元格 padding 必须消费间距/组件令牌，禁止裸值：${selector} { ${declaration.property.trim()}: ${declaration.value} }`,
          `bare:${selector}:${declaration.property.trim()}:${declaration.value}`,
        );
      }

      if (zeroDeclarations.length > 0 && !isStructuralPair) {
        report(
          region,
          zeroDeclarations[0].start,
          RULE.tableCellPadding,
          `普通数据格不得取零 padding；结构性零 padding 必须以 STRUCTURAL_CELL_PAIRS 里登记的文件 + 具体选择器限定：${selector}`,
          `zero:${selector}`,
        );
      }

      if (isStructuralPair && zeroDeclarations.length > 0 && !verifiedPairs.has(normalized)) {
        verifiedPairs.add(normalized);
        const pair = pairs.find((item) => `${item.file}|${normalizeSelector(item.selector)}` === normalized);
        const inner = rulesByKey.get(`${pair.innerFile}|${normalizeSelector(pair.innerSelector)}`);
        const outer = {region, index: rule.selectorStart, selector};
        if (inner === undefined) {
          report(
            outer.region,
            outer.index,
            RULE.tableCellPadding,
            `结构配对的内层容器未找到：${pair.innerFile} 的 ${pair.innerSelector}（配对：${pair.selector}）`,
            `pair-inner-missing:${pair.selector}`,
          );
        } else {
          const innerPadding = inner.declarations.filter(isPaddingDeclaration);
          const token = `var(${pair.requiredToken})`;
          if (!innerPadding.some((item) => item.value.includes(token))) {
            const at = innerPadding[0]?.start ?? inner.rule.selectorStart;
            const actual = innerPadding.map((item) => item.value).join(" / ") || "未声明 padding";
            report(
              {file: pair.innerFile, text: inner.region.text, offset: inner.region.offset},
              at,
              RULE.tableCellPadding,
              `结构配对的内层容器必须消费间距令牌 ${token}，实际为 ${actual}（外层：${pair.file} 的 ${pair.selector}）`,
              `pair-token:${pair.selector}:${actual}`,
            );
          }
        }
      }

      // —— 规则 2 续：同一 (文件, 作用域) 的普通格只能有一个 padding 档 ——
      if (!isStructuralPair && zeroDeclarations.length === 0) {
        const shorthand = paddings.find((item) => item.property.trim().toLowerCase() === "padding");
        if (shorthand !== undefined) {
          for (const target of targets) {
            const key = `${region.file}|${target.scope}`;
            const value = shorthand.value.trim();
            const seen = paddingTier.get(key);
            if (seen === undefined) {
              paddingTier.set(key, {value, selector});
              continue;
            }
            if (seen.value !== value) {
              report(
                region,
                shorthand.start,
                RULE.tableCellPadding,
                `同一张表的普通单元格只能有一个 padding 档：${target.scope || "(组件根作用域)"} 已为 ${seen.value}（${seen.selector}），此处为 ${value}（${selector}）`,
                `mismatch:${target.scope}:${seen.value}:${value}`,
              );
            }
          }
        }
      }
    }
  }

  return violations;
}
