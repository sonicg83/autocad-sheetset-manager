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
  const gates = [deferred(), deferred()];
  let previewCalls = 0;
  await page.route("**/api/workspaces/workspace-1/changes/preview", async (route) => {
    const index = previewCalls++;
    await gates[index].promise;
    // 旧代次（第 1 次）投影为 14 张，新代次（第 2 次）投影为 15 张
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
  // 结构动作二：新增一张（已有布局来源）→ 投影请求 #2（新代次，15 张）
  await page.getByRole("combobox", {name: "模板来源"}).selectOption("existing_snapshot");
  await page.getByRole("button", {name: "批量新增图纸"}).click();
  await expect.poll(() => previewCalls).toBe(2);

  // 假路由释放新 generation，再释放旧 generation 后仍显示最新数量
  gates[1].resolve();
  await expect(page.getByText("匹配 15 / 全部 15 张", {exact: true})).toBeVisible();
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

  // 结构动作一：改子集标题（update_subset_title）
  await page.getByLabel("当前子集标题").fill("平面图甲");
  await page.getByRole("button", {name: "加入标题变更"}).click();
  await expect.poll(() => bodies.length).toBe(1);
  // 结构动作二：新增一张（已有布局来源）
  await page.getByRole("combobox", {name: "模板来源"}).selectOption("existing_snapshot");
  await page.getByRole("button", {name: "批量新增图纸"}).click();
  await expect.poll(() => bodies.length).toBe(2);
  // 结构动作三：再次改同一子集标题（与动作一同键）
  await page.getByLabel("当前子集标题").fill("平面图乙");
  await page.getByRole("button", {name: "加入标题变更"}).click();
  await expect.poll(() => bodies.length).toBe(3);

  // 跨结构边界去重不得把动作一压缩掉：insert 之前不得被后续同键命令替代
  const last = bodies[2].commands as Array<{type: string}>;
  expect(last.map((command) => command.type)).toEqual(["update_subset_title", "insert_sheet", "update_subset_title"]);
});
