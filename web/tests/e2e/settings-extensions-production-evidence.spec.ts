// 扩展卡片 G8 生产同状态证据（GUIDE-DM-001 G8 / SPEC-DM-011 §7、§9）。
//
// 真实后端 + 夹具装配的 mock /api/extensions 与 /api/extensions/*/state（真实 PATCH 会写
// 用户数据库）。只打开设置对话框并切换到扩展分区，**不保存任何设置**——
// `settings-dialog.spec.ts` 串行共享同一个隔离配置文件，本文件写配置会污染它的基线。
//
// 截图经 testInfo 附件留档；G8 验收时把标准集复制到
// docs/dst-manager/specs/assets/SPEC-DM-011/production/，与 §7 冻结件 g4-* 同名对应
// （g8-ext-01→g4-07、g8-ext-02→g4-08、g8-ext-03→g4-10、g8-ext-04→g4-11；
//  g8-ext-05 为额外的最小视口断点证据，无冻结对照）。
//
// 虚构扩展条目仅为驱动卡片四层信息/徽标/分段渲染：name_key/description_key 用
// 字面中文（vue-i18n 未登记键按原文回退），与冻结 Demo 的虚构样本同口径。
//
// PLAN-DM-025 任务 7（SC-17）起，声明设置的卡片动作行多出「配置」文字按钮：本文件的
// 两份样本按冻结 Demo 的设置声明复原（图纸目录 = custom、图框批量更新 = generated，
// 其余不声明），所以重取产物与目录中 2026-09-11 归档的 g8-ext-02～05 在动作行上不再
// 逐字相同。动作行的权威冻结件是 g4-13。
//
// PLAN-DM-025 任务 9 步骤 5（G8）在本文件追加 g8-ext-06～10：扩展设置入口与两类子视图的
// 生产证据，逐张对照冻结设计件 g4-13（入口）、g4-14（generated 表单）、g4-15（custom 面板）：
//   g8-ext-06 → g4-13（浅色·1280×720）              g8-ext-07 → g4-14（浅色·1280×720）
//   g8-ext-08 → g4-15（深色·1280×720，过滤默认态）  g8-ext-09 无冻结对照（过滤编辑态）
//   g8-ext-10 无冻结对照（过滤字段错误态）
// 计划文件清单只列了 g8-ext-08 一个 custom 文件名，而步骤 5 的行文要求 custom 证据覆盖
// 「默认、编辑、字段错误」三态，故按需求追加 09/10 两份归档件（差异已在 changelog 与本
// 轮报告记录）。g8-ext-09/10 是补充检查，不能替代对 g4-15 的差异说明。
// 归档：用例只写附件；G8 验收时把标准集复制到 docs/dst-manager/specs/assets/SPEC-DM-011/production/
// （g8-ext-01～05 已于 2026-09-11 归档，本轮不重取、不覆盖）。
// 新增用例保存的是**夹具 mock 的**扩展设置端点（`installExtensionSettings`）：PUT 不会落到
// 真实后端，因此仍然只打开设置对话框、不写核心设置，不影响 settings-dialog.spec.ts 的串行基线。
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {openSettingsDialog} from "./fixtures/settings";
import {GENERATED_EXTENSION_ID, extensionSummary, installExtensionSettings, installExtensions} from "./fixtures/extensions";

// 4 条多状态样本：可用 / 已停用 / 启动失败（且用户意图启用）/ 不兼容（含诊断码）。
// 设置声明与冻结 Demo 的虚构样本一致：图纸目录 = custom、图框批量更新 = generated，
// 另两条不声明（无设置时动作行不出现「配置」）。停用/失败不隐藏配置入口（ARCH-DM-006 §8.1）。
function multiList(): unknown[] {
  return [
    extensionSummary({extension_id: "dst-manager.sheet-catalog", name_key: "图纸目录", description_key: "从图纸集数据生成图纸目录工作簿（XLSX），支持输出模板与字段表达式。"}),
    extensionSummary({extension_id: "demo.frame-update", name_key: "图框批量更新", description_key: "按图框属性表批量替换图框块并回写标题栏字段。", status: "DISABLED", enabled: false, settings_contribution: {presentation: "generated"}}),
    extensionSummary({extension_id: "demo.attribute-export", name_key: "属性批量导出", description_key: "把图纸与子集属性导出为制表符分隔文本，供外部审计比对。", status: "FAILED", enabled: true, error_code: "EXTENSION_START_FAILED", settings_contribution: null}),
    extensionSummary({extension_id: "demo.sheet-validate", name_key: "图纸一致性校验", description_key: "校验图号与文件名一致性并列出不一致项。", status: "INCOMPATIBLE", enabled: false, error_code: "EXTENSION_HOST_CONTRACT_MISMATCH", settings_contribution: null}),
  ];
}

// 8 条触发分段样本：已启用 4、已停用 4（分段键 = enabled）；新增的 4 条均不声明设置
function groupedList(): unknown[] {
  return [
    ...multiList(),
    extensionSummary({extension_id: "demo.batch-plot", name_key: "批量打印", description_key: "按子集输出 PDF 打印任务并记录每张图纸的结果。", status: "DISABLED", enabled: false, settings_contribution: null}),
    extensionSummary({extension_id: "demo.layer-audit", name_key: "图层审计", description_key: "汇总各图纸的图层使用情况与未使用图层。", status: "AVAILABLE", enabled: true, settings_contribution: null}),
    extensionSummary({extension_id: "demo.titleblock-sync", name_key: "标题栏同步", description_key: "把子集属性同步到标题栏的已登记字段。", status: "DISABLED", enabled: false, settings_contribution: null}),
    extensionSummary({extension_id: "demo.cad-version-report", name_key: "CAD 版本报告", description_key: "统计图纸保存版本并提示需转换的文件。", status: "AVAILABLE", enabled: true, settings_contribution: null}),
  ];
}

async function shoot(page: Page, info: TestInfo, name: string): Promise<void> {
  const file = info.outputPath(name);
  await page.screenshot({path: file, animations: "disabled"});
  await info.attach(name, {path: file, contentType: "image/png"});
}

// 打开设置并切到扩展分区（未加载工作区即可达，SC-15）
async function openExtensions(page: Page, list: unknown[]): Promise<void> {
  // 由夹具统一拦 /api/extensions 与 /api/extensions/*/state：本文件当前不拨动开关，
  // 但一旦新增切换动作，state 路由缺失就会真写用户 .dst-manager-data/dst-manager.db。
  await installExtensions(page, list);
  await page.goto("/");
  await openSettingsDialog(page);
  await page.getByRole("tab", {name: "扩展"}).click();
}

test("g8-ext-01 扩展分区·单条（浅色·1280×720，对照 g4-07）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  await openExtensions(page, [extensionSummary()]);
  await expect(page.locator(".ext-card")).toHaveCount(1);
  await shoot(page, info, "g8-ext-01-single-light.png");
});

test("g8-ext-02 扩展分区·四条多状态（浅色·1280×720，对照 g4-08）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  await openExtensions(page, multiList());
  await expect(page.locator(".ext-card")).toHaveCount(4);
  // 钉住「已启用 + 启动失败」组合：意图与运行时事实必须同时呈现
  const failed = page.locator('[data-extension-id="demo.attribute-export"]');
  await expect(failed.getByRole("switch", {name: "停用 属性批量导出"})).toHaveAttribute("aria-checked", "true");
  await expect(failed.locator(".badge", {hasText: "启动失败"})).toBeVisible();
  await expect(failed.getByText("诊断码 EXTENSION_START_FAILED")).toBeVisible();
  await shoot(page, info, "g8-ext-02-multi-light.png");
});

test("g8-ext-03 扩展分区·八条分段边界（浅色·1280×720，对照 g4-10）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  await openExtensions(page, groupedList());
  await expect(page.locator(".ext-card")).toHaveCount(8);
  await expect(page.locator(".group-title")).toHaveCount(2);
  await expect(page.locator(".group-title").first()).toHaveText("已启用");
  await expect(page.locator(".group-title").last()).toHaveText("已停用");
  // 对齐冻结件 g4-10 的取景：把「已停用」段标题滚到面板中部，让上一段尾部与该段卡片同框
  // （scrollIntoViewIfNeeded 只会把标题贴到面板底边，拍不到该段任何一张卡片）
  const offTitle = page.locator(".group-title").last();
  await offTitle.evaluate(el => el.scrollIntoView({block: "center"}));
  await expect(offTitle).toBeInViewport();
  await expect(page.locator("[data-extension-id=\"demo.batch-plot\"]")).toBeInViewport();
  await shoot(page, info, "g8-ext-03-grouped-light.png");
});

test("g8-ext-04 扩展分区·四条（深色·1280×720，对照 g4-11）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  await page.addInitScript(() => localStorage.setItem("dst-manager-theme", "dark"));
  await openExtensions(page, multiList());
  await expect(page.locator(".ext-card")).toHaveCount(4);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await shoot(page, info, "g8-ext-04-multi-dark.png");
});

test("g8-ext-05 扩展分区·四条（浅色·900×600，最小视口断点，无冻结对照）", async ({page}, info) => {
  await page.setViewportSize({width: 900, height: 600});
  await openExtensions(page, multiList());
  await expect(page.locator(".ext-card")).toHaveCount(4);
  await shoot(page, info, "g8-ext-05-min-viewport-light.png");
});

// =====================================================================
// PLAN-DM-025 任务 9 步骤 5（G8）：扩展设置入口与两类子视图的生产证据。
// 断言只用可见事实（可访问名/角色、DOM 顺序、输入值与 aria-* 关系、视口盒），不做像素比对。
// 取景：被证对象必须先滚入可视区并断言 toBeInViewport，否则截图不能独立说明该状态。
// =====================================================================
const SETTINGS_DIALOG = 'dialog[aria-labelledby="settings-title"]';
const CONFIG_VIEW = '[data-view="extension-config"]';
const CATALOG_NAME = "图纸目录";
const GENERATED_NAME = "图框批量更新";
const CATALOG_PANEL = '[data-testid="sheet-catalog-settings-panel"]';
const CATALOG_FILTER = '[data-testid="catalog-settings-filter"]';
const CATALOG_FILTER_ERROR = '[data-testid="catalog-settings-filter-error"]';
const FILTER_FIELD = "excluded_title_keywords";
const FILTER_HINT = "图名包含任一关键词时不写入目录，多个关键词用逗号分隔";
// 编辑态「未提交」断言需要覆盖防抖窗口：只写 `toHaveLength(0)` 在请求尚未发出时同样成立，
// 等待窗口后再断言才真的排除了「输入即自动保存」。取值见 catalogs 保存为显式动作（无自动保存），
// 这里只排除防抖/延时提交，不影响用例实际耗时感知。
const DRAFT_DEBOUNCE_WINDOW_MS = 400;

// 进入某个扩展的配置子视图（同一设置 <dialog> 内的平级子视图，SC-17）
async function openConfigView(page: Page, name: string): Promise<void> {
  await page.getByRole("button", {name: `配置 ${name}`}).click();
  await expect(page.locator(SETTINGS_DIALOG).locator(CONFIG_VIEW)).toBeVisible();
}

// 图纸目录 custom 设置 mock：schema_version 取自 Manifest（2），value 是持久值。
// PUT 被夹具接管（Provider 规范化 + 上限校验同构），不会落到真实后端。
async function installCatalogSettings(page: Page, value: Record<string, unknown> = {user_templates: []}) {
  return installExtensionSettings(page, {schemaVersion: 2, items: [], value});
}

test("g8-ext-06 扩展配置入口：声明设置的卡片动作行出现「配置」（浅色·1280×720，对照 g4-13）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  await installExtensionSettings(page);
  await openExtensions(page, multiList());

  const catalog = page.locator("[data-extension-id=\"dst-manager.sheet-catalog\"]");
  // 动作行 DOM 顺序固定为「配置 → 状态文字 → 开关」（SC-16/SC-17 同一行事实，
  // 与冻结件 g4-13、Demo 的 actionRow 探针同口径）：只断言数量无法证明顺序
  expect(await catalog.locator(".ext-side > *").evaluateAll(elements => elements.map(element =>
    element.hasAttribute("data-config-opener") ? "配置入口"
      : element.classList.contains("ext-state") ? "状态文字"
        : element.getAttribute("role") === "switch" ? "开关" : `未知:${element.tagName}`)))
    .toEqual(["配置入口", "状态文字", "开关"]);
  const entry = catalog.getByRole("button", {name: `配置 ${CATALOG_NAME}`});
  await expect(entry).toBeVisible();
  await expect(entry).toBeEnabled();
  // 4 条样本里声明设置的只有两条（图纸目录 custom、图框批量更新 generated），与 g4-13 同口径
  await expect(page.locator("[data-config-opener]")).toHaveCount(2);
  // 未声明设置的卡片：动作行只剩「状态文字 → 开关」，没有任何配置入口（更不留白按钮）
  const noSettings = page.locator('[data-extension-id="demo.attribute-export"]');
  expect(await noSettings.locator(".ext-side > *").evaluateAll(elements => elements.map(element =>
    element.hasAttribute("data-config-opener") ? "配置入口"
      : element.classList.contains("ext-state") ? "状态文字"
        : element.getAttribute("role") === "switch" ? "开关" : `未知:${element.tagName}`)))
    .toEqual(["状态文字", "开关"]);
  await expect(noSettings.locator("[data-config-opener]")).toHaveCount(0);

  await catalog.scrollIntoViewIfNeeded();
  await expect(entry).toBeInViewport();
  await shoot(page, info, "g8-ext-06-config-entry-light.png");
});

test("g8-ext-07 扩展配置子视图·generated 通用表单（浅色·1280×720，对照 g4-14）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  const mock = await installExtensionSettings(page);
  await openExtensions(page, multiList());
  // 自守护：字段顺序断言只有在本载荷的 order 非单调时才有鉴别力（夹具刻意写成 3/1/5/2/4）。
  // 若把 order 改回 1..5，「按数组顺序渲染」与「客户端按 order 重排」会同样通过，断言即成恒真。
  expect(
    mock.server.items.map(item => item.order),
    "载荷 order 变成单调递增：字段顺序断言已失去鉴别力，请恢复夹具的非单调取值",
  ).not.toEqual([...mock.server.items.map(item => item.order)].sort((a, b) => a - b));
  // 声明 generated 的样本同样走统一入口（入口只取决于「是否声明设置」，与呈现类型无关）
  await expect(page.locator(`[data-config-opener="${GENERATED_EXTENSION_ID}"]`)).toBeVisible();
  await openConfigView(page, GENERATED_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  // 子视图在同一对话框内：标题、唯一出路（返回扩展列表）与页脚「保存」都在
  await expect(dialog.getByRole("heading", {name: `配置 · ${GENERATED_NAME}`})).toBeVisible();
  await expect(dialog.getByRole("button", {name: "返回扩展列表"})).toBeVisible();
  await expect(dialog.locator("[role=\"dialog\"]")).toHaveCount(0);

  const form = dialog.locator(".ef-form");
  // 字段顺序 = 服务端给出的数组顺序（前端不重排、不丢弃未知字段）。载荷 order 非单调，
  // 因此该序列同时排除「客户端按 order 重排」的实现，不是恒真断言。
  expect(await form.locator(".ef-row").evaluateAll(rows => rows.map(row => row.getAttribute("data-field"))))
    .toEqual(["frame_block_prefix", "batch_limit", "write_back_titleblock", "ratio_threshold", "conflict_strategy"]);
  // 控件词表逐一落到契约控件：boolean→开关、integer/number→数字框、string→文本框、enum→单选组
  await expect(form.getByRole("switch", {name: "回写标题栏"})).toHaveAttribute("aria-checked", "true");
  await expect(form.getByRole("textbox", {name: "图框块名前缀"})).toHaveValue("TK-");
  await expect(form.getByRole("spinbutton", {name: "单批处理上限"})).toHaveValue("50");
  await expect(form.getByRole("spinbutton", {name: "比例容差"})).toHaveValue("0.5");
  await expect(form.getByRole("radiogroup", {name: "属性冲突处理"})).toBeVisible();
  await expect(form.getByRole("radio", {name: "ask"})).toBeChecked();
  // 标签与描述来自清单身份字段（label_key/description_key），不由本层重写
  await expect(form.getByText("写入图框块名的固定前缀")).toBeVisible();
  // 未改动时不点亮保存：表单是缓冲式的，控件即改即脏（g4-14 同一条表单）
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeDisabled();

  await expect(form).toBeInViewport();
  await shoot(page, info, "g8-ext-07-generated-light.png");
});

test("g8-ext-08 扩展配置子视图·custom 面板输出图纸过滤默认态（深色·1280×720，对照 g4-15）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  await page.addInitScript(() => localStorage.setItem("dst-manager-theme", "dark"));
  await installCatalogSettings(page);
  await openExtensions(page, [extensionSummary()]);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  await expect(dialog.locator(CATALOG_PANEL)).toBeVisible();
  const filter = dialog.locator(CATALOG_FILTER);
  await expect(dialog.getByText("输出图纸过滤", {exact: true})).toBeVisible();
  // 默认态：未配置过滤（输入为空），格式由示例占位提示；不做本地预判，无错误态
  await expect(filter).toHaveValue("");
  await expect(filter).toHaveAttribute("placeholder", "草图, 作废, TEMP");
  await expect(filter).toHaveAttribute("aria-invalid", "false");
  await expect(dialog.locator(CATALOG_FILTER_ERROR)).toHaveCount(0);
  // 字段说明与输入框的 aria-describedby 关系真实成立（说明元素存在且正文一致）
  const describedBy = await filter.getAttribute("aria-describedby");
  expect(describedBy).toBe("catalog-settings-filter-hint");
  await expect(dialog.locator(`#${describedBy}`)).toHaveText(FILTER_HINT);
  // 未改动时页脚「保存」不可点（不会误提交空过滤）
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeDisabled();

  await filter.scrollIntoViewIfNeeded();
  await expect(filter).toBeInViewport();
  await shoot(page, info, "g8-ext-08-custom-dark.png");
});

test("g8-ext-09 custom 面板输出图纸过滤编辑态（浅色·1280×720，无冻结对照）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  const mock = await installCatalogSettings(page);
  await openExtensions(page, [extensionSummary()]);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  const filter = dialog.locator(CATALOG_FILTER);
  await filter.fill("草图, TEMP, 作废");
  // 编辑态：输入原样呈现（前端不拆分、不去重、不截断），字段无错误态，保存按钮点亮
  await expect(filter).toHaveValue("草图, TEMP, 作废");
  await expect(filter).toHaveAttribute("aria-invalid", "false");
  await expect(dialog.locator(CATALOG_FILTER_ERROR)).toHaveCount(0);
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeEnabled();
  // 编辑态不等于已提交：等待覆盖防抖窗口后仍无任何 PUT 发出，服务端值仍为空
  // （不能只写 `expect(mock.puts).toHaveLength(0)`：请求尚未发出时它同样会通过）
  await page.waitForTimeout(DRAFT_DEBOUNCE_WINDOW_MS);
  expect(mock.puts, "过滤输入编辑态在防抖窗口内不得发出 PUT").toHaveLength(0);

  await filter.scrollIntoViewIfNeeded();
  await expect(filter).toBeInViewport();
  await shoot(page, info, "g8-ext-09-custom-filter-edited-light.png");
});

test("g8-ext-10 custom 面板输出图纸过滤字段错误态（浅色·1280×720，无冻结对照）", async ({page}, info) => {
  await page.setViewportSize({width: 1280, height: 720});
  const mock = await installCatalogSettings(page);
  await openExtensions(page, [extensionSummary()]);
  await openConfigView(page, CATALOG_NAME);

  const dialog = page.locator(SETTINGS_DIALOG);
  const filter = dialog.locator(CATALOG_FILTER);
  // 51 项超出 Provider 声明的关键词上限 50：服务端 422 定位到 excluded_title_keywords
  const overLimit = Array.from({length: 51}, (_, index) => `k${index}`).join(", ");
  await filter.fill(overLimit);
  await dialog.getByRole("button", {name: "保存", exact: true}).click();
  await expect.poll(() => mock.puts.length).toBe(1);

  const error = dialog.locator(CATALOG_FILTER_ERROR);
  await expect(error).toBeVisible();
  await expect(error).toContainText("扩展设置无效");
  await expect(filter).toHaveAttribute("aria-invalid", "true");
  // 输入保留（不截断、不静默丢弃首尾）且未落盘：服务端值仍是默认空配置
  await expect(filter).toHaveValue(overLimit);
  expect(mock.server.value[FILTER_FIELD]).toBeUndefined();
  // 失败后仍可修正：保存按钮保持可点，子视图不关闭
  await expect(dialog.getByRole("button", {name: "保存", exact: true})).toBeEnabled();

  await filter.scrollIntoViewIfNeeded();
  await expect(filter).toBeInViewport();
  await expect(error).toBeInViewport();
  await shoot(page, info, "g8-ext-10-custom-filter-error-light.png");
});

// ---------------------------------------------------------------------------
// PLAN-DM-029 Task 8 控件视觉基础正交证据（Step 4）：保存浅/深默认、校验错误、扩展禁用、窄屏。
// 落盘约定与既有 g8-ext-* 完全一致：截图经 testInfo 附件留档，验收时**显式复制**到
// `docs/dst-manager/specs/assets/SPEC-DM-011/production/`（目录已存在）——**刻意不加 env 开关
// 自动写库**（目录页那套会无差别覆盖既有验收资产，已登记为责任 T）。
// 本文件**不保存任何设置**（settings-dialog.spec.ts 串行共享同一隔离配置文件）。
// 每张图都配计算样式/几何断言，避免「有图无证据」。
// ---------------------------------------------------------------------------
test.describe("Task 8 控件视觉基础正交证据（PLAN-DM-029）", () => {
  async function openSettingsWithTheme(page: Page, theme: "light" | "dark"): Promise<void> {
    await page.addInitScript(value => localStorage.setItem("dst-manager-theme", value), theme);
    await page.goto("/");
    await openSettingsDialog(page);
  }

  async function makeDirty(page: Page): Promise<void> {
    await page.locator('input[data-key="cad_timeout_seconds"]').fill("900");
    await expect(page.getByRole("button", {name: "保存"})).toBeEnabled();
  }

  test("task8-01 保存浅色默认（1280×720）：脏状态保存可用 + 控件 34px 紧凑档", async ({page}, info) => {
    await page.setViewportSize({width: 1280, height: 720});
    await openSettingsWithTheme(page, "light");
    await makeDirty(page);
    const field = page.locator('[data-field="cad_timeout_seconds"]');
    await expect(field.locator("label"), "字段行必有可见 label").toBeVisible();
    const inputBox = (await field.locator("input").boundingBox())!;
    expect(Math.round(inputBox.height), "设置输入保持 34px 紧凑档（T8-1(D)）").toBe(34);
    await shoot(page, info, "task8-01-save-light-1280x720.png");
  });

  test("task8-02 保存深色默认（1280×720）：与浅色同状态成对比对", async ({page}, info) => {
    await page.setViewportSize({width: 1280, height: 720});
    await openSettingsWithTheme(page, "dark");
    await makeDirty(page);
    await expect(page.getByRole("button", {name: "保存"})).toBeEnabled();
    await shoot(page, info, "task8-02-save-dark-1280x720.png");
  });

  test("task8-03 校验错误：行内错误进入 aria-describedby 且保存禁用", async ({page}, info) => {
    await page.setViewportSize({width: 1280, height: 720});
    await openSettingsWithTheme(page, "light");
    const lease = page.locator('input[data-key="worker_lease_seconds"]');
    await lease.fill("5000");
    const error = page.locator('[data-field="worker_lease_seconds"] .f-error');
    await expect(error, "超范围必须显示行内错误").toBeVisible();
    const errorId = await error.getAttribute("id");
    expect(errorId, "error 必须有 id").toBeTruthy();
    const described = ((await lease.getAttribute("aria-describedby")) ?? "").split(/\s+/).filter(Boolean);
    expect(described, "错误文字必须经 aria-describedby 关联（仅视觉相邻不算）").toContain(errorId);
    await expect(page.getByRole("button", {name: "保存"})).toBeDisabled();
    // Minor-D：取景约定（同文件头部 :129「被证对象必须先滚入可视区」）——
    // 否则错误文案落在对话框可视区之外，这张图不能独立说明「校验错误」状态。
    await error.scrollIntoViewIfNeeded();
    await expect(error, "错误文案必须滚入可视区，截图才可独立作证").toBeInViewport();
    await shoot(page, info, "task8-03-validation-error-1280x720.png");
  });

  test("task8-04 扩展禁用：已停用卡片，开关可点盒 ≥44×32 且轨道仍 44×24", async ({page}, info) => {
    await page.setViewportSize({width: 1280, height: 720});
    await openExtensions(page, [extensionSummary({enabled: false, status: "DISABLED"})]);
    const card = page.locator(".ext-card");
    await expect(card.locator(".badge", {hasText: "已停用"})).toBeVisible();
    await expect(card.getByRole("switch")).toHaveAttribute("aria-checked", "false");
    const switchBox = (await card.locator(".switch").boundingBox())!;
    expect(Math.round(switchBox.width), "开关外层可点宽度").toBeGreaterThanOrEqual(44);
    expect(Math.round(switchBox.height), "开关外层可点高度必须 ≥32px").toBeGreaterThanOrEqual(32);
    const trackBox = (await card.locator(".switch-track").boundingBox())!;
    expect(Math.round(trackBox.width), "视觉轨道宽度").toBe(44);
    expect(Math.round(trackBox.height), "视觉轨道高度").toBe(24);
    await shoot(page, info, "task8-04-extension-disabled-1280x720.png");
  });

  test("task8-05 窄屏（900×600）：设置对话框不产生整页横向溢出", async ({page}, info) => {
    await page.setViewportSize({width: 900, height: 600});
    await openSettingsWithTheme(page, "light");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, "窄屏不得出现整页横向溢出").toBeLessThanOrEqual(1);
    await shoot(page, info, "task8-05-narrow-900x600.png");
  });
});
