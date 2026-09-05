// PLAN-DM-016 任务 4：属性字段定义折叠、查询、六条分页与增删 e2e（SPEC-DM-010 §4、P-01/P-02/P-05/P-12/P-14）。
// 覆盖：36 定义默认折叠、展开每页六条、名称/默认值搜索与作用域筛选、页码复位与最后一页删除回退、
// 同名跨作用域独立、空/长默认值、新增成功清空与筛选不匹配「查看字段」、新增失败保留输入、
// 删除确认文案不虚构影响数量、删除前先处理对应未提交值，以及定义表视觉与滚动契约。
// 夹具为本 spec 内联虚构数据（共享夹具由任务 6 建立），不含真实工程内容。
import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";
import type {PropertyDefinition, Workspace} from "../../src/api/contracts";

const LONG_DEFAULT = "本定义为虚构数据，仅用于字段定义默认值的长文本展示测试：默认值在表格中最多显示两行摘要，其余内容通过展开入口读取完整值验证不被截断也不丢失。";
// 36 项虚构定义：前 7 项覆盖同名跨作用域、空默认值与长默认值，其余按序号命名
const BASE_DEFINITIONS: PropertyDefinition[] = [
  {type: "sheetset", name: "项目编号", default_value: "GC-2026-000"},
  {type: "sheetset", name: "工程名称", default_value: ""},
  {type: "sheet", name: "工程名称", default_value: "建筑"},
  {type: "sheet", name: "图幅", default_value: "A1"},
  {type: "sheet", name: "比例", default_value: "1:100"},
  {type: "sheet", name: "专业", default_value: "建筑"},
  {type: "sheet", name: "LongNote", default_value: LONG_DEFAULT},
  ...Array.from({length: 29}, (_, index): PropertyDefinition => ({type: "sheet", name: `属性${String(index + 6).padStart(2, "0")}`, default_value: ""})),
];
const SHEETSET_VALUES: Record<string, string> = {项目编号: "GC-2026-000", 工程名称: "城东安置房一期"};

function definitionsFor(count: number): PropertyDefinition[] {
  return BASE_DEFINITIONS.slice(0, count);
}

// 安装夹具并把打开/刷新响应替换为带虚构定义与图纸集值的工作区；返回草稿 PUT 捕获数组
async function install(page: Page, options: {definitions?: PropertyDefinition[]; initialDraft?: unknown; values?: Record<string, string>} = {}) {
  const draftBodies: unknown[] = [];
  const {workspace} = await installSheetsFixture(page, {
    initialDraft: options.initialDraft,
    onDraftPut: (body) => draftBodies.push(body),
  });
  const modified = JSON.parse(JSON.stringify(workspace)) as Workspace;
  modified.sheet_set.custom_properties = options.values ?? {...SHEETSET_VALUES};
  modified.sheet_set.property_definitions = options.definitions ?? BASE_DEFINITIONS;
  // 后注册的路由优先：打开/刷新均返回虚构定义
  await page.route("**/api/workspaces/open", (route) => route.fulfill({json: modified}));
  await page.route("**/api/workspaces/workspace-1", (route) => route.fulfill({json: modified}));
  return {modified, draftBodies};
}

async function openProperties(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await page.getByRole("tab", {name: "属性"}).click();
  await expect(page.getByRole("textbox", {name: "属性 项目编号"})).toHaveValue("GC-2026-000");
}

async function expandDefinitions(page: Page, rows = 6) {
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  await expect(page.locator(".definition-panel tbody tr")).toHaveCount(rows);
}

function row(page: Page, name: string) {
  return page.locator(".definition-panel tbody tr").filter({hasText: name});
}

function lastCommands(draftBodies: unknown[]) {
  const actions = (draftBodies.at(-1) as {actions: {commands: {type: string}[]}[]}).actions;
  return actions.flatMap((action) => action.commands);
}

const STRUCTURAL_DRAFT = {
  schema_version: 1,
  workspace_id: "workspace-1",
  base_revision_id: "revision-1",
  repair_status: "VALID",
  version: 1,
  cursor: 1,
  actions: [{id: "structural-1", kind: "command_batch", label: "修改标题", commands: [{type: "update_subset_title", subset_id: "subset-1", title: "修订标题"}]}],
};

test("36 个定义默认折叠，展开后每页六条并可翻页", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  // 初始折叠：表格不渲染，标题栏仍显示字段总数
  await expect(page.locator(".definition-panel table")).toHaveCount(0);
  await expect(page.locator(".definition-panel")).toContainText("共 36 项");
  // 展开只显示六条：第一页保持输入顺序，页脚显示匹配总数与页码
  await expandDefinitions(page);
  const names = await page.locator(".definition-panel tbody tr td.col-name").allTextContents();
  expect(names).toEqual(["项目编号", "工程名称", "工程名称", "图幅", "比例", "专业"]);
  await expect(page.locator(".definition-panel .foot-info")).toContainText("匹配 36 项 · 第 1 / 6 页");
  await expect(page.getByRole("button", {name: "上一页"})).toBeDisabled();
  // 翻到最后一页：六条且下一页禁用
  await page.getByRole("button", {name: "下一页"}).click();
  await expect(page.locator(".definition-panel .foot-info")).toContainText("第 2 / 6 页");
  for (let i = 0; i < 4; i += 1) await page.getByRole("button", {name: "下一页"}).click();
  await expect(page.locator(".definition-panel .foot-info")).toContainText("第 6 / 6 页");
  await expect(page.getByRole("button", {name: "下一页"})).toBeDisabled();
  const lastNames = await page.locator(".definition-panel tbody tr td.col-name").allTextContents();
  expect(lastNames).toEqual(["属性29", "属性30", "属性31", "属性32", "属性33", "属性34"]);
});

test("名称与默认值搜索、作用域筛选与页码复位", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  await expandDefinitions(page);
  await page.getByRole("button", {name: "下一页"}).click();
  await expect(page.locator(".definition-panel .foot-info")).toContainText("第 2 / 6 页");
  // 按字段名搜索：回第一页并只显示匹配项
  const query = page.getByRole("searchbox", {name: "搜索字段"});
  await query.fill("属性1");
  await expect(page.locator(".definition-panel .foot-info")).toContainText("匹配 10 项 · 第 1 / 2 页");
  await expect(page.locator(".definition-panel tbody tr td.col-name").first()).toHaveText("属性10");
  // 按默认值搜索：命中「比例」的默认值 1:100
  await query.fill("1:100");
  await expect(page.locator(".definition-panel tbody tr")).toHaveCount(1);
  await expect(page.locator(".definition-panel tbody tr td.col-name")).toHaveText("比例");
  // 作用域筛选与搜索叠加：图纸集作用域内无默认值 1:100 的定义 → 空态与清除查询入口
  await page.getByRole("combobox", {name: "作用域筛选"}).selectOption({label: "图纸集"});
  await expect(page.getByText("没有匹配的字段定义")).toBeVisible();
  await page.getByRole("button", {name: "清除查询"}).click();
  await expect(page.locator(".definition-panel .foot-info")).toContainText("匹配 36 项 · 第 1 / 6 页");
  await expect(query).toHaveValue("");
  // 仅作用域筛选：图纸集两项
  await page.getByRole("combobox", {name: "作用域筛选"}).selectOption({label: "图纸集"});
  await expect(page.locator(".definition-panel tbody tr")).toHaveCount(2);
  await expect(page.locator(".definition-panel tbody tr td.col-name")).toHaveText(["项目编号", "工程名称"]);
});

test("同名跨作用域独立显示", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  await expandDefinitions(page);
  // 两个「工程名称」同时可见：作用域与默认值各自独立，不合并为一行
  const sameRows = page.locator(".definition-panel tbody tr").filter({hasText: "工程名称"});
  await expect(sameRows).toHaveCount(2);
  await expect(sameRows.nth(0).locator("td.col-scope")).toHaveText("图纸集");
  await expect(sameRows.nth(0).locator("td.col-default")).toContainText("（空）");
  await expect(sameRows.nth(1).locator("td.col-scope")).toHaveText("图纸");
  await expect(sameRows.nth(1).locator("td.col-default")).toHaveText("建筑");
  // 作用域筛选下各自出现
  await page.getByRole("combobox", {name: "作用域筛选"}).selectOption({label: "图纸"});
  await expect(page.locator(".definition-panel tbody tr").filter({hasText: "工程名称"})).toHaveCount(1);
});

test("空默认值显示（空），长默认值两行摘要并可展开读取完整值", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  await expandDefinitions(page);
  // 第一页：空默认值显示「（空）」
  await expect(row(page, "工程名称").first().locator("td.col-default")).toContainText("（空）");
  // LongNote 定义在第二页
  await page.getByRole("button", {name: "下一页"}).click();
  await expect(row(page, "LongNote")).toHaveCount(1);
  const longRow = row(page, "LongNote");
  const summary = longRow.locator(".default-text");
  // 两行摘要：webkit-line-clamp=2 截断
  expect(await summary.evaluate((el) => getComputedStyle(el).webkitLineClamp)).toBe("2");
  // 展开读取完整值：键盘可达按钮，展开后解除两行截断且完整文本可读
  const expandButton = longRow.getByRole("button", {name: "展开默认值 图纸 LongNote"});
  await expandButton.click();
  await expect(longRow).toContainText(LONG_DEFAULT);
  expect(await summary.evaluate((el) => getComputedStyle(el).webkitLineClamp)).toBe("none");
  await longRow.getByRole("button", {name: "收起默认值 图纸 LongNote"}).click();
  expect(await summary.evaluate((el) => getComputedStyle(el).webkitLineClamp)).toBe("2");
});

test("新增定义加入草稿并清空输入；与筛选不匹配时提示并提供查看字段", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const {draftBodies} = await install(page);
  await openProperties(page);
  await expandDefinitions(page);
  await page.getByRole("combobox", {name: "作用域筛选"}).selectOption({label: "图纸集"});
  await expect(page.locator(".definition-panel tbody tr")).toHaveCount(2);
  // 新增区仅作用域/名称/默认值
  await page.getByRole("button", {name: "新增字段"}).click();
  const addForm = page.locator(".definition-panel .add-form");
  await expect(addForm.getByLabel("属性作用域")).toBeVisible();
  await expect(addForm.getByLabel("属性名称")).toBeVisible();
  await expect(addForm.getByLabel("默认值")).toBeVisible();
  // 当前筛选（图纸集）与新增的图纸定义不匹配：成功提示 + 查看字段
  await addForm.getByLabel("属性作用域").selectOption({label: "图纸"});
  await addForm.getByLabel("属性名称").fill("备注");
  await addForm.getByLabel("默认值").fill("草稿备注");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const commands = lastCommands(draftBodies);
  expect(commands).toEqual([{type: "add_custom_property", property_type: "sheet", name: "备注", default_value: "草稿备注"}]);
  // 成功后清空输入
  await expect(addForm.getByLabel("属性名称")).toHaveValue("");
  await expect(addForm.getByLabel("默认值")).toHaveValue("");
  const hint = page.locator(".definition-panel .add-hint");
  await expect(hint).toContainText("已加入草稿");
  await hint.getByRole("button", {name: "查看字段"}).click();
  // 查看字段：清除筛选并跳到新增定义所在页，行可见
  await expect(page.locator(".definition-panel .foot-info")).toContainText("匹配 37 项");
  await expect(row(page, "备注").locator("td.col-scope")).toHaveText("图纸");
});

test("新增失败保留输入：名称为空与结构命令分批门禁", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const {draftBodies} = await install(page, {initialDraft: STRUCTURAL_DRAFT});
  await openProperties(page);
  await expandDefinitions(page);
  await page.getByRole("button", {name: "新增字段"}).click();
  const addForm = page.locator(".definition-panel .add-form");
  // 名称未填写：就近字段错误，不产生草稿命令
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.locator(".definition-panel .field-error")).toContainText("属性名称不能为空");
  expect(draftBodies).toHaveLength(0);
  // 存在结构命令：新增返回既有分批提示（App 顶部摘要），输入保留
  await addForm.getByLabel("属性名称").fill("备注");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByText("属性定义与结构变更必须分批预览和执行", {exact: true})).toBeVisible();
  await expect(addForm.getByLabel("属性名称")).toHaveValue("备注");
  await expect(addForm.getByLabel("默认值")).toHaveValue("");
  expect(draftBodies).toHaveLength(0);
});

test("删除定义先确认：文案含作用域与名称且不虚构影响数量；最后一页删除回退", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const {draftBodies} = await install(page, {definitions: definitionsFor(7)});
  await openProperties(page);
  await expandDefinitions(page);
  // 删除按钮可见且 accessible name 含作用域和名称
  await page.getByRole("button", {name: "下一页"}).click();
  const deleteButton = page.getByRole("button", {name: "删除 图纸 属性 LongNote"});
  await expect(deleteButton).toBeVisible();
  await deleteButton.click();
  // 删除确认：说明作用域与名称，不虚构级联影响数量
  const confirm = page.getByRole("dialog", {name: "删除属性定义"});
  await expect(confirm).toContainText("LongNote");
  await expect(confirm).toContainText("图纸");
  expect(await confirm.locator(".modal-message").textContent()).not.toMatch(/\d+ 张|\d+ 个/);
  await confirm.getByRole("button", {name: "取消"}).click();
  expect(draftBodies).toHaveLength(0);
  // 确认后加入删除草稿；当前页消失后回退到最后有效页
  await deleteButton.click();
  await confirm.getByRole("button", {name: "加入删除草稿"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  expect(lastCommands(draftBodies)).toEqual([{type: "delete_custom_property", property_type: "sheet", name: "LongNote"}]);
  await expect(page.locator(".definition-panel .foot-info")).toContainText("匹配 6 项 · 第 1 / 1 页");
  await expect(page.getByRole("button", {name: "删除 图纸 属性 专业"})).toBeVisible();
});

test("删除 sheetset 定义前先处理未提交值：留在此处阻断，放弃后进入确认", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const {draftBodies} = await install(page);
  await openProperties(page);
  await expandDefinitions(page);
  // 对应图纸集值字段存在未提交修改
  await page.getByRole("textbox", {name: "属性 工程名称"}).fill("城东安置房当前输入");
  const deleteButton = page.getByRole("button", {name: "删除 图纸集 属性 工程名称"});
  await deleteButton.click();
  // 先运行属性输入 guard（三选一），未决策前不弹删除确认
  const guardDialog = page.getByRole("dialog", {name: "未提交输入"});
  await expect(guardDialog).toBeVisible();
  await expect(page.getByRole("dialog", {name: "删除属性定义"})).toHaveCount(0);
  await guardDialog.getByRole("button", {name: "留在此处"}).click();
  await expect(guardDialog).toHaveCount(0);
  await expect(page.getByRole("dialog", {name: "删除属性定义"})).toHaveCount(0);
  expect(draftBodies).toHaveLength(0);
  // 放弃输入：输入回到草稿投影，再进入删除确认
  await deleteButton.click();
  await expect(guardDialog).toBeVisible();
  await guardDialog.getByRole("button", {name: "放弃输入"}).click();
  await expect(page.getByRole("textbox", {name: "属性 工程名称"})).toHaveValue("城东安置房一期");
  const confirm = page.getByRole("dialog", {name: "删除属性定义"});
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", {name: "取消"}).click();
  expect(draftBodies).toHaveLength(0);
  // 再次确认：加入删除草稿
  await deleteButton.click();
  await expect(page.getByRole("dialog", {name: "删除属性定义"})).toBeVisible();
  await page.getByRole("dialog", {name: "删除属性定义"}).getByRole("button", {name: "加入删除草稿"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  expect(lastCommands(draftBodies)).toEqual([{type: "delete_custom_property", property_type: "sheetset", name: "工程名称"}]);
  await expect(page.getByRole("textbox", {name: "属性 工程名称"})).toHaveValue("城东安置房一期");
});

test("定义表视觉契约：弱化表头、语义分隔线、单一纵向滚动与无溢出时无冻结阴影", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  await expandDefinitions(page);
  const header = page.locator(".definition-panel th.col-name");
  const body = page.locator(".definition-panel tbody td.col-name").first();
  const headerStyle = await header.evaluate((el) => {
    const css = getComputedStyle(el);
    return {position: css.position, background: css.backgroundColor, border: css.borderBottomColor, borderWidth: css.borderBottomWidth};
  });
  const bodyBackground = await body.evaluate((el) => getComputedStyle(el).backgroundColor);
  // 弱化表头：sticky 且背景与表体不同
  expect(headerStyle.position).toBe("sticky");
  expect(headerStyle.background).not.toBe(bodyBackground);
  expect(headerStyle.background).not.toBe("rgba(0, 0, 0, 0)");
  expect(headerStyle.borderWidth).not.toBe("0px");
  expect(headerStyle.border).not.toBe("rgba(0, 0, 0, 0)");
  // 语义分隔线：列间存在竖向分隔
  const separator = await page.locator(".definition-panel tbody td.col-scope").first().evaluate((el) => getComputedStyle(el).borderLeftWidth);
  expect(separator).not.toBe("0px");
  // 容器只承担横向滚动：内容不产生第二个纵向滚动条
  const scroll = await page.locator(".definition-panel .table-window").evaluate((el) => ({client: el.clientHeight, scroll: el.scrollHeight}));
  expect(scroll.scroll).toBeLessThanOrEqual(scroll.client + 1);
  // 无横向溢出：操作列保持普通列，无冻结阴影
  expect(await page.locator(".definition-panel .table-window").evaluate((el) => el.classList.contains("sticky-actions"))).toBe(false);
  const actionsShadow = await page.locator(".definition-panel th.col-actions").evaluate((el) => getComputedStyle(el).boxShadow);
  expect(actionsShadow).toBe("none");
  // hover 与键盘 focus 状态可区分
  const baseBackground = await body.evaluate((el) => getComputedStyle(el.parentElement!).backgroundColor);
  await body.hover();
  const hoverBackground = await body.evaluate((el) => getComputedStyle(el.parentElement!).backgroundColor);
  expect(hoverBackground).not.toBe(baseBackground);
  await page.getByRole("button", {name: "删除 图纸 属性 专业"}).focus();
  const focusBackground = await body.evaluate((el) => getComputedStyle(el.parentElement!).backgroundColor);
  expect(focusBackground).not.toBe(baseBackground);
});

test("窄视口横向溢出时冻结操作列且整页无横向溢出", async ({page}) => {
  await page.setViewportSize({width: 640, height: 768});
  await install(page);
  await openProperties(page);
  await expandDefinitions(page);
  const windowEl = page.locator(".definition-panel .table-window");
  await expect(windowEl).toHaveClass(/sticky-actions/);
  const actions = await page.locator(".definition-panel th.col-actions").evaluate((el) => {
    const css = getComputedStyle(el);
    return {position: css.position, right: css.right, shadow: css.boxShadow, background: css.backgroundColor};
  });
  expect(actions.position).toBe("sticky");
  expect(parseFloat(actions.right)).toBe(0);
  expect(actions.shadow).not.toBe("none");
  expect(actions.background).not.toBe("rgba(0, 0, 0, 0)");
  // 表格自身横向滚动，不撑破整页
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("新增区与查询控件密度：输入 38px、普通按钮 36px", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  await expandDefinitions(page);
  await page.getByRole("button", {name: "新增字段"}).click();
  const panel = page.locator(".definition-panel");
  const inputHeights = await panel.locator("input, select").evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().height)));
  expect(inputHeights.length).toBeGreaterThanOrEqual(4);
  expect(inputHeights.every((height) => height === 38)).toBe(true);
  // 展开新增区后标题按钮切换为「关闭新增」；普通按钮不低于 36px
  for (const name of ["加入草稿", "关闭新增"]) {
    const height = await panel.getByRole("button", {name}).evaluate((el) => Math.round(el.getBoundingClientRect().height));
    expect(height).toBeGreaterThanOrEqual(36);
  }
  await panel.getByRole("button", {name: "关闭新增"}).click();
  const addButtonHeight = await panel.getByRole("button", {name: "新增字段"}).evaluate((el) => Math.round(el.getBoundingClientRect().height));
  expect(addButtonHeight).toBeGreaterThanOrEqual(36);
});
