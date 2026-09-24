// 标准库主从分栏 e2e（PLAN-DM-035 Task 8 / SPEC-DM-016 §5–§6）。
// 标准端点经 fixtures/standards 的 route mock 驱动，断言停留在语义层：空库与筛选
// 无结果的区分、官方/已发布只读边界、草稿可维护、派生新草稿、加载失败与导入碰撞
// 不改变选中、900×768 分级视图无横向溢出。
import {expect, test, type Page} from "@playwright/test";
import {draft, draftDocument, groupHeaders, installStandards, libraryItems, openStandards, published} from "./fixtures/standards";

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
  state.list = [published("official", 2)];
  await page.getByRole("button", {name: "返回欢迎页"}).click();
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(libraryItems(page).filter({hasText: "市政燃气施工图"})).toHaveCount(1);
  await page.getByLabel("来源").selectOption("user");
  await expect(page.getByText("当前筛选条件下没有匹配的标准。")).toBeVisible();
  await expect(page.getByText("标准库为空，可新建草稿或导入标准包。")).toHaveCount(0);
});

test("官方标准只读并保留派生与导出动作", async ({page}) => {
  await installStandards(page, [published("official", 2), published("user", 1)]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "v2"}).click();

  await expect(page.getByText("官方标准只读")).toBeVisible();
  await expect(page.getByRole("button", {name: "编辑"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "删除草稿"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "派生新草稿"})).toBeVisible();
  await expect(page.getByRole("button", {name: "导出标准包"})).toBeVisible();
  // 能力摘要与版本历史来自 detail.document 与同一标准 ID 的已发布版本集合
  await expect(page.getByText("普通属性 1 项")).toBeVisible();
  await expect(page.getByText("派生属性 1 项")).toBeVisible();
  await expect(page.getByRole("button", {name: "v1 · 市政燃气施工图 · 用户"})).toBeVisible();
});

test("发布版本只读并可派生新草稿", async ({page}) => {
  const state = await installStandards(page, [
    published("official", 2),
    published("user", 1),
    draft("草稿 1", "draft-1"),
    draft("草稿 2", "draft-2"),
  ]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "v1"}).click();

  await expect(page.getByText("已发布版本不可直接修改")).toBeVisible();
  await expect(page.getByRole("button", {name: "编辑"})).toHaveCount(0);

  await page.getByRole("button", {name: "派生新草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("基于 szmedi.gas 1 派生")).toBeVisible();
  // 名称取当前草稿数 +1；派生草稿不携带版本（发布时由服务端分配）
  await expect(dialog.getByLabel("标准名称")).toHaveValue("草稿 3");
  await expect(dialog.getByLabel("版本号")).toHaveCount(0);
  await expect(dialog.getByText(/由服务端分配 v1、v2/)).toBeVisible();
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  await expect(page.getByText("草稿 3")).toBeVisible();
  expect(state.createBodies).toHaveLength(1);
  const created = state.createBodies[0] as {document: Record<string, unknown>};
  expect(created.document["standard_id"]).toBe("szmedi.gas");
  expect(created.document["version"]).toBeUndefined();
  expect(created.document["schema_version"]).toBe(2);
});

test("新建空白标准写入新 Schema 并可直接保存", async ({page}) => {
  const state = await installStandards(page, []);
  await openStandards(page);
  await expect(page.getByText("标准库为空，可新建草稿或导入标准包。")).toBeVisible();
  await page.getByRole("button", {name: "新建草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await dialog.getByLabel("标准名称").fill("空白标准");
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  // 创建体必须是 Schema v2（无版本字段）：不含旧顶层 rules，且带默认 DWG 命名模板
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
  await installStandards(page, [published("official", 2), draft("草稿 1", "draft-1")], {
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
  const state = await installStandards(page, [published("official", 2), published("user", 1)]);
  await openStandards(page);
  const selected = libraryItems(page).filter({hasText: "v2"});
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

// ---- 列表键与编辑身份（PLAN-DM-040 Task 5，F03/F05） ---------------------

test("同来源同版本的不同标准互不串键", async ({page}) => {
  await installStandards(page, [
    published("official", 1, {standard_id: "official.gas", name: "官方燃气标准"}),
    published("official", 1, {standard_id: "official.water", name: "官方给水标准"}),
  ]);
  await openStandards(page);
  await expect(libraryItems(page)).toHaveCount(2);

  const detail = page.getByRole("region", {name: "标准详情"});
  await libraryItems(page).filter({hasText: "官方燃气标准"}).click();
  await expect(detail).toContainText("official.gas");
  await libraryItems(page).filter({hasText: "官方给水标准"}).click();
  await expect(detail).toContainText("official.water");
  await expect(detail).not.toContainText("official.gas");
  // 选中高亮必须落在当前条目上（键重复时两个条目会同时命中）
  await expect(libraryItems(page).filter({hasText: "官方给水标准"})).toHaveClass(/selected/);
  await expect(libraryItems(page).filter({hasText: "官方燃气标准"})).not.toHaveClass(/selected/);
});

test("空库新建草稿后保存与发布只作用于新草稿", async ({page}) => {
  const state = await installStandards(page, []);
  await openStandards(page);
  await page.getByRole("button", {name: "新建草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await dialog.getByLabel("标准名称").fill("空白标准");
    await dialog.getByRole("button", {name: "创建草稿"}).click();

  const editor = page.getByRole("region", {name: "标准草稿编辑器"});
  await expect(editor).toBeVisible();
  await expect(editor).toContainText("draft-new-1");
  await editor.getByLabel("标准名称").fill("改名后的标准");
  await page.getByRole("button", {name: "保存草稿"}).click();
  await expect(page.getByTestId("editor-save-state")).toHaveText("已保存");
  expect(state.drafts.get("draft-new-1")?.["name"]).toBe("改名后的标准");

  await page.getByRole("button", {name: "发布检查"}).click();
  await page.getByRole("button", {name: "发布标准"}).click();
  await expect(page.getByRole("region", {name: "标准详情"})).toBeVisible();
  expect(state.publishDraftIds).toEqual(["draft-new-1"]);
});

test("选中旧草稿后新建：资产检查只调用新草稿 ID", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": draftDocument()},
  });
  state.assetResults["layout-template-1"] = {
    asset_id: "layout-template-1",
    kind: "layout-template",
    layouts: ["Model", "A4"],
    diagnostics: [],
  };
  await openStandards(page);
  await libraryItems(page).filter({hasText: "草稿 1"}).click();
  await page.getByRole("button", {name: "新建草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await dialog.getByLabel("标准名称").fill("空白标准");
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  await page.getByTestId("editor-section-assets").click();
  await page.getByRole("button", {name: "添加布局模板"}).click();
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\tmp\\A4 模板.dwg"; });
  await page.getByTestId("asset-file-pick-0").click();
  await page.getByLabel("图幅（role）").fill("A4");
  await page.getByRole("button", {name: "重新检查"}).click();
  await expect(page.getByTestId("asset-row-user-layout-template-1")).toContainText("检查通过");

  expect(new Set(state.inspectDraftIds)).toEqual(new Set(["draft-new-1"]));
});

// ---- 陈旧详情与版本跳转（PLAN-DM-040 Task 6，F08/F09） --------------------

test("切换选择后派生只消费已加载且身份匹配的详情", async ({page}) => {
  const state = await installStandards(
    page,
    [
      published("official", 1, {standard_id: "official.gas", name: "官方燃气标准"}),
      published("official", 1, {standard_id: "official.water", name: "官方给水标准"}),
    ],
    {
      detailFailures: {
        "official.water": {status: 404, code: "STANDARD_VERSION_NOT_FOUND", message: "标准不存在"},
      },
      detailDocuments: {
        // 两份详情内容可区分：派生来源必须是当前标准的文档
        "official.gas@1": draftDocument({standard_id: "official.gas", name: "官方燃气标准", numbering: {sequence_field: "subset.sequence", digits: 2}}),
        "official.water@1": draftDocument({standard_id: "official.water", name: "官方给水标准", numbering: {sequence_field: "subset.sequence", digits: 3}}),
      },
    },
  );
  await openStandards(page);
  const detail = page.getByRole("region", {name: "标准详情"});
  await libraryItems(page).filter({hasText: "官方燃气标准"}).click();
  await expect(detail).toContainText("official.gas");

  // 切到加载失败的 B：旧详情不得继续可用，派生不得基于 A 提交
  await libraryItems(page).filter({hasText: "官方给水标准"}).click();
  await expect(detail).not.toContainText("official.gas");
  await page.getByRole("button", {name: "派生新草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await dialog.getByLabel("标准名称").fill("派生草稿");
  await dialog.getByRole("button", {name: "创建草稿"}).click();
  await expect(page.getByText("请先加载要派生的已发布版本详情。")).toBeVisible();
  expect(state.createBodies).toEqual([]);

  // B 恢复加载后重新派生：来源必须是 B 的文档
  delete state.detailFailures["official.water"];
  await dialog.getByRole("button", {name: "取消"}).click();
  await libraryItems(page).filter({hasText: "官方燃气标准"}).click();
  await libraryItems(page).filter({hasText: "官方给水标准"}).click();
  await expect(detail).toContainText("official.water");
  await page.getByRole("button", {name: "派生新草稿"}).click();
  await dialog.getByLabel("标准名称").fill("派生草稿");
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();
  expect(state.createBodies).toHaveLength(1);
  const created = state.createBodies[0] as {document: Record<string, unknown>};
  expect(created.document["standard_id"]).toBe("official.water");
  expect((created.document["numbering"] as {digits: number}).digits).toBe(3);
});

test("版本历史跨官方与用户来源时选中正确标准", async ({page}) => {
  await installStandards(page, [
    published("official", 2, {standard_id: "szmedi.gas", name: "市政燃气施工图"}),
    published("user", 1, {standard_id: "szmedi.gas", name: "市政燃气施工图"}),
  ]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "v2"}).click();
  await expect(page.getByText("官方标准只读")).toBeVisible();

  // 版本历史条目自带来源：点击用户版本必须切换到用户来源，而不是沿用官方
  await page.getByRole("button", {name: "v1 · 市政燃气施工图 · 用户"}).click();
  await expect(page.getByText("已发布版本不可直接修改")).toBeVisible();
  await expect(page.getByText("官方标准只读")).toHaveCount(0);
  await expect(page.getByRole("region", {name: "标准详情"})).toContainText("szmedi.gas");
});

test("900×768 下标准库为列表 → 详情分级视图且无横向溢出", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [published("official", 2), draft("草稿 1", "draft-1")]);
  await openStandards(page);

  const libraryRegion = page.getByRole("region", {name: "标准库"});
  const detailRegion = page.getByRole("region", {name: "标准详情"});
  await expect(libraryRegion).toBeVisible();
  await expect(detailRegion).toBeHidden();

  await page.getByLabel("搜索标准").fill("市政");
  await libraryItems(page).filter({hasText: "v2"}).click();
  // 两级视图互斥：选中后列表隐藏、详情显示、返回列表可见
  await expect(detailRegion).toBeVisible();
  await expect(page.getByText("官方标准只读")).toBeVisible();
  await expect(libraryRegion).toBeHidden();
  const back = page.getByRole("button", {name: "返回列表"});
  await expect(back).toBeVisible();

  // 返回后筛选与选择保留；两侧互斥保持
  await back.click();
  await expect(libraryRegion).toBeVisible();
  await expect(detailRegion).toBeHidden();
  await expect(page.getByLabel("搜索标准")).toHaveValue("市政");
  await expect(libraryItems(page).filter({hasText: "v2"})).toHaveClass(/selected/);

  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(900);
});

test("列表与详情失败可就地重试，筛选无结果可清除", async ({page}) => {
  const state = await installStandards(page, [published("official", 2)], {listFails: true});
  await openStandards(page);

  // 列表失败：就地重试只重发列表请求
  await expect(page.getByText(/标准库加载失败/)).toBeVisible();
  state.listFails = false;
  await page.getByRole("button", {name: "重试加载标准库"}).click();
  await expect(libraryItems(page)).toHaveCount(1);

  // 详情失败：保留列表与选择，右栏就地错误与重试
  state.detailFailures["szmedi.gas"] = {status: 500, code: "INTERNAL_ERROR", message: "详情不可用"};
  await libraryItems(page).filter({hasText: "v2"}).click();
  await expect(page.getByTestId("detail-error")).toBeVisible();
  // 详情失败不渲染文档摘要（不把旧详情当作当前详情）
  await expect(page.getByRole("region", {name: "标准详情"})).not.toContainText("普通属性 1 项");
  delete state.detailFailures["szmedi.gas"];
  await page.getByRole("button", {name: "重试加载详情"}).click();
  await expect(page.getByRole("region", {name: "标准详情"})).toContainText("官方标准只读");

  // 筛选无结果：不伪装成空库，可一键清除筛选
  await page.getByLabel("搜索标准").fill("不存在的标准");
  await expect(page.getByText("当前筛选条件下没有匹配的标准。")).toBeVisible();
  await page.getByRole("button", {name: "清除筛选"}).click();
  await expect(page.getByLabel("搜索标准")).toHaveValue("");
  await expect(libraryItems(page)).toHaveCount(1);
});

/** 页面无横向溢出（窄屏与 200% 缩放的共同判据）。 */
async function expectNoPageHScroll(page: Page, label: string): Promise<void> {
  const metrics = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    win: window.innerWidth,
  }));
  expect(metrics.doc, `${label}：无页面级横向溢出`).toBeLessThanOrEqual(metrics.win);
}

test("200% 缩放下两级视图互斥且返回列表可达", async ({page}) => {
  await installStandards(page, [published("official", 2), draft("草稿 1", "draft-1")]);
  await page.goto("/");
  // 1440×900 下浏览器 200% 缩放 = CSS 视口 720×450 + 2x 渲染（与既有证据同一口径）
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {width: 720, height: 450, deviceScaleFactor: 2, mobile: false});
  await page.getByRole("button", {name: "管理图纸标准"}).click();

  const libraryRegion = page.getByRole("region", {name: "标准库"});
  const detailRegion = page.getByRole("region", {name: "标准详情"});
  await expect(libraryRegion).toBeVisible();
  await expect(detailRegion).toBeHidden();
  await expectNoPageHScroll(page, "200% 标准库列表");

  await libraryItems(page).filter({hasText: "v2"}).click();
  await expect(detailRegion).toBeVisible();
  await expect(libraryRegion).toBeHidden();
  const back = page.getByRole("button", {name: "返回列表"});
  await expect(back).toBeVisible();
  const box = await back.boundingBox();
  expect(box, "返回列表应有布局盒").not.toBeNull();
  // 用页面内真实视口高度判定：CDP 覆盖不会更新 page.viewportSize()
  const innerHeight = await page.evaluate(() => window.innerHeight);
  expect(box!.y + box!.height, "返回列表底部在视口内").toBeLessThanOrEqual(innerHeight + 1);
  await expectNoPageHScroll(page, "200% 标准详情");
});

test("窄屏两级视图可用键盘进入与返回", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [published("official", 2)]);
  await openStandards(page);

  const item = libraryItems(page).first();
  await item.focus();
  await expect(item).toBeFocused();
  await page.keyboard.press("Enter");
  const detailRegion = page.getByRole("region", {name: "标准详情"});
  await expect(detailRegion).toBeVisible();
  await expect(page.getByText("官方标准只读")).toBeVisible();

  const back = page.getByRole("button", {name: "返回列表"});
  await back.focus();
  await expect(back).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", {name: "标准库"})).toBeVisible();
  await expect(detailRegion).toBeHidden();
});

test("超长中英文标准名在窄屏两级视图下不溢出", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  const longName = "市政燃气管网施工图设计说明书（第一分册）VeryLongStandardNameForOverflowCheck2026";
  await installStandards(page, [
    published("official", 2, {name: longName}),
    draft("草稿 1", "draft-1"),
  ]);
  await openStandards(page);

  await expect(libraryItems(page).filter({hasText: "第一分册"})).toBeVisible();
  await expectNoPageHScroll(page, "长名称标准库列表");
  await libraryItems(page).filter({hasText: "第一分册"}).click();
  await expect(page.getByRole("region", {name: "标准详情"})).toContainText("VeryLongStandardNameForOverflowCheck2026");
  await expectNoPageHScroll(page, "长名称标准详情");
  // 返回列表仍可用，且选择保留
  await page.getByRole("button", {name: "返回列表"}).click();
  await expect(libraryItems(page).filter({hasText: "第一分册"})).toHaveClass(/selected/);
});

// ---- 新建弹窗焦点契约（PLAN-DM-040 Task 9，F13） --------------------------

test("新建草稿弹窗：初始焦点、Tab 圈闭、Escape 与焦点归还", async ({page}) => {
  const state = await installStandards(page, []);
  await openStandards(page);
  const opener = page.getByRole("button", {name: "新建草稿"});
  await opener.click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await expect(dialog).toBeVisible();

  // 打开后焦点进入弹窗内的真实停靠点（不是留在遮罩或页面背景）
  await expect(dialog.getByLabel("标准名称")).toBeFocused();
  // Tab 圈闭：首元素上 Shift+Tab 回到末元素，再从末元素 Tab 回首元素
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", {name: "创建草稿"})).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByLabel("标准名称")).toBeFocused();

  // Escape 关闭且不提交，焦点归还给打开按钮
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect(state.createBodies).toEqual([]);
});


test("窄屏删除当前草稿后回到列表而不是空白详情", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [draft("草稿 1", "draft-1"), draft("草稿 2", "draft-2")]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "草稿 1"}).click();
  const libraryRegion = page.getByRole("region", {name: "标准库"});
  const detailRegion = page.getByRole("region", {name: "标准详情"});
  await expect(detailRegion).toBeVisible();
  await expect(libraryRegion).toBeHidden();

  await page.getByRole("button", {name: "删除草稿"}).click();
  await page.locator('[role="dialog"][aria-modal="true"]').getByRole("button", {name: "删除"}).click();

  // 选中项被删除：必须回到列表，不能停在无可返回入口的空白详情
  await expect(libraryRegion).toBeVisible();
  await expect(detailRegion).toBeHidden();
  await expect(libraryItems(page).filter({hasText: "草稿 2"})).toBeVisible();
});

test("草稿加载失败时不显示无动作的详情重试按钮", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {}});
  await openStandards(page);
  await libraryItems(page).filter({hasText: "草稿 1"}).click();
  await page.getByRole("button", {name: "编辑"}).click();

  await expect(page.getByTestId("detail-error")).toBeVisible();
  // 草稿没有可重发的详情请求：不得给出点了没反应的「重试加载详情」
  await expect(page.getByRole("button", {name: "重试加载详情"})).toHaveCount(0);
});

// ---- 按 ID 归集与整数版本（PLAN-DM-041 Task 6） ---------------------------

test("标准库按 ID 归集并按整数版本降序，草稿归入同组", async ({page}) => {
  await installStandards(page, [
    published("official", 9, {standard_id: "szmedi.gas"}),
    published("user", 10, {standard_id: "szmedi.gas"}),
    draft("草稿 1", "draft-1"),
    published("user", 1, {standard_id: "other.std", name: "其他标准"}),
  ]);
  await openStandards(page);

  // 两个 ID → 两个归集组；组标题取当前可见最高版本（v10）的名称
  await expect(groupHeaders(page)).toHaveCount(2);
  await expect(groupHeaders(page).first()).toContainText("szmedi.gas");
  await expect(groupHeaders(page).first()).toContainText("v10");
  await expect(groupHeaders(page).last()).toContainText("other.std");

  // 组内整数降序：v10 在 v9 之前，草稿排在版本之后
  const entries = await libraryItems(page).allInnerTexts();
  expect(entries[0]).toContain("v10");
  expect(entries[1]).toContain("v9");
  expect(entries[2]).toContain("草稿 1");
  expect(entries[3]).toContain("v1");

  // 键盘可收起/展开：组头是带 aria-expanded 的按钮
  const header = groupHeaders(page).first();
  await header.focus();
  await page.keyboard.press("Enter");
  await expect(header).toHaveAttribute("aria-expanded", "false");
  // 收起用 v-show 隐藏（元素仍在 DOM），所以断言可见性而不是元素计数
  await expect(libraryItems(page).first()).toBeHidden();
  await page.keyboard.press("Enter");
  await expect(header).toHaveAttribute("aria-expanded", "true");
  await expect(libraryItems(page).first()).toBeVisible();
  await expect(libraryItems(page)).toHaveCount(4);
});

test("来源筛选只保留匹配版本与组，清除后复原", async ({page}) => {
  await installStandards(page, [
    published("official", 9, {standard_id: "szmedi.gas"}),
    published("user", 10, {standard_id: "szmedi.gas"}),
    published("user", 1, {standard_id: "other.std", name: "其他标准"}),
  ]);
  await openStandards(page);
  await expect(groupHeaders(page)).toHaveCount(2);

  await page.getByLabel("来源").selectOption("official");
  await expect(groupHeaders(page)).toHaveCount(1);
  await expect(libraryItems(page)).toHaveCount(1);
  await expect(libraryItems(page).first()).toContainText("v9");

  await page.getByLabel("来源").selectOption("all");
  await expect(groupHeaders(page)).toHaveCount(2);
  await expect(libraryItems(page)).toHaveCount(3);
});
