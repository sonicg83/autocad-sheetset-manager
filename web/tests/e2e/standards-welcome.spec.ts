// 欢迎页"打开优先"与标准入口 e2e（PLAN-DM-035 Task 7 / SPEC-DM-016 §2）。
// 断言全部语义化：欢迎页主任务唯一性、标准管理是应用级表面（不进工作区标签栏）、
// 无壳降级路径输入不回归、900×768 无横向滚动、普通 DST 打开不回归。
import {expect, test, type Page} from "@playwright/test";
import {installStandards, libraryItems, openStandards, published} from "./fixtures/standards";

const workspace = {
  id: "workspace-1", revision_id: "revision-1", dst_path: "C:\\project\\test.dst",
  sheet_set: {name: "测试图纸集", sheet_count: 1, subset_count: 1, custom_properties: {}, property_definitions: [], subsets: []},
  diagnostics: [],
};

test.beforeEach(async ({page}) => {
  // 与 main.spec 同型的假壳桥：e2e 默认有壳（选择 DST 文件按钮为主操作）
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => (window as any).__fakeSelectResult ?? null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
});

test("欢迎页保持打开 DST 为唯一主任务", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "打开图纸集"})).toBeVisible();
  const primary = page.getByRole("button", {name: "选择 DST 文件"});
  await expect(primary).toBeVisible();
  await expect(primary).toHaveClass(/primary/);
  // 次要动作：进入标准管理是应用级表面，不创建工作区、无工作区标签栏
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(page.getByRole("heading", {name: "标准管理"})).toBeVisible();
  await expect(page.locator(".workspace-tabs")).toHaveCount(0);
  await expect(page.getByRole("tablist")).toHaveCount(0);
  // 返回欢迎页，不创建工作区
  await page.getByRole("button", {name: "返回欢迎页"}).click();
  await expect(page.getByRole("heading", {name: "打开图纸集"})).toBeVisible();
});

test("欢迎页为打开优先双栏且三个次级任务走既有去向", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installStandards(page, []);
  await page.goto("/");
  const layout = page.getByTestId("welcome-layout");
  await expect(layout).toBeVisible();
  await expect(layout.getByTestId("welcome-open-card")).toBeVisible();
  await expect(layout.getByTestId("welcome-task-card")).toBeVisible();
  // 打开 DST 是唯一主强调动作：三个次级入口不得与它争夺视觉层级。
  // 限定在欢迎页布局内——常驻 DOM 的共享三选一对话框（关窗 display:none）也带 .primary，
  // 那是工作区门禁的按钮，不属于本页的视觉层级。
  await expect(layout.locator("button.primary")).toHaveCount(1);
  await expect(page.getByRole("button", {name: "创建新图纸集"})).toBeVisible();
  await expect(page.getByRole("button", {name: "管理图纸标准"})).toBeVisible();
  await expect(page.getByRole("button", {name: "导入标准包"})).toBeVisible();

  // 创建：进入既有明确不可用占位，不回退到无标准创建
  await page.getByRole("button", {name: "创建新图纸集"}).click();
  await expect(page.getByRole("heading", {name: "从标准创建图纸集"})).toBeVisible();
  await expect(page.getByText("该入口将在后续版本提供", {exact: false})).toBeVisible();
  await page.getByRole("button", {name: "返回欢迎页"}).click();

  // 导入标准包：进入标准库并直接打开唯一既有导入对话框
  await page.getByRole("button", {name: "导入标准包"}).click();
  await expect(page.getByRole("heading", {name: "标准管理"})).toBeVisible();
  await expect(page.getByRole("dialog", {name: "导入标准包"})).toBeVisible();
});

test("900×768 欢迎页单列且打开任务仍排在最前", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, []);
  await page.goto("/");
  const layout = page.getByTestId("welcome-layout");
  await expect(layout).toBeVisible();
  // 单列：主卡与任务卡在同一列的上下相邻位置，且主卡在上
  const columns = await layout.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(" "));
  expect(columns).toHaveLength(1);
  const openBox = (await layout.getByTestId("welcome-open-card").boundingBox())!;
  const taskBox = (await layout.getByTestId("welcome-task-card").boundingBox())!;
  expect(openBox.y).toBeLessThan(taskBox.y);
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(900);
});

test("从标准创建图纸集入口当前明确不可用且不回退", async ({page}) => {
  // Task 8 起“用于创建图纸集”位于已发布版本的详情动作（SPEC-DM-016 §5）：
  // 入口不再挂在标准管理页头部，而是逐标准提供（官方/已发布版本可选，草稿不可）。
  await installStandards(page, [published("official", "2.1.0"), published("user", "2.0.0")]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "2.1.0"}).click();
  await page.getByRole("button", {name: "用于创建图纸集"}).click();
  await expect(page.getByRole("heading", {name: "从标准创建图纸集"})).toBeVisible();
  await expect(page.getByText("该入口将在后续版本提供", {exact: false})).toBeVisible();
  await page.getByRole("button", {name: "返回欢迎页"}).click();
  await expect(page.getByRole("heading", {name: "打开图纸集"})).toBeVisible();
});

test("无桌面壳时路径输入与打开行为不回归", async ({page}) => {
  const pageWithoutShell: Page = page;
  await pageWithoutShell.addInitScript(() => {
    (window as any).pywebview = undefined;
  });
  await pageWithoutShell.route("**/api/workspaces/open", route => route.fulfill({json: workspace}));
  await pageWithoutShell.goto("/");
  const input = pageWithoutShell.getByLabel("输入 .dst 绝对路径");
  await expect(input).toBeVisible();
  await pageWithoutShell.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(pageWithoutShell.getByRole("heading", {name: "标准管理"})).toBeVisible();
  // 标准上下文中返回欢迎页后，无壳路径输入仍可用（降级入口不被导航破坏）
  await pageWithoutShell.getByRole("button", {name: "返回欢迎页"}).click();
  await input.fill("C:\\project\\test.dst");
  await pageWithoutShell.getByRole("button", {name: "打开项目"}).click();
  await expect(pageWithoutShell.getByRole("button", {name: "关闭"})).toBeVisible();
});

test("普通 DST 打开行为不回归", async ({page}) => {
  await page.route("**/api/workspaces/open", route => route.fulfill({json: workspace}));
  await page.goto("/");
  await page.evaluate(() => {(window as any).__fakeSelectResult = "C:\\project\\test.dst";});
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.locator(".workspace-tabs")).toHaveCount(0);
});

test("900×768 视口下标准管理单列无横向滚动", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await page.goto("/");
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(page.getByRole("heading", {name: "标准管理"})).toBeVisible();
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(900);
});
