// PLAN-DM-016 任务 7：属性页视觉基线（令牌来源、密度、同行对齐）与同状态证据采集。
// 断言（浅/深主题）：卡片表面、弱化表头、语义边框、焦点环、禁用态、错误与状态徽标色
// 全部解析自已定义 CSS 变量（与 :root / html[data-theme=dark] 解析值逐一比对）；
// 输入/选择器 38px、按钮 ≥36px 普通档、图标按钮 ≥36×36（属性页当前无图标按钮，若引入必须满足下限）、
// 同行控件垂直居中对齐。状态截图仅作为 testInfo 附件（同状态 Demo 对比图由验收时人工采集比对），
// 只使用 properties.ts 虚构夹具，不读取用户截图、真实工程或 sample/。
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {installPropertiesFixture, openProperties, pendingDraft} from "./fixtures/properties";

const THEMES = ["light", "dark"] as const;

async function openWorkspace(page: Page, theme?: "light" | "dark") {
  await installPropertiesFixture(page, {theme});
  await openProperties(page);
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  await page.getByRole("button", {name: "导入 / 导出"}).click();
}

// 解析 CSS 变量在当前主题下的实际颜色值（经探针元素取 computed color）
async function tokenColor(page: Page, token: string): Promise<string> {
  return page.evaluate((name) => {
    const probe = document.createElement("span");
    probe.style.color = `var(${name})`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  }, token);
}

// 断言元素计算样式等于指定令牌的解析值（不只靠截图目测）
async function expectToken(page: Page, selector: string, property: string, token: string) {
  const expected = await tokenColor(page, token);
  const actual = await page.locator(selector).first().evaluate((el, prop) => getComputedStyle(el)[prop as "color"], property);
  expect(actual, `${selector} ${property} 应来自 ${token}`).toBe(expected);
}

async function attachScreenshot(page: Page, info: TestInfo, state: string, theme: string) {
  const viewport = page.viewportSize()!;
  const name = `${state}-${viewport.width}x${viewport.height}-${theme}.png`;
  const path = info.outputPath(name);
  await page.screenshot({path, animations: "disabled"});
  await info.attach(name, {path, contentType: "image/png"});
}

for (const theme of THEMES) {
  test(`表面、弱化表头、语义边框与文字层级色来自已定义 CSS 变量：${theme}`, async ({page}) => {
    await openWorkspace(page, theme);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expectToken(page, ".value-panel", "backgroundColor", "--color-bg-surface");
    await expectToken(page, ".definition-panel", "backgroundColor", "--color-bg-surface");
    await expectToken(page, ".csv-panel", "backgroundColor", "--color-bg-surface");
    await expectToken(page, ".value-panel", "borderTopColor", "--color-border-subtle");
    await expectToken(page, ".definition-panel", "borderTopColor", "--color-border-subtle");
    await expectToken(page, ".definition-panel thead th", "backgroundColor", "--color-bg-muted");
    await expectToken(page, ".definition-panel thead th", "color", "--color-text-secondary");
    await expectToken(page, ".csv-panel .head-status", "color", "--color-text-muted");
    await expectToken(page, ".value-panel .panel-head", "borderBottomColor", "--color-border-subtle");
  });

  test(`焦点环来自焦点令牌、禁用态统一降级：${theme}`, async ({page}) => {
    await openWorkspace(page, theme);
    // 先用键盘建立键盘焦点上下文，再聚焦主按钮，使 :focus-visible 生效
    await page.keyboard.press("Tab");
    const focus = await page.locator(".definition-panel .link-actions button.primary").evaluate((el) => {
      el.focus();
      const computed = getComputedStyle(el);
      return {visible: el.matches(":focus-visible"), color: computed.outlineColor, width: computed.outlineWidth, style: computed.outlineStyle};
    });
    expect(focus.visible, "键盘聚焦命中 :focus-visible").toBe(true);
    expect(focus.style).toBe("solid");
    expect(focus.width).toBe("2px");
    expect(focus.color, "焦点环颜色 = --color-focus").toBe(await tokenColor(page, "--color-focus"));
    // 禁用分页按钮：统一不透明降级、不可点击（禁用不依赖颜色重绘）
    const disabled = await page.locator(".definition-panel .pager button").first().evaluate((el) => {
      const computed = getComputedStyle(el);
      return {isDisabled: (el as HTMLButtonElement).disabled, opacity: computed.opacity, cursor: computed.cursor};
    });
    expect(disabled.isDisabled).toBe(true);
    expect(disabled.opacity).toBe("0.5");
    expect(disabled.cursor).toBe("not-allowed");
  });

  test(`状态徽标与错误色来自已定义 CSS 变量：${theme}`, async ({page}) => {
    await installPropertiesFixture(page, {
      theme,
      initialDraft: pendingDraft(),
      failDraftSave: () => ({code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {项目编号: "演示校验错误"}}),
    });
    await openProperties(page);
    await page.getByRole("textbox", {name: "属性 设计阶段"}).fill("初步设计");
    await page.getByRole("button", {name: "更新图纸集"}).click();
    await expect(page.locator(".error-summary")).toContainText("草稿保存失败");
    await expect(page.locator(".value-panel .flag.pending").first()).toBeVisible();
    await expect(page.locator(".value-panel .flag.dirty").first()).toBeVisible();
    await expect(page.locator(".value-panel .flag.error").first()).toBeVisible();
    await expectToken(page, ".value-panel .flag.dirty", "color", "--color-warning");
    await expectToken(page, ".value-panel .flag.dirty", "backgroundColor", "--color-warning-bg");
    await expectToken(page, ".value-panel .flag.pending", "color", "--color-info");
    await expectToken(page, ".value-panel .flag.pending", "backgroundColor", "--color-info-bg");
    await expectToken(page, ".value-panel .flag.error", "color", "--color-danger");
    await expectToken(page, ".value-panel .flag.error", "backgroundColor", "--color-danger-bg");
    await expectToken(page, ".value-panel .field-error", "color", "--color-danger");
    await expectToken(page, ".value-panel .value-item.invalid input", "borderTopColor", "--color-danger");
    await expectToken(page, ".value-panel .value-item.invalid", "backgroundColor", "--color-danger-bg");
    await expectToken(page, ".error-summary", "borderTopColor", "--color-danger");
    await expectToken(page, ".error-summary", "backgroundColor", "--color-danger-bg");
  });

  test(`密度与同行对齐基线（38px 输入 / ≥36px 按钮 / 图标按钮 ≥36×36）：${theme}`, async ({page}) => {
    await installPropertiesFixture(page, {theme});
    await openProperties(page);
    await page.getByRole("button", {name: "展开属性字段定义"}).click();
    await page.getByRole("button", {name: "新增字段"}).click();
    await page.getByRole("button", {name: "导入 / 导出"}).click();
    // 文本输入与选择器统一 38px（checkbox/file 不在密度档内）
    const inputHeights = await page.locator(
      ".properties-view input[type=\"text\"], .properties-view input[type=\"search\"], .properties-view select",
    ).evaluateAll((elements) => elements.map((el) => el.getBoundingClientRect().height));
    expect(inputHeights.length).toBeGreaterThanOrEqual(10);
    for (const height of inputHeights) expect(height).toBe(38);
    // 普通按钮档 ≥36px；图标按钮（无文字内容的按钮）额外要求 ≥36×36（属性页当前无图标按钮）
    const buttons = await page.locator(".properties-view button:visible").evaluateAll((elements) => elements.map((el) => {
      const rect = el.getBoundingClientRect();
      return {height: rect.height, width: rect.width, iconOnly: el.textContent?.trim() === ""};
    }));
    expect(buttons.length).toBeGreaterThanOrEqual(10);
    for (const button of buttons) {
      expect(button.height).toBeGreaterThanOrEqual(36);
      if (button.iconOnly) {
        expect(button.width, "图标按钮宽 ≥36").toBeGreaterThanOrEqual(36);
        expect(button.height, "图标按钮高 ≥36").toBeGreaterThanOrEqual(36);
      }
    }
    // 同行控件垂直居中对齐：值面板搜索行与定义面板查询行的输入/选择器/按钮中点一致（±1px）
    for (const rowSelector of [".value-panel .value-toolbar", ".definition-panel .query-bar"]) {
      const centers = await page.locator(`${rowSelector} > *`).evaluateAll((elements) => elements
        .filter((el) => /^(INPUT|SELECT|BUTTON)$/.test(el.tagName))
        .map((el) => {
          const rect = el.getBoundingClientRect();
          return rect.top + rect.height / 2;
        }));
      expect(centers.length, `${rowSelector} 存在同行控件`).toBeGreaterThanOrEqual(2);
      for (const center of centers) expect(Math.abs(center - centers[0]), `${rowSelector} 同行垂直对齐`).toBeLessThanOrEqual(1);
    }
  });
}

for (const theme of THEMES) {
  test(`1440 双主题五状态同状态证据：${theme}`, async ({page}, info) => {
    await page.setViewportSize({width: 1440, height: 900});
    for (const state of ["default", "dirty-pending", "error", "add-field", "csv"] as const) {
      if (state === "default") {
        await openWorkspace(page, theme);
      } else if (state === "dirty-pending") {
        await installPropertiesFixture(page, {theme, initialDraft: pendingDraft()});
        await openProperties(page);
        await page.getByRole("textbox", {name: "属性 设计阶段"}).fill("初步设计");
      } else if (state === "error") {
        await installPropertiesFixture(page, {
          theme,
          initialDraft: pendingDraft(),
          failDraftSave: () => ({code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {项目编号: "演示校验错误"}}),
        });
        await openProperties(page);
        await page.getByRole("textbox", {name: "属性 设计阶段"}).fill("初步设计");
        await page.getByRole("button", {name: "更新图纸集"}).click();
        await expect(page.locator(".error-summary")).toContainText("草稿保存失败");
      } else if (state === "add-field") {
        await openWorkspace(page, theme);
        await page.getByRole("button", {name: "新增字段"}).click();
        await expect(page.locator(".definition-panel .add-form")).toBeVisible();
      } else {
        await openWorkspace(page, theme);
        await page.getByRole("button", {name: "导入 CSV"}).click();
        await expect(page.locator(".csv-panel .csv-flow")).toBeVisible();
      }
      await page.mouse.move(0, 0);
      await attachScreenshot(page, info, state, theme);
    }
  });

  test(`窄屏单列同状态证据：${theme}`, async ({page}, info) => {
    await page.setViewportSize({width: 900, height: 768});
    await openWorkspace(page, theme);
    const columns = await page.locator(".value-panel .value-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
    expect(columns, "900×768 属性值单列").toBe(1);
    await page.mouse.move(0, 0);
    await attachScreenshot(page, info, "narrow-single-column", theme);
  });

  test(`定义表横向溢出同状态证据（200% 缩放）：${theme}`, async ({page}, info) => {
    await page.setViewportSize({width: 1024, height: 768});
    await openWorkspace(page, theme);
    await page.evaluate(() => document.documentElement.style.setProperty("zoom", "2"));
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator(".definition-panel .table-window")).toHaveClass(/sticky-actions/);
    await page.locator(".definition-panel .table-window").scrollIntoViewIfNeeded();
    await page.mouse.move(0, 0);
    await attachScreenshot(page, info, "def-table-overflow", theme);
  });
}
