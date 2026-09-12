// 扩展清单 e2e 夹具（PLAN-DM-020 Task 10 / PLAN-DM-022 Task 4 从 extensions-settings.spec.ts 提取）。
// 契约红线：/api/extensions 必须 mock——真实后端会写用户 .dst-manager-data/dst-manager.db
// 的 extension_states，禁止在生产/测试混用下真停用扩展。列表可变（PATCH 后更新），
// 以便断言宿主按最新状态收敛标签与开关；/api/settings 与 /api/about 仍走真实后端。
import type {Page} from "@playwright/test";

// 与后端 ExtensionSummaryModel 契约同构的最小摘要（name_key 指向真实清单键）。
// 默认声明图纸目录的 custom 设置——这正是生产固定索引（manifest.yaml）的事实：
// 声明设置时卡片动作行出现「配置」，未声明（settings_contribution: null）时不出现（SC-17）。
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
    settings_contribution: {presentation: "custom", route_key: "sheet-catalog-settings"},
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

// ---- 扩展设置 mock（PLAN-DM-025 Task 7 / SPEC-DM-011 SC-17）----
// 生产固定索引只登记图纸目录一条 custom 声明（R5）：generated 场景必须由本夹具装配，
// 不得向 src/dst_manager/extensions/builtin/index.py 新增扩展。
// GET/PUT /api/extensions/{id}/settings 同形复刻后端契约：PUT 先核 schema_version，
// 再核 Provider 约束（越界/超长拒绝并定位字段、绝不截断），最后按 expected_revision
// 做乐观并发（冲突 409 + params 的 expected/current 修订），成功后就地推进修订。

/** generated 场景的虚构扩展 ID（不在生产固定索引里，见 R5）。 */
export const GENERATED_EXTENSION_ID = "demo.frame-update";

/** generated 字段项：控件词表是封闭的（boolean/integer/number/string/enum）。 */
export interface GeneratedSettingsItem {
  key: string;
  label_key: string;
  description_key: string | null;
  order: number;
  control: string;
  default: unknown;
  nullable: boolean;
  min_value: number | null;
  max_value: number | null;
  options: string[];
  max_length: number | null;
}

/** 字段顺序由后端合并后给出，前端不得重排：这里即服务端返回顺序（order 1..5）。 */
export function generatedSettingsItems(): GeneratedSettingsItem[] {
  const base = {nullable: false, min_value: null, max_value: null, options: [] as string[], max_length: null};
  return [
    {key: "frame_block_prefix", label_key: "图框块名前缀", description_key: "写入图框块名的固定前缀", order: 1, control: "string", default: "TK-", ...base, max_length: 8},
    {key: "batch_limit", label_key: "单批处理上限", description_key: null, order: 2, control: "integer", default: 50, ...base, min_value: 1, max_value: 200},
    {key: "write_back_titleblock", label_key: "回写标题栏", description_key: null, order: 3, control: "boolean", default: true, ...base},
    {key: "ratio_threshold", label_key: "比例容差", description_key: null, order: 4, control: "number", default: 0.5, ...base, min_value: 0, max_value: 1},
    {key: "conflict_strategy", label_key: "属性冲突处理", description_key: null, order: 5, control: "enum", default: "ask", ...base, options: ["skip", "overwrite", "ask"]},
  ];
}

export interface ExtensionSettingsMock {
  gets: number;
  puts: {schema_version: number; expected_revision: number; value: Record<string, unknown>}[];
  /** 置 true 后所有后续 GET 都以 500 失败（覆盖“只读判定不得依赖刷新”的场景） */
  failGets: boolean;
  /** 置 true 后所有后续 PUT 都以 500 失败（覆盖非字段级保存失败横幅的场景） */
  failPuts: boolean;
  /**
   * 修订冲突时服务端返回的稳定码（默认为线上设置 PUT 的 EXTENSION_SETTINGS_INVALID）。
   * 用例可改成另一个已登记码，以证明横幅是“原样透传服务端响应”而不是写死字面量。
   */
  conflictCode: string;
  /** 服务端当前快照：测试可在两次请求之间直接推进 revision 模拟“另一窗口已保存” */
  server: {
    schema_version: number;
    revision: number;
    value: Record<string, unknown>;
    read_only: boolean;
    diagnostic_code: string | null;
    items: GeneratedSettingsItem[];
  };
}

function defaultZeroValue(items: GeneratedSettingsItem[]): Record<string, unknown> {
  return Object.fromEntries(items.map(item => [item.key, item.default]));
}

// Provider 校验的最小同构：整数越界与字符串超长拒绝并定位字段（不改写用户输入）
function providerFieldError(
  items: GeneratedSettingsItem[],
  value: Record<string, unknown>,
): {field: string; limit: number; actual: number} | null {
  for (const item of items) {
    const current = value[item.key];
    if (item.control === "integer" || item.control === "number") {
      const numeric = typeof current === "number" ? current : Number(current);
      if (!Number.isFinite(numeric)) return {field: item.key, limit: item.max_value ?? 0, actual: 0};
      if (item.min_value !== null && numeric < item.min_value) return {field: item.key, limit: item.min_value, actual: numeric};
      if (item.max_value !== null && numeric > item.max_value) return {field: item.key, limit: item.max_value, actual: numeric};
    }
    if (item.control === "string" && item.max_length !== null && typeof current === "string" && current.length > item.max_length) {
      return {field: item.key, limit: item.max_length, actual: current.length};
    }
  }
  return null;
}

export async function installExtensionSettings(page: Page, options: {
  schemaVersion?: number;
  revision?: number;
  value?: Record<string, unknown>;
  readOnly?: boolean;
  items?: GeneratedSettingsItem[];
  conflictCode?: string;
} = {}): Promise<ExtensionSettingsMock> {
  const items = options.items ?? generatedSettingsItems();
  const state: ExtensionSettingsMock = {
    gets: 0,
    puts: [],
    failGets: false,
    failPuts: false,
    conflictCode: options.conflictCode ?? "EXTENSION_SETTINGS_INVALID",
    server: {
      schema_version: options.schemaVersion ?? 1,
      revision: options.revision ?? 0,
      value: options.value ?? defaultZeroValue(items),
      read_only: options.readOnly ?? false,
      diagnostic_code: options.readOnly === true ? "EXTENSION_SETTINGS_SCHEMA_NEWER" : null,
      items,
    },
  };
  const view = () => ({
    schema_version: state.server.schema_version,
    revision: state.server.revision,
    value: state.server.value,
    effective_value: state.server.value,
    read_only: state.server.read_only,
    diagnostic_code: state.server.diagnostic_code,
    items: state.server.items,
  });
  await page.route("**/api/extensions/*/settings", async route => {
    if (route.request().method() === "GET") {
      state.gets += 1;
      if (state.failGets) return route.fulfill({status: 500, json: {code: "INTERNAL_ERROR", message: "boom"}});
      return route.fulfill({json: view()});
    }
    const body = (await route.request().postDataJSON()) as ExtensionSettingsMock["puts"][number];
    state.puts.push(body);
    // 非字段级保存失败（5xx）：前端须就地横幅、保留输入并保持保存可用
    if (state.failPuts) return route.fulfill({status: 500, json: {code: "INTERNAL_ERROR", message: "boom"}});
    // 高版本只读：PUT 一律 409 拒绝覆盖（ARCH-DM-006 §8.1）
    if (state.server.read_only) {
      return route.fulfill({
        status: 409,
        json: {code: "EXTENSION_SETTINGS_SCHEMA_NEWER", message_key: "errors.extension.schemaNewer", params: {extension_id: "demo.frame-update"}, message: "已存设置 schema 更高，只读保留"},
      });
    }
    if (body.schema_version !== state.server.schema_version) {
      return route.fulfill({
        status: 422,
        json: {code: "EXTENSION_SETTINGS_INVALID", message_key: "errors.extension.settingsInvalid", params: {settings_schema: state.server.schema_version, submitted: body.schema_version}, message: "设置 schema 版本不匹配"},
      });
    }
    const invalid = providerFieldError(items, body.value);
    if (invalid !== null) {
      return route.fulfill({
        status: 422,
        json: {code: "EXTENSION_SETTINGS_INVALID", message_key: "errors.extension.settingsInvalid", params: invalid, message: "超出 Provider 声明的字段约束"},
      });
    }
    if (body.expected_revision !== state.server.revision) {
      return route.fulfill({
        status: 409,
        json: {code: state.conflictCode, message_key: "errors.extension.settingsInvalid", params: {expected_revision: body.expected_revision, current_revision: state.server.revision}, message: "设置已被其他保存更新"},
      });
    }
    state.server = {...state.server, revision: state.server.revision + 1, value: body.value};
    return route.fulfill({json: view()});
  });
  return state;
}
