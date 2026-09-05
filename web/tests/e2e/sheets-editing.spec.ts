// PLAN-DM-015 任务 5：分页编辑缓冲与全局输入保护（SPEC-DM-009 §6.1/§6.2）e2e。
// 覆盖：36 属性 6 页跨页修改与搜索隐藏后仍提交两项、取消不污染 base、切主标签恢复缓冲、
// 加入草稿成功退出并更新既有草稿投影、提交失败保留输入并呈现行内错误与可聚焦摘要、
// 错误摘要跳转到第六页字段、DRAFT_CONFLICT 保留输入提示过期、保存失败重试不重复加入、
// 切换范围/打开另一编辑上下文三选一（加入草稿后继续/放弃输入/留在此处）、
// 全局预览/确认写入先处理未提交输入且旧预览失效需重新预览、删除入口先处理缓冲、
// 基准刷新后编辑失效保留输入禁止提交、键盘焦点恢复、混合批次显示不回退既有属性值。
import {expect, test, type Page} from "@playwright/test";
import {buildPreviewFromBase, installSheetsFixture, previewResponse} from "./fixtures/sheets";

async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
}
// 打开第一行图纸的属性编辑（一次只展开一张图纸）
async function openEditor(page: Page) {
  await page.getByRole("button", {name: "编辑属性"}).first().click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toBeVisible();
}
// 第一行的图幅列单元格（可见列序中自定义属性第一列）
function firstRowPropCell(page: Page, index: number) {
  const row = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("001", {exact: true})});
  return row.locator("td.col-prop").nth(index);
}

test("跨页修改且搜索隐藏后仍提交两项", async ({page}) => {
  const draftBodies: unknown[] = [];
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  await openEditor(page);
  // 第一页修改图幅
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  // 翻到第六页修改另一字段（36 项 / 每页 6 项 = 6 页）
  for (let i = 0; i < 5; i++) await page.getByRole("button", {name: "下一页"}).click();
  await expect(page.getByText("第 6 / 6 页", {exact: true})).toBeVisible();
  await page.getByRole("textbox", {name: "属性 属性36", exact: true}).fill("X36");
  // 页脚显示跨页已修改数
  await expect(page.getByText("已修改 2 项", {exact: true})).toBeVisible();
  // 属性名搜索隐藏全部：翻页/搜索只改变展示，不丢输入
  await page.getByLabel("搜索属性").fill("属性99");
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
  // 提交全部属性页：两项修改都进草稿，不只当前页
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0); // 成功退出编辑
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const actions = (draftBodies[draftBodies.length - 1] as {actions: {commands: {type: string; sheet_id: string; custom_properties: Record<string, string>}[]}[]}).actions;
  const command = actions.flatMap((action) => action.commands).find((item) => item.type === "update_sheet_properties");
  expect(command?.sheet_id).toBe("sheet-1");
  expect(command?.custom_properties["图幅"]).toBe("A2");
  expect(command?.custom_properties["属性36"]).toBe("X36");
});

test("取消不污染 base 且退出编辑", async ({page}) => {
  const draftBodies: unknown[] = [];
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "取消"}).click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
  // base 未被污染：图幅列仍为 A1，草稿无新增命令
  await expect(firstRowPropCell(page, 0)).toHaveText("A1");
  await expect.poll(() => draftBodies.length).toBe(0);
});

test("切主标签保留缓冲与字段，返回后恢复且不触发输入保护", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  // 主标签切换不触发 guard（无三选一模态）、不销毁状态宿主
  await page.getByRole("tab", {name: /属性/}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await page.getByRole("tab", {name: /图纸/}).click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveValue("A2");
});

test("加入草稿成功退出编辑并更新既有草稿投影", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
  // 既有草稿投影更新：表内图幅列显示新值、草稿计数 1/1、行标「待变更」
  await expect(firstRowPropCell(page, 0)).toHaveText("A2");
  await expect(page.getByText(/草稿 1\/1/)).toBeVisible();
  const row = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("001", {exact: true})});
  await expect(row).toContainText("待变更");
});

test("提交失败保留输入并呈现行内错误与可聚焦摘要", async ({page}) => {
  let failures = 1;
  await installSheetsFixture(page, {
    failDraftSave: () => failures-- > 0
      ? {code: "PROPERTY_VALIDATION", message: "属性值校验失败", fields: {"图幅": "值无效"}}
      : null,
  });
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "加入草稿"}).click();
  // 失败保留输入、呈现行内错误与可聚焦摘要，摘要提供字段跳转入口
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveValue("A2");
  await expect(page.getByText("值无效", {exact: true})).toBeVisible();
  await expect(page.getByRole("alert", {name: "加入草稿错误摘要"})).toBeVisible();
  await expect(page.getByRole("button", {name: /图幅：值无效/})).toBeVisible();
});

test("错误摘要跳转到第六页字段并聚焦", async ({page}) => {
  await installSheetsFixture(page, {
    failDraftSave: () => ({code: "PROPERTY_VALIDATION", message: "属性值校验失败", fields: {"属性36": "值无效"}}),
  });
  await openWorkspace(page);
  await openEditor(page);
  // 翻到第六页修改属性36，提交触发第六页字段错误
  for (let i = 0; i < 5; i++) await page.getByRole("button", {name: "下一页"}).click();
  await expect(page.getByText("第 6 / 6 页", {exact: true})).toBeVisible();
  await page.getByRole("textbox", {name: "属性 属性36", exact: true}).fill("X36");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByRole("button", {name: /属性36：值无效/})).toBeVisible();
  // 先翻回第一页，再经错误摘要跳转到第六页对应字段
  for (let i = 0; i < 5; i++) await page.getByRole("button", {name: "上一页"}).click();
  await expect(page.getByText("第 1 / 6 页", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: /属性36：值无效/}).click();
  await expect(page.getByText("第 6 / 6 页", {exact: true})).toBeVisible();
  await expect(page.getByRole("textbox", {name: "属性 属性36", exact: true})).toBeFocused();
});

test("DRAFT_CONFLICT 保存失败保留输入并提示过期", async ({page}) => {
  await installSheetsFixture(page, {
    failDraftSave: () => ({code: "DRAFT_CONFLICT", message: "草稿版本冲突"}),
  });
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "加入草稿"}).click();
  // 冲突：保留输入、显示过期错误提示（草稿已被其他窗口更新）
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveValue("A2");
  await expect(page.getByText("草稿已在其他窗口更新；当前窗口禁止覆盖，请重新打开工作区", {exact: true})).toBeVisible();
});

test("草稿保存失败重试不重复加入同一命令批次", async ({page}) => {
  const draftBodies: unknown[] = [];
  let failures = 1;
  await installSheetsFixture(page, {
    onDraftPut: (body) => draftBodies.push(body),
    failDraftSave: () => failures-- > 0
      ? {code: "PROPERTY_VALIDATION", message: "属性值校验失败", fields: {"图幅": "值无效"}}
      : null,
  });
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByRole("button", {name: /图幅：值无效/})).toBeVisible();
  // 重试（一次性失败已清除）：不再重复加入同一命令批次，仅重试保存
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0); // 成功退出编辑
  await expect.poll(() => draftBodies.length).toBe(2);
  const last = draftBodies[draftBodies.length - 1] as {actions: {commands: {type: string}[]}[]};
  const propertyBatches = last.actions.filter((action) => action.commands[0]?.type === "update_sheet_properties");
  expect(propertyBatches.length).toBe(1);
  await expect(page.getByText(/草稿 1\/1/)).toBeVisible();
});

test("切换范围隐藏编辑对象时三选一：加入草稿后继续并应用切换", async ({page}) => {
  const draftBodies: unknown[] = [];
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  // 点击不含图纸 001 的子集 2（结构施工图）→ 编辑对象将被隐藏 → 提示三选一
  await page.getByRole("treeitem", {name: /结构施工图/}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "加入草稿后继续"}).click();
  // 保存后继续应用范围切换：编辑退出、范围已切到子集 2
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible();
  await expect.poll(() => draftBodies.length).toBe(1);
  const command = (draftBodies[0] as {actions: {commands: {type: string; custom_properties: Record<string, string>}[]}[]})
    .actions[0].commands[0];
  expect(command.type).toBe("update_sheet_properties");
  expect(command.custom_properties["图幅"]).toBe("A2");
});

test("切换范围三选一：放弃输入清空缓冲并应用切换", async ({page}) => {
  const draftBodies: unknown[] = [];
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("treeitem", {name: /结构施工图/}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "放弃输入"}).click();
  // 明确清空缓冲并继续切换：不污染 base、不产生命令
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible();
  await expect.poll(() => draftBodies.length).toBe(0);
});

test("切换范围三选一：留在此处不应用切换且保留编辑", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("treeitem", {name: /结构施工图/}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "留在此处"}).click();
  // 留在此处：范围未切换（仍在全部图纸）、编辑保留
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await expect(page.getByText("匹配 13 / 全部 13 张", {exact: true})).toBeVisible();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveValue("A2");
});

test("打开另一编辑上下文（新增操作）先三选一", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "编辑子集"}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "放弃输入"}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
  // 操作表单随后展开
  await expect(page.getByRole("region", {name: "编辑子集"})).toBeVisible();
});

test("点击全局预览先处理未提交输入且预览包含全部命令", async ({page}) => {
  const previewBodies: {commands: {type: string}[]}[] = [];
  await page.route("**/api/workspaces/workspace-1/changes/preview", async (route) => {
    previewBodies.push(await route.request().postDataJSON());
    await route.fulfill({json: previewResponse(13)});
  });
  await installSheetsFixture(page);
  await openWorkspace(page);
  // 先加入结构命令使「预览变更」可用（无命令时 dock 禁用预览）
  await page.getByRole("button", {name: "编辑子集"}).click();
  await page.getByLabel("当前子集").selectOption("subset-1");
  await page.getByLabel("子集标题").fill("平面图甲");
  await page.getByRole("button", {name: "加入草稿"}).click();
  // 结构提交经草稿保存与投影确认可能发出多次投影请求；只确认内部投影已发生
  await expect.poll(() => previewBodies.length).toBeGreaterThan(0);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "预览变更"}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "加入草稿后继续"}).click();
  // 保存后继续预览：混合批次命令都进入预览体（内部投影与用户预览可能有多次请求，按内容轮询）
  await expect.poll(() => {
    const last = previewBodies[previewBodies.length - 1];
    return last ? last.commands.map((item) => item.type).join(",") : "";
  }).toBe("update_subset_title,update_sheet_properties");
  // 任务浮层「修改预览」页签自动展开
  await expect(page.getByRole("tab", {name: /修改预览/})).toHaveAttribute("aria-selected", "true");
});

test("确认写入先处理未提交输入：保存后旧预览失效必须重新预览", async ({page}) => {
  const previewBodies: {commands: {type: string}[]}[] = [];
  let executed = false;
  await page.route("**/api/workspaces/workspace-1/changes/preview", async (route) => {
    previewBodies.push(await route.request().postDataJSON());
    await route.fulfill({json: previewResponse(13)});
  });
  await page.route("**/api/workspaces/workspace-1/changes/execute", async (route) => { executed = true; return route.fulfill({json: {}}); });
  await installSheetsFixture(page);
  await openWorkspace(page);
  // 先加入结构命令并预览，得到有效可执行预览上下文
  await page.getByRole("button", {name: "编辑子集"}).click();
  await page.getByLabel("当前子集").selectOption("subset-1");
  await page.getByLabel("子集标题").fill("平面图甲");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await page.getByRole("button", {name: "预览变更"}).click();
  await expect(page.getByRole("button", {name: "确认写入"})).toBeEnabled();
  // 预览抽屉覆盖主表，先通过真实入口收起再编辑。
  await page.getByRole("button", {name: "收起任务浮层"}).click();
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "确认写入"}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "加入草稿后继续"}).click();
  // 保存使旧预览失效：write 不能捕获旧 context 执行，必须重新预览
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "确认写入"})).toBeDisabled();
  await expect(page.getByText("请先预览", {exact: true})).toBeVisible();
  expect(executed).toBeFalsy();
});

test("编辑未提交时点击删除先处理缓冲，删除命令不夹带属性变更", async ({page}) => {
  const draftBodies: unknown[] = [];
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => route.fulfill({json: previewResponse(12)}));
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  const row = page.locator(".sheet-table-window tbody tr").filter({has: page.getByText("001", {exact: true})});
  await row.getByRole("button", {name: "删除", exact: true}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "加入草稿后继续"}).click();
  // 保存后再走删除确认流程
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await expect(page.getByRole("dialog", {name: "删除图纸"})).toBeVisible();
  await page.getByRole("button", {name: "加入删除草稿"}).click();
  // 两个独立批次：属性编辑 + 删除；删除命令不带 custom_properties
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const actions = (draftBodies[draftBodies.length - 1] as {actions: {commands: {type: string}[]}[]}).actions;
  expect(actions.map((action) => action.commands[0].type)).toEqual(["update_sheet_properties", "delete_sheet"]);
});

test("删除整个子集先处理未提交输入：加入草稿后继续进入整子集删除确认", async ({page}) => {
  const draftBodies: unknown[] = [];
  const {workspace} = await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => {
    const body = route.request().postDataJSON();
    route.fulfill({json: buildPreviewFromBase(workspace, body.commands)});
  });
  await openWorkspace(page);
  // 打开编辑子集表单并修改标题（产生未提交输入）
  await page.getByRole("button", {name: "编辑子集"}).click();
  await expect(page.getByRole("region", {name: "编辑子集"})).toBeVisible();
  await page.getByLabel("当前子集").selectOption("subset-1");
  await page.getByLabel("子集标题").fill("平面图甲");
  // 点击删除整个子集 → 先三选一处理缓冲，再进入整子集删除确认流程
  await page.getByRole("button", {name: "删除整个子集"}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "加入草稿后继续"}).click();
  // 缓冲已保存后进入整子集删除确认（不可逆强确认），此时尚未真正删除
  await expect(page.getByRole("dialog", {name: "删除整个子集"})).toBeVisible();
  await page.getByRole("dialog", {name: "删除整个子集"}).getByRole("button", {name: "取消", exact: true}).click();
  // 草稿只含标题变更批次，未夹带删除命令
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const actions = (draftBodies[draftBodies.length - 1] as {actions: {commands: {type: string}[]}[]}).actions;
  expect(actions.map((action) => action.commands[0].type)).toEqual(["update_subset_title"]);
});

test("删除整个子集三选一：留在此处时子集删除不发生", async ({page}) => {
  const draftBodies: unknown[] = [];
  await installSheetsFixture(page, {onDraftPut: (body) => draftBodies.push(body)});
  await openWorkspace(page);
  await page.getByRole("button", {name: "编辑子集"}).click();
  await expect(page.getByRole("region", {name: "编辑子集"})).toBeVisible();
  await page.getByLabel("当前子集").selectOption("subset-1");
  await page.getByLabel("子集标题").fill("平面图甲");
  await page.getByRole("button", {name: "删除整个子集"}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toBeVisible();
  await page.getByRole("button", {name: "留在此处"}).click();
  // 留在此处：不进入整子集删除确认、不产生删除命令，编辑保留
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  await expect(page.getByRole("dialog", {name: "删除整个子集"})).toHaveCount(0);
  await expect(page.getByLabel("子集标题")).toHaveValue("平面图甲");
  await expect.poll(() => draftBodies.length).toBe(0);
});

test("基准刷新后编辑失效保留输入供核对且禁止提交", async ({page}) => {
  let revisionOverride = "revision-1";
  await installSheetsFixture(page, {
    failDraftSave: () => ({code: "DRAFT_CONFLICT", message: "草稿版本冲突"}),
    transformWorkspaceGet: (workspace: unknown) => ({...(workspace as object), revision_id: revisionOverride}),
  });
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  // 保存触发 DRAFT_CONFLICT → 提示过期
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByText("草稿已在其他窗口更新；当前窗口禁止覆盖，请重新打开工作区", {exact: true})).toBeVisible();
  // 冲突重载：服务端返回新基准 revision-2 → 编辑上下文失效
  await page.getByRole("button", {name: /草稿 1\/1/}).click();
  await page.getByRole("button", {name: "放弃本地冲突动作并重新加载"}).click();
  await expect(page.getByRole("dialog", {name: "放弃冲突动作并重新加载"})).toBeVisible();
  revisionOverride = "revision-2";
  await page.getByRole("button", {name: "确定放弃冲突动作并重新加载"}).click();
  // 失效缓冲保留可见输入供核对，禁止提交到新基准
  await expect(page.getByText(/编辑上下文已失效/)).toBeVisible();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveValue("A2");
  await expect(page.getByRole("button", {name: "加入草稿"})).toBeDisabled();
});

test("关闭编辑器后焦点回到触发按钮", async ({page}) => {
  await installSheetsFixture(page);
  await openWorkspace(page);
  const editButton = page.getByRole("button", {name: "编辑属性"}).first();
  await editButton.click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toBeVisible();
  await page.getByRole("button", {name: "取消"}).click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
  await expect(editButton).toBeFocused();
});

test("混合批次显示不回退既有图纸属性值", async ({page}) => {
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => route.fulfill({json: previewResponse(14)}));
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
  await expect(firstRowPropCell(page, 0)).toHaveText("A2");
  // 加入结构命令（新增图纸）→ 混合批次：derived_document 不含值编辑合成，
  // 显示以命令簿叠加，既有图纸属性值不回退
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByRole("combobox", {name: "模板来源"}).selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByText("匹配 14 / 全部 14 张", {exact: true})).toBeVisible();
  await expect(firstRowPropCell(page, 0)).toHaveText("A2");
});

test("保存中切换范围：等保存完成后切换且不重复提示", async ({page}) => {
  let releaseSave = () => {};
  const saveGate = new Promise<void>((resolve) => { releaseSave = resolve; });
  await page.route("**/api/workspaces/workspace-1/draft", async (route) => {
    if (route.request().method() === "PUT") await saveGate;
    await route.continue();
  });
  await installSheetsFixture(page);
  await openWorkspace(page);
  await openEditor(page);
  await page.getByRole("textbox", {name: "属性 图幅", exact: true}).fill("A2");
  await page.getByRole("button", {name: "加入草稿"}).click();
  // 保存挂起期间切换范围：不重复提示，等待保存完成后再切换
  await page.getByRole("treeitem", {name: /结构施工图/}).click();
  await expect(page.getByRole("dialog", {name: "未提交输入"})).toHaveCount(0);
  releaseSave();
  await expect(page.getByText("匹配 3 / 全部 3 张", {exact: true})).toBeVisible();
  await expect(page.getByRole("textbox", {name: "属性 图幅", exact: true})).toHaveCount(0);
});
