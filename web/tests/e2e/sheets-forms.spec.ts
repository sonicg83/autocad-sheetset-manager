// PLAN-DM-015 任务 6：三类操作表单与参照位置映射（SPEC-DM-009 §6.3）e2e。
// 覆盖：单子集预填/全部必须选择、变目标清参照、删除参照需重选、同 ID 顺序变化重新映射、
// 空子集禁用新增、空集新子集 ordinal=1、基础与布局模板分离、成功定位派生新增对象、
// 失败保留输入、编辑子集全部范围先选择编辑对象、成功保留筛选并提示目标隐藏。
import {expect, test, type Page} from "@playwright/test";
import {buildPreviewFromBase, installSheetsFixture, installSmartPreview} from "./fixtures/sheets";

async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
}

test("新增图纸单子集范围预填目标子集", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("treeitem", {name: /结构施工图/}).click();
  await page.getByRole("button", {name: "新增图纸"}).click();
  await expect(page.getByRole("region", {name: "新增图纸"})).toBeVisible();
  await expect(page.getByLabel("目标子集")).toHaveValue("subset-2");
});

test("新增图纸全部范围必须明确选择目标子集且失败保留输入", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("button", {name: "新增图纸"}).click();
  await expect(page.getByRole("region", {name: "新增图纸"})).toBeVisible();
  await expect(page.getByLabel("目标子集")).toHaveValue("");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  await expect(page.getByRole("alert")).toHaveText("请选择目标子集");
  await expect(page.getByRole("region", {name: "新增图纸"})).toBeVisible();
});

test("新增图纸变目标后清除不属于新目标的参照", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await expect(page.getByLabel("参照图纸")).toHaveValue("sheet-1");
  // sheet-1 属于子集 1，切到子集 2 后参照必须清除（不静默保留旧参照）
  await page.getByLabel("目标子集").selectOption("subset-2");
  await expect(page.getByLabel("参照图纸")).toHaveValue("");
});

test("删除参照后加入草稿需重选且保留表单输入", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  // 先删除 sheet-1（表单未打开，无输入保护）
  const row = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("001", {exact: true})});
  await row.getByRole("button", {name: "删除", exact: true}).click();
  await page.getByRole("button", {name: "加入删除草稿"}).click();
  await expect(page.getByText("匹配 12 / 全部 12 张", {exact: true})).toBeVisible();
  // 撤销删除 → sheet-1 恢复
  await page.getByRole("button", {name: "撤销"}).click();
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
  // 打开新增图纸并选择参照 sheet-1
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  // 重做删除 → 投影移除 sheet-1，参照失效（表单仍打开）
  await page.getByRole("button", {name: "重做"}).click();
  await expect(page.getByText("匹配 12 / 全部 12 张", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  // 参照已失效：保留表单并要求重选，不静默替换对象（参照选项已随删除消失，select 回到占位值）
  await expect(page.getByText("参照图纸已失效，请重新选择", {exact: true})).toBeVisible();
  await expect(page.getByRole("region", {name: "新增图纸"})).toBeVisible();
  await expect(page.getByLabel("参照图纸")).toHaveValue("");
  await expect(page.getByLabel("模板来源")).toHaveValue("existing_snapshot");
});

test("同 ID 顺序变化后按当前投影重新映射 ordinal", async ({page}) => {
  const previewBodies: {commands: {type: string; ordinal?: number; placement?: string}[]}[] = [];
  const {workspace} = await installSheetsFixture(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => {
    const body = route.request().postDataJSON();
    previewBodies.push(body);
    route.fulfill({json: buildPreviewFromBase(workspace, body.commands)});
  });
  await openWorkspace(page);
  // 第一次：参照 sheet-1（ordinal 1），之前插入 1 张；成功后定位到子集 1（4 张）
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("图纸方向").selectOption("before");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  await expect(page.getByText("匹配 4 / 全部 4 张", {exact: true})).toBeVisible();
  // 撤销 → 恢复子集 1 的 3 张（定位后范围在子集 1）
  await page.getByRole("button", {name: "撤销"}).click();
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible();
  // 第二次：单子集范围预填目标子集 1；重做后 sheet-1 已移到 ordinal 2，提交应映射到当前序号而非旧序号
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await page.getByRole("button", {name: "重做"}).click();
  await expect(page.getByText("匹配 4 / 全部 4 张", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  await expect(page.getByText("匹配 5 / 全部 5 张", {exact: true})).toBeVisible();
  // 最后一条命令为 insert_sheet ordinal=2（sheet-1 已在第 2 位），不是旧 ordinal 1
  const last = previewBodies[previewBodies.length - 1].commands;
  const inserts = last.filter((command) => command.type === "insert_sheet");
  expect(inserts).toHaveLength(2);
  expect(inserts[0]).toMatchObject({ordinal: 1, placement: "before"});
  expect(inserts[1]).toMatchObject({ordinal: 2, placement: "after"});
});

test("空子集无可用参照时禁用新增并提示流程不可用", async ({page}) => {
  const {workspace} = await installSheetsFixture(page, {sheetCount: 3, subsetCount: 5});
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-4"); // 空分册 4
  await expect(page.getByText("当前子集没有可用图纸参照，新增流程不可用", {exact: true})).toBeVisible();
  await expect(page.getByLabel("参照图纸")).toBeDisabled();
  await expect(page.getByRole("button", {name: "加入草稿", exact: true})).toBeDisabled();
});

test("空图纸集新建首个子集沿用 ordinal=1 且不展示参照", async ({page}) => {
  const previewBodies: {commands: Record<string, unknown>[]}[] = [];
  const {workspace} = await installSheetsFixture(page, {empty: true});
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => {
    const body = route.request().postDataJSON();
    previewBodies.push(body);
    route.fulfill({json: buildPreviewFromBase(workspace, body.commands)});
  });
  await page.route("**/api/layout-names", (route) => route.fulfill({json: {layouts: ["A1模板"], cached: false, file_hash: "x"}}));
  await openWorkspace(page);
  await page.getByRole("button", {name: "创建首个子集"}).click();
  const subsetForm = page.getByRole("region", {name: "新建子集"});
  await expect(subsetForm).toBeVisible();
  await expect(subsetForm.getByText("创建首个子集", {exact: true})).toBeVisible();
  await expect(page.getByLabel("参照子集")).toHaveCount(0);
  await page.getByLabel("子集标题", {exact: true}).fill("首册");
  await page.getByLabel("初始图纸数").fill("1");
  await page.evaluate(() => {(window as any).__fakeSelectResult = "C:\\base.dwt";});
  await page.getByRole("button", {name: "选择基础模板文件"}).click();
  await page.evaluate(() => {(window as any).__fakeSelectResult = "C:\\template.dwt";});
  await page.getByRole("button", {name: "选择布局模板文件"}).click();
  await expect(page.getByRole("combobox", {name: /布局模板名称/})).toBeEnabled();
  await page.getByRole("combobox", {name: /布局模板名称/}).selectOption("A1模板");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  const command = previewBodies[previewBodies.length - 1].commands[0];
  expect(command).toMatchObject({
    type: "insert_subset", ordinal: 1, placement: "after", title: "首册", initial_sheet_count: 1,
    base_template_file: "C:\\base.dwt",
  });
  expect(command.source).toEqual({type: "template_layout", file: "C:\\template.dwt", layout: "A1模板"});
  await expect(page.getByText("匹配 1 / 全部 1 张", {exact: true})).toBeVisible();
});

test("新建子集基础与布局模板分开标注且各自独立选择", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await page.route("**/api/layout-names", (route) => route.fulfill({json: {layouts: ["A1模板"], cached: false, file_hash: "x"}}));
  await openWorkspace(page);
  await page.getByRole("button", {name: "新建子集"}).click();
  await expect(page.getByRole("button", {name: "选择基础模板文件"})).toBeVisible();
  await expect(page.getByRole("button", {name: "选择布局模板文件"})).toBeVisible();
  await page.evaluate(() => {(window as any).__fakeSelectResult = "C:\\base.dwt";});
  await page.getByRole("button", {name: "选择基础模板文件"}).click();
  await expect(page.getByText("C:\\base.dwt", {exact: true})).toBeVisible();
  await page.evaluate(() => {(window as any).__fakeSelectResult = "C:\\template.dwt";});
  await page.getByRole("button", {name: "选择布局模板文件"}).click();
  await expect(page.getByRole("combobox", {name: /布局模板名称/})).toBeEnabled();
  // 布局选择不回填基础模板：两个文件独立显示
  await expect(page.getByText("C:\\base.dwt", {exact: true})).toBeVisible();
  await expect(page.getByText("C:\\template.dwt", {exact: true})).toBeVisible();
});

test("新增图纸成功后关闭表单并定位到派生新增对象", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-2");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  // 表单关闭并定位到新增对象所在范围（子集 1，4 张）
  await expect(page.getByRole("region", {name: "新增图纸"})).toHaveCount(0);
  await expect(page.getByText("匹配 4 / 全部 4 张", {exact: true})).toBeVisible();
  // 新增 ID 从派生结果取得（sheet-der-*），不是按计数拼造 sheet-14
  await expect(page.getByText("派生图纸 3", {exact: true})).toBeVisible();
});

test("新增图纸失败保留完整输入且不展示为已创建", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("新增图纸数量").fill("0");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  await expect(page.getByText("新增图纸数量必须为正整数", {exact: true})).toBeVisible();
  await expect(page.getByRole("region", {name: "新增图纸"})).toBeVisible();
  await expect(page.getByLabel("参照图纸")).toHaveValue("sheet-1");
  await expect(page.getByLabel("新增图纸数量")).toHaveValue("0");
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
});

test("编辑子集全部范围先选择编辑对象", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("button", {name: "编辑子集"}).click();
  await expect(page.getByRole("region", {name: "编辑子集"})).toBeVisible();
  // 全部范围：未选择编辑对象时提交被拒且删除整个子集危险入口禁用（任务 7 修：不静默无操作）
  await expect(page.getByRole("button", {name: "删除整个子集"})).toBeDisabled();
  await page.getByLabel("子集标题").fill("平面图甲");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  await expect(page.getByText("请选择要编辑的子集", {exact: true})).toBeVisible();
  // 选择编辑对象后缓冲重置为该子集当前标题，危险入口可用
  await page.getByLabel("当前子集").selectOption("subset-2");
  await expect(page.getByLabel("子集标题")).toHaveValue("结构施工图");
  await expect(page.getByRole("button", {name: "删除整个子集"})).toBeEnabled();
});

test("同类操作入口点击不触发三选一且表单保留", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("button", {name: "编辑子集"}).click();
  await page.getByLabel("当前子集").selectOption("subset-1");
  await page.getByLabel("子集标题").fill("平面图甲");
  // 再次点击同类入口：同一表单已打开，先短路不重开、不触发三选一（任务 7 修）
  await page.getByRole("button", {name: "编辑子集"}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await expect(page.getByLabel("子集标题")).toHaveValue("平面图甲");
});

test("编辑子集单子集范围预填当前子集且标题可改", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByRole("treeitem", {name: /结构施工图/}).click();
  await page.getByRole("button", {name: "编辑子集"}).click();
  await expect(page.getByRole("region", {name: "编辑子集"})).toBeVisible();
  // 单子集范围：编辑对象选择器预填当前子集，标题预填
  await expect(page.getByLabel("当前子集")).toHaveValue("subset-2");
  await expect(page.getByLabel("子集标题")).toHaveValue("结构施工图");
  await page.getByLabel("子集标题").fill("结构施工图甲");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  await expect(page.getByRole("region", {name: "编辑子集"})).toHaveCount(0);
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible();
});

test("新增成功后保留筛选并提示目标被隐藏，可清除定位", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  // 搜索只匹配 001，新增对象不匹配 → 定位时提示目标被筛选隐藏
  await page.getByLabel("搜索图纸").fill("001");
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  await expect(page.getByText("目标被筛选隐藏", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "清除筛选并定位"}).click();
  await expect(page.getByText("目标被筛选隐藏", {exact: true})).toHaveCount(0);
});
