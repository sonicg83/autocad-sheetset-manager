// 标准分区编辑器 e2e（PLAN-DM-035 Task 9 / SPEC-DM-016 §6–§7）。
// 覆盖：映射表批量粘贴后保存为一条规则、分区切换不丢输入、dirty 改回回到 clean 语义禁用、
// 保存失败与修订冲突保留输入、未保存离开三选一门禁、错误摘要跳转并聚焦映射行、纯键盘操作。
import {expect, test} from "@playwright/test";
import {
  draft,
  draftDocument,
  editorSaveState,
  installStandards,
  openDraftEditor,
  openEditorSection,
  openStandards,
  partialMappingDraft,
} from "./fixtures/standards";

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

test("映射批量粘贴后保存为一条规则", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": partialMappingDraft()},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "mapping");

  await expect(page.getByText("1 条字段映射规则")).toBeVisible();
  // 初始表只覆盖一个源值：结构诊断在场，保存被阻断
  await expect(editorSaveState(page)).toContainText("有未保存修改");
  await expect(page.getByRole("button", {name: "保存草稿"})).toBeDisabled();

  await page.getByRole("button", {name: "批量粘贴"}).click();
  await page.getByLabel("映射内容").fill("燃气\tRQ\n建筑\tJZ\n结构\tJG\n给排水\tGPS");
  await page.getByRole("button", {name: "应用 4 行"}).click();

  // 四个专业一行一条，仍是一条映射规则（不是四条普通规则）
  await expect(page.getByRole("row")).toHaveCount(5);
  await expect(page.getByText("1 条字段映射规则")).toBeVisible();
  await expect(page.getByText("结构检查通过")).toBeVisible();

  await page.getByRole("button", {name: "保存草稿"}).click();
  await expect(editorSaveState(page)).toHaveText("已保存");
  expect(state.saveBodies).toHaveLength(1);
  const saved = state.saveBodies[0] as {rules: Array<{kind: string; table: string[][]}>};
  expect(saved.rules).toHaveLength(2);
  const mapping = saved.rules.find(rule => rule.kind === "mapping")!;
  expect(mapping.table).toEqual([["燃气", "RQ"], ["建筑", "JZ"], ["结构", "JG"], ["给排水", "GPS"]]);
  // 保存按草稿身份走 PUT，且夹具已知该草稿文档已被覆盖
  expect(state.drafts.get("draft-1")!["rules"]).toEqual(saved.rules);
});

test("分区切换不丢输入且改回后回到 clean 语义禁用", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);

  const nameInput = page.getByLabel("标准名称");
  await expect(nameInput).toHaveValue("市政燃气施工图");
  await expect(editorSaveState(page)).toHaveText("已保存");
  const save = page.getByRole("button", {name: "保存草稿"});
  await expect(save).toHaveAttribute("aria-disabled", "true");

  await nameInput.fill("市政燃气施工图 2026");
  await expect(editorSaveState(page)).toHaveText("有未保存修改");
  await expect(save).not.toHaveAttribute("aria-disabled", "true");

  // 分区切换只改视图：输入由壳层缓冲持有，来回切换必须原样保留
  await openEditorSection(page, "properties");
  await expect(page.getByRole("region", {name: "属性定义"})).toBeVisible();
  await openEditorSection(page, "basic");
  await expect(nameInput).toHaveValue("市政燃气施工图 2026");

  // 改回基准：回到 clean，保存动作重新变成可聚焦的语义禁用
  await nameInput.fill("市政燃气施工图");
  await expect(editorSaveState(page)).toHaveText("已保存");
  await expect(save).toHaveAttribute("aria-disabled", "true");
});

test("属性定义子集作用域只显示预留说明，不提供伪编辑入口", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {
      "draft-1": draftDocument({
        properties: [
          {name: "专业名称", scope: "sheetset", required: true, default_value: "", enum_values: ["燃气"], description: ""},
          {name: "子集编号", scope: "subset", required: false, default_value: "", enum_values: [], description: ""},
        ],
      }),
    },
  });
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "properties");

  await expect(page.getByText("子集属性预留，首版不可配置。", {exact: false})).toBeVisible();
  await expect(page.getByLabel("字段键")).toHaveCount(1); // 只有非预留属性行可编辑
});

test("保存失败保留输入与 dirty 状态并可重试成功", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  state.saveFailure = {status: 500, code: "INTERNAL_ERROR", message: "服务端暂时不可用"};
  await openStandards(page);
  await openDraftEditor(page);

  const nameInput = page.getByLabel("标准名称");
  await nameInput.fill("失败的名称");
  await expect(page.getByRole("button", {name: "保存草稿"})).toBeEnabled();
  await page.getByRole("button", {name: "保存草稿"}).click();

  await expect(page.getByTestId("editor-save-error")).toBeVisible();
  await expect(nameInput).toHaveValue("失败的名称");
  await expect(editorSaveState(page)).toHaveText("有未保存修改");

  // 重试：失败原因消失后同一输入可直接保存成功
  state.saveFailure = null;
  await page.getByRole("button", {name: "保存草稿"}).click();
  await expect(editorSaveState(page)).toHaveText("已保存");
  expect(state.saveBodies).toHaveLength(2);
});

test("修订冲突给出冲突说明且不静默覆盖", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  state.saveFailure = {status: 409, code: "STANDARD_VERSION_IMMUTABLE", message: "标准 szmedi.gas@3.0.0 已发布，不可修改"};
  await openStandards(page);
  await openDraftEditor(page);

  await page.getByLabel("标准名称").fill("冲突名称");
  await expect(page.getByRole("button", {name: "保存草稿"})).toBeEnabled();
  await page.getByRole("button", {name: "保存草稿"}).click();

  const error = page.getByTestId("editor-save-error");
  await expect(error).toContainText("保存失败");
  await expect(error).toContainText("草稿已被其他操作修改");
  await expect(editorSaveState(page)).toHaveText("有未保存修改");
  expect(state.drafts.get("draft-1")!["name"]).toBe("市政燃气施工图");
});

test("未保存修改离开编辑器走三选一门禁", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByLabel("标准名称").fill("待确认名称");

  await page.getByRole("button", {name: "返回标准库"}).click();
  const gate = page.locator("dialog[open]");
  await expect(gate).toContainText("有未保存的修改");
  // 留在此处：保持编辑器与输入
  await gate.getByRole("button", {name: "留在此处"}).click();
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();
  await expect(page.getByLabel("标准名称")).toHaveValue("待确认名称");

  // 放弃输入：回到标准库详情，草稿文档未被修改
  await page.getByRole("button", {name: "返回标准库"}).click();
  await page.locator("dialog[open]").getByRole("button", {name: "放弃输入"}).click();
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toHaveCount(0);
  await expect(page.getByRole("region", {name: "标准详情"})).toBeVisible();
});

test("错误摘要跳转到映射行并聚焦首个可编辑单元格", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {
      "draft-1": draftDocument({
        rules: [{
          rule_id: "specialty-code",
          kind: "mapping",
          target: "sheetset.专业代码",
          source: "sheetset.专业名称",
          allowed: [],
          table: [["燃气", "RQ"], ["燃气", "GAS"]],
          segments: [],
        }],
      }),
    },
  });
  await openStandards(page);
  await openDraftEditor(page);

  // 壳层摘要给出行级诊断；保存动作在存在结构诊断时不可执行
  await expect(page.getByText(/结构诊断 [0-9]+ 项/)).toBeVisible();
  await expect(page.getByRole("button", {name: "保存草稿"})).toBeDisabled();
  await page.getByTestId("structure-diagnostic-0").click();

  await expect(page.getByRole("region", {name: "字段映射"})).toBeVisible();
  await expect(page.getByTestId("mapping-source-0-1")).toBeFocused();
});

test("键盘可完成分区切换与映射行编辑", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);

  await page.getByTestId("editor-section-mapping").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", {name: "字段映射"})).toBeVisible();

  await page.getByRole("button", {name: "新增一行"}).click();
  // 新增行是表尾（夹具草稿已有 3 行），键盘写入只针对它，避免改到既有行
  const source = page.getByTestId("mapping-source-0-3");
  await source.focus();
  await page.keyboard.type("燃气");
  await expect(source).toHaveValue("燃气");
  // 新增行为空单元格：仍处于 dirty 且结构诊断未清的阻断状态
  await expect(editorSaveState(page)).toContainText("有未保存修改");
});
