// CSS 结构与自定义属性解析原语（PLAN-DM-029 Task 1）。
//
// 本模块不做规则判定，只把 CSS 文本变成可定位的结构：
// - `maskNonCode` 把注释与字符串字面量的**内容**替换为等长空格，使所有位置偏移
//   仍然指向原文，从而让后续匹配不会被注释里的 `var()` 或中文文案干扰；
// - `parseRules` 按花括号平衡解析出规则块（含 `@media` 祖先链）；
// - `parseDeclarations` 解析块内声明，按顶层分号切分；
// - `findVarNodes` 用**平衡括号**解析 `var()`（禁止用单层正则处理带 fallback 的
//   嵌套调用），返回可递归遍历的引用树；
// - `findCircularVariables` 在自定义属性依赖图上检测循环引用。
//
// 供 `visual-values.mjs` 复用的选择器/声明信息也在这里产出，避免再引入额外模块。

/** 找到 [from, to) 内与 index 位置对应的顶层分隔符边界。 */
function isStringQuote(ch) {
  return ch === '"' || ch === "'";
}

/**
 * 把注释与字符串字面量内容替换为空格（保留长度与换行）。
 * 返回与原文等长的字符串，位置可直接回查原文。
 */
export function maskNonCode(css) {
  const out = css.split("");
  const blank = (from, to) => {
    for (let i = from; i < to; i += 1) {
      if (out[i] !== "\n") out[i] = " ";
    }
  };
  let i = 0;
  while (i < css.length) {
    if (css.startsWith("/*", i)) {
      const end = css.indexOf("*/", i + 2);
      const stop = end === -1 ? css.length : end + 2;
      blank(i, stop);
      i = stop;
      continue;
    }
    if (isStringQuote(css[i])) {
      const quote = css[i];
      let j = i + 1;
      while (j < css.length && css[j] !== quote) {
        if (css[j] === "\\") j += 1;
        j += 1;
      }
      const stop = Math.min(j + 1, css.length);
      // 保留起止引号，只清空内容，便于调用方判断“这里原本是字符串”。
      blank(i + 1, stop - 1);
      i = stop;
      continue;
    }
    i += 1;
  }
  return out.join("");
}

function collapseWhitespace(text) {
  return text.trim().replace(/\s+/g, " ");
}

/**
 * 解析样式规则块。
 *
 * @returns {{selector: string, atRules: string[], selectorStart: number, openIndex: number,
 *   contentStart: number, contentEnd: number}[]} 仅样式规则（`@media` 等条件块本身
 *   不作为规则返回，但会出现在其内部规则的 `atRules` 里）。
 */
export function parseRules(css) {
  const masked = maskNonCode(css);
  const rules = [];
  const stack = [];
  let segmentStart = 0;
  for (let i = 0; i < masked.length; i += 1) {
    const ch = masked[i];
    if (ch === "{") {
      const parent = stack[stack.length - 1];
      const entry = {
        selector: collapseWhitespace(css.slice(segmentStart, i)),
        atRules: parent ? [...parent.atRules, parent.selector] : [],
        selectorStart: segmentStart,
        openIndex: i,
        contentStart: i + 1,
        contentEnd: -1,
      };
      stack.push(entry);
      segmentStart = i + 1;
      continue;
    }
    if (ch === "}") {
      const entry = stack.pop();
      if (entry) {
        entry.contentEnd = i;
        if (!entry.selector.startsWith("@") && entry.selector !== "") rules.push(entry);
      }
      segmentStart = i + 1;
      continue;
    }
    if (ch === ";" && stack.length === 0) segmentStart = i + 1;
  }
  return rules;
}

/** 在一个 [from, to) 区间内按顶层分隔符切片。 */
function splitTopLevel(css, masked, from, to, separator) {
  const segments = [];
  let depth = 0;
  let start = from;
  for (let i = from; i < to; i += 1) {
    const ch = masked[i];
    if (ch === "(" || ch === "[") depth += 1;
    else if (ch === ")" || ch === "]") depth = Math.max(0, depth - 1);
    else if (ch === separator && depth === 0) {
      segments.push({from: start, to: i});
      start = i + 1;
    }
  }
  segments.push({from: start, to});
  return segments;
}

/** 解析规则块内的声明（按顶层分号切分）。 */
export function parseDeclarations(css, rule) {
  const masked = maskNonCode(css);
  const from = rule.contentStart;
  const to = rule.contentEnd === -1 ? css.length : rule.contentEnd;
  const declarations = [];
  const push = (start, end) => {
    const segments = splitTopLevel(css, masked, start, end, ":");
    if (segments.length < 2) return;
    const property = css.slice(segments[0].from, segments[0].to).trim();
    if (property === "" || property.startsWith("@")) return;
    const valueFrom = segments[1].from;
    const valueTo = segments[segments.length - 1].to;
    declarations.push({
      property,
      value: css.slice(valueFrom, valueTo).trim(),
      start: segments[0].from,
      valueStart: valueFrom,
      valueEnd: valueTo,
    });
  };
  for (const segment of splitTopLevel(css, masked, from, to, ";")) push(segment.from, segment.to);
  return declarations;
}

/** 收集全部自定义属性声明，附带所在规则。 */
export function collectCustomPropertyDeclarations(css) {
  const declarations = [];
  for (const rule of parseRules(css)) {
    for (const declaration of parseDeclarations(css, rule)) {
      if (declaration.property.startsWith("--")) {
        declarations.push({...declaration, name: declaration.property, rule});
      }
    }
  }
  return declarations;
}

/**
 * 用平衡括号解析 [from, to) 内的 `var()` 引用，返回递归引用树。
 *
 * 每个节点形如 `{name, start, end, hasFallback, fallbacks}`：`name` 是变量名（含
 * 前导 `--`），`fallbacks` 是 fallback 参数中出现的嵌套 var() 节点。fallback 中的
 * 字面量不需要展开——字面量本身总能解析，只有其中的 var() 引用需要继续校验。
 */
export function findVarNodes(css, from = 0, to = css.length) {
  const masked = maskNonCode(css);
  const nodes = [];
  for (let i = from; i < to - 3; i += 1) {
    if (masked.slice(i, i + 4).toLowerCase() !== "var(") continue;
    const node = parseVarNode(css, masked, i, to);
    if (node) {
      nodes.push(node);
      i = node.end - 1;
    }
  }
  return nodes;
}

function parseVarNode(css, masked, index, limit) {
  const openIndex = index + 3;
  let depth = 0;
  let close = -1;
  for (let i = openIndex; i < limit; i += 1) {
    const ch = masked[i];
    if (ch === "(") depth += 1;
    else if (ch === ")") {
      depth -= 1;
      if (depth === 0) {
        close = i;
        break;
      }
    }
  }
  if (close === -1) return null;
  // 只认最外层 var(--name...) 形态；`var(--x` 之后必须是变量名，避免把函数名
  // 片段（例如 "var(" 出现在字符串里）误当作引用。
  const segments = splitTopLevel(css, masked, openIndex + 1, close, ",");
  const name = css.slice(segments[0].from, segments[0].to).trim();
  if (!name.startsWith("--")) return null;
  const fallbacks = [];
  for (const segment of segments.slice(1)) {
    fallbacks.push(...findVarNodes(css, segment.from, segment.to));
  }
  return {name, start: index, end: close + 1, hasFallback: segments.length > 1, fallbacks};
}

/** 深度优先收集引用树中的全部节点。 */
export function flattenVarNodes(nodes) {
  const out = [];
  const visit = (node) => {
    out.push(node);
    for (const fallback of node.fallbacks) visit(fallback);
  };
  for (const node of nodes) visit(node);
  return out;
}

/**
 * 在同一文件的声明集合上检测循环引用（自定义属性依赖图）。
 *
 * 每个环只报一次：`names` 为环成员（按 DFS 发现顺序），`start` 为环内最早的声明
 * 位置，用于定位。逐成员重复报告会让一次根因产生多条噪声违规。
 *
 * @param {{name: string, value: string, start: number}[]} declarations
 * @returns {{names: string[], start: number}[]}
 */
export function findCircularVariables(declarations) {
  const graph = new Map();
  const sites = new Map();
  for (const declaration of declarations) {
    const targets = graph.get(declaration.name) ?? new Set();
    for (const node of flattenVarNodes(findVarNodes(declaration.value))) targets.add(node.name);
    graph.set(declaration.name, targets);
    if (!sites.has(declaration.name)) sites.set(declaration.name, declaration.start);
  }
  const cycles = [];
  const seen = new Set();
  const visiting = new Set();
  const done = new Set();
  const walk = (name, stack) => {
    if (done.has(name)) return;
    if (visiting.has(name)) {
      const from = stack.indexOf(name);
      const members = stack.slice(from === -1 ? 0 : from);
      const key = [...members].sort().join(",");
      if (!seen.has(key)) {
        seen.add(key);
        cycles.push({
          names: members,
          start: Math.min(...members.map((member) => sites.get(member) ?? 0)),
        });
      }
      return;
    }
    visiting.add(name);
    stack.push(name);
    for (const target of graph.get(name) ?? []) walk(target, stack);
    stack.pop();
    visiting.delete(name);
    done.add(name);
  };
  for (const name of graph.keys()) walk(name, []);
  return cycles;
}
