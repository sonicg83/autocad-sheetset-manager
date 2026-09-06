// PLAN-DM-016 任务 6：属性页页面组合、状态摘要、折叠恢复与错误跳转 e2e（SPEC-DM-010 P-01~P-14）。
// 覆盖：默认组合（定义折叠/值展开）、面板标题折叠后仍显示字段/dirty/pending/error/CSV 状态、
// 错误摘要展开目标面板并聚焦字段、切主标签保留会话态、切工作区重置为定义折叠/值展开、
// 无值/无定义/查询无结果空态区分、无自定义值仍展示名称与新增 sheetset 字段入口、
// 共享夹具上的完整提交命令（三选一 guard 生命周期由 properties-buffer.spec 覆盖）。
import {expect, test, type Page} from "@playwright/test";
import {installPropertiesFixture, openProperties, pendingDraft, SHEETSET_VALUES} from "./fixtures/properties";

const SECOND_DST = "C:\\虚构工程\\乙工程\\第二套图纸集.dst";

async function collapseValuePanel(page: Page) {
  await page.getByRole("button", {name: "收起图纸集属性值"}).click();
  await expect(page.getByRole("button", {name: "展开图纸集属性值"})).toBeVisible();
}
async function expandValuePanel(page: Page) {
  await page.getByRole("button", {name: "展开图纸集属性值"}).click();
  await expect(page.getByRole("button", {name: "收起图纸集属性值"})).toBeVisible();
}
// CSV 面板展开后「导入 CSV」常驻（2026-09-06 取消二级菜单，与 properties-csv.spec 同一口径）
async function openCsvFlow(page: Page) {
  await page.getByRole("button", {name: "导入 CSV"}).click();
  await expect(page.getByLabel("属性 CSV 文件")).toBeVisible();
}

test("默认组合：定义折叠显示字段总数、值展开平铺 33 项、CSV 状态在标题栏", async ({page}) => {
  await installPropertiesFixture(page);
  await openProperties(page);
  // 定义面板默认折叠：标题栏仍显示字段总数
  const definitionHead = page.locator(".definition-panel .panel-head");
  await expect(definitionHead).toContainText("共 36 项");
  await expect(page.locator(".definition-panel .panel-body")).toHaveCount(0);
  // 值面板默认展开：名称 + 33 项原顺序平铺
  await expect(page.locator(".value-panel .panel-body")).toBeVisible();
  await expect(page.locator(".value-panel .value-item input")).toHaveCount(34);
  await expect(page.getByLabel("属性 项目编号")).toHaveValue(SHEETSET_VALUES["项目编号"]);
  await expect(page.getByLabel("属性 设计说明")).toHaveValue(SHEETSET_VALUES["设计说明"]);
  // CSV 面板标题栏状态
  await expect(page.locator(".csv-panel .panel-head")).toContainText("CSV：未选择文件");
});

test("面板标题折叠后仍显示字段/dirty/pending/error/CSV 状态", async ({page}) => {
  await installPropertiesFixture(page, {
    initialDraft: pendingDraft(),
    failDraftSave: () => ({code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {name: "图纸集名称已存在", "工程名称": "工程名称与既有图纸集冲突"}}),
  });
  await openProperties(page);
  // pending：草稿值待写入；dirty：本地编辑未加入草稿
  await expect(page.getByLabel("属性 项目编号")).toHaveValue("GC-2026-DRAFT");
  await page.getByLabel("属性 工程名称").fill("城东安置房二期");
  // 提交失败产生错误摘要与字段错误（命令已入草稿栈但保存失败：工程名称随投影变为待写入）
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect(page.locator(".properties-view .error-summary")).toContainText("草稿保存失败");
  // 再编辑一个未受影响字段：dirty 与 pending 并存
  await page.getByLabel("属性 版本号").fill("C");
  // 折叠值面板：标题栏仍显示 dirty/pending/error 计数与加入草稿摘要
  await collapseValuePanel(page);
  const valueHead = page.locator(".value-panel .panel-head");
  await expect(valueHead).toContainText("未加入草稿 1 项");
  await expect(valueHead).toContainText("待写入 2 项");
  await expect(valueHead).toContainText("错误 2 项");
  await expect(valueHead).toContainText("加入草稿：共 1 项");
  await expect(page.locator(".value-panel .panel-body")).toHaveCount(0);
  // 折叠 CSV 面板：选择文件后标题栏仍显示 CSV 状态
  await page.getByRole("button", {name: "收起属性导入导出"}).click();
  await expect(page.locator(".csv-panel .panel-head")).toContainText("CSV：未选择文件");
  // 折叠定义面板：标题栏仍显示字段总数
  await expect(page.locator(".definition-panel .panel-head")).toContainText("共 36 项");
});

test("错误摘要展开目标面板并聚焦字段；重新提交成功后摘要消失", async ({page}) => {
  let failNext = true;
  await installPropertiesFixture(page, {
    failDraftSave: () => failNext ? {code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {"工程名称": "工程名称与既有图纸集冲突"}} : null,
  });
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("城东安置房二期");
  await page.getByRole("button", {name: "更新图纸集"}).click();
  const summary = page.locator(".properties-view .error-summary");
  await expect(summary).toContainText("草稿保存失败");
  await expect(summary.getByRole("button", {name: "工程名称：工程名称与既有图纸集冲突"})).toBeVisible();
  // 折叠值面板后点击摘要字段项：目标面板展开且字段获得焦点
  await collapseValuePanel(page);
  await summary.getByRole("button", {name: "工程名称：工程名称与既有图纸集冲突"}).click();
  await expect(page.locator(".value-panel .panel-body")).toBeVisible();
  await expect(page.getByLabel("属性 工程名称")).toBeFocused();
  // 输入保留；修正后重新提交成功，摘要与字段错误消失
  await expect(page.getByLabel("属性 工程名称")).toHaveValue("城东安置房二期");
  failNext = false;
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect(summary).toHaveCount(0);
  await expect(page.locator(".value-panel .field-error")).toHaveCount(0);
});

test("切主标签保留折叠/查询/分页/导入区会话态（P-09）", async ({page}) => {
  await installPropertiesFixture(page);
  await openProperties(page);
  // 展开定义面板、查询、翻到第二页、折叠值面板、打开 CSV 导入区
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  await page.getByRole("searchbox", {name: "搜索字段"}).fill("图幅");
  await expect(page.locator(".definition-panel tbody tr")).toHaveCount(1);
  await page.getByRole("searchbox", {name: "搜索字段"}).fill("");
  await expect(page.locator(".definition-panel .foot-info")).toContainText("第 1 / 6 页");
  await page.getByRole("button", {name: "下一页"}).click();
  await expect(page.locator(".definition-panel .foot-info")).toContainText("第 2 / 6 页");
  await collapseValuePanel(page);
  await openCsvFlow(page);
  // 切到图纸页再回来：全部会话态保留
  await page.getByRole("tab", {name: "图纸"}).click();
  await page.getByRole("tab", {name: "属性"}).click();
  await expect(page.locator(".definition-panel .foot-info")).toContainText("第 2 / 6 页");
  await expect(page.locator(".value-panel .panel-body")).toHaveCount(0);
  await expect(page.getByLabel("属性 CSV 文件")).toBeVisible();
  await expandValuePanel(page);
});

test("切工作区重置：定义折叠、值展开、导入区关闭、查询清空", async ({page}) => {
  await installPropertiesFixture(page, {secondWorkspace: {dstPath: SECOND_DST, id: "workspace-2"}});
  await openProperties(page);
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  await page.getByRole("searchbox", {name: "搜索字段"}).fill("图幅");
  await collapseValuePanel(page);
  await openCsvFlow(page);
  // 关闭并打开另一工作区：会话态重置为定义折叠、值展开、导入区关闭
  await page.getByRole("button", {name: "关闭工作区"}).click();
  await page.evaluate((path) => { (window as any).__fakeSelectResult = path; }, SECOND_DST);
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("tab", {name: "属性"})).toBeVisible({timeout: 5000});
  await page.getByRole("tab", {name: "属性"}).click();
  await expect(page.locator(".definition-panel .panel-body")).toHaveCount(0);
  await expect(page.locator(".definition-panel .panel-head")).toContainText("共 36 项");
  await expect(page.locator(".value-panel .panel-body")).toBeVisible();
  await expect(page.locator(".value-panel .value-item input")).toHaveCount(34);
  await expect(page.getByLabel("属性 CSV 文件")).toBeHidden();
});

test("无自定义值仍展示名称并提供新增 sheetset 字段入口；定义/查询空态区分", async ({page}) => {
  await installPropertiesFixture(page, {noValues: true});
  await openProperties(page);
  // 名称仍展示；无值空态提供新增 sheetset 字段入口
  await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("虚构图纸集");
  const valueEmpty = page.locator(".value-panel .empty-values");
  await expect(valueEmpty).toBeVisible();
  await valueEmpty.getByRole("button", {name: "新增图纸集字段"}).click();
  // 入口展开定义面板并打开新增区，作用域预置为图纸集
  await expect(page.locator(".definition-panel .panel-body")).toBeVisible();
  await expect(page.getByLabel("属性作用域")).toHaveValue("sheetset");
  await expect(page.getByLabel("属性名称")).toBeFocused();
  // 定义面板空态（无定义）与查询无结果空态文案不同
  await page.getByRole("searchbox", {name: "搜索字段"}).fill("不存在字段");
  await expect(page.getByText("没有匹配的字段定义")).toBeVisible();
});

test("无定义与查询无结果采用不同空态", async ({page}) => {
  // 无定义空态：0 定义时提示使用「新增字段」
  await installPropertiesFixture(page, {definitionsCount: 0, noValues: true});
  await openProperties(page);
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  await expect(page.getByText("没有属性定义；使用「新增字段」创建第一个字段。")).toBeVisible();
  // 查询无结果空态：有定义但查询不命中，提供「清除查询」
  await installPropertiesFixture(page);
  await openProperties(page);
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  await page.getByRole("searchbox", {name: "搜索字段"}).fill("不存在字段名");
  await expect(page.locator(".definition-panel tbody tr")).toHaveCount(0);
  await expect(page.getByText("没有匹配的字段定义")).toBeVisible();
  await page.getByRole("button", {name: "清除查询"}).click();
  await expect(page.locator(".definition-panel tbody tr")).toHaveCount(6);
});

test("共享夹具完整提交：隐藏修改一次加入单个 update_sheet_set 命令", async ({page}) => {
  const {draftBodies} = await installPropertiesFixture(page);
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("城东安置房二期");
  await page.getByLabel("属性 车位数量").fill("900");
  await page.getByRole("searchbox", {name: "搜索属性值"}).fill("项目编号");
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const actions = (draftBodies.at(-1) as {actions: {commands: {type: string}[]}[]}).actions;
  const commands = actions.flatMap((action) => action.commands).filter((item) => item.type === "update_sheet_set");
  expect(commands).toHaveLength(1);
  const command = commands[0] as {name: string; custom_properties: Record<string, string>};
  expect(command.name).toBe("虚构图纸集");
  expect(Object.keys(command.custom_properties)).toHaveLength(33);
  expect(command.custom_properties).toEqual(expect.objectContaining({工程名称: "城东安置房二期", 车位数量: "900", 设计说明: SHEETSET_VALUES["设计说明"]}));
});
