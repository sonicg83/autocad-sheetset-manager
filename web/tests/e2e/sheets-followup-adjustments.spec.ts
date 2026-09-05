import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";

async function openWorkspace(page: Page, options: Parameters<typeof installSheetsFixture>[1] = {}) {
  await installSheetsFixture(page, options);
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("table", {name: "图纸表格"})).toBeVisible();
}

test("表头复选框控制当前筛选结果并呈现半选态", async ({page}) => {
  await openWorkspace(page);
  await expect(page.getByRole("button", {name: /全选当前结果/})).toHaveCount(0);
  await expect(page.getByRole("columnheader", {name: "选择"})).toHaveCount(0);
  const selectAll = page.getByRole("checkbox", {name: "全选当前结果"});
  await expect(selectAll).not.toBeChecked();
  await page.getByLabel("选择图纸 001").check();
  await expect(selectAll).toHaveJSProperty("indeterminate", true);
  await selectAll.check();
  await expect(page.getByText("已选 13 张", {exact: false})).toBeVisible();
  await selectAll.uncheck();
  await expect(page.locator(".selection-bar")).toHaveCount(0);
});

test("工具栏与选择栏按钮使用统一紧凑高度且批量控件独占下一行", async ({page}) => {
  await openWorkspace(page);
  const buttons = ["筛选", "显示列", "编辑子集", "新增图纸", "新建子集"];
  const heights: number[] = [];
  for (const name of buttons) {
    const box = await page.getByRole("button", {name, exact: true}).boundingBox();
    heights.push(box!.height);
  }
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
  expect(Math.max(...heights)).toBeLessThanOrEqual(34);

  await page.getByRole("checkbox", {name: "全选当前结果"}).check();
  await page.getByRole("button", {name: "批量修改属性"}).click();
  const actions = page.locator(".selection-actions");
  const controls = page.locator(".bulk-controls");
  const [actionBox, controlsBox] = await Promise.all([actions.boundingBox(), controls.boundingBox()]);
  expect(controlsBox!.y).toBeGreaterThanOrEqual(actionBox!.y + actionBox!.height - 1);
  for (const name of ["清除选择", "批量修改属性", "批量加入草稿"]) {
    const box = await page.getByRole("button", {name, exact: true}).boundingBox();
    expect(box!.height).toBeLessThanOrEqual(34);
  }
});

test("批量加入草稿后保留选择和批量状态并重置输入直到用户取消", async ({page}) => {
  await openWorkspace(page);
  await page.getByRole("checkbox", {name: "全选当前结果"}).check();
  await page.getByRole("button", {name: "批量修改属性"}).click();
  await page.getByLabel("既有图纸属性").selectOption("比例");
  await page.getByLabel("批量值").fill("1:200");
  await page.getByRole("button", {name: "批量加入草稿"}).click();
  await expect(page.getByText("已选 13 张", {exact: false})).toBeVisible();
  await expect(page.getByLabel("既有图纸属性")).toHaveValue("");
  await expect(page.getByLabel("批量值")).toHaveValue("");
  await expect(page.locator(".bulk-controls")).toBeVisible();
  await page.getByRole("button", {name: "清除选择"}).click();
  await expect(page.locator(".bulk-controls")).toHaveCount(0);
});

test("单张属性编辑器插入目标图纸行下方并在桌面显示三列", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await openWorkspace(page);
  const row = page.locator('tr[data-sheet-id="sheet-1"]');
  await row.getByRole("button", {name: "编辑属性"}).click();
  const editorRow = page.locator("tr.sheet-editor-row");
  await expect(editorRow).toHaveCount(1);
  expect(await row.evaluate((el) => el.nextElementSibling?.classList.contains("sheet-editor-row"))).toBe(true);
  await expect(editorRow.getByRole("region", {name: "属性编辑 图纸 001"})).toBeVisible();
  await expect(editorRow.locator(".editor-grid")).toHaveCSS("grid-template-columns", /.+ .+ .+/);
  await expect(page.locator(".sheet-editor-card")).toHaveCount(0);
});

test("深色主题属性编辑器隔离全局顶栏样式并统一输入控件", async ({page}) => {
  await openWorkspace(page);
  await page.evaluate(() => { document.documentElement.dataset.theme = "dark"; });
  await page.getByRole("button", {name: "编辑属性"}).first().click();
  const editor = page.getByRole("region", {name: "属性编辑 图纸 001"});
  const styles = await editor.evaluate((element) => {
    const header = element.querySelector<HTMLElement>(".editor-head")!;
    const heading = header.querySelector<HTMLElement>("h3")!;
    const inputs = [...element.querySelectorAll<HTMLInputElement>("input")];
    const probe = document.createElement("span");
    probe.style.color = "var(--color-text-primary)";
    document.body.append(probe);
    const primary = getComputedStyle(probe).color;
    probe.remove();
    const headerStyle = getComputedStyle(header);
    return {
      header: {
        minHeight: headerStyle.minHeight,
        paddingTop: headerStyle.paddingTop,
        background: headerStyle.backgroundColor,
      },
      headingColor: getComputedStyle(heading).color,
      primary,
      inputs: inputs.map((input) => {
        const style = getComputedStyle(input);
        return {
          height: input.getBoundingClientRect().height,
          borderWidth: parseFloat(style.borderTopWidth),
          borderStyle: style.borderTopStyle,
          radius: parseFloat(style.borderTopLeftRadius),
        };
      }),
    };
  });
  expect(styles.header).toEqual({minHeight: "auto", paddingTop: "0px", background: "rgba(0, 0, 0, 0)"});
  expect(styles.headingColor).toBe(styles.primary);
  expect(styles.inputs.length).toBeGreaterThan(1);
  for (const input of styles.inputs) {
    expect(input.height).toBe(38);
    expect(input.borderWidth).toBe(1);
    expect(input.borderStyle).toBe("solid");
    expect(input.radius).toBeGreaterThanOrEqual(6);
  }
});

test("表格横向溢出时右侧操作列保持冻结", async ({page}) => {
  await page.setViewportSize({width: 1024, height: 768});
  await openWorkspace(page);
  const tableWindow = page.locator(".sheet-table-window");
  expect(await tableWindow.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
  await expect(tableWindow).toHaveClass(/sticky-actions/);
  await expect(page.locator("th.col-actions")).toHaveCSS("position", "sticky");
  await tableWindow.evaluate((el) => { el.scrollLeft = el.scrollWidth; });
  const [windowBox, actionsBox] = await Promise.all([
    tableWindow.boundingBox(),
    page.locator("th.col-actions").boundingBox(),
  ]);
  expect(actionsBox!.x + actionsBox!.width).toBeLessThanOrEqual(windowBox!.x + windowBox!.width + 1);
});

test("子集文件布局和自定义属性与标题一样最多显示两行", async ({page}) => {
  await openWorkspace(page, {
    longText: true,
    initialColumns: {"workspace-1": {schemaVersion: 1, file: true, layout: true, subsetAll: true, subsetSingle: false, properties: {"sheet:图幅": true, "sheet:比例": true, "sheet:专业": true}}},
  });
  const row = page.locator('tr[data-sheet-id="sheet-13"]');
  for (const selector of [".col-subset .multiline-text", ".col-file .multiline-text", ".col-layout .multiline-text", ".col-prop .multiline-text"]) {
    const cellText = row.locator(selector).first();
    await expect(cellText).toHaveCSS("-webkit-line-clamp", "2");
    await expect(cellText).toHaveCSS("white-space", "normal");
    await expect(cellText).toHaveAttribute("tabindex", "0");
  }
});
