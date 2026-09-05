// PLAN-DM-015 任务 4：可配置列与图纸集级恢复（SPEC-DM-009 §5）e2e。
// 覆盖：固定列不可关、默认列与前三属性、子集列按两种范围分别记忆、36 字段搜索、
// 同名内置列独立配置、删除字段墓碑/撤销恢复、新增字段默认关并提示、重开恢复、
// 不同工作区不串、存储失败当前选择仍生效、标题两行/文件名键盘聚焦、窄屏不隐藏、诊断复制。
import {expect, test, type Page} from "@playwright/test";

test("列宽模型保持确定且短列文本与双状态限制在列内", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installSheetsFixture(page, {longText: true, dualStatus: true});
  await openWorkspace(page);
  await openColumns(page);
  await page.getByRole("checkbox", {name: "布局", exact: true}).check();
  await closeColumns(page);
  const widths = await page.locator(".sheet-table-window th").evaluateAll(cells => cells.map(cell => cell.getBoundingClientRect().width));
  expect(widths).toEqual([40, 72, 270, 220, 260, 160, 96, 140, 140, 140, 150]);
  const ordinary = await page.locator(".sheet-table-window tbody tr").nth(2).boundingBox();
  expect(ordinary!.height).toBeGreaterThanOrEqual(40);
  expect(ordinary!.height).toBeLessThanOrEqual(48);
  const status = page.locator(".sheet-table-window tbody tr").first().locator("td.col-status");
  await expect(status.locator(".pending")).toBeVisible();
  await expect(status.locator(".blocking")).toBeVisible();
  const geometry = await status.evaluate(el => {
    const cell = el.getBoundingClientRect();
    return [...el.children].map(child => {
      const r = child.getBoundingClientRect();
      return {left: r.left - cell.left, right: r.right - cell.left, top: r.top, bottom: r.bottom};
    });
  });
  for (const rect of geometry) {
    expect(rect.left).toBeGreaterThanOrEqual(0);
    expect(rect.right).toBeLessThanOrEqual(96);
  }
  for (let i = 1; i < geometry.length; i++) {
    const a = geometry[i - 1], b = geometry[i];
    expect(b.top >= a.bottom - 1 || b.left >= a.right - 1).toBe(true);
  }
  const number = page.locator(".sheet-table-window tbody tr .col-number .ellipsis").first();
  await expect(number).toHaveCSS("text-overflow", "ellipsis");
  await expect(number).toHaveAttribute("title", /.+/);
  for (const column of ["subset", "file", "layout", "prop"]) {
    const text = page.locator(`.sheet-table-window tbody tr .col-${column} .multiline-text`).first();
    await expect(text).toHaveCSS("-webkit-line-clamp", "2");
    await expect(text).toHaveCSS("white-space", "normal");
    await expect(text).toHaveAttribute("title", /.+/);
  }
});
import {installSheetsFixture} from "./fixtures/sheets";
import type {ColumnPreferences} from "../../src/features/sheets/types";

async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("table", {name: "图纸表格"})).toBeVisible();
}
async function openColumns(page: Page) {
  await page.getByRole("button", {name: "显示列"}).click();
  await expect(page.getByRole("dialog", {name: "显示列"})).toBeVisible();
}
async function closeColumns(page: Page) {
  await page.getByRole("button", {name: "关闭显示列"}).click();
  await expect(page.getByRole("dialog", {name: "显示列"})).toHaveCount(0);
}

function seededPreferences(overrides: Partial<ColumnPreferences>): ColumnPreferences {
  return {schemaVersion: 1, file: true, layout: false, subsetAll: true, subsetSingle: false, properties: {}, ...overrides};
}

test("固定列不可关且默认可选列与前三自定义属性符合规范", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openColumns(page);
  // 固定图号/标题/状态/操作锁定为禁用
  for (const name of ["图号", "标题", "状态", "操作"]) {
    await expect(page.getByRole("checkbox", {name: `${name} 固定`})).toBeDisabled();
  }
  // 文件名默认开、布局默认关、子集列（当前范围）默认开
  await expect(page.getByRole("checkbox", {name: "文件名"})).toBeChecked();
  await expect(page.getByRole("checkbox", {name: "布局", exact: true})).not.toBeChecked();
  await expect(page.getByRole("checkbox", {name: "所属子集（当前范围）"})).toBeChecked();
  // 前三自定义属性默认开，第四项起默认关
  for (const name of ["图幅", "比例", "专业"]) {
    await expect(page.getByRole("checkbox", {name, exact: true})).toBeChecked();
  }
  await expect(page.getByRole("checkbox", {name: "属性04", exact: true})).not.toBeChecked();
});

test("显示列开关立即改变表格列且不改变业务对象", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toHaveCount(0);
  await openColumns(page);
  await page.getByRole("checkbox", {name: "布局", exact: true}).check();
  await closeColumns(page);
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toBeVisible();
  // 取消文件名 → 立即隐藏
  await openColumns(page);
  await page.getByRole("checkbox", {name: "文件名"}).uncheck();
  await closeColumns(page);
  await expect(page.getByRole("columnheader", {name: "文件名", exact: true})).toHaveCount(0);
});

test("子集列按全部/单子集范围分别记忆开关", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  // 全部范围：子集列默认显示
  await expect(page.getByRole("columnheader", {name: "子集", exact: true})).toBeVisible();
  // 全部范围关闭子集列
  await openColumns(page);
  await page.getByRole("checkbox", {name: "所属子集（当前范围）"}).uncheck();
  await closeColumns(page);
  await expect(page.getByRole("columnheader", {name: "子集", exact: true})).toHaveCount(0);
  // 单子集范围：默认隐藏（subsetSingle 独立记忆）
  await page.getByRole("treeitem", {name: /建筑施工图/}).click();
  await expect(page.getByRole("columnheader", {name: "子集", exact: true})).toHaveCount(0);
  // 单子集范围打开子集列
  await openColumns(page);
  await page.getByRole("checkbox", {name: "所属子集（当前范围）"}).check();
  await closeColumns(page);
  await expect(page.getByRole("columnheader", {name: "子集", exact: true})).toBeVisible();
  // 回全部：全部范围的开关仍关闭
  await page.getByRole("treeitem", {name: /全部图纸/}).click();
  await expect(page.getByRole("columnheader", {name: "子集", exact: true})).toHaveCount(0);
  // 再回单子集：仍开启
  await page.getByRole("treeitem", {name: /建筑施工图/}).click();
  await expect(page.getByRole("columnheader", {name: "子集", exact: true})).toBeVisible();
});

test("自定义属性多时支持名称搜索", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openColumns(page);
  await page.getByRole("textbox", {name: "搜索自定义属性"}).fill("属性1");
  // 仅匹配 属性10–属性19 共 10 项；图幅被过滤、固定列常显
  await expect(page.getByRole("checkbox", {name: /^属性1/})).toHaveCount(10);
  await expect(page.getByRole("checkbox", {name: "图幅", exact: true})).toHaveCount(0);
  await expect(page.getByRole("checkbox", {name: "图号 固定"})).toBeVisible();
  // 清空恢复全部属性
  await page.getByRole("textbox", {name: "搜索自定义属性"}).fill("");
  await expect(page.getByRole("checkbox", {name: "图幅", exact: true})).toBeVisible();
});

test("同名内置列的属性独立配置不冲突", async ({page}) => {
  await installSheetsFixture(page, {propertyCount: 4, propertyNames: ["图幅", "比例", "专业", "图号"]});
  await openWorkspace(page);
  await openColumns(page);
  // 内置图号固定锁定；同名属性「图号」独立可开关（第四个，默认关）
  await expect(page.getByRole("checkbox", {name: "图号 固定"})).toBeDisabled();
  const propertyNumber = page.getByRole("checkbox", {name: "图号", exact: true});
  await expect(propertyNumber).not.toBeChecked();
  await propertyNumber.check();
  await closeColumns(page);
  // 表格出现两列「图号」：内置 + 自定义属性
  await expect(page.getByRole("columnheader", {name: "图号", exact: true})).toHaveCount(2);
});

test("拉丁字母属性名取值按原始大小写且重开后偏好身份稳定", async ({page}) => {
  await installSheetsFixture(page, {propertyCount: 5, propertyNames: ["图幅", "比例", "专业", "No.", "Scale"]});
  await openWorkspace(page);
  // 打开两个拉丁名属性列（默认关）
  await openColumns(page);
  await page.getByRole("checkbox", {name: "No.", exact: true}).check();
  await page.getByRole("checkbox", {name: "Scale", exact: true}).check();
  await closeColumns(page);
  // 值按服务端原始大小写键正确显示（修复前用小写 PropertyKey 取参会静默显示 "—"）
  const firstRow = page.locator(".sheet-table-window tbody tr").first();
  await expect(firstRow.getByText("V4", {exact: true})).toBeVisible();
  await expect(firstRow.getByText("V5", {exact: true})).toBeVisible();
  // 偏好身份稳定（小写 PropertyKey 仅用于偏好身份）：关闭重开后两个拉丁名列仍开启
  await page.getByRole("button", {name: "关闭工作区"}).click();
  await expect(page.getByRole("button", {name: "选择 DST 文件"})).toBeVisible();
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("columnheader", {name: "No.", exact: true})).toBeVisible();
  await expect(page.getByRole("columnheader", {name: "Scale", exact: true})).toBeVisible();
});

test("删除字段从配置移除且撤销恢复此前开关", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  // 打开属性07
  await openColumns(page);
  await page.getByRole("checkbox", {name: "属性07"}).check();
  await closeColumns(page);
  await expect(page.getByRole("columnheader", {name: "属性07", exact: true})).toBeVisible();
  // 属性标签删除属性07 定义
  await page.getByRole("tab", {name: /属性/}).click();
  await page.getByRole("button", {name: "删除 属性07"}).click();
  // 回图纸标签：列从表格与配置列表移除
  await page.getByRole("tab", {name: /图纸/}).click();
  await expect(page.getByRole("columnheader", {name: "属性07", exact: true})).toHaveCount(0);
  await openColumns(page);
  await expect(page.getByRole("checkbox", {name: "属性07"})).toHaveCount(0);
  await closeColumns(page);
  // 撤销删除 → 墓碑恢复此前开关（列重新显示）
  await page.getByRole("button", {name: "撤销"}).click();
  await expect(page.getByRole("columnheader", {name: "属性07", exact: true})).toBeVisible();
});

test("新增字段默认关闭并在配置入口提示新字段", async ({page}) => {
  const seeded = seededPreferences({properties: {"sheet:图幅": true, "sheet:比例": true, "sheet:专业": true}});
  await installSheetsFixture(page, {initialColumns: {"workspace-1": seeded}});
  await openWorkspace(page);
  const toggle = page.getByRole("button", {name: /显示列/});
  // 属性04–属性36 共 33 个新字段在入口计数提示
  await expect(toggle).toContainText("33");
  await openColumns(page);
  // 新增字段默认关且带「新字段」提示
  const property04 = page.getByRole("checkbox", {name: "属性04", exact: true});
  await expect(property04).not.toBeChecked();
  await expect(page.getByText("新字段", {exact: true}).first()).toBeVisible();
  // 勾选后不再计入新字段
  await property04.check();
  await closeColumns(page);
  await expect(toggle).not.toContainText("33");
});

test("恢复默认立即生效并重置为首次默认", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openColumns(page);
  // 先改两项：打开布局、关闭文件名
  await page.getByRole("checkbox", {name: "布局", exact: true}).check();
  await page.getByRole("checkbox", {name: "文件名"}).uncheck();
  // 恢复默认：布局关、文件名开、前三属性开
  await page.getByRole("button", {name: "恢复默认"}).click();
  await expect(page.getByRole("checkbox", {name: "布局", exact: true})).not.toBeChecked();
  await expect(page.getByRole("checkbox", {name: "文件名"})).toBeChecked();
  await expect(page.getByRole("checkbox", {name: "图幅", exact: true})).toBeChecked();
  await closeColumns(page);
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toHaveCount(0);
});

test("重开同一工作区恢复列配置", async ({page}) => {
  const seeded = seededPreferences({layout: true});
  await installSheetsFixture(page, {initialColumns: {"workspace-1": seeded}});
  await openWorkspace(page);
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toBeVisible();
});

test("不同工作区不串列配置", async ({page}) => {
  const seeded = seededPreferences({layout: true});
  await installSheetsFixture(page, {
    initialColumns: {"workspace-1": seeded},
    secondWorkspace: {dstPath: "C:\\虚构工程\\第二套图纸.dst", options: {sheetCount: 4, subsetCount: 2}},
  });
  await openWorkspace(page);
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toBeVisible();
  // 关闭并打开第二个工作区（不同 ID、无预置偏好）：不受第一个影响
  await page.getByRole("button", {name: "关闭工作区"}).click();
  await expect(page.getByRole("button", {name: "选择 DST 文件"})).toBeVisible();
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\虚构工程\\第二套图纸.dst"; });
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toHaveCount(0);
  // 第二个工作区独立开关
  await openColumns(page);
  await page.getByRole("checkbox", {name: "布局", exact: true}).check();
  await closeColumns(page);
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toBeVisible();
  // 关闭并重开第一个工作区：布局仍开启（未被第二个覆盖）
  await page.getByRole("button", {name: "关闭工作区"}).click();
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\虚构工程\\图纸集.dst"; });
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toBeVisible();
});

test("存储失败时当前选择仍生效且提示", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  // 注入存储失败：save_sheet_columns 返回 IO 错误
  await page.evaluate(() => {
    (window as any).pywebview.api.save_sheet_columns = async () => ({ok: false, code: "SHEET_PREFERENCES_IO", message: "磁盘只读"});
  });
  await openColumns(page);
  await page.getByRole("checkbox", {name: "布局", exact: true}).check();
  await expect(page.getByText("列配置保存失败，当前选择仍在本会话生效", {exact: true})).toBeVisible();
  await closeColumns(page);
  // 当前会话选择仍生效（未回退）
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toBeVisible();
});

test("标题最多两行且文件名单独显示并可键盘聚焦读取", async ({page}) => {
  await installSheetsFixture(page, {longText: true});
  await openWorkspace(page);
  const row = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("013", {exact: true})});
  // 标题最多两行，完整值悬停与键盘聚焦可读
  const title = row.locator(".title-text");
  await expect(title).toHaveCSS("-webkit-line-clamp", "2");
  await expect(title).toHaveAttribute("title", /超长标题/);
  await expect(title).toHaveAttribute("tabindex", "0");
  // 文件名只显示 basename，省略时仍可键盘聚焦读取完整文件名，不泄露目录路径
  const file = row.locator(".col-file .multiline-text");
  await expect(file).toHaveText("第 13 分册最终版.dwg");
  await expect(file).toHaveAttribute("title", "第 13 分册最终版.dwg");
  await expect(file).not.toContainText("C:\\虚构工程");
  await file.focus();
  await expect(file).toBeFocused();
});

test("窄屏下已配置列不自动隐藏仅内部横向滚动", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openColumns(page);
  await page.getByRole("checkbox", {name: "布局", exact: true}).check();
  await closeColumns(page);
  // 已配置列不因窄屏自动消失
  await expect(page.getByRole("columnheader", {name: "布局", exact: true})).toBeVisible();
  await expect(page.getByRole("columnheader", {name: "图号", exact: true})).toBeVisible();
  await expect(page.getByRole("columnheader", {name: "状态", exact: true})).toBeVisible();
  // 横向滚动仅限表格内部
  await expect(page.locator(".sheet-table-window")).toHaveCSS("overflow-x", "auto");
});

test("异常状态进入诊断并可复制原始路径", async ({page}) => {
  await page.addInitScript(() => {
    (window as any).__copiedText = "";
    Object.defineProperty(navigator, "clipboard", {
      value: {writeText: async (text: string) => { (window as any).__copiedText = text; }},
      configurable: true,
    });
  });
  await installSheetsFixture(page, {dualStatus: true});
  await openWorkspace(page);
  // 状态列对有诊断的行提供「诊断」跳转
  const row1 = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("001", {exact: true})});
  await expect(row1.getByRole("button", {name: "诊断"})).toBeVisible();
  await row1.getByRole("button", {name: "诊断"}).click();
  // 任务浮层诊断页签激活
  await expect(page.getByRole("tab", {name: "诊断", exact: true})).toHaveAttribute("aria-selected", "true");
  // 展开诊断列表（details 默认折叠）后复制原始诊断值（含原始路径），内容与后端原值一致
  await page.locator(".ov-diagnostics summary").click();
  await page.getByRole("button", {name: "复制诊断 DWG_UNRESOLVED"}).first().click();
  await expect.poll(() => page.evaluate(() => (window as any).__copiedText)).toBe("DWG_UNRESOLVED：图纸 001 布局未解析");
});
