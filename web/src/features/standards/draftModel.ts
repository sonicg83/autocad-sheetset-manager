// 标准草稿编辑模型（PLAN-DM-038 Task 5 / SPEC-DM-017）：纯函数视图模型，无 Vue 与网络依赖。
// 职责边界：
// - 把标准文档规范化为可编辑的判别联合，保留未知顶层字段（受控流程不得丢数据）；
// - 普通属性（文本/枚举）与派生属性（映射/组合）分开建模，稳定 ID 与显示值分离；
// - 结构提示与发布诊断使用与后端**同一组稳定错误码**：保存门禁只看结构致命错误，
//   发布门禁包含全部 error，warning 不阻断；
// - 字段令牌范围与示例预览是纯展示：真实求值仍由后端权威完成，前端不复制最终规则。
// 本模块不持有用户可见文案：只返回稳定码与结构化参数，由视图经语言包渲染。
import type {StandardSummary} from "./types";

export type DraftPropertyScope = "sheetset" | "sheet";

export const PROPERTY_SCOPES: DraftPropertyScope[] = ["sheetset", "sheet"];

export type OrdinaryPropertyKind = "text" | "enum";

export const ORDINARY_PROPERTY_KINDS: OrdinaryPropertyKind[] = ["text", "enum"];

export type DerivedPropertyKind = "mapping" | "composition";

export const DERIVED_PROPERTY_KINDS: DerivedPropertyKind[] = ["mapping", "composition"];

export type DraftPropertyKind = OrdinaryPropertyKind | DerivedPropertyKind;

export const PROPERTY_KINDS: DraftPropertyKind[] = [...ORDINARY_PROPERTY_KINDS, ...DERIVED_PROPERTY_KINDS];

/** 子集系统字段：只对标准级 DWG 命名模板开放。 */
export const SUBSET_SYSTEM_FIELDS = ["subset.scope", "subset.name", "subset.sequence"] as const;
/** Sheet 系统字段：只对 sheet 组合属性开放；不含 `sheet.name` 与布局名。 */
export const SHEET_SYSTEM_FIELDS = ["sheet.number", "sheet.title"] as const;

/** 保留属性名（比较忽略大小写）；`DSTManager.*` 前缀整体保留。 */
export const RESERVED_PROPERTY_NAMES = [
  ...SUBSET_SYSTEM_FIELDS,
  ...SHEET_SYSTEM_FIELDS,
  "DSTManager.Standard",
  "DSTManager.StandardOptions",
];
export const RESERVED_PROPERTY_NAME_PREFIX = "dstmanager.";

export type DraftAssetKind = "base-template" | "layout-template";

export const ASSET_KINDS: DraftAssetKind[] = ["base-template", "layout-template"];

/** 宿主登记的数字补零格式：1–2 位十进制数，宽度上限 12（与后端同一口径）。 */
export const PAD_FORMAT_PATTERN = /^\d{1,2}$/;
export const MAX_PAD_WIDTH = 12;
/** 含扩展名的完整文件名长度上限（与后端同一口径）。 */
export const MAX_FILENAME_LENGTH = 240;
export const DWG_EXTENSION = ".dwg";

export interface DraftEnumItem {
  item_id: string;
  value: string;
}

export interface DraftMappingRow {
  item_id: string;
  value: string;
}

/** 片段只能是属性令牌、系统字段令牌或固定文本（三者互斥，可带受控补零格式码）。 */
export interface DraftSegment {
  property_id?: string;
  system_field?: string;
  literal?: string;
  format?: string;
}

interface DraftPropertyBase {
  property_id: string;
  name: string;
  previous_names: string[];
  scope: DraftPropertyScope;
  required: boolean;
  default_value: string;
  description: string;
}

export interface DraftTextProperty extends DraftPropertyBase {
  kind: "text";
}

export interface DraftEnumProperty extends DraftPropertyBase {
  kind: "enum";
  enum_items: DraftEnumItem[];
}

export interface DraftMappingProperty extends DraftPropertyBase {
  kind: "mapping";
  source_property_id: string;
  mapping: DraftMappingRow[];
  /** 用户确认映射时的源枚举快照（`[enum_item_id, 显示值]`，有序）。 */
  confirmed_source_items: Array<[string, string]>;
}

export interface DraftCompositionProperty extends DraftPropertyBase {
  kind: "composition";
  segments: DraftSegment[];
}

export type DraftProperty =
  | DraftTextProperty
  | DraftEnumProperty
  | DraftMappingProperty
  | DraftCompositionProperty;

export interface DraftDwgNaming {
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
  dwg_naming: DraftDwgNaming;
  assets: DraftAsset[];
  numbering: DraftNumbering;
  dependencies: DraftDependency[];
  [key: string]: unknown;
}

export const DEFAULT_NUMBERING: DraftNumbering = {sequence_field: "subset.sequence", digits: 2, start: 1};

/** 新建空白标准与 DST 提取共用的默认 DWG 命名模板（不携带隐式前缀）。 */
export function defaultDwgNamingSegments(): DraftSegment[] {
  return [
    {system_field: "subset.scope"},
    {literal: " "},
    {system_field: "subset.name"},
  ];
}

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
  if (typeof source.property_id === "string") segment.property_id = source.property_id;
  else if (typeof source.system_field === "string") segment.system_field = source.system_field;
  else if (typeof source.literal === "string") segment.literal = source.literal;
  if (typeof source.format === "string") segment.format = source.format;
  return segment;
}

function normalizeEnumItem(raw: unknown): DraftEnumItem {
  const source = asRecord(raw);
  return {item_id: asString(source.item_id), value: asString(source.value)};
}

function normalizeMappingRow(raw: unknown): DraftMappingRow {
  const source = asRecord(raw);
  return {item_id: asString(source.item_id), value: asString(source.value)};
}

function normalizeConfirmedItems(raw: unknown): Array<[string, string]> {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is unknown[] => Array.isArray(item) && item.length === 2)
    .map(item => [asString(item[0]), asString(item[1])] as [string, string]);
}

function normalizeProperty(raw: unknown): DraftProperty {
  const source = asRecord(raw);
  const base: DraftPropertyBase = {
    property_id: asString(source.property_id),
    name: asString(source.name),
    previous_names: asStringArray(source.previous_names),
    scope: asString(source.scope, "sheetset") as DraftPropertyScope,
    required: source.required === true,
    default_value: asString(source.default_value),
    description: asString(source.description),
  };
  // 未知类型按原值保留（不做猜测），由 `STANDARD_PROPERTY_KIND_INVALID` 定位。
  const kind = asString(source.kind, "text") as DraftPropertyKind;
  if (kind === "enum") {
    return {...base, kind, enum_items: (Array.isArray(source.enum_items) ? source.enum_items : []).map(normalizeEnumItem)};
  }
  if (kind === "mapping") {
    return {
      ...base,
      kind,
      source_property_id: asString(source.source_property_id),
      mapping: (Array.isArray(source.mapping) ? source.mapping : []).map(normalizeMappingRow),
      confirmed_source_items: normalizeConfirmedItems(source.confirmed_source_items),
    };
  }
  if (kind === "composition") {
    return {
      ...base,
      kind,
      segments: (Array.isArray(source.segments) ? source.segments : []).map(normalizeSegment),
    };
  }
  return {...base, kind: kind as "text"};
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
  const naming = asRecord(document.dwg_naming);
  return {
    ...document,
    schema_version: asInt(document.schema_version, 1),
    standard_id: asString(document.standard_id),
    version: asString(document.version),
    name: asString(document.name),
    supported_cad_versions: asStringArray(document.supported_cad_versions),
    properties: (Array.isArray(document.properties) ? document.properties : []).map(normalizeProperty),
    dwg_naming: {
      segments: (Array.isArray(naming.segments) ? naming.segments : []).map(normalizeSegment),
    },
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

// ------------------------------------------------------------------ 查询

export function isDerivedProperty(property: DraftProperty): boolean {
  return property.kind === "mapping" || property.kind === "composition";
}

export function propertyById(document: DraftDocument, propertyId: string): DraftProperty | undefined {
  return document.properties.find(property => property.property_id === propertyId);
}

export function propertyIndexById(document: DraftDocument, propertyId: string): number {
  return document.properties.findIndex(property => property.property_id === propertyId);
}

/** 属性名比较口径：忽略首尾空格与大小写（与后端同一口径）。 */
export function normalizedPropertyName(name: string): string {
  return name.trim().toLocaleLowerCase();
}

/** 枚举属性按显示值取枚举项（映射求值以显示值 → item_id → 目标）。 */
export function enumItemByValue(property: DraftProperty | undefined, value: string): DraftEnumItem | undefined {
  if (property?.kind !== "enum") return undefined;
  return property.enum_items.find(item => item.value === value);
}

// -------------------------------------------------------------- 反向引用

export type ReferenceKind = "mapping" | "composition" | "dwgNaming";

export interface PropertyReference {
  kind: ReferenceKind;
  /** 引用方属性 ID；DWG 命名模板为空串。 */
  ownerId: string;
  segmentIndex?: number;
}

/**
 * 枚举对某属性的全部引用：映射源、组合令牌与 DWG 命名令牌。
 * 删除保护与发布诊断共用；顺序为属性文档顺序 + 命名片段顺序。
 */
export function referencesTo(document: DraftDocument, propertyId: string): PropertyReference[] {
  const references: PropertyReference[] = [];
  for (const property of document.properties) {
    if (property.kind === "mapping" && property.source_property_id === propertyId) {
      references.push({kind: "mapping", ownerId: property.property_id});
    }
    if (property.kind === "composition") {
      property.segments.forEach((segment, segmentIndex) => {
        if (segment.property_id === propertyId) {
          references.push({kind: "composition", ownerId: property.property_id, segmentIndex});
        }
      });
    }
  }
  document.dwg_naming.segments.forEach((segment, segmentIndex) => {
    if (segment.property_id === propertyId) {
      references.push({kind: "dwgNaming", ownerId: "", segmentIndex});
    }
  });
  return references;
}

// ------------------------------------------------------------ 字段令牌

/** 组合属性可见字段：普通/映射属性按作用域过滤，sheet 组合另加两个 Sheet 系统字段。 */
export function compositionFields(document: DraftDocument, scope: DraftPropertyScope): string[] {
  const fields: string[] = [];
  for (const property of document.properties) {
    if (isDerivedProperty(property) && property.kind === "composition") continue;
    if (scope === "sheetset" && property.scope !== "sheetset") continue;
    fields.push(property.property_id);
  }
  if (scope === "sheet") fields.push(...SHEET_SYSTEM_FIELDS);
  return fields;
}

/** DWG 命名可见字段：三个子集系统字段 + 全部 sheetset 属性（不含 sheet 属性）。 */
export function dwgNamingFields(document: DraftDocument): string[] {
  const fields: string[] = [...SUBSET_SYSTEM_FIELDS];
  for (const property of document.properties) {
    if (property.scope === "sheetset") fields.push(property.property_id);
  }
  return fields;
}

// -------------------------------------------------------------- 诊断

export type DiagnosticOwner = "document" | "property" | "dwgNaming" | "asset";
export type DiagnosticSeverity = "error" | "warning";

export interface DraftDiagnostic {
  code: string;
  severity: DiagnosticSeverity;
  owner: DiagnosticOwner;
  propertyId?: string;
  segmentIndex?: number;
  itemId?: string;
  assetId?: string;
  /** 删除保护专用：阻止删除的引用方列表。 */
  references?: PropertyReference[];
}

interface GatedDiagnostic extends DraftDiagnostic {
  /** 结构致命错误进保存门禁；其余只在发布门禁出现。 */
  gate: "structure" | "publish";
}

const ORDINARY_PREFIXES = ["STANDARD_PROPERTY_", "STANDARD_SCOPE_", "STANDARD_ENUM_"];

function isReservedName(normalized: string): boolean {
  return (
    RESERVED_PROPERTY_NAMES.some(name => normalizedPropertyName(name) === normalized)
    || normalized.startsWith(RESERVED_PROPERTY_NAME_PREFIX)
  );
}

export function isValidPadFormat(format: string | undefined): boolean {
  if (format === undefined) return true;
  if (!PAD_FORMAT_PATTERN.test(format)) return false;
  const width = Number(format);
  return width >= 1 && width <= MAX_PAD_WIDTH;
}

/** 文件名主体安全校验（与后端同码；不做字符替换，只返回定位性错误）。 */
function filenameDiagnostics(body: string, owner: DiagnosticOwner): GatedDiagnostic[] {
  const base = {severity: "error" as const, owner, gate: "publish" as const};
  if (body === "") return [{...base, code: "DWG_NAME_EMPTY"}];
  if (body.toLocaleLowerCase().includes(DWG_EXTENSION)) {
    return [{...base, code: "DWG_NAME_EXTENSION_FORBIDDEN"}];
  }
  if (body === "." || body === ".." || /[<>:"/\\|?*]/.test(body) || [...body].some(char => char.charCodeAt(0) < 32)) {
    return [{...base, code: "DWG_NAME_CHARACTER_INVALID"}];
  }
  if (body.endsWith(" ") || body.endsWith(".")) {
    return [{...base, code: "DWG_NAME_TRAILING_CHARACTER"}];
  }
  const device = body.split(".", 1)[0]?.toLocaleLowerCase() ?? "";
  const devices = ["con", "prn", "aux", "nul", "clock$", ...Array.from({length: 9}, (_item, index) => `com${index + 1}`), ...Array.from({length: 9}, (_item, index) => `lpt${index + 1}`)];
  if (devices.includes(device)) return [{...base, code: "DWG_NAME_RESERVED_DEVICE"}];
  if (body.length + DWG_EXTENSION.length > MAX_FILENAME_LENGTH) {
    return [{...base, code: "DWG_NAME_TOO_LONG"}];
  }
  return [];
}

function segmentDiagnostics(
  document: DraftDocument,
  segments: DraftSegment[],
  owner: DiagnosticOwner,
  propertyId: string | undefined,
  allowedFields: string[],
  allowedSystemFields: string[],
): GatedDiagnostic[] {
  const diagnostics: GatedDiagnostic[] = [];
  const base = {owner, propertyId, gate: "publish" as const, severity: "error" as const};
  segments.forEach((segment, segmentIndex) => {
    const contents = [segment.property_id, segment.system_field, segment.literal].filter(
      value => value !== undefined,
    );
    if (contents.length !== 1) {
      diagnostics.push({...base, code: "STANDARD_SEGMENT_INVALID", segmentIndex, gate: "structure"});
      return;
    }
    if (segment.property_id !== undefined) {
      if (!document.properties.some(property => property.property_id === segment.property_id)) {
        diagnostics.push({...base, code: "STANDARD_SEGMENT_REFERENCE_UNKNOWN", segmentIndex, gate: "structure"});
        return;
      }
      if (!allowedFields.includes(segment.property_id)) {
        diagnostics.push({...base, code: "STANDARD_SEGMENT_SCOPE_INVALID", segmentIndex});
      }
    }
    if (segment.system_field !== undefined && !allowedSystemFields.includes(segment.system_field)) {
      diagnostics.push({...base, code: "STANDARD_SEGMENT_SCOPE_INVALID", segmentIndex});
    }
    if (segment.format !== undefined && !isValidPadFormat(segment.format)) {
      diagnostics.push({...base, code: "STANDARD_SEGMENT_FORMAT_INVALID", segmentIndex});
    }
  });
  return diagnostics;
}

function propertyStructureDiagnostics(document: DraftDocument): GatedDiagnostic[] {
  const diagnostics: GatedDiagnostic[] = [];
  const seenIds = new Set<string>();
  for (const property of document.properties) {
    const base = {owner: "property" as const, propertyId: property.property_id, severity: "error" as const};
    if (property.property_id.trim() === "") {
      diagnostics.push({...base, code: "STANDARD_PROPERTY_ID_INVALID", gate: "structure"});
    } else if (seenIds.has(property.property_id)) {
      diagnostics.push({...base, code: "STANDARD_PROPERTY_ID_DUPLICATE", gate: "structure"});
    }
    seenIds.add(property.property_id);
    if (!PROPERTY_SCOPES.includes(property.scope)) {
      diagnostics.push({...base, code: "STANDARD_SCOPE_INVALID", gate: "structure"});
    }
    if (!PROPERTY_KINDS.includes(property.kind)) {
      diagnostics.push({...base, code: "STANDARD_PROPERTY_KIND_INVALID", gate: "structure"});
    }
    if (property.kind === "enum") {
      const itemIds = new Set<string>();
      for (const item of property.enum_items) {
        if (item.item_id.trim() === "") {
          diagnostics.push({...base, code: "STANDARD_ENUM_ITEM_ID_INVALID", itemId: item.item_id, gate: "structure"});
        } else if (itemIds.has(item.item_id)) {
          diagnostics.push({...base, code: "STANDARD_ENUM_ITEM_ID_DUPLICATE", itemId: item.item_id, gate: "structure"});
        }
        itemIds.add(item.item_id);
      }
    }
    if (property.kind === "mapping") {
      const source = propertyById(document, property.source_property_id);
      if (source === undefined) {
        diagnostics.push({...base, code: "STANDARD_MAPPING_SOURCE_INVALID", gate: "structure"});
      }
    }
    if (property.kind === "composition") {
      const allowed = compositionFields(document, property.scope).filter(
        field => !SHEET_SYSTEM_FIELDS.includes(field as typeof SHEET_SYSTEM_FIELDS[number]),
      );
      diagnostics.push(
        ...segmentDiagnostics(document, property.segments, "property", property.property_id, allowed, [
          ...(property.scope === "sheet" ? SHEET_SYSTEM_FIELDS : []),
        ]),
      );
    }
  }
  return diagnostics;
}

function propertyPublishDiagnostics(document: DraftDocument): GatedDiagnostic[] {
  const diagnostics: GatedDiagnostic[] = [];
  const claimed = new Map<string, string>();
  const mappingSources = new Map<string, string>();
  for (const property of document.properties) {
    const base = {owner: "property" as const, propertyId: property.property_id, severity: "error" as const};
    if (property.name.trim() === "") {
      diagnostics.push({...base, code: "STANDARD_PROPERTY_NAME_INVALID", gate: "publish"});
    }
    for (const name of [property.name, ...property.previous_names]) {
      const normalized = normalizedPropertyName(name);
      if (normalized === "") continue;
      if (isReservedName(normalized)) {
        diagnostics.push({...base, code: "STANDARD_PROPERTY_NAME_RESERVED", gate: "publish"});
        continue;
      }
      const owner = claimed.get(normalized);
      if (owner !== undefined && owner !== property.property_id) {
        diagnostics.push({...base, code: "STANDARD_PROPERTY_NAME_DUPLICATE", gate: "publish"});
      } else {
        claimed.set(normalized, property.property_id);
      }
    }
    if (property.kind === "enum") {
      const values: string[] = [];
      for (const item of property.enum_items) {
        if (item.value === "") {
          diagnostics.push({...base, code: "STANDARD_ENUM_ITEM_INVALID", itemId: item.item_id, gate: "publish"});
          continue;
        }
        if (values.includes(item.value)) {
          diagnostics.push({...base, code: "STANDARD_ENUM_ITEM_DUPLICATE", itemId: item.item_id, gate: "publish"});
          continue;
        }
        values.push(item.value);
      }
      if (property.default_value !== "" && !values.includes(property.default_value)) {
        diagnostics.push({...base, code: "STANDARD_ENUM_DEFAULT_INVALID", gate: "publish"});
      }
    }
    if (property.kind === "mapping") {
      const source = propertyById(document, property.source_property_id);
      if (source !== undefined && source.kind !== "enum") {
        diagnostics.push({...base, code: "STANDARD_MAPPING_SOURCE_INVALID", gate: "publish"});
      } else if (source !== undefined) {
        if (property.scope === "sheetset" && source.scope !== "sheetset") {
          diagnostics.push({...base, code: "STANDARD_MAPPING_SCOPE_INVALID", gate: "publish"});
        }
        const owner = mappingSources.get(source.property_id);
        if (owner !== undefined && owner !== property.property_id) {
          diagnostics.push({...base, code: "STANDARD_MAPPING_SOURCE_DUPLICATE", gate: "publish"});
        } else {
          mappingSources.set(source.property_id, property.property_id);
        }
        const targets = new Map(property.mapping.map(row => [row.item_id, row.value]));
        const snapshot = property.confirmed_source_items.map(([itemId, value]) => `${itemId}\u0000${value}`).join("\u0001");
        const current = source.enum_items.map(item => `${item.item_id}\u0000${item.value}`).join("\u0001");
        for (const item of source.enum_items) {
          if ((targets.get(item.item_id) ?? "") === "") {
            diagnostics.push({...base, code: "STANDARD_MAPPING_TARGET_EMPTY", itemId: item.item_id, gate: "publish"});
          }
        }
        if (snapshot !== current) {
          diagnostics.push({...base, code: "STANDARD_MAPPING_CONFIRMATION_REQUIRED", severity: "warning", gate: "publish"});
        }
      }
    }
  }
  return diagnostics;
}

function dwgNamingDiagnostics(document: DraftDocument): GatedDiagnostic[] {
  const diagnostics: GatedDiagnostic[] = [];
  const base = {owner: "dwgNaming" as const, severity: "error" as const};
  if (document.dwg_naming.segments.length === 0) {
    return [{...base, code: "STANDARD_DWG_NAMING_MISSING", gate: "structure"}];
  }
  diagnostics.push(
    ...segmentDiagnostics(
      document,
      document.dwg_naming.segments,
      "dwgNaming",
      undefined,
      document.properties.filter(property => property.scope === "sheetset").map(property => property.property_id),
      [...SUBSET_SYSTEM_FIELDS],
    ).map(item =>
      item.code === "STANDARD_SEGMENT_SCOPE_INVALID"
        ? {...item, code: "STANDARD_NAMING_FIELD_SCOPE_INVALID"}
        : item,
    ),
  );
  const systemFields = document.dwg_naming.segments
    .map(segment => segment.system_field)
    .filter((field): field is string => field !== undefined);
  if (!systemFields.includes("subset.scope") && !systemFields.includes("subset.sequence")) {
    diagnostics.push({...base, code: "DWG_NAMING_UNIQUENESS_UNPROVEN", severity: "warning", gate: "publish"});
  }
  return diagnostics;
}

function assetDiagnostics(document: DraftDocument): GatedDiagnostic[] {
  const diagnostics: GatedDiagnostic[] = [];
  const seen = new Set<string>();
  for (const asset of document.assets) {
    const base = {owner: "asset" as const, assetId: asset.asset_id, severity: "error" as const};
    if (asset.asset_id.trim() === "") {
      diagnostics.push({...base, code: "STANDARD_ASSET_INVALID", gate: "structure"});
    } else if (seen.has(asset.asset_id)) {
      diagnostics.push({...base, code: "STANDARD_ASSET_DUPLICATE", gate: "structure"});
    }
    seen.add(asset.asset_id);
    if (!ASSET_KINDS.includes(asset.kind as DraftAssetKind)) {
      diagnostics.push({...base, code: "STANDARD_ASSET_KIND_INVALID", gate: "structure"});
    }
    for (const file of asset.files) {
      if (!validAssetPath(file.path)) {
        diagnostics.push({...base, code: "STANDARD_ASSET_PATH_INVALID", gate: "structure"});
      }
    }
  }
  return diagnostics;
}

function documentDiagnostics(document: DraftDocument): GatedDiagnostic[] {
  const diagnostics: GatedDiagnostic[] = [];
  const base = {owner: "document" as const, severity: "error" as const, gate: "structure" as const};
  if (!STANDARD_ID_PATTERN.test(document.standard_id)) {
    diagnostics.push({...base, code: "STANDARD_ID_INVALID"});
  }
  if (!STANDARD_VERSION_PATTERN.test(document.version)) {
    diagnostics.push({...base, code: "STANDARD_VERSION_INVALID"});
  }
  if (document.name.trim() === "") diagnostics.push({...base, code: "STANDARD_NAME_INVALID"});
  if (document.supported_cad_versions.length === 0) {
    diagnostics.push({...base, code: "STANDARD_CAD_VERSIONS_INVALID"});
  }
  if (!Number.isInteger(document.numbering.digits) || document.numbering.digits <= 0) {
    diagnostics.push({...base, code: "STANDARD_NUMBERING_INVALID"});
  }
  return diagnostics;
}

/** 保存门禁：只包含结构致命错误（草稿允许语义未完成内容）。 */
export function draftDiagnostics(document: DraftDocument): DraftDiagnostic[] {
  return collectDiagnostics(document)
    .filter(item => item.gate === "structure")
    .map(({gate: _gate, ...item}) => item);
}

/** 发布门禁：结构 + 语义 error 与 warning（error 阻断，warning 只提示）。 */
export function publishIssues(document: DraftDocument): DraftDiagnostic[] {
  const diagnostics = [...collectDiagnostics(document), ...filenameIssues(document)];
  return diagnostics.map(({gate: _gate, ...item}) => item);
}

function collectDiagnostics(document: DraftDocument): GatedDiagnostic[] {
  return [
    ...documentDiagnostics(document),
    ...propertyStructureDiagnostics(document),
    ...propertyPublishDiagnostics(document),
    ...dwgNamingDiagnostics(document),
    ...assetDiagnostics(document),
  ];
}

/** 示例预览渲染后才能判定的文件名安全提示（前端只提示，发布以后端码为准）。 */
function filenameIssues(document: DraftDocument): GatedDiagnostic[] {
  if (document.dwg_naming.segments.length === 0) return [];
  return filenameDiagnostics(renderDwgNamingPreview(document).body, "dwgNaming");
}

export const STANDARD_ID_PATTERN = /^[a-z][a-z0-9-]*(\.[a-z0-9-]+)*$/;
export const STANDARD_VERSION_PATTERN = /^\d+\.\d+\.\d+$/;

function validAssetPath(path: string): boolean {
  if (path === "") return false;
  if (path.startsWith("/") || path.startsWith("\\")) return false;
  if (/^[A-Za-z]:/.test(path)) return false;
  return !path.split(/[/\\]/).includes("..");
}

// -------------------------------------------------------------- 示例预览

/** 取样顺序：默认值 → 枚举首项 → 首个非空映射目标 → 示例占位值。 */
export function samplePropertyValue(property: DraftProperty): string {
  if (property.default_value !== "") return property.default_value;
  if (property.kind === "enum") {
    const first = property.enum_items.find(item => item.value !== "");
    if (first !== undefined) return first.value;
  }
  if (property.kind === "mapping") {
    const first = property.mapping.find(row => row.value !== "");
    if (first !== undefined) return first.value;
  }
  return "";
}

export interface PreviewResult {
  /** 与片段一一对应的展示片段（缺失值为空串，预览不因单个缺失整体消失）。 */
  parts: string[];
  text: string;
  diagnostics: DraftDiagnostic[];
}

export interface DwgNamingPreview extends PreviewResult {
  /** 文件名主体（不含扩展名）。 */
  body: string;
  filename: string;
}

function renderSegments(
  document: DraftDocument,
  segments: DraftSegment[],
  sampleValues: Record<string, string>,
  systemValues: Record<string, string>,
): PreviewResult {
  const diagnostics: DraftDiagnostic[] = [];
  const parts = segments.map((segment, segmentIndex) => {
    if (segment.literal !== undefined) return segment.literal;
    if (segment.system_field !== undefined) {
      const value = systemValues[segment.system_field] ?? "";
      if (value === "") {
        diagnostics.push({code: "STANDARD_SYSTEM_VALUE_MISSING", severity: "error", owner: "dwgNaming", segmentIndex});
        return "";
      }
      return value;
    }
    const propertyId = segment.property_id ?? "";
    const value = sampleValues[propertyId] ?? "";
    if (value === "") {
      diagnostics.push({code: "STANDARD_DERIVED_UPSTREAM_INVALID", severity: "error", owner: "property", propertyId, segmentIndex});
      return "";
    }
    if (segment.format !== undefined && isValidPadFormat(segment.format)) {
      const number = Number(value);
      if (Number.isInteger(number)) return String(number).padStart(Number(segment.format), "0");
    }
    return value;
  });
  return {parts, text: parts.join(""), diagnostics};
}

/**
 * 标准编辑器中的 DWG 命名示例预览：固定 `subset.sequence = 1`、按编号位数构造
 * `subset.scope`、名称「示例子集」，并明确标注为示例（不得冒充工程结果）。
 */
export function renderDwgNamingPreview(document: DraftDocument): DwgNamingPreview {
  const sampleValues: Record<string, string> = {};
  for (const property of document.properties) sampleValues[property.property_id] = samplePropertyValue(property);
  const width = Math.max(document.numbering.digits, 1);
  const scope = `${String(1).padStart(width, "0")}-${String(3).padStart(width, "0")}`;
  const result = renderSegments(document, document.dwg_naming.segments, sampleValues, {
    "subset.scope": scope,
    "subset.name": SAMPLE_SUBSET_NAME,
    "subset.sequence": "1",
  });
  const body = result.text;
  const diagnostics = [
    ...result.diagnostics,
    ...filenameDiagnostics(body, "dwgNaming").map(({gate: _gate, ...item}) => item),
  ];
  return {parts: result.parts, text: body, body, filename: `${body}${DWG_EXTENSION}`, diagnostics};
}

export const SAMPLE_SUBSET_NAME = "示例子集";
export const SAMPLE_SHEET_NUMBER = "001";
export const SAMPLE_SHEET_TITLE = "示例图名";

/** 组合属性的实时示例预览（字段缺失按空字符串拼接）。 */
export function renderCompositionPreview(document: DraftDocument, property: DraftCompositionProperty): PreviewResult {
  const sampleValues: Record<string, string> = {};
  for (const candidate of document.properties) {
    sampleValues[candidate.property_id] = samplePropertyValue(candidate);
  }
  return renderSegments(document, property.segments, sampleValues, {
    "sheet.number": SAMPLE_SHEET_NUMBER,
    "sheet.title": SAMPLE_SHEET_TITLE,
  });
}

// -------------------------------------------------------------- 编辑辅助

export function nextPropertyId(document: DraftDocument, base: string, taken: string[] = []): string {
  const used = new Set([...document.properties.map(property => property.property_id), ...taken]);
  if (!used.has(base)) return base;
  let index = 2;
  while (used.has(`${base}-${index}`)) index += 1;
  return `${base}-${index}`;
}

export function nextEnumItemId(property: DraftProperty, base: string): string {
  const used = new Set(property.kind === "enum" ? property.enum_items.map(item => item.item_id) : []);
  if (!used.has(base)) return base;
  let index = 2;
  while (used.has(`${base}-${index}`)) index += 1;
  return `${base}-${index}`;
}

function blankBase(document: DraftDocument, scope: DraftPropertyScope): DraftPropertyBase {
  return {
    property_id: nextPropertyId(document, "prop-new"),
    name: "",
    previous_names: [],
    scope,
    required: false,
    default_value: "",
    description: "",
  };
}

export function blankOrdinaryProperty(
  document: DraftDocument,
  kind: OrdinaryPropertyKind,
  scope: DraftPropertyScope = "sheetset",
): DraftProperty {
  const base = blankBase(document, scope);
  if (kind === "enum") return {...base, kind, enum_items: [{item_id: "enum-new", value: ""}]};
  return {...base, kind: "text"};
}

export function blankDerivedProperty(
  document: DraftDocument,
  kind: DerivedPropertyKind,
  scope: DraftPropertyScope = "sheetset",
): DraftProperty {
  const base = blankBase(document, scope);
  if (kind === "mapping") {
    return {...base, kind, source_property_id: "", mapping: [], confirmed_source_items: []};
  }
  return {...base, kind, segments: []};
}

const CSV_TRUE_VALUES = new Set(["true", "1", "yes", "y", "是"]);

/**
 * 从逗号分隔文本生成**普通属性**定义（文本/枚举）：CSV 不产生任何派生关系，
 * 空名称行被丢弃，`|` 分隔的枚举值生成带稳定 ID 的枚举项。
 */
export function parsePropertyCsv(text: string, document: DraftDocument): DraftProperty[] {
  const properties: DraftProperty[] = [];
  const taken: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const cells = line.split(",").map(cell => cell.trim());
    const [name, scope, required, defaultValue, enumValues, description] = cells;
    if (!name) continue;
    const propertyId = nextPropertyId(document, "prop-csv", taken);
    taken.push(propertyId);
    const base: DraftPropertyBase = {
      property_id: propertyId,
      name,
      previous_names: [],
      scope: scope !== undefined && PROPERTY_SCOPES.includes(scope as DraftPropertyScope)
        ? scope as DraftPropertyScope
        : "sheetset",
      required: CSV_TRUE_VALUES.has((required ?? "").toLocaleLowerCase()),
      default_value: defaultValue ?? "",
      description: description ?? "",
    };
    const values = (enumValues ?? "").split("|").map(item => item.trim()).filter(Boolean);
    if (values.length === 0) {
      properties.push({...base, kind: "text"});
      continue;
    }
    properties.push({
      ...base,
      kind: "enum",
      enum_items: values.map((value, index) => ({item_id: `enum-csv-${index + 1}`, value})),
    });
  }
  return properties;
}

// -------------------------------------------------------------- 编辑分区

/** 编辑分区标识（SPEC-DM-017 §2 的固定六分区顺序）。 */
export type EditorSectionId = "basic" | "ordinary" | "derived" | "dwgNaming" | "assets" | "publish";

export const EDITOR_SECTIONS: Array<{id: EditorSectionId; labelKey: string}> = [
  {id: "basic", labelKey: "standards.sections.basic"},
  {id: "ordinary", labelKey: "standards.sections.ordinary"},
  {id: "derived", labelKey: "standards.sections.derived"},
  {id: "dwgNaming", labelKey: "standards.sections.dwgNaming"},
  {id: "assets", labelKey: "standards.sections.assets"},
  {id: "publish", labelKey: "standards.sections.publish"},
];

/** 草稿在标准库中的稳定键（列表选中与编辑器定位共用）。 */
export function draftKey(summary: Pick<StandardSummary, "source" | "draft_id" | "version">): string {
  return `${summary.source}/${summary.draft_id ?? summary.version}`;
}
