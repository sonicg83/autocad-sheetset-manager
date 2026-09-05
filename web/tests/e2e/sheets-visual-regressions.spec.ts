// PLAN-DM-015 实施评审整改：验证用户实际可见结果，而不是只验证 DOM/tooltip 存在。
import {expect, test, type Page} from "@playwright/test";
import {readFileSync} from "node:fs";
import {installSheetsFixture} from "./fixtures/sheets";

test("图纸组件源码不引用未声明的颜色别名", () => {
  for (const path of ["src/style.css", "src/components/sheets/SheetTree.vue", "src/components/SheetTable.vue", "src/components/sheets/SheetOperationForm.vue", "src/components/sheets/SheetToolbar.vue", "src/components/sheets/ColumnSettings.vue", "src/components/sheets/SheetPropertyEditor.vue", "src/views/SheetsView.vue"]) {
    expect(readFileSync(path, "utf8")).not.toMatch(/var\(\s*--color-(?:bg-surface-2|border|accent-soft|bg-hover|warning-soft|danger-soft)\s*[,)]/);
  }
});

for (const theme of ["light", "dark"] as const) {
  test(`${theme} 主题下工具栏、属性和恢复按钮保持点击留白`, async ({page}) => {
    await installSheetsFixture(page, {initialDraft: {
      schema_version: 1, workspace_id: "workspace-1", base_revision_id: "revision-1",
      repair_status: "VALID", version: 1, cursor: 1,
      actions: [{id: "visual-action", kind: "command_batch", label: "修改标题", commands: [{type: "update_subset_title", subset_id: "subset-1", title: "修订标题"}]}],
    }});
    await openWorkspace(page);
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    for (const selector of [".sheets-toolbar .operations button", ".recover-banner button", ".properties-view button", ".property-panel .link-actions a"]) {
      if (selector.startsWith(".properties")) await page.getByRole("tab", {name: "属性"}).click();
      const controls = page.locator(`${selector}:visible`);
      expect(await controls.count()).toBeGreaterThan(0);
      for (const control of await controls.all()) {
        const style = await control.evaluate(el => {
          const css = getComputedStyle(el);
          return {height: el.getBoundingClientRect().height, padding: parseFloat(css.paddingLeft), border: parseFloat(css.borderTopWidth), background: css.backgroundColor};
        });
        expect.soft(style.height).toBeGreaterThanOrEqual(selector.includes(".operations") ? 34 : 36);
        expect.soft(style.padding).toBeGreaterThanOrEqual(8);
        expect.soft(style.border).toBeGreaterThan(0);
        expect.soft(style.background).not.toBe("rgba(0, 0, 0, 0)");
      }
    }
  });
  test(`${theme} 主题下表单、表格和导航使用可辨识的令牌样式`, async ({page}) => {
    await page.setViewportSize({width: 1440, height: 900});
    await installSheetsFixture(page);
    await openWorkspace(page);
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    await page.getByRole("button", {name: "编辑子集", exact: true}).click();
    const form = page.getByRole("region", {name: "编辑子集", exact: true});
    const input = form.getByLabel("子集标题", {exact: true});
    const styles = await input.evaluate(el => {
      const style = getComputedStyle(el);
      return {height: el.getBoundingClientRect().height, border: style.borderTopColor, width: style.borderTopWidth, radius: style.borderTopLeftRadius};
    });
    expect.soft(styles.height).toBeGreaterThanOrEqual(36);
    expect.soft(styles.height).toBeLessThanOrEqual(40);
    expect.soft(styles.border).not.toBe("rgba(0, 0, 0, 0)");
    expect.soft(parseFloat(styles.width)).toBeGreaterThan(0);
    expect.soft(parseFloat(styles.radius)).toBeGreaterThanOrEqual(6);
    const header = page.locator(".sheet-table-window th.col-title");
    const body = page.locator(".sheet-table-window tbody td.col-title").first();
    const headerStyle = await header.evaluate(el => ({background: getComputedStyle(el).backgroundColor, border: getComputedStyle(el).borderBottomColor}));
    expect.soft(headerStyle.background).not.toBe(await body.evaluate(el => getComputedStyle(el).backgroundColor));
    expect.soft(headerStyle.background).not.toBe("rgba(0, 0, 0, 0)");
    expect.soft(headerStyle.border).not.toBe("rgba(0, 0, 0, 0)");
    const separator = page.getByRole("separator", {name: "调整图纸导航栏宽度"});
    expect.soft(await separator.evaluate(el => parseFloat(getComputedStyle(el).borderLeftWidth))).toBeGreaterThan(0);
    expect.soft(await separator.evaluate(el => getComputedStyle(el).borderLeftColor)).not.toBe("rgba(0, 0, 0, 0)");
    const activeNode = page.locator('.sheet-tree [role="treeitem"].active');
    expect.soft(await activeNode.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
    const forbidden = ["--color-bg-surface-2", "--color-border", "--color-accent-soft", "--color-bg-hover", "--color-warning-soft", "--color-danger-soft"];
    for (const node of [form, header, body, separator, activeNode]) {
      expect(await node.evaluate((el, names) => names.map(name => getComputedStyle(el).getPropertyValue(name).trim()), forbidden)).toEqual(forbidden.map(() => ""));
    }
  });
}

async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("table", {name: "图纸表格"})).toBeVisible();
}

for (const theme of ["light", "dark"] as const) {
  test(`${theme} 交互状态：树范围、图纸定位和表格鼠标键盘反馈`, async ({page}) => {
    await page.setViewportSize({width: 1920, height: 1080});
    await installSheetsFixture(page);
    await openWorkspace(page);
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    const token = async (name: string) => page.evaluate(name => {
      const probe = document.createElement("span");
      probe.style.color = `var(${name})`;
      document.body.append(probe);
      const color = getComputedStyle(probe).color;
      probe.remove();
      return color;
    }, name);
    const muted = await token("--color-bg-muted");
    const soft = await token("--color-info-bg");
    const subset = page.getByRole("treeitem", {name: /建筑施工图/});
    const defaultTree = await subset.evaluate(el => getComputedStyle(el).backgroundColor);
    await subset.hover();
    expect.soft(await subset.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(defaultTree);
    await expect.soft(subset).toHaveCSS("background-color", muted);
    await subset.click();
    await expect.soft(subset).toHaveCSS("background-color", await token("--color-accent"));
    for (const part of [subset, subset.locator(".node-count"), subset.locator(".chevron")]) {
      await expect.soft(part).toHaveCSS("color", await token("--color-on-accent"));
    }
    const row = page.locator('[data-sheet-id="sheet-1"]');
    const cells = row.locator("td");
    const defaultRow = await cells.first().evaluate(el => getComputedStyle(el).backgroundColor);
    await row.locator(".col-title").hover();
    expect.soft(await cells.first().evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(defaultRow);
    for (const cell of await cells.all()) await expect.soft(cell).toHaveCSS("background-color", muted);
    // 键盘进入表格后，焦点轮廓和整行反馈均保留。
    await page.mouse.move(0, 0);
    await page.getByLabel("过滤后的图纸表格").focus();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("全选当前结果")).toBeFocused();
    await page.keyboard.press("Tab");
    const checkbox = row.getByRole("checkbox");
    await expect(checkbox).toBeFocused();
    expect.soft(await checkbox.evaluate(el => parseFloat(getComputedStyle(el).outlineWidth))).toBeGreaterThan(0);
    for (const cell of await cells.all()) await expect.soft(cell).toHaveCSS("background-color", muted);
    const sheet = page.getByRole("treeitem", {name: "001 图纸 1", exact: true});
    await sheet.click();
    await expect.soft(sheet).toHaveCSS("background-color", soft);
    await expect.soft(sheet).toHaveCSS("color", await token("--color-accent"));
    for (const cell of await cells.all()) await expect.soft(cell).toHaveCSS("background-color", soft);
    await checkbox.check();
    await expect.soft(row).toHaveClass(/selected/);
    await expect.soft(row).toHaveClass(/focused/);
    await page.getByRole("treeitem", {name: "002 图纸 2", exact: true}).click();
    await expect.soft(row).not.toHaveClass(/focused/);
    await expect.soft(row).toHaveClass(/selected/);
    for (const cell of await cells.all()) await expect.soft(cell).toHaveCSS("background-color", soft);
    await sheet.click();
    await checkbox.uncheck();
    await expect.soft(row).not.toHaveClass(/selected/);
    await expect.soft(row).toHaveClass(/focused/);
    await sheet.focus();
    await page.keyboard.press("ArrowUp");
    await expect(subset).toBeFocused();
    expect.soft(await subset.evaluate(el => parseFloat(getComputedStyle(el).outlineWidth))).toBeGreaterThan(0);
    const ring = await subset.evaluate(el => {
      const css = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      const tree = el.parentElement!.getBoundingClientRect();
      let backdrop: Element | null = el.parentElement;
      while (backdrop && getComputedStyle(backdrop).backgroundColor === "rgba(0, 0, 0, 0)") backdrop = backdrop.parentElement;
      const extent = parseFloat(css.outlineOffset) + parseFloat(css.outlineWidth);
      const previous = el.previousElementSibling!.getBoundingClientRect();
      const next = el.nextElementSibling!.getBoundingClientRect();
      return {
        visible: el.matches(":focus-visible"), offset: parseFloat(css.outlineOffset),
        color: css.outlineColor, backdrop: backdrop ? getComputedStyle(backdrop).backgroundColor : "",
        inside: box.left - extent >= tree.left && box.right + extent <= tree.right && box.top - extent >= tree.top && box.bottom + extent <= tree.bottom,
        clearOfNeighbors: previous.bottom <= box.top - extent && next.top >= box.bottom + extent,
      };
    });
    expect.soft(ring.visible).toBe(true);
    expect.soft(ring.offset).toBe(2);
    expect.soft(ring.color).not.toBe(ring.backdrop);
    expect.soft(ring.inside).toBe(true);
    expect.soft(ring.clearOfNeighbors).toBe(true);
  });
}

for (const theme of ["light", "dark"] as const) {
  for (const operation of ["编辑子集", "新增图纸", "新建子集"]) {
    test(`${theme} ${operation} 操作表单控件尺寸、列数和动作层级`, async ({page}) => {
      await page.setViewportSize({width: 1440, height: 900});
      await installSheetsFixture(page);
      await openWorkspace(page);
      await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
      await page.getByRole("button", {name: operation, exact: true}).click();
      const form = page.getByRole("region", {name: operation, exact: true});
      await expect(form).toBeVisible();
      const token = async (name: string) => page.evaluate(name => {
        const probe = document.createElement("span");
        probe.style.color = `var(${name})`;
        document.body.append(probe);
        const color = getComputedStyle(probe).color;
        probe.remove();
        return color;
      }, name);
      const heading = await form.locator(".form-head").evaluate(el => ({color: getComputedStyle(el.querySelector("h3")!).color, minHeight: getComputedStyle(el).minHeight, padding: getComputedStyle(el).padding}));
      expect.soft(heading).toEqual({color: await token("--color-text-primary"), minHeight: "0px", padding: "0px"});
      await page.getByRole("button", {name: "筛选", exact: true}).click();
      const controls = page.locator('.operation-form input:visible, .operation-form select:visible, .sheets-toolbar input:not([type="checkbox"]):visible, .sheets-toolbar select:visible');
      const radii = [];
      for (const control of await controls.all()) {
        const css = await control.evaluate(el => ({height: el.getBoundingClientRect().height, radius: getComputedStyle(el).borderRadius}));
        expect.soft(css.height).toBeGreaterThanOrEqual(36);
        expect.soft(css.height).toBeLessThanOrEqual(40);
        radii.push(css.radius);
      }
      expect.soft(new Set(radii).size).toBe(1);
      const positions = await form.locator(".form-field").evaluateAll(els => els.map(el => Math.round(el.getBoundingClientRect().top)));
      expect.soft(Math.max(...positions.map(top => positions.filter(value => value === top).length))).toBeLessThanOrEqual(2);
      const primary = form.getByRole("button", {name: "加入草稿", exact: true});
      const primaryStyle = await primary.evaluate(el => ({primary: el.classList.contains("primary"), background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color}));
      expect.soft(primaryStyle).toEqual({primary: true, background: await token("--color-accent"), color: await token("--color-on-accent")});
      expect.soft(await form.getByRole("button", {name: "取消", exact: true}).evaluate(el => getComputedStyle(el).backgroundColor)).toBe(await token("--color-bg-surface"));
      if (operation === "编辑子集") {
        const danger = await form.locator(".form-danger").boundingBox();
        const footer = await form.locator(".form-footer").boundingBox();
        expect(danger!.y + danger!.height).toBeLessThanOrEqual(footer!.y);
      }
      const first = form.locator("input, select").first();
      await first.focus();
      await expect(first).toHaveCSS("outline-width", "2px");
      await expect(first).toHaveCSS("outline-color", await token("--color-focus"));
      await page.setViewportSize({width: 900, height: 768});
      const lefts = await form.locator(".form-field").evaluateAll(els => els.map(el => Math.round(el.getBoundingClientRect().left)));
      expect(new Set(lefts).size).toBe(1);
    });
  }
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

  const file = page.locator(".sheet-table-window tbody tr").first().locator(".col-file .multiline-text");
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
