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
        select_file: async () => (window as any).__fakeSelectResult ?? null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
});

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

test("发布检查的问题可跳回映射表并聚焦未覆盖摘要", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {
      "draft-1": draftDocument({
        properties: [
          {name: "专业名称", scope: "sheetset", required: true, default_value: "", enum_values: ["燃气", "建筑"], description: ""},
          {name: "专业代码", scope: "sheetset", required: false, default_value: "", enum_values: [], description: ""},
        ],
        rules: [{
          rule_id: "specialty-code",
          kind: "mapping",
          target: "sheetset.专业代码",
          source: "sheetset.专业名称",
          allowed: [],
          table: [["燃气", "RQ"]],
          segments: [],
        }],
      }),
    },
  });
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByRole("button", {name: "发布检查"}).click();

  await expect(page.getByText(/映射表未覆盖源值：建筑/)).toBeVisible();
  await page.getByTestId("publish-issue-0").click();
  await expect(page.getByRole("region", {name: "字段映射"})).toBeVisible();
  await expect(page.getByTestId("mapping-uncovered-summary")).toBeFocused();
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
  await page.getByLabel("路径").fill("assets/template.dwg");
  await page.getByLabel("图幅（role）").fill("A4");
  await expect(page.getByText("有未保存修改")).toBeVisible();

  await page.getByRole("button", {name: "重新检查"}).click();
  await expect(page.getByTestId("asset-row-user-layout-template-1")).toContainText("检查通过");
  expect(state.inspectCalls).toEqual(["layout-template-1"]);
});
