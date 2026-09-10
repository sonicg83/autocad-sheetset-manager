// 图纸目录页面、模板编辑与导出交互 e2e（PLAN-DM-020 Task 11 / SPEC-DM-012 §3/§7/§10/§11）。
// 覆盖三类场景：核心流程（默认模板/预览/字段插入/缺定义/缺值/空集）、模板状态
// （内置不可改/保存/另存/删除/大小写冲突/上限/不兼容/偏好/三选一保护/冲突恢复）、
// 导出状态（无壳/取消/旧预览/成功/漂移/授权失效/写失败）。全部为语义断言，
// 工作区/设置/动作路由经 fixtures/sheetCatalog.ts 模拟。
import {expect, test, type Page} from "@playwright/test";
import {
  EXTENSION_ID, fakeUuid, installSheetCatalogFixture, openCatalogPage, readBridgeCalls,
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
    await expect(browser.getByRole("button", {name: "number", exact: true})).toBeVisible();
    await expect(browser.getByRole("button", {name: "设计院", exact: true})).toBeVisible();
    await expect(browser.getByRole("button", {name: "专业代码", exact: true})).toBeVisible();
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
    await browser.getByRole("button", {name: "number", exact: true}).click();
    await expect(expression).toHaveValue("RQ-{sheet.number}{sheet.title}");
    // 特殊名称（含空格）必须插入方括号 JSON 字符串形式：先添加一个空列再插入
    await page.getByRole("button", {name: "添加列"}).click();
    await page.getByLabel("表达式 4").click();
    await browser.getByRole("button", {name: "项目 名称", exact: true}).click();
    await expect(page.getByLabel("表达式 4")).toHaveValue('{sheetset["项目 名称"]}');
  });

  test("组合表达式生成 RQ-001 形态的求值结果", async ({page}) => {
    await openCatalog(page);
    const expression = page.getByLabel("表达式 1");
    await expression.fill("RQ-");
    await page.getByRole("region", {name: "字段浏览器"}).getByRole("button", {name: "number", exact: true}).click();
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
  // PLAN-DM-022：目录页三选一已改为原生 <dialog showModal>，会自行进入 top layer 叠在
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
