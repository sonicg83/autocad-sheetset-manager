// 关于接口客户端单测（PLAN-DM-025 任务 6）：应用元数据在应用会话内只应请求一次。
// fetchAbout() 以模块级 Promise memo 承载在途请求——并发调用共享同一请求、成功后复用
// 同一份静态元数据；失败不缓存，下次调用显式重试（一次网络抖动不得固化成
// "关于分区永久加载失败"）。memo 是模块级状态，故每个用例先 resetModules 再动态导入。
// client.ts 经 ../i18n 取错误文案：node 单测按 useSettings.test.ts 先例 mock i18n 入口，
// 避免经 i18n/index.ts 连带加载 App.vue。
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";

vi.mock("../i18n", () => ({
  i18n: {global: {te: () => true, t: (key: string) => key}},
}));

const RAW_ABOUT = {
  app_name: "DST Manager",
  version: "0.3.0",
  license: {spdx: "MIT", text: "MIT License\n\nPermission is hereby granted, free of charge..."},
  homepage: "https://github.com/sonicg83/autocad-sheetset",
  feedback_url: "https://github.com/sonicg83/autocad-sheetset/issues",
};

// 期望值即 snake_case → camelCase 映射结果（契约在网络层，不在组件层）
const EXPECTED = {
  appName: "DST Manager",
  version: "0.3.0",
  license: RAW_ABOUT.license,
  homepage: RAW_ABOUT.homepage,
  feedbackUrl: RAW_ABOUT.feedback_url,
};

function okResponse(body: unknown) {
  return {ok: true, status: 200, json: async () => body};
}

function failureResponse() {
  return {ok: false, status: 500, json: async () => ({code: "INTERNAL_ERROR", message: "boom"})};
}

async function freshFetchAbout() {
  vi.resetModules();
  return (await import("./settings")).fetchAbout;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchAbout 会话内唯一请求", () => {
  it("并发两次调用只发一个 GET /api/about，并共享同一份元数据", async () => {
    const fetchMock = vi.fn(async () => okResponse(RAW_ABOUT));
    vi.stubGlobal("fetch", fetchMock);
    const fetchAbout = await freshFetchAbout();

    const [first, second] = await Promise.all([fetchAbout(), fetchAbout()]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/about", {headers: {"Content-Type": "application/json"}});
    expect(first).toEqual(EXPECTED);
    expect(second).toBe(first);
  });

  it("首次成功后再次调用复用同一份元数据：不再发起请求", async () => {
    const fetchMock = vi.fn(async () => okResponse(RAW_ABOUT));
    vi.stubGlobal("fetch", fetchMock);
    const fetchAbout = await freshFetchAbout();

    const first = await fetchAbout();
    const again = await fetchAbout();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(again).toBe(first);
  });

  it("首次请求失败不缓存：再次调用重新请求并返回元数据", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(failureResponse())
      .mockResolvedValueOnce(okResponse(RAW_ABOUT));
    vi.stubGlobal("fetch", fetchMock);
    const fetchAbout = await freshFetchAbout();

    await expect(fetchAbout()).rejects.toThrow();
    await expect(fetchAbout()).resolves.toEqual(EXPECTED);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("在途请求失败时并发调用者共享同一拒绝，且重试恰好再发一个请求", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(failureResponse())
      .mockResolvedValueOnce(okResponse(RAW_ABOUT));
    vi.stubGlobal("fetch", fetchMock);
    const fetchAbout = await freshFetchAbout();

    const inFlight = [fetchAbout(), fetchAbout()];
    await expect(inFlight[0]).rejects.toThrow();
    await expect(inFlight[1]).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await expect(fetchAbout()).resolves.toEqual(EXPECTED);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
