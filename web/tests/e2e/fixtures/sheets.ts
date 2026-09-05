// 图纸页单表工作区公共 e2e 夹具（PLAN-DM-015 任务 1 最小版 → 任务 3 扩展为全能力）。
// 默认 5 子集 / 13 图纸 / 36 字段；支持 161 张大列表、空集、无属性、长文本、双状态。
// 只含虚构路径与假壳/假路由；fake 壳持有当前工作区 ID 与独立偏好映射；
// 持久草稿路由保持 expected_version 语义。
import type {Page} from "@playwright/test";
import type {ChangeCommand, Preview, Subset, Workspace} from "../../../src/api/contracts";

export type SheetsFixtureOptions = {
  sheetCount?: number;    // 图纸总数，默认 13
  subsetCount?: number;   // 子集数，默认 5
  propertyCount?: number; // 图纸属性定义数，默认 36
  empty?: boolean;        // 空图纸集（0 子集 0 图纸）
  noProperties?: boolean; // 无属性定义与自定义属性
  longText?: boolean;     // 长标题与超长路径
  dualStatus?: boolean;   // 阻断诊断与待变更并存
  propertyNames?: string[]; // 覆盖图纸属性定义名称（同名内置列等用例）
  // 持久草稿恢复用例：GET 草稿路由返回该预置草稿（模拟上次未完成改动）
  initialDraft?: unknown;
  // 任务 4 列配置用例：预置偏好映射（按工作区 ID），模拟上次会话保存
  initialColumns?: Record<string, unknown>;
  // 任务 4 列配置用例：save/load_sheet_columns 返回 IO 错误（存储失败回退）
  failSaveColumns?: boolean;
  failLoadColumns?: boolean;
  // 任务 4 列配置用例：第二个可打开的工作区（不同 ID），用于跨工作区隔离
  secondWorkspace?: {dstPath: string; id?: string; options?: SheetsFixtureOptions};
  // 任务 5 编辑用例：草稿 PUT 注入失败（返回 422；返回 null 则正常保存，可经闭包一次性/条件触发）
  failDraftSave?: (body: unknown) => {code: string; message: string; fields?: Record<string, string>} | null;
  // 任务 5 编辑用例：工作区 GET 变换（模拟基准刷新/版本变化，闭包可变）
  transformWorkspaceGet?: (workspace: unknown) => unknown;
  // 任务 5 编辑用例：捕获草稿 PUT 请求体（经夹具路由直接回调，不额外安装捕获路由）
  onDraftPut?: (body: unknown) => void;
};

const FAKE_DST = "C:\\虚构工程\\图纸集.dst";
const SUBSET_NAMES = ["建筑施工图", "结构施工图", "给排水施工图", "电气施工图", "暖通施工图"];
const LONG_TITLE = "（超长标题）" + "建筑平面图大样详图之东北角楼梯间与疏散口细部构造做法示意说明".repeat(4);
const LONG_PATH = "C:\\虚构工程\\一期\\地下室\\东北角楼梯间\\细部构造做法示意图\\第 13 分册最终版.dwg";

// 图纸属性定义：前三项使用常用字段名（可用 propertyNames 覆盖），其余按序号命名，共 propertyCount 项
function buildPropertyDefinitions(propertyCount: number, names?: string[]) {
  const NAMES = names ?? ["图幅", "比例", "专业"];
  return Array.from({length: propertyCount}, (_, index) => ({
    type: "sheet" as const,
    name: index < NAMES.length ? NAMES[index] : `属性${String(index + 1).padStart(2, "0")}`,
    default_value: "",
  }));
}

// 把 sheetCount 张图纸均分到 subsetCount 个子集（前多后少），编号连续
function buildSubsets(
  sheetCount: number,
  subsetCount: number,
  opts: {noProperties: boolean; longText: boolean; propertyNames?: string[]},
) {
  const base = Math.floor(sheetCount / subsetCount);
  const remainder = sheetCount % subsetCount;
  const perSubset = Array.from({length: subsetCount}, (_, i) => base + (i < remainder ? 1 : 0));
  let cursor = 0;
  return perSubset.map((count, subsetIndex) => {
    const start = cursor + 1;
    const end = cursor + count;
    cursor = end;
    const suffix = SUBSET_NAMES[subsetIndex] ?? `分册 ${subsetIndex + 1}`;
    const sheets = Array.from({length: count}, (_, sheetIndex) => {
      const ordinal = start + sheetIndex;
      const number = String(ordinal).padStart(3, "0");
      const custom: Record<string, string> = opts.noProperties ? {} : {图幅: "A1", 比例: ordinal % 2 ? "1:100" : "1:50", 专业: "建筑"};
      // 附加（含拉丁名）属性也给出确定性值，供取值按原始大小写键的用例断言
      if (!opts.noProperties) {
        (opts.propertyNames ?? []).forEach((name, index) => {
          if (!(name in custom)) custom[name] = `V${index + 1}`;
        });
      }
      if (!opts.noProperties && ordinal === 7) custom["属性07"] = "特殊隐藏值X7";
      const long = opts.longText && ordinal === sheetCount;
      const file = `C:\\虚构工程\\一期\\${String(subsetIndex + 1).padStart(2, "0")} 分册.dwg`;
      return {
        id: `sheet-${ordinal}`,
        number,
        title: long ? LONG_TITLE : `图纸 ${ordinal}`,
        custom_properties: custom,
        layout: {
          file_name: long ? LONG_PATH : file,
          relative_file_name: long ? `.\\${LONG_PATH.split("\\").at(-1)}` : `.\\${String(subsetIndex + 1).padStart(2, "0")} 分册.dwg`,
          resolved_path: long ? LONG_PATH : file,
          layout_name: `${number} 图纸 ${ordinal}`,
          handle: ordinal.toString(16),
        },
      };
    });
    return {
      id: `subset-${subsetIndex + 1}`,
      name: count ? `${start}-${end} ${suffix}` : `空分册 ${subsetIndex + 1}`,
      title: suffix,
      number_range: count ? `${start}-${end}` : "",
      display_name: count ? `${start}-${end} ${suffix}` : `空分册 ${subsetIndex + 1}`,
      sheets,
    };
  });
}

// 双状态：sheet-1 阻断+待变更并存、sheet-2 待变更、sheet-3 阻断
const DUAL_STATUS_DIAGNOSTICS = [
  {code: "DWG_UNRESOLVED", severity: "error", message: "图纸 001 布局未解析", object_id: "sheet-1"},
  {code: "DWG_UNRESOLVED", severity: "error", message: "图纸 003 布局未解析", object_id: "sheet-3"},
];
const DUAL_STATUS_DRAFT = {
  schema_version: 1,
  workspace_id: "workspace-1",
  base_revision_id: "revision-1",
  repair_status: "VALID",
  version: 1,
  cursor: 2,
  actions: [
    {id: "dual-1", kind: "command_batch", label: "批量属性", commands: [{type: "update_sheet_properties", sheet_id: "sheet-1", custom_properties: {图幅: "A1", 比例: "1:100", 专业: "建筑"}}]},
    {id: "dual-2", kind: "command_batch", label: "批量属性", commands: [{type: "update_sheet_properties", sheet_id: "sheet-2", custom_properties: {图幅: "A1", 比例: "1:50", 专业: "建筑"}}]},
  ],
};

// 虚构工作区：subsets 子集、sheetCount 张图纸，全部路径虚构
function buildWorkspace(options: SheetsFixtureOptions = {}) {
  const {
    sheetCount = 13, subsetCount = 5, propertyCount = 36,
    empty = false, noProperties = false, longText = false, dualStatus = false,
    propertyNames,
  } = options;
  const total = empty ? 0 : sheetCount;
  const subsets = empty ? [] : buildSubsets(sheetCount, subsetCount, {noProperties, longText, propertyNames});
  const propertyDefinitions = noProperties ? [] : [
    {type: "sheetset", name: "项目号", default_value: "P-FAKE"},
    ...buildPropertyDefinitions(propertyCount, propertyNames),
  ];
  return {
    id: "workspace-1",
    revision_id: "revision-1",
    dst_path: FAKE_DST,
    root: "C:\\虚构工程",
    unreferenced_dwgs: [],
    dst_validation: {status: "VALID", actions: [], blocking_issues: []},
    sheet_set: {
      name: "虚构图纸集",
      sheet_count: total,
      subset_count: subsets.length,
      custom_properties: noProperties ? {} : {项目号: "P-FAKE"},
      property_definitions: propertyDefinitions,
      subsets,
    },
    diagnostics: dualStatus ? DUAL_STATUS_DIAGNOSTICS : [],
  };
}

// 权威结构投影的派生文档：既有对象沿用基底 ID，属性/布局取自响应原样
export function derivedDocument(sheetCount: number) {
  const sheets = Array.from({length: sheetCount}, (_, index) => {
    const ordinal = index + 1;
    const number = String(ordinal).padStart(3, "0");
    return {
      acsm_id: `sheet-${ordinal}`,
      number,
      title: `图纸 ${ordinal}`,
      // 既有图纸沿用基底属性（结构派生不合成值编辑；任务 5 以命令簿叠加修正混合批次显示）
      custom_properties: {图幅: "A1", 比例: ordinal % 2 ? "1:100" : "1:50", 专业: "建筑"},
      layout: {
        file_name: `C:\\虚构工程\\分册.dwg`,
        relative_file_name: `.\\分册.dwg`,
        layout_name: `${number} 图纸 ${ordinal}`,
        handle: "",
        resolved_path: null,
        resolution_source: null,
      },
    };
  });
  return {
    subsets: [
      {
        acsm_id: "subset-1",
        title: "平面图",
        number_range: sheetCount === 1 ? "1" : `1-${sheetCount}`,
        display_name: `1-${sheetCount} 平面图`,
        source_target_file: `C:\\虚构工程\\分册.dwg`,
        target_file: `C:\\虚构工程\\1-${sheetCount} 平面图.dwg`,
        sheets,
      },
    ],
    affected_subset_ids: ["subset-1"],
    property_diff: {added: [], skipped: []},
    layout_sources: {},
  };
}

// 最小可执行的结构预览响应（execution_intent.derived_document 权威显示）
export function previewResponse(sheetCount: number) {
  return {
    workspace_id: "workspace-1",
    base_revision_id: "revision-1",
    cad_version: "2020",
    requires_cad: true,
    affected_files: ["C:\\虚构工程\\图纸集.dst"],
    execution_intent: {
      groups: [],
      cardinality_frontier: null,
      subset_operations: [],
      deleted_subsets: [],
      path_graph: {old_sources: [], final_targets: [], reused_targets: [], delete_targets: [], transitions: []},
      affected_subset_ids: ["subset-1"],
      derived_document: derivedDocument(sheetCount),
      source_baselines: [],
      cad_validation_deferred: true,
      expected_file_hashes: {},
      estimate: null,
    },
    semantic_diff: {sheet_set: [], structure: {before: [], after: []}, properties: [], dwgs: []},
    preview_digest: "digest-fake",
    changes: [],
    diagnostics: [],
    executable: true,
  };
}

// 参照表单测试用的“智能投影”（任务 6）：把当前命令应用到基底工作区，生成权威派生文档，
// 模拟服务端对 insert/delete/rename 的派生结果——既有对象沿用基底 ID 与顺序，
// 新增对象使用独立派生 ID（sheet-der-N/subset-der-N），前端必须从派生结果取得而非按计数拼造。
export function buildPreviewFromBase(base: Workspace, commands: ChangeCommand[]): Preview {
  const subsets = JSON.parse(JSON.stringify(base.sheet_set.subsets)) as Subset[];
  let sheetSeq = 1000;
  let subsetSeq = 100;
  // 基底子集图纸用 id 键（派生文档映射时经 acsm_id 对齐），新增对象同样用 id 键保持一致
  const derivedSheet = (ordinal: number) => ({
    id: `sheet-der-${sheetSeq++}`,
    number: String(ordinal).padStart(3, "0"),
    title: `派生图纸 ${ordinal}`,
    custom_properties: {} as Record<string, string>,
    layout: {file_name: "C:\\虚构工程\\派生.dwg", relative_file_name: ".\\派生.dwg", layout_name: "", handle: "", resolved_path: null, resolution_source: null},
  });
  for (const command of commands) {
    switch (command.type) {
      case "delete_sheet":
        for (const subset of subsets) subset.sheets = subset.sheets.filter((s) => s.id !== command.sheet_id);
        break;
      case "insert_sheet": {
        const subset = subsets.find((s) => s.id === command.target_subset_id);
        if (!subset) break;
        const index = Math.min(Math.max((command.ordinal ?? 1) - 1, 0), subset.sheets.length);
        const at = command.placement === "before" ? index : index + 1;
        const inserted = Array.from({length: command.count}, (_, i) => derivedSheet(at + i + 1));
        subset.sheets.splice(at, 0, ...inserted);
        break;
      }
      case "delete_subset": {
        const index = subsets.findIndex((s) => s.id === command.subset_id);
        if (index >= 0) subsets.splice(index, 1);
        break;
      }
      case "insert_subset": {
        const index = Math.min(Math.max((command.ordinal ?? 1) - 1, 0), subsets.length);
        const at = command.placement === "before" ? index : index + 1;
        const id = `subset-der-${subsetSeq++}`;
        const sheets = Array.from({length: command.initial_sheet_count}, (_, i) => derivedSheet(at * 100 + i + 1));
        subsets.splice(at, 0, {id, name: command.title, title: command.title, number_range: "", display_name: command.title, sheets});
        break;
      }
      case "update_subset_title": {
        const subset = subsets.find((s) => s.id === command.subset_id);
        if (subset) { subset.title = command.title; subset.display_name = command.title; subset.name = command.title; }
        break;
      }
      case "update_sheet_properties": {
        const sheet = subsets.flatMap((s) => s.sheets).find((s) => s.id === command.sheet_id);
        if (sheet) sheet.custom_properties = {...command.custom_properties};
        break;
      }
      default:
        break; // update_sheet_set / 属性定义增删不改变派生结构
    }
  }
  const derivedSubsets = subsets.map((subset) => ({
    acsm_id: subset.id,
    title: subset.title,
    number_range: subset.number_range ?? "",
    display_name: subset.display_name,
    source_target_file: "",
    target_file: "",
    sheets: subset.sheets.map((sheet) => ({
      acsm_id: sheet.id,
      number: sheet.number,
      title: sheet.title,
      custom_properties: sheet.custom_properties,
      layout: {
        file_name: sheet.layout.file_name,
        relative_file_name: sheet.layout.relative_file_name,
        layout_name: sheet.layout.layout_name,
        handle: sheet.layout.handle ?? "",
        resolved_path: sheet.layout.resolved_path ?? null,
        resolution_source: null,
      },
    })),
  }));
  return {
    workspace_id: base.id,
    base_revision_id: base.revision_id,
    cad_version: "2020",
    requires_cad: true,
    affected_files: [base.dst_path],
    execution_intent: {
      groups: [],
      cardinality_frontier: null,
      subset_operations: [],
      deleted_subsets: [],
      path_graph: {old_sources: [], final_targets: [], reused_targets: [], delete_targets: [], transitions: []},
      affected_subset_ids: derivedSubsets.map((s) => s.acsm_id),
      derived_document: {
        subsets: derivedSubsets,
        affected_subset_ids: derivedSubsets.map((s) => s.acsm_id),
        property_diff: {added: [], skipped: []},
        layout_sources: {},
      },
      source_baselines: [],
      cad_validation_deferred: true,
      expected_file_hashes: {},
      estimate: null,
    },
    semantic_diff: {sheet_set: [], structure: {before: [], after: []}, properties: [], dwgs: []},
    preview_digest: "digest-fake",
    changes: [],
    diagnostics: [],
    executable: true,
  };
}

// 安装基于 buildPreviewFromBase 的智能投影路由（任务 6 表单测试用；既有测试仍可自行覆盖路由）
export async function installSmartPreview(page: Page, base: Workspace): Promise<void> {
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => {
    const body = route.request().postDataJSON() as {commands: ChangeCommand[]};
    route.fulfill({json: buildPreviewFromBase(base, body.commands)});
  });
}

// 全能力夹具：假壳（持有当前 ID 与独立偏好映射）+ 打开/工作区/持久草稿路由；
// 预览路由由各测试自装（投影门禁需要 gate）；返回基底工作区供智能投影复用。
export async function installSheetsFixture(page: Page, options: SheetsFixtureOptions = {}): Promise<{workspace: Workspace}> {
  const workspace = buildWorkspace(options);
  const initialDraft = options.dualStatus && !options.initialDraft ? DUAL_STATUS_DRAFT : options.initialDraft;
  const secondWorkspace = options.secondWorkspace
    ? (() => {
        const ws2 = buildWorkspace(options.secondWorkspace?.options);
        ws2.id = options.secondWorkspace!.id ?? "workspace-2";
        ws2.dst_path = options.secondWorkspace!.dstPath;
        return ws2;
      })()
    : null;
  const failLoad = options.failLoadColumns ?? false;
  const failSave = options.failSaveColumns ?? false;
  const initialColumns = options.initialColumns ?? {};
  const transformWorkspaceGet = options.transformWorkspaceGet;
  await page.addInitScript(({failLoad, failSave, initialColumns}) => {
    (window as any).__sheetsShell = {
      currentWorkspaceId: null,
      preferences: new Map(Object.entries(initialColumns)),
    };
    (window as any).pywebview = {
      api: {
        // 未显式设置选择结果时默认打开虚构 DST，便于「单表初始范围」等用例直点打开按钮
        select_file: async () => (window as any).__fakeSelectResult ?? "C:\\虚构工程\\图纸集.dst",
        on_files_dropped: async () => {},
        open_workspace_folder: async (workspaceId: string) => { (window as any).__sheetsShell.currentWorkspaceId = workspaceId; return {ok: true, value: null}; },
        load_sheet_columns: async (workspaceId: string) => {
          if (failLoad) return {ok: false, code: "SHEET_PREFERENCES_IO", message: "读取列配置失败"};
          return {ok: true, value: (window as any).__sheetsShell.preferences.get(workspaceId) ?? null};
        },
        save_sheet_columns: async (workspaceId: string, preferences: unknown) => {
          if (failSave) return {ok: false, code: "SHEET_PREFERENCES_IO", message: "磁盘只读"};
          (window as any).__sheetsShell.preferences.set(workspaceId, preferences);
          return {ok: true, value: null};
        },
        clear_workspace_context: async (workspaceId: string) => { if ((window as any).__sheetsShell.currentWorkspaceId === workspaceId) (window as any).__sheetsShell.currentWorkspaceId = null; return {ok: true, value: null}; },
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  }, {failLoad, failSave, initialColumns});
  // 打开路由按 DST 路径分发：第二工作区命中时返回不同 ID，否则返回主工作区
  await page.route("**/api/workspaces/open", async (route) => {
    if (secondWorkspace) {
      const body = await route.request().postDataJSON();
      if (body?.dst_path === secondWorkspace.dst_path) return route.fulfill({json: secondWorkspace});
    }
    return route.fulfill({json: workspace});
  });
  await page.route("**/api/workspaces/workspace-1", (route) => {
    const body = transformWorkspaceGet ? transformWorkspaceGet(workspace) : workspace;
    return route.fulfill({json: body});
  });
  if (secondWorkspace) {
    await page.route(`**/api/workspaces/${secondWorkspace.id}`, (route) => route.fulfill({json: secondWorkspace}));
  }
  const drafts = new Map<string, any>();
  await page.route("**/api/workspaces/*/draft", async (route) => {
    const request = route.request();
    const workspaceId = new URL(request.url()).pathname.split("/").at(-2)!;
    const current = drafts.get(workspaceId) ?? initialDraft ?? null;
    if (request.method() === "GET") return route.fulfill({json: {draft: current, corrupted: false, stale: false, stale_reasons: []}});
    if (request.method() === "DELETE") {
      drafts.delete(workspaceId);
      return route.fulfill({json: {deleted: current !== null}});
    }
    const body = await request.postDataJSON();
    // 任务 5：草稿保存失败注入（提交失败/字段错误/DRAFT_CONFLICT 用例），返回 null 走正常保存
    options.onDraftPut?.(body);
    const failure = options.failDraftSave?.(body) ?? null;
    if (failure) return route.fulfill({status: 422, json: failure});
    const saved = {...body, workspace_id: workspaceId, version: (current?.version ?? 0) + 1};
    delete saved.expected_version;
    drafts.set(workspaceId, saved);
    return route.fulfill({json: {draft: saved, corrupted: false, stale: false, stale_reasons: []}});
  });
  return {workspace};
}
