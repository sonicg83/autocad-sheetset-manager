// 扩展平台 API 客户端（PLAN-DM-020 Task 10 / ARCH-DM-006 §8）。
// 只封装列表与状态切换；预览/执行/设置/偏好端点由 Task 11 的页面状态所有者消费。
// 错误经 api/client 的统一分流：已知 code 按 message_key 渲染，未知 code 走
// errors.ui.unknownSummary 摘要 + 可展开原始诊断。
import {request} from "./client";
import type {ExtensionSummary} from "./contracts";

// 已登记扩展列表（含停用/失败条目：宿主按 status 决定页面入口去留）
export async function listExtensions(): Promise<ExtensionSummary[]> {
  return request("/api/extensions");
}

// 启用/停用扩展：成功返回更新后的摘要（status/enabled 为服务端权威值）
export async function patchExtensionState(extensionId: string, enabled: boolean): Promise<ExtensionSummary> {
  return request(`/api/extensions/${encodeURIComponent(extensionId)}/state`, {
    method: "PATCH",
    body: JSON.stringify({enabled}),
  });
}
