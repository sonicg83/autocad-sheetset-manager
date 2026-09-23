// 标准分区编辑器 e2e（PLAN-DM-038 Task 9 / SPEC-DM-017 §2–§7）。
// 覆盖：六分区单向流程（普通属性 → 映射 → 组合 → DWG 命名）、枚举改名保留映射、
// 枚举排序与取消不落盘、界面不暴露稳定内部 ID、全局跨作用域重名、引用删除阻断、
// 映射源唯一占用、组合/DWG 命名字段范围、未完成草稿可保存但不可发布、
// 发布 error 与 warning 区分、DWG 非法文件名、紧凑复选框、
// 900×768 与 200% 缩放下的模态操作栏可达，以及纯键盘令牌插入与模态焦点归还。
import {expect, test, type Page} from "@playwright/test";
import {installPreferenceSnapshot} from "./fixtures/settings";
import {
  draft,
  draftDocument,
  editorSaveState,
  installStandards,
  libraryItems,
  openDraftEditor,
  openEditorSection,
  openStandards,
  partialMappingDraft,
} from "./fixtures/standards";

test.beforeEach(async ({page}) => {
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => (window as any).__fakeSelectResult ?? null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
});

async function expectNoPageHScroll(page: Page, label: string): Promise<void> {
  const metrics = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    win: window.innerWidth,
  }));
  expect(metrics.doc, `${label}：html 无横向溢出`).toBeLessThanOrEqual(metrics.win);
  expect(metrics.body, `${label}：body 无横向溢出`).toBeLessThanOrEqual(metrics.win);
}

/** 操作按钮完整落在视口内（不因缩放被裁切或推出视口）。 */
async function expectActionsReachable(page: Page, names: string[]): Promise<void> {
  const viewport = page.viewportSize()!;
  for (const name of names) {
    const button = page.getByRole("button", {name});
    await expect(button).toBeVisible();
    const box = await button.boundingBox();
    expect(box, `${name} 应有布局盒`).not.toBeNull();
    expect(box!.y, `${name} 顶部在视口内`).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height, `${name} 底部在视口内`).toBeLessThanOrEqual(viewport.height + 1);
  }
}

async function saveDraftDocument(page: Page): Promise<void> {
  await page.getByRole("button", {name: "保存草稿"}).click();
  await expect(editorSaveState(page)).toHaveText("已保存");
}

/** 把界面语言与主题切到指定值：**不写全局共享的 settings.json**，改用 page 级请求拦截
 * （与 `main.spec.ts` 英文节、`standards-visual-evidence.spec.ts` 同型）——本 spec 在并行 project
 * 中运行，写共享配置会让并发 worker 拉到错误的语言/主题。 */
async function installLocale(page: Page, theme: "light" | "dark" = "light", locale: "zh-CN" | "en-US" = "zh-CN"): Promise<void> {
  await installPreferenceSnapshot(page, theme, "2020", locale);
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", locale);
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

test("普通属性到映射、组合和 DWG 命名形成单向流程", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);

  await expect(page.getByTestId("standard-section-nav").getByRole("button")).toHaveText([
    "1基本信息", "2普通属性1", "3派生属性2", "4DWG 命名1", "5模板资产", "6版本与发布",
  ]);

  // 枚举改名：稳定 ID 不变，映射按 enum_item_id 保留目标并进入待确认
  await openEditorSection(page, "ordinary");
  await page.getByTestId("edit-enum-prop-major").click();
  await expect(page.getByTestId("enum-dialog").getByText("编辑枚举值")).toBeVisible();
  await page.getByTestId("enum-value-enum-gas").fill("城镇燃气");
  await page.getByTestId("save-enum").click();
  await expect(page.getByTestId("enum-dialog")).toHaveCount(0);

  await openEditorSection(page, "derived");
  await expect(page.getByTestId("derived-source-prop-code")).toContainText("待确认");
  await page.getByTestId("edit-derived-prop-code").click();
  await expect(page.getByTestId("mapping-status")).toContainText("枚举已变化");
  await page.getByTestId("mapping-target-enum-gas").fill("RQ");
  await page.getByTestId("confirm-mapping").click();
  await expect(page.getByTestId("derived-source-prop-code")).not.toContainText("待确认");

  // DWG 命名：示例预览明确标注，扩展名在编辑框外固定追加
  await openEditorSection(page, "dwgNaming");
  await expect(page.getByTestId("token-preview")).toHaveText("RQ-001-003 示例子集.dwg");
  await expect(page.getByTestId("token-preview-state")).toHaveText("示例");
  await expect(page.getByTestId("naming-extension-note")).toContainText(".dwg");
  await expect(page.getByTestId("naming-uniqueness-warning")).toHaveCount(0);
});

test("草稿编辑器替换标准库主从分栏并在返回后恢复选择", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  // 互斥页面状态：编辑器在场时标准库与标准详情都不在 DOM 中（不只是 CSS 隐藏）
  await expect(page.getByTestId("standards-editor-mode")).toBeVisible();
  await expect(page.getByRole("region", {name: "标准库"})).toHaveCount(0);
  await expect(page.getByRole("region", {name: "标准详情"})).toHaveCount(0);
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();

  await page.getByRole("button", {name: "返回标准库"}).click();
  await expect(page.getByRole("region", {name: "标准库"})).toBeVisible();
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toHaveCount(0);
  await expect(page.getByRole("region", {name: "标准详情"})).toContainText("草稿 1");
});

test("未保存修改时返回标准库走三选一门禁且留在此处不丢输入", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByLabel("标准名称").fill("待确认名称");

  await page.getByRole("button", {name: "返回标准库"}).click();
  const gate = page.locator("dialog[open]");
  await expect(gate).toContainText("有未保存的修改");
  await gate.getByRole("button", {name: "留在此处"}).click();
  // 留在编辑器：仍是互斥编辑模式，输入不丢
  await expect(page.getByTestId("standards-editor-mode")).toBeVisible();
  await expect(page.getByLabel("标准名称")).toHaveValue("待确认名称");
});

test("编辑器工作台独立占满标准页内容宽度", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  const metrics = await page.getByTestId("standards-editor-workspace").evaluate(element => {
    const box = element.getBoundingClientRect();
    return {width: box.width, columns: getComputedStyle(element).gridTemplateColumns};
  });
  // 独立全宽工作台：不再被旧 library-split 的右栏压窄（旧右栏约 800px）
  expect(metrics.width).toBeGreaterThan(1100);
  expect(metrics.columns.split(" ")).toHaveLength(2);
  const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(pageWidth).toBeLessThanOrEqual(1440);
});

test("属性表单元格不再重复列标题标签", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  // 列标题已由表头表达；单元格内再渲染可见字段标签会与表头重复、把行撑高并错位（对照 SPEC-DM-017 Demo）
  await openEditorSection(page, "ordinary");
  const ordinaryLabel = page.getByTestId("ordinary-table").locator("label");
  // 每个单元格输入框保留标签（可访问名与表头一致），但标签视觉隐藏、不再占据行内高度
  expect(await ordinaryLabel.count()).toBeGreaterThan(0);
  await expect(ordinaryLabel.first()).toBeHidden();
  // 可访问名仍必须存在（不能因为隐藏可见标签而丢失字段名）
  await expect(page.getByTestId("ordinary-name-prop-major")).toHaveAttribute("aria-label", "属性名");

  await openEditorSection(page, "derived");
  const derivedLabel = page.getByTestId("derived-table").locator("label");
  expect(await derivedLabel.count()).toBeGreaterThan(0);
  await expect(derivedLabel.first()).toBeHidden();
});

test("900×768 派生属性行不因隐藏说明列而换行", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "derived");

  // 隐藏说明列必须隐藏整个网格项：UiInput 把 data-testid 透传到内层 input，
  // 只隐藏 input 会让外层 .ui-input 仍占一列，把最后的删除动作挤到第二行。
  const row = page.getByTestId("derived-table").locator(".derived-row:not(.derived-head)").first();
  const nameBox = (await row.getByTestId("derived-name-prop-code").boundingBox())!;
  const removeBox = (await row.getByTestId("derived-remove-prop-code").boundingBox())!;
  expect(Math.abs(removeBox.y - nameBox.y), "删除动作必须与属性名在同一行").toBeLessThan(nameBox.height);
  // 行内实际参与布局的子项数必须与声明的列数一致（否则网格自动放置会换行）
  const inFlow = await row.evaluate(element => {
    const columns = getComputedStyle(element).gridTemplateColumns.split(" ").length;
    const items = [...element.children].filter(child => getComputedStyle(child).display !== "none").length;
    return {columns, items};
  });
  expect(inFlow.items, "行内子项数与网格列数一致").toBe(inFlow.columns);
});

test("宽视口下编辑工作台宽度受内容上限约束", async ({page}) => {
  await page.setViewportSize({width: 2560, height: 1440});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  // 编辑器不得因宽屏被无限拉宽：宽度上限与标准库模式一致（取壳层内容宽令牌）
  const cap = await page.evaluate(() => {
    const probe = document.createElement("span");
    probe.style.maxWidth = "var(--shell-content-max-width)";
    document.body.append(probe);
    const value = getComputedStyle(probe).maxWidth;
    probe.remove();
    return Number.parseFloat(value);
  });
  const width = await page.locator(".standards-page").evaluate(element => element.getBoundingClientRect().width);
  expect(width).toBeLessThanOrEqual(cap + 1);
  await expectNoPageHScroll(page, "2560×1440 编辑器");
});

test("枚举单元格是摘要即触发器而不是独立按钮", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "ordinary");

  // SPEC-DM-017 编辑器 Demo：枚举值摘要本身可点即进入编辑对话框，没有额外的「编辑枚举值」按钮
  const trigger = page.getByTestId("edit-enum-prop-major");
  await expect(trigger).toHaveRole("button");
  await expect(trigger).toContainText("燃气");
  // WCAG 2.5.3：可访问名必须包含可见摘要文本（不能用动作名覆盖它）
  await expect(trigger).toHaveAccessibleName(/燃气/);
  // 摘要仍在同一按钮内（不能从触发器里拆出去变成兄弟节点）
  await expect(trigger.getByTestId("enum-summary-prop-major")).toHaveCount(1);

  // 文本属性的禁用占位与「不出现触发器」由单元测试 `OrdinaryPropertyEditor.test.ts` 覆盖（本夹具无文本属性）

  // 点击摘要即打开枚举编辑对话框
  await trigger.click();
  await expect(page.getByTestId("enum-dialog")).toBeVisible();
});

test("枚举排序与取消不落盘", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "ordinary");

  // 取消：本轮增删改排序全部丢弃，草稿回到 clean
  await page.getByTestId("edit-enum-prop-major").click();
  await page.getByTestId("enum-down-enum-gas").click();
  await page.getByTestId("add-enum").click();
  await page.getByTestId("cancel-enum").click();
  await expect(editorSaveState(page)).toHaveText("已保存");
  expect(state.saveBodies).toHaveLength(0);

  // 保存：一次性提交排序结果
  await page.getByTestId("edit-enum-prop-major").click();
  await page.getByTestId("enum-down-enum-gas").click();
  await page.getByTestId("save-enum").click();
  await expect(editorSaveState(page)).toHaveText("有未保存修改");
  await saveDraftDocument(page);

  const saved = state.saveBodies[0] as {
    properties: Array<{property_id: string; enum_items: Array<{item_id: string; value: string}>}>;
  };
  const major = saved.properties.find(item => item.property_id === "prop-major")!;
  expect(major.enum_items.map(item => item.item_id)).toEqual(["enum-jz", "enum-gas", "enum-jg"]);
});

test("界面不暴露稳定内部 ID", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);

  await openEditorSection(page, "ordinary");
  await page.getByTestId("edit-enum-prop-major").click();
  await expect(page.getByTestId("enum-dialog")).not.toContainText("enum-gas");
  await expect(page.getByTestId("enum-dialog")).toContainText("01");
  await page.getByTestId("cancel-enum").click();

  await openEditorSection(page, "derived");
  await page.getByTestId("edit-derived-prop-code").click();
  await expect(page.getByTestId("mapping-dialog")).not.toContainText("enum-gas");
  await expect(page.getByTestId("mapping-dialog")).toContainText("燃气");
  await page.getByTestId("cancel-mapping").click();
});

test("全局跨作用域重名进入发布门禁", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "ordinary");

  await page.getByTestId("add-ordinary").click();
  const rows = page.locator("[data-testid=ordinary-table] tbody tr");
  const lastRow = rows.last();
  await lastRow.getByLabel("属性名").fill(" 专业 ");
  await lastRow.getByLabel("作用域").selectOption("sheet");

  // 结构门禁放行（草稿可保存），发布门禁给 error
  await expect(editorSaveState(page)).toHaveText("有未保存修改");
  await expect(page.getByTestId("ordinary-issue-prop-new")).toContainText("命名空间");
  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByTestId("publish-review")).toContainText("属性名与当前或历史名称冲突");
  await expect(page.getByRole("button", {name: "发布标准"})).toBeDisabled();
});

test("删除被引用的属性被阻断并列出引用方", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "ordinary");

  await page.getByTestId("ordinary-remove-prop-major").click();
  await expect(page.getByTestId("ordinary-delete-blocked")).toContainText("专业代码");
  await expect(page.getByTestId("editor-delete-blocked")).toContainText("专业代码");
  await expect(page.getByTestId("ordinary-name-prop-major")).toHaveValue("专业");
  await expect(editorSaveState(page)).toHaveText("已保存");
});

test("映射源唯一占用与组合字段范围", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "derived");

  // 源唯一性：`prop-major` 已被 `prop-code` 占用，新增映射不得再选它
  await page.getByTestId("add-derived").click();
  await page.getByTestId("derived-kind-prop-new").selectOption("mapping");
  await page.getByTestId("edit-derived-prop-new").click();
  await expect(page.getByTestId("mapping-source").locator("option[value=prop-major]")).toHaveCount(0);
  await page.getByTestId("cancel-mapping").click();

  // 组合字段范围：sheetset 组合不能引用系统字段与其它组合属性
  await page.getByTestId("derived-kind-prop-new").selectOption("composition");
  await page.getByTestId("edit-derived-prop-new").click();
  await expect(page.getByTestId("token-field-sheet.number")).toHaveCount(0);
  await expect(page.getByTestId("token-field-subset.scope")).toHaveCount(0);
  await expect(page.getByTestId("token-field-prop-label")).toHaveCount(0);
  await page.getByTestId("cancel-composition").click();

  // DWG 命名：三个 subset 系统字段 + sheetset 属性，sheet 属性与组合属性都不出现
  await openEditorSection(page, "dwgNaming");
  await expect(page.getByTestId("token-field-subset.scope")).toBeVisible();
  await expect(page.getByTestId("token-field-subset.sequence")).toBeVisible();
  await expect(page.getByTestId("token-field-sheet.number")).toHaveCount(0);
});

test("未完成草稿可保存但发布被阻断", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": partialMappingDraft()},
  });
  await openStandards(page);
  await openDraftEditor(page);

  // 结构门禁放行：草稿（含未完成映射）可以保存
  await openEditorSection(page, "derived");
  await expect(page.getByTestId("derived-source-prop-code")).toContainText("待确认");
  await page.getByLabel("标准名称").fill("市政燃气施工图 v2");
  await saveDraftDocument(page);
  expect(state.saveBodies).toHaveLength(1);

  // 发布门禁：空目标阻断
  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByTestId("publish-review")).toContainText("存在没有目标值的枚举项");
  await expect(page.getByRole("button", {name: "发布标准"})).toBeDisabled();
  expect(state.publishCalls).toBe(0);
});

test("发布 error 与 warning 区分并跳回模态框", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {
    drafts: {"draft-1": partialMappingDraft()},
  });
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByRole("button", {name: "发布检查"}).click();

  const jump = page.getByTestId("publish-issue-0");
  await expect(jump).toContainText("派生属性");
  await jump.click();
  // 跳回派生分区并直接打开映射模态框，焦点落在目标输入框
  await expect(page.getByTestId("mapping-dialog")).toBeVisible();
  await expect(page.getByTestId("mapping-target-enum-ps")).toBeFocused();
  await page.getByTestId("mapping-target-enum-ps").fill("GPS");
  await page.getByTestId("confirm-mapping").click();
  await expect(editorSaveState(page)).toHaveText("有未保存修改");
  await saveDraftDocument(page);

  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByTestId("publish-review")).toContainText("未发现阻断问题");
  await expect(page.getByRole("button", {name: "发布标准"})).toBeEnabled();
  expect(state.publishCalls).toBe(0);
});

test("DWG 非法文件名在前端只提示不阻断发布", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "dwgNaming");

  await page.getByTestId("token-clear").click();
  await page.getByTestId("token-literal").fill("图签.dwg");
  await page.getByTestId("token-literal").press("Enter");
  // 文件名风险是 warning 提示（取值层面的校验以后端发布/渲染为准），不是阻断性 error
  await expect(page.getByTestId("naming-risk-warning")).toBeVisible();
  await expect(page.getByTestId("naming-uniqueness-warning")).toBeVisible();
  await expect(page.getByTestId("naming-error")).toHaveCount(0);

  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByTestId("publish-review")).toContainText("模板不得自行包含 .dwg 扩展名");
  await expect(page.getByRole("button", {name: "发布标准"})).toBeEnabled();

  // 恢复默认模板后风险消失
  await page.getByRole("button", {name: "返回编辑"}).click();
  await openEditorSection(page, "dwgNaming");
  // 恢复默认模板：不带隐式前缀，风险消失
  await page.getByTestId("reset-naming").click();
  await expect(page.getByTestId("naming-risk-warning")).toHaveCount(0);
  await expect(page.getByTestId("naming-error")).toHaveCount(0);
  await expect(page.getByTestId("token-preview")).toHaveText("001-003 示例子集.dwg");
});

test("必填复选框保持紧凑尺寸与更大点击区域", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "ordinary");

  const box = await page.getByTestId("ordinary-required-prop-major").boundingBox();
  expect(box?.width).toBe(16);
  expect(box?.height).toBe(16);
  const hit = await page.locator("label.required-hit").first().boundingBox();
  expect(hit?.width).toBeGreaterThanOrEqual(32);
  expect(hit?.height).toBeGreaterThanOrEqual(32);
});

test("900×768 编辑工作台保留侧栏且宽表只在自身滚动", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "ordinary");
  // 900px 仍保留侧栏 + 内容双列（SPEC-DM-017 Demo 的 1050px 档）；780px 以下才堆叠
  const columns = await page.getByTestId("standards-editor-workspace").evaluate(
    element => getComputedStyle(element).gridTemplateColumns.split(" "),
  );
  expect(columns).toHaveLength(2);
  await expectNoPageHScroll(page, "900×768 普通属性");
  // 页面不横向滚动 ≠ 表格不滚动：宽表在自身容器内滚动，保持可读的最小宽度
  const table = page.getByTestId("ordinary-table-scroll");
  await expect(table).toBeVisible();
  const overflow = await table.evaluate(element => element.scrollWidth > element.clientWidth);
  expect(overflow).toBe(true);
});

test("900×768 下英文与深色主题主要动作仍可见且无溢出", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  // 语言与主题在挂载前由快照决定：先装 page 级 /api/settings 拦截再 goto
  await installLocale(page, "dark", "en-US");
  await page.getByRole("button", {name: "Manage drawing standards"}).click();
  await libraryItems(page).first().click();
  await page.getByRole("button", {name: "Edit"}).click();
  await expect(page.getByRole("region", {name: "Standard draft editor"})).toBeVisible();

  // 只断言可见性、可达性与无溢出，不以固定文本像素宽度制造平台脆弱测试
  await expectActionsReachable(page, ["Save draft", "Publish check", "Back to standard library"]);
  await expectNoPageHScroll(page, "900×768 英文深色编辑器");
  await page.getByTestId("editor-section-dwgNaming").click();
  await expect(page.getByTestId("token-preview")).toContainText("RQ-001-003");
  await expectNoPageHScroll(page, "900×768 英文深色 DWG 命名");
});

test("200% 缩放下欢迎页、编辑器正文与发布检查页无页面级横向溢出", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await page.goto("/");
  // 1440×900 下浏览器 200% 缩放 = CSS 视口 720×450 + 2x 渲染（与 i18n 证据同一口径）
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {width: 720, height: 450, deviceScaleFactor: 2, mobile: false});
  await expect(page.getByTestId("welcome-layout")).toBeVisible();
  await expectNoPageHScroll(page, "200% 欢迎页");

  await page.getByRole("button", {name: "管理图纸标准"}).click();
  await libraryItems(page).first().click();
  await page.getByRole("button", {name: "编辑"}).click();
  await expect(page.getByTestId("standards-editor-workspace")).toBeVisible();
  await expectNoPageHScroll(page, "200% 编辑器正文");
  await page.getByRole("button", {name: "发布检查"}).click();
  await expect(page.getByTestId("publish-review")).toBeVisible();
  await expectNoPageHScroll(page, "200% 发布检查页");
});

test("900×768 下模态操作栏可见且无横向溢出", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "ordinary");
  await page.getByTestId("edit-enum-prop-major").click();
  await expect(page.getByTestId("enum-dialog")).toBeVisible();
  await expectActionsReachable(page, ["取消", "保存枚举值"]);
  await expectNoPageHScroll(page, "900×768 枚举模态");
  await page.getByTestId("cancel-enum").click();

  await openEditorSection(page, "derived");
  await page.getByTestId("edit-derived-prop-label").click();
  await expect(page.getByTestId("composition-dialog")).toBeVisible();
  await expectActionsReachable(page, ["取消", "保存组合"]);
  await expectNoPageHScroll(page, "900×768 组合模态");
});

test("200% 缩放下组合模态操作栏可达", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  // 1440×900 下浏览器 200% 缩放 = CSS 视口 720×450 + 2x 渲染（与 i18n 证据同一口径）
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setDeviceMetricsOverride", {width: 720, height: 450, deviceScaleFactor: 2, mobile: false});
  await openEditorSection(page, "derived");
  await page.getByTestId("edit-derived-prop-label").click();
  await expect(page.getByTestId("composition-dialog")).toBeVisible();
  await expectActionsReachable(page, ["取消", "保存组合"]);
  await expectNoPageHScroll(page, "200% 组合模态");
});

test("纯键盘插入令牌并在关闭后归还焦点", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await openEditorSection(page, "derived");

  const opener = page.getByTestId("edit-derived-prop-label");
  await opener.click();
  await expect(page.getByTestId("composition-dialog")).toBeVisible();
  // 纯键盘：聚焦字段按钮后回车插入令牌
  await page.getByTestId("token-field-prop-code").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("token-3")).toContainText("专业代码");
  // 退格按令牌整体删除（光标在末尾）
  await page.getByTestId("token-literal").focus();
  await page.keyboard.press("Backspace");
  await expect(page.getByTestId("token-3")).toHaveCount(0);
  // 关闭归还焦点给触发按钮
  await page.getByTestId("cancel-composition").click();
  await expect(page.getByTestId("composition-dialog")).toHaveCount(0);
  await expect(opener).toBeFocused();
});

test("保存失败保留输入与 dirty 状态并可重试成功", async ({page}) => {
  const state = await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  state.saveFailure = {status: 500, code: "INTERNAL_ERROR", message: "服务端暂时不可用"};
  await openStandards(page);
  await openDraftEditor(page);

  const nameInput = page.getByLabel("标准名称");
  await nameInput.fill("失败的名称");
  await page.getByRole("button", {name: "保存草稿"}).click();
  await expect(page.getByTestId("editor-save-error")).toBeVisible();
  await expect(nameInput).toHaveValue("失败的名称");
  await expect(editorSaveState(page)).toHaveText("有未保存修改");

  state.saveFailure = null;
  await page.getByRole("button", {name: "保存草稿"}).click();
  await expect(editorSaveState(page)).toHaveText("已保存");
  expect(state.saveBodies).toHaveLength(2);
});

test("未保存修改离开编辑器走三选一门禁", async ({page}) => {
  await installStandards(page, [draft("草稿 1", "draft-1")], {drafts: {"draft-1": draftDocument()}});
  await openStandards(page);
  await openDraftEditor(page);
  await page.getByLabel("标准名称").fill("待确认名称");

  await page.getByRole("button", {name: "返回标准库"}).click();
  const gate = page.locator("dialog[open]");
  await expect(gate).toContainText("有未保存的修改");
  await gate.getByRole("button", {name: "留在此处"}).click();
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toBeVisible();
  await expect(page.getByLabel("标准名称")).toHaveValue("待确认名称");

  await page.getByRole("button", {name: "返回标准库"}).click();
  await page.locator("dialog[open]").getByRole("button", {name: "放弃输入"}).click();
  await expect(page.getByRole("region", {name: "标准草稿编辑器"})).toHaveCount(0);
  await expect(page.getByRole("region", {name: "标准详情"})).toBeVisible();
});
