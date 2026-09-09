// PLAN-DM-021 Task 11：英文关键矩阵与语言切换业务不变量（SPEC-DM-013 §2.2/§7.1，I18N-06/15/16）。
// 关键矩阵：两种语言各跑一遍 启动 → 设置 → 打开 → 图纸 → 属性 → 预览 → 发布 → 任务 → 修订
// 九个关键域，每域同时断言语义键渲染与用户数据原样（图纸集名/路径/编号/属性名/哈希，I18N-16）；
// 不变量用例：语言切换前后 workspace 标识、未提交输入、选区、草稿、任务与修订完全一致，
// 发布不重跑（execute 只调用一次）、SSE 事件 URL 不携带语言（I18N-12）。
// 语言来源沿用 page 级 settings 快照路由（main.spec Task 5 模式）：不写共享 settings.json，
// 并行 worker 下与既有中文基线用例互不串扰；GET 也一并路由，本文件不依赖真实后端状态。
import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture, installSmartPreview} from "./fixtures/sheets";

// settings 快照：ui_locale 为必显项；再补一个带 min/max 的 int 项，保持与真实快照同构
function localeSnapshot(locale: string, configRevision = 1) {
  return {
    schema_version: 1, config_revision: configRevision, diagnostics: [], schema_blocked: false,
    items: [
      {key: "ui_locale", control: "enum", value: locale, default: "system", source: "file", has_file_override: true,
        label_key: "settings.items.uiLocale", category_key: "settings.categories.interface",
        options: [{value: "system", text_key: "settings.locale.system"}, {value: "zh-CN", text_key: "settings.locale.zhCN"}, {value: "en-US", text_key: "settings.locale.enUS"}]},
      {key: "cad_timeout_seconds", control: "int", value: 600, default: 600, source: "default", has_file_override: false,
        label_key: "settings.items.cadTimeout", category_key: "settings.categories.execution", min: 30, max: 3600},
    ],
  };
}

// 语言切换辅助：PUT 返回 en-US 快照驱动前端 applyLocale，GET 提供当前语言基线
async function installLocale(page: Page, locale: string) {
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "PUT") return route.fulfill({json: localeSnapshot("en-US", 2)});
    return route.fulfill({json: localeSnapshot(locale)});
  });
}

// 修订历史基线（用户数据：修订 ID/哈希/时间原样）
const REVISIONS = [{id: "revision-1", created_at: "2026-09-01T00:00:00Z", before_hash: "aaaaaaaa", result_hash: "bbbbbbbb"}];
async function installRevisions(page: Page) {
  await page.route("**/api/revisions?workspace_id=workspace-1", (route) => route.fulfill({json: REVISIONS}));
}

// 确认模态（main.spec 同款）：先勾选危险确认框，再点确认按钮
async function confirmModal(page: Page, confirmName: RegExp) {
  const modal = page.locator('[role="dialog"][aria-modal="true"]');
  if (await modal.getByRole("checkbox").count()) await modal.getByRole("checkbox").check();
  await modal.getByRole("button", {name: confirmName}).click();
}

// SSE 模拟（main.spec 同款）：捕获事件连接 URL 并支持注入任务事件
async function installMockEventSource(page: Page) {
  await page.addInitScript(() => {
    class FakeEventSource {
      url: string;
      onmessage: ((event: {data: string}) => void) | null = null;
      onerror: (() => void) | null = null;
      closed = false;
      constructor(url: string) { this.url = url; (window as any).__eventSources.push(this); }
      close() { this.closed = true; }
    }
    (window as any).__eventSources = [];
    (window as any).EventSource = FakeEventSource;
  });
}

// 每种语言的九域关键断言文案（语义键渲染结果）；用户数据一律内联原样断言，不进本表
const L = {
  "zh-CN": {
    welcomeHeading: "打开图纸集", selectDst: "选择 DST 文件",
    settings: "设置", settingsDialog: "设置", generalSection: "常规配置", localeLabel: "界面语言",
    close: "关闭", cadVersion: "AutoCAD 版本",
    tabs: {sheets: "图纸", properties: "属性", revisions: "修订历史"},
    headers: ["图号", "标题", "状态", "操作"],
    sheetsetName: "图纸集名称", updateSheetSet: "更新图纸集", propertyLabel: /属性 项目号/,
    draftChip: "草稿 1/1", preview: "预览变更", previewTitle: "完整变更预览", noBlocking: "无阻断诊断",
    write: "确认写入", publishConfirm: /确认发布/,
    queued: /已排队 · 0% · 第 0 次/, overlay: "任务浮层", progressTab: "实施进度",
    revisionsTitle: "永久修订", restorePreview: "恢复预览",
    selectRow: "选择图纸 001",
  },
  "en-US": {
    welcomeHeading: "Open Sheet Set", selectDst: "Select DST File",
    settings: "Settings", settingsDialog: "Settings", generalSection: "General", localeLabel: "UI language",
    close: "Close", cadVersion: "AutoCAD version",
    tabs: {sheets: "Sheets", properties: "Properties", revisions: "Revision History"},
    headers: ["Sheet No.", "Title", "Status", "Actions"],
    sheetsetName: "Sheet set name", updateSheetSet: "Update Sheet Set", propertyLabel: /Property 项目号/,
    draftChip: "Draft 1/1", preview: "Preview Changes", previewTitle: "Full Change Preview", noBlocking: "No blocking diagnostics",
    write: "Confirm Write", publishConfirm: /Confirm Publish/,
    queued: /Queued · 0% · Attempt 0/, overlay: "Task overlay", progressTab: "Implementation Progress",
    revisionsTitle: "Permanent Revisions", restorePreview: "Restore Preview",
    selectRow: "Select sheet 001",
  },
} as const;

for (const locale of ["zh-CN", "en-US"] as const) {
  test(`${locale} 关键矩阵：启动/设置/打开/图纸/属性/预览/发布/任务/修订`, async ({page}) => {
    const s = L[locale];
    await installLocale(page, locale);
    await installRevisions(page);
    await page.route("**/api/workspaces/workspace-1/changes/execute", (route) =>
      route.fulfill({json: {id: "job-mx", status: "QUEUED", progress: 0, attempt: 0, files: []}}));
    await page.route("**/api/jobs/job-mx", (route) =>
      route.fulfill({json: {id: "job-mx", status: "QUEUED", progress: 0, attempt: 0, files: []}}));
    const {workspace} = await installSheetsFixture(page);
    await installSmartPreview(page, workspace);

    // —— 启动：语言在挂载前确定，欢迎区语义键渲染 ——
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", locale);
    await expect(page.getByRole("heading", {name: s.welcomeHeading})).toBeVisible();

    // —— 设置：对话框打开，界面分组在常规配置首位，语言选择渲染当前值 ——
    await page.getByRole("button", {name: s.settings}).click();
    const dialog = page.getByRole("dialog", {name: s.settingsDialog});
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("tab", {name: s.generalSection})).toHaveAttribute("aria-selected", "true");
    await expect(dialog.getByText(s.localeLabel)).toBeVisible();
    await expect(dialog.locator(`input[data-key="ui_locale"][value="${locale}"]`)).toBeChecked();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    // —— 打开：工作区打开，用户数据（图纸集名/DST 路径）原样 ——
    await page.getByRole("button", {name: s.selectDst}).click();
    await expect(page.locator(".workspace-name")).toHaveText("虚构图纸集");
    await expect(page.locator(".workspace-name")).toHaveAttribute("title", "C:\\虚构工程\\图纸集.dst");
    await expect(page.getByRole("button", {name: s.close})).toBeVisible();
    await expect(page.getByText(s.cadVersion)).toBeVisible();

    // —— 图纸：单表工作区，内置列头语义键渲染；子集名（用户数据）原样 ——
    await expect(page.getByRole("tab", {name: s.tabs.sheets})).toHaveAttribute("aria-selected", "true");
    for (const header of s.headers) await expect(page.getByRole("columnheader", {name: header})).toBeVisible();
    await expect(page.getByRole("treeitem", {name: /建筑施工图/}).first()).toBeVisible();

    // —— 属性：字段标签语义键渲染，属性名与值（用户数据）原样 ——
    await page.getByRole("tab", {name: s.tabs.properties}).click();
    const nameInput = page.getByLabel(s.sheetsetName, {exact: true});
    await expect(nameInput).toBeVisible();
    await expect(page.getByLabel(s.propertyLabel)).toHaveValue("P-FAKE");

    // —— 预览：草稿动作后预览门禁放行，预览标题与诊断语义键渲染 ——
    await nameInput.fill("改名后的虚构图纸集");
    await page.getByRole("button", {name: s.updateSheetSet}).click();
    await expect(page.getByText(s.draftChip)).toBeVisible();
    await page.getByRole("tab", {name: s.tabs.sheets}).click();
    await page.getByRole("button", {name: s.preview}).click();
    await expect(page.getByRole("heading", {name: s.previewTitle})).toBeVisible();
    await expect(page.getByText(s.noBlocking)).toBeVisible();

    // —— 发布：确认模态（不可逆勾选）→ 任务建立 ——
    await page.getByRole("button", {name: s.write}).click();
    await confirmModal(page, s.publishConfirm);
    await expect(page.getByText(s.queued)).toBeVisible();

    // —— 任务：浮层实施进度页签展示同一任务 ——
    const overlay = page.getByRole("complementary", {name: s.overlay});
    await overlay.getByRole("tab", {name: s.progressTab}).click();
    await expect(page.getByText(s.queued)).toBeVisible();

    // —— 修订：修订哈希（用户数据）原样，恢复入口语义键渲染 ——
    await page.getByRole("tab", {name: s.tabs.revisions}).click();
    await expect(page.getByRole("heading", {name: s.revisionsTitle})).toBeVisible();
    await expect(page.getByText("aaaaaaaa → bbbbbbbb")).toBeVisible();
    await expect(page.getByRole("button", {name: s.restorePreview}).first()).toBeVisible();
  });
}

test("语言切换不变量：workspace/revision/draft/selection/job 标识与输入保持", async ({page}) => {
  const s = L["zh-CN"];
  const executeBodies: unknown[] = [];
  await installLocale(page, "zh-CN");
  await installRevisions(page);
  await installMockEventSource(page);
  await page.route("**/api/workspaces/workspace-1/changes/execute", async (route) => {
    executeBodies.push(await route.request().postDataJSON());
    return route.fulfill({json: {id: "job-inv", status: "QUEUED", progress: 0, attempt: 0, files: []}});
  });
  await page.route("**/api/jobs/job-inv", (route) =>
    route.fulfill({json: {id: "job-inv", status: "QUEUED", progress: 0, attempt: 0, files: []}}));
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);

  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await page.getByRole("button", {name: s.selectDst}).click();
  await expect(page.locator(".workspace-name")).toHaveText("虚构图纸集");

  // 属性页：未提交输入 + 一个草稿动作
  await page.getByRole("tab", {name: s.tabs.properties}).click();
  // 语言容忍定位（main.spec Task 5 同款）：切换后该输入可访问名合法变为英文名
  const nameInput = page.getByLabel(/^(图纸集名称|Sheet set name)$/);
  await nameInput.fill("不变量校验集");
  await page.getByRole("button", {name: s.updateSheetSet}).click();
  await expect(page.getByText(s.draftChip)).toBeVisible();

  // 图纸页：选区（001 勾选）
  await page.getByRole("tab", {name: s.tabs.sheets}).click();
  await page.getByRole("checkbox", {name: s.selectRow}).check();

  // 预览 + 发布：任务建立，SSE 连接 URL 不携带语言
  await page.getByRole("button", {name: s.preview}).click();
  await expect(page.getByRole("heading", {name: s.previewTitle})).toBeVisible();
  await page.getByRole("button", {name: s.write}).click();
  await confirmModal(page, s.publishConfirm);
  await expect(page.getByText(s.queued)).toBeVisible();
  const sseUrlsBefore = await page.evaluate(() => (window as any).__eventSources.map((source: any) => source.url));
  expect(sseUrlsBefore).toContain("/api/jobs/job-inv/events");

  // 修订历史：切换前基线
  await page.getByRole("tab", {name: s.tabs.revisions}).click();
  await expect(page.getByText("aaaaaaaa → bbbbbbbb")).toBeVisible();

  // —— 设置保存切换 en-US（PUT 被拦截，不落盘；GET 快照驱动其余语言状态）——
  await page.getByRole("button", {name: s.settings}).click();
  await page.locator('input[data-key="ui_locale"][value="en-US"]').check();
  await page.getByRole("button", {name: "保存"}).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", {name: "Settings"})).toBeHidden();

  // 不变量：workspace 标识不变（DST 路径 title 原样；顶栏名反映同一草稿名，未被语言切换重置）
  await expect(page.locator(".workspace-name")).toHaveAttribute("title", "C:\\虚构工程\\图纸集.dst");
  await expect(page.locator(".workspace-name")).toHaveText("不变量校验集");
  // 不变量：修订历史原样（仍在修订页签；修订 ID/哈希不被语言改写）
  await expect(page.getByText("aaaaaaaa → bbbbbbbb")).toBeVisible();
  // 不变量：选区保留——回到图纸页签（标签页签随语言渲染），同一行 checkbox 仍勾选
  await page.getByRole("tab", {name: L["en-US"].tabs.sheets}).click();
  await expect(page.getByRole("checkbox", {name: L["en-US"].selectRow})).toBeChecked();
  // 不变量：未提交输入保留——切到属性页签，输入从草稿/表单状态原样恢复（英文标签渲染）
  await page.getByRole("tab", {name: L["en-US"].tabs.properties}).click();
  await expect(nameInput).toHaveValue("不变量校验集");
  // 不变量：草稿保留（同一存储草稿以英文语义键渲染）
  await expect(page.getByText(L["en-US"].draftChip)).toBeVisible();
  // 不变量：任务不重建（状态语义不变，仅渲染语言变化；SSE 连接集合不变）
  await expect(page.getByText(L["en-US"].queued)).toBeVisible();
  const sseUrlsAfter = await page.evaluate(() => (window as any).__eventSources.map((source: any) => source.url));
  expect(sseUrlsAfter).toEqual(sseUrlsBefore);
  // 不变量：发布未重跑（execute 仅切换前那一次）
  expect(executeBodies).toHaveLength(1);
});
