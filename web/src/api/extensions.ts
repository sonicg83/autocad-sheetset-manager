// 扩展平台 API 客户端（PLAN-DM-020 Task 10 / ARCH-DM-006 §8）。
// 只封装列表、状态切换与单个扩展的设置读写；预览/执行/工作区偏好端点由 Task 11 的
// 页面状态所有者消费。错误经 api/client 的统一分流：已知 code 按 message_key 渲染，
// 未知 code 走 errors.ui.unknownSummary 摘要 + 可展开原始诊断。
import {request} from "./client";
import type {ExtensionSettingsView, ExtensionSettingsWrite, ExtensionSummary} from "./contracts";

// 已登记扩展列表（含停用/失败条目：宿主按 status 决定页面入口去留）；
// settings_contribution 为 null 表示未声明设置（设置中心不显示「配置」）
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

// 单个扩展的设置快照：value 为服务端持久值、effective_value 为 Provider 解析后的有效值，
// read_only/diagnostic_code 为服务端权威的只读保护（EXTENSION_SETTINGS_SCHEMA_NEWER）
export async function fetchExtensionSettings(extensionId: string): Promise<ExtensionSettingsView> {
  return request(`/api/extensions/${encodeURIComponent(extensionId)}/settings`);
}

// 保存单个扩展设置：schema_version 与 expected_revision 都取自服务端快照（乐观并发）。
// 409 不都是修订冲突：只有 isRevisionConflict()（useExtensionSettings）认下的码/参数才是，
// 其余 409（Provider 级拒绝，如模板重名）按普通保存失败呈现；422 = 字段级无效
// （params.field 定位到字段）；各路径都由 useExtensionSettings 收口。
export async function putExtensionSettings(extensionId: string, body: ExtensionSettingsWrite): Promise<ExtensionSettingsView> {
  return request(`/api/extensions/${encodeURIComponent(extensionId)}/settings`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
