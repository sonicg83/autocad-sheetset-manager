// 无障碍与响应式 e2e（PLAN-DB-001 Task 5）：1280×720 与最小支持视口 360×640、
// 浅/深主题令牌、200% 浏览器缩放、固定操作栏不遮挡聚焦控件、键盘主流程。
// 后端同样由 backend-mock 拦截。
import {expect, test} from "@playwright/test";
import {BackendMock} from "./helpers/backend-mock";

const MIN_VIEWPORT = {width: 360, height: 640} as const;

async function gotoStep1(page: import("@playwright/test").Page): Promise<BackendMock> {
  const mock = new BackendMock(page, {initialized: true, wizardStep: 1});
  await mock.install();
  await page.goto("/");
  await expect(page.getByTestId("wizard-shell")).toBeVisible();
  await expect(page.getByRole("heading", {name: "创建项目"})).toBeVisible();
  return mock;
}

function overflow(page: import("@playwright/test").Page) {
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

test("1280×720 无横向溢出（第 1、2 步）", async ({page}) => {
  await gotoStep1(page);
  const first = await overflow(page);
  expect(first.scrollWidth).toBeLessThanOrEqual(first.clientWidth);
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "配置规则"})).toBeVisible();
  const second = await overflow(page);
  expect(second.scrollWidth).toBeLessThanOrEqual(second.clientWidth);
});

test("最小支持视口 360×640 无横向溢出", async ({page}) => {
  await page.setViewportSize(MIN_VIEWPORT);
  await gotoStep1(page);
  const first = await overflow(page);
  expect(first.scrollWidth).toBeLessThanOrEqual(first.clientWidth);
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "配置规则"})).toBeVisible();
  const second = await overflow(page);
  expect(second.scrollWidth).toBeLessThanOrEqual(second.clientWidth);
});

test("360×640 下页面可纵向滚动（保证遮挡检查有意义）", async ({page}) => {
  await page.setViewportSize(MIN_VIEWPORT);
  await gotoStep1(page);
  const scrollable = await page.evaluate(() => document.documentElement.scrollHeight > document.documentElement.clientHeight);
  expect(scrollable).toBe(true);
});

test("浏览器 200% 缩放无横向溢出", async ({page}) => {
  await gotoStep1(page);
  await page.evaluate(() => {
    (document.documentElement.style as CSSStyleDeclaration & {zoom: string}).zoom = "2";
  });
  const {scrollWidth, clientWidth} = await overflow(page);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});

test("浅色主题使用已接受的语义令牌值", async ({page}) => {
  await gotoStep1(page);
  const canvas = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--color-bg-canvas").trim(),
  );
  expect(canvas).toBe("#F6F7F9");
});

test("深色主题令牌切换（prefers-color-scheme: dark）", async ({page}) => {
  await page.emulateMedia({colorScheme: "dark"});
  await gotoStep1(page);
  const tokens = await page.evaluate(() => ({
    canvas: getComputedStyle(document.documentElement).getPropertyValue("--color-bg-canvas").trim(),
    colorScheme: getComputedStyle(document.documentElement).colorScheme,
  }));
  expect(tokens.canvas).toBe("#10151E");
  expect(tokens.colorScheme).toBe("dark");
});

test("固定操作栏不遮挡聚焦控件（scroll-padding 兜底）", async ({page}) => {
  await page.setViewportSize(MIN_VIEWPORT);
  await gotoStep1(page);
  const output = page.getByLabel("成果目录");
  await output.focus();
  await expect(output).toBeFocused();
  const clear = await page.evaluate(() => {
    const input = document.querySelector<HTMLElement>('[data-field="project.output_path"]');
    const dock = document.querySelector<HTMLElement>('[data-testid="action-dock"]');
    if (!input || !dock) {
      return false;
    }
    const inputRect = input.getBoundingClientRect();
    const dockRect = dock.getBoundingClientRect();
    return inputRect.bottom <= dockRect.top + 1;
  });
  expect(clear).toBe(true);
});

test("键盘主流程：Tab 顺序覆盖步骤导航→字段→操作栏，Enter 推进，Space 选择 CAD 版本", async ({page}) => {
  await gotoStep1(page);
  await page.keyboard.press("Tab");
  const stops: string[] = [];
  for (let i = 0; i < 10; i += 1) {
    stops.push(
      await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        return el?.getAttribute("data-testid") ?? el?.getAttribute("data-field") ?? el?.tagName ?? "";
      }),
    );
    await page.keyboard.press("Tab");
  }
  // 可进入的步骤导航按钮在前，随后是本步字段，最后是操作栏按钮
  expect(stops.slice(0, 4)).toEqual(["rail-step-1", "rail-step-2", "rail-step-3", "rail-step-4"]);
  expect(stops.slice(4, 8)).toEqual([
    "project.name",
    "project.stage",
    "project.discipline",
    "project.output_path",
  ]);
  expect(stops[8]).toBe("dock-next");

  // Enter 激活“下一步”推进到第 2 步（焦点此时已在 dock-next）
  await page.getByTestId("dock-next").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", {name: "配置规则"})).toBeVisible();

  // Space 选择 AutoCAD 2016 单选项，示例图号即时更新
  const radio2016 = page.getByLabel("AutoCAD 2016");
  await radio2016.focus();
  await page.keyboard.press("Space");
  await expect(radio2016).toBeChecked();
  await expect(page.getByTestId("sheet-number-preview")).toHaveText("A-001");
});

test("步骤导航暴露 aria-current，完成状态可感知", async ({page}) => {
  await gotoStep1(page);
  await expect(page.getByTestId("rail-step-1")).toHaveAttribute("aria-current", "step");
  await expect(page.getByTestId("rail-step-1")).toContainText("已完成");
});
