// 创建向导第四阶段「检查并创建」e2e（SPEC-DM-018 §6–§8；PLAN-DM-036 Task 9）。
// 覆盖：顶部权威摘要、按组一行主表（无单张行与「布局」列）、不编号组单值范围、后端紧凑
// 标题、真实 DWG 文件名、动态属性列（同值 / 多值 / 首张空值）、逐张属性模态（键盘打开、
// Esc/关闭按钮退出、焦点回归）、诊断的阻断/非阻断分区与跳回定位、预览失效门禁、只发
// `preview_digest` 的执行与不可覆盖确认、失败保留草稿可重试、成功后按 `workspace_id`
// 切换普通工作区，以及 900×768、浅深主题下页面整体不横溢。
// 权威预览、执行入队与任务终态全部由 fixtures/creation 的 route mock 给出：前端只投影，
// 不自行推算图号、标题、DWG 文件名或派生值。
import {expect, test, type Page} from "@playwright/test";
import {
  chooseStandard,
  creationFailedJob,
  creationPreview,
  creationPreviewWithDiagnostics,
  installCreation,
  openCreation,
  openGroupsStep,
} from "./fixtures/creation";
import {installPreferenceSnapshot} from "./fixtures/settings";

test.beforeEach(async ({page}) => {
  // 与既有创建 spec 同型的假壳桥：目录选择与列配置经桥返回，不触发真实文件系统
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => null,
        select_folder: async () => (window as any).__fakeFolder ?? null,
        on_files_dropped: async () => {},
        load_sheet_columns: async () => ({ok: true, value: null}),
        save_sheet_columns: async () => ({ok: true, value: null}),
        open_workspace_folder: async () => ({ok: true, value: null}),
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
});

/** 建立可执行草稿并进入第四阶段（预览在进入时由后端权威结果给出）。 */
async function openReviewStep(page: Page): Promise<void> {
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await page.getByRole("button", {name: "下一步"}).click();
  await expect(page.getByRole("region", {name: "检查并创建"})).toBeVisible();
}

/** 某个图纸组行的定位器（按稳定的 `data-group-id`）。 */
function previewRow(page: Page, groupId: string) {
  return page.locator(`tr[data-group-id="${groupId}"]`);
}

/** 某个属性单元格定位器（列身份来自后端 `property_cells` 的键）。 */
function previewCell(page: Page, groupId: string, propertyId: string) {
  return previewRow(page, groupId).locator(`td[data-property-id="${propertyId}"]`);
}

async function noPageOverflow(page: Page, label: string): Promise<void> {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth, label).toBeLessThanOrEqual(clientWidth);
}

test("顶部摘要与按组一行主表只呈现后端权威结果", async ({page}) => {
  const state = await installCreation(page);
  await openReviewStep(page);

  // 顶部：固定标准、最终项目路径、组数/张数/DWG 数、当前编号设置与检查状态
  await expect(page.getByTestId("creation-fixed-standard")).toContainText("szmedi.gas");
  await expect(page.getByTestId("creation-preview-context")).toContainText("D:\\项目\\新建项目");
  const summary = page.getByTestId("creation-preview-summary");
  await expect(summary).toContainText("3 个图纸组");
  await expect(summary).toContainText("6 张图纸");
  await expect(summary).toContainText("3 个 DWG");
  await expect(page.getByTestId("creation-preview-numbering")).toContainText("2 位");
  await expect(page.getByTestId("creation-preview-status")).toHaveText("全部检查通过");
  expect(state.previewRequests).toBe(1);

  // 主表：固定列 + 标准动态 sheet 属性列；没有「布局」列，也没有单张 Sheet 行
  const table = page.getByTestId("creation-preview-table");
  for (const column of ["图纸组", "图纸范围", "图纸", "张数", "文件名", "基础模板", "布局模板", "图幅", "图纸阶段", "设计人"]) {
    await expect(table.getByRole("columnheader", {name: column, exact: true})).toBeVisible();
  }
  await expect(table.getByRole("columnheader", {name: "布局", exact: true})).toHaveCount(0);
  await expect(table.locator("tbody tr")).toHaveCount(3);

  // 图纸范围与紧凑标题来自后端：不编号组只显示同位数单值 00，不显示 00-00
  const cover = previewRow(page, "group-1");
  await expect(cover).toContainText("00");
  await expect(cover).not.toContainText("00-00");
  await expect(cover).toContainText("封面");
  await expect(cover).toContainText("RQ-封面.dwg");
  const plan = previewRow(page, "group-2");
  await expect(plan).toContainText("01-03");
  await expect(plan).toContainText("平面图 (一)-(三)");
  await expect(plan).toContainText("RQ-平面图.dwg");
  const section = previewRow(page, "group-3");
  await expect(section).toContainText("04-05");
  await expect(section).toContainText("纵断面图");
  await expect(section).toContainText("RQ-纵断面图.dwg");
});

test("组内同值直接显示，多值显示首张值加省略号，首张为空显示（空）加省略号", async ({page}) => {
  await installCreation(page);
  await openReviewStep(page);

  // 组内全同：直接显示值，不给「…」
  await expect(previewCell(page, "group-1", "prop-stage")).toHaveText("施工图");
  await expect(previewCell(page, "group-2", "prop-designer")).toHaveText("张工");

  // 组内不同：显示第一张实际值 + 可点击的「…」
  const stage = previewCell(page, "group-2", "prop-stage");
  await expect(stage).toContainText("施工图");
  await expect(stage.getByRole("button", {name: "查看第 2 组图纸阶段的全部图纸值"})).toBeVisible();
  await expect(previewCell(page, "group-1", "prop-stage").getByRole("button")).toHaveCount(0);

  // 首张为空：明确显示「（空）」再加「…」，绝不显示「多值」
  const designer = previewCell(page, "group-3", "prop-designer");
  await expect(designer).toContainText("（空）");
  await expect(designer.getByRole("button", {name: "查看第 3 组设计人的全部图纸值"})).toBeVisible();
  await expect(page.getByTestId("creation-preview-table")).not.toContainText("多值");
});

test("逐张属性模态列出全部图纸，支持键盘打开、Esc 与关闭按钮退出并归还焦点", async ({page}) => {
  await installCreation(page);
  await openReviewStep(page);

  const trigger = previewCell(page, "group-2", "prop-stage").getByRole("button");
  // 键盘打开：聚焦后回车
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", {name: "平面图 · 图纸阶段"});
  await expect(dialog).toBeVisible();
  // 只展示所点属性，按组内顺序列出全部图纸的图号｜图纸标题｜实际值
  await expect(dialog.getByRole("columnheader", {name: "图号"})).toBeVisible();
  await expect(dialog.getByRole("columnheader", {name: "图纸标题"})).toBeVisible();
  await expect(dialog.getByRole("columnheader", {name: "图纸阶段"})).toBeVisible();
  await expect(dialog.getByRole("columnheader", {name: "设计人"})).toHaveCount(0);
  const rows = dialog.locator("tbody tr");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText("01");
  await expect(rows.nth(0)).toContainText("平面图 (一)");
  await expect(rows.nth(0)).toContainText("施工图");
  await expect(rows.nth(1)).toContainText("竣工图");
  await expect(rows.nth(2)).toContainText("平面图 (三)");

  // Esc 退出并把焦点归还触发按钮
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();

  // 关闭按钮退出同样归还焦点
  await trigger.click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "关闭"}).click();
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("输入变化后不复用旧摘要，重新检查通过后才可执行", async ({page}) => {
  const state = await installCreation(page);
  // 预览延迟返回：用于观察「旧摘要已失效、新检查未完成」的中间态（无任何可执行入口）
  await page.route(url => url.pathname.endsWith("/preview"), async route => {
    state.previewRequests += 1;
    await new Promise(resolve => setTimeout(resolve, 1000));
    await route.fulfill({json: creationPreview()});
  });
  await openReviewStep(page);
  const execute = page.getByTestId("creation-execute");

  // 首次进入：检查未完成前没有任何可执行入口
  await expect(page.getByTestId("creation-preview-loading")).toBeVisible();
  await expect(execute).toHaveCount(0);
  await expect(page.getByTestId("creation-preview-table")).toBeVisible();
  await expect(execute).toBeEnabled();
  expect(state.previewRequests).toBe(1);

  // 回到项目信息改一个属性值：回到第四阶段时旧摘要不得被复用，必须重新请求权威预览
  await page.getByRole("button", {name: "上一步"}).click();
  await expect(page.getByRole("region", {name: "图纸组"})).toBeVisible();
  await page.getByRole("button", {name: "上一步"}).click();
  await page.getByLabel("工程名称").fill("滨河路改造工程");
  await page.getByRole("button", {name: "下一步"}).click();
  await page.getByRole("button", {name: "下一步"}).click();

  await expect(page.getByTestId("creation-preview-loading")).toBeVisible();
  await expect(execute).toHaveCount(0);
  await expect(page.getByTestId("creation-preview-table")).toBeVisible();
  await expect(execute).toBeEnabled();
  expect(state.previewRequests).toBe(2);
});

test("阻断错误与非阻断提示分区呈现，错误可跳回并定位到组行与项目字段", async ({page}) => {
  await installCreation(page, {preview: creationPreviewWithDiagnostics()});
  await openReviewStep(page);

  const errors = page.getByTestId("creation-preview-errors");
  await expect(errors).toBeVisible();
  await expect(errors).toContainText("图纸组图名不能为空");
  await expect(errors).toContainText("必填属性缺少值");
  await expect(page.getByTestId("creation-preview-status")).toHaveText("2 项阻断错误");
  // 非阻断提示单独呈现，不混进阻断错误
  const warnings = page.getByTestId("creation-preview-warnings");
  await expect(warnings).toBeVisible();
  await expect(warnings).toContainText("目标DWG内布局名重复：平面图-01");
  await expect(errors).not.toContainText("目标DWG内布局名重复");
  // 有阻断错误时不得创建
  await expect(page.getByTestId("creation-execute")).toBeDisabled();

  // 组行错误：跳回图纸组并定位到该行图名
  await errors.getByRole("button", {name: "返回修改第 1 项"}).click();
  await expect(page.getByRole("region", {name: "图纸组"})).toBeVisible();
  const title = previewRow(page, "group-1").locator('input[type="text"]').first();
  await expect(title).toBeFocused();

  // 项目字段错误：跳回项目信息并定位到该属性输入
  await page.getByRole("button", {name: "下一步"}).click();
  await expect(page.getByRole("region", {name: "检查并创建"})).toBeVisible();
  await page.getByTestId("creation-preview-errors").getByRole("button", {name: "返回修改第 2 项"}).click();
  await expect(page.getByRole("region", {name: "项目信息"})).toBeVisible();
  await expect(page.getByLabel("工程名称")).toBeFocused();
});

test("执行只发送 preview_digest，创建前展示最终路径与不可覆盖确认，成功后切换普通工作区", async ({page}) => {
  const state = await installCreation(page);
  await page.route("**/api/workspaces/created-1", route =>
    route.fulfill({
      json: {
        id: "created-1",
        revision_id: "revision-1",
        dst_path: "D:\\项目\\新建项目\\图纸集.dst",
        root: "D:\\项目\\新建项目",
        unreferenced_dwgs: [],
        dst_validation: {status: "VALID", actions: [], blocking_issues: []},
        sheet_set: {name: "新建项目", sheet_count: 6, subset_count: 3, custom_properties: {}, property_definitions: [], subsets: []},
        diagnostics: [],
      },
    }),
  );
  await page.route("**/api/workspaces/created-1/draft", route =>
    route.fulfill({json: {draft: null, corrupted: false, stale: false, stale_reasons: []}}),
  );
  await openReviewStep(page);

  await page.getByTestId("creation-execute").click();
  const confirm = page.getByRole("dialog", {name: "创建并打开图纸集？"});
  await expect(confirm).toBeVisible();
  // 创建前展示最终路径，并要求勾选不可覆盖确认后才可提交
  await expect(confirm).toContainText("D:\\项目\\新建项目");
  await expect(confirm.getByRole("button", {name: "创建并打开图纸集"})).toBeDisabled();
  await confirm.getByRole("button", {name: "取消"}).click();
  expect(state.executeBodies).toHaveLength(0);

  await page.getByTestId("creation-execute").click();
  await confirm.getByRole("checkbox").check();
  await confirm.getByRole("button", {name: "创建并打开图纸集"}).click();

  // 执行只发送权威摘要，不夹带任何派生输出
  await expect.poll(() => state.executeBodies.length).toBe(1);
  expect(state.executeBodies[0]).toEqual({preview_digest: "digest-1"});
  // 创建任务进度经同一个任务面板与终态语义订阅（SSE 事件流）
  await expect.poll(() => state.jobStreams).toBe(1);
  // 成功后用返回的 workspace_id 切换普通工作区
  await expect(page.getByRole("region", {name: "检查并创建"})).toHaveCount(0);
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.getByRole("banner")).toContainText("新建项目");
});

test("创建失败保留草稿与诊断，修正后重新预览并以新任务重试", async ({page}) => {
  const state = await installCreation(page, {jobResult: creationFailedJob()});
  await openReviewStep(page);

  await page.getByTestId("creation-execute").click();
  await page.getByRole("dialog", {name: "创建并打开图纸集？"}).getByRole("checkbox").check();
  await page.getByRole("dialog", {name: "创建并打开图纸集？"}).getByRole("button", {name: "创建并打开图纸集"}).click();

  // 失败保留草稿与可读诊断；旧摘要失效（不再有可执行入口），必须重新检查后才可重试
  await expect(page.getByTestId("creation-job")).toContainText("FAILED");
  await expect(page.getByTestId("creation-job")).toContainText("CREATION_PUBLISH_FAILED");
  await expect(page.getByRole("region", {name: "检查并创建"})).toBeVisible();
  await expect(page.getByTestId("creation-preview-stale")).toBeVisible();
  await expect(page.getByTestId("creation-execute")).toHaveCount(0);
  expect(state.drafts.has("draft-1")).toBe(true);

  await page.getByTestId("creation-preview-recheck").click();
  await expect(page.getByTestId("creation-execute")).toBeEnabled();
  await page.getByTestId("creation-execute").click();
  await page.getByRole("dialog", {name: "创建并打开图纸集？"}).getByRole("checkbox").check();
  await page.getByRole("dialog", {name: "创建并打开图纸集？"}).getByRole("button", {name: "创建并打开图纸集"}).click();
  await expect.poll(() => state.executeBodies.length).toBe(2);
  await expect.poll(() => state.jobStreams).toBe(2);
});

test("900×768、200% 缩放与浅深主题下页面整体不横溢，主表自身横向滚动", async ({page}) => {
  for (const theme of ["light", "dark"] as const) {
    await installPreferenceSnapshot(page, theme);
    await installCreation(page);
    await page.setViewportSize({width: 900, height: 768});
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await openReviewStep(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await noPageOverflow(page, `检查并创建 ${theme} 900x768`);
    // 200% 缩放（与既有视觉证据 spec 同口径：CSS zoom 2）：页面整体仍不横溢，主表自身滚动
    await page.evaluate(() => document.documentElement.style.setProperty("zoom", "2"));
    await noPageOverflow(page, `检查并创建 ${theme} 200% 缩放`);
    const scroll = await page.locator(".table-scroll").evaluate(el => getComputedStyle(el).overflowX);
    expect(scroll).toBe("auto");
    await page.evaluate(() => document.documentElement.style.removeProperty("zoom"));
  }
});
