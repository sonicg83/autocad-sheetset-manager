// 标准前端契约（PLAN-DM-035 Task 7）：只建立生成契约的窄别名与 UI 判别联合，
// 不复制后端最终校验规则（标准 Schema 校验在应用/领域层，错误以稳定码返回）。
export type StartSurface = "welcome" | "standards" | "create-sheetset";

export interface StandardIdentity {
  standardId: string;
  version: string;
}

export interface StandardSummary {
  source: "official" | "user";
  status: "published" | "draft";
  standard_id: string;
  version: string;
  name: string;
  draft_id: string | null;
}

export interface StandardDependency {
  extension_id: string;
  capability_id: string;
  min_version: string;
}

export interface StandardDetail {
  standard_id: string;
  version: string;
  name: string;
  supported_cad_versions: string[];
  dependencies: StandardDependency[];
}

export interface StandardDraft {
  draft_id: string;
  document: Record<string, unknown>;
}

/** DST 导入草稿；两个恒空数组是"不复制子集/图纸/外部引用"的契约证据。 */
export interface ImportedStandardDraft extends StandardDraft {
  subsets: string[];
  external_paths: string[];
}

export interface PublishedStandard {
  standard_id: string;
  version: string;
  name: string;
}

export type StandardDiagnosticSeverity = "error" | "warning" | "info";

export interface StandardDiagnostic {
  code: string;
  severity: StandardDiagnosticSeverity;
  message: string;
}

export interface AssetInspection {
  asset_id: string;
  kind: string;
  layouts: string[];
  diagnostics: StandardDiagnostic[];
}

export interface CreateDraftInput {
  draftId?: string;
  document: Record<string, unknown>;
}

export interface SaveDraftByIdentityInput {
  standardId: string;
  version: string;
  document: Record<string, unknown>;
}

export interface PublishInput {
  draftId: string;
}

export interface ImportPackageInput {
  path: string;
}

export interface CreateDraftFromDstInput {
  dstPath: string;
}

export interface InspectAssetInput {
  draftId: string;
  assetId: string;
  cadVersion: string;
}
