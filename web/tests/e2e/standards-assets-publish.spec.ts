// 模板资产检查与发布检查 e2e（PLAN-DM-035 Task 10 / SPEC-DM-016 §8–§9）。
// 覆盖：资产文件缺失、布局严格不匹配（含 `A3 ` 多空格）、检查本身失败与标准错误分离、
// 仅警告可发布、发布错误跳回映射表并聚焦未覆盖摘要、发布成功后进入新版本只读详情。
import {expect, test} from "@playwright/test";
import {
  draft,
  draftDocument,
  installStandards,
  libraryItems,
  openDraftEditor,
  openEditorSection,
  openStandards,
} from "./fixtures/standards";

/** 声明 A2/A3 两个图幅的布局资产草稿（图幅属性枚举引用它们，避免未引用警告）。 */
function layoutDraft(layouts: string[] = ["A2", "A3"]): Record<string, unknown> {
  return draftDocument({
    assets: [
      {
        asset_id: "layouts",
        kind: "layout-template",
        files: layouts.map((role, index) => ({path: `assets/layout-${index}.dwg`, role})),
      },
    ],
  });
}

function inspection(assetId: string, layouts: string[], diagnostics: Array<{code: string; severity: "error" | "warning" | "info"; message: string}> = []) {
  return {asset_id: assetId, kind: "layout-template", layouts, diagnostics};
}

test.beforeEach(async ({page}) => {
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        // 记录 file_kind：资产复制只允许固定 template 种类，不得由前端拼过滤器。
        select_file: async (kind: string) => {
          (window as any).__lastSelectKind = kind;
          return (window as any).__fakeSelectResult ?? null;
        },
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
});

/** 声明一个基础模板资产的草稿（默认已有受控路径，可直接复制替换）。 */
function templateDraft(path = "assets/A2.dwg"): Record<string, unknown> {
  return draftDocument({
    assets: [{asset_id: "base", kind: "base-template", files: [{path, role: ""}]}],
  });
}

test("布局严格不匹配时显示精确差异并阻断发布", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": layoutDraft()},
    // 实际布局中 A3 多了一个空格：严格比较必须判为不一致，且不静默去空格
    assetResults: {layouts: inspection("layouts", ["Model", "A2", "A3 "])},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "assets");

  await expect(page.getByTestId("asset-layout-A3")).toContainText("缺少同名布局");
  await expect(page.getByTestId("asset-layout-extra-0")).toContainText("A3 ");
  await expect(page.getByTestId("asset-layout-extra-0")).toContainText("未声明布局");

  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByTestId("publish-review")).toBeVisible();
  await expect(page.getByText(/图幅 A3 与实际布局严格不一致/)).toBeVisible();
  await expect(page.getByRole("button", {name: "发布标准"})).toBeDisabled();
  await expect(page.getByText("存在错误或检查失败，暂不能发布。")).toBeVisible();
});

test("资产文件缺失阻断发布并给出受控路径诊断", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": layoutDraft(["A3"])},
    assetResults: {
      layouts: inspection("layouts", [], [
        {code: "STANDARD_ASSET_FILE_MISSING", severity: "error", message: "资产声明的文件不在草稿中"},
      ]),
    },
  });
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "assets");

  await expect(page.getByTestId("asset-diagnostic-0")).toContainText("不在草稿受控目录内");
  await expect(page.getByText("检查有问题")).toBeVisible();
  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByRole("button", {name: "发布标准"})).toBeDisabled();
});

test("检查本身失败与标准错误分开呈现并可重试", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": layoutDraft()},
    assetResults: {layouts: inspection("layouts", ["Model", "A2", "A3"])},
    assetInspectFailures: {layouts: {status: 500, code: "INTERNAL_ERROR", message: "CAD 未就绪"}},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByRole("button", {name: "发布检查"}).click();

  // 检查失败不是「标准存在错误」：单独分组呈现，但同样阻断发布
  await expect(page.getByText("检查本身失败（不是标准错误）")).toBeVisible();
  await expect(page.getByText("未发现阻断问题。")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "发布标准"})).toBeDisabled();
  expect(state.inspectCalls).toEqual(["layouts"]);

  // 重试：失败原因消失后检查通过，发布恢复可用
  delete state.assetInspectFailures["layouts"];
  await page.getByRole("button", {name: "重新检查资产"}).click();
  await expect(page.getByText("检查本身失败（不是标准错误）")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "发布标准"})).toBeEnabled();
  expect(state.inspectCalls).toEqual(["layouts", "layouts"]);
});

test("仅警告时可发布并在发布后进入新版本只读详情", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {
      "draft-1": draftDocument({
        // A5 未被任何取值引用：有效但未引用 → 警告，不阻断发布
        assets: [{asset_id: "unused-layouts", kind: "layout-template", files: [{path: "assets/a5.dwg", role: "A5"}]}],
      }),
    },
    assetResults: {"unused-layouts": inspection("unused-layouts", ["Model", "A5"])},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByRole("button", {name: "发布检查"}).click();

  await expect(page.getByText(/资产 unused-layouts 未被标准取值引用/)).toBeVisible();
  await expect(page.getByText("1 条警告不阻断发布。")).toBeVisible();
  const publish = page.getByRole("button", {name: "发布标准"});
  await expect(publish).toBeEnabled();
  await publish.click();

  // 发布成功：退出编辑器并定位到新版本只读详情（草稿不复存在）
  await expect(page.getByRole("region", {name: "标准详情"})).toBeVisible();
  await expect(page.getByText("已发布版本不可直接修改")).toBeVisible();
  await expect(page.getByRole("button", {name: "编辑"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "派生新草稿"})).toBeVisible();
  await expect(page.getByRole("button", {name: "导出标准包"})).toBeVisible();
  await expect(libraryItems(page).filter({hasText: "3.0.0"})).toHaveCount(1);
  await expect(libraryItems(page).filter({hasText: "草稿 1"})).toHaveCount(0);
  expect(state.publishCalls).toBe(1);
});

test("发布失败保留检查页并显示稳定错误", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": layoutDraft()},
    assetResults: {layouts: inspection("layouts", ["Model", "A2", "A3"])},
  });
  state.publishFailure = {status: 409, code: "STANDARD_DEPENDENCY_MISSING", message: "缺少受信能力 catalog.render"};
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByRole("button", {name: "发布检查"}).click();
  await page.getByRole("button", {name: "发布标准"}).click();

  await expect(page.getByTestId("publish-error")).toContainText("发布失败");
  await expect(page.getByTestId("publish-error")).toContainText("STANDARD_DEPENDENCY_MISSING");
  await expect(page.getByTestId("publish-error")).toContainText("缺少受信能力");
  await expect(page.getByTestId("publish-review")).toBeVisible();
  expect(state.publishCalls).toBe(1);
});

test("发布检查的问题可跳回 DWG 命名分区并聚焦令牌", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {
      "draft-1": draftDocument({dwg_naming: {segments: [{literal: "图签.dwg"}]}}),
    },
  });
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByRole("button", {name: "发布检查"}).click();

  await expect(page.getByText(/模板不得自行包含 .dwg 扩展名/)).toBeVisible();
  await page.getByTestId("publish-issue-0").click();
  await expect(page.getByRole("region", {name: "DWG 命名"})).toBeVisible();
  await expect(page.getByTestId("token-literal")).toBeFocused();
  await expect(page.getByRole("button", {name: "发布标准"})).toHaveCount(0);
});

test("资产声明编辑：新增布局资产后未检查，重新检查后给出结果", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": draftDocument()},
  });
  state.assetResults["layout-template-1"] = inspection("layout-template-1", ["Model", "A4"]);
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "assets");

  await page.getByRole("button", {name: "添加布局模板"}).click();
  await expect(page.getByTestId("asset-row-user-layout-template-1")).toBeVisible();
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\tmp\\A4 模板.dwg"; });
  await page.getByTestId("asset-file-pick-0").click();
  await expect(page.getByTestId("asset-file-path-0")).toHaveValue("assets/managed-1.dwg");
  await page.getByLabel("图幅（role）").fill("A4");
  await expect(page.getByText("有未保存修改")).toBeVisible();

  await page.getByRole("button", {name: "重新检查"}).click();
  await expect(page.getByTestId("asset-row-user-layout-template-1")).toContainText("检查通过");
  expect(state.inspectCalls).toEqual(["layout-template-1"]);
  // 「保存并检查」：检查前先落盘，检查对象就是服务端已保存文档
  expect(state.saveBodies.length).toBe(1);
});

test("结构未完成时「保存并检查」不提交结果：显示未检查而不是未发现问题", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": templateDraft("")},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "assets");

  await expect(page.getByTestId("asset-unchecked")).toContainText("未检查");
  await expect(page.getByText("本次检查未发现问题")).toHaveCount(0);
  await expect(page.getByTestId("asset-row-user-base")).toContainText("未检查");
  // 结构无效：不发起检查（也不会把旧结果当作当前结果）
  expect(state.inspectCalls).toEqual([]);
});

test("发布检查页继续编辑后检查结果失效并阻断发布", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": layoutDraft(["A2"])},
    assetResults: {layouts: inspection("layouts", ["Model", "A2"])},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByRole("button", {name: "发布检查"}).click();

  const publish = page.getByRole("button", {name: "发布标准"});
  await expect(publish).toBeEnabled();
  // 版本说明也属于草稿缓冲：改动后检查结果不再对应当前快照
  await page.getByLabel("版本说明").fill("修订说明");
  await expect(publish).toBeDisabled();
  await expect(page.getByText(/图幅 A2 与实际布局严格不一致/)).toBeVisible();
});

// ---- 本机模板受控复制（PLAN-DM-040 Task 3，F01） ------------------------

test("选择本机模板复制为受控副本；取消不改缓冲", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": templateDraft()},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "assets");

  // 取消：不发请求，受控路径与保存状态保持不变
  await page.evaluate(() => { (window as any).__fakeSelectResult = null; });
  await page.getByTestId("asset-file-pick-0").click();
  expect(state.assetCopyCalls).toEqual([]);
  await expect(page.getByTestId("asset-file-path-0")).toHaveValue("assets/A2.dwg");
  await expect(page.getByTestId("editor-save-state")).toContainText("已保存");

  // 中文 + 空格 + OneDrive 风格路径：只把受控副本名写入缓冲
  await page.evaluate(() => {
    (window as any).__fakeSelectResult = "C:\\Users\\me\\OneDrive - 项目 资料\\A2 模板.dwg";
  });
  await page.getByTestId("asset-file-pick-0").click();
  await expect(page.getByTestId("asset-file-path-0")).toHaveValue("assets/managed-1.dwg");
  await expect(page.getByTestId("asset-file-path-0")).toHaveAttribute("readonly", "");
  expect(state.assetCopyCalls).toEqual([
    {draftId: "draft-1", sourcePath: "C:\\Users\\me\\OneDrive - 项目 资料\\A2 模板.dwg"},
  ]);
  expect(await page.evaluate(() => (window as any).__lastSelectKind)).toBe("template");
  await expect(page.getByTestId("editor-save-state")).toContainText("有未保存修改");

  // 已有声明时入口变为「替换文件」，再次复制得到新的受控副本
  await expect(page.getByRole("button", {name: "替换文件"})).toBeVisible();
  await page.getByTestId("asset-file-pick-0").click();
  await expect(page.getByTestId("asset-file-path-0")).toHaveValue("assets/managed-2.dwg");
});

test("复制失败就地显示错误并保留旧声明", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {
      "draft-1": draftDocument({
        assets: [{asset_id: "base", kind: "base-template", files: [{path: "assets/A2.dwg", role: ""}]}],
      }),
    },
  });
  state.assetCopyFailure = {
    status: 422,
    code: "STANDARD_ASSET_SOURCE_INVALID",
    message: "本机模板来源 '模板.txt' 必须是 .dwg 或 .dwt 文件",
  };
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "assets");

  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\tmp\\模板.txt"; });
  await page.getByTestId("asset-file-pick-0").click();

  await expect(page.getByTestId("asset-file-error-0")).toContainText("STANDARD_ASSET_SOURCE_INVALID");
  await expect(page.getByTestId("asset-file-path-0")).toHaveValue("assets/A2.dwg");
  await expect(page.getByTestId("editor-save-state")).toContainText("已保存");
});

test("无桌面壳时用显式来源绝对路径调用同一端点", async ({page}) => {
  await page.addInitScript(() => { delete (window as any).pywebview; });
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": templateDraft("")},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "assets");

  // 无壳态单独标明来源绝对路径；不用浏览器 <input type=file> 的 fakepath
  await page.getByLabel("来源绝对路径").fill("C:\\tmp\\A2 模板.dwg");
  await page.getByTestId("asset-file-copy-0").click();

  await expect(page.getByTestId("asset-file-path-0")).toHaveValue("assets/managed-1.dwg");
  expect(state.assetCopyCalls).toEqual([{draftId: "draft-1", sourcePath: "C:\\tmp\\A2 模板.dwg"}]);
});

test("复制 → 保存 → 检查 → 发布 闭环使用同一份受控副本", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {
      "draft-1": draftDocument({
        assets: [{asset_id: "layouts", kind: "layout-template", files: [{path: "", role: "A2"}]}],
      }),
    },
  });
  state.assetResults["layouts"] = inspection("layouts", ["Model", "A2"]);
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "assets");

  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\tmp\\A2 模板.dwg"; });
  await page.getByTestId("asset-file-pick-0").click();
  await expect(page.getByTestId("asset-file-path-0")).toHaveValue("assets/managed-1.dwg");

  await page.getByRole("button", {name: "保存草稿"}).click();
  await expect(page.getByTestId("editor-save-state")).toContainText("已保存");
  const savedAssets = (state.saveBodies.at(-1) as {assets: {files: {path: string}[]}[]}).assets;
  expect(savedAssets[0].files[0].path).toBe("assets/managed-1.dwg");

  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByRole("button", {name: "发布标准"})).toBeEnabled();
  await page.getByRole("button", {name: "发布标准"}).click();
  await expect(page.getByRole("region", {name: "标准详情"})).toBeVisible();
  expect(state.publishCalls).toBe(1);
});
