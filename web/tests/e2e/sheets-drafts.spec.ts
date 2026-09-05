// PLAN-DM-015 任务 7：批量、删除及草稿动作联动（SPEC-DM-009 §4.2/§6.1/§6.3）e2e。
// 覆盖：跨范围批量只改指定字段并保留其他字段、设置值空输入不生成命令、
// 清空值显式确认受影响数量、单删移除并取消勾选、撤销恢复但不恢复勾选、
// 删除/撤销计数联动（简报 verbatim）、删除整个子集强确认字段不变、
// 结构表单服务端失败保留输入。
import {expect, test, type Page} from "@playwright/test";
import {buildPreviewFromBase, installSheetsFixture, installSmartPreview} from "./fixtures/sheets";

async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
}
// 智能投影：删除等结构命令派生权威文档，既有对象沿用基底 ID
async function smartPreview(page: Page, workspace: unknown) {
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => {
    const body = route.request().postDataJSON();
    route.fulfill({json: buildPreviewFromBase(workspace as Parameters<typeof buildPreviewFromBase>[0], body.commands)});
  });
}
// 最近一次草稿 PUT 中的属性命令（按 sheet_id 匹配）
function lastPropertyCommands(body: unknown, sheetIds: string[]) {
  const actions = (body as {actions: {commands: {type: string; sheet_id: string; custom_properties: Record<string, string>}[]}[]}).actions;
  return actions
    .flatMap((action) => action.commands)
    .filter((item) => item.type === "update_sheet_properties" && sheetIds.includes(item.sheet_id));
}

test("跨范围两张批量只改指定字段并保留其他字段", async ({page}) => {
  const draftBodies: unknown[] = [];
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  // 选择子集 1 的 sheet-1 与子集 2 的 sheet-4（跨子集范围）
  await page.getByLabel("选择图纸 001").check();
  await page.getByLabel("选择图纸 004").check();
  await expect(page.getByText("已选 2 张，其中 0 张不在当前结果", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "批量修改属性"}).click();
  await page.getByLabel("既有图纸属性").selectOption("比例");
  await page.getByLabel("批量值").fill("1:200");
  await page.getByRole("button", {name: "批量加入草稿"}).click();
  // 提交摘要提示完整数量与跨子集范围
  await expect(page.getByRole("status").filter({hasText: "批量更新 比例（2 张 / 2 个子集）"})).toBeVisible();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const commands = lastPropertyCommands(draftBodies[draftBodies.length - 1], ["sheet-1", "sheet-4"]);
  expect(commands.map((item) => item.sheet_id)).toEqual(["sheet-1", "sheet-4"]);
  for (const command of commands) {
    expect(command.custom_properties["比例"]).toBe("1:200"); // 只改指定字段
    expect(command.custom_properties["图幅"]).toBe("A1");     // 保留其他字段
    expect(command.custom_properties["专业"]).toBe("建筑");
  }
});

test("设置值空输入不生成命令且仅提示", async ({page}) => {
  const draftBodies: unknown[] = [];
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  await page.getByLabel("选择图纸 001").check();
  await page.getByRole("button", {name: "批量修改属性"}).click();
  await page.getByLabel("既有图纸属性").selectOption("比例");
  // 值留空（set 模式默认）→ 只提示、不生成命令
  await page.getByRole("button", {name: "批量加入草稿"}).click();
  await expect(page.getByText(/批量设置为空值不会生成修改/)).toBeVisible();
  await expect.poll(() => draftBodies.length).toBe(0);
});

test("清空值须显式确认受影响数量且只清指定字段", async ({page}) => {
  const draftBodies: unknown[] = [];
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  await page.getByLabel("选择图纸 001").check();
  await page.getByLabel("选择图纸 004").check();
  await page.getByRole("button", {name: "批量修改属性"}).click();
  await page.getByLabel("批量模式").selectOption("clear");
  await page.getByLabel("既有图纸属性").selectOption("比例");
  await page.getByRole("button", {name: "清空所选属性"}).click();
  // 显式确认：受影响数量 2 张
  const modal = page.getByRole("dialog", {name: "清空属性值"});
  await expect(modal).toBeVisible();
  await expect(modal.getByText(/将清空 2 张/)).toBeVisible();
  await modal.getByRole("button", {name: "确定清空"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const commands = lastPropertyCommands(draftBodies[draftBodies.length - 1], ["sheet-1", "sheet-4"]);
  expect(commands).toHaveLength(2);
  for (const command of commands) {
    expect(command.custom_properties["比例"]).toBe(""); // 清空设空字符串
    expect(command.custom_properties["图幅"]).toBe("A1"); // 其他字段保留
  }
});

test("单张删除加入草稿后从投影表与勾选集合移除", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await smartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByLabel("选择图纸 001").check();
  await expect(page.getByText(/已选 1 张/)).toBeVisible();
  await page.getByRole("button", {name: "删除", exact: true}).first().click();
  await page.getByRole("button", {name: "加入删除草稿", exact: true}).click();
  // 投影表移除行
  await expect(page.getByText("匹配 12 / 全部 12 张", {exact: true})).toBeVisible();
  // 已从勾选集合移除（选择条消失）
  await expect(page.getByText(/已选 1 张/)).toHaveCount(0);
  // 反馈：加入删除草稿 toast
  await expect(page.getByRole("status").filter({hasText: "已加入删除草稿"})).toBeVisible();
});

test("撤销恢复图纸但不自动恢复勾选（含简报 verbatim 计数联动）", async ({page}) => {
  const {workspace} = await installSheetsFixture(page);
  await smartPreview(page, workspace);
  await openWorkspace(page);
  await page.getByLabel("选择图纸 001").check();
  // 简报 verbatim 断言
  await page.getByRole("button", {name: "删除", exact: true}).first().click();
  await page.getByRole("button", {name: "加入删除草稿", exact: true}).click();
  await expect(page.getByText("匹配 12 / 全部 12 张", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "撤销", exact: true}).click();
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
  // 撤销恢复图纸但不自动恢复勾选（S-12）
  await expect(page.getByLabel("选择图纸 001")).not.toBeChecked();
});

test("删除整个子集强确认字段不变且声明影响 DWG 与外部引用", async ({page}) => {
  const previewBodies: {commands: Record<string, unknown>[]}[] = [];
  const {workspace} = await installSheetsFixture(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => {
    const body = route.request().postDataJSON();
    previewBodies.push(body);
    route.fulfill({json: buildPreviewFromBase(workspace, body.commands)});
  });
  await openWorkspace(page);
  await page.getByRole("button", {name: "编辑子集"}).click();
  await page.getByLabel("当前子集").selectOption("subset-1");
  await page.getByRole("button", {name: "删除整个子集"}).click();
  const modal = page.getByRole("dialog", {name: "删除整个子集"});
  await expect(modal).toBeVisible();
  // 强确认要素：不可逆 + 影响 DWG + 外部引用声明（SPEC-DM-005 语义不变）
  await expect(modal.getByText("不可逆", {exact: true})).toBeVisible();
  await expect(modal.getByText(/及主 DWG：/)).toBeVisible();
  await expect(modal.getByText(/系统不会证明工程外部引用/)).toBeVisible();
  await modal.getByRole("checkbox").check();
  await modal.getByRole("button", {name: /确定删除整个子集/}).click();
  // 命令保持 confirm_delete_all_sheets/confirm_delete_main_dwg
  await expect.poll(() => previewBodies.length).toBeGreaterThan(0);
  const last = previewBodies[previewBodies.length - 1].commands;
  expect(last).toEqual([{type: "delete_subset", subset_id: "subset-1", confirm_delete_all_sheets: true, confirm_delete_main_dwg: true}]);
});

test("结构表单服务端失败保留完整输入且不展示为已创建", async ({page}) => {
  await installSheetsFixture(page, {
    failDraftSave: () => ({code: "PROPERTY_VALIDATION", message: "草稿保存失败", fields: {}}),
  });
  await openWorkspace(page);
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  // 服务端保存失败：表单保留、呈现错误、不展示为已创建
  await expect(page.getByText("草稿保存失败", {exact: true})).toBeVisible();
  await expect(page.getByRole("region", {name: "新增图纸"})).toBeVisible();
  await expect(page.getByLabel("参照图纸")).toHaveValue("sheet-1");
  await expect(page.getByLabel("模板来源")).toHaveValue("existing_snapshot");
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
});

test("撤销后重提交相同命令批次重新入栈且撤销/重做栈状态正确", async ({page}) => {
  const draftBodies: unknown[] = [];
  const {workspace} = await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await installSmartPreview(page, workspace);
  await openWorkspace(page);
  // 第一次提交：新增图纸（参照 sheet-1、existing_snapshot）批次 X 入栈，cursor=1
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  await expect(page.getByText("匹配 4 / 全部 4 张", {exact: true})).toBeVisible();
  await expect(page.getByText(/草稿 1\/1/)).toBeVisible();
  // 撤销：cursor=0，X 仍在数组尾部（重提交去重误吞的复现前提），匹配数恢复
  await page.getByRole("button", {name: "撤销", exact: true}).click();
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible();
  await expect(page.getByText(/草稿 0\/1/)).toBeVisible();
  // 重新打开编辑器输入相同值并提交：不得被 sameBatch 去重误吞，批次必须重新入栈
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿", exact: true}).click();
  // 批次重新入栈且匹配数再次改变；撤销/重做栈状态正确（新批次 cursor=1、actions=1）
  await expect(page.getByText("匹配 4 / 全部 4 张", {exact: true})).toBeVisible();
  await expect(page.getByText(/草稿 1\/1/)).toBeVisible();
  await expect(page.getByRole("button", {name: "重做", exact: true})).toBeDisabled();
  // 草稿请求体确认：重提交批次已重新入栈（cursor=1、含插入命令），非静默丢弃
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const lastBody = draftBodies[draftBodies.length - 1] as {cursor: number; actions: {commands: {type: string}[]}[]};
  expect(lastBody.cursor).toBe(1);
  expect(lastBody.actions.map((action) => action.commands[0].type)).toEqual(["insert_sheet"]);
  // 新批次独立可撤销/重做：撤销回基底（3/3）、重做恢复新增（4/4）
  await page.getByRole("button", {name: "撤销", exact: true}).click();
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "重做", exact: true}).click();
  await expect(page.getByText("匹配 4 / 全部 4 张", {exact: true})).toBeVisible();
});
