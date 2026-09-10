// 设置中心扩展分区 e2e（本次修复：停用后必须存在可再次启用的入口）。
// 背景：启停控件原先只长在扩展自己的页面上（SheetCatalogView 的「停用扩展」），
// 而 ARCH-DM-006 §7 要求停用后移除页面入口，于是开关变成单向、用户被永久卡死
// （extension_states.enabled 持久化为 false，重启对账仍会重新停掉）。
// 修复后设置中心成为唯一启停入口，扩展页面不再提供停用。
//
// PLAN-DM-022 修订：启停控件改为滑动开关（role=switch + aria-checked + 可见状态文字），
// 且停用不再关闭设置对话框。原先必须关窗让出 top layer，是因为闸门模态当时是页面内联
// 遮罩；两个闸门（宿主未提交输入三选一、目录页三选一）现已改为原生 <dialog showModal>，
// 自行进入 top layer 叠在设置窗口之上。本文件因此钉住两项新契约：
// 1) 停用后对话框保留、开关就地翻转、由用户手动关闭；
// 2) 闸门叠在设置窗口之上可见可点，且 Esc 只作用于最上层（不会连带关掉设置窗口）。
//
// 契约红线：只 mock /api/extensions（真实后端会写用户 .dst-manager-data/dst-manager.db
// 的 extension_states，禁止）；/api/settings 与 /api/about 走真实后端（global-setup
// 已隔离配置目录）。本文件不保存设置，以免干扰 settings-dialog.spec.ts 的串行基线。
import {expect, test, type Page} from "@playwright/test";
import {expectDialog} from "./fixtures/settings";

const workspace = {
  id: "workspace-1", revision_id: "revision-1", dst_path: "C:\\project\\test.dst",
  sheet_set: {name: "测试图纸集", sheet_count: 1, subset_count: 1, custom_properties: {}, property_definitions: [], subsets: [
    {id: "subset-1", name: "第一册", title: "第一册", number_range: "001-001", display_name: "第一册", sheets: [
      {id: "sheet-1", number: "001", title: "图纸 001", custom_properties: {}, layout: {file_name: "C:\\project\\001.dwg", relative_file_name: ".\\001.dwg", resolved_path: "C:\\project\\001.dwg", layout_name: "001", handle: "A1"}},
    ]},
  ]}, diagnostics: [],
};

// 与后端 ExtensionSummaryModel 契约同构的最小摘要（name_key 指向真实清单键）
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

interface ExtensionsState {list: unknown[]; patchBodies: unknown[]; listRequests: number}

// 列表可变（PATCH 后更新）以便断言宿主按最新状态收敛标签与开关
async function installExtensions(page: Page, initial: unknown[]): Promise<ExtensionsState> {
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

async function openWorkspace(page: Page): Promise<void> {
  await page.goto("/");
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\project\\test.dst"; });
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
}

// 打开设置并切到扩展分区（分区存在即证明宿主把扩展管理收进了设置中心）
async function openExtensionsSection(page: Page): Promise<void> {
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  await page.getByRole("tab", {name: "扩展"}).click();
}

async function expectTabIds(page: Page, ids: string[]): Promise<void> {
  // 限定到外壳标签栏：设置对话框的分区导航同样是 role="tablist"，
  // 而停用不再关窗，断言时两个 tablist 会同时存在
  await expect.poll(() => page.locator(".tabbar").getByRole("tab").evaluateAll(els => els.map(el => el.id))).toEqual(ids);
}

const CORE_TABS = ["tab-sheets", "tab-properties", "tab-revisions"];
const SETTINGS_DIALOG = 'dialog[aria-labelledby="settings-title"]';

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

test("无工作区也能看到扩展列表并启用（列表不依赖工作区加载）", async ({page}) => {
  const ext = await installExtensions(page, [extensionSummary({status: "DISABLED", enabled: false})]);
  await page.goto("/");
  // 前置：无工作区时没有标签栏，扩展页面入口不存在——入口只能来自设置中心
  await expect(page.getByRole("tablist")).toHaveCount(0);
  await openExtensionsSection(page);
  await expect(page.getByText("图纸目录", {exact: true})).toBeVisible();
  await expect(page.getByText("v0.1.0 · 已停用")).toBeVisible();
  // 立即生效语义：分区内必须有明确说明，避免与底部「取消」产生误导
  await expect(page.getByText("扩展启停立即生效，不受下方取消影响。")).toBeVisible();
  // 滑动开关：方向由 aria-checked 表达，可见状态文字与之一致（不靠颜色单向传达）
  const off = page.getByRole("switch", {name: "启用 图纸目录"});
  await expect(off).toHaveAttribute("aria-checked", "false");
  await expect(page.locator(".ext-state")).toHaveText("已停用");
  await off.click();
  await expect.poll(() => ext.patchBodies).toEqual([{enabled: true}]);
  await expect(page.getByText("v0.1.0 · 可用")).toBeVisible();
  await expect(page.getByRole("switch", {name: "停用 图纸目录"})).toHaveAttribute("aria-checked", "true");
  await expect(page.locator(".ext-state")).toHaveText("已启用");
});

test("停用不关窗：对话框保留、开关就地翻转、标签移除；再拨回启用标签恢复（停用可逆的核心钉子）", async ({page}) => {
  const ext = await installExtensions(page, [extensionSummary()]);
  await openWorkspace(page);
  await expectTabIds(page, [...CORE_TABS, "tab-sheet-catalog"]);

  // 先进入目录页：被移除的就是当前页，作为“停用真的生效于页面入口”的前置
  await expect(page.locator("#tab-sheet-catalog")).toBeEnabled();
  await page.getByRole("tab", {name: "图纸目录"}).click();
  await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
  await page.getByRole("button", {name: "设置"}).click();
  await page.getByRole("tab", {name: "扩展"}).click();

  // 停用：对话框保留（不再由停用触发关闭），开关与状态文字就地收敛
  await page.getByRole("switch", {name: "停用 图纸目录"}).click();
  await expect.poll(() => ext.patchBodies).toEqual([{enabled: false}]);
  await expect(page.locator(SETTINGS_DIALOG)).toBeVisible();
  await expect(page.getByRole("switch", {name: "启用 图纸目录"})).toHaveAttribute("aria-checked", "false");
  await expect(page.locator(".ext-state")).toHaveText("已停用");
  await expect(page.getByText("v0.1.0 · 已停用")).toBeVisible();
  // 标签移除发生在对话框背后（top layer 遮挡）；焦点留在对话框内的同一开关上
  await expectTabIds(page, CORE_TABS);
  await expect.poll(() => page.evaluate(() => document.activeElement?.classList.contains("switch"))).toBe(true);

  // 重新启用：仍在同一对话框内，入口始终可达（这正是本次修复的目标）
  await page.getByRole("switch", {name: "启用 图纸目录"}).click();
  await expect.poll(() => ext.patchBodies).toEqual([{enabled: false}, {enabled: true}]);
  await expect(page.getByRole("switch", {name: "停用 图纸目录"})).toHaveAttribute("aria-checked", "true");
  await expectTabIds(page, [...CORE_TABS, "tab-sheet-catalog"]);

  // 关闭窗口由用户手动触发（停用不再抢着关窗）；关闭后标签恢复且可进入
  await page.keyboard.press("Escape");
  await expect(page.locator(SETTINGS_DIALOG)).toBeHidden();
  await page.getByRole("tab", {name: "图纸目录"}).click();
  await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
});

test("设置内有未保存修改时点停用：编辑保留、对话框不关闭、不再弹放弃确认", async ({page}) => {
  const ext = await installExtensions(page, [extensionSummary()]);
  await openWorkspace(page);
  await openExtensionsSection(page);
  // 制造设置中心自身的未保存编辑（切到常规分区修改，不回填保存）
  await page.getByRole("tab", {name: "常规配置"}).click();
  await page.locator('input[data-key="cad_timeout_seconds"]').fill("777");
  await page.getByRole("tab", {name: "扩展"}).click();

  // 停用不再关闭对话框，也就不再会丢弃设置编辑：不得再弹「放弃修改并关闭」确认
  await page.getByRole("switch", {name: "停用 图纸目录"}).click();
  await expect.poll(() => ext.patchBodies).toEqual([{enabled: false}]);
  await expect(page.locator(`${SETTINGS_DIALOG} [role="dialog"][aria-modal="true"]`)).toHaveCount(0);
  await expect(page.locator(SETTINGS_DIALOG)).toBeVisible();
  // 编辑缓冲原样保留
  await page.getByRole("tab", {name: "常规配置"}).click();
  await expect(page.locator('input[data-key="cad_timeout_seconds"]')).toHaveValue("777");
});

test("目录页有未保存草稿时从设置中心停用：三选一叠在设置窗口之上且可点，停用不关设置窗口", async ({page}) => {
  const ext = await installExtensions(page, [extensionSummary()]);
  await openWorkspace(page);
  // 属性页制造未提交输入（会话缓冲跨主标签保留）
  await page.getByRole("tab", {name: "属性"}).click();
  await page.getByLabel("图纸集名称", {exact: true}).fill("未保存名称");
  await openExtensionsSection(page);
  await page.getByRole("switch", {name: "停用 图纸目录"}).click();

  // 关键断言：闸门是原生模态，自行进入 top layer 叠在设置窗口之上（可见且可点），
  // 且此时尚未发出停用
  const dialog = page.getByRole("dialog", {name: "未提交输入"});
  await expect(dialog).toBeVisible();
  expect(ext.patchBodies).toHaveLength(0);
  await dialog.getByRole("button", {name: "放弃输入"}).click();
  await expect.poll(() => ext.patchBodies).toEqual([{enabled: false}]);
  // 设置窗口保持打开（不再由停用触发关闭），开关就地翻转
  await expect(page.locator(SETTINGS_DIALOG)).toBeVisible();
  await expect(page.getByRole("switch", {name: "启用 图纸目录"})).toHaveAttribute("aria-checked", "false");
  await expectTabIds(page, CORE_TABS);
});

test("闸门内按 Esc = 留在此处：只关闸门，不连带关闭设置窗口", async ({page}) => {
  const ext = await installExtensions(page, [extensionSummary()]);
  await openWorkspace(page);
  await page.getByRole("tab", {name: "属性"}).click();
  await page.getByLabel("图纸集名称", {exact: true}).fill("未保存名称");
  await openExtensionsSection(page);
  await page.getByRole("switch", {name: "停用 图纸目录"}).click();
  const guard = page.getByRole("dialog", {name: "未提交输入"});
  await expect(guard).toBeVisible();
  await page.keyboard.press("Escape");
  // 原生模态的 cancel 只作用于最上层：闸门关闭（留在此处），设置窗口与编辑都还在
  await expect(guard).toBeHidden();
  await expect(page.locator(SETTINGS_DIALOG)).toBeVisible();
  expect(ext.patchBodies).toHaveLength(0);
  // 焦点归还到触发开关，键盘用户不丢位置
  await expect.poll(() => page.evaluate(() => (document.activeElement as HTMLElement | null)?.getAttribute("aria-checked"))).toBe("true");
});

test("启停失败就地行内呈现且对话框不关闭；服务端权威值未变时开关不乐观翻转", async ({page}) => {
  await page.route("**/api/extensions", route => route.fulfill({json: [extensionSummary()]}));
  await page.route("**/api/extensions/*/state", route => route.fulfill({
    status: 503,
    json: {code: "EXTENSION_CAPABILITY_UNAVAILABLE", message_key: "errors.extension.capabilityUnavailable", params: {}, message: "boom"},
  }));
  await openWorkspace(page);
  await openExtensionsSection(page);
  await page.getByRole("switch", {name: "停用 图纸目录"}).click();
  await expect(page.locator(`${SETTINGS_DIALOG} .ext-error`)).toBeVisible();
  await expect(page.locator(SETTINGS_DIALOG)).toBeVisible();
  await expect(page.getByRole("switch", {name: "停用 图纸目录"})).toHaveAttribute("aria-checked", "true");
});

test("扩展列表加载失败时给出可见降级与重试，不静默呈现为空", async ({page}) => {
  let fail = true;
  await page.route("**/api/extensions", route => fail
    ? route.fulfill({status: 500, json: {code: "INTERNAL_ERROR", message: "boom"}})
    : route.fulfill({json: [extensionSummary({status: "DISABLED", enabled: false})]}));
  await page.goto("/");
  await openExtensionsSection(page);
  await expect(page.getByText("扩展列表加载失败。")).toBeVisible();
  await expect(page.getByText("没有已登记的扩展")).toBeHidden();
  fail = false;
  await page.getByRole("button", {name: "重试"}).click();
  await expect(page.getByText("v0.1.0 · 已停用")).toBeVisible();
});
