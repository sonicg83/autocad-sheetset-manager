// 设置中心扩展分区 e2e（本次修复：停用后必须存在可再次启用的入口）。
// 背景：启停控件原先只长在扩展自己的页面上（SheetCatalogView 的「停用扩展」），
// 而 ARCH-DM-006 §7 要求停用后移除页面入口，于是开关变成单向、用户被永久卡死
// （extension_states.enabled 持久化为 false，重启对账仍会重新停掉）。
// 修复后设置中心成为唯一启停入口，扩展页面不再提供停用。
//
// SPEC-DM-011 修订「启停交互改进」：启停控件改为滑动开关（role=switch + aria-checked + 可见状态文字），
// 且停用不再关闭设置对话框。原先必须关窗让出 top layer，是因为闸门模态当时是页面内联
// 遮罩；两个闸门（宿主未提交输入三选一、目录页三选一）现已改为原生 <dialog showModal>，
// 自行进入 top layer 叠在设置窗口之上。本文件因此钉住两项新契约：
// 1) 停用后对话框保留、开关就地翻转、由用户手动关闭；
// 2) 闸门叠在设置窗口之上可见可点，且 Esc 只作用于最上层（不会连带关掉设置窗口）。
//
// 契约红线：只 mock /api/extensions 与 /api/extensions/*/settings（真实后端会写用户
// .dst-manager-data/dst-manager.db 的 extension_states，禁止）；/api/settings 与 /api/about
// 走真实后端（global-setup 已隔离配置目录）。本文件不保存核心设置，以免干扰
// settings-dialog.spec.ts 的串行基线——扩展设置保存只打本扩展的端点（SC-17 独立保存）。
import {expect, test, type Page} from "@playwright/test";
import {expectDialog} from "./fixtures/settings";
import {extensionSummary, generatedSettingsItems, installExtensionSettings, installExtensions} from "./fixtures/extensions";

const workspace = {
  id: "workspace-1", revision_id: "revision-1", dst_path: "C:\\project\\test.dst",
  sheet_set: {name: "测试图纸集", sheet_count: 1, subset_count: 1, custom_properties: {}, property_definitions: [], subsets: [
    {id: "subset-1", name: "第一册", title: "第一册", number_range: "001-001", display_name: "第一册", sheets: [
      {id: "sheet-1", number: "001", title: "图纸 001", custom_properties: {}, layout: {file_name: "C:\\project\\001.dwg", relative_file_name: ".\\001.dwg", resolved_path: "C:\\project\\001.dwg", layout_name: "001", handle: "A1"}},
    ]},
  ]}, diagnostics: [],
};

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
  const card = page.locator('[data-extension-id="dst-manager.sheet-catalog"]');
  await expect(card.locator(".ext-meta")).toContainText("v0.1.0");
  await expect(card.locator(".ext-meta")).toContainText("已停用");
  // 立即生效语义：分区内必须有明确说明，避免与底部「取消」产生误导
  await expect(page.getByText("扩展启停立即生效，不受下方取消影响。")).toBeVisible();
  // 滑动开关：方向由 aria-checked 表达，可见状态文字与之一致（不靠颜色单向传达）
  const off = page.getByRole("switch", {name: "启用 图纸目录"});
  await expect(off).toHaveAttribute("aria-checked", "false");
  await expect(page.locator(".ext-state")).toHaveText("已停用");
  await off.click();
  await expect.poll(() => ext.patchBodies).toEqual([{enabled: true}]);
  await expect(card.locator(".ext-meta")).toContainText("可用");
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
  await expect(page.locator('[data-extension-id="dst-manager.sheet-catalog"] .ext-meta')).toContainText("已停用");
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
  await expect(page.locator('[data-extension-id="dst-manager.sheet-catalog"] .ext-meta')).toContainText("已停用");
});

test("SC-16 卡片四层信息与不可点击：声明设置时可聚焦元素为「配置 → 开关」，未声明时只有开关", async ({page}) => {
  const ext = await installExtensions(page, [
    extensionSummary({status: "FAILED", enabled: true, error_code: "EXTENSION_START_FAILED"}),
    extensionSummary({extension_id: "demo.plain", name_key: "无设置扩展", description_key: "未声明设置的扩展只能启停。", settings_contribution: null, ui_contributions: []}),
  ]);
  await openWorkspace(page);
  await openExtensionsSection(page);

  const card = page.locator('[data-extension-id="dst-manager.sheet-catalog"]');
  // 四层：名称 + 描述（description_key）/ 版本 / 状态徽标 + 诊断码 / 动作行（配置 → 状态文字 → 开关）
  await expect(card.getByText("图纸目录", {exact: true})).toBeVisible();
  await expect(card.getByText("从当前工作区快照生成可配置的图纸目录表，并导出为 XLSX 文件")).toBeVisible();
  await expect(card.getByText("v0.1.0")).toBeVisible();
  await expect(card.locator(".badge", {hasText: "启动失败"})).toBeVisible();
  await expect(card.getByText("诊断码 EXTENSION_START_FAILED")).toBeVisible();
  // 「已启用 + 启动失败」必须同时成立：开关在开位，状态文字为已启用
  await expect(card.getByRole("switch", {name: "停用 图纸目录"})).toHaveAttribute("aria-checked", "true");
  await expect(card.locator(".ext-state")).toHaveText("已启用");
  // SC-17：声明设置时动作行出现「配置」，卡片内可聚焦元素按 DOM 顺序为「配置 → 开关」
  const actionRow = (locator: import("@playwright/test").Locator) => locator.evaluate(el => Array.from(el.querySelectorAll("[tabindex],a[href],button,[role=button],[role=link]")).map(n => n.tagName + (n.getAttribute("role") ? `[${n.getAttribute("role")}]` : "")));
  expect(await actionRow(card)).toEqual(["BUTTON", "BUTTON[switch]"]);
  await expect(card.getByRole("button", {name: "配置 图纸目录"})).toBeVisible();
  // 未声明设置的卡片不出现「配置」：卡片内只剩开关（原 SC-16 事实保留）
  expect(await actionRow(page.locator('[data-extension-id="demo.plain"]'))).toEqual(["BUTTON[switch]"]);
  // 卡片本体仍不可点击、不导航、不可聚焦：容器不是按钮/链接、不带 tabindex 与 role，点击名称不进入子视图
  const plain = page.locator('[data-extension-id="demo.plain"]');
  expect(await plain.evaluate(el => ({tag: el.tagName, tabindex: el.getAttribute("tabindex"), role: el.getAttribute("role"), href: el.getAttribute("href")}))).toEqual({tag: "LI", tabindex: null, role: null, href: null});
  await card.locator(".ext-name").click();
  await expect(page.locator('[data-view="extension-config"]')).toHaveCount(0);
  await expect(page.locator(".ext-list").first()).toBeVisible();
  // 状态徽标与开关方向来自不同权威：FAILED 不改变开关方向（不由 status 反推）
  expect(ext.patchBodies).toHaveLength(0);
});

// ---- SC-17：扩展全局设置入口（统一入口、同一对话框子视图、按扩展独立保存、脏状态闸门）----
// 生产固定索引只登记图纸目录一条 custom 声明且白名单专属面板属任务 8（R5/R17）：
// generated 场景与设置端点全部由 tests/e2e/fixtures/extensions.ts 装配，不新增生产扩展。

const GENERATED_ID = "demo.frame-update";
const GENERATED_NAME = "图框批量更新";

// 虚构 generated 扩展（Demo 的 g4-14 同一条；不写入 src/dst_manager/extensions/builtin/index.py）
function generatedExtension(overrides: Record<string, unknown> = {}) {
  return extensionSummary({
    extension_id: GENERATED_ID,
    name_key: GENERATED_NAME,
    description_key: "按图框属性表批量替换图框块并回写标题栏字段。",
    status: "DISABLED",
    enabled: false,
    settings_contribution: {presentation: "generated"},
    ...overrides,
  });
}

// 子视图容器（同一标记与冻结 Demo 的 data-view 一致）
const CONFIG_VIEW = '[data-view="extension-config"]';

async function openConfigView(page: Page, name: string): Promise<void> {
  await page.getByRole("button", {name: `配置 ${name}`}).click();
  await expect(page.locator(SETTINGS_DIALOG).locator(CONFIG_VIEW)).toBeVisible();
}

test("扩展配置入口：无工作区也能进入同一对话框子视图，分区导航禁用、唯一出路是返回扩展列表", async ({page}) => {
  await installExtensions(page, [generatedExtension()]);
  await installExtensionSettings(page);
  await page.goto("/");
  // 前置：没有打开工作区（扩展设置不依赖工作区快照，ARCH-DM-006 §8.2）
  await expect(page.getByRole("tablist")).toHaveCount(0);
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  // 同一 <dialog> 内的平级子视图：不叠加第二个模态，设置标题与关闭入口仍在
  await expect(dialog.locator(CONFIG_VIEW)).toBeVisible();
  await expect(dialog.getByRole("heading", {name: `配置 · ${GENERATED_NAME}`})).toBeVisible();
  await expect(dialog.getByRole("heading", {name: "设置"})).toBeVisible();
  await expect(dialog.locator('[role="dialog"]')).toHaveCount(0);
  // 子视图内分区导航禁用（避免未闸门的隐式离开），底部换成本扩展的「返回扩展列表 / 保存」
  await expect(dialog.getByRole("tab", {name: "常规配置"})).toBeDisabled();
  await expect(dialog.getByRole("tab", {name: "扩展"})).toBeDisabled();
  await expect(dialog.getByRole("tab", {name: "关于"})).toBeDisabled();
  await expect(dialog.getByRole("button", {name: "返回扩展列表"})).toBeVisible();
  await expect(dialog.getByRole("button", {name: "取消"})).toHaveCount(0);
  await expect(dialog.getByRole("button", {name: "保存"})).toBeVisible();
  // 进入焦点落在子视图首个可用字段控件（§3.3）
  await expect(page.getByLabel("图框块名前缀")).toBeFocused();
  // 扩展设置独立保存：未改动时保存按钮不可点（不会误提交）
  await expect(dialog.getByRole("button", {name: "保存"})).toBeDisabled();
});

test("扩展配置入口：未知 custom route_key fail-closed 成稳定诊断，不动态加载、不退化为 JSON 文本框", async ({page}) => {
  // 生产图纸目录声明 custom/sheet-catalog-settings，而白名单专属面板属任务 8——
  // 本任务不注册该键，子视图因此必须 fail-closed（SPEC-DM-011 §3.3 / ARCH-DM-006 §7）
  await installExtensions(page, [
    extensionSummary(),
    extensionSummary({extension_id: "demo.unknown-custom", name_key: "未知组件扩展", description_key: "声明了白名单外的设置组件。", settings_contribution: {presentation: "custom", route_key: "../views/UnknownSettings.vue"}, ui_contributions: []}),
  ]);
  await installExtensionSettings(page, {items: [], value: {}});
  const requests: string[] = [];
  page.on("request", request => requests.push(request.url()));
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, "图纸目录");
  const unavailable = dialog.getByTestId("extension-settings-unavailable");
  await expect(unavailable).toBeVisible();
  await expect(unavailable).toContainText("sheet-catalog-settings");
  // 不退化为 JSON 文本框：子视图内没有 textarea/JSON 编辑器
  await expect(dialog.locator("textarea")).toHaveCount(0);
  // 进入焦点确定：没有可用字段控件时落在诊断条（tabindex=-1），不退回 <body>
  await expect(unavailable).toBeFocused();
  await expect(dialog.getByRole("button", {name: "保存"})).toBeDisabled();

  // 未识别的 route_key 同样 fail-closed，且绝不按字符串动态加载（没有任何请求携带该键）
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
  await openConfigView(page, "未知组件扩展");
  await expect(dialog.getByTestId("extension-settings-unavailable")).toContainText("../views/UnknownSettings.vue");
  expect(requests.filter(url => url.includes("UnknownSettings") || url.includes("sheet-catalog-settings"))).toEqual([]);
});

test("generated 设置：字段按服务端顺序呈现、默认值来自 Provider，保存只提交本扩展快照", async ({page}) => {
  const mock = await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  const dialog = page.locator(SETTINGS_DIALOG);
  // 核心配置先留一处未保存修改：扩展设置保存不得影响它（SC-17 独立保存）
  await dialog.locator('input[data-key="cad_timeout_seconds"]').fill("777");
  await page.getByRole("tab", {name: "扩展"}).click();
  await openConfigView(page, GENERATED_NAME);

  // 字段顺序 = 服务端给出顺序（items 已排序，前端不得重排）
  await expect.poll(() => dialog.locator(".ef-row").evaluateAll(rows => rows.map(row => (row as HTMLElement).dataset.field)))
    .toEqual(["frame_block_prefix", "batch_limit", "write_back_titleblock", "ratio_threshold", "conflict_strategy"]);
  // 默认值来自 Provider（不是前端猜测）：string/integer/number/enum/boolean 五类控件逐一对位
  await expect(dialog.locator('input[data-key="frame_block_prefix"]')).toHaveValue("TK-");
  await expect(dialog.locator('input[data-key="batch_limit"]')).toHaveValue("50");
  await expect(dialog.locator('input[data-key="ratio_threshold"]')).toHaveValue("0.5");
  await expect(dialog.getByRole("radio", {name: "ask"})).toBeChecked();
  // boolean 复用设置中心既有滑动开关（与核心 bool 字段同形态）
  const boolSwitch = dialog.getByRole("switch", {name: "回写标题栏"});
  await expect(boolSwitch).toHaveClass(/switch/);
  await expect(boolSwitch).toHaveAttribute("aria-checked", "true");

  // 编辑后保存：PUT 只带本扩展的 schema_version 与 expected_revision，值是完整规范值
  await dialog.locator('input[data-key="batch_limit"]').fill("70");
  await boolSwitch.click();
  await dialog.getByRole("radio", {name: "overwrite"}).check();
  await expect(dialog.getByRole("button", {name: "保存"})).toBeEnabled();
  await dialog.getByRole("button", {name: "保存"}).click();
  await expect.poll(() => mock.puts).toEqual([{
    schema_version: 1,
    expected_revision: 0,
    value: {frame_block_prefix: "TK-", batch_limit: 70, write_back_titleblock: false, ratio_threshold: 0.5, conflict_strategy: "overwrite"},
  }]);
  await expect(dialog.getByTestId("extension-settings-saved-pill")).toBeVisible();
  await expect(dialog.getByRole("button", {name: "保存"})).toBeDisabled();

  // 核心配置的未保存缓冲不因保存扩展设置而变化
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
  await page.getByRole("tab", {name: "常规配置"}).click();
  await expect(dialog.locator('input[data-key="cad_timeout_seconds"]')).toHaveValue("777");

  // 重开子视图：保存值由服务端回读（第二次 GET），修订已推进
  await page.getByRole("tab", {name: "扩展"}).click();
  await openConfigView(page, GENERATED_NAME);
  await expect(dialog.locator('input[data-key="batch_limit"]')).toHaveValue("70");
  await expect(dialog.getByRole("switch", {name: "回写标题栏"})).toHaveAttribute("aria-checked", "false");
  await expect.poll(() => mock.gets).toBe(2);
  expect(mock.server.revision).toBe(1);
});

test("generated 设置：契约外控件显示不支持诊断，不提供 JSON 文本框", async ({page}) => {
  // 服务端控件词表是封闭的（boolean/integer/number/string/enum）：契约外取值必须 fail-closed
  await installExtensionSettings(page, {items: [
    ...generatedSettingsItems(),
    {key: "audit_scope", label_key: "审计范围", description_key: null, order: 6, control: "object", default: {}, nullable: false, min_value: null, max_value: null, options: [], max_length: null},
  ]});
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  const row = dialog.locator('[data-field="audit_scope"]');
  await expect(row.getByRole("note")).toContainText("object");
  await expect(row.locator("textarea")).toHaveCount(0);
  await expect(dialog.locator("textarea")).toHaveCount(0);
  // 其余字段仍可正常编辑与保存（一个不支持的控件不阻塞本扩展其他设置）
  await dialog.locator('input[data-key="batch_limit"]').fill("60");
  await dialog.getByRole("button", {name: "保存"}).click();
  await expect(dialog.getByTestId("extension-settings-saved-pill")).toBeVisible();
});

test("generated 设置：保存 422 按 params.field 行内定位、输入保留，错误摘要取得焦点", async ({page}) => {
  const mock = await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  // Provider 上限 200：越界值由服务端拒绝（前端不截断、不改写用户输入）
  const limit = dialog.locator('input[data-key="batch_limit"]');
  await limit.fill("999");
  await dialog.getByRole("button", {name: "保存"}).click();
  await expect.poll(() => mock.puts.length).toBe(1);
  // 错误摘要取得焦点（tabindex=-1），条目链接字段；行内错误定位到 params.field
  await expect(dialog.getByTestId("extension-settings-error-summary")).toBeFocused();
  await expect(dialog.locator('[data-field="batch_limit"] .ef-error')).toBeVisible();
  await expect(limit).toHaveValue("999");
  await expect(limit).toHaveAttribute("aria-invalid", "true");
  // 保留输入且未落盘：其他字段保持服务端值，子视图未关闭
  expect(mock.server.value.batch_limit).toBe(50);
  await expect(dialog.locator(CONFIG_VIEW)).toBeVisible();
  // 摘要条目跳转到该字段
  await dialog.getByTestId("extension-settings-error-summary").getByRole("button", {name: /单批处理上限/}).click();
  await expect(limit).toBeFocused();
  // 改为合法值后保存成功，行内错误清除
  await limit.fill("80");
  await dialog.getByRole("button", {name: "保存"}).click();
  await expect(dialog.getByTestId("extension-settings-saved-pill")).toBeVisible();
  await expect(dialog.locator('[data-field="batch_limit"] .ef-error')).toHaveCount(0);
});

test("扩展设置 设置冲突：409 保留本地输入并刷新服务端修订，可按新修订重试或放弃本地修改", async ({page}) => {
  const mock = await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  const limit = dialog.locator('input[data-key="batch_limit"]');
  await limit.fill("70");
  // 另一窗口已保存：服务端修订在本次子视图打开后推进（本地 expected_revision 随之过期）
  mock.server.revision = 1;
  await dialog.getByRole("button", {name: "保存"}).click();
  const conflict = dialog.locator(".cfg-conflict");
  await expect(conflict).toBeVisible();
  await expect(conflict).toContainText("expected_revision=0, current_revision=1");
  await expect(limit).toHaveValue("70");
  // 冲突后刷新服务端快照（第二次 GET），但保留本地编辑
  await expect.poll(() => mock.gets).toBe(2);
  // 出路一：按新修订重试（提交携带刷新后的 expected_revision）
  await dialog.getByRole("button", {name: "按新修订重试"}).click();
  await expect.poll(() => mock.puts.length).toBe(2);
  expect(mock.puts[1].expected_revision).toBe(1);
  await expect(dialog.getByTestId("extension-settings-saved-pill")).toBeVisible();
  await expect(conflict).toHaveCount(0);

  // 出路二：再制造一次冲突后「放弃本地修改」——回到服务端值、不再脏、冲突横幅消失
  await limit.fill("120");
  mock.server.revision = 3; // 上一次重试已经推进到 r2，本次由第三次服务端保存推进到 r3
  await dialog.getByRole("button", {name: "保存"}).click();
  await expect(conflict).toBeVisible();
  await dialog.getByRole("button", {name: "放弃本地修改"}).click();
  await expect(conflict).toHaveCount(0);
  await expect(limit).toHaveValue("70");
  await expect(dialog.getByRole("button", {name: "保存"})).toBeDisabled();
});

test("扩展设置 高版本只读：EXTENSION_SETTINGS_SCHEMA_NEWER 禁用输入与保存，进入焦点落在只读诊断条", async ({page}) => {
  await installExtensionSettings(page, {readOnly: true, schemaVersion: 3});
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  const readonly = dialog.getByTestId("extension-settings-readonly");
  await expect(readonly).toBeVisible();
  await expect(readonly).toContainText("已只读保留，无法覆盖保存");
  await expect(readonly).toContainText("EXTENSION_SETTINGS_SCHEMA_NEWER");
  // 只读子视图内所有控件都禁用，焦点必须落在只读诊断条（tabindex=-1），不得退回 <body>
  await expect(readonly).toBeFocused();
  await expect(dialog.locator('input[data-key="batch_limit"]')).toBeDisabled();
  await expect(dialog.getByRole("switch", {name: "回写标题栏"})).toBeDisabled();
  await expect(dialog.getByRole("button", {name: "保存"})).toBeDisabled();
  // 只读不可脏：返回不弹确认，直接回列表且焦点归还「配置」按钮
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
  await expect(dialog.locator(CONFIG_VIEW)).toHaveCount(0);
  await expect(dialog.locator('[role="dialog"]')).toHaveCount(0);
  await expect(page.getByRole("button", {name: `配置 ${GENERATED_NAME}`})).toBeFocused();
});

test("扩展配置入口：返回扩展列表先过脏状态闸门，确认后焦点归还卡片「配置」按钮", async ({page}) => {
  await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  const opener = page.getByRole("button", {name: `配置 ${GENERATED_NAME}`});
  await openConfigView(page, GENERATED_NAME);
  const limit = dialog.locator('input[data-key="batch_limit"]');
  await limit.fill("70");

  // 脏状态下返回：先确认（确认模态在同一对话框内，不叠加第二个设置子视图）
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
  const confirm = page.getByRole("dialog", {name: "有未保存的扩展设置修改"});
  await expect(confirm).toBeVisible();
  // 「留在此处」：不丢弃输入，焦点归还触发它的「返回扩展列表」
  await confirm.getByRole("button", {name: "留在此处"}).click();
  await expect(dialog.locator(CONFIG_VIEW)).toBeVisible();
  await expect(limit).toHaveValue("70");
  await expect(dialog.getByRole("button", {name: "返回扩展列表"})).toBeFocused();
  // 「放弃修改并返回」：回到列表，焦点归还卡片「配置」按钮，重进后回到服务端值
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
  await confirm.getByRole("button", {name: "放弃修改并返回"}).click();
  await expect(dialog.locator(CONFIG_VIEW)).toHaveCount(0);
  await expect(opener).toBeFocused();
  await openConfigView(page, GENERATED_NAME);
  await expect(dialog.locator('input[data-key="batch_limit"]')).toHaveValue("50");
});

test("扩展配置入口：Esc 与遮罩在子视图内等价于返回扩展列表（脏时先确认）", async ({page}) => {
  await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  const opener = page.getByRole("button", {name: `配置 ${GENERATED_NAME}`});
  await openConfigView(page, GENERATED_NAME);
  // 1) 未修改：Esc 等价于返回扩展列表，不关闭整个对话框，焦点归还「配置」按钮
  await page.keyboard.press("Escape");
  await expect(dialog.locator(CONFIG_VIEW)).toHaveCount(0);
  await expect(dialog).toBeVisible();
  await expect(opener).toBeFocused();

  // 2) 脏状态：Esc 与遮罩都先确认，不静默丢弃输入
  await openConfigView(page, GENERATED_NAME);
  const limit = dialog.locator('input[data-key="batch_limit"]');
  await limit.fill("70");
  const confirm = page.getByRole("dialog", {name: "有未保存的扩展设置修改"});
  await page.keyboard.press("Escape");
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", {name: "留在此处"}).click();
  await expect(limit).toHaveValue("70");
  await page.mouse.click(4, 4);
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", {name: "放弃修改并返回"}).click();
  // 遮罩点击只回到扩展列表，不关闭设置对话框
  await expect(dialog.locator(CONFIG_VIEW)).toHaveCount(0);
  await expect(dialog).toBeVisible();
  await expect(opener).toBeFocused();
});

test("扩展配置入口：子视图脏状态并入关闭确认，✕ 关闭后焦点归还齿轮入口", async ({page}) => {
  await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  await dialog.locator('input[data-key="batch_limit"]').fill("70");
  // 无核心配置修改、仅扩展设置脏：✕ 仍须确认，且确认文案合并子视图脏状态
  await dialog.getByRole("button", {name: "关闭设置"}).click();
  const confirm = page.getByRole("dialog", {name: "有未保存的修改"});
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText("扩展设置");
  await confirm.getByRole("button", {name: "留在此处"}).click();
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(CONFIG_VIEW)).toBeVisible();
  // 确认放弃后关闭：焦点归还齿轮入口（SC-09），子视图随关闭回收
  await dialog.getByRole("button", {name: "关闭设置"}).click();
  await confirm.getByRole("button", {name: "放弃修改并关闭"}).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", {name: "设置"})).toBeFocused();
});

// 扩展清单缩放（SPEC-DM-011 §3.3）：<6 条保持单列不分段；≥6 条按 enabled 分两段。
// 两条用例各自独立装数据，不依赖执行顺序。
test("SC-16 分段阈值下侧：5 条不分段", async ({page}) => {
  await installExtensions(page, [1, 2, 3, 4, 5].map((n) => extensionSummary({
    extension_id: `demo.ext-${n}`, enabled: n % 2 === 1, status: n % 2 === 1 ? "AVAILABLE" : "DISABLED",
  })));
  await page.goto("/");
  await openExtensionsSection(page);
  await expect(page.locator(".ext-card")).toHaveCount(5);
  await expect(page.locator(".group-title")).toHaveCount(0);
});

test("SC-16 分段阈值上侧：6 条分两段且分组键与开关同一权威", async ({page}) => {
  await installExtensions(page, [1, 2, 3, 4, 5, 6].map((n) => extensionSummary({
    extension_id: `demo.ext-${n}`, enabled: n % 2 === 1, status: n % 2 === 1 ? "AVAILABLE" : "DISABLED",
  })));
  await page.goto("/");
  await openExtensionsSection(page);
  await expect(page.locator(".ext-card")).toHaveCount(6);
  await expect(page.locator(".group-title")).toHaveCount(2);
  await expect(page.locator(".group-title").first()).toHaveText("已启用");
  await expect(page.locator(".group-title").last()).toHaveText("已停用");
  // 分组键与开关同一权威：任何一段内不得出现与段名矛盾的开关方向
  await expect(page.locator(".ext-group").first().locator('[aria-checked="false"]')).toHaveCount(0);
  await expect(page.locator(".ext-group").last().locator('[aria-checked="true"]')).toHaveCount(0);
});

// 并发代次闸门（PLAN-DM-024 / MEMO-DM-031 F1）：旧请求晚于新请求完成时，其响应不得
// 提交——既不能覆盖新请求写入的失败状态，也不能提交旧列表把标签拉回来/踢出去。
// 可控 Promise 在用例内接管 /api/extensions（本文件既有先例：用例内 route 覆盖）：
// 第 1 次请求（工作区打开）直通成功；第 2 次请求（打开设置 = 旧请求）挂起；
// 第 3 次请求（进入扩展分区 = 新请求）失败；最后放行旧请求并断言其成功响应被丢弃。
test("活动扩展失效先过守卫的并发代次：旧响应晚到不覆盖新列表或失败状态", async ({page}) => {
  let releaseOld: (() => void) | null = null;
  let oldRequestArrived: () => void;
  const oldRequestInFlight = new Promise<void>(resolve => { oldRequestArrived = resolve; });
  let requestCount = 0;
  await page.route("**/api/extensions", async route => {
    requestCount += 1;
    if (requestCount === 1) return route.fulfill({json: [extensionSummary()]});
    if (requestCount === 2) {
      oldRequestArrived();
      await new Promise<void>(resolve => { releaseOld = resolve; });
      // 旧请求最终以"成功但失效"响应收场：若被提交会移除目录标签
      return route.fulfill({json: [extensionSummary({status: "FAILED", error_code: "EXTENSION_START_FAILED"})]});
    }
    return route.fulfill({status: 500, json: {code: "INTERNAL_ERROR", message: "boom"}});
  });
  await openWorkspace(page);
  await expectTabIds(page, [...CORE_TABS, "tab-sheet-catalog"]);

  await page.getByRole("button", {name: "设置"}).click();
  // 等旧请求确实发出并挂起，再让新请求上路
  await oldRequestInFlight;
  await page.getByRole("tab", {name: "扩展"}).click();
  // 新请求失败：失败状态可见，旧列表保留（标签不消失）
  await expect(page.getByText("扩展列表加载失败。")).toBeVisible();
  await expectTabIds(page, [...CORE_TABS, "tab-sheet-catalog"]);

  // 旧请求晚于新请求完成：其成功响应必须被代次闸门丢弃
  releaseOld!();
  await expect(page.getByText("扩展列表加载失败。")).toBeVisible();
  await expectTabIds(page, [...CORE_TABS, "tab-sheet-catalog"]);
});
