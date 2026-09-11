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
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {openSettingsDialog} from "./fixtures/settings";
import {extensionSummary, installExtensions} from "./fixtures/extensions";

// 4 条多状态样本：可用 / 已停用 / 启动失败（且用户意图启用）/ 不兼容（含诊断码）
function multiList(): unknown[] {
  return [
    extensionSummary({extension_id: "dst-manager.sheet-catalog", name_key: "图纸目录", description_key: "从图纸集数据生成图纸目录工作簿（XLSX），支持输出模板与字段表达式。"}),
    extensionSummary({extension_id: "demo.frame-update", name_key: "图框批量更新", description_key: "按图框属性表批量替换图框块并回写标题栏字段。", status: "DISABLED", enabled: false}),
    extensionSummary({extension_id: "demo.attribute-export", name_key: "属性批量导出", description_key: "把图纸与子集属性导出为制表符分隔文本，供外部审计比对。", status: "FAILED", enabled: true, error_code: "EXTENSION_START_FAILED"}),
    extensionSummary({extension_id: "demo.sheet-validate", name_key: "图纸一致性校验", description_key: "校验图号与文件名一致性并列出不一致项。", status: "INCOMPATIBLE", enabled: false, error_code: "EXTENSION_HOST_CONTRACT_MISMATCH"}),
  ];
}

// 8 条触发分段样本：已启用 4、已停用 4（分段键 = enabled）
function groupedList(): unknown[] {
  return [
    ...multiList(),
    extensionSummary({extension_id: "demo.batch-plot", name_key: "批量打印", description_key: "按子集输出 PDF 打印任务并记录每张图纸的结果。", status: "DISABLED", enabled: false}),
    extensionSummary({extension_id: "demo.layer-audit", name_key: "图层审计", description_key: "汇总各图纸的图层使用情况与未使用图层。", status: "AVAILABLE", enabled: true}),
    extensionSummary({extension_id: "demo.titleblock-sync", name_key: "标题栏同步", description_key: "把子集属性同步到标题栏的已登记字段。", status: "DISABLED", enabled: false}),
    extensionSummary({extension_id: "demo.cad-version-report", name_key: "CAD 版本报告", description_key: "统计图纸保存版本并提示需转换的文件。", status: "AVAILABLE", enabled: true}),
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
