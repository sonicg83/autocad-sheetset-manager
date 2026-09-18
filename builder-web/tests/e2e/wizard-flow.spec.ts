// 六步引导主流程 e2e（PLAN-DB-001 Task 5；SPEC-DB-001 §2）。
// 后端全部由 backend-mock 拦截（controller 裁决）；步骤 5～6 的真实接线归 Task 9。
import {expect, test, type Page} from "@playwright/test";
import {BackendMock} from "./helpers/backend-mock";

async function gotoWizard(page: Page, mock: BackendMock): Promise<void> {
  await mock.install();
  await page.goto("/");
  await expect(page.getByTestId("wizard-shell")).toBeVisible();
}

test("六步按顺序贯通：创建项目 → 规则 → 图纸 → 模板 → 提交并确认计划 → 构建", async ({page}) => {
  const mock = new BackendMock(page, {inspect: {mode: "ok", layouts: ["Model", "A1", "A2"]}});
  await gotoWizard(page, mock);

  // 第 1 步：创建项目（未初始化状态）
  await expect(page.getByRole("heading", {name: "创建项目"})).toBeVisible();
  await page.getByLabel("项目目录").fill("D:/projects/demo");
  await page.getByLabel("工程名称").fill("示例工程");
  await page.getByLabel("阶段").fill("施工图");
  await page.getByLabel("专业").fill("建筑");
  await page.getByLabel("成果目录").fill("D:/deliveries/example-package");
  await page.getByTestId("create-project").click();
  // 创建成功后停留在第 1 步（编辑模式），由用户显式推进
  await expect(page.getByRole("heading", {name: "创建项目"})).toBeVisible();
  await expect(page.getByTestId("dock-next")).toBeEnabled();

  // 第 2 步：规则（默认草稿已带 A-/1/3/2020，示例图号可预览）
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "配置规则"})).toBeVisible();
  await expect(page.getByTestId("sheet-number-preview")).toHaveText("A-001");

  // 第 3 步：唯一图纸
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "编排图纸"})).toBeVisible();

  // 第 4 步：纳入资产并探测布局
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "匹配模板"})).toBeVisible();
  await page.getByLabel("基础 DWG 路径").fill("D:/templates/base.dwg");
  await page.getByTestId("intake-base").click();
  await expect(page.getByTestId("asset-base-info")).toContainText("aa11");
  await page.getByLabel("布局模板路径").fill("D:/templates/layout.dwg");
  await page.getByTestId("intake-layout").click();
  await expect(page.getByTestId("asset-layout-info")).toContainText("bb22");
  await page.getByTestId("inspect-layout").click();
  await page.getByLabel("源布局").selectOption("A1");

  // 第 5 步：预览 → 提交修订 → 用户显式确认（绝不自动确认）
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "构建前检查"})).toBeVisible();
  await expect(page.getByTestId("review-preview")).toContainText("A-001 首层平面图");
  await page.getByTestId("submit-revision").click();
  await expect(page.getByTestId("plan-preview")).toBeVisible();
  await expect(page.getByTestId("confirm-plan")).toBeEnabled();
  expect(mock.calls.confirm).toBe(0);
  await page.getByTestId("confirm-plan").click();
  await expect(page.getByTestId("plan-confirmed")).toBeVisible();
  expect(mock.calls.plans).toBe(1);
  expect(mock.calls.confirm).toBe(1);

  // 第 6 步：构建（mock 状态序列推进到 SUCCEEDED）——向导末步，构建成功即闭环
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "构建成果"})).toBeVisible();
  await page.getByTestId("start-build").click();
  await expect(page.getByTestId("build-status")).toHaveText(/SUCCEEDED/, {timeout: 10_000});
  expect(mock.calls.startBuild).toBe(1);
  await expect(page.getByTestId("published-path")).toContainText("example-package");
  // 末步不再有交接步：既无“下一步”，也无第 7 个导航项
  await expect(page.getByTestId("dock-next")).toBeHidden();
  await expect(page.getByTestId("rail-step-7")).toHaveCount(0);
});

test("前置门禁：未完成前置步骤时后续步骤不可进入，完成后逐步开放", async ({page}) => {
  const mock = new BackendMock(page);
  await gotoWizard(page, mock);

  for (let step = 2; step <= 6; step += 1) {
    await expect(page.getByTestId(`rail-step-${step}`)).toBeDisabled();
  }
  await expect(page.getByTestId("dock-next")).toBeDisabled();

  await page.getByLabel("工程名称").fill("示例工程");
  await page.getByLabel("阶段").fill("施工图");
  await page.getByLabel("专业").fill("建筑");
  await page.getByLabel("成果目录").fill("D:/deliveries/example-package");
  await page.getByTestId("create-project").click();
  await expect(page.getByTestId("dock-next")).toBeEnabled();

  // 默认草稿带合法规则与图名，第 2～4 步中规则/图纸已满足；第 4 步缺资产仍关门。
  await expect(page.getByTestId("rail-step-4")).toBeEnabled();
  await expect(page.getByTestId("rail-step-5")).toBeDisabled();
  await page.getByTestId("dock-next").click();
  await page.getByTestId("dock-next").click();
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "匹配模板"})).toBeVisible();
  await expect(page.getByTestId("dock-next")).toBeDisabled();
  // 前置未完成，第 5 步仍不可进入
  await expect(page.getByTestId("rail-step-5")).toBeDisabled();
});

test("已完成步骤可回访且字段值保留", async ({page}) => {
  const mock = new BackendMock(page, {initialized: true, wizardStep: 3});
  await gotoWizard(page, mock);
  await expect(page.getByRole("heading", {name: "编排图纸"})).toBeVisible();

  await page.getByTestId("rail-step-1").click();
  await expect(page.getByRole("heading", {name: "创建项目"})).toBeVisible();
  await expect(page.getByLabel("工程名称")).toHaveValue("示例工程");
  await expect(page.getByLabel("成果目录")).toHaveValue("D:/deliveries/example-package");

  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "配置规则"})).toBeVisible();
  await page.getByTestId("rail-step-3").click();
  await expect(page.getByRole("heading", {name: "编排图纸"})).toBeVisible();
  await expect(page.getByLabel("图名")).toHaveValue("首层平面图");
});

test("字段变更 500 ms 防抖保存，PATCH 携带 base_updated_at 并形成 CAS 链", async ({page}) => {
  const mock = new BackendMock(page, {initialized: true, wizardStep: 2});
  await gotoWizard(page, mock);

  const prefix = page.getByLabel("图号前缀");
  await prefix.fill("B-");
  await page.waitForTimeout(300);
  expect(mock.calls.patchDraft.length).toBe(0);
  await page.waitForTimeout(400);
  expect(mock.calls.patchDraft.length).toBeGreaterThanOrEqual(1);
  expect(mock.calls.patchDraft[0].base_updated_at).toBe("2026-09-17T08:00:00Z");

  // 保存成功后 base_updated_at 更新，下一次保存携带新值（乐观并发链）
  const nextBase = mock.state.updated_at;
  await prefix.fill("C-");
  await page.waitForTimeout(800);
  const last = mock.calls.patchDraft[mock.calls.patchDraft.length - 1];
  expect(last.base_updated_at).toBe(nextBase);
  expect((last.draft as {numbering: {prefix: string}}).numbering.prefix).toBe("C-");
});

test("重启恢复：回到保存的步骤并聚焦该步骤最后聚焦字段", async ({page}) => {
  const mock = new BackendMock(page, {
    initialized: true,
    wizardStep: 2,
    focusedField: "numbering.prefix",
  });
  await gotoWizard(page, mock);
  await expect(page.getByRole("heading", {name: "配置规则"})).toBeVisible();
  await expect(page.getByLabel("图号前缀")).toBeFocused();
});

test("重启恢复不能自动越过需用户确认的步骤 5", async ({page}) => {
  const mock = new BackendMock(page, {initialized: true, wizardStep: 7, draft: {template: {base_asset_id: "asset-base-1", layout_asset_id: "asset-layout-1", source_layout: "A1"}}});
  await gotoWizard(page, mock);
  await expect(page.getByRole("heading", {name: "构建前检查"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "构建成果"})).toBeHidden();
  // 恢复不自动提交/确认计划
  expect(mock.calls.plans).toBe(0);
  expect(mock.calls.confirm).toBe(0);
});

test("步骤 5 不自动确认：提交修订后必须由用户显式确认", async ({page}) => {
  const mock = new BackendMock(page, {initialized: true, wizardStep: 5, draft: {template: {base_asset_id: "asset-base-1", layout_asset_id: "asset-layout-1", source_layout: "A1"}}});
  await gotoWizard(page, mock);
  await expect(page.getByRole("heading", {name: "构建前检查"})).toBeVisible();
  expect(mock.calls.plans).toBe(0);
  expect(mock.calls.confirm).toBe(0);

  await page.getByTestId("submit-revision").click();
  await expect(page.getByTestId("plan-preview")).toBeVisible();
  expect(mock.calls.plans).toBe(1);
  // 提交修订不等于确认计划
  expect(mock.calls.confirm).toBe(0);
  await page.getByTestId("confirm-plan").click();
  await expect(page.getByTestId("plan-confirmed")).toBeVisible();
  expect(mock.calls.confirm).toBe(1);
});

test("构建运行中字段只读：输入禁用且无 :disabled 字面文本（Task 9 评审回归）", async ({page}) => {
  // buildSequence 停留在 BUILDING_DWG：模拟构建进行中。
  const mock = new BackendMock(page, {
    initialized: true,
    wizardStep: 5,
    draft: {template: {base_asset_id: "asset-base-1", layout_asset_id: "asset-layout-1", source_layout: "A1"}},
    buildSequence: [{status: "BUILDING_DWG", progress: 30}],
  });
  await gotoWizard(page, mock);

  // 第 5 步：提交并确认计划（构建输入冻结）
  await page.getByTestId("submit-revision").click();
  await expect(page.getByTestId("plan-preview")).toBeVisible();
  await page.getByTestId("confirm-plan").click();
  await expect(page.getByTestId("plan-confirmed")).toBeVisible();

  // 第 6 步：启动构建并停留在 BUILDING_DWG
  await page.getByTestId("dock-next").click();
  await expect(page.getByRole("heading", {name: "构建成果"})).toBeVisible();
  await page.getByTestId("start-build").click();
  await expect(page.getByTestId("build-status")).toHaveText("BUILDING_DWG", {timeout: 10_000});

  // 构建运行中：草稿字段禁用（跨步骤抽查），且页面上不得出现 ":disabled" 字面文本
  await page.getByTestId("rail-step-2").click();
  await expect(page.getByLabel("图号前缀")).toBeDisabled();
  await expect(page.getByLabel("起始序号")).toBeDisabled();
  await expect(page.getByLabel("位数")).toBeDisabled();
  await page.getByTestId("rail-step-3").click();
  await expect(page.getByLabel("图名")).toBeDisabled();
  const bodyText = await page.locator("body").textContent();
  expect(bodyText).not.toContain(":disabled");
});

test("字段诊断映射到具体控件：错误摘要获得焦点，条目可跳转聚焦对应输入", async ({page}) => {
  const mock = new BackendMock(page, {
    initialized: true,
    wizardStep: 1,
    patchBehavior: "fieldError",
    patchErrorField: "project.output_path",
    patchErrorMessage: "成果目录已存在，不能覆盖",
  });
  await gotoWizard(page, mock);

  await page.getByLabel("工程名称").fill("改名触发保存");
  const summary = page.getByTestId("field-error-summary");
  await expect(summary).toContainText("成果目录已存在，不能覆盖");
  await expect(summary).toBeFocused();

  const output = page.getByLabel("成果目录");
  await expect(output).toHaveAttribute("aria-invalid", "true");
  await summary.getByRole("button", {name: "成果目录已存在，不能覆盖"}).click();
  await expect(output).toBeFocused();
});

test("409 DRAFT_CONFLICT：提示草稿冲突且不静默覆盖", async ({page}) => {
  const mock = new BackendMock(page, {initialized: true, wizardStep: 1, patchBehavior: "conflict"});
  await gotoWizard(page, mock);

  await page.getByLabel("工程名称").fill("冲突触发");
  await expect(page.getByTestId("autosave-status")).toContainText("冲突", {timeout: 5_000});
  await expect(page.getByTestId("toast")).toContainText("冲突");
});
