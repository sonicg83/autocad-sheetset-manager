// CSS grid 伪表格的行高、padding 与行轨道对齐规则（PLAN-DM-044 Task 2）。

import {parseDeclarations, parseRules} from "./css-vars.mjs";
import {normalizeSelector} from "./table-cells.mjs";
import {isTableRootElement, scanTemplateElements} from "./table-without-cell-contract.mjs";
import {toPosition} from "./vue-source.mjs";
import {RULE} from "./types.mjs";

const ROW_HEIGHT = "var(--sheet-table-row-height)";
const ALLOWED_PADDING = /^var\(--space-[12]\)$/;
const ALLOWED_ALIGN_ITEMS = new Set(["center", "start"]);

function selectorMatches(ruleSelector, targetSelector) {
  const rule = normalizeSelector(ruleSelector);
  const target = normalizeSelector(targetSelector);
  const ruleParts = rule.split(",");
  return rule === target || ruleParts.includes(target) || target.split(",").some(part => ruleParts.includes(part));
}

function cssRegions(file) {
  return file.sfc ? file.sfc.styles.map(style => ({...style, file})) : [{content: file.text, offset: 0, file}];
}

function declarationsFor(file, selector) {
  return cssRegions(file).flatMap(region => parseRules(region.content)
    .filter(rule => selectorMatches(rule.selector, selector))
    .flatMap(rule => parseDeclarations(region.content, rule).map(declaration => ({...declaration, region, rule}))));
}

function selectorStart(file, selector, fallback) {
  for (const region of cssRegions(file)) {
    const rule = parseRules(region.content).find(item => selectorMatches(item.selector, selector));
    if (rule !== undefined) return region.offset + rule.selectorStart;
  }
  return fallback;
}

function emitViolation(emitFor, sourceFile, relativeFile, index, rule, message, semantic) {
  return emitFor(relativeFile)({
    rule,
    file: relativeFile,
    ...toPosition(sourceFile.text, index),
    message,
    semantic,
  });
}

function declarationIndex(declarations, property) {
  return declarations.find(item => item.property.trim().toLowerCase() === property);
}

function report(violations, emitFor, contract, sourceFile, index, rule, message, semantic) {
  violations.push(emitViolation(emitFor, sourceFile, sourceFile.relative, index, rule, message, `${contract.marker}:${semantic}`));
}

/**
 * 检查登记的 grid 表头/数据行 CSS 声明。规则只判断静态声明，不计算浏览器布局。
 * `contracts` 由逐表 marker 清单传入；无 marker 的 class-only 伪表不在静态发现范围内。
 */
export function collectGridTableCellViolations({files, emitFor, contracts = []}) {
  const violations = [];
  const fileByPath = new Map(files.map(file => [file.relative, file]));

  for (const contract of contracts) {
    const component = fileByPath.get(contract.file);
    if (component === undefined) continue;
    const template = component.sfc?.template;
    if (template === null || template === undefined) continue;
    const registeredRootExists = scanTemplateElements(template.content).some(element =>
      isTableRootElement(element) && getLiteralMarker(element.text) === contract.marker,
    );
    if (!registeredRootExists) continue;
    const styleFile = fileByPath.get(contract.cssFile);
    const header = styleFile === undefined ? [] : declarationsFor(styleFile, contract.headerSelector);
    const row = styleFile === undefined ? [] : declarationsFor(styleFile, contract.rowSelector);
    const file = styleFile ?? component;
    const fallback = component.sfc.template?.offset ?? 0;
    const headIndex = styleFile === undefined ? fallback : selectorStart(styleFile, contract.headerSelector, fallback);
    const rowIndex = styleFile === undefined ? fallback : selectorStart(styleFile, contract.rowSelector, fallback);

    for (const [name, declarations, index] of [["表头", header, headIndex], ["数据行", row, rowIndex]]) {
      const rowHeight = declarationIndex(declarations, "height") ?? declarationIndex(declarations, "min-height");
      if (rowHeight === undefined || rowHeight.value.trim() !== ROW_HEIGHT) {
        report(violations, emitFor, contract, file, index, RULE.gridTableRowHeight,
          `${name}必须显式消费 ${ROW_HEIGHT} 行高档`, `${name}:row-height:${rowHeight?.value ?? "missing"}`);
      }

      const paddingDeclarations = declarations.filter(item => /^padding(?:-|$)/i.test(item.property.trim()));
      const padding = declarationIndex(declarations, "padding");
      if (padding === undefined || paddingDeclarations.length !== 1 || !ALLOWED_PADDING.test(padding.value.trim())) {
        const actual = paddingDeclarations.map(item => `${item.property}:${item.value}`).join(" / ") || "missing";
        report(violations, emitFor, contract, file, index, RULE.gridTablePadding,
          `${name}必须使用单档间距令牌 padding:var(--space-1/--space-2)，实际为 ${actual}`, `${name}:padding:${actual}`);
      }

      const align = declarationIndex(declarations, "align-items");
      if (align === undefined || !ALLOWED_ALIGN_ITEMS.has(align.value.trim().toLowerCase())) {
        report(violations, emitFor, contract, file, index, RULE.gridTableAlign,
          `${name}必须显式声明 align-items:center 或 start`, `${name}:align-items:${align?.value ?? "missing"}`);
      }
    }

    const headerPadding = declarationIndex(header, "padding")?.value.trim();
    const rowPadding = declarationIndex(row, "padding")?.value.trim();
    if (headerPadding !== undefined && rowPadding !== undefined && headerPadding !== rowPadding) {
      report(violations, emitFor, contract, file, rowIndex, RULE.gridTablePadding,
        `表头与数据行必须使用相同 padding 档：${headerPadding} / ${rowPadding}`, `padding-mismatch:${headerPadding}:${rowPadding}`);
    }
  }

  return violations;
}

function getLiteralMarker(tagText) {
  if (!/(?:^|\s)data-ui-table-contract\s*=/.test(tagText)) return null;
  const match = /\sdata-ui-table-contract\s*=\s*(["'])(.*?)\1/.exec(tagText);
  return match?.[2] ?? null;
}
