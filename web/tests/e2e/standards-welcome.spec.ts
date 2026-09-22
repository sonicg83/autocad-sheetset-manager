// 欢迎页"打开优先"与标准入口 e2e（PLAN-DM-035 Task 7 / SPEC-DM-016 §2）。
// 断言全部语义化：欢迎页主任务唯一性、标准管理是应用级表面（不进工作区标签栏）、
// 无壳降级路径输入不回归、900×768 无横向滚动、普通 DST 打开不回归。
import {expect, test, type Page} from "@playwright/test";

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

test("从标准创建图纸集入口当前明确不可用且不回退", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await page.getByRole("button", {name: "从标准创建图纸集"}).click();
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
