// 发布检查模型（PLAN-DM-035 Task 10 / SPEC-DM-016 §8–§9）：纯函数门禁，无 Vue 与网络依赖。
// 职责边界：
// - 把壳层结构诊断（`validateDraftStructure`）映射到检查域与跳转目标（规则/映射行）；
// - 把后端资产检查结果与前端可推导的布局严格差异、未引用资产警告归一为发布问题；
// - 判定 `canPublish`：错误与「检查本身失败」都阻断，警告不阻断。
// 后端仍是发布门禁的权威：这里只做保存/发布前的就地提示，同一问题在后端返回时使用同一稳定码。
// 模型不持有用户可见文案：只返回稳定码与结构化插值参数，由视图经语言包渲染。
import {
  COMPOSITION_RULE_KINDS,
  type DraftAsset,
  type DraftDocument,
  type EditorSectionId,
  type DraftRule,
  type StructureDiagnostic,
} from "./draftModel";
import type {AssetInspection} from "./types";

/** 图幅匹配必须排除的模型空间布局（多文件聚合结果里同样排除）。 */
export const MODEL_LAYOUT_NAME = "Model";

/** 布局严格不一致的稳定码（与后端 `standard_assets._layout_mismatch` 同码）。 */
export const LAYOUT_MISMATCH_CODE = "STANDARD_LAYOUT_NAME_MISMATCH";

/** 未被标准取值引用的有效资产：警告，不阻断发布（SPEC-DM-016 §8.2）。 */
export const UNREFERENCED_ASSET_CODE = "STANDARD_ASSET_UNREFERENCED";

export type PublishSeverity = "error" | "warning";

export interface PublishTarget {
  section: EditorSectionId;
  ruleId?: string;
  /** 映射表行号（1 起始）；null 表示映射表整体（未覆盖源值）。 */
  row?: number | null;
  assetId?: string;
  layout?: string;
  field?: string;
}

export interface PublishIssue {
  code: string;
  severity: PublishSeverity;
  target: PublishTarget;
  /** 语言包插值参数（结构化值，不含本地化句子）。 */
  params: Record<string, string | number>;
}

/** 检查动作本身失败（CAD 不可用/网络失败等）：不是「标准存在错误」，但同样阻断发布。 */
export interface InspectionFailure {
  assetId: string;
  message: string;
}

export interface PublishGate {
  blockingErrors: PublishIssue[];
  warnings: PublishIssue[];
  inspectionFailures: InspectionFailure[];
  counts: {errors: number; warnings: number; failures: number};
  canPublish: boolean;
}

export interface PublishReport {
  document: DraftDocument;
  structure: StructureDiagnostic[];
  assets: AssetInspection[];
  inspectionFailures?: InspectionFailure[];
}

// ------------------------------------------------------------ 布局严格匹配

/** 资产声明的图幅（文件 role，去重且丢弃空值）。 */
export function declaredRoles(asset: DraftAsset): string[] {
  const roles: string[] = [];
  for (const file of asset.files) {
    if (file.role && !roles.includes(file.role)) roles.push(file.role);
  }
  return roles;
}

/** 检查到的非 Model 布局（不做去空白或大小写归一）。 */
export function nonModelLayouts(layouts: string[]): string[] {
  return layouts.filter(name => name !== MODEL_LAYOUT_NAME);
}

/**
 * 声明图幅与实际布局的严格差异：只做精确字符串比较——`"A3 "` 与 `"A3"` 视为两个不同布局。
 * 缺声明与多未声明都阻断发布（歧义布局）。
 */
export function compareLayouts(declared: string[], actual: string[]): {missing: string[]; extra: string[]} {
  return {
    missing: declared.filter(role => !actual.includes(role)),
    extra: actual.filter(name => !declared.includes(name)),
  };
}

// ------------------------------------------------------------ 资产引用关系

export type ReferenceKind =
  | "property-enum"
  | "rule-fixed"
  | "rule-allowed"
  | "mapping-target"
  | "segment-literal";

export interface AssetReference {
  role: string;
  kind: ReferenceKind;
  /** 引用位置标识（字段引用或规则 ID）。 */
  ref: string;
  value: string;
}

/** 标准里可能引用图幅取值的所有位置；为空表示本草案无法判定引用关系。 */
export function hasReferenceSources(document: DraftDocument): boolean {
  if (document.properties.some(property => property.enum_values.length > 0)) return true;
  return document.rules.some(rule =>
    rule.value !== undefined
    || rule.allowed.length > 0
    || rule.table.length > 0
    || rule.segments.some(segment => segment.literal !== undefined));
}

function ruleLabel(rule: {rule_id: string; target: string}): string {
  return rule.target || rule.rule_id;
}

/** 资产声明的图幅在标准中被引用的位置（属性枚举、规则取值、映射目标、固定文本片段）。 */
export function assetReferences(document: DraftDocument, asset: DraftAsset): AssetReference[] {
  const roles = declaredRoles(asset);
  if (roles.length === 0) return [];
  const references: AssetReference[] = [];
  const collect = (role: string, kind: ReferenceKind, ref: string, value: string): void => {
    references.push({role, kind, ref, value});
  };
  for (const role of roles) {
    for (const property of document.properties) {
      if (property.enum_values.includes(role)) {
        collect(role, "property-enum", `${property.scope}.${property.name}`, role);
      }
    }
    for (const rule of document.rules) {
      const ref = ruleLabel(rule);
      if (rule.value === role) collect(role, "rule-fixed", ref, role);
      if (rule.allowed.includes(role)) collect(role, "rule-allowed", ref, role);
      for (const [, target] of rule.table) {
        if (target === role) collect(role, "mapping-target", ref, role);
      }
      for (const segment of rule.segments) {
        if (segment.literal === role) collect(role, "segment-literal", ref, role);
      }
    }
  }
  return references;
}

// ------------------------------------------------------------ 结构诊断映射

function sectionOfRule(rule: DraftRule | undefined): EditorSectionId {
  if (rule === undefined) return "rules";
  if (rule.kind === "mapping") return "mapping";
  if (COMPOSITION_RULE_KINDS.includes(rule.kind)) return "composition";
  return "rules";
}

/** 非规则类结构码的检查域归属（基本信息/属性定义/模板资产）。 */
const CODE_SECTIONS: Array<[prefix: string, section: EditorSectionId]> = [
  ["STANDARD_ASSET_", "assets"],
  ["STANDARD_PROPERTY_", "properties"],
  ["STANDARD_SCOPE_", "properties"],
  ["STANDARD_NUMBERING_", "basic"],
  ["STANDARD_CAD_VERSIONS_", "basic"],
  ["STANDARD_ID_", "basic"],
  ["STANDARD_VERSION_", "basic"],
  ["STANDARD_NAME_", "basic"],
];

function sectionOfCode(code: string): EditorSectionId | null {
  for (const [prefix, section] of CODE_SECTIONS) {
    if (code.startsWith(prefix)) return section;
  }
  return null;
}

/** 结构诊断 → 发布问题：按规则种类决定检查域，行级诊断保留行号。 */
export function structureIssue(document: DraftDocument, item: StructureDiagnostic): PublishIssue {
  const rule = document.rules.find(candidate => candidate.rule_id === item.ruleId);
  const section = sectionOfCode(item.code) ?? sectionOfRule(rule);
  if (section !== "rules" && section !== "mapping" && section !== "composition") {
    // 基本信息/属性定义/模板资产类：没有行概念，只带字段标识便于视图定位
    const target: PublishTarget = {section};
    if (section === "assets" && item.field) target.assetId = item.field;
    const params: Record<string, string | number> = {};
    if (item.field !== undefined && item.field !== "") params.field = item.field;
    return {code: item.code, severity: "error", target, params};
  }
  if (item.code === "STANDARD_MAPPING_SOURCE_UNCOVERED") {
    // 未覆盖源值不指向具体行：定位到映射表整体，插值参数只有源值
    return {
      code: item.code,
      severity: "error",
      target: {section, ruleId: item.ruleId, row: null},
      params: {source: item.field ?? ""},
    };
  }
  const target: PublishTarget = {section, ruleId: item.ruleId};
  const params: Record<string, string | number> = {};
  if (item.field !== undefined && item.field !== "") params.field = item.field;
  if (item.code === "STANDARD_RULE_INVALID" && rule?.kind === "mapping") {
    // 空映射表：定位到映射表整体，交由映射分区聚焦未覆盖/表体摘要
    target.row = null;
  } else if (item.row !== undefined) {
    target.row = item.row;
    params.source = item.field ?? "";
  }
  return {code: item.code, severity: "error", target, params};
}

// ------------------------------------------------------------ 资产问题映射

function assetIssues(
  document: DraftDocument,
  asset: DraftAsset,
  result: AssetInspection | undefined,
  inspectionFailed: boolean,
): PublishIssue[] {
  const issues: PublishIssue[] = [];
  const declared = declaredRoles(asset);
  const actual = result === undefined ? [] : nonModelLayouts(result.layouts);
  // 检查本身失败时不做结构推导：没有实际布局可比，避免把「检查失败」误报成「布局不匹配」
  const diff = declared.length > 0 && !inspectionFailed ? compareLayouts(declared, actual) : {missing: [], extra: []};
  const hasDiff = diff.missing.length > 0 || diff.extra.length > 0;

  // 后端诊断优先列出（文件缺失/能力缺失/读取失败等），已由结构化差异覆盖的布局不一致不再重复
  for (const diagnostic of result?.diagnostics ?? []) {
    if (diagnostic.code === LAYOUT_MISMATCH_CODE && hasDiff) continue;
    issues.push({
      code: diagnostic.code,
      severity: diagnostic.severity === "warning" ? "warning" : "error",
      target: {section: "assets", assetId: asset.asset_id},
      params: {},
    });
  }

  for (const layout of diff.missing) {
    issues.push({
      code: LAYOUT_MISMATCH_CODE,
      severity: "error",
      target: {section: "assets", assetId: asset.asset_id, layout},
      params: {layout},
    });
  }
  for (const layout of diff.extra) {
    issues.push({
      code: LAYOUT_MISMATCH_CODE,
      severity: "error",
      target: {section: "assets", assetId: asset.asset_id, layout},
      params: {layout},
    });
  }

  // 未被引用的有效布局资产：仅当标准确实存在可引用位置时才判定（否则无从判断，不误报）
  if (
    asset.kind === "layout-template"
    && declared.length > 0
    && !hasDiff
    && !inspectionFailed
    && hasReferenceSources(document)
    && assetReferences(document, asset).length === 0
  ) {
    issues.push({
      code: UNREFERENCED_ASSET_CODE,
      severity: "warning",
      target: {section: "assets", assetId: asset.asset_id},
      params: {assetId: asset.asset_id},
    });
  }
  return issues;
}

// ------------------------------------------------------------ 门禁

/** 汇总检查报告为发布门禁：错误阻断、警告放行、检查失败单列并阻断。 */
export function buildPublishGate(report: PublishReport): PublishGate {
  const issues: PublishIssue[] = [
    ...report.structure.map(item => structureIssue(report.document, item)),
  ];
  const inspections = new Map(report.assets.map(item => [item.asset_id, item]));
  const failedAssets = new Set((report.inspectionFailures ?? []).map(item => item.assetId));
  for (const asset of report.document.assets) {
    issues.push(...assetIssues(report.document, asset, inspections.get(asset.asset_id), failedAssets.has(asset.asset_id)));
  }
  const blockingErrors = issues.filter(issue => issue.severity === "error");
  const warnings = issues.filter(issue => issue.severity === "warning");
  const inspectionFailures = report.inspectionFailures ?? [];
  return {
    blockingErrors,
    warnings,
    inspectionFailures,
    counts: {errors: blockingErrors.length, warnings: warnings.length, failures: inspectionFailures.length},
    canPublish: blockingErrors.length === 0 && inspectionFailures.length === 0,
  };
}

/** 检查域顺序（SPEC-DM-016 §9.1 的检查域）：左侧计数与右侧分组的共同顺序。 */
export const PUBLISH_SECTIONS: EditorSectionId[] = [
  "basic", "properties", "rules", "mapping", "composition", "assets", "publish",
];
