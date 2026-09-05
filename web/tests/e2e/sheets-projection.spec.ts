// 任务 1：权威结构投影与命令身份验证（先行门禁）。
// 结构变化经内部 /changes/preview 的 execution_intent.derived_document 显示，
// 与用户显式发布预览分离：投影请求不得启用「确认写入」，逆序响应只应用最新代次。
import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture, previewResponse} from "./fixtures/sheets";

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return {promise, resolve};
}

async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.evaluate((path) => { (window as any).__fakeSelectResult = path; }, "C:\\虚构工程\\图纸集.dst");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByRole("button", {name: "关闭"})).toBeVisible();
}

test("结构投影内部请求不启用确认写入，且逆序响应只应用最新代次", async ({page}) => {
  const gates = [deferred(), deferred(), deferred()];
  let previewCalls = 0;
  await page.route("**/api/workspaces/workspace-1/changes/preview", async (route) => {
    const index = previewCalls++;
    await gates[index].promise;
    // 旧代次（删除，第 1 次）投影为 14 张；新增后的两次投影请求（第 2/3 次）均为 15 张
    await route.fulfill({json: previewResponse(index === 0 ? 14 : 15)});
  });
  await installSheetsFixture(page, {sheetCount: 15});
  await openWorkspace(page);

  // 投影请求不得使「确认写入」启用
  await expect(page.getByRole("button", {name: "确认写入"})).toBeDisabled();
  await expect(page.getByText("匹配 15 / 全部 15 张", {exact: true})).toBeVisible();

  // 结构动作一：删除首张图纸 → 投影请求 #1（旧代次，14 张）
  await page.getByRole("button", {name: "删除", exact: true}).first().click();
  await page.getByRole("button", {name: "确认删除"}).click();
  // 结构动作二：新增一张（已有布局来源）→ 表单提交经草稿保存与投影确认，共发出两次投影请求（新代次，15 张）
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByRole("combobox", {name: "模板来源"}).selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect.poll(() => previewCalls).toBe(3);

  // 假路由先释放最新代次（第 3 次），再释放旧代次后仍显示最新数量
  gates[2].resolve();
  await expect(page.getByText("匹配 15 / 全部 15 张", {exact: true})).toBeVisible();
  gates[1].resolve();
  gates[0].resolve();
  await expect(page.getByText("匹配 15 / 全部 15 张", {exact: true})).toBeVisible();
  await expect(page.getByText("匹配 14 / 全部 14 张", {exact: true})).not.toBeVisible();
  await expect(page.getByRole("button", {name: "确认写入"})).toBeDisabled();
});

test("结构动作之间不跨边界去重压缩，服务端命令索引保持稳定", async ({page}) => {
  const bodies: any[] = [];
  await page.route("**/api/workspaces/workspace-1/changes/preview", async (route) => {
    bodies.push(await route.request().postDataJSON());
    await route.fulfill({json: previewResponse(15)});
  });
  await installSheetsFixture(page, {sheetCount: 15});
  await openWorkspace(page);

  // 结构提交经草稿保存与投影确认会产生多次投影请求，按最新请求体内容断言命令序列
  // 结构动作一：改子集标题（update_subset_title）；任务 6 起编辑子集先选择编辑对象
  await page.getByRole("button", {name: "编辑子集"}).click();
  await page.getByLabel("当前子集").selectOption("subset-1");
  await page.getByLabel("子集标题").fill("平面图甲");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect.poll(() => lastCommands(bodies)).toBe("update_subset_title");
  // 结构动作二：新增一张（已有布局来源）→ 切换为「新增图纸」表单（一次只出现一种）
  await page.getByRole("button", {name: "新增图纸"}).click();
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByRole("combobox", {name: "模板来源"}).selectOption("existing_snapshot");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect.poll(() => lastCommands(bodies)).toBe("update_subset_title,insert_sheet");
  // 结构动作三：再次改同一子集标题（与动作一同键）→ 切回「编辑子集」表单
  // 动作二定位后范围已在子集 1：编辑子集单子集范围预填编辑对象，无需再选择
  await page.getByRole("button", {name: "编辑子集"}).click();
  await page.getByLabel("子集标题").fill("平面图乙");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect.poll(() => lastCommands(bodies)).toBe("update_subset_title,insert_sheet,update_subset_title");

  // 跨结构边界去重不得把动作一压缩掉：insert 之前不得被后续同键命令替代
  const last = bodies[bodies.length - 1].commands as Array<{type: string}>;
  expect(last.map((command) => command.type)).toEqual(["update_subset_title", "insert_sheet", "update_subset_title"]);
});

test("撤销结构动作后早期返回恢复 pending：旧在途响应被丢弃且可再次投影", async ({page}) => {
  const gates = [deferred()];
  let previewCalls = 0;
  await page.route("**/api/workspaces/workspace-1/changes/preview", async (route) => {
    const index = previewCalls++;
    if (index === 0) await gates[0].promise; // 第一个结构请求在途被 gate
    await route.fulfill({json: previewResponse(14)});
  });
  await installSheetsFixture(page, {sheetCount: 15});
  await openWorkspace(page);
  await expect(page.getByText("匹配 15 / 全部 15 张", {exact: true})).toBeVisible();

  // 结构动作一：删除首张 → 内部投影请求在途（pending=true）
  await page.getByRole("button", {name: "删除", exact: true}).first().click();
  await page.getByRole("button", {name: "确认删除"}).click();
  await expect.poll(() => previewCalls).toBe(1);

  // 立即撤销 → 早期返回：不得再发新请求，pending 恢复 false，旧在途响应因代次失效被丢弃
  await page.getByRole("button", {name: "撤销"}).click();
  await expect.poll(() => previewCalls).toBe(1);
  gates[0].resolve();
  await expect(page.getByText("匹配 15 / 全部 15 张", {exact: true})).toBeVisible();
  await expect(page.getByText("匹配 14 / 全部 14 张", {exact: true})).not.toBeVisible();

  // 结构动作二：再次删除 → 重新投影成功，不受旧在途请求影响
  await page.getByRole("button", {name: "删除", exact: true}).first().click();
  await page.getByRole("button", {name: "确认删除"}).click();
  await expect.poll(() => previewCalls).toBe(2);
  await expect(page.getByText("匹配 14 / 全部 14 张", {exact: true})).toBeVisible();
});

test("持久草稿恢复：跨结构边界同键命令不被去重压缩，命令序列保持", async ({page}) => {
  const bodies: any[] = [];
  await page.route("**/api/workspaces/workspace-1/changes/preview", async (route) => {
    bodies.push(await route.request().postDataJSON());
    await route.fulfill({json: previewResponse(15)});
  });
  const initialDraft = {
    schema_version: 1,
    workspace_id: "workspace-1",
    base_revision_id: "revision-1",
    repair_status: "VALID",
    version: 1,
    cursor: 3,
    actions: [
      {id: "action-1", kind: "command_batch", label: "改子集标题", commands: [{type: "update_subset_title", subset_id: "subset-1", title: "平面图甲"}]},
      {id: "action-2", kind: "command_batch", label: "新增图纸", commands: [{type: "insert_sheet", target_subset_id: "subset-1", ordinal: 1, placement: "after", count: 1, source: {type: "existing_snapshot"}}]},
      {id: "action-3", kind: "command_batch", label: "再改子集标题", commands: [{type: "update_subset_title", subset_id: "subset-1", title: "平面图乙"}]},
    ],
  };
  await installSheetsFixture(page, {sheetCount: 15, initialDraft});
  await openWorkspace(page);

  // 持久草稿恢复提示：3 条待处理
  await expect(page.getByText("已恢复上次未完成的改动（3 条待处理）")).toBeVisible();
  // 内部投影请求携带跨边界命令序列：两个同键 update_subset_title 不得跨 insert 被去重压缩
  await expect.poll(() => bodies.length).toBe(1);
  const commands = bodies[0].commands as Array<{type: string}>;
  expect(commands.map((command) => command.type)).toEqual(["update_subset_title", "insert_sheet", "update_subset_title"]);
  expect(commands.map((command) => (command as any).subset_id ?? (command as any).target_subset_id)).toEqual(["subset-1", "subset-1", "subset-1"]);
});

// 最近一次投影请求体的命令类型序列（结构提交会产生多次投影请求，按最新内容断言）
function lastCommands(bodies: {commands: {type: string}[]}[]): string {
  return (bodies.at(-1)?.commands ?? []).map((command) => command.type).join(",");
}
