// PLAN-DM-015 实施评审整改：验证用户实际可见结果，而不是只验证 DOM/tooltip 存在。
import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";

async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("table", {name: "图纸表格"})).toBeVisible();
}

test("顶栏显示图纸集名称和清晰的打开所在文件夹按钮", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);

  const topbar = page.getByRole("banner");
  await expect(topbar.getByText("虚构图纸集", {exact: true})).toBeVisible();
  await expect(topbar.getByText("C:\\虚构工程\\图纸集.dst", {exact: true})).toHaveCount(0);

  const folder = topbar.getByRole("button", {name: "打开图纸集所在文件夹"});
  await expect(folder).toContainText("打开所在文件夹");
  const box = await folder.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(112);
  expect(box?.height).toBeGreaterThanOrEqual(32);
});

test("文件名列只显示独立文件名而不显示目录", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);

  const file = page.locator(".sheet-table-window tbody tr").first().locator(".col-file .ellipsis");
  await expect(file).toHaveText("01 分册.dwg");
  await expect(file).toHaveAttribute("title", "01 分册.dwg");
  await expect(file).not.toContainText("C:\\虚构工程");
});

test("桌面宽屏下标题和子集列保持可读宽度", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installSheetsFixture(page);
  await openWorkspace(page);

  const firstRow = page.locator(".sheet-table-window tbody tr").first();
  expect((await firstRow.locator(".col-title").boundingBox())?.width).toBeGreaterThanOrEqual(180);
  expect((await firstRow.locator(".col-subset").boundingBox())?.width).toBeGreaterThanOrEqual(190);
});

test("导航默认收起图纸并支持双行名称和键盘调宽", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installSheetsFixture(page, {longText: true});
  await openWorkspace(page);

  // 全部图纸范围下先只呈现子集，避免真实工程的图纸节点淹没导航层级。
  await expect(page.getByRole("treeitem", {name: "001 图纸 1"})).toHaveCount(0);

  const separator = page.getByRole("separator", {name: "调整图纸导航栏宽度"});
  const pane = page.locator(".sheet-tree-pane");
  await expect(separator).toBeVisible();
  expect((await pane.boundingBox())?.width).toBeGreaterThanOrEqual(300);
  await separator.focus();
  await page.keyboard.press("End");
  expect((await pane.boundingBox())?.width).toBeGreaterThanOrEqual(419);
  await page.keyboard.press("Home");
  expect((await pane.boundingBox())?.width).toBeLessThanOrEqual(261);
  const handle = await separator.boundingBox();
  expect(handle).not.toBeNull();
  await page.mouse.move(handle!.x + handle!.width / 2, handle!.y + handle!.height / 2);
  await page.mouse.down();
  await page.mouse.move(handle!.x + 82, handle!.y + handle!.height / 2);
  await page.mouse.up();
  expect((await pane.boundingBox())?.width).toBeGreaterThanOrEqual(330);

  // 选择子集后自动展开；名称使用双行而非强制单行省略。
  await page.getByRole("treeitem", {name: /暖通施工图/}).click();
  const longLabel = page.getByRole("treeitem", {name: /013 .*超长标题/}).locator(".node-label");
  await expect(longLabel).toBeVisible();
  await expect(longLabel).toHaveCSS("white-space", "normal");
  await expect(longLabel).toHaveCSS("-webkit-line-clamp", "2");
});

test("图纸工作区和主表填满 ActionDock 上方剩余高度", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installSheetsFixture(page);
  await openWorkspace(page);

  const gaps = await page.evaluate(() => {
    const workspace = document.querySelector<HTMLElement>(".sheets-workspace")!.getBoundingClientRect();
    const table = document.querySelector<HTMLElement>(".sheet-table-window")!.getBoundingClientRect();
    const shell = document.querySelector<HTMLElement>(".shell-main")!.getBoundingClientRect();
    return {
      workspaceToShell: shell.bottom - workspace.bottom,
      tableToWorkspace: workspace.bottom - table.bottom,
    };
  });
  expect(gaps.workspaceToShell).toBeLessThanOrEqual(24);
  expect(gaps.tableToWorkspace).toBeLessThanOrEqual(20);
});

test("900px 宽度下底部操作按钮不被任务栏遮挡", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installSheetsFixture(page);
  await openWorkspace(page);

  const confirm = page.getByRole("button", {name: "确认写入"});
  const taskRail = page.getByRole("complementary", {name: "任务浮层"});
  const [confirmBox, railBox] = await Promise.all([confirm.boundingBox(), taskRail.boundingBox()]);
  expect(confirmBox).not.toBeNull();
  expect(railBox).not.toBeNull();
  expect(confirmBox!.x + confirmBox!.width).toBeLessThanOrEqual(railBox!.x);
});
