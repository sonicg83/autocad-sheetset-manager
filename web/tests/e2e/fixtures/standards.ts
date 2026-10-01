// 标准管理 e2e 共享夹具（PLAN-DM-035 Task 8）：标准端点 route mock、标准表面入口与
// 主从分栏定位器。Task 9/10/11 的标准 spec 复用同一套契约同构数据，避免每个 spec
// 各自拼一份 list/detail 造成契约漂移。
//
// 注意：注册路由必须用 URL 判定而非 `**/api/standards**` glob——后者会把 vite 的
// `/src/api/standards.ts` 模块请求一并拦下（MIME 错误导致应用启动失败）。
import {expect, type Locator, type Page} from "@playwright/test";
import type {AssetInspection} from "../../../src/features/standards/types";

export type StandardSummary = {
  source: "official" | "user";
  status: "published" | "draft";
  standard_id: string;
  name: string;
  description: string;
  published_at: number | null;
  draft_id: string | null;
};

export function published(
  source: "official" | "user",
  overrides: Partial<StandardSummary> = {},
): StandardSummary {
  return {
    source,
    status: "published",
    standard_id: "00000000-0000-4000-8000-000000000046",
    name: source === "official" ? "官方标准" : "用户标准",
    description: "标准说明",
    published_at: 1_704_164_645_000,
    draft_id: null,
    ...overrides,
  };
}

/** 草稿由 draft_id 承载，标准 UUID 与已发布包身份一致。 */
export function draft(name: string, draftId: string, overrides: Partial<StandardSummary> = {}): StandardSummary {
  return {
    source: "user",
    status: "draft",
    standard_id: "00000000-0000-4000-8000-000000000046",
    name,
    description: "草稿说明",
    published_at: null,
    draft_id: draftId,
    ...overrides,
  };
}

/** 与 StandardDetailResponse 契约同构的详情；document 供派生草稿与能力摘要消费。 */
export function detailBody(summary: StandardSummary) {
  return {
    standard_id: summary.standard_id,
    published_at: summary.published_at ?? 1_704_164_645_000,
    name: summary.name,
    description: summary.description,
    supported_cad_versions: ["2016", "2020"],
    dependencies: [{extension_id: "dst-manager.sheet-catalog", capability_id: "catalog.render", min_version: "0.1.0"}],
    document: {
      schema_version: 3,
      standard_id: summary.standard_id,
      name: summary.name,
      description: summary.description,
      published_at: summary.published_at ?? 1_704_164_645_000,
      supported_cad_versions: ["2016", "2020"],
      properties: [
        {
          property_id: "prop-major",
          name: "专业",
          scope: "sheetset",
          kind: "enum",
          enum_items: [{item_id: "enum-gas", value: "燃气"}],
        },
        {
          property_id: "prop-code",
          name: "专业代码",
          scope: "sheetset",
          kind: "mapping",
          source_property_id: "prop-major",
          mapping: [{item_id: "enum-gas", value: "RQ"}],
          confirmed_source_items: [["enum-gas", "燃气"]],
        },
      ],
      dwg_naming: {
        segments: [
          {property_id: "prop-code"},
          {literal: "-"},
          {system_field: "subset.scope"},
          {literal: " "},
          {system_field: "subset.name"},
        ],
      },
      assets: [{asset_id: "layouts", kind: "layout-template", file: "assets/layouts.dwg", paper_layouts: ["A1", "A2"]}],
      numbering: {sequence_field: "subset.sequence", digits: 3},
    },
  };
}

/** 已发布文档直接生成详情（发布后的详情必须来自真实保存过的文档）。 */
export function detailFromDocument(document: Record<string, unknown>) {
  return {
    standard_id: String(document["standard_id"] ?? ""),
    published_at: Number(document["published_at"] ?? 0),
    name: String(document["name"] ?? ""),
    description: String(document["description"] ?? ""),
    supported_cad_versions: (document["supported_cad_versions"] as string[] | undefined) ?? [],
    dependencies: (document["dependencies"] as unknown[] | undefined) ?? [],
    document,
  };
}

export interface StandardsFixtureState {
  list: StandardSummary[];
  /** 可变的列表加载失败开关（可就地恢复并重试）。 */
  listFails: boolean;
  createBodies: unknown[];
  deleted: string[];
  deletedStandards: string[];
  deleteImpactRequests: string[];
  deleteTokens: Array<{standardId: string; impactToken: string}>;
  /** 导入预检端点被调用次数（碰撞场景断言用）。 */
  importAttempts: number;
  /** 确认导入端点被调用次数（幂等/防重复提交断言用）。 */
  confirmAttempts: number;
  /** 取消预检端点被调用次数（换文件/取消清凭证断言用）。 */
  cancelAttempts: number;
  /** 预检端点收到的来源路径（原样传递断言用：中文/空格/OneDrive 路径）。 */
  previewPaths: string[];
  /** 保存请求的文档体（草稿级与身份路由共用；按时间顺序）。 */
  saveBodies: Record<string, unknown>[];
  /** 草稿级保存命中的草稿 ID（F11：保存必须用打开时的草稿身份）。 */
  savedDraftIds: string[];
  /** 内存草稿文档：draft_id → document。 */
  drafts: Map<string, Record<string, unknown>>;
  /** 已发布文档（发布后详情端点直接返回它）：standard_id → document。 */
  published: Map<string, Record<string, unknown>>;
  /** 资产检查结果：asset_id → 响应。 */
  assetResults: Record<string, AssetInspection>;
  /** 可变的资产检查失败注入：asset_id → 错误响应（测试可中途清空重试）。 */
  assetInspectFailures: Record<string, {status: number; code: string; message: string}>;
  /** 资产检查调用次数（重试断言用）。 */
  inspectCalls: string[];
  /** 资产检查命中的草稿 ID（F03：编辑器必须只操作打开时的草稿）。 */
  inspectDraftIds: string[];
  /** 发布命中的草稿 ID（F03）。 */
  publishDraftIds: string[];
  /** 本机模板受控复制调用（入参：草稿 ID 与来源绝对路径）。 */
  assetCopyCalls: {draftId: string; sourcePath: string}[];
  /** 可变的复制失败注入（模拟后端稳定拒绝）。 */
  assetCopyFailure: {status: number; code: string; message: string} | null;
  /** 可变的详情加载失败注入（standard_id → 错误响应；可中途清空重试）。 */
  detailFailures: Record<string, {status: number; code: string; message: string}>;
  /** 可变的发布失败注入。 */
  publishFailure: {status: number; code: string; message: string} | null;
  publishCalls: number;
  /** 注入保存失败（模拟服务端 5xx/冲突），默认不失败。 */
  saveFailure: {status: number; code: string; message: string} | null;
}

export type StandardsFixtureOptions = {
  /** 列表端点返回 500，驱动加载失败边界。 */
  listFails?: boolean;
  /** 预检固定返回的身份冲突诊断。 */
  importConflict?: {status: number; code: string; message: string};
  /** 预检返回名称冲突，确认时可提交新名称作为本机副本名。 */
  importNameConflict?: string;
  /** 预检成功后、确认阶段发生冲突（模拟并发写入）。 */
  importConfirmConflict?: {status: number; code: string; message: string};
  /** 预置草稿文档：draft_id → document（编辑器加载与保存目标）。 */
  drafts?: Record<string, Record<string, unknown>>;
  /** 预置资产检查结果：asset_id → 响应。 */
  assetResults?: Record<string, AssetInspection>;
  /** 预置资产检查失败（可中途清空）：asset_id → 错误响应。 */
  assetInspectFailures?: Record<string, {status: number; code: string; message: string}>;
  /** 按 standard_id 注入详情加载失败（驱动“切换后旧详情不得被消费”）。 */
  detailFailures?: Record<string, {status: number; code: string; message: string}>;
  /** 按 standard_id 覆盖详情文档：区分不同标准的派生来源内容。 */
  detailDocuments?: Record<string, Record<string, unknown>>;
  /** 资产复制端点返回的布局列表（模拟后端从 DWG 读到的布局；默认 Model+A1+A2）。 */
  assetCopyLayouts?: string[];
  /** 保存接口返回的 Schema 版本，可验证编辑器采用服务端升级后的基准。 */
  saveSchemaVersion?: number;
};

/** 最小合法标准文档（草稿）：普通属性（枚举）+ 映射 + 组合 + 全局 DWG 命名模板。 */
export function draftDocument(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 3,
    standard_id: "00000000-0000-4000-8000-000000000046",
    name: "市政燃气施工图",
    description: "",
    published_at: null,
    supported_cad_versions: ["2020"],
    properties: [
      {
        property_id: "prop-major",
        name: "专业",
        scope: "sheetset",
        kind: "enum",
        required: true,
        enum_items: [
          {item_id: "enum-gas", value: "燃气"},
          {item_id: "enum-jz", value: "建筑"},
          {item_id: "enum-jg", value: "结构"},
        ],
      },
      {
        property_id: "prop-code",
        name: "专业代码",
        scope: "sheetset",
        kind: "mapping",
        source_property_id: "prop-major",
        mapping: [
          {item_id: "enum-gas", value: "RQ"},
          {item_id: "enum-jz", value: "JZ"},
          {item_id: "enum-jg", value: "JG"},
        ],
        confirmed_source_items: [["enum-gas", "燃气"], ["enum-jz", "建筑"], ["enum-jg", "结构"]],
      },
      {
        property_id: "prop-label",
        name: "图签",
        scope: "sheet",
        kind: "composition",
        segments: [{property_id: "prop-code"}, {literal: " "}, {system_field: "sheet.number"}],
      },
    ],
    dwg_naming: {
      segments: [
        {property_id: "prop-code"},
        {literal: "-"},
        {system_field: "subset.scope"},
        {literal: " "},
        {system_field: "subset.name"},
      ],
    },
    assets: [],
    numbering: {sequence_field: "subset.sequence", digits: 3, start: 1},
    ...overrides,
  };
}

/**
 * 部分映射草稿：源枚举新增了「给排水」，但映射行还没有目标值。
 * 草稿可以保存（结构合法），发布被 `STANDARD_MAPPING_TARGET_EMPTY` 阻断。
 */
export function partialMappingDraft(): Record<string, unknown> {
  return draftDocument({
    properties: [
      {
        property_id: "prop-major",
        name: "专业",
        scope: "sheetset",
        kind: "enum",
        required: true,
        enum_items: [
          {item_id: "enum-gas", value: "燃气"},
          {item_id: "enum-jz", value: "建筑"},
          {item_id: "enum-jg", value: "结构"},
          {item_id: "enum-ps", value: "给排水"},
        ],
      },
      {
        property_id: "prop-code",
        name: "专业代码",
        scope: "sheetset",
        kind: "mapping",
        source_property_id: "prop-major",
        mapping: [
          {item_id: "enum-gas", value: "RQ"},
          {item_id: "enum-jz", value: "JZ"},
          {item_id: "enum-jg", value: "JG"},
          {item_id: "enum-ps", value: ""},
        ],
        // 确认快照只到「结构」：新增「给排水」后映射进入待确认（warning）
        confirmed_source_items: [["enum-gas", "燃气"], ["enum-jz", "建筑"], ["enum-jg", "结构"]],
      },
    ],
  });
}

/**
 * 安装标准端点 mock：列表、详情、草稿读取、草稿创建/删除、按身份保存、发布、导入。
 * 列表可变（创建/删除后同步），detail 由列表中的已发布项派生，草稿文档保存在内存中，
 * 保证“读取 → 编辑 → 保存 → 重新读取”在夹具内自洽。
 */
export async function installStandards(
  page: Page,
  initial: StandardSummary[],
  options: StandardsFixtureOptions = {},
): Promise<StandardsFixtureState> {
  const state: StandardsFixtureState = {
    list: [...initial],
    listFails: options.listFails === true,
    createBodies: [],
    deleted: [],
    deletedStandards: [],
    deleteImpactRequests: [],
    deleteTokens: [],
    importAttempts: 0,
    confirmAttempts: 0,
    cancelAttempts: 0,
    previewPaths: [],
    saveBodies: [],
    savedDraftIds: [],
    drafts: new Map(Object.entries(options.drafts ?? {})),
    published: new Map(),
    assetResults: options.assetResults ?? {},
    assetInspectFailures: {...(options.assetInspectFailures ?? {})},
    inspectCalls: [],
    inspectDraftIds: [],
    publishDraftIds: [],
    detailFailures: {...(options.detailFailures ?? {})},
    assetCopyCalls: [],
    assetCopyFailure: null,
    publishFailure: null,
    publishCalls: 0,
    saveFailure: null,
  };
  await page.route(
    url => url.pathname === "/api/standards" || url.pathname.startsWith("/api/standards/"),
    async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const method = request.method();
      if (path === "/api/standards" && method === "GET") {
        if (state.listFails) return route.fulfill({status: 500, json: {code: "INTERNAL_ERROR", message: "标准库不可用"}});
        return route.fulfill({json: state.list});
      }
      const impactMatch = /^\/api\/standards\/([^/]+)\/delete-impact$/.exec(path);
      if (impactMatch && method === "GET") {
        const standardId = decodeURIComponent(impactMatch[1]);
        state.deleteImpactRequests.push(standardId);
        const summary = state.list.find(item => item.status === "published" && item.standard_id === standardId);
        if (summary === undefined || summary.source !== "user") {
          return route.fulfill({status: 403, json: {code: "STANDARD_OFFICIAL_DELETE_FORBIDDEN", message: "不可删除官方标准"}});
        }
        const affectedCount = state.list.filter(item => item.status === "draft" && item.standard_id === standardId).length;
        return route.fulfill({json: {
          standard_id: standardId,
          affected_count: affectedCount,
          impact_token: `impact:${standardId}:${affectedCount}`,
        }});
      }
      const standardDeleteMatch = /^\/api\/standards\/([^/]+)\/delete$/.exec(path);
      if (standardDeleteMatch && method === "POST") {
        const standardId = decodeURIComponent(standardDeleteMatch[1]);
        const body = (await request.postDataJSON()) as {impact_token: string};
        state.deleteTokens.push({standardId, impactToken: body.impact_token});
        const summary = state.list.find(item => item.status === "published" && item.standard_id === standardId);
        const affected = state.list.filter(item => item.status === "draft" && item.standard_id === standardId);
        const expectedToken = `impact:${standardId}:${affected.length}`;
        if (summary === undefined || summary.source !== "user") {
          return route.fulfill({status: 403, json: {code: "STANDARD_OFFICIAL_DELETE_FORBIDDEN", message: "不可删除官方标准"}});
        }
        if (body.impact_token !== expectedToken) {
          return route.fulfill({status: 409, json: {code: "STANDARD_DELETE_IMPACT_CHANGED", message: "删除影响已变化"}});
        }
        state.deletedStandards.push(standardId);
        state.list = state.list.filter(item => item.standard_id !== standardId);
        for (const item of affected) {
          if (item.draft_id !== null) {
            state.deleted.push(item.draft_id);
            state.drafts.delete(item.draft_id);
          }
        }
        return route.fulfill({json: {standard_id: standardId, deleted_count: affected.length + 1}});
      }
      if (path === "/api/standards/drafts" && method === "POST") {
        const body = (await request.postDataJSON()) as {document: Record<string, unknown>};
        state.createBodies.push(body);
        const created = draft(String(body.document["name"] ?? "草稿"), `draft-new-${state.createBodies.length}`);
        state.list.push(created);
        state.drafts.set(created.draft_id!, body.document);
        return route.fulfill({json: {draft_id: created.draft_id, document: body.document}});
      }
      if (path.startsWith("/api/standards/drafts/") && method === "GET") {
        const draftId = decodeURIComponent(path.split("/").at(-1)!);
        const document = state.drafts.get(draftId);
        if (document === undefined) return route.fulfill({status: 404, json: {code: "STANDARD_DRAFT_NOT_FOUND", message: draftId}});
        return route.fulfill({json: {draft_id: draftId, document}});
      }
      if (path.startsWith("/api/standards/drafts/") && method === "DELETE") {
        const draftId = decodeURIComponent(path.split("/").at(-1)!);
        state.deleted.push(draftId);
        state.list = state.list.filter(item => item.draft_id !== draftId);
        state.drafts.delete(draftId);
        return route.fulfill({json: {status: "deleted"}});
      }
      const copyMatch = /^\/api\/standards\/drafts\/([^/]+)\/asset-files$/.exec(path);
      if (copyMatch && method === "POST") {
        const body = (await request.postDataJSON()) as {source_path: string};
        state.assetCopyCalls.push({draftId: decodeURIComponent(copyMatch[1]), sourcePath: body.source_path});
        if (state.assetCopyFailure !== null) {
          return route.fulfill({status: state.assetCopyFailure.status, json: {code: state.assetCopyFailure.code, message: state.assetCopyFailure.message}});
        }
        // 与后端契约同构：受控副本名 + 复制时读取到的布局（绝不回显来源路径）
        const layouts = options.assetCopyLayouts ?? ["Model", "A1", "A2"];
        return route.fulfill({json: {path: `assets/managed-${state.assetCopyCalls.length}.dwg`, layouts, layouts_error: null}});
      }
      const draftSaveMatch = /^\/api\/standards\/drafts\/([^/]+)$/.exec(path);
      if (draftSaveMatch && method === "PUT") {
        const draftId = decodeURIComponent(draftSaveMatch[1]);
        const body = (await request.postDataJSON()) as {document: Record<string, unknown>};
        state.saveBodies.push(body.document);
        state.savedDraftIds.push(draftId);
        if (state.saveFailure !== null) {
          return route.fulfill({status: state.saveFailure.status, json: {code: state.saveFailure.code, message: state.saveFailure.message}});
        }
        if (!state.drafts.has(draftId)) {
          return route.fulfill({status: 404, json: {code: "STANDARD_DRAFT_NOT_FOUND", message: draftId}});
        }
        const savedDocument = options.saveSchemaVersion === undefined
          ? body.document
          : {...body.document, schema_version: options.saveSchemaVersion};
        state.drafts.set(draftId, savedDocument);
        return route.fulfill({json: {draft_id: draftId, document: savedDocument}});
      }
      if (path === "/api/standards/import-previews" && method === "POST") {
        state.importAttempts += 1;
        const body = (await request.postDataJSON()) as {path: string};
        state.previewPaths.push(body.path);
        const conflict = options.importConflict;
        if (conflict !== undefined && conflict.status !== 200) {
          return route.fulfill({status: conflict.status, json: {code: conflict.code, message: conflict.message}});
        }
        const nameConflict = options.importNameConflict !== undefined;
        if (conflict !== undefined) {
          return route.fulfill({
            json: {
              preview_id: null,
              expires_at: null,
              standard_id: "00000000-0000-4000-8000-000000000047",
              name: "导入标准",
              description: "导入标准描述",
              published_at: 1_704_164_645_000,
              name_conflict: false,
              existing_name: null,
              supported_cad_versions: ["2020"],
              diagnostics: [{code: conflict.code, severity: "error", message: conflict.message, property_id: null, segment_index: null}],
              can_import: false,
            },
          });
        }
        return route.fulfill({
          json: {
            preview_id: `preview-${state.importAttempts}`,
            expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
            standard_id: "00000000-0000-4000-8000-000000000047",
            name: "导入标准",
            description: "导入标准描述",
            published_at: 1_704_164_645_000,
            name_conflict: nameConflict,
            existing_name: options.importNameConflict ?? null,
            supported_cad_versions: ["2020"],
            diagnostics: nameConflict
              ? [{code: "STANDARD_NAME_CONFLICT", severity: "error", message: "名称已使用", property_id: null, segment_index: null}]
              : [],
            can_import: !nameConflict,
          },
        });
      }
      if (path === "/api/standards/import" && method === "POST") {
        state.confirmAttempts += 1;
        const body = (await request.postDataJSON()) as {preview_id: string; name?: string | null};
        const confirmConflict = options.importConfirmConflict;
        if (confirmConflict !== undefined) {
          return route.fulfill({
            status: confirmConflict.status,
            json: {code: confirmConflict.code, message: confirmConflict.message},
          });
        }
        const conflict = options.importConflict;
        if (conflict !== undefined && conflict.status !== 200) {
          return route.fulfill({status: conflict.status, json: {code: conflict.code, message: conflict.message}});
        }
        if (options.importNameConflict !== undefined && (!body.name || body.name === options.importNameConflict)) {
          return route.fulfill({status: 409, json: {code: "STANDARD_NAME_CONFLICT", message: "名称已使用"}});
        }
        const imported = {
          source: "user" as const,
          status: "published" as const,
          standard_id: "00000000-0000-4000-8000-000000000047",
          name: body.name ?? "导入标准",
          description: "导入标准描述",
          published_at: 1_704_164_645_000,
          draft_id: null,
        };
        state.list.push(imported);
        return route.fulfill({json: {
          standard_id: imported.standard_id,
          published_at: imported.published_at,
          name: imported.name,
          description: imported.description,
          preview_id: body.preview_id,
        }});
      }
      const importCancelMatch = /^\/api\/standards\/import-previews\/([^/]+)$/.exec(path);
      if (importCancelMatch && method === "DELETE") {
        state.cancelAttempts += 1;
        return route.fulfill({json: {status: "cancelled"}});
      }
      const inspectMatch = /^\/api\/standards\/drafts\/([^/]+)\/assets\/([^/]+)\/inspect$/.exec(path);
      if (inspectMatch && method === "POST") {
        const assetId = decodeURIComponent(inspectMatch[2]);
        state.inspectCalls.push(assetId);
        state.inspectDraftIds.push(decodeURIComponent(inspectMatch[1]));
        const failure = state.assetInspectFailures[assetId];
        if (failure !== undefined) {
          return route.fulfill({status: failure.status, json: {code: failure.code, message: failure.message}});
        }
        const result = state.assetResults[assetId];
        return route.fulfill({json: result ?? {asset_id: assetId, kind: "layout-template", layouts: [], diagnostics: []}});
      }
      const publishMatch = /^\/api\/standards\/drafts\/([^/]+)\/publish$/.exec(path);
      if (publishMatch && method === "POST") {
        state.publishCalls += 1;
        if (state.publishFailure !== null) {
          return route.fulfill({status: state.publishFailure.status, json: {code: state.publishFailure.code, message: state.publishFailure.message}});
        }
        const draftId = decodeURIComponent(publishMatch[1]);
        state.publishDraftIds.push(draftId);
        const document = state.drafts.get(draftId) ?? {};
        const standardId = String(document["standard_id"] ?? "");
        const publishedAt = Date.now();
        const publishedDocument = {...document, published_at: publishedAt};
        // 后端发布把草稿目录移入已发布目录：草稿不再存在，列表出现同名用户已发布版本
        state.drafts.delete(draftId);
        state.list = state.list.filter(item => item.draft_id !== draftId);
        const summary: StandardSummary = {
          source: "user",
          status: "published",
          standard_id: standardId,
          name: String(document["name"] ?? ""),
          description: String(document["description"] ?? ""),
          published_at: publishedAt,
          draft_id: null,
        };
        state.list.push(summary);
        state.published.set(standardId, publishedDocument);
        return route.fulfill({json: {
          standard_id: standardId,
          published_at: publishedAt,
          name: summary.name,
          description: summary.description,
        }});
      }
      const exportMatch = /^\/api\/standards\/([^/]+)\/export$/.exec(path);
      if (exportMatch && method === "GET") {
        return route.fulfill({status: 200, body: "standard-package", contentType: "application/zip"});
      }
      const standardMatch = /^\/api\/standards\/([^/]+)$/.exec(path);
      if (standardMatch && method === "GET") {
        const standardId = decodeURIComponent(standardMatch[1]);
        const summary = state.list.find(item =>
          item.status === "published" && item.standard_id === standardId);
        if (summary === undefined) return route.fulfill({status: 404, json: {code: "STANDARD_NOT_FOUND", message: "未找到"}});
        const failure = state.detailFailures[standardId];
        if (failure !== undefined) return route.fulfill({status: failure.status, json: {code: failure.code, message: failure.message}});
        const publishedDocument = state.published.get(standardId);
        if (publishedDocument !== undefined) return route.fulfill({json: detailFromDocument(publishedDocument)});
        const override = options.detailDocuments?.[standardId];
        if (override !== undefined) return route.fulfill({json: {...detailBody(summary), document: override}});
        return route.fulfill({json: detailBody(summary)});
      }
      return route.fulfill({status: 404, json: {code: "NOT_FOUND", message: path}});
    },
  );
  return state;
}

/** 从欢迎页进入应用级标准管理表面（不创建工作区、不进工作区标签栏）。 */
export async function openStandards(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(page.getByRole("heading", {name: "标准管理"})).toBeVisible();
}

/** 左栏标准条目按钮（限定在标准库列表内，避免与详情里的版本链接混淆）。
 *  用 `data-testid="library-list"` 而不是区域可访问名：区域名随语言变化，
 *  英文场景下按中文区域名定位会永远解析不到（定位器静默等待直到超时）。 */
export function libraryItems(page: Page): Locator {
  return page.getByTestId("library-item");
}

/** 归集组头按钮（按 standard_id 归集；键盘可展开/收起）。 */

/** 选中草稿并进入分区编辑器（详情面板的「编辑」入口）。 */
export async function openDraftEditor(page: Page, draftName = "草稿 1"): Promise<void> {
  await libraryItems(page).filter({hasText: draftName}).click();
  await page.getByRole("button", {name: "编辑"}).click();
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();
}

/** 切换到指定编辑分区（分区导航是原生按钮，回车/空格同样生效）。 */
export async function openEditorSection(page: Page, sectionId: string): Promise<void> {
  await page.getByTestId(`editor-section-${sectionId}`).click();
}

export function editorSaveState(page: Page): Locator {
  return page.getByTestId("editor-save-state");
}

/** 经固定 `dststandard` 原生选择器选取标准包（设置假桥的一次性返回路径）。 */
export async function chooseStandardPackage(page: Page, path: string): Promise<void> {
  await page.evaluate(value => {
    (window as unknown as {__fakeSelectResult?: string}).__fakeSelectResult = value;
  }, path);
  await page.getByTestId("import-choose-file").click();
}
