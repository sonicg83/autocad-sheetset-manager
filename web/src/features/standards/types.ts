// 标准前端契约（PLAN-DM-035 Task 7）：只建立生成契约的窄别名与 UI 判别联合，
// 不复制后端最终校验规则（标准 Schema 校验在应用/领域层，错误以稳定码返回）。
export type StartSurface = "welcome" | "standards" | "create-sheetset";

/** 新建草稿起点（Task 8 创建对话框）：空白 / 复制发布版本 / 从 DST 提取。 */
export type CreateMode = "blank" | "derive" | "from-dst";

export interface StandardIdentity {
  standardId: string;
  /** 服务端分配的整数发布版本；界面展示加 `v` 前缀。 */
  version: number;
}

export interface StandardSummary {
  source: "official" | "user";
  status: "published" | "draft";
  standard_id: string;
  /** 已发布为服务端分配的整数版本；草稿为 `null`。 */
  version: number | null;
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
  version: number;
  name: string;
  supported_cad_versions: string[];
  dependencies: StandardDependency[];
  /** 完整标准文档（派生草稿等场景需要）。 */
  document: Record<string, unknown>;
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
  version: number;
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

/** 本机模板受控复制：前端只传用户显式选择的来源路径，返回服务端生成的受控副本名。 */
export interface CopyAssetFileInput {
  draftId: string;
  sourcePath: string;
  /** 提供时后端复制后立即读取非 Model 布局；缺省只复制不读取。 */
  cadVersion?: string;
}

export interface CopiedAssetFile {
  path: string;
  /** 非 Model 布局名（保持文件内顺序与原名）；`layouts_error` 非空时为空数组。 */
  layouts: string[];
  /** 布局读取失败的稳定错误码；复制成功但读取失败不影响 `path`。 */
  layouts_error: string | null;
}

/** 草稿级保存：身份由草稿 ID 承载，文档身份必须等于草稿已存身份（F11）。 */
export interface SaveDraftInput {
  draftId: string;
  document: Record<string, unknown>;
}

export interface PublishInput {
  draftId: string;
}

export interface ImportPackageInput {
  path: string;
}

/** 导入预检（PLAN-DM-041 Task 5）：返回候选整数身份与可否导入。 */
export interface ImportPreviewInput {
  path: string;
}

export interface StandardExistingVersion {
  source: "official" | "user";
  version: number;
}

export interface ImportPreviewResult {
  preview_id: string | null;
  expires_at: string | null;
  standard_id: string;
  version: number;
  name: string;
  supported_cad_versions: string[];
  existing_versions: StandardExistingVersion[];
  diagnostics: StandardDiagnostic[];
  can_import: boolean;
}

/** 确认导入：只接受预检凭证（服务端不接受绕过预检的路径）。 */
export interface ConfirmImportInput {
  previewId: string;
}

export interface CreateDraftFromDstInput {
  dstPath: string;
}

export interface InspectAssetInput {
  draftId: string;
  assetId: string;
  cadVersion: string;
}
