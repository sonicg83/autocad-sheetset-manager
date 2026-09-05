// PLAN-DM-017 实现截图：仅使用虚构夹具，不代表已完成 Demo 同状态视觉验收。
// 普通回归只生成测试附件；持久证据由验收时显式复制，避免自动改写仓库文件。
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";

type Theme = "light" | "dark";

async function openWorkspace(page: Page, theme: Theme) {
  await page.addInitScript(t => localStorage.setItem("dst-manager-theme", t), theme);
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("table", {name: "图纸表格"})).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

async function attachScreenshot(page: Page, info: TestInfo, state: string, theme: Theme) {
  const viewport = page.viewportSize()!;
  const name = `${state}-${viewport.width}x${viewport.height}-${theme}.png`;
  const path = info.outputPath(name);
  await page.screenshot({path, animations: "disabled"});
  await info.attach(name, {path, contentType: "image/png"});
}

for (const theme of ["light", "dark"] as const) {
  test(`1440 双主题七状态实现证据：${theme}`, async ({page}, info) => {
    await page.setViewportSize({width: 1440, height: 900});
    await installSheetsFixture(page);
    await openWorkspace(page, theme);
    await page.mouse.move(0, 0);
    await attachScreenshot(page, info, "default", theme);
    for (const [label, state] of [
      ["编辑子集", "edit-subset"],
      ["新增图纸", "insert-sheet"],
      ["新建子集", "insert-subset"],
    ]) {
      await page.getByRole("button", {name: label, exact: true}).click();
      await expect(page.getByRole("region", {name: label, exact: true})).toBeVisible();
      await page.mouse.move(0, 0);
      await attachScreenshot(page, info, state, theme);
      await page.getByRole("button", {name: "取消", exact: true}).click();
    }
    const firstRow = page.locator(".sheet-table-window tbody tr").first();
    await firstRow.locator(".title-text").hover();
    await attachScreenshot(page, info, "hover", theme);
    await page.getByLabel("选择图纸 001", {exact: true}).check();
    await page.mouse.move(0, 0);
    await expect(firstRow).toHaveClass(/selected/);
    await attachScreenshot(page, info, "selected", theme);
    await page.getByLabel("选择图纸 001", {exact: true}).uncheck();
    await page.getByRole("button", {name: "展开任务浮层"}).click();
    await expect(page.locator(".task-drawer")).toBeVisible();
    await page.mouse.move(0, 0);
    await attachScreenshot(page, info, "overlay", theme);
  });
}

for (const width of [1024, 1120, 900]) {
  for (const theme of (width === 900 ? ["dark"] : ["light", "dark"]) as Theme[]) {
    test(`小视口任务抽屉实现证据：${width} ${theme}`, async ({page}, info) => {
      await page.setViewportSize({width, height: 768});
      await installSheetsFixture(page);
      await openWorkspace(page, theme);
      await page.getByRole("button", {name: "展开任务浮层"}).click();
      await expect(page.locator(".task-drawer")).toBeVisible();
      await page.mouse.move(0, 0);
      await attachScreenshot(page, info, "overlay", theme);
    });
  }
}

test("操作列仅在横向溢出时固定且宽视口恢复普通列", async ({page}) => {
  await page.setViewportSize({width: 2200, height: 900});
  await installSheetsFixture(page);
  await openWorkspace(page, "light");
  const tableWindow = page.locator(".sheet-table-window");
  for (const width of [2200, 1024, 2200]) {
    await page.setViewportSize({width, height: 900});
    if (width === 1024) await expect(tableWindow).toHaveClass(/sticky-actions/);
    else await expect(tableWindow).not.toHaveClass(/sticky-actions/);
    await expect(page.locator("td.col-actions").first()).toHaveCSS("position", width === 1024 ? "sticky" : "static");
    const rects = await page.locator(".sheet-table-window thead th").evaluateAll(cells => cells.map(cell => {
      const {left, right} = cell.getBoundingClientRect();
      return {left, right};
    }));
    for (let i = 1; i < rects.length - 1; i++) expect(rects[i].left).toBeGreaterThanOrEqual(rects[i - 1].right - 1);
    if (width === 1024) {
      const tableBox = (await tableWindow.boundingBox())!;
      expect(rects.at(-1)!.right).toBeLessThanOrEqual(tableBox.x + tableBox.width + 1);
    }
  }
});
