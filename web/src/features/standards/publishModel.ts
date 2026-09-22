// 发布检查模型（PLAN-DM-038 Task 5 / SPEC-DM-017 §7–§8）：纯函数门禁，无 Vue 与网络依赖。
// 职责边界：
// - 把草稿发布诊断（`publishIssues`）映射到六个编辑分区与可聚焦目标；
// - 把后端资产检查结果与前端可推导的布局严格差异、未引用资产警告归一为发布问题；
// - 判定 `canPublish`：错误与「检查本身失败」都阻断，warning 不阻断。
// 后端仍是发布门禁的权威：这里只做发布前的就地提示，同一问题在后端返回时使用同一稳定码。
// 模型不持有用户可见文案：只返回稳定码与结构化插值参数，由视图经语言包渲染。
import {
  type DraftAsset,
  type DraftDiagnostic,
  type DraftDocument,
  type EditorSectionId,
  isDerivedProperty,
  propertyById,
  publishIssues,
} from "./draftModel";
import type {AssetInspection} from "./types";

/** 图幅匹配必须排除的模型空间布局（多文件聚合结果里同样排除）。 */
export const MODEL_LAYOUT_NAME = "Model";

/** 布局严格不一致的稳定码（与后端 `standard_assets._layout_mismatch` 同码）。 */
export const LAYOUT_MISMATCH_CODE = "STANDARD_LAYOUT_NAME_MISMATCH";

/** 未被标准取值引用的有效资产：警告，不阻断发布。 */
export const UNREFERENCED_ASSET_CODE = "STANDARD_ASSET_UNREFERENCED";

export type PublishSeverity = "error" | "warning";

export interface PublishTarget {
  section: EditorSectionId;
  /** 普通/派生属性行定位（属性稳定 ID）。 */
  propertyId?: string;
  /** 命名或组合令牌片段序号。 */
  segmentIndex?: number;
  /** 映射行定位（源枚举项 ID）。 */
  itemId?: string;
  assetId?: string;
  layout?: string;
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

export type ReferenceKind = "property-enum" | "mapping-target" | "segment-literal";

export interface AssetReference {
  role: string;
  kind: ReferenceKind;
  /** 引用位置标识（属性 ID 或 DWG 命名模板）。 */
  ref: string;
  value: string;
}

/** 标准里可能引用图幅取值的所有位置；为空表示本草案无法判定引用关系。 */
export function hasReferenceSources(document: DraftDocument): boolean {
  if (document.properties.some(property => property.kind === "enum" && property.enum_items.length > 0)) {
    return true;
  }
  if (document.properties.some(property => property.kind === "mapping" && property.mapping.length > 0)) {
    return true;
  }
  return document.dwg_naming.segments.some(segment => segment.literal !== undefined);
}

/** 资产声明的图幅在标准中被引用的位置（枚举项、映射目标、组合与命名固定文本）。 */
export function assetReferences(document: DraftDocument, asset: DraftAsset): AssetReference[] {
  const roles = declaredRoles(asset);
  if (roles.length === 0) return [];
  const references: AssetReference[] = [];
  for (const role of roles) {
    for (const property of document.properties) {
      if (property.kind === "enum" && property.enum_items.some(item => item.value === role)) {
        references.push({role, kind: "property-enum", ref: property.property_id, value: role});
      }
      if (property.kind === "mapping" && property.mapping.some(row => row.value === role)) {
        references.push({role, kind: "mapping-target", ref: property.property_id, value: role});
      }
      if (property.kind === "composition" && property.segments.some(segment => segment.literal === role)) {
        references.push({role, kind: "segment-literal", ref: property.property_id, value: role});
      }
    }
    if (document.dwg_naming.segments.some(segment => segment.literal === role)) {
      references.push({role, kind: "segment-literal", ref: "dwgNaming", value: role});
    }
  }
  return references;
}

// ------------------------------------------------------------ 诊断映射

function sectionOfDiagnostic(document: DraftDocument, diagnostic: DraftDiagnostic): EditorSectionId {
  switch (diagnostic.owner) {
    case "asset":
      return "assets";
    case "dwgNaming":
      return "dwgNaming";
    case "document":
      return "basic";
    default: {
      const property = propertyById(document, diagnostic.propertyId ?? "");
      return property !== undefined && isDerivedProperty(property) ? "derived" : "ordinary";
    }
  }
}

/** 发布诊断 → 发布问题：按诊断归属决定检查域，令牌/枚举项级诊断保留定位。 */
export function issueOf(document: DraftDocument, diagnostic: DraftDiagnostic): PublishIssue {
  const section = sectionOfDiagnostic(document, diagnostic);
  const target: PublishTarget = {section};
  const params: Record<string, string | number> = {};
  if (diagnostic.propertyId !== undefined) {
    target.propertyId = diagnostic.propertyId;
    params.propertyId = diagnostic.propertyId;
    const property = propertyById(document, diagnostic.propertyId);
    if (property !== undefined) params.propertyName = property.name || diagnostic.propertyId;
  }
  if (diagnostic.segmentIndex !== undefined) {
    target.segmentIndex = diagnostic.segmentIndex;
    params.segmentIndex = diagnostic.segmentIndex + 1;
  }
  if (diagnostic.itemId !== undefined) {
    target.itemId = diagnostic.itemId;
    params.itemId = diagnostic.itemId;
  }
  if (diagnostic.assetId !== undefined) {
    target.assetId = diagnostic.assetId;
    params.assetId = diagnostic.assetId;
  }
  return {
    code: diagnostic.code,
    severity: diagnostic.severity,
    target,
    params,
  };
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
      params: {assetId: asset.asset_id},
    });
  }

  for (const layout of [...diff.missing, ...diff.extra]) {
    issues.push({
      code: LAYOUT_MISMATCH_CODE,
      severity: "error",
      target: {section: "assets", assetId: asset.asset_id, layout},
      params: {assetId: asset.asset_id, layout},
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

/** 汇总发布诊断与资产检查为发布门禁：错误阻断、警告放行、检查失败单列并阻断。 */
export function buildPublishGate(report: PublishReport): PublishGate {
  const issues: PublishIssue[] = publishIssues(report.document).map(diagnostic =>
    issueOf(report.document, diagnostic),
  );
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

/** 检查域顺序（SPEC-DM-017 §2 的六分区）：左侧计数与右侧分组的共同顺序。 */
export const PUBLISH_SECTIONS: EditorSectionId[] = [
  "basic", "ordinary", "derived", "dwgNaming", "assets", "publish",
];
