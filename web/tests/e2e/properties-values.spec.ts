// PLAN-DM-016 任务 3：属性值面板、搜索与三态反馈 e2e（SPEC-DM-010 P-03/P-07/P-10/P-11/P-13）。
// 覆盖：33 项原顺序平铺最多两列无分组无分页、全部 text input 38px、图纸集名称独立、
// 字段名/值搜索三模式与仅看修改取交集、活动字段暂留与隐藏修改计数、琥珀/蓝/红三态并存、
// 值对照对话框（阶段合并/Esc/焦点归还）、单项撤回、长值完整展示，以及四视口双主题无横向溢出。
// 夹具为本 spec 内联虚构数据（共享夹具由任务 6 建立），不含真实工程内容。
import {expect, test, type Page} from "@playwright/test";
import {installSheetsFixture} from "./fixtures/sheets";
import type {Workspace} from "../../src/api/contracts";

type Theme = "light" | "dark";
type InstallOptions = {
  theme?: Theme;
  initialDraft?: unknown;
  failDraftSave?: () => {code: string; message: string; fields?: Record<string, string>} | null;
};

// 33 项虚构图纸集自定义属性（P-03）：末项为长值，用于 full-width/展开编辑断言
const VALUE_ENTRIES: Array<[string, string]> = [
  ["工程名称", "城东安置房一期"],
  ["项目编号", "GC-2026-007"],
  ["设计阶段", "施工图"],
  ["出图日期", "2026-09-01"],
  ["版本号", "B"],
  ["备注", ""],
  ["比例", "1:100"],
  ["建设单位", "城东建设开发有限公司"],
  ["设计单位", "山水建筑设计院"],
  ["监理单位", "恒正工程监理"],
  ["施工单位", "宏远建设集团"],
  ["地勘单位", "岩土地质勘察"],
  ["图纸深度", "深"],
  ["保密等级", "内部"],
  ["工程地点", "城东新区纬三路"],
  ["总建筑面积", "128000.50"],
  ["地上层数", "18"],
  ["地下层数", "2"],
  ["建筑高度", "54.30"],
  ["耐火等级", "一级"],
  ["抗震设防", "7度"],
  ["结构类型", "剪力墙"],
  ["基础形式", "桩基"],
  ["人防等级", "核6级"],
  ["屋面防水", "一级"],
  ["节能标准", "75%"],
  ["PhotoCount", "42"],
  ["Phase", "phase 2"],
  ["UnitCode", "unit-a"],
  ["RevMark", "rev007"],
  ["SheetScale", "1:150"],
  ["DummyField", "占位"],
  ["LongNote", "本工程为虚构数据，仅用于属性值面板的长值展示与展开编辑测试覆盖，全部文字依次罗列以验证长文本不被截断也不丢失内容。"],
];

const SHEET_SET_NAME = "城东安置房一期";

// 预置草稿：草稿投影把「工程名称」改为草稿值（与正式基准不同 → 待写入）
const PENDING_DRAFT = {
  schema_version: 1,
  workspace_id: "workspace-1",
  base_revision_id: "revision-1",
  repair_status: "VALID",
  version: 1,
  cursor: 1,
  actions: [{
    id: "pending-1",
    kind: "command_batch",
    label: "更新图纸集",
    commands: [{
      type: "update_sheet_set",
      name: SHEET_SET_NAME,
      custom_properties: Object.fromEntries(VALUE_ENTRIES.map(([name, value]) => [name, name === "工程名称" ? "城东安置房草稿名" : value])),
    }],
  }],
};

// 在公共图纸页夹具上写入 33 项 sheetset 值与定义，并覆写打开/刷新响应；返回草稿 PUT 捕获数组
async function install(page: Page, options: InstallOptions = {}) {
  const draftBodies: unknown[] = [];
  if (options.theme) await page.addInitScript((t) => localStorage.setItem("dst-manager-theme", t), options.theme);
  const {workspace} = await installSheetsFixture(page, {
    initialDraft: options.initialDraft,
    failDraftSave: options.failDraftSave,
    onDraftPut: (body) => draftBodies.push(body),
  });
  // 后注册的路由优先：打开/刷新均返回带 33 项图纸集属性值的工作区
  const modified = JSON.parse(JSON.stringify(workspace)) as Workspace;
  modified.sheet_set.name = SHEET_SET_NAME;
  modified.sheet_set.custom_properties = Object.fromEntries(VALUE_ENTRIES);
  modified.sheet_set.property_definitions = [
    ...VALUE_ENTRIES.map(([name]) => ({type: "sheetset" as const, name, default_value: ""})),
    ...modified.sheet_set.property_definitions.filter((item) => item.type === "sheet"),
  ];
  await page.route("**/api/workspaces/open", (route) => route.fulfill({json: modified}));
  await page.route("**/api/workspaces/workspace-1", (route) => route.fulfill({json: modified}));
  return {draftBodies};
}

async function openProperties(page: Page) {
  await page.goto("/");
  await page.getByRole("button", {name: "选择 DST 文件"}).click();
  await page.getByRole("tab", {name: "属性"}).click();
  await expect(page.getByRole("textbox", {name: "属性 项目编号"})).toHaveValue("GC-2026-007");
}

function valueItem(page: Page, name: string) {
  return page.locator(".value-panel .value-item").filter({has: page.getByRole("textbox", {name: `属性 ${name}`, exact: true})});
}

test("33 项自定义属性原顺序平铺、最多两列、无分组无分页", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  // 全部 33 项都渲染为文本输入；图纸集名称是独立身份，不在 33 项内
  await expect(page.getByRole("textbox", {name: /^属性 /})).toHaveCount(33);
  // DOM 顺序 = 服务端映射顺序：名称行在最前，其后按原顺序（不排序、不分组、不补定义）
  const labels = await page.locator(".value-panel .value-item > label").allTextContents();
  expect(labels).toEqual(["图纸集名称", ...VALUE_ENTRIES.map(([name]) => name)]);
  // 最多两列（minmax(240px,360px) 双列节奏）
  const template = await page.locator(".value-panel .value-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns);
  expect(template.split(" ").length).toBe(2);
  // 无分页、无分组容器
  await expect(page.getByRole("button", {name: "上一页"})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "下一页"})).toHaveCount(0);
  await expect(page.locator(".value-panel fieldset")).toHaveCount(0);
  await expect(page.getByText("所有自定义属性均为文本")).toBeVisible();
});

test("全部输入为 38px 文本框", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  const input = page.getByRole("textbox", {name: "属性 工程名称"});
  await expect(input).toHaveAttribute("type", "text");
  const heights = await page.locator(".value-panel input:not([type='checkbox'])").evaluateAll(
    (els) => els.map((el) => Math.round(el.getBoundingClientRect().height)),
  );
  expect(heights.length).toBeGreaterThan(33);
  expect(heights.every((height) => height === 38)).toBe(true);
});

test("图纸集名称独立：不参与搜索、修改计入状态摘要与完整提交", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  const {draftBodies} = await install(page);
  await openProperties(page);
  await page.getByLabel("图纸集名称", {exact: true}).fill("城东安置房三期");
  // 名称独立标注三态（琥珀），并计入状态摘要
  const nameItem = page.locator(".value-panel .value-item.name");
  await expect(nameItem.getByText("未加入草稿")).toBeVisible();
  await expect(page.locator(".value-panel .metrics")).toContainText("未加入草稿 1 项");
  // 搜索自定义属性不影响名称行（不参与搜索）
  await page.getByRole("searchbox", {name: "搜索属性值"}).fill("监理单位");
  await expect(nameItem).toBeVisible();
  await expect(valueItem(page, "工程名称")).toHaveCount(0);
  await page.getByRole("button", {name: "清除搜索"}).click();
  // 名称修改计入一次完整提交
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect.poll(() => draftBodies.length).toBeGreaterThan(0);
  const actions = (draftBodies.at(-1) as {actions: {commands: {type: string}[]}[]}).actions;
  const command = actions.flatMap((action) => action.commands).find((item) => item.type === "update_sheet_set") as {name: string; custom_properties: Record<string, string>};
  expect(command.name).toBe("城东安置房三期");
  expect(Object.keys(command.custom_properties)).toHaveLength(33);
});

test("搜索三模式与仅看修改取交集，活动字段暂留并计入隐藏修改", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  const query = page.getByRole("searchbox", {name: "搜索属性值"});
  const mode = page.getByRole("combobox", {name: "搜索范围"});
  await page.getByRole("textbox", {name: "属性 工程名称"}).fill("修改后的工程名称");
  // 字段名或属性值（默认）：命中修改后的值
  await query.fill("修改后");
  await expect(page.locator(".value-panel .match-count")).toContainText("匹配 1 / 共 33 项");
  // 仅字段名：值命中但字段名不命中 → 不匹配；活动字段暂留并标注
  await mode.selectOption({label: "仅字段名"});
  const activeItem = valueItem(page, "工程名称");
  await expect(activeItem).toBeVisible();
  await expect(activeItem.getByText("不再匹配当前搜索")).toBeVisible();
  await expect(page.locator(".value-panel .submit-hint")).toContainText("共 1 项，其中 0 项当前未显示");
  // 结束编辑后该修改被隐藏，隐藏计数为 1
  await activeItem.getByRole("button", {name: "结束编辑"}).click();
  await expect(activeItem).toHaveCount(0);
  await expect(page.getByText("没有匹配属性")).toBeVisible();
  await expect(page.locator(".value-panel .match-count")).toContainText("1 项修改被隐藏");
  await expect(page.locator(".value-panel .submit-hint")).toContainText("共 1 项，其中 1 项当前未显示");
  // 仅属性值：重新命中
  await mode.selectOption({label: "仅属性值"});
  await expect(valueItem(page, "工程名称")).toBeVisible();
  // 仅看修改与搜索取交集：搜索命中但未修改的字段不计入
  await page.getByRole("checkbox", {name: "仅看修改"}).check();
  await query.fill("监理单位");
  await expect(page.getByText("没有匹配属性")).toBeVisible();
  await query.fill("修改后");
  await expect(valueItem(page, "工程名称")).toBeVisible();
  // 清除搜索恢复全集
  await page.getByRole("button", {name: "清除搜索"}).click();
  await expect(page.getByRole("textbox", {name: /^属性 /})).toHaveCount(33);
});

test("三态并存：琥珀未加入草稿、蓝待写入、错误边框优先且文字保留", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page, {
    initialDraft: PENDING_DRAFT,
    failDraftSave: () => ({code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {项目编号: "演示校验错误"}}),
  });
  await openProperties(page);
  // 草稿投影 ≠ 正式基准 → 待写入（蓝）
  const pendingItem = valueItem(page, "工程名称");
  await expect(pendingItem.getByText("待写入")).toBeVisible();
  await expect(pendingItem.getByRole("textbox")).not.toHaveClass(/invalid/);
  // 本地编辑 → 琥珀未加入草稿
  const dirtyItem = valueItem(page, "项目编号");
  await dirtyItem.getByRole("textbox").fill("GC-2026-009");
  await expect(dirtyItem.getByText("未加入草稿")).toBeVisible();
  // 提交失败：错误边框优先，但修改状态文字保留（保存失败重试语义：命令已在草稿栈，编辑转为待写入）
  await page.getByRole("button", {name: "更新图纸集"}).click();
  await expect(page.getByRole("alert")).toContainText("草稿保存失败");
  await expect(dirtyItem.getByText("演示校验错误")).toBeVisible();
  await expect(dirtyItem.getByText("待写入")).toBeVisible();
  await expect(dirtyItem).toHaveClass(/invalid/);
  // 错误边框颜色与无错字段不同（不只依赖颜色：错误文字与 aria-invalid 并存）
  const errorBorder = await dirtyItem.getByRole("textbox").evaluate((el) => getComputedStyle(el).borderColor);
  const normalBorder = await pendingItem.getByRole("textbox").evaluate((el) => getComputedStyle(el).borderColor);
  expect(errorBorder).not.toBe(normalBorder);
  await expect(dirtyItem.getByRole("textbox")).toHaveAttribute("aria-invalid", "true");
  // 输入 aria-describedby 关联状态与错误说明
  const describedby = await dirtyItem.getByRole("textbox").getAttribute("aria-describedby");
  expect(describedby).toContain("prop-error-");
  expect(describedby).toContain("prop-status-");
});

test("值对照对话框：三阶段对照、相同阶段合并、Esc 关闭并归还焦点", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page, {initialDraft: PENDING_DRAFT});
  await openProperties(page);
  await page.getByRole("textbox", {name: "属性 工程名称"}).fill("城东安置房当前输入");
  const trigger = page.getByRole("button", {name: "值对照 工程名称"});
  await trigger.click();
  const dialog = page.getByRole("dialog", {name: "值对照 · 工程名称"});
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("原文件值");
  await expect(dialog).toContainText("城东安置房一期");
  await expect(dialog).toContainText("草稿值");
  await expect(dialog).toContainText("城东安置房草稿名");
  await expect(dialog).toContainText("当前输入");
  await expect(dialog).toContainText("城东安置房当前输入");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  // 三阶段相同 → 合并为一个阶段展示
  await page.getByRole("button", {name: "值对照 监理单位"}).click();
  const mergedDialog = page.getByRole("dialog", {name: "值对照 · 监理单位"});
  await expect(mergedDialog).toContainText("原文件值 / 草稿值 / 当前输入");
  await expect(mergedDialog).toContainText("恒正工程监理");
  await mergedDialog.getByRole("button", {name: "关闭对照"}).click();
  await expect(mergedDialog).toHaveCount(0);
  await expect(page.getByRole("button", {name: "值对照 监理单位"})).toBeFocused();
});

test("单项撤回仅回到草稿投影值，不回到正式基准", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page, {initialDraft: PENDING_DRAFT});
  await openProperties(page);
  await page.getByRole("textbox", {name: "属性 工程名称"}).fill("城东安置房当前输入");
  await page.getByRole("button", {name: "撤回 工程名称"}).click();
  // 回到草稿投影值，不是正式基准值「城东安置房一期」
  await expect(page.getByRole("textbox", {name: "属性 工程名称"})).toHaveValue("城东安置房草稿名");
});

test("长值项整行展示且展开编辑不截断", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page);
  await openProperties(page);
  const longItem = valueItem(page, "LongNote");
  await expect(longItem).toHaveClass(/full/);
  const longValue = VALUE_ENTRIES.at(-1)![1];
  await longItem.getByRole("button", {name: "展开编辑 LongNote"}).click();
  const dialog = page.getByRole("dialog", {name: "展开编辑 · LongNote"});
  await expect(dialog).toBeVisible();
  const textarea = dialog.getByRole("textbox");
  await expect(textarea).toHaveValue(longValue);
  await textarea.fill(`${longValue}（补充）`);
  await dialog.getByRole("button", {name: "应用到输入"}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("textbox", {name: "属性 LongNote"})).toHaveValue(`${longValue}（补充）`);
  await expect(page.getByRole("textbox", {name: "属性 LongNote"})).toBeFocused();
});

// 四视口 × 双主题：属性值面板不产生整页横向溢出；窄宽度降为一列
for (const theme of ["light", "dark"] as const) {
  for (const viewport of [[1440, 900], [1120, 768], [1024, 768], [900, 768]] as const) {
    test(`无横向溢出 ${viewport[0]}×${viewport[1]} ${theme}`, async ({page}) => {
      await page.setViewportSize({width: viewport[0], height: viewport[1]});
      await install(page, {theme, initialDraft: PENDING_DRAFT});
      await openProperties(page);
      await page.getByRole("textbox", {name: "属性 项目编号"}).fill("GC-2026-009");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    });
  }
}

test("窄宽度（640px）值网格降为一列", async ({page}) => {
  await page.setViewportSize({width: 640, height: 768});
  await install(page);
  await openProperties(page);
  const template = await page.locator(".value-panel .value-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns);
  expect(template.split(" ").length).toBe(1);
});

// —— PLAN-DM-021 Task 7：英文关键矩阵（SPEC-DM-013 I18N-07/16）——
// 语言来源用 page 级路由（响应快照 ui_locale=en-US）；断言属性名与属性值原样（I18N-16）。
const enSettingsSnapshot = {
  schema_version: 1, config_revision: 1, diagnostics: [], schema_blocked: false,
  items: [{key: "ui_locale", control: "enum", value: "en-US", default: "system", source: "file", has_file_override: true,
    label_key: "settings.items.uiLocale", category_key: "settings.categories.interface",
    options: [{value: "system", text_key: "settings.locale.system"}, {value: "zh-CN", text_key: "settings.locale.zhCN"}, {value: "en-US", text_key: "settings.locale.enUS"}]}],
};

async function openPropertiesEn(page: Page) {
  await page.route("**/api/settings", (route) => route.fulfill({json: enSettingsSnapshot}));
  await page.goto("/");
  await page.getByRole("button", {name: "Select DST File"}).click();
  await page.getByRole("tab", {name: "Properties"}).click();
  await expect(page.getByRole("textbox", {name: "Property 项目编号"})).toHaveValue("GC-2026-007");
}

// 英文界面字段项定位（aria 前缀英文，属性名原样）
function valueItemEn(page: Page, name: string) {
  return page.locator(".value-panel .value-item").filter({has: page.getByRole("textbox", {name: `Property ${name}`, exact: true})});
}

test("英文界面：值面板三态、对照与展开编辑双语，属性名值原样", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await install(page, {initialDraft: PENDING_DRAFT});
  await openPropertiesEn(page);
  // 待写入（草稿）与未加入草稿（本地编辑）英文；属性值保持原样
  const pendingItem = valueItemEn(page, "工程名称");
  await expect(pendingItem.getByText("Pending write")).toBeVisible();
  await page.getByRole("textbox", {name: "Property 项目编号"}).fill("GC-2026-009");
  await expect(valueItemEn(page, "项目编号").getByText("Not in draft")).toBeVisible();
  await expect(page.locator(".value-panel .metrics")).toContainText("Not in draft: 1");
  // 搜索三模式选项英文；匹配计数英文
  await expect(page.getByRole("combobox", {name: "Search scope"})).toContainText("Field name only");
  await expect(page.getByText("Changed only")).toBeVisible();
  await page.getByRole("searchbox", {name: "Search property values"}).fill("监理单位");
  await expect(page.locator(".value-panel .match-count")).toContainText("1 matched / 33 items");
  await page.getByRole("button", {name: "Clear search"}).click();
  // 值对照对话框英文：三阶段相同合并展示，属性名与值原样
  await page.getByRole("button", {name: "Value Compare 监理单位"}).click();
  const mergedDialog = page.getByRole("dialog", {name: "Value Compare · 监理单位"});
  await expect(mergedDialog).toContainText("Base file value / Draft value / Current input");
  await expect(mergedDialog).toContainText("恒正工程监理");
  await mergedDialog.getByRole("button", {name: "Close Compare"}).click();
  // 单项撤回按钮英文（aria 含属性名，属性名原样）
  await expect(page.getByRole("button", {name: "Revert 工程名称"})).toBeVisible();
  // 展开编辑对话框英文：长值完整不截断，取消关闭
  await page.getByRole("button", {name: "Expand edit LongNote"}).click();
  const expandDialog = page.getByRole("dialog", {name: "Expand Edit · LongNote"});
  await expect(expandDialog).toBeVisible();
  await expect(expandDialog).toContainText("Edits the text input only");
  await expect(expandDialog.getByRole("textbox")).toHaveValue(VALUE_ENTRIES.at(-1)![1]);
  await expandDialog.getByRole("button", {name: "Cancel"}).click();
  await expect(expandDialog).toHaveCount(0);
});
