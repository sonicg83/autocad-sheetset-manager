// bootstrap 启动顺序与降级行为单测（ARCH-DM-005 §8.1 / I18N-01、I18N-04、I18N-06）：
// 设置请求结束前不 mount；读取失败或挂起超时按系统规则降级挂载；
// 全程只有一个 i18n 实例；applyLocale 同步 i18n locale 与 <html lang>。
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

const {fetchSettingsMock, createAppMock, useMock, mountMock} = vi.hoisted(() => ({
  fetchSettingsMock: vi.fn(),
  createAppMock: vi.fn(),
  useMock: vi.fn(),
  mountMock: vi.fn(),
}));

vi.mock("../api/settings", () => ({fetchSettings: fetchSettingsMock}));
// bootstrap 负责挂载；单测环境用桩 createApp 拦截，断言插件注册与挂载时机而不真实渲染
vi.mock("vue", async importOriginal => {
  const actual = await importOriginal<typeof import("vue")>();
  return {...actual, createApp: createAppMock.mockImplementation(() => ({use: useMock, mount: mountMock}))};
});
// App.vue 仅为 bootstrap 的挂载目标；避免在 node 环境加载完整 SFC
vi.mock("../App.vue", () => ({default: {name: "AppStub"}}));

import {applyLocale, bootstrap, i18n} from "./index";
import type {SettingsItem, SettingsSnapshot} from "../api/settings";

// node 测试环境没有 DOM：提供最小 document 桩以验证 <html lang> 同步
vi.stubGlobal("document", {documentElement: {lang: ""}});

function localeItem(value: SettingsItem["value"]): SettingsItem {
  return {key: "ui_locale", label: "", category: "", control: "enum", value, default: "system", source: "file", hasFileOverride: true};
}

function snapshotWithUiLocale(value: SettingsItem["value"] | null): SettingsSnapshot {
  return {
    schemaVersion: 1,
    configRevision: 1,
    diagnostics: [],
    schemaBlocked: false,
    items: value === null ? [] : [localeItem(value)],
  };
}

function stubNavigator(languages: readonly string[], language = languages[0] ?? ""): void {
  vi.stubGlobal("navigator", {languages, language});
}

beforeEach(async () => {
  vi.clearAllMocks();
  // 回到基线语言，保证每个用例观察到的语言变化来自当次 bootstrap/applyLocale
  i18n.global.locale.value = "zh-CN";
  document.documentElement.lang = "";
  stubNavigator(["zh-CN"]);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.stubGlobal("document", {documentElement: {lang: ""}});
});

describe("bootstrap", () => {
  it("设置请求结束前不 mount，请求结束后才挂载", async () => {
    let resolveFetch!: (snapshot: SettingsSnapshot) => void;
    fetchSettingsMock.mockImplementation(
      () => new Promise<SettingsSnapshot>(resolve => { resolveFetch = resolve; }),
    );

    const booting = bootstrap();
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(mountMock).not.toHaveBeenCalled();

    resolveFetch(snapshotWithUiLocale("en-US"));
    await booting;
    expect(mountMock).toHaveBeenCalledTimes(1);
    expect(mountMock).toHaveBeenCalledWith("#app");
  });

  it("挂载前把唯一 i18n 实例注册为 Vue 插件（use 先于 mount）", async () => {
    fetchSettingsMock.mockResolvedValue(snapshotWithUiLocale("zh-CN"));

    await bootstrap();

    expect(useMock).toHaveBeenCalledTimes(1);
    expect(useMock).toHaveBeenCalledWith(i18n);
    // 插件注册必须先于挂载，否则组件内 useI18n()/$t 运行时不可用
    expect(useMock.mock.invocationCallOrder[0]).toBeLessThan(mountMock.mock.invocationCallOrder[0]);
  });

  it("设置读取失败时按系统规则继续启动，不阻断挂载", async () => {
    fetchSettingsMock.mockRejectedValue(new Error("network down"));
    stubNavigator(["ja-JP"]);

    await bootstrap();

    expect(mountMock).toHaveBeenCalledTimes(1);
    expect(i18n.global.locale.value).toBe("en-US");
    expect(document.documentElement.lang).toBe("en-US");
  });

  it("设置读取挂起超过 5s 视为失败，按系统规则降级挂载", async () => {
    vi.useFakeTimers();
    fetchSettingsMock.mockReturnValue(new Promise<SettingsSnapshot>(() => {}));
    stubNavigator(["zh-TW"]);

    const booting = bootstrap();
    await vi.advanceTimersByTimeAsync(5_000);
    await booting;

    expect(mountMock).toHaveBeenCalledTimes(1);
    expect(i18n.global.locale.value).toBe("zh-CN");
    expect(document.documentElement.lang).toBe("zh-CN");
  });

  it("显式 ui_locale 覆盖系统语言并同步 <html lang>", async () => {
    fetchSettingsMock.mockResolvedValue(snapshotWithUiLocale("en-US"));
    stubNavigator(["zh-CN"]); // 系统是中文，显式英文设置仍优先

    await bootstrap();

    expect(mountMock).toHaveBeenCalledTimes(1);
    expect(i18n.global.locale.value).toBe("en-US");
    expect(document.documentElement.lang).toBe("en-US");
  });

  it("ui_locale 缺失或非法时视为 system 解析", async () => {
    fetchSettingsMock.mockResolvedValue(snapshotWithUiLocale(null));
    stubNavigator(["zh-CN"]);
    await bootstrap();
    expect(i18n.global.locale.value).toBe("zh-CN");

    fetchSettingsMock.mockResolvedValue(snapshotWithUiLocale("fr-FR"));
    stubNavigator(["en-US"]);
    await bootstrap();
    expect(i18n.global.locale.value).toBe("en-US");
  });

  it("bootstrap 复用同一个 i18n 实例，不重建", async () => {
    fetchSettingsMock.mockResolvedValue(snapshotWithUiLocale("en-US"));
    const probe = i18n.global as unknown as Record<string, unknown>;
    probe.__singletonProbe = Symbol("instance");

    await bootstrap();

    expect(probe.__singletonProbe).toBeDefined();
    expect(i18n.global.locale.value).toBe("en-US"); // 若被重建，语言不会反映本次解析结果
  });
});

describe("applyLocale", () => {
  it("同步更新 i18n locale 与 <html lang>", async () => {
    await applyLocale("en-US");
    expect(i18n.global.locale.value).toBe("en-US");
    expect(document.documentElement.lang).toBe("en-US");

    await applyLocale("zh-CN");
    expect(i18n.global.locale.value).toBe("zh-CN");
    expect(document.documentElement.lang).toBe("zh-CN");
  });
});
