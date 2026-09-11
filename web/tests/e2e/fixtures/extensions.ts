// 扩展清单 e2e 夹具（PLAN-DM-020 Task 10 / PLAN-DM-022 Task 4 从 extensions-settings.spec.ts 提取）。
// 契约红线：/api/extensions 必须 mock——真实后端会写用户 .dst-manager-data/dst-manager.db
// 的 extension_states，禁止在生产/测试混用下真停用扩展。列表可变（PATCH 后更新），
// 以便断言宿主按最新状态收敛标签与开关；/api/settings 与 /api/about 仍走真实后端。
import type {Page} from "@playwright/test";

// 与后端 ExtensionSummaryModel 契约同构的最小摘要（name_key 指向真实清单键）
export function extensionSummary(overrides: Record<string, unknown> = {}) {
  return {
    extension_id: "dst-manager.sheet-catalog",
    version: "0.1.0",
    name_key: "extensions.sheetCatalog.name",
    description_key: "extensions.sheetCatalog.description",
    status: "AVAILABLE",
    enabled: true,
    error_code: null,
    actions: [],
    ui_contributions: [{contribution_id: "workspace-page", kind: "workspace_page", route_key: "sheet-catalog"}],
    ...overrides,
  };
}

export interface ExtensionsState {list: unknown[]; patchBodies: unknown[]; listRequests: number}

export async function installExtensions(page: Page, initial: unknown[]): Promise<ExtensionsState> {
  const state: ExtensionsState = {list: initial, patchBodies: [], listRequests: 0};
  await page.route("**/api/extensions", route => {
    state.listRequests += 1;
    return route.fulfill({json: state.list});
  });
  await page.route("**/api/extensions/*/state", async route => {
    const body = (await route.request().postDataJSON()) as {enabled: boolean};
    state.patchBodies.push(body);
    const id = new URL(route.request().url()).pathname.split("/").at(-2)!;
    state.list = (state.list as Record<string, unknown>[]).map(ext =>
      ext.extension_id === id ? {...ext, enabled: body.enabled, status: body.enabled ? "AVAILABLE" : "DISABLED"} : ext);
    return route.fulfill({json: (state.list as Record<string, unknown>[]).find(ext => ext.extension_id === id)});
  });
  return state;
}
