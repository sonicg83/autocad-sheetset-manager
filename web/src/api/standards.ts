// 标准管理 API 包装（PLAN-DM-035 Task 6 生成契约的前端窄包装）。
// 只做 URL/负载映射与类型断言；错误经 request() 统一转为 ApiError
// （code 为后端稳定错误码，message 为兼容原始文本）。
import {request} from "./client";
import type {
  AssetInspection,
  CopiedAssetFile,
  CopyAssetFileInput,
  CreateDraftFromDstInput,
  CreateDraftInput,
  ImportedStandardDraft,
  InspectAssetInput,
  PublishInput,
  PublishedStandard,
  SaveDraftByIdentityInput,
  StandardDetail,
  StandardDraft,
  StandardIdentity,
  StandardSummary,
} from "../features/standards/types";
import type {StandardApi} from "../features/standards/store";

export function fetchStandards(): Promise<StandardSummary[]> {
  return request<StandardSummary[]>("/api/standards");
}

export function fetchStandardDetail(identity: StandardIdentity): Promise<StandardDetail> {
  return request<StandardDetail>(
    `/api/standards/${encodeURIComponent(identity.standardId)}/${encodeURIComponent(identity.version)}`,
  );
}

export function fetchStandardDraft(draftId: string): Promise<StandardDraft> {
  return request<StandardDraft>(`/api/standards/drafts/${encodeURIComponent(draftId)}`);
}

export function createStandardDraft(input: CreateDraftInput): Promise<StandardDraft> {
  return request<StandardDraft>("/api/standards/drafts", {
    method: "POST",
    body: JSON.stringify({draft_id: input.draftId ?? null, document: input.document}),
  });
}

export function saveStandardDraftByIdentity(input: SaveDraftByIdentityInput): Promise<StandardDraft> {
  return request<StandardDraft>(
    `/api/standards/${encodeURIComponent(input.standardId)}/${encodeURIComponent(input.version)}`,
    {method: "PUT", body: JSON.stringify(input.document)},
  );
}

export function deleteStandardDraft(draftId: string): Promise<void> {
  return request<{status: string}>(`/api/standards/drafts/${encodeURIComponent(draftId)}`, {
    method: "DELETE",
  }).then(() => undefined);
}

export function publishStandardDraft(input: PublishInput): Promise<PublishedStandard> {
  return request<PublishedStandard>(
    `/api/standards/drafts/${encodeURIComponent(input.draftId)}/publish`,
    {method: "POST"},
  );
}

export function importStandardPackage(input: {path: string}): Promise<PublishedStandard> {
  return request<PublishedStandard>("/api/standards/import", {
    method: "POST",
    body: JSON.stringify({path: input.path}),
  });
}

export function createStandardDraftFromDst(input: CreateDraftFromDstInput): Promise<ImportedStandardDraft> {
  return request<ImportedStandardDraft>("/api/standards/drafts/from-dst", {
    method: "POST",
    body: JSON.stringify({dst_path: input.dstPath}),
  });
}

export function inspectStandardAsset(input: InspectAssetInput): Promise<AssetInspection> {
  return request<AssetInspection>(
    `/api/standards/drafts/${encodeURIComponent(input.draftId)}/assets/${encodeURIComponent(input.assetId)}/inspect`,
    {method: "POST", body: JSON.stringify({cad_version: input.cadVersion})},
  );
}

/** 本机模板受控复制：后端把文件复制进草稿目录，只返回包内相对路径。 */
export function copyStandardAssetFile(input: CopyAssetFileInput): Promise<CopiedAssetFile> {
  return request<CopiedAssetFile>(
    `/api/standards/drafts/${encodeURIComponent(input.draftId)}/asset-files`,
    {method: "POST", body: JSON.stringify({source_path: input.sourcePath})},
  );
}

/** 标准包导出下载地址（GET /api/standards/{id}/{ver}/export，zip 下载）。 */
export function standardExportUrl(identity: StandardIdentity): string {
  return `/api/standards/${encodeURIComponent(identity.standardId)}/${encodeURIComponent(identity.version)}/export`;
}

// 组合默认实现：store 注入点（createStandardStore）按此契约消费，
// 测试以同形替身替换（见 store.test.ts 的 deferredStandardApi）。
export const standardsApi: StandardApi = {
  list: fetchStandards,
  fetchDetail: fetchStandardDetail,
  fetchDraft: fetchStandardDraft,
  createDraft: createStandardDraft,
  saveDraftByIdentity: saveStandardDraftByIdentity,
  createDraftFromDst: createStandardDraftFromDst,
  publish: publishStandardDraft,
  importPackage: importStandardPackage,
  deleteDraft: deleteStandardDraft,
  inspectAsset: inspectStandardAsset,
  copyAssetFile: copyStandardAssetFile,
};
