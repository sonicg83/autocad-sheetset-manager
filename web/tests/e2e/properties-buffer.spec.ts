// PLAN-DM-016 任务 2：属性页会话缓冲、提交生命周期与统一输入保护 e2e（SPEC-DM-010 §5.4、SPEC-DM-009 §6.2）。
// 覆盖：直接编辑只进缓冲不产生草稿命令、标签切换与折叠保留输入、隐藏修改一次完整加入草稿、
// 提交失败保留输入与字段错误、撤回仅回到草稿投影、关闭/预览/确认写入/CSV 导入统一触发三选一。
import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";
import type {Workspace} from "../../src/api/contracts";

const SHEETSET_VALUES: Record<string, string> = {项目号: "P-FAKE", 工程名称: "一期工程", 编号: "001"};

// 在公共夹具上补齐图纸集自定义属性（工程名称/编号），其余结构与默认夹具一致
function withSheetsetValues(base: Workspace): Workspace {
  const clone = JSON.parse(JSON.stringify(base)) as Workspace;
  clone.sheet_set.custom_properties = {...SHEETSET_VALUES};
  clone.sheet_set.property_definitions = [
    {type: "sheetset", name: "项目号", default_value: "P-FAKE"},
    {type: "sheetset", name: "工程名称", default_value: ""},
    {type: "sheetset", name: "编号", default_value: ""},
    ...clone.sheet_set.property_definitions.filter((item) => item.type === "sheet"),
  ];
  return clone;
}

// 安装夹具并把打开/刷新响应替换为带图纸集值的版本；返回草稿 PUT 捕获数组
async function install(page: Page, options: Parameters<typeof installSheetsFixture>[1] = {}) {
  const draftBodies: unknown[] = [];
  const {workspace} = await installSheetsFixture(page, {...options, onDraftPut: (body) => draftBodies.push(body)});
  const modified = withSheetsetValues(workspace);
  // 后注册的路由优先：打开/刷新均返回带图纸集属性值的工作区
  await page.route("**/api/workspaces/open", (route) => route.fulfill({json: modified}));
  await page.route("**/api/workspaces/workspace-1", (route) => route.fulfill({json: modified}));
  return {modified, draftBodies};
}

async function openProperties(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
  await page.getByRole("tab", {name: "属性"}).click();
  await expect(page.getByLabel("属性 工程名称")).toHaveValue("一期工程");
}

function guardDialog(page: Page) {
  return page.getByRole("dialog", {name: "未提交输入"});
}

// 图纸集名称独立输入框（PLAN-DM-016 任务 3 起在值面板内，exact 避免命中「值对照 图纸集名称」等按钮）
function nameInput(page: Page) {
  return page.getByLabel("图纸集名称", {exact: true});
}

test("直接编辑只进入缓冲：不产生草稿命令，标签切换保留输入", async ({page}) => {
  const {draftBodies} = await install(page);
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("二期");
  // 未提交：不产生草稿命令（不 PUT 草稿），workspace 名称不被输入污染
  expect(draftBodies).toHaveLength(0);
  await expect(nameInput(page)).toHaveValue("虚构图纸集");
  // 切换主标签：会话缓冲保留（折叠保留由任务 6 面板标题折叠覆盖）
  await page.getByRole("tab", {name: "图纸"}).click();
  await page.getByRole("tab", {name: "属性"}).click();
  await expect(page.getByLabel("属性 工程名称")).toHaveValue("二期");
  await page.locator(".draft-chip").click();
  await expect(page.getByText("动作 0/0")).toBeVisible();
});

test("隐藏的修改一次完整加入草稿：单个 update_sheet_set 携带完整名称与值映射", async ({page}) => {
  const {draftBodies} = await install(page);
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("二期");
  await page.getByLabel("属性 编号").fill("002");
  // 搜索其他字段隐藏两项修改后提交（搜索不丢弃隐藏修改）
  await page.getByRole("searchbox", {name: "搜索属性值"}).fill("项目号");
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const actions = (draftBodies.at(-1) as {actions: {commands: {type: string}[]}[]}).actions;
  const commands = actions.flatMap((action) => action.commands).filter((item) => item.type === "update_sheet_set");
  expect(commands).toHaveLength(1);
  const command = commands[0] as {name: string; custom_properties: Record<string, string>};
  expect(command.name).toBe("虚构图纸集");
  // 一次完整提交：完整映射包含未修改项（计划断言意图，选择器按实现适配）
  expect(command.custom_properties).toEqual(expect.objectContaining({工程名称: "二期", 编号: "002", 项目号: "P-FAKE"}));
  // 成功后输入以草稿投影重建：值保持且可继续编辑
  await page.getByRole("button", {name: "清除搜索"}).click();
  await expect(page.getByLabel("属性 工程名称")).toHaveValue("二期");
  await expect(page.getByLabel("属性 编号")).toHaveValue("002");
});

test("提交失败保留输入并呈现字段错误", async ({page}) => {
  await install(page, {
    failDraftSave: () => ({code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {name: "图纸集名称已存在"}}),
  });
  await openProperties(page);
  await page.getByLabel("图纸集名称", {exact: true}).fill("重复名称");
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect(page.getByRole("alert")).toContainText("草稿保存失败");
  await expect(page.getByText("图纸集名称已存在")).toBeVisible();
  await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("重复名称");
});

test("撤回仅回到草稿投影：已提交值保持，不回到正式基准", async ({page}) => {
  const {draftBodies} = await install(page);
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("二期");
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  await page.getByLabel("属性 工程名称").fill("三期");
  await page.getByRole("button", {name: "撤回 工程名称"}).click();
  // 回到草稿投影值「二期」，不是正式基准值「一期工程」
  await expect(page.getByLabel("属性 工程名称")).toHaveValue("二期");
});

test("关闭工作区先触发属性三选一：留在此处不关闭，加入草稿后进入关闭确认", async ({page}) => {
  const {draftBodies} = await install(page);
  await openProperties(page);
  await page.getByLabel("属性 编号").fill("002");
  await page.getByRole("button", {name: "关闭"}).click();
  const dialog = guardDialog(page);
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "留在此处"}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
  expect(draftBodies).toHaveLength(0);
  // 加入草稿后继续：等待保存与投影后再进入既有关闭确认
  await page.getByRole("button", {name: "关闭"}).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "加入草稿后继续"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const confirm = page.locator('[role="dialog"][aria-modal="true"]');
  await expect(confirm).toContainText(/确定关闭并放弃当前改动/);
  await confirm.getByRole("button", {name: "取消"}).click();
  await expect(page.getByLabel("属性 编号")).toHaveValue("002");
});

test("预览先处理属性输入：留在此处阻断，加入草稿后继续放行", async ({page}) => {
  const {draftBodies} = await install(page);
  const previewBodies: unknown[] = [];
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => {
    previewBodies.push(route.request().postDataJSON());
    return route.fulfill({json: {workspace_id: "workspace-1", base_revision_id: "revision-1", cad_version: "2020", preview_digest: "digest-buffer", executable: true, requires_cad: false, changes: [], diagnostics: [], affected_files: [], semantic_diff: {structure: {before: [], after: []}, properties: [], dwgs: []}, execution_intent: null}});
  });
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("二期");
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  await page.getByLabel("属性 编号").fill("002");
  await page.getByRole("tab", {name: "图纸"}).click();
  await page.getByRole("button", {name: "预览变更"}).click();
  const dialog = guardDialog(page);
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "留在此处"}).click();
  expect(previewBodies).toHaveLength(0);
  await page.getByRole("button", {name: "预览变更"}).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "加入草稿后继续"}).click();
  await expect.poll(() => previewBodies.length).toBe(1);
});

test("确认写入先处理属性输入三选一：留在此处不进入发布确认", async ({page}) => {
  const {draftBodies} = await install(page);
  const previewBodies: unknown[] = [];
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => {
    previewBodies.push(route.request().postDataJSON());
    return route.fulfill({json: {workspace_id: "workspace-1", base_revision_id: "revision-1", cad_version: "2020", preview_digest: "digest-write", executable: true, requires_cad: false, changes: [], diagnostics: [], affected_files: [], semantic_diff: {structure: {before: [], after: []}, properties: [], dwgs: []}, execution_intent: null}});
  });
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("二期");
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  await page.getByRole("tab", {name: "图纸"}).click();
  await page.getByRole("button", {name: "预览变更"}).click();
  await expect.poll(() => previewBodies.length).toBe(1);
  await page.getByRole("tab", {name: "属性"}).click();
  await page.getByLabel("属性 编号").fill("002");
  await page.getByRole("button", {name: "确认写入"}).click();
  const dialog = guardDialog(page);
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "留在此处"}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText(/确认发布/)).toHaveCount(0);
});

test("确认导入先处理属性输入三选一且 CSV 不被自动保存", async ({page}) => {
  const {draftBodies} = await install(page);
  const importBodies: unknown[] = [];
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => route.fulfill({json: {executable: true, changes: [{line: 2, action: "add", type: "sheet", name: "专业", default_value: "燃气"}], diagnostics: [], affected_files: ["test.dst"], execution_intent: null}}));
  await page.route("**/api/workspaces/workspace-1/custom-properties/import", (route) => {
    importBodies.push(route.request().postDataJSON());
    return route.fulfill({json: {id: "job-csv", status: "QUEUED", progress: 0, attempt: 1, files: []}});
  });
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("二期");
  // 任务 5 起 CSV 区经「导入 / 导出」菜单按需展开，不常驻文件选择器
  await page.getByRole("button", {name: "导入 / 导出"}).click();
  await page.getByRole("button", {name: "导入 CSV"}).click();
  await page.getByLabel("属性 CSV 文件").setInputFiles({name: "properties.csv", mimeType: "text/csv", buffer: Buffer.from("type,name,default_value\nsheet,专业,燃气\n", "utf8")});
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await page.getByRole("button", {name: "确认导入"}).click();
  const dialog = guardDialog(page);
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "留在此处"}).click();
  expect(importBodies).toHaveLength(0);
  // 加入草稿后继续：属性输入入草稿，再进入既有强确认，CSV 不自动执行
  await page.getByRole("button", {name: "确认导入"}).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "加入草稿后继续"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const confirm = page.locator('[role="dialog"][aria-modal="true"]');
  await expect(confirm).toContainText(/确认导入/);
  expect(importBodies).toHaveLength(0);
  await confirm.getByRole("button", {name: "取消"}).click();
});
