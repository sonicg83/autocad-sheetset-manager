// 视觉值与选择器规则原语（PLAN-DM-029 Task 1）。
//
// 覆盖三类静态可判定的视觉债务：
// - 未登记的十六进制颜色；
// - 未使用令牌的裸字号、裸高度与裸圆角；
// - 业务代码里不带根类限定的裸全局选择器。
//
// 范围说明（有意收窄，避免规则退化成噪声）：
// - `raw-visual-value` 只覆盖 ARCH-DM-007 §4.1 点名的四类原始值（字号、高度、圆角）
//   及其等宽行高；`padding`/`margin`/`gap` 等间距属性与纯粹的内容驱动宽度不属于本
//   规则，间距令牌迁移由各页面任务按布局证据处理。
// - `raw-hex-color` 与 `raw-visual-value` 都跳过令牌定义块（`:root` 与 `html[...]`），
//   因为令牌文件正是十六进制色与原始档位的合法定义处。
// - `global-selector-in-component` 只作用于「组件里非 scoped 的 `<style>` 块」与全局
//   业务样式表；Vue scoped 样式按 ARCH-DM-007 §7 是页面覆盖全局默认值的明确前提，
//   其中的元素选择器不属于裸全局选择器。

import {maskNonCode} from "./css-vars.mjs";

/** 需要令牌化的视觉属性。 */
export const RAW_VISUAL_PROPERTIES = Object.freeze([
  "font-size",
  "line-height",
  "height",
  "min-height",
  "max-height",
  "border-radius",
]);

/** 允许直接书写的值（关键字、内容驱动比例、函数计算等）。 */
const ALLOWED_VALUE_PATTERN =
  /^(inherit|initial|unset|revert|revert-layer|auto|none|fit-content|min-content|max-content|transparent|currentcolor|solid|dashed)$/i;
const COMPUTED_VALUE_PATTERN = /(var\(|calc\(|min\(|max\(|clamp\(|env\()/i;
const TOKENIZED_UNITS = /^-?\d*\.?\d+(px|rem|em)$/i;

/** 令牌定义块（十六进制色与原始档位的合法定义处）。 */
export function isTokenBlock(selector) {
  return selector
    .split(",")
    .map((part) => part.trim())
    .some((part) => part === ":root" || /^html(\[|$|\s)/.test(part));
}

/** 判断一条声明是否是「裸视觉值」。 */
export function isRawVisualValue(declaration) {
  if (!RAW_VISUAL_PROPERTIES.includes(declaration.property)) return false;
  const value = declaration.value.trim().toLowerCase();
  if (value === "" || ALLOWED_VALUE_PATTERN.test(value)) return false;
  if (COMPUTED_VALUE_PATTERN.test(value)) return false;
  if (value.endsWith("%")) return false;
  if (/^0(px|rem|em)?$/.test(value)) return false;
  return TOKENIZED_UNITS.test(value);
}

/** 判断一个值里是否写了十六进制颜色。
 *
 * 只屏蔽 `url(...)`（其中的 `#id` 是片段引用，不是颜色）；不跳过含 `var()` 的值，
 * 因为 fallback 里的裸色同样是业务组件里的未登记颜色。
 */
export function findHexColorsInValue(value) {
  const masked = maskNonCode(value).replace(/url\([^)]*\)/gi, (match) => " ".repeat(match.length));
  const colors = [];
  for (const match of masked.matchAll(/#[0-9a-f]{3,8}\b/gi)) colors.push(match[0]);
  return colors;
}

/** 去掉选择器的伪类/伪元素，取最左复合选择器的起始简单选择器。 */
function firstSimpleSelectors(selector) {
  const masked = maskNonCode(selector);
  let depth = 0;
  let compoundEnd = masked.length;
  for (let i = 0; i < masked.length; i += 1) {
    const ch = masked[i];
    if (ch === "(" || ch === "[") depth += 1;
    else if (ch === ")" || ch === "]") depth = Math.max(0, depth - 1);
    else if (depth === 0 && (ch === ">" || ch === "+" || ch === "~" || ch === " ")) {
      compoundEnd = i;
      break;
    }
  }
  const compound = masked.slice(0, compoundEnd);
  const simples = [];
  let i = 0;
  while (i < compound.length) {
    const ch = compound[i];
    if (ch === ":") {
      const name = /^:[:a-z-]+/i.exec(compound.slice(i))?.[0] ?? ":";
      simples.push(name === "::" ? "pseudo-element" : `pseudo:${name}`);
      i += name.length;
      while (compound[i] === "(") {
        let depth2 = 0;
        const start = i;
        for (; i < compound.length; i += 1) {
          if (compound[i] === "(") depth2 += 1;
          else if (compound[i] === ")") {
            depth2 -= 1;
            if (depth2 === 0) {
              i += 1;
              break;
            }
          }
        }
        simples.push(`args:${compound.slice(start, i)}`);
      }
      continue;
    }
    const token = /^[#.]?[A-Za-z0-9_-]+/.exec(compound.slice(i))?.[0] ?? compound[i];
    if (token.startsWith(".")) simples.push("class");
    else if (token.startsWith("#")) simples.push("id");
    else if (token === "*") simples.push("universal");
    else simples.push("type");
    i += token.length;
  }
  return simples;
}

/** 按顶层逗号切分选择器列表（括号内的逗号不算分隔）。 */
function splitSelectorList(selector) {
  const masked = maskNonCode(selector);
  const parts = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < masked.length; i += 1) {
    const ch = masked[i];
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

/** 判断单个选择器是否是裸全局选择器。 */
function isBareCompoundRoot(selector) {
  const simples = firstSimpleSelectors(selector);
  if (simples.length === 0) return false;
  const [first] = simples;
  if (first === "class" || first === "id") return false;
  // `:where(...)` / `:is(...)` 是明确的收窄作用域包装，其内部自带限定条件。
  if (simples.some((simple) => simple === "pseudo::where" || simple === "pseudo::is")) return false;
  return first === "type" || first === "universal" || first.startsWith("pseudo");
}

/** 判断选择器列表是否含裸全局选择器（选择器列表逐段判定）。 */
export function isBareGlobalSelector(selector) {
  return splitSelectorList(selector).some(isBareCompoundRoot);
}
