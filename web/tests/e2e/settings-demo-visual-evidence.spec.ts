// SPEC-DM-011 冻结件（交互 Demo）的证据截图与基线行为钉子（GUIDE-DM-001 G4 / SPEC-DM-011 §7）。
//
// 为什么单独有一个"对 Demo 截图"的证据 spec：SPEC-DM-011 §7 冻结包的 6 张基准图（g4-01～g4-06）
// 在上一轮 G4/G8 只作为附件与 .superpowers/ 本地产物存在，而 .superpowers/ 已被 .gitignore
// 忽略（见仓库 .gitignore 第 7 行），于是引用它们的 §7/§8 记录在仓库里无法核验。本 spec 把证据
// 固定成可复现的产物：每次运行以 testInfo 附件留档，G4 验收时把标准集复制到
// docs/dst-manager/specs/assets/SPEC-DM-011/（与 SPEC-DM-012/013 同一约定，且进入版本库）。
//
// 同时承担基线行为钉子（SC-16 / SC-17）：分组阈值、卡片不可点击、滑动开关语义、
// 「已启用 + 启动失败」组合、常规配置 bool 字段与扩展开关共用同一形态，
// 以及扩展全局设置入口（配置按钮条件、同对话框子视图、按扩展独立保存、
// 脏状态闸门、焦点归还、字段超限/冲突/高版本只读）。
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

// —— 扩展全局设置入口（SC-17）：声明设置时出现「配置」，进入同一 <dialog> 的子视图 ——
async function openConfigFor(page: Page, id: string): Promise<void> {
  await page.locator("#extCount").selectOption("4");
  await page.locator('[data-section="extensions"]').click();
  await page.locator(`[data-action="ext-config"][data-ext="${id}"]`).click();
  await expect(page.locator('[data-view="extension-config"]')).toBeVisible();
}

// —— R4 键盘走查工具：只用 page.keyboard 驱动，逐次 Tab 后核对焦点可见性与遮挡 ——
type FocusBox = {tag: string; name: string; visible: boolean; notOccludedByFooter: boolean; inTopDialog: boolean; inViewport: boolean};

async function focusedBox(page: Page): Promise<FocusBox> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    const settings = document.getElementById("settings") as HTMLDialogElement | null;
    const dialogs = Array.from(document.querySelectorAll("dialog[open]")) as HTMLDialogElement[];
    const top = dialogs[dialogs.length - 1] ?? null;
    const foot = document.querySelector(".dlg-foot") as HTMLElement | null;
    const fallback = {tag: el?.tagName ?? "NONE", name: "", visible: false, notOccludedByFooter: false, inTopDialog: false, inViewport: false};
    if (!el || el === document.body || !settings || !foot) return fallback;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const inside = (outer: DOMRect, inner: DOMRect) =>
      inner.left >= outer.left - 0.5 && inner.right <= outer.right + 0.5 && inner.top >= outer.top - 0.5 && inner.bottom <= outer.bottom + 0.5;
    // 焦点在设置窗口内时，不得落到固定页脚之后（页脚自身的按钮反过来必须完整在页脚内）
    const inSettingsContent = Boolean(el.closest("#settings")) && el !== settings;
    return {
      tag: el.tagName,
      name: el.getAttribute("aria-label") ?? (el.textContent ?? "").trim().slice(0, 20),
      visible: rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none" && style.opacity !== "0",
      notOccludedByFooter: !inSettingsContent ? true
        : el.closest(".dlg-foot") ? rect.top >= foot.getBoundingClientRect().top - 0.5
        : rect.bottom <= foot.getBoundingClientRect().top + 0.5,
      inTopDialog: top ? inside(top.getBoundingClientRect(), rect) : true,
      inViewport: rect.top >= -0.5 && rect.left >= -0.5 && rect.right <= window.innerWidth + 0.5 && rect.bottom <= window.innerHeight + 0.5,
    };
  });
}

// 逐次按 Tab 直到落点命中 target，并断言每一步的焦点都可见、未被页脚遮挡。
async function tabUntil(page: Page, target: string, label: string): Promise<void> {
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    const box = await focusedBox(page);
    expect(box.visible, `${label}：第 ${i + 1} 次 Tab 后的焦点不可见（${box.tag} ${box.name}）`).toBe(true);
    expect(box.inViewport, `${label}：焦点 ${box.tag}（${box.name}）不在视口内`).toBe(true);
    expect(box.inTopDialog, `${label}：焦点 ${box.tag}（${box.name}）不在最上层对话框内`).toBe(true);
    expect(box.notOccludedByFooter, `${label}：焦点 ${box.tag}（${box.name}）被固定页脚遮挡`).toBe(true);
    if (await page.evaluate(sel => document.activeElement?.matches(sel) ?? false, target)) return;
  }
  throw new Error(`${label}：按 Tab 40 次仍未到达 ${target}`);
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

test("g4-13 扩展配置入口：声明设置的卡片出现「配置」按钮（浅色·基准视口）", async ({page}, info) => {
  const errors = await openDemo(page, BASELINE, "light");
  await showExtensions(page, 4);
  // 4 条中只有声明设置的两条有配置入口（图纸录 custom / 图框批量更新 generated）
  await expect(page.locator('[data-action="ext-config"]')).toHaveCount(2);
  await expect(page.locator('[data-action="ext-config"][data-ext="dst-manager.sheet-catalog"]')).toBeVisible();
  await shoot(page, info, "g4-13-extension-config-entry-light.png");
  expect(errors).toEqual([]);
});

test("g4-14 扩展配置子视图：generated 表单（浅色·基准视口）", async ({page}, info) => {
  const errors = await openDemo(page, BASELINE, "light");
  await openConfigFor(page, "demo.frame-update");
  await expect(page.locator("#cfg-title")).toHaveText("配置 · 图框批量更新");
  await expect(page.getByRole("switch", {name: "回写标题栏"})).toHaveAttribute("aria-checked", "true");
  await expect(page.locator("#btn-cfg-back")).toBeVisible();
  await shoot(page, info, "g4-14-extension-config-generated-light.png");
  expect(errors).toEqual([]);
});

test("g4-15 扩展配置子视图：图纸目录 custom 面板与输出图纸过滤（深色·基准视口）", async ({page}, info) => {
  const errors = await openDemo(page, BASELINE, "dark");
  await openConfigFor(page, "dst-manager.sheet-catalog");
  const filter = page.locator('input[data-key="excluded_title_keywords"]');
  await expect(filter).toHaveAttribute("placeholder", "草图, 作废, TEMP");
  await expect(page.getByText("图名包含任一关键词时不写入目录，多个关键词用逗号分隔")).toBeVisible();
  await shoot(page, info, "g4-15-extension-config-custom-dark.png");
  expect(errors).toEqual([]);
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

  // 2) 卡片是状态容器：卡片本体不是按钮/链接、不带 tabindex，也不可点击。
  //    卡片内的可聚焦元素只有动作行——声明设置的卡片按 DOM 顺序为「配置」(SC-17) 与开关，
  //    无设置卡片仍只有开关（原 SC-16 钤子的同一事实保留在这一行）。
  await showExtensions(page, 4);
  const actionRow = (locator: import("@playwright/test").Locator) => locator.evaluate(el => Array.from(el.querySelectorAll("[tabindex], a[href], button, [role=button], [role=link]")).map(node => node.tagName + (node.getAttribute("role") ? `[${node.getAttribute("role")}]` : "")));
  const card = page.locator(".ext-card").first();
  expect(await card.evaluate(el => el.tagName === "BUTTON" || el.tagName === "A" || el.hasAttribute("tabindex") || el.hasAttribute("role"))).toBe(false);
  expect(await actionRow(card)).toEqual(["BUTTON", "BUTTON[switch]"]);
  expect(await actionRow(page.locator('.ext-card[data-ext="demo.attribute-export"]'))).toEqual(["BUTTON[switch]"]);
  // 点击卡片本体（名称）不进入配置子视图、不发生导航
  await card.locator(".ext-name").click();
  await expect(page.locator('[data-view="extension-config"]')).toHaveCount(0);
  await expect(page.locator(".ext-list").first()).toBeVisible();

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

// —— SC-17：扩展全局设置入口（统一入口、同对话框子视图、按扩展独立保存、脏状态闸门）——
test("SC-17 配置入口：仅声明设置的卡片有「配置」，动作行顺序为配置→状态文字→开关", async ({page}) => {
  await openDemo(page, BASELINE, "light");
  await showExtensions(page, 4);

  // 4 条中只有声明设置的两条出现配置入口；没有设置时不显示（ARCH-DM-006 §8.2）
  await expect(page.locator('[data-action="ext-config"]')).toHaveCount(2);
  await expect(page.locator('.ext-card[data-ext="demo.attribute-export"] [data-action="ext-config"]')).toHaveCount(0);
  await expect(page.locator('.ext-card[data-ext="demo.sheet-validate"] [data-action="ext-config"]')).toHaveCount(0);

  // 动作行 DOM 顺序固定：配置按钮 → 状态文字 → 开关；可访问名为「配置 {name}」
  const card = page.locator('.ext-card[data-ext="dst-manager.sheet-catalog"]');
  const order = await card.locator(".ext-side > *").evaluateAll(nodes => nodes.map(node => node.getAttribute("data-action") ?? (node.className as string).split(" ")[0]));
  expect(order).toEqual(["ext-config", "ext-state", "ext-toggle"]);
  await expect(card.getByRole("button", {name: "配置 图纸目录"})).toBeVisible();
  // 停用/启动失败的卡片不隐藏配置入口（停用保留设置，ARCH-DM-006 §8.1）
  await expect(page.locator('.ext-card[data-ext="demo.frame-update"] [data-action="ext-config"]')).toBeVisible();

  // 未加载工作区也能进入：不依赖工作区快照（ARCH-DM-006 §8.2）
  await expect(page.locator(".badge.muted", {hasText: "未加载工作区"})).toBeVisible();
});

test("SC-17 每个扩展独立保存：不清空核心配置缓冲，generated 默认值来自 Provider", async ({page}) => {
  await openDemo(page, BASELINE, "light");

  // 核心配置先留一处未保存修改
  await page.locator('input[data-key="cad_timeout_seconds"]').fill("900");
  await expect(page.locator("#btn-save")).toBeEnabled();

  // generated 子视图：字段按 Provider 默认值渲染，不出现 custom 面板
  await openConfigFor(page, "demo.frame-update");
  await expect(page.locator("#cfg-template")).toHaveCount(0);
  await expect(page.locator('input[data-key="batch_limit"]')).toHaveValue("50");
  await expect(page.locator('input[data-key="frame_block_prefix"]')).toHaveValue("TK-");
  await expect(page.getByRole("radio", {name: "询问"})).toBeChecked();

  // 独立保存：只提交本扩展设置，修订号与核心配置互不相干
  await page.locator('input[data-key="batch_limit"]').fill("120");
  await expect(page.locator("#btn-cfg-save")).toBeEnabled();
  await page.locator("#btn-cfg-save").click();
  await expect(page.locator("#cfg-saved-pill")).toBeVisible();
  await expect(page.locator(".cfg-title")).toContainText("设置修订 r3");
  await expect(page.locator("#foot-hint")).toContainText("扩展设置独立保存");

  // 核心配置缓冲未被清理：底部保存仍点亮，返回后核心编辑仍在
  await expect(page.locator("#btn-save")).toBeEnabled();
  await page.locator("#btn-cfg-back").click();
  await expect(page.locator('[data-view="extension-config"]')).toHaveCount(0);
  await page.locator('[data-section="general"]').click();
  await expect(page.locator('input[data-key="cad_timeout_seconds"]')).toHaveValue("900");
  await expect(page.locator("#btn-save")).toBeEnabled();

  // 重开子视图：保存值已回读，布尔字段仍是滑动开关（与核心 bool 同形态）
  await page.locator('[data-section="extensions"]').click();
  await page.locator('[data-action="ext-config"][data-ext="demo.frame-update"]').click();
  await expect(page.locator('input[data-key="batch_limit"]')).toHaveValue("120");
  const boolSwitch = page.getByRole("switch", {name: "回写标题栏"});
  await expect(boolSwitch).toHaveClass(/switch-track/);
  await boolSwitch.click();
  await expect(page.getByRole("switch", {name: "回写标题栏"})).toHaveAttribute("aria-checked", "false");
});

test("SC-17 脏状态闸门：返回/Esc/遮罩都先确认，关闭确认合并子视图 dirty", async ({page}) => {
  await openDemo(page, BASELINE, "light");
  await openConfigFor(page, "dst-manager.sheet-catalog");
  const filter = page.locator('input[data-key="excluded_title_keywords"]');
  await filter.fill("草图, 作废");
  await expect(page.locator("#foot-hint")).toContainText("扩展设置修改待保存");

  // 1) 返回扩展列表：先确认；选「留在此处」留在子视图，输入保留，焦点归还触发它的按钮
  await page.locator("#btn-cfg-back").click();
  await expect(page.locator("#modal")).toBeVisible();
  await expect(page.locator("#modal-title")).toHaveText("有未保存的扩展设置修改");
  await page.locator('[data-choice="cancel"]').click();
  await expect(page.locator("#modal")).toBeHidden();
  await expect(page.locator('[data-view="extension-config"]')).toBeVisible();
  await expect(filter).toHaveValue("草图, 作废");
  await expect(page.locator("#btn-cfg-back")).toBeFocused();

  // 2) Esc 与遮罩在子视图内等价于「返回扩展列表」（不是直接关闭整个对话框）
  await page.keyboard.press("Escape");
  await expect(page.locator("#modal-title")).toHaveText("有未保存的扩展设置修改");
  await page.locator('[data-choice="cancel"]').click();
  await page.mouse.click(4, 4);   // 遮罩点击（弹窗本体之外）
  await expect(page.locator("#modal-title")).toHaveText("有未保存的扩展设置修改");
  // 放弃修改并返回：回到列表，焦点归还卡片的「配置」按钮，草稿确实被丢弃
  await page.locator('[data-choice="discard"]').click();
  await expect(page.locator('[data-view="extension-config"]')).toHaveCount(0);
  await expect(page.locator('[data-action="ext-config"][data-ext="dst-manager.sheet-catalog"]')).toBeFocused();
  await page.locator('[data-action="ext-config"][data-ext="dst-manager.sheet-catalog"]').click();
  await expect(page.locator('input[data-key="excluded_title_keywords"]')).toHaveValue("");

  // 3) 子视图内分区导航禁用：唯一出路是「返回扩展列表」（避免未闸门的隐式离开）
  await expect(page.locator('[data-section="general"]')).toBeDisabled();
  // 4) 关闭确认合并扩展 dirty 与核心 dirty
  await page.locator('input[data-key="excluded_title_keywords"]').fill("TEMP");
  await page.locator('[data-action="close-x"]').click();
  await expect(page.locator("#modal")).toBeVisible();
  await expect(page.locator("#modal-body")).toContainText("扩展设置也有未保存修改");
  await page.locator('[data-choice="discard"]').click();
  await expect(page.locator("#settings")).toBeHidden();
  await expect(page.locator('[data-action="open-settings"]')).toBeFocused();
});

test("SC-17 服务端状态就地呈现：字段超限、修订冲突保留输入、高版本只读", async ({page}) => {
  await openDemo(page, BASELINE, "light");
  await openConfigFor(page, "dst-manager.sheet-catalog");
  const filter = page.locator('input[data-key="excluded_title_keywords"]');
  await expect(filter).toHaveAttribute("placeholder", "草图, 作废, TEMP");

  // 1) 字段超限：50/51 项与 100/101 字符两个边界都在行内定位到字段，保存被拒、输入保留
  const fifty = Array.from({length: 50}, (_, i) => `关键词${i}`).join(", ");
  await filter.fill(`${fifty}, 多出来的第51个`);
  await expect(page.locator("#err-excluded_title_keywords")).toContainText("最多 50 个关键词，当前 51 个");
  await expect(page.locator("#err-excluded_title_keywords")).toContainText("EXTENSION_SETTINGS_INVALID");
  await page.locator("#btn-cfg-save").click();
  await expect(page.locator("#cfg-saved-pill")).toBeHidden();
  await expect(filter).toHaveValue(`${fifty}, 多出来的第51个`);
  await filter.fill("x".repeat(101));
  await expect(page.locator("#err-excluded_title_keywords")).toContainText("单个关键词最多 100 个字符，当前 101 个");
  await filter.fill("TEMP");

  // 2) 修订冲突：409 就地呈现、输入保留，按新修订重试后成功（服务端值随之推进）
  await page.locator("#btn-cfg-back").click();
  await page.locator('[data-choice="discard"]').click();
  await page.locator('[data-action="cancel"]').click();   // 关闭设置窗口后才能切演示场景
  await page.locator("#scenario").selectOption("extconflict");
  await page.locator('[data-action="open-settings"]').click();
  await openConfigFor(page, "dst-manager.sheet-catalog");
  await page.locator('input[data-key="excluded_title_keywords"]').fill("作废");
  await page.locator("#btn-cfg-save").click();
  await expect(page.locator("#cfg-conflict")).toBeVisible();
  await expect(page.locator("#cfg-conflict")).toContainText("409 EXTENSION_SETTINGS_INVALID");
  await expect(page.locator("#cfg-conflict")).toContainText("expected_revision=7, current_revision=8");
  await expect(page.locator('input[data-key="excluded_title_keywords"]')).toHaveValue("作废");
  await page.locator("#btn-cfg-retry").click();
  await expect(page.locator("#cfg-saved-pill")).toBeVisible();
  await expect(page.locator("#cfg-conflict")).toHaveCount(0);
  await page.locator("#btn-cfg-back").click();
  await openConfigFor(page, "dst-manager.sheet-catalog");
  await expect(page.locator('input[data-key="excluded_title_keywords"]')).toHaveValue("作废");

  // 3) 未知更高 Schema：只读诊断 + 输入与保存都禁用，但仍可无确认地返回
  await page.locator("#btn-cfg-back").click();
  await page.locator('[data-action="cancel"]').click();
  await page.locator("#scenario").selectOption("extreadonly");
  await page.locator('[data-action="open-settings"]').click();
  await openConfigFor(page, "dst-manager.sheet-catalog");
  await expect(page.locator("#cfg-readonly")).toBeVisible();
  await expect(page.locator("#cfg-readonly")).toContainText("EXTENSION_SETTINGS_SCHEMA_NEWER");
  await expect(page.locator("#cfg-readonly")).toContainText("已只读保留，无法覆盖保存");
  await expect(page.locator('input[data-key="excluded_title_keywords"]')).toBeDisabled();
  await expect(page.locator("#btn-cfg-save")).toBeDisabled();
  await page.locator("#btn-cfg-back").click();
  await expect(page.locator("#modal")).toBeHidden();
  await expect(page.locator('[data-view="extension-config"]')).toHaveCount(0);
});

test("R4 键盘走查：进入配置、编辑、返回确认、保存与焦点归还全部只用键盘", async ({page}) => {
  await page.setViewportSize(BASELINE);
  await page.emulateMedia({colorScheme: "light"});
  await page.goto(DEMO_URL);

  // 0) 先只用键盘把扩展条目数改到 8（Windows 上方向键直接改变获得焦点的 select），
  //    使后面的卡片列表变成可滚动的分组长列表，面板内滚动后的焦点才能被页脚遮挡检查验证
  await tabUntil(page, "#extCount", "定位条目数选择框");
  await page.keyboard.press("ArrowDown");
  await expect(page.locator("#extCount")).toHaveValue("8");

  // 1) 键盘打开设置 → 扩展分区 → 进入图纸目录配置子视图
  await tabUntil(page, '[data-action="open-settings"]', "进入设置");
  await page.keyboard.press("Enter");
  await expect(page.locator("#settings")).toBeVisible();
  await tabUntil(page, '[data-section="extensions"]', "切换到扩展分区");
  await page.keyboard.press("Enter");
  await expect(page.locator(".ext-list").first()).toBeVisible();
  await tabUntil(page, '[data-action="ext-config"][data-ext="dst-manager.sheet-catalog"]', "聚焦配置按钮");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-view="extension-config"]')).toBeVisible();
  // 进入后焦点落在子视图首个字段控件
  await expect(page.locator("#cfg-template")).toBeFocused();

  // 2) 键盘编辑过滤文本框（半/全角逗号 + 重复项）
  await tabUntil(page, 'input[data-key="excluded_title_keywords"]', "定位过滤文本框");
  await page.keyboard.insertText("草图， 作废,,temp,草图");
  await expect(page.locator("#foot-hint")).toContainText("扩展设置修改待保存");

  // 3) 返回需要确认；确认框内的 Esc 只作用于最上层模态（留在此处）
  await tabUntil(page, "#btn-cfg-back", "定位返回按钮");
  await page.keyboard.press("Enter");
  await expect(page.locator("#modal")).toBeVisible();
  await expect(page.locator("#modal-title")).toHaveText("有未保存的扩展设置修改");
  await page.keyboard.press("Escape");
  await expect(page.locator("#modal")).toBeHidden();
  await expect(page.locator("#settings")).toBeVisible();
  await expect(page.locator("#btn-cfg-back")).toBeFocused();
  await expect(page.locator('input[data-key="excluded_title_keywords"]')).toHaveValue("草图， 作废,,temp,草图");

  // 4) 确认框内逐次 Tab 的焦点同样可见且不被遮挡；放弃修改并返回 → 焦点归还「配置」按钮
  await page.keyboard.press("Enter");
  await expect(page.locator("#modal")).toBeVisible();
  const modalFocus = await focusedBox(page);
  expect(modalFocus.visible && modalFocus.inTopDialog && modalFocus.inViewport && modalFocus.notOccludedByFooter, `确认框首个焦点：${JSON.stringify(modalFocus)}`).toBe(true);
  await page.keyboard.press("Tab");
  const modalNext = await focusedBox(page);
  expect(modalNext.visible && modalNext.inTopDialog && modalNext.inViewport && modalNext.notOccludedByFooter, `确认框第二个焦点：${JSON.stringify(modalNext)}`).toBe(true);
  await page.keyboard.press("Enter");   // 放弃修改并返回
  await expect(page.locator('[data-view="extension-config"]')).toHaveCount(0);
  await expect(page.locator('[data-action="ext-config"][data-ext="dst-manager.sheet-catalog"]')).toBeFocused();

  // 5) 键盘重新进入并保存：规范化回显 + 本扩展设置修订递增
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-view="extension-config"]')).toBeVisible();
  await tabUntil(page, 'input[data-key="excluded_title_keywords"]', "再次定位过滤文本框");
  await page.keyboard.insertText("草图， 作废,,temp,草图");
  await tabUntil(page, "#btn-cfg-save", "定位子视图保存");
  await page.keyboard.press("Enter");
  await expect(page.locator("#cfg-saved-pill")).toBeVisible();
  await expect(page.locator('input[data-key="excluded_title_keywords"]')).toHaveValue("草图, 作废, temp");
  await expect(page.locator(".cfg-title")).toContainText("设置修订 r8");

  // 6) 干净状态返回不需要确认，焦点仍归还「配置」按钮
  await tabUntil(page, "#btn-cfg-back", "定位返回按钮");
  await page.keyboard.press("Enter");
  await expect(page.locator("#modal")).toBeHidden();
  await expect(page.locator('[data-view="extension-config"]')).toHaveCount(0);
  await expect(page.locator('[data-action="ext-config"][data-ext="dst-manager.sheet-catalog"]')).toBeFocused();

  // 7) 分组长列表（8 条）逐张走到底：面板内滚动后的每个焦点同样可见且不被页脚遮挡
  await expect(page.locator('.ext-card [data-action="ext-toggle"]')).toHaveCount(8);
  await expect(page.locator(".group-title")).toHaveCount(2);
  await tabUntil(page, '.ext-card[data-ext="demo.cad-version-report"] [data-action="ext-toggle"]', "走到第二段最后一张卡片的开关");
  const deepest = await focusedBox(page);
  expect(deepest.notOccludedByFooter, `长列表末端焦点被页脚遮挡：${JSON.stringify(deepest)}`).toBe(true);

  // 8) 键盘关闭设置窗口，焦点归还齿轮入口
  await page.keyboard.press("Escape");
  await expect(page.locator("#settings")).toBeHidden();
  await expect(page.locator('[data-action="open-settings"]')).toBeFocused();
});
