// PLAN-DM-015 任务 8：视觉、可访问性、回归（SPEC-DM-009 §3.2/§8、SPEC-DM-006 §7）。
// 覆盖：四尺寸 × 浅深主题视口矩阵（默认/行编辑/三类操作表单/浮层展开/长列状态，无横向溢出）、
// 900px 树抽屉键盘开关与焦点归还且不与任务浮层同时锁焦、单一业务表与工具栏/选择条/固定列/ActionDock 不重叠、
// 展开编辑页脚始终可滚动到达、a11y 语义（树方向键/表格可访问名/展开 aria-expanded/完整文本键盘读取）与对比度。
// 截图仅作为 S-07 视觉证据（testInfo 附件），不替代上述行为断言。
import {expect, test, type Locator, type Page} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";

const VIEWPORTS = [
  {width: 1024, height: 768},
  {width: 1120, height: 768},
  {width: 1440, height: 900},
  {width: 900, height: 768},
] as const;
const THEMES = ["light", "dark"] as const;

test("任务浮层覆盖时四尺寸双主题几何与滚动不变", async ({page}) => {
  await installSheetsFixture(page, {sheetCount: 161});
  for (const vp of [VIEWPORTS[2],VIEWPORTS[0],VIEWPORTS[1],VIEWPORTS[3]]) for (const theme of THEMES) {
    await page.setViewportSize(vp);
    await openWorkspace(page, theme);
    await page.locator(".sheet-table-window").evaluate(el => el.scrollTop = 240);
    const snapshot = () => page.locator(".shell-main,.sheets-workspace,.sheet-table-window").evaluateAll(els => els.map(el => {
      const r = el.getBoundingClientRect();
      return {left:r.left,right:r.right,width:r.width,scrollTop:el.scrollTop};
    }));
    const before = await snapshot();
    expect(before[2].scrollTop).toBeGreaterThan(0);
    await page.getByRole("button", {name:"展开任务浮层"}).click();
    await expect(page.getByRole("button", {name:"收起任务浮层"})).toBeVisible();
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    const after = await snapshot();
    for (let i=0;i<before.length;i++) for (const key of ["left","right","width","scrollTop"] as const) expect(Math.abs(before[i][key]-after[i][key])).toBeLessThanOrEqual(1);
    const drawer = await page.locator(".task-drawer").boundingBox();
    const rail = await page.locator(".task-rail").boundingBox();
    const tabs = await page.locator(".tabbar").boundingBox();
    const dock = await page.locator(".dock").boundingBox();
    expect(rail!.width).toBe(48);
    expect(drawer!.x).toBeLessThan(before[0].right);
    expect(drawer!.x+drawer!.width).toBeLessThanOrEqual(rail!.x);
    expect(drawer!.y).toBeGreaterThanOrEqual(tabs!.y+tabs!.height);
    expect(drawer!.y+drawer!.height).toBeLessThanOrEqual(dock!.y);
    await page.keyboard.press("Escape");
    expect(await snapshot()).toEqual(before);
  }
});

test("任务浮层入口、页签键盘、Tab 困绕与 Esc 焦点归还", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page,"light");
  const entry = page.getByRole("button",{name:"修改预览",exact:true});
  await entry.click();
  await expect(entry).toHaveAttribute("aria-expanded","true");
  await expect(entry).toHaveAttribute("aria-controls","task-drawer");
  await expect(page.getByRole("tab",{name:"修改预览"})).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab",{name:"诊断"})).toBeFocused();
  for (const key of ["Tab","Shift+Tab"]) for (let i=0;i<8;i++) {
    await page.keyboard.press(key);
    expect(await page.evaluate(()=>Boolean(document.activeElement?.closest(".task-drawer")))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(page.locator(".task-drawer")).toBeHidden();
  await expect(page.getByRole("button",{name:"诊断",exact:true})).toBeFocused();
});

test("任务浮层 Tab 可达关闭和诊断复制控件并双向循环", async ({page}) => {
  await installSheetsFixture(page,{dualStatus:true});
  await openWorkspace(page,"light");
  await page.getByRole("navigation",{name:"任务入口"}).getByRole("button",{name:"诊断",exact:true}).click();
  const tab=page.getByRole("tab",{name:"诊断"});
  const close=page.getByRole("button",{name:"收起任务浮层"});
  await expect(tab).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(tab).toBeFocused();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const summary=page.locator(".ov-diagnostics summary");
  await expect(summary).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  const copies=page.getByRole("button",{name:"复制诊断 DWG_UNRESOLVED"});
  await expect(copies.first()).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(copies.last()).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(tab).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(copies.last()).toBeFocused();
});

test("导航拖拽后表格列不重叠", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installSheetsFixture(page);
  await openWorkspace(page, "dark");
  for (const width of [260, 320, 420]) {
    const divider = page.getByRole("separator");
    const box = await divider.boundingBox();
    const current = Number(await divider.getAttribute("aria-valuenow"));
    await page.mouse.move(box!.x + 4, box!.y + 30);
    await page.mouse.down();
    await page.mouse.move(box!.x + 4 + width - current, box!.y + 30);
    await page.mouse.up();
    await expect(divider).toHaveAttribute("aria-valuenow", String(width));
    if (width === 420) await page.getByRole("button", {name: "展开任务浮层"}).click();
    for (const selector of ["thead tr", "tbody tr"]) {
      const rects = await page.locator(`.sheet-table-window ${selector}`).first().locator("th,td").evaluateAll(cells => cells.map(cell => {
        const r = cell.getBoundingClientRect();
        return {left: r.left, right: r.right};
      }));
      for (let i = 1; i < rects.length - 1; i++) expect(rects[i].left).toBeGreaterThanOrEqual(rects[i - 1].right - 1);
      const tableBox = (await page.locator(".sheet-table-window").boundingBox())!;
      expect(rects.at(-1)!.right).toBeLessThanOrEqual(tableBox.x + tableBox.width + 1);
    }
    await assertNoHorizontalOverflow(page, 1440);
    expect(await page.locator(".sheet-table-window").evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
    await expect(page.locator(".sheet-table-window")).toHaveCSS("overflow-x", "auto");
  }
});

async function openWorkspace(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => localStorage.setItem("dst-manager-theme", t), theme);
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
  await expect(page.getByRole("table", {name: "图纸表格"})).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

async function assertNoHorizontalOverflow(page: Page, width: number) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

// —— 视口矩阵：默认态 ——
test("默认态四尺寸双主题无横向溢出且主表可达", async ({page}) => {
  await installSheetsFixture(page);
  for (const vp of VIEWPORTS) {
    for (const theme of THEMES) {
      await page.setViewportSize({width: vp.width, height: vp.height});
      await openWorkspace(page, theme);
      await assertNoHorizontalOverflow(page, vp.width);
      await expect(page.getByRole("table", {name: "图纸表格"})).toHaveCount(1);
    }
  }
});

// —— 视口矩阵：行编辑、三类操作表单、任务浮层展开 ——
test("行编辑、三类操作表单与浮层展开在四尺寸双主题下可达且无横向溢出", async ({page}) => {
  await installSheetsFixture(page);
  for (const vp of VIEWPORTS) {
    for (const theme of THEMES) {
      await page.setViewportSize({width: vp.width, height: vp.height});
      await openWorkspace(page, theme);
      // 行编辑（分页属性编辑器）
      await page.getByRole("button", {name: "编辑属性"}).first().click();
      await expect(page.getByRole("region", {name: /属性编辑/})).toBeVisible();
      await assertNoHorizontalOverflow(page, vp.width);
      await page.getByRole("button", {name: "取消", exact: true}).click();
      // 编辑子集
      await page.getByRole("button", {name: "编辑子集"}).click();
      await expect(page.getByRole("region", {name: "编辑子集"})).toBeVisible();
      await assertNoHorizontalOverflow(page, vp.width);
      await page.getByRole("button", {name: "取消", exact: true}).click();
      // 新增图纸
      await page.getByRole("button", {name: "新增图纸"}).click();
      await expect(page.getByRole("region", {name: "新增图纸"})).toBeVisible();
      await assertNoHorizontalOverflow(page, vp.width);
      await page.getByRole("button", {name: "取消", exact: true}).click();
      // 新建子集
      await page.getByRole("button", {name: "新建子集"}).click();
      await expect(page.getByRole("region", {name: "新建子集"})).toBeVisible();
      await assertNoHorizontalOverflow(page, vp.width);
      await page.getByRole("button", {name: "取消", exact: true}).click();
      // 任务浮层展开
      await page.getByRole("button", {name: "展开任务浮层"}).click();
      await expect(page.getByRole("button", {name: "收起任务浮层"})).toBeVisible();
      await assertNoHorizontalOverflow(page, vp.width);
    }
  }
});

// —— 长列状态：超长标题/超长路径下主表仍可达且无横向溢出 ——
test("长列状态在浅深主题下仅表格内部横向滚动、页面不溢出", async ({page}) => {
  await installSheetsFixture(page, {longText: true});
  for (const vp of [VIEWPORTS[2], VIEWPORTS[3]]) {
    for (const theme of THEMES) {
      await page.setViewportSize({width: vp.width, height: vp.height});
      await openWorkspace(page, theme);
      await assertNoHorizontalOverflow(page, vp.width);
      const window = page.locator(".sheet-table-window");
      await expect(window).toBeVisible();
      // 长值键盘聚焦可读（不靠悬停）：夹具仅末张图纸为超长标题/超长路径
      const longRow = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("013", {exact: true})});
      const longTitle = longRow.locator(".title-text");
      await longTitle.focus();
      await expect(longTitle).toBeFocused();
      await expect(longTitle).toHaveAttribute("title", /超长标题/);
    }
  }
});

// —— S-07 视觉证据：四尺寸双主题截图作为测试附件 ——
test("生成四尺寸双主题与三种操作态截图作为 S-07 视觉证据", async ({page}, testInfo) => {
  await installSheetsFixture(page, {longText: true});
  for (const vp of VIEWPORTS) {
    for (const theme of THEMES) {
      await page.setViewportSize({width: vp.width, height: vp.height});
      await openWorkspace(page, theme);
      const shot = testInfo.outputPath(`default-${vp.width}x${vp.height}-${theme}.png`);
      await page.screenshot({path: shot});
      await testInfo.attach(`default-${vp.width}x${vp.height}-${theme}.png`, {path: shot, contentType: "image/png"});
    }
  }
  // 三种操作态截图（1440×900 双主题）
  for (const theme of THEMES) {
    await page.setViewportSize({width: 1440, height: 900});
    await openWorkspace(page, theme);
    await page.getByRole("button", {name: "编辑属性"}).first().click();
    await expect(page.getByRole("region", {name: /属性编辑/})).toBeVisible();
    const edit = testInfo.outputPath(`state-editing-${theme}.png`);
    await page.screenshot({path: edit});
    await testInfo.attach(`state-editing-${theme}.png`, {path: edit, contentType: "image/png"});
    await page.getByRole("button", {name: "取消", exact: true}).click();
    await page.getByRole("button", {name: "编辑子集"}).click();
    await expect(page.getByRole("region", {name: "编辑子集"})).toBeVisible();
    const rename = testInfo.outputPath(`state-rename-${theme}.png`);
    await page.screenshot({path: rename});
    await testInfo.attach(`state-rename-${theme}.png`, {path: rename, contentType: "image/png"});
    await page.getByRole("button", {name: "取消", exact: true}).click();
    await page.getByRole("button", {name: "展开任务浮层"}).click();
    await expect(page.getByRole("button", {name: "收起任务浮层"})).toBeVisible();
    const overlay = testInfo.outputPath(`state-overlay-${theme}.png`);
    await page.screenshot({path: overlay});
    await testInfo.attach(`state-overlay-${theme}.png`, {path: overlay, contentType: "image/png"});
  }
});

// —— 900px 树抽屉：键盘开关、焦点归还、不与任务浮层同时锁焦 ——
test("900px 树收起为可访问抽屉：键盘开关、焦点归还且不与任务浮层同时锁焦", async ({page}) => {
  await installSheetsFixture(page);
  await page.setViewportSize({width: 900, height: 768});
  await openWorkspace(page, "light");
  const toggle = page.locator(".tree-drawer-toggle"); // 名称随开合变化（打开图纸导航/关闭图纸导航），用类定位保持稳定
  await expect(toggle).toBeVisible();
  await expect(page.getByRole("button", {name: "打开图纸导航"})).toBeVisible();
  await assertNoHorizontalOverflow(page, 900);
  // 树抽屉初始收起
  await expect(page.getByRole("tree", {name: "图纸导航"})).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  // 键盘打开：焦点移入树
  await toggle.click();
  await expect(page.getByRole("tree", {name: "图纸导航"})).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  // 任务浮层同时展开：两者不得锁焦，Tab 可离开树抽屉进入主区
  await page.getByRole("button", {name: "展开任务浮层"}).click();
  await expect(page.getByRole("button", {name: "收起任务浮层"})).toBeVisible();
  let leftDrawer = false;
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    leftDrawer = await page.evaluate(() => Boolean(document.activeElement && !document.activeElement.closest(".sheet-tree-pane")));
    if (leftDrawer) break;
  }
  expect(leftDrawer).toBe(true);
  // 第一次 Esc 只关闭任务抽屉，不让树同时抢焦点。
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", {name:"实施进度",exact:true})).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  // 第二次 Esc 关闭树抽屉并把焦点还给树入口。
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("tree", {name: "图纸导航"})).toBeHidden();
});

// —— 单一业务表与各栏不重叠 ——
test("只剩一张业务表；搜索栏、选择条、固定列与 ActionDock 不重叠", async ({page}) => {
  await installSheetsFixture(page);
  await page.setViewportSize({width: 1440, height: 900});
  await openWorkspace(page, "light");
  await expect(page.locator(".sheet-table-window table")).toHaveCount(1);
  await expect(page.getByRole("table", {name: "图纸表格"})).toHaveCount(1);
  // 选择后出现吸顶选择条
  await page.getByRole("checkbox", {name: "全选当前结果"}).check();
  await expect(page.locator(".selection-bar")).toBeVisible();
  const rects = await page.evaluate(() => {
    const rect = (s: string) => {
      const el = document.querySelector<HTMLElement>(s);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {top: r.top, bottom: r.bottom, left: r.left, right: r.right};
    };
    return {
      toolbar: rect(".sheets-toolbar"),
      selection: rect(".selection-bar"),
      table: rect(".sheet-table-window"),
      dock: rect(".dock"),
      selectCol: rect(".sheet-table-window th.col-select"),
      numberCol: rect(".sheet-table-window th.col-number"),
      actionsCol: rect(".sheet-table-window th.col-actions"),
    };
  });
  const overlaps = (a: typeof rects.table, b: typeof rects.table) =>
    a && b && a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1;
  expect(overlaps(rects.toolbar, rects.table)).toBe(false);
  expect(overlaps(rects.selection, rects.table)).toBe(false);
  expect(overlaps(rects.table, rects.dock)).toBe(false);
  // 左固定列始终可见；实际总列宽不足时操作列回归普通列，不覆盖中间字段。
  expect(rects.selectCol && rects.selectCol.left >= rects.table!.left - 1).toBe(true);
  const safeSticky = await page.locator(".sheet-table-window").evaluate(el => el.classList.contains("sticky-actions"));
  if (safeSticky) expect(rects.actionsCol!.right).toBeLessThanOrEqual(rects.table!.right + 1);
  else await expect(page.locator("th.col-actions")).toHaveCSS("right", "auto");
  expect(rects.numberCol && rects.numberCol.left >= rects.selectCol!.right - 1).toBe(true);
});

// —— 展开编辑页脚始终可滚动到达 ——
test("小视口下属性编辑与操作表单页脚可滚动到达", async ({page}) => {
  await installSheetsFixture(page);
  await page.setViewportSize({width: 900, height: 768});
  await openWorkspace(page, "light");
  // 属性编辑器页脚（加入草稿）
  await page.getByRole("button", {name: "编辑属性"}).first().click();
  const editor = page.getByRole("region", {name: /属性编辑/});
  const editSubmit = editor.getByRole("button", {name: "加入草稿"});
  await editSubmit.scrollIntoViewIfNeeded();
  await expect(editSubmit).toBeInViewport();
  await page.getByRole("button", {name: "取消", exact: true}).click();
  // 操作表单页脚（长表单内部滚动，保留取消/加入草稿入口）
  await page.getByRole("button", {name: "编辑子集"}).click();
  const form = page.getByRole("region", {name: "编辑子集"});
  const formSubmit = form.getByRole("button", {name: "加入草稿"});
  await formSubmit.scrollIntoViewIfNeeded();
  await expect(formSubmit).toBeInViewport();
});

// —— a11y：树方向键移动焦点、可访问名、aria-expanded、完整文本键盘读取 ——
test("a11y 语义：树方向键移动焦点、展开按钮 aria-expanded、表格可访问名、完整文本键盘读取", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page, "light");
  const tree = page.getByRole("tree", {name: "图纸导航"});
  await tree.focus();
  // Up/Down 移动焦点（roving tabindex：方向键焦点落到目标节点）
  await page.keyboard.press("ArrowDown");
  const subsetItem = page.getByRole("treeitem", {name: /建筑施工图/});
  await expect(subsetItem).toBeFocused();
  await expect(subsetItem).toHaveAttribute("aria-expanded", "false");
  // 全部图纸范围默认收起；Right 展开当前子集后才进入首张图纸
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("treeitem", {name: "001 图纸 1"})).toBeFocused();
  // Left 从子节点上移到父级子集，再 Left 折叠 → 子节点隐藏；Right 展开 → 子节点可见
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("treeitem", {name: /建筑施工图/})).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("treeitem", {name: "001 图纸 1"})).toHaveCount(0);
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("treeitem", {name: "001 图纸 1"})).toBeVisible();
  // Home/End
  await page.keyboard.press("End");
  await expect(page.getByRole("treeitem", {name: /暖通施工图/})).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("End");
  await expect(page.getByRole("treeitem", {name: /013 图纸 13/})).toBeFocused();
  await page.keyboard.press("Home");
  await expect(page.getByRole("treeitem", {name: /全部图纸/})).toBeFocused();
  // 子集可展开元素带 aria-expanded
  await expect(subsetItem).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("tree", {name: "图纸导航"})).toHaveAttribute("aria-label", "图纸导航");
  // 表格可访问名与选择复选框含图号
  await expect(page.getByRole("table", {name: "图纸表格"})).toBeVisible();
  await expect(page.getByLabel("选择图纸 001")).toBeVisible();
  // 完整文本键盘聚焦读取（标题/文件名省略时不可只靠悬停）
  const title = page.locator(".title-text").first();
  await title.focus();
  await expect(title).toBeFocused();
  await expect(title).toHaveAttribute("title", "图纸 1");
  // 「显示列」面板触发按钮带 aria-expanded（面板打开态）
  const colsToggle = page.getByRole("button", {name: "显示列", exact: true});
  await colsToggle.click();
  await expect(page.getByRole("dialog", {name: "显示列"})).toBeVisible();
  await expect(colsToggle).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(colsToggle).toHaveAttribute("aria-expanded", "false");
  await expect(colsToggle).toBeFocused();
});

// —— 对比度：浅深主题实际渲染前景/背景组合满足 WCAG ——
test("浅深主题正文对比度 ≥ 4.5:1、强调色 UI ≥ 3:1", async ({page}) => {
  await installSheetsFixture(page);
  for (const theme of THEMES) {
    await openWorkspace(page, theme);
    const ratio = await page.evaluate(() => {
      const lum = (r: number, g: number, b: number) => {
        const f = (c: number) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
      };
      const contrast = (a: number[], b: number[]) => {
        const [la, lb] = [lum(a[0], a[1], a[2]), lum(b[0], b[1], b[2])];
        const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
        return (hi + 0.05) / (lo + 0.05);
      };
      const parse = (v: string) => v.match(/[\d.]+/g)!.slice(0, 3).map(Number);
      const color = (sel: string, prop: string) => parse(getComputedStyle(document.querySelector<HTMLElement>(sel)!).getPropertyValue(prop));
      const bg = color(".sheets-workspace", "background-color");
      const primary = color(".tree-root", "color");
      const secondary = color(".count", "color");
      const muted = color(".brand-sub", "color");
      const accent = color(".tab[aria-selected='true']", "color");
      return {
        primary: contrast(primary, bg),
        secondary: contrast(secondary, bg),
        muted: contrast(muted, bg),
        accent: contrast(accent, bg),
      };
    });
    expect(ratio.primary, `primary ${theme}`).toBeGreaterThanOrEqual(4.5);
    expect(ratio.secondary, `secondary ${theme}`).toBeGreaterThanOrEqual(4.5);
    expect(ratio.muted, `muted ${theme}`).toBeGreaterThanOrEqual(4.5);
    expect(ratio.accent, `accent ${theme}`).toBeGreaterThanOrEqual(3);
  }
});
for (const operation of ["编辑子集", "新增图纸", "新建子集"]) {
  test(`独立编辑卡片：${operation}位于列表上方且取消后列表恢复高度`, async ({page}) => {
    await page.setViewportSize({width: 1440, height: 900});
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    const list = page.locator(".sheet-list-card");
    const editor = page.locator(".sheet-editor-card");
    await page.getByRole("button", {name: operation, exact: true}).click();
    await expect(editor).toHaveCount(1);
    await expect(list.locator(".sheets-toolbar")).toHaveCount(1);
    await expect(list.getByRole("table", {name: "图纸表格"})).toHaveCount(1);
    await expect(editor.locator(".sheets-toolbar")).toHaveCount(0);
    const editorBox = await editor.boundingBox();
    const listBox = await list.boundingBox();
    expect(editorBox!.y + editorBox!.height).toBeLessThanOrEqual(listBox!.y + 1);
    for (const card of [editor, list]) {
      const style = await card.evaluate(el => {
        const css = getComputedStyle(el);
        return {border: parseFloat(css.borderTopWidth), radius: parseFloat(css.borderTopLeftRadius), background: css.backgroundColor};
      });
      expect(style.border).toBeGreaterThan(0);
      expect(style.radius).toBeGreaterThan(0);
      expect(style.background).not.toBe("rgba(0, 0, 0, 0)");
    }
    await editor.getByRole("button", {name: "取消", exact: true}).click();
    await expect(editor).toHaveCount(0);
    const mainBox = await page.locator(".sheets-main").boundingBox();
    const restored = await list.boundingBox();
    expect(restored!.y).toBeCloseTo(mainBox!.y, 0);
    expect(restored!.height).toBeCloseTo(mainBox!.height, 0);
  });
}

test("批量编辑上下文不渲染空编辑卡片", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page, "light");
  await page.locator(".sheet-table-window tbody input[type=checkbox]").first().check();
  await page.getByRole("button", {name: "批量修改属性", exact: true}).click();
  await expect(page.locator(".sheet-editor-card")).toHaveCount(0);
  await expect(page.locator(".sheet-list-card .sheets-toolbar")).toHaveCount(1);
});

// PLAN-DM-029 Task 7：控件视觉基础（令牌 / 档位 / 同行对齐）。
// 迁移是值保持的，故以下多数断言属「回归钉」（迁移前后均应通过，另做变异自证证明非空转）；
// 工具栏动作按钮改用 UiButton 后字号由原语接管（13px → --button-font-size 14px），这类是真红。
test.describe("控件视觉基础（PLAN-DM-029 Task 7）", () => {
  async function resolveToken(page: Page, token: string, property: string): Promise<string> {
    return page.evaluate(([name, prop]) => {
      const probe = document.createElement("div");
      probe.style.setProperty(prop, `var(${name})`);
      document.body.appendChild(probe);
      const value = getComputedStyle(probe).getPropertyValue(prop);
      probe.remove();
      return value;
    }, [token, property]);
  }

  async function expectToken(page: Page, target: Locator, property: string, token: string): Promise<void> {
    const expected = await resolveToken(page, token, property);
    expect(expected, `${token} 必须能解析成具体值`).not.toBe("");
    const actual = await target.first().evaluate((element, prop) => getComputedStyle(element).getPropertyValue(prop), property);
    expect(actual, `${property} 应来自 ${token}`).toBe(expected);
  }

  test("工具栏动作按钮：紧凑档 34px 且字号由原语接管", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    const rename = page.getByRole("button", {name: "编辑子集", exact: true});
    await expectToken(page, rename, "height", "--control-height-compact");
    // UiButton 的下限来自原语的全局最小可点令牌（--min-tap-height=32px），而非页面的 34px；
    // 生效高度仍是 34px（height 大于 min-height），属无视觉影响的值变化。
    await expectToken(page, rename, "min-height", "--min-tap-height");
    await expectToken(page, rename, "font-size", "--button-font-size");
    await expectToken(page, page.locator(".filter-toggle"), "height", "--control-height-compact");
    await expectToken(page, page.locator(".filter-toggle"), "font-size", "--button-font-size");
  });

  test("显示列入口：生效值由工具栏唯一声明（消除注入顺序依赖）", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    const toggle = page.locator(".sheets-toolbar .cols-toggle");
    // `.cols-toggle` 的高度/内边距/圆角只由 `SheetToolbar.vue` 的 `:deep(.cols-toggle)` 声明。
    // 曾两侧同特异性（均 0,2,0）重复声明不同取值（子组件侧 4px 10px / --radius-sm），
    // 生效值取决于样式表注入顺序；现以**绝对值**钉住实测生效值，顺序变化会被立刻发现。
    await expect(toggle).toHaveCSS("height", "34px");
    await expect(toggle).toHaveCSS("padding-top", "0px");
    await expect(toggle).toHaveCSS("padding-left", "12px");
    await expect(toggle).toHaveCSS("border-top-left-radius", "8px");
    await expect(toggle).toHaveCSS("font-size", "13px");
  });

  test("常驻搜索与筛选：38px 表单档与搜索框宽度令牌", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    const search = page.locator(".search-box input");
    await expectToken(page, search, "width", "--sheet-search-width");
    // 绝对锚：expectToken 只证明「属性取自该令牌」——若令牌自身取值漂移，两侧同时变化仍会通过。
    // 故对本次新增的结构令牌再钉一次字面值，让「值保持」也机械可查（对应责任 S）。
    await expect(search).toHaveCSS("width", "260px");
    await expectToken(page, search, "height", "--control-height-form");
    await page.locator(".filter-toggle").click();
    await expectToken(page, page.locator(".toolbar-filters select").first(), "height", "--control-height-form");
  });

  test("条件标签：圆角与字号取自语义令牌", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    await page.locator(".filter-toggle").click();
    await page.locator(".toolbar-filters select").first().selectOption("resolved");
    const chip = page.locator(".chip").first();
    await expect(chip).toBeVisible();
    await expectToken(page, chip, "border-top-left-radius", "--radius-lg");
    await expectToken(page, chip, "font-size", "--font-caption");
  });

  test("批量编辑：同行居中、38px 值输入、未选属性时队列按钮禁用", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    await page.locator(".sheet-table-window tbody input[type=checkbox]").first().check();
    await page.getByRole("button", {name: "批量修改属性", exact: true}).click();
    const controls = page.locator(".bulk-controls");
    await expect(controls).toBeVisible();
    // 同行中心：各控件垂直中心必须一致（高度档不同也不许错位）
    const centers = await controls.locator("select, input").evaluateAll(elements => elements.map(element => {
      const rect = element.getBoundingClientRect();
      return Math.round(rect.top + rect.height / 2);
    }));
    expect(centers.length).toBeGreaterThan(1);
    expect(new Set(centers).size, `批量控件必须同行居中，实际 ${centers.join(" / ")}`).toBe(1);
    await expectToken(page, controls.locator("input").first(), "height", "--control-height-form");
    await expectToken(page, controls.locator("select").first(), "height", "--control-height-form");
    // 未选属性 → 加入草稿禁用（行为不变）
    await expect(controls.locator("button").last()).toBeDisabled();
    // T7-1(A) 第 4 个令牌的消费点：bulkMode=clear 分支渲染 .bulk-hint
    await controls.locator("select").first().selectOption("clear");
    await expectToken(page, page.locator(".bulk-hint"), "max-width", "--sheet-bulk-hint-max-width");
    await expect(page.locator(".bulk-hint")).toHaveCSS("max-width", "220px");
  });

  test("行状态徽章令牌：取值钉住", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    // `.status` 徽章只在行处于「待变更」或有诊断时渲染（SheetTable.vue:100-102）；
    // pendingSheetIds 由壳层根据草稿计算，图纸页固定装置不产这两种行状态（已实测：
    // 选中行 + 批量修改属性 + 点「加入草稿」后仍无 .status.pending）。
    // 故此处钉**令牌取值本身**；消费者存在性由 check:ui 的变量定义/引用规则保证。
    expect(await resolveToken(page, "--sheet-status-radius", "border-top-left-radius"), "--sheet-status-radius 必须解析为 10px").toBe("10px");
  });

  test("表格结构令牌：行高、行盒高、窗口最小高与表内字号", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    await expectToken(page, page.locator("table").first(), "font-size", "--font-label");
    await expectToken(page, page.locator("th").first(), "height", "--sheet-table-row-height");
    await expectToken(page, page.locator("th").first(), "line-height", "--sheet-table-line-height");
    await expectToken(page, page.locator(".sheet-table-window"), "min-height", "--sheet-table-window-min-height");
    await expectToken(page, page.locator(".title-text").first(), "max-width", "--sheet-title-max-width");
    // 绝对锚（同责任 S）：结构性令牌的字面值也不得漂移
    await expect(page.locator("th").first()).toHaveCSS("height", "44px");
    await expect(page.locator("th").first()).toHaveCSS("line-height", "20px");
    await expect(page.locator(".sheet-table-window")).toHaveCSS("min-height", "130px");
    await expect(page.locator(".title-text").first()).toHaveCSS("max-width", "280px");
  });

  test("列设置面板：宽度令牌与保留的 15px 标题字号", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    await page.locator(".cols-toggle").click();
    const panel = page.locator(".cols-panel");
    await expect(panel).toBeVisible();
    await expectToken(page, panel, "width", "--sheet-columns-panel-width");
    await expect(panel).toHaveCSS("width", "380px");
    // 15px 保留为显式例外（责任 K）：此处钉住当前值，防被顺手改动
    await expect(panel.locator(".cols-title")).toHaveCSS("font-size", "15px");
  });

  test("操作表单：38px 输入档与 36px 动作档", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    await page.getByRole("button", {name: "编辑子集", exact: true}).click();
    const form = page.locator(".operation-form");
    await expect(form).toBeVisible();
    await expectToken(page, form.locator("input").first(), "height", "--control-height-form");
    await expectToken(page, form.locator("select").first(), "height", "--control-height-form");
    await expectToken(page, form.locator("button").first(), "min-height", "--control-height-default");
  });

  test("行内属性编辑器：搜索框宽度令牌与保留的 15px 标题字号", async ({page}) => {
    await installSheetsFixture(page);
    await openWorkspace(page, "light");
    // 行内属性编辑器（SheetTable 内）——续轮补上 T7-1(A) 第 3 个令牌的覆盖缺口
    await page.getByRole("button", {name: "编辑属性"}).first().click();
    const editor = page.getByRole("region", {name: /属性编辑/});
    await expect(editor).toBeVisible();
    await expectToken(page, editor.locator(".editor-search input"), "width", "--sheet-property-search-width");
    await expect(editor.locator(".editor-search input")).toHaveCSS("width", "180px");
    // 15px 第 2 个消费者（3 处之一是 .editor-head h3）：同样保留为显式例外（责任 K），钉住当前值防顺手改动
    await expect(editor.locator(".editor-head h3")).toHaveCSS("font-size", "15px");
  });
});

// —— Step 4：批量编辑区四视口密集布局（不撑破表格、操作列可达、滚动条不遮内容） ——
test("批量编辑：四视口不撑破页面、操作列横向可达、滚动条不遮末行", async ({page}) => {
  await installSheetsFixture(page);
  // 由窄到宽遍历四个约定视口
  for (const vp of [VIEWPORTS[3], VIEWPORTS[0], VIEWPORTS[1], VIEWPORTS[2]]) {
    await page.setViewportSize({width: vp.width, height: vp.height});
    await openWorkspace(page, "light");
    await page.locator(".sheet-table-window tbody input[type=checkbox]").first().check();
    await page.getByRole("button", {name: "批量修改属性", exact: true}).click();
    const controls = page.locator(".bulk-controls");
    await expect(controls).toBeVisible();
    // ① 批量编辑区不得把页面撑出横向滚动
    await assertNoHorizontalOverflow(page, vp.width);
    const box = (await controls.boundingBox())!;
    expect(box.x, `${vp.width}：批量区左缘不得为负`).toBeGreaterThanOrEqual(-1);
    expect(box.x + box.width, `${vp.width}：批量区右缘不得超出视口`).toBeLessThanOrEqual(vp.width + 1);
    // ② 操作列高度可达：横向滚到最右后，末列单元格必须落在窗口可见区内
    const win = page.locator(".sheet-table-window");
    // 反空转：若窗口本身无横向溢出，「滚到最右仍可达」就是恒真断言
    expect(await win.evaluate(el => el.scrollWidth > el.clientWidth), `${vp.width}：应确有横向溢出，否则可达性断言空转`).toBe(true);
    const winBox = (await win.boundingBox())!;
    const winLeft = winBox.x;
    const winRight = winBox.x + winBox.width;
    const winBottom = winBox.y + winBox.height;
    await win.evaluate(el => { el.scrollLeft = el.scrollWidth; });
    const lastCell = (await win.locator("tbody tr").first().locator("td").last().boundingBox())!;
    const cellRight = lastCell.x + lastCell.width;
    expect(cellRight, `${vp.width}：操作列滚到最右后可见`).toBeLessThanOrEqual(winRight + 1);
    expect(cellRight, `${vp.width}：操作列不得被裁到窗口左侧之外`).toBeGreaterThan(winLeft);
    // ③ 横向滚动条不遮挡内容：纵向滚到底后末行底缘不得低于窗口底缘
    await win.evaluate(el => { el.scrollTop = el.scrollHeight; });
    const lastRow = (await win.locator("tbody tr").last().boundingBox())!;
    expect(lastRow.y + lastRow.height, `${vp.width}：末行不得被横向滚动条覆盖`).toBeLessThanOrEqual(winBottom + 1);
  }
});

// —— Step 4：200% 浏览器缩放韧性（CSS 视口 720×500，同 SPEC-DM-012 §13 口径） ——
test("200% 缩放（720×500）：无整页横滚且关键控件仍可达", async ({page}) => {
  await installSheetsFixture(page);
  await page.setViewportSize({width: 720, height: 500});
  await openWorkspace(page, "light");
  await assertNoHorizontalOverflow(page, 720);
  // 树降级为抽屉，触发按钮必须仍在
  await expect(page.locator(".tree-drawer-toggle")).toBeVisible();
  await expect(page.getByRole("table", {name: "图纸表格"})).toBeVisible();
  // 关键控件仍可达（表格内动作需先横向滚入）
  for (const name of ["编辑属性", "编辑子集"]) {
    const target = page.getByRole("button", {name}).first();
    await target.scrollIntoViewIfNeeded();
    await expect(target, `200%：${name} 应在视口内`).toBeInViewport();
  }
  // 批量区在 200% 下仍可用且不撑破
  await page.locator(".sheet-table-window tbody input[type=checkbox]").first().check();
  await page.getByRole("button", {name: "批量修改属性", exact: true}).click();
  await expect(page.locator(".bulk-controls")).toBeVisible();
  await assertNoHorizontalOverflow(page, 720);
});
