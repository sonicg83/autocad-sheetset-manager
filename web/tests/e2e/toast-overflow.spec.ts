// PLAN-DM-048 审查回归：从真实「关于」外链反馈累积通知，不直接注入 Toast 状态。
import {expect, test, type Page} from "@playwright/test";
import {installPreferenceSnapshot, openSettingsDialog} from "./fixtures/settings";

async function openAbout(page: Page, failures: number, theme: "light" | "dark") {
  await installPreferenceSnapshot(page, theme);
  await page.addInitScript(failureCount => {
    let calls = 0;
    // 只替换外部壳桥边界，Toast 的入列、计时、渲染与关闭均走生产代码。
    (window as unknown as {pywebview: unknown}).pywebview = {api: {
      open_external: async () => ++calls <= failureCount
        ? {ok: false, code: "SHELL_EXTERNAL_URL_REJECTED", message: "链接被拒绝"}
        : {ok: true, value: null},
    }};
  }, failures);
  await page.goto("/");
  await openSettingsDialog(page);
  await page.getByRole("tab", {name: "关于"}).click();
  await expect(page.getByRole("button", {name: "项目主页"})).toBeVisible();
}

test("四条失败通知之后的新成功通知仍可见", async ({page}) => {
  await openAbout(page, 4, "light");
  for (let index = 0; index < 5; index += 1) {
    await page.getByRole("button", {name: "项目主页"}).click();
  }
  await page.getByRole("button", {name: "关闭设置", exact: true}).click();

  await expect(page.locator(".toast.fail")).toHaveCount(4);
  await expect(page.locator(".toast.ok")).toContainText("已在系统浏览器打开");
  await expect(page.locator(".toast.ok")).toBeInViewport();
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [1024, 900]) {
    test(`${theme} ${width}×768 多条失败通知可滚动并逐项关闭`, async ({page}) => {
      await page.setViewportSize({width, height: 768});
      await openAbout(page, 12, theme);
      for (let index = 0; index < 12; index += 1) {
        await page.getByRole("button", {name: "项目主页"}).click();
      }
      await page.getByRole("button", {name: "关闭设置", exact: true}).click();
      const host = page.locator(".toast-host");
      await expect(host.locator(".toast.fail")).toHaveCount(12);
      const geometry = await host.evaluate(element => {
        const box = element.getBoundingClientRect();
        return {top: box.top, bottom: box.bottom, right: box.right,
          viewportWidth: innerWidth, viewportHeight: innerHeight,
          clientHeight: element.clientHeight, scrollHeight: element.scrollHeight,
          overflowY: getComputedStyle(element).overflowY};
      });
      expect(geometry.top).toBeGreaterThanOrEqual(0);
      expect(geometry.bottom).toBeLessThanOrEqual(geometry.viewportHeight);
      expect(geometry.right).toBeLessThanOrEqual(geometry.viewportWidth);
      expect(geometry.scrollHeight).toBeGreaterThan(geometry.clientHeight);
      expect(geometry.overflowY).toBe("auto");
      // 新反馈不藏在列表外；按键聚焦较早的关闭按钮应滚动到对应条目。
      const closeButtons = host.getByRole("button", {name: "忽略通知"});
      await expect(closeButtons.last()).toBeInViewport();
      await closeButtons.first().focus();
      await expect(closeButtons.first()).toBeInViewport();
      await page.keyboard.press("Enter");
      await expect(host.locator(".toast.fail")).toHaveCount(11);
      await closeButtons.last().click();
      await expect(host.locator(".toast.fail")).toHaveCount(10);
    });
  }
}
