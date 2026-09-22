// 标准库主从分栏 e2e（PLAN-DM-035 Task 8 / SPEC-DM-016 §5–§6）。
// 标准端点经 fixtures/standards 的 route mock 驱动，断言停留在语义层：空库与筛选
// 无结果的区分、官方/已发布只读边界、草稿可维护、派生新草稿、加载失败与导入碰撞
// 不改变选中、900×768 分级视图无横向溢出。
import {expect, test} from "@playwright/test";
import {draft, draftDocument, installStandards, libraryItems, openStandards, published} from "./fixtures/standards";

test.beforeEach(async ({page}) => {
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => (window as any).__fakeSelectResult ?? null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
});

test("空标准库与筛选无结果区分呈现", async ({page}) => {
  const state = await installStandards(page, []);
  await openStandards(page);
  await expect(page.getByText("标准库为空，可新建草稿或导入标准包。")).toBeVisible();

  // 库里有了标准之后，同样的界面必须能区分「筛没了」与「没有标准」
  state.list = [published("official", "2.1.0")];
  await page.getByRole("button", {name: "返回欢迎页"}).click();
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(libraryItems(page).filter({hasText: "市政燃气施工图"})).toHaveCount(1);
  await page.getByLabel("来源").selectOption("user");
  await expect(page.getByText("当前筛选条件下没有匹配的标准。")).toBeVisible();
  await expect(page.getByText("标准库为空，可新建草稿或导入标准包。")).toHaveCount(0);
});

test("官方标准只读并保留派生与导出动作", async ({page}) => {
  await installStandards(page, [published("official", "2.1.0"), published("user", "2.0.0")]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "2.1.0"}).click();

  await expect(page.getByText("官方标准只读")).toBeVisible();
  await expect(page.getByRole("button", {name: "编辑"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "删除草稿"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "派生新草稿"})).toBeVisible();
  await expect(page.getByRole("button", {name: "导出标准包"})).toBeVisible();
  // 能力摘要与版本历史来自 detail.document 与同一标准 ID 的已发布版本集合
  await expect(page.getByText("普通属性 1 项")).toBeVisible();
  await expect(page.getByText("派生属性 1 项")).toBeVisible();
  await expect(page.getByRole("button", {name: "v2.0.0 · 用户"})).toBeVisible();
});

test("发布版本只读并可派生新草稿", async ({page}) => {
  const state = await installStandards(page, [
    published("official", "2.1.0"),
    published("user", "2.0.0"),
    draft("草稿 1", "draft-1"),
    draft("草稿 2", "draft-2"),
  ]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "2.0.0"}).click();

  await expect(page.getByText("已发布版本不可直接修改")).toBeVisible();
  await expect(page.getByRole("button", {name: "编辑"})).toHaveCount(0);

  await page.getByRole("button", {name: "派生新草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("基于 szmedi.gas 2.0.0 派生")).toBeVisible();
  // 名称取当前草稿数 +1，版本取源版本补丁位 +1（仅补丁位递增，不产生新标准 ID）
  await expect(dialog.getByLabel("标准名称")).toHaveValue("草稿 3");
  await expect(dialog.getByLabel("版本号")).toHaveValue("2.0.1");
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  await expect(page.getByText("草稿 3")).toBeVisible();
  expect(state.createBodies).toHaveLength(1);
  const created = state.createBodies[0] as {document: Record<string, unknown>};
  expect(created.document["standard_id"]).toBe("szmedi.gas");
  expect(created.document["version"]).toBe("2.0.1");
});

test("新建空白标准写入新 Schema 并可直接保存", async ({page}) => {
  const state = await installStandards(page, []);
  await openStandards(page);
  await expect(page.getByText("标准库为空，可新建草稿或导入标准包。")).toBeVisible();
  await page.getByRole("button", {name: "新建草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await dialog.getByLabel("标准名称").fill("空白标准");
  await dialog.getByLabel("版本号").fill("1.0.0");
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  // 创建体必须是 Schema v1：不含旧顶层 rules，且带默认 DWG 命名模板
  expect(state.createBodies).toHaveLength(1);
  const created = state.createBodies[0] as {document: Record<string, unknown>};
  expect(created.document["rules"]).toBeUndefined();
  expect(created.document["dwg_naming"]).toEqual({
    segments: [
      {system_field: "subset.scope"},
      {literal: " "},
      {system_field: "subset.name"},
    ],
  });

  // 进入编辑器：结构门禁放行（可保存）、DWG 命名分区已有 1 条模板
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();
  await expect(page.getByTestId("editor-save-state")).toHaveText("已保存");
  await expect(page.getByTestId("editor-section-dwgNaming")).toContainText("DWG 命名1");
  await expect(page.getByTestId("token-preview")).toHaveCount(0);
});

test("草稿可维护：编辑入口直接进入分区编辑器", async ({page}) => {
  await installStandards(page, [published("official", "2.1.0"), draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": draftDocument()},
  });
  await openStandards(page);
  await libraryItems(page).filter({hasText: "草稿 1"}).click();

  await expect(page.getByText("官方标准只读")).toHaveCount(0);
  await expect(page.getByText("已发布版本不可直接修改")).toHaveCount(0);
  const edit = page.getByRole("button", {name: "编辑"});
  await expect(edit).toBeVisible();
  await expect(edit).toBeEnabled();
  await expect(page.getByRole("button", {name: "删除草稿"})).toBeVisible();
  await expect(page.getByRole("button", {name: "派生新草稿"})).toHaveCount(0);

  // Task 9：编辑入口直接进入分区编辑器，草稿按 draft_id 读取并建立可信基准
  await edit.click();
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();
  await expect(page.getByTestId("editor-save-state")).toHaveText("已保存");
});

test("删除草稿走共享确认模态，确认后才调用删除并刷新列表", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1"), draft("草稿 2", "draft-2")]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "草稿 1"}).click();
  await page.getByRole("button", {name: "删除草稿"}).click();

  const modal = page.locator('[role="dialog"][aria-modal="true"]');
  await expect(modal).toBeVisible();
  await expect(modal.getByText("确定删除草稿“草稿 1”？删除后不可恢复。")).toBeVisible();
  expect(state.deleted).toEqual([]);
  await modal.getByRole("button", {name: "删除"}).click();

  await expect(libraryItems(page).filter({hasText: "草稿 1"})).toHaveCount(0);
  await expect(libraryItems(page).filter({hasText: "草稿 2"})).toHaveCount(1);
  expect(state.deleted).toEqual(["draft-1"]);
  // 删除后回到未选中态：详情面板提示重新选择，不残留已删除草稿的只读/可写边界
  await expect(page.getByText("从左侧列表选择一条标准查看详情。")).toBeVisible();
});

test("标准库加载失败给出稳定错误且不伪造空库", async ({page}) => {
  await installStandards(page, [], {listFails: true});
  await openStandards(page);
  await expect(page.getByText("标准库加载失败", {exact: false})).toBeVisible();
  await expect(page.getByText("标准库为空，可新建草稿或导入标准包。")).toHaveCount(0);
  await expect(page.getByText("从左侧列表选择一条标准查看详情。")).toBeVisible();
});

test("导入碰撞不改变当前选择且不关闭导入对话框", async ({page}) => {
  const state = await installStandards(page, [published("official", "2.1.0"), published("user", "2.0.0")]);
  await openStandards(page);
  const selected = libraryItems(page).filter({hasText: "2.1.0"});
  await selected.click();
  await expect(page.getByText("官方标准只读")).toBeVisible();

  await page.getByRole("button", {name: "导入标准包"}).click();
  const dialog = page.getByRole("dialog", {name: "导入标准包"});
  await dialog.getByLabel("标准包路径（.dststandard）").fill("C:\\standards\\duplicate.dststandard");
  await dialog.getByRole("button", {name: "导入"}).click();

  await expect(page.getByText("操作失败，发生未知错误")).toBeVisible();
  await expect(dialog).toBeVisible();
  await expect(selected).toHaveClass(/selected/);
  await expect(page.getByText("官方标准只读")).toBeVisible();
  expect(state.list).toHaveLength(2);
});

test("900×768 下标准库为列表 → 详情分级视图且无横向溢出", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [published("official", "2.1.0")]);
  await openStandards(page);

  const detailRegion = page.getByRole("region", {name: "标准详情"});
  await expect(detailRegion).toBeHidden();
  await libraryItems(page).filter({hasText: "2.1.0"}).click();
  await expect(detailRegion).toBeVisible();
  await expect(page.getByText("官方标准只读")).toBeVisible();
  await expect(page.getByRole("region", {name: "标准库"})).toBeVisible();
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(900);
});
