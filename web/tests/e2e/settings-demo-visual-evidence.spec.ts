// SPEC-DM-011 冻结件（交互 Demo）的证据截图与基线行为钉子（GUIDE-DM-001 G4 / SPEC-DM-011 §7）。
//
// 为什么单独有一个"对 Demo 截图"的证据 spec：SPEC-DM-011 §7 冻结包的 6 张基准图（g4-01～g4-06）
// 在上一轮 G4/G8 只作为附件与 .superpowers/ 本地产物存在，而 .superpowers/ 已被 .gitignore
// 忽略（见仓库 .gitignore 第 7 行），于是引用它们的 §7/§8 记录在仓库里无法核验。本 spec 把证据
// 固定成可复现的产物：每次运行以 testInfo 附件留档，G4 验收时把标准集复制到
// docs/dst-manager/specs/assets/SPEC-DM-011/（与 SPEC-DM-012/013 同一约定，且进入版本库）。
//
// 同时承担基线行为钉子（SC-16）：分组阈值、卡片不可点击、滑动开关语义、
// 「已启用 + 启动失败」组合、以及常规配置 bool 字段与扩展开关共用同一形态。
// 只驱动 Demo 自身（file:// 打开，无后端、无网络请求）。
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import path from "node:path";
import {pathToFileURL} from "node:url";

// 运行目录为 web/（playwright.config.ts 的 testDir 基准）
const DEMO_URL = pathToFileURL(path.resolve(process.cwd(), "../docs/dst-manager/mockups/SPEC-DM-011-settings-demo.html")).href;
const BASELINE = {width: 1280, height: 720};   // §7 桌面基准
const MINIMAL = {width: 900, height: 600};     // §7 最小支持视口

async function openDemo(page: Page, viewport: {width: number; height: number}, theme: "light" | "dark"): Promise<string[]> {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(String(error)));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  await page.setViewportSize(viewport);
  await page.emulateMedia({colorScheme: theme});
  await page.goto(DEMO_URL);
  if (theme === "dark") await page.locator('[data-action="theme"]').click();
  await page.locator('[data-action="open-settings"]').click();
  await expect(page.locator("#settings")).toBeVisible();
  return errors;
}

async function shoot(page: Page, info: TestInfo, name: string): Promise<void> {
  const file = info.outputPath(name);
  await page.screenshot({path: file, animations: "disabled"});
  await info.attach(name, {path: file, contentType: "image/png"});
}

// —— 扩展分区三档样本：1 条（最小）/ 4 条（多状态）/ 8 条（触发分组）——
async function showExtensions(page: Page, count: 1 | 4 | 8): Promise<void> {
  await page.locator("#extCount").selectOption(String(count));
  await page.locator('[data-section="extensions"]').click();
  await expect(page.locator(".ext-list").first()).toBeVisible();
}

test("g4-01 常规配置默认态（浅色·基准视口）", async ({page}, info) => {
  const errors = await openDemo(page, BASELINE, "light");
  await shoot(page, info, "g4-01-general-light.png");
  expect(errors).toEqual([]);
});

test("g4-02 即时校验行内错误（浅色·基准视口）", async ({page}, info) => {
  await openDemo(page, BASELINE, "light");
  await page.locator('input[data-key="cad_timeout_seconds"]').fill("5000");
  await expect(page.locator("#err-cad_timeout_seconds")).toBeVisible();
  await shoot(page, info, "g4-02-validation-error-light.png");
});

test("g4-03 保存成功（浅色·基准视口）", async ({page}, info) => {
  await openDemo(page, BASELINE, "light");
  await page.locator('input[data-key="cad_timeout_seconds"]').fill("900");
  await page.locator('[data-action="save"]').click();
  await expect(page.locator("#saved-pill")).toBeVisible();
  await shoot(page, info, "g4-03-saved-light.png");
});

test("g4-04 常规配置（深色·基准视口）", async ({page}, info) => {
  await openDemo(page, BASELINE, "dark");
  await shoot(page, info, "g4-04-general-dark.png");
});

test("g4-05 关于分区（深色·基准视口）", async ({page}, info) => {
  await openDemo(page, BASELINE, "dark");
  await page.locator('[data-section="about"]').click();
  await expect(page.locator(".license")).toBeVisible();
  await shoot(page, info, "g4-05-about-dark.png");
});

test("g4-06 配置文件损坏诊断横幅（浅色·最小视口）", async ({page}, info) => {
  await openDemo(page, MINIMAL, "light");
  await page.locator("#scenario").selectOption("corrupt");
  await page.locator('[data-action="cancel"]').click();  // 无修改直接关闭
  await page.locator('[data-action="open-settings"]').click();
  await expect(page.locator("#diag")).toBeVisible();
  await shoot(page, info, "g4-06-corrupt-min-viewport-light.png");
});

test("g4-07 扩展分区·单条（浅色·基准视口）", async ({page}, info) => {
  const errors = await openDemo(page, BASELINE, "light");
  await showExtensions(page, 1);
  await shoot(page, info, "g4-07-extensions-single-light.png");
  expect(errors).toEqual([]);
});

test("g4-08 扩展分区·四条多状态（启用/停用/启动失败/不兼容，浅色）", async ({page}, info) => {
  await openDemo(page, BASELINE, "light");
  await showExtensions(page, 4);
  // 关键组合：用户意图为启用但运行时启动失败，两行信息必须同时成立且不互相否认
  const failed = page.locator('[data-ext="demo.attribute-export"]');
  await expect(failed.getByRole("switch", {name: "停用 属性批量导出"})).toHaveAttribute("aria-checked", "true");
  await expect(failed.locator(".badge", {hasText: "启动失败"})).toBeVisible();
  await expect(failed.getByText("诊断码 EXTENSION_START_FAILED")).toBeVisible();
  await expect(failed.locator(".ext-state")).toHaveText("已启用");
  await shoot(page, info, "g4-08-extensions-multi-light.png");
});

test("g4-09 扩展分区·八条触发分组（浅色，分组顶部）", async ({page}, info) => {
  await openDemo(page, BASELINE, "light");
  await showExtensions(page, 8);
  await expect(page.locator(".group-title")).toHaveCount(2);
  await expect(page.locator(".group-title").first()).toHaveText("已启用");
  await expect(page.locator(".group-title").last()).toHaveText("已停用");
  await shoot(page, info, "g4-09-extensions-grouped-top-light.png");
});

test("g4-10 扩展分区·八条分段边界（浅色，滚动到第二段）", async ({page}, info) => {
  await openDemo(page, BASELINE, "light");
  await showExtensions(page, 8);
  await page.locator(".group-title").last().scrollIntoViewIfNeeded();
  await shoot(page, info, "g4-10-extensions-grouped-boundary-light.png");
});

test("g4-11 扩展分区·四条（深色·基准视口）", async ({page}, info) => {
  await openDemo(page, BASELINE, "dark");
  await showExtensions(page, 4);
  await shoot(page, info, "g4-11-extensions-dark.png");
});

test("g4-12 编号规则：缓冲式 bool 字段与扩展开关共用同一滑动开关形态（浅色）", async ({page}, info) => {
  await openDemo(page, BASELINE, "light");
  await page.locator(".group-title", {hasText: "编号规则"}).scrollIntoViewIfNeeded();
  await expect(page.getByRole("switch", {name: "图纸编号追加后缀"})).toBeVisible();
  await shoot(page, info, "g4-12-general-bool-switch-light.png");
});

test("SC-16 基线钉子：分组阈值、卡片不可点击、开关语义与统一形态", async ({page}) => {
  await openDemo(page, BASELINE, "light");

  // 1) 分组阈值：<6 条不分组；≥6 条按 enabled 分两段
  await showExtensions(page, 4);
  await expect(page.locator(".group-title")).toHaveCount(0);
  await showExtensions(page, 8);
  await expect(page.locator(".group-title")).toHaveCount(2);
  await showExtensions(page, 1);
  await expect(page.locator(".group-title")).toHaveCount(0);

  // 2) 卡片是状态容器：不是按钮/链接，也不带 tabindex（唯一可聚焦元素是开关）
  const card = page.locator(".ext-card").first();
  const cardFocusables = await card.evaluate(el => Array.from(el.querySelectorAll("[tabindex], a[href], button, [role=button], [role=link]")).map(node => node.tagName + (node.getAttribute("role") ? `[${node.getAttribute("role")}]` : "")));
  expect(cardFocusables).toEqual(["BUTTON[switch]"]);

  // 3) 开关语义：role=switch + aria-checked，可访问名随状态翻转，可见状态文字同步
  const toggle = card.getByRole("switch");
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await expect(card.locator(".ext-state")).toHaveText("已启用");
  await toggle.click();
  await expect(card.getByRole("switch", {name: "启用 图纸目录"})).toHaveAttribute("aria-checked", "false");
  await expect(card.locator(".ext-state")).toHaveText("已停用");

  // 4) 统一形态：常规配置的缓冲式 bool 字段与扩展开关是同一控件（滑动开关）
  await page.locator('[data-section="general"]').click();
  const boolSwitch = page.getByRole("switch", {name: "图纸编号追加后缀"});
  await expect(boolSwitch).toHaveClass(/switch-track/);
  await expect(boolSwitch).toHaveAttribute("aria-checked", "true");
  await boolSwitch.click();
  await expect(page.getByRole("switch", {name: "图纸编号追加后缀"})).toHaveAttribute("aria-checked", "false");
});
