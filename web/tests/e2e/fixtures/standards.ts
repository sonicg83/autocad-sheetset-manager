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
  version: string;
  name: string;
  draft_id: string | null;
};

export function published(source: "official" | "user", version: string, overrides: Partial<StandardSummary> = {}): StandardSummary {
  return {source, status: "published", standard_id: "szmedi.gas", version, name: "市政燃气施工图", draft_id: null, ...overrides};
}

/** 草稿无版本号（版本由发布时确定），身份经 draft_id 承载。 */
export function draft(name: string, draftId: string, overrides: Partial<StandardSummary> = {}): StandardSummary {
  return {source: "user", status: "draft", standard_id: "", version: "", name, draft_id: draftId, ...overrides};
}

/** 与 StandardDetailResponse 契约同构的详情；document 供派生草稿与能力摘要消费。 */
export function detailBody(summary: StandardSummary) {
  return {
    standard_id: summary.standard_id,
    version: summary.version,
    name: summary.name,
    supported_cad_versions: ["2016", "2020"],
    dependencies: [{extension_id: "dst-manager.sheet-catalog", capability_id: "catalog.render", min_version: "0.1.0"}],
    document: {
      schema_version: 1,
      standard_id: summary.standard_id,
      version: summary.version,
      name: summary.name,
      supported_cad_versions: ["2016", "2020"],
      properties: [{key: "sheet.title"}, {key: "sheet.number"}, {key: "subset.sequence"}],
      rules: [{kind: "required", field: "sheet.title"}],
      assets: [{asset_id: "layouts", kind: "layout"}],
      numbering: {sequence_field: "subset.sequence", digits: 2},
    },
  };
}

/** 已发布文档直接生成详情（发布后的详情必须来自真实保存过的文档）。 */
export function detailFromDocument(document: Record<string, unknown>) {
  return {
    standard_id: String(document["standard_id"] ?? ""),
    version: String(document["version"] ?? ""),
    name: String(document["name"] ?? ""),
    supported_cad_versions: (document["supported_cad_versions"] as string[] | undefined) ?? [],
    dependencies: (document["dependencies"] as unknown[] | undefined) ?? [],
    document,
  };
}

export interface StandardsFixtureState {
  list: StandardSummary[];
  createBodies: unknown[];
  deleted: string[];
  /** 导入端点被调用次数（碰撞场景断言用）。 */
  importAttempts: number;
  /** 草稿按身份的保存请求体（PUT /api/standards/{id}/{ver}）。 */
  saveBodies: Record<string, unknown>[];
  /** 内存草稿文档：draft_id → document。 */
  drafts: Map<string, Record<string, unknown>>;
  /** 已发布文档（发布后详情端点直接返回它）：`"id@ver"` → document。 */
  published: Map<string, Record<string, unknown>>;
  /** 资产检查结果：asset_id → 响应。 */
  assetResults: Record<string, AssetInspection>;
  /** 可变的资产检查失败注入：asset_id → 错误响应（测试可中途清空重试）。 */
  assetInspectFailures: Record<string, {status: number; code: string; message: string}>;
  /** 资产检查调用次数（重试断言用）。 */
  inspectCalls: string[];
  /** 可变的发布失败注入。 */
  publishFailure: {status: number; code: string; message: string} | null;
  publishCalls: number;
  /** 注入保存失败（模拟服务端 5xx/冲突），默认不失败。 */
  saveFailure: {status: number; code: string; message: string} | null;
}

export type StandardsFixtureOptions = {
  /** 列表端点返回 500，驱动加载失败边界。 */
  listFails?: boolean;
  /** 导入端点固定返回的冲突响应（默认 409 STANDARD_VERSION_EXISTS）。 */
  importConflict?: {status: number; code: string; message: string};
  /** 预置草稿文档：draft_id → document（编辑器加载与保存目标）。 */
  drafts?: Record<string, Record<string, unknown>>;
  /** 预置资产检查结果：asset_id → 响应。 */
  assetResults?: Record<string, AssetInspection>;
  /** 预置资产检查失败（可中途清空）：asset_id → 错误响应。 */
  assetInspectFailures?: Record<string, {status: number; code: string; message: string}>;
};

/** 最小合法标准文档（草稿）：两个属性 + 一条空表映射规则 + 一条命名规则。 */
export function draftDocument(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 1,
    standard_id: "szmedi.gas",
    version: "3.0.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2020"],
    properties: [
      {name: "专业名称", scope: "sheetset", required: true, default_value: "", enum_values: ["燃气", "建筑", "结构"], description: ""},
      {name: "专业代码", scope: "sheetset", required: false, default_value: "", enum_values: [], description: ""},
    ],
    rules: [
      // 映射表覆盖源域全部枚举值：夹具草稿必须自洽可保存（空表会被结构诊断阻断）
      {rule_id: "specialty-code", kind: "mapping", target: "sheetset.专业代码", source: "sheetset.专业名称", allowed: [], table: [["燃气", "RQ"], ["建筑", "JZ"], ["结构", "JG"]], segments: []},
      {rule_id: "dwg-name", kind: "naming", target: "derived.dwg_name", allowed: [], table: [], segments: []},
    ],
    assets: [],
    numbering: {sequence_field: "subset.sequence", digits: 2, start: 1},
    ...overrides,
  };
}

/**
 * 部分映射草稿：源域有四个枚举值，映射表仅覆盖一个（`给排水` 未覆盖）。
 * 用于驱动「批量粘贴补齐映射表后才能保存」的边界。
 */
export function partialMappingDraft(): Record<string, unknown> {
  return draftDocument({
    properties: [
      {name: "专业名称", scope: "sheetset", required: true, default_value: "", enum_values: ["燃气", "建筑", "结构", "给排水"], description: ""},
      {name: "专业代码", scope: "sheetset", required: false, default_value: "", enum_values: [], description: ""},
    ],
    rules: [
      {rule_id: "specialty-code", kind: "mapping", target: "sheetset.专业代码", source: "sheetset.专业名称", allowed: [], table: [["燃气", "RQ"]], segments: []},
      {rule_id: "dwg-name", kind: "naming", target: "derived.dwg_name", allowed: [], table: [], segments: []},
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
    createBodies: [],
    deleted: [],
    importAttempts: 0,
    saveBodies: [],
    drafts: new Map(Object.entries(options.drafts ?? {})),
    published: new Map(),
    assetResults: options.assetResults ?? {},
    assetInspectFailures: {...(options.assetInspectFailures ?? {})},
    inspectCalls: [],
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
        if (options.listFails === true) return route.fulfill({status: 500, json: {code: "INTERNAL_ERROR", message: "标准库不可用"}});
        return route.fulfill({json: state.list});
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
      if (path === "/api/standards/import" && method === "POST") {
        state.importAttempts += 1;
        const conflict = options.importConflict ?? {status: 409, code: "STANDARD_VERSION_EXISTS", message: "同一标准 ID 与版本已存在"};
        return route.fulfill({status: conflict.status, json: {code: conflict.code, message: conflict.message}});
      }
      const inspectMatch = /^\/api\/standards\/drafts\/([^/]+)\/assets\/([^/]+)\/inspect$/.exec(path);
      if (inspectMatch && method === "POST") {
        const assetId = decodeURIComponent(inspectMatch[2]);
        state.inspectCalls.push(assetId);
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
        const document = state.drafts.get(draftId) ?? {};
        const standardId = String(document["standard_id"] ?? "");
        const version = String(document["version"] ?? "");
        // 后端发布把草稿目录移入已发布目录：草稿不再存在，列表出现同名用户已发布版本
        state.drafts.delete(draftId);
        state.list = state.list.filter(item => item.draft_id !== draftId);
        state.list.push({source: "user", status: "published", standard_id: standardId, version, name: String(document["name"] ?? ""), draft_id: null});
        state.published.set(`${standardId}@${version}`, document);
        return route.fulfill({json: {standard_id: standardId, version, name: document["name"] ?? ""}});
      }
      if (method === "PUT") {
        const match = /^\/api\/standards\/([^/]+)\/([^/]+)$/.exec(path);
        if (match === null) return route.fulfill({status: 404, json: {code: "NOT_FOUND", message: path}});
        const body = (await request.postDataJSON()) as Record<string, unknown>;
        state.saveBodies.push(body);
        if (state.saveFailure !== null) {
          return route.fulfill({status: state.saveFailure.status, json: {code: state.saveFailure.code, message: state.saveFailure.message}});
        }
        // 按身份找草稿（草稿推荐摘要的 version 恒为空串，身份在文档内）
        const draftId = [...state.drafts.entries()].find(([, document]) =>
          document["standard_id"] === body["standard_id"] && document["version"] === body["version"])?.[0];
        if (draftId === undefined) return route.fulfill({status: 404, json: {code: "STANDARD_DRAFT_NOT_FOUND", message: String(body["standard_id"])}});
        state.drafts.set(draftId, body);
        return route.fulfill({json: {draft_id: draftId, document: body}});
      }
      const match = /^\/api\/standards\/([^/]+)\/([^/]+)$/.exec(path);
      if (match && method === "GET" && match[1] !== "drafts") {
        const standardId = decodeURIComponent(match[1]);
        const version = decodeURIComponent(match[2]);
        const publishedDocument = state.published.get(`${standardId}@${version}`);
        const summary = state.list.find(item =>
          item.status === "published"
          && item.standard_id === standardId
          && item.version === version);
        if (summary === undefined) return route.fulfill({status: 404, json: {code: "STANDARD_NOT_FOUND", message: "未找到"}});
        if (publishedDocument !== undefined) return route.fulfill({json: detailFromDocument(publishedDocument)});
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

/** 左栏标准条目按钮（限定在「标准库」区域内，避免与详情里的版本链接混淆）。 */
export function libraryItems(page: Page): Locator {
  return page.getByRole("region", {name: "标准库"}).getByRole("list").getByRole("button");
}

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
