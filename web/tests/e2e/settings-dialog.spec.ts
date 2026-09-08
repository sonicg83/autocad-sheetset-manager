// 设置中心模态对话框 e2e（PLAN-DM-019 任务 10，SPEC-DM-011 SC-02~09/11/12/14）。
// 契约红线：不 mock /api/settings 与 /api/about——全局 setup 已否动真实后端，
// 配置经 DST_MANAGER_SETTINGS_PATH 指向固定临时目录；本文件用例串行执行
//（共享同一配置文件，保存/损坏/Schema 场景彼此有状态依赖）。
import {expect, test} from "@playwright/test";
import {SETTINGS_PATH, expectDialog, openSettingsDialog, writeSettingsFile} from "./fixtures/settings";

test.describe.configure({mode: "serial"});

const TIMEOUT_INPUT = 'input[data-key="cad_timeout_seconds"]';
const TIMEOUT_ROW = '[data-field="cad_timeout_seconds"]';

test("修改→保存→重开对话框值保留且来源变为用户覆盖", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  const timeout = page.locator(TIMEOUT_INPUT);
  await timeout.fill("900");
  await page.getByRole("button", {name: "保存"}).click();
  await expect(page.getByText("已保存").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("900");
  const row = page.locator(TIMEOUT_INPUT).locator("..");
  await expect(row).toContainText("用户覆盖");
});

test("数字超范围显示行内错误且保存禁用", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  const lease = page.locator('input[data-key="worker_lease_seconds"]');
  await lease.fill("5000");
  await expect(page.getByText("必须在 30–3600 之间")).toBeVisible();
  await expect(page.getByRole("button", {name: "保存"})).toBeDisabled();
  // 行内错误字段红边框（SC-06），修正后错误消失且保存恢复可用
  await expect(page.locator('[data-field="worker_lease_seconds"]')).toHaveClass(/error/);
  await lease.fill("600");
  await expect(page.getByText("必须在 30–3600 之间")).toBeHidden();
  await expect(page.getByRole("button", {name: "保存"})).toBeEnabled();
});

test("恢复继承：随下一次保存提交 unset 并回到默认", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  // 上一用例已把 cad_timeout_seconds 存为用户覆盖（900）
  const row = page.locator(TIMEOUT_ROW);
  await expect(row).toContainText("用户覆盖");
  await row.getByRole("button", {name: "恢复继承"}).click();
  // 契约语义：点击不落盘，标记随下次保存提交
  await row.getByRole("button", {name: "撤销恢复继承"}).click();
  await row.getByRole("button", {name: "恢复继承"}).click();
  await page.getByRole("button", {name: "保存"}).click();
  await expect(page.getByText("已保存").first()).toBeVisible();
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("600");
  await expect(page.locator(TIMEOUT_ROW)).toContainText("默认");
  await expect(page.locator(TIMEOUT_ROW)).not.toContainText("恢复继承");
});

test("未保存修改时关闭需确认（留在此处/放弃修改并关闭）", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  const timeout = page.locator(TIMEOUT_INPUT);
  await timeout.fill("777");
  await page.keyboard.press("Escape");
  const confirm = page.getByRole("dialog", {name: "有未保存的修改"});
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", {name: "留在此处"}).click();
  await expect(page.getByRole("dialog", {name: "设置"})).toBeVisible();
  await expect(timeout).toHaveValue("777");
  await page.keyboard.press("Escape");
  await page.getByRole("dialog", {name: "有未保存的修改"}).getByRole("button", {name: "放弃修改并关闭"}).click();
  await expect(page.getByRole("dialog", {name: "设置"})).toBeHidden();
  // 静默丢弃被禁止：放弃后重开应回到已保存值
  await openSettingsDialog(page);
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("600");
});

test("关于分区：应用名+版本、MIT 全文与外链（浏览器开发态 window.open）", async ({page}) => {
  await page.goto("/");
  // 仅拦截第三方站点（离线环境无法真实访问 github），应用自身契约不 mock；
  // popup 由 window.open 产生，page.route 不覆盖，须挂到 context 级
  await page.context().route("**/github.com/**", route => route.fulfill({status: 200, body: ""}));
  await openSettingsDialog(page);
  await page.getByRole("tab", {name: "关于"}).click();
  const aboutPanel = page.locator(".about-block");
  await expect(aboutPanel.first()).toContainText("DST Manager");
  await expect(aboutPanel.first()).toContainText(/v\d+\.\d+\.\d+/);
  await expect(aboutPanel.nth(1)).toContainText("MIT License");
  const homepage = "https://github.com/sonicg83/autocad-sheetset";
  const [popup] = await Promise.all([
    page.waitForEvent("popup"),
    page.getByRole("button", {name: "项目主页"}).click(),
  ]);
  await expect(popup).toHaveURL(new RegExp(`^${homepage.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  await popup.close();
});

test("浏览器开发态浏览按钮禁用（SC-04 降级）", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  await expect(page.getByRole("button", {name: "浏览…"}).first()).toBeDisabled();
});

test("配置文件损坏：诊断横幅（amber）且回退默认值", async ({page}) => {
  await page.goto("/");
  writeSettingsFile("{ 这不是合法 JSON", 3);
  await openSettingsDialog(page);
  const banner = page.getByRole("alert").filter({hasText: "SETTINGS_FILE_CORRUPT"});
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("默认值");
  // 损坏仅回退默认值，不进入只读（schemaBlocked=false）：横幅为 amber 而非红色只读
  await expect(page.locator(".diag.readonly")).toBeHidden();
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("600");
  // 还原合法文件，避免影响后续用例（文件已被后端备份改名，重写即恢复）
  writeSettingsFile({}, 3);
});

test("Schema 过新：红色只读诊断横幅，输入与保存禁用（SC-12）", async ({page}) => {
  await page.goto("/");
  writeSettingsFile({}, 5, 99);
  await openSettingsDialog(page);
  const banner = page.getByRole("alert").filter({hasText: "SETTINGS_SCHEMA_NEWER"});
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("只读");
  await expect(page.getByRole("button", {name: "保存"})).toBeDisabled();
  await expect(page.locator(TIMEOUT_INPUT)).toBeDisabled();
  writeSettingsFile({}, 5);
});

test("焦点圈闭与归还：打开聚焦首字段，Esc 关闭后焦点回到齿轮", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  await expect(page.locator(".panel input").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", {name: "设置"})).toBeHidden();
  await expect(page.getByRole("button", {name: "设置"})).toBeFocused();
});

test("对话框打开时拖放不穿透遮罩（SC-14）", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  const info = await page.evaluate(() => {
    const target = document.elementFromPoint(120, 360) as Element | null;
    const data = new DataTransfer();
    data.setData("text/plain", "C:\\project\\drop.dst");
    target?.dispatchEvent(new DragEvent("drop", {bubbles: true, cancelable: true, dataTransfer: data}));
    // 顶层对话框拦截命中测试：坐标点上的元素必须位于对话框子树内
    const dialog = document.querySelector("dialog");
    return {
      inDialog: target instanceof Element && dialog !== null && dialog.contains(target),
      dialogOpen: dialog !== null && dialog.open,
    };
  });
  expect(info.inDialog).toBe(true);
  expect(info.dialogOpen).toBe(true);
  // 底层页面状态不变：无错误提示、欢迎区未被拖入路径扰动
  await expect(page.locator(".error.notice")).toBeHidden();
  await expect(page.getByRole("region", {name: "打开图纸集"})).toBeVisible();
});
