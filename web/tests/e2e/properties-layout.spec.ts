// PLAN-DM-016 任务 6：属性页几何与布局契约 e2e（SPEC-DM-010 P-07/P-13，SPEC-DM-009 控件密度）。
// 覆盖：38px 文本输入/选择器、普通按钮 36px 基线（属性页无 34px 紧凑工具档，见 design-qa 遗留复评）、
// 60px 面板标题栏、独立语义卡片（细边框/浅阴影/16px 卡片间距）、四视口无横向溢出、
// 单一主纵向滚动区（页面不滚动，仅 shell-main 纵向滚动）。
import {expect, test, type Page} from "@playwright/test";
import {installPropertiesFixture, openProperties} from "./fixtures/properties";

// 安装夹具、打开属性页并展开定义面板、打开 CSV 导入区，让全部控件进入可视状态
async function openFullWorkspace(page: Page, theme?: "light" | "dark") {
  await installPropertiesFixture(page, {theme});
  await openProperties(page);
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  await page.getByRole("button", {name: "导入 / 导出"}).click();
}

async function inputHeights(page: Page): Promise<number[]> {
  return page.locator(".properties-view input[type=\"text\"], .properties-view input[type=\"search\"], .properties-view select")
    .evaluateAll((elements) => elements.map((el) => el.getBoundingClientRect().height));
}

test("文本输入与选择器统一 38px", async ({page}) => {
  await openFullWorkspace(page);
  const heights = await inputHeights(page);
  expect(heights.length).toBeGreaterThanOrEqual(8);
  for (const height of heights) expect(height).toBe(38);
});

test("按钮 36px 普通档基线：无低于 36px 高度的按钮", async ({page}) => {
  await openFullWorkspace(page);
  const buttons = page.locator(".properties-view button:visible");
  const count = await buttons.count();
  expect(count).toBeGreaterThanOrEqual(10);
  const heights = await buttons.evaluateAll((elements) => elements.map((el) => el.getBoundingClientRect().height));
  for (const height of heights) expect(height).toBeGreaterThanOrEqual(36);
});

test("面板标题栏 60px：折叠与展开状态都不低于 60px", async ({page}) => {
  await openFullWorkspace(page);
  const heads = page.locator(".properties-view .panel-head");
  await expect(heads).toHaveCount(3);
  for (const head of await heads.all()) {
    const box = await head.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(60);
  }
  // 折叠值面板后标题栏仍保持 60px 与状态层级
  await page.getByRole("button", {name: "收起图纸集属性值"}).click();
  const box = await page.locator(".value-panel .panel-head").boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(60);
});

test("独立语义卡片：细边框、浅阴影与 16px 卡片间距", async ({page}) => {
  await openFullWorkspace(page);
  const cards = page.locator(".properties-view > section");
  await expect(cards).toHaveCount(3);
  for (const card of await cards.all()) {
    const style = await card.evaluate((el) => {
      const computed = getComputedStyle(el);
      return {border: computed.borderTopWidth, shadow: computed.boxShadow, radius: computed.borderTopLeftRadius};
    });
    expect(style.border).toBe("1px");
    expect(style.shadow).not.toBe("none");
    expect(style.radius).not.toBe("0px");
  }
  const gap = await page.locator(".properties-view").evaluate((el) => getComputedStyle(el).columnGap);
  expect(parseFloat(gap)).toBe(16);
});

test("四视口双主题无整页横向溢出", async ({page}) => {
  for (const [width, height] of [[1024, 768], [1120, 768], [1440, 900], [900, 768]] as const) {
    await page.setViewportSize({width, height});
    for (const theme of ["light", "dark"] as const) {
      await openFullWorkspace(page, theme);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      expect(scrollWidth, `${width}x${height} ${theme}`).toBeLessThanOrEqual(clientWidth);
    }
  }
});

test("单一主纵向滚动区：页面不滚动，仅 shell-main 纵向滚动", async ({page}) => {
  await page.setViewportSize({width: 1024, height: 768});
  await openFullWorkspace(page);
  const result = await page.evaluate(() => {
    const root = document.documentElement;
    const main = document.querySelector<HTMLElement>(".shell-main");
    const mainScrollable = main ? main.scrollHeight > main.clientHeight + 1 : false;
    // 除 shell-main 外不应有其他纵向滚动容器（属性面板只允许横向滚动窗口）
    const others = Array.from(document.querySelectorAll<HTMLElement>(".properties-view, .properties-view *"))
      .filter((el) => el.scrollHeight > el.clientHeight + 1);
    return {pageScrollable: root.scrollHeight > root.clientHeight + 1, mainScrollable, otherCount: others.length};
  });
  expect(result.pageScrollable).toBe(false);
  expect(result.mainScrollable).toBe(true);
  expect(result.otherCount).toBe(0);
});
