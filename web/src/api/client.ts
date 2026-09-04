export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly fields?: Record<string, string>, // 服务端字段级错误（编辑器行内错误/摘要跳转消费）
  ) {
    super(message);
  }
}

export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    throw new ApiError(body.message ?? body.detail ?? "请求失败", response.status, body.code, body.fields);
  }
  return body as T;
}
