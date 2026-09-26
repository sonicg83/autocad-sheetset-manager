// 四阶段创建向导输入 e2e（SPEC-DM-018 §2–§5；PLAN-DM-036 Task 8）。
// 覆盖：四阶段壳与两入口、草稿恢复/重新开始、项目路径（含无壳降级）、按组复制与重排、
// 行内错误的可访问关联、批量修改（混合值与明确清空）、XLSX 导入的取消/失败/成功、
// 保存失败时返回欢迎页被拦下，以及浅深主题与键盘输入。
// 全部端点由 fixtures/creation 的 route mock 驱动（不读真实数据目录）；第四阶段
// 「检查并创建」的权威预览、执行与任务闭环由 `create-sheetset-review.spec.ts` 覆盖，
// 这里只断言四阶段导航与末阶段的接入点。
import {expect, test, type Locator, type Page} from "@playwright/test";
import {
  chooseStandard,
  creationCandidate,
  groupRow,
  installCreation,
  openCreation,
  openGroupsStep,
  publishedStandardSummary,
  unavailableCreationCandidate,
} from "./fixtures/creation";
import {installPreferenceSnapshot} from "./fixtures/settings";

test.beforeEach(async ({page}) => {
  // 与既有 spec 同型的假壳桥：文件夹选择由测试用例通过 __fakeFolder 控制
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => (window as any).__fakeSelectResult ?? null,
        select_folder: async () => (window as any).__fakeFolder ?? null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
});

/** 新建图纸组的标题输入（行内第一个文本输入；张数是 number 输入）。 */
function rowTitle(page: Page, groupId: string) {
  return groupRow(page, groupId).locator('input[type="text"]').first();
}
function rowCount(page: Page, groupId: string) {
  return groupRow(page, groupId).locator('input[type="number"]');
}
async function rowOrder(page: Page): Promise<string[]> {
  return page.locator("tbody tr").evaluateAll(rows =>
    rows.map(row => (row as HTMLElement).dataset["groupId"] ?? ""),
  );
}
async function noPageOverflow(page: Page, label: string): Promise<void> {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth, label).toBeLessThanOrEqual(clientWidth);
}

test("欢迎页入口进入第一阶段，只列可用标准且四阶段导航可读", async ({page}) => {
  await installCreation(page, {candidates: [creationCandidate(), unavailableCreationCandidate()]});
  await openCreation(page);

  await expect(page.getByRole("region", {name: "选择标准"})).toBeVisible();
  const list = page.getByTestId("creation-standard-list");
  await expect(list.getByRole("button")).toHaveCount(1);
  await expect(list.getByText("市政燃气施工图")).toBeVisible();
  // 不可用候选不进列表：它只在「无可用标准」时以原因呈现
  await expect(page.getByText("旧版市政模板")).toHaveCount(0);

  const stepper = page.getByTestId("creation-stepper");
  for (const label of ["选择标准", "项目信息", "图纸组", "检查并创建"]) {
    await expect(stepper.getByText(label)).toBeVisible();
  }
  await expect(stepper.locator('[aria-current="step"]')).toHaveText(/1\s*选择标准/);
  // 尚未建立草稿：下一步与 XLSX 入口不可用，且不会无标准创建
  await expect(page.getByRole("button", {name: "下一步"})).toBeDisabled();
  await expect(page.getByRole("button", {name: "XLSX 批量录入"})).toBeDisabled();
});

test("无可用标准时说明原因并可前往标准库", async ({page}) => {
  await installCreation(page, {candidates: [unavailableCreationCandidate()]});
  await openCreation(page);

  await expect(page.getByText("当前没有可用于创建的标准", {exact: false})).toBeVisible();
  await expect(page.getByText("标准资产 'layout-a' 声明的文件", {exact: false})).toBeVisible();
  await page.getByRole("button", {name: "前往标准库"}).click();
  await expect(page.getByRole("heading", {name: "标准管理"})).toBeVisible();
});

test("标准详情「用于创建」固定发布版本并直接进入第二阶段", async ({page}) => {
  const state = await installCreation(page, {standardsList: [publishedStandardSummary()]});
  await page.goto("/");
  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await page.getByTestId("library-item").filter({hasText: "市政燃气施工图"}).click();
  await page.getByRole("button", {name: "用于创建图纸集"}).click();

  // 直接落到第二阶段，且草稿固定的标准身份来自详情（不要求重复选择）
  await expect(page.getByRole("region", {name: "项目信息"})).toBeVisible();
  await expect(page.getByTestId("creation-fixed-standard")).toContainText("szmedi.gas");
  expect(state.createBodies).toEqual([{standard_id: "szmedi.gas", version: 1}]);
  await expect(page.getByTestId("creation-stepper").locator('[aria-current="step"]')).toHaveText(/2\s*项目信息/);
});

test("项目信息按标准动态生成属性，目录名合成完整路径", async ({page}) => {
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);

  // 普通属性：文本 + 枚举，必填与标准默认值可见；派生属性只读且无输入控件
  await expect(page.getByLabel("工程名称")).toHaveValue("");
  await expect(page.getByLabel("专业")).toHaveValue("燃气");
  await expect(page.getByText("必填 · 标准默认值：燃气")).toBeVisible();
  await expect(page.getByText("专业代码")).toBeVisible();
  await expect(page.getByText("待计算")).toBeVisible();

  // 目录名初值为「新建项目」；选择上一级目录后展示拼接后的完整最终路径
  await expect(page.getByLabel("项目目录名")).toHaveValue("新建项目");
  await page.evaluate(() => {(window as any).__fakeFolder = "D:\\项目\\";});
  await page.getByRole("button", {name: "选择目录"}).click();
  await expect(page.getByLabel("上一级目录")).toHaveValue("D:\\项目\\");
  await expect(page.getByTestId("creation-final-path")).toHaveText("D:\\项目\\新建项目");
  await page.getByLabel("项目目录名").fill("滨河路新建项目");
  await expect(page.getByTestId("creation-final-path")).toHaveText("D:\\项目\\滨河路新建项目");
  // 用户清空属性后不自动回填标准默认值
  await page.getByLabel("专业").selectOption("");
  await expect(page.getByLabel("专业")).toHaveValue("");
});

test("无桌面壳时保留手动路径输入并说明原因", async ({page}) => {
  await page.addInitScript(() => {(window as any).pywebview = undefined;});
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);

  await expect(page.getByRole("button", {name: "选择目录"})).toBeDisabled();
  await expect(page.getByText("当前环境没有桌面壳", {exact: false})).toBeVisible();
  await page.getByLabel("上一级目录").fill("C:\\workspace");
  await expect(page.getByTestId("creation-final-path")).toHaveText("C:\\workspace\\新建项目");
});

test("新建图纸组复制最近创建的组，重排后仍按创建序复制且不自动改名", async ({page}) => {
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);

  // 首个组取标准默认值（张数 1、模板与图幅来自标准候选、sheet 属性默认值）
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await expect(groupRow(page, "group-1")).toBeVisible();
  await expect(rowCount(page, "group-1")).toHaveValue("1");
  await expect(groupRow(page, "group-1").getByLabel(/基础模板$/)).toHaveValue("base-a");
  await expect(groupRow(page, "group-1").getByLabel(/图幅$/)).toHaveValue("A2");
  // 新建后焦点落在图名输入（可直接改名）
  await expect(rowTitle(page, "group-1")).toBeFocused();

  await page.getByRole("button", {name: "新建图纸组"}).click();
  await rowTitle(page, "group-2").fill("平面图");
  await rowCount(page, "group-2").fill("3");

  // 重排：只改数组顺序，不改变创建序
  await groupRow(page, "group-2").getByRole("button", {name: "上移第 2 组"}).click();
  expect(await rowOrder(page)).toEqual(["group-2", "group-1"]);

  // 复制「最近创建」（创建序最大）的组：重排后依然是 group-2 的输入
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await expect(rowTitle(page, "group-3")).toHaveValue("平面图");
  await expect(rowCount(page, "group-3")).toHaveValue("3");
  // 未改名而与原组重复：直接标错、不自动追加序号
  await expect(groupRow(page, "group-3").getByText("图名与其他图纸组重复（去首尾空格、大小写不敏感）")).toBeVisible();
  await expect(rowTitle(page, "group-2")).toHaveValue("平面图");
  await expect(rowTitle(page, "group-3")).toHaveValue("平面图");

  // 首末行禁用正确（当前顺序：group-2、group-1、group-3）
  expect(await rowOrder(page)).toEqual(["group-2", "group-1", "group-3"]);
  await expect(groupRow(page, "group-2").getByRole("button", {name: "上移第 1 组"})).toBeDisabled();
  await expect(groupRow(page, "group-3").getByRole("button", {name: "下移第 3 组"})).toBeDisabled();

  // 改名后错误消失；删除组后汇总同步
  await rowTitle(page, "group-3").fill("纵断面图");
  await expect(groupRow(page, "group-3").getByText("图名与其他图纸组重复", {exact: false})).toHaveCount(0);
  await groupRow(page, "group-1").getByRole("button", {name: /删除第 \d+ 组/}).click();
  await expect(groupRow(page, "group-1")).toHaveCount(0);
  await expect(page.getByTestId("creation-group-summary")).toHaveText("2 组 · 6 张");
});

test("行内错误经 aria-describedby 关联到对应输入，聚焦即可朗读原因", async ({page}) => {
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);

  await page.getByRole("button", {name: "新建图纸组"}).click();
  await rowTitle(page, "group-1").fill("平面图");
  // 新建组复制最近创建的组：未改名而同名 → 两行都标错，且各行的图名输入都有 describedby
  await page.getByRole("button", {name: "新建图纸组"}).click();
  expect(await rowOrder(page)).toEqual(["group-1", "group-2"]);
  await expect(rowTitle(page, "group-2")).toHaveValue("平面图");

  // 每行的错误列表有稳定 id；该行图名/张数/模板/图幅控件指向它（不是只给 aria-invalid）
  const issues = page.locator("#creation-group-issues-group-1");
  await expect(issues).toBeVisible();
  await expect(issues).toContainText("图名与其他图纸组重复（去首尾空格、大小写不敏感）");

  const title = rowTitle(page, "group-1");
  await title.focus();
  await expect(title).toBeFocused();
  await expect(title).toHaveAttribute("aria-invalid", "true");
  await expect(title).toHaveAttribute("aria-describedby", "creation-group-issues-group-1");
  // 键盘聚焦即可获得原因（可访问描述来自该行的错误列表）
  await expect(title).toHaveAccessibleDescription("图名与其他图纸组重复（去首尾空格、大小写不敏感）");
  for (const control of [
    rowCount(page, "group-1"),
    groupRow(page, "group-1").getByLabel(/基础模板$/),
    groupRow(page, "group-1").getByLabel(/布局模板$/),
    groupRow(page, "group-1").getByLabel(/图幅$/),
  ]) {
    await expect(control).toHaveAttribute("aria-describedby", "creation-group-issues-group-1");
  }

  // 改名消除错误后不再指向空的错误列表（不留悬空 id 引用）
  await title.fill("封面");
  await expect(issues).toHaveCount(0);
  await expect(title).not.toHaveAttribute("aria-describedby", /creation-group-issues/);
});

test("批量修改只作用选中组，混合值与明确清空可区分", async ({page}) => {
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);

  await page.getByRole("button", {name: "新建图纸组"}).click();
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await rowTitle(page, "group-1").fill("封面");
  await rowTitle(page, "group-2").fill("平面图");
  await rowTitle(page, "group-3").fill("纵断面图");
  await groupRow(page, "group-2").getByLabel(/图纸阶段$/).selectOption("竣工图");

  // 只选第 1、2 组：字段列表不含图名，当前值不一致显示「值不相同」
  await groupRow(page, "group-1").getByRole("checkbox").check();
  await groupRow(page, "group-2").getByRole("checkbox").check();
  await page.getByRole("button", {name: "批量修改"}).click();
  const dialog = page.getByRole("dialog", {name: "批量修改选中图纸组"});
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("option", {name: "图名"})).toHaveCount(0);
  await dialog.getByLabel("字段").selectOption("prop-stage");
  await expect(page.getByTestId("creation-batch-state")).toContainText("已选 2 组");
  await expect(page.getByTestId("creation-batch-state")).toContainText("值不相同");

  // 未填写的新值不是清空：应用按钮保持禁用
  await expect(dialog.getByRole("button", {name: "应用到选中组"})).toBeDisabled();
  // 明确清空只作用选中组
  await dialog.getByRole("button", {name: "明确清空"}).click();
  await expect(dialog).toHaveCount(0);
  await expect(groupRow(page, "group-1").getByLabel(/图纸阶段$/)).toHaveValue("");
  await expect(groupRow(page, "group-2").getByLabel(/图纸阶段$/)).toHaveValue("");
  await expect(groupRow(page, "group-3").getByLabel(/图纸阶段$/)).toHaveValue("施工图");

  // 一次应用新值：同样只作用选中组
  await page.getByRole("button", {name: "批量修改"}).click();
  await dialog.getByLabel("字段").selectOption("count");
  await dialog.getByLabel("新值").fill("4");
  await dialog.getByRole("button", {name: "应用到选中组"}).click();
  await expect(rowCount(page, "group-1")).toHaveValue("4");
  await expect(rowCount(page, "group-2")).toHaveValue("4");
  await expect(rowCount(page, "group-3")).toHaveValue("1");
});

test("草稿恢复提示继续或重新开始，重新开始须确认并放弃草稿", async ({page}) => {
  const state = await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await rowTitle(page, "group-1").fill("封面");
  // 返回欢迎页前先落盘：草稿不得因离开而静默丢失
  await page.getByRole("button", {name: "返回欢迎页"}).click();
  await expect(page.getByRole("heading", {name: "打开图纸集"})).toBeVisible();
  await expect.poll(() => state.saveBodies.length).toBeGreaterThan(0);

  await page.getByRole("button", {name: "创建新图纸集"}).click();
  const banner = page.getByTestId("creation-resume-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("已恢复未完成的创建草稿");
  await expect(page.getByRole("region", {name: "图纸组"})).toBeVisible();
  await expect(rowTitle(page, "group-1")).toHaveValue("封面");

  await banner.getByRole("button", {name: "继续草稿"}).click();
  await expect(banner).toHaveCount(0);
  await expect(rowTitle(page, "group-1")).toHaveValue("封面");

  // 重新开始：先确认，确认后才删除草稿并回到第一阶段
  await page.getByRole("button", {name: "重新开始"}).click();
  const confirm = page.getByRole("dialog", {name: "重新开始创建？"});
  await expect(confirm).toBeVisible();
  expect(state.deleted).toEqual([]);
  await confirm.getByRole("button", {name: "取消"}).click();
  expect(state.deleted).toEqual([]);
  await expect(rowTitle(page, "group-1")).toHaveValue("封面");

  await page.getByRole("button", {name: "重新开始"}).click();
  await page.getByRole("dialog", {name: "重新开始创建？"}).getByRole("button", {name: "放弃并重新开始"}).click();
  await expect(page.getByRole("region", {name: "选择标准"})).toBeVisible();
  expect(state.deleted).toEqual(["draft-1"]);
});

test("切换标准先提示再清除不兼容输入，不静默迁移", async ({page}) => {
  const second = creationCandidate({standard_id: "user.b", version: 2, name: "建筑设计图纸标准"});
  await installCreation(page, {candidates: [creationCandidate(), second]});
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await rowTitle(page, "group-1").fill("封面");

  await page.getByRole("button", {name: "上一步"}).click();
  await page.getByRole("button", {name: "上一步"}).click();
  await expect(page.getByRole("region", {name: "选择标准"})).toBeVisible();
  await page.getByTestId("creation-standard-list").getByRole("button").filter({hasText: "建筑设计图纸标准"}).click();
  const confirm = page.getByRole("dialog", {name: "切换图纸标准？"});
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", {name: "取消"}).click();
  // 取消保留当前草稿与输入（仍在第一阶段，未清除）
  await expect(page.getByTestId("creation-fixed-standard")).toContainText("szmedi.gas");

  await page.getByTestId("creation-standard-list").getByRole("button").filter({hasText: "建筑设计图纸标准"}).click();
  await page.getByRole("dialog", {name: "切换图纸标准？"}).getByRole("button", {name: "切换标准"}).click();
  await expect(page.getByRole("region", {name: "项目信息"})).toBeVisible();
  await expect(page.getByTestId("creation-fixed-standard")).toContainText("user.b");
});

test("保存失败时返回欢迎页被拦下，草稿与输入都不丢", async ({page}) => {
  const state = await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await page.getByLabel("工程名称").fill("滨河路改造工程");

  // 保存被拒（草稿修订冲突）：返回欢迎页必须先落盘，失败则留在当前页并显示错误
  state.saveFailure = {
    status: 409,
    body: {
      code: "CREATION_DRAFT_CONFLICT",
      message_key: "errors.creation.draftConflict",
      message: "修订冲突",
    },
  };
  await page.getByRole("button", {name: "返回欢迎页"}).click();
  await expect(page.getByTestId("creation-error")).toHaveText("创建草稿已被其他操作修改，请刷新后重试");
  await expect(page.getByRole("region", {name: "创建新图纸集"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "打开图纸集"})).toHaveCount(0);
  // 输入与草稿都没变：失败的保存不写草稿，界面也不清空
  await expect(page.getByLabel("工程名称")).toHaveValue("滨河路改造工程");
  expect(state.saveBodies).toHaveLength(1);
  expect(state.drafts.get("draft-1")?.sheetset_values["prop-name"]).toBe("");

  // 保存恢复后照常离开，且输入确实落盘
  state.saveFailure = null;
  await page.getByRole("button", {name: "返回欢迎页"}).click();
  await expect(page.getByRole("heading", {name: "打开图纸集"})).toBeVisible();
  await expect.poll(() => state.drafts.get("draft-1")?.sheetset_values["prop-name"]).toBe("滨河路改造工程");
});

test("XLSX 导入取消不发写请求，失败可定位且草稿零变更", async ({page}) => {
  const state = await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await page.getByLabel("上一级目录").fill("D:\\项目");

  await page.getByRole("button", {name: "XLSX 批量录入"}).click();
  const dialog = page.getByRole("dialog", {name: "XLSX 批量录入"});
  await expect(dialog).toBeVisible();
  // 模板下载地址指向固定标准版本的受控模板（不点击下载，只核对地址）
  await expect(page.getByTestId("creation-xlsx-template")).toHaveAttribute("href", "/api/creation-drafts/draft-1/xlsx-template");
  await page.getByTestId("creation-xlsx-file").setInputFiles({
    name: "creation.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("stub"),
  });
  await expect(page.getByTestId("creation-xlsx-filename")).toHaveText("creation.xlsx");

  // 已有输入：先提醒全量覆盖；取消不发任何写请求
  await dialog.getByRole("button", {name: "开始导入"}).click();
  const confirm = page.getByRole("dialog", {name: "覆盖当前草稿？"});
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText("不比较差异");
  await confirm.getByRole("button", {name: "取消"}).click();
  expect(state.importAttempts).toBe(0);

  // 确认导入但整批被拒：按工作表/行/列定位，草稿与预览状态不变
  await dialog.getByRole("button", {name: "开始导入"}).click();
  await page.getByRole("dialog", {name: "覆盖当前草稿？"}).getByRole("button", {name: "覆盖并导入"}).click();
  await expect.poll(() => state.importAttempts).toBe(1);
  const diagnostics = page.getByTestId("creation-xlsx-diagnostics");
  await expect(diagnostics).toBeVisible();
  await expect(diagnostics).toContainText("工作表 Sheet · 第 3 行 · 列 E");
  await expect(diagnostics).toContainText("图幅不在所选布局模板的布局内");
  await expect(diagnostics).toContainText("工作表 SheetSet · 第 5 行 · 列 B");
  await expect(page.getByText("导入未完成：草稿与预览保持原样。")).toBeVisible();
  await dialog.getByRole("button", {name: "取消"}).click();
  await expect(page.getByRole("region", {name: "项目信息"})).toBeVisible();
  await expect(page.getByTestId("creation-final-path")).toHaveText("D:\\项目\\新建项目");

  // 成功导入：一次性替换输入并使旧预览失效
  state.importFailure = null;
  await page.getByRole("button", {name: "XLSX 批量录入"}).click();
  await page.getByTestId("creation-xlsx-file").setInputFiles({
    name: "creation-ok.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("stub"),
  });
  await dialog.getByRole("button", {name: "开始导入"}).click();
  await page.getByRole("dialog", {name: "覆盖当前草稿？"}).getByRole("button", {name: "覆盖并导入"}).click();
  await expect(page.getByText("导入成功：项目属性、项目路径和全部图纸组已被替换", {exact: false})).toBeVisible();
  await dialog.getByRole("button", {name: "取消"}).click();
  await expect(page.getByRole("region", {name: "图纸组"})).toBeVisible();
  await expect(rowTitle(page, "xlsx-2")).toHaveValue("封面");
  await expect(rowCount(page, "xlsx-3")).toHaveValue("2");
  await page.getByRole("button", {name: "上一步"}).click();
  await expect(page.getByLabel("工程名称")).toHaveValue("滨河路改造工程");
  await expect(page.getByTestId("creation-final-path")).toHaveText("D:\\导入项目\\滨河路新建项目");
});

test("第四阶段接入权威预览，键盘输入即时清除错误", async ({page}) => {
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);

  // 键盘输入：新建组后直接键入图名，图名错误随输入消失
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await expect(groupRow(page, "group-1").getByText("图名不能为空")).toBeVisible();
  await page.keyboard.type("封面");
  await expect(rowTitle(page, "group-1")).toHaveValue("封面");
  await expect(groupRow(page, "group-1").getByText("图名不能为空")).toHaveCount(0);

  await page.getByRole("button", {name: "下一步"}).click();
  await expect(page.getByRole("region", {name: "检查并创建"})).toBeVisible();
  // 第四阶段由 Task 9 接入后端权威预览：占位说明已被按组主表取代
  await expect(page.getByTestId("creation-preview-table")).toBeVisible();
  await expect(page.getByTestId("creation-stepper").locator('[aria-current="step"]')).toHaveText(/4\s*检查并创建/);
  // 末阶段不再提供下一步；返回可回到上一阶段
  await expect(page.getByRole("button", {name: "下一步"})).toBeDisabled();
  await page.getByRole("button", {name: "上一步"}).click();
  await expect(page.getByRole("region", {name: "图纸组"})).toBeVisible();
});

test("浅深主题与 900×768 下向导无整页横向溢出", async ({page}) => {
  for (const theme of ["light", "dark"] as const) {
    await installPreferenceSnapshot(page, theme);
    await installCreation(page);
    await page.setViewportSize({width: 900, height: 768});
    // 轮次之间清掉本地草稿身份：否则第二轮会拿上一轮的 ID 去恢复新夹具里不存在的草稿
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await openCreation(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.getByRole("region", {name: "创建新图纸集"})).toBeVisible();
    await noPageOverflow(page, `选择标准 ${theme} 900x768`);
    await chooseStandard(page);
    await noPageOverflow(page, `项目信息 ${theme} 900x768`);
    await openGroupsStep(page);
    await page.getByRole("button", {name: "新建图纸组"}).click();
    await noPageOverflow(page, `图纸组 ${theme} 900x768`);
    // 主表自身可横向滚动（页面整体不溢出）
    const scroll = await page.locator(".table-scroll").evaluate(el => getComputedStyle(el).overflowX);
    expect(scroll).toBe("auto");
  }
});

test("标准候选加载失败给出稳定错误且不伪造空库", async ({page}) => {
  await installCreation(page, {listFails: true});
  await openCreation(page);
  await expect(page.getByText("标准候选加载失败", {exact: false})).toBeVisible();
  await expect(page.getByText("当前没有可用于创建的标准", {exact: false})).toHaveCount(0);
  await expect(page.getByTestId("creation-standard-list")).toHaveCount(0);
});

/** 同一行内所有可交互控件（含复选命中区与行操作按钮）的垂直中点最大差值。 */
async function controlCenterSpread(row: Locator): Promise<number> {
  return row.evaluate((tr) => {
    const centers = [...tr.querySelectorAll("input, select, button, .select-hit")]
      .map((element) => element.getBoundingClientRect())
      .filter((rect) => rect.height > 0)
      .map((rect) => rect.top + rect.height / 2);
    return centers.length === 0 ? 0 : Math.max(...centers) - Math.min(...centers);
  });
}

// PLAN-DM-043 Task 3：分组编辑表同为常驻 38px 输入框的编辑表，取 48px 基础档。
test("分组编辑表 48px 档与出错行增高（同行中点对齐 ≤1px）", async ({page}) => {
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await rowTitle(page, "group-1").fill("平面图");
  const table = page.getByRole("table", {name: "图纸组编辑表"});
  expect(
    Math.round(await table.locator("thead th").first().evaluate((element) => element.getBoundingClientRect().height)),
    "表头与同表普通编辑行采用同一基础档",
  ).toBe(48);
  const row = groupRow(page, "group-1");
  expect(
    Math.round(await row.locator("td").first().evaluate((element) => element.getBoundingClientRect().height)),
    "常驻编辑行取 48px 基础档",
  ).toBe(48);
  expect(
    Math.round(await rowTitle(page, "group-1").evaluate((element) => element.getBoundingClientRect().height)),
    "编辑控件保持 38px 表单档",
  ).toBe(38);
  expect(await controlCenterSpread(row), "同行控件与复选命中区垂直中点差 ≤1px").toBeLessThanOrEqual(1);
  // 同名第二组触发行内错误：该行按内容增高、整行同档对齐且错误列表不被裁切
  await page.getByRole("button", {name: "新建图纸组"}).click();
  const errorRow = groupRow(page, "group-2");
  const issues = errorRow.locator(".row-issues");
  await expect(issues, "出错行必须出现行内错误列表").toBeVisible();
  expect(
    Math.round(await errorRow.evaluate((element) => element.getBoundingClientRect().height)),
    "出错行按内容增高，不受 48px 下限裁切",
  ).toBeGreaterThan(48);
  expect(await controlCenterSpread(errorRow), "整个出错行同档对齐后中点差仍 ≤1px").toBeLessThanOrEqual(1);
  expect(
    await errorRow.evaluate((tr) => {
      const list = tr.querySelector(".row-issues");
      return list !== null && tr.getBoundingClientRect().bottom >= list.getBoundingClientRect().bottom;
    }),
    "错误列表不得被行裁切",
  ).toBe(true);
});

test("分组编辑表在 900×768 下不产生整页横溢且行控件可达", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installCreation(page);
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);
  await page.getByRole("button", {name: "新建图纸组"}).click();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "900px 宽下不得整页横滚（表格自身横向滚动）").toBeLessThanOrEqual(1);
  const title = rowTitle(page, "group-1");
  await title.scrollIntoViewIfNeeded();
  await expect(title).toBeInViewport();
});
