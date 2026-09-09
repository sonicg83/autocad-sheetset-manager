// PLAN-DM-021 Task 11：英文界面响应式与可访问性证据（SPEC-DM-013 I18N-15、§3.5、§5.3）。
// 三组视口/主题/缩放组合：1440×900 浅色、900×768 深色、200% 缩放（1440×900 的浏览器
// 200% 缩放等价于 720×450 CSS 视口 + 2x deviceScaleFactor，经 CDP 设定）；
// 布局断言只用几何/滚动语义（bounding box、scrollWidth、overflow），不做像素级比对：
// 无整页横滚、主操作可达、长错误完整可读、表格只在自身容器横滚；
// 键盘与焦点：Tab 到达主操作、Esc 关闭设置并归还焦点、模态焦点圈闭、422 错误摘要
// 聚焦并链接字段、状态不只靠颜色（文本徽章/role/禁用属性/计数文本）。
// 截图经 testInfo 附件留档（i18n-{状态}-{宽}x{高}-{主题}.png），只使用虚构夹具数据。
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";

// settings 快照：ui_locale=en-US + 一个带 min/max 的 int 项（422 摘要链接字段用）
const enSnapshot = {
  schema_version: 1, config_revision: 1, diagnostics: [], schema_blocked: false,
  items: [
    {key: "ui_locale", control: "enum", value: "en-US", default: "system", source: "file", has_file_override: true,
      label_key: "settings.items.uiLocale", category_key: "settings.categories.interface",
      options: [{value: "system", text_key: "settings.locale.system"}, {value: "zh-CN", text_key: "settings.locale.zhCN"}, {value: "en-US", text_key: "settings.locale.enUS"}]},
    {key: "cad_timeout_seconds", control: "int", value: 600, default: 600, source: "default", has_file_override: false,
      label_key: "settings.items.cadTimeout", category_key: "settings.categories.execution", min: 30, max: 3600},
  ],
};

async function installEnglish(page: Page, theme?: "light" | "dark") {
  if (theme) await page.addInitScript((t) => localStorage.setItem("dst-manager-theme", t), theme);
  await page.route("**/api/settings", (route) => route.fulfill({json: enSnapshot}));
}

async function openEnglishWorkspace(page: Page, options?: Parameters<typeof installSheetsFixture>[1]) {
  await installSheetsFixture(page, options);
  await page.goto("/");
  await page.getByRole("button", {name: "Select DST File"}).click();
  await expect(page.locator(".workspace-name")).toHaveText("虚构图纸集");
}

// 无整页横滚：document/body 的 scrollWidth 都不超过视口宽（长内容只允许容器内滚动）
async function expectNoPageHScroll(page: Page, label: string) {
  const metrics = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    win: window.innerWidth,
  }));
  expect(metrics.doc, `${label}：html 无横向溢出`).toBeLessThanOrEqual(metrics.win);
  expect(metrics.body, `${label}：body 无横向溢出`).toBeLessThanOrEqual(metrics.win);
}

// 主操作可达：按钮完整落在视口内（不因英文伸长被推出视口或截断）
async function expectActionsReachable(page: Page, names: string[]) {
  const viewport = page.viewportSize()!;
  for (const name of names) {
    const box = await page.getByRole("button", {name}).first().boundingBox();
    expect(box, `${name} 存在`).not.toBeNull();
    expect(box!.x, name).toBeGreaterThanOrEqual(0);
    expect(box!.y, name).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width, `${name} 右缘在视口内`).toBeLessThanOrEqual(viewport.width);
    expect(box!.y + box!.height, `${name} 底缘在视口内`).toBeLessThanOrEqual(viewport.height);
  }
}

// 表格只在自身横滚：内容溢出发生在 .sheet-table-window 容器内，页面不随之滚动
async function expectTableScrollsInternally(page: Page) {
  const table = page.locator(".sheet-table-window");
  await expect(table).toHaveCSS("overflow-x", "auto");
  const scroll = await table.evaluate((el) => ({sw: el.scrollWidth, cw: el.clientWidth}));
  expect(scroll.sw, "表格内容宽于容器（确实存在可滚动溢出）").toBeGreaterThan(scroll.cw);
}

async function attachScreenshot(page: Page, info: TestInfo, state: string, theme: string) {
  const viewport = page.viewportSize()!;
  const name = `i18n-${state}-${viewport.width}x${viewport.height}-${theme}.png`;
  const path = info.outputPath(name);
  await page.screenshot({path, animations: "disabled"});
  await info.attach(name, {path, contentType: "image/png"});
}

// —— 组合一：1440×900 浅色（英文基准视口）——
test("1440×900 浅色（英文）：无整页横滚、主操作可达、表格只在自身横滚", async ({page}, info) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installEnglish(page, "light");
  await openEnglishWorkspace(page, {longText: true});
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expectNoPageHScroll(page, "1440×900 浅色");
  await expectActionsReachable(page, ["Preview Changes", "Confirm Write", "Settings", "Close"]);
  await expectTableScrollsInternally(page);
  // 超长标题/文件名在工作区内省略+title 可读（不把整页撑宽）
  const longTitle = page.locator(".sheet-table-window tbody tr").last().locator(".title-text");
  await expect(longTitle).toBeVisible();
  await expectNoPageHScroll(page, "1440×900 浅色（长文本）");
  await page.mouse.move(0, 0);
  await attachScreenshot(page, info, "default", "light-1440x900");
});

// —— 组合二：900×768 深色（最小视口）+ 长错误可读 ——
const LONG_ERROR = "OSError: [WinError 206] The filename or extension is too long: "
  + "C:\\虚构工程\\" + "很长目录名称".repeat(30) + "\\图纸集.dst";

test("900×768 深色（英文）：主操作可达且长错误完整可读", async ({page}, info) => {
  await page.setViewportSize({width: 900, height: 768});
  await installEnglish(page, "dark");
  await installSheetsFixture(page);
  // 打开失败注入超长单行错误（未知 code）：主提示为本地化摘要，原文进可展开诊断详情
  // （后注册的路由优先，盖过夹具的打开路由）
  await page.route("**/api/workspaces/open", (route) =>
    route.fulfill({status: 422, contentType: "application/json", body: JSON.stringify({code: "DST_UNREADABLE", message: LONG_ERROR})}));
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", {name: "Select DST File"}).click();
  // 本地化摘要完整渲染（无单行截断），盒子不超出视口（String(e) 带 "Error: " 前缀）
  const notice = page.locator("p.error.notice").first();
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("The operation failed due to an unknown error");
  const noticeFit = await notice.evaluate((el) => ({ch: el.clientHeight, sh: el.scrollHeight, right: el.getBoundingClientRect().right}));
  expect(noticeFit.sh, "摘要无剪裁").toBeLessThanOrEqual(noticeFit.ch + 1);
  expect(noticeFit.right, "摘要右缘在视口内").toBeLessThanOrEqual(900);
  // 展开原始诊断详情：超长单行原文经 overflow-wrap 折行，只在自身内滚动，不撑宽页面
  await page.locator("details.error.notice summary").click();
  const raw = page.locator(".error-raw");
  await expect(raw).toBeVisible();
  await expect(raw).toContainText("很长目录名称");
  expect(await raw.evaluate((el) => getComputedStyle(el).overflowWrap)).toBe("anywhere");
  const rawBox = await raw.boundingBox();
  expect(rawBox!.x + rawBox!.width).toBeLessThanOrEqual(900);
  await expectNoPageHScroll(page, "900×768 深色（长错误展开）");
  // 最小视口主操作仍可达
  await expectActionsReachable(page, ["Settings"]);
  await page.mouse.move(0, 0);
  await attachScreenshot(page, info, "long-error", "dark-900x768");
});

// —— 组合三：200% 缩放（浏览器 200% = CSS 视口 720×450 + 2x 渲染）——
test("200% 缩放（英文）：无整页横滚、对话框内容区滚动、页脚操作可达", async ({page}, info) => {
  await installEnglish(page, "light");
  await openEnglishWorkspace(page);
  // 1440×900 下浏览器 200% 缩放的等价模拟（properties-visual 先例为 documentElement.zoom，
  // 此处用 CDP 设定 CSS 视口 + dsf，几何断言与截图单位都是真实 CSS 像素）
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {width: 720, height: 450, deviceScaleFactor: 2, mobile: false});
  await expect(page.getByRole("button", {name: "Preview Changes"})).toBeVisible();
  await expectNoPageHScroll(page, "200% 缩放主视图");
  // 设置对话框：内容区自身滚动，页脚取消/保存不因缩放被推出视口
  await page.getByRole("button", {name: "Settings"}).click();
  const dialog = page.getByRole("dialog", {name: "Settings"});
  await expect(dialog).toBeVisible();
  const panel = dialog.locator(".panel").first();
  const panelScroll = await panel.evaluate((el) => ({sh: el.scrollHeight, ch: el.clientHeight, oy: getComputedStyle(el).overflowY}));
  expect(panelScroll.sh, "对话框内容确实溢出（需要内部滚动）").toBeGreaterThan(panelScroll.ch);
  expect(["auto", "scroll"]).toContain(panelScroll.oy);
  await expectActionsReachable(page, ["Cancel", "Save"]);
  await expectNoPageHScroll(page, "200% 缩放设置对话框");
  await page.mouse.move(0, 0);
  await attachScreenshot(page, info, "settings-200pct", "light-720x450");
});

// —— 键盘与焦点：Tab 到达主操作、Esc 归还焦点、模态焦点圈闭 ——
test("键盘：Tab 到达主操作、Esc 关闭设置并归还焦点、对话框焦点圈闭", async ({page}) => {
  await installEnglish(page, "light");
  await openEnglishWorkspace(page);
  // Tab 环：连续 Tab 后主操作（撤销/预览/写入/设置/关闭）全部可达
  //（单表中段有大量可聚焦单元格，上限放宽到 150 并命中即止）
  const wanted = ["Undo", "Preview Changes", "Confirm Write", "Settings", "Close workspace"];
  const visited = new Set<string>();
  for (let i = 0; i < 220 && wanted.some((action) => !([...visited].some((name) => name.includes(action)))); i++) {
    await page.keyboard.press("Tab");
    const name = await page.evaluate(() => (document.activeElement as HTMLElement | null)?.getAttribute("aria-label")
      ?? (document.activeElement as HTMLElement | null)?.textContent?.trim() ?? "");
    if (name) visited.add(name);
  }
  for (const action of wanted) {
    expect([...visited].some((name) => name.includes(action)), `Tab 可达 ${action}（实际：${[...visited].join(" | ")}）`).toBe(true);
  }
  // 设置对话框：焦点圈闭（连续 Tab 焦点始终在对话框子树内）
  const settingsButton = page.getByRole("button", {name: "Settings"});
  await settingsButton.click();
  const dialog = page.getByRole("dialog", {name: "Settings"});
  await expect(dialog).toBeVisible();
  // 等快照加载后的 focusFirstField 完成：焦点进入对话框再开始圈闭断言
  await expect.poll(() => page.evaluate(() => document.querySelector("dialog.settings-dialog")?.contains(document.activeElement) ?? false)).toBe(true);
  for (let i = 0; i < 25; i++) {
    await page.keyboard.press("Tab");
    const inside = await page.evaluate(() => document.querySelector('dialog[open].settings-dialog')?.contains(document.activeElement) ?? false);
    expect(inside, `第 ${i + 1} 次 Tab 后焦点仍在设置对话框内`).toBe(true);
  }
  // Esc 关闭并归还焦点到触发按钮（无未保存修改直接关闭）
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(settingsButton).toBeFocused();
});

// —— 422 错误摘要（英文）：聚焦摘要、条目链接字段 ——
test("422 结构化错误（英文）：错误摘要聚焦并链接字段", async ({page}) => {
  await installEnglish(page, "light");
  await installSheetsFixture(page);
  await page.goto("/");
  await page.getByRole("button", {name: "Settings"}).click();
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    return route.fulfill({
      status: 422, contentType: "application/json",
      body: JSON.stringify({
        code: "SETTINGS_VALIDATION_FAILED",
        errors: {cad_timeout_seconds: {code: "SETTING_INTEGER_RANGE", message_key: "settings.validation.integerRange",
          params: {min: 30, max: 3600}, message: "CAD timeout (seconds) must be between 30 and 3600"}},
      }),
    });
  });
  const timeout = page.locator('input[data-key="cad_timeout_seconds"]');
  await timeout.fill("700"); // 范围内（客户端校验先放行），由 PUT 422 触发服务端结构化错误
  await page.getByRole("button", {name: "Save"}).click();
  const summary = page.getByTestId("settings-error-summary");
  await expect(summary).toBeFocused();
  await expect(summary).toContainText("CAD timeout (seconds)");
  await expect(summary).toContainText("Must be between 30 and 3600");
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US"); // 失败不切换语言
  await expect(timeout).toHaveValue("700"); // 本地输入保留
  await summary.getByRole("button").first().click();
  await expect(timeout).toBeFocused();
});

// —— 非颜色状态线索：文本徽章、role、禁用属性与计数文本 ——
test("状态不只靠颜色：禁用属性、文字化原因、role=status 通知与计数", async ({page}) => {
  await installEnglish(page, "light");
  await openEnglishWorkspace(page);
  // 禁用按钮带 disabled 属性 + 文字化原因（不靠颜色表达"不可用"）
  await expect(page.getByRole("button", {name: "Confirm Write"})).toBeDisabled();
  await expect(page.getByText("No changes to publish")).toBeVisible();
  // 草稿计数芯片：数字文本（非颜色）
  await expect(page.locator(".draft-chip")).toContainText("Draft 0/0");
  // DST 状态徽章带文字（圆点只是装饰，aria-hidden）
  await expect(page.locator(".topbar .pill")).toContainText("DST");
  // 加入删除草稿 → toast role=status（辅助技术可达）且草稿计数文本变化
  await page.getByRole("button", {name: "Delete", exact: true}).first().click();
  const modal = page.locator('[role="dialog"][aria-modal="true"]');
  await modal.getByRole("button", {name: "Add to Delete Draft"}).click();
  const toast = page.locator(".toast").first();
  await expect(toast).toBeVisible();
  await expect(toast).toHaveAttribute("role", "status");
  await expect(toast).toContainText("Added to Delete Draft");
  await expect(page.locator(".draft-chip")).toContainText("Draft 1/1");
});

test("状态不只靠颜色：状态列 Pending/Blocking 为文本徽章", async ({page}) => {
  await installEnglish(page, "light");
  await openEnglishWorkspace(page, {dualStatus: true});
  const firstRow = page.locator(".sheet-table-window tbody tr").first();
  await expect(firstRow.locator(".status.blocking")).toHaveText("Blocking");
  await expect(firstRow.locator(".status.pending")).toHaveText("Pending");
});
