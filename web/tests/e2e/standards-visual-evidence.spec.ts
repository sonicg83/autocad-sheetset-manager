// 图纸标准平台视觉证据（PLAN-DM-035 Task 11 / SPEC-DM-016 §12.2）。
// G4 冻结状态集：欢迎页、标准库、普通属性、派生属性、DWG 命名、模板资产、发布错误页、
// 发布成功详情（八态，1440×900 浅色），另加四态补充（欢迎页深色、标准库深色、
// DWG 命名 900×768 窄视口、发布错误页深色）。
//
// 与冻结设计逐对比对：本 spec 的同一状态集既可写 G4 冻结件，也可写 G8 生产证据
// （`DST_MANAGER_STANDARDS_EVIDENCE=g4|production`），两次运行使用完全相同的夹具数据、
// 主题与视口；比对与裁决记在 docs/dst-manager/specs/assets/SPEC-DM-016/README.md。
// 默认只留测试附件，不自动改写仓库文件（避免常规回归覆盖验收资产）。
//
// 用例内固定时钟（检查时间戳可复现）并禁用动画、等待字体就绪，保证两次抓图可比。
import {copyFileSync, mkdirSync} from "node:fs";
import path from "node:path";
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {installPreferenceSnapshot} from "./fixtures/settings";
import {draft, draftDocument, installStandards, libraryItems, openDraftEditor, openEditorSection, openStandards, published} from "./fixtures/standards";

const EVIDENCE_ROOT = path.resolve(process.cwd(), "..", "docs", "dst-manager", "specs", "assets", "SPEC-DM-016");
const EVIDENCE_TARGET = process.env.DST_MANAGER_STANDARDS_EVIDENCE;
// PLAN-DM-039：候选证据先写入计划资产目录（`.planning/memos/...`），经用户对照 Demo 裁决后才
// 用 `g4` / `production` 晋升为冻结件与生产证据——候选模式绝不覆盖 G4/production。
const EVIDENCE_DIR = EVIDENCE_TARGET === "plan-dm-039"
  ? path.resolve(process.cwd(), "..", ".planning", "memos", "dst-manager", "assets", "PLAN-DM-039")
  : EVIDENCE_TARGET === "production"
    ? path.join(EVIDENCE_ROOT, "production")
    : EVIDENCE_TARGET === "g4" ? EVIDENCE_ROOT : null;

/** 视觉证据固定注入的资产检查结果与文档（与 `draftDocument` 声明一致）。 */
function visualDraft(): Record<string, unknown> {
  return draftDocument({
    properties: [
      {
        property_id: "prop-major",
        name: "专业",
        scope: "sheetset",
        kind: "enum",
        required: true,
        default_value: "燃气",
        enum_items: [
          {item_id: "enum-gas", value: "燃气"},
          {item_id: "enum-jz", value: "建筑"},
          {item_id: "enum-jg", value: "结构"},
        ],
      },
      {
        property_id: "prop-code",
        name: "专业代码",
        scope: "sheetset",
        kind: "mapping",
        source_property_id: "prop-major",
        mapping: [
          {item_id: "enum-gas", value: "RQ"},
          {item_id: "enum-jz", value: "JZ"},
          {item_id: "enum-jg", value: "JG"},
        ],
        confirmed_source_items: [["enum-gas", "燃气"], ["enum-jz", "建筑"], ["enum-jg", "结构"]],
      },
      {
        property_id: "prop-frame",
        name: "图幅",
        scope: "sheetset",
        kind: "enum",
        default_value: "A3",
        enum_items: [{item_id: "enum-a2", value: "A2"}, {item_id: "enum-a3", value: "A3"}],
      },
      {
        property_id: "prop-label",
        name: "图签",
        scope: "sheet",
        kind: "composition",
        segments: [{property_id: "prop-code"}, {literal: " "}, {system_field: "sheet.number"}],
      },
    ],
    assets: [
      {
        asset_id: "layouts",
        kind: "layout-template",
        files: [
          {path: "assets/layout-a2.dwg", role: "A2"},
          {path: "assets/layout-a3.dwg", role: "A3"},
        ],
      },
    ],
  });
}

/** 与视觉草案同数据但「结构」没有映射目标：用于发布错误页状态。 */
function visualDraftWithMappingGap(): Record<string, unknown> {
  const document = visualDraft();
  const properties = document.properties as Array<{property_id: string; mapping?: Array<{item_id: string; value: string}>}>;
  const code = properties.find(item => item.property_id === "prop-code")!;
  code.mapping = code.mapping!.map(row => (row.item_id === "enum-jg" ? {...row, value: ""} : row));
  return document;
}

async function stable(page: Page, theme: "light" | "dark"): Promise<void> {
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await page.evaluate(() => document.fonts.ready);
  // 移除活动焦点：光标闪烁与焦点环都是渲染层时序，会让同一状态的两次抓图产生局部像素差
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur?.());
  await page.mouse.move(0, 0);
}

async function shot(page: Page, info: TestInfo, name: string): Promise<void> {
  const screenshotPath = info.outputPath(`${name}.png`);
  await page.screenshot({path: screenshotPath, animations: "disabled"});
  await info.attach(`${name}.png`, {path: screenshotPath, contentType: "image/png"});
  if (EVIDENCE_DIR !== null) {
    mkdirSync(EVIDENCE_DIR, {recursive: true});
    copyFileSync(screenshotPath, path.join(EVIDENCE_DIR, `${name}.png`));
  }
}

test.beforeEach(async ({page}) => {
  await page.clock.setFixedTime(new Date("2026-09-22T10:00:00"));
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

test("G4 八态：1440×900 浅色（欢迎页/标准库/属性/映射/组合/资产/发布错误/发布成功）", async ({page}, info) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installPreferenceSnapshot(page, "light");
  const state = await installStandards(page, [
    published("official", "2.1.0"),
    published("user", "2.0.0"),
    draft("草稿 1", "draft-1"),
  ], {
    drafts: {"draft-1": visualDraft()},
    assetResults: {layouts: {asset_id: "layouts", kind: "layout-template", layouts: ["Model", "A2", "A3"], diagnostics: []}},
  });
  expect(state.list).toHaveLength(3);

  await page.goto("/");
  await stable(page, "light");
  await expect(page.getByRole("heading", {name: "打开图纸集"})).toBeVisible();
  await shot(page, info, "g4-01-welcome-light-1440x900");

  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(page.getByRole("heading", {name: "标准管理"})).toBeVisible();
  await expect(libraryItems(page)).toHaveCount(3);
  await shot(page, info, "g4-02-library-light-1440x900");

  await openDraftEditor(page);
  await expect(page.getByTestId("editor-save-state")).toHaveText("已保存");
  await openEditorSection(page, "ordinary");
  await expect(page.getByTestId("ordinary-table")).toBeVisible();
  await shot(page, info, "g4-03-ordinary-light-1440x900");

  await openEditorSection(page, "derived");
  await expect(page.getByTestId("derived-table")).toBeVisible();
  await shot(page, info, "g4-04-derived-light-1440x900");

  await openEditorSection(page, "dwgNaming");
  await expect(page.getByTestId("token-preview")).toContainText("RQ-001-003 示例子集.dwg");
  await shot(page, info, "g4-05-dwg-naming-light-1440x900");

  await openEditorSection(page, "assets");
  await expect(page.getByTestId("asset-layout-A3")).toContainText("匹配");
  await shot(page, info, "g4-06-assets-light-1440x900");

  // 发布错误页：清空「结构」的映射目标，映射未完成 → 错误阻断发布
  await openEditorSection(page, "derived");
  await page.getByTestId("edit-derived-prop-code").click();
  await page.getByTestId("mapping-target-enum-jg").fill("");
  await page.getByTestId("confirm-mapping").click();
  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByTestId("publish-review")).toContainText("存在没有目标值的枚举项");
  await expect(page.getByRole("button", {name: "发布标准"})).toBeDisabled();
  await shot(page, info, "g4-07-publish-error-light-1440x900");

  // 发布成功详情：补齐映射目标后发布，进入新版本只读详情
  await page.getByRole("button", {name: "返回编辑"}).click();
  await openEditorSection(page, "derived");
  await page.getByTestId("edit-derived-prop-code").click();
  await page.getByTestId("mapping-target-enum-jg").fill("JG");
  await page.getByTestId("confirm-mapping").click();
  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByRole("button", {name: "发布标准"})).toBeEnabled();
  await page.getByRole("button", {name: "发布标准"}).click();
  await expect(page.getByText("已发布版本不可直接修改")).toBeVisible();
  await stable(page, "light");
  await shot(page, info, "g4-08-publish-success-light-1440x900");
});

test("G4 补充四态：欢迎页深色、标准库深色、字段映射窄视口、发布错误页深色", async ({page}, info) => {
  // 补充 1/2/4：深色 1440×900
  await page.setViewportSize({width: 1440, height: 900});
  await installPreferenceSnapshot(page, "dark");
  await installStandards(page, [published("official", "2.1.0"), draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": visualDraftWithMappingGap()},
    assetResults: {layouts: {asset_id: "layouts", kind: "layout-template", layouts: ["Model", "A2", "A3"], diagnostics: []}},
  });
  await page.goto("/");
  await stable(page, "dark");
  await shot(page, info, "g4-09-welcome-dark-1440x900");

  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await expect(libraryItems(page)).toHaveCount(2);
  await shot(page, info, "g4-10-library-dark-1440x900");

  await openDraftEditor(page);
  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByTestId("publish-review")).toContainText("存在没有目标值的枚举项");
  await shot(page, info, "g4-11-publish-error-dark-1440x900");

  // 补充 3：DWG 命名 900×768 窄视口（字段浏览器 + 令牌编辑 + 预览）
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": visualDraft()},
    assetResults: {layouts: {asset_id: "layouts", kind: "layout-template", layouts: ["Model", "A2", "A3"], diagnostics: []}},
  });
  await installPreferenceSnapshot(page, "light");
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "dwgNaming");
  await expect(page.getByTestId("token-preview")).toContainText("RQ-001-003 示例子集.dwg");
  await stable(page, "light");
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(900);
  await shot(page, info, "g4-12-dwg-naming-narrow-light-900x768");
});
