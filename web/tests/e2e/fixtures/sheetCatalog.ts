// 图纸目录页公共 e2e 夹具（PLAN-DM-020 Task 11 / SPEC-DM-012）。
// 只含虚构路径与假壳/假路由：工作区、扩展设置/偏好、预览/执行动作、Artifact 查询
// 全部经 page.route 模拟；预览模拟按 SPEC §8.1 的最小语义（缺定义阻断、缺值警告、
// 前 20 行 + 总数、递增摘要）计算，不复制后端完整校验规则。假桥持有
// request_extension_save / open_workspace_folder 的可编程行为与调用记录。
import {expect, type Page} from "@playwright/test";

export const EXTENSION_ID = "dst-manager.sheet-catalog";
export const WORKSPACE_ID = "workspace-1";

export interface CatalogColumn {
  column_id: string;
  header: string;
  expression: string;
}
export interface CatalogTemplate {
  template_id: string;
  name: string;
  schema_version: number;
  columns: CatalogColumn[];
}

export type SaveDialogMode = "grant" | "cancel" | "error";
export type ExecuteMode = "ok" | "repreviewRequired" | "saveGrantInvalid" | "destinationChanged" | "writeFailed" | "digestMismatch";
export type PutSettingsMode = "ok" | "conflict" | "duplicate" | "limit";

export type SheetCatalogFixtureOptions = {
  sheetCount?: number;                          // 图纸总数，默认 25（预览 20 行 < 总数）
  empty?: boolean;                              // 空图纸集（0 张图纸，可导出）
  sheetsetProperties?: Record<string, string>;  // 图纸集作用域自定义属性（定义 + 全量值）
  sheetProperties?: Record<string, string>;     // 图纸作用域自定义属性（定义 + 全量值）
  // 缺值警告场景：fromIndex 起的图纸该属性置空串；values 提供按图纸索引的完整值
  // 序列（空串 = 缺值，G8 同冻结 Demo 数据用）
  sheetPropertyValueOverrides?: {name: string; fromIndex?: number; values?: string[]}[];
  sheetTitles?: string[];                       // 按索引覆盖图纸标题（G8 同冻结 Demo 数据用）
  dstPath?: string;                             // 覆盖 DST 路径（顶栏工作区标识）
  sheetSetName?: string;                        // 覆盖图纸集名称
  userTemplates?: CatalogTemplate[];            // 预置用户模板（设置 GET 返回）
  preferenceTemplateId?: string | null;         // 预置"上次选中的已保存模板"偏好
  noShell?: boolean;                            // 不注入 pywebview 桥（无桌面壳）
  saveDialog?: SaveDialogMode;                  // 假桥另存为行为，默认 grant
  saveDialogError?: string;                     // saveDialog=error 时的稳定 code
  executeMode?: ExecuteMode;                    // 执行响应行为，默认 ok
  putSettingsMode?: PutSettingsMode;            // 模板设置 PUT 行为，默认 ok
};

export type CatalogControls = {
  saveDialog: SaveDialogMode;
  saveDialogError?: string;
  executeMode: ExecuteMode;
  putSettingsMode: PutSettingsMode;
};

export type SheetCatalogState = {
  controls: CatalogControls;
  revision: number;
  settingsValue: {schema_version: number; user_templates: CatalogTemplate[]};
  preferencePuts: {template_id?: string}[];
  // 每次模板设置 PUT 携带的 expected_revision（冲突恢复/另存为语义断言用）
  putExpectedRevisions: number[];
  previewRequests: {workspace_id: string; base_revision_id: string; template: unknown; preview_digest?: string}[];
  executeRequests: Record<string, unknown>[];
  lastDigest: string | null;
  artifacts: Map<string, Record<string, unknown>>;
  // 扩展启停状态：必须由夹具接管（见 installSheetCatalogFixture 的 /state 路由）
  extensionEnabled: boolean;
  extensionPatchBodies: unknown[];
};

// 假桥调用记录保存在浏览器侧（window.__catalogBridge）：跨 Node/浏览器边界统一经本 helper 读取
export async function readBridgeCalls(page: Page): Promise<{saveRequests: {extension_id: string; action_id: string; workspace_id: string}[]; openFolderCalls: string[]; artifactFolderCalls: {extension_id: string; artifact_id: string}[]}> {
  return page.evaluate(() => {
    const calls = (window as unknown as {__catalogBridge?: {saveRequests: unknown[]; openFolderCalls: string[]; artifactFolderCalls: unknown[]}}).__catalogBridge;
    return {
      saveRequests: (calls?.saveRequests ?? []) as {extension_id: string; action_id: string; workspace_id: string}[],
      openFolderCalls: calls?.openFolderCalls ?? [],
      artifactFolderCalls: (calls?.artifactFolderCalls ?? []) as {extension_id: string; artifact_id: string}[],
    };
  });
}

const BUILTIN_SHEET_FIELDS = ["number", "title", "file_name"];

let uuidCounter = 0;
export function fakeUuid(): string {
  uuidCounter += 1;
  const hex = (uuidCounter * 2654435761 % 0xffffffff).toString(16).padStart(8, "0").repeat(4);
  return `${hex.slice(0, 8)}-4${hex.slice(8, 11)}-8${hex.slice(11, 14)}-${hex.slice(14, 18)}-${hex.slice(18, 30)}`;
}

function pad3(index: number): string {
  return String(index + 1).padStart(3, "0");
}

function buildWorkspace(options: SheetCatalogFixtureOptions) {
  const sheetsetProperties = options.sheetsetProperties ?? {设计院: "中元设计院", "项目 名称": "示范工程"};
  const sheetProperties = options.sheetProperties ?? {专业代码: "RQ"};
  const overrides = options.sheetPropertyValueOverrides ?? [];
  const count = options.empty ? 0 : options.sheetCount ?? 25;
  const sheets = Array.from({length: count}, (_, index) => {
    const custom: Record<string, string> = {...sheetProperties};
    for (const override of overrides) {
      if (override.values) custom[override.name] = override.values[index] ?? "";
      else if (index >= (override.fromIndex ?? 0)) custom[override.name] = "";
    }
    const number = pad3(index);
    return {
      id: `sheet-${number}`,
      number,
      title: options.sheetTitles?.[index] ?? `图纸 ${number}`,
      custom_properties: custom,
      layout: {
        file_name: `C:\\虚构工程\\${number}.dwg`,
        relative_file_name: `.\\${number}.dwg`,
        resolved_path: `C:\\虚构工程\\${number}.dwg`,
        layout_name: number,
        handle: `H${number}`,
      },
    };
  });
  return {
    id: WORKSPACE_ID,
    revision_id: "revision-1",
    dst_path: options.dstPath ?? "C:\\虚构工程\\图纸集.dst",
    sheet_set: {
      name: options.sheetSetName ?? "测试图纸集",
      sheet_count: count,
      subset_count: 1,
      custom_properties: {...sheetsetProperties},
      property_definitions: [
        ...Object.keys(sheetsetProperties).map(name => ({name, type: "sheetset", default_value: ""})),
        ...Object.keys(sheetProperties).map(name => ({name, type: "sheet", default_value: ""})),
      ],
      subsets: [{
        id: "subset-1", name: "第一册", title: "第一册", number_range: count ? `001-${pad3(count - 1)}` : "001-001",
        display_name: "第一册", sheets,
      }],
    },
    diagnostics: [],
  };
}

// 按表达式文本求值单张图纸行（最小语义：字段引用替换为值，其余文字原样保留）
function evaluateRow(expression: string, sheet: {number: string; title: string; custom_properties: Record<string, string>}, sheetsetProperties: Record<string, string>): string {
  const fieldRe = /\{(sheetset|sheet)(?:\.([^{}]+?)|\["((?:[^"\\]|\\.)*)"\])\}/g;
  let result = "";
  let cursor = 0;
  for (const match of expression.matchAll(fieldRe)) {
    result += expression.slice(cursor, match.index);
    cursor = match.index + match[0].length;
    const scope = match[1];
    let name = match[2] ?? JSON.parse(`"${match[3]}"`) as string;
    let value = "";
    if (scope === "sheetset") {
      value = Object.entries(sheetsetProperties).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? "";
    } else if (BUILTIN_SHEET_FIELDS.includes(name.toLowerCase())) {
      name = name.toLowerCase();
      value = name === "number" ? sheet.number : name === "title" ? sheet.title : sheet.number + ".dwg";
    } else {
      value = Object.entries(sheet.custom_properties).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? "";
    }
    result += value;
  }
  return result + expression.slice(cursor).replace(/\{\{/g, "{").replace(/\}\}/g, "}");
}

function buildPreviewResponse(body: {template: {columns: CatalogColumn[]}}, workspace: ReturnType<typeof buildWorkspace>, state: SheetCatalogState) {
  const sheetsetProperties = workspace.sheet_set.custom_properties;
  const sheetsetDefs = Object.keys(sheetsetProperties);
  const sheetDefs = Object.keys(workspace.sheet_set.subsets[0]?.sheets[0]?.custom_properties ?? {});
  const fieldCatalog = {
    sheetset: sheetsetDefs.map(name => ({scope: "sheetset", canonical_name: name, builtin: false})),
    sheet: [
      ...BUILTIN_SHEET_FIELDS.map(name => ({scope: "sheet", canonical_name: name, builtin: true})),
      ...sheetDefs.map(name => ({scope: "sheet", canonical_name: name, builtin: false})),
    ],
  };
  const errors: Record<string, unknown>[] = [];
  const warnings: Record<string, unknown>[] = [];
  const seenHeaders = new Map<string, string>();
  const sheets = workspace.sheet_set.subsets[0]?.sheets ?? [];
  for (const column of body.template.columns ?? []) {
    const folded = column.header.toLowerCase();
    const duplicate = seenHeaders.get(folded);
    if (duplicate !== undefined) {
      errors.push({code: "SHEET_CATALOG_COLUMN_DUPLICATE", message_key: "errors.sheetCatalog.columnDuplicate", params: {header: column.header}, column_id: null, source_position: null});
    }
    seenHeaders.set(folded, column.header);
    for (const match of column.expression.matchAll(/\{(sheetset|sheet)(?:\.([^{}]+?)|\["((?:[^"\\]|\\.)*)"\])\}/g)) {
      const scope = match[1] as "sheetset" | "sheet";
      const name = match[2] ?? JSON.parse(`"${match[3]}"`) as string;
      const lower = name.toLowerCase();
      const defined = scope === "sheetset"
        ? sheetsetDefs.some(def => def.toLowerCase() === lower)
        : BUILTIN_SHEET_FIELDS.includes(lower) || sheetDefs.some(def => def.toLowerCase() === lower);
      if (!defined) {
        errors.push({code: "SHEET_CATALOG_FIELD_UNDEFINED", message_key: "errors.sheetCatalog.fieldUndefined", params: {scope, name}, column_id: column.column_id, source_position: null});
        continue;
      }
      const emptyCount = sheets.filter(sheet => {
        if (scope === "sheetset") return (Object.entries(sheetsetProperties).find(([key]) => key.toLowerCase() === lower)?.[1] ?? "") === "";
        if (BUILTIN_SHEET_FIELDS.includes(lower)) return false;
        return (Object.entries(sheet.custom_properties).find(([key]) => key.toLowerCase() === lower)?.[1] ?? "") === "";
      }).length;
      if (emptyCount > 0) {
        warnings.push({code: "SHEET_CATALOG_VALUE_MISSING", message_key: "errors.sheetCatalog.valueMissing", params: {scope, name, sheet_count: emptyCount}, column_id: null, source_position: null});
      }
    }
  }
  const executable = errors.length === 0;
  const rows = executable
    ? sheets.slice(0, 20).map(sheet => body.template.columns.map(column => evaluateRow(column.expression, sheet, sheetsetProperties)))
    : [];
  return {
    normalized_template: {template_id: null, name: "e2e", schema_version: 1, columns: body.template.columns ?? []},
    field_catalog: fieldCatalog,
    errors,
    warnings,
    rows,
    total_rows: sheets.length,
    preview_digest: `digest-${state.previewRequests.length + 1}`,
    executable,
  };
}

export async function installSheetCatalogFixture(page: Page, options: SheetCatalogFixtureOptions = {}): Promise<{state: SheetCatalogState}> {
  const workspace = buildWorkspace(options);
  const controls: CatalogControls = {
    saveDialog: options.saveDialog ?? "grant",
    saveDialogError: options.saveDialogError,
    executeMode: options.executeMode ?? "ok",
    putSettingsMode: options.putSettingsMode ?? "ok",
  };
  const state: SheetCatalogState = {
    controls,
    revision: options.userTemplates?.length ? 3 : 0,
    settingsValue: {schema_version: 1, user_templates: options.userTemplates ?? []},
    preferencePuts: [],
    putExpectedRevisions: [],
    previewRequests: [],
    executeRequests: [],
    lastDigest: null,
    artifacts: new Map(),
    extensionEnabled: true,
    extensionPatchBodies: [],
  };

  if (!options.noShell) {
    await page.addInitScript(({mode, errorCode}) => {
      const calls = {
        saveRequests: [] as unknown[],
        openFolderCalls: [] as string[],
        artifactFolderCalls: [] as {extension_id: string; artifact_id: string}[],
      };
      (window as unknown as Record<string, unknown>).__catalogBridge = calls;
      (window as unknown as Record<string, unknown>).pywebview = {
        api: {
          select_file: async () => "C:\\虚构工程\\图纸集.dst",
          on_files_dropped: async () => {},
          open_workspace_folder: async (workspaceId: string) => {
            calls.openFolderCalls.push(workspaceId);
            return {ok: true, value: null};
          },
          // Task 11B：导出成果"打开所在文件夹"专用桥方法（前端只传标识，不传路径）
          open_artifact_folder: async (extensionId: string, artifactId: string) => {
            calls.artifactFolderCalls.push({extension_id: extensionId, artifact_id: artifactId});
            return {ok: true, value: null};
          },
          request_extension_save: async (extensionId: string, actionId: string, workspaceId: string) => {
            calls.saveRequests.push({extension_id: extensionId, action_id: actionId, workspace_id: workspaceId});
            if (mode === "error") return {ok: false, code: errorCode ?? "EXTENSION_CAPABILITY_UNAVAILABLE", message: "保存对话框不可用"};
            if (mode === "cancel") return {ok: true, value: null};
            return {ok: true, value: {save_grant_id: "grant-e2e", file_name: "测试图纸集-图纸目录.xlsx", expires_at: "2026-09-10T00:00:00Z"}};
          },
        },
      };
      window.dispatchEvent(new Event("pywebviewready"));
    }, {mode: controls.saveDialog, errorCode: controls.saveDialogError ?? null});
  }

  const extensionSummary = () => ({
    extension_id: EXTENSION_ID,
    version: "0.1.0",
    name_key: "extensions.sheetCatalog.name",
    description_key: "extensions.sheetCatalog.description",
    status: state.extensionEnabled ? "AVAILABLE" : "DISABLED",
    enabled: state.extensionEnabled,
    error_code: null,
    actions: [{action_id: "export-xlsx", output_kind: "xlsx", media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}],
    ui_contributions: [{contribution_id: "workspace-page", kind: "workspace_page", route_key: "sheet-catalog"}],
  });

  await page.route("**/api/workspaces/open", route => route.fulfill({json: workspace}));
  await page.route("**/api/workspaces/workspace-1", route => route.fulfill({json: workspace}));
  await page.route("**/api/extensions", route => route.fulfill({json: [extensionSummary()]}));
  // 启停必须由夹具接管：真后端会写用户 .dst-manager-data/dst-manager.db 的
  // extension_states，把扩展真停掉且持久化（曾因此把开发环境卡在停用态）
  await page.route("**/api/extensions/*/state", async route => {
    const body = (await route.request().postDataJSON()) as {enabled: boolean};
    state.extensionPatchBodies.push(body);
    state.extensionEnabled = body.enabled;
    return route.fulfill({json: extensionSummary()});
  });
  const drafts = new Map<string, unknown>();
  await page.route("**/api/workspaces/*/draft", async route => {
    const request = route.request();
    const workspaceId = new URL(request.url()).pathname.split("/").at(-2)!;
    const current = drafts.get(workspaceId) ?? null;
    if (request.method() === "GET") return route.fulfill({json: {draft: current, corrupted: false, stale: false, stale_reasons: []}});
    if (request.method() === "DELETE") { drafts.delete(workspaceId); return route.fulfill({json: {deleted: current !== null}}); }
    const body = await request.postDataJSON();
    const previous = drafts.get(workspaceId) as {version?: number} | undefined;
    const saved = {...body, workspace_id: workspaceId, version: (previous?.version ?? 0) + 1};
    delete saved.expected_version;
    drafts.set(workspaceId, saved);
    return route.fulfill({json: {draft: saved, corrupted: false, stale: false, stale_reasons: []}});
  });
  await page.route("**/api/extensions/*/settings", async route => {
    const request = route.request();
    if (request.method() === "GET") {
      return route.fulfill({json: {schema_version: 1, revision: state.revision, value: state.settingsValue}});
    }
    const body = await request.postDataJSON();
    state.putExpectedRevisions.push(body?.expected_revision);
    if (state.controls.putSettingsMode === "conflict") {
      // 真实并发语义：其他窗口保存成功——服务端修订推进并写入冲突模板；冲突持续
      // 到用例改写 controls.putSettingsMode，前端必须刷新修订后才能再次保存
      state.revision += 1;
      state.settingsValue = {
        schema_version: 1,
        user_templates: [
          ...state.settingsValue.user_templates,
          {template_id: fakeUuid(), name: `其他窗口的模板 ${state.revision}`, schema_version: 1, columns: []},
        ],
      };
      return route.fulfill({status: 409, json: {
        code: "SHEET_CATALOG_TEMPLATE_CONFLICT",
        message_key: "errors.sheetCatalog.templateConflict",
        params: {expected_revision: body?.expected_revision ?? state.revision - 1, current_revision: state.revision},
        message: "模板已被其他保存更新",
      }});
    }
    if (state.controls.putSettingsMode === "duplicate") {
      return route.fulfill({status: 409, json: {
        code: "SHEET_CATALOG_COLUMN_DUPLICATE",
        message_key: "errors.sheetCatalog.columnDuplicate",
        params: {header: body?.value?.user_templates?.at(-1)?.name ?? "duplicate"},
        message: "名称重复",
      }});
    }
    if (state.controls.putSettingsMode === "limit") {
      return route.fulfill({status: 422, json: {
        code: "SHEET_CATALOG_TEMPLATE_LIMIT",
        message_key: "errors.sheetCatalog.templateLimit",
        params: {kind: "user_templates", limit: 100, actual: 101},
        message: "超出模板限制",
      }});
    }
    // 乐观并发核对（与 runtime.put_settings 同语义）：expected_revision 过期即 409
    if (body?.expected_revision !== state.revision) {
      return route.fulfill({status: 409, json: {
        code: "EXTENSION_SETTINGS_INVALID",
        message_key: "errors.extension.settingsInvalid",
        params: {expected_revision: body?.expected_revision ?? -1, current_revision: state.revision},
        message: "设置修订冲突",
      }});
    }
    state.revision += 1;
    state.settingsValue = body.value;
    return route.fulfill({json: {schema_version: 1, revision: state.revision, value: state.settingsValue}});
  });
  await page.route("**/api/extensions/*/workspaces/*/preferences", async route => {
    const request = route.request();
    if (request.method() === "GET") {
      const value = options.preferenceTemplateId ? {template_id: options.preferenceTemplateId} : {};
      return route.fulfill({json: {schema_version: 1, revision: 0, value}});
    }
    const body = await request.postDataJSON();
    state.preferencePuts.push(body.value);
    return route.fulfill({json: {schema_version: 1, revision: (state.preferencePuts.length), value: body.value}});
  });
  await page.route("**/api/extensions/*/actions/*/preview", async route => {
    const body = await route.request().postDataJSON();
    state.previewRequests.push(body);
    state.lastDigest = `digest-${state.previewRequests.length}`;
    const response = buildPreviewResponse(body, workspace, state);
    response.preview_digest = state.lastDigest; // 执行摘要复核按同一摘要核对
    return route.fulfill({json: response});
  });
  await page.route("**/api/extensions/*/actions/*/execute", async route => {
    const body = await route.request().postDataJSON();
    state.executeRequests.push(body);
    const mode = state.controls.executeMode;
    if (mode !== "ok" || body.preview_digest !== state.lastDigest) {
      const mapping: Record<string, {status: number; code: string; messageKey: string; params?: Record<string, unknown>}> = {
        repreviewRequired: {status: 409, code: "REPREVIEW_REQUIRED", messageKey: "errors.extension.repreviewRequired"},
        saveGrantInvalid: {status: 409, code: "SAVE_GRANT_INVALID", messageKey: "errors.extension.saveGrantInvalid"},
        destinationChanged: {status: 409, code: "EXPORT_DESTINATION_CHANGED", messageKey: "errors.extension.exportDestinationChanged"},
        writeFailed: {status: 500, code: "ARTIFACT_WRITE_FAILED", messageKey: "errors.extension.artifactWriteFailed"},
        digestMismatch: {status: 409, code: "REPREVIEW_REQUIRED", messageKey: "errors.extension.repreviewRequired"},
      };
      const resolved = mapping[mode === "ok" ? "digestMismatch" : mode];
      return route.fulfill({status: resolved.status, json: {code: resolved.code, message_key: resolved.messageKey, params: resolved.params ?? {}, message: resolved.code}});
    }
    state.artifacts.set("artifact-e2e", {
      artifact_id: "artifact-e2e",
      extension_id: EXTENSION_ID,
      extension_version: "0.1.0",
      workspace_id: WORKSPACE_ID,
      source_revision_id: "revision-1",
      kind: "sheet_catalog",
      media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      management_relation: "external",
      output_path: "C:\\导出\\测试图纸集-图纸目录.xlsx",
      file_name: "测试图纸集-图纸目录.xlsx",
      size_bytes: 4096,
      sha256: "a".repeat(64),
      created_at: "2026-09-10T00:00:00Z",
      availability: "AVAILABLE",
    });
    return route.fulfill({json: {
      artifact_id: "artifact-e2e",
      file_name: "测试图纸集-图纸目录.xlsx",
      output_path: "C:\\导出\\测试图纸集-图纸目录.xlsx",
      warnings: [],
    }});
  });
  await page.route("**/api/artifacts/*", async route => {
    const id = new URL(route.request().url()).pathname.split("/").at(-1)!;
    const record = state.artifacts.get(id);
    if (!record) return route.fulfill({status: 404, json: {code: "EXTENSION_ARTIFACT_NOT_FOUND", message_key: "errors.extension.artifactNotFound", params: {}, message: "not found"}});
    return route.fulfill({json: record});
  });
  return {state};
}

export async function openCatalogPage(page: Page, options: {noShell?: boolean} = {}): Promise<void> {
  await page.goto("/");
  // 有壳走假壳选择对话框；无壳（noShell 用例）走手动输入路径
  if (options.noShell) {
    await page.locator(".no-shell input").fill("C:\\虚构工程\\图纸集.dst");
    await page.getByRole("button", {name: "打开项目"}).click();
  } else {
    await page.getByRole("button", {name: "选择 DST 文件"}).click();
  }
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
  await page.getByRole("tab", {name: "图纸目录"}).click();
  await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
}
