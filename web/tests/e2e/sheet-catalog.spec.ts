// 图纸目录页面、模板编辑与导出交互 e2e（PLAN-DM-020 Task 11 / SPEC-DM-012 §3/§7/§10/§11）。
// 覆盖三类场景：核心流程（默认模板/预览/字段插入/缺定义/缺值/空集）、模板状态
// （内置不可改/保存/另存/删除/大小写冲突/上限/不兼容/偏好/三选一保护/冲突恢复）、
// 导出状态（无壳/取消/旧预览/成功/漂移/授权失效/写失败）。全部为语义断言，
// 工作区/设置/动作路由经 fixtures/sheetCatalog.ts 模拟。
import {expect, test, type Page} from "@playwright/test";
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
    // 执行请求契约：重复提交模板快照 + 预览摘要 + 保存授权
    const execute = state.executeRequests[0];
    expect(execute.workspace_id).toBe("workspace-1");
    expect(execute.base_revision_id).toBe("revision-1");
    expect(execute.preview_digest).toBe(state.lastDigest);
    expect(execute.save_grant_id).toBe("grant-e2e");
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
