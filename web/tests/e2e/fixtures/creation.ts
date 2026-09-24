// 创建向导 e2e 共享夹具（PLAN-DM-036 Task 8）：创建草稿、标准候选、XLSX 模板/导入与
// 标准文档详情的 route mock。夹具自洽（内存草稿 + 乐观修订门禁），使「读取 → 编辑 →
// 保存 → 重新读取」「导入 → 全量替换」在夹具内可验证，不依赖真实后端数据目录。
//
// 注意：注册路由必须用 URL 判定而非 glob（`**/api/creation-drafts**` 之类会把 vite 的
// `/src/api/creation.ts` 模块请求一并拦下），与 `fixtures/standards.ts` 同一理由。
import type {Page} from "@playwright/test";

export type CreationCandidateBody = {
  standard_id: string;
  version: string;
  name: string;
  supported_cad_versions: string[];
  available: boolean;
  reasons: string[];
  asset_options: Array<{asset_id: string; kind: string; label: string; layouts: string[]}>;
};

export type CreationGroupBody = {
  group_id: string;
  created_order: number;
  title: string;
  count: number;
  base_asset_id: string;
  layout_asset_id: string;
  paper_layout: string;
  sheet_values: Record<string, string>;
};

export type CreationDraftBody = {
  id: string;
  standard_id: string;
  standard_version: string;
  revision: number;
  step: string;
  target_path: string;
  sheetset_values: Record<string, string>;
  groups: CreationGroupBody[];
};

export type CreationImportDiagnosticBody = {
  code: string;
  message: string;
  sheet: string;
  row: number | null;
  column: string | null;
};

export interface CreationFixtureState {
  drafts: Map<string, CreationDraftBody>;
  createBodies: Array<{standard_id: string; version: string}>;
  saveBodies: Array<Record<string, unknown>>;
  deleted: string[];
  importAttempts: number;
  templateRequests: number;
  /** 可变的导入结果：`null` 表示成功（用 `importSuccess` 替换输入）。 */
  importFailure: {status: number; body: Record<string, unknown>} | null;
  importSuccess: {
    target_path: string;
    sheetset_values: Record<string, string>;
    groups: CreationGroupBody[];
  };
}

export interface CreationFixtureOptions {
  candidates?: CreationCandidateBody[];
  /** 标准库列表（标准详情入口用例需要一条已发布版本）；默认空库。 */
  standardsList?: Array<Record<string, unknown>>;
  /** 创建候选端点固定失败，驱动第一阶段错误边界。 */
  listFails?: boolean;
  /** 整批拒绝的导入响应；默认两条可定位诊断。 */
  importFailure?: {status: number; body: Record<string, unknown>} | null;
  /** 成功导入后的输入（一次性替换草稿的路径、属性与图纸组）。 */
  importSuccess?: CreationFixtureState["importSuccess"];
}

/** 标准文档：图纸集文本/枚举 + 派生映射 + 图纸组枚举/文本 + 两种模板资产。 */
export function creationStandardDocument(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 1,
    standard_id: "szmedi.gas",
    version: "2.1.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2016", "2020"],
    properties: [
      {
        property_id: "prop-name", name: "工程名称", scope: "sheetset", kind: "text",
        required: true, default_value: "",
      },
      {
        property_id: "prop-major", name: "专业", scope: "sheetset", kind: "enum",
        required: true, default_value: "燃气",
        enum_items: [{item_id: "enum-gas", value: "燃气"}, {item_id: "enum-jz", value: "建筑"}],
      },
      {
        property_id: "prop-code", name: "专业代码", scope: "sheetset", kind: "mapping",
        source_property_id: "prop-major", mapping: [{item_id: "enum-gas", value: "RQ"}],
        confirmed_source_items: [["enum-gas", "燃气"]],
      },
      {
        property_id: "prop-stage", name: "图纸阶段", scope: "sheet", kind: "enum",
        required: false, default_value: "施工图",
        enum_items: [{item_id: "enum-cs", value: "施工图"}, {item_id: "enum-jg", value: "竣工图"}],
      },
      {
        property_id: "prop-designer", name: "设计人", scope: "sheet", kind: "text",
        required: false, default_value: "",
      },
    ],
    dwg_naming: {
      segments: [
        {property_id: "prop-code"},
        {literal: "-"},
        {system_field: "subset.name"},
      ],
    },
    assets: [
      {asset_id: "base-a", kind: "base-template", files: [{path: "市政基础.dwt", role: ""}]},
      {
        asset_id: "layout-a", kind: "layout-template",
        files: [{path: "市政图框.dwt", role: "A2"}, {path: "市政图框.dwt", role: "A1"}],
      },
    ],
    numbering: {sequence_field: "subset.sequence", digits: 2, start: 1},
    ...overrides,
  };
}

/** 可用候选：与 `creationStandardDocument` 的属性与资产同源。 */
export function creationCandidate(overrides: Partial<CreationCandidateBody> = {}): CreationCandidateBody {
  return {
    standard_id: "szmedi.gas",
    version: "2.1.0",
    name: "市政燃气施工图",
    supported_cad_versions: ["2016", "2020"],
    available: true,
    reasons: [],
    asset_options: [
      {asset_id: "base-a", kind: "base-template", label: "市政基础.dwt", layouts: []},
      {asset_id: "layout-a", kind: "layout-template", label: "市政图框.dwt", layouts: ["A2", "A1"]},
    ],
    ...overrides,
  };
}

/** 不可用候选：模板资产缺失，只能出现在「无可用标准」的原因说明里。 */
export function unavailableCreationCandidate(): CreationCandidateBody {
  return creationCandidate({
    standard_id: "user.old",
    version: "0.9.0",
    name: "旧版市政模板",
    available: false,
    reasons: ["标准资产 'layout-a' 声明的文件 '市政图框.dwt' 不存在或路径非法"],
    asset_options: [],
  });
}

/** 已发布标准摘要（标准库列表）：供标准详情「用于创建」入口用例。 */
export function publishedStandardSummary(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    source: "user",
    status: "published",
    standard_id: "szmedi.gas",
    version: "2.1.0",
    name: "市政燃气施工图",
    draft_id: null,
    ...overrides,
  };
}

/** 默认导入拒绝：两条诊断覆盖「工作表 + 行 + 列」与「工作表 + 行」两种定位。 */
export function creationImportFailure(): {status: number; body: Record<string, unknown>} {
  return {
    status: 422,
    body: {
      code: "CREATION_IMPORT_INVALID",
      message_key: "errors.creation.importInvalid",
      params: {count: 2},
      message: "导入被整批拒绝：CREATION_XLSX_PAPER_LAYOUT_INVALID；CREATION_XLSX_HEADER_MISSING",
      diagnostics: [
        {
          code: "CREATION_XLSX_PAPER_LAYOUT_INVALID",
          message: "图幅不在所选布局模板的布局内",
          sheet: "Sheet",
          row: 3,
          column: "E",
        },
        {
          code: "CREATION_XLSX_HEADER_MISSING",
          message: "缺少必需的列或行标签",
          sheet: "SheetSet",
          row: 5,
          column: "B",
        },
      ],
    },
  };
}

/** 成功导入的输入：路径、图纸集属性与两个图纸组一次性替换草稿。 */
export function creationImportSuccess(): CreationFixtureState["importSuccess"] {
  return {
    target_path: "D:\\导入项目\\滨河路新建项目",
    sheetset_values: {"prop-name": "滨河路改造工程", "prop-major": "建筑"},
    groups: [
      {
        group_id: "xlsx-2",
        created_order: 0,
        title: "封面",
        count: 1,
        base_asset_id: "base-a",
        layout_asset_id: "layout-a",
        paper_layout: "A2",
        sheet_values: {"prop-stage": "施工图", "prop-designer": "张工"},
      },
      {
        group_id: "xlsx-3",
        created_order: 1,
        title: "平面图",
        count: 2,
        base_asset_id: "base-a",
        layout_asset_id: "layout-a",
        paper_layout: "A1",
        sheet_values: {"prop-stage": "施工图", "prop-designer": "李工"},
      },
    ],
  };
}

/**
 * 安装创建向导端点 mock：候选列表、草稿增删改查（乐观修订）、XLSX 模板与导入，
 * 以及标准文档详情。标准库列表（`GET /api/standards`）一并接管，使向导用例完全自洽，
 * 不读真实数据目录。
 */
export async function installCreation(
  page: Page,
  options: CreationFixtureOptions = {},
): Promise<CreationFixtureState> {
  const state: CreationFixtureState = {
    drafts: new Map(),
    createBodies: [],
    saveBodies: [],
    deleted: [],
    importAttempts: 0,
    templateRequests: 0,
    importFailure: options.importFailure === undefined ? creationImportFailure() : options.importFailure,
    importSuccess: options.importSuccess ?? creationImportSuccess(),
  };
  const candidates = options.candidates ?? [creationCandidate(), unavailableCreationCandidate()];
  const document = creationStandardDocument();

  await page.route(
    url => url.pathname.startsWith("/api/creation-drafts"),
    async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const method = request.method();
      if (path === "/api/creation-drafts/standards" && method === "GET") {
        if (options.listFails === true) {
          return route.fulfill({status: 500, json: {code: "INTERNAL_ERROR", message: "标准候选不可用"}});
        }
        return route.fulfill({json: candidates});
      }
      if (path === "/api/creation-drafts" && method === "POST") {
        const body = (await request.postDataJSON()) as {standard_id: string; version: string};
        state.createBodies.push(body);
        const draft: CreationDraftBody = {
          id: `draft-${state.createBodies.length}`,
          standard_id: body.standard_id,
          standard_version: body.version,
          revision: 1,
          step: "project",
          target_path: "",
          // 初建时后端只应用普通 sheetset 属性默认值（图纸组与路径留空）
          sheetset_values: {"prop-name": "", "prop-major": "燃气"},
          groups: [],
        };
        state.drafts.set(draft.id, draft);
        return route.fulfill({json: draft});
      }
      const templateMatch = /^\/api\/creation-drafts\/([^/]+)\/xlsx-template$/.exec(path);
      if (templateMatch && method === "GET") {
        state.templateRequests += 1;
        return route.fulfill({
          status: 200,
          contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          body: "creation-template-stub",
        });
      }
      const importMatch = /^\/api\/creation-drafts\/([^/]+)\/xlsx-import$/.exec(path);
      if (importMatch && method === "POST") {
        state.importAttempts += 1;
        const current = state.drafts.get(decodeURIComponent(importMatch[1]));
        if (current === undefined) {
          return route.fulfill({status: 404, json: {code: "CREATION_DRAFT_NOT_FOUND", message: "草稿不存在"}});
        }
        if (state.importFailure !== null) {
          // 整批拒绝：草稿 JSON 与修订号零变化
          return route.fulfill({status: state.importFailure.status, json: state.importFailure.body});
        }
        const replaced: CreationDraftBody = {
          ...current,
          revision: current.revision + 1,
          step: "groups",
          target_path: state.importSuccess.target_path,
          sheetset_values: state.importSuccess.sheetset_values,
          groups: state.importSuccess.groups.map(group => ({...group, sheet_values: {...group.sheet_values}})),
        };
        state.drafts.set(replaced.id, replaced);
        return route.fulfill({json: replaced});
      }
      const draftMatch = /^\/api\/creation-drafts\/([^/]+)$/.exec(path);
      if (draftMatch !== null) {
        const draftId = decodeURIComponent(draftMatch[1]);
        const current = state.drafts.get(draftId);
        if (current === undefined) {
          return route.fulfill({
            status: 404,
            json: {code: "CREATION_DRAFT_NOT_FOUND", message_key: "errors.creation.draftNotFound", message: draftId},
          });
        }
        if (method === "GET") return route.fulfill({json: current});
        if (method === "DELETE") {
          state.deleted.push(draftId);
          state.drafts.delete(draftId);
          return route.fulfill({json: {status: "deleted"}});
        }
        if (method === "PUT") {
          const body = (await request.postDataJSON()) as Record<string, unknown>;
          state.saveBodies.push(body);
          if (body["expected_revision"] !== current.revision) {
            return route.fulfill({
              status: 409,
              json: {code: "CREATION_DRAFT_CONFLICT", message_key: "errors.creation.draftConflict", message: "修订冲突"},
            });
          }
          const saved: CreationDraftBody = {
            ...current,
            revision: current.revision + 1,
            step: String(body["step"] ?? current.step),
            target_path: String(body["target_path"] ?? ""),
            sheetset_values: (body["sheetset_values"] as Record<string, string>) ?? {},
            groups: (body["groups"] as CreationGroupBody[]) ?? [],
          };
          state.drafts.set(draftId, saved);
          return route.fulfill({json: saved});
        }
      }
      return route.fulfill({status: 404, json: {code: "NOT_FOUND", message: path}});
    },
  );

  // 标准库列表（应用级表面）与标准文档详情：向导读取可输入属性与派生属性
  await page.route(
    url => url.pathname === "/api/standards",
    route => route.fulfill({json: options.standardsList ?? []}),
  );
  await page.route(
    url => /^\/api\/standards\/[^/]+\/[^/]+$/.test(url.pathname),
    route => {
      const segments = new URL(route.request().url()).pathname.split("/");
      return route.fulfill({
        json: {
          standard_id: decodeURIComponent(segments[3] ?? ""),
          version: decodeURIComponent(segments[4] ?? ""),
          name: document["name"],
          supported_cad_versions: document["supported_cad_versions"],
          dependencies: [],
          document: {...document, standard_id: decodeURIComponent(segments[3] ?? ""), version: decodeURIComponent(segments[4] ?? "")},
        },
      });
    },
  );
  return state;
}

/** 从欢迎页进入创建向导第一阶段。 */
export async function openCreation(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", {name: "创建新图纸集"}).click();
  await page.getByRole("region", {name: "创建新图纸集"}).waitFor();
}

/** 在第一阶段选择可用标准并进入第二阶段（项目信息）。 */
export async function chooseStandard(page: Page, name = "市政燃气施工图"): Promise<void> {
  await page.getByTestId("creation-standard-list").getByRole("button").filter({hasText: name}).click();
  await page.getByRole("region", {name: "项目信息"}).waitFor();
}

/** 进入第三阶段（图纸组）。 */
export async function openGroupsStep(page: Page): Promise<void> {
  await page.getByRole("button", {name: "下一步"}).click();
  await page.getByRole("region", {name: "图纸组"}).waitFor();
}

/** 某个图纸组的行定位器（按创建序稳定的 `data-group-id`）。 */
export function groupRow(page: Page, groupId: string) {
  return page.locator(`tr[data-group-id="${groupId}"]`);
}
