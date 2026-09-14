// Vue 单文件组件的源码定位原语（PLAN-DM-029 Task 1）。
//
// 检查器必须能分别对待 `<template>`、`<style>` 与 `<script>`：样式块交给 CSS 解析器、
// 模板需要标签与属性级定位、脚本与模板里的 `var()` 归属同一个消费方文件。因此这里
// 只做「把文本切成带偏移的区块」和「在区块内定位元素」两件事，不做任何规则判定。

const BLOCK_TAG_PATTERN = /<(\/?)(template|style|script)(\s[^>]*)?>/gi;

/**
 * 切分单文件组件。
 *
 * 用标签栈而不是惰性正则匹配块边界：模板里存在嵌套 `<template v-if>` / `<template #slot>`，
 * 惰性正则会停在第一个内层 `</template>`，导致后半段模板完全不被检查。
 *
 * @returns {{template: {content: string, offset: number} | null,
 *   styles: {content: string, offset: number, scoped: boolean}[],
 *   scripts: {content: string, offset: number}[]}}
 */
export function splitSfc(text) {
  const result = {template: null, styles: [], scripts: []};
  const stack = [];
  BLOCK_TAG_PATTERN.lastIndex = 0;
  let match;
  while ((match = BLOCK_TAG_PATTERN.exec(text)) !== null) {
    const closing = match[1] === "/";
    const tag = match[2].toLowerCase();
    if (!closing) {
      stack.push({
        tag,
        attributes: match[3] ?? "",
        offset: match.index + match[0].length,
        outermost: stack.length === 0,
      });
      continue;
    }
    const open = stack.pop();
    if (!open || open.tag !== tag) continue;
    const content = text.slice(open.offset, match.index);
    if (tag === "style") {
      result.styles.push({content, offset: open.offset, scoped: /\bscoped\b/.test(open.attributes)});
    } else if (tag === "script") {
      result.scripts.push({content, offset: open.offset});
    } else if (open.outermost && result.template === null) {
      result.template = {content, offset: open.offset};
    }
  }
  return result;
}

/** 把绝对字符下标换算成 1 基的行列号。 */
export function toPosition(text, index) {
  const safeIndex = Math.max(0, Math.min(index, text.length));
  const before = text.slice(0, safeIndex);
  const line = before.split("\n").length;
  const lastBreak = before.lastIndexOf("\n");
  return {line, column: safeIndex - lastBreak};
}

/** 找到标签的结束 `>`；属性值里的 `>`（如 `:disabled="count>=1"`）不算结束。 */
function findTagEnd(html, from) {
  let quote = null;
  for (let i = from; i < html.length; i += 1) {
    const ch = html[i];
    if (quote !== null) {
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      continue;
    }
    if (ch === ">") return i;
  }
  return -1;
}

/** 找出元素的开标签（忽略注释内的伪标签）。 */
export function findTags(html, tagName) {
  const tags = [];
  const pattern = new RegExp(`<${tagName}\\b`, "gi");
  let match;
  while ((match = pattern.exec(html)) !== null) {
    if (html.slice(Math.max(0, match.index - 4), match.index).includes("<!--")) continue;
    const end = findTagEnd(html, match.index);
    if (end === -1) continue;
    tags.push({start: match.index, openEnd: end + 1, text: html.slice(match.index, end + 1)});
  }
  return tags;
}

/** 找出含内容的元素范围（用于 label 包裹判定）。 */
export function findRanges(html, tagName) {
  const ranges = [];
  const closer = `</${tagName}>`;
  for (const tag of findTags(html, tagName)) {
    const closeIndex = html.indexOf(closer, tag.openEnd);
    if (closeIndex === -1) continue;
    ranges.push({start: tag.start, end: closeIndex + closer.length, contentStart: tag.openEnd, contentEnd: closeIndex});
  }
  return ranges;
}

/** 判断标签是否声明了某属性（同时接受 `x`、`:x`、`v-bind:x` 三种写法）。 */
export function hasAttribute(tagText, name) {
  const pattern = new RegExp(`\\s(?::|v-bind:)?${escapeForRegExp(name)}\\s*=`);
  return pattern.test(tagText);
}

/** 读取属性值（去掉引号）；未声明时返回 null。 */
export function getAttribute(tagText, name) {
  const pattern = new RegExp(`\\s(?::|v-bind:)?${escapeForRegExp(name)}\\s*=\\s*("([^"]*)"|'([^']*)')`);
  const match = pattern.exec(tagText);
  if (!match) return null;
  return match[2] ?? match[3] ?? "";
}

/** 取元素内联内容（到该元素自己的闭合标签为止，不被内层标签截断）。 */
export function innerContent(html, tag, tagName) {
  const closeIndex = html.indexOf(`</${tagName}>`, tag.openEnd);
  if (closeIndex === -1) return "";
  return html.slice(tag.openEnd, closeIndex);
}

/** 是否含可见文字（去掉标签、注释与实体后仍有内容；`{{ ... }}` 插值算可见）。 */
export function hasVisibleText(html) {
  const stripped = html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&[a-z#0-9]+;/gi, " ");
  return /[^\s\u00a0]/.test(stripped);
}

/** 元素的稳定文本签名，用作违规指纹里的语义（去掉标签、折叠空白）。 */
export function textSignature(html) {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 60);
}

function escapeForRegExp(value) {
  return value.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
}
