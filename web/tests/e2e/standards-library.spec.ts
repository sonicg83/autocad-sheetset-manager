// 标准库主从分栏 e2e（PLAN-DM-035 Task 8 / SPEC-DM-016 §5–§6）。
// 标准端点经 fixtures/standards 的 route mock 驱动，断言停留在语义层：空库与筛选
// 无结果的区分、官方/已发布只读边界、草稿可维护、派生新草稿、加载失败与导入碰撞
// 不改变选中、900×768 分级视图无横向溢出。
import {expect, test, type Page} from "@playwright/test";
import {chooseStandardPackage, draft, draftDocument, installStandards, libraryItems, openStandards, published} from "./fixtures/standards";

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
  state.list = [published("official", {name: "市政燃气施工图"})];
  await page.getByRole("button", {name: "返回欢迎页"}).click();
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(libraryItems(page).filter({hasText: "市政燃气施工图"})).toHaveCount(1);
  await page.getByLabel("来源").selectOption("user");
  await expect(page.getByText("当前筛选条件下没有匹配的标准。")).toBeVisible();
  await expect(page.getByText("标准库为空，可新建草稿或导入标准包。")).toHaveCount(0);
});

test("官方标准只读并保留派生与导出动作", async ({page}) => {
  await installStandards(page, [published("official", {name: "官方标准"}), published("user", {name: "用户标准", standard_id: "00000000-0000-4000-8000-000000000047"})]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "官方标准"}).click();

  await expect(page.getByText("官方标准只读")).toBeVisible();
  await expect(page.getByRole("button", {name: "编辑"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "删除", exact: true})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "派生新草稿"})).toBeVisible();
  await expect(page.getByRole("button", {name: "导出标准包"})).toBeVisible();
  // 能力摘要来自标准详情文档
  await expect(page.getByText("普通属性 1 项")).toBeVisible();
  await expect(page.getByText("派生属性 1 项")).toBeVisible();
  await expect(page.getByText("版本历史")).toHaveCount(0);
});

test("发布版本只读并可派生新草稿", async ({page}) => {
  const state = await installStandards(page, [
    published("official", {name: "官方燃气标准"}),
    published("user", {name: "用户燃气标准", standard_id: "00000000-0000-4000-8000-000000000047"}),
    draft("草稿 1", "draft-1"),
    draft("草稿 2", "draft-2"),
  ]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "用户燃气标准"}).click();

  await expect(page.getByText("已发布标准不可直接修改")).toBeVisible();
  await expect(page.getByRole("button", {name: "编辑"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "删除", exact: true})).toBeVisible();

  await page.getByRole("button", {name: "派生新草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/基于 00000000-0000-4000-8000-000000000047 派生/)).toBeVisible();
  // 名称取当前草稿数 +1；新草稿按 UUID 标识。
  await expect(dialog.getByLabel("标准名称")).toHaveValue("草稿 3");
  await expect(dialog.getByLabel("版本号")).toHaveCount(0);
  await expect(dialog.getByText(/服务端分配/)).toHaveCount(0);
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  await expect(page.getByText("草稿 3")).toBeVisible();
  expect(state.createBodies).toHaveLength(1);
  const created = state.createBodies[0] as {document: Record<string, unknown>};
  expect(created.document["standard_id"]).toBe("00000000-0000-4000-8000-000000000047");
  expect(created.document["version"]).toBeUndefined();
  expect(created.document["schema_version"]).toBe(3);
});

test("新建空白标准写入新 Schema 并可直接保存", async ({page}) => {
  const state = await installStandards(page, []);
  await openStandards(page);
  await expect(page.getByText("标准库为空，可新建草稿或导入标准包。")).toBeVisible();
  await page.getByRole("button", {name: "新建草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await dialog.getByLabel("标准名称").fill("空白标准");
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  // 创建体必须是 Schema v3：不含旧发布字段和旧顶层 rules，且带默认 DWG 命名模板
  expect(state.createBodies).toHaveLength(1);
  const created = state.createBodies[0] as {document: Record<string, unknown>};
  expect(created.document["standard_id"]).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  expect(created.document["schema_version"]).toBe(3);
  expect(created.document["description"]).toBe("");
  expect(created.document["published_at"]).toBeNull();
  expect(created.document["release_notes"]).toBeUndefined();
  expect(created.document["version"]).toBeUndefined();
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
  await installStandards(page, [published("official"), draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": draftDocument()},
  });
  await openStandards(page);
  await libraryItems(page).filter({hasText: "草稿 1"}).click();

  await expect(page.getByText("官方标准只读")).toHaveCount(0);
  await expect(page.getByText("已发布标准不可直接修改")).toHaveCount(0);
  const edit = page.getByRole("button", {name: "编辑"});
  await expect(edit).toBeVisible();
  await expect(edit).toBeEnabled();
  await expect(page.getByRole("button", {name: "删除", exact: true})).toBeVisible();
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
  await page.getByRole("button", {name: "删除", exact: true}).click();

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

test("导入预检冲突留在弹窗、保留路径且不改变当前选择", async ({page}) => {
  const state = await installStandards(page, [
    published("official", {name: "官方标准"}),
    published("user", {name: "用户标准", standard_id: "00000000-0000-4000-8000-000000000047"}),
  ], {
    importConflict: {status: 200, code: "STANDARD_ID_EXISTS", message: "同一标准 ID 已存在"},
  });
  await openStandards(page);
  const selected = libraryItems(page).filter({hasText: "官方标准"});
  await selected.click();
  await expect(page.getByText("官方标准只读")).toBeVisible();

  await page.getByRole("button", {name: "导入标准包"}).click();
  const dialog = page.getByRole("dialog", {name: "导入标准包"});
  // 空路径时预检按钮禁用（未选择不得提交）
  await expect(dialog.getByTestId("import-preview-button")).toBeDisabled();
  await chooseStandardPackage(page, "C:\\标准包\\带 空格\\duplicate.dststandard");
  await dialog.getByTestId("import-preview-button").click();
  await expect(dialog.getByTestId("import-preview")).toBeVisible();
  await expect(dialog.getByTestId("import-diagnostics")).toContainText("STANDARD_ID_EXISTS");
  await expect(dialog.getByTestId("import-confirm-button")).toBeDisabled();
  // 中文/空格路径原样交给预检端点并原样回显
  expect(state.previewPaths).toEqual(["C:\\标准包\\带 空格\\duplicate.dststandard"]);
  await expect(dialog.getByTestId("import-selected-path")).toHaveValue("C:\\标准包\\带 空格\\duplicate.dststandard");

  // 冲突不关闭弹窗、不改变当前选择，也不写标准库
  await expect(dialog).toBeVisible();
  await expect(selected).toHaveClass(/selected/);
  await expect(page.getByText("官方标准只读")).toBeVisible();
  expect(state.list).toHaveLength(2);
  expect(state.confirmAttempts).toBe(0);

  // 更换文件清除旧预检：预检面板消失，确认按钮回到禁用
  await chooseStandardPackage(page, "C:\\标准包\\other.dststandard");
  await expect(dialog.getByTestId("import-preview")).toHaveCount(0);
  await expect(dialog.getByTestId("import-confirm-button")).toBeDisabled();
});

test("重新预检时取消上一凭证并保留当前可确认状态", async ({page}) => {
  const state = await installStandards(page, []);
  await openStandards(page);
  await page.getByRole("button", {name: "导入标准包"}).click();
  const dialog = page.getByRole("dialog", {name: "导入标准包"});
  await chooseStandardPackage(page, "C:\\标准包\\a.dststandard");
  await dialog.getByTestId("import-preview-button").click();
  await expect(dialog.getByTestId("import-confirm-button")).toBeEnabled();

  await dialog.getByTestId("import-preview-button").click();

  await expect(dialog.getByTestId("import-confirm-button")).toBeEnabled();
  expect(state.importAttempts).toBe(2);
  expect(state.cancelAttempts).toBe(1);
});

test("导入预检通过后可确认导入，并按 UUID 定位新标准", async ({page}) => {
  const state = await installStandards(page, [published("official", {name: "官方标准"})]);
  await openStandards(page);
  await page.getByRole("button", {name: "导入标准包"}).click();
  const dialog = page.getByRole("dialog", {name: "导入标准包"});
  await chooseStandardPackage(page, "C:\\标准包\\standard.dststandard");
  await dialog.getByTestId("import-preview-button").click();
  await expect(dialog.getByTestId("import-preview")).toBeVisible();
  await expect(dialog.getByTestId("import-confirm-button")).toBeEnabled();

  await dialog.getByTestId("import-confirm-button").click();
  await expect(dialog.getByTestId("import-success")).toBeVisible();
  expect(state.confirmAttempts).toBe(1);

  // 关闭后列表刷新并定位到导入标准详情
  await page.getByRole("button", {name: "关闭"}).click();
  await expect(page.getByTestId("standard-import-dialog")).toHaveCount(0);
  await expect(libraryItems(page)).toHaveCount(2);
  await expect(page.getByText("已发布标准不可直接修改")).toBeVisible();
  await expect(page.getByRole("region", {name: "标准详情"})).toContainText("00000000-0000-4000-8000-000000000047");
});

test("同名导入可改名为本机副本并保留原标准包", async ({page}) => {
  const state = await installStandards(page, [published("official", {name: "官方标准"})], {
    importNameConflict: "导入标准",
  });
  await openStandards(page);
  await page.getByRole("button", {name: "导入标准包"}).click();
  const dialog = page.getByRole("dialog", {name: "导入标准包"});
  await chooseStandardPackage(page, "C:\\标准包\\same-name.dststandard");
  await dialog.getByTestId("import-preview-button").click();

  await expect(dialog.getByText("名称“导入标准”已被使用，请修改导入副本的名称。", {exact: true})).toBeVisible();
  await expect(dialog.getByText("该标准包当前不可导入", {exact: false})).toHaveCount(0);
  await expect(dialog.getByTestId("import-confirm-button")).toBeDisabled();
  await dialog.getByLabel("导入名称").fill("导入标准（本机副本）");
  await expect(dialog.getByTestId("import-confirm-button")).toBeEnabled();
  await dialog.getByTestId("import-confirm-button").click();

  await expect(dialog.getByTestId("import-success")).toBeVisible();
  expect(state.confirmAttempts).toBe(1);
  await dialog.getByRole("button", {name: "关闭"}).click();
  await expect(libraryItems(page).filter({hasText: "导入标准（本机副本）"})).toHaveCount(1);
  expect(state.list.find(item => item.name === "导入标准（本机副本）")?.standard_id)
    .toBe("00000000-0000-4000-8000-000000000047");
});

test("无桌面壳显示明确标注的本机路径开发态，桥迟到注入后离开该模式", async ({page}) => {
  // 覆盖 beforeEach 注入的假桥：本次按无壳浏览器起始
  await page.addInitScript(() => {
    delete (window as unknown as {pywebview?: unknown}).pywebview;
  });
  await installStandards(page, []);
  await openStandards(page);
  await page.getByRole("button", {name: "导入标准包"}).click();
  const dialog = page.getByRole("dialog", {name: "导入标准包"});
  await expect(dialog.getByTestId("import-dev-fallback")).toBeVisible();
  await expect(dialog.getByTestId("import-choose-file")).toHaveCount(0);

  // 桥迟到注入（pywebviewready）：离开开发态回退，改走原生固定种类选择器
  await page.evaluate(() => {
    (window as unknown as {pywebview?: unknown}).pywebview = {
      api: {
        select_file: async () => null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await expect(dialog.getByTestId("import-dev-fallback")).toHaveCount(0);
  await expect(dialog.getByTestId("import-choose-file")).toBeVisible();
});

// ---- 列表键与编辑身份（PLAN-DM-040 Task 5，F03/F05） ---------------------

test("不同 UUID 的标准选择互不串位", async ({page}) => {
  await installStandards(page, [
    published("official", {standard_id: "00000000-0000-4000-8000-000000000011", name: "官方燃气标准"}),
    published("official", {standard_id: "00000000-0000-4000-8000-000000000012", name: "官方给水标准"}),
  ]);
  await openStandards(page);
  await expect(libraryItems(page)).toHaveCount(2);

  const detail = page.getByRole("region", {name: "标准详情"});
  await libraryItems(page).filter({hasText: "官方燃气标准"}).click();
  await expect(detail).toContainText("00000000-0000-4000-8000-000000000011");
  await libraryItems(page).filter({hasText: "官方给水标准"}).click();
  await expect(detail).toContainText("00000000-0000-4000-8000-000000000012");
  await expect(detail).not.toContainText("00000000-0000-4000-8000-000000000011");
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
    // 复制响应模拟后端从 DWG 读到的布局：勾选 A4 需要它在列表中
    assetCopyLayouts: ["Model", "A4"],
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
  await page.getByTestId("asset-file-pick").click();
  await page.getByTestId("asset-paper-layout-A4").check();
  await page.getByRole("button", {name: "重新检查"}).click();
  await expect(page.getByTestId("asset-row-user-layout-template-1")).toContainText("检查通过");

  expect(new Set(state.inspectDraftIds)).toEqual(new Set(["draft-new-1"]));
});

// ---- 陈旧详情与版本跳转（PLAN-DM-040 Task 6，F08/F09） --------------------

test("切换选择后派生只消费已加载且身份匹配的详情", async ({page}) => {
  const state = await installStandards(
    page,
    [
      published("official", {standard_id: "00000000-0000-4000-8000-000000000011", name: "官方燃气标准"}),
      published("official", {standard_id: "00000000-0000-4000-8000-000000000012", name: "官方给水标准"}),
    ],
    {
      detailFailures: {
        "00000000-0000-4000-8000-000000000012": {status: 404, code: "STANDARD_NOT_FOUND", message: "标准不存在"},
      },
      detailDocuments: {
        // 两份详情内容可区分：派生来源必须是当前标准的文档
        "00000000-0000-4000-8000-000000000011": draftDocument({standard_id: "00000000-0000-4000-8000-000000000011", name: "官方燃气标准", numbering: {sequence_field: "subset.sequence", digits: 2}}),
        "00000000-0000-4000-8000-000000000012": draftDocument({standard_id: "00000000-0000-4000-8000-000000000012", name: "官方给水标准", numbering: {sequence_field: "subset.sequence", digits: 3}}),
      },
    },
  );
  await openStandards(page);
  const detail = page.getByRole("region", {name: "标准详情"});
  await libraryItems(page).filter({hasText: "官方燃气标准"}).click();
  await expect(detail).toContainText("00000000-0000-4000-8000-000000000011");

  // 切到加载失败的 B：旧详情不得继续可用，派生不得基于 A 提交
  await libraryItems(page).filter({hasText: "官方给水标准"}).click();
  await expect(detail).not.toContainText("00000000-0000-4000-8000-000000000011");
  await page.getByRole("button", {name: "派生新草稿"}).click();
  const dialog = page.getByRole("dialog", {name: "新建标准草稿"});
  await dialog.getByLabel("标准名称").fill("派生草稿");
  await dialog.getByRole("button", {name: "创建草稿"}).click();
  await expect(page.getByText("请先加载要派生的已发布标准详情。")).toBeVisible();
  expect(state.createBodies).toEqual([]);

  // B 恢复加载后重新派生：来源必须是 B 的文档
  delete state.detailFailures["00000000-0000-4000-8000-000000000012"];
  await dialog.getByRole("button", {name: "取消"}).click();
  await libraryItems(page).filter({hasText: "官方燃气标准"}).click();
  await libraryItems(page).filter({hasText: "官方给水标准"}).click();
  await expect(detail).toContainText("00000000-0000-4000-8000-000000000012");
  await page.getByRole("button", {name: "派生新草稿"}).click();
  await dialog.getByLabel("标准名称").fill("派生草稿");
  await dialog.getByRole("button", {name: "创建草稿"}).click();

  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();
  expect(state.createBodies).toHaveLength(1);
  const created = state.createBodies[0] as {document: Record<string, unknown>};
  expect(created.document["standard_id"]).toBe("00000000-0000-4000-8000-000000000012");
  expect((created.document["numbering"] as {digits: number}).digits).toBe(3);
});

test("删除用户标准前预览关联草稿，影响变化后要求重新确认", async ({page}) => {
  const standardId = "00000000-0000-4000-8000-000000000070";
  const state = await installStandards(page, [
    published("user", {standard_id: standardId, name: "用户标准"}),
    draft("关联草稿 1", "draft-1", {standard_id: standardId}),
  ]);
  await openStandards(page);
  await libraryItems(page).filter({hasText: "用户标准"}).click();
  await page.getByRole("button", {name: "删除", exact: true}).click();

  const modal = page.locator('[role="dialog"][aria-modal="true"]');
  await expect(modal).toBeVisible();
  await expect(modal).toContainText("将同时删除 1 个关联创建草稿");
  expect(state.deleteImpactRequests).toEqual([standardId]);
  await modal.getByRole("button", {name: "取消"}).click();
  expect(state.deletedStandards).toEqual([]);

  await page.getByRole("button", {name: "删除", exact: true}).click();
  const staleModal = page.locator('[role="dialog"][aria-modal="true"]');
  await expect(staleModal).toContainText("将同时删除 1 个关联创建草稿");
  state.list.push(draft("关联草稿 2", "draft-2", {standard_id: standardId}));
  await staleModal.getByRole("button", {name: "删除"}).click();

  await expect(page.getByTestId("standard-delete-notice")).toContainText("影响已变化");
  await expect(page.getByRole("region", {name: "标准详情"})).toContainText("将同时删除 2 个关联创建草稿");
  await expect(libraryItems(page).filter({hasText: "用户标准"})).toHaveClass(/selected/);
  expect(state.deletedStandards).toEqual([]);

  await page.getByRole("button", {name: "删除", exact: true}).click();
  const refreshedModal = page.locator('[role="dialog"][aria-modal="true"]');
  await expect(refreshedModal).toContainText("将同时删除 2 个关联创建草稿");
  await refreshedModal.getByRole("button", {name: "删除"}).click();

  await expect(libraryItems(page).filter({hasText: "用户标准"})).toHaveCount(0);
  expect(state.deletedStandards).toEqual([standardId]);
  expect(state.deleted).toEqual(["draft-1", "draft-2"]);
  expect(state.deleteTokens.map(item => item.impactToken)).toEqual([
    `impact:${standardId}:1`, `impact:${standardId}:2`,
  ]);
});

test("宽视口下标准库铺满工作区高度与宽度", async ({page}) => {
  await page.setViewportSize({width: 2560, height: 1440});
  await installStandards(page, [published("official")]);
  await openStandards(page);

  const layout = await page.evaluate(() => {
    const shell = document.querySelector<HTMLElement>(".shell-main")!;
    const view = document.querySelector<HTMLElement>(".standards-page")!;
    const split = document.querySelector<HTMLElement>(".library-split")!;
    const shellStyle = getComputedStyle(shell);
    const viewStyle = getComputedStyle(view);
    const shellRect = shell.getBoundingClientRect();
    const viewRect = view.getBoundingClientRect();
    const splitRect = split.getBoundingClientRect();
    return {
      viewWidth: viewRect.width,
      shellContentWidth: shell.clientWidth - Number.parseFloat(shellStyle.paddingLeft) - Number.parseFloat(shellStyle.paddingRight),
      viewBottom: viewRect.bottom,
      shellContentBottom: shellRect.top + shell.clientTop + shell.clientHeight - Number.parseFloat(shellStyle.paddingBottom),
      splitBottom: splitRect.bottom,
      viewContentBottom: viewRect.bottom - Number.parseFloat(viewStyle.paddingBottom),
    };
  });

  expect(Math.abs(layout.viewWidth - layout.shellContentWidth), "标准管理横向铺满壳层内容区").toBeLessThanOrEqual(1);
  expect(Math.abs(layout.viewBottom - layout.shellContentBottom), "标准管理纵向铺满壳层内容区").toBeLessThanOrEqual(1);
  expect(Math.abs(layout.splitBottom - layout.viewContentBottom), "列表与详情面板占据标题下方的剩余空间").toBeLessThanOrEqual(1);
});

test("顶部操作按固定顺序排列并在长列表滚动时保持可见", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const items = Array.from({length: 24}, (_, index) => published("user", {
    standard_id: `00000000-0000-4000-8000-${String(index + 101).padStart(12, "0")}`,
    name: `用户标准 ${index + 1}`,
    description: `面向用户标准 ${index + 1} 的说明。`,
  }));
  await installStandards(page, items);
  await openStandards(page);

  const actions = page.locator(".standards-header-actions button");
  await expect(actions).toHaveText(["新建草稿", "导入标准包", "返回欢迎页"]);
  for (const action of await actions.all()) await expect(action).toBeInViewport();
  const header = page.locator(".standards-header");
  const initialTop = await header.evaluate(element => element.getBoundingClientRect().top);
  const list = page.getByTestId("library-list");
  await list.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await expect.poll(() => list.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  await expect(header).toBeInViewport();
  const scrolledTop = await header.evaluate(element => element.getBoundingClientRect().top);
  expect(scrolledTop).toBeCloseTo(initialTop, 0);
  for (const action of await actions.all()) await expect(action).toBeInViewport();
});

test("900×768 下标准库为列表 → 详情分级视图且无横向溢出", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [published("official"), draft("草稿 1", "draft-1")]);
  await openStandards(page);

  const libraryRegion = page.getByRole("region", {name: "标准库"});
  const detailRegion = page.getByRole("region", {name: "标准详情"});
  const actions = page.locator(".standards-header-actions button");
  await expect(actions).toHaveText(["新建草稿", "导入标准包", "返回欢迎页"]);
  for (const action of await actions.all()) await expect(action).toBeInViewport();
  await expect(libraryRegion).toBeVisible();
  await expect(detailRegion).toBeHidden();

  await page.getByLabel("搜索标准").fill("官方");
  await libraryItems(page).filter({hasText: "官方标准"}).click();
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
  await expect(page.getByLabel("搜索标准")).toHaveValue("官方");
  await expect(libraryItems(page).filter({hasText: "官方标准"})).toHaveClass(/selected/);

  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(900);
});

test("列表与详情失败可就地重试，筛选无结果可清除", async ({page}) => {
  const state = await installStandards(page, [published("official")], {listFails: true});
  await openStandards(page);

  // 列表失败：就地重试只重发列表请求
  await expect(page.getByText(/标准库加载失败/)).toBeVisible();
  state.listFails = false;
  await page.getByRole("button", {name: "重试加载标准库"}).click();
  await expect(libraryItems(page)).toHaveCount(1);

  // 详情失败：保留列表与选择，右栏就地错误与重试
  state.detailFailures["00000000-0000-4000-8000-000000000046"] = {status: 500, code: "INTERNAL_ERROR", message: "详情不可用"};
  await libraryItems(page).filter({hasText: "官方标准"}).click();
  await expect(page.getByTestId("detail-error")).toBeVisible();
  // 详情失败不渲染文档摘要（不把旧详情当作当前详情）
  await expect(page.getByRole("region", {name: "标准详情"})).not.toContainText("普通属性 1 项");
  delete state.detailFailures["00000000-0000-4000-8000-000000000046"];
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
  await installStandards(page, [published("official"), draft("草稿 1", "draft-1")]);
  // 200% 缩放后的 CSS 视口等效为 720×450；直接设置视口可保留 Playwright 鼠标坐标一致。
  await page.setViewportSize({width: 720, height: 450});
  await page.goto("/");
  await page.getByRole("button", {name: "管理图纸标准"}).click();

  const actions = page.locator(".standards-header-actions button");
  await expect(actions).toHaveText(["新建草稿", "导入标准包", "返回欢迎页"]);
  for (const action of await actions.all()) await expect(action).toBeInViewport();

  const libraryRegion = page.getByRole("region", {name: "标准库"});
  const detailRegion = page.getByRole("region", {name: "标准详情"});
  await expect(libraryRegion).toBeVisible();
  await expect(detailRegion).toBeHidden();
  await expectNoPageHScroll(page, "200% 标准库列表");

  await libraryItems(page).filter({hasText: "官方标准"}).click();
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
  await installStandards(page, [published("official")]);
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
    published("official", {name: longName}),
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

  await page.getByRole("button", {name: "删除", exact: true}).click();
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

// ---- 扁平标准库与版本无关身份（PLAN-DM-046 Task 6） -------------------------

test("标准库平铺描述与发布时间，UUID 可搜索并从详情复制", async ({page, context}) => {
  const standardId = "00000000-0000-4000-8000-000000000046";
  const description = "用于验证列表摘要省略显示、悬停标题保留全文并在详情概览展示完整内容。".repeat(5);
  await installStandards(page, [published("official", {standard_id: standardId, description})]);
  await openStandards(page);

  const item = libraryItems(page).first();
  await expect(libraryItems(page)).toHaveCount(1);
  await expect(item.locator(".library-description")).toHaveAttribute("title", description);
  await expect(item.locator(".library-time")).toHaveText(/^\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}$/);
  const visibleText = await item.innerText();
  expect(visibleText).toContain("官方标准");
  expect(visibleText).not.toContain(standardId);
  expect(visibleText).not.toMatch(/\bv\d+\b/);
  const clipping = await item.locator(".library-description").evaluate(element => {
    const style = getComputedStyle(element);
    return {textOverflow: style.textOverflow, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth};
  });
  expect(clipping.textOverflow).toBe("ellipsis");
  expect(clipping.scrollWidth).toBeGreaterThan(clipping.clientWidth);

  await page.getByLabel("搜索标准").fill(standardId);
  await expect(libraryItems(page)).toHaveCount(1);
  await item.click();
  const detail = page.getByRole("region", {name: "标准详情"});
  await expect(detail.locator(".detail-title")).toHaveText("官方标准");
  await expect(detail.locator(".detail-overview")).toContainText(description);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await detail.getByRole("button", {name: "复制 UUID"}).click();
  await expect(detail.getByRole("status")).toContainText("已复制");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(standardId);
});

test("扁平标准库仍按来源、状态筛选并可恢复列表", async ({page}) => {
  await installStandards(page, [
    published("official", {standard_id: "00000000-0000-4000-8000-000000000011", name: "官方甲"}),
    published("user", {standard_id: "00000000-0000-4000-8000-000000000012", name: "用户乙"}),
    draft("草稿丙", "draft-1"),
  ]);
  await openStandards(page);
  await expect(libraryItems(page)).toHaveCount(3);

  await page.getByLabel("来源").selectOption("official");
  await expect(libraryItems(page)).toHaveCount(1);
  await expect(libraryItems(page).first()).toContainText("官方甲");
  await expect(page.getByTestId("library-group-header")).toHaveCount(0);

  await page.getByLabel("来源").selectOption("all");
  await page.getByLabel("状态").selectOption("draft");
  await expect(libraryItems(page)).toHaveCount(1);
  await expect(libraryItems(page).first()).toContainText("草稿丙");
  await page.getByLabel("搜索标准").fill("无匹配标准");
  await expect(page.getByText("当前筛选条件下没有匹配的标准。", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "清除筛选"}).click();
  await expect(libraryItems(page)).toHaveCount(3);
});
