// PLAN-DM-016 任务 5：CSV 渐进流程与普通草稿隔离 e2e（SPEC-DM-006 §6.2/§10.3、SPEC-DM-010 §4、P-06/P-12）。
// 覆盖：默认不显示文件选择、导入/导出菜单按需展开、UTF-8 读取、按响应顺序预览新增/跳过/冲突与行号、
// 无效数据禁用确认、读取/预览失败说明、换文件/工作区/基准修订/定义草稿变化后预览失效、
// 强确认勾选前禁用、普通未提交输入三选一且 CSV 不被自动保存、属性定义草稿与 CSV 分批阻断、
// 普通预览/写入绝不触发 CSV 导入。夹具内联虚构数据，不读取 sample/。
import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";
import type {PropertyDefinition, Workspace} from "../../src/api/contracts";

const DEFINITIONS: PropertyDefinition[] = [
  {type: "sheetset", name: "项目编号", default_value: "GC-2026-000"},
  {type: "sheetset", name: "工程名称", default_value: ""},
  {type: "sheet", name: "图幅", default_value: "A1"},
];
const SHEETSET_VALUES: Record<string, string> = {项目编号: "GC-2026-000", 工程名称: "虚构一期"};

// 安装夹具并补齐虚构定义/图纸集值；getRevision 供基准修订刷新用例动态切换 revision_id
async function install(page: Page, options: {getRevision?: () => string} = {}) {
  const {workspace} = await installSheetsFixture(page);
  const modified = JSON.parse(JSON.stringify(workspace)) as Workspace;
  modified.sheet_set.custom_properties = {...SHEETSET_VALUES};
  modified.sheet_set.property_definitions = DEFINITIONS;
  const revision = () => options.getRevision?.() ?? "revision-1";
  await page.route("**/api/workspaces/open", (r) => r.fulfill({json: {...modified, revision_id: revision()}}));
  await page.route("**/api/workspaces/workspace-1", (r) => r.fulfill({json: {...modified, revision_id: revision()}}));
  return {modified};
}

async function openProperties(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await page.getByRole("tab", {name: "属性"}).click();
  await expect(page.getByLabel("属性 项目编号")).toHaveValue("GC-2026-000");
}

// 经「导入 / 导出」菜单打开 CSV 流程区（幂等：菜单已展开或导入区已打开时直接复用）
async function openCsvFlow(page: Page) {
  if (await page.getByLabel("属性 CSV 文件").isVisible()) return;
  const trigger = page.getByRole("button", {name: "导入 / 导出"});
  if ((await trigger.getAttribute("aria-expanded")) !== "true") await trigger.click();
  await page.getByRole("button", {name: "导入 CSV"}).click();
  await expect(page.getByLabel("属性 CSV 文件")).toBeVisible();
}

function csvFile(content: string) {
  return {name: "properties.csv", mimeType: "text/csv", buffer: Buffer.from(content, "utf8")};
}

function csvPreviewBody(executable: boolean, digest = "digest-1") {
  return {
    executable,
    changes: [
      {line: 2, action: "conflict", type: "sheetset", name: "项目编号", default_value: "GC-2026-001", affected_sheet_count: 0},
      {line: 3, action: "add", type: "sheet", name: "专业", default_value: "燃气", affected_sheet_count: 5},
      {line: 4, action: "skip", type: "sheet", name: "图幅", default_value: "A1", affected_sheet_count: 0},
    ],
    diagnostics: [{line: 5, severity: "warning", code: "CUSTOM_PROPERTY_DEFAULT_EMPTY", message: "默认值为空，将导入空值"}],
    affected_files: ["test.dst"],
    execution_intent: null,
    base_revision_id: "revision-1",
    workspace_id: "workspace-1",
    preview_digest: digest,
    requires_cad: false,
    cad_version: "2020",
    commands: null,
    semantic_diff: {groups: []},
  };
}

test("默认不显示文件选择：经导入/导出菜单按需展开，未选择文件不出现预览操作", async ({page}) => {
  await install(page);
  await openProperties(page);
  await expect(page.getByLabel("属性 CSV 文件")).toBeHidden();
  // 菜单包含三个既有入口，下载模板/导出链接保持原 URL
  await page.getByRole("button", {name: "导入 / 导出"}).click();
  await expect(page.getByRole("link", {name: "下载 CSV 模板"})).toHaveAttribute("href", "/api/custom-properties/template");
  await expect(page.getByRole("link", {name: "导出当前属性"})).toHaveAttribute("href", "/api/workspaces/workspace-1/custom-properties/export");
  await expect(page.getByLabel("属性 CSV 文件")).toBeHidden();
  // 打开导入区后才出现文件选择；未选择文件不显示预览操作且确认禁用
  await openCsvFlow(page);
  await expect(page.getByRole("button", {name: "预览 CSV 导入"})).toBeHidden();
  await expect(page.getByRole("button", {name: "确认导入"})).toBeDisabled();
  await expect(page.getByText(/未选择 CSV 文件/)).toBeVisible();
  // 关闭导入区仅隐藏 UI：再打开仍可继续
  await page.getByRole("button", {name: "关闭导入"}).click();
  await expect(page.getByLabel("属性 CSV 文件")).toBeHidden();
  await openCsvFlow(page);
  await expect(page.getByLabel("属性 CSV 文件")).toBeVisible();
});

test("UTF-8 读取并按响应顺序预览新增/跳过/冲突及行号，诊断保留 code/message/severity", async ({page}) => {
  let previewCalls = 0;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => {
    previewCalls++;
    return route.fulfill({json: csvPreviewBody(true)});
  });
  await install(page);
  await openProperties(page);
  await openCsvFlow(page);
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheetset,项目编号,GC-2026-001\nsheet,专业,燃气\nsheet,图幅,A1\n"));
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator(".csv-preview")).toBeVisible();
  const rows = page.locator(".csv-preview .csv-change");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText("第 2 行");
  await expect(rows.nth(0)).toContainText("conflict");
  await expect(rows.nth(0)).toContainText("项目编号");
  await expect(rows.nth(1)).toContainText("第 3 行");
  await expect(rows.nth(1)).toContainText("add");
  await expect(rows.nth(1)).toContainText("专业");
  await expect(rows.nth(2)).toContainText("第 4 行");
  await expect(rows.nth(2)).toContainText("skip");
  // 诊断保留 code/message/severity
  await expect(page.locator(".csv-preview").getByText("CUSTOM_PROPERTY_DEFAULT_EMPTY")).toBeVisible();
  await expect(page.locator(".csv-preview").getByText("默认值为空，将导入空值")).toBeVisible();
  await expect(page.locator(".csv-preview .diagnostics .warning")).toHaveCount(1);
  await expect(page.getByRole("button", {name: "确认导入"})).toBeEnabled();
  expect(previewCalls).toBe(1);
});

test("无效数据禁用确认导入；乱码读取与预览失败均有明确说明且不请求导入", async ({page}) => {
  let previewCalls = 0, importCalls = 0;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => {
    previewCalls++;
    return route.fulfill({json: csvPreviewBody(false)});
  });
  await page.route("**/api/workspaces/workspace-1/custom-properties/import", (route) => {
    importCalls++;
    return route.abort();
  });
  await install(page);
  await openProperties(page);
  await openCsvFlow(page);
  // 乱码（非 UTF-8）：本地阻断，不请求预览
  await page.getByLabel("属性 CSV 文件").setInputFiles({name: "bad.csv", mimeType: "text/csv", buffer: Buffer.from([0x74, 0x79, 0x70, 0x65, 0x0a, 0xc3, 0x28])});
  await expect(page.getByText("CSV 必须使用 UTF-8 编码", {exact: true})).toBeVisible();
  expect(previewCalls).toBe(0);
  await expect(page.getByRole("button", {name: "确认导入"})).toBeDisabled();
  // 无效数据（executable=false）：确认禁用并有不可执行说明
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheet,,\n"));
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.getByText(/不可执行/)).toBeVisible();
  await expect(page.getByRole("button", {name: "确认导入"})).toBeDisabled();
  expect(importCalls).toBe(0);
  // 预览失败：给出错误说明且不进入确认
  await page.unroute("**/api/workspaces/workspace-1/custom-properties/import/preview");
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => route.abort());
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheet,专业,燃气\n"));
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator("main .error.notice")).toBeVisible();
  await expect(page.locator(".csv-preview")).toBeHidden();
  await expect(page.getByRole("button", {name: "确认导入"})).toBeDisabled();
  expect(importCalls).toBe(0);
});

test("换文件后旧预览失效：不显示旧结果且不能复用旧可执行标志确认新文件", async ({page}) => {
  const previews: string[] = [];
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", async (route) => {
    const body = await route.request().postDataJSON();
    const names = String(body.csv).split("\n").slice(1).filter(Boolean).map((line: string) => line.split(",")[1]);
    previews.push(names.join("|"));
    return route.fulfill({
      json: {
        ...csvPreviewBody(true, `digest-${previews.length}`),
        changes: names.map((name: string, index: number) => ({line: index + 2, action: "add", type: "sheet", name, default_value: "", affected_sheet_count: 0})),
      },
    });
  });
  await install(page);
  await openProperties(page);
  await openCsvFlow(page);
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheet,专业甲,燃气\n"));
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator(".csv-preview").getByText("专业甲")).toBeVisible();
  // 换文件：旧预览立即失效，确认禁用，不发额外请求
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheet,专业乙,给排水\n"));
  await expect(page.locator(".csv-preview")).toBeHidden();
  await expect(page.getByRole("button", {name: "确认导入"})).toBeDisabled();
  expect(previews).toHaveLength(1);
  // 重新预览后按新文件进入强确认
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator(".csv-preview").getByText("专业乙")).toBeVisible();
  await page.getByRole("button", {name: "确认导入"}).click();
  const modal = page.getByRole("dialog");
  await expect(modal).toBeVisible();
  await expect(modal.getByText(/新增属性「专业乙」/)).toBeVisible();
});

test("基准修订变化后预览失效：导入成功刷新出新基准后旧预览不可再确认", async ({page}) => {
  let revision = "revision-1";
  await install(page, {getRevision: () => revision});
  let importBody: Record<string, unknown> | null = null;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => route.fulfill({json: csvPreviewBody(true)}));
  await page.route("**/api/workspaces/workspace-1/custom-properties/import", (route) => {
    importBody = route.request().postDataJSON();
    return route.fulfill({json: {id: "csv-job", status: "SUCCEEDED", progress: 100, files: []}});
  });
  await openProperties(page);
  await openCsvFlow(page);
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheet,专业,燃气\n"));
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator(".csv-preview")).toBeVisible();
  // 强确认勾选后正式导入：请求携带原基准、冻结 CSV 与预览摘要
  await page.getByRole("button", {name: "确认导入"}).click();
  const modal = page.getByRole("dialog");
  await expect(modal.getByText("不可逆", {exact: true})).toBeVisible();
  await expect(modal.getByRole("button", {name: /确认导入/})).toBeDisabled();
  await modal.getByRole("checkbox").check();
  await modal.getByRole("button", {name: /确认导入/}).click();
  await expect.poll(() => importBody).not.toBeNull();
  expect(importBody!.base_revision_id).toBe("revision-1");
  expect(importBody!.preview_digest).toBe("digest-1");
  expect(importBody!.csv).toContain("sheet,专业,燃气");
  // 任务成功刷新出新基准 revision-2：旧预览失效，不能继续确认（重新打开导入区核对）
  revision = "revision-2";
  await expect(page.locator(".csv-preview")).toBeHidden({timeout: 5000});
  await openCsvFlow(page);
  await expect(page.locator(".csv-preview")).toBeHidden();
  await expect(page.getByRole("button", {name: "确认导入"})).toBeDisabled();
});

test("切换工作区后旧 CSV 预览不跨工作区沿用", async ({page}) => {
  await installSheetsFixture(page, {secondWorkspace: {dstPath: "C:\\虚构工程\\乙.dst", id: "workspace-2"}});
  let previewCalls = 0;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => {
    previewCalls++;
    return route.fulfill({json: csvPreviewBody(true)});
  });
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await page.getByRole("tab", {name: "属性"}).click();
  await openCsvFlow(page);
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheet,专业,燃气\n"));
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator(".csv-preview")).toBeVisible();
  // 关闭并打开另一工作区：CSV 预览上下文随基准重建失效
  await page.getByRole("button", {name: "关闭工作区"}).click();
  await page.evaluate(() => { (window as any).__fakeSelectResult = "C:\\虚构工程\\乙.dst"; });
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("虚构图纸集", {timeout: 5000});
  await page.getByRole("tab", {name: "属性"}).click();
  await openCsvFlow(page);
  await expect(page.locator(".csv-preview")).toBeHidden();
  await expect(page.getByRole("button", {name: "确认导入"})).toBeDisabled();
  expect(previewCalls).toBe(1);
});

test("影响定义的草稿命令变化使预览失效；已有属性定义草稿时确认导入按分批门禁阻断", async ({page}) => {
  let importCalls = 0;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => route.fulfill({json: csvPreviewBody(true)}));
  await page.route("**/api/workspaces/workspace-1/custom-properties/import", (route) => {
    importCalls++;
    return route.abort();
  });
  await install(page);
  await openProperties(page);
  await openCsvFlow(page);
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheet,专业,燃气\n"));
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator(".csv-preview")).toBeVisible();
  // 展开定义面板新增一条图纸属性定义命令：影响定义的投影命令变化 → 预览失效
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
  await page.getByRole("button", {name: "新增字段"}).click();
  const addForm = page.locator(".definition-panel .add-form");
  await addForm.getByLabel("属性作用域").selectOption({label: "图纸"});
  await addForm.getByLabel("属性名称").fill("备注");
  await page.getByRole("button", {name: "加入草稿"}).click();
  await expect(page.getByText(/已加入草稿/)).toBeVisible();
  await expect(page.locator(".csv-preview")).toBeHidden();
  await expect(page.getByRole("button", {name: "确认导入"})).toBeDisabled();
  // 重新预览后再确认：属性定义草稿与 CSV 导入冲突，明确阻断并要求分批，双方都不清空
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator(".csv-preview")).toBeVisible();
  await page.getByRole("button", {name: "确认导入"}).click();
  await expect(page.getByText(/与 CSV 导入必须分批/)).toBeVisible();
  expect(importCalls).toBe(0);
  await expect(page.locator(".csv-preview")).toBeVisible();
});

test("普通未提交输入必须三选一且 CSV 不被自动保存；强确认勾选前禁用", async ({page}) => {
  let importCalls = 0;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => route.fulfill({json: csvPreviewBody(true)}));
  await page.route("**/api/workspaces/workspace-1/custom-properties/import", (route) => {
    importCalls++;
    return route.abort();
  });
  await install(page);
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("虚构二期");
  await openCsvFlow(page);
  await page.getByLabel("属性 CSV 文件").setInputFiles(csvFile("type,name,default_value\nsheet,专业,燃气\n"));
  await page.getByRole("button", {name: "预览 CSV 导入"}).click();
  await expect(page.locator(".csv-preview")).toBeVisible();
  await page.getByRole("button", {name: "确认导入"}).click();
  // 三选一：留在此处不进入导入
  const dialog = page.getByRole("dialog", {name: "未提交输入"});
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "留在此处"}).click();
  expect(importCalls).toBe(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  // 加入草稿后继续：属性输入入草稿，CSV 不被自动执行，仍需强确认勾选
  await page.getByRole("button", {name: "确认导入"}).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", {name: "加入草稿后继续"}).click();
  const modal = page.getByRole("dialog");
  await expect(modal).toContainText(/确认导入属性定义/);
  expect(importCalls).toBe(0);
  await expect(modal.getByRole("button", {name: /确认导入/})).toBeDisabled();
  await modal.getByRole("checkbox").check();
  await modal.getByRole("button", {name: /确认导入/}).click();
  await expect.poll(() => importCalls).toBe(1);
});

test("全局普通预览与写入不触发 CSV 预览或导入", async ({page}) => {
  let csvPreviewCalls = 0, importCalls = 0, executeCalls = 0;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview", (route) => {
    csvPreviewCalls++;
    return route.abort();
  });
  await page.route("**/api/workspaces/workspace-1/custom-properties/import", (route) => {
    importCalls++;
    return route.abort();
  });
  await page.route("**/api/workspaces/workspace-1/changes/preview", (route) => route.fulfill({json: {executable: true, requires_cad: false, changes: [{type: "update_sheet_set", index: 0, after: {type: "update_sheet_set", name: "虚构图纸集", custom_properties: {}}}], diagnostics: [], affected_files: ["test.dst"], execution_intent: null, base_revision_id: "revision-1", workspace_id: "workspace-1", preview_digest: "digest-normal", commands: [], semantic_diff: {groups: []}, cad_version: "2020"}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute", (route) => {
    executeCalls++;
    return route.fulfill({json: {id: "normal-job", status: "SUCCEEDED", progress: 100, files: []}});
  });
  await install(page);
  await openProperties(page);
  await page.getByLabel("属性 工程名称").fill("虚构二期");
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await page.getByRole("tab", {name: "图纸"}).click();
  await page.getByRole("button", {name: "预览变更"}).click();
  await expect(page.getByText("update_sheet_set").first()).toBeVisible();
  await page.getByRole("button", {name: "收起任务浮层"}).click();
  await page.getByRole("button", {name: "确认写入"}).click();
  const modal = page.getByRole("dialog");
  await expect(modal).toContainText(/确认发布/);
  await modal.getByRole("checkbox").check();
  await modal.getByRole("button", {name: /确认发布/}).click();
  await expect.poll(() => executeCalls).toBe(1);
  expect(csvPreviewCalls).toBe(0);
  expect(importCalls).toBe(0);
});
