// 图纸标准平台视觉证据（PLAN-DM-035 Task 11 / SPEC-DM-016 §12.2）。
// G4 冻结状态集：欢迎页、标准库、属性定义、字段映射、字段组合、模板资产、发布错误页、
// 发布成功详情（八态，1440×900 浅色），另加四态补充（欢迎页深色、标准库深色、
// 字段映射 900×768 窄视口、发布错误页深色）。
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
const EVIDENCE_DIR = EVIDENCE_TARGET === "production"
  ? path.join(EVIDENCE_ROOT, "production")
  : EVIDENCE_TARGET === "g4" ? EVIDENCE_ROOT : null;

/** 视觉证据固定注入的资产检查结果与文档（与 `draftDocument` 声明一致）。 */
function visualDraft(): Record<string, unknown> {
  return draftDocument({
    properties: [
      {name: "专业名称", scope: "sheetset", required: true, default_value: "燃气", enum_values: ["燃气", "建筑", "结构"], description: ""},
      {name: "专业代码", scope: "sheetset", required: false, default_value: "", enum_values: [], description: ""},
      {name: "图幅", scope: "sheetset", required: false, default_value: "A3", enum_values: ["A2", "A3"], description: ""},
    ],
    assets: [{asset_id: "layouts", kind: "layout-template", files: [{path: "assets/layout-a2.dwg", role: "A2"}, {path: "assets/layout-a3.dwg", role: "A3"}]}],
    rules: [
      {
        rule_id: "specialty-code",
        kind: "mapping",
        target: "sheetset.专业代码",
        source: "sheetset.专业名称",
        allowed: [],
        table: [["燃气", "RQ"], ["建筑", "JZ"], ["结构", "JG"]],
        segments: [],
      },
      {
        rule_id: "dwg-name",
        kind: "naming",
        target: "derived.dwg_name",
        allowed: [],
        table: [],
        segments: [{field: "sheetset.专业代码"}, {field: "subset.sequence", format: "3"}, {literal: " "}, {literal: "总平面图"}],
      },
    ],
  });
}

/** 与视觉草案同数据但映射表未覆盖「结构」：用于发布错误页状态。 */
function visualDraftWithMappingGap(): Record<string, unknown> {
  const document = visualDraft();
  const rules = document.rules as Array<{rule_id: string; table: string[][]}>;
  rules[0].table = [["燃气", "RQ"], ["建筑", "JZ"]];
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
  await shot(page, info, "g4-03-properties-light-1440x900");

  await openEditorSection(page, "mapping");
  await expect(page.getByText("1 条字段映射规则")).toBeVisible();
  await shot(page, info, "g4-04-mapping-light-1440x900");

  await openEditorSection(page, "composition");
  await expect(page.getByTestId("composition-preview")).not.toHaveText("—");
  await shot(page, info, "g4-05-composition-light-1440x900");

  await openEditorSection(page, "assets");
  await expect(page.getByTestId("asset-layout-A3")).toContainText("匹配");
  await shot(page, info, "g4-06-assets-light-1440x900");

  // 发布错误页：删掉「结构 → JG」一行，使映射表未覆盖源值 → 错误阻断发布
  await openEditorSection(page, "mapping");
  await page.getByRole("button", {name: "删除第 3 行"}).click();
  await expect(page.getByTestId("mapping-uncovered-summary")).toBeVisible();
  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByText(/映射表未覆盖源值/)).toBeVisible();
  await expect(page.getByRole("button", {name: "发布标准"})).toBeDisabled();
  await shot(page, info, "g4-07-publish-error-light-1440x900");

  // 发布成功详情：补齐映射行后发布，进入新版本只读详情
  await page.getByRole("button", {name: "返回编辑"}).click();
  await openEditorSection(page, "mapping");
  await page.getByRole("button", {name: "新增一行"}).click();
  await page.getByTestId("mapping-source-0-2").fill("结构");
  await page.getByTestId("mapping-target-0-2").fill("JG");
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
  await expect(page.getByText(/映射表未覆盖源值/)).toBeVisible();
  await shot(page, info, "g4-11-publish-error-dark-1440x900");

  // 补充 3：字段映射 900×768 窄视口（分级视图）
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": visualDraft()},
    assetResults: {layouts: {asset_id: "layouts", kind: "layout-template", layouts: ["Model", "A2", "A3"], diagnostics: []}},
  });
  await installPreferenceSnapshot(page, "light");
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "mapping");
  await expect(page.getByText("1 条字段映射规则")).toBeVisible();
  await stable(page, "light");
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(900);
  await shot(page, info, "g4-12-mapping-narrow-light-900x768");
});
