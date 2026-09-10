// 扩展页面贡献、动态标签与离开保护 e2e（PLAN-DM-020 Task 10 / ARCH-DM-006 §7）。
// 生命周期场景经 route mock 驱动 GET /api/extensions 与 PATCH /api/extensions/{id}/state；
// 工作区/草稿路由与 main.spec 同模式。断言全部为语义断言（标签顺序、页面边界、
// 三选一模态、焦点归还），不依赖截图或动态 import 路径。
import {expect, test, type Page} from "@playwright/test";

const workspace = {
  id: "workspace-1", revision_id: "revision-1", dst_path: "C:\\project\\test.dst",
  sheet_set: {name: "测试图纸集", sheet_count: 1, subset_count: 1, custom_properties: {}, property_definitions: [], subsets: [
    {id: "subset-1", name: "第一册", title: "第一册", number_range: "001-001", display_name: "第一册", sheets: [
      {id: "sheet-1", number: "001", title: "图纸 001", custom_properties: {}, layout: {file_name: "C:\\project\\001.dwg", relative_file_name: ".\\001.dwg", resolved_path: "C:\\project\\001.dwg", layout_name: "001", handle: "A1"}},
    ]},
  ]}, diagnostics: [],
};

// 与后端 ExtensionSummaryModel 契约同构的最小摘要（name_key/description_key 指向真实清单键）
function extensionSummary(overrides: Record<string, unknown> = {}) {
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

interface ExtensionsState {list: unknown[]; patchBodies: unknown[]}

// 列表可变（PATCH 后更新）以便断言宿主按最新状态收敛标签
async function installExtensions(page: Page, initial: unknown[]): Promise<ExtensionsState> {
  const state: ExtensionsState = {list: initial, patchBodies: []};
  await page.route("**/api/extensions", route => route.fulfill({json: state.list}));
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

async function openWorkspace(page: Page): Promise<void> {
  await page.goto("/");
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\project\\test.dst"; });
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
}

// 标签 id 顺序 = 核心三标签固定顺序 + 扩展页面追加（id 稳定，文本经 i18n 渲染）
async function expectTabIds(page: Page, ids: string[]): Promise<void> {
  await expect.poll(() => page.getByRole("tablist").getByRole("tab").evaluateAll(els => els.map(el => el.id))).toEqual(ids);
}

const CORE_TABS = ["tab-sheets", "tab-properties", "tab-revisions"];

test.beforeEach(async ({page}) => {
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => (window as any).__fakeSelectResult ?? null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/workspaces/open", route => route.fulfill({json: workspace}));
  await page.route("**/api/workspaces/workspace-1", route => route.fulfill({json: workspace}));
  const drafts = new Map<string, any>();
  await page.route("**/api/workspaces/*/draft", async route => {
    const request = route.request();
    const workspaceId = new URL(request.url()).pathname.split("/").at(-2)!;
    const current = drafts.get(workspaceId) ?? null;
    if (request.method() === "GET") return route.fulfill({json: {draft: current, corrupted: false, stale: false, stale_reasons: []}});
    if (request.method() === "DELETE") { drafts.delete(workspaceId); return route.fulfill({json: {deleted: current !== null}}); }
    const body = await request.postDataJSON();
    const saved = {...body, workspace_id: workspaceId, version: (current?.version ?? 0) + 1};
    delete saved.expected_version;
    drafts.set(workspaceId, saved);
    return route.fulfill({json: {draft: saved, corrupted: false, stale: false, stale_reasons: []}});
  });
});

test("无工作区不显示标签栏；扩展 AVAILABLE 且工作区加载后目录标签追加在核心三标签之后并挂载页面边界", async ({page}) => {
  await installExtensions(page, [extensionSummary()]);
  await page.goto("/");
  await expect(page.getByRole("tablist")).toHaveCount(0);
  await openWorkspace(page);
  await expectTabIds(page, [...CORE_TABS, "tab-sheet-catalog"]);
  await page.getByRole("tab", {name: "图纸目录"}).click();
  // 页面边界：扩展名称/描述/版本/状态经宿主 i18n（清单键）渲染
  await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
  await expect(page.getByText("从当前工作区快照生成可配置的图纸目录表，并导出为 XLSX 文件")).toBeVisible();
  await expect(page.getByText("v0.1.0 · 可用")).toBeVisible();
});

test("DISABLED/FAILED/INCOMPATIBLE 时隐藏目录标签，核心三标签顺序固定且核心功能可用", async ({page}) => {
  for (const status of ["DISABLED", "FAILED", "INCOMPATIBLE"]) {
    await installExtensions(page, [extensionSummary({status, enabled: false})]);
    await openWorkspace(page);
    await expectTabIds(page, CORE_TABS);
    await page.getByRole("tab", {name: "属性"}).click();
    await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("测试图纸集");
  }
});

test("未知 route_key 与非 workspace_page 贡献被安全忽略，不产生标签或动态加载", async ({page}) => {
  await installExtensions(page, [
    extensionSummary({
      extension_id: "ext.unknown-route",
      ui_contributions: [
        {contribution_id: "c1", kind: "workspace_page", route_key: "template-browser"},
        {contribution_id: "c2", kind: "workspace_page", route_key: "../../views/SheetsView.vue"},
        {contribution_id: "c3", kind: "status_widget", route_key: "sheet-catalog"},
      ],
    }),
  ]);
  await openWorkspace(page);
  await expectTabIds(page, CORE_TABS);
  await page.getByRole("tab", {name: "图纸"}).click();
  await expect(page.getByRole("button", {name: "预览变更"})).toBeVisible();
});

test("方向键在动态标签列表内循环并切换扩展页面", async ({page}) => {
  await installExtensions(page, [extensionSummary()]);
  await openWorkspace(page);
  await page.getByRole("tab", {name: "图纸目录"}).click();
  await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("tab", {name: "修订历史"})).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", {name: "图纸目录"})).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
});

test("停用当前目录页：无未保存输入直接停用，回图纸页并把焦点归还目录标签原位置的邻近标签", async ({page}) => {
  const ext = await installExtensions(page, [extensionSummary()]);
  await openWorkspace(page);
  await page.getByRole("tab", {name: "图纸目录"}).click();
  await page.getByRole("button", {name: "停用扩展"}).click();
  await expectTabIds(page, CORE_TABS);
  // 回图纸页（核心首个标签成为激活页）
  await expect(page.getByRole("tablist").getByRole("tab").first()).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", {name: "预览变更"})).toBeVisible();
  // 焦点归还：目录标签原在索引 3，移除后原位置的安全邻近元素为末位标签（修订历史）
  await expect.poll(() => page.evaluate(() => document.activeElement?.id)).toBe("tab-revisions");
  // 三选一未出现，停用请求按契约发出
  await expect(page.locator('[role="dialog"][aria-modal="true"]')).toHaveCount(0);
  expect(ext.patchBodies).toEqual([{enabled: false}]);
});

test("停用当前目录页：有未保存输入先三选一，确认后才发出停用并移除标签", async ({page}) => {
  const ext = await installExtensions(page, [extensionSummary()]);
  await openWorkspace(page);
  // 属性页制造未提交输入（会话缓冲跨主标签保留）
  await page.getByRole("tab", {name: "属性"}).click();
  await page.getByLabel("图纸集名称", {exact: true}).fill("未保存名称");
  await page.getByRole("tab", {name: "图纸目录"}).click();
  await page.getByRole("button", {name: "停用扩展"}).click();
  const dialog = page.locator('[role="dialog"][aria-modal="true"]');
  await expect(dialog).toBeVisible();
  expect(ext.patchBodies).toHaveLength(0);
  await dialog.getByRole("button", {name: "放弃输入"}).click();
  await expectTabIds(page, CORE_TABS);
  expect(ext.patchBodies).toEqual([{enabled: false}]);
  await expect(page.getByRole("tablist").getByRole("tab").first()).toHaveAttribute("aria-selected", "true");
  await expect.poll(() => page.evaluate(() => document.activeElement?.id)).toBe("tab-revisions");
});
