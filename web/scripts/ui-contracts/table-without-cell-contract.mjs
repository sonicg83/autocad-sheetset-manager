// 按表根核对稳定锚点与单元格几何规则（PLAN-DM-044 Task 2）。

import {parseDeclarations, parseRules} from "./css-vars.mjs";
import {normalizeSelector} from "./table-cells.mjs";
import {getAttribute, toPosition} from "./vue-source.mjs";
import {RULE} from "./types.mjs";

function htmlTable(file, marker, selector) {
  return {file, marker, headerSelector: selector, rowSelector: selector, cssFile: file};
}

function gridTable(file, marker, headerSelector, rowSelector) {
  return {file, marker, headerSelector, rowSelector, cssFile: file};
}

const PREVIEW_FILE = "src/components/PreviewPanel.vue";
const PREVIEW_SELECTOR = ".preview th,.preview td";
const JOB_FILE = "src/components/JobStatusPanel.vue";
const JOB_SELECTOR = ".job-detail th,.job-detail td";

/** 每个真实表根单独登记；多张表可明确共用同一组单元格样式。 */
export const TABLE_CONTRACTS = Object.freeze([
  ...[
    "preview-sheetset-diff",
    "preview-structure",
    "preview-properties-diff",
    "preview-dwgs-diff",
    "preview-subset-operations",
    "preview-source-baselines",
    "preview-number-range",
    "preview-execution-layouts",
  ].map(marker => htmlTable(PREVIEW_FILE, marker, PREVIEW_SELECTOR)),
  htmlTable(JOB_FILE, "job-files", JOB_SELECTOR),
  htmlTable("src/components/properties/PropertyDefinitionTable.vue", "property-definitions", "th,td"),
  htmlTable("src/components/RevisionHistoryPanel.vue", "revision-history", ".panel th,.panel td"),
  htmlTable("src/components/SheetTable.vue", "sheet-browser", "th,td"),
  htmlTable("src/components/standards/AssetInspectionPanel.vue", "asset-layouts", ".layout-table th,.layout-table td"),
  htmlTable("src/components/creation/SheetValuesDialog.vue", "sheet-values", ".values-table th,.values-table td"),
  htmlTable("src/components/creation/GroupsStep.vue", "groups", ".group-table th,.group-table td"),
  htmlTable("src/components/creation/ReviewStep.vue", "creation-review", ".preview-table th,.preview-table td"),
  htmlTable("src/components/sheet-catalog/CatalogPreview.vue", "catalog-preview", ".table-window th,.table-window td"),
  htmlTable("src/components/standards/OrdinaryPropertyEditor.vue", "ordinary-properties", ".ordinary-table th,.ordinary-table td"),
  gridTable("src/components/standards/EnumValuesDialog.vue", "enum-values", ".enum-head", ".enum-row"),
  gridTable("src/components/standards/MappingPropertyDialog.vue", "mapping-values", ".mapping-head", ".mapping-row"),
  gridTable("src/components/standards/DerivedPropertyEditor.vue", "derived-properties", ".derived-head", ".derived-row"),
]);

/** 几何配对在 Task 3/4 加入 TABLE_CONTRACTS 时启用逐表根守卫。 */
export const GRID_TABLE_CONTRACTS = Object.freeze([
  gridTable("src/components/standards/EnumValuesDialog.vue", "enum-values", ".enum-head", ".enum-row"),
  gridTable("src/components/standards/MappingPropertyDialog.vue", "mapping-values", ".mapping-head", ".mapping-row"),
  gridTable("src/components/standards/DerivedPropertyEditor.vue", "derived-properties", ".derived-head", ".derived-row"),
  gridTable("src/components/sheet-catalog/ColumnEditor.vue", "catalog-columns", ".columns-head", ".column-row"),
]);

const VOID_ELEMENTS = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"]);

function findTagEnd(html, start) {
  let quote = null;
  for (let index = start; index < html.length; index += 1) {
    const character = html[index];
    if (quote !== null) {
      if (character === quote) quote = null;
    } else if (character === "\"" || character === "'") {
      quote = character;
    } else if (character === ">") {
      return index;
    }
  }
  return -1;
}

/** 仅解析 template 标签边界与祖先关系，不求值 Vue 表达式。 */
export function scanTemplateElements(html) {
  const elements = [];
  const stack = [];
  let index = 0;
  while (index < html.length) {
    const start = html.indexOf("<", index);
    if (start === -1) break;
    if (html.startsWith("<!--", start)) {
      const end = html.indexOf("-->", start + 4);
      index = end === -1 ? html.length : end + 3;
      continue;
    }
    const end = findTagEnd(html, start + 1);
    if (end === -1) break;
    const text = html.slice(start, end + 1);
    const closing = /^<\s*\//.test(text);
    const nameMatch = /^<\s*\/?\s*([A-Za-z][\w.-]*)/.exec(text);
    index = end + 1;
    if (nameMatch === null) continue;
    const tagName = nameMatch[1].toLowerCase();
    if (closing) {
      for (let stackIndex = stack.length - 1; stackIndex >= 0; stackIndex -= 1) {
        if (stack[stackIndex].tagName !== tagName) continue;
        stack[stackIndex].closeStart = start;
        stack[stackIndex].end = index;
        stack.length = stackIndex;
        break;
      }
      continue;
    }
    const element = {
      tagName,
      start,
      openEnd: index,
      end: html.length,
      text,
      ancestors: [...stack],
    };
    elements.push(element);
    if (!/\/\s*>$/.test(text) && !VOID_ELEMENTS.has(tagName)) stack.push(element);
  }
  return elements;
}

function selectorMatches(ruleSelector, targetSelector) {
  const rule = normalizeSelector(ruleSelector);
  const target = normalizeSelector(targetSelector);
  const ruleParts = rule.split(",");
  return rule === target || ruleParts.includes(target) || target.split(",").some(part => ruleParts.includes(part));
}

function regionsFor(file) {
  return file.sfc ? file.sfc.styles.map(style => ({...style, file})) : [{content: file.text, offset: 0, file}];
}

export function isTableRootElement(element) {
  return element.tagName === "table" || getAttribute(element.text, "role") === "table";
}

function hasLiteralMarker(element) {
  return /(?:^|\s)data-ui-table-contract\s*=/.test(element.text);
}

function report({file, index, semantic, message, emit, violations}) {
  violations.push(emit({
    rule: RULE.tableWithoutCellContract,
    file: file.relative,
    ...toPosition(file.text, index),
    message,
    semantic,
  }));
}

function findRulesForSelector(file, selector) {
  return regionsFor(file).flatMap(region => parseRules(region.content)
    .filter(rule => selectorMatches(rule.selector, selector))
    .map(rule => ({region, rule, declarations: parseDeclarations(region.content, rule)})));
}

function checkSelectorGeometry(contract, selector, isGrid, fileByPath) {
  const styleFile = fileByPath.get(contract.cssFile);
  if (styleFile === undefined) return [`样式文件不存在：${contract.cssFile}`];
  const rules = findRulesForSelector(styleFile, selector);
  if (rules.length === 0) return [`找不到已登记的 CSS 选择器：${selector}`];
  const declarations = rules.flatMap(item => item.declarations);
  if (declarations.length === 0) return [`已登记的 CSS 选择器没有声明：${selector}`];
  const properties = new Set(declarations.map(item => item.property.toLowerCase()));
  const missing = [];
  if (!properties.has("height") && !properties.has("min-height")) missing.push("height/min-height");
  if (!properties.has("padding")) missing.push("padding");
  const alignment = isGrid ? "align-items" : "vertical-align";
  if (!properties.has(alignment)) missing.push(alignment);
  return missing.length === 0 ? [] : [`${selector} 缺少 ${missing.join("、")} 声明`];
}

/**
 * 按表根核对 marker、登记配对、CSS 几何声明和孤立 row 角色。
 * `contracts`/`gridContracts` 可由单元测试注入；生产默认逐表登记位于模块常量中。
 */
export function collectTableWithoutCellContractViolations({files, emitFor, contracts = TABLE_CONTRACTS, gridContracts = GRID_TABLE_CONTRACTS}) {
  const violations = [];
  const fileByPath = new Map(files.map(file => [file.relative, file]));
  const contractByKey = new Map(contracts.map(contract => [`${contract.file}|${contract.marker}`, contract]));
  const gridKeys = new Set(gridContracts.map(contract => `${contract.file}|${contract.marker}`));
  const emitters = new Map();
  const emit = file => spec => {
    if (!emitters.has(file.relative)) emitters.set(file.relative, emitFor(file.relative));
    return emitters.get(file.relative)(spec);
  };
  const actualMarkers = new Map();

  for (const file of files) {
    if (file.sfc?.template === null || file.sfc === null) continue;
    const template = file.sfc.template;
    const elements = scanTemplateElements(template.content);
    const roots = elements.filter(isTableRootElement);
    const rootsByMarker = new Map();
    const markedElements = elements.filter(element => getAttribute(element.text, "data-ui-table-contract") !== null);

    for (const element of markedElements) {
      if (!isTableRootElement(element)) {
        report({file, index: template.offset + element.start, semantic: `marker-not-table-root:${getAttribute(element.text, "data-ui-table-contract")}`, message: "data-ui-table-contract 只能标在 <table> 或 role=table 根上", emit: emit(file), violations});
      }
    }

    for (const root of roots) {
      const marker = getAttribute(root.text, "data-ui-table-contract");
      const key = marker === null ? null : `${file.relative}|${marker}`;
      if (marker === null || !hasLiteralMarker(root)) {
        report({file, index: template.offset + root.start, semantic: `missing-marker:${root.tagName}:${marker ?? "none"}`, message: "每个 <table>/role=table 根都必须带唯一的字面量 data-ui-table-contract", emit: emit(file), violations});
        continue;
      }
      const sameFile = rootsByMarker.get(marker) ?? [];
      sameFile.push(root);
      rootsByMarker.set(marker, sameFile);
      if (!contractByKey.has(key)) {
        report({file, index: template.offset + root.start, semantic: `unregistered-marker:${marker}`, message: `表格 marker 未登记到 TABLE_CONTRACTS：${marker}`, emit: emit(file), violations});
      }
    }

    for (const [marker, markerRoots] of rootsByMarker) {
      if (markerRoots.length > 1) {
        report({file, index: template.offset + markerRoots[1].start, semantic: `duplicate-marker:${marker}`, message: `同一文件内表格 marker 重复：${marker}`, emit: emit(file), violations});
      }
      actualMarkers.set(`${file.relative}|${marker}`, markerRoots[0]);
    }

    for (const contract of contracts.filter(item => item.file === file.relative)) {
      const root = actualMarkers.get(`${contract.file}|${contract.marker}`);
      if (root === undefined) {
        report({file, index: template.offset, semantic: `registered-root-missing:${contract.marker}`, message: `登记的表格根未找到：${contract.marker}`, emit: emit(file), violations});
        continue;
      }
      const isGrid = gridKeys.has(`${contract.file}|${contract.marker}`);
      const geometryIssues = [contract.headerSelector, contract.rowSelector]
        .flatMap(selector => checkSelectorGeometry(contract, selector, isGrid, fileByPath));
      if (geometryIssues.length > 0) {
        report({file, index: template.offset + root.start, semantic: `geometry:${contract.marker}:${geometryIssues.join(";")}`, message: `表格 ${contract.marker} 的 CSS 契约不完整：${geometryIssues.join("；")}`, emit: emit(file), violations});
      }
    }

    for (const row of elements.filter(element => getAttribute(element.text, "role") === "row")) {
      const hasContainer = row.ancestors.some(ancestor =>
        isTableRootElement(ancestor) || getAttribute(ancestor.text, "role") === "rowgroup",
      );
      if (!hasContainer) {
        report({file, index: template.offset + row.start, semantic: "orphan-role-row", message: "role=row 必须位于 role=table、原生 table 或 role=rowgroup 内", emit: emit(file), violations});
      }
    }
  }

  return violations;
}
