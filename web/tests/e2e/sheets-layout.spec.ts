// PLAN-DM-015 任务 8：视觉、可访问性、回归（SPEC-DM-009 §3.2/§8、SPEC-DM-006 §7）。
// 覆盖：四尺寸 × 浅深主题视口矩阵（默认/行编辑/三类操作表单/浮层展开/长列状态，无横向溢出）、
// 900px 树抽屉键盘开关与焦点归还且不与任务浮层同时锁焦、单一业务表与工具栏/选择条/固定列/ActionDock 不重叠、
// 展开编辑页脚始终可滚动到达、a11y 语义（树方向键/表格可访问名/展开 aria-expanded/完整文本键盘读取）与对比度。
// 截图仅作为 S-07 视觉证据（testInfo 附件），不替代上述行为断言。
import {expect, test, type Page} from "@playwright/test";
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
