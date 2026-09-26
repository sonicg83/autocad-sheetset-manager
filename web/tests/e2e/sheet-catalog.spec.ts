// 图纸目录页面、模板编辑与导出交互 e2e（PLAN-DM-020 Task 11 / SPEC-DM-012 §3/§7/§10/§11）。
// 覆盖三类场景：核心流程（默认模板/预览/字段插入/缺定义/缺值/空集）、模板状态
// （内置不可改/保存/另存/删除/大小写冲突/上限/不兼容/偏好/三选一保护/冲突恢复）、
// 导出状态（无壳/取消/旧预览/成功/漂移/授权失效/写失败）。全部为语义断言，
// 工作区/设置/动作路由经 fixtures/sheetCatalog.ts 模拟。
import {expect, test, type Locator, type Page} from "@playwright/test";
import {
  EXTENSION_ID, fakeUuid, installSheetCatalogFixture, openCatalogPage, planExtensionsReload, readBridgeCalls, setSaveDialog,
  type CatalogTemplate, type SheetCatalogState,
} from "./fixtures/sheetCatalog";

function userTemplate(name: string, columns: {header: string; expression: string}[]): CatalogTemplate {
  return {
    template_id: fakeUuid(),
    name,
    schema_version: 1,
    columns: columns.map(column => ({...column, column_id: fakeUuid()})),
  };
}

// 冲突/重复/上限错误响应由夹具按 controls.putSettingsMode/executeMode 返回；
// 每个用例在触发前显式布防，用例内可改写 controls 以驱动"重试成功"后半段。
async function openCatalog(page: Page, options?: Parameters<typeof installSheetCatalogFixture>[1]): Promise<SheetCatalogState> {
  const {state} = await installSheetCatalogFixture(page, options);
  await openCatalogPage(page, {noShell: options?.noShell});
  return state;
}

async function expectPreviewRows(page: Page, count: number): Promise<void> {
  await expect(page.getByRole("region", {name: "预览"}).getByRole("row")).toHaveCount(count + 1); // 表头一行
}

test.describe("核心流程（SPEC §3.1）", () => {
  test("默认内置模板三列真实预览：前 20 行 + 总图纸数", async ({page}) => {
    await openCatalog(page);
    const preview = page.getByRole("region", {name: "预览"});
    await expect(preview.getByRole("columnheader")).toHaveText(["图号", "图名", "文件名"]);
    await expectPreviewRows(page, 20);
    await expect(preview.getByText("共 25 张图纸")).toBeVisible();
    await expect(preview.getByText("显示前 20 行")).toBeVisible();
    await expect(preview.getByRole("cell", {name: "001", exact: true})).toBeVisible();
  });

  test("字段浏览器分三组：固有字段、图纸集自定义属性、图纸自定义属性", async ({page}) => {
    await openCatalog(page);
    const browser = page.getByRole("region", {name: "字段浏览器"});
    await expect(browser.getByRole("heading", {name: "图纸固有字段"})).toBeVisible();
    await expect(browser.getByRole("heading", {name: "图纸集自定义属性"})).toBeVisible();
    await expect(browser.getByRole("heading", {name: "图纸自定义属性"})).toBeVisible();
    // 字段条目为冻结 Demo 的双行形态（第一行规范引用、第二行用户名称），可访问名包含两者
    await expect(browser.getByRole("button", {name: /sheet\.number/})).toBeVisible();
    await expect(browser.getByRole("button", {name: /sheetset\.设计院/})).toBeVisible();
    await expect(browser.getByRole("button", {name: /sheet\.专业代码/})).toBeVisible();
  });

  test("特殊属性在当前光标位置插入 JSON 方括号语法，普通字段插入点号语法", async ({page}) => {
    await openCatalog(page);
    const expression = page.getByRole("region", {name: "输出列编辑器"}).getByLabel("表达式 1");
    await expression.fill("RQ-{sheet.title}");
    await expression.evaluate(element => {
      (element as HTMLTextAreaElement).setSelectionRange(3, 3);
      (element as HTMLTextAreaElement).blur();
    });
    const browser = page.getByRole("region", {name: "字段浏览器"});
    await browser.getByRole("button", {name: /sheet\.number/}).click();
    await expect(expression).toHaveValue("RQ-{sheet.number}{sheet.title}");
    // 特殊名称（含空格）必须插入方括号 JSON 字符串形式：先添加一个空列再插入
    await page.getByRole("button", {name: "添加输出列"}).click();
    await page.getByLabel("表达式 4").click();
    await browser.getByRole("button", {name: /sheetset\["项目 名称"\]/}).click();
    await expect(page.getByLabel("表达式 4")).toHaveValue('{sheetset["项目 名称"]}');
  });

  test("组合表达式生成 RQ-001 形态的求值结果", async ({page}) => {
    await openCatalog(page);
    const expression = page.getByLabel("表达式 1");
    await expression.fill("RQ-");
    await page.getByRole("region", {name: "字段浏览器"}).getByRole("button", {name: /sheet\.number/}).click();
    await expect(expression).toHaveValue("RQ-{sheet.number}");
    const preview = page.getByRole("region", {name: "预览"});
    await expect(preview.getByRole("cell", {name: "RQ-001", exact: true})).toBeVisible();
  });

  test("缺定义可见且阻断导出：显示缺少的作用域与属性名", async ({page}) => {
    await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheetset.不存在属性}");
    const summary = page.getByRole("region", {name: "兼容性摘要"});
    await expect(summary.getByText("[sheetset] 不存在属性")).toBeVisible();
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeDisabled();
  });

  test("缺值带数量警告但允许导出", async ({page}) => {
    await openCatalog(page, {sheetPropertyValueOverrides: [{name: "专业代码", fromIndex: 20}]});
    await page.getByLabel("表达式 1").fill("{sheet.专业代码}-{sheet.number}");
    const summary = page.getByRole("region", {name: "兼容性摘要"});
    await expect(summary.getByText("[sheet] 专业代码（涉及 5 张图纸）")).toBeVisible();
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeEnabled();
  });

  test("空图纸集返回有效预览且可导出", async ({page}) => {
    await openCatalog(page, {empty: true});
    const preview = page.getByRole("region", {name: "预览"});
    await expect(preview.getByText("共 0 张图纸")).toBeVisible();
    await expect(preview.getByText("当前图纸集没有图纸")).toBeVisible();
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeEnabled();
  });
});

// PLAN-DM-023 Task 2（追踪矩阵 V4/V6）：字段本地搜索、常显引用语法与可用态头部密度。
// 搜索只过滤当前已取得的字段目录（页面本地瞬时状态，不进控制器、不发请求）；
// 可用态不再保留整行 `.catalog-status` 冗余卡，但版本/生命周期与启停指引仍为可见正文。
test.describe("字段搜索与可用态头部（PLAN-DM-023 Task 2）", () => {
  test("字段搜索：按中文名、规范引用与作用域过滤，且无结果显示可见空态", async ({page}) => {
    await openCatalog(page);
    const browser = page.getByRole("region", {name: "字段浏览器"});
    const search = page.getByLabel("搜索可用字段");
    await expect(search).toBeVisible();
    // 按中文名搜索：只留图名字段
    await search.fill("图名");
    await expect(browser.getByRole("button", {name: /sheet\.title/})).toBeVisible();
    await expect(browser.getByRole("button", {name: /sheet\.number/})).toHaveCount(0);
    // 按规范引用搜索：“设计院”是图纸集自定义属性
    await search.fill("设计院");
    await expect(browser.getByRole("button", {name: /sheetset\.设计院/})).toBeVisible();
    await expect(browser.getByRole("button", {name: /sheet\.title/})).toHaveCount(0);
    // 按作用域搜索：只留图纸固有字段
    await search.fill("图纸固有字段");
    await expect(browser.getByRole("button", {name: /sheet\.number/})).toBeVisible();
    await expect(browser.getByRole("button", {name: /sheetset\.设计院/})).toHaveCount(0);
    // 无结果显示可见空态（不能只剩空白）
    await search.fill("不存在的字段名称");
    await expect(browser.getByText("没有匹配的字段")).toBeVisible();
    await expect(browser.getByRole("button", {name: /sheet\.number/})).toHaveCount(0);
    // 清空后恢复完整目录
    await search.fill("");
    await expect(browser.getByRole("button", {name: /sheet\.number/})).toBeVisible();
    await expect(browser.getByRole("button", {name: /sheetset\.设计院/})).toBeVisible();
    // 搜索不改变插入语义
    await page.getByLabel("表达式 1").fill("");
    await browser.getByRole("button", {name: /sheet\.number/}).click();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}");
  });

  test("可用态头部：无独立状态大卡、版本可见且模板栏状态文字完整", async ({page}) => {
    const template = userTemplate("市政标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    // V6：可用态不再有整行状态卡，也不再有与模板栏重复的引导文案
    await expect(page.locator(".catalog-status")).toHaveCount(0);
    await expect(page.getByText("选择模板并配置输出列后即可导出当前图纸集的图纸目录。")).toHaveCount(0);
    // 版本与生命周期仍是可见正文（不是只有 title/aria-label）
    const head = page.locator(".catalog-head");
    await expect(head).toContainText("v0.1.0");
    await expect(head).toContainText("可用");
    // 启停入口唯一在设置中心：指引必须保持可见
    await expect(page.getByText("扩展的启用与停用请在设置中心操作。")).toBeVisible();
    // 模板栏恢复“内置模板/已保存模板”和“已保存/有未保存修改”两类状态文字
    const bar = page.getByRole("region", {name: "模板栏"});
    await expect(bar.getByText("已保存模板")).toBeVisible();
    await expect(bar.getByText("已保存", {exact: true})).toBeVisible();
    await page.getByLabel("选择模板").selectOption("");
    await expect(bar.getByText("内置模板")).toBeVisible();
    await expect(bar.getByText("已保存", {exact: true})).toBeVisible();
    await page.getByLabel("输出列名 1").fill("图号（改）");
    await expect(bar.getByText("有未保存修改")).toBeVisible();
    await expect(bar.getByText("已保存", {exact: true})).toHaveCount(0);
  });
});

// PLAN-DM-034 Task 6（SPEC-DM-015 §4.2/§5.2）：模板栏状态从 muted 正文升级为中性/警示
// 两种徽标（琥珀语义令牌 + 可见文字，role="status" 温和播报），保存修改按钮 clean 态从
// 原生 disabled 改为可聚焦语义禁用（UiButton.ariaDisabled）；read-only、saving 等强阻断
// 继续原生禁用。SPEC-DM-015 §4.2 裁决：琥珀只落在模板栏徽标，列输入框不得统一铺 dirty 底色。
test.describe("模板栏模板级状态（PLAN-DM-034 Task 6）", () => {
  test("clean：中性「已保存」徽标与语义禁用保存按钮，强激活不产生 PUT；dirty：警示徽标且保存可执行；改回快照恢复 clean", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    const bar = page.getByRole("region", {name: "模板栏"});
    const stateBadge = bar.locator(".template-state");
    const save = page.getByRole("button", {name: "保存修改"});

    // clean：中性「已保存」徽标；保存按钮 aria-disabled="true" 且无原生 disabled（可聚焦语义禁用）
    await expect(stateBadge).toHaveText("已保存");
    await expect(stateBadge).toHaveAttribute("role", "status");
    await expect(stateBadge).not.toHaveClass(/dirty/);
    await expect(save).toHaveAttribute("aria-disabled", "true");
    await expect(save).not.toHaveAttribute("disabled");
    // Playwright 1.55 把 aria-disabled 视为不可用：守卫断言必须用强制点击/键盘派发 + 请求计数
    await save.click({force: true});
    await save.focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Space");
    expect(state.putExpectedRevisions).toEqual([]);

    // 修改列名：模板栏出现警示徽标（可见文字 + dirty class），保存按钮转为可执行
    await page.getByLabel("输出列名 1").fill("图纸编号A");
    await expect(stateBadge).toHaveText("有未保存修改");
    await expect(stateBadge).toHaveClass(/dirty/);
    await expect(save).toBeEnabled();
    await expect(save).not.toHaveAttribute("aria-disabled");

    // 改回模板快照：恢复 clean 中性徽标，保存按钮重新语义禁用（且仍无原生 disabled）
    await page.getByLabel("输出列名 1").fill("图号");
    await expect(stateBadge).toHaveText("已保存");
    await expect(stateBadge).not.toHaveClass(/dirty/);
    await expect(save).toHaveAttribute("aria-disabled", "true");
    await expect(save).not.toHaveAttribute("disabled");
    expect(state.putExpectedRevisions).toEqual([]);
  });

  // “表达式错误时保存不可执行”的实现口径：前端不新增控制器并不存在的 invalid 派生状态
  //（保存按钮在错误态仍由模板 dirty 单独驱动），保存被现有 Provider 级 409 阻断——后端
  // validate_template 拒绝重名列（SHEET_CATALOG_COLUMN_DUPLICATE），而未定义字段引用
  // “不要求兼容当前字段目录”、不阻断保存。夹具的 duplicate 模式是这一现有阻断的模拟。
  test("列错误：保留「有未保存修改」徽标、错误就地呈现，保存被 Provider 拒绝不落盘", async ({page}) => {
    const template = userTemplate("标准目录", [
      {header: "图号", expression: "{sheet.number}"},
      {header: "图名", expression: "{sheet.title}"},
    ]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    const bar = page.getByRole("region", {name: "模板栏"});
    const stateBadge = bar.locator(".template-state");
    const editor = page.getByRole("region", {name: "输出列编辑器"});
    const save = page.getByRole("button", {name: "保存修改"});

    // 表达式错误（未定义字段）：徽标保留警示态，错误正文就地在出错列行内呈现
    await page.getByLabel("表达式 2").fill("{sheet.不存在属性}");
    await expect(stateBadge).toHaveText("有未保存修改");
    await expect(stateBadge).toHaveClass(/dirty/);
    const badRow = editor.locator(".columns .column-row").nth(1);
    await expect(badRow.locator(".status-cell")).toHaveText("需修正");
    await expect(badRow.getByText("[sheet] 不存在属性")).toBeVisible();
    // 不新增 invalid 派生：错误不改变保存按钮的模板级 dirty 语义（仍可执行）
    await expect(save).toBeEnabled();

    // 保存不可执行（现有阻断）：重名列触发 Provider 409，错误可见、修改保留、服务端值不变
    await page.getByLabel("表达式 2").fill("{sheet.title}");
    await page.getByLabel("输出列名 2").fill("图号");
    await expect(badRow.getByText("名称重复：图号")).toBeVisible();
    state.controls.putSettingsMode = "duplicate";
    await save.click();
    await expect(page.getByRole("alert").filter({hasText: "名称重复：标准目录"})).toBeVisible();
    await expect(stateBadge).toHaveText("有未保存修改");
    expect(state.settingsValue.user_templates[0]!.columns[1]!.header).toBe("图名");
  });

  // SPEC-DM-015 §4.2 裁决回归守卫（本任务实现不触碰 ColumnEditor，本用例从起即绿）：
  // 脏态下列输入框的背景/边框与 clean 态逐值相同——琥珀只出现在模板栏徽标，不铺到单元格。
  test("列输入框不随模板 dirty 变色：琥珀只出现在模板栏徽标", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    const header = page.getByLabel("输出列名 1");
    const expression = page.getByLabel("表达式 1");
    const styleOf = (locator: Locator, property: string) => locator.evaluate((element, prop) => getComputedStyle(element).getPropertyValue(prop), property);
    // 断言有效性：warning 底色令牌与输入框 clean 底色必须确实不同（防止断言恒真）
    const warningBg = await page.evaluate(() => {
      const probe = document.createElement("span");
      probe.style.backgroundColor = "var(--color-warning-bg)";
      document.body.appendChild(probe);
      const value = getComputedStyle(probe).backgroundColor;
      probe.remove();
      return value;
    });
    const cleanHeaderBg = await styleOf(header, "background-color");
    const cleanExpressionBg = await styleOf(expression, "background-color");
    expect(cleanHeaderBg, "warning-bg 与输入框 clean 底色不同（断言有效前提）").not.toBe(warningBg);

    await page.getByLabel("输出列名 1").fill("图纸编号A");
    await page.getByLabel("表达式 1").fill("{sheet.number}#");
    await expect(page.getByText("有未保存修改")).toBeVisible();
    await expect(header).not.toHaveClass(/dirty/);
    expect(await styleOf(header, "background-color")).toBe(cleanHeaderBg);
    expect(await styleOf(expression, "background-color")).toBe(cleanExpressionBg);
  });
});

// PLAN-DM-023 Task 3（追踪矩阵 V1/V5/V8/A1）：输出列恢复为冻结 Demo 的紧凑表格式——
// `.columns-head` 与 `.column-row` 共用同一组 grid 轨道，每行同时显示顺序、列名、
// 表达式、状态和操作；列区自身限高滚动，列数增长不得撑高页面。
// A1 是唯一预先接受差异：操作列继续使用 ↑ / ↓ / ✕ 图标按钮与现有完整 aria-label，
// 因此该轨道比冻结 Demo 的 188px 更窄。
test.describe("表格式输出列（PLAN-DM-023 Task 3）", () => {
  // 与 PLAN-DM-023 Task 1 同口径的几何读取（表头 + 每个数据行的五列轨道）
  async function readColumnGrid(page: Page): Promise<{left: number; right: number}[][]> {
    return page.evaluate(() => {
      const rect = (element: Element) => {
        const box = element.getBoundingClientRect();
        return {left: box.left, right: box.right};
      };
      return [
        Array.from(document.querySelectorAll(".columns-head > *")).map(rect),
        ...Array.from(document.querySelectorAll(".columns .column-row")).map(row => Array.from(row.children).map(rect)),
      ];
    });
  }

  test("表格式输出列：五列表头、列边界对齐、状态与列计数", async ({page}) => {
    const template = userTemplate("市政标准目录", [
      {header: "图纸编号", expression: "{sheet.专业代码}-{sheet.number}"},
      {header: "图名", expression: "{sheet.title}"},
      {header: "设计院", expression: "{sheetset.设计院}"},
      {header: "专业代码", expression: "{sheet.专业代码}"},
    ]);
    await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    const editor = page.getByRole("region", {name: "输出列编辑器"});
    await expect(editor.locator(".columns-head > *")).toHaveText(["顺序", "列名", "表达式", "状态", "操作"]);
    await expect(editor.getByText("4 / 50 列")).toBeVisible();
    // 四列均无阻断问题 → 状态列逐行显示“有效”
    await expect(editor.locator(".columns .column-row .status-cell")).toHaveText(["有效", "有效", "有效", "有效"]);
    // 表头与每个数据行共用同一组列边界（误差 ≤ 1px）
    const grid = await readColumnGrid(page);
    expect(grid.length, "表头 + 四个数据行").toBe(5);
    for (const row of grid.slice(1)) {
      expect(row).toHaveLength(5);
      for (let index = 0; index < 5; index++) {
        expect(Math.abs(row[index]!.left - grid[0]![index]!.left), `第 ${index + 1} 列左边界对齐`).toBeLessThanOrEqual(1);
        expect(Math.abs(row[index]!.right - grid[0]![index]!.right), `第 ${index + 1} 列右边界对齐`).toBeLessThanOrEqual(1);
      }
    }
    // 未知字段：该行变“需修正”，错误正文就在表达式单元格内
    await page.getByLabel("表达式 1").fill("{sheet.不存在属性}");
    const firstRow = editor.locator(".columns .column-row").first();
    await expect(firstRow.locator(".status-cell")).toHaveText("需修正");
    await expect(firstRow.getByText("[sheet] 不存在属性")).toBeVisible();
    await expect(editor.locator(".columns .column-row").nth(1).locator(".status-cell")).toHaveText("有效");
    await expect(editor.getByText("4 / 50 列")).toBeVisible();
  });

  test("图标列操作：无可见文字按钮，aria-label、禁用边界与顺序变更保持", async ({page}) => {
    await openCatalog(page);
    const editor = page.getByRole("region", {name: "输出列编辑器"});
    // A1：可见内容仍是图标，不是“上移/下移/删除”文字按钮
    await expect(editor.getByText("上移", {exact: true})).toHaveCount(0);
    await expect(editor.getByText("下移", {exact: true})).toHaveCount(0);
    await expect(editor.getByText("删除列", {exact: true})).toHaveCount(0);
    const up = editor.getByRole("button", {name: "上移 2"});
    await expect(up).toHaveText("↑");
    await expect(editor.getByRole("button", {name: "上移 1"})).toBeDisabled();
    await expect(editor.getByRole("button", {name: "下移 3"})).toBeDisabled();
    const headers = editor.getByLabel(/^输出列名 \d+$/);
    await expect(headers).toHaveCount(3);
    await expect(headers.nth(0)).toHaveValue("图号");
    await expect(headers.nth(1)).toHaveValue("图名");
    await up.click();
    await expect(editor.getByLabel("输出列名 1")).toHaveValue("图名");
    await expect(editor.getByLabel("输出列名 2")).toHaveValue("图号");
    // 删除仍走现有规则（直接移除该列，无额外确认）
    await editor.getByRole("button", {name: "删除列 1"}).click();
    await expect(headers).toHaveCount(2);
    await expect(editor.getByLabel("输出列名 1")).toHaveValue("图号");
  });
});

// PLAN-DM-023 Task 4（追踪矩阵 V2/V3）：兼容性摘要嵌回输出列上下文、刷新与导出入
// 预览上下文（刷新在头部、导出与反馈在底部）。组件仍各自独立存在且保留 aria-label
// region，只由业务上下文组件组合；诊断计算仍完全来自服务端。
test.describe("兼容性与预览操作坞（PLAN-DM-023 Task 4）", () => {
  test("兼容性归属：摘要嵌入输出列卡，警告可导出、错误禁用导出且正文不回退", async ({page}) => {
    await openCatalog(page, {sheetPropertyValueOverrides: [{name: "专业代码", fromIndex: 20}]});
    const editor = page.getByRole("region", {name: "输出列编辑器"});
    await page.getByLabel("表达式 1").fill("{sheet.专业代码}-{sheet.number}");
    const summary = editor.getByRole("region", {name: "兼容性摘要"});
    await expect(summary).toHaveCount(1);
    await expect(summary).toContainText("[sheet] 专业代码（涉及 5 张图纸）");
    await expect(editor.locator(".compat-badge")).toHaveText("可以导出，有 1 项提示");
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeEnabled();
    // 未知字段：徽标转为“不能导出”，详细正文与禁用状态不回退
    await page.getByLabel("表达式 1").fill("{sheet.不存在属性}");
    await expect(summary).toContainText("[sheet] 不存在属性");
    await expect(editor.locator(".compat-badge")).toHaveText("不能导出");
    await expect(summary.locator(".compat-title")).toHaveText("阻断问题");
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeDisabled();
    // 该列同时转“需修正”，状态与摘要来自同一处判定
    await expect(editor.locator(".columns .column-row").first().locator(".status-cell")).toHaveText("需修正");
  });

  test("预览操作坞：刷新在预览头部，导出与成功反馈在预览底部", async ({page}) => {
    await openCatalog(page);
    const preview = page.getByRole("region", {name: "预览"});
    await expect(preview.getByRole("button", {name: "刷新预览"})).toHaveCount(1);
    const actions = preview.getByRole("region", {name: "导出操作"});
    await expect(actions).toHaveCount(1);
    // 刷新已上提到预览头部，不再和导出挤在同一排
    await expect(actions.getByRole("button", {name: "刷新预览"})).toHaveCount(0);
    await expect(actions.getByRole("button", {name: "导出 XLSX"})).toHaveCount(1);
    // 一致性反馈与导出按钮同处预览底部
    await expect(actions.getByText("预览与当前模板草稿、工作区修订一致")).toBeVisible();
    // 成功反馈留在预览卡内
    await preview.getByRole("button", {name: "导出 XLSX"}).click();
    await expect(preview.getByText("图纸目录已保存到")).toBeVisible();
    await expect(preview.getByRole("button", {name: "打开所在文件夹"})).toBeVisible();
  });
});

test.describe("模板状态（SPEC §3.2/§6）", () => {
  test("内置模板编辑即变为未命名草稿，只能另存不能原位保存", async ({page}) => {
    await openCatalog(page);
    await expect(page.getByLabel("选择模板")).toHaveValue("");
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await expect(page.getByText("有未保存修改")).toBeVisible();
    await expect(page.getByText("未命名草稿")).toBeVisible();
    await expect(page.getByRole("button", {name: "保存修改"})).toHaveCount(0);
    await expect(page.getByRole("button", {name: "另存为"})).toBeEnabled();
  });

  test("用户模板可原位保存：PUT 设置携带更新后的模板且脏标记消失", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    await page.getByLabel("输出列名 1").fill("图纸编号");
    await page.getByRole("button", {name: "保存修改"}).click();
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    const put = state.settingsValue.user_templates[0];
    expect(put.name).toBe("标准目录");
    expect(put.columns[0].header).toBe("图纸编号");
  });

  // PLAN-DM-025 Task 2 修复：设置/偏好 PUT 提交的 schema_version 必须与后端 Manifest
  // 的 settings_schema 一致（不一致即 422）；本断言在常量回退到 1 时立即失败。
  test("设置与偏好 PUT 携带与 Manifest 一致的 settings schema_version", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    // 不带预置偏好：初始选中内置模板，切到已保存模板才写工作区偏好
    const state = await openCatalog(page, {userTemplates: [template]});
    await page.getByLabel("选择模板").selectOption({label: "标准目录"});
    await expect.poll(() => state.preferencePutBodies.length).toBe(1);
    await page.getByLabel("输出列名 1").fill("图纸编号");
    await page.getByRole("button", {name: "保存修改"}).click();
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    expect(state.settingsPutBodies).toHaveLength(1);
    expect(state.settingsPutBodies[0].schema_version).toBe(2);
    expect(state.preferencePutBodies[0].schema_version).toBe(2);
  });

  test("另存为新模板：输入名称保存后进入模板列表并记录工作区偏好", async ({page}) => {
    const state = await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await page.getByRole("button", {name: "另存为"}).click();
    const dialog = page.getByRole("dialog", {name: "另存为模板"});
    await dialog.getByLabel("模板名称").fill("标准目录");
    await dialog.getByRole("button", {name: "保存", exact: true}).click();
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    const saved = state.settingsValue.user_templates.at(-1)!;
    expect(saved.name).toBe("标准目录");
    expect(saved.columns[0].expression).toBe("{sheet.number}号");
    expect(state.preferencePuts).toEqual([{template_id: saved.template_id}]);
  });

  test("删除当前模板需确认：成功后回到内置默认模板，历史 Artifact 查询仍存在", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    // 先成功导出一次，留下历史 Artifact
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
    // 删除当前模板：先确认再执行
    await page.getByRole("button", {name: "删除模板"}).click();
    const dialog = page.locator('[role="dialog"][aria-modal="true"]');
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", {name: "删除", exact: true}).click();
    await expect(page.getByLabel("选择模板")).toHaveValue("");
    expect(state.settingsValue.user_templates).toEqual([]);
    // 历史 Artifact 不随模板删除消失
    const artifact = await page.evaluate(async () => {
      const response = await fetch("/api/artifacts/artifact-e2e");
      return {status: response.status, body: await response.json()};
    });
    expect(artifact.status).toBe(200);
    expect((artifact.body as Record<string, unknown>).availability).toBe("AVAILABLE");
  });

  test("模板名大小写不敏感冲突：错误可见、本地编辑保留、模板列表不变", async ({page}) => {
    const template = userTemplate("Catalog", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template]});
    state.controls.putSettingsMode = "duplicate";
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await page.getByRole("button", {name: "另存为"}).click();
    const dialog = page.getByRole("dialog", {name: "另存为模板"});
    await dialog.getByLabel("模板名称").fill("catalog");
    await dialog.getByRole("button", {name: "保存", exact: true}).click();
    await expect(page.getByText("名称重复：catalog")).toBeVisible();
    // 本地编辑保留：草稿表达式与另存为对话框输入不被清空
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}号");
    expect(state.settingsValue.user_templates).toHaveLength(1);
  });

  test("用户模板 100 上限：显示具体限制且不截断数据", async ({page}) => {
    const state = await openCatalog(page);
    state.controls.putSettingsMode = "limit";
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await page.getByRole("button", {name: "另存为"}).click();
    const dialog = page.getByRole("dialog", {name: "另存为模板"});
    await dialog.getByLabel("模板名称").fill("模板 101");
    await dialog.getByRole("button", {name: "保存", exact: true}).click();
    await expect(page.getByText("超出模板限制 user_templates：101/100")).toBeVisible();
    expect(state.settingsValue.user_templates).toHaveLength(0);
  });

  test("跨图纸集不兼容模板保留且突出缺少的 sheetset/sheet 字段", async ({page}) => {
    const template = userTemplate("跨集模板", [
      {header: "地区", expression: "{sheetset.地区}"},
      {header: "审定人", expression: "{sheet.审定人}"},
    ]);
    await openCatalog(page, {userTemplates: [template]});
    await page.getByLabel("选择模板").selectOption({label: "跨集模板"});
    const summary = page.getByRole("region", {name: "兼容性摘要"});
    await expect(summary.getByText("[sheetset] 地区")).toBeVisible();
    await expect(summary.getByText("[sheet] 审定人")).toBeVisible();
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeDisabled();
    // 模板保留可编辑：表达式内容仍在编辑器中
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheetset.地区}");
  });

  test("工作区偏好只记已保存模板：未命名草稿与内置模板不写入偏好", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    // 初始由偏好选中已保存模板
    await expect(page.getByLabel("选择模板")).toHaveValue(template.template_id);
    // 切到内置模板：不写偏好
    await page.getByLabel("选择模板").selectOption({label: "默认图纸目录（内置）"});
    expect(state.preferencePuts).toEqual([]);
    // 编辑成未命名草稿：同样不写偏好
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await expect(page.getByText("有未保存修改")).toBeVisible();
    expect(state.preferencePuts).toEqual([]);
    // 带未保存草稿切回已保存模板：先三选一（放弃修改），随后只记录已保存模板
    await page.getByLabel("选择模板").selectOption({label: "标准目录"});
    const dialog = page.getByRole("dialog", {name: "未保存的模板修改"});
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", {name: "放弃修改"}).click();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}");
    expect(state.preferencePuts).toEqual([{template_id: template.template_id}]);
  });

  test("有未保存草稿时切换页签出现三选一保护，留在此处不离开", async ({page}) => {
    await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    // 核心首标签（图纸）的可访问名带序号前缀，按位置定位
    await page.getByRole("tablist").getByRole("tab").first().click();
    const dialog = page.getByRole("dialog", {name: "未保存的模板修改"});
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", {name: "留在此处"}).click();
    await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}号");
  });

  test("三选一保护放弃修改后允许切换，返回时草稿已复位", async ({page}) => {
    await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await page.getByRole("tablist").getByRole("tab").first().click();
    const dialog = page.getByRole("dialog", {name: "未保存的模板修改"});
    await dialog.getByRole("button", {name: "放弃修改"}).click();
    await expect(page.getByRole("button", {name: "预览变更"})).toBeVisible();
    await page.getByRole("tab", {name: "图纸目录"}).click();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}");
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
  });

  test("关闭工作区同样经过三选一保护", async ({page}) => {
    await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await page.getByRole("button", {name: "关闭工作区"}).click();
    const dialog = page.getByRole("dialog", {name: "未保存的模板修改"});
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", {name: "留在此处"}).click();
    await expect(page.getByRole("button", {name: "关闭工作区"})).toBeVisible();
    await page.getByRole("button", {name: "关闭工作区"}).click();
    await dialog.getByRole("button", {name: "放弃修改"}).click();
    await expect(page.getByRole("button", {name: "选择 DST 文件"})).toBeVisible();
  });

  // 启停入口唯一在设置中心（扩展页面不再提供停用：否则停用会移除该页入口，开关单向）。
  // SPEC-DM-011 修订「启停交互改进」：目录页三选一已改为原生 <dialog showModal>，会自行进入 top layer 叠在
  // 设置窗口之上，因此停用不再需要先关闭设置窗口；本用例钉住“设置窗口仍开着时闸门
  // 可见可点”这一回归点（旧实现下内联遮罩会被 top layer 的设置窗口 inert 吞掉）。
  test("停用扩展（离开页面）先经过三选一保护，且设置窗口不关闭", async ({page}) => {
    const state = await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await page.getByRole("button", {name: "设置"}).click();
    await page.getByRole("tab", {name: "扩展"}).click();
    await page.getByRole("switch", {name: "停用 图纸目录"}).click();
    const dialog = page.getByRole("dialog", {name: "未保存的模板修改"});
    await expect(dialog).toBeVisible();
    // 设置窗口仍在（未被停用关闭）：闸门必须叠在它之上才能被点到
    await expect(page.locator('dialog[aria-labelledby="settings-title"]')).toBeVisible();
    expect(state.extensionPatchBodies).toHaveLength(0);
    await dialog.getByRole("button", {name: "放弃修改"}).click();
    await expect(page.getByRole("tab", {name: "图纸目录"})).toHaveCount(0);
    expect(state.extensionPatchBodies).toEqual([{enabled: false}]);
  });

  test("保存冲突保留本地编辑，可按新修订重试成功", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    state.controls.putSettingsMode = "conflict";
    await page.getByLabel("输出列名 1").fill("图纸编号");
    await page.getByRole("button", {name: "保存修改"}).click();
    const conflict = page.getByRole("alert").filter({hasText: "模板已被其他保存更新"});
    await expect(conflict).toBeVisible();
    // 本地编辑保留；服务端已被其他保存推进（r3→r4，并出现其他窗口的模板）
    await expect(page.getByLabel("输出列名 1")).toHaveValue("图纸编号");
    expect(state.revision).toBe(4);
    expect(state.settingsValue.user_templates.map(item => item.name)).toContain("其他窗口的模板 4");
    // 按新修订重试：刷新服务端修订（r4）后携带新 expected_revision 原样重放
    state.controls.putSettingsMode = "ok";
    await conflict.getByRole("button", {name: "按新修订重试"}).click();
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    expect(state.putExpectedRevisions).toEqual([3, 4]);
    expect(state.settingsValue.user_templates).toHaveLength(1);
    expect(state.settingsValue.user_templates[0].columns[0].header).toBe("图纸编号");
  });

  test("保存冲突后可改走另存为新模板，另存为携带刷新后的服务端修订", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    state.controls.putSettingsMode = "conflict";
    await page.getByLabel("输出列名 1").fill("图纸编号");
    await page.getByRole("button", {name: "保存修改"}).click();
    const conflict = page.getByRole("alert").filter({hasText: "模板已被其他保存更新"});
    await expect(conflict).toBeVisible();
    // 冲突后另存为：先刷新服务端修订（r4）再 PUT，携带过期 expected_revision 会再次 409
    state.controls.putSettingsMode = "ok";
    await conflict.getByRole("button", {name: "另存为新模板"}).click();
    const dialog = page.getByRole("dialog", {name: "另存为模板"});
    await dialog.getByLabel("模板名称").fill("标准目录副本");
    await dialog.getByRole("button", {name: "保存", exact: true}).click();
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    expect(state.putExpectedRevisions).toEqual([3, 4]);
    expect(state.settingsValue.user_templates.map(item => item.name)).toEqual(["标准目录", "其他窗口的模板 4", "标准目录副本"]);
  });

  test("连续冲突下另存为每次携带最新服务端修订并最终成功", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    state.controls.putSettingsMode = "conflict";
    await page.getByLabel("输出列名 1").fill("图纸编号");
    await page.getByRole("button", {name: "保存修改"}).click();
    const conflict = page.getByRole("alert").filter({hasText: "模板已被其他保存更新"});
    await expect(conflict).toBeVisible();
    // 第一次另存为：携带刷新后的 r4 仍冲突（并发持续，r4→r5）
    await conflict.getByRole("button", {name: "另存为新模板"}).click();
    const dialog = page.getByRole("dialog", {name: "另存为模板"});
    await dialog.getByLabel("模板名称").fill("标准目录副本");
    await dialog.getByRole("button", {name: "保存", exact: true}).click();
    await expect.poll(() => state.revision).toBe(5);
    expect(state.putExpectedRevisions).toEqual([3, 4]);
    // 并发停止后用同一对话框再次保存：携带刷新后的 r5 成功，不陷入死循环
    state.controls.putSettingsMode = "ok";
    await dialog.getByRole("button", {name: "保存", exact: true}).click();
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    expect(state.putExpectedRevisions).toEqual([3, 4, 5]);
    expect(state.settingsValue.user_templates.map(item => item.name)).toContain("标准目录副本");
  });
});

test.describe("导出状态（SPEC §10/§11）", () => {
  test("无桌面壳时导出禁用并显示可见说明", async ({page}) => {
    await openCatalog(page, {noShell: true});
    const exportButton = page.getByRole("button", {name: "导出 XLSX"});
    await expect(exportButton).toBeDisabled();
    await expect(page.getByText("桌面壳不可用", {exact: false})).toBeVisible();
  });

  test("用户取消另存为：草稿与预览保持不变且不发出执行请求", async ({page}) => {
    const state = await openCatalog(page, {saveDialog: "cancel"});
    await page.getByLabel("表达式 1").fill("{sheet.title}-图");
    await expect(page.getByRole("region", {name: "预览"}).getByRole("cell", {name: "图纸 001-图", exact: true})).toBeVisible();
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    expect((await readBridgeCalls(page)).saveRequests).toHaveLength(1);
    expect(state.executeRequests).toHaveLength(0);
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.title}-图");
    await expectPreviewRows(page, 20);
  });

  test("草稿修改后旧预览禁止导出，预览刷新后恢复", async ({page}) => {
    await openCatalog(page);
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeEnabled();
    await page.getByLabel("表达式 1").fill("{sheet.title}+");
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeDisabled();
    await expect(page.getByText("草稿已修改，预览更新后才能导出")).toBeVisible();
    const preview = page.getByRole("region", {name: "预览"});
    await expect(preview.getByRole("cell", {name: "图纸 001+", exact: true})).toBeVisible();
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeEnabled();
  });

  test("导出成功显示最终路径与打开所在文件夹，不显示 Artifact/修订/哈希", async ({page}) => {
    const state = await openCatalog(page);
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
    await expect(page.getByText("C:\\导出\\测试图纸集-图纸目录.xlsx")).toBeVisible();
    await expect(page.getByRole("button", {name: "打开所在文件夹"})).toBeVisible();
    // 不显示技术字段：artifact/哈希/修订标识不出现在页面正文
    await expect(page.getByText("artifact-e2e")).toHaveCount(0);
    await expect(page.getByText("revision-1")).toHaveCount(0);
    const body = await page.textContent("body");
    expect(body).not.toContain("sha256");
    // 执行请求契约：重复提交模板快照 + 预览摘要 + 设置修订 + 保存授权
    const execute = state.executeRequests[0];
    expect(execute.workspace_id).toBe("workspace-1");
    expect(execute.base_revision_id).toBe("revision-1");
    expect(execute.preview_digest).toBe(state.lastDigest);
    expect(execute.save_grant_id).toBe("grant-e2e");
    // PLAN-DM-025 Task 4：预览回传的设置修订必须原样重复提交（夹具缺失该字段
    // 或前端改用最新 settingsRevision 时此处红）；不可失败版本（两值确实不同）
    // 在同组"预览后保存模板推进设置修订"用例里，本用例修订 0 == 最新修订 0
    expect(state.previewSettingsRevisions.at(-1)).toBe(0);
    expect(execute.settings_revision).toBe(state.previewSettingsRevisions.at(-1));
    // 打开所在文件夹经专用桥方法：只传扩展与 Artifact 标识，不传 workspace_id/路径
    await page.getByRole("button", {name: "打开所在文件夹"}).click();
    await expect.poll(async () => (await readBridgeCalls(page)).artifactFolderCalls).toEqual([
      {extension_id: EXTENSION_ID, artifact_id: "artifact-e2e"},
    ]);
    expect((await readBridgeCalls(page)).openFolderCalls).toHaveLength(0);
  });

  test("预览漂移（REPREVIEW_REQUIRED）保留编辑，刷新预览后重试成功", async ({page}) => {
    const state = await openCatalog(page, {executeMode: "repreviewRequired"});
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    const alert = page.getByRole("alert").filter({hasText: "预览已过期"});
    await expect(alert).toBeVisible();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}");
    await expect(page.getByRole("button", {name: "重试导出"})).toBeEnabled();
    state.controls.executeMode = "ok";
    await page.getByRole("button", {name: "刷新预览"}).click();
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
  });

  // PLAN-DM-025 Task 4 修复轮 1：夹具 /execute 现在按设置修订做漂移门禁（提交值必须
  // 等于当前修订且是某次预览实际绑定的修订），本用例是 Fix 1（漂移必须给出可见的
  // "先刷新预览"出路）与 Fix 2（提交值必须来自预览、不得用最新修订）的真护栏。
  test("预览后保存模板推进设置修订：导出 409 EXTENSION_SETTINGS_CHANGED 并给出重新预览出路", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    const exportButton = page.getByRole("button", {name: "导出 XLSX"});
    await expect(exportButton).toBeEnabled();
    // 草稿改动触发的重新预览仍绑定保存前的设置修订（夹具记录每次预览绑定的修订）
    await page.getByLabel("输出列名 1").fill("图纸编号");
    await expect.poll(() => state.previewSettingsRevisions.length).toBeGreaterThan(1);
    await expect(exportButton).toBeEnabled();
    // 保存修改推进服务端设置修订：预览不再与当前设置一致
    await page.getByRole("button", {name: "保存修改"}).click();
    await expect.poll(() => state.revision).toBe(4);
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    await exportButton.click();
    await expect.poll(() => state.executeRequests.length).toBe(1);
    // 不可失败断言：提交值等于预览时捕获的修订，而该值不等于最新修订（两值必须不同）
    const boundRevision = state.previewSettingsRevisions.at(-1);
    expect(boundRevision).toBe(3); // 预置 userTemplates 时夹具初始修订为 3
    expect(state.revision).toBe(4);
    expect(state.executeRequests[0].settings_revision).toBe(boundRevision);
    // 漂移的可见出路：稳定错误文案 + "先刷新预览"提示（不再只有"重试导出"）
    const alert = page.getByRole("alert").filter({hasText: "扩展设置已变化"});
    await expect(alert).toBeVisible();
    await expect(alert.getByText("预览已过期，请先刷新预览再重试导出")).toBeVisible();
    // 不刷新预览直接"重试导出"：同一份过期修订被重复提交，必然再次 409（死循环本体）
    await alert.getByRole("button", {name: "重试导出"}).click();
    await expect.poll(() => state.executeRequests.length).toBe(2);
    expect(state.executeRequests[1].settings_revision).toBe(boundRevision);
    await expect(alert).toBeVisible();
    // 刷新预览重新绑定修订后，同一出口导出成功
    await page.getByRole("button", {name: "刷新预览"}).click();
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
    expect(state.previewSettingsRevisions.at(-1)).toBe(4);
    expect(state.executeRequests).toHaveLength(3);
    expect(state.executeRequests.at(-1)!.settings_revision).toBe(4);
  });

  test("授权失效保留编辑并可重试", async ({page}) => {
    const state = await openCatalog(page, {executeMode: "saveGrantInvalid"});
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    await expect(page.getByRole("alert").filter({hasText: "保存授权"})).toBeVisible();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}");
    state.controls.executeMode = "ok";
    await page.getByRole("button", {name: "重试导出"}).click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
  });

  test("写失败保留编辑并可重试", async ({page}) => {
    const state = await openCatalog(page, {executeMode: "writeFailed"});
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    await expect(page.getByRole("alert").filter({hasText: "成果文件写入失败"})).toBeVisible();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}");
    state.controls.executeMode = "ok";
    await page.getByRole("button", {name: "重试导出"}).click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
  });

  // PLAN-DM-024 Task 2 / MEMO-DM-031 F2：壳窗口未就绪时桥抛 RuntimeError，经
  // pywebview 变成 JS Promise 拒绝。此前 exportXlsx 未捕获该拒绝，phase 永久
  // 卡在 exporting、导出按钮死锁；修复后必须落回 failed 并可经同一出口重试。
  test("授权桥拒绝后可重试：本地化错误可见、退出导出中状态，桥恢复后重试成功", async ({page}) => {
    const state = await openCatalog(page, {saveDialog: "reject"});
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    expect((await readBridgeCalls(page)).saveRequests).toHaveLength(1);
    const alert = page.getByRole("alert").filter({hasText: "扩展当前不可用，无法执行该操作"});
    await expect(alert).toBeVisible();
    // 不卡死在"正在导出"：导出按钮回到可点击状态，可再次发起导出
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeEnabled();
    await expect(page.getByText("正在导出")).toHaveCount(0);
    // 桥恢复后同一出口重试成功：重新取授权并执行
    await setSaveDialog(page, "grant");
    await alert.getByRole("button", {name: "重试导出"}).click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
    expect(state.executeRequests).toHaveLength(1);
  });
});

test.describe("可访问性（SPEC-DM-012 §13，Task 12）", () => {
  test("三选一守卫模态移入焦点、Tab 圈闭、Esc 留在此处并归还焦点", async ({page}) => {
    await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    // 记录打开前焦点（触发元素）：守卫关闭后必须归还
    await page.getByRole("tablist").getByRole("tab").first().click();
    const dialog = page.getByRole("dialog", {name: "未保存的模板修改"});
    await expect(dialog).toBeVisible();
    // 焦点已移入模态（Task 11 遗留缺口修复：不再停留在触发元素/页面正文）。
    // 锚点用模态卡片：原生模态不写显式 role/aria-modal（关闭时元素仍常驻 DOM）
    await expect.poll(() => page.evaluate(() => document.activeElement?.closest(".modal-card") !== null)).toBe(true);
    // Tab 圈闭：连续 Tab 焦点始终在模态卡片内（禁用的"保存为模板"不参与）
    for (let step = 0; step < 8; step++) {
      await page.keyboard.press("Tab");
      const inside = await page.evaluate(() => Boolean(document.activeElement?.closest(".modal-card")));
      expect(inside, `第 ${step + 1} 次 Tab 后焦点仍在守卫模态内`).toBe(true);
    }
    // Esc = 留在此处：模态关闭、草稿保留、焦点归还触发元素
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}号");
    await expect.poll(() => page.evaluate(() => document.activeElement?.id)).toBe("tab-sheets");
  });

  test("表达式错误把焦点移到具体列的表达式输入框", async ({page}) => {
    await openCatalog(page);
    const expression = page.getByLabel("表达式 2");
    await expression.fill("{sheet.不存在}");
    // 模拟用户已离开编辑器（错误在防抖预览响应后到达）：焦点应移到出错列的表达式框
    await expression.evaluate(element => (element as HTMLTextAreaElement).blur());
    await expect(page.getByLabel("表达式 2")).toBeFocused();
    await expect(page.getByRole("alert").filter({hasText: "未定义的字段"}).first()).toBeVisible();
  });

  test("重名列阻断错误（无列 ID）把焦点移到匹配的列名输入框", async ({page}) => {
    await openCatalog(page);
    const header = page.getByLabel("输出列名 2");
    await header.fill("图号"); // 与内置默认第 1 列重名（服务端/预览诊断无 column_id）
    await header.evaluate(element => (element as HTMLInputElement).blur());
    // Task 11 遗留缺口修复：无 column_id 的错误此前无法聚焦任何输入
    await expect(page.getByLabel("输出列名 2")).toBeFocused();
    await expect(page.getByRole("alert").filter({hasText: "名称重复：图号"}).first()).toBeVisible();
  });

  test("另存为模态 Esc 关闭、Tab 圈闭并把焦点归还触发按钮", async ({page}) => {
    await openCatalog(page);
    const trigger = page.getByRole("button", {name: "另存为"});
    await trigger.click();
    const dialog = page.getByRole("dialog", {name: "另存为模板"});
    await expect(dialog).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.activeElement?.closest('[role="dialog"][aria-modal="true"]') !== null)).toBe(true);
    for (let step = 0; step < 6; step++) {
      await page.keyboard.press("Tab");
      const inside = await page.evaluate(() => Boolean(document.activeElement?.closest(".modal-card")));
      expect(inside, `第 ${step + 1} 次 Tab 后焦点仍在另存为模态内`).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});

// 扩展列表刷新的草稿生命周期闸门（PLAN-DM-024 / MEMO-DM-031 F1）。
// 缺陷背景：openSettings 触发的 reloadExtensions 失败时清空列表、成功但状态失效时直接
// 替换列表，两条路径都会让活动 sheet-catalog 标签被 useShellTabs 静默卸载，未保存草稿
// 随视图卸载丢失，完全绕过 guardSheetCatalogPage 三选一守卫。
test.describe("扩展列表刷新的草稿生命周期闸门（PLAN-DM-024 F1）", () => {
  test("打开设置触发刷新失败保留目录草稿：标签、激活态与表达式原样保留", async ({page}) => {
    const state = await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    // 打开设置与进入扩展分区各触发一次刷新（openSettings + showExtensions），两次都失败
    planExtensionsReload(state, ["fail", "fail"]);
    await page.getByRole("button", {name: "设置"}).click();
    await page.getByRole("tab", {name: "扩展"}).click();
    // 设置扩展区给出可见降级与重试（瞬时刷新失败不静默呈现为空列表）
    await expect(page.getByText("扩展列表加载失败。")).toBeVisible();
    // 标签仍存在且仍为活动标签：失败不得把用户踢回核心页签
    const catalogTab = page.locator("#tab-sheet-catalog");
    await expect(catalogTab).toBeVisible();
    await expect(catalogTab).toHaveAttribute("aria-selected", "true");
    // 关闭设置后回到目录页：草稿原样保留
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}号");
    await expect(page.getByText("有未保存修改")).toBeVisible();
  });

  test("活动扩展失效先过守卫：留在此处保留标签草稿与旧列表，放弃修改后才移除", async ({page}) => {
    const state = await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    planExtensionsReload(state, ["failedStatus"]);
    await page.getByRole("button", {name: "设置"}).click();
    // 先出现现有三选一守卫（打开设置的刷新先于分区切换返回），此时候选（FAILED）
    // 列表不得提交：守卫不依赖所在分区
    const dialog = page.getByRole("dialog", {name: "未保存的模板修改"});
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", {name: "留在此处"}).click();
    // 守卫返回 stay：标签与草稿保留，进入分区后旧列表未被替换（卡片仍"可用"）
    const catalogTab = page.locator("#tab-sheet-catalog");
    await expect(catalogTab).toBeVisible();
    await expect(catalogTab).toHaveAttribute("aria-selected", "true");
    await page.getByRole("tab", {name: "扩展"}).click();
    await expect(page.locator('[data-extension-id="dst-manager.sheet-catalog"] .ext-meta')).toContainText("可用");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", {name: "图纸目录"})).toBeVisible();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}号");
    // 再次刷新并选择放弃修改：列表替换放行，标签移除并回到图纸页签
    planExtensionsReload(state, ["failedStatus"]);
    await page.getByRole("button", {name: "设置"}).click();
    const dialogAgain = page.getByRole("dialog", {name: "未保存的模板修改"});
    await expect(dialogAgain).toBeVisible();
    await dialogAgain.getByRole("button", {name: "放弃修改"}).click();
    await expect(page.getByRole("tab", {name: "图纸目录"})).toHaveCount(0);
    await expect(page.locator("#tab-sheets")).toHaveAttribute("aria-selected", "true");
  });
});

// PLAN-DM-024 Task 2 / MEMO-DM-031 F3：Shell 扩展错误必须按当前语言渲染
// errors.extension.* 英文资源；桥返回的中文兼容 message 不得出现在 en-US 正文。
// 语言来源用 page 级路由（响应快照 ui_locale=en-US），不写全局 settings.json。
const enSettingsSnapshot = {
  schema_version: 1, config_revision: 1, diagnostics: [], schema_blocked: false,
  items: [{key: "ui_locale", control: "enum", value: "en-US", default: "system", source: "file", has_file_override: true,
    label_key: "settings.items.uiLocale", category_key: "settings.categories.interface",
    options: [{value: "system", text_key: "settings.locale.system"}, {value: "zh-CN", text_key: "settings.locale.zhCN"}, {value: "en-US", text_key: "settings.locale.enUS"}]}],
};

test.describe("Shell 扩展错误使用当前语言（PLAN-DM-024 F3）", () => {
  test("en-US：三个 Shell 扩展错误码正文均为英文资源，不显示桥返回的中文兼容 message", async ({page}) => {
    await page.route("**/api/settings", route => route.fulfill({json: enSettingsSnapshot}));
    await installSheetCatalogFixture(page, {saveDialog: "error", saveDialogError: "EXTENSION_NOT_FOUND"});
    await page.goto("/");
    await page.getByRole("button", {name: "Select DST File"}).click();
    await page.getByRole("tab", {name: "Sheet Catalog"}).click();
    const cases = [
      {code: "EXTENSION_NOT_FOUND", text: "The extension is not registered and the operation cannot be performed"},
      {code: "EXTENSION_ACTION_NOT_FOUND", text: "The extension does not declare this action"},
      {code: "EXTENSION_CAPABILITY_UNAVAILABLE", text: "The extension is currently unavailable"},
    ];
    for (const [index, item] of cases.entries()) {
      await setSaveDialog(page, "error", item.code);
      if (index === 0) {
        await page.getByRole("button", {name: "Export XLSX"}).click();
      } else {
        await page.getByRole("alert").filter({hasText: cases[index - 1]!.text}).getByRole("button", {name: "Retry export"}).click();
      }
      const alert = page.getByRole("alert").filter({hasText: item.text});
      await expect(alert).toBeVisible();
      // 桥的中文兼容 message 只作诊断，不得进入 en-US 正文
      const body = await page.textContent("body");
      expect(body, `桥的中文兼容 message 不得进入 en-US 正文（${item.code}）`).not.toContain("保存对话框不可用");
    }
  });
});

// PLAN-DM-024 Task 3 / MEMO-DM-031 F4：内置模板显示名随宿主语言变化，与内置
// 显示名的碰撞只能在当前 locale 前端拦截（服务端不认识本地化文案）；历史数据
// 或直接 API 注入的显示碰撞在下拉框消歧，但身份与操作仍按 UUID。
test.describe("模板显示名与身份不变量（PLAN-DM-024 F4）", () => {
  test("zh-CN 内置模板显示名冲突：另存为被本地拦截，不发送 PUT 且对话框保留输入", async ({page}) => {
    const state = await openCatalog(page);
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await page.getByRole("button", {name: "另存为"}).click();
    const dialog = page.getByRole("dialog", {name: "另存为模板"});
    await dialog.getByLabel("模板名称").fill("默认图纸目录（内置）");
    await dialog.getByRole("button", {name: "保存", exact: true}).click();
    // 本地化错误可见：不把语言包文案发给后端，也不依赖服务端重名错误
    await expect(page.getByText("该名称与内置默认模板的显示名相同")).toBeVisible();
    // 不发送 PUT：客户端拦截发生在设置端点之前
    expect(state.putExpectedRevisions).toEqual([]);
    expect(state.settingsValue.user_templates).toHaveLength(0);
    // 对话框保留输入
    await expect(dialog.getByLabel("模板名称")).toHaveValue("默认图纸目录（内置）");
  });

  test("en-US 内置模板显示名冲突：另存为被本地拦截并显示英文原因", async ({page}) => {
    await page.route("**/api/settings", route => route.fulfill({json: enSettingsSnapshot}));
    const {state} = await installSheetCatalogFixture(page);
    await page.goto("/");
    await page.getByRole("button", {name: "Select DST File"}).click();
    await page.getByRole("tab", {name: "Sheet Catalog"}).click();
    await page.getByLabel("Expression 1").fill("{sheet.number}#");
    await page.getByRole("button", {name: "Save as"}).click();
    const dialog = page.getByRole("dialog", {name: "Save as template"});
    await dialog.getByLabel("Template name").fill("Default catalog (built-in)");
    await dialog.getByRole("button", {name: "Save", exact: true}).click();
    await expect(page.getByText("matches the built-in default template")).toBeVisible();
    expect(state.putExpectedRevisions).toEqual([]);
    expect(state.settingsValue.user_templates).toHaveLength(0);
    await expect(dialog.getByLabel("Template name")).toHaveValue("Default catalog (built-in)");
  });

  test("历史同名模板可区分：en-US 下内置项与用户项文本可区分且按 UUID 操作", async ({page}) => {
    await page.route("**/api/settings", route => route.fulfill({json: enSettingsSnapshot}));
    const template = userTemplate("Default catalog (built-in)", [{header: "Sheet No.", expression: "{sheet.number}"}]);
    const {state} = await installSheetCatalogFixture(page, {userTemplates: [template]});
    await page.goto("/");
    await page.getByRole("button", {name: "Select DST File"}).click();
    await page.getByRole("tab", {name: "Sheet Catalog"}).click();
    // 内置项与用户项文本可区分：只有碰撞的用户项带“用户模板”后缀
    const select = page.getByRole("combobox", {name: "Select template"});
    await expect(select.locator("option")).toHaveText([
      "Default catalog (built-in)",
      "Default catalog (built-in) (user template)",
    ]);
    // 选择用户项仍按 UUID：option value 与选中值为该模板 UUID
    await select.selectOption({label: "Default catalog (built-in) (user template)"});
    await expect(page.getByLabel("Select template")).toHaveValue(template.template_id);
    // 原位保存：PUT 负载按 UUID 更新该模板，持久化名称不带消歧后缀
    await page.getByLabel("Column header 1").fill("Drawing No.");
    await page.getByRole("button", {name: "Save changes"}).click();
    // en 的 guardMessage 常驻隐藏 dialog 且含 "unsaved changes" 子串，不能用
    // getByText 宽松匹配；按脏标记元素精确断言。
    await expect(page.locator(".dirty-badge")).toHaveCount(0);
    expect(state.settingsValue.user_templates).toHaveLength(1);
    expect(state.settingsValue.user_templates[0]!.template_id).toBe(template.template_id);
    expect(state.settingsValue.user_templates[0]!.name).toBe("Default catalog (built-in)");
    // 删除：仍按该用户模板 UUID 删除
    await page.getByRole("button", {name: "Delete template"}).click();
    const dialog = page.locator('[role="dialog"][aria-modal="true"]');
    await dialog.getByRole("button", {name: "Delete", exact: true}).click();
    expect(state.settingsValue.user_templates).toEqual([]);
  });
});

// PLAN-DM-026 Task 3（SPEC-DM-012 §4.2/§5.4/§7.2 区域 2）：字段条目的数字格式码入口。
// 入口只把 `:0`/`:0000` 这类格式码拼进表达式文本，属于只读导出的输出格式化——
// 不修改 DST/DWG、不写回属性值、不做重编号。
test.describe("数字格式码入口（PLAN-DM-026）", () => {
  // 条目行 = 字段引用按钮 + 同行格式入口；格式入口与菜单项的可访问名不含字段引用文本，
  // 因此可与既有的 getByRole("button", {name: /sheet\.number/}) 严格定位共存。
  function fieldEntry(page: Page, reference: RegExp) {
    const browser = page.getByRole("region", {name: "字段浏览器"});
    return browser.locator(".field-entry").filter({has: page.getByRole("button", {name: reference})});
  }

  test("数字格式码入口把图号补零到 4 位", async ({page}) => {
    await openCatalog(page);
    const expression = page.getByLabel("表达式 1");
    await expression.fill("");
    const entry = fieldEntry(page, /sheet\.number/);
    const trigger = entry.getByRole("button", {name: "格式"});
    await trigger.click();
    await entry.getByRole("button", {name: "补零到 4 位"}).click();
    await expect(expression).toHaveValue("{sheet.number:0000}");
    // 夹具由 pad3 生成图号，首张为 001；补零只作用于输出侧，工作区快照不变
    await expect(page.getByRole("region", {name: "预览"}).getByRole("cell", {name: "0001", exact: true})).toBeVisible();
    // 选中即关闭菜单（选项随 v-if 卸载，回归为不关闭时这里会数到 6）；
    // 焦点由既有 caret 协议交给表达式输入框，不会落到 body（与点击 .field-chip 一致）
    await expect(entry.locator(".field-format-menu").getByRole("button")).toHaveCount(0);
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(expression).toBeFocused();
  });

  test("数字格式码入口可去掉前导零", async ({page}) => {
    await openCatalog(page);
    const expression = page.getByLabel("表达式 1");
    await expression.fill("");
    const entry = fieldEntry(page, /sheet\.number/);
    const trigger = entry.getByRole("button", {name: "格式"});
    await trigger.click();
    await entry.getByRole("button", {name: "去前导零"}).click();
    await expect(expression).toHaveValue("{sheet.number:0}");
    await expect(page.getByRole("region", {name: "预览"}).getByRole("cell", {name: "1", exact: true})).toBeVisible();
    // 同上：选中即关闭菜单，焦点交给表达式输入框（caret 协议），不落回 body
    await expect(entry.locator(".field-format-menu").getByRole("button")).toHaveCount(0);
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(expression).toBeFocused();
  });

  // 轻量 disclosure 菜单的键盘/指针契约：选中、Esc、外部点击与搜索过滤都要关闭；
  // 菜单在流内展开，打开时不得把字段栏撑宽（SPEC-DM-012 §7.2 冻结宽度 258px）。
  test("数字格式码菜单在选中、Esc、外部点击和搜索过滤时关闭", async ({page}) => {
    await openCatalog(page);
    const browser = page.getByRole("region", {name: "字段浏览器"});
    const entry = fieldEntry(page, /sheet\.number/);
    const trigger = entry.getByRole("button", {name: "格式"});

    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    // 去前导零 + NUMBER_FORMAT_WIDTHS 的 5 个补零选项
    await expect(entry.locator(".field-format-menu").getByRole("button")).toHaveCount(6);
    // 字段栏宽度由父级 SheetCatalogView 的固定 grid 轨道（258px）决定、且 .field-browser 带
    // overflow:hidden，因此不能拿“展开前后盒宽相等”当断言（永真）。这里改钉绝对冻结区间，
    // 与 sheet-catalog-visual-evidence.spec.ts 的轨道守卫同口径：轨道被改宽或菜单撑开布局即失败。
    const widthOpen = (await browser.boundingBox())!.width;
    expect(widthOpen, "菜单展开时字段栏仍为冻结的 258px 轨道").toBeGreaterThanOrEqual(256);
    expect(widthOpen, "菜单展开时字段栏仍为冻结的 258px 轨道").toBeLessThanOrEqual(260);

    // Esc 关闭并归还焦点到触发按钮
    await page.keyboard.press("Escape");
    await expect(entry.locator(".field-format-menu").getByRole("button")).toHaveCount(0);
    await expect(trigger).toBeFocused();

    // 外部点击关闭（搜索框不属于格式入口）
    await trigger.click();
    await expect(entry.locator(".field-format-menu").getByRole("button")).toHaveCount(6);
    await page.getByLabel("搜索可用字段").click();
    await expect(entry.locator(".field-format-menu").getByRole("button")).toHaveCount(0);
    await expect(trigger).toHaveAttribute("aria-expanded", "false");

    // 键盘展开后行被搜索过滤：菜单状态同步关闭，清空搜索不意外重新展开
    // （fill 不派发 pointerdown，因此这里只能靠 query 变化关闭菜单）
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    await page.getByLabel("搜索可用字段").fill("图名");
    await expect(entry).toHaveCount(0);
    await page.getByLabel("搜索可用字段").fill("");
    await expect(entry.locator(".field-format-menu").getByRole("button")).toHaveCount(0);
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});

// ---- PLAN-DM-025 Task 8：输出图纸过滤的呈现（R14）、预览响应违约的可见诊断（R15）、
//      设置中心 custom 面板与业务页两个实例不共享可变状态（SPEC-DM-011 SC-17）----
// 过滤语义在服务端（settings.py 的 normalize/title_matches_exclusion），夹具按同一规则
// 计算 total_rows/filtered_rows；页面只呈现：total_rows 是过滤后的输出行数，filtered_rows=0
// 时不显示任何过滤提示（SPEC-DM-012 §8.1）。
test.describe("输出图纸过滤与预览契约（PLAN-DM-025 Task 8）", () => {
  test("部分过滤：预览显示过滤后的行数与「已过滤 1 张图纸」，命中为 0 时不出现该提示", async ({page}) => {
    const state = await openCatalog(page, {excludedTitleKeywords: ["003"]});
    const preview = page.getByRole("region", {name: "预览"});
    // 25 张图纸中「图纸 003」被排除：输出 24 行（仍只显示前 20 行）
    await expect(preview.getByText("输出 24 张图纸")).toBeVisible();
    await expect(preview.getByTestId("catalog-preview-filtered")).toHaveText("已过滤 1 张图纸");
    await expect(preview.getByText("共 24 张图纸")).toHaveCount(0);
    await expectPreviewRows(page, 20);

    // 过滤词被清空（等价于在设置中心 custom 面板保存空过滤词）：提示消失、文案回到未过滤形态
    state.settingsValue = {user_templates: state.settingsValue.user_templates};
    await preview.getByRole("button", {name: "刷新预览"}).click();
    await expect(preview.getByTestId("catalog-preview-filtered")).toHaveCount(0);
    await expect(preview.getByText("共 25 张图纸")).toBeVisible();
  });

  test("全部过滤：显示「已过滤 25 张图纸」与输出 0 行，仍可导出（空工作簿）", async ({page}) => {
    await openCatalog(page, {excludedTitleKeywords: ["图纸"]});
    const preview = page.getByRole("region", {name: "预览"});
    await expect(preview.getByText("输出 0 张图纸")).toBeVisible();
    await expect(preview.getByTestId("catalog-preview-filtered")).toHaveText("已过滤 25 张图纸");
    await expect(preview.getByText("当前图纸集没有图纸")).toBeVisible();
    // 全部被过滤仍是可执行状态：导出不被阻断（后端生成只有表头的有效工作簿）
    const exportButton = page.getByRole("button", {name: "导出 XLSX"});
    await expect(exportButton).toBeEnabled();
    await exportButton.click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
  });

  test("预览响应违约（缺 settings_revision 绑定）：给出可见诊断与可重试出口，不静默禁用导出", async ({page}) => {
    const state = await openCatalog(page, {omitPreviewSettingsRevision: true});
    // 违约响应不发布预览：兼容性状态带显示失败正文，而不是静默无反应（R15）
    const summary = page.getByRole("region", {name: "兼容性摘要"});
    await expect(summary).toContainText("预览失败");
    await expect(summary).toContainText("预览响应缺少设置修订绑定");
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeDisabled();
    // 重试出口可用：服务端恢复契约后刷新预览即回到就绪态
    state.previewContractBroken = false;
    await page.getByRole("region", {name: "预览"}).getByRole("button", {name: "刷新预览"}).click();
    await expect(summary).toContainText("模板与当前图纸集兼容");
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeEnabled();
  });

  test("设置中心 custom 面板与业务页是两个实例：面板改模板/过滤词不改变业务页草稿状态", async ({page}) => {
    const state = await openCatalog(page);
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    // 打开设置中心 → 扩展 → 配置（生产图纸目录的唯一 custom 面板）
    await page.getByRole("button", {name: "设置"}).click();
    const dialog = page.locator('dialog[aria-labelledby="settings-title"]');
    await expect(dialog).toBeVisible();
    await page.getByRole("tab", {name: "扩展"}).click();
    await page.getByRole("button", {name: "配置 图纸目录"}).click();
    const panel = dialog.locator('[data-testid="sheet-catalog-settings-panel"]');
    await expect(panel).toBeVisible();
    // 面板内改过滤词并保存：写的是扩展设置（PUT /settings），业务页草稿不受影响
    await panel.locator('[data-testid="catalog-settings-filter"]').fill("003");
    await dialog.getByRole("button", {name: "保存", exact: true}).click();
    await expect(dialog.getByTestId("extension-settings-saved-pill")).toBeVisible();
    expect(state.settingsValue.excluded_title_keywords).toEqual(["003"]);
    // 业务页草稿仍是未修改状态（面板实例的编辑不进入页面实例）
    await expect(page.getByText("有未保存修改")).toHaveCount(0);
    // 两处「表达式 1」同时存在（业务页 + 面板）正说明是两个实例：断言页面那一份未被改动
    await expect(page.getByRole("region", {name: "图纸目录", exact: true}).getByLabel("表达式 1")).toHaveValue("{sheet.number}");
    // 返回扩展列表并关闭设置后刷新预览：服务端按新过滤词重算，业务页显示过滤结果
    await dialog.getByRole("button", {name: "返回扩展列表"}).click();
    await dialog.getByRole("button", {name: "关闭设置"}).click();
    await expect(dialog).toBeHidden();
    const preview = page.getByRole("region", {name: "预览"});
    await preview.getByRole("button", {name: "刷新预览"}).click();
    await expect(preview.getByTestId("catalog-preview-filtered")).toHaveText("已过滤 1 张图纸");
    await expect(preview.getByText("输出 24 张图纸")).toBeVisible();
  });
});

test.describe("初始化设置读取失败（PLAN-DM-025 Task 8 修复轮 I2）", () => {
  // 协议层只给 loadFailed 布尔，页面层的正文来自 extensions.sheetCatalog.settingsLoadFailed。
  // 该键缺失时 check-i18n 不会报错（只查 zh/en 对称与硬编码中文），页面会直接把原始 key
  // 当作正文印给用户——本用例钉住键存在且被真正使用。
  test("业务页以已登记文案键给出可见失败提示，不渲染原始 key 也不伪造可编辑正文", async ({page}) => {
    await openCatalog(page, {settingsGetFailure: true});

    await expect(page.getByRole("alert").filter({hasText: "图纸目录设置加载失败，请重试"})).toBeVisible();
    await expect(page.getByText("extensions.sheetCatalog.settingsLoadFailed")).toHaveCount(0);
    // 失败态下不渲染模板栏/预览（没有可编辑正文，也不伪造默认模板可保存）
    await expect(page.getByRole("button", {name: "另存为"})).toHaveCount(0);
    await expect(page.getByRole("region", {name: "预览"})).toHaveCount(0);
  });
});

// ---- PLAN-DM-025 Task 8 修复轮 1（B 部分）：草稿变更键（I3）与只读呈现（I5）、
//      列状态徽标（M2）、进行中总行数（M6）----
test.describe("修复轮 1（B 部分）（PLAN-DM-025 Task 8）", () => {
  // I3：变更键必须含列 UUID。后端 preview_digest 按列的规范 ID 计算，因此表头与表达式
  // 逐一相同、只有列 UUID 不同的两份模板是两次不同的预览输入。只比较内容时切换模板
  // 既不重放预览、也不显示"草稿已修改，预览更新后才能导出"（previewedColumns 没变），
  // 导出按钮保持可用，执行却会被 REPREVIEW_REQUIRED 拒绝。
  test("等值模板切换（列 UUID 不同）重放预览并允许导出", async ({page}) => {
    const columns = [{header: "图号", expression: "{sheet.number}"}, {header: "图名", expression: "{sheet.title}"}];
    const first = userTemplate("等值模板甲", columns);
    const second = userTemplate("等值模板乙", columns);
    // 前置：两份模板的表头与表达式逐一相同（唯一差别是列 UUID），否则本用例证明不了 I3
    expect(first.columns.map(column => [column.header, column.expression]))
      .toEqual(second.columns.map(column => [column.header, column.expression]));
    expect(first.columns.map(column => column.column_id)).not.toEqual(second.columns.map(column => column.column_id));

    const state = await openCatalog(page, {userTemplates: [first, second], preferenceTemplateId: first.template_id});
    const submittedColumnIds = (index: number) => (state.previewRequests[index]!.template as {columns: {column_id: string}[]}).columns.map(column => column.column_id);
    await expect(page.getByLabel("选择模板")).toHaveValue(first.template_id);
    // 首帧预览（偏好选中的等值模板甲）
    await expect.poll(() => state.previewRequests.length).toBe(1);
    expect(submittedColumnIds(0)).toEqual(first.columns.map(column => column.column_id));

    await page.getByLabel("选择模板").selectOption(second.template_id);
    // 列 UUID 不同就是新的预览输入：必须重放（旧实现按内容签名比较，这里不会发出请求）
    await expect.poll(() => state.previewRequests.length).toBe(2);
    expect(submittedColumnIds(1)).toEqual(second.columns.map(column => column.column_id));
    // 列状态仍由服务端诊断驱动（M2 不得拿业务页开刀）：本次预览无错误 → 逐列"有效"
    await expect(page.getByRole("region", {name: "输出列编辑器"}).locator(".status-badge").first()).toHaveText("有效");
    // 导出门禁回到就绪态：按钮可用且执行成功（模板快照带的是选中模板的列 UUID）
    await expect(page.getByRole("button", {name: "导出 XLSX"})).toBeEnabled();
    await page.getByRole("button", {name: "导出 XLSX"}).click();
    await expect(page.getByText("图纸目录已保存到")).toBeVisible();
    expect((state.executeRequests.at(-1)!.template as {columns: {column_id: string}[]}).columns.map(column => column.column_id))
      .toEqual(second.columns.map(column => column.column_id));
  });

  // I5：高版本只读（EXTENSION_SETTINGS_SCHEMA_NEWER）此前在业务页完全不可见——控制器在
  // 只读态直接返回 false，点"保存修改"没有任何反馈。现在业务页给出与设置中心同源的
  // 只读通知，并把三个保存入口（保存修改/另存为/删除模板）与守卫的"保存为模板"停用。
  test("高版本只读：业务页可见通知且保存入口停用，不留下无反馈的按钮", async ({page}) => {
    const template = userTemplate("标准目录", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {settingsReadOnly: true, userTemplates: [template], preferenceTemplateId: template.template_id});

    const notice = page.getByTestId("sheet-catalog-readonly");
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("已只读保留，无法覆盖保存");
    await expect(notice).toContainText("EXTENSION_SETTINGS_SCHEMA_NEWER");

    // 有未保存修改（本地草稿仍然可编辑）时保存入口也必须停用：控制器只读短路不落盘，
    // 按钮可点就是"点了没反应"的静默出口
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await expect(page.getByText("有未保存修改")).toBeVisible();
    await expect(page.getByRole("button", {name: "保存修改"})).toBeDisabled();
    await expect(page.getByRole("button", {name: "另存为"})).toBeDisabled();
    await expect(page.getByRole("button", {name: "删除模板"})).toBeDisabled();
    expect(state.settingsPutBodies).toHaveLength(0);

    // 导航守卫的"保存为模板"同源停用（此前点它只静默停在原地）
    await page.getByRole("tablist").getByRole("tab").first().click();
    const guard = page.getByRole("dialog", {name: "未保存的模板修改"});
    await expect(guard).toBeVisible();
    await expect(guard.getByRole("button", {name: "保存为模板"})).toBeDisabled();
    await guard.getByRole("button", {name: "留在此处"}).click();
    await expect(guard).toBeHidden();
    await expect(page.getByLabel("表达式 1")).toHaveValue("{sheet.number}号");
  });

  // M6：进行中状态不得让文案与数字自相矛盾。过滤提示与总数文案必须来自同一份预览：
  // 此前提示只在 ready 态显示，而总数一直用旧预览的（已过滤）行数，重算过程中会出现
  // "输出 24 张图纸"却没有"已过滤 1 张图纸"。
  test("预览进行中：过滤提示与总数取自同一份预览，不出现自相矛盾的计数", async ({page}) => {
    await openCatalog(page, {excludedTitleKeywords: ["003"]});
    const preview = page.getByRole("region", {name: "预览"});
    await expect(preview.getByText("输出 24 张图纸")).toBeVisible();
    await expect(preview.getByTestId("catalog-preview-filtered")).toHaveText("已过滤 1 张图纸");

    // 挂起下一次预览响应，把页面钉在 pending 态：这一期间仍展示旧预览的数字与其过滤提示
    let release = () => {};
    const held = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/api/extensions/*/actions/*/preview", async route => {
      await held;
      await route.fallback(); // 交给夹具的预览处理器（fallback 保持既有路由生效）
    });
    await page.getByLabel("表达式 1").fill("{sheet.number}号");
    await expect(preview.getByText("正在更新预览…")).toBeVisible();
    await expect(preview.getByText("输出 24 张图纸")).toBeVisible();
    await expect(preview.getByTestId("catalog-preview-filtered")).toHaveText("已过滤 1 张图纸");
    release();
    // 新预览到达后回到就绪态（表格首列按新表达式求值），过滤计数仍与服务端一致
    await expect(preview.getByRole("cell", {name: "001号", exact: true}).first()).toBeVisible();
    await expect(preview.getByTestId("catalog-preview-filtered")).toHaveText("已过滤 1 张图纸");
  });

  // 修复轮 1（C 部分）：只读转换窗口（GET 仍可写 → 首次 PUT 被 409 SCHEMA_NEWER 拒绝）
  // 内已经打开的"另存为"模态，确认按钮必须与三个保存入口同源停用。生产上这条窗口对应
  // "客户端落后于服务端升版"：控制器在只读态直接返回 false，按钮可点就是"点了没反应"的静默出口。
  test("只读转换窗口：已打开的另存为模态确认按钮同源停用，不再静默失败", async ({page}) => {
    const state = await openCatalog(page, {settingsReadOnlyAfterPut: true});
    await expect(page.getByTestId("sheet-catalog-readonly")).toHaveCount(0);

    await page.getByRole("button", {name: "另存为"}).click();
    const modal = page.getByRole("dialog", {name: "另存为模板"});
    await expect(modal).toBeVisible();
    await modal.getByLabel("模板名称").fill("转换窗口目录");
    // 服务端已升版：这一发 PUT 以 409 SCHEMA_NEWER 被拒，客户端就地转入粘性只读
    await modal.getByRole("button", {name: "保存", exact: true}).click();
    await expect(page.getByTestId("sheet-catalog-readonly")).toBeVisible();
    await expect(page.getByTestId("sheet-catalog-readonly")).toContainText("EXTENSION_SETTINGS_SCHEMA_NEWER");
    // 模态仍开着（失败不关闭、输入不丢），但确认按钮已停用：再点也只会静默返回 false
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("button", {name: "保存", exact: true})).toBeDisabled();
    await expect(modal.getByLabel("模板名称")).toHaveValue("转换窗口目录");
    expect(state.settingsPutBodies).toHaveLength(1);
    // 取消后回到可编辑正文，但三个保存入口一律停用（与既有只读用例同一口径）
    await modal.getByRole("button", {name: "取消"}).click();
    await expect(modal).toBeHidden();
    await expect(page.getByRole("button", {name: "另存为"})).toBeDisabled();
    // 关键回归：只读拒绝（409 SCHEMA_NEWER）会在保存过程中丢弃本地编辑，使得"仍脏"不再
    // 成立；若成功判定只看脏位，这次未落盘的保存会被误报为成功（模态关闭 + 成功提示）。
    // 本地编辑已丢弃，因此保存入口不存在而不是停用。
    await expect(page.getByRole("button", {name: "保存修改"})).toHaveCount(0);
    // 未落盘的保存不得发成功通知（此前只读拒绝会被误报为成功）
    await expect(page.locator(".toast-host .toast")).toHaveCount(0);
  });
});

// ---- PLAN-DM-029 Task 6：图纸目录页控件视觉基础由原语与令牌解析（追踪矩阵 T6） ----
// 断言口径与 properties-visual-evidence.spec.ts（Task 5）同源：期望值不硬编码 px 或色值，
// 而是在真实渲染文档里用探针元素从令牌解析后比对，令牌改名或改值都会连带失败。覆盖截图
// 红框内的模板栏动作、输出列编辑、字段搜索与导出 XLSX 的计算样式、禁用边界与表头轨道
// 对齐；结构尺寸断言锁定冻结 Demo 的首屏密度（T6-7 新增的 7 个 --catalog-* 令牌，值逐字
// 等值、零视觉变化），这些数值一旦回退成裸字面量就会再次触发 raw-visual-value。
test.describe("控件视觉基础（PLAN-DM-029 Task 6）", () => {
  // 用探针元素解析令牌的当前计算值。宽度/尺寸类属性对 inline 元素不生效，探针必须是
  // inline-block，否则 width 会读到 "auto"，断言将永远失败而不是核对令牌。
  async function resolveToken(page: Page, token: string, property: string): Promise<string> {
    return page.evaluate(({name, prop}) => {
      const probe = document.createElement("span");
      probe.style.display = "inline-block";
      probe.style.setProperty(prop, `var(${name})`);
      document.body.appendChild(probe);
      const value = getComputedStyle(probe).getPropertyValue(prop);
      probe.remove();
      return value;
    }, {name: token, prop: property});
  }

  // 元素的计算样式必须等于指定令牌的解析值
  async function expectToken(page: Page, target: Locator, property: string, token: string): Promise<void> {
    const expected = await resolveToken(page, token, property);
    expect(expected, `${token} 必须能解析成具体值`).not.toBe("");
    const actual = await target.first().evaluate((element, prop) => getComputedStyle(element).getPropertyValue(prop), property);
    expect(actual, `${property} 应来自 ${token}`).toBe(expected);
  }

  // 可见 label（T6-5）：仅 aria-label 不算——≤720px 表头隐藏后，这个可见 label 是唯一的可见列标签。
  // 实现上不得用「先读 id 再查 label[for]」的两次往返——UiInput 的兜底 id
  // 来自模块级计数器（见 instanceId.ts），id 按挂载顺序分配而非行序，控件重挂载就会换 id，
  // 两次往返之间发生重挂载即假失败（本用例曾因此 flaky）。这里改用 Playwright 自身的可访问
  // 名称计算 + 独立定位可见 label 元素，两者都不依赖 id，也不依赖 getByLabel 命中的是哪个节点。
  async function expectVisibleLabel(page: Page, control: Locator, text: string): Promise<void> {
    await expect(control.first(), `「${text}」应命中控件本身而不是 label`).toHaveJSProperty("tagName", "INPUT");
    await expect(control.first(), `「${text}」的可访问名称`).toHaveAccessibleName(text);
    await expect(control.first(), `「${text}」的名称必须来自可见 label，而不是仅 aria-label`).not.toHaveAttribute("aria-label", /.+/);
    await expect(page.locator("label.ui-input__label").filter({hasText: text}), `可见 label「${text}」`).toBeVisible();
  }

  // 同一工具区内所有动作按钮必须同高。这是迁移留下的真实缺陷的回归守卫：
  // 迁移曾把 .template-row 留成「删除 34px（--control-height-compact）/ 保存 36px（UiButton）」，
  // 而迁移前该行统一 34px；按收口裁定全页动作按钮归一为 UiButton 默认 36px。
  async function expectUniformButtonHeights(page: Page, selector: string): Promise<void> {
    const heights = await page.locator(selector).evaluateAll(buttons => buttons.map(button => getComputedStyle(button).height));
    expect(heights.length, `${selector} 至少要匹配到一个动作按钮`).toBeGreaterThan(0);
    expect(new Set(heights).size, `${selector} 内动作按钮高度必须一致，实际 ${heights.join(" / ")}`).toBe(1);
  }

  test("模板栏三级动作：次要、危险与脏位驱动的保存禁用边界", async ({page}) => {
    const template = userTemplate("市政标准目录", [{header: "图纸编号", expression: "{sheet.number}"}]);
    await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    const save = page.getByRole("button", {name: "保存修改"});
    const saveAs = page.getByRole("button", {name: "另存为"});
    const remove = page.getByRole("button", {name: "删除模板"});
    // 干净草稿：保存入口存在但停用，另存为与删除可用
    await expect(save).toBeVisible();
    await expect(save).toBeDisabled();
    await expect(saveAs).toBeEnabled();
    // 次要层级：表面底色、常规文字、36px 控件档与 --radius-md 圆角
    await expectToken(page, saveAs, "height", "--button-height");
    await expectToken(page, saveAs, "font-size", "--button-font-size");
    await expectToken(page, saveAs, "background-color", "--color-bg-surface");
    await expectToken(page, saveAs, "border-top-left-radius", "--radius-md");
    // 危险层级：删除是文字型危险动作，颜色只能来自 --color-danger
    await expectToken(page, remove, "color", "--color-danger");
    // 脏位驱动：改一处列名后保存入口转为可用（禁用不是装饰）
    await page.getByLabel("输出列名 1").fill("图纸编号A");
    await expect(save).toBeEnabled();
    await expectToken(page, save, "border-top-left-radius", "--radius-md");
    await expectToken(page, save, "font-size", "--button-font-size");
    // 同行一致（回归守卫）：保存/另存为是 UiButton，删除是保留低强调写法的裸按钮；
    // 迁移曾把后者留在 34px（--control-height-compact）而前者是 36px，本用例正是
    // 用户截图红框所在的行。等高断言排在单值断言之前，改回 34px 时由它先失败。
    await expectUniformButtonHeights(page, ".template-row button, .dock-row button");
    await expectToken(page, remove, "height", "--button-height");
    // 横向内边距：UiButton 默认 --space-4（迁移前 .template-row button 是 --space-3）；
    // 删除按钮有意保留 --space-3 的低强调写法（透明底 + 危险文字，不用实心 danger 变体），
    // 因此本轮只统一高度、不统一内边距。
    await expectToken(page, saveAs, "padding-left", "--space-4");
    await expectToken(page, remove, "padding-left", "--space-3");
    // 全页动作按钮同一档：任一按钮高度回退到 30/32/34px 都会在这里失败
    await expectUniformButtonHeights(page, ".template-row button, .dock-row button, .preview-head button, .editor-foot button");
  });

  test("导出 XLSX：唯一高强调 primary 动作的层级与控件档", async ({page}) => {
    await openCatalog(page);
    const exportButton = page.getByRole("button", {name: "导出 XLSX"});
    const dock = page.locator(".actions-dock");
    await expect(exportButton).toBeEnabled();
    // 高强调层级：accent 底 + on-accent 前景 + 36px 档
    await expectToken(page, exportButton, "background-color", "--color-accent");
    await expectToken(page, exportButton, "color", "--color-on-accent");
    await expectToken(page, exportButton, "height", "--button-height");
    await expectToken(page, exportButton, "border-top-left-radius", "--radius-md");
    // 内边距迁移前后都是 --space-4，未变（.dock-row button 迁移前即 --space-4）
    await expectToken(page, exportButton, "padding-left", "--space-4");
    // 操作坞内只有一个高强调动作：导出是唯一 primary，其余入口是次要层级
    await expect(dock.locator(".ui-button--primary")).toHaveCount(1);
    await expectToken(page, dock.locator(".dock-summary"), "font-size", "--font-caption");
    // 预览卡头的刷新动作用同一控件档
    await expectToken(page, page.getByRole("button", {name: "刷新预览"}), "height", "--button-height");
  });

  test("添加输出列与行内动作：控件档、点击面积与危险色", async ({page}) => {
    await openCatalog(page);
    const editor = page.getByRole("region", {name: "输出列编辑器"});
    // 编辑器尾部动作是次要控件
    const addColumn = editor.getByRole("button", {name: "添加输出列"});
    await expectToken(page, addColumn, "height", "--button-height");
    await expectToken(page, addColumn, "font-size", "--button-font-size");
    // A1 保留 ↑/↓/✕ 字符图标（T6-8）：点击面积取 --tap-target-min(32px)，
    // 圆角与字号按令牌给，不再裸写 30px/6px/13px
    const moveUp = editor.getByRole("button", {name: "上移 2"});
    await expectToken(page, moveUp, "width", "--tap-target-min");
    await expectToken(page, moveUp, "min-height", "--tap-target-min");
    await expectToken(page, moveUp, "border-top-left-radius", "--radius-sm");
    await expectToken(page, moveUp, "font-size", "--font-label");
    await expectToken(page, editor.getByRole("button", {name: "删除列 2"}), "color", "--color-danger");
    // 行内动作仍收在右对齐的第 5 条轨道里且不溢出（3×32 + 2×4 = 104 ≤ 112）
    const track = await editor.locator(".row-actions").first().evaluate(element => {
      const box = element.getBoundingClientRect();
      const buttons = Array.from(element.querySelectorAll("button")).map(button => button.getBoundingClientRect());
      return {
        left: box.left, right: box.right,
        buttons: buttons.map(item => ({left: item.left, right: item.right})),
      };
    });
    expect(track.buttons).toHaveLength(3);
    expect(Math.abs(track.buttons[2]!.right - track.right), "行内动作右对齐到轨道右边界").toBeLessThanOrEqual(1);
    expect(track.buttons[0]!.left, "三枚按钮不溢出轨道左边界").toBeGreaterThanOrEqual(track.left - 1);
    // 表达式文本域是等宽正文：最小高度、圆角与字号全部按令牌
    const expression = page.getByLabel("表达式 1");
    await expectToken(page, expression, "border-top-left-radius", "--radius-md");
    await expectToken(page, expression, "min-height", "--catalog-column-expression-min-height");
    await expectToken(page, expression, "font-size", "--font-label");
    await expectToken(page, expression, "font-family", "--font-mono");
  });

  test("输出列名与字段搜索：可见 label 关联控件，输入档 38px", async ({page}) => {
    await openCatalog(page);
    const header1 = page.getByLabel("输出列名 1");
    // 可见 label 而不是仅 aria-label（T6-5）：未迁移前这里没有 label，探针会找不到关联
    await expectVisibleLabel(page, header1, "输出列名 1");
    await expectToken(page, header1, "height", "--input-height");
    await expectToken(page, header1, "font-size", "--input-font-size");
    await expectToken(page, header1, "border-top-left-radius", "--radius-md");
    const query = page.getByLabel("搜索可用字段");
    // 字段搜索框与属性页同惯例：type="search" → role searchbox（属性页 spec 也按角色钉死，
    // 如 properties-definitions.spec.ts:106 / properties-buffer.spec.ts:72）。
    await expect(page.getByRole("searchbox", {name: "搜索可用字段"}), "字段搜索框应为 searchbox 角色").toBeVisible();
    await expectVisibleLabel(page, query, "搜索可用字段");
    await expectToken(page, query, "height", "--input-height");
  });

  // 责任 K 的另一半（T12-4，PLAN-DM-029）：14px/18px 此前无独立语义档位，5 处卡/页标题只能跨层
  // 借用组件层令牌（--button-font-size / --modal-title-font-size）——“值等值但语义不符”即语义说谎。
  // 本用例是这批声明的**真实性守卫**：
  //   ① 两个档位必须真实存在于语义层（直接读根元素自定义属性；缺失时读回空字符串）；
  //   ② 零视觉变化：5 处计算字号仍逐字等于 14px / 18px。
  // ①必须直接读自定义属性，**不能**用 resolveToken 探针代替：探针在令牌缺失时会回落到继承来的
  // 14px，恰好等于 14px 档位的期望值，在 14px 上会假通过（本任务已实测确认这一盲点）。
  test("语义字号档位：5 处卡/页标题消费语义层 14px/18px 档位", async ({page}) => {
    const template = userTemplate("语义字号档位核查", [{header: "图号", expression: "{sheet.number}"}]);
    const state = await openCatalog(page, {userTemplates: [template], preferenceTemplateId: template.template_id});
    const rootToken = (name: string) => page.evaluate(
      (token) => getComputedStyle(document.documentElement).getPropertyValue(token).trim(), name);
    expect(await rootToken("--font-card-title"), "--font-card-title 必须是已声明的语义档位").toBe("14px");
    expect(await rootToken("--font-view-title"), "--font-view-title 必须是已声明的语义档位").toBe("18px");
    await expectToken(page, page.locator(".preview-head h3"), "font-size", "--font-card-title");
    await expectToken(page, page.locator(".field-head h3"), "font-size", "--font-card-title");
    await expectToken(page, page.locator(".editor-head h3"), "font-size", "--font-card-title");
    await expectToken(page, page.locator(".catalog-head h2"), "font-size", "--font-view-title");
    // 冲突面板的 h3 同样是 14px 卡标题档位（由夹具布防冲突后可见）
    state.controls.putSettingsMode = "conflict";
    await page.getByLabel("输出列名 1").fill("语义字号档位核查");
    await page.getByRole("button", {name: "保存修改"}).click();
    const conflict = page.getByRole("alert").filter({hasText: "模板已被其他保存更新"});
    await expect(conflict).toBeVisible();
    await expectToken(page, conflict.locator("h3"), "font-size", "--font-card-title");
    // 零视觉变化的**直接绝对值锚**（值逐字等值）：上组断言只钉住「元素值 == 令牌解析值」，
    // 本组直接钉住像素值，二者合起来才能同时证明「已消费新档位」与「渲染没变」（只有前者时，
    // 把档位改成 18px 会两边一起变而仍然全绿 —— 上一轮 15px 档位的变异自证就吃过这一课）。
    await expect(page.locator(".preview-head h3")).toHaveCSS("font-size", "14px");
    await expect(page.locator(".field-head h3")).toHaveCSS("font-size", "14px");
    await expect(page.locator(".editor-head h3")).toHaveCSS("font-size", "14px");
    await expect(page.locator(".catalog-head h2")).toHaveCSS("font-size", "18px");
    await expect(conflict.locator("h3")).toHaveCSS("font-size", "14px");
  });

  test("结构尺寸来自组件层令牌且表头轨道与数据行对齐", async ({page}) => {
    await openCatalog(page);
    const editor = page.getByRole("region", {name: "输出列编辑器"});
    // 工作区栅格与卡标题：首屏密度预算仍取冻结 Demo 的确定值（T6-7）
    await expectToken(page, page.locator(".catalog-row"), "height", "--catalog-pane-height");
    // 18px 页标题已升为语义档位 --font-view-title（责任 K 另一半，T12-4），不再借用组件层令牌
    await expectToken(page, page.locator(".catalog-head h2"), "font-size", "--font-view-title");
    await expectToken(page, page.locator(".catalog-preview"), "min-height", "--catalog-preview-min-height");
    await expectToken(page, page.locator(".table-window"), "max-height", "--catalog-preview-table-max-height");
    await expectToken(page, editor.locator(".columns"), "max-height", "--catalog-columns-max-height");
    // 模板选择保留原生 select（UiSelect 的可见 label 会把这行从单行压成两行），宽度由令牌给
    await expectToken(page, page.locator(".template-select select"), "min-width", "--catalog-template-select-min-width");
    // 表头与数据行共用同一组轨道：第 5 条（操作）轨道的右边界必须重合
    const alignment = await page.evaluate(() => ({
      headRight: document.querySelector(".columns-head > *:last-child")!.getBoundingClientRect().right,
      rowRight: document.querySelector(".columns .column-row")!.lastElementChild!.getBoundingClientRect().right,
    }));
    expect(Math.abs(alignment.headRight - alignment.rowRight), "操作轨道表头与数据行右边界对齐").toBeLessThanOrEqual(1);
  });
});

// —— Task 12 用户验收修复轮：.modal-actions 公共悬停契约（原生按钮路径）——
test("用户验收修复轮：另存为模板弹窗原生按钮悬停抬升、禁用无误导反馈且操作区有 16px 间距", async ({page}) => {
  await openCatalog(page);
  await page.getByRole("button", {name: "另存为"}).click();
  const dialog = page.getByRole("dialog", {name: "另存为模板"});
  await expect(dialog).toBeVisible();
  const actions = dialog.locator(".modal-actions");
  const cancel = actions.locator("button").first();
  const confirm = actions.locator("button").last();

  // 输入为空时确认按钮禁用：悬停不得出现抬升阴影等误导性可点反馈
  await expect(confirm).toBeDisabled();
  await confirm.hover();
  expect(await confirm.evaluate((el) => getComputedStyle(el).boxShadow), "禁用按钮无悬停反馈").toBe("none");

  // 可用的取消按钮（原生 button）：悬停出现抬升阴影
  await cancel.hover();
  expect(await cancel.evaluate((el) => getComputedStyle(el).boxShadow), "原生按钮悬停抬升阴影").not.toBe("none");

  // 表单控件（模板名称输入）与按钮区不贴合：可见间隙 ≥16px 且来自 16px 语义档上间距
  const gap = await dialog.evaluate((el) => {
    const control = el.querySelector(".save-as-name")!;
    const bar = el.querySelector(".modal-actions")!;
    return {
      marginTop: parseFloat(getComputedStyle(bar).marginTop),
      visible: bar.getBoundingClientRect().top - control.getBoundingClientRect().bottom,
    };
  });
  expect(gap.marginTop, "操作区上间距取 16px 语义档").toBe(16);
  expect(gap.visible, "表单控件与按钮区可见间隙").toBeGreaterThanOrEqual(16);
});

// PLAN-DM-043 Task 4：图纸目录预览表普通格 44px 档 + 单档令牌化 padding + 显式中部对齐。
// 列值由用户模板决定、不做类型推断，因此这里只收口基础格规则，不计数值对齐。
test("目录预览表：44px 档、单档令牌化 padding 与显式中部对齐", async ({page}) => {
  await openCatalog(page);
  const table = page.getByTestId("catalog-preview-table");
  const head = table.locator("thead th").first();
  const cell = table.locator("tbody td").first();
  await expect(head, "预览表先有表头").toBeVisible();
  await expect(cell, "预览表先有数据行").toBeVisible();
  expect(Math.round(await head.evaluate((element) => element.getBoundingClientRect().height)), "表头与同表普通行同档").toBe(44);
  expect(Math.round(await cell.evaluate((element) => element.getBoundingClientRect().height)), "普通行消费 44px 基础档").toBe(44);
  for (const side of ["padding-top", "padding-right", "padding-bottom", "padding-left"]) {
    await expect(head, side).toHaveCSS(side, "4px");
    await expect(cell, side).toHaveCSS(side, "4px");
  }
  await expect(head).toHaveCSS("vertical-align", "middle");
  await expect(cell).toHaveCSS("vertical-align", "middle");
});
