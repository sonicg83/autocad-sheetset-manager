// Builder API client（SPEC-DB-001 §11）。类型全部取自 openapi-typescript 从
// builder-web/src/api/openapi.json 生成的 schema.d.ts，不手写重复枚举。

import type {components} from "./schema";

export type ProjectStateResponse = components["schemas"]["ProjectStateResponse"];
export type ProjectModel = components["schemas"]["ProjectModel"];
export type DraftFieldsModel = components["schemas"]["DraftFieldsModel"];
export type DraftPatchRequest = components["schemas"]["DraftPatchRequest"];
export type ProjectCreateRequest = components["schemas"]["ProjectCreateRequest"];
export type AssetIntakeRequest = components["schemas"]["AssetIntakeRequest"];
export type AssetModel = components["schemas"]["AssetModel"];
export type AssetInspectRequest = components["schemas"]["AssetInspectRequest"];
export type AssetInspectionResponse = components["schemas"]["AssetInspectionResponse"];
export type CadCapabilitiesResponse = components["schemas"]["CadCapabilitiesResponse"];
export type DiagnosticModel = components["schemas"]["DiagnosticModel"];
export type PlanSubmitResponse = components["schemas"]["PlanSubmitResponse"];
export type PlanConfirmationResponse = components["schemas"]["PlanConfirmationResponse"];
export type BuildStartRequest = components["schemas"]["BuildStartRequest"];
export type BuildStatusResponse = components["schemas"]["BuildStatusResponse"];

/** 统一错误负载（§11）：code / message / field / recovery_action / details。 */
export class BuilderApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | null;
  readonly recoveryAction: string;

  constructor(
    status: number,
    code: string,
    message: string,
    field: string | null,
    recoveryAction: string,
  ) {
    super(message);
    this.name = "BuilderApiError";
    this.status = status;
    this.code = code;
    this.field = field;
    this.recoveryAction = recoveryAction;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: {"Content-Type": "application/json"},
      ...init,
    });
  } catch (cause) {
    throw new BuilderApiError(0, "NETWORK_ERROR", "无法连接 Builder 服务", null, "确认服务已启动后重试");
  }
  const text = await response.text();
  const payload = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) {
    const error = payload as
      | {code?: string; message?: string; field?: string | null; recovery_action?: string}
      | null;
    throw new BuilderApiError(
      response.status,
      error?.code ?? "UNKNOWN",
      error?.message ?? `请求失败（HTTP ${response.status}）`,
      error?.field ?? null,
      error?.recovery_action ?? "",
    );
  }
  return payload as T;
}

export {requestJson};

export const api = {
  createProject: (body: ProjectCreateRequest) =>
    requestJson<ProjectStateResponse>("/api/projects", {method: "POST", body: JSON.stringify(body)}),
  getCurrentProject: () => requestJson<ProjectStateResponse>("/api/projects/current"),
  patchDraft: (body: DraftPatchRequest) =>
    requestJson<ProjectStateResponse>("/api/projects/current/draft", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  createAsset: (body: AssetIntakeRequest) =>
    requestJson<AssetModel>("/api/assets", {method: "POST", body: JSON.stringify(body)}),
  inspectAsset: (assetId: string, body: AssetInspectRequest) =>
    requestJson<AssetInspectionResponse>(
      `/api/assets/${encodeURIComponent(assetId)}/inspect`,
      {method: "POST", body: JSON.stringify(body)},
    ),
  getCadabilities: () => requestJson<CadCapabilitiesResponse>("/api/cadabilities"),
  // 步骤 5～6（Task 9 接线，§5/§6/§11）
  submitPlan: () => requestJson<PlanSubmitResponse>("/api/plans", {method: "POST"}),
  confirmPlan: (planId: string) =>
    requestJson<PlanConfirmationResponse>(`/api/plans/${encodeURIComponent(planId)}/confirm`, {method: "POST"}),
  startBuild: (body: BuildStartRequest) =>
    requestJson<BuildStatusResponse>("/api/builds", {method: "POST", body: JSON.stringify(body)}),
  getBuild: (buildId: string) =>
    requestJson<BuildStatusResponse>(`/api/builds/${encodeURIComponent(buildId)}`),
  cancelBuild: (buildId: string) =>
    requestJson<BuildStatusResponse>(`/api/builds/${encodeURIComponent(buildId)}/cancel`, {method: "POST"}),
};
