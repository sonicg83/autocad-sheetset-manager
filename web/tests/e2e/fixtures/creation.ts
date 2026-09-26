// 创建向导 e2e 共享夹具（PLAN-DM-036 Task 8，Task 9 追加预览/执行/任务端点）：创建草稿、
// 标准候选、XLSX 模板/导入、权威预览、执行入队、任务 SSE/轮询与标准文档详情的 route mock。
// 夹具自洽（内存草稿 + 乐观修订门禁），使「读取 → 编辑 → 保存 → 重新读取」「导入 →
// 全量替换」「预览 → 执行 → 任务终态」在夹具内可验证，不依赖真实后端数据目录。
//
// 预览响应是**后端权威结果**的替身：图号范围、紧凑标题、DWG 文件名与逐张属性值都由它
// 给出，前端只投影不推算；用例可在进入第四阶段前替换 `preview`/`jobResult` 驱动失效、
// 阻断与失败分支。
//
// 注意：注册路由必须用 URL 判定而非 glob（`**/api/creation-drafts**` 之类会把 vite 的
// `/src/api/creation.ts` 模块请求一并拦下），与 `fixtures/standards.ts` 同一理由。
import type {Page} from "@playwright/test";

export type CreationCandidateBody = {
  standard_id: string;
  version: number;
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
  standard_version: number;
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
  createBodies: Array<{standard_id: string; version: number}>;
  saveBodies: Array<Record<string, unknown>>;
  deleted: string[];
  importAttempts: number;
  templateRequests: number;
  /** 权威预览请求次数与执行请求体（执行只允许携带 `preview_digest`）。 */
  previewRequests: number;
  executeBodies: Array<Record<string, unknown>>;
  /** 创建任务 SSE 连接次数（含轮询回退共用的终态响应）。 */
  jobStreams: number;
  /** 可变的权威预览响应；用例可在进入第四阶段前替换。 */
  preview: Record<string, unknown> | null;
  /** 执行入队返回的任务（登记前 `workspace_id` 为空）。 */
  executeJob: Record<string, unknown>;
  /** 任务 SSE/轮询的终态响应（成功时带 `workspace_id`）。 */
  jobResult: Record<string, unknown>;
  /** 可变的导入结果：`null` 表示成功（用 `importSuccess` 替换输入）。 */
  importFailure: {status: number; body: Record<string, unknown>} | null;
  /** 可变的保存结果：`null` 表示按乐观修订正常落盘（驱动「离开向导前必须落盘」门禁）。 */
  saveFailure: {status: number; body: Record<string, unknown>} | null;
  importSuccess: {
    target_path: string;
    sheetset_values: Record<string, string>;
    groups: CreationGroupBody[];
  };
}

export interface CreationFixtureOptions {
  candidates?: CreationCandidateBody[];
  /** 权威预览响应；默认 `creationPreview()`（三组、含不编号组与多值属性）。 */
  preview?: Record<string, unknown> | null;
  /** 执行入队返回的任务；默认 `creationQueuedJob()`。 */
  executeJob?: Record<string, unknown>;
  /** 任务终态响应；默认 `creationSucceededJob()`（带新建工作区身份）。 */
  jobResult?: Record<string, unknown>;
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
    schema_version: 2,
    standard_id: "szmedi.gas",
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
      {asset_id: "base-a", kind: "base-template", file: "市政基础.dwt", paper_layouts: []},
      {
        asset_id: "layout-a", kind: "layout-template",
        file: "市政图框.dwt",
        paper_layouts: ["A2", "A1"],
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
    version: 1,
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
    version: 7,
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
    version: 1,
    name: "市政燃气施工图",
    draft_id: null,
    ...overrides,
  };
}

/**
 * 权威预览响应（后端结果的替身）：三个图纸组、共 6 张图纸，覆盖不编号组的单值范围
 * （`00`）、多值属性（首张值 + 明细）、首张为空的属性与紧凑标题范围。
 */
export function creationPreview(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const groups = [
    {
      group_id: "group-1",
      created_order: 0,
      title: "封面",
      number_range: "00",
      title_range: "封面",
      base_template: "市政基础.dwt",
      layout_template: "市政图框.dwt",
      paper_layout: "A2",
      dwg_name: "RQ-封面.dwg",
      target_path: "D:\\项目\\新建项目\\RQ-封面.dwg",
      sheet_count: 1,
      sheets: [{number: "00", title: "封面", layout_name: "封面-00", values: {"prop-stage": "施工图", "prop-designer": ""}}],
      property_cells: {
        "prop-stage": {property_id: "prop-stage", first_value: "施工图", sheets: [{number: "00", value: "施工图"}]},
        "prop-designer": {property_id: "prop-designer", first_value: "", sheets: [{number: "00", value: ""}]},
      },
    },
    {
      group_id: "group-2",
      created_order: 1,
      title: "平面图",
      number_range: "01-03",
      title_range: "平面图 (一)-(三)",
      base_template: "市政基础.dwt",
      layout_template: "市政图框.dwt",
      paper_layout: "A1",
      dwg_name: "RQ-平面图.dwg",
      target_path: "D:\\项目\\新建项目\\RQ-平面图.dwg",
      sheet_count: 3,
      sheets: [
        {number: "01", title: "平面图 (一)", layout_name: "平面图-01", values: {"prop-stage": "施工图", "prop-designer": "张工"}},
        {number: "02", title: "平面图 (二)", layout_name: "平面图-02", values: {"prop-stage": "竣工图", "prop-designer": "张工"}},
        {number: "03", title: "平面图 (三)", layout_name: "平面图-03", values: {"prop-stage": "施工图", "prop-designer": "张工"}},
      ],
      property_cells: {
        "prop-stage": {
          property_id: "prop-stage",
          first_value: "施工图",
          sheets: [
            {number: "01", value: "施工图"},
            {number: "02", value: "竣工图"},
            {number: "03", value: "施工图"},
          ],
        },
        "prop-designer": {
          property_id: "prop-designer",
          first_value: "张工",
          sheets: [
            {number: "01", value: "张工"},
            {number: "02", value: "张工"},
            {number: "03", value: "张工"},
          ],
        },
      },
    },
    {
      group_id: "group-3",
      created_order: 2,
      title: "纵断面图",
      number_range: "04-05",
      title_range: "纵断面图",
      base_template: "市政基础.dwt",
      layout_template: "市政图框.dwt",
      paper_layout: "A1",
      dwg_name: "RQ-纵断面图.dwg",
      target_path: "D:\\项目\\新建项目\\RQ-纵断面图.dwg",
      sheet_count: 2,
      sheets: [
        {number: "04", title: "纵断面图", layout_name: "纵断面图-04", values: {"prop-stage": "施工图", "prop-designer": ""}},
        {number: "05", title: "纵断面图", layout_name: "纵断面图-05", values: {"prop-stage": "施工图", "prop-designer": "李工"}},
      ],
      property_cells: {
        "prop-stage": {property_id: "prop-stage", first_value: "施工图", sheets: [{number: "04", value: "施工图"}, {number: "05", value: "施工图"}]},
        "prop-designer": {property_id: "prop-designer", first_value: "", sheets: [{number: "04", value: ""}, {number: "05", value: "李工"}]},
      },
    },
  ];
  return {
    draft_id: "draft-1",
    revision: 2,
    standard_id: "szmedi.gas",
    standard_version: 1,
    standard_name: "市政燃气施工图",
    target_path: "D:\\项目\\新建项目",
    sheetset_values: {"prop-name": "滨河路改造工程", "prop-major": "燃气"},
    group_count: 3,
    sheet_count: 6,
    dwg_count: 3,
    numbering: {sequence_field: "subset.sequence", digits: 2, start: 1},
    suffix: {enabled: false, suffix_type: 0, unnumbered_keywords: ["封面"]},
    diagnostics: [],
    groups,
    executable: true,
    preview_digest: "digest-1",
    ...overrides,
  };
}

/**
 * 带阻断错误与非阻断提示的预览：错误可定位到图纸组行与项目字段，`executable` 为假。
 */
export function creationPreviewWithDiagnostics(): Record<string, unknown> {
  const preview = creationPreview({executable: false});
  preview["diagnostics"] = [
    {
      code: "CREATION_GROUP_TITLE_EMPTY",
      message: "图纸组 'group-1' 的图名不能为空",
      severity: "error",
      group_id: "group-1",
      property_id: "",
    },
    {
      code: "CREATION_REQUIRED_VALUE_MISSING",
      message: "必填属性 '工程名称' 不能为空",
      severity: "error",
      group_id: "",
      property_id: "prop-name",
    },
    {
      code: "DUPLICATE_LAYOUT_NAME",
      message: "目标DWG内布局名重复：平面图-01",
      severity: "warning",
      group_id: "group-1",
      property_id: "",
    },
  ];
  return preview;
}

/**
 * 带「模板/图幅」组内诊断的预览：三种定位分别落在基础模板、图幅与布局模板控件上。
 * `CREATION_ASSET_INVALID` 同时覆盖两种模板资产，故组 1/组 3 用已解析的模板路径
 * （空串表示该资产解析失败）区分到底缺的是基础模板还是布局模板。
 */
export function creationPreviewWithTemplateDiagnostics(): Record<string, unknown> {
  const preview = creationPreview({executable: false});
  const groups = preview["groups"] as Array<Record<string, unknown>>;
  groups[0]!["base_template"] = ""; // 基础模板资产非法
  groups[1]!["paper_layout"] = "A0"; // 图幅不在布局模板的实际布局内
  groups[2]!["layout_template"] = ""; // 布局模板资产非法
  preview["diagnostics"] = [
    {
      code: "CREATION_ASSET_INVALID",
      message: "图纸组 'group-1' 的基础模板资产 'base-x' 不存在或不是基础模板",
      severity: "error",
      group_id: "group-1",
      property_id: "",
    },
    {
      code: "CREATION_PAPER_LAYOUT_INVALID",
      message: "图纸组 'group-2' 的图幅 'A0' 不在布局模板资产 'layout-a' 声明的图幅内",
      severity: "error",
      group_id: "group-2",
      property_id: "",
    },
    {
      code: "CREATION_ASSET_INVALID",
      message: "图纸组 'group-3' 的布局模板资产 'layout-x' 不存在或不是布局模板",
      severity: "error",
      group_id: "group-3",
      property_id: "",
    },
  ];
  return preview;
}

/** 执行入队响应：创建任务在登记前没有普通工作区。 */
export function creationQueuedJob(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "job-1",
    workspace_id: null,
    creation_draft_id: "draft-1",
    status: "QUEUED",
    progress: 0,
    type: "creation",
    cad_version: "2020",
    attempt: 1,
    payload: {creation_draft_id: "draft-1", preview_digest: "digest-1", target_path: "D:\\项目\\新建项目"},
    timeline: [{status: "QUEUED", progress: 0}],
    files: [],
    ...overrides,
  };
}

/** 创建成功终态：登记完成后任务带新建工作区身份（前端据此切换普通工作区）。 */
export function creationSucceededJob(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return creationQueuedJob({
    status: "SUCCEEDED",
    progress: 100,
    workspace_id: "created-1",
    revision_id: "revision-1",
    finished_at: "2026-09-24T10:00:00Z",
    payload: {creation_draft_id: "draft-1", workspace: {id: "created-1", revision_id: "revision-1", dst_path: "D:\\项目\\新建项目\\图纸集.dst"}},
    ...overrides,
  });
}

/** 创建失败终态：目标未留下半成品，草稿与诊断保留供修正后重试。 */
export function creationFailedJob(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return creationQueuedJob({
    status: "FAILED",
    error_code: "CREATION_PUBLISH_FAILED",
    error_detail: "模板资产不可读取",
    finished_at: "2026-09-24T10:00:00Z",
    ...overrides,
  });
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
    previewRequests: 0,
    executeBodies: [],
    jobStreams: 0,
    preview: options.preview === undefined ? creationPreview() : options.preview,
    executeJob: options.executeJob ?? creationQueuedJob(),
    jobResult: options.jobResult ?? creationSucceededJob(),
    importFailure: options.importFailure === undefined ? creationImportFailure() : options.importFailure,
    saveFailure: null,
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
        const body = (await request.postDataJSON()) as {standard_id: string; version: number};
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
      const previewMatch = /^\/api\/creation-drafts\/([^/]+)\/preview$/.exec(path);
      if (previewMatch && method === "POST") {
        state.previewRequests += 1;
        // 权威预览只由后端给出：夹具返回固定替身，前端不得自行推算任何派生输出
        return route.fulfill({json: state.preview ?? creationPreview()});
      }
      const executeMatch = /^\/api\/creation-drafts\/([^/]+)\/execute$/.exec(path);
      if (executeMatch && method === "POST") {
        state.executeBodies.push((await request.postDataJSON()) as Record<string, unknown>);
        return route.fulfill({json: state.executeJob});
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
          if (state.saveFailure !== null) {
            // 保存被拒：草稿 JSON 与修订号零变化
            return route.fulfill({status: state.saveFailure.status, json: state.saveFailure.body});
          }
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

  // 创建任务进度：SSE 一次性给出终态（与后端 `/api/jobs/{id}/events` 同形态），
  // 轮询端点返回同一份终态，供 EventSource 断线回退路径使用
  await page.route(
    url => url.pathname.startsWith("/api/jobs/"),
    route => {
      if (new URL(route.request().url()).pathname.endsWith("/events")) {
        state.jobStreams += 1;
        return route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: `data: ${JSON.stringify(state.jobResult)}\n\n`,
        });
      }
      return route.fulfill({json: state.jobResult});
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
          version: Number(segments[4]),
          name: document["name"],
          supported_cad_versions: document["supported_cad_versions"],
          dependencies: [],
          document: {...document, standard_id: decodeURIComponent(segments[3] ?? ""), version: Number(segments[4])},
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
