// 设置中心模态对话框 e2e（PLAN-DM-019 任务 10，SPEC-DM-011 SC-02~09/11/12/14）。
// 契约红线：不 mock /api/settings 与 /api/about——全局 setup 已否动真实后端，
// 配置经 DST_MANAGER_SETTINGS_PATH 指向固定临时目录；本文件用例串行执行
//（共享同一配置文件，保存/损坏/Schema 场景彼此有状态依赖）。
import {expect, test, type Locator, type Page} from "@playwright/test";
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

// ---- PLAN-DM-025 任务 6：关于分区抽为 AboutSection 后仍只请求一次 ----
// 契约红线（本文件头）不变：不 mock /api/about，只观察真实请求次数（page.on("request")）。
// 计数只在本文件内辅助断言，不影响当前用例串行共享的配置文件。
function countAboutRequests(page: Page): string[] {
  const aboutRequests: string[] = [];
  page.on("request", request => {
    if (new URL(request.url()).pathname === "/api/about") aboutRequests.push(request.url());
  });
  return aboutRequests;
}

// 拆分前安全网：分区来回切换不得重放 GET，且呈现与焦点与拆分前一致
test("关于分区：来回切换不重复请求 /api/about，元数据/外链可访问名与焦点稳定", async ({page}) => {
  const aboutRequests = countAboutRequests(page);
  await page.goto("/");
  await openSettingsDialog(page);
  const aboutTab = page.getByRole("tab", {name: "关于"});
  const aboutBlocks = page.locator(".about-block");
  await aboutTab.click();
  await expect(aboutBlocks.first()).toContainText("DST Manager");
  await expect(aboutBlocks.first()).toContainText(/v\d+\.\d+\.\d+/);
  await expect(aboutBlocks.nth(1)).toContainText("MIT License");
  // 外链可访问名固定（SC-11）；外链打开行为由上一用例断言，这里只钉住按钮仍在
  await expect(page.getByRole("button", {name: "项目主页"})).toBeVisible();
  await expect(page.getByRole("button", {name: "问题反馈"})).toBeVisible();
  // 进入关于分区不抢焦点：键盘用户仍停在分区标签上
  await expect(aboutTab).toBeFocused();
  // 切走再切回：分区组件重新挂载，模块级 memo 让整轮仍只有一个 GET
  await page.getByRole("tab", {name: "扩展"}).click();
  await expect(page.getByRole("tab", {name: "扩展"})).toBeFocused();
  await aboutTab.click();
  await expect(aboutBlocks.first()).toContainText("DST Manager");
  await expect(aboutTab).toBeFocused();
  expect(aboutRequests).toHaveLength(1);
});

// 会话级 memo：应用元数据静态不变（后端登记常量），关闭重开对话框也不得重放 GET
test("关于分区：关闭重开对话框不重复请求 /api/about", async ({page}) => {
  const aboutRequests = countAboutRequests(page);
  await page.goto("/");
  await openSettingsDialog(page);
  const aboutTab = page.getByRole("tab", {name: "关于"});
  await aboutTab.click();
  await expect(page.locator(".about-block").first()).toContainText("DST Manager");
  expect(aboutRequests).toHaveLength(1);
  // 关闭（分区回落常规配置）后重开：仍复用同一份元数据
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", {name: "设置"})).toBeHidden();
  await openSettingsDialog(page);
  await page.getByRole("tab", {name: "关于"}).click();
  await expect(page.locator(".about-block").first()).toContainText("DST Manager");
  expect(aboutRequests).toHaveLength(1);
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
  // Task 5 起外壳随生效语言切换：system 解析随浏览器语言，齿轮名称中英容忍
  await page.getByRole("button", {name: /设置|Settings/}).click();
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
  // Task 5 起外壳随生效语言切换：system 解析随浏览器语言，齿轮名称中英容忍
  await page.getByRole("button", {name: /设置|Settings/}).click();
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

// ---- PLAN-DM-021 Task 4：exe/dll 浏览的 file_kind + 本地化描述契约 ----
// 契约红线（原生文件选择白名单）：桥调用只传固定种类（exe/dll）与本地化描述，
// 白名单由壳侧按 kind 固定拼接——中英文切换只改变描述，种类（白名单）不变。

test("exe/dll 浏览：中英文只改变描述、固定种类（白名单）不变", async ({page}) => {
  writeSettingsFile({ui_locale: "zh-CN", cad_max_parallel: 6}, 5);
  await page.addInitScript(() => {
    (window as any).__fileDialogCalls = [];
    (window as any).pywebview = {
      api: {
        select_file: async (fileKind: string, description: string) => {
          (window as any).__fileDialogCalls.push({fileKind, description});
          return null; // 假桥只记录契约参数，不返回路径
        },
        select_folder: async () => {
          (window as any).__fileDialogCalls.push({fileKind: "folder"});
          return null;
        },
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });

  const browseCalls = async (browseLabel: string) => {
    await page.goto("/");
    // Task 5 起齿轮入口/壳界面随 ui_locale 切换，名称中英容忍；对话框标题随 ui_locale 切换
    await page.getByRole("button", {name: /设置|Settings/}).click();
    await page.locator('input[data-key="cad_timeout_seconds"]').waitFor();
    await page.locator('[data-field="autocad_2016_console"]').getByRole("button", {name: browseLabel}).click();
    await page.locator('[data-field="autocad_2016_plugin"]').getByRole("button", {name: browseLabel}).click();
    return page.evaluate(() => (window as any).__fileDialogCalls);
  };

  expect(await browseCalls("浏览…")).toEqual([
    {fileKind: "exe", description: "可执行程序"},
    {fileKind: "dll", description: "NET 程序集"},
  ]);

  // 切换到英文基线：语言包只改变描述参数，固定种类（=壳侧白名单）保持不变
  writeSettingsFile({ui_locale: "en-US", cad_max_parallel: 6}, 6);
  expect(await browseCalls("Browse…")).toEqual([
    {fileKind: "exe", description: "Executable program"},
    {fileKind: "dll", description: "NET assembly"},
  ]);

  // 还原中文基线（本用例接为串行链末尾）
  writeSettingsFile({ui_locale: "zh-CN", cad_max_parallel: 6}, 7);
});

// ---- PLAN-DM-022 任务 1：布尔状态控件统一为滑动开关 ----
// 布尔状态控件唯一视觉语言（SPEC-DM-006 §6.3 / SPEC-DM-011 §3.3）。
// 追加在文件末尾且**不落盘**：本文件串行共享同一配置文件，保存会污染后续基线。
test("布尔字段是滑动开关：role=switch + aria-checked + 可见状态文字，且仍走保存缓冲", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  const toggle = page.getByRole("switch", {name: "图纸编号追加后缀"});
  await expect(toggle).toBeVisible();
  // 初始为快照值 true；可见状态文字在开关右侧（与冻结件 g4-12 一致）
  // 注意必须限定 .bool-line：行内 .f-foot 里还有一个空的 .f-hint，直接取 .f-hint 会多元素命中
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await expect(page.locator('[data-field="enable_add_number_suffix"] .bool-line .f-hint')).toHaveText("开启");
  // 缓冲语义：点击后进入编辑缓冲（保存按钮点亮），但未保存不落库
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(page.locator('[data-field="enable_add_number_suffix"] .bool-line .f-hint')).toHaveText("关闭");
  await expect(page.getByRole("button", {name: "保存"})).toBeEnabled();
  // 放弃修改并关闭：回到快照值，不留持久化痕迹
  await page.keyboard.press("Escape");
  await page.locator('[role="dialog"][aria-modal="true"]').getByRole("button", {name: "放弃修改并关闭"}).click();
  await expect(page.locator('dialog[aria-labelledby="settings-title"]')).toBeHidden();
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  await expect(page.getByRole("switch", {name: "图纸编号追加后缀"})).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");
});

// ---- SPEC-DM-014 任务 5：编号规则分区新增"不编号图纸关键字"文本控件 ----
// 追加在文件末尾：本用例会短暂写入覆盖值，收尾以「恢复继承 + 保存」回到默认。
const KEYWORDS_INPUT = 'input[data-key="unnumbered_subset_keywords"]';
const KEYWORDS_ROW = '[data-field="unnumbered_subset_keywords"]';

test("不编号图纸关键字：文本控件渲染、规范化保存与恢复继承", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  const row = page.locator(KEYWORDS_ROW);
  await row.scrollIntoViewIfNeeded();
  await expect(row.locator(".f-label")).toHaveText("不编号图纸关键字");
  await expect(row.locator(".f-hint")).toContainText("最多 50 个");
  await expect(row).toContainText("默认"); // 未配置覆盖时来源徽章
  // 半/全角逗号混用 + 重复项：保存后由后端规范化（半角逗号、去重、保留首次原文）
  const input = page.locator(KEYWORDS_INPUT);
  await input.fill("封面， 目录,封面");
  await expect(row).toHaveClass(/dirty/);
  await page.getByRole("button", {name: "保存"}).click();
  await expect(page.getByText("已保存").first()).toBeVisible();
  // SC-13：关键字参与编号派生，保存后须追加"相关预览将按新配置重算"
  await expect(page.getByText("相关预览将按新配置重算")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  const reopened = page.locator(KEYWORDS_ROW);
  await expect(reopened.locator(KEYWORDS_INPUT)).toHaveValue("封面,目录");
  await expect(reopened).toContainText("用户覆盖");
  // 收尾：恢复继承 → 回到默认空值（标记随下次保存提交，不污染后续用例基线）
  await reopened.getByRole("button", {name: "恢复继承"}).click();
  await page.getByRole("button", {name: "保存"}).click();
  await expect(page.getByText("已保存").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  const restored = page.locator(KEYWORDS_ROW);
  await expect(restored.locator(KEYWORDS_INPUT)).toHaveValue("");
  await expect(restored).toContainText("默认");
  await page.keyboard.press("Escape");
});

test("不编号图纸关键字：数量/长度超限即时行内错误并禁用保存", async ({page}) => {
  await page.goto("/");
  await openSettingsDialog(page);
  const row = page.locator(KEYWORDS_ROW);
  const input = page.locator(KEYWORDS_INPUT);
  await row.scrollIntoViewIfNeeded();
  // 51 个不重复关键字 → 数量超限（后端上限 50）
  await input.fill(Array.from({length: 51}, (_, index) => `K${index}`).join(","));
  await expect(page.getByText("最多 50 个关键字（当前 51 个）")).toBeVisible();
  await expect(row).toHaveClass(/error/);
  await expect(page.getByRole("button", {name: "保存"})).toBeDisabled();
  // 单个关键字超过 100 字符 → 长度超限（按最长关键字报数，不报总数）
  await input.fill("测".repeat(101));
  await expect(page.getByText("单个关键字最长 100 个字符（当前 101 个）")).toBeVisible();
  await expect(page.getByRole("button", {name: "保存"})).toBeDisabled();
  // 计数口径与后端一致：去重后再判数量（50 个唯一项 + 重复项仍合法）
  await input.fill(Array.from({length: 50}, (_, index) => `K${index}`).join(",") + ",k0,K1");
  await expect(row).not.toHaveClass(/error/);
  await expect(page.getByRole("button", {name: "保存"})).toBeEnabled();
  // 未保存的编辑不落库：放弃修改并关闭
  await page.keyboard.press("Escape");
  await page.locator('[role="dialog"][aria-modal="true"]').getByRole("button", {name: "放弃修改并关闭"}).click();
  await page.getByRole("button", {name: "设置"}).click();
  await expectDialog(page);
  await expect(page.locator(KEYWORDS_ROW)).toContainText("默认");
  await expect(page.locator(KEYWORDS_INPUT)).toHaveValue("");
  await page.keyboard.press("Escape");
});

// ---------------------------------------------------------------------------
// 控件视觉基础（PLAN-DM-029 Task 8，T8-1 裁定）：量真实 getBoundingClientRect() /
// computed style —— 度量与断言的都是**渲染结果**，不是源码字面量。
// T8-1(I)：开关的三层尺寸必须分开断言：视觉轨道 44×24、滑块 18px、外层可点盒 ≥44×32。
// ---------------------------------------------------------------------------
test.describe("控件视觉基础（PLAN-DM-029 Task 8）", () => {
  const SWITCH_FIELD = '[data-field="enable_add_number_suffix"]';
  const PATH_FIELD = '[data-field="autocad_2016_console"]';
  const LEASE_FIELD = '[data-field="worker_lease_seconds"]';

  async function boxOf(locator: Locator, label: string): Promise<{w: number; h: number}> {
    const box = await locator.boundingBox();
    if (box === null) throw new Error(`${label} 不可见，无法度量`);
    return {w: Math.round(box.width), h: Math.round(box.height)};
  }

  // 令牌真值：注入探针元素解析 var()，不比 getPropertyValue 的原文
  async function tokenValue(page: Page, token: string, property: string): Promise<string> {
    return page.evaluate(
      ([name, prop]) => {
        const probe = document.createElement("span");
        probe.style.setProperty(prop, `var(${name})`);
        document.body.appendChild(probe);
        const value = getComputedStyle(probe).getPropertyValue(prop);
        probe.remove();
        return value;
      },
      [token, property] as const,
    );
  }

  test("开关：视觉轨道 44×24、滑块 18px、外层可点盒 ≥44×32，且 Space 切换与状态文案不变", async ({page}) => {
    await page.goto("/");
    await openSettingsDialog(page);
    const sw = page.locator(`${SWITCH_FIELD} .switch`);
    await expect(sw).toBeVisible();

    // 外层可点盒（Step 3 / T8-1(I)）：≥44×32 —— 断的是外层，不是轨道
    const outer = await boxOf(sw, "开关外层按钮");
    expect(outer.w, "开关外层可点宽度").toBeGreaterThanOrEqual(44);
    expect(outer.h, "开关外层可点高度必须 ≥32px（ARCH-DM-007 §10）").toBeGreaterThanOrEqual(32);

    // 视觉轨道必须仍是 44×24、滑块 18px（放大可点盒不得改变轨道观感）
    const track = sw.locator(".switch-track");
    await expect(track, "轨道必须有独立元素，才能在不改变轨道尺寸的前提下放大可点盒").toHaveCount(1);
    const trackBox = await boxOf(track, "开关轨道");
    expect(trackBox.w, "轨道宽度").toBe(44);
    expect(trackBox.h, "轨道高度").toBe(24);
    const thumb = await boxOf(sw.locator(".switch-thumb"), "开关滑块");
    expect(thumb.w, "滑块宽度").toBe(18);
    expect(thumb.h, "滑块高度").toBe(18);

    // 行为与文案不变：Space 切换 aria-checked，且状态文案随之变化
    const statusText = page.locator(`${SWITCH_FIELD} .f-hint`);
    const checkedBefore = await sw.getAttribute("aria-checked");
    const textBefore = await statusText.innerText();
    await sw.focus();
    await page.keyboard.press("Space");
    await expect(sw).toHaveAttribute("aria-checked", checkedBefore === "true" ? "false" : "true");
    expect(await statusText.innerText(), "状态文案应随 aria-checked 改变").not.toBe(textBefore);

    // 未保存：丢弃并关闭，不影响后续用例
    await page.keyboard.press("Escape");
    const discard = page.getByRole("button", {name: "放弃修改并关闭"});
    if (await discard.isVisible()) await discard.click();
  });

  test("字段行：label[for] 关联控件，hint 与 error 经 aria-describedby 关联（含 bool 行开关）", async ({page}) => {
    await page.goto("/");
    await openSettingsDialog(page);

    // ── bool 行（修复轮 Important-1）：开关的错误文字必须经 aria-describedby 落在
    // **根 button[role=switch] 本身**上（BooleanSwitch 是单根且未禁用属性透传）。
    // 开关无法产生本地校验错误，错误只能来自保存 422 的逐字段回显 → 用受限路由例外复现
    // （同文件 :299 的既定做法：仅拦截本次 PUT）。
    await page.route("**/api/settings", async route => {
      if (route.request().method() !== "PUT") return route.fallback();
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          code: "SETTINGS_VALIDATION_FAILED",
          errors: {
            enable_add_number_suffix: {
              code: "SETTING_BOOL_INVALID",
              message_key: "settings.validation.integerRange",
              params: {min: 0, max: 1},
              message: "自动添加编号后缀 取值不合法",
            },
          },
        }),
      });
    });
    const switchControl = page.locator(`${SWITCH_FIELD} [role="switch"]`);
    await expect(switchControl, "开关的根元素必须是 button[role=switch]").toBeVisible();
    // 切换开关使表单变脏（保存按钮才会启用），再保存触发 422 逐字段回显
    await switchControl.click();
    const saveButton = page.getByRole("button", {name: "保存"});
    await expect(saveButton, "切换开关后保存应可用").toBeEnabled();
    await saveButton.click();

    const switchError = page.locator(`${SWITCH_FIELD} .f-error`);
    await expect(switchError, "bool 行必须显示逐字段回显的错误").toBeVisible();
    const switchErrorId = await switchError.getAttribute("id");
    expect(switchErrorId, "错误元素必须有 id").toBeTruthy();
    // 关键断言：属性必须落在根 <button> 上，而不是某个包裹元素上
    expect(await switchControl.evaluate(el => el.tagName), "承载 aria-describedby 的必须是 button 本身").toBe("BUTTON");
    const switchDescribed = ((await switchControl.getAttribute("aria-describedby")) ?? "").split(/\s+/).filter(Boolean);
    expect(switchDescribed, "开关的错误文字必须经 aria-describedby 关联").toContain(switchErrorId);
    // 引用的 id 必须真实存在且有文案，否则是悬空引用（读屏取不到内容）
    const referenced = page.locator(`#${switchErrorId}`);
    await expect(referenced, "aria-describedby 指向的 id 必须存在").toHaveCount(1);
    await expect(referenced, "被引用的错误元素必须有文案").not.toBeEmpty();

    const input = page.locator(`${LEASE_FIELD} input[data-key="worker_lease_seconds"]`);
    const controlId = await input.getAttribute("id");
    expect(controlId, "控件必须有 id 才能被 label[for] 关联").toBeTruthy();
    await expect(page.locator(`${LEASE_FIELD} label[for="${controlId}"]`), "可见 label").toBeVisible();

    // hint 关联（仅有视觉相邻不算关联）
    const hintId = await page.locator(`${LEASE_FIELD} .f-hint`).first().getAttribute("id");
    expect(hintId, "hint 必须有 id 才能被 aria-describedby 引用").toBeTruthy();
    const describedHint = ((await input.getAttribute("aria-describedby")) ?? "").split(/\s+/).filter(Boolean);
    expect(describedHint, "hint 必须进入 aria-describedby").toContain(hintId);

    // error 关联：超范围触发行内错误后，错误元素必须进入 aria-describedby
    await input.fill("5000");
    const error = page.locator(`${LEASE_FIELD} .f-error`);
    await expect(error, "超范围应显示行内错误").toBeVisible();
    const errorId = await error.getAttribute("id");
    expect(errorId, "error 必须有 id").toBeTruthy();
    const describedError = ((await input.getAttribute("aria-describedby")) ?? "").split(/\s+/).filter(Boolean);
    expect(describedError, "error 必须进入 aria-describedby").toContain(errorId);

    // 还原（不落库）
    await input.fill("600");
  });

  test("按钮档位：浏览按钮 34px 紧凑档，链接型按钮 ≥32px，图标按钮 ≥32px", async ({page}) => {
    await page.goto("/");
    await openSettingsDialog(page);
    const browse = page.locator(`${PATH_FIELD} .browse-btn`);
    expect((await boxOf(browse, "浏览按钮")).h, "浏览按钮应保持 34px 紧凑档（T8-1(D)：档位不单方面改）").toBe(34);

    const linkBtn = page.locator(`${PATH_FIELD} .link-btn`).first();
    await expect(linkBtn).toBeAttached();
    expect((await boxOf(linkBtn, "链接型按钮")).h, "链接型按钮必须 ≥32px（T8-1(E)：28px 违反下限）").toBeGreaterThanOrEqual(32);

    const iconBtn = page.locator(".icon-btn").first();
    const iconBox = await boxOf(iconBtn, "图标按钮");
    expect(iconBox.w, "图标按钮可点宽度").toBeGreaterThanOrEqual(32);
    expect(iconBox.h, "图标按钮可点高度").toBeGreaterThanOrEqual(32);
  });

  test("路径字段：控件字体取自令牌、长路径不撑破本行", async ({page}) => {
    await page.goto("/");
    await openSettingsDialog(page);
    const input = page.locator(`${PATH_FIELD} input`);

    const fontFamily = await input.evaluate(el => getComputedStyle(el).fontFamily);
    expect(fontFamily, "控件字体族应取自 --font-ui").toBe(await tokenValue(page, "--font-ui", "font-family"));
    const fontSize = await input.evaluate(el => getComputedStyle(el).fontSize);
    expect(fontSize, "控件字号应取自 --input-font-size").toBe(await tokenValue(page, "--input-font-size", "font-size"));

    // 长路径不得撑破本行：输入框右边界不越过行右边界
    await input.fill("C:\\" + "very-long-segment\\".repeat(12) + "tool.exe");
    const geometry = await page.evaluate(sel => {
      const field = document.querySelector(sel)!;
      const line = field.querySelector(".f-line")!;
      const control = field.querySelector("input")!;
      return {
        controlRight: control.getBoundingClientRect().right,
        lineRight: line.getBoundingClientRect().right,
        lineScroll: line.scrollWidth - line.clientWidth,
      };
    }, PATH_FIELD);
    expect(geometry.controlRight, "输入框不得溢出本行").toBeLessThanOrEqual(geometry.lineRight + 1);
    expect(geometry.lineScroll, "本行不应出现横向溢出").toBeLessThanOrEqual(1);
  });

  test("焦点可见：键盘聚焦控件时轮廓可见（不是 none）", async ({page}) => {
    await page.goto("/");
    await openSettingsDialog(page);
    const input = page.locator(`${PATH_FIELD} input`);
    await input.focus();
    await expect(input).toBeFocused();
    // 用键盘走到下一个可聚焦控件，确保 :focus-visible 生效（程序化 focus 不一定匹配）
    await page.keyboard.press("Tab");
    const outline = await page.evaluate(() => {
      const element = document.activeElement as HTMLElement | null;
      if (!element) return {style: "none", width: "0px"};
      const computed = getComputedStyle(element);
      return {style: computed.outlineStyle, width: computed.outlineWidth};
    });
    expect(outline.style, "键盘聚焦必须可见轮廓").not.toBe("none");
    expect(parseFloat(outline.width), "轮廓宽度应 > 0").toBeGreaterThan(0);
  });
});
