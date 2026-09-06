// PLAN-DM-016 任务 6/7：属性页几何与布局契约 e2e（SPEC-DM-010 P-07/P-13，SPEC-DM-009 控件密度）。
// 覆盖：38px 文本输入/选择器、普通按钮 36px 基线（属性页无 34px 紧凑工具档与图标按钮，见 design-qa）、
// 60px 面板标题栏、独立语义卡片（细边框/浅阴影/16px 卡片间距且无旧 margin 叠加）、
// 四视口与 200% 缩放覆盖默认/dirty+pending/错误/新增/CSV 状态无整页横向溢出、
// 属性值两列按断点降一列、单一主纵向滚动区（页面不滚动，仅 shell-main 纵向滚动）、
// 定义表横向溢出时操作列冻结在容器右缘且表头同步冻结、无溢出时恢复普通列且无冻结阴影。
import {expect, test, type Page} from "@playwright/test";
import {installPropertiesFixture, openProperties, pendingDraft} from "./fixtures/properties";

const VIEWPORTS = [
  [1024, 768],
  [1120, 768],
  [1440, 900],
  [900, 768],
] as const;
const THEMES = ["light", "dark"] as const;
const STATES = ["default", "dirty-pending", "error", "add-field", "csv"] as const;
type StateName = (typeof STATES)[number];

// 安装夹具、打开属性页并展开定义面板，让全部控件进入可视状态（CSV 操作随面板常驻）
async function openFullWorkspace(page: Page, theme?: "light" | "dark") {
  await installPropertiesFixture(page, {theme});
  await openProperties(page);
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
}

// 打开指定业务状态（任务 7：布局矩阵与证据共用同一状态口径）
// - dirty-pending：预置待写入草稿（项目编号 → 待写入）+ 本地编辑（设计阶段 → 未加入草稿）
// - error：同上并在提交失败后注入字段错误（错误摘要 + 字段级错误）
// - add-field：展开定义面板并打开新增区（新增表单输入进入可视状态）
// - csv：打开 CSV 面板导入区
async function openState(page: Page, state: StateName, theme?: "light" | "dark") {
  const options: Parameters<typeof installPropertiesFixture>[1] = {theme};
  if (state === "dirty-pending" || state === "error") options.initialDraft = pendingDraft();
  if (state === "error") {
    options.failDraftSave = () => ({code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {项目编号: "演示校验错误"}});
  }
  await installPropertiesFixture(page, options);
  await openProperties(page);
  if (state === "dirty-pending" || state === "error") {
    await page.getByRole("textbox", {name: "属性 设计阶段"}).fill("初步设计");
  }
  if (state === "error") {
    await page.getByRole("button", {name: "更新图纸集"}).click();
    await expect(page.locator(".error-summary")).toContainText("草稿保存失败");
  }
  if (state === "add-field") {
    await page.getByRole("button", {name: "展开属性字段定义"}).click();
    await page.getByRole("button", {name: "新增字段"}).click();
    await expect(page.locator(".definition-panel .add-form")).toBeVisible();
  }
  if (state === "csv") {
    await page.getByRole("button", {name: "导入 CSV"}).click();
    await expect(page.locator(".csv-panel .csv-flow")).toBeVisible();
  }
}

// 200% 缩放：CSS zoom 让布局视口折半（1024 → 512），等比放大全部已渲染内容
async function setZoom(page: Page, factor: number) {
  await page.evaluate((value) => document.documentElement.style.setProperty("zoom", String(value)), factor);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function assertNoPageOverflow(page: Page, label: string) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth, label).toBeLessThanOrEqual(clientWidth);
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

test("独立语义卡片：细边框、浅阴影与 16px 卡片间距（可见间距无叠加）", async ({page}) => {
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
  // 纵向主轴间距读 row-gap；相邻卡片可见间距也必须是 16px（不允许旧 margin-bottom 叠加成 32px）
  const rowGap = await page.locator(".properties-view").evaluate((el) => parseFloat(getComputedStyle(el).rowGap));
  expect(rowGap).toBe(16);
  const [definitions, csv] = await Promise.all([
    page.locator(".definition-panel").boundingBox(),
    page.locator(".csv-panel").boundingBox(),
  ]);
  expect(Math.round(csv!.y - (definitions!.y + definitions!.height)), "定义卡与 CSV 卡可见间距").toBe(16);
});

test("属性值两列节奏按断点降为一列（与 Demo 900px 断点对齐）", async ({page}) => {
  await installPropertiesFixture(page);
  await openProperties(page);
  const grid = page.locator(".value-panel .value-grid");
  const columns = () => grid.evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
  expect(await columns(), "1440×900 两列").toBe(2);
  await page.setViewportSize({width: 900, height: 768});
  expect(await columns(), "900×768 降一列").toBe(1);
  await page.setViewportSize({width: 1024, height: 768});
  expect(await columns(), "1024×768 恢复两列").toBe(2);
});

test("四视口双主题无整页横向溢出", async ({page}) => {
  for (const [width, height] of VIEWPORTS) {
    await page.setViewportSize({width, height});
    for (const theme of THEMES) {
      await openFullWorkspace(page, theme);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await assertNoPageOverflow(page, `${width}x${height} ${theme}`);
    }
  }
});

test("四视口双主题覆盖 dirty+pending、错误、新增、CSV 状态无整页横向溢出", async ({page}) => {
  for (const [width, height] of VIEWPORTS) {
    await page.setViewportSize({width, height});
    for (const theme of THEMES) {
      for (const state of ["dirty-pending", "error", "add-field", "csv"] as const) {
        await openState(page, state, theme);
        await assertNoPageOverflow(page, `${width}x${height} ${theme} ${state}`);
      }
    }
  }
});

test("200% 缩放覆盖五状态：属性页区域无横向溢出且值网格降一列", async ({page}) => {
  // 说明：200% 缩放（CSS zoom 模拟）下整页级横向溢出来自共享外壳（topbar/dock 内容不随缩放压缩），
  // 图纸页现状相同（PLAN-DM-016 design-qa 有意裁决记录）；本断言限定属性页区域自身不溢出。
  await page.setViewportSize({width: 1024, height: 768});
  for (const state of STATES) {
    await openState(page, state);
    await setZoom(page, 2);
    const result = await page.evaluate(() => {
      const view = document.querySelector<HTMLElement>(".properties-view");
      const main = document.querySelector<HTMLElement>(".shell-main");
      return {
        viewOverflow: view ? view.scrollWidth - view.clientWidth : -1,
        viewRight: view ? view.getBoundingClientRect().right : 0,
        mainRight: main ? main.getBoundingClientRect().right : 0,
        columns: view ? getComputedStyle(view.querySelector<HTMLElement>(".value-grid")!).gridTemplateColumns.split(" ").length : 0,
      };
    });
    expect(result.viewOverflow, `200% 缩放 ${state} 属性页无横向溢出`).toBeLessThanOrEqual(0);
    expect(result.viewRight, `200% 缩放 ${state} 属性页不越出主滚动区`).toBeLessThanOrEqual(result.mainRight + 1);
    expect(result.columns, `200% 缩放 ${state} 值网格降一列`).toBe(1);
  }
});

test("单一主纵向滚动区：页面不滚动，仅 shell-main 纵向滚动（覆盖五状态）", async ({page}) => {
  await page.setViewportSize({width: 1024, height: 768});
  for (const state of STATES) {
    await openState(page, state);
    const result = await page.evaluate(() => {
      const root = document.documentElement;
      const main = document.querySelector<HTMLElement>(".shell-main");
      const mainScrollable = main ? main.scrollHeight > main.clientHeight + 1 : false;
      // 除 shell-main 外不应有其他纵向滚动容器（属性面板只允许横向滚动窗口）
      const others = Array.from(document.querySelectorAll<HTMLElement>(".properties-view, .properties-view *"))
        .filter((el) => el.scrollHeight > el.clientHeight + 1);
      return {pageScrollable: root.scrollHeight > root.clientHeight + 1, mainScrollable, otherCount: others.length};
    });
    expect(result.pageScrollable, `${state} 页面不滚动`).toBe(false);
    expect(result.mainScrollable, `${state} shell-main 纵向滚动`).toBe(true);
    expect(result.otherCount, `${state} 无其他纵向滚动容器`).toBe(0);
  }
});

test("定义表横向溢出时操作列冻结在容器右缘且表头同步冻结，无溢出时恢复普通列", async ({page}) => {
  await installPropertiesFixture(page);
  await openProperties(page);
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  const tableWindow = page.locator(".definition-panel .table-window");
  const actionsCell = page.locator(".definition-panel td.col-actions").first();
  // 1440：列宽之和 748px 小于容器宽度 → 普通列、无冻结阴影
  await expect(tableWindow).not.toHaveClass(/sticky-actions/);
  expect(await actionsCell.evaluate((el) => getComputedStyle(el).position)).toBe("static");
  expect(await actionsCell.evaluate((el) => getComputedStyle(el).boxShadow)).toBe("none");
  // 640：容器宽度小于表格最小宽度 748px → 操作列冻结、补不透明语义背景与分隔阴影
  await page.setViewportSize({width: 640, height: 768});
  await expect(tableWindow).toHaveClass(/sticky-actions/);
  const sticky = await actionsCell.evaluate((el) => {
    const computed = getComputedStyle(el);
    return {position: computed.position, shadow: computed.boxShadow};
  });
  expect(sticky.position).toBe("sticky");
  expect(sticky.shadow).not.toBe("none");
  // 操作列停在容器右缘（列右缘与表格窗口右缘对齐）
  const [cell, win] = await Promise.all([actionsCell.boundingBox(), tableWindow.boundingBox()]);
  expect(Math.abs(cell!.x + cell!.width - (win!.x + win!.width)), "操作列停在容器右缘").toBeLessThanOrEqual(2);
  // 表头同步冻结：操作列表头使用不透明语义背景，行滚动时不透底
  const head = await page.locator(".definition-panel th.col-actions").evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(head).not.toBe("rgba(0, 0, 0, 0)");
});
