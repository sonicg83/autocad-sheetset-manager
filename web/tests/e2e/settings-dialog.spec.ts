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
  // cad_max_parallel 属 SC-13 条件提示键集：本次保存须追加"相关预览将按新配置重算"
  await page.locator('input[data-key="cad_max_parallel"]').fill("6");
  await page.getByRole("button", {name: "保存"}).click();
  await expect(page.getByText("已保存").first()).toBeVisible();
  await expect(page.getByText("相关预览将按新配置重算")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("900");
  const row = page.locator(TIMEOUT_INPUT).locator("..");
  await expect(row).toContainText("用户覆盖");
  await expect(page.locator('input[data-key="cad_max_parallel"]')).toHaveValue("6");
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
  // 先编辑再恢复继承：编辑缓冲被丢弃（不与 unset 同键提交，用户编辑不静默混入本次保存）
  await page.locator(TIMEOUT_INPUT).fill("999");
  await row.getByRole("button", {name: "恢复继承"}).click();
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("900");
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
  // 先写坏再加载：启动读取确定命中损坏文件（消除启动读取与写入的竞态）。
  // 损坏使 ui_locale 回退默认 system，界面语言随系统（浏览器）解析（SPEC-DM-013 §3.1），
  // 故对话框可访问名称不固定，期望断言按中英双语容忍；诊断码与控件行为与语言无关
  writeSettingsFile("{ 这不是合法 JSON", 3);
  await page.goto("/");
  await page.getByRole("button", {name: "设置"}).click();
  await page.locator('input[data-key="cad_timeout_seconds"]').waitFor();
  const banner = page.getByRole("alert").filter({hasText: "SETTINGS_FILE_CORRUPT"});
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(/默认值|default values/);
  // 损坏仅回退默认值，不进入只读（schemaBlocked=false）：横幅为 amber 而非红色只读
  await expect(page.locator(".diag.readonly")).toBeHidden();
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("600");
  // 还原合法文件，避免影响后续用例（文件已被后端备份改名，重写即恢复）；
  // values 显式带回 ui_locale，防止后续用例随 system 解析漂移到浏览器语言
  writeSettingsFile({ui_locale: "zh-CN", cad_max_parallel: 6}, 3);
});

test("Schema 过新：红色只读诊断横幅，输入与保存禁用（SC-12）", async ({page}) => {
  // 先写后加载（同损坏用例：消除启动读取与写入竞态）。schema 过新时 resolver 降级：
  // values 整体失效（含 ui_locale → 默认 system），界面随系统语言解析（SPEC-DM-013 §3.3
  // "界面继续使用启动时已解析的语言"），故断言按中英双语容忍
  writeSettingsFile({}, 5, 99);
  await page.goto("/");
  await page.getByRole("button", {name: "设置"}).click();
  await page.locator('input[data-key="cad_timeout_seconds"]').waitFor();
  const banner = page.getByRole("alert").filter({hasText: "SETTINGS_SCHEMA_NEWER"});
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(/只读|Read-only/);
  await expect(page.locator(".dlg-foot button.primary")).toBeDisabled();
  await expect(page.locator(TIMEOUT_INPUT)).toBeDisabled();
  // 还原合法文件并保留 ui_locale（防止后续用例漂移到浏览器语言）
  writeSettingsFile({ui_locale: "zh-CN"}, 5);
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
    // 壳侧 drop 监听挂 document（shell.py）：在 document 挂 spy，断言对话框
    // 子树内的 drop 被 stop 后不再冒泡到 document（浏览器内可验证的部分）
    (window as unknown as Record<string, number>).__documentDropSeen = 0;
    document.addEventListener("drop", () => {(window as unknown as Record<string, number>).__documentDropSeen += 1;});
    const dialog = document.querySelector("dialog")!;
    const data = new DataTransfer();
    data.setData("text/plain", "C:\\project\\drop.dst");
    // 1) 命中测试：遮罩打开时坐标点上的元素必须位于顶层对话框子树内
    const target = document.elementFromPoint(120, 360) as Element | null;
    const inDialog = target instanceof Element && dialog.contains(target);
    // 2) 对话框子树内派发 drop：不冒泡出 dialog（stop），document spy 不得收到
    dialog.dispatchEvent(new DragEvent("drop", {bubbles: true, cancelable: true, dataTransfer: data}));
    return {inDialog, dialogOpen: dialog.open, documentDropSeen: (window as unknown as Record<string, number>).__documentDropSeen};
  });
  expect(info.inDialog).toBe(true);
  expect(info.dialogOpen).toBe(true);
  expect(info.documentDropSeen).toBe(0);
  // 底层页面状态不变：无错误提示、欢迎区未被拖入路径扰动
  await expect(page.locator(".error.notice")).toBeHidden();
  await expect(page.getByRole("region", {name: "打开图纸集"})).toBeVisible();
});

// 任务 11 入口专项补充（前 10 个用例已在未加载态经齿轮打开对话框，此处补显式断言）
test("未加载工作区时齿轮常驻可见可开（SC-01 入口）", async ({page}) => {
  await page.goto("/");
  // 未加载态：欢迎区可见（尚未打开任何 DST），入口不随工作区状态隐藏
  await expect(page.getByRole("region", {name: "打开图纸集"})).toBeVisible();
  const gear = page.getByRole("button", {name: "设置"});
  await expect(gear).toBeVisible();
  await expect(gear).toBeEnabled();
  await gear.click();
  await expectDialog(page);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", {name: "设置"})).toBeHidden();
});

test("重复打开不产生多实例且字段无状态残留", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  // 既有状态链保存值：cad_timeout_seconds=600（默认，前文已恢复继承）、cad_max_parallel=6（用户覆盖）
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("600");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", {name: "设置"})).toBeHidden();
  // 再次点齿轮重开：对话框实例唯一，未做编辑不触发未保存确认
  await openSettingsDialog(page);
  await expect(page.getByRole("dialog", {name: "设置"})).toHaveCount(1);
  await expect(page.getByRole("dialog", {name: "有未保存的修改"})).toBeHidden();
  // 字段与上次保存一致，无上一轮残留（无行内错误、无只读诊断、无脏字段高亮）；
  // 保存按钮按设计保持可聚焦（空保存由 onSave no-op 守卫承担），无脏字段以 .dirty 计数为证
  await expect(page.locator(TIMEOUT_INPUT)).toHaveValue("600");
  await expect(page.locator(TIMEOUT_ROW)).toContainText("默认");
  await expect(page.locator(".diag.readonly")).toBeHidden();
  await expect(page.locator(".field.dirty")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "保存"})).toBeEnabled();
});

// ---- PLAN-DM-021 Task 3：语言切换事务与双语错误恢复（SPEC-DM-013 §3.2/§3.3）----
// 既有用例依赖中文基线，语言事务用例按"可回滚状态"排列：每个用例先显式写入
// ui_locale 基线（前文"损坏/Schema"用例会把 values 清空，默认 system 会随
// 浏览器非中文 navigator 解析成 en-US），切换语言的用例放串行链最后并还原。

test("语言选择未保存不切换：取消后保持生效语言与快照选择", async ({page}) => {
  writeSettingsFile({ui_locale: "zh-CN", cad_max_parallel: 6}, 3);
  await page.goto("/");
  await openSettingsDialog(page);
  await page.locator('input[data-key="ui_locale"][value="en-US"]').check();
  await page.keyboard.press("Escape");
  const confirm = page.getByRole("dialog", {name: "有未保存的修改"});
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", {name: "放弃修改并关闭"}).click();
  await expect(page.getByRole("dialog", {name: "设置"})).toBeHidden();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  // 重开：取消不落盘，语言仍为快照中的简体中文
  await openSettingsDialog(page);
  await expect(page.locator('input[data-key="ui_locale"][value="zh-CN"]')).toBeChecked();
});

test("422 结构化错误：错误摘要聚焦并链接字段、语言与输入保留、对话框保持", async ({page}) => {
  writeSettingsFile({ui_locale: "zh-CN", cad_max_parallel: 6}, 3);
  await page.goto("/");
  await openSettingsDialog(page);
  // 契约红线的受限例外：仅拦截本次 PUT 复现 Task 1 冻结的 422 结构化错误体
  //（UI 无法构造出后端才能判定的越界负载）；GET 与其余用例仍走真实后端。
  await page.route("**/api/settings", async route => {
    if (route.request().method() !== "PUT") return route.fallback();
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        code: "SETTINGS_VALIDATION_FAILED",
        errors: {
          cad_timeout_seconds: {
            code: "SETTING_INTEGER_RANGE",
            message_key: "settings.validation.integerRange",
            params: {min: 30, max: 3600},
            message: "CAD 超时（秒） 必须介于 30 和 3600 之间",
          },
        },
      }),
    });
  });
  const timeout = page.locator(TIMEOUT_INPUT);
  await timeout.fill("120");
  await page.getByRole("button", {name: "保存"}).click();
  const summary = page.getByTestId("settings-error-summary");
  await expect(summary).toBeFocused(); // 错误摘要取得焦点（tabindex=-1）
  await expect(summary).toContainText("CAD 超时（秒）"); // 摘要条目解析字段标签
  await expect(summary).toContainText("必须在 30–3600 之间"); // message_key + 结构化参数
  await expect(page.getByRole("dialog", {name: "设置"})).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN"); // 语言不变
  await expect(timeout).toHaveValue("120"); // 本地输入保留
  // 摘要条目链接到字段：点击后焦点落到对应字段
  await summary.getByRole("button").first().click();
  await expect(timeout).toBeFocused();
});

test("409 冲突恢复：提示可见、输入与语言保留、对话框保持", async ({page}) => {
  writeSettingsFile({ui_locale: "zh-CN", cad_max_parallel: 6}, 3);
  await page.goto("/");
  await openSettingsDialog(page);
  // 同上：仅拦截 PUT 返回 409（并发修订冲突在单客户端 e2e 中无法自然复现）
  await page.route("**/api/settings", async route => {
    if (route.request().method() !== "PUT") return route.fallback();
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({code: "SETTINGS_CONFLICT", message: "config revision conflict"}),
    });
  });
  const timeout = page.locator(TIMEOUT_INPUT);
  await timeout.fill("650");
  await page.getByRole("button", {name: "保存"}).click();
  await expect(page.getByText("配置已被其他窗口修改，已刷新为最新配置，请核对后重试")).toBeVisible();
  await expect(page.getByRole("dialog", {name: "设置"})).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(timeout).toHaveValue("650"); // 本地选择保留，等待用户重试或取消
});

test("保存成功切换语言：html[lang] 同步、对话框保持、焦点恢复、背景输入不丢失", async ({page}) => {
  writeSettingsFile({ui_locale: "zh-CN", cad_max_parallel: 6}, 3);
  await page.goto("/");
  // 背景页面输入：打开对话框前在欢迎区路径框键入，切换后不得丢失（I18N-06）
  const bgInput = page.locator(".no-shell input");
  await bgInput.fill("C:\\temp\\keep.dst");
  await openSettingsDialog(page);
  await page.locator('input[data-key="ui_locale"][value="en-US"]').check();
  await page.getByRole("button", {name: "保存"}).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
  // 对话框保持打开，界面整体切换为英文（可访问名称随标题切换）
  await expect(page.getByRole("dialog", {name: "Settings"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Save"})).toBeFocused(); // nextTick 焦点恢复
  await expect(page.getByTestId("settings-saved-pill")).toHaveText("Saved"); // 本地化成功反馈
  // "跟随系统（当前：…）"复合标签随语言切换；当前生效语言为 en-US，自称形式显示 English
  //（SPEC-DM-013 §5.1：英文界面显示 "Follow system (current: English)"）
  await expect(page.getByText("Follow system (current: English)")).toBeVisible();
  await expect(page.getByText("CAD timeout (seconds)")).toBeVisible(); // 英文长标签完整渲染
  await expect(bgInput).toHaveValue("C:\\temp\\keep.dst");
  // 还原中文基线（本用例为串行链最后一个，覆盖值与 Task 3 之前的状态一致）
  writeSettingsFile({ui_locale: "zh-CN", cad_max_parallel: 6}, 4);
});
