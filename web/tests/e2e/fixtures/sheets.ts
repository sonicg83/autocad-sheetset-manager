// 图纸页单表工作区公共 e2e 夹具（PLAN-DM-015 任务 1 最小版）。
// 只含虚构路径与假壳/假路由；任务 3 再扩展为全能力夹具（5 子集/13 图纸/36 字段等）。
import type {Page} from "@playwright/test";

export type SheetsFixtureOptions = {
  sheetCount?: number;
  propertyCount?: number;
};

// 虚构工作区：单子集 sheetCount 张图纸，全部路径虚构
function buildWorkspace(sheetCount: number, propertyCount: number) {
  const sheets = Array.from({length: sheetCount}, (_, index) => {
    const ordinal = index + 1;
    const number = String(ordinal).padStart(3, "0");
    return {
      id: `sheet-${ordinal}`,
      number,
      title: `图纸 ${ordinal}`,
      custom_properties: {比例: "1:100"},
      layout: {
        file_name: `C:\\虚构工程\\${String(ordinal).padStart(2, "0")} 分册.dwg`,
        relative_file_name: `.\\${String(ordinal).padStart(2, "0")} 分册.dwg`,
        resolved_path: `C:\\虚构工程\\${String(ordinal).padStart(2, "0")} 分册.dwg`,
        layout_name: `${number} 图纸 ${ordinal}`,
        handle: ordinal.toString(16),
      },
    };
  });
  return {
    id: "workspace-1",
    revision_id: "revision-1",
    dst_path: "C:\\虚构工程\\图纸集.dst",
    sheet_set: {
      name: "虚构图纸集",
      sheet_count: sheetCount,
      subset_count: 1,
      custom_properties: {项目号: "P-FAKE"},
      property_definitions: [
        {type: "sheetset", name: "项目号", default_value: "P-FAKE"},
        ...Array.from({length: propertyCount}, (_, index) => ({type: "sheet", name: `属性${index + 1}`, default_value: ""})),
      ],
      subsets: [
        {
          id: "subset-1",
          name: `1-${sheetCount} 平面图`,
          title: "平面图",
          number_range: `1-${sheetCount}`,
          display_name: `1-${sheetCount} 平面图`,
          sheets,
        },
      ],
    },
    diagnostics: [],
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
      custom_properties: {比例: "1:100"},
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

// 最小夹具：假壳 + 打开/工作区/持久草稿路由；预览路由由各测试自装（投影门禁需要 gate）
export async function installSheetsFixture(page: Page, options: SheetsFixtureOptions = {}): Promise<void> {
  const {sheetCount = 15, propertyCount = 1} = options;
  const workspace = buildWorkspace(sheetCount, propertyCount);
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => (window as any).__fakeSelectResult ?? null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/workspaces/open", (route) => route.fulfill({json: workspace}));
  await page.route("**/api/workspaces/workspace-1", (route) => route.fulfill({json: workspace}));
  const drafts = new Map<string, any>();
  await page.route("**/api/workspaces/*/draft", async (route) => {
    const request = route.request();
    const workspaceId = new URL(request.url()).pathname.split("/").at(-2)!;
    const current = drafts.get(workspaceId) ?? null;
    if (request.method() === "GET") return route.fulfill({json: {draft: current, corrupted: false, stale: false, stale_reasons: []}});
    if (request.method() === "DELETE") {
      drafts.delete(workspaceId);
      return route.fulfill({json: {deleted: current !== null}});
    }
    const body = await request.postDataJSON();
    const saved = {...body, workspace_id: workspaceId, version: (current?.version ?? 0) + 1};
    delete saved.expected_version;
    drafts.set(workspaceId, saved);
    return route.fulfill({json: {draft: saved, corrupted: false, stale: false, stale_reasons: []}});
  });
}
