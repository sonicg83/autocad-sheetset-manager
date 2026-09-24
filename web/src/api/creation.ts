// 创建草稿、标准候选与 XLSX 端点包装（PLAN-DM-036 Task 8 的前端窄包装）。
// 只做 URL/负载映射与类型断言：错误经 `request()` 统一转为 ApiError（`code` 为后端稳定
// 错误码，`message` 已按 message_key 本地化）。工作簿导入走独立的 multipart 请求，因为
// 整批被拒（422）时响应体还带 `diagnostics`（工作表/行/列定位），统一错误通道拿不到它。
import {localizedError, request} from "./client";
import {fetchStandardDetail} from "./standards";
import type {
  CreationApi,
  CreationDraftState,
  CreationGroupState,
  CreationIdentity,
  CreationImportDiagnostic,
  CreationImportInput,
  CreationImportOutcome,
  CreationSaveInput,
  CreationStandardCandidate,
  CreationStep,
} from "../features/creation/types";

const CREATION_STEPS: CreationStep[] = ["standard", "project", "groups", "review"];

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asStringRecord(value: unknown): Record<string, string> {
  if (typeof value !== "object" || value === null) return {};
  const record: Record<string, string> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (typeof item === "string") record[key] = item;
  }
  return record;
}

function asStep(value: unknown): CreationStep {
  return CREATION_STEPS.includes(value as CreationStep) ? (value as CreationStep) : "standard";
}

function toGroupState(raw: Record<string, unknown>): CreationGroupState {
  return {
    group_id: asString(raw["group_id"]),
    created_order: typeof raw["created_order"] === "number" ? raw["created_order"] : 0,
    title: asString(raw["title"]),
    count: typeof raw["count"] === "number" ? raw["count"] : 0,
    base_asset_id: asString(raw["base_asset_id"]),
    layout_asset_id: asString(raw["layout_asset_id"]),
    paper_layout: asString(raw["paper_layout"]),
    sheet_values: asStringRecord(raw["sheet_values"]),
  };
}

function toDraftState(body: unknown): CreationDraftState {
  const raw = (typeof body === "object" && body !== null ? body : {}) as Record<string, unknown>;
  const groups = Array.isArray(raw["groups"]) ? raw["groups"] : [];
  return {
    id: asString(raw["id"]),
    standard_id: asString(raw["standard_id"]),
    standard_version: asString(raw["standard_version"]),
    revision: typeof raw["revision"] === "number" ? raw["revision"] : 0,
    step: asStep(raw["step"]),
    target_path: asString(raw["target_path"]),
    sheetset_values: asStringRecord(raw["sheetset_values"]),
    groups: groups
      .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      .map(toGroupState),
  };
}

function toCandidate(raw: Record<string, unknown>): CreationStandardCandidate {
  const options = Array.isArray(raw["asset_options"]) ? raw["asset_options"] : [];
  return {
    standard_id: asString(raw["standard_id"]),
    version: asString(raw["version"]),
    name: asString(raw["name"]),
    supported_cad_versions: Array.isArray(raw["supported_cad_versions"])
      ? raw["supported_cad_versions"].filter((item): item is string => typeof item === "string")
      : [],
    available: raw["available"] === true,
    reasons: Array.isArray(raw["reasons"])
      ? raw["reasons"].filter((item): item is string => typeof item === "string")
      : [],
    asset_options: options
      .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      .map(item => ({
        asset_id: asString(item["asset_id"]),
        kind: asString(item["kind"]),
        label: asString(item["label"]),
        layouts: Array.isArray(item["layouts"])
          ? item["layouts"].filter((layout): layout is string => typeof layout === "string")
          : [],
      })),
  };
}

function importDiagnostics(body: Record<string, unknown> | null): CreationImportDiagnostic[] {
  const items = body !== null && Array.isArray(body["diagnostics"]) ? body["diagnostics"] : [];
  return items
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map(item => ({
      code: asString(item["code"]),
      message: asString(item["message"]),
      sheet: asString(item["sheet"]),
      row: typeof item["row"] === "number" ? item["row"] : null,
      column: typeof item["column"] === "string" ? item["column"] : null,
    }));
}

/** 后端错误负载 → 主提示：已知 code 按 message_key 本地化，未知 code 回退兼容文本。 */
function errorMessageOf(body: Record<string, unknown> | null, status: number): string {
  if (body === null) return `HTTP ${status}`;
  const messageKey = typeof body["message_key"] === "string" ? body["message_key"] : undefined;
  const params =
    typeof body["params"] === "object" && body["params"] !== null
      ? (body["params"] as Record<string, string | number | boolean | string[]>)
      : undefined;
  const fallback = [body["message"], body["detail"]].find(
    (value): value is string => typeof value === "string" && value !== "",
  );
  return localizedError(messageKey, params, fallback ?? `HTTP ${status}`);
}

async function jsonBody(response: Response): Promise<Record<string, unknown> | null> {
  try {
    const body = (await response.json()) as unknown;
    return typeof body === "object" && body !== null ? (body as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export function fetchCreationStandards(): Promise<CreationStandardCandidate[]> {
  return request<Record<string, unknown>[]>("/api/creation-drafts/standards").then(items =>
    items.map(toCandidate),
  );
}

/** 固定标准的完整文档：可输入属性与派生属性都从这份文档解析（不复制后端规则）。 */
export function fetchCreationStandardDocument(
  identity: CreationIdentity,
): Promise<Record<string, unknown>> {
  return fetchStandardDetail(identity).then(detail => detail.document);
}

export function createCreationDraft(identity: CreationIdentity): Promise<CreationDraftState> {
  return request<unknown>("/api/creation-drafts", {
    method: "POST",
    body: JSON.stringify({standard_id: identity.standardId, version: identity.version}),
  }).then(toDraftState);
}

export function fetchCreationDraft(draftId: string): Promise<CreationDraftState> {
  return request<unknown>(`/api/creation-drafts/${encodeURIComponent(draftId)}`).then(toDraftState);
}

export function saveCreationDraft(input: CreationSaveInput): Promise<CreationDraftState> {
  return request<unknown>(`/api/creation-drafts/${encodeURIComponent(input.draftId)}`, {
    method: "PUT",
    body: JSON.stringify({
      expected_revision: input.expectedRevision,
      step: input.step,
      target_path: input.targetPath,
      sheetset_values: input.sheetsetValues,
      groups: input.groups.map(group => ({
        group_id: group.group_id,
        created_order: group.created_order,
        title: group.title,
        count: group.count,
        base_asset_id: group.base_asset_id,
        layout_asset_id: group.layout_asset_id,
        paper_layout: group.paper_layout,
        sheet_values: group.sheet_values,
      })),
    }),
  }).then(toDraftState);
}

export function deleteCreationDraft(draftId: string): Promise<void> {
  return request<{status: string}>(`/api/creation-drafts/${encodeURIComponent(draftId)}`, {
    method: "DELETE",
  }).then(() => undefined);
}

/** XLSX 模板下载地址（GET，附件下载；带固定标准版本的受控模板）。 */
export function creationTemplateUrl(draftId: string): string {
  return `/api/creation-drafts/${encodeURIComponent(draftId)}/xlsx-template`;
}

/**
 * 全量覆盖导入：multipart 上传工作簿。整批被拒时返回 `ok:false` 与可定位诊断，
 * 调用方据此保持草稿与预览原样；网络或响应体异常同样按失败处理，不抛给调用方。
 */
export async function importCreationWorkbook(
  input: CreationImportInput,
): Promise<CreationImportOutcome> {
  const url = `/api/creation-drafts/${encodeURIComponent(input.draftId)}/xlsx-import?expected_revision=${input.expectedRevision}`;
  const form = new FormData();
  form.append("file", input.file);
  let response: Response;
  try {
    response = await fetch(url, {method: "POST", body: form});
  } catch (error) {
    return {ok: false, message: error instanceof Error ? error.message : String(error), diagnostics: []};
  }
  const body = await jsonBody(response);
  if (!response.ok) {
    return {
      ok: false,
      message: errorMessageOf(body, response.status),
      diagnostics: importDiagnostics(body),
    };
  }
  if (body === null) return {ok: false, message: `HTTP ${response.status}`, diagnostics: []};
  return {ok: true, draft: toDraftState(body)};
}

// 组合默认实现：store 注入点（createCreationStore）按 `CreationApi` 消费，
// 测试以同形替身替换（见 features/creation/store.test.ts 的 fakeCreationApi）。
// 有意不提供 `seed`：真实实现以空态起步，草稿由异步端点恢复。
export const creationApi: CreationApi = {
  listStandards: fetchCreationStandards,
  fetchStandardDocument: fetchCreationStandardDocument,
  createDraft: createCreationDraft,
  fetchDraft: fetchCreationDraft,
  saveDraft: saveCreationDraft,
  deleteDraft: deleteCreationDraft,
  templateUrl: creationTemplateUrl,
  importWorkbook: importCreationWorkbook,
};
