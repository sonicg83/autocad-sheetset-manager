// 创建向导长内容布局回归：图纸组增多时页脚必须跟随内容下移。
import {expect, test} from "@playwright/test";
import {chooseStandard, installCreation, openCreation, openGroupsStep} from "./fixtures/creation";

test("900×768 下多组表格不会与向导页脚重叠", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => null,
        select_folder: async () => null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);

  for (let index = 0; index < 12; index += 1) {
    await page.getByRole("button", {name: "新建图纸组"}).click();
  }

  const {cardBottom, footerTop, gap} = await page.evaluate(() => ({
    cardBottom: document.querySelector(".groups-step .card")!.getBoundingClientRect().bottom,
    footerTop: document.querySelector(".wizard-foot")!.getBoundingClientRect().top,
    gap: Number.parseFloat(getComputedStyle(document.querySelector(".create-wizard")!).rowGap),
  }));
  expect(footerTop - cardBottom, "页脚须位于全部图纸组内容之后").toBeGreaterThanOrEqual(gap - 1);
  await page.locator(".wizard-foot").scrollIntoViewIfNeeded();
  await expect(page.locator(".wizard-foot")).toBeInViewport();
});
