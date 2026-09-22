// 标准草稿编辑模型（PLAN-DM-035 Task 9 / SPEC-DM-016 §6–§7）：纯函数视图模型，
// 无 Vue 与网络依赖。职责边界：
// - 把标准文档规范化为可编辑数组（保留未知顶层字段，不丢数据）；
// - 映射表的批量粘贴解析与行级诊断（重复源值/空单元格/非法目标值/枚举未覆盖）；
// - 字段组合与 DWG 命名的**纯展示**预览（不复制后端最终求值：真实求值仍由
//   `domain/standard_rules.evaluate_fields` 在宿主侧完成）；
// - 结构诊断（未知引用/重复目标/非法格式码/循环）——与后端 `compile_standard_rules`
//   使用**同一组稳定错误码**，作为保存前的就地提示；权威校验仍在后端，保存返回的
//   422 诊断按同码渲染，前端不重复实现字段求值。
// 本模块不持有用户可见文案：只返回稳定码与结构化参数，由视图经语言包渲染。
import type {StandardSummary} from "./types";

export type DraftScope = "sheetset" | "sheet" | "subset" | "derived";

export const FIELD_SCOPES: DraftScope[] = ["sheetset", "sheet", "subset", "derived"];

/** 首版预留作用域：只显示说明，不进入强制校验（PLAN-DM-035 Global Constraints）。 */
export const RESERVED_FIELD_SCOPES: DraftScope[] = ["subset"];

export type DraftRuleKind = "required" | "enum" | "fixed" | "mapping" | "compose" | "numbering" | "naming";

export const RULE_KINDS: DraftRuleKind[] = ["required", "enum", "fixed", "mapping", "compose", "numbering", "naming"];

/** 普通规则分区（SPEC-DM-016 §7.1）负责的规则种类；映射与组合各自独立分区。 */
export const ORDINARY_RULE_KINDS: DraftRuleKind[] = ["required", "enum", "fixed"];

/** 字段组合与 DWG 命名分区（SPEC-DM-016 §7.3）负责的规则种类。 */
export const COMPOSITION_RULE_KINDS: DraftRuleKind[] = ["compose", "naming"];

export type DraftAssetKind = "base-template" | "layout-template";

export const ASSET_KINDS: DraftAssetKind[] = ["base-template", "layout-template"];

/** 宿主登记的数字补零格式：1–2 位十进制数，宽度上限 12（与后端同一口径）。 */
export const PAD_FORMAT_PATTERN = /^\d{1,2}$/;
export const MAX_PAD_WIDTH = 12;

export interface DraftProperty {
  name: string;
  scope: string;
  required: boolean;
  default_value: string;
  enum_values: string[];
  description: string;
}

/** 片段只能是字段令牌、固定文本或受控序号令牌（可带补零格式码）。 */
export interface DraftSegment {
  field?: string;
  literal?: string;
  format?: string;
}

export interface DraftRule {
  rule_id: string;
  kind: DraftRuleKind;
  target: string;
  source?: string;
  value?: string;
  allowed: string[];
  table: Array<[string, string]>;
  segments: DraftSegment[];
}

export interface DraftAssetFile {
  path: string;
  role: string;
}

export interface DraftAsset {
  asset_id: string;
  kind: string;
  files: DraftAssetFile[];
}

export interface DraftNumbering {
  sequence_field: string;
  digits: number;
  start: number;
}

export interface DraftDependency {
  extension_id: string;
  capability_id: string;
  min_version: string;
}

/**
 * 可编辑标准文档：已知字段被规范化为强类型数组，未知顶层字段按原值保留
 * （受控流程不得丢弃未知节点，保存时原样写回）。
 */
export interface DraftDocument {
  schema_version: number;
  standard_id: string;
  version: string;
  name: string;
  supported_cad_versions: string[];
  properties: DraftProperty[];
  rules: DraftRule[];
  assets: DraftAsset[];
  numbering: DraftNumbering;
  dependencies: DraftDependency[];
  [key: string]: unknown;
}

export const DEFAULT_NUMBERING: DraftNumbering = {sequence_field: "subset.sequence", digits: 2, start: 1};

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asInt(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isInteger(value) ? value : fallback;
}

function normalizeSegment(raw: unknown): DraftSegment {
  const source = asRecord(raw);
  const segment: DraftSegment = {};
  if (typeof source.field === "string") segment.field = source.field;
  else if (typeof source.literal === "string") segment.literal = source.literal;
  if (typeof source.format === "string") segment.format = source.format;
  return segment;
}

function normalizeRule(raw: unknown): DraftRule {
  const source = asRecord(raw);
  return {
    rule_id: asString(source.rule_id),
    kind: asString(source.kind, "required") as DraftRuleKind,
    target: asString(source.target),
    source: typeof source.source === "string" ? source.source : undefined,
    value: typeof source.value === "string" ? source.value : undefined,
    allowed: asStringArray(source.allowed),
    table: (Array.isArray(source.table) ? source.table : [])
      .filter((row): row is unknown[] => Array.isArray(row) && row.length === 2)
      .map(row => [asString(row[0]), asString(row[1])] as [string, string]),
    segments: (Array.isArray(source.segments) ? source.segments : []).map(normalizeSegment),
  };
}

function normalizeAsset(raw: unknown): DraftAsset {
  const source = asRecord(raw);
  return {
    asset_id: asString(source.asset_id),
    kind: asString(source.kind, "base-template"),
    files: (Array.isArray(source.files) ? source.files : []).map(item => {
      const file = asRecord(item);
      return {path: asString(file.path), role: asString(file.role)};
    }),
  };
}

/** 把后端返回的原始标准文档规范化为可编辑文档。 */
export function toDraftDocument(document: Record<string, unknown>): DraftDocument {
  const numbering = asRecord(document.numbering);
  return {
    ...document,
    schema_version: asInt(document.schema_version, 1),
    standard_id: asString(document.standard_id),
    version: asString(document.version),
    name: asString(document.name),
    supported_cad_versions: asStringArray(document.supported_cad_versions),
    properties: (Array.isArray(document.properties) ? document.properties : []).map(item => {
      const property = asRecord(item);
      return {
        name: asString(property.name),
        scope: asString(property.scope, "sheetset"),
        required: property.required === true,
        default_value: asString(property.default_value),
        enum_values: asStringArray(property.enum_values),
        description: asString(property.description),
      };
    }),
    rules: (Array.isArray(document.rules) ? document.rules : []).map(normalizeRule),
    assets: (Array.isArray(document.assets) ? document.assets : []).map(normalizeAsset),
    numbering: {
      sequence_field: asString(numbering.sequence_field, DEFAULT_NUMBERING.sequence_field),
      digits: asInt(numbering.digits, DEFAULT_NUMBERING.digits),
      start: asInt(numbering.start, DEFAULT_NUMBERING.start),
    },
    dependencies: (Array.isArray(document.dependencies) ? document.dependencies : []).map(item => {
      const dependency = asRecord(item);
      return {
        extension_id: asString(dependency.extension_id),
        capability_id: asString(dependency.capability_id),
        min_version: asString(dependency.min_version),
      };
    }),
  };
}

/** 深拷贝草稿文档：编辑缓冲与可信基准必须互不引用。 */
export function cloneDocument(document: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(document)) as Record<string, unknown>;
}

export function isReservedScope(scope: string): boolean {
  return RESERVED_FIELD_SCOPES.includes(scope as DraftScope);
}

/** 属性/派生字段的完整引用（`scope.name`）。 */
export function fieldReference(property: Pick<DraftProperty, "name" | "scope">): string {
  return `${property.scope}.${property.name}`;
}

// ---------------------------------------------------------------- 映射表

export interface MappingRow {
  source: string;
  target: string;
}

/**
 * 解析映射表批量粘贴内容：制表符优先，否则按逗号切分；跳过空行、裁剪单元格。
 * 半填行被保留，交由 `validateMapping` 定位空单元格，不在解析期静默丢弃。
 */
export function buildMappingRows(text: string): MappingRow[] {
  const rows: MappingRow[] = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const cells = (line.includes("\t") ? line.split("\t") : line.split(",")).map(cell => cell.trim());
    rows.push({source: cells[0] ?? "", target: cells[1] ?? ""});
  }
  return rows;
}

export type MappingDiagnosticCode =
  | "STANDARD_MAPPING_SOURCE_DUPLICATE"
  | "STANDARD_MAPPING_SOURCE_UNCOVERED"
  | "STANDARD_MAPPING_EMPTY_CELL"
  | "STANDARD_MAPPING_TARGET_INVALID";

export interface MappingDiagnostic {
  code: MappingDiagnosticCode;
  /** 1 起始的数据行号；未覆盖项不对应具体行，为 null。 */
  row: number | null;
  source: string;
  value?: string;
}

export interface MappingTargetRule {
  /** 目标字段自身约束：非空表示受控枚举，目标值必须落在集合内。 */
  allowed: string[];
}

export function mappingRowsToTable(rows: MappingRow[]): Array<[string, string]> {
  return rows.map(row => [row.source, row.target] as [string, string]);
}

export function tableToMappingRows(table: Array<[string, string]>): MappingRow[] {
  return table.map(([source, target]) => ({source, target}));
}

/**
 * 行级映射诊断：每行最多一条（空单元格 → 重复源值 → 非法目标值），
 * 再按源域列出未被覆盖的值。源域为空表示不做覆盖检查。
 */
export function validateMapping(
  rows: MappingRow[],
  sourceDomain: string[],
  targetRule: MappingTargetRule,
): MappingDiagnostic[] {
  const diagnostics: MappingDiagnostic[] = [];
  const seen = new Map<string, number>();
  rows.forEach((row, index) => {
    const rowNumber = index + 1;
    // 重复判定先于空值判定：同源值第二次出现必须定位到行号
    const duplicate = row.source !== "" && seen.has(row.source);
    // 覆盖判定只看源值：整行存在但目标为空时不再额外报「未覆盖」（避免双报同因）
    if (row.source !== "" && !seen.has(row.source)) seen.set(row.source, rowNumber);
    if (!row.source || !row.target) {
      diagnostics.push({code: "STANDARD_MAPPING_EMPTY_CELL", row: rowNumber, source: row.source});
      return;
    }
    if (duplicate) {
      diagnostics.push({code: "STANDARD_MAPPING_SOURCE_DUPLICATE", row: rowNumber, source: row.source});
      return;
    }
    if (targetRule.allowed.length > 0 && !targetRule.allowed.includes(row.target)) {
      diagnostics.push({code: "STANDARD_MAPPING_TARGET_INVALID", row: rowNumber, source: row.source, value: row.target});
    }
  });
  for (const value of sourceDomain) {
    if (!seen.has(value)) diagnostics.push({code: "STANDARD_MAPPING_SOURCE_UNCOVERED", row: null, source: value});
  }
  return diagnostics;
}

// ------------------------------------------------------- 字段组合与 DWG 命名

export type SegmentKind = "field" | "literal" | "sequence";

export type CompositionDiagnosticCode =
  | "STANDARD_RULE_FIELD_UNKNOWN"
  | "STANDARD_RULE_FORMAT_INVALID"
  | "STANDARD_RULE_SOURCE_MISSING";

export interface CompositionDiagnostic {
  code: CompositionDiagnosticCode;
  segmentIndex: number;
  field?: string;
}

export interface CompositionPreview {
  /** 与片段一一对应的展示片段（缺失值为空串，预览不因单个缺失整体消失）。 */
  parts: string[];
  text: string;
  diagnostics: CompositionDiagnostic[];
}

export interface CompositionPreviewOptions {
  /** 站内已知字段引用（属性 + 派生目标 + 序数字段）；缺省表示不做引用检查。 */
  knownFields?: string[];
  /** 受控序号字段（`numbering.sequence_field`），用于区分序号令牌。 */
  sequenceField?: string;
}

export function segmentKind(segment: DraftSegment, sequenceField?: string): SegmentKind {
  if (segment.literal !== undefined) return "literal";
  if (sequenceField !== undefined && segment.field === sequenceField) return "sequence";
  return "field";
}

export function isValidPadFormat(format: string | undefined): boolean {
  if (format === undefined) return true;
  if (!PAD_FORMAT_PATTERN.test(format)) return false;
  const width = Number(format);
  return width >= 1 && width <= MAX_PAD_WIDTH;
}

/**
 * 纯展示预览：按片段顺序拼接示例值，同时就地报出非法格式码、未知引用与缺失示例值。
 * 不判断规则之间的拓扑依赖，也不做必填/枚举求值——那些仍由后端权威求值负责。
 */
export function renderCompositionPreview(
  segments: DraftSegment[],
  sampleValues: Record<string, string>,
  options: CompositionPreviewOptions = {},
): CompositionPreview {
  const diagnostics: CompositionDiagnostic[] = [];
  const parts = segments.map((segment, segmentIndex) => {
    if (segment.literal !== undefined) {
      // 固定文本不允许携带格式码（与后端同一判定）
      if (segment.format !== undefined) {
        diagnostics.push({code: "STANDARD_RULE_FORMAT_INVALID", segmentIndex});
      }
      return segment.literal;
    }
    const field = segment.field ?? "";
    if (options.knownFields !== undefined && !options.knownFields.includes(field)) {
      diagnostics.push({code: "STANDARD_RULE_FIELD_UNKNOWN", segmentIndex, field});
    }
    const value = sampleValues[field] ?? "";
    if (value === "") {
      diagnostics.push({code: "STANDARD_RULE_SOURCE_MISSING", segmentIndex, field});
      return "";
    }
    if (segment.format !== undefined) {
      if (!isValidPadFormat(segment.format)) {
        diagnostics.push({code: "STANDARD_RULE_FORMAT_INVALID", segmentIndex, field});
        return value;
      }
      const number = Number(value);
      if (!Number.isInteger(number)) return value;
      return String(number).padStart(Number(segment.format), "0");
    }
    return value;
  });
  return {parts, text: parts.join(""), diagnostics};
}

// ------------------------------------------------------------ 结构诊断

export interface StructureDiagnostic {
  code: string;
  ruleId?: string;
  field?: string;
  /** 映射表行号（1 起始）；非行级诊断为 undefined。 */
  row?: number;
}

/** 规则求值可引用的字段：属性定义 + 受控序数字段 + 规则派生目标。 */
export function knownFieldReferences(document: DraftDocument): string[] {
  const fields = document.properties.map(property => fieldReference(property));
  fields.push(document.numbering.sequence_field);
  fields.push(...document.rules.map(rule => rule.target));
  return fields.filter(Boolean);
}

function ruleSources(rule: DraftRule): string[] {
  if (rule.kind === "mapping") return rule.source ? [rule.source] : [];
  if (rule.kind === "compose" || rule.kind === "naming") {
    return rule.segments.filter(segment => typeof segment.field === "string").map(segment => segment.field!);
  }
  return [];
}

function hasCycle(rules: DraftRule[]): boolean {
  const produced = new Map<string, string>();
  for (const rule of rules) produced.set(rule.target, rule.rule_id);
  const dependents = new Map<string, string[]>();
  const indegree = new Map<string, number>();
  for (const rule of rules) {
    dependents.set(rule.rule_id, []);
    indegree.set(rule.rule_id, 0);
  }
  for (const rule of rules) {
    for (const source of ruleSources(rule)) {
      const producer = produced.get(source);
      if (producer === undefined || producer === rule.rule_id) continue;
      dependents.get(producer)!.push(rule.rule_id);
      indegree.set(rule.rule_id, (indegree.get(rule.rule_id) ?? 0) + 1);
    }
  }
  const ready = rules.filter(rule => indegree.get(rule.rule_id) === 0).map(rule => rule.rule_id);
  let resolved = 0;
  while (ready.length > 0) {
    const current = ready.shift()!;
    resolved += 1;
    for (const dependent of dependents.get(current) ?? []) {
      const next = (indegree.get(dependent) ?? 0) - 1;
      indegree.set(dependent, next);
      if (next === 0) ready.push(dependent);
    }
  }
  return resolved !== rules.length;
}

/**
 * 保存前的结构诊断：未知引用、重复规则/目标、非法格式码、空映射表与循环引用。
 * 与后端 `compile_standard_rules` 使用同一组稳定错误码，只做结构检查，不求值。
 */
export function validateDraftStructure(document: DraftDocument): StructureDiagnostic[] {
  const diagnostics: StructureDiagnostic[] = [];
  const known = knownFieldReferences(document);
  const targets = new Set<string>();
  const ruleIds = new Set<string>();
  for (const rule of document.rules) {
    if (rule.rule_id && ruleIds.has(rule.rule_id)) {
      diagnostics.push({code: "STANDARD_RULE_DUPLICATE", ruleId: rule.rule_id});
    }
    ruleIds.add(rule.rule_id);
    if (rule.target && targets.has(rule.target)) {
      diagnostics.push({code: "STANDARD_RULE_TARGET_DUPLICATE", ruleId: rule.rule_id, field: rule.target});
    }
    targets.add(rule.target);
    if (rule.kind === "mapping" && !rule.source) {
      diagnostics.push({code: "STANDARD_RULE_INVALID", ruleId: rule.rule_id});
    }
    for (const source of ruleSources(rule)) {
      if (!known.includes(source)) {
        diagnostics.push({code: "STANDARD_RULE_FIELD_UNKNOWN", ruleId: rule.rule_id, field: source});
      }
    }
    for (const segment of rule.segments) {
      if (!isValidPadFormat(segment.format)) {
        diagnostics.push({code: "STANDARD_RULE_FORMAT_INVALID", ruleId: rule.rule_id, field: segment.field});
      }
      if (segment.literal !== undefined && segment.format !== undefined) {
        diagnostics.push({code: "STANDARD_RULE_FORMAT_INVALID", ruleId: rule.rule_id, field: segment.literal});
      }
    }
    if (rule.kind === "mapping" && rule.table.length === 0) {
      diagnostics.push({code: "STANDARD_RULE_INVALID", ruleId: rule.rule_id});
    }
  }
  if (hasCycle(document.rules)) {
    diagnostics.push({code: "STANDARD_RULE_CYCLE", ruleId: document.rules[0]?.rule_id});
  }
  // 映射表行级诊断（重复源值/空单元格/非法目标值）带上行号，供错误摘要跳转到具体行
  for (const rule of document.rules) {
    if (rule.kind !== "mapping") continue;
    const target = document.properties.find(property => fieldReference(property) === rule.target);
    const source = document.properties.find(property => fieldReference(property) === rule.source);
    const rowDiagnostics = validateMapping(
      tableToMappingRows(rule.table),
      source?.enum_values ?? [],
      {allowed: target?.enum_values ?? []},
    );
    for (const item of rowDiagnostics) {
      diagnostics.push({
        code: item.code,
        ruleId: rule.rule_id,
        field: item.source,
        row: item.row ?? undefined,
      });
    }
  }
  return diagnostics;
}

// ------------------------------------------------------------ 编辑分区

/** 编辑分区标识（SPEC-DM-016 §6.1 的固定顺序）。 */
export type EditorSectionId =
  | "basic"
  | "properties"
  | "rules"
  | "mapping"
  | "composition"
  | "assets"
  | "publish";

export const EDITOR_SECTIONS: Array<{id: EditorSectionId; labelKey: string}> = [
  {id: "basic", labelKey: "standards.sections.basic"},
  {id: "properties", labelKey: "standards.sections.properties"},
  {id: "rules", labelKey: "standards.sections.rules"},
  {id: "mapping", labelKey: "standards.sections.mapping"},
  {id: "composition", labelKey: "standards.sections.composition"},
  {id: "assets", labelKey: "standards.sections.assets"},
  {id: "publish", labelKey: "standards.sections.publish"},
];

// ---------------------------------------------------------- 属性 CSV 导入

const CSV_TRUE_VALUES = new Set(["true", "1", "yes", "y", "是"]);

/** 从逗号分隔文本生成标准属性定义；空字段键的行被丢弃。 */
export function parsePropertyCsv(text: string): DraftProperty[] {
  const properties: DraftProperty[] = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const cells = line.split(",").map(cell => cell.trim());
    const [name, scope, required, defaultValue, enumValues, description] = cells;
    if (!name) continue;
    properties.push({
      name,
      scope: scope && FIELD_SCOPES.includes(scope as DraftScope) ? scope : "sheetset",
      required: CSV_TRUE_VALUES.has((required ?? "").toLowerCase()),
      default_value: defaultValue ?? "",
      enum_values: (enumValues ?? "").split("|").map(item => item.trim()).filter(Boolean),
      description: description ?? "",
    });
  }
  return properties;
}

// ------------------------------------------------------------ 规则摘要

export interface RuleSummary {
  /** 语言包键；视图用 `$t(summary.key, summary.params)` 渲染自然语言摘要。 */
  key: string;
  params: Record<string, string | number>;
}

export function ruleSummary(rule: DraftRule): RuleSummary {
  switch (rule.kind) {
    case "required":
      return {key: "standards.rules.summary.required", params: {field: rule.target}};
    case "enum":
      return {key: "standards.rules.summary.enum", params: {field: rule.target, values: rule.allowed.join(" / ")}};
    case "fixed":
      return {key: "standards.rules.summary.fixed", params: {field: rule.target, value: rule.value ?? ""}};
    case "mapping":
      return {
        key: "standards.rules.summary.mapping",
        params: {source: rule.source ?? "", target: rule.target, count: rule.table.length},
      };
    case "compose":
    case "naming":
      return {key: "standards.rules.summary.naming", params: {field: rule.target, count: rule.segments.length}};
    default:
      return {key: "standards.rules.summary.other", params: {field: rule.target}};
  }
}

/** 生成不冲突的规则 ID（用户可改，但默认值必须唯一）。 */
export function nextRuleId(document: DraftDocument, base: string): string {
  const used = new Set(document.rules.map(rule => rule.rule_id));
  if (!used.has(base)) return base;
  let index = 2;
  while (used.has(`${base}-${index}`)) index += 1;
  return `${base}-${index}`;
}

/** 草稿在标准库中的稳定键（列表选中与编辑器定位共用）。 */
export function draftKey(summary: Pick<StandardSummary, "source" | "draft_id" | "version">): string {
  return `${summary.source}/${summary.draft_id ?? summary.version}`;
}
