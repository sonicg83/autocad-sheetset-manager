export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly fields?: Record<string, string>, // 兼容：字符串型字段级错误（编辑器行内错误/摘要跳转消费）
    readonly fieldErrors?: Record<string, ApiFieldError>, // 结构化字段级错误（设置 PUT 422，PLAN-DM-021 Task 3）
  ) {
    super(message);
  }
}

// 结构化逐字段错误（ARCH-DM-005 §6.2）：code/message_key 稳定，params 只携带
// 结构化插值参数（禁止本地化 label 或完整句子）；message 为迁移期兼容中文。
export interface ApiFieldError {
  code: string;
  messageKey?: string;
  params?: Record<string, string | number | boolean | string[]>;
  message?: string;
}

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
    params: isPlainObject(value.params) ? value.params as ApiFieldError["params"] : undefined,
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
    throw new ApiError(body.message ?? body.detail ?? "请求失败", response.status, body.code, fields, fieldErrors);
  }
  return body as T;
}
