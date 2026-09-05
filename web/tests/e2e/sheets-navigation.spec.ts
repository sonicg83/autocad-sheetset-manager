// PLAN-DM-015 任务 3：统一范围与单表导航（SPEC-DM-009 §4）e2e。
// 覆盖：唯一业务表与初始范围、全部范围/子集范围切换、树点击图纸定位不勾选、
// 筛选隐藏目标提示、161 项首屏 80 与全选覆盖未加载结果、切范围保留勾选集合、
// 取消全选只取消当前匹配、投影删除对象修剪选择并提示、隐藏属性/完整路径搜索、
// 低频筛选展开与条件标签、空集引导、无结果清除入口、阻断与待变更并存。
import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture, previewResponse} from "./fixtures/sheets";

async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
}

test("单表初始范围", async ({page}) => {
  await installSheetsFixture(page);
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("table", {name: "图纸表格"})).toHaveCount(1);
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
});

test("点击子集切换范围：全部 13 张、子集 3 张，全部图纸只切范围", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await expect(page.getByRole("table", {name: "图纸表格"})).toHaveCount(1);
  await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(13);
  // 点击树中子集 1（1-3 建筑施工图）→ 主表仅显示该子集 3 张
  await page.getByRole("treeitem", {name: /建筑施工图/}).click();
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible();
  await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(3);
  // 点击全部图纸 → 只切换主表范围，不展开行编辑、不自动勾选
  await page.getByRole("treeitem", {name: /全部图纸/}).click();
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
  await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(13);
});

test("点击树中图纸切换到所属子集并定位且不自动勾选", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await page.getByRole("treeitem", {name: "002 图纸 2"}).click();
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible(); // 已切到子集 1
  const row = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("002", {exact: true})});
  await expect(row).toBeVisible();
  // 定位行高亮，但勾选框未被勾选（点击树不自动勾选）
  await expect(row).toHaveClass(/focused/);
  await expect(row.getByRole("checkbox")).not.toBeChecked();
});

test("筛选排除目标时显示目标被筛选隐藏并可清除筛选定位", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  // 搜索只命中图纸 5 → 目标 002（子集 1）被筛选排除
  await page.getByLabel("搜索图纸").fill("图纸 5");
  await expect(page.getByText("匹配 1 / 全部 13 张", {exact: true})).toBeVisible();
  await page.getByRole("treeitem", {name: "002 图纸 2"}).click();
  // 提示目标被筛选隐藏，条件不被暗中清除
  await expect(page.getByText("目标被筛选隐藏", {exact: true})).toBeVisible();
  await expect(page.getByLabel("搜索图纸")).toHaveValue("图纸 5");
  // 清除筛选并定位 → 002 行可见且高亮
  await page.getByRole("button", {name: "清除筛选并定位"}).click();
  await expect(page.getByLabel("搜索图纸")).toHaveValue("");
  const row = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("002", {exact: true})});
  await expect(row).toBeVisible();
  await expect(row).toHaveClass(/focused/);
});

test("161 项大列表首屏 80 行且全选覆盖未加载结果", async ({page}) => {
  await installSheetsFixture(page, {sheetCount: 161});
  await openWorkspace(page);
  await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(80);
  await expect(page.getByText("匹配 161 / 全部 161 张", {exact: true})).toBeVisible();
  await expect(page.getByText("已加载 80 行", {exact: true})).toBeVisible();
  // 全选覆盖全部匹配项（161），而非仅已渲染的 80 行
  await page.getByRole("button", {name: "全选当前结果"}).click();
  await expect(page.getByText("已选 161 张，其中 0 张不在当前结果", {exact: true})).toBeVisible();
  // 继续加载 → 已加载计数随可见行更新
  await page.getByRole("button", {name: /继续加载/}).click();
  await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(160);
  await expect(page.getByText("已加载 160 行", {exact: true})).toBeVisible();
});

test("切范围保留勾选集合且取消全选只移除当前匹配", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await page.getByRole("button", {name: "全选当前结果"}).click();
  await expect(page.getByText("已选 13 张，其中 0 张不在当前结果", {exact: true})).toBeVisible();
  // 切到子集 1（3 张）：勾选集合保留，10 张不在当前结果
  await page.getByRole("treeitem", {name: /建筑施工图/}).click();
  await expect(page.getByText("已选 13 张，其中 10 张不在当前结果", {exact: true})).toBeVisible();
  // 取消全选只移除当前 3 张匹配
  await page.getByRole("button", {name: "取消全选当前结果"}).click();
  await expect(page.getByText("已选 10 张，其中 10 张不在当前结果", {exact: true})).toBeVisible();
  // 回到全部图纸：仍保留 10 张
  await page.getByRole("treeitem", {name: /全部图纸/}).click();
  await expect(page.getByText("已选 10 张，其中 0 张不在当前结果", {exact: true})).toBeVisible();
});

test("投影删除的对象从勾选集合移除并提示", async ({page}) => {
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => route.fulfill({json: previewResponse(12)}));
  await installSheetsFixture(page);
  await openWorkspace(page);
  await page.getByRole("button", {name: "全选当前结果"}).click();
  await expect(page.getByText("已选 13 张，其中 0 张不在当前结果", {exact: true})).toBeVisible();
  // 删除第一张图纸（结构动作）→ 权威投影返回 12 张 → 选择集合修剪 1 张并提示
  await page.getByRole("button", {name: "删除", exact: true}).first().click();
  await page.getByRole("button", {name: "加入删除草稿"}).click();
  await expect(page.getByText("已从选择中移除 1 张已删除图纸", {exact: true})).toBeVisible();
  await expect(page.getByText("已选 12 张，其中 0 张不在当前结果", {exact: true})).toBeVisible();
});

test("全局搜索覆盖隐藏自定义属性与完整路径", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  // 仅存在于 custom_properties 的隐藏属性值（表格无属性列）
  await page.getByLabel("搜索图纸").fill("特殊隐藏值X7");
  await expect(page.getByText("匹配 1 / 全部 13 张", {exact: true})).toBeVisible();
  await expect(page.getByText("007", {exact: true})).toBeVisible();
  // 完整路径（全部 DWG 均含虚构工程目录）
  await page.getByLabel("搜索图纸").fill("虚构工程");
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
});

test("搜索默认作用于当前范围，可切换为搜索全部图纸", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  // 切到子集 1（3 张），图纸 5 不在其中 → 当前范围 0 匹配
  await page.getByRole("treeitem", {name: /建筑施工图/}).click();
  await page.getByLabel("搜索图纸").fill("图纸 5");
  await expect(page.getByText("匹配 0 / 全部 3 张", {exact: true})).toBeVisible();
  // 「搜索全部图纸」→ 跨子集命中图纸 5
  await page.getByLabel("搜索全部图纸").check();
  await expect(page.getByText("匹配 1 / 全部 13 张", {exact: true})).toBeVisible();
});

test("低频筛选在筛选切换后展开且条件以可清除标签展示", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await expect(page.getByRole("combobox", {name: "路径状态"})).toHaveCount(0); // 默认折叠
  await page.getByRole("button", {name: "筛选"}).click();
  await page.getByRole("combobox", {name: "路径状态"}).selectOption("resolved");
  // 生效条件以可清除标签展示
  await expect(page.getByRole("button", {name: "清除筛选：路径已解析"})).toBeVisible();
  await page.getByRole("button", {name: "清除全部筛选"}).click();
  await expect(page.getByRole("combobox", {name: "路径状态"})).toHaveValue("all");
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
});

test("空图纸集显示新建首个子集引导", async ({page}) => {
  await installSheetsFixture(page, {empty: true});
  await openWorkspace(page);
  await expect(page.getByText(/图纸集为空/)).toBeVisible();
  await expect(page.getByRole("button", {name: "创建首个子集"})).toBeVisible();
});

test("筛选无结果显示原因与清除入口，不渲染无说明空表头", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await page.getByLabel("搜索图纸").fill("不存在的图纸XYZ");
  await expect(page.getByText("无匹配图纸", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "清除筛选"}).click();
  await expect(page.getByLabel("搜索图纸")).toHaveValue("");
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
});

test("阻断与待变更并存显示，不相互遮盖", async ({page}) => {
  await installSheetsFixture(page, {dualStatus: true});
  await openWorkspace(page);
  // sheet-1：阻断 + 待变更并存；sheet-3：仅阻断
  const row1 = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("001", {exact: true})});
  await expect(row1).toContainText("待变更");
  await expect(row1).toContainText("阻断");
  const row3 = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("003", {exact: true})});
  await expect(row3).toContainText("阻断");
  await expect(row3).not.toContainText("待变更");
});
