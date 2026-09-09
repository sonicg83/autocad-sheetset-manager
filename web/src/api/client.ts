import {ref} from "vue";
import {i18n} from "../i18n";

export type StructuredParams = Record<string, string | number | boolean | string[]>;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly fields?: Record<string, string>, // 兼容：字符串型字段级错误（编辑器行内错误/摘要跳转消费）
    readonly fieldErrors?: Record<string, ApiFieldError>, // 结构化字段级错误（设置 PUT 422，PLAN-DM-021 Task 3）
    readonly messageKey?: string, // 已知错误稳定文案键（PLAN-DM-021 Task 9 / I18N-11）
    readonly params?: StructuredParams, // 结构化插值参数（稳定值，禁止本地化 label/句子）
    readonly rawMessage?: string, // 后端兼容原始文本；已知错误不用于主提示，未知错误仅进诊断详情
  ) {
    super(message);
  }
}

// 结构化逐字段错误（ARCH-DM-005 §6.2）：code/message_key 稳定，params 只携带
// 结构化插值参数（禁止本地化 label 或完整句子）；message 为迁移期兼容中文。
export interface ApiFieldError {
  code: string;
  messageKey?: string;
  params?: StructuredParams;
  message?: string;
}

// 最近一次未知错误的原始诊断（I18N-11）：主提示只显示本地化摘要，
// 原始文本仅在 App.vue 的可展开“原始错误详情”中呈现，不进入正常界面翻译。
export const lastErrorDiagnostic = ref("");

function isFieldErrorPayload(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && "code" in value;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// 后端为 snake_case（message_key）；camelCase 兼容留作将来契约演进
function toFieldError(value: Record<string, unknown>): ApiFieldError {
  const messageKey = value.message_key ?? value.messageKey;
  return {
    code: String(value.code ?? ""),
    messageKey: typeof messageKey === "string" ? messageKey : undefined,
    params: isPlainObject(value.params) ? value.params as StructuredParams : undefined,
    message: typeof value.message === "string" ? value.message : undefined,
  };
}

// 422 逐字段错误双形态兼容：设置端点已升级为结构化对象（{code,message_key,...}），
// 其他端点（如草稿编辑器）仍为 {key: message} 字符串。统一拆出两种视图：
// fields（字符串消息，旧消费方不变）与 fieldErrors（结构化对象，设置对话框消费）。
function splitFieldErrors(errors: unknown): {
  fields?: Record<string, string>;
  fieldErrors?: Record<string, ApiFieldError>;
} {
  if (typeof errors !== "object" || errors === null) return {};
  const fields: Record<string, string> = {};
  const fieldErrors: Record<string, ApiFieldError> = {};
  let hasStructured = false;
  for (const [key, value] of Object.entries(errors as Record<string, unknown>)) {
    if (isFieldErrorPayload(value)) {
      hasStructured = true;
      const error = toFieldError(value);
      fieldErrors[key] = error;
      if (error.message !== undefined) fields[key] = error.message;
    } else if (typeof value === "string") {
      fields[key] = value;
    }
  }
  return {
    fields: Object.keys(fields).length > 0 ? fields : undefined,
    fieldErrors: hasStructured ? fieldErrors : undefined,
  };
}

// 统一错误渲染（I18N-11）：已知错误按 message_key+params 渲染并忽略兼容 message；
// 未知错误显示本地化摘要，原文只进可展开诊断详情（lastErrorDiagnostic）。
function renderError(
  messageKey: string | undefined,
  params: StructuredParams | undefined,
  raw: string,
): {display: string; diagnostic: string} {
  if (messageKey && i18n.global.te(messageKey)) {
    // 换新错误时清掉上一次未知错误的诊断；已知错误不重复展示原始文本
    lastErrorDiagnostic.value = "";
    return {display: i18n.global.t(messageKey, params ?? {}), diagnostic: raw};
  }
  lastErrorDiagnostic.value = raw;
  return {display: i18n.global.t("errors.ui.unknownSummary"), diagnostic: raw};
}

// Shell 桥已知错误渲染：有 message_key 按 key 渲染，否则回退原始文本
export function localizedError(
  messageKey: string | undefined,
  params: StructuredParams | undefined,
  fallback: string,
): string {
  if (messageKey && i18n.global.te(messageKey)) return i18n.global.t(messageKey, params ?? {});
  return fallback;
}

export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    // 字段级错误：设置 PUT 422 返回结构化对象（ARCH-DM-005 §6.2），
    // 草稿等端点仍返回 {key: message}；统一映射进 ApiError 供行内错误/摘要消费
    const {fields, fieldErrors} = splitFieldErrors(body.errors ?? body.fields);
    const messageKey = typeof body.message_key === "string" && body.message_key ? body.message_key : undefined;
    const params = isPlainObject(body.params) ? body.params as StructuredParams : undefined;
    const raw = [body.message, body.detail].find(value => typeof value === "string" && value) ?? "";
    const {display, diagnostic} = renderError(messageKey, params, raw);
    throw new ApiError(display, response.status, body.code, fields, fieldErrors, messageKey, params, diagnostic || undefined);
  }
  return body as T;
}
