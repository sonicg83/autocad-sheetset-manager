// PLAN-DM-016 任务 7：属性页视觉基线（令牌来源、密度、同行对齐）与同状态证据采集。
// 断言（浅/深主题）：卡片表面、弱化表头、语义边框、焦点环、禁用态、错误与状态徽标色
// 全部解析自已定义 CSS 变量（与 :root / html[data-theme=dark] 解析值逐一比对）；
// 输入/选择器 38px、按钮 ≥36px 普通档、图标按钮 ≥36×36（属性页当前无图标按钮，若引入必须满足下限）、
// 同行控件垂直居中对齐。本 spec 的截图仅作为 testInfo 附件（{状态}-{宽}x{高}-{主题}.png，见 attachScreenshot）；
// 入库的同状态 Demo/生产对比图由验收时按相同视口、主题和状态显式复制附件到
// .planning/memos/dst-manager/assets/PLAN-DM-016/（demo 侧由临时采集脚本生成，脚本不进入提交树），
// 只使用 properties.ts 虚构夹具，不读取用户截图、真实工程或 sample/。
//
// PLAN-DM-029 任务 5 增补：属性页的控件视觉基础（字号档、控件高度、结构尺寸）必须由语义/组件令牌解析。
// 期望值不硬编码 px，而是在真实渲染文档里用探针元素从令牌解析后比对（`tokenReference`），
// 避免断言与令牌漂移；覆盖折叠标题与计数、折叠图标、查询/搜索可见 label、主次动作按钮档、
// 定义表行高、CSV 面板、值面板工具行与字段、以及两个模态的标题与结构尺寸。
import {expect, test, type Locator, type Page, type TestInfo} from "@playwright/test";
import {installPropertiesFixture, openProperties, pendingDraft} from "./fixtures/properties";

const THEMES = ["light", "dark"] as const;

async function openWorkspace(page: Page, theme?: "light" | "dark") {
  await installPropertiesFixture(page, {theme});
  await openProperties(page);
  await page.getByRole("button", {name: "展开属性字段定义"}).click();
}

// 解析 CSS 变量在当前主题下的实际颜色值（经探针元素取 computed color）
async function tokenColor(page: Page, token: string): Promise<string> {
  return page.evaluate((name) => {
    const probe = document.createElement("span");
    probe.style.color = `var(${name})`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  }, token);
}

// 断言元素计算样式等于指定令牌的解析值（不只靠截图目测）
async function expectToken(page: Page, selector: string, property: string, token: string) {
  const expected = await tokenColor(page, token);
  const actual = await page.locator(selector).first().evaluate((el, prop) => getComputedStyle(el)[prop as "color"], property);
  expect(actual, `${selector} ${property} 应来自 ${token}`).toBe(expected);
}

// 解析字体族令牌在当前环境下的 computed font-family（与 tokenColor 同思想：不把字体栈写死）
async function tokenFontFamily(page: Page, token: string): Promise<string> {
  return page.evaluate((name) => {
    const probe = document.createElement("span");
    probe.style.fontFamily = `var(${name})`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).fontFamily;
    probe.remove();
    return value;
  }, token);
}

// 断言元素的计算字体族等于指定令牌的解析值（接受 Locator 或选择器字符串，与 expectTokenValue 一致）
async function expectTokenFontFamily(page: Page, target: Locator | string, token: string) {
  const expected = await tokenFontFamily(page, token);
  const locator = typeof target === "string" ? page.locator(target) : target;
  const actual = await locator.first().evaluate((el) => getComputedStyle(el).fontFamily);
  expect(actual, `${typeof target === "string" ? target : target.toString()} font-family 应来自 ${token}`).toBe(expected);
}

// 读数值型自定义属性（如 `--line-height-body:1.5`）
async function tokenNumber(page: Page, token: string): Promise<number> {
  const raw = await page.evaluate((name) => getComputedStyle(document.documentElement).getPropertyValue(name), token);
  return parseFloat(raw);
}

// 行高断言：行高当前没有令牌层（收口责任 N），这里只锁定既有排版节奏。
// 未自行声明行高的元素沿 `reset.css:15` 的 `html{font:var(--font-body) var(--font-ui)}`（即 14px/1.5）
// 继承无单位行高，故「计算行高 ÷ 本元素字号」应等于 `--line-height-body`；
// 断言比值而非像素，既不硬编码 px，也不随字号档位漂移。
async function expectLineHeightRatio(page: Page, target: Locator, ratio: number, label: string) {
  const actual = await target.first().evaluate((el) => {
    const cs = getComputedStyle(el);
    // `line-height:normal` 依赖字体度量，比不出稳定比值：显式暴露为 NaN 让断言失败而不是静默通过
    return cs.lineHeight === "normal" ? Number.NaN : parseFloat(cs.lineHeight) / parseFloat(cs.fontSize);
  });
  expect(round2(actual), `${label} 计算行高与字号的比值`).toBe(ratio);
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

// 在真实文档里解析令牌数值：`computed` 走计算样式（字号、最小高度等），`box` 走实际盒尺寸
// （宽度、高度：边框盒下计算样式的 width/height 会被换算成内容盒，不能直接比令牌）。
async function tokenReference(page: Page, token: string, property: string, mode: "computed" | "box"): Promise<number> {
  return page.evaluate(({name, prop, kind}) => {
    const probe = document.createElement("div");
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    probe.style.display = "block";
    probe.style.setProperty(prop, `var(${name})`);
    document.body.appendChild(probe);
    const raw = kind === "computed"
      ? parseFloat(getComputedStyle(probe).getPropertyValue(prop))
      : Number(probe.getBoundingClientRect()[prop as "width" | "height"]);
    probe.remove();
    return raw;
  }, {name: token, prop: property, kind: mode});
}

// 断言目标的数值（计算样式或实际盒尺寸）等于令牌解析值
async function expectTokenValue(
  page: Page, target: Locator, property: string, token: string, mode: "computed" | "box" = "computed",
) {
  const expected = round2(await tokenReference(page, token, property, mode));
  const actual = round2(mode === "computed"
    ? parseFloat(await target.first().evaluate((el, prop) => getComputedStyle(el).getPropertyValue(prop), property))
    : await target.first().evaluate((el, prop) => Number(el.getBoundingClientRect()[prop as "width" | "height"]), property));
  expect(actual, `${property} 应来自 ${token}`).toBe(expected);
}

async function attachScreenshot(page: Page, info: TestInfo, state: string, theme: string) {
  const viewport = page.viewportSize()!;
  const name = `${state}-${viewport.width}x${viewport.height}-${theme}.png`;
  const path = info.outputPath(name);
  await page.screenshot({path, animations: "disabled"});
  await info.attach(name, {path, contentType: "image/png"});
}

for (const theme of THEMES) {
  test(`表面、弱化表头、语义边框与文字层级色来自已定义 CSS 变量：${theme}`, async ({page}) => {
    await openWorkspace(page, theme);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expectToken(page, ".value-panel", "backgroundColor", "--color-bg-surface");
    await expectToken(page, ".definition-panel", "backgroundColor", "--color-bg-surface");
    await expectToken(page, ".csv-panel", "backgroundColor", "--color-bg-surface");
    await expectToken(page, ".value-panel", "borderTopColor", "--color-border-subtle");
    await expectToken(page, ".definition-panel", "borderTopColor", "--color-border-subtle");
    await expectToken(page, ".definition-panel thead th", "backgroundColor", "--color-bg-muted");
    await expectToken(page, ".definition-panel thead th", "color", "--color-text-secondary");
    await expectToken(page, ".csv-panel .head-status", "color", "--color-text-muted");
    await expectToken(page, ".value-panel .panel-head", "borderBottomColor", "--color-border-subtle");
  });

  test(`焦点环来自焦点令牌、禁用态统一降级：${theme}`, async ({page}) => {
    await openWorkspace(page, theme);
    // 先用键盘建立键盘焦点上下文，再聚焦主按钮，使 :focus-visible 生效
    await page.keyboard.press("Tab");
    const focus = await page.getByRole("button", {name: "新增字段"}).evaluate((el) => {
      el.focus();
      const computed = getComputedStyle(el);
      return {visible: el.matches(":focus-visible"), color: computed.outlineColor, width: computed.outlineWidth, style: computed.outlineStyle};
    });
    expect(focus.visible, "键盘聚焦命中 :focus-visible").toBe(true);
    expect(focus.style).toBe("solid");
    expect(focus.width).toBe("2px");
    expect(focus.color, "焦点环颜色 = --color-focus").toBe(await tokenColor(page, "--color-focus"));
    // 禁用分页按钮：统一不透明降级、不可点击（禁用不依赖颜色重绘）
    const disabled = await page.locator(".definition-panel .pager button").first().evaluate((el) => {
      const computed = getComputedStyle(el);
      return {isDisabled: (el as HTMLButtonElement).disabled, opacity: computed.opacity, cursor: computed.cursor};
    });
    expect(disabled.isDisabled).toBe(true);
    expect(disabled.opacity).toBe("0.5");
    expect(disabled.cursor).toBe("not-allowed");
  });

  test(`状态徽标与错误色来自已定义 CSS 变量：${theme}`, async ({page}) => {
    await installPropertiesFixture(page, {
      theme,
      initialDraft: pendingDraft(),
      failDraftSave: () => ({code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {项目编号: "演示校验错误"}}),
    });
    await openProperties(page);
    await page.getByRole("textbox", {name: "属性 设计阶段"}).fill("初步设计");
    await page.getByRole("button", {name: "更新图纸集"}).click();
    // 虚构 code 不在错误目录（I18N-11）：摘要显示本地化未知摘要，兼容原文不进主提示
    await expect(page.locator(".error-summary")).toContainText("操作失败，发生未知错误");
    await expect(page.locator(".value-panel .flag.pending").first()).toBeVisible();
    await expect(page.locator(".value-panel .flag.dirty").first()).toBeVisible();
    await expect(page.locator(".value-panel .flag.error").first()).toBeVisible();
    await expectToken(page, ".value-panel .flag.dirty", "color", "--color-warning");
    await expectToken(page, ".value-panel .flag.dirty", "backgroundColor", "--color-warning-bg");
    await expectToken(page, ".value-panel .flag.pending", "color", "--color-info");
    await expectToken(page, ".value-panel .flag.pending", "backgroundColor", "--color-info-bg");
    await expectToken(page, ".value-panel .flag.error", "color", "--color-danger");
    await expectToken(page, ".value-panel .flag.error", "backgroundColor", "--color-danger-bg");
    await expectToken(page, ".value-panel .field-error", "color", "--color-danger");
    await expectToken(page, ".value-panel .value-item.invalid input", "borderTopColor", "--color-danger");
    // Ruling 35：错误态（持久语义态）必须优先于 hover（瞬时可供性反馈）。原语的
    // `.ui-input:not(.ui-input--invalid) .ui-input__control:hover:not(:disabled)` 把无效控件排除在
    // 悬停强调之外，所以悬停无效字段时描边**仍为危险色**。源文本断言看不见「声明写了但被更高特异度
    // 压掉」，只有真实 hover 后的计算样式能看见，故这里必须真的 hover。
    const invalidInput = page.locator(".value-panel .value-item.invalid input").first();
    // 守卫的前提：被 hover 的规则含 `:not(:disabled)`。若控件是 disabled，修正前后都会显示危险色，
    // 本条会**假绿**并失去证明力，故必须显式断言可交互。
    await expect(invalidInput, "hover 守卫的前提：无效字段控件必须处于可交互状态").toBeEnabled();
    await invalidInput.hover();
    await expectToken(page, ".value-panel .value-item.invalid input", "borderTopColor", "--color-danger");
    await expectToken(page, ".value-panel .value-item.invalid", "backgroundColor", "--color-danger-bg");
    await expectToken(page, ".error-summary", "borderTopColor", "--color-danger");
    await expectToken(page, ".error-summary", "backgroundColor", "--color-danger-bg");
  });

  test(`密度与同行对齐基线（38px 输入 / ≥36px 按钮 / 图标按钮 ≥36×36）：${theme}`, async ({page}) => {
    await installPropertiesFixture(page, {theme});
    await openProperties(page);
    await page.getByRole("button", {name: "展开属性字段定义"}).click();
    await page.getByRole("button", {name: "新增字段"}).click();
    // 文本输入与选择器统一 38px（checkbox/file 不在密度档内）
    const inputHeights = await page.locator(
      ".properties-view input[type=\"text\"], .properties-view input[type=\"search\"], .properties-view select",
    ).evaluateAll((elements) => elements.map((el) => el.getBoundingClientRect().height));
    expect(inputHeights.length).toBeGreaterThanOrEqual(10);
    for (const height of inputHeights) expect(height).toBe(38);
    // 普通按钮档 ≥36px；图标按钮（无文字内容的按钮）额外要求 ≥36×36（属性页当前无图标按钮）
    const buttons = await page.locator(".properties-view button:visible").evaluateAll((elements) => elements.map((el) => {
      const rect = el.getBoundingClientRect();
      return {height: rect.height, width: rect.width, iconOnly: el.textContent?.trim() === ""};
    }));
    expect(buttons.length).toBeGreaterThanOrEqual(10);
    for (const button of buttons) {
      expect(button.height).toBeGreaterThanOrEqual(36);
      if (button.iconOnly) {
        expect(button.width, "图标按钮宽 ≥36").toBeGreaterThanOrEqual(36);
        expect(button.height, "图标按钮高 ≥36").toBeGreaterThanOrEqual(36);
      }
    }
    // 同行控件垂直居中对齐：值面板搜索行与定义面板查询行的输入/选择器/按钮中点一致（±1px）
    // 控件已由原语包裹（`UiInput`/`UiSelect` 的根是 span），故按后代取真实控件而非直接子元素；
    // 可见 label 位于控件上方，行内用 flex-end 对齐控件底边，中心差不超过 1px。
    for (const rowSelector of [".value-panel .value-toolbar", ".definition-panel .query-bar"]) {
      const centers = await page.locator(`${rowSelector} input:not([type="checkbox"]):visible, ${rowSelector} select:visible, ${rowSelector} button:visible`).evaluateAll((elements) => elements.map((el) => {
        const rect = el.getBoundingClientRect();
        return rect.top + rect.height / 2;
      }));
      expect(centers.length, `${rowSelector} 存在同行控件`).toBeGreaterThanOrEqual(2);
      for (const center of centers) expect(Math.abs(center - centers[0]), `${rowSelector} 同行垂直对齐`).toBeLessThanOrEqual(1);
    }
  });

  test(`属性页控件视觉基础全部来自语义/组件令牌：${theme}`, async ({page}) => {
    await openWorkspace(page, theme);

    // 折叠标题栏：标题与计数档位、折叠图标、结构高度
    await expectTokenValue(page, page.locator(".definition-panel .head-title"), "font-size", "--font-label");
    await expectTokenValue(page, page.locator(".definition-panel .head-title small"), "font-size", "--font-caption");
    await expectTokenValue(page, page.locator(".definition-panel .panel-head"), "min-height", "--panel-head-min-height");
    await expectTokenValue(page, page.locator(".definition-panel .head-toggle"), "min-height", "--control-height-default");
    const chevron = page.locator(".definition-panel .head-toggle .ui-icon");
    await expect(chevron, "折叠字形改用本地 SVG 图标").toHaveCount(1);
    await expectTokenValue(page, chevron, "width", "--icon-size-sm", "box");
    await expectTokenValue(page, chevron, "height", "--icon-size-sm", "box");

    // 查询区：可见弱化 label（不靠 placeholder）、38px 输入、结构宽度与圆角令牌
    const search = page.getByRole("searchbox", {name: "搜索字段"});
    await expect(page.locator(".definition-panel .query-bar label").first(), "搜索框必须有可见 label").toHaveText("搜索字段");
    await expectTokenValue(page, search, "height", "--input-height", "box");
    await expectTokenValue(page, search, "width", "--panel-search-width", "box");
    await expectTokenValue(page, search, "padding-left", "--space-2");
    const scopeFilter = page.getByRole("combobox", {name: "作用域筛选"});
    await expectTokenValue(page, scopeFilter, "height", "--input-height", "box");
    await expectTokenValue(page, scopeFilter, "border-radius", "--radius-md");

    // 主次动作：普通按钮档 36px + 主按钮层级由原语承载
    await expectTokenValue(page, page.locator(".definition-panel .link-actions .ui-button"), "height", "--button-height", "box");
    await expect(page.locator(".definition-panel .link-actions .ui-button--primary")).toHaveCount(1);

    // 新增区：字段组合改用原语，可见 label、输入 38px、辅助与错误文案档
    await page.getByRole("button", {name: "新增字段"}).click();
    await expect(page.locator(".definition-panel .add-form")).toBeVisible();
    for (const field of ["属性作用域", "属性名称", "默认值"]) {
      await expectTokenValue(page, page.getByLabel(field, {exact: true}), "height", "--input-height", "box");
    }
    await expectTokenValue(page, page.locator(".definition-panel .add-actions .hint"), "font-size", "--font-caption");
    await page.getByRole("button", {name: "加入草稿"}).click();
    await expectTokenValue(page, page.locator(".definition-panel .field-error"), "font-size", "--font-caption");

    // 定义表：表体字号档、行高令牌（表头行由 `th,td` 同条规则给定高度，表体行被单元格内的
    // 展开/删除按钮撑高，属既有事实，故以表头行核对高度令牌）、页脚计数档、分页按钮普通档
    await expectTokenValue(page, page.locator(".definition-panel table"), "font-size", "--font-table");
    await expectTokenValue(page, page.locator(".definition-panel thead th").first(), "height", "--definition-row-height", "box");
    await expectTokenValue(page, page.locator(".definition-panel .foot-info"), "font-size", "--font-caption");
    await expectTokenValue(page, page.locator(".definition-panel .pager .ui-button").first(), "height", "--button-height", "box");

    // CSV 面板：标题与状态档、标题栏高度、下载项点击高度、流程提示档
    await expectTokenValue(page, page.locator(".csv-panel .head-title"), "font-size", "--font-label");
    await expectTokenValue(page, page.locator(".csv-panel .head-status"), "font-size", "--font-caption");
    await expectTokenValue(page, page.locator(".csv-panel .panel-head"), "min-height", "--panel-head-min-height");
    await expectTokenValue(page, page.locator(".csv-panel .io-menu a").first(), "min-height", "--control-height-default");
    await page.getByRole("button", {name: "导入 CSV"}).click();
    await expect(page.locator(".csv-panel .csv-flow")).toBeVisible();
    await expectTokenValue(page, page.locator(".csv-panel .csv-flow label"), "font-size", "--font-label");
    await expectTokenValue(page, page.locator(".csv-panel .csv-hint").first(), "font-size", "--font-caption");
    await expectTokenValue(page, page.locator(".csv-panel").getByRole("button", {name: "关闭导入"}), "height", "--button-height", "box");

    // 值面板：标题栏、工具行、字段标签与输入、状态徽标、行内文字按钮
    await expectTokenValue(page, page.locator(".value-panel .head-title"), "font-size", "--font-label");
    await expectTokenValue(page, page.locator(".value-panel .panel-head"), "min-height", "--panel-head-min-height");
    await expectTokenValue(page, page.locator(".value-panel .flag").first(), "font-size", "--font-caption");
    await expectTokenValue(page, page.locator(".value-panel .hint").first(), "font-size", "--font-caption");
    const valueSearch = page.getByRole("searchbox", {name: "搜索属性值"});
    await expectTokenValue(page, valueSearch, "height", "--input-height", "box");
    await expectTokenValue(page, valueSearch, "width", "--panel-search-width", "box");
    await expectTokenValue(page, page.getByRole("combobox", {name: "搜索范围"}), "height", "--input-height", "box");
    await expectTokenValue(page, page.locator(".value-panel .value-toolbar .only-changed"), "font-size", "--font-label");
    await expectTokenValue(page, page.locator(".value-panel .match-count"), "font-size", "--font-caption");
    await expectTokenValue(page, page.locator(".value-panel .value-item label").first(), "font-size", "--font-label");
    await expectTokenValue(page, page.locator(".value-panel .value-item input").first(), "height", "--input-height", "box");
    await expectTokenValue(page, page.locator(".value-panel .field-foot").first(), "min-height", "--control-height-default");
    await expectTokenValue(page, page.locator(".value-panel button.link").first(), "min-height", "--control-height-default");
    await expectTokenValue(page, page.locator(".value-panel .head-actions .ui-button--primary"), "height", "--button-height", "box");

    // Step 1 点名的六个排版属性中，`font-family` 与 `line-height` 此前零断言（首轮评审 Important-2）：
    // 折叠标题、导入导出、搜索、主次动作四组逐项锁定。上面已覆盖的高度类属性只是**部分**的：
    // 导入导出有 min-height、搜索框有 height/width、主按钮有 height，而折叠标题只断言了 font-size，
    // 次按钮没有任何结构尺寸断言；`padding` 与 `border-radius` 全文件各只有一条，且都落在
    // **定义面板查询区**（搜索框的 `padding-left`、作用域筛选的 `border-radius`），**不覆盖**本四组元素。
    // 搜索用 `valueSearch` 角色定位器而非 `.value-panel .ui-input__control` + `.first()`：后者顺序相关，
    // DOM 顺序一变就会静默改指某个值项输入并继续通过，而「搜索」不再被覆盖。
    await expectTokenFontFamily(page, ".value-panel .head-title", "--font-ui");
    await expectTokenFontFamily(page, ".csv-panel .io-menu a", "--font-ui");
    await expectTokenFontFamily(page, valueSearch, "--font-ui");
    await expectTokenFontFamily(page, ".value-panel .head-actions .ui-button--primary", "--font-ui");
    await expectTokenFontFamily(page, ".value-panel .head-actions .ui-button--secondary", "--font-ui");
    const bodyLineHeight = await tokenNumber(page, "--line-height-body");
    await expectLineHeightRatio(page, page.locator(".value-panel .head-title"), bodyLineHeight, "折叠标题");
    await expectLineHeightRatio(page, page.locator(".csv-panel .io-menu a"), bodyLineHeight, "导入导出");
    await expectLineHeightRatio(page, valueSearch, bodyLineHeight, "搜索输入");
    await expectLineHeightRatio(page, page.locator(".value-panel .head-actions .ui-button--primary"), bodyLineHeight, "主按钮");
    await expectLineHeightRatio(page, page.locator(".value-panel .head-actions .ui-button--secondary"), bodyLineHeight, "次按钮");

    // 两个模态：标题不再落 UA 原生尺度，结构尺寸来自令牌
    const nameItem = page.locator(".value-panel .value-item").first();
    await nameItem.getByRole("button", {name: /^展开编辑/}).click();
    const expandCard = page.locator(".value-panel .modal-card");
    await expect(expandCard).toBeVisible();
    await expectTokenValue(page, expandCard.locator("h2"), "font-size", "--modal-title-font-size");
    await expectTokenValue(page, expandCard.locator("textarea"), "min-height", "--expand-editor-min-height");
    await expandCard.getByRole("button", {name: "取消"}).click();
    await nameItem.getByRole("button", {name: /^值对照/}).click();
    const compareCard = page.locator(".compare-card");
    await expect(compareCard).toBeVisible();
    await expectTokenValue(page, compareCard.locator("h2"), "font-size", "--modal-title-font-size");
    await expectTokenValue(page, compareCard, "max-width", "--compare-card-max-width");
    await expectTokenValue(page, compareCard.locator(".compare-hint"), "font-size", "--font-label");
    await expectTokenValue(page, compareCard.locator(".compare-item pre").first(), "max-height", "--compare-item-max-height");
  });
}

// Ruling 33（Task 5 修复轮的核心回归守卫）：hover 必须真的命中控件。
// 页面侧原有的 `.value-item input:hover` 在控件换成 `UiInput` 后永不生效——`UiInput` 的根元素是
// `<span class="ui-input">`，真正的 `<input class="ui-input__control">` 不是根元素，而 scoped 的
// `data-v-*` 只追加到子组件根元素上（Task 6 的 `SheetPropertyEditor.vue:108` 是同一个待爆的雷）。
// 这类「声明写了但不命中」的失效源文本断言抓不到，只有真实 hover 后的计算样式能抓到。
for (const theme of THEMES) {
  test(`值面板字段输入 hover 后由 UiInput 原语提供强调色描边：${theme}`, async ({page}) => {
    await openWorkspace(page, theme);
    const fieldControl = ".value-panel .value-item:not(.invalid) .ui-input__control";
    // 先确认默认态是常规边框色，避免把「本来就是强调色」误读成 hover 生效
    await expectToken(page, fieldControl, "borderTopColor", "--color-border-strong");
    await page.locator(fieldControl).first().hover();
    await expectToken(page, fieldControl, "borderTopColor", "--color-accent");
  });
}

for (const theme of THEMES) {
  test(`1440 双主题五状态同状态证据：${theme}`, async ({page}, info) => {
    await page.setViewportSize({width: 1440, height: 900});
    for (const state of ["default", "dirty-pending", "error", "add-field", "csv"] as const) {
      if (state === "default") {
        await openWorkspace(page, theme);
      } else if (state === "dirty-pending") {
        await installPropertiesFixture(page, {theme, initialDraft: pendingDraft()});
        await openProperties(page);
        await page.getByRole("textbox", {name: "属性 设计阶段"}).fill("初步设计");
      } else if (state === "error") {
        await installPropertiesFixture(page, {
          theme,
          initialDraft: pendingDraft(),
          failDraftSave: () => ({code: "DRAFT_SAVE_FAILED", message: "草稿保存失败", fields: {项目编号: "演示校验错误"}}),
        });
        await openProperties(page);
        await page.getByRole("textbox", {name: "属性 设计阶段"}).fill("初步设计");
        await page.getByRole("button", {name: "更新图纸集"}).click();
        // 虚构 code 不在错误目录（I18N-11）：摘要显示本地化未知摘要，兼容原文不进主提示
        await expect(page.locator(".error-summary")).toContainText("操作失败，发生未知错误");
      } else if (state === "add-field") {
        await openWorkspace(page, theme);
        await page.getByRole("button", {name: "新增字段"}).click();
        await expect(page.locator(".definition-panel .add-form")).toBeVisible();
      } else {
        await openWorkspace(page, theme);
        await page.getByRole("button", {name: "导入 CSV"}).click();
        await expect(page.locator(".csv-panel .csv-flow")).toBeVisible();
      }
      await page.mouse.move(0, 0);
      await attachScreenshot(page, info, state, theme);
    }
  });

  test(`窄屏单列同状态证据：${theme}`, async ({page}, info) => {
    await page.setViewportSize({width: 900, height: 768});
    await openWorkspace(page, theme);
    const columns = await page.locator(".value-panel .value-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
    expect(columns, "900×768 属性值单列").toBe(1);
    await page.mouse.move(0, 0);
    await attachScreenshot(page, info, "narrow-single-column", theme);
  });

  test(`定义表横向溢出同状态证据（200% 缩放）：${theme}`, async ({page}, info) => {
    await page.setViewportSize({width: 1024, height: 768});
    await openWorkspace(page, theme);
    await page.evaluate(() => document.documentElement.style.setProperty("zoom", "2"));
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator(".definition-panel .table-window")).toHaveClass(/sticky-actions/);
    await page.locator(".definition-panel .table-window").scrollIntoViewIfNeeded();
    await page.mouse.move(0, 0);
    await attachScreenshot(page, info, "def-table-overflow", theme);
  });
}
