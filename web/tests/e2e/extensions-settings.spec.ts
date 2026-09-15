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
  // Tab 圈闭：永久断言（T9-3 转入项 1）。Task 9 把闸门的手写 onKeydown 换成 dialogFocus.ts 后
  // 只用**临时探针**验证过并被删掉——「圈闭」从此没有回归网。这里补上：在闸门内连按 Tab，
  // 焦点必须一直留在闸门内（原生模态的圈闭在尾→首回绕时有一拍落到 body）。
  // 刻意**不**断言「关闭归还焦点」：原生 <dialog> 自带归还（Task 9 的变异 C 因此不会变红），
  // 为该行为写断言会得到一条注定不敏感的钉子。
  for (let step = 1; step <= 8; step++) {
    await page.keyboard.press("Tab");
    const insideGuard = await guard.evaluate((el) => el.contains(document.activeElement));
    expect(insideGuard, `第 ${step} 次 Tab 后焦点应仍在闸门内`).toBe(true);
  }
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

// 修订冲突码探针：刻意不同于设置 PUT 的线上默认码（EXTENSION_SETTINGS_INVALID），
// 使「冲突横幅回显服务端返回的稳定码」这条断言在 E2E 里同样可失败——
// 前端一旦写死字面量即红，不再只靠单测钉住透传。
const CONFLICT_PROBE_CODE = "EXTENSION_SETTINGS_CHANGED";

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

test("扩展配置入口：白名单外与空 route_key 仍 fail-closed，不动态加载、不退化为 JSON 文本框", async ({page}) => {
  // PLAN-DM-025 Task 8 已把生产图纸目录的 sheet-catalog-settings 登记进编译期白名单
  // （其专属面板用例见下方 custom 面板分组），因此 fail-closed 分支的载体改为白名单外的
  // route_key——该分支必须保持可达且被覆盖（R20）。
  await installExtensions(page, [
    extensionSummary({extension_id: "demo.unknown-custom", name_key: "未知组件扩展", description_key: "声明了白名单外的设置组件。", settings_contribution: {presentation: "custom", route_key: "../views/UnknownSettings.vue"}, ui_contributions: []}),
    // 声明 custom 却没登记组件键（空 route_key）：原因与白名单未命中不同，
    // 不能把空值塞进「route_key {route_key}」模板印出带空白值的假原因
    extensionSummary({extension_id: "demo.missing-route-key", name_key: "缺组件键扩展", description_key: "声明了专属设置组件但没登记组件键。", settings_contribution: {presentation: "custom"}, ui_contributions: []}),
  ]);
  await installExtensionSettings(page, {items: [], value: {}});
  const requests: string[] = [];
  page.on("request", request => requests.push(request.url()));
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  // 未识别的 route_key 必须 fail-closed，且绝不按字符串动态加载（没有任何请求携带该键）
  await openConfigView(page, "未知组件扩展");
  const unavailable = dialog.getByTestId("extension-settings-unavailable");
  await expect(unavailable).toBeVisible();
  await expect(unavailable).toContainText("../views/UnknownSettings.vue");
  // 不退化为 JSON 文本框：子视图内没有 textarea/JSON 编辑器
  await expect(dialog.locator("textarea")).toHaveCount(0);
  // 进入焦点确定：没有可用字段控件时落在诊断条（tabindex=-1），不退回 <body>
  await expect(unavailable).toBeFocused();
  await expect(dialog.getByRole("button", {name: "保存"})).toBeDisabled();
  expect(requests.filter(url => url.includes("UnknownSettings") || url.includes("sheet-catalog-settings"))).toEqual([]);

  // 空 route_key：换一条诊断，不回显一个不存在的键值
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
  await openConfigView(page, "缺组件键扩展");
  const missing = dialog.getByTestId("extension-settings-unavailable");
  await expect(missing).toContainText("没有登记组件键（route_key）");
  await expect(missing).not.toContainText("（route_key ）");
  await expect(missing).not.toContainText("不在本程序的编译期白名单内");
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
  // enum 行的可见标签即 radiogroup 的可访问名（aria-labelledby 指向标签元素）：
  // enum 行不渲染带 id 的控件，所以不能挂 <label for>（会指向不存在的 id）
  const enumRow = dialog.locator('[data-field="conflict_strategy"]');
  await expect(enumRow.locator(".ef-label")).toHaveCount(1);
  expect(await enumRow.locator(".ef-label").evaluate(el => el.tagName)).toBe("SPAN");
  expect(await enumRow.locator(".ef-label").getAttribute("for")).toBeNull();
  await expect(enumRow.getByRole("radiogroup")).toHaveAttribute("aria-labelledby", "extension-settings-label-conflict_strategy");
  await expect(enumRow.getByRole("radiogroup")).toHaveAccessibleName("属性冲突处理");
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

test("扩展设置 加载失败：就地提示与重试；重试成功后焦点落在首个字段控件（不退回 <body>）", async ({page}) => {
  const mock = await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  mock.failGets = true; // 打开子视图的首次 GET 失败
  await page.getByRole("button", {name: `配置 ${GENERATED_NAME}`}).click();
  // 无快照时是独立失败态：不得静默呈现为空表单，也不得渲染任何字段控件
  const notice = dialog.getByTestId("extension-settings-load-failed");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("扩展设置加载失败。");
  await expect(dialog.locator(".ef-row")).toHaveCount(0);
  // 失败态下没有字段控件：焦点落在该状态唯一的可用控件（重试）上，不退回 <body>
  await expect(notice.getByRole("button", {name: "重试"})).toBeFocused();

  mock.failGets = false;
  await notice.getByRole("button", {name: "重试"}).click();
  await expect(dialog.locator('input[data-key="batch_limit"]')).toHaveValue("50");
  // 重试成功与进入时同一落点语义：重试按钮随失败态被移除，焦点必须重新定在首字段控件上
  await expect(dialog.getByLabel("图框块名前缀")).toBeFocused();
});

test("扩展设置 保存失败（5xx）：非字段级就地横幅可见、输入保留、保存按钮仍可用", async ({page}) => {
  const mock = await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  const limit = dialog.locator('input[data-key="batch_limit"]');
  await limit.fill("70");
  mock.failPuts = true; // 保存一律 500（非 422/409 的非字段级失败）
  await dialog.getByRole("button", {name: "保存"}).click();
  await expect.poll(() => mock.puts.length).toBe(1);
  // 未知错误的服务端响应没有 message_key：横幅显示本地化摘要，不把原始文本当正文
  const banner = dialog.getByTestId("extension-settings-save-failed");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("操作失败，发生未知错误");
  // 输入不被替换、子视图不关闭、保存仍可用（可直接重试）
  await expect(limit).toHaveValue("70");
  await expect(dialog.locator(CONFIG_VIEW)).toBeVisible();
  await expect(dialog.getByRole("button", {name: "保存"})).toBeEnabled();
  // 修正后重试成功：横幅随下一次编辑/保存收敛
  mock.failPuts = false;
  await dialog.getByRole("button", {name: "保存"}).click();
  await expect(dialog.getByTestId("extension-settings-saved-pill")).toBeVisible();
  await expect(banner).toHaveCount(0);
  expect(mock.server.value.batch_limit).toBe(70);
});

test("扩展设置 设置冲突：409 保留本地输入并刷新服务端修订，可按新修订重试或放弃本地修改", async ({page}) => {
  // 夹具的冲突码换成探针码：横幅必须回显服务端返回的码，写死字面量即红
  const mock = await installExtensionSettings(page, {conflictCode: CONFLICT_PROBE_CODE});
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
  // 横幅回显的是线上实际返回的稳定码（夹具与后端同一路径）与端点前缀，
  // 不是前端写死的字面量——服务端换码时这里必须跟着变
  await expect(conflict).toContainText(`PUT /api/extensions/${GENERATED_ID}/settings → 409 ${CONFLICT_PROBE_CODE}`);
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
  await conflict.getByRole("button", {name: "放弃本地修改"}).click();
  await expect(conflict).toHaveCount(0);
  await expect(limit).toHaveValue("70");
  await expect(dialog.getByRole("button", {name: "保存"})).toBeDisabled();
});

test("扩展设置 冲突后刷新失败：就地提示「内容可能已过期」与冲突横幅同时可见，输入保留", async ({page}) => {
  const mock = await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  const limit = dialog.locator('input[data-key="batch_limit"]');
  await limit.fill("70");
  mock.server.revision = 1; // 另一窗口已保存：本地 expected_revision 过期
  mock.failGets = true; // 冲突后的快照刷新失败
  await dialog.getByRole("button", {name: "保存"}).click();

  const conflict = dialog.locator(".cfg-conflict");
  await expect(conflict).toBeVisible();
  await expect(limit).toHaveValue("70");
  // 头部徽标仍是刷新前的陈旧快照（服务端已是 r1）：横幅让人「按新修订重试」时，
  // 必须有一条在 .cfg 级别可见的提示说明下方内容可能已过期（不只长在只读横幅里）
  await expect(dialog.locator(".cfg-title .badge").first()).toHaveText("设置修订 r0");
  const stale = dialog.getByTestId("extension-settings-refresh-failed");
  await expect(stale).toBeVisible();
  await expect(stale).toContainText("扩展设置刷新失败，下方内容可能已过期。");
  // 刷新确实发生过（失败）且本地输入未被丢弃
  await expect.poll(() => mock.gets).toBe(2);
  expect(mock.server.value.batch_limit).toBe(50);
  // 冲突出路仍可用：放弃本地修改后横幅与陈旧提示一并收敛
  await conflict.getByRole("button", {name: "放弃本地修改"}).click();
  await expect(conflict).toHaveCount(0);
  await expect(limit).toHaveValue("50");
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
  // 只读态不保留未保存的输入（只读不可脏）：横幅必须说明这一点，不静默丢弃
  await expect(readonly).toContainText("只读子视图不保留未保存的输入");
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

test("扩展设置 高版本只读：运行时 409 EXTENSION_SETTINGS_SCHEMA_NEWER 进入只读，刷新失败也不丢只读保护", async ({page}) => {
  const mock = await installExtensionSettings(page);
  await installExtensions(page, [generatedExtension()]);
  await page.goto("/");
  await openExtensionsSection(page);

  const dialog = page.locator(SETTINGS_DIALOG);
  await openConfigView(page, GENERATED_NAME);
  // 打开时服务端仍是可写快照（GET 200 read_only=false），因此只读判定不可能来自首次加载
  const limit = dialog.locator('input[data-key="batch_limit"]');
  await expect(limit).toBeEnabled();
  await limit.fill("70");
  await expect(dialog.getByRole("button", {name: "保存"})).toBeEnabled();

  // 另一进程写入更高 Schema：本次 PUT 以 409 EXTENSION_SETTINGS_SCHEMA_NEWER 拒绝；
  // 同时让后续刷新 GET 失败——只读判定必须与这次刷新解耦
  mock.server.read_only = true;
  mock.server.diagnostic_code = "EXTENSION_SETTINGS_SCHEMA_NEWER";
  mock.failGets = true;
  await dialog.getByRole("button", {name: "保存"}).click();

  const readonly = dialog.getByTestId("extension-settings-readonly");
  await expect(readonly).toBeVisible();
  await expect(readonly).toContainText("已只读保留，无法覆盖保存");
  await expect(readonly).toContainText("EXTENSION_SETTINGS_SCHEMA_NEWER");
  // 刷新失败可见（不静默），且不覆盖只读判定
  await expect(dialog.getByTestId("extension-settings-refresh-failed")).toBeVisible();
  // 控件与保存都禁用：不再可能重复提交必然 409 的保存
  await expect(limit).toBeDisabled();
  await expect(dialog.getByRole("button", {name: "保存"})).toBeDisabled();
  expect(mock.puts.length).toBe(1);
  // 只读不可脏：返回不弹确认，焦点归还卡片「配置」按钮
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
  await expect(dialog.locator(CONFIG_VIEW)).toHaveCount(0);
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
  // 3) 确认框已打开时再按 Esc：只作用于最上层确认框（留在此处），
  // 子视图仍开着、输入仍在，且不得连带关闭整个设置对话框
  await page.keyboard.press("Escape");
  await expect(confirm).toBeHidden();
  await expect(dialog.locator(CONFIG_VIEW)).toBeVisible();
  await expect(dialog).toBeVisible();
  await expect(limit).toHaveValue("70");
  // 闸门关掉后焦点归还打开它的控件（原生模态的 close 语义），不丢回 <body>
  await expect(limit).toBeFocused();
  // 再次打开闸门走可见入口：连续 Esc 会触发平台层对同一对话框的关闭请求节流，
  // 与本用例要钉的「Esc 只关最上层闸门」无关
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
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

// ---- SC-17：图纸目录 custom 设置面板（PLAN-DM-025 Task 8 / SPEC-DM-012 §6.2/§6.4）----
// 生产固定索引里唯一声明 settings 的扩展就是图纸目录，其 presentation=custom、
// route_key=sheet-catalog-settings：任务 8 把专属面板静态登记进编译期白名单，
// 因此下面的用例必须走真实面板（fail-closed 分支的覆盖见上方 route_key 用例）。
const CATALOG_NAME = "图纸目录";
const CATALOG_PANEL = '[data-testid="sheet-catalog-settings-panel"]';
const CATALOG_FILTER = '[data-testid="catalog-settings-filter"]';
const CATALOG_FILTER_ERROR = '[data-testid="catalog-settings-filter-error"]';
const FILTER_FIELD = "excluded_title_keywords";

function catalogTemplate(name: string, columns: {header: string; expression: string}[] = [{header: "图号", expression: "{sheet.number}"}]) {
  return {
    template_id: `tpl-${name}`,
    name,
    schema_version: 1,
    columns: columns.map((column, index) => ({column_id: `col-${name}-${index}`, ...column})),
  };
}

// 图纸目录设置 mock：schema_version 取自 Manifest（2），value 是持久值（user_templates +
// 可选 excluded_title_keywords），关键词上限与规范化由 extensions.ts 夹具按 settings.py 复刻。
async function installCatalogSettings(page: Page, options: {value?: Record<string, unknown>; revision?: number} = {}) {
  return installExtensionSettings(page, {schemaVersion: 2, items: [], value: {user_templates: []}, ...options});
}

test("custom 面板：无工作区可进入、可编辑表达式与另存模板，过滤词保存后按服务端数组规范化回显", async ({page}) => {
  const mock = await installCatalogSettings(page);
  await installExtensions(page, [extensionSummary()]);
  await page.goto("/");
  await expect(page.getByRole("tablist")).toHaveCount(0); // 前置：没有打开工作区
  await openExtensionsSection(page);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  const panel = dialog.locator(CATALOG_PANEL);
  await expect(panel).toBeVisible();
  // 无工作区：不渲染字段浏览器，也不伪造兼容性徽标/摘要（不伪造 preview）
  await expect(dialog.locator(".field-browser")).toHaveCount(0);
  await expect(dialog.locator(".compatibility")).toHaveCount(0);
  await expect(dialog.locator(".compat-badge")).toHaveCount(0);
  // 表达式文本仍可编辑（不因无工作区降级为只读），列增删可用
  const expression = dialog.getByLabel("表达式 1");
  await expect(expression).toBeEnabled();
  await expression.fill("{sheet.number}号");
  await dialog.getByRole("button", {name: "添加输出列"}).click();
  await expect(dialog.getByLabel("输出列名 4")).toBeVisible();

  // 另存为：内置模板不可原地保存，草稿只能另存为新模板（新模板带 4 列）
  await dialog.getByRole("button", {name: "另存为"}).click();
  const saveAs = page.getByRole("dialog", {name: "另存为模板"});
  await saveAs.getByLabel("模板名称").fill("无工作区模板");
  await saveAs.getByRole("button", {name: "保存", exact: true}).click();
  await expect.poll(() => mock.puts.length).toBe(1);
  expect(mock.puts[0]!.schema_version).toBe(2);
  const savedTemplates = mock.puts[0]!.value.user_templates as {name: string; columns: unknown[]}[];
  expect(savedTemplates.map(template => template.name)).toEqual(["无工作区模板"]);
  expect(savedTemplates[0]!.columns).toHaveLength(4);
  const createdTemplateId = (savedTemplates[0] as {template_id: string}).template_id;
  await expect(dialog.getByLabel("选择模板")).toHaveValue(createdTemplateId);

  // 输出图纸过滤：单行输入 + 说明 + 示例占位；PUT 提交原始文本，Provider 负责规范化
  const filter = dialog.locator(CATALOG_FILTER);
  await expect(filter).toHaveValue("");
  await expect(filter).toHaveAttribute("placeholder", "草图, 作废, TEMP");
  await filter.fill("草图， TEMP,,作废,temp");
  await dialog.getByRole("button", {name: "保存", exact: true}).click();
  await expect.poll(() => mock.puts.length).toBe(2);
  expect(mock.puts[1]!.value[FILTER_FIELD]).toBe("草图， TEMP,,作废,temp");
  // 规范化回显：半/全角逗号拆分、去空白与空项、大小写去重保留首见原文，逗号加空格连接
  expect(mock.server.value[FILTER_FIELD]).toEqual(["草图", "TEMP", "作废"]);
  await expect(dialog.getByTestId("extension-settings-saved-pill")).toBeVisible();
  await expect(filter).toHaveValue("草图, TEMP, 作废");
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeDisabled();

  // 重开子视图：模板与过滤词都从服务端回读（内存缓冲不是权威）
  await dialog.getByRole("button", {name: "返回扩展列表"}).click();
  await openConfigView(page, CATALOG_NAME);
  await expect(dialog.locator(CATALOG_FILTER)).toHaveValue("草图, TEMP, 作废");
  // 模板与过滤词都从服务端回读；子视图的“当前选中模板”是视图态（不进入扩展设置），
  // 重开后回到内置默认模板，但用户模板仍在列表中可选
  await expect(dialog.getByLabel("选择模板").locator("option")).toHaveCount(2);
  await expect(dialog.getByLabel("选择模板")).toContainText("无工作区模板");
  await expect(dialog.getByLabel("输出列名 1")).toHaveValue("图号");
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeDisabled();
});

test("custom 面板：过滤关键词 50/51 项与 100/101 字符的字段级错误定位，输入保留且不落盘", async ({page}) => {
  const mock = await installCatalogSettings(page);
  await installExtensions(page, [extensionSummary()]);
  await page.goto("/");
  await openExtensionsSection(page);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  const filter = dialog.locator(CATALOG_FILTER);
  const longKeyword = (length: number) => "k".repeat(length);

  // 50 项（上限）保存成功
  const fifty = Array.from({length: 50}, (_, index) => `k${index}`).join(", ");
  await filter.fill(fifty);
  await dialog.getByRole("button", {name: "保存", exact: true}).click();
  await expect(dialog.getByTestId("extension-settings-saved-pill")).toBeVisible();
  expect(mock.server.value[FILTER_FIELD] as string[]).toHaveLength(50);
  await expect(dialog.locator(CATALOG_FILTER_ERROR)).toHaveCount(0);

  // 51 项：服务端拒绝并定位到 excluded_title_keywords，不截断输入
  const fiftyOne = `${fifty}, k51`;
  await filter.fill(fiftyOne);
  await dialog.getByRole("button", {name: "保存", exact: true}).click();
  // 字段级 422：错误定位在这一行（aria-invalid + 行内正文），限额数字取自服务端稳定参数，
  // 文案按 errors.extension.settingsInvalid 渲染（扩展设置端点唯一已登记的 422 文案键）
  await expect(dialog.locator(CATALOG_FILTER_ERROR)).toContainText("扩展设置无效");
  await expect(filter).toHaveAttribute("aria-invalid", "true");
  await expect(filter).toHaveValue(fiftyOne);
  expect(mock.server.value[FILTER_FIELD] as string[]).toHaveLength(50);

  // 单项 100 字符（上限）保存成功
  await filter.fill(longKeyword(100));
  await dialog.getByRole("button", {name: "保存", exact: true}).click();
  await expect(dialog.locator(CATALOG_FILTER_ERROR)).toHaveCount(0);
  // 等这一发真的落盘（缓冲区回到干净态）再继续输入：行内错误的清除已不再依赖保存返回，
  // 不等的话下一发输入会被刚返回的成功响应（清空编辑缓冲）当掉
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeDisabled();
  expect(mock.server.value[FILTER_FIELD]).toEqual([longKeyword(100)]);

  // 101 字符：同样字段级拒绝，输入保留
  await filter.fill(longKeyword(101));
  await dialog.getByRole("button", {name: "保存", exact: true}).click();
  await expect(dialog.locator(CATALOG_FILTER_ERROR)).toContainText("扩展设置无效");
  await expect(filter).toHaveValue(longKeyword(101));
  expect(mock.server.value[FILTER_FIELD]).toEqual([longKeyword(100)]);
  // 输入仍可修正：回到合法值后保存成功且行内错误收敛（不存盘）
  await filter.fill("作废");
  // 继续输入即清除字段级错误：字段错误不自行消失会让修正后的输入继续顶着红框与
  // aria-invalid=true，直到下一次成功保存（清错不是本地校验，Provider 仍是唯一校验者）
  await expect(dialog.locator(CATALOG_FILTER_ERROR)).toHaveCount(0);
  await expect(filter).toHaveAttribute("aria-invalid", "false");
  expect(mock.server.value[FILTER_FIELD]).toEqual([longKeyword(100)]); // 清错不代表落盘
  await dialog.getByRole("button", {name: "保存", exact: true}).click();
  await expect(dialog.locator(CATALOG_FILTER_ERROR)).toHaveCount(0);
  // 同样等保存返回：下面的服务端值断言不再是可重试断言，不能靠已提前满足的错误清除来同步
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeDisabled();
  expect(mock.server.value[FILTER_FIELD]).toEqual(["作废"]);
});

test("custom 面板：模板名重复是 Provider 级 409，按普通保存失败呈现且不冒充修订冲突", async ({page}) => {
  const mock = await installCatalogSettings(page, {value: {user_templates: [catalogTemplate("标准目录")]}});
  await installExtensions(page, [extensionSummary()]);
  await page.goto("/");
  await openExtensionsSection(page);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  // 另存为与已有模板重名（前端只拦内置显示名，重名由 Provider 判定）：PUT 得到
  // 409 SHEET_CATALOG_COLUMN_DUPLICATE——与修订冲突同状态码、不同 code
  await dialog.getByRole("button", {name: "另存为"}).click();
  const saveAs = page.getByRole("dialog", {name: "另存为模板"});
  await saveAs.getByLabel("模板名称").fill("标准目录");
  await saveAs.getByRole("button", {name: "保存", exact: true}).click();
  await expect.poll(() => mock.puts.length).toBe(1);

  // 普通失败横幅显示服务端自己的正文（名称重复），且没有任何“落在“修订冲突”上的说法：
  // 断言“已被其他保存更新”之类的伪造不得出现，也不得给出无法成功的“按新修订重试”
  const notice = dialog.getByTestId("extension-settings-save-failed");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("名称重复：标准目录");
  await expect(dialog.locator(".cfg-conflict")).toHaveCount(0);
  await expect(dialog.getByRole("button", {name: "按新修订重试"})).toHaveCount(0);
  await expect(dialog.getByText(/已被其他保存更新/)).toHaveCount(0);
  // 子视图未关闭、输入未被丢弃（用户可以改名字再存），也没有自动重试的第二发请求
  await expect(dialog.locator(CATALOG_PANEL)).toBeVisible();
  expect(mock.puts).toHaveLength(1);

  // 修正重名后按同一入口保存：Provider 放行，修订仍是本地值（未被误推向新修订）
  await saveAs.getByRole("button", {name: "取消"}).click();
  await dialog.getByRole("button", {name: "另存为"}).click();
  await saveAs.getByLabel("模板名称").fill("另一目录");
  await saveAs.getByRole("button", {name: "保存", exact: true}).click();
  await expect.poll(() => mock.puts.length).toBe(2);
  expect(mock.puts[1]!.expected_revision).toBe(0);
  await expect(notice).toHaveCount(0);
});

// 修复轮 1（C 部分）：`conflict` 只在保存成功 / 放弃本地修改 / 只读收口时清除，而普通失败
// 横幅此前永远优先取 `conflict.message`。于是「先 Provider 级 409、再一发非 409 失败」时，
// 用户只能看到陈旧的「名称重复」，新失败的正文无处可见。
test("custom 面板：Provider 级 409 之后的非 409 失败不被陈旧冲突正文压掉", async ({page}) => {
  const mock = await installCatalogSettings(page, {value: {user_templates: [catalogTemplate("标准目录")]}});
  await installExtensions(page, [extensionSummary()]);
  await page.goto("/");
  await openExtensionsSection(page);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  const saveAs = page.getByRole("dialog", {name: "另存为模板"});
  const notice = dialog.getByTestId("extension-settings-save-failed");
  await dialog.getByRole("button", {name: "另存为"}).click();
  await saveAs.getByLabel("模板名称").fill("标准目录");
  await saveAs.getByRole("button", {name: "保存", exact: true}).click();
  await expect.poll(() => mock.puts.length).toBe(1);
  await expect(notice).toContainText("名称重复：标准目录");

  // 第二发换成非 409 失败（网络/5xx）：夹具的普通失败正文必须可见
  let failures = 0;
  await page.route("**/api/extensions/*/settings", async route => {
    if (route.request().method() !== "PUT") return route.fallback();
    failures += 1;
    return route.fulfill({status: 500, json: {code: "INTERNAL_ERROR", message: "保存失败：服务暂时不可用"}});
  });
  await saveAs.getByRole("button", {name: "取消"}).click();
  await dialog.getByRole("button", {name: "另存为"}).click();
  await saveAs.getByLabel("模板名称").fill("另一目录");
  await saveAs.getByRole("button", {name: "保存", exact: true}).click();
  await expect.poll(() => failures).toBe(1);
  // 客户端对无 message_key 的 5xx 给通用文案（不是夹具正文），关键是它不再被陈旧冲突正文压掉
  await expect(notice).toHaveText("操作失败，发生未知错误");
  // 陈旧的 Provider 冲突正文不得与之一同/取而代之呈现
  await expect(notice).not.toContainText("名称重复");
  await expect(dialog.getByText(/名称重复/)).toHaveCount(0);
  await expect(dialog.locator(".cfg-conflict")).toHaveCount(0);
});

test("custom 面板：删除用户模板先确认，取消保留、确认后回内置模板并落盘", async ({page}) => {
  const mock = await installCatalogSettings(page, {revision: 3, value: {user_templates: [catalogTemplate("标准目录")]}});
  await installExtensions(page, [extensionSummary()]);
  await page.goto("/");
  await openExtensionsSection(page);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  await dialog.getByLabel("选择模板").selectOption({label: "标准目录"});
  await dialog.getByRole("button", {name: "删除模板"}).click();
  const confirm = page.getByRole("dialog", {name: "删除模板"});
  await expect(confirm).toBeVisible();
  // 取消：模板与选择都不变，也没有发出 PUT
  await confirm.getByRole("button", {name: "取消"}).click();
  await expect(confirm).toBeHidden();
  await expect(dialog.getByLabel("选择模板")).toHaveValue("tpl-标准目录");
  expect(mock.puts).toHaveLength(0);
  // 确认：删除落盘并回到内置默认模板
  await dialog.getByRole("button", {name: "删除模板"}).click();
  await confirm.getByRole("button", {name: "删除", exact: true}).click();
  await expect.poll(() => mock.puts.length).toBe(1);
  expect(mock.puts[0]!.value.user_templates).toEqual([]);
  expect(mock.server.value.user_templates).toEqual([]);
  await expect(dialog.getByLabel("选择模板")).toHaveValue("");
});

test("custom 面板：修订冲突保留过滤词草稿，横幅给出两条出路，重试成功后不丢输入", async ({page}) => {
  const mock = await installCatalogSettings(page);
  await installExtensions(page, [extensionSummary()]);
  await page.goto("/");
  await openExtensionsSection(page);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  const filter = dialog.locator(CATALOG_FILTER);
  await filter.fill("草图—待保存");
  mock.server.revision = 1; // 另一窗口已保存：本地 expected_revision 过期
  await dialog.getByRole("button", {name: "保存", exact: true}).click();

  const conflict = dialog.locator(".cfg-conflict");
  await expect(conflict).toBeVisible();
  await expect(conflict).toContainText("409 EXTENSION_SETTINGS_INVALID");
  // 草稿保留：输入不被替换、子视图未关闭、缓冲仍脏
  await expect(filter).toHaveValue("草图—待保存");
  await expect(dialog.locator(CATALOG_PANEL)).toBeVisible();
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeEnabled();

  // 出路一：按新修订重试（提交刷新后的 expected_revision），值原样落盘。
  // 冲突横幅只在宿主一处渲染（面板内的 TemplateBar 用 hide-conflict 收起重复的那一份）
  await conflict.getByRole("button", {name: "按新修订重试"}).click();
  await expect.poll(() => mock.puts.length).toBe(2);
  expect(mock.puts[1]!.expected_revision).toBe(1);
  await expect(conflict).toHaveCount(0);
  await expect(filter).toHaveValue("草图—待保存");
  expect(mock.server.value[FILTER_FIELD]).toEqual(["草图—待保存"]);

  // 出路二：再制造一次冲突后放弃本地修改——回到服务端值、不再脏
  await filter.fill("作废");
  mock.server.revision = 3;
  await dialog.getByRole("button", {name: "保存", exact: true}).click();
  await expect(conflict).toBeVisible();
  await conflict.getByRole("button", {name: "放弃本地修改"}).click();
  await expect(conflict).toHaveCount(0);
  await expect(filter).toHaveValue("草图—待保存");
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeDisabled();
});

// PLAN-DM-025 Task 8 修复轮 1（B 部分）I5/M2：custom 面板的只读路径此前没有任何用例，
// <fieldset disabled> 分支从未执行过（夹具的 readOnly 开关是死代码）。高版本只读时
// 面板必须整体不可操作、宿主给出只读诊断条、页脚"保存"停用——不留"点了没反应"的出口；
// 同时列状态在无校验反馈时不得冒充绿色"有效"（M2）。
test("custom 面板：高版本只读进入配置子视图，面板整体 disabled 且列状态不冒充有效", async ({page}) => {
  const mock = await installCatalogSettings(page, {readOnly: true, revision: 3, value: {user_templates: [catalogTemplate("标准目录")]}});
  await installExtensions(page, [extensionSummary()]);
  await page.goto("/");
  await openExtensionsSection(page);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  const panel = dialog.locator(CATALOG_PANEL);
  await expect(panel).toBeVisible();
  // 宿主只读诊断条：与业务页同一语义（errors.extension.schemaNewer + readOnlyCode）
  const readonly = dialog.getByTestId("extension-settings-readonly");
  await expect(readonly).toBeVisible();
  await expect(readonly).toContainText("已只读保留，无法覆盖保存");
  await expect(readonly).toContainText("EXTENSION_SETTINGS_SCHEMA_NEWER");
  // <fieldset disabled> 覆盖全部后代控件：模板选择、过滤输入、表达式与列操作都不可操作
  await expect(panel.getByLabel("选择模板")).toBeDisabled();
  await expect(panel.locator(CATALOG_FILTER)).toBeDisabled();
  await expect(panel.getByLabel("表达式 1")).toBeDisabled();
  await expect(panel.getByRole("button", {name: "添加输出列"})).toBeDisabled();
  await expect(panel.getByRole("button", {name: "另存为"})).toBeDisabled();
  // 宿主页脚"保存"同样停用：只读态不产生静默无效保存
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeDisabled();
  expect(mock.puts).toHaveLength(0);
  // M2：没有工作区反馈就没有"已校验"这回事，状态列必须是中性"未校验"而不是"有效"
  await expect(panel.locator(".status-badge").first()).toHaveText("未校验");
  await expect(panel.locator(".status-badge").first()).toHaveClass(/neutral/);
});
