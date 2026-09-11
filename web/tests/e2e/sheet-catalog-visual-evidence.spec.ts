// 图纸目录页响应式/可访问性证据与 G8 同状态截图（PLAN-DM-020 Task 12 / SPEC-DM-012 §7.3 视图行 + §13）。
// 布局断言只用几何/滚动语义（scrollWidth、overflow、bounding box），不做像素级比对：
// 无整页横向溢出、主操作可见、预览区独立横滚；键盘：Tab 顺序、字段浏览器
// Enter/Space 插入、状态不只靠颜色。G8 成对截图（1440×1000 浅色 / 900×700 深色）
// 使用与冻结 Demo（commit 9f3dfb3）相同的虚构数据与展开状态，截图经 testInfo
// 附件留档（g8-catalog-{主题}-{宽}x{高}.png），验收时复制到版本库
// docs/dst-manager/specs/assets/SPEC-DM-012/production/ 与冻结基准图比对。
// PLAN-DM-023 Task 1 追加：V1/V2/V3/V4/V5/V7/V8 的冻结布局硬要求（首屏密度、
// 表格式输出列、字段可见性、列数增长不撑高页面）。这些用例代替
// “滚动后可达”作为 G4 一致性证据；差异裁决权仍在用户（MEMO-DM-030）。
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {demoSixColumnTemplate, installSheetCatalogFixture, openCatalogPage, type CatalogTemplate} from "./fixtures/sheetCatalog";

async function expectNoPageHScroll(page: Page, label: string) {
  const metrics = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    win: window.innerWidth,
  }));
  expect(metrics.doc, `${label}：html 无横向溢出`).toBeLessThanOrEqual(metrics.win);
  expect(metrics.body, `${label}：body 无横向溢出`).toBeLessThanOrEqual(metrics.win);
}

async function expectActionsReachable(page: Page, names: string[]) {
  const viewport = page.viewportSize()!;
  for (const name of names) {
    const box = await page.getByRole("button", {name}).first().boundingBox();
    expect(box, `${name} 存在`).not.toBeNull();
    expect(box!.x, name).toBeGreaterThanOrEqual(0);
    expect(box!.y, name).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width, `${name} 右缘在视口内`).toBeLessThanOrEqual(viewport.width);
    expect(box!.y + box!.height, `${name} 底缘在视口内`).toBeLessThanOrEqual(viewport.height);
  }
}

// 纵向滚动后可达：仅作为“无横向裁剪”的补充守卫（SPEC §13）。
// 注意：这不能证明 G4 一致——首屏密度由 PLAN-DM-023 的专用用例断言。
async function expectActionReachableAfterScroll(page: Page, name: string) {
  const viewport = page.viewportSize()!;
  const button = page.getByRole("button", {name}).first();
  await button.scrollIntoViewIfNeeded();
  const box = await button.boundingBox();
  expect(box, `${name} 存在`).not.toBeNull();
  expect(box!.x, name).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width, `${name} 右缘在视口内（无横向裁剪）`).toBeLessThanOrEqual(viewport.width);
  expect(box!.y + box!.height, `${name} 底缘在视口内`).toBeLessThanOrEqual(viewport.height);
}

// 横向滚动只发生在预览表容器内：容器 overflow-x:auto 且确实存在溢出
async function expectPreviewScrollsInternally(page: Page, label: string) {
  const tableWindow = page.locator(".table-window");
  await expect(tableWindow).toHaveCSS("overflow-x", "auto");
  const scroll = await tableWindow.evaluate(element => ({sw: element.scrollWidth, cw: element.clientWidth}));
  expect(scroll.sw, `${label}：预览内容宽于容器（确实存在可滚动溢出）`).toBeGreaterThan(scroll.cw);
}

async function attachScreenshot(page: Page, info: TestInfo, name: string) {
  const path = info.outputPath(name);
  await page.screenshot({path, animations: "disabled"});
  await info.attach(name, {path, contentType: "image/png"});
}

// ---- 与冻结 Demo（SPEC-DM-012 §7.4，commit 9f3dfb3）同口径的虚构数据 ----
// 图纸集 滨河市政工程.dst；sheetset 属性 项目名称/项目编号/项目.编号；sheet 属性
// 专业代码=RQ、设计人（003/004 缺值——同 Demo「正常与缺值警告」场景）；选中已保存
// 模板「市政标准目录」四列，预览就绪、无未保存修改。
function demoMunicipalTemplate(): CatalogTemplate {
  return {
    template_id: "template-demo-municipal",
    name: "市政标准目录",
    schema_version: 1,
    columns: [
      {column_id: "col-demo-1", header: "图纸编号", expression: "{sheet.专业代码}-{sheet.number}"},
      {column_id: "col-demo-2", header: "图名", expression: "{sheet.title}"},
      {column_id: "col-demo-3", header: "项目名称", expression: "{sheetset.项目名称}"},
      {column_id: "col-demo-4", header: "设计人", expression: "{sheet.设计人}"},
    ],
  };
}

const DEMO_DATASET = {
  dstPath: "C:\\虚构工程\\滨河市政工程.dst",
  sheetSetName: "滨河市政工程",
  sheetCount: 5,
  sheetTitles: ["图纸目录", "道路平面图", "纵断面图", "管线综合图", "节点详图"],
  sheetsetProperties: {"项目名称": "滨河市政工程", "项目编号": "BH-2026", "项目.编号": "BH.2026"},
  sheetProperties: {"专业代码": "RQ", "设计人": ""},
  sheetPropertyValueOverrides: [{name: "设计人", values: ["张工", "张工", "", "", "李工"]}],
  userTemplates: [demoMunicipalTemplate()],
  preferenceTemplateId: "template-demo-municipal",
};

async function openDemoState(page: Page, theme: "light" | "dark", viewport: {width: number; height: number}, dataset: typeof DEMO_DATASET = DEMO_DATASET) {
  await page.setViewportSize(viewport);
  await page.addInitScript(t => localStorage.setItem("dst-manager-theme", t), theme);
  await installSheetCatalogFixture(page, {...dataset});
  await openCatalogPage(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  const preview = page.getByRole("region", {name: "预览"});
  await expect(preview.getByRole("row")).toHaveCount(6); // 表头 + 5 行
  await expect(preview.getByText("共 5 张图纸")).toBeVisible();
  await expect(page.getByText("有未保存修改")).toHaveCount(0);
}

// —— G8 对 1：1440×1000 浅色（与冻结基准 default-light-1440x1000.jpg 同状态）——
test("G8 对 1：1440×1000 浅色缺值警告状态截图 + 布局守卫", async ({page}, info) => {
  await openDemoState(page, "light", {width: 1440, height: 1000});
  await expectNoPageHScroll(page, "1440×1000 浅色");
  await expectActionsReachable(page, ["另存为"]);
  // 补充守卫：滚动后仍无横向裁剪（首屏密度见 PLAN-DM-023 V1/V3 用例）
  await expectActionReachableAfterScroll(page, "刷新预览");
  await expectActionReachableAfterScroll(page, "导出 XLSX");
  await page.evaluate(() => { document.documentElement.scrollTop = 0; document.body.scrollTop = 0; for (const element of document.querySelectorAll<HTMLElement>("*")) if (element.scrollTop > 0) element.scrollTop = 0; });
  // 缺值警告文字（非颜色）：设计人 2 张缺值与 Demo 同口径
  await expect(page.getByRole("region", {name: "兼容性摘要"})).toContainText("设计人");
  await expect(page.getByRole("region", {name: "兼容性摘要"})).toContainText("2");
  await page.mouse.move(0, 0);
  await attachScreenshot(page, info, "g8-catalog-light-1440x1000.png");
});

// —— G8 对 2：900×700 深色（与冻结基准 default-dark-900x700.jpg 同状态）——
test("G8 对 2：900×700 深色最小视口截图 + 布局守卫", async ({page}, info) => {
  await openDemoState(page, "dark", {width: 900, height: 700});
  await expectNoPageHScroll(page, "900×700 深色");
  // 最小视口下主操作不被遮挡（允许页面纵向滚动后可达）
  await expectActionsReachable(page, ["另存为"]);
  await expectActionReachableAfterScroll(page, "导出 XLSX");
  await page.evaluate(() => { document.documentElement.scrollTop = 0; document.body.scrollTop = 0; for (const element of document.querySelectorAll<HTMLElement>("*")) if (element.scrollTop > 0) element.scrollTop = 0; });
  await page.mouse.move(0, 0);
  await attachScreenshot(page, info, "g8-catalog-dark-900x700.png");
});

// —— 200% 缩放（1440×1000 的浏览器 200% = CSS 720×500 + 2x 渲染，CDP 等价）——
test("200% 缩放：无整页横滚、主操作可达、预览区独立横滚", async ({page}) => {
  await openDemoState(page, "light", {width: 1440, height: 1000});
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {width: 720, height: 500, deviceScaleFactor: 2, mobile: false});
  await expectNoPageHScroll(page, "200% 缩放主视图");
  await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeVisible();
  // 最小 CSS 视口下长表达式使预览横向溢出：只允许在表容器内滚动
  await page.getByLabel("表达式 1").fill("{sheet.专业代码}-{sheet.number}-{sheet.title}-" + "超长组合表达式列内容".repeat(8));
  await expect(page.getByRole("region", {name: "预览"}).getByRole("cell").first()).toContainText("超长组合表达式列内容");
  await expectPreviewScrollsInternally(page, "200% 缩放");
  await expectNoPageHScroll(page, "200% 缩放宽预览");
});

// —— 50 列极限：宽预览只在表容器内横滚，页面不随之溢出 ——
test("50 列极限：无整页横滚且预览区独立横滚", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 1000});
  await page.addInitScript(() => localStorage.setItem("dst-manager-theme", "light"));
  const columns = Array.from({length: 50}, (_, index) => ({
    column_id: `col-50-${index + 1}`,
    header: `列 ${index + 1}`,
    expression: "{sheet.number}",
  }));
  const template: CatalogTemplate = {template_id: "template-50-columns", name: "50 列模板", schema_version: 1, columns};
  await installSheetCatalogFixture(page, {userTemplates: [template], preferenceTemplateId: "template-50-columns"});
  await openCatalogPage(page);
  const preview = page.getByRole("region", {name: "预览"});
  await expect(preview.getByRole("columnheader")).toHaveCount(50);
  await expectPreviewScrollsInternally(page, "50 列");
  await expectNoPageHScroll(page, "50 列");
  await expectActionReachableAfterScroll(page, "刷新预览");
  await expectActionReachableAfterScroll(page, "导出 XLSX");
});

// —— 1 列极限：最窄模板布局不破版 ——
test("1 列极限：无整页横滚且主操作可见", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 1000});
  await page.addInitScript(() => localStorage.setItem("dst-manager-theme", "light"));
  const template: CatalogTemplate = {
    template_id: "template-1-column", name: "单列模板", schema_version: 1,
    columns: [{column_id: "col-single", header: "图号", expression: "{sheet.number}"}],
  };
  await installSheetCatalogFixture(page, {userTemplates: [template], preferenceTemplateId: "template-1-column"});
  await openCatalogPage(page);
  await expect(page.getByRole("region", {name: "预览"}).getByRole("columnheader")).toHaveCount(1);
  await expectNoPageHScroll(page, "1 列");
  await expectActionReachableAfterScroll(page, "导出 XLSX");
});

// —— 长字段名与长值：字段浏览器与预览不把页面撑宽 ——
test("长字段名与长值：无整页横滚且预览区独立横滚", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 1000});
  await page.addInitScript(() => localStorage.setItem("dst-manager-theme", "light"));
  const longName = "超长图纸集自定义属性名称用于响应式边界验证壹贰叁肆伍陆柒捌玖拾";
  await installSheetCatalogFixture(page, {
    sheetsetProperties: {[longName]: "滨河市政工程"},
    sheetProperties: {"专业代码": "RQ"},
    sheetPropertyValueOverrides: [{
      name: "专业代码",
      // 首行超长值（宽于全宽预览容器）+ 其余图纸正常值（保证预览可执行、有行可渲染）
      values: ["很长的专业代码值用于验证预览单元格宽度边界".repeat(12), ...Array.from({length: 24}, () => "RQ")],
    }],
    userTemplates: [{
      template_id: "template-long", name: "长字段模板", schema_version: 1,
      columns: [{column_id: "col-long-1", header: longName, expression: `{sheetset["${longName}"]}-{sheet.专业代码}`}],
    }],
    preferenceTemplateId: "template-long",
  });
  await openCatalogPage(page);
  await expect(page.getByRole("region", {name: "字段浏览器"})).toContainText(longName);
  await expectNoPageHScroll(page, "长字段/长值");
  await expectPreviewScrollsInternally(page, "长字段/长值");
});

// —— 大数据摘要：总数正确、预览仍为 20 行、页面不横滚 ——
test("大数据摘要：500 张图纸显示总数与 20 行上限", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 1000});
  await page.addInitScript(() => localStorage.setItem("dst-manager-theme", "light"));
  await installSheetCatalogFixture(page, {sheetCount: 500});
  await openCatalogPage(page);
  const preview = page.getByRole("region", {name: "预览"});
  await expect(preview.getByText("共 500 张图纸")).toBeVisible();
  await expect(preview.getByText("显示前 20 行")).toBeVisible();
  await expect(preview.locator(".table-window")).toHaveCSS("overflow-x", "auto");
  await expectNoPageHScroll(page, "大数据");
});

// =====================================================================
// PLAN-DM-023 Task 1：把冻结布局（SPEC-DM-012 §7.4 / commit 9f3dfb3）的硬要求
// 写成会失败的生产证据。追踪矩阵 V1/V3/V4/V5/V7/V8 的自动验证入口在这里；
// 断言只用几何与可见正文，不用像素比对，也不把“滚动后可达”当作一致。
// =====================================================================

// 首屏密度与结构断言都从页面顶部开始：先把所有层级的滚动位置归零
// （焦点移入输入框或前一个断言滚动过页面时都会改变起点）。
async function resetPageScroll(page: Page) {
  await page.evaluate(() => {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    for (const element of document.querySelectorAll<HTMLElement>("*")) if (element.scrollTop > 0) element.scrollTop = 0;
  });
}

async function previewCardTop(page: Page): Promise<number> {
  const box = await page.getByRole("heading", {name: "预览"}).boundingBox();
  expect(box, "预览标题存在").not.toBeNull();
  return box!.y;
}

// 输出列表头与每行的五列网格轨道（`.columns-head` 与 `.column-row` 共用同一 grid），
// 以 getBoundingClientRect 的 left/right 校验列边界一致。
async function readColumnGrid(page: Page): Promise<{left: number; right: number}[][]> {
  return page.evaluate(() => {
    const rect = (element: Element) => {
      const box = element.getBoundingClientRect();
      return {left: box.left, right: box.right};
    };
    return [
      Array.from(document.querySelectorAll(".columns-head > *")).map(rect),
      ...Array.from(document.querySelectorAll(".columns .column-row")).map(row => Array.from(row.children).map(rect)),
    ];
  });
}

// —— V1/V3：1440×1000 首屏必须同时可见预览标题、前三行数据与导出按钮 ——
test("PLAN-DM-023 V1/V3：1440×1000 首屏同时可见预览标题、第三行数据与导出按钮", async ({page}) => {
  await openDemoState(page, "light", {width: 1440, height: 1000});
  await resetPageScroll(page);
  const dockTop = await page.locator(".dock").evaluate(element => element.getBoundingClientRect().top);
  for (const target of [
    page.getByRole("heading", {name: "预览"}),
    page.getByRole("region", {name: "预览"}).getByRole("row").nth(3),
    page.getByRole("button", {name: "导出 XLSX"}),
  ]) {
    const box = await target.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y + box!.height, "首屏内容底缘不越过 ActionDock").toBeLessThanOrEqual(dockTop);
  }
});

// —— V1/V2/V5：输出列表格式结构 + 兼容性与操作区的 DOM 归属 ——
test("PLAN-DM-023 V1/V2/V5：输出列表格式结构与兼容性/操作区归属", async ({page}) => {
  await openDemoState(page, "light", {width: 1440, height: 1000});
  await resetPageScroll(page);
  const editor = page.getByRole("region", {name: "输出列编辑器"});
  // 唯一表头行，五个列标签顺序固定
  await expect(editor.locator(".columns-head")).toHaveCount(1);
  const headLabels = (await editor.locator(".columns-head > *").allTextContents()).map(text => text.trim());
  expect(headLabels).toEqual(["顺序", "列名", "表达式", "状态", "操作"]);
  // 表头与每个数据行共用同一组列边界（误差 ≤ 1px），且每行都是五个单元格
  const grid = await readColumnGrid(page);
  expect(grid.length, "表头 + 四列模板的四个数据行").toBe(5);
  expect(grid[0]).toHaveLength(5);
  for (const row of grid.slice(1)) {
    expect(row).toHaveLength(5);
    for (let index = 0; index < 5; index++) {
      expect(Math.abs(row[index]!.left - grid[0]![index]!.left), `第 ${index + 1} 列左边界对齐`).toBeLessThanOrEqual(1);
      expect(Math.abs(row[index]!.right - grid[0]![index]!.right), `第 ${index + 1} 列右边界对齐`).toBeLessThanOrEqual(1);
    }
  }
  // 兼容性摘要必须在输出列上下文内，刷新与导出必须在预览上下文内
  await expect(editor.getByRole("region", {name: "兼容性摘要"})).toHaveCount(1);
  const preview = page.getByRole("region", {name: "预览"});
  await expect(preview.getByRole("button", {name: "刷新预览"})).toHaveCount(1);
  await expect(preview.getByRole("button", {name: "导出 XLSX"})).toHaveCount(1);
});

// —— V4：字段本地搜索 + 规范引用与用户名称同为可见正文 ——
test("PLAN-DM-023 V4：字段搜索可见且规范引用与用户名称同为可见正文", async ({page}) => {
  await openDemoState(page, "light", {width: 1440, height: 1000});
  await resetPageScroll(page);
  const browser = page.getByRole("region", {name: "字段浏览器"});
  await expect(page.getByLabel("搜索可用字段")).toBeVisible();
  await expect(browser.getByText("sheet.number", {exact: true})).toBeVisible();
  await expect(browser.getByText("图号", {exact: true})).toBeVisible();
  // 搜索框不改变插入语义：点击条目仍按规范引用插入
  await page.getByLabel("表达式 1").fill("");
  await browser.getByRole("button", {name: /sheet\.number/}).click();
  await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}");
});

// —— V7/V8：列数从 4 增到 6 不得继续撑高页面，编辑区自身滚动 ——
test("PLAN-DM-023 V7/V8：六列模板不撑高页面且列编辑区自身可滚动", async ({page}) => {
  await openDemoState(page, "light", {width: 1440, height: 1000}, {
    ...DEMO_DATASET,
    userTemplates: [demoMunicipalTemplate(), demoSixColumnTemplate()],
  });
  await resetPageScroll(page);
  const fourColumnTop = await previewCardTop(page);
  await page.getByLabel("选择模板").selectOption("template-demo-six");
  await expect(page.getByRole("region", {name: "预览"}).getByRole("columnheader")).toHaveCount(6);
  await resetPageScroll(page);
  const sixColumnTop = await previewCardTop(page);
  expect(Math.abs(sixColumnTop - fourColumnTop), "预览位置不随列数增长继续下移").toBeLessThanOrEqual(2);
  const columns = page.getByRole("region", {name: "输出列编辑器"}).locator(".columns");
  await expect(columns).toHaveCSS("overflow-y", "auto");
  const scroll = await columns.evaluate(element => ({sh: element.scrollHeight, ch: element.clientHeight}));
  expect(scroll.sh, "列编辑区内部可滚动").toBeGreaterThan(scroll.ch);
});

// —— 键盘：完整 Tab 顺序、字段浏览器 Enter/Space 插入、状态不只靠颜色 ——
test("键盘：Tab 顺序经过主操作、字段浏览器 Enter/Space 插入、状态文字化", async ({page}) => {
  await openDemoState(page, "light", {width: 1440, height: 1000});
  // 有序子序列断言：Tab 环按 DOM 顺序经过模板栏 → 字段浏览器 → 列编辑器 → 预览/操作区
  const anchors = ["选择模板", "另存为", "number", "输出列名 1", "表达式 1", "下移 1", "刷新预览", "导出 XLSX"];
  const visited: string[] = [];
  for (let step = 0; step < 140; step++) {
    await page.keyboard.press("Tab");
    const name = await page.evaluate(() => (document.activeElement as HTMLElement | null)?.getAttribute("aria-label")
      ?? (document.activeElement as HTMLElement | null)?.textContent?.trim() ?? "");
    if (name) visited.push(name);
    if (visited.some(item => item.includes("导出 XLSX"))) break;
  }
  let cursor = -1;
  for (const anchor of anchors) {
    const next = visited.slice(cursor + 1).findIndex(item => item.includes(anchor));
    expect(next, `Tab 顺序：${anchor} 应在 ${cursor >= 0 ? visited[cursor] : "起点"} 之后出现（实际：${visited.join(" | ")}）`).toBeGreaterThanOrEqual(0);
    cursor += next + 1;
  }
  // 字段浏览器按钮键盘激活：Enter 与 Space 都在光标位置插入语法
  const expression = page.getByLabel("表达式 1");
  await expression.fill("RQ-");
  await page.getByRole("region", {name: "字段浏览器"}).getByRole("button", {name: "number", exact: true}).focus();
  await page.keyboard.press("Enter");
  await expect(expression).toHaveValue("RQ-{sheet.number}");
  await page.getByRole("region", {name: "字段浏览器"}).getByRole("button", {name: "title", exact: true}).focus();
  await page.keyboard.press("Space");
  await expect(expression).toHaveValue("RQ-{sheet.number}{sheet.title}");
  // 状态不只靠颜色：脏标记、兼容性摘要、模板状态均为文字
  await expect(page.getByText("有未保存修改")).toBeVisible();
  await expect(page.getByRole("region", {name: "兼容性摘要"})).toContainText("警告");
  await expect(page.locator(".catalog-meta")).toContainText("可用");
});
