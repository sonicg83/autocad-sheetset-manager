// 语言解析单测（ARCH-DM-005 §4.2 / I18N-03）：
// 显式设置 > 系统语言（zh-* → zh-CN，其他可识别非中文语言 → en-US），
// 空列表 / navigator 异常 / 全部不可识别时回退 zh-CN。
import {afterEach, describe, expect, it, vi} from "vitest";
import {resolveLocale} from "./locale";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("resolveLocale", () => {
  it("显式 zh-CN / en-US 优先于系统语言", () => {
    expect(resolveLocale("zh-CN", ["en-US", "ja-JP"])).toBe("zh-CN");
    expect(resolveLocale("en-US", ["zh-CN", "zh-TW"])).toBe("en-US");
  });

  it("system：zh 系语言映射 zh-CN（按首个可识别标签判定）", () => {
    expect(resolveLocale("system", ["zh-TW", "en-US"])).toBe("zh-CN");
    expect(resolveLocale("system", ["en-US", "zh-CN"])).toBe("en-US");
    expect(resolveLocale("system", ["zh"])).toBe("zh-CN");
  });

  it("system：其他可识别非中文语言映射 en-US", () => {
    expect(resolveLocale("system", ["ja-JP"])).toBe("en-US");
    expect(resolveLocale("system", ["de-DE", "en-GB"])).toBe("en-US");
  });

  it("system：languages 缺省时读取 navigator.languages，为空再读 navigator.language", () => {
    vi.stubGlobal("navigator", {languages: ["ja-JP", "en-US"], language: "ja-JP"});
    expect(resolveLocale("system")).toBe("en-US");
    vi.stubGlobal("navigator", {languages: [], language: "fr-FR"});
    expect(resolveLocale("system")).toBe("en-US");
  });

  it("system：空语言列表回退 zh-CN", () => {
    expect(resolveLocale("system", [])).toBe("zh-CN");
    expect(resolveLocale("system")).toBe("zh-CN"); // navigator 也为空
  });

  it("system：navigator 访问异常回退 zh-CN", () => {
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      get() {
        throw new Error("navigator unavailable");
      },
    });
    expect(resolveLocale("system")).toBe("zh-CN");
  });

  it("system：不可识别的语言标签跳过，全部不可识别时回退 zh-CN", () => {
    expect(resolveLocale("system", ["", "und", "123", "中文"])).toBe("zh-CN");
  });
});
