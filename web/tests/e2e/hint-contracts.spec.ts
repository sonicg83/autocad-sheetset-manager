// PLAN-DM-048 Task 8：迁移提示的浏览器计算样式、ARIA 关联和窄视口长文验收。
// 颜色从实际 computed style 读取；900px 仅作为韧性边界，不据此重定义产品断点。
import {expect, test, type Page, type TestInfo} from "@playwright/test";
import {writeFileSync} from "node:fs";
import {creationPreviewWithDiagnostics, chooseStandard, installCreation, openCreation, openGroupsStep} from "./fixtures/creation";
import {installPreferenceSnapshot} from "./fixtures/settings";

const VIEWPORTS = [
  {width: 1024, height: 768},
  {width: 1120, height: 768},
  {width: 1440, height: 900},
  {width: 900, height: 768},
] as const;
const THEMES = ["light", "dark"] as const;

test.beforeEach(async ({page}) => {
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async () => null,
        select_folder: async () => null,
        on_files_dropped: async () => {},
      },
    };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.route("**/api/extensions", route => route.fulfill({json: []}));
});

async function openDiagnosticReview(page: Page, theme: "light" | "dark" = "light"): Promise<void> {
  await installPreferenceSnapshot(page, theme);
  await installCreation(page, {preview: creationPreviewWithDiagnostics()});
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);
  await page.getByRole("button", {name: "新建图纸组"}).click();
  await page.getByRole("button", {name: "下一步"}).click();
  await expect(page.getByRole("region", {name: "检查并创建"})).toBeVisible();
  await expect(page.getByTestId("creation-preview-errors")).toBeVisible();
  await expect(page.getByTestId("creation-preview-warnings")).toBeVisible();
  await expect(page.locator("[role='alert']:visible")).toHaveCount(1);
  await expect(page.getByTestId("creation-preview-errors")).toHaveAttribute("aria-live", "assertive");
}

async function setTheme(page: Page, theme: "light" | "dark"): Promise<void> {
  await page.locator("html").evaluate((element, value) => element.setAttribute("data-theme", value), theme);
}

async function capture(page: Page, info: TestInfo, name: string): Promise<void> {
  const path = info.outputPath(name);
  await page.screenshot({path, animations: "disabled"});
  await info.attach(name, {path, contentType: "image/png"});
}

test("hint_contrast_ratio_meets_wcag_threshold", async ({page}, info) => {
  await openDiagnosticReview(page);

  for (const theme of THEMES) {
    await setTheme(page, theme);
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      const geometry = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      }));
      expect(geometry.scrollWidth, `${viewport.width}x${viewport.height} ${theme} 页面宽度`).toBeLessThanOrEqual(geometry.clientWidth);

      const hints = await page.locator(".ui-hint:visible").evaluateAll(elements => {
        const parse = (value: string): number[] => (value.match(/[\d.]+/gu) ?? []).slice(0, 4).map(Number);
        const luminance = (rgb: number[]) => rgb.slice(0, 3).map(channel => {
          const normalized = channel / 255;
          return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
        }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index]!, 0);
        const contrast = (first: number[], second: number[]) => {
          const a = luminance(first);
          const b = luminance(second);
          return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        };
        const backdrop = (element: Element) => {
          const chain: Element[] = [];
          for (let current: Element | null = element; current !== null; current = current.parentElement) chain.unshift(current);
          let color = [255, 255, 255];
          for (const current of chain) {
            const next = parse(getComputedStyle(current).backgroundColor);
            if (next.length < 3) continue;
            const alpha = next.length > 3 ? next[3]! : 1;
            color = color.slice(0, 3).map((channel, index) => next[index]! * alpha + channel * (1 - alpha));
          }
          return color;
        };
        const probe = document.createElement("span");
        document.body.append(probe);
        const tokenColor = (name: string) => {
          probe.style.color = `var(${name})`;
          return getComputedStyle(probe).color;
        };
        const expected = {
          lead: tokenColor("--color-text-secondary"),
          help: tokenColor("--color-text-muted"),
          neutral: tokenColor("--color-text-secondary"),
          info: tokenColor("--color-info"),
          success: tokenColor("--color-success"),
          warning: tokenColor("--color-warning"),
          error: tokenColor("--color-danger"),
        };
        probe.remove();
        return elements.map(element => {
          const style = getComputedStyle(element);
          const kind = (element as HTMLElement).dataset["hintKind"] ?? "";
          const tone = (element as HTMLElement).dataset["tone"] ?? kind;
          const color = style.color;
          return {
            kind,
            tone,
            fontSize: style.fontSize,
            color,
            expectedColor: expected[kind === "lead" || kind === "help" ? kind : tone as keyof typeof expected],
            contrast: contrast(parse(color), backdrop(element)),
          };
        });
      });

      expect(hints.some(hint => hint.kind === "lead"), `Lead 可见：${theme} ${viewport.width}`).toBe(true);
      expect(hints.some(hint => hint.kind === "help"), `Help 可见：${theme} ${viewport.width}`).toBe(true);
      for (const hint of hints) {
        expect(hint.fontSize, `${hint.kind}/${hint.tone} 字号`).toBe(hint.kind === "lead" ? "13px" : "12px");
        expect(hint.color, `${hint.kind}/${hint.tone} 语义色`).toBe(hint.expectedColor);
        expect(hint.contrast, `${hint.kind}/${hint.tone} 文本对比度 ${theme} ${viewport.width}`).toBeGreaterThanOrEqual(4.5);
      }

      const hintVariants = await page.evaluate(() => {
        const source = document.querySelector<HTMLElement>(".ui-hint--lead");
        if (source === null) throw new Error("创建预览缺少实际 UiHint，无法验证提示样式");
        const host = document.createElement("div");
        host.style.cssText = "position:absolute;left:-10000px;top:0;width:600px;background:var(--color-bg-surface);visibility:hidden";
        document.body.append(host);
        const parse = (value: string): number[] => (value.match(/[\d.]+/gu) ?? []).slice(0, 4).map(Number);
        const luminance = (rgb: number[]) => rgb.slice(0, 3).map(channel => {
          const normalized = channel / 255;
          return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
        }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index]!, 0);
        const contrast = (first: number[], second: number[]) => {
          const a = luminance(first);
          const b = luminance(second);
          return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        };
        const probe = document.createElement("span");
        document.body.append(probe);
        const expected = {
          lead: getComputedStyle(probe).color,
          help: "",
          neutral: "",
          info: "",
          success: "",
          warning: "",
          error: "",
        };
        const token = (name: string) => {
          probe.style.color = `var(${name})`;
          return getComputedStyle(probe).color;
        };
        expected.lead = token("--color-text-secondary");
        expected.help = token("--color-text-muted");
        expected.neutral = token("--color-text-secondary");
        expected.info = token("--color-info");
        expected.success = token("--color-success");
        expected.warning = token("--color-warning");
        expected.error = token("--color-danger");
        probe.remove();
        const variants = [
          {kind: "lead", tone: "", classes: ["ui-hint--lead"]},
          {kind: "help", tone: "", classes: ["ui-hint--help"]},
          ...["neutral", "info", "success", "warning", "error"].map(tone => ({kind: "status", tone, classes: ["ui-hint--status", `ui-hint--tone-${tone}`]})),
          {kind: "error", tone: "error", classes: ["ui-hint--error", "ui-hint--tone-error"]},
        ];
        const result = variants.map(variant => {
          const element = source.cloneNode(true) as HTMLElement;
          for (const name of [...element.classList]) if (name.startsWith("ui-hint--")) element.classList.remove(name);
          element.classList.add(...variant.classes);
          element.dataset["hintKind"] = variant.kind;
          element.dataset["tone"] = variant.tone;
          element.textContent = `${variant.kind} ${variant.tone} contrast probe`;
          host.append(element);
          const style = getComputedStyle(element);
          const background = getComputedStyle(host).backgroundColor;
          const color = style.color;
          const expectedColor = expected[variant.kind === "lead" || variant.kind === "help" ? variant.kind : variant.tone as keyof typeof expected];
          return {kind: variant.kind, tone: variant.tone, fontSize: style.fontSize, color, expectedColor, background, contrast: contrast(parse(color), parse(background))};
        });
        host.remove();
        return result;
      });
      expect(hintVariants).toHaveLength(8);
      for (const hint of hintVariants) {
        expect(hint.fontSize, `${hint.kind}/${hint.tone} CSS 提示字号`).toBe(hint.kind === "lead" ? "13px" : "12px");
        expect(hint.color, `${hint.kind}/${hint.tone} CSS 提示语义色`).toBe(hint.expectedColor);
        expect(hint.contrast, `${hint.kind}/${hint.tone} CSS 提示对比度 ${theme}`).toBeGreaterThanOrEqual(4.5);
      }

      const banners = await page.evaluate(() => {
        const source = document.querySelector<HTMLElement>("[data-hint-kind='banner']");
        if (source === null) throw new Error("诊断页缺少实际 UiBanner，无法验证生产样式");
        const host = document.createElement("div");
        host.style.cssText = "position:absolute;left:0;top:0;width:min(600px,calc(100vw - 32px));visibility:hidden;z-index:-1";
        document.body.append(host);
        const parse = (value: string): number[] => (value.match(/[\d.]+/gu) ?? []).slice(0, 4).map(Number);
        const luminance = (rgb: number[]) => rgb.slice(0, 3).map(channel => {
          const normalized = channel / 255;
          return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
        }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index]!, 0);
        const contrast = (first: number[], second: number[]) => {
          const a = luminance(first);
          const b = luminance(second);
          return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        };
        const result = (["notice", "success", "warning", "error"] as const).map(tone => {
          const banner = source.cloneNode(true) as HTMLElement;
          for (const name of [...banner.classList]) if (name.startsWith("ui-banner--")) banner.classList.remove(name);
          banner.classList.add(`ui-banner--${tone}`);
          banner.dataset["tone"] = tone;
          const content = banner.querySelector<HTMLElement>(".ui-banner__content");
          if (content !== null) content.textContent = `Tone ${tone}: ${"long-path-segment-".repeat(8)}`;
          host.append(banner);
          const style = getComputedStyle(banner);
          return {
            tone,
            foreground: style.color,
            background: style.backgroundColor,
            border: style.borderInlineStartColor,
            textRatio: contrast(parse(style.color), parse(style.backgroundColor)),
            uiRatio: contrast(parse(style.borderInlineStartColor), parse(style.backgroundColor)),
            width: banner.getBoundingClientRect().width,
            scrollWidth: banner.scrollWidth,
            clientWidth: banner.clientWidth,
          };
        });
        host.remove();
        return result;
      });
      expect(banners).toHaveLength(4);
      for (const banner of banners) {
        expect(banner.textRatio, `${banner.tone} 横幅文本对比度 ${theme}`).toBeGreaterThanOrEqual(4.5);
        expect(banner.uiRatio, `${banner.tone} 横幅边线对比度 ${theme}`).toBeGreaterThanOrEqual(3);
        expect(banner.scrollWidth, `${banner.tone} 长文不得撑宽横幅 ${theme}`).toBeLessThanOrEqual(banner.clientWidth);
        expect(banner.width, `${banner.tone} 横幅宽度不得越过 viewport`).toBeLessThanOrEqual(viewport.width);
      }

      const computedPath = info.outputPath(`g8-computed-hints-${theme}-${viewport.width}x${viewport.height}.json`);
      writeFileSync(computedPath, JSON.stringify({theme, viewport, hints, hintVariants, banners}, null, 2), "utf8");
      await info.attach(`g8-computed-hints-${theme}-${viewport.width}x${viewport.height}.json`, {
        path: computedPath,
        contentType: "application/json",
      });

      if ((viewport.width === 1440 || viewport.width === 900)) {
        await capture(page, info, `g8-creation-review-${theme}-${viewport.width}x${viewport.height}.png`);
      }
    }
  }
});

test("hint_idref_targets_are_unique_and_invalid_fields_keep_their_error", async ({page}) => {
  await installCreation(page, {preview: creationPreviewWithDiagnostics()});
  await openCreation(page);
  await chooseStandard(page);
  await openGroupsStep(page);
  await page.getByRole("button", {name: "新建图纸组"}).click();
  const title = page.locator('tr[data-group-id="group-1"] input[type="text"]').first();
  await title.fill("");
  await page.getByRole("button", {name: "下一步"}).click();
  const errorBanner = page.getByTestId("creation-preview-errors");
  await expect(errorBanner).toBeVisible();
  await expect(errorBanner).toHaveAttribute("role", "alert");
  await errorBanner.getByRole("button", {name: "返回修改第 1 项"}).click();
  await expect(title).toBeFocused();
  await expect(title).toHaveAttribute("aria-invalid", "true");
  await expect(title).toHaveAttribute("aria-describedby", /creation-group-issue/u);

  const associations = await page.evaluate(() => {
    const ids = [...document.querySelectorAll<HTMLElement>("[id]")].map(element => element.id);
    const references = [...document.querySelectorAll<HTMLElement>("[aria-describedby]")].map(element => ({
      invalid: element.getAttribute("aria-invalid"),
      ids: (element.getAttribute("aria-describedby") ?? "").trim().split(/\s+/u).filter(Boolean),
    }));
    return {ids, references};
  });
  expect(new Set(associations.ids).size, "当前 DOM 的 ID 均唯一").toBe(associations.ids.length);
  expect(associations.references.length).toBeGreaterThan(0);
  for (const reference of associations.references) {
    for (const id of reference.ids) expect(associations.ids.filter(candidate => candidate === id), `IDREF ${id} 恰有一个目标`).toHaveLength(1);
  }
  const invalid = associations.references.filter(reference => reference.invalid === "true");
  expect(invalid.length).toBeGreaterThan(0);
  expect(invalid.every(reference => reference.ids.length > 0), "无效字段继续关联错误/帮助文字").toBe(true);
});

test("900×768 双主题长路径与多行错误不裁切也不产生页面横溢", async ({page}) => {
  await page.setViewportSize({width: 900, height: 768});
  await openDiagnosticReview(page);
  for (const theme of THEMES) {
    await setTheme(page, theme);
    const geometry = await page.getByTestId("creation-preview-errors").evaluate(element => {
      const content = element.querySelector<HTMLElement>(".ui-banner__content");
      if (content === null) throw new Error("错误横幅缺少内容容器");
      content.textContent = `C:\\虚构工程\\${"非常长且没有空格的目录名".repeat(16)}\\错误记录.txt\n第二行：保留完整的诊断与恢复信息`;
      const banner = element as HTMLElement;
      return {
        bannerWidth: banner.getBoundingClientRect().width,
        bannerClientWidth: banner.clientWidth,
        bannerScrollWidth: banner.scrollWidth,
        bannerHeight: banner.getBoundingClientRect().height,
        documentClientWidth: document.documentElement.clientWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        wrap: getComputedStyle(content).overflowWrap,
      };
    });
    expect(geometry.wrap).toBe("anywhere");
    expect(geometry.bannerScrollWidth).toBeLessThanOrEqual(geometry.bannerClientWidth);
    expect(geometry.bannerWidth).toBeLessThanOrEqual(900);
    expect(geometry.bannerHeight).toBeGreaterThan(48);
    expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.documentClientWidth);
  }
});
